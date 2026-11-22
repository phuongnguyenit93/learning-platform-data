# 13.8. Chẩn đoán metaspace tăng, số lớp hoặc class loader tăng và khả năng unload

Khi bộ nhớ tiến trình Java tăng dù heap vẫn tương đối ổn định, một khả năng cần kiểm tra là **metaspace**: vùng bộ nhớ native mà HotSpot sử dụng để quản lý metadata của các lớp đã được nạp. Trong ứng dụng có plugin, hot reload, proxy sinh động, script engine hoặc triển khai lại module nhiều lần, metaspace tăng có thể đi kèm với **số class đang được nạp tăng**, **số class loader còn sống tăng**, hoặc cả hai. Tuy nhiên, ba chỉ số không đồng nghĩa và không đủ để kết luận rò rỉ nếu xem riêng lẻ.

Mục tiêu chẩn đoán là trả lời lần lượt: **memory nào đang tăng?** → **class mới hay class loader mới xuất hiện?** → **có class unloading sau chu kỳ GC phù hợp không?** → **loader nào còn reachable và bị giữ bởi tham chiếu nào?**. Bài này tập trung vào HotSpot/OpenJDK 17+, với các ví dụ Java 17 có thể chạy độc lập. Tên metric và chi tiết GC có thể khác theo JDK, collector và công cụ quan sát.

## 1. Metaspace là gì, quan hệ với class loader ra sao?

Khi JVM nạp một class, ngoài đối tượng `java.lang.Class` biểu diễn class trên Java heap, JVM còn cần metadata nội bộ: cấu trúc mô tả class, phương thức, field, runtime constant pool, quan hệ kế thừa, một phần cấu trúc để hỗ trợ thực thi và các thành phần liên quan. HotSpot cấp phát phần metadata này qua bộ quản lý **metaspace** trong native memory; đây **không phải** một vùng chiếm dung lượng trong `-Xmx` theo nghĩa Java heap.

Với HotSpot, metadata thường được quản lý theo **vòng đời của defining class loader**. Mỗi loader định nghĩa class sở hữu những cấu trúc quản lý vùng cấp phát metadata liên quan. Khi GC xác định loader có thể được thu hồi và tiến hành class unloading, metadata của các class do loader đó định nghĩa có thể được giải phóng hoặc tái sử dụng, đồng thời một phần bộ nhớ đã commit có thể được uncommit.

Mô hình khái niệm:

```text
GC roots ──> ứng dụng / registry / thread / Class<?> / instance
                    │
                    └──> ClassLoader còn reachable
                                │ defines
                                ├──> PluginA (metadata trong metaspace)
                                ├──> PluginB (metadata trong metaspace)
                                └──> Proxy$123 (metadata trong metaspace)

Nếu class loader còn reachable, những class do nó định nghĩa
không thể được unload chỉ vì ứng dụng đã ngừng gọi method.
```

**Phân biệt quan hệ class–loader:**

- Một **defining class loader** là loader thực sự định nghĩa class. Một **initiating loader** có thể yêu cầu nạp nhưng class được định nghĩa bởi parent; không nên đếm mọi yêu cầu `loadClass()` như một class mới.
- Class có cùng tên nhị phân nhưng do hai defining loader khác nhau định nghĩa là **hai class khác nhau** đối với JVM. Vì vậy nạp lại cùng một JAR bằng nhiều loader có thể làm số class/metaspace tăng.
- Ứng dụng thường dùng loader sống lâu (bootstrap/platform/application) để nạp phần lớn class. Những class này ở lại đến cuối vòng đời JVM là bình thường.
- Class unloading là một dạng tối ưu do JVM/GC thực hiện; code ứng dụng không được dựa vào thời điểm unload cụ thể.

### Metaspace khác heap, RSS và compressed class space

| Chỉ số/vùng nhớ | Chứa gì hoặc biểu thị gì? | Sai lầm thường gặp |
| --- | --- | --- |
| `heap used` | Object/array sống hoặc chưa được GC thu hồi trên Java heap. | Dùng nó làm số liệu metaspace. |
| `Metaspace used` | Lượng metadata đang được HotSpot báo là đã dùng. | Coi mọi sự tăng là leak. |
| `Metaspace committed` | Phần bộ nhớ metaspace đã commit, có thể lớn hơn used. | Coi committed không giảm ngay là unload thất bại. |
| `Metaspace reserved` | Không gian địa chỉ ảo đã giữ chỗ; phần lớn có thể chưa commit. | Cộng trực tiếp vào RSS như bộ nhớ vật lý đang dùng. |
| `Compressed Class Space` | Vùng riêng cho một phần metadata class khi cơ chế compressed class pointers được bật. | Nhầm 1 GiB reserved mặc định với 1 GiB RAM thực tiêu thụ. |
| `RSS`/container memory | Bộ nhớ hiện diện của toàn tiến trình/container theo hệ điều hành. | Quy mọi RSS tăng cho metaspace, bỏ qua stack, direct buffer, JIT/code cache và native allocations. |

Khi HotSpot sử dụng compressed class pointers, nó quản lý metadata trong các khu vực logic khác nhau cho `class space` và `non-class metaspace`. Công cụ có thể hiển thị dòng “Metaspace” và “class space” riêng, hoặc một metric metaspace tổng hợp. **Đọc định nghĩa cụ thể của từng metric trước khi cộng/trừ**, tránh double-counting. Dung lượng `reserved` cao không tự chứng tỏ bộ nhớ vật lý bị tiêu thụ; `committed` và `used` hữu ích hơn để đánh giá tăng trưởng, nhưng vẫn cần đối chiếu RSS.

