# Dự phòng bộ nhớ ngoài heap thay vì dành toàn bộ giới hạn container cho Java heap

*Chủ đề: Java 10 — Bộ nhớ trong container. Bài Knowledge này giải thích vì sao **container memory limit khác với Java heap limit**; cách lập ngân sách cho heap, metaspace, JIT code cache, thread stacks, direct buffers, GC/JVM native allocations, JNI/mmap và phần dự phòng; cách đọc cgroup, chẩn đoán OOM, kiểm thử trên Java 17+ và lựa chọn JVM flags còn phù hợp trên JDK hiện hành.*

## 1. Vấn đề thực tế: đặt `-Xmx` bằng toàn bộ memory limit có an toàn không?

Một container Linux được đặt giới hạn bộ nhớ **1 GiB**. Người vận hành nghĩ rằng Java application “dùng bộ nhớ chủ yếu là heap”, nên đặt:

~~~bash
java -Xmx1g -jar app.jar
~~~

Đây là quyết định **rủi ro**. `-Xmx1g` chỉ giới hạn kích thước tối đa của **Java heap**, trong khi tiến trình Java và container còn có các loại bộ nhớ khác:

- **Metaspace/class metadata** được HotSpot cấp từ bộ nhớ native.
- **JIT compiled code cache** và dữ liệu của compiler.
- **Thread stacks** và cấu trúc native của mỗi platform thread.
- **Direct ByteBuffer / NIO** thường sử dụng native allocations ngoài Java heap.
- **GC bookkeeping, remembered sets, native arenas, runtime structures**.
- **JNI/JVMTI/native libraries**, những allocator không nhất thiết nằm trong phạm vi tracking của HotSpot.
- **Memory-mapped files, file cache, TLS/compression/network buffers** tùy ứng dụng.
- **Process khác trong cùng memory cgroup**, sidecar hoặc phần overhead tính vào giới hạn nếu có.

Vì thế, khi heap gần `1 GiB`, chỉ cần thêm bộ nhớ native hoặc các trang cgroup đang tính phí là có thể vượt giới hạn container. Hệ điều hành có thể **OOM-kill** tiến trình ngay cả khi bản thân Java chưa ném `OutOfMemoryError: Java heap space`.

**Nguyên tắc:** 

~~~text
Memory limit của container
    >= resident/charged memory của tất cả thành phần liên quan
    = heap resident + native/other resident + file/cache charges + ...
      (theo cách accounting của cgroup, không phải phép cộng mọi VM reservation)
~~~

Nên xem `-Xmx` là **một phần của ngân sách**, không phải toàn bộ ngân sách. Dự phòng được quyết định từ **đo đạc ở peak workload** và các giới hạn cần chịu được khi GC, JIT, mở kết nối hoặc tăng lượng thread.

### 1.1. “Dự phòng” không đồng nghĩa luôn cần giữ 50% heap trống

Không có một tỷ lệ “luôn chừa 20%, 25%, 30%” phù hợp mọi ứng dụng. Một dịch vụ có hàng trăm platform threads và native libraries có nhu cầu khác một dịch vụ hầu như chỉ dùng heap. Hãy chọn phần dự phòng dựa trên:

- Peak heap **committed/resident** và `-Xmx`.
- Metaspace/code cache thực đo.
- Số platform threads và nhu cầu stack.
- Direct buffer/Netty/native memory usage.
- GC/allocator overhead và memory fragmentation.
- Số lượng tiến trình/sidecar trong cgroup, file page cache.
- Độ dao động peak, warmup, tải đột biến và yêu cầu availability.

Một **bài tính ngân sách minh họa** có ích, nhưng không thể thay số liệu runtime.

## 2. Hai lớp giới hạn khác nhau: cgroup và HotSpot

### 2.1. Giới hạn container

Trong Linux cgroup v2:

~~~text
/sys/fs/cgroup/memory.max
~~~

chứa giới hạn hard memory của cgroup; có thể là một số byte hoặc `max` nếu không đặt giới hạn tại cấp đó. File:

~~~text
/sys/fs/cgroup/memory.current
~~~

báo lượng memory đang được charge cho cgroup và các nhánh con có liên quan. Các số này là **cgroup-level**, có thể bao gồm nhiều process và page cache, không phải một trường chỉ mô tả Java heap.

Nếu cgroup đạt `memory.max` và reclaim không đủ, **kernel OOM killer** có thể chọn kill process trong nhóm, tùy cấu hình và trạng thái hệ thống.

### 2.2. Giới hạn heap của JVM

~~~bash
java -Xmx512m -jar app.jar
~~~

đặt kích thước heap tối đa khoảng 512 MiB trong HotSpot. Nó **không** cấm JVM cấp thêm native memory ngoài heap; không tự đặt `MaxDirectMemorySize=0`, `MaxMetaspaceSize=0` và cũng không giới hạn tất cả thread stacks.

Tương tự:

~~~bash
java -XX:MaxRAMPercentage=50 -jar app.jar
~~~

hướng HotSpot chọn heap limit theo **một tỷ lệ** trên memory mà JVM cho là khả dụng để tính heap, với các heuristic và ràng buộc VM. Khi container detection hoạt động, con số cơ sở thường có xét tới hard memory limit. Đây là **heap sizing**, không phải tuyên bố tổng RSS JVM luôn ≤50% limit.

### 2.3. Container awareness trên JVM hiện hành

Từ JDK 10, HotSpot có hỗ trợ đọc resource constraints của **Linux containers**, được điều khiển bởi `-XX:+UseContainerSupport` trên nền tảng tương ứng. Trên JDK 17/21/25 phổ biến, cơ chế này vẫn còn quan trọng; dữ liệu cgroup v1/v2 và runtime image/JDK build quyết định kết quả nhận diện.

Lưu ý:

- `UseContainerSupport` là cờ **Linux-specific** trong HotSpot; không dùng kết quả thử nghiệm JVM Windows làm bằng chứng đọc cgroup.
- Không có `memory.max` hữu hạn thì JVM có thể chọn heap dựa trên memory lớn hơn điều bạn mong muốn.
- `-XX:MaxRAM=...` có thể ép giá trị cơ sở để tính heap, nhưng **không thiết lập hard cgroup limit cho Linux**.
- `-Xmx` đặt cụ thể heap max và thường **ưu tiên hơn** giá trị được tính từ `MaxRAMPercentage`.
- Một số JVM khác HotSpot và các phiên bản đã backport có cách phát hiện container khác; cần xác minh trên chính runtime deploy.

## 3. Bản đồ bộ nhớ: heap, non-heap và native không đồng nhất

| Vùng | Ví dụ nội dung | Có nằm dưới `-Xmx`? | Cách quan sát tiêu biểu |
| --- | --- | --- | --- |
| Java heap | Instance, array, object graph, GC-managed objects | **Có** | `MemoryMXBean.getHeapMemoryUsage`, GC logs, `jcmd GC.heap_info` |
| Metaspace | Metadata class, method, classloader | **Không** | `MemoryPoolMXBean`, `jcmd VM.metaspace`, NMT `Class` |
| Compressed Class Space | Không gian metadata cho class pointers ở cấu hình tương ứng | **Không** | NMT `Class`; phân biệt reserved/committed |
| JIT Code Cache | Compiled machine code và hạ tầng code | **Không** | Code cache memory pools, NMT `Code` |
| Platform thread stacks | Call frames và stack của thread gắn OS | **Không** | NMT `Thread`, thread count, OS maps |
| Direct NIO buffers | `ByteBuffer.allocateDirect` | **Không** | `BufferPoolMXBean` tên `direct`, một phần NMT |
| Memory-mapped buffers/files | File-backed mappings | **Không** | `BufferPoolMXBean` `mapped`, OS/cgroup stats |
| GC native structures | Remembered sets, card tables, allocator bookkeeping | **Không hoàn toàn** | NMT `GC`, GC logs |
| Compiler/VM internal | Compiler threads, arenas, symbols, internal tables | **Không** | NMT `Compiler`, `Internal`, `Symbol` |
| JNI/native libraries | Native malloc/mmap, compression, DB drivers, TLS, ML runtime | **Không** | OS RSS/smaps, native profilers; NMT không bao phủ toàn bộ |
| File cache/shared mappings | Các trang file/cache bị tính vào cgroup | **Không** | `memory.stat`, `memory.current` |
| Sidecar/tiến trình khác | Agent, log collector, helper process cùng cgroup | **Không** | Kubernetes/container/cgroup metrics |

**Ba thuật ngữ dễ nhầm:**

1. `MemoryMXBean.getNonHeapMemoryUsage()` là một phép đo **những vùng non-heap mà Java Management API định nghĩa**, **không phải tổng tất cả native memory** của tiến trình.
2. **Off-heap** thường mô tả vùng memory mà GC không quản lý như Java heap, chẳng hạn direct buffers và native allocations.
3. **Native memory** là khái niệm rộng hơn: VM internals, thread stacks, C/C++ allocations, metadata, compiler, malloc/mmap. Không có một biến `NonHeapSize` bao quát chính xác tất cả thứ đó.

