# Native Memory Tracking để theo dõi bộ nhớ native

## 1. Native Memory Tracking giải quyết vấn đề gì?

Một tiến trình Java sử dụng nhiều bộ nhớ hơn Java heap. Ngoài object và array do ứng dụng tạo, JVM còn dùng bộ nhớ native cho metadata của class, thread stack, JIT code, garbage collector, cấu trúc nội bộ và các hoạt động runtime khác. Thư viện JNI hoặc thư viện native bên thứ ba cũng có thể cấp phát bộ nhớ ngoài heap.

Vì vậy, có thể gặp tình huống:

- Heap used vẫn thấp nhưng RSS của tiến trình tăng liên tục.
- Container gần chạm memory limit dù không có `OutOfMemoryError: Java heap space`.
- Số lượng thread tăng khiến memory usage tăng dù heap gần như không đổi.
- Classloader hoặc dynamic proxy làm metaspace tăng.
- Sau khi tăng heap, container bị OOM kill sớm hơn vì phần native không còn đủ headroom.

**Native Memory Tracking (NMT)** là tính năng chẩn đoán của HotSpot JVM, cho phép theo dõi một số nhóm bộ nhớ native mà chính JVM quản lý. NMT cung cấp số liệu tổng hợp theo category và, ở chế độ chi tiết, theo call site hoặc vùng địa chỉ ảo. Nó giúp tìm hiểu JVM đang reserve/commit bộ nhớ ở đâu và mức sử dụng thay đổi thế nào theo thời gian.

NMT không phải heap profiler và cũng không phải công cụ đo toàn bộ RSS. Cần kết hợp NMT với heap metrics, GC log, heap dump, hệ điều hành và container metrics để có bức tranh đầy đủ.

## 2. Phân biệt Java heap, native memory và RSS

### 2.1. Các khái niệm

| Khái niệm | Ý nghĩa | Nguồn quan sát phù hợp |
|---|---|---|
| Java heap | Vùng lưu object và array của ứng dụng | Heap MXBean, GC log, heap dump, JFR |
| Native memory | Bộ nhớ ngoài heap do JVM, JDK hoặc thư viện native sử dụng | NMT kết hợp công cụ hệ điều hành |
| Reserved memory | Vùng địa chỉ ảo JVM đã reserve cho một mục đích | NMT, VM diagnostics |
| Committed memory | Vùng bộ nhớ JVM đã commit để có thể sử dụng theo cơ chế của VM/OS | NMT, VM diagnostics |
| RSS | Các trang bộ nhớ của tiến trình hiện đang resident trong RAM | OS process metrics |
| Container memory usage | Mức dùng bộ nhớ theo cgroup/container runtime | Container metrics, cgroup files |

Các số liệu này không thể thay thế cho nhau. Ví dụ, một vùng địa chỉ ảo lớn có thể được reserve nhưng chưa commit; một vùng committed cũng không nhất thiết toàn bộ đang resident trong RAM tại thời điểm đo.

### 2.2. Sơ đồ bộ nhớ ở mức tiến trình

```text
Java process
|
+-- Java heap
|     +-- Object và array
|
+-- JVM native memory
|     +-- Metaspace / class metadata
|     +-- Thread stacks
|     +-- JIT code cache
|     +-- GC structures
|     +-- Compiler / runtime / internal
|     +-- NMT bookkeeping
|
+-- Native memory ngoài phạm vi NMT đầy đủ
|     +-- JNI / native libraries
|     +-- Một số allocation của JDK class libraries
|     +-- Native allocator riêng của ứng dụng
|
+-- Mappings và tài nguyên do OS quản lý
      +-- Shared libraries / mapped files
      +-- Các trang resident và page cache theo cách tính của OS
~~~

NMT tập trung vào allocation do HotSpot VM quản lý. Phạm vi này hữu ích nhưng không bao quát tất cả bộ nhớ của tiến trình. Nếu tổng RSS lớn hơn nhiều so với các category NMT, đó là tín hiệu cần kiểm tra những allocation ngoài phạm vi NMT hoặc cách hệ điều hành tính bộ nhớ.

### 2.3. Reserved và committed không phải RSS

Ví dụ một category có:

```text
reserved=512MB, committed=128MB
```

Điều đó cho biết JVM đã reserve 512 MB không gian địa chỉ ảo và commit 128 MB theo cơ chế runtime. Không được kết luận tiến trình đang chiếm 512 MB RAM vật lý. Cũng không được kết luận RSS bằng 128 MB.

RSS phụ thuộc các trang đã được fault vào RAM, shared mappings, heap pages, native allocations và cách OS đo. Đối chiếu NMT với RSS/cgroup usage theo thời gian sẽ hữu ích hơn việc so sánh hai con số đơn lẻ.

## 3. Bật Native Memory Tracking trong Java 17

### 3.1. NMT mặc định tắt

Trên HotSpot, NMT mặc định ở trạng thái tắt. Cần bật khi khởi chạy JVM bằng flag:

```shell
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Hoặc bật chế độ chi tiết:

