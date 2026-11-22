# Kiểm tra khả năng gán kiểu rồi tạo đối tượng qua constructor phù hợp

## 1. Vấn đề trong quy trình biên dịch Java trong bộ nhớ

Khi ứng dụng nhận mã nguồn Java dưới dạng chuỗi, biên dịch bằng `JavaCompiler` và nạp bytecode thông qua một `ClassLoader` riêng, kết quả thường chỉ là một đối tượng `Class<?>`. **Biên dịch thành công** nghĩa là mã hợp lệ đối với compiler và các dependency nhìn thấy được; nó **không đảm bảo** lớp đã biên dịch là implementation mà host mong đợi, có thể tạo instance được hay có constructor đúng giao thức của host.

Ví dụ host định nghĩa hợp đồng:

~~~java
public interface Plugin {
    String greet(String name);
}
~~~

Host muốn tạo plugin từ tên nhị phân như `demo.generated.WithPrefix`, với một tham số cấu hình `String prefix` nếu lớp có constructor đó, hoặc constructor không tham số nếu không có. Những câu hỏi phải được xử lý đúng thứ tự:

1. Compilation có trả về thành công và sinh ra bytecode thật hay không?
2. Loader nào định nghĩa lớp từ bytecode? Nó có chia sẻ **đúng class/interface Plugin của host** không?
3. `Class<?>` vừa tải có **gán được** cho `Plugin` không?
4. Lớp đó có thể khởi tạo không (ví dụ không phải interface, abstract class hoặc enum không thể khởi tạo reflectively)?
5. Constructor nào khớp **chữ ký mong đợi**, có thể truy cập và được phép gọi?
6. `Constructor.newInstance(...)` có chạy thành công không, và instance cuối cùng có thể sử dụng theo hợp đồng hay không?

Quy trình an toàn về mặt kiểu là:

~~~text
Source String
    │
    ▼
JavaCompiler + JavaFileManager
    │ thành công và có byte[]
    ▼
Memory ClassLoader (parent chia sẻ API Plugin)
    │
    ▼
Class<?> candidate (tải nhưng chưa chủ động khởi tạo)
    │
    ├── không tương thích Plugin → từ chối
    ├── interface/abstract/không thể khởi tạo → từ chối
    ▼
Class<? extends Plugin> (asSubclass)
    │
    ├── chọn public constructor(String.class), nếu có
    └── nếu không có mới chọn public constructor()
    │
    ▼
Constructor.newInstance(...)
    │
    ▼
Plugin instance → chạy phương thức qua SPI chung
~~~

**Phạm vi bài học:** cách kiểm tra gán kiểu và khởi tạo phù hợp **sau khi compile/load bytecode trong bộ nhớ**. Compiler, file manager và loader được trình bày đủ để chạy ví dụ nhưng trọng tâm là ranh giới `Class<?>` → `Class<? extends Plugin>` → `Constructor` → instance.

## 2. Kiểm tra khả năng gán kiểu trước khi ép kiểu

### 2.1. Thứ tự của `isAssignableFrom`

Biểu thức đúng khi cần một implementation của `Plugin`:

~~~java
boolean accepted = Plugin.class.isAssignableFrom(candidate);
~~~

Ý nghĩa: một giá trị có runtime type `candidate` có thể được gán cho biến kiểu `Plugin` bằng phép chuyển đổi reference hợp lệ không? Nếu `candidate` implement `Plugin`, thừa kế lớp đã implement `Plugin`, hoặc chính là `Plugin`, kết quả là `true`. Trường hợp `candidate` **chính là interface Plugin** phải được kiểm tra thêm vì interface không khởi tạo được.

Dễ viết ngược:

~~~java
boolean reversed = candidate.isAssignableFrom(Plugin.class); // Không đúng mục tiêu
~~~

Phép đảo chiều hỏi “giá trị kiểu `Plugin` có gán được cho kiểu `candidate` không?”, thường không đúng khi candidate là implementation cụ thể. Một kiểm tra kiểu sai có thể cho kết quả từ chối implementation hợp lệ hoặc chấp nhận nhầm một superclass như `Object`.

So sánh:

| `candidate` | `Plugin.class.isAssignableFrom(candidate)` | Có thể trực tiếp tạo instance? |
|---|---|---|
| `WithPrefix implements Plugin` | `true` | Có, nếu class/constructor hợp lệ |
| `Defaulted implements Plugin` | `true` | Có, nếu class/constructor hợp lệ |
| `Unrelated`, không implement `Plugin` | `false` | Không được đưa vào nhánh khởi tạo plugin |
| `Plugin` interface | `true` | Không, interface không thể `new` |
| Abstract class implement `Plugin` | `true` | Không, class trừu tượng không thể khởi tạo |
| Enum implement `Plugin` | `true` | Không thể tạo enum bằng phản chiếu constructor |

