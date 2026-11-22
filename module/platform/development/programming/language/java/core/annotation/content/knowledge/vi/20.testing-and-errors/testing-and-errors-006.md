# Kiểm thử annotation processor bằng JavaCompiler và tệp được sinh

## 1. Mục tiêu và phạm vi

Annotation processor là chương trình chạy **trong lúc biên dịch**, thường dựa trên API JSR 269 thuộc gói javax.annotation.processing. Nó có thể kiểm tra khai báo được đánh dấu annotation, phát sinh lỗi biên dịch, tạo mã nguồn mới thông qua Filer, hoặc tạo tệp tài nguyên. Kiểm thử processor vì thế khác kiểm thử một phương thức Java thông thường: phải khởi động một **lượt biên dịch thật**, chạy processor trong lượt đó và quan sát kết quả.

Sau bài này, bạn có thể:

- Chạy processor trực tiếp bằng javax.tools.JavaCompiler, không phụ thuộc vào IDE hay Gradle/Maven.
- Truyền một nguồn Java nhỏ vào compiler, kích hoạt chính xác processor cần thử bằng CompilationTask.setProcessors.
- Dùng đường dẫn riêng cho tệp nguồn phát sinh (SOURCE_OUTPUT) và lớp biên dịch (CLASS_OUTPUT).
- Khẳng định có tệp .java được sinh, nội dung của nó chính xác, lớp .class tương ứng biên dịch được và hành vi runtime đúng.
- Kiểm thử tình huống annotation được dùng sai: compilation trả về false, có Diagnostic.Kind.ERROR với thông điệp mong đợi và không phát sinh tệp không hợp lệ.
- Giải thích các lỗi phổ biến về nhiều processing round, FilerException, classpath, nguồn sinh nhưng chưa được biên dịch và dọn dẹp môi trường test.

Ví dụ chạy trên **JDK 17 trở lên**, sử dụng classpath (không sử dụng module-path) và không cần thư viện test ngoài JDK. Đây là một bài kiểm thử tích hợp nhỏ bằng phương thức main; trong dự án thực tế có thể chuyển các assertion sang JUnit.

## 2. Điều gì cần được kiểm chứng?

Đường đi điển hình của một lượt biên dịch có annotation processing:

1. Compiler phân tích mã nguồn đầu vào thành các phần tử ngôn ngữ (Element).
2. Processor được chọn nhận các annotation nó hỗ trợ, xử lý các phần tử trong một hoặc nhiều round.
3. Processor có thể dùng Messager để phát diagnostics, Filer.createSourceFile để sinh .java, hoặc Filer.createResource để sinh tài nguyên.
4. Mã nguồn mới thường được xem xét trong round kế tiếp. Khi biên dịch đầy đủ (không bật -proc:only), compiler tiếp tục biên dịch lớp từ mã nguồn đầu vào và nguồn được sinh.
5. JavaCompiler.CompilationTask.call trả về Boolean: true khi biên dịch thành công; lỗi do processor phát ra thường khiến kết quả là false.

Một bài test đáng tin cần kiểm tra **ba lớp bằng chứng khác nhau**:

| Lớp kiểm chứng | Quan sát | Vì sao cần |
| --- | --- | --- |
| Compilation | task.call() thành công hoặc thất bại như dự kiến; diagnostics đúng | Processor đã chạy trong compiler thực |
| Artifact | Tồn tại tệp .java/.class/tài nguyên ở đúng thư mục, nội dung đúng | Phát hiện lỗi tên, package, escape, đường dẫn và Filer |
| Behavior | Nạp lớp đã sinh và gọi phương thức của nó | Phát hiện mã sinh ra tuy có tệp nhưng không đúng hành vi |

Không nên chỉ tìm chuỗi trong một tệp .java: điều đó không chứng minh mã sinh biên dịch được. Ngược lại, chỉ khẳng định compilation thành công cũng chưa chắc processor thật sự được gọi; compiler có thể hoàn thành mà không chạy processor nếu cấu hình discovery sai.

## 3. Ví dụ processor cần kiểm thử

