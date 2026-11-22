# Phần bộ nhớ cho bộ đệm trực tiếp và thư viện native khi chạy Java trong container

## 1. Vấn đề: heap chưa đầy nhưng container vẫn hết bộ nhớ

Khi triển khai ứng dụng Java trong Docker/Kubernetes, đôi khi ta thấy:

~~~text
Giới hạn bộ nhớ container:     512 MiB
Java heap tối đa (-Xmx):      320 MiB
Heap đang dùng theo GC:       180 MiB
Ứng dụng bị container OOM kill
~~~

Phản ứng “heap mới 180 MiB nên JVM không thể thiếu RAM” là **sai**. Một tiến trình Java không chỉ sử dụng Java heap. Nó còn có thể cấp phát bộ nhớ cho:

- **Direct buffers** của `java.nio`: vùng nhớ ngoài heap dùng cho I/O và thao tác bộ đệm.
- **Thư viện native** được gọi bằng JNI/JNA hoặc qua các runtime thành phần khác.
- **Metaspace/class metadata**, code cache/JIT, hoạt động garbage collector.
- **Thread stacks** cùng cấu trúc quản lý thread.
- Vùng memory-mapped, bộ nhớ allocator, buffers của networking/TLS/compression.
- Những trang bộ nhớ file-backed, shared mappings và chi phí của tiến trình khác trong cùng cgroup, tùy cấu hình.

Nếu cộng những thành phần **thực sự được charge vào memory cgroup** vượt giới hạn, kernel có thể kích hoạt OOM và kết thúc tiến trình/container. `-Xmx` chỉ đặt giới hạn **Java heap**, không phải giới hạn toàn bộ memory footprint.

Bài này thuộc chủ đề **Bộ nhớ trong container** của Java 10. Java 10 đã đưa cải tiến nhận biết tài nguyên Docker/cgroup vào HotSpot. Tuy nhiên, các nguyên tắc về direct buffers, native memory, giới hạn container và quan sát bằng công cụ hiện đại vẫn được áp dụng trong những JDK còn được hỗ trợ.

**Mục tiêu:** hiểu vùng nhớ nào nằm ngoài heap, giới hạn nào thực sự kiểm soát nó, cách đo trên Java 17+ và cách lập ngân sách tránh OOM. Không dùng lời khuyên cũ coi mọi bộ nhớ native là “PermGen”, không dùng API nội bộ để ép free direct buffer.

## 2. Bản đồ bộ nhớ của một tiến trình JVM

Một sơ đồ khái niệm:

~~~text
Giới hạn memory container/cgroup
+-------------------------------------------------------------+
| Java process                                                |
| +--------------------+  +--------------------------------+ |
| | Java heap          |  | Ngoài Java heap                | |
| | objects, arrays    |  | direct ByteBuffer native data  | |
| | (chịu -Xmx)        |  | JNI/native library allocations | |
| |                    |  | thread stacks                   | |
| |                    |  | metaspace, class metadata      | |
| |                    |  | code cache, JIT, GC structures | |
| +--------------------+  +--------------------------------+ |
| Memory-mapped/file-backed pages, shared libraries, allocators|
+-------------------------------------------------------------+
| Các chi phí khác bị charge vào cgroup theo Linux/kernel      |
| (file cache, tiến trình phụ, shared memory ... nếu áp dụng) |
+-------------------------------------------------------------+

Heap tối đa < giới hạn container KHÔNG đảm bảo tổng memory < limit.
~~~

Sơ đồ cố ý đơn giản hóa: vùng địa chỉ ảo được **reserve**, trang nhớ được **commit**, trang đã thực sự đi vào **resident set** và số byte cgroup **charge** không phải một đại lượng giống nhau.

### 2.1. Các loại bộ nhớ dễ nhầm

| Thành phần | Cấp phát ở đâu? | Giới hạn/quan sát liên quan |
| --- | --- | --- |
| Java heap | Vùng heap của JVM | `-Xmx`, `-XX:MaxRAMPercentage`, GC logs/JFR |
| Direct NIO buffers | Dữ liệu thường nằm ngoài heap; object wrapper ở heap | `-XX:MaxDirectMemorySize` cho phạm vi direct-buffer allocations; `BufferPoolMXBean` |
| Mapped buffers | Ánh xạ vùng file/thiết bị vào address space | `BufferPoolMXBean` tên `mapped`, OS mmap/page accounting |
| JNI / native library | Native heap/malloc, mmap hoặc allocator riêng | OS memory metrics, công cụ native; **NMT không bao phủ hết** |
| Metaspace | Native memory quản lý class metadata | `-XX:MaxMetaspaceSize` nếu đặt; NMT `Class` |
| Code cache | Vùng mã máy do JIT tạo | `-XX:ReservedCodeCacheSize`, NMT `Code` |
| Thread stacks | Stack của platform/native threads | `-Xss`, NMT `Thread`, OS threads |
| GC/JVM structures | Vùng do collector/runtime cần | NMT `GC`/`Internal`/... |
| Shared libraries | Image/mapping của thư viện native | OS maps, RSS/PSS, file-backed memory |

Các cờ chỉ kiểm soát **một phần** của tiến trình. Không thể tính tổng footprint chắc chắn bằng cách lấy `Xmx + MaxDirectMemorySize` rồi bỏ mọi thành phần khác.

### 2.2. Reserve, commit và RSS khác nhau

- **Reserved virtual address space**: khoảng địa chỉ JVM/OS giữ trước cho sử dụng có thể xảy ra, nhưng không nhất thiết tiêu thụ RAM vật lý tương ứng.
- **Committed memory**: lượng memory được JVM/OS cấp phép sử dụng theo cơ chế memory management; có thể lớn hơn hoặc khác resident pages.
- **RSS (resident set size)**: các trang hiện có trong RAM theo góc nhìn process, có thể gồm shared/file-backed pages.
- **Container memory.current / working set**: số liệu theo cgroup/kênh giám sát, có thể gồm trang file cache hoặc accounting khác RSS tiến trình.

Ví dụ JVM có thể **reserve** vài GiB address space cho heap/code nhưng **committed** thấp hơn nhiều. Không lấy tổng `reserved` của NMT so trực tiếp với `memory.max` rồi kết luận container đã dùng hết RAM.

Ngược lại, chỉ đo `heap used` có thể bỏ sót native allocations đang nằm trong RSS/cgroup memory.

## 3. Direct ByteBuffer là gì?

### 3.1. Heap buffer và direct buffer

Java NIO có hai dạng thường gặp:

~~~java
java.nio.ByteBuffer heapBuffer =
        java.nio.ByteBuffer.allocate(4096);

java.nio.ByteBuffer directBuffer =
        java.nio.ByteBuffer.allocateDirect(4096);

System.out.println(heapBuffer.isDirect());   // false
System.out.println(directBuffer.isDirect()); // true
~~~

`ByteBuffer.allocate(4096)` tạo bộ đệm dữ liệu thường nằm trên **Java heap**.

`ByteBuffer.allocateDirect(4096)` tạo **direct byte buffer**: đối tượng `ByteBuffer` vẫn là một Java object, nhưng vùng dữ liệu có thể được quản lý **ngoài Java heap** để hỗ trợ trao đổi với native I/O và giảm một số bước copy trong những trường hợp phù hợp.