```shell
java -XX:NativeMemoryTracking=detail -jar app.jar
```

Các mức:

| Giá trị | Theo dõi | Khi dùng |
|---|---|---|
| `off` | Tắt NMT | Runtime production không cần số liệu NMT |
| `summary` | Thống kê tổng hợp theo category | Theo dõi xu hướng native memory với chi phí thấp hơn detail |
| `detail` | Thống kê chi tiết hơn, có call site và thông tin vùng nhớ ảo | Điều tra sâu khi summary chưa đủ |

Nếu không chỉ định, giá trị mặc định là `off`.

### 3.2. Chọn summary hay detail

`summary` thường là điểm bắt đầu hợp lý:

```shell
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Chế độ này cho biết các category nào đang dùng nhiều native memory và số liệu reserve/commit thay đổi ra sao.

`detail` cung cấp thêm thông tin về call site hoặc mapping cụ thể:

```shell
java -XX:NativeMemoryTracking=detail -jar app.jar
```

Detail hữu ích khi cần khoanh vùng allocation trong một category. Output có thể dài và khó đọc hơn, đồng thời có thêm overhead.

### 3.3. NMT phải được bật lúc JVM khởi động

Không thể bật NMT lần đầu bằng `jcmd` sau khi JVM đã chạy mà không có tracking. Mức tracking phải được chọn khi khởi động tiến trình:

```shell
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Nếu cần đổi từ `summary` sang `detail`, hãy lên kế hoạch restart JVM với flag mới. Lệnh `jcmd VM.native_memory shutdown` có thể tắt NMT đang chạy; không coi đó là cơ chế chuyển sang detail hoặc bật lại tracking. Muốn thay đổi mức theo dõi, khởi động lại JVM với cấu hình mong muốn.

Điều này cần được tính đến khi lập kế hoạch triển khai: bật NMT trước khi cần điều tra sẽ giúp tránh phải chờ một lần restart khẩn cấp.

### 3.4. Xác nhận NMT đang bật

Xem flag cuối cùng của JVM:

```shell
jcmd <pid> VM.flags
```

Hoặc xem các flag mặc định/ergonomics:

```shell
java -XX:+PrintFlagsFinal -version
```

Tìm `NativeMemoryTracking` trong output. Có thể dùng `jcmd` để truy vấn trực tiếp:

```shell
jcmd <pid> VM.native_memory summary
```

Nếu NMT không được bật khi khởi động, lệnh có thể báo rằng Native Memory Tracking chưa được bật. Khi đó cần khởi động lại JVM với `-XX:NativeMemoryTracking=summary` hoặc `detail`.

## 4. Các lệnh jcmd quan trọng

### 4.1. In thống kê tổng hợp

```shell
jcmd <pid> VM.native_memory summary
```

Có thể yêu cầu đơn vị hiển thị:

```shell
jcmd <pid> VM.native_memory summary scale=MB
```

Các scale thường hỗ trợ là `KB`, `MB` và `GB`. Không thêm đơn vị vào số liệu khi so sánh nếu hai lần lấy mẫu dùng scale khác nhau.

### 4.2. In thống kê chi tiết

```shell
jcmd <pid> VM.native_memory detail
```

Lệnh này cần JVM đã được khởi động với `NativeMemoryTracking=detail`. Output có thể bao gồm các call site và vùng địa chỉ ảo. Dùng khi đã biết category cần điều tra; không nên bắt đầu bằng cách đọc một output detail rất dài mà chưa có câu hỏi cụ thể.

### 4.3. Tạo baseline

NMT hỗ trợ chụp baseline để so sánh:

```shell
jcmd <pid> VM.native_memory baseline
```

Baseline ghi lại trạng thái dùng làm mốc so sánh cho các lần truy vấn diff sau đó. Thường nên tạo baseline sau khi ứng dụng khởi động và hoàn tất warm-up, nếu mục tiêu là theo dõi tăng trưởng trong giai đoạn steady-state.

### 4.4. So sánh với baseline

Thống kê tổng hợp thay đổi kể từ baseline:

```shell
jcmd <pid> VM.native_memory summary.diff scale=MB
```

Với NMT detail:

```shell
jcmd <pid> VM.native_memory detail.diff scale=MB
```

`summary.diff` và `detail.diff` giúp thấy category hoặc call site tăng/giảm kể từ thời điểm baseline. Lấy nhiều snapshot theo cùng chu kỳ giúp nhận diện xu hướng.

### 4.5. Danh sách thao tác thường dùng

| Mục đích | Lệnh |
|---|---|
| Xem summary | `jcmd <pid> VM.native_memory summary` |
| Xem summary theo MB | `jcmd <pid> VM.native_memory summary scale=MB` |
| Xem detail | `jcmd <pid> VM.native_memory detail` |
| Ghi baseline | `jcmd <pid> VM.native_memory baseline` |
| Xem thay đổi summary | `jcmd <pid> VM.native_memory summary.diff scale=MB` |
| Xem thay đổi detail | `jcmd <pid> VM.native_memory detail.diff scale=MB` |
| Tắt NMT đang chạy | `jcmd <pid> VM.native_memory shutdown` |

