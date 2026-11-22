# Thread, ThreadLocal, context class loader và tác vụ chưa dừng khi dỡ plugin

> **Java Core → ClassLoader → Dỡ lớp và bộ nhớ.** Tạo một `ClassLoader` mới để nạp phiên bản plugin khác chỉ là phần đầu của vòng đời. Một **thread vẫn sống**, một giá trị `ThreadLocal` chưa dọn, một `Thread.contextClassLoader` (TCCL) còn trỏ vào plugin hoặc một task chưa kết thúc có thể giữ **tham chiếu mạnh** đến class loader cũ. Khi đó, dù host đã bỏ plugin khỏi registry và gọi `URLClassLoader.close()`, loader cùng các lớp nó định nghĩa có thể chưa đủ điều kiện để garbage collector thu hồi. Bài này trình bày đồ thị tham chiếu, cách tái hiện lỗi, phân biệt “task kết thúc” với “thread kết thúc”, quy trình cleanup đúng và cách chẩn đoán trên Java 17+.

## 1. Câu hỏi thực tế: tại sao plugin đã dừng mà heap vẫn tăng?

Một plugin manager hỗ trợ hot reload thường làm:

```text
1. Tải plugin-v1.jar bằng PluginClassLoader V1
2. Tạo đối tượng plugin và chạy tasks
3. Người dùng nâng cấp plugin
4. Gọi plugin.stop(), close(V1)
5. Tải plugin-v2.jar bằng PluginClassLoader V2
6. Mong V1 và các class metadata cũ được GC thu hồi
```

Nhưng sau nhiều vòng, heap/metaspace có thể tăng và nhiều loader thế hệ cũ vẫn xuất hiện trong heap dump. Một lý do phổ biến là **host đã quên một root reference**:

```text
Live thread / global executor / registry
      |
      +--> Thread.contextClassLoader --> PluginClassLoader V1
      |
      +--> ThreadLocalMap (của thread)
      |         '--> plugin object --> Class<?> --> PluginClassLoader V1
      |
      +--> Runnable / Future / callback còn sống
                '--> plugin object hoặc plugin Class<?> --> V1
```

Đây là sơ đồ hướng đi phổ biến, không phải kết luận rằng **mọi** đường tham chiếu đều tồn tại ở mọi JVM. Garbage collector quyết định theo reachability thực tế: nếu một loader còn được chạm tới từ GC roots, loader không thể được thu hồi chỉ vì ứng dụng gọi phương thức tên là `stop` hoặc `close`.

**Định nghĩa quan trọng:**

- **Class unloading**: JVM có thể loại bỏ class metadata khi đáp ứng điều kiện reachability/lifecycle thích hợp; không có lời hứa thời điểm cụ thể.
- **Class loader leak**: code không còn cần một loader nhưng các references vô tình giữ nó reachable.
- **Resource leak**: file descriptor, socket, thread, memory buffer hoặc task không được đóng/dừng. Nó có thể liên quan hoặc độc lập với loader leak.
- **Plugin unload đúng nghĩa**: host đã ngừng nhận công việc mới, dừng/cô lập công việc cũ, xóa references trong host và các threads, đóng nguồn, và **cho GC cơ hội** thu hồi khi còn không có references khác.

Đừng dùng “đã đóng JAR” như bằng chứng “đã dỡ class”.

## 2. Thread sống là một phần quan trọng của đồ thị tham chiếu

Một `Thread` đang chạy có thể giữ nhiều loại dữ liệu liên quan plugin:

1. **TCCL**: `thread.getContextClassLoader()` giữ một reference đến một `ClassLoader`.
2. **ThreadLocal values**: dữ liệu riêng của thread, có thể là object do plugin loader định nghĩa.
3. **Stack frames/local variables**: phương thức plugin đang thực thi có locals, `this`, `Class<?>` hoặc callbacks.
4. **Runnable/Callable**: target task giữ các fields hoặc lambda captures dẫn về plugin.
5. **`UncaughtExceptionHandler` và các handler/listener tùy chỉnh**: có thể giữ object hoặc class của plugin.
6. **Inherited state**: `InheritableThreadLocal` và TCCL được truyền tại thời điểm tạo thread theo quy tắc `Thread`.
7. **Thread pool bookkeeping**: queued `Runnable`, `FutureTask`, `ScheduledFuture` hoặc executor giữ dữ liệu liên quan plugin.

Một thread nền của plugin nếu tiếp tục vòng lặp sẽ giữ execution stack và có thể giữ loader gián tiếp qua class/method đang chạy. Một thread ở trạng thái `WAITING` cũng **không hẳn đã kết thúc**: nó có thể đang chờ queue, latch, socket hoặc timer trong khi vẫn giữ các references.

**Không phải mọi object giữ `Class<?>` đều là bug:** khi host còn chủ động cần chạy plugin, giữ references là đúng. “Leak” chỉ hình thành sau khi lifecycle đã tuyên bố plugin không còn được sử dụng nhưng references không được giải phóng.

## 3. Context Class Loader (TCCL) là gì và tại sao dễ giữ loader cũ?

`Thread` có hai phương thức:

```java
ClassLoader cl = Thread.currentThread().getContextClassLoader();
Thread.currentThread().setContextClassLoader(cl);
```

