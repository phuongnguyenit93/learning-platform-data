# Nạp bytecode bằng loader mới có hợp đồng chung ở loader cha

## 1. Bối cảnh và mục tiêu

Một hệ thống mở rộng Java có thể nhận source code lúc runtime (ví dụ biểu thức nghiệp vụ, quy tắc xử lý, plugin có nguồn do hệ thống sinh ra), biên dịch source thành **bytecode trong bộ nhớ** rồi nạp các lớp mới mà không cần ghi `.class` xuống đĩa. JDK cung cấp `javax.tools.JavaCompiler` để biên dịch, `JavaFileObject`/`JavaFileManager` để thu kết quả, còn `ClassLoader#defineClass` để định nghĩa class từ mảng byte.

Tuy nhiên, “nạp được class” **chưa đủ**. Host và plugin cần một **hợp đồng giao tiếp chung** (API/SPI) để host có thể cast instance, gọi method hoặc đăng ký provider an toàn:

- **Host sở hữu contract**: ví dụ `demo.host.MemoryPluginDemo.Greeting` được nạp và định nghĩa bởi class loader của host.
- **Mỗi lượt nạp plugin sở hữu loader riêng**: một `PluginLoader` mới giữ bytecode của `demo.plugin.Hello` rồi định nghĩa implementation đó.
- **Loader plugin có loader cha là loader của host**: khi implementation tham chiếu `Greeting`, việc ủy quyền mặc định tìm đúng **cùng một kiểu Java** mà host đang sử dụng.
- **Compiler thấy chính contract của host**: lúc biên dịch, `JavaCompiler` phải tra đúng classpath/module path chứa API chung. Việc compiler biên dịch thành công và việc JVM nạp bằng loader phù hợp là **hai điều kiện riêng**.
- **Không định nghĩa lại contract trong loader con**: nếu plugin tự tạo một bản sao interface cùng tên, `ClassCastException` hoặc lỗi linkage có thể xuất hiện dù source trông hợp lệ.

Trong phạm vi bài này, ví dụ chạy với **JDK 17+, Java classpath và một shared interface**, không yêu cầu thư viện ngoài. Các hệ JPMS, `ModuleLayer` hoặc dịch vụ không tin cậy cần thêm những kiểm soát riêng.

### 1.1. Sơ đồ tổng quát

```text
                       HOST (application class loader)
             +---------------------------------------+
             | API/SPI: Greeting                     |
             | Code gọi compiler + registry          |
             +---------------------------------------+
                                ^
                                | parent delegation
                   +------------+-------------+
                   |                          |
            PluginLoader A              PluginLoader B
            (new instance)              (new instance)
                   |                          |
            defineClass(...)             defineClass(...)
                   |                          |
            demo.plugin.Hello            demo.plugin.Hello
            greet() -> "hello-A"          greet() -> "hello-B"
                   |                          |
                   +--> implements cùng Greeting <--+
                        (do loader cha định nghĩa)
```

Hai class `demo.plugin.Hello` có **tên nhị phân giống nhau**, nhưng vì được định nghĩa bởi **hai defining loaders khác nhau**, chúng là **hai runtime class khác nhau**. Cả hai lại có thể implement **cùng** `Greeting` vì interface đó đến từ loader cha. Điều này rất hữu ích khi thay version plugin theo từng lượt mà không thay đổi contract của host.

## 2. Phân biệt biên dịch, nạp, liên kết và khởi tạo

Cần nhìn chuỗi xử lý theo từng giai đoạn để chẩn đoán lỗi chính xác.

| Giai đoạn | Thành phần | Kết quả | Một số lỗi thường gặp |
| --- | --- | --- | --- |
| Sinh/nhận source | Host | Chuỗi Java source | Code không hợp lệ, import sai |
| Biên dịch | `JavaCompiler` | Bytecode cho một hay nhiều binary class names | Compilation diagnostics, thiếu API trên classpath |
| Thu bytecode | `JavaFileManager` | `Map<String, byte[]>` | Không lưu đủ class phụ/anonymous class, quản lý output sai |
| Tạo loader | `new PluginLoader(parent, bytes)` | Loader mới, parent đã xác định | Chọn sai parent, leak reference |
| Nạp/định nghĩa | `loadClass` / `findClass` / `defineClass` | Một `Class<?>` mang danh tính loader cụ thể | `ClassNotFoundException`, `NoClassDefFoundError`, `ClassFormatError`, linkage |
| Khởi tạo instance | Reflection / constructor | Instance Java | `InvocationTargetException`, lỗi static initializer, không có constructor |
| Sử dụng contract | Cast sang API/SPI host | Host gọi method typed | `ClassCastException`, `NoSuchMethodError`, incompatibility |

