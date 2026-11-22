# Tệp class là biểu diễn nhị phân có thể tồn tại dưới dạng byte trong bộ nhớ

## 1. Một tệp `.class` có nhất thiết phải là một file trên đĩa?

**Không.** Trong Java, điều cốt lõi của **class-file format** là **một chuỗi byte có cấu trúc được Java Virtual Machine Specification quy định**. Đuôi `.class` là cách phổ biến để **lưu** chuỗi byte ấy thành tệp trên hệ thống file, không phải điều kiện duy nhất để biểu diễn hoặc nạp một lớp.

Ví dụ cùng một định nghĩa lớp có thể đi qua những dạng lưu trữ khác nhau:

~~~text
Mã Java                         bytecode dạng class-file
   |                                     |
   v                                     v
javac / compiler             CA FE BA BE 00 00 00 3D ...
   |                                     |
   +------> trên đĩa: MyType.class       |
   +------> trong JAR/ZIP entry          |
   +------> trong byte[] ở heap          |
   +------> trong ByteArrayOutputStream  |
   +------> bytes từ mạng/cache/DB       |
   +------> bytes tạo bởi thư viện       |
                                         v
                           ClassLoader.defineClass(...)
                                         |
                                         v
                              Class<?> trong JVM
~~~

Không nên diễn đạt “JVM chạy file `.class` trên đĩa”. JVM định nghĩa một lớp từ **biểu diễn hợp lệ theo class-file format** do cơ chế nạp lớp cung cấp; biểu diễn đó có thể bắt nguồn từ đĩa, JAR, mạng, dữ liệu sinh động hoặc bộ nhớ. Bước cuối tạo nên một đối tượng `Class<?>` và thông tin runtime mà JVM quản lý; chúng **không phải chính mảng `byte[]` ban đầu**.

**Phân biệt ba khái niệm ngay từ đầu:**

- **`class-file bytes`:** nội dung nhị phân theo một định dạng xác định, có thể nằm trong `byte[]`.
- **Tệp `Something.class`:** một **vật chứa trên file system** có nội dung là các byte nói trên; tệp có thể không tồn tại.
- **Lớp đã được JVM định nghĩa:** kiểu runtime do một defining class loader tạo ra, được biểu diễn qua `Class<?>`; không đồng nhất với bản sao bytes hoặc một file.

Định nghĩa này dùng được với class, interface và các biểu diễn liên quan mà JVMS mô tả, không riêng `public class` thông thường.

## 2. Một class-file thực sự chứa gì?

Theo **Java Virtual Machine Specification, chương 4**, class file là một chuỗi byte 8-bit. Các đại lượng nhiều byte được lưu theo **big-endian** (byte có trọng số cao trước). Các ký hiệu chuẩn là `u1`, `u2`, `u4`: giá trị không dấu chiếm 1, 2, 4 byte.

Khung tổng quát của `ClassFile`:

~~~text
ClassFile {
    u4 magic;
    u2 minor_version;
    u2 major_version;
    u2 constant_pool_count;
    cp_info constant_pool[constant_pool_count - 1];
    u2 access_flags;
    u2 this_class;
    u2 super_class;
    u2 interfaces_count;
    u2 interfaces[interfaces_count];
    u2 fields_count;
    field_info fields[fields_count];
    u2 methods_count;
    method_info methods[methods_count];
    u2 attributes_count;
    attribute_info attributes[attributes_count];
}
~~~

Đây là **cấu trúc mô tả trong đặc tả**, không phải khai báo C hay Java có thể biên dịch. Các mục được mã hóa nối tiếp theo định dạng class-file, không phải một struct native với alignment của hệ điều hành.

| Phần | Vai trò |
| --- | --- |
| `magic` | Bốn byte đầu nhận diện định dạng: `CA FE BA BE` |
| `minor_version`, `major_version` | Phiên bản class-file mà JVM phải hỗ trợ |
| `constant_pool_count` / `constant_pool` | Bảng hằng và tham chiếu tượng trưng: class, tên, descriptor, string, method handle... |
| `access_flags` | Các cờ truy cập/đặc điểm của kiểu |
| `this_class`, `super_class` | Tham chiếu bảng hằng cho class hiện tại và class cha, theo ràng buộc JVMS |
| `interfaces` | Các interface được khai báo |
| `fields` | Các field và metadata của chúng |
| `methods` | Các method và các attribute; bytecode của method thường ở attribute `Code` |
| `attributes` | Metadata của class, chẳng hạn thông tin nguồn, annotation, nest/record/module... khi có |

**Phần header có offset cố định** khi đọc từ đầu mảng:

| Offset tính từ 0 | Độ dài | Mục | Ví dụ class Java 17 |
| --- | --- | --- | --- |
| 0–3 | 4 byte | `magic` | `CA FE BA BE` |
| 4–5 | 2 byte | `minor_version` | `00 00` |
| 6–7 | 2 byte | `major_version` | `00 3D` (61 thập phân) |
| 8–9 | 2 byte | `constant_pool_count` | Thay đổi theo nội dung class |
| Từ 10 | Biến thiên | `constant_pool` rồi các phần tiếp theo | Không có offset cố định chung |

