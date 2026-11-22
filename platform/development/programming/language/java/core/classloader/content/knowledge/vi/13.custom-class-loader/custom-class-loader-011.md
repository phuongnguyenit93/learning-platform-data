# Giữ bất biến định danh kiểu và đóng tài nguyên do loader sở hữu

> **Java Core → ClassLoader → Loader tùy chỉnh.** Khi tự viết hoặc vận hành class loader cho plugin, bạn phải bảo vệ **định danh của mỗi runtime type**, để những API mà host/plugin trao đổi luôn thuộc cùng một type, và phải có **vòng đời đóng tài nguyên** rõ ràng. Nạp class thành công mới là bước đầu: lỗi cast giữa hai lớp cùng tên, JAR bị giữ file handle, thread/context class loader làm plugin không unload, hoặc cố dùng loader sau khi close đều là lỗi thiết kế dễ gặp.

## 1. Hai mục tiêu độc lập nhưng liên quan

**Bất biến định danh kiểu (type identity invariant):** Với class/interface thông thường, JVM phân biệt runtime class theo **binary name và defining class loader**. Hai loader khác nhau cùng định nghĩa `example.Plugin` tạo ra **hai runtime types** khác nhau, dù bytecode hoàn toàn giống. Một loader cũng không được định nghĩa một tên class hai lần trong cùng namespace. Khi host và plugin cần trao đổi object qua interface, cả hai phải nhìn thấy **cùng một đối tượng `Class`** cho interface đó.

**Bất biến sở hữu tài nguyên (resource ownership/lifecycle):** Loader hoặc plugin có thể mở JAR, file, URL stream, socket, native library, worker thread, executor, watcher, cache hoặc registry. Hệ thống cần biết **ai tạo**, **ai có quyền đóng**, **khi nào ngăn công việc mới**, **khi nào đợi công việc đang chạy** và **cách giải phóng**. Với `URLClassLoader`, `close()` có hợp đồng cụ thể về nguồn JAR/file nó đã mở; với custom `ClassLoader` thuần túy, Java API **không cung cấp `close()` chung** cho mọi loader.

Tóm tắt:

~~~text
HOST (vòng đời dài)
  |
  +-- Shared API/DTO, nạp bởi host parent loader
  |       |
  |       +------ Contract.class: chỉ MỘT runtime identity
  |
  +-- Plugin loader A -----> PluginImpl.class (identity A)
  |       + resources: JAR, streams, tasks, listeners
  |
  +-- Plugin loader B -----> PluginImpl.class (identity B)
          + resources: JAR, streams, tasks, listeners

Dừng plugin A:
quiesce tasks -> unregister/cancel -> close owned resources/loader
-> bỏ strong references -> GC có thể unload classes sau đó
~~~

Điểm quan trọng: `close()` không phải `unloadClass()`. Tài nguyên I/O có thể đã được đóng nhưng các `Class` đã nạp, object, method hoặc static state **vẫn tồn tại** nếu còn tham chiếu.

## 2. Danh tính kiểu phải nhất quán qua vòng đời plugin

Đối với class/interface thông thường, JVM xác định một kiểu runtime bằng cặp **(binary name, defining loader)**. Hai loader có thể trả cùng tên qua `getName()` nhưng `Class<?> a == Class<?> b` là `false` nếu chúng thực sự định nghĩa hai bản khác nhau. Ngược lại, hai loader con ủy quyền cho cùng cha có thể nhận lại **cùng kiểu**.

- **Defining loader** là chủ sở hữu định nghĩa class, xem qua `type.getClassLoader()`; **initiating loader** chỉ có thể đã khởi phát một yêu cầu rồi ủy quyền cho cha.
- Hai implementation cùng tên do hai loader độc lập định nghĩa có static state khác nhau và không tự cast qua lại. API/SPI chia sẻ phải được host và plugin nhìn qua cùng defining loader.
- Với một loader đã khởi xướng tên lớp, `loadClass` mặc định tìm/tái sử dụng kết quả; `defineClass` lần hai để cập nhật cùng tên có thể gây `LinkageError`.
- Muốn nạp generation mới của plugin, thường cần loader mới và chuyển các object thông qua một API ổn định của parent; không coi việc thay JAR trên disk là cập nhật `Class<?>` cũ.

