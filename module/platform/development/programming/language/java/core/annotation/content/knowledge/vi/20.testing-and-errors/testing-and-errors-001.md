# Kiểm thử biên dịch thành công và những mẫu annotation phải bị từ chối

## 1. Vì sao phải có cả positive và negative compile tests?

Với annotation trong Java, test “mã hợp lệ biên dịch thành công” mới kiểm chứng một nửa hợp đồng. Một thư viện annotation hoặc annotation processor còn phải **từ chối mã sai**. Nếu sau khi sửa processor, đoạn mã có `path` sai quy tắc đột nhiên được compiler chấp nhận thì đó là lỗi, ngay cả khi các positive tests vẫn xanh.

Ta cần hai loại kiểm thử:

- **Positive compile test:** mẫu mã hợp lệ **phải được chấp nhận**; `javac` hoặc API `JavaCompiler` trả trạng thái thành công.
- **Negative compile test:** mẫu mã trái hợp đồng **phải bị từ chối**; quan trọng hơn, phải kiểm tra **đúng nguyên nhân từ chối**, không chỉ kiểm tra compiler thất bại vì bất kỳ lỗi nào.

Phân biệt hai nhóm lỗi:

1. **Quy tắc ngôn ngữ của `javac`:** sai `@Target`, thiếu phần tử bắt buộc, sai kiểu phần tử, giá trị không phải hằng compile-time, dùng nhiều annotation cùng loại khi không `@Repeatable`, khai báo phần tử annotation có kiểu không hợp lệ.
2. **Quy tắc nghiệp vụ tùy chỉnh:** chuỗi `path` phải bắt đầu bằng `/`, số `retries` phải trong một miền, phương thức được gắn annotation phải có chữ ký nhất định. Các điều kiện này **chỉ được từ chối tại compile-time khi có processor/công cụ đã thực thi quy tắc**.

Khi thiết kế bộ test, hãy nêu rõ rule nào do compiler bảo vệ và rule nào do processor bảo vệ. Điều này giúp phát hiện trường hợp **processor không được kích hoạt**, dù source vẫn biên dịch bình thường.

## 2. Một hợp đồng annotation để làm ví dụ

Giả sử dự án định nghĩa:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Retention(RetentionPolicy.SOURCE)
@Target(ElementType.METHOD)
@interface Route {
    String path();
    int retries() default 1;
}
```

Đoạn code này minh họa hợp đồng; ví dụ chạy độc lập phía dưới sẽ tự khai báo lại `Route` trong từng fixture.

Theo ngôn ngữ Java:

- `@Target(METHOD)` chỉ cho phép annotation gắn trực tiếp trên khai báo phương thức.
- `path()` là một phần tử `String` **bắt buộc** vì không có `default`.
- `retries()` có `default 1` nên người dùng có thể bỏ qua phần tử đó.
- `@Retention(SOURCE)` nghĩa là cách sử dụng annotation chỉ cần tồn tại trong giai đoạn mã nguồn/biên dịch. Annotation processor vẫn có thể đọc nó tại compile-time.

Thêm hợp đồng **nghiệp vụ** cho processor: `path` phải bắt đầu bằng dấu `/`; `retries` phải thuộc đoạn **0 đến 3**, kể cả 0 và 3. Các điều kiện này không tự xuất hiện trong hành vi mặc định của `javac`.

### Positive examples

```java
class GoodService {
    @Route(path = "/health")
    void health() {}

    @Route(path = "/orders", retries = 3)
    void orders() {}

    static final String BASE = "/find";