**Không nói mọi direct buffer đều nhanh hơn.** Cấp phát direct memory thường có chi phí cao hơn heap buffer, và hiệu quả phụ thuộc kích thước, số lượt sử dụng lại, loại I/O, thư viện và JVM.

### 3.2. Direct buffer không biến mất khỏi giới hạn container

Mặc dù direct buffer data nằm ngoài heap, nó vẫn thuộc memory footprint của tiến trình/JVM và có thể bị charge vào **memory cgroup** khi các trang liên quan được sử dụng.

~~~text
-Xmx=256m
Direct buffers đang sử dụng nhiều memory
JNI/native allocations cũng tăng

=> Container vẫn có thể OOM dù Java heap còn trống.
~~~

`-Xmx` **không giới hạn** tổng số byte trong direct buffers. Hai miền memory có thể phát triển song song, làm tăng tổng footprint.

### 3.3. Direct memory có lợi khi nào?

Các hệ thống dùng NIO/network I/O, file channels, messaging frameworks hoặc xử lý dữ liệu nhị phân có thể hưởng lợi từ direct buffers:

- Có thể giảm một số lần copy trung gian giữa heap và native I/O.
- Dùng lại buffer qua pooling để tránh cấp phát/free lặp lại.
- Có thể giảm áp lực **heap GC** khi nhiều payload bytes không nằm trên heap.
- Phù hợp cho một số thao tác giao tiếp với native code.

Nhưng cần cân nhắc:

- Native allocation và deallocation có overhead.
- Object wrapper/metadata vẫn tạo hoạt động trên heap.
- Direct buffer sống lâu hoặc bị giữ trong cache/pool sẽ chiếm off-heap memory.
- Pool quá lớn hoặc không có chính sách giới hạn có thể khiến container chạm OOM.
- Heap GC không phản ánh trực tiếp toàn bộ chi phí và vòng đời native data.

**Giảm heap usage không đồng nghĩa giảm memory cgroup usage.** Di chuyển payload từ heap sang direct buffer có thể chỉ **chuyển nơi** chịu áp lực.

## 4. -XX:MaxDirectMemorySize giới hạn điều gì?

### 4.1. Cờ vẫn được hỗ trợ trên HotSpot hiện đại

Oracle Java 17/25 Java launcher mô tả:

~~~text
-XX:MaxDirectMemorySize=<size>
~~~

Ví dụ:

~~~bash
java -Xmx256m -XX:MaxDirectMemorySize=64m -jar app.jar
~~~

`-XX:MaxDirectMemorySize=64m` đặt mức tối đa cho **các cấp phát direct-buffer thuộc phạm vi java.nio do HotSpot quản lý**. Đây không phải toàn bộ **native memory limit** của process và không phải một quota cgroup riêng.

Trong những JDK hiện đại, nếu không đặt cờ, JVM tự chọn mức phù hợp; **không nên viết một con số mặc định bất biến cho mọi JDK/build**. Khi cần biết giá trị/cấu hình thực, kiểm JVM flags và đo behavior trong môi trường triển khai.

### 4.2. Điều cờ này KHÔNG kiểm soát

Cờ `MaxDirectMemorySize` không nên được kỳ vọng sẽ:

- Giới hạn toàn bộ native `malloc()` của thư viện C/C++ được gọi từ JNI/JNA.
- Giới hạn thread stacks, metaspace hay JIT code cache.
- Giới hạn mọi `mmap` hoặc vùng địa chỉ file-backed.
- Giới hạn bộ nhớ riêng của mọi allocator/framework native.
- Giữ RSS/container memory luôn dưới `memory.max`.
- Bảo đảm mọi thư viện bên thứ ba phải tạo buffer qua `ByteBuffer.allocateDirect`.
- Loại bỏ nhu cầu đo memory usage ở mức OS/cgroup.

Một thư viện native có thể gọi `malloc(100 MiB)` mà không đi qua cơ chế direct-buffer reservation của Java NIO. Khi đó, **đặt MaxDirectMemorySize thấp không ngăn allocator của thư viện đó**.

### 4.3. Điều gì xảy ra khi cạn direct-buffer budget?

Khi cấp phát direct buffer vượt mức do JVM quản lý, Java có thể ném `OutOfMemoryError` liên quan **direct buffer memory**, ví dụ những thông điệp kiểu:

~~~text
java.lang.OutOfMemoryError: Cannot reserve ... bytes of direct buffer memory
~~~

Thông điệp, đường đi xử lý/đợi reclaim và chi tiết stack trace **phụ thuộc JDK implementation**. Trong các trường hợp khác, hệ điều hành có thể từ chối cấp phát native, hoặc kernel có thể giết container theo memory cgroup trước khi Java kịp ném lỗi có thông điệp như trên.

**Đừng viết unit test yêu cầu một thông điệp OOM cụ thể.** Để hiểu vấn đề, phải xem error type, JVM flags, direct buffer metrics và OS/cgroup events.

### 4.4. Heap giới hạn nhỏ không bảo đảm direct memory nhỏ

~~~text
Container limit = 512 MiB
-Xmx           = 256 MiB
MaxDirect      = 128 MiB

256 + 128 = 384 MiB, còn 128 MiB trên giấy
~~~

Nhưng 128 MiB “còn lại” vẫn phải chứa metaspace, JIT/code cache, stacks, GC/native runtime structures, JNI allocations, shared libraries và các chi phí cgroup khác.

Đây chỉ là một **bước đầu của memory budget**, không phải bằng chứng sẽ chạy an toàn.

## 5. Vòng đời, giải phóng và pooling direct buffers

### 5.1. Không có close() trực tiếp cho ByteBuffer thường

Trong **Java 17**, `java.nio.ByteBuffer` không phải `AutoCloseable`; một direct `ByteBuffer` thông thường **không có phương thức public `close()` hay `free()`** để caller luôn chủ động giải phóng native storage tức thời.

Với direct buffer do JVM cấp phát thông thường, cơ chế quản lý reachability/GC và cleaner nội bộ có thể giải phóng native storage **sau khi buffer không còn được tham chiếu và cleanup diễn ra**.

Vì vậy:

~~~java
java.nio.ByteBuffer b =
        java.nio.ByteBuffer.allocateDirect(1024);

// Sử dụng b...

b = null; // Không bảo đảm native storage được free ngay ở dòng này.
~~~

`b = null` chỉ bỏ một tham chiếu Java. Không có lời hứa rằng native memory sẽ được giải phóng đúng thời điểm đó. `System.gc()` cũng **không** là cơ chế quản trị đáng tin để ép direct memory được thu hồi lập tức; lời gọi có thể bị bỏ qua hoặc diễn ra không đúng thời điểm mong muốn.

### 5.2. Thư viện có thể có resource ownership riêng

Một số networking frameworks dùng **pooled direct buffers** và reference counting. Trong hệ có API `release()`/`close()` cụ thể, caller phải tuân thủ **hợp đồng thư viện**. Nếu không release, pool/native memory có thể bị giữ lâu hơn dự kiến.

Không áp quy tắc của một framework lên `ByteBuffer` thuần Java SE. Ngược lại, đừng giả định GC sẽ chủ động release tài nguyên do framework quản lý bằng reference count.

### 5.3. Tránh API nội bộ để giải phóng buffer

