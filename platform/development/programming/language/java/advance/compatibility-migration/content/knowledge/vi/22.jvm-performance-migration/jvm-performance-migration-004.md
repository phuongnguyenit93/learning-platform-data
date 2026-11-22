# Heap, metaspace và hành vi quản lý bộ nhớ sau nâng cấp

Khi nâng JDK, một ứng dụng có thể chạy đúng chức năng nhưng tiêu thụ bộ nhớ khác trước: heap giảm mà RSS của process tăng, thời gian GC thay đổi, metaspace sau khi tải và gỡ lớp có thể thu hồi bộ nhớ khác, hoặc container bị kill dù `-Xmx` chưa chạm giới hạn. Những hiện tượng này không nhất thiết là Java mới “bị rò rỉ bộ nhớ”. Chúng có thể đến từ **bố cục và cách quản lý bộ nhớ của JVM**, garbage collector được chọn, giới hạn cgroup/container, thư viện mới, số lượng thread, buffer trực tiếp, code cache hoặc vòng đời class loader.

Trong **Java Advance Compatibility Migration**, cần giữ tách biệt ba câu hỏi:

1. **Có thay đổi về mức sử dụng bộ nhớ thực không?** Đo heap used/committed, metaspace, native/off-heap và RSS bằng phương pháp phù hợp.
2. **Vì sao thay đổi?** Do workload, version JDK/GC, sizing ergonomics, application retention, class loading hay native allocation?
3. **Ảnh hưởng tới mục tiêu vận hành thế nào?** Có tăng p99 latency, thời gian pause, số lần OOM, restart, CPU/throughput hoặc chi phí hạ tầng không?

Bài học giải thích heap, metaspace và các vùng bộ nhớ liên quan; những thay đổi quan trọng giữa các thế hệ JDK; cách đọc log/metric, thiết lập JVM options và xây dựng quy trình so sánh trước–sau có thể tái lập. Mục tiêu không phải là làm biểu đồ “used memory” luôn thấp, mà là **giữ ứng dụng ổn định, không vượt ngân sách bộ nhớ và đạt mục tiêu latency/throughput dưới tải thực tế**.

## 1. Bản đồ bộ nhớ của một tiến trình Java

Một ứng dụng HotSpot sử dụng nhiều vùng bộ nhớ hơn Java heap.

~~~text
Container / host memory budget
|
+-- Java process (JVM)
|   |
|   +-- Java heap
|   |   +-- Objects / arrays
|   |   +-- Young/old regions or generations (theo GC)
|   |
|   +-- Metaspace
|   |   +-- Class metadata
|   |   +-- Class-loader-related allocations
|   |
|   +-- Compressed class space (khi áp dụng)
|   +-- JIT code cache
|   +-- Thread stacks + JVM/internal threads
|   +-- Direct buffers / off-heap memory
|   +-- JNI / FFM / third-party native allocations
|   +-- GC bookkeeping, symbols, arenas, compiler data
|   +-- Mapped files and shared/native libraries
|
+-- Other processes and container overhead
~~~

Có những vùng có thể được giới hạn trực tiếp bằng JVM option, có những vùng không. Tổng memory mà hệ điều hành hoặc cgroup ghi nhận **không đơn giản bằng giá trị `-Xmx`**, và cũng không luôn bằng tổng mọi con số trên một dashboard do khác khái niệm reserved, committed và resident.

### 1.1. Bảng so sánh nhanh

| Vùng | Chứa gì | Tín hiệu/công cụ | Option liên quan |
|---|---|---|---|
| Java heap | Object/array Java, bao gồm nhiều buffer wrapper | `MemoryMXBean`, GC logs, `GC.heap_info`, heap dump | `-Xms`, `-Xmx`, `MaxRAMPercentage` |
| Metaspace | Metadata của lớp Java | Metaspace memory pool, `VM.metaspace`, NMT | `MaxMetaspaceSize`, `MetaspaceSize` |
| Compressed class space | Một phần class metadata khi compressed class pointers được dùng | `VM.metaspace`, NMT | `CompressedClassSpaceSize` |
| Thread stacks | Call frames/stack của Java/native threads | Số thread, NMT, OS metrics | `-Xss` |
| Code cache | Mã máy do JIT biên dịch | Code cache pools, NMT, code cache logs | `ReservedCodeCacheSize` |
| Direct buffer | Dữ liệu bên ngoài heap của direct `ByteBuffer` | `BufferPoolMXBean`, NMT/OS | `MaxDirectMemorySize` khi áp dụng |
| JNI/FFM/native | Allocation do native code/thư viện quản lý | NMT một phần, profiler/native tooling, OS | Phụ thuộc thư viện/allocator |
| File mappings | Memory mapped I/O, shared libraries | OS/proc metrics, NMT một phần | Phụ thuộc mapping và workload |

**Lưu ý:** `MaxDirectMemorySize` không phải giới hạn cho mọi loại native allocation. Thư viện JNI gọi `malloc` hoặc FFM cấp vùng ngoài heap có thể không chịu cùng giới hạn như direct buffer được JVM quản lý.

## 2. Reserved, committed, used và RSS không giống nhau

Đây là nền tảng khi so sánh JDK.

- **Reserved virtual memory:** không gian địa chỉ được đặt trước; không có nghĩa số byte tương ứng đang nằm trong RAM vật lý.
- **Committed:** những trang memory mà JVM/OS đã bảo đảm hoặc kích hoạt theo mô hình quản lý; không nhất thiết mọi trang đều resident ngay.
- **Used:** phần dữ liệu đang được sử dụng theo định nghĩa của từng memory pool.
- **Resident Set Size (RSS):** các trang của tiến trình hiện nằm trong bộ nhớ vật lý, bao gồm heap resident, stack, native allocations và các phần shared/mapped.
- **Container memory usage:** số liệu do cgroup/runtime đo; có thể bao gồm cache hoặc accounting khác tùy OS/cgroup và dashboard.

Ví dụ minh họa:

~~~text
-Xmx                         = 2 GiB
Heap reserved                ≈ 2 GiB
Heap committed               = 1.4 GiB
Heap used                    = 0.8 GiB
Metaspace committed          = 0.2 GiB
Native + stack + code + misc = biến động
Process RSS                  = 1.7 GiB
Container limit              = 2.5 GiB
~~~

Các số này chỉ để giải thích khái niệm; không phải công thức tổng chính xác. Đặc biệt, vùng compressed class space có thể **reserve không gian địa chỉ rất lớn** nhưng commit và RSS thấp. Nếu thấy reserved tăng trên JDK mới mà không có tăng committed/resident, chưa đủ để gọi là memory regression.

### 2.1. Vì sao biểu đồ heap có dạng răng cưa?

Java heap thường tăng giữa các lần GC vì ứng dụng liên tục cấp phát object. Sau GC, những object không còn reachable được thu hồi, mức used giảm xuống. Đây là hành vi bình thường.

Quan trọng là **đáy sau GC** (đại diện gần đúng cho live set), tốc độ cấp phát, thời gian pause và xu hướng sau nhiều chu kỳ tải giống nhau. Heap used tăng rồi giảm định kỳ không tự chứng minh memory leak.