Đây là snippet trong method. TCCL cho phép framework chạy trong class/library của host hỏi một loader thích hợp để tìm provider classes/resources của plugin. Ví dụ `ServiceLoader` và một số công nghệ SPI/framework có thể sử dụng context loader phù hợp để khám phá implementation.

TCCL **không nhất thiết là defining loader** của code đang chạy:

```text
Thread đang chạy method của host class
          |
          | getContextClassLoader()
          v
PluginClassLoader A

host method vẫn do host loader định nghĩa
TCCL chỉ là ngữ cảnh được chọn cho lookup tương ứng
```

Vì `Thread` lưu TCCL thành reference, khi một thread pool sống lâu hơn plugin và TCCL còn trỏ vào `PluginClassLoader V1`:

```text
GC root -> pooled Thread -> contextClassLoader -> PluginLoader V1
```

Loader V1 tiếp tục reachable. Ngay cả khi chưa có `ThreadLocal`, **một mình TCCL** có thể đủ để giữ loader.

### TCCL được kế thừa vào thời điểm tạo thread

Theo Java SE 21 `Thread`, context loader mặc định thường **được kế thừa từ parent thread khi child Thread được tạo**. Điều đó có nghĩa:

- Nếu host đặt TCCL thành plugin loader khi tạo một thread pool, pool workers có thể **kế thừa nhầm** loader của plugin.
- Sau khi host khôi phục TCCL ở thread tạo pool, TCCL trong các workers đã được tạo **không tự thay đổi theo**.
- Một thread pool có thể tái sử dụng cùng platform thread qua nhiều tasks. TCCL do task trước để lại có thể trở thành context của task kế tiếp.
- Không nên dựa vào việc “main thread đã set lại loader” để kết luận pool threads đã được dọn.

Để tránh tạo workers với context loader sai, cấu hình `ThreadFactory` thích hợp và luôn phục hồi TCCL trong **chính worker thread** sau khi chạy task.

### Mẫu đổi TCCL có try/finally

```java
Thread current = Thread.currentThread();
ClassLoader old = current.getContextClassLoader();

try {
    current.setContextClassLoader(pluginLoader);
    // Gọi plugin / ServiceLoader / framework API cần ngữ cảnh này.
} finally {
    current.setContextClassLoader(old);
}
```

Đây là snippet cần biến `pluginLoader` và đoạn gọi plugin thực tế. TCCL restore phải nằm trong `finally` vì plugin có thể ném exception. Nếu chỉ `current.setContextClassLoader(pluginLoader)` mà quên khôi phục, một pooled worker sau khi task kết thúc vẫn có thể giữ loader.

**Đừng tự khôi phục về `null` trừ khi `null` thực sự là giá trị trước đó.** `null` có semantics “dùng system class loader (hoặc bootstrap nếu cần)” theo API và có thể không tương đương context ban đầu của framework.

## 4. ThreadLocal giữ dữ liệu ra sao?

`ThreadLocal<T>` là một cách lưu **một giá trị riêng trên mỗi thread**. Dù biến khai báo ở class của host, chính worker thread giữ value riêng:

```java
private static final ThreadLocal<Object> CURRENT_PLUGIN =
        new ThreadLocal<>();
```

`CURRENT_PLUGIN.set(value)` lưu một value cho **thread đang chạy**. `CURRENT_PLUGIN.get()` trong thread khác không trả cùng value chỉ vì dùng cùng `ThreadLocal` key.

Nếu value là object có class do plugin loader định nghĩa:

```text
Host static ThreadLocal key
      |
Live pooled thread
      '--> ThreadLocal value: plugin.Instance
                      |
                      v
                Class<?> of plugin.Instance
                      |
                      v
              PluginClassLoader V1
```

Một key `ThreadLocal` đặt trong class host sống lâu và value do plugin tạo có thể giữ loader cũ cho đến khi worker gọi `remove()`, thay value, hoặc thread chết (và không còn references khác).

API chính:

- `set(value)`: ghi value của **thread hiện tại**.
- `get()`: lấy value của **thread hiện tại**; có thể dùng `initialValue()` tạo value.
- `remove()`: xóa value thuộc **thread hiện tại**.

Đặc biệt: **gọi `CURRENT_PLUGIN.remove()` ở main thread không xóa bản value mà một pool worker đang giữ**. Cleanup cần chạy trên đúng worker từng set nó, hoặc có một chính sách thay thế/hủy thread tương ứng.

### “ThreadLocal có weak key nên chắc không leak” là nhầm

Trong các triển khai HotSpot/OpenJDK thường gặp, `ThreadLocalMap` có keys là weak references tới `ThreadLocal` instances nhưng **giá trị có thể được giữ mạnh**. Nếu key bị GC, entry có thể trở thành stale trong map, và value không nhất thiết được thu hồi ngay cho đến khi map cleanup thực hiện.

Vì thế:

- Key là weak không bảo đảm value plugin được GC ngay.
- Mất reference tới biến `ThreadLocal` không thay thế `remove()`.
- Đừng tạo `new ThreadLocal<>()` cho mỗi request mà không dọn trên long-lived worker.
- Đừng dựa vào việc thread pool “sẽ làm sạch mọi ThreadLocal sau mỗi task” trừ khi **executor/framework cụ thể có hợp đồng làm điều đó**.

