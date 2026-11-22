# Kiểm chứng vòng đời đóng loader, dừng plugin và giải phóng tham chiếu

## 1. Mục tiêu: chứng minh teardown đúng, không chỉ gọi close()

Trong ứng dụng Java có plugin hoặc hot redeploy, vòng đời hợp lý thường là:

~~~text
Tạo ClassLoader cho plugin
           |
           v
Load class / tạo plugin instance
           |
           v
Đăng ký listener, task, scheduler, threads, resources
           |
           v
Plugin hoạt động
           |
           v
STOPPING: chặn tác vụ và callback mới
           |
           v
Gỡ registrations, dừng workers, đóng resources
           |
           v
Đóng URLClassLoader nếu plugin sở hữu nó
           |
           v
Bỏ strong references của host/plugin
           |
           v
Loader có thể đủ điều kiện được GC thu hồi
           |
           v
JVM có thể unload classes vào một thời điểm sau đó
~~~

Ba sự kiện dưới đây **khác nhau** và phải kiểm tra riêng:

1. **Plugin đã dừng đúng chức năng**: không nhận thêm callback/tác vụ, executor không còn chạy, tài nguyên do plugin sở hữu đã được đóng.
2. **Loader đã được đóng**: ví dụ **URLClassLoader.close()** giải phóng JAR/file handles do loader mở và không dùng loader đó để tìm *class/resource mới* của chính nó.
3. **Không còn tham chiếu mạnh giữ loader**: host registry, threads, thread context class loader (TCCL), ThreadLocal, instances, Class objects, Futures và caches không còn giữ phiên bản cũ.

**Đóng loader không đồng nghĩa JVM đã unload class.** Việc một loader có thể được GC thu hồi là điều kiện cần cho unloading của các class thông thường do loader ấy định nghĩa; quá trình GC/unload có thể xảy ra muộn hoặc không diễn ra trong thời gian quan sát. Bài này tập trung vào **kiểm chứng có bằng chứng**, không khẳng định “gọi System.gc() là PASS”.

### Kết quả học tập

Sau bài, bạn sẽ biết:

- Định nghĩa đúng trạng thái **STARTING/RUNNING/STOPPING/STOPPED/CLOSED/RELEASED**.
- Xây phép thử cho **URLClassLoader.close()** và hiểu điều gì vẫn hoạt động sau close.
- Tạo plugin nhỏ có **listener đăng ký ở host** và **ExecutorService riêng**, sau đó teardown deterministically.
- Chứng minh shared thread pool có thể giữ loader cũ qua **TCCL**; phục hồi đúng bằng **try/finally**.
- Dùng **WeakReference/ReferenceQueue** như diagnostic probe mà không tạo bài test GC dễ flake.
- Tìm **Path to GC Roots**, threads, queued tasks và metrics class loading/unloading.
- Phân biệt **điều kiện đủ để báo STOPPED** với **quan sát GC**.
- Thiết kế negative tests và kiểm tra lặp lại qua nhiều lần reload.

## 2. URLClassLoader.close() thực sự làm gì?

Theo Javadoc Java SE 17 của **java.net.URLClassLoader**:

- **close()** đóng loader để nó không thể tiếp tục tìm/nạp **những class hoặc resources mới do chính loader này định nghĩa**.
- Class/resources đã được loader tìm/nạp trước đó **vẫn có thể truy cập**.
- Class/resources được định nghĩa bởi **parent loaders** vẫn có thể được sử dụng qua delegation.
- Với URL dạng JAR/file, nó cố gắng đóng các opened files của loader.
- Nếu một thread đang load class khi thread khác gọi close, **kết quả load đồng thời đó không được xác định**.
- Nếu close nhiều lần, lời gọi sau trên loader đã đóng không có tác động thêm.
- close() có thể ném **IOException**, vì việc đóng các file handles có thể thất bại.

Vì vậy, không thể dùng:

~~~java
loader.close();
~~~

để thay thế tất cả thao tác **stop plugin**, **cancel tasks**, **unregister callbacks**, **clear ThreadLocal**, **release references** hay **class unloading**. Đó chỉ là một bước trong chu kỳ đóng.

### 2.1 Bốn tính chất cần tách riêng

| Việc kiểm chứng | Phương pháp | Kết luận phù hợp |
| --- | --- | --- |
| Class đã nạp còn dùng được sau close? | Giữ instance/Class trước khi close rồi gọi method sau close. | Close không invalidate instance/Class hiện có. |
| Class mới chỉ có trong JAR còn nạp được sau close? | Cố load một class chưa nạp trước close, bắt ClassNotFoundException. | Loader đã ngừng tìm class mới của chính nó. |
| Parent classes còn sẵn không? | loader.loadClass("java.lang.String"). | Parent/bootstrap delegation vẫn dùng được. |
| File/JAR handles đã đóng chưa? | Ghi nhận close() thành công và kiểm chứng thao tác file phù hợp môi trường. | Resource handles do URLClassLoader sở hữu được xử lý; không suy ra GC/unload. |

**Đừng dùng việc class đã load vẫn chạy sau close làm bằng chứng close thất bại.** Đó là behavior đã được API quy định.

### 2.2 Ai sở hữu URLClassLoader?

- **Host/container** thường tạo và sở hữu loader cho một deployment.
- **Plugin** sở hữu các resources/task/listeners mà nó tự tạo.
- Host chỉ gọi **loader.close()** sau khi plugin đã stop hợp tác và công việc đang chạy đã được drain/cancel theo chính sách.
- Không close một loader đang được dùng chung bởi nhiều plugin vẫn hoạt động.
- Không close **system/application loader** như thể nó là plugin loader do bạn sở hữu.
- Một custom ClassLoader khác URLClassLoader có thể **không có close()** và không phải AutoCloseable.

## 3. Một state machine teardown có thể kiểm thử

Một plugin manager nên xác định trạng thái rõ:

~~~text
NEW
 |
 v
STARTING -> RUNNING
             |
             v
          STOPPING
             |
             +-- chặn submit/callback mới
             +-- unregister listener và scheduler
             +-- chờ/cancel running tasks
             +-- close sockets, streams, files, sessions
             +-- dọn TCCL và ThreadLocal trên owner threads
             |
             v
           STOPPED
             |
             +-- URLClassLoader.close()
             |
             v
           CLOSED
             |
             +-- xóa references từ registry/cache/futures
             +-- bỏ các references host còn giữ
             |
             v
       RELEASED / GC-ELIGIBLE (chỉ là đánh giá reachability)
             |
             v
       Observed unload/GC (không bảo đảm thời điểm)
~~~

**STOPPED không bằng RELEASED.** Bạn có thể đã dừng mọi task nhưng còn một static map trong host giữ instance plugin. Ngược lại, bỏ reference trong registry khi worker vẫn đang chạy code plugin không có nghĩa teardown an toàn.

