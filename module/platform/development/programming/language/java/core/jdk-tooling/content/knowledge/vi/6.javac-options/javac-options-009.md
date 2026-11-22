# Compiler plugin trong javac

Compiler plugin là phần mở rộng được nạp vào quá trình biên dịch của javac. Plugin có thể quan sát các giai đoạn compiler xử lý source code, đọc cây cú pháp (AST), thu thập thông tin về class hoặc method và thực hiện các kiểm tra tùy biến. Cơ chế này hữu ích khi muốn bổ sung quy tắc kiểm tra mã nguồn, ghi nhận tiến trình compile hoặc tích hợp một công cụ phân tích vào build.

Trong JDK, API chính dành cho javac plugin là **com.sun.source.util.Plugin** thuộc module **jdk.compiler**. Compiler plugin ở đây là plugin chạy bên trong javac; khái niệm này khác với Maven Compiler Plugin hoặc Gradle plugin vốn cấu hình và điều phối build.

## 1. Cơ chế hoạt động

Một plugin javac thường có ba phần:

1. Một class triển khai interface **Plugin**.
2. Một khai báo service provider để Java ServiceLoader tìm được class đó.
3. Một lệnh javac chỉ định plugin bằng tùy chọn **-Xplugin**.

Khi javac bắt đầu compilation, nó tìm các plugin qua ServiceLoader, khởi tạo plugin được yêu cầu và gọi phương thức **init**. Plugin nhận một **JavacTask** đại diện cho lượt biên dịch. Phần lớn plugin đăng ký **TaskListener** lên task rồi thực hiện công việc khi compiler phát ra các sự kiện.

Luồng tổng quát:

~~~text
javac command
    |
    +-- tìm Plugin implementation qua ServiceLoader
    |
    +-- đối chiếu tên từ -Xplugin với Plugin.getName()
    |
    +-- gọi Plugin.init(JavacTask, args)
    |
    +-- plugin đăng ký TaskListener
    |
    +-- javac phát sự kiện PARSE, ENTER, ANALYZE, GENERATE, ...
    |
    +-- TaskListener quan sát sự kiện và xử lý AST hoặc thông tin compile
    |
    +-- javac tiếp tục biên dịch và tạo class file
~~~

Tên plugin là tên thân thiện do phương thức **getName()** trả về. Mỗi plugin được khởi chạy nhận một mảng chuỗi **args** chứa các đối số viết sau tên plugin trên command line.

## 2. API quan trọng

Các API nằm trong module **jdk.compiler**, chủ yếu ở package **com.sun.source.util** và **com.sun.source.tree**.

| API | Vai trò |
|---|---|
| Plugin | Điểm vào của plugin; cung cấp getName(), init() và autoStart() |
| JavacTask | Đại diện cho một lượt biên dịch javac; cho phép đăng ký listener và truy cập một số API compiler |
| TaskListener | Nhận thông báo khi một giai đoạn biên dịch bắt đầu hoặc kết thúc |
| TaskEvent | Mô tả sự kiện, loại sự kiện và compilation unit hoặc type liên quan |
| Tree | Kiểu cơ sở của các node trong cây cú pháp |
| ClassTree, MethodTree, VariableTree | Đại diện cho khai báo class, method và biến |
| TreePathScanner | Duyệt AST theo chiều sâu và giữ đường dẫn từ gốc đến node hiện tại |
| Trees | Cầu nối giữa AST, phần tử ngôn ngữ và thông tin kiểu; hỗ trợ phát diagnostic gắn với source tree |

### Plugin

Interface **Plugin** có hai phương thức cốt lõi:

~~~java
String getName();

void init(JavacTask task, String... args);
~~~

- **getName()** trả về tên dùng để gọi plugin bằng -Xplugin.
- **init()** được gọi khi plugin được khởi tạo cho compilation task. Đây là nơi đăng ký listener hoặc chuẩn bị trạng thái cần thiết.
- **autoStart()** là phương thức mặc định được bổ sung từ JDK 14. Plugin có thể trả về true để được tự khởi chạy khi được phát hiện qua ServiceLoader, ngay cả khi không được nêu tường minh bằng -Xplugin. Chỉ bật hành vi này khi thật sự muốn plugin chạy tự động trong mọi lượt compile có phát hiện nó.