NMT không cung cấp một thao tác runtime để chuyển từ off sang summary/detail. Lệnh shutdown cũng không phải thao tác bật lại; hãy restart để thay đổi mức tracking.

## 5. Đọc output NMT

### 5.1. Ví dụ output summary

Output thực tế phụ thuộc JDK build, collector, flags và workload. Một phần output minh họa:

```text
Native Memory Tracking:

Total: reserved=2450000KB, committed=820000KB

-                 Java Heap (reserved=1048576KB, committed=524288KB)
                            (mmap: reserved=1048576KB, committed=524288KB)

-                     Class (reserved=1100000KB, committed=45000KB)
                            (classes #...)
                            (  metadata: reserved=..., committed=...)

-                    Thread (reserved=120000KB, committed=120000KB)
                            (thread #...)
                            (stack: reserved=..., committed=...)

-                      Code (reserved=..., committed=...)
-                        GC (reserved=..., committed=...)
-                  Compiler (reserved=..., committed=...)
-                  Internal (reserved=..., committed=...)
-                    Symbol (reserved=..., committed=...)
-        Native Memory Tracking (reserved=..., committed=...)
```

Đây là ví dụ cấu trúc để học cách đọc, không phải số liệu dự đoán cho mọi ứng dụng. Category và trường con có thể thay đổi theo phiên bản HotSpot.

### 5.2. Total

Phần `Total` cho biết tổng reservation và commitment mà NMT ghi nhận trong phạm vi của nó. Không đồng nhất `Total committed` với process RSS hoặc container memory usage.

Nếu `Total committed` tăng, cần xem category nào đóng góp phần tăng. Nếu RSS tăng nhưng NMT Total gần như không đổi, điều đó gợi ý cần điều tra allocation ngoài phạm vi NMT hoặc mapping/OS memory.

### 5.3. Java Heap

NMT có thể hiển thị reservation/commitment của vùng Java heap như một category. Điều đó không có nghĩa NMT phân tích từng object trong heap hoặc tìm được object nào giữ reference.

Để phân tích object, dominator tree, retained size hoặc đường tham chiếu:

- Dùng heap dump.
- Dùng Java Flight Recorder cho allocation/GC event phù hợp.
- Dùng profiler hoặc công cụ phân tích heap.

### 5.4. Class và Metaspace

Category liên quan class/metaspace có thể tăng khi ứng dụng nạp nhiều class, sinh proxy hoặc giữ nhiều classloader. Hãy xem:

- Số lượng class đã nạp.
- Metaspace committed/used qua MemoryPoolMXBean.
- Classloader có được thu hồi không.
- Có hot reload, dynamic generation hoặc redeploy lặp lại không.

Không kết luận memory leak chỉ từ việc class count tăng trong giai đoạn startup; framework thường nạp class trong warm-up. Cần quan sát xu hướng sau khi workload ổn định.

### 5.5. Thread

Thread category phản ánh một phần bộ nhớ liên quan thread, gồm stack reservation/commitment theo cách HotSpot báo cáo. Nếu thread count tăng liên tục, native memory có thể tăng ngay cả khi heap không đổi.

Đối chiếu:

- Số thread sống.
- Stack size cấu hình qua `-Xss`.
- Thread dump.
- Thread pool sizing.
- Thread leak hoặc thread được tạo theo request mà không được kết thúc.

Không chỉ giảm `-Xss` để xử lý thread explosion. Cần kiểm tra số lượng thread và lifecycle trước.

### 5.6. Code, GC, Compiler và Internal

Các category này có thể phản ánh:

- Code cache và JIT-generated code.
- Cấu trúc nội bộ của garbage collector.
- Bộ nhớ compiler/JIT.
- Cấu trúc runtime nội bộ khác.

Tên và cách chia category có thể thay đổi giữa các HotSpot release. Hãy xem output của đúng JDK 17 đang chạy và tài liệu đi kèm thay vì phụ thuộc một danh sách category cố định từ runtime khác.

### 5.7. NMT category

NMT cần tự cấp phát một lượng bộ nhớ để lưu thông tin theo dõi. Vì vậy output có category liên quan Native Memory Tracking. Bản thân công cụ theo dõi cũng có chi phí memory và CPU; số liệu không phải một phép đo hoàn toàn miễn phí.

## 6. Reserved, committed và malloc trong chế độ detail

### 6.1. Vùng địa chỉ ảo

JVM có thể reserve một vùng địa chỉ ảo lớn trước, sau đó commit dần theo nhu cầu. Reservation không có nghĩa toàn bộ vùng đã được sử dụng hoặc chiếm RAM vật lý.

Ví dụ:

```text
reserved=1024MB
committed=256MB
```

Điều này có thể xảy ra với một vùng cần khả năng mở rộng trong tương lai. Khi đọc NMT, hãy chú ý cả hai cột.

### 6.2. malloc và mmap

