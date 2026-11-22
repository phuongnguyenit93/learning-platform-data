# Nạp lười và tác động của preloading đến hiệu năng Java ClassLoader

## 1. Tổng quan: trả chi phí ở startup hay ở lần dùng đầu tiên?

Một ứng dụng Java thường không cần thực sự chạy tất cả chức năng ngay khi khởi động. Một phần class chỉ được sử dụng khi có request cụ thể, người dùng kích hoạt tính năng hoặc hệ thống phát hiện plugin. Vì vậy runtime có thể **trì hoãn việc nạp, liên kết hoặc khởi tạo** một số class cho tới thời điểm cần thiết. Ta thường gọi lối vận hành này là **nạp lười (lazy loading)** theo nghĩa kiến trúc.

Ngược lại, **preloading** là một chiến lược **chủ động thực hiện sớm một phần công việc** với class, resource hoặc framework components để hạn chế độ trễ khi tính năng lần đầu được truy cập.

~~~text
LAZY                                      EAGER / PRELOADING
Process start                             Process start
   |                                          |
   | nạp/khởi tạo các lớp cần thiết             | chủ động nạp/khởi tạo thêm các lớp
   v                                          | dựng cache, chuẩn bị framework...
Server ready                                  v
   |                                      Server ready
   | first request                            |
   | nạp/link/init thêm class?                 | first request
   v                                          | ít việc còn phải làm hơn?
Response                                     v
                                          Response
~~~

Sự đánh đổi thường thấy:

- **Nạp lười:** có thể rút ngắn thời gian đến khi ứng dụng sẵn sàng và giảm số class thực sự phải xử lý nếu một tính năng hiếm khi dùng; nhưng request đầu tiên tới tính năng ấy có thể trả thêm chi phí.
- **Preloading:** có thể dịch chi phí vào startup hoặc giai đoạn warm-up, giúp giảm độ trễ ở lần sử dụng đầu tiên; đổi lại startup lâu hơn, có thể tăng bộ nhớ/resident metadata và gây thêm I/O/CPU hoặc tác dụng phụ của static initialization.

**Không có quy tắc “preload luôn nhanh hơn”**. Hiệu quả phụ thuộc tập class, cách nạp, JIT, class data sharing, lưu trữ, concurrency, hot paths, chính sách triển khai và metric được tối ưu (startup, p99 latency, RAM, throughput hay thời gian cập nhật).

Điểm quan trọng nhất của bài: **loading, linking, initialization và “warming” là các công việc khác nhau.** Một lệnh chủ động “load class” không mặc nhiên thực hiện static initializer, không khởi tạo Spring bean và không buộc JIT biên dịch tất cả methods.

## 2. Ba giai đoạn thường bị gọi chung là “nạp lớp”

Để chọn đúng mức preload, tách ba mốc JVM (JLS/JVMS): **loading** tìm bytes và tạo runtime `Class<?>`; **linking** gồm verification, preparation và resolution (resolution có thể diễn ra muộn); **initialization** chạy static field expressions và `<clinit>` khi active use yêu cầu.

| Mục tiêu preload | Có thể đã xong | Vẫn có thể phát sinh ở first request |
| --- | --- | --- |
| `loadClass(name)` | Tra class/define khi cần, một phần linking | `<clinit>`, lazy resolution, tạo instance, I/O/JIT |
| `Class.forName(name, false, loader)` | Nạp/link class theo API nhưng chưa yêu cầu init | Static initializer, provider/discovery và business setup |
| `Class.forName(name, true, loader)` | Thêm yêu cầu initialization | Constructor, DI graph, resource access khác, first-use/JIT |

### 2.1. “Lazy” không phải một bảo đảm thời điểm tuyệt đối cho loading

JVM và framework có thể chủ động nạp/link một số classes trước code path mà ứng dụng tưởng là lần dùng đầu. **API `false` chỉ bảo đảm không chủ động initialize class đích**, không bảo đảm class chưa từng được nạp trước đó; cũng không ép toàn bộ symbolic references resolve. Phép so sánh lazy/preload phải dựa trên class-load/init evidence và workload thật, không dựa vào suy đoán thời điểm.

## 3. Các API Java 17+ và điều thực sự xảy ra

| Cách dùng | Loading/linking | Initialization của class đích |
| --- | --- | --- |
| `loader.loadClass("demo.Feature")` | Yêu cầu loader tìm/nạp class; parent delegation áp dụng | **Không tự yêu cầu** initialization |
| `Class.forName("demo.Feature", false, loader)` | Tìm/nạp/liên kết theo API và quy tắc VM | **Không yêu cầu** initialization |
| `Class.forName("demo.Feature", true, loader)` | Tìm/nạp/liên kết và yêu cầu initialization | **Có**, nếu cần |
| `Class.forName("demo.Feature")` | Dùng defining loader của caller theo API tương ứng; yêu cầu initialization | **Có**, nếu cần |
| `Feature.class` | Lấy Class literal, có thể kích hoạt công việc class-loading cần thiết | **Không tự làm** Feature initialized |
| `new Feature()` | Cần class được chuẩn bị | **Có**, trước khi tạo instance theo quy tắc |
| `Feature.runStatic()` | Thực hiện static method invocation | **Có**, nếu chưa initialized |
| `Feature.nonConstantStatic` | Truy cập static field không phải constant variable | **Có**, nếu chưa initialized |
| `Feature.COMPILE_TIME_CONSTANT` | Constant variable thường được inline vào caller | **Có thể không** làm declaring class initialized |

