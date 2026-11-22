# Các vùng JVM vẫn được cấp phát riêng khi chuyển Java heap sang thiết bị bộ nhớ khác (Java 10+)

## 1. Tư tưởng cốt lõi

Java 10 giới thiệu **JEP 316 — Heap Allocation on Alternative Memory Devices**: cho phép HotSpot bố trí **Java object heap** trên thiết bị bộ nhớ khác DRAM thông qua ánh xạ bộ nhớ (`memory mapping`) tới một đường dẫn filesystem thích hợp, ví dụ thiết bị memory-class kiểu NV-DIMM hỗ trợ ngữ nghĩa tương đương DRAM.

Cú pháp cấu hình:

```bash
java -XX:AllocateHeapAt=/mnt/pmem-javaheap -Xms256m -Xmx512m -jar app.jar
```

Đây là lệnh **minh họa trên HotSpot/Linux đã cấu hình mount và thiết bị tương thích**, không phải lệnh bắt buộc chạy trên laptop thông thường; `/mnt/pmem-javaheap` là ví dụ về điểm mount thích hợp, **không** phải mọi thư mục đĩa đều đáp ứng yêu cầu của thiết bị bộ nhớ.

Điểm quan trọng nhất của đề bài:

> **Chỉ object heap được chuyển sang vùng bộ nhớ thay thế.** Những vùng khác phục vụ JVM, như **JIT code heap/code cache, Metaspace và native platform-thread stacks**, **vẫn được cấp phát riêng**; JEP 316 không đưa chúng tự động vào vùng heap thay thế.

Tài liệu lệnh `java` của **Oracle Java SE 26** vẫn mô tả `-XX:AllocateHeapAt=path` và nêu rõ các vùng bộ nhớ khác tiếp tục ở **DRAM**, ngay cả khi object heap được cấp phát trên thiết bị khác. Vì vậy đây **không** phải một tính năng đã biến mất cùng Java 10.

### Một sơ đồ nên ghi nhớ

```text
                Một tiến trình HotSpot JVM
+----------------------------------------------------------------+
|                                                                |
|    Java OBJECT HEAP (đối tượng/array Java)                     |
|    +------------------------------------------------------+    |
|    | Được map tới alternative memory device phù hợp       |    |
|    | qua -XX:AllocateHeapAt=<path>                        |    |
|    | Young / old regions tùy GC; -Xms/-Xmx vẫn áp dụng    |    |
|    +------------------------------------------------------+    |
|                                                                |
|    Những thành phần KHÁC, được cấp phát riêng:                  |
|    +------------------------------------------------------+    |
|    | Metaspace: metadata lớp/phương thức                  |    |
|    | Code Heap / Code Cache: mã máy do JIT biên dịch      |    |
|    | Platform-thread stacks / VM service-thread stacks   |    |
|    | GC structures, runtime internals và C/C++ native    |    |
|    | NIO direct buffers, JNI/library allocations*         |    |
|    +------------------------------------------------------+    |
|                                                                |
|    * Những native allocations bên thứ ba có cơ chế riêng;       |
|      không mặc định -XX:AllocateHeapAt điều khiển chúng.        |
+----------------------------------------------------------------+
```

Sơ đồ mô tả **ranh giới theo cơ chế cấp phát của JVM**, không phải bản đồ vị trí vật lý của mọi byte. Một tiến trình thực tế còn có shared libraries, CDS/AOT mappings, file-backed pages và các cấu trúc kernel có cách accounting riêng.

**Không nên kết luận:** “Chỉ cần chuyển heap sang PMEM thì toàn bộ RAM DRAM của process được giải phóng”. Metaspace, JIT, thread stacks, cấu trúc GC, JNI và các phần khác **vẫn cần tài nguyên**.

## 2. Mục tiêu học tập

Sau bài, bạn sẽ:

1. Giải thích đúng phạm vi của `-XX:AllocateHeapAt=path`.
2. Phân biệt **Java object heap** với **native heap**, **Metaspace**, **Code Cache** và **thread stacks**.
3. Hiểu vì sao “heap on alternative device” không có nghĩa mọi `new` trong C/C++ hoặc mọi bộ nhớ tiến trình chuyển theo.
4. Phân biệt **class metadata** với các Java objects đại diện cho class.
5. Biết JIT compiled code nằm trong code cache riêng, không phải object heap.
6. Biết native stacks của platform threads khác với heap chunks của virtual threads hiện đại.
7. Phân biệt `ByteBuffer.allocateDirect(...)` với `byte[]`.
8. Hiểu các cấu trúc GC và runtime có thể tiêu thụ DRAM riêng dù object heap đã chuyển vị trí.
9. Biết flag heap `-Xms`/`-Xmx` và tùy chọn GC vẫn có ý nghĩa.
10. Nhận diện những điều kiện của thiết bị: memory-mapped, load/store, atomic semantics, OS/JVM support.
11. Dùng `MemoryMXBean`/`MemoryPoolMXBean` để quan sát ranh giới heap và non-heap.
12. Dùng `BufferPoolMXBean` cho số liệu direct/mapped buffers thuộc nhóm mà JDK đo được.
13. Bật `Native Memory Tracking` (NMT), `jcmd VM.native_memory` để điều tra nhiều cấp phát JVM-native.
14. Biết giới hạn của NMT: không bao quát mọi native library/JNI allocation.
15. Phân biệt `reserved`, `committed`, `used` và process RSS; tránh cộng trùng.
16. Nhận thức OOME Java heap vẫn có thể xảy ra trong khi DRAM còn trống.
17. Biết rủi ro thiếu DRAM cho native allocation dù alternative memory còn dư.
18. Vận hành và benchmark có đối chứng, không mặc định PMEM nhanh hơn DRAM.
19. Kiểm thử chương trình Java 17+ portable, không cần thiết bị NV-DIMM để học ranh giới JVM memory pools.
20. Biết cách kiểm thêm **OS mappings và hardware** để chứng minh placement thật sự.
21. Tránh lấy ví dụ hoặc flags đã legacy làm khuyến nghị cho JDK hiện đại.

## 3. Ranh giới của `-XX:AllocateHeapAt` nằm ở đâu?

Khi HotSpot được cấu hình trên nền tảng hỗ trợ:

```text
-XX:AllocateHeapAt=/mnt/pmem-javaheap
```

HotSpot sử dụng một đường dẫn filesystem để đặt **bộ nhớ backing của object heap** trên vùng được hệ điều hành ánh xạ tới thiết bị đó.

Đây là **cấu hình của VM launcher**, không phải lời gọi Java source code. Ứng dụng tiếp tục tạo đối tượng bình thường:

```java
record Order(int id, String product) {}

Order order = new Order(42, "SSD");
int[] counters = new int[1000];
```

Đoạn mã là **ví dụ rút gọn** trong một phương thức Java có khai báo `Order` thích hợp. `Order` và `int[]` vẫn là đối tượng trên Java heap theo ngữ nghĩa Java. Việc heap có backing ở DRAM hay thiết bị được chọn là do **HotSpot/OS mapping**, không phải do cú pháp `new`.

### Cờ không thay thế Java Memory Model

Thiết bị đích phải có **ngữ nghĩa bộ nhớ như DRAM**, bao gồm các phép toán atomic phù hợp. Java concurrency, `volatile`, locks, `VarHandle` và thao tác đối tượng vẫn phải tuân thủ Java Memory Model.

Cấu hình `AllocateHeapAt` **không** biến Java objects thành bản ghi bền vững, không cấp transaction hay bảo đảm `persist` khi mất điện. Khả năng persistence của phần cứng và tính đúng đắn của định dạng dữ liệu sau khi JVM kết thúc là **những vấn đề khác**.

### Cờ không điều khiển `malloc` của mọi thư viện

Nếu một JNI library gọi `malloc`, hoặc một thư viện networking cấp phát direct memory, không có hợp đồng rằng `-XX:AllocateHeapAt` sẽ hướng chúng tới cùng device. Những cấp phát này sử dụng **cơ chế native allocator hoặc system calls riêng**.

Do đó thay đổi `AllocateHeapAt` không tự động làm số liệu native RAM giảm về 0.

## 4. “Heap” trong tên các vùng bộ nhớ không luôn là cùng một heap