Ở chế độ detail, output có thể mô tả allocation thông qua các cơ chế như `malloc` hoặc `mmap`, cùng call site liên quan.

- `malloc`: cấp phát native heap qua allocator.
- `mmap`: ánh xạ vùng nhớ vào không gian địa chỉ tiến trình.

Không phải mọi vùng `mmap` đều tương ứng một lượng RSS bằng reservation. Trang có thể chưa được chạm, được chia sẻ hoặc được OS quản lý theo cơ chế riêng.

### 6.3. Call site giúp khoanh vùng

Detail có thể giúp nhận biết category tăng do một nhóm call site nào. Ví dụ, nếu phần thread stack tăng cùng thread count, cần điều tra thread creation. Nếu class/metaspace tăng cùng số classloader, cần xem classloading.

Call site trong NMT là dấu vết allocation nội bộ HotSpot, không phải stack trace Java đầy đủ của mọi object hay native allocation trong thư viện bên thứ ba.

## 7. Baseline và diff để phát hiện tăng trưởng

### 7.1. Chọn thời điểm baseline

Một quy trình hữu ích:

1. Khởi động JVM với NMT summary hoặc detail.
2. Chờ ứng dụng hoàn tất startup.
3. Chạy warm-up để JIT, framework và connection pool ổn định.
4. Ghi baseline.
5. Chạy workload đại diện.
6. Lấy summary.diff theo chu kỳ.
7. Nếu cần, restart trong detail mode để điều tra category/call site cụ thể.

Nếu tạo baseline ngay khi JVM vừa khởi động, diff sẽ bao gồm cả startup, classloading và JIT warm-up. Điều đó có thể đúng với mục tiêu đo startup, nhưng không phù hợp nếu đang tìm tăng trưởng bất thường sau warm-up.

### 7.2. Ví dụ một phiên điều tra

```shell
# 1. Khởi động với summary tracking
java -XX:NativeMemoryTracking=summary -jar app.jar

# 2. Trong terminal khác, tìm PID và xem summary
jcmd -l
jcmd <pid> VM.native_memory summary scale=MB

# 3. Sau khi ứng dụng warm-up, tạo baseline
jcmd <pid> VM.native_memory baseline

# 4. Chạy workload trong một khoảng thời gian

# 5. Lấy chênh lệch
jcmd <pid> VM.native_memory summary.diff scale=MB
```

Để đo một giai đoạn khác, có thể ghi baseline mới trước giai đoạn đó rồi lấy diff sau khi hoàn tất. Ghi lại thời điểm, workload, replica, container limit và các JVM flags để so sánh các lần chạy có ý nghĩa.

### 7.3. Đọc diff đúng cách

Giả sử output diff cho thấy:

```text
Thread   +40MB committed
Class    +12MB committed
Code      +5MB committed
Java Heap +80MB committed
```

Đây chỉ là ví dụ minh họa. Cần đặt câu hỏi:

- Thread count có tăng tương ứng không?
- Có class được nạp thêm do workload hoặc proxy không?
- JIT warm-up có đang tiếp diễn không?
- Heap commitment tăng có phải do workload bình thường?
- Mức tăng có tiếp tục sau khi workload dừng không?

Một lần tăng không đủ kết luận leak. Memory có thể tăng trong startup hoặc warm-up rồi ổn định. Dấu hiệu đáng quan tâm là mức tăng tiếp tục qua các chu kỳ cùng workload, không giảm sau khi workload kết thúc, hoặc tương quan với một tài nguyên không được giải phóng.

### 7.4. Kết hợp summary và detail

Nên dùng hai bước:

- **Summary:** xác định category có mức tăng đáng kể.
- **Detail:** điều tra sâu category đã được khoanh vùng.

Không cần bật detail ngay từ đầu cho mọi production workload nếu overhead hoặc kích thước output không phù hợp. Nếu cần detail nhưng JVM hiện tại chỉ chạy summary, phải lên kế hoạch restart với detail.

## 8. NMT không theo dõi toàn bộ native memory

### 8.1. Phạm vi theo dõi

NMT được thiết kế để theo dõi allocation nội bộ HotSpot. Nó không phải bộ giám sát toàn diện mọi byte được tiến trình sử dụng.

Các khoản có thể không được NMT theo dõi đầy đủ gồm:

- Native memory được cấp phát trực tiếp bởi thư viện bên thứ ba.
- Allocation do code JNI của ứng dụng tự quản lý.
- Một số allocation do JDK class libraries thực hiện ngoài cơ chế HotSpot được theo dõi.
- Các mapping/shared memory và chi phí do hệ điều hành quản lý theo cách riêng.

Phạm vi cụ thể phụ thuộc đường cấp phát và phiên bản runtime. Khi có native library, không giả định NMT Total sẽ giải thích toàn bộ phần chênh lệch RSS.

### 8.2. Direct ByteBuffer

Direct buffer là một trường hợp cần chú ý:

```java
ByteBuffer buffer = ByteBuffer.allocateDirect(16 * 1024 * 1024);
```

