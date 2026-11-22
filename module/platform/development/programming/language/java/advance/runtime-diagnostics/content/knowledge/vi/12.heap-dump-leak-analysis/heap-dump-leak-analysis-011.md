# 12.11 Phân loại OutOfMemoryError theo thông báo và vùng tài nguyên thực sự cạn

## Mục tiêu và nguyên tắc chẩn đoán

Cùng là hiện tượng “hết bộ nhớ”, nhưng ứng dụng Java có thể thất bại ở nhiều tài nguyên khác nhau: Java heap, vùng metadata của class, direct buffer, bộ nhớ native, giới hạn số thread/process, không gian địa chỉ hoặc giới hạn bộ nhớ container. Chỉ khi xác định đúng **thông báo lỗi**, **nguồn tài nguyên bị cạn** và **bằng chứng ở thời điểm xảy ra sự cố** mới có thể chọn cách xử lý phù hợp.

Sau bài này, bạn có thể:

1. Phân loại các thông báo java.lang.OutOfMemoryError thường gặp trên HotSpot/OpenJDK.
2. Phân biệt lỗi OOME được JVM ném ra, JVM chết vì lỗi cấp phát native và tiến trình bị hệ điều hành/container giết.
3. Liên kết thông báo với vùng tài nguyên liên quan, từ đó chọn metrics, dump, log và lệnh kiểm tra đúng.
4. Phân biệt **triệu chứng cạn tài nguyên** với **nguyên nhân gốc** như memory leak, retention hợp lệ, allocation burst, tăng classloader hay giới hạn thread.
5. Tránh xử lý sai kiểu “tăng -Xmx cho mọi OOME”, và lập hồ sơ chứng cứ để kiểm tra giả thuyết.

**Phạm vi:** Java 17+ trên HotSpot/OpenJDK; nhiều ví dụ áp dụng JDK 21. Thông điệp cụ thể có thể khác giữa JVM vendor, JDK version, collector, OS và API dẫn tới lỗi. Các chuỗi dưới đây là dấu hiệu chẩn đoán, **không phải giao thức ổn định dùng để xác định nguyên nhân cuối cùng**.

## 1. Hiểu OutOfMemoryError đúng bản chất

java.lang.OutOfMemoryError kế thừa VirtualMachineError và là một Error: JVM hoặc thư viện có thể ném ra khi không thể đáp ứng yêu cầu cấp phát tài nguyên liên quan đến bộ nhớ. Tên “OutOfMemory” **không đồng nghĩa** với “Java heap đã đầy”, và OOME **không đồng nghĩa** với “memory leak”.

Ba lớp cần phân biệt:

| Lớp | Tình huống | Dấu hiệu điển hình | Hướng bằng chứng |
| --- | --- | --- | --- |
| **Java-level OOME** | JVM/thư viện tạo java.lang.OutOfMemoryError | Stack trace hoặc log có tên class và thông báo | Message, call stack, GC/JFR/heap/native/thread metrics |
| **JVM fatal native allocation** | JVM không cấp phát được bộ nhớ native và dừng với fatal error | Thông báo “There is insufficient memory for the Java Runtime Environment to continue”, file hs_err_pid..., exit bất thường | Error log JVM, OS memory, native allocations, limits |
| **OS/container kill** | Kernel/cgroup hoặc orchestrator chấm dứt process do áp lực hay giới hạn tài nguyên | SIGKILL, sự kiện OOMKilled, cgroup memory.events/oom_kill; có thể không có stack trace Java | Kernel/cgroup/Kubernetes events, memory.current, RSS/working set |

Exit code 137 trên Linux/container thường có nghĩa process bị SIGKILL (128 + 9), **không tự chứng minh** OOMKilled: phải tìm lý do trong orchestrator, cgroup events hoặc kernel logs. Tương tự, process không sinh heap dump sau khi chết không chứng minh rằng JVM không gặp vấn đề bộ nhớ: bị kill từ OS có thể xảy ra trước khi Java kịp ném OOME.

**Vùng xảy ra thất bại ≠ nguyên nhân gốc.** Chẳng hạn, lỗi Java heap space cho biết yêu cầu cấp phát trên heap thất bại; nguyên nhân có thể là một collection giữ reference quá lâu, cache được thiết kế không giới hạn, tải hợp lệ lớn hơn dung lượng heap hoặc một allocation đột biến. Stack trace tại điểm ném lỗi thường chỉ tới **nơi cấp phát cuối cùng thất bại**, không chắc là nơi tạo ra object giữ bộ nhớ.

## 2. Bản đồ thông báo → vùng tài nguyên → dấu hiệu cần xác minh