`Class.isAssignableFrom` kiểm tra **quan hệ type ở JVM runtime**, không chỉ so tên class hoặc package. Nó không đảm bảo constructor phù hợp, các dependency đã hoạt động hoặc việc khởi tạo sẽ không có side effect.

### 2.2. `asSubclass` tạo lớp được giới hạn kiểu

Sau khi xác nhận:

~~~java
if (!Plugin.class.isAssignableFrom(candidate)) {
    throw new IllegalArgumentException("Incompatible class");
}
Class<? extends Plugin> implementation =
        candidate.asSubclass(Plugin.class);
~~~

`Class.asSubclass(Plugin.class)` xác nhận runtime và trả về `Class<? extends Plugin>`, nhờ đó có thể lấy `Constructor<? extends Plugin>` và tạo instance có kiểu phù hợp **không cần cast generic unchecked**. Nếu không tương thích, `asSubclass` ném `ClassCastException`. Kiểm tra `isAssignableFrom` trước giúp trả lỗi có chủ đích và phân biệt chính sách của host với lỗi ép kiểu.

Nếu đã có **đối tượng** thay vì `Class<?>`, có thể dùng `Plugin.class.isInstance(value)` và `Plugin.class.cast(value)`. Nhưng `isInstance` yêu cầu instance đã tồn tại; trong bài này phải đánh giá class **trước khi gọi constructor**.

### 2.3. Class loader quyết định định danh kiểu

Trong JVM, định danh runtime của một lớp gồm **binary class name** và **defining class loader**. Hai interface đều có tên `demo.api.Plugin` nhưng được định nghĩa bởi hai loader khác nhau có thể là hai kiểu không tương thích:

~~~text
Host parent loader:  demo.api.Plugin  (type A)
Plugin child loader: demo.api.Plugin  (type B)
                                 A != B
~~~

Nếu `candidate` implement “Plugin type B”, còn host kiểm tra “Plugin type A”, `Plugin.class.isAssignableFrom(candidate)` trả `false` dù `candidate.getInterfaces()[0].getName()` trông giống nhau. Vì vậy **không** xác thực bằng `getName().equals(...)`.

Trong hệ thống plugin thông thường, parent loader của loader biên dịch trong bộ nhớ nên trỏ tới loader đã định nghĩa **API/SPI của host** (ví dụ `Plugin.class.getClassLoader()`). Host tránh tự compile/định nghĩa một bản sao của interface hợp đồng trong memory loader, trừ khi đã chủ động thiết kế cầu nối giữa hai identity khác nhau.

## 3. Tải class đúng thời điểm, tránh khởi tạo quá sớm

Sau khi compile, host thường biết `binaryName` và có `ClassLoader` mới. Có thể dùng:

~~~java
Class<?> raw = Class.forName(binaryName, false, memoryLoader);
~~~

Tham số `false` yêu cầu **không chủ động khởi tạo class** tại lời gọi này. Điều đó cho phép kiểm tra type, modifiers và constructor trước khi kích hoạt static initializer của implementation qua bước tạo instance sau đó. Nó **không** biến thao tác nạp/link thành vô hại: verification, resolution, lookup và class-loader code vẫn có thể gặp lỗi hoặc có hành vi riêng.

Một lựa chọn khác là `memoryLoader.loadClass(binaryName)`, thường cũng chưa khởi tạo class ngay. Đừng dùng `Class.forName(binaryName)` không truyền loader khi ứng dụng đang quản lý plugin trong loader riêng: overload này dùng **defining loader của caller** và yêu cầu initialize mặc định, có thể tìm nhầm lớp hoặc ném lỗi vì loader không nhìn thấy bytecode.

Đọc metadata trước khi tạo instance:

~~~java
if (raw.isInterface()
        || java.lang.reflect.Modifier.isAbstract(raw.getModifiers())) {
    throw new IllegalArgumentException("Not a concrete plugin");
}
~~~

Hệ thống production cũng nên xem xét từ chối `isEnum()`, anonymous/local class, implementation không public nếu hợp đồng chỉ nhận public class, hoặc kiểu không nằm trong tập package/module được cho phép. **Một check assignability thành công không thay thế kiểm tra chính sách khởi tạo.**

## 4. Chọn constructor phù hợp với hợp đồng

