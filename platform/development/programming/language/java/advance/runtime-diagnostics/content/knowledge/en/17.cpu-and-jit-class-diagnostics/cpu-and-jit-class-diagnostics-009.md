# 17.9. Liên hệ lớp sinh động, class loader giữ lâu với Metaspace

## Mục tiêu

Sau bài học, bạn sẽ có khả năng:

1. Giải thích **Metaspace** chứa metadata của lớp trong HotSpot/JVM và vì sao nó khác **Java heap**, nơi chứa đối tượng `ClassLoader`, instance và nhiều cấu trúc ứng dụng.
2. Phân biệt **một lớp có nhiều instance**, **một class được định nghĩa bởi nhiều class loader** và **nhiều class được tạo động lúc chạy**.
3. Vẽ đường tham chiếu từ **GC root → đối tượng giữ `ClassLoader` → lớp được định nghĩa bởi loader → metadata trong Metaspace** để hiểu vì sao việc giữ loader quá lâu có thể gây tăng Metaspace.
4. Đo **loaded/unloaded classes**, bộ nhớ Metaspace và số lượng loader bằng `ClassLoadingMXBean`, `MemoryPoolMXBean`, `jcmd VM.classloader_stats`, `VM.metaspace`, NMT và log class unloading.
5. Tái hiện bằng **Java 17+** hai tình huống: giữ tham chiếu mạnh tới loader (`hold`) và bỏ tham chiếu (`release`) khi tạo dynamic proxy; biết điều gì có thể và không thể kết luận từ số liệu.
6. Nhận diện dấu hiệu class-loader leak trong plugin, hot-reload, proxy/bytecode generator và khắc phục bằng quản lý vòng đời, cache và thread context class loader.

> **Thông điệp cốt lõi:** Một lớp được sinh động **không tự động là rò rỉ**. Vấn đề xuất hiện khi có nhiều *định nghĩa lớp* được tạo theo thời gian **và** các loader/lớp đó tiếp tục reachable dù chức năng liên quan đã kết thúc. Không giải phóng được loader thì metadata của các lớp do nó định nghĩa có thể tiếp tục chiếm Metaspace; nhưng tăng Metaspace một lần cũng không đủ để kết luận leak.

## 1. Metaspace nằm ở đâu trong bộ nhớ JVM?

Ở HotSpot từ Java 8, **Metaspace** là vùng bộ nhớ native do JVM quản lý, được dùng cho metadata phục vụ các lớp được tải/định nghĩa. Nó không phải một phần trực tiếp của Java object heap. Java heap vẫn chứa các đối tượng thông thường, ví dụ:

- Instance của lớp nghiệp vụ: `Order`, `User`, `ArrayList`, mảng byte.
- Đối tượng `java.lang.Class` phản ánh một lớp ở Java level.
- Đối tượng `ClassLoader`, map cache, thread, proxy instance và các tham chiếu ứng dụng.

Metaspace ở native memory chứa biểu diễn nội bộ của lớp và cấu trúc metadata tương ứng mà VM cần cho runtime. **Một đối tượng Java thường không tương đương với một định nghĩa lớp**: tạo 1 triệu `new Order()` vẫn dùng chung metadata của class `Order` do một loader định nghĩa. Ngược lại, một hệ thống tạo hàng nghìn **định nghĩa lớp khác nhau** qua runtime có thể gây áp lực Metaspace dù chỉ có ít instance sống trên heap.

```text
                 Java Heap                            Native memory
  +--------------------------------+           +----------------------------+
  | GC roots                       |           | Metaspace                  |
  |   -> registry / thread / cache |           |  metadata của class A      |
  |       -> ClassLoader L         |---------->|  metadata của class B      |
  |       -> Class<?> / instance   |   ràng    |  ...                       |
  |                                |   buộc    +----------------------------+
  +--------------------------------+
```

Mũi tên sang Metaspace trong sơ đồ là **quan hệ quản lý và vòng đời**, không phải khẳng định một địa chỉ tham chiếu Java trực tiếp trỏ đến block native cụ thể.

### Heap, Metaspace, Compressed Class Space, Code Cache: đừng nhầm

| Thành phần | Chứa gì ở mức khái niệm? | Quan sát chính |
| --- | --- | --- |
| **Java heap** | Object instance, `ClassLoader` object, `java.lang.Class` mirror, collection/cache. | Heap metrics, `GC.class_histogram`, heap dump/GC roots. |
| **Metaspace** | Metadata lớp do JVM quản lý ngoài heap. | Memory pool `Metaspace`, `jcmd VM.metaspace`, NMT. |
| **Compressed Class Space** (khi được dùng) | Vùng riêng phục vụ phần metadata/klass cho compressed class pointers. | Pool `Compressed Class Space`, `VM.metaspace`, NMT. |
| **Code Cache** | Machine code do JIT biên dịch và cấu trúc code liên quan. | `jcmd Compiler.codecache`, JFR/JIT metrics. |
| **Thread stack** | Stack frame của thread ở native memory. | Thread metrics, native memory tools. |

**Quan trọng:** `java.lang.OutOfMemoryError: Metaspace` không đồng nghĩa `java.lang.OutOfMemoryError: Java heap space`. Tăng `-Xmx` chỉ tăng giới hạn heap; nó **không trực tiếp mở rộng giới hạn Metaspace**. Trong container có tổng memory cố định, thay đổi heap có thể ảnh hưởng lượng native memory còn lại, nhưng đó là bài toán tổng ngân sách bộ nhớ, không phải hai vùng là một.

### `used`, `committed`, `reserved` là ba đại lượng khác nhau

- **Used:** metadata thực sự được sử dụng theo báo cáo của JVM/pool.
- **Committed:** dung lượng vùng nhớ JVM đã cam kết dùng được; có thể lớn hơn `used`.
- **Reserved:** không gian địa chỉ ảo đã đặt trước cho cấu trúc bộ nhớ, **không nhất thiết đã commit/chiếm RAM vật lý**.

Ví dụ **giả định**:

```text
Metaspace:    used = 120 MiB, committed = 144 MiB
Class space:  reserved = 1024 MiB, committed = 20 MiB
```

Không được kết luận JVM đang chiếm 1 GiB RAM chỉ vì **reserved = 1024 MiB**. Cũng không được coi `used` giảm sau unload thì RSS của tiến trình bắt buộc giảm ngay: chunk/page có thể được JVM giữ để tái sử dụng, allocator và OS quyết định thời điểm trả lại bộ nhớ. Phiên bản HotSpot/collector khác nhau có thể có hành vi thu hồi khác nhau.

## 2. “Lớp sinh động” chính xác là gì?

Trong bài này, **lớp sinh động** được hiểu là *class definition được tạo hoặc nạp trong lúc JVM đang chạy*, thay vì chỉ có tập class cố định được nạp một lần khi startup.

Các nguồn thường gặp:

- **JDK dynamic proxy:** `Proxy.newProxyInstance(...)` tạo instance từ một proxy class do JVM tạo cho tập interface/loader tương ứng.
- **Framework tạo bytecode:** AOP, interception, ORM, lazy proxy, serializer, mocking và bytecode generation (Byte Buddy/CGLIB/ASM, tùy framework).
- **Plugin và hot deployment:** nạp lại JAR/module với loader mới để thay phiên bản plugin mà không tắt JVM.
- **Scripting, expression/rule engines, template compiler:** có thể phát sinh class cho mỗi đoạn mã/biểu thức nếu không có cơ chế tái sử dụng.
- **`ClassLoader.defineClass` hoặc `MethodHandles.Lookup.defineClass`:** định nghĩa class từ bytecode nếu API và quyền cho phép.

Không phải thao tác “động” nào cũng tạo **class mới**:

| Hành động | Có tạo class definition mới mỗi lần không? |
| --- | --- |
| `new Customer()` 100.000 lần | **Không.** Các instance cùng chia sẻ metadata của class do loader đã định nghĩa. |
| `Class.forName("com.acme.Customer")` lặp lại qua cùng loader | Thông thường chỉ tìm/tải lại **cùng định nghĩa class** trong phạm vi loader; không sinh 100.000 class mới. |
| `Proxy.newProxyInstance(loader, cùng danh sách interface)` lặp lại với **cùng loader** | JDK tái sử dụng proxy class đã sinh cho tổ hợp loader/interface phù hợp; chủ yếu tạo **instance** mới. |
| `Proxy.newProxyInstance(loaderMới, cùng interface)` với 100 loader khác nhau | Có thể tạo **100 proxy class definition khác nhau**, mỗi loader có vùng metadata/vòng đời riêng. |
| Reload cùng tên `com.acme.Plugin` bằng loader khác | Hai class có tên giống nhau có thể là **hai type khác nhau** trong JVM. |

**Danh tính class:** về mặt định nghĩa, phải xét **tên nhị phân + defining class loader**. Một tên class xuất hiện trong hai loader khác nhau không tạo ra cùng một type; ép kiểu giữa chúng có thể gây `ClassCastException`, dù tên in ra trùng nhau.

Ví dụ minh họa ngữ nghĩa:

```text
com.acme.Plugin @ Loader-v1  !=  com.acme.Plugin @ Loader-v2
```

Class loader thường dùng cơ chế **parent delegation**: loader con tham chiếu tới loader cha để nhờ tìm class. **Quan hệ mặc định là con → cha**, không phải cha tự giữ mọi loader con. Để kết luận loader con bị giữ lâu, phải tìm tham chiếu thực tế đi từ một GC root tới nó, chứ không chỉ vì app class loader là parent.

## 3. Vì sao vòng đời ClassLoader quyết định khả năng thu hồi metadata?

Giả sử mỗi lần hot deploy bạn tạo một loader mới và nạp các class của plugin:

```text
Lần 1: PluginLoader-A -> 1.000 class
Lần 2: PluginLoader-B -> 1.000 class
Lần 3: PluginLoader-C -> 1.000 class
...
```

Khi A bị thay bằng B, **A chỉ có cơ hội được thu hồi** nếu các tham chiếu mạnh giữ loader A/lớp/instance của A không còn live. JVM có thể unload class khi defining loader đủ điều kiện thu gom và việc class unloading được thực hiện. **GC không đảm bảo mỗi class sẽ unload ngay tại một thời điểm xác định**, kể cả khi loader đã trở nên unreachable; JVM implementation và cấu hình GC cũng quan trọng.

### Hai tình huống đối lập

**A. Vòng đời sạch (có thể unload):**

```text
registry(active) -> Loader-B -> class metadata B
              ...
Loader-A không còn được registry, thread hay cache giữ mạnh
    -> Loader-A có thể được GC
    -> class của Loader-A có thể unload
    -> metadata/chunk của Loader-A có thể được tái sử dụng/thu hồi
```

**B. Loader bị giữ ngoài dự kiến (nguy cơ leak):**

```text
GC root
  -> static Map trong ứng dụng sống lâu
      -> PluginDescriptor cũ
          -> Loader-A
              -> các class do A định nghĩa
                  -> Metaspace giữ metadata liên quan
```

Trong B, dù không còn request sử dụng plugin A, loader A vẫn reachable từ root. Class unloading thông thường không thể thu hồi các class do A định nghĩa khi loader A vẫn cần thiết. Nếu mỗi deploy tạo loader mới và tất cả loader cũ vẫn được giữ, lượng class metadata có thể tăng theo số lần deploy.

**Cần phân biệt:** một chu kỳ tham chiếu *chỉ giữa các object thuộc cùng plugin* mà **không reachable từ GC root bên ngoài** không tự gây leak. GC xử lý các chu kỳ không còn reachable. Ngược lại, chỉ **một** tham chiếu mạnh từ registry/thread sống lâu cũng đủ giữ cả cụm object/loader sống.

### Những GC root/đường giữ loader thường gặp

