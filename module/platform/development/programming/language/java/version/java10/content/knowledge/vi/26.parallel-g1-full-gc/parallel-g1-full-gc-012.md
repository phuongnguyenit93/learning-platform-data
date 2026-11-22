# Ưu tiên xác định nguyên nhân Full GC trước khi điều chỉnh tham số (G1, Java 10+)

## 1. Vấn đề cần giải quyết

Thấy một dòng **Pause Full** trong GC log không có nghĩa bước tiếp theo luôn phải là tăng **-Xmx**, giảm **-XX:MaxGCPauseMillis** hoặc tăng **-XX:ParallelGCThreads**. Các tùy chọn này giải quyết những bài toán khác nhau. Nếu Full GC là kết quả của **System.gc()** do ứng dụng gọi, chỉnh ngưỡng marking không nhất thiết giúp ích. Nếu Full GC lặp lại vì heap chứa quá nhiều object còn sống, tăng số worker GC không khiến những object đó trở thành garbage.

**Nguyên tắc:** Xác nhận sự kiện → thu thập bằng chứng → xác định giả thuyết nguyên nhân → chọn biện pháp phù hợp → đo lại cùng workload. Không chuyển thẳng từ một triệu chứng sang một bộ JVM flags được truyền miệng.

Bài thuộc chủ đề **G1 Full GC song song** trong **Java 10**. **JEP 307** từ Java 10 đã giúp G1 thực hiện Full GC bằng **nhiều GC worker threads** để giảm worst-case latency. Nhưng Full GC vẫn **stop-the-world (STW)**: application threads phải dừng. Công việc song song trong GC không đồng nghĩa công việc thu gom diễn ra concurrent với ứng dụng.

Nội dung vẫn áp dụng với các HotSpot/JDK hiện đại, như **JDK 17, JDK 21 và JDK 25**. Phần thực hành sử dụng Java 17+; cách ghi GC log dùng **Unified GC Logging (-Xlog)**, không khuyến nghị những GC logging flags cũ đã bị thay thế.

Sau khi học, bạn có thể:
- Nhận diện Full GC và phân biệt nó với Young/Mixed GC.
- Phân biệt **cause** với **symptom**.
- Đọc chuỗi các sự kiện theo GC ID và thời gian.
- Đặt giả thuyết về evacuation failure, concurrent marking, humongous object, high live set, explicit GC hoặc native/container memory.
- Chọn hành động đúng: sửa code/lifetime, thay giới hạn tài nguyên hay thử một JVM flag.
- Dùng một chương trình Java 17+ độc lập để luyện đọc GC log giả lập và nhận biết giới hạn của dữ liệu.

## 2. Full GC trong chu trình G1

G1 chia Java heap thành nhiều **regions**. Chúng có thể được dùng cho Eden, Survivor, Old, Humongous hoặc Free. Young GC xử lý phần lớn object trẻ; Mixed GC có thể xử lý thêm các old regions được chọn. G1 cũng chạy **concurrent marking** để có thông tin về object sống ở Old.

Trong young/mixed evacuation, object còn sống thường được **di chuyển sang destination regions**; vùng nguồn được thu hồi nếu quá trình thành công.

| Sự kiện G1 | Công việc chính | Có phải Full GC? |
| --- | --- | --- |
| Pause Young (Normal) | Thu gom young collection set | Không |
| Pause Young (Concurrent Start) | Young GC, bắt đầu marking | Không |
| Concurrent Mark Cycle | Xác định live objects ở Old | Không |
| Pause Remark, Pause Cleanup | Các giai đoạn có pause của marking | Không |
| Pause Young (Mixed) | Young và một số old regions | Không |
| Pause Full | Thu gom/compact toàn heap | **Có** |

Young và Mixed GC cũng có **STW pauses**, vì vậy thấy ứng dụng bị dừng không đủ để nói đã có Full GC. Cần tìm đúng **Pause Full**.

Một chuỗi thiếu bộ nhớ điển hình:

~~~text
Allocation / promotion tăng nhanh
                │
                ▼
Old occupancy tăng, Free regions giảm
                │
                ▼
Marking / Mixed GC chưa dọn kịp
                │
                ▼
Evacuation thiếu destination space
                │
                ▼
G1 cố tiếp tục thu gom
                │
                ├─ Thu hồi đủ → tiếp tục
                └─ Không đủ → Full GC có thể xảy ra
                                   │
                                   ├─ Có chỗ → tiếp tục
                                   └─ Không đủ → có thể OutOfMemoryError
~~~

Đây là **mô hình tình huống**, không phải máy trạng thái bắt buộc trong mọi JDK. G1 vẫn có thể Full GC vì explicit request hoặc một cơ chế khác mà không đi qua toàn bộ chuỗi này.

## 3. Bước đầu tiên là xác định tác động thật