| Thông báo / sự kiện thường thấy | Tài nguyên liên quan | Hỏi thêm trước khi kết luận |
| --- | --- | --- |
| OutOfMemoryError: **Java heap space** | Java heap (object/array allocation không thành công) | Heap used/max, GC trước lỗi, post-GC live set, retained objects, allocation rate, -Xmx |
| OutOfMemoryError: **GC overhead limit exceeded** | Heap với GC tốn công nhưng thu hồi quá ít theo chính sách của JVM/collector | Tổng thời gian GC, mức thu hồi, allocation rate, collector, chính sách giới hạn có bật không |
| OutOfMemoryError: **Requested array size exceeds VM limit** | Giới hạn kích thước array/object mà VM cho phép, có thể trước khi thử cấp phát heap | Giá trị kích thước array, tính toán kích thước, dữ liệu đầu vào, integer arithmetic |
| OutOfMemoryError: **Metaspace** | Metadata class trong native memory/giới hạn metaspace | Class count, classloaders, class unloading, Metaspace used/committed/max, -XX:MaxMetaspaceSize |
| OutOfMemoryError: **Compressed class space** | Vùng chứa metadata Klass khi sử dụng compressed class pointers | Compressed class space usage/limit, classloaders/classes, cấu hình CCS |
| OutOfMemoryError: **Direct buffer memory** hoặc **Cannot reserve ... bytes of direct buffer memory** | Giới hạn/reservation của direct ByteBuffer, liên quan native memory | BufferPoolMXBean direct, -XX:MaxDirectMemorySize, buffer lifecycle, allocation hotspots |
| OutOfMemoryError: **Map failed** hoặc thông báo mapping tương tự | Memory-mapped file/khả năng mmap, vùng địa chỉ, OS limit và tài nguyên mapping | FileChannel.map, kích thước mapping, address space, mappings, OS/cgroup constraints |
| OutOfMemoryError: **unable to create native thread** | Tạo thread OS: native stack, PID/thread limit hoặc OS/native memory | Số thread, pids.current/max, ulimit, RSS/native, chính sách thread pool |
| **Out of swap space?** hoặc thông báo native allocation cụ thể | Native/OS virtual memory hoặc swap (phụ thuộc JVM/OS) | JVM fatal logs, commit limit, swap, memory maps, limits; xác minh đó là OOME hay VM fatal error |
| **Native memory allocation (malloc/mmap) failed** trong hs_err | Bộ nhớ native mà JVM không thể cấp phát | hs_err, OS/cgroup memory, NMT khi đã bật, thread count, JVM/native library usage |
| **OOMKilled**, cgroup oom_kill, Kubernetes reason OOMKilled | Giới hạn bộ nhớ ở cấp container/OS, không nhất thiết heap | Container memory limit, peak working set/RSS, cgroup memory.events, native/off-heap |
| **CodeCache is full**, compiler disabled... | Code cache có thể đầy | Đây thường là cảnh báo/sự cố biên dịch JIT, **không tự động là OutOfMemoryError**; đọc thông điệp thực tế |

Đọc nguyên văn **exception class + message + stack trace + timestamp**. Đừng gom tất cả thành nhãn “heap OOM” trong dashboard. Một số lỗi có message khác nhau giữa JDK/vendor, nên trường hợp không khớp bảng cần xếp **chưa xác định** và quay lại bằng chứng chứ không đoán.

### Cách đọc nhanh theo nhánh

1. Có **java.lang.OutOfMemoryError** trong log không? Nếu có, trích nguyên văn message và điểm ném; xác minh process có bị kill/fatal error tiếp theo hay không.
2. Có chuỗi **Java heap space / GC overhead**? Ưu tiên heap và GC evidence, sau đó phân biệt retention, allocation burst và heap quá nhỏ.
3. Có **Metaspace / Compressed class space**? Kiểm tra class metadata, classloader, unloading và giới hạn tương ứng.
4. Có **direct buffer / native thread / map**? Thu thập tài nguyên ngoài heap và giới hạn OS, không bắt đầu bằng tăng -Xmx.
5. Không có Java exception nhưng có **OOMKilled / hs_err**? Điều tra sự kiện OS/container hoặc fatal native allocation theo nguồn ghi nhận; heap dump có thể không tồn tại.
6. Nếu chỉ thấy một chuỗi không rõ nguồn, trước tiên xác minh process, JVM, version, timestamp và toàn bộ thông điệp; không vội gán nhóm.

## 3. Nhóm Java heap: cùng vùng, nhiều cơ chế khác nhau

### 3.1. java.lang.OutOfMemoryError: Java heap space

**Ý nghĩa:** JVM không đáp ứng được một yêu cầu cấp phát object/array trong heap, ngay cả sau những hành động thu hồi được phép tại thời điểm đó. Đây là mô tả **allocation failure**, không phải phép đo rằng mọi byte heap đều là object sống.

Các giả thuyết thường gặp:

- **Retention/leak:** object còn reachable qua static field, cache không giới hạn, listener, queue, collection, ThreadLocal, classloader hoặc vòng đời session. Post-GC occupancy/lượng object retained có xu hướng tăng khi so sánh cùng tải.
- **Live set hợp lệ quá lớn:** ứng dụng cần giữ dữ liệu thật sự (ví dụ batch tải cả tập dữ liệu vào RAM), nhưng heap tối đa không đủ.
- **Allocation burst:** tạo nhiều object/array lớn trong một khoảng ngắn; heap chạm giới hạn khi traffic/parallelism tăng.
- **Object/array rất lớn:** một lần cấp phát cần vùng heap lớn, gặp giới hạn kích thước object, fragmentation hoặc chính sách collector; không nhất thiết do hàng triệu object nhỏ.
- **Cấu hình không đúng với dự kiến:** -Xmx thực tế thấp hơn kế hoạch; container-aware heap sizing, script hoặc deployment overrides khiến JVM nhận giới hạn khác.

**Bằng chứng ưu tiên:** -Xmx có hiệu lực, heap occupancy trước/sau GC theo thời gian, GC logs, heap dump nếu có và an toàn, dominator tree, retained size, GC roots, allocation profile, sự biến động workload. Heap dump giúp tìm **ai đang giữ object**; allocation profile giúp tìm **ai tạo object mới**. Hai câu hỏi khác nhau, cần tránh dùng một số liệu thay cho số liệu kia.

