# Phân biệt API chuẩn với lớp triển khai nội bộ của javac

## 1. Mục tiêu và thông điệp chính

Khi viết công cụ biên dịch Java, một câu hỏi xuất hiện rất sớm: **nên gọi javax.tools.JavaCompiler, dùng com.sun.source.*, hay import trực tiếp com.sun.tools.javac.*?** Ba nhóm này không có cùng mức cam kết tương thích.

- **API chuẩn của Java SE**: các giao diện và lớp công khai như javax.tools.JavaCompiler, javax.tools.ToolProvider, javax.tools.JavaFileObject, javax.annotation.processing và javax.lang.model. Chúng mô tả *hợp đồng* lập trình cho compiler, file manager, diagnostics và annotation processing.
- **API công khai của JDK, gắn với javac**: tiêu biểu là com.sun.source.tree và com.sun.source.util, được module jdk.compiler export. Chúng được tài liệu JDK mô tả để xem cây cú pháp, đi qua AST và quan sát các pha javac, nhưng **không phải toàn bộ đều thuộc Java SE standard**.
- **Lớp triển khai nội bộ của javac**: com.sun.tools.javac.api.JavacTool, com.sun.tools.javac.tree.JCTree, com.sun.tools.javac.util.Context, com.sun.tools.javac.comp.Attr... Chúng phục vụ cách javac triển khai compiler, nhiều package không được export công khai cho ứng dụng bình thường. Không nên thiết kế ứng dụng lâu dài phụ thuộc trực tiếp vào chúng.

Bài này giải thích **phân biệt theo module, mức export, tài liệu và hợp đồng API**, thay vì nhận diện bằng tiền tố tên package. Bạn sẽ xây chương trình Java 17 biên dịch nguồn trong bộ nhớ bằng API chuẩn, xem diagnostics, thử Tree API công khai của JDK, hiểu vì sao import API nội bộ bị từ chối, và biết cách thiết kế tầng thích nghi nếu thực sự cần chức năng đặc thù của javac.

**Nguyên tắc:** nếu nhu cầu được API chuẩn đáp ứng, ưu tiên API chuẩn. Chỉ dùng API JDK-specific khi thật sự cần tính năng đó và đã xác định giới hạn hỗ trợ. Không nhầm một lớp có modifier public bên trong JDK với một API được cam kết cho ứng dụng của bạn.

## 2. Ba tầng API và module tương ứng

~~~text
Ứng dụng / build tool / IDE integration
                 |
                 | API chuẩn Java SE
                 v
           module java.compiler
    javax.tools.JavaCompiler
    javax.tools.JavaFileObject
    javax.annotation.processing.*
    javax.lang.model.*
                 |
                 | Service provider / compiler implementation
                 v
           module jdk.compiler
    +-----------------------------------+
    | Public JDK-specific APIs          |
    | com.sun.source.tree.*             |
    | com.sun.source.util.*             |
    +-----------------------------------+
    | Internal javac implementation     |
    | com.sun.tools.javac.api.*         |
    | com.sun.tools.javac.tree.*        |
    | com.sun.tools.javac.comp.*        |
    | com.sun.tools.javac.util.*        |
    +-----------------------------------+
                 |
                 v
             .class files
~~~

Bảng đối chiếu:

| Nhóm | Ví dụ | Module chứa API | Mức cam kết thực tế |
| --- | --- | --- | --- |
| Java SE compiler API | javax.tools.JavaCompiler, ToolProvider, DiagnosticListener | java.compiler | API chuẩn, phù hợp tích hợp compiler ở mức hợp đồng |
| Java SE annotation processing API | javax.annotation.processing.Processor, AbstractProcessor | java.compiler | API chuẩn cho processor và processing rounds |
| Java SE language model | javax.lang.model.element.TypeElement, javax.lang.model.util.Types | java.compiler | Mô hình kiểu/khai báo chuẩn |
| JDK public compiler Tree API | com.sun.source.tree.CompilationUnitTree | jdk.compiler | API công khai của JDK, chuyên biệt cho cây cú pháp javac |
| JDK public compiler utility API | com.sun.source.util.JavacTask, TreePathScanner, Trees | jdk.compiler | API JDK-specific được export; không phải interface JavaCompiler trung lập backend |
| Javac internal implementation | com.sun.tools.javac.api.JavacTool, JCTree, Context | jdk.compiler | Nội bộ, không được export chung cho ứng dụng; dễ thay đổi |

**Hai nhầm lẫn cần loại bỏ:**

1. Mọi package bắt đầu bằng com.sun đều là nội bộ? **Không.** com.sun.source.tree và com.sun.source.util là các API công khai được module jdk.compiler export.
2. Mọi class public bên trong module jdk.compiler đều có thể import? **Không.** JPMS xét cả exports của module. Một class public ở package không export vẫn không được ứng dụng khác dùng qua compile-time access bình thường.

## 3. java.compiler là hợp đồng, jdk.compiler là nhà cung cấp thực thi

Module **java.compiler** chứa những API chuẩn mà một công cụ có thể gọi để yêu cầu biên dịch hoặc triển khai annotation processing. Bản thân việc có API JavaCompiler **không có nghĩa mọi runtime image đều có compiler implementation**.

Trong JDK thông thường, module **jdk.compiler** cung cấp một implementation của compiler, và javac là công cụ dòng lệnh dùng hệ thống biên dịch đó. Nếu ứng dụng chạy trên một runtime image được tinh giản không có compiler provider, câu lệnh sau có thể trả null:

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
~~~

