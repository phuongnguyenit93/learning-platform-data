# Thiết kế cache bytecode và nguồn tài nguyên an toàn cho nhiều luồng trong Java ClassLoader

Khi nhiều thread cùng yêu cầu nạp class hoặc resource từ JAR, thư mục, bộ nhớ hay nguồn từ xa, một custom `ClassLoader` phải giải quyết **hai bài toán đồng thời nhưng khác nhau**:

1. **Định nghĩa runtime class an toàn:** một defining loader không thể định nghĩa cùng một binary class name hai lần. Các thread cạnh tranh cần nhận **cùng một `Class<?>`**, không cùng gọi `defineClass`.
2. **Tìm và đọc bytecode/resource hiệu quả:** nhiều thread có thể cần cùng dữ liệu `.class`, ảnh, template, cấu hình. Cache phải bảo đảm không rò rỉ dữ liệu chưa hoàn tất, không đọc lặp vô ích, quản lý lỗi và giữ đúng version/generation của nguồn.

Điểm tinh tế: **cache `byte[]` không phải cache `Class<?>`**. JVM/ClassLoader đã giữ trạng thái class được nạp theo defining/initiating loader; cache bytes chỉ lưu **nguyên liệu để định nghĩa**, trong khi cache resource thường lưu **dữ liệu bất biến** hoặc metadata nguồn. Không được lấy một `Class<?>` do loader A định nghĩa rồi “tái sử dụng như class của loader B”.

Bài này giải thích hợp đồng đồng thời của `ClassLoader`, cách chọn cache key, safe publication, single-flight, read-through, invalidation, fail/retry, resource stream, performance, class unloading và ví dụ Java 17+ chạy được.

## 1. Ba tầng bộ nhớ không nên nhập làm một

~~~text
                   Nhiều application threads
                       |              |
                 loadClass(...)    readResource(...)
                       |              |
                       v              v
                  ClassLoader      Resource service
                       |              |
            findLoadedClass(name)   Cache data/metadata
                       |              |
             tìm bytecode .class    tìm bytes/resource
                       |              |
              defineClass(...)       InputStream mỗi caller
                       |
                       v
                    Class<?>
                       |
                 JVM type identity
            (binary name, defining loader)
~~~

| Tầng | Thực thể lưu | Mục đích | Lưu ý |
|---|---|---|---|
| JVM/class-loading state | Thông tin class đã load/define | Tránh định nghĩa lại kiểu trong cùng loader, phục vụ liên kết kiểu | `findLoadedClass` liên quan initiating loader; dùng đúng quy tắc delegation |
| Bytecode source cache | `byte[]` hoặc kết quả đọc bytecode | Hạn chế I/O/transform/verify nguồn lặp | Phải gắn với source version/loader generation |
| Resource cache | Bytes, nội dung đã parse, metadata hoặc handle có vòng đời | Tránh đọc resource lặp | Không chia sẻ một `InputStream` đang bị consume |
| External cache (tùy chọn) | JAR index, HTTP artifact, disk cache | Giảm chi phí đọc từ xa | Cần integrity, expiration và policy version |

**Sai lầm phổ biến:** dùng `ConcurrentHashMap<String, Class<?>>` làm kho toàn cục cho tất cả loaders. Key chỉ có tên class không đủ, vì **type identity = (binary name, defining class loader)**. Ngoài ra, giữ tham chiếu mạnh tới `Class<?>` có thể vô tình giữ cả loader cũ sống lâu.

## 2. Tránh định nghĩa class trùng dù đã cache bytes
Cache `byte[]` chỉ lưu dữ liệu nguồn; nó **không có quyền thay thế** trạng thái class được JVM ghi nhận. Với `loadClass` mặc định, cùng tên được bảo vệ bởi `getClassLoadingLock(name)`, rồi `findLoadedClass` kiểm tra class đã được nạp trước khi `findClass` có cơ hội `defineClass`. Do đó hai thread cùng load `plugin.Task` thành công sẽ nhận một `Class<?>`, dù cache bytes có một hay nhiều lượt đọc.
Không gọi trực tiếp `findClass` từ nhiều threads để “sử dụng cache”; phương thức đó không thay thế synchronization của `loadClass`. Bài **Tránh race condition giữa findLoadedClass và defineClass** minh họa race bằng barrier.

## 3. Parallel loading và cache là hai tầng riêng
Subclass đăng ký **parallel-capable** từ static initializer cho phép `loadClass` mặc định khóa theo binary name thay vì toàn loader. Điều này chỉ giúp các **tên khác nhau** có cơ hội tiến hành đồng thời; không làm `ConcurrentHashMap`, `FutureTask`, stream hay resource service tự an toàn. Trong `findClass`, nên giữ buffer cục bộ và state chia sẻ đồng bộ đúng.
Nếu chỉ đổi nguồn bytes và vẫn parent-first, **chỉ override `findClass`**. Khi bắt buộc override `loadClass`, kiểm tra class đã nạp dưới cùng lock trước khi định nghĩa; xem các bài locking và race trước đó.

## 4. Cache key phải mô tả nguồn và version

Với **cache riêng cho một loader instance bất biến**, một class name có thể đủ làm key:

~~~text
class cache key = "plugin.impl.Task"
resource key    = "plugin/config.txt"
~~~

