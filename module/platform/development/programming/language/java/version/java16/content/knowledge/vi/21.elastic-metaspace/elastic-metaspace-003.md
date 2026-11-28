# Class loader quyết định vòng đời của metadata như thế nào

**Module:** JAVA_VERSION_JAVA16  
**Chương:** Elastic Metaspace  
**Áp dụng:** Java 16 trở lên; mô hình class loading, class unloading và quản lý Metaspace vẫn áp dụng trong các JDK hiện đại.

Mỗi class Java được định nghĩa bởi một class loader. Class loader không chỉ quyết định JVM tìm bytecode ở đâu; nó còn gắn với danh tính của class và vòng đời của metadata mà JVM tạo ra khi nạp class.

Từ Java 8, metadata của class được lưu trong native memory gọi là **Metaspace** thay cho PermGen. Java 16 tiếp tục cải thiện cách quản lý vùng nhớ này qua JEP 387 — Elastic Metaspace. Khi một class loader không còn được tham chiếu và đủ điều kiện thu hồi, JVM có thể unload các class do loader đó định nghĩa; metadata tương ứng được trả lại cho bộ quản lý Metaspace. Những vùng nhớ đã giải phóng có thể được tái sử dụng hoặc uncommit để trả lại cho hệ điều hành.

Vì vậy, muốn hiểu Metaspace tăng hoặc giảm, cần hiểu vòng đời class loader trước:

```text
Tạo class loader
      |
      v
Load / link / initialize các class
      |
      v
Metadata được cấp phát trong Metaspace
      |
      v
Ứng dụng và framework giữ các tham chiếu tới loader/class/object
      |
      v
Các tham chiếu tới loader được giải phóng
      |
      v
Loader đủ điều kiện được garbage collector thu hồi
      |
      v
Các class do loader định nghĩa được unload
      |
      v
Metadata trở lại bộ quản lý Metaspace
      |
      v
Vùng nhớ có thể tái sử dụng hoặc uncommit
```

## 1. Metadata của class nằm ở đâu?

JVM cần lưu thông tin để thực thi class: cấu trúc class, thông tin method, runtime constant pool, metadata phục vụ linking và các thông tin nội bộ khác. Trên HotSpot, phần metadata này được quản lý trong Metaspace, một vùng native memory.

Phân biệt các thành phần:

| Thành phần | Vị trí khái quát | Vai trò |
| --- | --- | --- |
| Class metadata | Native memory — Metaspace | Mô tả class và dữ liệu runtime phục vụ JVM |
| Đối tượng `Class<?>` (class mirror) | Java heap | Đại diện class trong Java API |
| Instance của class | Java heap | Dữ liệu object của ứng dụng |
| Đối tượng `ClassLoader` | Java heap | Đại diện loader và có thể được ứng dụng tham chiếu |
| Stack frame, local variable | Thread stack | Trạng thái thực thi method |

Không nên hiểu rằng mọi dữ liệu liên quan đến class đều nằm trong Metaspace. Ví dụ, object `Class<?>`, instance và nhiều dữ liệu ứng dụng vẫn nằm trên heap; Metaspace chứa metadata native của JVM.

## 2. Class loader gắn metadata với vòng đời như thế nào?

Khi class loader định nghĩa một class, JVM tạo metadata gắn với **defining class loader** đó. Loader định nghĩa class là một phần của danh tính kiểu tại runtime: hai class có cùng tên đầy đủ nhưng được định nghĩa bởi hai loader khác nhau vẫn là hai kiểu khác nhau.

Ví dụ:

```java
Class<?> first = Class.forName(
    "com.acme.plugin.Message",
    true,
    pluginLoaderA
);

Class<?> second = Class.forName(
    "com.acme.plugin.Message",
    true,
    pluginLoaderB
);

System.out.println(first.getName().equals(second.getName())); // true
System.out.println(first == second);                          // false
```