Vì vậy mã đúng nên kiểm tra null và đưa ra thông báo khi compiler không sẵn có, thay vì giả định mọi JVM đều có javac.

### Cách đọc module descriptor

Trên JDK có các module liên quan, có thể kiểm tra:

~~~sh
java --describe-module java.compiler
java --describe-module jdk.compiler
~~~

Trong kết quả, tìm các package được export và quan hệ requires/provides. Với JDK 17+ thông dụng, java.compiler export các package javax.tools, javax.annotation.processing và javax.lang.model; jdk.compiler export các package com.sun.source.tree, com.sun.source.util và có implementation phục vụ JavaCompiler.

Một số package nội bộ com.sun.tools.javac.* có thể được **qualified export** cho một số module JDK nhất định, nhưng điều đó **không** biến chúng thành exports chung cho ứng dụng classpath hay mọi named module. Cũng không nên coi danh sách qualified exports ở một phiên bản JDK là hợp đồng ổn định cho bản mới.

### Module descriptor khi tạo công cụ có tên module

Nếu bạn tạo một explicit named module chỉ dùng javax.tools và các API chuẩn khác trong java.compiler, module-info.java có thể khai báo:

~~~java
module demo.compiler.client {
    requires java.compiler;
}
~~~

Đây là một đoạn descriptor minh họa; để build cần bố trí source/module path phù hợp.

Nếu công cụ còn chủ động sử dụng com.sun.source.*, nó cần đọc **jdk.compiler**, chẳng hạn:

~~~java
module demo.javac.inspector {
    requires java.compiler;
    requires jdk.compiler;
}
~~~

Điểm mấu chốt là quan hệ **requires** và package **exports** đều quan trọng. Thêm requires jdk.compiler **không cho phép** gọi mọi com.sun.tools.javac.* chưa được export.

## 4. javax.tools.JavaCompiler giải quyết bài toán gì?

javax.tools.JavaCompiler là giao diện công khai tiêu chuẩn để yêu cầu một compiler biên dịch chương trình. Bạn có thể cung cấp source qua file hoặc JavaFileObject, options, file manager, diagnostic listener và nhận một CompilationTask.

Các thành phần chính:

| API | Vai trò |
| --- | --- |
| ToolProvider.getSystemJavaCompiler() | Lấy system Java compiler nếu có |
| JavaCompiler.getTask(...) | Tạo một nhiệm vụ compilation |
| JavaCompiler.CompilationTask.call() | Thực hiện compilation và trả Boolean |
| JavaFileObject | Trừu tượng hóa tệp source hoặc class |
| SimpleJavaFileObject | Base class thuận tiện để tạo JavaFileObject tùy chỉnh |
| StandardJavaFileManager | Quản lý vị trí/tệp tiêu chuẩn, thường sử dụng try-with-resources |
| DiagnosticCollector | Nhận các Diagnostic để ứng dụng xử lý có cấu trúc |
| Diagnostic.Kind | Phân biệt ERROR, WARNING, NOTE và các loại diagnostic khác |
| JavaCompiler.getStandardFileManager(...) | Lấy file manager tiêu chuẩn từ compiler |

Thông thường, khi muốn viết ứng dụng kiểm thử mã nguồn, IDE integration ở mức compile, hoặc một công cụ nhận Java source rồi tạo .class, đây là điểm vào ổn định hơn so với gọi trực tiếp lớp internal JavacTool.

### Ưu điểm của gọi qua interface

~~~text
Code ứng dụng
     |
     v
javax.tools.JavaCompiler
     |
     +-- javac implementation trong JDK
     |
     +-- implementation khác nếu môi trường cung cấp phù hợp
~~~

Ứng dụng ràng buộc vào **hợp đồng JavaCompiler**, không vào constructor hoặc field nội bộ của javac. Khi compiler thay đổi thuật toán nội bộ, code chỉ sử dụng API chuẩn thường ít bị tác động hơn.

Cần phân biệt rõ: **chính giao diện là chuẩn** nhưng các options truyền vào getTask có thể mang tính **compiler-specific**. Chẳng hạn nhiều tùy chọn javac được công cụ javac hỗ trợ, nhưng không phải mọi JavaCompiler implementation bắt buộc nhận tất cả lựa chọn của javac. Kiểm tra compiler provider và options trước khi dựa vào hành vi đặc thù.

## 5. Dự án Java 17: biên dịch source trong bộ nhớ

Ví dụ này dùng **chỉ API Java SE** và các lớp java.* chuẩn; không import com.sun.tools.javac.*. Nó biên dịch một class Java hợp lệ từ String, phát hiện source sai cú pháp bằng DiagnosticCollector và kiểm tra .class đã được tạo.

Tạo thư mục:

~~~text
compiler-api-lab/
└── CompilerApiDemo.java
~~~

### Tệp CompilerApiDemo.java hoàn chỉnh

~~~java
import java.io.IOException;
import java.io.StringWriter;
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