Tuy nhiên, với **cache chia sẻ giữa nhiều loader hoặc nhiều plugin generations**, key cần bổ sung:

~~~text
CacheKey = (
    artifact/source identity,
    artifact version or content hash,
    relative path / binary name,
    transformation pipeline version,
    possibly runtime target version
)
~~~

Vì sao?

- Hai plugin có thể chứa `plugin.impl.Task` cùng tên nhưng bytecode khác nhau.
- Cùng JAR path có thể bị ghi đè từ v1 sang v2; **đường dẫn không chứng minh nội dung bất biến**.
- Class transformer/instrumentation có thể thay bytes theo cấu hình khác.
- Multi-release JAR có thể phục vụ bytes khác nhau theo phiên bản runtime.
- Resource trong nhiều plugin có thể cùng path `config.properties` nhưng khác nội dung.
- Nếu file nguồn thay đổi giữa hai lần đọc, cache không nên âm thầm tạo lớp và resource thuộc hai versions khác nhau.

Với cache local của một loader gắn với một deployment bất biến, cách đơn giản nhất thường là **tạo loader mới mỗi plugin generation**, không hot-swap bytes của class đã định nghĩa bên trong một loader cũ.

## 5. Safe publication và immutability của dữ liệu cached

Một `ConcurrentHashMap` giúp các thread cùng truy cập map an toàn, nhưng **không tự biến giá trị mutable thành immutable**:

~~~java
ConcurrentHashMap<String, byte[]> cache = new ConcurrentHashMap<>();
~~~

`byte[]` có thể bị code khác chỉnh sửa sau khi lưu. Nếu một thread biến đổi nội dung trong khi thread khác gọi `defineClass` hoặc đọc resource, runtime có thể gặp bytecode hỏng hoặc dữ liệu không nhất quán.

Quy tắc:

1. Khi nhận byte[] từ nguồn ngoài, tạo **snapshot** trước khi công bố nếu bên ngoài vẫn có thể thay đổi array.
2. Không trả trực tiếp mutable `byte[]` từ public cache API cho caller không tin cậy.
3. Nếu resource phải có stream, tạo **một `ByteArrayInputStream` riêng cho mỗi caller** từ snapshot bất biến, thay vì cache/đưa cùng một `InputStream` cho nhiều thread.
4. Giữ metadata gắn với snapshot như source URI, content hash, generation; không cập nhật từng trường rời rạc khiến reader nhìn thấy “metadata v2 + bytes v1”.
5. Dùng object immutable (ví dụ record chứa bản sao bytes/metadata) hoặc cache entry không còn bị sửa sau công bố.

### Vì sao không cache một `InputStream` dùng chung?

`InputStream` có trạng thái vị trí đọc. Hai thread đọc cùng một stream sẽ tranh chấp con trỏ và có thể nhận dữ liệu thiếu, trùng hoặc xen kẽ. Một thread đóng stream còn làm thread kia thất bại.

**Nên cache bytes hoặc thông tin nguồn**, rồi cấp stream mới:

~~~java
byte[] bytes = immutableCachedBytes;
try (InputStream in = new ByteArrayInputStream(bytes)) {
    // Mỗi caller có vị trí đọc độc lập.
}
~~~

Đây là mảnh minh họa; bảo đảm `bytes` thật sự không bị mutation bên ngoài trong suốt thời gian stream tồn tại.

## 6. Single-flight: nhiều request, một lần tải nguồn

Có ba chiến lược caching thường gặp:

| Cách | Có ngăn duplicate I/O khi cache miss? | Ghi chú |
|---|---|---|
| `HashMap` thường, không khóa | Không; còn có data races | Không dùng chia sẻ đa luồng |
| `ConcurrentHashMap.get` rồi `putIfAbsent` sau khi I/O | **Không chắc**: hai thread vẫn đọc I/O trước khi một thread thắng `putIfAbsent` | Safe publication có thể có, nhưng duplicate work |
| `ConcurrentHashMap.computeIfAbsent` với I/O trong mapping function | Atomic cho key, có thể ngăn duplicate computation | Mapping function phải ngắn, không update lại map; I/O dài gây blocking |
| `ConcurrentHashMap<Key, FutureTask<byte[]>>` và `putIfAbsent` trước khi chạy task | Có: nhiều caller chờ cùng một future | Kiểm soát lỗi/retry và không chạy I/O dưới CHM mapping lock |
| `CompletableFuture` placeholder + producer | Có nếu dùng put-if-absent trước khi producer tải | Cần complete/completeExceptionally, timeout/cancel/lifecycle |

### Vì sao không đặt network I/O tùy ý trong `computeIfAbsent`?

Theo `ConcurrentHashMap.computeIfAbsent` JDK 17, lệnh tính mapping chạy atomically; một số update khác có thể bị block trong lúc đang tính, do đó mapping function nên **ngắn và đơn giản**. Mapping function không được sửa chính map trong khi chạy; update đệ quy có thể ném `IllegalStateException`.

Ví dụ không nên dùng cho network I/O nặng:

~~~java
byte[] b = cache.computeIfAbsent(key, k -> {
    // Không khuyến nghị: HTTP/disk I/O lâu trong mapping function.
    return slowRemoteDownload(k);
});
~~~