Vùng dữ liệu direct nằm ngoài Java heap. Object `ByteBuffer` wrapper vẫn ở heap, còn vùng dữ liệu được quản lý qua cơ chế native/JDK. Không nên mặc định NMT sẽ phân loại đầy đủ mọi direct buffer allocation như một category riêng trong mọi phiên bản.

Để quan sát direct/mapped buffer pool do JVM expose, dùng `BufferPoolMXBean`:

```java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;

for (BufferPoolMXBean pool :
        ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
    System.out.printf(
            "%s: count=%d, used=%d, capacity=%d%n",
            pool.getName(),
            pool.getCount(),
            pool.getMemoryUsed(),
            pool.getTotalCapacity()
    );
}
```

Đây là số liệu bổ sung cho direct/mapped buffers; hãy đối chiếu với NMT và RSS.

### 8.3. JNI và thư viện native

Một JNI library có thể gọi `malloc`, tạo native object, mở handle hoặc ánh xạ bộ nhớ riêng. Nếu library không dùng allocation path được NMT theo dõi, NMT không hiển thị đầy đủ allocation đó.

Khi nghi ngờ JNI/native library:

- Xem tài liệu và API lifecycle của thư viện.
- Kiểm tra native allocation/free có cân bằng không.
- Dùng profiler hoặc công cụ native phù hợp với nền tảng.
- So sánh RSS/cgroup usage với NMT Total.
- Tạo test tải lặp lại để xem memory có tăng theo số lần gọi hay ổn định.

Không kết luận “không có native leak” chỉ vì NMT summary không cho thấy category tăng.

## 9. Kết hợp NMT với các công cụ khác

### 9.1. Heap metrics và heap dump

Nếu Java heap used tăng sau GC, NMT không cho biết object nào giữ bộ nhớ. Dùng:

- `MemoryMXBean` và memory pool metrics.
- GC log.
- Heap dump với `-XX:+HeapDumpOnOutOfMemoryError`.
- Công cụ phân tích heap để tìm dominator/retained size.

NMT bổ sung góc nhìn native của JVM, không thay thế heap analysis.

### 9.2. JFR

Java Flight Recorder có thể ghi nhận allocation, GC, thread, lock và các event runtime phù hợp. JFR hữu ích để liên hệ hành vi ứng dụng với thay đổi bộ nhớ và latency.

JFR không phải bản thay thế trực tiếp của NMT cho mọi native allocation. Hãy chọn event và công cụ theo câu hỏi điều tra.

### 9.3. Công cụ hệ điều hành trên Linux

Một số lệnh thường dùng:

```shell
ps -o pid,rss,vsz,comm -p <pid>
cat /proc/<pid>/status
cat /proc/<pid>/smaps_rollup
pmap -x <pid>
```

Ý nghĩa khái quát:

- `RSS`: resident set size.
- `VSZ`: virtual address space size.
- `/proc/<pid>/status`: thông tin memory/thread của process.
- `smaps_rollup`: tổng hợp các mapping memory.
- `pmap`: ánh xạ vùng nhớ tiến trình.

Tên trường và khả năng có mặt phụ thuộc kernel/Linux distribution. Các lệnh đọc được số liệu OS, không tự xác định allocation nào thuộc Java object hay JVM category.

### 9.4. Container/cgroup metrics

Với Linux cgroup v2, hai file thường gặp:

```text
/sys/fs/cgroup/memory.current
/sys/fs/cgroup/memory.max
```

Với cgroup v1, tên file thường gặp:

```text
memory.usage_in_bytes
memory.limit_in_bytes
```

Đường dẫn thực tế phụ thuộc mount namespace và container runtime. Dùng metrics của Kubernetes/container platform nếu có; không hardcode đường dẫn cgroup v1 cho mọi môi trường.

Đối chiếu:

| Nguồn | Trả lời câu hỏi |
|---|---|
| NMT | HotSpot đang reserve/commit native memory ở category nào? |
| Heap metrics | Heap đang dùng/commit bao nhiêu? |
| Heap dump | Object nào giữ heap? |
| JFR | Allocation/GC/thread behavior diễn ra khi nào? |
| OS RSS/smaps | Tiến trình đang resident/mapping bao nhiêu memory? |
| cgroup metrics | Container đang tiêu thụ bao nhiêu so với limit? |
| BufferPoolMXBean | Direct/mapped buffer pools đang dùng bao nhiêu? |

## 10. Overhead và cách dùng NMT trong production

### 10.1. NMT có chi phí

NMT cần lưu metadata theo dõi allocation và cập nhật số liệu khi JVM cấp phát/giải phóng vùng nhớ. Điều đó có thể làm tăng CPU và memory overhead.

Chi phí thực tế phụ thuộc:

- Mức tracking summary/detail.
- Tần suất và kiểu allocation.
- JDK build và nền tảng.
- Workload và số lượng thread/category.

Detail thường có overhead cao hơn summary. Không nên cam kết một tỷ lệ overhead cố định cho mọi ứng dụng; hãy benchmark trên workload đại diện và đo cả latency lẫn memory.

