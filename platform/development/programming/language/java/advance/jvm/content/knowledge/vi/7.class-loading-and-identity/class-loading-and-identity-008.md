# Khi nào lớp có thể được dỡ bỏ và liên hệ với vòng đời class loader

## 1. Class unloading là gì?

JVM **nạp (load)** một lớp hoặc interface khi cần có biểu diễn kiểu ở runtime. Nó giữ thông tin về kiểu, method, field, constant pool và những cấu trúc nội bộ phục vụ liên kết, kiểm chứng và thực thi. **Class unloading** là quá trình JVM có thể thu hồi một định nghĩa kiểu runtime không còn cần thiết cùng tài nguyên metadata liên quan theo chính sách quản lý bộ nhớ.

Class unloading **không đồng nghĩa** với:

- **Object garbage collection:** thu gom instance của một class. Có thể không còn instance nào nhưng class vẫn sống vì class loader còn sống.
- **Đóng class loader:** `URLClassLoader.close()` đóng resource loader quản lý; không ép JVM unload những class đã định nghĩa.
- **Xóa JAR hoặc `.class` trên đĩa:** không ngay lập tức xóa class runtime đã nạp.
- **Gán một reference bằng `null`:** chỉ thay một reference, không đảm bảo mọi đường tham chiếu tới loader đã mất.
- **Chạy lại static initializer:** class unload và một class mới được định nghĩa ở một loader mới là hai runtime class khác nhau, không phải `<clinit>` của chính class cũ được “reset”.

Theo **JVMS §5.3**, với những **named class/interface thông thường**, một class/interface có thể được unload **khi và chỉ khi defining class loader của nó có thể được garbage collector thu hồi**. Đây là điều kiện eligibility, **không phải bảo đảm thời điểm thực thi**. JVM, garbage collector và cấu hình quyết định khi nào collection/unloading diễn ra, hoặc liệu nó có xảy ra trong thời gian chương trình còn chạy.

> **Mấu chốt:** giải phóng object của plugin mới chỉ là một phần. Muốn các named classes do plugin loader định nghĩa có cơ hội unload, cần để **defining class loader** và mọi đối tượng giữ loader ấy không còn đường tham chiếu mạnh từ những GC roots.

Có một ngoại lệ cần hiểu khi học JVM nâng cao: **hidden classes** được định nghĩa qua các API đặc biệt có thể dùng cơ chế reachability khác; không áp dụng nguyên xi quy tắc named-class/plugin-loader cho mọi class do JVM sinh động.

## 2. Class identity gắn với defining loader

Đối với named class/interface, cùng **binary name** chưa đủ để kết luận là cùng kiểu JVM; **defining class loader** cũng góp phần xác định runtime identity.

~~~text
URLClassLoader A
    └── define demo.plugin.Greeter ──> Class A

URLClassLoader B
    └── define demo.plugin.Greeter ──> Class B

Tên giống nhau, defining loader khác nhau:
Class A != Class B.
~~~

Điều này có hệ quả thực tế:

- Hai class trên có `Class<?>` object riêng, class metadata riêng và **static fields** riêng.
- Mỗi class có lifecycle **initialization** riêng: static initializer có thể chạy một lần với A và một lần với B.
- Object `Greeter` của A không tự nhiên là instance của `Greeter` của B. Cast chéo có thể ném `ClassCastException`, dù tên class in ra giống nhau.
- Đối với class do loader cha define và loader con chỉ ủy quyền (delegation), loader con không tạo một class identity mới.

Cần phân biệt **initiating loader** (loader yêu cầu/bắt đầu nạp) với **defining loader** (loader thực sự định nghĩa class). Parent-first delegation thường tìm ở parent trước. Nếu parent đã define class, một lời gọi `child.loadClass(name)` có thể nhận class của parent. **Không suy luận identity từ loader ban đầu mà code gọi**; hãy quan sát defining loader bằng `type.getClassLoader()`.

Các runtime package và access rules cũng chịu ảnh hưởng loader. Hai class có cùng chuỗi tên package nhưng defining loader khác nhau không tự trở thành cùng một runtime package để được truy cập package-private.

## 3. Vòng đời plugin loader: tách bước chủ động và GC

Một hệ plugin/hot-reload điển hình có hai phần vòng đời:

~~~text
Phần ứng dụng có thể kiểm soát:

[Khởi tạo plugin loader phiên v1]
      |
[Load / link / initialize các class khi cần]
      |
[Chạy plugin: requests, jobs, listeners]
      |
[Stop nhận việc mới / draining]
      |
[Hủy đăng ký, dừng thread, đóng I/O]
      |