**Không nên kết luận:** “Thấy Java heap space thì tăng Xmx là sửa được leak.” Heap lớn hơn có thể chỉ kéo dài thời gian tới lỗi; cũng có thể đẩy container tới OOMKilled do giảm headroom cho phần native.

### 3.2. java.lang.OutOfMemoryError: GC overhead limit exceeded

**Ý nghĩa:** JVM phát hiện tình trạng dành quá nhiều thời gian cho GC nhưng thu hồi quá ít bộ nhớ theo heuristic/chính sách giới hạn GC overhead áp dụng ở collector/cấu hình đó. Nó phản ánh **GC không giúp tiến trình tiếp tục hiệu quả**, thường liên quan heap pressure. Không đồng nhất với một pause duy nhất quá dài.

Cần xem:

- GC đang chạy bao nhiêu lần, tổng thời gian GC trên cửa sổ xảy ra lỗi; mức thu hồi trước/sau mỗi lần phù hợp.
- Heap sau GC còn rất cao vì object vẫn reachable hay do tải tạo object liên tục?
- Collector và option GC overhead limit có áp dụng hay không; không lấy một ngưỡng phần trăm bất biến áp cho mọi JVM.
- GC CPU, throughput, p99 latency, Full GC và allocation pressure trong cùng timeline.

**Xử lý hướng nguyên nhân:** kiểm tra retention, memory footprint hợp lệ, size/batch/concurrency, sau đó mới thiết kế thử nghiệm heap/GC. Vô hiệu hóa giới hạn GC overhead chỉ để “hết exception” có thể khiến ứng dụng tiếp tục quay cuồng trong GC mà không khôi phục được khả năng phục vụ; không làm như một giải pháp mặc định.

### 3.3. java.lang.OutOfMemoryError: Requested array size exceeds VM limit

**Ý nghĩa:** yêu cầu tạo array vượt ngưỡng kích thước mà JVM hỗ trợ. Giới hạn array không đơn giản bằng Integer.MAX_VALUE phần tử cho mọi loại array/JVM; overhead, object header và quy tắc VM có ảnh hưởng.

Ví dụ nguyên nhân: chuyển dữ liệu cực lớn thành một byte[], tính nhầm kích thước từ file/stream, cộng/trừ integer không kiểm tra, cố cấp phát tập dữ liệu vào một array duy nhất.

**Bằng chứng:** giá trị length yêu cầu, loại array, phép tính dẫn tới length, dữ liệu đầu vào, API và đoạn code cấp phát. Ưu tiên streaming, phân đoạn/chunking, validate kích thước, tránh ép toàn bộ payload thành một array. **Tăng -Xmx không vượt được giới hạn kích thước array của VM.**

Đừng đánh đồng với NegativeArraySizeException (kích thước âm) hoặc với Java heap space (cấp phát heap thất bại sau khi kích thước array hợp lệ).

## 4. Nhóm metadata: Metaspace và Compressed class space

### 4.1. OutOfMemoryError: Metaspace

Trên HotSpot hiện đại, metadata class chủ yếu ở **Metaspace**, một vùng quản lý bằng native memory (không phải Java object heap). Java 8+ không dùng PermGen theo mô hình HotSpot cũ. Vì vậy khi gặp Metaspace OOME, tăng -Xmx **không trực tiếp** mở rộng metaspace.

Khả năng thường gặp:

- Tải/sinh quá nhiều class hoặc classloader: dynamic proxies, bytecode generation, framework/plugin, hot reload, instrumentation.
- **Classloader leak:** classloader cũ vẫn reachable nên class và metadata liên quan không unload được, thường thấy classloader/class count tăng qua các lần redeploy.
- Giới hạn -XX:MaxMetaspaceSize quá thấp so với workload hợp lệ.
- Native/container memory pressure gây thiếu khả năng cấp phát ngay cả khi không giới hạn metaspace nhỏ.

Cần đo classloader statistics, loaded/unloaded classes, metaspace used/committed, class metadata theo thời gian, NMT (nếu có), memory limit/RSS. Một lượng class lớn **không tự chứng minh leak**: cần chứng minh classloader đáng lẽ hết vòng đời vẫn bị giữ. Class unloading phụ thuộc GC/classloader reachability và thời điểm collection; số class không giảm ngay sau một young GC là bình thường.

### 4.2. OutOfMemoryError: Compressed class space

Với cấu hình HotSpot dùng compressed class pointers, **Compressed Class Space (CCS)** chứa phần metadata cần địa chỉ nén của class và có giới hạn/cơ chế quản lý riêng. Lỗi “Compressed class space” định vị khác với “Metaspace”, dù đều thuộc miền class metadata.

Cần xác minh compressed class pointers đang bật, giới hạn -XX:CompressedClassSpaceSize nếu cấu hình có dùng, chỉ số CCS used/committed/reserved và sự tăng class/classloader. Điều chỉnh giới hạn riêng chỉ sau khi hiểu lớp nào/classloader nào tăng và container có đủ memory headroom.

**Sai lầm thường gặp:** tăng Xmx, thay GC hoặc tăng MaxMetaspaceSize đơn thuần mà không kiểm tra CCS. Tham số đúng để thử nghiệm tùy chính xác vùng giới hạn được ghi nhận và có dữ liệu thực nghiệm.

### 4.3. Dấu hiệu classloader leak trong heap dump