Bài này dùng nguyên tắc ấy để quyết định **ai giữ references và ai giải phóng tài nguyên** khi một plugin dừng hoặc được thay thế. Phần tiếp theo chỉ rõ ranh giới loader; các bước đóng và thu gom được kiểm chứng riêng ở các mục về lifecycle.

## 3. Xác định ranh giới API và ownership của loader

Trong hệ plugin, hãy đặt interface, DTO, exception hay annotation trao đổi với host ở **shared API loader**, để plugin ủy quyền khi cần. Phần triển khai và dependency private có thể thuộc loader riêng. Nếu child-first cần cho một package triển khai, hãy giới hạn chính sách theo namespace; không tự định nghĩa `java.*` hoặc API contract do host sở hữu.

Đối với parent-first custom loader chỉ thay nguồn bytecode, ưu tiên override `findClass`: `loadClass` mặc định đã xử lý locking, `findLoadedClass`, delegation và optional resolution. Khi custom `loadClass` thật sự cần thiết, phải bảo toàn những bước đó và phân biệt `ClassNotFoundException` với các lỗi linkage/security. Một interface cùng tên nhưng do child tự định nghĩa có thể làm `isAssignableFrom` thất bại tại host.

Ngoài danh tính `Class<?>`, loader còn phải giữ **runtime package, module access, certificate/signing và package sealing** đúng quy tắc. Nếu nạp từ JAR, `URLClassLoader` giúp xử lý nhiều metadata và I/O sẵn có. Không coi `ProtectionDomain` hay parent isolation là sandbox; điều quan trọng cho vòng đời là xác định **loader nào sở hữu mỗi tài nguyên** và khả năng dừng sử dụng trước khi đóng.

## 4. Ví dụ chạy được: cùng tên, hai loader, hai định danh

Mục đích là tự chứng minh **cùng một JAR nhưng hai loader riêng** tạo hai runtime classes. Không đặt plugin JAR trên host classpath.

Cấu trúc:

~~~text
identity-demo/
├── plugin-src/plugin/entry/Widget.java
├── host-src/IdentityDemo.java
├── plugins/               (sẽ tạo)
└── out/                   (sẽ tạo)
~~~

Tệp **`plugin-src/plugin/entry/Widget.java`**:

~~~java
package plugin.entry;

public class Widget {
    public Widget() { }
}
~~~

Tệp **`host-src/IdentityDemo.java`**:

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class IdentityDemo {
    public static void main(String[] args) throws Exception {
        URL jar = Path.of("plugins", "widget.jar").toUri().toURL();
        Class<?> leftType;
        Object leftObject;

        try (URLClassLoader left = new URLClassLoader(
                    new URL[] {jar},
                    ClassLoader.getPlatformClassLoader());
             URLClassLoader right = new URLClassLoader(
                    new URL[] {jar},
                    ClassLoader.getPlatformClassLoader())) {

            leftType = left.loadClass("plugin.entry.Widget");
            Class<?> rightType = right.loadClass("plugin.entry.Widget");
            leftObject = leftType.getDeclaredConstructor().newInstance();
            Object rightObject =
                    rightType.getDeclaredConstructor().newInstance();

            System.out.println("same name="
                    + leftType.getName().equals(rightType.getName()));
            System.out.println("same class=" + (leftType == rightType));
            System.out.println("same loader="
                    + (leftType.getClassLoader()
                       == rightType.getClassLoader()));
            System.out.println("left accepts right="
                    + leftType.isInstance(rightObject));
            System.out.println("right accepts left="
                    + rightType.isInstance(leftObject));
        }

        // close() đã chạy; Class<?> đã nạp không bị "xóa".
        System.out.println("old instance still valid="
                + leftType.isInstance(leftObject));
    }
}
~~~

Biên dịch, đóng JAR, chạy trong thư mục `identity-demo` bằng Java 17+ (POSIX shell):

~~~bash
mkdir -p out/plugin out/host plugins
javac --release 17 -d out/plugin \
    plugin-src/plugin/entry/Widget.java
jar --create --file plugins/widget.jar -C out/plugin .
javac --release 17 -d out/host host-src/IdentityDemo.java
java -cp out/host IdentityDemo
~~~

Stdout:

~~~text
same name=true
same class=false
same loader=false
left accepts right=false
right accepts left=false
old instance still valid=true
~~~

