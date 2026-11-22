# Giới hạn Metaspace, direct memory và code cache theo nhu cầu quan sát

## 1. Vì sao cấu hình ba vùng nhớ này không thể dựa vào một con số chung?

Trong **HotSpot JVM**, `-Xmx` chỉ giới hạn **Java heap**, không phải toàn bộ bộ nhớ mà tiến trình Java có thể sử dụng. Ngoài heap còn có class metadata, các buffer cấp phát ngoài heap, JIT-generated code, stacks của threads, GC structures, JNI/native libraries và các nguồn tiêu thụ bộ nhớ khác.

Ba nhóm thường cần quan sát và cân nhắc giới hạn là:

1. **Metaspace:** nơi HotSpot lưu class metadata; bị tác động bởi số classes, class loaders và cơ chế unload.
2. **Direct memory:** trong phạm vi cờ `-XX:MaxDirectMemorySize`, phần cấp phát **NIO direct buffers** của HotSpot; không đồng nghĩa toàn bộ native memory.
3. **Code cache:** vùng lưu generated native code/JIT compiled methods và một số runtime code của HotSpot; có thể bị áp lực khi ứng dụng có nhiều hot methods.

Mỗi vùng có **cách tăng trưởng, chỉ số quan sát, giới hạn và biểu hiện lỗi riêng**. Đặt `MaxMetaspaceSize=128m`, `MaxDirectMemorySize=128m` và `ReservedCodeCacheSize=128m` **không làm “bộ nhớ JVM ngoài heap” tự đúng bằng 384 MiB**, cũng không có nghĩa tổng RSS của Java process được bảo đảm dưới `Xmx + 384 MiB`.

```text
                   Java process address space
    +------------------------------------------------------+
    | Java heap (-Xms, -Xmx)                               |
    |   objects, arrays, direct buffer wrapper objects      |
    +------------------------------------------------------+
    | Metaspace / class metadata                            |
    |   classes, methods, class loader lifecycles           |
    +------------------------------------------------------+
    | Direct NIO buffer backing storage (off-heap/native)   |
    +------------------------------------------------------+
    | Code cache (generated JIT/native runtime code)        |
    +------------------------------------------------------+
    | Java thread stacks, GC structures, VM internal memory |
    | JNI / third-party native allocations, mapped files... |
    +------------------------------------------------------+

             Tổng process memory != -Xmx
             Ba giới hạn không thay thế native RAM budget.
```

### Mục tiêu của bài

- Hiểu **Metaspace**, **direct buffers** và **code cache** lưu gì, không lưu gì.
- Phân biệt **reserved / committed / used / resident**.
- Dùng đúng các cờ HotSpot `MaxMetaspaceSize`, `MaxDirectMemorySize`, `ReservedCodeCacheSize` và tùy chọn liên quan.
- Biết cách quan sát qua `jcmd`, **Native Memory Tracking (NMT)**, **MXBeans**, logs và OS/container metrics.
- Phân tích riêng **Metaspace OOME**, **direct buffer OOME**, **code cache full/JIT disabled**.
- Chọn giới hạn **từ số liệu có tải đại diện**, chừa headroom cho sự biến động và tránh bóp nghẹt VM.
- Thực hành một chương trình **Java 17+** biên dịch được và có stdout ổn định cho phần logic.

**Phạm vi:** bài này ưu tiên **HotSpot JDK 17+**, không khẳng định tên/cờ/pool của HotSpot là API bắt buộc của mọi JVM implementation.

## 2. Bản đồ ngắn: các vùng, cờ giới hạn và tín hiệu chẩn đoán

| Vùng / nguồn | Bản chất | Giới hạn HotSpot | Chỉ số hữu ích | Triệu chứng nổi bật |
| --- | --- | --- | --- | --- |
| **Java heap** | Object/array runtime | `-Xmx` | Heap used/committed, GC, live-set | `OutOfMemoryError: Java heap space` |
| **Metaspace** | Class metadata | `-XX:MaxMetaspaceSize` | Metaspace used/committed, class count, loader count | `OutOfMemoryError: Metaspace` |
| **Compressed Class Space** | Phần metadata liên quan compressed class pointers | `-XX:CompressedClassSpaceSize` | Class-space used/committed/reserved | `OutOfMemoryError: Compressed class space` |
| **NIO direct buffers** | Backing memory thường nằm ngoài heap | `-XX:MaxDirectMemorySize` | BufferPoolMXBean direct count/capacity/memoryUsed | `OutOfMemoryError` khi không reserve được buffer memory |
| **Code cache** | JIT code và runtime code blobs | `-XX:ReservedCodeCacheSize` | `Compiler.codecache`, CodeHeap/CodeCache MXBeans, codecache logs | Warning code cache full, compilation có thể bị ảnh hưởng |
| **Threads** | Native/JVM stacks và structures | `-Xss` và OS limits, số threads | thread count, NMT Thread, OS | `unable to create native thread` / process resource failures |
| **Native libraries / JNI** | C/C++/OS allocations | Không bị ba cờ trên giới hạn chung | OS RSS/maps, native profilers | Native OOM, process killed/crash |
| **Mapped files** | Memory mappings như `MappedByteBuffer` | Không phải cùng budget với plain direct allocations | mapped buffer pool, OS maps | Mapping/OS resource failures |

**Đừng dùng một “max memory” cho tất cả.** Từng giới hạn bảo vệ một loại áp lực nhất định và có thể kích hoạt cơ chế thất bại khác nhau.

## 3. Reserved, committed, used và RSS không phải cùng số

Khi xem NMT, MXBeans, logs và OS tools, thường gặp:

- **Reserved:** phần **virtual address space** được VM giữ/đặt trước để có thể sử dụng. **Không đồng nghĩa** chừng ấy bytes đang nằm trong RAM vật lý.
- **Committed:** phần memory mà VM đã yêu cầu/cấp phát backing khả dụng theo mô hình quản lý của VM/OS. Không thể chuyển thành RSS bằng một phép bằng đơn giản.
- **Used:** phần đã cấp cho metadata/code/buffer theo định nghĩa của pool. Có thể nhỏ hơn committed vì chunks/free space/fragmentation.
- **Resident Set Size (RSS):** lượng physical pages đang resident và được tính vào process theo công cụ OS; có thể bao gồm shared mapped pages, không thể tự suy từ VM used.
- **PSS (Proportional Set Size):** trên hệ hỗ trợ, chia tỷ lệ shared pages giữa các processes, hữu ích khi tổng memory footprint quan trọng.
- **Virtual size/address space:** không phải lượng RAM thực dùng.

Ví dụ một output dạng:

```text
Class: reserved=112MB, committed=1MB
Metaspace: used=900KB
Code: reserved=64MB, committed=3MB
```

Đây là **mẫu minh họa định dạng/đơn vị**, không phải trạng thái mặc định của mọi máy. **Không được cộng 112 MB reserved Class + 64 MB reserved Code rồi kết luận có 176 MB physical memory đã tiêu thụ.**

### 3.1. Vì sao Metaspace có reserved lớn nhưng committed nhỏ?

HotSpot có thể reserve virtual address ranges để cấp phát metadata về sau, trong khi chỉ commit phần nhỏ đang cần. JEP 387 (*Elastic Metaspace*) cải tiến cách trả lại memory đã commit mà không còn cần thiết, tùy loader lifecycle và fragmentation.

### 3.2. Vì sao CodeCache pool max không giống used?

Code cache thường reserve capacity cho future compiled code; số byte đã dùng phụ thuộc compilation workload. Đặt một maximum không đồng nghĩa JVM commit toàn bộ maximum ngay khi start.

### 3.3. Không dùng ba giới hạn để tính container memory tuyệt đối

Một container có thể bị OOMKilled vì tổng RSS/cgroup charge tăng do heap, native memory, page cache, thread stacks, heap/metaspace committed và workloads đồng thời. Cgroup accounting và host policies có thể khác; cần quan sát **container memory metrics thực tế**, không chỉ các số max VM.

## 4. Metaspace là gì?

**Metaspace** là hệ thống native-memory management mà HotSpot dùng để lưu **metadata của classes** từ JDK 8 trở đi, thay thế Permanent Generation (PermGen) từng tồn tại trong HotSpot cũ.