Plugin API có từ JDK 8. Ví dụ thực hành bên dưới dùng JDK 17 trở lên.

### TaskListener và TaskEvent

**TaskListener** có hai callback:

- **started(TaskEvent event)** được gọi khi một sự kiện bắt đầu.
- **finished(TaskEvent event)** được gọi khi sự kiện kết thúc.

Các loại sự kiện thường gặp gồm:

| Event kind | Ý nghĩa |
|---|---|
| COMPILATION | Toàn bộ lượt biên dịch |
| PARSE | Đọc source và tạo cây cú pháp |
| ENTER | Đưa khai báo vào symbol table |
| ANNOTATION_PROCESSING | Giai đoạn xử lý annotation |
| ANNOTATION_PROCESSING_ROUND | Một vòng annotation processing |
| ANALYZE | Phân tích ngữ nghĩa và kiểm tra kiểu |
| GENERATE | Sinh class file |

Các sự kiện xuất hiện tùy cấu trúc chương trình và cách compiler chạy. Không nên phụ thuộc vào một chuỗi sự kiện cố định cho mọi project hoặc mọi phiên bản JDK.

Trong sự kiện **PARSE** đã hoàn tất, plugin có thể lấy compilation unit từ **event.getCompilationUnit()** và duyệt cây cú pháp. Với các event khác, dữ liệu compilation unit hoặc type có thể không có; hãy kiểm tra đúng loại event trước khi truy cập.

## 3. Phân biệt javac plugin với annotation processor

Hai cơ chế đều mở rộng quy trình compile, nhưng phục vụ mục đích khác nhau.

| Tiêu chí | javac plugin | Annotation processor |
|---|---|---|
| API chính | Plugin, JavacTask, TaskListener | Processor, ProcessingEnvironment |
| Điểm kích hoạt | Sự kiện trong tiến trình javac | Các vòng annotation processing |
| Dữ liệu chính | TaskEvent và AST qua Tree API | Annotation và Element/TypeMirror |
| Mục đích thường gặp | Quan sát compiler, phân tích AST, quy tắc kiểm tra tùy biến | Xử lý annotation, sinh source/resource |
| Cách gọi | -Xplugin:name args | -processor hoặc tự discovery |
| Khả năng tương thích | Đặc thù javac | Chuẩn annotation processing của Java |

Ví dụ, một processor xử lý **@GenerateBuilder** để sinh thêm mã Java. Một javac plugin có thể duyệt AST để cảnh báo khi code vi phạm quy tắc nội bộ, chẳng hạn class có tên không đúng convention hoặc method có cấu trúc không được phép.

Nếu yêu cầu chỉ là sinh code dựa trên annotation, annotation processor thường phù hợp hơn. Nếu cần quan sát các giai đoạn compile hoặc duyệt AST theo luồng sự kiện của javac, plugin API là lựa chọn phù hợp.

## 4. Cách javac tìm plugin

Plugin được tìm bằng **ServiceLoader**. Theo tài liệu javac, cơ chế này sử dụng cùng đường dẫn tìm kiếm với annotation processor, tức **ANNOTATION_PROCESSOR_PATH** hoặc tùy chọn **-processorpath**.

Với plugin dạng JAR trên classpath, JAR cần chứa file service descriptor tại đúng đường dẫn:

~~~text
META-INF/services/com.sun.source.util.Plugin
~~~

Nội dung file là tên đầy đủ của class triển khai Plugin, mỗi provider một dòng. Ví dụ:

~~~text
demo.TracePlugin
~~~

Cấu trúc project mẫu:

~~~text
compiler-plugin-demo/
  plugin-src/
    demo/
      TracePlugin.java
    META-INF/
      services/
        com.sun.source.util.Plugin
  plugin-classes/
  trace-plugin.jar
  src/
    Hello.java
  out/
