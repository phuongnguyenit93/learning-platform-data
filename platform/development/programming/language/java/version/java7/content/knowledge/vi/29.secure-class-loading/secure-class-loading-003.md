# Nạp lớp an toàn trong Java: Đóng loader và giới hạn thu hồi các lớp đã nạp

## 1. Bài toán thực tế và kết luận cần nhớ

Một ứng dụng Java đôi khi cần nạp thư viện/plugin từ JAR, chạy một phiên bản, cập nhật JAR và nạp phiên bản mới **mà không khởi động lại toàn bộ tiến trình**. Một `URLClassLoader` riêng cho mỗi phiên bản giúp tạo một không gian định nghĩa lớp độc lập. Tuy nhiên, chuyện “đóng loader”, “ngừng dùng lớp”, “xóa JAR”, “GC thu hồi ClassLoader” và “JVM unload lớp” **là những trạng thái khác nhau**.

Bài **“Đóng loader và giới hạn thu hồi các lớp đã nạp”** thuộc chủ đề **“Nạp lớp an toàn”** trong Java 7. Tài liệu chỉ sử dụng kiến thức **còn đúng với Java 17+**. Các điểm quan trọng:

- `URLClassLoader` implements `Closeable`: có thể đóng bằng `close()` hoặc `try-with-resources`.
- `URLClassLoader.close()` ngăn tiếp tục nạp **lớp/tài nguyên mới được chính loader đó định nghĩa** và đóng các file JAR/file mà nó đã mở, với xử lý lỗi `IOException`.
- `close()` **không unload ngay các `Class` đã được định nghĩa**, không hủy object instances và không khiến method của lớp đã nạp ngừng chạy.
- Sau `close()`, các lớp **đã nạp trước đó** và các lớp của **parent class loader** vẫn có thể truy cập, theo contract.
- Khi muốn JVM unload một lớp, **defining class loader của lớp phải có khả năng được GC thu hồi**; JVM *có thể* unload khi phù hợp nhưng không có API portable ép unload và không có thời hạn chắc chắn.
- Các tham chiếu từ application host tới `Class<?>`, instances, `Method`, `MethodHandle`, `ClassLoader`, Thread Context ClassLoader, threads, executors, ThreadLocal hoặc registries có thể giữ plugin sống.
- Tạo loader mới từ cùng JAR có thể sinh một `Class` **khác identity**, nhưng **không chứng minh** loader cũ đã được thu hồi.
- ClassLoader tạo ranh giới **namespace/type identity**, **không phải sandbox bảo mật** cho mã không đáng tin cậy.

**Một câu:** Đóng `URLClassLoader` giúp ngừng dùng nguồn nạp và giải phóng handles, còn **class unloading chỉ trở thành khả dĩ sau khi toàn bộ đường giữ loader và các lớp của nó từ GC roots biến mất**; GC/JVM mới quyết định lúc nào thực hiện.

## 2. Phân biệt năm khái niệm dễ nhầm

| Thuật ngữ | Ý nghĩa | Điều chưa được bảo đảm |
| --- | --- | --- |
| `URLClassLoader.close()` | Đóng loader về khả năng nạp mới từ chính nó và file handles mà nó quản lý | Lớp đã nạp biến mất |
| Ngừng task/plugin | Không còn request mới, workers của plugin dừng | Mọi strong reference đã được gỡ |
| GC eligibility của loader | Không còn đường strong reachability từ roots tới loader/nhóm lớp của nó | GC chạy ngay |
| Class unloading | JVM giải phóng metadata/lớp đã không còn cần đến theo quy tắc spec | Xảy ra đúng sau `close` hoặc `System.gc` |
| Đóng/xóa JAR | Giải phóng OS file handles do loader sở hữu rồi thao tác file | Thay thế mọi bản copy tài nguyên do code khác mở |

Đặc biệt, **xóa JAR thành công không chứng minh class unloading**. JVM có thể vẫn thực thi bytecode đã được nạp trước đó, ngay cả khi file JAR gốc đã được đóng hoặc xóa. Ngược lại, một JAR không xóa được có thể do stream hoặc process khác giữ mở, không tự chứng minh có một `Class<?>` đang được tham chiếu.

### 2.1. ClassLoader không phải một đối tượng “đóng lớp”

`java.lang.ClassLoader` là abstract class có cơ chế nạp lớp. Interface phổ quát của mọi `ClassLoader` **không có `close()`**. `URLClassLoader` cung cấp `close` vì nó quản lý classpath URL, JAR/file resources. Custom loader hoặc loader do framework/module layer quản lý có thể có resource lifecycle khác; **không cast/close tùy tiện system class loader**.

### 2.2. Metaspace là vùng cần giám sát

Trong JVM hiện đại (Java 17+), thông tin metadata lớp thường chiếm **Metaspace**, không phải PermGen của các JVM cũ. Một service nạp hàng nghìn phiên bản plugin mà không gỡ references có thể khiến số loaders/classes đang sống tăng, làm tăng áp lực bộ nhớ và gây lỗi liên quan metaspace.

Không dựa vào cài đặt PermGen đã lỗi thời. Chẩn đoán trên đúng JDK/runtime và cấu hình GC của ứng dụng thực tế.

## 3. `URLClassLoader.close()` làm gì theo Javadoc Java SE 17?

Phương thức:

```java
public void close() throws IOException
```

Được định nghĩa bởi `java.net.URLClassLoader` từ Java 7 và hiện còn dùng. Tóm tắt contract:

1. **Ngừng nạp lớp và resource mới do loader tự định nghĩa.**
2. Các lớp và tài nguyên do **parent delegation hierarchy** định nghĩa vẫn có thể truy cập.
3. Các lớp/tài nguyên **đã nạp từ trước** vẫn có thể truy cập theo contract.
4. Với `jar:` và `file:` URLs, `close` đóng các **file đã được loader mở** để phục vụ việc nạp.
5. Nếu thread khác đồng thời đang nạp lớp qua cùng loader lúc `close()` chạy, **kết quả lần nạp đó không được xác định** theo Javadoc. Vì vậy phải dừng admission/đợi in-flight operations trước khi close.
6. `close` cố gắng đóng các files, bắt `IOException` nội bộ; có thể ném một IOException và gắn những lỗi đóng bổ sung dưới dạng suppressed exceptions.
7. Gọi `close` trên loader đã đóng là no-op, nhưng **không vì thế được gọi lung tung khi threads khác còn chạy**.

Không có hứa hẹn nào rằng JVM sẽ unload ngay những classes trước đó khi `close()` trả về.

### 3.1. Ví dụ dùng `try-with-resources`

```java
URL jar = Path.of("plugins", "feature.jar").toUri().toURL();
try (URLClassLoader loader = new URLClassLoader(
        new URL[]{jar},
        ClassLoader.getSystemClassLoader())) {

    Class<?> type = Class.forName("plugin.Feature", true, loader);
    // Gọi plugin, sao chép dữ liệu kết quả về host-owned DTO.
}
// loader.close() được gọi kể cả khi code trong try có exception.
```