Có ít nhất ba cách người ta dùng từ **heap**:

| Thuật ngữ | Nội dung | `-XX:AllocateHeapAt` có nhắm tới? |
| --- | --- | --- |
| **Java object heap** | Instance và arrays Java, do GC quản lý | **Có** |
| **Code heap / Code Cache** | Code blobs và mã máy được biên dịch/biên dịch lại bởi JIT | **Không** |
| **C/C++ native heap** | Cấp phát bởi native runtime, VM implementation hoặc thư viện | **Không** |

“Heap được chuyển” trong JEP 316 luôn hiểu là **Java object heap**; không phải mọi vùng có chữ `heap` trong tên.

### Không nên lấy tên class Java để suy ra vị trí metadata

Khi JVM load `class Customer`:

- **Java object** như `new Customer()` nằm trên **Java heap**.
- **Metadata** mô tả class, methods, constant-pool runtime và các cấu trúc quản lý class được HotSpot giữ trong **Metaspace/non-heap**.
- Một object kiểu `java.lang.Class` có thể được tham chiếu và quản lý như đối tượng Java, nhưng điều đó **không** đưa toàn bộ metadata của class vào Java heap.

Câu “class nằm trên heap” là quá mơ hồ. Phải hỏi **class metadata** hay **đối tượng thể hiện/tham chiếu class**.

## 5. Metaspace vẫn được cấp phát riêng

**Metaspace** là khu vực HotSpot quản lý nhiều loại metadata của các class được load: thông tin kiểu, methods, cấu trúc phục vụ linking và runtime.

Một số hiện tượng làm Metaspace tăng:

- Load thêm nhiều classes và dependencies.
- Framework tạo hoặc load proxy classes.
- Plugin systems và class loaders có vòng đời dài.
- Dynamic code generation làm class metadata nhiều.
- Classloader retention ngăn giải phóng class metadata không còn cần.

Nếu chuyển object heap sang device khác, **Metaspace không tự chuyển theo**. Nó vẫn dùng vùng memory riêng theo thiết kế HotSpot.

### `-Xmx` không giới hạn Metaspace

```bash
java -Xmx512m -XX:MaxMetaspaceSize=192m -jar app.jar
```

Trong ví dụ:

- `-Xmx512m` là giới hạn **Java object heap**.
- `-XX:MaxMetaspaceSize=192m` đặt một giới hạn khác cho Metaspace (khi HotSpot hỗ trợ).
- Hai giới hạn **khác nhau**, không phải hai tên của một cùng vùng.
- Đặt metaspace quá thấp có thể gây `OutOfMemoryError: Metaspace`, ngay cả khi heap còn trống.

`MaxMetaspaceSize` không phải giá trị “càng thấp càng tối ưu”. Cần đo mức class metadata thực tế; đừng cấu hình quá nhỏ chỉ để ép JVM tiết kiệm DRAM.

### Compressed Class Space

Trên một số cấu hình HotSpot có compressed class pointers, **Compressed Class Space** là khu vực liên quan tới metadata kiểu class. Nó **không** biến thành Java object heap khi `AllocateHeapAt` hoạt động.

Không hardcode rằng mọi JVM sẽ luôn có memory pool đúng tên `Compressed Class Space`: tên và việc tồn tại của pool phụ thuộc VM, architecture và các flags.

## 6. Code heap / Code Cache vẫn ở nơi riêng

HotSpot dùng **Just-in-Time (JIT) compilation** để chuyển bytecode của những phương thức thường xuyên chạy thành machine code được CPU thực thi trực tiếp.

Machine code và các thông tin code blobs thường được lưu ở **Code Cache** (cũng được gọi theo cấu trúc triển khai là code heaps/code cache segments).

```text
Bytecode (class file)
      |
      v
JIT compiler (VM native component)
      |
      v
Machine code / compiled nmethods
      |
      v
CODE CACHE riêng, KHÔNG phải Java object heap
```

Một JVM có thể có nhiều code heaps/segmented code cache như `CodeHeap 'non-nmethods'`, `profiled nmethods`, `non-profiled nmethods`. **Tên không phải API portable**; phụ thuộc HotSpot release và flags.

### Hạn mức Code Cache khác hạn mức Heap

Một số HotSpot options liên quan:

```bash
java -Xmx512m -XX:ReservedCodeCacheSize=128m -jar app.jar
```

Ý nghĩa:

- `ReservedCodeCacheSize` là cấu hình **code cache capacity**.
- Không phải giới hạn bytes của Java objects.
- Không làm `-XX:AllocateHeapAt` tự chuyển code cache.
- Thay đổi quá nhỏ có thể ảnh hưởng JIT, throughput và compilation behavior.

Một lỗi vận hành thường gặp là tăng `-Xmx` vì thấy VM cảnh báo code cache gần đầy. **Tăng Java heap không trực tiếp tăng Code Cache** khi đã có giới hạn riêng; cần xem đúng memory pool và nguyên nhân.

## 7. Native stacks của platform threads vẫn là vùng độc lập

Mỗi **platform thread** sử dụng một OS thread tương ứng trong thời gian sống. OS/JVM cấp phát **native thread stack** cho các call frames, local variables và runtime invocation state phù hợp.

Về mặt memory budget:

```text
Java object heap có thể nằm ở alternative device
Native platform-thread stack vẫn được cấp phát riêng
```

Khi nhiều platform threads cùng tồn tại, tổng native stack reservations/commits có thể đáng kể, dù Java heap chỉ chứa ít object.

Tùy VM/OS, `-Xss` có thể điều chỉnh kích thước stack của thread:

```bash
java -Xmx512m -Xss1m -jar app.jar
```

Không suy diễn phép nhân **thread count × -Xss** thành RSS chính xác: stack có thể chỉ commit các trang thực sự dùng và OS accounting khác nhau. Tuy vậy nó là một **rủi ro upper-bound/budget quan trọng**.

### Vì sao stack không thuộc Java heap?

Java stack frames là trạng thái thực thi của thread, không phải đối tượng `new` bình thường được GC xử lý như một list cùng object heap. Code có thể tham chiếu objects trên heap, nhưng bản thân native stack memory cho platform threads có vòng đời và cơ chế quản lý riêng.

`-XX:AllocateHeapAt` không đưa mọi native stack vào thiết bị thay thế.

## 8. Ngoại lệ cần hiểu trong Java hiện đại: virtual threads

**Virtual threads**, được chuẩn hóa trong Java 21, có vòng đời nhẹ và không sở hữu riêng một OS thread trong suốt thời gian tồn tại. Khi unmounted, các stack frames của virtual threads có thể được lưu dưới dạng **stack chunk objects trong Java heap**.

Điều này dẫn đến một sắc thái mà bài giảng về JEP 316 thời Java 10 chưa đề cập:

- **Native stack của platform thread/carrier:** không thuộc Java object heap và không tự chuyển theo `AllocateHeapAt`.
- **Stack chunks của virtual thread khi được JVM lưu trên Java heap:** là **Java heap objects** theo cơ chế triển khai liên quan, nên có thể sử dụng heap backing như các objects khác.
- Không được kết luận “mọi loại stack trong Java 26 nằm hoàn toàn ngoài heap” hoặc “mọi virtual thread có một native stack riêng”.

Ví dụ Java 21+ tạo virtual thread:

```java
Thread worker = Thread.ofVirtual().start(() -> {
    System.out.println("virtual");
});
worker.join();
```

Đây là mã minh họa cho **Java 21+**, **không nằm trong chương trình Java 17+** ở mục 18. Nó chứng minh public API virtual thread; không chứng minh vật lý stack placement của một JVM cụ thể.

**Mấu chốt của đề bài vẫn đúng:** tài liệu `AllocateHeapAt` nói **thread stacks** tiếp tục được cấp phát riêng theo phạm vi hạ tầng native/OS thread của JEP 316. Với virtual threads đời mới phải phân biệt loại memory đang được hỏi, thay vì áp dụng một câu giản lược cho mọi loại stack.

## 9. GC metadata và những cấu trúc VM nội bộ không nằm trọn trong object heap

Garbage collectors cần thêm cấu trúc để vận hành, chẳng hạn:

- Card tables / remembered sets hoặc các bảng theo dõi tham chiếu.
- Mark bitmaps hoặc các cấu trúc phục vụ marking.
- Data structures cho GC workers, queues và task coordination.
- Metadata giúp HotSpot nạp classes, xác định roots và xử lý references.
- Bookkeeping của heap regions, object headers hoặc runtime.

**Không phải mọi cấu trúc này được đặt ngoài heap**: một số metadata gắn với objects hoặc được hiện thực bằng các Java objects, tùy collector/JDK. Nhưng **nhiều phần cấp phát native riêng** và sẽ không tự động được điều khiển bởi `AllocateHeapAt`.

### Tại sao “heap lớn hơn” không tự bảo đảm đủ DRAM?

Giả sử object heap 16 GiB được ánh xạ vào một thiết bị phù hợp. JVM vẫn cần DRAM cho các công việc:

- JIT compile và code cache.
- Metaspace cho những classes đang load.
- Native stacks và GC worker threads.
- Native allocations của GC.
- JNI/direct buffers, system libraries.

Nếu DRAM thiếu chỗ cho các cấu trúc này, một tiến trình vẫn có thể gặp lỗi cấp phát native, không tạo được thread hoặc crash vì thiếu memory **mặc dù alternative device còn dư dung lượng cho heap**.

Điều này rất quan trọng với hệ thống được thiết kế “để giảm tải DRAM”: giảm **object heap placement** không xóa bỏ nhu cầu DRAM của HotSpot.

## 10. Direct buffers: một trường hợp ngoài heap thường bị bỏ quên

Java NIO cung cấp:

```java
ByteBuffer direct = ByteBuffer.allocateDirect(1024 * 1024);
```

Thông thường trên HotSpot, **vùng payload** của direct buffer được cấp phát ở **native/off-heap memory**. Đối tượng `ByteBuffer` dùng để quản lý nó vẫn là một Java object có thể được GC theo dõi.

Phân biệt:

| Cách cấp phát | Dữ liệu bytes chủ yếu nằm ở đâu? |
| --- | --- |
| `new byte[1024 * 1024]` | **Java object heap** |
| `ByteBuffer.allocate(1024 * 1024)` | Backing array / Java heap (thường) |
| `ByteBuffer.allocateDirect(1024 * 1024)` | Native direct memory tách khỏi object heap |

Vì vậy `-XX:AllocateHeapAt` **không có nghĩa direct-buffer payload cùng được ánh xạ tới alternative heap device**.

### BufferPoolMXBean giúp thấy điều gì?

`ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)` cho phép truy cập một số buffer pools như `direct` hoặc `mapped`, nếu VM có cung cấp.

Các số như:

- `getCount()`: số buffers đang theo dõi.
- `getMemoryUsed()`: bộ nhớ được dùng theo báo cáo buffer pool.
- `getTotalCapacity()`: tổng capacity.

Chúng là **số liệu quản lý**, không phải bản đồ physical memory. Không dùng `getMemoryUsed()` để kết luận toàn bộ native library allocations đã được đo.

### Không nhầm direct memory với memory-mapped files

`MappedByteBuffer` có thể đại diện cho một **file mapping**; nguồn bytes và accounting phụ thuộc OS, file-backed pages và cách map. Nó khác với direct buffer do một allocator native tạo. Cả hai đều không được tự động kéo vào object heap chỉ bằng `-XX:AllocateHeapAt`.

## 11. JNI, C/C++ native allocations và runtime services

JVM chạy nhiều native code:

- C++ components của chính HotSpot.
- Threading, synchronization và memory management internals.
- File/network I/O trong JDK native libraries.
- JNI/JVMTI agents.
- Third-party native libraries như codecs, cryptography, machine learning.

Một lời gọi native cấp phát `malloc` có thể đưa memory vào vùng **native heap** của process, chứ không thông qua Java `new`.

```text
new Object()               -> Java object heap (HotSpot GC)
ByteBuffer.allocateDirect() -> native/off-heap payload (HotSpot thường dùng)
JNI malloc()                -> allocator của native library
JIT compiled code           -> Code Cache
Class metadata              -> Metaspace
Platform-thread call stack  -> native thread stack
```

Không phải một quy luật “mọi non-heap byte luôn ở đúng một ngân sách DRAM dễ đo”: OS page policies, NUMA, shared libraries và file mappings có ảnh hưởng. Điều đang được khẳng định theo JEP 316 là **flag chuyển object heap không chuyển đồng bộ toàn bộ các cấu trúc khác**.

### CDS/AOT cũng là một phạm vi riêng

Class Data Sharing archives hoặc AOT caches trên JDK hiện đại có thể được **memory-mapped** từ file, có shared pages và cơ chế riêng. Việc dùng `-XX:AllocateHeapAt` **không tự biến các file mapping này thành Java object heap**.

Không lấy kích thước `.jsa`/`.aot` cộng thẳng với maximum heap rồi coi là RSS chắc chắn; cần xem OS mapping/accounting và actual resident pages.

## 12. `-Xms`, `-Xmx` và tùy chọn GC vẫn áp dụng

Một điều dễ hiểu nhầm là “một khi heap đặt ở thiết bị khác, JVM không còn điều khiển kích thước heap”. Thực tế tài liệu `java` JDK 26 nêu rõ **heap-related flags và GC-related flags vẫn hoạt động như trước** trong phạm vi được triển khai hỗ trợ.

Ví dụ:

```bash
java \
  -XX:AllocateHeapAt=/mnt/pmem-javaheap \
  -Xms256m -Xmx512m \
  -jar app.jar
```

Ở đây:

- `-XX:AllocateHeapAt`: chọn **thiết bị backing** cho object heap.
- `-Xms`: thiết lập initial heap sizing.
- `-Xmx`: giới hạn **maximum Java object heap**.
- Collector vẫn quản lý allocations và GC theo cơ chế phù hợp.

Cờ `-Xmx512m` **không** đặt upper bound cho Metaspace, code heap, native stacks hoặc JNI memory; chúng có những điều kiện và tùy chọn quản lý riêng.

### Không tự giả định mọi collector và mọi platform đều hỗ trợ kết hợp

JDK có thể có nhiều collectors và các ràng buộc platform khác nhau. Tài liệu launcher mô tả mục tiêu của flag, nhưng không bảo đảm rằng **mọi tổ hợp `-XX:AllocateHeapAt` với mọi collector, architecture, page size hoặc OS** đều được hỗ trợ hoặc có hiệu năng như nhau.

Trước khi triển khai:

1. Đối chiếu tài liệu **đúng HotSpot build**.
2. Kiểm cờ có được JVM nhận diện không.
3. Kiểm điểm mount có semantics yêu cầu.
4. Chạy validation/stress test của collector và workload.
5. Quan sát memory placement, GC logs, native memory và latency.

### Device capacity không thay thế process capacity

Nếu heap device có 32 GiB nhưng process address space, container accounting hoặc DRAM khác không đủ, JVM có thể vẫn lỗi. Đừng tính `-Xmx` chỉ dựa vào dung lượng device; cần tính toàn bộ giới hạn OS/container và JVM native resources.

## 13. Sơ đồ các cấp phát và bộ đo thích hợp

| Thành phần | Thuộc object heap? | Công cụ thường dùng | Ghi chú |
| --- | --- | --- | --- |
| Java objects và arrays | Có | `MemoryMXBean`, GC logs, heap dump | Đây là phạm vi `AllocateHeapAt` |
| Metaspace | Không | `MemoryPoolMXBean`, NMT `Class` | Vẫn riêng |
| Code Cache | Không | `MemoryPoolMXBean`, NMT `Code` | Vẫn riêng |
| Native platform-thread stacks | Không | NMT `Thread`, OS thread metrics | Committed khác reserved |
| Native GC/runtime structures | Không hoàn toàn | NMT `GC`/`Internal`, JVM logs | Phụ thuộc collector |
| Direct buffers | Payload thường native | `BufferPoolMXBean`, NMT/OS | Java wrapper trên heap |
| JNI third-party allocations | Thường không | Native profiler, OS, library metrics | NMT có giới hạn |
| CDS/AOT file-backed maps | Không mặc định | `pmap`, `/proc/<pid>/maps`, `smaps` | Có thể shared/mapped |
| RAM OS / cgroup charge | Không phải pool JVM | `/proc`, cgroup metrics | Không thay bằng heap used |

