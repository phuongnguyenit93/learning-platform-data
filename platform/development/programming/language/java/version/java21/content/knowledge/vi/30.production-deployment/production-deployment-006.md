# Cấu hình GC và quan sát theo workload đã đo

Không nên chọn Garbage Collector (GC) chỉ theo một lời khuyên chung như “ưu tiên latency” hoặc “heap càng lớn càng tốt”. Hãy dùng số liệu load test để xác định mục tiêu của service, sau đó chọn collector và cấu hình heap phù hợp với workload, giới hạn CPU/bộ nhớ của môi trường triển khai và SLA thực tế.

Trong Java 21, G1 là collector mặc định cho cấu hình server-class thông thường. Parallel GC phù hợp khi ưu tiên throughput và chấp nhận pause dài hơn; ZGC hướng đến độ trễ thấp với công việc concurrent nhiều hơn. Generational ZGC có trong Java 21 nhưng cần bật tường minh bằng `-XX:+UseZGC -XX:+ZGenerational`. Sau khi chọn, phải quan sát GC log, JFR, heap, CPU và latency ứng dụng trong cùng một khoảng thời gian.

## 1. Bắt đầu từ workload và mục tiêu đã đo

Trước khi đổi GC, xác định service đang cần cải thiện điều gì:

| Mục tiêu/workload | Collector nên đưa vào thử nghiệm | Lý do và điều cần đánh giá |
| --- | --- | --- |
| Ứng dụng server tổng quát, cân bằng throughput và pause | G1 | Lựa chọn mặc định phổ biến; có cơ chế điều chỉnh vùng thu gom để hướng đến mục tiêu pause. |
| Throughput cao, batch hoặc xử lý nền, pause dài có thể chấp nhận | Parallel GC | Dùng nhiều thread cho công việc thu gom; đo tổng CPU và thời gian dừng ứng dụng. |
| SLA latency chặt, heap lớn hoặc nhiều request đồng thời | ZGC | Công việc thu gom chủ yếu concurrent, hướng đến pause rất ngắn; cần đánh giá CPU và headroom bộ nhớ. |
| Ứng dụng nhỏ, ít thread, heap nhỏ hoặc môi trường đơn giản | Serial GC | Cấu trúc đơn giản, overhead thấp trong một số workload nhỏ; không phù hợp mặc định cho server nhiều CPU. |

Đây là danh sách lựa chọn để benchmark, không phải kết luận collector nào luôn tốt hơn. Cùng một collector có thể hoạt động khác nhau tùy allocation rate, live set, tỷ lệ object sống lâu, kích thước heap, CPU quota, NUMA, downstream latency và cách service tạo object.

Nếu chưa có bằng chứng GC đang cản trở SLA hoặc resource budget, hãy bắt đầu bằng collector JVM tự chọn theo ergonomics. Chỉ override collector khi baseline và phép thử có kiểm soát cho thấy lựa chọn khác cải thiện mục tiêu cụ thể.

Hãy dùng số liệu load test để trả lời:

- p95/p99 tăng có trùng thời điểm GC pause hay không?
- Throughput có giảm trong các chu kỳ GC hoặc khi GC tiêu thụ CPU cao không?
- Heap sau GC có xu hướng tăng dần, hay dao động quanh một mức ổn định?
- Allocation rate có vượt khả năng thu hồi của collector không?
- Service có đủ CPU headroom cho công việc concurrent của collector không?
- Container có đủ bộ nhớ ngoài Java heap cho thread stack, direct buffer, metaspace và native allocation không?

Nếu p99 tăng do database pool cạn hoặc downstream chậm, đổi GC có thể không giải quyết được vấn đề. Luôn ghép GC telemetry với request latency, queue wait, CPU và pool metrics.

## 2. Các collector hiện hành cần biết trong Java 21

### G1 GC

G1 chia heap thành các region và thu gom những vùng được đánh giá có lợi nhất trong giới hạn mục tiêu pause. G1 cân bằng throughput và pause nên phù hợp với nhiều ứng dụng server tổng quát; đây là mặc định của các cấu hình server-class trong Java 21.

Có thể bật rõ ràng:

```shell
-XX:+UseG1GC
```

