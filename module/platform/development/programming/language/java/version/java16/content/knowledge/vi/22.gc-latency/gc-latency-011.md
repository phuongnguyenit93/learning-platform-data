# So sánh G1 và ZGC bằng workload đại diện có số lượng thread thực tế

So sánh G1 và ZGC chỉ có ý nghĩa khi hai collector chạy cùng workload, cùng giới hạn CPU/bộ nhớ và mức đồng thời gần với môi trường thật. Một benchmark dùng một thread trong khi production có hàng chục worker, nhiều request đồng thời hoặc virtual thread sẽ không phản ánh đúng áp lực cấp phát, tranh chấp CPU và hành vi GC của dịch vụ. Cần đo đồng thời tail latency, throughput, GC pause, CPU, memory và số thread thực sự hoạt động.

G1 hướng tới cân bằng throughput và pause goal; ZGC thực hiện phần lớn công việc concurrent để giữ pause rất ngắn. Cả hai đều có chi phí tài nguyên và giới hạn riêng. Kết quả không thể kết luận chỉ từ pause duration: ZGC có thể giảm pause nhưng dùng thêm CPU headroom, còn G1 có thể đạt throughput tốt hơn với workload cụ thể. Hãy đo bằng tải đại diện, bao gồm số worker và concurrency production.

Bài học thuộc chương **GC và độ trễ** của module **JAVA_VERSION_JAVA16**. G1 và ZGC đều là collector chính thức, còn được sử dụng trong JDK hiện đại. Trên JDK 23 trở lên, Generational ZGC là chế độ mặc định khi chọn ZGC; luôn kiểm tra tài liệu của đúng JDK đang chạy. Nội dung không sử dụng các cờ thử nghiệm cũ hoặc giả định một collector luôn tốt hơn collector còn lại.

## 1. G1 và ZGC tối ưu những điều gì?

| Đặc điểm | G1 | ZGC |
| --- | --- | --- |
| Định hướng | Cân bằng throughput, footprint và pause goal | Giảm stop-the-world pause bằng nhiều pha GC concurrent |
| Mục tiêu pause | Có `-XX:MaxGCPauseMillis` làm mục tiêu heuristic | Không dùng G1 pause goal để đặt SLA cho ZGC |
| Công việc concurrent | Có các pha concurrent và các pha stop-the-world | Phần lớn công việc chính chạy concurrent |
| Chi phí cần theo dõi | Pause, tần suất GC, throughput và CPU | CPU concurrent, memory headroom, allocation stall và throughput |
| Phù hợp khi | Workload tổng quát cần cân bằng hiệu năng | Workload nhạy với pause và có đủ CPU/memory headroom |

G1 có thể điều chỉnh collection set để cố gắng đáp ứng pause goal, nhưng không cam kết hard deadline. ZGC giảm pause của GC nhưng không loại bỏ thời gian chờ queue, lock, database, network hoặc CPU scheduling. Cả hai cần được đánh giá bằng request latency end-to-end.

## 2. Vì sao số lượng thread thực tế làm thay đổi kết quả?

Số thread ảnh hưởng đến cách ứng dụng tạo tải và cạnh tranh tài nguyên:

- Nhiều worker hoạt động đồng thời có thể làm allocation rate tăng, khiến GC phải xử lý nhiều object hơn trong cùng khoảng thời gian.
- Nhiều platform thread runnable có thể cạnh tranh CPU với worker GC và các pha concurrent.
- Thread bị block ở database hoặc network không tiêu thụ CPU liên tục, nhưng vẫn giữ stack, context và có thể giữ object tham chiếu.
- Thread pool quá lớn có thể làm queue, context switching và lock contention tăng mà throughput không tăng tương ứng.
- Với virtual thread, số lượng virtual thread có thể rất lớn nhưng không đồng nghĩa có cùng số platform thread chạy đồng thời. Phải ghi riêng số virtual thread, platform thread và mức CPU concurrency.

Không lấy số thread trong cấu hình làm đại diện duy nhất. Hãy ghi cả:

| Số liệu | Ý nghĩa |
| --- | --- |
| Configured worker count | Số worker tối đa do thread pool hoặc server cấu hình |
| Active workers | Số worker đang xử lý công việc trong thời điểm đo |
| Runnable platform threads | Số platform thread đang sẵn sàng chạy hoặc tranh CPU |
| Blocked/waiting threads | Số thread đang chờ lock, I/O, pool hoặc điều kiện khác |
| Virtual threads | Số virtual thread đang tồn tại/được sử dụng nếu ứng dụng dùng mô hình này |
| Queue depth | Số request/task đang chờ worker |
| CPU quota và throttling | Giới hạn CPU thực tế và thời gian bị container throttling |