**Cảnh báo quan trọng:** `MemoryPoolMXBean` phân loại theo **logical memory management của JVM**; nó **không trả địa chỉ vật lý** hoặc thiết bị DRAM/PMEM. Muốn biết backing thực của heap, cần xem thêm OS/device mappings và môi trường.

## 14. NMT và ý nghĩa thật của `reserved`/`committed`

HotSpot **Native Memory Tracking (NMT)** giúp theo dõi nhiều cấp phát và virtual-memory regions bên trong JVM.

Bật NMT ngay khi khởi động:

```bash
java -XX:NativeMemoryTracking=summary \
     -XX:AllocateHeapAt=/mnt/pmem-javaheap \
     -Xms256m -Xmx512m -jar app.jar
```

Từ một terminal khác trên máy có JDK tools và quyền phù hợp:

```bash
jcmd <pid> VM.native_memory summary
```

`<pid>` là placeholder phải thay bằng PID thật (ví dụ từ `jcmd -l` hoặc công cụ OS). Không gõ nguyên dấu ngoặc nhọn `<pid>` vào terminal Linux như một PID.

### Đọc báo cáo NMT đúng cách

Một báo cáo có thể phân hạng `Java Heap`, `Class`, `Thread`, `Code`, `GC`, `Internal` và nhiều phần khác tùy JDK build.

NMT thường báo:

- **Reserved**: không gian địa chỉ ảo được đặt trước hoặc phân bổ cho một subsystem; **không đồng nghĩa** toàn bộ là RAM vật lý.
- **Committed**: phần bộ nhớ được commit theo cơ chế memory management, **không thể tự coi là private resident RSS**.
- **Malloc**: cấp phát native allocator mà NMT có theo dõi.
- **Mmap**: vùng memory mappings trong phạm vi theo dõi.

`Java Heap` trong NMT là một **hạng mục logical JVM**, có thể cho biết size của heap reserved/committed, nhưng **không chứng minh vị trí vật lý của backing device** nếu không đối chiếu maps và mount.

### NMT không đo mọi thứ

NMT có thể bỏ qua bộ nhớ cấp phát bên ngoài JVM subsystem, ví dụ third-party JNI code và một số thành phần JDK/native libraries. Nó cũng **không thay thế** OS RSS/PSS, cgroup accounting hay các công cụ kiểm tra vùng memory-mapped files.

Nếu NMT báo tổng native khá thấp nhưng RSS lớn, cần xem:

- Memory-mapped file pages.
- Native libraries bên thứ ba.
- Direct buffers và JDK allocations theo cách tracking.
- Shared memory, page cache, GC heap residency.
- Sự chồng lấn giữa các số liệu.

Đừng dùng `NMT total reserved + NMT total committed` làm tổng RAM: đó là hai khái niệm của cùng các vùng nhớ, không phải hai nhóm không trùng nhau.

## 15. Xem sự thay đổi theo thời gian bằng `jcmd`

Sau khi bật NMT, có thể lập baseline rồi xem phần chênh lệch:

```bash
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary.diff
```

Quy trình gợi ý:

1. Khởi chạy workload và để hệ thống hoàn thành warmup.
2. Thiết lập baseline.
3. Thực hiện một workload có đặc trưng xác định.
4. Chạy `summary.diff` để xem các hạng mục JVM đang tăng.
5. Phân loại tăng do `Class`, `Thread`, `Code`, `GC` hay một subsystem khác.
6. So với application traffic và OS RSS/PSS.

Nếu muốn xem sâu hơn, HotSpot có `NativeMemoryTracking=detail` và `VM.native_memory detail.diff` trên các bản hỗ trợ. Chế độ detail có overhead lớn hơn; chỉ sử dụng khi có nhu cầu.

### Vì sao NMT không thể trả lời một mình “vùng nào nằm ở PMEM”?

NMT biết JVM đã đặt/tổ chức memory như thế nào, nhưng không có contract chuẩn là nó phải ánh xạ từng page vào tên DIMM/NUMA node hay path mount của thiết bị. Cần thêm OS tools (ví dụ `/proc/<pid>/maps`, `smaps`/`pmap`, mount info và các công cụ kiểm tra NUMA/device) để xác nhận placement trên Linux thích hợp.

## 16. Phân biệt used, committed và max ở tầng Java

`Runtime` và `MemoryMXBean` cung cấp thông tin hữu ích nhưng **không chỉ ra vị trí vật lý**:

```java
Runtime runtime = Runtime.getRuntime();

long maxHeap = runtime.maxMemory();
long currentHeap = runtime.totalMemory();
long freeInCurrentHeap = runtime.freeMemory();
long usedEstimate = currentHeap - freeInCurrentHeap;
```

`Runtime.maxMemory()` là upper bound **Java heap**; `totalMemory()-freeMemory()` ước lượng phần heap đang dùng.

Ví dụ với `MemoryMXBean`:

```java
var bean = ManagementFactory.getMemoryMXBean();
var heap = bean.getHeapMemoryUsage();
var nonHeap = bean.getNonHeapMemoryUsage();

System.out.println(heap.getUsed());
System.out.println(heap.getCommitted());
System.out.println(nonHeap.getUsed());
```

Đoạn trên là **minh họa** trong class có import `java.lang.management.ManagementFactory`; output số sẽ khác nhau theo runtime, workload và thời điểm.

Hai số:

- `heap.getUsed()`.
- `nonHeap.getUsed()`.

là hai nhóm được Java Memory Management API mô tả riêng; chúng **không phải** địa chỉ vật lý và cũng không đại diện đầy đủ mọi JNI/native/process allocation.

### `MemoryPoolMXBean` cho thấy logic phân vùng

`ManagementFactory.getMemoryPoolMXBeans()` trả các pools. Mỗi pool có `getType()`:

- `MemoryType.HEAP`: heap memory pools.
- `MemoryType.NON_HEAP`: non-heap memory pools.

Bạn có thể xác định Metaspace/CodeCache pools theo tên trên **HotSpot thực tế**, nhưng danh sách và tên pool **không thuộc hợp đồng cố định cho mọi JVM**.

## 17. Một ví dụ ngân sách bộ nhớ: chỉ object heap chuyển vị trí

Giả sử một ứng dụng có nhu cầu **minh họa, không phải đo thực tế**:

| Thành phần | Giả định (MiB) | Phạm vi |
| --- | ---: | --- |
| Java object heap | 512 | Backing ở alternative device phù hợp |
| Metaspace | 80 | Vùng riêng |
| Code Cache | 64 | Vùng riêng |
| Native thread stacks | 48 | Vùng riêng |
| Direct buffers | 40 | Vùng riêng |
| Other JVM/native | 100 | Vùng riêng |
| **Tổng các hạng mục không trùng nhau** | **844** | Nhiều loại memory allocations |
| **Phần ngoài object heap** | **332** | Vẫn cần tài nguyên riêng |

Tính:

```text
80 + 64 + 48 + 40 + 100 = 332 MiB
512 + 332 = 844 MiB
```

Ý nghĩa:

- Nếu object heap chuyển tới alternative memory device, **332 MiB mô hình** còn là các khoản cần cấp phát riêng.
- Không được tuyên bố JVM chỉ cần 0 MiB DRAM sau khi chuyển heap.
- Một số OS mappings/cache/native allocations và container charges ngoài bảng vẫn có thể tồn tại.

**Cảnh báo phương pháp:** các khoản trong bảng là **ngân sách giả định được định nghĩa không overlap**. Trong metrics thật, `RSS` đã có thể bao gồm resident heap pages; cộng RSS với heap used sẽ **double-count**. NMT reserved/committed cũng không được cộng vô điều kiện vào cgroup memory.current.

### Nếu heap là 4 GiB thì sao?

Ngay cả khi device dành cho heap còn 4 GiB, một ứng dụng có hàng nghìn platform threads hoặc native buffers lớn có thể thiếu DRAM. **Heap capacity và DRAM headroom là hai câu hỏi khác nhau**.

## 18. Chương trình Java 17+ độc lập: chứng minh các pool được quản lý riêng