[Đóng URLClassLoader, bỏ host references]
      v

Phần JVM/GC quyết định:

[Loader không còn reachable từ GC roots]
      |
[Eligible cho collection và class unloading]
      |
[GC thực thi khi phù hợp]
      |
[Class metadata có thể được thu hồi]
~~~

**Không tồn tại API Java tiêu chuẩn `Class.unload()`** cho named class thông thường. Ứng dụng quản lý tài nguyên và ownership; unloading xảy ra sau đó **nếu** điều kiện và chính sách runtime cho phép.

Không nên thiết kế một API `stopPlugin()` trả về với lời hứa “mọi class thuộc phiên plugin đã bị JVM unload”. Lời hứa hợp lý hơn là: plugin đã ngừng xử lý công việc, dọn sạch đăng ký/tài nguyên mà hệ thống sở hữu và loại bỏ các strong references mà host có thể kiểm soát.

### Loading, linking, initialization và unloading không phải một trạng thái

| Giai đoạn | Điều JVM thực hiện | Không được suy ra |
| --- | --- | --- |
| Loading | Tìm binary representation, tạo runtime class/interface | Static initializer đã chạy |
| Linking | Verification, preparation, resolution theo quy tắc JVM | Mọi symbolic reference luôn resolve ngay một lần |
| Initialization | Thực thi logic `<clinit>` khi được yêu cầu | Đã tạo một instance |
| Usage | Tạo object, chạy method, reflection, tasks... | Class được tự động unload khi một method kết thúc |
| Eligible for unloading | Defining loader không còn cần được giữ sống (named classes thông thường) | JVM đã unload tức thời |
| Actual unloading | JVM thu hồi class metadata tương ứng | File JAR hoặc tài nguyên ứng dụng đã tự đóng |

Ví dụ một class tiện ích chỉ có static method có thể được initialize và dùng nhiều lần mà không hề có instance. Ngược lại, thu gom hết instance không làm class phải unload.

## 4. Vì sao một loader vẫn sống? GC roots và reachability

GC không hoạt động bằng cách “đếm bao nhiêu reference trong một vòng tròn”. Nó tìm những object còn được truy cập qua **strong references** từ các root như thread stacks, một số static references, native/JNI handles và cấu trúc runtime phù hợp.

Hãy hỏi về plugin v1:

1. Host vẫn giữ `ClassLoader` trong một `Map`, registry hoặc biến field không?
2. Có **plugin instance** trong cache, listener, message queue, scheduler hoặc callback của host?
3. Có `Class<?>`, `Method`, `Field`, `Constructor`, `MethodHandle`, proxy, lambda hoặc framework cache giữ class plugin?
4. Có thread đang chạy code plugin hoặc một executor chưa shutdown, hay còn queued `Runnable`/`Callable` tạo từ class plugin?
5. Có thread host sống lâu mà **thread context class loader (TCCL)** vẫn trỏ tới loader plugin?
6. Có `ThreadLocal` value trên thread pool hoặc request context không được clear?
7. Có MBean, driver, logging handler, event bus listener, shutdown hook, resource manager hoặc native global ref chưa hủy đăng ký?
8. Có framework/module layer hoặc loader cha tùy biến đang giữ reference tới loader con?

Đây là **những nơi cần đo retaining paths**, không phải khẳng định rằng mọi API vừa kể đều chắc chắn leak trong mọi tình huống.

### Ví dụ đường giữ sống

~~~text
GC ROOT: host worker thread
       |
       +── contextClassLoader
                   |
                   v
             PluginLoader v1
                   |
                   +── define PluginClass / Helpers / ...
~~~

Dù UI đã báo “plugin stopped”, một thread host vẫn có thể giữ v1 qua `contextClassLoader`. Loại bỏ đường đó cùng những strong paths khác giúp loader có thể trở thành unreachable.

### Một chu trình thuần túy không phải leak

~~~text
PluginLoader -> PluginClass -> PluginSingleton
     ^                             |
     +-----------------------------+
~~~

Nếu cụm object trên **không có đường tới từ GC root**, tracing GC có thể thu hồi chu trình ấy. Vì thế không kết luận rằng class static field trỏ về loader thì loader mãi mãi không thể unload; **đường root thực tế** mới là vấn đề.

Ngược lại, một **host static cache** ở class do application loader sống lâu định nghĩa có thể là root path:

~~~text
HostRegistry.staticMap
        |
        v
   PluginObject
        |
        v
  Runtime Class
        |
        v
  Defining Loader v1
~~~

Gán một biến cục bộ `plugin = null` mà quên `HostRegistry.staticMap.remove(key)` không giải quyết retaining path này.