JDK 16+ có **Elastic Metaspace** (JEP 387), cho phép HotSpot trả những vùng metadata không dùng về hệ điều hành hiệu quả hơn sau unloading. Tuy nhiên, allocator còn các chunk tái sử dụng, mức committed và RSS có thể phản ứng trễ; **không được suy ra unload chỉ từ một đoạn committed giảm, hoặc suy ra không unload chỉ vì committed chưa giảm**.

## 2. Khi nào một class thực sự có thể được unload?

Java Language Specification đặt điều kiện nền tảng: một class chỉ có thể được unload khi **defining loader của class có thể được GC thu hồi**. Đối với class do bootstrap loader nạp, class unloading không diễn ra theo cách này. HotSpot cần một lần xử lý GC có hỗ trợ unloading để phát hiện và giải phóng metadata phù hợp.

Một loader muốn trở thành ứng viên thu hồi cần không còn đường tham chiếu mạnh từ GC roots giữ loader, các class do nó định nghĩa, object thuộc những class đó hoặc những cấu trúc liên quan còn sống. Các trường hợp cần kiểm tra:

- Một `Class<?>` hoặc instance của class do loader định nghĩa còn nằm trong cache/registry dài hạn.
- Thread đang chạy code từ plugin, hay giữ `Thread.contextClassLoader` trỏ vào loader cũ.
- `ThreadLocal`, listener, callback, executor, task được giữ bởi thread hoặc service sống lâu.
- Framework quản lý plugin/module giữ reference trong bản đồ quản lý, scheduler, MBean/driver registry hoặc static field của **class thuộc loader sống lâu**.
- Agent/native/JNI/JVMTI hoặc framework instrumentation giữ tham chiếu khiến object graph chưa đủ điều kiện thu hồi.

**Đừng hiểu quá mức về `static`:** một field static tự tham chiếu tới object trong chính class/loader sắp bị thu hồi có thể nằm trong một cụm đối tượng không còn reachable; chỉ vì tồn tại static field không mặc nhiên gây leak. Điều đáng ngại là có **đường từ root sống lâu bên ngoài loader** (ví dụ registry của application loader) quay lại giữ loader/plugin.

`URLClassLoader.close()` đóng các tài nguyên I/O (như JAR đã mở) liên quan đến loader; **nó không bắt JVM unload các class ngay lập tức**. Tương tự, gán biến thành `null` chỉ loại bỏ một cạnh tham chiếu cụ thể; nó không bảo đảm mọi đường từ GC roots đã mất. `System.gc()` là một yêu cầu GC có thể bị bỏ qua, và không bảo đảm class unloading diễn ra ngay.

## 3. Bốn nhóm số liệu cần đặt cạnh nhau

### 3.1. Class count: đang nạp, đã từng nạp, đã unload

`ClassLoadingMXBean` cung cấp ba bộ đếm:

- `getLoadedClassCount()`: số class hiện đang được JVM báo là loaded.
- `getTotalLoadedClassCount()`: tổng class đã loaded từ lúc JVM khởi động, **tích lũy**, không giảm.
- `getUnloadedClassCount()`: tổng class đã unloaded, **tích lũy**, không giảm.

Giả sử hai mẫu cách nhau 10 phút:

```text
t0: current=10_000, total=20_000, unloaded=10_000
t1: current=10_050, total=30_000, unloaded=19_950
```

Ở đây đã có nhiều hoạt động class load/unload, nhưng **số class hiện tại chỉ tăng 50**. Nếu chỉ nhìn `totalLoaded` tăng 10.000, bạn có thể kết luận nhầm “10.000 class bị rò rỉ”. Công cụ lấy mẫu không nhất thiết chụp cả ba bộ đếm tại cùng một thời điểm nguyên tử, nên không dựa vào phép `total − unloaded = current` như một bất biến chính xác tuyệt đối trong mọi bản ghi.

Ngược lại, nếu `current loaded` tăng liên tục sau nhiều chu kỳ GC so sánh được, đó là tín hiệu cần tìm nguồn class/loader mới còn sống. Không có ngưỡng “trên N class là leak” áp dụng cho mọi chương trình.

### 3.2. Class loader: số lượng, loại và vòng đời

Số loader đang sống cần đo bằng công cụ có khả năng liệt kê loader hoặc `ClassLoaderData`, ví dụ `jcmd <pid> VM.classloader_stats`. **Không dùng `totalLoadedClassCount` làm số lượng class loader**. Một loader có thể định nghĩa hàng nghìn class; nhiều loader khác nhau có thể chỉ định nghĩa một class mỗi cái.

Khi đọc thống kê, cần phân biệt loader đang hoạt động hợp lệ (ví dụ plugin còn được sử dụng) với loader **của phiên bản/deployment cũ** đáng ra đã được giải phóng. Sau mỗi lượt redeploy/reload, tìm dấu hiệu số loader thế hệ cũ tăng mà không giảm trong các chu kỳ GC phù hợp.

### 3.3. Metaspace: used, committed, reserved, class space

Lấy chuỗi thời gian `used` và `committed` của metaspace, cùng số liệu `Compressed Class Space` nếu JVM bật và công cụ cung cấp. Giữ đúng đơn vị KiB/MiB và scope (pool, instance, JVM). Một dashboard chỉ hiển thị tổng reserved chưa đủ để chẩn đoán metadata retention.