### 10.2. Chọn chiến lược bật

Một số lựa chọn vận hành:

| Môi trường | Chiến lược |
|---|---|
| Local development | Bật summary hoặc detail khi học/điều tra |
| CI integration test | Bật summary nếu test cần xác nhận xu hướng native memory |
| Staging | Bật summary trong các đợt load test hoặc khi cần baseline |
| Production | Cân nhắc summary nếu lợi ích quan sát lớn hơn overhead đã đo |
| Điều tra chuyên sâu | Khởi động một instance canary với detail theo thời gian giới hạn |

Không bật detail trên mọi replica một cách mặc định nếu chưa đánh giá overhead và dung lượng log/output. Có thể chọn một canary instance có workload đại diện để điều tra.

### 10.3. Bảo vệ thông tin chẩn đoán

Output NMT có thể chứa thông tin về cấu trúc runtime, call site, thư viện và cách ứng dụng vận hành. Hãy:

- Giới hạn quyền truy cập vào `jcmd` và process diagnostics.
- Lưu output trong nơi có kiểm soát truy cập.
- Không đưa log chẩn đoán chi tiết vào kênh công khai.
- Ghi rõ thời điểm, PID, container/replica và JVM flags.
- Tắt chế độ detail sau khi hoàn tất nếu không còn nhu cầu và triển khai lại theo cấu hình phù hợp.

## 11. Ví dụ quy trình điều tra native memory tăng

Giả sử một service chạy trong container 1 GiB. Heap max là 512 MiB, heap used sau GC ổn định quanh 180 MiB nhưng container memory usage tăng dần tới 900 MiB.

### 11.1. Quan sát ban đầu

Thu thập cùng thời điểm:

- Heap used/committed/max.
- Process RSS.
- cgroup memory.current.
- Thread count.
- Direct buffer pool.
- NMT summary.

Nếu heap used ổn định nhưng RSS tăng, chưa thể kết luận native leak; cần tìm category hoặc allocation ngoài phạm vi NMT.

### 11.2. Bật summary và tạo baseline

Khởi động instance điều tra:

```shell
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Sau warm-up:

```shell
jcmd <pid> VM.native_memory summary scale=MB
jcmd <pid> VM.native_memory baseline
```

Chạy workload với concurrency đại diện và lấy diff theo chu kỳ:

```shell
jcmd <pid> VM.native_memory summary.diff scale=MB
```

### 11.3. Diễn giải kết quả

Giả sử thread category tăng tương ứng với thread count. Khi đó:

1. Lấy thread dump.
2. Xác định thread pool nào tạo thread.
3. Kiểm tra thread có kết thúc sau request/task không.
4. Kiểm tra cấu hình pool và giới hạn concurrency.
5. Đối chiếu stack reservation/commitment và RSS.

Nếu category Class/Metaspace tăng:

1. Theo dõi class count và metaspace pool.
2. Kiểm tra classloader có được giải phóng không.
3. Kiểm tra dynamic proxy, script engine, hot reload hoặc redeploy.
4. Dùng class histogram/heap dump nếu cần tìm reference giữ classloader.

Nếu NMT không giải thích được RSS tăng:

1. Xem direct/mapped buffer pools.
2. Kiểm tra JNI/native libraries.
3. Đọc `smaps_rollup` hoặc `pmap`.
4. Dùng native profiler hoặc công cụ theo nền tảng.

### 11.4. Chuyển sang detail khi cần

Nếu summary cho thấy category cụ thể tăng nhưng chưa rõ call site, triển khai một instance điều tra với:

```shell
java -XX:NativeMemoryTracking=detail -jar app.jar
```

Sau warm-up, baseline rồi lấy:

```shell
jcmd <pid> VM.native_memory detail
jcmd <pid> VM.native_memory detail.diff scale=MB
```

Detail có thể giúp xác định call site HotSpot liên quan. Nếu allocation thuộc JNI hoặc thư viện ngoài phạm vi NMT, cần công cụ khác.

## 12. Những lỗi thường gặp khi dùng NMT

| Lỗi | Vì sao sai | Cách xử lý |
|---|---|---|
| Chạy `jcmd VM.native_memory` khi NMT chưa bật | JVM không có dữ liệu tracking | Restart với `-XX:NativeMemoryTracking=summary` hoặc `detail` |
| Nghĩ có thể bật NMT sau startup | Tracking cần khởi tạo từ đầu | Chọn mức tracking khi khởi động JVM |
| Đọc reserved như RAM đang dùng | Reserved là không gian địa chỉ ảo | Đọc committed, RSS và cgroup metrics riêng |
| Đồng nhất committed với RSS | Hai phép đo có định nghĩa khác nhau | Đối chiếu NMT với OS process metrics |
| Nghĩ NMT theo dõi mọi JNI allocation | NMT tập trung vào HotSpot VM; native code ngoài phạm vi có thể không được ghi nhận | Dùng native profiler/OS metrics cho thư viện native |
| Dùng NMT thay heap dump | NMT không phân tích object graph/retained size | Dùng heap dump và JFR cho heap |
| Kết luận leak từ một lần diff | Startup, warm-up và workload tạo tăng trưởng bình thường | Lấy nhiều baseline/diff qua các chu kỳ tương đương |
| Bật detail trên mọi replica | Overhead và output có thể không cần thiết | Dùng summary trước, detail trên canary khi cần |
| Không ghi lại thời điểm baseline | Diff khó gắn với workload | Ghi timestamp, workload, PID và cấu hình |
| So sánh output khác scale | Đơn vị không giống nhau | Dùng cùng scale khi so sánh |
| Dùng NMT Total để giải thích toàn bộ container usage | Còn OS, JNI, class libraries và native allocation khác | Kết hợp RSS/cgroup, buffer metrics và native tools |
| Tắt NMT rồi kỳ vọng bật lại bằng jcmd | Shutdown không phải cơ chế re-enable | Restart JVM với tracking được bật |

## 13. Ví dụ Java 17: đọc heap, non-heap, thread và buffer metrics

NMT được truy vấn bằng `jcmd`; ứng dụng cũng có thể cung cấp các metric JVM để đối chiếu. Lưu file **JvmMemoryMetrics.java**:

```java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;
import java.lang.management.ThreadMXBean;

