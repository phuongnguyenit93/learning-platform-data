# Truyền và kế thừa context class loader khi tạo luồng

> **Java Core → ClassLoader → Loader ngữ cảnh.** Bài học giải thích cách **thread context class loader (TCCL)** được thừa hưởng khi tạo thread, cách đặt và khôi phục loader, sự khác biệt giữa tạo thread mới và chạy task trong thread pool, và những lưu ý với virtual threads. Các ví dụ độc lập dùng Java 17+; phần virtual threads yêu cầu Java 21+.

## 1. Context class loader là gì?

Mỗi đối tượng `Thread` có một **context class loader** có thể đọc và cập nhật:

~~~java
Thread thread = Thread.currentThread();
ClassLoader context = thread.getContextClassLoader();
thread.setContextClassLoader(context);
~~~

Mục đích thường gặp: mã thư viện/framework nạp bởi loader tầng cha có thể dùng loader ngữ cảnh để tìm classes, resources hoặc service providers thuộc ứng dụng/plugin đang gọi nó. Đây là cách **đảo chiều hướng tìm kiếm** so với việc luôn chỉ dựa vào defining loader của chính thư viện.

Phân biệt ba khái niệm:

| Thuật ngữ | Nghĩa | Có tự động giống TCCL? |
| --- | --- | --- |
| **Defining class loader** | Loader trực tiếp định nghĩa runtime class; một thành phần của class identity | Không |
| **Initiating class loader** | Loader mà JVM ghi nhận đã khởi xướng load thành công class, có thể qua delegation | Không |
| **Thread context class loader (TCCL)** | Một tham chiếu `ClassLoader` gắn với từng `Thread` để code lựa chọn dùng khi tìm class/resource | Không |

`Thread.currentThread().getContextClassLoader()` không nhất thiết bằng `SomeLibrary.class.getClassLoader()`, `ClassLoader.getSystemClassLoader()` hoặc loader đã tạo `Runnable`. Giá trị `null` ở API này có ý nghĩa fallback tới system class loader (hoặc bootstrap loader nếu không có system loader) theo tài liệu `Thread`; đừng tùy tiện suy ra `null` nghĩa là lỗi.

**Quan trọng:** TCCL **không chuyển** class sang defining loader mới. Nó chỉ là tham chiếu mà những API chủ động dùng TCCL có thể truy vấn. `SomeClass.class` và method bytecode resolution không đổi loader chỉ vì bạn set TCCL.

## 2. Quy tắc mặc định: kế thừa tại thời điểm **tạo Thread**

Với các public `Thread` constructors thông thường, **thread mới kế thừa context class loader từ thread đang tạo nó**. Đây là một trường hợp đặc biệt của cơ chế thừa hưởng initial values của inheritable-thread-locals được tài liệu `Thread` mô tả.

~~~text
Thread A đang chạy
    TCCL = loaderA
          |
          | new Thread(task)  <-- lấy trạng thái tại thời điểm tạo
          v
Thread B được tạo
    TCCL ban đầu = loaderA
          |
          | B.start()          <-- chỉ lập lịch thực thi; không lấy lại TCCL
          v
Thread B chạy task dưới TCCL ban đầu
~~~

Từ khóa chính là **khi `new Thread(...)` xảy ra**, không phải khi `start()` được gọi hoặc khi scheduler thật sự cho thread chạy.

Nếu thread A đổi TCCL **sau** khi tạo B nhưng **trước** khi start B, B không tự thay đổi theo A. Nếu sau này A đổi nữa thì B cũng không tự cập nhật. Các thread lưu tham chiếu TCCL riêng, không chia sẻ một biến TCCL duy nhất.

### 2.1. Ví dụ kiểm chứng creation-time inheritance, Java 17+

Tệp **TcclAtCreation.java**:

~~~java
public class TcclAtCreation {
    public static void main(String[] args)
            throws InterruptedException {
        Thread parent = Thread.currentThread();
        ClassLoader original = parent.getContextClassLoader();
        ClassLoader marker = new ClassLoader(original) { };

        try {
            parent.setContextClassLoader(marker);
            Thread child = new Thread(() -> {
                System.out.println("child inherited marker="
                    + (Thread.currentThread()
                        .getContextClassLoader() == marker));
            });

            // Thay đổi ở thread cha SAU khi child đã được tạo.
            parent.setContextClassLoader(original);
            System.out.println("parent restored="
                + (parent.getContextClassLoader() == original));

            child.start();
            child.join();
        } finally {
            parent.setContextClassLoader(original);
        }
    }
}
~~~

