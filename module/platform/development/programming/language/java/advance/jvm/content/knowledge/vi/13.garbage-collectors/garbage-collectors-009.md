# So sánh GC bằng cùng tải, giới hạn tài nguyên và mục tiêu độ trễ

## 1. Câu hỏi đúng: collector nào đạt yêu cầu ứng dụng trong cùng ngân sách?

Trong Java/JVM, **garbage collector (GC)** không có một thứ hạng “nhanh nhất” áp dụng cho mọi hệ thống. Kết quả phụ thuộc vào **tải thực**, phân bố tuổi thọ object, allocation rate, live-set size, heap, CPU cores, bộ nhớ tiến trình, phiên bản JDK, thời gian warm-up và đặc biệt là **mục tiêu độ trễ**.

So sánh công bằng không phải chỉ chạy hai JVM rồi đọc con số **GC pause thấp nhất**. Cần cố định hoặc ghi rõ những yếu tố kiểm soát, đưa tất cả ứng viên qua **cùng tiêu chí thành công**, sau đó mới xét trade-off:

- **Correctness và availability:** không bỏ request, không OOM, không bị container kill, cùng kết quả nghiệp vụ.
- **Throughput:** xử lý được bao nhiêu operation hoặc request thành công mỗi giây dưới cùng offered load.
- **Latency:** p50, p95, p99, p99.9, max và tỷ lệ vượt SLO; phân biệt *request latency* với *GC pause*.
- **Tài nguyên:** CPU quota/usage, tổng process RSS/cgroup memory, heap live/committed, native/direct memory, số threads.
- **GC costs:** tổng wall-clock STW, pause duration distribution, concurrent GC CPU, allocation rate, full GC, GC overhead và các safepoints không do GC.
- **Tính ổn định:** kết quả qua nhiều lượt độc lập, tải ổn định đủ lâu, không chỉ một run thắng ngẫu nhiên.

**Kết luận quan trọng:** collector có p99 GC pause ngắn nhất **chưa chắc** là collector làm p99 API latency thấp nhất hoặc đạt throughput cao nhất. Ngược lại, collector có throughput tốt có thể vi phạm tail-latency SLO hoặc vượt ngân sách bộ nhớ.

### Không nhầm “cùng tải” với “cùng số vòng lặp”

Hai JVM xử lý đúng 10.000 operations không có nghĩa chúng nhận cùng **tải theo thời gian**. Collector chậm có thể làm closed-loop client phát sinh request chậm hơn; do đó tải thực đến server ít hơn và độ trễ được quan sát có thể đẹp giả tạo.

Đối với benchmark **dịch vụ**, hãy kiểm soát **offered arrival rate** (lượng request chủ động phát theo thời gian), không chỉ đạt cùng tổng số request. Với benchmark **allocation micro-workload**, ít nhất cần cố định số lần lặp, kích thước object, tỷ lệ giữ sống, concurrency và heap; đồng thời nói rõ đó **không phải** đo production request latency.

## 2. GC nào là ứng viên đáng thử trên JDK 17?

Bảng này nói về **định hướng thiết kế**, không phải thứ hạng đã đo. Phải xác minh GC có được đóng gói và hoạt động trên distribution/JDK mục tiêu.

| Collector | Định hướng tổng quát | Trade-off cần đo |
| --- | --- | --- |
| **Serial GC** (`-XX:+UseSerialGC`) | Đơn giản, ít GC workers, có thể hợp workload nhỏ và CPU hạn chế | STW pauses có thể dài khi live set lớn; throughput trên nhiều cores có thể kém |
| **Parallel GC** (`-XX:+UseParallelGC`) | Ưu tiên throughput nhờ nhiều GC worker threads | Có thể chịu pauses đáng kể, nhất là live set lớn |
| **G1 GC** (`-XX:+UseG1GC`) | GC vùng/region, cố gắng cân bằng throughput và pause goals | Có overhead concurrent/remembered sets; pause goal là mục tiêu, không phải bảo đảm cứng |
| **ZGC** (`-XX:+UseZGC`) | Collector concurrent, hướng tới độ trễ pause rất thấp | Cần đo native/heap headroom, CPU và throughput; behavior của **JDK 17** không tự đồng nhất với ZGC ở JDK mới |
| **Shenandoah GC** (`-XX:+UseShenandoahGC`, **nếu bản JDK hỗ trợ**) | Collector concurrent tối ưu pauses thấp | Sự hiện diện/flags tùy bản OpenJDK distribution; chi phí CPU/throughput/memory cần đo |

**G1** là baseline hợp lý ở nhiều ứng dụng server HotSpot Java 17; Oracle JDK 17 hướng dẫn trước tiên chạy với collector do VM chọn nếu không có yêu cầu pause quá nghiêm ngặt, rồi điều chỉnh heap/collector khi cần. Nhưng **default không đồng nghĩa tối ưu** với mọi workload.

**Đừng bật nhiều `-XX:+Use*GC` cạnh tranh trong cùng một lệnh**. Mỗi benchmark là một JVM process riêng, bật đúng một collector.

**Lưu ý phiên bản:** Java 17 ZGC không giống hoàn toàn các khả năng của generational ZGC trong các JDK sau. Shenandoah có thể không có ở một số builds. Không tự bật flags chỉ xuất hiện ở các JDK mới và gọi đó là benchmark “Java 17”.