Đây là **pseudocode minh họa** với `cache`, `key` và `slowRemoteDownload` tự triển khai, không phải chương trình độc lập. Ngoài blocking, ngoại lệ checked từ nguồn cũng phải chuyển đổi và quản lý cẩn thận.

**Phương án minh bạch hơn:** map từ key sang `FutureTask<byte[]>`. Thread thắng `putIfAbsent` thực hiện đọc I/O bên ngoài thao tác update map, các thread còn lại chờ cùng task. Nếu task thất bại, remove đúng `(key, future)`, tránh cache mãi lỗi tạm thời.

## 7. Ví dụ Java 17+ hoàn chỉnh: cache bytecode và resource đa luồng

Chương trình dưới đây dùng:

- Một loader kế thừa trực tiếp `ClassLoader` và đăng ký `parallel-capable`.
- Method `findClass` đọc `plugin/Task.class` qua cache **single-flight**.
- Một API riêng `openResource` đọc `plugin/config.txt` qua cache tương tự, trả stream mới cho mỗi caller.
- `ConcurrentHashMap<String, FutureTask<byte[]>>` để chia sẻ một lần đọc theo key.
- `Executors.newFixedThreadPool(8)` cho **24 tác vụ**, tất cả yêu cầu cùng `plugin.Task` và cùng resource.
- Counter cho **số lần đọc nguồn thành công**, không phải số lượt gọi API.

Mục tiêu là chứng minh **các thread nhận cùng runtime class, dữ liệu resource đầy đủ và chỉ một lần đọc class file + một lần đọc resource file** trên cache miss thành công.

### 7.1. Cấu trúc thư mục

~~~text
project/
  src/
    plugin/Task.java
    host/CacheDemo.java
  plugin-out/
    plugin/
      Task.class
      config.txt
  host-out/
    CacheDemo.class
    CacheDemo$DirectoryLoader.class
~~~

Hai thư mục output sinh từ lệnh `javac`. Plugin class **không được thêm vào application classpath** khi chạy host.

### 7.2. File `src/plugin/Task.java`

~~~java
package plugin;

public final class Task {
    public String message() {
        return "task-ok";
    }
}
~~~

### 7.3. File `src/host/CacheDemo.java`

~~~java
import java.io.ByteArrayInputStream;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.FutureTask;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class CacheDemo {

    static final class DirectoryLoader extends ClassLoader {
        static {
            if (!registerAsParallelCapable()) {
                throw new ExceptionInInitializerError(
                        "Cannot register parallel class loader");
            }
        }

        private final Path root;
        private final ConcurrentHashMap<String, FutureTask<byte[]>> flights =
                new ConcurrentHashMap<>();

        private final AtomicInteger classReads = new AtomicInteger();
        private final AtomicInteger resourceReads = new AtomicInteger();

        DirectoryLoader(Path root) {
            super(ClassLoader.getPlatformClassLoader());
            this.root = root.toAbsolutePath().normalize();
        }

        private byte[] loadOnce(String key, String relativePath,
                                AtomicInteger successfulReads)
                throws IOException {

            Path source = root.resolve(relativePath).normalize();
            if (!source.startsWith(root)) {
                throw new IOException("Outside configured directory");
            }

            FutureTask<byte[]> future = flights.get(key);

            if (future == null) {
                FutureTask<byte[]> candidate = new FutureTask<>(() -> {
                    byte[] data = Files.readAllBytes(source);
                    successfulReads.incrementAndGet();
                    return data;
                });

                FutureTask<byte[]> previous =
                        flights.putIfAbsent(key, candidate);

                if (previous == null) {
                    future = candidate;
                    candidate.run();
                } else {
                    future = previous;
                }
            }

            try {
                return future.get();
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IOException("Interrupted waiting for " + key, ex);
            } catch (ExecutionException ex) {
                flights.remove(key, future);
                throw new IOException("Failed loading " + key, ex.getCause());
            }
        }

        @Override
        protected Class<?> findClass(String name)
                throws ClassNotFoundException {
            if (!"plugin.Task".equals(name)) {
                throw new ClassNotFoundException(name);
            }

            try {
                byte[] bytes = loadOnce(
                        "class:plugin.Task",
                        "plugin/Task.class",
                        classReads);

                return defineClass(name, bytes, 0, bytes.length);
            } catch (IOException ex) {
                throw new ClassNotFoundException(name, ex);
            }
        }

        // API resource riêng: không giả vờ thay ClassLoader.getResource.
        InputStream openResource(String name) throws IOException {
            if (!"plugin/config.txt".equals(name)) {
                throw new FileNotFoundException(name);
            }

            byte[] data = loadOnce(
                    "resource:" + name, name, resourceReads);

            // Mỗi caller có một con trỏ stream đọc riêng.
            return new ByteArrayInputStream(data);
        }

        int classReads() {
            return classReads.get();
        }

        int resourceReads() {
            return resourceReads.get();
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: CacheDemo <plugin-directory>");
        }

        DirectoryLoader loader =
                new DirectoryLoader(Path.of(args[0]));

        ExecutorService workers = Executors.newFixedThreadPool(8);
        CountDownLatch ready = new CountDownLatch(8);
        CountDownLatch go = new CountDownLatch(1);
        List<Future<Class<?>>> results = new ArrayList<>();

        try {
            for (int i = 0; i < 24; i++) {
                Callable<Class<?>> action = () -> {
                    ready.countDown();
                    go.await();

                    Class<?> type = loader.loadClass("plugin.Task");

                    try (InputStream stream =
                            loader.openResource("plugin/config.txt")) {
                        String content = new String(
                                stream.readAllBytes(),
                                StandardCharsets.UTF_8).strip();

                        if (!"config-ok".equals(content)) {
                            throw new IllegalStateException(
                                    "Unexpected resource: " + content);
                        }
                    }

                    return type;
                };

                results.add(workers.submit(action));
            }

            // Đợi 8 worker threads bắt đầu rồi cùng mở cổng.
            ready.await();
            go.countDown();

            Class<?> first = results.get(0).get();
            boolean sameClass = true;

            for (Future<Class<?>> result : results) {
                if (result.get() != first) {
                    sameClass = false;
                }
            }

            System.out.println("parallel capable: "
                    + loader.isRegisteredAsParallelCapable());
            System.out.println("same runtime class: " + sameClass);
            System.out.println("defined by custom loader: "
                    + (first.getClassLoader() == loader));
            System.out.println("successful class reads: "
                    + loader.classReads());
            System.out.println("successful resource reads: "
                    + loader.resourceReads());
            System.out.println("tasks completed: " + results.size());
        } finally {
            go.countDown(); // Không để task đợi cổng nếu main lỗi.
            workers.shutdown();
            if (!workers.awaitTermination(10, TimeUnit.SECONDS)) {
                workers.shutdownNow();
            }
        }
    }
}
~~~

