# Rò rỉ bộ nhớ khi luồng sống lâu giữ loader của plugin

## 1. Hiện tượng

Một ứng dụng Java chạy lâu có thể nạp plugin bằng ClassLoader riêng, chạy code của plugin, sau đó unload/redeploy. Nếu hoàn tất cleanup, ClassLoader cũ và các class do nó định nghĩa có thể đủ điều kiện được thu hồi.

Nhưng một thread sống lâu của host có thể đang giữ **Thread Context ClassLoader (TCCL)** trỏ tới loader cũ. Đây là một strong reference:

~~~text
GC root / live thread
       |
       v
Host worker thread (vẫn sống)
       |
       v
Thread.contextClassLoader
       |
       v
PluginClassLoader phiên bản cũ
       |
       +-- class metadata và đối tượng liên quan

=> Loader vẫn reachable dù plugin đã stop
=> Các class của plugin có thể không unload được
~~~

Sau nhiều lần deploy, nhiều phiên bản PluginClassLoader bị giữ có thể gây tăng heap, metaspace và đôi khi OutOfMemoryError: Metaspace. Không phải cứ tăng bộ nhớ là do TCCL; bài này chỉ rõ cơ chế này và cách chẩn đoán những đường giữ khác.

**Mục tiêu:** phân biệt TCCL với defining loader; hiểu reachability; tái hiện strong reference bằng Java 17+; khôi phục loader trong finally; kiểm soát việc kế thừa context ở thread con; quản lý executor, ThreadLocal và vòng đời plugin; tìm GC roots trong heap dump.

## 2. TCCL không phải defining loader

API của java.lang.Thread:

~~~java
Thread t = Thread.currentThread();
ClassLoader previous = t.getContextClassLoader();
t.setContextClassLoader(pluginLoader);
~~~

Đây là code minh họa đặt trong method có biến pluginLoader, chưa là chương trình độc lập.

TCCL là **một thuộc tính có thể đổi của Thread**. Một số framework dùng nó để tìm class, resources hoặc providers. Theo JDK API, khi tạo thread mới mà không cấu hình riêng, context loader thường được kế thừa từ thread tạo ra nó.

| API / khái niệm | Ý nghĩa |
| --- | --- |
| Thread.currentThread().getContextClassLoader() | Loader ngữ cảnh hiện tại của thread. |
| Thread.setContextClassLoader(loader) | Đổi ngữ cảnh cho thread này; không định nghĩa lại class. |
| SomeClass.class.getClassLoader() | Defining loader của class; không đổi vì TCCL đổi. |
| ClassLoader.getSystemClassLoader() | System/application loader, không mặc nhiên trùng TCCL của mọi thread. |
| ServiceLoader.load(service) | Một ví dụ API sử dụng context loader theo hợp đồng của overload này. |
| ServiceLoader.load(service, loader) | Một overload cho phép truyền loader tường minh. |

**TCCL không làm thay đổi danh tính của class.** Danh tính kiểu runtime thông thường liên quan binary name cùng defining loader. Đổi TCCL không chuyển một Class hiện hữu từ plugin sang host hoặc ngược lại.

## 3. Vì sao TCCL có thể trở thành một memory leak?

### 3.1 GC nhìn tham chiếu, không nhìn trạng thái nghiệp vụ

Khi host đánh dấu plugin STOPPED, object ClassLoader chưa chắc có thể bị thu hồi. Nếu worker còn sống, JVM vẫn có thể giữ Thread; field contextClassLoader trong Thread giữ reference đến PluginLoader.

~~~text
Host ExecutorService
    |
    +-- worker (chờ nhận task tiếp theo)
           |
           +-- contextClassLoader = oldPluginLoader

Plugin Registry đã xóa plugin cũ
JAR handle đã đóng
Nhưng oldPluginLoader vẫn có đường tham chiếu mạnh
~~~

Trong server chạy liên tục, một worker có thể tồn tại lâu hơn mọi phiên bản plugin được nó từng phục vụ.

### 3.2 Điều kiện class unloading