Nội dung có thể gồm metadata về:

- Runtime classes/interfaces.
- Methods/fields/signatures.
- Runtime constant pools và các cấu trúc class liên quan.
- Class loader–scoped metadata allocations.

**Không** nhầm với heap objects của ứng dụng: một `new Customer()` thông thường nằm ở Java heap về mặt runtime, còn metadata mô tả class `Customer` được HotSpot quản lý qua các cấu trúc metadata.

### 4.1. Metaspace thuộc native memory, không bị `-Xmx` trực tiếp giới hạn

Ví dụ:

```bash
java -Xmx256m -XX:MaxMetaspaceSize=192m MyApplication
```

`MyApplication` là placeholder class ứng dụng. `-Xmx256m` không khiến Metaspace tự phải nằm trong 256 MiB heap đó; giới hạn 192 MiB là một cấu hình **riêng** cho class metadata.

### 4.2. Vì sao Metaspace tăng?

Một số nguồn:

- Nạp thêm application classes.
- Frameworks/proxies/bytecode generation tạo thêm classes.
- Nhiều class loader instances giữ những bộ class metadata riêng.
- Hot redeploy/plugin architectures tạo class loaders mới mà loaders cũ chưa collectible.
- Class initialization và reflection có thể kéo theo nhiều classes được nạp.

**Số classes đang sống và loaders còn reachable** có ý nghĩa lớn. Metaspace growth không mặc nhiên là memory leak: ứng dụng có thể vẫn đang warm paths hoặc preload các modules đúng thiết kế.

### 4.3. Class unloading và Metaspace reclamation

HotSpot có thể reclaim metadata khi classes/loaders tương ứng đủ điều kiện unload, dựa trên GC và runtime reachability. Nếu application vô tình giữ reference tới class loader cũ qua static registries, threads, caches hoặc ThreadContextClassLoader, nó có thể **ngăn class unloading**, khiến Metaspace tăng lâu dài.

Không giải quyết class-loader leak chỉ bằng tăng `MaxMetaspaceSize`; cần tìm nguyên nhân giữ loaders.

## 5. `-XX:MaxMetaspaceSize`: giới hạn đúng phạm vi

Cờ:

```bash
-XX:MaxMetaspaceSize=192m
```

giới hạn lượng memory class metadata mà HotSpot có thể sử dụng/commit theo accounting của Metaspace. Nếu chạm giới hạn mà không thể thu hồi/reclaim đủ, JVM có thể báo:

```text
java.lang.OutOfMemoryError: Metaspace
```

Oracle JDK 17 mô tả rằng mặc định **MaxMetaspaceSize không có upper bound do cờ này đặt**, nhưng vẫn bị giới hạn bởi address space/OS/container resources.

### 5.1. `MaxMetaspaceSize` không phải dung lượng đã commit khi start

`MaxMetaspaceSize=192m` là **cap**, không là lệnh JVM cấp phát/commit sẵn 192 MiB native memory ở startup.

### 5.2. `-XX:MetaspaceSize` khác `MaxMetaspaceSize`

`MetaspaceSize` là một **initial threshold/GC trigger liên quan metadata usage**, không phải lượng RAM initial commit mà người dùng có thể cộng thẳng vào RSS, cũng không phải một maximum.

Ví dụ:

```bash
java -XX:MetaspaceSize=32m -XX:MaxMetaspaceSize=192m MyApplication
```

Không diễn giải “Metaspace luôn dùng 32 MiB, không thể thấp hơn hoặc cao hơn trước GC”. Threshold được HotSpot điều chỉnh theo policy.

### 5.3. Đặt cap quá thấp gây hại gì?

- Class loading/verification/metadata allocation có thể thất bại.
- GC/class unloading bị gọi dồn dập nhằm reclaim Metaspace.
- Frameworks/proxies/plugins không thể nạp classes cần thiết.
- Startup hoặc một feature hiếm dùng có thể vỡ muộn trong production.

Một cấu hình chỉ đủ lúc **service vừa lên** không chắc đủ khi traffic kích hoạt thêm classes sau vài giờ.

### 5.4. Có nên đặt cap rất lớn để tránh OOME?

Giới hạn quá lớn có thể làm vấn đề class-loader leak khó nhận diện sớm và tạo rủi ro vượt memory limit của container. Cap cần dựa vào **peak class metadata dùng thực tế**, kịch bản deploy/plugin/lazy loading và headroom.

## 6. Compressed Class Space khác phần non-class Metaspace

Với compressed class pointers trên HotSpot 64-bit, class metadata có thể được chia thành nhóm:

- **Class space:** phần cho class pointer-related metadata.
- **Non-class Metaspace:** metadata khác.

Cờ:

```bash
-XX:CompressedClassSpaceSize=128m
```

điều chỉnh giới hạn vùng **compressed class space** khi tính năng tương ứng hoạt động. Nếu hết phần này, có thể gặp:

```text
java.lang.OutOfMemoryError: Compressed class space
```

**Không nhầm CompressedClassSpaceSize với MaxMetaspaceSize**. Hai giá trị ảnh hưởng các cơ chế giới hạn khác nhau; khi giới hạn cả hai, cần hiểu mối quan hệ account tổng metadata và các vùng con theo JDK.

### 6.1. Reserved class space có thể lớn

Ở một số HotSpot builds, compressed class space mặc định reserve virtual memory khá lớn (ví dụ 1 GiB); **virtual reservation không phải 1 GiB RAM vật lý đã commit**.

### 6.2. Đặt class space lớn hơn không tự cứu non-class Metaspace

Nếu non-class metadata mới là nguồn áp lực, tăng chỉ `CompressedClassSpaceSize` không giải quyết. Phải xem NMT Class, `VM.metaspace` và MemoryPoolMXBean tương ứng.

### 6.3. Quan hệ giới hạn trên JDK cụ thể cần kiểm tra

HotSpot có thể chuẩn hóa/điều chỉnh các flags kết hợp, ví dụ khi `MaxMetaspaceSize` nhỏ hơn compressed class space default. Hãy xem **`java -XX:+PrintFlagsFinal -version`**, không giả định đúng y nguyên các số bạn không kiểm tra.

## 7. Direct memory: chính xác là gì?

**Direct `ByteBuffer`** là một NIO buffer có backing storage được JVM cấp phát ngoài Java heap thông thường trên HotSpot. Một **Java wrapper object** vẫn tồn tại ở Java heap, nhưng phần data bytes của direct buffer thường nằm trong off-heap/native memory.

Ví dụ:

```java
java.nio.ByteBuffer b =
        java.nio.ByteBuffer.allocateDirect(1024 * 1024);
b.putInt(0, 42);
```

Đây là snippet có thể đặt trong method; nó cấp một direct buffer dung lượng 1 MiB, sau đó ghi integer tại offset 0.

### 7.1. Direct buffer khác heap buffer

```java
java.nio.ByteBuffer heapBuffer =
        java.nio.ByteBuffer.allocate(1024 * 1024);
java.nio.ByteBuffer directBuffer =
        java.nio.ByteBuffer.allocateDirect(1024 * 1024);
```

- `allocate` thường dùng mảng Java heap làm backing.
- `allocateDirect` dùng native/off-heap backing storage trong HotSpot.
- Cả hai vẫn có Java-level object metadata/wrapper.
- Direct buffer có thể giảm copy overhead trong một số native I/O paths, nhưng allocate/free có thể đắt hơn; không phải mọi workload nhanh hơn.

### 7.2. Direct buffer memory không phải toàn bộ native memory

Native memory của một process còn gồm:

- JNI libraries và native malloc.
- VM internal arenas.
- Thread stacks.
- Code cache.
- Metaspace.
- Mapped files, filesystem mappings.
- Native memory do thư viện ngoài Java quản lý.

**`MaxDirectMemorySize` không đặt global cap cho những nguồn trên.**

### 7.3. MappedByteBuffer không thể gộp vô điều kiện với direct buffers

`FileChannel.map` tạo mapped byte buffers, liên quan memory-mapped files và OS VM mappings. MXBeans thường có pool **`mapped`** riêng. Không suy rằng mọi mmap bytes đều thuộc cùng accounting với `MaxDirectMemorySize`.

