# Kiểm thử processor với mã sinh đúng và đầu vào không hợp lệ

## 1. Học được gì từ một phép kiểm thử biên dịch?

**Annotation processor** xử lý annotation trong lúc Java compiler chạy. Nó có thể sinh mã nguồn, tạo tài nguyên hoặc báo lỗi cho những khai báo vi phạm quy tắc. Kiểm thử processor phải kiểm chứng **cả lần biên dịch**, vì một lần gọi phương thức process thành công chưa bảo đảm source được sinh hợp lệ.

Hai tình huống cần chứng minh:

1. **Đầu vào hợp lệ:** compiler nạp processor; processor sinh đúng tên, package và nội dung; generated source compile được; API được sinh có hành vi đúng.
2. **Đầu vào không hợp lệ:** compiler thực sự chạy processor; processor báo lỗi đúng nguyên nhân, tại source liên quan; compilation thất bại; processor không tạo những file bị cấm.

Bài học dùng một annotation processor Java 17+ và một chương trình test bằng **Java Compiler API**. Ví dụ không yêu cầu JUnit hay thư viện bên ngoài nên có thể chạy với JDK 17 hoặc JDK 21. Đối với dự án thật, có thể chuyển các assertion sang JUnit hoặc một thư viện compile-testing nhưng vẫn giữ cùng hợp đồng.

## 2. Annotation processing có nhiều round

~~~text
Source Java ban đầu
       |
       v
javac phân tích và tìm annotation
       |
       v
Processor.process(annotations, roundEnv)
        |                           |
        |                           +-- Messager -> NOTE/WARNING/ERROR
        +-- Filer -> source/resource mới
       |
       v
Round tiếp theo nếu có source mới
       |
       v
Biên dịch source ban đầu + source mới
       |
       v
Diagnostics, trạng thái success/failure, .java, .class
~~~

| API | Vai trò |
| --- | --- |
| AbstractProcessor | Lớp cơ sở để khai báo annotation mà processor xử lý |
| ProcessingEnvironment | Cung cấp Messager, Filer và tiện ích mô hình kiểu |
| RoundEnvironment | Các element thuộc round hiện tại, trạng thái processingOver |
| Element / TypeElement | Mô hình semantic của khai báo Java |
| Filer | Tạo source/resource; ngăn tạo cùng file trùng trong một compilation |
| Messager | Phát diagnostic, có thể gắn vào phần tử source |
| JavaCompiler | Dựng compilation task thật |
| StandardJavaFileManager | Chuyển tệp source thành JavaFileObject và xử lý file manager |
| DiagnosticCollector | Thu ERROR, WARNING và các diagnostics khác |

**Giá trị true của process() không phải kết quả compilation.** True nghĩa là processor claim annotation; nếu processor đã in một Diagnostic.Kind.ERROR, toàn bộ compilation thường phải thất bại. Kết quả chính cần assert nằm ở **CompilationTask.call()**.

Không nên kiểm thử processor bằng cách parse text source bằng regex. Java compiler đã cung cấp mô hình element và annotation tương ứng, giúp processor hoạt động đúng cả khi cách viết source thay đổi.

## 3. Hợp đồng ví dụ: GenerateGreeting

Ta tạo annotation **@GenerateGreeting** áp dụng cho kiểu Java. Processor chỉ chấp nhận **class** và chuỗi không blank. Với class **sample.Good** mang @GenerateGreeting("Hello"), processor sinh **sample.GoodGreeting** có phương thức public static String message() trả về "Hello".

| Trường hợp | Input | Expected result |
| --- | --- | --- |
| Valid | @GenerateGreeting("Hello") trên class Good | Compile true, sinh GoodGreeting.java và GoodGreeting.class, message() trả Hello |
| Invalid value | @GenerateGreeting("   ") trên class Bad | Compile false, ERROR chứa GREETING_001, không sinh BadGreeting.java |
| Invalid element | @GenerateGreeting("Hello") trên interface WrongKind | Compile false, ERROR chứa GREETING_002, không sinh WrongKindGreeting.java |

Cần kiểm tra **nguyên nhân lỗi**, vì compilation false do thiếu annotation dependency hoặc processor không load được không phải bằng chứng processor đã từ chối input theo nghiệp vụ.

Cấu trúc ví dụ:

~~~text
processor-demo/
└── src/
    └── demo/
        ├── annotations/
        │   └── GenerateGreeting.java
        ├── processor/
        │   └── GreetingProcessor.java
        └── test/
            └── ProcessorCompilationTest.java