Một đối tượng `ClassLoader` mới **không tự động định nghĩa** mọi class có trong map bytecode. Khi host gọi `loader.loadClass(binaryName)`, cơ chế ủy quyền sẽ kiểm tra parent và gọi `findClass` để định nghĩa bytecode phù hợp nếu parent không có class đó.

**`loadClass` không tự động khởi tạo class như khi tạo instance.** Việc gọi constructor sau đó sẽ kích hoạt các bước cần thiết để thực thi code của lớp. Vì vậy lỗi có thể xuất hiện trong pha biên dịch, nạp, liên kết hoặc khi chạy constructor, không nên dồn mọi lỗi vào một nhãn “compilation failed”.

## 3. Các thành phần JavaCompiler khi biên dịch hoàn toàn trong bộ nhớ

### 3.1. Lấy compiler từ JDK

`ToolProvider.getSystemJavaCompiler()` trả về compiler mặc định khi môi trường Java có công cụ tương ứng. Với một runtime không có compiler, kết quả có thể là `null`:

```java
JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
if (compiler == null) {
    throw new IllegalStateException("A JDK is required");
}
```

Đây là **đoạn minh họa**, cần import `javax.tools.JavaCompiler` và `javax.tools.ToolProvider`. Chương trình hoàn chỉnh ở phần 5 có đầy đủ import và cách sử dụng.

JavaCompiler là API biên dịch, không phải API chạy code trong sandbox. Khi compiler dùng classpath không đúng, source có thể không nhận ra interface host hoặc dùng nhầm một phiên bản khác. Cần xác định rõ phiên bản Java mục tiêu (ví dụ `--release 17`) và thư viện API nào compiler được phép tham chiếu.

### 3.2. Source nằm trong JavaFileObject

Để compiler không phải đọc tệp `.java` vật lý, ta tạo một `SimpleJavaFileObject` loại `Kind.SOURCE`, cung cấp nội dung qua `getCharContent`.

Một URI dạng `string:///demo/plugin/Hello.java` giúp compiler biết tên tệp ảo và ánh xạ tới binary name `demo.plugin.Hello`. URI này **không phải đường dẫn mà JVM sẽ tự tìm class**; nó chỉ là định danh cho file object của compiler.

Có thể đưa nhiều source object vào một lần gọi compiler. Nếu source sinh ra các inner class, local class hoặc nhiều class phụ, output có thể gồm nhiều tên `ClassName$Inner.class`, `ClassName$1.class`... Không nên tự giả định compiler chỉ xuất đúng một `.class` cho một tệp source.

### 3.3. Bytecode đầu ra nằm trong ByteArrayOutputStream

`JavaCompiler` hỏi file manager nơi ghi output cho từng class. Khi override `ForwardingJavaFileManager#getJavaFileForOutput`, ta có thể trả về `JavaFileObject` có `openOutputStream()` ghi vào `ByteArrayOutputStream`.

```text
getJavaFileForOutput(location, "demo.plugin.Hello", CLASS, sibling)
    -> Bytecode("demo.plugin.Hello")
        -> openOutputStream()
            -> byte[] đại diện cho demo.plugin.Hello
```

Map bytecode nên có khóa là **tên nhị phân đầy đủ**, không chỉ tên file đơn giản. Ví dụ `demo.plugin.Hello` là tên mà `ClassLoader.findClass(String)` nhận; khóa `Hello` sẽ không khớp.

`ByteArrayOutputStream` có thể chuyển thành bản sao `byte[]` bằng `toByteArray()`. Không gửi buffer có thể thay đổi từ bên ngoài vào loader nếu không xác minh ownership/immutability. Với hệ thống lớn, nên giới hạn kích thước bytecode, số class và dung lượng bộ nhớ.

### 3.4. FileManager chuẩn vẫn có vai trò quan trọng

`StandardJavaFileManager` giúp compiler tìm các class đã biên dịch và thư viện phụ thuộc trên classpath/module path. `ForwardingJavaFileManager` bọc file manager này để **chặn đầu ra** vào bộ nhớ nhưng **vẫn giữ nguyên khả năng đọc dependency** theo cấu hình compiler.

Điểm phân biệt quan trọng:

- “Biên dịch trong bộ nhớ” trong ví dụ có nghĩa **source plugin là chuỗi và output plugin là mảng byte**, không tạo `.java`/`.class` vật lý cho plugin đó.
- Class API của host vẫn đã có trên classpath lúc chạy demo; đây là hợp đồng dùng chung, không phải sản phẩm plugin.
- Nếu cần compiler nhìn thấy class được biên dịch **trong một lượt trước nhưng chưa hề lưu lên đĩa**, chỉ ghi đè `getJavaFileForOutput` chưa đủ cho mọi tình huống; có thể cần thêm cơ chế cung cấp input/listing, classpath ảo hoặc compiler task nhiều source cùng lúc.
- Annotation processors và tài nguyên do chúng sinh ra có thể cần thêm các override/cấu hình khác. Mã mẫu tập trung vào một Java source đơn giản và output `.class`.