Trước khi đọc GC log, hãy biết vì sao cần can thiệp:
- Người dùng gặp **request timeout** hay p99 latency tăng?
- Batch hoàn tất chậm hơn? Dịch vụ fail readiness? Container restart?
- Sự cố chỉ trên một instance hay trên nhiều instance?
- Có thay phiên bản ứng dụng, traffic, payload, batch size, JDK hoặc container quota gần đây không?
- Mục tiêu là giảm **pause thời gian thực**, tránh OOM, tăng throughput hay giữ memory footprint?

Ví dụ bảng incident tối thiểu:

| Thông tin | Mục đích |
| --- | --- |
| JDK vendor/version/build | Phân biệt GC heuristics và format log |
| GC collector và VM flags | Xác nhận thật sự dùng G1 |
| Heap size và container limit | Đánh giá headroom |
| GC ID, cause, pause duration | Xác nhận Full GC |
| Heap occupied trước/sau | Đo lượng reclaim |
| Old/Humongous region count | Phân tích fragmentation/pressure |
| Allocation/promotion rate | Liên hệ với tốc độ tạo dữ liệu |
| Workload, queue, cache | Tìm nguyên nhân ở ứng dụng |
| p95/p99 latency, CPU, throughput | Đo thành công của thay đổi |

**Đừng chỉ tối ưu Full GC count.** Một cấu hình có ít Full GC nhưng CPU tăng cao, Young GC kéo dài hoặc throughput giảm vẫn có thể làm dịch vụ tệ hơn.

## 4. Thu thập bằng chứng bằng Unified GC Logging

Trên HotSpot JDK 17+, ví dụ bật GC logging khi khởi động một JAR:

~~~bash
java -XX:+UseG1GC -Xlog:gc*=info:file=g1.log:time,uptime,level,tags:filecount=5,filesize=20M -jar app.jar
~~~

Đây là lệnh **minh họa**. Nó cần một JAR có thật và quyền ghi file log. Giữ timestamp, uptime, level, tags giúp ghép sự kiện GC với application logs. File rotation được cấu hình để tránh log tăng mãi.

Trong một lần phân tích sâu, có thể dùng:

~~~bash
java -XX:+UseG1GC -Xlog:gc*=debug:file=g1-debug.log:time,uptime,level,tags:filecount=5,filesize=20M -jar app.jar
~~~

**Không bật debug/trace rộng trong benchmark chính**: log có overhead CPU/I/O và có thể làm sai lệch số đo. Các flags này là của **HotSpot**, không mặc định mọi Java SE JVM đều hỗ trợ giống nhau.

Nếu có **jcmd** phù hợp và đủ quyền, một số lệnh xem process thật:

~~~text
jcmd -l
jcmd <pid> VM.version
jcmd <pid> VM.flags
jcmd <pid> GC.heap_info
~~~

Thay **<pid>** bằng PID thực. Những lệnh này phụ thuộc quyền truy cập/attach policy và có thể gây overhead. Chúng không thay thế GC log theo thời gian; **GC.heap_info** chỉ là ảnh chụp tại một thời điểm.

Những lệnh nặng như **GC.heap_dump** hoặc **GC.class_histogram** có thể gây safepoint/GC, chiếm nhiều CPU/disk hoặc mang dữ liệu nhạy cảm. Chỉ chạy khi được phép, có đánh giá tác động và bảo vệ artifact phù hợp.

Ngoài GC log, ghép thêm:
- Request/batch volume, queue length, cache size;
- Allocation rate và retained objects nếu có profiling phù hợp;
- CPU throttling/container memory limits;
- Lỗi OutOfMemoryError và container OOM events;
- Latency p95/p99 và throughput.

## 5. Xác nhận Pause Full và đọc đúng ý nghĩa

Một ví dụ **giả lập hình thức GC log**:

~~~text
[12.345s][info][gc] GC(72) Pause Full (G1 Compaction Pause) 980M->945M(1024M) 430.0ms
~~~

Giải thích:
- **GC(72):** mã để liên kết các dòng chi tiết cùng sự kiện.
- **Pause Full:** sự kiện Full GC thật.
- **G1 Compaction Pause:** loại công việc, chưa phải root cause.
- **980M->945M(1024M):** heap used trước/sau, capacity hiện tại.
- **430.0ms:** pause duration.

Từ ví dụ, GC reclaim khoảng **35 MiB** nhưng sau thu gom heap vẫn gần đầy. Điều này gợi ý **live set/retention cao**; không đủ bằng chứng tự kết luận memory leak.

Các mẫu quan trọng:

| Mẫu log | Có thể biết | Chưa thể kết luận |
| --- | --- | --- |
| **Pause Full** | Có Full GC | Mọi Full GC đều do heap hết chỗ |
| **Pause Young (Mixed)** | Mixed GC | Đây là Full GC |
| **Pause Remark** | Một pause marking | Đây là Full GC |
| **To-space exhausted** | Evacuation có vấn đề destination space ở một số JDK | Full GC xuất hiện ngay sau |
| **Evacuation Failure: Allocation** | Evacuation thiếu vùng đích | Chắc chắn memory leak |
| **Evacuation Failure: Pinned** | Pinning cản trở relocation | Cùng nguyên nhân với thiếu chỗ |
| **G1 Humongous Allocation** | Có hoạt động GC liên quan object lớn | Sự kiện này tự là Full GC |
| **System.gc()** | Có explicit request/cause | Heap chắc chắn gần đầy |

