# Phân biệt vùng heap đối tượng với bộ nhớ ngoài heap khi đặt Java heap trên thiết bị bộ nhớ (Java 10+)

## 1. Câu hỏi trọng tâm: Java heap nằm trên thiết bị khác có trở thành “off-heap” không?

**Không.** Trong HotSpot, **Java object heap** được hiểu theo **vai trò quản lý bộ nhớ**: nơi lưu phần lớn đối tượng Java do JVM quản lý bằng garbage collector (GC). Việc chuyển **vị trí vật lý của vùng heap ấy** sang một loại thiết bị bộ nhớ khác không đổi nó thành bộ nhớ “off-heap”.

Đó là điều cốt lõi để hiểu **JEP 316 — Heap Allocation on Alternative Memory Devices**, được triển khai trong **Java 10**. Với tùy chọn HotSpot `-XX:AllocateHeapAt=<path>`, JVM có thể dùng cơ chế memory mapping đặt **Java object heap** lên một thiết bị bộ nhớ được hệ điều hành trình bày thông qua filesystem, ví dụ một vùng **NV-DIMM** hỗ trợ truy cập kiểu bộ nhớ.

Điều đó **không** có nghĩa:

- mọi vùng bộ nhớ của JVM cùng chuyển sang thiết bị ấy;
- Java objects trở thành những bytes do lập trình viên tự giải phóng;
- bộ thu gom rác bị bỏ qua;
- `new` tự động cấp phát off-heap theo nghĩa `ByteBuffer.allocateDirect`;
- dữ liệu đối tượng có thể được khôi phục trực tiếp sau restart như database;
- `-Xmx` không còn giới hạn object heap.

Ngược lại, **bộ nhớ ngoài Java heap** (*off-heap* theo ngữ cảnh ứng dụng) thường là những vùng byte/native allocations **không nằm trong Java object heap**, chẳng hạn nội dung của direct NIO buffers, bộ nhớ được cấp qua Foreign Function & Memory API hoặc vùng ánh xạ file. Đây là trục phân loại **khác** với trục “DRAM hay thiết bị bộ nhớ khác”.

### Mục tiêu bài học

Sau bài, bạn có thể:

1. Phân biệt **Java object heap**, **JVM non-heap memory**, **native/off-heap memory** và **memory-mapped files**.
2. Giải thích chính xác JEP 316 chuyển **vị trí của object heap** nhưng vẫn giữ nguyên GC/`-Xmx`.
3. Biết phần nào của JVM **vẫn nằm ngoài object heap**, ví dụ metaspace, code cache, thread stacks.
4. Phân tích sự khác biệt giữa `byte[]`, `ByteBuffer.allocate`, `ByteBuffer.allocateDirect` và `MappedByteBuffer`.
5. Không nhầm `MemoryMXBean.getNonHeapMemoryUsage()` với **toàn bộ native memory**.
6. Dùng `BufferPoolMXBean`, `jcmd VM.native_memory`, GC logs và số liệu RSS/container để chẩn đoán.
7. Hiểu vòng đời, khả năng thu hồi, quota, lỗi OOME và giới hạn của việc dùng bộ nhớ ngoài heap.
8. Chạy ví dụ Java 17+ bằng API chuẩn, không cần phần cứng NV-DIMM thật.
9. Tránh API hoặc mẹo lỗi thời theo Special Note; chỉ dùng các cơ chế vẫn còn hiện hành.

## 2. Hai trục phân loại bộ nhớ phải tách nhau

### Trục A: **Ai quản lý vùng nhớ và bằng cơ chế nào?**

- **Java object heap (GC-managed):** JVM cấp phát đối tượng và giải phóng các đối tượng không còn reachable theo thuật toán GC.
- **JVM non-heap memory:** vùng cần cho thực thi VM nhưng không phải object heap, điển hình là **metaspace/class metadata** và **code cache/JIT-compiled code**.
- **Off-heap/native memory:** những vùng được cấp phát bên ngoài Java object heap, ví dụ phần dữ liệu của direct buffers hoặc allocations do thư viện native quản lý.
- **Mapped file memory:** vùng địa chỉ ảo ánh xạ file; chính sách residency và đồng bộ xuống file có quy tắc OS/file mapping riêng.

### Trục B: **Dữ liệu vật lý được đặt ở đâu?**

- DRAM thông thường.
- Một loại **alternative memory device** có semantic cần thiết để dùng như memory.
- Vùng file mapping qua filesystem đặc biệt, chẳng hạn thiết bị có **DAX** (*direct access*) khi được hỗ trợ.
- Những pages được OS phân phối/swap/map theo chính sách của hệ thống.

**JEP 316 thay đổi chủ yếu trục B của Java object heap**, không định nghĩa lại trục A. Một đối tượng `Customer` được tạo bằng `new Customer(...)` vẫn là **đối tượng Java do GC quản lý**, kể cả khi những trang vật lý backing heap được ánh xạ tới thiết bị memory khác.

### Sơ đồ khái niệm

```text
                      Một tiến trình HotSpot JVM
+--------------------------------------------------------------+
| Java object heap                                             |
|   new Order(...)  /  new byte[...]  /  String / wrapper...   |
|   GC theo dõi và thu hồi                                     |
|   Có thể được đặt trên alternative memory device (JEP 316)   |
+--------------------------------------------------------------+
| JVM non-heap structures                                      |
|   class metadata / metaspace, code heap, runtime metadata    |
|   Không tự chuyển sang device chỉ vì AllocateHeapAt          |
+--------------------------------------------------------------+
| Native and other process memory                              |
|   native stacks, JNI/native allocations, direct-buffer data  |
|   mapped files, allocator overhead, VM internal data         |
|   Không tự thuộc Java object heap                            |
+--------------------------------------------------------------+
                Linux/OS virtual memory mappings
                  DRAM / file backing / device
```

Sơ đồ chỉ phân tách **vai trò**, không thể hiện chính xác mọi mapping nội bộ. Những nhóm đo của Native Memory Tracking, OS process memory và Java Management API **không nhất thiết chia cùng ranh giới hoặc cộng trực tiếp**.

## 3. Java object heap là gì?

Java object heap là vùng phục vụ **cấp phát các đối tượng Java** và được JVM/GC quản lý. Những ví dụ thường liên quan:

```java
record Item(String name, int quantity) {}

Item item = new Item("pen", 3);
byte[] bytes = new byte[1024];
String text = "Java";
```

Đây là **đoạn minh họa**, không phải chương trình độc lập. Các đối tượng Java tương ứng được quản lý theo ngữ nghĩa của Java heap. JVM có thể áp dụng escape analysis, scalar replacement hoặc các tối ưu khác làm một đối tượng không cần cấp phát vật lý theo hình thức mà ta tưởng tượng; điều đó không biến semantics của Java reference thành raw off-heap pointer.

### 3.1. Đặc điểm quản lý

- Các đối tượng được truy cập qua **Java references**, không phải các địa chỉ native do code Java thông thường tự cộng/trừ.
- **GC** xác định object graph còn reachable và tái sử dụng vùng của đối tượng không còn cần thiết.
- GC có thể **di chuyển hoặc compact** các đối tượng, tùy collector và phase.
- Không có API chuẩn bắt lập trình viên gọi `free(Object)` để giải phóng đối tượng Java.
- **Giới hạn heap** liên quan `-Xmx`/`-XX:MaxHeapSize`; heap size không bao gồm mọi chi phí native của tiến trình.

### 3.2. `-Xmx` giới hạn gì?

```bash
java -Xms64m -Xmx512m MyApplication
```

`MyApplication` ở đây là tên main class **minh họa**. Ý nghĩa:

- `-Xms64m`: chỉ định kích thước heap ban đầu/tối thiểu theo hợp đồng launcher tương ứng.
- `-Xmx512m`: đặt giới hạn tối đa của **Java object heap** khoảng 512 MiB.
- Các vùng **metaspace, code cache, native stacks, direct-buffer contents** không cùng là đối tượng tiêu thụ của giới hạn `-Xmx`.

Không kết luận “`-Xmx512m` nghĩa process RSS không thể vượt 512 MiB”. Tiến trình JVM còn nhiều vùng bộ nhớ, mapping và overhead.

### 3.3. Khi đặt object heap trên thiết bị khác

Với `-XX:AllocateHeapAt`, `-Xmx` và các cờ GC thông thường **tiếp tục có ý nghĩa** đối với object heap. Collector vẫn xác định đối tượng sống/chết và dùng các vùng heap như Java heap thông thường; thay đổi vị trí backing memory **không trao quyền truy cập bộ nhớ thô cho các class Java**.

Nếu GC báo `java.lang.OutOfMemoryError: Java heap space`, không nên coi việc tăng kích thước **native direct memory** là cách sửa trực tiếp, vì hai vùng có giới hạn và cơ chế quản lý khác nhau.

## 4. JEP 316 (Java 10): object heap trên alternative memory device

### 4.1. Mục đích và cơ chế

**JEP 316 — Heap Allocation on Alternative Memory Devices** giúp HotSpot có khả năng phân bổ **Java object heap** trên một thiết bị bộ nhớ do người vận hành chọn, ví dụ NV-DIMM khi đáp ứng yêu cầu của bộ nhớ truy cập trực tiếp.

Flag trong tài liệu launcher JDK hiện hành vẫn tồn tại:

```text
-XX:AllocateHeapAt=<path>
```

Nó nhận **đường dẫn filesystem** mà JVM sử dụng để tạo memory mapping cho object heap trên thiết bị thích hợp. Một số filesystem expose non-DRAM memory với **DAX** để memory mapping có thể truy cập thiết bị trực tiếp và tránh đi qua page cache theo cơ chế thông thường.

**Điều kiện nền tảng:** thiết bị memory phải cung cấp các semantic như DRAM cần cho object heap, gồm thao tác nguyên tử (*atomic operations*) và memory access phù hợp. Đây **không** chỉ là câu chuyện có một ổ đĩa nhanh hoặc một thư mục ghi được.

### 4.2. Tùy chọn này còn được hỗ trợ chứ?

Tài liệu **Oracle Java SE 27 — The java Command** vẫn mô tả `-XX:AllocateHeapAt=path`, ý nghĩa mapping heap trên alternative memory device, và nhấn mạnh những cấu trúc như code heap, metaspace và thread stacks vẫn ở DRAM.

Vì vậy, về kiến thức **vẫn áp dụng**, phải phân biệt:

- **Cơ chế/flag hiện hành:** tài liệu launcher vẫn mô tả.
- **Tính khả dụng ở máy cụ thể:** phụ thuộc OS, HotSpot build, filesystem, DAX/device, quyền và triển khai.
- **Giá trị sử dụng thực tế:** cần benchmark latency/bandwidth/GC trên phần cứng mục tiêu; không mặc định tốt hơn DRAM.
- **Vòng đời sản phẩm phần cứng:** không nên học JEP 316 bằng cách yêu cầu mua một dòng NV-DIMM cũ nếu hạ tầng không hỗ trợ.

### 4.3. Điều gì vẫn ở DRAM?

Tài liệu launcher nêu rõ: khi chuyển **object heap** sang thiết bị thay thế, các cấu trúc còn lại như:

- **code heap / JIT code cache**;
- **metaspace / class metadata**;
- **thread stacks**;

vẫn ở DRAM trong mô hình được mô tả. Ngoài ra còn có các vùng native/VM khác. Flag **không chuyển toàn bộ tiến trình JVM** sang device.

Đây là chỗ dễ hiểu sai nhất: chữ “heap” trong `AllocateHeapAt` nghĩa **Java object heap**, không phải một công tắc “mọi thứ gọi là heap của native allocators”.

### 4.4. Không nhầm alternative heap với heap persistence

Ngay cả khi **NV-DIMM là công nghệ non-volatile**, HotSpot không tự biến các đối tượng Java thành database persistent:

- Object graph có headers, references và cấu trúc GC phụ thuộc một phiên JVM đang chạy.
- Các Java references không được thiết kế như địa chỉ bền vững có thể khôi phục tùy ý sau restart.
- Memory mapping của heap phục vụ **runtime allocation**, không phải hợp đồng transaction/serialization/consistency.
- Một JVM mới không được mặc định “gắn lại” object heap cũ như một Java heap hợp lệ.
- Xử lý crash recovery, transaction log, persistence schema, flush/ordering và security retention là bài toán **khác**.

**Không dùng `-XX:AllocateHeapAt` để thay database, object serialization hay một hệ thống persistent-memory data structure chuyên dụng.**

### 4.5. Không thử trên thư mục thông thường để giả làm NV-DIMM

Cú pháp mang tính cấu hình trên hạ tầng đã được chuẩn bị:

```bash
java -Xms2g -Xmx2g -XX:AllocateHeapAt=/mnt/pmem \
     -XX:+UseG1GC com.example.Main
```

Đây là **lệnh minh họa**, chỉ phù hợp khi `/mnt/pmem` thực sự là điểm mount của một thiết bị/file system được HotSpot và OS hỗ trợ, đủ dung lượng/quyền truy cập. Không chạy nguyên lệnh trên máy học có ổ đĩa thường rồi cho rằng nó đã kiểm thử NV-DIMM; cũng không tạo file/thư mục bừa trên host để thay thiết bị thật.

Cờ `-Xms`, `-Xmx` và `-XX:+UseG1GC` vẫn có ý nghĩa; **thay đổi memory backing** không xóa GC.

### 4.6. Những gì cần kiểm tra trước khi triển khai JEP 316

1. Có hardware/alternative memory device thật phù hợp không?
2. Kernel/filesystem/DAX mode có hỗ trợ đúng semantic về memory mapping/atomic operation không?
3. HotSpot JDK vendor/version/architecture có hỗ trợ flag trên OS đó không?
4. Đường dẫn thực sự trỏ đến mount đúng, có dung lượng và quyền phù hợp không?
5. Có container mount namespace/SELinux/AppArmor policy tác động không?
6. Heap `-Xmx` cần bao nhiêu vùng backing memory; có đủ headroom không?
7. Nếu device có băng thông/độ trễ khác DRAM, GC pause, allocation latency và application throughput thay đổi ra sao?
8. Có chính sách cleanup, kiểm soát truy cập, bảo mật dữ liệu trên thiết bị sau shutdown/crash không?
9. Có cơ chế fallback/rollout/rollback rõ nếu mapping không khả dụng không?
10. Những native structures vẫn ở DRAM có đủ memory budget không?

Không viết một benchmark kết luận “NV-DIMM luôn nhanh hơn DRAM” khi chưa chạy trên phần cứng thật. Trong nhiều workload, chuyển object heap sang memory chậm hơn có thể **làm xấu latency**.

## 5. “Off-heap” trong Java thực tế bao gồm những gì?

Thuật ngữ **off-heap** thường được dùng trong kiến trúc ứng dụng để chỉ bộ nhớ **ngoài vùng Java object heap**. Nhưng nó không phải một vùng đơn nhất có một allocator hay một garbage collector duy nhất.

### 5.1. Bảng so sánh những vùng thường gặp

