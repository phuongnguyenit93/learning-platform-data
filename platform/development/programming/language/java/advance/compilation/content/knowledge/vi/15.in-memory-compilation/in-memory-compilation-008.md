# Ranh giới giữa biên dịch bytecode với nạp hoặc chạy bytecode trong Java

Khi biên dịch Java **trong bộ nhớ**, ta thường bắt đầu từ một chuỗi source code, gọi `JavaCompiler`, rồi nhận được một hoặc nhiều mảng byte đại diện cho tệp `.class`. Nhưng **có bytecode không đồng nghĩa class đã được JVM nạp hoặc chương trình đã được chạy**. Ba bước có mục đích, API, lỗi và vòng đời khác nhau:

1. **Biên dịch (compilation):** phân tích mã Java, phân giải tên/kiểu, kiểm tra ngữ nghĩa, tạo bytecode theo class file format. API: `javax.tools.JavaCompiler`, `JavaFileObject`, `JavaFileManager`.
2. **Nạp và liên kết (loading/linking):** JVM tìm hoặc nhận bytes của class, định nghĩa một runtime class gắn với class loader, kiểm tra/chuẩn bị và phân giải các tham chiếu khi cần. API thường thấy: `ClassLoader`, `defineClass`, `Class.forName`.
3. **Khởi tạo và thực thi (initialization/execution):** JVM chạy static initializers khi class được khởi tạo, gọi constructor/method, thực hiện bytecode; Java có thể dùng reflection hoặc lời gọi kiểu tĩnh bình thường để kích hoạt hành vi.

Phân biệt ba bước rất quan trọng trong IDE, sandbox, REPL, hệ plugin, template engine và công cụ tự biên dịch source runtime. Một đoạn mã **biên dịch thành công** vẫn có thể thất bại ở class loading, verification, linking, initialization hoặc lời gọi method; một `byte[]` hợp lệ cũng không tự làm phát sinh side effect.

## 1. Bảng đối chiếu: ba trạng thái không tương đương

| Câu hỏi | Biên dịch bytecode | Nạp/liên kết class | Chạy bytecode |
| --- | --- | --- | --- |
| Input chính | `.java` hoặc `JavaFileObject` chứa source | Binary name và `.class` bytes/nguồn class | Class/method/object đã sẵn sàng |
| Output chính | `.class` bytes, diagnostics | `Class<?>` có identity theo name + defining loader | Return value, side effect, exception |
| Thành phần chủ đạo | `javac` / `JavaCompiler` | JVM + `ClassLoader` | JVM execution engine, thread và chương trình |
| Có thể diễn ra mà không chạy `main`? | Có | Có | Có: gọi một method khác `main` |
| Có thể thất bại độc lập? | Có: type/syntax error | Có: class version, verification, dependencies | Có: logic, exception, initialization, I/O |
| Có nạp class vừa sinh vào current loader? | **Không tự động** | Có thể, khi được yêu cầu | Dùng class đã định nghĩa hoặc kích hoạt tải khi cần |
| Có nghĩa đã thực hiện static initializer? | Không | Không bắt buộc | Khi class được **khởi tạo** theo quy tắc JVM |

Sơ đồ tổng quát:

~~~text
String / .java / JavaFileObject
             |
             |  JavaCompiler.CompilationTask.call()
             v
     .class bytes in memory
             |
             |  ClassLoader.defineClass(...) hoặc tìm class từ path/JAR
             v
       JVM runtime Class
             |
             |  verification / preparation / resolution
             |  (một số việc có thể thực hiện sớm hoặc muộn)
             v
        Initialization
             |
             |  <clinit> nếu class cần khởi tạo
             v
     Call method / new object / execution
             |
             v
     Kết quả, side effects, exceptions
~~~

**Lưu ý:** sơ đồ chỉ là mô hình học tập. JVM specification phân biệt **loading**, **linking** (verification, preparation, resolution), **initialization**; resolution có thể thực hiện theo nhu cầu. Không được hiểu rằng mọi tham chiếu method/field của class đều đã được resolve ngay sau `defineClass`.

## 2. CompilationTask.call() thực sự làm gì?

Trong Java Compiler API:

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
JavaCompiler.CompilationTask task = compiler.getTask(
        null, fileManager, diagnostics,
        options, null, compilationUnits);
boolean success = Boolean.TRUE.equals(task.call());
~~~

Đây là **fragment**, giả sử các biến đã có kiểu/import thích hợp. `task.call()` kích hoạt compilation task và trả kết quả compile. Nó có thể:

- Đọc `JavaFileObject` chứa source `.java` hoặc source trong RAM.
- Phân tích cú pháp, tên khai báo, kiểu, generic, overload, accessibility và checked exception.
- Chạy annotation processors đã cấu hình (nếu được bật/khả dụng), có thể sinh thêm source và resource.
- Tạo file class qua `JavaFileManager.getJavaFileForOutput(...)`; file manager có thể ghi xuống disk hoặc giữ trong RAM.
- Phát `Diagnostic` như `ERROR` hoặc `WARNING`.

**Nó không mặc nhiên gọi `main`, không gọi constructor/static initializer của class mới sinh và không bắt buộc nạp class ấy vào JVM đang chạy.** `JavaCompiler` bản thân là compiler implementation; processor có thể thực thi mã Java ở build-time, nhưng đó là **mã của processor**, không phải hành vi chạy ứng dụng vừa biên dịch.