Ta xây dựng annotation @GenerateHello dùng cho kiểu, một processor sinh hai kết quả khi annotation đặt trên một class: lớp nguồn CustomerHello.java với message(), và tài nguyên META-INF/hello/Customer.txt. Nếu annotation được gắn vào interface, processor phát lỗi biên dịch. Bộ kiểm thử sẽ xác minh cả nhánh thành công và nhánh lỗi.

Cấu trúc tệp cần tạo:

~~~text
src/
├── demo/
│   ├── GenerateHello.java
│   └── HelloProcessor.java
└── ProcessorIntegrationTest.java
~~~

**src/demo/GenerateHello.java**

~~~java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.SOURCE)
public @interface GenerateHello {
}
~~~

RetentionPolicy.SOURCE đủ cho annotation chỉ phục vụ compiler. @Target(TYPE) cho phép annotation xuất hiện trên cả class lẫn interface; nhờ đó processor có thể tự báo lỗi cụ thể nếu gặp interface.

**src/demo/HelloProcessor.java**

~~~java
package demo;

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
import javax.tools.FileObject;
import javax.tools.JavaFileObject;
import javax.tools.StandardLocation;

@SupportedAnnotationTypes("demo.GenerateHello")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public final class HelloProcessor extends AbstractProcessor {

    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {

        if (roundEnv.processingOver()) {
            return true;
        }

        for (Element element :
                roundEnv.getElementsAnnotatedWith(GenerateHello.class)) {
            if (element.getKind() != ElementKind.CLASS) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "@GenerateHello chỉ áp dụng cho class",
                        element);
                continue;
            }

            String packageName = processingEnv.getElementUtils()
                    .getPackageOf(element).getQualifiedName().toString();
            String simpleName = element.getSimpleName().toString();
            String generatedSimpleName = simpleName + "Hello";
            String qualifiedName = packageName.isEmpty()
                    ? generatedSimpleName
                    : packageName + "." + generatedSimpleName;

            try {
                JavaFileObject source = processingEnv.getFiler()
                        .createSourceFile(qualifiedName, element);
                try (Writer writer = source.openWriter()) {
                    if (!packageName.isEmpty()) {
                        writer.write("package " + packageName + ";\n");
                    }
                    writer.write(
                            "public final class " + generatedSimpleName + " {\n");
                    writer.write(
                            "    private " + generatedSimpleName + "() {}\n");
                    writer.write(
                            "    public static String message() { return "
                            + "\"Hello, " + simpleName + "\"; }\n");
                    writer.write("}\n");
                }

                FileObject resource = processingEnv.getFiler().createResource(
                        StandardLocation.CLASS_OUTPUT,
                        "",
                        "META-INF/hello/" + simpleName + ".txt",
                        element);
                try (Writer writer = resource.openWriter()) {
                    writer.write("Hello, " + simpleName + "\n");
                }
            } catch (IOException error) {
                processingEnv.getMessager().printMessage(
                        Diagnostic.Kind.ERROR,
                        "Không tạo được tệp cho " + simpleName
                                + ": " + error.getMessage(),
                        element);
            }
        }
        return true;
    }
}
~~~

Các điểm quyết định:

- @SupportedAnnotationTypes khai báo tên đầy đủ của annotation; setProcessors ở bài test sẽ **chỉ định trực tiếp** instance processor nên không cần META-INF/services/javax.annotation.processing.Processor.
- Filer.createSourceFile sử dụng tên kiểu có package, không phải đường dẫn tệp tùy ý. Compiler/Filer quyết định chỗ lưu dựa vào SOURCE_OUTPUT.
- Filer.createResource(CLASS_OUTPUT, "", "META-INF/hello/Customer.txt", ...) sinh tài nguyên bên dưới thư mục chứa class; nó **không** tạo thêm round xử lý nguồn Java.
- originating element giúp công cụ build theo dõi quan hệ giữa phần tử đầu vào và đầu ra, hữu ích cho incremental build.
- Một tệp chỉ được tạo một lần trong mỗi lượt biên dịch. Processor chỉ duyệt những phần tử đang có annotation và không tạo lại CustomerHello khi xử lý round của mã nguồn được sinh; nếu cố tạo cùng tên lần hai sẽ nhận FilerException.
- Không được nuốt IOException hoặc trả về thành công trong khi không tạo được kết quả thiết yếu: ví dụ chuyển lỗi tạo tệp thành Diagnostic.Kind.ERROR.
- return true báo annotation này đã được processor xử lý; điều đó **không** có nghĩa toàn bộ compilation tự động thành công.