Metaspace nằm ngoài Java heap nhưng **đường tham chiếu giữ classloader** thường có thể thấy trong heap dump: static references, Thread.contextClassLoader, cache registry, thread còn sống, listener/driver không deregister, plugin manager giữ handle. Xem cả retained paths của classloader và xu hướng tăng metaspace; đừng tìm “object Metaspace” trong Java heap như một object bình thường.

## 5. Nhóm off-heap/direct buffer và memory mapping

### 5.1. Direct buffer memory

Thông báo có thể là:

~~~text
java.lang.OutOfMemoryError: Direct buffer memory
~~~

hoặc trong một số JDK:

~~~text
java.lang.OutOfMemoryError: Cannot reserve 1048576 bytes of direct buffer memory (allocated: ..., limit: ...)
~~~

Đây là nhóm cấp phát/quản lý **direct ByteBuffer**: vùng dữ liệu buffer nằm ngoài heap. Direct buffer thường có một Java wrapper trên heap, trong khi bộ nhớ thực chứa dữ liệu do cơ chế native quản lý.

Cần tách ba đại lượng:

- **Java heap:** chứa wrapper/đối tượng tham chiếu tới buffer.
- **Direct buffer reservation/limit:** giới hạn do -XX:MaxDirectMemorySize và cơ chế JVM áp dụng cho một số direct buffer allocations; message có thể nêu “allocated/limit”.
- **Native/RSS:** tổng bộ nhớ ngoài heap của tiến trình rộng hơn direct buffer, gồm threads, class metadata, code cache, native libraries và những vùng không thuộc direct buffer counter.

**Bằng chứng:** java.nio.BufferPoolMXBean cho pool direct (Count, MemoryUsed, TotalCapacity; tên/khả năng tùy implementation), NMT nếu đã bật, allocation profile, số kết nối và kích thước buffers, vòng đời cleanup, RSS/container limit. Khi MemoryUsed, TotalCapacity và số buffers tăng theo tải, cần phân biệt cache hợp lệ với retention/leak.

Direct buffer giới hạn đạt trần **không đồng nghĩa** toàn bộ hệ điều hành hết RAM. Ngược lại, direct buffer còn dưới giới hạn không chứng minh native memory đủ cho các thành phần khác. Tăng MaxDirectMemorySize phải đi kèm budget native/container, nếu không có thể chuyển lỗi thành OOMKilled.

### 5.2. MappedByteBuffer và lỗi map

FileChannel.map và memory-mapped I/O sử dụng OS memory mappings và **không hoàn toàn có cùng vòng đời/giới hạn** như direct ByteBuffer thông thường. Một OOME có message liên quan “Map failed”/mmap không đủ để suy ra lỗi do MaxDirectMemorySize.

Kiểm tra loại mapping, file size, số lượng mappings, address space, OS vm.max_map_count (nếu phù hợp), limits, file-backed mappings và cách ứng dụng quản lý lifecycle. Lỗi map có thể liên quan không gian địa chỉ hoặc nguồn lực của OS; cũng phải đọc nguyên nhân hệ thống cụ thể. Không đề xuất tăng -Xmx khi thấy map failure; heap lớn hơn có thể chiếm thêm địa chỉ/bộ nhớ.

### 5.3. Những vùng native khác

Ngoài direct/mapped buffers còn có native allocations của thư viện JNI/FFM, thread stacks, JIT code cache, GC metadata, arenas, runtime internals và memory-mapped libraries. NMT phân loại phần **do JVM theo dõi**, không đảm bảo bao phủ mọi allocation của thư viện native ngoài JVM; các số reserved/committed của NMT cũng **không bằng RSS**.

Nếu RSS/working set tăng nhưng heap used tương đối ổn định, cần kiểm tra native breakdown, direct buffer pools, thread count, metaspace, memory mappings, cgroup limit và native profiler khi thật cần.

## 6. Nhóm native thread: không tạo được thread mới

Một thông báo HotSpot thường thấy:

~~~text
java.lang.OutOfMemoryError: unable to create native thread: possibly out of memory or process/resource limits reached
~~~

JVM phải tạo một thread hệ điều hành tương ứng với platform thread. Việc tạo thread có thể thất bại do:

- Cạn giới hạn số process/thread trong OS hoặc cgroup pids.max.
- Không còn đủ memory/address space để đặt native thread stack và cấu trúc liên quan.
- Tạo quá nhiều thread vì thread pool không giới hạn, mỗi request tạo thread mới, thread bị giữ hoặc nhiều thư viện cùng lập pool.
- Giới hạn per-user/process như ulimit và chính sách runtime/container.

**Bằng chứng cần thu:** số thread đang sống (JVM và OS), xu hướng tăng, thread names/states, thread dump khi an toàn, pids.current/pids.max, ulimit, stack size thực tế, OS/RSS/native memory. Đọc “unable to create native thread” để điều tra **thread/resource limits**, không tự cho rằng heap đầy.

Các biện pháp dựa trên nguyên nhân có thể là bounded thread pool, giới hạn concurrency/queue, đóng executor khi hết vòng đời, xử lý blocking I/O, điều chỉnh PID limit theo năng lực hệ thống. Chỉ chỉnh -Xss khi hiểu tác động đến call depth/StackOverflowError, tài nguyên và số thread; hạ Xss không sửa nguyên nhân tạo vô hạn thread.

**Lưu ý:** Java virtual threads (JDK 21) được quản lý khác platform threads; số lượng virtual threads không đồng nhất với số thread OS. Native-thread OOME vẫn liên quan tài nguyên platform/carrier threads hoặc những luồng OS khác.