### 7.4. Biên dịch và chạy

Các lệnh dùng Bash, chạy trong thư mục `project`:

~~~bash
mkdir -p plugin-out/plugin host-out

javac -d plugin-out src/plugin/Task.java

printf 'config-ok\n' > plugin-out/plugin/config.txt

javac -d host-out src/host/CacheDemo.java

java -cp host-out CacheDemo plugin-out
~~~

**Lưu ý:** lệnh chạy chỉ đưa `host-out` vào application classpath. `plugin-out` là thư mục dữ liệu/bytecode mà custom loader sẽ tìm; không thêm nó vào `-cp`, nếu không ví dụ không còn tách bạch host/plugin loading.

**Stdout dự kiến khi mọi file có sẵn và các tác vụ hoàn tất thành công:**

~~~text
parallel capable: true
same runtime class: true
defined by custom loader: true
successful class reads: 1
successful resource reads: 1
tasks completed: 24
~~~

Đây là kết quả có chủ đích của cache key cố định, source files không đổi, single-flight và class loader locking. Thứ tự hoàn thành task bên trong thread pool không xác định, nhưng chương trình **không in log per thread**, vì vậy các dòng trên vẫn theo thứ tự in của `main`.

### 7.5. Vì sao đúng dù 24 tác vụ chạy đồng thời?

- `registerAsParallelCapable` thành công khi loader class được khởi tạo, vì kế thừa trực tiếp `ClassLoader` đã parallel-capable.
- Các lời gọi `loadClass("plugin.Task")` trên cùng loader dùng class-loading lock cho tên `plugin.Task`; một lần `findClass` thành công sẽ `defineClass`, các lần khác dùng class đã nạp.
- `loadOnce` dùng `putIfAbsent` để công bố một `FutureTask` cho mỗi key **trước** khi bắt đầu đọc file; chỉ một thread chạy task cho cache miss.
- Các thread khác gọi `future.get()` để đợi; completion của FutureTask công bố data an toàn cho các thread nhận kết quả.
- `resourceReads == 1` vì mọi lời gọi mở `plugin/config.txt` dùng cùng key `resource:plugin/config.txt`.
- Mỗi lời gọi `openResource` trả **ByteArrayInputStream mới**; các task không giành một con trỏ stream dùng chung.
- Cả 24 kết quả là cùng `Class<?>` do custom loader định nghĩa. Không thread nào tự gọi `defineClass` bên ngoài đường `loadClass` có lock.

**Cần nói rõ giới hạn ví dụ:** loader cố ý chỉ nạp **một binary class name** và cho đọc **một resource name** đã biết. Việc dùng whitelist tránh đưa bytecode path tùy ý vào demo. Đây là mẫu học về concurrency/caching, chưa phải loader production tổng quát hỗ trợ package sealing, code signing, mọi định dạng nguồn hay sandbox.

### 7.6. Kiểm tra lỗi I/O và retry

Nếu `plugin/config.txt` không có, `Files.readAllBytes` làm `FutureTask` thất bại. `ExecutionException` được chuyển thành `IOException` và mapping lỗi bị loại bằng `flights.remove(key, future)`.

Tác dụng:

- Kết quả lỗi tạm thời **không bị cache vĩnh viễn**.
- Request tiếp theo có cơ hội thử lại nếu file xuất hiện.
- `remove(key, future)` không xóa nhầm một future khác được thêm sau đó.
- Nhiều request cùng chờ một future thất bại có thể nhận cùng lỗi; khi future bị remove, request mới có thể khởi tạo **một lần tải mới**. Vì vậy không nên khẳng định “tối đa một lần I/O trong suốt đời loader” **khi có lỗi và retry**.
- Một hệ thống production nên có backoff/jitter và phân biệt lỗi vĩnh viễn (file không hợp lệ, tên không được phép) với lỗi tạm thời (I/O, timeout).