### 4.1. `getConstructor` tìm public constructor theo chữ ký *chính xác*

Nếu host ưu tiên constructor nhận `String`:

~~~java
Constructor<? extends Plugin> constructor =
        implementation.getConstructor(String.class);

Plugin plugin = constructor.newInstance("Xin chao");
~~~

`getConstructor(String.class)` tìm constructor **public** có đúng một tham số khai báo kiểu `java.lang.String`. Nó không tự suy luận các overload theo quy tắc Java compiler dùng khi bạn viết lệnh `new` trong mã nguồn.

Ví dụ:

~~~java
public WithPrefix(String prefix) { ... }
public WithPrefix(CharSequence text) { ... }
public WithPrefix(int count) { ... }
~~~

Ba constructor trên là ba chữ ký khác nhau. `getConstructor(String.class)` chọn đúng nhánh `String`. `getConstructor(CharSequence.class)` không đồng nghĩa tìm constructor `String`, và `getConstructor()` tìm constructor **không tham số**, không tự truyền giá trị mặc định.

`Constructor.newInstance(args...)` gọi constructor đã chọn và chuyển đối số theo các quy tắc reflection tương ứng; nếu sai số lượng/kiểu đối số, có thể ném `IllegalArgumentException`. Tốt nhất host xác lập trước một **hợp đồng constructor cụ thể** (ví dụ `(Config)`, `(String)` hoặc `()`) và tra cứu chữ ký đó, thay vì tùy tiện lấy constructor đầu tiên từ `getConstructors()`.

### 4.2. Fallback hợp lý: chỉ khi *không có* constructor ưu tiên

~~~java
try {
    Constructor<? extends Plugin> preferred =
            implementation.getConstructor(String.class);
    return preferred.newInstance(prefix);
} catch (NoSuchMethodException missingPreferred) {
    Constructor<? extends Plugin> fallback =
            implementation.getConstructor();
    return fallback.newInstance();
}
~~~

Điểm quan trọng: khối `catch` chỉ bắt **`NoSuchMethodException`** từ việc **không tìm được chữ ký**. Nếu constructor `String` có tồn tại nhưng thực thi thất bại (ví dụ ném exception), **không nên im lặng gọi constructor mặc định** vì sẽ che giấu lỗi thật và có thể lặp side effect.

`getConstructor()` cũng có thể ném `NoSuchMethodException` nếu không có public no-arg constructor. Khi đó host nên trả lỗi rõ “không có constructor phù hợp”, thay vì chuyển sang `Class.newInstance()`.

### 4.3. `getDeclaredConstructor` và module access

`getDeclaredConstructor(...)` tìm constructor **được khai báo** ở class, kể cả private/package-private; việc tìm được descriptor không tự có quyền gọi nó. `getConstructor(...)` chỉ tìm public constructor theo chữ ký. Trong mô hình plugin public SPI, nên ưu tiên **public class + public constructor** để giảm phụ thuộc reflection phá encapsulation.

`setAccessible(true)` hoặc `trySetAccessible()` không phải cách chung để sửa lỗi quyền truy cập. Với named modules JPMS, deep reflection còn bị giới hạn bởi `opens`, caller module và các quy tắc access; thiếu quyền có thể gây `InaccessibleObjectException` hoặc `IllegalAccessException`. Đừng tự động mở mọi package chỉ vì có lỗi nạp plugin.

### 4.4. Vì sao không dùng `Class.newInstance()`?

`Class.newInstance()` đã deprecated từ Java 9. Nó chỉ dùng constructor không tham số và có hành vi xử lý checked exception kém rõ ràng hơn. API được khuyến nghị là `clazz.getDeclaredConstructor().newInstance()` khi phù hợp, hoặc `getConstructor(signature...).newInstance(args...)` theo hợp đồng. Với bài toán cần chọn constructor thích hợp, `Constructor` API thể hiện chính xác yêu cầu hơn.

## 5. Ví dụ Java 17+ hoàn chỉnh: compile bytecode vào memory, kiểm tra type và khởi tạo

Ví dụ sau **biên dịch và chạy độc lập** khi có JDK 17+. Nó tạo ba class động từ chuỗi nguồn:

1. `WithPrefix` implement `Plugin` và có public constructor `(String)`.
2. `Defaulted` implement `Plugin` và chỉ có public constructor không tham số.
3. `Unrelated` không implement `Plugin` và phải bị từ chối **trước khi gọi constructor**.

