# Thu bytecode và nạp bằng ClassLoader thích hợp

## 1. Mục tiêu: từ mã nguồn trong bộ nhớ đến lớp Java có thể sử dụng

Trong Java, **biên dịch trong bộ nhớ** thường gồm hai phần độc lập:

1. **Thu bytecode:** đưa mã nguồn Java từ một `String` hoặc dữ liệu khác vào `JavaCompiler`, rồi thay đầu ra `.class` trên đĩa bằng các `JavaFileObject` ghi vào `ByteArrayOutputStream`. Kết quả là một tập `Map<String, byte[]>` theo **binary name** của mỗi lớp.
2. **Nạp lớp:** cung cấp các byte `.class` cho một `ClassLoader` phù hợp. Loader gọi `defineClass(binaryName, bytes, offset, length)` để JVM định nghĩa lớp, rồi ứng dụng mới có thể dùng reflection hoặc một interface dùng chung để gọi mã đã biên dịch.

**Biên dịch thành công chưa đồng nghĩa JVM đã nạp hoặc chạy lớp mới.** `JavaCompiler.CompilationTask.call()` tạo ra bytecode; `ClassLoader.loadClass(...)` tìm/nạp `Class<?>`; khởi tạo lớp và thực thi phương thức là những bước tiếp theo theo quy tắc JVM.

Sơ đồ luồng dữ liệu:

~~~text
String chứa mã nguồn Java
    |
    v
