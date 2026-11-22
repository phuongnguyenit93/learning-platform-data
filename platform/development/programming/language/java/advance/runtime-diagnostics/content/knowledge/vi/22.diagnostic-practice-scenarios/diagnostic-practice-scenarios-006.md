# 22.6 So sánh bộ nhớ tiến trình, heap, NMT và direct buffer trong một tình huống tăng bộ nhớ

## Mục tiêu

Một service Java có thể báo heap used ổn định ở 350 MiB, trong khi biểu đồ “process memory” tăng từ 760 lên 1.180 MiB rồi container chạm giới hạn. Tình huống này **không tự chứng minh Java heap bị leak**, cũng không chứng minh native memory leak. Người điều tra cần biết mỗi nguồn dữ liệu đang đo **lớp bộ nhớ nào**, theo **đơn vị nào**, ở **thời điểm nào** và có **bao hàm/chồng lấp** với nguồn khác hay không.

Trong chủ đề thực hành tổng hợp này, chúng ta đối chiếu bốn góc nhìn chính:

1. **Bộ nhớ tiến trình:** Linux RSS/PSS, virtual size, anonymous/file-backed mappings, native allocations.
2. **Java heap:** used, committed, max, hành vi GC, live set và ý nghĩa của số liệu sau GC.
3. **HotSpot Native Memory Tracking (NMT):** reserved/committed theo hạng mục JVM, baseline/diff, phạm vi NMT đo được và các khoảng trống.
4. **Direct buffers:** ByteBuffer.allocateDirect, BufferPoolMXBean, bytes/capacity/count, vòng đời off-heap và mối liên hệ *có thể có* với NMT.

Sau bài học, bạn có thể lập bảng snapshot đúng thời gian, tránh cộng trùng, nhận diện giả thuyết hợp lý khi RSS tăng khác nhịp với heap/NMT/direct, thu số liệu bằng jcmd/JMX/proc/cgroup, rồi thiết kế một phép kiểm chứng không làm tình trạng thiếu bộ nhớ nặng thêm.

**Phạm vi:** Java 17+ trên HotSpot/OpenJDK; ví dụ lệnh jcmd theo JDK 21; Linux và cgroup v2 nếu đang chạy trong container. Tên hạng mục NMT và mức bao phủ có thể khác giữa JDK/vendor. Không áp dụng các công thức cân bằng bên dưới như một phép “hạch toán chính xác từng byte”: các phép đo có **định nghĩa và thời điểm khác nhau**.

## 1. Bốn góc nhìn không nằm ở bốn ngăn độc lập

Mô hình khái niệm:

~~~text
Host / kernel / container memory accounting
|
+-- Java process
|   |
|   +-- Java heap: objects, arrays, heap regions
|   +-- JVM runtime native areas:
|   |     metaspace, class metadata, code cache,
|   |     thread structures/stacks, GC data, JIT compiler...
|   +-- Off-heap / direct / native:
|   |     direct ByteBuffer storage, native libraries,
|   |     malloc arenas, JNI allocations, mappings...
|   +-- File-backed / shared mappings:
|         libraries, mapped files, shared pages...
|
+-- Other processes in the same memory cgroup
+-- File/page cache and some kernel charges
~~~

Gắn từng đồng hồ đo lên mô hình:

- **Java heap used:** phần heap JVM đang sử dụng theo định nghĩa memory pool/MXBean; không phải toàn bộ vùng nhớ của process.
- **Heap committed:** bộ nhớ ảo JVM đã cam kết cho heap theo API/runtime; không tự là số trang vật lý đang resident.
- **NMT:** theo dõi nhiều cấp phát và vùng bộ nhớ **nội bộ HotSpot**; có cả hạng mục Java Heap và các vùng native do VM theo dõi. Vì vậy NMT total **không phải “native ngoài heap”**.
- **Direct BufferPoolMXBean:** ước lượng usage của các buffer pools JVM báo cáo; một phần off-heap này có thể đã nằm trong NMT ở hạng mục thích hợp trên bản triển khai đang dùng. Nó không phải một khoản luôn luôn cần cộng thêm.
- **Process RSS:** các trang bộ nhớ vật lý hiện resident và được ánh xạ vào tiến trình, gồm anonymous và file-backed/shared pages; có thể bao gồm trang tương ứng với heap, một số native areas và mappings. RSS không phản ánh toàn bộ virtual reserved space.
- **Cgroup memory.current:** lượng bộ nhớ đang bị tính cho cgroup, có thể bao gồm file cache, kernel memory và các process khác; **không đồng nhất với RSS của một PID**.

Do đó phép tính sau **sai về mô hình**:

~~~text
total_memory = process_RSS + heap_used + NMT_committed + direct_used
~~~

Các đại lượng này chồng lấp hoặc dùng phương pháp đo khác nhau. Nếu RSS đã chứa phần heap resident, cộng heap vào RSS là đếm lại. Nếu NMT total đã bao gồm committed Java Heap, cộng heap committed vào NMT total là đếm lại. Nếu direct allocation được NMT ghi nhận ở một hạng mục, cộng direct pool vào NMT total lại có thể đếm trùng.

## 2. Định nghĩa chuẩn trước khi so sánh

| Đại lượng | Nguồn điển hình | Thước đo | Câu hỏi trả lời | Điều **không** được suy |
| --- | --- | --- | --- | --- |
| Heap used | MemoryMXBean / JMX / GC telemetry | Bytes | Heap đang được sử dụng theo runtime | Toàn bộ process RSS hoặc retained live objects |
| Heap committed | MemoryMXBean / JMX | Bytes | JVM đã cam kết dung lượng heap bao nhiêu | Tất cả committed pages đang resident |
| Heap max | MemoryMXBean / -Xmx | Bytes hoặc undefined | Giới hạn heap mà runtime công bố | Container memory limit |
| NMT reserved | jcmd VM.native_memory | KB/MB/GB | Vùng địa chỉ/virtual reservations do NMT theo dõi | RAM vật lý đang dùng |
| NMT committed | jcmd VM.native_memory | KB/MB/GB | Bộ nhớ các subsystem HotSpot báo đã commit | Bằng RSS hay bao trọn mọi malloc trong process |
| Direct pool memoryUsed | BufferPoolMXBean | Bytes, có thể -1 | Ước lượng bộ nhớ của buffer pool | Toàn bộ off-heap/JNI/native memory |
| Direct pool totalCapacity | BufferPoolMXBean | Bytes | Tổng logical capacities thuộc pool | Physical RSS hoặc native allocation chính xác |
| VmRSS/RSS | /proc/PID/status, smaps_rollup, ps | kB/KiB tùy tool | Resident pages của process | Private memory duy nhất của process |
| PSS | /proc/PID/smaps_rollup | kB | Shared pages phân bổ tỷ lệ cho process | JVM heap used |
| VmSize/VSZ | /proc/PID/status, ps | kB | Tổng virtual address space mappings/reservations | RAM đã cấp phát vật lý |
| memory.current | cgroup v2 | Bytes | Charge bộ nhớ của toàn cgroup | RSS của riêng Java PID |
| memory.stat anon/file | cgroup v2 | Bytes | Một số nhóm charge trong cgroup | Bản đối chiếu một–một với NMT categories |

**Đơn vị:** NMT với scale=MB và các tiện ích Linux có thể dùng cách định nghĩa MB/KiB khác cách đặt tên trong dashboard. Quy ước thống nhất trong ví dụ ở bài: **1 MiB = 1.048.576 bytes**; nếu số liệu từ lệnh dùng kB/KiB, ghi cách chuyển đổi trước khi trừ. Sai lệch do MB thập phân và MiB nhị phân không giải thích được mọi chênh lệch lớn, nhưng có thể làm bảng thiếu chính xác.

## 3. Java heap: used, committed, max và live set

### 3.1. Heap used chưa chắc là bộ nhớ còn sống

Heap used là dung lượng đang sử dụng theo cách JVM báo; nó có thể chứa các object đã không còn reachable **nhưng chưa được GC thu gom**. Không thể chỉ lấy heap used ở hai timestamp rồi kết luận retained live set thay đổi đúng bằng chênh lệch.

Muốn xét **heap leak / retention**, ưu tiên:

- Chuỗi thời gian **heap usage sau các chu kỳ GC tương đương**, đặc biệt old-generation live set ở steady state.
- Allocation rate, GC frequency, số lượng/loại object, classloader, cache occupancy.
- Heap dump/dominator tree khi cần và có đủ quyền/bộ nhớ lưu; phân biệt objects còn reachable với các vùng native.
- Cùng workload, traffic, payload, warm-up, GC collector và Xmx.

