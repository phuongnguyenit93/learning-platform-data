# Biên dịch trong bộ nhớ: Quản lý tên lớp, URI và nhiều đơn vị biên dịch

## Mục tiêu

Khi ứng dụng biên dịch mã Java được tạo động trong RAM, không có sẵn các tệp **.java** và **.class** trên đĩa để trình biên dịch tự suy ra tên, đường dẫn và vị trí đầu ra. Người viết công cụ phải cung cấp những thông tin đó cho **Java Compiler API** một cách nhất quán.

Sau bài học này, bạn có thể:

1. Phân biệt **tên nhị phân của lớp (binary name)**, **package**, tên tệp nguồn, tên tệp bytecode và **URI** của JavaFileObject.
2. Tạo một **đơn vị biên dịch trong bộ nhớ** bằng **SimpleJavaFileObject** với **Kind.SOURCE**, giữ mã nguồn dạng **String**.
3. Cấp nhiều JavaFileObject cho cùng một lần gọi **JavaCompiler.getTask(...)**, kể cả khi các lớp tham chiếu chéo giữa những package khác nhau.
4. Thu nhận nhiều tệp **.class** từ compiler qua **ForwardingJavaFileManager**, **Kind.CLASS** và **getJavaFileForOutput(...)**, không ghi bytecode ra đĩa.
5. Đọc diagnostic theo URI, kiểm tra tên lớp và quản lý kết quả, sau đó nạp các lớp đã biên dịch bằng một **ClassLoader** thích hợp.
6. Nhận diện lỗi tên không khớp, URI sai, trùng class, phụ thuộc không được tìm thấy và hiểu giới hạn của biên dịch hoàn toàn trong RAM.

Bài dùng API **javax.tools** vẫn được hỗ trợ trên các JDK hiện đại. Ví dụ độc lập yêu cầu **JDK 17+** và không sử dụng thư viện bên ngoài.

## 1. Tại sao tên lớp và URI quan trọng khi biên dịch trong RAM?

Trong luồng biên dịch thông thường, một file Java có sẵn trên đĩa:

~~~text
src/demo/app/Runner.java
           │
           ├── package demo.app;
           ├── public class Runner { ... }
           └── compiler tạo demo/app/Runner.class ở thư mục output
~~~

Với biên dịch trong bộ nhớ, source chỉ là một **String**, còn output là một mảng **byte[]**. Compiler vẫn cần biết mỗi chuỗi source đại diện cho đơn vị biên dịch nào, nó có tên gì và output tương ứng phải ghi vào đối tượng nào.

~~~text
("demo.app.Runner", String chứa Java source)
                  │
                  ▼
  JavaFileObject SOURCE
  URI string:///demo/app/Runner.java
                  │
            JavaCompiler
                  │
                  ▼
  JavaFileObject CLASS
  URI mem:///demo/app/Runner.class
                  │
                  ▼
  Map<String, byte[]>: "demo.app.Runner" → bytecode
                  │
                  ▼
       ClassLoader / defineClass
~~~

**URI không phải đường dẫn bắt buộc phải tồn tại trên ổ đĩa.** URI cung cấp danh tính có cấu trúc cho file object và giúp các thao tác của compiler/diagnostic gọi được **toUri()**, **getName()**, **getKind()** và các phương thức file abstraction.

## 2. Hiểu đúng bốn kiểu tên thường bị nhầm

Xét source:

~~~java
package demo.app;

public class Runner {
    public static String value() {
        return "OK";
    }
}
~~~

Các tên và vai trò:

| Khái niệm | Giá trị ví dụ | Ý nghĩa |
| --- | --- | --- |
| Package | **demo.app** | Namespace khai báo trong source |
| Tên đơn giản | **Runner** | Tên của top-level class |
| Tên nhị phân (binary name) | **demo.app.Runner** | Tên dùng bởi JVM và ClassLoader.loadClass |
| Tên file source tương thích | **Runner.java** | Một public top-level class cần file mang tên đó |
| URI source trong RAM | **string:///demo/app/Runner.java** | Định danh JavaFileObject chứa source |
| URI output trong RAM | **mem:///demo/app/Runner.class** | Định danh JavaFileObject nhận bytecode |
| Key trong output Map | **demo.app.Runner** | Tên để tìm đúng bytecode lúc nạp class |

Cần chú ý:

- Trong source, **package demo.app** và **public class Runner** tạo nên danh tính **demo.app.Runner**. Đặt URI theo đúng package và tên class để compiler có thể đối chiếu tên đơn vị nguồn.
- **Tên nhị phân** của nested class thường có ký hiệu **$**: ví dụ **demo.app.Outer$Inner**; source code gọi thành viên bằng cú pháp **Outer.Inner**. Không tự biến mọi nested class thành một đơn vị SOURCE riêng nếu nó đã được khai báo trong Outer.java.
- Một file nguồn có thể chứa các lớp top-level **không public** bên cạnh public class. Số lượng output **.class** có thể lớn hơn số SOURCE.
- Với source không có package, binary name là tên lớp đơn giản, ví dụ **Runner**; tuy nhiên, trong dự án thực tế nên tổ chức package rõ ràng.
- **Module name** của JPMS (ví dụ **com.example.module**) khác với binary name của Java class. Bài này minh họa compilation trong classpath/unnamed module; mục về JPMS ở phần sau giải thích ranh giới.

**Nguyên tắc:** Chỉ cần một bản ghi nguồn cho mỗi **compilation unit**, không phải một bản ghi cho mỗi file **.class** dự kiến xuất ra.

## 3. JavaFileObject, Kind và quy tắc URI

**JavaFileObject** đại diện cho một file nguồn hoặc file class mà compiler thao tác. **SimpleJavaFileObject** giúp triển khai các hành vi tối thiểu cần thiết cho đối tượng nằm trong RAM.

### 3.1. SOURCE: tên lớp → URI → String

~~~java
// Mảnh mã minh họa; xem chương trình chạy đầy đủ ở mục 6.
final class Source extends SimpleJavaFileObject {
    private final String code;

    Source(String binaryName, String code) {
        super(URI.create("string:///" +
                binaryName.replace('.', '/') + Kind.SOURCE.extension),
                Kind.SOURCE);
        this.code = code;
    }

    @Override
    public CharSequence getCharContent(boolean ignoreEncodingErrors) {
        return code;
    }
}
~~~

Các điểm chính:

1. **binaryName** là tên đầy đủ của public top-level class hoặc interface, ví dụ **demo.api.Message**. Hàm **replace('.', '/')** biến phần package thành các segment đường dẫn.
2. **Kind.SOURCE.extension** là **.java**. URI **string:///demo/api/Message.java** là URI tuyệt đối với scheme **string**, không mở kết nối mạng.
3. **getCharContent(...)** trả trực tiếp chuỗi chứa source. Compiler không cần đọc file thật; tham số **ignoreEncodingErrors** không có tác động đến việc giải mã byte vì source đã là **CharSequence**.
4. Khi source đến từ **byte[]** hoặc một file, ứng dụng cần giải mã theo charset đúng **trước khi** đưa dữ liệu vào object này; **-encoding UTF-8** không sửa được String đã giải mã sai.
5. URI cần hợp lệ và ổn định trong phạm vi một compilation task; không nên dùng URI ngẫu nhiên mỗi lần truy cập cùng một source.

Đây là **đoạn minh họa**, chưa chạy độc lập vì cần import và chương trình bao ngoài.

### 3.2. CLASS: tên lớp → URI → OutputStream

Để nhận output mà không ghi ra đĩa, tạo JavaFileObject loại **CLASS** có **openOutputStream()** trả về luồng ghi byte trong RAM:

~~~java
// Mảnh mã minh họa; định nghĩa hoàn chỉnh ở mục 6.
final class Bytecode extends SimpleJavaFileObject {
    private final ByteArrayOutputStream content = new ByteArrayOutputStream();

    Bytecode(String binaryName, Kind kind) {
        super(URI.create("mem:///" +
                binaryName.replace('.', '/') + kind.extension), kind);
    }

    @Override
    public OutputStream openOutputStream() {
        return content;
    }

    byte[] getBytes() {
        return content.toByteArray();
    }
}
~~~

- **Kind.CLASS.extension** là **.class**.
- URI output có scheme **mem** để phân biệt ý nghĩa với source; đây là quy ước do ứng dụng đặt, không phải yêu cầu phải dùng đúng hai scheme **string/mem**.
- Tên output do **compiler** cung cấp tại **getJavaFileForOutput(...)**, có thể là tên của class phụ hoặc nested class phát sinh từ source; không nên đoán trước một source chỉ sinh ra một output.
- Chỉ lấy **getBytes()** sau khi task biên dịch đã hoàn tất và thành công; byte được ghi trong quá trình compile có thể chưa hoàn chỉnh.