**Lưu ý:** `ClassLoader.loadClass(String, boolean resolve)` là protected overload; `resolve=true` nghĩa yêu cầu **linking thông qua resolveClass**, **không phải initialization**. Không tự equate “resolve class” với “chạy static initializer”.

Lệnh `Class.forName(name, false, loader)` thích hợp khi cần lấy `Class<?>` để xem metadata, giữ một handle hoặc kiểm tra class có thể tải, nhưng **không nên gọi đó là full application warm-up**.

## 4. Ví dụ chạy được: ba chế độ lazy, load và preload

Thí nghiệm dưới đây cố định thứ tự các thông báo để minh họa **thời điểm static initialization**. Nó không cố đo benchmark thời gian bằng số milliseconds giả định, vì thời gian thực tế thay đổi theo máy và JDK.

### 4.1. File LoadingDemo.java

~~~java
public class LoadingDemo {
    static final class Feature {
        static {
            System.out.println("Feature initialized");
        }

        static void serve() {
            System.out.println("Feature.serve");
        }
    }

    public static void main(String[] args) throws Exception {
        String mode = args.length == 0 ? "lazy" : args[0];
        ClassLoader loader = LoadingDemo.class.getClassLoader();
        String name = "LoadingDemo$Feature";

        switch (mode) {
            case "lazy" -> {
                // Không chủ động nạp hay khởi tạo Feature.
            }
            case "load" -> {
                loader.loadClass(name);
                System.out.println("Class loaded without initialization");
            }
            case "lookup" -> {
                Class.forName(name, false, loader);
                System.out.println("Class resolved without initialization");
            }
            case "preload" -> {
                Class.forName(name, true, loader);
                System.out.println("Preload completed");
            }
            default -> throw new IllegalArgumentException(mode);
        }

        System.out.println("Application ready");
        System.out.println("First request");
        Feature.serve();
        System.out.println("Request completed");
    }
}
~~~

Dùng **Java 17+**, trong một thư mục mới chứa `LoadingDemo.java`:

~~~bash
javac --release 17 -d out LoadingDemo.java
java -cp out LoadingDemo lazy
java -cp out LoadingDemo load
java -cp out LoadingDemo lookup
java -cp out LoadingDemo preload
~~~

**Chạy từng lệnh trong một JVM process mới**, bởi initialization của cùng một Class runtime xảy ra tối đa một lần trong vòng đời tương ứng. Nếu gọi lần thứ hai trong cùng JVM, sự khác biệt có thể biến mất vì class đã initialized.

### 4.2. Kết quả chính xác: lazy

~~~text
Application ready
First request
Feature initialized
Feature.serve
Request completed
~~~

Tại thời điểm in `Application ready`, code chưa cố chủ động khởi tạo `Feature`. Sau dòng `First request`, lời gọi static method `Feature.serve()` cần đảm bảo class initialized, nên thông báo của static initializer xuất hiện trước khi chạy body của `serve`.

### 4.3. Kết quả chính xác: loadClass

~~~text
Class loaded without initialization
Application ready
First request
Feature initialized
Feature.serve
Request completed
~~~

`loadClass` đã trả về Class trước khi ứng dụng ready, **nhưng static initializer vẫn chỉ chạy khi method được sử dụng**. Lúc này một phần công việc loading có thể đã được chuyển tới startup, nhưng chi phí `<clinit>` chưa được chuyển.

### 4.4. Kết quả chính xác: Class.forName với initialize=false

~~~text
Class resolved without initialization
Application ready
First request
Feature initialized
Feature.serve
Request completed
~~~

Chương trình in dòng `Class resolved without initialization` làm **nhãn mô tả thao tác lookup của demo**; đừng suy rằng mọi symbol trong bytecode đã được eagerly resolved. Điều chắc chắn là API không yêu cầu initialization, thể hiện qua thứ tự stdout.

### 4.5. Kết quả chính xác: preload có initialization=true

~~~text
Feature initialized
Preload completed
Application ready
First request
Feature.serve
Request completed
~~~

Lần này `Class.forName(name, true, loader)` buộc `Feature` được initialized trước `Application ready`. Request đầu không còn in thông báo khởi tạo vì static initializer chỉ chạy một lần trong namespace của loader.

**Điều ví dụ chứng minh:** preloading có thể **di chuyển thời điểm initialization**. Nó **không chứng minh** rằng p99 latency trong hệ thống thật nhất định giảm, startup nhất định tăng một con số cụ thể, hoặc mọi thành phần của framework đã được warm.

## 5. Định nghĩa chính xác “preloading” theo mức độ

Trong kiến trúc, từ preloading đôi khi được dùng cho những việc rất khác nhau:

| Cấp độ | Việc thực hiện | Công việc có thể còn dồn vào request đầu |
| --- | --- | --- |
| **Name lookup / load** | `loader.loadClass(name)` | Initialization, reflection cache, method first-use |
| **Load without init** | `Class.forName(name, false, loader)` | `<clinit>` và logic phụ thuộc |
| **Initialize** | `Class.forName(name, true, loader)` | Constructor, dependency initialization theo đường khác, request-specific logic |
| **Instantiate** | `Constructor.newInstance` hoặc `new` để tạo object | Lazy fields, caches, network connections, business paths |
| **Framework warm-up** | Dựng DI graph, route mapping, serializers, proxies | Paths chưa thực thi, class resolution khác, JIT compilation |
| **Application exercise** | Chạy một request an toàn đại diện | Dữ liệu khác, locks/cache misses, workload-dependent logic |
| **JIT warm-up** | Chạy hot methods đủ để JIT tối ưu theo profile | Deoptimization, profile shift, các paths hiếm |
| **CDS/AppCDS** | Chia sẻ class metadata được archive khi khởi động thích hợp | Static initialization và request-specific caches thường vẫn còn |

Đừng viết trong tài liệu vận hành rằng “đã preload xong” khi thực tế hệ thống chỉ gọi `loadClass` rồi bỏ qua startup error từ static initializer hoặc chưa kích hoạt đường code mà khách hàng sắp dùng.

### 5.1. Nạp trước không đồng nghĩa tạo bean ngay

Trong Spring hoặc framework DI khác, việc class được JVM load không đồng nghĩa **bean object đã được tạo, dependency graph hoàn chỉnh hay lifecycle hooks đã chạy**. Nạp lớp và initialization của một class cũng không đồng nghĩa với application-level initialization của framework component.

Nếu mục tiêu là tránh chậm request đầu cho DI container, cần đo và warm **đúng component path**, không chỉ gọi `Class.forName` trên các bean classes.

### 5.2. Nạp trước không đồng nghĩa JIT đã biên dịch

`Class.forName` không gọi toàn bộ methods của class và không đảm bảo JVM JIT compiler đã tối ưu chúng. JIT optimization chủ yếu phản ứng với actual execution profiles/hotness. Một “preload” thuần metadata không thay thế warm-up workload.

## 6. Tác động tới startup latency

Ở ứng dụng CLI, serverless, job chạy ngắn hoặc desktop launch, **thời gian tới hành động hữu ích đầu tiên** có thể quan trọng nhất.

Chi phí startup liên quan class loading có thể bao gồm:

- Đọc JAR entries hoặc class files từ storage.
- Tìm class trên classpath/module path qua parent delegation, URLClassLoader hoặc custom lookup.
- Verification, preparation và một phần resolution.
- Static initialization của class được sử dụng sớm.
- Framework classpath scanning/reflection index generation/proxy generation.
- Đọc cấu hình, dựng dependency graph và caches.
- I/O và page-cache warm-up ở filesystem/JAR processing.

Preload toàn bộ plugin classes ở startup có thể làm service sẵn sàng chậm, nhất là nếu chỉ một plugin được gọi ở phần nhỏ requests. Ngược lại, môi trường có health/readiness traffic ngay sau start có thể chấp nhận warm-up có kiểm soát để tránh latency spike của request đầu.

**Cần đo startup theo một định nghĩa cụ thể:**

- **Process-start to bound port?**
- **Process-start to readiness true?**
- **Readiness true to first successful request?**
- **First request p50/p95/p99 latency?**
- **Time for a batch job to finish?**

Chuyển chi phí từ trước readiness sang sau readiness có thể làm “startup metric” đẹp hơn nhưng **trải nghiệm người dùng đầu tiên** xấu hơn. Chuyển ngược lại có thể làm readiness chậm hơn trong khi request ngay sau readiness ổn định hơn. Không có lựa chọn đúng nếu chưa xác định SLA/SLO.

## 7. Tác động tới độ trễ request đầu tiên và tail latency

Lazy loading đặc biệt rõ khi một endpoint hoặc feature **chưa từng được gọi** trong process hiện tại:

~~~text
Request A đến khi class chưa initialized:
  routing
  -> discovery / class loading / linking (nếu cần)
  -> static initialization
  -> tạo dependency/proxy/cache (nếu thiết kế có)
  -> xử lý logic
  -> response

Request B đến khi class đã initialized:
  routing
  -> xử lý logic (có thể vẫn gặp warm-up khác)
  -> response
~~~

Một single-use cold path có thể tạo spike ở **p99** dù phần lớn requests nhanh. Nhưng:

- Không phải mọi lần request đầu đều phải load class; framework có thể đã load nó khi scan.
- Load và initialization có thể được trigger bởi một thread khác trước request A.
- Request đầu có thể chậm do DNS/TLS, connection pool, disk cache, JIT hoặc external service, không do class loading.
- Một preload có thể đẩy chi phí sang startup nhưng cũng làm nhiều services cùng preload đồng thời, tranh CPU và I/O, gây throughput giảm tạm thời.
- Metric chỉ đo average latency có thể che spike rõ ở requests lạnh.

Để phân tích, ghi **thời gian và thông tin event** quanh class initialization và request path, rồi đối chiếu trace/JFR thay vì chỉ đo bằng `System.currentTimeMillis` và đoán nguyên nhân.

