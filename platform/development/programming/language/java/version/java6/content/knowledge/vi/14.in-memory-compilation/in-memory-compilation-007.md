# Vòng đời ClassLoader và tránh giữ lớp không còn dùng khi biên dịch trong bộ nhớ

## 1. Bối cảnh: vì sao code biên dịch động có thể giữ bộ nhớ lâu?

Java Compiler API (`javax.tools.JavaCompiler`) cho phép ứng dụng nhận mã Java dưới dạng chuỗi, biên dịch thành bytecode và lưu đầu ra trong bộ nhớ. Để **sử dụng** bytecode, ứng dụng tạo `ClassLoader` rồi nạp/định nghĩa các class từ mảng byte. Cơ chế này thường có trong rule engine, plugin engine, IDE, template compiler hoặc hệ thống kiểm tra code.

Vấn đề nảy sinh khi mã nguồn được cập nhật liên tục: mỗi bản mới tạo các class mới, nhưng phiên bản cũ có thể vẫn sống vì listener, cache, thread, instance, reflection hoặc service registry còn giữ tham chiếu. Sau nhiều lượt biên dịch/nạp phiên bản, **heap và class metadata (metaspace trong HotSpot)** có thể tiếp tục tăng nếu các loader cũ không thể được thu hồi.

Hai kết luận nền tảng:

- **Ứng dụng điều khiển vòng đời của phiên bản:** chọn lúc tạo, ngừng nhận tác vụ, đóng tài nguyên, bỏ tham chiếu tới loader và instance cũ.
- **JVM điều khiển class unloading:** khi defining class loader có thể được thu hồi, JVM *có thể* unload các class do nó định nghĩa; **không có thời điểm unload được bảo đảm**.

Đừng nhầm “compile xong”, “đã gọi close”, “đã gán biến bằng null” với “class chắc chắn đã unload”. Tất cả giải thích dưới đây tập trung vào Java **17+** và các API còn sử dụng hiện nay.

## 2. Hiểu đúng ba vòng đời khác nhau

| Đối tượng | Được tạo khi nào? | Khi hết dùng cần làm gì? |
| --- | --- | --- |
| Source/bytecode `JavaFileObject`, `byte[]`, `JavaFileManager` | Trong mỗi lần `CompilationTask.call()` | Đóng file manager, bỏ buffer/cache không cần thiết |
| `ClassLoader`, `Class<?>` và object được tạo từ class động | Khi nạp/định nghĩa và gọi class | Ngừng hoạt động phiên bản, đóng resource nghiệp vụ, loại bỏ các **strong references** |
| Runtime class metadata | JVM tạo khi load/link | JVM tự chọn lúc reclaim/unload khi defining loader đủ điều kiện; không có API phổ thông ép unload từng class |

~~~text
String source
    │ JavaCompiler.getTask(...).call()
    ▼
byte[] class file (trong MemoryFileManager)
    │ new MemoryLoader(...).loadClass(...)
    ▼
Class<?> (gắn với defining ClassLoader)
    │ reflection / new instance
    ▼
object đang phục vụ request
    │ stop traffic → drain → close/deregister
    ▼
không còn strong reference giữ version/loader cũ
    │ điều kiện reachability của JVM
    ▼
GC có thể reclaim loader; JVM có thể unload class sau đó
~~~

### Biên dịch ≠ nạp ≠ thực thi

`CompilationTask.call()` chỉ biên dịch và báo thành công/thất bại. Nó không tự tạo ClassLoader ứng dụng, không thay thế class đã nạp và không thực thi các phương thức của class vừa biên dịch. `ClassLoader#defineClass` dùng bytecode để định nghĩa class ở một loader; `ClassLoader#loadClass` thường tìm class đã nạp, **ủy quyền cho parent**, rồi mới gọi `findClass` nếu cần. Tạo một object hoặc invoke method sau đó là một bước riêng.

### Class identity: cùng tên vẫn có thể khác kiểu

Trong JVM, runtime class được nhận diện bằng **binary name và defining class loader**. Hai class cùng tên nhưng do hai loader khác nhau tự định nghĩa là **hai kiểu khác nhau**. Chẳng hạn:

~~~java
Class<?> oldType = oldLoader.loadClass("demo.Message");
Class<?> newType = newLoader.loadClass("demo.Message");

boolean namesEqual = oldType.getName().equals(newType.getName()); // true
boolean sameType = oldType == newType;                            // false
~~~