| Vị trí giữ | Ví dụ giữ mạnh | Hành động nên xem |
| --- | --- | --- |
| **Registry singleton/static của ứng dụng chính** | `Map<id, PluginContext>` vẫn chứa context/plugin cũ. | Remove entry khi unload, kiểm tra instance còn được tham chiếu ở đâu. |
| **Thread context class loader (TCCL)** | Worker trong pool có `getContextClassLoader()` trỏ loader plugin sau khi task xong. | Khôi phục TCCL trong `finally`; kiểm tra thread do plugin tạo. |
| **Executor, scheduler, timer, thread** | Task/closure/listener còn sống giữ Class/instance/loader plugin. | Cancel task, shutdown executor, unregister listener, join/terminate thread đúng cách. |
| **Cache reflection/method** | Cache có `Class<?>`, `Method`, `Constructor`, `MethodHandle`/factory của plugin. | Giới hạn scope, xóa cache khi unload, khóa cache theo vòng đời. |
| **ThreadLocal** | Giá trị thread-local của platform thread pool trỏ object class của plugin. | `remove()` trong lifecycle đúng ngữ cảnh; tránh trữ plugin context lâu. |
| **EventBus, JDBC/driver, service registry** | Listener/driver/provider do plugin đăng ký chưa hủy. | Thực hiện cleanup qua API đăng ký tương ứng. |
| **Weak-key cache thiết kế sai** | Value giữ strong reference ngược về key `ClassLoader`. | Xem đồ thị value → key; chỉ key weak không tự đảm bảo reclaim. |

Ví dụ về **Thread Context ClassLoader** (đoạn minh họa dùng trong một luồng có thể tái sử dụng):

```java
ClassLoader previous = Thread.currentThread().getContextClassLoader();
try {
    Thread.currentThread().setContextClassLoader(pluginLoader);
    runPluginTask();
} finally {
    Thread.currentThread().setContextClassLoader(previous);
}
```

Trong đó `pluginLoader` và `runPluginTask()` là các biến/hàm của ứng dụng thực tế, **đoạn này không phải một chương trình Java độc lập**. Ý chính là không để thread pool giữ TCCL của plugin cũ sau khi task đã hoàn thành.

### Bẫy của `WeakHashMap`

Đoạn sau **không đảm bảo** loader có thể được GC:

```java
Map<ClassLoader, Class<?>> cache = new WeakHashMap<>();
cache.put(pluginLoader, generatedClass);
```

Nếu `generatedClass` do `pluginLoader` định nghĩa, value `Class<?>` có thể giữ loader sống. Chuỗi đi từ map → **value mạnh** → class/loader → key tạo thành đường giữ key, khiến weak key không giúp. Đây là **đoạn minh họa**, không phải ví dụ khuyến nghị lưu trữ. Cần cache theo lifecycle hoặc cấu trúc yếu phù hợp **cả key lẫn value/graph**.

Một hiểu nhầm khác: `URLClassLoader.close()` chủ yếu đóng tài nguyên như file/JAR mà loader mở; **close không có nghĩa JVM unload mọi class của loader ngay lập tức**. Vẫn cần bỏ tham chiếu và chờ điều kiện unloading.

## 4. Đọc đúng ba nhóm số liệu: class count, Metaspace và loader count

Để chẩn đoán, **đừng chỉ nhìn một biểu đồ Metaspace used**. Theo dõi đồng thời:

1. **Class loading:** số class hiện đang loaded, số class đã từng loaded và số đã unloaded.
2. **Metaspace:** `used`, `committed`, (khi có) `reserved`; lưu ý cả Compressed Class Space.
3. **Class loaders:** số loader và phân bố số class/metadata theo loader hoặc loại loader.

### 4.1. `ClassLoadingMXBean` (chuẩn Java)

Giao diện `java.lang.management.ClassLoadingMXBean` có ba bộ đếm quan trọng:

| API | Ý nghĩa |
| --- | --- |
| `getLoadedClassCount()` | Số class **đang loaded hiện tại**. |
| `getTotalLoadedClassCount()` | Tổng số class **đã loaded kể từ khi JVM khởi động** (bộ đếm cộng dồn). |
| `getUnloadedClassCount()` | Tổng số class **đã được unloaded kể từ khi JVM khởi động** (bộ đếm cộng dồn). |

Do tính chất cumulative:

```text
deltaCurrentlyLoaded
    ≈ deltaTotalLoaded - deltaUnloaded
```

Dấu `≈` nhắc rằng đọc từng bộ đếm không nhất thiết là một snapshot nguyên tử duy nhất nếu ứng dụng vẫn đang nạp/unload class. **Tổng loaded tăng đều không đủ kết luận leak**: đó là bộ đếm chỉ tăng kể cả khi lớp unload bình thường. Cần so *currently loaded* và *unloaded*, cùng bối cảnh warm-up/deploy.

### 4.2. `MemoryPoolMXBean` cho Metaspace

Dùng `ManagementFactory.getMemoryPoolMXBeans()` để đọc pool có tên như `Metaspace`, `Compressed Class Space` (trên HotSpot thích hợp). `MemoryUsage.getUsed()` và `getCommitted()` báo **byte**, không phải KB; cần đổi đơn vị khi in.

Trường `getMax()` có thể là `-1` nếu JVM/pool không xác định một maximum cố định. Đừng coi `-1` là “vô hạn RAM thực tế”. Container memory, OS, địa chỉ ảo và các giới hạn JVM khác vẫn có thể làm cấp phát thất bại.

### 4.3. Mẫu hình nào đáng nghi?