Nếu đồ thị heap luôn thấp nhưng container memory vẫn tăng, việc kiểm tra **chỉ heap** là thiếu dữ liệu.

## 4. Đặt ngân sách ví dụ cho container 1 GiB

Giả sử một ứng dụng được chạy trong cgroup có hard limit:

~~~text
L = 1 GiB = 1024 MiB
~~~

Một mô hình thăm dò ban đầu:

| Hạng mục cần tính | Hạn mức ngân sách minh họa |
| --- | ---: |
| Java heap cap `-Xmx` | 512 MiB |
| NIO direct-buffer limit | 128 MiB |
| Metaspace + JIT code + class metadata | 128 MiB |
| Platform thread stacks + GC + JNI/native khác | 128 MiB |
| Headroom cho biến động RSS, file cache, sidecar và peak | 128 MiB |
| **Tổng ngân sách** | **1024 MiB** |

**Đây là phép chia minh họa, không phải mặc định khuyến nghị 512/128/128/128/128 cho mọi ứng dụng.** Các con số giả định phải được thay bằng peak data thực tế. Một số lớp memory (ví dụ code cache và thread stacks) có phần **reserved** lớn nhưng **committed/resident** nhỏ hơn, nên không lấy tất cả số “reserved” trong công cụ rồi cộng trực tiếp như RSS. Ngược lại, JNI/native memory có thể chưa được NMT ghi nhận, vì vậy không thể dựa hoàn toàn vào NMT.

### 4.1. Công thức hoạch định thực dụng

Ở mức operational:

~~~text
L = memory limit mà cgroup thực sự thực thi

H = giới hạn Java heap tối đa (-Xmx)
N = peak native/other memory đã quan sát và dự báo tăng trưởng
F = memory/file cache/sidecar tính phí trong cùng giới hạn
S = phần dự phòng cho đỉnh tải + sai số đo + fragmentation

Phải hướng tới:
    H + N + F + S <= L

Nhưng:
    N, F, S phải được đo/ước lượng nhất quán,
    không chỉ lấy tổng "reserved" hoặc mọi counter chồng lấn.
~~~

Ở đây `H` là mức trần để tính tình huống xấu nhất, còn `N` và `F` cần là **các category không double-count** trên cùng hệ quy chiếu. Nếu đo `memory.current` để lấy tổng cgroup, **không cộng thêm heap RSS vào `memory.current` lần nữa** vì heap resident đã nằm bên trong tổng đó.

### 4.2. Vì sao cần headroom ngay cả khi mỗi vùng đã có limit?

Không phải mọi vùng native đều có hard cap đơn giản, và các peak có thể xuất hiện đồng thời: JIT hoạt động, class được load nhiều, buffers đang flush, GC tăng bookkeeping, connection pool mở rộng, threads tăng, file cache nóng. Một ứng dụng ở mức 95–99% memory limit bình thường rất dễ bị kill khi workload chuyển trạng thái.

Dự phòng có thể nhỏ hơn hoặc lớn hơn 128 MiB tùy tải và runtime, nhưng phải tồn tại một tiêu chí kiểm chứng **peak container charged memory nằm dưới limit với biên an toàn**.

## 5. `-Xmx`, `-Xms` và `MaxRAMPercentage`: dùng đúng

### 5.1. `-Xmx` giới hạn heap max

~~~bash
java -Xmx512m -jar app.jar
~~~

Nó không nói native memory được bao nhiêu. Nếu container limit là 512 MiB mà `-Xmx512m`, ngân sách non-heap gần bằng 0 trong tình huống heap được dùng hết, nên không an toàn.

### 5.2. `-Xms` là heap khởi tạo/commit, không phải native reserve

~~~bash
java -Xms128m -Xmx512m -jar app.jar
~~~

Heap ban đầu và tối đa là hai con số khác nhau. `Xms` càng lớn có thể khiến footprint lúc startup cao hơn; `Xmx` lớn thì JVM có thể **reserve** vùng địa chỉ heap lớn hơn. Các trang RAM thực sự resident phụ thuộc quá trình commit/touch và hệ điều hành.

Nếu dùng:

~~~text
-Xms512m -Xmx512m -XX:+AlwaysPreTouch
~~~

HotSpot có thể commit/touch lượng heap lớn ngay lúc khởi động, làm RSS và thời gian startup tăng. **Không** nghĩ rằng `Xmx` là lượng RAM process đã sử dụng tại mọi thời điểm, và cũng không nghĩ `Xms` luôn trùng RSS byte-for-byte.

### 5.3. `-XX:MaxRAMPercentage`

Ví dụ với container hard limit 1 GiB, nếu VM nhận diện đúng limit và bạn chọn:

~~~bash
java -XX:MaxRAMPercentage=50 -jar app.jar
~~~

heap max thường gần **512 MiB**, trước những ràng buộc/rounding cụ thể. Cách đặt theo tỷ lệ giúp heap tự thích nghi khi **triển khai lại JVM** ở môi trường có giới hạn memory khác, không có nghĩa mọi thread pool và JIT đã tự giãn tương ứng.

Theo tài liệu `java` JDK 25, giá trị mặc định `MaxRAMPercentage` của HotSpot là **25%**, với những ngoại lệ/heuristics cho heap nhỏ và các tình huống khác. Đừng giả định mặc định tự động dành đúng 75% cho native hoặc đó là tỷ lệ tối ưu: giá trị mặc định chỉ là **heap sizing ergonomics**.

### 5.4. `-Xmx` có ưu tiên so với tỷ lệ

Thử nghiệm với HotSpot JDK 24:

~~~bash
java -XX:MaxRAM=1g -XX:MaxRAMPercentage=50 \
     -XX:+PrintFlagsFinal -version
~~~

trả:

~~~text
MaxRAM = 1073741824
MaxRAMPercentage = 50.000000
MaxHeapSize = 536870912
~~~

Giá trị `536870912` là **512 MiB**.

Khi có thêm `-Xmx128m`:

~~~bash
java -XX:MaxRAM=1g -XX:MaxRAMPercentage=90 \
     -Xmx128m -XX:+PrintFlagsFinal -version
~~~

trả:

~~~text
MaxRAM = 1073741824
MaxRAMPercentage = 90.000000
MaxHeapSize = 134217728
~~~

`134217728` byte là **128 MiB**, vì explicit heap cap đã thắng kết quả tỷ lệ. Đây là **kiểm chứng sizing flag**, không phải thử nghiệm chạy trong cgroup 1 GiB: `MaxRAM=1g` dùng để cố định cơ sở tính heap trên máy kiểm thử, **không tạo kernel cgroup limit**.

### 5.5. Đừng chỉnh cả tỷ lệ và `-Xmx` rồi tưởng cả hai cùng giới hạn

Nếu chạy:

~~~bash
java -Xmx800m -XX:MaxRAMPercentage=50 -jar app.jar
~~~

thì không nên viết tài liệu vận hành rằng JVM heap chắc chắn bằng 50% container limit. `-Xmx` đã đặt rõ trần heap, và tỷ lệ không phải lớp bảo vệ độc lập.

**Quy ước triển khai:** chọn một cơ chế chính trong release configuration (fixed heap hoặc percentage), kiểm tra giá trị hiệu lực qua `PrintFlagsFinal` / `Runtime.maxMemory()` trong chính container.

## 6. Direct memory: một vùng ngoài heap có thể làm OOM dù heap còn trống

### 6.1. `ByteBuffer.allocateDirect`

~~~java
ByteBuffer direct = ByteBuffer.allocateDirect(8 * 1024 * 1024);
~~~

Vùng nội dung của direct buffer thường ở native memory ngoài Java heap. Đối tượng Java `ByteBuffer` mô tả buffer vẫn tồn tại trên heap (cùng những object hỗ trợ), nhưng **dữ liệu 8 MiB** không phải là 8 MiB Java heap array.

Direct buffers hữu ích cho I/O, networking, frameworks, native integration; nhưng cấp phát quá nhiều có thể làm native footprint tăng. Việc giữ tham chiếu lâu, pool không có giới hạn hoặc release không đúng có thể duy trì tài nguyên ngoài heap ngay cả khi heap metrics bình thường.

### 6.2. `-XX:MaxDirectMemorySize`

~~~bash
java -Xmx512m -XX:MaxDirectMemorySize=128m -jar app.jar
~~~

Cờ này giới hạn **một lớp cấp phát direct-buffer của `java.nio`**. Nó **không** giới hạn tổng native memory của JNI, metaspace, thread stacks, code cache và mọi allocator khác. Nếu không cấu hình, VM chọn giới hạn direct-buffer theo chính sách nội bộ của JDK; không nên coi một giá trị suy đoán là contract vĩnh viễn.

