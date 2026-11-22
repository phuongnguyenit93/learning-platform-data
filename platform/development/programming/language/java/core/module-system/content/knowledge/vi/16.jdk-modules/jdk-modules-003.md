# jdk.* module và công cụ phát triển

Từ Java 9, Java Platform Module System (JPMS) phân chia JDK thành nhiều **named modules**. Một nhóm là các module có tên bắt đầu bằng `java.` (ví dụ `java.base`, `java.compiler`, `java.sql`); nhóm khác có tên bắt đầu bằng `jdk.` (ví dụ `jdk.compiler`, `jdk.javadoc`, `jdk.jdeps`, `jdk.jlink`, `jdk.jshell`).

Nhiều module `jdk.*` cung cấp **công cụ dành cho người phát triển**, implementation của compiler, công cụ phân tích dependency, công cụ tạo runtime image, môi trường JShell hoặc những chức năng quan sát JVM. Hiểu chúng giúp cấu hình đúng build, nhận biết API nào được hỗ trợ, và tránh lỗi khi chạy trên một Java runtime image không chứa đầy đủ công cụ của JDK.

**Nguyên tắc:** tiền tố `jdk.` chỉ cho biết tên module thuộc nhóm module do JDK cung cấp; nó không tự chứng minh mọi package bên trong đều là public API ổn định. Cần xem **exports**, tài liệu API và mục đích cụ thể của module trước khi phụ thuộc trực tiếp vào class nào đó.

## 1. java.* và jdk.* khác nhau như thế nào?

Trong JDK modular:

- Các module `java.*` bao gồm các API Java SE chuẩn như collections, networking, JDBC, XML, logging và Java Compiler API. Ví dụ `java.base` luôn có mặt trong mọi runtime Java.
- Các module `jdk.*` cung cấp những khả năng do JDK định nghĩa, bao gồm một số API công khai của JDK và cả implementation hoặc công cụ dành cho lập trình viên.
- Một module có thể **exports** package công khai trong khi giữ những package nội bộ không được export.
- Tập module thực tế có thể khác giữa các phiên bản JDK, nhà cung cấp JDK và custom runtime images.

Ví dụ:

    module com.example.app {
        requires java.compiler;
    }

Khai báo trên cho phép ứng dụng dùng API Java Compiler chuẩn trong `javax.tools` và `javax.annotation.processing`. Nó **không tương đương** với:

    module com.example.app {
        requires jdk.compiler;
    }

`jdk.compiler` chứa implementation của compiler cùng một số API công cụ riêng của JDK; còn `java.compiler` định nghĩa những interface và kiểu chuẩn mà ứng dụng có thể sử dụng khi phù hợp.

Cũng cần phân biệt **module name** với **package name**. Một package tên `com.sun.source.tree` có thể được export từ `jdk.compiler`, dù tên package không bắt đầu bằng `jdk.`. Ngược lại, package bắt đầu bằng `jdk.internal.` thường không phải API được hỗ trợ để ứng dụng dùng trực tiếp.

## 2. Những module jdk.* thường gặp

| Module | Chức năng chính | Công cụ hoặc API liên quan |
|---|---|---|
| `jdk.compiler` | Implementation Java compiler và API phân tích cấu trúc source của JDK | `javac`, `com.sun.source.tree`, `com.sun.source.util` |
| `jdk.javadoc` | Implementation công cụ tạo tài liệu Java | `javadoc`, `jdk.javadoc.doclet` |
| `jdk.jdeps` | Phân tích dependency của class/JAR và gợi ý module dependencies | `jdeps` |
| `jdk.jlink` | Công cụ liên kết module và đóng gói runtime image | `jlink`, `jmod` |
| `jdk.jshell` | API và implementation JShell | `jshell`, `jdk.jshell` |
| `jdk.jfr` | Java Flight Recorder (JFR) | `jdk.jfr.FlightRecorder`, `Recording` |
| `jdk.attach` | Attach API để tương tác với JVM khác khi được hỗ trợ | `com.sun.tools.attach.VirtualMachine` |
| `jdk.management` | Phần mở rộng JDK Management API | `com.sun.management` |
| `jdk.httpserver` | HTTP server nhẹ do JDK cung cấp | `com.sun.net.httpserver.HttpServer` |
| `jdk.unsupported` | Một số API legacy không chuẩn được duy trì để tương thích | Không nên chọn cho ứng dụng mới nếu có API thay thế |