**Đặc biệt:** dòng **Pause Young (Concurrent Start) (G1 Humongous Allocation)** là Young GC, không phải Full GC.

## 6. Tái dựng một timeline thay vì nhìn một dòng

Ví dụ chuỗi **giả định**:

~~~text
T-30s  Old regions tăng đều
T-12s  Concurrent marking khởi động
T-2s   Evacuation Failure: Allocation
T      Pause Full (G1 Compaction Pause)
T+1s   Heap sau Full vẫn gần capacity
~~~

Giả thuyết phù hợp là lượng object sống/promotion tăng nhanh hơn khả năng reclaim của G1. Nhưng vẫn cần đọc số liệu các regions, GC causes và workload để xác minh.

Một chuỗi khác:

~~~text
T-10s  Heap vẫn còn headroom
T-1s   Agent hoặc tác vụ quản trị gửi explicit GC request
T      Pause Full (System.gc())
T+1s   Ứng dụng tiếp tục bình thường
~~~

Trường hợp này nên điều tra **caller/agent**, không mặc định tăng heap hoặc chỉnh IHOP.

G1 marking có thể kéo dài qua nhiều lần Young GC, nên điều tra cả khoảng thời gian đủ dài, không chỉ vài dòng sát sự kiện.

## 7. Nhóm nguyên nhân A — Evacuation failure và thiếu to-space

Trong một Young/Mixed collection, G1 phải copy các object sống sang Survivor hoặc Old destination regions. Nếu không tìm đủ vùng đích, **evacuation failure** có thể xảy ra.

Dấu hiệu tùy JDK:

~~~text
To-space exhausted
Evacuation Failure: Allocation
~~~

Các yếu tố thường liên quan:
- Free regions ít;
- Object trẻ sống sót nhiều, promotion cao;
- Old occupancy quá cao;
- Concurrent marking/mixed collection chưa dọn đủ;
- Allocation spike hoặc live set tăng;
- Humongous regions chiếm diện tích đáng kể.

**Không nên đồng nhất evacuation failure với Full GC:** G1 có thể tiếp tục xử lý các region thất bại trong các collection sau. Chỉ một dòng **Pause Full** mới xác nhận Full GC.

Hướng điều tra:
1. Old occupancy có tăng liên tục không?
2. G1 có đủ free regions trước evacuation không?
3. Concurrent marking có hoàn tất kịp không?
4. Có phải batch/traffic tăng cùng lúc không?
5. Heap sau các Young/Mixed GC giảm bao nhiêu?

**Ưu tiên ứng dụng**: giảm số object còn sống, hạn chế batch/concurrency, dùng bounded queues/cache. Nếu live set hợp lệ và có RAM headroom, cân nhắc tăng heap. Những cờ như **G1ReservePercent** chỉ nên đánh giá khi có evidence đúng cơ chế.

## 8. Nhóm nguyên nhân B — Concurrent marking không theo kịp

G1 dùng concurrent marking để xác định các old regions có thể được thu hồi trong **space-reclamation phase**. **IHOP** (*Initiating Heap Occupancy Percent*) tham gia quyết định lúc bắt đầu marking; HotSpot hiện đại thường dùng **adaptive IHOP**.

Nếu tốc độ cấp phát/promote tăng đột ngột:
- Old occupancy tăng nhanh hơn mức dự đoán.
- Marking bắt đầu hoặc hoàn tất quá muộn.
- Mixed collections chưa thu hồi đủ.
- Evacuation tiếp theo thiếu destination regions.
- G1 có thể phải fallback Full GC.

~~~text
Old/promotion spike
       │
       ▼
Marking chưa hoàn tất kịp
       │
       ▼
Mixed GC chưa tạo đủ Free regions
       │
       ▼
Allocation/Evacuation pressure
       │
       ▼
Có thể Full GC
~~~

**Concurrent Mark Cycle xuất hiện không đồng nghĩa sự cố.** Đây là hoạt động thường ngày của G1. Cần nhìn timing và mức reclaim thực.

Thứ tự xử lý:
1. Kiểm tra batch size, queue, object lifetime và cache.
2. Đánh giá CPU/concurrent GC thread headroom.
3. Tăng heap khi live set hợp lệ và RAM còn đủ.
4. Nếu chứng cứ chỉ ra marking kém kịp, xem **-XX:ConcGCThreads** hoặc **-XX:G1ReservePercent**.
5. Tránh tắt adaptive IHOP hoặc đặt threshold thủ công ngay từ đầu.

Tăng concurrent threads có thể lấy CPU từ ứng dụng và giảm throughput, vì vậy cần benchmark cùng workload.

## 9. Nhóm nguyên nhân C — Humongous objects và fragmentation