Không được giả định `methods_count` luôn ở một offset cố định: các entry trong constant pool có kích thước khác nhau, và các bảng trung gian cũng dài biến thiên. Ví dụ `CONSTANT_Long_info` và `CONSTANT_Double_info` còn chiếm **hai chỉ số** trong constant pool. Vì vậy `constant_pool_count - 1` **không nên diễn giải máy móc** là số object Java hoặc số bytecode instruction.

### 2.1. Vì sao `CA FE BA BE` quan trọng nhưng không đủ?

Bốn byte `CA FE BA BE` ở vị trí đầu là **magic number**. Nó giúp nhận diện nhanh dữ liệu có thể thuộc class-file format. Tuy nhiên:

- Mảng chỉ có bốn byte magic **không phải** một class file hợp lệ.
- Header đúng nhưng constant pool sai, method descriptor sai hoặc code không đạt quy tắc verifier vẫn có thể bị JVM từ chối.
- Chỉ kiểm tra `major_version` không thay thế được kiểm tra toàn bộ cấu trúc và các ràng buộc của class file.
- Một luồng byte lấy từ nguồn không tin cậy phải được coi là đầu vào cần kiểm tra, không phải “an toàn” chỉ vì có magic đúng.

### 2.2. Major version thể hiện điều gì?

Một số mốc thông dụng:

| Java release | Class-file major |
| --- | --- |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 24 | 68 |

Bảng trên cho **phiên bản mặc định phù hợp** khi compiler phát class file cho release tương ứng. Ví dụ chạy `javac --release 17` trên JDK có hỗ trợ tùy chọn đó sẽ xuất class-file **major 61**, dù bản JDK chạy compiler có thể mới hơn.

Nếu đưa class major cao hơn phiên bản JVM hỗ trợ vào một JVM cũ hơn, có thể nhận `UnsupportedClassVersionError`. Đây là vấn đề **định dạng/khả năng runtime**, không phải chỉ đổi tên tệp từ `.class` sang `.bin` là khắc phục được. Một số trường hợp preview feature còn có quy tắc minor version riêng, không nên bỏ qua khi làm công cụ đọc class-file tổng quát.

## 3. Bytecode, class file, `Class<?>` và machine code không phải một thứ

Một lỗi khái niệm phổ biến là gọi mọi thứ liên quan đến class là “bytecode trong RAM”. Có ít nhất bốn tầng:

~~~text
Java source
    | javac / compiler
    v
Class-file bytes: header + constant pool + fields/methods/attributes
    | ClassLoader + JVM loading/linking
    v
Runtime class metadata + Class<?> mirror
    | execution / interpreter / JIT khi cần
    v
Hoạt động runtime: object, stack frame, JIT machine code (nếu có)
~~~

- **Java source** là văn bản như `public class Greeting { ... }`.
- **Class-file bytes** là biểu diễn nhị phân có cấu trúc. Trong nhiều method, phần `Code` chứa **JVM instructions**; toàn bộ class file còn có metadata, không chỉ instruction.
- **`Class<?>`** là một đối tượng Java phản ánh kiểu đã được định nghĩa trong JVM. Không phải một “view byte[]” của class file.
- **Machine code JIT** là kết quả tối ưu hóa tùy runtime và thời điểm, không phải nội dung `.class`. Một JVM có thể thực thi bytecode bằng interpreter mà không yêu cầu lưu file `.class` riêng cho mỗi lớp.

**Ví dụ:** Khi `ClassLoader#defineClass` nhận một `byte[]` hợp lệ, nó tạo kiểu runtime; việc gọi một static method của kiểu ấy có thể kích hoạt khởi tạo lớp. Bỏ tham chiếu tới mảng nguồn **không có nghĩa** lớp runtime sẽ tự biến mất ngay, cũng không bắt JVM biên dịch JIT ngay lập tức.

Từ “class file” trong đặc tả có thể chỉ **một biểu diễn ở định dạng class-file**, dù nó chưa từng được ghi ra filesystem. Đây chính là ý của đề bài.

## 4. Byte của class file có thể đến từ đâu?

| Nguồn | Dữ liệu tại điểm JVM/công cụ nhận | Ví dụ sử dụng |
| --- | --- | --- |
| Tệp vật lý `.class` | Đọc tệp thành mảng hoặc stream byte | `Files.readAllBytes(path)` |
| JAR/JMOD và các dạng gói phù hợp | Đọc entry/resource thành bytes | Classpath hoặc cơ chế module |
| Compiler chạy trong chính ứng dụng | Mảng bytes do `javax.tools.JavaCompiler` trả qua file manager tùy biến | Plugin, rule engine, code generation |
| Thư viện tạo bytecode | Một `byte[]` hoàn chỉnh theo JVMS | Proxy/codegen và công cụ build |
| Hệ thống khác cung cấp dữ liệu | Bytes được truyền qua IPC, mạng, cache hoặc cơ sở dữ liệu | Loader/plugin tùy biến có xác thực |
| Java agent/transformer | `classfileBuffer` do JVM cung cấp ở callback | Quan sát hoặc tạo bytes đã biến đổi |