~~~

Lưu ý:

- File service descriptor phải được đóng gói bên trong JAR, không phải chỉ nằm cạnh JAR.
- Tên class trong descriptor phải đúng package và class name.
- JAR plugin phải nằm trên processor path mà javac dùng để tìm service.
- Nếu dùng nhiều plugin hoặc annotation processor, ghép các JAR bằng path separator của hệ điều hành.
- Khi sử dụng Java module, có thể khai báo service provider trong module descriptor bằng cú pháp provides/with. Ví dụ dưới đây dùng JAR trên classpath để dễ quan sát cơ chế ServiceLoader.

## 5. Ví dụ hoàn chỉnh: plugin ghi nhận class trong source

Ta tạo plugin tên **Trace**. Plugin đăng ký TaskListener, chờ sự kiện PARSE kết thúc, rồi duyệt AST và in tên mỗi class tìm thấy.

### File TracePlugin.java

Tạo file **plugin-src/demo/TracePlugin.java**:

~~~java
package demo;

import com.sun.source.tree.ClassTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.Plugin;
import com.sun.source.util.TaskEvent;
import com.sun.source.util.TaskListener;
import com.sun.source.util.TreePathScanner;

public final class TracePlugin implements Plugin {

    @Override
    public String getName() {
        return "Trace";
    }

    @Override
    public void init(JavacTask task, String... args) {
        String label = args.length == 0 ? "Trace" : args[0];
        System.out.println("[" + label + "] plugin initialized");

        task.addTaskListener(new TaskListener() {
            @Override
            public void finished(TaskEvent event) {
                if (event.getKind() != TaskEvent.Kind.PARSE
                        || event.getCompilationUnit() == null) {
                    return;
                }

                new TreePathScanner<Void, Void>() {
                    @Override
                    public Void visitClass(ClassTree node, Void unused) {
                        System.out.println(
                                "[" + label + "] class: " + node.getSimpleName()
                        );
                        return super.visitClass(node, unused);
                    }
                }.scan(event.getCompilationUnit(), null);
            }
        });
    }
}
~~~

Giải thích:

- Class **TracePlugin** triển khai Plugin.
- **getName()** trả về Trace nên javac sẽ nhận tên này trong tùy chọn -Xplugin.
- **init()** nhận task và các đối số tùy chọn. Ví dụ sẽ dùng đối số đầu tiên làm nhãn log.
- **addTaskListener()** đăng ký listener cho lượt compile hiện tại.
- Callback **finished()** chỉ xử lý event PARSE đã hoàn tất.
- **TreePathScanner** duyệt cây cú pháp; **visitClass()** được gọi khi gặp khai báo class, kể cả nested class.
- **super.visitClass()** tiếp tục duyệt các node con để không bỏ qua class lồng bên trong.

### File service descriptor

Tạo file **plugin-src/META-INF/services/com.sun.source.util.Plugin** với nội dung:

~~~text
demo.TracePlugin
~~~

Dòng này cho ServiceLoader biết class nào là implementation của Plugin.

### Source để thử nghiệm

Tạo file **src/Hello.java**:

~~~java
public class Hello {
    static class Greeter {
        void greet() {
            System.out.println("Hello from javac plugin");
        }
    }

    public static void main(String[] args) {
        new Greeter().greet();
    }
}
~~~

### Biên dịch plugin và đóng gói JAR

Dùng JDK 17 trở lên. Các lệnh dưới đây viết theo PowerShell:

~~~powershell
New-Item -ItemType Directory -Force plugin-classes | Out-Null

javac -encoding UTF-8 -d plugin-classes plugin-src/demo/TracePlugin.java

New-Item -ItemType Directory -Force plugin-classes/META-INF/services | Out-Null

Copy-Item plugin-src/META-INF/services/com.sun.source.util.Plugin plugin-classes/META-INF/services/