## 8. `-XX:MaxDirectMemorySize`: giới hạn NIO direct buffers

Cờ HotSpot:

```bash
-XX:MaxDirectMemorySize=64m
```

đặt maximum cho **direct-buffer allocations thuộc accounting của java.nio/HotSpot**. Theo tài liệu `java` JDK 17, nếu không đặt rõ, VM chọn kích thước phù hợp; trường `MaxDirectMemorySize=0` khi in flags thường có thể biểu thị **ergonomic/default handling**, không phải “Java được phép cấp đúng 0 bytes direct memory”.

### 8.1. Ví dụ cấu hình an toàn cho chương trình demo

```bash
java -Xmx128m -XX:MaxDirectMemorySize=16m MemoryBudgetDemo
```

Demo cấp một direct buffer 1 MiB, dưới limit 16 MiB trong môi trường bình thường.

### 8.2. Khi chạm giới hạn

Một chương trình giữ nhiều direct buffers lớn có thể nhận `OutOfMemoryError` với thông báo liên quan không thể reserve/thêm **direct buffer memory**, ví dụ dạng:

```text
java.lang.OutOfMemoryError: Cannot reserve ... bytes of direct buffer memory
```

**Thông báo chính xác** phụ thuộc JDK; không nhất thiết là chính xác “Direct buffer memory” trên mọi release. Các lỗi OS/native allocator cũng có thể xảy ra mà không liên quan trực tiếp đến cap này.

### 8.3. Tại sao tăng `-Xmx` đôi khi không giải quyết direct OOME?

`-Xmx` giới hạn Java heap, còn direct buffer backing storage sử dụng memory bên ngoài heap. Một heap còn free vẫn có thể gặp direct allocation failure khi `MaxDirectMemorySize` hoặc OS/container resource cạn.

### 8.4. GC và lifetime của direct buffer

HotSpot direct buffers được quản lý thông qua Java object reachability và cơ chế cleanup phù hợp (như Cleaner). **Việc bỏ reference không đảm bảo native memory giải phóng ngay tại dòng code tiếp theo**.

Cần phân biệt:

- Buffer vẫn được ứng dụng/caches giữ reference: native memory **còn được sử dụng hợp lệ hoặc bị leak reference**.
- Buffer không còn reachable nhưng cleanup/GC chưa xảy ra: allocation pressure có thể tăng tạm thời.
- Native allocations từ JNI/Unsafe libraries: có lifecycle và công cụ chẩn đoán riêng, không mặc nhiên dùng direct-buffer cleaner.

### 8.5. Pool capacity khác memoryUsed

`BufferPoolMXBean.getTotalCapacity()` báo **ước tính tổng capacity** của buffers trong pool. `getMemoryUsed()` báo **ước tính bytes memory VM đang dùng** và có thể khác capacity vì allocation/alignment/overhead, hoặc trả -1 nếu không có estimate.

Đừng sử dụng hai số này như một guaranteed exact native-address accounting.

## 9. Code cache: nơi JVM lưu compiled code

**HotSpot code cache** là vùng memory runtime chứa compiled code **nmethods** được JIT tạo và một số non-method runtime code/stubs/adapters.

Khi code mới đủ hot:

```text
Java bytecode
     |
 interpreter / runtime profiling
     |
 JIT compiler C1/C2
     |
 machine code + runtime metadata
     |
 CODE CACHE
     |
 JVM chạy optimized native code nếu phù hợp
```

Code cache **khác Java heap**, **khác Metaspace** và **khác direct buffer backing storage**.

### 9.1. Vì sao code cache tăng?

- Nhiều methods/loops hot được JIT compile.
- Framework code và thư viện được tải theo nhu cầu.
- Inlining/optimization biến method code size khác đi.
- Deoptimization và recompilation có thể tạo version compiled mới.
- Method adapters/runtime stubs cũng sử dụng code-cache space.

JIT có thể reclaim/mark nmethods và sweeper có thể làm việc, nhưng việc reclaim phụ thuộc runtime state; không phải lúc nào old code được trả ngay.

### 9.2. Code cache đầy là vấn đề gì?

Khi code cache không còn đủ chỗ cho compilation code phù hợp, JVM có thể ghi warnings như:

```text
CodeCache is full. Compiler has been disabled.
```

Đó là **một mẫu thông báo HotSpot**, không phải một fatal Java exception bắt buộc. Khi không thể compile thêm, Java application có thể vẫn tiếp tục chạy, nhưng latency/throughput có thể giảm hoặc compilation bị dừng/khôi phục theo implementation/version.

**Không suy mọi code cache full đều ném `OutOfMemoryError: Java heap space`.** Đây là vùng khác và có cơ chế thất bại khác.

### 9.3. Code cache không phải CDS archive

CDS giúp reuse metadata lớp giữa các JVM processes. Code cache chứa generated code/runtime blobs riêng cho process, không tự được chia sẻ qua default AppCDS `.jsa`.

## 10. `-XX:ReservedCodeCacheSize` và segmented code cache

Cờ:

```bash
-XX:ReservedCodeCacheSize=128m
```

đặt maximum **reserved code cache size** mà JVM dùng cho compiled/runtime code cache theo HotSpot. Tài liệu Oracle JDK 17 ghi mức mặc định thường **240 MiB** khi tiered compilation; không mặc định rằng mọi release/config luôn có cùng con số. Khi tắt tiered compilation, default có thể nhỏ hơn.

### 10.1. Từ “reserved” không có nghĩa toàn bộ committed

Một JVM có thể reserve 128 MiB virtual code cache nhưng mới commit/vận hành vài MiB. `Compiler.codecache` và NMT Code giúp phân biệt.

### 10.2. Segmented Code Cache (HotSpot)

Khi enabled, code cache có thể chia các vùng:

- **Non-nmethod heap:** runtime stubs/adapters và code không gắn trực tiếp với compiled Java method.
- **Profiled nmethods heap:** C1 compiled code ở những profiling tiers.
- **Non-profiled nmethods heap:** C2/compiled code ít profiling.
  
Với một số cấu hình khác, JVM có thể không chia ba segments mà báo một pool **`CodeCache`**. Vì vậy khi đọc MXBeans:

```text
CodeHeap 'non-nmethods'
CodeHeap 'profiled nmethods'
CodeHeap 'non-profiled nmethods'
```

hoặc:

```text
CodeCache
```

đều có thể là output hợp lệ tùy HotSpot options/build. **Không hardcode test rằng phải luôn có đúng ba CodeHeap pools.**

### 10.3. `SegmentedCodeCache` và ngưỡng

Tài liệu HotSpot nêu segmentation được bật theo tiered compilation và code cache size policy (JDK 17 thường từ một ngưỡng nhất định, ví dụ 240 MiB). Khi giảm `ReservedCodeCacheSize` tới 64 MiB, output có thể đổi thành một **`CodeCache`** không segmented.

### 10.4. Đặt cache quá nhỏ

Một limit quá thấp có thể:

- Làm code cache đầy trong startup/steady workload.
- Giới hạn JIT compilations và nmethod replacements.
- Tăng rủi ro latency/throughput regressions.
- Làm runtime phải quản lý code cache quá gắt.

**Không khuyên hạ code cache để tiết kiệm virtual reserved pages mà chưa có OS RSS/PSS và code-cache usage evidence.**

## 11. Một cấu hình “tối thiểu” không phải công thức cộng số

Cú pháp đầy đủ ví dụ:

```bash
java -Xms64m -Xmx128m \
     -XX:MaxMetaspaceSize=128m \
     -XX:MaxDirectMemorySize=16m \
     -XX:ReservedCodeCacheSize=64m \
     MemoryBudgetDemo
```