Đây là **snippet minh họa**, không độc lập: cần `import java.net.*`, `import java.nio.file.Path`, JAR/class tương ứng; method cần xử lý/khai báo checked exceptions. Nó còn bỏ qua việc dừng plugin nếu plugin tạo tasks chạy lâu hơn scope; chỉ thích hợp khi mọi công việc dùng loader **đã xong trước khi thoát try**.

### 3.2. Ví dụ đóng thủ công đúng ownership

```java
URLClassLoader loader = new URLClassLoader(urls, parent);
try {
    // Nạp và sử dụng plugin một cách có kiểm soát.
} finally {
    loader.close();
}
```

Đây là snippet với `urls` và `parent` do ứng dụng định nghĩa. Đừng cho plugin sử dụng loader ở thread khác trong khi scope finally bắt đầu đóng. `close()` có thể ném `IOException`, nên phải thiết kế logging/error reporting thích hợp.

### 3.3. `getResourceAsStream` và file handles

`URLClassLoader` có thể mở JAR/files khi `findClass`, `getResource` hoặc `getResourceAsStream`. Dùng `try (InputStream in = loader.getResourceAsStream(...))` để đóng stream do caller sở hữu **ngay khi dùng xong**; `URLClassLoader.close` quản lý handles do loader mở nhưng không thay trách nhiệm đóng mọi tài nguyên do code ngoài tự mở từ URL/path.

Không giả định `URL` đã được lưu trước khi loader đóng sẽ không thể mở bằng một API khác; một `URL` đơn thuần có thể được ứng dụng khác tự mở file/connection độc lập. **Boundary là tài nguyên do URLClassLoader quản lý**, không phải khóa toàn cục với mọi lần đọc JAR của process.

### 3.4. “Đã đóng” không đồng nghĩa mọi `loadClass` đều thất bại

`ClassLoader.loadClass` thường theo **parent-first delegation**. Sau `URLClassLoader.close`:
- Có thể vẫn trả `Class<?>` của **một lớp đã được loader nạp từ trước**.
- Có thể vẫn trả lớp từ **parent** như `java.lang.String`.
- Lớp plugin **chưa được nạp** và chỉ có trong JAR mà loader này cung cấp sẽ không được load mới từ nguồn đó.

Đừng dùng một câu `loader.loadClass("java.lang.String")` thành công sau close rồi kết luận `close` “không hoạt động”. Đây là class parent, không phải kiểm tra new child definition.

## 4. Đã nạp trước khi đóng: tại sao method vẫn chạy?

Ví dụ thứ tự:

```text
T0: Jar plugin-v1.jar có First.class và Second.class
T1: URLClassLoader L được tạo cho jar
T2: L định nghĩa First.class -> Class<?> first
T3: Host lấy Method first.getMethod("value")
T4: L.close()
T5: Method.invoke(null) của First vẫn chạy
T6: L.loadClass("Second") mới -> thất bại nếu parent không cung cấp
T7: Host vẫn giữ first/method/L -> chưa thể đòi GC unload
```

**Vì sao T5 hợp lệ?** `close` không hủy đã defined `Class<?>`. JVM có thể giữ metadata của lớp, bytecode, constant pool đã resolve, các methods và đối tượng liên quan. Dù loader không còn mở JAR để tìm lớp mới, những phần đã nạp vẫn tồn tại.

**Giới hạn:** Một method của lớp đã nạp có thể **lần đầu tham chiếu tới một lớp khác chưa được nạp** sau khi loader đóng. Khi cần lazy resolution, nó có thể gặp `ClassNotFoundException`/`NoClassDefFoundError` hoặc lỗi linkage phù hợp. Vì vậy không được kết luận “toàn bộ mọi hành vi của plugin vẫn hoạt động đầy đủ sau close”. Chỉ các hành vi **không đòi nạp lớp/resource mới từ loader đã đóng** mới có thể tiếp tục.

### 4.1. Tại sao không nên cố sử dụng loader sau close?

Dù lớp đã nạp vẫn chạy được, một plugin live thường có lazy initialization, resource bundles, reflection, serialization, logging appenders hay service discovery có thể nạp thêm classes/resources. Đóng loader khi plugin chưa shutdown hoàn chỉnh là rủi ro vận hành. Hãy coi close như một **bước kết thúc vòng đời sau khi ngừng mọi công việc liên quan**, không là công tắc pause.

## 5. Class unloading: cần điều kiện gì?

JLS Java SE 17 `12.7 về unloading nói class/interface **có thể được unload chỉ khi defining loader của nó có thể được garbage collector thu hồi**. Đây là điều kiện cần; không phải lời hứa rằng JVM phải unload ngay khi điều kiện thỏa.

### 5.1. Các strong references cần tránh

Một vài đường tham chiếu hay xảy ra:

```text
GC ROOT
  |
  +-- Host singleton / static registry
  |      +-- Map<String, Class<?>> -> plugin Class -> defining loader L
  |      +-- service implementation instance -> Class -> L
  |      +-- Method / MethodHandle -> defining Class -> L
  |
  +-- Live worker thread
  |      +-- Thread.contextClassLoader -> L
  |      +-- running stack -> plugin execution/classes
  |      +-- ThreadLocal value -> plugin object -> L
  |
  +-- Executor queue / scheduler
  |      +-- Runnable/Callable from plugin -> Class -> L
  |
  +-- Registered listeners / callbacks / MXBeans / JDBC drivers
         +-- plugin implementation -> Class -> L

L.close() affects JAR/file handles; it DOES NOT cut these paths.
```

Nếu bất kỳ đường strong reachability hữu hiệu nào còn sống, defining loader không đủ điều kiện được thu hồi; classes mà nó định nghĩa cũng không thể được trông đợi unload.

### 5.2. Một `Class<?>` có thể giữ loader

Theo `ClassLoader` Javadoc, mỗi `Class` object có reference tới defining `ClassLoader`. Host có thể vô tình giữ `Class<?>` trong cache hoặc biến static:

```java
static final Map<String, Class<?>> CACHE =
        new ConcurrentHashMap<>();

// Host giữ Class do pluginLoader định nghĩa:
CACHE.put("plugin.feature", pluginClass);
```

Đây là snippet trong class có imports `java.util.Map` và `java.util.concurrent.ConcurrentHashMap`; giả định `pluginClass` được định nghĩa bởi plugin loader. Nếu host cache tồn tại suốt process, `Class<?>` và loader có thể bị giữ sống. Cleanup cần loại bỏ entries liên quan khi unload plugin.

### 5.3. Instance plugin giữ defining class

Một instance plugin mang runtime class đã định nghĩa bởi loader. Nếu host giữ `PluginImplementation instance` trong registry, callback hoặc listener, loader không thể coi là hoàn toàn không còn được tham chiếu.

Chuyển kết quả từ plugin sang một object **thuộc classloader host/shared API** (ví dụ String/primitive hoặc host-defined immutable DTO) khi rời plugin boundary giúp tránh vô tình trả về plugin-specific type.

### 5.4. Method, MethodHandle, Constructor, lambdas

Reflection objects `Method`, `Constructor`, `Field` và những `MethodHandle` trỏ tới members của plugin có thể giữ những class/loader liên quan. Lambda/callback closures có thể giữ instance hay class plugin.

**Đừng chỉ xóa một field `ClassLoader loader` rồi khẳng định đã hết references.** Hãy rà soát cả những class, methods, callbacks mà host còn lưu.

### 5.5. Thread Context ClassLoader (TCCL)

Java cho phép thread có context class loader:

```java
Thread thread = Thread.currentThread();
ClassLoader previous = thread.getContextClassLoader();