    @Route(path = BASE)
    void find() {}
}
```

Các phương thức nằm đúng vị trí. `BASE` là `static final String` được khởi tạo bằng constant expression, nên có thể dùng làm giá trị phần tử annotation. `health` dùng mặc định `retries=1`, còn `orders` dùng giá trị biên trên 3. Bộ test nên xác nhận **cả ba cách đều biên dịch thành công**.

## 3. Những mẫu mã `javac` phải từ chối ngay cả khi không có processor

Mỗi đoạn sau **cố ý sai**. Chúng không được ghép vào chương trình positive test rồi mong lệnh biên dịch thành công.

### 3.1 Sai vị trí `@Target`

```java
class WrongTarget {
    @Route(path = "/user")
    String user;
}
```

`Route` chỉ cho phép `METHOD`, không cho phép `FIELD`. Đây là lỗi ngôn ngữ Java do compiler kiểm tra. Nếu sau này thay `@Target` để thêm `FIELD`, kỳ vọng của test phải thay đổi theo hợp đồng mới.

### 3.2 Thiếu phần tử bắt buộc

```java
class MissingPath {
    @Route
    void serve() {}
}
```

`path()` không có giá trị mặc định. Compiler phải từ chối việc không cung cấp `path`, trong khi không cung cấp `retries` là hợp lệ.

### 3.3 Giá trị sai kiểu

```java
class WrongType {
    @Route(path = 42)
    void serve() {}
}
```

Số `42` không thể làm giá trị cho phần tử `String path()`. Không cần tạo validator nghiệp vụ để kiểm tra lỗi này.

### 3.4 Giá trị không phải hằng compile-time

```java
class NonConstantPath {
    static String runtimeValue = "/service";

    @Route(path = runtimeValue)
    void serve() {}
}
```

Dù `runtimeValue` có kiểu `String`, đây không phải constant variable; compiler phải từ chối. Trái lại, một biến `static final String` khởi tạo bằng constant expression phù hợp có thể được chấp nhận.

### 3.5 Annotation lặp không hợp lệ

```java
class Duplicated {
    @Route(path = "/a")
    @Route(path = "/b")
    void serve() {}
}
```

`Route` không được khai báo `@Repeatable`. Compiler phải từ chối hai annotation cùng loại trên một khai báo. Nếu thư viện hỗ trợ repeatable annotations, cần kiểm tra riêng container type và ngữ nghĩa nhiều giá trị.

### 3.6 Kiểu trả về của phần tử annotation không được phép

```java
@interface InvalidAnnotation {
    java.util.List<String> names();
}
```

`List<String>` không nằm trong các kiểu phần tử được ngôn ngữ Java hỗ trợ. Annotation elements chỉ dùng được những loại cho phép (kiểu nguyên thủy, `String`, `Class`, enum, annotation type và mảng một chiều của các loại phù hợp). Trường hợp này sai **ngay ở khai báo loại annotation**, trước cả lúc có nơi sử dụng.

## 4. Những mẫu cần processor riêng mới bị từ chối

Các ví dụ dưới đây đúng kiểu và đúng vị trí trong Java, nhưng **trái quy tắc nghiệp vụ**:

```java
class BusinessErrors {
    @Route(path = "orders")
    void noLeadingSlash() {}

