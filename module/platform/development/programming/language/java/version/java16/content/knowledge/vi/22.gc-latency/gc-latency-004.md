# Phân biệt mục tiêu pause thấp với bảo đảm độ trễ toàn ứng dụng

Một GC pause ngắn không đồng nghĩa mọi request của ứng dụng đều có độ trễ thấp. GC pause là khoảng thời gian garbage collector tạm dừng các luồng ứng dụng trong một số pha; độ trễ end-to-end còn bao gồm thời gian chờ hàng đợi, xử lý nghiệp vụ, lập lịch CPU, lock, I/O và dịch vụ bên ngoài. Vì vậy, `-XX:MaxGCPauseMillis` là mục tiêu để JVM tối ưu hành vi GC, không phải cam kết rằng request luôn hoàn tất dưới một ngưỡng thời gian.

Khi đặt mục tiêu latency, cần đo cả pause của GC và phân phối độ trễ của request, đặc biệt p95, p99 và p99.9. Một collector hướng tới pause thấp có thể giảm thời gian dừng ứng dụng, nhưng vẫn cần CPU và bộ nhớ để chạy các pha concurrent; nếu hệ thống thiếu tài nguyên hoặc allocation rate quá cao, ứng dụng vẫn có thể chậm hoặc bị allocation stall.

Bài học thuộc chương **GC và độ trễ** của module **JAVA_VERSION_JAVA16**. Các nguyên tắc về G1 pause goal, collector concurrent và đo latency vẫn áp dụng trong JDK hiện đại. Nội dung tập trung vào cách diễn giải đúng mục tiêu pause, xác định giới hạn của GC và đo hiệu năng ứng dụng; không xem một tùy chọn GC là bảo đảm SLA.

## 1. GC pause và request latency là hai số đo khác nhau

**GC pause** là khoảng thời gian một pha GC dừng các luồng ứng dụng (stop-the-world). Trong khoảng dừng đó, các luồng Java không tiếp tục thực thi code nghiệp vụ. Tùy collector, một số pha GC khác có thể chạy concurrent trong lúc ứng dụng tiếp tục hoạt động.

**Request latency** là thời gian từ lúc request được nhận tới lúc kết quả được trả về. Nó có thể bao gồm:

- Thời gian request nằm trong queue trước khi worker xử lý.
- Thời gian thực thi code ứng dụng.
- Thời gian chờ lock, thread pool hoặc tài nguyên dùng chung.
- Thời gian chờ database, filesystem, network hoặc dịch vụ khác.
- Thời gian ứng dụng bị dừng bởi GC pause hoặc một safepoint khác.
- Thời gian bị ảnh hưởng bởi CPU scheduling, throttling hoặc memory pressure.

Một mô hình đơn giản:

```text
Request latency
  = queue wait
  + application processing
  + lock / pool / I/O wait
  + scheduling delay
  + time affected by GC and safepoints
```

Đây là mô hình phân tích, không phải công thức cộng các trường log một cách máy móc. Các khoảng thời gian có thể chồng lấp, nhất là khi request chờ I/O trong lúc GC chạy concurrent.

Ví dụ: GC pause lớn nhất trong một cửa sổ đo là 30 ms, nhưng p99 request latency là 900 ms. Điều đó không mâu thuẫn. Phần lớn độ trễ có thể đến từ queue, database hoặc CPU contention; GC pause chỉ là một thành phần nhỏ.

## 2. Mục tiêu pause của G1 không phải hard limit

G1 là collector mặc định trong nhiều cấu hình HotSpot hiện đại. Có thể đặt mục tiêu pause bằng:

```bash
java -XX:MaxGCPauseMillis=100 -jar service.jar
```

`-XX:MaxGCPauseMillis` yêu cầu G1 cố gắng giữ thời gian pause ở gần mục tiêu đã đặt. JVM dùng mục tiêu này trong các quyết định ergonomics, ví dụ điều chỉnh kích thước young generation và lượng công việc đưa vào collection set.

Điều cần nhớ:

- Đây là mục tiêu tối ưu, không phải hard deadline.
- G1 có thể vượt mục tiêu nếu trạng thái heap, tốc độ cấp phát hoặc công việc cần thực hiện không cho phép đáp ứng.
- Đặt mục tiêu quá thấp có thể khiến G1 thu nhỏ lượng công việc mỗi lần pause và thực hiện GC thường xuyên hơn.
- GC thường xuyên hơn có thể làm tăng overhead và giảm throughput.
- Mục tiêu pause không kiểm soát thời gian database, network, lock hoặc queue.

Ví dụ, đặt mục tiêu 50 ms không có nghĩa mọi GC pause đều nhỏ hơn hoặc bằng 50 ms, càng không có nghĩa mọi HTTP request hoàn tất trong 50 ms. Hãy xem đây là một tín hiệu cho thuật toán điều chỉnh GC, sau đó kiểm tra kết quả qua log và latency thực tế.

## 3. Pause ngắn không có nghĩa GC không tiêu thụ tài nguyên

Các collector concurrent thực hiện một phần công việc trong khi ứng dụng vẫn chạy. Điều này giúp giảm thời gian stop-the-world, nhưng công việc GC vẫn sử dụng CPU và bộ nhớ.

Nếu GC cạnh tranh CPU với ứng dụng:

- Worker có thể nhận ít CPU time hơn.
- Queue request có thể tăng dù pause rất ngắn.
- Pha concurrent kéo dài hơn khi CPU bị giới hạn.
- Ứng dụng có thể phải chờ khi tốc độ cấp phát vượt khả năng cấp phát an toàn tại thời điểm đó.

Với collector concurrent, cần phân biệt **pause time** với **thời gian hoàn thành chu kỳ GC**. Một chu kỳ có thể kéo dài nhiều trăm mili giây hoặc lâu hơn nhưng chỉ có một số pause ngắn; trong suốt chu kỳ đó, GC vẫn dùng tài nguyên và có thể ảnh hưởng throughput.

## 4. ZGC hướng tới pause thấp nhưng không bảo đảm end-to-end latency

ZGC là collector concurrent, được đưa vào production từ JDK 15. Nó được thiết kế để giữ các pause của GC rất ngắn và ít phụ thuộc vào dung lượng heap. Đây là lựa chọn đáng cân nhắc cho ứng dụng có yêu cầu latency chặt chẽ, nhưng không loại bỏ mọi nguồn gây chậm.

Ví dụ chọn ZGC trên JDK hiện đại:

```bash
java -XX:+UseZGC -jar service.jar
```

Trên các JDK mới, ZGC có chế độ generational; hãy dùng tài liệu của đúng phiên bản JDK để xác định chế độ và tùy chọn đang có. Không sao chép cờ thử nghiệm hoặc tùy chọn của một bản JDK cũ sang môi trường mới mà không kiểm tra hỗ trợ.

Ngay cả khi pause rất ngắn, ứng dụng vẫn có thể gặp:

- **Allocation stall:** luồng ứng dụng phải chờ khi cần cấp phát nhưng GC chưa thu hồi hoặc tái sử dụng được vùng nhớ kịp thời.
- **CPU contention:** các pha concurrent của GC cạnh tranh CPU với worker.
- **Memory pressure:** hệ điều hành hoặc container thiếu RAM, dẫn đến reclaim, paging hoặc throttling.
- **Application bottleneck:** database, network, lock, queue hoặc code nghiệp vụ chậm.

ZGC giảm một nguồn gây dừng ứng dụng; nó không đặt giới hạn cho tổng thời gian request.

## 5. So sánh mục tiêu của collector với SLO ứng dụng

| Chỉ số hoặc mục tiêu | Đo điều gì? | Có bảo đảm request latency không? |
| --- | --- | --- |
| G1 `MaxGCPauseMillis` | Mục tiêu pause để G1 điều chỉnh hoạt động GC | Không |
| GC pause duration | Thời gian một pha GC dừng ứng dụng | Không |
| Concurrent GC cycle duration | Thời gian hoàn thành các pha GC concurrent | Không |
| Allocation rate | Tốc độ ứng dụng tạo object | Không |
| Request p95/p99/p99.9 | Phân phối độ trễ request thực tế | Là số đo trực tiếp để đánh giá SLO |
| Timeout/error rate | Tỷ lệ request không hoàn tất đúng hạn | Là số đo trực tiếp về chất lượng dịch vụ |