Nếu hai loader thực sự tự định nghĩa class `com.acme.plugin.Message`, JVM xem chúng là hai kiểu riêng. Chúng có metadata và trạng thái class riêng, và vòng đời của mỗi nhóm class gắn với defining loader tương ứng.

Lưu ý: parent delegation có thể khiến loader con yêu cầu parent nạp class. Trong trường hợp đó, defining loader là parent; class không thuộc vòng đời unload của loader con.

## 3. Điều kiện để class được unload

Theo quy tắc của JVM, class chỉ có thể được unload khi defining class loader của nó có thể được garbage collector thu hồi. Điều này có nghĩa:

- Không còn đường tham chiếu mạnh từ GC roots tới class loader.
- Không còn object, class, thread, cache hoặc cấu trúc ứng dụng giữ loader sống.
- Collector/runtime thực hiện một chu kỳ có xử lý class unloading.

Việc loader trở nên unreachable chỉ làm cho nó **đủ điều kiện** được thu hồi. Class không bị unload ngay tại thời điểm tham chiếu cuối cùng biến mất. Thời điểm thực tế phụ thuộc hoạt động GC và cấu hình collector.

Các class do bootstrap loader định nghĩa thường có vòng đời của JVM và không phải nhóm class ứng dụng có thể unload bằng cách bỏ một custom loader.

Không có API Java thông thường để yêu cầu unload một class riêng lẻ. JVM quản lý class unloading theo defining loader; ứng dụng cần quản lý vòng đời loader và các tham chiếu tới nó.

## 4. Tạo và kết thúc một vòng đời plugin

Một ứng dụng plugin có thể tạo loader riêng cho từng plugin. Interface mà ứng dụng và plugin cùng dùng nên được nạp bởi parent loader để hai phía nhìn thấy cùng một kiểu API:

```java
public interface Plugin {
    void start() throws Exception;
    void stop() throws Exception;
}
```

Ví dụ quản lý một plugin bằng `URLClassLoader`:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;