public final class CompilerApiDemo {
    private static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source(String qualifiedName, String code) {
            super(URI.create("string:///" + qualifiedName.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    private static boolean compile(JavaCompiler compiler, Path output,
            String name, String code,
            DiagnosticCollector<JavaFileObject> collector) throws IOException {
        try (StandardJavaFileManager files =
                compiler.getStandardFileManager(
                        collector, Locale.ROOT, StandardCharsets.UTF_8)) {
            JavaCompiler.CompilationTask task = compiler.getTask(
                    new StringWriter(), files, collector,
                    List.of("--release", "17", "-proc:none",
                            "-d", output.toString()),
                    null, List.of(new Source(name, code)));
            return Boolean.TRUE.equals(task.call());
        }
    }

    public static void main(String[] args) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        System.out.println("Compiler found: " + (compiler != null));
        if (compiler == null) {
            return;
        }

        Path output = Path.of("build", "classes");
        Files.createDirectories(output);

        String validCode = "package demo.gen; public class Hello {"
                + " public static String text() { return \"Hello\"; } }";
        String invalidCode = "package demo.gen; public class Broken {"
                + " public static void test() { int x = ; } }";

        DiagnosticCollector<JavaFileObject> goodDiagnostics =
                new DiagnosticCollector<>();
        boolean valid = compile(compiler, output,
                "demo.gen.Hello", validCode, goodDiagnostics);
        System.out.println("Valid compilation: " + valid);
        System.out.println("Hello.class exists: "
                + Files.isRegularFile(
                        output.resolve("demo/gen/Hello.class")));

        DiagnosticCollector<JavaFileObject> badDiagnostics =
                new DiagnosticCollector<>();
        boolean invalid = compile(compiler, output,
                "demo.gen.Broken", invalidCode, badDiagnostics);
        System.out.println("Invalid compilation: " + invalid);

        boolean errorPresent = badDiagnostics.getDiagnostics().stream()
                .anyMatch(d -> d.getKind() == Diagnostic.Kind.ERROR);
        System.out.println("Error diagnostic present: " + errorPresent);
    }
}
~~~

Đây là một chương trình Java 17 hoàn chỉnh có public class trùng tên file. Nó tạo thư mục build/classes trong project khi chạy. Mã nguồn dùng String được cung cấp cho compiler qua Source extends SimpleJavaFileObject; vì vậy không phải ghi Hello.java và Broken.java ra đĩa trước.

### Biên dịch và chạy chương trình điều khiển compiler

Từ gốc compiler-api-lab, tạo output cho class CompilerApiDemo. Chọn một lệnh:

~~~bash
# Bash (Linux/macOS)
mkdir -p out
~~~

~~~powershell
# PowerShell (Windows)
New-Item -ItemType Directory -Path out -Force | Out-Null
~~~

Sau đó:

~~~sh
javac --release 17 -encoding UTF-8 -d out CompilerApiDemo.java
java -cp out CompilerApiDemo
~~~

**Stdout chính xác khi chạy trên JDK 17+ có system javac và quyền ghi project:**

~~~text
Compiler found: true
Valid compilation: true
Hello.class exists: true
Invalid compilation: false
Error diagnostic present: true
~~~

Nếu runtime image không có compiler provider, dòng đầu là false và chương trình kết thúc sớm; trong môi trường đó bạn không nên kỳ vọng bốn dòng tiếp theo.

### Vì sao output đáng tin?

- ToolProvider trả đối tượng có kiểu JavaCompiler hoặc null; code kiểm tra trước khi gọi.
- SourceFile dùng URI dạng string:///demo/gen/Hello.java và Kind.SOURCE nên compiler biết tên file nguồn logic.
- JavaCompiler.getTask nhận một đơn vị nguồn, file manager, options, diagnostics và tạo task.
- --release 17 yêu cầu javac dùng mức ngôn ngữ/API và bytecode đích Java 17; -proc:none tắt annotation processing vì ví dụ chỉ kiểm tra Compiler API.
- StandardJavaFileManager được đóng tự động bởi try-with-resources.
- Valid source tạo build/classes/demo/gen/Hello.class. Compiler trả Boolean.TRUE khi thành công.
- Invalid source có int x = ; nên cú pháp không hợp lệ; compile trả false và DiagnosticCollector nhận ít nhất một ERROR.
- Demo không giả định **số lượng lỗi, dòng thông báo chính xác hoặc tên class implementation** của compiler. Những chi tiết đó có thể thay đổi theo JDK.

### Tại sao không in compiler.getClass().getName() làm kết quả chuẩn?

Dòng:

~~~java
System.out.println(compiler.getClass().getName());
~~~

có thể tiết lộ implementation cụ thể, ví dụ tên class của javac. Đây chỉ là thông tin chẩn đoán; **đừng dùng tên implementation để viết nhánh nghiệp vụ** hoặc kỳ vọng kết quả ổn định giữa compiler/JDK khác nhau. Giao diện JavaCompiler mới là kiểu bạn nên dùng.

### Không cần Reflection để gọi compiler

Nếu đã có JavaCompiler, gọi getTask và call trực tiếp. Đừng gọi Class.forName để tìm một class nội bộ rồi reflective invoke method của nó chỉ vì thấy implementation trong một stack trace.

## 6. Những điểm cần hiểu sâu về JavaCompiler API

### Một CompilationTask không phải một tiến trình javac độc lập

CompilationTask đại diện một công việc biên dịch mà compiler implementation thực hiện. Trong ví dụ, chương trình gọi task.call() đồng bộ. Nó không yêu cầu spawn một tiến trình hệ điều hành mới hay chạy lệnh shell javac. Tuy nhiên implementation có thể dùng tài nguyên nội bộ tùy ý; không nên tự giả định hiệu suất hoặc tính độc lập thread mà API không cam kết.

**Task chỉ nên thực hiện theo hợp đồng một lần.** Nếu muốn compile source mới, hãy tạo một task mới. Tương tự, xử lý lifecycle của file manager đúng cách.

### DiagnosticCollector có cấu trúc

Khi javac báo lỗi:

~~~java
for (Diagnostic<? extends JavaFileObject> diagnostic
        : badDiagnostics.getDiagnostics()) {
    System.out.println(diagnostic.getKind());
}
~~~

Đây là đoạn minh họa **chèn bên trong main sau lượt compile lỗi**, không phải một tệp Java độc lập. Diagnostic còn cung cấp source, line, column, code, message tùy compiler. Khi hiển thị cho người học, có thể dùng getMessage(Locale), getLineNumber() và getSource() phù hợp. Không cứng hóa việc mọi diagnostic đều có vị trí nguồn, vì một số lỗi thuộc configuration không gắn vào file cụ thể.

### StandardJavaFileManager và JavaFileObject

File manager là tầng đọc/ghi JavaFileObject. Bạn có thể dùng một file manager tiêu chuẩn để xử lý source files từ đĩa, hoặc cung cấp JavaFileObject từ bộ nhớ. Để điều khiển tinh vi hơn, JavaFileManager có thể được bọc bởi ForwardingJavaFileManager; nhưng đó là **mở rộng qua giao diện chuẩn**, vẫn không đòi hỏi gọi trực tiếp com.sun.tools.javac.util.Context.

### Cẩn trọng khi biên dịch nguồn không đáng tin

Dù example chỉ compile một String, đừng nhầm compilation thành **sandbox bảo mật**. Một số compiler plugins hoặc annotation processors có thể thực thi code trong build; compiler có thể đọc/ghi file theo quyền process. Với source không đáng tin, hãy dùng cô lập ở cấp hệ điều hành/container, kiểm soát options, output directory và dependency; bản thân JavaCompiler API không cung cấp sandbox.

## 7. Tree API công khai của JDK: com.sun.source.*

Nhiều công cụ cần **xem AST** chứ không chỉ biết compilation success. JDK cung cấp các package công khai, nổi bật:

- **com.sun.source.tree**: các interface mô tả cây cú pháp, ví dụ Tree, CompilationUnitTree, ClassTree, MethodTree, VariableTree.
- **com.sun.source.util**: các utility API như JavacTask, Trees, TreePath, TreeScanner, TreePathScanner, TaskEvent, TaskListener.

Các package này được module **jdk.compiler export công khai**. Chúng không nên bị đánh đồng với com.sun.tools.javac.tree.JCTree chỉ vì có tiền tố com.sun.

**Phân biệt chính xác:**

- com.sun.source.*: API được JDK công bố để truy cập mô hình cây cú pháp của javac. **JDK-specific**, không đồng nhất với Java SE javax.tools interface.
- com.sun.tools.javac.*: phần lớn là implementation nội bộ, dùng bởi chính javac và một số công cụ JDK được cấp qualified exports; không phải interface mở rộng ổn định cho ứng dụng bình thường.

### Ví dụ đọc AST mà không chạm JCTree

Tại cùng thư mục compiler-api-lab, tạo **TreeApiDemo.java**:

~~~java
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.util.JavacTask;
import java.util.List;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class TreeApiDemo {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            System.out.println("No system compiler");
            return;
        }

        try (StandardJavaFileManager files =
                compiler.getStandardFileManager(null, null, null)) {
            Iterable<? extends JavaFileObject> inputs =
                    files.getJavaFileObjectsFromStrings(
                            List.of("CompilerApiDemo.java"));

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, files, null,
                    List.of("-proc:none"), null, inputs);

            if (!(task instanceof JavacTask)) {
                System.out.println("JavacTask unavailable");
                return;
            }

            for (CompilationUnitTree unit
                    : ((JavacTask) task).parse()) {
                System.out.println("Top-level declarations: "
                        + unit.getTypeDecls().size());
            }
        }
    }
}
~~~