Nếu SLO yêu cầu 99% request hoàn tất trong 200 ms, cần đo p99 của request ở ranh giới dịch vụ. GC pause goal có thể hỗ trợ đạt SLO, nhưng không thể thay thế phép đo đó.

## 6. Dùng percentile thay vì chỉ xem average

Latency thường có phân phối lệch: nhiều request nhanh nhưng một số request rất chậm. Average có thể che khuất các request ở tail.

| Chỉ số | Cách đọc |
| --- | --- |
| p50 | Một nửa request nhanh hơn hoặc bằng giá trị này |
| p95 | 95% request nhanh hơn hoặc bằng giá trị này |
| p99 | 99% request nhanh hơn hoặc bằng giá trị này |
| p99.9 | 99,9% request nhanh hơn hoặc bằng giá trị này |
| Maximum | Request chậm nhất trong cửa sổ đo; nhạy với outlier và cỡ mẫu |

Ví dụ minh họa:

| Chỉ số | Trước điều chỉnh | Sau điều chỉnh |
| --- | ---: | ---: |
| GC pause p99 | 80 ms | 35 ms |
| Request p50 | 18 ms | 18 ms |
| Request p99 | 240 ms | 225 ms |
| Request p99.9 | 1.2 s | 1.1 s |

Pause giảm đáng kể nhưng tail latency của request chỉ cải thiện ít. Đây là dấu hiệu cần tiếp tục điều tra queue, CPU, lock hoặc downstream dependency thay vì chỉ tiếp tục ép pause thấp hơn.

Khi benchmark, chọn cửa sổ đo đủ dài và tải đại diện. Load generator nên tránh coordinated omission: nếu chính client phát tải ngừng gửi request trong lúc hệ thống chậm, histogram có thể bỏ qua một phần độ trễ mà người dùng thực tế phải chịu.

## 7. Những nguồn latency không nằm trong GC pause

Khi p99 tăng nhưng GC pause không tăng tương ứng, kiểm tra các nhóm sau:

| Nguồn | Dấu hiệu thường gặp | Hướng điều tra |
| --- | --- | --- |
| CPU saturation | CPU gần giới hạn, runnable thread tăng | CPU profile, container CPU throttling, mức cạnh tranh GC/worker |
| Queue buildup | Thời gian chờ trước khi xử lý tăng | Queue depth, worker pool size, admission control |
| Lock contention | Thread chờ monitor hoặc lock lâu | JFR monitor/park events, thread dump |
| Database | Thời gian query hoặc pool wait tăng | Database metrics, connection pool wait, query plan |
| Network/I/O | Socket read, write hoặc filesystem wait kéo dài | JFR I/O events, network và storage metrics |
| Safepoint ngoài GC | Có pause nhưng không tương ứng GC event | Safepoint log và nguyên nhân VM operation |
| JIT/compiler | Latency tăng ở giai đoạn warm-up hoặc deoptimization | JFR compiler events, compilation log |
| Memory pressure | CPU reclaim, swap hoặc container OOM pressure | RSS, container memory metrics, OS metrics |

Không kết luận mọi khoảng dừng của Java thread đều do GC. JVM có các safepoint phục vụ nhiều hoạt động khác. Bật log safepoint giúp phân biệt thời gian dừng liên quan GC với các safepoint khác.

## 8. Thu thập GC và safepoint log

Unified Logging là cách hiện hành để ghi GC và safepoint trên JDK hiện đại:

```bash
java -Xlog:gc*,safepoint:file=gc-safepoint.log:time,uptime,level,tags -jar service.jar
```

Khi đọc log, đối chiếu:

- Thời điểm và duration của từng pause.
- Loại GC event và nguyên nhân kích hoạt.
- Heap occupancy trước và sau GC.
- Khoảng cách giữa các pause và tần suất GC.
- Thời lượng các pha concurrent nếu collector ghi nhận.
- Safepoint synchronization và thời gian dừng liên quan VM operation.

Không chỉ nhìn dòng pause dài nhất. Hãy so sánh log với histogram request theo cùng khoảng thời gian để biết pause có trùng với tail latency hay không.

## 9. Dùng JFR để tìm nguyên nhân request chậm