## 3. Viết SLO và giới hạn tài nguyên trước khi benchmark

Một mẫu **giả định cho dịch vụ Java 17**:

| Điều kiện | Ví dụ giới hạn |
| --- | --- |
| Request loại A | Cùng request mix/response payload, cùng dữ liệu và cache state |
| Offered load | 3.000 requests/giây ổn định trong một cửa sổ đo |
| Success rate | Ít nhất 99,9%; timeout/error vẫn được tính |
| p99 end-to-end latency | Không quá 80 ms tại điểm đo client |
| p99.9 | Không quá 150 ms |
| Peak container memory | Không quá 800 MiB |
| CPU quota | Tối đa 2 vCPU, cùng cấu hình CPU/CPU affinity |
| JVM maximum heap | 512 MiB cho lượt so sánh cùng heap |
| Test duration | Warm-up + nhiều cửa sổ steady-state, tối thiểu đủ samples |
| Kết luận | Chỉ ứng viên **đạt tất cả điều kiện** mới vào vòng tối ưu hóa trade-off |

**Các số trên chỉ để minh họa cách định nghĩa bài toán**, không phải lời khuyên cấu hình chung cho production. Đối với batch job, throughput/deadline có thể quan trọng hơn p99 request; đối với trading hoặc real-time interaction, tail latency có thể quan trọng hơn throughput.

### SLO là ngưỡng quyết định, không phải mục tiêu GC riêng lẻ

Nếu target request p99 ≤ 80 ms, một GC pause 100 ms đôi khi vẫn không làm *mọi* request vi phạm, nhưng nó là rủi ro lớn. Cũng có thể GC p99 5 ms mà request p99 200 ms do DB/lock/CPU. Vì vậy thiết lập:

1. **Primary success gate:** correctness, error rate, request p99/p99.9 ở offered load.
2. **Resource gate:** peak RSS/cgroup, CPU throttling, native memory và OOM status.
3. **Supporting diagnostics:** GC pause distribution, safepoint times, allocation rate.
4. **Tiebreaker:** throughput, CPU cost, footprint, ổn định và độ đơn giản vận hành.

Không nên xếp hạng chỉ bằng `-XX:MaxGCPauseMillis` hay bằng max pause trong log GC.

## 4. Cố định các biến để so sánh công bằng

### 4.1. Cùng workload, dữ liệu và concurrency

- Cùng application binary, dependency versions, JVM bytecode target và feature flags.
- Cùng request types, tỷ lệ GET/POST hoặc compute/IO, payload sizes, database fixtures và dữ liệu ngẫu nhiên có seed cố định.
- Cùng offered arrival rate hoặc cùng workload closed-loop được mô tả rõ, cùng độ dài chạy và cửa sổ đo.
- Cùng số workers/concurrent connections khi thuộc bài toán; tránh việc một test vô tình dùng 2 threads còn test khác dùng 200.
- Cùng cache warm state hoặc cùng quy trình prefill/reset; không so cache nóng với cache lạnh.
- Cùng tác nhân bên ngoài: DB connection limit, downstream latency, network, TLS, disk, log level và tracing sampling.
- Không đổi logic nghiệp vụ hoặc kích thước objects giữa hai lượt chỉ để GC này trông tốt hơn.

Đối với workload phân bổ object, ghi rõ **bytes allocated mỗi operation**, live-set size, age/lifetime distribution và % objects được giữ qua nhiều collection cycles. Một vòng lặp chỉ tạo mảng rồi bỏ là **allocation stress test**, không đại diện cho mọi service.

### 4.2. Cùng ngân sách CPU và bộ nhớ

Giữ cố định CPU quota/cpuset, container memory limit, OS/JDK build và heap policy. **CPU quota thực sự** phải do OS/container áp đặt; `-XX:ActiveProcessorCount=2` chỉ ảnh hưởng nhận thức của HotSpot về số processor, **không tự áp đặt quota OS**.

| Resource | Cần giữ/ghi nhận | Tại sao |
| --- | --- | --- |
| OS CPU quota & CPU affinity | Cùng vCPU/quota, host load, không noisy neighbors quá khác | GC parallel/concurrent threads chiếm CPU như business threads |
| Container memory limit | Cùng giới hạn tổng | Heap bằng nhau nhưng native footprint khác nhau |
| `-Xms`, `-Xmx` | Cố định trong thí nghiệm equal-heap | Kích thước heap ảnh hưởng frequency và GC cost |
| Direct/native memory | Giới hạn và đo, ví dụ `MaxDirectMemorySize` nếu dùng NIO | Tổng RSS không chỉ là Java heap |
| GC/JIT worker ergonomics | Ghi số threads thực và flags được suy ra | Collector chọn parallelism khác nhau |
| Process restart | JVM process mới cho từng repetition | Tránh code cache/heap và trạng thái từ lượt trước |
| GC logs & JFR | Cùng levels/settings giữa candidates | Instrumentation overhead có thể bias kết quả |

### Hai chế độ so sánh đều có giá trị nhưng phải tách

**A. Equal-heap benchmark:** đặt cùng `-Xmx` và `-Xms`, cùng container CPU/memory. Nó trả lời “với heap cùng kích thước, collector nào hoạt động ra sao?”. Nếu collector cần headroom native lớn hơn, kết quả có thể OOM ở tổng budget và đó là thông tin quan trọng.