Biên dịch, chạy từ gốc compiler-api-lab (out đã tồn tại):

~~~sh
javac --release 17 -encoding UTF-8 -d out TreeApiDemo.java
java -cp out TreeApiDemo
~~~

**Stdout trên javac/JDK 17+ dùng cho bài:**

~~~text
Top-level declarations: 1
~~~

CompilerApiDemo.java có một khai báo top-level class; các nested classes nằm bên trong nên không làm tăng số top-level declarations. Lệnh parse() đọc cấu trúc syntax; ví dụ không gọi CompilationTask.call() để tạo thêm .class.

### Vì sao phải kiểm tra instanceof JavacTask?

JavaCompiler.CompilationTask là interface chuẩn. Không có hợp đồng rằng **mọi compiler implementation** đều trả một object triển khai com.sun.source.util.JavacTask. Với system javac hiện đại, cast này dùng được; nếu muốn viết công cụ có thể chạy trên compiler implementation khác, hãy xử lý trường hợp JavacTask unavailable như ví dụ.

### Giới hạn của API cây cú pháp

Tree API giúp đi qua các nodes, nhận biết vị trí hoặc cấu trúc source; nó không cam kết các field, layout bộ nhớ, optimization flags hay implementation classes bên trong javac. Nếu cần kiểm tra kiểu tương ứng từng Tree, có thể dùng Trees, TreePath và javax.lang.model phù hợp. Không giả định object đại diện Tree có thể ép kiểu sang JCTree.

**Công khai không đồng nghĩa Java SE portable:** Tree API là public JDK API, nhưng sự hiện diện của jdk.compiler và hành vi của hệ thống javac là điều kiện môi trường của công cụ.

## 8. Khi nào cần javax.annotation.processing và javax.lang.model?

Nếu mục tiêu là **xem khai báo/kiểu và sinh code trong quá trình biên dịch**, nhiều bài toán có thể giải quyết hoàn toàn bằng annotation processing chuẩn.

Một processor thường mở rộng:

~~~java
public final class MyProcessor
        extends javax.annotation.processing.AbstractProcessor {
    @Override
    public boolean process(
            java.util.Set<? extends javax.lang.model.element.TypeElement> types,
            javax.annotation.processing.RoundEnvironment round) {
        return false;
    }
}
~~~

Đây là **khung minh họa**, không phải một processor được cấu hình đầy đủ hoặc class runnable (cần package, annotation types và source version được hỗ trợ, init/config nếu cần). Nó nhấn mạnh kiểu trả về của process và hai tham số chuẩn.

Bộ API liên quan:

| Nhu cầu | API chuẩn nên ưu tiên |
| --- | --- |
| Lấy các elements được annotate | RoundEnvironment.getElementsAnnotatedWith(...) |
| Kiểm tra class/interface/field/method | javax.lang.model.element |
| Kiểm tra kiểu/generics/subtype | javax.lang.model.type và javax.lang.model.util.Types |
| Tra cứu package, type, annotation | javax.lang.model.util.Elements |
| Sinh source hoặc resource mới | javax.annotation.processing.Filer |
| Báo lỗi biên dịch | javax.annotation.processing.Messager |
| Đọc compiler options -A | ProcessingEnvironment.getOptions() |

Khác với Reflection runtime, language model biểu diễn code đang compile. Với type đang chưa có .class, dùng TypeElement/TypeMirror hợp lý hơn việc cố Class.forName.

**Ranh giới API chuẩn:** javax.annotation.processing được thiết kế để đọc model, phát diagnostics và sinh output mới. Nó không cung cấp hợp đồng chung để sửa mọi node AST hay chèn lệnh tùy ý vào một method đã viết. Một số công cụ cụ thể làm việc này bằng compiler internals, nhưng đó là chiến lược khác với annotation processing chuẩn.

## 9. Lớp nào thực sự nội bộ?

Một số tên mà bạn có thể gặp khi đọc source javac, stack trace hoặc dự án tích hợp compiler sâu:

| Package/class | Vai trò trong implementation | Vì sao tránh phụ thuộc trực tiếp? |
| --- | --- | --- |
| com.sun.tools.javac.api.JavacTool | Một implementation cụ thể của JavaCompiler | Tên/cách khởi tạo và member nội bộ không phải contract JavaCompiler |
| com.sun.tools.javac.tree.JCTree | Cây AST implementation riêng của javac | Kiểu node và field có thể đổi giữa bản JDK |
| com.sun.tools.javac.util.Context | Service/context registry nội bộ | Lifecycle và keys phụ thuộc javac |
| com.sun.tools.javac.comp.Attr | Phần xử lý attribution/type checking | Implementation detail, không phải extension interface chuẩn |
| com.sun.tools.javac.main.JavaCompiler | Thành phần orchestration nội bộ javac | Dễ phụ thuộc vào trình tự pha và trạng thái compiler |

Các class nêu trên **không phải cùng mức cam kết với javax.tools.JavaCompiler hoặc com.sun.source.tree.Tree**. Kể cả một class nội bộ hiện là public, module jdk.compiler vẫn có thể không export package đó cho ứng dụng.

### Kiểm tra bằng một ví dụ thất bại có chủ đích

Tạo **InternalProbe.java**:

~~~java
import com.sun.tools.javac.api.JavacTool;

public final class InternalProbe {
    JavacTool tool;
}
~~~

**Đây là ví dụ cố tình không biên dịch bằng cấu hình bình thường.** Nó không phải một phần của chương trình chạy thành công.

Trên JDK 17+ có jdk.compiler, thử:

~~~sh
javac InternalProbe.java
~~~

Diagnostic có thể ghi đại ý:

~~~text
package com.sun.tools.javac.api is not visible
(package com.sun.tools.javac.api is declared in module jdk.compiler,
 which does not export it to the unnamed module)
~~~

Khi dùng:

~~~sh
javac --release 17 InternalProbe.java
~~~

một javac mới có thể hiển thị **package ... does not exist** thay vì **is not visible**, vì --release giới hạn tập platform APIs được phép thấy. **Đừng lấy nguyên văn diagnostic này làm định nghĩa API:** cả hai trường hợp đều cho thấy source code đang phụ thuộc vào API không nằm trong hợp đồng compile được phép.

Nếu muốn dùng interface chuẩn thay vì lớp nội bộ:

~~~java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
~~~

Snippet trên là các dòng minh họa trong một phương thức hợp lệ; không phải class hoàn chỉnh. Cách viết này sử dụng hợp đồng API công khai và không cần biết compiler implementation đang dùng tên gì.

### Vì sao public class vẫn bị báo not visible?

Một package ở module khác chỉ truy cập được nếu **module readability** và **package exports** cùng cho phép. Class có modifier public là điều kiện riêng, không vượt qua ranh giới module. Java module jdk.compiler export công khai com.sun.source.* nhưng không export chung toàn bộ com.sun.tools.javac.*.

Một số package nội bộ được qualified export tới các module JDK được chọn. Điều đó phục vụ thiết kế của chính JDK, không biến API thành public extension point cho mọi ứng dụng.

## 10. --add-exports và --add-opens không phải giải pháp thiết kế bền vững

Khi tìm kiếm cách dùng JCTree hoặc JavacTool, bạn có thể gặp các command-line options:

- **--add-exports**: bổ sung export package ở runtime hoặc compile-time theo cấu hình, cho phép truy cập các public types ở một package vốn không được export tới module caller.
- **--add-opens**: bổ sung quyền mở package cho deep reflection khi chạy.
- **--add-reads**: bổ sung quan hệ đọc giữa modules khi cần.

