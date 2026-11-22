# Phân biệt module java.compiler với triển khai trong jdk.compiler

Trong Java 9+, **Java Compiler API** được tổ chức theo hệ thống module. Có hai tên thường xuất hiện gần nhau nhưng đảm nhiệm những trách nhiệm khác nhau:

- **`java.compiler`**: module **chuẩn Java SE** định nghĩa các **interface, class và hợp đồng API** dùng để gọi compiler, nhận diagnostics, mô hình hóa phần tử/kiểu Java và viết annotation processor.
- **`jdk.compiler`**: module thuộc **JDK**, cung cấp **triển khai javac**, chương trình biên dịch hệ thống, các service providers tương ứng và **Compiler Tree API** để đọc cây cú pháp của mã nguồn.

Một phép so sánh dễ nhớ: **`java.compiler` là hợp đồng; `jdk.compiler` là một bên thực hiện hợp đồng ấy và cung cấp thêm công cụ phân tích AST**. Có hợp đồng không nhất thiết có triển khai trong runtime image hiện tại. Và không phải mọi class xuất hiện trong module `jdk.compiler` đều là API công khai được khuyến khích sử dụng.

## 1. Vì sao Java tách API và implementation?

Một chương trình quản lý IDE, build tool, hệ thống chấm bài hoặc công cụ phân tích mã cần một cách có cấu trúc để yêu cầu compiler biên dịch mã nguồn. Thay vì phụ thuộc trực tiếp vào lớp nội bộ của một bản javac, Java cung cấp những interface chung như **`javax.tools.JavaCompiler`**.

Một môi trường triển khai Java SE có thể cung cấp phần API nhưng **không kèm trình biên dịch**. Chẳng hạn ứng dụng chạy trên custom runtime image được tạo bằng `jlink` và chỉ bao gồm những module cần thiết. Việc thiếu compiler là một lựa chọn đóng gói, không phải lỗi của interface.

Thiết kế tách biệt mang lại:

1. **Ranh giới ổn định** cho code dùng Java Compiler API.
2. **Khả năng thay thế triển khai** ở những nơi có compiler phù hợp với SPI.
3. **Tránh buộc mọi runtime** mang theo đầy đủ mã javac.
4. **Phân biệt công cụ chuẩn Java SE** với phần mở rộng JDK phục vụ phân tích cây cú pháp.
5. **Encapsulation** cho những package implementation mà javac cần tự thay đổi khi phát triển.

Từ đó, cách viết phụ thuộc đúng là: dùng `javax.tools` khi chỉ cần biên dịch và thu diagnostics; chọn `com.sun.source.*` khi bài toán cần AST; tránh can thiệp vào `com.sun.tools.javac.*` nội bộ.

## 2. Bảng đối chiếu trực tiếp

| Tiêu chí | Module java.compiler | Module jdk.compiler |
| --- | --- | --- |
| Bản chất | API và SPI chuẩn Java SE | Triển khai compiler của JDK và API cây cú pháp |
| Đảm bảo có implementation compiler? | **Không** | Cung cấp javac của JDK |
| Package đặc trưng | `javax.tools`, `javax.lang.model.*`, `javax.annotation.processing` | `com.sun.source.tree`, `com.sun.source.util`, `com.sun.source.doctree` |
| Đối tượng sử dụng | IDE, build tool, JavaCompiler client, annotation processor | Trình biên dịch javac, công cụ phân tích AST, plugin javac |
| Compiler interface | Định nghĩa `javax.tools.JavaCompiler` | Cung cấp implementation của `javax.tools.JavaCompiler` |
| Phần mở rộng theo JDK | Không cần để diễn tả compiler API cơ bản | Có Tree API và implementation cụ thể |
| Phụ thuộc module | Phụ thuộc nền tảng Java | **`requires transitive java.compiler`** |
| Runtime image thiếu jdk.compiler | API vẫn có thể tồn tại | Không có javac implementation này |
| Phạm vi ổn định | API Java SE | Public exported Tree API có tài liệu; package nội bộ không có cùng cam kết |
| Module-info.java client | Thường `requires java.compiler;` | `requires jdk.compiler;` khi dùng Compiler Tree API |

**Không đánh đồng tên module và tên package.** `java.compiler` là tên module; `javax.tools` là package. Tương tự, `jdk.compiler` là module nhưng Java source có thể sử dụng các package được xuất như `com.sun.source.tree`. Module name không phải một câu lệnh import.

**Không đánh đồng module `jdk.compiler` với toàn bộ namespace `com.sun.tools.javac`.** Một vài entry point legacy được xuất, nhưng hầu hết lớp trong các subpackage implementation là nội bộ, không được bảo đảm tương thích.

## 3. Các package trong java.compiler

Trang mô tả chính thức của module `java.compiler` liệt kê các package được exports:

| Package | Chức năng |
| --- | --- |
| `javax.tools` | Gọi compiler từ chương trình, cung cấp file objects và file manager, xử lý diagnostics |
| `javax.annotation.processing` | Khai báo và thực hiện annotation processing qua `Processor`, `RoundEnvironment`, `ProcessingEnvironment`, `Filer` và `Messager` |
| `javax.lang.model` | Khái niệm chung về mô hình ngôn ngữ Java |
| `javax.lang.model.element` | Biểu diễn package, class, method, field, parameter, annotation trong mô hình phần tử |
| `javax.lang.model.type` | Biểu diễn kiểu, primitive, declared type, executable type, type variable... |
| `javax.lang.model.util` | Tiện ích làm việc với `Elements`, `Types` và các đối tượng mô hình |