~~~bash
javac --release 17 TcclAtCreation.java
java -cp . TcclAtCreation
~~~

Stdout:

~~~text
parent restored=true
child inherited marker=true
~~~

Giải thích: việc tạo `child` dưới TCCL `marker` đã chụp giá trị này vào initial context của child. Khôi phục loader của parent trước `start()` không đổi TCCL đã có của child. `join()` làm chương trình chờ child hoàn tất nên output có thứ tự ổn định.

`new ClassLoader(original) { }` chỉ tạo loader **làm marker** để so sánh identity; nó không thực sự nạp class từ plugin JAR. Không nên nhầm minh họa truyền loader reference với một thử nghiệm định nghĩa class mới.

### 2.2. Gán TCCL tường minh cho thread đích

Thay vì dựa vào thời điểm tạo, bạn có thể set trên đối tượng thread mới trước khi start:

~~~java
Thread worker = new Thread(task);
worker.setContextClassLoader(pluginLoader);
worker.start();
~~~

Đây là snippet cần biến `task` và `pluginLoader` ở scope phù hợp. Nó mô tả một **policy rõ ràng hơn** cho ứng dụng cần loader nhất quán. Nếu worker đã chạy, thay TCCL giữa chừng có thể gây race về lúc thư viện bên trong gọi `getContextClassLoader()`; cấu hình trước `start()` thường dễ kiểm soát hơn.

### 2.3. Khác với `ThreadLocal` thường

- `ThreadLocal<T>` thông thường giữ giá trị riêng mỗi thread và **không mặc định truyền** sang child.
- `InheritableThreadLocal<T>` sao chép/tạo initial child values tại **thread construction**, không truyền động mọi cập nhật về sau.
- **TCCL** được `Thread` xử lý như một special inheritable thread-local value; hiểu nguyên tắc thời điểm kế thừa giúp tránh nhầm với ThreadLocal bình thường.
- Kế thừa TCCL **không đồng nghĩa sao chép toàn bộ trạng thái của classloader**. Hai threads có thể giữ cùng một tham chiếu loader, dùng chung classes đã được loader định nghĩa.

**Chú ý:** ClassLoader là object reference; “truyền” TCCL không clone bytecode, không tạo loader mới và không thay quyền truy cập Java module.

## 3. Trong trường hợp nào TCCL được sử dụng?

Nhiều thư viện sử dụng TCCL có chủ đích để tìm resources/SPI/providers. Ví dụ:

~~~java
ClassLoader loader =
        Thread.currentThread().getContextClassLoader();

Class<?> providerClass =
        loader.loadClass("example.plugin.Provider");
~~~

Đây là **snippet**, sẽ ném `NullPointerException` nếu `loader` thực sự null và gọi instance method trực tiếp; ứng dụng cần quyết định fallback trước khi sử dụng. Binary name là tên minh họa, không có sẵn class trong Java SE.

### 3.1. `ServiceLoader`

API `ServiceLoader.load(Service.class)` trong ngữ cảnh thông thường sử dụng **TCCL của thread hiện tại** làm class loader tìm providers. API overload như `ServiceLoader.load(Service.class, explicitLoader)` cho phép chủ động chọn loader, và JPMS còn có `ServiceLoader.load(layer, Service.class)` khi làm việc với module layer.

Nếu host và plugin có hai loaders:

- Contract/interface `Service` nên được chia sẻ bằng **cùng runtime class identity**; nếu mỗi loader tự define tên interface giống nhau, provider có thể bị từ chối vì type mismatch.
- TCCL có thể giúp thư viện tầng cha truy tìm plugin implementation theo caller context.
- Việc đưa provider vào JAR hoặc cấu hình `META-INF/services`/module `provides` phải đúng; TCCL không làm provider thiếu xuất hiện.
- Nếu một thread trong pool giữ TCCL của plugin A khi xử lý request plugin B, provider discovery có thể nhìn nhầm plugin.

### 3.2. Resource lookup

~~~java
ClassLoader tccl =
        Thread.currentThread().getContextClassLoader();
var url = tccl == null
        ? ClassLoader.getSystemResource("config/app.properties")
        : tccl.getResource("config/app.properties");
~~~

Đây là snippet minh họa, không phải tệp Java độc lập. `getResource` dùng logical resource name thường có dấu phân cách `/`. Resource trong named modules còn chịu module encapsulation; việc TCCL có thể nhìn class không đảm bảo mọi resource đều accessible. Một resource trả về `null` có thể do không tồn tại hoặc quyền module/loader, không nhất thiết do sai path vật lý.

### 3.3. Không nhầm TCCL với Java module access