Một cách đơn giản nhất để có bytes là:

~~~java
byte[] classBytes = java.nio.file.Files.readAllBytes(
        java.nio.file.Path.of("Example.class"));
~~~

Đây chỉ là **mảnh code có thể đặt trong phương thức khai báo/handle `IOException`**. Nó vẫn **đọc từ đĩa**, sau đó đưa nội dung vào một `byte[]`. Muốn chứng minh **không cần ghi file class được sinh ra**, ví dụ ở mục tiếp theo sẽ compile trong bộ nhớ, chặn đường ghi output bằng file manager riêng.

Ngược lại, đừng suy rằng **mọi** class đang chạy đều có thể truy xuất lại chính xác nguyên bản `byte[]` của lần load. `Class<?>` không cung cấp một phương thức chuẩn “getOriginalClassFileBytes()”. Class có thể đã được transform, sinh động, bị ẩn sau class loader hoặc thiếu resource trên đĩa.

## 5. Ví dụ độc lập Java 17+: biên dịch một lớp thành `byte[]` mà không ghi `.class` của lớp đó ra đĩa

Bài thực hành dùng **JavaCompiler API** (module `java.compiler`) và một `ForwardingJavaFileManager` tùy biến. Nguồn Java của lớp đích được chứa trong một `String`, output compiler được nhận vào `ByteArrayOutputStream`, sau đó truyền `byte[]` cho custom `ClassLoader#defineClass`.

**Mục đích của ví dụ:** cho thấy lớp `demo.MemoryHello` có thể được biên dịch và nạp trong **một lần chạy JVM**, dù không tạo tệp `demo/MemoryHello.class` trên filesystem. Bản thân `InMemoryClassDemo.class` — chương trình chạy thử — vẫn được `javac` biên dịch theo cách thông thường để khởi chạy. Không được diễn đạt rằng “toàn bộ JDK không hề đọc file nào”.

### 5.1. Mã nguồn đầy đủ