jar --create --file trace-plugin.jar -C plugin-classes .
~~~

Sau bước này, JAR cần có ít nhất:

~~~text
demo/TracePlugin.class
META-INF/services/com.sun.source.util.Plugin
~~~

Có thể kiểm tra nội dung JAR bằng:

~~~bash
jar --list --file trace-plugin.jar
~~~

### Gọi plugin khi biên dịch ứng dụng

Tạo thư mục output và gọi javac:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null

javac -encoding UTF-8 -processorpath trace-plugin.jar '-Xplugin:Trace Build' -d out src/Hello.java
~~~

Giải thích các phần:

- **-processorpath trace-plugin.jar** cung cấp JAR cho cơ chế ServiceLoader tìm plugin.
- **-Xplugin:Trace Build** yêu cầu chạy plugin có tên Trace và truyền đối số Build. Vì tên và đối số có dấu cách, toàn bộ giá trị được đặt trong dấu nháy.
- **-d out** ghi class file của ứng dụng vào thư mục out.
- **src/Hello.java** là source được biên dịch và được plugin quan sát.

Trong lúc javac chạy, plugin in log đại diện:

~~~text
[Build] plugin initialized
[Build] class: Hello
[Build] class: Greeter
~~~

Thứ tự các class theo thứ tự duyệt AST. Nếu source có thêm class hoặc nested class, plugin sẽ in thêm tên tương ứng.

Chạy ứng dụng:

~~~bash
java -cp out Hello
~~~

Stdout:

~~~text
Hello from javac plugin
~~~

Plugin chỉ quan sát source trong lúc compile. Nó không cần được đưa vào classpath khi chạy ứng dụng; class file của ứng dụng có thể chạy độc lập sau khi biên dịch thành công.

## 6. Truyền đối số cho plugin

Tùy chọn có dạng:

~~~bash
javac -Xplugin:name args Source.java
~~~

Khi plugin được gọi, các chuỗi sau tên plugin được truyền vào mảng **args** của phương thức init.

Ví dụ:

~~~bash
javac -processorpath trace-plugin.jar -Xplugin:"Trace Build verbose" -d out src/Hello.java
~~~

Trong plugin mẫu:

- args[0] là Build.
- args[1] là verbose.

Có thể định nghĩa quy ước đối số riêng, chẳng hạn mức log, tên file báo cáo hoặc chế độ kiểm tra. Nên kiểm tra số lượng và giá trị đối số ngay trong init; nếu cấu hình sai, phát thông báo rõ ràng và dừng plugin theo cách phù hợp.

Không nên tự phân tích chuỗi tùy tiện khi có nhiều tùy chọn. Hãy quy định cú pháp rõ ràng, ví dụ key=value hoặc một tập cờ đã được tài liệu hóa.

## 7. Duyệt AST và phát hiện quy tắc tùy biến

Ví dụ trên mới in tên class. Trong công cụ thực tế, plugin thường duyệt các node khác để tìm quy tắc.

Một số loại node:

- **ClassTree**: class, interface, enum hoặc record declaration.
- **MethodTree**: khai báo method hoặc constructor.
- **VariableTree**: field, parameter hoặc biến cục bộ.
- **MethodInvocationTree**: lời gọi method.
- **IfTree**, **ForLoopTree**, **TryTree**: cấu trúc điều khiển.

Ví dụ, muốn in tên method, có thể bổ sung vào TreePathScanner:

~~~java
@Override
public Void visitMethod(MethodTree node, Void unused) {
    System.out.println("Method: " + node.getName());
    return super.visitMethod(node, unused);
}
~~~

Cần import:

~~~java
import com.sun.source.tree.MethodTree;
~~~

Một số method có tên đặc biệt như **<init>** đại diện constructor. Vì vậy, khi hiển thị hoặc kiểm tra tên method, hãy xử lý constructor theo mục đích của quy tắc.

### Phân biệt cú pháp và ngữ nghĩa

AST sau PARSE cho biết cấu trúc cú pháp của source. Nó chưa chắc đã chứa đầy đủ thông tin kiểu và symbol đã được phân giải.

