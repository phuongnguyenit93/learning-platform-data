# Thread pool và ngữ cảnh có thể khác luồng gửi công việc

Khi ứng dụng Java đưa công việc từ một thread sang `ExecutorService` hoặc thread pool, **thread thực sự thực thi công việc có thể có context class loader (TCCL) khác thread gửi công việc**. Lệnh `submit()` không có hợp đồng tự động chuyển `Thread.currentThread().getContextClassLoader()` từ bên gửi sang worker trong mỗi lần gọi. Worker có thể được tạo từ trước, tồn tại lâu và thực hiện nhiều tác vụ của những thành phần khác nhau.

Điểm này ảnh hưởng các thư viện tìm class, resource hoặc provider dựa trên TCCL: chương trình có thể hoạt động khi gọi trực tiếp nhưng mất provider khi chạy nền; một worker giữ TCCL của plugin cũ cũng có thể gây rò rỉ class loader sau hot redeploy. Bài học giải thích cơ chế, trình bày ví dụ Java 17 chạy độc lập và cách **capture → set → execute → restore** an toàn.

## 1. TCCL là gì?

Mỗi `Thread` có một **thread context class loader**. Hai API quan trọng:

~~~java
ClassLoader current =
        Thread.currentThread().getContextClassLoader();

Thread.currentThread().setContextClassLoader(current);
~~~

Đây là **fragment minh họa**; nó đọc rồi đặt lại cùng giá trị nên không làm thay đổi hành vi. TCCL có thể bằng `null` và không phải mọi API đều sử dụng nó.

TCCL thường giúp code thư viện tìm implementation do ứng dụng hoặc plugin cung cấp. Một số tình huống:

- `ServiceLoader.load(MyService.class)` thường dùng TCCL hiện tại để khám phá service provider theo quy tắc API.
- Framework đọc `META-INF/services/...`, resource hoặc cấu hình thông qua `Thread.currentThread().getContextClassLoader().getResource(...)`.
- Application server đặt TCCL phù hợp trước khi gọi code của web application hoặc plugin.

**Phân biệt TCCL với defining loader.** `SomeClass.class.getClassLoader()` cho biết class loader **đã định nghĩa** `SomeClass`; thay TCCL không làm class này đổi defining loader hay sửa `ClassCastException` giữa hai định nghĩa kiểu cùng tên.

| Tình huống | Class loader nào được sử dụng? |
| --- | --- |
| `ServiceLoader.load(Service.class)` | Mặc định dựa vào TCCL của thread gọi. |
| `ServiceLoader.load(Service.class, chosenLoader)` | Dùng loader truyền tường minh, trong khuôn khổ quy tắc module/provider. |
| `Class.forName(name, true, chosenLoader)` | Dùng loader được truyền vào. |
| `Class.forName(name)` | Dùng cơ chế của caller, không mặc định chuyển sang TCCL. |
| `MyClass.class` | Tham chiếu kiểu được JVM liên kết, không tự đổi theo TCCL. |
| `ClassLoader.getSystemClassLoader()` | System/application class loader, không nhất thiết là TCCL. |

Muốn hiểu vì sao thread pool làm khác kết quả, cần xác định code bên trong task **thực sự đang dùng API tra cứu nào**.

## 2. Thời điểm kế thừa context loader

Khi tạo một `Thread` mới trong điều kiện thông thường, TCCL ban đầu được **kế thừa từ thread tạo nó**, trừ khi ứng dụng, `ThreadFactory` hoặc môi trường thay đổi tường minh. Việc kế thừa diễn ra khi **tạo thread**, không phải khi chạy từng `Runnable` hoặc nhận từng `Callable`.

~~~text
Submitter S                    Worker W trong thread pool
TCCL = PluginLoader              đã tạo trước đó
      |                           TCCL = BaseLoader
      |                                    |
      +-- executor.submit(job) ----------> |
                                           v
                                        job chạy
                                           |
                                           v
                                   TCCL = BaseLoader
                                     (khác submitter)
~~~

Tại thời điểm `submit`:

1. Executor nhận và lên lịch công việc. Nó có thể đặt task vào queue thay vì tạo thread.
2. Worker được chọn có thể đã chạy những task khác, hoặc được tạo bởi `ThreadFactory` trên một thread hoàn toàn khác.
3. Nếu task gọi `Thread.currentThread().getContextClassLoader()` thì giá trị là **TCCL hiện tại của worker**, không tự sao chép của submitter.
4. Nếu task thay TCCL của worker mà quên khôi phục, **task tiếp theo** có thể thấy loader không liên quan.
5. `Future.get()` chỉ đợi kết quả hoặc exception; nó không truyền TCCL từ thread gọi sang worker.