**Tệp: `InMemoryClassDemo.java`**

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.net.URI;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class InMemoryClassDemo {
    private static final class Source extends SimpleJavaFileObject {
        private final String source;
        Source(String name, String source) {
            super(URI.create("string:///" + name.replace('.', '/')
                    + Kind.SOURCE.extension), Kind.SOURCE);
            this.source = source;
        }
        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return source;
        }
    }

    private static final class ByteCode extends SimpleJavaFileObject {
        private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        ByteCode(String name, Kind kind) {
            super(URI.create("memory:///" + name.replace('.', '/')
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
            extends ForwardingJavaFileManager<JavaFileManager> {
        private final Map<String, ByteCode> compiled = new HashMap<>();
        MemoryFiles(JavaFileManager base) {
            super(base);
        }
        @Override
        public JavaFileObject getJavaFileForOutput(
                Location location, String className,
                JavaFileObject.Kind kind, FileObject sibling) throws IOException {
            ByteCode code = new ByteCode(className, kind);
            compiled.put(className, code);
            return code;
        }
        byte[] bytesFor(String name) {
            ByteCode code = compiled.get(name);
            if (code == null) {
                throw new IllegalStateException("No compiled class: " + name);
            }
            return code.toByteArray();
        }
    }

    private static final class MemoryLoader extends ClassLoader {
        MemoryLoader() {
            super(ClassLoader.getPlatformClassLoader());
        }
        Class<?> define(String binaryName, byte[] bytes) {
            return defineClass(binaryName, bytes, 0, bytes.length);
        }
    }

    public static void main(String[] args) throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException(
                    "Run with a JDK, not a minimal JRE");
        }
        String binaryName = "demo.MemoryHello";
        String source = "package demo; public class MemoryHello { "
                + "public static String message() { "
                + "return \"Hello from RAM\"; } }";
        DiagnosticCollector<JavaFileObject> diagnostics =
                new DiagnosticCollector<>();
        byte[] classBytes;

        try (StandardJavaFileManager standard =
                     compiler.getStandardFileManager(
                             diagnostics, Locale.ROOT, StandardCharsets.UTF_8);
             MemoryFiles memory = new MemoryFiles(standard)) {
            boolean success = Boolean.TRUE.equals(compiler.getTask(
                    null, memory, diagnostics, List.of("--release", "17"),
                    null, List.of(new Source(binaryName, source))).call());
            if (!success) {
                throw new IllegalStateException("Compilation failed: "
                        + diagnostics.getDiagnostics());
            }
            classBytes = memory.bytesFor(binaryName);
        }

        ByteBuffer header = ByteBuffer.wrap(classBytes)
                .order(ByteOrder.BIG_ENDIAN);
        long magic = Integer.toUnsignedLong(header.getInt());
        int minor = Short.toUnsignedInt(header.getShort());
        int major = Short.toUnsignedInt(header.getShort());
        int cpCount = Short.toUnsignedInt(header.getShort());
        System.out.printf("magic=%08X%n", magic);
        System.out.println("minor=" + minor);
        System.out.println("major=" + major);
        System.out.println("constantPoolCountPositive=" + (cpCount > 1));
        System.out.println("byteArrayNonEmpty=" + (classBytes.length > 0));

        MemoryLoader loader = new MemoryLoader();
        Class<?> type = loader.define(binaryName, classBytes);
        System.out.println("name=" + type.getName());
        System.out.println("customLoader=" + (type.getClassLoader() == loader));
        System.out.println("message="
                + type.getMethod("message").invoke(null));
    }
}
~~~

### 5.2. Biên dịch và chạy

Cần một **JDK đầy đủ** (không phải runtime image đã bỏ module compiler). Trên Java 17 hoặc bản JDK mới hơn hỗ trợ `--release 17`:

~~~bash
javac --release 17 InMemoryClassDemo.java
java InMemoryClassDemo
~~~

**Stdout chính xác của ví dụ**, đã được kiểm thử khi biên dịch với `--release 17` và chạy bằng JDK có compiler:

~~~text
magic=CAFEBABE
minor=0
major=61
constantPoolCountPositive=true
byteArrayNonEmpty=true
name=demo.MemoryHello
customLoader=true
message=Hello from RAM
~~~

Trong ví dụ này, `major=61` là hệ quả của `--release 17`; `minor=0` là bản không dùng preview feature. Nội dung constant pool có thể thay đổi theo compiler và optimization, nên ví dụ **không in giá trị số cụ thể** của `cpCount`, chỉ xác minh đây là một bảng có dữ liệu.

Nếu môi trường không có compiler module hoặc `ToolProvider.getSystemJavaCompiler()` trả `null`, đây là **giới hạn của môi trường chạy**, không chứng minh “class-file bắt buộc phải nằm trên đĩa”.

### 5.3. Phân tích từng bước trong ví dụ

**Bước 1 — `Source`:** `SimpleJavaFileObject` với `Kind.SOURCE` cung cấp nội dung Java từ một `String` qua `getCharContent`. URI `string:///...` đóng vai trò **định danh logical** của nguồn, không tự tạo file trên filesystem.

**Bước 2 — `ByteCode`:** Một `JavaFileObject` loại `CLASS` chấp nhận output qua `openOutputStream()` rồi giữ bytes trong `ByteArrayOutputStream`. URI `memory:///...` cũng chỉ là URI nhận diện output. Không có `FileOutputStream` hay `Files.write` cho lớp được sinh.

**Bước 3 — `MemoryFiles`:** Bằng cách override `getJavaFileForOutput(...)`, ta yêu cầu compiler ghi kết quả biên dịch vào đối tượng bộ nhớ. Map `compiled` liên kết **binary class name** với bytes. Trong hệ thống thực, nếu một source tạo nhiều class/nested class, file manager cần giữ và triển khai việc nạp/đọc **từng output** phù hợp.

**Bước 4 — `JavaCompiler.getTask`:** Compiler nhận nguồn `JavaFileObject`, file manager, diagnostics và tùy chọn `--release 17`. `call()` thực hiện compilation và trả `Boolean`; không suy ra thành công chỉ vì map đã có một số byte. Ví dụ kiểm tra thất bại và nêu diagnostics.

**Bước 5 — đọc header:** `ByteBuffer.wrap(classBytes)` cho phép đọc bytes đã có trong heap mà không cần mở file. Lệnh `getInt()` và `getShort()` đọc theo **big-endian**; `Integer.toUnsignedLong` và `Short.toUnsignedInt` giữ nghĩa không dấu của trường JVMS. Bốn byte magic được in dưới dạng hex bằng `%08X`.

**Bước 6 — `defineClass`:** `MemoryLoader` là class loader tùy biến, truyền `binaryName` cùng mảng bytes cho phương thức `ClassLoader#defineClass` (được bảo vệ/protected). JVM định nghĩa kiểu `demo.MemoryHello` từ dữ liệu ấy. Việc khởi tạo parent là platform class loader giúp lớp mới vẫn tham chiếu được Java platform classes và tránh phụ thuộc vào một file `demo/MemoryHello.class` trên application classpath.

**Bước 7 — thực thi:** `type.getMethod("message").invoke(null)` gọi static method của lớp vừa được định nghĩa, cho ra `Hello from RAM`. Lúc này JVM đã có kiểu runtime và thực thi method; đó là **bước khác** với sở hữu một `byte[]` chứa class-file format.

**Kết luận thực nghiệm:** chương trình chính có thể xuất hiện dưới dạng tệp `InMemoryClassDemo.class`, nhưng **lớp đích `demo.MemoryHello` không cần file `demo/MemoryHello.class`**. Bộ compiler và loader trao đổi class-file bytes ngay trong bộ nhớ.

## 6. Kiểm tra header đơn giản không đồng nghĩa viết parser class-file hoàn chỉnh

Đoạn rút gọn sau cho thấy ý tưởng đọc 10 byte đầu:

~~~java
if (bytes.length < 10) {
    throw new IllegalArgumentException("Too short for class-file header");
}
java.nio.ByteBuffer header = java.nio.ByteBuffer.wrap(bytes)
        .order(java.nio.ByteOrder.BIG_ENDIAN);
int magic = header.getInt();
int minor = Short.toUnsignedInt(header.getShort());
int major = Short.toUnsignedInt(header.getShort());
int cpCount = Short.toUnsignedInt(header.getShort());
if (magic != 0xCAFEBABE) {
    throw new IllegalArgumentException("Wrong class-file magic");
}
~~~

Đây là **mảnh code trong method có sẵn `byte[] bytes`**. Literal hex `0xCAFEBABE` là `int` Java có bit dấu, nhưng so sánh bit pattern vẫn đúng; ví dụ đầy đủ dùng `Integer.toUnsignedLong` để in dãy hex không dấu cho dễ đọc.

**Chỉ kiểm tra header là kiểm tra sơ bộ**: parser hoàn chỉnh còn phải hiểu các loại constant-pool entry, độ dài biến thiên, field/method descriptors, attributes, cấu trúc code và những ràng buộc của từng phiên bản. Việc tự “cắt byte ở offset nào đó” mà không biết JVMS rất dễ phá vỡ class file.

Khi chỉ muốn xem cấu trúc từ file đã biên dịch, có thể dùng công cụ JDK:

~~~bash
javap -verbose InMemoryClassDemo
~~~

`javap` giúp xem constant pool, major version, methods và các attribute mà tool hỗ trợ. Nhưng lưu ý nó đang đọc **class của chương trình demo** từ classpath. Để inspect bytes của `demo.MemoryHello` sinh trong RAM, bạn phải chủ động lưu những bytes đó ra một file để `javap` đọc **hoặc** dùng một API parser phù hợp trực tiếp trên `byte[]`.

Từ **JDK 24**, Java có `java.lang.classfile` chuẩn hóa để đọc/tạo/biến đổi cấu trúc class file (JEP 484); trên Java 17, package chuẩn này chưa có. Nếu muốn parser trên Java 17, có thể dùng thư viện thích hợp hoặc tự triển khai một phần có ràng buộc rõ, thay vì giả định `ClassFile.of()` biên dịch được ở mọi JDK.

## 7. Nạp class từ byte[]: loading, linking, initialization là các giai đoạn khác nhau

Với một lớp có bytes hợp lệ, việc định nghĩa và sử dụng trong JVM gồm các hoạt động:

~~~text
Class-file bytes
      |
      v
Loading / defining       -> ClassLoader#defineClass(...)
      |
      v
Linking                  -> verification + preparation + resolution khi cần
      |
      v
Initialization           -> thực hiện class initializer khi được kích hoạt
      |
      v
Invocation/instantiation -> gọi method / tạo object theo luật JVM
~~~

Các giai đoạn có những điểm có thể **trì hoãn** theo JVMS; sơ đồ là ranh giới logic, không phải khẳng định JVM luôn làm mọi thao tác đúng một lượt tuần tự tại thời điểm gọi `defineClass`.

- **Loading** tạo/định nghĩa lớp từ biểu diễn class-file. Class loader có thể dùng cơ chế file, resource, compiler động hoặc bytes tự sinh.
- **Verification** bảo đảm các ràng buộc về định dạng, loại dữ liệu và mã lệnh mà JVM yêu cầu. Bytearray không hợp lệ có thể dẫn tới lỗi.
- **Preparation** tạo/khởi tạo giá trị mặc định cho static fields trong cấu trúc runtime theo quy tắc JVM.
- **Resolution** chuyển symbolic references thành tham chiếu runtime, có thể trì hoãn.
- **Initialization** thực hiện `<clinit>` khi tình huống sử dụng kích hoạt nó. `defineClass` tự nó không có nghĩa tất cả static initializer của mọi kiểu liên quan đã được chạy.

Ví dụ ở mục 5 gọi một public static method bằng reflection sau `defineClass`, nên đi xa hơn mức “chỉ có bytes trong mảng”. Nếu chỉ đọc header `CA FE BA BE`, ta **chưa nạp lớp**; nếu đã có `Class<?>`, ta **không tự động có bản sao bytes chính xác của tệp gốc**.

### 7.1. Danh tính class không chỉ là tên

JVM phân biệt kiểu runtime bằng **tên nhị phân** và **defining class loader**. Hai class loader khác nhau có thể định nghĩa hai kiểu có cùng tên binary nhưng **không phải cùng một `Class<?>`**.

~~~text
Loader A + "demo.MemoryHello" -> Class<?> A
Loader B + "demo.MemoryHello" -> Class<?> B

Tên giống nhau; định danh runtime khác nhau.
~~~

Điều đó quan trọng khi dùng in-memory loader cho plugin hoặc generated code: instance tạo từ class do loader A định nghĩa **không tự nhiên cast** được thành một class cùng tên do loader B định nghĩa. Một class loader bình thường còn có **delegation** và chính sách bảo mật; không nên bỏ qua cơ chế parent loader nếu không có chủ đích.

Nếu dùng `defineClass(binaryName, bytes, ...)`, tên nhị phân được truyền phải phù hợp với tên mà class file mô tả. Không thể đổi tên lớp một cách hợp lệ chỉ bằng thay chuỗi `binaryName` trong lời gọi; đó là metadata nằm trong chính class-file bytes.

## 8. Các trường hợp byte trong bộ nhớ trong instrumentation

Đây là liên hệ trực tiếp với module **Java Advance - instrumentation**. Một Java agent có thể nhận callback của `ClassFileTransformer` khi JVM định nghĩa hoặc biến đổi class.

Ví dụ **mảnh code**, không phải chương trình standalone:

~~~java
@Override
public byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        java.security.ProtectionDomain domain,
        byte[] classfileBuffer) {

    // classfileBuffer là bytes của lần biến đổi đang xử lý.
    if (className == null || !className.startsWith("example/app/")) {
        return null;
    }

    // Phân tích classfileBuffer khi cần, nhưng không sửa mảng đầu vào.
    // Không biến đổi class này thì trả về null.
    return null;
}
~~~