    @Route(path = "/orders", retries = 4)
    void tooManyRetries() {}
}
```

Nếu chỉ chạy compiler mà không bật processor, hai method này về cơ bản vẫn hợp lệ với định nghĩa `Route`. Để bắt lỗi khi biên dịch, processor phải đọc metadata qua mô hình ngôn ngữ và phát `Diagnostic.Kind.ERROR`.

Trong ví dụ hoàn chỉnh:

- `ROUTE001`: `path` không bắt đầu bằng `/`.
- `ROUTE002`: `retries` không nằm trong đoạn `0..3`.

Processor nên dùng `Elements.getElementValuesWithDefaults(...)` để nhận giá trị hiệu lực của các phần tử, vì `retries` có thể bị bỏ qua ở nơi sử dụng nhưng vẫn có mặc định 1. `AnnotationMirror.getElementValues()` đơn thuần chỉ mô tả những cặp được khai báo tường minh, không đủ nếu rule cần đánh giá cả default.

`@Retention(SOURCE)` **không cản trở annotation processor**: nó đang phân tích source/Language Model trong khi biên dịch, không cần runtime Reflection.

## 5. Ma trận kiểm thử cần hiện thực

| Tên case | Mẫu kiểm thử | Kỳ vọng |
| --- | --- | --- |
| `valid-default` | `@Route(path="/ok")` trên method | ACCEPT |
| `valid-boundary` | `retries=3` | ACCEPT |
| `valid-constant` | `path` dùng `static final String` hằng | ACCEPT |
| `wrong-target` | `@Route` gắn trên field | REJECT bởi `javac` |
| `missing-required` | Thiếu `path` | REJECT bởi `javac` |
| `wrong-value-type` | `path=42` | REJECT bởi `javac` |
| `nonconstant` | `path` dùng biến không hằng | REJECT bởi `javac` |
| `not-repeatable` | Hai `@Route` trên cùng method | REJECT bởi `javac` |
| `processor-path` | `path="orders"` | REJECT bởi `ROUTE001` |
| `processor-retries` | `retries=4` | REJECT bởi `ROUTE002` |

Nhờ có case pass và fail, test có thể phát hiện cả **quá nghiêm** (từ chối mã hợp lệ) lẫn **quá lỏng** (nhận mã không hợp lệ).

Với miền `0..3`, bộ test sản phẩm còn nên bổ sung case `retries=0` là ACCEPT và `retries=-1` là REJECT để kiểm tra biên dưới; hai trường hợp ở bảng kiểm tra default và biên trên. Khi thay đổi chính sách, phải cập nhật test theo quy tắc công bố, không “sửa kỳ vọng cho xanh” mà bỏ qua lý do thay đổi.

## 6. Java 17+ chạy độc lập: test mã nguồn trong bộ nhớ bằng `JavaCompiler`

Chương trình dưới đây dùng **JDK JavaCompiler API** để thực sự biên dịch các fixture độc lập, đăng ký annotation processor tường minh, thu diagnostics và so kết quả với kỳ vọng.

Tạo tệp **`AnnotationCompileTests.java`**:

```java
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.stream.Stream;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.AnnotationMirror;
import javax.lang.model.element.Element;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class AnnotationCompileTests {
    private record Case(String name, String body, boolean accept) {}

    private static final String DECLARATIONS = """
            import java.lang.annotation.*;
            @Retention(RetentionPolicy.SOURCE)
            @Target(ElementType.METHOD)
            @interface Route {
                String path();
                int retries() default 1;
            }
            """;

    private static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source(String code) {
            super(URI.create("string:///Sample.java"), Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    public static final class RouteProcessor extends AbstractProcessor {
        @Override
        public Set<String> getSupportedAnnotationTypes() {
            return Set.of("Route");
        }

        @Override
        public SourceVersion getSupportedSourceVersion() {
            return SourceVersion.RELEASE_17;
        }

        @Override
        public boolean process(
                Set<? extends TypeElement> annotations,
                RoundEnvironment round) {
            if (round.processingOver()) {
                return true;
            }

            for (TypeElement routeType : annotations) {
                for (Element element :
                        round.getElementsAnnotatedWith(routeType)) {
                    for (AnnotationMirror mirror :
                            element.getAnnotationMirrors()) {
                        if (!mirror.getAnnotationType()
                                .asElement().equals(routeType)) {
                            continue;
                        }

                        String path = null;
                        Integer retries = null;
                        var values = processingEnv.getElementUtils()
                                .getElementValuesWithDefaults(mirror);

                        for (var entry : values.entrySet()) {
                            String name = entry.getKey()
                                    .getSimpleName().toString();
                            Object value = entry.getValue().getValue();
                            if ("path".equals(name)
                                    && value instanceof String s) {
                                path = s;
                            }
                            if ("retries".equals(name)
                                    && value instanceof Integer n) {
                                retries = n;
                            }
                        }

                        if (path == null || !path.startsWith("/")) {
                            processingEnv.getMessager().printMessage(
                                    Diagnostic.Kind.ERROR,
                                    "ROUTE001: path must start with /",
                                    element);
                        }
                        if (retries == null || retries < 0
                                || retries > 3) {
                            processingEnv.getMessager().printMessage(
                                    Diagnostic.Kind.ERROR,
                                    "ROUTE002: retries must be 0..3",
                                    element);
                        }
                    }
                }
            }
            return true;
        }
    }

    private static boolean compileCase(
            JavaCompiler compiler, Case test) throws IOException {
        Path output = Files.createTempDirectory("route-compile-");
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager files =
                     compiler.getStandardFileManager(
                             diagnostics, Locale.ROOT,
                             StandardCharsets.UTF_8)) {
            String sourceCode = DECLARATIONS + "\n" + test.body();
            JavaFileObject unit = new Source(sourceCode);

            List<String> options = List.of(
                    "--release", "17", "-encoding", "UTF-8",
                    "-d", output.toString());

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, files, diagnostics,
                    options, null, List.of(unit));
            task.setProcessors(List.of(new RouteProcessor()));

            boolean actual = Boolean.TRUE.equals(task.call());
            boolean passed = (actual == test.accept());
            System.out.println((passed ? "PASS " : "FAIL ")
                    + test.name() + " -> "
                    + (actual ? "ACCEPT" : "REJECT"));

            if (!passed) {
                for (Diagnostic<? extends JavaFileObject> diagnostic :
                        diagnostics.getDiagnostics()) {
                    if (diagnostic.getKind() == Diagnostic.Kind.ERROR) {
                        System.out.println("  ERROR: "
                                + diagnostic.getMessage(Locale.ROOT));
                    }
                }
            }
            return passed;
        } finally {
            try (Stream<Path> paths = Files.walk(output)) {
                for (Path path : paths.sorted(
                        Comparator.reverseOrder()).toList()) {
                    Files.deleteIfExists(path);
                }
            }
        }
    }

    public static void main(String[] args) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "JDK compiler is required");
        }

        List<Case> cases = List.of(
            new Case("valid-default",
                "class Sample { @Route(path=\"/ok\") void run() {} }",
                true),

            new Case("valid-boundary",
                "class Sample { @Route(path=\"/ok\", retries=3)"
                + " void run() {} }",
                true),

            new Case("valid-constant",
                "class Sample { static final String P=\"/ok\";"
                + " @Route(path=P) void run() {} }",
                true),

            new Case("wrong-target",
                "class Sample { @Route(path=\"/x\") String field; }",
                false),

            new Case("missing-required",
                "class Sample { @Route void run() {} }",
                false),

            new Case("wrong-value-type",
                "class Sample { @Route(path=42) void run() {} }",
                false),

            new Case("nonconstant",
                "class Sample { static String P=\"/x\";"
                + " @Route(path=P) void run() {} }",
                false),

            new Case("not-repeatable",
                "class Sample { @Route(path=\"/a\")"
                + " @Route(path=\"/b\") void run() {} }",
                false),

            new Case("processor-path",
                "class Sample { @Route(path=\"orders\") void run() {} }",
                false),

            new Case("processor-retries",
                "class Sample { @Route(path=\"/orders\", retries=4)"
                + " void run() {} }",
                false)
        );

        boolean allPassed = true;
        for (Case test : cases) {
            boolean passed = compileCase(compiler, test);
            allPassed &= passed;
        }

        System.out.println(allPassed
                ? "ALL TESTS PASSED" : "SOME TESTS FAILED");
        if (!allPassed) {
            throw new IllegalStateException("Compilation contract failed");
        }
    }
}
```

**Lệnh chạy** trong thư mục chứa file, cần **JDK 17 trở lên** và system Java compiler:

```bash
javac --release 17 -encoding UTF-8 AnnotationCompileTests.java
java AnnotationCompileTests
```

**Stdout khi toàn bộ bộ kiểm thử đạt:**

```text
PASS valid-default -> ACCEPT
PASS valid-boundary -> ACCEPT
PASS valid-constant -> ACCEPT
PASS wrong-target -> REJECT
PASS missing-required -> REJECT
PASS wrong-value-type -> REJECT
PASS nonconstant -> REJECT
PASS not-repeatable -> REJECT
PASS processor-path -> REJECT
PASS processor-retries -> REJECT
ALL TESTS PASSED
```

### Cách chương trình hoạt động

**`Source`** kế thừa `SimpleJavaFileObject` và chứa mã nguồn trong bộ nhớ. Mỗi fixture ghép định nghĩa `Route` vào một source mới, dùng URI giả `string:///Sample.java`. `JavaCompiler.getTask(...)` nhận source, lựa chọn `--release 17`, file manager và nơi nhận diagnostics.

