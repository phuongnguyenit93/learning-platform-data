# 6.3 MemoryMXBean, MemoryPoolMXBean và ý nghĩa used, committed, max, init

## Mục tiêu học tập

Khi chẩn đoán Java runtime, một dashboard có thể hiển thị **heap used = 600 MiB**, **heap committed = 768 MiB** và **heap max = 1 GiB**. Các giá trị tưởng đơn giản này thường bị đọc sai thành “Java đã chiếm 768 MiB RAM vật lý”, “còn chính xác 424 MiB là chắc chắn cấp phát được” hoặc “heap tăng nghĩa là memory leak”. Trong thực tế, Java Management API cung cấp **những ảnh chụp của các miền bộ nhớ mà JVM quản lý**, không phải toàn bộ bảng phân bổ bộ nhớ của hệ điều hành.

Bài này tập trung vào hai MXBean chuẩn trong module `java.management`:

- **`MemoryMXBean`:** nhìn tổng thể **Java heap** và **non-heap** mà JVM báo cáo.
- **`MemoryPoolMXBean`:** nhìn từng **memory pool** do JVM cung cấp (ví dụ các vùng heap của collector, Metaspace hoặc code cache ở một số HotSpot configuration).
- **`MemoryUsage`:** đối tượng snapshot mang bốn số `init`, `used`, `committed`, `max` theo **byte**.

Sau bài học, bạn có thể phân biệt chính xác bốn trường, chọn mẫu đo và tỷ lệ giám sát phù hợp, đọc dữ liệu từng pool, hiểu peak/collection usage và threshold, viết chương trình Java 17+ dùng MXBeans, đồng thời **không nhầm Java heap với RSS/native memory hoặc kết luận leak chỉ từ một snapshot**.

> Phạm vi: API Java SE 17+ và hành vi minh họa trên HotSpot/JDK 21. Tên pool, số lượng pool, giới hạn và mức hỗ trợ chức năng có thể khác nhau theo JVM/GC/vendor. Giá trị đang đo phải đến từ **đúng JVM đang gặp sự cố**.

## 1. Ba tầng quan sát: JVM, pool và snapshot

### 1.1 MemoryMXBean — bức tranh heap và non-heap

Lấy bean của **JVM hiện tại** bằng:

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryUsage;

MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
MemoryUsage heap = memory.getHeapMemoryUsage();
MemoryUsage nonHeap = memory.getNonHeapMemoryUsage();
```

Đây là **đoạn code minh họa đặt trong class/method**, chưa phải chương trình độc lập. `getHeapMemoryUsage()` trả snapshot heap, `getNonHeapMemoryUsage()` trả snapshot non-heap do JVM quản lý. Hai snapshot được lấy ở **hai thời điểm gọi riêng biệt**, nên không bảo đảm nguyên tử với nhau.

Java heap thường chứa object/array của ứng dụng và được quản lý bởi garbage collector. Non-heap chứa các vùng JVM quản lý ngoài heap, chẳng hạn metadata về class/method và vùng mã biên dịch JIT, tùy implementation. **Non-heap MXBean không có nghĩa toàn bộ native memory/RSS** của tiến trình, và không đại diện đầy đủ thread stacks, JNI allocations, native malloc, tất cả memory mappings hay mọi loại off-heap buffer.

### 1.2 MemoryPoolMXBean — nhìn vào thành phần

`ManagementFactory.getMemoryPoolMXBeans()` trả danh sách các memory pool hiện được JVM quản lý. Một pool có:

- `getName()`: tên pool do VM đặt.
- `getType()`: `MemoryType.HEAP` hoặc `MemoryType.NON_HEAP`.
- `getUsage()`: snapshot `MemoryUsage` hiện tại, **có thể null** nếu pool không còn hợp lệ hoặc VM không lấy được.
- `getPeakUsage()`: snapshot mức sử dụng đỉnh theo thời gian mà VM theo dõi.
- `getCollectionUsage()`: usage sau hoạt động thu hồi của GC gần nhất mà pool hỗ trợ theo dõi; **có thể null**.
- `isValid()`: pool còn tồn tại trong hệ thống memory management của JVM hay không.
- `getMemoryManagerNames()`: tên các memory manager liên quan, không phải danh sách thread.
- Các khả năng threshold: `isUsageThresholdSupported()` và `isCollectionUsageThresholdSupported()`.

**Đừng hard-code số pool hoặc tên pool** như một phần của Java API contract. Trên HotSpot với G1, bạn *có thể* gặp các tên `G1 Eden Space`, `G1 Survivor Space`, `G1 Old Gen`, `Metaspace`, `Compressed Class Space` hoặc những vùng `CodeHeap`. Với ZGC, Serial GC, một HotSpot release khác hay OpenJ9, phân vùng, tên, giá trị `max` và ngữ nghĩa chi tiết có thể khác.

### 1.3 MemoryUsage — bốn con số của cùng một snapshot

`MemoryUsage` là value object mô tả tình trạng bộ nhớ tại một thời điểm theo **byte**, không phải stream thời gian và không tự chứa nguyên nhân. Với mỗi `MemoryUsage u`:

```java
long init = u.getInit();
long used = u.getUsed();
long committed = u.getCommitted();
long max = u.getMax();
```

Các trường `init` và `max` được phép là `-1`, có nghĩa **“không xác định”**, không phải 0 hay “vô hạn”. `used` và `committed` luôn không âm theo contract của `MemoryUsage`. Khi `max` được xác định, các bất biến là:

```text
0 <= used <= committed
nếu max != -1: committed <= max
init >= 0 hoặc init == -1
max >= 0 hoặc max == -1
```

**Không có bất biến `init <= committed`**: JVM có thể thu hẹp vùng committed dưới giá trị init theo thời gian. Cũng không có quy tắc `init <= used`; `used` có thể rất thấp ngay sau khởi động/GC. Đây là những khác biệt quan trọng khi thiết kế kiểm tra tự động hoặc đọc bảng số liệu.

## 2. Ý nghĩa chính xác của init, used, committed và max

| Trường | Phương thức | Giải thích | Điều **không** được suy ra |
| --- | --- | --- | --- |
| **init** | `getInit()` | Lượng memory ban đầu JVM yêu cầu từ OS để quản lý vùng bộ nhớ này lúc startup; **có thể -1** | Không phải luôn là RAM được giữ vĩnh viễn, không buộc bằng current committed, không buộc bằng used |
| **used** | `getUsed()` | Số byte bộ nhớ hiện đang được sử dụng trong vùng đo; với GC pool, có thể gồm object chưa reachable nhưng chưa được thu hồi | Không phải “live objects” tuyệt đối, không phải RSS và không chứng minh leak |
| **committed** | `getCommitted()` | Số byte memory được **bảo đảm sẵn cho JVM sử dụng** trong phạm vi region/pool đo; có thể tăng/giảm | Không phải số byte resident trong RAM của OS; không phải always allocated objects |
| **max** | `getMax()` | Giới hạn lớn nhất được báo cáo cho memory management của vùng đó, **nếu xác định** | Không phải RAM hiện có của máy, không phải memory đã commit; `-1` không có nghĩa “unlimited” |

Bốn trường thuộc về **cùng một scope**: heap tổng thể, non-heap tổng thể hoặc **một** pool cụ thể. Không thể đem `used` của Metaspace so trực tiếp với `max` của heap để tính phần trăm rồi kết luận Metaspace quá tải.

### 2.1 Used: hiện sử dụng, chưa chắc còn sống sau GC

Với Java heap, `used` có thể tăng nhanh khi tạo object; sau một đợt GC nó có thể giảm. Trong một **garbage-collected memory pool**, tài liệu `MemoryPoolMXBean` nêu `getUsage()` có thể tính cả đối tượng **reachable và unreachable** còn chiếm memory trước khi được thu hồi. Vì vậy:

- Heap `used` tăng trong một phút **không đủ bằng chứng leak**.
- `used` giảm sau GC **không chứng minh không có leak**; có thể vẫn còn tập đối tượng được giữ tăng chậm.
- Heap `used` cao nhưng throughput/pause/latency vẫn bình thường có thể là lựa chọn hợp lý của GC.
- Heap `used` thấp **không loại trừ** `OutOfMemoryError` liên quan metaspace, direct buffer, native memory, thread creation, container memory limit hoặc cấp phát một object quá lớn so với vùng liên tục hiện có.

### 2.2 Committed: đã bảo đảm cho JVM, không phải RSS

`committed` là memory capacity JVM đã sẵn sàng sử dụng cho scope đó. Hình dung:

```text
+----------------------- max (nếu biết) ------------------------+
|      used       | còn trống trong committed | chưa committed |
+----------------- committed ------------------+---------------+
```

Đây là mô hình khái niệm, không nhất thiết các vùng nằm liên tục trong địa chỉ ảo. Khi `used` tăng gần `committed`, JVM **có thể** mở rộng committed nếu còn headroom theo max và tài nguyên OS; cũng có thể khởi động GC hoặc thất bại cấp phát. Khi workload giảm, JVM/GC **có thể** trả bớt memory và `committed` giảm.

Đừng xem `committed - used` là số byte application còn cấp phát “không thể thất bại”: Java object layout, GC reserves, fragmentation, thread scheduling, safepoint, vùng thế hệ, native overhead và tình trạng OS/container làm phép suy diễn đó không an toàn.

`committed` cũng **không đồng nghĩa resident set size (RSS)**. OS RSS thường tính các trang memory đang cư trú, gồm Java heap, thread stacks, JIT code, native allocations, shared mappings... và có thể có khác biệt về loại trang; `MemoryMXBean` không bao phủ tất cả.

### 2.3 Max: trần có thể dùng, không phải khoản cấp phát bảo đảm

Nếu `max = 1 GiB` và `committed = 512 MiB` thì 1 GiB không có nghĩa JVM đang chiếm 1 GiB RAM. Khoảng từ 512 MiB lên 1 GiB **chưa được JVM bảo đảm**; thiếu virtual memory, container limit hay native headroom vẫn có thể gây lỗi allocation trước khi `used` đạt `max`.

Nếu `max == -1`:

- Ghi `undefined` hoặc `unknown`, **không tính** `used / max`.
- Không diễn giải thành `0`, `Long.MAX_VALUE` hay không giới hạn.
- Một số pool, đặc biệt non-heap, không công bố giới hạn có ý nghĩa trong `MemoryUsage` mặc dù runtime/OS vẫn có các ràng buộc thực tế.

`max` có thể thay đổi theo các cơ chế quản lý memory của VM nếu được định nghĩa. Vì vậy giá trị cần lưu kèm timestamp, JDK/GC và option, không mặc định bất biến trên mọi JVM.

### 2.4 Init: điểm bắt đầu, không phải ngưỡng hiện hành

`init` mô tả lượng memory ban đầu VM yêu cầu khi khởi tạo quản lý vùng đó. Trong heap, có thể liên quan `-Xms`, nhưng **không được suy ra mọi pool đều có init bằng một phần cố định của `-Xms`**. JVM có thể co/giãn committed, và `init` có thể không xác định với một pool.

Hình dung ba thời điểm:

| Snapshot minh họa | init | used | committed | max |
| --- | ---: | ---: | ---: | ---: |
| Sau startup | 256 MiB | 100 MiB | 256 MiB | 1.024 MiB |
| Trong đợt tải | 256 MiB | 650 MiB | 768 MiB | 1.024 MiB |
| Sau thời gian nhàn rỗi | 256 MiB | 80 MiB | 192 MiB | 1.024 MiB |

Đây là **số giả định hợp lệ theo contract**, không phải dự đoán HotSpot sẽ luôn co xuống 192 MiB trong cấu hình bất kỳ. Bảng minh họa `init` không đổi nhưng `used` và `committed` thay đổi; committed **có thể nhỏ hơn init**.

## 3. Tính tỷ lệ đúng: từng mẫu số nói một câu chuyện khác

Giả sử heap snapshot có:

```text
init      = 256 MiB
used      = 256 MiB
committed = 512 MiB
max       = 1.024 MiB
```

Ta có:

- **Used/committed** = `256 / 512 = 50%`: mức sử dụng so với memory đã được VM bảo đảm cho scope đó.
- **Used/max** = `256 / 1.024 = 25%`: mức sử dụng so với giới hạn tối đa được công bố.
- **Committed/max** = `512 / 1.024 = 50%`: mức capacity đã commit trong trần của cùng scope.
- **Committed - used** = `256 MiB`: chênh lệch lý thuyết giữa capacity committed và used tại snapshot.
- **Max - used** = `768 MiB`: headroom số học tới max; **không đảm bảo** mọi allocation tương ứng sẽ thành công.

Điểm mấu chốt: cùng một JVM có thể **50% của committed nhưng mới 25% của max**. Một dashboard đặt nhãn chung “heap usage = 50%” mà không cho biết mẫu số là **committed hay max** sẽ gây hiểu nhầm trong capacity planning.

### 3.1 Công thức và điều kiện

```text
utilization_committed = used / committed          (nếu committed > 0)
utilization_max       = used / max                (nếu max > 0)
commitment_ratio      = committed / max           (nếu max > 0)
committed_free_bytes  = committed - used
uncommitted_headroom  = max - committed           (nếu max >= 0)
```

Nếu `committed == 0`, không thực hiện phép chia. Nếu `max == -1`, **không có tỷ lệ used/max có ý nghĩa**. Các tỷ lệ phải gắn cùng `pool/type`, instance và timestamp; không so numerator của instance A với denominator của B.

### 3.2 MiB, MB và byte

API trả `long` theo **byte**, không phải KB/MB. Với giám sát vận hành, nên thống nhất:

- `1 MiB = 1.048.576 bytes` (hệ nhị phân).
- `1 MB = 1.000.000 bytes` (hệ thập phân).
- `-Xmx1g` và `-Xmx1024m` thường dùng đơn vị dạng power-of-two của launcher/JVM; phải xác nhận cú pháp của VM/version.
- Dấu `-1` là sentinel của API, **không phải -1 byte memory thực**.

Lỗi hiển thị thường gặp: lấy `used / 1024 / 1024` rồi gắn nhãn `MB`, trong khi giá trị đúng của phép đổi ấy là **MiB**. Khác biệt khoảng 4,86% giữa MB và MiB có thể khiến các cảnh báo sai ngưỡng ở vùng gần giới hạn.

### 3.3 Khi max thuộc nhiều pool

Một JVM có thể báo `getMax()` của Eden/Survivor/Old khác nhau; chúng chịu cách phân chia của GC, và các giới hạn pool có thể phản ánh capacity tiềm năng thay vì vùng cố định độc lập. **Không cộng `max` của các pool thành heap max** như thể tất cả pool có thể cùng đạt max độc lập. Tương tự, tổng `used` của nhiều pool đọc tuần tự có thể lệch một chút so với `MemoryMXBean.getHeapMemoryUsage().getUsed()` vì GC/allocations diễn ra trong lúc đo.

Chọn **heap tổng thể** khi cần capacity heap; chọn **pool** khi cần biết điều gì đang chiếm chỗ/áp lực trên một region, và ghi rõ điểm đo không nguyên tử.

## 4. Heap, non-heap, memory pool và native memory: đừng cộng sai

### 4.1 Heap memory

Heap là khu vực cho nhiều object/array Java, thường do GC quản lý. `MemoryMXBean.getHeapMemoryUsage()` cung cấp một cách theo dõi heap ở thời điểm hiện tại. Đây không phải “đếm retained objects” và cũng không phải hiện trạng toàn bộ memory process.

Giải thích hiện tượng thường gặp:

- **Used tăng trước GC, giảm sau GC:** nhiều khi là allocation churn bình thường.
- **Committed tăng rồi duy trì:** JVM đã mở rộng heap capacity để đáp ứng tải, không có nghĩa object đang dùng hết.
- **Used sau nhiều GC liên tiếp tăng ở workload tương đương:** đáng điều tra retention, cache, class loaders, lifecycle, nhưng **chưa tự chứng minh leak**.
- **Heap max nhỏ hơn RAM node:** có thể do `-Xmx`, ergonomics, container limits hoặc JVM default khác; cần đọc startup VM flags và resource limits thay vì suy ra từ OS RAM.

### 4.2 Non-heap memory

`getNonHeapMemoryUsage()` phản ánh những miền non-heap mà VM quản lý. Trên HotSpot, những pool như Metaspace và Code Cache có thể xuất hiện. Nhưng native process memory còn có nhiều nguồn ngoài phép đo này:

- Native libraries/JNI allocations.
- Thread stacks và VM internal allocations.
- Direct buffers/mapped buffers và memory-mapped files.
- GC bookkeeping, JIT compiler native allocations.
- Memory của runtime/allocator và các ánh xạ shared libraries.

Không có quy tắc `heap.used + nonHeap.used == RSS`. Sự chênh lệch **không tự là memory leak**; có thể do phạm vi đo khác nhau, reserved/committed/RSS semantics và thời điểm lấy snapshot khác nhau.

Nếu cần đo **direct/mapped buffer pools** trong Java Management API, có thể xem thêm `java.lang.management.BufferPoolMXBean` (ví dụ pool `direct`/`mapped` nếu VM cung cấp). Đó là **loại MXBean khác**, không phải `MemoryPoolMXBean` với `MemoryType.NON_HEAP`. Buffer pool metrics cũng không thay thế theo dõi mọi native allocation.

### 4.3 Metaspace, Code Cache và lỗi bộ nhớ không thuộc heap

Một `OutOfMemoryError: Metaspace` có thể xảy ra khi heap `used/max` vẫn thấp. Một lỗi tạo thread mới có thể do giới hạn process/OS/native stack hoặc container policy; tăng `-Xmx` có thể khiến tổng memory càng căng. Tương tự, lỗi ở direct buffer hay native allocations không nhất thiết được giải quyết bằng tăng heap.

Khi chẩn đoán:

1. Đọc **exception message** và JVM/GC version.
2. Đối chiếu `MemoryMXBean` heap/nonheap và từng `MemoryPoolMXBean` có liên quan.
3. Đối chiếu **OS RSS/container memory**, process thread count, buffer pools, GC logs/JFR và (nếu bật từ startup) Native Memory Tracking.
4. Kiểm tra **giới hạn thực tế** của heap/Metaspace/native, cả việc dùng virtual memory và container constraints.
5. Không sửa cờ trong runtime chỉ vì một snapshot có vẻ cao; xác định nguyên nhân, trend và hệ quả trước.

## 5. Đọc MemoryPoolMXBean đúng cách

### 5.1 Mỗi pool có một loại và tên riêng

`MemoryPoolMXBean.getType()` trả `MemoryType.HEAP` hoặc `MemoryType.NON_HEAP`. Tên pool dùng để gắn nhãn quan sát **cho JVM đó**, không phải một danh mục cố định của Java SE. Việc triển khai hoặc collector khác có thể tạo bớt/thay pool trong vòng đời process; `isValid()` giúp kiểm tra một pool còn tồn tại.

Ví dụ bảng **minh họa chứ không phải kết quả cố định**:

| Pool giả định | Type | Diễn giải thực tế |
| --- | --- | --- |
| G1 Eden Space | HEAP | Vùng chứa nhiều allocation mới; used thường dao động theo chu kỳ GC |
| G1 Survivor Space | HEAP | Vùng chứa object sống qua một số vòng GC, tùy G1 |
| G1 Old Gen | HEAP | Nhiều object dài hạn; theo dõi after-GC usage có ích khi xét retention |
| Metaspace | NON_HEAP | Metadata class/method; chú ý class loader lifecycle |
| CodeHeap 'non-profiled nmethods' | NON_HEAP | Một phần code cache chứa code đã biên dịch của HotSpot |
| Compressed Class Space | NON_HEAP | Một vùng class metadata khi VM sử dụng compressed class pointers |

Không buộc JVM nào cũng có tất cả các dòng, hay cùng tên. Các vùng `CodeHeap` có thể có tên khác theo segmented code cache. Tránh hard-code tên như điều kiện duy nhất cho tất cả dashboards. Khi cần query xuyên collector, nên chuẩn hóa bằng **type + tên pool + VM/version** và có chiến lược mapping rõ.

### 5.2 Current usage, peak usage và collection usage khác nhau

| API của một pool | Câu hỏi trả lời | Lưu ý |
| --- | --- | --- |
| `getUsage()` | Pool đang có usage ước lượng bao nhiêu? | Snapshot; có thể gồm unreachable objects chưa GC |
| `getPeakUsage()` | Giá trị peak được VM ghi nhận kể từ startup/đợt reset là gì? | Không phải average và không phải peak chỉ trong 5 phút dashboard, trừ khi đã thiết kế lại mốc đo |
| `getCollectionUsage()` | Sau lần GC gần nhất có dữ liệu cho pool, usage là gì? | Có thể `null`; có thể “cũ” nếu chưa có GC thích hợp |
| `resetPeakUsage()` | Đặt lại peak statistic | **Thay đổi state** của bean, không làm trong lượt giám sát read-only |
| `isValid()` | Pool còn valid không? | Cần xét khi JVM thay đổi các memory pools |

**Peak** có thể rất lớn do một spike đã kết thúc. Nếu UI cứ hiển thị peak cao, không có nghĩa current used đang cao. Một graph lấy `getPeakUsage().getUsed()` mỗi 10 giây thường **không giảm** cho tới khi reset/restart; dùng nó để cảnh báo “đang căng memory” có thể false positive. Nên hiển thị current và peak thành **hai series riêng**.

**Collection usage** thường có giá trị phân tích khi muốn biết bao nhiêu object vẫn chiếm memory sau đợt thu hồi GC mà VM ghi nhận. Tuy nhiên:

- Có thể null nếu VM/pool không hỗ trợ.
- Thời điểm của “most recent collection” không nhất thiết bằng timestamp bạn đang scrape.
- Pool có thể được collector quản lý đồng thời, không có một điểm “sau GC” rõ ràng để đo.
- `getCollectionUsage()` **không tự thực hiện GC**; không được dùng như một nút “ép JVM cleanup”.

### 5.3 Mối quan hệ với MemoryMXBean

`MemoryMXBean` báo heap/non-heap tổng thể. Danh sách pools có thể bổ sung chi tiết, nhưng phép cộng giá trị pool **không là transaction nhất quán**. Snapshot của pool A và pool B được thu ở hai thời điểm trong JVM đang chạy, có thể vừa xảy ra allocation/GC giữa chừng.

Đối với capacity toàn heap, lấy **`MemoryMXBean.getHeapMemoryUsage()`** làm tín hiệu chính. Nếu dùng tổng từ pools, phải nói rõ đó là ước lượng theo sampling riêng và có thể chênh; việc dashboard hiện lệch vài MiB không tự chỉ ra bug của MXBean.

### 5.4 Một pool có max = -1 trong khi heap tổng thể có max

Có thể xảy ra. `max` của pool là **giới hạn do pool đó công bố**, không phải phép chia bắt buộc từ total heap max. Một pool có thể thay đổi dung lượng với GC, nên VM không thể hoặc không chọn công bố max cục bộ có ý nghĩa. Đừng đem `getMax() == -1` thay bằng `getHeapMemoryUsage().getMax()`, vì hai scope khác nhau.

Nếu muốn cảnh báo pool, chọn ngưỡng theo **usage, after-GC trend và đặc tính pool/collector**, thay vì ép công thức `used/max` cho mọi pool.

## 6. Ví dụ Java 17+ hoàn chỉnh: đọc tổng thể và từng pool

Tạo tệp **`MemoryMxBeanLab.java`**. Chương trình thực hiện **chỉ đọc**, không gọi GC, không đặt threshold và không reset peak. Để không bịa số byte thực của một máy chưa đo, nó in bốn dòng đầu **xác định hoàn toàn** từ một `MemoryUsage` giả lập, sau đó in các giá trị thực của JVM đang chạy.

```java
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryUsage;
import java.util.Comparator;
import java.util.Locale;