**B. Equal-total-memory-budget benchmark:** áp dụng cùng memory cap của container/process, cho phép **điều chỉnh heap hợp lệ** riêng cho mỗi collector sao cho đều dưới cap. Nó trả lời “trong cùng giới hạn tổng tài nguyên, cấu hình collector nào đem lại SLO/throughput tốt nhất?”.

**Không trộn** kết quả một ứng viên được cấp 4 GiB heap và ứng viên khác chỉ có 512 MiB rồi kết luận bản chất collector tốt hơn. Nếu tối ưu heap riêng cho mỗi collector, công bố **heap của từng cấu hình** và so dưới ngân sách tổng giống nhau.

### 4.3. Phiên bản và flags

Ghi `java -version` và `java -XX:+PrintFlagsFinal -version` nếu cần tìm effective flags. JDK 17.0.x build khác JDK 21/24; đặc biệt GC/JIT đã tiến hóa nên không gộp kết quả thành “so sánh GC Java” phi thời gian.

Với thí nghiệm initial baseline, **không ép một knob collector-specific cho tất cả collectors**. Ví dụ `-XX:MaxGCPauseMillis=50` là tuning target liên quan G1/collector hỗ trợ; không có nghĩa mọi collector diễn giải flag như nhau. Chạy defaults trước, sau đó tuning riêng trong **vòng thứ hai** có ghi rõ mục đích và chi phí.

## 5. Quy trình chạy A/B có tính lặp lại

1. **Định nghĩa target SLO và resource caps.** Chốt offered-load levels, latency percentiles, error budget, peak RSS, CPU/throttling, startup/steady-state duration.
2. **Đóng băng môi trường:** JDK build, host/kernel, image, binary, network, DB snapshots, log/JFR settings, time source.
3. **Smoke test mọi candidate:** JVM có hỗ trợ collector không, startup thành công không, cùng chức năng/correctness không.
4. **Warm-up** đến khi JIT/code cache/connection pools/caches tương đối ổn; loại riêng thời gian warm-up hoặc đo startup bằng bài test khác.
5. **Chạy steady-state** ở cùng offered rate; theo dõi achieved throughput, errors/timeouts và dropped requests.
6. **Lấy GC/JFR/OS metrics** song song với client latency histograms.
7. **Lặp độc lập** (ví dụ ít nhất 5 lần) với JVM process mới. Trộn thứ tự như G1→Parallel→ZGC→Serial rồi đảo thứ tự ở round kế tiếp để giảm bias host temperature/noisy neighbor.
8. **Đánh giá nhiều tải:** below target, target, gần saturation và overload nhẹ; xác định điểm gãy và failure mode.
9. **Áp SLO gates**, chỉ so trade-off giữa candidates hợp lệ; kiểm tra outliers và confidence intervals.
10. **Kiểm chứng production-like:** long soak, memory footprint, collector instability, rare Full GC, p99.9/timeout và deployment behavior.

**Không dùng một run ngắn để kết luận** rằng collector thắng 10% throughput hoặc p99 đẹp hơn. Nếu khoảng biến động giữa các lượt lớn hơn chênh lệch, chưa đủ bằng chứng chọn phương án.

### Startup benchmark khác steady-state benchmark

Một collector có overhead startup/class loading khác collector kia; warm-up JIT và heap occupancy ban đầu cũng ảnh hưởng. Nếu startup latency là mục tiêu, tạo **bài test cold start riêng** không loại warm-up. Nếu mục tiêu là p99 khi phục vụ ổn định, **loại warm-up** và đo thời gian đủ lâu. Đừng cùng lúc tối ưu startup và steady state nhưng chỉ công bố một số tổng.

## 6. Closed-loop, open-loop và coordinated omission

### Closed-loop generator

~~~text
Client sends request
       |
       v
Wait for response
       |
       v
Send next request
~~~

Khi server chậm, client cũng gửi requests chậm hơn. **Offered load tự giảm**, có thể che mất queueing và latency ở giai đoạn server quá tải. Closed-loop phù hợp khi chính workload thực cũng theo mô hình synchronous closed-loop, nhưng không thay thế open-loop khi muốn kiểm tra service capacity ở fixed arrival rate.

### Open-loop / rate-controlled generator

~~~text
Clock sends requests at target timestamps
   t=0ms, 1ms, 2ms, ...
       |
       +--> nếu server còn đang xử lý, requests có thể queue
       |
       +--> đo completed, failed, timed-out và dropped
~~~

Để so GC khi mục tiêu 3.000 req/s, cần load generator có thể phát tới target rate **ngay cả khi response chậm**, với giới hạn queue và error handling rõ. Nếu generator không đủ CPU hoặc network, offered-rate kiểm soát bị phá; phải đo cả tài nguyên **load generator**.

**Coordinated omission:** khi tool chỉ ghi nhận latency của request thực sự gửi/hoàn thành mà bỏ qua những request lẽ ra phải đến theo lịch trong lúc server tạm dừng, histogram có thể **đánh giá thấp tail latency**. Dùng scheduler dựa trên arrival timestamps hoặc cơ chế histogram correction phù hợp workload và ghi rõ cách tính. Không âm thầm loại bỏ timeouts/failed requests khỏi p99 khiến một collector “nhanh” vì nó đánh rơi requests.

### Throughput delivered khác offered load

Ghi đồng thời:

- `offered_requests_per_second`
- `completed_success_per_second`
- `failed_requests_per_second`
- `timeouts_and_dropped_per_second`
- `in_flight`, queue depth hoặc backlog.