## 8. Tác động tới memory: loaded classes không phải miễn phí

Khi một class được định nghĩa, JVM thường phải giữ metadata trong **Metaspace**, dữ liệu về constant pool, method metadata và những cấu trúc khác. Thao tác reflection/JIT/initialization cũng có thể tạo thêm objects/code caches/caches tùy ứng dụng.

Preloading nhiều classes có thể làm:

1. Tăng số **loaded classes** trong tiến trình.
2. Tăng Metaspace usage và một phần native memory.
3. Tạo static caches, singletons hoặc thread/resources khi khởi tạo.
4. Giảm cơ hội **không bao giờ dùng** những classes của features hiếm.
5. Tăng startup I/O và heap activity, có thể kéo theo GC sớm.

Nhưng không khẳng định một lớp **đã load** chắc chắn vĩnh viễn chiếm toàn bộ bộ nhớ trong cả đời process. **Class unloading** có thể xảy ra khi defining class loader và các associated classes không còn reachable theo các điều kiện JVM; các references từ static caches, threads, context class loaders, ServiceLoader/proxy caches có thể làm plugin loaders còn sống lâu hơn dự kiến.

Với classloader riêng cho nhiều plugin, preloading tất cả implementation classes vào nhiều loaders có thể tạo **nhiều bản metadata và static state** thay vì dùng một shared parent loader. Khi tối ưu startup và memory, xem cả **type identity và loader lifecycle**.

## 9. Parent delegation, ClassLoader locks và preloading song song

Một custom `ClassLoader` thường theo mô hình:

~~~text
loadClass(binaryName)
    -> findLoadedClass
    -> parent delegation
    -> findClass / defineClass
    -> resolveClass (khi yêu cầu)
~~~

Mỗi lần tự đọc class bytes từ file/mạng có thể tốn I/O. Một loader có cache và reuse `Class<?>` phù hợp sẽ tránh định nghĩa lặp.

Khi nhiều threads cùng muốn nạp một class, class loader phải đồng bộ thích hợp; `ClassLoader.loadClass` dùng class loading lock theo chính sách của loader. Với **parallel-capable class loaders**, `getClassLoadingLock(name)` có thể cấp lock theo class name để tăng concurrency; custom loaders cần đăng ký parallel-capable đúng cách nếu thiết kế hỗ trợ.

### 9.1. Chạy preload song song không phải lúc nào cũng nhanh

- Nhiều workers đọc cùng storage/JAR có thể gây I/O contention.
- Verification/initialization có thể tranh CPU ở startup.
- JVM có **class initialization lock**, nên nhiều threads cùng active-use một class có thể đợi thread đang thực hiện `<clinit>`.
- Custom loader với đồng bộ toàn loader có thể tuần tự hóa các yêu cầu mặc dù preloading được phân luồng.
- Circular initialization hoặc side effects của `<clinit>` có thể gây deadlock/hang, nhất là khi static initializer tự tạo threads và đợi chúng hoàn tất.

**Ưu tiên dùng một kế hoạch warm-up có giới hạn concurrency, phân nhóm theo hot paths và đo thực tế**, thay vì tung hàng trăm `Class.forName(name,true,loader)` cùng lúc.

## 10. Static initialization có tác dụng phụ

Đặt network/database/file I/O nặng trong `static { }` hoặc static field initializers khiến cả lazy loading lẫn preload khó dự đoán.

Ví dụ minh họa:

~~~java
final class RemoteConfig {
    static final String VALUE = fetchConfiguration();

    static String fetchConfiguration() {
        // Giả sử thực hiện I/O và có thể ném lỗi, timeout.
        return "configured";
    }
}
~~~

**Đây là snippet minh họa**, không thực sự gọi network. Khi class được initialized, `fetchConfiguration()` chạy. Preload theo `Class.forName(..., true, ...)` sẽ chạy logic đó **trước readiness** nếu target chưa initialized.

Tác động:

- **Lỗi initialization** có thể ngăn startup, thay vì chỉ làm feature hiếm gặp lỗi ở lần dùng đầu.
- **Timeout/external dependency** có thể biến readiness thành phụ thuộc vào một dịch vụ không cần thiết cho mọi chức năng.
- **CPU/memory spikes** có thể xảy ra khi nhiều static caches cùng được tạo.
- **Order dependencies** không rõ: initializer chạy sớm khi environment/config chưa sẵn sàng.

Vì vậy nên cân nhắc giữ `<clinit>` đơn giản, chuyển I/O nặng sang initialization có lifecycle rõ, có timeout, reporting và khả năng retry phù hợp. Preload static initializers để “hâm nóng” ứng dụng chỉ khi đã hiểu chính xác những side effects.

## 11. Lỗi class initialization và retry

Nếu một static initializer thất bại với exception thường, lần đầu khởi tạo có thể báo `ExceptionInInitializerError`; lần sử dụng sau của class ấy có thể báo `NoClassDefFoundError` rằng class không thể initialized. Điều này **không được giải quyết bằng cách gọi Class.forName nhiều lần trên cùng class loader**.

Ví dụ:

~~~java
public final class Broken {
    static {
        if (System.getProperty("config.ready") == null) {
            throw new IllegalStateException("missing config");
        }
    }