## 3. Java heap: chức năng và cách JVM quản lý

Heap là nơi lưu nhiều object và array Java. Garbage collector quyết định khi nào thu hồi object không còn reachable, cách compact/relocate chúng và cách chia các vùng để tối ưu hiệu năng.

Một số khái niệm:

- **Allocation rate:** lượng bộ nhớ object mới được tạo ra mỗi đơn vị thời gian.
- **Live set:** những object còn reachable sau một chu kỳ thu gom phù hợp.
- **Object retention:** object bị giữ sống bởi reference, cache, listener, thread-local hoặc static field.
- **Young/old generations hoặc regions:** cách một collector phân nhóm object theo tuổi/vị trí; chi tiết tùy GC.
- **GC pause:** khoảng thời gian ứng dụng bị tạm dừng do những pha stop-the-world.
- **Concurrent GC:** nhiều công việc thu gom diễn ra song song với application threads nhưng không loại bỏ mọi loại pause.

Các collector khác nhau có thiết kế khác nhau. Không nên áp hình dung Eden/Survivor/Old theo cùng một layout vật lý cho mọi GC hiện đại, đặc biệt với ZGC.

### 3.1. `-Xms` và `-Xmx`

Ví dụ:

~~~bash
java -Xms512m -Xmx2g -jar application.jar
~~~

- `-Xms` là mức heap khởi tạo theo cấu hình JVM.
- `-Xmx` là giới hạn trên heap.
- Heap có thể tăng hoặc, với những GC/chính sách phù hợp, giảm committed memory trong quá trình chạy.
- Cấp `-Xmx` quá thấp có thể khiến GC quá thường xuyên hoặc gặp `OutOfMemoryError: Java heap space`.
- Cấp `-Xmx` gần bằng giới hạn container không để đủ ngân sách cho metaspace, thread stacks, direct buffers, JIT và native allocations.

Không nên tự chọn `-Xms = -Xmx` cho mọi hệ thống. Cách đó có thể giúp một số workload ổn định sizing nhưng giảm khả năng JVM trả bớt heap đã commit; tác động còn tùy GC, memory pressure và yêu cầu latency.

### 3.2. Cấu hình tỷ lệ heap theo RAM

Các HotSpot JDK hỗ trợ những option như:

~~~text
-XX:InitialRAMPercentage=...
-XX:MaxRAMPercentage=...
-XX:MinRAMPercentage=...
~~~

Ví dụ minh họa:

~~~bash
java -XX:MaxRAMPercentage=60.0 -jar application.jar
~~~

Khi không đặt giới hạn heap tuyệt đối, JVM có thể chọn max heap theo tỷ lệ bộ nhớ được runtime nhận diện. Trong container-aware JDK, nguồn bộ nhớ này thường liên quan giới hạn container, nhưng cần kiểm đúng runtime và phiên bản.

**Không dùng `MaxRAMPercentage` như giới hạn toàn bộ process.** Nó chủ yếu ảnh hưởng heap sizing, không quản lý tất cả metaspace/native allocations. Khi đồng thời cung cấp `-Xmx`, cần xem JVM áp dụng thứ tự ưu tiên của những option sizing ở đúng JDK.

## 4. Metaspace là gì?

Metaspace là vùng quản lý phần lớn metadata của class trong HotSpot, nằm ngoài Java heap. Một class có metadata về method, field, constant pool liên quan và cấu trúc runtime; chúng không giống với object instance của class được cấp phát trên heap.

Từ **Java 8**, HotSpot chuyển từ permanent generation (PermGen) sang Metaspace. Vì vậy, các tùy chọn cũ như `-XX:PermSize` và `-XX:MaxPermSize` không còn là cách phù hợp để kiểm soát metadata trên JDK hiện đại.

### 4.1. Metaspace phụ thuộc vòng đời class loader

Khi ứng dụng tải một class thông qua class loader, metadata liên quan được tạo. Class unloading có thể giải phóng metadata khi các điều kiện về reachability của class loader, class và dữ liệu liên quan cho phép.

Một số trường hợp làm metaspace tăng:

- Ứng dụng có nhiều dependency và class được load ở startup.
- ORM/DI/AOP framework tạo proxy classes.
- Bytecode instrumentation hoặc dynamic class generation.
- JSP/script engine tạo class mới.
- Plugin/module được load động.
- Nhiều application class loaders không được giải phóng.
- Framework cache giữ reference tới class hoặc class loader sau undeploy.

Metaspace tăng trong quá trình warm-up có thể bình thường. Nhưng nếu số class loader tồn tại và class loaded tăng vô hạn qua nhiều vòng tạo/hủy plugin, đó có thể là dấu hiệu **classloader leak**.

### 4.2. Compressed class space

Khi HotSpot sử dụng compressed class pointers, một phần class metadata nằm trong compressed class space. Vùng này có reservation và accounting riêng; khi xem thống kê cần phân biệt `Metaspace` và `Compressed Class Space` tùy công cụ.

Một vùng reserved lớn không đồng nghĩa toàn bộ vùng đó đã commit. Không tự cộng các số reserved vào ngân sách RSS.

### 4.3. `MetaspaceSize` khác `MaxMetaspaceSize`

| Option | Ý nghĩa khái quát | Cảnh báo |
|---|---|---|
| `-XX:MetaspaceSize` | Ngưỡng/điểm khởi đầu ảnh hưởng chính sách GC vì metadata, không phải “cấp cố định toàn bộ metaspace ngay lập tức” | Đặt rất lớn có thể trì hoãn metadata-driven collection |
| `-XX:MaxMetaspaceSize` | Đặt giới hạn trên cho metaspace theo HotSpot | Quá thấp có thể gây OOM khi tải class |
| `-XX:CompressedClassSpaceSize` | Giới hạn không gian dành cho compressed class metadata khi cơ chế này được dùng | Không đồng nghĩa với toàn bộ metaspace hay RSS |

Ví dụ:

~~~bash
java -XX:MaxMetaspaceSize=384m -jar application.jar
~~~

Đây là **giới hạn giả định** để minh họa cú pháp, không phải recommendation dùng cho mọi ứng dụng. Cần đo mức class metadata hợp lệ dưới tải và kiểm tra overhead/fragmentation trước khi đặt.

Nếu gặp `OutOfMemoryError: Metaspace`, tăng limit chỉ có thể trì hoãn thất bại nếu gốc rễ là classloader leak hoặc dynamic class generation vô hạn.

## 5. JDK 16 và Elastic Metaspace

**JEP 387 — Elastic Metaspace** được đưa vào JDK 16. Mục tiêu là cải thiện khả năng trả những phần metaspace không còn dùng về hệ điều hành, giảm footprint trong một số workload, nhất là hệ thống nạp/gỡ class loaders thường xuyên.

Điều này dẫn tới một thay đổi quan trọng khi so sánh:

- Trên một JDK cũ, committed metaspace có thể giữ lại một mức cao sau khi unload nhiều class.
- Trên JDK có Elastic Metaspace, JVM có thể uncommit những vùng metadata đã rảnh với độ hạt nhỏ hơn.
- Metaspace **used**, **committed** và **reserved** có thể thay đổi theo đường thời gian khác, dù số class cần dùng không thay đổi đáng kể.
- Một số lợi ích phụ thuộc collector, class unloading, footprint và workload cụ thể.

Không nên tuyên bố “JDK 16 trở đi luôn dùng ít metaspace hơn X%” nếu không có benchmark. Elastic Metaspace là cải tiến cơ chế, không phải bảo đảm rằng mọi ứng dụng giảm RSS.

### 5.1. Thay đổi metaspace không tự chứng minh classloader leak

Khi nâng JDK 11 lên 17 và thấy committed metaspace thấp hơn sau chu kỳ tải plugin, điều đó có thể là kết quả của Elastic Metaspace. Ngược lại, nếu metaspace tăng, cần xem class count/class loader lifetime, framework và workload; không kết luận JDK mới làm leak chỉ từ một đường biểu đồ.

### 5.2. Ví dụ vòng đời classloader

~~~text
Startup:
  10 000 classes loaded
  Metaspace grows

Plugin loaded:
  +2 000 classes
  Metaspace grows

Plugin unloaded, no references remain:
  classes may be unloaded in later GC cycles
  metaspace used falls
  committed pages may be uncommitted, depending on JVM/GC
~~~

Nếu một static registry hoặc thread tiếp tục giữ reference đến plugin classloader, việc gọi “unload plugin” theo logic ứng dụng chưa đủ để JVM thực sự gỡ metadata của các class.

## 6. Garbage Collector mặc định có thể thay đổi khi nâng JDK

Một trong những nguồn khác biệt lớn là **GC được chọn**. Không nên giả định JDK mới sử dụng collector cũ nếu launcher không chỉ định rõ.

Các mốc quan trọng:

| Mốc JDK | Thay đổi đáng chú ý | Hệ quả cần kiểm |
|---|---|---|
| JDK 8 | Nhiều deployment HotSpot dùng Parallel GC mặc định ở server-class configuration | Pause, throughput và heap layout là baseline riêng |
| JDK 9 — JEP 248 | G1 trở thành GC mặc định của HotSpot trong cấu hình phổ biến | Hành vi GC và memory footprint có thể khác dù code không đổi |
| JDK 14 — JEP 363 | CMS GC bị loại bỏ | Flag `-XX:+UseConcMarkSweepGC` cũ không còn hợp lệ |
| JDK 15 — JEP 377 | ZGC trở thành production feature | Có thêm lựa chọn GC tối ưu pause thấp |
| JDK 21 — JEP 439 | Generational ZGC được giới thiệu | Cần xác định mode/flag của đúng release |
| JDK 23 — JEP 474 | Generational ZGC trở thành mode mặc định khi chọn ZGC | Không so sánh ZGC cũ và mới như cùng cấu hình |
| JDK 24 — JEP 490 | Bỏ non-generational ZGC | Không dùng cấu hình mode đã bị loại bỏ |

Đây là các mốc HotSpot/OpenJDK để định hướng. Tính khả dụng của collector, default và flag có thể phụ thuộc JDK distribution, platform, architecture, update/build và các lựa chọn startup. **Luôn xác nhận GC thực tế qua startup log hoặc `jcmd`.**

### 6.1. G1 không phải “không có pause”

G1 hướng tới cân bằng throughput và pause với cấu trúc regions, collection sets và các pha concurrent. Nhưng nó vẫn có các pha stop-the-world, và mục tiêu như `-XX:MaxGCPauseMillis` là **mục tiêu mềm**, không phải SLA tuyệt đối.

Nếu trên JDK mới p99 latency tốt hơn nhưng CPU GC tăng, đó là một trade-off cần đo. Nếu heap có nhiều humongous objects, G1 có hành vi riêng cần phân tích từ GC logs.

### 6.2. ZGC không phải câu trả lời mặc định cho mọi workload

ZGC tập trung giảm pause và thực hiện nhiều công việc đồng thời với ứng dụng. Điều đó có thể phù hợp với dịch vụ nhạy latency, nhưng không tự đảm bảo throughput, CPU hay RSS tốt hơn ở mọi tải.

Đặc biệt, bộ nhớ cấp phát nhanh, heap headroom thiếu hoặc CPU cạnh tranh với GC concurrent work đều có thể ảnh hưởng kết quả. Chọn G1, Parallel GC, ZGC hoặc collector khác phải dựa trên **benchmark và mục tiêu vận hành**, không chỉ tên collector.

### 6.3. Shenandoah và collector tùy distribution

Shenandoah có thể sẵn có trên nhiều bản OpenJDK, nhưng không nên giả định mọi build/distribution/platform đều có cùng tập GC options. Cần kiểm tool output và release docs của runtime đích.

## 7. Xác định JVM và GC thật sự đang chạy

Các lệnh kiểm tra thường dùng với HotSpot:

~~~bash
java -version
java -XX:+PrintFlagsFinal -version
java -Xlog:gc -version
~~~

`PrintFlagsFinal` xuất nhiều dòng, nên nên lọc những flag quan trọng khi làm báo cáo. Các JVM không phải HotSpot hoặc các JDK cũ có thể khác option support.

Trong tiến trình đang chạy:

~~~bash
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
~~~

`<pid>` là process ID; thay bằng PID thực tế. Không sao chép literal `<pid>` vào shell nếu chưa thay. Những diagnostic command được hỗ trợ có thể khác theo JDK/collector. Kiểm `jcmd <pid> help` để xem tập command khả dụng.

**Dòng chữ “G1” trên dashboard không đủ nếu môi trường khác đang dùng collector khác.** Khi baseline, ghi lại JVM version, GC name, kích thước heap và startup arguments cho từng deployment.

## 8. GC logging từ Java 8 sang Java 9+

Java 9 đưa vào Unified JVM Logging (JEP 158). Vì thế, các flag logging GC kiểu Java 8 cần được xem xét khi đổi release.

Ví dụ JDK 8 thường gặp:

~~~bash
java -XX:+PrintGCDetails \
     -XX:+PrintGCDateStamps \
     -Xloggc:gc.log \
     -jar application.jar
~~~

Trên JDK 9+ có thể dùng:

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags \
     -jar application.jar
~~~

Nếu cần log rotation theo tùy chọn JVM hỗ trợ:

~~~bash
java "-Xlog:gc*,safepoint:file=gc.log:time,uptime,level,tags:filecount=5,filesize=20m" \
     -jar application.jar
~~~

Quoting phụ thuộc shell; với Windows/PowerShell, cú pháp gọi thực tế cần được điều chỉnh. Không mặc định mọi cờ GC log JDK 8 được runtime mới chấp nhận nguyên vẹn.

### 8.1. Tín hiệu nên trích từ GC logs