## 5. “Có thể unload” và “đã unload” không đồng nghĩa

| Quan sát | Kết luận hợp lệ |
| --- | --- |
| Không còn instance trực tiếp của Plugin | **Chưa đủ**; loader/class vẫn có thể reachable |
| `plugin = null` | Chỉ xóa một reference; có thể còn nhiều reference khác |
| `loader = null` | Chưa biết root path nào khác giữ loader |
| `URLClassLoader.close()` trả về | Đã xử lý resource theo contract của `close`; **không xác nhận unload** |
| `System.gc()` được gọi | JVM nhận một yêu cầu/hint GC; **không có deadline hoặc bảo đảm unload** |
| `WeakReference<ClassLoader>.get() == null` | Loader được weak reference theo dõi đã được GC clear; đây là tín hiệu rõ về reachability tại lúc quan sát |
| Log HotSpot `class+unload` ghi event class X | Có bằng chứng JVM đã unload X trong lần chạy đó |
| `Metaspace committed` chưa giảm | **Không đủ** để nói class chưa unload; JVM có thể giữ capacity để dùng lại |
| `Metaspace used` tăng | Không tự chứng minh leak; có thể nhiều class mới được load hoặc workload tăng |

`System.gc()` còn có thể bị vô hiệu hóa hoặc triển khai theo cơ chế khác tùy VM flags/collector. Không viết test kiểu “gọi GC ba lần rồi tất cả class v1 phải unload”.

**Các class do bootstrap, platform hoặc application loader sống lâu định nghĩa** thường có vòng đời tương ứng JVM hoặc ứng dụng. Chúng không phải một cơ chế unload từng feature tùy ý. Nếu một loader thông thường vẫn sống, không có API “unload riêng named class đã define” như cách xóa một entry khỏi map.

## 6. Ví dụ Java 17 chạy độc lập: cùng tên, hai class loader

Ví dụ sau minh họa **hai runtime class riêng biệt** và hoạt động `close()` của loader mà **không khẳng định việc class unloading sẽ xảy ra** ngay lập tức. Tạo hai source file trong hai cây thư mục khác nhau.

### 6.1. File plugin: `plugin-src/demo/plugin/Greeter.java`

~~~java
package demo.plugin;

public class Greeter {
    static {
        System.out.println("PLUGIN_INIT");
    }

    public String hello() {
        return "HELLO";
    }
}
~~~

### 6.2. File host: `app-src/LoaderCycleDemo.java`

~~~java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

public final class LoaderCycleDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: LoaderCycleDemo plugin-out");
        }

        URL root = Path.of(args[0]).toAbsolutePath().toUri().toURL();

        try (URLClassLoader first = new URLClassLoader(
                     new URL[] { root },
                     ClassLoader.getPlatformClassLoader());
             URLClassLoader second = new URLClassLoader(
                     new URL[] { root },
                     ClassLoader.getPlatformClassLoader())) {

            Class<?> typeA = Class.forName(
                    "demo.plugin.Greeter", true, first);
            Class<?> typeB = Class.forName(
                    "demo.plugin.Greeter", true, second);

            System.out.println("SAME_NAME=" +
                    typeA.getName().equals(typeB.getName()));
            System.out.println("SAME_CLASS=" + (typeA == typeB));
            System.out.println("SAME_LOADER=" +
                    (typeA.getClassLoader() == typeB.getClassLoader()));

            Object objectA = typeA.getConstructor().newInstance();
            System.out.println("HELLO=" +
                    typeA.getMethod("hello").invoke(objectA));

            try {
                typeB.cast(objectA);
                System.out.println("CROSS_CAST=OK");
            } catch (ClassCastException expected) {
                System.out.println("CROSS_CAST=FAIL");
            }
        }

        System.out.println("LOADERS_CLOSED");
    }
}
~~~

Ở đây **host không import `demo.plugin.Greeter`**: host chỉ dùng reflection và tên nhị phân. Parent được đặt thành **platform class loader**, để hai `URLClassLoader` tải class plugin từ cùng thư mục và mỗi loader tự define `Greeter`. Không thêm `plugin-out` vào `java -cp` của host.

### 6.3. Biên dịch và chạy

Từ thư mục chứa `plugin-src` và `app-src`:

~~~bash
javac --release 17 -d plugin-out plugin-src/demo/plugin/Greeter.java
javac --release 17 -d app-out app-src/LoaderCycleDemo.java
java -cp app-out LoaderCycleDemo plugin-out
~~~

**Stdout xác định bởi chương trình:**

~~~text
PLUGIN_INIT
PLUGIN_INIT
SAME_NAME=true
SAME_CLASS=false
SAME_LOADER=false
HELLO=HELLO
CROSS_CAST=FAIL
LOADERS_CLOSED
~~~