### Mã nguồn không đồng nghĩa bytecode

Từ source:

~~~java
public final class Hello {
    public static void main(String[] args) {
        System.out.println("hello");
    }
}
~~~

Sau khi compile thành công, bytecode có các tham chiếu tượng trưng tới `java.lang.System.out` và `PrintStream.println`. Lệnh `System.out.println("hello")` **chưa chạy** trong quá trình compiler chỉ tạo class file `Hello.class`.

Compiler cũng có thể tạo **nhiều** `.class` từ một compilation unit: nested classes, anonymous classes, local classes, records, enum, helper types. Vì vậy in-memory file manager thường cần lưu một **map binary name → byte[]**, không chỉ một buffer.

## 3. JavaFileObject và file manager: nơi đặt bytes không quyết định có chạy hay không

`JavaCompiler` đọc file qua `JavaFileObject` và ghi kết quả qua `JavaFileManager`. Bạn có thể cung cấp:

1. **Source trên disk**: `StandardJavaFileManager.getJavaFileObjectsFromPaths(...)`.
2. **Source trong RAM**: kế thừa `SimpleJavaFileObject`, override `getCharContent(...)`.
3. **Class output trên disk**: `StandardJavaFileManager` ghi ra `CLASS_OUTPUT`.
4. **Class output trong RAM**: `ForwardingJavaFileManager` chặn `getJavaFileForOutput(...)` và trả `JavaFileObject` có `openOutputStream()` ghi vào `ByteArrayOutputStream`.

Output trong RAM chỉ thay đổi **đích I/O của compiler**. Một `Map<String, byte[]>` thu được là dữ liệu của host ứng dụng; JVM chưa tự định nghĩa class từ các bytes ấy.

Một ví dụ class output:

~~~text
compile("demo.Dynamic")
       |
       v
Map<String, byte[]>
  "demo.Dynamic" -> CA FE BA BE 00 00 00 3D ...
       |
       +--> Có thể lưu artifact, inspect bằng ASM/javap, ký, kiểm tra
       |
       +--> Có thể tạo custom ClassLoader để defineClass
       |
       +--> Có thể bỏ bytes nếu chỉ cần diagnostics
~~~

`CA FE BA BE` là magic number class file; `00 00 00 3D` tương ứng minor 0, major 61 (Java 17). Bytes này **không phải** chuỗi văn bản Java source. Việc decode nó như UTF-8 rồi `eval` không phải cách JVM nạp class.

## 4. Ví dụ Java 17 độc lập: biên dịch RAM → nạp → khởi tạo → chạy

Ví dụ sau dùng hoàn toàn API JDK 17+, không ghi source hay class file sinh ra xuống disk. Chỉ cần tạo **một tệp host `InMemoryBoundaryDemo.java`**; tệp này thực thi compiler, giữ bytecode trong `Map`, rồi tạo hai class loader riêng.

**Tệp đầy đủ `InMemoryBoundaryDemo.java`:**

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

public final class InMemoryBoundaryDemo {
    static final class Source extends SimpleJavaFileObject {
        private final String source;

        Source(String binaryName, String source) {
            super(
                    URI.create("string:///"
                            + binaryName.replace('.', '/')
                            + Kind.SOURCE.extension),
                    Kind.SOURCE
            );
            this.source = source;
        }

        @Override
        public CharSequence getCharContent(
                boolean ignoreEncodingErrors) {
            return source;
        }
    }

    static final class ClassBytes extends SimpleJavaFileObject {
        private final ByteArrayOutputStream buffer =
                new ByteArrayOutputStream();

        ClassBytes(String binaryName, Kind kind) {
            super(
                    URI.create("mem:///"
                            + binaryName.replace('.', '/')
                            + kind.extension),
                    kind
            );
        }

        @Override
        public OutputStream openOutputStream() {
            return buffer;
        }

        byte[] copyBytes() {
            return buffer.toByteArray();
        }
    }

    static final class MemoryManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        private final Map<String, ClassBytes> output = new HashMap<>();

        MemoryManager(StandardJavaFileManager delegate) {
            super(delegate);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location,
                String className,
                JavaFileObject.Kind kind,
                FileObject sibling) {
            ClassBytes file = new ClassBytes(className, kind);
            output.put(className, file);
            return file;
        }