Dấu `\` nối dòng dành cho Bash. Trong PowerShell dùng một dòng:

```powershell
java -Xms64m -Xmx128m -XX:MaxMetaspaceSize=128m -XX:MaxDirectMemorySize=16m -XX:ReservedCodeCacheSize=64m MemoryBudgetDemo
```

**Đây là cấu hình cho chương trình demo nhỏ, KHÔNG phải preset cho production services.** Một service dùng Netty/WebFlux có thể cần direct buffers nhiều hơn; framework/plugin system có thể có Metaspace lớn hơn; workload cần JIT có thể cần code cache lớn hơn.

### 11.1. Vì sao không cộng ra “JVM sẽ dùng tối đa 336 MiB”?

- Những cờ là caps/reservations cho các nhóm khác nhau, không phải committed usage thực.
- Java thread stacks, GC, JNI, native allocators, runtime libraries và mapped files chưa được tính.
- Native memory hoặc Linux RSS có thể vượt các thành phần đã cộng.
- Ngay một số flags còn giới hạn theo accounting nội bộ, không phải physical maximum cùng cách.
- Code cache **reserved** là virtual space, khác committed/resident.

Một budget đúng cần cộng **peak committed/native/heap/threads có quan sát thực tế** với headroom, sau đó so với container/OS limits.

## 12. Thứ tự hợp lý khi quyết định giới hạn

Đừng bắt đầu bằng “Metaspace 128m, direct 128m, code 128m vì dễ nhớ”. Thay vào đó:

1. Xác định **SLO**: latency, throughput, pod/container limit, startup deadline.
2. Ghi JDK/HotSpot version và **current JVM flags**.
3. Ghi **baseline** NMT, MemoryPoolMXBeans/BufferPoolMXBeans, code cache.
4. Tạo **representative load**, gồm peak concurrency và những code paths hiếm nhưng quan trọng.
5. Theo dõi **used/committed/reserved trends**, class count, direct pool capacity/count, compile status.
6. Phân biệt startup/warm-up và steady-state.
7. Xác định peak + biến động + kịch bản deploy/redeploy.
8. Chọn **cap có headroom**, không thấp hơn peak measured usage.
9. Kiểm tra lại trên container/VM resources thật.
10. Giảm/tăng từng flag **một biến mỗi lần**, thu rollback criteria.

### 12.1. Headroom không có tỷ lệ phổ quát

Một ứng dụng có rất ít dynamic classes có Metaspace ổn định; một service hot-reload/plugins có thể tăng đột biến. Direct buffers của một gateway chịu traffic burst khác batch CPU-bound. Code cache nhu cầu thay đổi theo số classes/hot methods/JIT policy.

Vì vậy không đưa lời hứa kiểu “+20% là luôn đủ” vào runbook. Headroom phải dựa vào **percentiles, spikes, deployment patterns, GC response và incidents**.

## 13. Native Memory Tracking (NMT): thấy memory của HotSpot theo subsystem

**NMT** là công cụ HotSpot theo dõi một phần **native memory allocations mà VM quản lý**, hỗ trợ chia nguồn sử dụng theo categories như Class, Code, Thread, GC, Compiler, Internal...

Bật tại lúc khởi động:

```bash
java -XX:NativeMemoryTracking=summary MemoryBudgetDemo
```

Có hai mức thường dùng:

- `-XX:NativeMemoryTracking=summary`: thống kê theo JVM subsystems.
- `-XX:NativeMemoryTracking=detail`: thêm thông tin các call sites/virtual memory regions; tốn overhead hơn.

Theo Oracle, **NMT mặc định tắt** và thường cần bật ngay khi VM start; không giả định có thể yêu cầu NMT full history từ một process trước đó không bật.

### 13.1. NMT không theo dõi mọi malloc bên ngoài VM

Điểm quan trọng từ tài liệu Oracle: NMT tập trung vào **HotSpot/JVM-managed native memory**, **không phải một native profiler toàn diện cho code JNI hoặc third-party native libraries**.

Do đó tổng NMT **không bắt buộc bằng RSS hoặc toàn bộ native bytes**; nếu điều tra native memory leak ngoài HotSpot, có thể cần OS maps, allocators/profilers hoặc thư viện chuyên dụng.

### 13.2. NMT summary không phải “một dòng direct memory”

Direct-buffer backing allocations có thể xuất hiện dưới một hoặc vài NMT categories tùy HotSpot version và allocator path; NMT **không bảo đảm có riêng một dòng tên `Direct buffer memory`** đúng bằng direct pool capacity.

Khi nghi direct buffer pressure, dùng **BufferPoolMXBean** trước, NMT/OS metrics để bổ sung ngữ cảnh.

### 13.3. Tác động overhead

Oracle ghi NMT có thể làm giảm hiệu năng và tăng memory overhead (các tài liệu troubleshooting nêu khoảng 5–10% cho một số workload). Cần bật có chủ đích trên môi trường đo/diagnostics, không mặc định giữ `detail` cho production mãi mãi.

## 14. `jcmd VM.native_memory`: summary và so sánh delta

Đầu tiên xác định JVM process:

```bash
jcmd -l
```

Ví dụ với PID đã biết:

```bash
jcmd <pid> VM.native_memory summary scale=MB
```

`<pid>` là placeholder, phải thay bằng PID thực tế; **không copy dấu `<`/`>` vào shell như một số shell sẽ coi là cú pháp redirect**.

Nếu JVM được start với NMT summary/detail, có thể lấy baseline:

```bash
jcmd <pid> VM.native_memory baseline
```

sau khi chạy workload/đợi trạng thái cần quan sát:

```bash
jcmd <pid> VM.native_memory summary.diff scale=MB
```

### 14.1. Baseline có ích ở đâu?

Bạn có thể so:

- Sau startup/ready.
- Sau load bài kiểm thử.
- Sau mở/đóng plugin.
- Sau redeploy.
- Sau idle và GC/class unloading, khi phù hợp.

Một số dạng output:

```text
Total: reserved=..., committed=...
- Java Heap (reserved=..., committed=...)
- Class (reserved=..., committed=...)
- Code (reserved=..., committed=...)
- Thread (reserved=..., committed=...)
```

Đây là **cấu trúc minh họa**. Đơn vị, dấu cộng/trừ và các categories phụ thuộc VM/report.

### 14.2. Không suy mỗi delta tăng là leak

Class metadata tăng khi lazy loads là bình thường; code cache tăng trong warm-up cũng bình thường. Một leak đáng nghi khi usage tăng liên tục **dưới workload/class-loader lifecycle dự kiến phải ổn định**, đặc biệt sau khi đã unload/release phù hợp.

### 14.3. Nếu `VM.native_memory` báo disabled

NMT cần bật từ JVM startup bằng `-XX:NativeMemoryTracking=summary` hoặc `detail`. Không làm lại truy vấn 10 lần trên cùng process rồi mong nó xuất hiện retroactively.

## 15. `jcmd VM.metaspace`: quan sát class metadata chuyên biệt

Theo tài liệu HotSpot/JDK phù hợp:

```bash
jcmd <pid> VM.metaspace basic
```

Báo cáo có thể cho thông tin:

- Class/non-class metadata usage.
- Reserved/committed.
- Virtual space, chunks, fragmentation.
- Class loader usage và class counts ở mức tùy option.

Tùy JDK/build, có thể có additional diagnostics:

```bash
jcmd <pid> VM.metaspace show-loaders
```

Kiểm tra capabilities bằng:

```bash
jcmd <pid> help
jcmd <pid> help VM.metaspace
```

### 15.1. Vì sao xem class loaders?

Nếu Metaspace tăng sau mỗi hot redeploy, có thể một số class loaders cũ vẫn reachable. Dùng breakdown theo loader để xem số classes và memory của các loaders có giảm như kỳ vọng khi unload hay không.

### 15.2. Đừng chỉ thấy `Metaspace used` mà bỏ class space

Với compressed class pointers, JVM có non-class và class metadata spaces. Những caps có thể bị chạm theo cách khác nhau; cần xem cả Metaspace và **Compressed Class Space**.

### 15.3. Không phải mọi `jcmd` command có trên mọi VM

HotSpot/JDK release hoặc quyền attach/container policy có thể hạn chế commands. Không suy một lệnh thất bại đồng nghĩa Metaspace không tồn tại.

## 16. `jcmd Compiler.codecache`: cách biết code cache còn chỗ không

Lệnh:

```bash
jcmd <pid> Compiler.codecache
```

trên HotSpot thường cho các số:

```text
CodeCache: size=65536Kb used=2701Kb max_used=2701Kb free=62834Kb
...
Compilation: enabled, stopped_count=0, restarted_count=0
```

Đây là **một mẫu output quan sát từ môi trường kiểm tra**, không phải số phải giống trên mọi JVM. Khi segmented code cache, output có thể hiện từng CodeHeap riêng biệt.

### 16.1. Đọc những số nào?

- **size:** capacity của code cache/segment.
- **used/free:** hiện trạng theo code cache accounting.
- **max_used:** peak usage theo run.
- **Compilation status:** compiler còn đang enabled hoặc đã stop/restart theo VM.

### 16.2. Phân tích sâu hơn

Một số HotSpot builds hỗ trợ:

```bash
jcmd <pid> Compiler.CodeHeap_Analytics
```

Output có thể chi tiết về code heaps/free space/method counts. Đây là diagnostic operation; tùy version/permissions và workload có overhead.

### 16.3. Nếu Code Cache liên tục đầy

Đừng chỉ tăng `ReservedCodeCacheSize` ngay. Hãy kiểm tra:

- Những hot methods/JIT levels và code cache occupancy.
- Khả năng class loading/code generation bùng nổ.
- Compiler stop/restart warnings.
- Code cache fragmentation/method sweeping.
- Heap/native memory pressure và container limits.
- Startup/steady-state difference.

Có thể cần tăng limit **nếu usage thật đang tiệm cận cap**, nhưng phải giữ đủ memory headroom.

## 17. `-Xlog`: class, metaspace và code cache events

HotSpot Unified Logging cung cấp những tags phù hợp để quan sát, tùy version:

```bash
java -Xlog:gc+metaspace=info MemoryBudgetDemo
```

Có thể ghi chi tiết Metaspace theo mức hỗ trợ:

```bash
java -Xlog:metaspace=info MemoryBudgetDemo
```

Code cache events theo tags mà runtime hỗ trợ:

```bash
java -Xlog:codecache=info MemoryBudgetDemo
```

**Quan trọng:** từng tag/tag combination và level phải được kiểm tra:

```bash
java -Xlog:help
```

Nếu tag trên không được VM hỗ trợ ở release đang dùng, đừng khẳng định mọi JVM bắt buộc in đúng câu mẫu. Một số thông tin CodeCache còn được đưa qua compiler logs hoặc `jcmd`.

### 17.1. Logging là công cụ giải thích, không baseline timing sạch

Verbose logs có CPU/I/O overhead và có thể thay đổi scheduling. Hãy thu performance metrics ở runs riêng với diagnostics khi cần benchmark nghiêm túc.

### 17.2. OOME log không phải lúc nào cho đủ nguyên nhân

`OutOfMemoryError` có thể báo tên vùng, nhưng để biết vì sao vùng tăng cần kiểm tra class-loader retention, buffer ownership, code cache activity và cả OS native allocations.

## 18. MemoryPoolMXBean: đo Metaspace và Code Cache từ Java

JDK cung cấp **`java.lang.management.MemoryPoolMXBean`**, có thể truy cập bằng:

```java
ManagementFactory.getMemoryPoolMXBeans()
```

Một số pool names trên HotSpot:

```text
Metaspace
Compressed Class Space
CodeHeap 'non-nmethods'
CodeHeap 'profiled nmethods'
CodeHeap 'non-profiled nmethods'
CodeCache
```

Không phải tất cả cùng xuất hiện. Với segmentation, thường có CodeHeap pools; với một cấu hình code cache nhỏ, có thể có một pool `CodeCache`.

### 18.1. `MemoryUsage` có những gì?

`MemoryPoolMXBean.getUsage()` có thể trả:

- `getUsed()`: bytes used theo pool.
- `getCommitted()`: bytes committed theo pool.
- `getMax()`: maximum theo pool, **-1** nếu undefined.
- `getInit()`: initial allocation estimate nếu có.

**Không lấy `getMax() == -1` nghĩa pool “vô hạn RAM vật lý”**. Nó chỉ có nghĩa management interface không định nghĩa maximum cụ thể.

### 18.2. MXBeans là ảnh chụp gần đúng

Các values có thể thay đổi ngay khi chương trình/JVM tiếp tục chạy. Chúng hữu ích để tracking trends, không là atomic snapshot mọi native allocations trên tất cả pools.

## 19. BufferPoolMXBean: đo NIO direct memory từ Java

JDK có interface:

```java
java.lang.management.BufferPoolMXBean
```

Lấy các pool:

```java
ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)
```

Một số HotSpot pool names:

- `direct`.
- `mapped`.
- `mapped - 'non-volatile memory'` trên platform/configuration hỗ trợ.

Với từng pool:

- `getCount()` — estimate number of buffers.
- `getTotalCapacity()` — estimate aggregate buffer capacity bytes.
- `getMemoryUsed()` — estimate memory bytes, **có thể -1** hoặc khác capacity do alignment/allocator overhead.

**Chọn pool bằng tên và kiểm tra tồn tại**; không hardcode “mỗi JVM có đúng một direct pool và không có mapped pool”.

### 19.1. Direct pool tăng không chắc là leak

Một server có thể giữ pooled direct buffers hợp lệ để tránh frequent allocations. Cần biết pool ownership, idle reclamation policy và traffic concurrency. Kiểm tra plateau sau warm-up/peak load thay vì đòi usage phải về 0 sau mỗi request.

### 19.2. Off-heap library có thể không hiện trong direct pool

Native allocations từ bên ngoài Buffer APIs có thể không được quản lý qua cùng pool. Nếu process RSS tăng mà BufferPoolMXBean ổn định, xem thêm NMT, JNI/native libraries, thread stacks và OS maps.

## 20. Ví dụ Java 17+ độc lập để nhìn cả ba vùng

Tạo tệp **`MemoryBudgetDemo.java`**:

```java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryUsage;
import java.nio.ByteBuffer;
import java.util.Locale;