~~~

## 4. Viết annotation

Tệp **src/demo/annotations/GenerateGreeting.java**:

~~~java
package demo.annotations;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateGreeting {
    String value();
}
~~~

**RetentionPolicy.SOURCE** là đủ cho compile-time processing. **ElementType.TYPE** cho phép annotation xuất hiện trên interface, còn processor sẽ chủ động báo GREETING_002 vì business rule chỉ hỗ trợ class. Nếu dùng một @Target hẹp khiến compiler tự chặn trường hợp sai ngay lập tức, test không thể kỳ vọng diagnostic của processor như ở ví dụ này.

## 5. Viết processor

Tệp **src/demo/processor/GreetingProcessor.java**:

~~~java
package demo.processor;

import demo.annotations.GenerateGreeting;
import java.io.IOException;
import java.io.Writer;
import java.util.Set;
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.Element;
import javax.lang.model.element.ElementKind;
import javax.lang.model.element.TypeElement;
import javax.tools.Diagnostic;
import javax.tools.JavaFileObject;

@SupportedAnnotationTypes("demo.annotations.GenerateGreeting")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class GreetingProcessor extends AbstractProcessor {

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateGreeting.class)) {

            if (element.getKind() != ElementKind.CLASS) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "GREETING_002: @GenerateGreeting requires a class",
                        element);
                continue;
            }

            String message = element.getAnnotation(
                    GenerateGreeting.class).value();

            if (message.isBlank()) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "GREETING_001: message must not be blank",
                        element);
                continue;
            }

            TypeElement type = (TypeElement) element;
            String packageName = processingEnv.getElementUtils()
                    .getPackageOf(type)
                    .getQualifiedName()
                    .toString();
            String generatedName = type.getSimpleName() + "Greeting";
            String qualifiedName = packageName.isEmpty()
                    ? generatedName
                    : packageName + "." + generatedName;

            try {
                JavaFileObject generated = processingEnv.getFiler()
                        .createSourceFile(qualifiedName, element);

                try (Writer writer = generated.openWriter()) {
                    if (!packageName.isEmpty()) {
                        writer.write("package " + packageName + ";\n");
                    }
                    writer.write("public final class "
                            + generatedName + " {\n");
                    writer.write("  private " + generatedName + "() {}\n");
                    writer.write("  public static String message() {\n");
                    writer.write("    return \"" + escape(message) + "\";\n");
                    writer.write("  }\n}\n");
                }
            } catch (IOException ex) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "GREETING_003: cannot generate "
                                + qualifiedName + ": " + ex.getMessage(),
                        element);
            }
        }

        return true;
    }

    private static String escape(String value) {
        return value.replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "\\r")
                .replace("\t", "\\t");
    }
}
~~~

**Điểm kỹ thuật cần chú ý:**

- @SupportedAnnotationTypes dùng fully qualified annotation name; @SupportedSourceVersion(RELEASE_17) khai báo release mà processor của ví dụ hỗ trợ.
- Processor đọc **getElementsAnnotatedWith** qua compiler model, tránh lệ thuộc source formatting.
- Kiểm tra element kind và giá trị **isBlank()** diễn ra trước Filer. Input không hợp lệ sẽ chỉ nhận diagnostic và không sinh file tương ứng.
- **Messager.printMessage(ERROR, ..., element)** gắn lỗi với element, giúp compiler và test có source location. Đây là cách báo lỗi nghiệp vụ phù hợp hơn việc throw RuntimeException.
- Filer nhận fully qualified generated type và originating element. Originating element hữu ích cho hệ thống build nhưng không tự đảm bảo mọi incremental processing hợp lệ.
- Hàm escape xử lý một số ký tự Java string phổ biến; processor production nên xử lý thêm control characters/Unicode và các trường hợp tên class/package xung đột.
- File được tạo trong round đầu xuất hiện ở round tiếp theo. Vì generated class không mang @GenerateGreeting, đoạn này không tự lặp generation trong các round kế tiếp.
- Processor trả true nghĩa là claim annotation, không có nghĩa compilation có kết quả true.

Một processor lớn cần tự kiểm soát việc tạo trùng cùng fully qualified name. **FilerException** có thể xuất hiện khi cùng file bị tạo lại; nuốt lỗi mà không ghi diagnostic sẽ che nguyên nhân.

## 6. Java Compiler API test harness

