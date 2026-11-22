# Phân tích GC log trong Java

**GC log** là nhật ký do Java Virtual Machine ghi lại để mô tả hoạt động garbage collection (GC): loại collection, thời điểm, heap usage trước và sau GC, thời gian pause, các phase và một số thông tin CPU hoặc metaspace. Phân tích GC log giúp xác định JVM có đang thu gom quá thường xuyên, pause quá dài, giữ lại quá nhiều object hay gặp vấn đề về allocation hay không.

Từ Java 9, HotSpot dùng **Unified Logging** với cú pháp **-Xlog**. Đây là cách cấu hình GC logging hiện đại thay cho các ví dụ cũ dùng nhiều cờ PrintGC riêng lẻ. Với G1, có thể bắt đầu bằng **-Xlog:gc*=info** để xem tổng quan; khi cần tìm nguyên nhân, bổ sung log phase, heap, CPU, safepoint hoặc mức debug.

GC log là bằng chứng về hành vi của collector, không phải bản đồ object graph. Nó cho biết heap thay đổi thế nào và GC đã làm gì, nhưng không tự chỉ ra object nào giữ tham chiếu hoặc class nào gây memory leak. Khi cần chi tiết đó, hãy kết hợp JFR, heap histogram, heap dump và application metrics.

## 1. GC log dùng để làm gì?

GC log giúp trả lời các câu hỏi:

- JVM đang dùng garbage collector nào?
- Young GC, Mixed GC hoặc Full GC xảy ra thường xuyên đến mức nào?
- Mỗi pause kéo dài bao lâu?
- Heap còn bao nhiêu sau mỗi collection?
- Old generation hoặc Metaspace có tăng liên tục không?
- Có evacuation failure, allocation failure hoặc humongous allocation không?
- GC dành thời gian cho phase nào?
- CPU time của GC đến từ VM, hệ điều hành hay scheduling?
- Có safepoint nào ngoài GC làm ứng dụng dừng lâu không?
- Thay đổi code, heap hoặc GC configuration có cải thiện latency không?

GC log đặc biệt hữu ích khi điều tra:

- Request latency tăng theo chu kỳ.
- CPU tăng bất thường.
- Young GC xảy ra liên tục.
- Full GC kéo dài.
- Heap sau GC không giảm.
- Metaspace tăng hoặc class unloading không diễn ra.
- OutOfMemoryError hoặc GC overhead limit exceeded.
- Pause time vượt SLO.

### GC log không thay thế application monitoring

GC log chỉ mô tả hoạt động của JVM/collector. Nó không trực tiếp cho biết request nào chậm, p95/p99 latency, database query, queue backlog hoặc business error rate.

Khi điều tra production, cần đối chiếu GC log với application metrics, distributed tracing, OS/container metrics và JFR.

## 2. Unified Logging và cú pháp -Xlog

Từ JDK 9, HotSpot tích hợp Unified Logging. GC là một nhóm tag trong hệ thống này.

Cú pháp tổng quát:

~~~bash
-Xlog:<selections>:<output>:<decorators>:<output-options>
~~~

Các phần:

- **selections:** tag, tổ hợp tag và mức log.
- **output:** stdout, stderr hoặc file.
- **decorators:** timestamp, uptime, level, tags, PID...
- **output-options:** rotation, kích thước file và số file giữ lại.

Một lựa chọn tag có thể gồm nhiều tag kết hợp bằng dấu cộng. Dấu phẩy phân tách các selection khác nhau.

Ví dụ:

~~~bash
-Xlog:gc
~~~

Chỉ ghi các message mang tag gc ở mức info trở xuống vào stdout theo cấu hình mặc định.

Ví dụ rộng hơn:

~~~bash
-Xlog:gc*=info
~~~

Ghi message có tag gc và các tag liên quan đến GC ở mức info. Đây là điểm bắt đầu hữu ích để xem tổng quan nhiều collector.

### Phân biệt gc và gc*

- **gc:** chỉ chọn message có đúng tag gc.
- **gc*:** chọn các tag set có gc và các tag bổ sung liên quan, ví dụ gc,start; gc,heap; gc,phases.

Vì vậy gc* tạo log chi tiết hơn và có thể sinh nhiều dòng hơn.

### Mức log

Các mức thường gặp:

| Level | Ý nghĩa |
|---|---|
| off | Tắt message |
| error | Lỗi |
| warning | Cảnh báo |
| info | Thông tin vận hành |
| debug | Chi tiết phục vụ chẩn đoán |
| trace | Rất chi tiết |

Nếu chỉ cần quan sát tổng quan, bắt đầu ở info. Chỉ bật debug hoặc trace cho tag cần điều tra và trong thời gian giới hạn.

## 3. Bật GC log khi khởi chạy JVM

Ví dụ G1 trên Java 17+:

~~~bash
java -Xms512m -Xmx512m -XX:+UseG1GC -Xlog:gc*=info -jar app.jar
~~~

Lệnh trên:

- Cấu hình heap tối thiểu và tối đa 512 MB.
- Chọn G1 rõ ràng.
- Ghi thông tin GC và các tag liên quan.
- Ghi ra stdout theo mặc định.

Để ghi vào file với timestamp và các decorator hữu ích:

~~~bash
java -Xms512m -Xmx512m -XX:+UseG1GC "-Xlog:gc*=info:file=gc.log:time,uptime,level,tags" -jar app.jar
~~~

Trên Windows PowerShell, đặt toàn bộ tùy chọn có dấu hai chấm trong dấu ngoặc kép như ví dụ để tránh shell xử lý ký tự đặc biệt.

### Dùng một log ngắn gọn hơn

~~~bash
java "-Xlog:gc:file=gc.log:time,uptime,level,tags" -jar app.jar
~~~

Cấu hình này chỉ chọn tag gc ở mức info. Khi cần phase breakdown hoặc heap detail, dùng gc* hoặc thêm selection riêng.

### Ghi chi tiết phase của G1

~~~bash
java "-Xlog:gc*=info,gc+phases=debug:file=gc.log:time,uptime,level,tags" -jar app.jar
~~~

gc+phases=debug bổ sung thông tin chi tiết về các phase của GC. Cú pháp tag có dấu cộng nghĩa là message phải mang cả hai tag gc và phases.

Không bật tất cả tag ở trace trong production trong thời gian dài nếu chưa đánh giá lượng log, I/O và dung lượng lưu trữ.

## 4. Decorators: đọc thời gian và nguồn log

Một dòng log có thể bắt đầu bằng:

~~~text
[2026-11-10T20:17:50.458+0700][0.038s][info][gc]
~~~

Các phần:

- **time:** ngày giờ wall-clock.
- **uptime:** thời gian đã trôi qua kể từ khi JVM khởi chạy.
- **level:** mức log, ví dụ info.
- **tags:** nhóm tag, ví dụ gc.

Các decorator hữu ích:

| Decorator | Ý nghĩa |
|---|---|
| time | Ngày giờ local |
| utctime | Ngày giờ UTC |
| uptime | Thời gian kể từ khi JVM start |
| uptimemillis | Uptime tính bằng milliseconds |
| timemillis | Wall-clock epoch milliseconds |
| pid | Process ID |
| tid | Thread ID |
| level | Log level |
| tags | Tag set của message |
| hostname | Hostname |
| none | Không thêm decorator |

Ví dụ thêm PID và hostname:

~~~bash
-Xlog:gc*=info:file=gc-%p.log:time,uptime,pid,hostname,level,tags
~~~

%p được thay bằng PID của JVM trong tên file. Có thể dùng %t cho startup timestamp và %hn cho hostname theo khả năng của phiên bản JDK.

Uptime rất hữu ích để đối chiếu với log ứng dụng hoặc thời điểm deploy. Wall-clock time hữu ích để liên kết với monitoring bên ngoài, nhưng cần tính đến timezone và clock synchronization.

## 5. Rotation và quản lý dung lượng log

GC log có thể tăng nhanh, đặc biệt khi dùng gc*=debug hoặc trace. Nên bật file rotation để tránh một file không giới hạn.

Ví dụ:

~~~bash
java "-Xlog:gc*=info:file=gc-%p.log:time,uptime,level,tags:filecount=5,filesize=20M" -jar app.jar
~~~

Ý nghĩa:

- **file=gc-%p.log:** tên file chứa PID.
- **filesize=20M:** mục tiêu kích thước mỗi file khoảng 20 MB.
- **filecount=5:** giữ tối đa 5 file archive ngoài file đang ghi.

Kích thước và số lượng file cần được chọn theo retention, tốc độ log và dung lượng volume. Rotation không thay thế backup hoặc retention policy.

### Các lưu ý

- Đảm bảo thư mục output tồn tại và JVM có quyền ghi.
- Dùng volume có đủ dung lượng.
- Không ghi GC log vào filesystem đã gần đầy.
- Theo dõi cả file active và các file archive.
- Không xóa log đang được dùng để điều tra incident.
- Nếu chạy nhiều JVM, đặt tên file có PID hoặc timestamp để tránh ghi đè.

JVM hỗ trợ các output option như filesize và filecount. Kiểm tra java -Xlog:help của JDK mục tiêu để xác nhận cú pháp.

## 6. Các cấu hình GC logging thường dùng

| Mục tiêu | Cấu hình |
|---|---|
| GC summary | -Xlog:gc |
| GC và tag liên quan | -Xlog:gc*=info |
| GC phases chi tiết | -Xlog:gc+phases=debug |
| Heap usage/region | -Xlog:gc+heap=info |
| CPU time của GC | -Xlog:gc+cpu=info |
| GC ergonomics | -Xlog:gc+ergo=debug |
| Reference processing | -Xlog:gc+ref=debug |
| Safepoint | -Xlog:safepoint=info |
| Nhiều nhóm cùng lúc | -Xlog:gc*=info,safepoint=info |

Có thể ghi GC và safepoint vào cùng một file:

~~~bash
java "-Xlog:gc*=info,safepoint=info:file=gc.log:time,uptime,level,tags" -jar app.jar
~~~

Nếu cần phase breakdown:

~~~bash
java "-Xlog:gc*=info,gc+phases=debug,gc+cpu=info,safepoint=info:file=gc-detail.log:time,uptime,level,tags:filecount=5,filesize=20M" -jar app.jar
~~~

Không cần bật mọi selection cho mọi sự cố. Bắt đầu từ log info, xác định phần còn thiếu rồi thêm tag tương ứng.

## 7. Bật hoặc kiểm tra logging trên JVM đang chạy

Nếu JVM đã chạy mà chưa bật GC log, có thể kiểm tra dynamic logging qua diagnostic command VM.log nếu runtime hỗ trợ.

Liệt kê cấu hình hiện tại:

~~~bash
jcmd <pid> VM.log list
~~~

Xem cú pháp của đúng JVM:

~~~bash
jcmd <pid> help VM.log
~~~

Ví dụ cấu hình một output file mới:

~~~bash
jcmd <pid> VM.log output=gc-dynamic.log what="gc*=info" decorators="time,uptime,level,tags"
~~~

Lệnh này yêu cầu JVM bật selection và output theo tham số được hỗ trợ. Đường dẫn tương đối được giải quyết theo working directory của JVM. Hãy kiểm tra VM.log list sau khi cấu hình để xác nhận.

Có thể yêu cầu rotate các log output:

~~~bash
jcmd <pid> VM.log rotate=true
~~~

Dynamic logging có ích khi không thể restart ngay, nhưng cần lưu ý:

- Chỉ có tác dụng trong vòng đời JVM hiện tại.
- Không tự lưu cấu hình cho lần restart tiếp theo.
- Có thể bị giới hạn bởi quyền attach và runtime.
- Cần xác nhận output file được tạo và ghi.
- Không dùng disable=true một cách tùy tiện vì có thể xóa cấu hình logging khác.

Đối với cấu hình vận hành lâu dài, nên đặt -Xlog trong startup command hoặc service configuration.

## 8. Cấu trúc một dòng GC log

Một dòng G1 summary có thể trông như sau:

~~~text
[2026-11-10T20:17:50.458+0700][0.038s][info][gc] GC(0) Pause Young (Normal) (G1 Evacuation Pause) 17M->2M(32M) 0.767ms
~~~

Đọc theo từng phần:

| Thành phần | Ý nghĩa |
|---|---|
| timestamp | Thời điểm wall-clock |
| uptime | Thời gian JVM đã chạy |
| info | Log level |
| gc | Tag |
| GC(0) | ID của collection event |
| Pause Young | Loại collection và stop-the-world pause |
| Normal | Nhóm/cause của collection |
| G1 Evacuation Pause | Ngữ cảnh collection của G1 |
| 17M | Heap usage trước GC |
| 2M | Heap usage sau GC |
| (32M) | Heap capacity tại thời điểm đó |
| 0.767ms | Thời gian pause được ghi trong summary |

### Cách đọc A->B(C)

Mẫu:

~~~text
17M->2M(32M)
~~~

có nghĩa:

- Trước collection: heap usage khoảng 17 MB.
- Sau collection: heap usage khoảng 2 MB.
- Capacity: khoảng 32 MB.

Đây là số liệu heap tổng hợp ở thời điểm collection, không phải retained size theo object. Với collection chỉ xử lý một phần heap, không diễn giải giá trị sau GC như toàn bộ live set chính xác của ứng dụng.

Capacity có thể thay đổi theo thời gian khi heap mở rộng hoặc thu hẹp. Vì vậy, hãy đọc cả ba số thay vì chỉ nhìn phần trăm hoặc giá trị sau GC.

### GC ID giúp ghép các dòng

Một collection có thể sinh nhiều dòng start, task, phases, heap, metaspace và cpu. Các dòng cùng GC(n) thuộc cùng collection.

Dùng ID này để ghép phase breakdown với summary line và tránh cộng nhầm các dòng của hai collection khác nhau.

## 9. Phân biệt Young, Mixed, Concurrent và Full GC

Tên collection phụ thuộc collector và phiên bản JDK. Với G1, các loại thường gặp gồm:

### Young GC

G1 thu gom các region thuộc young generation. Đây thường là pause stop-the-world. Object còn sống được chuyển sang survivor hoặc old region tùy tuổi và trạng thái.

Young GC thường xuyên không nhất thiết là lỗi. Nếu allocation rate cao, young collection xảy ra thường xuyên là hành vi bình thường.

Cần xem:

- Khoảng cách giữa các collection.
- Duration từng pause.
- Lượng heap được giải phóng.
- Survivor/old region thay đổi.
- Request latency trong cùng thời điểm.

### Concurrent Start

Một young pause có thể khởi động concurrent marking cycle. Sau đó G1 thực hiện các phase marking trong khi application threads tiếp tục chạy.

Concurrent marking giúp xác định vùng old generation có thể thu hồi. Nó không có nghĩa toàn bộ GC diễn ra concurrent; vẫn có các pause stop-the-world như Remark và Cleanup.