G1 xem object có kích thước từ khoảng **một nửa heap region trở lên** là **humongous**. Nó thường được cấp trực tiếp vào Old và có thể cần **nhiều regions liền nhau**.

Ví dụ hình dung:

~~~text
[Free][Old][Free][Old][Free][Free][Old][Free]
~~~

Tổng số Free regions có vẻ nhiều nhưng **không có ba Free regions liên tiếp**. Một allocation lớn cần ba regions có thể thất bại vì fragmentation.

Tín hiệu:

~~~text
Pause Young (Concurrent Start) (G1 Humongous Allocation)
Humongous regions: 16->14
~~~

Đây chỉ là **ví dụ dạng log**, không phải số đo thực tế. Dòng đầu là Young GC và **không tự là Full GC**.

Trước khi đổi region size:
- Tìm các object lớn: **byte[]**, buffers, strings hoặc các dữ liệu serialization lớn;
- Xem chúng có được giữ sống quá lâu không;
- Kiểm tra cache/batch kích thước lớn;
- Xem số humongous regions và actual region size.

Giải pháp ứng dụng thường là **streaming, chunking, giới hạn payload/batch/cache**. Cờ **-XX:G1HeapRegionSize** có thể tăng ngưỡng humongous và giảm số object thuộc nhóm này, nhưng thay đổi granularity và có trade-off, cần đo.

## 10. Nhóm nguyên nhân D — Live set cao hoặc leak

Full GC **không thu hồi** những object vẫn còn reachable.

Hai dòng **giả lập**:

~~~text
GC(101) Pause Full (G1 Compaction Pause) 992M->958M(1024M)
GC(105) Pause Full (G1 Compaction Pause) 1008M->990M(1024M)
~~~

Heap giảm lần lượt **34 MiB** và **18 MiB**, sau Full vẫn gần đầy. Đây là tín hiệu giữ nhiều object sống.

Nguyên nhân có thể là:
- Live set hợp lệ quá lớn cho heap budget;
- Cache không giới hạn;
- Queue backlog;
- Batch giữ toàn bộ dataset;
- Reference leak, vòng đời object sai.

Cần kết hợp **heap dump**, retained-size analysis, object histogram và GC roots khi phù hợp, cùng biến động object counts theo thời gian. **Không có một ngưỡng occupied duy nhất chứng minh leak.**

| Điều tìm thấy | Hướng xử lý đầu tiên |
| --- | --- |
| Cache không giới hạn | Bounded cache, TTL, eviction |
| Queue tích lũy | Backpressure, giới hạn concurrency |
| Batch giữ mọi object | Streaming, pagination, chunking |
| Leak do tham chiếu | Sửa lifecycle/reference path |
| Live set hợp lệ lớn | Cân nhắc Xmx/capacity hoặc phân chia workload |

Tăng **-Xmx** có thể giúp live set hợp lệ, nhưng nếu leak thật thì chỉ hoãn thời gian cạn heap.

## 11. Nhóm nguyên nhân E — Explicit GC và yêu cầu bên ngoài

Lời gọi:

~~~java
System.gc();
~~~

chỉ là **yêu cầu JVM thu gom**, không phải hợp đồng đảm bảo một Full GC giống hệt trên mọi JVM. HotSpot/G1 có thể in **Pause Full (System.gc())** tùy cấu hình.

Các cờ tham khảo:

~~~text
-XX:+ExplicitGCInvokesConcurrent
-XX:+DisableExplicitGC
~~~

**ExplicitGCInvokesConcurrent** yêu cầu explicit GC theo đường concurrent phù hợp trên G1. **DisableExplicitGC** khiến JVM bỏ qua lời gọi System.gc() từ ứng dụng, **không tắt GC tự động khi cần**.

**Không bật cờ trước khi biết ai gọi System.gc().** Caller có thể là code, thư viện, agent hoặc công cụ quản trị; cần đánh giá tác dụng phụ nếu thay behavior. Một số cấu hình G1 periodic GC cũng có thể yêu cầu GC khi idle, nhưng không phải mặc định mọi JVM sẽ Full GC theo chu kỳ.

Nếu Full GC chỉ xuất hiện tại thời điểm tác vụ quản trị trong khi heap còn headroom, hãy điều tra explicit cause trước, không vội chỉnh IHOP hoặc tăng heap.

## 12. Nhóm nguyên nhân F — Pinning trên HotSpot mới hơn

Ở những JDK có G1 region pinning cải tiến (JEP 423), có thể thấy:

~~~text
Evacuation Failure: Allocation
Evacuation Failure: Pinned
Evacuation Failure: Allocation/Pinned
~~~

**Allocation** liên quan thiếu vùng đích. **Pinned** liên quan object/region không thể được di chuyển do tương tác native/JNI ở thời điểm ấy. Hai tình huống khác nhau.

Khi gặp Pinned:
1. Điều tra native libraries/JNI interactions.
2. Xem thời gian pinning và khả năng phục hồi sau đó.
3. Không tự kết luận heap leak hoặc thiếu destination space.
4. Đọc tài liệu đúng runtime; format log JDK 17 và JDK mới có thể khác.

