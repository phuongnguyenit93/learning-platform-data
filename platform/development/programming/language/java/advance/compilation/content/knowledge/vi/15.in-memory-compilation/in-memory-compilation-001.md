# Mô hình JavaFileObject và URI của một đơn vị nguồn khi biên dịch trong bộ nhớ

Trong Java Compiler API, mã nguồn không bắt buộc nằm trong một tệp `.java` trên đĩa. Trình biên dịch có thể đọc một `String` thông qua đối tượng triển khai `JavaFileObject`. Đối tượng đó có **URI làm danh tính logic**, **Kind để biết loại tệp**, và các phương thức cung cấp nội dung. Đây là nền tảng của trình biên dịch nhúng trong IDE, REPL, công cụ sinh mã hoặc dịch vụ kiểm tra source.

Bài thuộc chủ đề **Biên dịch trong bộ nhớ** của Java Advance – compilation. Trọng tâm là phân biệt tên nhị phân của một lớp, URI của compilation unit, nội dung text nguồn, cơ chế tìm/ghi của JavaFileManager và đầu ra bytecode. Ví dụ dùng API có trong Java 17, đã chạy với `javac --release 17`; phần khác biệt từ các JDK mới được ghi riêng.

## 1. JavaFileObject là mô hình tệp Java, không đồng nghĩa tệp thật

`javax.tools.JavaFileObject` kế thừa `javax.tools.FileObject`. Chúng biểu diễn những đối tượng mà công cụ biên dịch có thể đọc hoặc ghi, dù dữ liệu thực nằm trong RAM, hệ thống tệp, JAR hoặc nguồn lưu trữ khác.

Các thành phần quan trọng:

| API | Vai trò |
|---|---|
| `toUri()` | Trả URI xác định file object |
| `getName()` | Tên hiển thị cho người dùng, chẩn đoán hoặc công cụ |
| `getKind()` | Phân loại đơn vị SOURCE, CLASS, HTML, OTHER |
| `getCharContent(boolean)` | Đọc nội dung ký tự của file object |
| `openReader(boolean)` | Mở Reader nếu implementation hỗ trợ |
| `openInputStream()` | Mở dòng đọc bytes khi được hỗ trợ |
| `openOutputStream()` | Mở dòng ghi bytes, thường dùng cho đầu ra class |
| `openWriter()` | Ghi ký tự khi file object hỗ trợ |
| `isNameCompatible(simpleName, kind)` | Đối chiếu tên đơn và Kind |
| `getLastModified()`, `delete()` | Metadata/thao tác bổ trợ tùy implementation |

`JavaFileObject.Kind` gồm `SOURCE` (extension `.java`), `CLASS` (`.class`), `HTML` (`.html`), và `OTHER` (không có extension mặc định).

Một file object cho nguồn Java chứa **ký tự text** và dùng `Kind.SOURCE`. Một file object cho bytecode đầu ra chứa **bytes nhị phân** và dùng `Kind.CLASS`. Không đọc `.class` bằng cách tùy tiện giải mã thành String; cũng không gắn Kind.CLASS cho một nguồn chỉ vì compiler sắp sinh class từ nguồn đó.

### 1.1. Compilation unit không đồng nghĩa một class output

Một `JavaFileObject` nguồn biểu diễn **một đơn vị biên dịch**. Một file Java có thể chứa một public top-level class, các kiểu package-private và nested classes. Vì thế một nguồn có thể sinh **nhiều** file `.class`:

~~~java
package demo;

public class Hello {
    static class Nested {}
}

class Helper {}
~~~

Với một nguồn như trên, compiler có thể sinh `demo/Hello.class`, `demo/Hello$Nested.class` và `demo/Helper.class`. File manager đầu ra trong RAM phải lưu riêng mỗi class. Đừng giả định một source luôn tương ứng đúng một class.

## 2. URI của nguồn: danh tính logic thay cho đường dẫn vật lý

URI là viết tắt của Uniform Resource Identifier. API `FileObject.toUri()` không bắt buộc dùng scheme `file:`. Các ví dụ minh họa:

~~~text
file:///home/reader/project/src/demo/Hello.java
string:///demo/Hello.java
mem:///demo/Hello.class
jar:file:///opt/libs/example.jar!/demo/Hello.class
~~~