Cùng một số lượng class, committed có thể cao hơn do **chunk allocation, phần trống trong chunk, cấu trúc quản lý hoặc chiến lược thu hồi**. Với class loader còn sống, metadata đã cấp phát không phải lúc nào cũng có thể giải phóng từng phần tùy ý.

### 3.4. Hoạt động GC và class unloading

Ghi lại thời điểm collector chạy những pha có thể unload class, số unload event, và sự thay đổi `current loaded`, `metaspace used` sau đó. Trong G1, những chu kỳ/pha khác nhau có khả năng khác nhau; **young GC đơn lẻ không đủ chứng minh JVM đã có cơ hội xử lý toàn bộ metadata của các loader không còn dùng**. Với collector đồng thời, unloading có thể xảy ra theo lịch riêng của chu kỳ và các dấu vết sẽ không nhất thiết khớp một điểm giảm heap used.

## 4. Những hình dạng thường thấy và cách diễn giải

| Quan sát đồng thời | Giả thuyết hợp lý | Cần kiểm chứng |
| --- | --- | --- |
| `totalLoaded` tăng, `unloaded` cũng tăng; `current` và metaspace used ổn định | Nạp/unload class theo vòng đời bình thường. | Xem số loader phiên bản cũ, GC unloading và tải. |
| `current` tăng, metaspace used tăng, loader count gần như ổn định | Một hoặc vài loader sống lâu liên tục định nghĩa thêm class, ví dụ dynamic bytecode/proxy. | Lọc nhóm class và call site sinh class; kiểm tra cache/khóa duy nhất. |
| Loader count tăng cùng `current` và metaspace used, nhiều loader phiên bản cũ | Có thể đang giữ plugin loader cũ sau reload/deploy. | Tìm reference đến các loader cũ bằng heap dump/path to GC roots. |
| Loader count tăng lúc deploy rồi giảm sau GC phù hợp, metaspace used giảm/ổn định | Churn theo lifecycle, có thể bình thường. | So sánh qua vài chu kỳ, kiểm tra peak có vượt memory budget không. |
| Metaspace committed tăng nhưng used ổn định, class/loader count không tăng | Chunk/capacity/reuse hoặc biến động native allocator; chưa đủ kết luận leak. | Xem `VM.metaspace`, NMT, GC phase và xu hướng dài hạn. |
| RSS tăng nhưng metaspace used/committed ổn định | Nghi ngờ bộ nhớ native khác, heap committed, direct buffer, stack, code cache... | Xem NMT, OS/container memory và pool tương ứng. |
| Metaspace used tăng sau startup rồi ổn định | Warm-up: lazy class loading, framework/proxy initialization. | So thời điểm warm-up, đồng bộ workload; đánh giá plateau. |
| `OutOfMemoryError: Metaspace` hoặc `Compressed class space` | Cạn budget metadata hoặc giới hạn liên quan, chưa tự động chứng minh leak. | Kiểm tra VM flags, class/loader growth, native budget, log và dump phù hợp. |

## 5. Quy trình chẩn đoán theo thời gian

1. **Khóa bối cảnh:** ghi JDK/vendor/version, collector, `-Xmx`, `-XX:MaxMetaspaceSize` nếu đặt, `CompressedClassSpaceSize`, workload, thời điểm deploy/reload, PID/instance và container memory limit.
2. **Lấy baseline sau warm-up:** thu `Metaspace used/committed`, `Compressed Class Space`, `current/total/unloaded class`, số loader và RSS. Nếu chỉ có một snapshot, chưa kết luận xu hướng.
3. **Quan sát lặp lại:** lấy mẫu sau các lượt deploy/reload hoặc theo cửa sổ thời gian cố định; chụp timestamp và request rate cùng lúc. Dùng cùng công cụ/đơn vị để các mốc so sánh được.
4. **Kiểm tra unloading thực tế:** đối chiếu `-Xlog:class+unload`, GC logs và `unloaded` counter sau những chu kỳ GC có hỗ trợ unload. Nếu chưa có chu kỳ phù hợp, không dùng việc counter chưa tăng để kết luận leak.
5. **Xác định loader/class tăng:** phân tích `VM.classloader_stats`, `VM.metaspace` (khi JVM hỗ trợ), class histogram/JFR hoặc heap dump; ghi những loader có metadata lớn và loader của phiên bản cũ không biến mất.
6. **Tìm đường giữ tham chiếu:** mở heap dump bằng Eclipse MAT/VisualVM, truy `ClassLoader` / `Class<?>` / instance → `Path to GC Roots`. Tìm registry, thread context loader, `ThreadLocal`, listener, MBean, static cache ở loader sống lâu.
7. **Kiểm chứng bằng thay đổi có kiểm soát:** sửa điểm giữ reference hoặc giảm việc sinh class trùng lặp; lặp lại cùng workload/reload; xác nhận class unloading trở lại và metaspace used không tiếp tục tăng ngoài dự kiến.

Cần ghi lại số liệu trước/sau **điều kiện tương đương**. Sau mỗi deploy, JVM có thể phải biên dịch JIT, nạp framework class và tạo proxy nhiều hơn; vì vậy baseline quá sớm khi chưa warm-up sẽ thổi phồng mức tăng tự nhiên.

## 6. Công cụ HotSpot/OpenJDK cần biết

### 6.1. `jcmd`: snapshot loader và metaspace

Chạy bằng user có quyền attach vào cùng JVM; `<pid>` là chỗ điền PID thực, **không gõ nguyên chuỗi này vào shell**.