Một service có pool 64 thread nhưng chỉ 8 worker active không tương đương service có 64 worker liên tục runnable. Ngược lại, một service dùng virtual thread có thể có hàng nghìn request đang chờ I/O nhưng chỉ một số platform thread thực sự chạy CPU. Benchmark phải mô phỏng đúng mô hình concurrency của ứng dụng.

## 3. Xác định workload đại diện trước khi chạy benchmark

Trước khi chọn collector, thu thập thông tin từ production hoặc staging có tải tương tự:

1. **Request mix:** tỷ lệ các endpoint, kích thước payload, đường đi code và thời gian xử lý.
2. **Concurrency:** số request đồng thời, worker pool size, active thread và queue depth.
3. **Allocation profile:** allocation rate, kích thước object, tần suất tạo object ngắn hạn và object sống lâu.
4. **Live set:** lượng object còn reachable sau GC ổn định.
5. **Dependency:** database, cache, network, filesystem và connection pool.
6. **Tài nguyên:** CPU quota, RAM/container limit, heap limit và giới hạn native memory.
7. **Thời gian:** startup, warm-up, steady state, burst và chu kỳ tải cao kéo dài.

Nếu chưa có production profile, tạo workload mô phỏng các luồng chính và ghi rõ giả định. Một benchmark chỉ tạo object trong vòng lặp không thể thay thế workload có request, lock, I/O và dependency thật.

## 4. Thiết kế ma trận thread count và concurrency

Không benchmark chỉ với một mức thread. Tạo ma trận phản ánh cách service vận hành:

| Kịch bản | Số worker/thread | Mục đích |
| --- | --- | --- |
| Low concurrency | Mức thấp thường gặp | Xác định chi phí nền và độ trễ khi tải nhẹ |
| Normal production | Số worker và concurrency thường thấy | So sánh trong điều kiện vận hành bình thường |
| Peak production | Mức đồng thời cao đã quan sát | Đánh giá tail latency và khả năng duy trì throughput |
| Burst | Tăng tải nhanh tới mức đỉnh | Quan sát queue buildup, allocation pressure và recovery |
| Saturation | Tăng tải tới khi tài nguyên đạt giới hạn | Xác định điểm bão hòa và hành vi khi quá tải |

Ví dụ nếu production thường chạy 32 worker, peak khoảng 64 worker và có burst ngắn lên 96 worker, hãy thử các mức đó. Không tự chọn 1, 100 hoặc 1000 thread chỉ vì đó là con số tròn. Ghi rõ số worker cấu hình, số worker active và số platform thread runnable ở mỗi lần đo.

Với virtual thread, thiết kế hai trục riêng: số virtual thread/request đồng thời và số platform thread/CPU worker có thể chạy song song. Không chuyển workload từ platform thread sang virtual thread trong lúc so sánh collector; đó là thay đổi mô hình concurrency, không còn là phép thử chỉ thay GC.

## 5. Kiểm soát môi trường để so sánh công bằng

Giữ các yếu tố sau giống nhau giữa lần chạy G1 và ZGC:

- Cùng bản phân phối và build JDK.
- Cùng máy, CPU quota, RAM limit, kernel và container configuration.
- Cùng application artifact, cấu hình, dữ liệu và phiên bản dependency.
- Cùng số worker, request concurrency, request mix và arrival rate.
- Cùng giới hạn heap, ví dụ `-Xms4g -Xmx4g`, ở vòng baseline.
- Cùng cách ghi log, JFR settings và thời gian benchmark.
- Cùng trạng thái cache, database và các dịch vụ phụ thuộc.

Chạy từng collector trong process mới để không mang trạng thái heap hoặc JIT từ lượt trước sang lượt sau. Thực hiện warm-up đến khi throughput, compilation và latency tương đối ổn định. Lặp lại nhiều lần và đổi thứ tự chạy để giảm ảnh hưởng nhiệt độ CPU, cache hoặc biến động hạ tầng.

Nên có hai vòng đánh giá:

1. **Baseline có kiểm soát:** cùng `-Xms`, `-Xmx`, CPU và workload; dùng thiết lập collector mặc định để quan sát khác biệt ban đầu.
2. **Tuning theo SLO:** điều chỉnh từng collector riêng, nhưng vẫn giữ cùng ngân sách CPU/memory và yêu cầu latency/throughput. Không ép ZGC dùng `MaxGCPauseMillis`; đây là mục tiêu của G1.