Cấu trúc nội bộ `ThreadLocalMap` là implementation detail, không phải API để ứng dụng truy cập hoặc chỉnh sửa bằng reflection. **Biện pháp đúng** là thiết kế ownership, dùng `try/finally`/`remove()`, và để worker kết thúc khi plugin được gỡ nếu còn state không kiểm soát.

## 5. Kết thúc task khác kết thúc thread

`ExecutorService.submit(Runnable)` trả về `Future` có thể `isDone() == true`, nhưng điều này **không** đồng nghĩa executor đã dừng hoặc worker thread đã chết.

Ví dụ:

```text
t0: Thread pool tạo worker-1
t1: worker-1 chạy Task A của plugin-v1
t2: Task A hoàn thành, Future A = done
t3: worker-1 quay về đợi trong task queue
t4: Task B chạy trên cùng worker-1
t5: pool shutdown, workers mới có thể kết thúc theo quy tắc executor
```

Nếu Task A để lại TCCL hoặc `ThreadLocal` của plugin-v1, worker-1 có thể mang nó từ t2 sang t4, thậm chí Task B thuộc một plugin khác.

Có ba trạng thái phải hỏi riêng:

| Trạng thái | Ý nghĩa | Điều không thể suy ra |
| --- | --- | --- |
| `future.isDone()` | Task đã hoàn thành/cancelled theo `Future` contract. | Thread pool đã chết hoặc TCCL/TL đã được dọn. |
| `executor.isShutdown()` | Executor không tiếp nhận tasks mới. | Mọi task đang chạy đã kết thúc. |
| `executor.isTerminated()` | Sau shutdown, mọi tasks hoàn tất theo contract executor. | Không còn **bất kỳ** reference plugin trong host caches/TCCL threads ngoài pool. |
| `thread.isAlive()` | Thread đã start và chưa kết thúc. | Nó đang chạy tác vụ hữu ích; có thể đang chờ queue. |
| `loader.close()` | URLClassLoader đóng các resources/nguồn tải của nó theo API. | Class đã unload, thread/task tự ngừng, hoặc mọi references bị xóa. |

**`shutdownNow()` không phải “kill tất cả code”.** Nó thường cố dừng bằng interrupt và trả tasks chưa chạy; code có thể bỏ qua interrupt, mắc I/O không interruptible hoặc giữ references khác. Với plugin code tùy ý không tin cậy, chỉ cố interrupt thread trong cùng JVM không phải giới hạn an toàn tương đương kill một process.

## 6. Ví dụ Java 17+ kiểm chứng TCCL và ThreadLocal retention

Ví dụ này giữ nguyên một **worker thread trong pool** sau khi task ban đầu đã hoàn thành. Worker chứa hai references tới loader plugin: TCCL và một `ThreadLocal<Object>` có value class do plugin loader định nghĩa.

Sau đó, host **gửi cleanup task vào đúng worker**, gọi `ThreadLocal.remove()` và restore TCCL về baseline đã biết. Cuối cùng mới shutdown pool và close URL loader.

Demo **không gọi `System.gc()`**, không yêu cầu suy ra class unloading xảy ra ngay. Nó kiểm tra được **tham chiếu đang tồn tại/được gỡ** và lifecycle, điều này có kết quả xác định.

### Cấu trúc source

```text
src/
  plugin/
    sample/
      plugin/
        Payload.java
  app/
    RetainedLoaderDemo.java
plugin-classes/  (javac tạo)
app-classes/     (javac tạo)
```

**File `src/plugin/sample/plugin/Payload.java`:**

```java
package sample.plugin;

public final class Payload {
    public String label() {
        return "plugin-value";
    }
}
```

