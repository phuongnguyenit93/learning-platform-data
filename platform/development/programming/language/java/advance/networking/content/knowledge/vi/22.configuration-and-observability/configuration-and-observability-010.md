# Đánh giá hiệu năng bằng thông lượng, phân vị độ trễ, CPU và dung lượng bộ nhớ

## Mục tiêu bài học

Một dịch vụ Java networking có thể xử lý thử vài HTTP request rất nhanh nhưng chậm, lỗi hoặc hết bộ nhớ khi tải tăng. Để đánh giá đúng, cần xem **thông lượng (throughput)**, **phân vị độ trễ (latency percentiles)**, **mức sử dụng CPU** và **dung lượng bộ nhớ** trong **cùng cửa sổ đo**, kèm tỷ lệ thành công và điều kiện workload. Không đánh giá chất lượng chỉ bằng một con số requests/giây.

Sau bài này, bạn có thể:

- Định nghĩa rõ **offered load, completed throughput, successful throughput/goodput, bytes/giây, errors và timeouts**.
- Dùng `System.nanoTime()` đo elapsed time và phân biệt thời gian client end-to-end, server processing, queue wait và full response body.
- Tính **p50, p90, p95, p99, p99.9** từ raw observations theo **nearest-rank**, nhận ra sample-count bias và nguy cơ chỉ xem trung bình.
- Không lấy trung bình p95/p99 của nhiều server; biết dùng raw samples hoặc merge histograms/sketches.
- Hiểu **coordinated omission**, closed-loop so với open-loop load generator và Little's Law `L = λW`.
- Đo **CPU process time** bằng JDK MXBean, đổi thành core-equivalents và chuẩn hóa theo processors/quota.
- Phân biệt **heap used/committed/max**, off-heap/direct buffers, RSS/native memory, allocation rate, GC và memory leak.
- Thiết kế benchmark có warmup, thời gian đo đủ dài, cùng thông số môi trường, lặp nhiều lần, không vô tình benchmark load generator.
- Chạy hai chương trình Java 17+: ví dụ tính phân vị đầu vào cố định, và một HTTP mini benchmark có server/client thật trên loopback.
- Dùng **JFR**, `jcmd`, MXBeans, GC logs, profiler để tìm nguyên nhân khi p99, CPU hoặc RSS bất thường.

**Phạm vi:** Java 17+ và thư viện JDK tiêu chuẩn; ví dụ chạy trên `127.0.0.1`, không cần Internet. Một mini benchmark trên cùng JVM chỉ minh họa **cách đo**, không phải chứng nhận hiệu năng production.

## 1. Các chỉ số cùng mô tả một hệ thống

| Nhóm | Định nghĩa | Đơn vị | Câu hỏi cần làm rõ |
|---|---|---|---|
| **Throughput** | Số đơn vị công việc hoàn tất trong một khoảng thời gian | req/s, messages/s, operations/s | “Hoàn tất” có tính 4xx/5xx/timeout không? |
| **Goodput** | Số đơn vị **hữu ích, thành công** theo tiêu chuẩn hệ thống | success req/s, valid bytes/s | HTTP 200 nhưng body sai có tính thành công? |
| **Latency** | Thời gian từ điểm bắt đầu đến điểm hoàn tất đã định nghĩa | ms, µs | Đo client hay server, TTFB hay full body? |
| **p50/p95/p99** | Các mốc phân vị latency, nêu mức độ đuôi chậm | ms, µs | Bao nhiêu mẫu, dùng thuật toán percentile nào? |
| **CPU** | Thời gian xử lý CPU mà process/threads tiêu thụ | core equivalents, % CPU quota | Một core hay toàn bộ host? |
| **Memory** | Bộ nhớ JVM/process dùng hoặc đã cam kết | MiB/GiB, allocations/s | Heap, RSS hay direct buffers? |
| **GC** | Collection activity/pauses và chi phí dọn đối tượng | count, ms, pause distribution | GC có giải thích tail latency không? |

**Nguyên tắc quan sát:** cùng thời gian, cùng traffic mix, cùng latency boundary và cùng môi trường. Nếu RPS lấy từ sáng, p99 lấy ban đêm, CPU lấy trước deploy còn memory lấy sau GC thì các con số ấy **không tạo thành một bức tranh nhân quả**.

Với Java server, hãy lưu **run ID, JDK/GC, process PID, heap limit, CPU quota, phiên bản service, concurrency, payload và measurement interval** trước khi công bố kết quả.

## 2. Định nghĩa thông lượng không đánh lừa người đọc

Công thức cơ bản:

~~~text
completed_throughput_req_per_s =
    số HTTP attempts đã hoàn tất / thời gian đo tính bằng giây

successful_throughput_req_per_s =
    số HTTP attempts đạt tiêu chuẩn thành công / thời gian đo

error_rate =
    số requests lỗi / số requests hoàn tất hoặc attempts theo hợp đồng

body_transfer_bytes_per_s =
    tổng bytes body đã gửi/nhận / thời gian đo
~~~

Phải công bố **mẫu số**. Nếu một request bị time out nhưng đã kết thúc future exceptionally, trong ví dụ B nó được đếm là **completed attempt lỗi**. Trong một dashboard production, phân biệt additionally dropped/rejected requests chưa được đưa vào server.

Ví dụ một test có 1.000 attempts hoàn tất trong 2 giây:
- 900 thành công: **completed throughput 500 req/s**.
- **Successful throughput 450 req/s**.
- **Error rate 10%**.

Cả hai kết quả thông lượng đều có ý nghĩa; nhưng chỉ nhìn 500 RPS sẽ che chất lượng. Một service trả HTTP `503` rất nhanh có thể có completed RPS cao mà **goodput thấp**. `200` cũng chưa chắc thành công nếu body/schema nghiệp vụ không hợp lệ.

### Offered load và achieved throughput

- **Offered load**: tốc độ client *muốn* gửi request hoặc concurrency mục tiêu.
- **Achieved/completed throughput**: những requests đã hoàn tất ở measurement boundary.
- **Successful throughput**: số operations đã hoàn tất **đúng** mỗi giây.
- **Queue/backlog**: requests đang chờ connection pool, thread pool, upstream database hoặc server.

Tăng offered load không bảo đảm achieved throughput tăng mãi. Tại **điểm bão hòa**, RPS có thể chững/giảm, p99 tăng, timeout và rejects tăng. “Max RPS” ở vùng quá tải chưa chắc là mức vận hành an toàn có headroom.

### Đừng quên bytes/s