### Mixed GC

Sau khi marking hoàn tất, G1 có thể thực hiện Mixed collections. Collection set bao gồm young regions và một số old regions được chọn để thu hồi.

Mixed GC thường xuất hiện thành một chuỗi pause trong giai đoạn space reclamation. Không coi mọi Mixed pause là Full GC.

### Full GC

Full GC thường là thao tác stop-the-world có thể rất tốn thời gian. Trong G1, log có thể ghi:

~~~text
Pause Full (G1 Compaction Pause)
~~~

Nếu Full GC lặp lại, cần điều tra allocation rate, old-generation occupancy, concurrent marking có hoàn thành kịp không, humongous allocation và khả năng giữ object quá nhiều.

Một Full GC đơn lẻ có thể do System.gc() hoặc công cụ bên ngoài yêu cầu. Luôn xem cause trong log trước khi kết luận.

## 10. Phân tích G1 phase breakdown

G1 chia công việc trong pause thành nhiều phase. Bật:

~~~bash
-Xlog:gc+phases=debug
~~~

Các nhóm phase thường gặp:

- Pre Evacuate Collection Set.
- Merge Heap Roots.
- Evacuate Collection Set.
- Post Evacuate Collection Set.
- Other.

Trong đó **Evacuate Collection Set** thường là phần chính của việc di chuyển live objects khỏi các region được chọn. Nếu phase này chiếm phần lớn pause, thời gian có thể liên quan đến lượng object còn sống cần copy, số root/reference cần quét và năng lực CPU.

Một số sub-phase:

- Ext Root Scanning.
- Code Root Scan.
- Scan Heap Roots.
- Object Copy.

### Vì sao pause dài?

Một pause dài có thể do:

- Quá nhiều live objects cần copy.
- Heap lớn hoặc collection set lớn.
- Remembered set lớn.
- Nhiều root/reference cần scan.
- CPU bị giới hạn hoặc cạnh tranh.
- Allocation pressure cao.
- Heap fragmentation hoặc evacuation failure.
- Hệ điều hành tốn nhiều thời gian xử lý memory.

Không chỉ nhìn tổng duration. Xem phase nào chiếm thời gian lớn nhất, sau đó đối chiếu CPU, heap và workload.

## 11. Đọc GC CPU time và safepoint

### GC CPU breakdown

Bật:

~~~bash
-Xlog:gc+cpu=info
~~~

Một dòng ví dụ:

~~~text
GC(0) User=0.20s Sys=0.00s Real=0.01s
~~~

Ý nghĩa:

- **User:** tổng CPU time của các GC worker trong user mode.
- **Sys:** CPU time trong kernel/system mode.
- **Real:** thời gian thực tế đã trôi qua của pause.

User time có thể lớn hơn Real vì GC chạy song song trên nhiều worker. Ví dụ tổng worker CPU là 200 ms nhưng pause wall-clock chỉ 10 ms.

Nếu Sys time cao bất thường, cần kiểm tra OS, memory allocation, filesystem, container và các yếu tố môi trường.

### Safepoint logging

GC pause thường diễn ra tại safepoint, nhưng JVM còn có safepoint vì nhiều thao tác khác. Bật:

~~~bash
-Xlog:safepoint=info
~~~

Safepoint log giúp xem thời gian JVM yêu cầu và đạt safepoint, thời gian dừng application threads và các thông tin liên quan.

Nếu request latency cao nhưng GC summary không có pause tương ứng, hãy kiểm tra safepoint log để tìm những điểm dừng khác.

Không cộng trực tiếp mọi duration từ GC và safepoint nếu chúng mô tả các phần thời gian có thể chồng lấn hoặc có ranh giới khác nhau. Cần hiểu từng trường và ID trước khi tổng hợp.

## 12. Heap, generations và Metaspace

Một số dòng log cung cấp trạng thái các vùng heap:

~~~text
Eden regions: 20->0(18)
Survivor regions: 2->3(4)
Old regions: 10->10
Humongous regions: 1->1
Metaspace: 8152K->8152K(1056768K)
~~~

Các số trên chỉ minh họa cấu trúc.

### Eden và Survivor

Eden chứa object mới được cấp phát trong G1. Survivor chứa object sống sót qua collection và tiếp tục được giữ lại.

Nếu Eden thường xuyên đầy, young GC sẽ xảy ra. Đây có thể là dấu hiệu allocation rate cao, nhưng không nhất thiết là memory leak.

### Old regions

Object sống lâu có thể được promote vào old generation. Nếu old regions tăng liên tục và sau các chu kỳ GC vẫn không giảm, cần điều tra live set, cache, session, collection hoặc reference retention.

### Humongous regions

Trong G1, object có kích thước ít nhất bằng một nửa region được xử lý như humongous object. Chúng chiếm các humongous regions và có cách cấp phát/thu hồi riêng.

Nếu humongous regions tăng nhiều:

- Kiểm tra các array hoặc object rất lớn.
- Xem region size.
- Kiểm tra payload, buffer và batch size.
- Xem các lần GC có được kích hoạt sớm do humongous allocation không.
- Đánh giá fragmentation và khả năng tìm đủ region liền kề.

Không kết luận fragmentation chỉ từ một dòng humongous count; cần xem heap state và collection history.

### Metaspace

Metaspace lưu metadata của class trong native memory. Dòng Metaspace phản ánh trạng thái metadata theo log của JVM.

Nếu Metaspace tăng liên tục, có thể do class loading liên tục, class loader leak hoặc framework tạo nhiều class động. Kết hợp class loading counters, JFR, jcmd VM.classloader_stats và heap analysis để tìm nguyên nhân.

Metaspace không phải Java heap. Không cộng Metaspace vào heap usage rồi coi đó là tổng RSS của process.

## 13. Dấu hiệu GC bất thường thường gặp

### Young GC quá thường xuyên

Dấu hiệu:

- Khoảng cách giữa các Young pause ngắn.
- Eden nhanh chóng đầy lại.
- YGC tăng liên tục.
- Tổng thời gian GC chiếm tỷ lệ đáng kể.

Nguyên nhân có thể là allocation rate cao, object tạm được tạo quá nhiều hoặc heap/young sizing không phù hợp.

Hướng điều tra:

1. Dùng JFR allocation profiling.
2. Tìm method tạo nhiều object.
3. Xem object lifetime và allocation rate.
4. Giảm allocation không cần thiết.
5. Kiểm tra workload và heap sizing.

### Heap sau GC tăng dần

Nếu giá trị heap sau collection tăng theo thời gian, live set có thể đang tăng.

Nguyên nhân có thể gồm:

- Cache không có giới hạn.
- Session hoặc request state không được giải phóng.
- Queue backlog giữ object.
- Static collection hoặc listener giữ tham chiếu.
- Class loader cũ còn reachable.

Đây là dấu hiệu cần điều tra, chưa đủ để khẳng định memory leak. So sánh nhiều chu kỳ, cùng workload và heap capacity.

### Full GC lặp lại

Tìm các dòng:

~~~text
Pause Full (G1 Compaction Pause)
~~~

Kiểm tra cause và các collection trước đó. Full GC có thể liên quan đến old generation occupancy cao, concurrent marking không theo kịp allocation, humongous object hoặc explicit GC request.

Nếu Full GC giải phóng rất ít heap, cần xem object retention và heap dump.

### Evacuation Failure

G1 có thể ghi:

~~~text
Evacuation Failure: Allocation
~~~

hoặc:

~~~text
Evacuation Failure: Pinned
~~~

- **Allocation:** không đủ vùng đích để chuyển object.
- **Pinned:** object bị pin, ví dụ qua JNI critical access, nên không thể di chuyển trong lần evacuation đó.

Evacuation failure có thể khiến region tạm thời không dùng được và làm tăng áp lực collection. Kiểm tra heap occupancy, live set, allocation rate, native/JNI usage và các Full GC tiếp theo.

### Pause dài bất thường

Xem:

- Tổng pause duration.
- Phase breakdown.
- GC worker count.
- User/Sys/Real CPU time.
- Heap size và live objects.
- CPU throttling hoặc OS scheduling.
- Safepoint synchronization.

Nếu Real cao nhưng User/Sys không giải thích được, xem scheduling và thời gian chờ đạt safepoint. Nếu User cao, GC có thể đang làm nhiều công việc song song.

### Metaspace tăng hoặc OOM

Kiểm tra class loading/unloading, class loader stats và native memory. Nếu class count và Metaspace cùng tăng, điều tra class loader lifecycle, dynamic proxy, plugin và redeploy.

## 14. Đo các chỉ số GC theo thời gian

Không nên đánh giá collector bằng một pause riêng lẻ. Thu thập chuỗi dữ liệu trong một khoảng thời gian đại diện.

Các chỉ số cần tổng hợp:

| Metric | Cách đọc |
|---|---|
| GC count | Số collection theo loại |
| Pause duration | Thời gian mỗi stop-the-world pause |
| Pause p50/p95/p99/max | Phân bố pause |
| Time between GC | Khoảng cách giữa các collection |
| Heap before/after | Occupancy trước/sau collection |
| Old occupancy after GC | Xu hướng live set/retention |
| Allocation rate | Lượng object được cấp phát theo thời gian |
| Promotion rate | Tốc độ object chuyển sang old generation |
| GC CPU time | CPU dùng cho collector |
| Metaspace usage | Xu hướng metadata class |
| Humongous regions | Số region chứa object lớn trong G1 |
| Safepoint duration | Thời gian dừng JVM vì safepoint |

### Tỷ lệ thời gian pause

Với collector có stop-the-world pauses, có thể ước lượng phần thời gian ứng dụng bị dừng do GC bằng tổng pause time chia cho khoảng thời gian quan sát.

Đây chỉ là chỉ số gần đúng:

- Cần tránh cộng trùng các dòng start/summary.
- Cần phân biệt pause duration với concurrent GC duration.
- Concurrent collector còn tiêu thụ CPU khi ứng dụng vẫn chạy.
- Safepoint có thể có thời gian bổ sung ngoài GC work.

Không dùng một tỷ lệ duy nhất để kết luận collector tốt hay xấu. Đặt trong tương quan với throughput, latency và CPU budget.

## 15. Khác biệt log giữa các garbage collector

Tên phase và event phụ thuộc collector. Không áp dụng cách đọc G1 cho mọi JVM.

| Collector | Đặc điểm tổng quan khi đọc log |
|---|---|
| Serial GC | Collection đơn luồng, stop-the-world; log thường tập trung vào young/full collection |
| Parallel GC | Collection stop-the-world với nhiều worker; xem worker CPU và pause |
| G1 GC | Region-based; có Young, Concurrent Start, Mixed, marking và evacuation phases |
| ZGC | Thiết kế pause rất ngắn, nhiều công việc concurrent; log có phase và cycle riêng |
| Shenandoah | Concurrent evacuation/reclamation; log có phase và cycle riêng |

Đầu tiên xác định collector thực tế bằng JVM flags hoặc dòng GC initialization. Không suy ra collector chỉ từ một tên event.

Ví dụ xem flags:

~~~bash
java -XX:+PrintFlagsFinal -version
~~~

Hoặc xem startup log với cấu hình gc init phù hợp.

### G1

G1 cố gắng cân bằng throughput và pause-time goal. Tuning pause target không bảo đảm mọi pause đều nhỏ hơn mục tiêu. Cần xem collection set, live data và phase costs.

### Parallel

Parallel GC hướng đến throughput. Pause dài hơn có thể là trade-off để hoàn thành collection nhanh và tăng thời gian application chạy giữa các pause.

### ZGC và Shenandoah

Các collector này tập trung giảm pause bằng cách chuyển nhiều công việc sang concurrent phases. Đừng chỉ xem stop-the-world pause; cần quan sát CPU overhead, allocation headroom, concurrent cycle duration và throughput.

## 16. Legacy GC logging và chuyển sang -Xlog

Tài liệu cũ có thể sử dụng:

~~~bash
-verbose:gc
-XX:+PrintGCDetails
-Xloggc:gc.log
~~~

Từ JDK 9, Unified Logging thay thế cách cấu hình GC logging cũ bằng -Xlog.

Oracle ghi nhận -verbose:gc là alias cho -Xlog:gc. Các cờ legacy khác có lịch sử tương thích riêng và có thể thay đổi theo JDK. Không sao chép nguyên bộ cờ từ runbook Java 8 sang JDK hiện đại mà chưa kiểm tra.

Cấu hình mới nên dùng:

~~~bash
-Xlog:gc*=info:file=gc.log:time,uptime,level,tags
~~~

Kiểm tra help:

~~~bash
java -Xlog:help
~~~

Help liệt kê tag, level, decorator và output options mà đúng runtime hỗ trợ.

## 17. Phân tích GC log bằng công cụ

### Dùng PowerShell để lọc log

Tìm Young và Full GC:

~~~powershell
Select-String -Path .\gc.log -Pattern "Pause Young|Pause Full"
~~~

Tìm evacuation failure:

~~~powershell
Select-String -Path .\gc.log -Pattern "Evacuation Failure"
~~~

Tìm Metaspace:

~~~powershell
Select-String -Path .\gc.log -Pattern "Metaspace"
~~~

### Dùng grep trên Linux/macOS

~~~bash
grep -E "Pause Young|Pause Full" gc.log
grep -E "Evacuation Failure" gc.log
grep -E "Metaspace" gc.log
~~~

Các lệnh trên chỉ lọc dòng để điều tra nhanh; không thay thế parser hiểu cấu trúc log.

### JDK Mission Control và JFR

JFR giúp xem GC events, allocation, thread CPU, lock và I/O cùng một timeline. JMC phù hợp khi cần phân tích mối quan hệ giữa GC và workload.

Bắt đầu recording:

~~~bash
jcmd <pid> JFR.start name=gc-analysis settings=profile duration=60s filename=gc-analysis.jfr
~~~

Sau đó mở file bằng JMC và xem Garbage Collections, Heap, Allocation và Threads.

### GC log analyzer

Có thể dùng GCViewer hoặc các GC log analyzer khác để tổng hợp pause distribution, throughput và heap trends. Kiểm tra công cụ có hỗ trợ đúng format JDK đang dùng hay không.

GC log có thể chứa hostname, PID, file path và thông tin nội bộ. Nếu dùng dịch vụ phân tích trực tuyến, chỉ upload khi được phép và đã đánh giá dữ liệu nhạy cảm. Ưu tiên công cụ chạy local cho log production.

## 18. Lab Java 17+: tạo và phân tích GC log

Lab này cố tình tạo allocation pressure để quan sát Young GC và gọi System.gc() một lần để tạo một Full GC có cause rõ ràng. Không dùng System.gc() như kỹ thuật tối ưu production; lời gọi này chỉ phục vụ minh họa log.

