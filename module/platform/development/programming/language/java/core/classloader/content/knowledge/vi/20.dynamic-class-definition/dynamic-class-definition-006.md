# Sinh bytecode, biên dịch động và trách nhiệm quản lý ClassLoader trong Java

Java có thể tạo thêm class **khi chương trình đang chạy**, thay vì chỉ sử dụng những tệp `.class` được đóng gói từ trước. Một ứng dụng có thể sinh mã nguồn từ template rồi biên dịch bằng `javax.tools.JavaCompiler`, hoặc sinh trực tiếp bytecode qua thư viện chuyên dụng và đưa bytes vào JVM. Sau đó **ClassLoader** (hoặc cơ chế định nghĩa class phù hợp) làm nhiệm vụ chuyển định dạng class-file thành **runtime `Class<?>`**.

Các bước này giải quyết **ba việc khác nhau**:

1. **Sinh mã / sinh bytecode:** tạo dữ liệu biểu diễn class, thường là source `.java` hoặc `byte[]` class-file hợp lệ.
2. **Biên dịch / biến đổi:** dùng Java compiler, code generator hoặc bytecode transformer để tạo bytes đúng định dạng, đúng Java version, dependency và method signatures.
3. **Định nghĩa / nạp kiểu:** JVM cần một **defining loader** và thực hiện các kiểm tra tên, package, loading constraints, verification/linking, bảo mật tương ứng trước khi runtime class được sử dụng.

**Không có phép đồng nhất** giữa “tôi đã tạo được bytecode”, “class đã được JVM nạp” và “class đã được initialize/tạo instance”. Bài này giải thích luồng xử lý từ đầu tới cuối, những trách nhiệm không thể đẩy hết cho JavaCompiler hoặc JVM, đồng thời có chương trình Java 17+ **biên dịch source trong bộ nhớ, tự định nghĩa class, tạo object và so sánh hai thế hệ loader**.

## 1. Mô hình tổng quan

~~~text
                         Host application
                               |
                +--------------+--------------+
                |                             |
        Source generation               Bytecode generation
        String / .java                  ASM, Byte Buddy, v.v.
                |                             |
        JavaCompiler API                     byte[]
                |                             |
       class-file byte[]                     |
                +--------------+--------------+
                               |
                         Loader generation
                               |
                 findClass -> defineClass
                               |
                          JVM Class<?>
                     (tên, defining loader)
                               |
                   Linking / Initialization
                               |
                     Reflection / Interface
                               |
                         Object instance
~~~

Đây là **hai nhánh đầu vào khác nhau** để có bytes, nhưng đầu ra cuối cùng đều chịu các ràng buộc class loading của JVM. Nếu code generator đã tạo bytecode hợp lệ, không cần chạy `javac` lần nữa. Nếu mới tạo chuỗi source, cần một compiler phù hợp để có class-file bytes.

| Khái niệm | Dữ liệu/API | Điều không nên nhầm |
|---|---|---|
| Java source | `String`, `.java`, `JavaFileObject.Kind.SOURCE` | Chưa phải runtime class |
| Java compilation | `JavaCompiler.getTask(...).call()` | Trả kết quả biên dịch; không tự instantiate |
| Class-file bytes | `byte[]`, `JavaFileObject.Kind.CLASS` | Chưa bảo đảm đã verify/link/initialize |
| Custom loader | `ClassLoader.findClass` và `defineClass` | Định nghĩa kiểu theo loader identity |
| Runtime class | `Class<?>` | Là đại diện kiểu, không phải object của class |
| Instance | `Constructor.newInstance()` hoặc gọi `new` trong mã đã liên kết | Có hành vi constructor/initialization riêng |
| Reload thế hệ mới | **Loader instance mới** | Không thay class đang tồn tại trong loader cũ |

### Danh tính kiểu là câu hỏi nền tảng

Theo JVM, **runtime class/interface identity** gắn với:

~~~text
(binary name, defining class loader)
~~~

Ví dụ hai generation đều có `generated.Hello`:

~~~text
("generated.Hello", LoaderA) -> Class A
("generated.Hello", LoaderB) -> Class B

ClassA.getName().equals(ClassB.getName()) == true
ClassA == ClassB                       == false
~~~

Vì vậy một chương trình **không thể “ghi đè” cùng class name trong cùng loader** bằng cách gọi `defineClass` lần hai. Nếu có nhu cầu thêm phiên bản mới, thường tạo loader mới và chuyển traffic/reference theo vòng đời.

## 2. Cách 1: Sinh mã nguồn và biên dịch động bằng `javax.tools`

Package `javax.tools` thuộc module chuẩn **`java.compiler`**; nó có các interface hỗ trợ đưa nguồn vào, lấy output ra, thu thập lỗi và tùy biến nơi lưu file. Một JDK đầy đủ thường cung cấp compiler hệ thống qua:

~~~java
import javax.tools.JavaCompiler;
import javax.tools.ToolProvider;

JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("No system Java compiler");
}
~~~

Đây là đoạn minh họa, không phải chương trình độc lập. **`compiler == null` là tình huống phải xử lý**, ví dụ runtime image được tạo bằng `jlink` không chứa module/compiler provider cần thiết hoặc môi trường chỉ có runtime tối giản. Không mặc định bất kỳ JVM nào cũng có compiler để sinh source code lúc chạy.

### Các thành phần của pipeline

| API | Vai trò |
|---|---|
| `ToolProvider.getSystemJavaCompiler()` | Lấy trình biên dịch Java hệ thống nếu có |
| `JavaFileObject` | Biểu diễn đơn vị source hoặc class-file |
| `SimpleJavaFileObject` | Lớp tiện ích để triển khai file object trong memory |
| `StandardJavaFileManager` | Quản lý locations/classpath/output theo hợp đồng compiler |
| `ForwardingJavaFileManager` | Chặn hoặc chuyển hướng những lệnh file-manager tới implementation tùy chỉnh |
| `JavaFileManager.getJavaFileForOutput` | Quyết định nơi compiler ghi class-file output |
| `DiagnosticCollector<JavaFileObject>` | Thu thập lỗi/cảnh báo với vị trí source |
| `JavaCompiler.getTask(...).call()` | Chạy compilation task, trả `Boolean` thành công/thất bại |

**Quan trọng:** `JavaCompiler.getTask` tạo task, nhưng **`call()` mới thực hiện biên dịch**. Biên dịch thành công cũng chỉ cho thấy compiler tạo output hợp lệ theo compiler rules; khi JVM nạp, vẫn có thể phát hiện lỗi ở dependency/linkage/runtime.

### Source trong bộ nhớ

Thay vì tạo file `Hello.java` trên ổ đĩa, ta có thể dùng:

~~~java
final class StringSource extends SimpleJavaFileObject {
    private final String code;

    StringSource(String binaryName, String code) {
        super(URI.create("string:///"
                + binaryName.replace('.', '/')
                + Kind.SOURCE.extension), Kind.SOURCE);
        this.code = code;
    }

    @Override
    public CharSequence getCharContent(boolean ignoreEncodingErrors) {
        return code;
    }
}
~~~

