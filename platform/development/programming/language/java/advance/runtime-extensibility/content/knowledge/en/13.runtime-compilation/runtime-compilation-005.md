# Tạo CompilationTask bằng getTask và đọc kết quả call

## 1. Tình huống sử dụng: biên dịch Java ngay khi ứng dụng đang chạy

Một ứng dụng Java đôi khi cần nhận mã nguồn Java lúc runtime và biến nó thành bytecode mà không gọi lệnh **javac** bằng tiến trình hệ điều hành riêng. Ví dụ, một công cụ học lập trình biên dịch bài tập người dùng gửi đến, một nền tảng plugin tạo implementation từ mẫu đã kiểm soát, hoặc một hệ thống xây dựng mã sinh tự động.

Java cung cấp **Java Compiler API** trong package **javax.tools**, thuộc module **java.compiler**. Với một bản JDK có compiler khả dụng, luồng xử lý thường là:

~~~text
Mã nguồn Java (tệp .java hoặc JavaFileObject từ chuỗi)
                     |
                     v
        ToolProvider.getSystemJavaCompiler()
                     |
                     v
           JavaFileManager + options
                     |
                     v
    JavaCompiler.getTask(...) -> CompilationTask
                     |
                     | cấu hình thêm nếu cần
                     v
               task.call()
              /           \
           true           false
            |               |
     không có lỗi       có lỗi biên dịch
      biên dịch         -> xem diagnostics
            |
     có thể có .class
     ở output đã chọn
~~~

**Điểm mấu chốt:** **JavaCompiler.getTask(...)** chỉ **tạo một tác vụ biên dịch**, chưa thực hiện biên dịch. **JavaCompiler.CompilationTask.call()** mới **chạy tác vụ** và trả kết quả **Boolean**.

Nếu biên dịch thành công, ứng dụng vẫn chưa tự động **chạy** class mới. Biên dịch, nạp class và gọi phương thức là những trách nhiệm riêng; bài này tập trung vào cách tạo CompilationTask, thực thi và đọc kết quả.

## 2. Các kiểu API tham gia

Các lớp/interface thường dùng:

| Kiểu | Vai trò |
|---|---|
| **ToolProvider** | Lấy compiler hệ thống qua **getSystemJavaCompiler()** |
| **JavaCompiler** | Giao diện điều khiển trình biên dịch Java |
| **JavaCompiler.CompilationTask** | Tác vụ cấu hình sẵn nhưng chưa chạy; có **call()** |
| **JavaFileObject** | Biểu diễn một đơn vị mã nguồn Java hoặc tệp Java liên quan |
| **SimpleJavaFileObject** | Lớp nền tiện dụng để tạo nguồn từ chuỗi trong bộ nhớ |
| **StandardJavaFileManager** | Quản lý nguồn/đầu ra và các đường dẫn chuẩn của compiler |
| **DiagnosticCollector<JavaFileObject>** | Thu thập lỗi/cảnh báo/note do compiler phát ra |
| **Diagnostic<? extends JavaFileObject>** | Chi tiết một diagnostic: loại, vị trí, thông điệp |

Bước khởi đầu:

~~~java
// Mảnh mã minh họa trong một phương thức Java.
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();

if (compiler == null) {
    throw new IllegalStateException("A JDK compiler is required");
}
~~~

Dùng **JDK 17+** cho các ví dụ ở đây. **getSystemJavaCompiler() có thể trả null** nếu runtime image không chứa compiler, ví dụ môi trường chỉ đóng gói các module runtime cần thiết nhưng thiếu **jdk.compiler**. Việc máy có lệnh **java** không tự bảo đảm compiler được đóng gói. Với named module sử dụng javax.tools, module ứng dụng khai báo **requires java.compiler**; để thực sự biên dịch còn cần triển khai compiler khả dụng lúc chạy.

Không sử dụng **com.sun.tools.javac.Main** hoặc API nội bộ chỉ để gọi javac từ Java code; **javax.tools** là giao diện chuẩn cho mục tiêu này.

## 3. Hiểu đầy đủ chữ ký getTask(...)

Phương thức của **JavaCompiler**:

~~~java
JavaCompiler.CompilationTask getTask(
    java.io.Writer out,
    JavaFileManager fileManager,
    DiagnosticListener<? super JavaFileObject> diagnosticListener,
    Iterable<String> options,
    Iterable<String> classes,
    Iterable<? extends JavaFileObject> compilationUnits
);
~~~

Ý nghĩa sáu tham số:

| Tham số | Ý nghĩa | Cách dùng điển hình |
|---|---|---|
| **out** | Writer nhận các thông tin đầu ra bổ sung của compiler | null để dùng đích mặc định hoặc StringWriter để thu nội dung |
| **fileManager** | Điều phối đọc source, classpath/module path và ghi kết quả | Truyền StandardJavaFileManager đã cấu hình; null để compiler tạo mặc định |
| **diagnosticListener** | Nhận diagnostic theo từng sự kiện | DiagnosticCollector để giữ lại lỗi/cảnh báo có cấu trúc |
| **options** | Các tùy chọn trình biên dịch dưới dạng chuỗi tách riêng | List.of("--release", "17", "-d", "out") |
| **classes** | Tên class phục vụ **annotation processing** | Thường **null** khi chỉ biên dịch các source units |
| **compilationUnits** | Danh sách JavaFileObject là các đơn vị mã nguồn cần biên dịch | File manager chuyển .java thành JavaFileObject, hoặc tự tạo source trong bộ nhớ |

**Hai nhầm lẫn cần tránh:**

- **classes** không phải tham số “tên class đầu ra cần tạo” hay tên class chuẩn bị chạy. Nó chủ yếu dành cho tên các class cần xử lý bởi annotation processor. Nếu đã có JavaFileObject của source, phần lớn trường hợp truyền **classes = null**.
- Mỗi option và giá trị của option nên là **hai phần tử riêng**, ví dụ **"-d", "out"** thay vì ghép **"-d out"** thành một chuỗi; tương tự **"--release", "17"**.

Ví dụ cấu hình ngắn:

~~~java
// Mảnh minh họa: compiler, manager, diagnostics và units có sẵn.
JavaCompiler.CompilationTask task = compiler.getTask(
    null,                          // compiler output Writer
    manager,                       // JavaFileManager
    diagnostics,                   // DiagnosticCollector
    List.of("--release", "17",
            "-proc:none",
            "-d", "out"),          // compiler options
    null,                          // class names for annotation processing
    units                          // source JavaFileObject
);
~~~

Khi câu lệnh này kết thúc, **task tồn tại nhưng chưa biên dịch**. Có thể tùy chỉnh một số khía cạnh của task trước khi chạy, sau đó gọi **task.call()**.

### Writer và DiagnosticCollector khác nhau thế nào?

**out** nhận phần output bổ sung mà compiler gửi qua Writer. **diagnosticListener** nhận các diagnostic có cấu trúc; chúng có thể bao gồm **ERROR**, **WARNING**, **MANDATORY_WARNING**, **NOTE** và **OTHER**, với nguồn, vị trí, mã diagnostic và thông điệp.

Để tự phân loại lỗi hoặc gắn lỗi với dòng mã nguồn trong giao diện, **DiagnosticCollector** hữu ích hơn việc đọc một chuỗi console. Không nên giả định mọi bản JDK hay mọi locale in đúng cùng một văn bản lỗi. Giá trị **call()** nói tác vụ thành công hay thất bại; danh sách diagnostics giúp giải thích chi tiết tại sao.

## 4. CompilationTask.call() làm gì?

Interface **JavaCompiler.CompilationTask** mở rộng **Callable<Boolean>**. Khi gọi:

~~~java
// Mảnh minh họa.
Boolean result = task.call();
boolean success = Boolean.TRUE.equals(result);
~~~

- **call()** chạy tác vụ biên dịch **đồng bộ trong lời gọi hiện tại** và chỉ trả về khi tác vụ hoàn tất hoặc ném lỗi. Không phải lệnh tự gửi vào background thread.
- **Boolean.TRUE** tương ứng việc **tất cả các source units được biên dịch không có lỗi**. Có thể vẫn có warning/note.
- **Boolean.FALSE** tương ứng biên dịch có lỗi. Nó là **kết quả biên dịch bình thường**, không phải mặc định là exception.
- Tác vụ **chỉ thực thi một lần**. Gọi **call()** lần thứ hai trên cùng task gây **IllegalStateException**; muốn biên dịch lại, phải tạo **CompilationTask mới**.
- Thông số **setProcessors(...)**, **setLocale(...)** và **addModules(...)** (khi thích hợp) phải cấu hình **trước** khi bắt đầu task; không thay đổi giữa lúc chạy hoặc sau khi chạy.
- Một số lỗi cấu hình hoặc lỗi nghiêm trọng của thành phần do ứng dụng cung cấp có thể làm **getTask/call ném exception**. Không đánh đồng mọi exception với Boolean.FALSE.

Cách diễn đạt đúng:

~~~java
// Mảnh minh họa.
JavaCompiler.CompilationTask task = compiler.getTask(
        null, manager, diagnostics, options, null, sourceFiles);