        Map<String, byte[]> snapshot() {
            Map<String, byte[]> result = new HashMap<>();
            output.forEach(
                    (name, file) -> result.put(name, file.copyBytes()));
            return Map.copyOf(result);
        }
    }

    static final class BytesLoader extends ClassLoader {
        private final Map<String, byte[]> classes;

        BytesLoader(Map<String, byte[]> classes) {
            super(ClassLoader.getPlatformClassLoader());
            this.classes = classes;
        }

        @Override
        protected Class<?> findClass(String binaryName)
                throws ClassNotFoundException {
            byte[] bytes = classes.get(binaryName);
            if (bytes == null) {
                throw new ClassNotFoundException(binaryName);
            }
            return defineClass(binaryName, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "JDK compiler is unavailable");
        }

        String source = """
                package demo;

                public final class Dynamic {
                    static {
                        System.out.println("initialized");
                    }

                    public static String message() {
                        return "Hello from bytes";
                    }
                }
                """;

        Map<String, byte[]> compiled;
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (MemoryManager manager = new MemoryManager(
                compiler.getStandardFileManager(
                        null, Locale.ROOT, StandardCharsets.UTF_8))) {
            JavaFileObject unit =
                    new Source("demo.Dynamic", source);

            JavaCompiler.CompilationTask task = compiler.getTask(
                    null,
                    manager,
                    diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null,
                    List.of(unit)
            );

            boolean ok = Boolean.TRUE.equals(task.call());
            System.out.println("compiled: " + ok);

            if (!ok) {
                for (Diagnostic<? extends JavaFileObject> d
                        : diagnostics.getDiagnostics()) {
                    System.err.println(d.getMessage(Locale.ROOT));
                }
                return;
            }

            compiled = manager.snapshot();
        }

        System.out.println(
                "bytes present: " + compiled.containsKey("demo.Dynamic"));

        BytesLoader firstLoader = new BytesLoader(compiled);
        Class<?> firstClass = Class.forName(
                "demo.Dynamic", false, firstLoader);
        System.out.println("loaded: " + firstClass.getName());

        Object result = firstClass.getMethod("message").invoke(null);
        System.out.println("result: " + result);

        BytesLoader secondLoader = new BytesLoader(compiled);
        Class<?> secondClass = Class.forName(
                "demo.Dynamic", false, secondLoader);
        System.out.println("same class: " + (firstClass == secondClass));
    }
}
~~~

Biên dịch và chạy **host**, từ thư mục có file trên JDK 17 trở lên:

~~~bash
javac --release 17 -encoding UTF-8 InMemoryBoundaryDemo.java
java InMemoryBoundaryDemo
~~~

**Stdout chính xác trong điều kiện JDK 17+ thông thường:**

~~~text
compiled: true
bytes present: true
loaded: demo.Dynamic
initialized
result: Hello from bytes
same class: false
~~~

Các kết quả phản ánh **ranh giới thực tế**:

1. `compiled: true` nghĩa là `JavaCompiler` hoàn tất lần compile. Chưa có dòng `initialized` vì static initializer của `Dynamic` **không chạy khi biên dịch**.
2. `bytes present: true` cho thấy file manager đã lưu `demo.Dynamic.class` trong RAM và trả bản sao byte array.
3. `Class.forName("demo.Dynamic", false, firstLoader)` yêu cầu tìm/định nghĩa class nhưng **không yêu cầu khởi tạo**. Vì thế dòng `loaded: demo.Dynamic` xuất hiện trước `initialized`.
4. `firstClass.getMethod("message").invoke(null)` gọi method `static`. Đây là một **active use** khiến JVM khởi tạo class nếu chưa khởi tạo. Static initializer in `initialized`, sau đó method trả `Hello from bytes`.
5. `secondLoader` định nghĩa một runtime class **khác** với cùng binary name. Kết quả `firstClass == secondClass` là `false` vì **defining class loader khác nhau**.

Ví dụ cố ý chọn parent `ClassLoader.getPlatformClassLoader()` cho custom loader. Vì class `demo.Dynamic` chỉ phụ thuộc JDK base classes, platform/bootstrap delegation giải quyết được dependency và loader có thể định nghĩa riêng `demo.Dynamic`. Trong dự án có dependency ứng dụng, phải quyết định parent delegation hoặc cơ chế tìm class phù hợp để class mới nhìn thấy kiểu cần thiết.

### Một chi tiết về đóng tài nguyên

`MemoryManager` kế thừa `ForwardingJavaFileManager`, và `try-with-resources` đóng manager cùng delegate chuẩn của nó. `snapshot()` tạo **bản sao bytecode** trước khi file manager được đóng. Vì vậy loader có thể nạp class sau khi session compile đã kết thúc.

Đây là ranh giới tốt giữa pha compile và pha execution: **không giữ file manager sống chỉ để JVM tiếp tục chạy code đã compile**. Trong hệ thống dài hạn, quản lý vòng đời class loader và object do nó định nghĩa riêng biệt.

## 5. ClassLoader, defineClass và danh tính kiểu

`ClassLoader` nhận yêu cầu nạp một binary name. Khi custom loader tìm bytes và gọi:

~~~java
return defineClass(binaryName, bytes, 0, bytes.length);
~~~

JVM định nghĩa class mới từ bytecode nếu định dạng/định danh và các quy tắc nạp cho phép. Đây là **fragment** thuộc một phương thức `findClass` hợp lệ, không phải API có thể gọi ở bất kỳ nơi nào không có quyền truy cập. `defineClass` là protected API của `ClassLoader` và kiểm tra nhiều điều kiện, chẳng hạn tên/bytes hợp lệ.

Các khái niệm cần phân biệt:

| Khái niệm | Ý nghĩa |
| --- | --- |
| Binary name | Ví dụ `demo.Dynamic` hoặc `pkg.Outer$Inner` |
| Defining loader | Loader thực sự gọi định nghĩa class bằng cơ chế hợp lệ |
| Initiating loader | Loader bắt đầu yêu cầu nạp class; có thể nhận class do parent định nghĩa |
| Runtime class identity | **Cặp (binary name, defining loader)** |
| `Class<?>` object | Đại diện runtime của class đã được JVM định nghĩa |
| Byte array class file | Dữ liệu để định nghĩa class; **không phải** `Class<?>` |

