# Dùng unified logging -Xlog:gc* để đọc chu kỳ và pause của collector

## 1. Vì sao cần đọc GC log?

Garbage Collection (GC) thu hồi vùng nhớ heap mà ứng dụng không còn sử dụng. Với collector có các pha Stop-The-World (STW), JVM tạm dừng các luồng ứng dụng trong một khoảng thời gian để thực hiện công việc cần thiết. Những lần dừng này có thể làm tăng response time, tạo request timeout hoặc khiến độ trễ p95/p99 xấu đi.

GC log giúp trả lời:

- GC xảy ra bao nhiêu lần, vào thời điểm nào và vì nguyên nhân gì?
- Mỗi lần pause kéo dài bao lâu? Pha nào chiếm nhiều thời gian?
- Heap trước và sau GC thay đổi ra sao?
- Có Full GC, evacuation failure, allocation failure hoặc chu kỳ concurrent kéo dài không?
- Pause dài do công việc GC, thiếu CPU, hệ điều hành, safepoint hay I/O ghi log?

Từ JDK 9, JVM cung cấp Unified Logging qua tùy chọn `-Xlog`. Đây là cơ chế hiện hành để thu thập GC log trên JDK 16 và các JDK mới hơn. Cấu hình `-Xlog:gc*` thay thế cách bật log chi tiết bằng `-XX:+PrintGCDetails` trong các hướng dẫn cũ.

GC log là bằng chứng để chẩn đoán, không tự động chỉ ra một flag cần chỉnh. Hãy đọc chu kỳ và xu hướng dưới workload thực tế trước khi thay đổi heap hoặc collector.

## 2. Cú pháp cơ bản của Unified Logging

Cú pháp tổng quát:

~~~text
-Xlog:<what>:<output>:<decorators>:<output-options>
~~~

Trong đó:

| Thành phần | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `what` | Tag set và mức log cần lấy | `gc*`, `gc=debug`, `gc+phases=debug` |
| `output` | Nơi ghi log | `stdout`, `stderr`, `file=logs/gc.log` |
| `decorators` | Thông tin gắn trước mỗi dòng | `time,uptime,level,tags` |
| `output-options` | Tùy chọn file như rotation | `filecount=5,filesize=20M` |

Một log entry có tag set và level. Các level phổ biến là `error`, `warning`, `info`, `debug`, `trace` và `off`. Level càng chi tiết thì lượng log có thể càng lớn.

Có thể xem cú pháp, tag, level và decorator được JVM hiện tại hỗ trợ:

~~~powershell
java -Xlog:help
~~~

Danh sách tag có thể khác theo JDK build và collector. Dùng `-Xlog:help` trên chính runtime sẽ chạy ứng dụng để xác nhận tag hợp lệ.

## 3. Hiểu tag gc và wildcard gc*

`gc` là tag dùng cho thông tin garbage collection. Ví dụ:

~~~powershell
java -Xlog:gc -jar app.jar
~~~

Lệnh này lấy các log entry có tag set chính xác là `gc` ở level mặc định `info`.

`gc*` dùng wildcard để chọn các tag set có chứa tag `gc`, bao gồm các nhóm như `gc,heap`, `gc,phases`, `gc,cpu` hoặc các tag set khác được JVM cung cấp:

~~~powershell
java -Xlog:gc* -jar app.jar
~~~

Vì vậy, `-Xlog:gc*` cho góc nhìn rộng hơn `-Xlog:gc`. Đây là cấu hình khởi đầu hữu ích khi cần đọc chu kỳ GC, thông tin heap và các pha liên quan.

Wildcard chỉ chọn các tag set khớp với `gc`; nó không bật mọi log của JVM. Các nhóm như safepoint, class loading hoặc JIT có thể cần lựa chọn riêng.

## 4. Bật GC log ra file có timestamp và rotation

Trong production, nên ghi log ra file có rotation để tránh ghi vô hạn vào một file:

~~~powershell
New-Item -ItemType Directory -Force logs | Out-Null
java "-Xlog:gc*:file=logs/gc-%p-%t.log:time,uptime,level,tags:filecount=5,filesize=20M" -jar app.jar
~~~