Bảng mô tả các module quen thuộc trong những bản JDK hiện đại; **không phải cam kết rằng mọi bản phân phối Java đều có toàn bộ danh sách**. Module cung cấp công cụ có thể không có trong runtime image tối giản được tạo bởi `jlink`.

`jdk.*` cũng không đồng nghĩa mọi module chỉ dành cho compile time: chẳng hạn `jdk.jfr`, `jdk.attach`, `jdk.management` hoặc `jdk.httpserver` có thể được sử dụng khi chương trình đang chạy.

## 3. Module là thành phần runtime; lệnh javac là công cụ

Có hai tầng cần tách:

**Tầng module:** `jdk.compiler` là một named module có descriptor, các package, dependencies và exports cụ thể.

**Tầng công cụ:** `javac` là công cụ dòng lệnh dùng để biên dịch source Java. Khi chạy `javac`, bạn đang sử dụng chức năng compiler của JDK; shell command không phải là tên module.

Tương tự:

    Công cụ:  javac       -> module liên quan: jdk.compiler
    Công cụ:  javadoc     -> module liên quan: jdk.javadoc
    Công cụ:  jdeps       -> module liên quan: jdk.jdeps
    Công cụ:  jlink       -> module liên quan: jdk.jlink
    Công cụ:  jshell      -> module liên quan: jdk.jshell

Không phải mọi command-line launcher đều có cùng cơ chế cung cấp API trong chương trình Java. Khi viết Java code, hãy tìm API công khai phù hợp và khai báo `requires` nếu source module cần dùng kiểu của module đó.

Các executable trong thư mục `bin` của JDK và các runtime modules được lưu trong JDK image là những thành phần liên quan nhưng không phải cùng một thực thể.

## 4. Xem các module đang có trong JDK

Cách dễ nhất để biết một Java runtime nhìn thấy những module hệ thống nào là:

    java --list-modules

Đầu ra có thể gồm:

    java.base@...
    java.compiler@...
    jdk.compiler@...
    jdk.javadoc@...
    jdk.jdeps@...
    jdk.jlink@...

Dấu `...` chỉ phiên bản được rút gọn trong ví dụ. Danh sách thực tế phụ thuộc JDK.

Lọc tên module trên Linux/macOS:

    java --list-modules | grep '^jdk\.'

Trên Windows với Command Prompt:

    java --list-modules | findstr /B jdk.

Xem descriptor của một module:

    java --describe-module jdk.compiler

Descriptor có thể cho biết:

- Tên và phiên bản module.
- Directive `requires`, gồm module nào nó đọc.
- Những package được `exports`.
- Những package được `opens` nếu có.
- Các service declarations `uses` và `provides`.

Nếu `java --describe-module jdk.compiler` báo module không tìm thấy, hãy kiểm tra đúng lệnh `java` đang chạy thuộc JDK/runtime image nào, thay vì mặc định lỗi nằm ở source application.

## 5. Quan sát module bằng Java API

API `ModuleFinder` cho phép tìm module hệ thống hiện có:

    import java.lang.module.ModuleFinder;
    import java.lang.module.ModuleReference;

    public class InspectJdkModule {
        public static void main(String[] args) {
            ModuleFinder finder = ModuleFinder.ofSystem();

            finder.find("jdk.compiler").ifPresentOrElse(
                reference -> {
                    System.out.println(reference.descriptor().name());
                    System.out.println(reference.descriptor().exports());
                    System.out.println(reference.location());
                },
                () -> System.out.println("jdk.compiler unavailable")
            );
        }
    }

`ModuleFinder.ofSystem()` mô tả các module hệ thống mà runtime hiện tại có thể tìm thấy. Nó không phải trình quét mọi JAR của Maven hay Gradle.

Đừng nhầm “module hiện diện trong system module finder” với “module đã được resolve vào boot layer”. Có thể xem:

    boolean resolved = ModuleLayer.boot()
            .findModule("jdk.compiler")
            .isPresent();