Hai class cùng binary name do **hai defining loader khác nhau** tạo ra là hai runtime type khác nhau. Chúng không tự động cast cho nhau. Trong plugin system, phải thiết kế rõ class/interface dùng chung được parent cung cấp, và class implementation riêng được plugin loader định nghĩa.

### Parent delegation có thể thay đổi kết quả

Một custom loader mặc định thường dùng parent-first: `loadClass` hỏi parent trước, rồi mới gọi `findClass` nếu parent không trả được class. Nếu parent đã định nghĩa `demo.Dynamic` cùng binary name, method `findClass` ở custom loader có thể **không được gọi**. Thí nghiệm dùng package `demo` riêng và platform parent để tránh xung đột đó.

Nếu triển khai child-first loader hoặc override `loadClass`, bạn cần hiểu thread safety, package sealing, code source, bảo mật và shared APIs; không đơn giản đổi thứ tự để nạp bất kỳ class nào mong muốn.

### “Chưa initialized” không có nghĩa “chưa verified”

Lời gọi `Class.forName(name, false, loader)` không yêu cầu khởi tạo class, nhưng JVM có thể thực hiện verification/linking **trước khi init** theo quy tắc triển khai. Vì vậy không thể nói mọi lỗi class file đều chỉ xuất hiện khi gọi method. Một class có bytecode hỏng có thể bị từ chối ngay lúc define/link, còn một symbolic reference không hợp lệ có thể chỉ gây lỗi khi instruction liên quan được resolve sau đó.

## 6. Loading, linking, initialization theo JVM Specification

Các giai đoạn liên quan:

### 6.1. Loading

JVM nhận class được yêu cầu và tìm định nghĩa class: từ file/JAR/module, hoặc bytes do user-defined loader cung cấp. Class file phải có định dạng chấp nhận được; sai class version có thể gây `UnsupportedClassVersionError`, bytecode hỏng có thể gây `ClassFormatError`.

### 6.2. Linking

Thường được chia thành:

- **Verification:** xác minh class file/bytecode theo các ràng buộc của JVM; lỗi có thể là `VerifyError`.
- **Preparation:** cấp phát/khởi tạo giá trị mặc định cho các static fields (với ngoại lệ/quy tắc liên quan tới constant values). **Không đồng nghĩa chạy static initializer của source**.
- **Resolution:** phân giải symbolic references từ constant pool thành class/field/method tương ứng; có thể eager hoặc lazy trong giới hạn đặc tả.

Một số thông báo như `NoSuchMethodError`, `NoSuchFieldError`, `IllegalAccessError` hay `IncompatibleClassChangeError` phát sinh khi linking/resolution hoặc lúc instruction cần dùng tham chiếu bị lỗi.

### 6.3. Initialization

Khi class bắt đầu được khởi tạo theo quy tắc active use, JVM thực hiện class initialization method (`<clinit>`) nếu cần, chạy static field initializers và static blocks theo thứ tự thích hợp. Đây là lúc chương trình có thể in text, tạo thread, mở kết nối hoặc ném exception do mã static initializer.

Ví dụ:

~~~java
class Example {
    static int number = initialize();

    static int initialize() {
        System.out.println("init");
        return 42;
    }
}
~~~

Chỉ biên dịch class này không in `init`. Một số thao tác khởi tạo class như gọi method static `Example.initialize()` có thể khiến `init` được in trước khi lời gọi method hoàn tất. Đoạn này là **minh họa**, chưa có `main` để chạy độc lập.

**Không phải mọi tham chiếu `Example` đều buộc initialization ngay.** Class literal `Example.class` có thể lấy Class object mà không khởi tạo class. `Class.forName(name, true, loader)` thì **có yêu cầu khởi tạo**; `Class.forName(name, false, loader)` thì không.

## 7. Reflection: gọi code đã nạp, không phải compile

Sau khi có `Class<?>`, reflection có thể tìm và gọi constructor hoặc method:

~~~java
Class<?> type = Class.forName(
        "demo.Dynamic", false, myLoader);
Object result = type.getMethod("message").invoke(null);
~~~

Đây là fragment trong method có `myLoader` hợp lệ; method `message()` phải public, static và không có tham số để lời gọi giống ví dụ. `getMethod` tìm public method theo tên và tham số; `invoke` chạy method (với checking và wrapping exception tương ứng).

Nếu method ném exception, reflection có thể ném `InvocationTargetException` bao bọc nguyên nhân từ method, cần đọc `getCause()` để biết lỗi ứng dụng. Reflection **không dùng để tạo bytecode** và không thể “thêm method” vào class đã nạp. Nó chỉ tìm/call method có trong runtime class.

### Không cần reflection để thực thi bytecode

Bạn có thể biên dịch source xuống `.class` trên disk, rồi chạy:

~~~bash
javac --release 17 Hello.java
java Hello
~~~

Hoặc một class khác có kiểu compile-time rõ ràng có thể gọi trực tiếp:

~~~java
Hello.main(new String[0]);
~~~

Đoạn cuối là fragment và đòi hỏi `Hello` có mặt trong compile/runtime classpath. Reflection cần thiết hơn khi host **không biết trước kiểu** hoặc khi class được nạp từ bytes qua loader tùy biến. Sự khác biệt là **cách gọi và liên kết API**, không phải mức độ “chạy thật” của bytecode.

## 8. ClassFile bytes hợp lệ chưa bảo đảm runtime thành công

Một byte array bắt đầu bằng `CAFEBABE`, có major version được runtime hỗ trợ vẫn có thể thất bại:

| Giai đoạn | Tình huống | Lỗi có thể gặp |
| --- | --- | --- |
| Compile | Sai cú pháp, kiểu không tìm thấy, checked exception chưa xử lý | Diagnostics `ERROR`, `task.call() == false` |
| Define/load | Class file bị cắt/hỏng hoặc không hợp chuẩn | `ClassFormatError` |
| Define/load | Class file phiên bản cao hơn JVM runtime hoặc preview không phù hợp | `UnsupportedClassVersionError` |
| Verification | Bytecode không thỏa điều kiện verifier | `VerifyError` |
| Resolution/linking | Class dependency không tìm được khi cần | `NoClassDefFoundError` |
| Resolution | Method/field mà bytecode trỏ tới không còn tồn tại | `NoSuchMethodError` / `NoSuchFieldError` |
| Resolution/access | Class/member thay đổi không tương thích hoặc không được truy cập | `IncompatibleClassChangeError` / `IllegalAccessError` |
| Initialization | Static initializer ném exception | `ExceptionInInitializerError` (cùng các quy tắc khởi tạo lỗi) |
| Execution | Exception nghiệp vụ do code vừa chạy ném | Ví dụ `IllegalArgumentException` hoặc `IOException` |
| Reflection invocation | Code được gọi ném exception | `InvocationTargetException` bao quanh cause |

**Không nên coi bảng là ánh xạ một-một tuyệt đối.** Một số lỗi linkage xảy ra sớm hay muộn theo việc JVM resolve các tham chiếu; cùng một kiểu exception có thể xuất hiện ở nhiều thời điểm. Điều quan trọng là xác định **nó thuộc compile hay runtime class loading/linking/execution** trước khi tìm cách sửa.

Ví dụ `task.call() == true` nhưng lúc tải class ném `UnsupportedClassVersionError` nếu host compile target mới hơn runtime khác. Nếu compiler và loader nằm cùng một JDK 17 và target `--release 17` như thí nghiệm, loại mismatch đó không xảy ra trong điều kiện bình thường; vẫn có các vấn đề classpath hoặc bytecode khác nếu build phức tạp.

## 9. Lỗi runtime từ static initializer: bằng chứng compiler không chạy ứng dụng

Tạo file **`InitFailureDemo.java`** độc lập:

~~~java
public final class InitFailureDemo {
    static final class Broken {
        static {
            System.out.println("Broken initializing");
            if (System.nanoTime() != Long.MIN_VALUE) {
                throw new IllegalStateException("bad static state");
            }
        }

        static void run() {
            System.out.println("never reached");
        }
    }

    public static void main(String[] args) {
        System.out.println("before initialization");
        try {
            Broken.run();
        } catch (ExceptionInInitializerError ex) {
            System.out.println("initialization failed");
        }
    }
}
~~~

Compile và chạy:

~~~bash
javac --release 17 -encoding UTF-8 InitFailureDemo.java
java InitFailureDemo
~~~

**Stdout chính xác trong trường hợp chương trình thực thi nhánh lỗi:**

~~~text
before initialization
Broken initializing
initialization failed
~~~

Đây là minh họa luồng khởi tạo với điều kiện runtime gần như chắc chắn khác `Long.MIN_VALUE`; để tránh phụ thuộc vào điều kiện hiếm về đồng hồ, có thể thay điều kiện bằng một method luôn trả true mà compiler không đánh giá như compile-time constant. Trong thực hành bình thường, `System.nanoTime() != Long.MIN_VALUE` sẽ đúng. Nếu muốn output **quyết định tuyệt đối** trong mọi môi trường, dùng phiên bản sau:

~~~java
public final class InitFailureDemo {
    static final class Broken {
        static {
            System.out.println("Broken initializing");
            fail();
        }

        private static void fail() {
            throw new IllegalStateException("bad static state");
        }

        static void run() {
            System.out.println("never reached");
        }
    }

    public static void main(String[] args) {
        System.out.println("before initialization");
        try {
            Broken.run();
        } catch (ExceptionInInitializerError ex) {
            System.out.println("initialization failed");
        }
    }
}
~~~

**Đây là bản thay thế hoàn chỉnh cho tệp `InitFailureDemo.java`** với output chính xác ba dòng như trên. `javac` không gọi `Broken.fail()` khi biên dịch; chỉ lúc `Broken.run()` là active use, JVM khởi tạo `Broken` và exception mới xuất hiện. Không chạy cả hai phiên bản trong cùng một tệp.

Khi class initialization thất bại, class thường bị đánh dấu erroneous đối với defining loader. Các lần active use tiếp theo có thể gây `NoClassDefFoundError` với nguyên nhân liên quan đến khởi tạo trước đó; không nên tạo vòng retry mù quáng trên cùng class loader và mong static initializer chạy lại.