    public static void run() { }
}
~~~

Đây là **đoạn minh họa**; Java compiler có thể yêu cầu static initializer hoàn thành bình thường theo flow rules, còn nhánh if có điều kiện runtime như trên cho phép class compile. Nếu code chủ động preload `Broken` khi chưa cấu hình hệ thống, nó có thể **đẩy lỗi vào startup** và khiến class ở trạng thái erroneous trong defining loader.

**Nạp sớm để fail fast** có thể là một tính năng tốt nếu ứng dụng buộc cần class ấy để phục vụ bất kỳ request nào. Nhưng với optional plugin, fail fast toàn bộ process có thể làm độ sẵn sàng tệ hơn: nên cách ly lỗi và chỉ đánh dấu plugin unavailable khi phù hợp.

Muốn nạp class phiên bản mới sau khi initialization thất bại, trong một plugin architecture có thể cần **loader mới** với class definition mới và quản lý lifecycle; không thể “reset” trạng thái initialization của cùng Class tùy ý.

## 12. Một ví dụ thứ hai: preloading API mà không kích hoạt static side effects

Trong môi trường plugin, đôi khi chỉ cần xác nhận binary class name tồn tại mà **không chạy static initializer**.

~~~java
public final class PluginCatalog {
    public static Class<?> find(String name, ClassLoader loader)
            throws ClassNotFoundException {
        return Class.forName(name, false, loader);
    }
}
~~~

Đây là **class có thể biên dịch nhưng không có main**. Nó cung cấp lookup Class mà không yêu cầu initialization. Tuy nhiên:

- Chỉ việc tìm thấy Class chưa chứng minh plugin có dependencies tương thích tại mọi call site.
- Classfile có thể được link/resolved theo JVM semantics khác nhau.
- Một static initializer có thể thất bại khi plugin thực sự được sử dụng.
- Không thể coi đây là probe hoàn chỉnh để đảm bảo ServiceLoader provider hay DI bean đã sẵn sàng.

Nếu muốn rà soát API trước readiness, có thể dùng `Class.getDeclaredMethods()` hoặc `isAssignableFrom` theo nhu cầu, nhưng các thao tác reflection cũng có thể yêu cầu nạp những kiểu được tham chiếu và gây errors riêng. Đừng suy luận rằng introspection tất cả classes là zero-cost hoặc không có tương tác module/access.

## 13. ServiceLoader: khám phá provider cũng thường lazy

`ServiceLoader.load(Service.class, loader)` trả về một ServiceLoader; việc tìm metadata, tải class provider hoặc tạo instance thường diễn ra **lười khi iterate**.

Ví dụ:

~~~java
ServiceLoader<MyService> services =
        ServiceLoader.load(MyService.class, pluginLoader);

for (MyService provider : services) {
    provider.run();
}
~~~

Đây là **snippet minh họa**, giả sử `MyService` và `pluginLoader` đã tồn tại. Chỉ tạo `ServiceLoader` ở startup mà không duyệt providers không bảo đảm provider classes đã được nạp/khởi tạo.

Để warm provider thực sự, cần **duyệt và khởi tạo** các providers chủ đích (và có thể gọi các paths an toàn phù hợp). Tuy nhiên:

- Plugin constructor có thể thực hiện I/O và đăng ký resources.
- Nếu plugin bytecode không tương thích service interface runtime, iteration có thể ném `ServiceConfigurationError`.
- Nếu provider optional, preloading tất cả provider có thể làm startup chịu lỗi của plugin không dùng.
- `reload()` làm mới cache ServiceLoader, **không thay Class đã được defining loader nạp/khởi tạo**.

Đặt service API ở common parent loader nếu host và provider cần chia sẻ cùng runtime type, để tránh preloading làm lộ các lỗi “provider not a subtype” trong lúc startup.

## 14. Reflection, Dynamic Proxy và framework startup

Reflection frameworks có thể tạo nhiều chi phí “đầu tiên”:

- Tìm annotations trên classes.
- Lấy `Method`, `Field`, constructors và kiểm tra access.
- Sinh dynamic proxy classes.
- Dựng object graph và injection metadata.
- Phân tích route/controller mappings.
- Cấu hình serializers/deserializers.
- Scan classpath/JAR entries.

**Chủ động nạp class bằng Class.forName(false) không tự thực hiện tất cả các công việc này.**

Nếu framework cung cấp chế độ eager initialization, lazy bean creation hoặc startup hooks, hãy hiểu **đơn vị được preload là gì**. Chẳng hạn một framework có thể load class để đọc annotation nhưng trì hoãn tạo bean; request đầu vẫn phải chạy constructor và proxy generation.

Trong hệ thống có nhiều ClassLoader hoặc ModuleLayer, proxy class được tạo phải nhìn thấy **đúng interface Class runtime** từ loader được chỉ định. Tăng preload bừa bãi không sửa được parent delegation/API duplication hay module opens/exports issues.

## 15. JIT warm-up khác class preloading

**Class loading và JIT compilation là hai hiện tượng riêng.**

Một JVM có thể interpreter-run một method trước, thu execution profiles rồi biên dịch bằng JIT khi method trở nên hot. Preloading một Class mà không gọi methods của nó không tạo đủ profile để làm mọi method hot.