### 3.3. Vì sao hình dạng URI phải khớp?

Đường dẫn phần **.java** gắn với tên public class giúp trình biên dịch kiểm tra tính tương thích. Ví dụ:

~~~text
Tên đăng ký: demo.api.Message
URI source:  string:///demo/api/Message.java
Nội dung:   package demo.api; public interface Message { ... }
Kết quả:    hợp lệ
~~~

Nếu URI lại là **string:///demo/api/Other.java** nhưng source có **public interface Message**, javac có thể báo rằng public interface phải được khai báo trong file **Message.java**.

Ngược lại, nếu chỉ sửa tên hiển thị mà không sửa **package** hay tên public class bên trong source, không thể làm compiler “đổi tên lớp” tùy ý. Danh tính thực của các type vẫn do cú pháp Java trong source quyết định.

Đối với mã nguồn được tạo động, nên định nghĩa cấu trúc dữ liệu gắn chặt **binaryName** và **code**, xác thực cả hai trước khi thêm vào danh sách compilation units.

### 3.4. Xử lý URI khi đầu vào không được kiểm soát

Mẫu **binaryName.replace('.', '/')** được dùng trong ví dụ với **các tên package/class cố định và hợp lệ**. Nếu hệ thống nhận tên từ người dùng hoặc một dịch vụ khác, phải kiểm tra tên theo quy tắc tên Java và giới hạn cho phép trước khi tạo URI:

- Không chấp nhận chuỗi chứa **/**, **\\**, **..**, ký tự điều khiển hoặc scheme tùy tiện để “chen” đường dẫn vào URI.
- Không coi **URI.create(...)** là hàm tự xác thực Java identifier. Nó chỉ kiểm tra cú pháp URI.
- Với identifier Unicode, phải encode URI đúng tiêu chuẩn thay vì giả định phép nối chuỗi thô luôn phù hợp. **Binary name** và **URI** có thể có biểu diễn ký tự khác nhau nhưng vẫn phải chỉ tới cùng đơn vị logic.
- Không dùng URI làm bằng chứng an toàn: compiler có khả năng xử lý mã Java được cung cấp; việc biên dịch và chạy mã không tin cậy cần ranh giới bảo mật riêng.

## 4. Nhiều đơn vị biên dịch trong một tác vụ

Hãy xem ba unit:

~~~text
demo.api.Message               (interface)
         ▲
         │ implements
demo.impl.VietnameseMessage
         ▲
         │ được tạo và gọi bởi
demo.app.Main
~~~

Nếu có cả ba **JavaFileObject.Kind.SOURCE** trong **cùng** danh sách **compilationUnits** của một task, compiler có thể giải quyết quan hệ type giữa chúng mà không cần tạo thư viện trung gian trên đĩa.

~~~java
// Mảnh code minh họa, không phải file chạy độc lập.
List<JavaFileObject> units = List.of(
        new Source("demo.api.Message", apiSource),
        new Source("demo.impl.VietnameseMessage", providerSource),
        new Source("demo.app.Main", mainSource)
);

Boolean success = compiler.getTask(
        null, fileManager, diagnostics,
        List.of("--release", "17", "-proc:none"),
        null, units).call();
~~~

**getTask(...)** nhận **Iterable<? extends JavaFileObject>**; các phần tử trong ví dụ đều là SOURCE. **Một task** kiểm tra và biên dịch tập source thống nhất; thứ tự liệt kê trong **List.of(...)** không cần khớp thứ tự import/phụ thuộc giữa các unit. Tuy nhiên, không nên dựa vào thứ tự mà compiler sinh ra file **.class**; thứ tự đó không phải contract nghiệp vụ.

Nếu chia thành nhiều lần **getTask(...)**:

- Task thứ hai cần tìm được các class do task thứ nhất tạo.
- Khi output đầu tiên chỉ nằm trong Map RAM, StandardJavaFileManager thông thường **không tự biết** Map đó. Muốn biên dịch nhiều giai đoạn hoàn toàn trong RAM, cần mở rộng file manager để hỗ trợ lookup/list class đã biên dịch (ví dụ **getJavaFileForInput(...)**, **list(...)**, **inferBinaryName(...)** theo contract), hoặc cung cấp artifact/classpath thích hợp cho task sau.
- Không kỳ vọng dùng lại **CompilationTask.call()** trên cùng task; mỗi lần biên dịch phải tạo task mới.
- Nếu không cần biên dịch nhiều giai đoạn, **đưa mọi source phụ thuộc vào cùng task** là cách ít cấu hình và dễ kiểm tra hơn.

## 5. Thu nhận nhiều file CLASS qua FileManager

Một **StandardJavaFileManager** chuẩn thường ghi class ra filesystem. Để đổi nơi nhận class thành RAM, dùng **ForwardingJavaFileManager<StandardJavaFileManager>** và chỉ tùy biến đường output cần thiết.

~~~java
// Trích từ ví dụ đầy đủ ở mục 6.
private static final class MemoryFiles
        extends ForwardingJavaFileManager<StandardJavaFileManager> {
    private final Map<String, Bytecode> classFiles = new LinkedHashMap<>();

    MemoryFiles(StandardJavaFileManager delegate) {
        super(delegate);
    }

    @Override
    public JavaFileObject getJavaFileForOutput(
            Location location, String className, JavaFileObject.Kind kind,
            FileObject sibling) throws IOException {
        if (location == StandardLocation.CLASS_OUTPUT
                && kind == JavaFileObject.Kind.CLASS) {
            Bytecode file = new Bytecode(className, kind);
            classFiles.put(className, file);
            return file;
        }
        return super.getJavaFileForOutput(location, className, kind, sibling);
    }
}
~~~

Khi compiler muốn ghi class:

1. Nó gọi **getJavaFileForOutput(...)** với **className** là tên do compiler xác định.
2. FileManager tạo **Bytecode** dùng đúng className, kind và URI output.
3. Lưu theo key là binary name trong **Map<String, Bytecode>**.
4. Compiler ghi byte của class vào luồng từ **openOutputStream()**.
5. Khi task thành công, ứng dụng lấy **Map<String, byte[]>**; sau đó mới nạp class nếu cần.

Dùng **Map** thay vì một biến byte[] duy nhất là bắt buộc về mặt thiết kế cho nhiều lớp: nếu chỉ giữ output cuối cùng, những lớp phụ thuộc trước đó sẽ bị mất.

**CLASS_OUTPUT** cần được chặn đúng vị trí. Những output khác, chẳng hạn **SOURCE_OUTPUT** do annotation processing tạo source, có vòng đời riêng. Ví dụ này dùng **-proc:none** để không thực thi annotation processors trong bài tập; nếu hệ thống có annotation processing, phải thiết kế luôn đường đọc/ghi file object cho các output có liên quan.

## 6. Chương trình Java 17+ hoàn chỉnh: 3 source → 3 class trong RAM

Tạo **duy nhất một file** tên **MemoryCompileDemo.java** với nội dung sau. Đây là một chương trình độc lập, không yêu cầu tạo các file **.java** bên trong package **demo**. Ba unit sẽ được tạo từ Java text blocks khi chương trình chạy.

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.StandardLocation;
import javax.tools.ToolProvider;

public final class MemoryCompileDemo {
    private static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source(String binaryName, String code) {
            super(URI.create("string:///" +
                    binaryName.replace('.', '/') + Kind.SOURCE.extension),
                    Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    private static final class Bytecode extends SimpleJavaFileObject {
        private final ByteArrayOutputStream content = new ByteArrayOutputStream();

        Bytecode(String binaryName, Kind kind) {
            super(URI.create("mem:///" +
                    binaryName.replace('.', '/') + kind.extension), kind);
        }

        @Override
        public OutputStream openOutputStream() {
            return content;
        }

        byte[] getBytes() {
            return content.toByteArray();
        }
    }

    private static final class MemoryFiles
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        private final Map<String, Bytecode> classFiles = new LinkedHashMap<>();

        MemoryFiles(StandardJavaFileManager delegate) {
            super(delegate);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                Location location, String className, JavaFileObject.Kind kind,
                FileObject sibling) throws IOException {
            if (location == StandardLocation.CLASS_OUTPUT
                    && kind == JavaFileObject.Kind.CLASS) {
                Bytecode file = new Bytecode(className, kind);
                classFiles.put(className, file);
                return file;
            }
            return super.getJavaFileForOutput(location, className, kind, sibling);
        }

        Map<String, byte[]> snapshot() {
            Map<String, byte[]> result = new HashMap<>();
            classFiles.forEach((name, file) ->
                    result.put(name, file.getBytes()));
            return Map.copyOf(result);
        }
    }

    private static final class MemoryLoader extends ClassLoader {
        private final Map<String, byte[]> bytecodes;

        MemoryLoader(Map<String, byte[]> bytecodes) {
            super(MemoryCompileDemo.class.getClassLoader());
            this.bytecodes = bytecodes;
        }

        @Override
        protected Class<?> findClass(String binaryName)
                throws ClassNotFoundException {
            byte[] bytes = bytecodes.get(binaryName);
            if (bytes == null) {
                throw new ClassNotFoundException(binaryName);
            }
            return defineClass(binaryName, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler is unavailable");
        }

        List<JavaFileObject> units = List.of(
                new Source("demo.api.Message", """
                        package demo.api;
                        public interface Message {
                            String text();
                        }
                        """),
                new Source("demo.impl.VietnameseMessage", """
                        package demo.impl;
                        public class VietnameseMessage implements demo.api.Message {
                            @Override public String text() {
                                return "Xin chào Java";
                            }
                        }
                        """),
                new Source("demo.app.Main", """
                        package demo.app;
                        public class Main {
                            public static String message() {
                                return new demo.impl.VietnameseMessage().text();
                            }
                        }
                        """)
        );

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();
        Map<String, byte[]> compiled;

        StandardJavaFileManager standard =
                compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT, StandardCharsets.UTF_8);
        try (MemoryFiles files = new MemoryFiles(standard)) {
            Boolean ok = compiler.getTask(
                    null, files, diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null, units).call();
            if (!Boolean.TRUE.equals(ok)) {
                diagnostics.getDiagnostics().forEach(System.err::println);
                throw new IllegalStateException("Compilation failed");
            }
            compiled = files.snapshot();
        }

        System.out.println(compiled.keySet().stream().sorted().toList());
        Class<?> entry = new MemoryLoader(compiled).loadClass("demo.app.Main");
        System.out.println(entry.getMethod("message").invoke(null));
    }
}
~~~

### 6.1. Lệnh chạy

Trong thư mục chứa **MemoryCompileDemo.java**, dùng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 --release 17 MemoryCompileDemo.java
java MemoryCompileDemo
~~~

**Stdout chính xác:**

~~~text
[demo.api.Message, demo.app.Main, demo.impl.VietnameseMessage]
Xin chào Java
~~~

Chương trình sẽ tạo **MemoryCompileDemo.class** và các class nested của chính driver trên đĩa do lệnh **javac** đầu tiên. Tuy nhiên, **ba lớp demo.api.Message, demo.impl.VietnameseMessage và demo.app.Main** chỉ được biên dịch thành **byte[] trong RAM** bởi lời gọi **JavaCompiler.getTask(...)** bên trong chương trình; ví dụ không tự ghi chúng thành các file **demo/**/*.class**.