Java Flight Recorder (JFR) thu thập sự kiện JVM và ứng dụng để hỗ trợ phân tích. Có thể bắt đầu một recording trong thời gian giới hạn:

```bash
jcmd <pid> JFR.start name=latency settings=profile duration=60s filename=latency.jfr
```

Mở file recording bằng Java Mission Control hoặc công cụ phân tích JFR phù hợp. Tùy workload và recording settings, xem các nhóm sự kiện:

- Garbage collection và GC phase/pause.
- Execution samples và CPU load.
- Thread park, monitor contention và thread scheduling.
- Socket/file I/O và thời gian chờ.
- JIT compilation và compiler activity.

JFR giúp liên hệ thời điểm latency tăng với hoạt động JVM. Nó không tự thay thế metrics request của ứng dụng; hãy giữ timestamp hoặc trace ID phù hợp để đối chiếu histogram và distributed tracing.

Recording `profile` có overhead nhất định. Đo trong khoảng thời gian đủ để bắt được vấn đề, cân nhắc settings phù hợp môi trường và không mặc định bật một cấu hình thu thập chi tiết trên mọi instance nếu chưa đánh giá chi phí.

## 10. Đọc các dấu hiệu GC cần theo dõi

| Dấu hiệu | Có thể gợi ý điều gì? | Cần kiểm tra thêm |
| --- | --- | --- |
| Pause duration tăng | Heap/collection set lớn hoặc công việc GC tăng | Collector, heap occupancy, allocation rate |
| Pause ngắn nhưng GC cycle kéo dài | Concurrent work bị kéo dài hoặc thiếu CPU | CPU headroom, allocation rate, GC cycle log |
| Allocation stall | Ứng dụng cấp phát nhanh hơn khả năng cấp phát an toàn tại thời điểm đó | Allocation rate, heap headroom, concurrent GC progress |
| GC liên tục nhưng ít reclaim | Live set lớn hoặc object còn reachable | Heap dump khi phù hợp, object retention, cache |
| Request p99 tăng nhưng pause ổn định | Nguồn latency có thể nằm ngoài GC pause | Queue, CPU, lock, I/O, downstream |
| Pause ổn định nhưng timeout tăng | Deadline hoặc dependency không đáp ứng | Timeout budget, retry, pool saturation |

Với ZGC, hãy quan sát các event đặc thù của collector và allocation stalls trong log của đúng JDK đang chạy. Không diễn giải các dòng log của G1 theo cùng cách với ZGC hoặc collector khác.

## 11. Quy trình đánh giá một thay đổi GC

Không thay collector hoặc pause goal chỉ dựa vào một con số. Dùng quy trình có thể lặp lại:

1. **Định nghĩa SLO:** xác định p95/p99/p99.9 và timeout mục tiêu ở ranh giới request.
2. **Đo baseline:** ghi latency histogram, throughput, error rate, CPU, memory và GC logs dưới tải đại diện.
3. **Xác định tương quan:** kiểm tra request chậm có trùng với GC pause, concurrent GC, safepoint hay không.
4. **Tìm bottleneck:** xem queue, CPU throttling, lock, I/O, pool và downstream.
5. **Thay một yếu tố:** ví dụ thay G1 pause goal hoặc thử collector khác; không thay đồng thời nhiều tham số.
6. **Chạy lại cùng workload:** so sánh p99/p99.9, throughput, CPU, memory và error rate.
7. **Kiểm tra độ ổn định:** thử tải cao, burst, warm-up và thời gian chạy dài.

Chỉ giữ thay đổi nếu cải thiện latency mục tiêu mà không làm throughput, độ ổn định hoặc chi phí tài nguyên xấu đi ngoài mức chấp nhận.

## 12. Chọn G1 hay ZGC theo yêu cầu thực tế

| Tiêu chí | G1 | ZGC |
| --- | --- | --- |
| Định hướng | Cân bằng throughput và pause goal | Pause thấp, phần lớn công việc GC chạy concurrent |
| Điều chỉnh pause | Có `-XX:MaxGCPauseMillis` làm mục tiêu heuristic | Không dùng G1 pause goal để đặt SLA cho ZGC |
| Tài nguyên concurrent | Có các pha concurrent và stop-the-world | Cần CPU headroom cho hoạt động concurrent |
| Trường hợp phù hợp | Ứng dụng tổng quát, cần cân bằng hiệu năng | Ứng dụng nhạy với pause và có thể cấp đủ tài nguyên |
| Điều cần đo | Pause, throughput, allocation và tail latency | Pause, concurrent cycle, allocation stall, CPU và tail latency |