Một biểu đồ heap hình răng cưa tăng rồi giảm về baseline có thể là allocation pressure bình thường, không phải leak. Ngược lại một baseline sau GC tăng đều với lượng công việc tương đương đáng điều tra object retention.

### 3.2. Heap committed không bằng heap used hoặc RSS

JVM có thể commit một vùng heap lớn để tối ưu allocation/GC, trong khi số byte used thấp. Chuyển từ used=350 MiB sang used=355 MiB không có nghĩa process RSS chỉ tăng 5 MiB; native allocations và resident pages khác vẫn có thể thay đổi.

Heap committed cũng **không nhất thiết tương đương số trang vật lý đã fault vào RAM**. Trên Linux, việc reserve/commit/mmap/huge pages/transparent huge pages và touch pages ảnh hưởng RSS. JVM có thể giữ heap committed không giảm ngay khi used giảm sau GC; behavior phụ thuộc collector và chính sách uncommit.

### 3.3. Xmx không phải bộ nhớ tối đa của container

-Xmx thường giới hạn Java heap tối đa, **không giới hạn** metaspace, code cache, direct buffers, thread stacks, JNI/native malloc, JIT/GC bookkeeping, file mappings hay page cache được tính trong cgroup. Container có memory.max=1.5 GiB và -Xmx=1 GiB vẫn có thể OOMKilled khi native/cgroup charges vượt headroom.

Với memory pressure, kiểm tra cả heap **và** process/cgroup metrics; không tự tăng Xmx khi RSS hoặc memory.current đã gần giới hạn.

## 4. Bộ nhớ tiến trình ở Linux: RSS, VSS và PSS

### 4.1. RSS là gì?

Resident Set Size (RSS) xấp xỉ số trang hiện có trong RAM được ánh xạ vào process. Thường bao gồm:
- anonymous resident pages: heap, một số native allocations/stacks;
- file-backed resident pages: shared libraries, mapped files;
- shared-memory pages;
- các vùng hợp lệ theo kernel accounting.

Trong /proc/PID/status, VmRSS thường được biểu diễn tương ứng với **RssAnon + RssFile + RssShmem** theo giao diện kernel. RSS từ proc/status có thể không là snapshot tuyệt đối chính xác ở từng thời điểm vì cơ chế accounting; smaps_rollup cho phân tích chi tiết hơn nhưng đọc có overhead.

**RSS không chỉ là native heap.** Nó bao phần heap đã resident, code, stacks, mappings và một số shared pages. Nếu hai JVM cùng map một thư viện, RSS của cả hai có thể cùng ghi nhận các shared pages; cộng RSS của nhiều process có thể đếm lại physical pages.

### 4.2. VSS/VmSize thường rất lớn mà vẫn bình thường

Virtual address space bao gồm vùng reserved, mapped nhưng chưa resident, class space reservation, guard pages, thread stack reservations và các vùng khác. Một JVM có VmSize 8 GiB nhưng RSS 700 MiB **không tự** nghĩa nó dùng 8 GiB RAM. Đó là khác biệt cốt lõi giữa **reserved virtual** và **resident physical**.

Cũng không dùng NMT “Total reserved = vài GiB” để kết luận container sắp chạm RAM limit. Cần nhìn committed, RSS, cgroup usage và memory pressure.

### 4.3. PSS/USS khi có nhiều shared mappings

- **PSS (Proportional Set Size):** resident shared pages được chia tỷ lệ giữa những process cùng dùng; có ích khi quy chi phí giữa nhiều process.
- **USS/private RSS** (tùy công cụ, thường suy từ Private_Clean + Private_Dirty trong smaps): phần resident không được chia sẻ theo cách đếm của công cụ.
- **RSS:** tính resident mappings của process, bao cả shared pages.

PSS giúp khi có nhiều JVM dùng chung libs/file maps, nhưng nó **không** tương đương NMT committed, và không nên bỏ qua sai số/timestamp khi so với cgroup.

### 4.4. Lệnh read-only cho đúng PID

Trên host hoặc namespace có quyền, thay PID cho đúng tiến trình Java:

~~~bash
PID=12345
grep -E '^(Name|Pid|PPid|VmSize|VmPeak|VmRSS|VmHWM|RssAnon|RssFile|RssShmem|Threads):' \
  "/proc/$PID/status"
cat "/proc/$PID/smaps_rollup"
ps -p "$PID" -o pid,etime,rss,vsz,cmd
~~~

- /proc/PID/status cung cấp snapshot thô, gồm VmHWM (RSS high-water mark) nhưng HWM không cho biết **khi nào** đỉnh xảy ra.
- smaps_rollup cho Rss, Pss, shared/private dirty/clean và các counters liên quan nếu kernel hỗ trợ. Đọc rất thường xuyên có overhead.
- ps có đơn vị riêng cho rss/vsz (thường KiB), cần đọc man của OS/tool.
- Một số môi trường container cấm đọc /proc/ PID khác; không mở rộng quyền hoặc chạy công cụ trái chính sách để bỏ qua hạn chế.

Nếu Java process **đã chết** và PID được tái sử dụng, đọc /proc/PID hiện tại có thể là một process khác; phải xác nhận start time và process identity.

## 5. Memory cgroup: tại sao memory.current có thể khác RSS?

Trong cgroup v2, memory.current phản ánh memory charges của cgroup cùng descendants theo semantics kernel, có thể gồm:

- anonymous memory của các process thuộc cgroup;
- file/page cache được charge vào cgroup;
- kernel memory như slab/sock/pagetables/kstack theo kernel/controller;
- các process/sidecar khác nếu nằm trong cùng phạm vi cgroup.

Nó không phải “RAM riêng của Java heap” và cũng không nhất thiết trùng tổng RSS. Trên container orchestration, biểu đồ “container memory usage”, “working set”, “RSS” hoặc “usage_bytes” dùng định nghĩa và trừ một số cache khác nhau theo collector. **Ghi tên metric gốc**, không chỉ nhãn trên dashboard.

Các file read-only điển hình, khi **đã xác nhận đúng cgroup v2**:

~~~bash
cat /proc/self/cgroup
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.peak
cat /sys/fs/cgroup/memory.stat
cat /sys/fs/cgroup/memory.events
~~~

Trên host, /sys/fs/cgroup của shell có thể là cgroup **khác** với Java PID. Khi đọc từ trong container, cgroup namespace có thể khiến path biểu diễn khác host. Phải kiểm tra /proc/PID/cgroup, mount info và mapping Kubernetes/container ID; không dùng các con số cgroup **khác scope** để diễn giải Java process.

Đặc biệt:
- **memory.current:** usage tại thời điểm đọc, không phải process RSS.
- **memory.max:** hard limit (“max” nếu không áp giới hạn) của cgroup theo cấu hình; không phải -Xmx.
- **memory.peak:** đỉnh theo semantics kernel/FD; không có timestamp riêng để biết khi nào peak.
- **memory.stat anon, file, slab...:** phân tách một số khoản cgroup charge; tùy kernel có các counters khác nhau.
- **memory.events oom/oom_kill/max:** sự kiện pressure/kill; so delta và xác nhận cgroup/khung thời gian, không coi một counter tích lũy là bằng chứng vừa xảy ra OOM.

Nếu memory.current tăng trong khi RSS Java ổn định, có thể do page cache, sidecar, kernel charges hoặc process khác. Ngược lại RSS Java tăng nhưng cgroup usage ít đổi cũng có thể do reclaim/cache và các cơ chế khác; cần xem đúng metric và timestamp.

## 6. Native Memory Tracking (NMT) đo gì, không đo gì?

### 6.1. Bản chất NMT

**NMT là tính năng của HotSpot theo dõi vùng/cấp phát bộ nhớ do JVM quản lý nội bộ**, không phải một máy quét toàn bộ address space của process. Nó cho biết các hạng mục như:

- Java Heap;
- Class / Metadata / Compressed Class Space;
- Thread;
- Code;
- GC, Compiler, Internal;
- Symbol, Native Memory Tracking, Arena Chunk;
- Other và các categories bổ sung tùy JDK/collector.

Danh sách và cách phân loại có thể thay đổi theo phiên bản JDK. NMT có thể không theo dõi chính xác mọi allocation của JNI/native third-party libraries hoặc các thành phần runtime nằm ngoài cơ chế HotSpot tracking. Oracle cũng nêu rõ giới hạn với third-party native code và một số JDK class-library allocations. **Nếu NMT flat trong khi RSS tăng, điều đó không loại trừ native memory leak.**

### 6.2. NMT tắt theo mặc định và cần bật từ lúc khởi chạy