**Evacuation failure không tự là Full GC.** Cần tìm event **Pause Full** riêng.

## 13. Đừng nhầm container OOM kill với Java heap Full GC

Java process sử dụng nhiều vùng ngoài Java heap:
- Metaspace;
- Direct/native buffers;
- Thread stacks;
- JIT code cache, GC native metadata;
- JNI và memory-mapped pages.

Nếu container/OS kill process vì memory limit, **không nhất thiết có Pause Full**. OutOfMemoryError do **Metaspace** hoặc direct buffer cũng cần hướng chẩn đoán khác Java heap pressure.

Bước phân biệt:
- **Pause Full** trong GC log xác nhận Full GC.
- **OutOfMemoryError: Java heap space** chỉ ra sự cố cấp phát heap.
- **OutOfMemoryError: Metaspace** hướng tới metadata/classes.
- **Container OOM kill** cần đọc events/cgroup memory/OS logs.

Tăng Xmx không tính đến native headroom có thể khiến container bị kill sớm hơn. Đừng dùng Full GC như lời giải thích duy nhất cho mọi process restart.

## 14. Chỉ chọn JVM flag sau khi bằng chứng hỗ trợ

| Dấu hiệu | Giả thuyết cần xác minh | Hành động ưu tiên | Flag có thể xem xét sau |
| --- | --- | --- | --- |
| Pause Full (System.gc()) | Explicit request | Tìm caller, xem chính sách | ExplicitGCInvokesConcurrent hoặc DisableExplicitGC |
| Evacuation Failure: Allocation | Thiếu destination regions | Giảm live set/batch, xem capacity | G1ReservePercent/ConcGCThreads |
| Marking chậm, Old tăng | Marking không theo kịp | Giảm promotion, xem CPU | ConcGCThreads, IHOP theo bằng chứng |
| Humongous regions cao | Object lớn và fragmentation | Streaming/chunking/cache | G1HeapRegionSize |
| Full GC lặp, after-GC heap cao | Live set/retention | Heap dump, sửa cache/queue | Xmx nếu data hợp lệ |
| Evacuation Failure: Pinned | Native/JNI pinning | Điều tra native interactions | Không tự chọn cờ cho Allocation |
| Young GC dài nhưng không Full | Young pause problem | Phân tích phases riêng | MaxGCPauseMillis nếu phù hợp |
| OOM kill không có Full GC | Container/native memory | Kiểm tra memory tổng | Có thể cần giảm Xmx |

Đây là **ma trận gợi ý điều tra**, không phải điều kiện đủ để bật cờ. Những trường hợp có thể chồng lấn: cache lớn vừa tăng Old occupancy vừa tạo humongous allocations.

### Các cờ dễ bị hiểu nhầm

- **-XX:MaxGCPauseMillis** là mục tiêu mềm, không đảm bảo Full GC dưới mốc đó.
- **-XX:ParallelGCThreads** không khiến object còn sống thành garbage; quá nhiều threads có thể tăng overhead.
- **-XX:ConcGCThreads** có thể giúp marking khi đủ CPU, nhưng giành CPU với application.
- **-XX:G1ReservePercent** liên quan dự phòng region và adaptive IHOP; không chữa leak.
- **-XX:G1HeapRegionSize** có trade-off về region granularity.
- **-Xmn**, cố định young generation một cách máy móc có thể cản G1 tự sizing cho pause target.
- **-Xms = -Xmx** hoặc **AlwaysPreTouch** phục vụ một số mục tiêu memory commitment/page faults, không tự sửa high live set.

Oracle khuyến nghị **bắt đầu từ G1 defaults** và chỉ chỉnh một số tham số khi có bằng chứng.

## 15. Ba kịch bản ra quyết định

### Kịch bản A — Full GC lặp và reclaim ít

**Giả định:** Sau Full GC, heap vẫn dùng trên 90% capacity nhiều lần, cache tăng theo traffic.

**Sai:** tăng Xmx liên tục.

**Đúng:** kiểm tra retained objects, xem cache/queue có giữ dữ liệu quá lâu không. Nếu có leak, sửa lifecycle; nếu live set hợp lệ và cần nhiều RAM, cân nhắc tăng heap phù hợp container budget.

**Xác nhận:** heap sau GC có headroom ổn định, Full GC ít hơn, latency/error rate cải thiện.

### Kịch bản B — Full GC xảy ra đúng lịch tác vụ quản trị

**Giả định:** log có Pause Full (System.gc()) lúc heap không quá đầy.

**Sai:** chỉnh G1ReservePercent hoặc ConcGCThreads.

**Đúng:** tìm explicit caller. Nếu lời gọi không cần thiết, loại bỏ. Nếu có lý do cần gọi, đánh giá cấu hình concurrent explicit GC theo runtime và business requirement.

**Xác nhận:** không còn Full GC bất ngờ và ứng dụng vẫn đúng chức năng.

### Kịch bản C — Batch đột biến làm marking không kịp

**Giả định:** batch mới tăng promotion rate, marking chưa xong đã gặp evacuation failure.