public final class MemoryBudgetDemo {
    private static volatile long sink;

    static int transform(int x) {
        return (x * 31) ^ (x >>> 3);
    }

    public static void main(String[] args) throws Exception {
        ByteBuffer direct = ByteBuffer.allocateDirect(1024 * 1024);
        direct.putInt(0, 424242);
        System.out.println("directValue=" + direct.getInt(0));

        long sum = 0;
        for (int i = 0; i < 100_000; i++) {
            sum += transform(i);
        }
        sink = sum;
        System.out.println("checksum=" + sum);
        System.out.println("sinkMatches=" + (sink == sum));

        boolean metaspaceFound = false;
        boolean codeCacheFound = false;
        for (MemoryPoolMXBean pool :
                ManagementFactory.getMemoryPoolMXBeans()) {
            String name = pool.getName();
            if (name.equals("Metaspace")) metaspaceFound = true;
            if (name.startsWith("CodeHeap")
                    || name.startsWith("CodeCache")) {
                codeCacheFound = true;
            }

            if (name.equals("Metaspace")
                    || name.equals("Compressed Class Space")
                    || name.startsWith("CodeHeap")
                    || name.startsWith("CodeCache")) {
                MemoryUsage usage = pool.getUsage();
                if (usage != null) {
                    System.out.printf(Locale.ROOT,
                            "%s: usedKiB=%d committedKiB=%d maxKiB=%d%n",
                            name,
                            usage.getUsed() / 1024,
                            usage.getCommitted() / 1024,
                            usage.getMax() < 0
                                    ? -1 : usage.getMax() / 1024);
                }
            }
        }

        boolean directPoolFound = false;
        for (BufferPoolMXBean pool :
                ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
            if (pool.getName().equals("direct")) {
                directPoolFound = true;
                System.out.println("directPoolCount=" + pool.getCount());
                System.out.println("directPoolCapacityBytes="
                        + pool.getTotalCapacity());
                System.out.println("directPoolUsedBytes="
                        + pool.getMemoryUsed());
            }
        }

        System.out.println("metaspacePoolFound=" + metaspaceFound);
        System.out.println("codeCachePoolFound=" + codeCacheFound);
        System.out.println("directPoolFound=" + directPoolFound);

        if (args.length != 0 && args[0].equals("hold")) {
            System.out.println("pid=" + ProcessHandle.current().pid());
            System.out.println("waitingForDiagnostics=true");
            Thread.sleep(15_000);
        }
    }
}
```

### 20.1. Biên dịch

```bash
javac --release 17 MemoryBudgetDemo.java
```

### 20.2. Chạy mặc định

```bash
java MemoryBudgetDemo
```

**Ba dòng đầu có giá trị cố định khi chương trình chạy đúng:**

```text
directValue=424242
checksum=154999801808
sinkMatches=true
```

Phần tiếp theo là **metadata của pools**, có thể gồm:

```text
Metaspace: usedKiB=... committedKiB=... maxKiB=...
Compressed Class Space: usedKiB=... committedKiB=... maxKiB=...
CodeHeap 'non-nmethods': usedKiB=... committedKiB=... maxKiB=...
...
directPoolCount=...
directPoolCapacityBytes=...
directPoolUsedBytes=...
metaspacePoolFound=true
codeCachePoolFound=true
directPoolFound=true
```

Dấu `...` ở block này là **placeholder minh họa metric không cố định**, **không phải stdout chính xác**. Các pool-presence booleans đã được kiểm chứng bằng HotSpot local; **JVM khác HotSpot có thể dùng names khác**.

### 20.3. Chạy với ba giới hạn

```bash
java -Xmx128m -XX:MaxMetaspaceSize=128m \
     -XX:MaxDirectMemorySize=16m \
     -XX:ReservedCodeCacheSize=64m \
     MemoryBudgetDemo