- Collector và heap configuration.
- Allocation/evacuation rate, young/mixed/full collections khi có ý nghĩa với GC.
- Pause count, p50/p95/p99 và thời gian pause dài nhất.
- Tỷ lệ thời gian JVM dành cho GC và CPU.
- Heap used trước/sau collection, committed/capacity.
- To-space exhaustion, evacuation failure, concurrent mode failure hoặc các cảnh báo tương ứng.
- Class unloading và metaspace information nếu logging được bật.
- Heap shrinking/uncommit nếu collector hỗ trợ.

Không so số lượng “young GC” giữa hai collector như một đại lượng tương đương tuyệt đối. Chính sách phân vùng và naming khác nhau; hãy so sánh latency, throughput, GC overhead và live set theo mục tiêu chung.

## 9. Memory ergonomics và container awareness

Nhiều Java application được chạy trong Docker, Kubernetes hoặc runtime cgroup. Khi chuyển từ JDK 8 cũ sang JDK hiện đại, JVM có thể **nhận diện giới hạn RAM/CPU của container khác trước**. Điều này ảnh hưởng mặc định heap size, số GC threads, JIT compiler threads và các quyết định sizing.

Các HotSpot JDK mới hỗ trợ cơ chế container awareness; một số JDK 8 update cũng có backport. Không nên đưa ra quy tắc chỉ dựa vào “Java 8” mà bỏ qua update/build.

### 9.1. Vấn đề điển hình: JVM nhìn thấy RAM host thay vì container

Giả sử host có 64 GiB nhưng container bị giới hạn 2 GiB. Trên một runtime cũ hoặc cấu hình không nhận diện đúng cgroup, JVM có thể suy ra memory budget không phù hợp với container.

Hậu quả:

- Max heap mặc định lớn hơn mức container chịu được.
- Số GC threads/worker threads quá nhiều.
- Process bị cgroup OOM kill dù Java không ném `OutOfMemoryError`.
- Một đợt nâng JDK “tình cờ” thay sizing mặc định và làm profile bộ nhớ/CPU khác trước.

Vì vậy, khi so sánh JDK, **đừng giữ nguyên container limit rồi mặc định JVM memory layout cũng giống nhau**.

### 9.2. Xem container settings JVM đang nhận diện

Trong các HotSpot JDK có hỗ trợ logging liên quan:

~~~bash
java -XshowSettings:system -version
java -XshowSettings:vm -version
~~~

Có thể xem container logging khi JDK hỗ trợ tag đó:

~~~bash
java -Xlog:os+container=debug -version
~~~

Lệnh `-XshowSettings`/logging có thể thay đổi chi tiết output theo JDK. Để hiểu chính xác, ghi thông tin cgroup thực tế từ container runtime/Kubernetes và `VM.flags`, không chỉ tin một lệnh.

### 9.3. Cgroup v1/v2 và giới hạn CPU

Một số JDK update khác nhau về mức hỗ trợ cgroup v1 và cgroup v2. Nếu CI chạy trên host cgroup v1 còn production trên cgroup v2, JVM có thể diễn giải CPU/memory quota khác nhau.

Điều này ảnh hưởng:

- Số GC threads.
- Số lượng thread do framework chọn theo `availableProcessors()`.
- Concurrent GC scheduling.
- Default heap sizing.
- Tính ổn định latency khi CPU bị throttling.

Đừng chỉ test trên cùng Docker image mà bỏ qua khác biệt cgroup/host kernel của môi trường triển khai.

## 10. Lập ngân sách container: không để heap chiếm toàn bộ giới hạn

Một công thức **khái niệm** hữu ích:

~~~text
Container memory limit
    >= heap resident budget
     + metaspace / class metadata
     + code cache
     + thread stacks
     + direct / off-heap buffers
     + JNI / FFM / native libraries
     + JVM / GC internal memory
     + OS and container accounting headroom
~~~

Đây không phải phép cộng chính xác của mọi metric vì shared mappings, page accounting và reserved/committed/resident có thể khác nhau. Tuy nhiên, nó nhắc rằng **`-Xmx` không được xem là toàn bộ process memory**.

Ví dụ minh họa ngân sách cho container 2 GiB:

| Hạng mục | Giá trị dự kiến minh họa |
|---|---:|
| Max heap | 1.1 GiB |
| Metaspace + compressed class metadata | 180 MiB |
| Direct/off-heap buffers | 150 MiB |
| Thread stacks/code/JIT/GC/native | 300 MiB |
| Headroom cho biến động/accounting | Phần còn lại |

Các con số trên **không phải khuyến nghị cấu hình cụ thể**. Một service Netty, database driver có native buffer hoặc ứng dụng nhiều thread có thể yêu cầu ngân sách hoàn toàn khác. Đo thực tế trước khi đặt limit.

### 10.1. CPU/memory limit là yêu cầu cho workload, không phải chỉ JVM

Một limit đủ cho startup có thể thiếu khi chạy peak traffic. Test cần có warm-up, concurrency và dữ liệu đại diện, bao gồm đỉnh memory trong khoảng thời gian có batch/compaction/reconfiguration.

Nếu pod bị restart với trạng thái OOMKilled, phải đối chiếu event từ orchestration, cgroup metrics và log JVM. Exit code 137 là tín hiệu thường gặp khi process nhận SIGKILL, nhưng **không đủ một mình để kết luận kernel OOM kill** trong mọi trường hợp.

## 11. Direct buffers và off-heap memory

Java NIO có `ByteBuffer.allocateDirect()` để cấp phát direct buffer mà nội dung được quản lý ngoài heap Java thông thường. Object wrapper và reference tới buffer vẫn thuộc Java heap.

~~~java
import java.nio.ByteBuffer;

ByteBuffer buffer = ByteBuffer.allocateDirect(1024 * 1024);
buffer.putInt(42);
buffer.flip();
System.out.println(buffer.getInt());
~~~

Direct buffers có thể giúp I/O hoặc tương tác native, nhưng footprint không hiển thị đầy đủ trong heap dump. Nếu process RSS tăng mà heap used ổn định, cần xem buffer pools, native allocations và thread stacks.

### 11.1. MaxDirectMemorySize không phải cap của toàn bộ native memory

Tùy JDK/implementation:

~~~bash
java -XX:MaxDirectMemorySize=256m -jar application.jar
~~~

Option này giới hạn một loại direct memory được JVM quản lý; không giới hạn mọi cấp phát trong JNI, FFM, C library, mapped file hoặc native allocator bên thứ ba.

Một hệ thống có thể gặp `OutOfMemoryError: Cannot reserve ... direct buffer memory` hoặc thông báo tương tự dù heap còn dư. Tăng `-Xmx` không giải quyết đúng gốc rễ; đôi khi còn làm container chịu thêm memory pressure.

### 11.2. Đọc BufferPoolMXBeans

~~~java
import java.lang.management.BufferPoolMXBean;
import java.lang.management.ManagementFactory;

for (BufferPoolMXBean pool :
        ManagementFactory.getPlatformMXBeans(BufferPoolMXBean.class)) {
    System.out.printf(
            "%s: count=%d memoryUsed=%d totalCapacity=%d%n",
            pool.getName(),
            pool.getCount(),
            pool.getMemoryUsed(),
            pool.getTotalCapacity());
}
~~~