Ví dụ startup **cho môi trường có thể đánh giá overhead**:

~~~bash
java -XX:NativeMemoryTracking=summary -Xmx768m -jar app.jar
~~~

Hoặc chọn detail khi cần call-site evidence và có điều kiện:

~~~bash
java -XX:NativeMemoryTracking=detail -Xmx768m -jar app.jar
~~~

- **summary:** tổng hợp theo hạng mục; thường là điểm bắt đầu phù hợp nhất.
- **detail:** theo dõi chi tiết hơn, phục vụ truy nguồn cấp phát VM nhưng overhead cao hơn; phải đánh giá trên workload.
- **off:** mặc định trên nhiều HotSpot builds; không có NMT history để dựng lại sau sự cố.

NMT **không thể bật từ off thành summary/detail cho một process đang chạy chỉ bằng jcmd**. Có thể dừng NMT theo cơ chế hỗ trợ, nhưng không được giả định khởi động lại tracking trong process sau khi đã tắt. NMT có overhead CPU/memory; tài liệu Oracle nêu mức tham khảo khoảng **5–10% overhead hiệu năng** trong một số điều kiện, không phải SLA cố định.

### 6.3. Reserved và committed không bằng nhau

Một ví dụ NMT summary minh họa:

~~~text
Total: reserved=4500MB, committed=740MB
- Java Heap (reserved=2048MB, committed=512MB)
- Class     (reserved=1050MB, committed=45MB)
- Thread    (reserved=420MB,  committed=40MB)
- Code      (reserved=260MB,  committed=35MB)
- ...
~~~

Đây là **số tổng hợp giả định để minh họa**, không phải output đầy đủ của JDK cụ thể; các hạng mục rút gọn **không cộng ra Total** do không liệt kê toàn bộ. Một reserved=4.500 MB không có nghĩa process dùng 4.500 MB RAM; committed=740 MB cũng không bằng RSS=740 MB. NMT committed là commit theo mô hình VM, còn RSS phụ thuộc trang hiện resident và những cấp phát/mappings khác.

Cần đọc:
- Giá trị tuyệt đối của hạng mục;
- Delta committed so với **baseline cùng PID**;
- Delta reserved chỉ để hiểu address-space growth;
- Chênh lệch giữa các categories (Java Heap, Thread, Class, Code, GC, Other);
- Context của JVM flags, collector, JDK version, threads/classes và workload.

**Không lấy NMT total rồi cộng heap committed**: Java Heap đã được tính trong NMT total nếu report chứa category tương ứng.

### 6.4. Baseline/diff: so xu hướng thay vì hai ảnh chụp rời rạc

Khi NMT đã được bật từ startup:

~~~bash
PID=12345
jcmd "$PID" VM.native_memory summary scale=MB
jcmd "$PID" VM.native_memory baseline
# Tái hiện workload hoặc quan sát một khoảng được ghi rõ.
jcmd "$PID" VM.native_memory summary.diff scale=MB
~~~

Nếu bật detail từ startup và có lý do điều tra sâu:

~~~bash
jcmd "$PID" VM.native_memory detail.diff scale=MB
~~~

- Baseline đánh dấu tham chiếu **tại thời điểm chạy**, không tự bao gồm trạng thái trước lúc bạn bật NMT.
- summary.diff hiển thị delta theo category kể từ baseline; các allocations/frees có thể triệt tiêu nên snapshot không thay thế event history.
- Không so diff của hai JVM/PID khác nhau rồi gọi đó là leak của cùng process.
- NMT output có thể thay đổi do GC/heap expansion, JIT warm-up, classloading hoặc native allocator; cần phân biệt thay đổi dự kiến với tăng trưởng liên tục.
- Đảm bảo workload/cấu hình tương đương; baseline nên lấy sau warm-up nếu bạn muốn điều tra steady-state retention.

## 7. Direct ByteBuffer và BufferPoolMXBean

### 7.1. Direct buffer ở heap hay native?

ByteBuffer.allocateDirect(capacity) trả về một **Java object trên heap** mô tả buffer, nhưng vùng lưu dữ liệu chính thường nằm **ngoài Java heap**, thuộc memory do JVM/native allocator quản lý tùy implementation. Vì vậy heap used có thể chỉ tăng rất ít khi ứng dụng tạo nhiều direct buffers có tổng capacity lớn; process RSS hoặc cgroup memory vẫn tăng.

Đây là một cơ chế quan trọng trong NIO, network frameworks, file I/O và zero-copy-oriented paths. Nhưng:
- Không phải mọi native allocation đều là direct buffer.
- Không phải mọi ByteBuffer nằm ngoài heap: ByteBuffer.allocate(...) là heap buffer.
- MappedByteBuffer/file mapping là một loại mapping khác; không đồng nhất với direct pool.
- Direct buffer object có thể vẫn reachable vì cache/pool/reference; thu hồi native memory liên quan lifecycle của object và cơ chế cleanup/runtime, **không nhất thiết diễn ra ngay** khi application bỏ tham chiếu.

### 7.2. BufferPoolMXBean đưa ra ba metric khác nhau

Java cung cấp BufferPoolMXBean qua:

~~~java
ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)
~~~

Các pool thường thấy trên HotSpot là **direct**, **mapped** (và có thể thêm pool khác). Với mỗi pool:

- **getCount():** số buffers ước lượng thuộc pool;
- **getTotalCapacity():** tổng capacity logic ước lượng, đơn vị bytes;
- **getMemoryUsed():** ước lượng bộ nhớ JVM đang dùng cho pool, đơn vị bytes; có thể **trả -1** nếu không có ước lượng.

MemoryUsed và TotalCapacity **không bắt buộc bằng nhau** do alignment, allocator overhead và implementation. Không dùng capacity làm “RSS direct memory” tuyệt đối; không dùng count làm số allocation còn live trên mọi thư viện vì pooling/slicing và implementation details.

### 7.3. Direct pool không bằng mọi off-heap

Nhiều native allocations có thể đi qua JNI, malloc trong libraries, JIT/GC/internal JVM, compression, crypto/TLS, memory-mapped files hoặc SDK khác. BufferPoolMXBean không hứa đo mọi vùng đó. Ngược lại, một số allocations của direct ByteBuffer có thể xuất hiện trong NMT ở hạng mục như Other trên một bản HotSpot, nhưng **không được giả định category Other luôn bằng direct pool**; cần kiểm tra implementation/JDK, thời điểm đo và NMT diff.

Quan trọng nhất: nếu một direct buffer đã được phản ánh trong NMT committed hoặc process RSS, thì thêm direct pool number vào NMT/RSS sẽ **đếm trùng**. Hãy dùng direct pool như **bằng chứng về một loại allocation**, không phải một “dòng tiền mới” có thể cộng vào tổng.

### 7.4. MaxDirectMemorySize không phải trần toàn bộ native memory

Tùy HotSpot và JDK, -XX:MaxDirectMemorySize có thể hạn chế một số allocations qua cơ chế direct buffer tương ứng, nhưng **không giới hạn mọi off-heap/JNI/mmap/allocator**. Không coi -Xmx + MaxDirectMemorySize là tổng process max. Khi thay limit này, kiểm tra thư viện đang dùng allocations nào và behavior thực tế; thiếu direct memory có thể gây OutOfMemoryError ở Java ngay cả khi heap chưa đầy.

## 8. Mô hình các phép đo và bẫy cộng trùng

Giả sử bốn nguồn cùng lúc đưa:

~~~text
Process RSS             = 1,180 MiB
Java heap used          =   355 MiB
NMT total committed     =   860 MiB
Direct pool memoryUsed  =   218 MiB
~~~

**Không** tính 1.180 + 355 + 860 + 218 = 2.613 MiB. Con số đó vô nghĩa vì có nhiều phần chồng lấp.

Thay bằng bốn nhận định **tách biệt**:
1. OS đang ghi nhận process có 1.180 MiB resident mappings.
2. JVM báo 355 MiB used trong heap tại snapshot đó.
3. NMT báo 860 MiB committed trong các categories do HotSpot theo dõi, gồm cả heap committed.
4. BufferPoolMXBean báo 218 MiB ước lượng direct memory của pool (nếu implementation hỗ trợ).

Mỗi số phục vụ một câu hỏi:
- **Ứng dụng có đang tiến sát memory limit ở process/container không?** → RSS, cgroup usage, memory.max và xu hướng trước OOM.
- **Objects Java có bị giữ lại không?** → heap-after-GC, old generation, heap dump/retained set.
- **HotSpot subsystem nào lớn lên?** → NMT summary.diff, categories Thread/Class/GC/Code/Java Heap/Other.
- **Direct buffers có góp phần không?** → BufferPoolMXBean direct metrics, số connections/pools, reference retention và NMT category correlation nếu có.