```

Trên Windows PowerShell:

```powershell
java -Xmx128m -XX:MaxMetaspaceSize=128m -XX:MaxDirectMemorySize=16m -XX:ReservedCodeCacheSize=64m MemoryBudgetDemo
```

**Ba dòng checksum cố định không thay đổi.** Pool `CodeHeap` có thể chuyển sang `CodeCache` do segmentation thay đổi theo config; ví dụ đã tính tới cả hai.

### 20.4. Vì sao có một direct allocation mà memory pool chỉ “ước tính”?

Demo cấp 1 MiB bằng `ByteBuffer.allocateDirect` và giữ local reference tới buffer trong `main`. Buffer pool thường ghi nhận ít nhất allocation này. Nhưng GC/VM/library allocations khác có thể làm `getCount()` và `getMemoryUsed()` thay đổi theo thời điểm.

**Đừng so exact directPoolCount với hằng số 1 trên mọi JVM/runtime.**

### 20.5. Giá trị `checksum` tính bằng gì?

`transform(i)` tính `(i*31) ^ (i>>>3)` theo 32-bit Java integer arithmetic. Kết quả được cộng vào `long` qua 100.000 iterations, cho giá trị xác định **154999801808** ở input demo.

`volatile sink` tạo một observable side effect giúp tránh một số compiler optimizations bỏ hẳn tính toán; không dùng demo này làm microbenchmark performance thay cho JMH.

## 21. Chẩn đoán bằng `jcmd` trên cùng process

Chương trình hỗ trợ đối số `hold` để giữ JVM chạy trong một khoảng ngắn cho người học attach diagnostics:

```bash
java -XX:NativeMemoryTracking=summary -Xmx128m \
     -XX:MaxMetaspaceSize=128m \
     -XX:MaxDirectMemorySize=16m \
     -XX:ReservedCodeCacheSize=64m \
     MemoryBudgetDemo hold
```

Trong một terminal khác, khi process còn chạy, lấy PID in bởi demo hoặc:

```bash
jcmd -l
```

Sau đó:

```bash
jcmd <pid> VM.native_memory summary scale=MB
jcmd <pid> VM.metaspace basic
jcmd <pid> Compiler.codecache
```

Với `<pid>` là PID thực tế.

### 21.1. Đây là một cửa sổ thử nghiệm, không phải server production

`Thread.sleep(15_000)` chỉ giữ demo process khoảng 15 giây sau khi in các metrics. Lệnh `jcmd` phải được chạy khi process còn sống. Nếu lỡ hết cửa sổ, khởi chạy demo mới; **không giữ process vô hạn** chỉ để quan sát.

### 21.2. Ví dụ đã được kiểm chứng thực tế

Trên **OpenJDK HotSpot 24.0.2** (mã tương thích **Java 17** và biên dịch bằng `javac --release 17`), thử nghiệm cho thấy:

- `MemoryBudgetDemo` chạy thành công với flags trên, checksum đúng.
- `MemoryPoolMXBean` hiển thị Metaspace, Compressed Class Space và code cache.
- Khi code cache giới hạn 64 MiB, VM hiển thị pool **`CodeCache`**, không nhất thiết có ba CodeHeap pools.
- `BufferPoolMXBean` có pool `direct`, report 1 MiB direct buffer trong lúc đo.
- `jcmd VM.native_memory summary` cung cấp Class/Code/Heap/Thread categories.
- `jcmd VM.metaspace basic` hiển thị metadata usage.
- `jcmd Compiler.codecache` báo trạng thái compilation và code cache occupancy.

Đây là một **kiểm thử local**; số dùng/commit/reserve khác trên môi trường thật. Không nhầm “Java 17-compatible” với lời khẳng định thử đã chạy trên đúng binary JDK 17.

## 22. Tình huống A — Metaspace cứ tăng sau mỗi redeploy

**Triệu chứng:** sau mỗi lần deploy/hot reload, loaded class count/Metaspace không về mức dự kiến; dần gặp `OutOfMemoryError: Metaspace`.

Cách suy luận:

1. Ghi số classes và Metaspace used/committed trước deploy.
2. Deploy/reload, chờ/quan sát class unloading theo GC.
3. Dùng `jcmd VM.metaspace` và class-loading/unloading logs.
4. Kiểm tra xem class loaders cũ còn reachable không.
5. Tìm references qua static registries, thread local values, executors, caches, TCCL, lingering threads.
6. Sửa ownership/cleanup; chỉ tăng cap nếu workload thật sự cần và được đo.

### 22.1. Không coi việc GC một lần không giảm ngay là kết luận leak

Class unloading phụ thuộc GC cycle, loader reachability và VM policies. Có thể có delayed reclamation hoặc fragmentation. Dấu hiệu leak mạnh hơn khi **sau nhiều chu kỳ lifecycle tương tự**, số loaders/classes giữ lại tăng mà không có lý do nghiệp vụ.

### 22.2. `-Xmx` lớn có chữa Metaspace leak không?

Không trực tiếp. Còn native memory budget có thể bị áp lực hơn. Nguyên nhân là metadata/lifecycle, không chỉ object heap cap.

## 23. Tình huống B — Direct buffers tăng theo kết nối mạng

**Triệu chứng:** service NIO/Netty/network stack nhận traffic; direct pool `count/totalCapacity/memoryUsed` tăng, sau đó `OutOfMemoryError` trong reserve direct buffer memory hoặc container OOM.

Checklist:

- Đo **active connections × buffers per connection × average capacity**, cộng pipeline caches/pooling.
- Đọc `BufferPoolMXBean` direct pool và application buffer pool diagnostics.
- Kiểm tra pooling: buffer trả về pool đúng lúc không?
- Kiểm tra requests/errors/cancellation paths có giữ reference không.
- Kiểm tra burst/retry/queue backlog và container memory limit.
- Đừng chỉ tăng `MaxDirectMemorySize` nếu buffer references không được release.

### 23.1. Leak thật và pooling hợp lệ khác nhau

Pool giữ vài trăm MiB để tái sử dụng có thể là một thiết kế có chủ đích, không tự là leak. Nhưng nếu direct pool không plateau dưới tải ổn định, cần điều tra.

### 23.2. Native allocations ngoài DirectByteBuffer

Nếu BufferPoolMXBean direct gần như ổn định mà RSS tăng, mở rộng chẩn đoán sang JNI/native allocators, mapped pages, native arenas, stacks, GC và OS metrics.

## 24. Tình huống C — Code cache đầy khi số hot methods tăng

**Triệu chứng:** HotSpot báo code cache full/compiler disabled, application throughput giảm sau warm-up hoặc code cache usage sát limit.

Cách kiểm tra:

1. `jcmd <pid> Compiler.codecache`.
2. Kiểm tra `Compilation: enabled/stopped_count/restarted_count` nếu có.
3. Quan sát `-Xlog:codecache`/compiler events ở mức hỗ trợ.
4. Xem JVM code generation/proxy/lambda/framework classes tạo ra nhiều methods không.
5. So nhu cầu code cache với `ReservedCodeCacheSize`, segmented configuration và container budget.
6. Thử tăng limit từng bước nếu code cache là bottleneck được chứng minh.

### 24.1. Không suy code cache full là Java heap OOME

Vùng code cache có exhaustion behavior riêng. JVM vẫn có thể tiếp tục ở interpreter/compiled code còn sẵn; hiệu năng mới là dấu hiệu dễ thấy, không bắt buộc crash ngay.

### 24.2. Code cache dùng nhiều trong warm-up là thường gặp

Khi lượng hot code được biên dịch trong thời gian đầu, used code cache tăng. Nếu nó plateau xa cap và compilation vẫn enabled, không có lý do tự động tăng reserve chỉ vì giá trị cao hơn hôm qua.

## 25. Cấu hình theo tài nguyên container: budget thay vì các cap độc lập

Giả sử một container bị giới hạn ở một memory budget đã biết. Cách chuẩn không phải:

```text
container_limit = Xmx + MaxMetaspaceSize
                  + MaxDirectMemorySize + ReservedCodeCacheSize