Mã host `InMemoryCtorDemo` được biên dịch bình thường vào thư mục `out`; **ba class động** được compiler đưa bytecode vào `ByteArrayOutputStream` và được loader tự định nghĩa, không phải viết ra `.class` trên đĩa.

### 5.1. Tạo file

Lưu toàn bộ mã sau trong **`demo/InMemoryCtorDemo.java`** (thư mục `demo` khớp khai báo package `demo`). Java text blocks dùng ở đây có từ Java 15 và tương thích Java 17.

~~~java
package demo;

import java.io.ByteArrayOutputStream;
import java.io.OutputStream;
import java.lang.reflect.Constructor;
import java.lang.reflect.Modifier;
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

public final class InMemoryCtorDemo {
    public interface Plugin {
        String greet(String name);
    }

    public static void main(String[] args) throws Exception {
        String withPrefix = """
                package demo.generated;
                import demo.InMemoryCtorDemo.Plugin;
                public final class WithPrefix implements Plugin {
                    private final String prefix;
                    public WithPrefix(String prefix) { this.prefix = prefix; }
                    public String greet(String name) { return prefix + ", " + name + "!"; }
                }
                """;
        String defaulted = """
                package demo.generated;
                import demo.InMemoryCtorDemo.Plugin;
                public final class Defaulted implements Plugin {
                    public Defaulted() {}
                    public String greet(String name) { return "Hello, " + name + "!"; }
                }
                """;
        String unrelated = """
                package demo.generated;
                public final class Unrelated {
                    public Unrelated() {}
                }
                """;

        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("A JDK compiler is required");
        }
        DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
        Map<String, byte[]> classBytes;
        try (StandardJavaFileManager standard =
                     compiler.getStandardFileManager(diagnostics, null, StandardCharsets.UTF_8);
             MemoryManager manager = new MemoryManager(standard)) {
            List<JavaFileObject> sources = List.of(
                    new Source("demo.generated.WithPrefix", withPrefix),
                    new Source("demo.generated.Defaulted", defaulted),
                    new Source("demo.generated.Unrelated", unrelated));
            Boolean ok = compiler.getTask(null, manager, diagnostics,
                    List.of("--release", "17", "-classpath",
                            System.getProperty("java.class.path"), "-proc:none"),
                    null, sources).call();
            if (!Boolean.TRUE.equals(ok)) {
                diagnostics.getDiagnostics().forEach(System.err::println);
                throw new IllegalStateException("Compilation failed");
            }
            classBytes = manager.classBytes();
        }

        ClassLoader loader =
                new MemoryClassLoader(Plugin.class.getClassLoader(), classBytes);
        Class<?> with = Class.forName("demo.generated.WithPrefix", false, loader);
        System.out.println("WithPrefixAssignable=" + Plugin.class.isAssignableFrom(with));
        Plugin first = createPlugin(with, "Xin chao");
        System.out.println("WithPrefix=" + first.greet("Java"));

        Class<?> fallback = Class.forName("demo.generated.Defaulted", false, loader);
        System.out.println("DefaultedAssignable=" + Plugin.class.isAssignableFrom(fallback));
        Plugin second = createPlugin(fallback, "unused");
        System.out.println("Defaulted=" + second.greet("Java"));