Các lựa chọn trên phục vụ nhiều tình huống tương thích, migration hoặc gỡ lỗi đặc biệt. Nhưng chúng **không tạo cam kết binary/source compatibility** đối với field/method của compiler implementation.

Ví dụ nếu ép ứng dụng phụ thuộc vào JCTree, chỉ cần JDK mới thay đổi cấu trúc AST nội bộ, constructor, field hoặc method là build có thể thất bại, dù --add-exports vẫn được truyền chính xác.

**Không nhầm --add-opens với --add-exports:** quyền reflective access không tự làm một source import hợp lệ; và quyền import một public class không đồng nghĩa có quyền phản xạ sâu vào private field.

**Lưu ý --release:** javac không cho phép một số dạng mở rộng khả năng truy cập internal platform modules đồng thời với --release. Vì vậy việc “thêm --add-exports cho hết lỗi” có thể không hoạt động với toolchain đang khóa mục tiêu Java 17. Cách đúng cho bài tập của chúng ta là **không phụ thuộc internals**.

## 11. Vì sao code gọi internals dễ hỏng khi nâng cấp JDK?

### Source compatibility

API nội bộ có thể đổi constructor, method names hoặc types. Code Java nguồn của plugin biên dịch được trên JDK cũ có thể lỗi ngay khi compile trên JDK mới.

### Binary compatibility

Plugin đã biên dịch có thể chứa method/field references trỏ vào member nội bộ. Nếu JDK mới đổi binary signature hoặc layout liên quan, runtime có thể báo NoSuchMethodError, NoSuchFieldError, IllegalAccessError hoặc lỗi liên kết khác. Không có lời bảo đảm loại lỗi luôn giống nhau.

### Runtime access

Trong một JDK có module system và strong encapsulation, code có thể compile do flags đặc biệt nhưng thất bại khi chạy nếu launcher/test runner không cấp quyền tương ứng. Các công cụ IDE/Gradle/Maven fork JVM riêng cũng cần cấu hình đúng process; đừng giả định flags của javac command được chuyển sang process chạy plugin.

### Tính khả chuyển

Java SE chuẩn định nghĩa javax.tools API, không yêu cầu mọi Java compiler implementation đều có class com.sun.tools.javac.api.JavacTool. Khi code phụ thuộc một implementation cụ thể, nó tự giới hạn runtime/toolchain hỗ trợ.

### Bảo trì và bảo mật build

Công cụ can thiệp implementation compiler có thể chạy với quyền của build process, ảnh hưởng cache, diagnostics và khả năng debug. Một plugin mới hoặc jar annotation processor mới cũng là dependency được thực thi trong build: chỉ dùng nguồn đáng tin, version đã kiểm thử và công bố hỗ trợ JDK rõ ràng.

## 12. Khi nào công cụ nên dùng từng tầng API?

| Bạn muốn làm gì? | Lựa chọn khuyến nghị | Ghi chú |
| --- | --- | --- |
| Biên dịch Java source từ ứng dụng | javax.tools.JavaCompiler | Portable contract; kiểm tra provider null |
| Lấy diagnostics có line/column | DiagnosticCollector và Diagnostic | Dữ liệu có cấu trúc, không parse stderr bằng regex |
| Đọc class/method/field declarations lúc compile | javax.lang.model qua annotation processing | Phù hợp model ngôn ngữ |
| Sinh tệp source mới từ annotation | AbstractProcessor + Filer | Không sửa source input đang có |
| Đi qua cú pháp if/for/method/class | com.sun.source.tree + TreePathScanner | JDK javac-specific public API |
| Theo dõi events parse/analyze/generate | com.sun.source.util.TaskListener | Giới hạn trong JDK compiler public utility APIs |
| Sửa node AST nội bộ hoặc thay đổi attribution | Không có API Java SE chung tương đương | Cân nhắc đổi kiến trúc; nếu dùng internals phải khóa toolchain/test riêng |
| Gọi compiler implementation qua lớp concrete | Không dùng nếu JavaCompiler interface đủ | Tránh JavacTool trực tiếp |

**Điểm quyết định:** chọn interface ở mức cao nhất có thể đáp ứng yêu cầu. Một annotation processor không cần JCTree nếu chỉ đọc TypeElement, xem TypeMirror, validate và generate Java source. Một ứng dụng “compile code” không cần biết javac dùng Context hay Attr.

### AST public API có đủ để sửa AST không?

Tree API công khai chủ yếu hỗ trợ **quan sát/duyệt cây**. Nó không cung cấp một giao diện Java SE chuẩn để đổi mọi Tree node, tái cấu trúc statement và bắt compiler dùng cây đã sửa. Nếu muốn refactor source, nhiều công cụ chọn phân tích cú pháp rồi tạo **văn bản source mới** hoặc dùng thư viện refactoring chuyên dụng, thay vì thao tác field nội bộ của JCTree.

## 13. Một góc nhìn về JSR 199 và JSR 269

Hai chuẩn thường được nhắc tới trong hệ sinh thái compiler:

- **JSR 199 — Java Compiler API**: cơ sở của javax.tools.JavaCompiler, JavaFileManager, JavaFileObject và DiagnosticListener; giúp ứng dụng tích hợp compilation như một tác vụ có cấu trúc.
- **JSR 269 — Pluggable Annotation Processing API**: cơ sở của javax.annotation.processing và language model liên quan; giúp compiler chạy processors trong các rounds.

Chúng giải quyết hai bài toán khác nhau:

~~~text
Ứng dụng A muốn tự gọi compiler
    -> JavaCompiler.getTask(...).call()
             |
             v
            javac
             |
             +-- Có thể chạy annotation processors
             |       -> AbstractProcessor.process(...)
             |       -> Filer sinh source mới
             |
             +-- Biên dịch source và generated source thành .class
~~~

Việc JavaCompiler API cho phép caller yêu cầu compilation **không có nghĩa caller tự động trở thành annotation processor**. Ngược lại, một annotation processor được compiler nạp **không nhất thiết phải tự tạo và gọi một JavaCompiler mới** để sinh file; nó dùng Filer và rounds của invocation hiện tại.

### Sử dụng com.sun.source cùng API chuẩn

Một công cụ chạy trên JDK có javac có thể:

1. Dùng javax.tools.JavaCompiler để tạo task.
2. Nếu task hỗ trợ JavacTask, dùng API công khai com.sun.source.util.JavacTask để parse hoặc quan sát source.
3. Dùng com.sun.source.tree để duyệt các node.
4. Dùng javax.lang.model / Trees khi cần liên hệ AST với model kiểu.

Đó là kết hợp **API chuẩn + JDK public APIs**, không phải bằng chứng rằng nên tiếp tục cast object tree thành com.sun.tools.javac.tree.JCTree.

## 14. Các lỗi thường gặp khi chuyển hướng từ internals sang API công khai

### Lỗi A — Cannot find symbol trong javax.tools

Người viết code import JavaCompiler nhưng gọi method riêng của JavacTool, khiến compiler báo không có method. Đây là dấu hiệu bạn đang dùng một chức năng **không thuộc JavaCompiler contract**. Hãy kiểm tra API chuẩn thực sự hỗ trợ điều gì; nếu cần javac-specific Tree API, dùng interface công khai tương ứng thay vì ép JavaCompiler thành implementation nội bộ.

### Lỗi B — package com.sun.tools.javac.* is not visible

Không phải lỗi do thiếu Maven dependency. Package có thể tồn tại ngay trong jdk.compiler nhưng không export cho module caller. Đừng thêm JAR copy của module JDK vào classpath. Hãy thay bằng javax.tools/com.sun.source hoặc đổi thiết kế.

### Lỗi C — getSystemJavaCompiler() trả null

Chương trình có thể đang chạy trên runtime image không có compiler provider. Kiểm tra JDK/runtime image và module jdk.compiler. Nếu công cụ bắt buộc compile Java, hãy tài liệu hóa yêu cầu **JDK với compiler implementation** thay vì cast null.

### Lỗi D — ClassCastException khi ép CompilationTask sang JavacTask

Không phải compiler provider nào cũng hỗ trợ JavacTask. Kiểm tra instanceof; nếu tính năng AST chỉ có trên javac, công bố toolchain yêu cầu javac, hoặc có phương án fallback khi backend khác.

### Lỗi E — IllegalAccessError / InaccessibleObjectException

Code phụ thuộc vào package nội bộ, hoặc reflection vào nó, nhưng module flags không cho phép tại runtime. Đây là ranh giới module. --add-exports/--add-opens có thể thay đổi kết quả trong môi trường thử nghiệm nhưng không tạo public API ổn định.

### Lỗi F — NoSuchMethodError sau nâng cấp JDK

Một thư viện/plugin đã được biên dịch với class nội bộ phiên bản cũ có thể gọi method mà bản JDK mới không còn giữ tương thích. Điều tra **phiên bản JDK + plugin + bytecode dependency**, không mặc định đây là lỗi logic source ứng dụng.

### Lỗi G — Biên dịch cùng source nhưng diagnostic khác

JavaCompiler interface chuẩn cho phép nhiều compiler implementations, các messages và vị trí/cách diễn đạt diagnostic có thể khác nhau. Hãy kiểm tra Diagnostic.Kind, code, source/line khi có; đừng phụ thuộc vào toàn bộ câu tiếng Anh được in ra.

## 15. Thiết kế một tầng compiler integration ổn định

Gợi ý kiến trúc:

~~~text
Tool application
       |
       v
CompilationService (interface do ứng dụng định nghĩa)
       |
       +-- StandardCompilationService
       |       javax.tools.JavaCompiler
       |       DiagnosticCollector
       |       JavaFileManager
       |
       +-- JavacInspectionService (tính năng tùy chọn)
               com.sun.source.util.JavacTask
               com.sun.source.tree.*
~~~

Với những chức năng cần javac-specific, đặt chúng trong một module/component nhỏ có tên rõ, viết test trên các phiên bản JDK cần hỗ trợ và có logic kiểm tra capability. Đừng để nội bộ compiler len vào hàng trăm class nghiệp vụ.

**Nếu bắt buộc dùng com.sun.tools.javac internals** cho một công cụ chuyên biệt, hãy coi đó là rủi ro kiến trúc có chủ đích: khóa phạm vi JDK được hỗ trợ, test matrix mỗi lần nâng cấp, ghi rõ flags JVM/compiler, và dự kiến các thay đổi của implementation có thể buộc sửa code. Nó không phải con đường mặc định cho chương trình cần portable compiler integration.

### Các nguyên tắc cụ thể

1. **Program to interface:** dùng JavaCompiler, JavaFileObject, DiagnosticListener và standard file manager.
2. **Handle absence of provider:** getSystemJavaCompiler() có thể null.
3. **Treat options as capabilities:** không giả định một backend bất kỳ nhận mọi flag riêng của javac.
4. **Isolate JDK-specific APIs:** sử dụng com.sun.source.* trong tầng cần AST; không ép xuống JCTree.
5. **Test generated output:** verify .class được tạo và chạy được theo mục tiêu, không chỉ xem task.call()==true.
6. **Surface diagnostics:** trả thông tin source/line/kind thay vì chỉ Boolean.
7. **Keep classpath/module path explicit:** compile task có thể phụ thuộc vào library artifacts; hạn chế dùng môi trường không xác định.
8. **Do not compile arbitrary untrusted code with broad permissions:** compiler và plugins là một phần của build attack surface.