**`task.setProcessors(List.of(new RouteProcessor()))`** là điểm cốt lõi: processor được bật rõ ràng. Nếu bỏ dòng này, các lỗi ngôn ngữ vẫn phải thất bại, nhưng `path="orders"` và `retries=4` có thể biên dịch thành công vì `javac` không biết rule nghiệp vụ.

**`RouteProcessor`** lấy annotation mirrors và đọc các phần tử bằng `getElementValuesWithDefaults`. Cách này thấy được cả `retries` do default 1, không chỉ những phần tử được viết trực tiếp. Processor phát `Diagnostic.Kind.ERROR` với mã `ROUTE001` hoặc `ROUTE002` khi giá trị vi phạm.

**`compileCase`** tạo thư mục output tạm **riêng cho mỗi fixture**, gọi compiler và so boolean thực tế với kỳ vọng. Sau đó dọn các file `.class` đã sinh qua `finally`. Các case không ảnh hưởng nhau bởi class cũ hay tên `Sample` trùng.

**`ALL TESTS PASSED`** chỉ xuất hiện khi mọi case có trạng thái ACCEPT/REJECT đúng như đã định. Chương trình không chạy phương thức `run()` của các fixture; nó đang **kiểm tra compiler**, không kiểm tra hành vi runtime.