**File `src/app/RetainedLoaderDemo.java`:**

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public final class RetainedLoaderDemo {
    private static final ThreadLocal<Object> HOLDER = new ThreadLocal<>();

    public static void main(String[] args) throws Exception {
        URL source = Path.of("plugin-classes").toAbsolutePath()
                .toUri().toURL();
        Class<?> loaded;

        try (URLClassLoader loader = new URLClassLoader(
                new URL[]{source}, ClassLoader.getPlatformClassLoader())) {
            loaded = Class.forName(
                    "sample.plugin.Payload", true, loader);
            Object value = loaded.getDeclaredConstructor().newInstance();

            AtomicReference<Thread> worker = new AtomicReference<>();
            ExecutorService pool =
                    Executors.newSingleThreadExecutor(action -> {
                        Thread thread =
                                new Thread(action, "reusable-worker");
                        thread.setContextClassLoader(
                                ClassLoader.getPlatformClassLoader());
                        return thread;
                    });

            try {
                pool.submit(() -> {
                    worker.set(Thread.currentThread());
                    Thread.currentThread()
                            .setContextClassLoader(loader);
                    HOLDER.set(value);
                }).get();

                System.out.println("defined by plugin loader: "
                        + (loaded.getClassLoader() == loader));
                System.out.println("worker stays alive: "
                        + worker.get().isAlive());
                System.out.println("TCCL retains loader: "
                        + pool.submit(
                                () -> Thread.currentThread()
                                        .getContextClassLoader()
                                        == loader).get());
                System.out.println("ThreadLocal retains plugin value: "
                        + pool.submit(
                                () -> HOLDER.get() != null
                                        && HOLDER.get().getClass()
                                           .getClassLoader() == loader).get());
            } finally {
                pool.submit(() -> {
                    HOLDER.remove();
                    Thread.currentThread().setContextClassLoader(
                            ClassLoader.getPlatformClassLoader());
                }).get();

                System.out.println("TCCL restored: "
                        + pool.submit(
                                () -> Thread.currentThread()
                                        .getContextClassLoader()
                                        == ClassLoader.getPlatformClassLoader()).get());
                System.out.println("ThreadLocal cleared: "
                        + pool.submit(() -> HOLDER.get() == null).get());

                pool.shutdown();
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                }
            }
        }

        System.out.println("class usable after close: "
                + loaded.getName().equals("sample.plugin.Payload"));
    }
}
```

### Biên dịch và chạy

Đứng trong thư mục gốc chứa `src`:

```bash
javac --release 17 -d plugin-classes src/plugin/sample/plugin/Payload.java
javac --release 17 -d app-classes src/app/RetainedLoaderDemo.java
java -cp app-classes RetainedLoaderDemo
```

Code tương thích Java 17; `ClassLoader.getPlatformClassLoader()` có từ Java 9 và `URLClassLoader` hỗ trợ try-with-resources. Không đưa `plugin-classes` vào application classpath: class `sample.plugin.Payload` phải do URL loader trong demo định nghĩa.

**Stdout chính xác đã được kiểm chứng trên OpenJDK 24 sau khi biên dịch với `javac --release 17`:**

```text
defined by plugin loader: true
worker stays alive: true
TCCL retains loader: true
ThreadLocal retains plugin value: true
TCCL restored: true
ThreadLocal cleared: true
class usable after close: true
```

### Phân tích kết quả

1. `defined by plugin loader: true`: `Payload` được loader URL mới định nghĩa thay vì application/platform loader.
2. `worker stays alive: true`: task đầu tiên đã kết thúc và `Future.get()` trả về, nhưng `newSingleThreadExecutor` vẫn giữ worker để dùng cho task kế tiếp.
3. `TCCL retains loader: true`: chính worker thread có `contextClassLoader == loader` **sau** task trước. Đây là một reference mạnh.
4. `ThreadLocal retains plugin value: true`: bản value `HOLDER` thuộc worker thread là object của plugin. Không gọi `remove` thì nó có thể đi theo worker qua các tasks tiếp theo.
5. `TCCL restored: true`: cleanup task chạy trên cùng worker và reset loader về platform baseline do `ThreadFactory` đã thiết lập. Trong ứng dụng thật, nên lưu `old = thread.getContextClassLoader()` rồi restore chính giá trị ấy.
6. `ThreadLocal cleared: true`: worker không còn value do task đầu đặt. Host **không** gọi `HOLDER.remove()` trong main rồi hy vọng dọn hộ worker.
7. `class usable after close: true`: `URLClassLoader.close()` không “xóa” Class object đã được định nghĩa; biến `loaded` ở host vẫn giữ reference. Đây **không phải test GC**. Class chỉ có thể được thu hồi sau khi không còn các references ngăn thu hồi và GC thực sự xử lý.

**Phạm vi kiểm thử:** Ví dụ dùng single-thread executor, nên các tasks inspection/cleanup được thực thi trên **cùng một worker**. Với fixed pool có nhiều workers, gửi một task cleanup không đảm bảo nó chạy trên tất cả workers đã từng xử lý plugin. Cần quản lý state theo từng thread/task, hoặc shutdown và thay hẳn pool thuộc plugin.

**Cẩn trọng production:** Ví dụ tập trung quan sát nên cleanup task đơn giản và `get()` có thể block theo contract. Trong hệ thống thực phải bảo đảm cleanup/shutdown diễn ra kể cả khi một task khác ném exception, bị hủy, executor từ chối submit hoặc worker kẹt; không xem một `finally` chứa các thao tác có thể lỗi như giải pháp tuyệt đối cho mọi tình huống.

## 7. Mẫu phục hồi TCCL + ThreadLocal đúng trong từng task

Với một worker pool **do host sở hữu**, nên bọc mọi lần thực thi plugin:

```java
// Snippet trong Runnable có các biến pluginLoader,
// pluginContext và HOST_CONTEXT do ứng dụng cung cấp:
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    HOST_CONTEXT.set(pluginContext);

    // invokePlugin();
} finally {
    HOST_CONTEXT.remove();
    thread.setContextClassLoader(previous);
}
```

`HOST_CONTEXT` nên có kiểu `ThreadLocal<PluginContext>` hoặc kiểu phù hợp; đây là **snippet**, không phải chương trình chạy độc lập. Điều quan trọng nhất là `remove()` và TCCL restore nằm **trong task, trên chính worker**.

Nếu plugin hoặc framework có **nhiều ThreadLocal khác** do nó tự tạo, host chỉ dọn `HOST_CONTEXT` là **chưa đủ**. Plugin/framework phải có lifecycle cleanup riêng hoặc được chạy trong pool chuyên dụng mà bạn có thể shutdown, chờ hoàn tất và loại bỏ toàn bộ threads.

### Tác vụ lồng nhau / TCCL stack

Một task có thể thay TCCL nhiều lần:

```text
Host TCCL H
   -> plugin A TCCL A
      -> thư viện tải provider B, TCCL B
      <- restore A
   <- restore H