**Giải thích từng dòng:** Hai `URLClassLoader` dùng cùng URL, nhưng vì parent là platform loader và `plugin.entry.Widget` không nằm trong parent, mỗi loader **tự define** một bản class. Chúng có cùng binary name nhưng khác defining loader. `isInstance` chéo trả false. Sau khối `try-with-resources`, `URLClassLoader.close()` đã được gọi; các object/class đã có vẫn hợp lệ nếu còn tham chiếu.

**Ràng buộc của demo:** Không đặt `plugins/widget.jar` vào classpath của host nếu bạn muốn thử đúng ranh giới loader. Không dùng `ClassLoader.getSystemClassLoader()` làm parent chỉ vì thuận tiện khi host cũng vô tình chứa cùng class. Nếu plugin cần một interface do host định nghĩa, cần dùng parent có thể tìm đúng shared interface; giải thích ở mục kế tiếp.

## 5. Chia sẻ contract mà không nhân đôi `Class`

Một kiến trúc plugin thực tế thường cần host nhận một service object. Ví dụ shared contract:

~~~java
package api;

public interface PluginService extends AutoCloseable {
    String name();

    @Override
    void close();
}
~~~

Đây là tệp **`api/PluginService.java`**, một phần của project, không phải chương trình có `main`. Plugin có thể implement:

~~~java
package plugin.impl;

import api.PluginService;

public final class PluginServiceImpl implements PluginService {
    @Override
    public String name() {
        return "plugin-A";
    }

    @Override
    public void close() {
        // Đóng những tài nguyên do instance sở hữu.
    }
}
~~~

Đây là tệp **`plugin/impl/PluginServiceImpl.java`**, cũng không có `main`. Để cast an toàn ở host:

1. Biên dịch và đặt `api.PluginService` ở **host/shared API loader**.
2. Biên dịch plugin theo contract ấy, nhưng không bundle một bản API sẽ được child-first loader define lại.
3. Tạo plugin loader với **parent là host/shared loader**, và giữ parent-first cho package `api`.
4. Host lấy class triển khai từ plugin loader, gọi constructor theo contract/module access; cast sang `api.PluginService` do host định nghĩa.
5. Host gọi lifecycle `service.close()` trước khi đóng plugin loader, sau đó bỏ object/loader references.

Nếu plugin và host **mỗi bên định nghĩa lại `api.PluginService`** với cùng tên, bạn có thể gặp `ClassCastException` hoặc `LinkageError`, kể cả source chữ giống hệt. Việc “cùng JAR tên api.jar” không đủ; điều kiện là **cùng runtime `Class<?>`**.

### 5.1. Kiểm tra khi nhận plugin

~~~java
Class<?> impl = pluginLoader.loadClass("plugin.impl.PluginServiceImpl");
if (!PluginService.class.isAssignableFrom(impl)) {
    throw new IllegalArgumentException("Wrong shared API loader");
}
PluginService service = PluginService.class.cast(
        impl.getDeclaredConstructor().newInstance());
~~~

Đây là **snippet yêu cầu class `PluginService`, biến `pluginLoader` và điều kiện access hợp lệ**. Chỉ kiểm tra `isAssignableFrom` không bảo đảm constructor public, module opens, artifact trusted, dependency resolution hay vòng đời plugin. Đừng dùng `getName().equals(...)` thay kiểm tra type để “sửa” lỗi hai loaders.

## 6. `URLClassLoader.close()` thực sự bảo đảm điều gì?

`URLClassLoader` implements `Closeable`/`AutoCloseable` nên có thể dùng `try-with-resources`. Theo Javadoc:

- `close()` làm loader **không thể nạp mới classes/resources mà chính nó định nghĩa/tìm** qua URL path.
- Classes/resources đã nạp trước đó **vẫn có thể dùng**; classes/resources từ parent delegation **vẫn có thể truy cập**.
- Với các URL dạng `jar:`/`file:`, loader **đóng các file mà nó đã mở**, ở mức best effort, bao gồm JAR handles tương ứng.
- `getResourceAsStream` được `URLClassLoader` override: các streams do method này mở được quản lý/đóng khi loader close theo Javadoc.
- `close()` có thể ném `IOException` khi có lỗi đóng file; nếu nhiều IOException, các lỗi sau có thể là suppressed exceptions.
- Gọi `close()` lần nữa trên loader đã close không có tác dụng.
- Nếu **một thread đang load class đồng thời với close**, Javadoc nói kết quả thao tác đang load **không xác định**. Vì vậy lifecycle phải ngăn concurrency trước khi close.