Đây là **mảnh class minh họa**, cần import `java.net.URI` và `javax.tools.SimpleJavaFileObject`; không có `main`. URI dạng `string:///generated/Hello.java` giúp compiler thấy tên file hợp với `public class Hello` mà không cần file system path thật.

### Output `.class` trong bộ nhớ

Một cách tạo output riêng:

~~~java
final class BytesFile extends SimpleJavaFileObject {
    private final ByteArrayOutputStream buffer =
            new ByteArrayOutputStream();

    BytesFile(String binaryName, Kind kind) {
        super(URI.create("mem:///"
                + binaryName.replace('.', '/')
                + kind.extension), kind);
    }

    @Override
    public OutputStream openOutputStream() {
        return buffer;
    }

    byte[] snapshot() {
        return buffer.toByteArray();
    }
}
~~~

Đây là **mảnh minh họa** với imports `ByteArrayOutputStream`, `OutputStream`, `URI`, `SimpleJavaFileObject`. Compiler ghi bytes qua `openOutputStream()`; sau khi `call()` thành công, code lấy snapshot `buffer.toByteArray()`. Một nguồn có thể sinh **nhiều class files**, ví dụ inner class, local class hoặc class phụ; cần lưu output theo **binary class name**, không chỉ một `byte[]` duy nhất.

## 3. Cách 2: Sinh bytecode trực tiếp

Thư viện chuyên dụng (ví dụ ASM hoặc Byte Buddy) có thể tạo `byte[]` mang cấu trúc một class file mà không cần viết source rồi chạy `JavaCompiler`.

~~~text
DSL / metadata / schema
           |
           v
 bytecode generator
           |
           v
   JVM class-file bytes
           |
           v
 defineClass / Lookup.defineClass
           |
           v
        Class<?>
~~~

Điểm lợi:

- Tránh vòng source-text parse/compile khi generator chỉ cần cấu trúc bytecode cụ thể.
- Tạo proxy, adapter, accessor, framework-generated subclasses, instrumentation hoặc method bodies theo nhu cầu.
- Có thể thao tác cấu trúc JVM bytecode khó biểu đạt bằng Java source thông thường.

Điểm phải chịu trách nhiệm:

1. **Class-file format hợp lệ**, constant pool, stack-map frames, access flags, signatures, version hỗ trợ bởi JVM đích.
2. **Định danh và package** khớp tên binary, loader, package/module context.
3. **Bytecode verification và linkage**; có thể gặp `ClassFormatError`, `VerifyError` hoặc `LinkageError`.
4. **Source provenance**, integrity và giới hạn đầu vào; một generator không an toàn có thể tạo class sai hoặc cho phép thực thi mã không mong muốn.
5. **Caching và loader lifecycle**; không tạo vô hạn class độc nhất hoặc loader vô thời hạn.

Không nên tự ghép mảng byte bằng tay để tạo class-file phức tạp trong production khi có thư viện đã hiểu JVM specification; ví dụ sau dùng **JavaCompiler tích hợp**, không phụ thuộc thư viện bytecode ngoài.

### `ClassLoader.defineClass` và `MethodHandles.Lookup.defineClass`

Hai API có scope khác:

- `ClassLoader.defineClass(String, byte[], int, int)` là **protected final**. Mã ứng dụng không gọi tùy ý trên một ClassLoader bất kỳ; custom subclass thường expose gián tiếp qua `findClass`.
- `MethodHandles.Lookup.defineClass(byte[])` là cơ chế có từ Java 9, dùng **Lookup có đủ quyền** để định nghĩa class trong **cùng package và defining loader** với lookup class. Nó **không phải** API tạo bất kỳ class name/package/loader nào.
- `Lookup.defineHiddenClass(...)` hỗ trợ **hidden classes** cho một số cơ chế runtime/framework. Hidden class có đặc tính về discoverability/lifecycle riêng, không phải class tên thông thường để mọi caller tìm bằng `Class.forName(binaryName)`.

Chọn giải pháp theo mục tiêu: loader riêng cho **plugin/generation có thể unload**, hoặc `Lookup` khi sinh thêm kiểu trong package/loader của một host class có quyền phù hợp. Đừng chọn `Lookup` chỉ để né các ràng buộc classloader/package.

## 4. Giao ước của `defineClass`: tên, package và class loading

Custom loader có thể nhận map các class bytes:

~~~java
final class ByteArrayLoader extends ClassLoader {
    private final Map<String, byte[]> definitions;

    ByteArrayLoader(Map<String, byte[]> definitions,
                    ClassLoader parent) {
        super(parent);
        this.definitions = definitions;
    }

    @Override
    protected Class<?> findClass(String name)
            throws ClassNotFoundException {
        byte[] bytes = definitions.get(name);
        if (bytes == null) {
            throw new ClassNotFoundException(name);
        }
        return defineClass(name, bytes, 0, bytes.length);
    }
}
~~~

Đây là **khung API minh họa**, cần import `Map` và bổ sung chính sách snapshot/immutability nếu map/bytes có thể bị thread khác sửa. Trong ví dụ đầy đủ, ta thực hiện snapshot và sao chép bytes.

### Vì sao override `findClass` thay vì viết lại `loadClass`?

Implementation mặc định của `ClassLoader.loadClass`:

1. Dùng `getClassLoadingLock(name)` để điều phối các yêu cầu theo chính sách parallel-capable.
2. Kiểm tra `findLoadedClass(name)`.
3. Hỏi parent/bootstrapping trước.
4. Gọi `findClass(name)` khi parent không tìm ra class.
5. `resolveClass` khi được yêu cầu.

Nếu nhu cầu chỉ là đổi **nguồn tìm bytecode**, override `findClass` là điểm mở rộng hợp lý, kế thừa delegation và classloading lock chuẩn. Tự override `loadClass` mà không duy trì `findLoadedClass`/lock có thể khiến hai thread cùng `defineClass` một binary name, dẫn tới `LinkageError`.

### `defineClass` không đồng nghĩa initialization

~~~java
Class<?> type = loader.loadClass("generated.Hello");
Object object = type.getConstructor().newInstance();
~~~

Lời gọi thứ nhất yêu cầu loader tìm class, **không tự yêu cầu chạy static initializer**. Lời gọi reflection tiếp theo tạo instance và sẽ yêu cầu initialization theo quy tắc Java nếu kiểu chưa được khởi tạo.

Các API liên quan:

| API | Trạng thái mong đợi |
|---|---|
| `loader.loadClass(name)` | Yêu cầu load; không tự yêu cầu initialize |
| `Class.forName(name, false, loader)` | Tìm/nạp/liên kết nhưng không yêu cầu initialize |
| `Class.forName(name, true, loader)` | Tìm kiểu và yêu cầu initialize |
| `defineClass(...)` | Định nghĩa runtime class từ class-file bytes; không gọi constructor |
| `resolveClass(type)` | Yêu cầu liên kết (resolution); không có nghĩa tạo instance |
| `getConstructor().newInstance()` | Tạo instance và thực thi constructor |

**Một binary class name chỉ được định nghĩa một lần trong cùng defining loader**. Nếu cố gọi `defineClass` lại với cùng tên trong cùng loader, việc định nghĩa trùng không hợp lệ. Muốn đổi bytecode sau deployment, tạo **generation loader mới** hoặc sử dụng instrumentation/redefinition có những giới hạn riêng.