Đổi TCCL **không tự cấp** `requires`/`exports`/`opens` cho named module. Class có thể được tìm bởi một loader nhưng caller vẫn bị giới hạn bởi accessibility rules hoặc class identity constraints. Với plugin isolation, phải thiết kế đồng thời loader boundary, module graph và shared API.

## 4. Thread pool: task mới không đồng nghĩa thread mới
Executor thường tái sử dụng worker có từ trước. Nếu caller đổi TCCL sang plugin A rồi submit task, worker có thể vẫn giữ context cũ (base hoặc plugin B). `submit()` không có hợp đồng chụp lại TCCL ở mỗi tác vụ; dù worker được tạo khi caller giữ plugin A, nó cũng có thể tiếp tục giữ A ở các tác vụ đến sau.

```text
creator TCCL=A → new Thread(worker) → worker ban đầu có TCCL=A
creator đổi TCCL=B → executor.submit(job) → worker vẫn có thể giữ A
```

Thay TCCL của worker mà quên restore còn gây nhiễm context giữa các tasks và kéo dài reference tới plugin. Muốn thực sự truyền context, capture loader ở boundary submit theo ownership của tác vụ, rồi áp dụng bên trong worker với wrapper ở phần 5; hoặc dùng API nhận `ClassLoader` tường minh. Bài “Thread pool và ngữ cảnh có thể khác luồng gửi công việc” có chương trình Java 17 kiểm chứng plain/wrapped/restored tasks.
## 5. Cách truyền TCCL vào task và khôi phục an toàn

Khi công việc phải chạy qua executor có worker được tái sử dụng, hãy **capture desired loader lúc submit** và thực thi task dưới loader đó với wrapper. Ví dụ một helper chuẩn cho Java 17+:

~~~java
import java.util.concurrent.Callable;

public final class ContextTasks {
    private ContextTasks() {}

    public static <T> Callable<T> withLoader(
            ClassLoader desired, Callable<T> operation) {
        return () -> {
            Thread current = Thread.currentThread();
            ClassLoader previous = current.getContextClassLoader();
            try {
                current.setContextClassLoader(desired);
                return operation.call();
            } finally {
                current.setContextClassLoader(previous);
            }
        };
    }
}
~~~

Tệp `ContextTasks.java` độc lập biên dịch được. Sử dụng từ code ứng dụng đã có `ExecutorService executor`:

~~~java
ClassLoader desired = Thread.currentThread().getContextClassLoader();

var result = executor.submit(ContextTasks.withLoader(desired, () -> {
    ClassLoader actual = Thread.currentThread().getContextClassLoader();
    return actual == desired;
}));
System.out.println(result.get());
~~~

Đây là **snippet caller**, yêu cầu biến `executor` và handling `Exception` phù hợp. Khi task được thực thi, wrapper set TCCL rồi luôn restore loader cũ trong `finally`. Kể cả `operation.call()` ném exception, worker không bị bỏ lại với desired context.

### 5.1. Biến thể `Runnable`

~~~java
static Runnable withLoader(ClassLoader desired, Runnable operation) {
    return () -> {
        Thread worker = Thread.currentThread();
        ClassLoader old = worker.getContextClassLoader();
        try {
            worker.setContextClassLoader(desired);
            operation.run();
        } finally {
            worker.setContextClassLoader(old);
        }
    };
}
~~~

Đây là **method minh họa** cần đặt trong class phù hợp. Tạo wrapper tại nơi nhận task/boundary của framework để policy nhất quán. Nếu hệ thống có context propagation API đã được framework hỗ trợ, ưu tiên dùng cơ chế chung ấy để tránh bỏ sót nested tasks và context khác như tracing, tenant, security.

**Tránh capture nhầm loader:** `getContextClassLoader()` tại submitter có thể đã bị một tác vụ khác làm bẩn. Trong hệ plugin, xác định loader từ **chủ sở hữu plugin/request** rõ ràng và restore cả caller nếu chính caller cũng đã thay đổi.

### 5.2. ThreadFactory cố định TCCL cho workers

Nếu mọi task trong một pool đều thuộc **một plugin**, có thể chọn TCCL của worker ngay trong ThreadFactory:

~~~java
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadFactory;

class PluginFactoryExample {
    static ThreadFactory factory(ClassLoader pluginLoader) {
        ThreadFactory base = Executors.defaultThreadFactory();
        return command -> {
            Thread thread = base.newThread(command);
            thread.setContextClassLoader(pluginLoader);
            return thread;
        };
    }
}
~~~