Kết quả phụ thuộc cấu hình khởi chạy, root modules và resolution. Một module có thể quan sát được nhưng chưa nằm trong module graph của chương trình hiện tại.

Nếu cần tìm một module phụ thuộc tùy chọn, hãy kiểm tra sự hiện diện và cấu hình resolution thay vì dựa duy nhất vào filename của JAR.

## 6. java.compiler: API chuẩn cho trình biên dịch

Module `java.compiler` định nghĩa các API chuẩn phục vụ compiler và annotation processing:

    javax.tools.JavaCompiler
    javax.tools.ToolProvider
    javax.tools.JavaFileObject
    javax.annotation.processing.Processor
    javax.lang.model.element.Element
    javax.lang.model.type.TypeMirror

Nếu ứng dụng muốn yêu cầu hệ thống biên dịch một file Java thông qua Java Compiler API, có thể khai báo:

    module com.example.buildhelper {
        requires java.compiler;
    }

Sau đó:

    import javax.tools.JavaCompiler;
    import javax.tools.ToolProvider;

    public class CompileSample {
        public static void main(String[] args) {
            JavaCompiler compiler =
                    ToolProvider.getSystemJavaCompiler();

            if (compiler == null) {
                System.err.println(
                    "No system Java compiler in current runtime");
                return;
            }

            int code = compiler.run(
                    null,
                    System.out,
                    System.err,
                    "-d", "out",
                    "src/demo/Hello.java"
            );

            System.out.println("Compiler exit code: " + code);
        }
    }

`getSystemJavaCompiler()` trả về `null` nếu runtime không cung cấp compiler hệ thống. Ví dụ, một runtime image được tùy biến chỉ chứa các module cần chạy ứng dụng có thể không có compiler.

Điểm quan trọng là **source code gọi các API chuẩn từ `java.compiler`**, còn implementation compiler thực tế thường do `jdk.compiler` cung cấp trong JDK đầy đủ. Nếu chương trình cần compiler khi chạy, runtime phải có implementation thích hợp.

## 7. Khi nào cần requires jdk.compiler?

Không phải ứng dụng dùng `javac` đều cần khai báo:

    requires jdk.compiler;

Nếu ứng dụng **chỉ được javac biên dịch**, module app không cần `requires jdk.compiler` vì chỉ dùng compiler như một công cụ bên ngoài.

Nếu ứng dụng dùng các API chuẩn `javax.tools` hoặc `javax.lang.model`, thông thường dùng:

    requires java.compiler;

Nếu ứng dụng thật sự import API của module `jdk.compiler`, chẳng hạn Tree API hoặc Trees utility:

    import com.sun.source.tree.CompilationUnitTree;
    import com.sun.source.util.JavacTask;
    import com.sun.source.util.Trees;

khi đó module có thể cần:

    module com.example.analysis {
        requires jdk.compiler;
    }

Một số package `com.sun.source.*` là API công khai do `jdk.compiler` export để hỗ trợ phân tích source. Ngược lại, các package `com.sun.tools.javac.*` chứa nhiều implementation detail không được export rộng và không phải API ổn định.

**Không suy ra từ tiền tố `com.sun` rằng mọi API đều giống nhau**: kiểm tra exports trong descriptor và tài liệu API tương ứng.

## 8. Ví dụ sử dụng API phân tích source của javac

Nếu cần phân tích AST (Abstract Syntax Tree), có thể sử dụng `JavacTask` và `CompilationUnitTree` thay vì truy cập nội bộ compiler không được hỗ trợ.

Ví dụ:

    import com.sun.source.tree.CompilationUnitTree;
    import com.sun.source.util.JavacTask;
    import javax.tools.JavaCompiler;
    import javax.tools.StandardJavaFileManager;
    import javax.tools.ToolProvider;
    import java.util.List;

    public final class AstReader {
        public static void main(String[] args) throws Exception {
            JavaCompiler compiler =
                    ToolProvider.getSystemJavaCompiler();

            if (compiler == null) {
                throw new IllegalStateException(
                    "Compiler implementation unavailable");
            }

            try (StandardJavaFileManager files =
                    compiler.getStandardFileManager(
                        null, null, null)) {

                var source = files.getJavaFileObjects(
                        "src/demo/Hello.java");

                JavacTask task = (JavacTask) compiler.getTask(
                        null, files, null, List.of(), null, source);

                for (CompilationUnitTree unit : task.parse()) {
                    System.out.println(
                        unit.getSourceFile().getName());
                }
            }
        }
    }