**Không dùng `MaxDirectMemorySize=128m` để kết luận “native memory tối đa 128 MiB”.** JNI/Netty/native malloc và các phần khác có thể không thuộc cùng cơ chế accounting.

### 6.3. Direct buffer có thể OOME trước khi cgroup OOM

Một chương trình xin 8 MiB direct memory với cờ:

~~~bash
java -Xmx128m -XX:MaxDirectMemorySize=4m DirectMemoryLimitDemo
~~~

có thể bị từ chối ở tầng cấp phát direct buffer dù heap còn đủ chỗ. Đây là khác biệt quan trọng giữa **Java-level resource limit** và **cgroup limit**.

Trong ứng dụng thật, **không nên bắt `OutOfMemoryError` rồi tiếp tục xử lý request như chưa xảy ra gì**. Ví dụ ở mục 11 bắt OOME chỉ để chứng minh giới hạn của demo; khi có memory exhaustion thực, cần ngừng/khôi phục theo chính sách rõ.

### 6.4. Theo dõi qua `BufferPoolMXBean`

~~~java
for (BufferPoolMXBean p :
        ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
    System.out.println(p.getName() + ": "
            + p.getCount() + ", "
            + p.getTotalCapacity() + ", "
            + p.getMemoryUsed());
}
~~~

Đây là đoạn code dùng trong một method, cần import `java.lang.management.BufferPoolMXBean` và `java.lang.management.ManagementFactory`.

- `getCount()`: ước lượng số buffers.
- `getTotalCapacity()`: ước lượng tổng dung lượng buffers trong pool.
- `getMemoryUsed()`: ước lượng memory VM dùng cho pool, **có thể khác totalCapacity** và có thể trả `-1` khi không có số đo.

Đừng cộng `getMemoryUsed()` một cách vô điều kiện vào RSS đã đo vì các con số có thể phản ánh cùng trang RAM theo cách khác nhau.

## 7. Metaspace và class metadata

Metaspace lưu thông tin về class, method và những cấu trúc class metadata do VM quản lý. Trong HotSpot hiện đại, class metadata **không nằm trong Java object heap**. Ứng dụng sử dụng dependency injection, bytecode generation, serialization frameworks, proxies hoặc nhiều classloaders có thể tiêu tốn nhiều metaspace.

Có thể giới hạn:

~~~bash
java -XX:MaxMetaspaceSize=192m -jar app.jar
~~~

Điều đó tạo **trần** cho metaspace theo HotSpot, nhưng nếu đặt quá thấp, class loading có thể gặp `OutOfMemoryError: Metaspace`. Không nên “cứ đặt thấp để tiết kiệm memory” khi chưa đo số class/classloader và peak.

### 7.1. `MetaspaceSize` không giống `MaxMetaspaceSize`

- `-XX:MetaspaceSize=...`: một **ngưỡng GC trigger** liên quan class metadata, không phải trần của mọi native memory.
- `-XX:MaxMetaspaceSize=...`: **maximum** cho metaspace theo HotSpot.

Sửa sai lầm phổ biến: chỉ đặt `MetaspaceSize=64m` **không** có nghĩa process sẽ không dùng quá 64 MiB metaspace.

### 7.2. Compressed class space và virtual reservation

Một JVM có thể **reserve** vùng địa chỉ ảo lớn cho compressed class space hoặc các cấu trúc class, nhưng chỉ một phần nhỏ đã **commit** và có trang resident. Vì vậy, khi NMT báo:

~~~text
Class (reserved=... , committed=...)
~~~

không được lấy con số reserved rất lớn rồi kết luận JVM đã chiếm từng ấy RAM vật lý. Đọc cả hai trường và so với RSS/cgroup.

### 7.3. Classloader leaks không phải lúc nào heap OOME xuất hiện đầu tiên

Nếu ứng dụng liên tục tạo classloaders mới, dynamic proxies hoặc bytecode-generated classes và giữ tham chiếu, metaspace có thể tăng dần. Heap metrics có thể không phản ánh ngay toàn bộ chi phí native.

Cách điều tra:

- `jcmd <pid> VM.metaspace`.
- NMT `Class` category theo thời gian.
- Class loading/unloading count và classloader graph.
- Đối chiếu sau deploy/hot reload; kiểm tra classloader được giải phóng đúng.

Không khắc phục classloader leak chỉ bằng tăng `-Xmx`, vì heap cap không trực tiếp khống chế metaspace.

## 8. JIT code cache, GC structures, VM internals

### 8.1. JIT compiled code cache

HotSpot compile method thường xuyên chạy sang machine code, lưu trong vùng code cache. Ngoài ra có code/metadata của runtime, stubs và compiler. Vùng này **không nằm dưới `-Xmx`**.

Flag có thể xuất hiện:

~~~text
-XX:ReservedCodeCacheSize=<size>
~~~

Tuy nhiên, con số `ReservedCodeCacheSize` là không gian dành cho code cache theo VM; không đồng nghĩa tất cả đã resident hoặc mọi native allocation của JIT đều nằm trong đó. Cố giảm quá thấp có thể hạn chế JIT compilation và làm throughput suy giảm.

Trong NMT, category `Code` và `Compiler` có thể giúp quan sát một phần chi phí này.

### 8.2. GC bookkeeping

Garbage collector phải duy trì một số cấu trúc quản lý vùng nhớ, mark bits, remembered sets, card tables, queues hoặc metadata khác. Các cấu trúc này có thể tăng theo heap size, tỷ lệ cấp phát, số region/thread và collector.

Nói `Xmx=512m` **không có nghĩa tất cả chi phí GC đều đã nằm trong 512 MiB**. Một số dữ liệu GC nằm ngoài heap và hiện dưới NMT `GC` hoặc các category khác.

Không áp dụng một công thức chung “GC native overhead = 5% heap” như quy tắc chính xác. G1, Parallel GC, ZGC và các phiên bản JDK có thiết kế khác nhau. Đo với **collector đang sử dụng**.

### 8.3. JNI/JVMTI/native libraries

Thư viện nén/giải nén, TLS, socket transport, machine learning, database native client, hardware libraries hoặc instrumentation agents có thể gọi `malloc`/`mmap` bên ngoài HotSpot memory tracking.

Đây là lý do NMT **không bao phủ mọi byte native** trong tiến trình. Các category NMT là góc nhìn của HotSpot, không thay cho `/proc/<pid>/smaps_rollup`, cgroup accounting và profiler native khi chẩn đoán.

## 9. Platform thread stacks và số lượng threads

Một Java platform thread thường có stack riêng gắn với OS thread. Heap cap không giới hạn trực tiếp số platform threads có thể tạo, và stack không thể coi là một Java object array bên trong heap.

Có thể điều chỉnh stack size với:

~~~bash
java -Xss1m -jar app.jar
~~~

Nhưng cần hiểu:

- `-Xss` kiểm soát vùng stack mỗi platform thread theo VM/platform, không phải tổng native memory của JVM.
- **1 MiB stack reservation × 500 threads = khoảng 500 MiB virtual address reservation** là phép tính thô; **không đồng nghĩa 500 MiB resident**. Trang nào được commit/touch mới ảnh hưởng footprint vật lý theo cơ chế OS.
- Số thread lớn tạo thêm native thread descriptors, stacks, scheduling và tài nguyên khác.
- Đặt stack quá nhỏ có thể làm `StackOverflowError` ở call depth phù hợp; đặt quá lớn có thể làm giới hạn native memory/khả năng tạo thread bị áp lực.
- `OutOfMemoryError: unable to create native thread` có thể do thiếu native memory, giới hạn PID/thread, OS hoặc quota khác, **không** chỉ do heap.

### 9.1. Virtual threads trên JDK 21+ không phải một OS stack riêng cho từng task

JDK 21 cung cấp virtual threads. Không được nhân `-Xss` với số **virtual threads** như thể mỗi virtual thread có một OS platform thread stack độc lập. Virtual threads dùng continuations và scheduling trên carrier/platform threads; chúng vẫn sử dụng heap và VM/runtime resources, không phải “miễn phí”.

Nếu một hệ thống chuyển từ hàng nghìn platform threads sang virtual threads, profile native thread stacks có thể thay đổi, nhưng heap/continuation state, library pinning và connection concurrency cần đánh giá riêng. Không giải quyết container memory bằng cách chỉ thay executor mà không quan sát peak thực.

## 10. Reserved, committed, RSS và cgroup charge: bốn số khác nhau

### 10.1. Reserved virtual memory

`Reserved`: vùng không gian địa chỉ ảo đã được giữ lại để VM có thể dùng. Một `Java Heap reserved=512 MiB` không tự nghĩa container đã bị charge đủ 512 MiB RAM.

### 10.2. Committed memory