static void runPlugin(Path pluginJar) throws Exception {
    ClassLoader previous =
        Thread.currentThread().getContextClassLoader();

    URL[] urls = { pluginJar.toUri().toURL() };
    URLClassLoader pluginLoader = new URLClassLoader(
        urls,
        Plugin.class.getClassLoader()
    );

    try {
        Thread.currentThread().setContextClassLoader(pluginLoader);

        Class<?> pluginType = Class.forName(
            "com.acme.plugin.WeatherPlugin",
            true,
            pluginLoader
        );

        Plugin plugin =
            (Plugin) pluginType.getDeclaredConstructor().newInstance();

        try {
            plugin.start();
            // Ứng dụng sử dụng plugin trong thời gian đã định.
        } finally {
            plugin.stop();
        }
    } finally {
        Thread.currentThread().setContextClassLoader(previous);
        pluginLoader.close();
    }
}
```

Khi phương thức kết thúc, các biến cục bộ không còn được giữ bởi stack frame đang hoạt động. Ví dụ này minh họa việc đóng tài nguyên và khôi phục context class loader; ứng dụng thật còn phải dừng thread, executor, listener và gỡ đăng ký callback do plugin tạo ra.

Đóng `URLClassLoader` không bảo đảm class được unload ngay. Nếu một cache, thread hoặc object ở nơi khác vẫn tham chiếu tới loader hoặc class do nó định nghĩa, loader vẫn sống.

## 5. close() không đồng nghĩa với class unloading

`URLClassLoader.close()` có mục đích quản lý tài nguyên:

- Đóng các JAR/file đã mở bởi loader.
- Ngăn loader tải thêm class hoặc resource mới từ các URL sau khi đóng.
- Không xóa những class đã được định nghĩa.
- Không ép garbage collector thu hồi loader.

Các class đã load vẫn có thể được sử dụng khi loader còn được tham chiếu. Metadata vẫn cần tồn tại để JVM thực thi các method của những class đó.

Phân biệt ba thao tác:

| Thao tác | Tác dụng |
| --- | --- |
| `URLClassLoader.close()` | Giải phóng tài nguyên I/O do loader mở và ngừng tải mới từ URL |
| Giải phóng mọi tham chiếu tới loader | Làm loader có thể trở thành unreachable |
| Garbage collection có class unloading | Thu hồi loader và unload class khi đủ điều kiện |

Không dùng `close()` như một phép đo xác nhận Metaspace đã giảm. Cần quan sát class unloading và thống kê class loader sau khi hệ thống chạy qua các chu kỳ phù hợp.

## 6. Những tham chiếu thường khiến class loader không thể thu hồi

Lỗi class loader leak thường xuất hiện khi một thành phần có vòng đời dài hơn plugin giữ tham chiếu tới object hoặc class của plugin.

| Nguồn giữ tham chiếu | Ví dụ | Cách xử lý khi dừng plugin |
| --- | --- | --- |
| Static cache ở parent/application loader | Map lưu `Class<?>`, `Method`, object plugin | Xóa entry do plugin đăng ký |
| Thread đang chạy code plugin | Thread được tạo bởi plugin nhưng không kết thúc | Dừng thread có kiểm soát và chờ kết thúc |
| Thread context class loader | Worker thread giữ TCCL trỏ tới plugin loader | Khôi phục TCCL hoặc kết thúc worker thread |
| `ThreadLocal` | Thread pool dùng chung giữ object plugin trong ThreadLocal | Gọi `remove()` trên đúng thread hoặc kết thúc thread |
| Listener/callback registry | Event bus hoặc scheduler giữ lambda/listener của plugin | Hủy đăng ký trước khi bỏ loader |
| Reflection/method-handle cache | Cache toàn cục giữ `Class`, `Method`, `MethodHandle` | Xóa cache entry gắn với plugin |
| JNI/native global reference | Native code giữ reference tới object Java | Giải phóng global reference theo hợp đồng native |
| Stack frame còn hoạt động | Method plugin vẫn đang chạy trên thread | Chờ tác vụ hoàn tất và thread thoát khỏi code plugin |

Đặc biệt chú ý thread pool dùng chung. Một worker thread có thể sống lâu sau khi plugin dừng; nếu TCCL hoặc ThreadLocal của worker vẫn giữ class loader, metadata không thể được thu hồi.

## 7. Parent loader và child loader: hướng tham chiếu rất quan trọng

Thông thường, class loader con giữ tham chiếu tới parent loader để thực hiện delegation. Điều đó không tự động có nghĩa parent loader giữ tham chiếu tới mọi child loader.

Tuy nhiên, ứng dụng có thể vô tình tạo tham chiếu ngược:

```text
Parent/application loader
       |
       | static registry / cache
       v
Plugin object hoặc Class<?>
       |
       v