### Default thread factory có giải quyết không?

`new Thread(...)` và default `ThreadFactory` thường kế thừa TCCL **tại lúc tạo worker**. Pool có thể tạo worker khi nhận task đầu hoặc khi cần mở rộng, nhưng **không đảm bảo worker mới cho mỗi lần submit**. Nếu pool có một worker tạo lúc Thread A đang giữ PluginA, task của Thread B gửi sau này có thể tiếp tục thấy PluginA thay vì PluginB. Không nên dựa vào submitter đầu tiên, bởi pool có thể khởi tạo worker sớm, tái tạo worker hoặc dùng factory riêng.

## 3. Ví dụ Java 17 chạy được và có output xác định

Ví dụ tạo một `URLClassLoader` tượng trưng cho plugin và một executor một worker. `ThreadFactory` thiết lập TCCL **cố định là system class loader** cho worker, giúp chứng minh sự khác biệt mà không phụ thuộc thời điểm tạo thread.

Tạo tệp **`ThreadPoolContextDemo.java`**:

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;
import java.util.concurrent.TimeUnit;

public class ThreadPoolContextDemo {
    private static <T> Callable<T> withContextLoader(
            ClassLoader desired, Callable<T> action) {

        return () -> {
            Thread worker = Thread.currentThread();
            ClassLoader previous = worker.getContextClassLoader();
            worker.setContextClassLoader(desired);

            try {
                return action.call();
            } finally {
                worker.setContextClassLoader(previous);
            }
        };
    }

    public static void main(String[] args) throws Exception {
        ClassLoader baseLoader = ClassLoader.getSystemClassLoader();

        try (URLClassLoader pluginLoader =
                     new URLClassLoader(new URL[0], baseLoader)) {

            ThreadFactory factory = job -> {
                Thread worker = new Thread(job, "context-worker");
                worker.setContextClassLoader(baseLoader);
                return worker;
            };

            ExecutorService pool =
                    Executors.newSingleThreadExecutor(factory);

            Thread submitter = Thread.currentThread();
            ClassLoader previousSubmitterLoader =
                    submitter.getContextClassLoader();

            try {
                submitter.setContextClassLoader(pluginLoader);

                System.out.println("Submitter uses plugin: "
                        + (submitter.getContextClassLoader() == pluginLoader));

                boolean plain = pool.submit(() ->
                        Thread.currentThread().getContextClassLoader()
                                == pluginLoader).get();
                System.out.println("Plain task uses plugin: " + plain);

                boolean wrapped = pool.submit(
                        withContextLoader(pluginLoader, () ->
                                Thread.currentThread().getContextClassLoader()
                                        == pluginLoader)).get();
                System.out.println("Wrapped task uses plugin: " + wrapped);

                boolean restored = pool.submit(() ->
                        Thread.currentThread().getContextClassLoader()
                                == baseLoader).get();
                System.out.println("Worker restored base: " + restored);

            } finally {
                submitter.setContextClassLoader(previousSubmitterLoader);
                pool.shutdown();

                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                }
            }
        }
    }
}
~~~

Chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 ThreadPoolContextDemo.java
java ThreadPoolContextDemo
~~~

**Stdout chính xác:**

~~~text
Submitter uses plugin: true
Plain task uses plugin: false
Wrapped task uses plugin: true
Worker restored base: true
~~~

Giải thích từng kết quả:

1. `pluginLoader` và `baseLoader` là hai object khác nhau. `new URL[0]` có nghĩa ví dụ **không thực sự tải lớp của plugin**, mà chỉ kiểm tra TCCL identity một cách độc lập, dễ tái hiện.
2. Submitter set TCCL thành `pluginLoader`. Vì thế dòng đầu bằng `true`.
3. `ThreadFactory` tạo worker với TCCL cố định `baseLoader`; task gửi theo `submit` thông thường vẫn thấy base, nên dòng thứ hai bằng `false`.
4. `withContextLoader` lưu ngữ cảnh cũ của worker, tạm đặt ngữ cảnh plugin rồi chạy `action.call()`. Dòng thứ ba bằng `true`.
5. `finally` của wrapper khôi phục đúng TCCL cũ ngay cả khi action ném exception. Task tiếp theo thấy base và dòng cuối bằng `true`.
6. `finally` ở `main` khôi phục TCCL submitter, shutdown pool và đợi worker dừng. `try-with-resources` đóng tài nguyên `URLClassLoader`. Việc đóng loader **không ép JVM unload mọi class tức thì**.