Ví dụ đã được kiểm tra bằng compiler JDK với `--release 17`; ba positive cases được chấp nhận và bảy negative cases bị từ chối. Khi chạy trên JDK hoặc môi trường khác, nên kiểm tra thêm loại lỗi/diagnostic nếu kết quả sai để biết do compiler, processor hay cấu hình.

## 7. Cải tiến negative tests: từ chối phải **đúng nguyên nhân**

Bộ test trên tập trung vào tính đúng của trạng thái biên dịch. Nhưng sản phẩm thực tế cần thêm một bước để tránh **false positive**: một negative case thất bại vì thiếu classpath hoặc compiler bị lỗi không nên được coi là test thành công.

Với hai rule nghiệp vụ, kiểm tra **mã diagnostic**:

```java
// Trích đoạn mở rộng; dùng biến diagnostics ở compileCase.
boolean hasRoute001 = diagnostics.getDiagnostics().stream()
        .anyMatch(d ->
                d.getKind() == Diagnostic.Kind.ERROR
                && d.getMessage(Locale.ROOT).contains("ROUTE001:"));
```

Với case `processor-path`, kỳ vọng **biên dịch thất bại và có `ROUTE001`**. Case `processor-retries` phải có `ROUTE002`. Nếu compiler thất bại vì không tìm thấy loại `Route`, đây là lỗi setup/hạ tầng, không phải xác nhận validator đang hoạt động.

Với các lỗi thuộc ngôn ngữ, nên kiểm tra diagnostic liên quan đúng rule và tránh phụ thuộc hoàn toàn vào **chính xác từng chữ** của thông báo `javac`, vì message có thể khác giữa phiên bản JDK hoặc locale. Mỗi fixture chỉ nên cố ý vi phạm **một điều kiện nền tảng** để dễ phân tích.

Nếu dùng shell thay cho API, cần kiểm tra mã thoát:

- Bash: `$?` là exit code của lệnh trước đó.
- PowerShell: `$LASTEXITCODE` chứa exit code của lệnh native vừa chạy.

Không viết test theo kiểu “bắt mọi exception rồi coi là pass”; điều đó có thể che giấu compiler hoặc processor không được cấu hình đúng.

## 8. Kiểm thử biên, default, warning và mã được sinh