Nếu quy tắc cần biết method call đang gọi overload nào, kiểu của biểu thức hoặc declaration mà identifier tham chiếu tới, hãy xem xét các event sau ANALYZE và sử dụng API **Trees**, **Elements** hoặc **Types** khi phù hợp.

Ví dụ lấy Trees từ task:

~~~java
import com.sun.source.util.Trees;

Trees trees = Trees.instance(task);
~~~

**Trees** cung cấp khả năng ánh xạ giữa cây cú pháp và phần tử ngôn ngữ. API này hữu ích khi cần truy vấn symbol hoặc phát thông báo gắn với vị trí source. Không nên giả định thông tin ngữ nghĩa đã sẵn sàng trong callback PARSE.

### Phát diagnostic gắn với source

Có thể dùng Trees để ghi cảnh báo vào đúng node:

~~~java
trees.printMessage(
        javax.tools.Diagnostic.Kind.WARNING,
        "Quy tắc nội bộ: cần xem lại khai báo này",
        tree,
        compilationUnit
);
~~~

Đoạn gọi cần có biến **trees**, **tree** và **compilationUnit** tương ứng. Cách phát diagnostic này giúp cảnh báo xuất hiện cùng vị trí source trong output compiler, thay vì chỉ in một dòng log không có ngữ cảnh.

Plugin nên tránh phát quá nhiều cảnh báo trùng lặp. Hãy định nghĩa rõ mức độ ERROR/WARNING/NOTE và vị trí cần gắn cảnh báo.

## 8. autoStart và hành vi nạp plugin

Từ JDK 14, Plugin có phương thức mặc định **autoStart()**. Khi trả về true, javac sẽ khởi tạo plugin với mảng đối số rỗng nếu plugin được tìm thấy qua ServiceLoader và chưa được khởi tạo bởi tùy chọn tường minh.

Điều này tạo ra hai cách sử dụng:

- **Khởi chạy tường minh**: người dùng chỉ định -Xplugin:name. Đây là cách dễ kiểm soát và dễ dự đoán cho hầu hết plugin.
- **Tự khởi chạy**: plugin override autoStart() trả về true. Plugin có thể chạy khi JAR xuất hiện trên đường dẫn tìm kiếm processor, kể cả khi người dùng không ghi -Xplugin.

Không nên bật autoStart nếu plugin có tác dụng phụ lớn, ghi file, thay đổi kết quả compile hoặc làm tăng đáng kể thời gian build. Hành vi tự động cần được tài liệu hóa và kiểm soát trong build environment.

## 9. Tích hợp với build tool

javac plugin được kích hoạt khi build tool gọi javac với processor path và tùy chọn plugin phù hợp. Cần phân biệt plugin của javac với plugin của build tool.

### Maven

Maven Compiler Plugin là thành phần cấu hình việc biên dịch trong Maven. Nó không phải là javac Plugin API. Khi dùng compiler backend là javac, có thể truyền tùy chọn compiler để kích hoạt plugin.

Một cấu hình minh họa với maven-compiler-plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <compilerArgs>
            <arg>-Xplugin:Trace</arg>
        </compilerArgs>
        <annotationProcessorPaths>
            <path>
                <groupId>example</groupId>
                <artifactId>trace-plugin</artifactId>
                <version>1.0.0</version>
            </path>
        </annotationProcessorPaths>
    </configuration>
</plugin>
~~~

Trong cấu hình thực tế, khai báo artifact của plugin theo tọa độ Maven nội bộ và xác nhận phiên bản Maven Compiler Plugin hỗ trợ cách truyền processor path như dự kiến. Nếu cần truyền đối số có dấu cách, hãy dùng cấu hình argument tương ứng và kiểm tra command line compiler thực tế mà Maven sinh ra.

### Gradle

Với Gradle Java, có thể cấu hình compiler argument và annotation processor path trên các task JavaCompile:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-Xplugin:Trace']
    options.annotationProcessorPath = configurations.tracePlugin
}
~~~