```bash
# Liệt kê PID JVM (trên host/vùng PID namespace phù hợp)
jcmd -l

# Xem các lệnh khả dụng và help chính xác của JVM đang chạy
jcmd <pid> help
jcmd <pid> help VM.classloader_stats
jcmd <pid> help VM.metaspace

# Số class/bytes và thống kê theo class loader
jcmd <pid> VM.classloader_stats

# Thống kê metaspace nếu lệnh có mặt ở phiên bản JVM này
jcmd <pid> VM.metaspace

# Khi hỗ trợ: tách mức sử dụng theo loader
jcmd <pid> VM.metaspace show-loaders
```

`VM.classloader_stats` cho thông tin loader và các thống kê liên quan; cách hiển thị phụ thuộc JDK. `VM.metaspace` và option `show-loaders` có thể chỉ có ở một số phiên bản/phân phối; **luôn kiểm tra `jcmd <pid> help`**. Output `VM.metaspace` thường gồm các khái niệm như used, committed, reserved, capacity hoặc free chunks; nếu thấy hàng nghìn MiB reserved nhưng committed thấp hơn nhiều, không suy luận JVM đang sử dụng từng đó RAM vật lý.

Công cụ `jcmd` có thể lấy safepoint hoặc gây chi phí tùy lệnh và số loader/class; tránh gọi liên tục ở tần suất cao trên hệ thống rất lớn. Nếu ứng dụng trong container, cần truy đúng PID namespace và user; lệnh trên host chưa chắc thấy PID nội bộ theo đúng cách.

### 6.2. `jstat`: chuỗi thời gian nhanh

```bash
# Mỗi 1.000 ms lấy một mẫu, tổng 10 mẫu
jstat -class <pid> 1000 10

# Theo dõi capacity của các không gian metadata (nếu JVM báo)
jstat -gcmetacapacity <pid> 1000 10

# Theo dõi tỷ lệ sử dụng các vùng GC / metaspace
jstat -gcutil <pid> 1000 10
```

`jstat -class` có các cột về class `Loaded`, `Unloaded` và thời gian load/unload; không có nghĩa tất cả đều là **class hiện đang live**. Kiểm tra đơn vị cột `Bytes` theo help của phiên bản JDK. `-gcutil` thường có chỉ số `M` cho phần trăm metaspace used theo capacity báo cáo và `CCS` cho compressed class space (nếu có), **không phải MiB tuyệt đối**. `-gcmetacapacity` tập trung vào các chỉ số capacity/committed phù hợp; tên cột có thể thay đổi theo JDK/collector. Dùng `jstat -options` để xem nhóm có sẵn.

### 6.3. JVM unified logging: class load/unload và metaspace GC

Từ lúc khởi chạy JVM, có thể bật một cấu hình log có nhãn/timestamp rõ ràng:

```bash
java -Xms256m -Xmx1024m \
  -Xlog:gc*=info,class+unload=info,gc+metaspace=debug:file=class-gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar app.jar
```

Đây là ví dụ cho HotSpot 17+. GC logs giúp đối chiếu những thời điểm metadata biến động với pha GC; `class+unload` ghi các sự kiện unload được phát hiện. Nếu cần biết **class nào đang liên tục được định nghĩa mới**, có thể tạm thêm `class+load=info`, nhưng log này có thể rất lớn trên ứng dụng động. **Không bật log chi tiết liên tục trên production nếu chưa đo overhead và chuẩn bị rotation/storage.**

Không thấy `class+unload` trong một khoảng quan sát ngắn có thể đơn giản vì JVM **chưa có lý do/chu kỳ GC phù hợp để unload**, logging bị tắt, hoặc tất cả loader còn reachable. Muốn phân biệt cần đối chiếu GC events và class/loader snapshots.

### 6.4. Native Memory Tracking: đo mức tăng theo subsystem

Native Memory Tracking (NMT) của HotSpot cần được bật từ **lúc JVM khởi động**; chế độ `summary` thường đủ cho bước đầu, còn `detail` có chi phí cao hơn.

```bash
java -XX:NativeMemoryTracking=summary -jar app.jar

# Sau khi ứng dụng warm-up, lấy baseline
jcmd <pid> VM.native_memory baseline

# Xem summary hiện tại
jcmd <pid> VM.native_memory summary scale=MB

# Sau một giai đoạn có hiện tượng tăng, so với baseline
jcmd <pid> VM.native_memory summary.diff scale=MB
```

Trong NMT, nhóm `Class` và dòng/chi tiết `Metaspace` có thể thể hiện reserved, committed, vùng metadata/loader overhead theo cấu hình JVM. **Reserved không phải committed, committed không phải used**. Nếu `Class` gần như ổn định mà RSS tăng, tìm subsystem khác: `Thread`, `Code`, `GC`, `Internal`, native allocation ngoài phần HotSpot NMT theo dõi, bộ nhớ của thư viện bên thứ ba. NMT không bao quát mọi `malloc` của thư viện native ngoài JVM, cũng không cung cấp toàn bộ đồ thị giữ tham chiếu.

### 6.5. JFR, heap dump và liên kết nguyên nhân

Java Flight Recorder (JFR) có thể ghi sự kiện class loading/unloading và dấu vết GC nếu event tương ứng được bật; xem bằng Java Mission Control. Dùng một recording ngắn, có điều kiện tái hiện:

```bash
jcmd <pid> JFR.start name=metaspace-check settings=profile duration=120s filename=metaspace-check.jfr

# Khi cần phân tích retention và có đủ disk/quyền:
jcmd <pid> GC.heap_dump /tmp/loader-investigation.hprof
```

`GC.heap_dump` có thể pause JVM và tạo file rất lớn; mặc định trên HotSpot, thao tác dump có thể yêu cầu full GC trước khi chụp (xem `jcmd <pid> help GC.heap_dump`). Heap dump là snapshot **object graph trên heap**, không đo trực tiếp toàn bộ byte metadata native. Nó giúp tìm vì sao `ClassLoader` còn reachable, ví dụ do một thread hoặc registry giữ. Dùng MAT `Path to GC Roots` để kiểm chứng.

HPROF có thể chứa token, thông tin người dùng và dữ liệu nội bộ; chỉ lưu, truyền và xóa theo chính sách bảo mật phù hợp.

## 7. Java 17+ — tự lấy mẫu class và Metaspace MXBean

Chương trình sau độc lập, không cần thư viện ngoài JDK. Nó đọc `ClassLoadingMXBean` và `MemoryPoolMXBean` của pool `Metaspace`, in ra 5 dòng cách nhau khoảng 1 giây. Lưu `ClassMetaspaceMonitor.java`:

```java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryUsage;
import java.time.Instant;

public final class ClassMetaspaceMonitor {
    private static final long KIB = 1024L;

    public static void main(String[] args) throws InterruptedException {
        ClassLoadingMXBean classBean =
                ManagementFactory.getClassLoadingMXBean();

        MemoryPoolMXBean metaspace = ManagementFactory.getMemoryPoolMXBeans()
                .stream()
                .filter(pool -> "Metaspace".equals(pool.getName()))
                .findFirst()
                .orElseThrow(() ->
                        new IllegalStateException("HotSpot Metaspace pool not found"));

        for (int i = 0; i < 5; i++) {
            MemoryUsage usage = metaspace.getUsage();

            System.out.printf(
                    "%s current=%d total=%d unloaded=%d metaUsed=%dKiB metaCommitted=%dKiB%n",
                    Instant.now(),
                    classBean.getLoadedClassCount(),
                    classBean.getTotalLoadedClassCount(),
                    classBean.getUnloadedClassCount(),
                    usage.getUsed() / KIB,
                    usage.getCommitted() / KIB);

            if (i < 4) {
                Thread.sleep(1000);
            }
        }
    }
}
```

Biên dịch và chạy:

```bash
javac ClassMetaspaceMonitor.java
java ClassMetaspaceMonitor
```

**Output:** đúng **5 dòng** theo định dạng ở `printf`. Timestamp, class counts và dung lượng metaspace phụ thuộc JDK/máy/lần chạy; không có stdout số học cố định đáng tin. Chẳng hạn **một dòng minh họa giả định**, không phải kết quả đo chuẩn:

```text
2026-10-29T10:00:00Z current=1020 total=1060 unloaded=40 metaUsed=5120KiB metaCommitted=5376KiB
```

Cả ba số class lấy từ ba lời gọi MXBean liên tiếp, không phải cùng một snapshot nguyên tử. Ví dụ chỉ đo **chính tiến trình monitor**, không đo ứng dụng khác. Muốn chẩn đoán service thật, gắn metric qua JMX/monitoring hoặc dùng `jcmd`/`jstat` vào đúng PID. Pool tên `Metaspace` là tên đặc trưng của HotSpot; JVM khác có thể dùng các pool khác.

## 8. Java 17+ — tái hiện vòng đời nhiều class loader

Bài thử dưới đây nạp **cùng một class bằng nhiều URLClassLoader khác nhau**, từ đó cho thấy vì sao số loader, class và metaspace có thể tăng dù source class không đổi. Có hai chế độ: **`release`** không cố tình giữ loader; **`retain`** giữ các loader trong danh sách static sống lâu. Đây là mô hình kiểm thử, không chạy như workload production.

Tạo `PluginTask.java`:

```java
public final class PluginTask {
    public static String run() {
        return "ready";
    }
}
```

Tạo `LoaderCycleDemo.java`:

```java
import java.net.URL;
import java.net.URLClassLoader;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public final class LoaderCycleDemo {
    private static final List<ClassLoader> RETAINED = new ArrayList<>();

    public static void main(String[] args) throws Exception {
        boolean retain = args.length > 0 && "retain".equals(args[0]);
        URL pluginDir = Path.of("plugin-bin").toAbsolutePath().toUri().toURL();

        for (int i = 0; i < 100; i++) {
            try (URLClassLoader loader = new URLClassLoader(
                    new URL[]{pluginDir},
                    ClassLoader.getPlatformClassLoader())) {

                Class<?> plugin = Class.forName("PluginTask", true, loader);
                Object value = plugin.getMethod("run").invoke(null);
                if (!"ready".equals(value)) {
                    throw new IllegalStateException("Unexpected plugin output");
                }

                if (retain) {
                    RETAINED.add(loader);
                }
            }
        }

        System.out.printf("created=100 retained=%d%n", RETAINED.size());
        Thread.sleep(30_000L);
    }
}
```

Chạy từ thư mục chứa hai file source trên Bash/Linux/macOS (có JDK 17+, `javac` và `java` trên PATH):