Một collector xử lý 2.500 req/s trong thí nghiệm offered 3.000 req/s là **không đạt cùng yêu cầu tải**, ngay cả nếu p99 trên những request thành công có vẻ thấp.

## 7. Các latency percentiles cần đo đúng cách

Với `N` latency samples được sắp tăng dần, một cách trình bày minh họa là **nearest-rank percentile**: p99 ở vị trí `ceil(0.99 × N)` tính từ 1. Các công cụ có thể chọn interpolation hoặc histogram HDR, nên khi so số liệu giữa tool khác nhau phải thống nhất định nghĩa.

| Metric | Cho biết |
| --- | --- |
| p50 | Request điển hình ở giữa distribution |
| p95 | 95% requests dưới hoặc bằng ngưỡng theo method percentile |
| p99 | Tail latency; với 10.000 mẫu, xét vùng 1% chậm |
| p99.9 | Tail rất hiếm; cần đủ samples để ổn định |
| Max | Sự kiện tệ nhất trong một tập sample cụ thể |
| Latency histogram | Phân bố đầy đủ, tránh trung bình che outlier |
| Throughput/success/errors | Thực sự phục vụ được tải theo yêu cầu hay không |

**Giá trị p99 trên tập 100 samples không đáng tin như p99 trên hàng trăm nghìn samples** nếu workload có những spikes hiếm. Cần đủ samples mỗi repetition và nhiều repetitions độc lập.

**Định nghĩa timestamp:** từ client send đến receive (client-side), từ server accept đến response (server-side), hay chỉ handler execution? Không dùng lẫn loại measurement. GC ảnh hưởng nhiều nơi trên critical path, còn client-side latency thường phản ánh trải nghiệm đầy đủ hơn (kèm network).

## 8. Benchmark Java 17 thực hành: cùng synthetic allocation workload

Chương trình này minh họa **workload cố định, collector đổi bằng JVM flag, đo throughput và latency distribution**. Nó **không phải** load generator open-loop, không đại diện cho HTTP server, và **không đủ** để tuyên bố collector nào tối ưu production. Ưu điểm: source đơn giản, payload/count cố định, kết quả một phần xác định, dùng để luyện thu thập GC logs và so sánh có kỷ luật.

Tạo file **`CollectorLoadLab.java`**:

~~~java
import java.util.Arrays;
import java.util.Locale;

public final class CollectorLoadLab {
    private static volatile long observed;

    static long percentile(long[] sorted, double q) {
        int rank = Math.max(1, (int) Math.ceil(q * sorted.length));
        return sorted[Math.min(sorted.length - 1, rank - 1)];
    }

    public static void main(String[] args) {
        final int warmup = 3000;
        final int measured = 12000;
        final int payloadBytes = 48 * 1024;
        final byte[][] retained = new byte[16][];
        final long[] latencyNs = new long[measured];
        long checksum = 0L;

        long measuredStart = 0L;
        for (int i = 0; i < warmup + measured; i++) {
            if (i == warmup) measuredStart = System.nanoTime();
            long opStart = System.nanoTime();

            byte[] payload = new byte[payloadBytes];
            payload[0] = (byte) i;
            payload[payloadBytes - 1] = (byte) (i >>> 8);
            retained[i % retained.length] = payload;
            checksum += payload[0] & 0xff;

            if (i >= warmup) {
                latencyNs[i - warmup] = System.nanoTime() - opStart;
            }
        }

        long elapsedNs = System.nanoTime() - measuredStart;
        observed = checksum;
        Arrays.sort(latencyNs);

        System.out.println("warmup=" + warmup);
        System.out.println("measured=" + measured);
        System.out.println("payloadKiB=" + payloadBytes / 1024);
        System.out.printf(Locale.ROOT, "allocatedMiB=%.1f%n",
                (warmup + measured) * (double) payloadBytes
                        / (1024 * 1024));
        System.out.printf(Locale.ROOT, "throughputOpsPerSecond=%.1f%n",
                measured * 1_000_000_000.0 / elapsedNs);
        System.out.printf(Locale.ROOT, "p50Us=%.3f%n",
                percentile(latencyNs, 0.50) / 1000.0);
        System.out.printf(Locale.ROOT, "p99Us=%.3f%n",
                percentile(latencyNs, 0.99) / 1000.0);
        System.out.println("checksum=" + observed);
        java.lang.ref.Reference.reachabilityFence(retained);
    }
}
~~~

### 8.1. Biên dịch

~~~bash
javac --release 17 CollectorLoadLab.java
~~~

### 8.2. Chạy từng collector với cùng heap

~~~bash
java -Xms128m -Xmx128m -XX:+UseSerialGC CollectorLoadLab
java -Xms128m -Xmx128m -XX:+UseParallelGC CollectorLoadLab
java -Xms128m -Xmx128m -XX:+UseG1GC CollectorLoadLab
java -Xms128m -Xmx128m -XX:+UseZGC CollectorLoadLab
~~~

**ZGC cần được hỗ trợ trên JDK/OS đang sử dụng**; nếu option bị VM từ chối, đánh dấu **UNSUPPORTED** và không tự coi việc không chạy là kết quả hiệu năng. Tương tự với Shenandoah, chỉ chạy khi JDK distribution xác nhận có collector đó.

### 8.3. Phần stdout bất biến và phần biến thiên