Cấu hình trên giả định project đã khai báo configuration **tracePlugin** chứa JAR plugin. Cần tạo configuration và thêm dependency phù hợp, ví dụ:

~~~groovy
configurations {
    tracePlugin
}

dependencies {
    tracePlugin 'example:trace-plugin:1.0.0'
}
~~~

Tên configuration và cách chia sẻ dependency nên phù hợp với cấu trúc project. Nếu dùng plugin trên nhiều module, nên đưa cấu hình vào convention plugin hoặc build logic dùng chung để tránh mỗi module có hành vi khác nhau.

Build tool có thể dùng compiler khác hoặc daemon có classloader riêng. Hãy xác nhận backend thực sự là javac và kiểm tra log build nếu plugin không được nạp.

## 10. Giới hạn và lưu ý khi phát triển

- **Đặc thù javac**: Plugin API là extension point của javac. Không mặc định plugin sẽ hoạt động với Eclipse Compiler for Java hoặc compiler khác.
- **Không dựa vào implementation nội bộ**: ưu tiên com.sun.source.util và com.sun.source.tree. Các package com.sun.tools.javac.* là nội bộ và có thể thay đổi giữa các phiên bản.
- **Tương thích JDK**: biên dịch và chạy plugin với JDK phù hợp. Kiểm tra API mới trước khi sử dụng nếu phải hỗ trợ nhiều major version.
- **Tác động build**: duyệt toàn bộ AST, đọc file hoặc gọi dịch vụ bên ngoài có thể làm compile chậm. Tránh công việc nặng trong callback.
- **An toàn và tái lập**: plugin chạy code trong tiến trình compiler với quyền của tiến trình build. Chỉ nạp JAR tin cậy, kiểm soát dependency và tránh tải code động không cần thiết.
- **Tính song song**: build tool có thể biên dịch nhiều module hoặc source task đồng thời. Không dùng state mutable static chung nếu chưa thiết kế để thread-safe.
- **Diagnostic**: xác định rõ khi nào chỉ cảnh báo và khi nào cần làm compilation thất bại. Không biến quy tắc chưa ổn định thành lỗi build bắt buộc.
- **Không ghi đè source**: plugin phân tích nên tránh tự sửa source file. Nếu cần sinh source, annotation processor hoặc một bước code generation riêng thường phù hợp hơn.

## 11. Xử lý lỗi thường gặp

### javac báo không tìm thấy plugin

Kiểm tra:

1. JAR plugin có nằm trên processor path hay chưa.
2. File service descriptor có đúng tên và đúng đường dẫn META-INF/services hay không.
3. Nội dung descriptor có đúng fully qualified class name không.
4. Class triển khai có public và có constructor không tham số để ServiceLoader khởi tạo được không.
5. Class plugin có implement đúng interface com.sun.source.util.Plugin không.
6. Tên trong -Xplugin có khớp chính xác với getName() không.

### Plugin được tìm thấy nhưng init không chạy

- Xác nhận đã gọi đúng -Xplugin:name.
- Kiểm tra cú pháp quote nếu plugin có đối số chứa khoảng trắng.
- Nếu dựa vào autoStart, kiểm tra JDK có hỗ trợ API này hay không; autoStart có từ JDK 14.
- Kiểm tra build tool có thực sự truyền tùy chọn đến javac hay không.
- Xem log command line hoặc bật chế độ verbose của build tool.

### Không tìm thấy class hoặc gặp lỗi linkage

- Kiểm tra JAR có chứa class đã compile và dependency cần thiết.
- Kiểm tra phiên bản JDK dùng để compile plugin và JDK chạy compiler.
- Kiểm tra classpath/processorpath có thiếu dependency hoặc có nhiều phiên bản xung đột không.
- Với plugin dạng module, kiểm tra module descriptor, requires và provides/uses phù hợp.
- Tránh tham chiếu package nội bộ của javac vì có thể gặp lỗi truy cập module hoặc thay đổi API.