**Không bảo đảm:**

- `Class` và instances lập tức biến mất.
- `static` singleton bị reset.
- JVM ngay lập tức unload classes hoặc reclaim Metaspace.
- Threads/executors, sockets, JDBC connections, files mở **bên ngoài loader**, logger appenders, HTTP clients, timers, listeners và caches tự đóng.
- URL/InputStream do application tự mở từ `URL.openStream()` hoặc `Files.newInputStream()` tự được dọn sạch chỉ vì loader đã close.
- Native/JNI libraries do plugin nạp được unload ngay; có thể còn ràng buộc VM/OS và class loader.

**Không có `close()` chung cho mọi `ClassLoader`**. Nếu bạn subclass trực tiếp `ClassLoader` và tự mở JAR/socket/channel, hãy thiết kế `AutoCloseable`/`Closeable` riêng, hoặc giữ owner khác quản lý tài nguyên đó. `URLClassLoader` có sẵn lifecycle I/O vì đặc tính URL search path, không vì mọi loader đều giống nhau.

## 7. Mẫu quản lý resource ownership

Với mỗi resource, hãy trả lời ba câu: **Ai tạo? Ai đóng? Đóng khi nào?** Ví dụ:

| Resource | Owner hợp lý | Bước đóng/giải phóng |
| --- | --- | --- |
| `URLClassLoader` và JAR handles của nó | Plugin runtime / host plugin manager | `loader.close()` sau khi không còn class-loading tasks |
| File streams/JarFile do plugin code tự mở | Thành phần trực tiếp mở | `try-with-resources` hoặc `close()` trong lifecycle riêng |
| Plugin executor/thread/timer | Plugin instance hoặc host manager quản lý pool | `shutdown`, cancel, `awaitTermination`; tránh bỏ tasks chạy |
| WatchService, sockets, DB pool | Thành phần plugin tạo | Close theo API tương ứng; xử lý lỗi best effort |
| ServiceLoader và provider instance cache | Host/plugin container | Bỏ references, clear registry, không giữ provider sau unload |
| `Thread.currentThread().getContextClassLoader()` | Từng task/worker đặt loader | `finally` restore loader trước đó |
| ThreadLocal value có chứa class/plugin | Code thiết lập value | `remove()` theo quy tắc lifecycle, đặc biệt trên thread pool |
| Static registry/listener ở host giữ plugin object | Host registry | Unregister listener/callback/caches trước unload |
| JNI/native library | Plugin/native runtime với contract riêng | Giải phóng handles qua API native; đừng kỳ vọng `close(loader)` là đủ |

**Nguyên tắc sở hữu:** Nếu loader là child của một parent dùng chung, **không bao giờ gọi `close()` vào parent chỉ vì plugin kết thúc**, trừ khi chính plugin thực sự sở hữu parent ấy. Một parent loader bị đóng khi còn nhiều plugin phụ thuộc có thể làm hỏng hệ thống.

### 7.1. Dùng try-with-resources cho những vòng đời ngắn

~~~java
URL location = Path.of("plugins", "task.jar").toUri().toURL();

try (URLClassLoader pluginLoader =
         new URLClassLoader(new URL[] {location},
                            ClassLoader.getSystemClassLoader())) {
    Class<?> pluginType = pluginLoader.loadClass("example.Task");
    // Chạy công việc plugin và đóng resources do plugin tạo.
}
~~~

Đây là snippet cần imports `java.net.URL`, `java.net.URLClassLoader`, `java.nio.file.Path` và exception handling. Class `example.Task` và JAR phải tồn tại, nên không coi đây là chương trình chạy được độc lập. Khối `try` chỉ tự close **pluginLoader**; các đối tượng được plugin tạo có thể cần lifecycle close riêng **trước** khi ra khỏi khối.

### 7.2. Vòng đời plugin dài: `stop → drain → close → release`