Ý nghĩa:

- `file=logs/gc-%p-%t.log`: ghi vào file; `%p` được thay bằng PID và `%t` bằng thời điểm JVM khởi động.
- `time`: thời gian thực theo định dạng ngày giờ.
- `uptime`: thời gian tính từ lúc JVM khởi động.
- `level`: level của log entry.
- `tags`: tag set của log entry.
- `filecount=5`: giữ tối đa năm file trong chu kỳ rotation.
- `filesize=20M`: kích hoạt rotation khi file đạt kích thước mục tiêu khoảng 20 MB.

Kích thước rotation là mục tiêu gần đúng, không phải giới hạn byte tuyệt đối. Nếu thư mục log chưa tồn tại, hãy tạo thư mục trước khi khởi chạy JVM. Bảo đảm tài khoản chạy ứng dụng có quyền ghi và hệ thống thu thập log có chính sách lưu trữ phù hợp.

Có thể dùng `uptime` để sắp xếp sự kiện trong cùng một lần chạy và `time` để đối chiếu với log ứng dụng, metric, trace hoặc sự cố bên ngoài. PID và thời điểm khởi động giúp phân biệt log của nhiều JVM hoặc nhiều lần restart.

## 5. Chọn mức log phù hợp: info, debug và trace

Nên bắt đầu với log nền ở mức `info`:

~~~powershell
java "-Xlog:gc*:file=logs/gc.log:time,uptime,level,tags:filecount=5,filesize=20M" -jar app.jar
~~~

Khi phát hiện pause dài hoặc GC bất thường, tăng chi tiết trong một lần chạy điều tra:

~~~powershell
java "-Xlog:gc*=debug:file=logs/gc-debug.log:time,uptime,level,tags:filecount=5,filesize=50M" -jar app.jar
~~~

Với G1, Oracle khuyến nghị `-Xlog:gc*=debug` như điểm bắt đầu khi cần xem chi tiết hoạt động trong và ngoài pause. Log sẽ cung cấp loại collection và thời gian của các pha trong pause.

Có thể chỉ tăng chi tiết cho một nhóm cụ thể:

~~~powershell
java "-Xlog:gc*,gc+phases=debug:file=logs/gc-phases.log:time,uptime,level,tags:filecount=5,filesize=30M" -jar app.jar
~~~

Ví dụ trên giữ thông tin GC nền và tăng mức log cho nhóm `gc+phases`. Cách chọn cụ thể phụ thuộc tag mà collector phát ra; kiểm tra bằng `-Xlog:help` và log thực tế.

Không bật `trace` cho toàn bộ tag GC trong thời gian dài nếu chưa cần thiết. Log quá chi tiết có thể tăng I/O, dung lượng lưu trữ và độ khó khi phân tích.

## 6. Đọc cấu trúc một GC event

Một dòng log GC thường có các phần:

~~~text
[4.344s][info][gc,start] GC(46) Pause Full (Ergonomics)
~~~

Diễn giải:

- `[4.344s]`: JVM đã chạy được khoảng 4,344 giây.
- `[info]`: level của log.
- `[gc,start]`: tag set mô tả nhóm sự kiện.
- `GC(46)`: mã định danh của GC event; các dòng liên quan thường dùng cùng mã này.
- `Pause Full`: loại pause.
- `(Ergonomics)`: nguyên nhân/nguồn kích hoạt được JVM ghi nhận trong ví dụ.

Một ví dụ khác về pha:

~~~text
[4.402s][info][gc,phases] GC(46) Marking Phase 57.896ms
~~~

Dòng này thuộc cùng `GC(46)`, ghi nhận pha Marking Phase kéo dài khoảng 57,896 ms. Có thể ghép các dòng có cùng GC ID để dựng lại thứ tự bắt đầu, các pha và kết thúc của một chu kỳ.

Không đọc từng dòng độc lập. Hãy nhóm theo GC ID, sắp xếp theo timestamp và xác định dòng bắt đầu/kết thúc pause trước khi tính thời gian.