Không dùng `sun.misc.Unsafe` hoặc cast vào `sun.nio.ch.DirectBuffer` rồi gọi cleaner trực tiếp như hướng dẫn chung. Các API nội bộ không có hợp đồng Java SE ổn định, chịu encapsulation/module restrictions và có thể gây use-after-free nếu vẫn còn slice/view/tham chiếu.

Nếu cần thời điểm giải phóng được kiểm soát, chọn **API resource ownership được hỗ trợ** của thư viện hoặc Foreign Function & Memory API trên JDK đủ mới, với lifetime/arena phù hợp (trình bày ở mục 14). Đừng “sửa OOM” bằng cách can thiệp mù quáng vào native pointer.

### 5.4. Slices, duplicates và giữ tham chiếu

~~~java
java.nio.ByteBuffer root =
        java.nio.ByteBuffer.allocateDirect(8192);
java.nio.ByteBuffer view = root.slice();
~~~

`slice()`/`duplicate()` thường cùng chia sẻ dữ liệu phía sau. Dù mất tham chiếu tới `root`, vẫn còn `view` thì storage có thể chưa được reclaim.

Một cache chứa hàng nghìn `ByteBuffer` hoặc các views của chúng có thể vô tình giữ memory lâu. Hãy phân tích **reference graph**, cache lifetime và pool policies thay vì chỉ nhìn số instance class wrapper.

## 6. Thư viện native dùng memory ngoài heap theo những cách nào?

### 6.1. JNI và native allocator

Một ứng dụng Java có thể gọi C/C++ qua JNI/JNA. Native code có thể dùng:

~~~c
/* Mã C minh họa, không phải chương trình độc lập */
void *p = malloc(1024 * 1024);
/* ... dùng p ... */
free(p);
~~~

`malloc`/`free` ở trên do **native code** quản lý, không được Java GC tự động kiểm soát theo reachability của Java objects. Nếu bỏ `free` hoặc giữ native allocation trong cache vô hạn, process có thể **tăng RSS dù Java heap ổn định**.

Tình huống thường gặp:

- Compression/decompression codecs sử dụng native buffers.
- TLS/crypto/network I/O stack có buffers riêng.
- Image/AI/database/native client libraries.
- JNI wrappers tạo handle trỏ tới vùng nhớ C/C++.
- Native allocator dùng arenas, object pools hoặc thread-local caches.
- Memory-mapped file và vùng cấp phát từ `mmap`.

**Không coi mọi bộ nhớ ngoài heap đều là “direct ByteBuffer”.** Đó chỉ là một nhánh của native memory.

### 6.2. NewDirectByteBuffer và ownership

JNI có các API để **tạo direct byte buffer view trên một địa chỉ native** (ví dụ `NewDirectByteBuffer`). Nhưng việc có một Java `ByteBuffer` wrapper **không tự quy định ai sở hữu và ai giải phóng** vùng memory gốc.

Nếu một C library đã `malloc` rồi bọc vùng nhớ bằng direct buffer view, phải xem contract của thư viện về lifetime, reference/cleanup và thread safety. Không giả định `MaxDirectMemorySize` tự bắt buộc mọi vùng native do bên thứ ba tạo phải đi qua một ngân sách Java NIO thống nhất.

### 6.3. Native memory leak khác Java heap leak

| Dấu hiệu | Có thể là Java heap leak | Có thể là native leak |
| --- | --- | --- |
| Java heap after-GC tăng dần | Thường có | Có thể **không tăng** |
| RSS/cgroup memory tăng | Có | Có |
| Heap dump giữ nhiều object | Có thể thấy roots | Có thể chỉ thấy wrapper/handle rất nhỏ |
| `OutOfMemoryError: Java heap space` | Có thể | Không phải tín hiệu bắt buộc |
| Container exit do OOM kill | Có thể | Có thể |
| NMT Java Heap tăng | Có thể | Không đủ để phát hiện mọi native allocations |
| BufferPoolMXBean direct tăng | Nếu giữ nhiều direct buffers thì có thể | Chỉ phản ánh các pool được instrument |
| RSS tăng nhưng mọi NMT category tương đối ổn | Ít đặc trưng cho heap leak | Cần nghi external native allocations/page cache/mappings |

Không thể xác định chính xác “leak ở thư viện X” từ hai số heap used và RSS. Cần thêm bằng chứng theo thời gian, allocation profile, stack native hoặc một thí nghiệm có kiểm soát.

## 7. Phân biệt direct buffer, mapped buffer và page cache

### 7.1. MappedByteBuffer

~~~java
// Mã minh họa ở trong method đã xử lý IOException.
try (var channel = java.nio.channels.FileChannel.open(
        java.nio.file.Path.of("data.bin"),
        java.nio.file.StandardOpenOption.READ)) {
    java.nio.MappedByteBuffer mapped =
            channel.map(
                    java.nio.channels.FileChannel.MapMode.READ_ONLY,
                    0,
                    channel.size());
    // Dùng mapped trong phạm vi được thiết kế.
}
~~~

`MappedByteBuffer` ánh xạ file vào không gian địa chỉ process. Nó có đặc điểm về lifetime, I/O và OS page accounting khác những buffer `allocateDirect` cấp phát bằng cơ chế khác.

**Đừng lấy byte mapped capacity rồi cộng mù quáng vào RSS**: phần lớn vùng address space có thể chưa resident; file-backed pages có thể được chia sẻ. Container memory accounting có thể tính những trang cache hoặc mmap tùy trạng thái và kernel.

### 7.2. BufferPoolMXBean có thể có nhiều pool

Quản lý buffer pool của Java có thể liệt kê `direct`, `mapped` và những pool khác theo JVM. Không gộp `mapped` vào `direct` khi thiết kế ngân sách mà chưa hiểu cách ứng dụng tạo memory, và không mặc định các pool này bao quát toàn bộ allocations của third-party native libraries.

### 7.3. /dev/shm và file cache

Ngoài private anonymous memory, Linux cgroup có thể charge những vùng như page cache hoặc shared memory theo chính sách. Một container có `memory.current` tăng dù Java heap/direct buffer metrics không tăng tương ứng có thể liên quan file cache, mapped files hoặc tiến trình khác trong cgroup.

Với các số liệu quản lý container, xem cả `memory.stat`, phân biệt `anon`, `file`, `shmem` khi kernel hỗ trợ. Không cộng chồng các category con đã nằm trong cùng một tổng.

## 8. Bộ nhớ trong container: giới hạn nằm ở đâu?

### 8.1. Cgroup v2

Trên Linux cgroup v2, những file thường gặp:

~~~bash
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/memory.stat
~~~

Ví dụ **minh họa**, không phải số liệu từ máy của người đọc:

~~~text
memory.max       = 536870912
memory.current   = 492830720
memory.events:
  low 0
  high 0
  max 15
  oom 2
  oom_kill 1
~~~

`memory.max` thường là hard memory limit (đơn vị bytes) tại cgroup đang đọc. Giá trị `max` nghĩa là không có giới hạn cứng ở vị trí đó, nhưng vẫn có thể có ràng buộc cgroup cha hoặc host.

`memory.current` là memory usage theo **cgroup accounting**, không phải `Runtime.totalMemory()` hoặc số **heap used**.

`memory.events` ghi những biến cố như chạm limit, OOM và số tiến trình bị OOM kill. Cần hiểu đây là counter tích lũy và có thể khác theo kernel/version; đo delta trong đúng khoảng thời gian sự cố để kết luận.