Đây là **API** chứ không phải mã cài đặt chi tiết bộ phân tích cú pháp của javac. Ví dụ, `javax.lang.model.element.TypeElement` biểu diễn một loại khai báo Java ở mức language model; nó **không phải** AST node chứa tất cả token, dấu ngoặc và cấu trúc expression.

### 3.1. Những interface/classes quan trọng trong javax.tools

- **`JavaCompiler`**: interface của compiler được gọi bằng API.
- **`JavaCompiler.CompilationTask`**: một tác vụ biên dịch có thể được chạy qua `call()`.
- **`ToolProvider`** trong package `javax.tools`: điểm truy cập system Java compiler có sẵn.
- **`JavaFileObject`** và **`SimpleJavaFileObject`**: trừu tượng hóa tệp nguồn hoặc class.
- **`JavaFileManager`** và **`StandardJavaFileManager`**: quản lý nguồn, class output và đường dẫn các tệp đầu vào.
- **`Diagnostic`**, **`DiagnosticListener`**, **`DiagnosticCollector`**: nhận loại lỗi, nội dung và vị trí diagnostic có cấu trúc.
- **`Tool`**: giao diện chung cho một công cụ có thể được gọi trong Java.

Các API này giúp một chương trình nhúng logic biên dịch **mà không phải parse chuỗi stderr của lệnh javac**. Tuy vậy, kết quả của compilation task còn phụ thuộc processor, classpath, file manager, phiên bản compiler và các tùy chọn cụ thể.

### 3.2. Annotation processor cũng dựa trên java.compiler

Một processor thường được viết bằng:

~~~java
import javax.annotation.processing.AbstractProcessor;
import javax.annotation.processing.RoundEnvironment;
import javax.annotation.processing.SupportedAnnotationTypes;
import javax.annotation.processing.SupportedSourceVersion;
import javax.lang.model.SourceVersion;
import javax.lang.model.element.TypeElement;
import java.util.Set;

@SupportedAnnotationTypes("*")
@SupportedSourceVersion(SourceVersion.RELEASE_17)
public class CheckProcessor extends AbstractProcessor {
    @Override
    public boolean process(
            Set<? extends TypeElement> annotations,
            RoundEnvironment roundEnv) {
        return false;
    }
}
~~~

Đây là ví dụ **lớp processor hoàn chỉnh về cú pháp nhưng chưa có logic xử lý**, không phải ứng dụng có hàm main để chạy trực tiếp. Các class `AbstractProcessor`, `RoundEnvironment` và `TypeElement` đều đến từ `java.compiler`.

**Không nên tự import lớp implementation từ `com.sun.tools.javac.processing` chỉ để viết một annotation processor.** API `javax.annotation.processing` và language model giúp processor bớt gắn chặt vào internals của javac.

## 4. Những gì jdk.compiler thực sự bổ sung

Module `jdk.compiler` định nghĩa **triển khai system Java compiler** và tương đương dòng lệnh `javac`. Nó cung cấp các service provider cho:

- **`javax.tools.JavaCompiler`**, tức implementation của Java Compiler SPI.
- **`javax.tools.Tool`**, để gọi công cụ theo cách API.
- **`java.util.spi.ToolProvider`**, để tìm công cụ dòng lệnh theo tên, ví dụ `javac`.

Ngoài ra, module này exports các package công khai phục vụ truy cập cây cú pháp:

| Public exported package | Công dụng |
| --- | --- |
| `com.sun.source.tree` | Interface biểu diễn AST của mã Java (class, statement, expression, type...) |
| `com.sun.source.doctree` | Cây cú pháp của nội dung tài liệu JavaDoc |
| `com.sun.source.util` | `JavacTask`, `TreePath`, `TreePathScanner`, `Trees`, `SourcePositions` và tiện ích duyệt/phân tích cây |

Tài liệu module `jdk.compiler` cũng liệt kê package **`com.sun.tools.javac`** chứa entry point **legacy javac API**. Không nên vì thế suy ra toàn bộ các subpackage `com.sun.tools.javac.api`, `com.sun.tools.javac.code`, `com.sun.tools.javac.comp`, `com.sun.tools.javac.parser`... đều là exported public API. Nhiều package chỉ mở/export có điều kiện cho module của JDK hoặc không exported ra module của ứng dụng.

**Phân loại đúng:**

1. **`javax.tools.`***: API chuẩn trong `java.compiler`.
2. **`com.sun.source.`***: public Compiler Tree API trong `jdk.compiler`, có tài liệu nhưng phụ thuộc javac/JDK.
3. **`com.sun.tools.javac.`***: phần lớn là implementation internals; không dùng làm dependency API mặc định.

### 4.1. Quan hệ requires transitive

Trong module descriptor của `jdk.compiler`, quan hệ phụ thuộc đến `java.compiler` là **transitive**. Vì vậy module cần `jdk.compiler` cũng đọc được `java.compiler` theo quy tắc readability của JPMS.

~~~text
module tool.ast
    |
    | requires jdk.compiler
    v
jdk.compiler
    |
    | requires transitive java.compiler
    v
java.compiler
~~~

Điều đó **không đảo chiều**. Module chỉ khai báo `requires java.compiler;` không tự được cấp implementation `jdk.compiler` hoặc Tree API.

## 5. Kiểm tra module ở JDK đang dùng

Các lệnh sau giúp nhận diện thành phần mà JDK thực sự có:

~~~bash
java -version
javac -version
java --describe-module java.compiler
java --describe-module jdk.compiler
~~~

Trên JDK 21, output mô tả module cho thấy `java.compiler` exports `javax.tools` và `javax.lang.model.*`; còn `jdk.compiler` exports `com.sun.source.*`, `requires java.compiler transitive` và `provides javax.tools.JavaCompiler`.

**Không coi số phiên bản và toàn bộ dòng output là bất biến**: `java --describe-module` có thể hiển thị thêm requires, exports hoặc service providers theo bản JDK. Điều cần xác nhận là cấu trúc quyền và service, không phải định dạng chính xác của mỗi dòng.

Ví dụ module summary trong JDK 21 có những dòng mang ý nghĩa:

~~~text
java.compiler:
  exports javax.tools
  exports javax.annotation.processing
  exports javax.lang.model...

jdk.compiler:
  requires java.compiler transitive
  exports com.sun.source.tree
  exports com.sun.source.util
  provides javax.tools.JavaCompiler ...
~~~

Đây là **trích lược diễn giải**, không phải bản ghi stdout nguyên văn.

Để xem toàn bộ module của runtime:

~~~bash
java --list-modules
~~~

Một runtime image tạo bằng `jlink` có thể chứa `java.compiler` nhưng không chứa `jdk.compiler`. Vì thế đừng mặc định “lệnh java chạy được” nghĩa là “javac có sẵn trong cùng runtime image”.

## 6. Ví dụ runnable 1: quan sát module của API và implementation

Tạo **ModuleProbe.java**:

~~~java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;
import com.sun.source.tree.Tree;

public class ModuleProbe {
    public static void main(String[] args) {
        System.out.println(JavaCompiler.class.getModule().getName());
        System.out.println(ToolProvider.class.getModule().getName());
        System.out.println(Tree.class.getModule().getName());

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        System.out.println(compiler != null);

        if (compiler != null) {
            System.out.println(
                compiler.getClass().getModule().getName()
            );
        }

        System.out.println(
            java.util.spi.ToolProvider
                .findFirst("javac")
                .isPresent()
        );
    }
}
~~~

Biên dịch và chạy với **JDK 17+ đầy đủ**, ví dụ JDK 21:

~~~bash
javac ModuleProbe.java
java ModuleProbe
~~~

**Standard output đã kiểm chứng trên OpenJDK 21:**

~~~text
java.compiler
java.compiler
jdk.compiler
true
jdk.compiler
true
~~~

Giải thích từng dòng:

1. Interface `JavaCompiler` thuộc `java.compiler`.
2. Class `javax.tools.ToolProvider` cũng thuộc `java.compiler`.
3. Interface `com.sun.source.tree.Tree` thuộc `jdk.compiler`.
4. System compiler hiện diện trên JDK đầy đủ, nên phép so sánh khác null là `true`.
5. Object triển khai compiler thực tế là class trong module `jdk.compiler`.
6. `java.util.spi.ToolProvider.findFirst("javac")` tìm thấy công cụ javac qua service provider, nên `isPresent()` là `true`.

Đây là **một cách chứng minh module ownership**, không phải cách khuyên ứng dụng phụ thuộc tên concrete class trả về ở dòng 5. Một bản triển khai compiler khác có thể dùng class implementation khác.

### 6.1. Hai lớp ToolProvider trùng simple name

Có **hai API ToolProvider khác nhau** trong các package khác nhau:

| Tên đầy đủ | Module | Vai trò |
| --- | --- | --- |
| `javax.tools.ToolProvider` | `java.compiler` | Truy cập compiler hệ thống bằng `getSystemJavaCompiler()` |
| `java.util.spi.ToolProvider` | `java.base` | API dịch vụ chung cho các command-line tools, có `findFirst("javac")` |

Đừng nhầm:

~~~java
// Đúng: trả về JavaCompiler hoặc null
javax.tools.JavaCompiler compiler =
        javax.tools.ToolProvider.getSystemJavaCompiler();

// Đúng: trả về Optional<ToolProvider> cho công cụ javac
var commandTool =
        java.util.spi.ToolProvider.findFirst("javac");
~~~

Đoạn trên là **mảnh mã đặt trong một method**, không phải chương trình độc lập. Chúng dùng cùng chuỗi “ToolProvider” nhưng **khác package, module, kiểu trả về và mục đích**.

**`javax.tools.ToolProvider` không phải implementation javac**: nó là class API dùng để tìm compiler được cung cấp trong runtime hiện tại.

## 7. Ví dụ runnable 2: gọi JavaCompiler qua API chuẩn

Bài này không cần import `com.sun.tools.javac.*` hoặc `com.sun.source.*`. Nó dùng phần interface trong `java.compiler`, nhận một source Java trong bộ nhớ, biên dịch và thu diagnostic.

Tạo **ApiCompile.java**:

~~~java
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class ApiCompile {
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();

        if (compiler == null) {
            System.out.println("No system Java compiler");
            return;
        }

        String source =
                "public class Sample { int number = 42; }";

        JavaFileObject input = new SimpleJavaFileObject(
                URI.create("string:///Sample.java"),
                JavaFileObject.Kind.SOURCE) {
            @Override
            public CharSequence getCharContent(
                    boolean ignoreEncodingErrors) {
                return source;
            }
        };

        Path output =
                Files.createTempDirectory("java-compiler-demo-");

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager manager =
                    compiler.getStandardFileManager(
                        diagnostics, null, null)) {

            Boolean ok = compiler.getTask(
                null,
                manager,
                diagnostics,
                List.of("-proc:none", "-d", output.toString()),
                null,
                List.of(input)
            ).call();

            System.out.println("compiled=" + ok);
            System.out.println(
                "diagnostics=" + diagnostics.getDiagnostics().size()
            );
            System.out.println(
                "class-file=" +
                Files.exists(output.resolve("Sample.class"))
            );
        }
    }
}
~~~