try {
    thread.setContextClassLoader(pluginLoader);
    // Chỉ làm công việc cần plugin loader trong scope có kiểm soát.
} finally {
    thread.setContextClassLoader(previous);
}
```

Đây là snippet cần `pluginLoader` hợp lệ; `setContextClassLoader` không miễn trừ chính sách quyền truy cập của ứng dụng. Nếu quên restore trên **pool thread còn sống lâu**, thread có thể giữ loader kể cả sau khi plugin đã dừng. Không giữ `previous` trong một registry lâu hơn cần thiết; nếu `previous` là loader khác, ownership của nó cũng phải rõ.

### 5.6. Threads và executors do plugin tạo

Nếu plugin tạo executor/scheduler, thread hoặc task đang chạy, những stack frames, Runnable/Callable objects hoặc contextCL có thể giữ classes của plugin. Một quy trình dừng nên:
- Ngừng nhận tasks mới.
- Yêu cầu plugin stop/cancel một cách hợp tác.
- `shutdown()` executor; `awaitTermination` với deadline.
- Nếu cần `shutdownNow()` và interrupt, xử lý trường hợp task không tôn trọng interrupt.
- Đảm bảo không còn callback/timer/queue nhắc đến plugin.
- Restore TCCL ở **mọi thread liên quan**, không chỉ main.
- Chỉ đóng loader sau khi hoàn tất công việc cần nạp classes/resources.

Không nên tự động `Thread.stop()`, vì API này không an toàn/không là lựa chọn hiện đại cho quản lý plugin tasks. Không ép giết threads từ loader khi chưa thiết kế hệ thống cô lập.

### 5.7. ThreadLocal

Một `ThreadLocal` do plugin tạo và set trên **host pool threads** có thể giữ một plugin value lâu dài, kể cả khi plugin đã đóng loader. Cleanup `remove()` phải chạy **trên chính worker thread đã set**; gọi `remove` trên main không tự xóa ThreadLocal values của worker khác.

Tốt hơn là thiết kế per-task scope có `try/finally remove` ngay trong worker. Không phụ thuộc vào việc internal ThreadLocal map có weak keys rồi suy rằng value không thể leak; strong values và stale entries có thể tiếp tục tồn tại.

### 5.8. Global registries và hooks

Những đối tượng đăng ký sống ngoài loader có thể giữ plugin:
- Listener/callback ở application singleton, event bus, UI frameworks.
- JDBC driver đăng ký qua `DriverManager` (tùy cách đăng ký/driver lifecycle).
- MBeans trong `MBeanServer`, scheduler tasks, shutdown hooks.
- Logging appenders/handlers hoặc metrics registry mà plugin tạo.
- `ServiceLoader` instances và caches nếu host giữ provider objects.
- Host-side collections/caches chứa plugin classes hoặc closures.

Khi dừng plugin, deregister những thứ **do plugin sở hữu** khỏi host, cẩn trọng không deregister registrations chung thuộc plugin khác. Đừng cố “dọn sạch JVM” toàn cục để giải phóng một plugin.

### 5.9. Static fields: hiểu đúng chiều tham chiếu

Một `static Map` **bên trong plugin class** có thể giữ nhiều object của plugin. Nhưng một chu trình chỉ gồm plugin loader → classes → static fields → plugin objects → loader **không tự giữ toàn bộ nhóm sống mãi nếu không còn GC root bên ngoài**. GC có thể thu hồi cả chu trình nếu thực sự không reachable.

Nguy hiểm nhất là **root bên ngoài**, ví dụ static cache ở host hoặc thread còn sống, trỏ ngược vào plugin class/instance. Vì vậy “plugin có static field” chưa đủ chứng minh leak; cần xác định chuỗi reachability.

## 6. Điều gì `WeakReference<ClassLoader>` chứng minh được và không?

Có thể tạo:

```java
WeakReference<ClassLoader> observer =
        new WeakReference<>(pluginLoader);
```

Đây là snippet với `import java.lang.ref.WeakReference` và `pluginLoader` thuộc scope.

`observer.get()` **khác null** có nghĩa tại thời điểm đó vẫn còn referent; **không nói** tự nó rằng có leak. `observer.get()==null` sau một đợt GC có thể là tín hiệu loader được thu hồi, nhưng không chứng minh toàn bộ tài nguyên bên ngoài plugin (process/DB/socket/threads) đã được cleanup.

### 6.1. Không assert GC phải chạy trong 100 ms

Không có contract rằng:

```java
pluginLoader.close();
pluginLoader = null;
System.gc();
assert observer.get() == null;
```

sẽ pass. Đây là **phản ví dụ**, không phải test đáng tin. `System.gc()` là đề nghị GC, có thể bị bỏ qua, phụ thuộc JVM options, độ tải và collector. JVM có quyền chưa unload lớp dù loader đã đủ điều kiện, hoặc giữ các tham chiếu trong stack/caches lâu hơn test dự tính.

### 6.2. WeakReference khi vẫn có Class strong ref

Nếu bạn giữ `Class<?> pluginClass` ở host và class đó được định nghĩa bởi loader, không nên mong loader được reclaim. Trong demo hoàn chỉnh, có **strong references tới loader/Class/Method**, nên test chỉ kiểm chứng `observer.get()==loader` ở lúc ref vẫn sống, **không chạy GC** và không tuyên bố đo class unloading.

### 6.3. Khi thực sự muốn quan sát unloading

Trên HotSpot, có thể bật thống kê/log class unloading bằng công cụ của JDK như:
- `-Xlog:class+unload=info` khi chạy Java.
- `jcmd <pid> VM.classloader_stats` nếu lệnh có trong JDK/runtime và được cấp quyền attach.
- Java Flight Recorder (JFR) class-loading/unloading events khi cấu hình phù hợp.
- So sánh classloader instances, live classes, Metaspace usage theo thời gian sau chu kỳ reload có kiểm soát.

**Đây là công cụ chẩn đoán**, không thay đổi semantic contract: ngay cả quan sát một lần có unloading cũng không hứa mọi deployment sẽ unload theo cùng thời điểm. `jcmd`/unified logging là công cụ implementation-specific; không dùng chúng trong unit test portable bắt buộc mỗi commit.

## 7. Class identity khi nạp lại: cùng tên chưa chắc cùng lớp

JVM định danh một class không chỉ theo *binary name* mà còn theo **defining class loader**. Ví dụ:

```text
L1 defines example.plugin.First -> Class A
L1.close()
L2 defines example.plugin.First -> Class B