## 7. Native allocation fatal và container OOMKilled

### 7.1. JVM fatal error khi không cấp phát native memory

Ví dụ thông điệp startup/runtime:

~~~text
There is insufficient memory for the Java Runtime Environment to continue.
Native memory allocation (malloc) failed to allocate ... bytes ...
~~~

Cũng có thể thấy mmap/commit failures hoặc thông báo không thể reserve heap lúc khởi động. Các chuỗi này thường xuất hiện trong **VM fatal error report** (ví dụ hs_err_pid*.log), không nhất thiết là java.lang.OutOfMemoryError đã được ném và bắt bởi ứng dụng.

Đọc file hs_err đầy đủ: allocation type, bytes requested, native stack, process/thread information, VM flags, OS memory/swap và cgroup limits. Đối chiếu với giám sát process trước khi chết. **Không xử lý** chỉ bằng heap dump của một process đã chết hoặc bằng cách đổi Xmx mà chưa hiểu bộ nhớ native cần bao nhiêu.

### 7.2. Container OOMKilled và tín hiệu từ kernel

Trong Kubernetes, trạng thái container có thể ghi reason **OOMKilled** với exit code 137 và restart count tăng. JVM có thể bị kill tức thì nên không kịp ghi Java stack trace, heap dump hoặc shutdown hook. Cũng cần loại trừ SIGKILL do tác nhân khác khi chỉ có exit 137.

Xem sự kiện/termination reason từ container runtime và orchestrator; trên Linux cgroup v2, đọc đúng cgroup của process/container:

~~~bash
cat /sys/fs/cgroup/memory.max
cat /sys/fs/cgroup/memory.current
cat /sys/fs/cgroup/memory.events
cat /sys/fs/cgroup/pids.current
cat /sys/fs/cgroup/pids.max
~~~

Đường dẫn trên chỉ minh họa một cách mount cgroup v2 phổ biến. Trong container khác, cgroup v1 hoặc cấu hình mount đặc biệt, phải định vị cgroup thực tế; không coi các lệnh này luôn chỉ về ứng dụng đang điều tra. memory.events có các counters như oom/oom_kill; đối chiếu theo thời điểm/cgroup, không lấy counters tích lũy rồi kết luận rằng sự kiện mới nhất do ứng dụng.

**Ngân sách memory container** bao gồm heap + metaspace + thread stacks + direct buffers + code cache + GC/native allocations + các thành phần khác. Đừng tính “limit = -Xmx” hay “RSS = heap used”. Cờ MaxRAMPercentage chỉ ảnh hưởng quy tắc chọn heap trong những hoàn cảnh tương ứng, không cấp toàn bộ memory cho heap.

### 7.3. Đừng nhầm với StackOverflowError

java.lang.StackOverflowError thường xảy ra khi stack của một thread không chứa thêm frame do đệ quy sâu/vô hạn; đó là **một Error khác**. Không phân loại thành Java heap OOME. Native-thread OOME có thể liên quan memory dành cho stack, nhưng là lỗi **tạo thread**, không đồng nhất với tràn stack khi thực thi.

## 8. Thu thập chứng cứ: đúng tiến trình, đúng thời điểm, đúng công cụ

### 8.1. Chụp hồ sơ lỗi khi process còn sống

Các ví dụ sau dành cho HotSpot/OpenJDK 17+ trên môi trường có jcmd/jstat (JDK tools), với quyền attach hợp lệ; nhiều minimal container không đóng gói đủ công cụ. Thay PID theo process cụ thể:

~~~bash
java -version
jcmd -l
PID=12345  # Thay bằng PID thực tế
jcmd "$PID" VM.command_line
jcmd "$PID" VM.flags
jcmd "$PID" GC.heap_info
jstat -gcutil "$PID" 1000 20
~~~

Giải thích:

- VM.command_line/VM.flags xác nhận JVM và options **đang chạy**, không dựa vào giá trị trong chart hoặc manifest đã cũ.
- GC.heap_info cung cấp ảnh chụp heap/metaspace tùy implementation, không thay được chuỗi thời gian trước lúc OOME.
- jstat -gcutil lấy 20 mẫu cách nhau 1 giây, giúp nhận diện xu hướng GC; một snapshot sau restart **không đại diện** cho lúc process trước đó bị chết.
- VM.command_line có thể lộ arguments nhạy cảm: loại bỏ secret trước khi chia sẻ log.

Nếu nghi classloader/thread issue, trước tiên kiểm tra lệnh có được JVM hỗ trợ:

~~~bash
jcmd "$PID" help
jcmd "$PID" Thread.print -l
jcmd "$PID" VM.classloader_stats
~~~

Thread.print có thể tạo file/log lớn hoặc gây overhead với ứng dụng rất nhiều thread; áp dụng theo giới hạn vận hành. VM.classloader_stats có trên một số HotSpot versions/configurations; nếu command không có, dùng classloading metrics/JFR hoặc công cụ thay thế phù hợp.

Trên Linux, số thread và RSS ở cấp process có thể tham khảo:

~~~bash
ps -o pid,nlwp,rss,vsz,cmd -p "$PID"
~~~

RSS từ ps thường tính KiB trên Linux, VSZ là virtual memory size; không đồng nhất với heap size. Cột và đơn vị phụ thuộc OS.

### 8.2. Quan sát native memory (NMT) có điều kiện

HotSpot Native Memory Tracking cần được bật từ lúc khởi động nếu muốn dùng các lệnh NMT; ví dụ:

~~~text
-XX:NativeMemoryTracking=summary
~~~

Sau đó:

~~~bash
jcmd "$PID" VM.native_memory summary
jcmd "$PID" VM.native_memory baseline
# Sau một khoảng tải đại diện:
jcmd "$PID" VM.native_memory summary.diff
~~~

NMT có chi phí theo dõi và phạm vi quan sát riêng; chỉ dùng trên production khi đã đánh giá overhead. Không thể kỳ vọng bật NMT hồi tố sau khi process chết. Summary/diff cho thấy nhóm memory do JVM quản lý tăng/giảm, **không thay được** process RSS, cgroup memory hoặc native profiler khi thư viện ngoài JVM cấp phát.

### 8.3. GC logs và JFR

Khi có thể cấu hình từ startup với phạm vi logging phù hợp:

~~~bash
java '-Xlog:gc*,safepoint=info:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20M' -jar app.jar
~~~

Lệnh minh họa cần app.jar thật, quyền ghi file và dung lượng/rotation phù hợp. GC logs nên được liên kết với application p99/throughput/errors, CPU và memory tại **cùng timestamp**. Nếu được phép, một JFR recording với cấu hình có GC/classloading/allocation events có thể hỗ trợ điều tra:

~~~bash
jcmd "$PID" JFR.start name=oome_probe settings=profile duration=5m filename=oome-probe.jfr
jcmd "$PID" JFR.check
~~~

Duration 5 phút chỉ minh họa; event coverage tùy cấu hình, và profile có overhead. Không khẳng định recording này sẽ chứng minh leak hoặc capture đầy đủ mọi native allocation. Bảo vệ log/recording vì có thể chứa thông tin nhạy cảm.

### 8.4. Heap dump: giá trị và giới hạn

Các tùy chọn HotSpot thường dùng khi cần ghi dump tại một Java OOME:

~~~text
-XX:+HeapDumpOnOutOfMemoryError
-XX:HeapDumpPath=/path/with/space/and/permissions
~~~

Chúng phải được cấu hình và kiểm tra từ trước, gồm dung lượng disk, quyền file, chính sách dữ liệu nhạy cảm. Heap dump có thể rất lớn và tạo thêm áp lực I/O; không chắc được sinh khi process bị OOMKilled, native fatal error hoặc không đủ disk. Đặt path ngoài volume nhỏ thường giúp tránh làm đầy container.

Heap dump chỉ mô tả **Java heap tại thời điểm dump**. Nó hữu ích cho retained objects và GC roots nhưng không chứa toàn bộ native allocations. Với Metaspace leak, dùng heap dump để lần theo classloader references kết hợp class metadata/NMT; với direct buffer, tìm wrapper/retention trên heap nhưng xác minh dung lượng direct bằng buffer pool/native metrics.

**Không tự chạy heap dump trên production để “thử xem”** nếu chưa biết tác động: một số lệnh heap inspection gây pause lớn, có thể kích hoạt GC, chiếm đĩa và chứa dữ liệu nhạy cảm.

### 8.5. Khi process đã chết

Nếu không thể attach, dùng dữ liệu được thu từ trước: ứng dụng stderr/stdout, structured exception logs, GC logs, JFR/heap dump đã cấu hình, hs_err file, APM metrics, Prometheus time series, Kubernetes events, kernel/cgroup events, restart reason, deployment/JDK flags. Tách ID của process/container **trước và sau restart**: không dùng measurements của process mới làm evidence cho process cũ.

## 9. Bảng điều tra theo vùng và quyết định thử nghiệm

| Kết quả đã xác minh | Bằng chứng tiếp theo | Giả thuyết/can thiệp có thể thử | Không nên làm ngay |
| --- | --- | --- | --- |
| Heap OOME + retained set tăng dù workload tương tự | Heap dump, dominator tree, GC roots, cache/queue | Sửa reference retention, giới hạn cache/queue | Chỉ tăng heap để che leak |
| Heap OOME + live set ổn định nhưng burst vượt headroom | GC log, allocation rate, peak concurrency, memory budget | Streaming/chunking, giới hạn concurrency, thử Xmx phù hợp budget | Tăng Xmx vượt memory limit |
| GC overhead OOME + GC tốn CPU và thu hồi rất ít | GC time, post-GC heap, allocation/retention | Giảm churn/retention; thử heap/GC trong benchmark | Tắt kiểm tra GC overhead để dập exception |
| Requested array size exceeds VM limit | Requested length/loại array/công thức size | Chunking/streaming, validate input, sửa phép tính | Tăng Xmx như lời giải duy nhất |
| Metaspace/CCS OOME + classloader count tăng | Classloader stats, unloading, references, class gen | Sửa classloader leak/stop generation; điều chỉnh đúng cap nếu hợp lệ | Đổi heap size thay cho metadata |
| Direct buffer OOME + direct pool tiến gần cap | BufferPoolMXBean, peak allocation, cleanup, RSS | Giảm/giới hạn buffer retention, tối ưu pool, cân nhắc direct cap có budget | Tăng -Xmx hoặc direct cap mù quáng |
| Unable to create native thread + pids gần cap | Thread dump, pids.max/current, OS limit | Bounded pool, xử lý thread leak, tăng limit có căn cứ | Tự động giảm Xss mà không hiểu thread growth |
| OOMKilled + heap không gần Xmx | cgroup, process RSS, NMT/native, direct/thread/meta | Tìm bộ nhớ ngoài heap; cân lại limit/replica/budget | Gắn nhãn “Java heap leak” |
| Fatal native malloc failure | hs_err, native breakdown, system commit/memory | Giảm native pressure, sửa leak, xử lý OS constraints | Chỉ phân tích Java heap dump |