## 7. Đọc heap trước và sau GC, duration và cause

Một dòng pause minh họa:

~~~text
[12.345s][info][gc] GC(42) Pause Young (Normal) (G1 Evacuation Pause) 512M->128M(1024M) 18.456ms
~~~

Các thành phần thường gặp:

- `Pause Young`: collection thuộc young generation.
- `Normal`: phân loại collection theo collector.
- `G1 Evacuation Pause`: loại pause cụ thể của G1.
- `512M->128M`: heap occupancy trước và sau sự kiện trong ví dụ.
- `(1024M)`: dung lượng heap tại thời điểm log.
- `18.456ms`: thời lượng pause được ghi cho event này.

Các nhãn `Young`, `Mixed`, `Full`, `Concurrent Mark Cycle`, `Evacuation Failure` hoặc `System.gc()` có ý nghĩa phụ thuộc collector và ngữ cảnh. Đừng giả định mọi collector dùng cùng tên event hoặc cùng cấu trúc log.

Heap giảm mạnh sau GC cho thấy collection đã thu hồi được nhiều heap ở thời điểm đó. Nếu heap sau GC vẫn cao và tăng dần qua nhiều chu kỳ, có thể có live set lớn, object được giữ tham chiếu lâu hoặc workload tạo nhiều dữ liệu sống. Cần đối chiếu với heap occupancy, allocation rate và heap dump/JFR khi cần.

## 8. Phân biệt pause và concurrent phase

Không phải toàn bộ thời gian của một chu kỳ GC đều là thời gian ứng dụng bị dừng.

Ví dụ G1 có thể thực hiện concurrent marking trong khi các luồng ứng dụng tiếp tục chạy, nhưng vẫn có những pha STW như initial mark, remark, cleanup hoặc evacuation pause. ZGC và Shenandoah cũng thực hiện nhiều công việc concurrent, xen kẽ với một số pha pause ngắn.

Một log có thể thể hiện:

~~~text
GC(52) Concurrent Mark Cycle
GC(52) Pause Remark
GC(52) Concurrent Mark Cycle 420.000ms
~~~

Các dòng trên chỉ minh họa cấu trúc. Thời gian của `Concurrent Mark Cycle` là thời gian chu kỳ concurrent, không đồng nghĩa ứng dụng bị dừng trong toàn bộ khoảng đó. Cần tìm các event có `Pause` và thời lượng tương ứng để đánh giá STW latency.

Đối với collector concurrent, chỉ nhìn tổng duration của cycle có thể làm đánh giá sai ảnh hưởng tới request latency. Hãy tách:

- **Pause duration:** thời gian các luồng ứng dụng bị dừng.
- **Concurrent duration:** thời gian GC chạy song song với ứng dụng.
- **Cycle duration:** khoảng thời gian bao trùm một chu kỳ collection, có thể chứa cả concurrent phase và pause.

## 9. Theo dõi các pha bằng gc+phases

Khi một pause kéo dài, cần biết pha nào chiếm thời gian:

~~~powershell
java "-Xlog:gc*,gc+phases=debug:file=logs/gc-phases.log:time,uptime,level,tags:filecount=5,filesize=30M" -jar app.jar
~~~

Các tên pha tùy collector và JDK, nhưng thường phản ánh những công việc như:

- Root scanning hoặc xử lý root.
- Marking và xử lý reference.
- Evacuation/copy object.
- Update references hoặc remapping.
- Cleanup và reclaim region.
- Compaction trong collection cần di chuyển/thu gọn object.

Nếu một pha chiếm phần lớn pause, đó là hướng điều tra tiếp theo. Ví dụ, thời gian xử lý reference cao có thể liên quan số lượng reference object; evacuation kéo dài có thể liên quan lượng object phải di chuyển, tốc độ cấp phát hoặc áp lực heap. Tên pha đơn lẻ không đủ kết luận nguyên nhân; cần đối chiếu log chi tiết, workload và collector.

## 10. Đối chiếu CPU time và real time

Với G1, có thể bật thông tin CPU cho từng pause:

~~~powershell
java "-Xlog:gc*,gc+cpu=info:file=logs/gc-cpu.log:time,uptime,level,tags:filecount=5,filesize=20M" -jar app.jar
~~~

Ví dụ một dòng CPU có dạng:

~~~text
User=0.19s Sys=0.00s Real=0.01s
~~~

Ý nghĩa:

- `User`: thời gian CPU mà JVM dùng để thực hiện công việc ở user space.
- `Sys`: thời gian CPU dành cho công việc trong hệ điều hành/kernel.
- `Real`: thời gian thực đã trôi qua trong khoảng được đo.

Diễn giải:

- `User + Sys` giải thích phần lớn `Real`: thời gian pause có thể chủ yếu dành cho công việc CPU. Trên máy nhiều core, tổng CPU time của các worker song song có thể lớn hơn `Real`.
- `Sys` cao: xem xét chi phí kernel, memory mapping, page fault hoặc hoạt động hệ điều hành.
- `Real` lớn hơn nhiều so với `User + Sys`: JVM có thể không được cấp CPU liên tục, máy/container bị tranh chấp CPU hoặc thread bị trì hoãn bởi môi trường.

Đây là chỉ báo để khoanh vùng, không phải bằng chứng độc lập. Trên máy nhiều core, tổng CPU time của nhiều thread có thể lớn hơn real time; so sánh phải tính đến số worker và cách collector chạy song song.

## 11. Đối chiếu GC pause với safepoint

GC pause thường yêu cầu JVM đi tới safepoint, nhưng không phải mọi safepoint đều do GC. JVM cũng có thể dừng thread để thực hiện các hoạt động khác.

Để xem thêm thông tin safepoint:

~~~powershell
java "-Xlog:gc*,safepoint=info:file=logs/gc-safepoint.log:time,uptime,level,tags:filecount=5,filesize=20M" -jar app.jar
~~~

So sánh timestamp của GC event với safepoint log:

- Nếu GC pause và safepoint duration gần nhau, GC có thể chiếm phần lớn thời gian dừng.
- Nếu safepoint tổng thể dài hơn đáng kể, xem xét thời gian đưa thread tới safepoint và các công việc VM khác.
- Nếu có safepoint dài nhưng không có GC pause tương ứng, điều tra nguyên nhân safepoint riêng.

Không đồng nhất thời gian từ lúc JVM yêu cầu safepoint với thời gian collector thực hiện công việc. Một số log safepoint có các thành phần như thời gian đồng bộ thread, cleanup và thời gian VM operation.

## 12. Những dấu hiệu cần tìm trong log

| Dấu hiệu | Ý nghĩa có thể | Hướng điều tra |
| --- | --- | --- |
| Pause Young xuất hiện quá dày | Allocation rate cao hoặc young collection diễn ra thường xuyên | Đo allocation rate, object churn và workload |
| Pause duration tăng dần | Heap pressure, live data tăng hoặc phase xử lý nặng | So sánh heap trước/sau, phase breakdown và live set |
| `Pause Full` lặp lại | Collector phải thu gom toàn heap; với G1 thường là dấu hiệu cần điều tra | Tìm nguyên nhân Full GC, evacuation failure, old occupancy và humongous allocation |
| `Evacuation Failure` | Collector không đủ vùng đích để di chuyển object trong collection | Xem heap headroom, allocation rate và log region |
| Concurrent cycle không kịp hoàn tất | Collector có thể bị áp lực allocation hoặc thiếu CPU | So sánh cycle duration, allocation rate và CPU contention |
| Pause ngắn nhưng tổng pause lớn | Nhiều pause cộng dồn ảnh hưởng request | Tính pause frequency và tổng pause trong cửa sổ thời gian |
| `System.gc()` xuất hiện | Có lời gọi explicit GC hoặc công cụ yêu cầu GC | Tìm caller và đánh giá nhu cầu |
| Real time cao bất thường | Có thể bị tranh chấp CPU hoặc chậm từ OS/I/O | Đối chiếu `gc+cpu`, safepoint và metric hệ thống |