**GC-ELIGIBLE không phải một trạng thái JVM cam kết báo tức thì.** Đây là một trạng thái thiết kế/phân tích: bạn đã cắt mọi đường strong reference được quản lý trong hệ thống và không còn công việc plugin đang chạy. Heap analyzer/ReferenceQueue có thể bổ sung bằng chứng, nhưng không có API phổ thông bảo đảm trả lời ngay rằng tất cả class được unload.

## 4. Thiết kế tiêu chí PASS/FAIL theo mức độ

| Mức | Câu hỏi | Cách PASS đáng tin |
| --- | --- | --- |
| **Functional stop** | Plugin ngừng xử lý request/event mới? | Chặn intake, unregister callbacks; kiểm tra zero active registrations. |
| **Thread shutdown** | Executor/worker của plugin kết thúc? | shutdown hoặc shutdownNow phù hợp; awaitTermination thành công, thread đã dừng. |
| **Context cleanup** | Host worker có mang plugin TCCL sau task? | Kiểm tra context trở về previous ClassLoader trên worker. |
| **Resource cleanup** | Streams/sockets/handles đã đóng? | close hoặc try-with-resources; kiểm tra trạng thái/phép thử I/O thích hợp. |
| **Loader close** | URLClassLoader được đóng? | close thành công; không dùng lại để nạp class mới do nó định nghĩa. |
| **Reference cleanup** | Host còn callback, queue, cache, Future hay Class<?> giữ loader? | Kiểm tra owner registries rỗng; heap Path to GC Roots không còn retention path dự kiến. |
| **GC observation** | Weak ref bị clear, class unload event/metric xuất hiện? | Bằng chứng bổ sung có điều kiện; không bắt buộc để unit test teardown deterministically PASS. |

**Tránh một boolean "unloaded=true" tự báo do plugin đã stop.** Chỉ có thể nói rõ phần nào đã được xác nhận và phần nào còn phụ thuộc GC.

## 5. Ví dụ Java 17+ số 1 — close() không xóa Class đã nạp

Ví dụ đơn giản này tách hành vi **resource close** khỏi **Class identity và lifetime**.

### 5.1 Cấu trúc thư mục

~~~text
project/
├── plugin-src/lab/plugin/
│   ├── Ready.java
│   └── Later.java
└── CloseDemo.java
~~~

**plugin-src/lab/plugin/Ready.java**:

~~~java
package lab.plugin;

public class Ready {
    public String text() {
        return "ready";
    }
}
~~~

**plugin-src/lab/plugin/Later.java**:

~~~java
package lab.plugin;

public class Later {
    public String text() {
        return "later";
    }
}
~~~

**CloseDemo.java**:

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class CloseDemo {
    public static void main(String[] args) throws Exception {
        URL jar = Path.of("plugin.jar").toUri().toURL();

        URLClassLoader loader = new URLClassLoader(
                new URL[]{jar},
                ClassLoader.getPlatformClassLoader());

        Class<?> ready = loader.loadClass("lab.plugin.Ready");
        Object object = ready.getConstructor().newInstance();

        System.out.println("before close = "
                + ready.getMethod("text").invoke(object));

        loader.close();

        System.out.println("after close = "
                + ready.getMethod("text").invoke(object));

        System.out.println("parent available = "
                + (loader.loadClass("java.lang.String")
                        == String.class));

        try {
            loader.loadClass("lab.plugin.Later");
            System.out.println("unexpected load");
        } catch (ClassNotFoundException expected) {
            System.out.println("new plugin class rejected = true");
        }
    }
}
~~~

Đứng tại thư mục **project**, dùng JDK 17+:

~~~bash
javac --release 17 -d plugin-out plugin-src/lab/plugin/Ready.java plugin-src/lab/plugin/Later.java
jar --create --file plugin.jar -C plugin-out .
javac --release 17 CloseDemo.java
java CloseDemo
~~~

Trên Windows PowerShell, các lệnh trên cũng chạy được vì classpath trong ví dụ chỉ chứa một root; **không cần** thay dấu phân tách classpath.

**Stdout đã biên dịch/chạy thực tế trên OpenJDK 21:**

~~~text
before close = ready
after close = ready
parent available = true
new plugin class rejected = true
~~~

### 5.2 Vì sao output đúng?

1. **Ready** được định nghĩa từ plugin.jar và một instance được tạo **trước close**.
2. Loader đóng JAR/file handles qua close.
3. Method **Ready.text()** đã có sẵn vẫn chạy được. **close không invalidate object hoặc Class object**.
4. **java.lang.String** được định nghĩa bởi bootstrap loader, vẫn có thể tìm qua delegation.
5. **Later** chưa được nạp trước close và chỉ tồn tại trong plugin.jar. Do URLClassLoader đã close, lookup của class mới thất bại bằng **ClassNotFoundException**.

**Bẫy kiểm thử:** Nếu gọi **loader.loadClass("lab.plugin.Later")** trước close, nó đã cached/initiated và có thể vẫn truy cập sau close. Phải chọn **một class chắc chắn chưa nạp** để kiểm tra đúng điều kiện.

**Giới hạn:** Demo giữ mạnh biến **loader**, **ready** và **object** trong main khi in output. Nó **không** kiểm chứng class unloading. Nó chỉ chứng minh close semantics và khả năng dùng classes/resources đã load.

## 6. Ví dụ Java 17+ số 2 — dừng plugin, gỡ listener và kết thúc executor

Ví dụ này dùng **host API contract** chung, plugin implementation được nạp bằng URLClassLoader riêng. Plugin sở hữu:

- Một **Runnable listener** đăng ký trong host registry; nó giữ tham chiếu đến plugin instance qua method reference.
- Một **single-thread ExecutorService** do plugin tạo, worker mang **plugin ClassLoader làm TCCL**.
- Một giao thức **start → stop** đóng các đường giữ ở host và chờ worker termination.

### 6.1 Cấu trúc dự án

~~~text
lifecycle/
├── host-src/
│   ├── host/api/Plugin.java
│   ├── host/api/Registry.java
│   └── HostLifecycleDemo.java
└── plugin-src/
    └── plug/PluginImpl.java
~~~

Thư mục output:

~~~text
host-out/          class files của host và shared API
plugin-out/        class files implementation của plugin
plugin-impl.jar    JAR plugin, không chứa bản sao host.api.*
~~~

**Quan trọng:** Interface **host.api.Plugin** phải do host loader định nghĩa. Plugin implementation dùng **cùng Class object** khi cast. Đừng gói bản sao host.api.Plugin riêng vào plugin-impl.jar rồi child-first redefine interface chung.

### 6.2 Shared interface

**host-src/host/api/Plugin.java**:

~~~java
package host.api;