### 7.7. Vì sao không gọi `defineClass` trong FutureTask?

Cache future trong ví dụ chỉ quản lý **bytes đọc từ nguồn**. `defineClass` được gọi trong `findClass` và thực hiện dưới sự điều phối của `loadClass`. Nếu đặt `defineClass` vào task chia sẻ chung giữa loaders hoặc ngoài classloading lock, rất dễ làm lẫn bytecode caching với type definition và gặp duplicate definition.

Đặc biệt, **không cache `Class<?>` toàn cục** rồi trả về từ loader khác chỉ dựa vào tên binary. JVM yêu cầu class identity và loading constraints được xử lý đúng theo loader hierarchy.

## 8. Bytecode cache không cần tồn tại mãi

Ví dụ giữ `FutureTask<byte[]>` trong `flights` suốt vòng đời loader. Nó phù hợp demo nhỏ nhưng có thể lãng phí trong hệ thống nhiều class:

- Sau khi JVM đã định nghĩa class, thường **không cần giữ bytecode `byte[]` mãi** trong cache của loader chỉ để phục vụ `loadClass` sau này; `findLoadedClass` và JVM đã có trạng thái runtime class.
- Nếu transformation/verification cần bytes để audit hoặc nhiều source loader dùng lại một artifact, cache có lợi; cần memory budget.
- Dùng **bounded cache**, policy LRU/weight-based hoặc eviction rõ ràng cho source bytes/resources lớn.
- Nếu tính năng `reload` được yêu cầu, **thay bytes trong cache không thay định nghĩa class đã có**. Một plugin generation mới thường cần **loader instance mới**.
- Với cache dùng chung nhiều loaders, key phải chứa source version/content hash. Không trộn bytes v1/v2 của cùng class path.
- Thực hiện snapshot artifact bất biến trong một generation thay vì đọc từng file của deployment đang bị ghi đè.

Một chiến lược thường tốt hơn cache bytes không giới hạn là **cache index và immutable artifact metadata**, để mỗi loader giữ trạng thái runtime của chính nó; dữ liệu lớn có thể chia sẻ có kiểm soát theo content hash và bị evict khi không dùng.

## 9. Cache tài nguyên: byte[] hay parsed object?

| Dạng cache | Phù hợp khi | Rủi ro |
|---|---|---|
| `byte[]` snapshot | Resource nhỏ, đọc lặp, cần stream độc lập | Heap tăng; phải tránh mutation và giới hạn kích thước |
| Immutable parsed config | Dữ liệu có cấu trúc, nhiều thread cùng đọc | Parser/representation phải thread-safe và immutable |
| URI/Path + metadata | File lớn, ít đọc, muốn tránh giữ bytes | Mỗi caller vẫn làm I/O, có race nếu source đổi |
| Open `InputStream` | **Không nên chia sẻ giữa threads** | Con trỏ đọc chung, close race, handle leak |
| Mmap/FileChannel (chuyên dụng) | Tệp lớn, random access được thiết kế có kiểm soát | Lifetime mapping/channel, OS resources, bounds/cleanup |
| Cache future của bytes | Nhiều concurrent misses cùng key | Phải xử lý failure, cancellation, invalidation và wait cycles |

Đối với resource lớn, `readAllBytes()` có thể tốn bộ nhớ. Dùng stream riêng từng request hoặc giới hạn byte count; không cache mọi dữ liệu chỉ vì có nhiều thread.

### Reader/writer đồng thời khi cấu hình thay đổi

Nếu cần reload resource đang được đọc, tránh sửa **byte[] tại chỗ**:

~~~text
generation 1 -> immutable snapshot v1
generation 2 -> immutable snapshot v2

Reader A lấy v1 và đọc nhất quán đến hết.
Reader B bắt đầu sau publish mới lấy v2.
~~~

Có thể dùng một immutable snapshot object được thay atomically qua `AtomicReference<Snapshot>` hoặc map versioned. Đối với nhiều resource cần cập nhật nhất quán, thay **toàn bộ snapshot/generation** trong một bước, thay vì invalidate từng key không có giao thức.

**Không dùng cùng quy tắc để “reload” class đã định nghĩa.** JVM không thay class identity chỉ vì source bytes thay; cần lớp cơ chế khác như loader generation mới hoặc instrumentation/redefinition với giới hạn riêng.

## 10. Cẩn thận với tương tác locks, Future và I/O

### Lock ordering

Per-class load lock giúp tránh duplicate definition theo tên, nhưng nếu `findClass(A)` giữ lock A rồi chờ một thao tác khác cần lock B, trong khi thread khác giữ lock B rồi chờ lock A, có thể deadlock.

~~~text
Thread 1: lock A -> waits on B
Thread 2: lock B -> waits on A
=> cyclic wait
~~~

Parallel-capable **giảm** việc chặn toàn loader, nhưng không tự loại bỏ mọi deadlock nếu delegation graph, transformation, cache callbacks hoặc plugin initialization tạo quan hệ chờ vòng.

Nên giữ lock duration gọn, ưu tiên hierarchical delegation đơn giản, tránh callbacks gọi nạp class khác khi đang xử lý key trong cache, và không dùng synchronization global không cần thiết.

### FutureTask và self-wait