| Quan sát theo thời gian | Cách hiểu hợp lý |
| --- | --- |
| Startup: class loaded và Metaspace tăng, sau warm-up ổn định | Thường bình thường do nạp class/JIT/framework khởi tạo. |
| Mỗi lần plugin reload: loader count và loaded class lại tăng; unloaded gần như đứng yên; Metaspace used tiếp tục tăng | **Nghi giữ loader cũ**; cần tìm GC roots, so với số plugin sống hợp lệ. |
| Tổng loaded tăng, unloaded cũng tăng, currently loaded đi ngang | Có tạo và unload class theo vòng đời; chưa có bằng chứng leak. |
| Metaspace committed giữ nguyên sau khi used giảm | Có thể vì vùng nhớ/chunk vẫn được giữ để tái dùng, không nhất thiết leak. |
| Metaspace used tăng nhưng class count tương đối ổn định | Có thể thay đổi metadata của các class, độ trễ GC/reclamation, cache hoặc thống kê; cần điều tra thêm, không quy ngay về số loader. |
| `Class` trong NMT có `reserved` rất lớn nhưng `committed` nhỏ | Chưa thể kết luận chiếm lượng RAM tương ứng `reserved`. |
| `OutOfMemoryError: Compressed class space` | Kiểm tra cấu hình compressed class space và class churn; không đánh đồng với heap OOME. |

**Dấu hiệu mạnh** là xu hướng lặp lại qua nhiều vòng deploy/workload tương đương và quan hệ reachability được xác thực, **không phải một snapshot**.

## 5. Công cụ chẩn đoán trên JVM thực: `jcmd`, NMT và log

Giả sử JVM ứng dụng có PID `12345` (**chỉ là ví dụ, thay bằng PID thật**). Dùng JDK tương thích, quyền attach phù hợp và cùng máy/PID namespace nếu JVM ở container.

### 5.1. Liệt kê loader, số class và Metaspace

```bash
jcmd -l
jcmd 12345 help VM.classloader_stats
jcmd 12345 VM.classloader_stats
jcmd 12345 VM.classloaders
jcmd 12345 VM.metaspace basic
```

- `VM.classloader_stats`: thống kê class loader, số class và các thông số vùng metadata. Output có thể gồm `ClassLoader`, `CLD*`, `Classes`, `ChunkSz`, `BlockSz` hoặc cấu trúc khác tùy JDK.
- `VM.classloaders`: in hệ phân cấp loader. Có thể chọn `show-classes` để xem lớp nhưng kết quả rất dài và chi phí có thể lớn; xem `help` trước.
- `VM.metaspace basic`: thống kê Metaspace cơ bản; đây là cách ít chi tiết hơn và theo tài liệu HotSpot không cần safepoint đối với chế độ `basic`.
- `VM.metaspace`: thông tin nhiều hơn; có thể dùng `show-loaders`/`show-classes` khi điều tra sâu và chấp nhận impact.

Ví dụ:

```bash
jcmd 12345 help VM.metaspace
jcmd 12345 VM.metaspace show-loaders
```

**Lưu ý vận hành:** `VM.metaspace` được tài liệu JDK phân loại **Impact: Medium**, tùy số class; không bật nhiều option chi tiết liên tiếp trên production đang quá tải. Trong Docker/Kubernetes, PID nhìn từ host có thể khác và `jcmd` có thể không có trong runtime image tối giản. Xác nhận `jcmd` nhìn thấy JVM và cùng effective user/quyền.

### 5.2. Native Memory Tracking (NMT)

NMT hữu ích để theo dõi các hạng mục native do HotSpot quản lý, trong đó có **Class/metadata**. Nó **không bao phủ mọi native allocation của thư viện bên ngoài**.

**Bật khi khởi động JVM** (không thể dùng `jcmd` bật NMT lần đầu cho JVM đang chạy nếu chưa khởi động với NMT):

```bash
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Trong terminal quản trị hợp lệ, tại thời điểm đã warm-up:

```bash
jcmd 12345 VM.native_memory summary
jcmd 12345 VM.native_memory baseline
```

Sau một giai đoạn có thao tác tải/reload lớp:

```bash
jcmd 12345 VM.native_memory summary.diff
```

`summary.diff` báo thay đổi từ baseline, gồm các nhóm native memory như `Class`. Phân biệt `reserved`, `committed`, và các chỉ số nội bộ metadata. Không diễn giải hạng mục `Class` là *số byte của các đối tượng `ClassLoader` trên Java heap*. NMT có overhead và phải chủ động chọn `summary` hay `detail` theo nhu cầu.

Nếu NMT không bật, `VM.native_memory summary` có thể báo rằng tracking chưa được kích hoạt. **Đừng coi đó là kết quả “0 byte native”**.

### 5.3. Log nạp/unload class và GC

Với HotSpot dùng unified logging (Java 9+), có thể dùng:

```bash
java -Xlog:class+unload=info -jar app.jar
```

Trong lab, log kiểu `class+unload` giúp kiểm tra class nào **thực sự được unload** sau khi loader không còn reachable. Không có log unload trong vài giây đầu không chứng minh leak: chưa có GC phù hợp, chưa đủ điều kiện thu gom, event chưa diễn ra hoặc log chưa bật.

Có thể thu GC log/heap metrics bằng cấu hình vận hành của hệ thống. Tăng độ chi tiết log class loading trên production có thể tạo lượng output rất lớn; chỉ bật có mục tiêu.

### 5.4. JFR và heap dump bổ trợ nhau ra sao?

- **JFR** (khi các event tương ứng được bật): có thể quan sát class-load/unload activity và thay đổi Metaspace theo thời gian; ví dụ type `jdk.ClassLoad`, `jdk.ClassUnload`, `jdk.ClassLoadingStatistics`, `jdk.MetaspaceSummary` trong các phiên bản/cấu hình thích hợp. Kiểm tra `jfr summary file.jfr` và metadata thay vì mặc định event nào cũng hiện.
- **Heap dump HPROF + Eclipse MAT**: tìm **đường tham chiếu tới `ClassLoader`/`Class<?>`/instance plugin**, ví dụ registry, ThreadLocal, thread context class loader, event listener. Sử dụng *Path to GC Roots* / *Dominator Tree* để điều tra vì sao loader vẫn reachable. Heap dump **không đo trực tiếp toàn bộ byte metadata nằm trong native Metaspace**.
- **`GC.class_histogram`**: có thể thấy số object `ClassLoader`, `Class<?>` và instance trên heap, nhưng `#bytes` là **shallow bytes của Java heap objects**; nó **không thay thế** `VM.metaspace` hoặc NMT.