Tạo file **GcLogDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;

public final class GcLogDemo {
    private static final List<byte[]> retained = new ArrayList<>();

    public static void main(String[] args) throws InterruptedException {
        System.out.println("READY");

        for (int i = 0; i < 300; i++) {
            byte[] block = new byte[256 * 1024];
            block[0] = (byte) i;

            if (i % 20 == 0) {
                retained.add(block);
            }
        }

        System.out.println("Retained blocks: " + retained.size());

        System.gc();
        Thread.sleep(100);

        System.out.println("DONE");
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 GcLogDemo.java
~~~

Chạy với G1 và heap 32 MB:

~~~bash
java -Xms32m -Xmx32m -XX:+UseG1GC "-Xlog:gc*=info:file=gc.log:time,uptime,level,tags" GcLogDemo
~~~

Stdout chính xác:

~~~text
READY
Retained blocks: 15
DONE
~~~

Chương trình tạo 300 array, mỗi array 256 KiB. Mỗi 20 lần lặp, một array được giữ trong static list. Do vòng lặp chạy từ 0 đến 299, có 15 array được giữ lại.

### Xem GC summary

Mở gc.log và tìm các dòng:

~~~text
GC(0) Pause Young (Normal) (G1 Evacuation Pause) 17M->2M(32M) 0.767ms
GC(6) Pause Full (System.gc()) 13M->4M(32M) 2.844ms
~~~

Đây là các dòng đại diện từ một lần chạy kiểm tra OpenJDK 24.0.2. Timestamp, GC ID, heap usage và duration thay đổi theo môi trường.

Diễn giải:

- Young GC thu gom object tạm và giảm heap usage.
- Full GC được khởi tạo bởi lời gọi System.gc().
- Heap sau Full GC vẫn còn khoảng 4 MB vì static list giữ lại các array.
- Capacity là 32 MB theo cấu hình -Xms/-Xmx.
- Pause duration trong ví dụ rất ngắn vì heap nhỏ và workload đơn giản.

Tìm các collection:

~~~powershell
Select-String -Path .\gc.log -Pattern "Pause Young|Pause Full"
~~~

Tìm heap initialization và Metaspace:

~~~powershell
Select-String -Path .\gc.log -Pattern "Heap Max Capacity|Metaspace"
~~~

### Thử thay đổi

Có thể chạy lại với heap lớn hơn:

~~~bash
java -Xms64m -Xmx64m -XX:+UseG1GC "-Xlog:gc*=info:file=gc-64m.log:time,uptime,level,tags" GcLogDemo
~~~

So sánh số lần Young GC, heap before/after và pause. Heap lớn hơn có thể giảm tần suất collection nhưng không tự động làm ứng dụng tốt hơn; nó có thể tăng footprint hoặc thay đổi pause behavior.

Có thể chạy với log phase chi tiết:

~~~bash
java -Xms32m -Xmx32m -XX:+UseG1GC "-Xlog:gc*=info,gc+phases=debug:file=gc-detail.log:time,uptime,level,tags" GcLogDemo
~~~

So sánh tổng pause với từng phase để hiểu GC dành thời gian ở đâu.

## 19. Troubleshooting theo dấu hiệu trong log

### GC xảy ra liên tục

- Xem khoảng cách giữa các Young GC.
- Xem allocation rate bằng JFR.
- Tìm method tạo nhiều object.
- Kiểm tra heap size và workload.
- Giảm allocation không cần thiết trước khi thay collector.

### Heap sau GC tăng qua từng chu kỳ

- Xem old regions và live set.
- Kiểm tra cache, session, queue và static collection.
- Dùng class histogram và heap dump.
- Tìm paths to GC roots bằng MAT.
- So sánh cùng workload qua thời gian.

### Full GC kéo dài

- Xác định cause: explicit GC, allocation pressure hoặc tình trạng old generation.
- Kiểm tra evacuation failure trước đó.
- Xem concurrent marking có hoàn thành kịp không.
- Kiểm tra humongous allocation và fragmentation.
- Kiểm tra lượng object còn sống và CPU availability.

### Pause vượt SLO

- Xem phase breakdown.
- Xem User/Sys/Real.
- Kiểm tra heap size và collection set.
- Kiểm tra CPU throttling, scheduling và memory pressure.
- Đối chiếu safepoint và request latency.
- Không chỉ giảm MaxGCPauseMillis mà không hiểu nguyên nhân.

### Metaspace tăng liên tục

- Xem class load/unload counters.
- Kiểm tra class loader statistics.
- Điều tra plugin, redeploy và dynamic proxy.
- Dùng heap dump/JFR để tìm loader còn reachable.
- Kiểm tra giới hạn Metaspace và native memory.

### Không thấy GC event trong log

- Xác nhận đúng JVM và đúng file.
- Kiểm tra -Xlog selection có chọn tag gc không.
- Kiểm tra level, output path và quyền ghi.
- Kiểm tra rotation và file archive.
- Xem jcmd <pid> VM.log list nếu dùng dynamic logging.
- Xác nhận JVM có thực sự thực hiện GC trong khoảng quan sát.

### GC log quá lớn

- Giảm từ gc*=debug/trace về info.
- Chỉ bật phase/tag cần thiết.
- Bật file rotation.
- Giảm thời gian recording.
- Thiết lập retention và lưu trữ an toàn.

## 20. Quy trình phân tích GC log hoàn chỉnh

1. Xác định service, JVM PID, JDK version và collector đang dùng.
2. Thu thập GC log trong workload đại diện.
3. Ghi timestamp, uptime, PID và tags.
4. Xác nhận log có đầy đủ các collection trong khoảng cần điều tra.
5. Tính số lần GC, khoảng cách và pause duration.
6. Xem heap before/after và capacity.
7. Theo dõi old generation, survivor, humongous regions và Metaspace.
8. Tìm Full GC, evacuation failure và allocation failure.
9. Bật gc+phases và gc+cpu khi cần phân tích pause.
10. Dùng safepoint log nếu thời gian dừng không được giải thích bởi GC summary.
11. Kết hợp JFR để xem allocation, thread và CPU.
12. Dùng heap dump/MAT nếu cần tìm object retention.
13. Đối chiếu với application latency, throughput, error rate và OS/container metrics.
14. Đưa ra giả thuyết và chỉ thay đổi một yếu tố chính mỗi lần.
15. Ghi lại baseline và so sánh lại sau tối ưu.
16. Lưu log theo retention policy và bảo vệ dữ liệu nội bộ.

## 21. Checklist GC log

- Xác định đúng JDK và garbage collector.
- Dùng Unified Logging với -Xlog.
- Bắt đầu bằng gc*=info khi cần tổng quan.
- Thêm gc+phases=debug khi cần phase breakdown.
- Thêm gc+heap, gc+cpu và safepoint khi phù hợp.
- Ghi time, uptime, level, tags và PID nếu cần.
- Bật rotation và kiểm soát dung lượng.
- Đọc GC ID, cause, heap before/after/capacity và duration.
- Phân biệt Young, Mixed, Concurrent và Full GC.
- Kiểm tra evacuation failure và humongous regions.
- Theo dõi heap sau GC và Metaspace theo thời gian.
- Không kết luận memory leak từ một dòng log.
- Không áp dụng cách đọc G1 cho mọi collector.
- Kết hợp JFR, heap dump, metrics và tracing.
- So sánh cùng workload trước và sau thay đổi.
- Bảo vệ log và áp dụng retention policy.

## 22. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| GC log | Nhật ký hoạt động garbage collection |
| Unified Logging | Hệ thống logging của HotSpot dùng cú pháp -Xlog |
| GC ID | Định danh một collection và các dòng liên quan |
| Young GC | Collection vùng young generation |
| Mixed GC | G1 collection gồm young và một số old regions |
| Full GC | Collection toàn heap, thường có pause dài |
| Concurrent marking | Giai đoạn đánh dấu object trong khi application tiếp tục chạy |
| Evacuation | Di chuyển live objects khỏi collection set |
| Evacuation failure | Không thể di chuyển một số object trong collection |
| Humongous object | Object có kích thước ít nhất bằng nửa G1 region |
| Heap occupancy | Mức sử dụng heap |
| Capacity | Dung lượng heap hiện tại được log |
| Metaspace | Native memory chứa class metadata |
| Safepoint | Điểm JVM có thể dừng các application threads an toàn |
| Pause duration | Thời gian application bị dừng trong pause |
| Allocation rate | Lượng object/bộ nhớ được cấp phát theo thời gian |
| Promotion | Chuyển object sống lâu sang old generation |
| JFR | Java Flight Recorder |
| JMC | JDK Mission Control |
| GC tuning | Điều chỉnh collector, heap và allocation để đáp ứng mục tiêu |

Phân tích GC log bắt đầu từ việc đọc đúng collection type, cause, heap before/after và pause duration. Khi cần tìm nguyên nhân, mở rộng sang phase breakdown, CPU, safepoint, JFR và heap analysis. Chỉ thay đổi GC hoặc heap sau khi dữ liệu chỉ ra bottleneck cụ thể và luôn đo lại trên workload tương đương.

## Tài liệu tham khảo

- Oracle JDK 24 — Garbage Collector Implementation: https://docs.oracle.com/en/java/javase/24/gctuning/garbage-collector-implementation.html
- Oracle JDK 24 — G1 Garbage Collector: https://docs.oracle.com/en/java/javase/24/gctuning/garbage-first-g1-garbage-collector1.html
- Oracle JDK 24 — G1 GC Tuning: https://docs.oracle.com/en/java/javase/24/gctuning/garbage-first-garbage-collector-tuning.html
- Oracle JDK 24 — The java Command and -Xlog: https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html
- Oracle JDK 24 — The jcmd Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jcmd.html
- Oracle JDK 24 — Troubleshooting Guide: https://docs.oracle.com/en/java/javase/24/troubleshoot/troubleshooting-guide.pdf