Một Full GC đơn lẻ trong quá trình khởi động hoặc do thao tác chẩn đoán không đủ để kết luận hệ thống có vấn đề. Cần đánh giá tần suất, thời lượng, nguyên nhân và ảnh hưởng tới SLA.

## 13. Đọc GC log theo từng collector

`-Xlog:gc*` là điểm vào chung, nhưng cách diễn giải cần theo collector đang chạy:

| Collector | Đặc điểm cần lưu ý khi đọc log |
| --- | --- |
| G1 | Theo dõi Young/Mixed/Full pause, region, evacuation, humongous object, concurrent marking và phase breakdown |
| ZGC | Phân biệt các phase concurrent với các pause ngắn; không dùng tổng cycle duration thay cho pause latency |
| Shenandoah | Theo dõi concurrent cycle, degenerated/full collection và các pause phase theo log của phiên bản |
| Serial/Parallel GC | Công việc GC thường tập trung nhiều hơn vào STW pause; xem thời lượng collection và heap trước/sau |

Không sao chép nguyên xi kết luận hoặc tuning flag của G1 sang ZGC, Shenandoah, Serial hay Parallel GC. Hãy xác định collector thực tế và đọc đúng các tag/phase mà nó phát ra.

Có thể kiểm tra collector và flag đang áp dụng bằng:

~~~powershell
jcmd 12345 VM.flags -all
~~~

Thay PID bằng tiến trình thực tế. Khi cần xác nhận collector, đối chiếu flag `UseG1GC`, `UseZGC`, `UseShenandoahGC`, `UseParallelGC` hoặc thông tin khởi động tương ứng. Đừng giả định collector chỉ từ tên JDK.

## 14. Đo latency bằng pause distribution, không chỉ nhìn một dòng log

Đối với ứng dụng nhạy độ trễ, cần tổng hợp các chỉ số trong cùng một cửa sổ thời gian:

- Số pause và tần suất pause.
- Pause duration p50, p95, p99 và maximum.
- Tổng thời gian ứng dụng bị dừng trong cửa sổ.
- Heap occupancy trước/sau GC và xu hướng live set.
- Tần suất Full GC và concurrent cycle.
- Allocation rate, CPU utilization và request latency.

Ví dụ:

| Chỉ số trong 10 phút | JVM A | JVM B |
| --- | ---: | ---: |
| Số pause | 120 | 24 |
| Pause p99 | 18 ms | 65 ms |
| Pause dài nhất | 24 ms | 90 ms |
| Tổng thời gian pause | 1.4 s | 1.1 s |

Đây là số liệu giả định để minh họa. JVM A có pause thường xuyên hơn nhưng từng pause ngắn; JVM B ít pause hơn nhưng có pause dài hơn. Ứng dụng cần chọn cách đánh giá theo SLA và độ nhạy của request, không chỉ xếp hạng theo một con số.

GC log thô không phải lúc nào cũng là định dạng thuận tiện để tính percentile. Có thể dùng công cụ phân tích GC log hoặc JFR để tổng hợp pause distribution, sau đó đối chiếu với latency metric của ứng dụng.

## 15. Tách vấn đề GC khỏi vấn đề ứng dụng và môi trường

Một request chậm không nhất thiết do GC. Khi đối chiếu timestamp, cần xem:

- Thread có bị pause bởi GC hoặc safepoint trong khoảng request không?
- CPU có bị throttling trong container hoặc tranh chấp với tiến trình khác không?
- Có lock contention, I/O chậm, network delay hoặc downstream service chậm không?
- Ứng dụng có allocation burst hoặc tạo nhiều object ngắn hạn trước thời điểm pause không?
- Log có được ghi lên filesystem đang bị nghẽn I/O không?

Nếu GC pause chỉ chiếm một phần nhỏ trong khoảng request chậm, tập trung điều tra application trace, thread dump, JFR hoặc dependency bên ngoài. Không điều chỉnh collector chỉ dựa trên tương quan thời gian chưa được xác nhận.