```

Mỗi tầng phải **restore giá trị cũ của nó**, không hardcode toàn hệ thống về system loader. Nếu một tầng quên restore, code phía ngoài có thể hoạt động sai hoặc giữ B lâu hơn mong muốn.

Khi framework dùng `ServiceLoader.load(SomeService.class)` (overload sử dụng context loader phù hợp theo API), TCCL sai có thể khiến tìm nhầm provider version hoặc giữ provider loader cũ; không chỉ là vấn đề bộ nhớ.

## 8. ThreadLocal trong thread pool: hai dạng retention phổ biến

### Dạng A — ThreadLocal key đặt ở host, value do plugin tạo

```text
GC root -> pooled Thread
                 |
                 '--> ThreadLocal value (plugin instance)
                                |
                                '--> plugin Class<?> / loader
```

Đây là dạng dễ xảy ra khi host lưu `currentTenant`, `pluginContext` hoặc transaction context bằng `ThreadLocal` và vô tình ghi object thuộc plugin. Key trong host có thể sống suốt JVM, nên value còn trong worker có thể giữ plugin rất lâu.

### Dạng B — ThreadLocal key do plugin tạo

Plugin khai báo:

```java
package sample.plugin;

public final class PluginContext {
    static final ThreadLocal<Object> CURRENT = new ThreadLocal<>();
}
```

Đây là một class Java hợp lệ nếu đặt đúng file `PluginContext.java`. Nếu plugin code gọi `CURRENT.set(...)` trong host pool worker nhưng không gọi `CURRENT.remove()` trước khi trả thread:

- Worker giữ per-thread entry có thể chứa object/plugin metadata.
- Static field và bản `ThreadLocal` key thuộc class được plugin loader định nghĩa.
- Kể cả khi static reference/key có thể trở nên unreachable, một **stale ThreadLocalMap entry** trong các JDK implementations vẫn có thể giữ strong value tới khi cleanup.

Chỉ đặt `CURRENT = null` hoặc xóa reference tới plugin không đảm bảo dọn value đã lưu trong mọi worker threads. Không nên dùng reflection mở `java.lang.Thread.threadLocals` để xóa “thủ công”: internal layout không phải public API, JPMS có encapsulation, và truy cập/sửa xuyên thread dễ gây race hoặc phá framework state.

### InheritableThreadLocal và threads sinh từ plugin

`InheritableThreadLocal` có thể truyền giá trị từ parent sang child **khi tạo thread**. TCCL cũng có tính kế thừa theo Java `Thread` API. Nếu plugin tạo thread con khi TCCL/value đang trỏ vào plugin, child có thể giữ chúng sau khi parent hoàn thành.

**Executor reuse khác inheritance:** InheritableThreadLocal không được thiết kế như “per task context propagation” an toàn cho thread pool. Workers thường được tạo một lần rồi nhận nhiều tasks; value được thừa hưởng lúc tạo không tự cập nhật cho từng request. Nếu framework có context propagation chuyên biệt, đọc hợp đồng và cleanup của chính framework.

## 9. Tác vụ chưa dừng: không chỉ là ThreadLocal

Các đường retention khác thường thấy:

| Nguồn giữ tham chiếu | Đường tới loader | Cách dọn phù hợp |
| --- | --- | --- |
| `new Thread(pluginRunnable).start()` còn chạy | Thread → Runnable/stack → plugin code hoặc object. | Yêu cầu dừng hợp tác, cancel I/O, `join`, kiểm tra còn sống. |
| `ScheduledExecutorService.scheduleAtFixedRate` | Executor → recurring `ScheduledFuture`/Runnable → plugin closure. | `cancel` scheduled task, shutdown executor đúng ownership. |
| `ExecutorService` queue | Queue → `Runnable/FutureTask` → plugin captures. | Ngừng tiếp nhận, cancel/purge tasks, drain/terminate theo API. |
| `CompletableFuture` chưa hoàn tất | Completion chain/lambda → plugin values/functions. | Complete/cancel theo contract, xóa references chain, xử lý work nguồn. |
| Event bus/listener registry của host | Host singleton → listener object do plugin tạo. | `unsubscribe/unregister` listeners/callbacks. |
| Shutdown hook đã đăng ký | JVM hook registry → plugin Thread/Runnable. | `removeShutdownHook` theo lifecycle khi hợp lệ. |
| `Timer` / background scheduler | Timer thread và tasks giữ callbacks. | `Timer.cancel()`, xóa task refs, dùng scheduler chuẩn khi có thể. |
| Framework cache / SPI provider | Cache hoặc service registry → plugin `Class<?>`/instance. | Evict đúng cache, unregister providers, clear TCCL. |
| Static field của host | Host class → plugin instance / `Class<?>`. | Bỏ reference/callback, quản lý ownership. |
| Open sockets/streams | Resource và async callbacks vẫn hoạt động. | Close/cancel operations, unregister handlers. |

Một plugin có thể giữ thread chạy mã trong plugin package, nhưng host chưa bao giờ lưu plugin loader vào `ThreadLocal`. Nó vẫn có thể giữ class metadata qua stack và runnable. Vì thế **chỉ quét TCCL/ThreadLocal là chưa đủ** nếu plugin tạo tasks và callbacks khác.

### Interrupted không đồng nghĩa terminated

`Future.cancel(true)` hoặc `ExecutorService.shutdownNow()` thường chỉ cố **interrupt** thread chạy; Java không đảm bảo task hợp tác. Một task có thể:

- Bắt `InterruptedException` rồi tiếp tục vòng lặp.
- Bị kẹt I/O hoặc lời gọi bên thứ ba không có deadline.
- Giữ monitor trong deadlock.
- Tạo thread phụ và bỏ quên nó.
- Đăng ký callback/lambda vào global host singleton.

Vì vậy shutdown cần có **deadline, xác minh hoàn tất và chính sách xử lý thất bại**. Không dùng `Thread.stop()` như cách kill class loader; nó đã bị deprecated/không an toàn vì có thể phá invariants và monitors.

## 10. Close URLClassLoader không ép JVM unload Class

`URLClassLoader.close()` xử lý resource lookup và JAR handles thuộc loader, **không dừng worker threads**, xóa `ThreadLocal`, phục hồi TCCL hay hủy pending tasks. Class đã load vẫn có thể dùng sau close khi còn references.

Muốn retiring thread-related state, thực hiện cleanup tại đúng thread/executor owner rồi mới release generation; log unload chỉ là bước quan sát tùy JVM.

## 11. Một quy trình unload plugin có trách nhiệm

Plugin manager nên có trạng thái rõ ràng, ví dụ:

```text
ACTIVE -> QUIESCING -> STOPPING -> CLEANING -> CLOSED -> RETIRED
```

Trình tự tham khảo:

1. **Chặn việc gọi mới**: gỡ plugin khỏi route/dispatcher và từ chối tasks mới, tránh concurrent unload.
2. **Ngừng scheduled/background work**: cancel periodic tasks, ngừng subscription, dừng task producer.
3. **Chờ hoặc cancel tasks đang chạy**: dùng deadlines hợp lý, ghi nhận tasks chưa kết thúc, không tuyên bố thành công khi chúng còn sống.
4. **Chạy cleanup trong worker**: restore TCCL và gọi `ThreadLocal.remove` trong chính thread đã set; cleanup framework-specific request contexts.
5. **Đóng tài nguyên plugin**: streams, sockets, watchers, database handles, files, timers, JAR handles.
6. **Dừng plugin-owned executors/threads**: `shutdown`, `awaitTermination`; khi thất bại dùng `shutdownNow` theo contract, tiếp tục xác minh và phân loại blockers.
7. **Unregister references từ host**: listeners, MBeans, caches, service registries, logging appenders, callbacks, static maps, shutdown hooks.
8. **Close class loader** nếu API hỗ trợ; tránh thực hiện khi class loading khác vẫn đang diễn ra.
9. **Bỏ host references**: manager state không còn giữ plugin instance, `Class<?>`, loader, lambda hoặc `Future` của generation cũ.
10. **Kiểm tra bằng công cụ**: kiểm tra thread dump/heap dump/classloader statistics theo thời gian; không khẳng định GC tức thì.

Có thể chia cleanup thành các bước idempotent, ghi log lỗi theo từng bước và vẫn cố dọn các phần còn lại. Với platform thread/task không hợp tác, thực tế có thể cần **restart worker process hoặc host process** nếu không thể dừng an toàn.

### Shutdown executor chuẩn (minh họa)

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.TimeUnit;

// Snippet trong method có executor đã biết:
executor.shutdown();
try {
    if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
        executor.shutdownNow();
        if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
            System.err.println("Tasks remain active");
        }
    }
} catch (InterruptedException e) {
    executor.shutdownNow();
    Thread.currentThread().interrupt();
}
```