Trong đó:

- `file:` có thể biểu diễn file thật trên filesystem.
- `jar:` có thể biểu diễn entry trong một JAR.
- `string:` là **scheme tự đặt** để định danh nguồn chứa trong String.
- `mem:` là **scheme tự đặt** cho đầu ra nằm trong RAM.

Không có giao thức mạng hay filesystem chuẩn tự động xử lý `string:` và `mem:` trong ví dụ. URI là **tên**, còn nội dung do implementation của JavaFileObject cung cấp. Khi viết `string:///demo/Hello.java`, không có file `Hello.java` thật nào tự xuất hiện trên đĩa.

### 2.1. Vì sao thường dùng string:///?

~~~java
URI uri = URI.create("string:///demo/Hello.java");
~~~

URI này có scheme `string`, path `/demo/Hello.java` và không có authority. Dùng path giống cấu trúc package để file object và compiler có một quy ước nhất quán. Đừng chuyển URI `string:` thành `Path` rồi giả định `Files.readString` sẽ hoạt động; không có filesystem provider mặc định tương ứng.

### 2.2. Tên lớp, tên tệp và URI là ba khái niệm

Với source:

~~~java
package demo;
public class Hello {}
~~~

| Khái niệm | Giá trị |
|---|---|
| Binary name | `demo.Hello` |
| Simple class name | `Hello` |
| URI của source trong ví dụ | `string:///demo/Hello.java` |
| URI của bytecode trong ví dụ | `mem:///demo/Hello.class` |

Có thể dựng URI từ binary name:

~~~java
String binaryName = "demo.Hello";
URI sourceUri = URI.create(
    "string:///" + binaryName.replace('.', '/')
    + JavaFileObject.Kind.SOURCE.extension
);
~~~

Đầu ra có URI `string:///demo/Hello.java`. Ví dụ giả định binary name là tên Java hợp lệ. Trong ứng dụng nhận dữ liệu ngoài, phải **kiểm tra tên class/package** trước khi nối chuỗi URI và mã hóa ký tự URI nếu cần. Binary name khác với tên mà editor hiển thị, và khác với nội dung nguồn thực tế.

### 2.3. Ý nghĩa của isNameCompatible

`SimpleJavaFileObject.isNameCompatible` kiểm tra Kind và path URI có tương thích với simple name yêu cầu hay không. Nếu URI kết thúc bằng `/Hello.java` và Kind là SOURCE:

~~~java
source.isNameCompatible("Hello", JavaFileObject.Kind.SOURCE); // true
source.isNameCompatible("Other", JavaFileObject.Kind.SOURCE); // false
~~~

Đây là đoạn minh họa với biến `source` đã được tạo. Quy ước tên đặc biệt quan trọng với **public top-level class**: source khai báo `public class Hello` nhưng được đặt tên logic là `Wrong.java` có thể bị compiler từ chối, tương tự quy tắc tên file Java thông thường.

## 3. Tạo JavaFileObject từ String bằng SimpleJavaFileObject

`javax.tools.SimpleJavaFileObject` được thiết kế để subclass. Constructor chính:

~~~java
protected SimpleJavaFileObject(URI uri, JavaFileObject.Kind kind)
~~~

Ví dụ một source object chỉ đọc:

~~~java
import java.net.URI;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;

final class StringSource extends SimpleJavaFileObject {
    private final String content;

    StringSource(String binaryName, String content) {
        super(URI.create("string:///"
                + binaryName.replace('.', '/')
                + JavaFileObject.Kind.SOURCE.extension),
              JavaFileObject.Kind.SOURCE);
        this.content = content;
    }

    @Override
    public CharSequence getCharContent(boolean ignoreEncodingErrors) {
        return content;
    }
}
~~~

Đây là một **class thành phần**, chưa phải chương trình standalone. Chương trình hoàn chỉnh có main ở phần 7.

Điểm quan trọng:

1. `super(uri, SOURCE)` cung cấp danh tính và loại đơn vị nguồn.
2. `getCharContent` trả source text đã có trong String.
3. Compiler có thể phân tích source dù không có file vật lý.
4. Mặc định `SimpleJavaFileObject.getCharContent` ném `UnsupportedOperationException`; nếu không override thì source ảo không cung cấp được nội dung theo cách này.
5. Tham số `ignoreEncodingErrors` liên quan đọc/giải mã bytes; với String có sẵn ký tự, implementation trên không cần giải mã bytes nên trả thẳng content.