Lệnh:

~~~bash
javac ApiCompile.java
java ApiCompile
~~~

**Stdout đã kiểm chứng trên OpenJDK 21:**

~~~text
compiled=true
diagnostics=0
class-file=true
~~~

Giải thích các thành phần:

- `SimpleJavaFileObject` mô phỏng tệp `Sample.java` trong bộ nhớ.
- `JavaCompiler.getTask(...)` tạo một compilation task; `call()` thực hiện task.
- `StandardJavaFileManager` xử lý output vật lý của compiler. Ví dụ tạo một thư mục tạm bằng `Files.createTempDirectory` và đóng manager sau khi dùng.
- `DiagnosticCollector` nhận lỗi/cảnh báo có cấu trúc; sample hợp lệ không phát diagnostic trong cấu hình thử nghiệm.
- `-proc:none` ngăn annotation processors hoạt động ngoài ý muốn; đây là lựa chọn của **task** chứ không phải module khác.

**Điều cần chú ý:** `JavaCompiler` và các interface sử dụng nằm trong `java.compiler`, nhưng vì đang chạy JDK có `jdk.compiler`, `ToolProvider` mới tìm được implementation để thực hiện biên dịch. Không cần import tên cụ thể của `com.sun.tools.javac.api.JavacTool` để thực hiện tác vụ.

Đây là ví dụ **có thể tự chạy độc lập**; file `Sample.class` được tạo trong một thư mục tạm mới, không ghi vào thư mục output của dự án.

### 7.1. Khi compiler không có sẵn

Code đã kiểm tra:

~~~java
JavaCompiler compiler =
        ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    System.out.println("No system Java compiler");
    return;
}
~~~

Đây là một **đường xử lý hợp lệ** theo contract của API. `getSystemJavaCompiler()` có thể trả null khi nền tảng hiện tại không cung cấp compiler. Không nên viết công cụ production theo giả định rằng mọi máy chạy Java đều có system compiler.

Một lần nữa: **không có compiler implementation** khác với **không có interface javax.tools.JavaCompiler**. Interface có thể nằm trong `java.compiler` nhưng service cung cấp triển khai không tồn tại.

## 8. Ví dụ runnable 3: Compiler Tree API nằm trong jdk.compiler

Nếu chỉ cần biên dịch và thu diagnostics, `javax.tools` là đủ. Nhưng nếu muốn **đọc AST** để viết static analyzer, hỗ trợ IDE, kiểm tra cấu trúc method hoặc biểu thức, có thể dùng **Compiler Tree API** từ `jdk.compiler`.

Tạo **InspectTree.java**:

~~~java
import com.sun.source.tree.CompilationUnitTree;
import com.sun.source.tree.Tree;
import com.sun.source.tree.VariableTree;
import com.sun.source.util.JavacTask;
import com.sun.source.util.TreePathScanner;

import java.net.URI;
import java.util.List;

import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.ToolProvider;

public class InspectTree {
    public static void main(String[] args) throws Exception {
        String text =
                "class Sample { int answer = 2 + 3 * 4; }";

        JavaFileObject input = new SimpleJavaFileObject(
                URI.create("string:///Sample.java"),
                JavaFileObject.Kind.SOURCE) {
            @Override
            public CharSequence getCharContent(
                    boolean ignoreEncodingErrors) {
                return text;
            }
        };

        JavaCompiler compiler =
                ToolProvider.getSystemJavaCompiler();

        if (compiler == null) {
            System.out.println("Compiler unavailable");
            return;
        }

        JavacTask task = (JavacTask) compiler.getTask(
                null,
                null,
                null,
                List.of("-proc:none"),
                null,
                List.of(input)
        );

        for (CompilationUnitTree unit : task.parse()) {
            for (Tree declaration : unit.getTypeDecls()) {
                System.out.println(declaration.getKind());
            }

            new TreePathScanner<Void, Void>() {
                @Override
                public Void visitVariable(
                        VariableTree variable, Void unused) {
                    if (variable.getName()
                            .contentEquals("answer")) {
                        System.out.println(
                            variable.getInitializer().getKind()
                        );
                    }
                    return super.visitVariable(variable, unused);
                }
            }.scan(unit, null);
        }
    }
}
~~~

Biên dịch và chạy với JDK 17+ đầy đủ:

~~~bash
javac InspectTree.java
java InspectTree
~~~

**Stdout đã kiểm chứng trên OpenJDK 21:**

~~~text
CLASS
PLUS
~~~

Cây phân tích có một class declaration và initializer của biến `answer` có toán tử `PLUS` ở ngoài: `2 + (3 * 4)`. Chương trình minh họa chỉ **parse()**; nó chưa gọi `analyze()` hay `generate()` nên không khẳng định đã kiểm tra kiểu toàn diện hoặc sinh bytecode cho input.