Child/plugin loader
```

Khi parent loader giữ plugin object hoặc `Class<?>`, child loader vẫn reachable. Một registry trong application loader vì vậy có thể ngăn plugin unload dù ứng dụng đã gọi `URLClassLoader.close()`.

Thiết kế registry nên hỗ trợ unregister theo plugin identity và không giữ class/object của plugin lâu hơn vòng đời plugin. Dùng `WeakReference` không phải cách thay thế cho quy trình shutdown đúng; weak reference cũng không giải quyết thread đang chạy hoặc native reference.

## 8. Module không thay thế defining class loader

JPMS module và class loader là hai khái niệm khác nhau:

- Module xác định ranh giới dependency, readability, exports và opens.
- Class loader định nghĩa class và gắn class với một namespace kiểu tại runtime.
- Nhiều module có thể được định nghĩa trong cùng một class loader.
- Module layer mới không đồng nghĩa mọi class trong layer có một class loader riêng; cách tạo layer quyết định loader được dùng.

Vì vậy, không thể suy ra metadata sẽ unload chỉ vì một `ModuleLayer` hoặc một module không còn được ứng dụng sử dụng theo logic nghiệp vụ. Cần xem defining loader của các class trong layer và toàn bộ tham chiếu tới loader đó.

## 9. Elastic Metaspace cải thiện việc thu hồi bộ nhớ ra sao?

JEP 387 đưa Elastic Metaspace vào Java 16 để làm cho việc cấp phát và thu hồi native memory của Metaspace linh hoạt hơn. Mục tiêu chính là giảm footprint và trả lại vùng nhớ không còn cần thiết cho hệ điều hành hiệu quả hơn.

Ở mức khái quát:

1. Class loader định nghĩa class, JVM cấp phát metadata trong Metaspace.
2. Khi loader được thu hồi và class unloading diễn ra, các khối metadata tương ứng trở thành vùng trống trong bộ quản lý Metaspace.
3. Bộ quản lý có thể tái sử dụng vùng trống cho class metadata mới.
4. Những phần đã commit nhưng không cần giữ lại có thể được uncommit và trả lại cho hệ điều hành theo chính sách quản lý bộ nhớ.

Điểm quan trọng: **class unloading và uncommit là hai bước khác nhau**. Unload class giải phóng metadata về mặt logic; Elastic Metaspace quản lý các chunk trống và quyết định khi nào có thể trả các trang native memory không còn cần thiết.

Không nên kỳ vọng RSS của process giảm ngay sau mỗi lần unload. JVM có thể giữ một phần vùng đã commit để tái sử dụng, hoặc hệ điều hành cập nhật số liệu resident memory theo thời điểm khác. Metaspace đã giải phóng có thể hữu ích cho class loading tiếp theo mà không cần xin thêm native memory.

## 10. Phân biệt used, committed và reserved

Khi đọc số liệu Metaspace, cần hiểu các khái niệm:

| Khái niệm | Ý nghĩa khái quát |
| --- | --- |
| Used | Phần bộ nhớ đang chứa metadata đã cấp phát |
| Committed | Phần native memory JVM đã commit để có thể sử dụng |
| Reserved | Phần không gian địa chỉ đã reserve cho mục đích quản lý vùng nhớ |

Các con số này không đồng nghĩa với nhau. `Used` giảm sau class unloading nhưng `Committed` có thể giữ nguyên một thời gian vì JVM muốn tái sử dụng vùng nhớ. `Reserved` cũng không phải lượng RAM vật lý đang tiêu thụ.

Khi đánh giá Elastic Metaspace, quan sát xu hướng qua nhiều chu kỳ tải/dỡ plugin hoặc redeploy, không kết luận chỉ từ một snapshot.

## 11. Ví dụ một class loader leak trong ứng dụng plugin

Giả sử ứng dụng có registry toàn cục:

```java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

final class PluginRegistry {
    static final Map<String, Object> INSTANCES =
        new ConcurrentHashMap<>();

    static void register(String id, Object plugin) {
        INSTANCES.put(id, plugin);
    }