| Vùng / tài nguyên | Có thuộc Java object heap không? | Ai quản lý? | Cách quan sát nổi bật |
| --- | --- | --- | --- |
| `new byte[SIZE]` | **Có**, về semantics Java | JVM/GC | Heap MXBean, GC/heap dump |
| `new Order(...)`, `String` | **Có**, về semantics Java | JVM/GC | Heap profiling, MemoryMXBean |
| `ByteBuffer.allocate(SIZE)` | **Non-direct**; thường backed bởi mảng heap | JVM/GC | `isDirect=false`, heap metrics |
| **Nội dung** `ByteBuffer.allocateDirect(SIZE)` | Thường **ngoài object heap** | HotSpot native allocator; lifecycle gắn với buffer/cleaner | `BufferPoolMXBean("direct")`, native metrics |
| Object wrapper của một **direct ByteBuffer** | **Có**, là Java object | JVM/GC | Heap profiling |
| `FileChannel.map` / `MappedByteBuffer` | File mapping **ngoài object heap** | OS mapping; vòng đời gắn với buffer/mapping | `BufferPoolMXBean("mapped")`, OS mapping |
| **Metaspace/class metadata** | **Không** | VM/native memory allocator | Non-heap MXBean, NMT `Class` |
| **JIT code cache** | **Không** | VM/native code cache | Non-heap/code-cache pool, NMT `Code` |
| **Java thread native stacks** | **Không** | OS/JVM thread stacks | NMT `Thread`, OS thread count |
| **JNI/native library allocations** | **Không** | Native code và allocator tương ứng | OS tools, native profiler, NMT một phần |
| **FFM `Arena` / `MemorySegment`** (JDK 22+) | Native segment có thể ngoài heap | Arena/lifetime scope theo API | API scope, native/process metrics |
| Java object heap trên **`AllocateHeapAt` device** | **Có**, vẫn là **Java heap** | JVM/GC | Heap MXBean, GC logs, OS mappings |

Một object **ByteBuffer wrapper** và **vùng bytes mà nó đại diện** có thể thuộc **hai vùng quản lý khác nhau**. Đây là ví dụ rõ nhất cho việc không nên gán nhãn toàn bộ object chỉ theo vị trí backing content.

### 5.2. JVM “non-heap” khác với “tất cả off-heap”

`ManagementFactory.getMemoryMXBean().getNonHeapMemoryUsage()` thống kê những **non-heap memory pools** do Java management API expose, chẳng hạn vùng liên quan tới class metadata và code cache.

**Nó không phải** một phép cộng toàn bộ:

```text
direct buffers + JNI malloc + thread stacks + mmap + allocator overhead
```

Có những vùng native nằm ngoài các MXBean non-heap pools. Vì thế:

> “nonHeapMXBean.used chỉ 60 MiB, nên toàn bộ native/off-heap của tiến trình chỉ 60 MiB”

là kết luận **sai**.

Để xác định nguồn tăng resident memory, cần kết hợp **nhiều lớp quan sát** thay vì dùng duy nhất `MemoryMXBean`.

## 6. `ByteBuffer.allocate` so với `ByteBuffer.allocateDirect`

### 6.1. Non-direct buffer thường dựa trên heap array

```java
byte[] bytes = new byte[1024];
ByteBuffer heapBuffer = ByteBuffer.wrap(bytes);
```

Cả `byte[]` và `ByteBuffer` wrapper là các đối tượng Java. `ByteBuffer.wrap` tạo non-direct buffer backed bởi mảng Java đã cung cấp.

```java
System.out.println(heapBuffer.isDirect()); // false
System.out.println(heapBuffer.hasArray());  // true
```

Trong ví dụ này, `hasArray()` đúng vì buffer đang backed bởi array truy cập được. **Không xem `hasArray()` là định nghĩa tuyệt đối của “on heap” trong mọi biến thể ByteBuffer**, vì read-only buffer hoặc subclass có thể hạn chế truy cập backing array.

### 6.2. Direct buffer dùng backing native memory

```java
ByteBuffer direct = ByteBuffer.allocateDirect(1024);
System.out.println(direct.isDirect()); // true
System.out.println(direct.hasArray()); // false trên HotSpot thông thường
```

Javadoc của `ByteBuffer` giải thích direct buffers có thể giúp native I/O tránh copy trung gian, nhưng allocation/deallocation có thể tốn chi phí hơn và bộ nhớ content **có thể nằm ngoài normal GC heap**, khiến footprint không hiển thị trực quan trong heap metrics.

**Điểm phân biệt:**

- `direct` **là một Java object reference**; object wrapper được GC quản lý.
- **Dữ liệu byte** phía sau wrapper trên HotSpot thường nằm ở native memory ngoài Java heap.
- JVM/cleaner có thể giải phóng backing memory khi không còn sử dụng, **nhưng thời điểm thu hồi phụ thuộc lifecycle/GC**; không nên giả định lập tức giải phóng khi biến local ra scope.
- `-Xmx` không phải một bộ giới hạn tổng native memory; `-XX:MaxDirectMemorySize` có ý nghĩa riêng cho NIO direct-buffer allocations.

### 6.3. `-XX:MaxDirectMemorySize` giới hạn cái gì?

```bash
java -Xmx256m -XX:MaxDirectMemorySize=64m MyApp
```

Cờ `MaxDirectMemorySize` giới hạn **các cấp phát NIO direct buffer thuộc phạm vi HotSpot theo option này**, không phải tổng chi phí native của toàn JVM.

Không kết luận rằng với `-Xmx256m` và `MaxDirectMemorySize=64m` thì process không thể vượt 320 MiB. Metaspace, code cache, stacks, native libraries và nhiều mapping khác vẫn tiêu thụ bộ nhớ.

### 6.4. Direct buffer không tự là persistent memory

`ByteBuffer.allocateDirect` cấp phát vùng memory native thông thường, **không** có nghĩa:

- luôn dùng NV-DIMM;
- bytes sống qua restart;
- thực hiện transaction hoặc fsync;
- cấp phát từ device do `-XX:AllocateHeapAt` chỉ định.

Cũng vậy, bật `AllocateHeapAt` không tự chuyển các direct-buffer allocations sang device của Java heap. Hai lựa chọn thuộc **hai phạm vi cấp phát khác nhau**.

### 6.5. Quyền sở hữu và lifecycle

Một lỗi dễ gặp khi dùng direct buffer là giữ tham chiếu tới buffer hoặc view lâu hơn dự tính. Khi đó:

- backing native memory vẫn bị giữ;
- heap usage có thể khá thấp;
- tiến trình vẫn tăng RSS hoặc chạm giới hạn native;
- pool direct capacity tăng dù heap GC không thấy “đầy”.

Với direct buffers, hãy giới hạn tổng số buffers, tái sử dụng khi có lợi và thiết kế lifecycle rõ. **Không dùng `System.gc()` như cơ chế trả direct memory có bảo đảm**, và không dựa vào `sun.misc.Unsafe` hoặc các cleaner nội bộ không có hợp đồng ổn định cho code ứng dụng mới.

## 7. File-backed mapping: `MappedByteBuffer` khác Java object heap

`FileChannel.map` tạo một `MappedByteBuffer` đại diện cho một vùng file được ánh xạ vào memory:

```java
// Minh họa trong phương thức đã mở FileChannel đúng mode.
MappedByteBuffer mapped = channel.map(
        FileChannel.MapMode.READ_WRITE, 0, 4096);
mapped.put(0, (byte) 7);
mapped.force();
```

Đây **không phải chương trình độc lập**: cần khai báo/khởi tạo `channel` và import đúng. `MappedByteBuffer` là một loại **direct buffer** nhưng backing nằm ở **file mapping** thay vì đơn thuần là direct allocation như `allocateDirect`.