Trong ví dụ, task được lấy bằng `javax.tools.JavaCompiler.getTask(...)` nhưng được ép sang `com.sun.source.util.JavacTask`, là API đặc thù javac để truy cập parse/analysis. Điều này hợp lệ khi provider thực tế hỗ trợ `JavacTask` (như javac trong JDK đã thử), **không được giả định mọi triển khai JavaCompiler bên ngoài đều trả về JavacTask**.

**Vì sao `java.compiler` một mình không đủ?** Vì các interface `CompilationUnitTree`, `Tree`, `VariableTree` và tiện ích `JavacTask`, `TreePathScanner` thuộc module `jdk.compiler`. Cần JDK/runtime chứa module ấy để biên dịch và chạy công cụ dựa trên Tree API.

## 9. Khai báo module-info.java cho client

### 9.1. Chỉ dùng API chuẩn

Nếu module ứng dụng chỉ gọi JavaCompiler và thu diagnostics:

~~~java
module example.compilerclient {
    requires java.compiler;
}
~~~

Bài compiler client có thể import:

~~~java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;
~~~

Đây là khai báo module và mảnh import minh họa; để thành một dự án modular chạy được, còn cần package chứa class chính, source tree và lệnh build. **`requires java.compiler` chỉ cấp quyền đọc API**, không tự bảo đảm JVM cuối cùng có `jdk.compiler`.

### 9.2. Dùng Compiler Tree API

Nếu ứng dụng cần `com.sun.source.tree` và `com.sun.source.util`, module descriptor có thể khai báo:

~~~java
module example.asttool {
    requires jdk.compiler;
}
~~~

JDK module `jdk.compiler` khai báo `requires transitive java.compiler`, nên example.asttool có thể đọc API của `java.compiler` theo transitive readability.

Dù vậy, khai báo cả hai module trong descriptor để làm rõ dependency trực tiếp của source cũng có thể phù hợp với quy ước thiết kế:

~~~java
module example.asttool {
    requires java.compiler;
    requires jdk.compiler;
}
~~~

Đừng nhầm `requires` với “tải module từ mạng”. Module phải có mặt trong JDK/module path/runtime image đã cấu hình thì quá trình resolve mới thực hiện được.

### 9.3. Thử compile với module path

Nếu tổ chức source thành:

~~~text
src/
└── example.asttool/
    ├── module-info.java
    └── example/
        └── asttool/
            └── Main.java
~~~

Trong đó `Main.java` thuộc package `example.asttool`, sử dụng Tree API và có main method, có thể biên dịch kiểu modular:

~~~bash
javac --module-source-path src -d mods -m example.asttool
java --module-path mods -m example.asttool/example.asttool.Main
~~~

Đây là **mẫu lệnh cho cấu trúc modular**, không phải một dự án đầy đủ được viết ở đây. Không thêm `--add-exports` nếu chỉ sử dụng các package **com.sun.source.tree/util** được module `jdk.compiler` exports công khai.

## 10. Runtime image chỉ có API: kiểm chứng bằng jlink

**`java.compiler` tồn tại** không chứng minh **compiler implementation tồn tại**. Có thể tự kiểm chứng bằng một custom runtime image.

Tạo **ProviderProbe.java**:

~~~java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

public class ProviderProbe {
    public static void main(String[] args) {
        JavaCompiler compiler =
                ToolProvider.getSystemJavaCompiler();

        System.out.println(
            JavaCompiler.class.getModule().getName()
        );
        System.out.println(
            compiler == null
                ? "compiler absent"
                : "compiler present"
        );
    }
}
~~~

Trên JDK đầy đủ:

~~~bash
javac -d out ProviderProbe.java
java -cp out ProviderProbe
~~~

**Stdout đã kiểm chứng trên OpenJDK 21:**

~~~text
java.compiler
compiler present
~~~

Tiếp theo, tạo runtime image có **`java.base` và `java.compiler`** nhưng cố ý **không có `jdk.compiler`**:

~~~bash
jlink --add-modules java.base,java.compiler --output runtime-api
~~~

Trên Linux/macOS:

~~~bash
./runtime-api/bin/java -cp out ProviderProbe
~~~

Trên Windows:

~~~powershell
.\runtime-api\bin\java.exe -cp out ProviderProbe
~~~

**Stdout đã kiểm chứng trên OpenJDK 21 với runtime image tối giản:**

~~~text
java.compiler
compiler absent
~~~

Từ đó:

1. Class `javax.tools.JavaCompiler` vẫn có thể nạp được vì image chứa `java.compiler`.
2. `getSystemJavaCompiler()` trả **null** vì image không có system javac provider từ `jdk.compiler`.
3. Application chỉ dùng API không mặc nhiên trở thành một JDK.
4. Nếu ứng dụng thực sự cần chạy javac, cần đóng gói runtime có compiler implementation phù hợp hoặc thiết kế cách dùng external compiler.

Đây là thử nghiệm về **runtime module composition**, không phải khuyến nghị mọi ứng dụng đều tạo image riêng. Khi runtime được tối giản, module availability phải được xác minh trong artifact deployment thật.

**Lưu ý:** `jdk.compiler` cũng có các yêu cầu module hỗ trợ khác, ví dụ `jdk.zipfs` trong JDK nhất định để đọc JAR; hãy để `jlink` resolve các dependency chính xác thay vì tự giả định chỉ hai module đủ cho mọi trường hợp.

## 11. Service provider: ai cung cấp compiler?

`java.compiler` định nghĩa **SPI** `javax.tools.JavaCompiler`. Module `jdk.compiler` có implementation và khai báo service provider phù hợp. Khi compiler hiện diện, client có thể đi qua các đường được hỗ trợ:

~~~text
Ứng dụng
   |
   +-- javax.tools.ToolProvider.getSystemJavaCompiler()
   |               |
   |               v
   |        javax.tools.JavaCompiler  (API)
   |               ^
   |               |
   |          implementation ở jdk.compiler
   |
   +-- java.util.spi.ToolProvider.findFirst("javac")
                   |
                   v
            công cụ javac dạng command-line provider
~~~

Hai đường truy cập này **không trả cùng interface**:

- `getSystemJavaCompiler()` trả **`JavaCompiler`** hoặc null; phù hợp khi cần `getTask`, file manager và diagnostics.
- `java.util.spi.ToolProvider.findFirst("javac")` trả **`Optional<ToolProvider>`**; phù hợp khi muốn gọi công cụ với bộ tham số tương tự command-line trong cùng JVM.

Ví dụ mảnh code minh họa:

~~~java
var javacTool = java.util.spi.ToolProvider
        .findFirst("javac");

if (javacTool.isPresent()) {
    System.out.println("javac tool is available");
}
~~~

**Không dùng `new com.sun.tools.javac.api.JavacTool()` để thay thế các entry point công khai.** Concrete class có thể không exported hoặc thay đổi giữa các JDK, trong khi ứng dụng có thể dùng service/API chuẩn.

## 12. Những giới hạn khi gọi javac qua API

**Không phải mọi lựa chọn của native javac launcher đều hoạt động nguyên xi qua `JavaCompiler.getTask`.** Tài liệu module `jdk.compiler` mô tả một số giới hạn có tính thiết kế:

| Trường hợp | Native javac launcher | `JavaCompiler` API |
| --- | --- | --- |
| `-J...` để đặt JVM options cho process javac | Dùng được với native launcher | Không dùng trong `getTask`; đặt VM options cho JVM đang chạy công cụ |
| Classpath wildcard như `libs/*` | Native launcher có xử lý mở rộng wildcard theo quy tắc riêng | Không tự mở rộng wildcard trong API; liệt kê JAR cụ thể |
| Argument file `@args.txt` | Launcher hỗ trợ | `JavaCompiler` interface không nhận dạng cú pháp argument file như launcher |
| `JDK_JAVAC_OPTIONS` | Có thể tác động tới native launcher | API không tự áp dụng biến môi trường này |
| `--help` và `--version` | Dùng để lấy thông tin ở launcher | Không dùng như compilation options trong `JavaCompiler.getTask` |
| Đường classpath/module path | Theo tùy chọn công cụ | Tùy file manager; standard manager hỗ trợ các options tiêu chuẩn |

Do đó khi port một build script dùng lệnh `javac` sang một chương trình gọi `JavaCompiler`, không nên đơn thuần sao chép mọi chuỗi đối số và chờ hành vi hoàn toàn tương tự. Với classpath, file manager và annotation processors, cần tái tạo cấu hình build chính xác.

**Điểm thực hành:** muốn truyền tham số JVM cho process chạy compiler API, hãy cấu hình **JVM của ứng dụng chủ** chứ không đưa `-J...` vào list options của compilation task.

## 13. Vì sao com.sun.source.* khác com.sun.tools.javac.*?

Cả hai đều có từ “sun”, nhưng **phần đầu tên package không quyết định mức độ hỗ trợ**. Quan trọng là **module descriptor và tài liệu API**.

**`com.sun.source.tree` và `com.sun.source.util`**:

- Được `jdk.compiler` exports công khai.
- Có Javadoc cho các interface và tiện ích cây cú pháp.
- Là lựa chọn có chủ đích khi viết công cụ phụ thuộc javac AST.

**`com.sun.tools.javac.api`, `com.sun.tools.javac.comp`, `com.sun.tools.javac.parser`...**:

- Nhiều subpackage **không exported** cho ứng dụng thông thường.
- Tập trung vào cấu trúc implementation của javac.
- Có thể đổi API, cấu trúc, ngữ nghĩa giữa các bản JDK mà không theo cùng cam kết tương thích của Java SE APIs.
- Có thể gây compile error **package ... is not visible** theo JPMS khi ứng dụng cố import.

Nếu cố dùng một package nội bộ, người ta có thể thêm tham số như:

~~~bash
javac --add-exports jdk.compiler/com.sun.tools.javac.parser=ALL-UNNAMED ...
~~~

Đây là **ví dụ cú pháp mở encapsulation**, không phải lời khuyên hoặc một lệnh hoàn chỉnh. Khi dùng internals, còn có thể cần xử lý runtime exports/opens và rủi ro thay đổi implementation. Một công cụ học tập bình thường nên **không** đi theo cách này chỉ để lấy AST: Tree API đã có sẵn qua `com.sun.source.*`.

### 13.1. Legacy entry point không có nghĩa toàn bộ internals là public

Module `jdk.compiler` có package **`com.sun.tools.javac`** được exports cho legacy entry point. Nhưng tên prefix đó không “kéo theo” quyền export của **`com.sun.tools.javac.api`** hoặc **`com.sun.tools.javac.util`**. JPMS exports theo **package chính xác**, không theo cả cây subpackage.

Hãy dựa vào:

~~~bash
java --describe-module jdk.compiler
~~~

để biết public exports/qualified exports trong JDK cụ thể. Một package chỉ **qualified exported to jdk.javadoc** không tự được dùng từ một ứng dụng bất kỳ.

## 14. Bảng chọn API theo nhu cầu

