# 15.1 Chuỗi tạo bytecode hợp lệ, định nghĩa lớp, khởi tạo và gọi mã mới

Trong Java, có thể tạo ra **một lớp chưa tồn tại trong mã nguồn khi chương trình khởi động**, đưa định nghĩa lớp đó vào JVM rồi khởi tạo đối tượng và gọi những phương thức mới. Chuỗi này thường gặp trong runtime frameworks, ngôn ngữ động chạy trên JVM, proxy/code generation, rule engines và hệ thống biên dịch tại chỗ (*runtime compilation*).

Điểm cốt lõi không chỉ là “có một mảng `byte[]` và gọi `defineClass`”. Mảng đó phải biểu diễn **classfile hợp lệ** với metadata, constant pool, chữ ký phương thức và bytecode đúng; class phải được định nghĩa trong **class loader/module/package phù hợp**; JVM còn thực hiện liên kết và kiểm chứng; chỉ sau đó mới có thể **khởi tạo lớp, tạo instance và thực thi phương thức**. Mỗi giai đoạn có lỗi và điều kiện thành công riêng.

Bài này tập trung vào toàn bộ đường đi:

~~~text
Mô tả lớp / source / bytecode builder
                    │
                    ▼
       Tạo nội dung .class hợp lệ
                    │
                    ▼
       byte[] chứa classfile
                    │
        kiểm tra cấu trúc cơ bản
                    │
                    ▼
          Định nghĩa lớp
       Lookup.defineClass(bytes)
           hoặc ClassLoader
                    │
                    ▼
       Class<?> đại diện cho lớp
                    │
         linking / verification
                    │
                    ▼
      Khởi tạo class (<clinit>)
         (khi được yêu cầu)
                    │
                    ▼
    Tạo object (constructor <init>)
                    │
                    ▼
   Gọi mã mới qua Reflection /
      MethodHandle / interface
~~~

Các chương trình tự chạy trên **JDK 17+**, không cần thư viện ngoài. Ví dụ thứ nhất nhờ `JavaCompiler` của JDK tạo bytecode hợp lệ trong bộ nhớ, rồi dùng `MethodHandles.Lookup.defineClass`. Ví dụ thứ hai tự dựng **classfile nhị phân tối giản** bằng `DataOutputStream`, định nghĩa qua một `ClassLoader` riêng, khởi tạo instance và gọi phương thức mới. Việc tự viết bytecode thủ công chỉ nhằm học cấu trúc; production nên ưu tiên trình biên dịch hoặc thư viện tạo bytecode đã được kiểm thử.

## 1. Class mới thực sự bắt đầu từ đâu?

Có ba khái niệm không nên trộn:

- **Mã nguồn Java**: chuỗi có cú pháp như `public class Greeter { ... }`. JVM thông thường **không nạp trực tiếp chuỗi source** để tạo class; phải có bước biên dịch hoặc sinh classfile.
- **Classfile**: chuỗi byte theo JVM Class File Format. Nó bắt đầu bằng magic `0xCAFEBABE`, có thông tin version, constant pool, access flags, this/super class, danh sách field/method/attribute và `Code` attributes chứa chỉ thị bytecode.
- **Lớp đã được JVM định nghĩa**: thực thể runtime được biểu diễn bằng một `Class<?>`, gắn với **defining class loader** và các quy tắc module/package. Một tên lớp nhìn giống nhau không chứng minh hai lớp là cùng một kiểu nếu loader khác nhau.

Ví dụ một classfile có tên nhị phân `runtime.GeneratedMultiplier` dùng tên nội bộ trong constant pool:

~~~text
binary name (Java API): runtime.GeneratedMultiplier
internal JVM name:     runtime/GeneratedMultiplier
class descriptor:      Lruntime/GeneratedMultiplier;
~~~

Mảng `byte[]` hợp lệ là **đầu vào** của việc định nghĩa lớp, không phải một object đã được tạo. Chỉ khi `defineClass` trả `Class<?>` thành công, JVM mới có định nghĩa lớp tương ứng. Việc gọi constructor là giai đoạn khác nữa.

### “Tạo bytecode” có thể có nhiều con đường

| Đường tạo byte[] | Đặc điểm | Khi thích hợp |
| --- | --- | --- |
| `javac` hoặc `javax.tools.JavaCompiler` | Biên dịch source hợp lệ thành classfile, compiler tự tạo constant pool, stack maps, bytecode | Khi có thể diễn đạt lớp mới bằng Java source |
| Thư viện bytecode chuyên dụng như ASM/Byte Buddy | Có API dựng/biến đổi classfile, hỗ trợ thao tác JVM ở mức thấp | Framework/code generator phức tạp |
| Tự viết classfile với `DataOutputStream` | Tự chịu trách nhiệm từng chỉ số, độ dài, opcode và verification constraints | Học cấu trúc classfile hoặc bài toán cực kỳ giới hạn |
| Đọc classfile đã biên dịch sẵn | Không phải tạo bytecode mới; chỉ nạp một định nghĩa chưa nạp | Plugin/extension có sẵn class bytes |

Không phải code generation nào cũng cần `invokedynamic`. `invokedynamic` liên quan một **điểm gọi** có bootstrap/linkage; còn `defineClass` liên quan **định nghĩa một kiểu mới**. Hai cơ chế có thể phối hợp trong một framework nhưng không đồng nghĩa.

## 2. Điều kiện tối thiểu để bytecode hợp lệ

Một classfile không phải dữ liệu tùy ý có tên kết thúc `.class`. Cần tuân thủ JVM Class File Format và các ràng buộc semantic/verifier.

**Header:** bốn byte đầu là `CA FE BA BE`, sau đó hai byte `minor_version` và hai byte `major_version`. Java 17 ứng với major version **61** (hệ thập phân). Không suy ra phiên bản Java từ độ dài mảng byte; đọc đúng vị trí của header.

**Constant pool:** là bảng một-based, với `constant_pool_count` bao gồm slot số 0 không sử dụng. Các mục như `CONSTANT_Utf8`, `CONSTANT_Class`, `CONSTANT_NameAndType`, `CONSTANT_Methodref` tham chiếu nhau bằng chỉ số. Tham chiếu tới sai loại constant hoặc chỉ số ngoài bảng dẫn đến classfile không hợp lệ.

**Class metadata:** `access_flags` chỉ ra class/interface/public/final...; `this_class`, `super_class` phải tham chiếu đúng mục `CONSTANT_Class`. Tên nội bộ dùng dấu gạch chéo `/`. Class thông thường có super class (trừ `java/lang/Object`).

**Method descriptors:** mô tả chính xác kiểu input/output. Ví dụ `()V` là phương thức không tham số trả `void`; `(I)I` nhận `int` và trả `int`. Không đặt `(int)int` vào constant pool như descriptor JVM; ký hiệu đó chỉ là cách đọc tiện trong Java.

**Code attribute:** method có code phải khai báo `max_stack`, `max_locals`, `code_length`, mã bytecode, exception table và danh sách attribute con. Giá trị `max_stack` cần đủ cho độ sâu operand stack; `max_locals` cần chứa receiver ở slot 0 với instance method và các tham số, kể cả trường hợp `long`/`double` chiếm hai slot.

**Control flow và verifier:** bytecode không chỉ đúng cú pháp mà còn phải có stack types, branch targets, kiểu giá trị và quy tắc khởi tạo object nhất quán. Với classfile phiên bản mới, các branch phức tạp thường cần `StackMapTable` phù hợp. Ví dụ classfile tự viết trong bài có **luồng thẳng không nhánh**, nên có thể dùng Code attribute tối giản mà không tự xây stack map frames.