```

đẳng thức này **sai** vì trộn **virtual reserve**, **committed** và **potential allocations**, đồng thời bỏ sót nhiều nguồn memory.

Một budgeting worksheet có thể là:

| Thành phần | Cần khảo sát | Có phụ thuộc workload? |
| --- | --- | --- |
| Heap | Peak live set, GC overhead, Xmx | Rất nhiều |
| Metaspace | Class count, loaders, peaks, MaxMetaspace | Có |
| Direct buffers | Peak outstanding bytes, pooling, bursts | Có |
| Code cache | Max used, compiler enabled, hot code footprint | Có |
| Threads | Number × stack usage/native footprint | Có |
| GC/compiler/native/JNI | NMT + OS metrics + library diagnostics | Có |
| Mapped/shared pages | RSS/PSS/cgroup accounting | Có |
| Headroom | traffic spikes, deploy change, instrumentation | Có |

### 25.1. Không đặt mọi cap sát giá trị used ở idle

Metaspace có thể tăng sau lần chạy chức năng hiếm; direct memory tăng khi concurrent requests cao; code cache có thể tăng khi JIT profile đủ. Chỉ đo idle và đặt limit sát idle usage sẽ dẫn tới failures muộn.

### 25.2. Bản thân việc giới hạn có thể ảnh hưởng behavior

Nếu hạ `MaxMetaspaceSize`, GC/class unloading policy có thể hoạt động nhiều hơn. Nếu hạ code cache, JIT compilation có thể chậm hoặc dừng. Nếu hạ direct memory, buffers có thể gây OOME/GC pressure. Các thay đổi cap phải được **load test**, không chỉ kiểm tra `java -version`.

## 26. Những hiểu lầm thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “-Xmx là maximum memory của cả Java process.” | Nó giới hạn Java heap, không bao toàn bộ native memory. |
| “Metaspace nằm trong Java heap.” | HotSpot quản lý class metadata trong native memory. |
| “MaxMetaspaceSize=128m thì start đã commit 128m.” | Đây là cap, không phải allocation upfront. |
| “MetaspaceSize và MaxMetaspaceSize đồng nghĩa.” | Một cái liên quan threshold, một cái là maximum. |
| “Metaspace growth luôn chứng minh leak.” | Lazy class loading/initialization cũng làm tăng usage. |
| “Compressed Class Space chỉ là tên khác của toàn Metaspace.” | Có scope class metadata riêng với cap tương ứng. |
| “CompressedClassSpaceSize reserved 1 GiB = 1 GiB RAM đang dùng.” | Virtual reservation khác committed/RSS. |
| “Direct ByteBuffer wrapper là toàn bộ storage nằm trong heap.” | Backing data của direct buffer thường là off-heap. |
| “MaxDirectMemorySize chặn tất cả JNI malloc.” | Cờ này chủ yếu quản lý NIO direct-buffer accounting. |
| “Direct buffers không cần GC/reachability để reclaim.” | Cleaner/lifetime phụ thuộc reachability/VM mechanism. |
| “Capacity bằng memoryUsed trong mọi trường hợp.” | MXBean values là estimates, có alignment/allocator overhead. |
| “MappedByteBuffer luôn cùng pool/limit với direct buffers.” | Mapped buffers có scope/accounting khác. |
| “Code cache và Metaspace là một vùng.” | Metadata và generated code là hai vùng khác nhau. |
| “ReservedCodeCacheSize=64m nghĩa RSS tăng ngay 64m.” | Reservation không đồng nghĩa committed/resident. |
| “CodeCache phải luôn gồm đúng ba CodeHeap MXBeans.” | Segmentation phụ thuộc JVM build/config. |
| “Code cache full luôn ném Java heap OutOfMemoryError.” | Thường liên quan compilation disabled/warnings và performance. |
| “Một compiled method level 4 chứng minh code cache đầy.” | Compilation level và memory occupancy là hai metrics khác nhau. |
| “NMT tổng luôn bằng process RSS.” | NMT không đo mọi native allocation/OS memory. |
| “NMT summary bắt buộc có dòng Direct buffer memory.” | Direct buffers có thể xuất hiện qua VM categories không có tên đó. |
| “NMT mặc định luôn bật.” | Off theo mặc định ở HotSpot JDK17. |
| “Một lần tăng code cache used là leak.” | JIT warm-up có thể là tăng trưởng bình thường. |
| “Cộng Xmx + ba max là memory limit chính xác.” | Không; còn thread stacks, native/GC/JNI, committed/reserved khác nhau. |
| “Giới hạn càng nhỏ luôn giảm latency.” | Có thể kích hoạt GC/compilation stops/OOME. |
| “Một demo có poolFound=true chứng minh mọi JVM có tên pool đó.” | Đây là HotSpot-specific naming/behavior. |
| “JDK version không ảnh hưởng mặc định flags.” | VM ergonomics/options đổi theo build và architecture. |

## 27. Câu hỏi tự kiểm tra có đáp án

**Câu 1.** `-Xmx` có giới hạn Metaspace không?

**Đáp án:** Không. Heap và class metadata Metaspace có cơ chế giới hạn khác nhau trên HotSpot.

**Câu 2.** Cờ đặt cap cho class metadata là gì?

**Đáp án:** `-XX:MaxMetaspaceSize=...`.

**Câu 3.** `MetaspaceSize` có phải maximum không?

**Đáp án:** Không. Nó liên quan threshold/GC trigger, khác `MaxMetaspaceSize`.

**Câu 4.** Khi nào xuất hiện `OutOfMemoryError: Compressed class space`?

**Đáp án:** Khi vùng compressed class space hết capacity theo cấu hình và VM không thể đáp ứng allocation phù hợp.

**Câu 5.** Reserved 1 GiB có nghĩa RSS tăng 1 GiB không?

**Đáp án:** Không. Reserved virtual address space khác committed/resident physical memory.

**Câu 6.** Direct ByteBuffer nằm hoàn toàn trong Java heap không?

**Đáp án:** Không. Wrapper là Java object, backing storage direct buffer trên HotSpot thường là off-heap.

**Câu 7.** `MaxDirectMemorySize` có giới hạn mọi thư viện native/JNI malloc không?

**Đáp án:** Không. Nó nhắm vào NIO direct-buffer memory accounting.

**Câu 8.** Vì sao direct pool count/capacity không giảm ngay sau `buffer = null`?

**Đáp án:** Cleanup phụ thuộc reachability, GC/Cleaner và VM pooling; không có immediate-free guarantee.

**Câu 9.** Đọc direct pool bằng API nào?

**Đáp án:** `BufferPoolMXBean` qua `ManagementFactory.getPlatformMXBeans`.

**Câu 10.** `getMemoryUsed()` có thể khác `getTotalCapacity()` không?

**Đáp án:** Có. Alignment/allocator overhead và implementation-specific estimates làm khác biệt.

**Câu 11.** Code cache chứa loại dữ liệu gì?

**Đáp án:** JIT generated nmethods và runtime code/stubs của VM, khác heap class metadata.

**Câu 12.** Cờ code cache maximum thường là gì?

**Đáp án:** `-XX:ReservedCodeCacheSize=...`.

**Câu 13.** Code cache đầy có buộc application ném Java heap OOME không?

**Đáp án:** Không. VM có thể cảnh báo/dừng compilation, ảnh hưởng throughput/latency.

**Câu 14.** Tại sao có lúc thấy `CodeHeap`, lúc thấy `CodeCache`?

**Đáp án:** HotSpot có thể dùng segmented hoặc unsegmented code cache tùy runtime flags/build.

**Câu 15.** Reserved và committed khác thế nào?

**Đáp án:** Reserved giữ virtual address range; committed là memory đã được yêu cầu backing theo VM/OS mechanism.

**Câu 16.** NMT bật bằng flag nào?

**Đáp án:** `-XX:NativeMemoryTracking=summary` hoặc `detail` khi start.

**Câu 17.** Lệnh jcmd nào xem breakdown JVM native memory?

**Đáp án:** `jcmd <pid> VM.native_memory summary` nếu NMT được bật.

**Câu 18.** Lệnh xem class metadata chi tiết?

**Đáp án:** `jcmd <pid> VM.metaspace basic` trên HotSpot hỗ trợ.

**Câu 19.** Lệnh xem code cache usage/compilation status?

**Đáp án:** `jcmd <pid> Compiler.codecache`.

**Câu 20.** Vì sao NMT và RSS không nhất thiết bằng nhau?

**Đáp án:** Scope NMT chỉ một số allocations của VM; RSS còn gồm OS residency/shared pages và native allocations bên ngoài VM tracking.

**Câu 21.** Có thể tính total process RAM bằng `Xmx + MaxMetaspaceSize + MaxDirectMemorySize + ReservedCodeCacheSize` không?

**Đáp án:** Không, các metrics/caps khác định nghĩa và còn nhiều native areas chưa tính.

**Câu 22.** Metaspace tăng qua redeploy gợi ý kiểm tra gì?

**Đáp án:** Class loader retention/unloading, proxy class generation, cache/thread references, class counts và NMT/VM.metaspace.

**Câu 23.** Direct memory tăng dưới traffic gợi ý kiểm tra gì?

**Đáp án:** Buffer pooling/ownership, outstanding buffers/connections, async cancellation paths và BufferPoolMXBean direct usage.

**Câu 24.** Code cache gần đầy dưới load gợi ý kiểm tra gì?

**Đáp án:** Compiler.codecache, compiler logs, hot code footprint, code sweeper/fragmentation và JVM flags.

**Câu 25.** Vì sao không nên chọn memory caps chỉ từ idle metrics?

**Đáp án:** Các vùng có spikes theo class lazy-loading, request concurrency và JIT warm-up, cần peak/load data và headroom.

**Câu 26.** Demo chạy với JDK 24 có tự chứng minh mọi JDK 17 build hỗ trợ chính xác cùng pool names không?

**Đáp án:** Không. Code dùng API Java 17 và JDK 17-compatible flags; names/metrics cụ thể thuộc HotSpot implementation.

## 28. Checklist đưa vào production

1. Xác nhận **Java/JVM vendor, build, architecture** và flags hiện tại.
2. Xác định **container/OS memory budget**, chính sách OOMKilled và cách đo RSS/PSS.
3. Đo heap live set, Metaspace used/committed, compressed class space, direct pool và code cache.
4. Bật NMT summary **có chủ đích** trên môi trường chẩn đoán phù hợp.
5. Lấy NMT baseline và diff qua các pha startup/steady/peak/redeploy.
6. Dùng `VM.metaspace` để quan sát loaders và class metadata khi có dấu hiệu tăng trưởng.
7. Dùng `Compiler.codecache` để quan sát compilation enabled/stopped/usage.
8. Dùng `BufferPoolMXBean` cho `direct` và `mapped` pools nếu có.
9. Không đồng nhất `MaxDirectMemorySize` với mọi native allocations.
10. Không so reserved virtual code cache với RSS như hai chỉ số cùng đơn vị sử dụng.
11. Chạy representative workload gồm peak concurrency và lazy/rare code paths.
12. Tìm leaks/pools không plateau trước khi tăng caps.
13. Giữ headroom cho thread stacks/GC/JNI và non-VM allocations.
14. Thay đổi từng flag độc lập và ghi lại outcome/latency/GC/OOME.
15. Đừng đặt cap sát idle used.
16. Kiểm tra quy tắc lỗi/alert cho Metaspace OOME, direct OOME và code cache warning riêng.
17. Tránh giữ NMT detail hoặc logging verbose mãi mãi nếu overhead không được chấp nhận.
18. Benchmark performance không diagnostic I/O trước khi kết luận lợi ích.
19. Có rollback plan và kịch bản memory incident.
20. Không coi cấu hình demo 128/16/64 MiB là gợi ý production mặc định.

### Sơ đồ ghi nhớ nhanh

```text
                       JVM memory observation
                                 |
             +-------------------+-------------------+
             |                   |                   |
         Metaspace           Direct NIO            Code Cache
        class metadata       ByteBuffer             JIT/native
             |               backing                 blobs
             |                   |                   |
    MaxMetaspaceSize    MaxDirectMemorySize    ReservedCodeCacheSize
             |                   |                   |
     VM.metaspace         BufferPoolMXBean       Compiler.codecache
       / NMT Class          / NMT + OS             / NMT Code
             |                   |                   |
        Class loader        Pool lifetime          Compiler status
         growth/leaks      burst/caching            occupancy
             |                   |                   |
             +-------------------+-------------------+
                                 |
                   measured under real workload
                   compare used / committed / RSS
                   headroom + native/GC/thread costs
                                 |
                     change limits with evidence