`Committed`: vùng được VM/OS cam kết theo cơ chế memory management. Nhưng **committed memory của HotSpot không luôn bằng physical RSS** tại cùng thời điểm; có thể có trang chưa touch, trang shared, page reclamation hoặc accounting đặc biệt.

### 10.3. RSS (Resident Set Size)

RSS là số trang hiện resident trong RAM của một process theo OS metric, gồm private và shared mappings. **Cộng RSS của nhiều tiến trình có thể double-count shared pages.** Một số môi trường dùng PSS/USS để phân tích memory chia sẻ chính xác hơn.

### 10.4. Cgroup `memory.current`

`memory.current` thể hiện tổng memory đang được charge cho cgroup (và descendants theo hierarchy). Nó có thể bao gồm anonymous memory, page cache, kernel memory và nhiều thành phần khác, tùy cách cgroup accounting. Nó **không** phải `Runtime.maxMemory()` và cũng không phải một bản cộng đơn giản của NMT committed.

Ví dụ:

~~~text
Java heap max        = 512 MiB
Java heap committed  = 256 MiB
NMT Class reserved   = 1 GiB (ví dụ address space)
NMT Class committed  = 30 MiB
Process RSS          = 410 MiB
Cgroup memory.current= 470 MiB
Cgroup memory.max    = 1024 MiB
~~~

Đây là **số giả định để phân biệt chỉ số**, không phải log của một JVM cụ thể. Không cộng 1 GiB Class reserved vào RSS 410 MiB rồi nói container đã dùng 1,4 GiB. Một phần NMT committed đã được bao gồm trong RSS, còn `memory.current` có thể tính các khoản ngoài process RSS.

**Quy tắc khi tạo dashboard:** ghi rõ từng metric là JVM heap, JVM NMT, process RSS/PSS, cgroup current hay orchestrator working set; không gộp khác hệ đo mà không giải thích.

## 11. Ví dụ Java 17+ đầy đủ: heap cap, direct buffer và platform threads

Mục tiêu demo:

1. Xác minh `-Xmx128m` đặt trần heap cỡ 128 MiB.
2. Xác minh `MemoryMXBean` có non-heap usage nhưng không đại diện cho mọi native memory.
3. Cấp phát **8 MiB direct buffer** ở ngoài Java heap và đọc `BufferPoolMXBean`.
4. Chạy 3 platform threads ngắn hạn, chờ an toàn, shutdown rõ ràng.
5. Tránh hardcode số RSS/non-heap byte phụ thuộc JDK/OS.

### 11.1. File Java hoàn chỉnh

~~~java
// File: ContainerMemoryBudgetDemo.java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;

public final class ContainerMemoryBudgetDemo {
    private static final int MIB = 1024 * 1024;

    public static void main(String[] args) throws InterruptedException {
        long maxHeap = Runtime.getRuntime().maxMemory();
        MemoryMXBean memory = ManagementFactory.getMemoryMXBean();

        System.out.println("heap cap <= 128 MiB = "
                + (maxHeap <= 128L * MIB));
        System.out.println("heap cap >= 120 MiB = "
                + (maxHeap >= 120L * MIB));
        System.out.println("nonheap bean used > 0 = "
                + (memory.getNonHeapMemoryUsage().getUsed() > 0));

        ByteBuffer direct = ByteBuffer.allocateDirect(8 * MIB);
        direct.putInt(0, 0x1234ABCD);
        System.out.println("direct buffer = " + direct.isDirect());
        System.out.println("direct data retained = "
                + (direct.getInt(0) == 0x1234ABCD));

        BufferPoolMXBean directPool =
                ManagementFactory.getPlatformMXBeans(
                        BufferPoolMXBean.class).stream()
                        .filter(p -> "direct".equals(p.getName()))
                        .findFirst()
                        .orElseThrow();

        System.out.println("direct buffers observed >= 1 = "
                + (directPool.getCount() >= 1));
        System.out.println("direct capacity >= 8 MiB = "
                + (directPool.getTotalCapacity() >= 8L * MIB));

        CountDownLatch started = new CountDownLatch(3);
        CountDownLatch release = new CountDownLatch(1);
        List<Thread> workers = new ArrayList<>();

        try {
            for (int i = 0; i < 3; i++) {
                Thread worker = new Thread(() -> {
                    started.countDown();
                    try {
                        release.await();
                    } catch (InterruptedException ex) {
                        Thread.currentThread().interrupt();
                    }
                }, "memory-demo-" + i);
                workers.add(worker);
                worker.start();
            }

            started.await();
            System.out.println("platform workers alive = "
                    + workers.stream().allMatch(Thread::isAlive));
        } finally {
            release.countDown();
            for (Thread worker : workers) {
                worker.join();
            }
        }

        System.out.println("workers terminated = "
                + workers.stream().noneMatch(Thread::isAlive));
        System.out.println("buffer value still valid = "
                + (direct.getInt(0) == 0x1234ABCD));
    }
}
~~~

**Lưu ý:** Đây là chương trình demo ngắn, không dùng một container limit thật; nó đặt một số JVM flags để kiểm thử khả năng phân tách vùng bộ nhớ. Kết quả của `MemoryMXBean`/`BufferPoolMXBean` là snapshot của **runtime thử nghiệm**, không phải bộ đo tổng memory cgroup.

### 11.2. Biên dịch/chạy Java 17+

~~~bash
javac --release 17 ContainerMemoryBudgetDemo.java

java -Xms64m -Xmx128m \
     -XX:MaxDirectMemorySize=16m \
     -XX:NativeMemoryTracking=summary \
     ContainerMemoryBudgetDemo
~~~

Trên PowerShell:

~~~powershell
javac --release 17 ContainerMemoryBudgetDemo.java
java '-Xms64m' '-Xmx128m' '-XX:MaxDirectMemorySize=16m' '-XX:NativeMemoryTracking=summary' ContainerMemoryBudgetDemo
~~~

`-XX:NativeMemoryTracking=summary` bật tracking cho quy trình chẩn đoán thêm ở mục 13. **NMT mặc định tắt** và có overhead; không cần bật chỉ để chương trình Java chạy.

### 11.3. Stdout đã kiểm chứng trên HotSpot JDK 24

~~~text
heap cap <= 128 MiB = true
heap cap >= 120 MiB = true
nonheap bean used > 0 = true
direct buffer = true
direct data retained = true
direct buffers observed >= 1 = true
direct capacity >= 8 MiB = true
platform workers alive = true
workers terminated = true
buffer value still valid = true
~~~

Trong phép thử, giới hạn 128 MiB được áp đúng và một direct buffer 8 MiB có thể được cấp vì giới hạn direct-buffer được chọn là 16 MiB. Không có số byte RSS nào được hardcode, vì chúng thay đổi theo VM và OS.

### 11.4. Giải thích kết quả

- `heap cap <= 128 MiB = true`: ứng dụng nhận đúng heap cap cấu hình.
- `nonheap bean used > 0 = true`: VM có non-heap regions đang dùng; **không** phải tổng native RSS.
- `direct buffer = true`: `ByteBuffer` đang dùng một direct buffer.
- `direct data retained = true`: giá trị 32-bit trong vùng direct memory còn nguyên.
- `direct buffers observed >= 1` và `direct capacity >= 8 MiB`: Management API nhận diện vùng buffer phù hợp.
- `platform workers alive = true`: ba thread vẫn hoạt động/chờ lúc snapshot, vì vậy nguồn native stack/resource là vấn đề có thật.
- `workers terminated = true`: demo đóng các worker, không rò thread do quên join.
- `buffer value still valid = true`: buffer còn sống đến cuối; chỉ để minh họa scope, không phải khuyến nghị giữ mọi direct buffers vô hạn.

### 11.5. Không dùng demo để dự đoán RSS

Chạy `ByteBuffer.allocateDirect(8MiB)` không cho phép bạn kết luận “container.current tăng chính xác 8MiB”: alignment, allocator, page-touch, native memory overhead, file/cache accounting và JVM runtime state có thể khác. Muốn đo cgroup RSS hãy chạy **trong Linux container**, lấy memory.current trước/sau theo cùng điều kiện và dùng số liệu lặp.

## 12. Ví dụ thứ hai: direct-memory limit riêng, dù heap vẫn có thể cấp phát

### 12.1. File Java đầy đủ

~~~java
// File: DirectMemoryLimitDemo.java
import java.nio.ByteBuffer;

public final class DirectMemoryLimitDemo {
    public static void main(String[] args) {
        byte[] heap = new byte[1024 * 1024];
        heap[0] = 7;

        System.out.println("heap allocation succeeds = "
                + (heap[0] == 7));
        try {
            ByteBuffer.allocateDirect(8 * 1024 * 1024);
            System.out.println("direct allocation rejected = false");
        } catch (OutOfMemoryError directLimit) {
            System.out.println("direct allocation rejected = true");
        }
    }
}
~~~