### 7.1. Vòng đời và thay đổi nội dung

Javadoc hiện hành nói vùng mapping gắn với lifetime của mapped buffer, và file có thể bị thay đổi/truncate trong khi mapping còn tồn tại. Truy cập vùng file bị truncate có thể gây lỗi không xác định về thời điểm/loại; việc một thread khác sửa file có thể ảnh hưởng nội dung đang đọc.

Không đồng nhất `mapped.force()` với “biến mọi đối tượng Java trên heap thành dữ liệu persistent”. `force()` áp dụng cho **file mapping ấy** theo các bảo đảm riêng của API và OS.

### 7.2. `MappedByteBuffer` không phải `-XX:AllocateHeapAt`

Hai cơ chế đều liên quan đến **memory mapping**, nhưng scope khác:

| Khía cạnh | `MappedByteBuffer` | `-XX:AllocateHeapAt` |
| --- | --- | --- |
| Ai chọn file/region? | Code Java qua `FileChannel.map` | JVM theo flag lúc startup |
| Nội dung ánh xạ | Bytes của file được mapping | **Toàn bộ vùng Java object heap** của VM |
| GC quản lý content bytes như Java objects? | **Không** | **Có**: vẫn là object heap |
| Có API `force` cho vùng tương ứng? | `MappedByteBuffer.force` | Không có API biến object heap thành file database |
| Có thay đổi ý nghĩa `new Object()`? | Không | Không; chỉ đổi backing location của heap |
| Cần thiết bị bộ nhớ đặc biệt? | Không nhất thiết | Cần nền tảng/thiết bị phù hợp với yêu cầu của flag |

Điểm dễ nhớ: **“đều dùng mmap” không có nghĩa hai vùng nhớ có cùng ngữ nghĩa sở hữu, persistence hoặc GC**.

## 8. Metaspace, code heap và thread stacks

### 8.1. Metaspace

Metaspace lưu **class metadata** cần cho class loading và runtime. Nó không phải nơi chứa các đối tượng Java thông thường, dù code Java có thể tham chiếu `Class<?>` objects biểu diễn class ở mức API.

- Metaspace nằm ngoài Java object heap.
- `-Xmx` không trực tiếp bao trùm toàn bộ metaspace.
- Có thể quản lý/đo bằng **non-heap MemoryPoolMXBeans**, Native Memory Tracking và tools tương ứng.
- `-XX:MaxMetaspaceSize` là cờ còn được tài liệu JVM mô tả nhưng chỉ nên điều chỉnh theo nhu cầu thực.

**Không dùng cách gọi “PermGen” như thiết kế memory hiện hành của HotSpot**: vùng PermGen đã bị thay thế từ Java 8, và không phù hợp với Special Note.

### 8.2. Code cache / code heap

JIT compiler có thể tạo **native machine code** và lưu trong các code heaps/code cache. Đây không phải heap chứa objects như `new byte[]`, dù tên có từ “heap”.

**Không nhầm chữ “code heap” với Java object heap** và không mong `AllocateHeapAt` tự chuyển JIT code sang thiết bị alternative memory.

### 8.3. Thread stacks

Mỗi platform thread thường sử dụng stack/native thread resources do OS/JVM quản lý. Java local references có thể nằm trong stack frames, nhưng các **objects được tham chiếu** vẫn có semantics cấp phát trên Java heap nếu không được tối ưu theo cách khác.

`-Xss` liên quan cấu hình stack cho thread; **không giới hạn toàn bộ native memory** và không có nghĩa mọi thread đều luôn commit đủ `Xss` bytes theo một phép cộng đơn giản.

Với workload có rất nhiều platform threads, native stacks có thể đóng góp đáng kể vào memory footprint; `AllocateHeapAt` không tự đưa chúng sang device của object heap.

## 9. Java heap, JVM non-heap, off-heap và tổng bộ nhớ process

### 9.1. Không lấy `-Xmx` làm giới hạn tổng RSS

Một JVM có thể dùng:

```text
Java object heap committed
+ native code cache, class metadata, thread stacks
+ NIO direct buffers / mapped files
+ JNI/native library memory
+ garbage collector and compiler bookkeeping
+ C/C++ allocator overhead
+ other OS mappings and shared libraries
```

Danh sách trên mang tính **phân loại nguyên nhân**, không phải phương trình cộng chính xác do những số liệu khác nhau có thể chồng lắp, dùng đơn vị virtual/reserved/committed/resident khác nhau.

**RSS** là lượng pages resident được OS tính cho tiến trình; **virtual memory size** gồm cả mappings chưa resident. **Heap used** là dung lượng đối tượng mà JVM báo đang dùng, khác với **heap committed**, và càng không bằng tổng memory footprint process.

### 9.2. Container memory limits

Trong Linux container, `memory.max` (cgroups v2) hoặc controller tương ứng ở v1 có thể giới hạn memory chung của cgroup. Tiến trình có thể bị **OOM-killed** bởi kernel/container runtime ngay cả khi Java heap vẫn còn trống nếu tổng footprint tiến gần hard limit.

Ví dụ giả định:

```text
Container memory limit:      512 MiB
Java -Xmx:                  384 MiB
Native + stacks + metadata:  150 MiB
Tổng nhu cầu:                >512 MiB
```

Các con số chỉ minh họa rằng `-Xmx` không dành sẵn headroom cho các vùng native. Quyết định thực tế cần dựa trên heap committed, direct/mapped buffers, native categories, OS page accounting, file cache và behavior cụ thể.

**Không khuyên** đặt `-Xmx` đúng 100% container memory limit mà bỏ qua các vùng khác.

### 9.3. Đặt Java object heap trên device khác có làm mất chi phí native không?

Không. Với JEP 316, dù object heap được đặt trên alternative memory, các vùng **metaspace, code heap, stacks và native allocations** vẫn là một phần footprint của tiến trình. Có thể chúng được cấp trong DRAM theo JDK/OS được mô tả, nhưng chưa chắc các phép đo OS “dùng ít RAM” sẽ đơn giản giảm đúng bằng dung lượng heap do page mapping và chính sách hạ tầng.

Phải kiểm tra **cả memory device usage lẫn DRAM/RSS/cgroup metrics**, không chỉ nhìn `MemoryMXBean`.

## 10. Dùng `MemoryMXBean` cho số liệu Java heap và non-heap

API quản lý trong `java.management`:

```java
MemoryMXBean mx = ManagementFactory.getMemoryMXBean();

MemoryUsage heap = mx.getHeapMemoryUsage();
MemoryUsage nonHeap = mx.getNonHeapMemoryUsage();
```

Đây là code minh họa **trong một phương thức**, cần imports tương ứng.

Một `MemoryUsage` có bốn giá trị:

- `init`: kích thước khởi tạo được yêu cầu; có thể `-1` khi không xác định.
- `used`: dung lượng đang được các pools báo sử dụng.
- `committed`: dung lượng đã được JVM commit/sẵn sàng để dùng theo nghĩa API.
- `max`: giới hạn khả dụng nếu biết; có thể `-1`.

### 10.1. `getHeapMemoryUsage()`

Phản ánh Java heap pools của JVM để cấp phát objects. Khi chuyển object heap lên device khác qua JEP 316, **semantics vẫn là Java heap**, do đó tiếp tục dùng nhóm số liệu **heap** để theo dõi GC-managed objects.

Nó **không** nói chính xác thiết bị vật lý nào đang backing mỗi page; phải thêm metrics của OS/device.

### 10.2. `getNonHeapMemoryUsage()`

Phản ánh các **non-heap memory pools của VM**. **Không đồng nghĩa tổng native allocations**; direct buffers, JNI allocations và thread stacks có thể không được tổng hợp đầy đủ trong số này.