### Tên binary khớp class-file thực

`defineClass("generated.Hello", bytes, ...)` đòi class-file bytes thực sự mô tả đúng tên ấy. Sai tên có thể gây `NoClassDefFoundError` hoặc lỗi class format/linkage tương ứng.

Không tự tạo class bằng prefix `java.` từ custom loader: JDK có ràng buộc đặc biệt với package nền tảng, có thể ném `SecurityException`. Ngoài ra, nếu các class trong một package dùng package-private access, các class ấy phải ở đúng **runtime package**, vốn phụ thuộc **package name + defining loader**.

## 5. Ví dụ đầy đủ Java 17+: biên dịch trong RAM, nạp hai phiên bản

Chương trình **`DynamicCompilationDemo.java`** dưới đây:

1. Tạo chuỗi source cho class `generated.Hello` với hai bản `dynamic-v1` và `dynamic-v2`.
2. Gọi `ToolProvider.getSystemJavaCompiler()` và `JavaCompiler.getTask(...)` để sinh class bytes.
3. Sử dụng `SimpleJavaFileObject` và `ForwardingJavaFileManager` để **không ghi file `.class` động ra đĩa**.
4. Tạo **hai custom ClassLoader instances**, mỗi loader giữ bytecode của một version.
5. Dùng reflection tạo object, gọi method và kiểm tra class identity, defining loader.
6. Chứng minh cùng binary name nhưng khác loader tạo **hai runtime types khác nhau**; trong cùng loader, gọi `loadClass` lần hai nhận lại cùng `Class<?>`.

### 5.1. File `DynamicCompilationDemo.java`

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

public final class DynamicCompilationDemo {

    private static final String CLASS_NAME = "generated.Hello";

    // 1. Source nằm trong bộ nhớ.
    static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source(String binaryName, String code) {
            super(URI.create("string:///"
                    + binaryName.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    // 2. File output .class nằm trong bộ nhớ.
    static final class Bytecode extends SimpleJavaFileObject {
        private final ByteArrayOutputStream buffer =
                new ByteArrayOutputStream();

        Bytecode(String binaryName, Kind kind) {
            super(URI.create("mem:///"
                    + binaryName.replace('.', '/')
                    + kind.extension), kind);
        }

        @Override
        public OutputStream openOutputStream() {
            return buffer;
        }

        byte[] snapshot() {
            return buffer.toByteArray();
        }
    }

    // 3. Compiler ghi class files vào một map thay vì ra đĩa.
    static final class MemoryFiles
            extends ForwardingJavaFileManager<StandardJavaFileManager> {

        private final Map<String, Bytecode> outputs =
                new LinkedHashMap<>();

        MemoryFiles(StandardJavaFileManager standard) {
            super(standard);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location,
                String className,
                JavaFileObject.Kind kind,
                FileObject sibling) {
            Bytecode output = new Bytecode(className, kind);
            outputs.put(className, output);
            return output;
        }

        Map<String, byte[]> snapshot() {
            Map<String, byte[]> result = new HashMap<>();
            for (var entry : outputs.entrySet()) {
                result.put(entry.getKey(), entry.getValue().snapshot());
            }
            return result;
        }
    }

    // 4. Loader tự định nghĩa những class có bytes trong map.
    static final class MemoryLoader extends ClassLoader {
        private final Map<String, byte[]> definitions = new HashMap<>();

        MemoryLoader(Map<String, byte[]> bytes, ClassLoader parent) {
            super(parent);
            bytes.forEach((name, data) ->
                    definitions.put(name, data.clone()));
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            byte[] data = definitions.get(name);
            if (data == null) {
                throw new ClassNotFoundException(name);
            }
            return defineClass(name, data, 0, data.length);
        }
    }

    private static String sourceFor(String label) {
        return "package generated;\n"
                + "public final class Hello {\n"
                + "  public String message() {\n"
                + "    return \"" + label + "\";\n"
                + "  }\n"
                + "}\n";
    }

    private static Map<String, byte[]> compile(
            JavaCompiler compiler, String code) throws IOException {

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        try (StandardJavaFileManager standard =
                compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT, StandardCharsets.UTF_8)) {

            MemoryFiles files = new MemoryFiles(standard);
            JavaFileObject source = new Source(CLASS_NAME, code);

            Boolean success = compiler.getTask(
                    null,
                    files,
                    diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null,
                    List.of(source)
            ).call();

            if (!Boolean.TRUE.equals(success)) {
                for (Diagnostic<? extends JavaFileObject> d
                        : diagnostics.getDiagnostics()) {
                    System.err.println(
                            d.getKind() + " at line "
                            + d.getLineNumber() + ": " + d.getMessage(
                                    Locale.ROOT));
                }
                throw new IllegalStateException("Compilation failed");
            }

            return files.snapshot();
        }
    }

    private static String message(Class<?> type) throws Exception {
        Object instance = type.getConstructor().newInstance();
        return (String) type.getMethod("message").invoke(instance);
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "A full JDK compiler is required");
        }

        Map<String, byte[]> v1 =
                compile(compiler, sourceFor("dynamic-v1"));
        Map<String, byte[]> v2 =
                compile(compiler, sourceFor("dynamic-v2"));

        ClassLoader parent = DynamicCompilationDemo.class.getClassLoader();

        MemoryLoader loader1 = new MemoryLoader(v1, parent);
        MemoryLoader loader2 = new MemoryLoader(v2, parent);

        Class<?> first = loader1.loadClass(CLASS_NAME);
        Class<?> second = loader2.loadClass(CLASS_NAME);

        System.out.println("compiler available: true");
        System.out.println("v1: " + message(first));
        System.out.println("v2: " + message(second));
        System.out.println("same binary name: "
                + first.getName().equals(second.getName()));
        System.out.println("same runtime type: " + (first == second));
        System.out.println("v1 defined by loader1: "
                + (first.getClassLoader() == loader1));
        System.out.println("v2 defined by loader2: "
                + (second.getClassLoader() == loader2));
        System.out.println("repeat load same class: "
                + (loader1.loadClass(CLASS_NAME) == first));
        System.out.println("generated in unnamed module: "
                + !first.getModule().isNamed());
    }
}
~~~

### 5.2. Biên dịch và chạy

Lưu file với tên **`DynamicCompilationDemo.java`** trong thư mục riêng. Dùng JDK 17+:

~~~bash
javac -encoding UTF-8 DynamicCompilationDemo.java
java DynamicCompilationDemo
~~~

Lệnh `javac` ban đầu biên dịch **host utility**; còn class `generated.Hello` được biên dịch bằng **JavaCompiler bên trong ứng dụng**, từ chuỗi source lúc runtime. Không có bước `javac generated/Hello.java` và cũng không cần ghi file `generated/Hello.class` ra đĩa.

**Stdout dự kiến khi chạy trên JDK đầy đủ có JavaCompiler:**

~~~text
compiler available: true
v1: dynamic-v1
v2: dynamic-v2
same binary name: true
same runtime type: false
v1 defined by loader1: true
v2 defined by loader2: true
repeat load same class: true
generated in unnamed module: true
~~~

### 5.3. Vì sao kết quả như vậy?