Mảnh mã này nằm trong một lớp implements `java.lang.instrument.ClassFileTransformer`. Một transformer **không nhận đường dẫn tệp `.class` bắt buộc**; nó nhận biểu diễn class-file ở dạng `byte[]` từ JVM. Điều này là lý do Java agent có thể quan sát các lớp được sinh động ngay trong bộ nhớ.

Theo hợp đồng transformer:

- `return null`: transformer **không sửa** class bytes cho lần gọi ấy.
- Trả một `byte[]` mới: đề xuất nội dung class-file đã biến đổi, vẫn phải hợp lệ theo JVMS và giới hạn redefinition/retransformation tương ứng.
- **Không sửa trực tiếp** `classfileBuffer` JVM đưa vào. Khi dùng ASM/Byte Buddy/Class-File API ở phiên bản hỗ trợ, tạo bytes mới và giữ dữ liệu đầu vào đúng hợp đồng.
- **Loại trừ agent/helper/logger** và lọc tên class sớm, tránh tự chèn mã vào cơ chế instrumentation.
- `className` trong callback thường là dạng internal name `example/app/Service`, khác binary name dấu chấm của `Class#getName()`.

Các class có thể được JVM/agent biến đổi mà không có tệp `Service.class` trên đĩa ở một vị trí có thể truy cập. Vì vậy việc tìm “đường dẫn file gốc” không phải một phần bắt buộc của hợp đồng transformer.