Trong ví dụ, producer chỉ gọi `Files.readAllBytes` cho path cố định; nó không đệ quy gọi `loadOnce` với chính key đang chạy. Trong hệ thống phức tạp, nếu code của producer lại gọi `future.get()` lên future của chính nó, thread sẽ **tự đợi vô hạn**. Vì vậy cần cấm recursive load của cùng key hoặc phát hiện cycle khi xử lý dependencies từ xa.

### Interruption và cancellation

Một waiter bị interrupt nên:

- Khôi phục interrupt flag bằng `Thread.currentThread().interrupt()`.
- Trả lỗi theo hợp đồng gọi.
- **Không tùy ý cancel future chung**, vì nhiều caller khác còn chờ nó.

Timeout có thể hữu ích cho remote I/O, nhưng chỉ áp dụng ở tầng thật sự điều khiển network read/cancellation. `Future.get(timeout)` ở waiter không có nghĩa producer đã ngừng chạy.

### Race khi close source

Đừng đóng `URLClassLoader` hay file/resource provider trong lúc thread khác đang nạp class. Javadoc `URLClassLoader.close()` nêu rằng nếu thread khác đang load khi gọi close, kết quả load ấy **không được xác định**.

Một plugin runtime có thể dùng lifecycle state:

~~~text
ACTIVE -> DRAINING -> CLOSED

ACTIVE: nhận request mới
DRAINING: ngừng nhận mới, đợi in-flight operations xong
CLOSED: đóng loader, stream và underlying sources
~~~

Với cache có background executor hoặc remote download, phải dừng producer, cancel nhiệm vụ không còn dùng theo hợp đồng, và không công bố dữ liệu của generation đã đóng vào loader mới.

## 11. Cache negative results và sai lầm khi retry

Không tìm thấy class/resource cũng là một kết quả có ý nghĩa, nhưng cache lỗi không đúng có thể tạo bug:

- Nếu cache vĩnh viễn `ClassNotFoundException` trong loader mà source URL còn có thể bổ sung file, plugin mới sẽ không bao giờ được tìm thấy dù file đã xuất hiện.
- Nếu cache `null` trong `ConcurrentHashMap`, thao tác put sẽ ném `NullPointerException` vì ConcurrentHashMap không chấp nhận null key/value.
- Nếu file bị lỗi tạm thời, retry ngay ở mọi thread có thể tạo **thundering herd** I/O/network. Dùng backoff/timeout hoặc cache lỗi có TTL ngắn khi thích hợp.
- Nếu artifact bất biến (generation đã đóng băng) và một class chắc chắn không tồn tại, negative cache có thể hợp lý, nhưng phải gắn với **artifact generation**.
- Nếu lỗi bytecode `ClassFormatError`, `VerifyError` hoặc `SecurityException`, không xử lý như lỗi network tạm thời; cần báo lỗi đúng và kiểm tra nguồn.
- Đừng nuốt `LinkageError` rồi thử định nghĩa class khác cùng tên như cách “retry”.

**Bài học:** policy invalidation cần theo **loại lỗi**, **độ tin cậy của nguồn** và **tính bất biến của generation**, không thể chỉ dựa vào “có catch exception”.

## 12. Performance: đo đúng bottleneck

Tăng parallelism không phải lúc nào cũng tăng throughput. Một số giới hạn:

| Chi phí | Nếu làm sai | Gợi ý |
|---|---|---|
| Disk/network reads | Nhiều thread cùng đọc một file | Single-flight cho cache misses; kiểm soát concurrency |
| CPU transform/verify | Làm lại bytecode transform nhiều lần | Cache kết quả theo hash + transform version khi hợp lệ |
| Class-loading locks | Giữ global loader lock cho mọi class | Đăng ký parallel-capable nếu thiết kế hỗ trợ |
| Cache memory | Giữ vô hạn `byte[]`, duplicate trong heap/metaspace | Giới hạn memory và eviction |
| Resource streams | Chia sẻ một stream hoặc quên close | Một stream mỗi caller, try-with-resources |
| Source snapshot | Đọc class v2 nhưng resource v1 khi deploy | Pin immutable generation và publish atomically |
| Logging | Log chi tiết mỗi class mỗi thread | Dùng sampling/structured metrics để giảm overhead |
| Retry | Lỗi I/O làm mọi thread cùng retry | Backoff + single-flight + error taxonomy |

### Số liệu nên thu thập

- `cache_hits` / `cache_misses` theo class/resource và generation.
- `inflight_loads`, số waiter, thời gian đợi future.
- `source_read_count` và latency của file/JAR/network.
- `class_load_failures` theo `ClassNotFoundException`, `LinkageError` và lỗi I/O.
- `resource_read_failures`, `resource_bytes_cached` và eviction count.
- CPU, heap pressure, metaspace và số lượng classloader đang sống.
- Nếu cần: phân tích JFR/JVM Unified Logging `-Xlog:class+load=info,class+unload=info` trên JDK thích hợp.

Không log toàn bộ bytecode, resource secrets hoặc path chứa credentials. Khi chẩn đoán, log source identifier/hash và loader identity có kiểm soát.

## 13. Test concurrency: những trường hợp bắt buộc

**Test 1 — Nhiều thread, cùng một class name:** trả cùng `Class<?>`, không có duplicate `defineClass` hay `LinkageError`.