public interface Plugin {
    void start(Registry registry) throws Exception;
    boolean stop(Registry registry) throws Exception;
}
~~~

Method **stop** trả true khi plugin-owned worker đã kết thúc trong thời hạn. Ví dụ đơn giản hóa lifecycle; ứng dụng thật thường có status object chứa chi tiết lỗi, timeout và cleanup status cho từng resource.

### 6.3 Host registry

**host-src/host/api/Registry.java**:

~~~java
package host.api;

import java.util.HashSet;
import java.util.Set;

public final class Registry {
    private final Set<Runnable> listeners = new HashSet<>();

    public void add(Runnable listener) {
        listeners.add(listener);
    }

    public void remove(Runnable listener) {
        listeners.remove(listener);
    }

    public int count() {
        return listeners.size();
    }
}
~~~

Registry là ví dụ đồng bộ đơn giản do tất cả lời gọi add/remove/count trong fixture đến từ một thread host. Trong ứng dụng nhiều threads, cần thêm synchronization hoặc concurrent data structure và giao thức ngăn callback mới sau STOPPING.

**Registry có thể giữ plugin lâu hơn dự tính:** Vì listener là object do plugin tạo và có thể capture plugin instance, host registry nếu giữ listener sẽ trở thành **đường tham chiếu mạnh** tới plugin và defining loader.

### 6.4 Plugin implementation

**plugin-src/plug/PluginImpl.java**:

~~~java
package plug;

import host.api.Plugin;
import host.api.Registry;
import java.util.concurrent.*;

public final class PluginImpl implements Plugin {
    private ExecutorService pool;
    private Runnable callback;

    private void onEvent() {
        // Một callback của plugin.
    }

    @Override
    public void start(Registry registry) throws Exception {
        callback = this::onEvent;
        registry.add(callback);

        pool = Executors.newSingleThreadExecutor(task -> {
            Thread worker = new Thread(task, "plugin-worker");
            worker.setContextClassLoader(
                    getClass().getClassLoader());
            return worker;
        });

        // Future.get(): bảo đảm worker đã được tạo/chạy
        // trước khi host tiến hành kiểm thử stop.
        pool.submit(() -> {}).get();
    }

    @Override
    public boolean stop(Registry registry) throws Exception {
        registry.remove(callback);
        callback = null;

        pool.shutdownNow();
        boolean terminated = pool.awaitTermination(
                5, TimeUnit.SECONDS);

        pool = null;
        return terminated;
    }
}
~~~

### 6.5 Launcher của host

**host-src/HostLifecycleDemo.java**:

~~~java
import host.api.Plugin;
import host.api.Registry;
import java.lang.ref.WeakReference;
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public class HostLifecycleDemo {
    static WeakReference<ClassLoader> cycle(
            Registry registry) throws Exception {

        URL url = Path.of("plugin-impl.jar").toUri().toURL();

        try (URLClassLoader loader = new URLClassLoader(
                new URL[]{url},
                HostLifecycleDemo.class.getClassLoader())) {

            Class<?> pluginClass =
                    loader.loadClass("plug.PluginImpl");

            Plugin plugin = (Plugin) pluginClass
                    .getConstructor().newInstance();

            plugin.start(registry);

            System.out.println("listeners while active = "
                    + registry.count());

            System.out.println("worker terminated = "
                    + plugin.stop(registry));

            System.out.println("listeners after stop = "
                    + registry.count());

            // WeakReference không giữ loader sống.
            return new WeakReference<>(loader);
        } // URLClassLoader.close() qua try-with-resources.
    }

    public static void main(String[] args) throws Exception {
        Registry registry = new Registry();

        WeakReference<ClassLoader> probe = cycle(registry);

        System.out.println("cleanup checks passed = "
                + (registry.count() == 0));

        // Chỉ xác nhận ta có probe, KHÔNG khẳng định GC đã chạy.
        System.out.println("probe installed = "
                + (probe != null));
    }
}
~~~

### 6.6 Biên dịch/chạy

Đứng tại thư mục **lifecycle**:

~~~bash
javac --release 17 -d host-out host-src/host/api/Plugin.java host-src/host/api/Registry.java host-src/HostLifecycleDemo.java
javac --release 17 -cp host-out -d plugin-out plugin-src/plug/PluginImpl.java
jar --create --file plugin-impl.jar -C plugin-out .
java -cp host-out HostLifecycleDemo
~~~

**Stdout đã chạy thực tế trên OpenJDK 21:**

~~~text
listeners while active = 1
worker terminated = true
listeners after stop = 0
cleanup checks passed = true
probe installed = true
~~~

### 6.7 Vì sao ví dụ này kiểm chứng được teardown?

**Bước RUNNING:**

- Plugin object được tạo từ Class do URLClassLoader mới định nghĩa.
- Host nhận một Runnable callback là method reference **this::onEvent**, nên registry giữ đường tham chiếu tới plugin instance.
- Plugin-owned executor tạo thread, TCCL của worker trỏ tới plugin loader.
- **submit(...).get()** bảo đảm worker đã nhận task; nếu chỉ gọi newSingleThreadExecutor mà không submit, worker có thể chưa được tạo.

**Bước STOPPING/STOPPED:**

- **registry.remove(callback)** cắt host listener reference.
- **callback = null** dọn reference nội bộ của plugin.
- **shutdownNow()** phát tín hiệu dừng bằng interrupt và cancel queued tasks phù hợp.
- **awaitTermination(5s)** xác nhận worker đã kết thúc trong timeout. Với fixture no-op task, trả true.
- **pool = null** bỏ reference plugin giữ tới executor sau khi dừng.
- **try-with-resources** close loader sau khi stop return.

**Bước RELEASE CANDIDATE:**

- Method **cycle** trả **WeakReference** thay vì trả instance/Class/loader mạnh.
- Sau khi cycle return, biến local **plugin**, **pluginClass**, **loader** của frame đó không còn được dùng bởi host launcher.
- Host registry vẫn tồn tại, nhưng **count() = 0**, nên không còn callback do ví dụ quản lý.

Đây là **bằng chứng đã dọn những đường giữ mà fixture tạo ra**. Không tự suy rằng toàn JVM hết mọi tham chiếu mạnh hoặc loader được unload ngay. WeakReference có thể vẫn trả non-null một thời gian vì GC chưa diễn ra hoặc runtime còn references khác.

### 6.8 Điều kiện production phải bổ sung

Fixture ưu tiên ngắn gọn và stdout deterministically kiểm chứng được. Một hệ thực cần:

- Nếu **stop() ném exception giữa chừng**, cleanup registry, executor và resource vẫn phải chạy trong finally/đường bù.
- Nếu **awaitTermination trả false**, không được xóa reference rồi báo worker đã chết. Giữ trạng thái **STOP_TIMEOUT/BLOCKED**, ghi thread dump và xử lý theo policy.
- **InterruptedException** khi host đợi shutdown phải phục hồi interrupt flag hoặc tuân theo hợp đồng hủy.
- **shutdownNow** không ép thread lập tức dừng; task phải hợp tác với interrupt.
- Phải dọn **queued tasks/Futures/listeners** ở cả host và plugin, không chỉ những biến có trong fixture.
- Plugin có thể sở hữu thêm **ScheduledExecutorService, ThreadLocal, socket, file handle, JDBC connection, MBean, driver, timers, JMX/logging hooks**.
- Nếu **close()** ném IOException, không được coi resource close PASS mặc nhiên; JDK có thể gắn nhiều failures trong suppressed exceptions.
- **Chặn registration mới trước khi drain**, nếu không plugin có thể thêm listener mới ngay sau khi host vừa xóa registry.
- Không gọi close loader trong khi threads đang nạp class. URLClassLoader Javadoc nói behavior của load đồng thời với close là không xác định.

## 7. Kiểm chứng TCCL: shared host worker có thể giữ plugin cũ

Trong môi trường server dài hạn, **Thread Context ClassLoader** của một thread có thể là đường giữ mạnh:

~~~text
GC root -> live Host worker Thread
                 |
                 +-- contextClassLoader
                           |
                           v
                      OldPluginLoader
                           |
                           +-- class metadata/objects có liên quan
~~~

Một task plugin có thể đặt TCCL là loader của plugin để dùng ServiceLoader, resource loading hoặc framework APIs. Nếu task return nhưng không **restore previous context**, host pool giữ worker sống lâu và tiếp tục giữ loader cũ.

### 7.1 Bad pattern

~~~java
Thread.currentThread()
        .setContextClassLoader(pluginLoader);
invokePlugin();
// Nếu task throw hoặc return sớm -> không restore.
~~~

Đây là snippet với pluginLoader/invokePlugin có sẵn. Nó **không phải chương trình độc lập** và là anti-pattern cố ý.

Một task sau có thể chạy với **TCCL của phiên bản plugin cũ**, gây cả **memory retention** và **lookup sai class/provider/resource**.

### 7.2 Correct pattern

~~~java
Thread current = Thread.currentThread();
ClassLoader previous = current.getContextClassLoader();

current.setContextClassLoader(pluginLoader);
try {
    invokePlugin();
} finally {
    current.setContextClassLoader(previous);
}
~~~

**Luôn restore chính previous**, không đoán system loader là đúng và không mặc định set null. Previous có thể là host loader, framework loader hoặc null.

Nếu API nhận loader rõ ràng (ví dụ một số ServiceLoader overloads), có thể **truyền loader tường minh** để tránh thay shared thread state khi phù hợp.

## 8. Ví dụ Java 17+ số 3 — host pool leak TCCL và khôi phục bằng finally

Tạo file **TcclPoolDemo.java** cùng thư mục có plugin.jar từ ví dụ 1:

~~~java
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.concurrent.*;

