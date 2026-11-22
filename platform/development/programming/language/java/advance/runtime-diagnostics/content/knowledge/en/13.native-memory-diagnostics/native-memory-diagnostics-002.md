# 13.2 Nguồn bộ nhớ ngoài heap: thread stack, metaspace, code cache, direct buffer và thư viện native

## 1. Mục tiêu và ranh giới bộ nhớ

Một tiến trình Java **không chỉ dùng Java heap**. `-Xmx` giới hạn phần heap do JVM quản lý cho Java objects; tiến trình còn cần bộ nhớ cho thread, metadata của class, mã máy do JIT tạo ra, I/O buffers, garbage collector, runtime và thư viện native. Vì vậy tình huống **heap còn trống nhưng RSS tăng, container bị OOMKilled hoặc JVM báo lỗi cấp phát native** hoàn toàn có thể xảy ra.

Bài học này giúp bạn:

1. Chỉ ra nơi cấp phát, vòng đời và cách giới hạn năm nguồn chính: **platform-thread stack, metaspace, code cache, direct buffer và native library**.
2. Phân biệt Java heap, vùng non-heap mà MXBean báo cáo, native/off-heap và tổng footprint của tiến trình.
3. Đọc đúng các con số **reserved, committed, used, RSS** và giới hạn ở JVM/container.
4. Dùng `jcmd`, Native Memory Tracking (NMT), `BufferPoolMXBean` và số liệu hệ điều hành để xác định nguồn tăng bộ nhớ.
5. Chọn hành động sửa lỗi phù hợp thay vì chỉ tăng `-Xmx` hay ép GC.

**Cách hiểu thuật ngữ:**

- **Java heap:** vùng JVM dùng cấp phát phần lớn Java objects và arrays; chịu quản lý GC, thường được quan sát qua heap metrics và `-Xmx`.
- **JVM non-heap (theo `MemoryMXBean`):** các memory pool phục vụ JVM như metaspace và code cache. Đây **không phải** toàn bộ native memory của tiến trình.
- **Native/off-heap memory:** cách gọi chung cho các vùng ngoài Java heap, gồm nhiều phần do HotSpot, Java libraries hoặc native code quản lý. Mỗi nguồn có cơ chế theo dõi và giới hạn riêng.
- **Process footprint:** bộ nhớ nhìn từ hệ điều hành/container, có thể gồm Java heap, native allocations, runtime structures, các memory mappings và vùng dùng chung.

Không có một phương trình chính xác kiểu `RSS = heap used + metaspace used + direct buffer used`. Các bộ đo có phạm vi khác nhau, và một phần vùng nhớ được chia sẻ, ánh xạ, chỉ reserved hoặc chưa nằm trong RAM.

## 2. Bản đồ năm nguồn bộ nhớ

| Nguồn | Nội dung chính | Vòng đời / yếu tố tăng | Công cụ quan sát | Giới hạn liên quan |
| --- | --- | --- | --- | --- |
| **Thread stack** | Call frames của **platform/OS threads**, vùng bảo vệ stack và cấu trúc thread | Số platform threads, độ sâu lời gọi, kích thước stack | NMT `Thread`, số thread OS, `jcmd Thread.print`, OS | `-Xss`, `-XX:ThreadStackSize`; thêm giới hạn OS/container |
| **Metaspace** | Metadata của classes, methods, class loaders; có thể có compressed class space | Nhiều classes được nạp, class loaders còn sống, dynamic proxies/codegen | NMT `Class`, `jcmd VM.metaspace`, class-loading metrics | `-XX:MaxMetaspaceSize`, `-XX:CompressedClassSpaceSize` khi áp dụng |
| **Code cache** | Native machine code do JIT sinh và các thành phần code runtime | Warm-up, số method/phiên bản tối ưu, tiered compilation | NMT `Code`, `jcmd Compiler.codecache`, JIT logs | `-XX:ReservedCodeCacheSize` |
| **Direct buffers** | Nội dung của `ByteBuffer.allocateDirect` thường ở ngoài heap | Số buffer, capacity, object/view giữ tham chiếu, tốc độ giải phóng | `BufferPoolMXBean` (`direct`), JFR/metrics thư viện, OS | `-XX:MaxDirectMemorySize` cho NIO direct allocations phù hợp |
| **Native libraries** | `malloc`/`mmap`, cấu trúc C/C++, JNI/FFM, native handles, code/data của `.so`/`.dll` | Cache native, native leaks, library lifecycle, memory mappings | OS memory maps, profiler native, metrics của thư viện | Giới hạn riêng của thư viện, OS/cgroup; các cờ JVM trên **không** đặt trần tổng cho nguồn này |

Ngoài năm nguồn chính còn có **GC structures, compiler working data, symbols, internal JVM structures, arena, JFR buffers, memory-mapped files, page tables**... Không nên ép các khoản đó vào metaspace hoặc direct buffer chỉ vì chúng nằm ngoài heap.

### 2.1. Sự khác nhau giữa reserved, committed, used và RSS