### AST hoặc type information bị null

- Kiểm tra event kind trước khi gọi getCompilationUnit() hoặc getTypeElement().
- Dùng compilation unit ở sự kiện phù hợp, thường là PARSE.
- Nếu cần type hoặc symbol đã được phân giải, xử lý ở giai đoạn phù hợp như ANALYZE.
- Kiểm tra các source file có thực sự nằm trong lượt compile hay chỉ được tìm gián tiếp qua classpath.

### Build chạy chậm sau khi thêm plugin

- Đo thời gian trước và sau khi bật plugin.
- Giới hạn loại event được xử lý; đừng duyệt AST lặp lại không cần thiết.
- Cache kết quả trong phạm vi compilation task.
- Tránh truy cập mạng hoặc đọc nhiều file đồng bộ trong listener.
- Cho phép tắt plugin bằng cấu hình build khi cần so sánh hoặc khoanh vùng.

## 12. Khi nào nên dùng javac plugin?

Nên cân nhắc javac plugin khi cần:

- Theo dõi các giai đoạn compile để debug build hoặc tích hợp công cụ.
- Duyệt AST để kiểm tra convention hoặc quy tắc source riêng của tổ chức.
- Phân tích cấu trúc source trước hoặc sau một giai đoạn compiler.
- Tạo diagnostic tùy biến gắn với vị trí trong source.
- Kết nối javac với hệ thống đo lường hoặc báo cáo compile có kiểm soát.

Không nên chọn javac plugin chỉ vì muốn thêm dependency, chạy formatter hoặc sinh source đơn giản. Các việc đó có thể được xử lý tốt hơn bằng build plugin, formatter, static analyzer hoặc annotation processor chuyên dụng.

## 13. Checklist tạo và sử dụng plugin

- [ ] Chọn đúng mục tiêu: theo dõi compiler, phân tích AST hay xử lý annotation.
- [ ] Triển khai com.sun.source.util.Plugin và trả về tên ổn định trong getName().
- [ ] Đăng ký TaskListener trong init() và chỉ xử lý đúng event cần thiết.
- [ ] Đóng gói service descriptor tại META-INF/services/com.sun.source.util.Plugin.
- [ ] Đưa JAR plugin lên processor path.
- [ ] Gọi bằng -Xplugin với đúng tên và đối số.
- [ ] Kiểm tra plugin trên một source nhỏ trước khi tích hợp toàn project.
- [ ] Đo tác động đến thời gian compile và kiểm tra tương thích JDK.
- [ ] Tránh API nội bộ com.sun.tools.javac.* khi có thể dùng API công khai.
- [ ] Ghi rõ cách bật/tắt và cách xử lý khi plugin phát hiện lỗi.

## 14. Ghi nhớ

- javac plugin là extension point của compiler, dùng interface **Plugin** trong module **jdk.compiler**.
- **getName()** xác định tên plugin; **init()** nhận JavacTask và đối số.
- **ServiceLoader** tìm plugin qua cùng đường dẫn tìm annotation processor, thường cấu hình bằng **-processorpath**.
- **-Xplugin:name args** kích hoạt plugin trong command line javac.
- **TaskListener** theo dõi các sự kiện PARSE, ENTER, ANALYZE, GENERATE và các giai đoạn khác.
- **TreePathScanner** và Tree API cho phép duyệt AST; dùng Trees khi cần liên kết AST với symbol hoặc phát diagnostic.
- Plugin API dành riêng cho javac; annotation processor và Maven/Gradle plugin là những cơ chế khác nhau.
- Ưu tiên API công khai, giữ plugin nhẹ, xác định rõ tác động build và kiểm soát JAR được nạp.

## Tài liệu tham khảo chính thức

- [javac Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)
- [Plugin API — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.compiler/com/sun/source/util/Plugin.html)
- [TaskListener API — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/util/TaskListener.html)
- [com.sun.source.util package — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/jdk.compiler/com/sun/source/util/package-summary.html)