Có thể thấy những pool như `direct` và `mapped`, tùy runtime. Những chỉ số này hữu ích nhưng **không bao phủ mọi allocation native từ thư viện bên thứ ba**.

## 12. Thread stacks, code cache và native overhead

### 12.1. Số thread lớn có thể tiêu tốn memory đáng kể

Mỗi platform thread thường có stack riêng. JVM option `-Xss` điều chỉnh kích thước stack của Java threads trong phạm vi HotSpot hỗ trợ.

~~~bash
java -Xss1m -jar application.jar
~~~

Đây là cú pháp minh họa, không phải giá trị tối ưu phổ quát. Nếu có hàng nghìn platform threads, phần reservation/commit của stacks và overhead mỗi thread có thể đáng kể. Số byte resident thực tế không đơn giản bằng `thread count × -Xss`, nhưng thread count vẫn là tín hiệu phải theo dõi.

Giảm stack quá thấp có thể gây `StackOverflowError` ở code có call depth lớn. Khi dùng virtual threads trên JDK có hỗ trợ, cơ chế stack/scheduling khác platform threads; không quy chênh lệch footprint thành một phép nhân đơn giản.

### 12.2. JIT code cache

JIT compiler tạo mã máy để tăng tốc code nóng, lưu trong code cache ngoài Java heap. Khi đổi JDK, optimizer, compile policy và code cache use có thể khác.

Một số triệu chứng:

- Warning code cache đầy.
- Hiệu năng giảm vì compiler không thể tiếp tục tối ưu.
- RSS tăng dù heap không tăng.
- Warm-up thay đổi theo JDK hoặc workload.

Cấu hình như `-XX:ReservedCodeCacheSize` cần được xem xét cùng profiler và JDK docs; không tự nâng cap để bỏ warning mà không phân tích.

## 13. Native Memory Tracking (NMT)

HotSpot Native Memory Tracking là công cụ quan trọng khi phải phân biệt heap với native memory. Nó cần được bật **khi khởi động JVM**:

~~~bash
java -XX:NativeMemoryTracking=summary -jar application.jar
~~~

Hoặc với chi tiết sâu hơn:

~~~bash
java -XX:NativeMemoryTracking=detail -jar application.jar
~~~

Chế độ chi tiết có thể tăng overhead và lượng dữ liệu thu thập; nên dùng có kế hoạch, nhất là trong môi trường production.

### 13.1. Xem NMT bằng jcmd

Sau khi tìm đúng PID:

~~~bash
jcmd <pid> VM.native_memory summary scale=MB
~~~

NMT có thể chia memory thành các nhóm như Java Heap, Class, Thread, Code, GC, Compiler, Internal và những nhóm khác; tên nhóm và accounting có thể thay đổi theo release.

Nếu muốn đo chênh lệch trong một khoảng hoạt động:

~~~bash
jcmd <pid> VM.native_memory baseline
# Chạy một workload hoặc một chu kỳ tạo/gỡ plugin.
jcmd <pid> VM.native_memory summary.diff scale=MB
~~~

Ở chế độ detail có thể dùng thống kê chi tiết và diff tương ứng nếu JVM hỗ trợ. Luôn kiểm `jcmd <pid> help VM.native_memory` trên release thực tế.

### 13.2. Giới hạn của NMT

- NMT có overhead nên không phải lúc nào cũng nên bật detail thường trực.
- NMT không nhất thiết bao phủ đầy đủ allocation do bên thứ ba dùng `malloc`, native library hoặc external allocator.
- NMT category không thể luôn cộng trực tiếp với RSS/cgroup usage.
- Một số vùng reserved có thể rất lớn nhưng không resident.
- NMT summary tăng không chứng minh memory leak nếu workload còn warm-up hoặc có cache hữu ích.

Khi NMT không giải thích được RSS, có thể cần OS tools, allocator profiling, heap/native profiler hoặc vendor-specific diagnostics.

## 14. MemoryMXBean, MemoryPoolMXBean và class loading metrics

Một service có thể xuất metric dựa trên Java Management API:

~~~java
import java.lang.management.ClassLoadingMXBean;
import java.lang.management.ManagementFactory;
import java.lang.management.MemoryMXBean;
import java.lang.management.MemoryPoolMXBean;
import java.lang.management.MemoryUsage;

public final class JvmMemorySnapshot {
    public static void main(String[] args) {
        MemoryMXBean memory =
                ManagementFactory.getMemoryMXBean();

        MemoryUsage heap = memory.getHeapMemoryUsage();
        MemoryUsage nonHeap = memory.getNonHeapMemoryUsage();

        System.out.println("Heap used: " + heap.getUsed());
        System.out.println("Heap committed: " + heap.getCommitted());
        System.out.println("Heap max: " + heap.getMax());
        System.out.println("Non-heap used: " + nonHeap.getUsed());

        for (MemoryPoolMXBean pool :
                ManagementFactory.getMemoryPoolMXBeans()) {
            MemoryUsage usage = pool.getUsage();
            if (usage != null) {
                System.out.printf("%s used=%d committed=%d%n",
                        pool.getName(),
                        usage.getUsed(),
                        usage.getCommitted());
            }
        }

        ClassLoadingMXBean classes =
                ManagementFactory.getClassLoadingMXBean();

        System.out.println("Loaded classes: "
                + classes.getLoadedClassCount());
        System.out.println("Total loaded classes: "
                + classes.getTotalLoadedClassCount());
        System.out.println("Unloaded classes: "
                + classes.getUnloadedClassCount());
    }
}
~~~

Các giá trị thuộc API tiêu chuẩn, nhưng cách JVM phân vùng memory pool và tên pool có thể khác collector/JDK. `getMax()` có thể trả giá trị âm nếu maximum không xác định.

### 14.1. Ý nghĩa khi đọc metrics

- Heap used gần `-Xmx` trong một khoảng ngắn chưa đủ kết luận OOM sắp xảy ra.
- Non-heap used không đồng nghĩa tổng native RSS.
- Loaded class count tăng khi startup/warm-up là bình thường.
- Total loaded chỉ tăng theo lịch sử, không phải số class đang sống.
- Unloaded count tăng là dấu hiệu đã gỡ một số class, nhưng không xác nhận plugin không còn giữ reference nào khác.

Để đánh giá leak, cần đo trong một chuỗi workload tương đương có đủ thời gian warm-up và collection.

## 15. jcmd, JFR và heap dump cho điều tra có kiểm soát

Một số lệnh HotSpot hay dùng:

~~~bash
jcmd <pid> GC.heap_info
jcmd <pid> VM.metaspace
jcmd <pid> GC.class_histogram
jcmd <pid> Thread.print
jcmd <pid> VM.flags
~~~

Không phải mọi JVM/version đều hỗ trợ cùng tên diagnostic command hoặc cấu hình. Dùng `jcmd <pid> help` để xác nhận. Một số thao tác như class histogram, heap dump hoặc GC trigger có thể gây safepoint, tốn CPU/RAM, làm giảm hiệu năng; không chạy tùy tiện trên production peak traffic.