Các nhánh cần xét **đồng thời** nếu ứng dụng có nhiều áp lực: một ứng dụng có thể có cả leak trên heap và native thread growth. Chỉ số tốt hơn ở một vùng chưa có nghĩa tiến trình đã an toàn.

## 10. Ví dụ Java 17+ để tránh phân loại quá tự tin

Đoạn sau là **chương trình độc lập chạy được**, minh họa cách biến một số message thành **giả thuyết tài nguyên đầu tiên**, chưa phải bằng chứng nguyên nhân. Đặt file tên OomeTriage.java:

~~~java
import java.util.Locale;

public class OomeTriage {
    static String suspectedArea(String message) {
        if (message == null || message.isBlank()) {
            return "Chưa đủ thông tin";
        }
        String m = message.toLowerCase(Locale.ROOT);
        if (m.contains("requested array size exceeds vm limit")) {
            return "Giới hạn kích thước array của VM";
        }
        if (m.contains("gc overhead limit exceeded")) {
            return "Heap và tiến độ thu hồi của GC";
        }
        if (m.contains("java heap space")) {
            return "Java heap";
        }
        if (m.contains("compressed class space")) {
            return "Compressed class space";
        }
        if (m.contains("metaspace")) {
            return "Metaspace";
        }
        if (m.contains("direct buffer memory")) {
            return "Direct buffer / native allocation";
        }
        if (m.contains("native thread")) {
            return "Thread OS, PID limit hoặc native stack";
        }
        if (m.contains("map failed")) {
            return "Memory mapping / tài nguyên OS";
        }
        return "Chưa phân loại; cần nguyên văn lỗi và telemetry";
    }