Tạo file **`SeparateJvmMemoryAreasDemo.java`**:

```java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryType;
import java.lang.management.MemoryUsage;
import java.lang.ref.Reference;
import java.nio.ByteBuffer;
import java.util.List;
import java.util.Locale;

public final class SeparateJvmMemoryAreasDemo {
    private static final long MIB = 1024L * 1024L;

    record MemoryModel(int heapMiB, int metaspaceMiB, int codeMiB,
                       int threadStacksMiB, int directMiB, int otherNativeMiB) {
        int separateMiB() {
            int one = Math.addExact(metaspaceMiB, codeMiB);
            int two = Math.addExact(threadStacksMiB, directMiB);
            return Math.addExact(Math.addExact(one, two), otherNativeMiB);
        }
        int combinedMiB() {
            return Math.addExact(heapMiB, separateMiB());
        }
    }

    public static void main(String[] args) {
        // Cac so trong model la GIA DINH, khong phai do phan cung.
        MemoryModel model = new MemoryModel(512, 80, 64, 48, 40, 100);
        System.out.println("modelHeapMiB=" + model.heapMiB());
        System.out.println("modelMetaspaceMiB=" + model.metaspaceMiB());
        System.out.println("modelCodeMiB=" + model.codeMiB());
        System.out.println("modelStacksMiB=" + model.threadStacksMiB());
        System.out.println("modelDirectMiB=" + model.directMiB());
        System.out.println("modelOtherNativeMiB=" + model.otherNativeMiB());
        System.out.println("modelSeparateMiB=" + model.separateMiB());
        System.out.println("modelCombinedMiB=" + model.combinedMiB());

        List<MemoryPoolMXBean> pools = ManagementFactory.getMemoryPoolMXBeans();
        boolean heapPool = pools.stream()
                .anyMatch(p -> p.getType() == MemoryType.HEAP);
        boolean nonHeapPool = pools.stream()
                .anyMatch(p -> p.getType() == MemoryType.NON_HEAP);
        boolean metaspace = pools.stream()
                .anyMatch(p -> p.getType() == MemoryType.NON_HEAP
                        && p.getName().toLowerCase(Locale.ROOT)
                                .contains("metaspace"));
        boolean codeCache = pools.stream()
                .anyMatch(p -> p.getType() == MemoryType.NON_HEAP
                        && p.getName().toLowerCase(Locale.ROOT)
                                .contains("code"));

        MemoryUsage heap = ManagementFactory.getMemoryMXBean()
                .getHeapMemoryUsage();
        MemoryUsage nonHeap = ManagementFactory.getMemoryMXBean()
                .getNonHeapMemoryUsage();

        ByteBuffer direct = ByteBuffer.allocateDirect(1024 * 1024);
        direct.putInt(0, 123456);
        boolean directPayloadOk = direct.getInt(0) == 123456;
        BufferPoolMXBean directPool = ManagementFactory
                .getPlatformMXBeans(BufferPoolMXBean.class).stream()
                .filter(p -> "direct".equals(p.getName()))
                .findFirst().orElseThrow();

        System.out.println("heapPoolPresent=" + heapPool);
        System.out.println("nonHeapPoolPresent=" + nonHeapPool);
        System.out.println("metaspacePoolPresent=" + metaspace);
        System.out.println("codeCachePoolPresent=" + codeCache);
        System.out.println("heapMaxWithin128MiB="
                + (Runtime.getRuntime().maxMemory() > 0
                && Runtime.getRuntime().maxMemory() <= 128L * MIB));
        System.out.println("heapUsedWithinCommitted="
                + (heap.getUsed() >= 0
                && heap.getUsed() <= heap.getCommitted()));
        System.out.println("nonHeapUsedWithinCommitted="
                + (nonHeap.getUsed() >= 0
                && nonHeap.getUsed() <= nonHeap.getCommitted()));
        System.out.println("directMemoryAtLeastOneMiB="
                + (directPool.getMemoryUsed() >= MIB));
        System.out.println("directPayloadOK=" + directPayloadOk);
        Reference.reachabilityFence(direct);
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac --release 17 -encoding UTF-8 SeparateJvmMemoryAreasDemo.java
java -Xms32m -Xmx128m SeparateJvmMemoryAreasDemo
```

**Stdout chính xác đã đối chiếu trên HotSpot JDK 24:**

```text
modelHeapMiB=512
modelMetaspaceMiB=80
modelCodeMiB=64
modelStacksMiB=48
modelDirectMiB=40
modelOtherNativeMiB=100
modelSeparateMiB=332
modelCombinedMiB=844
heapPoolPresent=true
nonHeapPoolPresent=true
metaspacePoolPresent=true
codeCachePoolPresent=true
heapMaxWithin128MiB=true
heapUsedWithinCommitted=true
nonHeapUsedWithinCommitted=true
directMemoryAtLeastOneMiB=true
directPayloadOK=true
```

### Bài demo chứng minh điều gì?

**Nhóm mô hình:**

- `modelHeapMiB=512`: Java heap giả định.
- `modelMetaspaceMiB=80`, `modelCodeMiB=64`, `modelStacksMiB=48`, `modelDirectMiB=40`, `modelOtherNativeMiB=100`: các khoản riêng.
- `modelSeparateMiB=332`: tổng giả định ngoài object heap.
- `modelCombinedMiB=844`: tổng các khoản không trùng nhau.

**Nhóm MXBean:**

- `heapPoolPresent=true`: HotSpot báo một hoặc nhiều memory pools có kiểu `HEAP`.
- `nonHeapPoolPresent=true`: có các memory pools kiểu `NON_HEAP`.
- `metaspacePoolPresent=true` và `codeCachePoolPresent=true`: tên pools trong **JDK 24** có chứa `metaspace` và `code`.
- `heapMaxWithin128MiB=true`: bài lab được chạy với `-Xmx128m`.
- `heapUsedWithinCommitted=true` và `nonHeapUsedWithinCommitted=true`: các mối quan hệ accounting ở thời điểm snapshot.

**Nhóm direct buffer:**

- `directMemoryAtLeastOneMiB=true`: chương trình đã cấp phát một direct buffer 1 MiB, pool `direct` theo dõi memory.
- `directPayloadOK=true`: đọc/ghi bytes của buffer hoạt động.
- `Reference.reachabilityFence(direct)` giữ đối tượng `direct` reachable tới cuối giai đoạn quan sát.

### Điều demo không chứng minh

Máy chạy QA **không có cấu hình thiết bị bộ nhớ thay thế tương đương DRAM để thử `-XX:AllocateHeapAt`**. Vì vậy các boolean chỉ kiểm **logical boundaries và JVM memory management APIs**, **không** chứng minh Java heap đang được ánh xạ tới NV-DIMM.

Để xác nhận physical placement, phải chạy trong **HotSpot/Linux phù hợp với mount/device thật** và dùng các công cụ OS tại mục 20.

Các tên pools và buffer tracking có thể khác ở JVM không phải HotSpot. Chương trình được viết để runnable trên Java 17+, nhưng **17 dòng stdout là kết quả chính xác đã QA với HotSpot JDK 24**; đừng suy ra mọi JVM implementation bắt buộc có một pool tên `Metaspace` hoặc `CodeHeap`.

## 19. Những lỗi khi suy luận từ báo cáo Java metrics

### Lỗi A: “`getNonHeapMemoryUsage` là tổng mọi bộ nhớ ngoài heap”

Không đúng. Nó đo nhóm memory JVM quản lý qua MXBean; nhiều native allocations, JNI libraries và OS mappings không được đại diện đầy đủ.

### Lỗi B: “`heap.getCommitted` cho biết Java heap đang ở DRAM”

Không. Nó nói về commitment theo JVM accounting, không chỉ ra backing device.

### Lỗi C: “`heap.getUsed + nonHeap.getUsed` là tổng process RSS”

Không chắc. Những cấu trúc native, shared/file mappings và cách OS đếm trang resident khác nhau; phép cộng chỉ có nghĩa theo **hai logical MXBean categories**.

### Lỗi D: “Tên `CodeHeap` chứng minh code cache nằm trong Java heap”

Không. Code heap là cấu trúc **Code Cache** riêng.

### Lỗi E: “Có direct buffer là Java byte array nằm trên heap alternative device”