A.getName().equals(B.getName()) == true
A == B == false
A.getClassLoader() == L1
B.getClassLoader() == L2
```

Đây là trạng thái quan sát được khi hai loaders độc lập đều định nghĩa class cùng tên. **Nó không chứng minh Class A đã unload**; trong ví dụ A còn tồn tại và vẫn gọi được.

### 7.1. ClassCastException “cùng tên lớp”

Nếu host giữ một instance của class A và muốn cast sang class B, tên in stack trace có thể giống nhau nhưng JVM coi hai types khác nhau. `B.isInstance(instanceFromA)` sẽ là false nếu hai Class identities khác nhau.

Thiết kế plugin boundary nên có interface/DTO **được parent/shared loader định nghĩa**, để cả host và plugin thấy **cùng một `Class<?>` identity** cho API chung. Child loader định nghĩa implementation, host không nên cast trực tiếp implementation của phiên bản cũ sang implementation bản mới.

### 7.2. Parent delegation ảnh hưởng cách “nạp lại”

`URLClassLoader` mặc định tìm ở parent trước, sau đó mới theo classpath của nó. Nếu parent đã có một class cùng binary name, child có thể **trả class của parent** thay vì định nghĩa bản mới. Trong hệ thống plugin, đừng chỉ thấy có URLClassLoader riêng rồi khẳng định mỗi class luôn có một bản độc lập.

Khi cần isolation cho plugin-specific packages, thiết kế parent delegation và export/import packages có chủ đích. **Không tự sửa cơ chế delegation thành child-first đại trà**, vì có thể tạo trùng type/JDK package và lỗi liên kết nghiêm trọng.

## 8. Thứ tự shutdown plugin an toàn

Một quy trình có thể được dùng trong service có loader riêng:

```text
1. Admission OFF
   Host không gửi thêm request/task cho plugin cũ.

2. Quiesce / drain
   Đợi công việc đang chạy hoàn tất, có deadline/cancellation.

3. Stop owned background work
   Dừng executors, scheduled tasks, watchers, network loops.

4. Deregister
   Gỡ listeners, MBeans, driver registrations, shutdown hooks,
   service providers/callbacks do plugin sở hữu.

5. Release host references
   Xóa caches, Class/Method/MethodHandle/instance references,
   detach event subscriptions, trả DTO thuộc host.

6. Restore context and thread-local state
   TCCL và ThreadLocal trên đúng threads từng sử dụng.

7. Close URLClassLoader
   Try-with-resources hoặc explicit close; ghi nhận IOException.

8. Drop manager references to old loader
   Thay generation old bằng generation new một cách an toàn.

9. Observe / diagnose
   Theo dõi loaders/classes/Metaspace, không đòi GC ngay.
```

**Thứ tự có thể khác** theo ownership của hệ thống; điểm bất biến là **đừng close loader khi có worker đang load class/resource qua nó**. Nếu framework sở hữu executors/registries, dùng API lifecycle của framework; không tự terminate resource của host.

### 8.1. Tại sao phải tắt admission trước?

Nếu vừa reload vừa tiếp nhận request vào plugin cũ, một task có thể đột ngột lazy-load một class sau khi manager đã đóng loader. Điều này tạo lỗi khó tái hiện. Đóng loader đồng thời với class loading đang diễn ra được Javadoc mô tả là không có hành vi kết quả xác định.

### 8.2. Phân biệt shutdown “graceful” và “forced”

Graceful shutdown chờ công việc hiện tại hoàn tất trong deadline. Forced shutdown có thể interrupt/cancel nhưng cần business policy cho request đang dở (retry, idempotency, rollback, ack). Không coi `loader.close()` là một cơ chế hủy task. Những method đang chạy trên class đã nạp **không tự bị dừng**.

### 8.3. Shutdown hook và callback của plugin

Nếu plugin tự đăng ký shutdown hook bằng một `Thread` chứa code/plugin class, hook đó có thể giữ classloader sống tới khi process shutdown. Khi plugin stop, nếu chính plugin đã đăng ký hook, quản lý việc `Runtime.removeShutdownHook(thread)` theo API và trạng thái JVM phù hợp. Chú ý không cố remove hook khi shutdown đã bắt đầu.

## 9. Nạp loader mới sau close: giới hạn của hot reload

Một cách tiếp cận đơn giản cho plugin generation:

```text
PluginManager
    |
    +-- generation 1 (loader L1, API adapters)
             |
             +-- stop -> close L1 -> detach references
    |
    +-- generation 2 (loader L2, new implementation)
             |
             +-- active calls