// Đến đây mới tạo task.
Boolean compiled = task.call(); // Bắt đầu biên dịch.

if (Boolean.TRUE.equals(compiled)) {
    System.out.println("Compilation succeeded");
} else {
    System.out.println("Compilation failed");
}
~~~

**Tránh gọi lặp:** **task.call()** không phải phương thức kiểm tra trạng thái bất biến. Nếu cần biết lần biên dịch đã thành công chưa ở chỗ khác, **lưu kết quả Boolean**, không gọi lại task.

## 5. Ví dụ đầy đủ Java 17: hai tác vụ, một thành công và một thất bại

Chương trình sau tự tạo **JavaFileObject từ chuỗi** nên bạn chỉ cần một file source để chạy ví dụ. Nó sẽ:

1. Lấy JavaCompiler của JDK.
2. Chuẩn bị thư mục output riêng cho .class.
3. Tạo một source **demo.Good** hợp lệ và một source **demo.Bad** chứa lỗi kiểu dữ liệu.
4. Tạo **CompilationTask riêng** cho từng lần biên dịch bằng **getTask(...)**.
5. Gọi **call()**, in kết quả thành công/thất bại và kiểm tra có diagnostic loại ERROR hay không.

### 5.1. Nội dung tệp CompilationTaskDemo.java

~~~java
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

public final class CompilationTaskDemo {

    private static final class StringSource extends SimpleJavaFileObject {
        private final String code;