Đây là code minh họa xử lý lifecycle; `executor` do caller quản lý. Nó không tự giải phóng mọi `ThreadLocal` nếu tasks đã ghi chúng mà không remove, và `shutdownNow` không đảm bảo mọi task dừng. Với executor dùng chung của host, **không gọi `shutdown`** chỉ để unload một plugin; bạn cần cơ chế hủy/cleanup **các tasks thuộc plugin ấy** mà không làm hỏng các plugin khác.

## 12. ThreadFactory và việc ngăn kế thừa loader ngoài ý muốn

Khi tạo thread pool chung, một `ThreadFactory` đặt TCCL baseline rõ ràng giúp tránh kế thừa nhầm loader tại thời điểm workers được tạo:

```java
import java.util.concurrent.ThreadFactory;

ThreadFactory factory = task -> {
    Thread thread = new Thread(task, "host-shared-worker");
    thread.setContextClassLoader(
            ClassLoader.getPlatformClassLoader());
    return thread;
};
```

Đây là snippet cần dùng `factory` khi tạo executor; không phải class có `main`. Chọn loader baseline theo kiến trúc: `ClassLoader.getPlatformClassLoader()` chỉ phù hợp nếu công việc không cần host application classes từ TCCL; nhiều frameworks cần system/application loader. Một factory hardcode platform loader có thể khiến plugin providers của host không tìm thấy — **đây không phải lựa chọn mặc định cho mọi ứng dụng**.

Quan trọng hơn, dù factory đã đặt baseline, **mỗi task vẫn phải restore TCCL** sau khi tạm đổi sang plugin loader. Một task có thể làm bẩn state của pooled thread bất kể initial context là gì.