Với G1, tài liệu Oracle lưu ý `Real` có thể lớn bất thường khi VM không được cấp đủ CPU time. Việc ghi log cũng có thể bị chậm nếu disk I/O bị tranh chấp. Khi đã chứng minh log I/O gây stall, có thể đánh giá asynchronous logging; tuy nhiên, asynchronous mode dùng buffer hữu hạn và chế độ drop có thể bỏ log khi buffer đầy. Chỉ bật sau khi cân nhắc độ đầy đủ của dữ liệu chẩn đoán.

## 16. Những cấu hình log cũ cần thay bằng -Xlog

Các hướng dẫn cũ có thể dùng nhiều flag GC logging riêng lẻ. Với JDK hiện đại, dùng Unified Logging:

| Cách cũ | Cách hiện hành |
| --- | --- |
| `-XX:+PrintGC` | `-Xlog:gc` |
| `-XX:+PrintGCDetails` | `-Xlog:gc*` |
| `-XX:+PrintGCDateStamps` | Dùng decorator `time` trong `-Xlog` |
| `-XX:+PrintGCTimeStamps` | Dùng decorator `uptime` trong `-Xlog` |
| `-XX:+PrintGCApplicationStoppedTime` | `-Xlog:safepoint` |
| `-XX:+PrintHeapAtGC` | `-Xlog:gc+heap=trace` |
| `-XX:+PrintReferenceGC` | `-Xlog:gc+ref*=debug` |

Các flag như `GCLogFileSize`, `NumberOfGCLogFiles` và `UseGCLogFileRotation` thuộc cơ chế rotation cũ. Unified Logging đã tích hợp rotation bằng `filecount` và `filesize`.

Không trộn cấu hình legacy với `-Xlog` trong một script khởi chạy mới. Khi di chuyển từ JDK cũ, dùng bảng chuyển đổi trong tài liệu `java` của đúng JDK mục tiêu; một số flag cũ có thể đã deprecated, obsolete hoặc bị loại bỏ ở phiên bản mới.

## 17. Quy trình thực hành đọc GC log

1. Xác nhận JDK version, collector và JVM flags đang chạy.
2. Bật `-Xlog:gc*` ở mức mặc định `info`, ghi ra file có timestamp và rotation.
3. Thu log trong workload đại diện, bao gồm thời gian warm-up và giai đoạn tải ổn định.
4. Tìm GC ID có pause dài, Full GC, evacuation failure hoặc chu kỳ bất thường.
5. Ghép các dòng theo GC ID để xem cause, heap trước/sau và duration.
6. Bật `gc*=debug` hoặc `gc+phases=debug` trong lần điều tra tiếp theo để xác định phase chiếm thời gian.
7. Bật `gc+cpu=info` và `safepoint=info` khi cần phân biệt GC work, CPU contention và safepoint delay.
8. Đối chiếu pause distribution với request latency, CPU, allocation rate và container metrics.
9. Xác định nguyên nhân ở ứng dụng, heap, collector hay môi trường trước khi thay đổi tuning.
10. Sau khi điều chỉnh, chạy lại cùng workload và so sánh cùng chỉ số p95/p99, pause sum, throughput và memory footprint.

**Ghi nhớ:** `-Xlog:gc*` là điểm bắt đầu hiện hành để đọc GC cycle và pause. Nhóm log theo GC ID, phân biệt STW pause với concurrent phase, xem heap trước/sau và phase breakdown; dùng `gc+cpu` và `safepoint` để khoanh vùng độ trễ từ CPU hoặc JVM. Bật debug có chọn lọc khi cần và luôn đối chiếu log với metric ứng dụng. Không dùng các flag GC logging legacy trong cấu hình mới.

## Nguồn tham khảo chính thức

- [The java Command — Unified Logging, JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [Garbage-First Garbage Collector Tuning — JDK 26](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-garbage-collector-tuning.html)
- [Troubleshoot Memory Leaks — GC Logging, JDK 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshooting-memory-leaks.html)
- [Troubleshoot Performance Issues Using Flight Recorder — JDK 26](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshoot-performance-issues-using-jfr.html)
- [JEP 271: Unified GC Logging](https://openjdk.org/jeps/271)