## 10. In-memory compilation: nhiều class và dependency classpath

Thí nghiệm ở mục 4 có một output class. Dự án thực tế có thể có nhiều type:

~~~text
source input:
  pkg.Service.java

generated bytecode:
  pkg.Service.class
  pkg.Service$Helper.class
  pkg.Service$1.class
~~~

Vì vậy file manager nên lưu output theo **binary name** hoặc một khóa chứa location, kind, name để tránh trùng. Khi processor tạo resource, còn phải xử lý `getFileForOutput(...)` nếu muốn giữ tất cả output trong memory. Override chỉ `getJavaFileForOutput(...)` trong ví dụ đủ cho **class output** nhưng **không phải một file manager RAM toàn diện cho source/resource do annotation processor sinh ra**.

Điểm cần phân biệt:

- **Biên dịch mã mới với thư viện đã có trên disk**: custom file manager có thể forward lookup tới `StandardJavaFileManager`.
- **Biên dịch mã mới phụ thuộc vào class vừa compile trong RAM ở task trước**: compiler task sau không tự tìm class đó nếu file manager chỉ giữ `byte[]` mà không cho compiler tra lại nó.
- **Chạy mã đã compile trong RAM**: custom class loader cần bytes của các type liên quan và parent phù hợp cho dependency.
- **Giữ output tách biệt qua nhiều compilation sessions**: quản lý version/cache/identity và binary name collisions cẩn thận.

Ví dụ: Task 1 sinh `lib.Calculator.class` trong `Map`. Task 2 cần import `lib.Calculator`. Chỉ đặt `Map` trong `BytesLoader` của runtime **không** khiến `javac` của task 2 tự tìm được `Calculator`. File manager cho task 2 phải cung cấp `JavaFileObject.Kind.CLASS` tương ứng (và lookup/listing khi compiler yêu cầu), hoặc biên dịch dependency vào đường classpath hợp lệ, hoặc đưa cả hai nguồn vào cùng compilation task.

**Ranh giới compile-time lookup và runtime class loading là độc lập.**

## 11. Tách compile session và load session trong ứng dụng chạy lâu

Một hệ thống REPL hoặc IDE thường có:

~~~text
[Source input v1] -> [Compiler task 1] -> [bytecode v1]
                                          |
                                     [Loader A]
                                          |
                                      Class A

[Source input v2] -> [Compiler task 2] -> [bytecode v2]
                                          |
                                     [Loader B]
                                          |
                                      Class B
~~~

Nếu v2 cùng binary name với v1, muốn dùng bản mới thường tạo **loader mới** có định nghĩa class mới. Ghi đè byte array trong map của loader đã định nghĩa class cũ không thay định nghĩa đó.

Phần khó:

1. **Loại bỏ class loader cũ** chỉ có thể khi không còn tham chiếu sống từ thread, instance, Class/Method, cache, ThreadLocal, static registry và các cơ chế tương tự. Class unloading là công việc của GC, không phải lập tức khi gọi một method.
2. **Chia sẻ interface/API giữa loaders**: đặt các interfaces chung vào parent/loader ổn định, để object plugin có thể cast qua interface chung.
3. **Resource isolation**: class loader quyết định cả việc tìm class và resource; không dùng context loader bất kỳ nếu cần resource từ bytes/plugin riêng.
4. **Recompile nhiều source phụ thuộc**: khi ABI thay đổi, class v1 đã compile có thể không tương thích API v2 dù loader mới nạp thành công.
5. **Diagnostics và artifact lifecycle**: lưu theo compilation id, không trộn bytecode từ lần compile thất bại với build trước.

Không nên dùng một map toàn cục không phiên bản rồi thay bytes giữa lúc threads đang chạy; việc class đã được define, symbolic references và code đang thực thi có những vòng đời khác với nội dung map.

## 12. Security: biên dịch không biến source thành sandbox an toàn

**Đây là ranh giới an toàn rất quan trọng.** Một chương trình host có thể compile source của người dùng mà không thực thi những class mới; việc đó không có nghĩa source người dùng luôn vô hại, nhất là khi **annotation processing** hoặc compiler plugins được bật. Processor có thể thực thi code Java trong quá trình biên dịch.

Và khi host chủ động load/invoke bytecode, code mới có thể:

- Truy cập file, network hoặc tài nguyên mà tiến trình host có quyền.
- Tạo threads, dùng CPU/memory và thay đổi static/shared state.
- Gọi API khác trong runtime tùy khả năng truy cập.
- Tương tác với context class loader, reflection hoặc native libraries tùy cấu hình.

Một custom `ClassLoader` **không phải cơ chế cô lập bảo mật** đủ để chạy Java không đáng tin. Class loader chủ yếu giải quyết **namespace và vòng đời class**. Java Security Manager đã bị hạn chế/loại bỏ trong các release hiện đại; không nên dựa vào cơ chế này làm sandbox chung cho code chưa tin cậy.