Một endpoint trả 5.000 response/s × 1.024-byte body = 5.120.000 body bytes/s, **chưa kể** HTTP headers, TLS records, TCP/IP framing, ACK và retries. Nếu chuyển sang payload 1 MiB, mạng/bộ nhớ có thể trở thành bottleneck dù RPS thấp hơn nhiều. Khi đo SocketChannel, DatagramChannel, WebSocket và HTTP, ghi **messages/s lẫn bytes/s** cùng kích thước phân phối message.

## 3. Chọn đúng ranh giới đo latency

Latency end-to-end ở phía client có thể bao gồm:

~~~text
start
  ├─ chờ client queue/connection pool
  ├─ DNS/TCP/TLS handshake khi cần
  ├─ gửi request bytes
  ├─ chờ server accept/queue
  ├─ server xử lý, gọi DB/upstream
  ├─ response đi qua network/proxy
  └─ đọc đủ body hoặc nhận result theo contract
end → latency = end - start
~~~

Các metric **không thay thế nhau**:
- **Server handler time**: chỉ đoạn xử lý trong handler.
- **Queue wait**: chờ worker/connection.
- **TTFB**: thời gian từ start đến byte response đầu tiên theo định nghĩa đo.
- **Full-response latency**: đến khi body đã được đọc/tiêu thụ hoàn chỉnh.
- **End-to-end client latency**: tùy loại client, có thể gồm DNS/connect/TLS, pool waits và callbacks.

Với HTTP streaming hoặc WebSocket sống nhiều phút, không nên coi thời gian toàn kết nối là “request latency”; dùng **message/event latency** theo protocol.

Trong Java:

~~~java
long start = System.nanoTime();
try {
    operation();
} finally {
    double milliseconds =
        (System.nanoTime() - start) / 1_000_000.0;
}
~~~

Đây là **snippet**, `operation()` là hàm giả định. `System.nanoTime()` phù hợp **đo durations**, không phải timestamp UTC. `System.currentTimeMillis()` là wall clock có thể bị điều chỉnh và kém thích hợp cho khoảng ngắn.

**HTTP body trap:** với `HttpResponse.BodyHandlers.ofInputStream()`, future có thể hoàn tất trước khi ứng dụng đọc hết stream. Nếu muốn đo full-body latency, đặt điểm kết thúc **sau khi stream được đọc/đóng theo protocol**, thay vì ngay khi có đối tượng `HttpResponse<InputStream>`. Ví dụ B dùng `ofByteArray()` nên full response body đã được nhận tại callback completion.

## 4. Mean, median và tail percentiles

Giả sử có 99 requests mất 10 ms và một request mất 2.000 ms:
- **Mean** = (99 × 10 + 2.000) / 100 = **29,9 ms**.
- **p50** = 10 ms.
- **p99 theo nearest-rank** = 10 ms.
- **Max** = 2.000 ms.

Ngay cả p99 với N=100 có thể chưa thể hiện single worst outlier; muốn thấy đuôi cực hiếm dùng p99.9/max và **nhiều mẫu**.

| Metric | Cách hiểu |
|---|---|
| p50 | Khoảng một nửa observations không lớn hơn mốc này |
| p90 | Khoảng 90% observations không lớn hơn mốc này |
| p95 | Bắt đầu quan sát nhóm 5% chậm nhất |
| p99 | Mốc tail của khoảng 1% chậm nhất |
| p99.9 | Đuôi hiếm, cần rất nhiều mẫu để ước lượng |
| mean | Trung bình cộng, nhạy với outlier |
| max | Mẫu chậm nhất **đã quan sát**, không phải worst case tương lai |

### Tính bằng nearest-rank

Với N observations sắp xếp tăng dần và percentile p trong khoảng (0,100]:

~~~text
rank = ceil((p / 100) * N)
percentile = sorted[rank - 1]
~~~

Trong ví dụ A có 100 observations: 1, 2, ..., 98, 600, 2.000 microseconds:
- p50 = 50 µs, p90 = 90 µs, p95 = 95 µs.
- p99 = 600 µs.
- p99.9 = 2.000 µs.
- Mean = 74,51 µs.

**Không có một định nghĩa percentile duy nhất ở mọi thư viện.** Một số công cụ nội suy quantiles, một số chọn nearest-rank hoặc approximate histogram. Khi so các dịch vụ, ghi rõ thuật toán/buckets và sample counts.

Nếu N=20, p99 nearest-rank là rank ceil(19,8)=20 → **max**. Nếu N=240, p99 là mẫu thứ **238** sau sort, tức số mẫu tail rất ít. Không công bố p99.9 từ vài trăm requests như một ước lượng chắc chắn.

## 5. Ví dụ A: percentile và throughput có stdout xác định

Chương trình dùng input **cố định** để kiểm tra công thức. Nó **không** benchmark CPU hay HTTP; đây là unit-test kiến thức về percentile.