public class JvmMemoryMetrics {

    private static double mib(long bytes) {
        return bytes / 1024.0 / 1024.0;
    }

    public static void main(String[] args) {
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        MemoryUsage heap = memory.getHeapMemoryUsage();
        MemoryUsage nonHeap = memory.getNonHeapMemoryUsage();

        System.out.printf("Heap used: %.1f MiB%n", mib(heap.getUsed()));
        System.out.printf(
                "Heap committed: %.1f MiB%n",
                mib(heap.getCommitted())
        );
        System.out.printf("Heap max: %.1f MiB%n", mib(heap.getMax()));
        System.out.printf(
                "Non-heap used: %.1f MiB%n",
                mib(nonHeap.getUsed())
        );

        ThreadMXBean threads = ManagementFactory.getThreadMXBean();
        System.out.println("Live threads: " + threads.getThreadCount());

        for (BufferPoolMXBean pool :
                ManagementFactory.getPlatformMXBeans(
                        BufferPoolMXBean.class
                )) {
            System.out.printf(
                    "%s: count=%d, used=%.1f MiB, capacity=%.1f MiB%n",
                    pool.getName(),
                    pool.getCount(),
                    mib(pool.getMemoryUsed()),
                    mib(pool.getTotalCapacity())
            );
        }
    }
}
```

Biên dịch và chạy trên JDK 17:

```shell
javac --release 17 JvmMemoryMetrics.java
java -XX:NativeMemoryTracking=summary JvmMemoryMetrics
```

Sau đó lấy PID của JVM và chạy:

```shell
jcmd <pid> VM.native_memory summary scale=MB
```

Các số liệu trong ví dụ là metric từ MXBean; chúng không bao phủ toàn bộ native memory. Dùng chúng cùng NMT và OS/container metrics để đối chiếu.

## 14. Quy trình thực hành từ đầu đến cuối

1. **Xác định câu hỏi.** Heap tăng, native memory tăng, RSS tăng hay container chạm limit? Chọn đúng metric cần kiểm tra.
2. **Bật NMT trước khi chạy.** Dùng summary cho khảo sát ban đầu; detail cho điều tra sâu.
3. **Xác nhận mức tracking.** Kiểm tra `VM.flags` và thử `VM.native_memory summary`.
4. **Chờ startup/warm-up.** Nếu đang tìm leak steady-state, không tạo baseline giữa lúc framework/JIT còn nạp tài nguyên ban đầu.
5. **Ghi baseline.** Chạy `jcmd <pid> VM.native_memory baseline`.
6. **Chạy workload có thể lặp lại.** Ghi concurrency, request rate, thời gian và dữ liệu đầu vào.
7. **Lấy diff.** Dùng `summary.diff` cùng scale nhất quán.
8. **Khoanh vùng category.** So sánh với thread count, class count, heap, buffer pool và RSS.
9. **Chuyển detail nếu cần.** Dùng một instance có detail để xem call site.
10. **Kiểm tra ngoài phạm vi NMT.** Nếu RSS không được giải thích, dùng OS/native tools.
11. **Lặp lại để xác nhận.** Một xu hướng chỉ đáng tin khi tái hiện được trong nhiều lần đo có điều kiện tương đương.
12. **Ghi kết quả và tắt cấu hình chẩn đoán không còn cần thiết.** Nếu đổi mức NMT, triển khai restart với flag phù hợp.

## 15. Bài tập thực hành

### Bài 1 — Bật NMT summary

Chạy ứng dụng Java 17 với:

```shell
java -XX:NativeMemoryTracking=summary -jar app.jar
```

Dùng `jcmd` lấy summary. Xác định Total reserved/committed và các category lớn. Giải thích vì sao không thể gọi committed là RSS.

### Bài 2 — Tạo baseline và diff

Sau warm-up, chạy:

```shell
jcmd <pid> VM.native_memory baseline
```

Tạo tải trong một khoảng thời gian rồi chạy:

```shell
jcmd <pid> VM.native_memory summary.diff scale=MB
```

Ghi lại category tăng nhiều nhất và đưa ra giả thuyết cần kiểm chứng. Lặp lại với workload tương đương để phân biệt tăng trưởng ổn định và dao động bình thường.

### Bài 3 — So sánh summary và detail

Khởi động hai JVM test riêng: một với `summary`, một với `detail`. So sánh output và quan sát mức overhead trên cùng workload. Không đổi mức tracking giữa chừng trong cùng JVM.

### Bài 4 — Theo dõi thread

Tạo workload có thread pool được cấu hình ở các kích thước khác nhau. So sánh NMT Thread category, thread count và RSS. Giải thích vì sao thread stack có thể làm tăng native memory.

### Bài 5 — Theo dõi direct buffer

Tạo một số `ByteBuffer.allocateDirect`, quan sát `BufferPoolMXBean`, NMT và RSS. Giải thích vì sao không nên kỳ vọng một category NMT luôn phản ánh đầy đủ direct buffer trong mọi runtime.

### Bài 6 — Phân biệt heap và native growth

Tạo một workload tăng heap object và một workload tăng native allocation trong môi trường test thích hợp. Quan sát heap metrics, NMT và RSS. Xác định công cụ nào giải thích được từng loại.

### Bài 7 — Điều tra cgroup

Chạy JVM trong container có memory limit. Theo dõi cgroup usage cùng NMT Total committed và heap usage. Giải thích những khoản nào có thể tạo chênh lệch giữa ba số liệu.

### Bài 8 — Tạo báo cáo điều tra

Ghi lại:

- JDK vendor/version và JVM flags.
- NMT level.
- Container memory limit.
- Thời điểm warm-up và baseline.
- Workload.
- Summary và diff.
- RSS/cgroup peak.
- Giả thuyết và bằng chứng xác nhận.

Không kết luận leak chỉ từ một snapshot.

## 16. Câu hỏi tự kiểm tra

1. NMT là gì và được triển khai ở tầng nào của Java runtime?
2. Vì sao NMT không thay thế heap profiler?
3. NMT mặc định bật hay tắt trên HotSpot?
4. Khác biệt giữa `summary` và `detail`?
5. Vì sao phải bật NMT lúc JVM khởi động?
6. `jcmd VM.native_memory baseline` có tác dụng gì?
7. `summary.diff` so sánh với mốc nào?
8. Reserved và committed khác nhau thế nào?
9. Vì sao committed không bằng RSS?
10. Những category nào thường xuất hiện trong NMT summary?
11. Thread count liên quan native memory ra sao?
12. NMT có theo dõi đầy đủ mọi allocation của JNI/native library không?
13. Vì sao direct buffer cần thêm BufferPoolMXBean?
14. Khi nào cần chuyển từ summary sang detail?
15. NMT có overhead không và làm sao đánh giá?
16. Nếu RSS tăng nhưng NMT gần như không đổi, cần kiểm tra gì?
17. Vì sao baseline sau warm-up có thể hữu ích khi tìm tăng trưởng steady-state?
18. OOMKilled khác OutOfMemoryError như thế nào?
19. Có thể bật lại NMT sau khi dùng lệnh shutdown không?
20. Vì sao phải kết hợp NMT với cgroup/container metrics?

## 17. Tài liệu tham khảo

- [Java SE 17 Troubleshooting Guide — Native Memory Tracking](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshooting-memory-leaks.html): sử dụng NMT để điều tra memory leak và native memory.
- [Java SE 17 jcmd Tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): cú pháp gửi diagnostic command tới JVM đang chạy.
- [Java SE 17 VM Options](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): tùy chọn `-XX:NativeMemoryTracking` và các flag runtime.
- [Java SE 17 API — MemoryMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap và non-heap memory usage.
- [Java SE 17 API — BufferPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): thông tin direct và mapped buffer pools.
- [Java SE 17 API — ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html): số lượng và thông tin thread.
- [OpenJDK HotSpot Virtual Machine Guide](https://docs.oracle.com/en/java/javase/17/vm/): các cơ chế runtime và quản lý bộ nhớ của HotSpot.

Native Memory Tracking giúp quan sát cách HotSpot reserve và commit bộ nhớ native theo category, đồng thời cung cấp baseline/diff để tìm xu hướng tăng trưởng. Hãy bật tracking khi khởi động JVM, dùng summary để khoanh vùng và detail khi cần điều tra sâu. Luôn phân biệt NMT với heap object usage, RSS và container memory usage; khi số liệu không khớp, kiểm tra direct buffers, JNI, thư viện native và các vùng nhớ do hệ điều hành quản lý. Kết hợp các nguồn đo này giúp chẩn đoán bộ nhớ Java 17 chính xác hơn mà không nhầm một category NMT với toàn bộ bộ nhớ tiến trình.