Nguồn trong RAM không tự làm mọi đầu ra cũng ở RAM. Nếu dùng file manager mặc định, compiler vẫn có thể ghi bytecode ra ổ đĩa. Cần cấu hình **cả đường nhận nguồn và đường ghi kết quả**.

## 4. JavaCompiler và JavaFileManager phối hợp ra sao?

Các thành phần chính của package `javax.tools`:

- `ToolProvider.getSystemJavaCompiler()`: lấy Java compiler của môi trường JDK; có thể trả null nếu runtime không cung cấp compiler.
- `JavaCompiler.getTask(...)`: tạo tác vụ biên dịch, nhận options, file manager, diagnostics, classes/processors và danh sách compilation units.
- `JavaCompiler.CompilationTask.call()`: thực hiện biên dịch, thường trả Boolean.
- `StandardJavaFileManager`: file manager tiêu chuẩn, xử lý file, classpath, module path và các vị trí chuẩn.
- `ForwardingJavaFileManager`: bọc manager khác và chỉ override thao tác cần tùy biến.
- `DiagnosticCollector<JavaFileObject>`: thu lỗi/cảnh báo với thông tin nguồn, vị trí và mức độ.
- `JavaFileObject`: đơn vị đầu vào/đầu ra ở cấp compiler.

Luồng cơ bản:

~~~text
String chứa source
        |
        v
StringSource: Kind.SOURCE, URI string:///demo/Hello.java
        |
        v
JavaCompiler.getTask(..., sources)
        |
        v
parse -> resolve -> type check -> generate
        |
        v
JavaFileManager.getJavaFileForOutput(...)
        |
        v
BytecodeOutput: Kind.CLASS, URI mem:///demo/Hello.class
        |
        v
byte[] trong RAM -> ClassLoader -> thực thi
~~~

Khi chỉ muốn source trong RAM nhưng output trên đĩa, có thể sử dụng StandardJavaFileManager cùng `-d out`. Khi muốn **source và class output cùng ở RAM**, file manager cần trả một object nhận bytes khi compiler yêu cầu đầu ra.

### 4.1. getJavaFileForOutput

Chữ ký quan trọng:

~~~java
JavaFileObject getJavaFileForOutput(
    JavaFileManager.Location location,
    String className,
    JavaFileObject.Kind kind,
    FileObject sibling
) throws IOException;
~~~

- `location`: vị trí logic, chẳng hạn CLASS_OUTPUT trong task xuất class.
- `className`: binary name của class mà compiler đang tạo.
- `kind`: thường CLASS khi tạo `.class`.
- `sibling`: gợi ý về nguồn gốc/đối tượng liên quan; không mặc định là file path thật.

File manager có thể trả JavaFileObject với `openOutputStream()` ghi vào ByteArrayOutputStream. Nếu có nhiều class output, mỗi class phải có một buffer riêng. `ForwardingJavaFileManager` cho phép các thao tác tiêu chuẩn không được override vẫn do standard manager xử lý.

## 5. Biên dịch trong RAM khác với nạp class trong RAM

**Compile-time:** JavaCompiler tìm source, symbol và dependencies thông qua JavaFileObject và JavaFileManager. Nó tạo bytecode.

**Runtime:** JVM/ClassLoader tìm hoặc định nghĩa class từ bytecode phù hợp. ClassLoader không tự tham gia biên dịch nguồn trong JavaCompiler.

Trong ví dụ ở phần 7, map output lưu `String binaryName -> BytecodeOutput`. Một ClassLoader riêng lấy byte[] từ map và gọi `defineClass`. Điều này chứng minh cả source lẫn bytecode tạo động có thể ở RAM, nhưng **ClassLoader không phải sandbox bảo mật** và không thay thế compiler classpath.

Nếu sau khi compile class A, bạn tạo một **compiler task thứ hai** để biên dịch B phụ thuộc A, chỉ có map bytes từ task đầu không đủ. File manager cần giúp compiler tìm class A (hoặc bạn xuất nó ra một location tiêu chuẩn). Với nhiều nguồn phụ thuộc nhau, biên dịch **cùng một task** thường đơn giản hơn.