**Ý nghĩa thực tế:** TCCL của worker có thể khác submitter ngay cả khi task do submitter đó gửi. Nếu một library gọi `ServiceLoader` hay tìm resource bằng TCCL bên trong worker, nó có thể nhận kết quả khác.

## 4. Pattern capture → set → execute → restore

Khi một task **cần TCCL của bên submit** theo thiết kế, capture ở boundary gửi việc:

~~~text
SUBMITTER
    captured = currentThread.getContextClassLoader()
    executor.submit(wrap(captured, task))

WORKER
    previous = currentThread.getContextClassLoader()
    currentThread.setContextClassLoader(captured)
    try:
        task.call()
    finally:
        currentThread.setContextClassLoader(previous)
~~~

Ở Java, có thể dùng chính hàm `withContextLoader` của ví dụ trước. Ví dụ fragment sau giả định đã có `ExecutorService executor` và `Callable<T> task` bên trong một method generic:

~~~java
ClassLoader captured =
        Thread.currentThread().getContextClassLoader();

Future<T> result = executor.submit(
        withContextLoader(captured, task));
~~~

Đây là **fragment**, cần khai báo/import `Future`, `T`, `task`, `executor` phù hợp. Điều quan trọng:

- **Capture tại thời điểm submit** nếu đó là ngữ cảnh cần chuyển, chứ không capture một lần khi tạo singleton pool.
- **Set trên worker khi task bắt đầu**, không chỉ set tại submitter trước khi `submit`.
- **Khôi phục đúng giá trị trước đó**, kể cả `null`, dùng `finally`. Không tự thay mọi loader cũ thành system loader.
- Dùng wrapper riêng cho `Runnable` nếu task không trả kết quả, giữ xử lý exception của executor.
- Không truyền TCCL bừa cho mọi task; tác vụ hệ thống chung đôi khi nên dùng base loader.
- Chuyển loader bằng đối số tường minh khi API hỗ trợ (`Class.forName(name, true, loader)`, `ServiceLoader.load(service, loader)`) thường ít trạng thái ẩn hơn.
- Captured loader là một **strong reference** trong task/queue. Khi plugin kết thúc vòng đời, cần hủy task tồn đọng và release các reference này.

Nếu wrapper chỉ restore TCCL nhưng task còn thay đổi `ThreadLocal`, logging MDC, security context hoặc transaction context, các trạng thái đó **không tự được dọn**. Chúng có cơ chế và lifecycle riêng.

## 5. Vì sao ServiceLoader và resource có thể cho kết quả khác?

Giả sử provider class và metadata `META-INF/services/com.acme.Service` chỉ nằm trong đường tìm kiếm của plugin loader. Khi gọi trực tiếp trên submitter (TCCL=plugin), discovery có thể tìm thấy provider; khi gọi trong worker (TCCL=base), provider có thể không được tìm thấy.

~~~text
Submitter TCCL=PluginLoader
  ServiceLoader.load(Service.class)
      └─ nhìn thấy provider của plugin

Worker TCCL=BaseLoader
  ServiceLoader.load(Service.class)
      └─ có thể không thấy provider plugin
~~~

Ví dụ Java dạng **fragment**, cần interface `MyService` và khai báo provider hợp lệ nên **chưa phải chương trình độc lập**:

~~~java
ServiceLoader<MyService> providers =
        ServiceLoader.load(MyService.class);

for (MyService provider : providers) {
    provider.execute();
}
~~~

Lời gọi dạng một tham số ở trên sử dụng TCCL theo quy tắc API. Có thể chọn overload rõ ràng để tránh phụ thuộc trạng thái worker:

~~~java
ServiceLoader<MyService> providers =
        ServiceLoader.load(MyService.class, pluginLoader);
~~~

Fragment này cần `pluginLoader` và các loại/import tương ứng. Dùng loader tường minh không bảo đảm provider hợp lệ nếu interface `MyService` đã bị host và plugin định nghĩa riêng: provider vẫn phải triển khai **đúng cùng định nghĩa interface** mà consumer yêu cầu. Module graph, visibility, `uses`/`provides` cũng có thể ảnh hưởng discovery trong JPMS.

Tương tự, các API có thể khác nhau:

| API trong worker | Có dùng TCCL không? |
| --- | --- |
| `Thread.currentThread().getContextClassLoader().getResource(name)` | Có, dùng loader của worker. |
| `ServiceLoader.load(Service.class)` | Thông thường dùng TCCL theo API. |
| `SomeClass.class.getResource("config.properties")` | Dựa trên class/package/module liên quan, **không mặc định chuyển qua TCCL**. |
| `Class.forName(name, true, loader)` | Dùng loader được truyền tường minh. |

Vì vậy, **resource trả `null` chưa chắc do thread pool**: có thể sai tên đường dẫn, module encapsulation, loader không nhìn thấy JAR, thiếu provider metadata hoặc code đang tra cứu bằng một API khác.

## 6. ThreadFactory, pool dùng chung và plugin-specific pool

Một `ThreadFactory` có thể tạo worker với TCCL mong muốn ngay từ đầu:

~~~java
ThreadFactory factory = job -> {
    Thread worker = new Thread(job, "plugin-worker");
    worker.setContextClassLoader(pluginLoader);
    return worker;
};
~~~

Đây là **fragment**, cần `pluginLoader` được khai báo ở nơi dùng. Nó hợp lý khi **pool chỉ thuộc một plugin** và có vòng đời tương ứng. Nhưng với pool **chia sẻ nhiều plugin**, một TCCL cố định là không đủ: task của plugin B có thể được xử lý bằng loader A. Khi đó wrapper per-task hoặc truyền class loader tường minh thường phù hợp hơn.

Còn một vấn đề: task có thể thay TCCL ngay trong lúc chạy. Nếu quên restore, chính worker vốn được tạo đúng bởi factory vẫn bị “bẩn” cho các task tiếp theo. Không nên cố thay TCCL của một worker đang chạy **từ thread khác**: việc thay đổi đồng thời có thể gây lỗi ngữ cảnh khó tái hiện. Đặt/khôi phục trong code được thực thi trên chính worker.

## 7. CompletableFuture và callback không nhất thiết chạy trên submitter

`CompletableFuture.supplyAsync(...)` hoặc `runAsync(...)` không truyền executor thường sử dụng `ForkJoinPool.commonPool()` khi thích hợp (có fallback phụ thuộc điều kiện), nên stage chạy trên thread do framework/pool quản lý.

~~~java
CompletableFuture<Result> future =
        CompletableFuture.supplyAsync(() -> queryProvider());
~~~

Đây là **fragment minh họa**: `Result` và `queryProvider()` chưa được khai báo. Không thể suy ra TCCL của stage từ thread tạo future.

Điểm cần lưu ý:

- `thenApply(...)` không phải async: action có thể chạy ở thread hoàn thành stage trước hoặc khi đăng ký vào stage đã hoàn tất.
- `thenApplyAsync(...)` lên lịch theo executor liên quan; TCCL là của thread thực hiện stage đó.
- Nhiều stage có thể chạy ở **nhiều thread khác nhau**. Nếu từng stage cần TCCL của plugin, phải đảm bảo context tại **mỗi boundary thực sự cần**.
- Scheduled executor, event loop hoặc background callback có cùng nguyên tắc: xác định **ai sở hữu thread**, thay vì giả định là thread đã gửi công việc.

Framework đôi khi có task decorator/context propagation. Cần đọc rõ tính năng đó có truyền **TCCL** hay chỉ MDC, security context, tracing context. Không được coi các ngữ cảnh trên là đồng nhất.

## 8. Rò rỉ class loader sau undeploy
Nếu worker sống lâu quên restore TCCL, nó giữ strong reference tới loader plugin cũ sau khi plugin dừng. Tương tự, task chờ trong queue hoặc `Future`/callback cũng có thể giữ loader qua closure. Điều này vừa gây provider lookup sai vừa làm class unloading bị trì hoãn.

```text
Host executor → live worker → contextClassLoader → old PluginLoader
```

Khi unload, chặn task mới, cho task hiện tại hoàn thành/hủy theo policy, restore TCCL trong `finally`, dọn queue/callback/`ThreadLocal`, và shutdown pool **nếu thuộc sở hữu plugin**. `URLClassLoader.close()` không tự giải phóng mọi class ngay. Bài “Rò rỉ bộ nhớ...” đi sâu GC roots, metaspace và cách đo qua nhiều vòng redeploy.
## 9. Những lỗi lập trình thường gặp

**Chỉ set TCCL tại submitter:**

~~~java
Thread.currentThread().setContextClassLoader(pluginLoader);
executor.submit(task);
~~~

Đây là **anti-pattern fragment**, chưa khôi phục TCCL và cũng không bảo đảm worker thấy plugin loader. Submitter có thể tự mang ngữ cảnh sai sau khi gọi.