```bash
mkdir -p plugin-bin
javac -d plugin-bin PluginTask.java
javac LoaderCycleDemo.java

# Lượt A: không chủ động giữ reference tới loader
java -Xmx128m -Xlog:class+unload=info -cp . LoaderCycleDemo release

# Lượt B: giữ 100 loader trong static list
java -Xmx128m -Xlog:class+unload=info -cp . LoaderCycleDemo retain
```

Hai dòng kết quả của chính chương trình (không tính các dòng VM log) **xác định được** lần lượt là:

```text
created=100 retained=0
```

```text
created=100 retained=100
```

Trong mỗi lượt, chương trình ngủ 30 giây sau khi in để có thời gian quan sát từ terminal khác bằng `jcmd <pid> VM.classloader_stats`. Vì `PluginTask` nằm trong `plugin-bin` chứ không nằm trong classpath `.`, và parent là platform loader, mỗi `URLClassLoader` mới có thể **tự định nghĩa bản `PluginTask` của mình**. Nếu thay parent bằng application loader có thể tự tìm thấy class, cơ chế parent-first delegation sẽ làm kết quả khác.

**Ý nghĩa vòng đời:**
- Ở chế độ `retain`, `RETAINED` là field static của **application class loader**, nên 100 loader vẫn reachable; đóng `URLClassLoader` bằng try-with-resources chỉ giải phóng tài nguyên liên quan, không khiến chúng unload.
- Ở chế độ `release`, không có danh sách giữ lại, nhưng class unloading vẫn phụ thuộc reachability thực và GC. Có thể không nhìn thấy **bất kỳ** sự kiện unload nào trong đúng 30 giây nếu collector không tiến hành pha phù hợp.
- Không so sánh hai lượt chỉ bằng RSS tại giây cuối hoặc bắt buộc `System.gc()`. Muốn đánh giá chắc chắn, chạy workload lặp lại có kiểm soát, lấy số liệu trước/sau các chu kỳ GC có unloading, và xem loader còn reachable hay không.

Nếu muốn mô phỏng leak thực tế hơn, hãy đặt danh sách giữ vào một registry của ứng dụng/hot-reload manager và cho lặp nhiều thế hệ. Phần cần sửa là **vòng đời quản lý reference**, không phải chỉ tăng `MaxMetaspaceSize`.

## 9. Dựng bảng đo và đọc một ví dụ có số liệu

Giả định một service plugin được reload hàng giờ; các mốc ở bảng lấy sau warm-up và sau những chu kỳ GC có cơ hội class unloading, workload tương đương. Tất cả là **số liệu giả định để luyện đọc**, không phải ngưỡng chẩn đoán chuẩn:

| Mốc | Current loaded classes | Total loaded classes | Total unloaded classes | Loader còn sống | Metaspace used | Metaspace committed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 08:00 | 9.200 | 14.000 | 4.800 | 95 | 80 MiB | 96 MiB |
| 10:00 | 11.900 | 21.000 | 9.100 | 240 | 118 MiB | 132 MiB |
| 12:00 | 14.300 | 29.000 | 14.700 | 400 | 159 MiB | 172 MiB |

Từ 08:00 đến 12:00, `totalLoaded` tăng 15.000 và `totalUnloaded` tăng 9.900: JVM **có unloading** nhưng số class hiện đang loaded vẫn tăng 5.100. Loader còn sống tăng 305, metaspace used tăng 79 MiB. Sự tăng đồng thời này đặt ra giả thuyết: **các loader/plugin thế hệ cũ chưa được giải phóng hoặc việc tạo class mới nhanh hơn tốc độ unload**.

Muốn kết luận loader leak, cần tìm: loader nào có tuổi đời vượt vòng đời hợp lệ, thuộc bản deploy nào, bao nhiêu class do nó định nghĩa và GC root nào giữ nó. Một chức năng mở nhiều plugin hợp lệ cũng có thể tạo số liệu tăng tương tự. Bảng chỉ xác lập **tín hiệu điều tra**, không tự chứng minh nguyên nhân.

Nếu thay bằng chuỗi thứ hai: `current=9.200 → 9.250 → 9.230`, `metaspace used=80 → 83 → 81 MiB` trong khi `totalLoaded` tiếp tục tăng, khả năng cao ứng dụng load/unload có kiểm soát. Chênh lệch `committed` vẫn có thể tồn tại do chunk reserve/reuse mà không nhất thiết là rò rỉ.

## 10. Nguyên nhân điển hình và hướng khắc phục

### 10.1. Plugin/redeploy giữ loader cũ

Ví dụ một manager nạp mỗi bản plugin bằng `URLClassLoader` mới, nhưng khi unload chỉ đóng JAR mà không xóa entry trong `Map<String, ClassLoader>` của ứng dụng hoặc vẫn để scheduler chạy task plugin. Loader cũ vẫn reachable, class do nó định nghĩa không unload.

**Điều tra:** so các thế hệ loader, thread, scheduler, registry; trong heap dump tìm path từ root tới loader cũ. **Khắc phục:** hủy task/executor, gỡ listener/callback/MBean, xóa registry entry, đóng tài nguyên, bỏ mạnh reference, rồi kiểm tra unload qua nhiều chu kỳ phù hợp.

### 10.2. Thread context class loader và `ThreadLocal`

Thread pool sống lâu có thể giữ `contextClassLoader` của plugin cũ, hoặc `ThreadLocal` value tham chiếu tới class/instance do loader cũ định nghĩa. Sau redeploy, việc xóa một biến ở plugin manager chưa đủ nếu thread vẫn tồn tại.