**Quyền truy cập:** không thể làm một class trở nên hợp lệ bằng cách bỏ qua package/module, superclass access hoặc quyền truy cập. Những lỗi này có thể xảy ra trong giai đoạn verification, preparation, resolution, initialization hoặc method invocation tùy tình huống.

Các lỗi phổ biến được phân tích ở phần sau; trước tiên cần một cách tạo byte[] mà compiler đảm bảo hợp lệ.

## 3. Phân tách loading, linking, initialization, instantiation

Java định nghĩa các giai đoạn khác nhau đối với một class:

| Giai đoạn | Chuyện gì xảy ra? | Điều không được suy đoán |
| --- | --- | --- |
| **Loading/definition** | Tìm/nhận biểu diễn nhị phân, đưa class vào JVM, có `Class<?>` | Constructor đã chạy |
| **Verification** | Kiểm tra bytecode và ràng buộc an toàn kiểu | Nội dung phương thức chắc chắn đúng nghiệp vụ |
| **Preparation** | Cấp phát/thiết lập giá trị mặc định cho static fields theo cơ chế JVM | Static initializer trong source đã được chạy |
| **Resolution** | Chuyển symbolic references sang runtime references khi cần | Mọi liên kết phụ thuộc đều bắt buộc xong hoàn toàn ngay lập tức |
| **Initialization** | Thực hiện class initializer `<clinit>` nếu có, theo quy tắc JVM | Đồng nghĩa tạo một instance |
| **Instantiation** | Tạo object, cấp phát và chạy constructor `<init>` | Mỗi class chỉ có đúng một instance |
| **Invocation** | Gọi method trên object hoặc gọi static method | Lúc gọi có thể bỏ qua quyền truy cập, kiểu tham số và ngoại lệ |

Thứ tự và thời điểm chi tiết của loading/linking/resolution có thể được JVM thực hiện *lazily* theo quy tắc specification. `Lookup.defineClass` không tự yêu cầu chạy class initializer. Muốn buộc initialization có thể dùng `Class.forName(name, true, loader)` hoặc thao tác kích hoạt khởi tạo theo ngữ nghĩa Java, chẳng hạn tạo object bằng constructor.

**Tên class và object:** `Class<?> generated` là handle metadata của kiểu; `Object instance = constructor.newInstance(...)` là một instance của kiểu đó. Giữ riêng hai biến giúp tránh nhận định sai “defineClass đã tạo đối tượng”.

## 4. Lựa chọn API định nghĩa lớp

### A. MethodHandles.Lookup.defineClass(byte[])

~~~java
MethodHandles.Lookup lookup = MethodHandles.lookup();
Class<?> defined = lookup.defineClass(bytes);
~~~

Đây là **đoạn minh họa**, cần import `java.lang.invoke.MethodHandles`, biến `bytes` mang classfile hợp lệ và ngữ cảnh cho phép. API có từ Java 9, cho phép định nghĩa một **named class** bằng byte[] trong cùng runtime package với lớp chứa lookup và dưới quyền truy cập phù hợp. Lookup phải có quyền **PACKAGE**; không thể dùng lookup của một package bất kỳ để lén định nghĩa lớp ở package khác.

Trong một ví dụ ở **default package**, lookup lấy từ `CompileAndDefineDemo` sẽ định nghĩa được class mới `GeneratedGreeter` cũng thuộc default package, với class loader/module phù hợp. Nếu classfile tên `other.pkg.GeneratedGreeter` thì `lookup.defineClass(bytes)` không thể tùy tiện đặt tên đó vào package khác.

`defineClass` trả `Class<?>`, **không khởi tạo class chỉ bởi thao tác định nghĩa**; mã `static { ... }` chưa nhất thiết chạy. Sau đó có thể yêu cầu initialization rõ ràng.

### B. ClassLoader.defineClass(...)

~~~java
static class ByteLoader extends ClassLoader {
    ByteLoader(ClassLoader parent) {
        super(parent);
    }

    Class<?> define(String binaryName, byte[] bytes) {
        return defineClass(binaryName, bytes, 0, bytes.length);
    }
}
~~~

Đây là **đoạn class minh họa**, cần đặt vào class/file hợp lệ và truyền đúng `binaryName`. `ClassLoader#defineClass` là phương thức **protected**, thường dùng trong subclass loader tự viết. Nó có thể định nghĩa class từ mảng byte theo tên nhị phân; JVM kiểm tra tên, cấu trúc và các ràng buộc liên quan. Nó **không** là cách tránh verifier.

Một class được xác định bằng **(binary name, defining loader)**. Hai `Class<?>` có tên `runtime.GeneratedMultiplier` nhưng loader khác nhau là **hai kiểu khác nhau** tại runtime. Dùng `instanceof`/cast giữa hai thế giới loader không được phép chỉ vì tên text giống nhau.

### C. defineHiddenClass, khác mục tiêu của bài

`Lookup.defineHiddenClass(...)` có thể dùng cho một số kiểu class hỗ trợ runtime code generation có identity/khả năng khám phá khác named classes. Hidden classes có các quy tắc tên/lookup và class loading khác, không phải thay thế trực tiếp khi bạn cần một **named class** có thể tra bằng `Class.forName("pkg.Name")`. Trong bài này ta cố ý dùng **named class** để quan sát đủ chuỗi define → initialize → instantiate → invoke.

### D. Không cần chọn loader tùy tiện

Nếu framework muốn định nghĩa lớp trong cùng package/module và tương tác trực tiếp với các member cho phép, `Lookup.defineClass` có lợi thế quyền truy cập tương ứng lookup. Nếu muốn cách ly phiên bản/plugin hoặc tạo namespace riêng, một `ClassLoader` chuyên dụng phù hợp hơn; khi đó phải thiết kế delegation, parent loader, visibility, package, module và lifecycle. Không áp dụng mẹo reflection gọi `ClassLoader.defineClass` trên arbitrary loader để vượt encapsulation của JDK.

## 5. Ví dụ hoàn chỉnh 1 — biên dịch Java source thành byte[] trong bộ nhớ

Ví dụ này dùng **JDK JavaCompiler API**, hoàn toàn không ghi file `GeneratedGreeter.class` lên đĩa. Chương trình:

1. Viết mã nguồn lớp `GeneratedGreeter` thành một `String`.
2. Dùng `JavaCompiler` và một `JavaFileManager` nhận bytecode vào `ByteArrayOutputStream`.
3. Kiểm tra file sinh ra có magic `CAFEBABE`.
4. Dùng `MethodHandles.lookup().defineClass(bytes)`.
5. Chủ động kích hoạt `<clinit>` bằng `Class.forName(..., true, ...)`.
6. Tạo object qua constructor.
7. Gọi `greet` bằng Reflection và bằng `MethodHandle`.