Snippet là class Java độc lập để tạo factory; không có `main`. Có thể dùng `Executors.newFixedThreadPool(2, factory(pluginLoader))` khi loader sống cùng pool. Nhưng với pool dùng chung nhiều plugins, **không gắn cố định loader của một plugin cho tất cả tasks**; dùng wrapper có restore per-task hoặc thiết kế pool phân vùng rõ.

Khi dừng plugin cần shutdown pool/worker, hủy callbacks và clear references; một active worker có TCCL trỏ tới pluginLoader có thể giữ plugin cũ trong bộ nhớ.

## 6. Virtual threads (JDK 21+) và inheritance

Từ Java 21, virtual threads được hỗ trợ chính thức. `Thread.ofVirtual()`/`Thread.ofPlatform()` builder có method:

~~~java
inheritInheritableThreadLocals(boolean inherit)
~~~

Theo API, default thường là **inherit=true**, và TCCL là một trong các inherited context values ở **thread creation time**. Có thể tắt inheritance rõ ràng:

~~~java
Thread child = Thread.ofVirtual()
    .inheritInheritableThreadLocals(false)
    .unstarted(task);
~~~

Đây là snippet cần biến `task`. Khi chọn false, đừng dựa vào việc TCCL sẽ tự bằng loader của parent; nếu cần policy xác định, set TCCL hoặc bọc task một cách rõ ràng.

### 6.1. Ví dụ virtual thread kế thừa TCCL (Java 21+)

Tệp **VirtualTccl.java**:

~~~java
public class VirtualTccl {
    public static void main(String[] args) throws InterruptedException {
        Thread creator = Thread.currentThread();
        ClassLoader saved = creator.getContextClassLoader();
        ClassLoader marker = new ClassLoader(saved) { };

        try {
            creator.setContextClassLoader(marker);
            Thread child = Thread.ofVirtual().unstarted(() ->
                System.out.println("virtualInherited=" +
                    (Thread.currentThread()
                        .getContextClassLoader() == marker)));

            creator.setContextClassLoader(saved);
            child.start();
            child.join();
        } finally {
            creator.setContextClassLoader(saved);
        }
    }
}
~~~

~~~bash
javac --release 21 VirtualTccl.java
java -cp . VirtualTccl
~~~

Stdout:

~~~text
virtualInherited=true
~~~

Tương tự platform thread, virtual thread **không lấy TCCL từ carrier thread** mỗi khi được scheduler gắn lên một carrier. `Thread.currentThread()` trong task trả về virtual thread, nên TCCL thuộc virtual thread. Nếu carrier đổi/virtual thread unmount rồi remount, context class loader của virtual thread không vì thế biến thành TCCL của carrier.

Với task chạy qua `Executors.newVirtualThreadPerTaskExecutor()`, mỗi task có một virtual thread mới, nhưng vẫn nên rõ chính sách inheritance/capture. Virtual threads giúp tránh reuse cùng thread giữa các tasks, không loại bỏ toàn bộ rủi ro giữ loader khi task sống quá lâu hoặc khi các async boundaries khác dùng pools.

## 7. Khi nào không nên mặc định kế thừa?

Trong một số hệ thống multi-tenant, plugin sandbox, extension runtime hoặc long-lived background jobs, kế thừa TCCL từ creator có thể không phù hợp vì:

- Creator có thể đang xử lý một plugin cụ thể trong khi background thread dự kiến phục vụ toàn hệ thống.
- Không muốn worker giữ strong reference đến plugin loader sau plugin unload.
- Muốn worker chỉ thấy host/shared APIs hoặc module layer cụ thể.
- Cần tránh “context tràn” giữa requests ở pools và async pipelines.

Cách xử lý tùy thiết kế:

1. Khi tạo worker, set TCCL tường minh trong ThreadFactory; dùng **host loader** nếu worker thuộc host.
2. Khi chạy callback/plugin operation, bọc theo desired loader và restore trong `finally`.
3. Với Thread.Builder của JDK phù hợp, cân nhắc `inheritInheritableThreadLocals(false)` rồi set TCCL theo policy đã định.
4. Đừng truyền `ClassLoader` chỉ để dùng như cơ chế phân quyền bảo mật: TCCL không thay Java access checks, module rules hoặc isolation được kiểm chứng.
5. Khi unload plugin, shutdown workers, gỡ callbacks/listeners, release caches và tham chiếu class/loader; theo dõi thread dumps nếu loader còn bị giữ.

**Đặc biệt:** `setContextClassLoader(null)` có ý nghĩa API rõ ràng (system loader hoặc fallback), không bảo đảm mọi thư viện dùng null đúng như nhau khi nó tự gọi `getContextClassLoader().loadClass(...)`; thư viện cần xử lý null một cách có chủ đích.