**Biên miền giá trị:** với `0..3`, nên có `0` và `3` hợp lệ, `-1` và `4` không hợp lệ. Test `retries` bỏ qua cần dùng mặc định `1`. Nếu default thay đổi, test phải phản ánh hợp đồng mới.

**Warning khác error:** `Diagnostic.Kind.WARNING` không nhất thiết làm compiler thất bại. Rule bắt buộc phải chặn build nên dùng `ERROR`; rule chỉ gợi ý nên dùng `WARNING` và kiểm tra warning tương ứng. `-Werror` có thể biến warning thành lỗi theo chính sách build, nhưng không được mặc định mọi môi trường đều bật `-Werror`.

**Annotation lặp:** nếu hỗ trợ `@Repeatable`, phải test container, nhiều annotation cùng loại, cách đọc trực tiếp/gián tiếp và thứ tự xử lý theo quy ước thư viện.

**Annotation ở mức type use:** `ElementType.TYPE_USE` cho phép marker nằm trong cây kiểu, ví dụ generic type argument. Không nên coi mọi type-use annotation là một declaration annotation được `RoundEnvironment.getElementsAnnotatedWith` trả ra như method/field; có thể cần kiểm tra `TypeMirror` hoặc AST phù hợp.

**Sinh mã bằng processor:** ngoài compile pass/fail, cần xác nhận resource/source được tạo bởi `Filer` đúng tên, đúng nội dung, không tạo trùng giữa các processing rounds và bản source sinh ra có thể biên dịch với `--release` mục tiêu.

**Runtime validation:** nếu annotation còn điều khiển framework tại runtime, hãy viết test runtime riêng. Compile-time acceptance không khẳng định registry, transaction, validation hay routing chạy đúng.

## 9. Thiết kế test suite đáng tin trong dự án

Một ma trận thực tế nên có các tiêu chí:

| Yếu tố | Yêu cầu |
| --- | --- |
| Tập fixture | Positive + negative cho từng rule, có case giá trị biên |
| Môi trường | Chốt JDK/compiler, release target, classpath, processor path |
| Đăng ký processor | Rõ ràng; không lệ thuộc discovery không được kiểm soát |
| Isolation | Source/output riêng, không vô tình dùng `.class` còn lại |
| Kỳ vọng | Trạng thái ACCEPT/REJECT, error kind, mã diagnostic nếu do processor |
| Khả năng tái lập | Không phụ thuộc thứ tự diagnostic hoặc văn bản lỗi không ổn định |
| Generated output | Kiểm tra file sinh và khả năng biên dịch nếu có code generation |
| Regression | Chạy lại trong CI khi sửa annotation type, processor hoặc nâng JDK |

Nên kiểm tra cấu hình **`@SupportedSourceVersion`** của processor khi nâng mức nguồn ứng dụng. Processor công bố `RELEASE_17` không tự bảo đảm hiểu mọi cú pháp được thêm ở bản mới; và `javac --release 17` mới là phần kiểm soát source/API/bytecode target, không phải annotation cấu hình của processor.

## 10. Lỗi thường gặp

1. **Chỉ test mã hợp lệ.** Không bắt được trường hợp processor bị vô hiệu hóa hoặc rule trở nên quá lỏng.
2. **Chấp nhận mọi lỗi compile làm positive cho negative test.** Có thể “đạt” giả vì dependency hoặc cấu hình thiếu.
3. **Nhầm compiler errors với business errors.** `path=42` sai kiểu Java; `path="orders"` sai policy do processor tự viết.
4. **Không bật processor trong test.** Những rule nghiệp vụ sẽ không được kiểm tra; test thiếu negative cases càng khó phát hiện.
5. **Không đọc giá trị mặc định.** `AnnotationMirror.getElementValues()` có thể bỏ qua `retries` nếu nơi dùng không ghi tường minh.
6. **Ghép mọi mã sai trong một tệp.** Lỗi trước có thể che mất lỗi sau; khó chứng minh case nào thực sự được kiểm thử.
7. **Dùng regex thay cho `javac`.** Không mô phỏng đầy đủ ngữ nghĩa kiểu, `@Target`, giá trị hằng và annotation processing.
8. **Quên các điểm biên.** Rule `0..3` dễ bị lỗi so sánh lớn-hơn/lớn-hơn-bằng.
9. **Coi compile success là runtime success.** Processor kiểm tra metadata nhưng không tự thực hiện hành vi ứng dụng.
10. **Chạy trên JDK mới mà không kiểm tra JDK tối thiểu.** `--release 17` hữu ích nhưng kiểm thử trên JDK 17 thật vẫn có giá trị cho ma trận hỗ trợ.