Giải thích:

1. `Class.forName("demo.plugin.Greeter", true, first)` nạp và **initialize** class mà loader `first` define, in `PLUGIN_INIT` lần đầu.
2. Lời gọi với `second` tạo một runtime class khác cùng binary name, in `PLUGIN_INIT` lần thứ hai.
3. `typeA.getName().equals(typeB.getName())` đúng, nhưng `typeA == typeB` sai vì defining loader khác nhau. Loader objects cũng khác nhau.
4. Reflection gọi `hello()` trên instance của typeA thành công.
5. `typeB.cast(objectA)` thất bại: object của typeA không là instance của typeB.
6. `try-with-resources` gọi `close()` với cả hai URLClassLoader và in `LOADERS_CLOSED` sau đó. **Dòng này không khẳng định class hoặc loader đã được GC/unload.**

Ví dụ có tính quyết định về identity và dispatch trong điều kiện Java 17+ chuẩn. Nó **không** dùng chu kỳ GC, heap size hay thời điểm JIT làm điều kiện output. Với một JVM agent/instrumentation tùy biến, môi trường có thể có tác động thêm không thuộc bài thực hành.

## 7. Đóng loader không giống đóng plugin và không giống unload

`URLClassLoader.close()` giải phóng tài nguyên mở mà loader quản lý, chẳng hạn những `JarFile` theo hợp đồng API. Điều quan trọng:

- Class **đã define** không biến mất chỉ vì `close()`.
- Method đang chạy từ class plugin không tự bị JVM cắt ngang.
- Object đã tạo vẫn có thể tồn tại và dùng những class đã load.
- Loader object đã đóng vẫn có thể được host map, thread hoặc reflection cache giữ sống.
- Sau khi đóng, loader không còn được kỳ vọng tải thêm class/resource mới theo cách cũ; ứng dụng không nên tiếp tục sử dụng nó như loader còn hoạt động.
- GC và class unloading có thể diễn ra muộn hoặc không diễn ra trước khi process kết thúc.

Vì thế bạn nên thiết kế ba lớp vòng đời tách bạch:

~~~text
Vòng đời nghiệp vụ:
   stop job -> unregister -> hoàn tất request -> close resource

Vòng đời class loader:
   tạo loader -> define class -> phục vụ -> close loader ->
   bỏ references do host sở hữu

Vòng đời bộ nhớ JVM:
   GC phân tích reachability -> eligible -> có thể unload ->
   metadata có thể thu hồi / tái sử dụng
~~~

Không đợi unload làm nhiệm vụ đóng `Socket`, transaction, logging handler, thread pool hoặc file: Java không cung cấp một class destructor đáng tin để tự làm việc này.

## 8. Dùng WeakReference để quan sát, không để ép unload

`WeakReference<ClassLoader>` có thể giúp quan sát liệu một loader đã được GC xử lý. Nhưng bản thân việc dùng weak reference không khiến class unload đúng hạn.

~~~java
import java.lang.ref.WeakReference;

// Đoạn minh họa: makeLoaderAndReleaseStrongRefs()
// phải được viết để không trả lại strong reference
// và phải stop/close mọi tài nguyên của plugin.
WeakReference<ClassLoader> probe = makeLoaderAndReleaseStrongRefs();

System.gc(); // chỉ là đề nghị, có thể không GC/unload
ClassLoader result = probe.get();

System.out.println(result == null
        ? "LOADER_CLEARED"
        : "NOT_CLEARED_YET");
~~~

**Đoạn trên không phải chương trình Java độc lập**: method minh họa `makeLoaderAndReleaseStrongRefs()` chưa được định nghĩa. Nó giải thích cách đọc phép đo:

- `LOADER_CLEARED` nghĩa là weak reference không còn nhận được loader object; đây là tín hiệu loader đã được xử lý bởi GC.
- `NOT_CLEARED_YET` **không phải chứng minh class-loader leak**: có thể còn strong reference hoặc collector chưa chạy theo hướng cần thiết.
- Biến `result` khi khác `null` lại chính là **strong reference mới** trong scope đang chạy; test code có thể vô tình giữ sống object mà nó đang chờ thu gom.

**Tránh `finalize()`:** overriding `finalize()` của một loader hoặc plugin object không phải hook của class unloading. Finalization là cơ chế cũ, deprecated/không đáng tin và có thể bị vô hiệu hóa. Dùng explicit close, Reference API đúng ngữ nghĩa hoặc công cụ JVM để đo, không coi log từ finalizer là bằng chứng class đã unload.