Giữ cùng `-Xmx` giúp so sánh trong cùng heap budget, nhưng chưa chắc hai collector có cùng native memory footprint. Vì vậy, cần ghi cả RSS và tổng memory của container, không chỉ heap.

## 6. Chạy cùng ứng dụng với G1 và ZGC

Ví dụ baseline trên Linux/macOS, dùng cùng heap và ghi log GC/safepoint:

~~~bash
java -Xms4g -Xmx4g \
  -XX:+UseG1GC \
  -Xlog:gc*,safepoint:file=g1-gc.log:time,uptime,level,tags \
  -jar service.jar
~~~

Chạy lại cùng workload với ZGC:

~~~bash
java -Xms4g -Xmx4g \
  -XX:+UseZGC \
  -Xlog:gc*,safepoint:file=zgc-gc.log:time,uptime,level,tags \
  -jar service.jar
~~~

Trên JDK 23 trở lên, ZGC dùng Generational ZGC mặc định. Không thêm cờ bật generational mode từ các bản JDK cũ nếu bản JDK hiện tại đã không còn hỗ trợ cờ đó. Nếu phải so sánh trên JDK khác, xác nhận tùy chọn theo tài liệu của đúng phiên bản và giữ nguyên JDK giữa các lượt thử.

Không đặt `-XX:MaxGCPauseMillis` vào lệnh ZGC rồi kết luận hai collector có cùng mục tiêu pause; tham số này là mục tiêu của G1. Đầu tiên hãy so sánh default behavior, sau đó tune từng collector theo cùng SLO.

## 7. Chọn tải và mô hình phát request

Load test phải phản ánh cách request đến service:

- **Open-loop:** bộ phát tải gửi request theo arrival rate mục tiêu, độc lập với tốc độ phản hồi. Phù hợp để phát hiện queue buildup và tránh coordinated omission.
- **Closed-loop:** client gửi request tiếp theo sau khi request trước hoàn tất. Có ích để kiểm tra concurrency cố định, nhưng có thể che khuất độ trễ khi hệ thống chậm vì tốc độ phát tải tự giảm.
- **Burst:** tăng arrival rate nhanh để xem queue và GC phản ứng ra sao khi allocation tăng đột ngột.

Nếu dùng closed-loop, cần hiểu giới hạn của histogram và bổ sung open-loop hoặc phép đo latency có hiệu chỉnh coordinated omission. Dùng cùng load generator, cùng arrival rate, số client và payload cho cả hai collector.

Đừng chỉ chạy tải CPU-bound nếu production chủ yếu chờ database hoặc network. Cũng đừng chỉ mô phỏng I/O-bound nếu ứng dụng thực tế tạo nhiều object hoặc xử lý JSON nặng. Request mix và thời gian chờ downstream phải gần thực tế.

## 8. Những chỉ số cần thu thập

| Nhóm | Chỉ số |
| --- | --- |
| Request | Throughput, p50, p95, p99, p99.9, maximum, timeout và error rate |
| GC | Pause duration/percentile, số lần pause, GC cycle duration, allocation stall và lượng reclaim |
| Allocation | Allocation rate, object allocation profile, promotion/live set |
| CPU | Process CPU, CPU quota, throttled time, runnable threads và GC CPU |
| Thread | Configured pool size, active worker, platform thread, virtual thread, blocked/waiting và queue depth |
| Memory | Heap used/committed, RSS, native memory, container working set và memory limit |
| Ứng dụng | Connection pool wait, database latency, lock contention và downstream latency |

Với G1, quan sát pause, evacuation, concurrent marking và dấu hiệu to-space exhaustion nếu xuất hiện. Với ZGC, theo dõi pause, chu kỳ concurrent, allocation stalls và headroom. Tên event và nội dung log có thể thay đổi theo JDK; đọc log bằng tài liệu của bản đang chạy.

## 9. Đo số thread thực tế trong lúc tải

Ghi nhận thread count trong cùng cửa sổ đo latency. Có thể lấy thread dump và trạng thái JVM bằng `jcmd`:

~~~bash
jcmd <pid> Thread.print -l > threads.txt
jcmd <pid> VM.flags
~~~

Thread dump cho biết thread platform, trạng thái và stack tại một thời điểm. Nó không thay thế metric theo thời gian; nên kết hợp JFR Thread events, thread pool metrics của ứng dụng và metric container/OS. Đặc biệt, thread dump không phải cách đếm đầy đủ virtual thread đang tồn tại trong mọi cấu hình hoặc mọi JDK.