        Class<?> other = Class.forName("demo.generated.Unrelated", false, loader);
        System.out.println("UnrelatedAssignable=" + Plugin.class.isAssignableFrom(other));
        boolean rejected = false;
        try {
            createPlugin(other, "unused");
        } catch (IllegalArgumentException expected) {
            rejected = true;
        }
        System.out.println("UnrelatedRejected=" + rejected);
    }

    private static Plugin createPlugin(Class<?> raw, String argument)
            throws ReflectiveOperationException {
        if (!Plugin.class.isAssignableFrom(raw)) {
            throw new IllegalArgumentException("Not a Plugin: " + raw.getName());
        }
        if (raw.isInterface() || Modifier.isAbstract(raw.getModifiers())) {
            throw new IllegalArgumentException("Not concrete: " + raw.getName());
        }

        Class<? extends Plugin> type = raw.asSubclass(Plugin.class);
        try {
            Constructor<? extends Plugin> constructor =
                    type.getConstructor(String.class);
            System.out.println("Chosen=" + raw.getSimpleName() + ":String");
            return constructor.newInstance(argument);
        } catch (NoSuchMethodException missingStringConstructor) {
            Constructor<? extends Plugin> constructor =
                    type.getConstructor();
            System.out.println("Chosen=" + raw.getSimpleName() + ":no-arg");
            return constructor.newInstance();
        }
    }

    private static final class Source extends SimpleJavaFileObject {
        private final String source;
        Source(String binaryName, String source) {
            super(URI.create("string:///" + binaryName.replace('.', '/')
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
        ByteCode(String binaryName, Kind kind) {
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

    private static final class MemoryManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        private final Map<String, ByteCode> compiled = new HashMap<>();
        MemoryManager(StandardJavaFileManager delegate) {
            super(delegate);
        }
        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location, String className,
                JavaFileObject.Kind kind, FileObject sibling) {
            ByteCode output = new ByteCode(className, kind);
            compiled.put(className, output);
            return output;
        }
        Map<String, byte[]> classBytes() {
            Map<String, byte[]> result = new HashMap<>();
            compiled.forEach((name, output) ->
                    result.put(name, output.toByteArray()));
            return result;
        }
    }

    private static final class MemoryClassLoader extends ClassLoader {
        private final Map<String, byte[]> bytecode;
        MemoryClassLoader(ClassLoader parent, Map<String, byte[]> bytecode) {
            super(parent);
            this.bytecode = Map.copyOf(bytecode);
        }
        @Override
        protected Class<?> findClass(String name) throws ClassNotFoundException {
            byte[] bytes = bytecode.get(name);
            if (bytes == null) {
                throw new ClassNotFoundException(name);
            }
            return defineClass(name, bytes, 0, bytes.length);
        }
    }
}
~~~

### 5.2. Biên dịch và chạy

Từ thư mục **cha của `demo/`**, chạy trên Bash (Linux/macOS hoặc Git Bash trên Windows):

~~~bash
mkdir -p out
javac --release 17 -d out demo/InMemoryCtorDemo.java
java -cp out demo.InMemoryCtorDemo
~~~

Trên PowerShell, tạo `out` bằng `New-Item -ItemType Directory -Force out`; hai lệnh `javac`/`java` phía trên cũng chạy được nếu JDK nằm trên `PATH`. `--release 17` kiểm tra cú pháp và API của host theo Java 17; trong mã, compiler động cũng được truyền `--release 17`.

Kết quả chuẩn của chương trình:

~~~text
WithPrefixAssignable=true
Chosen=WithPrefix:String
WithPrefix=Xin chao, Java!
DefaultedAssignable=true
Chosen=Defaulted:no-arg
Defaulted=Hello, Java!
UnrelatedAssignable=false
UnrelatedRejected=true
~~~

Đã kiểm tra ví dụ bằng `javac --release 17` và chạy trên OpenJDK 24: kết quả đúng **từng dòng** như trên. Nếu dùng runtime chỉ cung cấp các module tối thiểu và không có compiler, `ToolProvider.getSystemJavaCompiler()` có thể trả `null`; ví dụ yêu cầu một JDK/runtime image có module `jdk.compiler`.

### 5.3. Nối từng thành phần của mã với cơ chế Java

**`Source`** mở rộng `SimpleJavaFileObject` kiểu `Kind.SOURCE`. Nó cung cấp nội dung source bằng `getCharContent` từ chuỗi, nên compiler không phải đọc `WithPrefix.java` hoặc `Defaulted.java` từ đĩa.

**`ByteCode`** là `JavaFileObject` kiểu output, trả `ByteArrayOutputStream` khi compiler cần ghi class bytes. **`MemoryManager`** là `ForwardingJavaFileManager` chặn `getJavaFileForOutput` rồi giữ các `ByteCode` theo **binary name**. Nếu một source sinh thêm class phụ (inner/anonymous class), file manager có thể nhận thêm các output tương ứng; loader cần giữ các bytecode này, không chỉ class top-level.

**`compiler.getTask(...).call()`** chạy compiler. Kiểm tra `Boolean.TRUE.equals(ok)` trước khi nạp bất kỳ class nào. Trong một hệ thống thật, còn cần xem `DiagnosticCollector` để trả lỗi có vị trí dòng/cột cho người viết source; không được bỏ qua compile failure hoặc tiếp tục với bytecode cũ từ lần biên dịch trước.

**`MemoryClassLoader`** giữ bản sao map tên binary → bytecode và override `findClass`. Nó dùng parent là `Plugin.class.getClassLoader()`, nhờ đó ba class động nhìn thấy **cùng interface Plugin** mà host sử dụng. `ClassLoader.loadClass` mặc định thử parent trước; `findClass` chỉ định nghĩa class từ bytes khi parent không có class đó.

**`Class.forName(name, false, loader)`** cho host một `Class<?>` của class động trong memory loader mà chưa chủ động initialize. Host gọi `Plugin.class.isAssignableFrom(raw)` để kiểm tra trước khi dùng `asSubclass`; sau đó chọn public constructor. Với `WithPrefix`, nó dùng `(String)`, với `Defaulted` fallback `()`, còn `Unrelated` bị từ chối trước khi dùng reflection constructor.

**`-classpath System.getProperty("java.class.path")`** trong compiler động giúp compiler thấy bytecode interface `demo.InMemoryCtorDemo.Plugin` đã biên dịch trong `out`. Đây là một cách đơn giản và phù hợp với ví dụ **classpath**; ứng dụng thực tế sử dụng module path, nhiều loader hay annotation processor cần cấu hình compiler/module path/file manager rõ ràng hơn. Cờ `-proc:none` tắt annotation processing trong ví dụ; không nên mặc định cho compiler thực thi processor không tin cậy trong tiến trình host.

### 5.4. Tại sao nên viết generic `Class<? extends Plugin>`?

Một cách làm nguy hiểm là:

~~~java
Class<?> raw = loader.loadClass(binaryName);
Object value = raw.getDeclaredConstructor().newInstance();
Plugin plugin = (Plugin) value;
~~~

Đoạn minh họa này có hai vấn đề: nó **không xác thực class theo SPI trước khi khởi tạo**, và **chỉ dùng no-arg constructor** dù provider có thể yêu cầu cấu hình. Nếu class không tương thích, constructor có thể đã chạy rồi mới ném `ClassCastException` ở bước ép kiểu. Với plugin không mong muốn, side effect của constructor có thể xảy ra trước khi host kịp từ chối.

Quy trình đúng ưu tiên:

~~~java
if (!Plugin.class.isAssignableFrom(raw)) {
    throw new IllegalArgumentException("Not a Plugin");
}
Class<? extends Plugin> type = raw.asSubclass(Plugin.class);
Constructor<? extends Plugin> ctor = type.getConstructor(String.class);
Plugin plugin = ctor.newInstance("Xin chao");
~~~

Đây là **đoạn minh họa rút gọn** cho trường hợp constructor `String` tồn tại; chương trình hoàn chỉnh có nhánh fallback khi constructor này không có.

## 6. Những lỗi cần phân biệt đúng giai đoạn

| Vấn đề | Dấu hiệu/lỗi thường gặp | Cách xử lý |
|---|---|---|
| Source Java không hợp lệ | Compiler trả `false`, có `Diagnostic.Kind.ERROR` | Đọc diagnostics, không nạp bytecode của lần biên dịch lỗi |
| Compiler không sẵn có | `ToolProvider.getSystemJavaCompiler() == null` | Chạy trên JDK/runtime image có `jdk.compiler` |
| Loader không có bytecode hoặc dependency | `ClassNotFoundException` | Kiểm tra binary name, map bytecode và parent/classpath |
| Một dependency chỉ thiếu khi linking | `NoClassDefFoundError`/`LinkageError` | Xem cause, loader, class/module path và dependency |
| Interface cùng tên nhưng khác defining loader | `isAssignableFrom == false` hoặc `ClassCastException` về sau | Chia sẻ đúng class object `Plugin` giữa host/plugin |
| Candidate không implements SPI | `isAssignableFrom == false` | Từ chối trước khi tìm constructor |
| Candidate là interface/abstract | `isAssignableFrom` có thể `true` nhưng không thể tạo instance | Kiểm tra modifiers; không chỉ dựa vào quan hệ kiểu |
| Thiếu constructor có chữ ký yêu cầu | `NoSuchMethodException` | Chọn fallback được định nghĩa rõ, nếu không có thì báo lỗi hợp đồng |
| Public constructor nhưng class/package không truy cập được | `IllegalAccessException` hoặc lỗi access JPMS | Kiểm tra public class, exports/opens phù hợp và caller module |
| Sai kiểu/số đối số khi gọi constructor | `IllegalArgumentException` | Chọn chữ ký đúng, kiểm tra arguments đúng thứ tự và kiểu |
| Constructor tự ném exception | `InvocationTargetException`; dùng `getCause()` | Ghi cause thật, coi đây là lỗi khi khởi tạo; không fallback im lặng |
| Static initializer thất bại | `ExceptionInInitializerError`, có thể dẫn đến `NoClassDefFoundError` ở lần sau | Phân tích initializer/cause và trạng thái loader, không tái sử dụng class lỗi tùy tiện |
| Tên lớp đã định nghĩa trùng trong cùng loader | `LinkageError` trong tình huống define trùng | Quản lý map bytecode, generation/version và tạo loader mới khi thay implementation |
| Dùng JAR/plugin từ nguồn không tin cậy | Không có lỗi đảm bảo trước khi thực thi | Cách ly ở cấp process/container; không coi type check là sandbox |

### `InvocationTargetException`: xem lỗi gốc

Khi constructor **đã được chọn và gọi**, exception do code constructor ném thường được bọc trong `InvocationTargetException`. Một ví dụ xử lý riêng ở tầng host:

~~~java
try {
    return constructor.newInstance(arguments);
} catch (java.lang.reflect.InvocationTargetException e) {
    Throwable original = e.getCause();
    // Ghi log hoặc chuyển thành lỗi domain có gắn nguyên nhân gốc.
    throw e;
}
~~~

Đây là đoạn **minh họa tích hợp**: giả định đã có `Constructor<?> constructor` và `Object[] arguments`. Phải giữ original cause để chẩn đoán. Không được lấy việc constructor ném lỗi làm tín hiệu để thử một constructor khác một cách vô điều kiện, vì constructor có thể đã thay đổi state trước khi thất bại.

### `getDeclaredConstructor` không tự vượt qua JPMS

Một class thuộc named module có package không `exports` hoặc `opens` cho module host có thể từ chối truy cập phản chiếu sâu. Việc lấy được object `Constructor` chưa có nghĩa được phép `newInstance`. Khi thiết kế plugin hợp đồng public, cung cấp public constructor trong class public thuộc module/package có access policy phù hợp; nếu cần private constructor do framework quản lý, phải thiết kế `opens` và quyền truy cập tường minh.

## 7. Chọn constructor khi hệ thống thực tế phức tạp hơn

Một host production thường có nhiều dependency injection và cấu hình; không nên phản chiếu “constructor đầu tiên” rồi chọn đối số theo cảm tính.

- **Quy ước một chữ ký**: interface provider yêu cầu public constructor `(PluginConfig)` hoặc factory method, host biết chính xác cách cung cấp `PluginConfig`. Ưu điểm: lỗi rõ ở deployment.
- **Quy ước thứ tự ưu tiên**: thử `(PluginConfig)`, nếu *không tìm thấy* mới thử `()`; áp dụng chính sách cố định và log constructor được chọn. Bài chạy được minh họa với `(String)` và `()`.
- **Chọn theo metadata**: plugin descriptor công bố kiểu constructor/định danh factory được hỗ trợ, nhưng cần kiểm tra metadata bằng reflection trước khi invoke.
- **Dùng factory/SPI**: nếu khởi tạo phức tạp hoặc cần nhiều dependency, có thể để plugin cung cấp factory được đăng ký qua `ServiceLoader`; đừng tạo phụ thuộc vào public constructor chỉ vì reflection dễ viết.
- **Constructor varargs hoặc primitive/wrapper**: `getConstructor` tra cứu **chính xác danh sách kiểu khai báo**, không thực hiện overload resolution như javac. Ví dụ `getConstructor(int.class)` khác `getConstructor(Integer.class)`; xử lý chuyển đổi args khi invoke là một bước khác.
- **Nested non-static classes**: constructor phản chiếu của inner class không static còn có tham số instance bao ngoài; nếu không có quy ước rõ thì plugin nên là top-level class hoặc static nested class.
- **Records/enums**: record có thể có public canonical constructor đúng chữ ký, nhưng enum không thể được tạo bằng cách gọi constructor reflectively; API service nên quy định loại provider được chấp nhận.

Nếu cần hỗ trợ non-public constructor, hãy nêu rõ yêu cầu về module access thay vì tự động `setAccessible(true)` cho mọi thứ. Nếu phải reload plugin, dùng class loader/layer mới; thay chuỗi source hoặc map bytecode của một loader đã định nghĩa class không tự làm JVM thay class cũ.

## 8. Bộ quy tắc kiểm tra trước khi kích hoạt plugin

Đối với một bước biên dịch trong bộ nhớ và tạo plugin tự động, host có thể xây một pipeline như sau:

1. **Source hợp lệ:** giới hạn class name, source size, dependencies và compilation options được chấp nhận; thông báo lỗi từ `DiagnosticCollector`.
2. **Compile thành công:** xác nhận `getTask().call()` là `true`; biết bytecode nào được sinh và class nào là entry point.
3. **Loader đồng nhất:** tạo loader đúng parent cho SPI; không định nghĩa trùng interface host trong loader con.
4. **Tải class đúng tên:** dùng binary name đã biết và loader cụ thể, ưu tiên chưa initialize khi kiểm tra.
5. **Type check:** `ExpectedService.class.isAssignableFrom(candidate)` theo đúng thứ tự.
6. **Instantiation policy:** class không phải interface/abstract/enum; visibility/module access phù hợp; chọn constructor theo quy ước.
7. **Instantiate:** gọi `Constructor.newInstance(...)`, giữ nguyên cause khi exception và không retry nhánh khác nếu constructor đã được gọi nhưng thất bại.
8. **Register/lifecycle:** kiểm tra instance thực hiện hợp đồng, sau đó mới đăng ký vào host; có quy trình stop/dispose khi thay phiên bản.

Type checking **không tạo ranh giới bảo mật**. Java compiler, class loader và constructor có thể xử lý mã mà sau này được chạy với quyền của tiến trình. Với mã do người dùng hoặc bên thứ ba không tin cậy gửi lên, cần cơ chế cô lập riêng, giới hạn tài nguyên, chính sách dependency và đánh giá quyền truy cập.

Ngoài ra, compiler/file manager cần được đóng sau khi sử dụng. Với hệ thống biên dịch nhiều lần, quản lý cache và class loader theo mỗi generation để tránh giữ bytecode, class objects, static state, threads hoặc listener vô hạn. Việc loại bỏ các tham chiếu và để JVM thu gom class loader là điều kiện để class của generation cũ có thể được dọn.

## 9. Câu hỏi tự kiểm tra

1. **Tại sao compile thành công chưa đủ để ép `Class<?>` thành `Plugin`?** Vì compiler chỉ xác nhận source hợp lệ; implementation có thể không implements SPI hoặc dùng interface có runtime identity khác.
2. **Biểu thức nào đúng: `Plugin.class.isAssignableFrom(raw)` hay `raw.isAssignableFrom(Plugin.class)`?** Biểu thức đầu, vì cần xác minh candidate có thể gán vào biến `Plugin`.
3. **`isAssignableFrom == true` có đảm bảo tạo instance được không?** Không. Class có thể abstract/interface, thiếu constructor, bị hạn chế quyền hoặc constructor có thể thất bại.
4. **Vì sao dùng `raw.asSubclass(Plugin.class)`?** Để nhận `Class<? extends Plugin>` đã được xác thực runtime, giảm cast generic không an toàn.
5. **Khi nào được thử constructor không tham số?** Khi hợp đồng cho phép fallback và constructor ưu tiên **không tồn tại** (`NoSuchMethodException`), không phải khi invocation đã thất bại.
6. **`getConstructor(String.class)` có tự tìm constructor `(CharSequence)` hay `(Object)` không?** Không; tra cứu chữ ký chính xác, khác với overload resolution của javac.
7. **Đổi `Class.forName(name, true, loader)` thành `Class.forName(name, false, loader)` giúp gì?** Cho phép kiểm tra class metadata trước khi chủ động initialize class; không biến mã untrusted thành an toàn.
8. **Hai interface cùng binary name nhưng do hai loader khác nhau định nghĩa có giống nhau không?** Không. Class identity phụ thuộc defining loader.
9. **Nếu `Constructor.newInstance` ném `InvocationTargetException`, nên làm gì?** Đọc `getCause()`, thông báo lỗi khởi tạo; không tự động chạy constructor khác.
10. **Khi đổi source và compile lại, có thể dùng cùng loader đã định nghĩa class cũ để thay bytecode không?** Không thể chỉ thay map bytes rồi mong class đã định nghĩa đổi theo. Thường cần loader/layer mới và quản lý generation rõ ràng.

**Ghi nhớ:** sau biên dịch trong bộ nhớ, hãy **xác nhận type compatibility trước khi khởi tạo**, dùng **`asSubclass`** để thu hẹp `Class<?>` một cách an toàn, **chọn đúng public constructor theo chữ ký đã cam kết** và xử lý riêng lỗi thiếu constructor với lỗi constructor thực thi thất bại. Đồng thời, host và implementation phải dùng **cùng runtime identity của SPI**, nếu không những class cùng tên vẫn có thể không gán kiểu được.

## Tài liệu tham khảo

- [Java SE 17 — `Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `isAssignableFrom`, `asSubclass`, `getConstructor`, `getDeclaredConstructor` và `Class.forName`.
- [Java SE 17 — `Constructor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Constructor.html): `newInstance` và các exception khi reflection.
- [Java SE 17 — `JavaCompiler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html) và [`ForwardingJavaFileManager`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html): compiler task và ghi output trong bộ nhớ.
- [Java SE 17 — `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findClass`, `defineClass` và class identity.