**Điều tra:** xem `Thread`/`contextClassLoader`, `ThreadLocalMap` trong heap dump; đối chiếu thread/task sống qua các lượt deploy. **Khắc phục:** phục hồi context class loader sau tác vụ bằng `try/finally`, gọi `ThreadLocal.remove()` ở đúng scope, dừng task/threads khi hủy plugin; tránh để task/plugin object lọt vào executor có vòng đời dài.

### 10.3. Proxy/bytecode sinh động không giới hạn

Framework tạo proxy, generated bytecode, runtime class, template/script class hoặc instrumentation theo dữ liệu mới. Nếu mỗi request sinh một **class định nghĩa khác nhau** trong loader sống lâu, `current loaded` và metaspace used có thể tăng trong khi **loader count hầu như không đổi**. Với cùng defining loader còn sống, JVM không thể đơn giản unload tùy ý các class đã định nghĩa chỉ vì một instance proxy không còn dùng.

**Điều tra:** xem tên class sinh ra, stack sinh class, khóa cache, thống kê class theo loader, JFR/trace phù hợp. **Khắc phục:** tái sử dụng cấu hình/proxy, chuẩn hóa cache key, giới hạn generated variants, thay thiết kế cache/loader lifecycle; không tự động coi class có tên `$Proxy` hoặc `$$Enhancer` là leak.

### 10.4. Registry/global cache giữ `Class<?>`

Một map ở class thuộc application loader lưu `Class<?>`/`Method`/`Constructor` của plugin cũ, listener hoặc callback. Vì object `Class<?>` và reflection metadata liên kết tới defining loader, việc giữ reference này có thể cản class unloading.

**Điều tra:** heap dump + retained path; kiểm tra static registry thuộc loader **sống lâu hơn plugin**. **Khắc phục:** bỏ entry khi unload, dùng chính sách cache phù hợp với vòng đời, cân nhắc yếu tham chiếu chỉ khi không phá vỡ semantics nghiệp vụ.

### 10.5. Tăng bình thường khi warm-up hoặc triển khai chức năng mới

Một microservice có thể lazy-load class khi đường request hiếm lần đầu được chạy, kích hoạt codec, JSON serializer, ORM proxy hoặc library. Metaspace tăng lúc đầu rồi **đạt plateau** là hành vi bình thường. Bổ sung feature/dependency có thể tăng baseline class và metadata vĩnh viễn.

**Điều tra:** so cùng phiên bản/cấu hình với workload đã warm-up, tránh dùng “trước deploy” và “sau deploy” có tập class khác nhau làm mẫu so leak. **Khắc phục:** nếu không vượt budget và ổn định, có thể không cần thay đổi.

## 11. Các cờ JVM cần đọc đúng

| Flag | Tác dụng | Cảnh báo khi dùng |
| --- | --- | --- |
| `-XX:MetaspaceSize=<size>` | Mức **high-water mark ban đầu** dùng trong chính sách kích hoạt GC liên quan đến metaspace. | Không phải kích thước metaspace cố định hoặc “giới hạn tối đa”. |
| `-XX:MaxMetaspaceSize=<size>` | Đặt trần cho native memory dành cho class metadata; liên quan cả committed class space khi compressed class pointers được dùng. | Có thể làm `OutOfMemoryError: Metaspace` xuất hiện sớm hơn; không sửa nguồn giữ loader. |
| `-XX:CompressedClassSpaceSize=<size>` | Điều chỉnh vùng địa chỉ ảo dành cho compressed class space trong cấu hình có hỗ trợ. | Dung lượng reserved lớn không đồng nghĩa RAM used lớn; không tùy tiện thu nhỏ. |
| `-XX:+ClassUnloading` / `-XX:-ClassUnloading` | Bật/tắt khả năng class unloading ở HotSpot khi collector hỗ trợ. | Tắt unloading có thể làm metadata tiếp tục giữ; chỉ đổi khi có lý do xác thực. |
| `-XX:NativeMemoryTracking=summary` | Theo dõi native memory của HotSpot theo subsystem. | Cần bật lúc khởi động và tính đến overhead. |
| `-XX:MetaspaceReclaimPolicy=...` | Chính sách elastic metaspace reclaim của HotSpot đời mới. | Không thay thế việc dọn references; chỉ cân nhắc tuning sau khi đã chẩn đoán đúng nguyên nhân. |

`-Xmx` chỉ giới hạn Java heap, **không giới hạn metaspace trong heap đó**. Trên container, heap + metaspace + compressed class space committed + thread stacks + direct buffers + code cache + phần native khác góp vào memory budget. Khi gặp `OutOfMemoryError: Metaspace`, cần xác định **do `MaxMetaspaceSize`, do tăng class/loader, hay do hạn mức RAM/native thực tế** thay vì lập tức tăng flag.

Nếu `CompressedClassSpaceSize` reserved xấp xỉ 1 GiB trong log, đừng tự quy nó là 1 GiB RSS: xem lượng **committed** và **used** thực tế. Khi tính committed, chú ý metric tổng hoặc metric riêng để tránh cộng trùng.

## 12. Thực hành đọc ba tình huống khác nhau

### A. Heap phẳng nhưng Metaspace/loader tăng

Sau 10 lần redeploy plugin, `heap used after GC` không tăng rõ, nhưng `VM.classloader_stats` cho thấy loader của cả 10 phiên bản vẫn hiện; `Metaspace used` tăng theo từng lần. Heap dump cho thấy một application-level event bus giữ listener của phiên bản cũ, listener giữ object và defining loader. **Khắc phục** là unregister listener khi unload và xác nhận loader cũ trở thành unloadable. Tăng `-Xmx` không giúp giải quyết metadata native retention.