**Cảnh báo:** `catch (OutOfMemoryError)` trong chương trình này chỉ là **thao tác minh họa**. Không copy cách tiếp tục sau OOME sang business logic production; trạng thái hệ thống có thể đã thiếu tài nguyên nghiêm trọng.

### 12.2. Biên dịch/chạy

~~~bash
javac --release 17 DirectMemoryLimitDemo.java

java -Xmx128m \
     -XX:MaxDirectMemorySize=4m \
     DirectMemoryLimitDemo
~~~

Stdout đã kiểm chứng với HotSpot JDK 24:

~~~text
heap allocation succeeds = true
direct allocation rejected = true
~~~

Ở thời điểm này, phép cấp phát heap nhỏ thành công trong khi phép cấp phát direct buffer 8 MiB vượt giới hạn direct 4 MiB. Như vậy **có nhiều giới hạn memory độc lập**, không phải chỉ một con số heap.

Không nhầm lỗi cấp phát direct bị giới hạn với **cgroup OOM kill**: ví dụ này không đặt `memory.max` của Linux, không chứng minh kernel đã kill tiến trình.

## 13. Native Memory Tracking (NMT): quan sát đúng và biết giới hạn của nó

HotSpot cung cấp **Native Memory Tracking**, thường gọi **NMT**, để giám sát các khoản memory thuộc các subsystems do HotSpot ghi nhận.

Bật khi khởi động:

~~~bash
java -XX:NativeMemoryTracking=summary -Xmx512m -jar app.jar
~~~

Hoặc khi cần chi tiết hơn:

~~~bash
java -XX:NativeMemoryTracking=detail -Xmx512m -jar app.jar
~~~

Sau đó dùng `jcmd` (từ JDK tương thích) trên tiến trình **đang chạy**:

~~~bash
jcmd <pid> VM.native_memory summary scale=MB
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff scale=MB
~~~

Đây là lệnh được **tài liệu JDK 25 hỗ trợ**, không phải stdout được tạo bằng các ví dụ demo của bài. `<pid>` phải thay bằng PID có thật, và công cụ attach cần quyền cùng runtime/container namespace phù hợp.

### 13.1. Category cần đọc

Các tên category có thể thay đổi/được bổ sung theo release, ví dụ:

| NMT category | Thông tin cần quan sát |
| --- | --- |
| `Java Heap` | Reserved/committed vùng heap |
| `Class` | Class metadata và compressed class space |
| `Thread` | Native thread structures, stack reservation/commit |
| `Code` | Code cache/JIT code |
| `GC` | GC native structures |
| `Compiler` | Compiler/JIT infrastructure |
| `Internal`, `Symbol`, `Arena Chunk` | Các khoản VM internal khác |
| `Native Memory Tracking` | Chính memory overhead của việc theo dõi |

Trong report:

~~~text
Total: reserved=... MB, committed=... MB
- Java Heap (reserved=... MB, committed=... MB)
- Class     (reserved=... MB, committed=... MB)
- Thread    (reserved=... MB, committed=... MB)
- Code      (reserved=... MB, committed=... MB)
- GC        (reserved=... MB, committed=... MB)
~~~

Đây là **minh họa cấu trúc log**, không phải output exact của một PID trong bài.

### 13.2. NMT không theo dõi tất cả native memory

Theo hướng dẫn Oracle JDK25, NMT **không** theo dõi mọi cấp phát của native third-party code và có các giới hạn với native memory của một số phần JDK libraries, CDS archive hoặc người dùng JNI. Vì vậy:

~~~text
NMT total committed != tổng RSS chắc chắn của process
NMT total reserved  != container memory.current
~~~

Nếu `memory.current` hoặc RSS tăng liên tục nhưng NMT category không tăng tương ứng, xem:

- JNI/native third-party allocators.
- Memory-mapped files/page cache.
- File descriptors/network stacks.
- Các vùng bị giới hạn tracking/OS accounting.
- Các process khác trong cùng cgroup.
- Fragmentation và behavior của native allocator.

### 13.3. Reserved và committed là hai cột riêng

Một NMT report có thể có Class `reserved` rất lớn do **compressed class space virtual reservation**, trong khi `committed` nhỏ. Đừng báo cáo “JVM dùng RAM vượt container limit” chỉ vì `NMT Total reserved` lớn hơn `memory.max`. Những con số này **không có cùng đơn vị ý nghĩa**.

### 13.4. NMT có overhead

Tài liệu Oracle nêu NMT có thể gây **5–10% overhead hiệu năng** và thêm memory tracking metadata. Không bật `detail` mãi trên production chỉ để có một dashboard đẹp. Nên dùng staging hoặc thời gian điều tra có kiểm soát; với production nếu cần `summary` thì phải đo overhead và có chính sách bật/tắt.

NMT phải bật **khi JVM khởi động**; `jcmd` có thể dừng tracking, nhưng không thể bắt đầu NMT từ một process vốn khởi động với NMT off.

## 14. Quan sát Linux cgroup v2 và process memory

### 14.1. Đọc memory limit và hiện trạng

Trong container dùng cgroup v2 với mount path tương ứng:

~~~bash
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.peak
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/memory.stat
~~~

Giải thích:

- `memory.max`: hard limit, có thể là `max`.
- `memory.current`: charged memory hiện tại.
- `memory.peak`: peak charged memory trong khoảng mà kernel cung cấp.
- `memory.events`: các event pressure/limit/oom; xem `oom` và `oom_kill` khi có.
- `memory.stat`: phân rã một số loại charged memory, gồm anonymous/file/kernel categories theo kernel.

File paths này đúng với hierarchy cgroup v2 **khi các controller được mount theo vị trí đó**. Không giả định mọi Linux host/container đều có cùng mount path, đặc biệt trong cgroup v1/hybrid setup hoặc khi chạy trong Kubernetes namespace có cấu trúc khác.

### 14.2. Tại sao `memory.current` khác `RSS`?

Cgroup memory accounting bao gồm các khoản được charge cho cgroup và descendants, không phải chỉ trang private của một process. Một sidecar chạy trong cùng cgroup có thể làm `memory.current` tăng dù Java process RSS không đổi.

Vì vậy, muốn kết luận memory pressure của **pod**, cần biết cách pod/container groups được tổ chức trong orchestrator, xem đúng cấp cgroup và không ngầm gộp các con số từ khác scope.

### 14.3. Process-level trên Linux

~~~bash
cat /proc/<pid>/status
cat /proc/<pid>/smaps_rollup
~~~

`VmRSS` và các thông tin `Rss/Pss/Private_*` giúp soi những mappings resident. Lệnh đúng quyền truy cập có thể đọc:

~~~bash
ps -o pid,rss,vsz,nlwp,cmd -p <pid>
~~~

- `rss` là resident size theo công cụ/OS.
- `vsz` là virtual address size, thường cao do reservations; không so trực tiếp với cgroup hard limit.
- `nlwp` là số OS threads của process tại thời điểm đo, không đồng nhất với Java virtual thread count.

Đừng lấy `vsz > memory.max` làm bằng chứng OOM. Có JVM reserve các không gian virtual lớn nhưng chỉ commit/touch một phần.

### 14.4. Java/JDK logs có liên quan

~~~bash
java -Xlog:os+container=debug -jar app.jar
java -Xlog:gc*=info -jar app.jar
java -XX:+PrintFlagsFinal -version
~~~

`-Xlog:os+container` giúp hiểu container detection ở HotSpot Linux; `gc*` giúp biết collector/heap behavior; `PrintFlagsFinal` cho thấy `MaxHeapSize`, `MaxRAMPercentage`, `MaxMetaspaceSize` và các flag có origin do command line/ergonomics.

Log CPU/memory limit không phải lời bảo đảm container capacity: cần đối chiếu OS cgroup và runtime thực tế.

## 15. Khi container bị OOM: hai tình huống rất khác nhau

### 15.1. Java `OutOfMemoryError`

Ví dụ thông báo:

~~~text
java.lang.OutOfMemoryError: Java heap space
java.lang.OutOfMemoryError: Metaspace
java.lang.OutOfMemoryError: Direct buffer memory
java.lang.OutOfMemoryError: unable to create native thread
~~~

Thông báo phụ thuộc VM/đường code và không nhất thiết có đúng cụm chữ trên mọi JDK. Điểm chung: **JVM đã tạo lỗi cấp phát tại mức Java**. Nguyên nhân cần phân tích tương ứng:

- Heap: object retention, allocation peaks, live set quá lớn so với `Xmx`.
- Metaspace: số class/classloader, dynamic proxies, metadata growth, MaxMetaspaceSize.
- Direct: direct buffer usage/pool/caps, retention, NIO framework.
- Native thread: OS thread limit, stack reserve, memory, resource quotas.

