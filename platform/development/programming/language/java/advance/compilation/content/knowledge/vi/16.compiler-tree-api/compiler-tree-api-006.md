# Quan sát giai đoạn bằng TaskListener mà không sửa nội bộ compiler

## 1. Mục tiêu và ý tưởng chính

Khi tìm hiểu cách Java được biên dịch, ta thường muốn biết javac đã **phân tích cú pháp (parse)**, **đưa khai báo vào bảng ký hiệu (enter)**, **kiểm tra/thuộc tính kiểu (analyze)** và **sinh bytecode (generate)** ở những thời điểm nào. Có người giải quyết bằng cách import các lớp như com.sun.tools.javac.comp.Attr, com.sun.tools.javac.main.JavaCompiler hoặc sửa cây JCTree; cách đó phụ thuộc trực tiếp vào implementation nội bộ của javac và dễ hỏng khi nâng cấp JDK.

Java JDK cung cấp một phương án quan sát tốt hơn: **TaskListener** trong package com.sun.source.util, đi cùng **JavacTask** và **TaskEvent**. Đây là các **API công khai của JDK**, nằm trong module **jdk.compiler** và được export cho ứng dụng. Ta có thể đăng ký listener vào một tác vụ biên dịch javac để nhận callback mỗi khi một event bắt đầu hoặc kết thúc, **không sửa AST, không truy cập Context hoặc các pha nội bộ của compiler**.

Bài này hướng dẫn bạn:

- Nêu rõ ranh giới Java SE chuẩn, API javac công khai và lớp triển khai nội bộ.
- Hiểu JavacTask, TaskListener, TaskEvent.Kind và started/finished.
- Tự tạo một JavaCompiler.CompilationTask, kiểm tra có phải JavacTask, đăng ký listener trước khi chạy.
- Quan sát các event PARSE, ENTER, ANALYZE, GENERATE của một chương trình Java 17.
- Đọc CompilationUnitTree/TypeElement từ sự kiện đúng ngữ cảnh, hiểu callback có thể lặp và dữ liệu có thể null.
- Gỡ lỗi khi không thấy event, khi compiler gặp lỗi, khi dùng annotation processor hoặc project đa tệp.
- Biết TaskListener quan sát được điều gì và **không** được dùng để thay đổi implementation compiler.

Mục tiêu là **quan sát có căn cứ**, không tìm cách “can thiệp để javac chạy theo thứ tự mình muốn”.

## 2. TaskListener thuộc tầng API nào?

Để không nhầm mức ổn định, phân biệt ba nhóm:

| Nhóm | Ví dụ | Module | Mức cam kết |
| --- | --- | --- | --- |
| Java SE compiler API | javax.tools.JavaCompiler, ToolProvider, JavaFileObject, DiagnosticCollector | java.compiler | Giao diện chuẩn Java SE cho yêu cầu biên dịch và nhận diagnostic |
| Public JDK compiler API | com.sun.source.util.JavacTask, TaskListener, TaskEvent, Trees và com.sun.source.tree.* | jdk.compiler | API công khai được JDK export để quan sát/công cụ tích hợp javac |
| Internal javac implementation | com.sun.tools.javac.comp.Attr, com.sun.tools.javac.util.Context, com.sun.tools.javac.tree.JCTree | jdk.compiler | Chi tiết triển khai, nhiều package không được export cho ứng dụng thông thường |

**TaskListener không nằm trong javax.tools của Java SE**, nhưng nó cũng **không phải lớp nội bộ cần --add-exports** như nhiều phần của com.sun.tools.javac.*.

Dấu hiệu cần kiểm tra là **tài liệu API, package được module export và hợp đồng sử dụng**, không chỉ tiền tố com.sun. Một package công khai của JDK vẫn có thể khiến code phụ thuộc vào javac thay vì mọi implementation JavaCompiler.

Sơ đồ:

~~~text
Ứng dụng công cụ học compiler
          |
          +-- javax.tools.JavaCompiler (API Java SE)
          |           |
          |           v
          |    CompilationTask
          |           |
          |      instanceof JavacTask?
          |           |
          |           v
          +-- com.sun.source.util.JavacTask
                         |
                         v
                  addTaskListener(...)
                         |
                         v
                  TaskListener
                  started(event)
                  finished(event)
                         |
                         v
                  Quan sát các Kind:
                  PARSE / ENTER / ANALYZE / GENERATE
~~~

Nhờ cách này, code của bạn được viết theo interface công khai. Bạn không cần gọi trực tiếp constructor của com.sun.tools.javac.api.JavacTool hoặc thao tác JCTree.

## 3. Ba interface/class cốt lõi

### JavacTask

com.sun.source.util.JavacTask là một dạng CompilationTask dành cho javac, có các chức năng như:

- addTaskListener(TaskListener): đăng ký listener quan sát các sự kiện.
- removeTaskListener(TaskListener): gỡ listener được đăng ký.
- parse(): yêu cầu parse nguồn ở ngữ cảnh tác vụ khi dùng API từng pha.
- analyze(): yêu cầu phân tích/kiểm tra khi sử dụng cách điều khiển pha công khai.
- generate(): yêu cầu sinh output từ tác vụ theo API tương ứng.
- getElements() và getTypes(): lấy dịch vụ mô hình ngôn ngữ liên quan để khảo sát khai báo/kiểu.

Trong ví dụ chính, ta chỉ dùng **addTaskListener** rồi gọi **task.call()** để chạy nguyên một tác vụ. Không trộn parse/analyze/generate thủ công với call() của cùng task khi không có kế hoạch điều khiển vòng đời rõ ràng.

**Quan trọng:** JavaCompiler.CompilationTask là giao diện chuẩn. Không phải mọi compiler implementation đều bảo đảm task của nó là JavacTask. Vì vậy ta dùng **instanceof** và thông báo không hỗ trợ nếu provider khác.

### TaskListener

com.sun.source.util.TaskListener cung cấp hai callback:

~~~java
@Override
public void started(TaskEvent event) {
    // Compiler thông báo một activity bắt đầu.
}

@Override
public void finished(TaskEvent event) {
    // Compiler thông báo activity kết thúc.
}
~~~

Listener được gọi trong hoạt động của compiler; các callback nên nhẹ, nhanh và không thực hiện công việc gây side effects không cần thiết. Không nên ép compiler vào một thứ tự pha khác bằng cách sửa trạng thái nội bộ từ callback.

### TaskEvent

TaskEvent chứa dữ liệu về sự kiện hiện tại. Các method thường dùng:

- getKind(): loại hoạt động compiler đang được thông báo.
- getCompilationUnit(): CompilationUnitTree nếu event có thông tin về compilation unit phù hợp.
- getSourceFile(): JavaFileObject của nguồn khi có.
- getTypeElement(): TypeElement liên quan trong một số event.

**Không mặc định mọi trường đều khác null.** Có event mang tính tổng thể, event chỉ liên quan một nguồn, event liên quan một type. Chỉ truy cập source file, cây cú pháp hoặc type khi giá trị thực sự được cung cấp; kiểm tra null trước.

## 4. Các event quan trọng và giới hạn diễn giải

TaskEvent.Kind cho biết *loại sự kiện*, không phải một timeline toàn cục bất biến. Các giá trị thường gặp:

| Kind | Ý nghĩa học tập | Điều không nên tự suy diễn |
| --- | --- | --- |
| COMPILATION | Hoạt động compilation ở cấp tác vụ | Không đồng nghĩa mọi loại callback chỉ xảy ra một lần |
| PARSE | Javac parse một compilation unit | Không chứng minh mọi lỗi cú pháp đã biến mất sau một event |
| ENTER | Đưa thông tin khai báo vào môi trường ký hiệu | Không đồng nghĩa kiểm tra kiểu toàn chương trình đã xong |
| ANALYZE | Phân tích/kiểm tra một khai báo kiểu hoặc đơn vị phù hợp | Không phải kết quả tối ưu hóa hay chỉ số hiệu suất |
| GENERATE | Tạo output cho kiểu/class tương ứng | Không bảo đảm chỉ có một event cho mỗi tệp nguồn |
| ANNOTATION_PROCESSING | Hoạt động annotation processing | Không bảo đảm processor thực sự tạo source mới |
| ANNOTATION_PROCESSING_ROUND | Một round annotation processing | Không đồng nghĩa một round chỉ chứa một annotation |

Không nên cố định một chuỗi “PARSE, rồi đúng một ENTER, rồi đúng một ANALYZE, rồi đúng một GENERATE” cho mọi project. Với nhiều source files, nested classes, processors sinh nguồn mới và compile errors, số lượng và thứ tự các callback có thể khác.

**Đặc biệt:** event GENERATE có thể xảy ra cho nhiều class trong cùng một source, còn ANALYZE có thể liên quan type. Tốt hơn là đếm/ghi loại sự kiện và đối tượng nguồn/kiểu liên quan, không coi số event chính xác là API contract.

### started và finished khác nhau ra sao?

- started(event): compiler thông báo một activity thuộc Kind tương ứng bắt đầu.
- finished(event): compiler thông báo activity kết thúc theo cơ chế reporting của javac.

Nhận finished(PARSE) có nghĩa là một activity parse đã được báo hoàn tất, **không có nghĩa toàn bộ compile đã thành công**. Chẳng hạn một file có thể được parse và enter rồi thất bại do lỗi kiểu; khi đó không nên kỳ vọng GENERATE cho class lỗi.

Callback được dùng cho **instrumentation/observation**, không phải cơ chế rollback, transaction, hoặc cơ hội thay thế implementation của compiler.

## 5. Dự án Java 17 hoàn chỉnh để quan sát các pha

Tạo thư mục:

~~~text
task-listener-lab/
├── TaskListenerDemo.java
├── out/               # Sau khi biên dịch công cụ
└── build/
    └── classes/       # Đầu ra do công cụ tạo khi chạy
~~~