Đây là ví dụ dùng API JDK cho AST. Tên module cung cấp implementation vẫn liên quan tới `jdk.compiler`; khi đóng gói thành named module, `requires jdk.compiler;` phù hợp với imports `com.sun.source.*`.

Hãy dùng public Tree API trước khi đụng tới các cấu trúc `com.sun.tools.javac.*` nội bộ. API công khai có hợp đồng hỗ trợ tốt hơn khi nâng JDK.

## 9. Annotation processors không phải lúc nào cần jdk.compiler

Một annotation processor thông thường thường dùng:

    javax.annotation.processing.AbstractProcessor
    javax.annotation.processing.RoundEnvironment
    javax.lang.model.element.TypeElement

Các API đó thuộc `java.compiler`.

Module processor có thể viết:

    module com.example.processor {
        requires java.compiler;

        provides javax.annotation.processing.Processor
            with com.example.processor.MyProcessor;
    }

Khi biên dịch module processor, cần đưa implementation vào processor path hoặc processor module path thích hợp để compiler phát hiện và chạy processor.

Không nên mặc định annotation processor nào cũng phải `requires jdk.compiler`. Chỉ thêm dependency đó nếu processor thực sự sử dụng các API `jdk.compiler` export.

Processor đời cũ có thể phụ thuộc vào `com.sun.tools.javac` nội bộ, gặp `IllegalAccessError` hoặc lỗi package visibility trên các JDK mới. Giải pháp bền vững thường là cập nhật processor hoặc đổi sang API chuẩn, không phải mở tất cả package nội bộ của `jdk.compiler`.

## 10. jdk.javadoc và công cụ tạo tài liệu

Module `jdk.javadoc` chứa implementation của công cụ `javadoc`. Khi chạy:

    javadoc -d docs -sourcepath src com.example.api

Javadoc sẽ phân tích source và sinh tài liệu HTML, tùy source layout và cấu hình command.

Một số API phát triển công cụ Javadoc nằm trong các package như:

    jdk.javadoc.doclet

Nếu viết doclet riêng và import API ở module `jdk.javadoc`, source module cần quan hệ đọc thích hợp, chẳng hạn:

    module com.example.doclet {
        requires jdk.javadoc;
    }

Điều này khác với việc đơn giản dùng command `javadoc` để tạo tài liệu cho một ứng dụng. Ứng dụng **không cần** `requires jdk.javadoc` chỉ vì pipeline build có bước tạo Javadoc.

Trong custom runtime image không có `jdk.javadoc`, những chức năng cần Javadoc implementation có thể không khả dụng. Hãy giữ nhiệm vụ sinh tài liệu ở môi trường build JDK nếu production không cần chúng.

## 11. jdk.jdeps: phân tích dependency khi modularize

`jdeps` là một công cụ quan trọng khi chuyển dự án legacy sang JPMS. Module hỗ trợ công cụ này là `jdk.jdeps`.

Ví dụ liệt kê dependency ở cấp module:

    jdeps --print-module-deps app.jar

Nếu phụ thuộc không nằm trong nguồn mà công cụ thấy được, có thể cần bổ sung classpath hoặc module path tương ứng.

Xem phụ thuộc vào nội bộ JDK:

    jdeps --jdk-internals app.jar

Lệnh này đặc biệt hữu ích khi ứng dụng hoặc thư viện cũ sử dụng API JDK nội bộ từng có thể truy cập từ classpath.

Đối với JAR yêu cầu module path riêng:

    jdeps --module-path libs --print-module-deps app.jar

`jdeps` hỗ trợ phân tích tĩnh dependency được biểu diễn trong class files; nó **không bảo đảm nhìn thấy mọi dependency được tạo động bằng reflection hoặc service discovery**.