Đây là khác biệt quan trọng khi xử lý sự cố:

> Heap used ổn định, non-heap used ổn định, nhưng RSS tăng.

Không thể loại trừ memory leak: cần điều tra direct buffers, native libraries, mappings và OS accounting.

### 10.3. Số liệu có tính thời điểm

Memory usage thay đổi do GC, class loading, compilation, caching và những thread khác. Đừng viết test kỳ vọng `heap.used == 1048576` sau `new byte[1048576]`:

- có object headers/alignment;
- có allocations nền;
- GC có thể chạy;
- JVM có thể tối ưu các allocations;
- committed size khác used size.

Hãy dùng **dữ liệu định tính và xu hướng đo**, hoặc assertion đủ rộng cho mục tiêu cụ thể.

## 11. `BufferPoolMXBean` cho NIO direct/mapped buffers

Để quan sát pool của NIO buffers, Java có API chuẩn:

```java
List<BufferPoolMXBean> pools =
    ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class);
```

Các thông số:

- `getName()`: thường gặp `direct` và `mapped` trên HotSpot;
- `getCount()`: ước lượng số buffers trong pool;
- `getTotalCapacity()`: ước lượng tổng capacity của buffers;
- `getMemoryUsed()`: ước lượng memory mà VM dùng, **có thể khác total capacity** do alignment/allocator overhead hoặc là `-1` nếu không ước lượng được.

**Cảnh báo:** `BufferPoolMXBean` không cho phép đo mọi allocation do JNI, native library hay Foreign Memory API tạo. Nó theo dõi các pools mà JVM expose qua giao diện này.

### 11.1. Không cộng buffer pool stats vào `MemoryMXBean.nonHeap` một cách mù quáng

Các phép đo đến từ những **giao diện đo khác phạm vi**. Nếu cộng tất cả số liệu như cùng một hệ quy chiếu, có thể thiếu hoặc trùng những thành phần native. `getMemoryUsed()` cũng là ước lượng, không phải RSS.

### 11.2. Phân biệt capacity với memory used

Một direct buffer có `capacity=2 MiB` không chứng minh physical allocation chính xác 2 MiB, vì alignment/memory allocator overhead và page residency. BufferPoolMXBean có hai số liệu riêng để tránh đánh đồng hai khái niệm.

Không dùng `bufferPool.getTotalCapacity()` làm phép đo chính xác lượng DRAM đang resident.

## 12. Java 17+ runnable: heap-backed buffer và direct off-heap data

Ví dụ dùng Java SE API ổn định, **không cần NV-DIMM/DAX**. Nó so sánh một `byte[]` backed heap buffer với direct buffer, đồng thời kiểm tra sự tồn tại của heap/non-heap MXBeans và direct buffer pool.

**Lưu file `HeapAndOffHeap373.java`:**

```java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.nio.ByteBuffer;

public final class HeapAndOffHeap373 {
    public static void main(String[] args) {
        byte[] payload = new byte[1024 * 1024];
        ByteBuffer heapView = ByteBuffer.wrap(payload);
        ByteBuffer directView = ByteBuffer.allocateDirect(2 * 1024 * 1024);

        heapView.putInt(0, 17);
        directView.putInt(0, 42);

        System.out.println("heapViewDirect=" + heapView.isDirect());
        System.out.println("heapViewHasArray=" + heapView.hasArray());
        System.out.println("directViewDirect=" + directView.isDirect());
        System.out.println("directViewHasArray=" + directView.hasArray());
        System.out.println("heapValue=" + heapView.getInt(0));
        System.out.println("directValue=" + directView.getInt(0));
        System.out.println("heapPayloadMiB=" + (payload.length / (1024 * 1024)));
        System.out.println("directCapacityMiB=" + (directView.capacity() / (1024 * 1024)));

        MemoryMXBean bean = ManagementFactory.getMemoryMXBean();
        boolean heapUsageValid = bean.getHeapMemoryUsage().getUsed() >= 0
                && bean.getHeapMemoryUsage().getCommitted() >= 0;
        boolean nonHeapUsageValid = bean.getNonHeapMemoryUsage().getUsed() >= 0
                && bean.getNonHeapMemoryUsage().getCommitted() >= 0;
        System.out.println("heapMXBeanValid=" + heapUsageValid);
        System.out.println("nonHeapMXBeanValid=" + nonHeapUsageValid);

        boolean directPoolDetected = ManagementFactory
                .getPlatformMXBeans(BufferPoolMXBean.class).stream()
                .filter(pool -> pool.getName().equals("direct"))
                .anyMatch(pool -> pool.getTotalCapacity() >= directView.capacity());
        System.out.println("directPoolDetected=" + directPoolDetected);

        System.out.println("java17OrNewer=" + (Runtime.version().feature() >= 17));
    }
}
```

### 12.1. Biên dịch

```bash
javac --release 17 -encoding UTF-8 HeapAndOffHeap373.java
```

### 12.2. Chạy với giới hạn minh họa

```bash
java -Xms32m -Xmx128m -XX:MaxDirectMemorySize=16m HeapAndOffHeap373
```

**Stdout chính xác đã kiểm thử trên OpenJDK 24.0.2:**

```text
heapViewDirect=false
heapViewHasArray=true
directViewDirect=true
directViewHasArray=false
heapValue=17
directValue=42
heapPayloadMiB=1
directCapacityMiB=2
heapMXBeanValid=true
nonHeapMXBeanValid=true
directPoolDetected=true
java17OrNewer=true
```

### 12.3. Diễn giải

- `heapViewDirect=false`: buffer backed bởi `payload` là **non-direct**, nội dung do Java array lưu giữ.
- `heapViewHasArray=true`: trong ví dụ này có một backing array truy cập được.
- `directViewDirect=true`: `allocateDirect` cấp direct buffer; trên HotSpot, backing content thường là native memory.
- `directViewHasArray=false`: buffer direct không expose Java backing array qua `array()`.
- `heapValue` và `directValue` cho thấy hai loại buffer đều cho phép đọc/ghi dữ liệu kiểu số.
- `heapPayloadMiB=1` và `directCapacityMiB=2` là **kích thước dữ liệu yêu cầu**, không phải heap used hay RSS đo được.
- `heapMXBeanValid`, `nonHeapMXBeanValid` chỉ kiểm tra management API trả những giá trị không âm, **không chứng minh 1 MiB và 2 MiB nằm ở đúng thiết bị vật lý nào**.
- `directPoolDetected=true`: HotSpot JDK 24.0.2 expose pool tên `direct` với capacity ít nhất 2 MiB. Tên/tập pool có thể phụ thuộc implementation; không ép toàn bộ Java VM phải in true.
- `java17OrNewer=true` khi chạy đúng môi trường Java 17+.

**Quan trọng:** không lấy output của demo để tuyên bố `AllocateHeapAt` đã được thử. Nó **chưa được bật** và không có alternative device thật; demo chỉ kiểm chứng sự khác nhau giữa **heap-backed vs direct buffer** và management categories.

### 12.4. Vì sao không in số heap used “chính xác”?

Bởi vì `heap.used` và `nonHeap.used` biến đổi theo startup/JIT/class loading/GC, và kích thước object không chỉ gồm byte payload. Dùng output cố định trong bài có thể dạy người học hiểu sai. Với monitoring, xem **số liệu thực tại thời điểm chạy**, không coi `new byte[1 MiB]` đồng nghĩa heap usage tăng đúng 1 MiB.

### 12.5. Thực hành thay `MaxDirectMemorySize`