Project chỉ cần **một file Java nguồn**. Nó biên dịch một class con tên demo.Hello từ chuỗi source trong bộ nhớ, lắng nghe các Kind và kiểm tra class file đã được sinh.

### Tệp TaskListenerDemo.java

~~~java
import com.sun.source.util.JavacTask;
import com.sun.source.util.TaskEvent;
import com.sun.source.util.TaskListener;
import java.io.IOException;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.EnumSet;
import java.util.List;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class TaskListenerDemo {
    private static final class Source extends SimpleJavaFileObject {
        private final String text;

        Source(String name, String text) {
            super(URI.create("string:///" + name.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.text = text;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return text;
        }
    }

    public static void main(String[] args) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            System.out.println("No system Java compiler");
            return;
        }

        Path output = Path.of("build", "classes");
        Files.createDirectories(output);

        String code = "package demo; public final class Hello {"
                + " public static int value() { return 42; } }";

        EnumSet<TaskEvent.Kind> finished =
                EnumSet.noneOf(TaskEvent.Kind.class);

        try (StandardJavaFileManager files =
                compiler.getStandardFileManager(
                        null, null, StandardCharsets.UTF_8)) {
            JavaCompiler.CompilationTask generic = compiler.getTask(
                    null, files, null,
                    List.of("--release", "17", "-proc:none",
                            "-d", output.toString()),
                    null, List.of(new Source("demo.Hello", code)));

            if (!(generic instanceof JavacTask task)) {
                System.out.println("JavacTask unavailable");
                return;
            }

            task.addTaskListener(new TaskListener() {
                @Override
                public void started(TaskEvent event) {
                }

                @Override
                public void finished(TaskEvent event) {
                    finished.add(event.getKind());
                }
            });

            boolean success = Boolean.TRUE.equals(task.call());
            System.out.println("Compilation success: " + success);
        }

        System.out.println("PARSE observed: "
                + finished.contains(TaskEvent.Kind.PARSE));
        System.out.println("ENTER observed: "
                + finished.contains(TaskEvent.Kind.ENTER));
        System.out.println("ANALYZE observed: "
                + finished.contains(TaskEvent.Kind.ANALYZE));
        System.out.println("GENERATE observed: "
                + finished.contains(TaskEvent.Kind.GENERATE));
        System.out.println("Class exists: "
                + Files.isRegularFile(
                        output.resolve("demo/Hello.class")));
    }
}
~~~

Đây là source **độc lập, đầy đủ**, phù hợp Java 17. Source lồng bên trong thuộc class Source extends SimpleJavaFileObject, cung cấp mã bằng getCharContent. Không cần tạo file demo/Hello.java trước.

### 5.1. Biên dịch công cụ quan sát

Mở terminal ở **gốc task-listener-lab** và kiểm tra phiên bản:

~~~sh
javac -version
java -version
~~~

Dùng JDK 17+ có javac, không chỉ runtime image tối giản không có compiler.

Tạo out:

~~~bash
# Bash (macOS/Linux)
mkdir -p out
~~~

~~~powershell
# PowerShell (Windows)
New-Item -ItemType Directory -Path out -Force | Out-Null
~~~

Biên dịch:

~~~sh
javac --release 17 -encoding UTF-8 -d out TaskListenerDemo.java
~~~

Import com.sun.source.util.JavacTask, TaskEvent và TaskListener hợp lệ trên JDK 17 vì **com.sun.source.util** là package công khai trong module jdk.compiler. Đây không phải thao tác mở package internals bằng --add-exports.

### 5.2. Chạy công cụ

~~~sh
java -cp out TaskListenerDemo
~~~

**Stdout của ví dụ trên JDK có system javac (đã kiểm thử với JDK 24 và --release 17):**

~~~text
Compilation success: true
PARSE observed: true
ENTER observed: true
ANALYZE observed: true
GENERATE observed: true
Class exists: true
~~~

Kết quả này cho thấy:

1. ToolProvider.getSystemJavaCompiler đã trả một compiler provider.
2. getTask tạo task nhận mã nguồn từ SimpleJavaFileObject.
3. Task runtime là JavacTask nên việc đăng ký listener thành công.
4. Listener đã thấy các Kind PARSE, ENTER, ANALYZE và GENERATE ở callback finished.
5. .class được ghi dưới build/classes/demo/Hello.class.

**Giới hạn kết quả:** ví dụ hiển thị boolean *đã từng nhận event* thay vì giả định thứ tự/số lượng callback. Với một compiler provider khác không hỗ trợ JavacTask, chương trình in "JavacTask unavailable" và không thực hiện lệnh compile trong nhánh đó. Với runtime image không có system compiler, nó in "No system Java compiler".

### 5.3. Chương trình đã làm gì mà không dùng internals?

- JavaCompiler của **javax.tools** chịu trách nhiệm tạo compilation task.
- JavacTask của **com.sun.source.util** cung cấp listener registration.
- TaskEvent.Kind mô tả sự kiện đã được thông báo.
- StandardJavaFileManager quản lý tài nguyên compiler và được đóng bằng try-with-resources.
- Compiler thực hiện phân tích và sinh .class; observer chỉ ghi nhận.
- Chương trình không import JCTree, Context, Attr hay các class nội bộ khác.