Heap dump có thể rất lớn, ảnh hưởng pause và chứa dữ liệu nhạy cảm. Chỉ thu khi có thẩm quyền và tài nguyên, theo quy trình an toàn phù hợp.

## 6. Thực hành Java 17+: một loader mới sinh một proxy class, giữ hay thả?

Mục tiêu: dùng **API JDK thuần** để tạo nhiều **dynamic proxy classes**. Không cần Byte Buddy, CGLIB, Spring hoặc thư viện ngoài. Chúng ta tạo **100 ClassLoader instance khác nhau**, rồi sinh **một proxy class cho mỗi loader** bằng `Proxy.newProxyInstance`. Một cấu hình `loader + interface` lặp lại trong **cùng loader** thường tái sử dụng class đã sinh; vì thế demo cố ý tạo loader mới.

Tạo file **`LoaderMetaspaceDemo.java`**:

```java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryUsage;
import java.lang.ref.WeakReference;
import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.List;

public class LoaderMetaspaceDemo {
    public interface Greeting {
        String say();
    }

    private static final List<ClassLoader> RETAINED = new ArrayList<>();
    private static final List<WeakReference<ClassLoader>> WATCH = new ArrayList<>();

    private static void makeProxies(int count, boolean retain) {
        for (int i = 0; i < count; i++) {
            ClassLoader loader = new ClassLoader(Greeting.class.getClassLoader()) {};
            Object proxy = Proxy.newProxyInstance(
                    loader, new Class<?>[]{Greeting.class},
                    (object, method, args) -> "hello");
            if (!Proxy.isProxyClass(proxy.getClass())) {
                throw new AssertionError("Expected generated proxy");
            }
            WATCH.add(new WeakReference<>(loader));
            if (retain) {
                RETAINED.add(loader);
            }
        }
    }

    private static void show(String stage) {
        ClassLoadingMXBean classes = ManagementFactory.getClassLoadingMXBean();
        long reachableLoaders = WATCH.stream().filter(ref -> ref.get() != null).count();
        System.out.printf("%s: loaded=%d totalLoaded=%d unloaded=%d weakAlive=%d retained=%d%n",
                stage, classes.getLoadedClassCount(),
                classes.getTotalLoadedClassCount(), classes.getUnloadedClassCount(),
                reachableLoaders, RETAINED.size());

        for (MemoryPoolMXBean pool : ManagementFactory.getMemoryPoolMXBeans()) {
            if (pool.getName().equals("Metaspace")
                    || pool.getName().equals("Compressed Class Space")) {
                MemoryUsage usage = pool.getUsage();
                if (usage != null) {
                    System.out.printf("  %s usedKiB=%d committedKiB=%d%n",
                            pool.getName(), usage.getUsed() / 1024,
                            usage.getCommitted() / 1024);
                }
            }
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1
                || (!args[0].equals("hold") && !args[0].equals("release"))) {
            System.out.println("Usage: java LoaderMetaspaceDemo hold|release");
            return;
        }

        boolean retain = args[0].equals("hold");
        System.out.println("mode=" + args[0]);
        makeProxies(100, retain);
        show("after-create");

        System.gc(); // Chỉ là gợi ý; không đảm bảo unload lập tức.
        Thread.sleep(800);
        show("after-gc-hint");

        System.out.println("Press Enter to exit...");
        System.in.read();
    }
}
```

Chương trình **biên dịch bằng Java 17** (dù JDK hiện tại cao hơn):

```bash
javac --release 17 LoaderMetaspaceDemo.java
```

### 6.1. Chế độ `hold`: cố tình giữ loader

Terminal A:

```bash
java -Xms64m -Xmx192m LoaderMetaspaceDemo hold
```

Các dòng **cố định về nội dung**, còn số đo thay đổi theo hệ thống:

```text
mode=hold
after-create: loaded=... totalLoaded=... unloaded=... weakAlive=... retained=100
  Metaspace usedKiB=... committedKiB=...
  Compressed Class Space usedKiB=... committedKiB=...
after-gc-hint: loaded=... totalLoaded=... unloaded=... weakAlive=... retained=100
  Metaspace usedKiB=... committedKiB=...
  Compressed Class Space usedKiB=... committedKiB=...
Press Enter to exit...
```

Các dấu `...` trong khối trên **chỉ là ký hiệu mô tả số thay đổi, không phải output nguyên văn**. Nếu JVM không dùng pool Compressed Class Space thì dòng của pool đó có thể không có. `RETAINED` là một **static strong-reference list** trong lớp được nạp bởi app loader; nó giữ 100 loader con, do đó có thể giữ 100 proxy class tương ứng và metadata.

**Khi gặp dòng `Press Enter`**, giữ tiến trình chạy, mở terminal B để lấy số liệu rồi mới nhấn Enter thoát.

### 6.2. Chế độ `release`: không giữ loader mạnh

Sau khi tắt tiến trình `hold`, chạy một tiến trình mới:

```bash
java -Xms64m -Xmx192m LoaderMetaspaceDemo release
```

Trong chế độ này, `RETAINED` trống; danh sách `WATCH` chỉ giữ **`WeakReference<ClassLoader>`**. Khi method `makeProxies` kết thúc, demo không chủ động giữ strong reference tới các loader vừa tạo. Sau GC có thể thấy:

- `weakAlive` giảm, thậm chí về 0.
- `unloaded` tăng vì các generated proxy class có cơ hội unload.
- Metaspace `usedKiB` và Compressed Class Space `usedKiB` có thể giảm.
- `committedKiB` có thể giảm **hoặc vẫn giữ** vì memory management của VM.

**Không có con số bắt buộc**: JIT, JVM version, GC, class loading do management APIs và thời điểm chạy thay đổi kết quả. `System.gc()` chỉ là *gợi ý*; JVM có thể bỏ qua hoặc chưa thực hiện unloading (`-XX:+DisableExplicitGC`, GC khác...). **Không dùng `System.gc()` như một kỹ thuật sửa leak trên production.**