Theo JLS §12.7, một class/interface có thể bị unload chỉ khi **defining ClassLoader** của nó có thể được garbage collector thu hồi. Nếu long-lived thread giữ loader, điều kiện này chưa thỏa.

Tuy nhiên, **xóa đường tham chiếu không bảo đảm JVM unload ngay**. GC và class unloading được thực hiện theo nhu cầu, cấu hình và implementation. Cần phân biệt:

1. Plugin đã ngừng nhận công việc.
2. Mọi task, callback, thread và registry đã được cleanup.
3. ClassLoader không còn strongly reachable.
4. JVM đã thực sự thu hồi/unload class (có thể sau đó).

**System.gc() không phải phép đo quyết định:** đó là yêu cầu/hint, không phải lời cam kết loader sẽ biến mất ngay.

### 3.3 Heap và Metaspace

ClassLoader và object giữ tham chiếu ở heap. JVM HotSpot sử dụng metaspace để quản lý nhiều loại class metadata. Nếu loader cũ không collectible, class metadata cũng có thể tiếp tục tồn tại; redeploy liên tục có thể gây áp lực metaspace. Triệu chứng còn phụ thuộc số class, GC, giới hạn bộ nhớ và các reference khác.

## 4. Kịch bản phổ biến: task plugin đổi TCCL trên host pool

Một ứng dụng tạo pool dùng chung:

~~~text
Host starts
    |
    +-- ExecutorService hostPool
           |
           +-- host-worker-1 (sống hàng giờ)
~~~

Plugin v1 chạy trong worker:

~~~java
Thread.currentThread().setContextClassLoader(pluginLoader);
invokePlugin();
// Quên restore
~~~

Nếu task return thành công, worker vẫn có thể được pool tái sử dụng với **contextClassLoader = PluginLoaderV1**. Host unload v1 rồi nạp v2 bằng loader mới, nhưng loader v1 vẫn nằm trên worker.

Hậu quả kép:

- **Retention:** loader cũ còn reachable.
- **Sai context:** task chạy sau có thể dùng nhầm loader của plugin cũ để tìm provider, class hoặc resource.

Sự cố thường lộ ra khi application redeploy nhiều lần chứ không phải ở lần khởi động đầu.

## 5. Ví dụ Java 17+ số 1: quan sát strong reference ở thread sống lâu

Tạo file **ContextRetentionDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class ContextRetentionDemo {
    static final class PluginLoader extends ClassLoader {
        PluginLoader(ClassLoader parent) {
            super(parent);
        }
    }

    public static void main(String[] args) throws Exception {
        ClassLoader host = ContextRetentionDemo.class.getClassLoader();
        PluginLoader plugin = new PluginLoader(host);

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            started.countDown();
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "host-worker");

        worker.setContextClassLoader(plugin);
        worker.start();
        started.await();

        System.out.println("worker alive = " + worker.isAlive());
        System.out.println("worker holds plugin = "
                + (worker.getContextClassLoader() == plugin));

        worker.setContextClassLoader(host);
        System.out.println("worker restored host = "
                + (worker.getContextClassLoader() == host));

        release.countDown();
        worker.join();
        System.out.println("worker stopped = " + !worker.isAlive());
    }
}
~~~

Chạy:

~~~bash
javac ContextRetentionDemo.java
java ContextRetentionDemo
~~~

Stdout xác định trong ví dụ:

~~~text
worker alive = true
worker holds plugin = true
worker restored host = true
worker stopped = true
~~~

**Phân tích:** worker đang đợi latch và vẫn sống. Trước khi reset, field TCCL của worker giữ chính object plugin. Thay bằng host cắt **đường giữ qua TCCL**, rồi chương trình giải phóng latch và join để kết thúc thread.

**Giới hạn:** ví dụ không chứng minh GC đã xảy ra. Biến local plugin trong main vẫn còn giữ loader, và loader trong ví dụ chưa được dùng để định nghĩa class plugin. Nó chỉ xác nhận cơ chế strong reference, không đo lượng metaspace. Trong production, thông thường để **worker tự phục hồi context trong finally** thay vì thread khác thay context khi nó đang chạy công việc.