~~~text
ACTIVE
  -> STOPPING: từ chối công việc mới, rút khỏi discovery/routing
  -> DRAINING: cancel hoặc chờ tasks đang chạy; stop timers/threads
  -> CLEANUP: unregister callbacks/listeners; close plugin instances
  -> CLOSE LOADER: đóng JAR/file handles do loader sở hữu
  -> RELEASE: bỏ references đến Class, Method, objects, caches, TCCL
  -> ELIGIBLE FOR GC: VM có thể unload classes khi đủ điều kiện
~~~

Đây là **mô hình quản trị vòng đời**, không phải state machine do Java tự động cung cấp. Cần định nghĩa khi nào một request được xem là đã hoàn thành, timeout/cancellation policy, cách tiếp tục cleanup nếu một bước ném lỗi, và cách tránh actor khác tiếp tục sử dụng plugin cũ.

Một thứ tự cleanup thực dụng:

1. Ngừng publish plugin và nhận work mới; khóa registration theo giao ước.
2. Cancel/chờ background tasks và các request đang gọi code plugin; không `close()` loader trong lúc chúng đang tìm thêm class/resource.
3. Gỡ callback, listener, scheduler, MBean, metrics hook, shutdown hook/registries mà plugin đã đăng ký vào host.
4. Gọi `close()` của plugin service, release file/socket/DB pools, dọn ThreadLocal và restore TCCL ở workers.
5. Close những resources loader-owned, bao gồm `URLClassLoader.close()`.
6. Bỏ tất cả references host còn giữ tới plugin objects/classes/loader và các captured lambdas.
7. Quan sát GC/class unloading **không đưa ra deadline cứng**; verify bằng log/profiler và lặp vòng start/stop khi test.

Nếu một bước cleanup ném exception, hãy ghi nhận và tiếp tục dọn **các resources độc lập còn lại**, sau đó tổng hợp lỗi. Dùng `try/finally`, `try-with-resources` hoặc cơ chế suppressed exceptions thích hợp; tránh nuốt lỗi khiến vận hành tưởng plugin đã đóng an toàn.

## 8. TCCL, worker threads và classloader leaks

Trong hệ plugin, một thread có thể giữ **strong reference** tới plugin loader qua `Thread.contextClassLoader`. Điều này đặc biệt dễ xảy ra với **executor threads sống lâu**.

~~~java
Thread worker = Thread.currentThread();
ClassLoader previous = worker.getContextClassLoader();

try {
    worker.setContextClassLoader(pluginLoader);
    // Gọi ServiceLoader, resource lookup hoặc plugin callback.
} finally {
    worker.setContextClassLoader(previous);
}
~~~

Đây là snippet cần biến `pluginLoader` và phần callback thực tế. **Restore trong `finally`** để exception không làm worker giữ loader cũ. Không được giả định task nộp vào `ExecutorService` sẽ tự kế thừa TCCL từ submitter: worker đã được tạo từ trước có thể dùng TCCL khác hoặc từ task trước.

Một utility có thể wrap mỗi task, capture desired loader tại boundary và restore previous loader sau task. Nhưng thiết kế plugin phải xem **ai thực sự muốn dùng loader nào**, đừng capture một TCCL đã bị task trước làm bẩn.

Còn những roots khác:

- `ThreadLocal` key/value trên thread pool chứa plugin object/Class/Method.
- Host `static` maps, service registry, listeners, caches và timers giữ instances/classes.
- `ServiceLoader` hoặc framework registry giữ cached providers qua nhiều generations.
- Running threads đang execute method của class plugin, stack frames và callbacks.
- Java native handles hoặc JNI references trong phạm vi lifetime thích hợp.
- Một `Class<?>` hoặc `Method` được host giữ có thể giữ loader gián tiếp.

**Không nhầm:** Việc một plugin có instance trong heap chưa chắc là memory leak nếu plugin vẫn active. “Leak” là khi plugin **đã stop** theo thiết kế nhưng objects/loader vẫn bị giữ không mong muốn; cần heap dump/dominator path và lifecycle evidence để kết luận.

## 9. Class unloading: làm gì và không được hứa gì?

VM **có thể** unload một class khi điều kiện của VM/GC cho phép, thường gắn với việc defining loader và các class/object liên quan không còn reachable. Nhưng:

- Java API không cung cấp `ClassLoader.unloadClass(name)` chuẩn.
- `URLClassLoader.close()` không buộc unload class; class đã nạp vẫn sống nếu `Class<?>` hoặc objects còn referenced.
- `System.gc()` chỉ là đề nghị GC, không bảo đảm GC sẽ chạy hoặc class sẽ unload ngay.
- Không đánh giá “unload thất bại” chỉ vì một lần GC chưa thấy sự kiện; có thể còn references, thời điểm GC/chính sách runtime khác, hoặc class không unload trong đợt quan sát.

Trong HotSpot hỗ trợ unified logging, có thể xem:

~~~bash
java -Xlog:class+load=info,class+unload=info -cp out/host IdentityDemo
~~~

Lệnh này là **diagnostic HotSpot**, không phải contract chung mọi JVM. Tùy JDK, có thể dùng `jcmd <pid> VM.classloader_stats` hoặc heap dump/Java Flight Recorder để khảo sát loader còn sống. Trước khi dùng `jcmd`, kiểm tra `jcmd <pid> help` để biết command được hỗ trợ. Trong bài lab ngắn, chỉ đóng loader mà còn giữ `leftType`/`leftObject` sẽ **không** chứng minh class phải được unload.

### 9.1. Thí nghiệm kiểm tra leak nghiêm túc

Thiết kế test loop:

1. Tạo loader mới cho plugin JAR, load/khởi tạo plugin.
2. Gọi method plugin, đăng ký và sau đó unregister các hooks cần thiết.
3. Dừng tasks và close resources; bỏ references mạnh trong host.
4. Dùng `WeakReference<ClassLoader>`/`ReferenceQueue` hoặc profilers **để quan sát**, không coi kết quả ngay lập tức là chứng cứ chắc chắn.
5. Chạy nhiều lần, kiểm tra số classes/loaders, Metaspace, threads, JAR file handles; so sánh xu hướng.
6. Nếu loader vẫn reachable, tìm đường strong reference như TCCL, thread-local, static cache, listener hoặc provider.

Tránh dùng `finalize()` hoặc finalizers làm cleanup contract: không có thời điểm chắc chắn, và finalization không phù hợp để giải quyết vòng đời resource rõ ràng. Ưu tiên `AutoCloseable` và quản lý lifecycle tường minh.

## 10. Đóng tài nguyên tự quản lý trong `ClassLoader` tùy biến

Nếu custom loader đọc JAR thủ công, bạn có hai cách thiết kế:

**A. Đọc class bytes trong phạm vi ngắn**, đóng `InputStream`/`JarFile` bằng try-with-resources ngay trong `findClass`. Loader không cần giữ open JAR giữa các lần tìm (đổi lại có thể chi phí I/O). Bảo đảm `defineClass` được gọi sau khi bytes đọc đầy đủ.

**B. Giữ lâu `JarFile`/file channel/cache** để tải nhanh. Khi ấy loader/container phải implement `AutoCloseable` và có trạng thái lifecycle `OPEN → CLOSING → CLOSED`, ngăn loads mới và khóa việc đóng với loads đang chạy.

Pseudocode tài nguyên:

~~~java
final class ResourceOwner implements AutoCloseable {
    private final java.util.jar.JarFile jar;
    private boolean closed;

    ResourceOwner(java.nio.file.Path path) throws java.io.IOException {
        jar = new java.util.jar.JarFile(path.toFile());
    }

    synchronized byte[] entryBytes(String name) throws java.io.IOException {
        if (closed) {
            throw new IllegalStateException("owner closed");
        }
        var entry = jar.getJarEntry(name);
        if (entry == null) {
            throw new java.io.FileNotFoundException(name);
        }
        try (var input = jar.getInputStream(entry)) {
            return input.readAllBytes();
        }
    }

    @Override
    public synchronized void close() throws java.io.IOException {
        if (!closed) {
            closed = true;
            jar.close();
        }
    }
}
~~~

Đây là **class Java độc lập biên dịch trên Java 17+** nhưng không có `main`; nó chỉ minh họa owner của `JarFile` chứ không phải `ClassLoader` đầy đủ. `synchronized` tuần tự hóa read/close trong ví dụ này; một implementation khác có thể dùng read/write lock, reference counting hoặc state machine để tránh race. Cần đảm bảo các reads đang diễn ra không gặp file bị close giữa chừng.

**Không dùng `finalize` hoặc chỉ tin GC đóng file.** Khi resource còn ở trạng thái OPEN dù business plugin đã stop, file handles có thể giữ khóa JAR (đặc biệt hữu hình trên Windows), gây lỗi upgrade/remove artifact.