    public static void main(String[] args) {
        String[] messages = {
            "Java heap space",
            "GC overhead limit exceeded",
            "Metaspace",
            "Cannot reserve 1048576 bytes of direct buffer memory",
            "unable to create native thread: possibly out of memory"
        };
        for (String message : messages) {
            System.out.println(message + " => " + suspectedArea(message));
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17+:

~~~bash
javac OomeTriage.java
java OomeTriage
~~~

Kết quả chuẩn của chương trình trên (chuỗi input đã cố định):

~~~text
Java heap space => Java heap
GC overhead limit exceeded => Heap và tiến độ thu hồi của GC
Metaspace => Metaspace
Cannot reserve 1048576 bytes of direct buffer memory => Direct buffer / native allocation
unable to create native thread: possibly out of memory => Thread OS, PID limit hoặc native stack
~~~

**Giới hạn cố ý của ví dụ:** chỉ so chuỗi mẫu, không tạo OOME thật và không phân tích runtime. Phân loại production phải lấy cả exception type, JVM vendor/version, log và số liệu tương ứng. Ví dụ, message “native memory allocation failed” từ hs_err có thể là fatal JVM event chứ không phải một java.lang.OutOfMemoryError.

### Mẫu thu thập nhanh để kiểm chứng giả thuyết

Ghi theo cấu trúc sau trong incident/ticket:

| Trường | Nội dung cần ghi |
| --- | --- |
| Service/process | Tên service, pod/container, PID, deploy version |
| Thời điểm | Timestamp với timezone, thời điểm restart và thời điểm lỗi |
| Loại thất bại | Java OOME, VM fatal, OS OOMKilled hay chưa xác định |
| Thông điệp | Exception class + message nguyên văn, stack trace/hs_err/termination reason |
| JVM và giới hạn | JDK/vendor, GC, -Xmx/-Xms, MaxMetaspaceSize/MaxDirectMemorySize nếu có, cgroup memory/pids limits |
| Tài nguyên nghi cạn | Heap, metaspace, CCS, direct, mapped, native thread, native memory, container |
| Chứng cứ thời điểm lỗi | Heap used/post-GC, GC events, RSS, thread/classloader/buffer counters, kernel/cgroup events |
| Giả thuyết | Một phát biểu có thể bác bỏ được, kèm điều kiện và loại trừ nguyên nhân khác |
| Thử nghiệm và guardrails | Thay đổi nhỏ nhất, workload tương đương, p99/errors/throughput, RSS/CPU, kế hoạch rollback |

## 11. Ba tình huống dễ chẩn đoán nhầm

### Tình huống A — Heap OOME nhưng vấn đề là giữ object

Sau mỗi batch, heap used tăng. Sau các collection tương đương ở cùng workload, mức used “đáy” cũng tăng. Cuối cùng xuất hiện Java heap space. Heap dump cho thấy một static map giữ hàng triệu record của các batch đã hoàn tất qua GC root. **Nguyên nhân gốc là retention của map**; phương án là thiết kế lại vòng đời/cache/eviction hoặc streaming. Tăng -Xmx có thể kéo dài thời gian trước khi thất bại, nhưng không giải quyết reference còn sống.

### Tình huống B — Không có Java heap OOME nhưng container OOMKilled

Pod memory limit 1 GiB, -Xmx 512 MiB. Heap used quanh 300 MiB, nhưng direct buffers + metaspace + thread stacks + các allocations khác khiến working set vượt limit khi tải tăng. Kubernetes ghi OOMKilled, không có Java exception. **Không thể kết luận heap thiếu**; cần memory budget đầy đủ, direct pool/thread trends và cgroup events. Tăng -Xmx từ 512 lên 768 MiB mà giữ nguyên limit có thể làm rủi ro lớn hơn.

Các số là ví dụ giả định, không phải khuyến nghị cấu hình.

### Tình huống C — Metaspace OOME sau nhiều lần hot reload

Sau mỗi lần reload plugin, số classloader tăng và không giảm; Metaspace usage tăng đều cho tới OutOfMemoryError: Metaspace. Heap dump tìm được thread do plugin cũ tạo, vẫn giữ context classloader. **Classloader retention** là giả thuyết mạnh vì có chuỗi reference và trend; cần dừng thread/đóng plugin đúng lifecycle, chứ không chỉ tăng MaxMetaspaceSize. Xác nhận bằng số classloader, unload events và metaspace ổn định qua nhiều vòng reload.

## 12. Những lỗi điều tra thường gặp

- **Chỉ nhìn message, bỏ qua môi trường:** cùng Java heap space nhưng nguyên nhân có thể là leak, burst hay Xmx thấp. Message định vị bước đầu, không thay chứng cứ.
- **Đồng nhất heap used, committed, max và RSS:** bốn giá trị khác nghĩa; memory limit container quản lý nhiều vùng ngoài heap.
- **Dùng heap dump để “đo toàn bộ native RAM”:** dump chứa Java objects và reference, không đo đầy đủ metaspace, direct allocations, thread stacks hay memory-mapped files.
- **Diễn giải stack trace allocation failure là vị trí leak:** object bị giữ có thể do nơi khác tạo reference lâu dài; cần retained paths/GC roots.
- **Nhìn Full GC nhiều rồi đổi collector ngay:** phải xác định Full GC do thiếu headroom, retention, fragmentation, metadata hay allocation burst; collector không chữa leak.
- **Chạy lệnh nặng trong sự cố mà không đánh giá tác động:** heap dump/class histogram/JFR profiling và attachment có thể gây overhead, pause và I/O; không phải mọi lệnh đều an toàn ở mọi tải.
- **So số đo trước và sau restart:** PID khác, heap khác, classloader khác. Ghi lại thông tin process cũ.
- **Chỉ dựa vào exit 137:** cần OOMKilled reason hoặc kernel/cgroup event; SIGKILL có thể đến từ tác nhân khác.
- **Tăng -Xmx trong container có memory limit cố định:** native headroom giảm, có thể chuyển Java OOME thành OOMKilled.
- **Trông chờ -XX:+HeapDumpOnOutOfMemoryError cho mọi failure:** VM fatal/native kill không bảo đảm sinh dump; phải chuẩn bị GC logs, container telemetry và crash logs từ trước.
- **Thay nhiều tham số cùng lúc:** không biết gì gây cải thiện hoặc regression; thử từng giả thuyết, giữ baseline và rollback rõ ràng.

## 13. Checklist ra quyết định cuối cùng

- [ ] Tôi đã ghi nguyên văn class/message, stack trace hoặc hs_err/termination reason và timestamp.
- [ ] Tôi phân biệt Java OOME với VM fatal native error và process bị OOMKilled.
- [ ] Tôi xác nhận chính xác JVM version/vendor, flags và giới hạn OS/cgroup thực tế.
- [ ] Tôi xác định vùng tài nguyên **nghi cạn**, kèm metrics phù hợp để chứng minh hoặc bác bỏ.
- [ ] Tôi đã đối chiếu tình trạng trước, trong, sau sự cố ở đúng PID/pod và dưới workload tương đương.
- [ ] Với heap: xem live set/retained paths, allocation rate, GC behavior và peak load.
- [ ] Với Metaspace/CCS: xem classloader/classes/unloading và giới hạn metadata.
- [ ] Với direct/native/thread: xem buffer pools, NMT khi có, RSS, pids/thread limits và lifecycle tài nguyên.
- [ ] Với container kill: có OOMKilled/cgroup/kernel evidence; không suy diễn từ exit 137 đơn lẻ.
- [ ] Tôi viết được giả thuyết nguyên nhân gốc và lựa chọn can thiệp đúng vùng: sửa retention, giới hạn tải/thread, streaming/chunking, sửa classloader/direct lifecycle hoặc tuning có kiểm chứng.
- [ ] Có baseline, điều kiện chấp nhận, guardrails và rollback; không chỉnh heap/GC/OS limits mù quáng.

## 14. Kết luận

**OutOfMemoryError là điểm bắt đầu của chẩn đoán, không phải tên một nguyên nhân gốc duy nhất.** Quy trình đúng là:

**Đọc nguyên văn lỗi → xác định loại thất bại (Java/VM fatal/OS kill) → ánh xạ vùng tài nguyên → thu thập chứng cứ cùng thời điểm → phân biệt leak với tải hợp lệ/giới hạn cấu hình → thử nghiệm can thiệp và kiểm chứng.**

Đừng để chữ “memory” khiến bạn tự động tăng Java heap. Chính vùng tài nguyên **thực sự không thể cấp phát được** cùng với dữ liệu đối chiếu mới quyết định nên kiểm tra heap dump, classloader, direct buffer, native thread, memory maps hay giới hạn container.

### Tài liệu chính thức để tra cứu theo môi trường

- Java 21 API — OutOfMemoryError: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/OutOfMemoryError.html
- Java 21 — jcmd: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html
- Java 21 — Java launcher / VM options / Unified Logging: https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html
- Linux kernel cgroup v2: https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html