Hãy tránh mô hình “unexplained native = RSS − heap used − NMT committed − direct”. Vì các đại lượng khác accounting, phép trừ có thể âm hoặc dương tùy page residency, shared mappings, kernel caches và NMT coverage; **phần dư không tự là native leak**.

## 9. Tình huống thực hành: process tăng 420 MiB nhưng heap used gần như đứng yên

Service xử lý nhiều kết nối NIO, giữ một số buffer pools để phục vụ network traffic. Hai snapshot được thu trên **cùng PID**, sau warm-up, cùng JDK, cùng cgroup và gần các mốc tải tương ứng. Mọi số bên dưới là **giả định** và đã chuẩn hóa sang MiB để luyện lập luận.

| Chỉ số | T0 | T1 sau 30 phút | Delta |
| --- | ---: | ---: | ---: |
| Process RSS | 760 | 1.180 | +420 |
| Heap used | 350 | 355 | +5 |
| Heap committed | 512 | 512 | 0 |
| Heap max (-Xmx) | 768 | 768 | 0 |
| NMT total committed | 680 | 860 | +180 |
| NMT category Other committed | 80 | 250 | +170 |
| Direct pool memoryUsed | 48 | 218 | +170 |
| Direct pool totalCapacity | 48 | 218 | +170 |
| Direct pool count | 120 | 540 | +420 |
| Cgroup memory.current | 980 | 1.420 | +440 |
| Cgroup memory.max | 1.536 | 1.536 | 0 |
| RPS trung bình | 800 | 800 | 0 |

Vì hai snapshot cách 30 phút, các delta không nói từng MiB đã cấp phát lúc nào. Process RSS tăng 420 MiB, còn NMT committed chỉ tăng 180 MiB; không phải số liệu “đánh nhau” vì NMT committed và RSS **khác phạm vi và semantics**.

### 9.1. Đọc bảng theo thứ tự đúng

**Quan sát 1 — RSS tăng và tiến gần giới hạn.** Process RSS tăng +420 MiB, container memory.current +440 MiB và chỉ còn 116 MiB trước memory.max trong số liệu T1 (1.536 − 1.420). Đây là rủi ro vận hành thực, nhưng memory.current không phải RSS và có thể chứa page cache/kernel/other-process charges.

**Quan sát 2 — heap used gần như không tăng.** Heap +5 MiB, heap committed không đổi. Không ủng hộ giả thuyết “toàn bộ +420 MiB đến từ Java objects đang chiếm heap used”, nhưng chưa thể nói heap retention **không** có vấn đề nếu hai snapshot không chuẩn hóa theo GC phase/live set.

**Quan sát 3 — NMT đang thấy một phần tăng trưởng.** Total committed +180 MiB, trong đó Other +170 MiB. Đây là tín hiệu cần drill-down: biết category Other tăng không tự chứng minh nó là direct buffers.

**Quan sát 4 — direct pool tăng tương quan.** Direct memoryUsed +170 MiB, capacity +170 MiB, count tăng. Điều này phù hợp giả thuyết **direct-buffer pool/retention tăng** và có thể giải thích **một phần** sự dịch chuyển NMT Other trên implementation này. Không được cộng +170 (direct) và +170 (Other) thành +340 MiB mà không chứng minh chúng độc lập.

**Quan sát 5 — còn khoảng chênh về cơ chế đo.** RSS +420, NMT committed +180. Không thể gọi ngay +240 MiB còn lại là “native leak không được NMT tracking”. Có thể là allocator arenas, resident transition của pages đã committed, file-backed mappings, JNI/native allocations hoặc noise do snapshots/lượt thu khác thời điểm. Cần smaps_rollup, /proc/PID/status, memory.stat và native evidence phù hợp.

### 9.2. Kết luận sơ bộ đúng mức

> Trong 30 phút, cùng JVM PID có RSS tăng +420 MiB, heap used gần như ổn định, NMT committed tăng +180 MiB (chủ yếu category Other +170 MiB) và direct buffer pool memoryUsed tăng +170 MiB. Có cơ sở điều tra **direct-buffer growth** là một phần nguyên nhân; chưa đủ dữ liệu để gọi leak hoặc quy toàn bộ RSS tăng cho direct buffers. Container memory.current đã gần memory.max; cần kiểm tra buffer ownership/lifecycle và các memory mappings khác trước khi tăng heap hoặc giảm memory limit.

Đây là kết luận có nguồn và giới hạn; tốt hơn câu “NMT thiếu 240 MiB nên JNI đang leak” hoặc “direct buffer đã dùng 218 MiB, cộng thêm vào RSS là 1.398 MiB”.

### 9.3. Vì sao tương quan chưa phải leak?

Pool có thể tăng lên theo concurrency hoặc high-water mark rồi ổn định; một hệ thống giữ buffer cache có giới hạn có thể chủ ý dùng memory để tránh allocations. Một số buffers có thể được giữ bởi connections đang hoạt động; buffer count tăng khi traffic mix/payload thay đổi dù RPS bằng nhau. Hỏi thêm:

- Số connection/HTTP2 streams, request size và in-flight messages có tăng không?
- Direct pool có **plateau** khi workload ổn định không, hay vẫn tăng không giới hạn?
- Sau khi kết nối/batch đóng và load giảm, buffers có được trả về pool hoặc cleanup theo lifecycle hợp lệ không?
- Có reference retention ở cache/pool/map/listener không? Có leak trong Netty/driver/native transport không?
- Có allocator chunk fragmentation hoặc memory không trả ngay cho OS dù buffers đã release không?
- Có đổi SDK/JDK/GC, pool config hoặc phiên bản thư viện không?

Không nên ép System.gc() để cố chứng minh direct buffers “phải giảm ngay”; GC/cleaner, pooling và native allocator release không đồng nhất, và ép GC có thể làm méo phép đo.

## 10. Bổ sung số liệu để phân xử phần RSS tăng

### 10.1. Nhìn /proc/PID/status và smaps_rollup trước/sau

Nếu T0 → T1:
- RssAnon tăng mạnh: nghĩ tới heap pages, direct/native malloc, thread stacks, anonymous mappings và các vùng khác; **không** kết luận ngay direct leak.
- RssFile tăng mạnh: nghĩ tới mapped files, shared libraries, page cache gắn process; kiểm tra smaps theo path và mapping.
- RssShmem tăng: xem shared memory/mmap mechanism tương ứng.
- PSS và Private_Dirty tăng: giúp hiểu phần resident thực của process và tính shared/private.
- VmSize tăng nhưng RSS không: có thể chỉ tăng virtual reservations, không phải áp lực RAM vật lý ngay.

Sử dụng đồng thời NMT diff để xem HotSpot categories nào đổi. Nếu NMT flat mà RssAnon tăng, ưu tiên kiểm tra third-party JNI/native malloc, allocator arenas và những resident transitions không được NMT phản ánh. **Không thay mọi giả thuyết bằng một phép trừ.**

### 10.2. Cgroup memory.stat bổ sung gì?

Nếu memory.current tăng +440 MiB, kiểm tra các key theo kernel cụ thể:
- anon tăng → có thể tương ứng user anonymous memory từ các process;
- file tăng → file/page cache/mapped file charges;
- slab, sock, kernel_stack, pagetables hoặc kernel thành phần khác tăng → kernel charges;
- các process cùng cgroup/sidecar cũng có thể sử dụng memory.

Một pod có Java RSS tương đối ổn định nhưng memory.current tăng do file cache/sidecar là chuyện có thể xảy ra. NMT không giúp đo page cache của toàn cgroup.

### 10.3. Áp lực bộ nhớ và OOMKill

Tại T1 memory.current=1.420 MiB, memory.max=1.536 MiB, headroom khoảng 116 MiB theo snapshot. Tuy nhiên headroom không phải lời hứa sẽ không OOM: memory có thể tăng đột ngột, charging/reclaim behavior và concurrent workloads thay đổi. Nếu đã có OOMKilled:
- đọc container last termination reason, đúng container ID;
- đọc cgroup memory.events oom_kill delta và kernel logs nếu còn;
- xác nhận memory usage/peak trước crash;
- không dùng PID mới hoặc cgroup sau restart làm snapshot thay cho process đã chết.

Heap dump hoặc NMT attach vào process đã bị SIGKILL không thể thực hiện sau đó; chuẩn bị telemetry **trước sự cố** là một phần của bài thực hành.

## 11. Quy trình đo lặp lại được: T0, T1, T2

### Bước 1 — Xác định đúng đối tượng và giới hạn