G1 hỗ trợ `-XX:MaxGCPauseMillis` như một mục tiêu mềm để JVM điều chỉnh hoạt động thu gom. Đây không phải cam kết mọi pause đều thấp hơn con số cấu hình. Nếu workload cấp phát quá nhanh, live set lớn, CPU thiếu hoặc heap không đủ headroom, G1 vẫn có thể vượt mục tiêu.

```shell
-XX:+UseG1GC -XX:MaxGCPauseMillis=200
```

Chỉ thử thay đổi pause target sau khi có baseline. Mục tiêu pause thấp hơn có thể làm collector thu gom thường xuyên hơn và giảm throughput; mục tiêu cao hơn có thể cải thiện throughput nhưng tăng pause. Đánh giá bằng latency percentile và CPU thay vì chỉ xem giá trị flag.

### Parallel GC

Parallel GC dùng nhiều worker để thu gom heap theo các pha stop-the-world, ưu tiên throughput. Nó có thể phù hợp với batch, tác vụ xử lý nền hoặc service không có yêu cầu pause nghiêm ngặt.

```shell
-XX:+UseParallelGC
```

Với Parallel GC, cần quan sát thời gian pause, tổng thời gian GC, CPU GC và throughput. Nếu ứng dụng nhạy với tail latency, pause dài có thể làm p99 xấu dù tổng throughput cao.

### ZGC và Generational ZGC

ZGC hướng đến pause ngắn bằng cách thực hiện phần lớn công việc thu gom đồng thời với ứng dụng. Đổi lại, collector cần CPU cho công việc concurrent và có thể cần thêm headroom bộ nhớ. Vì vậy, ZGC không mặc nhiên làm ứng dụng nhanh hơn; nó phù hợp khi pause là một phần đáng kể của SLA và CPU/memory budget cho phép.

Trong Java 21, Generational ZGC là chế độ nên đưa vào thử nghiệm cho triển khai mới khi workload cần latency thấp. Bật chế độ này tường minh:

```shell
-XX:+UseZGC -XX:+ZGenerational
```

Generational ZGC phân biệt young và old generation để tối ưu cho đặc tính phổ biến là nhiều object có vòng đời ngắn. Khi đánh giá, cần xem allocation rate, young/old collection, promotion, heap headroom và CPU. Không suy luận chỉ từ startup banner `Using The Z Garbage Collector`, vì banner này không cho biết chế độ generational. Nếu đang chẩn đoán một process Java 21 cũ chỉ có `-XX:+UseZGC`, cần biết nó đang chạy chế độ non-generational; đây là thông tin tương thích khi đọc cấu hình hiện hữu, không phải cấu hình khuyến nghị cho triển khai mới.

ZGC được thiết kế để tự điều chỉnh; trong nhiều workload, `-Xmx` là tuning knob quan trọng nhất. Heap phải đủ chỗ cho live set và allocation phát sinh trong khi collector làm việc concurrent. Nếu heap quá sát live set, ứng dụng có thể gặp allocation stall dù pause vẫn ngắn. Việc đặt `-Xms` bằng `-Xmx` hoặc thay đổi chính sách uncommit có thể hữu ích với một workload nhạy latency, nhưng làm JVM giữ nhiều bộ nhớ hơn; chỉ cân nhắc sau khi đo được chi phí commit/uncommit và memory headroom.

Các phiên bản JDK sau Java 21 đã thay đổi mặc định và vòng đời flag của Generational ZGC. Khi triển khai đúng Java 21, hãy dùng tài liệu của đúng JDK 21 update đang chạy và xác minh flags thực tế; không sao chép cấu hình từ JDK mới hơn mà không kiểm tra tương thích.

### Serial GC

Serial GC thực hiện công việc thu gom trên một thread. Nó có thể hợp lý cho ứng dụng nhỏ hoặc môi trường ít CPU, nhưng thường không phải lựa chọn cho service nhiều request đồng thời cần throughput cao.

```shell
-XX:+UseSerialGC
```

Chỉ chọn Serial khi benchmark cho thấy footprint/overhead thấp có lợi và pause phù hợp với yêu cầu. Không dùng nó chỉ vì ứng dụng chạy trong container nhỏ mà chưa đo.

## 3. Chọn heap theo live set và giới hạn container