public class TcclPoolDemo {
    public static void main(String[] args) throws Exception {
        ClassLoader host =
                TcclPoolDemo.class.getClassLoader();

        URLClassLoader plugin = new URLClassLoader(
                new java.net.URL[]{
                        Path.of("plugin.jar").toUri().toURL()
                },
                host);

        ExecutorService pool =
                Executors.newSingleThreadExecutor(job -> {
            Thread t = new Thread(job, "host-worker");
            t.setContextClassLoader(host);
            return t;
        });

        try {
            // Cố ý quên restore trong một task.
            pool.submit(() -> Thread.currentThread()
                    .setContextClassLoader(plugin)).get();

            System.out.println("after unsafe task = "
                    + pool.submit(() -> Thread.currentThread()
                        .getContextClassLoader() == plugin).get());

            // Dọn context cũ trên CHÍNH host worker.
            pool.submit(() -> Thread.currentThread()
                    .setContextClassLoader(host)).get();

            System.out.println("restored baseline = "
                    + pool.submit(() -> Thread.currentThread()
                        .getContextClassLoader() == host).get());

            try {
                pool.submit(() -> {
                    Thread thread = Thread.currentThread();
                    ClassLoader prior =
                            thread.getContextClassLoader();

                    thread.setContextClassLoader(plugin);
                    try {
                        throw new IllegalStateException(
                                "task failed");
                    } finally {
                        thread.setContextClassLoader(prior);
                    }
                }).get();
            } catch (ExecutionException expected) {
                System.out.println("error = "
                        + expected.getCause()
                                .getClass().getSimpleName());
            }

            System.out.println("after failed task = "
                    + pool.submit(() -> Thread.currentThread()
                        .getContextClassLoader() == host).get());
        } finally {
            pool.shutdown();

            if (!pool.awaitTermination(
                    5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
                pool.awaitTermination(5, TimeUnit.SECONDS);
            }

            plugin.close();
        }

        System.out.println("pool terminated = "
                + pool.isTerminated());
    }
}
~~~

Biên dịch và chạy (trong thư mục của plugin.jar ví dụ 1):

~~~bash
javac --release 17 TcclPoolDemo.java
java TcclPoolDemo
~~~

**Stdout đã chạy thực tế trên OpenJDK 21:**

~~~text
after unsafe task = true
restored baseline = true
error = IllegalStateException
after failed task = true
pool terminated = true
~~~

### 8.1 Giải thích kết quả

- **after unsafe task = true:** Single-thread executor tái sử dụng worker; task đầu đã đặt TCCL tới plugin loader nhưng không restore. Task tiếp theo thấy plugin context vẫn còn.
- **restored baseline = true:** Một task cleanup chạy **trên cùng worker** phục hồi host loader. Không đổi TCCL của worker bận từ một thread khác một cách tùy tiện.
- **error = IllegalStateException:** Task thử nghiệm cố ý ném lỗi. Khi Future.get() phát hiện lỗi, nó bọc nguyên nhân trong ExecutionException.
- **after failed task = true:** **finally** vẫn chạy để restore TCCL khi task thất bại.
- **pool terminated = true:** Host shutdown và await trong fixture thành công.

**Điểm quan trọng:** Ví dụ không dùng GC làm điều kiện PASS. Nó kiểm tra **trực tiếp một retention path**, nên kết quả deterministic dưới đúng môi trường chạy.

### 8.2 TCCL kế thừa khi tạo thread mới

Theo Thread API, một thread mới thường **kế thừa contextClassLoader của thread tạo ra nó**, trừ khi cấu hình khác. Nếu tạo plugin worker trong khi thread tạo đang mang plugin TCCL, thread con có thể giữ plugin loader **kể cả sau khi parent đã restore**.

Vì vậy:

- Host **ThreadFactory** cho shared pools nên đặt baseline TCCL phù hợp, thay vì vô tình kế thừa plugin context.
- Plugin-owned thread có thể dùng plugin TCCL trong suốt vòng đời của plugin nhưng **phải dừng và giải phóng** khi plugin stop.
- Đừng dựa vào thread name hay daemon flag để kết luận loader không bị giữ. Một live daemon thread vẫn có thể giữ references trong JVM đang chạy.
- Executor có thể tạo worker **lúc task đầu được submit**, không bắt buộc lúc constructor executor được gọi.

## 9. ThreadLocal và các reference paths khác

**TCCL chỉ là một đường giữ mạnh**. Trong production, có thể còn:

~~~text
Live Thread
    +-- contextClassLoader -> OldPluginLoader
    +-- ThreadLocalMap value -> PluginObject
    +-- Runnable/Future đang thực thi -> PluginObject

Host static Registry
    +-- callback/listener -> PluginObject
    +-- service cache -> Plugin Class
    +-- plugin metadata -> URLClassLoader

Scheduler / Executor queue
    +-- Delayed task -> Plugin Runnable
    +-- Future -> Callable / result / class from plugin
~~~

### 9.1 Dọn ThreadLocal trên owner thread

~~~java
ThreadLocal<Object> local = new ThreadLocal<>();

try {
    local.set(pluginScopedValue);
    executePluginTask();
} finally {
    local.remove();
}
~~~

Đây là snippet minh họa với pluginScopedValue và executePluginTask có sẵn.

**Restore TCCL không gọi ThreadLocal.remove().** Ngược lại, remove ThreadLocal không xóa TCCL. Phải cleanup cả hai nếu scope dùng cả hai.

ThreadLocalMap có weak keys, nhưng values có thể vẫn bị giữ trong thread lâu sống khi entry chưa được làm sạch. Việc không còn reference tới ThreadLocal key **không phải** bằng chứng ngay lập tức value đã được thu hồi.

### 9.2 Các nguồn giữ hay bị quên

- **ScheduledFuture** của periodic task, kể cả sau khi plugin “không làm gì nữa”.
- Host-managed **ExecutorService** còn queued tasks do plugin submit.
- **CompletableFuture** chains hoặc callbacks capture plugin state.
- Global **Map/Set/caches** chứa Class, Method, MethodHandle hoặc object do plugin class tạo.
- Logging handlers, metrics listeners, event bus registrations, MBeans/JMX, JDBC drivers, ShutdownHooks.
- Thread-created **TCCL inheritance** và custom ThreadFactory.
- ThreadLocal values trên shared workers.
- Class<?> và instance **được lưu vào static field thuộc host**.
- Resources mở ngoài URLClassLoader như FileInputStream, ZipFile, Socket, native libraries.

Các loại giữ này **không được đóng tự động chỉ vì URLClassLoader.close() trả về**.

## 10. WeakReference/ReferenceQueue: dùng đúng để quan sát, không biến GC thành assertion cứng

Một công cụ chẩn đoán là:

~~~java
WeakReference<ClassLoader> weak =
        new WeakReference<>(pluginLoader);
~~~

WeakReference không tự giữ đối tượng được tham chiếu sống, khác với một reference mạnh. Nhưng **chỉ tạo weak reference khi vẫn giữ biến pluginLoader mạnh chưa chứng minh gì**.

### 10.1 Điều kiện quan trọng nhất

Bạn phải đưa quá trình **tạo loader + load classes + instantiate plugin + stop + close** vào một method riêng và chỉ trả về **weak reference** sau khi frame đó kết thúc; đồng thời host phải unregister mọi references do nó quản lý.

Mô hình ở ví dụ 2:

~~~text
static WeakReference<ClassLoader> cycle(...) {
    URLClassLoader loader = new URLClassLoader(...);
    try {
        ... start ...
        ... stop/drain/unregister ...
        return new WeakReference<>(loader);
    } finally {
        loader.close();
    }
}

WeakReference<ClassLoader> probe = cycle(...);
~~~

Đây là pseudocode minh họa cấu trúc; chương trình runnable đầy đủ ở phần 6 dùng try-with-resources.

**Mục đích:** giảm khả năng local variables trong caller vô tình giữ loader trong khi bạn kiểm tra reachability.

### 10.2 ReferenceQueue cho tín hiệu một chiều

Nếu muốn nhận thông báo khi GC xử lý reference:

~~~java
ReferenceQueue<ClassLoader> queue =
        new ReferenceQueue<>();

WeakReference<ClassLoader> probe =
        new WeakReference<>(loader, queue);
~~~

Snippet trên cần imports **java.lang.ref.ReferenceQueue/WeakReference** và biến loader có sẵn.

- Khi **probe được clear/enqueue** theo cơ chế GC, đó là bằng chứng hữu ích rằng referent không còn được weak reference giữ và GC đã xử lý nó.
- **queue.poll() == null** chưa chứng minh loader bị leak; GC có thể chưa xử lý hoặc chưa enqueue.
- **probe.get() != null** chưa chứng minh có một đường tham chiếu mạnh bất thường; có thể JVM chưa thu hồi đối tượng.
- Ngay cả khi loader được thu hồi, việc quan sát **class unloading** còn là sự kiện JVM riêng, không được đồng bộ tức thì với user code.
- ReferenceQueue không mang metadata chính xác về **GC root** đã từng giữ loader; nếu thấy retention, dùng heap analyzer.

### 10.3 Vì sao không viết unit test “System.gc rồi phải null”?

~~~java
System.gc();
assert weak.get() == null;
~~~

Đây là **phản ví dụ**: phép kiểm tra này không đáng tin.

**System.gc() là request/hint**, không có cam kết theo thời gian rằng loader sẽ bị thu hồi trong thời điểm đó. GC có thể không thực thi theo yêu cầu, có thể trì hoãn class unloading, hoặc code test/debugger/JIT vẫn giữ reference tạm. Do đó test dễ **flaky** giữa JDK/JVM/CI environments.

Nếu cần stress/probe để quan sát, có thể thử nhiều vòng với timeout hữu hạn và in:

~~~text
OBSERVED: weak reference cleared
~~~

hoặc:

~~~text
INCONCLUSIVE: not collected within observation window
~~~

Đây là **hai kết quả thay thế**, không phải stdout cố định. **INCONCLUSIVE không đồng nghĩa FAILED** trừ khi test có giả định/điều kiện GC được kiểm soát và định nghĩa rõ.

### 10.4 Negative control giúp kiểm tra probe đúng hơn

Trong lab test riêng:

1. Giữ một **strong reference cố ý** từ host registry tới plugin/loader.
2. Xác nhận bằng kiểm tra registry rằng reference ấy còn tồn tại.
3. Thực hiện cleanup và bỏ reference.
4. Dùng WeakReference/ReferenceQueue hoặc heap snapshot để quan sát.
5. Nếu chỉ dùng GC signal mà không đo đường root, không tuyên bố chắc chắn negative control là bằng chứng leak thực tế.

**Điểm quyết định là chẩn đoán đường giữ cụ thể**, không phải đếm số lần gọi System.gc.

## 11. Kiểm thử repeated reload và nhận diện memory leak thực

Một loader leak thường rõ nhất sau nhiều lần reload:

~~~text
Deploy #1 -> Loader1 -> RUNNING -> STOP
Deploy #2 -> Loader2 -> RUNNING -> STOP
Deploy #3 -> Loader3 -> RUNNING -> STOP

Nếu host registry/thread còn giữ:
GC roots -> Loader1, Loader2, Loader3 ...

Nếu cleanup đúng:
references owned by host về loaders cũ được bỏ
-> loaders có thể được GC thu hồi về sau
~~~

### 11.1 Một kế hoạch đo hợp lý

1. **Warm-up baseline:** đo classloader counts/metaspace sau khi host startup ổn định.
2. **Deploy:** ghi module/plugin version, loader identity, loaded class count, số callbacks/tasks.
3. **Run:** tạo workload đại diện, bao gồm tasks async, resources, ServiceLoader và callbacks.
4. **Stop:** ngừng intake; hủy pending tasks; chờ running tasks kết thúc theo timeout.
5. **Close/release:** unregister; close resources; close loader; clear host refs.
6. **Observe:** đo sau nhiều chu kỳ bằng công cụ JVM; dùng heap dump nếu loaders cũ tích tụ.
7. **Investigate GC roots:** tìm **Reference path từ GC root tới old loader**, không chỉ nhìn biểu đồ heap.
8. **Regression test:** bổ sung asserts cho chính listener registry, executor termination, TCCL và closure policies.

Đừng kết luận memory leak chỉ vì metaspace cao ngay sau deploy: HotSpot có thể giữ/commit memory và unload vào thời điểm phù hợp. Nhưng **số lượng old plugin loaders vẫn strongly reachable tăng đều** cùng cụ thể các paths qua threads/caches là tín hiệu đáng điều tra.

### 11.2 Các chỉ số có ý nghĩa và giới hạn

| Quan sát | Cho biết | Không cho biết |
| --- | --- | --- |
| **ClassLoadingMXBean.getLoadedClassCount()** | Số class hiện loaded ở JVM theo metric | Không chỉ ra loader cụ thể giữ class nào. |
| **ClassLoadingMXBean.getUnloadedClassCount()** | Tổng class đã unloaded tích lũy | Không bảo đảm loader vừa stop đã được unload. |
| **JFR class load/unload events** | Sự kiện JVM khi cấu hình thu thập phù hợp | Không nhất thiết xác định GC root gây retention. |
| **jcmd VM.classloader_stats** | Classloader/class metadata statistics, tùy JVM hỗ trợ | Không tự chỉ ra callback/ThreadLocal nào đang giữ loader. |
| **Heap dump + MAT** | Path to GC Roots, dominator tree, retained objects | Snapshot phụ thuộc thời điểm và GC trước đó. |
| **Thread dump** | Worker threads, stack, blocking state | Không đủ chứng minh mọi Java object retention path. |
| **OS file handles** | Có còn JAR/file handle mở không | Không phải bằng chứng class unloaded. |

**Nên có nhiều góc nhìn** vì close, GC eligibility, class unloading và OS resource handles là những lớp trạng thái khác nhau.

## 12. Chẩn đoán bằng jcmd, JFR và heap dump

Trên HotSpot JDK phù hợp, một số lệnh thường dùng:

~~~bash
jcmd
jcmd <PID> help
jcmd <PID> VM.classloader_stats
jcmd <PID> GC.class_histogram
jcmd <PID> GC.heap_dump /path/to/heap.hprof
~~~

**<PID>** ở trên là placeholder process ID, không phải ký tự gõ nguyên văn. Tên command có thể tùy JDK/JVM, do đó hãy **jcmd <PID> help** trước khi áp dụng.

**Cảnh báo vận hành:** Heap dump có thể rất lớn, gây pause/I/O và chứa dữ liệu nhạy cảm (tokens, PII, business objects). Chỉ lấy khi được phép và có chính sách lưu giữ/xóa phù hợp.

### 12.1 GC root path thường gặp

Nếu live worker giữ TCCL:

~~~text
GC Root: Java Thread
   |
   +-- Thread.contextClassLoader
         |
         +-- URLClassLoader (old plugin)
~~~

Nếu host registry giữ callback:

~~~text
GC Root: host static field
   |
   +-- ListenerRegistry
         |
         +-- Runnable callback
             |
             +-- PluginImpl instance
                  |
                  +-- Class PluginImpl / defining loader
~~~

Nếu executor queue giữ task:

~~~text
GC Root: Host ExecutorService
   |
   +-- workQueue
         |
         +-- FutureTask / Runnable
              |
              +-- captured plugin object
                    |
                    +-- defining loader
~~~

Có thể tồn tại **nhiều đường root cùng lúc**. Sửa TCCL mà quên listener registry vẫn giữ loader; sửa listener mà còn task queue cũng chưa đủ.

### 12.2 Quy trình MAT/JFR

- Heap dump: tìm instance của URLClassLoader/custom PluginLoader, đặc biệt loader phiên bản cũ.
- Xem **Incoming references** và **Path to GC Roots**; loại trừ weak/soft refs trong phân tích để tập trung strong paths phù hợp.
- Xem retained size và số loader versions sau nhiều deploy cycles.
- So sánh trước/sau cleanup ở workloads tương đương.
- Dùng JFR/class unloading events nếu muốn biết JVM có thực sự unload classes, nhưng đừng biến absence of event trong cửa sổ ngắn thành lỗi teardown.
- Dùng thread dumps để xác định plugin-owned threads còn sống/blocked và xử lý shutdown hang.

### 12.3 Không nhầm close với file-delete portability

**URLClassLoader.close()** giúp đóng file/JAR handles do loader đã mở, hữu ích khi cần thay/deploy JAR, đặc biệt trên hệ điều hành khóa file. Nhưng một process còn **file stream/JarFile khác** tự mở ngoài loader vẫn có thể giữ handle; đóng loader không đóng mọi resource bên ngoài nó.

Ngoài ra, OS/file-system behavior khác nhau; khả năng thay file thành công không chứng minh JVM đã unload classes từ phiên bản trước.

## 13. Lifecycle tối thiểu nên có trong production

Một lifecycle manager có thể biểu đạt dưới dạng pseudo-code:

~~~java
// Pseudocode cấu trúc, không phải class chạy độc lập.
stopAcceptingNewWork(pluginId);

try {
    unregisterHostCallbacks(pluginId);
    cancelOrDrainQueuedTasks(pluginId);
    stopPluginOwnedExecutors(pluginId);
    awaitWorkersStopped(pluginId, timeout);

    closePluginOwnedStreamsSocketsAndResources(pluginId);
    verifyThreadLocalsAndTcclCleanup(pluginId);

    // Chỉ khi không còn active class/resource loading.
    pluginLoader.close();

    clearHostReferences(pluginId);
} finally {
    recordShutdownOutcome(pluginId);
}
~~~

**Không coi đoạn này là đủ cho mọi trường hợp:** nó trình bày thứ tự ý tưởng. Một triển khai thật phải có đường xử lý lỗi cho từng bước, timeout, idempotence, reentrancy, concurrent stop/start, interrupt policy và resource owner.

### 13.1 Idempotent stop

Plugin.stop có thể được gọi hai lần vì retry hoặc shutdown signal lặp. Một lifecycle vững cần:

- Không re-register khi STOPPING.
- Unregister idempotent hoặc an toàn khi listener đã được gỡ.
- shutdown executor nhiều lần không gây state bất nhất.
- close loader multiple times không tạo thêm vấn đề.
- Persist/report trạng thái để host không lầm timeout là STOPPED.

### 13.2 Trường hợp stop bị treo

Nếu plugin thread block I/O không phản hồi interrupt:

- **shutdownNow không bảo đảm termination**.
- Không dùng **Thread.stop()** để cưỡng bức kết thúc vì nguy hiểm, có thể phá invariants.
- Dùng I/O timeouts, cancel/callback cooperative protocol, đóng socket để unblock, thread dump và escalation policy.
- Không close loader trong lúc còn thread có thể cần load class mới hoặc resource; Javadoc coi concurrent close/load là undefined.
- Khi không thể đạt trạng thái an toàn, báo **STOP_TIMEOUT/BLOCKER**, không đánh dấu RELEASED.

## 14. Những anti-pattern thường tạo loader leaks

### 14.1 Chỉ close URLClassLoader mà không stop plugin

~~~java
loader.close();
plugin.stop();
~~~

Thứ tự này có thể đóng nguồn classes/resources **trong khi task plugin còn chạy**. Nếu task sau đó cần class chưa nạp hoặc resource mới, có thể lỗi. Hãy quiesce/stop workers trước, rồi close khi quyền sở hữu rõ ràng.

### 14.2 Đánh dấu plugin STOPPED rồi quên registry

~~~text
plugin.state = STOPPED
registry.listeners vẫn chứa plugin callback
~~~

Host vẫn giữ object plugin, nghĩa là loader có thể chưa collectible. Dùng register/unregister đối xứng với lifecycle.

### 14.3 Đổi TCCL mà không restore

Host worker thuộc thread pool lâu sống sẽ tiếp tục mang plugin loader sau khi task return. Dùng try/finally trên worker; kiểm thử task **ném exception** như ví dụ 3.

### 14.4 Tin rằng daemon thread không giữ references

Daemon thread vẫn là live Thread khi JVM còn chạy, vẫn có thể giữ plugin loader/TCCL/ThreadLocals. Daemon chỉ ảnh hưởng quy tắc JVM exit; không biến references thành weak.

### 14.5 Gọi System.gc() rồi coi weak.get()!=null là FAIL

GC không bảo đảm thu hồi ngay. Bài test như vậy có thể flaky trên CI, các JVM flags, các GC algorithms và debugger.

### 14.6 Chỉ kiểm thử trường hợp STOP sạch

Lỗi lifecycle thường xảy ra khi:

- Plugin.start thất bại **sau khi đã register callback**.
- Task đang chạy ném exception.
- Executor shutdown timeout.
- Close một stream ném IOException.
- Hai threads cùng gọi stop.
- Callback mới đến trong lúc đang unregister.
- Worker tạo thêm child Thread kế thừa plugin TCCL.
- Plugin hot reload nhiều lần làm old instances tích tụ.

Phải có negative tests cho những đường lỗi, không chỉ happy path.

### 14.7 Giữ ClassLoader trong metrics/test harness

Test tự tạo một list:

~~~java
static final java.util.List<ClassLoader> history =
        new java.util.ArrayList<>();
~~~

rồi thêm loader của từng deploy vào mà không xóa. Danh sách đó trở thành **strong reference leak do test tạo ra**. Nếu cần thống kê loader lifecycles, chỉ lưu string ID, deployment timestamps hoặc WeakReferences phù hợp.

### 14.8 Static field của host giữ Class/Method/MethodHandle

Plugin đã stop nhưng host cache reflection có thể giữ Class của plugin. Vì runtime Class của class thông thường liên hệ với defining loader, những references này có thể ngăn unloading. Clear caches theo plugin ID/version.

### 14.9 Chỉ xét heap mà quên native/file resources

Có thể không có loader leak nhưng có file/socket/native leak; và ngược lại loader leak dù OS handles đã đóng. Theo dõi hai thứ riêng.

## 15. Bộ checklist kiểm thử tự động

### 15.1 Trước stop

- [ ] Loader mới định nghĩa đúng plugin class (không nhầm parent-defined class).
- [ ] Plugin API type đến từ shared loader phù hợp.
- [ ] Plugin đã đăng ký listener/task/scheduler đúng expected count.
- [ ] Plugin-owned executor đã tạo worker theo nhu cầu thực tế.
- [ ] TCCL đang dùng đúng trong phạm vi công việc; host worker baseline được lưu.
- [ ] Có deployment/plugin ID rõ để truy tìm references khi reload.

### 15.2 Trong STOPPING

- [ ] Chặn callback/task mới trước khi drain.
- [ ] Unregister đầy đủ listeners/subscriptions/metrics hooks.
- [ ] Cancel queued tasks và kết thúc running tasks theo cooperative policy.
- [ ] awaitTermination thành công hoặc báo timeout rõ, không giả PASS.
- [ ] ThreadLocal.remove() trên các workers thích hợp.
- [ ] TCCL khôi phục previous ClassLoader ở shared host worker.
- [ ] Đóng plugin-owned streams/sockets/JDBC/JMX/resources.
- [ ] Không còn thread thực thi code plugin khi close loader.

### 15.3 Sau stop/close

- [ ] Close URLClassLoader do deployment sở hữu và ghi nhận IOException nếu có.
- [ ] Bỏ references từ registries, caches, Futures và metrics.
- [ ] Kiểm tra host registry count đúng baseline.
- [ ] Kiểm tra executor isTerminated/threads ended.
- [ ] Kiểm tra host worker context không còn old plugin loader.
- [ ] Nếu có GC probe, báo **OBSERVED/INCONCLUSIVE** theo kết quả thực, không assert tức thời.
- [ ] Có kế hoạch heap dump/JFR nếu repeated reload làm retained old loaders tăng.

Checklist là **hợp đồng kiểm thử đề xuất**; không phải mọi mục đều áp dụng cho mọi plugin. Nhưng mọi thành phần mà plugin **thực sự sở hữu** phải có cleanup đối xứng.

## 16. Một test matrix cho các tình huống thực tế

| Test | Thiết lập | Kết quả cần xác nhận |
| --- | --- | --- |
| **Close loaded class** | Load Ready, tạo instance, close loader, gọi Ready.text. | Instance đã load vẫn chạy. |
| **Close new class** | Giữ Later chưa load, close trước rồi yêu cầu Later. | Không tìm class mới từ loader đã close. |
| **Parent after close** | close plugin loader rồi yêu cầu String. | Parent/bootstrap class vẫn dùng được. |
| **Listener unregister** | Plugin start đăng ký callback. | Host registry count về baseline sau stop. |
| **Executor termination** | Plugin worker được start bằng submit. | awaitTermination thành công hoặc báo timeout. |
| **Unsafe TCCL negative** | Host worker chạy task đổi TCCL không restore. | Task sau nhìn thấy plugin TCCL vẫn bị giữ. |
| **finally on exception** | Plugin task throw sau khi set TCCL. | TCCL của host worker trở về previous. |
| **ThreadLocal cleanup** | Task đặt value từ plugin trên shared worker. | remove() trên worker trong finally. |
| **Partial start failure** | start ném lỗi sau khi register. | Startup rollback gỡ listener/stop workers. |
| **Repeated reload** | Deploy/stop 20-100 lần trong lab. | Registries/threads baseline; retention paths không tích tụ. |
| **GC probe** | Trả WeakReference sau cleanup, bỏ strong refs. | Quan sát GC nếu có; timeout là INCONCLUSIVE. |
| **Forced stalled task** | Task không phản hồi interrupt (chỉ lab). | Stop báo timeout, không close/đánh dấu safe tùy tiện. |

**Không cố định một số lần GC hoặc thời gian thu hồi chung cho mọi JVM** trong test matrix. Kiểm tra deterministic cleanup trước rồi mới dùng GC observations để phân tích bổ sung.

## 17. Tự kiểm tra kiến thức

**Câu 1.** Gọi URLClassLoader.close() rồi instance class đã nạp trước đó vẫn chạy. Có phải close lỗi không?

**Đáp án:** Không. Javadoc cho phép tiếp tục sử dụng classes/resources đã nạp.

**Câu 2.** Loader.close() có shutdown Thread do plugin tự tạo không?

**Đáp án:** Không. Thread/executor phải được plugin/container quản lý riêng, stop/cancel và await termination.

**Câu 3.** Plugin đã unregister listener nhưng host worker còn contextClassLoader=oldPluginLoader. Loader có thể bị giữ không?

**Đáp án:** Có. Live Thread giữ strong reference qua TCCL.

**Câu 4.** Vì sao phải restore previous TCCL trong finally?

**Đáp án:** Vì task có thể return sớm hoặc throw; host pool tái sử dụng cùng worker sau khi task xong.

**Câu 5.** Thread mới tạo khi parent thread đang mang plugin TCCL, parent restore sau đó thì child tự restore không?

**Đáp án:** Không. Thread con có context riêng đã kế thừa từ thời điểm tạo, trừ khi cấu hình khác.

**Câu 6.** awaitTermination trả false nhưng registry rỗng. Có nên báo plugin fully stopped không?

**Đáp án:** Không. Worker có thể còn chạy; cần xử lý timeout và xem resource/thread ownership.

**Câu 7.** WeakReference.get() chưa null sau System.gc(). Có chứng minh memory leak không?

**Đáp án:** Không. GC/unloading không có cam kết xảy ra ngay; kết quả là INCONCLUSIVE nếu không có thêm bằng chứng.

**Câu 8.** Tại sao giữ Class<?> của plugin trong host static Map có thể ngăn class unloading?

**Đáp án:** Class object thuộc class thông thường liên hệ với defining loader; strong reference giữ Class có thể giữ loader reachable.

**Câu 9.** close() thành công có nghĩa mọi FileInputStream do plugin mở đều được đóng không?

**Đáp án:** Không. URLClassLoader đóng resources do nó sở hữu; streams do plugin tự mở phải đóng riêng.

**Câu 10.** Khi nào nên close loader theo thứ tự lifecycle?

**Đáp án:** Sau khi chặn công việc mới, stop/drain threads, unregister callbacks, đóng resources và bảo đảm không còn concurrent loading không an toàn.

**Câu 11.** Vì sao repeated reload dễ phát hiện leak hơn một lần stop?

**Đáp án:** Các old loaders/callbacks/threads có thể tích tụ qua mỗi vòng, làm retention paths và metaspace pressure rõ hơn.

**Câu 12.** Công cụ nào trả lời ai đang giữ old ClassLoader?

**Đáp án:** Heap dump với Path to GC Roots/dominator tree, kết hợp thread dumps, JFR/jcmd metrics và code ownership.

## 18. Kết luận

~~~text
ĐÓNG LOADER != DỪNG PLUGIN != CLASS UNLOADING

STOP/QUIESCE:
  stop nhận công việc -> unregister -> drain/cancel tasks
  -> await worker termination -> cleanup TCCL/ThreadLocal
  -> close tài nguyên plugin

CLOSE:
  URLClassLoader.close()
  -> đóng handles do loader sở hữu
  -> không tìm new classes/resources của loader
  -> old Class/instances vẫn có thể dùng

RELEASE:
  clear host registries/caches/Futures/Class references
  -> loader có thể không còn strongly reachable
  -> GC có thể thu hồi vào thời điểm không xác định
  -> JVM có thể unload class sau đó

VERIFY:
  deterministic: trạng thái/tasks/threads/context/resources
  diagnostic: WeakReference, ReferenceQueue, JFR, jcmd, heap roots
~~~

**Bản kiểm thử tốt nhất không bắt GC làm theo một thời hạn tùy ý.** Nó chứng minh các bước cleanup thuộc quyền kiểm soát của ứng dụng bằng assertions deterministic, đồng thời dùng heap/GC observations để điều tra những tham chiếu còn tồn tại hoặc việc unload diễn ra sau đó.

### Tài liệu tham khảo

- Java SE 17 **URLClassLoader.close()**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- Java SE 17 **ClassLoader API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- Java SE 17 **Thread context ClassLoader**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
- Java SE 17 **ExecutorService shutdown/awaitTermination**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- Java SE 17 **WeakReference / ReferenceQueue**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html
- Java SE 17 **ClassLoadingMXBean**: https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html
- Java SE 17 **JLS §12.7 Class Unloading**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7
- Java SE 17 **jcmd**: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