- **Reserved**: vùng địa chỉ ảo được giữ trước cho mục đích nào đó. Reserved lớn **không tự chứng minh** tiến trình đang giữ lượng RAM tương ứng. Ví dụ compressed class space có thể reserve một vùng địa chỉ lớn trong khi committed còn nhỏ.
- **Committed**: bộ nhớ đã được cam kết/cấp cho vùng của JVM theo cách hệ điều hành hỗ trợ. Đây vẫn **không đồng nghĩa chính xác** với số trang đang resident trong RAM.
- **Used**: lượng được bộ cấp phát hoặc subsystem tính là đang dùng bên trong committed. NMT và các MXBean có thể có cách đo khác nhau.
- **RSS (Resident Set Size)**: tổng trang bộ nhớ của tiến trình đang resident theo phép đo OS. Shared pages, file mappings và cách OS ghi nhận trang khiến RSS không thể cộng trực tiếp với NMT categories.

Ví dụ minh họa: `Class reserved=1050 MB, committed=38 MB` **không có nghĩa** 1.050 MB metaspace đã ăn hết RAM. Khi điều tra áp lực bộ nhớ thực, cần xem **committed/used thay đổi ra sao theo thời gian** và đối chiếu RSS/container memory.

## 3. Thread stack: một OS thread có chi phí riêng

### 3.1. Platform thread và native stack

`new Thread(...).start()` tạo một **platform thread** trên các JDK phổ biến. Nó gắn với OS thread, có native stack cho khung lời gọi, tham số, biến cục bộ, thông tin runtime và vùng guard. Có thể điều chỉnh kích thước stack bằng `-Xss`:

```bash
java -Xss1m -Xmx512m -jar app.jar
```

`-Xss1m` định kích thước stack cho thread theo cách triển khai/OS, **không** nghĩa mỗi thread ngay lúc tạo đã làm RSS tăng đúng 1 MiB. OS thường reserve nhiều không gian địa chỉ và commit/touch trang khi cần; HotSpot có thể báo phần stack trong NMT theo quy ước accounting của nó. Thread còn có native data structures ngoài stack, nên phép ước tính `threadCount × Xss` chỉ là **ước lượng địa chỉ dự trữ**, không phải công thức RSS.

Nếu có 500 platform threads và cấu hình stack gần 1 MiB, riêng không gian dành cho stack đã ở quy mô hàng trăm MiB. Nhưng mức sử dụng vật lý thực còn phụ thuộc độ sâu stack, OS và các vùng liên quan.

**Hai lỗi cần phân biệt:**

- `java.lang.StackOverflowError`: một thread vượt khả năng chứa stack, chẳng hạn do đệ quy không dừng; có thể xảy ra dù toàn tiến trình còn RAM.
- `java.lang.OutOfMemoryError: unable to create native thread` hoặc thông điệp tương tự: OS/JVM không tạo thêm được native thread do thiếu tài nguyên, process/thread limits, PID limits hoặc native memory pressure; **không nhất thiết heap đã đầy**.

Cách cải thiện: giới hạn số platform threads đồng thời, tránh tạo một platform thread cho mỗi request mà không có bound, phân tích thread leak/blocked threads, cân nhắc thread pools hoặc virtual threads nếu workload phù hợp. Hạ `-Xss` quá nhỏ có thể làm ứng dụng dễ `StackOverflowError`; tăng `-Xss` không giải quyết việc tạo quá nhiều threads.

### 3.2. Virtual threads không có native stack riêng theo cách đó

Từ JDK 21, virtual threads là tính năng chính thức. Chúng dùng **stack chunks** ở Java heap khi được unmount, được scheduler mount lên **carrier platform threads** để chạy. Do đó **không nhân số lượng virtual threads với `-Xss` để tính tổng native stack**: một triệu VT không tương ứng một triệu OS stacks. Tuy nhiên các carrier/platform threads vẫn có stack native; VT vẫn tiêu thụ heap và các tài nguyên khác mà công việc của chúng sử dụng (buffers, kết nối, objects).

Khi số thread hoặc `Thread` category tăng, trước tiên xác nhận đó là **platform/OS threads** hay số VT trong ứng dụng. Không kết luận “nhiều VT → nhiều native stacks”.

### 3.3. Chỉ dấu thực tế

```bash
jcmd <PID> Thread.print
jcmd <PID> VM.native_memory summary scale=MB
```

Đọc NMT category `Thread`, số threads và `stack: reserved/committed`. Kết hợp số lượng OS threads từ `/proc/<PID>/status` (Linux: trường `Threads`) hoặc công cụ tương ứng. Với tiến trình có rất nhiều threads, `Thread.print` có thể tạo output lớn; dùng khi cần chẩn đoán có chủ đích.

## 4. Metaspace: metadata của classes và class loaders

### 4.1. Metaspace chứa gì?

HotSpot dùng **metaspace** để lưu metadata cần thiết cho class đã nạp: thông tin class, methods, constant-pool metadata và cấu trúc hỗ trợ. **Java objects của ứng dụng vẫn ở Java heap**; `Class<?>` là Java object trong heap nhưng nhiều cấu trúc mô tả lớp nằm ở vùng metadata riêng.