**Ví dụ đã được biên dịch và chạy thành công trên OpenJDK 24.0.2** với tùy chọn **--release 17**, dùng đúng stdout ở trên.

### 6.2. Tại sao kết quả ổn định?

- Ba source sử dụng package và public type tương ứng với **binaryName** đã truyền vào constructor **Source**.
- **URI source** được tạo đúng bằng **Kind.SOURCE.extension**, nên file manager/diagnostics có danh tính nguồn phù hợp.
- Một lần **getTask(...)** nhận đủ cả interface, implementation và consumer, tránh phải làm cho compiler thấy bytecode output từ một task trước.
- **getJavaFileForOutput(...)** chặn việc ghi CLASS và lưu đúng tên do compiler tạo.
- **snapshot()** tạo Map tên lớp → bytecode sau khi task thành công.
- **MemoryLoader.findClass(...)** dùng **defineClass** để định nghĩa đúng tên đã biên dịch; parent class loader vẫn phục vụ các lớp của JDK và bản thân driver.
- Biểu thức **sorted()** làm thứ tự tên khi in ra xác định; thứ tự compiler thực sự ghi output không được lấy làm giả định.
- Output tiếng Việt đã nằm trong Java **String/CharSequence**, nên nó không phụ thuộc vào đường chuyển byte→ký tự của file nguồn động. Lệnh **javac -encoding UTF-8** ở ngoài vẫn cần phù hợp với cách lưu **MemoryCompileDemo.java**.

### 6.3. Điều gì thay đổi khi có nested class?

Giả sử một source khác chứa:

~~~java
package demo.app;

public class Outer {
    public static class Inner {
        public String label() {
            return "inner";
        }
    }
}
~~~