### 6.3. Thu số liệu bên ngoài khi chương trình đang chờ

Trong terminal B, tìm PID thật từ `jcmd -l` hoặc giá trị PID của tiến trình. Thay `12345` bằng PID thực tế:

```bash
jcmd -l
jcmd 12345 VM.classloader_stats
jcmd 12345 VM.metaspace basic
jcmd 12345 VM.metaspace show-loaders
```

Bạn có thể thu hai lần khi còn ở `hold` hoặc `release` trước khi thoát. Đối chiếu:

- Số `ClassLoader`/class tại thời điểm đo.
- `loaded`, `unloaded` từ chương trình demo.
- `used`/`committed` của Metaspace.
- Khác nhau giữa **có tham chiếu mạnh** và **không cố tình giữ tham chiếu mạnh**.

Nếu cần kiểm tra unload bằng log, chạy lại một trong hai mode:

```bash
java -Xlog:class+unload=info -Xms64m -Xmx192m LoaderMetaspaceDemo release
```

### 6.4. Vì sao đây là phép thử có ý nghĩa?

1. `Greeting` là **public interface** được app loader định nghĩa, để loader con có thể nhìn thấy qua delegation.
2. `new ClassLoader(Greeting.class.getClassLoader()) {}` tạo một **đối tượng loader con mới** mỗi vòng lặp.
3. `Proxy.newProxyInstance(...)` sinh hoặc tìm proxy class tương ứng với loader và interface; do loader khác nhau, các proxy class có **định danh type khác nhau**.
4. `WATCH` giữ weak reference: có thể quan sát loader đã bị GC hay chưa mà không cố tình giữ nó sống.
5. `RETAINED` giữ **strong reference** ở `hold`, mô phỏng registry/loader leak; ở `release` danh sách không giữ loader, để kiểm tra unloading **nếu JVM thực hiện**.
6. `ClassLoadingMXBean` đo **class count**, còn `MemoryPoolMXBean` đo **Metaspace used/committed**. Hai phép đo có đơn vị và ý nghĩa khác nhau.
7. Việc đọc bằng `jcmd` từ terminal khác thể hiện đúng quy trình chẩn đoán trên JVM đang sống.

**Giới hạn thí nghiệm:** demo chỉ minh họa vòng đời loader/proxy, không tái hiện toàn bộ cache của framework. Không nên so số tuyệt đối giữa hai tiến trình như một benchmark hiệu năng hay cỡ bộ nhớ trên mọi JVM; so **xu hướng và điều kiện tạo/giữ loader**.

## 7. Một ca phân tích production: Metaspace tăng mỗi lần hot-reload

Giả sử service hỗ trợ nạp lại bộ quy tắc hoặc plugin mà không restart JVM. Mỗi lần deploy một phiên bản plugin mới, service tạo loader mới.

Giả lập báo cáo sau nhiều lượt load/unload nghiệp vụ (**số liệu dưới đây là ví dụ, không phải kết quả JVM thật**):

| Giai đoạn | Plugin đang active | Class loader còn reachable | Currently loaded classes | Metaspace used |
| --- | ---: | ---: | ---: | ---: |
| Sau warm-up | 1 | 1 liên quan plugin | 8.000 | 90 MiB |
| Sau 5 reload | 1 | 6 liên quan plugin | 13.500 | 145 MiB |
| Sau 10 reload | 1 | 11 liên quan plugin | 19.000 | 205 MiB |
| Sau cleanup + GC phù hợp | 1 | 1 liên quan plugin | 8.500 | 98 MiB |

**Bước phân tích đúng:**

1. Ghi mốc thời gian reload, số plugin được phép active, JDK/GC và tỷ lệ request.
2. Chụp `VM.classloader_stats` sau mỗi vài lần reload; xem các loader **cũ** có còn với lượng class tương tự không.
3. Theo dõi `ClassLoadingMXBean`: `getTotalLoadedClassCount()` phải tăng nếu tạo class mới; vấn đề nằm ở `getLoadedClassCount()` không quay xuống và `getUnloadedClassCount()` không tăng như kỳ vọng sau các vòng đời kết thúc.
4. Theo dõi Metaspace used/committed, NMT `Class`, GC/class unload log để củng cố cùng một xu hướng.
5. Thu heap dump nếu đủ thẩm quyền/tài nguyên. Dùng MAT **Path to GC Roots** để tìm chuỗi giữ loader cũ, ví dụ `PluginRegistry -> historicalContexts -> ClassLoader` hoặc pool thread `contextClassLoader`.
6. Kiểm tra code cleanup khi unload: deregister listener/driver, cancel task, cleanup ThreadLocal/TCCL, xóa cache reflection/proxy nếu không còn dùng.
7. Chạy lại workload tương đương và đo trước/sau. **Giảm loaded class/Metaspace qua nhiều chu kỳ** là bằng chứng tốt hơn một lần `System.gc()` không thấy thay đổi.

Nếu số loader chỉ tăng cùng với số plugin **thực sự còn active**, không nhất thiết có leak. Nếu Metaspace used tăng rồi giữ plateau do cache ấm, không nhất thiết có leak. **Cần một vòng đời được kỳ vọng kết thúc nhưng tham chiếu không được bỏ**.

## 8. Chẩn đoán root cause: class loader nào bị giữ bởi ai?

Khi nghi leak, bạn cần tìm **retaining path** thay vì chỉ tăng giới hạn Metaspace.

### Checklist đường tham chiếu

```text
GC root
  ├─ singleton/static registry -> PluginContext -> PluginClassLoader
  ├─ pool Thread -> contextClassLoader -> PluginClassLoader
  ├─ pool Thread -> ThreadLocal value -> plugin instance -> PluginClassLoader
  ├─ scheduler/Executor -> pending task -> closure -> plugin class/instance
  ├─ event bus -> listener -> plugin instance
  └─ reflection/proxy cache -> Class<?>/Method -> PluginClassLoader
```

Đây là **sơ đồ các khả năng**, không khẳng định mọi JVM ứng dụng có đủ các đường trên.