Metaspace phụ thuộc **số class được load và vòng đời class loader**. Ứng dụng dùng dynamic proxies, bytecode enhancement, scripting, plugin systems, hot reload hoặc tạo class runtime có thể làm metadata tăng. GC chỉ thu hồi metadata khi class/class loader **đủ điều kiện để unload**, nên tăng heap GC frequency không bảo đảm thu hồi metaspace.

Với compressed class pointers, HotSpot có thể sử dụng vùng **compressed class space** cho một số loại class metadata. Vùng này được reserve riêng và có thể có giá trị `reserved` lớn hơn rất nhiều `committed`.

### 4.2. Giới hạn và lỗi

```bash
java -XX:MaxMetaspaceSize=256m -XX:CompressedClassSpaceSize=128m -jar app.jar
```

- `-XX:MaxMetaspaceSize` giới hạn mức sử dụng class metadata theo cơ chế của VM. Không đặt không có nghĩa memory vô hạn; vẫn bị ràng buộc bởi OS/container.
- `-XX:CompressedClassSpaceSize` chi phối vùng cho class metadata dành cho compressed class pointers **khi cơ chế này được bật và áp dụng**. Đây không phải cách giới hạn chung cho toàn bộ metaspace hay mọi native allocations.
- Thiếu chỗ có thể gây `OutOfMemoryError: Metaspace` hoặc `OutOfMemoryError: Compressed class space`, là hai tín hiệu cần phân biệt.

Tăng giới hạn có thể phù hợp nếu workload thật sự cần nhiều class. Nhưng **class loaders bị giữ tham chiếu sau redeploy**, cache static, registry hoặc thread context class loader giữ plugin cũ cũng có thể làm metaspace tăng liên tục. Khi đó tăng giới hạn chỉ trì hoãn vấn đề.

### 4.3. Theo dõi

```bash
jcmd <PID> VM.metaspace basic
jcmd <PID> VM.metaspace show-loaders
jcmd <PID> VM.native_memory summary scale=MB
```

NMT group `Class` thường hiển thị `Metadata`, `Class space`, số class và các lượng `reserved/committed`. `VM.metaspace show-loaders` giúp xem class loader nào giữ metadata; thêm `show-classes` khi thật sự cần mức chi tiết cao hơn. JMX memory pools như `Metaspace` và `Compressed Class Space`, cùng class-loading metrics, giúp theo dõi theo thời gian.

**Gợi ý chẩn đoán:** tổng số classes/loaded loaders tăng không giảm dù workload đã trở về nền, hoặc sau mỗi redeploy lại tạo thêm bản sao classes, là dấu hiệu cần kiểm tra class-loader retention. Không kết luận class-loader leak chỉ vì JVM warm-up làm metaspace tăng một lần rồi ổn định.

## 5. Code cache: mã máy do JIT biên dịch

### 5.1. Code cache khác metaspace

Khi chương trình chạy, HotSpot Just-In-Time compiler chuyển các Java methods thường xuyên thực thi thành **native machine code**. Các đoạn code đó và một số runtime code/stubs được đặt ở **code cache**. Đây là vùng executable memory, khác Java heap (objects) và metaspace (class metadata).

Khi ứng dụng warm-up hoặc có nhiều method/đường code được tối ưu, code cache tăng. HotSpot có cơ chế làm sạch code không còn phù hợp và quản lý các code heaps; một số phiên bản sử dụng **segmented code cache** (profiled nmethods, non-profiled nmethods, non-nmethods). NMT group `Code` phản ánh nhiều thành phần code cache; group `Compiler` phản ánh **working memory phục vụ compiler**, không nên đánh đồng hai group này.

### 5.2. Giới hạn và triệu chứng

```bash
java -XX:ReservedCodeCacheSize=256m -jar app.jar
```

`-XX:ReservedCodeCacheSize` kiểm soát mức reserved tối đa cho code cache theo HotSpot. Nếu code cache không còn chỗ phù hợp, JVM có thể log kiểu **code cache is full** và hoạt động biên dịch JIT có thể bị hạn chế/ngừng; tốc độ ứng dụng có thể giảm dù heap còn trống. Đây thường không biểu hiện giống `OutOfMemoryError: Java heap space`.

Quan sát:

```bash
jcmd <PID> Compiler.codecache
jcmd <PID> Compiler.queue
jcmd <PID> VM.native_memory summary scale=MB
```

`Compiler.codecache` cho các code heap hiện có, size/used/max và trạng thái; `Compiler.queue` kiểm tra công việc biên dịch đang chờ. Kết hợp logs biên dịch khi cần. Không tăng code cache theo phản xạ: cần xem nó thực sự đầy, tốc độ compile, số lượng compiled methods và footprint toàn tiến trình.

## 6. Direct buffers: I/O memory ngoài Java heap

### 6.1. `allocate` và `allocateDirect`