- Cả hai compilation tasks nhận source tên `generated.Hello`, nhưng source method `message()` khác nhau.
- `JavaCompiler` sinh bytes vào các `Bytecode` objects do `MemoryFiles.getJavaFileForOutput` cung cấp; các maps v1/v2 không chia sẻ class objects.
- `MemoryLoader.findClass` nhận bytes từ map và gọi `defineClass`. Vì app loader không có `generated.Hello` trên classpath của ví dụ, parent-first delegation không che class cần định nghĩa.
- `first.getClassLoader() == loader1` và `second.getClassLoader() == loader2` là `true`: hai defining loaders khác nhau.
- `first.getName().equals(second.getName())` là `true` nhưng `first == second` là `false`, thể hiện type identity.
- Trong **cùng loader1**, lời gọi `loadClass(CLASS_NAME)` tiếp theo tìm class đã nạp và trả lại object `Class<?>` cũ; không gọi `defineClass` lần hai.
- Cả hai generated classes thuộc **unnamed module của defining loaders** khi định nghĩa bằng cơ chế ClassLoader thường. Một map bytes tự tạo không tự resolve thành named module JPMS.
- `message(first)` dùng constructor và public method qua reflection. Cách này cần class được định nghĩa thành công và có access phù hợp; trong ví dụ generated class/method là `public`.

### 5.4. Phân tích vai trò của các class helper

**`Source`** không tạo file trên hệ thống: `URI` chỉ cung cấp tên giả tương thích compiler. `getCharContent` là source thực tế.

**`Bytecode`** nhận dữ liệu compiler ghi qua `openOutputStream`. Snapshot tạo một byte[] độc lập từ output stream sau khi biên dịch xong.

**`MemoryFiles`** kế thừa `ForwardingJavaFileManager` để giữ phần lớn logic input/classpath của standard file manager nhưng chuyển hướng **class outputs** sang bộ nhớ. Nó lưu theo tên class, cho phép compiler sinh nhiều output khác nhau nếu nguồn chứa lớp con/anonymous classes.

**`MemoryLoader`** không biết cách tự biên dịch; nó chỉ định nghĩa bytes đã tạo. Bản sao `data.clone()` giảm nguy cơ mã bên ngoài mutate dữ liệu sau khi loader đã nhận.

**`compile(...)`** tạo diagnostics/file manager **mới cho mỗi lần biên dịch**, rồi đóng standard file manager qua try-with-resources. Không chia sẻ file manager giữa nhiều compilation tasks đồng thời nếu chưa có thiết kế synchronization rõ ràng.

**`--release 17`** yêu cầu compiler sinh bytecode/API phù hợp Java 17 dù chương trình chạy trên JDK mới hơn (nếu JDK đó hỗ trợ target 17). **`-proc:none`** tắt annotation processing trong demo để giảm phụ thuộc vào processors tình cờ có trên classpath.

### 5.5. Những giới hạn có chủ ý của ví dụ

1. Mỗi lần compile chỉ có một Java source với class binary name `generated.Hello`. Production có thể cần nhiều nguồn và output files.
2. Source được sinh từ **nhãn có kiểm soát**. Đừng ghép source tùy ý từ dữ liệu người dùng rồi coi kết quả là an toàn.
3. Parent là application loader; nếu class `generated.Hello` đã có ở parent, parent-first sẽ thắng. Muốn cách ly tên trùng, cần namespace riêng hoặc loader policy phù hợp.
4. `MemoryLoader` giữ các byte[] trong map trong suốt vòng đời để ví dụ đơn giản. Production có thể evict bytes sau khi định nghĩa nếu không cần cache.
5. `MemoryLoader` không triển khai `Closeable` vì không mở URL/JAR handles. Nó cũng không có method `unload()`; thời điểm class unloading do JVM/GC quyết định.
6. Không cung cấp resource names `getResource`/`getResourceAsStream` từ memory map. Đây là cache **class-file bytes**, không phải cơ chế resource lookup tổng quát.
7. Chỉ in kết quả chính từ `main`; khi input/compiler lỗi, diagnostic message và exception sẽ phụ thuộc lỗi cụ thể và không thuộc stdout chuẩn trên.

## 6. Biên dịch source phụ thuộc API của host

Ví dụ `generated.Hello` vừa rồi chỉ dùng `String` và các API từ `java.base`. Plugin thực tế thường implement một **shared interface** từ host, ví dụ:

~~~java
package api;

public interface Greeting {
    String message();
}
~~~

Nếu source generated dùng:

~~~java
package generated;

public final class Hello implements api.Greeting {
    @Override
    public String message() {
        return "hello";
    }
}
~~~

Đây là **hai tệp Java minh họa** cho API và implementation, không phải tệp thay thế tự động cho demo độc lập ở phần 5.

### Compile-time classpath khác runtime defining loader

Khi dùng `JavaCompiler`, compiler phải nhìn thấy `api.Greeting` trong input classpath/module path:

~~~java
List<String> options = List.of(
        "--release", "17",
        "-proc:none",
        "-classpath", System.getProperty("java.class.path")
);
~~~

Đây là **mảnh minh họa tùy cấu hình**; giả định API đã có trên classpath ứng dụng và property tương ứng được thiết lập. Với ứng dụng named-module hoặc custom plugin layers, phải thiết kế **module path, classpath và file manager** phù hợp; không coi `java.class.path` là đại diện mọi thứ mà JVM đã nạp bằng custom loaders.

Sau biên dịch, loader định nghĩa generated class cũng phải **nhìn đúng `api.Greeting` runtime** từ parent:

~~~text
Application loader
  defines api.Greeting
          |
          v
MemoryLoader (parent = application loader)
  defines generated.Hello
  generated.Hello implements api.Greeting from parent
~~~

Nếu custom loader tự định nghĩa một bản `api.Greeting` khác bytecode nhưng cùng tên, JVM coi đó là **interface khác**, và cast từ generated object về `api.Greeting` phía host có thể thất bại. Không đủ để hai lớp API có cùng source/bytecode; chúng phải chia sẻ **defining loader identity**.

### Ranh giới khi compile với dependency riêng

Một plugin có thể compile dựa vào thư viện v2 nhưng runtime parent-first lại nạp v1. Nếu method chữ ký không tồn tại ở v1, có thể gặp `NoSuchMethodError` khi liên kết/gọi. Vì vậy:

- Chọn compile classpath/module path **phù hợp** với dependency generation sẽ dùng khi chạy.
- Đặt shared APIs ở parent.
- Cô lập private dependencies đúng namespace nếu cần version khác.
- Đừng cho private dependency types rò rỉ vào public signatures qua boundary.
- Kiểm tra code generation dưới nhiều runtime configurations, không chỉ “compile succeeded”.

## 7. Biên dịch động với file trên đĩa khác gì trong RAM?

Một cách đơn giản để thử biên dịch động là ghi source ra thư mục tạm rồi gọi compiler:

~~~text
generated-src/generated/Hello.java
             |
          javac
             |
          generated-out/generated/Hello.class
             |
       URLClassLoader
             |
        generated.Hello
~~~

Cách này dễ debug: mở được `.java`, `.class` và phân tích bằng `javap`. Nhưng nó tạo file tạm, cần dọn dẹp an toàn, giới hạn quyền truy cập và quản lý URLClassLoader/file handles.