Sơ đồ:

~~~text
Class bytes --> loading/linking --> initialization
                       |
                       +--> first method invocation
                                 |
                                 +--> interpreter / tiered compilation
                                 +--> hotness / profile / optimization
                                 +--> potential deoptimization and recompilation
~~~

Nếu mục tiêu giảm latency request đầu do JIT, hãy thiết kế **warm-up workload** đại diện với data đủ giống production, nhưng kiểm soát side effects:

- Gọi test endpoint nội bộ khi ứng dụng ở trạng thái warming nhưng chưa nhận traffic.
- Không tạo giao dịch thật hay gửi email thật chỉ để “warm”.
- Không mặc định JIT state và profile của test request sẽ bao phủ production distributions.
- Đo lại performance sau warm-up, không dùng số vòng lặp cố định áp dụng cho mọi JDK và CPU.
- Với serverless/short-lived CLI, prewarming dài có thể tốn hơn lợi ích của nó.

CDS và AppCDS có thể giúp giảm một phần chi phí loading/memory bằng archive được JVM hỗ trợ. **Chúng không phải lệnh “chạy mọi static initializer”** và không loại bỏ JIT/runtime warm-up của ứng dụng.

## 16. Measuring: phân biệt cold start, warm start và cold path

Một kế hoạch benchmark đáng tin nên xác định:

| Metric | Câu hỏi | Cách đo gợi ý |
| --- | --- | --- |
| Time to process ready | JVM có thể nhận traffic hợp lệ sau bao lâu? | Đo process start đến readiness event |
| Cold first request | Request đầu sau launch chậm bao nhiêu? | Đo end-to-end client-side latency |
| Warm request latency | Sau khi đã dùng feature, latency ra sao? | Nhiều iterations, phân phối latency |
| p95/p99 | Có long-tail spikes lúc class init không? | Request traces + histograms |
| Classes loaded | Bao nhiêu Class được nạp, từ đâu? | JVM Unified Logging / JFR |
| Metaspace | Preload thêm metadata bao nhiêu? | JFR, MemoryPoolMXBean, native memory tracking |
| Heap allocations/GC | Init caches có gây pressure không? | JFR, GC logging, heap metrics |
| CPU/I/O during startup | Preload chiếm CPU và disk bao nhiêu? | Process/host-level metrics |
| Throughput under load | Preloading có làm xử lý tổng thể tốt hơn? | Load test sau readiness |

### 16.1. Chạy benchmark mỗi phương án trong JVM process mới

Nếu chạy lazy rồi preload tuần tự trong **cùng JVM với cùng defining loader**, lần thứ hai có thể không còn class initialization cost: kết quả thiên lệch vì class đã initialized. Muốn đo cold effects, tạo **process mới** cho từng trial hoặc có một loader namespace thực sự mới khi phù hợp với kiến trúc.

Nên:

1. Build artifact cố định, cùng JDK/version, cùng hardware/CPU quota và configuration.
2. Chạy nhiều vòng độc lập cho **lazy**, **preload-load-only**, **preload-initialize**.
3. Tách cold OS page-cache và warm OS page-cache nếu nó ảnh hưởng.
4. Ghi startup/readiness, first-use latency và p99; không chỉ average.
5. Đo memory (Metaspace, heap, code cache) và GC, cùng số classloaded.
6. Báo p50/p95/p99, confidence range hoặc phân phối; không công bố một con số đại diện cho mọi máy.
7. Chạy A/B ở cùng traffic/load; ghi rõ preload có sử dụng CPU cores cạnh tranh với workloads không.

Với microbenchmarks về method execution, ưu tiên JMH và tránh dùng một vòng lặp `nanoTime` đơn giản để kết luận JIT optimization toàn diện. Với first-request latency, **end-to-end process-level measurements** thường hữu ích hơn.

### 16.2. Quan sát class loading với JVM Unified Logging

Trên OpenJDK/HotSpot Java 17+:

~~~bash
java -Xlog:class+load=info -cp out LoadingDemo lazy
~~~

Lệnh này chạy ví dụ ở mục 4 nếu đã compile. Nó sẽ in **rất nhiều log từ JVM**, tùy phiên bản và classpath; không có transcript cố định. So `class+load` events với log `Feature initialized` để thấy **đã load** không đồng nghĩa **đã initialize**.

Unified logging bản thân cũng có overhead, do đó chỉ bật ở giai đoạn chẩn đoán hoặc benchmark có cấu hình nhất quán giữa các biến thể.

### 16.3. Dùng Java Flight Recorder

Có thể bắt đầu JFR khi launch:

~~~bash
java -XX:StartFlightRecording=filename=loading.jfr,settings=profile \
     -cp out LoadingDemo preload
~~~

Đây là lệnh **Unix shell** minh họa. Trên PowerShell/CMD, viết cùng trên một dòng:

~~~powershell
java -XX:StartFlightRecording=filename=loading.jfr,settings=profile -cp out LoadingDemo preload
~~~