## 11. Tránh race giữa `close()` và class loading

Với `URLClassLoader`, tài liệu API nói thẳng: nếu một thread đang nạp class trong khi thread khác gọi `close()`, **kết quả load không xác định**. Vì thế cần tách trách nhiệm:

- Chặn việc cấp plugin handle / nhận request mới trước khi shutdown.
- Chờ các request/background jobs có khả năng nạp class/resource kết thúc.
- Không phát lệnh `close()` từ một cleanup thread trong khi còn plugin scanner đang `loadClass`.
- Nếu có lỗi stop/timeout, đưa trạng thái thành FAILED/QUARANTINED theo chính sách container, không claim resources đã được giải phóng sạch sẽ.
- Đồng bộ state (lifecycle lock/counter/phaser) theo quy tắc concurrency của hệ thống; một `AtomicBoolean closed` riêng **không đủ** để bảo đảm mọi load đã kết thúc trước close.

Có thể coi plugin runtime là một resource owner, thay vì đưa `URLClassLoader` ra nhiều modules rồi để ai cũng có thể `close()`. Trong API host, expose interface operations và lifecycle quản lý tập trung.

## 12. Bảo vệ binary/source compatibility khi reload

Giữa hai plugin generations, version phụ thuộc có thể khác. Kiểm tra:

1. **Shared API types không bị plugin shade/relocate nhầm** thành một bản riêng tại runtime.
2. Mã host không giữ `Class<?>`/method handles của generation cũ khi chuyển route sang generation mới.
3. Serialized objects, reflection, service interfaces và callbacks phải xử lý version boundaries; không cast object gen A sang class gen B chỉ dựa trên tên.
4. Có contract khả năng đóng: provider implement `AutoCloseable`, hoặc plugin manager quản lý close hooks theo thứ tự.
5. Các JAR/resources của generation cũ được close trước khi xóa/thay file, nhưng vẫn phải quản lý references tránh unload leak.
6. Không tự ý chuyển `parent-first` sang `child-first` trên toàn bộ packages để sửa dependency version; xác định packages sở hữu rõ ràng.

JPMS thêm khái niệm module identity/access/layer; việc nạp đúng class file vẫn có thể không đủ vì `requires`/`exports`/`opens` và module layer rules. Việc close loader không phải hành động “gỡ module” tự động khỏi layer đang được tham chiếu.

## 13. Lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân khả dĩ | Hướng sửa |
| --- | --- | --- |
| `Plugin cannot be cast to Plugin` | Hai class cùng name nhưng defining loaders khác | Chia sẻ contract qua parent; kiểm tra loader identity |
| `LinkageError: attempted duplicate class definition` | Gọi `defineClass` lặp cùng binary name trong loader | `findLoadedClass`, locking, không redefine |
| `NoClassDefFoundError` sau khi loader đã close | Một thành phần vẫn cần class mới sau shutdown | Ngăn activity, wait/drain tasks, chỉ close khi an toàn |
| `IOException` từ `URLClassLoader.close()` | Lỗi đóng file handles | Xử lý/log, suppressed errors, retry theo policy nhưng không giả định close sạch |
| JAR không xóa/đổi tên được trên Windows | `JarFile`/stream/loader còn mở | Đóng owner và URLClassLoader, tìm handles thực |
| Plugin cũ không unload sau GC | TCCL, threads, ThreadLocal, host registry/caches giữ loader | Shutdown/unregister/remove, heap dominator path |
| Parent API khác bản giữa host/plugin | Dependency packaging/shading sai | Shared API loader, contract test |
| `IllegalAccessError` ở module | JPMS readability/exports/opens | Sửa module graph/access, không bypass bằng class name |
| Child-first loader deadlock | Delegate vòng, khóa thô, concurrency sai | getClassLoadingLock/parallel capable policy, giản lược graph |
| ServiceLoader không nhận provider | TCCL sai, SPI metadata thiếu, provider type khác loader | Shared interface, loader đúng, cache/lifecycle đúng |
| Native library bị giữ | JNI/OS/native references và lifecycle khác classloading | Đóng native resources theo API, không tin `close(loader)` tự unload |

## 14. Checklist triển khai và review