Không có collector tốt nhất cho mọi workload. G1 có thể đáp ứng tốt một dịch vụ với SLO vừa phải; ZGC có thể phù hợp khi tail latency nhạy với pause. Quyết định phải dựa trên benchmark của chính ứng dụng, JDK, heap size, CPU quota và môi trường triển khai.

## 13. Những sai lầm thường gặp

- Xem `MaxGCPauseMillis` như một giới hạn cứng hoặc SLA request.
- Chỉ theo dõi average latency mà bỏ qua p99 và p99.9.
- Cho rằng collector concurrent không dùng CPU hoặc không ảnh hưởng throughput.
- Chọn ZGC chỉ vì muốn latency thấp mà không cấp đủ CPU/memory headroom.
- Tăng heap hoặc giảm pause goal mà không kiểm tra allocation rate và live set.
- Đổ mọi safepoint hoặc request spike cho GC.
- So sánh hai cấu hình bằng workload khác nhau hoặc cửa sổ đo quá ngắn.
- Đo closed-loop load test khiến histogram bỏ qua thời gian chờ do coordinated omission.

## 14. Bài tập tự kiểm tra

Một API có SLO p99 dưới 250 ms. Nhóm vận hành đặt `-XX:MaxGCPauseMillis=50` cho G1. GC log cho thấy phần lớn pause dưới 50 ms, nhưng p99 API vẫn là 700 ms. JFR cho thấy một phần lớn thời gian request chờ connection pool và database; CPU container cũng thường xuyên bị throttling.

Hãy trả lời:

1. `MaxGCPauseMillis=50` có nghĩa p99 API phải dưới 50 ms không?
2. Vì sao GC pause thấp nhưng p99 vẫn cao?
3. Nên kiểm tra những chỉ số nào trước khi tiếp tục giảm pause goal?
4. Nếu thử ZGC, cần đo thêm những yếu tố nào?
5. Dùng số liệu nào để kết luận SLO đã đạt?

**Đáp án:**

1. Không. Đây là mục tiêu heuristic cho G1, không phải giới hạn request latency.
2. Request còn chờ connection pool/database và bị ảnh hưởng bởi CPU throttling.
3. Queue wait, connection pool wait, database latency, CPU throttling, throughput, GC pause và safepoint.
4. Concurrent GC CPU usage, allocation rate, allocation stalls, heap headroom, throughput và p99/p99.9.
5. Histogram request tại ranh giới API, đặc biệt p99 trong cửa sổ tải đại diện, cùng error/timeout rate.

## Ghi nhớ

**Mục tiêu pause thấp chỉ giúp JVM tối ưu thời gian GC dừng ứng dụng; nó không bảo đảm độ trễ end-to-end của request.** `-XX:MaxGCPauseMillis` là mục tiêu heuristic của G1, còn collector concurrent như ZGC vẫn cần CPU và bộ nhớ, đồng thời có thể chịu allocation stall. Hãy đo p95/p99/p99.9, throughput và timeout ở tầng ứng dụng; đối chiếu với GC/safepoint logs, JFR, CPU, queue, lock, I/O và downstream dependency trước khi điều chỉnh collector.

## Tài liệu tham khảo

- [Oracle Java SE 26 — Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/26/gctuning/)
- [Oracle Java SE 26 — G1 Garbage Collector](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-garbage-collector-tuning.html)
- [Oracle Java SE 26 — Z Garbage Collector](https://docs.oracle.com/en/java/javase/26/gctuning/z-garbage-collector.html)
- [Oracle Java SE 26 — Unified Logging](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [Oracle Java SE 26 — jcmd](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [JEP 248 — Make G1 the Default Garbage Collector](https://openjdk.org/jeps/248)
- [JEP 377 — ZGC: A Scalable Low-Latency Garbage Collector](https://openjdk.org/jeps/377)