Với hệ thống cho phép biên dịch và chạy code của bên thứ ba, ưu tiên một **process/container cô lập theo chính sách của môi trường**: giới hạn quyền file/network, CPU/time/memory, số process/thread, quyền người dùng, thư mục tạm và vòng đời, đồng thời vô hiệu hóa annotation processors/plugins không đáng tin trong compile hoặc thực hiện compile trong môi trường cô lập tương đương. Những biện pháp này là **thiết kế hệ thống**, không được thay thế bằng `ClassLoader#defineClass`.

### Phân biệt hoạt động compile của processor với app runtime

Bản thân `JavaCompiler` chạy một pipeline compile. Nếu processor được khám phá/chỉ định và chạy trong JVM host, **processor code** có thể tạo side effect **trong lúc compile**, ngay cả khi bạn chưa load class vừa biên dịch. Vì vậy câu “compile không chạy code” cần hiểu chính xác là **không chạy method/initializer của ứng dụng vừa biên dịch như một chương trình**, không phải cam kết không code nào được thực thi bởi compiler/tooling.

Để tránh processor discovery ngoài ý muốn trong ví dụ đơn giản, code sử dụng option `-proc:none`. Đây là lựa chọn minh họa khi không cần annotation processing; trong build cần processor thì phải quản trị processor path và nguồn tin cậy có chủ đích.

## 13. Module, package và giới hạn API khi load bytecode

### Package name và defineClass

`defineClass(binaryName, bytes, ...)` yêu cầu bytecode có tên class phù hợp. Nếu truyền bytes của `demo.Dynamic` nhưng binaryName là `demo.Other`, JVM có thể ném lỗi tên class sai như `NoClassDefFoundError: wrong name` hoặc các lỗi liên quan. Không dùng tên file tùy tiện làm binary name.

Các lớp thuộc package bị hạn chế như `java.*` không thể được tự do định nghĩa bởi user class loader. Package sealing và signer/certificate constraints cũng có thể tác động khi nhiều nguồn định nghĩa các class trong một package.

### JPMS module path không tự được chuyển sang custom loader

Nếu bytecode mới phụ thuộc một named module, host phải thiết kế module readability/exports/opens và module layer khi cần; nạp bytes qua một custom class loader **không tự giải quyết toàn bộ module graph**.

Một class được define thông thường qua `defineClass` trong một user-defined loader thường thuộc unnamed module của loader, với các quy tắc module/access áp dụng tương ứng. Reflection vẫn chịu Java accessibility và module encapsulation. `getDeclaredMethod` thấy một method không bảo đảm `invoke` được phép gọi nếu không có quyền truy cập.

### Hidden classes

Từ Java 15, `MethodHandles.Lookup.defineHiddenClass(...)` cung cấp cơ chế định nghĩa hidden class cho nhu cầu như framework/language runtime. Nó có danh tính, khả năng lookup và lifecycle khác class có binary name thông thường. **Không cần** hidden classes để học ranh giới compiler → bytes → loader ở bài này. Nếu xây runtime động phức tạp, hãy nghiên cứu API phù hợp mục đích thay vì tự áp dụng hidden class như một thay thế đơn giản cho file manager.

## 14. Chẩn đoán theo triệu chứng

| Hiện tượng | Ranh giới nên kiểm tra | Hướng điều tra |
| --- | --- | --- |
| `task.call() == false` | Compile | Đọc `DiagnosticCollector`, source level, dependencies và JavaFileManager |
| Compile thành công nhưng map rỗng | File manager output | `getJavaFileForOutput` có được gọi? Đúng kind/location? Stream đã đóng? |
| `ClassNotFoundException` khi `Class.forName` | Load/lookup | Binary name, parent delegation, loader map và dependency |
| `NoClassDefFoundError` | Load/link/initialization | Class phụ thuộc có sẵn? Trước đó class init lỗi? Cause/stack trace |
| `ClassFormatError` / `VerifyError` | Define/verification | Bytes có hợp lệ không? Có bị cắt/ghi sai kind không? |
| `UnsupportedClassVersionError` | Load | Đọc major/minor, đối chiếu target `--release` và JVM runtime |
| `NoSuchMethodError` | Linking/ABI | Runtime class khác compile-time API? Kiểm tra method descriptor |
| `ExceptionInInitializerError` | Initialization | Static initializer/cause, lần active use đầu tiên |
| `InvocationTargetException` | Reflective execution | Đọc `getCause()`; exception từ method đích |
| Đổi bytes nhưng hành vi không đổi | Loader lifecycle | Class đã được define; tạo loader mới hoặc reload theo cơ chế hợp lệ |
| `ClassCastException` dù cùng tên class | Loader identity | So sánh defining loader của cả hai type |
| Runtime không tìm được resource | Loader/resource lookup | `getResourceAsStream`, package path và resource output trong manager |
| Compiler task 2 không thấy class task 1 | Compile-time class lookup | Forwarding file manager chưa hỗ trợ lookup trong RAM hoặc thiếu classpath |
| Process bị treo/hết RAM sau khi invoke | Execution/isolation | Giới hạn thời gian/tài nguyên ở process boundary, không chỉ class loader |

### Checklist debug theo thứ tự