Một ứng dụng chỉ dùng reflection theo tên class trong chuỗi có thể cần module runtime mà `jdeps` không phát hiện bằng phân tích static. Vì vậy, kết quả `jdeps` là cơ sở cho module graph, không phải bản kiểm kê tất cả thành phần chạy được.

## 12. jdk.jlink: tạo runtime image theo modules

`jlink` giúp tạo một Java runtime image chỉ chứa các module được yêu cầu và dependency cần thiết của chúng. Công cụ liên quan tới module `jdk.jlink`.

Ví dụ:

    jlink --add-modules java.base,java.logging
          --output image

Runtime image này có thể phù hợp với ứng dụng chỉ cần một tập API nhỏ. Tuy nhiên, nó không nhất thiết chứa compiler, Javadoc, JShell hay các công cụ phát triển khác.

Nếu ứng dụng thực sự cần compiler ở runtime:

    jlink --add-modules java.base,jdk.compiler
          --output image-with-compiler

Module graph của `jdk.compiler` kéo theo những module phụ thuộc phù hợp khi image được tạo.

Khi triển khai production, **không thêm tất cả module `jdk.*` chỉ vì chúng có trong full JDK**. Đưa vào những module thực sự cần cho ứng dụng để giảm kích thước và bề mặt phụ thuộc.

Ngoài ra, lưu ý **JMOD** và **modular JAR** khác nhau: các file `.jmod` trong thư mục `jmods` của JDK hỗ trợ công cụ như `jlink`; chúng không phải artifact JAR để chương trình tùy ý nạp trên application module path bằng Java launcher.

## 13. jdk.jshell: thử mã và API JShell

JShell cung cấp môi trường REPL (Read-Eval-Print Loop) để chạy đoạn mã Java ngắn:

    jshell

Trong JShell có thể thử:

    jshell> 1 + 2

Bên cạnh công cụ dòng lệnh, module `jdk.jshell` cung cấp API công khai như `jdk.jshell.JShell`.

Một ứng dụng xây dựng giao diện học Java hoặc IDE plugin có thể dùng:

    module com.example.repl {
        requires jdk.jshell;
    }

Ví dụ tạo một JShell instance:

    import jdk.jshell.JShell;

    public class MiniRepl {
        public static void main(String[] args) {
            try (JShell shell = JShell.create()) {
                shell.eval("int total = 3 + 4;");
                shell.eval("System.out.println(total);");
            }
        }
    }

Nếu application chỉ được build bằng JDK có công cụ `jshell` nhưng không import API JShell, **không cần** thêm `requires jdk.jshell`.

Hãy nhớ rằng JShell có cơ chế execution environment riêng; việc sử dụng JShell API trong ứng dụng nhúng phải cân nhắc vòng đời tài nguyên và môi trường thực thi snippet.

## 14. Một số jdk.* module có API ở runtime

Không phải module `jdk.*` nào cũng chỉ phục vụ build:

**`jdk.jfr` — Java Flight Recorder**

Cung cấp API quan sát hiệu năng và sự kiện runtime:

    module com.example.monitoring {
        requires jdk.jfr;
    }

Có thể sử dụng API `jdk.jfr.Recording` hoặc event phù hợp khi ứng dụng cần JFR.

**`jdk.attach` — Attach API**

Cung cấp các kiểu như `com.sun.tools.attach.VirtualMachine`. Khả năng attach phụ thuộc nền tảng, quyền tiến trình, chính sách bảo mật và runtime image; không phải lúc nào ứng dụng cũng được phép attach JVM khác.

**`jdk.management` — mở rộng quản lý JVM**

Cung cấp các API quản lý mở rộng trong package `com.sun.management`. Phân biệt với API JMX chuẩn như `java.management`.

**`jdk.httpserver` — HTTP server nhỏ**

Cung cấp `com.sun.net.httpserver.HttpServer`, đôi khi hữu ích cho công cụ phát triển, test hoặc demo. Khi source import kiểu thuộc package này, named module cần:

    requires jdk.httpserver;