Những dòng từ logic mô tả workload cố định:

~~~text
warmup=3000
measured=12000
payloadKiB=48
allocatedMiB=703.1
~~~

Sau đó là:

~~~text
throughputOpsPerSecond=<thay đổi theo JVM/máy/lần chạy>
p50Us=<thay đổi theo JVM/máy/lần chạy>
p99Us=<thay đổi theo JVM/máy/lần chạy>
checksum=1904596
~~~

Phần `<...>` là **mô tả output biến thiên**, **không phải stdout nguyên văn** của lần chạy. Mã đã được biên dịch với `javac --release 17` và chạy thực tế trên JDK 24 với G1 và Serial GC. Trong **một lần đo cục bộ**, G1 có throughput khoảng 316.637 ops/s, Serial khoảng 430.597 ops/s; **không được biến hai số ngẫu nhiên này thành kết luận collector**. Thời gian quá ngắn, chỉ một thread, workload cực đơn giản, VM build không phải JDK 17 runtime.

**Kiểm tra tính đúng:** tổng allocation lũy kế là 15.000 × 48 KiB = 703,125 MiB (in một chữ số thập phân là 703.1). Mảng `retained` có 16 slots nên không giữ đồng thời lượng bytes ấy. `checksum` chống bỏ hoàn toàn kết quả tính toán và cho thấy cùng logic dữ liệu giữa các lần chạy; nó không chứng minh JIT không tối ưu mọi chi tiết hay benchmark đã đại diện production.

### 8.4. Giới hạn của chương trình thử nghiệm

- Benchmark này là **single-thread closed-loop**: vòng lặp sau chỉ bắt đầu sau vòng hiện tại.
- `System.nanoTime()` tự có overhead; những operations rất nhanh dễ bị nhiễu bởi resolution/scheduling.
- 12.000 measured iterations có thể quá ít cho p99.9 hoặc rare GC events.
- 128 MiB heap và 48 KiB arrays không đại diện cho live sets lớn, object graphs đa dạng hoặc real server.
- JIT compilation, tiered compilation và GC ergonomics có thể chưa ổn định.
- CPU quota/container memory nếu không áp bằng OS thì chỉ `-Xmx` không bảo đảm fairness về process resources.
- Để nghiêm túc đo microbenchmark, nên dùng JMH phù hợp và cấu hình forks/warm-up/measurement; nhưng JMH cũng không thay thế fixed-arrival server load tests.
- GC work có thể xảy ra giữa nhiều operations; p99 synthetic allocation không tương đương p99 API request.

Bài lab phù hợp để **luyện dụng cụ quan sát và so output**, không dùng làm bảng xếp hạng chính thức Serial vs G1.

## 9. Thu GC logs và JFR với cùng cấu hình

Bật HotSpot Unified Logging khi chạy từng collector, ghi file **khác nhau** tránh ghi đè. Ví dụ G1:

~~~bash
java -Xms128m -Xmx128m -XX:+UseG1GC \
  '-Xlog:gc=info,safepoint=info:file=g1-gc.log:uptime,level,tags' \
  CollectorLoadLab
~~~