```

Mỗi generation có **owner rõ** và các service adapters/interfaces chung do host nạp. Sau swap, host gửi requests mới sang generation 2; các requests đang in-flight ở generation 1 cần chính sách drain/timeout.

### 9.1. Không re-define class trong cùng loader

`URLClassLoader.close()` không xóa các class đã được định nghĩa bên trong loader và cũng không “reset” lớp cũ. Để nạp implementation mới cùng binary name, **tạo loader mới**. Cố nạp lại cùng tên bằng `defineClass` trong cùng loader thường dẫn đến `LinkageError: duplicate class definition` nếu class đã được định nghĩa.

### 9.2. Hot reload không thay native process isolation

Cả hai generations có thể cùng tồn tại trong một JVM, cùng dùng threads/heap/native memory/process permissions. Một bug hoặc mã độc trong plugin có thể gây hại tới toàn bộ process. **ClassLoader không phải cơ chế bảo vệ đầy đủ cho code không đáng tin cậy.**

Nếu plugin nguồn không tin cậy, cân nhắc chạy nó **ở process/container riêng** với OS permissions, network/filesystem quotas, giao thức IPC và xác thực rõ. Không xây “Java security sandbox” chỉ dựa vào `URLClassLoader` hoặc một SecurityManager cũ đã bị deprecate trong JDK hiện đại.

### 9.3. Metaspace không giảm ngay sau swap

Khi generation 1 đã detached, loader có thể được GC thu hồi và classes có thể unload trong lần collection phù hợp. Nhưng không có đảm bảo rằng ngay sau `L1.close()`, chỉ số Metaspace giảm lập tức hoặc class count giảm đúng số lớp trong JAR. Collector, fragmentation, caching và runtime tối ưu hóa ảnh hưởng các metrics.

## 10. Giới hạn của resource cleanup

### 10.1. File JAR

Trên Windows, một JAR đang được `JarFile`/classloader mở có thể cản xóa/thay thế do file handles. `URLClassLoader.close()` có tác dụng giải phóng file handles do loader quản lý, hữu ích cho cập nhật plugin. **Nếu loader khác hoặc code ngoài cũng mở cùng JAR, vẫn có thể chưa xóa được**.

Trong ví dụ hoàn chỉnh, cả old loader và fresh loader đều đóng trước khi `Files.delete(jar)` được gọi. Kết quả delete thành công chỉ nói về tệp demo **đã được các loaders đó release**, không chứng minh không còn Class objects.

### 10.2. InputStream và resource URL

Dùng `try-with-resources` cho `InputStream` từ loader. `URLClassLoader.close` có behavior đóng files đã mở bởi loader, nhưng không tự bảo đảm các streams do plugin tự mở bằng `Files.newInputStream` hoặc network clients sẽ bị đóng. Chúng có owners riêng.

### 10.3. Socket, thread, file watcher, database connection

Loader close **không đóng** các `Socket`, `WatchService`, `Connection`, `ExecutorService` hoặc app-level file handles mà plugin mở tùy ý. Mỗi resource cần `close`/shutdown theo API và ownership riêng. Nếu plugin còn thread giữ connection hoặc callback, loader vẫn có thể bị pin.

### 10.4. Native libraries

Khi plugin load native library, lifecycle và class-loader association có các ràng buộc riêng. Không nghĩ `URLClassLoader.close` là một lệnh portable ép unload native library hoặc có thể nạp cùng native library tùy ý ở hai defining loaders. Nếu sử dụng JNI/native code, tài liệu hóa chính sách nạp thư viện, cleanup và thử nghiệm với JVM/OS đích.

### 10.5. Java Module System

Với JPMS `ModuleLayer` và các lớp nạp bởi module loaders, không có bảo đảm một lời gọi `URLClassLoader.close()` sẽ giải phóng mọi module layer được tạo bằng API khác. ClassLoader API chung không có close; có thể cần giải phóng references tới `ModuleLayer`, `Module`, services, loader và resources theo lifecycle của từng cơ chế.

## 11. Ví dụ Java 17+ độc lập: tự tạo plugin JAR, đóng loader và xác minh

Chương trình **`LoaderCloseDemo.java`** dưới đây chạy **chỉ bằng JDK 17+**, không cần JAR/driver/IDE bên ngoài. Nó làm các việc:

1. Tạo một thư mục tạm dưới `java.io.tmpdir`.
2. Tạo hai file source plugin nhỏ: `example.plugin.First` và `example.plugin.Second`.
3. Biên dịch chúng bằng `javax.tools.JavaCompiler` của JDK vào thư mục classes.
4. Thêm resource `example/plugin/info.txt` vào thư mục classes.
5. Tạo JAR bằng `JarOutputStream`.
6. Tạo một `URLClassLoader` với parent là platform loader, nạp **chỉ class First**, gọi method và đọc resource.
7. Đóng old loader bằng `try-with-resources`.
8. Xác minh `First` vẫn được gọi/tra cứu qua loader cũ; nhưng `Second` và resource mới không thể nạp/tìm từ loader cũ.
9. Kiểm tra loader cũ vẫn delegate được `java.lang.String` cho parent.
10. Xác minh lúc vẫn giữ strong references tới loader và `Class<?>`, không có cơ sở kỳ vọng class unload.
11. Tạo **URLClassLoader mới** từ cùng JAR và nạp class cùng binary name, nhận **Class identity mới**.
12. Đóng cả hai loaders, xóa JAR và cleanup thư mục tạm.

**Giới hạn của test:** đây là một demo về API/lifecycle và type identity **trên một JDK**, không phải test đủ để chứng minh class unloading hay đo GC. Không gọi `System.gc()`, không assert WeakReference bị clear và không đo lượng Metaspace.

### 11.1. Mã đầy đủ `LoaderCloseDemo.java`

```java
import java.io.*;
import java.lang.ref.WeakReference;
import java.lang.reflect.Method;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.nio.file.attribute.BasicFileAttributes;
import java.util.Comparator;
import java.util.List;
import java.util.jar.*;
import java.util.stream.Stream;
import javax.tools.*;

public final class LoaderCloseDemo {
    private static void check(boolean value, String label) {
        if (!value) throw new AssertionError(label);
    }

    private static Path makePluginJar(Path dir) throws Exception {
        Path sources = dir.resolve("src").resolve("example").resolve("plugin");
        Files.createDirectories(sources);
        Path first = sources.resolve("First.java");
        Path second = sources.resolve("Second.java");
        Files.writeString(first,
                "package example.plugin; public final class First { "
              + "public static String value() { return \"ALIVE\"; } }",
                StandardCharsets.UTF_8);
        Files.writeString(second,
                "package example.plugin; public final class Second { "
              + "public static String value() { return \"NEW\"; } }",
                StandardCharsets.UTF_8);

        Path classes = dir.resolve("classes");
        Files.createDirectories(classes);
        JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
        check(compiler != null, "JDK compiler needed");
        int result = compiler.run(null, null, null,
                "-encoding", "UTF-8",
                "-d", classes.toString(),
                first.toString(), second.toString());
        check(result == 0, "plugin compilation failed");
        Path res = classes.resolve("example").resolve("plugin")
                .resolve("info.txt");
        Files.writeString(res, "resource-ok", StandardCharsets.UTF_8);

        Path jar = dir.resolve("demo-plugin.jar");
        try (JarOutputStream zip =
                     new JarOutputStream(Files.newOutputStream(jar));
             Stream<Path> files = Files.walk(classes)) {
            List<Path> entries = files
                    .filter(Files::isRegularFile)
                    .sorted(Comparator.comparing(Path::toString)).toList();
            for (Path file : entries) {
                String name = classes.relativize(file)
                        .toString().replace('\\', '/');
                zip.putNextEntry(new JarEntry(name));
                Files.copy(file, zip);
                zip.closeEntry();
            }
        }
        return jar;
    }

    private static void deleteTree(Path dir) throws IOException {
        if (!Files.exists(dir)) return;
        Files.walkFileTree(dir, new SimpleFileVisitor<>() {
            @Override public FileVisitResult visitFile(Path file,
                    BasicFileAttributes attrs) throws IOException {
                Files.delete(file);
                return FileVisitResult.CONTINUE;
            }
            @Override public FileVisitResult postVisitDirectory(
                    Path path, IOException error) throws IOException {
                if (error != null) throw error;
                Files.delete(path);
                return FileVisitResult.CONTINUE;
            }
        });
    }