Ghi service, build, JDK vendor/version, PID + start time, container ID/pod UID, node, Xms/Xmx, MaxDirectMemorySize nếu dùng, NMT level, GC, thread count, direct-buffer/pool config, memory.max và cgroup path.

**Không bao giờ** ghép NMT của PID mới với RSS của PID cũ sau restart. Nếu có nhiều JVM cùng một pod, container memory.current không thể mặc nhiên gán hết cho một JVM.

### Bước 2 — Chọn điều kiện đo có thể so

T0 sau warm-up; T1 trong lúc memory tăng; T2 sau khi tải/hay batch kết thúc hoặc sau giai đoạn ổn định. Ghi:
- exact timestamp UTC;
- RPS, request mix, connection count, in-flight, payload sizes, batch;
- GC phase gần snapshot (heap used trước hay sau GC);
- deploy, traffic spike, autoscale và native library state.

Nếu RPS như nhau nhưng số kết nối mở tăng gấp ba, mẫu trực tiếp vẫn không hoàn toàn tương đương.

### Bước 3 — Chụp đồng thời bốn nhóm

1. JMX heap used/committed/max và GC metrics;
2. NMT summary/diff (nếu đã bật);
3. direct/mapped BufferPoolMXBean count/capacity/memoryUsed;
4. Process /proc/PID/{status,smaps_rollup}, cgroup memory.current/memory.stat/memory.events.

Đọc một chuỗi lệnh cần thời gian; ghi mỗi snapshot timestamp, không viết “đo đồng thời chính xác đến mili-giây” nếu thực tế thu lần lượt.

### Bước 4 — Tính delta **trong từng cột**

RSS_T1 − RSS_T0, HeapUsed_T1 − HeapUsed_T0, NMTCommitted_T1 − NMTCommitted_T0, DirectUsed_T1 − DirectUsed_T0, CgroupCurrent_T1 − CgroupCurrent_T0.

Sau đó mới xem **tương quan về thời gian** và sự phù hợp cơ chế, chứ không cộng các delta thành “total delta”.

### Bước 5 — Đặt giả thuyết và chỉ định nguồn bác bỏ

Ví dụ:
- Direct retention: direct pool tăng và number connections/buffers không được giải phóng sau load; bác bỏ nếu pool ổn định/giảm trong khi RSS vẫn tăng.
- Heap retention: post-GC old-gen trend tăng; bác bỏ nếu live-set ổn định qua các chu kỳ so sánh.
- Native leak ngoài NMT: RSS/RssAnon tăng và NMT/direct/heap ổn định; xác nhận bằng native allocator profiling, JNI ownership hoặc smaps.
- Page cache/cgroup growth: memory.stat file/slab tăng, process RSS không tăng tương ứng; xác nhận OS/controller evidence.
- Thread explosion: thread count và NMT Thread committed/virtual stack tăng; kiểm tra thread dumps và pool limits.

### Bước 6 — Thí nghiệm nhỏ, đo cả hệ thống

Nếu nghi direct buffers: đo trước/sau khi giới hạn connection pool, fixed buffer cache, giảm retained references hoặc đóng đúng lifecycle; bảo đảm throughput, latency và CPU/GC không regress. Nếu nghi native third-party: dùng tool có khả năng phân tích allocator đúng libc/library, trong staging trước khi áp production.

### Bước 7 — Báo cáo theo mức tin cậy

Phân biệt:
- **Observed:** metric nào tăng bao nhiêu, nguồn nào, window nào;
- **Hypothesis:** vùng hay allocator nào có khả năng gây tăng;
- **Falsifier:** đo gì sẽ bác bỏ hypothesis;
- **Decision:** observe, reproduce, limited rollout, rollback;
- **Limitations:** NMT disabled, thiếu T0, timestamps lệch, cgroup không cùng scope...

## 12. Lệnh thực tế: jcmd và JMX

### 12.1. JVM đang chạy và đã bật NMT từ startup

~~~bash
java -version
jcmd -l
PID=12345

jcmd "$PID" VM.command_line
jcmd "$PID" VM.flags
jcmd "$PID" GC.heap_info
jcmd "$PID" VM.native_memory summary scale=MB
jcmd "$PID" VM.native_memory baseline
# Sau một khoảng tải đã ghi rõ:
jcmd "$PID" VM.native_memory summary.diff scale=MB
~~~

Lưu ý:
- jcmd attach thường cần user/quyền phù hợp, JVM hỗ trợ và target PID nhìn thấy trong namespace.
- GC.heap_info cho thông tin heap theo JVM, nhưng nội dung khác nhau theo collector/version.
- NMT summary/diff chỉ hoạt động nếu đã bật NMT; khi disabled, không có dữ liệu đã bị mất trong quá khứ để khôi phục.
- Đặt baseline ở **trạng thái ổn định**, không so startup đang JIT/classload với steady state rồi gọi là leak.
- Không gọi GC.heap_dump, GC.class_histogram hoặc GC.run tùy tiện trên production. Heap dump có thể dừng ứng dụng, tiêu I/O/disk và chứa dữ liệu nhạy cảm; một số diagnostic operations thay đổi trạng thái/GC, làm méo phép so.

### 12.2. NMT chưa bật?

Nếu process vẫn chạy với NMT off, không thể đơn giản dùng jcmd để bật summary “từ giờ” mà không restart JVM theo cách được hỗ trợ. Vẫn còn:
- JMX heap, direct BufferPoolMXBean và thread/class metrics;
- /proc/PID/status, smaps_rollup và cgroup;
- application pool counters, GC logs/JFR nếu đã có;
- OS/native allocator diagnostics phù hợp quyền.

Lập kế hoạch enable NMT trong lần redeploy canary/staging để lấy T0/T1 có kiểm soát; không restart ồ ạt production chỉ để bổ sung một metric.

### 12.3. BufferPoolMXBean qua JMX

ObjectName của buffer pool trên JVM thường theo dạng:

~~~text
java.nio:type=BufferPool,name=direct
java.nio:type=BufferPool,name=mapped
~~~

Các attributes như Count, TotalCapacity, MemoryUsed có thể scrape qua JMX agent/metrics exporter đã phê duyệt. Hãy kiểm tra names/attributes thực có, không giả định mọi JVM đều có pool direct hay mapped với cùng semantics. Đặc biệt MemoryUsed có thể trả -1 và cần xử lý như “unknown”, không gán 0.

## 13. Java 17+ runnable: đọc heap và direct pool trên một JVM thật

Ví dụ **MemoryViewProbe.java** dùng API chuẩn java.management và java.nio. Nó không dùng internal sun.* APIs, không phụ thuộc thư viện ngoài. Chương trình tạo **8 MiB direct buffer** trong một lần chạy lab để minh họa sự khác nhau giữa heap array và direct-buffer storage, nhưng không gây OOME hay cố buộc GC dọn sạch bộ nhớ.

~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryUsage;
import java.nio.ByteBuffer;
import java.util.List;
import java.util.Locale;

public final class MemoryViewProbe {
    private static final int MIB = 1024 * 1024;

    private static long directUsed() {
        List<BufferPoolMXBean> pools =
                ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class);