Dùng bộ nhớ:

~~~text
String source
     |
JavaCompiler / JavaFileObject
     |
byte[] map
     |
MemoryLoader
     |
Class<?> / object
~~~

Giảm nhu cầu I/O trung gian và thuận tiện cho runtime template/generation. Đổi lại, việc debug stack trace/class-file metadata và resource lookup cần được thiết kế rõ.

| Tiêu chí | Disk output + URLClassLoader | In-memory JavaFileObject + MemoryLoader |
|---|---|---|
| Xem class files khi debug | Dễ hơn | Phải chủ động xuất bytes/log |
| Cần tệp tạm | Có | Không cho generated output |
| Resource/JAR integration | URLClassLoader có sẵn cơ chế URL | Phải triển khai riêng nếu cần |
| Cleanup | File/JAR handles, temp directory, stream | Map bytes và references/lifecycle |
| Loader ownership | URLClassLoader instance | MemoryLoader instance |
| Bytecode verification | JVM vẫn thực hiện | JVM vẫn thực hiện |
| Reload class cùng binary name | Thường loader generation mới | Loader generation mới |
| Support compiler diagnostics | Compiler API | Compiler API |

**Không phải** “in-memory luôn an toàn và nhanh hơn”. Source templates phức tạp, số lượng class lớn, annotation processors hoặc constant pools lớn đều có chi phí biên dịch/caching/metaspace đáng kể.

## 8. Lỗi biên dịch: đừng chuyển mọi thứ thành `ClassNotFoundException`

Nếu `getTask(...).call()` trả `false`, đây trước hết là **compilation failure**, ví dụ syntax error, missing imported type, incompatible method signature hoặc unsupported option.

`DiagnosticCollector` có thể cung cấp:

~~~java
for (Diagnostic<? extends JavaFileObject> d
        : diagnostics.getDiagnostics()) {
    System.out.println(d.getKind());
    System.out.println(d.getLineNumber());
    System.out.println(d.getColumnNumber());
    System.out.println(d.getMessage(Locale.ROOT));
}
~~~

Đây là **mảnh code minh họa**, không phải ví dụ chạy độc lập; cần biến `diagnostics` và imports thích hợp.

Nên giữ các thông tin:

- Generated source identifier, ví dụ `string:///generated/Hello.java`.
- Compiler options và target `--release`.
- Compilation diagnostics (kind, line/column, message) có giới hạn độ dài.
- Artifact/template version và dependency classpath/module path.
- Số lượng class files đã sinh và hash của bytes.
- Không đưa source code chứa secrets hoặc dữ liệu người dùng nhạy cảm vào log công khai.

**Phân biệt lỗi theo giai đoạn:**

| Giai đoạn | Ví dụ lỗi | Hướng điều tra |
|---|---|---|
| Sinh source | Template tạo dấu ngoặc sai | Log template/generator version và source an toàn |
| Biên dịch | `error: cannot find symbol` | Compile classpath/module path và source |
| Xuất class-file | `IOException` từ file manager | OutputStream/location/capacity/lifecycle |
| Nạp class | `ClassNotFoundException` | Bytes map, tên binary, parent delegation |
| Định nghĩa class | `ClassFormatError` | Class-file bytes không hợp lệ |
| Verification/linkage | `VerifyError`, `NoClassDefFoundError`, `NoSuchMethodError` | Stack maps, dependency, method signature/version |
| Access/package | `IllegalAccessError`, `SecurityException` | Runtime package, module exports/opens, package ownership |
| Initialization | `ExceptionInInitializerError`, `NoClassDefFoundError` sau init fail | Code `static` và nguyên nhân gốc |
| Reflection/instance | `NoSuchMethodException`, `InvocationTargetException` | Constructor/method thực và cause của target |

**Không bắt `LinkageError` rồi tùy tiện gọi lại `defineClass`**, vì lỗi có thể đến từ việc class name đã được định nghĩa trong loader. Cần hiểu nguyên nhân và quyết định generation strategy thích hợp.

## 9. Các ràng buộc package, protection domain và module

### Package và loading constraints

`defineClass` nhận **binary name** và bytes. JVM yêu cầu class-file phù hợp, kiểm tra package/security/linkage. Một loader không thể định nghĩa hai class cùng tên trong chính nó để “cập nhật phiên bản”.

Nếu hai class cùng package cần package-private access, JVM xem chúng cùng runtime package chỉ khi **package name và defining loader** khớp. Dùng hai loader khác nhau có thể gây `IllegalAccessError` dù hai source đều khai báo `package generated;`.

### ProtectionDomain và CodeSource

`ClassLoader.defineClass` có overload nhận `ProtectionDomain`:

~~~java
Class<?> defineClass(
    String name, byte[] data, int offset, int length,
    ProtectionDomain protectionDomain)
~~~

Đây là **chữ ký minh họa** của overload `protected final`, không phải lời gọi trên ClassLoader từ mã bên ngoài.

- Protection domain, CodeSource, certificate/signers và policy package sealing có những ý nghĩa runtime riêng.
- Nếu custom loader phân phối class từ JAR đã ký, phải duy trì **tính nhất quán của certificates trong package** theo hợp đồng ClassLoader.
- Source URL/code origin cho class in-memory không tự xuất hiện; nếu cần audit, ghi origin/generation/hash rõ ràng trong loader metadata.
- **Không hiểu ProtectionDomain là sandbox sẵn có** có thể chạy mã chưa tin cậy an toàn. Trong Java hiện đại, cần giải pháp an toàn mạnh hơn ở biên process/OS.

### Named modules

Custom `MemoryLoader` tự định nghĩa classes thông thường trong **unnamed module** gắn với loader ấy. Việc source hoặc bytes có `module-info.class` không đồng nghĩa mọi class lập tức trở thành một named module đã được JPMS resolve.

Nếu yêu cầu thật sự là named modules, dùng module path, `ModuleFinder`, `Configuration`, `ModuleLayer` và loader mappings thích hợp. Các khai báo `exports`/`opens`/`requires` quyết định những mặt khác của accessibility; loader visibility không tự bỏ qua JPMS.

### Class trong `java.*`

JDK không cho một custom class loader thông thường tùy ý định nghĩa class thuộc `java.*`. `defineClass` có thể ném `SecurityException` cho những tên như vậy. Không sử dụng namespace `java.` để thử nghiệm generation.

## 10. Quản lý tài nguyên và resource lookup

Mã runtime có thể cần cả dữ liệu ngoài class-file: file cấu hình, template, `META-INF/services` hoặc resource của thư viện.

**Class bytes map không tự là resource registry.** `MemoryLoader.findClass` trong demo chỉ dùng map để tìm class bytes; `ClassLoader.getResource(...)`/`getResourceAsStream(...)` có policy và hook riêng. Nếu muốn serve resources từ memory, có thể:

1. Xây **API resource riêng** trả stream mới từ immutable bytes cache.
2. Override resource lookup đúng hợp đồng, cung cấp URL/URL handler khi thực sự cần `URL` semantics, quản lý lifetime của dữ liệu.
3. Đóng gói plugin thành JAR và dùng `URLClassLoader` nếu cần cơ chế resource/JAR/manifest tích hợp.
4. Nếu dùng named modules, áp dụng quy tắc module resource encapsulation và `opens`.