Không. Payload của `allocateDirect` thường nằm trong native memory; `ByteBuffer` wrapper có thể vẫn ở object heap.

### Lỗi F: “`ThreadMXBean.getThreadCount` nhân `-Xss` là RSS chính xác”

Không. Stack reservations/commits và mức chạm trang khác nhau; còn có native VM threads và virtual thread semantics.

### Lỗi G: “NMT chỉ báo 1 GiB nên process RSS chắc chắn bằng 1 GiB”

Không. NMT không bao quát mọi allocations và dùng reserved/committed semantics riêng.

### Lỗi H: “PMEM có nhiều dung lượng nên không bao giờ có `OutOfMemoryError`”

Sai. Heap có `-Xmx` riêng, native memory có thể thiếu, và OS/device có thể lỗi.

## 20. Kiểm chứng alternative memory placement trên Linux

Đây là **quy trình thực hành cho môi trường có phần cứng và filesystem thích hợp**, không phải lệnh cần chạy trong mọi container hoặc laptop.

### Bước 1 — xác minh thiết bị và filesystem

Cần trả lời:

1. Device có hỗ trợ **memory-mapped load/store** với semantics tương đương DRAM không?
2. Filesystem đã được cấu hình/mount phù hợp để JVM ánh xạ trực tiếp vào vùng bộ nhớ thiết bị chưa?
3. Đường dẫn `/mnt/pmem-javaheap` có tồn tại và writable với tài khoản chạy JVM không?
4. Mount có đủ capacity cho heap reserved/committed cần thiết và các file VM tạo ra không?
5. JDK build/OS/architecture có hỗ trợ flag trên nền tảng này không?

Các lệnh đọc môi trường:

```bash
mount | grep -E 'dax|pmem|/mnt/pmem'
lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINTS
df -h /mnt/pmem-javaheap
```

Đây chỉ là thông tin **thiết bị, mount, dung lượng**; thấy chuỗi `pmem` trong tên mount **không đủ chứng minh** thiết bị có đúng semantics. Kiểm tài liệu và cấu hình của phần cứng/filesystem/OS.

### Bước 2 — chạy một ứng dụng bằng đường dẫn phù hợp

```bash
java -XX:AllocateHeapAt=/mnt/pmem-javaheap \
     -Xms256m -Xmx512m \
     -XX:NativeMemoryTracking=summary \
     -Xlog:gc=info \
     -jar app.jar
```

Nếu `app.jar` cần option/truyền tham số, thêm vào sau tên file JAR. Đảm bảo mọi JVM flags đứng **trước `-jar`**.

### Bước 3 — đọc đúng quá trình JVM

```bash
jcmd -l
jcmd <pid> VM.native_memory summary
jcmd <pid> GC.heap_info
```

Các commands trên giúp xem object heap và native subsystem categories; **đừng gọi đây là chứng cứ đầy đủ của vị trí backing physical pages**.

### Bước 4 — đối chiếu OS mappings

Khi đã biết PID, trên Linux:

```bash
cat /proc/<pid>/maps
cat /proc/<pid>/smaps
pmap -x <pid>
```

`<pid>` là placeholder, cần thay bằng PID thật. Trong `maps`/`smaps`, đối chiếu mapping được backing bởi thiết bị/filesystem mong đợi, kích thước, permission flags và actual memory residency.

Nếu cần NUMA/device-level kiểm chứng, dùng công cụ mà **kernel/driver/device** tương ứng hỗ trợ. Không suy diễn địa chỉ ảo trong `maps` thành DRAM/PMEM physical address mà chưa xác minh.

**Đo đúng câu hỏi:** một lần nhìn thấy mapping file thiết bị chỉ là bước đầu; cần kiểm nó thực sự được JVM dùng làm **object heap** chứ không phải một mapping thư viện hoặc file khác.

### Bước 5 — kiểm dữ liệu app và hiệu năng

So sánh hai cấu hình:

- Baseline: heap backing bình thường trên runtime đó.
- Alternative: heap backing qua `-XX:AllocateHeapAt`.

Sử dụng **cùng JDK build, classpath, GC, heap settings và workload**. Đo startup, throughput, GC pause, tail latency, process DRAM usage và device telemetry. Đừng chỉ lấy thời gian của một lần `java -version` rồi kết luận về hiệu năng giao dịch.

## 21. Các lỗi cấu hình và giới hạn cần kiểm

### 21.1. JVM báo unrecognized option

```text
Unrecognized VM option 'AllocateHeapAt'
```

Có thể runtime/VM/platform không hỗ trợ. Kiểm implementation cụ thể (HotSpot hay JVM khác), JDK build, OS, architecture và version. **Không** tự xử lý bằng cách thêm một flag legacy được tìm thấy trên blog cũ.

### 21.2. Mount path không hợp lệ hoặc không writable

Điểm mount phải tồn tại, có quyền phù hợp và backing memory map theo hợp đồng; sai đường dẫn, readonly filesystem hoặc capacity thấp có thể khiến VM thất bại lúc startup hoặc cấp phát.

### 21.3. Chọn filesystem thường thay vì memory-class device

Một đường dẫn `/tmp/heap` trên disk thông thường không tự tạo **DRAM-equivalent alternative memory device**. Có thể JVM mmap file nhưng đó không đem lại đặc tính mà JEP 316 hướng đến.

Tránh đưa môi trường production vào một kiểu mapping chưa được xác minh correctness/latency/atomic operations; không mặc định tất cả block storage đều phù hợp.

### 21.4. Device đủ lớn nhưng DRAM vẫn không đủ

Object heap có thể sử dụng vùng thay thế, nhưng Metaspace, Code Cache, native thread stacks và VM allocations vẫn cần tài nguyên tương ứng. Có thể thấy lỗi `OutOfMemoryError: Metaspace` hoặc lỗi native allocations ngay khi heap còn nhiều dung lượng.

### 21.5. `-Xmx` quá nhỏ

`AllocateHeapAt` không gỡ bỏ giới hạn heap; nếu live Java object graph vượt mức tối đa, ứng dụng vẫn có thể nhận `OutOfMemoryError: Java heap space`.

### 21.6. Kiểm mỗi Java heap used

Heap used thấp không chứng minh code cache, metaspace, thread stacks hoặc direct memory thấp. Phải đo thêm native pools, OS RSS và device/cgroup accounting.

### 21.7. Dùng heap mapping làm nơi lưu dữ liệu bền

Một object heap được GC quản lý và có các con trỏ/runtime metadata. **Không** giả định có thể khởi động lại JVM rồi đọc lại object graph của process cũ như file database chỉ vì vùng nhớ vật lý có tính persistent. Muốn persistence, dùng database, file format/serialization hoặc engine thiết kế riêng.

### 21.8. Copy NMT reserved sang “DRAM used”

Reserved có thể lớn hơn committed/resident rất nhiều. Đừng cộng tổng virtual reservations rồi khẳng định lượng DRAM vật lý thiếu.

### 21.9. Gán ý nghĩa sai cho “all other memory structures remain DRAM”

Câu này mô tả **phạm vi của JEP 316**: không điều khiển các cấu trúc ngoài object heap. Nó **không** là tuyên bố rằng OS không bao giờ map shared files, NUMA allocations, device memory của thư viện hoặc stack chunks của virtual threads trong heap.

## 22. Bài toán ngân sách DRAM sau khi chuyển heap

Đối với một ứng dụng tải lớn, hãy tạo hai bảng budget riêng:

**A. Phần object heap backing ở alternative device**

- `-Xms` / `-Xmx` và maximum heap.
- GC overhead liên quan tới objects bên trong heap.
- Capacity/headroom của thiết bị, filesystem/mapping và allocation failure.
- Chênh lệch GC/heap latency khi dùng thiết bị thay thế.

**B. Phần DRAM/non-heap/native vẫn phải cấp phát**

- Class metadata và các cấu trúc Metaspace.
- JIT Code Cache và compiler internals.
- Platform thread stacks, native VM/service/GC threads.
- JNI/direct buffers và native allocations.
- OS mappings, libraries, page cache và process khác theo phạm vi quản trị.
- Ràng buộc cgroup/container hoặc OS overcommit/NUMA.