Dấu `\` nối dòng dùng cho Bash/Linux/macOS. Trên PowerShell:

~~~powershell
java -Xms128m -Xmx128m -XX:+UseG1GC '-Xlog:gc=info,safepoint=info:file=g1-gc.log:uptime,level,tags' CollectorLoadLab
~~~

Chạy Serial với cùng options trừ GC choice và **filename**:

~~~bash
java -Xms128m -Xmx128m -XX:+UseSerialGC \
  '-Xlog:gc=info,safepoint=info:file=serial-gc.log:uptime,level,tags' \
  CollectorLoadLab
~~~

Cần so:

1. GC count và types (`Young`, `Mixed`, `Full`, concurrent cycle events) theo collector.
2. GC pause durations: count, max, histogram và percentiles.
3. Safepoint reaching/at/leaving/total: **không mặc nhiên bằng GC pause elapsed**.
4. Allocation throughput (bytes/s), live set, heap occupancy và old-gen pressure.
5. JVM process CPU time + OS CPU usage, container throttling.
6. Peak RSS/cgroup memory và native memory.
7. Application throughput, p99/p99.9 latency, errors/timeouts dưới same offered load.

**Phân biệt wall-clock và CPU time:** GC workers chạy song song có thể dùng tổng CPU time lớn hơn elapsed pause. Concurrent GC có thể tốn CPU ngoài các STW pauses, nên chỉ tổng STW không phản ánh toàn bộ cost.

### Java Flight Recorder

Trên JDK 17+ có JFR, có thể ghi recording profile (tên và cài đặt events tùy JDK):

~~~bash
java '-XX:StartFlightRecording=filename=gc-lab.jfr,settings=profile' \
  -Xms128m -Xmx128m -XX:+UseG1GC CollectorLoadLab
~~~

Dùng các file JFR riêng cho từng collector/run; công cụ JDK cho phép:

~~~bash
jfr summary gc-lab.jfr
jfr print --events jdk.GarbageCollection,jdk.GCPhasePause gc-lab.jfr
~~~

Một chương trình lab chạy quá nhanh có thể không đủ events để kết luận; cần tăng độ dài workload **như nhau cho mọi ứng viên** hoặc dùng server load test dài hơn. Recording/JFR có overhead; nếu dùng, bật settings tương đương cho tất cả ứng viên.

### Lưu ý với HotSpot `-Xlog` tags

Tags/format và mức độ chi tiết log phụ thuộc bản JVM. Dùng:

~~~bash
java -Xlog:help
~~~

Đối với service cần bền log, quản lý file rotation, output volume và phân quyền log. Không bật một collector ở log `trace` còn collector khác ở `info` rồi so performance như môi trường bằng nhau.

## 10. Resource fairness: CPU quota khác ActiveProcessorCount

HotSpot có tùy chọn `-XX:ActiveProcessorCount=N` ảnh hưởng cách JVM tính số CPU để chọn một số worker/ergonomics. Nó **không phải OS CPU quota**.

Ví dụ hai process đều chạy với `-XX:ActiveProcessorCount=2`, nhưng một process được container cấp 2 vCPU và process còn lại được cấp 8 vCPU thực tế: đây **không phải môi trường tài nguyên tương đương**. GC workers, Java threads và OS scheduling vẫn chịu giới hạn bên ngoài.

Trong hệ container, hãy ghi:

- cgroup CPU quota/period và cpuset; mức CPU throttling.
- memory.max (hoặc cgroup equivalent), memory.current/peak, OOMKilled events.
- Host CPU contention và NUMA/pinning nếu có.
- JVM effective heap sizes và GC/JIT thread counts.
- Thư viện native/DirectByteBuffer cùng quota nếu workload sử dụng.

**Memory cap bằng nhau** không đồng nghĩa **heap cap bằng nhau đã tối ưu**. Collector concurrent có thể cần headroom để vừa cấp phát cho mutators vừa thu hồi trong background. Nếu buộc `-Xmx` quá thấp và một collector OOM, đó là kết quả hợp lệ của equal-heap scenario nhưng nên thử thêm equal-total-budget tuned scenario trước khi kết luận về suitability.

## 11. Tại sao chỉ xem `-Xmx` là sai?

Tổng memory footprint của JVM process còn có:

~~~text
Java heap
+ native direct buffers / mapped files
+ metaspace / class metadata
+ JIT code cache
+ native thread stacks
+ GC bookkeeping và collector structures
+ JNI/JNA/native library allocations
+ OS memory mappings và allocator overhead
~~~

Không nhất thiết cộng chính xác các dashboard numbers thành RSS vì có khác biệt giữa **reserved**, **committed** và **resident** memory cùng khả năng double-count shared pages.

Cặp ví dụ:

- G1 có p99 tốt dưới 512 MiB heap và container 800 MiB.
- ZGC có p99 GC pauses rất thấp nhưng vượt memory budget do workload/collector/native overhead trong cùng giới hạn.

Trong bài toán có **hard memory cap**, ứng viên vượt cap là **FAIL** dù pause đẹp. Nhưng hãy xác minh cap thực sự enforced và OOM do yếu tố nào, không quy mọi OOM cho collector implementation.

## 12. So sánh bằng một scorecard có ngưỡng loại

Dưới đây là dữ liệu **GIẢ LẬP để luyện cách ra quyết định**, tuyệt đối không phải benchmark kết quả của JDK 17:

| Collector | Throughput (req/s) | p99 client (ms) | Peak memory (MiB) | Kết luận theo ví dụ |
| --- | ---: | ---: | ---: | --- |
| Serial | 3.400 | 180 | 530 | FAIL: p99 |
| Parallel | 3.900 | 115 | 630 | FAIL: p99 |
| G1 | 3.600 | 68 | 730 | PASS |
| ZGC | 3.350 | 24 | 920 | FAIL: peak memory |

**SLO giả định:** throughput ≥ 3.000 req/s, p99 ≤ 80 ms, peak memory ≤ 800 MiB, error rate dưới giới hạn.

Theo bảng mô phỏng, G1 là **ứng viên duy nhất đạt đủ ba cổng**. Chọn Serial vì ít memory nhất sẽ vi phạm p99; chọn ZGC chỉ vì p99 đẹp nhất sẽ vi phạm memory cap. Nếu điều chỉnh memory cap thành 1.024 MiB, ZGC cũng pass; lúc ấy cần xem p99.9, CPU budget, throughput và chi phí vận hành để chọn.

**Không tạo một “GC tổng điểm 8.4/10” vô căn cứ** bằng cách cộng các metric khác đơn vị. Đặt điều kiện loại trước, sau đó xét Pareto trade-offs theo business priority.

### Pareto frontier

Một phương án **Pareto-dominated** nếu phương án khác ít nhất tốt bằng ở mọi metric ưu tiên, tốt hơn ở ít nhất một metric và vẫn cùng tài nguyên/độ tin cậy. Nhưng throughput, latency và memory có hướng tối ưu khác nhau; thường tồn tại nhiều điểm **không có phương án nào áp đảo**. Khi đó quyết định phụ thuộc SLO/chi phí, không phải có collector “thắng tuyệt đối”.

## 13. Phân tích biến động và độ tin cậy

Khi chênh lệch p99 giữa G1 và ZGC chỉ 3% mà mỗi lần chạy dao động 10%, không thể tuyên bố ZGC đã thắng chắc chắn. Cần:

- Nhiều process runs độc lập và randomized order.
- Median của per-run metrics, min/max hoặc confidence intervals phù hợp.
- Thời gian warm-up được định nghĩa, dài đủ để code cache/JIT và heap occupancy ổn định.
- Sample size lớn để có p99.9 có ý nghĩa.
- Kiểm tra mối quan hệ throughput và offered load, không bỏ requests thất bại.
- Quan sát long-tail events: rare full GC, OS noise, background compaction, CPU throttling, OOM pressure.
- Đảm bảo recording/logging settings giống nhau.

**Cẩn thận percentile aggregation:** trung bình cộng p99 của 5 chạy không bằng p99 của tất cả requests gộp từ 5 chạy, nhất là khi số requests mỗi run khác. Nếu gộp histograms, cần đảm bảo bins, time windows và sample weights tương thích; hoặc báo per-run percentiles cùng phân bố confidence thay vì một số “p99 trung bình” không giải thích.

## 14. Tình huống benchmark bị sai và cách khắc phục

### 14.1. Collector A xử lý 3.000 req/s, collector B chỉ 2.200 req/s

Nếu target 3.000 req/s và offered load giống nhau, B không đạt throughput yêu cầu. p99 của B trên 2.200 completed requests có thể bị đẹp giả do timeouts bị loại. Ghi failures và offered-vs-completed; không công nhận B vượt SLO.

### 14.2. Dùng throughput benchmark single-thread rồi kết luận p99 service

Một thread chạy cấp phát mảng nhanh không đo thread pool, request queueing, DB latency, object graphs thật hoặc CPU contention của concurrent GC. Dùng lab này làm exercise; kết luận vận hành cần **production-like workload**.

### 14.3. GC pause p99 tốt, request p99 xấu

Có thể là concurrent GC tranh CPU, allocations gây memory bandwidth pressure, CPU throttling, blocking locks hoặc downstream I/O. So JFR CPU/thread events và tracing của app. Không đồng nhất GC pause với toàn bộ latency.

### 14.4. Chạy trên máy chung với nhiều tiến trình lạ

Host load và thermal/CPU frequency scaling thay đổi có thể lấn át chênh lệch nhỏ. Nên dùng isolated worker/node hoặc đo/ghi rõ noisy neighbors; randomized run order giúp giảm bias nhưng không thay được môi trường ổn định.

### 14.5. Cùng Xmx nhưng một collector OOM

Đó là thông tin về **equal-heap** test, song cũng có thể do collector cần extra headroom/native memory, startup settings hoặc load quá ngưỡng. Thử equal-total-memory tuning nếu ứng dụng cho phép; vẫn tính failure của mỗi scenario đúng cách.

### 14.6. Không cùng cache/JIT warm state

Ứng viên chạy sau có cache nóng từ DB/filesystem và nhanh hơn, dù GC không liên quan. Dùng reset/prefill giống nhau, cold-start test riêng và randomize order. `-Xms`/`-Xmx` khác nhau cũng ảnh hưởng heap commit/GC ergonomics.

### 14.7. Chỉ dùng GC logs đo performance

GC logs cho biết events liên quan GC, không đo toàn bộ request latency, correctness, queue backlog hoặc native memory. Phải có application-side instrumentation và OS metrics.

### 14.8. Dùng một flag tuning rồi kết luận collector tệ

Một collector có thể bị ép heap/pause goal không hợp workload. Baseline defaults để hiểu cost, sau đó tuning có kiểm soát, cùng ngân sách tài nguyên. Ghi rõ flag set và version khi công bố.

## 15. Một quy trình hai vòng thực dụng

### Vòng A — Baseline có kiểm soát

Giữ các biến:

~~~text
App binary:       y hệt
JDK build:        y hệt
Container CPU:    2 vCPU
Memory limit:     800 MiB
Heap:             Xms=Xmx=512 MiB
Workload:         request mix, dữ liệu, arrival rate giống nhau
Warm-up:          giống nhau
Measurement:      ví dụ 15 phút steady state
Logging/JFR:      cùng settings
Runs:             tối thiểu 5 lần mỗi collector
Thay đổi:         GC selection (mỗi run một collector)
~~~

Kết quả: hiểu collector nào đạt hoặc không đạt SLO ở cấu hình baseline.

### Vòng B — Tune riêng nhưng chung budget

Với ứng viên tiềm năng, được phép chỉnh heap và các collector-specific knobs **có ghi lại**, ví dụ thay G1 pause target hoặc ZGC memory headroom; vẫn giữ **2 vCPU/800 MiB/arrival rate/SLO** giống nhau. Nếu tăng heap của một collector, phải giảm thành phần khác hoặc vẫn nằm dưới cap. Chỉ tối ưu trên tập workload training, sau đó đánh giá lại trên workloads/periods độc lập để tránh overfit.

**Vì sao cần hai vòng?** Chỉ so equal-heap có thể chưa phản ánh “lựa chọn tốt nhất trong budget”; chỉ so tuned-final mà không có baseline dễ khiến những thủ thuật tuning không công bằng hoặc không tái lập.

## 16. Checklist trước khi công bố kết quả benchmark GC

- [ ] Đã ghi JVM vendor/build/version, GC option và effective flags.
- [ ] Cùng application binary, dataset, request mix, caches, warm-up.
- [ ] Cùng CPU quota/cpuset và container memory cap được OS thực thi.
- [ ] Có kịch bản equal-heap và, nếu cần, equal-total-memory-tuned riêng biệt.
- [ ] Offered load được đo và đạt target; errors, timeouts, dropped requests được tính.
- [ ] Thống nhất latency histogram method, p99/p99.9 sample size và timestamp scope.
- [ ] Ghi request throughput, correctness, SLO compliance; không chỉ GC pause.
- [ ] GC logs/JFR cùng settings và cùng time window của request metrics.
- [ ] Đo GC STW, safepoint, CPU usage, RSS và allocation rate.
- [ ] Có nhiều repeats với process mới và randomized order.
- [ ] Kiểm tra collector support và startup/compatibility, không bỏ qua unsupported runs.
- [ ] Kiểm tra OOMKilled/cgroup throttling và các failure modes.
- [ ] Đã phân biệt synthetic allocation lab với production-like end-to-end test.
- [ ] Những bảng minh họa được ghi rõ là giả lập, không coi là empirical results.
- [ ] Đã chọn kết luận bằng SLO/resource gates trước trade-off optimization.

## 17. Câu hỏi tự kiểm tra

1. Cùng 10.000 requests nhưng tốc độ phát request khác nhau có phải cùng tải không? **Không**, arrival rate khác có thể thay queueing/latency.
2. Collector có GC pause p99 thấp nhất có chắc làm HTTP p99 tốt nhất không? **Không**, còn CPU, I/O, locks, queueing và concurrent GC cost.
3. `-Xmx512m` có khống chế RSS process tối đa 512 MiB không? **Không**, còn native/JIT/thread/GC allocations.
4. `-XX:ActiveProcessorCount=2` có thực sự giới hạn container ở 2 vCPU không? **Không**, cần OS/cgroup quota.
5. Nếu benchmark closed-loop, server chậm có thể làm offered load giảm không? **Có**.
6. Coordinated omission làm p99 đo được thế nào? **Có thể bị thấp giả vì các request lẽ ra đến trong pause không được đo phù hợp**.
7. Có cần đếm failed/timeout requests không? **Có**, không được chỉ nhìn successful latency.
8. Equal-heap và equal-total-memory có là cùng một experiment không? **Không**, chúng trả lời câu hỏi khác nhau.
9. G1 pause target có hard-bound p99 request không? **Không**.
10. Concurrent GC có thể tiêu tốn CPU mà GC pause log rất ngắn không? **Có**.
11. GC CPU time có thể lớn hơn elapsed pause khi nhiều workers chạy song song không? **Có**.
12. Với 12000 measurements, có đủ để kết luận p99.9 ở production 10 triệu requests/ngày không? **Không**, còn tail rarity/representativeness và repetitions.
13. Nếu collector không có trên JDK build, có ghi benchmark 0 ops/s không? **Không**, phân loại unsupported và cân nhắc compatibility.
14. Khi một JVM chỉ chạy một process 200 ms đã đo hơn JVM khác 5%, có kết luận ngay không? **Không**, thời lượng/variance/JIT chưa phù hợp.
15. `allocatedMiB=703.1` trong lab có nghĩa `live set` là 703.1 MiB không? **Không**, đó là tổng allocation lũy kế.
16. Nếu collector B đạt p99 20 ms nhưng vượt memory cap, có pass SLO đầy đủ không? **Không**.
17. p99 của các lần chạy có được trung bình rồi xem là pooled p99 không? **Không**, cần histogram gộp đúng sample weighting hoặc báo per-run distributions.
18. Nếu gỡ GC logging cho ZGC nhưng bật debug logging cho G1, thí nghiệm có công bằng không? **Không**, overhead khác.
19. Nên chọn collector nào trước khi có dữ liệu? **Không tự xếp hạng chắc chắn; bắt đầu với default thích hợp, đo workload, SLO và budget thực**.
20. Trong scorecard giả lập mục 12, ứng viên nào đạt cả ba cổng? **G1**, bởi throughput, p99 và peak memory đều qua ngưỡng giả định.

## 18. Nguồn tài liệu chính thống

- Oracle Java SE 17, **Available Collectors** và hướng chọn collector: https://docs.oracle.com/en/java/javase/17/gctuning/available-collectors.html
- Oracle Java SE 17, **G1 Garbage Collector** và mục tiêu pause/throughput: https://docs.oracle.com/en/java/javase/17/gctuning/garbage-first-g1-garbage-collector1.html
- Oracle Java SE 17, **GC Tuning Guide**: https://docs.oracle.com/en/java/javase/17/gctuning/
- Oracle JDK 17, **`java` launcher options**, các flags GC/heap và JVM Unified Logging: https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html
- Oracle JDK 17, **`jfr`** command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html
- Oracle JDK 17, **`jcmd`** command: https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html
- Oracle Java SE 17, **Java Flight Recorder API/module**: https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/module-summary.html
- OpenJDK JMH project (dành cho benchmarking Java methods/micro-workloads): https://openjdk.org/projects/code-tools/jmh/

**Kết luận kỹ thuật:** So sánh collector phải bắt đầu từ **cùng workload và offered load, cùng CPU/memory budget, cùng JDK/binary và cùng mục tiêu end-to-end latency**. GC pause, GC CPU, safepoint total và request p99 là các chỉ số khác nhau. Dùng các ngưỡng **correctness, errors, throughput, p99/p99.9 và peak resource** để loại cấu hình không đáp ứng; chỉ sau đó cân nhắc hiệu suất, throughput, memory và vận hành. Đừng phong collector nhanh nhất từ một microbenchmark ngắn, một lần chạy hoặc chỉ từ GC pause log.