**Test 2 — Nhiều thread, class names khác nhau:** với parallel-capable loader, có thể tiến hành cùng lúc nếu source/cache hỗ trợ; không gây race/deadlock.

**Test 3 — Cùng resource path:** mọi stream đọc trọn nội dung, không chia sẻ con trỏ đọc.

**Test 4 — Missing resource:** thất bại có nguyên nhân rõ, xử lý retry theo policy, không cache null vĩnh viễn.

**Test 5 — Missing class/dependency:** phân biệt `ClassNotFoundException` và `NoClassDefFoundError`; không mù quáng retry những lỗi linkage.

**Test 6 — Corrupt bytecode:** truyền đúng `ClassFormatError`/lỗi xác thực, không nuốt và ghi cache như dữ liệu hợp lệ.

**Test 7 — Source cập nhật giữa hai lần đọc:** xác định generation bất biến; không trộn bytes/config từ hai release.

**Test 8 — Cache pressure:** giới hạn memory, eviction đúng, không đuổi một future đang cần bởi loader trước khi trạng thái được xử lý.

**Test 9 — Shutdown và in-flight load:** ngừng request, drain, rồi close; không để thread khác gọi closed loader.

**Test 10 — Plugin redeploy:** loader cũ không giữ reference thừa qua cache tĩnh, TCCL, background executor; loader mới có generation riêng.

**Test 11 — Parent delegation:** nếu parent có class, custom child trả đúng parent class, không cố define lại không cần thiết.

**Test 12 — Resource duplicate names:** class policy và resource lookup policy được kiểm tra riêng nếu parent/child có cùng path.

**Test 13 — Interruption:** waiter được báo/carry interrupt đúng, không cancel shared producer vô ý.

**Test 14 — Cache failures:** sau failure tạm thời, một load mới có thể retry; metrics phản ánh số lần attempt thay vì tưởng cache luôn exactly once.

**Test 15 — Malicious/untrusted path:** xác thực tên class/resource và nguồn; tránh path traversal, symlink surprises, zip-slip khi giải nén JAR và tải bytecode chưa tin cậy.

## 14. Các lỗi thường gặp và cách nhận diện

| Triệu chứng | Nguyên nhân điển hình | Hướng xử lý |
|---|---|---|
| `LinkageError: duplicate class definition` | Hai đường gọi `defineClass` cùng tên/loader | Đưa vào `loadClass` lock, tránh gọi `findClass` trực tiếp |
| Deadlock class loading | Vòng delegation hoặc lock ordering giữa A/B | Thread dump, phân tích locks, parallel capability |
| `ClassNotFoundException` dù file tồn tại | Parent/source path/cache negative sai | Xem binary name, URL/JAR, generation |
| `NoClassDefFoundError` | Dependency vắng, init thất bại hoặc lỗi liên kết | Đọc `Caused by` và nguồn bytecode |
| Resource đọc thiếu trong nhiều threads | Chia sẻ một `InputStream` | Cache bytes + stream mới per caller |
| Resource không đổi sau deploy | Cache key không có version/generation | Invalidate/generation switch đúng thời điểm |
| GC giữ plugin cũ | Cache toàn cục giữ `Class<?>`/ClassLoader | Giảm strong references, quản lý lifecycle |
| `OutOfMemoryError: Java heap space` | Cache giữ bytes lớn vô hạn | Giới hạn kích thước, eviction/streaming |
| `IllegalStateException` trong `computeIfAbsent` | Recursive map update trong mapping function | Không update cùng map từ mapping callback |
| Nhiều lần tải file sau lỗi | Future bị remove để retry, nhiều request đến | Backoff và single-flight cho mỗi attempt |
| Load fail khi shutdown | Close source đúng lúc thread còn đọc | ACTIVE/DRAINING/CLOSED protocol |
| Class cache trả sai type | Cache global keyed chỉ theo class name | Key theo loader identity/generation; đừng cache Class xuyên loaders |

## 15. Quy tắc thực hành

**Nên làm:**

1. Kế thừa `ClassLoader` và override **`findClass`** nếu vẫn dùng delegation mặc định.
2. Đăng ký `parallel-capable` một lần ở static initialization khi thực sự thiết kế cho concurrency.
3. Để `getClassLoadingLock(name)` phối hợp class loading theo tên; không phát minh lock thứ hai bao trùm tất cả nếu không cần.
4. Sử dụng `ConcurrentHashMap` và immutable cache entries; single-flight khi cache miss tốn kém.
5. Phân biệt `Class<?>` runtime identity với `byte[]` source artifact.
6. Trả stream mới cho mỗi caller, đóng streams sớm và quản lý memory budget.
7. Pin version/content hash/generation, định nghĩa quy tắc invalidation và retry.
8. Log class/resource source cùng loader identity và nguyên nhân lỗi.
9. Đảm bảo shutdown đợi các operations đang chạy trước khi đóng source provider.
10. Test cạnh tranh dữ liệu, lỗi, thay version và lifecycle trên workload thực tế.

**Tránh làm:**