```java
ByteBuffer heapBuffer = ByteBuffer.allocate(1024);
ByteBuffer directBuffer = ByteBuffer.allocateDirect(1024);
```

- `allocate`: tạo buffer dựa trên Java heap (ví dụ là Java byte array).
- `allocateDirect`: tạo direct byte buffer, với dữ liệu thường nằm ngoài Java heap, để JVM cố gắng tránh sao chép trung gian trong native I/O. **Java wrapper object** và các references quản lý nó vẫn sống trong heap.
- `isDirect()` cho biết loại buffer; direct buffer thường tốn chi phí cấp phát/giải phóng lớn hơn nên không mặc định nhanh hơn cho mọi kích thước và cách dùng.

Trong HotSpot, tài nguyên native của nhiều direct buffers được giải phóng khi wrapper hoặc các object giữ tài nguyên đó không còn reachable và cơ chế cleanup có cơ hội chạy. **`buffer = null` không bảo đảm giải phóng tức thì**; các `slice()`, `duplicate()`, cache và retained views có thể kéo dài vòng đời bộ nhớ. Không gọi API nội bộ/Unsafe để ép cleanup một buffer còn đang được dùng.

### 6.2. Giới hạn NIO direct memory

```bash
java -Xmx512m -XX:MaxDirectMemorySize=128m -jar app.jar
```

`-XX:MaxDirectMemorySize` áp dụng cho **nhóm NIO direct-buffer allocations do JDK/VM quản lý**, không phải một quota cho **mọi loại native memory**. Mặc định nếu không chỉ rõ, VM/JDK chọn giới hạn theo chính sách implementation; đừng mặc định mọi phiên bản đều dùng một con số cố định. Nếu hết quota, có thể thấy `OutOfMemoryError` với thông điệp về không thể reserve direct buffer memory (cú pháp thông điệp khác nhau theo bản JDK).

Một direct buffer có capacity 1 MiB có thể chiếm lượng native lớn hơn một chút vì allocator, alignment hoặc metadata; metric capacity không nhất thiết bằng actual memory used. `-XX:MaxDirectMemorySize` cũng **không giới hạn tất cả JNI `malloc`, native library caches, memory-mapped pages hoặc FFM allocations**.

### 6.3. Quan sát qua `BufferPoolMXBean`

Java cung cấp `java.lang.management.BufferPoolMXBean` cho các pool như `direct` và `mapped`:

- `getCount()`: ước lượng số buffers.
- `getTotalCapacity()`: tổng capacity được ước lượng (bytes).
- `getMemoryUsed()`: ước lượng bytes tiêu thụ; có thể trả `-1` nếu không xác định được.
- `getName()`: tên pool; danh sách và phạm vi pool phụ thuộc JVM/provider.

**Tại sao cần cả count, capacity và used?** Một pool có ít buffers nhưng mỗi buffer cực lớn; hoặc nhiều buffers bé với overhead cao. Chỉ nhìn `count` sẽ bỏ sót mẫu dùng bộ nhớ. Còn tổng memoryUsed của buffer pools **không phải** toàn bộ off-heap trong tiến trình.

**Memory-mapped files:** `FileChannel.map` tạo `MappedByteBuffer` gắn với trang file và paging của OS. Nó không nên được xem giống hoàn toàn một `allocateDirect` dùng anonymous native memory; quan sát pool `mapped`, memory mappings, RSS/page cache theo ngữ cảnh và xử lý lifecycle của file/mappings phù hợp.

## 7. Native libraries: JNI, FFM, allocator và mappings

Một chương trình Java có thể dùng native code qua **JNI**, thư viện có `.so`/`.dll`/`.dylib`, thư viện đồ họa/mã hóa/nén, hoặc **Foreign Function & Memory API (FFM)** ở JDK hỗ trợ. Chúng có thể:

- Cấp phát `malloc`, `calloc`, native arenas hoặc `mmap`.
- Tạo OS threads, bộ nhớ thread-local, native caches, TLS buffers, handles và cấu trúc unmanaged.
- Map executable code, data và shared-library pages vào không gian địa chỉ tiến trình.
- Giữ vùng nhớ dù Java wrapper đã nhỏ hoặc không hiển thị rõ trong heap dump.

Native code phải quản lý cặp acquire/release đúng contract của từng thư viện; ví dụ JNI cần giải phóng native allocations của mình, FFM arenas cần được đóng theo vòng đời thích hợp. Nếu giữ con trỏ trỏ tới vùng đã giải phóng hoặc đóng arena quá sớm, có thể phát sinh crash/use-after-free; nếu không giải phóng, có thể xảy ra native leak.

**Giới hạn quan trọng của NMT:** Native Memory Tracking của HotSpot theo dõi **bộ nhớ được chính HotSpot/JVM tracking**, không bao trùm mọi allocations do JNI, native libraries hoặc các phần class library thực hiện. Vì vậy **NMT ổn định không có nghĩa native memory của toàn tiến trình ổn định**. Khi nghi ngờ native code, dùng profiler/allocator instrumentation đúng nền tảng hoặc metrics do chính thư viện cung cấp, kết hợp công cụ OS.