Đối với executor, ghi `pool size`, `active count`, `completed task count` và queue size. Đối với request, ghi in-flight request và concurrency. Đối với virtual thread, ghi số virtual thread được tạo và số tác vụ đang hoạt động; đồng thời quan sát platform thread mà scheduler dùng để thực thi.

Không ép `-XX:ParallelGCThreads` hoặc `-XX:ConcGCThreads` ngay trong vòng baseline. Để JVM chọn giá trị ergonomic trước, rồi mới thử tuning riêng nếu log và CPU profile cho thấy GC worker count là nút thắt. Nếu dùng `-XX:ActiveProcessorCount` để mô phỏng CPU quota, áp dụng cùng giá trị cho cả hai collector và ghi lại trong báo cáo.

## 10. Đọc kết quả và xác định điểm đánh đổi

Ví dụ minh họa một workload chạy với 64 worker active, cùng CPU quota và heap limit:

| Chỉ số | G1 | ZGC |
| --- | ---: | ---: |
| Throughput | 12.000 req/s | 11.600 req/s |
| Request p99 | 180 ms | 125 ms |
| Request p99.9 | 420 ms | 260 ms |
| GC pause p99 | 75 ms | 2 ms |
| CPU trung bình | 68% | 78% |
| Container memory | 5,2 GB | 5,7 GB |

Các con số trên chỉ minh họa cách đọc bảng, không phải kết quả benchmark chung cho G1 hoặc ZGC. Trong ví dụ, ZGC cải thiện tail latency và GC pause nhưng tiêu thụ thêm CPU và memory, đồng thời throughput thấp hơn. Nếu CPU quota đã gần bão hòa, chênh lệch CPU có thể làm hệ thống khó chịu tải burst.

Một kết quả khác cũng có thể xảy ra: G1 đạt throughput cao và p99 đáp ứng SLO, trong khi ZGC không đem lại lợi ích đủ lớn để bù chi phí tài nguyên. Chọn collector theo SLO và ngân sách vận hành, không theo một bảng benchmark trên máy khác.

## 11. Cách diễn giải các tình huống thường gặp

| Quan sát | Diễn giải có thể | Bước tiếp theo |
| --- | --- | --- |
| ZGC pause thấp hơn nhiều nhưng p99 gần như không đổi | Tail latency chủ yếu đến từ queue, DB, lock hoặc CPU | Dùng JFR và tracing để xác định đoạn chờ |
| ZGC p99 tốt hơn nhưng CPU cao hơn | Concurrent GC dùng thêm CPU headroom | Kiểm tra CPU quota/throttling và throughput ở peak |
| G1 throughput cao hơn nhưng p99 xấu hơn | Pause hoặc allocation/evacuation pressure ảnh hưởng tail | Kiểm tra GC log, pause distribution và live set |
| Cả hai đều xấu khi worker tăng | CPU saturation, allocation rate hoặc downstream trở thành bottleneck | So sánh active/runnable thread, queue, allocation và dependency |
| Một collector chỉ tốt ở 1 thread | Workload thử không đại diện concurrency production | Chạy lại ma trận thread count thực tế |
| Latency tăng khi burst nhưng GC pause không tăng | Queue buildup hoặc CPU saturation có thể chi phối | Kiểm tra arrival rate, queue depth và throttling |

Không so sánh chỉ maximum pause hoặc maximum request latency. Maximum nhạy với outlier; cần xem percentile, cỡ mẫu, thời gian chạy và tính ổn định giữa các lần lặp.

## 12. Quy trình benchmark có thể lặp lại

1. **Chốt workload:** request mix, data size, dependency và mô hình open/closed-loop.
2. **Chốt thread matrix:** low, normal, peak và burst dựa trên worker/concurrency production.
3. **Chốt tài nguyên:** JDK build, CPU quota, RAM, heap, container limit và OS.
4. **Chạy baseline G1:** warm-up, steady state và thu thập đầy đủ metrics/log.
5. **Chạy baseline ZGC:** giữ nguyên workload, thread matrix và giới hạn tài nguyên.
6. **Lặp lại:** chạy nhiều lượt và đổi thứ tự collector để giảm sai lệch môi trường.
7. **Phân tích:** so sánh throughput, p99/p99.9, CPU, RSS, GC metrics, queue và error rate.
8. **Tune riêng:** điều chỉnh collector theo SLO nhưng giữ cùng ngân sách tài nguyên.
9. **Xác nhận:** chạy peak/burst/long-duration và kiểm tra không có regression hoặc memory pressure.