### 8.1. Bytes của class được định nghĩa không đồng nghĩa “source code”

Một agent nhìn thấy class-file bytes, **không nhất thiết nhìn thấy Java source**. Những gì có thể phân tích gồm method descriptors, constant pool, code attributes và metadata được giữ lại sau compile; comment Java và nhiều thông tin mức nguồn thường không còn. `SourceFile` hoặc line-number metadata (nếu được compiler ghi) không tái tạo đầy đủ mã nguồn ban đầu.

Decompiler là công cụ **suy dựng** Java-like source từ bytecode, không phải “giải mã nguyên văn” từng ký tự file `.java`. Điều này cũng đúng khi class-file chỉ tồn tại dưới dạng bytes trong memory.

## 9. Mảng `byte[]` vẫn mutable: quyền sở hữu và tính nhất quán

**Class-file format là một chuẩn nhị phân; `byte[]` là một kiểu dữ liệu Java có thể sửa.** Không nên nhầm “class đã compile” với “mảng bytes của nó là immutable”.

Ví dụ:

~~~java
byte[] safeSnapshot = originalBytes.clone();
java.nio.ByteBuffer header =
        java.nio.ByteBuffer.wrap(safeSnapshot)
                .order(java.nio.ByteOrder.BIG_ENDIAN);
~~~

Đây là mảnh code trong method có `originalBytes`. Clone tạo **bản sao**, nhưng giả định người gọi kiểm soát việc không ghi vào `originalBytes` trong lúc clone. `ByteBuffer.wrap` **không tự sao chép** mảng; nếu ai đó còn giữ `safeSnapshot` và sửa nó, buffer sẽ thấy nội dung thay đổi.

Các nguyên tắc vận hành:

1. **Sở hữu rõ ràng:** thread nào tạo/sửa bytes; khi nào được phép publish cho worker khác.
2. **Không giữ tham chiếu mutable không kiểm soát:** bytes được nhận từ một thư viện/plugin có thể bị tái sử dụng hoặc thay đổi theo hợp đồng riêng.
3. **Không chia sẻ builder/stream đang ghi:** chờ compilation/transformation hoàn tất rồi mới lấy snapshot.
4. **Cache theo nội dung/phiên bản khi cần:** cùng binary class name có thể ứng với các phiên bản bytes khác nhau; class loader cũng ảnh hưởng danh tính runtime.
5. **Kiểm tra tài nguyên:** giữ hàng nghìn mảng lớn cùng lúc có thể tăng heap/GC; dùng cơ chế giới hạn/giải phóng phù hợp.
6. **Không suy rằng dropping bytes sẽ unload class:** việc unload runtime class phụ thuộc class loader, mức reachability và quyết định của JVM, không chỉ scope biến local.