## 6. SourceObject và ClassOutputObject có quyền truy cập khác nhau

Source object thường chỉ cần cung cấp:

~~~java
@Override
public CharSequence getCharContent(boolean ignoreEncodingErrors) {
    return content;
}
~~~

Class output object thường cung cấp:

~~~java
@Override
public OutputStream openOutputStream() {
    return output;
}
~~~

`output` là ByteArrayOutputStream riêng của object. Không dùng `getCharContent` để đọc class file thành String vì bytecode là dữ liệu nhị phân.

Một URI dạng `mem:///demo/Hello.class` không có nghĩa là `new URL(...).openStream()` tự đọc được bytes từ map. Cần **file manager/class loader cụ thể** có khả năng đọc dữ liệu. URI tự thân chỉ định danh đối tượng.

## 7. Chương trình đầy đủ Java 17: String source đến bytecode trong RAM

Tạo file **InMemoryCompilationDemo.java** đúng tên, không có khai báo package. Mã dưới đây là chương trình hoàn chỉnh, đã biên dịch và chạy với `javac --release 17` trên JDK 24.0.2.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class InMemoryCompilationDemo {
    static final class StringSource extends SimpleJavaFileObject {
        private final String content;

        StringSource(String binaryName, String content) {
            super(URI.create("string:///" + binaryName.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.content = content;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return content;
        }
    }

    static final class BytecodeOutput extends SimpleJavaFileObject {
        private final ByteArrayOutputStream output =
                new ByteArrayOutputStream();

        BytecodeOutput(String binaryName, Kind kind) {
            super(URI.create("mem:///" + binaryName.replace('.', '/')
                    + kind.extension), kind);
        }

        @Override
        public OutputStream openOutputStream() {
            return output;
        }

        byte[] bytes() {
            return output.toByteArray();
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler required");
        }

        StringSource source = new StringSource(
                "demo.Hello",
                "package demo; public class Hello { "
                + "public static String message() { return \"Xin chào\"; } }");

        Map<String, BytecodeOutput> outputClasses = new HashMap<>();
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager standard =
                    compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT, StandardCharsets.UTF_8);
             JavaFileManager files =
                    new ForwardingJavaFileManager<StandardJavaFileManager>(
                            standard) {
                        @Override
                        public JavaFileObject getJavaFileForOutput(
                                Location location, String className,
                                JavaFileObject.Kind kind, FileObject sibling) {
                            BytecodeOutput output =
                                    new BytecodeOutput(className, kind);
                            outputClasses.put(className, output);
                            return output;
                        }
                    }) {

            Boolean succeeded = compiler.getTask(
                    null, files, diagnostics,
                    List.of("--release", "17", "-encoding", "UTF-8"),
                    null, List.of(source)).call();

            System.out.println("sourceURI=" + source.toUri());
            System.out.println("kind=" + source.getKind());
            System.out.println("compatible=" + source.isNameCompatible(
                    "Hello", JavaFileObject.Kind.SOURCE));
            System.out.println("compiled=" + succeeded);

            if (!Boolean.TRUE.equals(succeeded)) {
                for (Diagnostic<? extends JavaFileObject> d
                        : diagnostics.getDiagnostics()) {
                    System.out.println(
                        d.getKind() + " " + d.getMessage(Locale.ROOT));
                }
                return;
            }
        }

        ClassLoader loader = new ClassLoader(
                InMemoryCompilationDemo.class.getClassLoader()) {
            @Override
            protected Class<?> findClass(String name)
                    throws ClassNotFoundException {
                BytecodeOutput output = outputClasses.get(name);
                if (output == null) {
                    throw new ClassNotFoundException(name);
                }
                byte[] bytes = output.bytes();
                return defineClass(name, bytes, 0, bytes.length);
            }
        };

        Class<?> generated = Class.forName("demo.Hello", true, loader);
        System.out.println(
            "classURI=" + outputClasses.get("demo.Hello").toUri());
        System.out.println(
            "message=" + generated.getMethod("message").invoke(null));
        System.out.println("classCount=" + outputClasses.size());
    }
}
~~~

Biên dịch chương trình điều phối và chạy:

~~~sh
javac --release 17 -encoding UTF-8 InMemoryCompilationDemo.java
java InMemoryCompilationDemo
~~~

**Stdout chính xác đã kiểm chứng:**

~~~text
sourceURI=string:///demo/Hello.java
kind=SOURCE
compatible=true
compiled=true
classURI=mem:///demo/Hello.class
message=Xin chào
classCount=1
~~~

### 7.1. Giải thích từng kết quả

- `sourceURI`: JavaFileObject nguồn có URI logic, không có file `demo/Hello.java` vật lý.
- `kind=SOURCE`: compiler nhận diện đối tượng là nguồn.
- `compatible=true`: tên Hello và Kind.SOURCE khớp path URI.
- `compiled=true`: tác vụ JavaCompiler đã hoàn tất thành công.
- `classURI`: BytecodeOutput cho class có URI mem ảo.
- `message=Xin chào`: class loader đã định nghĩa class từ byte[] lưu trong RAM và phương thức được gọi thành công.
- `classCount=1`: đơn vị nguồn cụ thể này chỉ tạo một class.

Lệnh javac ngoài cùng tạo **InMemoryCompilationDemo.class** trên đĩa, nhưng task nội bộ tạo **demo.Hello** trong RAM. Hai tầng biên dịch không nên bị lẫn. Khi chạy task nội bộ, chúng ta không gọi command shell javac lần nữa; JavaCompiler chạy trong tiến trình JVM của công cụ điều phối.

### 7.2. Cách thử thay đổi nội dung nguồn

Đổi chuỗi source để phương thức message trả `"Hello RAM"`, biên dịch và chạy lại chương trình điều phối. URI có thể giữ nguyên vì binary name vẫn là demo.Hello; nội dung được StringSource cung cấp đã thay đổi. Nếu ứng dụng thực tế cần version hóa nhiều lượt edit, nên lưu revision kèm URI để diagnostics map đúng phiên bản source.

Nếu source chứa nhiều class hoặc nested class, outputClasses có thể chứa nhiều entry. Đừng cố lưu tất cả class vào cùng một ByteArrayOutputStream.

## 8. DiagnosticCollector sử dụng URI để gắn lỗi vào nguồn ảo

Tạo **DiagnosticDemo.java**:

~~~java
import java.net.URI;
import java.util.List;
import javax.tools.*;

public class DiagnosticDemo {
    static class Source extends SimpleJavaFileObject {
        Source() {
            super(URI.create("string:///demo/Broken.java"), Kind.SOURCE);
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return "package demo;\n"
                + "public class Broken {\n"
                + " int n = \"bad\";\n"
                + "}\n";
        }
    }