`System.gc()` không phải cơ chế sửa native leak. Garbage collection có thể giúp một số wrapper được cleanup khi chúng không còn reachable, nhưng không giải phóng vùng đã bị native code quên release hay vùng đang bị giữ tham chiếu.

## 8. Quan hệ giữa các cờ giới hạn và lỗi

| Cờ/giới hạn | Phạm vi chính | Không giới hạn |
| --- | --- | --- |
| `-Xmx` | Java heap maximum | Native stacks, metaspace, code cache, direct/native libraries |
| `-Xss` | Stack size mỗi platform thread theo VM/OS | Tổng số thread, tất cả native memory |
| `-XX:MaxMetaspaceSize` | Class metadata trong metaspace | Direct buffers, stacks, JNI allocations |
| `-XX:CompressedClassSpaceSize` | Compressed class metadata space khi dùng | Toàn bộ metaspace và native libraries |
| `-XX:ReservedCodeCacheSize` | JIT code cache | Metaspace, heap hay tất cả compilation working data |
| `-XX:MaxDirectMemorySize` | NIO direct-buffer allocations phù hợp | JNI `malloc`, memory mappings, toàn bộ off-heap |
| cgroup `memory.max`, OS memory limit | Tài nguyên được tính cho container/tiến trình theo OS | Không phân loại JVM subsystem và không thay đổi cách JVM bookkeeping nội bộ |

Một ví dụ sai lầm phổ biến: container có giới hạn 2 GiB nhưng đặt `-Xmx2g`, mặc định còn kỳ vọng không có native overhead. **Ngay cả khi heap chưa đạt Xmx**, process vẫn cần thread stacks, class metadata, JIT code, GC data và buffers. Nên thiết kế headroom cho native memory bằng **dữ liệu quan sát ở tải cao**, thay vì cộng các `reserved` values làm số RAM thật.

### Những lỗi thường gặp có ý nghĩa khác nhau

| Dấu hiệu | Khả năng nổi bật | Việc cần xác nhận |
| --- | --- | --- |
| `OutOfMemoryError: Java heap space` | Java heap không còn chỗ cho objects | Heap dump, retained objects, allocation rate, `-Xmx` |
| `OutOfMemoryError: Metaspace` | Metadata không còn chỗ theo giới hạn | Số class/loaders, `VM.metaspace`, Class NMT |
| `OutOfMemoryError: Compressed class space` | Giới hạn class space riêng | Compressed class space use/committed/limit |
| `OutOfMemoryError: unable to create native thread` | Không tạo được OS thread | OS thread count, PID limits, stack, native memory |
| `OutOfMemoryError` nhắc `direct buffer memory` | NIO direct-buffer quota/cấp phát thất bại | BufferPoolMXBean, capacity/used, retention |
| `CodeCache is full` trong JVM logs | Vùng code cache đầy/hạn chế JIT | `Compiler.codecache`, hiệu năng warm-up và logs |
| Container `OOMKilled` mà không có Java stack trace | OS/cgroup chọn kill do áp lực bộ nhớ | `memory.events`, RSS/cgroup usage, NMT và mappings |

Các thông điệp cụ thể thay đổi theo JDK/OS; một lỗi có thể có nhiều nguyên nhân, cần lấy evidence thay vì suy luận từ câu chữ duy nhất.

## 9. Native Memory Tracking (NMT) từ con số đến chẩn đoán

### 9.1. Bật NMT từ lúc khởi động

```bash
java -XX:NativeMemoryTracking=summary -Xmx512m -jar app.jar
```

NMT **tắt mặc định** trên nhiều bản HotSpot. Nó có hai mức:

- `summary`: thống kê theo JVM subsystem/category, thường là điểm khởi đầu phù hợp nhất.
- `detail`: cộng thêm call-site và bản đồ vùng địa chỉ, dùng khi summary chưa đủ. NMT làm tăng chi phí bộ nhớ/CPU; tài liệu Oracle ghi nhận overhead có thể khoảng **5–10%**, nên bật có chủ đích.

Không thể bật hoặc nâng mức NMT từ `off` lên `summary/detail` cho một JVM đã chạy chỉ bằng `jcmd`; hãy cấu hình **khi khởi động** rồi chạy lại phiên chẩn đoán khi phù hợp. `jcmd` chủ yếu dùng để **đọc** số liệu, tạo baseline, diff hoặc tắt NMT.

```bash
jcmd -l
jcmd <PID> VM.native_memory summary scale=MB
jcmd <PID> VM.native_memory baseline
```

Sau khi tải thực đã chạy một khoảng thời gian, đọc mức thay đổi kể từ baseline:

```bash
jcmd <PID> VM.native_memory summary.diff scale=MB
```

Nếu đã bật `-XX:NativeMemoryTracking=detail` từ đầu:

```bash
jcmd <PID> VM.native_memory detail scale=MB
jcmd <PID> VM.native_memory detail.diff scale=MB
```