## 4. Vai trò của loader cha và ranh giới API/SPI

### 4.1. Vì sao interface chung phải do parent định nghĩa?

Trong Java, class identity gắn với **binary name + defining class loader**. Hai interface có cùng tên `com.example.spi.Task` nhưng do hai loader khác nhau định nghĩa là hai runtime types khác nhau. Host cast instance của plugin sang `Task` của host có thể thất bại nếu implementation dùng bản interface khác.

Với chính sách thông thường của `ClassLoader.loadClass`:

1. Kiểm tra class đã được loader đó nạp trước (`findLoadedClass`).
2. Thử hỏi loader cha.
3. Nếu parent không tìm thấy, gọi `findClass` của loader con để định nghĩa class local.
4. Có thể resolve theo yêu cầu trước khi trả về.

Trong hệ plugin, đây là chính sách **parent-first**, phù hợp khi host sở hữu interface, DTO, enum, exception và callback qua ranh giới. Việc parent-first cũng có nghĩa **nếu host vô tình có class implementation `demo.plugin.Hello`**, parent có thể trả về class của host thay vì bytecode mới. Vì vậy cần kiểm tra classpath của host không shadow tên implementation, hoặc thiết kế quy tắc child-first có ngoại lệ **parent-only** cho contract dùng chung.

### 4.2. Không chỉ chia sẻ interface chính

Một contract thực tế có thể dùng:

```java
package com.example.api;

public interface Transform {
    Result apply(Request request) throws TransformException;
}
```

Đoạn trên chỉ mô tả kiến trúc; `Request`, `Result`, `TransformException` không phải class mặc định của Java. Nếu host và plugin cần trao đổi trực tiếp những kiểu này, **tất cả** nên thuộc API dùng chung với cùng class identity:

- Interface/abstract class và base class.
- DTO, record, enum, annotation đi qua boundary.
- Exception trong chữ ký method, callback/listener, event type.
- Những generic bound hoặc kiểu lộ ra qua method signature.
- Phần của framework host mà plugin thực sự dùng làm contract.

Không nên chỉ đặt `Transform` ở parent rồi để plugin tự định nghĩa một bản khác của `Result`. Mọi type có ý nghĩa qua ranh giới phải được quản trị về identity và API version.

### 4.3. Quy tắc hạn chế tìm local class

Loader demo kiểm tra:

```java
if (binaryName.startsWith("java.") || binaryName.startsWith("demo.host.")) {
    throw new ClassNotFoundException("Shared classes are parent-owned: " + binaryName);
}
```

Đây là **đoạn trích từ chương trình hoàn chỉnh**. Nó ngăn chính `findClass` của loader plugin định nghĩa bytecode nằm trong các namespace đó. Tuy nhiên `loadClass` mặc định đã hỏi parent trước; khi parent tìm được `demo.host.*`, nhánh `findClass` không chạy. Việc kiểm tra ở `findClass` là một hàng rào bổ sung nếu parent báo không tìm được, không phải cơ chế kiểm chứng artifact không có class cấm.

Một hệ production nên **kiểm tra danh sách binary names ngay khi nhận map bytecode**, từ chối plugin cố định nghĩa package API hoặc protected namespace, và bảo đảm contract cần thiết thực sự tồn tại ở parent. Không nên cố “cứu” một contract không tồn tại ở parent bằng cách tự định nghĩa bản copy bên plugin.

### 4.4. Một class name, nhiều loader

Plugin A và B có thể cùng định nghĩa `demo.plugin.Hello`:

```text
PluginLoader A  --defines--> demo.plugin.Hello [version A]
PluginLoader B  --defines--> demo.plugin.Hello [version B]
Host loader     --defines--> demo.host.MemoryPluginDemo$Greeting
```

Khi đó:

- `first.getClass() != second.getClass()` là **true**.
- `first instanceof Greeting` và `second instanceof Greeting` đều có thể là **true**.
- Không được cast instance của A sang class implementation của B; hai định nghĩa class khác nhau.
- Parent phải cung cấp API đúng phiên bản. Shared identity không tự bảo đảm method ABI hay behavior tương thích.
- Nếu cần nâng cấp một implementation đã được nạp, thường tạo **loader mới**, không cố gọi `defineClass` lần nữa cùng binary name trong loader cũ.