## 9. Theo dõi class loading/unloading bằng HotSpot

Với JVM HotSpot/JDK 17+ hỗ trợ **Unified Logging**, dùng:

~~~bash
java -Xlog:class+load=info,class+unload=info -cp app-out LoaderCycleDemo plugin-out
~~~

Lệnh này ghi cả sự kiện class load và **class unload nếu có**. Dữ liệu output log phụ thuộc JVM/GC/environment nên không đưa “stdout cố định” khi bật logging.

Có thể ghi log JVM ra file (Bash/Linux/macOS):

~~~bash
java '-Xlog:class+load=info,class+unload=info:file=classes.log:uptime,level,tags' -cp app-out LoaderCycleDemo plugin-out
~~~

Trong PowerShell, truyền option chứa ký tự đặc biệt bằng chuỗi quoted:

~~~powershell
java '-Xlog:class+load=info,class+unload=info' -cp app-out LoaderCycleDemo plugin-out
~~~

**Lưu ý:** ví dụ ở mục 6 chạy nhanh, không ép collector, vì vậy hoàn toàn có thể có log load của cả hai `Greeter` **mà không có log unload nào** trước khi tiến trình kết thúc. Đó không phải một lỗi; mục đích ví dụ là chứng minh **class identity**, không tạo workload để đo GC.

Các cách quan sát bổ sung trên JVM tương thích:

- `-Xlog:gc*` hiển thị hoạt động GC, nhưng không tự giải thích vì sao một loader bị giữ sống.
- `jcmd <pid> VM.classloader_stats` có thể cung cấp thống kê class loaders/class metadata trên các bản HotSpot hỗ trợ lệnh này; dùng `jcmd <pid> help` kiểm tra thực trạng của JVM đích.
- Heap dump/Java Flight Recorder hoặc profiler có thể hỗ trợ tìm những **retaining paths** từ GC roots tới `ClassLoader`, thread, `Class<?>`, listener hoặc cache.
- Khi so sánh các lần reload, ghi lại plugin version, ID của loader, thời điểm stop/close và số lượng loader còn sống.

Một heap dump có thể chứa mật khẩu, token và dữ liệu người dùng trong memory. Chỉ thu thập khi được phép, lưu ở nơi kiểm soát quyền truy cập và không tải công khai.

### Metaspace không đồng nghĩa class count

HotSpot thường dùng **Metaspace** để quản lý nhiều dạng class metadata. Nhưng:

- `used`, `committed` và `reserved` là các đại lượng khác nhau.
- JVM có thể giữ committed capacity để **tái sử dụng** dù có metadata đã được thu hồi.
- Workload đồng thời có thể load lớp mới khi lớp cũ unload, khiến tổng `used` không giảm.
- Memory của object instance, class metadata, code cache, native buffers và file-mapped pages là những nguồn tiêu thụ khác nhau.

Vì vậy “RSS không giảm” hoặc “Metaspace committed không giảm ngay” **không đủ** kết luận rằng class unloading thất bại. Hãy kết hợp unload events, loader stats và heap retaining paths.

## 10. Những nguyên nhân class loader leak thường gặp

### 10.1. Thread do plugin tạo chưa được dừng

Plugin tạo background thread, executor, scheduler hoặc job queue. Sau khi host xóa plugin khỏi UI, worker vẫn chạy code plugin hoặc giữ callback/plugin instance. Worker có thể giữ runtime class/loader của plugin hoặc TCCL.

Cách phòng ngừa:

1. Thiết kế lifecycle `start()`, `stop()`/`close()` có quyền sở hữu rõ ràng.
2. Ngừng nhận task mới.
3. Gọi shutdown/cancel theo giao thức, dùng interruption đúng cách.
4. Chờ bounded timeout và ghi log task chưa hoàn tất.
5. Không dùng `Thread.stop()` để ép dừng.

Đừng viết plugin worker là busy loop không bao giờ dừng rồi hy vọng GC tự giải quyết.

### 10.2. Thread context class loader không được restore

Một thread host sống lâu có thể thay đổi context loader để chạy dịch vụ plugin:

~~~java
Thread current = Thread.currentThread();
ClassLoader previous = current.getContextClassLoader();

try {
    current.setContextClassLoader(pluginLoader);
    // Gọi plugin/service discovery phù hợp
} finally {
    current.setContextClassLoader(previous);
}
~~~

Đây là **mảnh minh họa**: `pluginLoader` được tạo ở nơi khác. Nếu không restore trong `finally`, thread host có thể giữ loader phiên cũ rất lâu.

Tuy nhiên, restore TCCL **chưa đủ** nếu host vẫn giữ `Class<?>`, plugin instance, proxy hoặc registry entry. Đây chỉ là một nhánh trong checklist.