Khi nhiều thread cần đọc header độc lập, có thể sao chép bytes hoặc bảo đảm một snapshot không bị sửa sau khi publish với cơ chế memory visibility đúng Java Memory Model. Một `ByteBuffer.asReadOnlyBuffer()` chỉ tạo **read-only view qua buffer đó**; nếu có một reference mutable khác tới backing array, dữ liệu vẫn có thể bị thay đổi.

## 10. Những điều kiện và lỗi khi nạp bytes không hợp lệ

Một class loader không nên nhận bytes từ nguồn không tin cậy rồi định nghĩa lớp mà không có chính sách kiểm soát. JVM có kiểm tra định dạng/bytecode, nhưng **bytecode hợp lệ vẫn có thể thực thi hành vi không an toàn cho ứng dụng**, ví dụ đọc file hoặc gọi network API theo quyền của runtime.

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `UnsupportedClassVersionError` | Major/minor version không được JVM hỗ trợ | Xem `major_version` và phiên bản target JVM |
| `ClassFormatError` | Cấu trúc class file/constant pool/attribute sai | Xác minh bytes theo JVMS, parser/verifier |
| `VerifyError` | Ràng buộc verifier hoặc kiểu dữ liệu bytecode không hợp lệ | Xem verifier message, lỗi transformer/generator |
| `NoClassDefFoundError` | Tên bytes không khớp tên yêu cầu hoặc thiếu class phụ thuộc ở thời điểm liên kết | Kiểm tra binary name và classpath/loader |
| `LinkageError` | Xung đột định nghĩa, phụ thuộc, tên hoặc ràng buộc linking | Xem defining loader và nguyên nhân cụ thể |
| `ClassNotFoundException` | Loader được hỏi nhưng không tìm hoặc tạo được class | Khác với lỗi bytes không hợp lệ trong `defineClass` |
| `IllegalAccessError`/`IncompatibleClassChangeError` | Ràng buộc truy cập hoặc cấu trúc runtime không tương thích | Đối chiếu phiên bản class và phụ thuộc |
| `ToolProvider.getSystemJavaCompiler() == null` | Runtime không cung cấp compiler hệ thống | Chạy bằng JDK đầy đủ hoặc dùng compiler khác có sẵn |

**Magic đúng không loại trừ các lỗi trên.** JVM verifier giúp bảo vệ tính đúng đắn của mã lệnh theo định dạng, nhưng **không thay thế** chính sách xác thực nguồn, phân quyền và kiểm thử compatibility của code do bên ngoài cung cấp.

Với code generation, cần chủ động quản lý lượng class sinh ra: mỗi defining loader/kiểu có thể tiêu thụ metadata trong runtime; nếu tạo nhiều lớp và giữ loader sống lâu, memory footprint có thể tăng. Không thiết kế một cơ chế “tạo class mới mỗi request” nếu không hiểu khả năng thu hồi class/loader.

## 11. Mô hình tư duy khi cần quyết định công cụ

| Mục tiêu thực tế | Phương án và lý do |
| --- | --- |
| Chỉ xem phiên bản class file trên đĩa | `javap -verbose` hoặc đọc 10 byte header |
| Phân tích class file chưa nạp | Đọc `byte[]` bằng parser class-file phù hợp; không cần `Class.forName` |
| Tạo lớp runtime không ghi tệp của lớp đích | JavaCompiler in-memory + file manager + `defineClass`, như ví dụ |
| Sinh proxy/helper động | Bytecode generator và class-loader/lookup phù hợp với mô hình an toàn |
| Instrument lớp khi đang được nạp | Java agent `ClassFileTransformer` nhận class bytes, trả bytes mới hoặc `null` |
| Thay một lớp đã load | `Instrumentation` cùng retransform/redefine khi được hỗ trợ; không thể chỉ gọi lại `defineClass` với cùng loader và tên |
| Dùng cùng tên cho nhiều bản class | Phân biệt class loader; thiết kế isolation/caching/versioning đúng |
| Phân tích nhiều bytes trong nhiều thread | Sở hữu hoặc copy bytes rõ ràng; tránh ghi đồng thời và dùng chung mutable parsing state |

Chú ý `ClassLoader#defineClass` **định nghĩa một kiểu mới trong loader**, chứ không phải API “ghi đè class hiện tại”. Cố định nghĩa lại cùng binary name trong cùng loader thường gây `LinkageError`; muốn instrumentation/redefinition class đang chạy phải dùng đúng cơ chế của JVM và đáp ứng các giới hạn tương ứng.

## 12. Các hiểu nhầm cần tránh