Một thay đổi chỉ được xem là tốt khi cải thiện mục tiêu đã xác định mà không vi phạm các ràng buộc khác. Ví dụ, p99 giảm nhưng error rate, CPU throttling hoặc container OOM tăng thì chưa phải kết quả chấp nhận được.

## 13. Những lỗi benchmark thường gặp

- Chỉ dùng một thread dù production có nhiều worker và request đồng thời.
- Đặt cùng số thread nhưng không kiểm tra số active/runnable thread thực tế.
- Dùng workload synthetic chỉ cấp phát object mà bỏ qua I/O, lock và dependency.
- So sánh hai JDK build, CPU quota hoặc heap limit khác nhau.
- Đo trước warm-up hoặc chỉ chạy trong thời gian quá ngắn.
- Dùng closed-loop load generator rồi bỏ qua coordinated omission.
- Chỉ báo cáo GC pause mà không báo request p99/p99.9 và throughput.
- Chỉ báo heap used mà bỏ qua RSS/native memory và container limit.
- Tinh chỉnh GC worker count trước khi có baseline và bằng chứng.
- Dùng cờ ZGC thử nghiệm của JDK cũ trên JDK mới mà không kiểm tra hỗ trợ.

## 14. Bài tập tự kiểm tra

Một dịch vụ production dùng 48 platform worker, thường có 40 worker active ở tải bình thường và 64 worker active khi peak. Nó có p99 dưới 200 ms, allocation rate cao khi xử lý JSON và gọi database qua connection pool. Nhóm benchmark so sánh G1 và ZGC chỉ với 1 worker, không có database, sau đó kết luận ZGC luôn nhanh hơn vì pause thấp hơn.

Hãy trả lời:

1. Vì sao workload một worker không đại diện production?
2. Nên chọn những mức worker/concurrency nào để benchmark?
3. Cần giữ những yếu tố nào giống nhau giữa G1 và ZGC?
4. Ngoài GC pause, cần đo những số liệu nào?
5. Nếu dùng virtual thread, cần phân biệt những loại thread nào?

**Đáp án:**

1. Nó không tạo đủ allocation pressure, CPU contention, queue và tương tác với database/connection pool như production.
2. Ít nhất mức thấp, mức thường 40 active, mức peak 64 active và một kịch bản burst phù hợp với tải thật; ghi riêng pool size và active/runnable thread.
3. Cùng JDK build, application artifact, request mix, dữ liệu, CPU/RAM quota, heap, dependency, load generator và thời gian warm-up/đo.
4. Throughput, p95/p99/p99.9, timeout/error, allocation rate, GC cycle/pause, CPU/throttling, RSS/native memory, queue, connection pool wait và database latency.
5. Phân biệt virtual thread, platform thread, active worker và runnable thread; số virtual thread không đồng nghĩa số thread chạy CPU song song.

## Ghi nhớ

**So sánh G1 và ZGC phải dùng workload đại diện với số worker, active thread và request concurrency gần production.** Giữ cùng JDK, CPU/memory budget, heap, dữ liệu và request mix; chạy baseline rồi mới tune riêng từng collector. Đo p99/p99.9, throughput, GC pause/cycle, allocation stall, CPU, RSS, queue, thread state và downstream latency. G1 pause goal không phải hard guarantee; ZGC pause thấp vẫn cần CPU và memory headroom. Chọn collector dựa trên SLO và kết quả lặp lại ở tải bình thường, peak và burst.

## Tài liệu tham khảo

- [Oracle Java SE 26 — Garbage Collection Tuning Guide](https://docs.oracle.com/en/java/javase/26/gctuning/)
- [Oracle Java SE 26 — G1 Garbage Collector Tuning](https://docs.oracle.com/en/java/javase/26/gctuning/garbage-first-garbage-collector-tuning.html)
- [Oracle Java SE 26 — Z Garbage Collector](https://docs.oracle.com/en/java/javase/26/gctuning/z-garbage-collector.html)
- [Oracle Java SE 26 — The `java` Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [Oracle Java SE 26 — `jcmd` Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jcmd.html)
- [JEP 248 — Make G1 the Default Garbage Collector](https://openjdk.org/jeps/248)
- [JEP 377 — ZGC: A Scalable Low-Latency Garbage Collector](https://openjdk.org/jeps/377)
- [JEP 474 — ZGC: Generational Mode by Default](https://openjdk.org/jeps/474)