- Chia sẻ `HashMap`/`ArrayList` mutable không khóa cho loader cache giữa nhiều threads.
- Dùng `if (!map.containsKey(k)) map.put(k, read())` rồi tưởng thao tác atomic.
- Chia sẻ `InputStream` như một value của resource cache.
- Gọi `defineClass` lặp lại chỉ vì muốn “cache class”, hoặc giữ `Class<?>` vô hạn trong global static map.
- Đặt network I/O lâu và callback phức tạp trong `computeIfAbsent`.
- Coi `registerAsParallelCapable` là bảo đảm tự động cho mọi shared state của subclass.
- Coi `close` tương đương unloading ngay lập tức.
- Dựa vào classloader để chạy mã không tin cậy trong sandbox.

## 16. Tự kiểm tra

**Câu 1.** Hai thread đồng thời gọi `loader.loadClass("p.Task")`. Vì sao không nên để cả hai cùng tự gọi `defineClass` từ ngoài `loadClass`?

**Đáp án:** JVM không chấp nhận hai definition cùng binary name trong một defining loader; có thể gây `LinkageError`. Hãy dùng locking trong `loadClass` và kiểm tra class đã nạp.

**Câu 2.** Đăng ký `registerAsParallelCapable` có làm `HashMap` riêng của loader thread-safe không?

**Đáp án:** Không. Nó chỉ thay cơ chế class-loading locks; mọi cache mutable của subclass vẫn cần synchronization/safe publication.

**Câu 3.** `ConcurrentHashMap<String, byte[]>` đã bảo vệ byte[] khỏi bị thread khác chỉnh sửa chưa?

**Đáp án:** Chưa. Map thread-safe nhưng array vẫn mutable. Dùng snapshot bất biến, không trao mảng gốc cho code có thể mutate, hoặc cấp bản sao khi cần.

**Câu 4.** Vì sao dùng `FutureTask<byte[]>` với `putIfAbsent` thay vì để nhiều thread cùng tải bytes rồi mới `putIfAbsent`?

**Đáp án:** Placeholder future được công bố **trước khi** I/O bắt đầu, nên các thread cùng key chờ một task thay vì cùng làm duplicate I/O.

**Câu 5.** Có thể cache `InputStream` và đưa cùng một stream cho 24 thread không?

**Đáp án:** Không nên: stream có trạng thái đọc và vòng đời đóng, nên một thread có thể làm hỏng kết quả thread khác. Cache bytes bất biến rồi tạo stream mới.

**Câu 6.** Nếu muốn cập nhật `plugin.Task` từ bytecode v1 sang v2, sửa bytes trong cache của cùng ClassLoader có thay `Class<?>` đang dùng không?

**Đáp án:** Không. Runtime class đã định nghĩa không được tự thay bằng bytes mới qua cơ chế classloader thường. Dùng loader generation mới hoặc cơ chế class redefinition chuyên dụng với giới hạn riêng.

**Câu 7.** Vì sao `URLClassLoader.close()` cần phối hợp với in-flight loads?

**Đáp án:** API không xác định kết quả nếu một thread đang load class khi thread khác close loader. Nên dừng nhận tải mới và drain trước khi close.

**Câu 8.** Nếu `computeIfAbsent` chạy một network request mất vài giây, đó có phải luôn là thiết kế tốt không?

**Đáp án:** Không. JDK khuyến nghị mapping function ngắn/đơn giản vì có thể chặn các update khác; dùng future placeholder/single-flight và quản lý timeout/retry bên ngoài map operation.

**Câu 9.** Cache key chỉ chứa `plugin.Task` có đủ cho cache chia sẻ giữa hai plugin generations không?

**Đáp án:** Không. Cần cả artifact/source identity và version/hash/generation để tránh dùng nhầm bytes khác nội dung.

## 17. Sơ đồ thiết kế đề xuất

~~~text
                 Concurrent requests for key K
                           |
                           v
                  Check loader/generation
                           |
                           v
             CHM<K, FutureTask<bytes>>
                  /                \
           Future tồn tại         Chưa có
                 |                   |
             future.get()      putIfAbsent(new task)
                 |                   |
              nhận bytes        Người thắng run task
                 |                   |
                 +---------+---------+
                           |
                     Immutable bytes
                           |
           +---------------+----------------+
           |                                |
    Class-loading path                Resource path
           |                                |
      getClassLoadingLock(name)         new InputStream
           |                           per caller
       findLoadedClass
           |
       findClass / defineClass
           |
       Runtime Class<?>
           |
    Theo vòng đời loader riêng
~~~

**Ghi nhớ ba nguyên tắc:**

1. **Khóa class definition là trách nhiệm của class loading path.** Dùng `loadClass`/`getClassLoadingLock` đúng và chỉ định nghĩa một lần trong cùng loader.
2. **Bytecode/resource cache là một tầng khác.** Dùng key đúng version, dữ liệu bất biến, single-flight và stream độc lập.
3. **Lifecycle mới là yếu tố quyết định tính an toàn lâu dài.** Xử lý failure/retry, invalidation, memory budget và shutdown trước khi đóng loader/source.

### Tài liệu chính thức

- [Java SE 17 — ClassLoader: parallel-capable, getClassLoadingLock, loadClass](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html)
- [Java SE 17 — ConcurrentHashMap: computeIfAbsent](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html#computeIfAbsent(K,java.util.function.Function))
- [Java SE 17 — FutureTask: concurrent computation và get](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/FutureTask.html)
- [Java SE 17 — URLClassLoader: close concurrency caveat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html#close())
- [JVMS 17 §5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3)