| Nhu cầu | Chọn API | Module ứng dụng đọc |
| --- | --- | --- |
| Biên dịch source trong bộ nhớ hoặc từ file | `JavaCompiler`, `JavaFileObject`, `JavaFileManager` | `java.compiler` |
| Thu lỗi/cảnh báo có cấu trúc | `DiagnosticCollector`, `Diagnostic` | `java.compiler` |
| Viết annotation processor | `AbstractProcessor`, `TypeElement`, `Elements`, `Types` | `java.compiler` |
| Thử xem javac có tồn tại không | `ToolProvider.getSystemJavaCompiler()` | `java.compiler` (provider phải có tại runtime) |
| Gọi công cụ javac theo kiểu command-line từ Java | `java.util.spi.ToolProvider.findFirst("javac")` | API thuộc `java.base`; cần provider có mặt |
| Duyệt AST source Java | `JavacTask`, `TreePathScanner`, `Tree` | `jdk.compiler` |
| Phân tích cây Javadoc | `com.sun.source.doctree` | `jdk.compiler` |
| Thao tác bộ phân giải/biểu diễn nội bộ javac | **Tránh** `com.sun.tools.javac.*` internals nếu có public alternative | Ràng buộc implementation không ổn định |

Nếu cần triển khai portable cho mọi Java SE runtime có thể bị thu nhỏ, chỉ khai báo `requires java.compiler` chưa đủ: phải **kiểm tra provider**. Nếu công cụ cần AST, phụ thuộc vào `jdk.compiler` là quyết định kiến trúc có chủ đích và cần phân phối JDK/runtime phù hợp.

## 15. Những lỗi thường gặp và cách chẩn đoán

### 15.1. ToolProvider.getSystemJavaCompiler() trả null

**Triệu chứng:** ứng dụng vẫn import được `javax.tools.JavaCompiler` nhưng compiler variable null.

**Nguyên nhân thường gặp:** ứng dụng đang chạy trên runtime image không có module cung cấp javac, ví dụ image tạo bằng `jlink` chỉ gồm `java.base`, `java.compiler`.

**Xử lý:** xác minh `java --list-modules` trong **runtime thực sự chạy ứng dụng**, thêm module/provider vào runtime image nếu cần, hoặc thiết kế khả năng dùng compiler bên ngoài. Không sửa source bằng cách import thêm `com.sun.tools.javac.*`.

### 15.2. Không tìm thấy com.sun.source.tree.Tree

**Triệu chứng:** javac báo package `com.sun.source.tree` không tồn tại hoặc module không được đọc.

**Nguyên nhân khả dĩ:** compiler/runtime không có `jdk.compiler`, module descriptor của tool chưa `requires jdk.compiler;`, hoặc cấu hình module path sai.

**Xử lý:** kiểm tra JDK, `module-info.java` và module graph. Không nhầm với class trong `javax.tools`, vì Tree API không nằm trong `java.compiler`.

### 15.3. Package com.sun.tools.javac.api is not visible

**Nguyên nhân:** đang import package implementation nội bộ mà module `jdk.compiler` không export công khai cho ứng dụng.

**Xử lý:** chuyển sang `javax.tools` hoặc `com.sun.source.*`. Đừng chọn `--add-exports` làm phương án mặc định để né thiết kế encapsulation của JPMS.

### 15.4. ClassCastException khi ép CompilationTask sang JavacTask

**Nguyên nhân:** code giả định mọi `JavaCompiler` provider đều là javac. Interface `CompilationTask` không bắt buộc mọi compiler khác trả về `JavacTask`.

**Xử lý:** chỉ cast khi biết provider thực tế hỗ trợ Compiler Tree API; nêu rõ yêu cầu JDK/javac cho tính năng AST. Nếu tool cho phép nhiều compiler, có đường fallback không phụ thuộc `JavacTask`.

### 15.5. Biên dịch được ở IDE nhưng runtime không có compiler

**Nguyên nhân:** IDE dùng JDK cho compile, nhưng artifact production được chạy bằng custom runtime image tối giản.

**Xử lý:** kiểm tra **cả build JDK và runtime image**, không chỉ phiên bản compiler của developer workstation.

### 15.6. Lệnh JavaCompiler API không nhận -J hoặc @argfile

**Nguyên nhân:** nhầm API method options với native launcher flags.

**Xử lý:** đặt JVM options ở process chủ; truyền các javac options được API hỗ trợ trực tiếp; tự phân giải danh sách classpath files nếu cần.

### 15.7. Tree API parse được nguồn nhưng không phải đã compile hoàn chỉnh

**Nguyên nhân:** code gọi `JavacTask.parse()` nhưng coi AST như bằng chứng toàn bộ kiểu, symbol và bytecode đã hợp lệ.

**Xử lý:** phân biệt các pha `parse()`, `analyze()`, `generate()`. Phân tích tree ở parse phase có thể có nguồn chưa qua semantic checks.

## 16. Quy trình thiết kế công cụ JavaCompiler vững chắc

