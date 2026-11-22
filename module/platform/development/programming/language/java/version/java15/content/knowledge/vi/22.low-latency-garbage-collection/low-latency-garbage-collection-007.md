# Chọn garbage collector theo mục tiêu có số đo (Java 15+)

## 1. Bài toán: “GC nào nhanh nhất?” không phải câu hỏi đủ chính xác

Trong JVM, **garbage collector (GC)** thu hồi bộ nhớ của những đối tượng không còn được sử dụng. Các collector khác nhau ưu tiên các đặc tính khác nhau: thời gian ứng dụng bị dừng, thông lượng, CPU dùng cho GC, lượng heap cần dự phòng và mức tiêu thụ bộ nhớ thực tế.

Vì thế, câu hỏi “collector nào tốt nhất?” chỉ có thể trả lời sau khi xác định **workload**, **mục tiêu đo được** và **giới hạn tài nguyên** của ứng dụng.

Ví dụ:

- Một **API giao dịch** yêu cầu phản hồi p99 dưới 50 ms khi có 20.000 yêu cầu/giây và không muốn GC gây những khoảng dừng dài.
- Một **batch ETL** chạy trong vài phút quan tâm tổng thời gian hoàn thành hơn là từng khoảng dừng.
- Một **dịch vụ container** có ngân sách bộ nhớ 1 GiB, số core CPU giới hạn, cần tránh OOMKill.
- Một **hệ thống real-time mềm** muốn giảm tail latency nhưng vẫn phải duy trì throughput trong những đợt tăng tải.

Các hệ thống đó có thể chọn collector khác nhau, **ngay cả khi chạy cùng phiên bản Java**.

**Nguyên tắc chính của bài:** định nghĩa tiêu chí thành số, đo bằng workload đại diện, so sánh trong cùng điều kiện, kiểm tra failure modes và chỉ sau đó chọn collector. Không kết luận theo khẩu hiệu “ZGC luôn tốt nhất” hoặc “G1 luôn đủ nhanh”.

Trong Java 15, **ZGC** và **Shenandoah** được đưa vào trạng thái production tại những build hỗ trợ, mở thêm các lựa chọn GC độ trễ thấp. Nhưng JDK hiện đại đã thay đổi cách triển khai một số collector; cần dùng **tùy chọn đúng với JDK thực tế**, không sao chép nguyên cấu hình từ các bài viết cũ.

## 2. Các chỉ số phải thống nhất trước khi so sánh

### 2.1. Pause time: JVM dừng ứng dụng bao lâu?

**Stop-the-world (STW) pause** là khoảng thời gian ứng dụng bị dừng bởi một hoạt động JVM, có thể do GC hoặc một safepoint khác. GC pause thường tính bằng millisecond hoặc microsecond.

Cần biết:

- **Số lần pause** trong một khoảng đo.
- **p50/p95/p99/p99.9 pause duration** và **max pause**.
- **Tổng thời gian dừng vì GC** trong cửa sổ đo.
- **Những pha nào dừng ứng dụng, những pha nào chạy concurrent**.
- Có **Full GC/degenerate/fallback/evacuation failure** hoặc những tình huống bất thường không?

Chú ý: một giá trị p99 GC pause **không đồng nghĩa** p99 độ trễ request. Ví dụ, GC pause 3 ms nhưng request mất 500 ms vì database, lock contention hoặc network. Ngược lại, pause GC 20 ms có thể ảnh hưởng đáng kể các request rơi đúng thời điểm pause.

**Mục tiêu GC pause** không phải một bảo đảm hard real-time. Với G1, `-XX:MaxGCPauseMillis=...` là **mục tiêu heuristic** mà collector cố gắng đạt, không phải giới hạn cứng cho tất cả các pause.

### 2.2. End-to-end latency: người dùng thật đợi bao lâu?

Đo latency **từ đầu tới cuối** theo đúng điểm đo dịch vụ (ví dụ từ lúc server nhận HTTP request đến khi hoàn tất phản hồi). Các percentile thường dùng:

- **p50:** thời gian điển hình.
- **p95:** phần đuôi chậm hơn.
- **p99:** 1% yêu cầu chậm nhất.
- **p99.9:** 0,1% yêu cầu chậm nhất, cần đủ lượng mẫu.

Ví dụ: **SLO giả định** “p99 latency dưới 50 ms trong cửa sổ đo tại 20.000 requests/s”. Đây chỉ là con số minh họa cách viết SLO, **không phải SLO mặc định của Java**.

Để kết luận GC có ảnh hưởng tới tail latency, cần **đối chiếu thời điểm request chậm với sự kiện GC pause và safepoint**, không dựa vào tên collector.

### 2.3. Throughput: xử lý được bao nhiêu công việc?

Với API: requests/s, operations/s, transactions/s. Với batch: records/s hoặc tổng thời gian hoàn tất.

Cần phân biệt:

- **Offered load**: tải được tạo gửi tới hệ thống.
- **Completed throughput**: số yêu cầu hoàn thành thành công mỗi giây.
- **Error/timeout rate**: tỉ lệ thất bại.
- **Saturation**: CPU, queue, connections hoặc GC không theo kịp cấp phát.

**Throughput cao nhưng tăng lỗi/timeout không phải kết quả thắng.** Nếu workload không đạt tải mục tiêu thì ngay cả p99 đẹp cũng chưa có ý nghĩa để chọn.

### 2.4. Memory footprint: không chỉ nhìn `-Xmx`

Các đại lượng nên theo dõi:

| Chỉ số | Ý nghĩa |
| --- | --- |
| **Live set** | Dữ liệu còn sống sau khi GC, cần đủ heap để giữ. |
| **Allocation rate** | Số byte được cấp phát/giây; tạo áp lực thu gom. |
| **Heap used / committed / max** | Dung lượng heap thực dùng, đã commit, giới hạn. |
| **RSS / container working set** | Bộ nhớ vật lý mà process/container thực dùng. |
| **Native memory** | Metaspace, code cache, thread stacks, direct buffers và các thành phần ngoài Java heap. |
| **Peak memory under bursts** | Dung lượng đỉnh khi có spike, có thể dẫn đến OOMKill. |

`-Xmx512m` chỉ giới hạn **Java heap tối đa**, không giới hạn toàn bộ RSS của JVM xuống 512 MiB. Một collector cần headroom cho concurrent collection; chọn heap quá sát live set có thể gây GC liên tiếp và giảm thông lượng.