`-Xms` đặt initial heap size và `-Xmx` đặt maximum heap size. Hai giá trị này cần được xác định từ live set sau GC, allocation rate, mức concurrency và bộ nhớ còn lại cho native memory.

```shell
-Xms2g -Xmx2g
```

Ví dụ trên chỉ minh họa cách cố định initial/maximum heap ở 2 GiB; không phải khuyến nghị cho mọi service. Đặt `Xms` bằng `Xmx` có thể làm heap ổn định hơn trong một số môi trường, nhưng cũng khiến JVM giữ trước một vùng heap lớn. Hãy kiểm tra giới hạn bộ nhớ container và mức dùng thực tế.

Không đặt `-Xmx` bằng toàn bộ memory limit của container. Tổng bộ nhớ process còn bao gồm:

- Java heap: object, array và các cấu trúc dữ liệu của ứng dụng.
- Metaspace và class metadata.
- Thread stack của platform threads và các native thread.
- Direct buffer, TLS/network buffer và native allocation của thư viện.
- JIT code cache, GC metadata, JVM internal structures và thư viện native.
- Bộ nhớ phụ trợ của agent, profiler hoặc instrumentation.

Nếu heap chiếm gần hết container limit, process có thể bị kernel/container runtime kill trước khi JVM ném `OutOfMemoryError`. Chừa headroom dựa trên số liệu RSS/container memory peak trong load test, không chỉ dựa trên `Runtime.maxMemory()`.

### Dùng tỷ lệ RAM khi môi trường có memory limit động

JVM hiện đại có thể nhận biết giới hạn container trên nền tảng được hỗ trợ. Có thể dùng `-XX:MaxRAMPercentage` để đặt tỷ lệ maximum heap so với RAM mà JVM nhận diện:

```shell
-XX:MaxRAMPercentage=60
```

Giá trị 60 ở đây chỉ là ví dụ. Không có một tỷ lệ đúng cho mọi container; phải tính cả native memory, thread stack, direct buffer và agent. Kiểm tra `VM.flags -all`, `VM.info` và số liệu container để xác nhận JVM nhìn thấy giới hạn RAM nào. Nếu deployment platform thay đổi memory limit, hãy đo lại heap ergonomics thay vì giả định giá trị cũ vẫn phù hợp.

## 4. Không tinh chỉnh nhiều GC flags cùng lúc

Một quy trình tuning có thể lặp lại:

1. Ghi baseline với collector và heap hiện tại.
2. Xác định triệu chứng bằng latency, throughput, GC log, CPU và heap.
3. Chỉ thay đổi một nhóm cấu hình có mục tiêu rõ, ví dụ collector hoặc heap maximum.
4. Chạy cùng workload, cùng duration, cùng môi trường và cùng load model.
5. So sánh p95/p99, throughput, error rate, GC pause, GC CPU và memory peak.
6. Giữ thay đổi chỉ khi cải thiện mục tiêu mà không làm xấu các giới hạn khác.

Với G1, tránh ép kích thước young generation bằng các flag như `-Xmn` khi chưa có bằng chứng cụ thể; việc này có thể làm giảm khả năng tự điều chỉnh của G1. Không chỉnh `ParallelGCThreads`, `ConcGCThreads`, region size hoặc các flag nội bộ theo cảm tính. JVM đã có ergonomics dựa trên CPU, heap và workload; chỉ override khi dữ liệu cho thấy mặc định không phù hợp.

## 5. Bật Unified GC Logging trong production

Java 21 dùng Unified JVM Logging. Cấu hình cơ bản:

```shell
-Xlog:gc*:file=/var/log/my-service/gc.log:time,uptime,level,tags:filecount=5,filesize=20M
```

Thiết lập này ghi GC events vào file, có timestamp/uptime/level/tags và xoay vòng tối đa năm file với kích thước mục tiêu 20 MB mỗi file. Thư mục phải tồn tại và process phải có quyền ghi. Trong container, cân nhắc ghi ra stdout/stderr để nền tảng log tập trung thu thập, hoặc mount volume có quota và rotation rõ ràng.

Nếu cần quan sát safepoint cùng GC:

```shell
-Xlog:gc*,safepoint:file=/var/log/my-service/gc.log:time,uptime,level,tags:filecount=5,filesize=20M
```