Không nên hiểu mọi module `jdk.*` đều là implementation detail không dùng được; một số export API công khai của JDK. Điều quan trọng là **đúng API, đúng module, đúng runtime**.

## 15. jdk.unsupported và ranh giới API nội bộ

`jdk.unsupported` tồn tại nhằm hỗ trợ một số API không chuẩn từng được phần mềm sử dụng rộng rãi, chẳng hạn một số kiểu `sun.misc`.

Sự tồn tại của module này **không biến mọi API nội bộ JDK thành API chuẩn**. Một API được export từ `jdk.unsupported` vẫn có thể có ràng buộc tương thích khác với API Java SE.

Ví dụ:

- Không thay `java.util.concurrent`, `VarHandle` hoặc API chuẩn khác bằng kiểu `Unsafe` chỉ để thuận tiện.
- Không xem `--add-exports` vào `jdk.internal.*` là giải pháp kiến trúc lâu dài.
- Khi thấy thư viện phụ thuộc vào `sun.*` hoặc `com.sun.tools.javac.*`, kiểm tra phiên bản thư viện và khả năng nâng cấp.

Dùng `jdeps --jdk-internals` để tìm dấu hiệu tham chiếu nội bộ JDK khi cần lập kế hoạch migration.

## 16. --add-modules dùng khi nào?

Khi chạy chương trình Java trên classpath hoặc với module roots cụ thể, không phải module hệ thống có sẵn nào cũng tự động được resolve vào boot layer.

Tùy chọn launcher:

    --add-modules module.name

bổ sung các module được chỉ định vào tập root cần resolve.

Ví dụ:

    java --add-modules jdk.compiler -cp app.jar com.example.Main

Nếu chương trình cần một tool provider do `jdk.compiler` cung cấp mà runtime đang không resolve module đó theo cấu hình mặc định, `--add-modules` có thể là phần của cấu hình phù hợp.

Nhưng **`--add-modules` không tạo module còn thiếu trong Java image**. Nếu custom runtime không chứa `jdk.compiler`, thêm root module name vẫn không thể khôi phục implementation.

Đối với named module có:

    requires jdk.compiler;

JPMS sẽ resolve dependency theo `requires` nếu module thực sự có sẵn; thông thường không cần lặp lại tên module đó trong `--add-modules`.

## 17. ToolProvider: hai API có tên giống nhau

Java có hai cách truy cập công cụ dễ gây nhầm:

1. `javax.tools.ToolProvider` thuộc `java.compiler`, dùng để lấy compiler hoặc documentation tool theo API chuẩn.
2. `java.util.spi.ToolProvider` thuộc `java.base`, là service-provider abstraction cho các công cụ dòng lệnh được JDK expose qua cơ chế tool providers.

Ví dụ với Java compiler API:

    JavaCompiler compiler =
        javax.tools.ToolProvider.getSystemJavaCompiler();

Ví dụ tìm công cụ dòng lệnh:

    import java.util.spi.ToolProvider;

    public class ToolDemo {
        public static void main(String[] args) {
            ToolProvider.findFirst("javac").ifPresentOrElse(
                tool -> {
                    int code = tool.run(
                        System.out, System.err, "--version");
                    System.out.println("Exit: " + code);
                },
                () -> System.out.println("javac tool not available")
            );
        }
    }

Dù cả hai có tên `ToolProvider`, chúng khác package, API và mục đích.

Khả năng tìm thấy một tool provider tùy vào các module/tool có mặt và được resolve trong Java runtime image. Nếu không tìm thấy, `Optional` rỗng không có nghĩa file source của ứng dụng bị lỗi.

## 18. Module path và system modules không giống nhau

Ứng dụng có thể có:

    --module-path libs:mods

để tìm **application/library modules**. Trong khi đó, các module JDK như `java.base`, `jdk.compiler`, `jdk.jfr` thường đến từ **system module image** của runtime.

Điểm cần nhớ:

- Module path cung cấp thêm application modules và thư viện.
- System modules được runtime cung cấp theo JDK image đang chạy.
- Cùng một source code có thể chạy trên full JDK nhưng lỗi trên custom runtime image thiếu `jdk.*` module cần thiết.
- Đưa một JAR lên classpath không phải cách thêm `jdk.compiler` vào system image bị cắt bỏ.