### 8.2. Cgroup v1

Nếu hệ thống dùng cgroup v1, những tên file thường gặp gồm:

~~~text
memory.limit_in_bytes
memory.usage_in_bytes
memory.failcnt
memory.stat
memory.oom_control
~~~

Đường dẫn controller khác nhau theo mount/cgroup namespace. Không giả định mọi container Linux hiện đại đều dùng cgroup v1 hoặc mọi file dưới `/sys/fs/cgroup` giống nhau. Trong môi trường lạ, xem `/proc/self/cgroup` và mountinfo, hoặc dùng công cụ quản trị tương ứng.

### 8.3. Container OOM kill khác JVM OutOfMemoryError

**JVM OutOfMemoryError**: Java/JVM phát hiện không đáp ứng được một yêu cầu cấp phát trong vùng memory mà nó quản lý. Có thể ném `OutOfMemoryError` và in stack trace (trừ các trường hợp không thể xử lý bình thường).

**Container OOM kill**: kernel/cgroup quyết định chấm dứt tiến trình khi vượt điều kiện memory limit, có thể không cho JVM cơ hội ghi `OutOfMemoryError` hoặc heap dump.

Trong Kubernetes có thể thấy trạng thái `OOMKilled`, một số môi trường trả exit code **137** do SIGKILL. Tuy nhiên exit 137 **không tự chứng minh** nguyên nhân là memory cgroup OOM: SIGKILL có thể đến từ nguyên nhân khác. Đối chiếu với Pod status, kernel/cgroup events và timeline.

### 8.4. Container limit không đồng nghĩa Xmx

Nếu Pod có:

~~~yaml
resources:
  limits:
    memory: "512Mi"
~~~

thì `512Mi` là giới hạn memory **của container** theo cơ chế triển khai, không phải một lệnh `-Xmx512m`. JVM vẫn cần chỗ cho off-heap, native allocations, stacks, class metadata và các thành phần khác.

Nếu ép `-Xmx512m` ở container có hard limit 512 MiB, ứng dụng còn hoạt động dù heap chưa đạt Xmx nhưng rủi ro OOM kill tăng rõ rệt do không có headroom cho các thành phần khác.

## 9. Lập ngân sách memory thực tế: không chỉ tính -Xmx

Một phép ước lượng thô:

~~~text
Memory cần thiết cho tiến trình/container
≈ heap committed/resident
+ direct-buffer native footprint
+ metaspace/class
+ JIT/code cache
+ thread stacks/native thread structures
+ GC/JVM internal
+ external JNI/native libraries
+ file-backed/shared/cache & other charges (nếu áp dụng)
+ safety headroom
~~~

**Cảnh báo quan trọng:** đây là mô hình **capacity planning**, không phải công thức cộng các metric thô từ nhiều công cụ. Các nguồn OS/NMT/JMX có thể đo vùng chồng lấn, có định nghĩa `reserved`/`committed` khác nhau hoặc đo tại thời điểm khác nhau. Đừng lấy `RSS + NMT committed + direct buffer used` cộng thành “tổng RAM thực”, vì nhiều phần đã nằm trong RSS.

### 9.1. Ví dụ container 512 MiB: cấu hình có headroom

| Thành phần ước lượng | MiB |
| --- | ---: |
| Heap sử dụng ở tải đỉnh | 256 |
| Direct buffers | 64 |
| Metaspace/class | 48 |
| Thread stacks/native thread data | 32 |
| Code cache/JIT | 32 |
| JNI/native libraries | 40 |
| GC, allocator, file/other reserve | 16 |
| **Tổng ước lượng** | **488** |
| **Headroom so với 512 MiB** | **24** |

Bảng chỉ là **scenario giả định** để học cách lập ngân sách. 24 MiB headroom có thể quá ít khi workload thay đổi hoặc có page cache/JNI spike. Không áp dụng nguyên các con số này làm cấu hình production.

### 9.2. Ví dụ nguy cơ vượt ngân sách

| Thành phần ước lượng | MiB |
| --- | ---: |
| Heap | 320 |
| Direct buffers | 96 |
| Metaspace | 48 |
| Thread stacks | 32 |
| Code cache | 32 |
| JNI/native libraries | 40 |
| GC, allocator, other | 16 |
| **Tổng** | **584** |
| **Vượt container 512 MiB** | **72** |

`-Xmx=320m` nhỏ hơn `512Mi`, nhưng **tổng memory footprint kế hoạch 584 MiB** vượt hard limit. Vì vậy câu “Xmx nhỏ hơn memory limit nên không OOM” là sai.

### 9.3. Headroom bao nhiêu là đúng?

Không có một tỷ lệ phù hợp cho mọi ứng dụng. Headroom phụ thuộc:

- Số lượng platform threads và kích thước stack.
- Direct-buffer pool sizes, số connections và concurrency.
- Số class được tải/metaspace, framework và class loaders.
- JNI/native allocator, compression, TLS, buffers.
- GC, JIT, page cache, mmap và hoạt động khởi động.
- Peak traffic, fragmentation và khả năng container OOM kill.

Đánh giá bằng **peak usage theo thời gian**, thêm hệ số an toàn phù hợp rủi ro; thử tải trong cùng giới hạn Docker/Kubernetes và JDK build dự kiến.

## 10. Các cờ HotSpot liên quan — giới hạn nào điều khiển vùng nào?

| Cờ JVM | Phạm vi chủ yếu | Không nên hiểu sai |
| --- | --- | --- |
| `-Xmx` hoặc `-XX:MaxHeapSize` | Giới hạn Java heap tối đa | Không phải RSS/container memory limit |
| `-XX:MaxRAMPercentage` | Tỷ lệ memory JVM tham chiếu để chọn max heap theo heuristics | Không cắt tổng native memory theo tỷ lệ này |
| `-XX:MaxDirectMemorySize` | Giới hạn cấp phát direct NIO buffers thuộc phạm vi JVM quản lý | Không chặn `malloc` của JNI/third-party |
| `-XX:MaxMetaspaceSize` | Giới hạn metaspace class metadata (nếu đặt) | Không giới hạn toàn bộ native memory |
| `-Xss` | Cỡ stack Java thread kiểu platform theo JVM | Không đồng nghĩa tổng stack memory cố định |
| `-XX:ReservedCodeCacheSize` | Reserved code cache cho JIT | Không phải limit của JNI/native malloc |
| `-XX:+UseContainerSupport` | HotSpot nhận diện giới hạn container trên nền tảng hỗ trợ | Không tạo memory cgroup quota |
| `-XX:NativeMemoryTracking=summary` | Bật quan sát NMT ở mức nhóm nội bộ HotSpot | Không phải công cụ chặn cấp phát |
| `-XX:NativeMemoryTracking=detail` | Thông tin chi tiết hơn về allocations HotSpot | Không bao phủ toàn bộ JNI hoặc OS memory |

### 10.1. -Xmx và MaxRAMPercentage

Nếu không đặt `-Xmx`, JVM HotSpot có thể tính heap tối đa từ available memory mà nó nhận biết (gồm giới hạn container trên Linux khi hỗ trợ) và những ergonomics flags như `MaxRAMPercentage`.

~~~bash
java -XX:MaxRAMPercentage=60 -jar app.jar
~~~