**Đây là một chương trình Java 17+ độc lập**, không cần Maven/Gradle/ASM. Tạo file **CompileAndDefineDemo.java**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;
import java.net.URI;
import java.nio.ByteBuffer;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public class CompileAndDefineDemo {
    static final class SourceFile extends SimpleJavaFileObject {
        private final String source;

        SourceFile(String binaryName, String source) {
            super(URI.create("string:///" + binaryName
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.source = source;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return source;
        }
    }

    static final class ClassFile extends SimpleJavaFileObject {
        private final ByteArrayOutputStream output =
                new ByteArrayOutputStream();

        ClassFile(String binaryName, Kind kind) {
            super(URI.create("memory:///" + binaryName + kind.extension),
                    kind);
        }

        @Override
        public OutputStream openOutputStream() {
            return output;
        }

        byte[] bytes() {
            return output.toByteArray();
        }
    }

    static final class MemoryFileManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        private final Map<String, ClassFile> compiled = new HashMap<>();

        MemoryFileManager(StandardJavaFileManager delegate) {
            super(delegate);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                Location location,
                String className,
                JavaFileObject.Kind kind,
                FileObject sibling) {
            ClassFile file = new ClassFile(className, kind);
            compiled.put(className, file);
            return file;
        }

        byte[] getBytes(String className) {
            ClassFile file = compiled.get(className);
            if (file == null) {
                throw new IllegalStateException("No class: " + className);
            }
            return file.bytes();
        }
    }

    public static void main(String[] args) throws Throwable {
        String className = "GeneratedGreeter";

        String source = """
                public class GeneratedGreeter {
                    static {
                        System.out.println("generated: initialized");
                    }

                    private final String prefix;

                    public GeneratedGreeter(String prefix) {
                        this.prefix = prefix;
                    }

                    public String greet(String name) {
                        return prefix + name;
                    }
                }
                """;

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("Run using a full JDK");
        }

        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();

        byte[] bytes;
        try (StandardJavaFileManager standard =
                     compiler.getStandardFileManager(
                             diagnostics, Locale.ROOT, null)) {
            MemoryFileManager files = new MemoryFileManager(standard);
            JavaCompiler.CompilationTask task = compiler.getTask(
                    null,
                    files,
                    diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null,
                    List.of(new SourceFile(className, source)));

            boolean compiled = Boolean.TRUE.equals(task.call());
            if (!compiled) {
                for (Diagnostic<? extends JavaFileObject> diagnostic :
                        diagnostics.getDiagnostics()) {
                    System.err.println(diagnostic);
                }
                throw new IllegalStateException("Compilation failed");
            }
            bytes = files.getBytes(className);
        }

        System.out.println("compiled: " + (bytes.length > 0));
        System.out.printf("magic: %08X%n",
                ByteBuffer.wrap(bytes).getInt());

        MethodHandles.Lookup lookup = MethodHandles.lookup();
        Class<?> generated = lookup.defineClass(bytes);
        System.out.println("defined: " + generated.getName());

        System.out.println("request initialization");
        Class.forName(
                generated.getName(), true, generated.getClassLoader());

        Object instance = generated
                .getDeclaredConstructor(String.class)
                .newInstance("Hi ");

        Method greet = generated.getMethod("greet", String.class);
        System.out.println("reflect: " + greet.invoke(instance, "Lan"));

        MethodHandle handle = lookup.findVirtual(
                generated,
                "greet",
                MethodType.methodType(String.class, String.class));
        System.out.println("handle type: " + handle.type());
        System.out.println("handle: " +
                handle.invokeWithArguments(instance, "Minh"));
    }
}
~~~

Lưu và thực thi:

~~~bash
javac CompileAndDefineDemo.java
java CompileAndDefineDemo
~~~

Stdout dự kiến trên **JDK 17+**:

~~~text
compiled: true
magic: CAFEBABE
defined: GeneratedGreeter
request initialization
generated: initialized
reflect: Hi Lan
handle type: (GeneratedGreeter,String)String
handle: Hi Minh
~~~

### Mổ xẻ từng dòng

- `compiled: true`: JavaCompiler đã sinh một classfile và bộ nhớ nhận được byte[]. Việc compile thành công cho thấy Java source hợp lệ theo cấu hình `--release 17`, nhưng chưa kiểm tra mọi chính sách nạp lớp của chương trình chủ.
- `magic: CAFEBABE`: đọc bốn byte đầu với `ByteBuffer` theo byte order mặc định big-endian. Đây là **kiểm tra nhận diện**, không phải kiểm tra đầy đủ classfile.
- `defined: GeneratedGreeter`: `Lookup.defineClass` đã tạo định nghĩa named class cùng package runtime với `CompileAndDefineDemo`. Chưa cần có object `GeneratedGreeter` nào.
- `request initialization` xuất hiện **trước** dòng `generated: initialized`. Lệnh `Class.forName(..., true, ...)` yêu cầu khởi tạo class và thực thi static initializer một lần cho class đó trong class loader tương ứng.
- `reflect: Hi Lan`: constructor `GeneratedGreeter(String)` tạo object với `prefix="Hi "`; `Method.invoke` gọi instance method trên object.
- `handle type: (GeneratedGreeter,String)String`: `findVirtual` tạo handle có receiver `GeneratedGreeter` là tham số đầu, dù method source chỉ khai báo một tham số `String`. Nếu dùng `bindTo(instance)`, handle mới sẽ chỉ nhận `String`.
- `handle: Hi Minh`: `invokeWithArguments` có thể gọi handle với các giá trị cung cấp; nó sử dụng cơ chế chuyển đổi lập luận thông thường của method handles. `invokeExact` yêu cầu chữ ký call site tĩnh khớp tuyệt đối, không phù hợp trực tiếp khi ta chỉ giữ receiver dưới kiểu `Object` mà không có adapter.

**Vì sao không dùng `Class.forName("GeneratedGreeter")` ngay từ đầu?** Trước khi định nghĩa class, loader thông thường chưa biết tên đó nếu không có classfile trên classpath. Sau khi `lookup.defineClass(bytes)` thành công, ta có thể dùng đúng `generated.getClassLoader()` để định vị lớp vừa được định nghĩa.

**Vì sao `GeneratedGreeter` không có `package`?** Để ví dụ trong **default package** có thể dùng lookup của `CompileAndDefineDemo` mà không cần file/thư mục package. Với mã production, hãy dùng package có tên và đảm bảo class mới cùng runtime package với lookup đúng theo yêu cầu `Lookup.defineClass`.

### Khi một lần biên dịch tạo nhiều classfile

Ví dụ chỉ có một class cần nạp. Mã Java có nested class hoặc nhiều top-level class hợp lệ có thể sinh **nhiều classfile**. `MemoryFileManager` đã lưu theo tên nhị phân; khi đó framework cần quản lý từng class byte[] và định nghĩa những class cần thiết theo loader phù hợp. Không giả định compiler luôn trả đúng một file class duy nhất chỉ vì đầu vào là một chuỗi source.

## 6. Tạo và khởi tạo class là hai việc khác nhau

Giả sử class có static initializer:

~~~java
static {
    System.out.println("class initialized");
}
~~~

Đây là **đoạn class member minh họa**, không phải class đầy đủ. Phân biệt:

~~~text
defineClass(bytes)
    => đã định nghĩa class
    => không tự yêu cầu chạy static initializer

Class.forName(binaryName, true, loader)
    => yêu cầu khởi tạo class
    => thực thi <clinit> nếu cần

getDeclaredConstructor(...).newInstance(...)
    => tạo object, chạy constructor
    => lớp phải được khởi tạo trước khi tạo object

method.invoke(object, ...)
    => chạy method trên instance đã có
~~~

Một số điểm tinh tế:

- **Loading** và **initialization** không đồng nghĩa. `Class.forName(name, false, loader)` có thể tìm/tải class mà không yêu cầu khởi tạo; `true` yêu cầu khởi tạo.
- **Initialization thông thường diễn ra một lần trên mỗi định nghĩa class** nếu thành công, không phải mỗi lần tạo object. Nếu chạy hai instance, constructor chạy hai lần, static initializer không vì vậy chạy hai lần.
- Nếu `<clinit>` thất bại, JVM có thể báo `ExceptionInInitializerError` (hoặc lan truyền `Error` thích hợp). Các lần sử dụng sau đó có thể gặp `NoClassDefFoundError` do lớp ở trạng thái erroneous, không nhất thiết chạy lại initializer.
- `Class<?>` không đồng nghĩa có constructor public/no-arg. `getDeclaredConstructor(...)` phải tìm đúng signature; muốn truy cập member không public còn liên quan quyền truy cập/module.
- Khi `newInstance` gọi constructor mà constructor ném exception, Reflection thường cung cấp `InvocationTargetException`; cần xem `getCause()` để biết lỗi constructor thật.