## 6. Cách sửa cốt lõi: lưu và khôi phục previous TCCL

Mẫu cần ưu tiên:

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

Đây là snippet đặt trong method có pluginLoader và invokePlugin() phù hợp.

Vì sao cần **finally**?

- Task có thể return sớm hoặc ném exception.
- Thread pool giữ worker sống sau khi task hoàn thành.
- Việc restore phải xảy ra trước khi worker nhận task tiếp theo.
- **previous** có thể là loader của host, loader của framework khác hoặc null. Không đoán rằng system loader luôn đúng.

**setContextClassLoader(null) không tương đương restore previous.** Null có ngữ nghĩa fallback của API, nhưng có thể không khôi phục đúng context của thread trước khi plugin chạy.

Nếu thao tác setContextClassLoader thất bại trước khi vào try (ví dụ vì ràng buộc bảo mật của runtime), đừng kết luận scope đã dùng loader mới. Cần xử lý lỗi theo hợp đồng framework.

**Nếu không cần TCCL, đừng đổi nó.** Khi API hỗ trợ truyền ClassLoader tường minh, sử dụng tham số đó có thể tránh sửa shared thread state.

## 7. Ví dụ Java 17+ số 2: executor phục hồi TCCL kể cả khi Callable lỗi

Tạo **ScopedContextDemo.java**:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

public class ScopedContextDemo {
    static final class PluginLoader extends ClassLoader {
        PluginLoader(ClassLoader parent) {
            super(parent);
        }
    }

    static <T> Callable<T> withContext(
            ClassLoader pluginLoader,
            Callable<T> action) {

        return () -> {
            Thread current = Thread.currentThread();
            ClassLoader previous = current.getContextClassLoader();

            current.setContextClassLoader(pluginLoader);
            try {
                return action.call();
            } finally {
                current.setContextClassLoader(previous);
            }
        };
    }