**Không cache chung một `InputStream` cho nhiều caller**, vì stream có con trỏ đọc và trạng thái close. Cache byte[] immutable hoặc metadata nguồn rồi trả **một stream mới mỗi lần**.

Với `ServiceLoader`, provider files trong `META-INF/services` hoặc `provides` của JPMS cần nằm đúng vùng tìm kiếm. Một custom in-memory loader không tự làm provider discovery khi bạn chỉ cung cấp `findClass`.

### Resource và class loading policy là hai nhánh

~~~text
Class loading:
  loadClass("generated.Hello")
       -> parent / findClass -> defineClass

Resource lookup:
  getResource("generated/config.txt")
       -> parent / findResource -> URL / stream
~~~

Nếu override `loadClass` để child-first, không có nghĩa `getResource` trở thành child-first. Sự khác biệt này đặc biệt nguy hiểm khi host/plugin chứa resource cùng tên. Cần test cả hai thứ riêng.

## 11. Concurrency và caching khi nhiều thread cùng yêu cầu class

Với custom `ClassLoader`, class loading mặc định dùng `getClassLoadingLock(name)` để điều phối cạnh tranh. Nếu chỉ override `findClass` như demo, framework loader tiếp tục kiểm tra class đã được load và định nghĩa lớp theo đồng bộ thích hợp.

Tuy nhiên, **compiler/file manager tự viết vẫn là shared mutable state** nếu được dùng chung. Không suy ra có class-loading lock thì toàn bộ compiler pipeline thread-safe.

Một thiết kế production có thể:

~~~text
Concurrent requests for template T, version V
                      |
                      v
       Cache key = (T, V, compiler options, deps hash)
                      |
                 single-flight
                      |
                 compile once
                      |
             immutable bytes snapshot
                      |
         +------------+-------------+
         |                          |
  Loader Generation A        Loader Generation B
         |                          |
   own Class<?> A              own Class<?> B
~~~

Key cache cần gồm:

- Template/source hash.
- `--release` / compiler version/options (nếu ảnh hưởng bytes).
- Classpath/module-path/dependency artifact versions.
- Annotation processing hoặc bytecode transformer version.
- Plugin generation/security policy nếu có.

Có thể chia sẻ **immutable bytecode bytes** giữa loaders khi generation/source tương đương, nhưng **không chia sẻ `Class<?>` runtime object** như thể nó được định nghĩa ở mọi loader.

### `ConcurrentHashMap.computeIfAbsent` không thay khóa classloading

`computeIfAbsent` giúp tạo cache entry atomically nhưng **không tự thay** `ClassLoader.getClassLoadingLock(name)`, `findLoadedClass` hoặc quy tắc `defineClass`. Không gọi một callback mapping có I/O rất lâu và update đệ quy cùng map rồi kỳ vọng mọi thứ không bị block/deadlock.

Nếu compile chậm, dùng single-flight placeholder như `FutureTask<byte[]>` hoặc `CompletableFuture` với lifecycle/retry rõ ràng. Khi compile lỗi:

- Không cache `null` trong ConcurrentHashMap.
- Không giữ failed future mãi trừ khi chủ động thiết kế negative cache/TTL.
- Phân biệt lỗi source vĩnh viễn và lỗi I/O/cache tạm thời.
- Không trả partial output map nếu compiler chưa báo thành công.
- Không đưa cùng mutable byte[] cho code có thể sửa trong lúc một loader gọi `defineClass`.

### Parallel-capable loader

Nếu thực sự nạp nhiều **binary class names khác nhau** song song, subclass có thể đăng ký parallel-capable bằng `registerAsParallelCapable()` khi class được initialize; tất cả superclass trong chuỗi (ngoại trừ `Object`) cần thỏa điều kiện đăng ký. Điều này cho phép loader dùng lock theo tên class thay vì khóa toàn loader trong `loadClass` mặc định.

Không bắt buộc demo nhỏ có ít class name phải đăng ký parallel-capable, và việc đăng ký **không tự làm compiler/file manager/resource cache thread-safe**.

## 12. Loader lifecycle, class unloading và hot reload

Điểm dễ mắc sai lầm là viết:

~~~java
loader = new MemoryLoader(newBytes, parent);
~~~

rồi nghĩ class cũ đã được unload. Thực tế:

- Class cũ vẫn tồn tại nếu có `Class<?>`, object instance, static cache, MethodHandle, Method/Constructor reflection object, running thread hay reference khác giữ nó/defining loader sống.
- Một loader không có `close()` không có nghĩa có thể quên lifecycle. MemoryLoader của demo giữ map bytes và Java runtime objects liên quan.
- `URLClassLoader.close()` đóng file/JAR handles, **không bắt JVM unload class ngay lập tức**.
- JVM có thể unload classes khi defining loader và những đối tượng liên quan đủ điều kiện thu gom; thời điểm không được bảo đảm theo lệnh ứng dụng.
- Nếu source/code gen thay đổi, một **loader generation mới** thường là đường thông thường để tạo runtime class mới cùng binary name.

Một lifecycle thực tế:

~~~text
Generation 1 (ACTIVE)
       |
       +--> stop accepting new plugin work
       |
       v
     DRAINING
       |
       +--> finish ongoing requests
       +--> stop plugin threads/scheduled tasks
       +--> close streams/JAR handles
       +--> unregister callbacks/services/listeners
       +--> clear caches holding Class/instance/loader
       +--> restore thread context loader
       |
       v
     RETIRED (eligible for GC when references disappear)

Generation 2 (ACTIVE)
       |
       +--> new loader + new generated classes
~~~

**Lưu ý:** để có hot reload không gián đoạn, host có thể cần **immutable shared API** ở parent và một **atomic generation handle** trỏ về tập provider mới. Request cũ tiếp tục dùng generation cũ đến khi hoàn tất, request mới dùng generation mới; sau đó gỡ references cũ. Không swap từng class name trong cùng loader rồi trông đợi JVM cập nhật ngay.

## 13. Khi nào dùng compiler, bytecode generator hoặc proxy?

| Nhu cầu | Hướng phù hợp | Cân nhắc |
|---|---|---|
| Sinh class từ Java source/template mà người phát triển kiểm soát | `JavaCompiler` API | Compiler phải có, chi phí compile và diagnostics |
| Sinh nhiều adapter/proxy hiệu năng cao | Byte Buddy/ASM hoặc runtime framework thích hợp | Hiểu bytecode verification, package, loader lifecycle |
| Tạo implementation của interface bằng handler | `java.lang.reflect.Proxy` | Giới hạn theo interface, method invocation handler |
| Tạo class cùng loader/package với một lookup class | `MethodHandles.Lookup.defineClass` khi hợp đồng cho phép | Lookup privileges, same package/loader |
| Class ngắn hạn phục vụ framework runtime | Hidden class APIs khi đúng use case | Không dùng như class tìm được bình thường bằng binary name |
| Plugin/JAR có nhiều resources/phụ thuộc | `URLClassLoader` + policy phù hợp | Quản lý URL/JAR handles, resources và parent delegation |
| Runtime Java 17+ không có compiler | Precompile trước, dùng compiled artifact hoặc công nghệ khác | Không mặc định `ToolProvider` luôn trả compiler |
| Plugin không tin cậy | Process/container isolation | Classloader không phải sandbox |