## 5. Ví dụ Java 17+ chạy được: biên dịch source vào bộ nhớ và nạp bằng loader con

Chỉ cần **một tệp Java nguồn ở phía host**. Chương trình tự tạo source string cho plugin, biên dịch vào bộ nhớ bằng `JavaCompiler`, tạo một loader mới cho mỗi phiên bản và cast instance về interface `Greeting` đã có ở host.

Đặt tệp vào đường dẫn **`src/demo/host/MemoryPluginDemo.java`**:

```java
package demo.host;

import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.List;
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

public final class MemoryPluginDemo {
    public interface Greeting {
        String greet();
    }

    private static final class Source extends SimpleJavaFileObject {
        private final String code;

        Source(String binaryName, String code) {
            super(URI.create("string:///" + binaryName.replace('.', '/') + Kind.SOURCE.extension),
                    Kind.SOURCE);
            this.code = code;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return code;
        }
    }

    private static final class Bytecode extends SimpleJavaFileObject {
        private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();

        Bytecode(String binaryName, Kind kind) {
            super(URI.create("mem:///" + binaryName.replace('.', '/') + kind.extension), kind);
        }

        @Override
        public OutputStream openOutputStream() {
            return bytes;
        }

        byte[] content() {
            return bytes.toByteArray();
        }
    }

    private static final class MemoryManager
            extends ForwardingJavaFileManager<JavaFileManager> {
        private final Map<String, Bytecode> outputs = new HashMap<>();

        MemoryManager(JavaFileManager delegate) {
            super(delegate);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                Location location, String className, JavaFileObject.Kind kind,
                FileObject sibling) {
            Bytecode output = new Bytecode(className, kind);
            outputs.put(className, output);
            return output;
        }

        Map<String, byte[]> snapshot() {
            Map<String, byte[]> result = new HashMap<>();
            outputs.forEach((name, output) -> result.put(name, output.content()));
            return Map.copyOf(result);
        }
    }

    private static final class PluginLoader extends ClassLoader {
        private final Map<String, byte[]> classes;

        PluginLoader(ClassLoader parent, Map<String, byte[]> classes) {
            super(parent);
            this.classes = Map.copyOf(classes);
        }

        @Override
        protected Class<?> findClass(String binaryName) throws ClassNotFoundException {
            if (binaryName.startsWith("java.") || binaryName.startsWith("demo.host.")) {
                throw new ClassNotFoundException("Shared classes are parent-owned: " + binaryName);
            }
            byte[] bytes = classes.get(binaryName);
            if (bytes == null) {
                throw new ClassNotFoundException(binaryName);
            }
            return defineClass(binaryName, bytes, 0, bytes.length);
        }
    }

    private static Map<String, byte[]> compile(String binaryName, String code)
            throws Exception {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A JDK is required");
        }
        DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
        try (StandardJavaFileManager standard =
                     compiler.getStandardFileManager(diagnostics, null, StandardCharsets.UTF_8)) {
            MemoryManager files = new MemoryManager(standard);
            List<String> options = List.of(
                    "--release", "17", "-classpath", System.getProperty("java.class.path"));
            boolean ok = Boolean.TRUE.equals(
                    compiler.getTask(null, files, diagnostics, options, null,
                            List.of(new Source(binaryName, code))).call());
            if (!ok) {
                throw new IllegalStateException("Compile errors: " + diagnostics.getDiagnostics());
            }
            return files.snapshot();
        }
    }

    private static Greeting create(String value) throws Exception {
        String binaryName = "demo.plugin.Hello";
        String code = """
                package demo.plugin;
                public final class Hello implements demo.host.MemoryPluginDemo.Greeting {
                    public Hello() {}
                    @Override public String greet() { return "%s"; }
                }
                """.formatted(value);
        Map<String, byte[]> bytes = compile(binaryName, code);
        ClassLoader loader = new PluginLoader(MemoryPluginDemo.class.getClassLoader(), bytes);
        Class<?> type = loader.loadClass(binaryName);
        return (Greeting) type.getDeclaredConstructor().newInstance();
    }

    public static void main(String[] args) throws Exception {
        Greeting first = create("hello-A");
        Greeting second = create("hello-B");
        System.out.println("first: " + first.greet());
        System.out.println("second: " + second.greet());
        System.out.println("shared contract: " +
                (first.getClass().getInterfaces()[0] == Greeting.class
                && second.getClass().getInterfaces()[0] == Greeting.class));
        System.out.println("different plugin loaders: " +
                (first.getClass().getClassLoader() != second.getClass().getClassLoader()));
        System.out.println("different implementation types: " +
                (first.getClass() != second.getClass()));
        try {
            Class.forName("demo.plugin.Hello", false, MemoryPluginDemo.class.getClassLoader());
            System.out.println("host sees implementation: true");
        } catch (ClassNotFoundException expected) {
            System.out.println("host sees implementation: false");
        }
    }
}
```