**Sai:** tăng ParallelGCThreads ngay.

**Đúng:** giảm batch concurrency hoặc giới hạn queue, kiểm tra cpu quota/heap headroom. Nếu vẫn chưa đủ, thử đúng một tuning parameter có liên quan trên staging.

**Xác nhận:** marking hoàn tất kịp, không thiếu destination regions, throughput/p99 latency đạt yêu cầu.

## 16. Ví dụ Java 17+ chạy độc lập để luyện chẩn đoán

Ví dụ dùng **log giả lập cố định**. Nó **không cố tạo Full GC hoặc OutOfMemoryError** trên máy học, nên an toàn và có stdout tái lập. Nó đếm sự kiện Full, explicit requests, evacuation warning và humongous signals, sau đó đánh dấu những Full GC có **after-GC occupancy từ 90% capacity trở lên theo quy tắc ví dụ**. Mốc 90% **không phải ngưỡng G1 bắt buộc Full GC**.

Tạo tệp **G1FullGcDiagnosisDemo.java**:

~~~java
import java.util.List;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class G1FullGcDiagnosisDemo {
    private static final Pattern HEAP = Pattern.compile(
            "(\\d+)M->(\\d+)M\\((\\d+)M\\)");

    static void analyze(List<String> lines) {
        int full = 0;
        int explicit = 0;
        int evacuation = 0;
        int humongous = 0;
        int highAfter = 0;

        for (String line : lines) {
            if (line.contains("To-space exhausted")
                    || line.contains("Evacuation Failure: Allocation")) {
                evacuation++;
            }
            if (line.contains("G1 Humongous Allocation")) {
                humongous++;
            }
            if (!line.contains("Pause Full")) {
                continue;
            }

            full++;
            boolean isExplicit = line.contains("System.gc()");
            if (isExplicit) {
                explicit++;
            }

            Matcher matcher = HEAP.matcher(line);
            if (matcher.find()) {
                long before = Long.parseLong(matcher.group(1));
                long after = Long.parseLong(matcher.group(2));
                long capacity = Long.parseLong(matcher.group(3));

                // Chỉ là ngưỡng ví dụ của chương trình!
                if (capacity > 0
                        && (double) after / capacity >= 0.90) {
                    highAfter++;
                }

                System.out.printf(Locale.ROOT,
                        "full #%d: reclaimed=%d MiB; "
                                + "after=%d/%d MiB; explicit=%s%n",
                        full, before - after,
                        after, capacity, isExplicit);
            }
        }

        System.out.println("full events = " + full);
        System.out.println("explicit full events = " + explicit);
        System.out.println("evacuation warning lines = " + evacuation);
        System.out.println("humongous allocation signals = " + humongous);
        System.out.println(
                "high after-full events (example 90%) = " + highAfter);
        System.out.println("warnings alone prove root cause = false");
    }

    public static void main(String[] args) {
        List<String> sample = List.of(
                "GC(20) Pause Young (Normal) "
                        + "(G1 Evacuation Pause) 720M->600M(1024M)",
                "GC(21) Evacuation Failure: Allocation",
                "GC(21) Pause Young (Normal) "
                        + "(G1 Evacuation Pause) 960M->940M(1024M)",
                "GC(22) Pause Full (G1 Compaction Pause) "
                        + "1000M->955M(1024M)",
                "GC(23) Pause Full (System.gc()) "
                        + "610M->530M(1024M)",
                "GC(24) Pause Young (Concurrent Start) "
                        + "(G1 Humongous Allocation) "
                        + "900M->820M(1024M)",
                "GC(25) Pause Full (G1 Compaction Pause) "
                        + "1010M->990M(1024M)"
        );

        analyze(sample);
    }
}
~~~

Biên dịch và chạy với **JDK 17+**:

~~~bash
javac --release 17 G1FullGcDiagnosisDemo.java
java G1FullGcDiagnosisDemo
~~~

**Stdout chính xác:**

~~~text
full #1: reclaimed=45 MiB; after=955/1024 MiB; explicit=false
full #2: reclaimed=80 MiB; after=530/1024 MiB; explicit=true
full #3: reclaimed=20 MiB; after=990/1024 MiB; explicit=false
full events = 3
explicit full events = 1
evacuation warning lines = 1
humongous allocation signals = 1
high after-full events (example 90%) = 2
warnings alone prove root cause = false
~~~

**Giải thích:**
- Có **3 dòng Pause Full**; một dòng có cause System.gc().
- Evacuation warning xuất hiện một lần, **không trực tiếp chứng minh Full GC**.
- G1 Humongous Allocation nằm trong **Pause Young**, không tăng Full count.
- Các lần Full reclaim **45, 80, 20 MiB** theo đúng số giả lập.
- Hai Full có after-GC occupancy cao theo **ngưỡng ví dụ 90%**, không phải quy tắc HotSpot mặc định.