        for (BufferPoolMXBean pool : pools) {
            if ("direct".equals(pool.getName())) {
                return pool.getMemoryUsed();
            }
        }
        return -1L;
    }

    private static String mib(long bytes) {
        if (bytes < 0) {
            return "unknown";
        }
        return String.format(Locale.ROOT, "%.1f", bytes / (double) MIB);
    }

    private static void snapshot(String label) {
        MemoryUsage heap =
                ManagementFactory.getMemoryMXBean().getHeapMemoryUsage();
        long direct = directUsed();

        System.out.printf(
                Locale.ROOT,
                "%s heap-used=%s MiB, heap-committed=%s MiB, "
                        + "direct-pool-used=%s MiB%n",
                label,
                mib(heap.getUsed()),
                mib(heap.getCommitted()),
                mib(direct));
    }

    public static void main(String[] args) {
        snapshot("before");

        byte[] heapArray = new byte[2 * MIB];
        ByteBuffer direct = ByteBuffer.allocateDirect(8 * MIB);
        heapArray[0] = 7;
        direct.put(0, (byte) 9);

        snapshot("after");
        System.out.println("heap-first=" + heapArray[0]);
        System.out.println("direct-first=" + direct.get(0));

        // Giữ hai đối tượng reachable tới đây.
        java.lang.ref.Reference.reachabilityFence(heapArray);
        java.lang.ref.Reference.reachabilityFence(direct);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac MemoryViewProbe.java
java MemoryViewProbe
~~~

**Hai dòng kiểm tra giá trị dữ liệu** luôn có cùng nội dung nếu chương trình chạy thành công:

~~~text
heap-first=7
direct-first=9
~~~

Chương trình còn in hai dòng snapshot before/after với các số cụ thể **phụ thuộc JDK, heap/GC, allocation alignment, background activity và implementation BufferPoolMXBean**, nên không bịa số stdout cố định cho các dòng đó. Trong một lần chạy HotSpot điển hình, direct-pool-used có thể tăng xấp xỉ 8 MiB; nhưng điều này không bảo đảm tuyệt đối vì metric là **ước lượng** và các allocations khác có thể cùng xảy ra.

Bài học từ code:
- byte[] là đối tượng/data trong heap, ByteBuffer object ở heap nhưng backing direct storage ở ngoài heap.
- Heap used có thể biến đổi không theo kích thước 2 MiB chính xác vì GC/allocator; không dùng snapshot một lần làm phép đo live set.
- Direct pool dùng API tiêu chuẩn, nhưng **không báo RSS** và không bắt mọi JNI allocations.
- reachabilityFence tránh compiler coi hai tham chiếu đã không còn cần trước điểm cuối minh họa; nó **không** ép giải phóng bộ nhớ.

## 14. Java 17+ runnable: tính delta mà không cộng trùng

Ví dụ thứ hai xử lý **bảng giả định ở mục 9**, xuất ra kết quả **hoàn toàn xác định**. Nó không cần truy cập jcmd hoặc /proc, thích hợp để kiểm tra cách ghi báo cáo và tránh suy luận “cộng các lớp” sai.

Tạo file **MemoryDeltaCase.java**:

~~~java
public final class MemoryDeltaCase {
    record Snapshot(
            long rssMiB,
            long heapUsedMiB,
            long heapCommittedMiB,
            long nmtCommittedMiB,
            long directUsedMiB,
            long cgroupCurrentMiB) {
    }

    public static void main(String[] args) {
        Snapshot t0 = new Snapshot(760, 350, 512, 680, 48, 980);
        Snapshot t1 = new Snapshot(1180, 355, 512, 860, 218, 1420);

        System.out.println("RSS delta MiB="
                + (t1.rssMiB() - t0.rssMiB()));
        System.out.println("Heap used delta MiB="
                + (t1.heapUsedMiB() - t0.heapUsedMiB()));
        System.out.println("Heap committed delta MiB="
                + (t1.heapCommittedMiB() - t0.heapCommittedMiB()));
        System.out.println("NMT committed delta MiB="
                + (t1.nmtCommittedMiB() - t0.nmtCommittedMiB()));
        System.out.println("Direct pool delta MiB="
                + (t1.directUsedMiB() - t0.directUsedMiB()));
        System.out.println("Cgroup current delta MiB="
                + (t1.cgroupCurrentMiB() - t0.cgroupCurrentMiB()));
        System.out.println("Do not sum overlapping memory views.");
    }
}
~~~

Chạy trên JDK 17+:

~~~bash
javac MemoryDeltaCase.java
java MemoryDeltaCase
~~~

Stdout **chính xác**:

~~~text
RSS delta MiB=420
Heap used delta MiB=5
Heap committed delta MiB=0
NMT committed delta MiB=180
Direct pool delta MiB=170
Cgroup current delta MiB=440
Do not sum overlapping memory views.
~~~

**Quan trọng:** Các delta không phải từng khoản độc lập để cộng. Ví dụ NMT +180 MiB có thể đã bao gồm phần direct +170 MiB trên implementation cụ thể; việc direct và NMT tăng gần nhau là tín hiệu **cần kiểm tra bằng chứng**, không chứng minh tương đương tuyệt đối.

## 15. Dùng NMT đúng cách khi Direct pool tăng

Giả sử NMT summary.diff:

~~~text
Total: committed=860MB +180MB
- Java Heap (committed=512MB)
- Other     (committed=250MB +170MB)
- ...
~~~

Đây là **output giả lập rút gọn** để minh họa số delta; thiếu các hạng mục còn lại và không đại diện chính xác dòng chữ của mọi JDK.

Quy trình:
1. Xác minh NMT bật từ T0; output là **summary.diff so cùng baseline**, không phải hai process khác nhau.
2. Chụp direct pool memoryUsed/count/totalCapacity **cùng cửa sổ**.
3. Nếu Other tăng +170 và Direct tăng +170, ghi giả thuyết “có thể là direct backing memory được phân loại ở Other”.
4. Chạy thử có kiểm soát: giữ workload, giảm/đóng buffer holders đúng lifecycle và xem **cả** direct pool, Other, RSS thay đổi thế nào.
5. Nếu direct pool giảm nhưng NMT Other không giảm, xem allocator retention, category mapping, sampling time và allocations khác.
6. Nếu NMT Other giảm nhưng RSS vẫn cao, có thể physical pages chưa trả về OS, file mappings tăng hoặc có nguồn ngoài NMT.
7. Nếu both flat mà RSS tăng, điều tra /proc/smaps và native third-party.

**Không tự tuyên bố NMT Other = ByteBuffer.allocateDirect** hoặc NMT total = heap + direct. NMT categories và đối tượng được tính có thay đổi giữa JDK, thư viện, allocator và đường cấp phát.

## 16. Bộ bằng chứng tối thiểu cho một incident

| Nguồn | Mốc cần thu | Dùng để | Cảnh báo quan trọng |
| --- | --- | --- | --- |
| PID/start time/build | T0, T1, T2 | Đảm bảo cùng JVM | Restart làm số liệu không còn so được |
| JMX heap used/committed/max | T0, T1, T2 cùng GC context | Heap usage/commit trend | Used không tự là live retained set |
| GC logs/after-GC occupancy | Liên tục | Retention vs allocation pressure | GC/collector phase khác nhau |
| NMT summary/diff | T0 baseline, T1/T2 | JVM internal categories | Off từ startup thì không khôi phục được |
| BufferPoolMXBean direct/mapped | T0, T1, T2 | Buffer count, capacity, usage | Ước lượng, có thể -1, không phải mọi off-heap |
| /proc/PID/status | T0, T1, T2 | RSS, RssAnon/RssFile/RssShmem, threads | Snapshot, process identity, accuracy |
| /proc/PID/smaps_rollup | Theo trigger | PSS, private/shared/mappings | Có overhead/quyền; không nên đọc liên tục |
| cgroup memory.current/stat/events | T0, T1, T2 | Container charges/limits/cache/pressure | Scope có thể gồm sidecar/other processes |
| Workload metrics | Liên tục | RPS, bytes, connections, queue/batches | Không cùng tải thì không kết luận leak vội |
| JVM flags, pool configs | Mỗi deploy | Xmx, NMT, direct size/pooling | Thay cấu hình làm baseline mất giá trị |

**Lưu dữ liệu theo timestamp UTC** và nhãn environment, service, pod/container ID, host node và PID. Không thu snapshots “trong 5 phút” rồi khẳng định chúng cùng một thời điểm; chênh thời gian có thể quan trọng khi GC và buffer recycling xảy ra nhanh.

## 17. Phân loại các mẫu tăng trưởng thường gặp

### 17.1. RSS tăng, heap used tăng, after-GC baseline tăng

Giả thuyết ưu tiên: Java object retention hoặc tăng live data set. Kiểm tra old-gen occupancy, dominator tree, static maps/caches, request/context leaks, classloader retention và workload. Nhưng đừng bỏ native area: cùng lúc JVM có thể mở rộng heap **và** direct buffers.

**Phản chứng:** heap sau GC ổn định qua cùng workload trong nhiều chu kỳ, còn RSS tăng chủ yếu ở RssAnon ngoài các vùng heap theo smaps; cần chuyển hướng điều tra.

### 17.2. RSS tăng, heap ổn định, direct pool và NMT Other tăng cùng nhịp

Giả thuyết ưu tiên: direct-buffer growth hoặc allocator behavior liên quan. Xem Netty/NIO/JDBC/network caches, byte buffer lifetime, connection count, in-flight requests, pooled chunk retention. Đừng gọi leak nếu tăng đến mức giới hạn rồi plateau hợp lý và giảm khi tải giảm.

**Phản chứng:** đóng connections/release pool trong lab làm direct memoryUsed giảm rõ, nhưng RSS vẫn tăng theo một native library khác; phải thu native allocator evidence.

### 17.3. RSS tăng, NMT Thread tăng, thread count tăng

Giả thuyết: unbounded thread creation hoặc thread pool cấu hình sai. Mỗi thread thường có native stack reservation/commit và runtime structures, nhưng Thread **reserved** không bằng stack resident. Xem /proc/PID/task count, Java thread dump, pool sizes, virtual threads vs platform threads, NMT Thread committed, RssAnon và container limit.

**Không** tính Thread reserved của 1.000 threads như RAM đã dùng vật lý. Virtual threads có cơ chế quản lý stack khác platform threads; không quy tất cả cho 1 MB OS stack/thread.

### 17.4. RSS tăng, NMT Class/Metaspace tăng và loaded classes tăng

Giả thuyết: classloader leak, dynamic proxy/generation, repeated redeploy-in-process, script/bytecode generation hoặc legitimate class growth. Kiểm tra loaded/unloaded class counters, classloader references, metaspace committed/used và JDK class metadata.

**Đừng** coi Class reserved lớn là leak nếu committed ổn định; compressed class space thường reserve address space lớn.

### 17.5. RSS tăng nhưng NMT/direct/heap tương đối phẳng

Điều tra:
- malloc/JNI/agent/native codec/crypto/compression allocations ngoài NMT;
- native allocator fragmentation/arenas, bộ nhớ không trả OS;
- anonymous/file mappings hoặc page residency;
- process khác trong cgroup, kernel/page cache nếu nhìn cgroup usage;
- metric mismatch hoặc snapshot không tương đương.

**NMT flat không phủ định native leak**, đặc biệt ở thư viện bên thứ ba. Dùng native memory profiler phù hợp, cùng thời gian, chứ không kết luận bằng phép trừ tự chế.

### 17.6. Cgroup current tăng nhưng Java RSS ổn định

Ưu tiên memory.stat: file/page cache, slab/sock, các processes/sidecars khác, OOM group scope, filesystem activity. Kiểm tra pod-level/container-level labels và memory working-set metric definitions. **Không** tăng heap hay giảm direct allocation nếu dữ liệu cho thấy phần tăng không thuộc Java PID.

### 17.7. VmSize/NMT reserved tăng mạnh nhưng RSS/committed không tăng

Đây có thể là virtual address reservation, stack reserve, class space hoặc mapping. Trừ khi có address-space exhaustion/commit failure, virtual reserved lớn tự nó không phải bằng chứng physical memory pressure. Trên 32-bit hoặc khi giới hạn VA đặc biệt, reservation có thể gây vấn đề khác; bài này tập trung Java 17+ 64-bit phổ biến.

## 18. Direct memory được giải phóng khi nào?

Điểm khó thực tế: một Java direct buffer có **wrapper object** trên heap, trong khi backing storage có vòng đời native. Khi wrapper không còn reachable, cơ chế cleanup/GC có thể thu hồi theo implementation; nhưng:
- thời điểm không nhất thiết ngay lập tức;
- pool/caches có thể giữ references có chủ ý;
- views/slices/duplicates có thể còn liên kết tới backing storage;
- native libraries có thể dùng cơ chế sở hữu/release riêng;
- allocator có thể giữ arena/chunks để tái sử dụng ngay cả sau free.

Đừng đánh giá leak từ một snapshot “sau khi method return”. Đặt **điểm đo T2 sau khi workload/connection lifecycle hoàn tất**, có thời gian ổn định, rồi xem buffer metrics và OS/RSS trajectories. Không dùng System.gc() làm thủ tục chuẩn để “ép direct memory về 0”; nó không bảo đảm native allocator trả pages về OS và gây méo benchmark.

Với framework có reference-counted buffers (ví dụ một số network libraries), phải tuân thủ API release/retain thực tế và instrument leak detector của thư viện theo chính sách. Một ByteBuffer.allocateDirect tiêu chuẩn không có giao thức release giống mọi framework.

## 19. Vì sao NMT committed tăng ít hơn RSS?

Đừng xem chênh lệch như một bucket bí mật. Các nguồn sai khác gồm:

1. **Coverage:** NMT không theo dõi đầy đủ native allocations của thư viện ngoài HotSpot.
2. **Resident vs committed:** physical pages có thể bắt đầu được touch trong vùng đã committed mà NMT delta committed không đổi.
3. **Shared/file-backed mappings:** RSS có file-backed pages chưa tương ứng theo cách NMT ghi.
4. **Allocator accounting:** malloc arenas/retained pages và khác biệt giữa alloc/free với RSS returned-to-OS.
5. **Time skew:** NMT, JMX, /proc và cgroup đọc tại những mốc hơi khác.
6. **Different scope:** cgroup current gồm nhiều processes/kernel/cache; NMT chỉ JVM target.
7. **Unit/rounding:** KB/MB, MiB và dashboard aggregation.
8. **Collector/JDK behavior:** heap uncommit, THP, page touching, GC resizing.
9. **Snapshots thiếu completeness:** partial files, permission, process restart, metrics scrape gaps.

Để quyết định, xem **xu hướng tương quan cùng thời gian và tính phù hợp cơ chế**, không theo một phương trình trừ tổng.

## 20. Phòng OOMKilled: ngân sách memory cho Java container

Một ngân sách thực hành gồm:
- heap max theo -Xmx hoặc ergonomic sizing;
- metaspace/class metadata và code cache;
- JIT/GC structures;
- platform thread stacks;
- direct buffers và native allocator;
- JNI/agents/third-party libraries;
- mappings/page cache/kernel charges;
- peak workload/payload, spikes và safety headroom.

Không có công thức “-Xmx bằng 80% memory limit” đúng cho mọi service. Ứng dụng dùng NIO/direct pools lớn cần headroom khác ứng dụng compute-bound không dùng native libraries. Hãy đo ở **peak representative load**, không chỉ idle startup.

Ví dụ: memory.max=1.536 MiB, Xmx=768 MiB. Heap max không bảo đảm còn 768 MiB dành cho native. Nếu direct pool + thread stacks + filesystem cache + kernel charges tăng nhanh, cgroup vẫn có thể đạt memory.max. Để ngăn OOM, có thể cần giới hạn pool, giảm retained buffers, điều chỉnh connection concurrency, workload/caches hoặc tăng resource limit sau capacity assessment — **không tự tăng Xmx**.

Hành động kiểm soát:
- alerts theo cgroup current / memory.max, RSS, direct pool, heap post-GC, NMT diff;
- xác nhận cgroup scope và restart metadata;
- giới hạn concurrency/queue/buffer ownership;
- chọn canary rollout, đo p99/throughput/GC/CPU và có rollback.

## 21. Khi nào cần heap dump, khi nào cần native tooling?

| Câu hỏi | Công cụ phù hợp | Rủi ro/giới hạn |
| --- | --- | --- |
| Objects Java nào còn reachable? | Heap dump + dominator tree, JFR object allocation/old object (nếu bật) | Pause/disk/PII, heap dump không đo native malloc |
| HotSpot subsystem nào tăng? | NMT summary.diff/detail.diff | Phải bật trước startup; không bao trọn third-party |
| Direct pool đang giữ bao nhiêu? | BufferPoolMXBean metrics + framework pool instrumentation | Ước lượng, không bao trọn off-heap |
| Cấp phát JNI/native ngoài NMT nào tăng? | Native allocator profiler, malloc/eBPF/traces trong môi trường có phép | Overhead/quyền/phạm vi khó; dữ liệu nhạy cảm |
| Process resident pages thuộc mappings nào? | /proc/PID/smaps_rollup, smaps, pmap | Snapshot, kernel accounting, shared pages |
| Container charge đến từ đâu? | cgroup memory.current/stat/events, runtime metrics | Scope gồm nhiều processes/kernel |
| Có OOM kill? | Kernel logs + cgroup oom_kill delta + container termination reason | Metrics sau restart có thể mất chứng cứ |
| Code path tạo direct buffers? | Application allocation tracing, JFR/native instrument theo API/thư viện | Sampling bias, context khớp request |

**Không lấy heap dump để giải thích trực tiếp toàn bộ RSS**. Nó hữu ích khi nghi Java object retention hoặc wrapper references giữ backing memory, nhưng không đo mọi native allocations. Với off-heap library không hiển thị trong heap, cần native/OS evidence.

## 22. Những quyết định sai và cách sửa

### Sai lầm 1 — “Heap used 350 MiB, RSS 1.180 MiB, vậy leak native 830 MiB”

Phép trừ không đủ: RSS gồm pages của heap committed/resident, mappings, shared pages; heap used không phải resident heap size; native areas có thể đã tồn tại ổn định. Muốn kết luận leak cần **tăng trưởng theo thời gian** và chứng minh không tương xứng với workload hoặc không được release hợp lệ.

### Sai lầm 2 — “NMT reserved 4 GiB, container chỉ 1.5 GiB nên chắc chắn OOM”

Reserved virtual address space khác committed/resident physical memory. Kiểm tra memory.current/RSS/NMT committed và limit; reserved lớn một mình không đủ.

### Sai lầm 3 — “NMT committed 860 + direct 218 = 1.078 MiB native”

NMT total đã gồm Java Heap; direct bytes có thể được NMT theo dõi trong một category; total và direct không độc lập. Cần so categories và pool, **không cộng**.

### Sai lầm 4 — “NMT flat nên Java không làm RSS tăng”

NMT có giới hạn coverage, đặc biệt JNI/native third-party; cũng có committed-vs-resident differences. Kiểm tra OS mappings và native allocator evidence.

### Sai lầm 5 — “Direct pool count tăng thì chắc chắn leak”

Pool có thể tăng tới watermark hợp lệ khi concurrency/payload tăng; vẫn cần kiểm tra plateau, owner references và behavior sau load/connection closure. Count/capacity/memoryUsed cùng timeline mạnh hơn một count đơn lẻ.

### Sai lầm 6 — “GC vừa chạy, direct memory phải về 0”

Direct buffers có lifecycle native/cleaner và pooling; GC không hứa giải phóng mọi off-heap ngay. Allocation đã free cũng có thể chưa trả resident pages cho OS.

### Sai lầm 7 — “Container memory.current chính là Java RSS”

Cgroup có file cache/kernel charges và có thể chứa sidecar/process khác. Đọc memory.stat, đúng cgroup scope và metrics definition.

### Sai lầm 8 — “Tăng Xmx để chữa OOMKilled”

Nếu kernel kill vì tổng cgroup usage vượt limit, tăng heap max khi limit không đổi có thể **giảm native headroom**. Phải xác định nguồn memory growth trước.

### Sai lầm 9 — “Một snapshot là đủ”

Các snapshot trước/sau GC hoặc sau restart không so trực tiếp. Phải ghi cùng PID, time window, workload, unit và GC state; ưu tiên time series.

### Sai lầm 10 — “Cứ bật detail NMT và heap dump trên mọi production”

NMT và heap dumps có overhead/ảnh hưởng disk/latency, đặc biệt lúc memory pressure. Dùng canary/staging hoặc kỹ thuật ít xâm lấn, có quyền, giới hạn tần suất, retention và kế hoạch rollback.

## 23. Mẫu phiếu điều tra có thể audit

~~~text
# Java memory growth comparison

Service / build / JDK vendor+version / collector:
PID + process start time:
Pod UID / container ID / node / cgroup path:
Xms / Xmx / direct memory flags / NMT level:
Incident UTC window:
Workload: RPS, payload, in-flight, connections, batches:
GC phase at measurement (before/after GC):

T0 UTC:
- Process VmRSS / RssAnon / RssFile / RssShmem:
- PSS / smaps private/shared breakdown:
- Heap used / committed / max:
- NMT total reserved / committed:
- NMT category breakdown:
- Direct pool count / capacity / memoryUsed:
- Mapped pool count / capacity / memoryUsed:
- Cgroup current / max / stat anon-file-slab:

T1 UTC (same PID? same workload?):
- All the same measurements
- Each metric delta within its own definition

T2 UTC (post-workload or stabilizing period):
- Same metrics and whether trends plateau/recover

OS/runtime:
- memory.events oom/oom_kill deltas:
- Container termination reason/restart metadata:
- GC logs, after-GC live-set, thread/class counts:

Observed:
Hypothesis A / supporting evidence / falsifier:
Hypothesis B / supporting evidence / falsifier:
Known blind spots (NMT off, -1 pool metric, missing T0...):
Experiment / guardrails / rollback:
Conclusion with confidence level:
~~~

Bảng này dùng để ghi chứng cứ **không cộng trùng** và tách rõ trực tiếp quan sát được khỏi giả thuyết. Khi thu snapshots, giữ cả output thô (không chỉ copy một con số) để người khác kiểm tra category, units và cách công cụ báo cáo.

## 24. Checklist hoàn thành bài thực hành

- [ ] Tôi xác nhận đúng JVM PID/start time, container/cgroup scope, JDK version, GC và workload.
- [ ] Tôi hiểu heap used, committed, max và vì sao heap used không hoàn toàn là live set.
- [ ] Tôi hiểu RSS khác virtual memory size, PSS và cgroup memory.current.
- [ ] Tôi không đồng nhất NMT total committed với RSS hoặc với “native ngoài heap”.
- [ ] Tôi phân biệt NMT reserved (virtual) và committed, không dùng reserved làm physical usage.
- [ ] Tôi biết NMT cần bật trước startup, level summary/detail và baseline/diff trên cùng JVM.
- [ ] Tôi biết NMT không bao trọn JNI/third-party native allocations hoặc mọi process mappings.
- [ ] Tôi dùng BufferPoolMXBean để đọc direct/mapped pool count, totalCapacity và memoryUsed.
- [ ] Tôi biết memoryUsed có thể -1 và capacity không tự là actual RSS.
- [ ] Tôi **không cộng** heap, NMT total, direct pool và RSS như các khoản độc lập.
- [ ] Tôi kiểm tra T0/T1/T2 cùng thời gian/workload và ghi GC state để so meaningful.
- [ ] Tôi tính delta riêng theo mỗi metric, không gọi phần dư RSS−NMT là leak không rõ.
- [ ] Tôi kiểm tra RssAnon/RssFile/RssShmem, smaps_rollup/PSS khi RSS thay đổi.
- [ ] Tôi kiểm tra memory.stat anon/file/slab và process khác khi cgroup current tăng.
- [ ] Tôi xem thread/class/code/GC/Other categories nếu NMT committed tăng.
- [ ] Tôi kiểm tra pool/connection/buffer lifecycle trước khi gọi direct growth là leak.
- [ ] Tôi không tăng Xmx hoặc MaxDirectMemorySize mù quáng khi container gần memory.max.
- [ ] Tôi đánh giá overhead của diagnostic tooling và bảo vệ dữ liệu trong logs/dumps.
- [ ] Tôi có hypothesis, falsifier, phép thử giới hạn và metrics xác nhận sau thay đổi.
- [ ] Tôi ghi “chưa đủ dữ liệu” khi chỉ có một snapshot hoặc NMT disabled.

## 25. Kết luận

**Process RSS, Java heap, NMT và direct buffer không phải bốn phép đo cùng đơn vị của bốn khoản độc lập.** Mỗi nguồn nhìn một lớp và một semantics khác:

- Heap giúp điều tra Java objects/GC và giới hạn Java heap.
- NMT giúp nhận diện phần tăng theo các hạng mục nội bộ HotSpot với reserved/committed/baseline/diff.
- BufferPoolMXBean cho thấy direct/mapped buffer pool usage theo API JVM, nhưng không phải toàn bộ off-heap.
- Linux /proc và cgroup giúp thấy resident pages, memory charges, shared/file mappings và rủi ro chạm giới hạn thực.

Trong tình huống RSS +420 MiB, heap used +5 MiB, NMT committed +180 MiB và direct pool +170 MiB, kết luận đúng là **direct buffer growth đáng điều tra**, không phải “đã xác nhận leak 170 MiB” và càng không phải “NMT thiếu 240 MiB là native leak”. Cần ghép cùng PID, timestamp, workload, NMT categories, OS memory mappings, buffer lifetime và số liệu sau khi workload giảm.

Quy trình sử dụng được trong production:

**Ghi định nghĩa metric → chụp T0/T1/T2 cùng JVM → so delta riêng từng nguồn → kiểm tra category/mapping/cgroup scope → đặt giả thuyết và phản chứng → kiểm thử nhỏ → xác nhận RSS, memory.current, GC, direct pool và SLO cùng ổn định.**

### Tài liệu tham khảo chính thức

- Oracle JDK 21 — Native Memory Tracking: https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html
- Oracle JDK 21 — jcmd (VM.native_memory, GC.heap_info): https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Oracle JDK 21 — BufferPoolMXBean API: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/BufferPoolMXBean.html
- Oracle JDK 21 — ManagementFactory / MXBeans: https://docs.oracle.com/en/java/javase/21/docs/api/java.management/java/lang/management/ManagementFactory.html
- Oracle JDK 21 — Diagnostic Tools and NMT categories: https://docs.oracle.com/en/java/javase/21/troubleshoot/diagnostic-tools.html
- Linux kernel — /proc filesystem, status/smaps/smaps_rollup: https://www.kernel.org/doc/html/latest/filesystems/proc.html
- Linux kernel — Control Group v2 memory.current/stat/max/events: https://docs.kernel.org/admin-guide/cgroup-v2.html