### 15.1. Heap dump

Có thể cấu hình dump khi Java heap OOME trong những JDK hỗ trợ:

~~~bash
java -XX:+HeapDumpOnOutOfMemoryError \
     -XX:HeapDumpPath=/secure/dumps \
     -jar application.jar
~~~

Hoặc tạo dump có chủ đích:

~~~bash
jcmd <pid> GC.heap_dump /secure/dumps/heap.hprof
~~~

Heap dump có thể chứa password, token, dữ liệu khách hàng, payload và những object nhạy cảm. Phải kiểm quyền truy cập, dung lượng đĩa, thời gian giữ file và quy trình xử lý dữ liệu.

Heap dump rất hữu ích cho **object retention** nhưng không hiển thị đầy đủ toàn bộ native/off-heap memory.

### 15.2. Java Flight Recorder

JFR cung cấp dữ liệu liên quan đến GC, allocation, class loading, thread, safepoint và nhiều sự kiện runtime khác. Ví dụ:

~~~bash
jcmd <pid> JFR.start \
    name=memory-investigation \
    settings=profile \
    duration=5m \
    filename=/secure/recordings/memory.jfr
~~~

Cú pháp chi tiết phụ thuộc JDK và cấu hình. Xác minh bằng `jcmd <pid> help JFR.start`. JFR giúp liên hệ memory pressure với allocation hotspots và GC pauses nhưng vẫn cần chọn thời gian ghi phù hợp và đánh giá overhead.

### 15.3. Không dùng System.gc() làm bằng chứng duy nhất

Gọi `System.gc()` không bảo đảm JVM sẽ thực hiện đầy đủ một kiểu collection cố định. Hành vi phụ thuộc collector, flag và release. Kể cả nếu một lần gọi làm heap giảm, điều đó cũng không chứng minh không có leak.

Để đánh giá live set, dùng GC log, heap dump, workload ổn định và nhiều chu kỳ quan sát thay vì một lần ép GC rồi so hai số.

## 16. Phân biệt các kiểu OutOfMemoryError và việc bị OS kill

| Triệu chứng | Vùng/lớp nguyên nhân đáng nghi | Phép kiểm ưu tiên |
|---|---|---|
| `OutOfMemoryError: Java heap space` | Heap thiếu hoặc object retention cao | Heap dump, GC log, allocation/live set |
| `OutOfMemoryError: GC overhead limit exceeded` | Collector tiêu nhiều thời gian mà thu hồi rất ít, khi chính sách này áp dụng | GC logs, allocation, live set, heap sizing |
| `OutOfMemoryError: Metaspace` | Class metadata giới hạn hoặc classloader retention | `VM.metaspace`, class count/loaders, JFR |
| `OutOfMemoryError: Compressed class space` | Phần class metadata dành cho compressed class space | Metaspace diagnostics, class loading |
| Direct buffer memory OOME | Giới hạn hoặc thiếu direct memory | Buffer pool metrics, direct memory config |
| Unable to create native thread | Thiếu OS resource, memory, thread/process limit | Thread counts, stack settings, ulimit/container |
| Container OOMKilled | Tổng memory cgroup vượt limit hoặc cơ chế quản lý OS kill process | Kubernetes events, cgroup/OS metrics, JVM logs |
| Process RSS tăng nhưng heap ổn định | Metaspace, direct/native, thread stacks, code cache, mmap | NMT, OS metrics, buffer pools, class metrics |

Một số thông báo thay đổi theo runtime. Không phải mọi process bị kill đều có Java OOME; kernel có thể dừng tiến trình trước khi JVM kịp tạo heap dump.

## 17. Case study A: heap giảm nhưng container vẫn OOMKilled

**Bối cảnh giả định:**

- Ứng dụng nâng từ JDK cũ lên JDK mới.
- Dashboard báo heap used sau GC thấp hơn.
- Container memory limit giữ nguyên.
- Sau giờ cao điểm, pod bị OOMKilled.

### 17.1. Giả thuyết cần kiểm

1. `-Xmx` mới tính theo cgroup khác baseline.
2. Thread count tăng do framework hoặc CPU ergonomics.
3. Direct buffers hoặc native SDK tăng.
4. Metaspace/class loading tăng do framework/proxy mới.
5. JIT/code cache hoặc GC internal overhead thay đổi.
6. RSS gồm những trang heap committed mà dashboard chỉ hiển thị heap used.
7. Thay đổi native library, allocator hoặc memory mapping.
8. Tải và concurrency ở giờ cao điểm không giống baseline.

### 17.2. Phương án điều tra

~~~text
Collect:
  - JDK version/vendor/build and GC
  - Effective -Xmx and cgroup memory limit
  - Heap used/committed/max
  - Metaspace and class counts
  - Thread count and stack config
  - Direct buffer pool metrics
  - NMT summary where enabled
  - Process RSS and container memory accounting
  - Peak traffic/time correlation
~~~

Nếu heap used thấp nhưng direct memory/native allocation tăng, tăng `-Xmx` thường không phải giải pháp. Có thể cần sửa buffer lifecycle, giới hạn concurrency hoặc cập nhật thư viện native.

## 18. Case study B: Metaspace OOME sau nhiều lần redeploy plugin

**Bối cảnh giả định:** một hệ thống plugin tạo class loader mới cho mỗi bản plugin. Sau mỗi lần reload, heap vẫn giảm nhưng metaspace và loaded class count tăng cho đến khi OOME.

Các nguyên nhân cần xem:

- Static singleton giữ reference tới class từ plugin cũ.
- Thread nền chưa stop, context class loader vẫn trỏ plugin.
- Registry/listener/callback không được unregister.
- ThreadLocal giữ value hoặc class loader.
- Framework cache lưu `Class`, proxy hoặc generated class.
- Một dependency tạo class loaders liên tục mà không đóng lifecycle.

### 18.1. Cách xử lý

1. Đo số class loaders và class đang sống qua từng chu kỳ reload.
2. Tìm GC roots/references giữ class loader bằng heap dump và profiler.
3. Hủy thread, unregister listener, clear cache và close resource đúng vòng đời.
4. Xác nhận class unloading thực sự diễn ra.
5. Kiểm lại metaspace used/committed và RSS qua nhiều chu kỳ.
6. Sau đó mới điều chỉnh `MaxMetaspaceSize` nếu cần headroom phù hợp.

**Tăng metaspace cap không thay thế sửa classloader leak.** Elastic Metaspace chỉ có thể thu hồi phần metadata rảnh; class loader còn reachable thì metadata liên quan vẫn cần tồn tại.

## 19. Case study C: thay đổi GC mặc định làm p99 latency khác

**Bối cảnh giả định:** dịch vụ JDK 8 chuyển sang JDK 17, không chỉ định GC. Trước đó JVM cũ thường dùng Parallel GC, còn JDK mới dùng G1 theo mặc định HotSpot thông dụng.

Khi so sánh, có thể thấy:

- Stop-the-world pause pattern khác.
- GC CPU overhead khác.
- Kích thước young/old regions khác.
- Throughput và p99 latency thay đổi.
- Heap committed và memory after GC khác.