## 8. Lỗi thường gặp và cách chẩn đoán

| Biểu hiện | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| Child thread thấy loader cũ dù parent đổi trước start | Inheritance xảy ra ở construction | Set TCCL trước `new Thread` hoặc set trên child |
| Task executor không thấy loader của submitter | Worker được tạo trước hoặc được tái sử dụng | Wrap task hoặc ThreadFactory policy |
| Task B tìm provider của plugin A | Task A bỏ quên restore | `try/finally` trong mọi context switch |
| Plugin hot reload không unload class metadata | Worker/ThreadLocal/TCCL giữ loader cũ | Shutdown worker và dọn references |
| `ClassNotFoundException` ở ServiceLoader/resource lookup | TCCL sai hoặc service config thiếu | Xác nhận TCCL, SPI metadata, module layer |
| Cast lỗi dù class cùng tên | Hai defining loaders khác nhau | Kiểm tra class identity; chia sẻ host interface |
| Set TCCL xong named module vẫn bị chặn access | TCCL không sửa readability/exports/opens | Kiểm tra JPMS graph |
| Virtual thread có TCCL khác dự kiến | Builder inheritance setting hoặc capture timing | Kiểm tra builder/factory và set explicit |

### Cách log tối thiểu

~~~java
Thread current = Thread.currentThread();
ClassLoader tccl = current.getContextClassLoader();

System.out.println("thread=" + current.getName());
System.out.println("TCCL=" + tccl);
System.out.println("definingLoader="
    + getClass().getClassLoader());
~~~

Đây là **snippet trong instance method**; khi dùng trong static context thay `getClass()` bằng một class literal phù hợp. `ClassLoader.toString()` là diagnostic, không phải stable ID hay bằng chứng hai loaders nạp cùng bytecode. Khi cần, kiểm tra thêm `clazz.getModule()`, runtime jar/version và context propagation boundaries.

## 9. Câu hỏi tự kiểm tra

1. TCCL của child `new Thread(...)` được lấy lúc nào? **Khi tạo Thread object**, trước `start()`.
2. Parent đổi TCCL sau khi tạo child, child có tự đổi không? **Không**.
3. TCCL và defining loader của class luôn giống nhau? **Không**.
4. Executor tái sử dụng worker có tự nhận TCCL của caller ở mỗi `submit`? **Không**.
5. Vì sao `finally` bắt buộc khi wrapper task đổi TCCL? **Để worker không giữ context của task trước khi có exception**.
6. TCCL được kế thừa giống mọi ThreadLocal bình thường? **Không**, nó được mô tả như special inheritable thread-local.
7. Một thread không có TCCL và trả về null có nghĩa classloading bất khả thi? **Không**, API có fallback rule.
8. Set TCCL có cho module A đọc package chưa export của B không? **Không**.
9. Virtual thread lấy TCCL theo carrier mỗi lần schedule? **Không**, TCCL thuộc virtual Thread object.
10. Muốn thread không kế thừa inherited context theo JDK 21 builder, dùng gì? **`inheritInheritableThreadLocals(false)`**.
11. Hot-reload plugin không unload dù đã đóng URLClassLoader: vì sao? **Có thể thread/pool giữ strong reference qua TCCL**.
12. Nên lưu plugin interface ở loader nào khi dùng ServiceLoader xuyên host/plugin? **Ở defining loader chung để tránh hai runtime types cùng tên**.

## 10. Nguồn tham khảo chuẩn

1. [Thread — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html): `getContextClassLoader`, `setContextClassLoader` và quy tắc inheritance at thread creation.
2. [Thread.Builder — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.Builder.html): `inheritInheritableThreadLocals`, platform/virtual thread builders.
3. [InheritableThreadLocal — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/InheritableThreadLocal.html): giá trị initial được kế thừa.
4. [Executors — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Executors.html): thread pools, ThreadFactory, virtual thread-per-task.
5. [ServiceLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ServiceLoader.html): lựa chọn loader/provider discovery.
6. [ClassLoader — Java SE 25 API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/ClassLoader.html): defining loader, resource lookup, delegation và module encapsulation.

**Ghi nhớ:** `new Thread` thường kế thừa TCCL **tại thời điểm tạo**, thread pools tái sử dụng context của **worker**, và virtual threads tuân theo chính sách inheritance của builder/factory. Với async code và plugin systems, xác định desired loader, truyền vào execution boundary rồi luôn **restore trong `finally`**.