Một số dấu hiệu trong heap dump:

- Nhiều object class loader cùng loại/tên tương đương nhưng gắn bản triển khai plugin cũ.
- Một registry sống lâu giữ cache có kích thước tăng theo mỗi reload.
- Một thread do plugin tạo không dừng hoặc một executor dùng ThreadLocal cũ.
- `Class<?>`/reflection object từ loader cũ còn được singleton app giữ.

**Đừng vội xóa cache bừa bãi:** class/proxy cache có thể cần cho tính đúng đắn và hiệu năng. Thiết kế theo scope/TTL/vòng đời, kiểm thử trường hợp còn request đang xử lý, và không tháo loader khi class còn cần thiết.

### Nguyên tắc thiết kế cho hệ thống có hot reload

- **Một lifecycle rõ ràng:** `load -> active -> quiesce -> close/unregister -> drop references -> observe unload`.
- **Cache theo loader/plugin version:** không để global cache giữ mọi `Class`, `Method`, factory hoặc bytecode model mãi mãi.
- **Khôi phục TCCL:** sử dụng `try/finally` khi tạm đổi context class loader.
- **Dọn ThreadLocal và background task:** `remove()` đúng luồng, hủy đăng ký listener, shutdown executor do plugin sở hữu.
- **Tái sử dụng class/proxy khi hợp lệ:** tránh sinh thêm định nghĩa class mỗi request khi một lớp/cache dùng chung đã đủ.
- **Tránh map có value tham chiếu ngược loader:** weak key một mình không đảm bảo thu gom.
- **Thực hiện giám sát dài hạn:** classload/unload rates, số loader sau mỗi reload, Metaspace used/committed, OOME và container RSS.

## 9. Metaspace OOME: tăng giới hạn hay sửa leak?

Hai lỗi thường gặp:

```text
java.lang.OutOfMemoryError: Metaspace
java.lang.OutOfMemoryError: Compressed class space
```

Cần phân biệt nguyên nhân:

| Nhóm nguyên nhân | Ví dụ | Phản ứng phù hợp |
| --- | --- | --- |
| **Giới hạn cấu hình quá thấp** | Ứng dụng hợp lệ cần nhiều class, nhưng `-XX:MaxMetaspaceSize` đặt quá nhỏ. | Đo live set/peak thực tế rồi điều chỉnh phù hợp tổng memory budget. |
| **Class-loader leak** | Loader cũ bị static registry/thread giữ sau mỗi deploy. | Sửa retaining path; tăng giới hạn chỉ trì hoãn OOME. |
| **Tạo class quá nhiều dù vòng đời hợp lệ** | Biên dịch biểu thức hoặc tạo proxy mới cho từng request/tenant. | Giảm class churn, caching/giới hạn số phiên bản, tránh generate class không cần thiết. |
| **GC/unloading chưa được kích hoạt theo kỳ vọng** | Không có collector cycle phù hợp, cấu hình tắt class unloading. | Xác nhận log/cấu hình GC; đừng lấy `System.gc()` làm bảo đảm. |
| **Native/container memory cạn** | Heap + Metaspace + thread stack + code cache vượt memory limit. | Xem ngân sách toàn tiến trình, NMT/OS/container; không chỉ sửa `-Xmx`. |

Các option HotSpot đáng biết:

- `-XX:MaxMetaspaceSize=...`: **giới hạn** tổng chi phí Metaspace theo cơ chế HotSpot; khi vượt có thể gặp `OutOfMemoryError: Metaspace`.
- `-XX:MetaspaceSize=...`: ngưỡng có ảnh hưởng tới việc JVM cân nhắc GC do áp lực metadata; **không phải cách ấn định Metaspace phải cấp trước đúng bấy nhiêu byte**.
- `-XX:CompressedClassSpaceSize=...`: giới hạn vùng class space nếu compressed class pointers được bật; không đồng nghĩa heap `-Xmx`.
- `-XX:NativeMemoryTracking=summary` hoặc `detail`: để NMT thu được số liệu ngay từ startup; có overhead.
- Các cờ class unloading/GC có thể thay đổi theo JDK và collector; kiểm tra `java -XX:+PrintFlagsFinal` hoặc `jcmd <PID> VM.flags -all` khi cần, **không tự thay cờ production chỉ để ép một thí nghiệm**.

**Không có “con số MaxMetaspaceSize tốt nhất cho mọi service”**. Một dịch vụ chạy plugin, framework proxy hoặc có số tenant/phiên bản khác sẽ cần bộ nhớ khác. Lấy baseline sau warm-up, peak lúc deploy, biên dự phòng và memory limit của container làm cơ sở; giữ monitoring/OOME alert.

## 10. Bảng phân biệt chẩn đoán hay nhầm

| Câu nói vội | Cách hiểu đúng |
| --- | --- |
| “Tạo 1 triệu object chắc chắn làm Metaspace tăng 1 triệu lần.” | Object cùng class dùng chung class metadata; heap mới là nơi cấp phát instance. |
| “Gọi reflection hay `Class.forName` nhiều lần đều tạo class mới.” | Cùng tên và defining loader thường chỉ có một class definition; cần phân biệt **load** với **lookup**. |
| “Hai class cùng tên luôn là cùng type.” | Định danh type còn phụ thuộc defining class loader. |
| “Một proxy instance = một proxy class mới.” | JDK proxy class có cơ chế tái sử dụng theo loader/interface; tạo loader mới mới đáng chú ý trong demo. |
| “Chỉ cần không giữ proxy instance thì Metaspace tự giảm.” | Nếu loader vẫn được registry/thread/cache giữ, class metadata có thể còn. |
| “Parent loader luôn giữ tất cả child loader.” | Child thường trỏ parent; chiều ngược lại cần **đường tham chiếu thực tế**, không mặc định. |
| “Static field ở plugin luôn làm leak loader.” | Static reference tạo vòng bên trong loader chưa đủ nếu cả nhóm không còn reachable từ GC root bên ngoài. |
| “`WeakHashMap<ClassLoader, Class<?>>` luôn bảo vệ khỏi leak.” | Value có thể giữ key/loader sống, làm yếu hóa key không còn ý nghĩa. |
| “`URLClassLoader.close()` sẽ unload ngay mọi class.” | Close giải phóng một số tài nguyên của loader; unload cần điều kiện reachability và JVM GC. |
| “`System.gc()` bảo đảm unload.” | Chỉ là gợi ý, có thể bị bỏ qua hoặc chưa làm công việc class unloading. |
| “Metaspace reserved = RAM đang dùng.” | Reserved là không gian địa chỉ ảo; cần xem committed/used và RSS thực tế. |
| “NMT `Class` là byte của `ClassLoader` trên heap.” | NMT đo hạng mục native của JVM; heap objects là vùng khác. |
| “Tổng loaded class tăng => leak.” | Bộ đếm cumulative luôn tăng; cần **currently loaded, unloaded**, loader counts và vòng đời. |
| “`-Xmx` lớn hơn sẽ sửa OOME Metaspace.” | `-Xmx` giới hạn heap, không trực tiếp sửa leak/cap native metadata. |
| “Tăng `MaxMetaspaceSize` là sửa tận gốc.” | Có thể cần khi cấu hình quá thấp, nhưng **không thay thế** sửa retaining path khi có leak. |