### 5.1. Biên dịch và chạy

Từ thư mục làm việc chứa `src`, sử dụng JDK 17 trở lên:

```bash
javac --release 17 -d out src/demo/host/MemoryPluginDemo.java
java -cp out demo.host.MemoryPluginDemo
```

Chương trình host được biên dịch thành `.class` trong `out`; **chỉ bytecode của plugin** mới được biên dịch động và giữ trong bộ nhớ. Nó cần JDK tại runtime để `ToolProvider.getSystemJavaCompiler()` hoạt động.

**Stdout chính xác đã kiểm chứng qua `javac --release 17` và `java`:**

```text
first: hello-A
second: hello-B
shared contract: true
different plugin loaders: true
different implementation types: true
host sees implementation: false
```

Ý nghĩa kết quả:

1. `first: hello-A` và `second: hello-B`: hai lần compiler chạy với source khác nhau; mỗi bytecode được định nghĩa trong một loader mới nên không ghi đè implementation cũ.
2. `shared contract: true`: class `Hello` của cả hai bản **đều tham chiếu đúng `Greeting.class` của host**; host có thể cast sang `Greeting` và gọi `greet()`.
3. `different plugin loaders: true`: hai instance được định nghĩa bởi hai loader khác nhau.
4. `different implementation types: true`: dù hai lớp cùng có binary name `demo.plugin.Hello`, chúng không phải cùng một `Class<?>`.
5. `host sees implementation: false`: hỏi class loader của host về implementation plugin thất bại như dự kiến; child loader biết class của mình, nhưng parent không tự “nhìn xuống” để tìm class đã được child định nghĩa.

### 5.2. Vì sao ví dụ không tạo bản thứ hai của Greeting?

`Greeting` là public nested interface bên trong `MemoryPluginDemo`, nên binary name thực tế của nó là `demo.host.MemoryPluginDemo$Greeting`. Compiler có thể resolve interface này qua classpath của host (`-cp out`). Khi loader con định nghĩa `demo.plugin.Hello`, cơ chế class loader mặc định ưu tiên parent; nó tìm `Greeting` tại loader đã định nghĩa `MemoryPluginDemo`.

Do đó, `(Greeting) type.getDeclaredConstructor().newInstance()` không gây `ClassCastException`. Nếu plugin tự định nghĩa bytecode với binary name `demo.host.MemoryPluginDemo$Greeting` ở một loader khác và runtime thực sự dùng bản riêng đó, điều kiện tương thích sẽ bị phá vỡ.

### 5.3. Giới hạn cố ý của ví dụ

- Chuỗi `"hello-A"`, `"hello-B"` cố định và tin cậy; demo dùng `String.formatted(value)` để sinh Java source, **không** phải bộ thoát chuỗi Java an toàn cho input tùy ý. Với input bên ngoài, phải sinh literal có escaping chính xác hoặc tách dữ liệu khỏi source code.
- Example classpath host chỉ có source và contract đã biên dịch. Hệ production cần cấp **classpath/module path tường minh và tối thiểu** cho compiler; đừng mặc định dùng toàn bộ `java.class.path` nếu điều đó làm lộ dependency nội bộ hoặc gây lệch version.
- `MemoryManager` thu output class đơn giản. Một compiler workflow phức tạp có annotation processor, generated resource, incremental compilation hoặc nhiều dependency in-memory có thể đòi hỏi file manager nâng cao.
- Loader chỉ override `findClass` và kế thừa **parent-first**; nếu class implementation trùng tên đã có trên classpath của parent, parent có thể thắng. Demo giả định host **không** chứa `demo.plugin.Hello`.
- Ví dụ dùng parent là loader của host, không thử triển khai chính sách bảo mật mạnh hoặc chạy code không tin cậy.

## 6. Thực hiện đúng hợp đồng khi bytecode được tạo nhiều lần

### 6.1. Giữ interface ổn định, thay implementation

Mô hình thực tế thường là:

```text
host:
  api.PluginTask       -> loader cha, định nghĩa một lần
  PluginRegistry       -> lưu api.PluginTask

compile generation #1:
  impl.TaskV1          -> pluginLoader#1
  impl.Helper          -> pluginLoader#1

compile generation #2:
  impl.TaskV2          -> pluginLoader#2
  impl.Helper          -> pluginLoader#2

PluginRegistry thay implementation, không đổi contract api.PluginTask
```