Chỉ tăng log level khi cần chẩn đoán sâu:

```shell
-Xlog:gc*=debug:file=/var/log/my-service/gc-debug.log:time,uptime,level,tags:filecount=3,filesize=30M
```

Không để log debug/trace vô thời hạn nếu chưa đánh giá dung lượng và overhead. Với cấu hình Java 21 mới, dùng Unified Logging để có một cơ chế thống nhất cho GC và safepoint events.

## 6. Đọc GC log theo câu hỏi cần trả lời

Đừng chỉ đếm số dòng GC. Ghép các event với khoảng thời gian load test và xem:

| Chỉ số/sự kiện | Câu hỏi cần trả lời |
| --- | --- |
| GC pause duration | Ứng dụng bị dừng bao lâu ở từng pause? p95/p99 pause có liên quan request tail latency không? |
| Collection frequency | GC chạy dày lên khi concurrency hoặc allocation tăng hay không? |
| Heap before/after collection | Sau khi thu gom, heap giảm về mức ổn định hay live set tiếp tục tăng? |
| Allocation rate | Tốc độ tạo object có vượt khả năng thu gom trong điều kiện hiện tại không? |
| Promotion/old generation | Object sống lâu có tăng nhanh và làm old generation đầy không? |
| Concurrent cycle/GC CPU | Collector có tiêu thụ quá nhiều CPU cạnh tranh với application threads không? |
| Full GC/allocation stall | Có tình huống áp lực bộ nhớ nghiêm trọng hoặc ứng dụng phải chờ GC hay không? |
| Safepoint | Có pause do hoạt động JVM khác ngoài GC làm tăng latency không? |

Với G1, quan sát thêm humongous allocations, mixed collections, evacuation failure và old-generation occupancy. Với Generational ZGC, phân biệt minor và major collection, xem allocation stall và thời gian concurrent work. Tên event và mức chi tiết cụ thể phụ thuộc collector/JDK update; không viết parser chỉ dựa vào một chuỗi log duy nhất.

Một lần GC ngắn không tự chứng minh GC là bottleneck. Cần đối chiếu timestamp với request latency và CPU. Nếu p99 tăng nhưng không có pause tương ứng, nguyên nhân có thể nằm ở queue, lock contention, downstream, CPU throttling hoặc scheduling.

## 7. Quan sát JFR và diagnostic commands

Java Flight Recorder (JFR) cung cấp dữ liệu về GC, allocation, CPU, locks, I/O và runtime events. Có thể bắt đầu một recording ngắn trên process đang chạy:

```shell
jcmd <pid> JFR.start name=production-observation settings=profile duration=5m filename=production-observation.jfr
```

Sau khi recording hoàn tất:

```shell
jfr summary production-observation.jfr
jfr print --events jdk.GarbageCollection production-observation.jfr
```

JFR `profile` phù hợp cho một lượt quan sát có mục tiêu, nhưng vẫn có overhead và có thể thu dữ liệu nhạy cảm về stack, class hoặc workload. Bảo vệ file recording như artifact production; giới hạn quyền truy cập và thời gian lưu. Khi so sánh hai collector, dùng cùng cấu hình recording hoặc có thêm lượt không recording để ước lượng overhead.

Các lệnh `jcmd` hữu ích khi kiểm tra process:

```shell
jcmd <pid> VM.version
jcmd <pid> VM.command_line
jcmd <pid> VM.flags -all
jcmd <pid> GC.heap_info
```

- `VM.version`: xác nhận runtime thực tế.
- `VM.command_line`: kiểm tra đối số JVM đã truyền.
- `VM.flags -all`: kiểm tra giá trị flags cuối cùng, gồm collector và heap settings.
- `GC.heap_info`: xem thông tin heap theo collector/runtime.

Chạy `jcmd` với quyền và process namespace phù hợp, đặc biệt trong container. Không dùng `System.gc()` hoặc diagnostic command gây full collection làm cách đo GC định kỳ; thao tác cưỡng bức có thể làm sai lệch kết quả workload.

## 8. Phân biệt heap và native memory