## 11. Quy trình thực hành chẩn đoán có thể áp dụng

**Trước khi tái hiện:**

1. Ghi PID, JDK version, GC, heap limit, metaspace limit, container memory limit, thời gian startup/warm-up/deploy.
2. Chụp baseline `VM.classloader_stats`, `VM.metaspace basic`, metrics `ClassLoadingMXBean`.
3. Nếu đã bật NMT, lấy `VM.native_memory baseline`; nếu chưa bật, lên kế hoạch enable ở lần restart được phê duyệt, không cố bật bằng `jcmd` khi đang chạy.

**Khi tạo tải/redeploy có kiểm soát:**

4. Lặp lại cùng một nghiệp vụ/tác vụ reload với số lượng và khoảng thời gian tương đương.
5. Chụp loaded/unloaded class count và Metaspace used/committed ở nhiều mốc; ghi số loader cũ còn lại.
6. Đọc log class unload/JFR khi có và lưu ý threshold/chi phí quan sát.
7. Nếu loader cũ bất thường, tìm GC root của **loader cụ thể** qua heap dump.

**Khi đưa ra kết luận:**

8. Xác định loader/lớp có **lẽ ra được giải phóng** không, hay vẫn thuộc plugin đang hoạt động.
9. Ghi rõ đường giữ mạnh và điểm sửa: static registry, thread context, listener, cache, task.
10. Đo sau sửa qua nhiều vòng chạy: loader cũ có biến mất, `unloaded` tăng phù hợp, Metaspace có ổn định theo tải hay không? Không yêu cầu `committed` hoặc RSS phải giảm về một con số cố định ngay lập tức.

**Câu kết luận có trách nhiệm:** “Sau 10 lượt reload, số loader cũ còn reachable tăng từ 0 lên 10 và Metaspace used tiếp tục tăng; heap dump chỉ ra một static registry giữ các loader cũ. Sau khi remove registry entries và hủy listener, các loader đủ điều kiện unload và xu hướng Metaspace ổn định.” Đây mạnh hơn câu “Metaspace tăng, nên Java bị leak”.

## 12. Câu hỏi tự kiểm tra

1. **Tại sao nhiều instance của cùng một class không làm số class definition tăng tương ứng?** Vì các instance dùng chung metadata của class do một loader định nghĩa.
2. **Một class có cùng tên nhưng được hai loader định nghĩa có phải cùng type không?** Không. Defining loader là thành phần của định danh runtime type.
3. **Chỉ số nào phân biệt class churn với class leak?** Kết hợp currently loaded, total loaded, unloaded, loader count, Metaspace used và vòng đời; **total loaded đơn lẻ không đủ**.
4. **Vì sao chỉ weak-key cache có thể vẫn giữ loader?** Value có thể giữ class của loader, dẫn ngược tới key/loader, tạo đường tham chiếu mạnh.
5. **Chỉ `URLClassLoader.close()` có bảo đảm unload không?** Không; cần bỏ strong references và GC/class unloading phù hợp.
6. **`VM.classloader_stats` và `GC.class_histogram` khác nhau ở đâu?** Cái đầu tập trung loader/classes/metadata; cái sau thống kê instance/shallow bytes trên Java heap.
7. **Nếu Metaspace committed không giảm nhưng used giảm thì chắc chắn leak không?** Không; vùng committed có thể được JVM giữ để tái sử dụng.
8. **Vì sao `System.gc()` trong demo không phải phép kiểm chứng tuyệt đối?** Vì đó là hint; GC và unloading không được bảo đảm ngay.
9. **Tại sao TCCL của thread pool đáng quan tâm?** Thread sống lâu hơn plugin có thể giữ loader cũ qua `contextClassLoader`.
10. **Khi nào tăng `MaxMetaspaceSize` là hợp lý?** Khi số đo cho thấy live metadata hợp lệ cần nhiều hơn cấu hình hiện tại, có đủ memory budget; không coi đó là bản sửa cho loader leak.

## Tài liệu tham khảo chính thức

- [Java SE 21 — Tối ưu quản lý bộ nhớ metadata / Metaspace](https://docs.oracle.com/en/java/javase/21/gctuning/other-considerations.html).
- [Java SE 21 — `jcmd`: `VM.classloader_stats`, `VM.classloaders`, `VM.metaspace`, `VM.native_memory`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html).
- [Java SE 21 — Native Memory Tracking: enable, baseline và diff](https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html).
- [Java SE 17 — `ClassLoadingMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ClassLoadingMXBean.html).
- [Java SE 21 — Chẩn đoán memory leaks](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-memory-leaks.html).
- [Java Language Specification §12.7 — Unloading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-12.html#jls-12.7).
- [Java SE 21 — Dynamic Proxy API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/reflect/Proxy.html).