Nếu thay bytecode của **cùng binary name** `impl.Task`, vẫn có thể nạp song song hai version bằng hai loader khác nhau. Trong cùng một loader, sau khi đã định nghĩa `impl.Task`, không thể chỉ thay nội dung map rồi kỳ vọng `loadClass("impl.Task")` trả về version mới. `ClassLoader` ghi nhớ class đã nạp; định nghĩa lại một tên trong cùng loader không phải cơ chế cập nhật hợp lệ.

### 6.2. Shared API phải có trên classpath lúc compile *và* loader cha lúc runtime

Nên xác nhận độc lập hai mặt:

- **Compile-time visibility:** compiler đang đọc bản API nào? `-classpath` hoặc `--module-path` có trỏ tới bản host mong muốn không? Compiler có báo method/constructor không tương thích không?
- **Runtime identity:** `Greeting.class.getClassLoader()` và interface mà implementation thực sự implement có phải một `Class<?>` không? `Greeting.class.isAssignableFrom(type)` có true không?
- **Version compatibility:** cùng class identity không tự chứng minh API version đã hỗ trợ hành vi plugin cần. Nên có metadata hoặc handshake về version/capability để từ chối plugin không tương thích.
- **Contract closure:** mọi DTO, enum, exception, callback và event type đi qua boundary phải dùng chung loader policy, không chỉ interface chính.

Một runtime có thể biên dịch thành công với một bản API, nhưng khi nạp runtime lại dùng một bản cũ hơn và gặp `NoSuchMethodError` hoặc lỗi liên kết. Cần kiểm thử đúng classpath và JDK của môi trường deploy, không chỉ IDE.

### 6.3. Chặn bytecode sai namespace trước khi define

Nếu áp dụng quy tắc namespace, host có thể kiểm tra `Map<String, byte[]>`:

```java
for (String name : compiledBytecode.keySet()) {
    if (name.startsWith("java.") || name.startsWith("demo.host.")) {
        throw new IllegalArgumentException("Plugin cannot define: " + name);
    }
}
```

Đây là **đoạn minh họa**, cần một biến `compiledBytecode` kiểu `Map<String, byte[]>` được định nghĩa từ kết quả biên dịch, không phải chương trình chạy độc lập. Trong hệ thật, kiểm tra tên binary từ map là hữu ích nhưng **chưa đủ** để xác thực nguồn bytecode: nên giới hạn package được phép, đánh giá định dạng, dependency và kích thước của class. Không dùng `defineClass` như trình thẩm định tính an toàn của code.

### 6.4. Parent-first và child-first

Loader ở ví dụ kế thừa thuật toán parent-first. Đây là lựa chọn phù hợp khi:

- Parent sở hữu `Greeting` và các API xuyên ranh giới.
- Host không đóng gói class implementation của plugin.
- Dependency riêng không xung đột tên với parent hoặc đã được đặt vào namespace riêng.

Nếu plugin có thư viện private cùng tên nhưng khác version so với host, parent-first có thể chọn nhầm bản host. Khi đó cần chính sách child-first có kiểm soát cho **implementation và dependency private**, nhưng vẫn **parent-only/parent-first nghiêm ngặt** đối với shared SPI. Đổi tất cả sang child-first mà không có ngoại lệ cho API thường tạo lỗi type identity khó chẩn đoán.

## 7. Chẩn đoán lỗi theo giai đoạn

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `getSystemJavaCompiler() == null` | Runtime không cung cấp compiler hệ thống | Dùng JDK phù hợp hoặc cung cấp chiến lược compiler khác |
| Compiler báo không thấy `Greeting` | API host không có trên compiler classpath/module path | Truyền đường dẫn đúng, không tạo bản copy tùy tiện |
| Compiler báo lỗi cú pháp | Source string không hợp lệ hoặc Java version mismatch | Đọc `DiagnosticCollector`, vị trí dòng/cột |
| Map bytecode thiếu tên class | File manager không ghi đủ `getJavaFileForOutput` hoặc không lưu output | Log binary names, xử lý nhiều output class |
| `ClassNotFoundException` | Sai binary name, không có bytecode hoặc parent không thấy dependency | Xác minh key của map và loader dùng để tìm |
| `NoClassDefFoundError` | Một class cần khi liên kết/khởi tạo không có, hoặc initialization thất bại trước đó | Kiểm tra dependency/cause, không chỉ class chính |
| `ClassFormatError` / `VerifyError` | Bytecode không hợp lệ cho JVM | Không định nghĩa bytecode chưa được compiler/JVM chấp nhận |
| `ClassCastException` | Plugin nạp bản copy contract với class identity khác | So sánh `Class<?>` và defining loader của SPI |
| `NoSuchMethodError` / `AbstractMethodError` | API lúc compile khác ABI runtime | Khóa version API, kiểm thử runtime dependency |
| `InvocationTargetException` | Constructor/method chạy qua reflection đã ném exception | Kiểm tra `getCause()` của lỗi phản chiếu |
| `ExceptionInInitializerError` | Static initializer của class lỗi | Giữ root cause, sửa logic initialization |
| Nạp version mới nhưng luôn nhận logic cũ | Dùng lại cùng loader/class hoặc bị parent shadow | Tạo loader mới và xác định parent có tên implementation không |
| Metaspace/memory tăng liên tục | Giữ class, instance, loader, thread, registry hoặc cache cũ | Quản lý lifecycle và loại bỏ tham chiếu không còn dùng |