Có thể nghiên cứu ảnh hưởng khi tạo nhiều direct buffers dưới một direct-memory limit nhỏ trong **lab có kiểm soát**. Không hướng dẫn tạo OOM/kill container production để “thấy lỗi cho rõ”; trước hết dùng BufferPoolMXBean và thử nghiệm có bộ nhớ giới hạn an toàn.

Nếu direct allocation vượt giới hạn phù hợp, HotSpot có thể ném `OutOfMemoryError` với thông báo liên quan `Direct buffer memory`. Đó là **loại áp lực khác** với `Java heap space`; phải phân loại trước khi chỉnh flags.

## 13. Native Memory Tracking và `jcmd`

HotSpot hỗ trợ **Native Memory Tracking (NMT)** để thấy các nhóm sử dụng native memory của VM.

Bật ở **JVM startup**:

```bash
java -XX:NativeMemoryTracking=summary -Xmx512m com.example.Main
```

`com.example.Main` là class minh họa, cần thay bằng main class thật. Sau khi JVM chạy, dùng một process được cấp quyền tương ứng:

```bash
jcmd <pid> VM.native_memory summary
```

`<pid>` là PID minh họa. Để thấy thay đổi giữa hai thời điểm:

```bash
jcmd <pid> VM.native_memory baseline
# Chạy workload đại diện và đo sau một khoảng thời gian.
jcmd <pid> VM.native_memory summary.diff
```

NMT chia các categories như Java Heap, Class, Thread, Code, GC, Compiler, Internal... tùy JDK.

### 13.1. Reserved, committed và resident khác nhau

- **Reserved virtual memory:** vùng địa chỉ ảo được dành trước; **không nhất thiết đã có physical pages**.
- **Committed memory:** vùng VM đã commit để sử dụng theo cơ chế quản lý của nó; không nên mặc định bằng RSS.
- **Resident memory (RSS):** trang bộ nhớ thực đang resident mà OS tính cho tiến trình.
- **Heap used:** lượng bộ nhớ đối tượng mà JVM báo đang dùng, bao gồm cả objects chưa được GC thu hồi.

Một output NMT nói `reserved=4 GiB` không chứng minh OS đã sử dụng 4 GiB DRAM. Cần phân biệt các đơn vị và cách đo.

### 13.2. Giới hạn của NMT

NMT **không phải bộ theo dõi mọi byte từ mọi native library**. Nó theo dõi những đường cấp phát mà HotSpot/NMT instrument, với mức `summary` hoặc `detail`; vùng do thư viện bên ngoài quản lý có thể không xuất hiện đầy đủ.

Ngoài ra, NMT có overhead về CPU/memory/tracking. Không bật `detail` mặc định trên mọi production JVM chỉ vì muốn nhiều số liệu hơn. Bật có mục tiêu khi điều tra, và phối hợp với OS/native profilers khi cần.

### 13.3. Chọn công cụ đo theo câu hỏi

| Câu hỏi | Công cụ thường phù hợp |
| --- | --- |
| Java heap dùng bao nhiêu? | `MemoryMXBean.getHeapMemoryUsage()`, GC logs, `jcmd GC.heap_info` |
| Non-heap VM pools ra sao? | `MemoryMXBean.getNonHeapMemoryUsage()`, `MemoryPoolMXBean` |
| Direct/mapped NIO buffers có tăng không? | `BufferPoolMXBean` |
| Native memory của các subsystem HotSpot tăng ở đâu? | NMT `VM.native_memory summary/diff` |
| Process thực sự resident bao nhiêu? | OS process RSS/PSS, `/proc/<pid>/smaps` trên Linux |
| Container đạt memory limit không? | cgroup `memory.current`/`memory.max`, runtime metrics |
| Thiết bị alternative memory có thực được dùng không? | JVM startup/logs, OS mappings, device/DAX metrics |
| Có object leak trong Java heap không? | Heap dump/JFR/profiler, GC roots |
| Có native/JNI leak không? | NMT phù hợp, native profiler và allocator tools |

**Không có một công cụ duy nhất thay thế được tất cả.**

## 14. Lỗi bộ nhớ: phân biệt trước khi “tăng `-Xmx`”

### 14.1. `OutOfMemoryError: Java heap space`

Đây thường gợi ý object heap không đủ cho object graph hiện tại/nhu cầu cấp phát. Hãy xem heap size, GC, memory retention, allocations và có thật là leak hay chỉ workload tăng đột biến.

Giới hạn `MaxDirectMemorySize` **không** trực tiếp mở rộng Java heap. Nếu đã dùng `AllocateHeapAt`, heap trên device vẫn có `-Xmx` và GC, nên cách chẩn đoán heap pressure vẫn tương tự về ngữ nghĩa.

### 14.2. `OutOfMemoryError: Direct buffer memory`

Đây là dấu hiệu về NIO direct-buffer allocation không đủ tài nguyên hoặc vượt direct memory limit. Hướng điều tra:

- số direct buffers và tổng capacity;
- có giữ ByteBuffer references quá lâu không;
- có quá nhiều per-request direct allocations không;
- pool reuse/lifecycle đã phù hợp chưa;
- `MaxDirectMemorySize` có phản ánh workload không;
- OS/container memory có đủ headroom không.

**Không** chỉ tăng `-Xmx` vì Java heap usage đang thấp; cần xem direct/native memory.

### 14.3. `OutOfMemoryError: Metaspace`

Có thể do quá nhiều class metadata/classloaders, hot deployment/classloader retention hoặc giới hạn metaspace. Xem class loader metrics, metaspace usage, class loading/unloading behavior và ứng dụng có tạo quá nhiều class loader không.

**Không** nhầm với Java heap exhausted, và không nói lỗi Metaspace được chữa bằng tăng `MaxDirectMemorySize`.

### 14.4. Không tạo được native thread

Một `OutOfMemoryError` liên quan tạo native thread có thể xuất phát từ OS thread/process limits, native stack memory, address space hoặc container constraints. Nó **không bắt buộc** do Java object heap đầy.

Dùng thread dump/OS process limits và native memory metrics. Đừng tự tăng heap nếu nguyên nhân là quá nhiều platform threads.

### 14.5. Kernel/container OOM kill

Container có thể bị kernel kill khi memory limit vượt ngưỡng, **không nhất thiết JVM kịp ném Java OOME hay tạo heap dump**. Điều tra cgroup OOM counters, container exit reason, kernel logs và process memory trends.

Không suy rằng “không có Java OOME” nghĩa bộ nhớ không có vấn đề.

## 15. Vòng đời bộ nhớ và an toàn truy cập

### 15.1. Java heap: GC và reachability

Java objects được GC quản lý. Khi không còn reachable, đối tượng **có thể** được reclaim vào một thời điểm do collector quyết định. Không gọi `free` trên Java object.

Một reference local ra khỏi block **không** là cam kết vùng heap được thu hồi ngay. GC có thể giữ heap committed để tái sử dụng và không trả RSS lập tức về OS.

### 15.2. Direct buffer: wrapper vs backing memory

Direct buffer có wrapper Java và backing native content. Vòng đời reclaim thường gắn với reachability/Cleaner của buffer và triển khai JVM, không phải một lệnh `close()` public tổng quát trên mọi `ByteBuffer`.

Đừng:

- dựa vào `finalize()` hay `System.runFinalization()` (deprecated/removed trong JDK mới);
- gọi `sun.misc.Unsafe` hoặc cleaner nội bộ để ép unmap/free mà không có hợp đồng ổn định;
- giả định object wrapper bị GC là native content lập tức biến mất trong cùng mili-giây;
- giữ reference/view/slice quá lâu mà quên backing allocation vẫn bị giữ.

**Với code mới**, ưu tiên API quản lý lifecycle rõ ràng khi cần deterministic allocation/free.