### 2.5. CPU và chi phí vận hành

Collector chạy concurrent có thể giảm STW pause, nhưng **dùng CPU trong khi application threads đang chạy**. Hãy đo:

- CPU process/container (đặc biệt khi có CPU quota).
- CPU thời gian GC so với application threads.
- Thời gian chờ, scheduling và contention.
- Số thread, độ ổn định throughput khi CPU bị giới hạn.
- Mức biến động của latency qua nhiều lần chạy, không chỉ lần tốt nhất.

Không nên xem “pause thấp” là miễn phí về CPU. Lựa chọn phải vừa ngân sách latency **vừa** ngân sách CPU và memory.

## 3. Các collector cần cân nhắc trong HotSpot hiện đại

Những lựa chọn phổ biến cần đánh giá:

| Collector | Điểm mạnh điển hình | Trade-off cần đo | Tùy chọn JVM |
| --- | --- | --- | --- |
| **G1 GC** | Cân bằng throughput và độ dài pause; phù hợp nhiều workload server; là mặc định trên đa số cấu hình server HotSpot. | Có STW pauses; `MaxGCPauseMillis` chỉ là mục tiêu, không đảm bảo tuyệt đối. | `-XX:+UseG1GC` |
| **ZGC** | GC đồng thời, tối ưu thời gian tạm dừng rất ngắn trên các heap khác nhau. | Cần heap headroom và CPU cho concurrent work; throughput/footprint có thể khác G1. | `-XX:+UseZGC` |
| **Parallel GC** | Ưu tiên tổng throughput trong các workload mà pause dài chấp nhận được. | Full/young pauses có thể dài hơn mục tiêu latency chặt. | `-XX:+UseParallelGC` |
| **Shenandoah** | Concurrent, hướng tới pause thấp khi build JVM hỗ trợ. | Khả dụng và mode phụ thuộc JDK distribution/version; đo CPU và memory. | `-XX:+UseShenandoahGC` khi có |
| **Serial GC** | Đơn giản, ít GC threads, có thể phù hợp heap/tài nguyên rất nhỏ. | STW sử dụng ít parallelism, không phù hợp mặc định cho nhiều dịch vụ latency-sensitive có tải lớn. | `-XX:+UseSerialGC` |

**Điểm khởi đầu an toàn:** thử JVM default với heap hợp lý; trên đa số server HotSpot đó là **G1**. Chỉ đổi collector sau khi đã có **bằng chứng rằng default không đạt mục tiêu** hoặc có mục tiêu rõ ràng đòi hỏi đánh giá khác.

### 3.1. G1: baseline quan trọng

G1 là collector generational, incremental và mostly-concurrent. Nó phân chia heap thành regions, thực hiện một phần công việc đồng thời và một phần trong **STW evacuation pauses**.

Ưu điểm: khá cân bằng giữa latency và throughput, nhiều default/heuristics đã được tối ưu cho server. G1 có thể cố gắng đáp ứng mục tiêu pause bằng cách điều chỉnh phần việc trong mỗi collection.

Ví dụ cấu hình minh họa:

~~~bash
java -Xms512m -Xmx512m -XX:+UseG1GC \
     -XX:MaxGCPauseMillis=50 \
     -jar app.jar
~~~