Đôi khi **không cần sinh class**: dùng lambda, strategy pattern, reflection, `MethodHandle` hoặc cấu hình dữ liệu có thể đơn giản hơn. Dynamic compilation nên được chọn khi sự linh hoạt thực sự bù được chi phí bộ nhớ, CPU và sự phức tạp của type/lifecycle.

## 14. An toàn: không biên dịch và chạy source tùy ý trong JVM host

**Cảnh báo thiết kế:** nhận source Java từ người dùng chưa tin cậy, gọi `JavaCompiler` và sau đó load/execute trong cùng JVM **không phải cách ly an toàn**.

Lý do:

- Compiler có thể tiêu thụ CPU/heap/disk và xử lý classpath/module path ngoài dự kiến.
- Annotation processors có thể chạy code trong quá trình compile nếu được cấu hình/cho phép. Demo sử dụng `-proc:none` để tắt processor, nhưng **điều này không tạo sandbox cho code được compile**.
- Bytecode đã load có thể gọi API file system, network, reflection hoặc tài nguyên tiến trình mà Java/OS cho phép.
- Một class có static initializer, thread vô hạn, recursion sâu hoặc giữ reference tới loader có thể phá vòng đời host.
- Dynamic generation có thể tạo vô hạn class unique, gây áp lực metaspace/heap và class unloading khó.

Nếu phải phục vụ mã chưa tin cậy:

1. Dùng process/container riêng với permissions tối thiểu và giới hạn CPU/memory/time.
2. Không dùng application classpath chứa secrets/internal APIs cho compiler không tin cậy.
3. Giới hạn kích thước source, số lượng classes, dependencies và thời gian compile.
4. Kiểm soát annotation processing, plugins/compiler options và artifact provenance.
5. Kiểm tra chữ ký/hash khi nhận bytecode sẵn có từ nguồn ngoài.
6. Giao tiếp qua RPC/schema thay vì cast trực tiếp các class không tin cậy vào object graph của host.
7. Không coi SecurityManager hoặc ClassLoader riêng là lớp sandbox bảo mật mặc định trên Java 17+.

## 15. Debug từ compiler output tới defining loader

Nếu class mới “không hoạt động”, chẩn đoán theo **giai đoạn** thay vì thay classpath ngẫu nhiên.

### Bước 1 — Compiler có sẵn không?

~~~java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
System.out.println(compiler != null);
~~~

Nếu `false`, xác minh runtime đang chạy có compiler provider và module `java.compiler` hay không; có thể cần chạy với JDK đầy đủ hoặc cấu hình runtime image lại.

### Bước 2 — Compiler diagnostics nói gì?

Đọc `DiagnosticCollector`: loại lỗi, dòng, cột, message, source URI. Nếu compile task trả `false`, chưa đến bước class loading.

### Bước 3 — Có đúng class-file output không?

~~~java
Map<String, byte[]> generated = files.snapshot();
System.out.println(generated.keySet());
~~~

Đây là **mảnh minh họa**, cần đối tượng file manager `files` từ pipeline. Nếu class cần là `generated.Hello`, phải có entry theo binary name ấy. Nếu compiler sinh nested classes, nhiều entries khác cũng cần được lưu.

### Bước 4 — Parent có che class mới không?

~~~java
Class<?> actual = loader.loadClass("generated.Hello");
System.out.println(actual.getClassLoader() == loader);
~~~

Nếu `false`, parent-first delegation có thể đã trả một class cùng binary name từ parent. Tên class đúng không chứng minh bytes vừa sinh đã được dùng.

### Bước 5 — Nhìn metadata và nguồn

~~~java
Class<?> type = loader.loadClass("generated.Hello");
System.out.println("type=" + type.getName());
System.out.println("loader=" + type.getClassLoader());
System.out.println("module=" + type.getModule());
~~~

Các mảnh code chẩn đoán cần biến `loader` và imports thích hợp.

Khi dùng class từ source/JAR, có thể xem `type.getProtectionDomain().getCodeSource()` nếu tồn tại; **generated in-memory classes không tự có CodeSource URL tin cậy**. Nên tự ghi logical generation ID, source hash, compiler options và bytecode hash trong metadata/log do host quản lý.

### Bước 6 — Nếu lỗi xuất hiện ở runtime

Phân biệt:

- `ClassNotFoundException`: loader không tìm được binary name.
- `NoClassDefFoundError`: dependency không tìm được lúc resolve, tên class mismatch hoặc init trước đó thất bại.
- `ClassFormatError`/`VerifyError`: bytes/generator không thỏa JVM class format/verifier.
- `NoSuchMethodError`: runtime dependency signature không khớp bản compile.
- `IllegalAccessError`: runtime package/module access không phù hợp.
- `ExceptionInInitializerError`: code `static` chạy rồi lỗi.
- `ClassCastException`: thường liên quan runtime type identity khi host/plugin có duplicate type definitions.

Không coi mọi lỗi trên là compiler lỗi. Cần stack trace, cause chain, defining loader, source bytes metadata và thời điểm load/link/initialize.

## 16. Những sai lầm phổ biến

1. **“Sinh được `byte[]` nghĩa là đã có runtime class.”** Sai: cần class definition trong JVM.
2. **“`JavaCompiler.getTask` tự biên dịch ngay.”** Sai: `call()` mới thực hiện task.
3. **“Biên dịch thành công nghĩa là mọi dependency runtime đều đúng.”** Sai: runtime loader có thể nhìn phiên bản khác.
4. **“`defineClass` tạo object và chạy constructor.”** Sai: nó định nghĩa Class, còn khởi tạo instance là bước khác.
5. **“Một loader có thể định nghĩa lại cùng tên để reload.”** Sai: cần generation loader mới hoặc redefinition API chuyên dụng.
6. **“Cùng binary name và bytecode là cùng runtime type.”** Sai nếu defining loader khác.
7. **“Có thể gọi `defineClass` trực tiếp trên system loader từ mọi class.”** Sai: protected final, phải dùng cơ chế hợp lệ.
8. **“`Lookup.defineClass` định nghĩa bất kỳ package/classloader nào.”** Sai: Lookup gắn với quyền, package và defining loader.
9. **“Các class do custom loader định nghĩa tự thành named JPMS modules.”** Sai: thông thường thuộc unnamed module của loader.
10. **“Resource lookup tự đọc map class bytes.”** Sai: `findClass` và `findResource` là đường API khác nhau.
11. **“Compiler file manager thread-safe vì ClassLoader thread-safe.”** Sai: các đối tượng/state có hợp đồng đồng thời riêng.
12. **“Cache `Class<?>` toàn cục theo tên là tốt.”** Sai: phá loader identity và giữ loader cũ sống.
13. **“`URLClassLoader.close()` lập tức unload mọi class.”** Sai: chỉ đóng tài nguyên loader; unloading phụ thuộc GC/references.
14. **“`-proc:none` làm source user nhập trở nên an toàn.”** Sai: chỉ tắt annotation processing trong compilation, không sandbox code runtime.
15. **“`ToolProvider.getSystemJavaCompiler()` chắc chắn không null.”** Sai với runtime image thiếu compiler.
16. **“`ClassNotFoundException` và `NoClassDefFoundError` hoàn toàn giống nhau.”** Sai: khác giai đoạn/nguyên nhân.
17. **“Thêm `-classpath` cho compiler là đủ cho named module runtime.”** Sai: còn module resolution, layer, readability/exports.
18. **“File `generated.Hello.class` là tên class để `loadClass`.”** Sai: gọi bằng `generated.Hello`; đường dẫn entry dùng dấu `/`.
19. **“Class loader là sandbox để chạy code khách.”** Sai: cần ranh process/OS nếu không tin cậy.
20. **“Giữ generated classes trong static map mãi không có hậu quả.”** Sai: có thể gây metaspace/heap pressure và plugin classloader leak.