Tại ranh giới nạp class, log ít nhất: binary class name, nguồn bytecode, hash/version của bản biên dịch, tên defining loader, tên contract, Java version và exception cause. Với source động chứa thông tin nhạy cảm, không log nguyên văn toàn bộ source trong production.

Có thể kiểm tra nhanh identity:

```java
Class<?> implementation = pluginLoader.loadClass("demo.plugin.Hello");
System.out.println(implementation.getClassLoader());
System.out.println(Greeting.class.getClassLoader());
System.out.println(Greeting.class.isAssignableFrom(implementation));
```

Đây là **đoạn minh họa tích hợp**, cần `pluginLoader` và `Greeting` do host cung cấp. Trong tình huống đúng, loader implementation thường khác loader của contract nhưng `isAssignableFrom` vẫn là true.

## 8. Resource, ServiceLoader, TCCL và module system

### 8.1. Bytecode trong map không tương đương một JAR plugin đầy đủ

Override `findClass` chỉ giải quyết việc nạp **class theo binary name**. Nó không tự cung cấp:

- `ClassLoader.getResource("config.yml")`.
- `getResources("META-INF/services/<service>")` để `ServiceLoader` tìm descriptor provider.
- Manifest, chữ ký JAR hoặc các file phụ của thư viện.
- Khả năng để compiler ở lần sau sử dụng lại toàn bộ bytecode đã nạp trong memory map như một classpath chuẩn.

Nếu plugin cần resource, phải thiết kế thêm cơ chế trả `URL`/resource stream hoặc gói output thành một artifact thích hợp, tùy kiến trúc. Không đồng nhất thứ tự tìm class với thứ tự tìm resource.

### 8.2. ServiceLoader và class identity

Nếu host dùng service contract `Greeting` và khám phá plugin bằng `ServiceLoader`, provider **phải implement cùng `Greeting.class`** mà host truyền cho loader. Nếu plugin tạo bản copy SPI trong loader riêng, lỗi cấu hình service có thể xuất hiện dù descriptor ghi đúng tên provider.

Demo chủ động gọi `loader.loadClass` rồi cast để làm nổi bật cơ chế parent-child, **không** gọi `ServiceLoader`. Muốn dùng `ServiceLoader` trên bytecode memory map, phải triển khai thêm khả năng khám phá provider (resource `META-INF/services` hoặc thiết kế module phù hợp), không chỉ copy đoạn code và kỳ vọng loader tự biết tên service.

Một số framework còn dựa vào **thread context class loader (TCCL)**. Gán TCCL cho plugin mà quên khôi phục sẽ làm thread pool dùng sai class/resource ở tác vụ tiếp theo và giữ tham chiếu tới loader cũ. Khi cần thay TCCL cho một lời gọi đồng bộ, phải dùng `try/finally` để phục hồi trạng thái cũ.

### 8.3. JPMS và ModuleLayer

Ví dụ sử dụng **unnamed modules/classpath** để API Java đơn giản và có thể chạy độc lập. Với **named modules**, lớp do `defineClass` vào custom loader không tự động trở thành một module có descriptor `module-info.class`. `ModuleLayer` và `Configuration.resolve` là quy trình khác: tìm module, giải quyết graph, định nghĩa layer cùng các loader tương ứng. Không suy luận rằng “compile vào byte[] + new ClassLoader” tự hoàn thành module resolution.

Khi sử dụng shared SPI thuộc named module, cần thêm `requires`, `exports`/`opens` và khả năng đọc module thích hợp. Ngược lại, API trong unnamed module và plugin trong named module có các giới hạn JPMS riêng; phải chọn mô hình deploy đúng thay vì áp một classpath demo lên mọi runtime.

## 9. Bảo mật, hiệu năng và vòng đời

### 9.1. Code động không phải code an toàn