Dấu `\` nối dòng ở trên dùng theo shell kiểu Bash; trên PowerShell/Windows cần đưa lệnh về một dòng hoặc dùng cú pháp nối dòng của shell phù hợp. `50` là **mục tiêu 50 ms**, không phải kết quả thực đo hay giới hạn cứng.

**Không khuyến nghị chỉnh hàng chục G1 flags ngay từ đầu.** Trước hết kiểm tra live set, allocation rate, heap headroom và phân bố pauses. Tinh chỉnh một biến có thể tăng throughput nhưng cũng có thể làm p99 tệ hơn.

### 3.2. ZGC: lựa chọn cho yêu cầu pause rất chặt

ZGC thực hiện phần lớn công việc thu gom concurrent với application threads và được thiết kế cho **low latency**. Tài liệu HotSpot hiện đại mô tả GC pause ở mức rất nhỏ, nhưng **không nên chuyển mô tả thiết kế thành một SLA bảo đảm tuyệt đối trong ứng dụng của bạn**.

Chọn ZGC làm ứng viên khi dữ liệu cho thấy GC pauses của collector hiện tại thực sự là nút thắt tail latency. Sau đó xác minh **CPU, memory footprint và thông lượng** có còn đạt SLO không.

Ví dụ:

~~~bash
java -Xms512m -Xmx512m -XX:+UseZGC -jar app.jar
~~~

**Đặc biệt quan trọng với Special Note về nội dung còn áp dụng:**

- Java 15 đưa ZGC thành tính năng production (JEP 377), nhưng triển khai lúc đó không giống hoàn toàn các JDK mới.
- Từ **JDK 24**, ZGC dùng **generational mode**, và **non-generational ZGC đã bị loại bỏ** (JEP 490). Với JDK 24+, `-XX:+UseZGC` là đủ để chọn ZGC; **không sử dụng các hướng dẫn cũ yêu cầu `-XX:+ZGenerational` hoặc `-XX:-ZGenerational`**.
- Vì ZGC thu gom concurrent, **heap cần đủ chỗ cho live data và cho cấp phát tiếp trong lúc GC đang chạy**. Heap quá chật có thể làm giảm đáng kể chất lượng latency/throughput.
- ZGC cũng có thể sử dụng nhiều tài nguyên CPU hơn; quan sát CPU quota và workload trước khi chọn.

### 3.3. Parallel GC: khi throughput là ưu tiên thực sự

`-XX:+UseParallelGC` có thể là ứng viên mạnh cho batch jobs hoặc công việc có thể chấp nhận pause. Nó tận dụng nhiều GC threads để thu gom song song, đặt trọng tâm vào thông lượng.

Ví dụ:

~~~bash
java -Xms512m -Xmx512m -XX:+UseParallelGC -jar batch.jar
~~~

Không chọn Parallel chỉ vì trong một benchmark ngắn operations/s cao nhất, nếu hệ thống thực tế có **SLO p99 chặt**. Cần quan sát pause max, tail latency và ảnh hưởng đến các yêu cầu đang chạy.

### 3.4. Shenandoah: có ích, nhưng phải xác nhận build hỗ trợ

Shenandoah được đưa vào production ở Java 15 (JEP 379) trong các build OpenJDK có thành phần này. **Không phải mọi JDK vendor/package đều nhất thiết tích hợp Shenandoah**.

Nếu runtime có hỗ trợ:

~~~bash
java -XX:+UseShenandoahGC -jar app.jar
~~~

JDK 25 đã hoàn thiện **Generational Shenandoah** (JEP 521) trên các build hỗ trợ. Nếu muốn kiểm thử mode này trên một JDK phù hợp, cú pháp là:

~~~bash
java -XX:+UseShenandoahGC \
     -XX:ShenandoahGCMode=generational \
     -jar app.jar
~~~

Đây là **lựa chọn có điều kiện theo JDK distribution/version**, không phải flag có thể copy chạy trên mọi JVM. `-XX:ShenandoahGCMode=generational` **không phải cấu hình mặc định cần thiết** của ứng dụng Java 15; phải đối chiếu tài liệu của JDK đang dùng. Đừng thêm các flag unlock experimental của hướng dẫn cũ nếu JDK hiện hành không yêu cầu.

### 3.5. Những lựa chọn không nên sao chép từ bài viết cũ

Để tránh hướng dẫn lỗi thời:

- **CMS** (`-XX:+UseConcMarkSweepGC`) đã bị loại khỏi HotSpot từ JDK 14, không phải ứng viên GC Java 15+ hiện đại.
- **ZGC non-generational flags** không còn dùng trên JDK 24+.
- Không cần `-XX:+UnlockExperimentalVMOptions` chỉ để bật ZGC production ở Java 15+.
- Không so sánh collector qua một thông số duy nhất hay một bài đăng benchmark khác JDK/hardware.
- Không áp tham số cũ cho GC hiện hành mà không xem lại `java -XX:+PrintFlagsFinal -version` và tài liệu tương ứng.

## 4. Chuyển yêu cầu nghiệp vụ thành SLO và tiêu chí loại trừ

Trước khi chạy benchmark, hãy viết **điều kiện quyết định**. Ví dụ giả định cho một API quan trọng:

| Nhóm | Điều kiện chấp nhận ví dụ |
| --- | --- |
| Tải | Duy trì **20.000 successful requests/s** trong thời gian đo. |
| Tail latency | `p99 end-to-end < 50 ms` và `p99.9 < 120 ms`. |
| GC pauses | `p99 GC pause < 10 ms`; `max pause < 50 ms` khi đủ dữ liệu. |
| Ổn định | Không OOM, không GC overhead kéo dài, lỗi ứng dụng dưới ngưỡng nghiệp vụ. |
| CPU | CPU sử dụng trung bình và peak nằm trong quota, ví dụ **< 75%** trong một số cửa sổ đo. |
| Bộ nhớ | RSS/container working set dưới giới hạn triển khai, có headroom cho spike. |
| Bursts | Vẫn đáp ứng các điều kiện chính khi tải tăng ngắn hạn, hoặc có chính sách degradation chấp nhận được. |

**Tất cả con số ở bảng trên là ví dụ**, không phải chuẩn JDK hay khuyến nghị áp dụng ngay cho mọi dịch vụ.

Một quy tắc chọn minh bạch:

> Loại những cấu hình không đạt SLO hoặc vượt quota. Trong số còn lại, chọn cấu hình có throughput/footprint/chi phí vận hành tốt nhất và hành vi ổn định nhất. Nếu không cấu hình nào đạt, xem lại ứng dụng, heap, tải và SLO thay vì cố chọn collector theo tên.

**Không nên cộng một “điểm tổng” tùy ý** khiến một cấu hình có p99 latency vượt giới hạn lại chiến thắng vì throughput cao. Các chỉ tiêu bắt buộc nên được áp dụng như **điều kiện loại trừ** trước.

## 5. Các phép đo cần ghi để chọn GC

### 5.1. Bắt đầu với baseline thật

Chạy ứng dụng bằng **collector mặc định** và ghi:

- JDK vendor/version/build, OS/container image, kernel, CPU count/quota, memory limit.
- `-Xms`, `-Xmx`, các cờ JVM liên quan và GC thực sự được chọn.
- Throughput, success/error rate, p50/p95/p99/p99.9 latency, max latency.
- GC pauses, GC cycle frequency, allocation rate, live set và heap sau GC.
- RSS, CPU tổng, CPU GC/concurrent overhead, tốc độ tăng memory.
- Thời gian chạy **warm-up** và thời gian đo **steady state**, số vòng lặp/đợt lặp.

Có thể xác nhận GC đang dùng bằng JVM log khởi động:

~~~bash
java -Xlog:gc -version
~~~

Dòng log sẽ cho biết collector được HotSpot chọn trong môi trường ấy. Không mặc định rằng mọi container/JVM image giống nhau; default có thể phụ thuộc CPU/RAM và JDK distribution.

### 5.2. Unified GC logging: bằng chứng gốc về pause

Trên HotSpot Java 15+, dùng **unified logging**:

~~~bash
java -Xms512m -Xmx512m -XX:+UseG1GC \
     -Xlog:gc*,safepoint:file=g1-gc.log:time,uptime,level,tags \
     -jar app.jar
~~~

Với ZGC, thay collector và file log:

~~~bash
java -Xms512m -Xmx512m -XX:+UseZGC \
     -Xlog:gc*,safepoint:file=zgc-gc.log:time,uptime,level,tags \
     -jar app.jar
~~~

`-Xlog:gc*` thu thập các sự kiện GC theo tags, `safepoint` giúp nhận diện cả những điểm dừng JVM liên quan khác. Đọc log để thống kê **thời gian GC pause thực**, không suy ra pause bằng tổng thời gian của một concurrent GC cycle.

Khi chạy lâu trên production, cần thiết kế **log rotation**, mức log hợp lý và kiểm soát dung lượng disk. Không bật log debug quá chi tiết vô thời hạn mà không đánh giá overhead và retention.

### 5.3. Java Flight Recorder (JFR): quan sát GC cùng toàn hệ thống

**JFR** là công cụ profiling/observability chuẩn có trong các JDK phù hợp, hữu ích để nhìn **GC events, safepoints, thread stalls, allocations, CPU và I/O** trong cùng trục thời gian.

Ví dụ bật recording:

~~~bash
java -XX:StartFlightRecording=filename=run.jfr,settings=profile,dumponexit=true \
     -Xms512m -Xmx512m -XX:+UseG1GC \
     -jar app.jar
~~~

Sau khi ứng dụng dừng và file đã được ghi:

~~~bash
jfr summary run.jfr
jfr print --events jdk.GCPhasePause run.jfr
~~~

`jdk.GCPhasePause` cho biết các khoảng dừng liên quan GC; `jdk.GarbageCollection` và các sự kiện khác cung cấp thêm bối cảnh. Kết hợp với timestamps application tracing và logs để xác định liệu **request chậm có trùng với GC pause** không.

**Lưu ý overhead:** `settings=profile` có thể thu thập nhiều event hơn `default`. Với benchmark latency nhạy cảm, cần đánh giá overhead của instrumentation và khi cần so sánh có/không bật profiler. Một số thao tác như heap statistics hoặc path-to-GC-roots có thể kích hoạt hoạt động thu gom bổ sung, không nên bật tùy tiện khi đo tail latency.

### 5.4. MXBean: thống kê thô, không phải pause p99

Java có `ManagementFactory.getGarbageCollectorMXBeans()` để xem tên collector, `getCollectionCount()` và `getCollectionTime()`. API này hữu ích cho **quan sát mức cao** nhưng không cung cấp phân bố pause chi tiết.

**Cảnh báo quan trọng:**

- `getCollectionTime()` có thể gồm thời gian đo của các collection activities theo từng bean; semantics khác collector/provider.
- Với collector concurrent, tổng thời gian collection không giống **thời gian toàn bộ application threads bị dừng**.
- Cộng `getCollectionTime` qua mọi bean **không phải công thức đo chính xác tổng STW pause**, và có thể không so sánh trực tiếp giữa G1, ZGC và Parallel GC.
- Để kiểm chứng pause SLO, dùng **GC logs/JFR** với sự kiện pause đúng nghĩa.

Ví dụ Java hoàn chỉnh phần sau có in các thống kê MXBean để **khảo sát nhanh**, đồng thời nêu rõ không dùng chúng thay GC pause histogram.

## 6. Thiết kế thí nghiệm công bằng

Một collector chỉ “thắng” nếu được thử trong **điều kiện phù hợp**.

### 6.1. Những thứ cần cố định

- **Cùng phiên bản JDK/build**, cùng ứng dụng và bytecode.
- Cùng OS/container image, CPU quota, thread count và vùng memory.
- Cùng khối lượng requests, distribution kích thước payload, thời gian warm-up và duration.
- Cùng data set, live set và trạng thái cache sau warm-up.
- Cùng `-Xmx` (khi so sánh cùng heap ngân sách) và log/profile overhead tương đương.
- Cùng network/DB dependencies hoặc cách mock ổn định để không biến so sánh GC thành so sánh network.
- Cùng số lần thử và quy tắc chọn kết quả (không chọn “best run”).

**Không nhất thiết phải đặt `-Xms == -Xmx` trong production.** Khi benchmark có thể dùng cùng `-Xms/-Xmx` để giảm khác biệt resizing, nhưng nếu footprint và khả năng uncommit memory là mục tiêu, cũng nên kiểm thử **cấu hình thực tế với `-Xms < -Xmx`**.

### 6.2. Warm-up, steady state và spikes

Một chương trình Java cần thời gian cho JIT compilation, class loading và cache warm-up. Nên tách ít nhất:

1. **Warm-up** để ổn định JIT/cache và allocation behavior.
2. **Steady state** để đo throughput, latency và GC.
3. **Burst/spike** để xem thời gian thích ứng và GC khi allocation rate tăng.
4. **Sustained high load** để đánh giá GC có theo kịp mutator hay không.
5. **Memory pressure** để tìm ranh giới heap headroom/OOM, không chỉ case nhẹ.

Một bài chạy 1 giây hoặc vài triệu phép cấp phát tổng hợp chỉ xác minh code/cờ/log, **không đủ để chọn collector cho production**.

### 6.3. Tránh coordinated omission và dữ liệu thống kê thiếu

Khi phát sinh tải request, nếu load generator ngừng gửi trong lúc server chậm, biểu đồ latency có thể “đẹp giả” vì không đo được các request lẽ ra đã đến. Nên dùng công cụ load generation phù hợp với SLO, quan sát **offered rate** và **completed rate**, số request chờ/hàng đợi và errors.

Để ước lượng p99.9 đáng tin cậy, cần nhiều mẫu thực, nhiều lần chạy và báo độ không chắc chắn; không suy ra p99.9 từ vài trăm operation.

Báo cáo nên gắn percentile với **tải, thời gian đo và số lượng mẫu**, ví dụ “p99 end-to-end latency = X ms, n = Y thành công, target throughput = Z/s”, chứ không ghi trơ một con số.

## 7. Ví dụ Java 15 chạy được: đo các chỉ số sơ bộ dưới các collector

Chương trình sau **không phải production benchmark và không mô phỏng HTTP service**. Nó có mục đích học tập: tạo workload cấp phát bộ nhớ, giữ một phần đối tượng sống qua vòng lặp, đo throughput gần đúng, lấy mẫu độ trễ **một thao tác cấp phát nhỏ**, và in tên collector cùng các MXBeans.

Các ý chính:

- `runPhase(warmupMs, false)` chạy một giai đoạn warm-up.
- `runPhase(measureMs, true)` chạy giai đoạn đo.
- Mỗi iteration tạo `byte[]` cỡ 1–3 KiB, một phần được giữ trong vòng `retained`.
- Mỗi 32 iteration lấy mẫu thời gian thao tác bằng `System.nanoTime()`; tối đa 100.000 mẫu để không tăng bộ nhớ vô hạn.
- Sắp xếp mẫu rồi tính p50/p95/p99 theo nearest-rank.
- Đọc `GarbageCollectorMXBean` trước/sau để in số collection và thời gian **thô** theo bean.
- Không dùng `System.gc()` để tự kích hoạt collection và không khẳng định số liệu là SLO production.

### 7.1. File `GcSloProbe.java`

~~~java
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public final class GcSloProbe {
    private static volatile long checksum;

    static final class Result {
        final long operations;
        final long elapsedNanos;
        final long[] latencies;
        final int samples;
        final long gcCount;
        final long gcTimeMs;

        Result(long operations, long elapsedNanos, long[] latencies, int samples,
               long gcCount, long gcTimeMs) {
            this.operations = operations;
            this.elapsedNanos = elapsedNanos;
            this.latencies = latencies;
            this.samples = samples;
            this.gcCount = gcCount;
            this.gcTimeMs = gcTimeMs;
        }
    }

    private static long totalGcCount() {
        long sum = 0;
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            if (bean.getCollectionCount() >= 0) {
                sum += bean.getCollectionCount();
            }
        }
        return sum;
    }

    private static long totalGcTimeMs() {
        long sum = 0;
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            if (bean.getCollectionTime() >= 0) {
                sum += bean.getCollectionTime();
            }
        }
        return sum;
    }

    private static Result runPhase(int durationMs, boolean measure) {
        byte[][] retained = new byte[2048][];
        long[] durations = measure ? new long[100_000] : new long[0];
        long count = 0;
        int sampled = 0;
        long localChecksum = 0;
        long beforeGc = totalGcCount();
        long beforeGcMs = totalGcTimeMs();
        long begin = System.nanoTime();
        long endAt = begin + durationMs * 1_000_000L;

        while (System.nanoTime() < endAt) {
            boolean sampledOp = measure && (count & 31L) == 0
                    && sampled < durations.length;
            long opStart = sampledOp ? System.nanoTime() : 0;
            byte[] payload = new byte[1024 + (int) (count & 2047L)];
            payload[0] = (byte) count;
            payload[payload.length - 1] = (byte) (count >>> 8);
            if ((count & 31L) == 0) {
                retained[(int) ((count >>> 5) & 2047L)] = payload;
            }
            localChecksum += payload[0] + payload[payload.length - 1];
            if (sampledOp) {
                durations[sampled++] = System.nanoTime() - opStart;
            }
            count++;
        }

        long elapsed = System.nanoTime() - begin;
        checksum = localChecksum;
        Arrays.sort(durations, 0, sampled);
        return new Result(count, elapsed, durations, sampled,
                totalGcCount() - beforeGc, totalGcTimeMs() - beforeGcMs);
    }

    private static long percentile(Result r, int percentile) {
        if (r.samples == 0) return -1;
        int index = Math.max(0,
                (int) Math.ceil(r.samples * percentile / 100.0) - 1);
        return r.latencies[Math.min(index, r.samples - 1)];
    }

    public static void main(String[] args) {
        int warmupMs = args.length > 0 ? Integer.parseInt(args[0]) : 500;
        int measureMs = args.length > 1 ? Integer.parseInt(args[1]) : 1500;
        if (warmupMs < 100 || measureMs < 100) {
            throw new IllegalArgumentException("Durations must be >= 100 ms");
        }

        List<String> names = new ArrayList<>();
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            names.add(bean.getName());
        }
        runPhase(warmupMs, false);
        Result result = runPhase(measureMs, true);

        double throughput = result.operations * 1_000_000_000.0
                / result.elapsedNanos;
        long p50 = percentile(result, 50);
        long p95 = percentile(result, 95);
        long p99 = percentile(result, 99);

        System.out.println("collectors=" + String.join(", ", names));
        System.out.printf(Locale.ROOT, "operationsPerSecond=%.1f%n", throughput);
        System.out.println("latencySamples=" + result.samples);
        System.out.println("sampledOperationP50Ns=" + p50);
        System.out.println("sampledOperationP95Ns=" + p95);
        System.out.println("sampledOperationP99Ns=" + p99);
        System.out.println("gcCountDelta=" + result.gcCount);
        System.out.println("gcTimeMxBeanDeltaMs=" + result.gcTimeMs);
        System.out.println("measurementsValid=" +
                (result.samples > 0 && throughput > 0 && p50 <= p95 && p95 <= p99));
    }
}
~~~

### 7.2. Biên dịch và so sánh nhanh G1, Parallel, ZGC

Lưu file đúng tên và biên dịch:

~~~bash
javac --release 15 -encoding UTF-8 GcSloProbe.java
~~~

Chạy từng trường hợp **riêng**, trên cùng máy/JDK và heap 256 MiB:

~~~bash
java -Xms256m -Xmx256m -XX:+UseG1GC \
     -Xlog:gc*,safepoint:file=g1-gc.log:time,uptime,level,tags \
     GcSloProbe 250 900
~~~

~~~bash
java -Xms256m -Xmx256m -XX:+UseParallelGC \
     -Xlog:gc*,safepoint:file=parallel-gc.log:time,uptime,level,tags \
     GcSloProbe 250 900
~~~

~~~bash
java -Xms256m -Xmx256m -XX:+UseZGC \
     -Xlog:gc*,safepoint:file=zgc-gc.log:time,uptime,level,tags \
     GcSloProbe 250 900
~~~

Ở PowerShell, đưa các dòng thành **một lệnh** hoặc thay dấu nối dòng Bash theo cú pháp của shell. Tên file log khác nhau để không ghi đè kết quả.

**Đã biên dịch `javac --release 15` và chạy thành công ba cấu hình trên JDK 24**. Chương trình xuất các trường:

~~~text
collectors=...
operationsPerSecond=...
latencySamples=...
sampledOperationP50Ns=...
sampledOperationP95Ns=...
sampledOperationP99Ns=...
gcCountDelta=...
gcTimeMxBeanDeltaMs=...
measurementsValid=true
~~~

Dấu `...` trong khối này là **ký hiệu mô tả các giá trị biến thiên**, không phải stdout được dự đoán chính xác. Tên collector beans, tốc độ và các percentile thực tế phụ thuộc CPU, OS, heap, JIT và JDK. Dòng cuối được kiểm chứng là `measurementsValid=true` trên cả ba lần chạy thử.

Ví dụ **một stdout thực tế đã đo bằng G1 trên JDK 24**:

~~~text
collectors=G1 Young Generation, G1 Concurrent GC, G1 Old Generation
operationsPerSecond=3554002.5
latencySamples=99957
sampledOperationP50Ns=200
sampledOperationP95Ns=500
sampledOperationP99Ns=900
gcCountDelta=42
gcTimeMxBeanDeltaMs=44
measurementsValid=true
~~~

Kết quả riêng từ cùng quá trình thử nhanh:

| Collector | Compile/run | Kết luận có thể rút ra |
| --- | --- | --- |
| G1 | PASS | JVM chạy workload và ghi GC log thành công. |
| Parallel GC | PASS | JVM chạy workload và ghi GC log thành công. |
| ZGC | PASS | JVM chạy workload và ghi GC log thành công. |

**Không thể kết luận G1 “thắng” hay ZGC “thua” từ phép thử 900 ms này.** Nó là kiểm thử tính hoạt động của ví dụ và flag, không phải một thí nghiệm đại diện. Thay đổi kích thước heap, live set, allocation pattern hoặc workload có thể đảo ngược thứ hạng.

**Giới hạn cụ thể của mã học tập:**

- Độ trễ `sampledOperationP99Ns` là p99 **của những thao tác cấp phát được lấy mẫu**, **không phải p99 HTTP request**, cũng không phải p99 GC pause.
- Tối đa 100.000 sample; các sample về cuối có thể không được ghi nếu đã đầy, gây sampling bias.
- `getCollectionTime()` không đo chính xác STW pause tổng; semantics khác nhau ở collector concurrent.
- Bài đo rất ngắn; JIT, scheduler và timer overhead có thể chi phối các con số ở đơn vị nanosecond.
- Các phép cấp phát có thể được compiler/JIT tối ưu khác nhau; benchmark thực tế nên dùng workload ứng dụng hoặc công cụ phù hợp.
- Không tính RSS, CPU, error rate, p99 end-to-end, full safepoint distribution hay SLO production.

Vì vậy, để **chọn collector**, phải chạy ứng dụng thật dưới tải đại diện, kết hợp telemetry và kiểm soát biến; code ở đây chỉ giúp học cách **đọc kết quả, bật log và không nhầm metrics**.

### 7.3. Kiểm chứng JFR

Một lệnh đã được chạy thành công trong thử nghiệm JDK 24:

~~~bash
java -Xms256m -Xmx256m -XX:+UseG1GC \
     -XX:StartFlightRecording=filename=g1-probe.jfr,settings=profile,dumponexit=true \
     GcSloProbe 150 700
~~~

File `g1-probe.jfr` đã được sinh; `jfr summary` ghi nhận sự kiện `jdk.GCPhasePause` và `jdk.GarbageCollection`. Đây là bước xác nhận **chuỗi công cụ đo hoạt động**, chưa phải benchmark quyết định SLO. Nếu không có JFR trong bản build JVM đang dùng, cần sử dụng GC logging/monitoring được hỗ trợ thay thế.

## 8. Đọc kết quả mà không chọn nhầm GC

### 8.1. Ma trận quyết định bằng điều kiện

Giả sử sau khi **benchmark ứng dụng thật**, có dữ liệu như sau. Tất cả con số dưới đây là **giả định để học cách ra quyết định**, không phải số đo ở đoạn Java vừa chạy:

| Ứng viên | Throughput | p99 request | p99 GC pause | RSS peak | Quyết định nếu SLO: ≥20k rps, p99 request <50ms, RSS <2GiB |
| --- | ---: | ---: | ---: | ---: | --- |
| G1 | 24k rps | 65 ms | 23 ms | 1.35 GiB | **Loại**: p99 vượt mục tiêu. |
| Parallel | 28k rps | 120 ms | 80 ms | 1.22 GiB | **Loại**: p99 vượt mục tiêu, dù throughput cao. |
| ZGC | 22k rps | 38 ms | 0.8 ms | 1.72 GiB | **Đạt theo ba tiêu chí ví dụ**, cần xét thêm CPU, lỗi và spike. |
| Shenandoah (nếu có) | 21k rps | 43 ms | 1.6 ms | 1.83 GiB | **Đạt theo ba tiêu chí ví dụ**, cần xét thêm CPU và sự hỗ trợ trên distribution. |

Một cấu hình đạt điều kiện trên bảng **chưa tự được chọn**: phải xem thêm độ ổn định, CPU, memory headroom, rủi ro OOM và yêu cầu vận hành. Nếu các chỉ số thực tế khác, quyết định cũng phải khác.

Đặc biệt, **giảm GC p99 không bảo đảm giảm HTTP p99 tương ứng**; phân tích nguyên nhân request chậm bằng tracing/JFR.

### 8.2. Khi G1 không đạt p99

Đừng đổi ngay sang ZGC mà bỏ qua:

- Heap có quá chật? Live set chiếm gần hết heap?
- Allocation rate tăng đột ngột?
- Có object humongous lớn gây áp lực trong G1 không?
- CPU/quota thiếu làm thời gian GC kéo dài?
- Có `System.gc()` từ thư viện/tooling làm phát sinh pause?
- Request latency bị chi phối bởi database/locks thay vì GC?

Sau khi kiểm tra các nguyên nhân, nếu **GC pauses là giới hạn thực sự**, thử ZGC hoặc Shenandoah trên môi trường hỗ trợ. So sánh cùng throughput/memory ngân sách.

### 8.3. Khi ZGC có p99 GC pause thấp nhưng ứng dụng vẫn chậm

Có thể xảy ra:

- Concurrent GC lấy CPU từ application threads dưới quota thấp.
- Heap headroom thiếu, collector phải làm việc quá sức hoặc allocation stall.
- Latency nằm ở network/DB/lock, không liên quan GC.
- Tải gửi vượt sức xử lý, queue tăng; p99 end-to-end xấu.
- RSS quá cao dẫn tới memory pressure hoặc OOMKill.

**Không tăng heap vô hạn** để “giữ ZGC chạy”: phải xét giới hạn container, tỷ lệ live set và footprint ngoài heap. Tinh chỉnh dựa trên telemetry và thử lặp.

### 8.4. Khi Parallel có throughput tốt nhất

Với batch job không có hard tail latency, throughput có thể là mục tiêu đúng. Nhưng vẫn phải kiểm tra:

- Tổng wall-clock completion time, không chỉ operations/s của một vòng loop.
- CPU và mức dùng memory trong suốt job.
- Full GC pauses và khả năng làm trễ các nhiệm vụ khác dùng chung host.
- Ảnh hưởng tới SLA của các job khác và resource sharing.

“Low-latency collector” **không phải bắt buộc** khi ứng dụng không có yêu cầu pause chặt.

## 9. Heap sizing trước tuning chi tiết

Chọn GC và heap size là **hai quyết định liên quan**. Nếu heap quá chật, collector tốt đến đâu cũng khó đạt throughput và latency mong muốn.

### 9.1. Live set và headroom

Có thể hình dung:

~~~text
Xmx can phai du cho:
    live-set o peak load
  + allocation trong khi GC thuc hien
  + transient objects / bursts
  + GC-specific reserved space
~~~

Tỉ lệ headroom phù hợp phụ thuộc thực nghiệm, collector, allocation rate và CPU; không có quy tắc “luôn tăng heap lên đúng 2 lần” cho mọi ứng dụng.

Khi live set tăng dần không giảm qua nhiều collection, cần kiểm tra **memory leak/cache growth** thay vì chỉ tăng `-Xmx`.

### 9.2. `-Xms == -Xmx` có phải luôn đúng?

Không.

- Trong phép đo, đặt bằng nhau có thể giảm biến động do resizing và giúp các ứng viên có cùng fixed heap budget.
- Trong production, đặt `-Xms` thấp hơn `-Xmx` có thể giúp JVM điều chỉnh memory commitment theo tải và trả lại bộ nhớ khi được hỗ trợ.
- Trong container, **RSS và giới hạn toàn process** quan trọng; không phải cứ `-Xmx` dưới limit là đủ.
- Pre-touch và huge pages có thể ảnh hưởng startup/latency/footprint; chỉ bật khi có kết quả đo rõ.

Nếu thay `-Xms/-Xmx` khi chuyển collector, phải ghi rõ **đây là hai thay đổi cùng lúc**, khó quy tác động cho GC riêng lẻ. Nên có các vòng thử điều khiển.

## 10. Quy trình benchmark tối thiểu có thể kiểm tra được

### Giai đoạn A — baseline và giả thuyết

Viết ra: “Ứng dụng đang chạy G1, p99 latency vượt SLO trong spike; GC log cho thấy p99 pause tăng đúng thời điểm request chậm.” Hoặc “batch cần throughput cao hơn, không có pause SLO”.

Nếu GC không phải nút thắt, **không thay GC chỉ vì có collector mới**.

### Giai đoạn B — ứng viên hợp lệ

Kiểm tra `java -version`, `java -XX:+PrintFlagsFinal -version` (chỉ dùng đọc), cấu hình container và collector flags được runtime hỗ trợ. Trên JDK 24+, ZGC đã generational; nếu thử Shenandoah phải chắc chắn bản JVM đó cung cấp nó.

Danh sách ứng viên nên nhỏ, ví dụ **Default G1 → ZGC → Parallel** hoặc thêm Shenandoah khi có và có lý do.

### Giai đoạn C — test có kiểm soát

Với mỗi ứng viên:

1. Warm-up đủ thời gian.
2. Chạy cùng tải ổn định và các burst.
3. Ghi GC log/JFR, application latency và throughput.
4. Ghi CPU, RSS, OOM, native memory nếu có.
5. Lặp nhiều lần, báo cả variation/min/median/max khi phù hợp.
6. Kiểm tra các ranh giới memory/CPU quota và cách JVM hồi phục sau burst.

Không dùng một lần chạy tốt nhất để quyết định.

### Giai đoạn D — chọn cấu hình

Áp dụng các **điều kiện loại trừ SLO** trước; sau đó mới so sánh hiệu quả tài nguyên và chi phí vận hành giữa các ứng viên còn lại.

Nếu mọi ứng viên đều không đạt, cần xem lại code cấp phát, giữ object, cache, CPU/heap budget hoặc thiết kế ứng dụng. Cố ép collector giải quyết một memory leak sẽ không tạo ra giải pháp bền vững.

### Giai đoạn E — rollout và theo dõi

Khi triển khai:

- Canary/blue-green với một phần lưu lượng phù hợp.
- Theo dõi p99/p99.9 latency, throughput, errors, CPU, RSS, heap và GC pause.
- Có rollback và phân biệt tác động do GC với biến động tải.
- Giữ dữ liệu baseline để so sánh sau mỗi nâng cấp JDK.
- Kiểm thử lại khi nâng version JDK, thay container limits hoặc thay allocation profile.

**Tối ưu GC là quá trình lặp**, không phải một flag được chọn một lần rồi quên.

## 11. Những lỗi suy luận phổ biến

| Sai lầm | Vì sao sai? | Cách sửa |
| --- | --- | --- |
| “Chọn collector có p99 GC pause thấp nhất là đủ.” | Request latency, CPU, RSS và throughput có thể không đạt. | Chọn theo toàn bộ SLO và constraints. |
| “`-XX:MaxGCPauseMillis=10` bảo đảm mọi pause <10ms.” | Đây là mục tiêu của G1, không phải hard guarantee. | Đo histogram pause thực tế. |
| “JDK 24+ phải thêm `-XX:+ZGenerational` cho ZGC.” | Flag chọn mode không còn cần/được hỗ trợ sau khi non-generational mode bị loại. | Dùng `-XX:+UseZGC`. |
| “G1 là default nên không bao giờ phải đo.” | Default phù hợp nhiều máy, không bảo đảm workload cụ thể. | Đo baseline trước và sau thay đổi. |
| “Parallel throughput cao hơn trên toy test ⇒ phù hợp cho API p99.” | Toy microbenchmark không đo end-to-end tail. | Thử tải API và GC pause thực. |
| “`getCollectionTime` là tổng STW pause.” | Concurrent GC có thời gian activity không tương đương pause. | Dùng GC log/JFR pause events. |
| “Heap used thấp ⇒ process memory thấp.” | Metaspace, direct buffers, native memory, threads. | Đo RSS/container footprint. |
| “Tăng heap luôn làm GC nhanh hơn.” | Tốn memory và có thể thay trade-off, tăng RSS. | Chọn headroom bằng measurements. |
| “Một lần benchmark đủ quyết định.” | JIT, scheduler, cache, spike và noise. | Warm-up, repeat và ghi variance. |
| “Shenandoah luôn có trên mọi JDK 15+.” | Khả dụng tùy vendor/distribution/version. | Kiểm tra runtime thật trước khi bật. |
| “Thời gian collector concurrent chính là thời gian dừng application.” | Concurrent phases chạy trong khi app vẫn tiến hành. | Phân biệt concurrent cycles và pause phases. |
| “Độ trễ 900 ns trong toy allocation test là HTTP p99.” | Chỉ là một phép toán nội bộ được sample. | Đo request latency ở ranh giới dịch vụ. |
| “Chỉ xét request thành công, bỏ timeout/error.” | Dễ tạo latency đẹp giả khi hệ thống quá tải. | Xem offered load, completed load và lỗi. |
| “ZGC luôn nên dùng cho mọi batch job.” | Có thể tăng CPU/footprint với ít lợi ích nếu không cần pause thấp. | So sánh throughput và completion time. |
| “CMS vẫn là lựa chọn hiện hành.” | CMS đã bị remove khỏi HotSpot JDK 14+. | Dùng collector được JDK hiện đại hỗ trợ. |

## 12. Bài tập tự kiểm tra

**Câu 1.** Một API có p99=80 ms, SLO p99<50 ms. G1 GC pause p99=2 ms. Có thể kết luận đổi sang ZGC sẽ giúp đạt SLO không?

**Đáp án:** Không. GC pause hiện đã khá nhỏ so với p99 request; nút thắt có thể nằm ở database, lock, queue hoặc network. Phải tương quan traces với GC trước.

**Câu 2.** Parallel GC cho throughput cao hơn 12%, nhưng p99 request vượt giới hạn 50 ms. Có nên chọn không?

**Đáp án:** Nếu p99<50 ms là **điều kiện bắt buộc**, không. Chỉ có thể cân nhắc nếu thay đổi SLO có căn cứ hoặc triển khai cho workload khác không cần latency chặt.

**Câu 3.** Vì sao `-XX:MaxGCPauseMillis=50` không phải chứng cứ đã đạt max pause 50 ms?

**Đáp án:** Đó là **mục tiêu heuristic** của G1, không đảm bảo mọi pause. Phải đo GC logs/JFR để thấy phân bố và giá trị cực đại thực.

**Câu 4.** Đặt `-Xmx256m` và thấy RSS=340MiB có phải JVM vượt giới hạn heap không?

**Đáp án:** Không nhất thiết. RSS còn native memory, metaspace, thread stacks, direct buffers và phần JVM khác ngoài Java heap.

**Câu 5.** Vì sao so sánh `getCollectionTime` giữa G1 và ZGC có thể gây hiểu nhầm?

**Đáp án:** Các collection activities và concurrent phases có semantics khác; tổng thời gian bean không phải GC pause histogram và không trực tiếp tương đương thời gian app bị dừng.

**Câu 6.** Với JDK 24+, muốn chọn ZGC cần flag gì?

**Đáp án:** `-XX:+UseZGC`; ZGC generational là chế độ hiện hành, tùy chọn `ZGenerational` đã được remove.

**Câu 7.** Tại sao cần test cả burst và steady state?

**Đáp án:** Allocation spikes, queue buildup, CPU saturation và heap headroom có thể khiến collector có kết quả đẹp ở steady state nhưng xuống cấp ở burst.

**Câu 8.** Ghi “p99=5ms” mà không nêu số mẫu, load và vị trí đo có đủ cơ sở chọn collector không?

**Đáp án:** Không. Phải biết đây là p99 request hay GC pause, tải bao nhiêu, thời lượng đo, sample size và sai số đo.

## 13. Ghi nhớ

- **Chọn GC theo mục tiêu có số đo, không theo tên.** Tối thiểu xét end-to-end p99/p99.9, throughput, pause, CPU, RSS và errors.
- **Dùng collector mặc định/G1 làm baseline** trên server HotSpot, rồi thử ZGC/Parallel/Shenandoah theo mục tiêu cụ thể.
- **ZGC hướng tới pause rất thấp** nhưng phải đo headroom/CPU và throughput; **Parallel ưu tiên throughput**, **G1 cân bằng**.
- **JDK 24+ ZGC đã generational**, không dùng các cờ `ZGenerational` cũ; Shenandoah generational chỉ chọn khi build/JDK hỗ trợ.
- **`MaxGCPauseMillis` chỉ là mục tiêu**, còn `getCollectionTime` không thay histogram pause.
- **GC logs/JFR giúp xác minh nguyên nhân**, nhưng quyết định cuối dựa trên SLO ứng dụng thật.
- **Một toy benchmark chỉ chứng minh code/công cụ chạy được**, không đủ để quyết định production.
- **Thử trong cùng điều kiện, warm-up, lặp, mô phỏng bursts, kiểm tra quota** và rollout có quan sát/rollback.

### Tài liệu chính thức và tài liệu kỹ thuật còn áp dụng

- [Oracle HotSpot GC Tuning Guide – Available Collectors (JDK 26)](https://docs.oracle.com/en/java/javase/26/gctuning/available-collectors.html): định hướng chọn G1, ZGC, Parallel và các trade-off.
- [Oracle HotSpot GC Tuning Guide – G1 (JDK 25)](https://docs.oracle.com/en/java/javase/25/gctuning/garbage-first-g1-garbage-collector1.html): G1 là mặc định trên nhiều cấu hình, mục tiêu pause không phải hard guarantee.
- [Oracle HotSpot GC Tuning Guide – ZGC (JDK 24)](https://docs.oracle.com/en/java/javase/24/gctuning/z-garbage-collector.html): ZGC hiện hành và headroom cho concurrent collection.
- [Oracle JDK 24 Migration Guide](https://docs.oracle.com/en/java/javase/24/migrate/significant-changes-jdk-24.html): non-generational ZGC bị loại, `ZGenerational` không còn.
- [OpenJDK JEP 377 – ZGC Production](https://openjdk.org/jeps/377): ZGC chuyển sang production ở Java 15.
- [OpenJDK JEP 379 – Shenandoah Production](https://openjdk.org/jeps/379): Shenandoah production ở Java 15 trên các build hỗ trợ.
- [OpenJDK JEP 490 – ZGC: Remove the Non-Generational Mode](https://openjdk.org/jeps/490): chuyển đổi ZGC trên JDK mới.
- [OpenJDK JEP 521 – Generational Shenandoah](https://openjdk.org/jeps/521): generational mode trong JDK 25.
- [Oracle JDK 26 Troubleshooting – JFR Performance & GC](https://docs.oracle.com/en/java/javase/26/troubleshoot/troubleshoot-performance-issues-using-jfr.html): phân tích GC pauses, stalls và allocation bằng JFR.
- [Oracle JDK 26 – Diagnostic Tools](https://docs.oracle.com/en/java/javase/26/troubleshoot/diagnostic-tools.html): JFR, heap và CPU events.