Với thread pools được framework quản lý, đừng tự tạo thread hoặc thay ThreadFactory không theo contract; xem cơ chế context propagation/lifecycle của container.

## 13. Chẩn đoán ClassLoader leak và retention graph

Đừng dùng `System.gc()` trong test rồi in “GC đã thu hồi loader” như một khẳng định có thể lặp lại. `System.gc()` chỉ là **request**, JVM có thể không thực hiện GC ngay hoặc có references khác không được nhìn thấy.

### Các công cụ nên dùng

- **Thread dump** (`jcmd <pid> Thread.print` hay công cụ tương đương): xem tên threads, stacks, WAITING/BLOCKED, plugin method frames, pool workers chưa dừng. Cần phân biệt một thread idle sống lâu hợp lệ với leak giữ TCCL/value cũ.
- **JFR (Java Flight Recorder):** xem hoạt động threads, allocations, class loading/unloading và các sự kiện liên quan theo cấu hình JDK/JFR; diễn giải cùng heap evidence.
- **Heap dump + Eclipse MAT/VisualVM:** tìm instance class loader cũ, retained size, **path to GC roots**, `Thread.contextClassLoader`, `ThreadLocalMap` entries, `FutureTask`, listener registry.
- **`jcmd <pid> VM.classloader_stats`**: kiểm tra thống kê loader/classes nếu lệnh được JVM hỗ trợ; thống kê không trực tiếp là graph root-cause.
- **Native Memory Tracking/metaspace metrics** nếu phù hợp: quan sát memory theo vùng, không mặc định growth chỉ do class loaders.

Lệnh tham khảo (đổi PID thành process thực):

```bash
jcmd <pid> Thread.print
jcmd <pid> VM.classloader_stats
jcmd <pid> GC.heap_dump /tmp/plugin-heap.hprof
```

Các dòng trên là **mẫu cú pháp công cụ**, không phải script chạy nguyên văn: `<pid>` là placeholder, tùy quyền attach của JVM và dung lượng disk. Heap dump có thể chứa **dữ liệu nhạy cảm**, phải xử lý như artifact bảo mật và không đưa công khai lên mạng.

### Đọc “path to GC roots” đúng cách

Ví dụ một đường giữ loader:

```text
GC Root
  -> Thread "host-executor-3"
  -> contextClassLoader
  -> PluginClassLoader#v17
```

Một đường khác:

```text
GC Root
  -> Thread "host-executor-3"
  -> threadLocals / ThreadLocalMap entry
  -> value: PluginContext
  -> class sample.plugin.PluginContext
  -> defining PluginClassLoader#v17
```

Nếu path dẫn qua `CompletableFuture`, `ScheduledThreadPoolExecutor` queue, `ServiceLoader` cache hoặc host static map, phải sửa **chủ sở hữu reference đó**, không chỉ TCCL.

**Đừng coi số lượng class loaders tăng một vài chu kỳ là chứng cứ tự động của leak.** GC và class unloading không ngay lập tức, JIT/runtime có lifecycle phức tạp. Cần đo sau những vòng load/unload có kiểm soát và xem references còn tồn tại theo heap snapshots.

### WeakReference kiểm tra thế nào?

Có thể giữ `WeakReference<ClassLoader>` trong bài test để quan sát loader có biến mất sau khi host bỏ strong references không. Nhưng:

- `ref.get() != null` tại một thời điểm **không tự chứng minh leak**.
- `ref.get() == null` cũng không khẳng định mọi resources/tasks được dọn đúng.
- Không giữ loader trong biến local, lambda hoặc debugger inspection khi test reachability.
- Không đòi kết quả `null` sau một số vòng `System.gc()` cố định, vì đây là kiểm tra có thể flaky.

Cách đáng tin hơn để tìm nguyên nhân là heap dump, GC roots và kiểm tra lifecycle được xây thành unit/integration tests cho từng registration/unregistration.

## 14. Trường hợp Java 21+ virtual threads có khác không?

Java 21 giới thiệu virtual threads dạng production, nhưng bài này ưu tiên chạy được trên Java 17. Cần phân biệt:

- Virtual thread cũng có `ThreadLocal` và context class loader semantics tương ứng, nhưng lifecycle thường **ngắn theo task** hơn pooled platform threads truyền thống.
- Nếu mỗi task dùng **một virtual thread riêng** rồi thread đó thực sự kết thúc, giá trị thread-local thường không bị giữ lâu bởi **chính thread đã kết thúc**.
- Tuy vậy, plugin object vẫn có thể bị giữ bởi **task chưa xong**, scheduler/framework references, `Future`, callback hoặc thread khác.
- Không xem “dùng virtual threads” là phép chữa mọi loader leak. Context propagation/inheritance và plugin tasks không ngừng vẫn cần phân tích.

Đừng trộn semantics của `Executors.newVirtualThreadPerTaskExecutor()` (Java 21) vào ví dụ `javac --release 17`; đó là API không có trong Java 17.

## 15. Các lỗi thường gặp