### B. Metaspace committed tăng nhưng used và class count ổn định

Sau đợt churn plugin, `totalLoaded` tăng mạnh, `totalUnloaded` cũng tăng; `current` và `used` trở lại gần baseline, `committed` còn cao hơn. Khả năng là allocator giữ chunk để tái sử dụng hoặc chưa uncommit; ở JDK 17+ bộ quản lý elastic metaspace thường có thể trả một phần về OS sau unload, nhưng thời điểm phụ thuộc trạng thái VM. **Không có bằng chứng trực tiếp về loader leak** chỉ từ committed chưa giảm. Theo dõi thêm vài chu kỳ, đối chiếu NMT và RSS.

### C. Current class tăng mà loader count gần như không đổi

Một service dùng một loader sống lâu nhưng tạo class bytecode mới mỗi lần nhận cấu hình ngẫu nhiên. `current loaded` tăng từ 20.000 lên 50.000; loader count không đổi, metaspace used tăng. Hướng điều tra là generator và logic cache/khóa class, **không phải chỉ tìm loader bị quên close**. Giải pháp có thể là tái sử dụng kiểu proxy hoặc giảm cardinality của generated class.

## 13. Lỗi suy luận phổ biến

- **“Metaspace tăng tức memory leak.”** Chưa đủ; cần xác định plateau, workload, class growth, loader lifetime và GC unloading.
- **“`totalLoaded` tăng nghĩa là số class còn sống tăng.”** Sai; counter tổng chỉ tăng, kể cả class đã unload.
- **“Có class unloading thì không thể leak.”** Sai; một phần class có thể unload trong khi loader khác bị giữ dai dẳng.
- **“Loader đã `close()` nên chắc chắn được unload.”** Sai; `close` giải phóng tài nguyên URL/JAR, không xóa mọi GC roots.
- **“Một class không còn instance thì chắc chắn được unload.”** Sai; defining loader có thể vẫn reachable và class còn được dùng qua reflection/static code.
- **“Số loader ổn định thì không thể leak metadata.”** Sai; một loader sống lâu có thể định nghĩa nhiều class mới mãi.
- **“Reserved metaspace cao chính là RAM đã dùng.”** Sai; phân biệt reserved/committed/used và đo RSS.
- **“`-XX:MetaspaceSize` là cap.”** Sai; nó liên quan high-water mark để quyết định GC, cap được kiểm soát bởi `MaxMetaspaceSize` khi cấu hình.
- **“`System.gc()` không làm unloaded tăng thì có leak.”** Sai; gọi GC chỉ là đề nghị, collector/JVM có thể không unload trong đợt đó.
- **“Heap dump cho biết chính xác tất cả metadata native.”** Sai; dump giúp truy đường giữ loader trên heap, không thay báo cáo metaspace/NMT.
- **“Tăng `MaxMetaspaceSize` là fix.”** Sai; trần lớn hơn chỉ thêm headroom, còn leak do reference/bytecode generation vẫn tiếp diễn.
- **“RSS tăng là lỗi metaspace.”** Sai; phải so NMT, heap committed, thread/native memory và container metrics.

## 14. Checklist vận hành trước khi kết luận

1. **Metric:** có dùng đúng `Metaspace used`, `committed`, `Compressed Class Space` và đơn vị, đúng một JVM không?
2. **Baseline:** đã loại giai đoạn startup/warm-up và so cùng phiên bản/workload chưa?
3. **Class:** `current loaded` tăng bền vững, hay chỉ `totalLoaded` tăng theo thời gian?
4. **Loader:** có loader plugin/redeploy thế hệ cũ còn sống, hoặc một loader liên tục định nghĩa class mới không?
5. **GC:** đã có các chu kỳ có thể class unload và log/counter `unloaded` thay đổi như thế nào?
6. **Native:** NMT `Class/Metaspace` và RSS có đồng thuận; có dấu hiệu tăng ở subsystem khác không?
7. **Reachability:** đã tìm được đường từ GC roots giữ loader/`Class<?>`/instance bằng heap dump chưa?
8. **Giải pháp:** sau khi dọn registry, thread context, listener, cache hoặc giảm sinh class, xu hướng class/loader/metaspace có ổn định trong cùng kịch bản thử nghiệm không?

**Điểm cốt lõi:** để chẩn đoán metaspace growth, hãy đọc **bộ ba xu hướng metaspace–classes–class loaders** cùng sự kiện GC có class unloading. `Total loaded` chỉ nói lượng class **đã từng** nạp; `current loaded` cho biết tồn tại tại thời điểm đo; số loader và các GC roots giúp tìm vòng đời đối tượng nào giữ metadata. Quyết định sửa phải dựa trên nguyên nhân giữ loader hoặc cơ chế sinh class quá mức, chứ không dựa vào một đường tăng memory duy nhất.

### Tài liệu tham khảo chính thức

- [Oracle JDK 17 — Garbage Collection Tuning: Other Considerations (Class Metadata)](https://docs.oracle.com/en/java/javase/17/gctuning/other-considerations.html)
- [Oracle JDK 17 — jcmd diagnostic commands](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html)
- [Java Language Specification, Java SE 17 — `12.7 Unloading of Classes and Interfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-12.html#jls-12.7)
- [OpenJDK JEP 387 — Elastic Metaspace](https://openjdk.org/jeps/387)