Dù dùng package com.sun.source.util, đây vẫn là cách dùng **public JDK API** được tài liệu mô tả.

## 6. Tại sao phải đăng ký listener trước task.call()?

Trong project, thứ tự thực hiện là:

~~~text
getTask(...) -> check instanceof JavacTask
            -> addTaskListener(listener)
            -> task.call()
            -> xử lý kết quả và event đã ghi nhận
~~~

Nếu gọi task.call() xong mới đăng ký listener thì các callback của hoạt động đã hoàn tất **không được phát lại** cho listener mới.

Một CompilationTask thông thường được thiết kế để thực hiện **một lần**. Không gọi task.call() nhiều lần để nhận lại events; nếu muốn compile một source khác, tạo task khác với input/output phù hợp.

### Có cần removeTaskListener không?

Trong chương trình ngắn này, task không dùng lại, listener chỉ sống cùng task nên không bắt buộc gọi removeTaskListener. Trong công cụ tái sử dụng hoặc đăng ký/gỡ listener động, removeTaskListener là API hợp lệ để hủy đăng ký. Đừng đăng ký cùng listener không kiểm soát nhiều lần rồi đếm event sai.

### Vì sao output được lưu sau khi task.call?

Sơ đồ hoạt động như sau:

~~~text
Source(JavaFileObject)   -> javac
                             |
                             +-- parse -> listener
                             +-- enter -> listener
                             +-- analyze -> listener
                             +-- generate -> listener
                             |
                             v
                        Hello.class
~~~

Lệnh Files.isRegularFile trong demo **kiểm tra bằng chứng trên filesystem**, bổ sung cho việc compiler trả success và listener thấy GENERATE. Một event không thay thế việc xác minh output thật.

## 7. Quan sát thông tin của event an toàn

Ngoài getKind(), TaskEvent còn có thể có CompilationUnitTree, JavaFileObject và TypeElement tùy sự kiện.

Trong callback của một TaskListener, có thể ghi log sau:

~~~java
@Override
public void finished(TaskEvent event) {
    System.out.println("Kind: " + event.getKind());

    if (event.getSourceFile() != null) {
        System.out.println("Source: "
                + event.getSourceFile().getName());
    }

    if (event.getTypeElement() != null) {
        System.out.println("Type: "
                + event.getTypeElement().getQualifiedName());
    }

    if (event.getCompilationUnit() != null) {
        System.out.println("Package: "
                + event.getCompilationUnit().getPackageName());
    }
}
~~~

Đây là **đoạn thay thế callback finished**, không phải class độc lập. Tên nguồn, số event và thứ tự log phụ thuộc vào loại hoạt động và project. Vì vậy bài **không** đưa “stdout cố định” cho snippet này.

**Không giả định các getter đồng thời có giá trị.** Với event thuộc cấp compilation tổng thể, source hoặc unit có thể null. Với event liên quan một type cụ thể, TypeElement có thể hiện diện. Khi viết observer, hãy xử lý dữ liệu vắng mặt thay vì gọi getQualifiedName hoặc getPackageName vô điều kiện.

### Dùng Tree API đúng mức

TaskEvent.getCompilationUnit() trả CompilationUnitTree, một **interface AST công khai** trong com.sun.source.tree. Nếu muốn duyệt cú pháp, có thể dùng com.sun.source.util.TreeScanner hoặc TreePathScanner. Đó là cách **quan sát**, không đụng đến com.sun.tools.javac.tree.JCTree.

Ví dụ, với event có CompilationUnitTree, bạn có thể xem:

~~~java
if (event.getCompilationUnit() != null) {
    int topLevelCount =
            event.getCompilationUnit().getTypeDecls().size();
}
~~~

Đoạn này là snippet, không phải chương trình độc lập. Nó đọc danh sách declarations ở cấp compilation unit, không chỉnh sửa nodes. Để phân tích tên/kiểu của AST tại một vị trí, có thể dùng Trees/TreePath và model javax.lang.model khi thông tin đó đã sẵn sàng ở pha phù hợp.

### Những trường hợp không nên thu thập quá sớm

Trong PARSE, cú pháp đã được tạo nhưng không có bảo đảm mọi tên được phân giải hoặc mọi kiểu được kiểm tra. Đừng dùng dữ liệu ở event PARSE để khẳng định type checking đã xong. Với các công cụ muốn nhìn TypeElement đã phân giải, sự kiện ENTER hoặc ANALYZE có thể thích hợp hơn tùy yêu cầu; nhưng vẫn phải kiểm tra null và hợp đồng từng event.

## 8. Thêm thống kê số lần callback cho dự án nhiều tệp

Ví dụ chính dùng EnumSet để trả lời “đã thấy event loại này chưa?”. Với nhiều source files, có thể cần biết **bao nhiêu lần** một event được thông báo. Khi đó dùng EnumMap<TaskEvent.Kind,Integer>:

~~~java
java.util.EnumMap<TaskEvent.Kind, Integer> counts =
        new java.util.EnumMap<>(TaskEvent.Kind.class);

TaskListener listener = new TaskListener() {
    @Override
    public void started(TaskEvent event) {
    }

    @Override
    public void finished(TaskEvent event) {
        counts.merge(event.getKind(), 1, Integer::sum);
    }
};
~~~

Đây là **snippet minh họa**, không phải main hoàn chỉnh. Nếu sử dụng, hãy thêm nó vào scope phù hợp và đăng ký listener trước khi gọi task.call().

**Không đặt kỳ vọng count(PARSE) bằng số .class output.** Một source có thể chứa nhiều class, nested types, và annotation processing có thể sinh source mới. ANALYZE/GENERATE có thể được báo ở mức từng type, còn PARSE liên quan compilation unit.

Khi so sánh số event giữa các phiên bản JDK, nên đánh dấu đó là **đo lường thực nghiệm**, không phải một công thức chính thức của Java Language Specification.

### Một phương án kiểm thử ít giòn

Thay vì assert “thứ tự event chính xác là P, E, A, G và mỗi loại đúng một lần”, kiểm thử rằng với source hợp lệ và javac bạn hỗ trợ:

- task.call() trả true;
- PARSE/ENTER/ANALYZE/GENERATE có mặt trong tập quan sát ở ví dụ cụ thể;
- output class file thực sự tồn tại;
- task không cần import các package internal.

Khi xử lý source lỗi, assert compile thất bại và có diagnostic ERROR, **không** yêu cầu GENERATE nhất định phải xảy ra.

## 9. Liên kết TaskListener với DiagnosticCollector

TaskListener báo hoạt động, còn DiagnosticCollector của javax.tools báo **vấn đề mà compiler phát hiện**. Hai nguồn thông tin trả lời hai câu hỏi khác nhau:

- TaskListener: compiler đang/đã thông báo giai đoạn nào?
- DiagnosticListener: compiler báo lỗi/cảnh báo gì, ở file/dòng nào nếu có?

Trong một compiler task, có thể cấu hình DiagnosticCollector khi tạo getTask:

~~~java
javax.tools.DiagnosticCollector<JavaFileObject> diagnostics =
        new javax.tools.DiagnosticCollector<>();

JavaCompiler.CompilationTask generic = compiler.getTask(
        null, files, diagnostics,
        List.of("--release", "17", "-proc:none",
                "-d", output.toString()),
        null, sources);
~~~

Đây là **mảnh mã thay thế cho phần tạo getTask của ví dụ**, không phải một phương thức đầy đủ. Biến sources phải là Iterable<? extends JavaFileObject> được chuẩn bị trước.

Sau khi task.call() hoàn tất, kiểm tra:

~~~java
boolean hasErrors = diagnostics.getDiagnostics().stream()
        .anyMatch(d -> d.getKind()
                == javax.tools.Diagnostic.Kind.ERROR);
~~~

Có thể lấy kind, source, line, column và message khi sẵn có. Không nên định nghĩa toàn bộ trạng thái build chỉ bằng số lượng events: một compiler có thể đã parse source nhưng bị lỗi tên/kiểu hoặc thiếu dependency nên không tạo bytecode.

### Một tình huống sai cú pháp

Thay source của demo bằng:

~~~java
String badCode = "package demo; public class Broken { "
        + "void test() { int x = ; } }";
~~~

Nếu dùng badCode làm input của một task mới, javac thường phát diagnostic ERROR và task.call() trả false. Listener có thể vẫn thấy các event liên quan parse, nhưng **không có lý do để đòi GENERATE** cho lớp Broken.

Điều này làm rõ sự khác biệt giữa *quan sát pha đã được báo* và *chứng minh compile thành công*.

## 10. Annotation processing và TaskListener

Một compiler có thể chạy annotation processors, sinh file nguồn mới và tạo thêm rounds. TaskListener có các Kind liên quan:

- ANNOTATION_PROCESSING;
- ANNOTATION_PROCESSING_ROUND.

Sự kiện có thể giúp observer nhận biết hoạt động annotation processing, nhưng **không có nghĩa listener chính là annotation processor**.

| Thành phần | Vai trò |
| --- | --- |
| TaskListener | Quan sát event javac bắt đầu/kết thúc một hoạt động |
| AbstractProcessor | Processor theo JSR 269, xử lý annotation trong rounds |
| RoundEnvironment | Cung cấp elements và trạng thái mỗi processing round |
| ProcessingEnvironment | Cấp Filer, Messager, Elements, Types cho processor |
| TaskEvent | Dữ liệu sự kiện compiler thông báo cho TaskListener |

Trong ví dụ runnable, ta dùng **-proc:none** để tắt annotation processing, giữ cho bốn Kind chính dễ quan sát. Nếu bật processors, chúng có thể thêm source, thêm rounds và thay số lượng events. Hãy cấu hình processor path và processor selection rõ ràng khi bạn muốn nghiên cứu điều đó; tránh suy đoán số event dựa trên một project không dùng processor.