Lưu file **`PercentileMathDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.Locale;

public class PercentileMathDemo {
    static long nearestRank(long[] observations, double percentile) {
        if (observations.length == 0
                || percentile <= 0.0 || percentile > 100.0) {
            throw new IllegalArgumentException("Invalid sample or percentile");
        }
        long[] sorted = observations.clone();
        Arrays.sort(sorted);
        int index = (int) Math.ceil(
            percentile / 100.0 * sorted.length) - 1;
        return sorted[index];
    }

    public static void main(String[] args) {
        long[] latencyUs = new long[100];
        for (int i = 0; i < 98; i++) {
            latencyUs[i] = i + 1;
        }
        latencyUs[98] = 600;
        latencyUs[99] = 2_000;
        long total = 0;
        for (long v : latencyUs) total += v;

        System.out.println("samples: " + latencyUs.length);
        System.out.printf(Locale.ROOT, "mean_us: %.2f%n",
            (double) total / latencyUs.length);
        for (double p : new double[] {50, 90, 95, 99, 99.9}) {
            System.out.printf(Locale.ROOT, "p%s_us: %d%n",
                (p == Math.rint(p)
                    ? Integer.toString((int) p) : "99.9"),
                nearestRank(latencyUs, p));
        }
        long completed = 900;
        long elapsedNanos = 1_500_000_000L;
        System.out.printf(Locale.ROOT, "throughput_req_per_s: %.2f%n",
            completed * 1e9 / elapsedNanos);
        System.out.printf(Locale.ROOT, "little_law_inflight: %.2f%n",
            600.0 * 0.025);
    }
}
~~~

Biên dịch/chạy JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 PercentileMathDemo.java
java PercentileMathDemo
~~~

**Stdout thực tế đã được kiểm thử:**

~~~text
samples: 100
mean_us: 74.51
p50_us: 50
p90_us: 90
p95_us: 95
p99_us: 600
p99.9_us: 2000
throughput_req_per_s: 600.00
little_law_inflight: 15.00
~~~

`900 requests / 1,5 seconds` và `L=600 × 0,025 = 15` chỉ là **dữ liệu giả định để minh họa**, không phải số đo khả năng máy. Code dùng `Locale.ROOT` để in dấu chấm thập phân nhất quán và clone array trước khi sort để không thay input.

### Vì sao không dùng average thay p99?

Dữ liệu có hai outliers 600 và 2.000 µs. Mean 74,51 µs có thể tạo ấn tượng request bình thường ~75 µs dù median chỉ 50 µs và một request mất 2.000 µs. Vì thế p50, p95, p99, max và rate timeout nên được xem cùng nhau.

## 6. Little's Law: liên hệ throughput, latency và concurrency

Trong hệ thống **ổn định**, Little's Law:

~~~text
L = λ × W
L: số công việc đang ở trong hệ thống trung bình
λ: throughput bình quân (requests/second)
W: average time in system (seconds)
~~~

Ví dụ 600 requests/s và **mean** end-to-end time 25 ms:

~~~text
L = 600 × 0.025 = 15 in-flight requests
~~~

**Đừng thay W bằng p99**. Little's Law cần **mean** và cùng system boundary. Khi queue đang tăng vô hạn, offered load khác completion throughput, requests bị drop hoặc retries phức tạp, công thức phải được dùng đúng tập công việc/giả định.

Concurrency tăng có thể cải thiện throughput trong khi nhiều requests đang chờ I/O. Nhưng nếu worker pool/CPU/DB đã bão hòa, tăng concurrency chủ yếu làm tăng queue wait, memory và p99 thay vì năng suất.

## 7. Vì sao không trung bình p95/p99 của nhiều server?

Percentile **không linear**. Ví dụ:
- Server A nhận 100 requests, tất cả mất 10 ms → p95(A)=10 ms.
- Server B nhận 1 request mất 1.000 ms → p95(B)=1.000 ms.
- Trung bình p95 hai server = (10+1.000)/2 = 505 ms.
- Nhưng trong 101 samples gộp, rank p95 = ceil(0,95×101)=96, mẫu thứ 96 là 10 ms → **p95 global = 10 ms**.

Không chỉ trung bình đơn giản, **weighted average p95** cũng không cho percentile global.

Cách đúng:
1. Gộp **raw observations** khi ít data và cho phép lưu.
2. Với traffic lớn, gộp **histogram bucket counts** có cùng bucket boundaries, rồi tính quantile từ histogram tổng.
3. Hoặc dùng sketch có khả năng merge và error bounds rõ (HDR Histogram, t-digest...) theo stack hiện có.
4. Không gộp metrics có boundary khác nhau: server processing latency không phải client full-response latency.

Cũng phải báo **sample count mỗi replica**, status/error distribution và window time; một pod nhận 100 req không được có cùng trọng số với pod nhận 10 triệu req chỉ vì mỗi pod có một con số p99.

## 8. Coordinated omission: một lỗi benchmark rất dễ mắc

Closed-loop test thường tạo request/batch, **chờ xong** rồi mới tạo request/batch tiếp theo. Khi server bị stall 2 giây, client cũng chờ; không có những requests mới đến trong thời gian đó. Nếu tải thực tế của sản phẩm **vẫn có requests đến đều**, kết quả closed-loop có thể làm tail latency trông đẹp hơn thực tế: đây là **coordinated omission**.

~~~text
Closed-loop:
send batch ───────── wait responses ───────── send next batch
server stalled → generator cũng dừng tạo request mới

Open-loop / scheduled arrivals:
0ms send ─ 10ms send ─ 20ms send ─ 30ms send ...
server stalled → queue, timeouts, rejects được ghi rõ
~~~

Open-loop đúng nghĩa không phải phát requests vô hạn: cần **rate cap, in-flight cap, queue cap, stop criteria và quyền kiểm thử** để không DoS. Nếu generator drop requests vì quá tải, phải đếm dropped events và định nghĩa latency của chúng theo reporting contract.

Ví dụ B bên dưới cố tình dùng **12 requests song song mỗi batch rồi chờ `allOf`**, nên là **closed-loop mini benchmark** và có giới hạn. Không dùng nó để chứng minh p99 production hay tải hở.

### Timeout không được biến mất khỏi thống kê

Nếu một request timeout 5s:
- Ghi **error/timeout count**.
- Có thể ghi termination-time latency của attempt, nhưng đó không phải thời gian trả response thành công.
- Nên báo **success-only latency histogram**, **all-attempt duration** và tỷ lệ errors riêng, hoặc một SLO tổng “hoàn thành thành công trong deadline”.
- Không bỏ toàn bộ failed requests rồi công bố một percentile có vẻ đẹp.

Vì timeout có thể là **censored observation** đối với thời gian response thực, không suy diễn server đã hoàn tất ngay khi client timeout.

## 9. CPU process time, cores và quota

Một request mất 100 ms wall time có thể chỉ thực dùng 8 ms CPU vì chờ network 92 ms. Ngược lại process chạy đa luồng có thể dùng nhiều cores trong một giây: tổng process CPU time **lớn hơn** wall time.

Java 17 cung cấp `com.sun.management.OperatingSystemMXBean.getProcessCpuTime()` (nanoseconds; nếu không hỗ trợ phải báo unavailable). Đo hai snapshot:

~~~text
cpuCoresAvg =
    (processCpuTimeAfter - processCpuTimeBefore)
    / (wallTimeAfter - wallTimeBefore)

processCpuPctOfVisible =
    100 * cpuCoresAvg / Runtime.getRuntime().availableProcessors()
~~~

Ví dụ 3 giây process CPU time trong 1 giây wall time → trung bình **3 core-equivalents**. Nếu JVM thấy 8 cores, đó khoảng **37,5% của 8 visible cores**, nhưng cần biết quota/cgroup thực trước khi so containers.

**Điểm dễ sai:**
- “CPU 100%” ở tool A có thể là **một logical core**; tool B có thể normalize 100% = **toàn process quota**.
- `availableProcessors()` phụ thuộc JDK/container/affinity, không nhất thiết là tổng CPU physical host.
- CPU sampling window quá ngắn dễ nhiễu do resolution của counter/JIT/GC/background processes.
- Nếu client và server cùng JVM (như demo), **process CPU bao gồm cả load generator lẫn server**, không thể tách server capacity.
- CPU thấp không chứng minh có nhiều headroom: có thể bottleneck I/O pool, lock contention, network throttle hoặc upstream.

### CPU profile khi bottleneck chưa rõ

`ThreadMXBean` (nếu supported) có thể đo CPU time per-thread. JFR CPU samples và profiler giúp biết CPU đang tốn ở serialization, TLS, JSON, GC, contention, selector callback, DB driver hay code application. Đừng thêm threads trước khi biết threads hiện có đang **RUNNABLE sử dụng CPU** hay **WAITING chờ I/O**.

## 10. Dung lượng bộ nhớ: heap, committed, RSS và native memory

Một JVM process sử dụng nhiều vùng bộ nhớ:

~~~text
RSS / resident process memory (OS)
├─ Java heap (objects và arrays)
│  ├─ used       : bytes đang dùng tại snapshot
│  ├─ committed  : JVM đã commit
│  └─ max        : trần heap theo JVM configuration
├─ Metaspace / class metadata
├─ JIT code cache
├─ Thread stacks / native threads
├─ Direct và mapped ByteBuffers
├─ Native runtime / TLS / JNI / libc allocations
└─ OS/JVM overhead khác
~~~

### Đọc đúng các chỉ số

| Metric | Quan sát | Không nên suy diễn |
|---|---|---|
| `MemoryMXBean.getHeapMemoryUsage().getUsed()` | Heap used tại snapshot | Không phải peak, không phải total RSS |
| `MemoryUsage.getCommitted()` | Heap memory đã commit | Không phải toàn bộ RAM system |
| `MemoryUsage.getMax()` hoặc `Runtime.maxMemory()` | Trần heap | Không nhất thiết bằng container RAM |
| `MemoryMXBean.getNonHeapMemoryUsage()` | Một phần memory ngoài heap | Không bao trùm mọi native allocations |
| `BufferPoolMXBean.getMemoryUsed()` | Memory của direct/mapped buffer pool theo JVM | Có thể trả -1 khi không hỗ trợ |
| RSS / cgroup memory | Bộ nhớ resident hoặc charged của process/container | Không đồng nhất với heap used |
| Allocation rate | Bytes objects cấp phát trên đơn vị thời gian | Heap used có thể vẫn ổn khi GC dọn thường xuyên |
| GC pauses | Các khoảng ngừng/phase xử lý GC theo collector | Không tự bằng toàn bộ latency |

**Một snapshot heap used tăng không chứng minh leak.** Cache, JIT/class loading, response byte arrays, retained futures hoặc GC chưa chạy có thể khiến heap tăng trong mini test. Tìm leak cần phân tích **live object retention** qua nhiều chu kỳ tải/GC, allocation profiles và heap dump khi được phép.

Ngược lại, một service dùng `SocketChannel` và `ByteBuffer.allocateDirect` có thể có **heap thấp nhưng RSS cao** vì direct buffers. Đừng chỉ nhìn `-Xmx` để đặt memory limit cho container; tính thêm native allocations, threads, metaspace và GC/JIT overhead.

### ByteBuffer trực tiếp

Ví dụ snippet quan sát buffer pool:

~~~java
for (BufferPoolMXBean pool : ManagementFactory.getPlatformMXBeans(
        BufferPoolMXBean.class)) {
    System.out.println(pool.getName() + ": "
        + pool.getMemoryUsed());
}
~~~

Cần import `java.lang.management.BufferPoolMXBean` và `java.lang.management.ManagementFactory`. `getMemoryUsed()` có thể trả -1; đừng diễn giải như số lượng bytes âm. Quan sát direct/mapped pool và OS RSS **cùng lúc** khi nghi native memory pressure.

### Đơn vị memory

- 1 MiB = **1.048.576 bytes**.
- 1 MB thập phân = **1.000.000 bytes**.
- Đừng so `heap_used_mib` với memory dashboard ghi MB mà không quy đổi.
- `Runtime.maxMemory()` trả bytes; một hệ thống không cần luôn dùng hết max heap.

## 11. GC và p99: cần xem cả CPU/allocations

Garbage collection ảnh hưởng performance bằng nhiều đường:
- Allocation rate cao khiến collector chạy thường xuyên hơn.
- Collector có các giai đoạn concurrent, có thể tốn CPU song song với application.
- Các stop-the-world pauses có thể tăng p99 một số requests.
- Heap quá nhỏ có thể tạo GC pressure; heap quá lớn tăng footprint và có trade-off khác tùy collector.

JDK `GarbageCollectorMXBean.getCollectionCount()` và `getCollectionTime()` là counters, có thể trả -1 khi không được hỗ trợ. **Collection time không luôn bằng tổng downtime** của concurrent GC; muốn xem pause distribution dùng JFR/GC unified logs.

Nếu demo in `gc_collections_delta: 0`, điều đó **chỉ có nghĩa counter không tăng trong measurement window**, không chứng minh chương trình không allocate, không chứng minh heap không cần GC hoặc không có native memory overhead.

Dùng timestamps cùng window để so p99 spikes với GC pause events, lock/queue/network events; trùng thời điểm chưa phải bằng chứng chắc chắn về quan hệ nhân quả.

## 12. Thiết kế benchmark có ý nghĩa cho networking

### Giữ cùng workload và môi trường

Ghi tối thiểu:
- JDK vendor/version, GC, `-Xms/-Xmx`, OS/kernel/CPU quota, RAM/cgroup.
- HTTP/1.1 vs HTTP/2, HTTPS/TLS, keep-alive, proxy, DNS/region.
- Request mix, method/path, body size, response size, validation semantics.
- Số clients/connections, concurrency, offered rate, queue/rate limits.
- Warmup, measurement duration, repeats, status/timeout criteria.
- Latency measurement boundary, percentile algorithm/histogram bucket policy.
- Sự khác nhau giữa server version/config A và B.

Nếu một lần đo HTTP không TLS trên localhost và lần khác đo HTTPS qua proxy, không thể quy sự khác biệt RPS đơn giản cho thuật toán Java.

### Warmup và steady state

Java có class loading, JIT compilation, connection setup và caches. Để đo **steady-state**, chạy warmup, sau đó tách measurement windows. Nếu muốn đo **cold start**, đó là một workload khác: phải đo lần request đầu **riêng** thay vì xóa warmup rồi tuyên bố không có cold-start problem.

Test production-like nên kéo dài đủ để quan sát cache eviction, nhiều GC cycles, tail latency, throttling, kết nối bị reset và queue buildup. Chạy nhiều lần để thấy variance, không chỉ chọn run nhanh nhất.

### Load generator cũng có giới hạn

Nếu client generator CPU 100% hoặc tạo connections quá chậm, server có thể có CPU thấp và RPS thấp dù **server còn dư năng lực**. Đo client và server **tách process/máy** để tránh nhiễu, đồng thời đo offered requests và generator drop/retry. Một JVM cùng chạy server và client như demo chỉ để học cách tạo metrics.

### Giới hạn an toàn

Load test chỉ nên chạy với hệ thống **bạn được phép kiểm thử**; giới hạn concurrency, ramp-up, timeout, network traffic và thời gian. Có kế hoạch dừng nếu lỗi/tài nguyên vượt mức, tránh vô tình DoS hoặc tăng chi phí cloud.

## 13. Ví dụ B: HTTP loopback + throughput, p50/p95/p99, CPU, heap và GC

Bài lab sau sử dụng **JDK 17**, không cần dependency ngoài:
- `HttpServer` trên `127.0.0.1:0`, route `GET /payload` trả **1.024 bytes**.
- Server executor 4 workers, client `HttpClient` preferred HTTP/1.1, dùng lại một instance.
- 30 requests warmup **không tính**.
- 240 requests đo, chia thành **20 batches × 12** requests đồng thời.
- Mỗi future ghi latency bằng `System.nanoTime()`; phân loại successful theo HTTP `200` và body đúng 1.024 bytes.
- Tổng measured wall duration dùng tính completed RPS.
- Process CPU time tính average core-equivalents và normalized process CPU percentage.
- Heap used before/after/max, GC collection counts được ghi bằng MXBeans.

**Giới hạn quan trọng:** đây là **closed-loop 12-in-flight mini benchmark** với client và server chạy **trong cùng process**; CPU process bao gồm cả hai; heap before/after không phải peak; p99 từ 240 samples rất thiếu chắc chắn. Số đo chỉ minh họa instrumentation, không chứng nhận SLO.

### 13.1. Source đầy đủ `LoopbackHttpBenchmarkDemo.java`

~~~java
import com.sun.management.OperatingSystemMXBean;
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.lang.management.GarbageCollectorMXBean;
import java.lang.management.ManagementFactory;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;

public class LoopbackHttpBenchmarkDemo {
    static final int REQUESTS = 240;
    static final int BATCH_SIZE = 12;
    static final int BODY_BYTES = 1_024;

    static long processCpuNanos() {
        var bean = ManagementFactory.getOperatingSystemMXBean();
        if (bean instanceof OperatingSystemMXBean mx) {
            return mx.getProcessCpuTime();
        }
        return -1;
    }

    static long heapUsedBytes() {
        return ManagementFactory.getMemoryMXBean()
            .getHeapMemoryUsage().getUsed();
    }

    static long gcCollections() {
        long count = 0;
        for (GarbageCollectorMXBean bean :
                ManagementFactory.getGarbageCollectorMXBeans()) {
            long value = bean.getCollectionCount();
            if (value < 0) return -1;
            count += value;
        }
        return count;
    }

    static double percentileMs(long[] latencyNanos, double percentile) {
        long[] sorted = latencyNanos.clone();
        Arrays.sort(sorted);
        int position = (int) Math.ceil(
            percentile / 100.0 * sorted.length) - 1;
        return sorted[position] / 1_000_000.0;
    }

    public static void main(String[] args) throws Exception {
        byte[] payload = new byte[BODY_BYTES];
        Arrays.fill(payload, (byte) 'A');
        ExecutorService serverThreads = Executors.newFixedThreadPool(4);
        HttpServer server = HttpServer.create(
            new InetSocketAddress(
                InetAddress.getByName("127.0.0.1"), 0), 0);
        server.setExecutor(serverThreads);
        server.createContext("/payload", exchange -> {
            try {
                if (!"GET".equals(exchange.getRequestMethod())) {
                    exchange.sendResponseHeaders(405, -1);
                    return;
                }
                exchange.getResponseHeaders().set(
                    "Content-Type", "application/octet-stream");
                exchange.sendResponseHeaders(200, payload.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(payload);
                }
            } finally {
                exchange.close();
            }
        });
        server.start();

        try {
            URI endpoint = URI.create("http://127.0.0.1:"
                + server.getAddress().getPort() + "/payload");
            HttpClient client = HttpClient.newBuilder()
                .version(HttpClient.Version.HTTP_1_1)
                .connectTimeout(Duration.ofSeconds(2))
                .build();
            HttpRequest request = HttpRequest.newBuilder(endpoint)
                .timeout(Duration.ofSeconds(5)).GET().build();

            // Warm up code paths and reusable HTTP connections; exclude samples.
            for (int i = 0; i < 30; i++) {
                HttpResponse<byte[]> response = client.send(
                    request, HttpResponse.BodyHandlers.ofByteArray());
                if (response.statusCode() != 200
                        || response.body().length != BODY_BYTES) {
                    throw new IllegalStateException("Warmup failed");
                }
            }

            long[] latencies = new long[REQUESTS];
            AtomicInteger successes = new AtomicInteger();
            AtomicInteger failures = new AtomicInteger();
            long heapBefore = heapUsedBytes();
            long gcBefore = gcCollections();
            long cpuBefore = processCpuNanos();
            long wallBefore = System.nanoTime();

            for (int offset = 0; offset < REQUESTS;
                    offset += BATCH_SIZE) {
                List<CompletableFuture<Void>> batch = new ArrayList<>();
                for (int i = offset; i < Math.min(
                        offset + BATCH_SIZE, REQUESTS); i++) {
                    final int index = i;
                    long started = System.nanoTime();
                    CompletableFuture<Void> done = client.sendAsync(
                        request, HttpResponse.BodyHandlers.ofByteArray())
                        .handle((response, error) -> {
                            latencies[index] =
                                System.nanoTime() - started;
                            if (error == null
                                    && response.statusCode() == 200
                                    && response.body().length == BODY_BYTES) {
                                successes.incrementAndGet();
                            } else {
                                failures.incrementAndGet();
                            }
                            return (Void) null;
                        });
                    batch.add(done);
                }
                CompletableFuture.allOf(
                    batch.toArray(new CompletableFuture<?>[0])).join();
            }

            long wallAfter = System.nanoTime();
            long cpuAfter = processCpuNanos();
            long gcAfter = gcCollections();
            long heapAfter = heapUsedBytes();
            int completed = successes.get() + failures.get();
            double seconds = (wallAfter - wallBefore) / 1e9;
            double throughput = completed / seconds;

            System.out.println("requests_completed: " + completed);
            System.out.println("successes: " + successes.get());
            System.out.println("failures: " + failures.get());
            System.out.printf(Locale.ROOT,
                "throughput_req_per_s: %.2f%n", throughput);
            System.out.printf(Locale.ROOT,
                "latency_ms p50=%.3f p95=%.3f p99=%.3f%n",
                percentileMs(latencies, 50),
                percentileMs(latencies, 95),
                percentileMs(latencies, 99));
            if (cpuBefore >= 0 && cpuAfter >= cpuBefore) {
                double cpuCores =
                    (cpuAfter - cpuBefore) / (double) (wallAfter - wallBefore);
                int visibleCpus = Runtime.getRuntime().availableProcessors();
                System.out.printf(Locale.ROOT,
                    "process_cpu_cores_avg: %.3f%n", cpuCores);
                System.out.printf(Locale.ROOT,
                    "process_cpu_pct_visible: %.2f%%%n",
                    100.0 * cpuCores / visibleCpus);
            } else {
                System.out.println("process_cpu: unavailable");
            }
            System.out.printf(Locale.ROOT,
                "heap_used_mib before=%.2f after=%.2f%n",
                heapBefore / 1_048_576.0, heapAfter / 1_048_576.0);
            System.out.printf(Locale.ROOT,
                "heap_max_mib: %.2f%n",
                Runtime.getRuntime().maxMemory() / 1_048_576.0);
            if (gcBefore >= 0 && gcAfter >= gcBefore) {
                System.out.println("gc_collections_delta: "
                    + (gcAfter - gcBefore));
            } else {
                System.out.println("gc_collections_delta: unavailable");
            }
        } finally {
            server.stop(0);
            serverThreads.shutdownNow();
        }
    }
}
~~~

### 13.2. Biên dịch/chạy

Cần một JDK 17+ đầy đủ với `jdk.httpserver`, `jdk.management`, `java.management`, `java.net.http`. Với classpath application, các modules thường tự được resolve. Với project có `module-info.java`, hãy khai báo `requires` phù hợp.

~~~bash
javac --release 17 -encoding UTF-8 LoopbackHttpBenchmarkDemo.java
java LoopbackHttpBenchmarkDemo
~~~

**Một stdout có thật từ lần test trên một môi trường JDK (giá trị performance thay đổi khi chạy lại):**

~~~text
requests_completed: 240
successes: 240
failures: 0
throughput_req_per_s: 5340.35
latency_ms p50=1.177 p95=2.536 p99=3.398
process_cpu_cores_avg: 6.258
process_cpu_pct_visible: 22.35%
heap_used_mib before=33.11 after=65.11
heap_max_mib: 30208.00
gc_collections_delta: 0
~~~

**Không kỳ vọng throughput 5340.35 RPS hoặc heap 65.11 MiB trên máy của bạn.** Một mini test ngắn với cả client/server trong cùng JVM có thể có process CPU sampled rất nhiễu, nhiều background threads và JIT/GC; `heap_max_mib` tùy `-Xmx`/container; p99 thay đổi theo scheduler và hardware.

Nếu provider không hỗ trợ process CPU time, chương trình sẽ in `process_cpu: unavailable` thay vì ghi một số CPU giả bằng 0%. Nếu request lỗi do runtime/network, `successes` có thể nhỏ hơn 240. Đây là hành vi test cần được báo, không phải dữ liệu được giấu.

### 13.3. Hiểu chính xác các phép đo

- `REQUESTS=240` và `BATCH_SIZE=12` → 20 batches; đợi `allOf` trước batch mới nên **closed loop**.
- `System.nanoTime()` đo elapsed từ ngay trước `sendAsync` đến `handle`; bao gồm phần client/server/network của HTTP exchange theo `BodyHandlers.ofByteArray()`.
- `AtomicInteger` tránh race khi callbacks hoàn tất trên các threads khác nhau.
- `latencies` có một phần tử cho **mỗi attempt** và gồm thời gian tới khi lỗi được ghi nhận nếu request exceptional. Dashboard thực nên chia successful latency và timeout/error metrics.
- `completed/s` đo **cửa sổ wall** bao gồm khởi tạo các batches và đợi tất cả callbacks, không cộng individual latencies để tính total duration.
- CPU core-equivalents là **process JVM gồm cả client+server**; không thể nói đó là CPU server riêng.
- Heap used snapshot before/after là **hai điểm thời gian**, không phải peak hay proof of leak.
- GC collection delta bằng 0 chỉ cho thấy counter không tăng trong cửa sổ ngắn.
- `Runtime.maxMemory()` là heap maximum, không phải OS RSS.
- `server.stop(0)` và `serverThreads.shutdownNow()` giải phóng server/executor sau test; code không tạo HTTP client riêng cho mỗi request.

### Bài thử ở môi trường thật cần gì thêm?

Chạy server/client ở **hai process/máy**; workload thực, response body sizes phân phối, HTTP/TLS/connection reuse đúng cấu hình, offered rate cố định nếu cần, sample count lớn, duration đủ dài, repeats và cả OS/container metrics. Nếu muốn benchmark **một đoạn xử lý Java nhỏ** thay vì end-to-end HTTP, cân nhắc **JMH** với warmup/iterations/forks thay vì tự viết microbenchmark bằng một vòng for.

## 14. Tìm bottleneck từ bốn nhóm metrics

Đây là **giả thuyết điều tra**, không phải chẩn đoán chắc chắn:

| Quan sát đồng thời | Nơi đáng kiểm tra |
|---|---|
| RPS tăng, p99 ổn, CPU vừa, lỗi thấp | Có thể còn headroom; ramp-up thận trọng |
| RPS chững, CPU process cao, p99 tăng | CPU saturation, JIT/GC, serialization, lock contention |
| CPU thấp nhưng p99 cao, queue/pool chờ dài | DB/upstream I/O, connection pool, semaphore, network |
| p50 ổn, p99 chỉ thỉnh thoảng spike | GC pauses, kernel scheduling, retransmission, queue bursts |
| p50/p95/p99 cùng tăng | Bottleneck nền, server capacity giảm, upstream chậm |
| Heap used tăng cùng tải, giảm sau GC | Allocation pressure, cần xem allocation rate |
| Heap live set tăng sau nhiều chu kỳ GC | Có thể có retained references/leak |
| Heap thấp nhưng RSS/native tăng | Direct buffers, metaspace, stacks, native allocations |
| CPU generator cao, server CPU thấp | Generator không đủ tạo offered load |
| RPS cao nhưng 5xx/timeouts tăng | Failed throughput, không phải useful capacity tăng |
| Concurrency tăng, RPS không tăng nhưng p99 tăng | Quá saturation point, queue buildup |
| Server processing p99 thấp, client e2e p99 cao | Queue trước handler, network/proxy/TLS/pool wait |

**Đừng tối ưu bằng cách “thêm threads” khi chưa xác định bottleneck.** NIO server có thể phục vụ nhiều connections với ít selectors, nhưng nếu callback CPU-heavy chặn event loop, p99 vẫn tệ. Tương tự, nhiều worker threads khi DB connection pool chỉ có vài slots thường chỉ tạo queue ở nơi khác.

## 15. Quan sát bằng JFR, jcmd, JMX và GC logs

### JFR

Java Flight Recorder thu CPU samples, allocation/GC, thread scheduling và nhiều JVM events phù hợp để điều tra p99 spikes/cpu pressure. Với một JVM do bạn sở hữu, xem PID:

~~~bash
jcmd
~~~

Ví dụ kích hoạt một profile có thời hạn:

~~~bash
jcmd 12345 JFR.start name=netperf settings=profile duration=60s filename=netperf.jfr
~~~

**12345 là PID ví dụ giả**; chọn PID thật có quyền kiểm tra. `settings=profile` có overhead, có thể ảnh hưởng benchmark. File JFR chứa metadata/stack traces có thể nhạy cảm; bảo vệ theo chính sách.

### Heap, thread diagnostics

~~~bash
jcmd 12345 GC.heap_info
jcmd 12345 Thread.print
~~~

Thread dump có thể giúp thấy WAITING/BLOCKED/RUNNABLE nhưng không phải mọi RUNNABLE thread đều **đang dùng CPU**. Heap info là snapshot; kết hợp repeated windows/profiling trước khi kết luận leak.

### Native Memory Tracking

Trên HotSpot, để có NMT cần bật từ lúc khởi động:

~~~bash
java -XX:NativeMemoryTracking=summary -jar service.jar
jcmd 12345 VM.native_memory summary
~~~

`service.jar` là tên **ứng dụng minh họa**, không phải dependency của demo; PID phải thay. NMT có overhead và không bao quát mọi native allocations do các thư viện bên ngoài. Nó **không phải tổng RSS đúng tuyệt đối**, cần đối chiếu OS/cgroup metrics.

### GC logs

~~~bash
java -Xlog:gc*:file=gc.log:time,uptime,level,tags -jar service.jar
~~~

Đây là cấu hình minh họa của HotSpot, cần thiết lập log retention/rotation. So GC pause timestamps với latency tail spikes trong cùng window, không khẳng định quan hệ nhân quả chỉ vì một event trùng lúc.

### MXBeans

- `MemoryMXBean`: heap/non-heap.
- `GarbageCollectorMXBean`: collections và collection time.
- `ThreadMXBean`: thread count, thread CPU times khi support.
- `OperatingSystemMXBean` mở rộng của JDK: process CPU time.
- `BufferPoolMXBean`: direct/mapped buffers.

Khi có metrics backend như Micrometer/Prometheus/OpenTelemetry, ưu tiên xuất histogram có khả năng aggregation. Không dùng **raw URL có token/user ID**, session cookie hoặc request ID làm high-cardinality metrics labels; dùng route template và redaction.

## 16. Đặt SLO thay vì chỉ công bố RPS cao

Một ví dụ SLO thiết kế:

> “Ít nhất 99% requests hợp lệ đến GET /items trong cửa sổ đánh giá phải hoàn tất thành công trong 200 ms theo client-side e2e timing; timeouts và HTTP 5xx được tính vào phần không đạt.”

Đây là **SLO ví dụ**, không phải một SLA có thật của hệ thống. Muốn vận hành:
1. Chốt boundary, event nào được tính là valid request.
2. Xác định status 2xx/4xx/5xx, timeouts, cancels, dropped load và redirects.
3. Chọn time window và cách gộp histogram across instances.
4. Công bố throughput + error rate + latency distribution + CPU/memory.
5. Bảo đảm headroom cho spike, failover và background work.

**Chú ý:** “99% requests thành công” và “99% requests hoàn tất **thành công dưới 200 ms**” là hai điều kiện khác nhau. Một request thành công sau 10 giây có thể đạt điều kiện thứ nhất nhưng không đạt điều kiện thứ hai.

## 17. Lỗi phổ biến cần tránh

| Sai lầm | Vấn đề | Cách sửa |
|---|---|---|
| Chỉ nhìn average latency | p99 tail có thể rất lớn | Báo p50/p95/p99/max |
| Báo p99 từ 20 requests như production metric | Sample count không đủ | Window/mẫu đủ lớn |
| Lấy trung bình p99 từng pod | Không phải quantile global | Merge histogram/raw samples |
| Đo bằng `System.currentTimeMillis` trong operation ngắn | Wall clock drift/resolution | `System.nanoTime` |
| Không kiểm tra HTTP status/body | Fast HTTP errors làm RPS đẹp | Completed và success RPS riêng |
| Không ghi timeouts/dropped load | SLO được tô hồng | Error/timeout/drop counts |
| Không phân biệt successful-only và all-attempt latencies | Trộn failure latency với success | Báo metric boundaries rõ |
| HTTP body handler trả InputStream rồi đo ngay | Chưa đủ full-body latency | Đo đến khi đọc body xong |
| Không warmup nhưng so steady-state | JIT/cache/cold connection gây nhiễu | Warmup và cold-start test riêng |
| Chọn run nhanh nhất | Selection bias | Lặp nhiều runs, báo variability |
| Client/server chung JVM rồi quy CPU riêng server | CPU đo cả generator và server | Tách process/host |
| Chạy 50 ms rồi kết luận CPU quota | Sample nhiễu | Window dài và OS cross-check |
| Heap used tăng = leak | Có thể chỉ allocations/cache/GC timing | Phân tích live set/retention |
| Heap max = RSS | Bỏ qua direct/native/stacks | OS RSS/NMT/BufferPoolMXBean |
| GC count không đổi = không có allocations | Counter không phản ánh toàn bộ | JFR allocation/heap |
| Closed-loop mà không nhắc coordinated omission | Tail latency có thể quá đẹp | Open-loop nếu phù hợp workload |
| Tăng concurrency vô hạn | Queue/memory quá tải, có thể DoS | Rate cap, ramp-up, stop limits |
| Đổi payload/TLS/HTTP version giữa A/B | So workload khác nhau | Khóa config và ghi rõ thay đổi |
| Dùng CPU % nhưng không nói số cores/quota | Khó so environments | Cores avg + visible/quota |
| Bật profiler nặng trong một run rồi so run không có | Instrumentation bias | Đo profile overhead |
| Chỉ nhìn CPU mà không nhìn queue/pool waits | Chẩn đoán sai bottleneck | Theo dõi queue, in-flight, upstream |
| Ghi URL/token vào metrics labels | Leakage và high cardinality | Route template, redact |
| Chạy load trên production không được phép | Nguy cơ downtime và chi phí | Lab/staging được phê duyệt |

## 18. Bài tập thực hành

1. Dịch vụ hoàn tất 2.400 requests/4 giây, trong đó 2.280 thành công. Tính completed RPS, successful RPS và error rate.
2. Vì sao service trả `503` rất nhanh vẫn có thể báo completed RPS cao?
3. Phân biệt offered load, completed throughput, success throughput và bytes/s.
4. `System.nanoTime()` khác `System.currentTimeMillis()` thế nào?
5. Tại sao kết thúc `sendAsync` với `ofInputStream()` chưa chắc là full-body latency?
6. Với mảng 100 samples 1..98, 600, 2.000 µs, p50/p95/p99/max là gì?
7. Với 20 samples, p99 nearest-rank là phần tử thứ mấy?
8. Tại sao không được lấy average của hai p95 từ hai servers?
9. Giải thích coordinated omission và vì sao closed-loop generator có thể bỏ sót tail khi server stall.
10. Một request timeout được loại khỏi histogram success. Cần báo thêm metric nào?
11. Little's Law dùng mean time hay p99? Điều kiện cần?
12. Process dùng 3 giây CPU trong 1 giây wall time, CPU core equivalents bao nhiêu?
13. Vì sao CPU time một process có thể lớn hơn elapsed wall time?
14. Vì sao CPU process cùng JVM client+server không thể đại diện riêng server?
15. `Runtime.maxMemory()` là heap max hay total RSS?
16. Nêu ít nhất ba vùng memory ngoài heap và cách quan sát direct buffers.
17. Heap used tăng giữa hai snapshots có phải bằng chứng leak không?
18. GC collection delta=0 có chứng minh không có allocation không?
19. Vì sao `-Xmx` chưa đủ để dự báo RAM container?
20. Trong demo B, vì sao phải dùng `AtomicInteger`?
21. Vì sao throughput dùng total wall time của batch loop chứ không cộng các latency requests?
22. P99 của 240 requests có thể đại diện traffic production không? Vì sao?
23. Trong một kết quả RPS chững, CPU thấp, queue dài, cần điều tra gì?
24. Nêu ba yếu tố có thể làm p99 tăng nhưng p50 vẫn ổn.
25. Muốn so phiên bản A/B, bạn sẽ khóa các thông số JDK/protocol/payload/load nào?
26. Khi nào nên đo cold-start latency riêng thay vì bỏ warmup?
27. Dùng JFR/jcmd có thể gây sai lệch performance không?
28. Một service đạt 99% successful nhưng 10% responses thành công chậm trên 200ms; có đạt SLO “99% thành công trong 200ms” không?

**Đáp án gợi ý:** (1) 600, 570 req/s, 5%; (2) lỗi nhanh không phải useful work; (3) tải muốn gửi/đã hoàn tất/thành công/bandwidth; (4) monotonic elapsed vs wall time; (5) stream chưa đọc hết; (6) 50/95/600/2000 µs; (7) 20; (8) quantile không linear; (9) client ngừng gửi khi server stall; (10) timeout/error rate và all-attempt duration; (11) mean và steady state; (12) 3 cores; (13) đa lõi; (14) CPU trộn hai bên; (15) heap max; (16) metaspace/stacks/direct buffers và BufferPoolMXBean; (17) chưa; (18) không; (19) native/offheap; (20) concurrency callbacks; (21) batch requests overlap; (22) mẫu ít, generator closed-loop, localhost; (23) upstream I/O/pool/locks; (24) GC pause/queue burst/retransmission; (25) cùng env/workload; (26) khi cold start là SLO; (27) có overhead; (28) không.

## 19. Checklist trước khi công bố một benchmark

1. Định nghĩa rõ endpoint/response correctness và cùng workload.
2. Ghi JDK, GC, heap, CPU quota, host/container, mạng và deployment version.
3. Có request counts: attempts/completions/success/errors/timeouts/rejected.
4. Tách completed throughput và successful throughput.
5. Đặt boundary latency, dùng `System.nanoTime` cho durations.
6. Báo percentile method, sample count, p50/p95/p99/max.
7. Không average p99 giữa replicas; merge histogram/distribution.
8. Tránh coordinated omission hoặc báo rõ mô hình closed-loop.
9. Có warmup cho steady state, cold-start đo riêng nếu cần.
10. Có duration đủ dài, repeats và cùng offered rate/concurrency.
11. CPU process time cùng window với latency/throughput; báo cores/quota.
12. Heap used/committed/max cùng native/RSS/GC khi cần.
13. Tách server khỏi load generator khi kết luận capacity.
14. Dùng JFR/JMX/GC logs để điều tra, kiểm soát diagnostic overhead.
15. Có tiêu chuẩn SLO đạt/không đạt, không chỉ một con số RPS đẹp.
16. Chỉ kiểm thử hệ thống được phép; bảo vệ logs/telemetry khỏi secrets.

## 20. Tổng kết

- **Throughput** là số công việc hoàn tất/giây; **goodput** là công việc thành công/hữu ích. Luôn công bố status/error/timeout context.
- **Latency là phân phối**, không chỉ mean; p50/p95/p99 cần sample count và percentile method rõ ràng. Không average percentiles giữa machines.
- **Coordinated omission** có thể làm closed-loop benchmark đánh giá tail quá đẹp so với workload có arrival rate độc lập.
- **CPU** nên đo process CPU time và wall time trong cùng window, quy đổi core-equivalents; xác định quota và tách CPU generator khỏi server.
- **Memory** bao gồm heap used/committed/max và các vùng native/direct/stacks; RSS không bằng heap, memory tăng trong một snapshot không chứng minh leak.
- **GC/JFR/queue/network** giúp giải thích p99 spikes; chỉ có một metric chưa đủ chỉ ra nguyên nhân.
- **Benchmark tốt** có workload contract, warmup, thời gian đo đủ, repeats, correct response validation và SLO.
- **Hai Java 17 demos đã chạy thật:** percentile/throughput với dữ liệu cố định; HTTP loopback với 240 requests, latency p50/p95/p99, CPU process, heap và GC counts.

### Tài liệu tham khảo

- [Oracle Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Oracle Java SE 17 — HttpServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpServer.html)
- [Oracle Java SE 17 — ManagementFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ManagementFactory.html)
- [Oracle Java SE 17 — MemoryMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryMXBean.html)
- [Oracle Java SE 17 — MemoryUsage](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/MemoryUsage.html)
- [Oracle Java SE 17 — BufferPoolMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/BufferPoolMXBean.html)
- [Oracle Java SE 17 — GarbageCollectorMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/GarbageCollectorMXBean.html)
- [Oracle Java SE 17 — ThreadMXBean](https://docs.oracle.com/en/java/javase/17/docs/api/java.management/java/lang/management/ThreadMXBean.html)
- [Oracle Java SE 17 — OperatingSystemMXBean mở rộng](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.management/com/sun/management/OperatingSystemMXBean.html)
- [Oracle Java SE 17 — jcmd và JFR](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jcmd.html)
- [Oracle Java SE 17 — JFR command-line](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jfr.html)
- [OpenJDK JMH](https://github.com/openjdk/jmh)