## 16. Bài tập thực hành

**Bài 1 — Phân loại API.** Xếp JavaCompiler, DiagnosticCollector, AbstractProcessor, TypeMirror, JavacTask, CompilationUnitTree, JavacTool, JCTree và Context vào ba nhóm: Java SE chuẩn, JDK public compiler APIs và javac internals. Giải thích tiêu chí bằng module exports và tài liệu, không chỉ tên package.

**Bài 2 — Compiler API.** Chạy CompilerApiDemo. Giải thích vì sao một String source có thể được compile thành .class dù không có Hello.java trên disk trước compile, và vì sao Invalid compilation là false.

**Bài 3 — Diagnostics.** Mở rộng CompilerApiDemo để in Diagnostic.Kind, source name và line number khi có ERROR. Không test bằng cách so toàn bộ câu lỗi tiếng Anh cố định.

**Bài 4 — Runtime image.** Đề xuất ứng xử khi ToolProvider.getSystemJavaCompiler() là null. Ứng dụng nên thông báo gì và yêu cầu môi trường chạy thế nào?

**Bài 5 — AST.** Chạy TreeApiDemo. Vì sao kết quả Top-level declarations là 1 dù CompilerApiDemo chứa nested class Source? Nêu khác biệt top-level declarations và member declarations.

**Bài 6 — API nội bộ.** Thử compile InternalProbe không có flags đặc biệt. Đọc diagnostic từ javac. Tại sao JavacTool là class public mà source vẫn không thể import ở chế độ bình thường?

**Bài 7 — Modules.** Viết descriptor cho công cụ dùng javax.tools. Nếu công cụ muốn import com.sun.source.util.JavacTask, cần thêm yêu cầu module nào?

**Bài 8 — Thiết kế lại plugin.** Một plugin hiện dùng JCTree chỉ để tìm các method được annotate và sinh một class phụ trợ. Hãy đề xuất chuyển sang AbstractProcessor, RoundEnvironment, TypeElement, Filer và Messager. Phần nào không cần API nội bộ nữa?

**Bài 9 — Khả chuyển.** Một JavaCompiler implementation khác trả CompilationTask không phải JavacTask. Chương trình nên làm gì nếu chỉ cần compile? Và nên làm gì nếu tính năng AST là bắt buộc?

**Bài 10 — Nâng cấp JDK.** Khi plugin nội bộ gặp NoSuchFieldError sau nâng JDK, xác định các dữ liệu cần thu thập: phiên bản plugin/JDK, flags, tên class/member, dependency graph, và test phiên bản tương thích.

## 17. Checklist trước khi dùng compiler APIs

- Hiểu java.compiler chứa các hợp đồng Java SE cho compiler, diagnostics, annotation processing và language model.
- Hiểu jdk.compiler cung cấp implementation của javac và các API cây cú pháp công khai của JDK.
- Biết com.sun.source.* không đồng nghĩa com.sun.tools.javac.*.
- Không nhầm public modifier với quyền truy cập xuyên qua module exports.
- Đã dùng JavaCompiler.getTask(...) và CompilationTask.call() trong ví dụ runnable.
- Đã kiểm tra ToolProvider.getSystemJavaCompiler() có thể null.
- Đã dùng DiagnosticCollector thay vì parse stderr để biết lỗi biên dịch.
- Đã dùng JavaFileObject cho source trong bộ nhớ và file manager có vòng đời rõ ràng.
- Đã biết JavacTask là JDK-specific API và không ép mọi CompilationTask thành JavacTask.
- Đã hiểu JCTree/Context/JavacTool là implementation details có rủi ro tương thích.
- Biết --add-exports và --add-opens không nâng một internal API thành Java SE API.
- Khi cần sinh nguồn từ annotation, ưu tiên JSR 269 và Filer.
- Khi cần quan sát AST, cân nhắc com.sun.source.tree/util trước internals.
- Có chiến lược test compile, diagnostics, output và JDK version trên toolchain được hỗ trợ.

### Tài liệu chuẩn để tìm hiểu thêm

- **Java SE 17 API**, module java.compiler: javax.tools.JavaCompiler, ToolProvider, JavaFileObject, StandardJavaFileManager, DiagnosticCollector; javax.annotation.processing; javax.lang.model.
- **JDK 17 API**, module jdk.compiler: com.sun.source.tree và com.sun.source.util (gồm JavacTask, Trees, TreePathScanner).
- **Java Platform Module System**: cách requires, exports và opens quyết định accessibility giữa modules.
- **JSR 199** và **JSR 269**: compiler API và annotation processing chuẩn.
- **javac documentation** của JDK đang dùng: options --release, -proc:none, -d, --module-path và các hạn chế khi dùng internal platform APIs.

**Kết luận:** javax.tools/annotation processing/language model là hợp đồng chuẩn dành cho công cụ Java; com.sun.source.* là API cây cú pháp công khai của JDK; còn com.sun.tools.javac.* là implementation nội bộ không có cùng cam kết hỗ trợ. Chọn tầng API theo đúng nhu cầu sẽ giúp công cụ tích hợp compiler dễ kiểm thử và ít hỏng hơn khi nâng cấp JDK.