Khi kiểm tra một ứng dụng đã đóng gói, hãy chạy:

    java --list-modules

bằng **Java executable của image thực tế** chứ không chỉ bằng `java` từ JDK cài đặt toàn hệ thống.

## 19. Lỗi thường gặp với jdk.* modules

| Lỗi hoặc triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| `error: module not found: jdk.compiler` | Compile JDK/toolchain không chứa module, hoặc cấu hình không dùng đúng JDK | Xác định `javac` đang chạy từ JDK nào; kiểm tra `java --list-modules` |
| `FindException: Module jdk.compiler not found` | Runtime image không có `jdk.compiler` | Dùng JDK/image có module hoặc tạo lại image bằng `jlink` |
| `getSystemJavaCompiler() == null` | Không có system compiler implementation | Kiểm tra module `jdk.compiler` và runtime thực tế |
| `IllegalAccessError` với `com.sun.tools.javac.*` | Processor/tool phụ thuộc nội bộ compiler bị đóng gói | Cập nhật công cụ, chuyển sang API chuẩn hoặc API export công khai |
| `package com.sun.source... is not visible` | Chưa đọc `jdk.compiler` hoặc cấu hình module path/exports sai | Kiểm tra `requires jdk.compiler` và descriptor |
| `jdeps` không có trong image | Image không đóng gói công cụ/module liên quan | Dùng full JDK build image hoặc runtime chứa tool nếu thực sự cần |
| JShell không khởi động | Thiếu module/tool trong image hoặc sai Java executable | Kiểm tra danh sách module, launcher, quyền thực thi |
| `ClassNotFoundException` với API `jdk.*` | Module chưa resolve, image thiếu module hoặc classpath/module configuration sai | Xác định module thực tế, thêm `requires` hoặc cấu hình roots đúng |

Không suy luận tất cả lỗi đều do `--module-path` thiếu JAR. Với system modules, vấn đề có thể là Java image đã lược bỏ module, hoặc dự án đang chạy bằng một JDK/toolchain khác với bản biên dịch.

## 20. Maven, Gradle và nhiều JDK versions

Trong Maven, compiler plugin và test plugin có thể sử dụng JDK/toolchain khác với JVM chạy Maven:

- Maven process có thể chạy trên một JDK.
- `maven-compiler-plugin` có thể dùng toolchain riêng.
- Surefire/Failsafe có thể khởi chạy JVM test riêng.
- Production image có thể là custom runtime không có các developer modules.

Với Gradle cũng cần phân biệt JVM chạy Gradle daemon, Java toolchain cho compile, JVM cho test và JVM ứng dụng.

Một đoạn code import `jdk.jshell` có thể compile thành công bằng full JDK nhưng không chạy trên image được tạo chỉ với `java.base` và dependencies của module app nếu `jdk.jshell` không được đưa vào.

Để giảm sai lệch giữa các môi trường, nên kiểm tra:

1. Phiên bản JDK thực tế của từng công cụ.
2. Module `jdk.*` có nằm trong runtime image dùng cho từng bước không.
3. Build/test tool có dùng API chuẩn `java.compiler` hay import implementation internals.
4. Các JVM test và production có cùng tập modules cần thiết không.
5. Việc đóng gói custom image có bao gồm dependency runtime thực sự không.

**Developer tools** nên nằm trong build environment nếu production không cần chúng. Không phải runtime ứng dụng nào cũng cần mang theo compiler, Javadoc hoặc JShell.

## 21. Quy trình chẩn đoán khi thiếu jdk.* module

Khi gặp lỗi liên quan `jdk.compiler`, `jdk.jlink`, `jdk.jfr` hoặc module JDK khác, hãy thực hiện:

**Bước 1 — Xác định công cụ đang lỗi.**

Lỗi xảy ra khi chạy `javac`, Maven/Gradle build, unit tests hay trong Java runtime image?

**Bước 2 — Xác định tên module chính xác.**

Xem `requires` trong `module-info.java` hoặc module name trong stack trace.

**Bước 3 — Kiểm tra Java executable của đúng môi trường.**

    java --version
    java --list-modules