Đoạn trên là **mã minh họa**, cần có hai loader thực sự định nghĩa `demo.Message`. Chỉ tạo hai instance `ClassLoader` chưa đủ để kết luận kiểu khác nhau: nếu **parent** đã định nghĩa class đó, parent-first delegation có thể trả **cùng một `Class<?>`** ở cả hai lời gọi.

Để nạp bản v2 với cùng binary name mà không thay đổi lớp đã định nghĩa bởi loader v1, mô hình thường dùng là **loader riêng cho mỗi version**. Một loader thông thường không thể gọi lại `defineClass` với cùng binary name để ghi đè phiên bản đang có; hành vi đó có thể ném `LinkageError`.

**Ranh giới API:** Nếu plugin implements một interface chung (ví dụ `Plugin`), hãy đặt interface ở class loader dùng chung do host sở hữu, còn implementation ở child loader riêng. Không để host/plugin vô tình biên dịch và nạp hai bản riêng của chính interface giao tiếp, vì điều đó có thể gây `ClassCastException` và lỗi assignability.

## 3. Điều kiện để classloader cũ có thể được thu hồi

Java Language Specification `12.7 nêu: một class/interface chỉ có thể được unload khi **defining class loader** của nó có thể được garbage collector thu hồi. Không thể unload riêng tùy ý một class từ một loader vẫn còn reachable.

**Reachability** mới là vấn đề trọng tâm. Dù bạn đã thực hiện `oldLoader = null`, vẫn có thể có đường giữ strong reference:

~~~text
GC root: singleton registry của ứng dụng
    └── Map<String, Object>
           └── instance plugin v1
                  └── Class<?> plugin v1
                         └── defining ClassLoader v1
                                └── các class của v1
~~~

Ngoài instance, việc giữ `Class<?>`, `Method`, `Constructor`, `MethodHandle` hoặc những đối tượng/metadata liên quan có thể giữ loader. Một giá trị `byte[]` chỉ chứa bytecode **không đồng nghĩa** với một đối tượng `Class<?>` đã nạp; tuy nhiên cache bytecode cũng tiêu thụ heap và cần giới hạn vòng đời.

**Phân biệt ba tình huống:**

1. Loader cũ vẫn còn phục vụ task hoặc còn trong registry hợp lệ: nó **nên** còn sống.
2. Loader cũ đã retire nhưng registry/thread/callback vô tình giữ: đây là một **ứng viên memory leak** cần điều tra.
3. Loader cũ đã unreachable nhưng chưa được GC/unload ngay: không có bằng chứng leak chỉ từ việc collector chưa thu hồi.

`System.gc()` **không** là cam kết class unloading. Không viết logic sản phẩm phải chờ nó hoàn tất mới được đưa phiên bản mới vào sử dụng. Việc lượng RSS/metaspace không giảm ngay cũng không đủ kết luận leak: JVM có thể giữ vùng bộ nhớ đã cấp phát để tái sử dụng.

## 4. Các vị trí thường giữ class và loader không còn cần

| Nơi giữ | Vì sao nguy hiểm? | Cách giải phóng |
| --- | --- | --- |
| Static map/singleton trong host | Lưu `Class<?>`, instance, `Method`, factory, lambda, callback của bản cũ | Cache theo version, xóa entry khi retire; không cache vô hạn |
| In-flight request / callback | Task đang chạy còn giữ object/code v1 trên stack | Dừng nhận việc mới, **drain** việc đang chạy trước khi teardown |
| Thread và executor do plugin tạo | Thread active chạy code plugin hoặc giữ TCCL trỏ tới loader cũ | Shutdown/cancel/join có giới hạn, kiểm tra task còn hoạt động |
| Thread context class loader (TCCL) | Thread pool lâu sống giữ loader qua `setContextClassLoader` | Lưu loader trước, **khôi phục trong `finally`** |
| `ThreadLocal` | Value hoặc đối tượng liên quan còn trên các thread được tái sử dụng | `remove()` trên chính thread đã đặt value |
| Event bus, scheduler, listener | Registry giữ subscription, lambda hoặc task từ v1 | Hủy đăng ký/cancel đúng ownership |
| `ServiceLoader` được host cache | Giữ provider instance/loader scope cũ | Giải phóng ServiceLoader/provider cũ, tạo loader mới cho version mới |
| Logging/MBean/driver/shutdown hook | Registry toàn JVM giữ implementation/callback cũ | Dùng API unregister/deregister thích hợp |
| File manager, output buffer, diagnostic cache | Giữ `JavaFileObject`, source text, bytecode hoặc tham chiếu class | Đóng `JavaFileManager`, bỏ buffer và collector sau job |

### Ví dụ TCCL phải có `finally`

~~~java
ClassLoader previous = Thread.currentThread().getContextClassLoader();
try {
    Thread.currentThread().setContextClassLoader(pluginLoader);
    runPluginOperation();
} finally {
    Thread.currentThread().setContextClassLoader(previous);
}
~~~

Đây là **mã minh họa trong ngữ cảnh đã định nghĩa `pluginLoader` và `runPluginOperation()`**. TCCL là thuộc tính của thread hiện tại; không mặc định executor thread mang TCCL giống thread submit task. Khi dùng thread pool, một TCCL không khôi phục có thể giữ v1 qua rất nhiều request.

Với `ThreadLocal`, dùng `try/finally` để `remove()` ngay trên thread đã ghi. Không dựa vào việc key yếu hoặc garbage collection sẽ lập tức xóa value. Trường hợp callback, listener, task chạy nền và plugin mở socket, chúng phải được đóng/hủy **trước** khi bỏ reference, không chờ GC.

### `ServiceLoader.reload()` không phải class unload

`ServiceLoader.reload()` chỉ xóa cache provider của **ServiceLoader hiện tại**; nó không thay đổi class loader/module layer đã chọn, không tự đóng provider cũ và không unload class. Trong hot reload plugin, cần quản lý **ServiceLoader theo phiên bản**, chọn scope mới, ngừng dùng provider cũ và dọn các reference sau khi drain.

## 5. Chương trình Java 17+ chạy được: compile và nạp hai phiên bản từ bộ nhớ

Chương trình dưới đây dùng source `String` và lưu `.class` trong một `ByteArrayOutputStream` thông qua `ForwardingJavaFileManager`. Mỗi phiên bản được tải bằng một `MemoryLoader` riêng. Một `WeakReference<ClassLoader>` được dùng để minh họa **quan sát mà không cố giữ loader sống**.

Cấu trúc chỉ có một tệp:

~~~text
InMemoryLoaderLifecycleDemo.java
~~~

**Nội dung đầy đủ của `InMemoryLoaderLifecycleDemo.java`:**

~~~java
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.lang.ref.WeakReference;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Locale;
import javax.tools.DiagnosticCollector;
import javax.tools.FileObject;
import javax.tools.ForwardingJavaFileManager;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileManager;
import javax.tools.JavaFileObject;
import javax.tools.SimpleJavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;

public final class InMemoryLoaderLifecycleDemo {
    private static final String CLASS_NAME = "demo.Message";

    private static final class Source extends SimpleJavaFileObject {
        private final String text;

        Source(String text) {
            super(URI.create("string:///demo/Message.java"), Kind.SOURCE);
            this.text = text;
        }

        @Override
        public CharSequence getCharContent(boolean ignoreEncodingErrors) {
            return text;
        }
    }

    private static final class Bytecode extends SimpleJavaFileObject {
        private final ByteArrayOutputStream buffer = new ByteArrayOutputStream();

        Bytecode(String className, Kind kind) {
            super(URI.create("bytes:///" + className.replace('.', '/')
                    + kind.extension), kind);
        }

        @Override
        public OutputStream openOutputStream() {
            return buffer;
        }

        byte[] bytes() {
            return buffer.toByteArray();
        }
    }

    private static final class MemoryFileManager
            extends ForwardingJavaFileManager<StandardJavaFileManager> {
        private Bytecode output;

        MemoryFileManager(StandardJavaFileManager delegate) {
            super(delegate);
        }

        @Override
        public JavaFileObject getJavaFileForOutput(
                JavaFileManager.Location location, String className,
                JavaFileObject.Kind kind, FileObject sibling) throws IOException {
            if (!CLASS_NAME.equals(className) || kind != JavaFileObject.Kind.CLASS) {
                throw new IOException("Unexpected output: " + className);
            }
            output = new Bytecode(className, kind);
            return output;
        }

        byte[] classBytes() {
            if (output == null) {
                throw new IllegalStateException("No bytecode generated");
            }
            return output.bytes();
        }
    }

    private static final class MemoryLoader extends ClassLoader {
        private final byte[] bytecode;

        MemoryLoader(ClassLoader parent, byte[] bytecode) {
            super(parent);
            this.bytecode = bytecode;
        }

        @Override
        protected Class<?> findClass(String name) throws ClassNotFoundException {
            if (!CLASS_NAME.equals(name)) {
                throw new ClassNotFoundException(name);
            }
            return defineClass(name, bytecode, 0, bytecode.length);
        }
    }

    private static byte[] compile(String version) throws IOException {
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        if (compiler == null) {
            throw new IllegalStateException("JDK compiler unavailable");
        }
        String source = "package demo; public final class Message {"
                + "public String text() { return \"" + version + "\"; } }";
        DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
        try (MemoryFileManager files = new MemoryFileManager(
                compiler.getStandardFileManager(
                        diagnostics, Locale.ROOT, StandardCharsets.UTF_8))) {
            JavaCompiler.CompilationTask task = compiler.getTask(
                    null, files, diagnostics,
                    List.of("--release", "17", "-proc:none"),
                    null, List.of(new Source(source)));
            if (!Boolean.TRUE.equals(task.call())) {
                throw new IllegalStateException(
                        "Compilation failed: " + diagnostics.getDiagnostics());
            }
            return files.classBytes();
        }
    }

    private static WeakReference<ClassLoader> demonstrate() throws Exception {
        ClassLoader parent = InMemoryLoaderLifecycleDemo.class.getClassLoader();
        MemoryLoader first = new MemoryLoader(parent, compile("v1"));
        MemoryLoader second = new MemoryLoader(parent, compile("v2"));

        Class<?> oldType = first.loadClass(CLASS_NAME);
        Class<?> newType = second.loadClass(CLASS_NAME);
        Object oldInstance = oldType.getDeclaredConstructor().newInstance();
        Object newInstance = newType.getDeclaredConstructor().newInstance();

        System.out.println("old: " + oldType.getMethod("text").invoke(oldInstance));
        System.out.println("new: " + newType.getMethod("text").invoke(newInstance));
        System.out.println("same binary name: "
                + oldType.getName().equals(newType.getName()));
        System.out.println("same class identity: " + (oldType == newType));
        System.out.println("new type accepts old: " + newType.isInstance(oldInstance));
        System.out.println("old still usable: "
                + oldType.getMethod("text").invoke(oldInstance));

        return new WeakReference<>(first);
    }

    public static void main(String[] args) throws Exception {
        WeakReference<ClassLoader> observation = demonstrate();
        System.out.println("weak monitor installed: " + (observation != null));
        System.out.println("unloading guaranteed: false");
    }
}
~~~

Chạy từ thư mục có tệp bằng **JDK 17+ có compiler**:

~~~bash
javac --release 17 InMemoryLoaderLifecycleDemo.java
java InMemoryLoaderLifecycleDemo
~~~

Stdout **chính xác**:

~~~text
old: v1
new: v2
same binary name: true
same class identity: false
new type accepts old: false
old still usable: v1
weak monitor installed: true
unloading guaranteed: false
~~~

Mẫu đã được biên dịch và chạy thành công trên OpenJDK 21 với `--release 17`.

### Vì sao kết quả như vậy?

1. `compile("v1")` và `compile("v2")` dùng hai task và hai file manager riêng. `Source` giả lập `demo/Message.java` trong bộ nhớ; `MemoryFileManager` trả `Bytecode` để javac ghi output vào stream.
2. `first` và `second` đều có parent là application loader, nhưng parent **không** có `demo.Message` trong ví dụ này. Vì vậy mỗi child định nghĩa một bản riêng qua `findClass`/`defineClass`.
3. `oldType.getName()` và `newType.getName()` bằng nhau, nhưng `oldType == newType` là `false`. Object v1 cũng không là instance của class v2.
4. Việc load v2 **không vô hiệu hóa** object v1; v1 vẫn có thể được gọi. Do đó cần quy trình drain và cleanup trước khi retire version cũ.
5. `demonstrate()` chỉ trả `WeakReference` đến loader v1, không trả instance hoặc `Class<?>` ra caller. Sau khi method kết thúc, nếu không có strong reference nào khác giữ v1, loader **có thể** trở thành eligible for GC. Dòng `weak monitor installed: true` không hề khẳng định GC đã xảy ra.
6. Demo cố tình **không** gọi `System.gc()`, không đo thời gian unloading và không in kết quả phụ thuộc collector; stdout vì vậy có thể kiểm tra ổn định.

**Giới hạn demo:** `MemoryFileManager` chỉ hỗ trợ duy nhất output class `demo.Message`. Trong engine thực tế, javac có thể sinh nhiều class (kể cả nested class), khi đó cần lưu output vào `Map<String, Bytecode>` và để loader tìm đúng bytecode theo binary name. Mẫu cũng không cấp sandbox: đừng chạy bytecode từ nguồn không tin cậy trong JVM sản phẩm chỉ vì nó đã biên dịch thành công.

## 6. Thay phiên bản an toàn: swap rồi drain, không ép GC

Một quy trình hot reload đúng phải tách **đổi bản đang phục vụ** khỏi **đóng phiên bản cũ**:

~~~text
(1) compile source v2 → bytecode
    ↓
(2) tạo loader v2 → nạp class → khởi tạo plugin v2 → health-check
    ↓
(3) atomic swap handle hiện hành v1 → v2
    ├─ request mới dùng v2
    └─ request đang chạy với v1 được phép hoàn tất
    ↓
(4) drain request v1, ngừng scheduler/task/listener phiên bản cũ
    ↓
(5) close resource/plugin, restore TCCL, remove ThreadLocal
    ↓
(6) deregister event bus/MBean/driver, xóa cache & registry v1
    ↓
(7) bỏ strong references tới instance, Class, loader v1
    ↓
(8) JVM có thể GC loader và unload class về sau
~~~

Để chuyển traffic, host có thể giữ một `AtomicReference<PluginHandle>`; mỗi `PluginHandle` quản lý version, loader, instance và tài nguyên của phiên bản. Nhưng **chỉ gán `current = newHandle` là chưa đủ**: task cũ có thể vẫn đang chạy. Cần cơ chế theo dõi in-flight work/refcount, đồng bộ quá trình drain, và tránh đóng loader/resource khi thread khác còn dùng.

Một phiên bản cũ có thể tạm thời sống song song với bản mới. Đó là **đúng thiết kế** nếu đang drain. Rò rỉ thực sự là khi version đã ngừng hoạt động nhưng registry/callback vẫn giữ reference vô thời hạn.

### `URLClassLoader.close()` có phải unload không?

**Không.** `URLClassLoader` là loader dùng cho JAR/directory và có `close()`. Theo API hiện hành, `close()` ngăn loader tiếp tục tìm class/resource mới từ URL của nó và đóng những file/JAR được mở bởi loader (best effort). Những class đã nạp **vẫn dùng được** khi còn tham chiếu; việc đóng URL loader không phải class unloading và không dừng code plugin.

Nếu dùng `URLClassLoader`, shutdown plugin và drain tác vụ trước khi đóng loader. Javadoc lưu ý kết quả của một thao tác load class diễn ra đồng thời với `close()` là không xác định. Với `MemoryLoader extends ClassLoader` trong demo, **không tồn tại `close()` mặc định**; phải dọn các tài nguyên do ứng dụng và plugin sở hữu, rồi bỏ reference.

## 7. Quan sát việc loader cũ còn sống

Có thể tạo một `WeakReference<ClassLoader>` sau khi khởi tạo loader, đặt nó trong hệ thống theo dõi, rồi quan sát sau khi đã xóa strong references:

~~~java
WeakReference<ClassLoader> watch = new WeakReference<>(pluginLoader);

// Chỉ khảo sát sau khi đã retire và bỏ các strong references khác.
ClassLoader current = watch.get();
boolean alreadyCleared = current == null;
current = null;
~~~

Đây là **mã ghép trong ngữ cảnh**, không phải test bảo đảm class unload. `WeakReference` **không** giữ loader sống. `get()` có thể trả referent hoặc `null` tùy collector. Nếu trả referent, biến `current` tạm thời là strong reference và không nên giữ lâu.

Phân biệt:

- `watch.get() != null` **không nhất thiết là leak**; JVM có thể chưa GC, hoặc một request cũ vẫn hợp lệ.
- `watch.get() == null` cho thấy weak referent đã bị clear; nó **không** thay thế phép đo class unloading hay đảm bảo toàn bộ tài nguyên nghiệp vụ đã được đóng.
- `System.gc()` và lời hẹn “loader phải biến mất trong 1 giây” không phải điều kiện kiểm thử portable.

Để theo dõi có hệ thống, có thể dùng `ReferenceQueue<ClassLoader>`, giữ các **WeakReference objects** còn reachable và đếm sự kiện clear/enqueue theo vòng đời. Quan sát thêm số loader/version, heap dump và đường đi từ GC roots, Java Flight Recorder, class unloading logs và metaspace theo **nhiều chu kỳ tải**. Trên HotSpot, `-Xlog:class+unload=info` có thể giúp quan sát sự kiện unload, nhưng là **logging**, không phải ép unload. Chỉ số RSS hoặc metaspace tại một thời điểm không đủ kết luận bị rò rỉ.

## 8. Lỗi phổ biến

| Nhầm lẫn | Thực tế |
| --- | --- |
| “`oldLoader = null` là đủ.” | Object, Class, reflection cache, thread hoặc listener khác vẫn có thể giữ loader |
| “Compile lại cùng class name là ghi đè v1.” | Runtime class identity gắn với defining loader; cần loader/version mới |
| “Hai bản `demo.Message` cùng tên chắc chắn cast được.” | Không nếu được định nghĩa bởi loader khác nhau |
| “`close()` của URLClassLoader unload lớp cũ.” | Nó giải phóng tài nguyên URL/JAR, không unload class đã nạp |
| “`ServiceLoader.reload()` thay bytecode provider.” | Không; nó chỉ reset cache provider trong scope cũ |
| “Chạy `System.gc()` là có thể đợi unload ngay.” | Thời điểm GC/unloading không được đảm bảo |
| “Task v1 vẫn chạy thì chứng tỏ leak.” | Nếu còn in-flight work, việc giữ v1 sống có thể là cần thiết |
| “TCCL/ThreadLocal không ảnh hưởng unload.” | Thread sống lâu có thể giữ loader, class, object cũ |
| “Loader mới là sandbox cho code tùy ý.” | ClassLoader không tự giới hạn quyền file/network/process; cần cách ly riêng cho code không tin cậy |

## 9. Câu hỏi tự kiểm tra

1. **Vì sao class cùng tên v1 và v2 có thể là hai kiểu khác nhau?** Vì chúng có thể được hai defining loader khác nhau định nghĩa.
2. **Việc đặt biến loader về `null` có giúp unload ngay không?** Không. Cần xét toàn bộ đồ thị strong reference và thời điểm GC.
3. **Có nên đóng phiên bản cũ ngay sau khi atomic swap?** Không nếu còn in-flight tasks; drain trước, rồi mới shutdown và deregister.
4. **Vì sao phải khôi phục TCCL ở thread pool?** Nếu không, thread dùng lại có thể giữ loader cũ và tìm class/resource theo sai scope.
5. **Dùng `WeakReference.get() != null` để kết luận memory leak được không?** Không; phải xem phiên bản còn hoạt động không và có reference không cần thiết hay chỉ chưa được GC.
6. **`URLClassLoader.close()` có đóng thread, socket của plugin không?** Không. Plugin cần contract shutdown/`AutoCloseable` và owner gọi đúng lúc.
7. **Biên dịch trong memory có tự làm bytecode biến mất khi close file manager không?** Không; nếu host/loader còn giữ bytecode hoặc `Class<?>`, chúng vẫn sống theo reachability của riêng chúng.

## 10. Nguồn chính thức còn áp dụng

- [Java SE 25 — ClassLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): định nghĩa class, parent delegation và defining loader.
- [Java Language Specification SE 25 — `12.7 Unloading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se25/html/jls-12.html#jls-12.7): điều kiện để class có thể unload.
- [Java SE 25 — JavaCompiler](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/JavaCompiler.html): biên dịch bằng `CompilationTask`.
- [Java SE 25 — JavaFileManager](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/JavaFileManager.html) và [ForwardingJavaFileManager](https://docs.oracle.com/en/java/javase/25/docs/api/java.compiler/javax/tools/ForwardingJavaFileManager.html): quản lý và đóng output compiler.
- [Java SE 25 — URLClassLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/URLClassLoader.html): giới hạn thực tế của `close()`.
- [Java SE 25 — WeakReference](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ref/WeakReference.html): theo dõi mà không giữ referent sống.
- [Java SE 25 — ServiceLoader](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html): cache provider và `reload()`.

**Kết luận:** Biên dịch tạo bytecode, loader tạo danh tính class, ứng dụng quản lý lifecycle của version, và JVM quyết định lúc GC/unload. Muốn tránh giữ lớp không còn dùng, hãy giải phóng **mọi reference/callback/resource** theo ownership và đo xu hướng qua nhiều vòng thay phiên bản, thay vì dựa vào `System.gc()`.