### 10.3. ThreadLocal trong thread pool host

Thread pool thường tái sử dụng worker lâu dài. Nếu một `ThreadLocal` trên host worker giữ object thuộc class plugin và plugin không gọi `remove()`, loader có thể còn reachable từ thread pool.

Ngay cả khi implementation dùng **weak keys** cho `ThreadLocalMap`, value vẫn có thể bị giữ tới lúc map dọn các stale entries. Không dùng “ThreadLocal key weak” như lời hứa garbage collector tự giải phóng object plugin ngay.

Thực hành tốt: set context trong một scope với `try/finally`, gọi `remove()` khi context không còn cần, và không để queued tasks hoặc MDC/logging context giữ object plugin qua nhiều request.

### 10.4. Cache, service registry, listener, MBean, driver

Nguồn root phổ biến:

- `static Map<String,Object>` do host class giữ plugin object hoặc class metadata.
- Event bus giữ listener được tạo từ class plugin.
- Service locator/DI container giữ singleton plugin sau khi disable.
- Executor queue giữ `Runnable` hoặc lambda capture của plugin.
- Logging handler hoặc callback vẫn được đăng ký.
- MBeanServer giữ MBean do plugin đăng ký.
- JDBC/service registry hoặc thư viện native giữ driver/handle theo cơ chế riêng.
- Một cache reflection giữ `Class<?>`, `Method`, `Field`, `Constructor` của thế hệ plugin cũ.
- JNI global reference hoặc framework runtime có reference đến class/plugin object.

Không xóa bừa tất cả cache: tìm **owner và registration API**, rồi unregister từng resource tại thời điểm stop. Cùng một class loader có thể bị giữ từ nhiều nhánh độc lập; cần xử lý **tất cả retaining paths** có ý nghĩa.

### 10.5. Static field và chu trình tham chiếu

Static field trong một class **do plugin loader định nghĩa** có thể trỏ tới object plugin hoặc loader, tạo cycle. Nếu toàn bộ cycle không còn reachable từ roots, tracing GC vẫn có thể thu hồi.

Ngược lại, `HostRegistry.staticMap -> PluginObject -> PluginClass -> PluginLoader` xuất phát từ một class host sống lâu là retention thật. Khi reload, phải dọn **bản đăng ký của phiên cũ**, không chỉ gán null cho một biến cục bộ.

## 11. Thiết kế hot-reload theo từng phiên loader

Với plugin có thể nâng cấp khi ứng dụng đang chạy, một cấu trúc phổ biến là:

~~~text
App loader / shared API loader
  ├── Plugin (interface)
  ├── PluginContext
  └── PluginManager

PluginLoader v1
  ├── PluginImplementation v1
  └── dependencies riêng v1

PluginLoader v2
  ├── PluginImplementation v2
  └── dependencies riêng v2
~~~

**Vì sao API phải ở loader chung?** Nếu host và plugin đều tự define interface `Plugin` bằng hai defining loaders khác nhau, chúng là hai runtime classes khác nhau dù tên giống; `instanceof Plugin` hoặc cast có thể thất bại.

### Quy trình thay phiên an toàn

1. Tạo v2 loader và chuẩn bị binary/dependencies.
2. Xác nhận v2 có thể khởi tạo và trả lời các health checks cần thiết.
3. Ngăn request mới tới v1; để v1 **drain** các task/request đã nhận.
4. Khi v1 không còn phục vụ, gọi lifecycle `stop/close`, hủy scheduler/timer, đóng network/database/file resources.
5. Unregister mọi callback/listener/MBean/registry/cache có giữ v1.
6. Dọn TCCL, ThreadLocals, queues, retained class/method/instance references trong host.
7. Đóng loader v1 nếu nó là `URLClassLoader` để đóng các JAR/resource tương ứng.
8. Bỏ những reference cuối cùng do host sở hữu tới v1.
9. Theo dõi loader version và class-unload events **sau này**; không khẳng định `stop()` đã làm class unload đồng bộ.

Cần giữ nguyên tính nhất quán nghiệp vụ: đừng close loader v1 khi request v1 vẫn cần load class/resource mới. Đóng file handle sớm không nhất thiết cắt method đang chạy, nhưng có thể làm những thao tác tải dependency/resource sau đó bị lỗi.

### Không define lại cùng named class trong cùng loader

Một loader bình thường không phải “bộ nhớ từ điển” cho phép tùy tiện ghi đè definition của named class đã define bằng bytecode khác. Định nghĩa lại cùng binary name trong cùng loader bằng đường define thông thường có thể dẫn tới `LinkageError`. Java instrumentation/hotswap là cơ chế riêng với những giới hạn nhất định.