Tạo **src/demo/test/ProcessorCompilationTest.java**:

~~~java
package demo.test;

import java.io.IOException;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.Locale;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class ProcessorCompilationTest {

    private ProcessorCompilationTest() {
    }

    private record Compilation(
            boolean success,
            Path classes,
            Path generated,
            List<Diagnostic<? extends JavaFileObject>> diagnostics) {
    }

    public static void main(String[] args) throws Exception {
        testValidSource();
        testBlankMessage();
        testWrongElementKind();
    }

    private static void testValidSource() throws Exception {
        Compilation result = compile("Good", """
                package sample;
                import demo.annotations.GenerateGreeting;

                @GenerateGreeting("Hello")
                public class Good {
                    public static void main(String[] args) {
                        System.out.println(GoodGreeting.message());
                    }
                }
                """);

        check(result.success(), "Valid source must compile");
        check(Files.exists(result.generated()
                .resolve("sample/GoodGreeting.java")),
                "Generated .java is missing");
        check(Files.exists(result.classes()
                .resolve("sample/GoodGreeting.class")),
                "Generated .class is missing");

        try (URLClassLoader loader = new URLClassLoader(
                new URL[] {result.classes().toUri().toURL()},
                ProcessorCompilationTest.class.getClassLoader())) {
            Class<?> generated = loader.loadClass("sample.GoodGreeting");
            String actual = (String) generated.getMethod("message")
                    .invoke(null);
            check("Hello".equals(actual),
                    "Generated method returned: " + actual);
        }

        System.out.println(
                "PASS valid: sample.GoodGreeting.message() = Hello");
    }

    private static void testBlankMessage() throws Exception {
        Compilation result = compile("Bad", """
                package sample;
                import demo.annotations.GenerateGreeting;

                @GenerateGreeting("   ")
                public class Bad {
                }
                """);

        check(!result.success(),
                "Blank message must fail compilation");
        check(hasError(result, "GREETING_001", "Bad.java"),
                "Missing GREETING_001 diagnostic on Bad.java");
        check(!Files.exists(result.generated()
                .resolve("sample/BadGreeting.java")),
                "Invalid input unexpectedly generated source");

        System.out.println(
                "PASS invalid value: GREETING_001 and compile failed");
    }

    private static void testWrongElementKind() throws Exception {
        Compilation result = compile("WrongKind", """
                package sample;
                import demo.annotations.GenerateGreeting;

                @GenerateGreeting("Hello")
                public interface WrongKind {
                }
                """);

        check(!result.success(),
                "Annotated interface must fail compilation");
        check(hasError(result, "GREETING_002", "WrongKind.java"),
                "Missing GREETING_002 diagnostic");
        check(!Files.exists(result.generated()
                .resolve("sample/WrongKindGreeting.java")),
                "Invalid kind unexpectedly generated source");

        System.out.println(
                "PASS invalid kind: GREETING_002 and compile failed");
    }

    private static Compilation compile(String name, String source)
            throws IOException {

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "Run tests using a JDK, not a runtime without javac");
        }

        Path root = Files.createTempDirectory("processor-" + name + "-");
        Path sourceFile = root.resolve("src/sample/" + name + ".java");
        Path classes = root.resolve("classes");
        Path generated = root.resolve("generated");
        Files.createDirectories(sourceFile.getParent());
        Files.createDirectories(classes);
        Files.createDirectories(generated);
        Files.writeString(sourceFile, source, StandardCharsets.UTF_8);

        DiagnosticCollector<JavaFileObject> collector =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                     compiler.getStandardFileManager(
                             collector, Locale.ROOT,
                             StandardCharsets.UTF_8)) {

            Iterable<? extends JavaFileObject> units =
                    manager.getJavaFileObjects(sourceFile.toFile());

            String toolClasspath = System.getProperty("java.class.path");

            List<String> options = List.of(
                    "--release", "17",
                    "-encoding", "UTF-8",
                    "-classpath", toolClasspath,
                    "-processorpath", toolClasspath,
                    "-processor", "demo.processor.GreetingProcessor",
                    "-d", classes.toString(),
                    "-s", generated.toString());

            Boolean successful = compiler.getTask(
                    null, manager, collector, options, null, units)
                    .call();

            return new Compilation(
                    Boolean.TRUE.equals(successful),
                    classes,
                    generated,
                    List.copyOf(collector.getDiagnostics()));
        }
    }

    private static boolean hasError(
            Compilation result, String code, String filename) {

        return result.diagnostics().stream().anyMatch(d ->
                d.getKind() == Diagnostic.Kind.ERROR
                        && d.getMessage(Locale.ROOT).contains(code)
                        && d.getSource() != null
                        && d.getSource().getName().endsWith(filename));
    }

    private static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }
}
~~~