## 11. Bài tập tự kiểm tra

**Câu 1.** Vì sao `@Route(path=42)` phải thất bại kể cả khi không bật processor?

**Đáp án:** `path()` trả `String`, còn `42` có kiểu `int`; compiler tự kiểm tra kiểu của phần tử annotation.

**Câu 2.** `@Route(path="orders")` có nhất thiết bị `javac` từ chối nếu processor không chạy không?

**Đáp án:** Không. Giá trị đúng kiểu `String`; tiền tố `/` là business rule do processor tự viết.

**Câu 3.** Vì sao `@Route(path="/ok")` vẫn hợp lệ dù thiếu `retries`?

**Đáp án:** `retries()` có `default 1`, nên không bắt buộc được cung cấp tường minh.

**Câu 4.** Một negative fixture trả kết quả REJECT vì sai classpath. Test nên PASS không?

**Đáp án:** Không nên. Test cần xác minh nguyên nhân hợp đồng mong đợi, đặc biệt là mã lỗi processor như `ROUTE001`.

**Câu 5.** Vì sao `static final String P="/ok"` dùng được làm giá trị `path` nhưng `static String P="/ok"` thì không?

**Đáp án:** Trường hợp đầu là constant variable được khởi tạo bằng constant expression; trường hợp sau không phải hằng compile-time hợp lệ.

**Câu 6.** Trường hợp `retries=0` và `retries=3` kiểm tra điều gì?

**Đáp án:** Hai biên hợp lệ của miền `0..3`; giúp phát hiện lỗi off-by-one.

**Câu 7.** Khi dùng `JavaCompiler`, vì sao cần `task.setProcessors(...)`?

**Đáp án:** Để kích hoạt rõ ràng processor thực thi rule nghiệp vụ và tránh phụ thuộc vào cơ chế tìm processor theo môi trường.

**Câu 8.** Annotation có retention `SOURCE` có kiểm thử bằng annotation processor ở compile-time được không?

**Đáp án:** Có. Annotation processor đọc mô hình compiler khi source đang được xử lý, không cần Reflection runtime.

**Câu 9.** Nếu processor sinh thêm một class registry, chỉ kiểm tra `task.call()` trả true đã đủ chưa?

**Đáp án:** Chưa. Cần đối chiếu tên/nội dung artifact, kiểm tra khả năng biên dịch và tránh tạo file trùng giữa các round.

**Câu 10.** Khi chuyển từ `@Target(METHOD)` sang `@Target({METHOD, FIELD})`, negative test sai vị trí ở field có còn đúng không?

**Đáp án:** Không. Hợp đồng vị trí đã thay đổi; phải cập nhật test để phản ánh ý định mới hoặc xây thêm processor rule rõ ràng nếu nghiệp vụ vẫn cấm field.

## 12. Kết luận

Một bộ kiểm thử annotation tốt phải chứng minh **mã hợp lệ được chấp nhận**, **mã sai bị từ chối** và **sự từ chối có đúng nguyên nhân**. Hãy dùng `javac` để kiểm tra các ràng buộc ngôn ngữ, annotation processor cho quy tắc nghiệp vụ, `JavaCompiler` hoặc script build để tổ chức fixture độc lập, và thêm kiểm tra diagnostic, biên giá trị, giá trị mặc định, code generation/runtimes khi cần. Đây là nền tảng giúp thay đổi processor hoặc nâng JDK mà vẫn giữ vững hợp đồng annotation.