Trong một container memory limit 1 GiB, số 60 là tỷ lệ hướng tới sizing Java **heap**, không phải cho phép tiến trình “dùng tối đa 60% RAM tổng cộng”. Native/direct memory vẫn cần ngân sách riêng.

**Không áp một default MaxRAMPercentage cố định cho mọi JDK/độ lớn heap.** Trong Java launcher có cả `MinRAMPercentage` dành cho hoàn cảnh heap nhỏ; giá trị mặc định và heuristics có thể khác theo build. Nếu muốn biết cấu hình thực, dùng flags/diagnostic trong môi trường triển khai.

### 10.2. Xss và số platform threads

Ví dụ:

~~~bash
java -Xss512k -jar app.jar
~~~

`-Xss` liên quan stack size của Java platform threads. Với nhiều threads, vùng stack reservation/commit và native metadata có thể tăng đáng kể, nhưng không nên tính *thread count × Xss* rồi khẳng định bằng RSS: stack pages được commit/touch khác nhau theo OS/JVM.

Trên JDK có virtual threads, số virtual threads **không tương đương** số platform/native thread stacks cùng kích thước `-Xss`. Tuy nhiên virtual threads cũng không làm biến mất mọi native memory (carrier threads, I/O, runtime vẫn tồn tại).

### 10.3. Không coi MaxDirectMemorySize là cơ chế chống mọi OOM

Một cấu hình ví dụ:

~~~bash
java -Xmx256m -XX:MaxDirectMemorySize=64m \
  -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Lệnh POSIX shell trên chỉ là mẫu; trên Windows nên dùng một dòng hoặc cú pháp nối dòng riêng. Chỉ dùng NMT cho mục đích quan sát/diagnostics sau khi cân nhắc overhead.

Cờ direct-buffer limit giúp kiểm **một nhánh** native memory. Để giới hạn native memory của thư viện khác, cần xem API/allocator, cấu hình pool, driver hoặc native library documentation. Một số framework có policy quản lý buffer riêng.

## 11. Quan sát direct-buffer usage bằng API Java được hỗ trợ

### 11.1. BufferPoolMXBean

Gói `java.lang.management` cung cấp `BufferPoolMXBean`, dùng được trên Java 17+:

~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;

for (BufferPoolMXBean pool :
        ManagementFactory.getPlatformMXBeans(
                BufferPoolMXBean.class)) {
    System.out.println(pool.getName());
    System.out.println(pool.getCount());
    System.out.println(pool.getTotalCapacity());
    System.out.println(pool.getMemoryUsed());
}
~~~

Các trường:

- `getName()`: tên pool, chẳng hạn `direct` hoặc `mapped`.
- `getCount()`: **ước lượng** số buffers.
- `getTotalCapacity()`: ước lượng tổng capacity buffers trong pool.
- `getMemoryUsed()`: ước lượng memory mà JVM sử dụng cho pool, hoặc **`-1` nếu không có số liệu**.

`memoryUsed` có thể khác `totalCapacity` do **alignment, allocator và chi phí implementation**. Các metric được liệt kê **không bao phủ mọi native library allocation**.

### 11.2. Khi nào metric hữu ích?

Nếu số direct buffers/tổng capacity tăng liên tục đồng thời memory cgroup tăng, đây là tín hiệu nên kiểm:

- Những nơi gọi `ByteBuffer.allocateDirect`.
- Pool/caching lifecycle của thư viện network/I/O.
- View/slice/duplicate giữ underlying storage.
- Backpressure và giới hạn số kết nối đồng thời.
- Retention qua executor/task queues.

Nhưng nếu JVM báo direct-buffer pool ổn định mà container RSS tăng, cần kiểm thêm **JNI native malloc, memory-mapped files, page cache, allocator fragmentation, thread stacks hoặc process khác**.

### 11.3. Không đặt test đòi số direct memoryUsed cố định

Ví dụ buffer capacity 4096 bytes không có nghĩa `getMemoryUsed()` bắt buộc đúng 4096: số liệu pool là estimate, và JVM có thể cộng alignment/overhead. Tương tự, số buffer objects trong pool có thể thay đổi khi cleaner chạy.

Ví dụ đầy đủ sau chỉ assert những điều được Java API bảo đảm: `capacity()`, `isDirect()` và nội dung `getInt()`. Các metric runtime được in **ở chế độ riêng**, không đưa vào stdout cố định.

## 12. Chương trình Java 17+ hoàn chỉnh: tính memory budget và tạo direct buffer

File **`NativeMemoryBudgetDemo.java`**:

~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.nio.ByteBuffer;
import java.util.List;
import java.util.Locale;

public final class NativeMemoryBudgetDemo {

    private NativeMemoryBudgetDemo() {
    }

    record Budget(
            String name,
            long limitMiB,
            long heapMiB,
            long directMiB,
            long metaspaceMiB,
            long threadMiB,
            long codeMiB,
            long externalNativeMiB,
            long otherMiB) {

        Budget {
            if (name == null
                    || limitMiB <= 0
                    || heapMiB < 0
                    || directMiB < 0
                    || metaspaceMiB < 0
                    || threadMiB < 0
                    || codeMiB < 0
                    || externalNativeMiB < 0
                    || otherMiB < 0) {
                throw new IllegalArgumentException(
                        "invalid memory budget");
            }
        }

        long plannedMiB() {
            return heapMiB + directMiB + metaspaceMiB
                    + threadMiB + codeMiB
                    + externalNativeMiB + otherMiB;
        }

        long headroomMiB() {
            return limitMiB - plannedMiB();
        }
    }

    static void show(Budget b) {
        System.out.printf(
                Locale.ROOT,
                "%s: limitMiB=%d plannedMiB=%d"
                        + " headroomMiB=%d overBudget=%s%n",
                b.name(),
                b.limitMiB(),
                b.plannedMiB(),
                b.headroomMiB(),
                b.headroomMiB() < 0);
    }

    static void showLiveBufferPools() {
        for (BufferPoolMXBean pool :
                ManagementFactory.getPlatformMXBeans(
                        BufferPoolMXBean.class)) {
            System.out.printf(
                    Locale.ROOT,
                    "pool=%s count=%d capacity=%d"
                            + " memoryUsed=%d%n",
                    pool.getName(),
                    pool.getCount(),
                    pool.getTotalCapacity(),
                    pool.getMemoryUsed());
        }
    }