## 4. Harness tích hợp với javax.tools.JavaCompiler

Test tạo đơn vị nguồn Java **trong bộ nhớ**, nhưng yêu cầu compiler/Filer ghi kết quả thật xuống thư mục tạm. Mỗi case dùng thư mục classes và generated riêng để tránh artifact từ lần trước gây test xanh giả. DiagnosticCollector lấy thông báo của compiler và processor, trong khi StandardJavaFileManager quyết định nơi lưu các đầu ra.

**src/ProcessorIntegrationTest.java**

~~~java
import demo.HelloProcessor;
import java.io.IOException;
import java.net.URI;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.stream.Stream;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public final class ProcessorIntegrationTest {
    private record Outcome(
            boolean success,
            List<Diagnostic<? extends JavaFileObject>> diagnostics) {
    }

    private static final class Source extends SimpleJavaFileObject {
        private final String content;

        Source(String className, String content) {
            super(URI.create("string:///"
                    + className.replace('.', '/')
                    + JavaFileObject.Kind.SOURCE.extension),
                    JavaFileObject.Kind.SOURCE);
            this.content = content;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return content;
        }
    }

    private static Outcome compile(
            String className, String content, Path testDir)
            throws IOException {

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Cần chạy test bằng JDK 17+");
        }

        Path classes = Files.createDirectories(testDir.resolve("classes"));
        Path generated = Files.createDirectories(testDir.resolve("generated"));
        DiagnosticCollector<JavaFileObject> collector =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                compiler.getStandardFileManager(
                        collector, Locale.ROOT, StandardCharsets.UTF_8)) {

            manager.setLocationFromPaths(
                    StandardLocation.CLASS_OUTPUT, List.of(classes));
            manager.setLocationFromPaths(
                    StandardLocation.SOURCE_OUTPUT, List.of(generated));

            JavaFileObject input = new Source(className, content);
            List<String> options = List.of(
                    "--release", "17",
                    "-classpath", System.getProperty("java.class.path"),
                    "-encoding", "UTF-8");

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, manager, collector, options, null, List.of(input));
            task.setProcessors(List.of(new HelloProcessor()));

            boolean success = Boolean.TRUE.equals(task.call());
            return new Outcome(
                    success, List.copyOf(collector.getDiagnostics()));
        }
    }

    private static void require(boolean condition, String description) {
        if (!condition) {
            throw new AssertionError(description);
        }
    }

    private static String messages(Outcome result) {
        return String.join("\n", result.diagnostics().stream()
                .map(d -> d.getKind() + ": " + d.getMessage(Locale.ROOT))
                .toList());
    }

    private static void deleteTree(Path root) throws IOException {
        try (Stream<Path> paths = Files.walk(root)) {
            for (Path path :
                    paths.sorted(Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(path);
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path temp = Files.createTempDirectory("processor-test-");
        try {
            String valid = """
                    package demo;
                    @GenerateHello
                    public class Customer {}
                    """;
            Outcome good = compile(
                    "demo.Customer", valid, temp.resolve("valid"));
            require(good.success(), "Compilation lỗi:\n" + messages(good));

            Path source = temp.resolve(
                    "valid/generated/demo/CustomerHello.java");
            Path bytecode = temp.resolve(
                    "valid/classes/demo/CustomerHello.class");
            Path resource = temp.resolve(
                    "valid/classes/META-INF/hello/Customer.txt");

            require(Files.isRegularFile(source), "Thiếu .java được sinh");
            String expectedSource = """
                    package demo;
                    public final class CustomerHello {
                        private CustomerHello() {}
                        public static String message() { return "Hello, Customer"; }
                    }
                    """;
            require(expectedSource.equals(
                    Files.readString(source, StandardCharsets.UTF_8)),
                    "Nội dung nguồn sinh không khớp");
            System.out.println("PASS: generated .java");

            require(Files.isRegularFile(bytecode), "Thiếu .class được sinh");
            require(Files.isRegularFile(resource), "Thiếu resource");
            require("Hello, Customer\n".equals(
                    Files.readString(resource, StandardCharsets.UTF_8)),
                    "Resource sai nội dung");

            URL classesUrl = temp.resolve("valid/classes").toUri().toURL();
            try (URLClassLoader loader = new URLClassLoader(
                    new URL[] {classesUrl},
                    ClassLoader.getPlatformClassLoader())) {
                Class<?> type = Class.forName(
                        "demo.CustomerHello", true, loader);
                Object message = type.getMethod("message").invoke(null);
                require("Hello, Customer".equals(message),
                        "Lớp được sinh chạy sai");
            }
            System.out.println("PASS: generated .class, resource and runtime");

            String invalid = """
                    package demo;
                    @GenerateHello
                    public interface InvalidType {}
                    """;
            Outcome bad = compile(
                    "demo.InvalidType", invalid, temp.resolve("invalid"));
            require(!bad.success(),
                    "Interface không hợp lệ phải làm compilation thất bại");
            boolean hasExpectedError = bad.diagnostics().stream()
                    .anyMatch(d ->
                            d.getKind() == Diagnostic.Kind.ERROR
                            && d.getMessage(Locale.ROOT)
                                    .contains("@GenerateHello chỉ áp dụng cho class"));
            require(hasExpectedError,
                    "Thiếu diagnostic đúng:\n" + messages(bad));
            require(!Files.exists(temp.resolve(
                    "invalid/generated/demo/InvalidTypeHello.java")),
                    "Không được sinh nguồn cho interface không hợp lệ");
            System.out.println("PASS: negative diagnostics");
        } finally {
            deleteTree(temp);
        }
    }
}
~~~

### Ý nghĩa từng thao tác

**Source trong bộ nhớ:** SimpleJavaFileObject cung cấp tên URI phù hợp với className và trả về mã nguồn trong getCharContent. Như vậy kiểm thử không cần lưu Customer.java đầu vào xuống đĩa, nhưng compiler vẫn phân tích mã đó như một compilation unit Java.

**Lựa chọn processor:** task.setProcessors(List.of(new HelloProcessor())) kích hoạt đúng processor đang được kiểm thử. Điều này giảm phụ thuộc vào cơ chế tự tìm processor qua service registration hoặc biến động theo JDK. Nếu kiểm thử chính chức năng tự đăng ký processor, cần một bài test riêng dùng đường dẫn processor và service file, không gọi setProcessors.

**Classpath và đường dẫn output:** classpath lấy từ java.class.path của quá trình chạy test để compiler tìm được demo.GenerateHello; SOURCE_OUTPUT chứa mã sinh; CLASS_OUTPUT chứa .class và resource. Hai lượt compile thành công/thất bại có thư mục con khác nhau. Tùy dự án modular, có thể cần MODULE_PATH/PROCESSOR_PATH tương ứng, nhưng ví dụ này dùng classpath rõ ràng.

**Diagnostics:** DiagnosticCollector ghi loại thông báo (ERROR, WARNING...), nội dung và khi có sẵn cả nguồn, dòng/cột. Với nhánh lỗi, phải kiểm tra cả kết quả false lẫn thông báo chứa ý nghĩa cụ thể; nếu chỉ kiểm tra false thì một lỗi syntax/classpath không liên quan cũng làm test “đạt”.

**Artifact và hành vi:** Bài test so khớp toàn bộ CustomerHello.java, đọc resource bằng UTF-8, kiểm tra bytecode .class tồn tại, nạp lớp từ thư mục output qua URLClassLoader và gọi message() phản chiếu. Điều này chứng minh bước phát sinh và biên dịch hoàn chỉnh. Test đóng file manager/class loader và dọn thư mục tạm dù assertion thất bại.

## 5. Biên dịch và chạy bài test

Mở terminal tại thư mục chứa src rồi chạy:

~~~bash
javac -encoding UTF-8 --release 17 -d out src/demo/GenerateHello.java src/demo/HelloProcessor.java src/ProcessorIntegrationTest.java
java -cp out ProcessorIntegrationTest
~~~

Các lệnh hoạt động khi javac và java thuộc **JDK 17+** và thư mục hiện hành có đúng cấu trúc bên trên. Java 17 cung cấp records, text blocks, Stream.toList và API StandardJavaFileManager.setLocationFromPaths đã dùng ở ví dụ. Nếu đặt mã trong project Gradle/Maven, giữ processor class trên classpath của test hoặc cấu hình processor path cho vòng biên dịch.

Stdout khi mọi assertion đạt:

~~~text
PASS: generated .java
PASS: generated .class, resource and runtime
PASS: negative diagnostics
~~~

Không có dòng “PASS” tương ứng khi kiểm tra trước nó thất bại; chương trình sẽ ném AssertionError, in stack trace ra stderr và thoát khác 0. Lượt biên dịch interface là **âm tính có chủ đích**: JavaCompiler báo lỗi thông qua collector, harness kiểm tra lỗi thay vì in lỗi này ra stdout.

Để quan sát artifact thủ công, tạm bỏ khối finally/deleteTree hoặc đặt breakpoint trước khi dọn. Khi chạy bình thường, các đường dẫn nằm dưới thư mục tạm do Files.createTempDirectory tạo và sẽ được xóa sau test.

## 6. Lựa chọn khác: kiểm thử bằng javac trên dòng lệnh

Nếu có sẵn tệp đầu vào src/demo/Customer.java gồm nội dung dưới đây:

~~~java
package demo;

@GenerateHello
public class Customer {
}
~~~

Có thể chạy processor bằng javac CLI sau khi đã biên dịch demo.GenerateHello và demo.HelloProcessor vào thư mục out:

~~~bash
javac -cp out -processor demo.HelloProcessor -s generated -d classes src/demo/Customer.java
~~~

Chạy từ gốc dự án; tạo thư mục generated và classes trước nếu hệ thống/lệnh build yêu cầu. Tham số -s chỉ vị trí tệp nguồn Java được sinh; -d chỉ vị trí lớp đã biên dịch và resource CLASS_OUTPUT. Với biên dịch đầy đủ, lớp nguồn được sinh cũng được biên dịch. Tham số -processor xác định processor bằng tên đầy đủ, cho phép thử nhanh hành vi CLI; harness JavaCompiler ở trên phù hợp hơn để đặt assertion tự động và đọc diagnostics có cấu trúc.

Nếu chỉ muốn kiểm tra nguồn được sinh mà **không tạo class**, có thể chọn -proc:only khi gọi javac; khi ấy đừng kỳ vọng CustomerHello.class xuất hiện. Để kiểm tra bytecode và runtime như bài test trên, phải biên dịch đầy đủ.

## 7. Các tình huống lỗi cần bổ sung vào test suite thực tế

| Tình huống | Assertion nên có |
| --- | --- |
| Đầu vào hợp lệ | Compilation thành công; không có ERROR bất ngờ; tệp nguồn/resource đúng; .class có thể chạy |
| Annotation đặt sai kiểu | Compilation thất bại; ERROR trỏ tới phần tử sai; không sinh artifact hợp lệ giả |
| Thiếu classpath/annotation | Phân biệt lỗi “cannot find symbol” hoặc package không tồn tại với lỗi nghiệp vụ của processor |
| Tên lớp/package khác | Đường dẫn và package của lớp sinh khớp tên kiểu đầu vào; không cố định cứng demo.Customer |
| Hai class cùng tên đơn giản khác package | Tên nguồn được sinh theo tên đầy đủ, tránh đụng tệp |
| Nhiều phần tử annotated một lượt | Sinh đủ artifact cho từng phần tử; không sinh trùng giữa rounds |
| Biên dịch lại với output tồn tại | Dùng thư mục sạch để loại artifact cũ, hoặc chủ động kiểm chứng chiến lược incremental build |
| Processor báo warning/note | Assert đúng Kind, thông điệp và vị trí nếu chúng là một phần contract |
| Không ghi được output hoặc FilerException | Processor biến lỗi I/O thành ERROR, compilation không thành công |
| Processor chưa được đăng ký | Có test chuyên biệt xác minh cơ chế service discovery, ngoài test gọi setProcessors trực tiếp |

Khi kiểm tra diagnostics, ưu tiên Kind.ERROR, thông điệp nghiệp vụ ổn định và phần tử liên quan. Tránh snapshot toàn bộ text diagnostics do số dòng/cột, đường dẫn tạm, locale và wording của compiler có thể thay đổi giữa JDK. Ở ví dụ này, kiểm tra thông điệp do **chính processor** phát ra là ổn định.

Khi code được sinh phụ thuộc thứ tự duyệt phần tử, thời gian hiện tại hoặc đường dẫn tuyệt đối, snapshot tệp sẽ không ổn định. Hãy thiết kế processor tạo đầu ra xác định: sắp thứ tự phần tử nếu cần, dùng line ending và charset rõ ràng, không nhúng thời gian/ngẫu nhiên. Với các file lớn, có thể parse nội dung sinh ra hoặc so sánh AST và các thuộc tính cần thiết; với file nhỏ cố định ở ví dụ, exact text match là cách phù hợp.

## 8. Các bẫy thường gặp và cách xử lý

1. **Nhầm “có source” với “đã compile thành công”.** Filer tạo được .java không bảo đảm nó hợp lệ. Xác minh task.call() và tệp .class, tốt hơn nữa là nạp/chạy lớp.
2. **Không chạy processor thật.** Lệnh javac mặc định có thể không tìm thấy processor (đặc biệt khi thay đổi cấu hình build/JDK). Dùng setProcessors hoặc -processor rõ ràng; nếu thử auto-discovery, chuẩn bị service file và processor path tương ứng.
3. **Tạo lại cùng tệp trong nhiều round.** Filer chỉ cho phép tạo mới một lần mỗi lượt biên dịch. Không phát sinh khi processingOver(), xử lý tập phần tử phù hợp từng round và không gọi createSourceFile lặp lại cho cùng tên.
4. **Dùng vị trí output lẫn nhau.** SOURCE_OUTPUT cho mã nguồn sinh; CLASS_OUTPUT cho bytecode và tài nguyên runtime; CLASS_PATH/ANNOTATION_PROCESSOR_PATH có vai trò tìm lớp, không phải vị trí artifact.
5. **Chia sẻ output giữa test case.** Tệp cũ khiến Files.exists trả về true dù processor hiện tại không sinh gì. Tạo thư mục tạm mới cho từng case và dọn sau test.
6. **Bắt lỗi nhưng vẫn báo compile thành công.** Một exception không được báo qua Messager có thể làm mất bằng chứng nghiệp vụ. Với lỗi không thể phục hồi, phát Diagnostic.Kind.ERROR và xác minh task.call() trả false.
7. **So sánh diagnostics quá cứng.** Không ràng buộc toàn bộ stack trace, compiler location hoặc thông báo do compiler tạo nếu chỉ cần kiểm chứng error do processor.
8. **Đóng file manager quá sớm hoặc giữ file handle.** Chỉ đọc artifact sau task.call(), đóng StandardJavaFileManager và URLClassLoader; trên Windows cần đóng loader trước khi xóa cây thư mục tạm.
9. **Lẫn runtime test với compile-time test.** RetentionPolicy.SOURCE nghĩa là annotation không cần hiện diện ở runtime. Đối tượng runtime cần thử là lớp/tài nguyên sinh ra, không phải annotation gốc.
10. **Dùng -proc:only khi yêu cầu lớp .class.** -proc:only phục vụ annotation processing mà không biên dịch toàn bộ thành bytecode; hãy chạy compilation đầy đủ khi muốn assert .class hoặc hành vi.

## 9. Checklist nghiệm thu

- Bộ test tự tạo nguồn đầu vào hợp lệ và không hợp lệ; cả hai đều gọi JavaCompiler thực.
- Mỗi compilation xác định processor, classpath, SOURCE_OUTPUT và CLASS_OUTPUT.
- Case hợp lệ assert true, nội dung generated .java, generated .class, resource và hành vi thực.
- Case không hợp lệ assert false, có Diagnostic.Kind.ERROR đúng, không có generated source bất hợp lệ.
- Có xử lý round và lỗi Filer, không dựa vào tệp còn sót từ test trước.
- Mã minh họa biên dịch/chạy được bằng JDK 17+, stdout đã nêu là kết quả của đường đi thành công.

Cách kiểm thử này tạo một vòng chứng minh hoàn chỉnh: **nguồn đầu vào → processor trong compiler → diagnostics và artifact → bytecode/hành vi thực tế**. Nó giúp bắt lỗi sinh mã mà unit test gọi trực tiếp process() trên các mock Element thường bỏ sót.