Trong số tình huống, JVM có thể ném lỗi rồi tiếp tục; nhưng không nên dựa vào khả năng recovery từ resource exhaustion như một chiến lược vận hành bình thường.

### 15.2. Linux kernel/container OOM kill

Khi memory cgroup đạt giới hạn và reclaim thất bại, kernel có thể kill process. Ứng dụng Java có thể **không kịp ném hoặc ghi log OutOfMemoryError**. Kubernetes thường hiển thị container termination reason `OOMKilled` trong những trường hợp tương ứng.

Các dấu hiệu nên xem:

~~~bash
cat /sys/fs/cgroup/memory.events
kubectl describe pod <pod>
kubectl get pod <pod> -o json
~~~

Các lệnh `kubectl` cần kubecontext/permission; `<pod>` là placeholder tên pod, **không chạy nguyên văn**. Trong `memory.events`, trường `oom_kill` tăng là bằng chứng có process trong cgroup bị OOM killer kill; cần đối chiếu với scope/cấp cgroup và thời gian.

Một exit code kiểu `137` có thể xuất hiện khi process bị `SIGKILL`, nhưng **không dùng 137 một mình như chứng nhận 100% là OOM**: SIGKILL có nhiều nguyên nhân. Dùng reason của runtime/kube, kernel events và time correlation.

### 15.3. Vì sao tăng `-Xmx` có thể làm OOMKilled nặng hơn?

Nếu container limit cố định và RSS đã sát trần, tăng `Xmx` cho phép heap dùng nhiều hơn, **thu hẹp headroom native và page cache**. Dịch vụ có thể không còn `Java heap space` sớm, nhưng lại bị kernel kill cả process.

Ngược lại, hạ `Xmx` quá thấp có thể làm nhiều GC, tăng pause và ném heap OOME. Sizing phải cân đối **live heap**, native memory và container pressure, không giải quyết bằng một phía duy nhất.

## 16. Thiết kế Kubernetes memory limit có chủ đích

Ví dụ YAML minh họa container memory limit 1 GiB và JVM heap 512 MiB:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: memory-budget-demo
spec:
  replicas: 2
  selector:
    matchLabels:
      app: memory-budget-demo
  template:
    metadata:
      labels:
        app: memory-budget-demo
    spec:
      containers:
        - name: app
          image: example/memory-budget-demo:1.0
          resources:
            requests:
              memory: "768Mi"
            limits:
              memory: "1Gi"
          env:
            - name: JAVA_TOOL_OPTIONS
              value: "-Xmx512m -XX:MaxDirectMemorySize=128m"
~~~

**Đây là ví dụ cấu hình**, không có bảo đảm image trong `example/...` tồn tại; thay bằng artifact thật có provenance và policy của dự án.

Ý nghĩa:

- Kubernetes `limits.memory: 1Gi` tạo hard limit tương ứng theo container/runtime.
- `requests.memory: 768Mi` tham gia scheduling/đảm bảo tài nguyên, **không phải thay thế hard limit**.
- `-Xmx512m` giới hạn heap khoảng 512 MiB.
- `-XX:MaxDirectMemorySize=128m` giới hạn đường cấp phát `java.nio` direct buffers tương ứng, **không giới hạn tổng native memory**.
- Phần còn lại phải đủ cho metaspace, code, threads, GC, JNI, file cache và headroom qua đo đạc.

**Không coi 1Gi - 512Mi = 512Mi là phần native chắc chắn tự được bảo vệ.** Nếu application dùng JNI native allocations không giới hạn, phần đó có thể tăng vượt budget. Một CPU/memory spike vẫn có thể dẫn tới OOMKilled.

### 16.1. Percentage-based alternative

Trong môi trường muốn heap thay đổi theo hard memory limit:

~~~yaml
env:
  - name: JAVA_TOOL_OPTIONS
    value: "-XX:MaxRAMPercentage=50 -XX:MaxDirectMemorySize=128m"
~~~

Dùng cách này khi HotSpot container detection đã được xác minh trong chính deployment. Nếu JDK không đọc đúng cgroup hoặc memory.max=`max`, tỷ lệ có thể tính theo memory host lớn hơn kỳ vọng. Tránh đồng thời đặt `-Xmx` rồi giả định `MaxRAMPercentage` vẫn kiểm soát kết quả.

### 16.2. Pod chứa sidecar

Một pod có ứng dụng Java, sidecar proxy và log agent cần có **memory budgets riêng** phù hợp cách runtime giới hạn từng container và scope metrics. Không mặc nhiên suy pod memory = Java heap + Java native duy nhất. Theo dõi từng container và nếu dùng metrics cấp pod, tránh nhầm tổng với giới hạn của một container.

### 16.3. Hạn mức nhỏ

Ở container chỉ có 128–256 MiB, overhead JVM và native là tỷ lệ đáng kể. Các heuristic `MinRAMPercentage`/heap nhỏ và runtime capabilities có thể làm trần heap khác phép nhân ngây thơ. **Luôn đo `Runtime.maxMemory()` và startup RSS**. Nếu runtime không thể khởi động với headroom đủ, cần tăng limit hoặc giảm footprint bằng giải pháp có chứng cứ, không cố ép toàn bộ container vào `-Xmx`.

## 17. Giảm bộ nhớ ngoài heap bằng biện pháp nào?

### 17.1. Giảm số platform threads không cần thiết

Nếu số thread tăng bất thường, xem executor lifecycle, giới hạn queue, connection pool và HTTP framework. Điều chỉnh bằng concurrency caps/backpressure phù hợp trước khi chỉnh `-Xss`. Việc hạ `-Xss` có thể giảm reservation per thread nhưng phải test call depth và native stack behavior.

### 17.2. Giới hạn direct-buffer pools theo workload

Đo `BufferPoolMXBean`, network framework buffer allocators, pooling/retention. Khi có ích, dùng `-XX:MaxDirectMemorySize` như một guardrail và cấu hình pool limit riêng, tránh giữ buffer vô hạn. Đừng đưa một direct limit quá thấp khiến ứng dụng networking gặp direct OOME khi tải tăng.

### 17.3. Kiểm tra classloader lifetime

Classloaders giữ lại lâu có thể kéo metadata sống lâu. Các hệ thống deploy/reload nhiều lần cần kiểm tra class unload, proxy generation và metaspace. Một `MaxMetaspaceSize` vừa phải có thể bắt lỗi sớm, nhưng không thay sửa leak.

### 17.4. Chọn JVM/GC và heap sizing phù hợp

GC overhead có thể khác giữa collectors. Việc chọn GC nên dựa trên latency/throughput/heap size và workload, không chỉ nhằm cắt một category NMT. Các lựa chọn có thể ảnh hưởng số threads và native overhead, vì vậy mọi thay đổi GC cần benchmark.

### 17.5. JNI/native allocator diagnosis

Nếu OS RSS tăng nhưng NMT không tăng, dùng native profiling, `smaps_rollup` và tài liệu native library. Tránh liên tục tăng `-Xmx` — việc tăng heap không sửa cấp phát native do thư viện C/C++ không giải phóng.

### 17.6. Mapped file/page cache

Nếu workload dùng `MappedByteBuffer`, memory-mapped indexes hoặc file I/O nặng, hãy xem file/cache charges. Nhiều trang có thể reclaim được nhưng cgroup vẫn chịu pressure; cần đo `memory.stat` và resident pages thay vì quy mọi tăng trưởng vào heap leak.

## 18. Quy trình xác định ngân sách dựa trên số liệu

Một quy trình an toàn theo các bước:

1. **Chốt hard limit**: đọc `memory.max` từ container thật và manifest orchestration.
2. **Chốt hiệu lực JVM heap**: in `Runtime.maxMemory()`, `Xmx`, `MaxRAMPercentage`, NMT nếu đã bật.
3. **Đo ở steady state**: service sau warmup, kết nối DB/HTTP và cache chính đã sẵn sàng.
4. **Đo ở peak workload**: concurrency, traffic pattern, batch size, file upload, response payload, warm caches.
5. **Ghi cgroup peak/oom**: `memory.current`, `memory.peak`, `memory.events`, `memory.stat`.
6. **Ghi process resident/threads**: RSS/PSS và số platform threads, native allocations quan trọng.
7. **Ghi heap/GC**: live set, allocation rate, peak committed heap, pause/throughput.
8. **Ghi direct/metaspace/code**: BufferPoolMXBean, MemoryPoolMXBean, NMT categories và growth.
9. **Kiểm tra external native**: JNI/agents/mmap nếu NMT không giải thích được RSS.
10. **Tính headroom có xét biến động**: tránh đặt `Xmx` sát memory.max.
11. **Thử nghiệm nhiều mức heap/limit**: giữ workload, GC và resource limits tương đương.
12. **Chọn SLO/guardrail**: container usage peak, OOMKill count, heap OOM, p99 latency, GC overhead.
13. **Đóng băng cấu hình có thể rollback**: JDK build, flags, limit, image và profile tải.
14. **Giám sát sau deploy**: nếu growth thay đổi, điều tra trước khi tăng memory.