Đây là **một** source unit có URI ví dụ **string:///demo/app/Outer.java**, nhưng bình thường sinh ra **hai** CLASS outputs:

~~~text
demo.app.Outer        → mem:///demo/app/Outer.class
demo.app.Outer$Inner  → mem:///demo/app/Outer$Inner.class
~~~

Khi nạp nested class theo binary name, **ClassLoader.loadClass("demo.app.Outer$Inner")** dùng tên có **$**. Cú pháp Java trong source để tham chiếu nó là **Outer.Inner**. Nếu bổ sung unit này vào cùng task, output Map phải đủ chỗ cho **cả hai key**, không thể giả định số tệp .class bằng số JavaFileObject SOURCE.

## 7. Quản lý tập nhiều source một cách đáng tin cậy

Khi xây công cụ thực sự (editor, rule compiler, code generator, template runtime), không nên lưu source bằng danh sách String không rõ danh tính. Một bản ghi nguồn tối thiểu cần:

~~~text
SourceUnit {
    binaryName: demo.app.Main
    sourceUri:  string:///demo/app/Main.java
    content:    package demo.app; public class Main { ... }
}
~~~

Các bước kiểm tra trước khi biên dịch:

1. **Tên không trống và hợp lệ:** xác định binary name của public top-level type, kiểm tra package/name, tạo URI tương thích.
2. **Một danh tính → một source unit:** tránh hai object khác nội dung dùng chung binary name/URI trong cùng task. Nếu cho phép cập nhật, quy định rõ bản nào là phiên bản được biên dịch và loại bỏ bản cũ trước khi lập danh sách.
3. **Package khớp với nội dung:** đừng chỉ tin metadata ngoài source. Đối với input không tin cậy hoặc cần độ chính xác cao, có thể sử dụng một bước parse/compile để xác minh bằng compiler diagnostics.
4. **Tập source đầy đủ:** gom tất cả unit cần thiết và dependency bên ngoài cho một lần biên dịch.
5. **Giới hạn và thứ tự ổn định:** sắp xếp đầu vào bằng tên khi cần log/debug tái lập, nhưng không dựa vào thứ tự đầu vào để giải quyết type.
6. **Output Map riêng cho mỗi task:** không để bytecode lỗi hoặc từ phiên bản cũ lẫn vào kết quả mới.
7. **Chỉ công bố kết quả thành công:** khi **call()** trả false, không dùng những byte[] có thể mới được tạo một phần.

Hãy nhớ rằng **binary name** là danh tính Java class. URI của file object là công cụ biểu diễn file trừu tượng, không phải “cơ chế đổi tên class sau khi biên dịch”.

### 7.1. Diagnostics: tìm lỗi theo URI của source

**DiagnosticCollector<JavaFileObject>** ghi các chẩn đoán mà compiler tạo ra. Một diagnostic có thể chứa:

- **getKind()**: ERROR/WARNING/NOTE hoặc mức khác.
- **getSource()**: JavaFileObject liên quan; có thể là null.
- **getSource().toUri()**: URI nguồn bạn đã đặt, giúp map lỗi về editor/source item.
- **getLineNumber() / getColumnNumber()**: vị trí trong nội dung source, có thể là **Diagnostic.NOPOS** nếu không có thông tin.
- **getMessage(Locale.ROOT)**: giải thích lỗi theo locale tương ứng.

Mảnh code minh họa để chèn **khi task không thành công**:

~~~java
for (var diagnostic : diagnostics.getDiagnostics()) {
    String uri = diagnostic.getSource() == null
            ? "<unknown>"
            : diagnostic.getSource().toUri().toString();

    System.err.printf("%s %s at %s:%d:%d: %s%n",
            diagnostic.getKind(),
            uri,
            uri,
            diagnostic.getLineNumber(),
            diagnostic.getColumnNumber(),
            diagnostic.getMessage(Locale.ROOT));
}
~~~

Ở ví dụ này phần URI được in lặp lại trong mẫu định dạng nhằm minh họa cả nguồn và vị trí; trong sản phẩm hãy chọn cấu trúc log gọn, chỉ chứa thông tin cần thiết và phù hợp bảo mật. **Đây là mảnh code minh họa**, không phải file Java chạy độc lập.

Nếu source unit có URI **string:///demo/app/Main.java**, diagnostic có thể đưa lỗi về đúng entry đó mà không cần dựa vào đường dẫn file vật lý. Đừng hard-code nguyên văn thông điệp từ compiler vào unit test: ngôn ngữ và cách diễn đạt có thể đổi giữa JDK. Ưu tiên kiểm tra **Kind.ERROR**, danh tính nguồn và vị trí hợp lệ.