1. **Xác định mức API cần dùng.** Nếu chỉ cần compile/diagnostics, bắt đầu từ `javax.tools`. Nếu cần AST, cân nhắc `com.sun.source.*`.
2. **Ghi đúng module dependencies.** `requires java.compiler;` cho standard compiler API; `requires jdk.compiler;` khi cần Tree API.
3. **Kiểm tra implementation ở runtime.** `getSystemJavaCompiler()` có thể null.
4. **Sử dụng file manager có chủ đích.** Quản lý classpath/module path, source objects và output.
5. **Truyền options phù hợp API.** Không sao chép mù quáng launcher-only flags.
6. **Thu diagnostics bằng API** thay vì parse chuỗi thông báo stderr khi cần máy xử lý.
7. **Tách ranh giới compiler và JDK internals.** Không dùng internal implementation types nếu public API đáp ứng.
8. **Thử trên runtime image cuối cùng.** Với jlink/containers, xác nhận module provider được đóng gói đầy đủ.
9. **Kiểm tra dữ liệu lỗi.** Source Java không hợp lệ vẫn có thể phát diagnostic/AST một phần; ứng dụng phải xử lý compilation task false.
10. **Ghi rõ tính tương thích.** Công cụ AST dựa javac không đương nhiên chạy trên mọi Java SE compiler khác.

## 17. Bài tập thực hành

**Bài 1 — Đọc module graph.** Chạy `java --describe-module java.compiler` và `java --describe-module jdk.compiler` trên JDK của bạn. Tìm dòng exports, requires transitive và provides. Giải thích tại sao yêu cầu `jdk.compiler` kéo theo khả năng đọc API từ `java.compiler` nhưng chiều ngược lại không đúng.

**Bài 2 — Chạy ModuleProbe.** Tạo `ModuleProbe.java` ở phần 6. Dự đoán sáu dòng stdout, sau đó chạy trên JDK 17+. Nếu khác, ghi lại JDK vendor, phiên bản và module list.

**Bài 3 — Dùng API chuẩn.** Chạy `ApiCompile.java` ở phần 7. Thay nội dung String source bằng một chương trình Java sai cú pháp; quan sát `compiled=false` và diagnostic count. Mở rộng vòng lặp để in `Diagnostic.getKind()`, `getLineNumber()` và `getMessage(Locale.ENGLISH)`.

**Bài 4 — Dùng AST.** Chạy `InspectTree.java` ở phần 8. Đổi biểu thức thành `(2 + 3) * 4` rồi in kind của initializer. Dự đoán vì sao kết quả khác dù các literal giống nhau.

**Bài 5 — Runtime không có compiler.** Chạy `ProviderProbe.java` trên JDK đầy đủ và trên image `jlink` chỉ chứa `java.base,java.compiler`. So sánh `compiler present` và `compiler absent`.

**Bài 6 — Tránh internal API.** Một công cụ đang import `com.sun.tools.javac.api.JavacTool` và `com.sun.tools.javac.tree.JCTree`. Hãy đề xuất đường thay thế bằng `JavaCompiler` và `JavacTask`/`Tree` tương ứng, đồng thời nêu giới hạn của việc thay thế nếu công cụ cần đặc tính implementation không có trong public API.

**Bài 7 — Truy vấn CLI tool.** Viết chương trình gọi `java.util.spi.ToolProvider.findFirst("javac")` và xử lý `Optional.empty()`. Giải thích vì sao cách này không trả về `JavaCompiler.CompilationTask`.

## 18. Câu hỏi tự kiểm tra

- `java.compiler` chứa interface `JavaCompiler` hay implementation javac?
- `jdk.compiler` cung cấp những service và package Tree API nào?
- Hai `ToolProvider` ở `javax.tools` và `java.util.spi` khác nhau ở đâu?
- Vì sao chương trình import `javax.tools.JavaCompiler` được nhưng `getSystemJavaCompiler()` vẫn trả null?
- `requires jdk.compiler;` có tạo quan hệ đọc `java.compiler` không? Vì sao?
- `com.sun.source.tree` có cùng trạng thái API như `com.sun.tools.javac.parser` không?
- Vì sao JavaCompiler API không tiếp nhận mọi launcher options như `-J` và `@argfile`?
- `JavacTask.parse()` có đồng nghĩa source hợp lệ về kiểu không?
- Có nên viết IDE plugin mới phụ thuộc concrete class `com.sun.tools.javac.api.JavacTool` không?
- Một runtime image muốn biên dịch nguồn Java cần đóng gói gì ngoài module chứa API?

## 19. Nguồn tham khảo chính thức

- **Oracle Java SE 21 — Module java.compiler:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/module-summary.html
- **Oracle JDK 21 — Module jdk.compiler:** https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/module-summary.html
- **Java SE 21 — javax.tools package:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/package-summary.html
- **Java SE 21 — JavaCompiler API:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/JavaCompiler.html
- **Java SE 21 — javax.tools.ToolProvider:** https://docs.oracle.com/en/java/javase/21/docs/api/java.compiler/javax/tools/ToolProvider.html
- **Java SE 21 — java.util.spi.ToolProvider:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/spi/ToolProvider.html
- **JDK 21 — JavacTask / Tree API:** https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/util/JavacTask.html
- **JDK 21 — Compiler Tree package:** https://docs.oracle.com/en/java/javase/21/docs/api/jdk.compiler/com/sun/source/tree/package-summary.html
- **JDK 21 — javac tool guide:** https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html

**Ghi nhớ:** `java.compiler` định nghĩa **hợp đồng Java Compiler API** và language model. `jdk.compiler` cung cấp **javac implementation** và các public Compiler Tree APIs. Chỉ cần compile và diagnostic: bắt đầu từ `javax.tools`. Cần AST: chủ động phụ thuộc `com.sun.source.*` trong `jdk.compiler`. Tránh dùng `com.sun.tools.javac.*` internals, và luôn kiểm tra compiler provider thực sự có trong runtime image.