Việc biên dịch source trong bộ nhớ rồi nạp bằng loader riêng **không tạo sandbox bảo mật**. Plugin có thể gọi API mà host/runtime cho phép, truy cập file/mạng hoặc sử dụng reflection tùy environment. JavaCompiler còn có thể chạy **annotation processors** có trên compiler path nếu được cấu hình/phát hiện theo cơ chế đang dùng; chúng là code thực thi trong quá trình build/compile, không phải dữ liệu thuần.

Với nguồn code không tin cậy, cần cô lập ở ranh giới hệ điều hành/tiến trình, hạn chế quyền, filesystem/network, resource và quản lý thời gian thực thi. Có thể dùng `-proc:none` khi không cần annotation processing để tránh chạy processor do compiler tự tìm; nhưng điều đó **không** biến việc chạy bytecode plugin thành an toàn. Một chiến lược tốt hơn cho rule nghiệp vụ là DSL/hạn chế grammar hoặc chạy trong worker process có quota rõ ràng.

Nếu cho phép user nhập dữ liệu, không chèn trực tiếp vào Java source string như `String.formatted(userInput)` mà không thoát literal và xác thực. Trong demo, `value` chỉ nhận hai constant đã biết để giữ ví dụ dễ hiểu.

### 9.2. Bytecode size, time và memory

- Giới hạn độ dài source, số class output, dung lượng bytecode và số task compile đồng thời.
- Thu diagnostics có phân loại lỗi; không lưu vĩnh viễn mọi source/bytecode trong cache nếu không cần.
- Phân biệt chi phí **compile** (CPU/heap) với **class loading/linking** (heap/metaspace) và **thực thi plugin** (CPU, IO, bộ nhớ).
- Cache theo hash source + compiler options + API version khi phù hợp; không lấy hash source làm bằng chứng bytecode tương thích với runtime mới.
- Không lặp tạo loader mới không giới hạn cho cùng một request nhỏ nếu workload yêu cầu throughput lớn.

### 9.3. Unload là vấn đề của tham chiếu

`ClassLoader` không cung cấp thao tác “xóa class đã define” ngay lập tức. Khi nâng cấp:

1. Tạo loader mới và instance plugin mới.
2. Đăng ký instance mới, chuyển routing/callback một cách có kiểm soát.
3. Hủy registration của instance cũ.
4. Dọn task, listener, thread, TCCL và cache còn giữ tham chiếu tới `Class<?>`/instance/loader cũ.
5. Để GC có thể thu hồi loader và các class của nó khi không còn tham chiếu mạnh.

Một instance của plugin cũ vẫn dùng được nếu host còn giữ nó và class chưa bị thu hồi. Đây là đặc tính có ích cho chuyển đổi theo phiên bản, nhưng cũng là nguồn gây memory leak khi registry không hủy bản cũ.

## 10. Checklist kiểm thử hệ thống runtime compilation

1. **API tồn tại trước:** `Greeting.class` phải được host định nghĩa và truy cập bởi loader cha của plugin.
2. **Compiler trỏ đúng API:** tùy classpath/module path và Java baseline; không vô tình biên dịch dựa vào version khác.
3. **Không ghi plugin .class ra đĩa:** `getJavaFileForOutput` thu đúng map bytecode, kể cả nested/anonymous classes nếu có.
4. **Binary names chính xác:** `demo.plugin.Hello` trong source, output map và `loadClass` phải trùng nhau.
5. **Parent không shadow implementation:** khi cần bytecode mới, host classpath không có implementation cùng tên, hoặc loader policy đã được thiết kế đúng.
6. **Contract runtime identity:** `Greeting.class.isAssignableFrom(type)` true, cast về `Greeting` và method hoạt động.
7. **Hai generation độc lập:** cùng binary name nhưng loader khác nhau sẽ cho class identity khác nhau.
8. **Missing dependency:** lỗi lúc compile, nạp hay chạy được phân biệt rõ trong logs.
9. **Không leak loader:** test reload nhiều lần, thu hồi thread/cache/instance sau khi thay phiên bản.
10. **Không xem ClassLoader là sandbox:** kiểm soát độ tin cậy source, annotation processors, quyền thực thi, quotas và input escaping.

**Kết luận:** kiến trúc đúng cho **“nạp bytecode bằng loader mới có hợp đồng chung ở loader cha”** là: biên dịch source plugin bằng `JavaCompiler` với API host hợp lệ trên compiler path; thu bytecode vào map thông qua `JavaFileManager`; tạo **loader con mới** có parent là loader host; chỉ định nghĩa implementation/dependency thuộc plugin trong loader con; và cast instance qua **chính contract do parent định nghĩa**. Các plugin có thể thay version theo loader riêng mà vẫn giữ type identity ổn định tại ranh giới host–plugin.