    public static void main(String[] args) throws Exception {
        Path temp = Files.createTempDirectory("loader-close-");
        try {
            Path jar = makePluginJar(temp);
            URL[] classpath = {jar.toUri().toURL()};
            Class<?> oldClass;
            Method oldMethod;
            URLClassLoader oldLoader =
                    new URLClassLoader(classpath,
                            ClassLoader.getPlatformClassLoader());
            WeakReference<ClassLoader> observer =
                    new WeakReference<>(oldLoader);

            try (oldLoader) {
                oldClass = Class.forName(
                        "example.plugin.First", true, oldLoader);
                oldMethod = oldClass.getMethod("value");
                check(oldClass.getClassLoader() == oldLoader,
                        "wrong defining loader");
                check("ALIVE".equals(oldMethod.invoke(null)),
                        "first invocation failed");
                try (InputStream input =
                         oldLoader.getResourceAsStream(
                                  "example/plugin/info.txt")) {
                    check(input != null, "resource missing");
                    check("resource-ok".equals(
                            new String(input.readAllBytes(),
                                    StandardCharsets.UTF_8)),
                            "resource content");
                }
                System.out.println("beforeClose.firstLoaded=true");
                System.out.println("beforeClose.resourceRead=true");
            }

            // close() stops fresh lookup from this loader.
            // Already-defined classes and parent classes remain usable.
            check(oldLoader.loadClass("example.plugin.First") == oldClass,
                    "previously loaded class was lost");
            check("ALIVE".equals(oldMethod.invoke(null)),
                    "loaded class became unusable");
            check(oldLoader.getResource(
                    "example/plugin/info.txt") == null,
                    "resource should not be newly located");
            boolean newClassRejected = false;
            try {
                oldLoader.loadClass("example.plugin.Second");
            } catch (ClassNotFoundException expected) {
                newClassRejected = true;
            }
            check(newClassRejected, "closed loader loaded new plugin class");
            check(oldLoader.loadClass("java.lang.String") == String.class,
                    "parent class not accessible");
            check(observer.get() == oldLoader
                            && oldClass.getClassLoader() == oldLoader,
                    "strong references should still retain loader");
            System.out.println("afterClose.oldMethodStillWorks=true");
            System.out.println("afterClose.newPluginClassRejected=true");
            System.out.println("afterClose.newResourceMissing=true");
            System.out.println("afterClose.parentDelegationWorks=true");
            System.out.println("afterClose.strongReferenceStillKeepsLoader=true");

            // Fresh loader defines an independent Class for the same name.
            // That does not prove old class unloading.
            try (URLClassLoader fresh =
                     new URLClassLoader(classpath,
                             ClassLoader.getPlatformClassLoader())) {
                Class<?> freshClass =
                        Class.forName("example.plugin.First", true, fresh);
                check(freshClass != oldClass, "class identity must differ");
                check(freshClass.getName().equals(oldClass.getName()),
                        "expected same binary class name");
                check(freshClass.getClassLoader() == fresh,
                        "fresh loader mismatch");
                check("ALIVE".equals(
                        freshClass.getMethod("value").invoke(null)),
                        "new loader class failed");
                System.out.println("replacement.sameNameNewClassIdentity=true");
            }
            Files.delete(jar);
            check(!Files.exists(jar), "jar not deleted");
            System.out.println("jar.deletedAfterClose=true");
            System.out.println("checks=PASS");
        } finally {
            deleteTree(temp);
        }
    }
}
```

### 11.2. Cách biên dịch và chạy

Đảm bảo dùng **JDK 17+** có `javac` và module `java.compiler`; một Java runtime chỉ có `java` mà không có compiler sẽ không đủ cho test tự biên dịch classes. Chạy:

```bash
javac -encoding UTF-8 LoaderCloseDemo.java
java LoaderCloseDemo
```

Chương trình tự tạo và dọn thư mục tạm. Nó không ghi vào project hiện tại, không kết nối mạng, không cần database.

### 11.3. Stdout chính xác đã kiểm chứng

```text
beforeClose.firstLoaded=true
beforeClose.resourceRead=true
afterClose.oldMethodStillWorks=true
afterClose.newPluginClassRejected=true
afterClose.newResourceMissing=true
afterClose.parentDelegationWorks=true
afterClose.strongReferenceStillKeepsLoader=true
replacement.sameNameNewClassIdentity=true
jar.deletedAfterClose=true
checks=PASS
```

Đây là output đã chạy thực tế với Java/JDK phù hợp, exit code 0. Output không in đường dẫn tạm hoặc classloader identity không ổn định, nên dễ đối chiếu.

### 11.4. `beforeClose.*`

Loader mới nạp `example.plugin.First` từ JAR, gọi `First.value()` trả `ALIVE` và đọc `example/plugin/info.txt` với nội dung `resource-ok`. Class `Second` có trên JAR nhưng chương trình chưa gọi loadClass cho nó.

### 11.5. `afterClose.oldMethodStillWorks`

Sau khi old loader đóng, `oldMethod.invoke(null)` vẫn chạy. Đây là ví dụ thực tế phân biệt **loader close** với **class unloading**: class First đã định nghĩa trước đó tiếp tục sử dụng được.

### 11.6. `afterClose.newPluginClassRejected`

`oldLoader.loadClass("example.plugin.Second")` thử nạp class chưa được định nghĩa trước khi close. Vì class chỉ có trong child JAR và parent không cung cấp, lời gọi bị `ClassNotFoundException`, đúng hợp đồng của URLClassLoader đã đóng.

### 11.7. `afterClose.newResourceMissing`

`oldLoader.getResource("example/plugin/info.txt")` trả null sau khi loader đóng. Lúc này resource không được parent cung cấp. Đừng mở rộng kết luận thành “mọi URL đã từng trỏ vào JAR không còn đọc được qua mọi Java API”; phạm vi là classloader đã đóng.

### 11.8. `afterClose.parentDelegationWorks`

`oldLoader.loadClass("java.lang.String")` vẫn trả `String.class`, vì lớp nền tảng do parent/bootstrap hierarchy định nghĩa, không phải class mới do child JAR định nghĩa.

### 11.9. `afterClose.strongReferenceStillKeepsLoader`

`oldClass.getClassLoader()==oldLoader` và `observer.get()==oldLoader` khi chương trình còn giữ các strong references. **Không gọi GC**; test minh họa reachability hiện hữu chứ không chứng minh sau này old loader sẽ hoặc sẽ không unload.

### 11.10. `replacement.sameNameNewClassIdentity`

Loader mới nạp một `Class<?>` với binary name `example.plugin.First` nhưng class object khác với oldClass. Hai phiên bản có thể song song tồn tại. Việc class identity khác đi **không phải phép đo class unloading**.

### 11.11. `jar.deletedAfterClose`

Sau khi đóng cả old/fresh loader, chương trình xóa `demo-plugin.jar`. Đây là kiểm tra thao tác file thành công **trong một fixture local**, không là bảo đảm với mọi external process/file lock trên mọi OS.

## 12. Một lifecycle manager cho plugin thật sẽ phức tạp hơn ví dụ

Ví dụ mục 11 cố ý không tạo worker lâu sống, cache global hoặc register SPI. Trong ứng dụng thật, plugin manager thường cần:
- Một **generation ID** cho mỗi phiên bản plugin.
- Một trạng thái `STARTING/RUNNING/DRAINING/CLOSED` hoặc tương đương do host định nghĩa.
- Một interface chung do host classloader định nghĩa.
- Một admission gate chống request mới tới generation đang đóng.
- In-flight counter hoặc task tracking không dùng busy-spin.
- Completion/cancellation protocol.
- Một registry các tài nguyên do plugin sở hữu để cleanup.
- Khả năng đổi active generation một cách an toàn.
- Kiểm tra JAR đã được xác thực/approved và quyền truy cập vào file/network/process ngoài JVM.
- Quan sát lỗi khi close, error stack và metrics classloader.

### 12.1. Ví dụ state machine

```text
CREATED -> STARTING -> RUNNING -> DRAINING -> CLOSED
                         |
                         +-------> FAILED -> DRAINING -> CLOSED