### 19.1. Cách đánh giá đúng

Cần hai dạng thí nghiệm:

- **So sánh mặc định**: giữ workload, container, JVM knobs cơ bản tương đương để biết hành vi upgrade thực tế.
- **So sánh có kiểm soát**: thử collector/heap headroom khác phù hợp support policy để xác định lựa chọn tối ưu.

Đừng kết luận “G1 chậm hơn Parallel GC” từ một workload hay một sample. Chọn collector theo p99 latency, throughput, GC CPU, RSS và tính ổn định trong các mức tải.

## 20. JFR và GC logs: đọc allocation pressure khác memory leak

Hai hệ thống có thể cùng dùng 1 GiB heap nhưng mang profile rất khác:

| Dạng biểu đồ | Diễn giải ban đầu | Kiểm tra tiếp |
|---|---|---|
| Heap tăng giữa GC rồi giảm về đáy ổn định | Allocation bình thường dưới tải ổn định | GC overhead và latency |
| Đáy sau GC tăng dần qua nhiều chu kỳ tương đương | Có khả năng retained objects tăng | Heap dump diff, allocation site, GC roots |
| RSS tăng trong khi heap used và committed ổn định | Native/off-heap/thread/metaspace/mapped | NMT, OS, buffer pools |
| Metaspace used tăng theo số plugin/class loader | Class loading hoặc retention | Class unloading và loader lifetime |
| GC rất thường xuyên, pause ngắn, throughput kém | Heap nhỏ hoặc allocation rate cao | Allocation profiling, heap sizing, GC options |
| Ít GC nhưng pause rất dài khi memory pressure | Collector/workload/heap headroom không phù hợp | GC log phases, safepoints, load |
| Sau startup RSS tăng rồi ổn định | Warm-up, class loading, JIT, caches | Quan sát đủ thời gian trước khi kết luận leak |

Để gọi là **memory leak**, cần chứng cứ về tài nguyên không được giải phóng theo kỳ vọng, không chỉ một đường memory tăng trong vài phút warm-up.

## 21. Thiết kế phép so sánh trước–sau nâng JDK

Một phép benchmark tốt phải kiểm soát biến và trả lời câu hỏi cụ thể.

### 21.1. Giữ nguyên các yếu tố nền khi có thể

- Cùng source commit và artifact, nếu binary có thể chạy trên cả hai JDK.
- Cùng dependency graph và schema.
- Cùng request mix, input dataset và concurrency.
- Cùng container memory/CPU limit.
- Cùng OS/architecture và cgroup mode nếu có thể.
- Cùng warm-up và thời gian đo.
- Cùng chính sách log/monitoring.
- Cùng khoảng tải nền từ database/external services.

Nếu phải nâng framework cùng JDK vì compatibility, báo cáo cần ghi rõ **đang so sánh hai stack**, không gán toàn bộ khác biệt cho JVM.

### 21.2. Bộ metric tối thiểu

| Nhóm | Metric cần lưu |
|---|---|
| Service | Throughput, error rate, p50/p95/p99 latency |
| GC | Collector, pause count/duration, GC CPU/time, full GC |
| Heap | Used/committed/max, live-set trend, allocation rate |
| Metaspace | Used/committed, class loaded/unloaded, class loader count khi có |
| Native | RSS, NMT summary, direct buffers, thread count, code cache |
| Container | Memory working set/usage, cgroup limit, OOM events, CPU throttling |
| Runtime | JDK feature/update/vendor, flags, OS/arch, container image |
| Stability | Restart, OOME, native crash, long safepoints |

Dữ liệu nên được thu trong nhiều lần chạy để tránh kết luận từ biến động ngẫu nhiên. Các metric cần cùng định nghĩa và đơn vị khi so sánh, đặc biệt khi đổi GC.

### 21.3. Định nghĩa tiêu chí go/no-go trước khi chạy

Ví dụ định hướng:

~~~text
Baseline:
  Java 17, G1, container 4 GiB
Candidate:
  Java 21, G1, cùng workload và giới hạn

Chỉ tiêu:
  - p99 latency không vượt ngưỡng SLO
  - Không có OOMKilled/OOME trong thử tải đại diện
  - Peak RSS không vượt memory budget và headroom
  - GC pause/CPU nằm trong ngân sách
  - Metaspace và classloader count ổn định sau warm-up
  - Không có regression chức năng/dữ liệu
~~~

Đây là ví dụ tiêu chí, không phải kết quả kiểm thử của một ứng dụng có thật. Ngưỡng số phải lấy từ SLO và resource budget của dự án.

## 22. Cấu hình JVM theo môi trường thay vì sao chép flags cũ

Một startup command kiểu JDK 8 có thể chứa rất nhiều cờ GC, PermGen và logging lịch sử:

~~~text
-XX:+UseConcMarkSweepGC
-XX:MaxPermSize=256m
-XX:+PrintGCDetails
-Xloggc:/logs/gc.log
~~~

Khi lên JDK 17/21/25, một số cờ đã bị xóa, obsolete hoặc có cách logging thay thế. **Không sao chép nguyên bộ cờ cũ rồi cho qua warning.**

Quy trình:

1. Lưu tất cả JVM options hiện tại và mục đích từng option.
2. Phân loại heap sizing, metaspace, GC selection, logging, diagnostics, native access và security.
3. Đối chiếu option support của JDK mục tiêu.
4. Bỏ cờ không còn hợp lệ, đổi logging sang Unified Logging nếu cần.
5. Bắt đầu với ít tuning hơn nếu có cơ sở thử nghiệm.
6. Đo baseline với defaults phù hợp.
7. Thêm tuning chỉ khi có vấn đề đã đo và giả thuyết rõ.
8. Lưu mỗi thay đổi cờ và kết quả thử nghiệm.

Tuning hiệu quả trên JDK 8 không tự phù hợp với collector và ergonomics của JDK 21. Các thay đổi nhỏ về JVM flag có thể làm phân tích regression trở nên khó khăn khi chúng được gộp với nâng dependency và schema.

## 23. Ví dụ cấu hình cho service trong container

Một cấu hình minh họa ở JDK hiện đại:

~~~bash
java \
  -Xms512m \
  -Xmx1536m \
  -XX:+UseG1GC \
  -XX:+HeapDumpOnOutOfMemoryError \
  -XX:HeapDumpPath=/secure/dumps \
  "-Xlog:gc*:file=/secure/logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20m" \
  -jar application.jar
~~~

**Không coi các giá trị trên là khuyến nghị áp dụng sẵn.** Cần đủ ngân sách cho metaspace, direct/native buffers, thread stacks và GC internals. Nếu chọn giới hạn container 2 GiB mà đặt heap 1.5 GiB, có thể vẫn thiếu headroom cho một ứng dụng nhiều thread hoặc dùng nhiều native memory.

Khi có thể, xác nhận cờ thực tế bằng `jcmd <pid> VM.flags` và startup logs. Một container entrypoint hoặc nền tảng triển khai có thể thêm/ghi đè JVM args.