**Không dùng quy tắc `DRAM need = -Xmx × 0%`**. Muốn xác định DRAM tối thiểu, đo **committed/resident native-related memory trong workload thật**, cộng safety margin phù hợp, tránh trùng phạm vi đo.

### Một công thức kế hoạch, không phải phép đo OS

```text
Alternative-device capacity budget
    >= object heap max (theo mức hỗ trợ) + device-level margin

Separate DRAM/non-heap budget
    >= JIT + Metaspace + native stacks + GC/VM native
       + JNI/direct buffers + OS/shared mappings + safety margin
```

Đây là mô hình để tư duy. Một số cấp phát có thể dùng different OS policies và accounting hoặc nằm trong heap; phải tránh double-count và xác minh bằng số đo.

## 23. GC không thu gom toàn bộ bộ nhớ JVM

**Garbage Collector** chủ yếu quản lý vòng đời **Java objects và arrays** trên object heap.

Điều đó **không** có nghĩa GC không tham gia gián tiếp vào một số hoạt động class unloading hoặc cleanup các tài nguyên có wrapper Java. Tuy nhiên:

- GC không quản lý mọi `malloc` trong JNI như `new Object()`.
- Code Cache có cơ chế quản lý compiled methods/code sweeper.
- Metaspace gắn với vòng đời class loaders/class unloading.
- Native thread stacks được cấp phát/giải phóng theo vòng đời platform threads.
- Direct memory có cơ chế cleanup riêng, có thể liên quan reference processing nhưng không thuộc giới hạn object heap.

Vì vậy gọi `System.gc()` không phải chiến lược sửa lỗi “DRAM còn đầy dù heap đã sang PMEM”. Có thể cần sửa leak native, hạn chế thread count, direct buffers hoặc classloader retention.

### Những lỗi OOME khác nhau

| Lỗi/triệu chứng | Khả năng liên quan | Có thể sửa chỉ bằng tăng `-Xmx` không? |
| --- | --- | --- |
| `OutOfMemoryError: Java heap space` | Object heap không đủ | Có thể nếu live-set hợp lý và thiết bị/cgroup đủ, nhưng cần điều tra |
| `OutOfMemoryError: Metaspace` | Class metadata | **Không trực tiếp** |
| `OutOfMemoryError: Direct buffer memory` | Native/direct buffers | **Không trực tiếp** |
| `OutOfMemoryError: unable to create native thread` | Native stacks/resources/OS limits | **Không trực tiếp** |
| JVM fatal native allocation failure | C/C++ allocator hoặc OS | **Không trực tiếp** |
| Kernel OOM-kill container/process | Tổng memory charges/OS policy | **Không trực tiếp**, tăng heap có thể làm nặng hơn |

Không nên xem mọi OOME như cùng một lý do. Đọc thông báo cụ thể, logs và metrics.

## 24. Những nhầm lẫn rất thường gặp

### Nhầm 1 — “JEP 316 đưa toàn bộ JVM sang bộ nhớ phi DRAM”

Sai: chỉ object heap; Metaspace, code heap, stacks và nhiều native allocations vẫn riêng.

### Nhầm 2 — “Metaspace là một thư mục của heap thay thế”

Sai: Metaspace là non-heap metadata memory region được HotSpot quản lý riêng.

### Nhầm 3 — “Đã chuyển heap thì Code Cache cũng sang theo”

Sai: machine code JIT được lưu trong code cache/code heaps riêng.

### Nhầm 4 — “Dùng PMEM có nghĩa class metadata persisted sau reboot”

Không. Metadata thuộc runtime process và được thiết kế theo vòng đời JVM, không phải database persistence.

### Nhầm 5 — “Thread stacks đều biến thành Java heap objects”

Không với native stacks của platform threads. Virtual threads hiện đại có stack chunks trên heap; phải phân biệt loại thread.

### Nhầm 6 — “Một direct buffer là một byte array Java”

Không. Payload của direct buffer thường ở native memory, wrapper là Java object.

### Nhầm 7 — “`-Xmx` cho biết lượng RAM DRAM tối đa của JVM”

Không. `-Xmx` giới hạn **object heap**, native/non-heap và OS mappings còn dùng memory riêng.

### Nhầm 8 — “Thấy non-heap thấp trong JMX nghĩa là toàn native memory thấp”

Không. MemoryMXBean không bao trùm mọi native/JNI allocations.

### Nhầm 9 — “`jcmd VM.native_memory` liệt kê tất cả native bytes của mọi thư viện”

Không. NMT theo dõi JVM allocations trong phạm vi của nó, không phải mọi third-party native allocator.

### Nhầm 10 — “Reserved bằng lượng RAM vật lý đang dùng”

Không. Reserved thường chỉ là virtual address space; committed/resident là các khái niệm khác.

### Nhầm 11 — “Đường dẫn `/tmp` bình thường chắc chắn là NV-DIMM”

Không. Cần kiểm hardware, filesystem, mount và semantics.

### Nhầm 12 — “PMEM lớn hơn nên hiệu năng Java chắc chắn tốt hơn”

Không. Latency/bandwidth/NUMA/GC and workload có thể khác; cần benchmark.

### Nhầm 13 — “GC có thể thu hồi code cache, Metaspace, JNI giống object heap”

Không. Các subsystem có cơ chế quản lý riêng và một số hành động phụ thuộc lifecycle/cleanup.

### Nhầm 14 — “`MemoryPoolMXBean` cho biết địa chỉ DIMM vật lý”

Không. Nó là API quản lý logical JVM pools.

### Nhầm 15 — “Nếu không có thiết bị PMEM thì không thể học gì về vùng JVM riêng”

Không. Có thể dùng `MemoryPoolMXBean`, `MemoryMXBean` và `BufferPoolMXBean` để quan sát ranh giới, nhưng không thể chứng minh device placement.

### Nhầm 16 — “Tất cả các flag JDK 10 chạy giống hệt trên JDK 26 và mọi OS”

Không. Phải kiểm tài liệu JDK build và platform; riêng `AllocateHeapAt` vẫn được mô tả hiện hành nhưng có giới hạn môi trường.

## 25. Quy trình vận hành khi cần dùng alternative heap thực

1. **Nêu lý do:** cần mở rộng capacity object heap, tối ưu cost/DRAM hay có bài toán dữ liệu tương ứng?
2. **Đối chiếu HotSpot/JDK:** build, OS/architecture và GC strategy hỗ trợ.
3. **Xác minh thiết bị:** memory semantics tương đương DRAM, atomic operations, mapping và filesystem.
4. **Đảm bảo quyền:** mount path, read/write/execute theo security policy, device resource limits.
5. **Chạy baseline:** không có `-XX:AllocateHeapAt`, ghi startup/throughput/GC/heap/native.
6. **Chạy alternative:** có `-XX:AllocateHeapAt` với cùng mức `-Xms`/`-Xmx` và workload.
7. **Xác minh mapping:** OS files `maps`/`smaps`/`pmap` cùng mount/device information.
8. **Đo Java heap:** GC logs, `MemoryMXBean`, peak memory.
9. **Đo Metaspace/Code Cache:** `MemoryPoolMXBean`, NMT `Class`/`Code`.
10. **Đo stacks/native:** thread count, NMT `Thread`/`Internal`, OS RSS.
11. **Đo direct/JNI:** BufferPoolMXBean, library-native profiling khi cần.
12. **Kiểm giới hạn:** device capacity, cgroups, host RAM, process virtual address space.
13. **Đo khi đột biến:** class loading burst, many threads, JNI buffers, GC pressure.
14. **Xem SLA:** p95/p99 latency, throughput, GC tail pauses; không đo một lần rồi kết luận.
15. **Chuẩn bị rollback:** khi thiết bị không sẵn có hoặc performance không đủ.
16. **Theo dõi security/data sanitization:** memory persistence của thiết bị không đồng nghĩa data format bền vững.
17. **Tái kiểm tra mỗi lần nâng JDK/OS/hardware** vì JVM flags advanced không phải Java SE API portable.
18. **Ghi lại quyết định trong runbook**: lý do chọn heap device, flags, yêu cầu native DRAM.

## 26. Bài tập tự kiểm tra