### 7.2. Lỗi thường gặp liên quan tên, URI và số lượng output

| Hiện tượng | Nguyên nhân điển hình | Cách sửa |
| --- | --- | --- |
| **class X is public, should be declared in a file named X.java** | URI source kết thúc bằng tên file khác với public class/interface | Đối chiếu binaryName, package, public type và phần đuôi **.java** |
| **package ... does not exist** | Thiếu một source phụ thuộc trong units hoặc thiếu class/JAR trên classpath của task | Gom đủ source vào một task, hoặc cung cấp đường dẫn/MemoryFileManager có thể đọc output từ task trước |
| **cannot find symbol** | Tên class/interface sai, import sai, unit chưa được nạp, thiếu dependency | Kiểm tra package/type, danh sách units, compiler diagnostics và classpath |
| Output Map chỉ có một class | File manager dùng biến byte[] duy nhất hoặc key bị ghi đè | Dùng Map theo **className** mà compiler cung cấp |
| Compiler báo success nhưng không thấy file **.class** trên đĩa | File manager chủ động ghi output vào RAM | Kiểm tra Map bytecode, không tìm nhầm trên filesystem |
| Lấy bytecode quá sớm | Đọc OutputStream/Map trước khi task hoàn thành | Gọi **call()** xong và chỉ publish khi true |
| **ClassNotFoundException** lúc nạp | Key yêu cầu sai binary name hoặc class chưa có trong Map | Dùng tên đầy đủ đúng, kể cả **$** của nested class; kiểm tra mọi output |
| **NoClassDefFoundError** khi khởi tạo/gọi class | Một dependency của class đã load không được tìm thấy | Đảm bảo các class liên quan được nạp trong cùng phạm vi loader hoặc có trên parent |
| **IllegalArgumentException** khi tạo URI | Chuỗi URI không hợp lệ, không encode ký tự theo quy tắc | Xác thực tên, tạo URI phù hợp và kiểm tra kết quả |
| Trùng class/sai phiên bản | Nhiều bản bytecode cùng tên trên các class loader/classpath hoặc source units không thống nhất | Cấu hình một nguồn chân lý cho mỗi binary name và định nghĩa ranh giới loader |
| **ToolProvider.getSystemJavaCompiler() == null** | Runtime không có triển khai JDK compiler khả dụng | Chạy trong JDK đầy đủ hoặc runtime image có module compiler |
| Task thứ hai không thấy output RAM của task thứ nhất | File manager chỉ intercept output mà không cung cấp **CLASS_PATH** input từ Map | Dùng chung một task, hoặc triển khai đầu vào bộ nhớ có hỗ trợ lookup/list theo API |

## 8. Vòng đời, class loading và các giới hạn cần biết

### 8.1. Biên dịch trong RAM không đồng nghĩa thực thi an toàn

**JavaCompiler** phân tích và tạo bytecode; **ClassLoader.defineClass** định nghĩa class trong JVM. Chúng không tạo sandbox. Code được thực thi có thể sử dụng quyền của process nếu không có ranh giới cách ly phù hợp. Đặc biệt:

- Không tự biên dịch rồi chạy mã do người dùng không tin cậy gửi vào ngay trong JVM chính.
- **-proc:none** trong ví dụ vô hiệu hóa annotation processing của task, giúp giới hạn một loại code thực thi trong lúc compile. Nó **không** làm mã nguồn được biên dịch hoặc bytecode sau đó trở thành an toàn.
- Với dữ liệu không tin cậy, cần cơ chế cách ly phù hợp (tiến trình/container chuyên dụng, giới hạn tài nguyên/quyền, kiểm soát thư viện và mạng).
- Giới hạn số lượng source, kích thước chuỗi, CPU, bộ nhớ, thời gian xử lý và dung lượng bytecode theo yêu cầu của hệ thống.

### 8.2. ClassLoader không thay bytecode của class đã được định nghĩa

Mỗi lần **defineClass** gắn tên lớp với một phiên bản bytecode trong một loader. Khi cần biên dịch lại và nạp phiên bản mới cùng binary name, không gọi **defineClass** lần hai cho cùng tên trong cùng loader vì có thể gặp **LinkageError**. Thiết kế một **loader mới cho mỗi phiên bản hoặc nhóm bytecode** khi cần nạp động.