Heap usage ổn định không đồng nghĩa process memory ổn định. Nếu RSS/container memory tăng nhưng heap không tăng tương ứng, hãy xem native memory, direct buffer, thread stack, metaspace, code cache và thư viện native.

Có thể bật Native Memory Tracking (NMT) khi khởi động:

```shell
-XX:NativeMemoryTracking=summary
```

Sau đó lấy baseline và xem chênh lệch:

```shell
jcmd <pid> VM.native_memory baseline
jcmd <pid> VM.native_memory summary
jcmd <pid> VM.native_memory summary.diff
```

NMT có overhead và phải được bật từ lúc JVM khởi động. NMT giúp phân loại một số nhóm native memory do JVM quản lý, nhưng không phải công cụ đo toàn bộ mọi allocation native của mọi thư viện. Đối chiếu thêm container RSS, direct buffer metrics và công cụ hệ điều hành.

## 9. Bảo vệ heap dump và xử lý OOM

Trong production, có thể cấu hình JVM tạo heap dump khi gặp `OutOfMemoryError`:

```shell
-XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/var/lib/my-service/heapdumps
```

Thư mục phải tồn tại, có quyền ghi và đủ dung lượng. Heap dump có thể chứa token, dữ liệu cá nhân, request payload hoặc thông tin xác thực đang nằm trong heap. Hãy giới hạn quyền truy cập, mã hóa nơi lưu trữ nếu cần, đặt retention và xóa theo chính sách bảo mật.

Phân biệt Java heap OOM với container OOM kill. Nếu kernel/container runtime kill process do vượt memory limit, JVM có thể không có cơ hội tạo heap dump hoặc ghi log. Vì vậy phải theo dõi cả heap metrics và memory usage của container.

## 10. Ví dụ cấu hình khởi chạy theo hai mục tiêu

### Service tổng quát dùng G1

```shell
java \
  -Xms2g -Xmx2g \
  -XX:+UseG1GC \
  -XX:MaxGCPauseMillis=200 \
  -Xlog:gc*,safepoint:file=/var/log/my-service/gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar my-service.jar
```

Đây là cấu hình minh họa cho một service đã được đo với heap 2 GiB và mục tiêu pause mềm 200 ms. Hãy thay dung lượng heap và pause target bằng số liệu của ứng dụng. Không xem 200 ms là SLA được bảo đảm.

### Service latency-sensitive thử Generational ZGC trên Java 21

```shell
java \
  -Xms4g -Xmx4g \
  -XX:+UseZGC -XX:+ZGenerational \
  -Xlog:gc*,safepoint:file=/var/log/my-service/gc.log:time,uptime,level,tags:filecount=5,filesize=20M \
  -jar my-service.jar
```

Chỉ dùng cấu hình này sau khi load test cho thấy pause là một phần đáng kể của tail latency và container còn đủ CPU/memory headroom. Generational ZGC trong Java 21 cần được bật tường minh. Kiểm tra startup log và `jcmd <pid> VM.flags -all` để xác minh đúng collector và chế độ.

Không đưa cả hai ví dụ vào cùng một JVM. Chọn một collector cho mỗi lượt benchmark và giữ workload/configuration còn lại nhất quán.

## 11. Đưa thay đổi GC vào production an toàn

Thay đổi GC hoặc heap size có thể làm thay đổi CPU, memory footprint, startup behavior và tail latency. Áp dụng theo từng bước:

1. Lưu lại baseline hiện tại: JDK build, flags, heap, container limit, GC log, JFR, p95/p99 và throughput.
2. Chạy benchmark/load test trên môi trường gần production với workload đại diện.
3. Chọn một collector/configuration candidate và chỉ thay đổi các flags cần thiết.
4. Triển khai canary trên một phần nhỏ traffic hoặc một instance riêng.
5. Theo dõi error rate, latency percentile, CPU, RSS, heap, GC pause, allocation và downstream pool.
6. Mở rộng rollout nếu các chỉ số đạt mục tiêu và không chạm resource limit.
7. Rollback flags/phiên bản nếu p99, OOM, CPU hoặc error rate vượt ngưỡng đã định trước.

Giữ GC logs có timestamp và gắn với instance/deployment version để có thể so sánh trước/sau. Khi chạy nhiều replica, không gộp mọi log vào một file không có nhận diện instance; điều đó làm mất khả năng đối chiếu sự kiện với process.