public final class MemoryMxBeanLab {
    private static String display(long value) {
        return value == -1L ? "undefined" : Long.toString(value);
    }

    private static void printUsage(String scope, MemoryUsage usage) {
        if (usage == null) {
            System.out.println(scope + " unavailable");
            return;
        }

        System.out.printf(Locale.ROOT,
                "%s used=%d committed=%d max=%s init=%s%n",
                scope,
                usage.getUsed(),
                usage.getCommitted(),
                display(usage.getMax()),
                display(usage.getInit()));
    }

    public static void main(String[] args) {
        // Dữ liệu giả lập để kiểm tra contract, không lấy từ JVM.
        MemoryUsage sample = new MemoryUsage(-1L, 256L, 512L, -1L);
        System.out.println("sample.used=" + sample.getUsed());
        System.out.println("sample.committed=" + sample.getCommitted());
        System.out.println("sample.max=" + display(sample.getMax()));
        System.out.println("sample.used<=committed=" +
                (sample.getUsed() <= sample.getCommitted()));

        // Từ đây trở đi là dữ liệu của chính JVM chạy chương trình.
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();
        printUsage("heap", memory.getHeapMemoryUsage());
        printUsage("nonheap", memory.getNonHeapMemoryUsage());

        ManagementFactory.getMemoryPoolMXBeans().stream()
                .sorted(Comparator.comparing(MemoryPoolMXBean::getName))
                .forEach(pool -> {
                    System.out.println("pool.name=" + pool.getName()
                            + " type=" + pool.getType()
                            + " valid=" + pool.isValid());
                    printUsage("  current", pool.getUsage());
                    printUsage("  peak", pool.getPeakUsage());
                    printUsage("  afterCollection", pool.getCollectionUsage());
                    System.out.println("  usageThresholdSupported=" +
                            pool.isUsageThresholdSupported());
                    System.out.println("  collectionThresholdSupported=" +
                            pool.isCollectionUsageThresholdSupported());
                });
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac MemoryMxBeanLab.java
java -Xms64m -Xmx256m MemoryMxBeanLab
```

**Bốn dòng stdout đầu tiên chính xác, không phụ thuộc máy:**

```text
sample.used=256
sample.committed=512
sample.max=undefined
sample.used<=committed=true
```

Những dòng còn lại **không có stdout cố định**: số byte, tên pools, peak, collection usage, threshold support và cả GC được dùng phụ thuộc JVM, vendor, version, workload và thời điểm chạy. Một dòng mô phỏng hình thức, **không phải expected output**:

```text
heap used=<byte-thuc-te> committed=<byte-thuc-te> max=<byte-hoac-undefined> init=<byte-hoac-undefined>
```

Hãy thay các giá trị mô phỏng bằng output thu thật; không copy góc nhọn hoặc chữ giả định vào kết quả chạy.

### 6.1 Vì sao mẫu giả lập có ích?

Constructor `new MemoryUsage(-1L, 256L, 512L, -1L)` hợp lệ vì:

- `init = -1`: VM không công bố giá trị khởi tạo.
- `max = -1`: giới hạn không xác định.
- `used = 256` và `committed = 512` đều không âm và `used <= committed`.

Thử `new MemoryUsage(0, 513, 512, 1024)` sẽ ném `IllegalArgumentException` vì `used > committed`. Đây là tính chất của object `MemoryUsage` do API kiểm tra, **không phải cách để phát hiện memory leak**.

### 6.2 Vì sao không in “tỷ lệ sử dụng” vô điều kiện?

Bài thực hành cố ý in **giá trị raw**. Nếu tính tỷ lệ trong hệ thống monitoring, phải kiểm tra `max > 0` hoặc `committed > 0`. Trường hợp `max = -1` không phải 0 và không được chia; nếu có sự thay đổi của pool/GC hoặc tên pool trùng giữa instances, cần xử lý scope và identity trước.

Có thể dùng helper tính phần trăm chỉ khi mẫu số hợp lệ:

```java
// Đoạn bổ sung nằm trong một class, không phải chương trình độc lập.
static double usagePercent(long used, long capacity) {
    return capacity > 0 ? (100.0 * used / capacity) : Double.NaN;
}
```

`Double.NaN` biểu thị tỷ lệ **không xác định** để tầng trình bày xử lý. Không nhất thiết xuất `NaN` thành một sample series trong mọi metrics backend; khi không có mẫu số, nhiều hệ thống tốt hơn là **không xuất tỷ lệ** hoặc gắn trạng thái unavailable.

### 6.3 Vì sao việc đọc này là “đọc JVM mẫu”, chưa phải production?

Chạy chương trình tạo **một JVM mới**. Nó không mô tả JVM service đang gặp sự cố. Để theo dõi production, cần:

- Instrument **đúng service process** để đọc MXBeans hoặc dùng JMX/management endpoint có quyền phù hợp.
- Ghép dữ liệu với application/build, host/container, PID, JVM start time và timestamp UTC.
- So các snapshot trong **cùng process** và workload tương ứng; đừng coi kết quả từ một JVM lab là output của production.
- Tránh công khai bean dumps chứa path, system properties, JVM command line hoặc tên module nhạy cảm khi mở JMX remote.

## 7. Theo dõi thay đổi theo thời gian: tránh kết luận từ một snapshot

Một `MemoryUsage` không tự chứa timestamp hay lịch sử. Khi thu nhiều mẫu, hệ thống quan sát phải gắn:

- `capturedAtUtc`: thời điểm JVM/collector ghi nhận dữ liệu.
- `instance/processStart`: xác định đúng JVM, tránh nối nhầm qua restart.
- `scope`: `heap`, `nonheap` hoặc tên/type pool.
- `usedBytes, committedBytes, maxBytes, initBytes`: raw bytes; đánh dấu giá trị sentinel.
- `gcName, javaVersion, relevantFlags` nếu cần so sánh giữa GC/JDK.
- Độ dài polling interval, số mẫu mất, exporter lags và giới hạn retention.

### 7.1 Ví dụ một chu kỳ cấp phát bình thường

Giả sử một service có max 1 GiB và quan sát tại các thời điểm gần nhau:

| Mốc | Heap used | Heap committed | Diễn giải hợp lý |
| --- | ---: | ---: | --- |
| T0 | 250 MiB | 512 MiB | JVM có không gian trong committed |
| T1 | 460 MiB | 512 MiB | Nhiều object được tạo; chưa đủ biết reachable hay không |
| T2 | 610 MiB | 768 MiB | Heap có thể mở rộng committed và dùng thêm memory |
| T3 sau GC | 290 MiB | 768 MiB | Nhiều object đã được thu hồi; committed không buộc giảm ngay |
| T4 lâu sau | 280 MiB | 512 MiB | JVM có thể thu hẹp committed nếu GC/policy cho phép |

Số là **giả định**. Đây là một cơ chế có thể xảy ra, không phải biểu đồ bắt buộc cho mọi collector. Dữ liệu quan trọng là **tương quan với GC/events/workload**: nếu chỉ nhìn T2, bạn có thể báo leak sai.

### 7.2 Used tăng sau GC: khi nào đáng nghi?

Với heap, một chuỗi các điểm **sau những lần GC có tác dụng thu hồi phù hợp** dưới tải và trạng thái tương tự thường hữu ích hơn chỉ nhìn đường used thô. Nếu đáy `used` tăng qua nhiều chu kỳ, đó là tín hiệu cần kiểm tra retained objects, cache, references, classloader hoặc workload thay đổi.

Tuy nhiên, “sau GC” là khái niệm phụ thuộc collector: nhiều GC chạy concurrent/incremental, một số pool có `getCollectionUsage() == null`. Không được gán nhãn mỗi mẫu sau lúc thấy một log “GC” là live heap toàn phần. Hãy đối chiếu loại GC event, phạm vi collection và timestamps.

### 7.3 Sampling interval ảnh hưởng nhận định

Nếu heap có spikes 2 giây nhưng dashboard scrape mỗi 30 giây, gauge `used` có thể bỏ lỡ đỉnh. `getPeakUsage()` của pool có thể lưu một đỉnh từ **cả đời JVM** (hoặc từ lần reset), không nhất thiết đỉnh trong cửa sổ 30 giây. Để nghiên cứu áp lực allocation ngắn hạn, dùng thêm JFR allocation/GC events, histograms/metrics phù hợp và sampling interval có khả năng thấy hiện tượng.

Không “sửa” chênh lệch bằng cách tự ép GC mỗi khi scrape: `System.gc()`/`MemoryMXBean.gc()` không phải công cụ đọc thụ động, có thể ảnh hưởng latency và làm biến dạng workload đang điều tra.

## 8. Peak usage và collection usage: dùng khi nào?

### 8.1 Peak là watermark theo thời gian kể từ mốc reset

`pool.getPeakUsage()` trả `MemoryUsage` của peak mà VM theo dõi. Theo API, giá trị peak được duy trì kể từ khi JVM bắt đầu hoặc khi gọi `resetPeakUsage()`. Dùng để phát hiện JVM đã từng chạm mức sử dụng cao, đặc biệt hữu ích với spikes mà polling thưa có thể bỏ qua.

Giới hạn:

- Peak có thể xảy ra trước đợt incident và vẫn còn ghi nhận.
- Reset peak là **hành động thay đổi diagnostic state**, có thể ảnh hưởng dashboards của người khác.
- Không mặc định peak của các pools được ghi tại cùng một thời điểm.
- Peak usage khác p95/p99 hoặc high-water mark trong cửa sổ tùy chọn của time-series database.

Nếu cần “đỉnh 5 phút qua” cho dashboard, nên lưu raw used samples với lịch sử đủ dày rồi tính max over time tại backend, ghi rõ độ phân giải. Đừng lẫn với peak từ lúc JVM startup.

### 8.2 Collection usage là “sau lần thu hồi gần nhất”

`pool.getCollectionUsage()` trả usage sau lần VM gần đây nhất đã cố gắng thu hồi object không còn dùng trong pool. Nếu không được hỗ trợ, trả **null**. Từ đó, một số pool (ví dụ pool chứa object dài hạn dưới GC có điểm collection rõ) có thể cho tín hiệu về **tập đối tượng còn chiếm không gian sau GC**.

Không hiểu nhầm:

- “Collection usage” không bằng “live object graph chính xác”.
- Một số GC concurrent không cung cấp điểm collection rõ để threshold/collection usage hoạt động.
- `getCollectionUsage()` có thể là snapshot cũ nếu chưa có GC phù hợp.
- Dữ liệu của collection usage và current usage không được đọc nguyên tử cùng một thời điểm.

Khi nghi leak, kết hợp collection usage với class histogram/heap dump có kiểm soát hoặc JFR allocation, và không coi một ảnh chụp thay cho lịch sử tăng dần.

## 9. Usage threshold và collection usage threshold

`MemoryPoolMXBean` hỗ trợ hai loại threshold **theo khả năng của pool**, không phải thuộc tính chắc chắn có trên mọi VM. `MemoryMXBean` có thể phát notification khi pool vượt threshold do JVM phát hiện.

### 9.1 Usage threshold

Một pool có thể hỗ trợ `isUsageThresholdSupported()`. Nếu có, `setUsageThreshold(long bytes)` đặt ngưỡng, nhưng đây là **hành động thay đổi cấu hình monitoring của JVM**, không phải thao tác read-only. Ngưỡng dương bật kiểm tra; 0 tắt. Việc kiểm tra diễn ra tại thời điểm JVM thấy phù hợp, **không cam kết phát notification ngay lập tức tại từng byte vượt ngưỡng**.

`getUsageThresholdCount()` là số lần JVM **phát hiện ngưỡng bị vượt** theo semantics của threshold; không phải số allocation hay số GC. `isUsageThresholdExceeded()` phản ánh trạng thái vượt ngưỡng theo khả năng JVM hỗ trợ. Cần kiểm tra `isUsageThresholdSupported()` trước khi gọi API liên quan, vì một số API có thể ném `UnsupportedOperationException` nếu không được hỗ trợ.

### 9.2 Collection usage threshold

`isCollectionUsageThresholdSupported()` cho biết pool hỗ trợ ngưỡng **sau hoạt động collection** không. Điều này đặc biệt phù hợp khi muốn cảnh báo memory vẫn cao sau GC, tránh chỉ báo động vì những spike ngắn trước GC.

Nếu được hỗ trợ, `setCollectionUsageThreshold(long bytes)` thiết lập ngưỡng collection; cũng là thay đổi state. Khi VM phát hiện sau GC phù hợp mà usage đạt/vượt ngưỡng, nó có thể tăng counter và phát notification thông qua `MemoryMXBean`. Pool không có điểm collection rõ có thể **không hỗ trợ** ngưỡng này.

Không lấy notification count làm số lần “leak” hay số lần GC. Notification mang ý nghĩa **JVM phát hiện vượt một ngưỡng đã cấu hình**, phụ thuộc thời điểm kiểm tra và việc usage giảm rồi tăng lại. Những vượt ngưỡng liên tục không buộc tạo notification lặp vô hạn.

### 9.3 Notifications từ MemoryMXBean

`MemoryMXBean` có thể phát `MemoryNotificationInfo.MEMORY_THRESHOLD_EXCEEDED` hoặc `MEMORY_COLLECTION_THRESHOLD_EXCEEDED` khi pool tương ứng hỗ trợ và ngưỡng đã được thiết lập. Các notification thuộc cơ chế JMX và thường chứa pool name, usage snapshot và count, không phải sự kiện về object cụ thể nào gây áp lực.

Hãy phân biệt hai thao tác:

- **Đọc/monitor:** gọi `getUsage()`, `getPeakUsage()`, kiểm tra flags hỗ trợ; thường phù hợp trong diagnostic session.
- **Điều khiển:** gọi `setUsageThreshold`, `setCollectionUsageThreshold`, `resetPeakUsage` hoặc `MemoryMXBean.gc()`; phải có mục tiêu/quyền/thỏa thuận và đánh giá tác động.

Không tạo ví dụ tự đặt threshold tùy tiện trong production vì có thể phá chính sách cảnh báo đã được cấu hình. Trong bài tập read-only, in cờ `...Supported` là đủ để biết có thể xây dựng cơ chế đó sau này hay không.

## 10. Một số lệnh JVM bổ trợ khi MXBeans chưa đủ

MXBeans hữu ích cho tình trạng hiện tại của memory management; để giải thích **vì sao** used/committed thay đổi, cần các nguồn bổ sung. Ví dụ dưới đây dành cho HotSpot JDK 21, PID **12345 chỉ là giả định**:

```bash
jcmd 12345 VM.version
jcmd 12345 VM.flags
jcmd 12345 GC.heap_info
jcmd 12345 JFR.check
```

- `VM.version`: xác định đúng JVM/version.
- `VM.flags`: xem effective JVM flags liên quan heap/GC. Đừng suy ra chỉ từ `-Xmx` ghi trong manifest.
- `GC.heap_info`: nhận thông tin heap tùy GC; cùng scope nhưng cấu trúc không nhất thiết giống hoàn toàn các MXBean metrics.
- `JFR.check`: xem recording JFR đang chạy, không tự bắt đầu recording.

Khi cần **chẩn đoán sâu**, GC logs/JFR events giúp xác định chu kỳ GC, pause, allocation; heap dump/class histogram có thể phân tích object types/references nhưng tạo chi phí/tác động cao và có thể chứa dữ liệu nhạy cảm. Không bật heap dump chỉ để xác minh một số `used`.

### 10.1 NMT khác MemoryMXBean

Native Memory Tracking (NMT) trên HotSpot theo dõi nhiều vùng cấp phát nội bộ JVM. Muốn dùng `jcmd PID VM.native_memory summary`, thông thường phải bật NMT từ **startup** (chẳng hạn `-XX:NativeMemoryTracking=summary`) vì trạng thái off không thể chuyển thành summary/detail trên tiến trình đang chạy. NMT có các cột reserved/committed theo category khác với `MemoryUsage`.

NMT vẫn không bao phủ toàn bộ native memory từ các thư viện bên thứ ba; số của NMT cũng không buộc bằng RSS. Không dùng công thức `RSS = heap.used + nonheap.used + NMT.total`: các nguồn đo có phạm vi khác nhau, và nhiều vùng **chồng lấp**.

### 10.2 BufferPoolMXBean khác MemoryPoolMXBean

`BufferPoolMXBean` cung cấp những thông tin như `getName()`, `getCount()`, `getTotalCapacity()`, `getMemoryUsed()` cho buffer pools mà VM hỗ trợ. Ví dụ:

```java
// Đoạn minh họa bên trong method, không phải chương trình độc lập.
for (java.lang.management.BufferPoolMXBean p :
        java.lang.management.ManagementFactory.getPlatformMXBeans(
                java.lang.management.BufferPoolMXBean.class)) {
    System.out.println(p.getName() + " buffers=" + p.getCount()
            + " capacityBytes=" + p.getTotalCapacity()
            + " memoryUsedBytes=" + p.getMemoryUsed());
}
```

Bộ dữ liệu này hữu ích khi direct/mapped buffers làm tăng memory ngoài Java heap. Nó **không phải cùng contract bốn trường `init/used/committed/max` của `MemoryUsage`**, và `getMemoryUsed()` cũng có thể trả -1 khi VM không có ước lượng phù hợp. Dùng để bổ sung, không thay các metrics heap/pool hay OS.

## 11. Tình huống chẩn đoán thường gặp

### Tình huống A — Heap used gần max, committed vẫn chưa chạm max

Ví dụ snapshot giả định:

```text
heap.used      = 750 MiB
heap.committed = 800 MiB
heap.max       = 1.024 MiB
```

`used/committed ≈ 93,75%`, `used/max ≈ 73,24%`. JVM **có thể** còn quyền mở rộng committed theo max, nhưng điều đó không đảm bảo cấp phát thành công. Cần xem GC frequency/pause, allocation rate, CPU, container memory limits và biến động committed. Nếu ngay sau một GC phù hợp used giảm về 320 MiB, đó có thể là spike do workload; nếu đáy sau GC ngày càng tăng trong tải so sánh được, cần điều tra giữ tham chiếu.

Không đưa cảnh báo “heap gần OOM” chỉ từ `used/committed` cao khi `used/max` còn thấp mà không xét GC behavior; tuy nhiên cũng không xem `used/max` thấp là bảo đảm an toàn.

### Tình huống B — Committed tăng mà used gần như không đổi

Có thể JVM đã mở rộng capacity theo dự đoán tải, giữ lại để tránh trả/nhận memory liên tục, hoặc thay đổi cấu trúc pool. Đây **không tự là leak** vì retained objects vẫn chưa tăng rõ. Kiểm tra committed/max, GC policy, heap flags, OS RSS và container memory behavior. Trong hệ thống memory-constrained, committed cao có thể làm tăng áp lực tổng thể dù used thấp; nhưng bản thân số committed không bằng số trang resident đã dùng.

### Tình huống C — Heap bình thường nhưng RSS của container tăng

Đầu tiên **không cộng** heap/nonheap used để khẳng định chênh lệch là “memory leak chưa được thống kê”. Kiểm tra:

- `getNonHeapMemoryUsage()` và pools như Metaspace/Code Cache.
- `BufferPoolMXBean` cho direct/mapped buffers nếu có.
- Số thread, stack sizes, native libraries, mapped files và các chỉ số OS.
- NMT nếu đã bật từ startup; giới hạn coverage.
- Container memory limit, memory pressure, page cache/accounting theo hệ đo.

Kết luận phải nói rõ nguồn và phạm vi. Có thể có vấn đề native memory mà heap MXBean không nhìn thấy.

### Tình huống D — Sau deployment, Metaspace pool tăng

Class loading/JIT trong warm-up có thể làm non-heap tăng hợp lý. Nếu Metaspace used tiếp tục tăng theo mỗi lần reload module hoặc tạo class loader mới mà không giảm qua nhiều chu kỳ, cần xem class loader retention, dynamic proxy, reflection/generated classes, deployment strategy và JFR/VM classloader diagnostics. Không dùng ngưỡng cố định “Metaspace > X MiB = leak” chung cho mọi ứng dụng.

### Tình huống E — Pool max = -1, cảnh báo biểu thị 100% hoặc số âm

Đây là lỗi logic khi biến sentinel thành mẫu số. Ngay tại exporter:

```text
if max <= 0:
    export maxBytes as unavailable/undefined
    do NOT calculate used / max
else:
    calculate used / max
```

Đây là **pseudocode**, không phải Java. Nếu backend không hỗ trợ missing value tốt, tách metric `hasDefinedMax` hoặc gắn metadata, đừng làm giả max = 1 hoặc 0. Điều chỉnh query/dashboard để không đưa pool có undefined max vào tỷ lệ.

### Tình huống F — Nhìn peak cao liên tục sau một spike ngắn

`getPeakUsage()` không phải “used hiện tại”. Nếu dashboard vẽ `peak.used` mà đặt nhãn “current memory used”, người đọc sẽ tưởng JVM vẫn ở mức cao. Tách hai đường và ghi chú peak kể từ startup/reset, còn current từ `getUsage()`. Muốn peak 5 phút, cần lưu raw time series đủ độ phân giải rồi tính max over window.

### Tình huống G — Sau GC collection usage vẫn cao

Nếu pool hỗ trợ `getCollectionUsage()` và có event GC thích hợp, đây có thể là tín hiệu nhiều đối tượng tiếp tục chiếm pool. Tuy nhiên cần so workloads, collector semantics, thời gian GC, rate của requests và công việc background. Đừng kết luận ngay “leak đã được chứng minh”; có thể là cache sống hợp lệ, retained session/batch state hoặc snapshot cũ.

## 12. Thiết kế metrics và dashboard cho MXBeans

Một cách chuẩn hóa (tên chỉ là **đề xuất**, không phải metric name bắt buộc của Prometheus/OTel) là:

| Series đề xuất | Scope/nhãn | Giá trị |
| --- | --- | --- |
| `jvm_memory_used_bytes` | `area=heap/nonheap`, instance | `MemoryMXBean` `used` |
| `jvm_memory_committed_bytes` | area, instance | `committed` |
| `jvm_memory_max_bytes` | area, instance, chỉ khi xác định | `max` |
| `jvm_memory_init_bytes` | area, instance, chỉ khi xác định | `init` |
| `jvm_memory_pool_used_bytes` | pool, type, instance | `MemoryPoolMXBean.getUsage().getUsed()` nếu non-null |
| `jvm_memory_pool_peak_used_bytes` | pool, type, instance | `getPeakUsage().getUsed()` |
| `jvm_memory_pool_after_gc_used_bytes` | pool, type, instance | `getCollectionUsage().getUsed()` khi hỗ trợ và dữ liệu có sẵn |

Trong hệ thống sử dụng Micrometer, OpenTelemetry hoặc JMX exporter, **tên thực và semantics của metric có thể khác**; luôn kiểm tra cấu hình exporter, đơn vị, labels và dấu hiệu thiếu dữ liệu thay vì giả định hoàn toàn từ tên.

### 12.1 Mỗi panel phải có scope và mẫu số

- Heap tổng: used bytes, committed bytes và max bytes (nếu có) trên cùng chart hoặc các biểu đồ tương quan.
- Heap pressure: `used/max` khi `max > 0`; vẽ rõ mẫu số và cảnh báo đặc thù workload.
- Capacity commitment: `committed/max` khi được định nghĩa; hữu ích để thấy JVM đã mở rộng heap đến mức nào.
- Memory pools: mỗi pool một line/legend, có type và GC/vendor context; không gộp những pool có semantics khác nhau thành một “heap ratio” không rõ nguồn.
- Native process memory: RSS/container usage **từ OS/agent** ở panel riêng; không cộng với MXBean numbers.

### 12.2 Dữ liệu mất, số âm sentinel và exporter bugs

Với `init/max` không xác định, ghi rõ **unavailable** chứ không chuyển sang 0 rồi đi tính percentage. Không nên đưa giá trị `-1` vào biểu đồ như memory âm. Nếu `getUsage() == null` hoặc pool không còn valid, exporter phải bỏ/đánh dấu series tương ứng, **không tự báo used=0** vì 0 là một quan sát khác về mặt ngữ nghĩa.

Khi process restart, các giá trị peak/threshold counters khởi động lại theo VM; cần phân biệt series mới với dữ liệu lịch sử. Nhãn `instance`/`processStartTime` hoặc resource identity giúp tránh nối tiếp hai JVM như thể một.

### 12.3 Tần suất thu và độ chính xác

MXBeans phản ánh snapshot. Nếu đo mỗi 30 giây, các spikes ngắn có thể nằm giữa hai lần poll; nếu poll mọi mili-giây, bạn có thể thêm overhead và vẫn bỏ qua peak theo ý nghĩa bộ nhớ khi GC chạy đồng thời. Chọn chu kỳ theo SLA, độ dài sự cố và tổng số series; dùng GC logs/JFR events khi cần timeline chi tiết.

Đặc biệt với memory pool có nhiều object và cách tính usage đắt theo implementation, đọc liên tục có thể tăng overhead. Tài liệu `MemoryPoolMXBean` gọi `getUsage()` là phép đo nhẹ **trong đa số trường hợp**, nhưng có pool cần tính toán tốn kém; phải đo thực và không coi mỗi getter luôn O(1).

### 12.4 Không suy từ metrics correlation sang nguyên nhân

Ví dụ heap used và latency tăng cùng lúc có thể do allocation pressure, GC, contention, batch job, downstream backlog hoặc đơn giản tăng tải. Để kết luận, đối chiếu GC pause, thread states, throughput, allocation samples, error traces và thời điểm rollout. MXBeans là một mảnh chứng cứ, không phải profiler hay object graph.

## 13. Quy trình thu thập phục vụ incident

### Bước 1: Gắn đúng JVM và thời điểm

Ghi service, environment, host/container, PID, process start time, JDK version/vendor, GC, heap options và timestamp UTC. Đừng đo bằng một Java process demo rồi suy ra JVM production.

### Bước 2: Thu tổng thể trước

Lấy `heap` và `nonheap` từ `MemoryMXBean`, bao gồm **bốn trường raw bytes**. Kiểm tra `used <= committed` và `max == -1`. Nếu thấy tỷ lệ báo sai, xem đơn vị và mẫu số.

### Bước 3: Xem pools để tìm vùng có áp lực

Đọc `getMemoryPoolMXBeans()`, tên/type và current `getUsage()`. Dùng `getPeakUsage()` khi cần lịch sử watermark, `getCollectionUsage()` nếu VM hỗ trợ và có giá trị; phân biệt các loại. Không sửa threshold/peak trong một lượt read-only.

### Bước 4: So qua các mốc và correlate

Giữ ít nhất một cửa sổ baseline, một đoạn xảy ra vấn đề và đoạn hồi phục; ghi GC events và application throughput/request mix. Tính `used/max` chỉ với same-scope max xác định; không cộng tất cả pool max.

### Bước 5: Mở rộng công cụ theo triệu chứng

Nếu nghi heap retention, dùng allocation profiling/heap analysis có kiểm soát; nếu RSS vượt xa heap metrics, bổ sung buffer pools, OS/process/container và NMT nếu bật; nếu Metaspace tăng, xem class loading/classloader. Đánh giá ảnh hưởng trước khi dùng heap dump, forced GC hoặc công cụ nặng.

### Bước 6: Báo cáo kết luận có giới hạn

Ví dụ cấu trúc báo cáo:

```text
Tại 10:22:14 UTC, JVM service A (PID..., start time...)
  heap.used      = 256 MiB
  heap.committed = 512 MiB
  heap.max       = 1024 MiB
  used/max       = 25%
  used/committed = 50%

Pool liên quan:
  name = <ten-tu-JVM>, type = HEAP
  current.used = <gia-tri>, afterCollection.used = <gia-tri-neu-co>

Quan sát:
  used tăng theo đợt tải, có/không có GC trong khoảng đo.
Chưa đủ bằng chứng:
  leak, nguyên nhân RSS, vị trí code giữ references.
Bước tiếp:
  xem JFR/GC logs, workload và heap analysis nếu cần.
```

Các số là **giả định minh họa tỷ lệ**, không phải dữ liệu từ production. Chỉ kết luận các điều đã đo được trong đúng môi trường/thời gian.

## 14. Các nhầm lẫn phổ biến

| Nhầm lẫn | Điều chính xác hơn |
| --- | --- |
| “`used` chính là dung lượng object còn sống sau GC.” | Có thể gồm unreachable objects trước khi chúng được thu hồi; xem GC/collection context. |
| “`committed` là lượng RAM vật lý process đang sử dụng.” | Nó là capacity VM bảo đảm, không bằng RSS/working set. |
| “`max` là số byte JVM đã được OS cấp sẵn.” | Giới hạn tối đa, không phải memory đã commit/physical RAM. |
| “`max = -1` tức không giới hạn.” | Nó chỉ có nghĩa giới hạn **không xác định** theo API. |
| “`init` luôn bằng `committed`.” | Committed có thể tăng/giảm; thậm chí nhỏ hơn init sau shrink. |
| “`used/max` và `used/committed` là một.” | Hai mẫu số mô tả hai câu hỏi khác nhau. |
| “Pool max có thể cộng thành tổng heap max.” | GC có thể phân phối linh hoạt; các max pool không buộc độc lập. |
| “Tổng used tất cả pool luôn bằng used của MemoryMXBean.” | Các snapshot không nhất quán nguyên tử và phạm vi/timing có thể khác. |
| “Mọi JVM đều có Eden/Survivor/Old/Metaspace với cùng tên.” | Phụ thuộc GC, implementation, vendor/version. |
| “Non-heap used + heap used chính là RSS.” | Không phản ánh mọi native/offheap/mappings/OS accounting. |
| “getCollectionUsage() luôn có và thể hiện sau GC mới nhất ngay lúc scrape.” | Có thể null hoặc phản ánh lần collection phù hợp gần nhất trước đó. |
| “getPeakUsage() là peak trong 5 phút vừa qua.” | Là peak do VM theo dõi từ startup/reset, không phải cửa sổ dashboard. |
| “resetPeakUsage() là chỉ đọc.” | Nó thay đổi state của statistic. |
| “setUsageThreshold() có thể dùng để xem ngưỡng mặc định.” | Đây là setter thay đổi threshold; kiểm tra support và getter trước. |
| “Threshold notification đến tức thời mỗi lần vượt ngưỡng.” | JVM kiểm tra theo cơ chế/thời điểm phù hợp; không phải sensor theo từng byte. |
| “GC chậm tức chắc chắn memory leak.” | GC pressure có nhiều nguyên nhân; cần đối chiếu allocation, retained usage và workload. |
| “Heap used dưới max chứng minh không thể OOM.” | Vẫn có thể OOM do native/metaspace/direct/container hoặc cấp phát không thành công. |

## 15. Tự kiểm tra và đáp án

**Câu 1.** Một snapshot có `used=400 MiB`, `committed=800 MiB`, `max=1.600 MiB`. Tỷ lệ used/committed và used/max là bao nhiêu?

**Đáp án:** used/committed = **50%**; used/max = **25%**. Cả hai hợp lệ nếu cùng scope, nhưng có ý nghĩa khác nhau.

**Câu 2.** Một pool báo `init=256 MiB`, `committed=192 MiB`. Có trái contract không?

**Đáp án:** không. `committed` được phép giảm dưới `init` khi JVM trả memory theo thời gian. Bất biến quan trọng là `used <= committed`, và `committed <= max` nếu max xác định.

**Câu 3.** `getMax() == -1`, dashboard tính `used / -1` ra phần trăm âm. Xử lý?

**Đáp án:** đánh dấu **undefined** và bỏ phép tính tỷ lệ; `-1` là sentinel không xác định, không phải capacity âm hay vô hạn.

**Câu 4.** Heap used tăng từ 200 MiB lên 650 MiB rồi giảm về 220 MiB sau GC. Có thể kết luận leak không?

**Đáp án:** không. Mô hình này phù hợp allocation churn. Cần quan sát nhiều chu kỳ, collection usage (nếu có), workload và retained references để đánh giá leak.

**Câu 5.** `MemoryPoolMXBean.getCollectionUsage()` trả null. Có được xuất value 0 để tránh chart gap không?

**Đáp án:** không. Null là không có số liệu/không được hỗ trợ, khác với snapshot usage thực bằng 0. Ghi unavailable và dựa trên current usage cùng các nguồn khác.

**Câu 6.** Heap max là 1 GiB, Metaspace pool max là -1. Có nên lấy 1 GiB làm max của Metaspace không?

**Đáp án:** không. Đó là hai scope khác nhau; undefined max của Metaspace không thể tự thay bằng heap max.

**Câu 7.** JVM có heap used 500 MiB nhưng container RSS 1.1 GiB. Có “600 MiB leak” không?

**Đáp án:** chưa chứng minh. RSS gồm nhiều vùng native/stack/mappings/heap resident và accounting khác nhau. Đo non-heap, buffer pools, NMT nếu bật và OS/container memory trước khi kết luận.

**Câu 8.** Tại sao `getPeakUsage()` của pool vẫn cao sau khi current used giảm?

**Đáp án:** peak là high-water mark của JVM từ startup/reset; nó không được xóa khi GC giảm current usage. Đó là hai metrics khác nhau.

**Câu 9.** Có thể dùng `MemoryMXBean.gc()` mỗi 10 giây để có “after-GC usage chính xác” không?

**Đáp án:** không nên. Đây là thao tác yêu cầu GC, **không chỉ đọc**, có thể ảnh hưởng latency/throughput và làm méo hiện tượng. Dùng dữ liệu GC events/collection usage khi thích hợp.

**Câu 10.** Vì sao phải lưu tên GC/JDK khi so sánh memory pools giữa hai môi trường?

**Đáp án:** cấu trúc, tên pool, cách chia vùng, `max` và mức hỗ trợ collection/threshold có thể khác nhau. Một chart mapping theo tên cố định có thể tạo so sánh sai.

## 16. Checklist cuối bài

- Xác minh **đúng JVM, PID/start time, JDK/GC**.
- Đọc **`MemoryMXBean` cho heap và non-heap**, **`MemoryPoolMXBean` cho các pools**, và nêu scope của từng số.
- Giữ đơn vị **bytes** tại nguồn, đổi sang MiB/MB có nhãn rõ.
- Luôn hiểu `used <= committed`, và `committed <= max` **chỉ khi max xác định**; `init` không là giới hạn hiện hành.
- Xử lý `init/max == -1` và `getUsage()/getCollectionUsage() == null` theo đúng nghĩa **unknown/unavailable**.
- Phân biệt **current, peak, after-GC**; không dùng lẫn trên cùng chart.
- Không suy `heap + nonheap = RSS`, không cộng pool max và không kết luận leak từ một snapshot.
- Tính tỷ lệ chỉ khi có mẫu số dương, cùng scope và cùng instance.
- Khi nghi memory issue, đối chiếu **workload, GC, RSS, NMT, buffer pools** và các công cụ sâu hơn theo mục tiêu, có kiểm soát overhead.
- Giữ quyền truy cập an toàn nếu dùng JMX remote, không bật setter/forced GC trong một lượt thu thập chỉ đọc.

**Kết luận:** `used` là mức hiện dùng, `committed` là capacity đã bảo đảm cho JVM, `max` là giới hạn được công bố nếu có và `init` là giá trị khởi tạo nếu có. Muốn đo đúng phải hiểu **đơn vị, scope, thời điểm, loại pool và GC semantics**. MXBeans giúp tìm tín hiệu và xu hướng; kết luận về memory leak/OOM cần thêm chứng cứ về allocation, retention và resource limits.

### Tài liệu tham khảo chính thức

- [Java SE 21 — MemoryUsage](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryUsage.html): ý nghĩa bốn trường, sentinel -1, bất biến used/committed/max và constructor validation.
- [Java SE 21 — MemoryMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap/non-heap usage, notifications và phạm vi memory management.
- [Java SE 21 — MemoryPoolMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html): current/peak/collection usage, pool type/name, thresholds và support flags.
- [Java SE 21 — ManagementFactory](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html): lấy các platform MXBeans từ JVM.
- [Java SE 21 — BufferPoolMXBean](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): direct/mapped buffer pool statistics và sự khác biệt với MemoryPoolMXBean.
- [Oracle JDK 21 — jcmd](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): lệnh chẩn đoán VM/GC và điều kiện sử dụng trên JVM đích.