Để hot-reload thế hệ plugin, dùng **new defining loader** và quản lý đồng thời các object phiên cũ/mới trong giai đoạn draining.

## 12. Một số ngoại lệ và mở rộng JVM nâng cao

### Hidden classes

`MethodHandles.Lookup.defineHiddenClass` cho phép định nghĩa kiểu runtime chuyên dụng cho framework/lambda/proxy. Hidden classes có những quy tắc đặc biệt về định danh, khả năng tìm theo tên và **strong/weak reachability**.

Hidden class với cơ chế weak reachability có thể đủ điều kiện unload theo reachability riêng của class đó, **không nhất thiết phải chờ defining loader có thể được thu gom giống named class thông thường**. Vì thế câu “mọi class trong JVM chỉ được unload khi cả loader chết” là quá rộng nếu bao gồm hidden classes.

### Lambda và bytecode sinh động

Lambda hoặc framework-generated code không nhất thiết tương ứng một tệp `.class` có trong JAR. Một số JVM dùng hidden classes hoặc phương thức runtime khác. Không dùng số file `.class` trên đĩa để tính chính xác số runtime classes đã load/unload.

### Native handles và reflection

Một `Class<?>` hoặc `java.lang.reflect.Method` có thể giữ class/loader theo quan hệ runtime; `MethodHandle`, proxy, JNI refs có thể thêm retaining paths. Các cấu trúc JVM nội bộ không nhất thiết hiển thị hoàn toàn bằng một Java heap object thông thường, nên khi cần chẩn đoán sâu phải phối hợp tool của JVM với heap analysis.

## 13. Kiểm thử unload đúng cách

Một bài test integration cho hot reload nên đo **nhiều chu kỳ** và **sự hội tụ** thay vì một deadline dựa trên một lần `System.gc()`.

### Các bước

1. Tạo loader **mới cho mỗi phiên** và ghi ID/version của loader.
2. Load, chạy một tập request nhỏ và xác nhận đầu ra.
3. Shutdown plugin theo lifecycle, unregister, đóng I/O, dừng thread pool.
4. Bỏ mọi references do test harness hoặc host giữ tới loader, class và plugin objects.
5. Theo dõi `WeakReference<ClassLoader>`/`ReferenceQueue` mà không vô tình giữ một strong reference trong code test.
6. Nếu cần, dùng GC pressure ở môi trường kiểm thử với hạn mức an toàn; không dùng vòng lặp `System.gc()` như lời hứa quyết định.
7. Đối chiếu class-unload logging, class-loader stats và heap retaining paths.
8. So sánh Metaspace/class count và các chỉ số memory **qua nhiều chu kỳ**, không từ một snapshot đơn lẻ.

**Phân loại kết quả:**

- **Observed unloading:** runtime log thực sự ghi những class version cũ đã unload.
- **Loader retained:** có đường strong reference từ root tới loader hoặc đối tượng dẫn tới nó sau khi plugin đã stop.
- **Inconclusive:** `WeakReference.get()` vẫn khác null hoặc committed memory chưa giảm sau một lần GC. Đây là quan sát tạm thời, không đủ khẳng định leak.

Dù có chứng cứ unload, bài test vẫn phải xác nhận **resources đã đóng** và không còn background work trái phép. Unloading không thay thế nghĩa vụ cleanup của plugin.

## 14. Các tình huống chẩn đoán thường gặp

### Tình huống A: Reload 20 lần, Metaspace tăng liên tục

Các khả năng gồm: đúng là có nhiều class generation mới; loader cũ bị host static cache giữ; thread plugin chưa dừng; JVM chưa unload; hoặc committed capacity chưa trả OS. Hãy tìm retaining path và log unload trước khi đổi collector/tăng heap.

### Tình huống B: Không còn instance, nhưng loader vẫn sống

Kiểm tra `Class<?>`, reflection caches, thread context loader, global registry, lambda/callback, scheduler queue và thread-local values. Class không cần instance để còn sống.

### Tình huống C: `ClassCastException: Foo cannot be cast to Foo`

Có thể có **hai runtime Foo khác nhau** do hai defining loaders. Quan sát `obj.getClass()` và `obj.getClass().getClassLoader()`, kiểm tra shared API loader, không so bằng class name đơn thuần.

### Tình huống D: Loader đã `close()` mà method plugin vẫn chạy

Đúng: close không phải interrupt hay unload. Host phải dừng task theo lifecycle riêng trước khi đóng loader và bỏ references.

### Tình huống E: `System.gc()` không sinh class-unload event