**Giới hạn:** Đây là **bộ đọc dòng giả lập phục vụ học tập**, không phải GC log parser production-ready. Log thực có thể dùng đơn vị K/M/G, nhiều dòng chung GC ID, timestamp/decorators khác và cú pháp thay đổi theo JDK. Công cụ production phải **gom theo event**, chuẩn hóa units và ghép timeline; tuyệt đối không kết luận root cause chỉ từ việc đếm keyword.

## 17. Đo hiệu quả thay đổi một cách có căn cứ

### Xây dựng giả thuyết

Ví dụ:
- **Bằng chứng:** old occupancy tăng trong batch, marking chưa kịp hoàn tất, có Evacuation Failure: Allocation, sau đó Pause Full.
- **Giả thuyết:** quá nhiều object sống cùng lúc làm G1 thiếu headroom.
- **Hành động:** giảm batch concurrency hoặc cache retention trước khi tuning.
- **Dấu hiệu bác bỏ:** sau khi giảm batch pressure, Full GC vẫn xuất hiện theo lịch System.gc() và old occupancy vẫn bình thường.

Một giả thuyết tốt phải có thể được **kiểm chứng hoặc bác bỏ** bằng dữ liệu.

### Chọn đúng chỉ số

Ít nhất nên đo:
- Full GC frequency/duration và causes;
- p95/p99 request latency, timeout/error rate;
- Heap occupied sau GC, old occupancy;
- Allocation/promotion rate, humongous regions;
- CPU, CPU throttling, throughput;
- Java/native memory và container limits.

**Giảm Full GC count không đủ**, nếu lỗi người dùng hoặc CPU tăng.

### Đối chứng công bằng

Dùng cùng:
- JDK build, JAR, dependencies và GC collector;
- Workload, dữ liệu đầu vào, thời gian chạy;
- CPU/RAM/container limits;
- Log level có overhead tương đương;
- Số lượt đo đủ để báo median và biến thiên.

Chỉ thay **một nhóm biến phù hợp giả thuyết**. Nếu thay Xmx, phải ghi rõ heap budget cũ/mới và kiểm tra memory headroom.

### Thử nghiệm an toàn

Chạy staging/canary với workload đại diện, theo dõi regression, giữ cấu hình rollback. **Không cố tạo một chuỗi Full GC nặng trên production** chỉ để xác nhận logger hoạt động.

Sau thay đổi, ghi lại:
- Sự kiện ban đầu đã được xác minh;
- Nguyên nhân đã xác nhận hay chỉ còn là giả thuyết;
- Thay đổi code/config cụ thể;
- Dữ liệu trước/sau và độ tin cậy;
- Rủi ro, điều kiện rollback và kế hoạch giám sát.

## 18. Lỗi thường gặp

**Lỗi 1 — Thấy Full GC là tăng Xmx.** Không đúng khi cause là explicit GC hoặc leak chưa sửa.

**Lỗi 2 — Gọi mọi STW là Full GC.** Young/Mixed cũng là STW pause.

**Lỗi 3 — Chỉ đọc một dòng Pause Full.** Root cause thường nằm ở những phút trước.

**Lỗi 4 — Evacuation Failure chắc chắn là memory leak.** Allocation failure và pinned failure cần điều tra khác nhau.

**Lỗi 5 — G1 Humongous Allocation chính là Full GC.** Nó có thể là Young Concurrent Start.

**Lỗi 6 — Full GC Java 10 đã parallel nên không còn STW.** Parallel GC workers không đồng nghĩa application concurrent.

**Lỗi 7 — MaxGCPauseMillis là bảo đảm cứng.** Đây là mục tiêu mềm, không áp lên mọi Full GC.

**Lỗi 8 — Tăng ParallelGCThreads sẽ hết Full GC.** Không giải quyết live set hoặc allocation pressure.

**Lỗi 9 — Chỉnh IHOP mà không xem marking timeline.** Có thể sai hoàn toàn với explicit GC.

**Lỗi 10 — Bật quá nhiều GC debug log trong benchmark.** Làm tăng overhead, méo số đo.

**Lỗi 11 — Full GC reclaim ít chắc chắn leak.** Có thể live set hợp lệ lớn.

**Lỗi 12 — Tăng Xmx mà quên container/native RAM.** Có thể gây OOM kill.

**Lỗi 13 — Thay nhiều flags cùng lúc.** Mất khả năng phân lập tác dụng.

**Lỗi 14 — Heap dump trên production một cách tùy tiện.** Có thể dừng ứng dụng và tạo file chứa dữ liệu nhạy cảm.

**Lỗi 15 — Chỉ xem Full GC count.** Phải quan sát user latency, error rate và throughput.

## 19. Checklist trước khi tuning G1