### 6.1. Chính xác test này kiểm chứng điều gì?

**Positive** gồm ba tầng: compilation true; generated .java và .class tồn tại ở đường dẫn đúng; reflection nạp generated class rồi gọi phương thức và kiểm tra giá trị Hello. Nếu source sinh ra có lỗi cú pháp, compilation false; nếu phương thức sai, reflection hoặc assertion fail. Điều này mạnh hơn chỉ khẳng định một source file đã được ghi.

**Negative** gồm compilation false, diagnostic **Kind.ERROR** có mã nghiệp vụ và source file đúng, và không có generated source bị cấm. Một ERROR do thiếu classpath/annotation **không được tính** là processor validation hoạt động đúng.

**DiagnosticCollector** lưu lỗi compiler/processor để test đọc chính xác; không nên đòi thứ tự hoặc toàn văn diagnostics cố định giữa JDK/locale. **Locale.ROOT** làm message rendering ít phụ thuộc locale của runner.

### 6.2. Vì sao classpath và processor path đều cần?

Trong ví dụ, chương trình test chạy với classpath chứa annotation API và processor. JavaCompiler sử dụng:

- **-classpath:** đưa annotation API vào quá trình compile source test.
- **-processorpath:** compiler tìm được processor binary và các dependency của processor.
- **-processor:** chọn chính xác processor, không lệ thuộc discovery.
- **-d:** thư mục chứa class biên dịch.
- **-s:** thư mục generated Java source.
- **--release 17:** chốt ngôn ngữ, bytecode và Java platform API theo release 17.

Sử dụng một toolClasspath duy nhất chỉ để demo độc lập. Trong dự án thực, classpath source và processor path thường chứa những tập dependency khác nhau.

### 6.3. Cách ly output để tránh false positive

Hàm compile() tạo thư mục tạm mới cho **mỗi** case, trong đó source, classes và generated tách biệt. Nếu tái sử dụng một output directory chung, BadGreeting.java cũ có thể khiến test negative sai, và GoodGreeting.class cũ có thể khiến positive pass dù processor không còn sinh gì.

Temporary files được giữ lại để tiện điều tra. Với JUnit hoặc framework production, có thể dùng cơ chế quản lý temp directory của test và dọn artifacts sau khi không cần thiết.

## 7. Biên dịch và chạy đúng ví dụ

Đặt terminal tại thư mục **processor-demo** với đúng ba file source ở trên.

**Linux/macOS:**

~~~bash
mkdir -p out/tools
javac --release 17 -encoding UTF-8 -d out/tools \
  src/demo/annotations/GenerateGreeting.java \
  src/demo/processor/GreetingProcessor.java \
  src/demo/test/ProcessorCompilationTest.java
java -cp out/tools demo.test.ProcessorCompilationTest
~~~

**Windows PowerShell** (lệnh javac viết một dòng để có thể copy nguyên văn):

~~~powershell
New-Item -ItemType Directory -Force out/tools | Out-Null
javac --release 17 -encoding UTF-8 -d out/tools src/demo/annotations/GenerateGreeting.java src/demo/processor/GreetingProcessor.java src/demo/test/ProcessorCompilationTest.java
java -cp out/tools demo.test.ProcessorCompilationTest
~~~

**Stdout chính xác của chương trình test khi cả ba case đạt:**

~~~text
PASS valid: sample.GoodGreeting.message() = Hello
PASS invalid value: GREETING_001 and compile failed
PASS invalid kind: GREETING_002 and compile failed
~~~

Lệnh javac compile bộ source công cụ khi thành công không bắt buộc có stdout. Nếu một assertion fail, chương trình test ném AssertionError và kết thúc không thành công.

Trong thư mục tạm của case Good, compiler tạo:

~~~text
generated/sample/GoodGreeting.java
classes/sample/GoodGreeting.class
~~~

Source được sinh có nội dung tương đương:

~~~java
package sample;
public final class GoodGreeting {
  private GoodGreeting() {}
  public static String message() {
    return "Hello";
  }
}
~~~