    public static void main(String[] args) {
        Budget healthy = new Budget(
                "healthy",
                512,
                256, 64, 48, 32, 32, 40, 16);

        Budget risk = new Budget(
                "risk",
                512,
                320, 96, 48, 32, 32, 40, 16);

        for (Budget b : List.of(healthy, risk)) {
            show(b);
        }

        System.out.println("heapBelowLimitButRisk="
                + (risk.heapMiB() < risk.limitMiB()
                        && risk.headroomMiB() < 0));

        // Vùng dữ liệu bên ngoài Java heap.
        ByteBuffer direct = ByteBuffer.allocateDirect(4096);
        direct.putInt(0, 0x12345678);

        System.out.println("direct=" + direct.isDirect());
        System.out.println("directCapacity="
                + direct.capacity());
        System.out.println("directValue="
                + direct.getInt(0));

        // Không giả định getMemoryUsed chính xác bằng capacity.
        if (args.length == 1
                && "--live".equals(args[0])) {
            showLiveBufferPools();
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac --release 17 -encoding UTF-8 NativeMemoryBudgetDemo.java
java NativeMemoryBudgetDemo
~~~

**Stdout chính xác, không phụ thuộc máy chạy:**

~~~text
healthy: limitMiB=512 plannedMiB=488 headroomMiB=24 overBudget=false
risk: limitMiB=512 plannedMiB=584 headroomMiB=-72 overBudget=true
heapBelowLimitButRisk=true
direct=true
directCapacity=4096
directValue=305419896
~~~

### Giải thích kết quả

1. `healthy` là **bài toán ngân sách minh họa**: tổng ước lượng 488 MiB dưới limit 512 MiB, headroom chỉ 24 MiB. Điều này **không bảo đảm production an toàn**.
2. `risk` dự kiến dùng 584 MiB, vượt giới hạn 512 MiB **72 MiB**.
3. `heapBelowLimitButRisk=true` cho thấy heap ở scenario risk vẫn nhỏ hơn giới hạn container (320 MiB dưới 512 MiB), nhưng **tổng nhu cầu memory** đã cao hơn limit.
4. `ByteBuffer.allocateDirect(4096)` trả buffer direct có capacity đúng 4096 bytes theo API.
5. `getInt(0)` đọc đúng `0x12345678`, biểu diễn decimal là `305419896`; kết quả không phụ thuộc CPU/OS.
6. Chương trình không ép GC hoặc free buffer để đo thời điểm cleanup; không có giả định native memory được giải phóng tức thì.
7. Mô hình không dùng RSS/NMT thật để cộng trùng các số metric. Đây là **dữ liệu giả định lập ngân sách**.

Để xem **thêm số liệu thật** của pool Java NIO trong JVM:

~~~bash
java NativeMemoryBudgetDemo --live
~~~

Chương trình sẽ in thêm các dòng dạng:

~~~text
pool=direct count=... capacity=... memoryUsed=...
pool=mapped count=... capacity=... memoryUsed=...
~~~

Đây chỉ là **định dạng minh họa**, không phải stdout tuyệt đối, bởi tên và số lượng pool cũng như memory stats phụ thuộc JDK và trạng thái runtime. Một pool có thể báo `memoryUsed=-1` khi số liệu không khả dụng.

### Vì sao không ném OutOfMemoryError để “minh họa”?

Cố tình cấp phát direct memory đến hết quota trên container nhỏ có nguy cơ làm process bị OOM kill, ảnh hưởng thiết bị/CI và tạo test không ổn định. Mô hình budget cho phép học nguyên tắc mà **không chủ động exhaust memory**. Khi cần load-test real allocations, dùng môi trường cách ly và giới hạn thời gian/nguồn lực thích hợp.

## 13. Chẩn đoán với Native Memory Tracking (NMT) và jcmd

### 13.1. Bật NMT khi khởi động

NMT là tính năng của **HotSpot**, được Oracle Java 17/25 hỗ trợ:

~~~bash
java -XX:NativeMemoryTracking=summary -jar app.jar
~~~

Hoặc khi cần chi tiết:

~~~bash
java -XX:NativeMemoryTracking=detail -jar app.jar
~~~

NMT thường **tắt theo mặc định** và cần được bật từ khi JVM khởi động. `summary` gom theo subsystem; `detail` cho thêm allocation call sites/virtual memory regions, có overhead lớn hơn.

NMT có **chi phí hiệu năng/bộ nhớ**. Oracle troubleshooting hướng dẫn thận trọng khi bật ở production và nêu overhead có thể đáng kể tùy workload. Chỉ bật phù hợp mục đích quan sát và giai đoạn điều tra.

### 13.2. Gọi jcmd trên process đang chạy

Với PID thực của JVM, các lệnh ví dụ:

~~~bash
jcmd 12345 VM.native_memory summary scale=MB
jcmd 12345 VM.native_memory baseline
jcmd 12345 VM.native_memory summary.diff scale=MB
~~~

`12345` chỉ là một PID minh họa. Thay bằng PID thực, cần quyền chẩn đoán phù hợp và công cụ JDK có khả năng attach vào JVM đích.

**Một workflow hợp lý:**

1. Khởi động ứng dụng với `-XX:NativeMemoryTracking=summary`.
2. Khi hệ thống ổn định, đặt `baseline`.
3. Khi memory footprint tăng, lấy `summary.diff` để xem nhóm nào tăng.
4. Nếu nghi nguyên nhân bên trong HotSpot, chạy lại ở môi trường thử với `detail` để có thêm call-site data.
5. Đối chiếu với RSS/cgroup metrics trong cùng time window.

NMT output gồm các nhóm như Java Heap, Class, Thread, Code, GC, Compiler, Internal, Symbol và Other (tùy JDK). Các nhóm này có thể thay đổi qua bản phát hành, nên **không viết parser hard-coded** cho đúng một biểu mẫu NMT mãi mãi.

### 13.3. Giới hạn quan trọng của NMT

Oracle Java VM Guide nói rõ **NMT theo dõi memory được JVM/HotSpot cấp phát**, **không theo dõi đầy đủ cấp phát của code native bên thứ ba hay một số JDK class libraries**.

Vì vậy:

~~~text
NMT committed tăng ít
RSS hoặc container memory.current tăng nhiều

=> Không thể kết luận không có native memory leak.
=> Cần tiếp tục điều tra JNI/native libraries, mmap,
   allocator caches, file-backed pages và số liệu OS.
~~~

Một số cấp phát Java NIO được HotSpot hạch toán vào các hạng mục nội bộ có thể xuất hiện trong NMT, nhưng **đừng khẳng định toàn bộ direct-buffer data luôn nằm đúng một category cố định và mọi JNI malloc đều được NMT nhìn thấy**.

NMT cũng không phải phép đo toàn bộ RSS: reserved/committed khác resident; shared mappings và OS cache có thể được accounting khác. NMT và OS metrics cần **bổ trợ nhau**, không cộng chồng như hai cục bộ nhớ độc lập.

## 14. Quy trình điều tra khi heap ổn định nhưng container memory tăng

### Bước 1 — Xác nhận đúng triệu chứng

Đo theo cùng timeline:

- `memory.current`/memory working set của container.
- `memory.max`/Kubernetes memory limit.
- Java heap **used after GC**, heap committed và max.
- RSS/PSS/anonymous/file-backed memory của tiến trình.
- Direct/mapped pool metrics.
- Số platform threads, metaspace, code cache và JNI activity.
- Sự kiện `OOMKilled` hoặc `memory.events` nếu có.

Nếu chỉ nhìn dashboard `jvm_memory_used_bytes{area="heap"}`, có thể bỏ sót phần tăng chính nằm ngoài heap.

### Bước 2 — Phân loại loại memory đang tăng

| Quan sát | Hướng điều tra |
| --- | --- |
| Heap after-GC tăng liên tục | Java object retention, cache, heap dump |
| Direct buffer pool capacity/memory tăng | NIO buffer lifecycle, connection pool, resource release |
| Mapped buffer pool tăng | Memory mappings, file channels, file sizes |
| NMT Class/Metaspace tăng | Class loading, dynamic class loaders |
| NMT Thread tăng | Thread proliferation, stack reservation/commit |
| NMT Code/Compiler tăng | JIT compilation/code cache |
| RSS/cgroup tăng, NMT ổn định | JNI/native malloc, mmap/page cache, allocator fragmentation, external processes |
| memory.stat file tăng | Page cache/file-backed accounting, không vội kết luận heap/native leak |
| OOM kill nhưng không có Java OOME | Kernel/cgroup enforcement, cần xem memory.events và Pod status |

Không có tín hiệu nào đủ để kết luận chính xác toàn bộ nguyên nhân. Cần tương quan thời gian và đối chiếu memory categories.

### Bước 3 — Kiểm direct-buffer pressure

Đọc `BufferPoolMXBean` trong một khoảng thời gian, không chỉ một snapshot:

- `direct.count` có tăng cùng số active connections?
- `direct.totalCapacity` có đạt mức ứng dụng/pool dự kiến?
- `direct.memoryUsed` có khả dụng không và có tăng theo?
- Kết nối/tác vụ kết thúc có trả buffer cho pool hoặc gọi `release()` theo contract?
- Có nhiều `slice()`/`duplicate()` giữ underlying storage?
- Có dữ liệu tồn đọng do backpressure/queue không được giới hạn?

Nếu dùng framework có native allocator riêng, xem **metrics và leak detection của framework đó** vì BufferPoolMXBean không phải bảng kê toàn bộ allocations.

### Bước 4 — Kiểm external native allocations

Nếu Java heap và NIO pool vẫn ổn nhưng OS metrics tăng:

1. Xem NMT categories (nếu đã bật) và các số committed/reserved.
2. Xem process memory maps và anonymous/file-backed mappings theo OS.
3. Kiểm JNI/JNA libraries, versions, native allocation ownership.
4. Dùng profiler/tracing native phù hợp môi trường (ví dụ công cụ allocator hoặc system profiling được tổ chức cho phép).
5. Kiểm thread stacks, glibc allocator arenas/caches, mapped files và sidecar processes.
6. Tái hiện bằng workload kiểm soát; so khi bật/tắt từng thành phần tích hợp.

Không ép NMT phải chỉ ra tên C function gây leak; phạm vi của NMT không bao gồm mọi malloc của code ngoài HotSpot.

### Bước 5 — Kiểm phản ứng của kernel/cgroup

Ở cgroup v2, đọc `memory.events` trước/sau spike. Nếu `oom_kill` tăng cùng thời điểm process biến mất, đây là bằng chứng mạnh hơn cho memory cgroup OOM. Đồng thời xem Kubernetes status/events và node memory pressure.

Trong các trường hợp file cache tăng, kernel có thể reclaim một phần cache khi áp lực bộ nhớ; vì vậy một thời điểm `memory.current` cao không tự động tương đương leak không thể thu hồi. Tìm xu hướng dài hạn và nguyên nhân charge vào cgroup.

### Bước 6 — Đặt giới hạn và kiểm lại

- Cân chỉnh `-Xmx`/`MaxRAMPercentage` sao cho còn headroom.
- Giới hạn hoặc làm nhỏ direct-buffer pools khi có bằng chứng.
- Tối ưu số connections và backpressure.
- Kiểm thread count/stacks nếu thread proliferation.
- Fix lifetime/release của JNI/native allocations.
- Chọn memory limit container phù hợp với peak workload.
- Chạy load test nhiều lượt, theo dõi OOM events và p95/p99 latency sau thay đổi.

**Không “sửa” bằng cách chỉ tăng `-Xmx`** khi vấn đề nằm ở off-heap/native: tăng heap có thể còn làm container OOM sớm hơn.

## 15. Các lỗi hiểu nhầm phổ biến

| Nhận định sai | Vì sao sai? | Cách xử lý |
| --- | --- | --- |
| “Heap used thấp thì container không thể OOM.” | Native/direct/metadata/stacks vẫn cần memory | Xem RSS/cgroup + nhiều pool |
| “`-Xmx` bằng container limit là tối ưu nhất.” | Không còn headroom | Dành ngân sách cho non-heap |
| “Direct buffer là Java heap array.” | Data của direct buffer nằm ngoài heap | Dùng đúng `isDirect()`/MXBean |
| “Direct buffer không tính vào memory container.” | Native pages vẫn bị charge | Đo cgroup memory |
| “`MaxDirectMemorySize` giới hạn tất cả native malloc.” | Chỉ phạm vi NIO direct buffer do JVM quản lý | Giới hạn/pool JNI riêng |
| “MaxRAMPercentage giới hạn toàn bộ process.” | Nó chủ yếu tính max heap | Dành headroom native |
| “ByteBuffer có close/free public trên Java 17.” | API Java SE không có phương thức đó | Dựa vào lifetime/contract |
| “Đặt buffer = null là native memory được free ngay.” | Cleanup không tức thời | Tránh retention, quản lý pool |
| “Gọi System.gc() bảo đảm direct memory giảm.” | Không bảo đảm thời điểm GC/cleaner | Theo dõi lifecycle thật |
| “Mọi direct buffer view sở hữu memory độc lập.” | Slice/duplicate có thể chia sẻ backing memory | Kiểm root buffer/lifetime |
| “Một NMT Other category là toàn bộ JNI memory.” | NMT không bao phủ mọi code native | Dùng thêm OS/native profiling |
| “NMT reserved = RSS thực.” | Reserved là vùng địa chỉ, không phải RAM resident | So committed/RSS đúng nghĩa |
| “Cộng RSS + NMT committed để tính process memory.” | Hai nguồn có overlap | Không cộng hai tổng |
| “memory.current bằng Java heap size.” | Cgroup charge nhiều thành phần | Đọc memory.stat và process metrics |
| “Một exit code 137 chắc chắn là Java heap OOME.” | SIGKILL có nhiều nguyên nhân | Xem OOMKilled/memory.events |
| “JNI malloc được Java GC tự động giải phóng.” | Native allocation có ownership riêng | Ghép free/close theo contract |
| “Heap dump luôn thấy toàn bộ native leak.” | Heap dump có thể chỉ thấy wrapper rất nhỏ | Dùng native/OS profiler |
| “Mapped buffer capacity = RAM resident.” | Mapping có thể không resident hoặc shared | Đọc mmap/page accounting |
| “NMT detail không tốn overhead.” | Tracking tăng chi phí memory/CPU | Bật có kiểm soát |
| “Sửa OOM bằng Unsafe cleaner.” | API nội bộ không ổn định, use-after-free | Dùng supported lifetime APIs |
| “Giảm direct memory luôn tăng tốc.” | Có trade-off I/O copy và pooling | Benchmark thực tế |

## 16. Checklist và câu hỏi ôn tập

### Checklist cho developer

1. Hiểu `-Xmx` là giới hạn Java heap, không phải memory limit của process.
2. Biết `ByteBuffer.allocateDirect` dùng dữ liệu ngoài heap, trong khi Java object vẫn được GC quản lý.
3. Không coi direct buffer và JNI allocations là một vùng có cùng chính sách.
4. Dùng `BufferPoolMXBean` để quan sát direct/mapped pools với caveat số **ước lượng**.
5. Không tự gọi API nội bộ `Unsafe`/cleaner để ép free buffer.
6. Nếu thư viện dùng reference counting/pools, tuân thủ `close/release` đúng contract.
7. Giới hạn queues/connections/backpressure để tránh giữ nhiều direct buffers.
8. Kiểm leak của native libraries bằng công cụ phù hợp, không chỉ heap dump.
9. Đo peak ngoài heap bằng OS/cgroup và nhận diện source dữ liệu nào trùng nhau.
10. Có load test với cùng memory limit container và peak concurrency dự kiến.

### Checklist cho vận hành

1. Xác nhận memory limit thực của container và cgroup v1/v2.
2. Theo dõi `memory.current`, `memory.events` và `memory.stat` trên cgroup v2.
3. So heap used/committed/max, direct/mapped pool metrics và RSS/PSS.
4. Bật NMT từ startup cho cửa sổ điều tra phù hợp; không bật detail không giới hạn.
5. Dùng `jcmd VM.native_memory summary`/`summary.diff` nếu NMT đang bật.
6. Hiểu NMT không bao quát các allocations native bên thứ ba.
7. Phân biệt JVM `OutOfMemoryError` với cgroup `oom_kill`.
8. Không suy memory leak từ reserved VM address space.
9. Đặt headroom cho metaspace, stacks, JNI, page cache, JVM subsystems.
10. Xem các file/sidecar khác bị charge chung memory cgroup.
11. Khi thay memory limit hoặc Xmx, chạy lại workload và theo dõi peak.
12. Giữ tài liệu JDK theo đúng phiên bản/runtime image, không dựa vào số mặc định đã cũ.

### Tự kiểm tra

**Câu 1.** Container memory limit 512 MiB, `-Xmx=256m`. Ứng dụng có thể OOM do direct buffers không?

**Đáp án:** Có. Direct buffers dùng off-heap memory, còn có metaspace, stacks, JNI và các allocations khác.

**Câu 2.** `-XX:MaxDirectMemorySize=64m` có giới hạn toàn bộ `malloc` của thư viện C++ không?

**Đáp án:** Không. Nó giới hạn những cấp phát Java NIO direct buffers thuộc phạm vi JVM quản lý, không phải mọi malloc bên ngoài HotSpot.

**Câu 3.** Vì sao direct buffer không có `close()` trong Java 17?

**Đáp án:** `ByteBuffer` không thực thi `AutoCloseable`; vòng đời direct storage thông thường liên quan reachability/cleanup JVM. Nếu thư viện cung cấp release/close riêng, cần tuân thủ contract đó.

**Câu 4.** `BufferPoolMXBean.getMemoryUsed()` có bắt buộc bằng `getTotalCapacity()` không?

**Đáp án:** Không. MemoryUsed là số ước lượng có thể khác do alignment/allocator, và có thể trả -1 nếu không có số liệu.

**Câu 5.** NMT có báo đầy đủ JNI native allocations không?

**Đáp án:** Không. NMT chủ yếu theo dõi vùng memory của JVM/HotSpot, không phải mọi cấp phát thư viện native bên ngoài.

**Câu 6.** Vì sao tổng NMT reserved lớn hơn container limit chưa chắc là vấn đề?

**Đáp án:** Reserved virtual address space không phải RAM resident hay memory thực tế đã commit/charge; cần hiểu committed và OS/cgroup metrics.

**Câu 7.** `memory.current` có bằng Java heap used không?

**Đáp án:** Không. Cgroup accounting tính nhiều loại trang bộ nhớ có thể gồm file cache, native memory và các process khác.

**Câu 8.** Container có exit 137 có nghĩa chắc chắn `OutOfMemoryError: Java heap space`?

**Đáp án:** Không. Cần xem Pod status `OOMKilled`, `memory.events` và nguồn SIGKILL.

**Câu 9.** Nếu direct pool metrics ổn định nhưng RSS tăng, tiếp theo kiểm gì?

**Đáp án:** JNI/native malloc, memory-mapped files, file cache, allocator, thread stacks và các nguồn khác, kèm OS/native profiler.

**Câu 10.** Thay `-XX:MaxRAMPercentage` có thay cgroup memory.max không?

**Đáp án:** Không. Nó ảnh hưởng heap sizing, còn cgroup memory limit do Docker/Kubernetes/Linux quản lý.

**Câu 11.** Có nên dùng `System.gc()` làm công cụ free direct memory đúng thời điểm?

**Đáp án:** Không. Không có bảo đảm tương ứng chính xác về GC/cleaner và nhiều thư viện quản lý native buffers riêng.

**Câu 12.** Với memory limit 512 MiB, planned usage 584 MiB, thiếu bao nhiêu?

**Đáp án:** Thiếu 72 MiB theo mô hình ngân sách. Phải giảm nhu cầu hoặc tăng limit và dành thêm headroom thích hợp.

## 17. Tài liệu chính thức và nguồn hiện còn áp dụng

- [Oracle Java SE 25 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/25/vm/native-memory-tracking.html): phạm vi theo dõi JVM/HotSpot, giới hạn với third-party native code/JDK class libraries và yêu cầu bật tracking từ startup.
- [Oracle Java SE 25 — Diagnostic Tools](https://docs.oracle.com/en/java/javase/25/troubleshoot/diagnostic-tools.html): `jcmd VM.native_memory`, baseline/diff, reserved/committed, overhead và phân tích native memory.
- [Oracle Java SE 25 — The java Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html): `-XX:MaxDirectMemorySize`, `-Xmx`, `-XX:MaxRAMPercentage`, `-XX:NativeMemoryTracking` và `-Xlog:os+container`.
- [Oracle Java SE 17 — ByteBuffer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/ByteBuffer.html): `allocate()`, `allocateDirect()`, `isDirect()` và đặc tính direct buffers.
- [Oracle Java SE 17 — BufferPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html): `direct`/`mapped` pool, `getCount`, `getTotalCapacity`, `getMemoryUsed`.
- [Oracle Java SE 17 — Runtime Memory Methods](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Runtime.html): phân biệt `totalMemory`, `freeMemory` và `maxMemory` thuộc Java heap.
- [Oracle Java SE 17 — jcmd](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html): `VM.native_memory` và các lệnh chẩn đoán HotSpot.
- [Linux Kernel — cgroup v2 Documentation](https://docs.kernel.org/admin-guide/cgroup-v2.html): `memory.max`, `memory.current`, `memory.events`, `memory.stat` và nguyên tắc memory accounting.
- [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/): giới hạn memory container và ứng xử khi vượt memory limit.
- [Oracle JDK 10 Release Notes](https://www.oracle.com/java/technologies/javase/10-relnote-issues.html): cải tiến Docker/container awareness từ Java 10.
- [OpenJDK JEP 454 — Foreign Function & Memory API](https://openjdk.org/jeps/454): API quản lý vùng nhớ native/lifetime được chuẩn hóa từ Java 22, dùng khi ứng dụng có target JDK phù hợp.

**Kết luận:** **Direct NIO buffers và các thư viện native tiêu thụ memory ngoài Java heap nhưng vẫn có thể làm tăng footprint của container.** `-Xmx`, `MaxDirectMemorySize` và `MaxRAMPercentage` kiểm soát **những phạm vi khác nhau**, không bảo đảm tổng RSS/cgroup memory dưới hard limit. Hãy lập ngân sách cả heap lẫn non-heap/native, kiểm `BufferPoolMXBean`, dùng NMT đúng giới hạn và đối chiếu với OS/cgroup metrics. Khi heap ổn định nhưng memory container tăng, hãy điều tra **JNI/native allocations, mapped memory, page cache và vòng đời direct buffers** thay vì chỉ tăng heap hoặc gọi GC thủ công.