1. **“Không có file `.class` trên đĩa thì JVM không chạy được.”** Sai: định dạng class-file có thể nằm trong byte array/nguồn khác mà loader cung cấp.
2. **“Mảng `byte[]` là một đối tượng `Class<?>`.”** Sai: trước và sau loading là hai khái niệm khác nhau.
3. **“Class file chỉ chứa instruction.”** Sai: còn header, constant pool, field, method và attributes.
4. **“Bốn byte `CAFEBABE` đủ để định nghĩa class.”** Sai: còn toàn bộ cấu trúc và xác minh.
5. **“`major=61` nghĩa máy hiện tại chắc chắn chạy Java 17.”** Sai: nó nói class được biên dịch ở định dạng Java 17; JVM runtime có thể mới hơn.
6. **“`ByteBuffer.wrap` sao chép bytes.”** Sai: nó dùng backing array được cung cấp.
7. **“Đổi tên tham số `defineClass` là đổi tên class trong bytes.”** Sai: nội dung class file phải mô tả tên phù hợp.
8. **“Hai lớp cùng tên luôn cùng một kiểu.”** Sai: defining class loader là một phần danh tính.
9. **“JVM bắt buộc lưu bytes gốc dưới dạng tệp và public API cho phép lấy lại.”** Sai: cơ chế và quyền truy cập bytes gốc không được bảo đảm như vậy.
10. **“Class file hợp lệ đương nhiên an toàn để chạy.”** Sai: bytecode hợp lệ vẫn là mã có thể thực hiện hành động nguy hiểm dưới quyền của ứng dụng.
11. **“Agent có thể sửa trực tiếp mảng `classfileBuffer`.”** Sai: theo hợp đồng transformer cần tạo mảng mới khi có biến đổi.
12. **“Việc gọi `defineClass` chắc chắn đã chạy static initializer.”** Sai: initialization có điều kiện và thời điểm riêng theo JVM.
13. **“Không tạo tệp class nghĩa compiler không thể dùng JDK/module từ đĩa.”** Sai: chỉ output class được sinh trong ví dụ lưu ở memory; compiler vẫn có thể cần truy cập các thành phần JDK.

## 13. Câu hỏi và bài tập tự kiểm tra

1. Nếu ứng dụng nhận một `byte[]` từ network, cần điều kiện gì trước khi có thể gọi `defineClass` thành công?
2. Bốn byte ở offset 0–3, hai byte ở offset 6–7 lần lượt mang ý nghĩa gì?
3. Vì sao không thể đọc `methods_count` bằng offset cố định ở mọi class file?
4. Chạy ví dụ trên JDK 21 với `--release 17` thì `major` bằng bao nhiêu? Vì sao?
5. Tại sao phương thức `type.getMethod("message").invoke(null)` chứng minh được nhiều hơn việc chỉ in header bytes?
6. `MemoryFiles.getJavaFileForOutput` giúp tránh tạo file `demo/MemoryHello.class` ở bước nào?
7. Vì sao `type.getClassLoader() == loader` đáng kiểm tra khi nạp một lớp sinh động?
8. Nếu tạo một `MemoryLoader` thứ hai rồi định nghĩa `demo.MemoryHello` từ cùng bytes, hai `Class<?>` có bằng nhau theo identity không?
9. Nếu sửa một byte ngẫu nhiên trong constant pool, JVM chắc chắn từ chối tại `defineClass` hay có thể lỗi xuất hiện lúc liên kết/sử dụng? Vì sao cần tuân hợp đồng JVM thay vì đoán?
10. Tại sao không được ghi vào `classfileBuffer` mà `ClassFileTransformer` truyền vào?
11. `Class<?>` có cung cấp phương thức lấy lại nguyên văn các bytes lúc compiler xuất ra không?
12. Với một class-file byte array chỉ tồn tại trong RAM, có nhất thiết tồn tại một `Path` tương ứng không?

**Ghi nhớ:** “`.class`” là cách lưu phổ biến, còn **class-file format là một cấu trúc nhị phân có thể biểu diễn đầy đủ bằng một `byte[]`**. JVM cần **nội dung byte hợp lệ và cơ chế nạp/định nghĩa phù hợp**, không nhất thiết cần file vật lý cho lớp đó. Java compiler, class loader và Java agent đều có những giao diện làm việc trực tiếp với bytes; hãy phân biệt bytes, lớp runtime và machine code, đồng thời kiểm soát version, class loader, mutability và nguồn gốc dữ liệu.

### Tài liệu chính thức

- [JVMS Java 17 — Chapter 4: The class File Format](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html)
- [JVMS Java 17 — Chapter 5: Loading, Linking, and Initializing](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html)
- [Java 17 — ClassLoader và defineClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java 17 — javax.tools.JavaCompiler](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html)
- [Java 17 — ClassFileTransformer](https://docs.oracle.com/en/java/javase/17/docs/api/java.instrument/java/lang/instrument/ClassFileTransformer.html)
- [JEP 484 — Class-File API chuẩn hóa JDK 24](https://openjdk.org/jeps/484)