`summary.diff` và `detail.diff` cần **baseline trước đó**. Đặt baseline sau warm-up (nếu muốn tìm leak trong steady state), chạy **cùng loại workload** đủ lâu, rồi so sánh nhiều lần. Quan sát chênh lệch ngày càng lớn có ý nghĩa hơn một snapshot lớn đơn lẻ.

### 9.2. Đọc các category NMT

Ví dụ **minh họa cách đọc**, không phải output cố định của một chương trình:

```text
Total: reserved=2600MB, committed=920MB
- Java Heap (reserved=1536MB, committed=480MB)
- Class     (reserved=1040MB, committed=36MB)
- Thread    (reserved=160MB,  committed=24MB)
- Code      (reserved=240MB,  committed=90MB)
```

Các dòng ở ví dụ được rút gọn và **không nhằm cộng thành tổng thực** (còn rất nhiều category khác). Điều cần chú ý:

- `Java Heap`: vẫn xuất hiện trong NMT. NMT **không phải** bảng chỉ có memory ngoài heap; khi phân tích native phải tách category heap.
- `Class`: metadata và class space. Trường `reserved` lớn chưa chứng minh class leak.
- `Thread`: thread structures và stack; đọc thêm `stack: reserved/committed` cùng OS thread counts.
- `Code`: mã runtime/JIT. Đừng nhầm với `Compiler` là dữ liệu làm việc của JIT compiler.
- `GC`, `Internal`, `Symbol`, `Arena Chunk`, `Native Memory Tracking`, các nhóm khác: đều có thể tiêu thụ native memory đáng kể tùy workload/JDK.

**NMT committed khác RSS.** NMT theo dõi một phạm vi HotSpot; RSS phản ánh những trang resident của process và còn có allocations/mappings bên ngoài phạm vi NMT. Vì thế không lấy `RSS - NMT committed` rồi khẳng định hiệu số chính xác là “JNI leak”: có thể có shared pages, allocator fragmentation, class library allocations hoặc đặc điểm paging.

### 9.3. Kết hợp đúng công cụ

| Khi cần biết | Công cụ | Cách dùng kết quả |
| --- | --- | --- |
| Native memory do HotSpot dùng tăng ở group nào | `jcmd VM.native_memory summary.diff` | Xác định `Thread`, `Class`, `Code`, `GC`, ... |
| Metaspace tăng do loaders nào | `jcmd VM.metaspace show-loaders` | Lần về framework, plugin, redeploy hoặc codegen |
| Code cache đầy hay đang tăng | `jcmd Compiler.codecache` | Đánh giá used/free và JIT compilation status |
| Direct-buffer pool tăng | `BufferPoolMXBean` / JMX | Xem count, capacity, used, retention |
| OS thread count nhiều | OS `/proc/<PID>/status`, `Thread.print` | So sánh platform-thread count và stack pressure |
| Tổng footprint tăng trong Linux | `/proc/<PID>/status`, `/proc/<PID>/smaps_rollup`, `pmap` | Kiểm tra RSS, mappings, anonymous/file-backed regions |
| Container gần OOM | cgroup `memory.current`, `memory.max`, `memory.events` | Kiểm tra mức dùng và dấu hiệu OOM-kill |
| NMT không tăng nhưng RSS tăng | OS profiler/native allocator tools | Tìm JNI/library allocator, mapping, fragmentation, page residency |

Linux ví dụ đọc trực tiếp (điền PID phù hợp):

```bash
grep -E 'VmRSS|VmSize|Threads' /proc/<PID>/status
cat /proc/<PID>/smaps_rollup
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.events
```

Trên cgroup v2, các file `memory.current` và `memory.events` nằm ở **cgroup chứa tiến trình**, không nhất thiết ở root path ví dụ trên. `memory.current` cũng có phạm vi accounting của cgroup, **không đồng nhất** với RSS một PID. Trên Windows/macOS, dùng công cụ process/memory-map tương ứng. Hãy phân biệt số liệu theo **PID, process tree, container/cgroup và host** trước khi so sánh.

## 10. Lab Java 17+: đối chiếu heap buffer và direct buffer

Tạo file **`OffHeapSourcesDemo.java`** dưới thư mục làm việc. Ví dụ dùng ~1 MiB direct memory, đủ nhỏ để chạy cục bộ; tùy chọn `hold` giữ tiến trình sống 60 giây để attach `jcmd`.

```java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;

public class OffHeapSourcesDemo {
    private static ByteBuffer retained;

    public static void main(String[] args) throws InterruptedException {
        ByteBuffer heap = ByteBuffer.allocate(32);
        retained = ByteBuffer.allocateDirect(1024 * 1024);
        retained.putInt(0, 42);

        System.out.println("heap.isDirect=" + heap.isDirect());
        System.out.println("direct.isDirect=" + retained.isDirect());
        System.out.println("direct.value=" + retained.getInt(0));

        for (BufferPoolMXBean pool : ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
            if ("direct".equals(pool.getName())) {
                System.out.println("pool.name=" + pool.getName());
                System.out.println("pool.count=" + pool.getCount());
                System.out.println("pool.capacityBytes=" + pool.getTotalCapacity());
                System.out.println("pool.usedBytes=" + pool.getMemoryUsed());
            }
        }

        if (args.length == 1 && "hold".equals(args[0])) {
            System.out.println("pid=" + ProcessHandle.current().pid());
            Thread.sleep(60_000);
        }
    }
}
```