    public static void main(String[] args) throws Exception {
        ClassLoader host = ScopedContextDemo.class.getClassLoader();
        PluginLoader plugin = new PluginLoader(host);

        ExecutorService pool = Executors.newSingleThreadExecutor(task -> {
            Thread worker = new Thread(task, "host-pool-1");
            worker.setContextClassLoader(host);
            return worker;
        });

        try {
            System.out.println("before = " + pool.submit(
                    () -> Thread.currentThread()
                            .getContextClassLoader() == host
            ).get());

            System.out.println("during = " + pool.submit(
                    withContext(plugin, () ->
                            Thread.currentThread()
                                    .getContextClassLoader() == plugin)
            ).get());

            System.out.println("after = " + pool.submit(
                    () -> Thread.currentThread()
                            .getContextClassLoader() == host
            ).get());

            try {
                pool.submit(withContext(plugin, () -> {
                    throw new IllegalStateException("boom");
                })).get();
            } catch (ExecutionException expected) {
                System.out.println("failure = "
                        + expected.getCause()
                                .getClass().getSimpleName());
            }

            System.out.println("after failure = " + pool.submit(
                    () -> Thread.currentThread()
                            .getContextClassLoader() == host
            ).get());
        } finally {
            pool.shutdown();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                pool.shutdownNow();
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac ScopedContextDemo.java
java ScopedContextDemo
~~~

Stdout:

~~~text
before = true
during = true
after = true
failure = IllegalStateException
after failure = true
~~~

Giải thích:

1. ThreadFactory host tạo worker với TCCL là host loader, không phụ thuộc context của thread đang submit.
2. Wrapper **withContext** đổi sang plugin loader trong phạm vi công việc.
3. Sau khi job kết thúc, **finally** phục hồi previous.
4. Khi job ném **IllegalStateException**, Future.get bọc nó vào **ExecutionException**, nhưng cleanup vẫn chạy.
5. Task cuối nhìn thấy host TCCL, cho thấy không còn plugin context trên worker đó.

**Đây chưa phải giải pháp cho tất cả reference leaks.** Callable có thể capture plugin loader và vẫn nằm trong task queue, Future hoặc callback registry do host giữ. Phải hủy/xóa các reference đó ở lifecycle unload.

## 8. Nguy cơ thứ hai: thread con kế thừa TCCL ở thời điểm tạo

JDK Thread API quy định context loader mặc định của thread mới được kế thừa từ thread tạo ra nó, nếu không bị cấu hình riêng.

~~~text
Thread A (host): TCCL = PluginLoader
        |
        | new Thread(...)
        v
Thread B: TCCL kế thừa = PluginLoader
        |
Thread A restore HostLoader
        |
Thread B vẫn có TCCL riêng trỏ PluginLoader
~~~

Chỉ restore A không khiến B tự restore. Nếu B sống hàng giờ, nó có thể giữ loader cũ.

### Ví dụ Java 17+ số 3

Tạo file **InheritedContextDemo.java**:

~~~java
public class InheritedContextDemo {
    static final class PluginLoader extends ClassLoader {
        PluginLoader(ClassLoader parent) {
            super(parent);
        }
    }

    public static void main(String[] args) throws Exception {
        Thread parent = Thread.currentThread();
        ClassLoader previous = parent.getContextClassLoader();
        PluginLoader plugin = new PluginLoader(previous);
        Thread child;

        try {
            parent.setContextClassLoader(plugin);

            child = new Thread(() -> {
                System.out.println("child inherited plugin = "
                        + (Thread.currentThread()
                                .getContextClassLoader()
                                instanceof PluginLoader));
            }, "background-child");

            System.out.println("before start = "
                    + (child.getContextClassLoader() == plugin));
        } finally {
            parent.setContextClassLoader(previous);
        }

        child.start();
        child.join();

        System.out.println("parent restored = "
                + (parent.getContextClassLoader() == previous));
    }
}
~~~

Chạy:

~~~bash
javac InheritedContextDemo.java
java InheritedContextDemo
~~~

Stdout:

~~~text
before start = true
child inherited plugin = true
parent restored = true
~~~

**before start = true** chứng minh child đã nhận context trước khi start. Trong ví dụ child kết thúc nên không khẳng định leak lâu dài; trong thực tế nếu child chạy mãi, nó có thể giữ PluginLoader.

### Vì sao thread pool có thể kế thừa ngoài ý muốn?

**Executors.newSingleThreadExecutor** không bắt buộc tạo worker ngay khi construct executor; worker có thể được tạo khi submit task đầu tiên. Nếu thread submitter lúc đó mang plugin TCCL, ThreadFactory mặc định có thể cho worker kế thừa loader plugin. ThreadFactory do host sở hữu nên **đặt baseline context loader rõ ràng** cho mọi worker.

## 9. Đúng ownership khi quản lý executor

| Thành phần | Chủ sở hữu | Khi unload plugin |
| --- | --- | --- |
| Host ExecutorService shared | Host | Không shutdown toàn bộ; dừng/cancel task thuộc plugin, chờ cleanup và reset TCCL trên worker. |
| Plugin-owned ExecutorService | Plugin/container | Ngừng nhận task, shutdown, awaitTermination, cancel nếu cần. |
| Plugin ScheduledExecutorService | Plugin | Hủy scheduled jobs, shutdown và bỏ references tới Runnable/Callable plugin. |
| Thread riêng do plugin tạo | Plugin | Dừng hợp tác bằng interrupt/cờ dừng, unblock, join phù hợp. |
| Host ThreadFactory | Host | Cài đặt TCCL baseline an toàn cho workers. |
| Host registry của listeners/callbacks | Host + plugin | Unregister callbacks và references trước khi kết thúc unload. |
| ThreadLocal trên shared worker | Scope sở hữu key/value | Remove trong finally khi scope kết thúc. |

**Không dùng Thread.stop** để cưỡng bức dừng worker: nó nguy hiểm và có thể phá invariants. Interrupt chỉ là tín hiệu, không chứng minh thread đã chết. Một task không phản hồi interrupt cần timeout và giao thức stop phù hợp, không nên được báo là teardown thành công vô điều kiện.

**Đừng đổi TCCL của worker đang bận từ một thread khác** trong production nếu chưa điều phối; điều đó có thể ảnh hưởng lookup đang diễn ra. Trình tự an toàn là ngừng nhận task mới, chờ/cancel task, cho cleanup trên chính thread chạy task thực hiện, rồi quản lý references.

## 10. ThreadLocal là một đường retention riêng

TCCL là một field trên Thread. ThreadLocal dùng cấu trúc **ThreadLocalMap**, nơi value có thể là instance do plugin loader định nghĩa.

~~~text
Live Thread
  |
  +-- contextClassLoader -> PluginLoader
  |
  +-- threadLocals / ThreadLocalMap
         |
         +-- Entry.value -> PluginObject
                                 |
                                 +-- defining PluginLoader
~~~

Key trong ThreadLocalMap có tính chất weak, nhưng **value vẫn có thể bị giữ** trên long-lived worker nếu scope không remove. Việc quên TCCL và quên ThreadLocal có thể đồng thời tạo hai đường giữ mạnh.

Mẫu cleanup cho ThreadLocal do scope sở hữu:

~~~java
ThreadLocal<Object> state = new ThreadLocal<>();

try {
    state.set(pluginObject);
    runPluginTask();
} finally {
    state.remove();
}
~~~

Đây là snippet minh họa, không phải chương trình hoàn chỉnh; cần pluginObject và runPluginTask phù hợp.

**Restore TCCL không tự gọi state.remove().** Ngược lại, remove ThreadLocal không tự reset context loader. Khi dùng cả hai, cleanup cả hai trong finally (và xử lý thứ tự/error nếu cleanup có thể ném exception).

Không dùng reflection vào nội bộ Thread để “quét sạch tất cả ThreadLocal” của framework mà không có quyền sở hữu rõ.

## 11. Quy trình unload/redeploy an toàn

~~~text
1. Đưa plugin vào trạng thái STOPPING
         |
         v
2. Chặn task/callback mới thuộc plugin
         |
         v
3. Hủy/drain queue và running tasks theo timeout
         |
         v
4. Trong mọi task/plugin callback:
   - restore TCCL trong finally
   - remove ThreadLocal value do scope sở hữu
   - đóng streams/sessions/resources
         |
         v
5. Shutdown và chờ threads/executors do plugin sở hữu
         |
         v
6. Unregister listener, scheduler, driver, MBean,
   logging/service hooks và cache/callback còn giữ plugin
         |
         v
7. Xóa host references tới plugin objects và loader
         |
         v
8. Quan sát class-loader retention qua nhiều lần redeploy
~~~

**Race conditions cần chú ý:**

- Task mới lọt vào queue ngay sau khi bắt đầu stop.
- Task đang chạy tạo thêm Thread kế thừa plugin TCCL.
- Pool thay worker bằng thread mới khi context không đúng.
- Future/cache vẫn giữ Callable capture plugin loader.
- Callback khác còn đang chạy khi registry đã đánh dấu plugin stopped.
- Exception khiến nhánh cleanup không thực thi.

Vì vậy unload có thể cần một trạng thái **quiescing/draining** rõ ràng, thay vì chỉ xóa object plugin khỏi map rồi hy vọng GC xử lý.

## 12. URLClassLoader.close không phải lệnh unload mọi class

Một số loader như **URLClassLoader** có **close()** để đóng tài nguyên và file handles. Nhưng nếu một Thread vẫn có TCCL trỏ tới URLClassLoader đã close, loader đó vẫn reachable.

Phải phân biệt:

- **Đóng resource handles**.
- **Dừng background work**.
- **Xóa references** tới ClassLoader và các object của plugin.
- **JVM thu hồi khi đủ điều kiện**.

Đừng tự ý close loader chia sẻ giữa nhiều plugin đang hoạt động.

## 13. Chẩn đoán bằng heap dump, JFR và jcmd

Nếu nghi leak sau redeploy, cần tìm **đường tham chiếu giữ loader cũ**, không chỉ quan sát một biểu đồ RAM.

### 13.1 Công cụ

Với JVM HotSpot có những lệnh phù hợp:

~~~bash
jcmd
jcmd <PID> help
jcmd <PID> VM.classloader_stats
jcmd <PID> GC.class_histogram
jcmd <PID> GC.heap_dump /path/to/heap.hprof
~~~

Cú pháp và tính khả dụng phụ thuộc JDK/JVM; chạy **jcmd <PID> help** để xác nhận. Heap dump có thể lớn, tốn thời gian và chứa dữ liệu nhạy cảm; không tạo trên production khi chưa có quy trình vận hành/cho phép.

- **JFR (Java Flight Recorder)**: theo dõi class load/unload events, GC và tài nguyên khi bật cấu hình phù hợp.
- **Eclipse Memory Analyzer (MAT)**: mở heap dump, dùng **Path to GC Roots**, incoming references và retained size.
- **Thread dump**: tìm các worker còn sống, stuck hoặc đang giữ callback cũ.
- **Metaspace/classloader metrics**: so sánh nhiều chu kỳ deploy với baseline.

### 13.2 Mẫu Path to GC Roots

Nếu nguyên nhân là TCCL, heap analyzer có thể cho đường:

~~~text
GC Root: Java Thread
   |
   -> java.lang.Thread
        |
        -> contextClassLoader
             |
             -> PluginClassLoader (old deployment)
~~~

Nếu nguyên nhân khác:

~~~text
GC Root
   |
   -> host ExecutorService / listener registry / cache
        |
        -> Future / Runnable / callback / PluginObject
             |
             -> plugin class / PluginClassLoader
~~~

Khi có cả hai, sửa một đường vẫn có thể không đủ. **Đường mạnh đến GC root** mới là bằng chứng giá trị; chỉ thấy object trong heap không tự chứng minh leak nếu GC chưa xảy ra.

### 13.3 Tránh kiểm thử phụ thuộc System.gc

Có thể dùng WeakReference<ClassLoader> trong thí nghiệm chẩn đoán, nhưng không kết luận chắc chắn loader phải biến mất sau **System.gc()**. GC có thể bị trì hoãn/tắt theo tùy chọn, class unloading không nhất thiết xảy ra ngay, stack local variables/debugger cũng có thể giữ reference.

Ba ví dụ Java ở trên cố ý kiểm tra các giá trị **TCCL==plugin**, **restore==host**, **thread inheritance**, không đòi GC xảy ra đúng thời điểm.

### 13.4 Đo qua nhiều vòng redeploy

1. Ghi số loader/classes/metaspace sau warm-up.
2. Deploy plugin và chạy workload đại diện.
3. Unload bằng cùng quy trình, không bỏ qua timeout.
4. Lặp nhiều vòng, so sánh các plugin loader cũ còn reachable.
5. Khi số lượng loader cũ tăng bất thường, lấy heap dump và tìm Path to GC Roots.
6. Đối chiếu source task/callback để xác định chỗ đặt TCCL mà không restore hoặc chỗ giữ strong reference.

Không kết luận có leak chỉ vì sau deploy lượng metaspace cao hơn ngay trước khi GC có cơ hội hoạt động.

## 14. Những hiểu nhầm thường gặp

- **“Plugin stop rồi, class chắc chắn unload.”** Sai: class unloading phụ thuộc reachability của defining loader và quyết định của JVM.
- **“TCCL chỉ là tên loader dạng String.”** Sai: nó là tham chiếu tới đối tượng ClassLoader.
- **“Thread pool tự bỏ worker sau mỗi task.”** Sai: worker thường được tái sử dụng.
- **“Restore context về null luôn đúng.”** Sai: phải phục hồi previous context, kể cả previous có thể null.
- **“Restore parent TCCL cũng restore tất cả child.”** Sai: child có context riêng sau khi được tạo.
- **“Pool tạo sớm thì không thể kế thừa plugin loader.”** Không bảo đảm worker cũng được tạo sớm.
- **“Cleanup TCCL cũng cleanup ThreadLocal.”** Sai: hai cơ chế khác nhau.
- **“Thread daemon không giữ objects.”** Sai: khi JVM còn sống, daemon thread vẫn có thể giữ references.
- **“Đã interrupt worker thì nó chắc chắn kết thúc.”** Sai: task phải hợp tác.
- **“URLClassLoader.close tự giải phóng tất cả class.”** Sai: nó không xóa references từ host.
- **“System.gc chưa unload = chắc chắn leak.”** Không đủ chứng cứ; cần heap path và đo theo thời gian.

## 15. Tự kiểm tra kiến thức

**Câu 1.** Host worker sống lâu giữ TCCL = PluginLoaderV1 sau plugin stop. Vì sao loader có thể chưa collectible?

**Đáp án:** Thread.contextClassLoader còn strong reference tới PluginLoaderV1 từ một live thread.

**Câu 2.** Vì sao dùng try/finally thay vì setContextClassLoader(plugin), gọi task rồi reset sau đó?

**Đáp án:** Task có thể ném exception/return sớm; finally phục hồi previous trong các đường thực thi phù hợp.

**Câu 3.** Main có plugin TCCL lúc new Thread, sau đó main restore trước child.start. Child còn có thể mang plugin loader không?

**Đáp án:** Có, vì Thread mới thường kế thừa context tại lúc tạo Thread.

**Câu 4.** Host Future giữ Runnable capture plugin object, nhưng TCCL đã restore. Leak vẫn có thể xảy ra?

**Đáp án:** Có, Runnable/Future là đường giữ riêng; cần dọn queue/registrations/host references.

**Câu 5.** ThreadLocalMap dùng weak key thì value plugin tự biến mất khi key không được giữ?

**Đáp án:** Không có bảo đảm lập tức; value có thể còn trong long-lived thread, cần remove trong finally.

**Câu 6.** Vì sao classloader.close không đủ để chứng minh class unloaded?

**Đáp án:** Close dọn resources/handles chứ không xóa mọi reference và không ép GC.

**Câu 7.** Tool nào cho biết ai đang giữ plugin loader cũ?

**Đáp án:** Heap dump với Path to GC Roots/dominator tree; JFR, jcmd, thread dumps và metrics hỗ trợ chẩn đoán.

**Câu 8.** Plugin owns ScheduledExecutorService. Bước cleanup cần gì?

**Đáp án:** Hủy scheduled tasks, shutdown và chờ kết thúc theo timeout, dọn callbacks, TCCL/ThreadLocal và references.

**Câu 9.** Nếu chỉ cần load provider và API nhận loader tường minh, có phải luôn đổi TCCL không?

**Đáp án:** Không. Truyền loader tường minh thường tránh thay state dùng chung khi phù hợp.

**Câu 10.** Sau khi dọn mọi strong references, JVM phải unload ngay không?

**Đáp án:** Không. Đủ điều kiện để thu hồi không đồng nghĩa chắc chắn thu hồi tức thời.

## 16. Ghi nhớ

~~~text
TCCL leak:
Long-lived host Thread
      -> contextClassLoader
      -> PluginLoader phiên bản cũ
      -> class metadata/objects được giữ

Phòng tránh:
Save previous TCCL
      -> set plugin TCCL trong scope ngắn
      -> invoke plugin
      -> finally restore previous
      -> cleanup ThreadLocal, callbacks, queued tasks,
         plugin threads/executors và host references
~~~

**Một thread sống lâu có thể giữ toàn bộ vòng đời ClassLoader của plugin cũ chỉ vì quên phục hồi TCCL.** Nhưng sửa TCCL chỉ giải quyết một đường retention; unload đáng tin cần quản lý đầy đủ workers, tasks, registries, resources và kiểm chứng GC roots qua nhiều vòng redeploy.

### Tài liệu tham khảo

- Thread API Java SE 17: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
- ClassLoader API Java SE 17: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- ExecutorService API Java SE 17: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- ServiceLoader API Java SE 17: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- JLS §12.7 Unloading of Classes and Interfaces: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7
- IBM — Class loader memory leaks in enterprise Java: https://www.ibm.com/docs/en/was-nd/8.5.5?topic=cmlp-memory-leaks-in-java-platform-enterprise-edition-applications