### 18.1. Một bảng ghi số liệu đề xuất

| Metric | Đơn vị/nguồn | Ý nghĩa |
| --- | --- | --- |
| `memory.max` | byte, cgroup | Hard limit |
| `memory.current` | byte, cgroup | Current charged memory |
| `memory.peak` | byte, cgroup | Peak charged memory |
| `memory.events oom_kill` | count, cgroup | Kernel OOM kill evidence |
| Java heap used/committed/max | byte, JVM | Đối tượng Java/heap |
| Metaspace used/committed | byte, JVM/JFR/NMT | Class metadata |
| Code Cache used | byte, JVM pool/NMT | JIT code |
| Direct buffer count/capacity/used | count/byte, BufferPoolMXBean | NIO direct allocations |
| Platform thread count | count, JVM/OS | Một nguồn stack/native overhead |
| NMT summary/diff | byte, HotSpot | Các vùng nội bộ HotSpot |
| Process RSS/PSS | byte, OS | Resident memory |
| GC pause/allocation rate | ms, bytes/s | Tradeoff heap sizing |
| Request p95/p99/errors | ms/count, app metrics | Kết quả người dùng trải nghiệm |

Một phép đo “nonheap used” tăng không tự kết luận classloader leak. Có thể do codecache warmup, class initialization, thread growth hoặc native libraries. **Phân loại nguồn trước khi sửa.**

## 19. Các lỗi nhận thức dễ gây sự cố

| Ngộ nhận | Cách hiểu đúng |
| --- | --- |
| “Container limit 1Gi thì đặt `-Xmx1g` là dùng đúng tài nguyên.” | Native/off-heap/file/cache cũng cần memory. |
| “Mọi byte không phải heap đều được `MemoryMXBean.nonHeap` đo.” | MXBean chỉ thấy các memory pools được quản lý, không phải toàn bộ native. |
| “`MaxRAMPercentage=100` giới hạn tổng tiến trình ở 100% RAM.” | Chỉ liên quan heap sizing, rất dễ không còn headroom. |
| “Default MaxRAMPercentage 25% nghĩa là 75% còn lại chắc chắn miễn phí.” | 75% là khoảng không dành cho heap theo heuristic, native có thể dùng nhiều/ít hơn. |
| “`Xmx` là lượng RSS luôn đang dùng.” | Là heap maximum; reserved/committed/resident khác nhau. |
| “`-Xms` và `-Xmx` luôn tạo cùng resident bytes.” | Startup heap commit/touch và OS behavior phụ thuộc flags. |
| “`MaxDirectMemorySize` giới hạn toàn bộ native memory.” | Chỉ bảo vệ đường cấp phát direct NIO có liên quan. |
| “Direct ByteBuffer không tạo object trên heap.” | Buffer object Java vẫn nằm trên heap; vùng dữ liệu direct là native. |
| “NMT Total reserved là RSS.” | Reserved address space không đồng nghĩa RAM resident. |
| “NMT thấy hết JNI/native malloc.” | Không; NMT có giới hạn và không thay OS/native profilers. |
| “Bỏ qua `BufferPoolMXBean` khi heap đồ thị thấp.” | Direct NIO có thể tăng dù heap nhỏ. |
| “`MaxMetaspaceSize` là metadata của object heap.” | Metaspace là vùng native class metadata. |
| “`MetaspaceSize` là hard cap cho metaspace.” | Là một GC threshold; dùng `MaxMetaspaceSize` để đặt max. |
| “Code cache nằm hoàn toàn trong heap.” | JIT code cache là ngoài Java object heap. |
| “`-Xss1m` × 500 threads = chắc chắn 500MiB RSS.” | Là ước lượng virtual stack reservation, không phải mọi trang resident. |
| “Một virtual thread luôn có 1MiB OS stack.” | Virtual threads không 1–1 với OS threads. |
| “Một ứng dụng heap còn trống thì không bao giờ OOMKilled.” | cgroup tổng có thể vượt limit từ vùng khác. |
| “Exit 137 luôn có nghĩa là OOMKilled.” | Có nhiều nguyên nhân SIGKILL; cần runtime/kernel evidence. |
| “Tăng `Xmx` luôn chữa memory errors.” | Có thể làm cgroup OOM-kill nhanh hơn nếu native thiếu headroom. |
| “`MaxRAM=1g` tạo hard limit 1GiB cho container.” | Chỉ thay cơ sở tính heap của HotSpot, không thay cgroup. |
| “`memory.current` = Java heap used.” | Là charged memory cấp cgroup, có thể gồm file cache/other processes. |
| “`memory.max` bất kỳ cũng có nghĩa VM tự nhận diện đúng.” | Phụ thuộc JDK, cgroup mount/controller, runtime flags. |
| “Đọc mỗi `-Xmx` đủ để tính chi phí pod.” | Cần heap + native + cgroup/sidecar metrics và headroom. |
| “Giảm native cap thật thấp luôn tốt.” | Có thể gây OOME direct/metaspace hoặc giảm throughput. |
| “Không có Java OOME log thì không phải memory issue.” | Kernel OOM kill có thể xảy ra trước Java exception. |

## 20. Bài tập thực hành và đáp án

### Bài 1 — Tính headroom

**Đề:** Container 1024 MiB, `Xmx=768 MiB`. Dưới góc nhìn trần heap, còn bao nhiêu MiB cho tất cả thành phần khác?

**Đáp án:** 1024 − 768 = **256 MiB** trước khi tính native overhead, file cache và các charge khác. Đây là khoảng ngân sách, không bảo đảm 256 MiB là đủ.

### Bài 2 — Heap bằng container limit

**Đề:** `memory.max=512MiB` và `-Xmx512m`. Vì sao nguy hiểm?

**Đáp án:** Không có headroom được dự trù cho metaspace, code cache, thread stacks, direct buffers, GC native, JIT/JNI và các charge khác khi heap lên tới max.

### Bài 3 — Phân biệt default MaxRAMPercentage

**Đề:** JDK25 HotSpot có mặc định `MaxRAMPercentage=25`. Điều này có nghĩa JVM không thể vượt 25% container memory?

**Đáp án:** Không. 25% là heuristic heap maximum mặc định trong những tình huống tương ứng; tổng JVM native + heap vẫn có thể vượt tỷ lệ đó.

### Bài 4 — Cấu hình cả tỷ lệ và Xmx

**Đề:** Chạy `-XX:MaxRAM=1g -XX:MaxRAMPercentage=90 -Xmx128m`. Heap max được thử nghiệm là bao nhiêu?

**Đáp án:** **128 MiB** (134217728 byte). `Xmx` tường minh ưu tiên hơn heap max tính từ 90% của 1 GiB.

### Bài 5 — Direct buffer bị chặn trước heap

**Đề:** JVM chạy `-Xmx128m -XX:MaxDirectMemorySize=4m`. Allocate direct 8MiB có thể thất bại dù 1MiB heap array vẫn cấp phát được?

**Đáp án:** Có. Trong demo đã kiểm thử, heap array 1MiB thành công còn direct 8MiB bị từ chối, vì giới hạn khác nhau.

### Bài 6 — Metaspace leak

**Đề:** Heap occupancy ổn định nhưng `Class` category NMT tăng sau mỗi lần dynamic class loading. Hướng điều tra?

**Đáp án:** Classloader lifetime, class unloading, generated proxies/classes và cấu hình metaspace. Đừng chỉ tăng `-Xmx`.

### Bài 7 — Threads

**Đề:** Có 500 platform threads với `-Xss1m`. Có được ghi RSS threads là đúng 500MiB không?

**Đáp án:** Không. `Xss` mô tả stack size/reservation theo nền tảng; resident phụ thuộc phần stack thực sự commit/touch và native structures.

### Bài 8 — Virtual threads

**Đề:** 100.000 virtual threads có nghĩa JVM đã reserve 100.000 × `Xss` OS stacks?

**Đáp án:** Không. Virtual threads dùng mô hình scheduler/continuations khác. Cần đo heap, carrier threads và tài nguyên mà các tasks thực sự dùng.

### Bài 9 — RSS và committed

**Đề:** NMT báo Class reserved=1GiB, committed=30MiB. Có phải class metadata đã chiếm 1GiB RAM vật lý?

**Đáp án:** Không. Reserved là không gian địa chỉ; committed/resident mới liên quan gần hơn đến memory tiêu thụ, và vẫn phải so với OS/cgroup.

### Bài 10 — NMT coverage

**Đề:** RSS tiếp tục tăng nhưng NMT gần như không đổi. Có thể loại trừ native memory leak không?