**Không dùng TaskListener để thay Filer sinh source mới.** Filer quản lý generated files theo API annotation processing; TaskListener cung cấp callback quan sát pha, không phải một cơ chế chuẩn để sửa source/AST trực tiếp hoặc inject code tùy ý vào pipeline.

## 11. Quan sát bằng JavacTask thay vì tự gọi internals

Điểm then chốt của chủ đề là **không sửa nội bộ compiler**. So sánh:

| Việc cần làm | Public API phù hợp | Không cần/không nên mặc định dùng |
| --- | --- | --- |
| Yêu cầu compile source | javax.tools.JavaCompiler.getTask | com.sun.tools.javac.api.JavacTool trực tiếp |
| Lắng nghe phase event | JavacTask.addTaskListener | Patch com.sun.tools.javac.main.JavaCompiler |
| Đọc AST | com.sun.source.tree.* | Cast sang JCTree |
| Duyệt syntax | TreeScanner/TreePathScanner | Chỉnh trực tiếp fields của JCTree |
| Gắn AST với model kiểu | Trees và javax.lang.model | Truy cập Attr hoặc Context |
| Nhận errors/warnings | javax.tools.DiagnosticListener | Parse thông báo stderr theo chuỗi cố định |
| Sinh source theo annotation | AbstractProcessor + Filer | Ghi đè source input trong TaskListener |

### Vì sao không trực tiếp dùng com.sun.tools.javac.comp.Attr?

Attr là một thành phần của implementation javac. Những kiểu như Context, Attr hoặc JCTree có thể thay đổi fields/methods, constructor, lifecycle giữa các bản JDK. Module jdk.compiler không export công khai phần lớn package com.sun.tools.javac.* cho ứng dụng bình thường. Code dùng các lớp đó có thể gặp compile-time package not visible, IllegalAccessError hoặc các lỗi tương thích nhị phân khi nâng cấp.

TaskListener và JavacTask nằm trong API được JDK công bố để làm công cụ biên dịch. Chúng không nhất thiết biến một ứng dụng thành portable với **mọi** compiler Java khác, nhưng cho ranh giới sử dụng rõ hơn nhiều so với gắn trực tiếp vào nội bộ javac.

### Có cần --add-exports không?

**Không cần cho ví dụ ở phần 5**, vì com.sun.source.util được export công khai từ jdk.compiler trên JDK 17. Tùy chọn --add-exports thường được nhắc khi code muốn truy cập package nội bộ không export; không dùng nó làm giải pháp mặc định để quan sát compilation events.

Nếu viết một **named module** dùng TaskListener, có thể khai báo:

~~~java
module demo.compiler.observer {
    requires java.compiler;
    requires jdk.compiler;
}
~~~

Đây là đoạn **module-info.java minh họa**. Muốn biên dịch/running named module thật cần đặt source theo module root và dùng lệnh --module-path hoặc --module-source-path phù hợp. Hai requires chỉ rõ module chứa javax.tools và com.sun.source.util. Chúng không mở mọi package com.sun.tools.javac.*.

## 12. Lifecycle, tài nguyên và thread safety

### Một task tương ứng một hoạt động compile

Trong bản demo, compiler tạo generic task, observer đăng ký callback, task.call() thực hiện compilation, sau đó ta đọc kết quả. Không nên lưu JavacTask để gọi call lần thứ hai sau khi đã hoàn thành.

### Đóng file manager

StandardJavaFileManager dùng try-with-resources để tránh rò rỉ handles/tài nguyên. Khi compiler làm việc với nhiều files/JAR hoặc trong service lâu sống, đóng tài nguyên đúng cách rất quan trọng.

### Giữ listener nhẹ

Callback của TaskListener được compiler gọi trong quá trình xử lý. Nếu callback ghi đĩa chậm, gọi mạng hoặc thao tác khóa đồng bộ không phù hợp, bạn có thể làm build chậm hoặc gây rủi ro khi compiler đang giữ trạng thái xử lý nội bộ.

Cách tốt cho instrumentation: lưu thông tin tối thiểu như event kind, source name/qualified type name (khi có), thời điểm monotonic nếu cần đo thời gian và diagnostics. Không giữ AST/Element trong cache qua nhiều compilation invocations.

### Không giả định mọi callback được chạy trên một thread cụ thể

Trong một toolchain cụ thể bạn có thể quan sát thứ tự và luồng callback nhất định. Nhưng code tích hợp bền vững nên tránh phụ thuộc vào một triển khai concurrency không được API cam kết. Nếu listener chia sẻ dữ liệu với thread khác, dùng cơ chế đồng bộ thích hợp. Bản demo chỉ đọc tập finished **sau khi task.call() trả về**, nên không cần thiết kế pipeline đa luồng.

### Không sửa source/AST từ callback