Three independent controls != complete process memory cap.
```

**Kết luận:** Chỉ nên giới hạn Metaspace, NIO direct memory và code cache **theo dữ liệu quan sát được và yêu cầu vận hành**. Metaspace theo class metadata/class loader lifecycle; direct-buffer budget theo buffers/traffic/pooling; code cache theo hot methods/JIT behavior. Cả ba khác `-Xmx` và khác tổng native/RSS của process. Hãy dùng **NMT + đúng MXBean/jcmd của từng vùng + OS/container metrics**, rồi đặt limit có headroom đủ và load-test để kiểm tra, thay vì sao chép ba con số mặc định bất kỳ.

### Tài liệu chính thức và nguồn kỹ thuật

- [Oracle JDK 17 — `java` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): `MaxMetaspaceSize`, `MaxDirectMemorySize`, `ReservedCodeCacheSize`, `NativeMemoryTracking`, segmented code cache và các VM flags liên quan.
- [Oracle JDK 17 — Troubleshooting Memory Leaks](https://docs.oracle.com/en/java/javase/17/troubleshoot/troubleshooting-memory-leaks.html): các dạng Java heap/Metaspace/Compressed Class Space OOME, native-memory diagnostics, NMT limits.
- [Oracle JDK 17 — GC Tuning, Other Considerations](https://docs.oracle.com/en/java/javase/17/gctuning/other-considerations.html): Metaspace, class metadata allocations, class space.
- [Oracle JDK 17 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/17/vm/native-memory-tracking.html): NMT summary/detail, baseline/diff, overhead và scope.
- [Oracle JDK 17 — `jcmd` command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `VM.native_memory`, `VM.metaspace`, `Compiler.codecache`.
- [BufferPoolMXBean API, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): direct/mapped pool metrics và estimation caveats.
- [MemoryPoolMXBean API, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryPoolMXBean.html): used/committed/max/usage thresholds.
- [ByteBuffer API, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `allocate` vs `allocateDirect`.
- [OpenJDK JEP 387 — Elastic Metaspace](https://openjdk.org/jeps/387): reclaim/uncommit và quản lý native class metadata.
- [OpenJDK JEP 197 — Segmented Code Cache](https://openjdk.org/jeps/197): non-nmethods, profiled và non-profiled compiled code.