**Đáp án:** Không. Third-party JNI/native malloc, mmap/file mappings và các vùng NMT không theo dõi có thể là nguyên nhân.

### Bài 11 — Container OOMKilled

**Đề:** Kubernetes báo `OOMKilled`, log không có `java.lang.OutOfMemoryError`. Điều đó có vô lý không?

**Đáp án:** Không. Kernel có thể kill JVM khi cgroup vượt hard limit; Java không nhất thiết có cơ hội tạo/log exception.

### Bài 12 — Cgroup current

**Đề:** `memory.current=800MiB` và Java heap used=400MiB. Có thể kết luận toàn bộ 400MiB còn lại là metaspace không?

**Đáp án:** Không. Có thể gồm direct, code, thread, JNI, file cache, GC native, process khác và OS charges.

### Bài 13 — Sidecar

**Đề:** Pod có Java container và sidecar. Vì sao đo tổng pod memory không bằng Java heap + nonheap?

**Đáp án:** Pod metrics có thể gồm sidecar/OS charges và phạm vi accounting khác, trong khi Java Management APIs chỉ theo dõi một số vùng của JVM.

### Bài 14 — Quota nhỏ

**Đề:** JVM nhận container limit 256MiB nhưng chương trình tính heap 200MiB. Cần kiểm tra gì trước production?

**Đáp án:** Startup RSS, metaspace/code/thread/native peaks, direct buffer usage, GC, memory.current/peak/events và load test. 56MiB headroom có thể không đủ.

### Bài 15 — Dữ liệu phản ánh memory leak

**Đề:** `-Xmx` không đổi, NMT Thread category và OS thread count cùng tăng liên tục. Gợi ý?

**Đáp án:** Có thể có thread leak/unbounded executor, cần xem thread dumps, pool lifecycle và native stacks. Không kết luận chỉ từ một sample.

### Bài 16 — Default NIO cap

**Đề:** Không đặt `MaxDirectMemorySize`. Có được khẳng định max direct luôn đúng bằng `Xmx` trên mọi Java version không?

**Đáp án:** Không nên. VM có chính sách nội bộ, điều kiện khác nhau; kiểm tra runtime thực và đặt explicit limit nếu sản phẩm cần guardrail.

### Bài 17 — NMT tracking overhead

**Đề:** Có nên bật NMT `detail` trên mọi production JVM vô thời hạn để xem mọi native allocation?

**Đáp án:** Không mặc định. NMT có overhead, không bao phủ mọi native code. Bật có chủ đích và đối chiếu với OS metrics/native profiler.

### Bài 18 — File cache

**Đề:** Container memory.current tăng khi đọc nhiều file mmap nhưng Java heap used ổn định. Có phải Java heap leak không?

**Đáp án:** Chưa có bằng chứng. Xem memory.stat file cache/mmap, process RSS/PSS và buffer pools để xác định nguồn charge.

### Bài 19 — Chọn mức Xmx

**Đề:** Tải peak có non-heap/native khoảng 350MiB, file/cache/headroom cần thêm 150MiB, container limit 1024MiB. Mức Xmx tối đa theo phép ngân sách đơn giản?

**Đáp án:** 1024 − 350 − 150 = **524MiB**. Đây là kết quả trên **giả định N/F/S đã đo không trùng nhau**; chọn mức thực tế còn phụ thuộc heap live set và safety margin. Không nhất thiết đặt 524MiB chính xác nếu cần dự phòng khác.

### Bài 20 — Giữ cấu hình sau nâng JDK

**Đề:** Đổi JDK 17 sang JDK 25 nhưng giữ nguyên `Xmx` và cgroup limit. Có cần load test lại memory không?

**Đáp án:** Có. GC, runtime native overhead, code cache, class metadata và memory ergonomics có thể khác; kiểm tra peak cgroup memory và hiệu năng trên build mới.

## 21. Checklist trước khi đưa Java container vào production

- [ ] Đã xác định hard `memory.max` thật và phạm vi cgroup/container chưa?
- [ ] Có log `Runtime.maxMemory()` và so với `-Xmx`/`MaxRAMPercentage` không?
- [ ] Có nhận diện đúng JDK/HotSpot/container support của runtime deploy không?
- [ ] Có tránh đặt heap max bằng trọn container memory limit không?
- [ ] Có dự phòng cho metaspace, JIT, threads, GC và JNI native memory không?
- [ ] Có đo direct buffers bằng `BufferPoolMXBean` hoặc metrics framework không?
- [ ] Có hiểu `MaxDirectMemorySize` không phải trần mọi native allocation không?
- [ ] Có theo dõi `MemoryMXBean.nonHeap` nhưng không coi nó là toàn bộ native RSS không?
- [ ] Có phân biệt NMT reserved/committed và process RSS/cgroup current không?
- [ ] Có nhìn `memory.stat` để phân biệt file cache/mapped memory khi cần không?
- [ ] Có ghi `memory.peak` và `memory.events oom_kill` qua thời gian không?
- [ ] Có phân biệt Java OOME và kernel/container OOMKilled trong runbook không?
- [ ] Có kiểm tra số platform threads và `-Xss`/executor pools không?
- [ ] Có xem classloader/metaspace growth dưới tải dài hạn không?
- [ ] Có xem code cache/GC native overhead thay vì chỉ object heap không?
- [ ] Có đánh giá JNI/native libraries và các vùng NMT không bao phủ không?
- [ ] Có lập budget bằng các hạng mục không double-count không?
- [ ] Có đo p95/p99, throughput và GC pauses khi giảm `Xmx` không?
- [ ] Có không dùng `-Xmx` như cách chữa mọi native memory leak không?
- [ ] Có policy headroom phù hợp với peak traffic và rollback không?
- [ ] Có xem các container sidecars và memory budget đúng scope không?
- [ ] Có kiểm tra kết quả sau thay JVM build/GC/heap flags không?
- [ ] Có tránh bật NMT `detail` lâu dài khi chưa đánh giá overhead không?
- [ ] Có test OOM behavior trong môi trường không nguy hiểm, không gây sự cố production không?

## 22. Nguồn chính thức còn áp dụng

- [JDK 25 — `java` launcher JVM options](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-Xmx`/`MaxHeapSize`, `-XX:MaxRAMPercentage`, `-XX:MaxRAM`, `-XX:MaxDirectMemorySize`, `-XX:MaxMetaspaceSize`, `-Xss`, `-XX:+UseContainerSupport`.
- [JDK 25 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/25/vm/native-memory-tracking.html): NMT summary/detail, `jcmd VM.native_memory`, giới hạn tracking và overhead.
- [JDK 25 — Diagnostic Tools / NMT Memory Categories](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html): phân biệt JVM native categories, reserved vs committed và giải thích sample output.
- [JDK 25 — `jcmd` command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html): `GC.heap_info`, `VM.metaspace`, `VM.native_memory`, `VM.flags`.
- [Java SE 25 — `BufferPoolMXBean`](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): ước lượng số lượng, capacity và memory used của direct/mapped pools.
- [Java SE 25 — `MemoryMXBean`](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/MemoryMXBean.html): heap và non-heap memory usages theo JVM memory management model.
- [Java SE 25 — `ByteBuffer`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/ByteBuffer.html): `allocateDirect` và mô hình buffer.
- [JDK 25 — GC Tuning: Other Considerations](https://docs.oracle.com/en/java/javase/25/gctuning/other-considerations.html): native class metadata/Metaspace và giới hạn.
- [Linux Kernel — cgroup v2](https://docs.kernel.org/admin-guide/cgroup-v2.html): `memory.max`, `memory.current`, `memory.peak`, `memory.events`, `memory.stat`.
- [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): requests vs limits, memory enforcement, cgroup và scheduling.
- [JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): phân biệt logical virtual threads với platform/OS threads và các tài nguyên runtime.
- [Java SE 17 — `BufferPoolMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): xác nhận API demo dùng được với `javac --release 17`.
- [Java SE 17 — `MemoryMXBean`](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html): API đo heap và non-heap hiện diện trong Java 17.

**Kết luận:** Khi cấu hình bộ nhớ cho Java container, đừng gán toàn bộ `memory.max` cho `-Xmx`. Heap chỉ là **một phần** của memory footprint; metaspace, JIT code, platform thread stacks, direct NIO, GC bookkeeping, JNI/mmap, page cache và các process khác cũng có thể tiêu thụ memory tính vào giới hạn. `MaxRAMPercentage` là **heap-sizing heuristic**, còn `MaxDirectMemorySize` chỉ kiểm soát direct allocations tương ứng. Phân biệt **reserved, committed, RSS và cgroup charged memory**, theo dõi NMT cùng OS/cgroup, và chọn `Xmx` từ peak measurements cộng headroom an toàn. Java OOME và Linux OOMKilled là hai cơ chế lỗi khác nhau; cả hai cần được phát hiện đúng và xử lý bằng cấu hình có kiểm chứng.