- [ ] Định nghĩa **shared API packages** và **plugin-private packages**; test `sharedContractFromHost == sharedContractFromPlugin`.
- [ ] Không định nghĩa trùng binary name trong cùng loader; dùng delegation, `findLoadedClass` và locking thích hợp.
- [ ] Kiểm soát parent-first/child-first theo package, không để child define lại `java.*` hoặc API của host.
- [ ] Xác định rõ owner của loader, `JarFile`, InputStreams, executor, sockets, watchers, native handles và listeners.
- [ ] Các resource ngắn hạn có `try-with-resources`; owner dài hạn có `close()` rõ ràng và kiểm tra idempotence.
- [ ] Plugin shutdown có **quiesce → drain → cleanup → close → release**, xử lý lỗi từng bước.
- [ ] Mọi task đổi TCCL đều khôi phục trong `finally`; dọn ThreadLocal/registries.
- [ ] Không dùng loader sau `close` để tìm **class/resource mới do loader tự định nghĩa**.
- [ ] Không kỳ vọng `close()` làm các `Class` đã nạp, objects hoặc native resources biến mất.
- [ ] Test reload nhiều lần, quan sát loader retention/file handles, phân biệt hiện tượng GC tạm thời và leak thật.
- [ ] Review module access và class compatibility xuyên versions; không dùng `getName()` như bằng chứng cast được.

## 15. Bài tập tự kiểm tra

1. Hai `URLClassLoader` có URL giống nhau, cùng parent platform loader, mỗi loader tự định nghĩa `plugin.Widget`. Hai `Class` có `==` không? **Không**.
2. Hai child loaders đều delegate `api.Contract` về parent. Hai `Class` do `loadClass` trả có `==` không? **Có**, nếu parent thực sự define cùng runtime type.
3. `URLClassLoader.close()` có làm các object của class đã nạp invalid? **Không**.
4. Có thể gọi `close()` trong lúc thread khác đang load mà mong behavior xác định? **Không**, cần quiesce/drain.
5. Có `ClassLoader.close()` chuẩn cho mọi custom loader không? **Không**.
6. Nếu plugin manager bỏ reference loader nhưng executor thread còn TCCL trỏ tới loader, class unloading có được bảo đảm? **Không**.
7. Có nên set `System.gc()` để “bắt buộc unload” không? **Không**, chỉ là đề nghị.
8. Cách nào tránh class duplicate trong custom loader? **findLoadedClass + class loading lock + định nghĩa một lần**.
9. `ServiceLoader` đã cache provider plugin cũ nhưng bạn chỉ close loader: provider object có tự mất? **Không**, phải dọn cache/reference.
10. `parent-first` cho shared API có ý nghĩa gì? **Giữ contract ở cùng defining loader mà host/plugin cùng thấy**.
11. JNI native library có chắc unload khi URLClassLoader close không? **Không**, vòng đời native tách biệt.
12. Cách xác minh memory leak? **Kiểm tra strong reference roots và thử vòng stop/reload lặp, không chỉ nhìn một lần GC**.

## 16. Tài liệu đặc tả và API

- [JVMS §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se25/html/jvms-5.html#jvms-5.3): runtime class identity, defining/initiating loaders, loading constraints.
- [ClassLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): `loadClass`, `findClass`, `findLoadedClass`, `defineClass`, `getClassLoadingLock` và `registerAsParallelCapable`.
- [URLClassLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/net/URLClassLoader.html): URL search path, `close`, JAR/file handles và concurrent close behavior.
- [AutoCloseable — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/AutoCloseable.html): scoped resource cleanup.
- [JarFile — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/jar/JarFile.html): native JAR file owner và lifecycle I/O.
- [Thread — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html): context class loader references.
- [ServiceLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html): provider discovery/cache và loader selection.

**Kết luận:** Một loader tùy chỉnh đúng không chỉ nạp được bytecode; nó phải **giữ cùng runtime identity cho shared contracts** và **đóng đúng tài nguyên do mình sở hữu** theo vòng đời được quản trị. `URLClassLoader.close()` giúp release file/JAR handles nhưng **không phải lệnh unload class**, không dừng plugin threads và không xóa mọi strong reference. Thiết kế cả type boundary, concurrency và cleanup ngay từ đầu để plugin reload không trở thành nguồn lỗi khó tái hiện.