Chưa kết luận được: loader có thể còn root path hoặc JVM chưa làm class unloading. Kiểm tra log và heap. Đừng dùng `finalize()` để cố quan sát class unloading.

### Tình huống F: Một ứng dụng mới chỉ gọi static method mà class đã initialized

Static method có thể kích hoạt class initialization mà không tạo instance. Ngược lại, class có thể đã loaded mà chưa initialized. **Loading, initialization, object GC, class unloading** là bốn khái niệm riêng.

## 15. Checklist vận hành plugin unload-safe

- **Ownership:** mỗi plugin version có loader/context và danh sách resource/callback do nó sở hữu.
- **Start:** ghi version, binary path, class-loader identity và dependency boundary.
- **Stop:** chặn việc mới, drain các tác vụ cũ có giới hạn, đóng network/file/DB/executor.
- **Unregister:** xóa plugin khỏi host registries, services, MBeans, listeners, caches và scheduling.
- **Context:** restore TCCL, remove ThreadLocal, clear queued callbacks.
- **Loader:** đóng `URLClassLoader`/resource quản lý theo API đúng thời điểm.
- **References:** đảm bảo host không giữ Plugin object, Class, Method, loader version cũ.
- **Verification:** theo dõi class load/unload log và retained loader references; đánh giá memory trên nhiều chu kỳ.
- **Failure handling:** nếu loader còn sống, đọc heap retaining paths từ root; không chỉ thêm `System.gc()`.

Quy trình này giúp ứng dụng quản lý tốt **resource và an toàn nghiệp vụ** ngay cả khi JVM quyết định trì hoãn class unloading.

## 16. Câu hỏi tự kiểm tra

1. Không còn instance của `Plugin` có bảo đảm class unload ngay không? **Không**, defining loader có thể còn reachable.
2. Với named classes bình thường, điều kiện trung tâm để class có thể unload là gì? **Defining class loader có thể được GC thu hồi**.
3. `URLClassLoader.close()` là lệnh unload tất cả class nó define đúng không? **Sai**.
4. Hai class cùng binary name do hai loader define là một kiểu JVM đúng không? **Sai**.
5. Một app static cache giữ plugin object cũ có thể giữ loader cũ không? **Có**.
6. `System.gc()` là deadline đảm bảo class unload không? **Không**.
7. Class-loader leak thường chứng minh bằng gì? **Strong retaining path từ GC root**.
8. Vì sao TCCL phải được restore trên thread host? **Tránh giữ loader phiên cũ ngoài ý muốn**.
9. Một reference cycle bên trong plugin chắc chắn leak không? **Không**, nếu không reachable từ root.
10. `WeakReference<ClassLoader>.get() != null` sau GC có chứng minh leak không? **Không**.
11. Vì sao Metaspace committed không giảm không đủ kết luận class không unload? **JVM có thể giữ capacity để tái sử dụng**.
12. Class do bootstrap loader define có vòng đời như plugin child loader không? **Không**.
13. Nên hot-reload nhiều phiên cùng một named class trong cùng loader không? **Không phải chiến lược thông thường; dùng loader theo phiên**.
14. Có nên để GC tự dọn socket, executor, DB connections của plugin không? **Không**, đóng chủ động.
15. Hidden classes có thể có quy tắc unload đặc biệt không? **Có**, không áp dụng mọi mệnh đề của named class.
16. Nếu `Foo cannot be cast to Foo`, kiểm tra gì? **Defining loaders và runtime class identity**.

## 17. Tài liệu chuẩn

- **JVMS Java SE 17, §5.3 Creation and Loading**, class identity và unloading: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3
- **JVMS §5.4 Linking**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.4
- **JVMS §5.5 Initialization**: https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.5
- **JLS Java SE 17, Chapter 12 Execution**: https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html
- **`ClassLoader` Java SE 17 API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
- **`URLClassLoader` Java SE 17 API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html
- **`WeakReference` Java SE 17 API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html
- **`MethodHandles.Lookup.defineHiddenClass` Java SE 17 API**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html

**Kết luận kỹ thuật:** class unloading không phải lời gọi trực tiếp mà là **hệ quả có thể xảy ra của GC và chính sách JVM**. Với named classes thông thường, defining loader phải đủ điều kiện được GC thu hồi. Trong hệ plugin/hot-reload, việc quan trọng nhất là **quản lý lifecycle có chủ đích: stop công việc → unregister → đóng resources → bỏ strong references → để JVM quyết định GC/unload**. Quan sát bằng class-unload log và retaining paths; không coi `System.gc()` hoặc `URLClassLoader.close()` là cam kết unload tức thời.