## 12. Lỗi thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Chọn GC theo benchmark của workload khác | Kết quả không phản ánh allocation/live set của service. | Đo workload thực tế và so sánh trong cùng môi trường. |
| Chỉ nhìn average pause | Bỏ qua tail latency. | Theo dõi p95/p99 request latency và phân phối pause. |
| Đặt `-Xmx` bằng toàn bộ memory limit | Container có thể OOM kill vì native memory và thread stacks. | Chừa headroom và đo RSS/container memory peak. |
| Nghĩ G1 pause target là cam kết | JVM không thể bảo đảm mọi pause luôn dưới ngưỡng. | Xem đây là mục tiêu mềm và đo thực tế. |
| Bật ZGC nhưng quên `ZGenerational` trên Java 21 | JVM chạy ZGC non-generational. | Bật `-XX:+UseZGC -XX:+ZGenerational` và xác minh flags. |
| Nghĩ startup banner ZGC chứng minh generational mode | Banner không phân biệt hai chế độ trên Java 21. | Kiểm tra `ZGenerational` và GC events. |
| Tinh chỉnh nhiều flags cùng lúc | Không biết thay đổi nào tạo ra kết quả. | Thay từng nhóm có giả thuyết và đo lại. |
| Dùng GC log cũ/legacy cho cấu hình mới | Thiếu tính nhất quán với Java 21 Unified Logging. | Dùng `-Xlog:gc*`. |
| Chỉ theo dõi heap | Bỏ sót native memory hoặc container OOM kill. | Theo dõi RSS, NMT, direct buffer và container metrics. |
| Cưỡng bức `System.gc()` trong benchmark | Làm sai lệch workload và pause. | Để collector chạy theo workload tự nhiên. |
| Thu JFR/heap dump rồi lưu công khai | Có thể lộ dữ liệu nhạy cảm. | Giới hạn quyền, retention và nơi lưu trữ. |

## 13. Checklist trước khi phát hành cấu hình GC

1. Ghi rõ JDK vendor, version và update đang chạy trong production.
2. Có baseline workload với offered rate, throughput, p95/p99, errors và CPU.
3. Biết live set sau GC, allocation rate và heap headroom ở peak load.
4. Chọn collector theo SLA, không theo một con số benchmark riêng lẻ.
5. Đặt `Xms`/`Xmx` hoặc RAM percentage sao cho còn native/container headroom.
6. Bật Unified GC Logging có timestamp và log rotation.
7. Dùng JFR/jcmd khi cần phân tích sâu; bảo vệ recording và heap dump.
8. Với Generational ZGC trên Java 21, bật và xác minh `UseZGC` cùng `ZGenerational`.
9. Thay đổi từng bước, canary và đặt rollback thresholds.
10. Kiểm tra lại sau khi thay đổi workload, CPU/memory limit hoặc JDK update.

## 14. Tài liệu tham khảo chính thức

- [Java SE 21 — Available Collectors](https://docs.oracle.com/en/java/javase/21/gctuning/available-collectors.html): các collector và lựa chọn theo workload.
- [Java SE 21 — G1 Garbage Collector](https://docs.oracle.com/en/java/javase/21/gctuning/garbage-first-garbage-collector.html): hoạt động và tuning G1.
- [Java SE 21 — Parallel Collector](https://docs.oracle.com/en/java/javase/21/gctuning/parallel-collector1.html): throughput-oriented collector.
- [Java SE 21 — Z Garbage Collector](https://docs.oracle.com/en/java/javase/21/gctuning/z-garbage-collector2.html): ZGC và Generational ZGC trên Java 21.
- [JEP 439 — Generational ZGC](https://openjdk.org/jeps/439): thiết kế Generational ZGC trong JDK 21.
- [Java SE 21 — `java` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html): heap, GC và Unified Logging options.
- [Java SE 21 — `jcmd` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jcmd.html): diagnostic commands cho JVM đang chạy.
- [Java SE 21 — `jfr` command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): phân tích Flight Recording.
- [Java SE 21 — Native Memory Tracking](https://docs.oracle.com/en/java/javase/21/vm/native-memory-tracking.html): theo dõi một số nhóm native memory của JVM.