Để kiểm chứng thứ tự, dùng class có static block in một dòng và constructor in một dòng khác. Không sử dụng side effect của static initializer như đồng hồ đo kiểm tra tính đúng; thứ tự có thể bị ảnh hưởng bởi các thao tác kích hoạt initialization khác trong chương trình.

## 7. Ví dụ hoàn chỉnh 2 — tự xây classfile nhị phân đúng cấu trúc

Trong ví dụ thứ hai, ta **không biên dịch source**. Ta tạo các byte theo JVM Class File Format rồi đưa vào một `ClassLoader` riêng. Lớp được tạo có tên nhị phân `runtime.GeneratedMultiplier`:

~~~java
package runtime;

public class GeneratedMultiplier {
    public GeneratedMultiplier() {
        super();
    }

    public int twice(int value) {
        return value * 2;
    }
}
~~~

Đây là **mã nguồn tương đương về hành vi**, **không cần tạo thành file riêng**. Chương trình dưới đây tự tạo classfile có constructor và method `twice` ở mức bytecode, không dùng source trên.

Tạo file **HandmadeBytecodeDemo.java**:

~~~java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.lang.invoke.MethodHandle;
import java.lang.invoke.MethodHandles;
import java.lang.invoke.MethodType;
import java.lang.reflect.Method;
import java.nio.ByteBuffer;

public class HandmadeBytecodeDemo {
    private static final String BINARY_NAME =
            "runtime.GeneratedMultiplier";

    static class ByteLoader extends ClassLoader {
        ByteLoader(ClassLoader parent) {
            super(parent);
        }

        Class<?> define(byte[] classfile) {
            return defineClass(
                    BINARY_NAME, classfile, 0, classfile.length);
        }
    }

    // Constant-pool helpers.
    static void utf8(DataOutputStream out, String value)
            throws IOException {
        out.writeByte(1);     // CONSTANT_Utf8
        out.writeUTF(value);  // modified UTF-8 length + payload
    }

    static void cpClass(DataOutputStream out, int nameIndex)
            throws IOException {
        out.writeByte(7);     // CONSTANT_Class
        out.writeShort(nameIndex);
    }

    static void nameAndType(
            DataOutputStream out, int nameIndex, int typeIndex)
            throws IOException {
        out.writeByte(12);    // CONSTANT_NameAndType
        out.writeShort(nameIndex);
        out.writeShort(typeIndex);
    }

    static void methodRef(
            DataOutputStream out, int ownerIndex, int nameTypeIndex)
            throws IOException {
        out.writeByte(10);    // CONSTANT_Methodref
        out.writeShort(ownerIndex);
        out.writeShort(nameTypeIndex);
    }

    static void writeMethod(
            DataOutputStream out,
            int flags,
            int nameIndex,
            int descriptorIndex,
            byte[] code,
            int maxStack,
            int maxLocals) throws IOException {
        out.writeShort(flags);
        out.writeShort(nameIndex);
        out.writeShort(descriptorIndex);
        out.writeShort(1); // one method attribute: Code

        out.writeShort(9);  // "Code" in constant pool
        out.writeInt(12 + code.length);
        out.writeShort(maxStack);
        out.writeShort(maxLocals);
        out.writeInt(code.length);
        out.write(code);
        out.writeShort(0); // exception_table_length
        out.writeShort(0); // Code.attributes_count
    }

    static byte[] buildClassfile() throws IOException {
        ByteArrayOutputStream memory = new ByteArrayOutputStream();
        DataOutputStream out = new DataOutputStream(memory);

        out.writeInt(0xCAFEBABE);
        out.writeShort(0);   // minor version
        out.writeShort(61);  // major: Java 17
        out.writeShort(12);  // constant_pool_count, indexes 1..11

        // #1 Utf8 runtime/GeneratedMultiplier
        utf8(out, "runtime/GeneratedMultiplier");
        // #2 Class #1
        cpClass(out, 1);
        // #3 Utf8 java/lang/Object
        utf8(out, "java/lang/Object");
        // #4 Class #3
        cpClass(out, 3);
        // #5 Utf8 <init>
        utf8(out, "<init>");
        // #6 Utf8 ()V
        utf8(out, "()V");
        // #7 NameAndType #5:#6
        nameAndType(out, 5, 6);
        // #8 Methodref #4:#7 = Object.<init>:()V
        methodRef(out, 4, 7);
        // #9 Utf8 Code
        utf8(out, "Code");
        // #10 Utf8 twice
        utf8(out, "twice");
        // #11 Utf8 (I)I
        utf8(out, "(I)I");

        out.writeShort(0x0021); // ACC_PUBLIC | ACC_SUPER
        out.writeShort(2);      // this_class = #2
        out.writeShort(4);      // super_class = #4
        out.writeShort(0);      // interfaces_count
        out.writeShort(0);      // fields_count
        out.writeShort(2);      // methods_count

        // public <init>()V:
        //   aload_0; invokespecial #8; return
        byte[] constructor = {
                (byte) 0x2A, (byte) 0xB7, 0x00, 0x08, (byte) 0xB1
        };
        writeMethod(out, 0x0001, 5, 6, constructor, 1, 1);

        // public twice(I)I:
        //   iload_1; iconst_2; imul; ireturn
        byte[] twice = {
                (byte) 0x1B, (byte) 0x05,
                (byte) 0x68, (byte) 0xAC
        };
        writeMethod(out, 0x0001, 10, 11, twice, 2, 2);

        out.writeShort(0); // class attributes_count
        out.flush();
        return memory.toByteArray();
    }