```

Các transitions phải được bảo vệ theo concurrency model của ứng dụng. Không cho request mới vào sau khi chuyển DRAINING. Nếu không dừng được một task, báo timeout/failure theo policy, không lờ đi và close loader giữa khi đang load class.

### 12.2. API boundary nên tách data khỏi implementation

Giả sử host có `PluginApi` interface được nạp bởi parent. Plugin implementation bên child trả `PluginResult` cũng do parent định nghĩa. Khi reload, host giữ interface type/DTO ổn định và không cần giữ implementation class cũ. **Nếu API type cũng bị child define hai lần, cast và linkage có thể thất bại dù tên lớp giống hệt.**

### 12.3. Xử lý lỗi close

Với `try-with-resources`, nếu code trong body và `close()` cùng ném, Java giữ suppressed close exceptions. Nếu close thủ công trong manager, ghi lại thất bại, không chuyển mọi lỗi thành “đã release thành công”. Dù `close()` có `IOException`, vẫn phải cleanup đăng ký/tài nguyên khác có ownership riêng, có thể theo chuỗi suppressed exceptions.

### 12.4. Trong lúc reload vẫn có old references

Một hệ thống có graceful drain có thể giữ generation 1 sống đủ lâu để hoàn tất request đã nhận trong khi generation 2 nhận request mới. Điều đó **không mặc nhiên là leak**. Leak chỉ xuất hiện khi generation cũ không còn yêu cầu nghiệp vụ nhưng vẫn bị giữ vô thời hạn bởi một root/callback/resource không được cleanup.

## 13. Các lỗi thường gặp trong thực tế

| Sai lầm | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| “`URLClassLoader.close` unload class ngay” | Close chủ yếu release URL/file handles và dừng load mới | Phân biệt GC eligibility và unloading |
| “Đóng loader thì code plugin tự dừng” | Method đã loaded vẫn có thể chạy | Stop tasks trước |
| “Đóng loader nhưng để executor của plugin sống” | Thread/tasks pin classloader | Shutdown/await/cancel |
| “Xóa JAR xong nghĩa classes đã unload” | File deletion khác metadata lifecycle | Kiểm tra reachability/metrics |
| “URLClassLoader không có leak vì không có field cached loader” | Host giữ Class/instance/Method có thể pin loader | Audit reference graph |
| “TCCL ở main đã restore nên mọi thread sạch” | Pool threads giữ context loader riêng | Restore ở đúng worker threads |
| “Gọi `ThreadLocal.remove` ở main để dọn pool thread” | ThreadLocal value per-thread | Cleanup trong worker scope |
| “Static state bên plugin luôn gây leak dù không có roots” | GC thu hồi chu trình unreachable | Tìm GC root bên ngoài |
| “WeakReference.clear sau System.gc là contract” | GC không có deadline | Diagnostic best-effort, không CI assertion cứng |
| “Class loader mới định nghĩa Class khác chứng minh old unload” | Hai types có thể cùng tồn tại | Phân biệt identity và unloading |
| “Sau close, loadClass(String) cũng phải fail” | Parent classes và loaded classes vẫn usable | Kiểm tra class chưa từng loaded thuộc child |
| “Sau close, mọi plugin method chắc chắn chạy bình thường” | Lazy load class/resource mới có thể fail | Không dùng loader sau shutdown |
| “Có URLClassLoader là sandbox” | Cùng process không đủ trust boundary | OS process/container isolation |
| “ModuleLayer nào cũng close bằng URLClassLoader” | Loader types/lifecycle khác nhau | Thực hiện theo framework/module API |
| “ClassCastException cùng tên là JVM bug” | Type identity gồm defining loader | Shared parent API types |
| “Gọi close khi thread khác đang load luôn ổn” | Javadoc nói kết quả concurrent load undefined | Admission gate + drain |
| “Call close nhiều lần thay nhiều resource cleanups” | Close chỉ tài nguyên do loader quản lý | Cleanup sockets/threads/registries riêng |
| “Bắt IOException rồi tuyên bố cleaned” | Close có thể fail/best effort | Log/suppressed và verify resource state |
| “Chuyển sang plugin mới là old instance tự giải phóng” | Registries/caches có thể còn giữ | Explicit deregister và drop references |
| “Metaspace phải giảm ngay sau close” | JVM/GC quyết định unloading | Theo dõi theo nhiều chu kỳ |
| “Nâng PermGen size là giải pháp Java 17” | JDK hiện đại dùng Metaspace | Sửa leak + monitor native memory |
| “Để plugin tự đóng host classloader” | Ownership sai | Chỉ manager sở hữu loader đóng loader đó |

## 14. Checklist vận hành và kiểm thử

### 14.1. Tính đúng của loader close

- [ ] Loader là một `URLClassLoader` do thành phần này sở hữu.
- [ ] Không đóng system/platform loader hoặc loader do framework khác sở hữu.
- [ ] Đã chặn request mới và đợi những tác vụ cần lazy load xong trước close.
- [ ] Đã xử lý `IOException` và suppressed exceptions của `close`.
- [ ] Không dùng lại loader đã đóng cho class/resource chưa nạp.
- [ ] Không giả định lớp đã nạp sẽ lập tức không dùng được.
- [ ] Test phân biệt class đã loaded, class chưa loaded và parent class.
- [ ] Streams/JarFiles/files khác được đóng đúng ownership.

### 14.2. Điều kiện thuận lợi cho unloading

- [ ] Không còn host cache giữ `Class<?>` của plugin.
- [ ] Không còn plugin instances được host giữ.
- [ ] Không còn `Method`/`MethodHandle`/callback của plugin nằm trong registries.
- [ ] Workers/executors/tasks/scheduled loops của plugin đã dừng.
- [ ] ContextClassLoader được restore trên từng thread liên quan.
- [ ] ThreadLocal values đã được remove trong đúng thread/scope.
- [ ] Listeners, hooks, drivers, MBeans và resource registrations của plugin đã được gỡ.
- [ ] Không còn host static singleton trỏ vào generation cũ.
- [ ] Không còn PluginManager/generation table giữ loader cũ.
- [ ] Hiểu rằng vòng tham chiếu tự chứa không mặc nhiên là leak nếu không có roots.
- [ ] Không yêu cầu `System.gc()` gây unloading theo deadline.
- [ ] Metaspace/classloader metrics được quan sát theo thời gian nếu app reload nhiều.

### 14.3. An toàn khi nạp plugin

- [ ] Không lấy một JAR bất kỳ từ nguồn không tin cậy rồi chạy trong host process.
- [ ] Có kiểm tra nguồn JAR/allowlist/checksum hoặc ký số theo threat model.
- [ ] Parent/shared API types được định nghĩa nhất quán, tránh ClassCastException.
- [ ] Không lạm dụng child-first, phản xạ private hoặc sửa module boundaries để load plugin.
- [ ] Không coi URLClassLoader là security sandbox.
- [ ] Nếu cần cô lập code thực sự không đáng tin, dùng process/container boundary.
- [ ] Không để plugin lấy credentials/secret từ host ngoài quyền thiết kế.
- [ ] Không để shutdown code plugin tùy tiện close resource của host.

## 15. Câu hỏi thường gặp

**1. `URLClassLoader.close()` có khiến các lớp đã nạp bị unload ngay không?**  
Không. Những lớp đã định nghĩa vẫn có thể dùng; unloading là cơ chế do JVM/GC quyết định khi defining loader có thể được thu hồi.

**2. Sau close, có thể gọi method của class đã loaded không?**  
Có thể, nếu method không phải load thêm dependency/resource mới từ loader đã đóng. Demo đã kiểm chứng method cũ tiếp tục hoạt động.

**3. Sau close, `loadClass("java.lang.String")` có thể thành công không?**  
Có, vì parent/bootstrap hierarchy cung cấp String; close chỉ ngăn load mới do chính loader đã đóng định nghĩa.

**4. Sau close, class plugin chưa loaded có thể nạp thêm không?**  
Không từ search path của URLClassLoader đã đóng; nếu parent có class cùng tên thì parent delegation là câu chuyện khác.

**5. `ClassLoader` nào cũng có `close` không?**  
Không. `URLClassLoader` implement `Closeable`, còn `ClassLoader` chung không cung cấp `close`.

**6. Đóng loader có đóng executor/threads của plugin không?**  
Không. Phải shutdown/cancel/await theo API và ownership riêng.

**7. Vì sao một `Class<?>` vẫn có thể pin loader?**  
Class object giữ reference đến defining loader; host cache class có thể kéo loader sống.

**8. `WeakReference.get()!=null` có chắc chắn là leak?**  
Không. Nó chỉ cho biết referent còn tồn tại lúc quan sát; có thể do strong refs hợp lệ hay GC chưa chạy.

**9. `WeakReference.get()==null` có chứng minh mọi resource đã release?**  
Không. Socket, database connection, native/process resources phải được đóng đúng vòng đời.

**10. Có nên gọi `System.gc()` sau mỗi plugin stop không?**  
Không. Đó không phải protocol unload portable, còn có thể gây tốn tài nguyên.

**11. Tại sao cùng tên class nhưng cast bị lỗi?**  
Defining loaders khác nhau tạo hai type identities khác nhau.

**12. Có thể nạp lại class đã định nghĩa vào cùng loader không?**  
Không theo cách reset đơn giản; dùng loader generation mới để có type identity mới.

**13. Đóng URLClassLoader giúp xóa JAR trên Windows không?**  
Nó đóng handles do loader quản lý, thường là bước cần để thay/xóa JAR; có thể còn handles từ nguồn khác.

**14. Loader close có làm Connection/JDBC Driver registration tự cleanup không?**  
Không. Các resource và registrations có cleanup riêng.

**15. TCCL có ảnh hưởng unloading không?**  
Có thể. Một pool thread còn sống giữ context loader của plugin sẽ pin loader.

**16. Chỉ plugin static field có gây leak không?**  
Không nhất thiết; nếu cả nhóm không còn reachable từ roots, GC có thể thu hồi chu trình tham chiếu.

**17. Java 17 còn dùng PermGen không?**  
Không. Class metadata trong JVM hiện đại liên quan Metaspace; theo dõi bằng công cụ tương ứng.

**18. Có phải mọi class của một plugin unload cùng giây sau close?**  
Không có thời hạn được JLS bảo đảm. Đừng thiết kế theo thời điểm GC.

**19. `close()` đồng thời với `loadClass()` có xác định kết quả không?**  
Javadoc nêu kết quả loading đang diễn ra lúc close là undefined; phải quiesce trước.

**20. Có nên dùng ClassLoader để chạy untrusted plugin như sandbox không?**  
Không. Loader namespace isolation không thay OS/process-level security isolation.

## 16. Kết luận và tài liệu chính thức Java 17

Với bài **“Đóng loader và giới hạn thu hồi các lớp đã nạp”**, hãy luôn phân biệt:

1. **Đóng `URLClassLoader`:** quản lý search path/JAR/file handles, ngăn load mới từ loader đó và cleanup theo `Closeable`.
2. **Lớp đã định nghĩa:** vẫn tồn tại và có thể tiếp tục sử dụng sau close; lazy dependency mới có thể fail.
3. **GC eligibility:** cần cắt mọi strong references từ GC roots vào defining loader/các classes/instances/callbacks của plugin.
4. **Class unloading:** chỉ *có thể* xảy ra theo JVM/GC; không có API `unloadClassNow()` portable và `System.gc()` không phải lời hứa.
5. **Reload đúng:** tạo loader generation mới, quản lý class identity và API boundary, không giả định old generation đã biến mất.
6. **Bảo mật:** loader không tự tạo sandbox cho mã chưa tin cậy; dùng trust policy hoặc process isolation.
7. **Verification:** dùng code runnable để kiểm tra close/load/identity/files, còn class unloading phải quan sát bằng diagnostics và phân tích reachability thay vì một assertion may rủi.

### Nguồn chính thức Java SE 17

- [Oracle `URLClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLClassLoader.html): `close()`, file resources, parent delegation và khả năng truy cập classes đã loaded.
- [Oracle `ClassLoader`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html): định nghĩa loader, `Class` reference to defining loader, delegation và built-in loaders.
- [Oracle `Class`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html): `getClassLoader()`, class identity và runtime class introspection.
- [Oracle `Thread`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html): context class loader, threads lifecycle.
- [Oracle `ThreadLocal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html): per-thread values và `remove()`.
- [Oracle `ExecutorService`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html): `shutdown`/`awaitTermination` và dừng tasks.
- [Oracle `WeakReference`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ref/WeakReference.html): weak reachability không phải lệnh GC.
- [Oracle `JavaCompiler`](https://docs.oracle.com/en/java/javase/17/docs/api/java.compiler/javax/tools/JavaCompiler.html): compile nguồn Java từ chương trình JDK.
- [Oracle `JarOutputStream`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/jar/JarOutputStream.html): tạo JAR file.
- [JLS Java SE 17 `12.7 — Unloading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7): điều kiện defining class loader có thể được GC reclaim và unloading không là cam kết thời điểm.
- [JVMS Java SE 17 `5.3 — Creation and Loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html#jvms-5.3): class loaders và class identity.
- [JVMS Java SE 17 `5.5 — Initialization / `5.3 class loading](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-5.html): các giai đoạn lifecycle class.