Test không chỉ xem file GoodGreeting.java mà còn kiểm tra class và giá trị được trả về. Khi hợp đồng yêu cầu formatting chính xác, có thể thêm golden-file assertion; nếu chỉ kiểm tra API và hành vi, compile + invocation giúp test ít brittle hơn trước thay đổi whitespace.

## 8. Tái hiện thủ công qua javac

Để đối chiếu compiler invocation trong trường hợp test API fail, tạo thêm file **samples/Good.java**:

~~~java
package sample;

import demo.annotations.GenerateGreeting;

@GenerateGreeting("Hello")
public class Good {
    public static void main(String[] args) {
        System.out.println(GoodGreeting.message());
    }
}
~~~

Sau khi đã compile annotation và processor thành out/tools, Linux/macOS có thể chạy:

~~~bash
mkdir -p out/manual-classes out/manual-generated
javac --release 17 -encoding UTF-8 \
  -classpath out/tools \
  -processorpath out/tools \
  -processor demo.processor.GreetingProcessor \
  -d out/manual-classes \
  -s out/manual-generated \
  samples/Good.java
java -cp out/manual-classes:out/tools sample.Good
~~~

**Stdout:** 

~~~text
Hello
~~~

File samples/Good.java là bài tập thủ công bổ sung, **không nằm trong ba file tối thiểu** của test harness; phải tạo nó trước khi chạy lệnh. Trên Windows, classpath Java ngăn cách entries bằng dấu **;** thay cho dấu **:** và cách nối dòng terminal cũng khác.

Với test negative thủ công, biên dịch một source Bad.java có @GenerateGreeting("   ") trong output directory khác. Kiểm tra javac exit code khác 0 **và** có mã GREETING_001. Chỉ thấy exit code lỗi có thể do thiếu dependency hoặc chọn sai processor.

Chế độ **-proc:only** hữu ích để xem các tệp do annotation processing sinh ra, nhưng không thay thế positive test compilation đầy đủ vì chưa chứng minh generated Java tạo được .class hợp lệ.

## 9. Các ca biên đáng kiểm thử

| Nhóm | Input/test | Điều cần assert |
| --- | --- | --- |
| Cơ bản | Một class hợp lệ | Generated class và source đúng, compilation success |
| Nhiều input | Hai class hợp lệ trong cùng compilation | Đủ cả hai output, không sinh thừa |
| Giá trị biên | Rỗng, chỉ whitespace | ERROR đúng code và không generate |
| Escape | Dấu nháy, backslash, newline, Unicode | Generated source vẫn compile; runtime giữ đúng nội dung |
| Element kind | Interface/enum/record theo contract | ERROR đúng hoặc compiler validation tương ứng |
| Duplicate | Hai khai báo đòi cùng generated name | Lỗi có giải thích, không overwrite |
| Processing rounds | Source mới chứa annotation xử lý tiếp | Không lặp vô hạn, không generate trùng |
| Không annotation | Source bình thường | Success, không sinh output ngoài ý muốn |
| Warning | Input không lý tưởng nhưng vẫn hợp lệ | WARNING, compile status đúng chính sách |
| Incremental | Thay đổi source giữa nhiều build | Output mới, không dùng file/cache cũ |

Không nhất thiết mọi processor phải sinh .java. Processor chỉ validation nên tập trung diagnostics; processor tạo resource thì kiểm tra tài nguyên output; processor generate type thì kiểm tra package, chữ ký, khả năng compile và hành vi.

### Processing round và trùng file

Filer có thể ném FilerException khi một tên nguồn được tạo hai lần trong cùng compilation. Nếu source generated lại được gắn annotation dẫn tới round kế tiếp, processor cần tránh tạo vô hạn hoặc ghi trùng tên. Một test nên đưa nhiều annotated element vào **cùng một compilation**, không chỉ chạy hai lần riêng rẽ, để phát hiện bug mapping tên output.

Đặc biệt, true của process() chỉ claim annotation; không dùng nó để suy ra rằng Filer write, diagnostics và compilation đã thành công.

## 10. Phân biệt lỗi processor và lỗi của test setup

| Triệu chứng | Khả năng chính | Cần xác minh |
| --- | --- | --- |
| getSystemJavaCompiler() trả null | Runtime thiếu compiler | Chạy từ JDK đầy đủ |
| Processor not found | Sai processor path/FQCN | -processorpath, -processor, binary JAR |
| package demo.annotations does not exist | Thiếu annotation trên compile classpath | -classpath |
| Compilation false nhưng không có GREETING_001 | Fail vì lỗi compiler khác | Xem diagnostics chi tiết |
| Generated .java tồn tại, .class thiếu | Java sinh sai hoặc -proc:only | Status, diagnostic, mode |
| FilerException | Trùng fully qualified name | Mapping tên, round, file owner |
| Test chỉ pass sau test khác | Shared state hoặc output | Tách directories và classloaders |
| CI khác máy cá nhân | JDK/toolchain, encoding, path, dependencies | Log compiler và resolved classpath |