### 15.3. Java 22+: Foreign Function & Memory API có lifetime rõ ràng

**JEP 454** chuẩn hóa **Foreign Function & Memory (FFM) API** trong **JDK 22**. Trong các trường hợp phù hợp, `Arena` và `MemorySegment` giúp cấp phát native memory với phạm vi vòng đời explicit:

```java
// Đoạn minh họa JDK 22+, KHÔNG thuộc chương trình Java 17+ phía trên.
import java.lang.foreign.Arena;
import java.lang.foreign.MemorySegment;

try (Arena arena = Arena.ofConfined()) {
    MemorySegment nativeBlock = arena.allocate(1024);
    // Truy cập qua các API MemorySegment phù hợp.
} // arena.close(): kết thúc lifetime của các segments trong arena.
```

Đây là một lựa chọn hiện hành cho việc quản lý vùng native memory có phạm vi rõ ràng. Nhưng **không phải mọi ứng dụng cần chuyển từ direct ByteBuffer sang FFM**; lựa chọn phụ thuộc I/O, JNI/native integration, hiệu năng và yêu cầu lifecycle.

**Không nhầm** native `MemorySegment` với toàn bộ Java object heap, và **không** dùng các package `jdk.incubator.foreign` cũ cho code Java mới: API chuẩn đã có ở `java.lang.foreign` từ Java 22.

### 15.4. Alternative heap device và dữ liệu nhạy cảm

Dữ liệu trong Java object heap có thể chứa tokens, keys, PII hoặc dữ liệu nghiệp vụ. Nếu backing memory là thiết bị có đặc tính giữ dữ liệu khác DRAM, đội vận hành cần đánh giá:

- kiểm soát truy cập filesystem/device;
- xóa/cleanup mapping và file remnants theo chính sách;
- thu hồi bộ nhớ sau crash/restart;
- tính toàn vẹn và khả năng rò rỉ dữ liệu trên thiết bị;
- encryption, isolation và data retention requirements.

**Không** mặc định việc GC reclaim hay JVM exit đồng nghĩa “xóa an toàn mọi bytes ở tầng thiết bị”. Đây là chính sách bảo mật dữ liệu/OS/hardware độc lập với Java GC semantics.

## 16. Checklist QA cho hệ thống dùng nhiều loại bộ nhớ

**Nhóm A — Object heap**

- Xác định `-Xms`, `-Xmx` và GC collector.
- Đo heap `used/committed/max` và old-gen/live set.
- Phân tích heap dumps khi nghi retention/leak.
- Nếu dùng `AllocateHeapAt`, kiểm tra đúng memory device và throughput/latency của GC.

**Nhóm B — JVM non-heap**

- Xem metaspace/class metadata và classloader behavior.
- Xem code cache, JIT và thread stacks.
- Kiểm tra `-XX:MaxMetaspaceSize` chỉ nếu thật cần.
- Nhớ rằng `MemoryMXBean.nonHeap` **không phải tổng native memory**.

**Nhóm C — Off-heap/native**

- Thu `BufferPoolMXBean` cho direct/mapped buffers.
- Xem `MaxDirectMemorySize` và số buffer giữ lâu.
- Bật NMT có mục tiêu để xem native categories.
- Điều tra JNI/native libs bằng tool phù hợp nếu NMT không bao trùm.
- Xem OS RSS/PSS và cgroup memory utilization.

**Nhóm D — Alternative memory device**

- Xác nhận hardware/mount/DAX semantics và đúng JDK build.
- Đặt heap chỉ trên thiết bị được hỗ trợ, không giả bằng thư mục bất kỳ.
- Kiểm tra mapping, permission, capacity và crash behavior.
- Benchmark trên workload đại diện, gồm allocation, GC pause và latency tail.
- Định nghĩa cleanup/data-retention/security policy, không giả định object persistence.

**Nhóm E — Release/monitoring**

- Lưu JDK version, VM flags, container image digest và OS/kernel version.
- Phân biệt virtual/reserved/committed/resident metrics.
- Thu baseline trước khi đổi cấu hình và so sau deploy.
- Không so “heap used” của một phiên JVM với “RSS” của phiên khác rồi kết luận off-heap leak.

## 17. Những ngộ nhận phổ biến

**Ngộ nhận 1 — “Heap nằm trên NV-DIMM nghĩa objects đã off-heap.”**  
Sai. `AllocateHeapAt` đổi backing location nhưng dữ liệu vẫn là **Java object heap** do GC quản lý.

**Ngộ nhận 2 — “Mọi thứ của JVM đều chuyển sang device khi dùng `AllocateHeapAt`.”**  
Sai. Metaspace, code heap, thread stacks và các native structures khác không tự chuyển theo.

**Ngộ nhận 3 — “NV-DIMM non-volatile nên Java objects tự phục hồi sau crash.”**  
Sai. JEP 316 không biến object graph thành persistent transactional store.

**Ngộ nhận 4 — “`-Xmx` giới hạn toàn bộ bộ nhớ của process.”**  
Sai. Nó giới hạn Java object heap; native allocations, stacks, metaspace và mappings còn tồn tại.

**Ngộ nhận 5 — “`MemoryMXBean.nonHeap` đo tổng mọi off-heap.”**  
Sai. Đây là thống kê **non-heap memory pools** của JVM, không bao trùm mọi native allocation.

**Ngộ nhận 6 — “Direct ByteBuffer hoàn toàn nằm off-heap.”**  
Không chính xác: wrapper là Java object, backing content thường ở native memory.

**Ngộ nhận 7 — “`MaxDirectMemorySize` giới hạn toàn bộ native memory.”**  
Sai. Nó áp dụng cho phạm vi direct-buffer allocations của JVM, không bao trùm JNI/mapped files/stacks.

**Ngộ nhận 8 — “`getHeapMemoryUsage().used` phải tăng đúng bằng số bytes mảng mới cấp.”**  
Sai. Object headers, GC, nền runtime và các tối ưu làm số đo không đơn giản như vậy.

**Ngộ nhận 9 — “`ByteBuffer.hasArray()==false` nghĩa chắc chắn mọi dữ liệu ở off-heap.”**  
Sai. Read-only/access restrictions cũng có thể khiến không truy cập được backing array; dùng `isDirect` để xác định thuộc tính direct theo API.

**Ngộ nhận 10 — “Memory mapping file bằng `MappedByteBuffer` giống cấp phát toàn Java heap trên device.”**  
Sai. Một cơ chế mapping bytes của một file, cơ chế kia thay backing của JVM object heap.

**Ngộ nhận 11 — “Chỉ cần chọn `AllocateHeapAt=/tmp` là đã benchmark NVM.”**  
Sai. Thư mục thường không chứng minh đúng hardware/file system có DAX semantics.

**Ngộ nhận 12 — “Java object hết reachability thì RSS lập tức giảm.”**  
Sai. GC có thể giữ heap committed và OS có cơ chế memory mappings/page residency riêng.

**Ngộ nhận 13 — “NMT theo dõi toàn bộ native allocations của mọi thư viện.”**  
Không. NMT chủ yếu theo dõi những allocations do HotSpot instrument; cần tool bổ sung cho JNI/native libs.

**Ngộ nhận 14 — “Có thể dùng finalize() để giải phóng direct memory kịp thời.”**  
Sai và lỗi thời. Finalization không còn là chiến lược lifecycle đúng cho ứng dụng mới.

**Ngộ nhận 15 — “PermGen vẫn là non-heap vùng chính trong HotSpot JDK 27.”**  
Sai. Dùng khái niệm metaspace hiện hành.

**Ngộ nhận 16 — “Heap đã ở thiết bị khác nên GC không cần chạy nữa.”**  
Sai. GC quản lý object reachability theo Java heap semantics, bất kể backing device.