**Set TCCL trong worker nhưng không restore:**

~~~java
executor.submit(() -> {
    Thread.currentThread().setContextClassLoader(pluginLoader);
    runPluginJob();
});
~~~

Đây cũng chỉ là **fragment minh họa lỗi**. Khi `runPluginJob()` trả về hoặc ném exception, worker có thể giữ loader ấy cho task sau.

**Nhầm `InheritableThreadLocal` với propagation theo task:** `InheritableThreadLocal` cũng chủ yếu truyền dữ liệu lúc tạo thread con. Nó không cập nhật giá trị mỗi lần thread pool nhận task. TCCL có cơ chế kế thừa riêng của `Thread` nhưng cũng không tự cập nhật khi submit.

**Nhầm lỗi SPI với lỗi loader duy nhất:** `ServiceConfigurationError` có thể do thiếu metadata, class/provider không nạp được, module access hoặc provider không triển khai đúng interface. TCCL đúng chưa chắc đủ.

**Quên dọn trạng thái ngoài TCCL:** `ThreadLocal`, MDC, transaction context hoặc những object ứng dụng không tự được restore bằng wrapper chỉ xử lý `ClassLoader`.

## 10. Quy trình debug

1. Ngay tại submitter, log `Thread.currentThread().getName()`, TCCL và class loader của kiểu dịch vụ cần dùng.
2. Ngay trong worker khi task chạy, log **chính các thông tin ấy** và so sánh; tránh log trước khi enqueue rồi suy luận thread trong pool tương tự.
3. Xem worker được tạo ở đâu và `ThreadFactory` có đặt TCCL không.
4. Kiểm tra task trước đó có `setContextClassLoader` mà thiếu `finally` không.
5. Với `ServiceLoader`, in provider thực tế hoặc lỗi discovery và xác minh interface do loader nào định nghĩa.
6. Với resource, kiểm tra URL từ `getResource()` qua đúng loader và đường dẫn, kể cả module access.
7. Dùng wrapper capture/set/restore hoặc truyền loader tường minh rồi xác minh **task sau wrapper đã thấy loader gốc**.
8. Với hot redeploy, kiểm tra queue và thread còn giữ class loader deployment cũ.

## 11. Tự kiểm tra kiến thức

**Câu 1.** Thread S có TCCL=PluginA, pool worker W đã có TCCL=Base từ trước. Sau `submit`, task thấy loader nào nếu không có propagation?

**Đáp án:** Nó thấy **Base**, tức TCCL hiện tại của W.

**Câu 2.** Worker được tạo lúc thread A giữ PluginA; hôm sau thread B giữ PluginB và submit task vào chính worker ấy. TCCL worker có tự thành PluginB?

**Đáp án:** Không. Kế thừa lúc tạo thread không phải cơ chế truyền dữ liệu ở mỗi submit.

**Câu 3.** Tại sao wrapper cần `finally`?

**Đáp án:** Để khôi phục TCCL trước đó khi task hoàn tất hoặc ném exception, tránh ảnh hưởng task khác và giữ loader cũ.

**Câu 4.** `ServiceLoader.load(Service.class)` có thể khác kết quả khi gọi trên submitter và worker?

**Đáp án:** Có, vì TCCL khác nhau có thể làm thay đổi provider được nhìn thấy.

**Câu 5.** `Class.forName(name, true, loader)` dùng TCCL ngầm không?

**Đáp án:** Không; overload này dùng `loader` truyền tường minh.

**Câu 6.** TCCL đúng nhưng vẫn gặp `ClassCastException` ở provider là vì sao?

**Đáp án:** Có thể do provider và consumer dùng hai định nghĩa interface giống tên nhưng khác defining loader; TCCL không tự hợp nhất kiểu.

## Ghi nhớ

**TCCL thuộc về thread thực thi, không tự động gắn với tác vụ khi `submit`.** Worker được tạo và tái sử dụng ở thời điểm khác submitter, nên có thể tìm class, resource và provider khác. Nếu thật sự cần ngữ cảnh của submitter, hãy **capture → set trên worker → execute → restore trong finally**, hoặc truyền `ClassLoader` tường minh khi API hỗ trợ. Cần quản lý queue/worker khi plugin dừng để tránh dùng sai loader và giữ deployment cũ.

**Tài liệu chính thức:**

- `Thread` (Java SE 17): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html
- `ClassLoader` (Java SE 17): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- `ExecutorService`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html
- `Executors` và `ThreadFactory`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html
- `ServiceLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- `CompletableFuture`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html