Class có thể tiếp tục sống khi còn tham chiếu tới instance, Class, loader hoặc các đối tượng liên quan. Muốn có vòng đời rõ ràng, hãy tránh giữ loader/bytecode/instance vô thời hạn, và dọn tài nguyên ứng dụng theo hợp đồng thích hợp. Java Compiler API không tự quản lý vòng đời plugin.

### 8.3. Tương thích thư viện và module

- Ví dụ dùng **classpath/unnamed module** và có parent loader làm nguồn các class nền tảng của JDK. Nếu source tham chiếu JAR ngoài, phải cung cấp classpath thích hợp cho compiler và đưa thư viện tương thích vào runtime loader.
- Với **named modules (JPMS)**, cần xét **module-info.java**, **module source path/module path**, tên module và module layer. Không coi URI **string:///...** của một class là đủ để compiler hiểu module.
- Với nhiều source package/module phức tạp hoặc annotation processing, cần xây FileManager đầy đủ hơn; override riêng **getJavaFileForOutput** là ví dụ tối thiểu cho tình huống output CLASS.
- Không dùng classpath hoặc module path tùy ý nhận từ dữ liệu không tin cậy để cấp đặc quyền cho compiler/runtime.

### 8.4. Giới hạn bộ nhớ, lộ trình triển khai

Chương trình mẫu giữ String source, **ByteArrayOutputStream** và bản sao **byte[]** trong Map. Trong production, cần hạn mức rõ ràng để tránh giữ quá nhiều phiên bản. Tùy mục đích, bytecode có thể được cache theo fingerprint của source và options, rồi dọn theo tuổi/lượt dùng. Cache phải gắn với **toàn bộ nguồn, dependency, compiler options, JDK mục tiêu**; chỉ dựa vào binary name là không đủ.

Nếu hệ thống không thực sự cần chạy code trong cùng JVM, một tiến trình biên dịch riêng và artifact tạm/được quản lý có thể đơn giản hơn, dễ quan sát và dễ cách ly. Điều đó không làm thay đổi bản chất tên lớp/URI/compilation units của API.

## 9. Bài tập tự luyện

1. Thêm source unit **demo.api.Version** chứa một hằng số và cho **demo.impl.VietnameseMessage** sử dụng nó. Dự đoán số class output, chạy lại và kiểm tra danh sách key trong Map.
2. Tạo một source unit **demo.app.Outer** có nested class **Inner**. Xác nhận **MemoryFiles** nhận cả **Outer** và **Outer$Inner**, dù chỉ có một đơn vị nguồn tương ứng.
3. Cố tình đăng ký URI **string:///demo/app/Wrong.java** cho source chứa **public class Main**. Quan sát diagnostic có URI/line liên quan và sửa bằng cách đồng bộ tên unit.
4. Bỏ unit **demo.api.Message** khỏi danh sách. Đọc compiler diagnostics và giải thích vì sao không thể dùng class **Message** khi chưa có classpath thay thế.
5. Sửa **MemoryLoader** để tra cứu bytecode theo binary name và tạo hai loader khác nhau cho hai bản compile. So sánh danh tính **Class** của cùng tên lớp ở hai loader.
6. Viết kiểm thử khẳng định: mọi output byte[] không rỗng, tên key là binary name, task trả false không publish bytecode, và chương trình chỉ tạo những lớp demo trong RAM.

## Kết luận

Để biên dịch nhiều source Java trong bộ nhớ một cách đáng tin cậy, cần giữ chuỗi quan hệ:

**Binary name đúng ↔ URI SOURCE tương thích ↔ nội dung package/public type đúng → một danh sách compilationUnits đầy đủ → JavaCompiler.getTask(...).call() → FileManager lưu mọi CLASS output theo className → ClassLoader nạp bytecode theo binary name.**

**Số source units không bắt buộc bằng số class outputs**; class loading và các task biên dịch sau cần biết chính xác Map/loader chứa các class đã tạo. Luôn kiểm tra diagnostics, chỉ công bố kết quả sau khi compile thành công và giữ ranh giới bảo mật rõ ràng khi chạy code động.

**Tham khảo chính thức đang áp dụng:**

- [JavaCompiler — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaCompiler.html)
- [JavaFileObject — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaFileObject.html)
- [SimpleJavaFileObject — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html)
- [ForwardingJavaFileManager — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html)
- [JavaFileManager — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaFileManager.html)