**Ngộ nhận 17 — “Không có Java OutOfMemoryError thì container chưa thể hết bộ nhớ.”**  
Sai. Kernel/cgroup OOM kill có thể xảy ra trước khi JVM in lỗi.

**Ngộ nhận 18 — “Off-heap luôn nhanh hơn on-heap.”**  
Sai. Native allocations có overhead, access patterns, page faults và CPU/GC trade-offs; benchmark trên workload thật.

## 18. Câu hỏi tự kiểm tra

**Câu 1.** `-XX:AllocateHeapAt` làm gì?  
**Đáp án:** Cho HotSpot dùng memory mapping để đặt **Java object heap** lên alternative memory device được chỉ định khi nền tảng hỗ trợ.

**Câu 2.** Java objects trên heap của JEP 316 có còn được GC quản lý không?  
**Đáp án:** Có. Thay backing memory không đổi cơ chế quản lý đối tượng.

**Câu 3.** Khi heap được đặt trên NV-DIMM, code heap/metaspace/stacks có tự chuyển sang device không?  
**Đáp án:** Không. Tài liệu launcher nêu các cấu trúc này vẫn ở DRAM trong mô hình hỗ trợ.

**Câu 4.** Có thể dùng JEP 316 như object database tự khôi phục sau restart không?  
**Đáp án:** Không. Không có hợp đồng persistence/transaction/recovery cho Java object graph.

**Câu 5.** `ByteBuffer.wrap(new byte[1024]).isDirect()` trả gì?  
**Đáp án:** `false`, vì đó là non-direct buffer backed bởi heap array.

**Câu 6.** `ByteBuffer.allocateDirect(1024).isDirect()` trả gì?  
**Đáp án:** `true`. Trên HotSpot, backing bytes thường ở native memory ngoài normal Java heap.

**Câu 7.** Vì sao direct buffer vẫn có Java heap usage?  
**Đáp án:** Vì wrapper/metadata Java object vẫn do GC quản lý, dù backing content nằm ngoài object heap.

**Câu 8.** `MemoryMXBean.getNonHeapMemoryUsage()` có tính mọi JNI allocation không?  
**Đáp án:** Không. Nó thống kê non-heap pools do Java management API expose.

**Câu 9.** Dùng API chuẩn nào để xem lượng direct/mapped buffer?  
**Đáp án:** `BufferPoolMXBean` qua `ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)`.

**Câu 10.** `BufferPoolMXBean.getMemoryUsed()` có luôn bằng `getTotalCapacity()` không?  
**Đáp án:** Không. Alignment/allocator overhead và implementation có thể làm khác nhau; giá trị memoryUsed cũng có thể là `-1`.

**Câu 11.** `-Xmx512m` có chặn process RSS ở 512 MiB không?  
**Đáp án:** Không. Native stacks, metaspace, direct buffers, code cache và các vùng khác vẫn tốn bộ nhớ.

**Câu 12.** `-XX:MaxDirectMemorySize=64m` có chặn JNI malloc ở 64 MiB không?  
**Đáp án:** Không. Đó không phải native memory cap chung.

**Câu 13.** Dùng `System.gc()` có bảo đảm direct memory được giải phóng lập tức không?  
**Đáp án:** Không. Không nên dùng explicit GC làm chiến lược lifecycle.

**Câu 14.** Công cụ nào giúp xem native memory của HotSpot theo categories?  
**Đáp án:** Bật `-XX:NativeMemoryTracking=summary` rồi dùng `jcmd <pid> VM.native_memory summary`.

**Câu 15.** Vì sao RSS tăng khi heap used ổn định?  
**Đáp án:** Có thể vì direct/native buffers, stacks, class metadata, mappings, JNI hoặc OS accounting; cần thêm dữ liệu, không kết luận vội.

**Câu 16.** Khi nâng JDK/OS/memory device, có nên giả định `AllocateHeapAt` cho kết quả như cũ không?  
**Đáp án:** Không. Phải xác minh khả năng hỗ trợ, mapping và benchmark lại.

**Câu 17.** API quản lý native memory có lifecycle explicit được chuẩn hóa từ JDK 22 là gì?  
**Đáp án:** Foreign Function & Memory API với `Arena` và `MemorySegment`.

**Câu 18.** Tại sao demo Java 17+ của bài không chứng minh NV-DIMM support?  
**Đáp án:** Nó chỉ tạo heap-backed và direct buffers; không bật `AllocateHeapAt` và không có device DAX thật.

## 19. Ghi nhớ

1. **“Java object heap” là khái niệm về ngữ nghĩa đối tượng/GC**, không đồng nghĩa “chỉ được nằm trong DRAM”.
2. **Java 10/JEP 316** cho phép HotSpot đặt object heap trên alternative memory device với `-XX:AllocateHeapAt` khi nền tảng hỗ trợ; **heap vẫn do GC quản lý**.
3. **Metaspace, code heap và thread stacks** không tự chuyển sang alternative device chỉ vì object heap chuyển vị trí.
4. **Native/off-heap memory** là nhóm khái niệm khác: direct buffers, mapped files, native libraries, stacks và các vùng JVM ngoài object heap.
5. **Direct ByteBuffer wrapper là Java object**, backing data có thể nằm trong native memory. `ByteBuffer.isDirect` cho biết thuộc tính direct.
6. `-Xmx` quản lý giới hạn **object heap**, `-XX:MaxDirectMemorySize` liên quan direct-buffer allocations; **không cờ nào là giới hạn tổng RSS**.
7. `MemoryMXBean.getNonHeapMemoryUsage()` đo VM non-heap pools, **không phải tổng off-heap/native memory**.
8. Dùng `BufferPoolMXBean`, NMT, `jcmd` và OS/cgroup metrics để chẩn đoán bộ nhớ **đa vùng**.
9. **Không nhầm DAX/mmap với persistence tự động của Java objects**; crash recovery và data-retention là bài toán riêng.
10. Với code mới, dùng API chuẩn còn được hỗ trợ; **không khuyến nghị PermGen, finalizers, Unsafe/cleaner nội bộ hoặc incubator FFM đã lỗi thời**.

## Tài liệu chính thức còn áp dụng

- **OpenJDK JEP 316 — Heap Allocation on Alternative Memory Devices**, delivered in JDK 10: https://openjdk.org/jeps/316
- **Oracle Java SE 27 — The java Command**, option `-XX:AllocateHeapAt`, `-Xmx`, `MaxDirectMemorySize`, `NativeMemoryTracking`: https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html
- **Java SE 26 API — `ByteBuffer`**, direct và non-direct buffers: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/ByteBuffer.html
- **Java SE 26 API — `MappedByteBuffer`**, mapping và `force`: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/nio/MappedByteBuffer.html
- **Java SE 26 API — `MemoryMXBean`**: https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MemoryMXBean.html
- **Java SE 26 API — `BufferPoolMXBean`**: https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/BufferPoolMXBean.html
- **Java SE 26 API — `MemoryUsage`**, `used/committed/max`: https://docs.oracle.com/en/java/javase/26/docs/api/java.management/java/lang/management/MemoryUsage.html
- **Oracle Java SE 27 — jcmd command**, `VM.native_memory` và GC diagnostics: https://docs.oracle.com/en/java/javase/27/docs/specs/man/jcmd.html
- **OpenJDK JEP 454 — Foreign Function & Memory API**, finalized in JDK 22: https://openjdk.org/jeps/454
- **Oracle Java SE 26 — Foreign Function & Memory API**, `Arena` và `MemorySegment`: https://docs.oracle.com/en/java/javase/26/core/foreign-function-and-memory-api.html