**Câu 1.** `-XX:AllocateHeapAt` được thiết kế để di chuyển khu vực nào của HotSpot?

**Câu 2.** Metaspace có theo object heap sang alternative memory device không?

**Câu 3.** JIT code cache nằm trong Java object heap hay được cấp phát riêng?

**Câu 4.** `-Xmx512m` có phải hard limit cho toàn tiến trình HotSpot không?

**Câu 5.** Native platform-thread stacks có tự chuyển sang alternative heap device không?

**Câu 6.** Nếu dùng virtual threads trên Java 21+, tại sao câu “mọi stack frame ngoài Java heap” không còn chính xác?

**Câu 7.** `new byte[4096]` khác `ByteBuffer.allocateDirect(4096)` ở đâu?

**Câu 8.** `BufferPoolMXBean` cho biết một direct buffer nằm ở DIMM vật lý nào không?

**Câu 9.** `ManagementFactory.getMemoryPoolMXBeans()` cung cấp thông tin gì?

**Câu 10.** Có thể coi `getNonHeapMemoryUsage()` là tổng RSS của mọi JNI libraries không?

**Câu 11.** Nếu app nhận `OutOfMemoryError: Metaspace`, tăng `-Xmx` có trực tiếp giải quyết không?

**Câu 12.** Native Memory Tracking báo `reserved` có phải RAM đã dùng vật lý không?

**Câu 13.** Một device hỗ trợ mmap nhưng không bảo đảm atomic semantics như DRAM có phù hợp với mục tiêu JEP 316 không?

**Câu 14.** JEP 316 có bảo đảm Java objects sau khi JVM kết thúc vẫn được khôi phục từ PMEM không?

**Câu 15.** Cần kiểm gì để xác nhận heap thực sự đang map tới đúng thiết bị?

**Câu 16.** Vì sao không thể tuyên bố “DRAM usage = 0” sau khi chuyển heap?

**Câu 17.** Các flag `-Xms`, `-Xmx` và GC flags còn có ý nghĩa không?

**Câu 18.** Trong budget giả định 512 + 80 + 64 + 48 + 40 + 100 MiB, tổng và khoản ngoài heap là bao nhiêu?

**Câu 19.** Vì sao cộng NMT reserved vào RSS tạo báo cáo sai?

**Câu 20.** `-XX:AllocateHeapAt` có ảnh hưởng trực tiếp tới `malloc` bên trong mọi native library không?

**Câu 21.** JVM có thể hết native memory dù alternative device còn heap trống không?

**Câu 22.** Có nên so hiệu năng bằng workload/JDK/GC khác nhau giữa baseline và alternative không?

**Câu 23.** `MemoryPoolMXBean` là logical classification hay hardware-placement API?

**Câu 24.** Khi không có NV-DIMM, chương trình Java 17+ của bài chứng minh được điều gì?

**Đáp án:**

1. **Java object heap**; không tự động di chuyển toàn process.
2. Không. Metaspace vẫn được cấp phát riêng.
3. Code Cache/code heaps riêng, không nằm trong Java object heap.
4. Không. Nó đặt maximum object heap, native/non-heap khác.
5. Không. Native stacks của platform threads là cấp phát riêng.
6. Virtual threads có thể lưu stack chunks trên Java heap, không mỗi thread một native OS stack.
7. `byte[]` là object heap; direct buffer payload thường native/off-heap.
8. Không; nó là management accounting, không phải hardware mapping.
9. Logical heap/non-heap pools, type và usage theo API.
10. Không; nhiều JNI allocations không được MXBean này bao trùm.
11. Không trực tiếp; cần kiểm class metadata/classloader, metaspace sizing.
12. Không; reserved là virtual address reservation.
13. Không; thiết bị mục tiêu cần memory/atomic semantics như DRAM.
14. Không. Java heap không trở thành persistent database.
15. OS mappings/mount/device information cộng heap/JVM logs và đúng process.
16. Code Cache, Metaspace, native stacks, GC/JNI và runtime khác vẫn cần memory.
17. Có; heap sizing và GC options vẫn có hiệu lực theo hỗ trợ của JVM.
18. Tổng **844 MiB**, ngoài object heap **332 MiB**.
19. Hai số thuộc scope/định nghĩa khác nhau và có thể overlap.
20. Không. Native code có allocator riêng.
21. Có. Native resource exhaustion độc lập với heap capacity.
22. Không; cần baseline và alternative đủ tương đồng để so sánh.
23. Logical memory pools của JVM.
24. Phân loại heap/non-heap và direct memory monitoring; **không chứng minh placement ở device**.

## 27. Tóm tắt cuối bài

- **JEP 316 / Java 10** cho phép HotSpot ánh xạ **Java object heap** tới alternative memory device với DRAM-equivalent semantics qua `-XX:AllocateHeapAt=path`.
- **Oracle Java SE 26 vẫn tài liệu hóa option này**, nên đây là kiến thức còn áp dụng ở runtime hiện hành khi thiết bị và platform hỗ trợ.
- **Chỉ Java object heap được chuyển theo flag.** Metaspace, JIT Code Cache, native platform-thread stacks và VM native allocations **vẫn được cấp phát riêng**.
- **Tên “code heap” hoặc “native heap” không phải Java object heap.**
- **Direct-buffer payload** và JNI/native memory không tự động chuyển theo flag.
- **Virtual threads** là ngoại lệ cần hiểu trong Java hiện đại: stack chunks của chúng có thể ở object heap, khác native stacks của platform threads.
- `-Xms`/`-Xmx` và GC flags vẫn điều chỉnh heap/collector; chúng không giới hạn toàn native memory.
- **NMT, MemoryMXBean, BufferPoolMXBean** là các công cụ quan sát logical JVM subsystems; **OS mappings** mới là một phần chứng cứ về vị trí backing device.
- **Reserved ≠ committed ≠ used ≠ RSS**; không cộng trùng hoặc gán chúng cho vị trí vật lý sai.
- **OOM và latency** cần kiểm cả object heap và các nguồn native/non-heap.
- Cấu hình alternative heap chỉ nên áp dụng khi có thiết bị phù hợp, workload thực tế, kiểm chứng correctness, benchmark và vận hành an toàn.

## 28. Tài liệu tham khảo chính thức, còn áp dụng

1. [Oracle Java SE 26 — The java Command, `-XX:AllocateHeapAt`](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html#advanced-runtime-options-for-java): option còn hỗ trợ theo tài liệu HotSpot, object heap ánh xạ vào alternative memory, **code heap/Metaspace/thread stacks tiếp tục ở DRAM**.
2. [OpenJDK JEP 316 — Heap Allocation on Alternative Memory Devices](https://openjdk.org/jeps/316): cơ sở kỹ thuật của tính năng Java 10.
3. [Oracle Java SE 26 — MemoryMXBean](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MemoryMXBean.html): ý nghĩa heap/non-heap của JVM.
4. [Oracle Java SE 26 — MemoryPoolMXBean](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html): quản lý memory pools/`MemoryType`, logical không phải physical placement.
5. [Oracle Java SE 26 — MemoryUsage](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MemoryUsage.html): `init`, `used`, `committed`, `max`.
6. [Oracle Java SE 26 — BufferPoolMXBean](https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): direct/mapped pools theo VM.
7. [Oracle Java SE 26 — The jcmd Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html): `VM.native_memory summary`/`summary.diff` và `GC.heap_info`.
8. [Oracle Java — Native Memory Tracking](https://docs.oracle.com/en/java/javase/26/vm/native-memory-tracking.html): NMT phạm vi theo dõi, cách cấu hình và giới hạn native memory.
9. [Oracle Java SE 26 — Virtual Threads](https://docs.oracle.com/en/java/javase/26/core/virtual-threads.html): platform vs virtual threads.
10. [OpenJDK JEP 444 — Virtual Threads](https://openjdk.org/jeps/444): model carrier threads/stack chunks của virtual threads.
11. [Oracle Java SE 26 — Troubleshooting Guide](https://docs.oracle.com/en/java/javase/26/troubleshoot/): OOME, native-memory issues và diagnostics.
12. [Oracle JVM Performance — Introduction to Memory Pools](https://ops.java/performance/jvm/articles/memory-pools/): tách Java Heap, Metaspace, Code Cache và native memory.