    public static void main(String[] args) {
        JavaCompiler javac = ToolProvider.getSystemJavaCompiler();
        DiagnosticCollector<JavaFileObject> report =
                new DiagnosticCollector<>();

        boolean ok = javac.getTask(
                null, null, report,
                List.of("--release", "17"),
                null, List.of(new Source())).call();

        System.out.println("success=" + ok);
        for (Diagnostic<? extends JavaFileObject> d
                : report.getDiagnostics()) {
            if (d.getKind() == Diagnostic.Kind.ERROR) {
                System.out.println("uri=" + d.getSource().toUri());
                System.out.println("line=" + d.getLineNumber());
                System.out.println("column=" + d.getColumnNumber());
                System.out.println("kind=" + d.getKind());
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~sh
javac --release 17 -encoding UTF-8 DiagnosticDemo.java
java DiagnosticDemo
~~~

**Stdout chính xác đã kiểm chứng:**

~~~text
success=false
uri=string:///demo/Broken.java
line=3
column=10
kind=ERROR
~~~

Không có file Broken.java trên đĩa: compiler nhận source text từ getCharContent và diagnostic trả URI do chúng ta chỉ định.

Trong code tổng quát, hãy kiểm tra `d.getSource() != null` trước khi lấy URI; những diagnostic toàn cục có thể không có nguồn hoặc vị trí, và line/column có thể mang `Diagnostic.NOPOS`. Giá trị line/column tương ứng với text **đúng phiên bản compiler đã đọc**. Khi editor sửa source liên tục, cần kết nối URI với revision để không highlight nhầm.

DiagnosticDemo dùng file manager mặc định vì nó minh họa một lượt **biên dịch thất bại**. Để đảm bảo các lượt thành công không tạo class trên ổ đĩa, cần custom file manager như InMemoryCompilationDemo.

## 9. Biên dịch nhiều JavaFileObject trong cùng task

`JavaCompiler.getTask` nhận một Iterable các `JavaFileObject`. Một task có thể chứa nhiều đơn vị nguồn và giúp compiler xử lý tham chiếu qua lại.

Ví dụ đặt trong chương trình đã định nghĩa StringSource:

~~~java
JavaFileObject library = new StringSource(
    "demo.Library",
    "package demo; public class Library { "
    + "public static int answer() { return 42; } }"
);

JavaFileObject main = new StringSource(
    "demo.Main",
    "package demo; public class Main { "
    + "public static void main(String[] args) { "
    + "System.out.println(Library.answer()); } }"
);

List<JavaFileObject> units = List.of(library, main);
~~~

Truyền `units` vào getTask thay cho `List.of(source)`. Đoạn trên không tự chạy vì còn cần compiler task, file manager và imports; nó là một phần mở rộng cho chương trình đầy đủ.

Lợi ích: compiler cùng nhìn thấy Library và Main, không cần ngay lập tức xây dựng cơ chế đọc class bytes từ task trước. Với task kế tiếp độc lập, nếu muốn dùng class bytes trong bộ nhớ làm dependency cần triển khai file manager để trả những class files đó khi compiler tìm.

### 9.1. Các phương thức cần cân nhắc cho file manager nâng cao

Trong hệ thống biên dịch nhiều lượt, ngoài getJavaFileForOutput có thể cần:

- `getJavaFileForInput`: trả class/source input theo location, binary name và Kind.
- `list`: cho compiler liệt kê file object trong package theo Kind.
- `inferBinaryName`: chuyển một file object do manager quản lý thành binary name đúng.
- `hasLocation` và cấu hình location: đảm bảo compiler biết nơi cần tìm.
- `getFileForOutput`: xử lý resources không chỉ là class, có thể do annotation processor tạo.
- Quản lý source/class output cho nhiều task, module path và classpath theo yêu cầu.

Chỉ override getJavaFileForOutput **không** tạo ra đầy đủ một classpath in-memory. Thiết kế cần dựa trên hợp đồng JavaFileManager, không dựa vào suy luận rằng compiler tự nhìn thấy mọi map bytecode.

## 10. URI đúng nhưng compiler vẫn có thể báo lỗi

Một URI hợp lệ **không bảo đảm mã hợp lệ**. Compiler vẫn áp dụng Java Language Specification:

- Package và public class phải nhất quán với đơn vị nguồn.
- Kiểu, tên biến/phương thức, access modifiers, generics phải đúng.
- Nếu source import thư viện ngoài, compiler phải tìm được dependency qua classpath/module path.
- Nếu có nhiều nguồn cùng binary name, có thể phát sinh lỗi trùng class.
- Nếu output object không hỗ trợ thao tác ghi mà compiler dùng, tác vụ có thể lỗi I/O.

Ví dụ: StringSource có URI string:///demo/Hello.java và code `package demo; public class Hello...` là nhất quán. Nhưng nội dung `package other; public class Hello...` sẽ không phù hợp kỳ vọng từ URI và lookup nếu hệ thống file manager tổ chức source theo demo.Hello. Hãy thiết kế tên binary, source package và URI cùng một quy ước, thay vì chỉ cố làm URI parse được.

### 10.1. Tên URI có được trùng không?

Trong cùng tập compilation units, hãy chọn URI khác nhau cho các nguồn khác nhau. URI trùng khiến việc nhận diện source, cache hoặc diagnostics có thể trở nên mơ hồ. Với editor có nhiều file cùng tên Hello.java ở các package khác nhau, URI cần phản ánh đường package hoặc một định danh hợp lệ khác.

### 10.2. Khi tên đến từ người dùng

Không ghép thẳng dữ liệu tùy ý vào đường URI. Kiểm tra Java identifier, package components, tránh traversal hoặc ký tự làm thay đổi cấu trúc URI; dùng URI constructors/escaping phù hợp nếu cần. Tên hiển thị cho editor có thể khác binary name mà compiler sử dụng.

## 11. Phiên bản Java: API nào có từ JDK 17?

Các interface và class cốt lõi `JavaCompiler`, `JavaFileObject`, `SimpleJavaFileObject`, `StandardJavaFileManager`, `ForwardingJavaFileManager` và `ToolProvider` được hỗ trợ ở Java 17. Ví dụ chính dùng các API này, nên không cần Java 23.

**Từ JDK 23**, `SimpleJavaFileObject.forSource(URI, String)` giúp tạo source object trực tiếp mà không viết subclass:

~~~java
JavaFileObject source = SimpleJavaFileObject.forSource(
    URI.create("string:///demo/Hello.java"),
    "package demo; public class Hello {}"
);
~~~

Đoạn trên chỉ dành cho **JDK 23 trở lên**. Không viết nó vào project bắt buộc biên dịch với `--release 17`, vì Java 17 chưa có factory method này.

Trong InMemoryCompilationDemo, options truyền vào **task bên trong** là:

~~~java
List.of("--release", "17", "-encoding", "UTF-8")
~~~

Cờ này yêu cầu JavaCompiler nhắm Java 17; nó không tự thay đổi phiên bản runtime đang chạy công cụ điều phối. Nếu compiler JDK không hỗ trợ release đó, task sẽ lỗi. Muốn kiểm tra cần xem `javac -version`, `java -version` và options thực tế của tool.

## 12. Những lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh/sửa |
|---|---|---|
| getSystemJavaCompiler trả null | Runtime không cung cấp compiler | Chạy bằng JDK có jdk.compiler hoặc toolchain phù hợp |
| UnsupportedOperationException khi đọc source | SimpleJavaFileObject chưa override getCharContent | Cung cấp getCharContent hoặc cách đọc text phù hợp |
| public class phải ở Hello.java | URI/name không khớp simple name | Dùng URI kết thúc /Hello.java với SOURCE |
| package does not exist | Thiếu nguồn hoặc dependency cần compile | Truyền đủ units, cấu hình classpath/module path |
| Bytecode xuất hiện trên đĩa | Output vẫn do standard manager ghi | Chặn getJavaFileForOutput và trả BytecodeOutput |
| Đã compile nhưng không load được class | Runtime loader không có bytes đúng binary name | Giữ map tất cả outputs, kiểm tra loader |
| Task thứ hai không thấy class từ task trước | Map RAM chưa được expose như compiler input | Bổ sung list/getJavaFileForInput/inferBinaryName hoặc compile chung task |
| Chỉ có một output dù source có nested classes | File manager ghi đè cùng một buffer | Tạo BytecodeOutput riêng theo className |
| Diagnostic URI không có source đúng | Định danh trùng hoặc map text/revision sai | Gắn URI với đúng đơn vị nguồn và revision |
| URI string: không đọc được bằng Files | Đây là scheme logic, không phải filesystem path | Đọc từ JavaFileObject/custom file manager |
| Tưởng ClassLoader là sandbox | Class được định nghĩa vẫn chạy trong JVM | Không thực thi code chưa tin cậy trong tiến trình có quyền cao |
| Cache bytes/loader làm tăng RAM | Giữ map và references quá lâu | Xác định vòng đời, xóa cache và đặt quota |

## 13. Thiết kế an toàn cho compiler nhúng

Nếu xây dựng dịch vụ nhận source từ editor hoặc request bên ngoài, hãy phân biệt **biên dịch** và **thực thi**.

1. Giới hạn số nguồn, kích thước source và mức sử dụng CPU/RAM.
2. Validate binary names và URI; tránh nhầm người dùng với filename tùy ý.
3. Cố định danh sách compiler options và dependency được tin cậy.
4. Cân nhắc annotation processors: chúng là **mã chạy trong quá trình build**, không chỉ metadata.
5. Không đưa secrets vào diagnostic logs hoặc source không được tin cậy.
6. Không gọi code được compile từ người dùng trong cùng JVM có quyền truy cập hệ thống nếu chưa có sandbox/process isolation phù hợp.
7. Quản lý vòng đời JavaFileManager, ClassLoader và bytecode cache.
8. Gắn diagnostic với đúng source URI, line/column và revision.
9. Chạy kiểm thử trên target JDK và classpath/module path thực tế.
10. Tách runtime loader với compile-time file manager và kiểm tra dependency ở cả hai phía.

ClassLoader riêng **không phải** ranh giới bảo mật; nó giúp định nghĩa và tìm class, nhưng code vẫn có thể sử dụng các API với quyền của tiến trình JVM. Trong ứng dụng có mã không tin cậy, cần cô lập tiến trình/container, quyền và tài nguyên phù hợp.

## 14. Bài tập thực hành

**Bài 1:** Từ binary name `edu.lesson.Parser`, dựng URI SOURCE và CLASS. Đáp án gợi ý: `string:///edu/lesson/Parser.java` và `mem:///edu/lesson/Parser.class`.

**Bài 2:** Với URI `string:///demo/Hello.java`, thử isNameCompatible với Hello/SOURCE, Other/SOURCE và Hello/CLASS. Giải thích kết quả dựa trên path và Kind.

**Bài 3:** Cho StringSource chứa hai top-level classes và nested class. Dự đoán số lượng class output, sau đó quan sát map BytecodeOutput. Vì sao một nguồn có thể sinh nhiều class?

**Bài 4:** Thêm một nguồn demo.Library và một nguồn demo.Main tham chiếu Library, truyền cả hai vào một getTask. So sánh khi chỉ truyền Main mà không có dependency.

**Bài 5:** Đổi nội dung của DiagnosticDemo thành lỗi ở dòng khác, kiểm tra Diagnostic.getSource().toUri(), line và column. Vì sao lỗi vẫn gắn được vào source dù không có tệp thật?

**Bài 6:** So sánh source URI và class URI trong stdout InMemoryCompilationDemo. Tại sao scheme mem: không giúp Class.forName tự tìm class nếu thiếu ClassLoader?

**Bài 7:** Đánh giá việc chuyển từ compile một task sang nhiều task; liệt kê những API của JavaFileManager cần bổ sung để tái sử dụng class output RAM.

**Bài 8:** Khi project cần Java 17, giải thích vì sao sử dụng subclass SimpleJavaFileObject có thể chạy được, còn SimpleJavaFileObject.forSource chỉ phù hợp khi target JDK 23+.

## 15. Checklist cuối bài

- [ ] Phân biệt binary name, URI, Kind và source text.
- [ ] SOURCE object có URI hợp lệ, Kind.SOURCE và cách đọc ký tự.
- [ ] Public class, package và URI được đặt nhất quán.
- [ ] Compiler task nhận các JavaFileObject cần thiết và đủ dependency.
- [ ] Class output được file manager ghi đúng nơi: RAM hoặc filesystem.
- [ ] Bytecode CLASS là bytes, không phải String.
- [ ] Nhiều class outputs được giữ riêng, kể cả nested/helper classes.
- [ ] DiagnosticCollector map URI và vị trí về đúng source.
- [ ] ClassLoader nhìn thấy bytecode và runtime dependencies.
- [ ] Phiên bản Java/API phù hợp mức --release.
- [ ] Có giới hạn tài nguyên và không coi ClassLoader là sandbox bảo mật.

**Kết luận:** JavaFileObject là **đối tượng tệp logic ở cấp compiler**; URI là danh tính của đối tượng, không phải bảo đảm có file trên ổ đĩa. Khi một Kind.SOURCE cung cấp text qua getCharContent và JavaFileManager xử lý đầu ra, compiler có thể biên dịch một chuỗi Java thành các Kind.CLASS trong RAM. Ranh giới giữa danh tính, nội dung, lookup, output và class loading chính là chìa khóa để triển khai công cụ biên dịch trong bộ nhớ đúng và có thể mở rộng.

## 16. Tài liệu chính thức

- Java SE 17, JavaFileObject: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaFileObject.html
- Java SE 17, SimpleJavaFileObject: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html
- Java SE 17, JavaCompiler: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
- Java SE 17, JavaFileManager: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaFileManager.html
- Java SE 17, ForwardingJavaFileManager: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html
- Java SE 24, SimpleJavaFileObject và factory forSource: https://docs.oracle.com/en/java/javase/24/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html
- JSR 199 — Java Compiler API: https://jcp.org/en/jsr/detail?id=199