Tập events thu được phụ thuộc cấu hình JFR và JVM; nếu cần **class loading/initialization events chi tiết**, bật những events khả dụng trong runtime mà bạn đang dùng. Không suy rằng profile settings mặc định chứa mọi class event hoặc tự đo được tất cả static initialization cost ở cấp method.

JFR giúp quan sát timeline, allocation và các events hoạt động JVM, nhưng **không thay request latency measurements** từ phía client.

## 17. Preloading theo thứ tự, ưu tiên và “readiness budget”

Thay vì preload **mọi class**, ta có thể phân loại:

**Nhóm A — bắt buộc trước khi sẵn sàng:** shared service API, những modules/beans luôn dùng bởi mọi request, config bắt buộc, failure nên fail fast.

**Nhóm B — hot paths quan trọng:** authentication/authorization, routing/serialization của endpoint thường gặp. Có thể warm trước readiness hoặc trong giai đoạn canary/warm-up ngắn sau startup.

**Nhóm C — optional/rare paths:** exporters ít dùng, report builders, admin-only endpoints, plugin tùy chọn. Thường phù hợp lazy initialization nếu first-use latency vẫn đáp ứng SLO.

**Nhóm D — dynamic plugins/reloadable:** load theo demand với quản lý loader lifecycle, cache bounded và isolation. Không tự động eager-init plugin từ nguồn chưa được phép.

Một kế hoạch mẫu:

~~~text
Process start
  |
  +-- initialize mandatory core (fail-fast)
  |
  +-- build routing table / dependency metadata
  |
  +-- optional: warm critical endpoints safely
  |
  +-- readiness ON
  |
  +-- background/low-priority warm optional warmable paths
  |      (chỉ nếu có orchestration, quotas, cancellation)
  |
  +-- normal user traffic
~~~

Đây là **sơ đồ thiết kế**, không phải chức năng tự có của `ClassLoader`. Nếu production chạy nhiều replicas, orchestrator cần biết lúc nào instance nhận traffic; khi hệ thống không có warm-up hooks và budgets rõ ràng, “preload nền” có thể tranh CPU với request và làm tail latency tệ hơn.

## 18. Preloading không phải tự động an toàn

Khi chủ động chạy `Class.forName(name, true, loader)` trên các class names lấy từ manifest:

- Một số class có static initializer gửi requests hoặc đọc credentials.
- Một số plugin chỉ được phép chạy khi tenant/feature flag cụ thể được bật.
- Một initializer có thể tạo threads, register shutdown hooks hoặc giữ loader references.
- A plugin may be untrusted code even if bytecode verified.
- Eager initialization làm những lỗi optional có thể xuất hiện trước readiness.
- Eager scanning trên network storage có thể gây timeout/retry storms.

Do đó, **class names phải thuộc allowlist đáng tin**, source artifact phải được approve, và preload policy cần dựa trên những class **được phép khởi tạo**; không dùng một danh sách path tùy ý từ user input rồi tự tạo static side effects.

**Security note:** verifier và custom ClassLoader không phải sandbox quyền I/O cho code plugin. Khi code từ bên không tin cậy phải bị hạn chế, dùng isolation tại process/container/VM và các OS permissions phù hợp.

## 19. Những lỗi thường gặp khi đánh giá lazy loading

### Lỗi 1: Đồng nhất loadClass với initialize

`loadClass` không tự yêu cầu static initialization. Muốn chuyển công việc `<clinit>` sớm hơn, phải chọn API/cách sử dụng có thể yêu cầu initialization, ví dụ `Class.forName(..., true, loader)` — nhưng phải cân nhắc side effects.

### Lỗi 2: “Class.forName(false) đã warm toàn bộ feature”

Không. Nó không yêu cầu static initialization, không tạo object theo DI lifecycle và không thực thi hot methods để warm JIT.

### Lỗi 3: Preload càng nhiều càng tốt

Sai. Nhiều class hiếm có thể tăng startup, metadata/memory và I/O mà không cải thiện SLO cho traffic thực.

### Lỗi 4: Đánh giá trong cùng JVM đã warm

Class đã initialized không chạy `<clinit>` lần nữa chỉ vì gọi `Class.forName`. Test cold cần process/layer/loader thực sự mới theo bài toán, không reuse một runtime warmed-up.

### Lỗi 5: Chỉ so startup time

Mô hình preload có thể chậm startup nhưng giảm latency request đầu; mô hình lazy ngược lại. Cần đo cả readiness và first-use/p99.

### Lỗi 6: Giả định mọi delay đầu tiên do class loading

Class initialization, first connection, JIT, disk cache, TLS, DNS, data cache, reflection/proxy generation cũng có thể tạo delay. Dùng traces và JFR để phân biệt.

### Lỗi 7: Quên static initializer side effects

Preload có thể kích hoạt I/O, throw exception hoặc chờ locks ngay khi deployment. Khởi tạo có chủ đích phải có observability và error handling phù hợp.

### Lỗi 8: Bỏ qua class loader identity

Hai loaders tự định nghĩa cùng binary name sẽ tạo hai Class runtime riêng. Warm class bằng loader A không bảo đảm plugin loader B đã được warm; preload sai loader có thể làm tăng overhead.

### Lỗi 9: Bỏ qua memory overhead của metadata