Để xem lỗi, có thể bổ sung **phương thức sau vào class ProcessorCompilationTest**:

~~~java
private static void printDiagnostics(Compilation result) {
    for (Diagnostic<? extends JavaFileObject> d
            : result.diagnostics()) {
        System.err.printf("%s %s:%d %s%n",
                d.getKind(),
                d.getSource() == null
                        ? "<unknown>"
                        : d.getSource().getName(),
                d.getLineNumber(),
                d.getMessage(Locale.ROOT));
    }
}
~~~

Đây là snippet bổ sung vào class, không phải chương trình độc lập. Diagnostic có thể không có source, khi đó getSource() == null và line number có thể là -1. Không dùng việc in diagnostics thay cho assertion.

## 11. Đưa test vào build tool và CI

**Gradle:** Trong dự án có module annotations và processor riêng, phần tiêu thụ annotation thường cần dependency tách biệt:

~~~groovy
dependencies {
    compileOnly project(':annotations')
    annotationProcessor project(':processor')
}
~~~

Đoạn này chỉ là cấu hình minh họa nếu các module được nêu thực sự tồn tại. Module processor còn cần phụ thuộc annotation API để biên dịch processor. Không mặc định một JAR nằm trên implementation sẽ được nạp như annotation processor.

**Maven:** Kiểm tra phiên bản maven-compiler-plugin, cấu hình processor/annotationProcessorPaths ở phiên bản hỗ trợ, release, toolchain và active profile. Cơ chế discovery có thể thay đổi theo JDK và plugin; lựa chọn processor tường minh giúp test dễ tái hiện.

**CI:** Một job phù hợp cần compile processor, chạy harness và trả nonzero exit nếu assertion lỗi. Ghim JDK/toolchain, giữ source/dependencies nhất quán, không để cache hoặc task skip che việc processor có chạy hay không. Khi fail, thu compiler version, diagnostics và artifacts tạm cần thiết sau khi lọc dữ liệu nhạy cảm.

**Test âm thành công nghĩa là test harness đã chứng minh compilation con thất bại đúng lý do.** Không được cấu hình CI bỏ qua mọi compilation error với kỳ vọng mọi negative case đều là pass.

## 12. Nguyên tắc kết luận và checklist

- [ ] Compiler thật có mặt và processor được nạp bằng cấu hình đúng.
- [ ] Annotation dependency và processor dependency nằm trên path tương ứng.
- [ ] Test dương kiểm tra compilation success, generated source, generated class và API/hành vi.
- [ ] Test âm kiểm tra compilation failure **đúng nguyên nhân**, có Kind.ERROR, mã lỗi, source và không có output bị cấm.
- [ ] Các case độc lập về source files, class output, generated output và classloader.
- [ ] Case nhiều element, nhiều processing round và duplicate generated name đã được cân nhắc.
- [ ] Không phụ thuộc thứ tự/định dạng exact của diagnostics do javac phát.
- [ ] JDK, Java release, encoding và kết quả stdout được đối chiếu đúng.
- [ ] CI không vô tình nuốt lỗi compile hoặc dùng lại artifacts cũ.

Các unit test của hàm escape/naming vẫn có giá trị, nhưng không thể thay kiểm thử compilation thật. Một processor có thể sinh source hợp lệ về mặt string mà vẫn thất bại khi javac compile do thiếu module, generic type hoặc API không đúng Java release.

## Tài liệu tham khảo

- [Java SE 17 Annotation Processing API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/annotation/processing/package-summary.html)
- [Java SE 17 JavaCompiler API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html)
- [Java SE 17 DiagnosticCollector](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/DiagnosticCollector.html)
- [Java SE 17 javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html)
- [JSR 269 Pluggable Annotation Processing API](https://jcp.org/en/jsr/detail?id=269)

Một bộ test processor đáng tin cậy phải chứng minh **mã sinh từ input hợp lệ compile và hoạt động đúng**, còn **input không hợp lệ làm compilation thất bại đúng lý do, không tạo artifacts bị cấm**.