SimpleJavaFileObject (Kind.SOURCE, URI string:///...)
    |
    v
JavaCompiler.getTask(...).call()
    |
    v
ForwardingJavaFileManager.getJavaFileForOutput(...)
    |
    +--> Bytecode JavaFileObject #1 --> byte[] của Foo.class
    +--> Bytecode JavaFileObject #2 --> byte[] của Foo$Helper.class
    +--> ... (mọi class file được compiler sinh ra)
    |
    v
Map<binaryName, byte[]>
    |
    v
MemoryClassLoader.findClass(name)
    |
    v
defineClass(name, bytes, 0, bytes.length)
    |
    v
Class<?> --> reflection hoặc interface dùng chung
~~~

Với trường hợp chỉ muốn tạo file `.class` hoặc JAR phục vụ build, không nhất thiết phải nạp bytecode vào JVM hiện tại. Ngược lại, nếu cần tạo plugin, biểu thức, rule hay lớp từ source ở runtime, việc chọn và quản lý `ClassLoader` là một phần quan trọng của thiết kế.

## 2. Các API cần hiểu và trách nhiệm riêng

| API | Công dụng |
| --- | --- |
| `javax.tools.ToolProvider.getSystemJavaCompiler()` | Lấy trình biên dịch Java hệ thống; trả `null` nếu runtime thiếu implementation |
| `javax.tools.JavaCompiler.getTask(...)` | Tạo một tác vụ biên dịch có source/options/file manager được chỉ định |
| `javax.tools.SimpleJavaFileObject` | Tạo source/object ảo có URI và `Kind` để compiler có thể đọc/ghi |
| `javax.tools.StandardJavaFileManager` | Cơ chế tìm source, dependency, module/class path và output mặc định |
| `javax.tools.ForwardingJavaFileManager` | Bọc file manager khác để chỉ tùy biến hành vi cần thay thế |
| `JavaFileManager.getJavaFileForOutput(...)` | Điểm mở rộng để chặn yêu cầu ghi `Kind.CLASS` của compiler |
| `java.io.ByteArrayOutputStream` | Nhận các byte do compiler ghi vào một class file ảo |
| `java.lang.ClassLoader.findClass(...)` | Tìm class mà parent loader không giải quyết được |
| `ClassLoader.defineClass(String, byte[], int, int)` | Định nghĩa lớp từ bytecode cùng với binary name xác định |
| `Class<?>` | Kết quả lớp đã được nạp, dùng cho reflection, kiểm tra kiểu và tạo instance |

Có hai cặp dễ nhầm:

- `JavaFileObject` đại diện cho **tệp mã nguồn hoặc tệp class** ở giao diện compiler; nó chưa phải `java.lang.Class<?>` của JVM.
- `JavaFileManager` phục vụ **đường đi biên dịch**; `ClassLoader` phục vụ **đường đi nạp và liên kết lớp lúc chạy**. Việc tạo một file manager trong bộ nhớ không tự khiến `ClassLoader` mặc định biết đến bytecode vừa tạo.

Trong ứng dụng có named module, mã sử dụng `javax.tools` cần `requires java.compiler;` và **môi trường chạy** cần cung cấp system compiler (thường là module `jdk.compiler`) nếu thực sự muốn biên dịch. Có `java.compiler` API nhưng thiếu compiler implementation thì `ToolProvider.getSystemJavaCompiler()` có thể trả `null`.

## 3. Định danh class: dùng binary name, không suy đoán từ tên file nguồn

Một source:

~~~java
package sample.generated;
public class Greeter {
    private static class Helper {}
}
~~~

có thể sinh **hai file class**:

~~~text
sample/generated/Greeter.class
sample/generated/Greeter$Helper.class
~~~

Binary name dùng với `ClassLoader.loadClass(...)` là:

- `sample.generated.Greeter`
- `sample.generated.Greeter$Helper`

Dấu `.` phân tách package/class bên ngoài; dấu `$` có thể xuất hiện trong binary name của lớp lồng nhau. Không lấy tên `Greeter.java` rồi mặc định chỉ có một output class. Compiler cũng có thể tạo bytecode cho anonymous/local class, record hoặc những class khác tùy source.

Map lưu bytecode nên có dạng `Map<String, byte[]>`, **khóa là binary name chính xác do compiler cung cấp qua `getJavaFileForOutput(...)`**. Khi gọi `defineClass`, truyền cùng tên ấy và đúng mảng byte `.class` đã được tạo.

Sử dụng overload `defineClass(String name, byte[] b, int off, int len)` hiện hành. Overload cũ không nhận `name` đã bị deprecated từ rất lâu, không phù hợp cho hướng dẫn mới.

## 4. Ví dụ Java 17+ hoàn chỉnh: compile, thu bytecode và load ngay trong RAM

Chương trình sau được tổ chức thành **một tệp duy nhất `MemoryCompilerLoaderDemo.java`**, không dùng thư viện ngoài. Nó tạo source `sample.generated.Greeter` trong một Java text block, trong đó `Greeter` gọi một lớp lồng nhau `Helper`:

- `Source` cho compiler đọc text nguồn từ RAM.
- `Bytecode` cung cấp `OutputStream` ghi vào `ByteArrayOutputStream`.
- `MemoryFiles` bọc standard file manager, bắt mọi yêu cầu ghi `Kind.CLASS` và giữ chúng theo binary name.
- `MemoryLoader` nạp các class từ bản sao bytecode bằng `findClass`/`defineClass`, đồng thời giữ mô hình parent delegation mặc định.
- `main` kiểm tra kết quả biên dịch, gọi `Greeter.hello("Java")` qua reflection và so sánh danh tính class từ hai loader riêng.

Lưu chính xác đoạn sau thành **`MemoryCompilerLoaderDemo.java`**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
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

public class MemoryCompilerLoaderDemo {
    private static final class Source extends SimpleJavaFileObject {
        private final String content;

        Source(String binaryName, String content) {
            super(URI.create("string:///" + binaryName.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.content = content;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return content;
        }
    }

    private static final class Bytecode extends SimpleJavaFileObject {
        private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        Bytecode(String binaryName, Kind kind) {
            super(URI.create("mem:///" + binaryName.replace('.', '/')
                    + kind.extension), kind);
        }

        @Override
        public OutputStream openOutputStream() {
            return bytes;
        }

        byte[] toByteArray() {
            return bytes.toByteArray();
        }
    }

    private static final class MemoryFiles
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        private final Map<String, Bytecode> generated = new TreeMap<>();

        MemoryFiles(StandardJavaFileManager standard) {
            super(standard);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location, String className,
                JavaFileObject.Kind kind, FileObject sibling) throws IOException {
            if (kind != JavaFileObject.Kind.CLASS) {
                return super.getJavaFileForOutput(
                        location, className, kind, sibling);
            }
            Bytecode output = new Bytecode(className, kind);
            generated.put(className, output);
            return output;
        }

        Map<String, byte[]> snapshot() {
            Map<String, byte[]> result = new TreeMap<>();
            generated.forEach((name, file) ->
                    result.put(name, file.toByteArray()));
            return result;
        }
    }

    private static final class MemoryLoader extends ClassLoader {
        private final Map<String, byte[]> classBytes = new HashMap<>();

        MemoryLoader(ClassLoader parent, Map<String, byte[]> source) {
            super(parent);
            source.forEach((name, bytes) ->
                    classBytes.put(name, bytes.clone()));
        }

        @Override
        protected Class<?> findClass(String binaryName)
                throws ClassNotFoundException {
            byte[] bytes = classBytes.get(binaryName);
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
                    "Runtime lacks a system Java compiler");
        }

        String name = "sample.generated.Greeter";
        String code = """
                package sample.generated;
                public class Greeter {
                    public static String hello(String name) {
                        return "Hello, " + Helper.upper(name);
                    }
                    private static class Helper {
                        static String upper(String name) {
                            return name.toUpperCase(java.util.Locale.ROOT);
                        }
                    }
                }
                """;

        Map<String, byte[]> compiled;
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();
        try (MemoryFiles files = new MemoryFiles(
                compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT, StandardCharsets.UTF_8))) {
            Boolean ok = compiler.getTask(
                    null, files, diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null, List.of(new Source(name, code))
            ).call();

            System.out.println(
                    "Compilation successful: " + Boolean.TRUE.equals(ok));
            if (!Boolean.TRUE.equals(ok)) {
                for (Diagnostic<? extends JavaFileObject> d
                        : diagnostics.getDiagnostics()) {
                    System.err.println(d.getKind() + ": "
                            + d.getMessage(Locale.ROOT));
                }
                return;
            }
            compiled = files.snapshot();
        }

        System.out.println("Captured classes: " + compiled.keySet());
        MemoryLoader first = new MemoryLoader(
                MemoryCompilerLoaderDemo.class.getClassLoader(), compiled);
        Class<?> greeter = first.loadClass(name);
        System.out.println("Loaded by memory loader: "
                + (greeter.getClassLoader() == first));
        System.out.println("Invocation: "
                + greeter.getMethod("hello", String.class)
                         .invoke(null, "Java"));

        MemoryLoader second = new MemoryLoader(
                MemoryCompilerLoaderDemo.class.getClassLoader(), compiled);
        System.out.println("Distinct class identities: "
                + (greeter != second.loadClass(name)));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên trong thư mục chứa file:

~~~sh
javac --release 17 MemoryCompilerLoaderDemo.java
java MemoryCompilerLoaderDemo
~~~

**Kết quả chính xác** (đã biên dịch và chạy trên JDK 24):

~~~text
Compilation successful: true
Captured classes: [sample.generated.Greeter, sample.generated.Greeter$Helper]
Loaded by memory loader: true
Invocation: Hello, JAVA
Distinct class identities: true
~~~

Đầu ra đã được sắp xếp ổn định nhờ `TreeMap`, không phụ thuộc thứ tự compiler phát ra từng class. Chương trình không chủ động ghi `Greeter.class` hay `Greeter$Helper.class` ra đĩa: hai output `Kind.CLASS` đi vào `ByteArrayOutputStream`. Compiler vẫn có thể **đọc** JDK và dependency ở môi trường thực tế qua standard file manager; đây là ví dụ **class output trong bộ nhớ**, không phải cam kết “toàn bộ hệ thống biên dịch không bao giờ truy cập filesystem”.

## 5. Phân tích từng mắt xích của ví dụ

### 5.1. Source trong RAM: `SimpleJavaFileObject` loại `SOURCE`

`new Source(name, code)` tạo file ảo với URI như `string:///sample/generated/Greeter.java`. Nó khai báo `Kind.SOURCE` và override `getCharContent(...)` trả về nội dung Java từ một `String`. Nhờ thế compiler có thể phân tích source mà không cần có `Greeter.java` trên ổ đĩa.

URI có tên và đuôi hợp lệ giúp compiler xác định đơn vị biên dịch; source phải khai báo đúng package và tên lớp public. Khi cần biên dịch nhiều nguồn, truyền `Iterable<? extends JavaFileObject>` chứa nhiều đối tượng `Source` cho `getTask(...)`.

### 5.2. Output trong RAM: compiler gọi `getJavaFileForOutput`

Trong biên dịch bình thường, standard file manager ghi `.class` vào output location. `MemoryFiles` kế thừa `ForwardingJavaFileManager` nên vẫn dùng cơ chế chuẩn để đọc dependency, nhưng override:

~~~java
@Override
public JavaFileObject getJavaFileForOutput(
        JavaFileManager.Location location, String className,
        JavaFileObject.Kind kind, FileObject sibling) throws IOException {
    if (kind != JavaFileObject.Kind.CLASS) {
        return super.getJavaFileForOutput(
                location, className, kind, sibling);
    }
    Bytecode output = new Bytecode(className, kind);
    generated.put(className, output);
    return output;
}
~~~

Đây là **trích đoạn từ `MemoryFiles` trong chương trình đầy đủ**, không phải một lớp Java độc lập. Compiler cung cấp `className` riêng cho từng output. Khi compiler mở stream bằng `output.openOutputStream()`, những byte `.class` được ghi vào bộ đệm RAM; sau khi `CompilationTask.call()` thành công mới lấy snapshot.

**Vì sao giữ một map thay vì một mảng byte duy nhất?** Một source có thể sinh nhiều `.class`. Ví dụ `Greeter` và nested `Helper` tạo hai entry. Nếu bỏ entry của `Helper`, việc gọi `Greeter.hello(...)` có thể thất bại lúc JVM cần resolve `Greeter$Helper`, dù nạp `Greeter` đã thành công.

Ví dụ chỉ chuyển `Kind.CLASS` vào RAM. Các loại output khác, annotation processing hoặc resource được ghi bởi compiler cần chính sách riêng; `-proc:none` tắt annotation processing trong bản demo. Không nên coi override này là implementation đầy đủ của một hệ thống compiler hoàn toàn không sử dụng filesystem.

### 5.3. Snapshot bytecode và đóng file manager

`snapshot()` trả `Map<String, byte[]>` đã chứa các byte được sao chép từ từng `ByteArrayOutputStream`. Sau `call() == true`, ví dụ lấy snapshot **trước khi đóng file manager**:

~~~java
compiled = files.snapshot();
~~~

`MemoryFiles` kế thừa `Closeable` qua `JavaFileManager`. `try-with-resources` gọi `close()` của `ForwardingJavaFileManager`, chuyển tiếp xuống `StandardJavaFileManager` đang được bọc. Đóng file manager giải phóng tài nguyên biên dịch; nó **không xóa** bản sao `Map<String,byte[]>` đã được giữ ngoài khối `try`.

Khi có lỗi biên dịch, mã không lấy snapshot để nạp class có thể bị tạo một phần. Một hệ thống production nên chỉ “công bố” bytecode của batch sau khi mọi task cần thiết thành công và qua bước kiểm tra đầu ra.

### 5.4. `ClassLoader.findClass` và `defineClass`

`MemoryLoader` chỉ override `findClass(String)`. Khi ứng dụng gọi `first.loadClass(name)`, `ClassLoader.loadClass` mặc định:

1. Kiểm tra lớp cùng tên đã được loader này nạp hay chưa.
2. Đề nghị parent loader nạp trước.
3. Nếu parent không tìm được, gọi `findClass` của loader hiện tại.

Trong `findClass`, chương trình lấy `byte[]` bằng **binary name** và gọi:

~~~java
return defineClass(binaryName, bytes, 0, bytes.length);
~~~

Đây là **một câu lệnh bên trong override `findClass`** ở chương trình hoàn chỉnh. `defineClass` thực hiện định nghĩa lớp và áp dụng kiểm tra định dạng/định danh JVM. Mã nguồn sinh ra theo package `sample.generated`; tên tham số và bytes phải nhất quán. Bytecode sai định dạng hoặc không khớp có thể dẫn tới `ClassFormatError`, `NoClassDefFoundError` hoặc những lỗi liên kết khác thay vì trả về `Class<?>` như mong đợi.

Việc dùng `super(parent)` với class loader đã nạp ứng dụng giúp lớp sinh ra nhìn thấy các thư viện cần thiết thông qua parent (nếu được parent cho phép), đồng thời giữ **parent-first delegation** mặc định. Không override `loadClass(...)` để bỏ qua parent-first chỉ vì muốn lấy bytecode của mình trước: điều đó dễ gây xung đột lớp lõi và lớp API dùng chung.

### 5.5. Khi nào class được thực thi?

`first.loadClass(name)` trả về một `Class<?>`. Trong ví dụ, kiểm tra `greeter.getClassLoader() == first` trả `true` vì tên `sample.generated.Greeter` không tồn tại trong parent. Việc gọi:

~~~java
greeter.getMethod("hello", String.class).invoke(null, "Java");
~~~

lấy public static method và invoke với receiver `null`. Khi phương thức chạy, JVM cần đến nested `Helper`; nó yêu cầu loader đã định nghĩa `Greeter` giải quyết `sample.generated.Greeter$Helper`. Vì bytecode của helper cũng nằm trong map nên việc liên kết và thực thi thành công, trả `Hello, JAVA`.

`loadClass` mặc định không buộc **khởi tạo lớp** ngay; việc sử dụng chủ động như gọi static method có thể kích hoạt khởi tạo theo quy tắc JVM. Không dùng việc “biên dịch thành công” như bằng chứng mọi tham chiếu động đều resolve được: lỗi dependency có thể chỉ xuất hiện khi lớp/method thực sự được dùng.

## 6. Chọn ClassLoader nào là “thích hợp”?

| Tình huống | Cách nạp phù hợp | Vì sao |
| --- | --- | --- |
| Có `byte[]` từ JavaCompiler và muốn định nghĩa class bình thường | Custom `ClassLoader` với `findClass`/`defineClass(String, byte[], ...)` | Dùng trực tiếp bytes trong RAM, quản lý parent và lifecycle |
| Đã đóng gói output thành JAR hoặc thư mục chứa `.class` | `URLClassLoader` (nếu phù hợp môi trường classpath) hoặc cơ chế nạp module | URLClassLoader đọc từ URL/JAR; không nhận một `byte[]` trần như constructor |
| Tạo class trong **cùng runtime package và cùng loader** của một lớp đang có | `MethodHandles.Lookup.defineClass(byte[])` khi có lookup với quyền `PACKAGE` phù hợp | Không cần tạo custom loader; có ràng buộc cùng package/loader |
| Tạo helper implementation không cần truy cập qua tên nhị phân thông thường | `MethodHandles.Lookup.defineHiddenClass(...)` với lookup hợp lệ | Hidden class có cơ chế định danh/vòng đời riêng, không dùng như plugin public thông thường |
| Plugin vận hành như **named module** trong JPMS | Thiết kế module path, resolver và `ModuleLayer`/loader tương ứng | Custom `defineClass` đơn thuần không tự đăng ký lớp thành named module |

**Ví dụ này dùng custom `ClassLoader` vì có nhiều output class trong RAM, các class tham chiếu lẫn nhau và cần nạp bằng binary name thông thường.** Hai API `Lookup` là các lựa chọn hiện hành nhưng có ràng buộc cụ thể; không thay thế tuỳ ý cho class loader của plugin framework.

Nếu cần một hợp đồng plugin mạnh hơn reflection, các class được sinh có thể implements một interface do ứng dụng định nghĩa, ví dụ `GreetingPlugin`. **Interface đó nên được parent loader nạp một lần và chia sẻ cho cả host lẫn plugin**; sau đó host có thể dùng `asSubclass(...)` hoặc kiểm tra `instanceof` và cast. Nếu tạo một bản sao interface cùng binary name trong child loader thì chúng có **danh tính kiểu khác nhau**, dễ gây `ClassCastException`.

## 7. Danh tính lớp, xung đột tên và nạp lại phiên bản mới

JVM không định danh class chỉ bằng tên. Về bản chất, **binary name cùng defining class loader** xác định danh tính runtime của lớp. Trong ví dụ:

- `first.loadClass("sample.generated.Greeter")` trả một `Class<?>` do `first` định nghĩa.
- `second.loadClass("sample.generated.Greeter")` trả một `Class<?>` khác, dù hai loader cùng nhận các byte giống nhau.
- Vì vậy `greeter != second.loadClass(name)` trả `true`.

Hệ quả quan trọng:

1. **Một loader không dùng để “định nghĩa lại” cùng một class tùy ý.** Nếu binary name đã được loader đó định nghĩa, gọi `defineClass` lần nữa cho cùng tên trong cùng loader dẫn tới lỗi liên kết như `LinkageError`. Muốn nạp một phiên bản mới, thường tạo **loader mới** với tập bytes mới, rồi chuyển tham chiếu sử dụng sang phiên bản ấy.
2. **Parent-first có thể che phiên bản trong RAM.** Nếu parent đã có `sample.generated.Greeter`, `first.loadClass(name)` có thể trả class của parent và không gọi `MemoryLoader.findClass`. Cần dùng namespace dành riêng cho mã sinh, thiết kế parent rõ ràng và kiểm tra `result.getClassLoader()` khi quan trọng.
3. **Hai loader có lớp cùng tên vẫn không trao đổi đối tượng trực tiếp như cùng kiểu.** Không cast một object của lớp định nghĩa bởi loader A sang bản cùng tên định nghĩa bởi loader B. Dùng API/DTO thuộc một parent loader chung để trao đổi.
4. **Không có `ClassLoader.unloadClass(...)`.** JVM chỉ có thể thu hồi class khi các điều kiện reachability và class unloading được đáp ứng. Những tham chiếu sống đến `Class<?>`, instance, loader, thread, static cache hoặc resource có thể giữ phiên bản cũ ở lại. Hệ thống tạo nhiều phiên bản cần quản lý lifecycle/caching chặt chẽ.

Nếu nhiệm vụ chỉ là **nạp bytecode được sinh thêm** vào một phạm vi ổn định, custom loader độc lập là đơn giản. Nếu phải hỗ trợ hot reload lâu dài, hãy coi mỗi bộ phiên bản là một generation, có cơ chế chuyển tiếp và giải phóng tham chiếu rõ ràng.

## 8. Phân biệt lỗi biên dịch, lỗi nạp và lỗi thực thi

| Giai đoạn | Dấu hiệu thường gặp | Cách xử lý |
| --- | --- | --- |
| **Không có compiler** | `ToolProvider.getSystemJavaCompiler() == null` | Kiểm tra runtime có `jdk.compiler`; không cố dùng `getTask` trên `null` |
| **Compiler báo lỗi source** | `CompilationTask.call()` trả `false` | Đọc `DiagnosticCollector`: syntax, package, type, classpath/module path, option |
| **Thiếu bytecode của một class** | `ClassNotFoundException` khi `findClass` không tìm thấy tên | Kiểm tra map có đủ class chính, nested/anonymous và generated dependency |
| **Bytecode không hợp lệ hoặc JVM không hỗ trợ version** | `ClassFormatError`, `UnsupportedClassVersionError` | Kiểm tra bytes, binary name, target bytecode với `--release` |
| **Thiếu dependency khi link/resolve** | `NoClassDefFoundError`, các `LinkageError` phù hợp | Bảo đảm parent loader/loader bytecode biết dependency thực tế |
| **Không gọi được method/constructor** | `NoSuchMethodException`, `IllegalAccessException` | Kiểm tra chữ ký, visibility, package/module access |
| **Mã được gọi ném exception** | `InvocationTargetException` bọc lỗi từ method được gọi | Tách lỗi bên trong mã plugin khỏi lỗi reflection; đọc `getCause()` |

**Compiler success là điều kiện cần, chưa đủ**: source có thể tham chiếu dependency tồn tại trong compile classpath nhưng không có trong class loader ở runtime. `ClassLoader` cũng không tự biết các source hoặc class file chỉ xuất hiện trong bộ nhớ nếu chưa được đưa vào bản đồ nạp.

Khi có nhiều source, đặc biệt có phụ thuộc chéo, hãy xem kết quả compilation như **một batch**. Không nên lặng lẽ dùng class file cũ còn trong cache khi task mới biên dịch thất bại.

## 9. Classpath, module và quyền truy cập

Ví dụ chỉ dùng `java.base` trong source được biên dịch nên không cần thêm thư viện ngoài. Trong hệ thống thực:

- Nếu source sử dụng dependency ngoài, hãy cấu hình `--class-path` hoặc `--module-path` / file manager location tương ứng cho **compiler**.
- Khi nạp bytes, **parent loader** hoặc cơ chế loader/module layer của ứng dụng cũng cần nhìn thấy dependency ấy. Compile classpath và runtime visibility là hai vấn đề khác nhau.
- Custom `ClassLoader.defineClass` thông thường đưa lớp vào **unnamed module của loader tương ứng**. Nó không biến class vừa sinh thành thành viên của một named module chỉ vì source có package giống một named module.
- Các quy tắc Java về `public`, package-private, module exports/opens, readability và reflection vẫn áp dụng. Không dùng reflection với `setAccessible(true)` như một giải pháp chung để bỏ qua giới hạn module; thiết kế API public hoặc cơ chế truy cập đúng hợp đồng.
- Nếu source cần tài nguyên như `META-INF/services/...` hoặc `.properties`, việc cung cấp bytecode bằng `findClass` **chưa tự cung cấp tài nguyên**. Plugin loader cần triển khai thêm cơ chế resource phù hợp hoặc đóng gói thành JAR/module.

Khuyến nghị dùng binary name phân biệt rõ namespace của mã sinh và lớp host. Tên package có vẻ giống nhau nhưng được định nghĩa bằng hai class loader khác nhau cũng có thể không thuộc **cùng runtime package**, dẫn tới lỗi truy cập package-private.

## 10. Bảo mật: ClassLoader không phải sandbox

Một custom `ClassLoader` **không làm mã được biên dịch trở nên an toàn**. Nếu ứng dụng tự biên dịch/nạp và thực thi source chưa được tin cậy:

- Mã có thể tiêu tốn CPU, RAM, mở file/kết nối mạng hoặc gọi API mà tiến trình host có quyền truy cập.
- Compiler, annotation processor hoặc plugin có thể có side effect. `-proc:none` trong ví dụ chỉ tắt annotation processing; **không ngăn mã đã nạp thực thi thao tác nguy hiểm**.
- Kiểm tra source bằng regex, “chặn import” hoặc chỉ dùng parent delegation không phải ranh giới an toàn đủ mạnh.
- `defineClass` có một số kiểm tra tên/package/class format, nhưng **đó không phải chính sách cô lập quyền hạn của plugin**.
- Đối với mã không tin cậy, thực hiện biên dịch và thực thi ở **tiến trình/container cô lập** với giới hạn tài nguyên, filesystem, mạng, quyền và thời gian; giao tiếp với host qua giao thức/bộ dữ liệu đã được kiểm soát.

Nhiều ứng dụng nên biên dịch trước trong pipeline build/CI rồi chỉ tải artifact đã ký, kiểm tra và duyệt ở production. In-memory compilation phù hợp khi có nhu cầu động thực sự và có mô hình tin cậy rõ ràng.

## 11. Quản lý bộ nhớ và tài nguyên đúng vòng đời

`ByteArrayOutputStream` và bản sao `byte[]` chiếm RAM theo số lượng/độ lớn class; `MemoryFiles.generated` cũng giữ object output đến khi file manager không còn được tham chiếu. Trong ví dụ:

1. Sau `call() == true`, `snapshot()` sao chép bytes ra map độc lập.
2. `try-with-resources` đóng `MemoryFiles` và standard file manager nền.
3. `MemoryLoader` sao chép từng mảng byte lần nữa để không phụ thuộc việc caller sửa mảng đầu vào.
4. Khi không dùng loader/instance/class nữa, ứng dụng bỏ các tham chiếu; garbage collector có thể thu hồi theo điều kiện class unloading của JVM.

Trong sản xuất, nên giới hạn số class có thể tạo, tổng kích thước bytecode, thời gian biên dịch và số loader sống. Nếu pipeline tạo hàng nghìn class mỗi phút, rò rỉ `ClassLoader` hoặc cache giữ `Class<?>` có thể làm tăng class metadata/metaspace. Tránh giữ map bytecode và loader trong cache toàn cục vô hạn.

**Đóng compiler file manager không tương đương unload các lớp đã định nghĩa.** Đây là hai vòng đời khác nhau: file manager quản lý resource biên dịch; class loader/JVM quản lý kiểu runtime.

## 12. Lỗi thường gặp khi triển khai

1. **Chỉ override `getJavaFileForOutput` rồi gọi `Class.forName(...)` bằng loader mặc định:** loader mặc định không biết map bytes. Phải dùng đúng custom loader hoặc cơ chế class definition thích hợp.
2. **Chỉ lưu output class chính:** bỏ lớp nested `$Helper` hoặc các output phụ khiến code có thể lỗi khi liên kết/thực thi.
3. **Dùng tên path có dấu `/` cho `loadClass`:** `loadClass` yêu cầu binary name có dấu `.`, ví dụ `sample.generated.Greeter`; dấu `/` dùng trong đường dẫn file/URI.
4. **Định nghĩa lại cùng tên trong cùng loader:** `defineClass` không phải API thay thế class tùy ý. Tạo loader mới khi cần thế hệ class mới.
5. **Không kiểm tra `call()` và diagnostics:** có thể nhận snapshot chưa đủ sau compilation thất bại rồi báo lỗi loader khó hiểu.
6. **Không đóng file manager:** bộ đọc JAR/stream/cache của compiler có thể bị giữ lâu; dùng `try-with-resources`.
7. **Dùng loader không nhìn thấy dependency hoặc API host:** source compile được nhưng runtime không tìm thấy class, hoặc có hai định nghĩa interface cùng tên gây lỗi cast.
8. **Tưởng `loadClass` đồng nghĩa đã gọi phương thức:** biên dịch, định nghĩa class, khởi tạo và thực thi là các giai đoạn khác nhau.
9. **Tưởng có thể gắn class vào named module bằng `defineClass`:** JPMS cần module resolution/layer phù hợp.
10. **Tưởng class loader cô lập mã không tin cậy:** nó là cơ chế nạp/định danh kiểu, không phải sandbox bảo mật.

## 13. Bài tập kiểm tra

**Bài 1.** Source `Outer` có một nested class `Outer.Inner`; compiler tạo `Outer.class` và `Outer$Inner.class` nhưng bạn chỉ đưa `Outer.class` vào map loader. Điều gì có thể xảy ra?

**Đáp:** `Outer` có thể được nạp, nhưng khi JVM cần `Outer$Inner`, loader không tìm thấy bytecode và có thể phát sinh lỗi liên kết. Phải thu **tất cả `Kind.CLASS`** theo binary name do compiler báo.

**Bài 2.** Hai loader nhận cùng bytes `pkg.Task`. `loaderA.loadClass("pkg.Task") == loaderB.loadClass("pkg.Task")` luôn đúng?

**Đáp:** Không. Nếu mỗi loader **tự định nghĩa** một class cùng binary name, hai `Class<?>` khác nhau. Nếu cả hai cùng delegate tên đó về **cùng một class của parent**, kết quả có thể là cùng `Class<?>`. Cần kiểm tra loader thực sự định nghĩa class, không chỉ nhìn tên.

**Bài 3.** `compiler.getTask(...).call()` trả `true`. Có đủ bảo đảm `loader.loadClass(...)` và reflection luôn thành công?

**Đáp:** Không. Bytecode map, target runtime, dependency, quyền truy cập và signature của method vẫn phải đúng. Tách diagnostics compile khỏi lỗi loading/linking/invocation.

**Bài 4.** Có thể cho người dùng nhập source bất kỳ, compile in-memory rồi thực thi trên server nhờ custom loader mà không cần kiểm soát thêm?

**Đáp:** Không. Custom loader không giới hạn quyền thực thi. Mã chưa được tin cậy cần môi trường cô lập và giới hạn tài nguyên phù hợp.

**Ghi nhớ:** Dùng `JavaCompiler` cùng `JavaFileObject`/`ForwardingJavaFileManager` để **thu trọn bộ bytes `.class` theo binary name**; khi biên dịch thành công, dùng **ClassLoader có parent đúng và `findClass`/`defineClass(String,...)`** để định nghĩa và sử dụng lớp. Kiểm soát dependency, danh tính class, vòng đời loader và ranh giới bảo mật là điều kiện để giải pháp hoạt động ổn định.

### Tài liệu tham khảo — API hiện hành

- [Java SE 26 — `JavaCompiler`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaCompiler.html): compilation task, standard file manager và diagnostic.
- [Java SE 26 — `JavaFileManager`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/JavaFileManager.html): chuyển hướng output, quản lý Java file objects.
- [Java SE 26 — `ForwardingJavaFileManager`](https://docs.oracle.com/en/java/javase/26/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html): bọc và override file manager.
- [Java SE 26 — `ClassLoader`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ClassLoader.html): parent delegation, `findClass`, `defineClass` và danh tính loader.
- [Java SE 26 — `MethodHandles.Lookup`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): `defineClass` và `defineHiddenClass` theo lookup context.