API TaskListener không đưa ra hợp đồng công khai rằng bạn có thể lấy một Tree rồi biến đổi implementation node trong callback. Dù có người dùng kỹ thuật compiler-specific để làm điều đó, đây **không phải** cách quan sát an toàn, dễ bảo trì mà bài này hướng đến.

## 13. Những vấn đề dễ nhầm khi đọc log

| Hiện tượng | Suy luận dễ sai | Cách hiểu đúng |
| --- | --- | --- |
| PARSE finished | Mọi tên/kiểu đã được giải quyết | PARSE chủ yếu liên quan cấu trúc syntax |
| ENTER finished | Chắc chắn compile sẽ thành công | Các bước ngữ nghĩa tiếp theo vẫn có thể báo lỗi |
| ANALYZE xuất hiện nhiều lần | Compiler lặp một pha sai | Có thể gắn với nhiều types/units |
| GENERATE xuất hiện nhiều lần | Mỗi tệp nguồn chỉ nên có một .class | Một source có thể khai báo nhiều types/nested classes |
| Không có GENERATE | TaskListener bị hỏng | Compilation có thể thất bại trước khi phát sinh bytecode |
| Callback có source null | Compiler không biết source | Loại event đó có thể mang tính tổng thể |
| Task không instanceof JavacTask | JavaCompiler API bị lỗi | Provider đó không hứa hỗ trợ javac-specific API |
| Có annotation processing round | Listener là annotation processor | Hai API có trách nhiệm khác nhau |
| TaskListener dùng com.sun.* | Đó là internal API | com.sun.source.* là public JDK compiler API |
| javac in error nhưng đã thấy PARSE | Lỗi compile không có thật | Quan sát PARSE không thay thế task.call và diagnostics |
| Chạy tool tạo .class cũ | Code nguồn mới đã được compile | Kiểm tra output/build directory và compile result |

## 14. Quy trình chẩn đoán khi listener không hoạt động

1. **Kiểm tra JDK:** javac -version, java -version; có dùng JDK 17+ không, runtime có compiler provider không?
2. **Kiểm tra task:** ToolProvider.getSystemJavaCompiler() có null không? CompilationTask có instanceof JavacTask không?
3. **Kiểm tra thứ tự:** listener có được đăng ký **trước** task.call() không?
4. **Kiểm tra source input:** JavaFileObject có URI/Kind.SOURCE và mã nguồn hợp lệ không? Với source trên disk, file manager có đọc được file không?
5. **Kiểm tra task options:** đã đặt --release, -proc, -d và đường dẫn thư viện phù hợp chưa?
6. **Kiểm tra diagnostic:** task.call() trả gì, có ERROR do parser/type checker/dependency không?
7. **Kiểm tra Kind:** có đang chờ ANNOTATION_PROCESSING_ROUND dù đã bật -proc:none không?
8. **Kiểm tra metadata:** event.getCompilationUnit/getTypeElement/getSourceFile có thể null; đừng để NullPointerException trong callback che lỗi gốc.
9. **Kiểm tra output:** .class có được tạo không, đã chạy đúng directory không?
10. **Kiểm tra portability:** nếu dùng compiler implementation khác, hãy làm rõ JavacTask là điều kiện riêng của tính năng observer.

### Thêm DiagnosticCollector khi cần

Để phân biệt source sai với listener không chạy, nên đưa javax.tools.DiagnosticCollector vào getTask và in diagnostic theo Kind/source/line khi có. Đừng chỉ đếm events rồi tự quyết định status của build. Cũng đừng dựa trên toàn bộ câu tiếng Anh của một error message vì javac có thể đổi cách diễn đạt qua phiên bản.

## 15. Mở rộng: theo dõi thời lượng hoạt động

Một ứng dụng profiling có thể muốn đo thời gian giữa started/finished cho cùng activity. Điều này **khó hơn** chỉ đếm event: một Kind có thể xuất hiện cho nhiều compilation units/types và các hoạt động có thể lồng nhau.

Cách tiếp cận:

1. Chọn một khóa sự kiện gồm Kind, nguồn và type khi sẵn có.
2. Theo dõi started/finished tương ứng với khóa và ngữ cảnh callback phù hợp.
3. Dùng nguồn thời gian monotonic như System.nanoTime nếu đo duration trong cùng JVM.
4. Chỉ xuất thống kê sau khi task hoàn tất; nêu rõ số event và cách ghép cặp.
5. Đối chiếu với dữ liệu đo từ profiler/benchmark nếu cần kết luận hiệu suất.

**Không suy diễn rằng cộng tổng thời lượng từng Kind bằng wall-clock compile time.** Hoạt động có thể chồng lấn/lồng nhau, và listener có overhead. Một phép đo thực nghiệm trên JDK cụ thể không phải định nghĩa chính thức của thời gian parse/analyze trong Java.

Bài runnable cố ý chỉ thu thập **sự hiện diện của events** để tránh tạo ấn tượng rằng TaskListener là profiler có độ chính xác/định nghĩa thời gian hoàn toàn ổn định.

## 16. Bài tập thực hành