    static void unregister(String id) {
        INSTANCES.remove(id);
    }
}
```

Nếu plugin đăng ký instance nhưng lúc dừng chỉ đóng URLClassLoader mà không gọi `unregister`, registry vẫn giữ instance. Instance có class được định nghĩa bởi plugin loader; do đó loader và metadata của các class plugin vẫn reachable.

Quy trình shutdown phải gỡ registry trước khi bỏ loader:

```java
static void stopPlugin(String id, Plugin plugin) throws Exception {
    try {
        plugin.stop();
    } finally {
        PluginRegistry.unregister(id);
    }
}
```

Đây chỉ là một phần của quy trình. Cần đồng thời dừng worker thread, scheduler, callback, TCCL và các cache liên quan. Nếu có nhiều loại tài nguyên, đóng chúng theo thứ tự để plugin không đăng ký thêm công việc mới trong lúc shutdown.

## 12. Kiểm tra class unloading và Metaspace

Khi nghi ngờ class loader leak, hãy đo trước và sau các chu kỳ load/unload trong cùng workload.

### Ghi log class load/unload

Unified logging là cách hiện hành để quan sát sự kiện:

```sh
java -Xlog:class+load=info,class+unload=info -jar application.jar
```

Log class unload giúp xác nhận JVM có unload class. Không thấy log ngay sau khi đóng loader không chứng minh leak; loader có thể chưa unreachable hoặc chưa có GC cycle xử lý class unloading.

### Xem thống kê class loader

Với tiến trình đang chạy:

```sh
jcmd <pid> VM.classloader_stats
```

Lệnh này cung cấp thống kê theo class loader và dữ liệu liên quan đến metadata. So sánh số loader, số class và kích thước Metaspace qua các lần triển khai plugin để tìm xu hướng tăng bất thường.

### Xem native memory

Nếu cần phân tích native memory chi tiết, bật Native Memory Tracking khi khởi chạy JVM:

```sh
java -XX:NativeMemoryTracking=summary -jar application.jar
```

Sau đó lấy summary:

```sh
jcmd <pid> VM.native_memory summary
```

Native Memory Tracking có overhead và phải được bật khi JVM khởi động. Số liệu NMT giúp xem nhóm Class/Metaspace ở mức native memory; kết hợp với class loader stats và log unload để xác định nguyên nhân.

## 13. Khi nào Metaspace tăng là bình thường?

Metaspace tăng không tự động có nghĩa memory leak. Các trường hợp bình thường:

- Ứng dụng vừa nạp thêm nhiều class lần đầu.
- Framework tạo proxy hoặc class động trong giai đoạn startup.
- Nhiều plugin đang hoạt động đồng thời theo thiết kế.
- JVM giữ vùng committed để tái sử dụng sau khi class unload.

Dấu hiệu đáng điều tra:

- Số class loader tăng sau mỗi lần redeploy nhưng không giảm hoặc ổn định trở lại.
- Số class do loader ứng dụng/plugin định nghĩa tăng không giới hạn.
- Class unloading không xảy ra dù loader được cho là đã dừng và không còn được sử dụng.
- `Used` của Metaspace tăng đều qua các chu kỳ có cùng tải, không quay về vùng ổn định.
- Xuất hiện `OutOfMemoryError: Metaspace` khi ứng dụng tiếp tục nạp class.

Khi điều tra, kiểm tra reference path tới loader trong heap dump hoặc profiler. Thống kê Metaspace cho biết xu hướng; heap analysis thường giúp tìm object/cache/thread đang giữ loader.

## 14. Có nên đặt MaxMetaspaceSize ngay từ đầu?

`-XX:MaxMetaspaceSize` đặt giới hạn cho Metaspace. Đây là giới hạn tài nguyên có thể hữu ích trong môi trường có memory budget rõ, nhưng đặt quá thấp có thể làm ứng dụng lỗi khi tải class hợp lệ.

Không dùng việc tăng `MaxMetaspaceSize` như cách chữa class loader leak. Nếu mỗi lần redeploy tạo thêm loader không thể thu hồi, tăng giới hạn chỉ trì hoãn `OutOfMemoryError: Metaspace`.

Trước khi điều chỉnh:

1. Đo số class loader và số class qua workload đại diện.
2. Xác minh class unloading có diễn ra.
3. Tìm các tham chiếu giữ loader nếu số loader tăng liên tục.
4. Đo `Used`, `Committed` và native memory sau nhiều chu kỳ.
5. Chỉ đặt giới hạn sau khi hiểu nhu cầu bình thường và headroom của ứng dụng.

Không sử dụng các hướng dẫn PermGen hoặc tùy chọn GC cũ để điều chỉnh Metaspace hiện đại. PermGen đã bị loại bỏ từ Java 8; Elastic Metaspace là cơ chế hiện hành từ Java 16.

## 15. Những nhầm lẫn cần tránh

| Nhận định | Đúng hay sai? | Giải thích |
| --- | --- | --- |
| Metadata class nằm hoàn toàn trên Java heap. | **Sai** | HotSpot quản lý class metadata trong native Metaspace; `Class<?>` mirror và object ứng dụng nằm trên heap. |
| Class cùng tên luôn là cùng một kiểu. | **Sai** | Defining class loader là một phần của type identity. |
| Gọi `URLClassLoader.close()` sẽ unload toàn bộ class. | **Sai** | `close()` quản lý tài nguyên I/O, không ép GC thu hồi loader. |
| Loader unreachable có nghĩa class unload ngay lập tức. | **Sai** | Loader đủ điều kiện được thu hồi; class unloading phụ thuộc GC cycle. |
| Parent delegation khiến parent luôn giữ mọi child loader. | **Sai** | Hướng tham chiếu thông thường là child tới parent; registry/cache do ứng dụng tạo có thể giữ child. |
| Thread context class loader có thể giữ plugin loader sống. | **Đúng** | Thread sống lâu giữ TCCL trỏ tới plugin loader là nguồn leak phổ biến. |
| Class unloading và uncommit Metaspace là cùng một thao tác. | **Sai** | Unload giải phóng metadata; Elastic Metaspace quản lý tái sử dụng và uncommit các vùng native trống. |
| RSS phải giảm ngay khi class unload. | **Sai** | JVM có thể giữ vùng committed để tái sử dụng. |
| Metaspace tăng trong startup luôn là leak. | **Sai** | Framework và ứng dụng có thể nạp thêm class hợp lệ. |
| Tăng `MaxMetaspaceSize` sửa được class loader leak. | **Sai** | Nó chỉ tăng giới hạn trước khi lỗi xuất hiện. |

## 16. Checklist quản lý vòng đời class loader

1. Class loader nào thực sự định nghĩa class của plugin/framework?
2. Có tạo class loader mới cho mỗi lần reload và có giới hạn số loader đồng thời không?
3. Plugin đã dừng thread, executor, scheduler và callback chưa?
4. Thread context class loader đã được khôi phục hoặc worker thread đã kết thúc chưa?
5. `ThreadLocal` trên thread dùng chung đã được xóa chưa?
6. Registry/cache ở parent loader đã bỏ object, `Class`, `Method` và `MethodHandle` của plugin chưa?
7. Đã đóng `URLClassLoader` để giải phóng tài nguyên I/O chưa?
8. Đã loại bỏ mọi tham chiếu mạnh tới loader trước khi mong class unload chưa?
9. Có theo dõi class unloading bằng unified logging không?
10. Có so sánh `VM.classloader_stats` qua các chu kỳ load/unload không?
11. Nếu cần native memory detail, NMT đã được bật từ lúc khởi động chưa?
12. Có phân biệt `Used`, `Committed`, `Reserved` và RSS không?
13. Đã kiểm tra reference path tới loader khi Metaspace tăng liên tục chưa?

**Ghi nhớ:** Defining class loader quyết định nhóm class và metadata có thể được thu hồi cùng nhau. Khi loader không còn reachable, JVM có thể unload các class do nó định nghĩa trong một chu kỳ GC phù hợp. `URLClassLoader.close()` chỉ đóng tài nguyên loader mở, không ép unload. Elastic Metaspace từ Java 16 cải thiện khả năng tái sử dụng và uncommit native memory đã trống; vì vậy cần phân biệt class unloading, Metaspace used/committed và RSS. Khi Metaspace tăng liên tục, hãy tìm tham chiếu giữ loader thay vì chỉ tăng giới hạn bộ nhớ.

## Tài liệu chính thức

- [JEP 387 — Elastic Metaspace, delivered in Java 16](https://openjdk.org/jeps/387).
- [Java Virtual Machine Specification — Section 5.3, Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-5.html#jvms-5.3).
- [Java Language Specification — Section 12.7, Unloading of Classes](https://docs.oracle.com/javase/specs/jls/se26/html/jls-12.html#jls-12.7).
- [Java SE 26 API — ClassLoader](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/ClassLoader.html).
- [Java SE 26 API — URLClassLoader.close()](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/net/URLClassLoader.html#close()).
- [Java SE 26 jcmd Tool — VM.classloader_stats and VM.native_memory](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html).
- [Java SE 26 java Launcher — Unified Logging and Native Memory Tracking options](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html).