    public static void main(String[] args) throws Throwable {
        byte[] classfile = buildClassfile();

        System.out.printf("magic: %08X%n",
                ByteBuffer.wrap(classfile).getInt());
        System.out.println("major: " +
                Short.toUnsignedInt(
                        ByteBuffer.wrap(classfile, 6, 2).getShort()));

        ByteLoader loader = new ByteLoader(
                HandmadeBytecodeDemo.class.getClassLoader());
        Class<?> generated = loader.define(classfile);

        System.out.println("defined: " + generated.getName());
        System.out.println("custom loader: " +
                (generated.getClassLoader() == loader));

        Object instance = generated.getDeclaredConstructor().newInstance();
        System.out.println("instance: " +
                instance.getClass().getName());

        Method twice = generated.getMethod("twice", int.class);
        System.out.println("reflect: " + twice.invoke(instance, 21));

        MethodHandle handle = MethodHandles.publicLookup().findVirtual(
                generated,
                "twice",
                MethodType.methodType(int.class, int.class));
        System.out.println("handle: " +
                handle.invokeWithArguments(instance, 15));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac HandmadeBytecodeDemo.java
java HandmadeBytecodeDemo
~~~

Stdout dự kiến:

~~~text
magic: CAFEBABE
major: 61
defined: runtime.GeneratedMultiplier
custom loader: true
instance: runtime.GeneratedMultiplier
reflect: 42
handle: 30
~~~

### Đối chiếu bytecode với hành vi thực tế

**Từ mảng byte đến Class:** `buildClassfile()` viết header, constant pool và hai method_info entries. `ByteLoader.define(classfile)` nạp các byte đó vào loader mới, cho JVM định nghĩa named class `runtime.GeneratedMultiplier`. Lệnh in `defined` chỉ chứng minh class tồn tại; lệnh in `custom loader` xác nhận defining loader chính là `ByteLoader` vừa tạo.

**Constructor:** `public <init>()V` dùng `aload_0` để đưa receiver chưa khởi tạo lên operand stack, `invokespecial #8` gọi `java/lang/Object.<init>:()V`, rồi `return`. Không có lời gọi superclass constructor, classfile của một instance class bình thường sẽ vi phạm quy tắc khởi tạo object.

**Method `twice`:** descriptor `(I)I` nghĩa là một `int` vào và một `int` ra. Vì là instance method, `max_locals=2` dành slot 0 cho `this` và slot 1 cho `value`. `iload_1` đưa `value` lên stack; `iconst_2` đưa hằng số 2; `imul` nhân; `ireturn` trả kết quả.

**max_stack:** `twice` cần tối đa 2 phần tử (`value` và `2` trước `imul`). Constructor cần tối đa 1 tham chiếu receiver trước `invokespecial`. Các giá trị này là **giới hạn stack slots**, không phải số lượng lệnh bytecode.

**Code attribute length:** phần cố định của Code attribute trong ví dụ là 12 byte cộng `code_length`, do `exception_table_length=0` và không có nested attributes. Vì vậy `writeMethod` dùng `out.writeInt(12 + code.length)`. Nếu sau này có exception table/attributes, phải **tính lại** độ dài đúng; không lấy công thức này dùng mù quáng.

**Reflection:** `getDeclaredConstructor().newInstance()` tạo instance; `getMethod("twice", int.class)` tìm public method; `Method.invoke(instance, 21)` trả một `Object` có giá trị nguyên boxing, nên in `42`.

**MethodHandle:** `findVirtual` tạo handle nhận receiver và `int`, trả `int`; `invokeWithArguments` chấp nhận truyền receiver và `15` dưới dạng đối số Java rồi chuyển đổi khi gọi. Kết quả được boxing thành `Integer` để trả về `Object` và in ra `30`.

### Vì sao ví dụ này hợp lệ dù không có StackMapTable?

Code của hai method **chỉ chạy tuyến tính, không branch**, không có exception handler hay merge của các luồng điều khiển. Với dạng rất nhỏ này, không có thêm stack-map frames cần ghi nhận tại các basic block khác. Với generated class có `if`, `switch`, vòng lặp, `try/catch`, stack types phức tạp hoặc object chưa khởi tạo đi qua nhánh, bạn cần hiểu các ràng buộc `StackMapTable`/verifier tương ứng. Trong production, dùng compiler/bytecode library tính frames thích hợp sẽ an toàn hơn.

### Tại sao chọn ClassLoader thay vì Lookup.defineClass?

Bytecode trên khai báo package `runtime`, trong khi `HandmadeBytecodeDemo` nằm ở default package. `Lookup.defineClass(classfile)` với lookup từ `HandmadeBytecodeDemo` sẽ không thỏa yêu cầu **cùng runtime package**. Một `ByteLoader` chuyên dụng có thể định nghĩa class có binary name `runtime.GeneratedMultiplier` mà chính nó chịu trách nhiệm quản lý, không cần lookup cùng package. Đây là lựa chọn theo **bối cảnh định nghĩa lớp**, không phải khác biệt “bytecode nào tốt hơn”.

## 8. Cấu trúc classfile tối giản của ví dụ thủ công

Có thể tóm tắt các phần đã ghi như sau:

~~~text
ClassFile {
  u4 magic = 0xCAFEBABE
  u2 minor_version = 0
  u2 major_version = 61
  u2 constant_pool_count = 12

  constant_pool[1..11]:
    #1  Utf8 "runtime/GeneratedMultiplier"
    #2  Class #1
    #3  Utf8 "java/lang/Object"
    #4  Class #3
    #5  Utf8 "<init>"
    #6  Utf8 "()V"
    #7  NameAndType #5:#6
    #8  Methodref #4:#7
    #9  Utf8 "Code"
    #10 Utf8 "twice"
    #11 Utf8 "(I)I"

  u2 access_flags = 0x0021
  u2 this_class = #2
  u2 super_class = #4
  u2 interfaces_count = 0
  u2 fields_count = 0
  u2 methods_count = 2

  method #1:
    access = public
    name = #5
    descriptor = #6
    Code:
      max_stack = 1
      max_locals = 1
      aload_0
      invokespecial #8
      return

  method #2:
    access = public
    name = #10
    descriptor = #11
    Code:
      max_stack = 2
      max_locals = 2
      iload_1
      iconst_2
      imul
      ireturn

  class attributes_count = 0
}
~~~

Đây là **sơ đồ cấu trúc** để đọc, không phải syntax mà JVM chấp nhận như source Java. `DataOutputStream` ghi số nguyên theo big-endian, phù hợp nhiều trường u2/u4 của JVM format. `writeUTF` sử dụng modified UTF-8 có tiền tố chiều dài u2, tương thích cách mã hóa `CONSTANT_Utf8_info` trong phạm vi chuỗi ASCII của ví dụ. Khi làm bytecode generator tổng quát, phải tuân thủ đầy đủ giới hạn chiều dài, cách mã hóa và các loại constant pool.

Lý do `constant_pool_count=12` chứ không phải `11`: slot `0` được dành riêng, nên 11 mục có chỉ số từ 1 tới 11 yêu cầu count bằng 12. Một lỗi off-by-one ở đây có thể khiến phần còn lại của classfile bị parser đọc lệch.

## 9. Inspect classfile mới tạo với javap như thế nào?

`javap` cần đọc classfile từ file hoặc classpath. Hai demo trên cố ý giữ bytecode **trong bộ nhớ**; vì vậy `javap -v -c GeneratedGreeter` không nhất thiết tìm thấy classfile vừa được tạo chỉ từ việc chương trình đã chạy.

Để kiểm tra phiên bản thủ công bằng `javap`, trong `main` của `HandmadeBytecodeDemo` có thể thêm các dòng sau **ngay sau** `byte[] classfile = buildClassfile();`, trước khi kết thúc chương trình:

~~~java
java.nio.file.Path output = java.nio.file.Path.of(
        "out", "runtime", "GeneratedMultiplier.class");
java.nio.file.Files.createDirectories(output.getParent());
java.nio.file.Files.write(output, classfile);
~~~

Đây là **đoạn tùy chọn**, không có sẵn trong chương trình gốc và sẽ ghi file trong thư mục `out` khi bạn chủ động thêm nó. Sau đó:

~~~bash
javac HandmadeBytecodeDemo.java
java HandmadeBytecodeDemo
javap -classpath out -p -c -v runtime.GeneratedMultiplier
~~~

Đọc `major version: 61`, các mục constant pool, phần method `twice` và chỉ thị `iload_1`, `iconst_2`, `imul`, `ireturn`. Không cần khớp số dòng in hay spacing của mọi bản `javap`; nội dung ngữ nghĩa của classfile mới là bằng chứng.

Có thể thử chế độ verification kỹ hơn:

~~~bash
java -Xverify:all HandmadeBytecodeDemo
~~~

Tùy phiên bản JDK, tùy chọn `-Xverify:all` có thể có cảnh báo về vòng đời hỗ trợ, nhưng ở JDK 17 vẫn được nhận. Việc class load và method chạy thành công cũng là một kiểm chứng thực dụng của bytecode trong ví dụ; tuy vậy, một lần chạy đúng với input nhỏ **không chứng minh mọi đường điều khiển** của generator tổng quát đều đúng.

### Lưu ý về file name và class name

File chứa mã **generator** là `HandmadeBytecodeDemo.java`; class được tạo có binary name **`runtime.GeneratedMultiplier`**. Bạn **không cần** có `runtime/GeneratedMultiplier.java` để chạy generator. Nếu xuất file `.class` ra đĩa để dùng `javap`, đặt nó dưới `out/runtime/GeneratedMultiplier.class` và thêm `out` làm classpath root cho `javap`.

Với ví dụ JavaCompiler, generated class `GeneratedGreeter` thuộc default package, còn code generator `CompileAndDefineDemo` cũng thuộc default package. Nếu đặt generator vào một named package, cần sửa tên binary của generated source cho khớp package và quyền lookup.

## 10. Định nghĩa một class nhiều lần và class-loader identity

Một loader không thể định nghĩa cùng một **binary name** nhiều lần. Nếu dùng cùng `ByteLoader` và gọi `define(classfile)` hai lần cho `runtime.GeneratedMultiplier`, lần thứ hai có thể gây `LinkageError` do trùng định nghĩa. Không nên “retry” bằng cách gọi lại y nguyên vào cùng loader sau khi class đã được định nghĩa.

Ngược lại, hai loader khác nhau có thể định nghĩa những class có cùng binary name:

~~~text
ByteLoader A → runtime.GeneratedMultiplier [Class A]
ByteLoader B → runtime.GeneratedMultiplier [Class B]

Class A.getName() == Class B.getName()  // true về chuỗi
Class A == Class B                       // false về identity
~~~

Sơ đồ là khái niệm. Hai kiểu khác nhau này không tự cast được sang nhau: một object từ class trong loader A không phải instance của class trong loader B chỉ vì tên hiển thị giống nhau. Các interface cha chung được tải bởi parent có thể dùng làm **hợp đồng giao tiếp** giữa plugin và host, nếu thiết kế delegation tương thích.

### Loader lifecycle và metaspace

Class đã định nghĩa không được xóa riêng bằng cách “set `Class<?> = null`”. JVM có thể thu hồi metadata của class khi **defining loader** cùng các đối tượng phụ thuộc không còn reachable và các điều kiện unloading được đáp ứng. Framework sinh hàng nghìn class khác tên trong một loader sống suốt vòng đời ứng dụng có thể tạo áp lực metaspace.

Vì vậy, khi định nghĩa class động:

- Tái sử dụng class đã tạo nếu ngữ nghĩa và isolation cho phép.
- Thiết kế vòng đời loader rõ ràng cho nhóm class/plugin có thể bỏ.
- Không cache vô hạn `Class<?>`, constructor, method handles hoặc các instance gắn với loader đã hết nhiệm vụ.
- Giám sát lỗi metaspace và số lượng class được định nghĩa; tránh chiến lược “một class mới cho mỗi request” nếu không cần thiết.

Đó là vấn đề **vòng đời runtime**, khác với tính hợp lệ của một classfile đơn lẻ.

## 11. Reflection và MethodHandle: gọi mã vừa định nghĩa

Vì mã nguồn của chương trình chủ chưa biết kiểu generated class ở compile time, ta thường nhận kết quả dưới kiểu `Class<?>`. Các lựa chọn gọi:

**Reflection:**

~~~java
Class<?> type = /* Class<?> đã define */;
Object instance = type.getDeclaredConstructor().newInstance();
Object value = type.getMethod("twice", int.class)
        .invoke(instance, 21);
~~~

Đoạn này là **minh họa**, yêu cầu biến `type` hợp lệ và xử lý các checked exceptions của Reflection. `getDeclaredConstructor()` tìm no-arg constructor; `newInstance()` gọi constructor; `Method.invoke` boxing kết quả primitive vào `Integer` để trả `Object`.

**MethodHandle:**

~~~java
MethodHandle twice = MethodHandles.publicLookup().findVirtual(
        type,
        "twice",
        MethodType.methodType(int.class, int.class));
Object value = twice.invokeWithArguments(instance, 21);
~~~

Đây cũng là **đoạn minh họa**, cần imports và biến `type`/`instance`. `findVirtual` trả handle có receiver làm tham số đầu, tức là về mô hình `(GeneratedMultiplier,int)int`. `invokeWithArguments` phù hợp với code động khi receiver chỉ biết kiểu `Object`. Nếu đã có kiểu Java rõ ràng ở compile time, `invokeExact` có thể dùng để kiểm soát chặt chữ ký, nhưng phải bảo đảm return type cũng khớp.

**Giao diện chung:** nếu class được tạo implement một interface có sẵn và interface ấy được tải trong class loader phù hợp, chương trình chủ có thể cast instance sang interface đó và gọi method trực tiếp. Đây là một thiết kế API thường đáng ưu tiên hơn việc reflection trên từng lần gọi, nhất là khi cần kiểm tra type tại compile time.

### Vì sao Method.invoke có thể ném InvocationTargetException?

Nếu method được gọi **tự ném ngoại lệ**, `Method.invoke` bọc ngoại lệ từ target vào `InvocationTargetException`. Muốn biết nguyên nhân đích, dùng `getCause()`. Những lỗi do tìm sai tên/signature (`NoSuchMethodException`), thiếu quyền (`IllegalAccessException`) hoặc sai args (`IllegalArgumentException`) thuộc **tầng Reflection**, không phải lỗi của method mới.

`MethodHandle` không bắt buộc bọc ngoại lệ target theo cùng cách đó; handle invocation truyền lỗi theo hợp đồng method handle. Phân biệt lớp lỗi giúp chẩn đoán chính xác “classfile hỏng”, “class load hỏng” và “code chạy nhưng nghiệp vụ ném lỗi”.

## 12. Lỗi theo giai đoạn: đọc stack trace ở đúng chỗ

| Giai đoạn | Ví dụ lỗi | Hướng xử lý |
| --- | --- | --- |
| **Generate/compile** | JavaCompiler báo syntax/type error | Đọc `DiagnosticCollector`; sửa source hoặc cấu hình release/classpath |
| **Parse classfile** | `ClassFormatError`, constant-pool index sai | Kiểm tra magic/version/count/attribute lengths/descriptor |
| **Verify bytecode** | `VerifyError`, stack types hoặc stackmap không hợp lệ | Kiểm tra operand stack, locals, control-flow joins và StackMapTable |
| **Phiên bản classfile** | `UnsupportedClassVersionError` | Sinh bytecode target tương thích JDK runtime, ví dụ major 61 cho Java 17 |
| **Định nghĩa tên class** | `NoClassDefFoundError` với thông báo tên không khớp, `LinkageError` trùng class | Xác nhận binary/internal name và class loader; không định nghĩa trùng trong cùng loader |
| **Lookup/package** | `IllegalArgumentException` hoặc `IllegalAccessException` theo ngữ cảnh Lookup API | Kiểm tra package của classfile, quyền PACKAGE và module của lookup |
| **Superclass/dependency** | `NoClassDefFoundError`, `IllegalAccessError` hoặc `IncompatibleClassChangeError` | Đảm bảo các class tham chiếu tồn tại và loader/module cho phép truy cập |
| **Class initialization** | `ExceptionInInitializerError`, hoặc lỗi từ initializer | Điều tra `<clinit>`; không xem đó là constructor failure |
| **Constructor lookup/invocation** | `NoSuchMethodException`, `IllegalAccessException`, `InvocationTargetException` | Kiểm tra signature và cause gốc của constructor |
| **Method lookup/invocation** | `NoSuchMethodException`, `WrongMethodTypeException`, `ClassCastException` | Kiểm tra method descriptor, receiver, dạng handle và call-site type |
| **Tài nguyên runtime** | `OutOfMemoryError: Metaspace` | Giảm tạo class vô hạn, xét lifecycle của defining loader |

Các tình huống trên là **nhóm lỗi điển hình**, không phải bảng ánh xạ duy nhất: JVM có quyền thực hiện một số bước linking lazily, nên lỗi phụ thuộc có thể xuất hiện khi truy cập member chứ không phải ngay `defineClass`. Một `VerifyError` vẫn có thể bị phát hiện bởi VM tại thời điểm mà code ứng dụng thấy là lần dùng class đầu tiên.

### Không catch Throwable rồi bỏ qua

Lỗi trong chuỗi này có cả `Error` thuộc nhóm `LinkageError`, `VerifyError` và `OutOfMemoryError`. Không nên bắt tất cả rồi tự động sinh bytes khác và retry vô hạn; có thể để JVM ở trạng thái có class đã định nghĩa một phần hoặc làm rối ownership/tên class.

Với runtime framework, ghi log đủ **binary name, defining loader, classfile major version, bước đang làm và root cause**. Nếu bytecode có thể chứa dữ liệu bí mật (constant pool strings), không log toàn bộ nội dung byte[] vào hệ thống giám sát.

## 13. Quy trình kiểm thử một generator: từ bytes tới hành vi

Một generator đáng tin không thể chỉ test “mảng bytes không rỗng”. Nên thiết kế kiểm thử theo nhiều tầng:

1. **Kiểm tra header và phiên bản:** magic `CAFEBABE`, major/minor đúng, byte[] không bị cắt.
2. **Kiểm tra cấu trúc:** constant pool indexes/tags, names, descriptors, attribute lengths; khi có công cụ, dump `javap -v -c` để thấy code.
3. **Kiểm tra verifier bằng JVM thật:** định nghĩa class trong loader cô lập, thử chạy với verification đầy đủ khi phù hợp; test cả đường có nhánh và exception handlers nếu generator hỗ trợ.
4. **Kiểm tra identity và quyền:** tên, package, loader, superclass, interfaces và khả năng truy cập từ mã gọi.
5. **Kiểm tra initialization:** static initializer chạy ở thời điểm dự kiến; không chạy lặp trong cùng definition.
6. **Kiểm tra constructor:** số lượng/kiểu tham số đúng, object được tạo có trạng thái mong muốn; trường hợp thiếu constructor phải báo rõ.
7. **Kiểm tra method:** input/output và ngoại lệ của method mới, bao gồm primitive, reference, null, biên số và điều kiện không hợp lệ.
8. **Kiểm tra cleanup:** lifecycle loader và class metadata nếu generator tạo nhiều lớp.
9. **Kiểm tra phiên bản:** chạy trên JDK runtime thấp nhất được hỗ trợ và dùng đúng target version.

Với một class `twice(I)I` đơn giản, test ít nhất `twice(0)==0`, `twice(1)==2`, `twice(-3)==-6`, đồng thời nhận biết **overflow `int`** theo ngữ nghĩa Java nếu đầu vào lớn. Code có type đúng nhưng tính sai vẫn là lỗi generator hoặc lỗi mô hình nghiệp vụ.

### Test âm cần biết, nhưng không coi là ví dụ hợp lệ

Một số thay đổi cố ý phá classfile để xem JVM kiểm tra:

- Đổi một byte của magic `CAFEBABE` → classfile không còn header chuẩn.
- Đổi `major_version` thành số cao hơn runtime hỗ trợ → `UnsupportedClassVersionError`.
- Tăng `constant_pool_count` lên một nhưng không thêm phần tử → classfile bị parse lệch.
- Đặt `invokespecial` trỏ tới một constant pool entry sai loại → lỗi cấu trúc/linking/verifier.
- Dùng `ireturn` khi operand stack chỉ có reference → verification failure.

Các ca này chỉ nên làm trong **test process/loader tách biệt** và coi là đầu vào cố ý không hợp lệ. Không đưa classfile lỗi vào luồng chạy production và không xem việc một JVM phiên bản cụ thể báo lỗi ở thời điểm nào là hợp đồng duy nhất.

## 14. Các quyết định thiết kế trong ứng dụng thật

### A. Tránh tự viết toàn bộ classfile nếu không cần

Ví dụ thủ công chỉ có một class, một constructor và một phép nhân. Chỉ cần thêm branching, generic signatures, annotations, interfaces, exception handlers, stack-map frames, fields, records hoặc invokedynamic là số trạng thái cần quản lý tăng nhiều. Dùng JavaCompiler nếu có thể mô tả source, hoặc thư viện sinh bytecode tin cậy khi cần tối ưu/biến đổi trực tiếp bytecode.

### B. Không chạy mã không tin cậy như “sandbox” chỉ vì dùng loader riêng

Tạo một `ClassLoader` mới **không làm mã đó an toàn**. Khi đã được nạp và chạy trong cùng JVM, mã có thể sử dụng các API được cấp quyền theo môi trường; Security Manager truyền thống không còn là mô hình sandbox đáng dựa vào ở các phiên bản Java hiện đại. Nếu chạy code không tin cậy, cần thiết kế cách ly ở mức process/container/OS, quyền tài nguyên, giới hạn CPU/memory/time và cơ chế xác thực đầu vào phù hợp.

Kiểm chứng bytecode giúp an toàn kiểu và tính đúng cấu trúc JVM, **không có nghĩa mã được định nghĩa không thể thực hiện hành động nguy hiểm**.

### C. Cẩn thận với package/module và library version

`Lookup.defineClass` chịu ràng buộc package/module của lookup. `ClassLoader.defineClass` cần loader thích hợp và có thể đụng class visibility, sealing, package signer hoặc module boundary. Khi một generated class gọi thư viện của host, hai bên phải cùng nhìn thấy kiểu giao tiếp có identity tương thích.

Nếu framework dùng nhiều plugin loader, đừng truyền một object của “cùng tên class” rồi tin cast luôn hoạt động. Kiểm tra actual loader chain và interface contract.

### D. Đặt tên class có chủ đích và cache hợp lý

Một class tên cố định nên được định nghĩa **một lần trong một loader**. Nếu thay đổi mã từng thế hệ, có thể dùng loader mới hoặc tên phiên bản khác theo thiết kế. Cần cân nhắc metaspace/caches để không tăng số class không giới hạn. Không dùng tên do người dùng cung cấp một cách trực tiếp mà thiếu validation và namespace policy.

### E. Không phụ thuộc trình tự side effect khó dự đoán

Trong ví dụ thứ nhất, thứ tự rõ ràng vì code gọi `Class.forName(..., true, ...)` trước constructor và log. Trong môi trường có nhiều luồng, class initialization có cơ chế đồng bộ hóa riêng của JVM; không tự khởi tạo cùng class vô hạn hay dùng static block cho công việc có side effect khó phục hồi. Framework nên kiểm soát khởi tạo runtime qua API/constructor rõ ràng khi có thể.

## 15. Phân biệt các cách “chạy mã mới” sau khi define

| Cách | Ưu điểm | Nhược điểm/điều kiện |
| --- | --- | --- |
| `Constructor.newInstance(...)` rồi `Method.invoke(...)` | Hoạt động khi chỉ có `Class<?>`, dễ đọc và debug | Lookup theo tên/signature ở runtime, kết quả boxing, ngoại lệ target bọc trong InvocationTargetException |
| `MethodHandles.Lookup.findVirtual/findStatic` | Mô hình typed handles, dễ dựng adapter/call chains | Phải khớp `MethodType` và quyền Lookup; `invokeExact` nghiêm ngặt |
| Cast sang interface đã biết | Type safety tốt ở source, API dễ sử dụng | Generated class phải implement đúng interface với loader identity tương thích |
| Static method qua Reflection/handle | Không cần tạo instance để gọi static code | Lớp cần initialization theo quy tắc JVM trước active use; lỗi linkage/initializer vẫn có thể xảy ra |
| `MethodHandles.Lookup.findConstructor` | Có thể biểu diễn constructor bằng MethodHandle | Signature handle constructor trả kiểu object; cần quản lý quyền và chuyển kiểu |

**Định nghĩa class** chỉ là bước cho JVM biết kiểu mới. Để thực thi mã mới, caller vẫn phải chọn **constructor/method tương ứng**, có object nếu là instance method, đáp ứng quyền và kiểu, và xử lý ngoại lệ khi chạy.

Nếu biết sẵn interface ở compile time, một chiến lược bền vững là compiler/generator tạo class **implements interface**, rồi tạo object và cast về interface. Nếu không biết shape, Reflection/MethodHandles giúp thao tác mềm dẻo nhưng chuyển nhiều lỗi từ compile time sang runtime.

## 16. Các câu hỏi thực hành và đáp án

**1. `byte[]` có bốn byte đầu `CAFEBABE` đã đủ để gọi `defineClass` thành công chưa?**  
Chưa. Đây chỉ là magic; constant pool, version, metadata, Code attributes và verifier constraints đều phải hợp lệ.

**2. Java 17 dùng major classfile version nào?**  
Major version `61`. Một runtime cũ không hỗ trợ version đó sẽ không nạp classfile Java 17.

**3. `Lookup.defineClass(bytes)` có tự chạy static initializer không?**  
Không theo hợp đồng API. Cần thao tác kích hoạt initialization, ví dụ `Class.forName(name, true, loader)`.

**4. `Class<?>` và object generated khác nhau thế nào?**  
`Class<?>` biểu diễn định nghĩa kiểu; object là instance được tạo qua constructor hoặc một cơ chế tạo đối tượng thích hợp.

**5. Vì sao `Lookup.defineClass` không thể tùy tiện nạp bytecode ở package khác với lookup?**  
API yêu cầu class được định nghĩa cùng runtime package dưới quyền lookup phù hợp; không phải một entrypoint nạp class vào package bất kỳ.

**6. Dùng `ClassLoader#defineClass` có bỏ qua bytecode verifier được không?**  
Không. JVM vẫn kiểm tra cấu trúc, quyền, tính tương thích bytecode và class linking.

**7. Vì sao class `runtime.GeneratedMultiplier` có `max_locals=2` cho `twice(int)`?**  
Vì đây là instance method: slot 0 là `this`, slot 1 là đối số `int`.

**8. Vì sao constructor bytecode phải gọi `Object.<init>`?**  
Instance constructor cần tuân thủ quy tắc khởi tạo superclass và receiver. Code của ví dụ dùng `aload_0; invokespecial Object.<init>; return`.

**9. Tại sao `constant_pool_count` bằng 12 nhưng có 11 entries?**  
Constant-pool index 0 không sử dụng, entries mang số 1..11.

**10. `Class.forName(name, true, loader)` khác `Class.forName(name, false, loader)` ở đâu?**  
`true` yêu cầu initialization; `false` không yêu cầu khởi tạo ngay chỉ từ lời gọi đó.

**11. Hai class cùng binary name trong hai loader có được xem là một kiểu không?**  
Không. Type identity của class JVM phụ thuộc **tên và defining loader**; cùng tên text không đủ.

**12. Vì sao `Method.invoke` trả Object dù method generated trả `int`?**  
Reflection API có return type `Object`; giá trị primitive được boxing thành wrapper thích hợp.

**13. Khi constructor generated ném lỗi, `newInstance` có thể báo gì?**  
`InvocationTargetException` với nguyên nhân gốc trong `getCause()`; cần phân biệt với lỗi tìm constructor hoặc thiếu quyền.

**14. `MethodHandle.findVirtual` của `twice(int)int` nhận bao nhiêu tham số?**  
Hai khi handle chưa bind receiver: receiver generated class và một `int`. Về mô hình là `(GeneratedMultiplier,int)int`.

**15. Khi nào nên dùng `javap`?**  
Để đọc classfile/bytecode sau khi xuất bytes ra file hoặc có class trên classpath. `javap` không tự đọc Class<?> vừa được tạo trong một JVM khác.

**16. Có thể dùng class loader mới để chạy bytecode độc hại một cách an toàn không?**  
Không. Loader riêng không tự tạo sandbox an ninh; cần cách ly tài nguyên/quyền thực sự.

**17. Bắt `Throwable` rồi retry define lại ngay có hợp lý không?**  
Không. Phải phân loại lỗi generator, duplicate name, verifier, linkage, initializer và lỗi runtime. Retry sai có thể làm hỏng trạng thái hoặc tăng số lớp.

**18. Nếu mỗi request lại define một class mới trong loader sống lâu, có vấn đề gì?**  
Có nguy cơ tăng metadata/metaspace và gây khó unload; nên cache generator outputs hoặc thiết kế vòng đời loader có kiểm soát.

## 17. Checklist triển khai tuần tự

- [ ] Xác định **binary name**, package, target JDK major version, superclass/interfaces và method signatures.
- [ ] Chọn cách tạo bytecode: JavaCompiler, bytecode library hoặc builder thủ công nếu thật sự có lý do.
- [ ] Tạo **byte[] đầy đủ**, không cắt nửa chừng; kiểm tra magic/version/cấu trúc nếu cần.
- [ ] Nếu tự dựng classfile: rà soát constant pool indexes, descriptors, max_stack/max_locals, Code lengths, control flow/stack maps.
- [ ] Chọn **defining loader/lookup** phù hợp package/module/quyền truy cập; không định nghĩa tên trùng trong cùng loader.
- [ ] Gọi `defineClass` và giữ `Class<?>` được trả về; phân biệt với object instance.
- [ ] Yêu cầu initialization tại thời điểm mong muốn, theo dõi static initializer và lỗi liên quan.
- [ ] Tìm **constructor đúng signature**, tạo instance và xử lý nguyên nhân nếu constructor ném lỗi.
- [ ] Tìm/gọi **method đúng signature** qua interface, Reflection hoặc MethodHandle; đảm bảo receiver/return type khớp.
- [ ] Kiểm thử giá trị đầu vào/đầu ra và exceptions của mã mới; không coi “define thành công” là chứng minh logic đúng.
- [ ] Giám sát classloader lifecycle, class name collisions, caching và metaspace.
- [ ] Không xem verification/classloader là sandbox để chạy mã không tin cậy.

## 18. Kết luận

Chuỗi tạo và thực thi mã động trong JVM gồm **bốn ranh giới chính**:

1. **Tạo bytes hợp lệ:** xuất classfile đúng format, version và bytecode verification rules.
2. **Định nghĩa class:** chọn `Lookup.defineClass` hoặc `ClassLoader.defineClass` theo package/module/loader; nhận `Class<?>`.
3. **Khởi tạo class và object:** phân biệt `<clinit>`, `<init>`, `Class.forName` và constructor.
4. **Thực thi mã mới:** gọi method bằng Reflection, MethodHandle hoặc interface với kiểu và quyền phù hợp.

Hai chương trình Java 17+ đã minh họa cả đường **compiler tạo classfile** lẫn đường **tự ghi bytecode từ đầu**, đều đi tới việc tạo instance và gọi method trên class vừa định nghĩa. Khi hiểu các ranh giới này, bạn có thể đọc stack trace đúng giai đoạn, tránh nhầm classfile với object, và thiết kế runtime code generation vừa kiểm chứng được vừa quản lý được vòng đời.