1. **Compiler có sẵn không?** `ToolProvider.getSystemJavaCompiler()` có thể `null` trên runtime image không có compiler.
2. **Đầu vào đúng không?** URI của `JavaFileObject`, source content, encoding, classpath/module path.
3. **Task compile thành công không?** Kiểm tra `Boolean.TRUE.equals(task.call())` và diagnostics (đừng chỉ nhìn một dòng log).
4. **Bytes output có thật không?** Map chứa đúng binary name, có classfile header và kích thước hợp lý? Có nhiều generated class khác?
5. **Dùng loader nào?** Parent-first có lấy class khác cùng tên? `defineClass` có được gọi không?
6. **Class đã initialize chưa?** Dùng `Class.forName(name, false, loader)` nếu muốn quan sát giai đoạn load chưa init.
7. **Lời gọi đầu tiên gây lỗi gì?** Phân biệt `LinkageError`, `ExceptionInInitializerError` và `InvocationTargetException`.
8. **Dependency của runtime đã được nạp/nhìn thấy chưa?** Compile classpath và loader classpath là hai cấu hình độc lập.
9. **Có reload không?** Nếu source thay đổi, class trong loader cũ không tự cập nhật.
10. **Có code không đáng tin không?** Quản lý processor và runtime execution bằng process isolation/throttling phù hợp.

## 15. Bài tập tự kiểm tra

**Bài 1.** Sau `task.call() == true`, chưa hề tạo custom loader hay gọi `java`. Static initializer trong source vừa compile có chạy chưa?

**Đáp án:** Chưa, chỉ do compilation task. Compiler tạo bytecode chứ không chủ động khởi tạo class ứng dụng mới sinh. Lưu ý annotation processors nếu được bật là code tooling có thể chạy khi compile.

**Bài 2.** `Class.forName("demo.Dynamic", false, loader)` trả `Class<?>`. Có bảo đảm static initializer đã chạy không?

**Đáp án:** Không. `initialize=false` không yêu cầu class initialization. JVM vẫn có thể thực hiện verification/linking như cần thiết.

**Bài 3.** Cùng một `byte[]` định nghĩa `demo.Dynamic` bởi hai defining class loaders khác nhau. Hai `Class<?>` có `==` không?

**Đáp án:** Không, trong trường hợp mỗi loader tự định nghĩa class riêng và không ủy quyền tới cùng một định nghĩa từ parent. Class identity gồm binary name + defining loader.

**Bài 4.** Vì sao `Map<String, byte[]>` dùng để chạy task 1 không tự giúp `javac` của task 2 tìm class ấy?

**Đáp án:** Compiler lookup qua `JavaFileManager` và các đường tìm source/class. Runtime BytesLoader là cơ chế khác; muốn task 2 thấy class phải cung cấp bytes qua file manager/classpath hoặc compile chung source.

**Bài 5.** Khi gọi method bằng `Method.invoke` và method ném `IllegalArgumentException`, code host thường nhận gì?

**Đáp án:** `InvocationTargetException` bao quanh exception do method đích ném; dùng `getCause()` để xem lỗi gốc. Bản thân thao tác reflection cũng có thể ném lỗi riêng do lookup/access/arguments.

**Bài 6.** Một class mới đã compile với `--release 21`, nhưng JVM dùng loader Java 17. Kết quả có thể là gì?

**Đáp án:** JVM Java 17 không hỗ trợ class file major 65 của Java 21, nên có thể ném `UnsupportedClassVersionError` khi tải class. Cần target tương thích hoặc runtime đủ mới.

**Bài 7.** Có thể xem một custom ClassLoader là sandbox an toàn để chạy source Java không đáng tin không?

**Đáp án:** Không. Loader tạo namespace class, không tự hạn chế I/O, CPU, network hoặc native access theo chính sách bảo mật. Với code không đáng tin phải thiết kế isolation ở cấp process/OS/container.

**Bài 8.** Tại sao `Class.forName(name, true, loader)` và `Class.forName(name, false, loader)` có thể khác thứ tự output với static block?

**Đáp án:** Bản `true` yêu cầu initialization nên static block có thể chạy trong lời gọi; bản `false` không yêu cầu initialization, static block thường chạy khi gặp active use sau đó.

## Ghi nhớ

- **Compilation thành công tạo bytecode**, không tự đồng nghĩa JVM đã nạp, liên kết, khởi tạo hay thực thi class đó.
- **In-memory file manager** lưu class file dưới dạng bytes; **ClassLoader** cần được chỉ định để định nghĩa class; **lời gọi method/constructor** mới thực thi logic ứng dụng.
- **Loading/linking/initialization khác nhau**: `Class.forName(..., false, ...)` giúp quan sát ranh giới trước init; reflective invocation static method có thể kích hoạt init.
- **Danh tính runtime của class = binary name + defining loader**. Cùng bytes do hai loaders khác nhau định nghĩa vẫn là hai runtime types.
- **Compiler classpath và runtime loader dependencies độc lập**; khi biên dịch nhiều lượt trong RAM, phải cung cấp output của lượt trước cho cả compiler lookup nếu cần.
- **Biên dịch mã chưa tin cậy cũng có rủi ro khi processor/plugin chạy**, còn nạp/thực thi bytecode không được biến thành sandbox chỉ nhờ custom class loader.
- Khi lỗi xảy ra, xác định nó thuộc **compile, define/load, verification/linking, initialization hay invocation** để xử lý đúng nguyên nhân.