### Bài 1 — Đọc kết quả demo

Chạy TaskListenerDemo.java. Giải thích vì sao compilation success, PARSE, ENTER, ANALYZE, GENERATE và Class exists đều là true khi source hợp lệ. Mỗi dòng là bằng chứng cho điều gì?

### Bài 2 — Chỉ rõ event được báo ở callback nào

Đổi listener để đếm riêng started và finished. Có thể chỉ nhìn số lượng callback mà kết luận mọi Kind luôn xuất hiện đúng một lần không? Vì sao?

### Bài 3 — Thêm source thứ hai

Tạo thêm SimpleJavaFileObject cho demo.Second và đưa hai source vào getTask. So sánh số lần PARSE/ANALYZE/GENERATE. Ghi nhận kết quả thực nghiệm mà không biến nó thành luật cố định.

### Bài 4 — Source lỗi

Thử compile source có int x = ; trong task mới và dùng DiagnosticCollector. Dự đoán compilation success là false. Vì sao PARSE có thể đã được báo nhưng GENERATE có thể không xuất hiện cho class lỗi?

### Bài 5 — Thêm tên source

Trong finished(), kiểm tra event.getSourceFile()!=null rồi in source name. So sánh event nào gắn với JavaFileObject, event nào không có source.

### Bài 6 — Thêm TypeElement

Kiểm tra event.getTypeElement()!=null và in qualified name. Vì sao không thể luôn lấy TypeElement cho mọi Kind, đặc biệt khi mới parse?

### Bài 7 — AST không cần internals

Lấy CompilationUnitTree từ TaskEvent khi có và in getTypeDecls().size(). Không ép cast sang JCTree. Giải thích vì sao cách này ít phụ thuộc implementation hơn.

### Bài 8 — Named module

Phác thảo module-info.java cần java.compiler và jdk.compiler. Giải thích vì sao requires jdk.compiler chưa cho phép import com.sun.tools.javac.comp.Attr.

### Bài 9 — Annotation processing

Thay -proc:none bằng cấu hình một annotation processor có thật trong dự án riêng. Quan sát ANNOTATION_PROCESSING_ROUND và generated source. Vì sao TaskListener và Processor vẫn là hai loại extension khác nhau?

### Bài 10 — Thiết kế observer production

Viết kế hoạch log events không làm chậm build: giới hạn lượng log, kiểm tra null, không giữ AST quá lâu, gắn type/source khi có, phân biệt diagnostic với event, và kiểm thử trên JDK hỗ trợ.

## 17. Checklist trước khi kết thúc

- Biết TaskListener là API công khai của JDK, không phải implementation nội bộ com.sun.tools.javac.*.
- Phân biệt javax.tools.JavaCompiler chuẩn Java SE với com.sun.source.util.JavacTask chuyên biệt cho javac.
- Biết đăng ký TaskListener trước khi task.call().
- Hiểu started/finished và TaskEvent.Kind, đặc biệt PARSE, ENTER, ANALYZE, GENERATE.
- Không giả định số lần và thứ tự events bất biến cho mọi chương trình/JDK.
- Kiểm tra null khi đọc CompilationUnitTree, JavaFileObject và TypeElement từ TaskEvent.
- Dùng DiagnosticCollector để hiểu lỗi biên dịch, không suy ra kết quả build từ event count.
- Đã chạy được mã Java 17 và thấy file build/classes/demo/Hello.class.
- Hiểu -proc:none tắt annotation processing trong demo; khi bật processors có thể phát sinh thêm rounds.
- Hiểu việc quan sát AST qua com.sun.source.tree không cho quyền sửa JCTree.
- Không cần --add-exports cho com.sun.source.util trong ví dụ thông thường.
- Biết đóng file manager và không tái sử dụng CompilationTask đã hoàn thành.
- Có chiến lược thử nghiệm khi compiler provider không hỗ trợ JavacTask.

### Tài liệu chính thống để học sâu

- **JDK API com.sun.source.util.JavacTask**, **TaskListener** và **TaskEvent**: giao diện public để theo dõi sự kiện của javac.
- **JDK API com.sun.source.tree** và **com.sun.source.util.Trees/TreePathScanner**: AST và kỹ thuật quan sát cây cú pháp.
- **Java SE javax.tools.JavaCompiler**, **JavaFileObject**, **DiagnosticListener**: yêu cầu biên dịch và nhận errors/warnings qua API chuẩn.
- **Java Platform Module System (JPMS)**: ranh giới java.compiler, jdk.compiler, requires và exports.
- Tài liệu javac của phiên bản JDK đang sử dụng để đối chiếu options --release, -proc:none và output classes.

**Tóm lại:** muốn biết javac đang trải qua những pha nào, hãy tạo JavacTask và đăng ký TaskListener, kết hợp TaskEvent và DiagnosticCollector để nhận thông tin có cấu trúc. Quan sát bằng API công khai không đòi hỏi can thiệp Context, Attr, JCTree hay bất kỳ lớp triển khai nội bộ nào của compiler.