## 17. Checklist production

- [ ] Chọn rõ cơ chế **source compiler**, **bytecode generator** hay **proxy**, không dùng generation khi một strategy object đơn giản đủ đáp ứng.
- [ ] Compiler tồn tại ở runtime image mục tiêu; `--release` tương thích JVM đích.
- [ ] Source name và public class/binary name khớp; compiler output map chứa đủ nested/helper classes.
- [ ] Diagnostics có line/column/message và không lộ dữ liệu nhạy cảm.
- [ ] File manager/streams được đóng đúng cách, không dùng chung mutable state không kiểm soát.
- [ ] Parent loader định nghĩa các shared interfaces/DTOs theo hợp đồng.
- [ ] Compilation classpath và runtime loader có dependency versions tương thích.
- [ ] Generated bytes là snapshot bất biến trước khi đưa cho loader.
- [ ] `loadClass`/`getClassLoadingLock`/`findLoadedClass` không bị bypass sai cách.
- [ ] `defineClass` dùng binary name đúng, không lạm dụng protected API.
- [ ] Runtime module/package/access constraints được kiểm tra.
- [ ] Có test generated bytecode khác version, corrupted class-file, missing dependencies và duplicate definition.
- [ ] Có bound/single-flight cho compilation cache nếu nhiều request cùng source.
- [ ] Có giới hạn CPU/heap/metaspace, số classes, source size, compile timeout.
- [ ] Không dùng compile/load trong cùng process cho code chưa tin cậy.
- [ ] Có generation/version ID và cơ chế chuyển thế hệ không làm request đang chạy lỗi.
- [ ] Có shutdown/drain để ngừng thread/plugin tasks và loại references tới loader cũ.
- [ ] Resource, SPI, TCCL và caches được kiểm tra riêng với class loading.
- [ ] JFR/JVM classloading metrics hoặc log có thể giúp chẩn đoán leaks khi cần.

## 18. Bài tập tự kiểm tra

**Câu 1.** Java source `generated.Hello` đã có trong một String. API nào biến source thành bytes mà không cần tự viết class-file format?

**Đáp án:** `javax.tools.JavaCompiler` với một `JavaFileObject` và file manager phù hợp. Gọi `getTask(...).call()`, thu output `.class`.

**Câu 2.** Cần đưa bytes vào JVM thành runtime class. Có thể gọi `defineClass` trực tiếp trên một ClassLoader bất kỳ không?

**Đáp án:** Không từ mã không có quyền truy cập, vì `defineClass` là protected final. Thường tạo custom ClassLoader và override `findClass`, để `loadClass` chuẩn điều phối.

**Câu 3.** Cùng binary name `generated.Hello` nhưng compile hai phiên bản rồi định nghĩa trong hai loaders. Hai `Class<?>` có bằng nhau theo `==` không?

**Đáp án:** Không. JVM xét cả defining loader trong runtime type identity.

**Câu 4.** Compile class mới thành công nhưng lúc dùng gặp `NoSuchMethodError`. Nên điều tra gì?

**Đáp án:** Runtime dependency defining loader/version, method descriptor được compile và binary compatibility, không chỉ compiler diagnostics.

**Câu 5.** Thay `byte[]` trong map của loader cũ có cập nhật `Class<?>` đã định nghĩa không?

**Đáp án:** Không. Có thể tạo loader generation mới; instrumentation/redefinition có quy tắc riêng.

**Câu 6.** Một generated class implement SPI của host nhưng host cast thất bại dù tên interface giống nhau. Khả năng gì?

**Đáp án:** Hai bản SPI được định nghĩa bởi loaders khác nhau. Shared API nên do parent chung định nghĩa.

**Câu 7.** Vì sao `ToolProvider.getSystemJavaCompiler()` có thể trả `null`?

**Đáp án:** Compiler provider/module không có trong runtime image hoặc môi trường không cung cấp system compiler; cần full JDK hoặc cấu hình khác.

**Câu 8.** Đặt `-proc:none` trong demo có biến việc thực thi generated code thành an toàn không?

**Đáp án:** Không. Nó chỉ tắt annotation processing ở compilation; runtime code vẫn có quyền của process.

**Câu 9.** `ClassLoader.close()` có phải API của mọi ClassLoader không?

**Đáp án:** Không. `ClassLoader` cơ sở không có `close()`; `URLClassLoader` triển khai `Closeable`. Loader custom lưu bytes trong RAM cần quản lý references/lifecycle phù hợp.

**Câu 10.** Khi compiled source chứa cả inner class `Hello$Inner`, cần lưu những output nào?

**Đáp án:** Tất cả class files mà compiler sinh ra, gồm `generated.Hello` và `generated.Hello$Inner` khi có, keyed theo binary names, để loader tìm được khi JVM cần.

## 19. Mô hình quyết định

~~~text
Cần sinh behavior động?
          |
          v
Có cần một Class mới không?
      /             \
    Không            Có
      |               |
Lambda/strategy   Source Java hay bytecode trực tiếp?
                      /                   \
                   Source              Bytecode
                      |                   |
                JavaCompiler         generator ASM/...
                      |                   |
               Diagnostics +          validate class
               classfile bytes        file version
                      +---------+---------+
                                |
                         Loader generation
                                |
                    shared API từ parent?
                                |
                    defineClass đúng name
                                |
                      Class<?> và instance
                                |
                 verify type identity/linkage
                                |
                metadata/cache/resource/lifecycle
                                |
                retire loader generation khi xong
~~~

**Tổng kết:** Sinh source/bytecode là bước **tạo dữ liệu**; JavaCompiler là bước **tạo class-file bytes**; ClassLoader là bước **xác lập runtime type identity**. Một hệ thống dynamic class generation đúng cần đồng thời thiết kế compiler diagnostics, classpath/version, package/module access, loader concurrency, nguồn resource và cơ chế thu hồi generation. Hai class cùng tên có thể cùng tồn tại nhờ hai loaders, nhưng không thể “ghi đè” class cũ trong cùng loader như thay file văn bản.

### Tài liệu chính thức

- [Java SE 17 — JavaCompiler API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html)
- [Java SE 17 — JavaFileManager API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaFileManager.html)
- [Java SE 17 — SimpleJavaFileObject API](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/SimpleJavaFileObject.html)
- [Java SE 17 — ClassLoader / defineClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — MethodHandles.Lookup.defineClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html#defineClass(byte%5B%5D))
- [JVMS 17 §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3)