Biên dịch và chạy với JDK 17+:

```bash
javac OffHeapSourcesDemo.java
java -XX:NativeMemoryTracking=summary -XX:MaxDirectMemorySize=128m OffHeapSourcesDemo
```

**Ba dòng đầu của stdout** (ổn định với ví dụ):

```text
heap.isDirect=false
direct.isDirect=true
direct.value=42
```

Các dòng sau in tên `direct` và các số liệu `pool.count`, `pool.capacityBytes`, `pool.usedBytes`; giá trị cụ thể phụ thuộc JVM và các buffer khác trong cùng tiến trình. Ví dụ chạy trên một JDK sạch có thể thấy `pool.capacityBytes=1048576`, nhưng **không coi đây là output cố định trên mọi môi trường**.

Để thu snapshot trong khi chương trình còn chạy, khởi chạy lại với `hold`:

```bash
java -XX:NativeMemoryTracking=summary -XX:MaxDirectMemorySize=128m OffHeapSourcesDemo hold
```

Chương trình in thêm `pid=<một số PID>`, giữ process sống khoảng một phút. Mở terminal thứ hai, thay PID bằng số thực tế đã in:

```bash
jcmd <PID> VM.native_memory summary scale=MB
jcmd <PID> VM.metaspace basic
jcmd <PID> Compiler.codecache
```

**Điều quan trọng nhất từ lab:** object `retained` nằm trong Java heap còn dữ liệu của direct buffer thường nằm ngoài heap; `isDirect()` giúp phân loại, `BufferPoolMXBean` theo dõi NIO buffer pool, NMT theo dõi các category HotSpot. Không yêu cầu NMT `Other` tăng chính xác 1 MiB tương ứng `allocateDirect` vì NMT **không cam kết** bao phủ toàn bộ allocations của Java class libraries.

Có thể thử chạy với direct memory limit nhỏ hơn kích thước buffer để hiểu quota, nhưng đừng lấy một thông điệp lỗi cụ thể làm output chuẩn cho mọi JDK; còn có padding/alignment và allocator behavior.

## 11. Quy trình chẩn đoán năm nguồn bộ nhớ

**Tình huống A — heap ổn định, RSS tăng cùng số OS threads.** Đo platform-thread count và `Thread` NMT, kiểm tra có pool mở rộng không giới hạn hay thread không kết thúc. Sửa lifecycle/thread pool, kiểm tra số native threads và headroom; xem `-Xss` như công cụ tuning có giới hạn, không là giải pháp thay cho bound concurrency.

**Tình huống B — số classes và `Class` NMT tăng theo mỗi lần deploy.** Dùng `VM.metaspace show-loaders`, logs class load/unload hoặc class-loader analysis; tìm loader/plugin cũ bị giữ, static cache hoặc thread-context references. Khắc phục retention rồi quan sát metaspace giảm hoặc ổn định; chỉ điều chỉnh `MaxMetaspaceSize` dựa trên nhu cầu thực.

**Tình huống C — JVM log code cache full, throughput giảm sau warm-up.** Đọc `Compiler.codecache`, logs JIT, kích thước `ReservedCodeCacheSize`. Nếu đã chứng minh code cache thiếu và có đủ native headroom, điều chỉnh kích thước và kiểm tra hiệu năng; không xử lý bằng tăng Java heap nếu nguyên nhân ở code cache.

**Tình huống D — NIO networking tăng direct memory theo tải, có `direct buffer memory` OOME.** Theo dõi `BufferPoolMXBean` theo thời gian; kiểm tra pooling, cache, `slice`/`duplicate` giữ buffer gốc, I/O lifecycle và backpressure. Cân đối lại buffer pool sizing hoặc giới hạn concurrency. Tăng `MaxDirectMemorySize` chỉ khi cần và không vượt budget container.

**Tình huống E — RSS/container memory tăng nhưng NMT categories gần như ổn định.** Xác nhận số liệu cùng thời điểm, kiểm tra native library allocations, memory mappings, fragmentation, cgroup page cache, shared pages; dùng native allocator profiler hoặc tools OS. Đừng dùng kết quả NMT ổn định để kết luận không có native leak.

**Tình huống F — container bị OOMKilled không có heap OOME.** Lấy cgroup `memory.events`, memory limit, RSS/mapping, heap committed, NMT committed, direct pool metrics, JVM flags. Ghi rõ process có JVM và service phụ khác trong cùng cgroup không. Heap dump sẽ không tự giải thích toàn bộ native allocations; hãy lấy dữ liệu sớm trước khi process bị kill.