Nếu cần kiểm tra descriptor:

    java --describe-module jdk.compiler

**Bước 4 — Phân biệt thiếu module với thiếu readability hoặc exports.**

Nếu module không có trong image, `--add-exports` hay `--add-opens` sẽ không làm nó xuất hiện. Nếu module có nhưng package không được export, phải xem API đó có được hỗ trợ hay không.

**Bước 5 — Xem module graph đang resolve.**

    java --show-module-resolution -m com.example.app/com.example.Main

Lệnh trên là ví dụ khởi chạy một named module. Điều chỉnh module path và main class theo ứng dụng thực tế.

**Bước 6 — Quyết định cách sửa nhỏ nhất.**

- Cần Java Compiler API: dùng `requires java.compiler` và bảo đảm implementation compiler có mặt khi chạy.
- Cần public Tree API: dùng `requires jdk.compiler`.
- Cần JFR API: dùng `requires jdk.jfr`.
- Chỉ cần chạy `jdeps` trong CI: sử dụng JDK build có `jdeps`, không thêm dependency đó vào production module.
- Thiếu trong custom image: cấu hình lại `jlink` hoặc loại bỏ nhu cầu dùng module đó tại runtime.

## 22. Những nhầm lẫn thường gặp

- **Tưởng mọi `jdk.*` module đều là nội bộ không bao giờ được dùng.** Một số module export API công khai như `jdk.jfr`, `jdk.jshell`, `com.sun.source.*`.
- **Tưởng mọi package trong `jdk.compiler` đều public.** Nhiều implementation package không được export hoặc không có cam kết ổn định.
- **Tưởng ứng dụng được `javac` biên dịch phải `requires jdk.compiler`.** Build tool dùng compiler bên ngoài không tạo dependency runtime tự động.
- **Tưởng `java.compiler` và `jdk.compiler` là cùng module.** Một module chứa API chuẩn, module kia chủ yếu cung cấp implementation và một số API công cụ JDK.
- **Tưởng có command `jdeps` nghĩa application cần `requires jdk.jdeps`.** Công cụ build và dependency của ứng dụng là hai tầng khác nhau.
- **Tưởng `--add-modules` tải lại một module đã bị jlink cắt bỏ.** Nếu image không có module, phải chọn image khác hoặc tạo lại image.
- **Tưởng module có mặt thì luôn nằm trong boot layer.** Cần phân biệt observable system module với module đã resolve.
- **Tưởng `com.sun.source.*` giống các package `com.sun.tools.javac.*` nội bộ.** Hãy xem exports, API docs và mục đích package.
- **Tưởng classpath chứa JAR là cách cung cấp compiler trong custom image.** Compiler implementation là module của runtime image, không phải JAR thông thường.
- **Tưởng JVM production, JVM test và JVM build luôn dùng cùng JDK.** Toolchains hoặc cấu hình triển khai có thể khác nhau.

## Ghi nhớ

- Các module `jdk.*` cung cấp nhiều công cụ và khả năng riêng của JDK, như compiler, Javadoc, dependency analysis, runtime-image creation, JShell và monitoring.
- `java.compiler` là API Java Compiler chuẩn; `jdk.compiler` cung cấp implementation và API phân tích source do JDK export.
- Chỉ khai báo `requires jdk.*` khi **source module thực sự dùng API hoặc runtime service của module đó**; không thêm chỉ vì lệnh build có sử dụng công cụ JDK.
- Dùng `java --list-modules`, `java --describe-module`, `ModuleFinder.ofSystem()` và `jdeps` để chẩn đoán.
- Custom runtime image có thể không chứa developer modules; `--add-modules` không khôi phục module không tồn tại.
- Ưu tiên API chuẩn và API được JDK export công khai, tránh phụ thuộc vào các implementation package nội bộ khi có thể.

Hiểu rõ ranh giới giữa **API Java SE**, **module triển khai của JDK** và **command-line build tool** sẽ giúp ứng dụng modular có dependency chính xác, đồng thời tránh lỗi khi thay JDK, nâng phiên bản toolchain hoặc triển khai bằng runtime image tối giản.