1. Xác minh HotSpot/JDK build và process đang dùng G1.
2. Xác nhận sự cố nghiệp vụ và mốc đo.
3. Tìm chính xác event **Pause Full**.
4. Ghi GC ID, cause, duration, heap trước/sau.
5. Xem các events trước Full GC và timeline marking.
6. Tìm To-space exhausted/Evacuation Failure nếu có.
7. Phân biệt Allocation và Pinned.
8. Kiểm tra old/humongous regions và free space.
9. Đối chiếu batch/concurrency/allocation rate.
10. Kiểm tra heap sau nhiều Full GC có còn rất cao không.
11. Điều tra heap retention/leak khi có bằng chứng.
12. Loại trừ System.gc() hoặc yêu cầu quản trị.
13. Phân biệt Java heap OOME và container/native OOM.
14. Nêu **một giả thuyết cụ thể**, điều kiện xác minh và bác bỏ.
15. Ưu tiên sửa code/workload khi đó là nguyên nhân.
16. Chỉ thử một VM flag sau khi đã thu đủ bằng chứng.
17. Benchmark cùng workload, cùng runtime.
18. So p99 latency, throughput, CPU, memory và Full GC.
19. Thử canary và chuẩn bị rollback.
20. Lưu log/phiên bản/cấu hình để tái hiện.

## 20. Tự kiểm tra kiến thức

**1. Vì sao không đổi flags ngay khi thấy Full GC?**  
Vì một Full GC có thể có nhiều cause. Tuning sai có thể không cải thiện và làm tăng overhead.

**2. Full GC song song của G1 bắt đầu từ đâu?**  
Java 10, JEP 307; nhiều GC workers xử lý song song nhưng vẫn stop-the-world.

**3. To-space exhausted có chứng minh Full GC xảy ra ngay không?**  
Không. Cần event Pause Full riêng.

**4. Vì sao marking chậm có thể gây Full GC?**  
Old occupancy tăng nhanh hơn tiến độ xác định/reclaim vùng, làm thiếu headroom.

**5. Humongous allocation liên quan fragmentation ra sao?**  
Object lớn có thể cần nhiều free regions liên tiếp, dù tổng free regions chưa bằng 0.

**6. System.gc() luôn báo thiếu heap?**  
Không, đây là explicit request và không bảo đảm một kiểu GC cố định.

**7. After-Full heap gần đầy có chắc chắn leak?**  
Không. Đó là bằng chứng live set/retention cao, cần heap analysis.

**8. Vì sao tăng Xmx có thể khiến container OOM kill?**  
Vì native/process memory vẫn cần headroom trong tổng giới hạn RAM.

**9. G1 Humongous Allocation là Full GC không?**  
Không tự nó là Full GC; có thể thuộc Pause Young.

**10. MaxGCPauseMillis bảo đảm thời lượng Full GC không?**  
Không, nó là pause-time goal mềm.

**11. Khi nào xem ConcGCThreads?**  
Khi marking không kịp, CPU có headroom và phép đo hỗ trợ giả thuyết.

**12. Nên đọc gì ngoài một dòng Full GC?**  
GC IDs, timestamps, old/humongous regions, marking progress và workload.

**13. Nếu Full GC do System.gc(), bước đầu là gì?**  
Tìm caller/agent và mục đích request, không tăng heap ngay.

**14. Có thể dùng parser chỉ tìm Allocation Failure trên mọi JDK không?**  
Không. Cause và log format có thể khác; tìm đúng event Pause Full cùng ngữ cảnh.

**15. Số lần Full GC giảm có đủ chứng minh hiệu năng tốt hơn?**  
Không. Cần latency, throughput, CPU, memory và error rate.

## 21. Ghi nhớ cuối bài

- **Full GC là sự kiện phải xác minh; nguyên nhân gốc cần điều tra.**
- **Evacuation failure, concurrent marking không kịp, humongous fragmentation và live set cao** là những nhóm cause quan trọng, nhưng không phải duy nhất.
- **System.gc()/external GC requests** có thể gây Full GC không liên quan thiếu heap.
- **JEP 307 từ Java 10** giúp G1 Full GC song song, nhưng vẫn STW.
- **To-space exhausted** và **G1 Humongous Allocation** không tự chứng minh Full GC.
- **After-GC occupancy cao** cần kiểm tra retained objects, không mặc định kết luận leak.
- **Unified GC Logging, GC IDs và dữ liệu workload** là nền tảng quyết định.
- Chỉ đổi **Xmx, G1ReservePercent, ConcGCThreads, G1HeapRegionSize** khi có giả thuyết và số đo phù hợp.
- Giữ đối chứng, thử nghiệm an toàn và rollback.

**Tài liệu chính thức, vẫn áp dụng:**
- [Oracle Java SE 25 — G1 Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-garbage-collector-tuning.html).
- [Oracle Java SE 25 — G1 Collector: Evacuation Failure, Humongous Objects](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html).
- [Oracle Java SE 17 — G1 Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-garbage-collector-tuning.html).
- [Oracle Java SE 21 — JVM Options and Unified Logging](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html).
- [Oracle JDK 10 Release Notes — JEP 307](https://www.oracle.com/java/technologies/javase/10all-relnotes.html).
- [OpenJDK — JEP 307: Parallel Full GC for G1](https://openjdk.org/jeps/307).
- [OpenJDK — JEP 423: Region Pinning for G1](https://openjdk.org/jeps/423).