        StringSource(String className, String code) {
            super(
                URI.create(
                    "string:///" + className.replace('.', '/')
                        + JavaFileObject.Kind.SOURCE.extension
                ),
                JavaFileObject.Kind.SOURCE
            );
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    private static void compile(
            JavaCompiler compiler,
            String label,
            JavaFileObject unit,
            Path output) throws IOException {

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        // Tạo file manager cho lần biên dịch này.
        try (StandardJavaFileManager manager =
                compiler.getStandardFileManager(
                    diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {

            List<String> options = List.of(
                "--release", "17",
                "-proc:none",
                "-d", output.toString()
            );

            JavaCompiler.CompilationTask task = compiler.getTask(
                null,               // Writer nhận output khác
                manager,            // Quản lý source và class output
                diagnostics,        // Thu thập diagnostic
                options,            // Tùy chọn compiler
                null,               // Không cung cấp class để xử lý annotation
                List.of(unit)       // Một source unit
            );

            // Chỉ sau lời gọi này compiler mới thực thi tác vụ.
            Boolean result = task.call();

            boolean hasErrors = diagnostics.getDiagnostics().stream()
                .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR);

            System.out.println(
                label + " success=" + Boolean.TRUE.equals(result));
            System.out.println(label + " hasErrors=" + hasErrors);
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Requires a JDK compiler");
        }

        Path output = Path.of("out");
        Files.createDirectories(output);

        String validSource = """
                package demo;
                public class Good {
                    public static int answer() {
                        return 42;
                    }
                }
                """;

        String invalidSource = """
                package demo;
                public class Bad {
                    public static int answer() {
                        return "not-an-int";
                    }
                }
                """;

        compile(
            compiler,
            "good",
            new StringSource("demo.Good", validSource),
            output
        );

        compile(
            compiler,
            "bad",
            new StringSource("demo.Bad", invalidSource),
            output
        );
    }
}
~~~

**Biên dịch và chạy** bằng JDK 17 trở lên, từ thư mục chứa file:

~~~bash
javac --release 17 -encoding UTF-8 CompilationTaskDemo.java
java CompilationTaskDemo
~~~

**Stdout dự kiến chính xác với JDK 17 và ví dụ trên:**

~~~text
good success=true
good hasErrors=false
bad success=false
bad hasErrors=true
~~~

Chương trình không cố in nguyên văn compiler error vì thông điệp có thể khác theo phiên bản JDK và locale. **Bad** chứa lỗi không thể chuyển String sang int, nên việc biên dịch thất bại và có ít nhất một diagnostic ERROR. **Good** hợp lệ, nên không có diagnostic ERROR. Ví dụ dùng **-proc:none** để tránh annotation processor ngoài dự kiến ảnh hưởng lần biên dịch.

Sau khi chạy, thư mục **out/demo/** chứa **Good.class** nếu biên dịch thành công. **Bad** không được kỳ vọng tạo ra class hợp lệ. Để thận trọng trong ứng dụng thực tế, không dùng sự hiện diện của một tệp .class từ lần chạy trước làm dấu hiệu thành công của lần biên dịch hiện tại; hãy dựa vào kết quả **call()** và quản lý thư mục output theo từng lần build.

### 5.2. Tại sao cần StringSource?

**SimpleJavaFileObject** đại diện một nguồn trong bộ nhớ. URI:

~~~text
string:///demo/Good.java
~~~

cho compiler biết đường dẫn logic tương ứng tên binary **demo.Good** và loại file **Kind.SOURCE**. Method **getCharContent(...)** trả chuỗi mã nguồn. Chương trình không cần tạo **Good.java** và **Bad.java** thật trên đĩa trước khi biên dịch.

Nếu chỉ cần biên dịch tệp .java có sẵn, **StandardJavaFileManager** đã cung cấp cách chuyển tệp thành JavaFileObject; không phải viết StringSource. Phần 7 minh họa hướng đó.

### 5.3. Tại sao dùng hai CompilationTask?

**Mỗi tác vụ chỉ call() một lần.** Muốn compile mã Good rồi compile mã Bad, chương trình tạo hai task riêng bằng hai lần **compiler.getTask(...)**. Có thể tạo một task chứa nhiều source units để biên dịch cả hai cùng lúc, nhưng khi một source có lỗi, kết quả chung sẽ **false**, khó minh họa riêng nhánh thành công và thất bại.

Đầu ra **good success=true** là kết quả **Boolean** của task đầu tiên; **bad success=false** là kết quả của task thứ hai. Hai dòng **hasErrors** đi từ **DiagnosticCollector**, dùng để giải thích kết quả nhưng không thay thế hoàn toàn nó.

### 5.4. Vì sao cần file manager?

**StandardJavaFileManager** giúp compiler tìm nguồn, xác định classpath/module path và viết file .class vào output. Ở ví dụ, option **-d out** chỉ định thư mục output; lệnh **Files.createDirectories(out)** tạo trước thư mục để tránh lỗi do đường dẫn chưa tồn tại. **try-with-resources** đóng file manager dù biên dịch thành công hay thất bại.

File manager là tài nguyên liên quan đến compiler; với hệ thống biên dịch nhiều lần liên tiếp, có thể tái sử dụng một StandardJavaFileManager một cách có kiểm soát để tận dụng cache. Tuy nhiên không được đóng nó trước khi **call()** kết thúc, và phải điều phối an toàn nếu có nhiều task.

## 6. Phân biệt kết quả call() với diagnostics

**Boolean result** và **DiagnosticCollector** trả lời hai câu hỏi khác nhau:

| Quan sát | Kết luận đúng |
|---|---|
| **call() == true** | Tất cả đơn vị nguồn trong task được biên dịch không có lỗi |
| **call() == false** | Có lỗi biên dịch trong task |
| **diagnostic.Kind.ERROR** | Compiler báo một lỗi cụ thể, có thể lấy source/line/column/message |
| Chỉ có **WARNING/NOTE** | Task vẫn có thể thành công nếu không có ERROR |
| **call() ném exception** | Có lỗi không được biểu diễn đơn thuần bằng kết quả biên dịch false; cần xử lý nguyên nhân |
| **call() == true** nhưng sau đó class không load được | Biên dịch thành công không bảo đảm runtime dependencies, classpath, bytecode loading hoặc hành vi nghiệp vụ |

Ví dụ xử lý kết quả và in thông tin diagnostic (mảnh minh họa, đặt tại nơi đã có **task** và **diagnostics**):

~~~java
Boolean result = task.call();

if (Boolean.TRUE.equals(result)) {
    System.out.println("Compilation OK");
} else {
    System.out.println("Compilation has errors");
}

for (Diagnostic<? extends JavaFileObject> d
        : diagnostics.getDiagnostics()) {
    System.out.printf(
        "%s at line %d: %s%n",
        d.getKind(),
        d.getLineNumber(),
        d.getMessage(Locale.ROOT)
    );
}
~~~

**Diagnostic.getLineNumber()** hoặc **getColumnNumber()** có thể trả **Diagnostic.NOPOS** nếu lỗi không gắn với vị trí cụ thể; một số diagnostic cũng không có source. Giao diện hiển thị lỗi nên có fallback cho những trường hợp ấy.

Để tạo output ổn định cho kiểm thử, ưu tiên kiểm tra **Kind**, **getCode()**, số lượng lỗi hoặc trạng thái true/false hơn là so khớp toàn bộ câu chữ diagnostic. Ngôn ngữ và chi tiết thông điệp của compiler không phải hợp đồng hiển thị bất biến giữa các phiên bản.

### Ví dụ điều kiện cảnh báo

Một source hợp lệ có thể tạo warning khi dùng API deprecated hoặc generic unchecked conversion. Khi ấy:

~~~text
result = true
diagnostics có WARNING hoặc MANDATORY_WARNING
~~~

Nếu build policy của bạn xem warning là lỗi, có thể dùng compiler option **-Werror** để nâng warning thành nguyên nhân thất bại. Đừng tự suy đoán rằng **diagnostics không rỗng** đồng nghĩa biên dịch lỗi.

## 7. Biên dịch một hoặc nhiều tệp .java thực tế

Nếu nguồn đã nằm trên đĩa, dùng **getJavaFileObjectsFromPaths** thay cho StringSource. Với tệp **src/demo/Greeting.java**, ví dụ:

~~~java
// Mảnh minh họa, giả định compiler và diagnostics đã tồn tại.
try (StandardJavaFileManager manager =
        compiler.getStandardFileManager(
            diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {

    Iterable<? extends JavaFileObject> units =
        manager.getJavaFileObjectsFromPaths(
            List.of(Path.of("src/demo/Greeting.java"))
        );

    JavaCompiler.CompilationTask task = compiler.getTask(
        null,
        manager,
        diagnostics,
        List.of("--release", "17", "-d", "out"),
        null,
        units
    );

    boolean ok = Boolean.TRUE.equals(task.call());
    System.out.println("Compilation OK: " + ok);
}
~~~

Đây là **mảnh code minh họa**, không phải chương trình độc lập: cần các import, compiler, diagnostics và thư mục **out** đã tạo. Đoạn code cho thấy cùng API **getTask/call**, chỉ khác cách tạo **compilationUnits**. Đối với nhiều tệp source, cung cấp nhiều JavaFileObject:

~~~java
// Mảnh minh họa khi có sẵn hai tệp.
Iterable<? extends JavaFileObject> units =
    manager.getJavaFileObjectsFromPaths(List.of(
        Path.of("src/demo/Greeting.java"),
        Path.of("src/demo/Helper.java")
    ));
~~~

Nếu các source phụ thuộc lẫn nhau, biên dịch chúng cùng trong một task thường giúp compiler giải quyết tên/kiểu nhất quán. Nếu source sử dụng thư viện ngoài, cần bổ sung **-classpath** hoặc **--module-path**, và có thể cần **--add-modules**, tùy mô hình deploy. Không tự động lấy dependencies của cả ứng dụng làm classpath biên dịch nếu đó là mã không tin cậy hoặc cần build lặp lại có kiểm soát.

## 8. Tùy chọn compiler và classpath cho CompilationTask

Một số tùy chọn thường đặt trong tham số **options** của getTask:

| Option | Tác dụng |
|---|---|
| **--release 17** | Biên dịch theo ngôn ngữ, bytecode và API công khai của Java 17 |
| **-d outputDir** | Chỉ định thư mục class output |
| **-classpath path** hoặc **-cp path** | Đặt classpath chứa các kiểu/phụ thuộc compiler cần |
| **--module-path path** | Đặt module path để resolve named modules khi cần |
| **-proc:none** | Tắt annotation processing cho task |
| **-Xlint:all** | Yêu cầu thông báo lint chi tiết |
| **-Werror** | Coi warning thành lỗi biên dịch |

Trong API, mỗi chuỗi là một phần tử:

~~~java
// Mảnh minh họa, sử dụng đúng OS-specific classpath string.
List<String> options = List.of(
    "--release", "17",
    "-d", "out",
    "-classpath", "lib/api.jar",
    "-proc:none"
);
~~~

Nếu có nhiều JAR trên classpath, dấu phân cách đường dẫn là **:** trên Linux/macOS và **;** trên Windows. Không ghép option/vị trí đầu ra bằng cách chèn tùy tiện shell quote vào List: **getTask** nhận argument đã tách, không thông qua shell parser.

**Không tự chế danh sách source bằng tên class trong tham số classes.** Nếu có tên class như **demo.Greeting** mà muốn compile file **Greeting.java**, hãy chuyển tệp đó thành **JavaFileObject** và đặt trong **compilationUnits**. Tham số **classes** chủ yếu phục vụ annotation processing trên class names.

### Đối với nguồn tạo động

Khi mã mới dùng interface host như **plugin.api.Extension**, phải cho compiler thấy bản API phù hợp ở classpath/module path. Biên dịch thành công với một phiên bản API khác không bảo đảm class nạp vào runtime host tương thích; quản lý classpath và classloader là công việc tiếp theo sau **call()**.

## 9. Một tác vụ, một lần chạy: trạng thái và tái sử dụng

Một số hiểu nhầm về vòng đời CompilationTask:

**getTask() không phải Future đã được submit.** Javadoc mô tả task đại diện việc biên dịch sẽ thực hiện sau đó. Nó mở rộng **Callable<Boolean>**, nhưng nếu mã gọi **task.call()** trực tiếp thì biên dịch chạy đồng bộ. Muốn chạy trên executor riêng là quyết định của ứng dụng; khi đó cần quản lý concurrency và file manager/output riêng, không được suy luận compiler tự tạo thread.

**Không gọi call hai lần.**

~~~java
// Mảnh minh họa:
JavaCompiler.CompilationTask task = compiler.getTask(
        null, manager, diagnostics, options, null, units);
Boolean first = task.call();

// Sai: đây không phải cách đọc lại kết quả.
Boolean second = task.call(); // IllegalStateException
~~~

Để compile lại source, tạo **task mới**. Nếu muốn giữ kết quả, lưu biến **first**. Với hệ thống cần nạp source mới nhiều lần, tạo task mới cho mỗi lần biên dịch, chọn output directory theo lượt và tránh cập nhật chung các artifact đang được dùng bởi runtime.

**Cấu hình processor/locale phải diễn ra trước call():**

~~~java
// Mảnh minh họa, task được tạo nhưng chưa chạy.
task.setLocale(Locale.ROOT);

// Nếu muốn chỉ định annotation processors:
// task.setProcessors(List.of(myProcessor));

// Tác vụ bắt đầu tại đây.
Boolean result = task.call();
~~~

Gọi **setLocale** hay **setProcessors** sau khi task đã bắt đầu có thể ném **IllegalStateException**. **setProcessors(...)** ghi đè cơ chế tự phát hiện processors bằng danh sách do ứng dụng cung cấp; cần hiểu rõ khi dùng annotation processing. Ví dụ chính dùng **-proc:none**, nên không chạy processors.

## 10. Xử lý thất bại đúng chỗ

Hãy chia lỗi thành ba giai đoạn:

### 10.1. Không lấy được compiler

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();

if (compiler == null) {
    throw new IllegalStateException(
        "No system Java compiler; run on a JDK with jdk.compiler");
}
~~~

Lỗi này xảy ra **trước khi getTask**. Kiểm tra JDK thực tế của process, cấu hình runtime image và modules. Không nên coi đây là lỗi source của người dùng.

### 10.2. Cấu hình task thất bại

Ví dụ option không hợp lệ, file manager không hỗ trợ location bắt buộc, input không đúng hoặc vấn đề I/O có thể làm quá trình chuẩn bị task hoặc call không chạy đúng. Cần phân biệt lỗi cấu hình/deployment với lỗi mã nguồn.

~~~java
// Mảnh minh họa: chuẩn bị task trong try phù hợp.
try {
    JavaCompiler.CompilationTask task = compiler.getTask(
        null, manager, diagnostics, options, null, units);
    Boolean result = task.call();
    System.out.println("compiled=" + result);
} catch (IllegalArgumentException e) {
    throw new IllegalStateException("Invalid compiler configuration", e);
}
~~~

Không phải mọi lỗi setup đều là IllegalArgumentException; ví dụ này chỉ nhấn mạnh một loại, không phải danh sách catch đầy đủ. Với thành phần do ứng dụng tự viết như JavaFileManager, DiagnosticListener hoặc JavaFileObject, lỗi runtime do callback gây ra có thể làm task ném RuntimeException, theo hợp đồng API. Cần log cause có ngữ cảnh, không nuốt lỗi rồi giả là lỗi source.

### 10.3. Nguồn Java chứa lỗi

Đây là trường hợp thông thường:

~~~java
Boolean result = task.call();

if (!Boolean.TRUE.equals(result)) {
    for (Diagnostic<? extends JavaFileObject> diagnostic
            : diagnostics.getDiagnostics()) {
        if (diagnostic.getKind() == Diagnostic.Kind.ERROR) {
            System.err.println(diagnostic.getMessage(Locale.ROOT));
        }
    }
}
~~~

**false** nghĩa compilation không thành công. Đối với code dịch vụ, hãy trả về trạng thái và các lỗi hợp lệ cho caller thay vì chuyển mọi lỗi mã nguồn thành exception không phân loại.

**Thất bại không đồng nghĩa không có output:** Compiler có thể đã tạo một số tệp .class trước khi phát hiện lỗi khác, hoặc output có thể chứa kết quả từ lần biên dịch trước. Đừng đưa output vào sử dụng khi **call() == false**; nên build trong thư mục/staging riêng rồi chỉ xuất bản artifacts sau khi kết quả thành công.

## 11. Thiết kế an toàn khi nhận mã Java lúc runtime

Runtime compilation có giá trị trong công cụ IDE, bài tập, rule engine hoặc plugin host, nhưng cần ranh giới rõ:

- **Biên dịch khác với chạy:** JavaCompiler phân tích và tạo bytecode; muốn gọi class mới phải dùng classloader/module layer khác, kiểm tra kiểu hợp đồng, quản lý lifecycle và quyền sử dụng.
- **Chạy annotation processor cũng là chạy mã:** Không đưa processors ngoài dự kiến vào compiler invocation nếu nguồn không tin cậy. Có thể dùng **-proc:none** khi không cần processing, như ví dụ.
- **Không dùng classpath quá rộng:** Tránh cho compiler nhìn thấy secret/internal classes không cần; quản lý dependency của source và version API.
- **Giới hạn tài nguyên:** Biên dịch mã phức tạp có thể dùng nhiều CPU, RAM, I/O. Nếu chạy nguồn không tin cậy, cần isolation mạnh ở process/container, timeout và hạn ngạch phù hợp. Không coi JavaCompiler là sandbox.
- **Gắn kết quả với từng lượt biên dịch:** Dùng output directory riêng và diagnostic collector riêng, tránh race giữa các lần biên dịch, tránh đọc nhầm kết quả trước đó.
- **Đóng tài nguyên:** File manager, stream và classloader dùng sau biên dịch có vòng đời riêng. JavaCompiler.CompilationTask không tự đóng mọi tài nguyên do ứng dụng truyền vào.

**Chỉ gọi call() thành công không xác thực mã có an toàn để thực thi.** Bytecode có thể chứa logic nguy hiểm hoặc mã gọi thư viện bên ngoài; chạy code của bên thứ ba trong cùng JVM chỉ nên thực hiện với độ tin cậy và chính sách phù hợp.

## 12. So sánh getTask/call với các cách biên dịch khác

| Phương án | Khi nào thích hợp | Khác biệt cần nhớ |
|---|---|---|
| **JavaCompiler.getTask + call** | Ứng dụng muốn điều khiển source, options, diagnostics/file manager và xử lý trạng thái trong Java | Tách tạo task và thực thi; hỗ trợ JavaFileObject trong bộ nhớ |
| **JavaCompiler.run(...)** | Cần giao diện đơn giản dạng command-line từ Java | Nhận input/output stream và argument, trả int exit code; ít điều khiển cấu trúc hơn |
| **ProcessBuilder chạy javac** | Cần process bên ngoài và cách ly tiến trình rõ, hoặc dùng một toolchain riêng | Phải quản lý process, stdout/stderr, exit code và classpath |
| **javac qua terminal** | Biên dịch dự án/tệp thủ công | Công cụ CLI, không tích hợp trực tiếp cấu trúc diagnostics vào ứng dụng |
| **JShell API** | Chạy đoạn snippet tương tác, REPL, trạng thái phiên | Mô hình snippet khác với full compilation units và task từ getTask |

Nếu mục tiêu là **đọc kết quả biên dịch và trả diagnostics có cấu trúc**, getTask/call kết hợp DiagnosticCollector phù hợp hơn việc parse text từ terminal. Nếu chỉ cần biên dịch dự án chuẩn, build tool thường là lựa chọn thực tế hơn thay vì tự xây compiler orchestration.

## 13. Kiểm thử và quan sát hành vi

### Kiểm thử 1: getTask chưa khởi chạy compile

Tạo task nhưng chưa gọi **call()** rồi kiểm tra thư mục output của một lần chạy sạch. Chưa có yêu cầu compiler thực thi compilation unit; chỉ khi call() chạy mới có kết quả. Đừng nhầm với hành vi setup file manager có thể truy cập filesystem.

### Kiểm thử 2: nguồn hợp lệ

**Good** trong ví dụ trả **true**, không có diagnostic **Kind.ERROR**. Có thể thấy class output tương ứng trong **out/demo/Good.class**.

### Kiểm thử 3: nguồn sai kiểu

**Bad** trả **false**, **hasErrors=true**. Dùng diagnostic để xác định lỗi tại phép return String từ phương thức trả int. Không kiểm tra bằng cách cố chạy Bad.class.

### Kiểm thử 4: gọi call lần thứ hai

~~~java
// Mảnh minh họa:
task.call();
task.call(); // IllegalStateException
~~~

Nhấn mạnh điều này không phải cách “lấy lại kết quả”, mà là lỗi vòng đời của task.

### Kiểm thử 5: warning không phải failure

Dùng source tạo warning nhưng không có error; **call()** vẫn có thể **true**. Bật **-Werror** khi chính sách build muốn warning làm thất bại compilation.

### Kiểm thử 6: compiler không tồn tại

Chạy ứng dụng trên runtime image không chứa trình biên dịch; kiểm tra **ToolProvider.getSystemJavaCompiler() == null** được báo thành lỗi hạ tầng rõ ràng, không bị hiểu nhầm là lỗi source Java.

## 14. Các câu hỏi tự đánh giá

**Câu 1.** Dòng **compiler.getTask(...)** có biên dịch ngay source không?

**Trả lời:** Không. Nó tạo một **CompilationTask** chưa thực thi. **task.call()** mới chạy compilation.

**Câu 2.** Giá trị **Boolean.FALSE** từ call() có nghĩa chương trình Java bị lỗi khi chạy không?

**Trả lời:** Không. Nó báo **lỗi biên dịch**. Mã chưa nhất thiết được nạp hoặc chạy; runtime error thuộc giai đoạn sau.

**Câu 3.** Nếu compiler tạo warning nhưng không có error, call() trả gì?

**Trả lời:** Thông thường **true**, vì compilation không có lỗi; riêng chính sách như **-Werror** có thể biến warning thành lỗi khiến task thất bại.

**Câu 4.** Vì sao **classes = null** khi biên dịch mã nguồn từ JavaFileObject?

**Trả lời:** Tham số này phục vụ **tên class cho annotation processing**, không phải vị trí đặt source file. Các nguồn muốn biên dịch đã được đưa trong **compilationUnits**.

**Câu 5.** Có nên gọi cùng **task.call()** lần nữa sau khi sửa source Java?

**Trả lời:** Không. Task chỉ được chạy một lần. Tạo task mới từ JavaFileObject mới và tùy chọn/file manager phù hợp.

**Câu 6.** Tại sao không nên so sánh text lỗi compiler nguyên văn trong unit test?

**Trả lời:** Diagnostic message có thể thay đổi theo JDK, locale và phiên bản; nên dựa trên trạng thái, Kind, code hoặc các thuộc tính có cấu trúc phù hợp.

**Câu 7.** Biên dịch thành công có bảo đảm class mới hoạt động với API host không?

**Trả lời:** Không. Runtime classpath/module path, classloader identity, phiên bản dependencies và logic nghiệp vụ vẫn có thể gây lỗi. Giai đoạn load/execute phải kiểm tra riêng.

## 15. Checklist khi triển khai vào ứng dụng

1. **Runtime có compiler:** xác minh getSystemJavaCompiler() khác null và JDK/module cần thiết hiện diện.
2. **Source hợp lệ:** cung cấp JavaFileObject từ tệp hoặc chuỗi với tên URI đúng, mã hóa UTF-8 và dependency source phù hợp.
3. **Task được cấu hình đúng:** xác định file manager, diagnostics, options, annotation processing policy; hiểu đúng hai tham số classes và compilationUnits.
4. **Output cách ly:** chỉ định -d vào thư mục rõ ràng, tránh trộn kết quả biên dịch thành công/thất bại hoặc các phiên đồng thời.
5. **Gọi call() đúng một lần:** lưu Boolean, phân biệt true/false và exception; không coi getTask là lệnh thực thi.
6. **Đọc diagnostics:** dùng Kind.ERROR, line/column/source/code khi phù hợp; không phụ thuộc hoàn toàn vào câu chữ.
7. **Đóng tài nguyên:** StandardJavaFileManager bằng try-with-resources; tự quản lý classloader/lifecycle nếu dùng bytecode.
8. **Kiểm thử cả hai nhánh:** nguồn hợp lệ trả true, nguồn lỗi trả false; xác minh case compiler null, warning, option sai và exception từ callback nếu hệ thống cần.
9. **Chỉ chạy mã đã được tin cậy/kiểm soát:** compiler không cung cấp sandbox; cần cách ly riêng với source không tin cậy.

**Ghi nhớ:** **getTask(...)** giúp chuẩn bị một **CompilationTask** với source, file manager, options và diagnostics. **call()** thực sự thực hiện việc biên dịch và trả **Boolean** thành công/thất bại, chỉ gọi một lần. Kiểm tra kết quả cùng các **Diagnostic** là nền tảng để một ứng dụng phản hồi chính xác cho người dùng về tác vụ biên dịch Java lúc chạy.

### Tài liệu Java SE 17

- JavaCompiler: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html
- JavaCompiler.CompilationTask: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.CompilationTask.html
- Diagnostic / DiagnosticCollector: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/Diagnostic.html
- StandardJavaFileManager: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/StandardJavaFileManager.html
- ToolProvider: https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ToolProvider.html