| Sai lầm | Hậu quả | Giải pháp |
| --- | --- | --- |
| Task plugin kết thúc nên pool worker chắc đã chết | Worker còn sống và giữ TCCL/ThreadLocal cũ. | Phân biệt task lifecycle và pool/thread lifecycle. |
| `ThreadLocal.remove()` trong main dọn value của worker | Không có tác dụng trên value thuộc worker. | Remove trong chính worker/task. |
| `System.setProperty("java.class.path", ...)` để “thay plugin” | Không cập nhật tự động loader/runtime classes. | Quản lý loader generation và dependency graph. |
| Set TCCL plugin mà không restore | Loader cũ tiếp tục được thread tham chiếu. | `try/finally` restore TCCL cũ. |
| Tạo pool khi TCCL là plugin loader | Worker mới có thể kế thừa loader plugin. | Dùng ThreadFactory/context baseline phù hợp. |
| Tin rằng `ThreadLocal` weak key không giữ value | Value có thể được giữ mạnh trong map. | Explicit `remove()` và worker lifecycle. |
| Gọi `URLClassLoader.close()` trước khi dừng tasks | Loader đóng nhưng task vẫn chạy hoặc nạp class/resource mới lỗi. | Quiesce, stop, cleanup, rồi close. |
| `Future.cancel(true)` chắc chắn giết task | Interrupt cần task hợp tác. | Deadlines, monitoring, process isolation nếu code không tin cậy. |
| Chỉ cleanup một task trong fixed pool nhiều workers | Các worker khác vẫn có TL/TCCL value. | Per-task cleanup hoặc shutdown pool thế hệ plugin. |
| Giữ `Class<?>`/plugin instance trong host cache | Defining loader vẫn reachable. | Evict caches và unregister listeners. |
| Dùng `System.gc()` như bằng chứng unload ngay | Không có timing guarantee. | Heap dump/path-to-roots và thống kê theo thời gian. |
| Không giới hạn `ScheduledExecutorService` recurring tasks | Scheduled callbacks có thể giữ plugin rất lâu. | Cancel futures, shutdown đúng ownership. |
| Cố dùng `Thread.stop()` để dừng plugin | Có thể làm hỏng invariant/monitor; API không an toàn. | Cooperative cancellation hoặc worker process riêng. |

## 16. Bài tập tự kiểm tra

1. **Một task có `Future.isDone() == true`, pool worker có thể còn sống không?** Có. Executor có thể giữ worker chờ task mới.
2. **Vì sao một TCCL vẫn trỏ vào plugin loader cũ có thể ngăn thu hồi loader?** Thread sống giữ reference mạnh tới loader.
3. **Một host static `ThreadLocal<Object>` giữ value plugin trên worker, main gọi `remove()` có xóa value ấy không?** Không; `remove` chỉ tác động current thread.
4. **`ThreadLocalMap` có weak keys đồng nghĩa mọi values được GC ngay khi key mất?** Không; value có thể còn giữ mạnh cho đến cleanup.
5. **`URLClassLoader.close()` có dừng background thread hoặc hủy static host registry không?** Không.
6. **Một plugin vẫn đang thực thi trên stack có đủ điều kiện bị unload chắc chắn không?** Không thể coi như vậy; stack frames/objects/class metadata của tác vụ có thể giữ loader reachable.
7. **Phải restore TCCL về system loader mọi lúc?** Không. Restore **giá trị trước khi tạm đổi**, không hardcode.
8. **ThreadFactory đã đặt baseline TCCL thì các task có cần finally restore không?** Có; worker có thể được tái sử dụng.
9. **Một cleanup task có dọn tất cả TL values trong fixed pool 10 threads không?** Không có bảo đảm; nó chỉ chạy trên một worker cụ thể.
10. **Vì sao `shutdownNow()` chưa đủ để xác nhận plugin đã dừng?** Vì interrupt có thể không được task hợp tác, và queued/callback references còn tồn tại.
11. **Hai kết quả của demo có chứng minh GC đã unload class không?** Không. Demo chỉ kiểm tra references TCCL/TL và class tiếp tục dùng sau close.
12. **Cần làm gì khi plugin không đáng tin và không thể dừng thread hợp tác?** Đặt plugin ở process có quota/timeout và quyền OS hạn chế, có thể terminate process nếu không hợp tác.

## 17. Tài liệu chính thức

- [Java SE 21 — Thread](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Thread.html): `getContextClassLoader`, `setContextClassLoader`, context inheritance, thread lifecycle.
- [Java SE 21 — ThreadLocal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ThreadLocal.html): per-thread values, `set`, `get`, `remove`.
- [Java SE 21 — InheritableThreadLocal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/InheritableThreadLocal.html): inheritance tại thời điểm tạo thread.
- [Java SE 21 — URLClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/net/URLClassLoader.html): semantics của `close` và khả năng dùng lớp đã load.
- [Java SE 21 — ExecutorService](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ExecutorService.html): `shutdown`, `shutdownNow` và `awaitTermination`.
- [Java SE 21 — Future](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Future.html): `isDone` và `cancel`.
- [Java SE 21 — ServiceLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ServiceLoader.html): chọn class loader cho provider lookup.
- [Java SE 21 — ClassLoader](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html): defining loader/class identity và delegation.
- [Java SE 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): thread dumps, VM classloader stats và heap dump tùy command/JVM.
- [Oracle Java SE 21 — Core Libraries, Thread-Local Variables](https://docs.oracle.com/en/java/javase/21/core/java-core-libraries-developer-guide.pdf): cơ chế ThreadLocal.