### Mẫu ghi chép một đợt chẩn đoán

Lưu ít nhất: **JDK/VM version; OS/container/cgroup limit; `-Xmx`, `-Xss`, metaspace/code-cache/direct limits; NMT mode; thời điểm baseline; throughput/tải; heap used/committed; `Class/Thread/Code` NMT; direct pool count/capacity/used; RSS/container memory; error/log gần thời điểm tăng**.

Từ đó kết luận theo **xu hướng**, không theo một ảnh chụp: category nào tăng trước, có tương quan với workload hoặc số thread/class/buffer không, NMT có quan sát được nguồn nghi ngờ không, và thay đổi đã xác nhận bằng điều kiện chạy tương đương hay chưa.

## 12. Các nhầm lẫn cần tránh

1. **“Heap usage thấp nên process không thể OOM.”** Sai: native memory và OS/container accounting vẫn có thể chạm giới hạn.
2. **“Reserved của metaspace/class space = RAM đang dùng.”** Sai: phải phân biệt reserved, committed, used và RSS.
3. **“`MemoryMXBean.getNonHeapMemoryUsage()` là tổng mọi off-heap.”** Sai: đó là các memory pools JVM định nghĩa, thường không gồm thread stacks, JNI allocations và toàn bộ direct memory.
4. **“Mỗi virtual thread cần một `-Xss` native stack.”** Sai: virtual thread stacks chủ yếu là heap-backed stack chunks; carrier platform threads vẫn có native stacks.
5. **“Tăng `-XX:MaxDirectMemorySize` thì hết native OOM.”** Sai: nó không giới hạn hay sửa các allocations từ JNI/FFM, thread stacks, code cache và libraries.
6. **“NMT `Other` luôn bằng direct buffer usage.”** Sai: NMT không thống kê toàn bộ vùng memory do Java libraries/native libraries cấp phát; dùng thêm BufferPoolMXBean.
7. **“Thấy code cache lớn là leak.”** Sai: warm-up/JIT hợp lệ có thể làm tăng tới plateau; cần kiểm tra full state và xu hướng.
8. **“Metaspace sẽ giảm ngay mỗi lần GC.”** Sai: class unloading phụ thuộc khả năng thu hồi class loader, references và chính sách runtime.
9. **“`-Xss` nhỏ nhất luôn tiết kiệm RAM nhất.”** Sai: rủi ro stack overflow, guard/alignment, giới hạn OS, và RSS không bằng reserved.
10. **“Một heap dump sẽ chứa hết native memory.”** Sai: heap dump chủ yếu hiển thị Java objects/wrappers và đường retention; native bytes thường cần NMT, JMX, OS/native tools.
11. **“RSS − NMT committed = chính xác JNI allocations.”** Sai: phạm vi đo, mapping, resident pages, fragmentation và shared memory khác nhau.
12. **“Giới hạn container bằng `-Xmx`.”** Sai: `-Xmx` chỉ là maximum heap; cần native headroom và theo dõi cgroup.

## 13. Checklist áp dụng

- [ ] Xác nhận **JDK/OS/container**, tổng footprint và các JVM flags thật đang dùng.
- [ ] Phân biệt heap used/committed với native sources; ưu tiên quan sát **thay đổi theo thời gian**.
- [ ] Dùng NMT `summary`/`summary.diff` cho `Thread`, `Class`, `Code` và các JVM categories khác; chọn `detail` từ lúc khởi động nếu cần call-site evidence.
- [ ] Dùng `VM.metaspace`, `Compiler.codecache`, thread metrics, `BufferPoolMXBean`, OS memory maps và cgroup memory theo từng giả thuyết.
- [ ] Nhận biết phần **JNI/native library** không được NMT phủ hết; đo bằng công cụ native khi cần.
- [ ] Kiểm chứng nguyên nhân qua lifecycle, counters và workload; sửa retention/bounds trước khi tăng quota.
- [ ] Đánh giá lại throughput, latency, peak RSS/container usage và số liệu bộ nhớ sau thay đổi.

**Điểm cốt lõi:** năm nguồn bộ nhớ khác nhau về **người cấp phát, vòng đời, công cụ đo và giới hạn**. Một tiến trình Java có thể hết native memory mà Java heap không đầy. Chẩn đoán đúng đòi hỏi nối số liệu **JVM + JMX + OS/container**, đọc đúng đơn vị và giới hạn của từng nguồn.

## Tài liệu tham khảo

- [Oracle Java 21 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html)
- [Oracle Java 21 — Diagnostic Tools / NMT categories](https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html)
- [Oracle Java 21 — `java` options: `-Xss`, metaspace, direct memory, code cache](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [Oracle Java 21 — `jcmd` diagnostic commands](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html)
- [Oracle Java 21 — `ByteBuffer` direct vs non-direct](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/ByteBuffer.html)
- [Oracle Java 21 — `BufferPoolMXBean`](https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/BufferPoolMXBean.html)
- [OpenJDK — JEP 444: Virtual Threads](https://openjdk.org/jeps/444)