Class đã loaded có metadata và có thể giữ static state. Preload mọi plugin tăng pressure lên Metaspace/caches, và giữ references có thể chặn unloading.

### Lỗi 10: Bật preload nhiều luồng không giới hạn

Có thể tranh CPU/IO, làm initializer lock contention và tăng latency. Hạn chế concurrency, đo rate và tách critical/non-critical work.

### Lỗi 11: Tưởng CDS/AppCDS thay thế workload warm-up

CDS hỗ trợ archive metadata/class data theo VM; không đảm bảo static initializers được chạy hoặc methods đã JIT optimized cho traffic.

### Lỗi 12: Dùng ServiceLoader.load nhưng không iterate

ServiceLoader dùng lazy discovery/instantiation. Chỉ tạo ServiceLoader không đảm bảo providers đã được tạo hoặc validated toàn diện.

## 20. Gợi ý thiết kế API warm-up có kiểm soát

Nếu cần warm service có interface chung, ưu tiên **warm tại tầng use case** thay vì reflection vô hạn:

~~~java
public interface Warmable {
    void warmUp();
}
~~~

Service có thể implement contract và warm một đường code **an toàn, idempotent, có timeout/quota**. Orchestrator gọi nó theo danh sách các components đã approve.

Những lưu ý:

- `warmUp()` có thể chạy nhiều lần hoặc bị retry; cần biết có an toàn không.
- Nếu hệ thống dùng DI, hãy gọi sau khi config và dependencies sẵn sàng.
- Tránh ghi dữ liệu sản xuất, gửi external notifications hoặc tạo giao dịch thật khi chỉ muốn warm.
- Expose readiness **sau** warm-up bắt buộc; warm-up optional có thể chạy ở trạng thái giảm ưu tiên và có cancellation.
- Ghi metric riêng cho warm time, failure và CPU/memory cost.
- Với plugins, expose shared interface `Warmable` từ common parent loader, không cho child-first định nghĩa một bản copy.

Đây là **thiết kế minh họa**, không phải một API Java SE tên “preload all applications”. Mọi chiến lược cần tích hợp vào lifecycle của chính ứng dụng.

## 21. Bài tập tự kiểm tra

**1. Loading khác initialization ở điểm nào?** Loading tạo runtime Class từ bytes, initialization thực thi `<clinit>` theo quy tắc active use.

**2. `loader.loadClass(name)` có tự chạy static initializer không?** Không yêu cầu. Đó là khác biệt quan trọng so với `Class.forName(name, true, loader)`.

**3. `Class.forName(name,false,loader)` giúp gì?** Lấy/tìm Class mà không yêu cầu initialization; không tự warm DI/JIT.

**4. Tại sao `Feature.class` chưa chắc in thông báo static initializer?** Class literal không tự làm class initialized.

**5. Gọi static method lần đầu có thể làm gì?** Active use kích hoạt initialization của declaring class nếu cần trước khi chạy method.

**6. Preloading có thể cải thiện metric nào?** First-use latency và một số tail spikes, nếu thực sự chuyển công việc cần thiết khỏi request path.

**7. Preloading có thể làm xấu metric nào?** Startup/readiness latency, I/O/CPU contention và memory footprint.

**8. Vì sao benchmark phải dùng JVM process mới?** Nếu dùng lại Class đã initialized, kết quả cold latency không còn hợp lệ.

**9. Vì sao JIT warm-up không tương đương class loading?** JIT cần execution profiles/hotness; load Class không chạy hết methods.

**10. Vì sao preloading static initializer có thể làm startup fail?** Nó có thể ném exception, chờ I/O, tạo threads hoặc phụ thuộc config chưa sẵn sàng.

**11. `ServiceLoader.load` có bảo đảm provider class đã khởi tạo không?** Không; khám phá/tạo provider thường lazy khi iterate.

**12. Vì sao RAM có thể tăng sau preload?** Nhiều Class metadata trong Metaspace, static caches và có thể thêm heaps/code caches.

**13. Class loader mới load cùng binary name có tận dụng initialization của class loader cũ không?** Không mặc nhiên; đó có thể là hai runtime Class khác nhau.

**14. Có nên preload tất cả optional plugins khi process start không?** Không mặc định. Phân nhóm theo SLO, tải có chọn lọc, đo startup/first-use và bảo vệ nguồn code.

**15. Preload có thể thay thế readiness/liveness probe không?** Không. Readiness phải phản ánh hệ thống có thể phục vụ hợp lệ; preloading chỉ là một chiến lược lifecycle.

## 22. Tài liệu tham khảo

- **JLS Java 17 `12.2 — Loading of Classes and Interfaces:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.2
- **JLS Java 17 `12.3 — Linking of Classes and Interfaces:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.3
- **JLS Java 17 `12.4 — Initialization of Classes and Interfaces:** https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.4
- **JVMS Java 17 `5 — Loading, Linking and Initializing:** https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html
- **Java SE 17 — ClassLoader:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **Java SE 17 — Class.forName:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html
- **Java SE 17 — ServiceLoader:** https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ServiceLoader.html
- **Java SE 17 — JFR APIs:** https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/module-summary.html
- **Java SE 17 — java launcher (Unified Logging, JFR, CDS options):** https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