## 24. Sự cố thường bị diễn giải sai

**“Heap used thấp nên process không thể bị OOM.”** Sai. Tổng RSS/cgroup usage còn có metaspace, stacks, direct memory, native allocations và overhead.

**“Đặt `-Xmx` bằng container limit sẽ tận dụng hết RAM.”** Dễ gây OOMKilled vì thiếu headroom ngoài heap.

**“Reserved memory bằng RAM đã dùng.”** Sai. Reserved có thể chỉ là vùng địa chỉ ảo; phải xem committed/resident.

**“Heap tăng dần nghĩa là leak.”** Không nhất thiết; có thể do warm-up, cache có giới hạn hoặc allocation bình thường.

**“Metaspace OOME thì cứ tăng MaxMetaspaceSize.”** Có thể che classloader leak hoặc class generation không kiểm soát.

**“PermGen flags vẫn điều khiển metaspace trên Java mới.”** Không. PermGen đã được thay bằng metaspace từ Java 8.

**“Elastic Metaspace luôn giúp mọi ứng dụng giảm RAM.”** Không. Lợi ích phụ thuộc workload và việc metadata có được giải phóng hay không.

**“JDK mới dùng cùng GC cũ khi không có flag.”** Không thể mặc định; HotSpot đổi default GC từ JDK 9 trong cấu hình phổ biến.

**“MaxGCPauseMillis là giới hạn pause tuyệt đối.”** Không. Đó là mục tiêu mềm của các collector phù hợp.

**“ZGC luôn nhanh hơn G1.”** Tùy workload, CPU, heap headroom, throughput và SLO.

**“MaxDirectMemorySize giới hạn mọi native allocation.”** Không. JNI/FFM và malloc của thư viện ngoài có thể không chịu cùng cap.

**“GC heap dump đủ để điều tra RSS tăng.”** Không. Heap dump không bao phủ đầy đủ native/off-heap.

**“NMT cho thấy tất cả native allocations.”** Không hoàn toàn; nhiều allocation bên ngoài JVM allocator có thể cần native profiler.

**“Pod exit 137 chắc chắn là Java OOME.”** Không. Cần OS/container event và log để xác định nguyên nhân.

**“CI test pass thì memory production an toàn.”** Tải, cgroup, container limit và warm-up có thể khác.

## 25. Checklist migration JVM memory

- [ ] Đã ghi JDK feature/update/build, vendor và OS/architecture nguồn/đích.
- [ ] Đã kiểm GC thực tế và cờ JVM của từng môi trường.
- [ ] Đã phân biệt heap used/committed/reserved với RSS/container memory.
- [ ] Đã ghi `-Xms`, `-Xmx` và phần trăm RAM nếu dùng.
- [ ] Đã để headroom cho metaspace, thread stacks, direct/native memory và code cache.
- [ ] Đã đối chiếu container cgroup limits, CPU quota và JVM container awareness.
- [ ] Đã kiểm JDK/GC option obsolete hoặc removed; không giữ cờ CMS cũ.
- [ ] Đã chọn GC dựa trên latency/throughput/RSS, không chỉ mặc định lịch sử.
- [ ] Đã dùng GC logs theo cú pháp hỗ trợ của JDK đích.
- [ ] Đã quan sát metaspace, class counts và classloader lifecycle.
- [ ] Đã xem xét tác động Elastic Metaspace với workload có unload class.
- [ ] Đã kiểm direct buffer pools và native allocations khi RSS khác heap.
- [ ] Đã kiểm thread count, `-Xss`, code cache và native libraries.
- [ ] Đã kích hoạt NMT nếu cần và hiểu overhead/giới hạn công cụ.
- [ ] Đã có kế hoạch JFR, heap dump và quyền truy cập dữ liệu nhạy cảm.
- [ ] Đã phân biệt Java OOME với kernel/container OOMKilled.
- [ ] Đã chạy benchmark có warm-up, tải đại diện và nhiều lần đo.
- [ ] Đã lưu p95/p99 latency, throughput, GC pauses, peak RSS và cgroup events.
- [ ] Đã ghi rõ ảnh hưởng của những thay đổi dependency/framework ngoài JDK.
- [ ] Đã có tiêu chí go/no-go, rollout và rollback/roll-forward nếu gặp regression.
- [ ] Những môi trường chưa kiểm đã được đánh dấu, không mặc định PASS.

## 26. Tài liệu tham khảo chính thức để đối chiếu theo JDK

Các nguồn tham khảo về thay đổi của HotSpot và GC:

- **JEP 122 — Remove the Permanent Generation (Java 8):** https://openjdk.org/jeps/122
- **JEP 158 — Unified JVM Logging (Java 9):** https://openjdk.org/jeps/158
- **JEP 248 — Make G1 the Default Garbage Collector (Java 9):** https://openjdk.org/jeps/248
- **JEP 363 — Remove the Concurrent Mark Sweep (CMS) Garbage Collector (Java 14):** https://openjdk.org/jeps/363
- **JEP 377 — ZGC: A Scalable Low-Latency Garbage Collector (Java 15):** https://openjdk.org/jeps/377
- **JEP 387 — Elastic Metaspace (Java 16):** https://openjdk.org/jeps/387
- **JEP 439 — Generational ZGC (Java 21):** https://openjdk.org/jeps/439
- **JEP 474 — ZGC: Generational Mode by Default (Java 23):** https://openjdk.org/jeps/474
- **JEP 490 — ZGC: Remove the Non-Generational Mode (Java 24):** https://openjdk.org/jeps/490
- **Java SE `java`/`jcmd` tool documentation:** sử dụng bản tài liệu đúng với JDK target trên https://docs.oracle.com/en/java/javase/

Các link trên hỗ trợ xác định mốc thay đổi; khi triển khai thật, vẫn cần đối chiếu bản phân phối, GC flags và cập nhật của đúng JDK đã chọn. Không lấy thông số benchmark của một JEP làm kết quả đo cho hệ thống riêng.

## Kết luận

**Heap, metaspace và bộ nhớ native là những vùng khác nhau, và hành vi quản lý chúng có thể thay đổi đáng kể sau khi nâng JDK.** Từ thay đổi default G1, việc loại bỏ CMS, cải tiến Elastic Metaspace đến ZGC và container ergonomics, JVM mới có thể đổi GC pause, heap commitment, khả năng trả metadata về OS hoặc cách tính memory budget — ngay cả khi mã nghiệp vụ không đổi.

Để đánh giá tương thích hiệu năng, phải đo **heap used/committed/max, metaspace, direct/native memory, thread stacks, RSS, GC và giới hạn container** theo cùng workload. Khi gặp OOM, xác định đúng loại: Java heap, metaspace, direct buffer, native thread hay cgroup OOMKilled; mỗi loại đòi cách chẩn đoán và sửa khác nhau. Kết luận cuối cùng cần dựa trên SLO, peak RSS, GC behavior, tính ổn định dưới tải, và bằng chứng có thể tái lập theo từng JDK — không chỉ một biểu đồ heap hoặc một cờ JVM sao chép từ phiên bản cũ.
