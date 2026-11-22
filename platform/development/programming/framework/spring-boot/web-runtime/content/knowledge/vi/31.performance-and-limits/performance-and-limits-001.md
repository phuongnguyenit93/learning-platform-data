# Phân biệt thông lượng, độ trễ, số yêu cầu đồng thời và mức sử dụng tài nguyên trong Spring Boot

## 1. Mục tiêu và bối cảnh

Trong vận hành **Spring Boot web runtime**, bốn đại lượng rất dễ bị gọi chung là “hiệu năng”:

1. **Thông lượng (throughput):** hệ thống hoàn thành bao nhiêu HTTP request trong một đơn vị thời gian?
2. **Độ trễ (latency):** một request mất bao lâu từ điểm bắt đầu tới điểm kết thúc được định nghĩa?
3. **Số yêu cầu đồng thời (concurrent / in-flight requests):** tại một thời điểm có bao nhiêu request đã bắt đầu nhưng chưa hoàn tất?
4. **Mức sử dụng tài nguyên (resource utilization):** CPU, bộ nhớ, thread, connection, hàng đợi, disk I/O, network và downstream đang được sử dụng đến đâu so với giới hạn thật?

Bốn đại lượng **liên quan nhưng không đồng nghĩa**. Một web service có thể đạt RPS cao nhưng p99 latency tệ; có thể có 500 request đang chờ I/O với CPU chỉ 10%; có thể CPU 95% mà throughput không tăng được; hoặc số socket kết nối mở rất lớn trong khi chỉ một phần nhỏ request đang chạy.

Bài học này thuộc chủ đề **Hiệu năng và giới hạn**. Trọng tâm là mô hình đo đạc, khả năng chịu tải và sự khác biệt giữa **Spring MVC trên Servlet container/Tomcat** và **Spring WebFlux**. Phần thực hành dùng **Java 17+, Spring Boot 3.5.16, Micrometer/Actuator, Tomcat** với code biên dịch/chạy được; có lệnh đo HTTP thật, bài kiểm thử tích hợp và một load probe bằng JDK HttpClient để tái hiện sự khác nhau giữa lượng tải, độ trễ và tài nguyên.

Sau khi học, bạn có thể:

- Viết đúng đơn vị **requests/second**, **milliseconds**, **requests in flight**, **CPU cores / CPU %**, **bytes**, **threads** và **connections**.
- Đọc p50/p95/p99 mà không nhầm percentile với trung bình.
- Dùng **Little's Law** với đúng giả thiết để liên hệ throughput, mean latency và average in-flight requests.
- Nhận diện **queueing**, saturation, backpressure, timeouts, retries và tail latency.
- Biết vì sao tăng `server.tomcat.threads.max`, số connections hay số replicas **không tự bảo đảm** ứng dụng nhanh hơn.
- Kích hoạt metrics HTTP/server/JVM và đo đồng thời, không chỉ xem một dòng log duration.
- Thực hiện load test có kiểm soát, tránh “coordinated omission” và dữ liệu đo sai vì client yếu hoặc môi trường không ổn định.

**Câu hỏi phải trả lời trước mọi benchmark:** đo từ **góc nhìn nào** (client, proxy, Tomcat, controller hay downstream), ở **điểm bắt đầu/kết thúc nào**, với **tải và môi trường nào**, và mục tiêu SLO là gì?

## 2. Bốn đại lượng: định nghĩa, công thức, đơn vị

| Đại lượng | Ký hiệu thường dùng | Cách định nghĩa/đơn vị | Điều không thể suy ra chỉ từ đại lượng đó |
| --- | --- | --- | --- |
| Throughput hoàn thành | `X` hoặc `λ` khi hệ thống ổn định | completed requests / second (RPS) | Không nói request nhanh hay chậm; không nói còn dư capacity |
| Offered load / arrival rate | `λ_in` | số request được **gửi đến** mỗi giây | Không chắc số request **hoàn tất** bằng mức gửi đến |
| Latency | `W`, `R`, `T` | seconds/request hoặc ms/request | Một con số trung bình che tail latency |
| In-flight/concurrency | `L`, `N` | số request đã nhận nhưng chưa hoàn tất, tại một thời điểm | Không đồng nghĩa số threads hoặc TCP connections |
| CPU utilization | `U_cpu` | tỷ lệ thời gian CPU bận so với **quota/capacity** được cấp | Không cho biết thread đang block hoặc app có bottleneck DB |
| Memory usage | `M` | heap, non-heap, direct memory, RSS, % cgroup limit | Heap 70% không mặc nhiên là leak |
| Pool utilization | `U_pool` | active/leased connections chia giới hạn pool | Không nói upstream đang lỗi hay không |
| Queue depth | `Q` | request/pending tasks chưa được xử lý | Không đồng nghĩa throughput đã tăng |

**Định nghĩa throughput chính xác:**

\[
\text{RPS}_{completed}
= \frac{\text{số request hoàn tất trong cửa sổ quan sát}}{\text{số giây của cửa sổ}}
\]

Ví dụ trong **60 giây ổn định**, hệ thống hoàn tất 7.200 requests:

\[
X=7200/60=120\ \text{requests/second}
\]

Nếu có 9.000 requests được gửi tới trong cùng khoảng đó nhưng chỉ 7.200 hoàn tất, **arrival rate = 150 RPS** và **completed throughput = 120 RPS**. Chênh lệch có thể đang nằm trong hàng đợi/in-flight, bị hủy, lỗi, bị gateway từ chối, hoặc rơi vào các cửa sổ đo lường khác nhau. Không trừ hai rate rồi tự tuyên bố chính xác bao nhiêu request bị mất mà chưa kiểm tra inflight và counter boundaries.

**Tính cả lỗi khi báo throughput:** server có thể xử lý 100 RPS gồm 60 lần 200, 30 lần 429 và 10 lần 503. Nếu chỉ nói “100 RPS” thì không phản ánh **goodput** — lượng request tạo ra kết quả nghiệp vụ thành công. Cần trình bày status mix, accepted/successful throughput, error rate và SLO.

### 2.1. Latency đo từ đâu đến đâu?

Một client có thể đo end-to-end latency:

```text
Client bắt đầu gửi request
   | DNS/TCP/TLS, network tới edge
   v
Gateway / reverse proxy (queue, route, retries)
   v
Tomcat nhận và dispatch
   v
Spring filters -> controller -> service -> database/outbound HTTP
   v
Serialize/compress và truyền response
   v
Client nhận đủ response body
```

Một số kiểu đo:

- **Client end-to-end**: từ trước khi gửi đến khi client nhận đủ response theo cách tải; bao gồm nhiều network/proxy/client overhead.
- **Time to first byte (TTFB)**: thời điểm byte phản hồi đầu tiên tới client; không đại diện cho **tổng thời gian download**.
- **Server request duration**: thời gian các HTTP server observations của framework bao phủ; cấu hình/filter/asynchronous completion ảnh hưởng semantics.
- **Controller method time**: thời gian code trong controller/service; **không** bao gồm mọi filter, proxy, network hoặc response streaming.
- **Downstream call duration**: từ lúc gọi tới khi client HTTP nhận dữ liệu theo semantics; có thể gồm chờ connection pool.

**Không trộn latency tại hai điểm đo rồi so trực tiếp.** Ví dụ client p95=300 ms, service p95=120 ms không có nghĩa chính xác 180 ms “bị mất ở mạng”: percentile không cộng/trừ tuyến tính, và request sets/sampling windows có thể khác.

### 2.2. In-flight request và concurrency

Khi một request bắt đầu được theo dõi, bộ đếm tăng; khi request thực sự kết thúc theo contract đo, bộ đếm giảm. Giá trị `inFlight(t)` là ảnh chụp **tại thời điểm t**, không phải “số request trong một phút”.

Ví dụ:

```text
12:00:00.000  request A bắt đầu -> in-flight=1
12:00:00.010  request B bắt đầu -> in-flight=2
12:00:00.020  request C bắt đầu -> in-flight=3
12:00:00.070  request B hoàn tất -> in-flight=2
12:00:00.090  request A hoàn tất -> in-flight=1
12:00:00.130  request C hoàn tất -> in-flight=0
```

**Peak in-flight** trong một khoảng không bằng **average in-flight** của cùng khoảng. Với Servlet async/SSE/WebSocket, định nghĩa “request vẫn đang mở” cần làm rõ: một long-lived stream có thể làm số kết nối/in-flight cao rất lâu trong khi request thread đã được giải phóng.

### 2.3. Resource utilization cần chỉ rõ mẫu số

Nói “CPU 80%” thiếu thông tin nếu không biết:

- CPU 80% của **một core**, của **4 vCPU được cấp**, hay của toàn host 64 cores?
- JVM thấy bao nhiêu processors sau container limits? Có CPU throttling do cgroup quota không?
- Trong cùng thời điểm, CPU usage của app, DB, proxy và máy phát tải là bao nhiêu?
- Có throttling, steal time, GC pauses hoặc native/direct-buffer allocation không?

Nếu app được quota 2 vCPU và sử dụng gần 2 vCPU liên tục, nó có thể bị giới hạn dù host còn nhiều cores rỗi. `Runtime.availableProcessors()` là **số processors có sẵn theo JVM/runtime**, không phải phần trăm CPU đang dùng; đừng in nó như phép đo utilization.

## 3. Bảng ví dụ minh họa: cùng throughput nhưng trải nghiệm khác nhau

Các giá trị sau là **dữ liệu giả định để học**, không phải kết quả benchmark một ứng dụng Spring Boot cụ thể:

| Tình huống | Completed RPS | Mean latency | p95 latency | In-flight trung bình gần đúng | CPU sử dụng |
| --- | ---: | ---: | ---: | ---: | --- |
| A — xử lý ổn định | 100 | 50 ms | 90 ms | ~5 | 35% quota |
| B — upstream chậm | 100 | 300 ms | 700 ms | ~30 | 18% quota |
| C — có queue/saturation | 100 | 900 ms | 2.500 ms | ~90 | 95% quota |
| D — phản hồi sớm bằng 429 | 150 tổng, nhưng 90 thành công | 60 ms (trộn status) | 100 ms | ~9 | 60% quota |

Giải thích:

- **A và B cùng 100 RPS** nhưng B giữ nhiều request in-flight hơn do mỗi request đợi lâu.
- **B có CPU thấp** vì có thể block chờ database hoặc network. CPU thấp **không chứng minh** ứng dụng còn dư throughput capacity; bottleneck có thể là connection pool hoặc downstream quota.
- **C có thông lượng không tăng** nhưng mean/p95 latency cao và CPU bận: tải vượt điểm cân bằng, queue tăng và tail latency xấu.
- **D có throughput tổng lớn hơn** nhưng thành công chỉ 90 RPS: đếm 429 như “xử lý nhanh” mà báo tốt hơn A là sai. Cần tách goodput/status mix.

Giá trị in-flight trong A/B/C dùng **Little's Law** cho hệ thống được giả định ổn định và cùng boundary: `100 × 0,05 = 5`, `100 × 0,3 = 30`, `100 × 0,9 = 90`. Với D, `150 × 0,06 = 9` chỉ áp dụng khi mean latency của **toàn bộ** responses trong cùng completed population được dùng nhất quán.

## 4. Percentile latency: p50, p95, p99 và tail

Giả sử có 100 request đã hoàn tất, sắp xếp duration tăng dần:

- **p50**: ngưỡng khoảng 50% samples có latency không vượt; phản ánh “request điển hình” hơn mean trong phân phối lệch.
- **p95**: khoảng 95% samples không vượt ngưỡng đó; 5% còn lại có thể rất chậm.
- **p99**: khoảng 99% samples không vượt; đặc biệt quan trọng khi request lớn/cần SLO chặt.
- **max**: giá trị lớn nhất quan sát trong cửa sổ; nhạy với số mẫu và outliers.
- **mean**: tổng durations / số samples; dùng trong Little's Law khi định nghĩa W là **thời gian trung bình của cùng tập**.

Ví dụ 99 requests mất 20 ms nhưng 1 request mất 10.000 ms:

\[
\mathrm{mean}=(99 \times 20 + 10000)/100=119{,}8\ \mathrm{ms}
\]

Đa số user thấy 20 ms, một số ít thấy 10 giây, mean gần 120 ms. **Một mean duy nhất không phản ánh tail**. Ngược lại p99 tùy phương pháp tính percentile có thể **không đưa đầy đủ outlier duy nhất** vào ngưỡng; nên xem p99, max và số mẫu cùng nhau.

### 4.1. Percentile không cộng được giữa các service

Nếu service A p95=100 ms, B p95=200 ms thì request A→B **không thể** kết luận p95 tổng=300 ms. Percentile của tổng phụ thuộc **phân phối và sự tương quan** giữa thời gian ở mỗi chặng, cùng request population, retries và các nhánh gọi song song.

Tương tự, không cộng p95 riêng của mỗi instance để lấy p95 toàn cluster, và không tính average của các p95 rồi gọi “global p95”. Muốn percentile gộp, cần **histogram/distribution** có bucket tương thích hoặc raw samples đã được thu thập có kiểm soát. Micrometer/Prometheus histogram là một trong các cách đo tổng hợp.

### 4.2. SLO theo latency phải kèm success

Ví dụ SLO:

> Trong 30 ngày, 99% **request hợp lệ** tới `GET /api/items/{id}` hoàn thành **dưới 300 ms** và không bị lỗi server.

Cần định nghĩa cụ thể:

- Request nào hợp lệ và nằm trong denominator?
- 4xx do client/429 do overload có tính là failures không?
- Mốc latency lấy từ browser, gateway hay server?
- Có xét đủ response body cho streaming/download không?
- Có warm-up hoặc maintenance window được loại trừ không?
- Metric nào đại diện và có đủ samples, không high-cardinality labels?

SLO không nên chỉ là `p95 < 300ms` mà không có error rate/goodput. Một hệ thống có thể trả 503 thật nhanh để “tối ưu latency” nhưng không phục vụ nghiệp vụ.

## 5. Little's Law: liên hệ thông lượng, độ trễ và requests đồng thời

Với một hệ thống **ổn định** và một tập request/boundary đo nhất quán:

\[
L = \lambda W
\]

Trong đó:

- `L`: **số request trung bình trong hệ thống** (đang chờ + đang xử lý trong boundary đã chọn), đơn vị requests.
- `λ`: **lưu lượng hoàn tất/đến** trong trạng thái ổn định, requests/second, thống nhất population và không tích tụ queue vô hạn.
- `W`: **mean time trong hệ thống**, seconds/request, gồm thời gian chờ nếu boundary có queue.

Ví dụ:

```text
λ = 120 requests/second
W = 250 milliseconds/request = 0,25 second/request

L = λ × W
  = 120 × 0,25
  = 30 requests (trung bình)
```

Ý nghĩa: để duy trì throughput ~120 RPS với mean response 250 ms, hệ thống thường có trung bình ~30 requests trong boundary ấy. Đây **không phải** quy định phải đặt Tomcat threads.max=30. Có những request chờ I/O, Servlet async, HTTP/2 multiplexing, pool queue, business tasks và stream còn mở, nên số request in-flight không bằng số worker threads.

**Không lấy p95/p99 thay W** trong công thức. `L = λ × p99` không phải Little's Law. W là **mean latency**, không phải percentile.

**Điều kiện/giới hạn:**

1. Tải đủ ổn định trong cửa sổ đo; arrival/completion và in-flight không có xu hướng tăng vô hạn.
2. Cùng một request population: nếu throughput đếm mọi 2xx/4xx/5xx nhưng mean latency chỉ lấy 2xx, công thức bị sai.
3. Cùng boundary: không nhân throughput của toàn gateway với controller duration của một route rồi gọi số request in-flight toàn cluster.
4. Nếu có retries, một user operation có thể tạo nhiều HTTP exchanges. Phải xác định đếm **business operations** hay **HTTP requests**.
5. Với SSE/WebSocket kéo dài, lifetime của kết nối và duration của từng message khác nhau. Chọn đơn vị phù hợp; không dùng Little's Law của short-lived GET để sizing 10.000 sockets long-lived.
6. Đơn vị phải đúng: 120 RPS × 250 ms = 30 requests **sau khi đổi ms sang seconds**, không phải 30.000 requests.
7. Trong transient overload, số request pending có thể tăng nhanh dù completed throughput gần như cố định; con số từ Little's Law ở trạng thái ổn định không dự báo đầy đủ bùng nổ queue.

### 5.1. Chương trình Java 17 độc lập tính Little's Law

**`LittleLawDemo.java`**

```java
import java.util.Locale;

public class LittleLawDemo {
    public static void main(String[] args) {
        double completedRps = 120.0;
        double meanLatencyMs = 250.0;

        double meanInFlight = completedRps * meanLatencyMs / 1000.0;

        System.out.printf(
            Locale.ROOT,
            "Average in-flight requests: %.1f%n",
            meanInFlight
        );
    }
}
```

Chạy với JDK 17+:

```bash
javac LittleLawDemo.java
java LittleLawDemo
```

**Stdout chính xác** (theo mã và Locale.ROOT):

```text
Average in-flight requests: 30.0
```

Đây là **phép tính minh họa**, không phải phép đo concurrency của một ứng dụng đang chạy. Trong hệ thống thật phải lấy completed RPS và **mean latency** từ cùng cửa sổ và boundary.

## 6. Queueing, saturation và vì sao thêm load có thể làm chậm

Một web request có thể phải chờ:

```text
Client arrival
   |
   v
Ingress / gateway queue
   |
   v
Tomcat accept queue / worker availability
   |
   v
Application executor / semaphore / bulkhead
   |
   v
DB pool acquire / outbound HTTP pool acquire
   |
   v
CPU / database / network / service time
   |
   v
Response serialization + network
```

Mỗi queue có thể **giấu thời gian** mà chỉ nhìn một controller method không thấy. Nếu arrivals vượt service capacity, thời gian chờ tăng; một số request timeout hoặc bị từ chối. Khi gần bão hòa, chỉ một chút tăng tải cũng có thể tạo tail latency rất lớn.

### 6.1. Mô hình M/M/1 chỉ để hiểu xu hướng

Mô hình hàng đợi **M/M/1** có giả thiết khá mạnh: arrivals Poisson, service time theo phân phối exponential, một server, steady state và buffer lý tưởng. Với `λ < μ` (μ là service capacity requests/s), **mean response time của hệ thống**:

\[
W = \frac{1}{\mu-\lambda}
\]

Nếu `μ = 100 requests/s`, minh họa:

| Arrival rate λ | Utilization `ρ=λ/μ` | Mean response W theo M/M/1 |
| --- | ---: | ---: |
| 50 RPS | 50% | 20 ms |
| 80 RPS | 80% | 50 ms |
| 90 RPS | 90% | 100 ms |
| 98 RPS | 98% | 500 ms |

**Đây là kết quả của mô hình lý thuyết, không phải latency Spring Boot thực tế**. Web services có nhiều workers, variable CPU time, database calls, caching, retries, connection pools, HTTP/2 và concurrency đa tầng. Công thức hữu ích để thấy **latency tăng phi tuyến gần ngưỡng bão hòa**, không nên dùng như capacity calculator production nếu chưa kiểm chứng giả thiết.

### 6.2. Concurrency cao chưa chắc throughput cao

Nếu upstream giới hạn **10 connections** và mỗi call mất 100 ms, một mô hình blocking đơn giản chỉ có thể thực hiện khoảng **100 calls/s** từ 10 slots trong điều kiện lý tưởng. Tăng số request đồng thời từ 10 lên 100 chỉ làm 90 requests phải chờ acquire hoặc timeout; không tự tăng giới hạn upstream.

Nếu request tiêu tốn trung bình 20 ms CPU-time trên mỗi request và app thật sự có **4 vCPU quota**, upper bound lý tưởng theo CPU demand:

\[
X_{\max,\mathrm{CPU}} \leq \frac{4\ \mathrm{CPU\ seconds/second}}
{0.020\ \mathrm{CPU\ seconds/request}}
= 200\ \mathrm{requests/second}
\]

Đây chỉ là **trần lý thuyết ở 100% CPU**, chưa tính kernel, GC, TLS, logging, JVM overhead, dependencies, load imbalance hay SLO tail latency. Throughput bền vững ở latency mong muốn thường **thấp hơn** ngưỡng này. Nếu bottleneck là DB, con số 200 cũng không thể dùng để dự đoán kết quả.

### 6.3. Backpressure, admission control và retry storms

Một hệ thống có thể chọn:

- **Bounded concurrency** với semaphore/bulkhead cho downstream.
- **Queue hữu hạn** với timeout/deadline cụ thể.
- **Load shedding** hoặc trả 429/503 có kiểm soát khi vượt giới hạn thay vì nhận vô hạn.
- **Retry có backoff + jitter**, chỉ khi operation idempotent/an toàn và còn deadline.
- **Circuit breaker** khi dependency lỗi; giới hạn fan-out và avoid duplicate attempts.
- **Autoscaling** trên tín hiệu phù hợp như CPU, latency, requests in flight, queue; tính tới warm-up/thời gian spin up.

Tăng concurrency quá mức có thể tạo **retry amplification**: client timeout rồi retry, proxy retry, service lại retry, khiến downstream nhận nhiều lần cho một tác vụ business. Vì vậy phải đo **offered load, completed throughput, rejected requests, retries và queue** cùng nhau.

## 7. Mức sử dụng tài nguyên: nhìn nhiều chiều thay vì chỉ CPU

### 7.1. CPU

CPU cao có thể do business computation, serialization JSON, TLS, regex, GC, lock contention hoặc retry loop. CPU thấp nhưng latency cao có thể do:

- DB queries chậm hoặc DB connection pool bị hết.
- Outbound HTTP pool pending.
- Thread đang block ở `Future.get()`, socket read, filesystem.
- Gateway/network hoặc server-side throttling.
- Hàng đợi executor giữ request lâu trong khi thread ít dùng CPU.
- Low CPU quota cùng cgroup throttling theo chu kỳ.

Đo cả **CPU used / quota**, **CPU throttling**, GC CPU, load distribution giữa pods và downstream. Một con số CPU 95% chưa đủ biết tối ưu code nào; profiling/tracing giúp tìm bottleneck.

### 7.2. Memory: heap, non-heap và RSS

Phân biệt:

- **Heap used/committed/max**: object allocations, caches, request bodies; GC quản lý.
- **Non-heap**: metaspace, code cache và các vùng JVM.
- **Direct/native buffers**: Netty/TLS/compression hoặc native allocations.
- **Container RSS/working set**: bộ nhớ thực tế theo cgroup/pod; có thể khác heap nhiều.
- **GC pause frequency/duration**: thời gian stop-the-world ảnh hưởng latency tail.

Heap cao vì cache “nóng” có thể bình thường; heap tăng liên tục kèm GC thường xuyên và OOM mới là dấu hiệu cần điều tra. **Tăng heap** có thể giảm frequency GC nhưng cũng tiêu thụ quota và kéo dài một số pause; phải đo, không mặc định càng lớn càng nhanh.

### 7.3. Thread và executor

- **JVM live threads** không phải số HTTP requests in flight.
- **Tomcat busy threads** khác total threads; một thread có thể đang chờ socket/DB và vẫn tính busy.
- **Executor active/queued/rejected** là các số riêng cho pool xử lý bất đồng bộ.
- Trong Java 21 virtual threads, số tasks đồng thời có thể vượt xa platform thread count mà CPU không thay đổi khả năng xử lý tính toán.
- Thread dumps có thể cho biết BLOCKED/WAITING/TIMED_WAITING/RUNNABLE, nhưng cần đọc stack/context; không cộng tất cả WAITING rồi gọi deadlock.

### 7.4. TCP connections và HTTP requests

Một HTTP/1.1 keep-alive connection có thể phục vụ nhiều request **nối tiếp**; HTTP/2 có thể multiplex nhiều streams. Idle socket không đồng nghĩa request đang chạy. Với WebSocket và SSE, có những connection sống lâu nhưng rất ít CPU. Đếm connections để tính max in-flight có thể sai cả hai chiều.

### 7.5. Disk I/O và network

File downloads, access logging sync, upload streaming, compression và reverse proxy buffering có thể làm throughput phụ thuộc **network bytes/s**, disk IOPS, kernel buffers, TLS encryption hoặc bandwidth dù CPU controller thấp. Cần đo request body size/response size distribution và compression; “100 RPS” với 1 KB khác rất xa “100 RPS” với file 100 MB.

## 8. Spring MVC / Tomcat: threads, connections, queue và async

### 8.1. Worker threads không bằng concurrent requests

Với Spring MVC đồng bộ truyền thống, một request thường chiếm Servlet worker thread trong giai đoạn controller/filter xử lý blocking operations. Nếu 200 request cùng block 1 giây ở DB, có thể cần nhiều threads hoặc queue, **nhưng** tăng thread pool chỉ làm thêm request xếp hàng ở DB nếu DB đã bão hòa.

Các thuộc tính phổ biến cho embedded Tomcat trong Spring Boot 3.5:

```properties
# Các số bên dưới là cấu hình demo; KHÔNG là mức khuyến nghị production.
server.tomcat.threads.max=40
server.tomcat.threads.min-spare=5
server.tomcat.max-connections=300
server.tomcat.accept-count=100
server.tomcat.mbeanregistry.enabled=true
```

Ý nghĩa:

- `server.tomcat.threads.max`: tối đa Servlet worker threads trong mô hình platform threads; mặc định 200 trong Boot 3.5, có thể không tác dụng khi **virtual threads enabled** theo tài liệu.
- `server.tomcat.threads.min-spare`: số worker threads dự phòng theo implementation, không là số requests bắt buộc chạy.
- `server.tomcat.max-connections`: giới hạn connections mà Tomcat nhận/xử lý tại cùng thời điểm; **không** đồng nghĩa max active requests hay max threads.
- `server.tomcat.accept-count`: mức queue incoming connection requests khi connector đã đến limits, không là toàn bộ request backlog của business.
- `server.tomcat.mbeanregistry.enabled=true`: cần nếu muốn Boot auto-instrument Tomcat metrics từ MBeans; MBeans/Tomcat stats chỉ hữu ích khi có Actuator/Micrometer và metric names đúng version.

**Đừng kết luận từ `threads.max=40` rằng ứng dụng chỉ có thể xử lý 40 connections**. Keep-alive idle và async có thể thay đổi mối quan hệ; HTTP/2 streams còn có đặc tính multiplexing.

### 8.2. Servlet async và streaming

Spring MVC hỗ trợ `Callable`, `DeferredResult`, `WebAsyncTask`, `StreamingResponseBody` và `SseEmitter`. Khi controller dùng Servlet async, container thread có thể được trả lại trước khi response hoàn tất. Nhưng:

- Async request có thể vẫn chiếm một slot trong quota kết nối.
- Blocking operations trong async executor vẫn cần threads.
- Với Spring MVC, các **response writes cho streaming vẫn blocking** theo framework async executor; không đồng nghĩa thành WebFlux non-blocking I/O.
- Response latency của client vẫn gồm thời gian chờ callback/stream, dù controller method trả về rất nhanh.
- Một filter đo thời gian tới `chain.doFilter` return không nhất thiết phản ánh **request completion latency** khi dùng async/streaming.

Spring Framework khuyến nghị cấu hình `AsyncTaskExecutor` thích hợp trong môi trường tải lớn; executor mặc định đơn giản không nên được coi là production sizing. Không nhận tất cả long-lived streams rồi tăng threads vô hạn.

### 8.3. Virtual threads Java 21+

Với `spring.threads.virtual.enabled=true` trên Java 21+ và stack hỗ trợ, blocking request tasks có thể được thực thi bằng virtual threads. Điều này có thể **giảm chi phí thread** khi nhiều tasks đợi I/O, nhưng:

- Không tạo thêm CPU cores.
- Không làm DB/query chậm trở nên nhanh một cách kỳ diệu.
- Không thay đổi giới hạn DB connections, HTTP pool, memory, bandwidth và downstream quota.
- Không làm CPU-bound tasks tự có throughput cao hơn.
- Pinning, synchronized/natives, ThreadLocal-heavy behavior và monitor contention vẫn phải được đo theo Java/JVM version.
- Không lấy `server.tomcat.threads.max` của platform threads làm công cụ sizing concurrency virtual threads theo cùng cách.

Nếu bật virtual threads, đo **outbound pool saturation, heap/GC, p95/p99 và user-perceived latency**. Các giới hạn nghiệp vụ/bulkheads vẫn cần thiết.

## 9. Spring WebFlux / Reactor Netty: non-blocking không có nghĩa vô hạn

WebFlux được thiết kế cho non-blocking I/O với event loop và Reactor `Mono`/`Flux`. Khi một handler chủ yếu chờ outbound HTTP hoặc DB driver non-blocking, WebFlux có thể phục vụ nhiều in-flight operations mà không giữ một thread riêng cho mỗi request.

Nhưng non-blocking không có nghĩa:

- CPU-heavy work có thể chạy thoải mái trên Netty event loop.
- Buffering/truyền file lớn không dùng memory.
- Có thể gọi `RestClient.block()` hoặc `Thread.sleep` trên event-loop threads mà không gây nghẽn.
- Backpressure ở Reactor giải quyết được mọi queue ở proxy/DB/remote API.
- Có thể nhận số subscriptions không giới hạn mà không có per-user quota và timeout.

Ví dụ snippet WebFlux (không phải class độc lập):

```java
@GetMapping("/remote")
Mono<String> remote() {
    return webClient.get()
        .uri("https://partner.example.org/status")
        .retrieve()
        .bodyToMono(String.class);
}
```

Cần biến `webClient` đã được inject và imports WebFlux/Reactor. Không gọi `.block()` trong handler. Một pipeline non-blocking vẫn chịu giới hạn của Netty connection pool, remote service, CPU decode, backpressure và client cancellation.

**So sánh cần công bằng:** MVC với blocking I/O, MVC với virtual threads, MVC async, WebFlux Netty **khác nhau về thread/resource model**. Không thể kết luận WebFlux “nhanh hơn” trong mọi tình huống từ một benchmark JSON localhost nhỏ; kết quả phụ thuộc workload, library tương thích, concurrency, logging, TLS, proxy và cách dùng thread.

## 10. Observability: đo bằng Spring Boot Actuator và Micrometer

Spring Boot Actuator/Micrometer giúp quan sát, nhưng cần phân biệt **request timer**, **active requests** và **resource gauges**. Timer của một request hoàn tất không tự biến thành một số concurrency tức thời.

Các nhóm metrics quan trọng:

| Cần biết | Ví dụ metric/cách đo | Cách đọc |
| --- | --- | --- |
| Tổng request hoàn tất và duration | `http.server.requests` (Micrometer Timer, name chuẩn trong Spring MVC/WebFlux Boot 3.5) | COUNT/TOTAL_TIME/MAX; derive RPS bằng rate trên counter của monitoring backend |
| HTTP status mix | Tags `status`, `outcome`, `method`, `uri` | Phân tích tỷ lệ 2xx/4xx/5xx, route; tránh cardinality cao |
| JVM CPU | `process.cpu.usage` hoặc JVM/process metrics tùy exporter | Sử dụng CPU theo process; đối chiếu cgroup quota |
| JVM threads | `jvm.threads.live`, `jvm.threads.states` | Không đồng nghĩa in-flight |
| Heap/non-heap | `jvm.memory.used` và `jvm.memory.max` | Bytes theo `area`/`id`, so sánh với container RSS |
| GC | `jvm.gc.pause` và metrics phiên bản tương ứng | Tần suất/duration GC, liên hệ tail latency |
| Tomcat threads | `tomcat.threads.busy`/config metrics khi MBean registry bật | Container busy, không phải toàn request in flight |
| Tomcat connections | `tomcat.connections.current` hoặc tên tương đương nếu có | Kết nối, bao gồm idle; không phải số request |
| In-flight request app demo | `demo.requests.active` (custom Gauge) | Snapshot trong sync filter boundary, **không gồm toàn async lifetime** |
| Peak trong đời process | `demo.requests.peak` (custom Gauge) | Peak kể từ lúc app khởi động, không phải p95 |
| DB/HTTP pool queue | `hikaricp.connections.pending`, Reactor Netty provider pending | Nút thắt ở pool, có thể làm CPU thấp/latency cao |

**Lưu ý:** Tên meter/tag thực tế còn phụ thuộc Boot, Micrometer, binder và runtime. Không xem bảng trên như cam kết mọi metric mặc định luôn xuất hiện; mở `/actuator/metrics` hoặc endpoint Prometheus để kiểm tra tên thật. Đặc biệt các Tomcat metrics cần `server.tomcat.mbeanregistry.enabled=true` theo tài liệu Boot.

### 10.1. Timer COUNT không tự là RPS

Giả sử `http.server.requests` có COUNT 1.000 tại t=10s và COUNT 2.200 tại t=20s:

\[
\text{RPS over interval} = (2200-1000)/(20-10)=120
\]

Không lấy COUNT cuối cùng 2.200 rồi đọc là “2.200 RPS”. Với Prometheus, dùng `rate(...)` hoặc `increase(...)` trên **counter series** có labels thích hợp, chú ý metric name được chuẩn hóa (chẳng hạn `http_server_requests_seconds_count` khi dùng histogram/timer export). Monitoring backend khác có tên/semantics khác.

### 10.2. Prometheus histogram và percentile

Spring Boot hỗ trợ:

```properties
management.metrics.distribution.percentiles-histogram.http.server.requests=true
```

Cấu hình này cho phép histograms phù hợp với tính **aggregable percentile approximations** khi registry hỗ trợ, nhưng có chi phí cardinality/buckets. Cần chọn route tags ít cardinality và giới hạn bucket range/SLO khi vận hành lớn.

Trong Prometheus, nếu đã có histogram buckets cho `http.server.requests`, có thể ước lượng p95 bằng biểu thức kiểu:

```promql
histogram_quantile(
  0.95,
  sum by (le, uri) (
    rate(http_server_requests_seconds_bucket{job="spring-demo"}[5m])
  )
)
```

Đây là **ví dụ truy vấn**: label `job`, `uri`, meter name và cấu hình buckets phải khớp exporter thực, và route label phải là **template** thay vì ID người dùng. Không sao chép truy vấn khi Prometheus data source chưa có các series tương ứng.

**Không tính p95 từ trung bình p95 của từng instance**. Cần aggregate histogram buckets theo dimension đã chọn, giữ `le` và các labels muốn phân nhóm.

### 10.3. Vì sao `/actuator/metrics` không thay cho monitoring backend?

Metrics endpoint được dùng để **diagnostics** tại ứng dụng: liệt kê meter names và xem measurements/tags hiện có. Nó không phải time-series DB dùng để tính p99 tuần qua, rate qua nhiều replicas và SLO error budget. Để vận hành production, dùng registry/exporter và backend như Prometheus/OpenTelemetry phù hợp.

**Bảo mật Actuator:** metrics, env, heapdump, threaddump, configprops có thể tiết lộ thông tin runtime hoặc secrets. Trong demo có thể expose `health,metrics` trên localhost. Production cần network isolation/authentication/authorization, không công bố `/actuator/**` tùy ý cho Internet.

## 11. Dự án thực hành: đo latency và in-flight trong Spring Boot MVC

Ví dụ cung cấp hai loại endpoint có đặc tính rất khác nhau:

- `GET /demo/wait?ms=100`: **chờ bằng Thread.sleep** — mô phỏng blocking I/O latency, hầu như không cần CPU trong khi chờ. **Chỉ dùng để học**.
- `GET /demo/cpu?iterations=100000`: thực hiện phép tính CPU — đo độ trễ bị ảnh hưởng bởi CPU/quota/concurrency; không phải benchmark CPU khoa học.
- `GET /demo/resources`: xuất snapshot số request đang trong filter, peak, live JVM threads, heap used/max, `availableProcessors`; snapshot **không** tính CPU utilization.
- `/actuator/metrics/http.server.requests` và `/actuator/metrics/demo.requests.active`: xem metrics HTTP và gauge do demo đăng ký.

Với hai loại tải, bạn sẽ thấy **in-flight**, **duration**, **CPU usage** và **throughput** không biến đổi cùng một cách khi tăng concurrency.

### 11.1. Cấu trúc file

```text
performance-demo/
├─ pom.xml
└─ src/
   ├─ main/
   │  ├─ java/com/example/demo/
   │  │  ├─ PerformanceApplication.java
   │  │  ├─ RequestConcurrencyFilter.java
   │  │  └─ PerformanceController.java
   │  └─ resources/application.properties
   └─ test/
      └─ java/com/example/demo/
         └─ PerformanceApplicationTest.java
```

### 11.2. Maven `pom.xml`

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>performance-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot dependency management cung cấp phiên bản tương thích của Spring Framework, Micrometer và embedded Tomcat. `3.5.16` là bản đã phát hành ngày 25/06/2026 nhưng **đây là bản OSS cuối của dòng 3.5.x**; với ứng dụng mới đưa lên production, nên chọn dòng Spring Boot còn được OSS hỗ trợ và bản vá hiện hành, kiểm tra thay đổi starter/API ở Boot 4.x. Bản 3.5.16 được cố định ở đây để bài thực hành tái lập import theo dòng 3.x.

### 11.3. Cấu hình

**`src/main/resources/application.properties`**

```properties
server.port=8080

# Giới hạn mẫu dễ quan sát: chỉ dùng local/benchmark được phép.
server.tomcat.threads.max=40
server.tomcat.threads.min-spare=5
server.tomcat.max-connections=300
server.tomcat.accept-count=100

# Cho phép đo các Tomcat MBean metrics.
server.tomcat.mbeanregistry.enabled=true

# Local diagnostics only. Không để /actuator/metrics public trên Internet.
management.endpoints.web.exposure.include=health,metrics

# Cung cấp histogram cho request timer khi registry hỗ trợ.
management.metrics.distribution.percentiles-histogram.http.server.requests=true
```

Trong demo chỉ có Spring MVC synchronous request handling. Nếu thêm Spring Security, phải bảo vệ actuator endpoints theo `SecurityFilterChain`. Nếu chạy test trên random port, `server.port=8080` được `@SpringBootTest(RANDOM_PORT)` override theo integration test config của Spring Boot.

### 11.4. Main class

**`src/main/java/com/example/demo/PerformanceApplication.java`**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PerformanceApplication {
    public static void main(String[] args) {
        SpringApplication.run(PerformanceApplication.class, args);
    }
}
```

### 11.5. Đo đồng thời bên trong filter synchronous

**`src/main/java/com/example/demo/RequestConcurrencyFilter.java`**

```java
package com.example.demo;

import java.io.IOException;
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.core.instrument.MeterRegistry;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class RequestConcurrencyFilter extends OncePerRequestFilter {

    private final AtomicInteger active = new AtomicInteger();
    private final AtomicInteger peak = new AtomicInteger();

    public RequestConcurrencyFilter(MeterRegistry registry) {
        // Registry dùng reference tới AtomicInteger mà bean đang sở hữu.
        registry.gauge("demo.requests.active", active);
        registry.gauge("demo.requests.peak", peak);
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        int now = active.incrementAndGet();
        peak.accumulateAndGet(now, Math::max);

        try {
            chain.doFilter(request, response);
        } finally {
            active.decrementAndGet();
        }
    }

    public int active() {
        return active.get();
    }

    public int peak() {
        return peak.get();
    }
}
```

**Ý nghĩa và giới hạn quan trọng:**

1. `AtomicInteger` bảo đảm việc tăng/giảm đếm an toàn khi nhiều Servlet threads cùng thực thi. Bộ đếm tồn tại trong singleton bean.
2. `finally` giảm counter kể cả khi controller throw exception; tránh “leak” do quên decrement. Không nắm `AtomicInteger` làm primitive bảo vệ nghiệp vụ: đây chỉ là **quan sát**.
3. `peak.accumulateAndGet(now, Math::max)` lưu peak từ lúc khởi động process, **không tự reset theo 1 phút**.
4. `MeterRegistry.gauge(...)` xuất snapshot; gauge có thể được scrape **khi request đang chạy**, nên không chắc thấy mọi đỉnh thoáng qua.
5. Filter tính số request đang ở **phạm vi filter chain đồng bộ**. Nó **không đo** thời gian chờ ở client/proxy/accept queue trước khi filter.
6. Với `Callable`, `DeferredResult`, `StreamingResponseBody` hay SSE, `chain.doFilter` có thể return sớm hơn HTTP completion. Đây **không phải** bộ đếm completion-aware phù hợp cho mọi async workloads.
7. `@Component` đăng ký filter với container; nếu nhiều filters và Spring Security, order ảnh hưởng requests nào được tính. Không tuyên bố gauge này bao phủ cả request bị gateway/WAF từ chối.
8. Khi chính `/demo/resources` hoặc `/actuator/metrics` được gọi, **request đo metrics cũng được tính vào active**. Số đọc có thể là 1 ngay cả khi không có request khác; không coi đó là leak.
9. Tăng concurrency của request không đồng nghĩa tăng `active` mãi: nếu requests kết thúc rất nhanh giữa hai lần scrape, gauge có thể thấp; đo với histograms/queue metrics bổ sung.

### 11.6. Controller mô phỏng CPU và wait latency

**`src/main/java/com/example/demo/PerformanceController.java`**

```java
package com.example.demo;

import java.lang.management.ManagementFactory;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/demo")
public class PerformanceController {

    private final RequestConcurrencyFilter concurrency;

    public PerformanceController(RequestConcurrencyFilter concurrency) {
        this.concurrency = concurrency;
    }

    @GetMapping("/wait")
    public Map<String, Object> waitForIo(
            @RequestParam(defaultValue = "100") long ms) {

        if (ms < 0 || ms > 2000) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "ms must be 0..2000"
            );
        }

        // Chỉ mô phỏng blocking wait, không làm như vậy trong production.
        try {
            Thread.sleep(ms);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new ResponseStatusException(
                HttpStatus.SERVICE_UNAVAILABLE,
                "Interrupted",
                ex
            );
        }

        return Map.of("kind", "wait", "delayMs", ms);
    }

    @GetMapping("/cpu")
    public Map<String, Object> cpuWork(
            @RequestParam(defaultValue = "100000") int iterations) {

        if (iterations < 1000 || iterations > 300000) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST, "iterations must be 1000..300000"
            );
        }

        long checksum = 0L;
        for (int i = 1; i <= iterations; i++) {
            checksum += Math.round(Math.sqrt(i) * 1000.0);
        }

        return Map.of(
            "kind", "cpu",
            "iterations", iterations,
            "checksum", checksum
        );
    }

    @GetMapping("/resources")
    public Map<String, Object> resources() {
        Runtime runtime = Runtime.getRuntime();

        long heapUsed = runtime.totalMemory() - runtime.freeMemory();
        long heapMax = runtime.maxMemory();

        return Map.of(
            "activeFilterRequests", concurrency.active(),
            "peakFilterRequests", concurrency.peak(),
            "heapUsedBytes", heapUsed,
            "heapMaxBytes", heapMax,
            "liveJvmThreads",
                ManagementFactory.getThreadMXBean().getThreadCount(),
            "availableProcessors", runtime.availableProcessors()
        );
    }
}
```

**Giải thích chính xác:**

- `/wait` dùng `Thread.sleep` để tạo **latency do chờ** mà không chủ động tính toán CPU. Với MVC blocking, mỗi request đang sleep có thể giữ worker thread; đây **không phải ví dụ code I/O production** và không nên dùng trong WebFlux event loop.
- `/cpu` dùng vòng lặp tính toán để minh họa CPU-bound work. Không phải bộ benchmark tính FLOPS hay phép đo công suất CPU chuẩn: JIT, Turbo Boost, GC và warm-up thay đổi thời gian chạy; hãy đo throughput/p95 thay vì lấy iterations làm đơn vị CPU.
- Cả hai endpoint giới hạn input để tránh người dùng bên ngoài yêu cầu sleep rất dài hoặc CPU loop vô hạn. Dù vậy **chỉ chạy demo ở localhost/private test environment**.
- `resources()` là một **snapshot**. `heapUsedBytes` là heap used gần đúng tại thời điểm gọi, không phải process RSS/cgroup memory; `heapMaxBytes` không phải bộ nhớ máy vật lý. `liveJvmThreads` không đếm WebFlux requests hay virtual-thread tasks một cách tương đương.
- `availableProcessors` là thông tin capacity mà JVM nhìn thấy, **không phải CPU utilization**. Muốn đo actual CPU %, dùng Micrometer/process/cgroup metrics ngoài endpoint này.
- `Map.of` không bảo đảm thứ tự keys JSON. Tests nên parse fields, không so sánh thứ tự chuỗi.
- Khi client gọi `/demo/resources`, filter đã tăng `active` cho request này; giá trị 1 là hành vi bình thường trong trạng thái nhàn rỗi.

## 12. Chạy và quan sát metrics

### 12.1. Khởi động

Với JDK 17+ và Maven:

```bash
java -version
mvn spring-boot:run
```

Hoặc `./mvnw spring-boot:run` nếu project có Maven Wrapper (Windows: `mvnw.cmd spring-boot:run`). Port 8080 phải còn trống. Cấu hình đã bật `/actuator/metrics` **cho local demo**, không bật public Internet tương tự khi triển khai thực.

### 12.2. Baseline request

```bash
curl -i "http://localhost:8080/demo/wait?ms=100"
curl -i "http://localhost:8080/demo/cpu?iterations=100000"
curl -i "http://localhost:8080/demo/resources"
```

Phản hồi mẫu của `/wait`:

```json
{"kind":"wait","delayMs":100}
```

Phản hồi mẫu `/resources` có cấu trúc như:

```json
{
  "activeFilterRequests": 1,
  "peakFilterRequests": 1,
  "heapUsedBytes": 24780000,
  "heapMaxBytes": 1073741824,
  "liveJvmThreads": 32,
  "availableProcessors": 4
}
```

Đó là **số minh họa**, không phải output tất định: peak/heap/thread/processors tùy tải, JVM và container. Chỉ keys, types và semantics được giải thích là contract của code mẫu; thứ tự JSON thay đổi.

### 12.3. Đo thời gian phía curl

```bash
curl -sS -o /dev/null \
  -w 'http=%{http_code} ttfb=%{time_starttransfer}s total=%{time_total}s\n' \
  "http://localhost:8080/demo/wait?ms=100"
```

`time_starttransfer` là client-observed TTFB, `time_total` là tổng thời gian request theo curl. Với body JSON nhỏ, hai số có thể gần nhau nhưng **không chắc bằng nhau**. Chúng bao gồm các yếu tố ở curl/HTTP/network và không bằng thời gian `Thread.sleep` chính xác 100 ms.

Nếu dùng PowerShell, gọi `curl.exe` để tránh alias khác cú pháp.

### 12.4. Đọc HTTP metrics từ Actuator

```bash
curl -sS "http://localhost:8080/actuator/metrics"
curl -sS "http://localhost:8080/actuator/metrics/http.server.requests"
curl -sS "http://localhost:8080/actuator/metrics/demo.requests.active"
curl -sS "http://localhost:8080/actuator/metrics/demo.requests.peak"
```

Sau khi ít nhất một request được xử lý và observation đã hoàn tất, `http.server.requests` thường có measurements như **COUNT, TOTAL_TIME, MAX** và tags `method`, `status`, `uri`, `outcome` theo framework. Count là **tổng được tích lũy** trong meter, không là instantaneous RPS; total time thường dùng seconds (kiểm tra `baseUnit` của meter). HTTP server timing không bao gồm toàn bộ DNS/TLS ở client.

Có thể lọc route/tag:

```bash
curl -sS \
  "http://localhost:8080/actuator/metrics/http.server.requests?tag=uri:/demo/wait"
```

Tên `uri` là path template được framework ghi nhận; xác nhận `availableTags` qua response thực trước khi đưa query vào dashboard.

Với `/actuator/metrics/demo.requests.active`, giá trị có thể là 1 vì **request đọc metrics** đang đi qua filter. Metric gauge không có quan hệ 1:1 với Tomcat busy threads, và tại một thời điểm có thể bỏ lỡ những peaks giữa các scrape.

### 12.5. Đọc Tomcat/JVM metrics

```bash
curl -sS "http://localhost:8080/actuator/metrics/jvm.memory.used"
curl -sS "http://localhost:8080/actuator/metrics/jvm.threads.live"
curl -sS "http://localhost:8080/actuator/metrics/process.cpu.usage"
curl -sS "http://localhost:8080/actuator/metrics/tomcat.threads.busy"
```

Nếu một tên không xuất hiện, **đừng tự suy hệ thống không dùng CPU hoặc không có threads**. Meter có thể phụ thuộc environment, MBean registration, classpath, binder và Spring Boot version; kiểm tra list tên trước. Memory metrics có tags cho heap/nonheap và memory pool; process CPU usage có mẫu số theo process/JVM semantics, còn cgroup throttling cần quan sát từ container metrics.

## 13. Tạo tải có giới hạn và tính throughput từ client

**Không dùng load test trên endpoint doanh nghiệp/public Internet nếu chưa được phép.** Các thí nghiệm bên dưới dành cho **localhost hoặc staging đã được chủ sở hữu cho phép**, có giới hạn số requests và concurrency.

### 13.1. Kiểm tra thủ công bằng một đợt requests

Trên Bash/Linux/macOS có `xargs -P`:

```bash
seq 1 20 | xargs -P 5 -I {} sh -c \
  'curl -sS -o /dev/null "http://localhost:8080/demo/wait?ms=100"'
```

Có tối đa khoảng 5 tiến trình curl đang gửi requests trong một lúc, tổng 20 requests. Tuy nhiên mỗi lần curl là một process/client riêng, tự tạo connections và có overhead; **không coi phép đo này là benchmark throughput chuẩn**.

Một request sleep 100 ms, 20 requests qua 5 slots lý tưởng có 4 waves (khoảng 400 ms cho sleep), nhưng tổng thời gian thực còn network, queue, JVM scheduling, TLS/proxy nếu có. Không assert 400 ms là kết quả cố định.

### 13.2. LoadProbe Java 17: chia workload vào số workers giới hạn

Thêm file **`LoadProbe.java`** ở thư mục riêng hoặc root; nó dùng JDK `HttpClient` **một instance dùng chung**, một fixed-size executor và gửi **tổng số request hữu hạn**. Code không phụ thuộc Spring, chạy được với Java 17+. Nó đo client-wall time, per-request completed latency và tỉ lệ status, nhưng là **closed-loop load generator** (worker chỉ gửi request mới sau khi hoàn tất request trước), nên có giới hạn về việc tìm capacity thực.

**`LoadProbe.java`**

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class LoadProbe {

    record Sample(int status, double durationMs) {}

    private static Sample call(HttpClient client, URI url)
            throws Exception {
        HttpRequest request = HttpRequest.newBuilder(url)
            .timeout(Duration.ofSeconds(5))
            .GET()
            .build();

        long begin = System.nanoTime();
        HttpResponse<byte[]> response = client.send(
            request, HttpResponse.BodyHandlers.ofByteArray()
        );

        double elapsedMs = (System.nanoTime() - begin) / 1_000_000.0;
        return new Sample(response.statusCode(), elapsedMs);
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            System.err.println(
                "Usage: java LoadProbe <url> <totalRequests> <workers>"
            );
            return;
        }

        URI url = URI.create(args[0]);
        int total = Integer.parseInt(args[1]);
        int workers = Integer.parseInt(args[2]);

        if (total < 1 || total > 500 || workers < 1 || workers > 50) {
            throw new IllegalArgumentException(
                "Use 1..500 totalRequests and 1..50 workers"
            );
        }

        HttpClient client = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_1_1)
            .connectTimeout(Duration.ofSeconds(2))
            .build();

        ExecutorService executor = Executors.newFixedThreadPool(workers);
        List<Future<Sample>> jobs = new ArrayList<>();
        long wallStart = System.nanoTime();

        try {
            for (int i = 0; i < total; i++) {
                jobs.add(executor.submit(() -> call(client, url)));
            }

            List<Double> latenciesMs = new ArrayList<>();
            int success = 0;
            int errors = 0;

            for (Future<Sample> job : jobs) {
                Sample sample = job.get();
                latenciesMs.add(sample.durationMs());

                if (sample.status() >= 200 && sample.status() < 300) {
                    success++;
                } else {
                    errors++;
                }
            }

            double wallSeconds =
                (System.nanoTime() - wallStart) / 1_000_000_000.0;

            Collections.sort(latenciesMs);
            double mean = latenciesMs.stream()
                .mapToDouble(Double::doubleValue)
                .average()
                .orElse(0.0);

            // Nearest-rank p95 cho sample hữu hạn; các tool khác
            // có thể dùng interpolation/histogram estimates.
            int p95Index =
                (int) Math.ceil(0.95 * latenciesMs.size()) - 1;
            double p95 = latenciesMs.get(p95Index);

            System.out.printf(
                Locale.ROOT,
                "done=%d success=%d errors=%d " +
                "wall=%.3fs throughput=%.2fRPS " +
                "mean=%.2fms p95=%.2fms%n",
                total,
                success,
                errors,
                wallSeconds,
                total / wallSeconds,
                mean,
                p95
            );
        } finally {
            executor.shutdownNow();
            executor.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
```

Chạy:

```bash
javac LoadProbe.java
java LoadProbe "http://localhost:8080/demo/wait?ms=100" 50 1
java LoadProbe "http://localhost:8080/demo/wait?ms=100" 50 5
java LoadProbe "http://localhost:8080/demo/wait?ms=100" 50 20
java LoadProbe "http://localhost:8080/demo/cpu?iterations=300000" 50 5
```

Ví dụ một dòng output **chỉ minh họa hình dạng**, **không phải số đo cố định**:

```text
done=50 success=50 errors=0 wall=1.150s throughput=43.48RPS mean=110.10ms p95=130.00ms
```

**Các con số sẽ khác trên từng máy.** Không kỳ vọng có đúng 43,48 RPS/110,10 ms sau khi chạy. Giá trị RPS trong code là **completed requests / wall seconds** của batch gồm 50 requests. Nó có thể bao gồm thời gian tạo threads/warmup và không là **steady-state RPS** của server. `mean`/`p95` là latency của các HTTP exchanges đo từ client, không bao gồm thời gian Future chờ trong executor **trước khi request bắt đầu** (tức queue trong máy phát tải).

**Những giới hạn của LoadProbe này:**

1. Đây là **closed-loop**: fixed number of worker threads chờ response rồi tiếp tục. Nếu server chậm đi, arrival rate tự giảm; điều đó có thể tạo **coordinated omission** khi đánh giá tail latency so với hệ thống có arrivals theo lịch.
2. Nó đợi kết quả từng Future, nhưng tất cả tasks đã submit trong executor. Throughput theo wall time gồm cả queue của load generator; latency chỉ tính từ khi task thực sự bắt đầu gửi. Hai boundary khác nhau.
3. Dùng `BodyHandlers.ofByteArray()` để **consume toàn bộ body** trước khi tính response complete; phù hợp với JSON nhỏ nhưng không dành cho file tải hàng GB.
4. Max 500 requests và 50 workers chỉ là guardrails local; không biến phép thử này thành capacity test có ramp-up ổn định.
5. Không khẳng định Java HttpClient sẽ dùng đúng một TCP connection; client dùng chung có thể mở nhiều sockets.
6. Nếu một future thất bại vì exception/timeout, code mẫu sẽ throw và không xuất summary success/error đầy đủ. Với load generator production cần ghi errors/timeouts riêng trong từng sample; demo này cố ý giữ ngắn gọn và dùng trong môi trường ổn định.
7. Client và server cùng host chia sẻ CPU/network; máy phát tải có thể là bottleneck. Đo CPU của cả hai hoặc chạy load generator riêng ở môi trường kiểm soát.
8. Không gửi credential thật, không in token hay payload cá nhân; chỉ dùng URL local đã được phép.

### 13.3. Bảng quan sát nên tự điền

Khi chạy từng mức workers, ghi lại:

| Workload | Workers | Offered/completed RPS | Mean | p95/p99 | Active/peak | CPU/quota | Threads/queue | Errors |
| --- | ---: | ---: | --- | --- | --- | --- | --- | --- |
| wait 100 ms | 1 | *đo* | *đo* | *đo* | *đo* | *đo* | *đo* | *đo* |
| wait 100 ms | 5 | *đo* | *đo* | *đo* | *đo* | *đo* | *đo* | *đo* |
| wait 100 ms | 20 | *đo* | *đo* | *đo* | *đo* | *đo* | *đo* | *đo* |
| CPU 300000 | 5 | *đo* | *đo* | *đo* | *đo* | *đo* | *đo* | *đo* |

Trong bảng trên, *đo* nghĩa là **người học tự thu thập**; không phải giá trị đã có. LoadProbe không trực tiếp đo **p99, CPU/quota hay threads/queue**; các cột ấy phải lấy thêm từ Actuator/monitoring container và một công cụ metrics phù hợp. Không tự điền những con số từ stdout mà công cụ chưa xuất.

## 14. Kiểm thử tích hợp HTTP thật

Thêm một test class để xác nhận API, validation, metrics và concurrency basic. `@SpringBootTest(RANDOM_PORT)` mở **embedded Tomcat thật** trên cổng ngẫu nhiên, không dùng MockMvc để giả lập connector. Vì vậy test kiểm tra request qua HTTP stack thực, không chỉ gọi controller Java.

**`src/test/java/com/example/demo/PerformanceApplicationTest.java`**

```java
package com.example.demo;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.stream.IntStream;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PerformanceApplicationTest {

    @LocalServerPort
    int port;

    private final HttpClient client = HttpClient.newHttpClient();
    private final ObjectMapper json = new ObjectMapper();

    private URI uri(String path) {
        return URI.create("http://127.0.0.1:" + port + path);
    }

    private HttpRequest request(String path) {
        return HttpRequest.newBuilder(uri(path)).GET().build();
    }

    private HttpResponse<String> get(String path) throws Exception {
        return client.send(
            request(path), HttpResponse.BodyHandlers.ofString()
        );
    }

    @Test
    void waitReturnsExpectedPayload() throws Exception {
        HttpResponse<String> response = get("/demo/wait?ms=50");

        assertEquals(200, response.statusCode());
        JsonNode payload = json.readTree(response.body());
        assertEquals("wait", payload.get("kind").asText());
        assertEquals(50, payload.get("delayMs").asLong());
    }

    @Test
    void invalidWaitIsRejected() throws Exception {
        assertEquals(
            400,
            get("/demo/wait?ms=2001").statusCode()
        );
    }

    @Test
    void cpuEndpointReturnsPositiveChecksum() throws Exception {
        HttpResponse<String> response =
            get("/demo/cpu?iterations=1000");

        assertEquals(200, response.statusCode());
        JsonNode payload = json.readTree(response.body());
        assertEquals("cpu", payload.get("kind").asText());
        assertTrue(payload.get("checksum").asLong() > 0L);
    }

    @Test
    void resourcesExposeSnapshotsNotCpuPercent() throws Exception {
        HttpResponse<String> response = get("/demo/resources");

        assertEquals(200, response.statusCode());
        JsonNode payload = json.readTree(response.body());

        assertTrue(payload.get("activeFilterRequests").asInt() >= 1);
        assertTrue(payload.get("heapUsedBytes").asLong() > 0);
        assertTrue(payload.get("availableProcessors").asInt() > 0);
        assertTrue(payload.get("liveJvmThreads").asInt() > 0);
    }

    @Test
    void actuatorExposesHttpServerRequestTimer() throws Exception {
        // Bảo đảm đã có ít nhất một observation của MVC.
        get("/demo/wait?ms=1");

        HttpResponse<String> response =
            get("/actuator/metrics/http.server.requests");

        assertEquals(200, response.statusCode());
        JsonNode payload = json.readTree(response.body());
        assertEquals(
            "http.server.requests",
            payload.get("name").asText()
        );
        assertTrue(payload.get("measurements").isArray());
    }

    @Test
    void concurrentRequestsAllComplete() {
        List<CompletableFuture<HttpResponse<String>>> calls =
            IntStream.range(0, 8)
                .mapToObj(i -> client.sendAsync(
                    request("/demo/wait?ms=100"),
                    HttpResponse.BodyHandlers.ofString()
                ))
                .toList();

        CompletableFuture.allOf(
            calls.toArray(CompletableFuture[]::new)
        ).join();

        for (CompletableFuture<HttpResponse<String>> call : calls) {
            assertEquals(200, call.join().statusCode());
        }
    }
}
```

Chạy:

```bash
mvn test
```

Nếu có Maven Wrapper dùng `./mvnw test` hoặc Windows `mvnw.cmd test`. **Sáu tests được kỳ vọng pass** với đúng files/dependencies và môi trường local phù hợp. Đây là **kết quả dự kiến**, không phải lời khẳng định đã chạy test trên repository nào.

Test kiểm chứng:

- HTTP endpoint `wait`, `cpu` và validation trả status/body đúng.
- Resource snapshot có các trường với giá trị hợp lý, không khẳng định CPU %.
- Actuator HTTP request timer tồn tại sau request thực sự.
- Tám requests HTTP đồng thời đều hoàn tất ở tải nhỏ.

Test **không** chứng minh:

- Server có throughput tối đa bao nhiêu RPS hay latency p99 dưới SLO.
- CPU đang 50% hay 95%.
- Concurrency peak chính xác là 8: scheduler và client connection selection có thể làm overlap khác nhau.
- Không có queueing dưới tải production hoặc backend đủ capacity.
- CORS/TLS/proxy/CDN, nhiều replicas hay WebFlux behavior.
- JVM warm-up, GC, load generator overhead và histogram aggregation có cấu hình production-like.

Để kiểm thử hiệu năng có ý nghĩa, cần **một thí nghiệm có công cụ và thống kê riêng**, không gán nhãn “performance tested” chỉ vì functional integration tests xanh.

## 15. Thiết kế thí nghiệm hiệu năng công bằng

### 15.1. Xác định workload và SLO

Trước khi bấm chạy load tool, cố định:

- Tỷ lệ endpoints GET/POST, read/write và phân phối traffic.
- Payload size và response size (1 KB vs 5 MB tạo giới hạn hoàn toàn khác).
- Authentication/cookie, TLS, HTTP/1.1 vs HTTP/2, keep-alive, compression.
- Tỷ lệ cache hit/miss, DB data volume/indexes và số dependencies.
- Số replicas, CPU/memory limits, JVM heap, GC, DB/HTTP pool configs.
- Tốc độ arrival theo user simulation (open-loop) hay fixed concurrent users (closed-loop).
- Khoảng warm-up JVM/JIT, sampling length, ramp-up, cool-down, repeatability.
- Mục tiêu: ví dụ `200 successful RPS, p95 < 250ms, errors < 0.5%` ở workload được mô tả cụ thể.

**Không chạy destructive load test trên production khi chưa được phê duyệt**; dùng staging có dữ liệu giả hoặc production canary với budget/bảo vệ đã được chủ sở hữu chấp thuận.

### 15.2. Tăng tải theo bậc

Ví dụ các bậc đồng thời ở môi trường cho phép:

```text
C=1 -> C=5 -> C=10 -> C=20 -> C=40
  warm-up, giữ tải đủ thời gian, thu metrics từng bước
```

Ghi lại:

- Completed RPS, successful/goodput RPS, 2xx/4xx/5xx/429, timeouts.
- Mean/p50/p95/p99 latency, max, request duration histograms.
- In-flight average/peak, Tomcat busy threads, pending outbound pool.
- CPU % so với quota, throttling, memory/GC, network/disk.
- p95 của downstream DB/HTTP, circuit breaker, queue wait.
- Số replicas, configurations, version commit/deploy để so sánh.

Quan sát “knee” của curve: khi tăng arrival/concurrency mà throughput gần không tăng, trong khi p95/p99, error rate hoặc CPU/queue tăng vọt, rất có thể đã chạm saturation. Điểm tối ưu thực tế thường **trước** saturation peak và còn headroom cho bursts/failover.

### 15.3. Tránh coordinated omission

Nếu load generator kiểu **closed-loop** chỉ gửi request mới khi request trước kết thúc, khi server bắt đầu chậm, **arrival rate giảm theo**. Các khoảng thời gian mà user thật lẽ ra vẫn gửi request mới có thể bị “bỏ sót” khỏi latency distribution; p99 trông đẹp hơn overload thực.

Đối với mục tiêu arrival-rate SLO:

- Dùng công cụ open-loop/constant-arrival-rate có khả năng lên lịch request **độc lập response completion**.
- Đảm bảo load generator đủ năng lực; nếu không gửi kịp arrival target, ghi rõ `dropped/scheduled/delayed` requests.
- Ghi planned arrival timestamp, actual send timestamp và completion timestamp; đánh giá request delay/queue phù hợp.
- Theo dõi client-side queue và transport limits để không lẫn bottleneck generator với server.
- Dùng latency histograms/analysis phù hợp với công cụ đã chọn; nếu histogram correction được áp dụng phải mô tả phương pháp, không quảng cáo kết quả như raw latency.
- Với closed-loop benchmark, vẫn dùng được để nghiên cứu concurrency, nhưng **không tự suy ra** phục vụ constant-arrival 1.000 RPS sẽ ổn.

### 15.4. Warm-up và nhiễu

Java có JIT compilation, class loading, connection pool warm-up, caches, GC cycles. Kết quả vài giây đầu có thể khác steady-state. Hãy:

1. Khởi động, làm ấm app và downstream một cách có kiểm soát.
2. Đo baseline idle resource sử dụng.
3. Tăng tải theo bậc, ổn định trước khi lấy số.
4. Thu dữ liệu ở cùng thời gian và cùng time zone/clock sync.
5. Lặp lại thí nghiệm, báo phân phối giữa runs, không chọn một lần đẹp nhất.
6. Giữ nguyên app version, CPU/memory quota, DB dataset/cache state và traffic mix.
7. Tách load generator khỏi server khi cần, kiểm tra generator không saturate.
8. Ghi lại failures/timeouts/cancellation, không lọc chúng âm thầm khỏi thống kê.
9. Khi so sánh hai versions, chạy A/B xen kẽ hoặc trên môi trường tương đương để giảm khác biệt do thời điểm.

## 16. Chẩn đoán theo bộ triệu chứng

| Triệu chứng | Không nên suy ngay | Khả năng cần kiểm tra |
| --- | --- | --- |
| RPS giữ nguyên, p99 tăng | “Chỉ cần thêm users/threads” | Queueing, DB/HTTP pool saturation, CPU quota, GC |
| CPU thấp, in-flight cao | “App còn khỏe, tăng load tiếp” | Blocked I/O, downstream latency, executor queue |
| CPU cao, RPS không tăng | “CPU metrics sai” | CPU saturation, serialization, GC, hotspot, contention |
| Thread count tăng | “RPS phải tăng” | Thread-per-request blocked calls, thread leak, misconfigured executor |
| TCP connections cao | “Có rất nhiều active HTTP requests” | Idle keep-alive, HTTP/2, SSE/WebSocket, pool routing |
| Average 50 ms, p99 5 s | “API nhanh trung bình là đủ” | Tail latency, lock contention, GC pauses, noisy neighbors |
| 200 RPS gồm nhiều 503 | “Throughput đạt mục tiêu 200” | Goodput thấp, upstream failure, overload shedding |
| Heap dùng 80% | “Có memory leak” | Caches, GC allocation pressure, container memory limit, RSS |
| Client time lớn hơn app timer | “Spring đo sai” | Network/proxy/queue/response streaming, different boundaries |
| Actuator timer COUNT=10000 | “Hiện tại 10000 RPS” | Cumulative COUNT cần `rate` theo thời gian |
| Gauge active=1 khi app nhàn | “Một request bị leak” | Chính request đọc gauge cũng được đếm |
| Tăng threads.max mà p99 tệ hơn | “Cần tăng thêm nữa” | Thêm contention/queue downstream, CPU/memory |
| Nhiều 429 nhưng latency thấp | “SLO latency rất tốt” | Requests bị shed/không thành công; cần goodput/error SLO |
| Autoscale tăng replicas mà DB quá tải | “Autoscaling bị lỗi” | Downstream shared bottleneck, fan-out/retry amplification |
| p95 trung bình qua các pods thấp | “Global p95 đạt SLO” | Percentile không cộng/gộp bằng trung bình đơn giản |
| CPU usage 30% nhưng throttling | “CPU quota còn thừa” | Đo usage/quota và cgroup throttling thật, time slices |
| Async controller trả nhanh | “Response tới client nhanh” | Async completion, streaming, backpressure, client download |

## 17. Lưu ý bảo mật và vận hành khi đo hiệu năng

- **Không công khai** `/actuator/metrics`, `/actuator/threaddump`, `/actuator/heapdump` hoặc exporter không kiểm soát; thông tin runtime có thể giúp attacker lập bản đồ hệ thống.
- Không gắn user ID, full path có token, raw query hoặc session ID thành **metric labels** có cardinality cao. Dùng `uri` route template, method, status, service/env/version ổn định.
- Đừng ghi full HTTP request/response body hoặc Authorization/Cookie chỉ để kiểm tra latency; logging đó có thể tăng memory, I/O và rủi ro lộ PII.
- Hạn chế load test vào môi trường được phê duyệt, giới hạn tốc độ/thời gian, dùng test data, có plan rollback và quan sát downstream.
- Khi traffic tăng, đừng bật DEBUG/TRACE toàn framework vì có thể làm sai performance results và log secrets.
- Phân biệt performance debugging với **stress test gây gián đoạn**; không tự bắn lưu lượng lớn tới hạ tầng sản xuất.
- Đo endpoint latency cùng authorization/tenant checks, đừng tối ưu bằng cách bỏ security filters hoặc validation.
- Với proxy, tin cậy forwarded headers chỉ từ trusted edge; metrics theo client IP/host bị spoof có thể gây sai rate limiting và privacy issues.
- Cấu hình timeout, max request body, max HTTP connections và pool quotas có liên hệ với DoS resilience; nhưng mỗi limit phải gắn với SLA và test tương ứng.

## 18. Checklist trước khi đưa ra kết luận “hệ thống chịu được X RPS”

- [ ] Định nghĩa rõ **offered load**, **completed throughput**, **successful/goodput RPS**, HTTP status mix và window.
- [ ] Đo latency ở cùng boundary, có **mean/p50/p95/p99/max** và số samples.
- [ ] Không trộn p95/p99 vào Little's Law; chỉ dùng `L=λW` với **mean W** và hệ thống gần steady state.
- [ ] Có in-flight/peak metric và hiểu phạm vi đếm (sync filter, async lifetime, proxy).
- [ ] Có CPU/quota/throttling, heap/non-heap/RSS, GC, threads, connections, pool pending và downstream latency.
- [ ] Tomcat `threads.max`, `max-connections`, `accept-count` được hiểu là ba giới hạn khác nhau.
- [ ] Có load test warm-up, ramp, steady window, multiple runs, thống kê confidence và repeatability.
- [ ] Phân biệt closed-loop concurrency và open-loop arrival rate; đánh giá coordinated omission.
- [ ] Tham số request/payload mix, cache hit, TLS, auth, network, proxy, HTTP version và keep-alive giống thực tế.
- [ ] Đã kiểm tra capacity của **load generator** và downstream, không chỉ Spring Boot process.
- [ ] Histogram percentile được gộp đúng từ buckets, không trung bình p95 qua replicas.
- [ ] Có SLO latency **và** success/error rate, không tối ưu thành các fast 429/503.
- [ ] Có headroom cho bursts, replicas failover và GC; không chạy sát 100% utilization liên tục.
- [ ] Đã xác nhận Actuator/metrics không public và tags không chứa PII, secrets hoặc per-user IDs.
- [ ] Không dùng một vài GET local hoặc 6 functional tests để chứng minh capacity production.
- [ ] Tài liệu kết quả ghi app version, infra limits, dates/time window, dataset, test scripts và các caveats.

## 19. Câu hỏi tự kiểm tra

**1. Throughput và số requests in-flight có phải cùng một đại lượng không?**  
Không. RPS là số request hoàn tất trong một giây; in-flight là số request đang mở ở một thời điểm.

**2. Nếu λ=80 RPS và mean response time=0,5 giây, average in-flight gần đúng bằng bao nhiêu?**  
Theo Little's Law ở steady state: `L=80×0,5=40 requests`.

**3. Có thể lấy λ×p99 để tính average in-flight không?**  
Không. Little's Law dùng **mean W**, không dùng p99.

**4. Khi CPU chỉ 15% nhưng 500 requests đang chờ thì hệ thống chắc chắn còn dư khả năng phục vụ?**  
Không. Có thể request bị giữ do I/O, DB pool, remote service, proxy và queue.

**5. Mở 200 TCP connections nghĩa là có 200 HTTP requests đồng thời?**  
Không. Idle keep-alive, HTTP/2 multiplexing và long-lived connections làm số liệu khác nhau.

**6. Tăng `server.tomcat.threads.max` từ 40 lên 400 có làm RPS tăng 10 lần?**  
Không. CPU, downstream quotas/latency, pool, memory và queue có thể là bottleneck.

**7. `http.server.requests` có COUNT=5000, đây có phải 5000 RPS không?**  
Không. COUNT tích lũy; phải lấy chênh lệch theo thời gian hoặc `rate`.

**8. Khi client p95=300ms và server p95=100ms, có chắc network p95=200ms?**  
Không. Percentile không trừ như trung bình và hai tập request/measurement boundaries có thể khác.

**9. Tại sao HTTP 429 nhanh có thể làm throughput tổng trông đẹp?**  
Vì server trả nhiều response nhanh nhưng goodput thành công thấp; cần status mix/error SLO.

**10. `Runtime.availableProcessors()` là chỉ số CPU usage?**  
Không. Nó phản ánh processors mà JVM thấy, không đo CPU thực đang tiêu thụ.

**11. Đo `active` bằng OncePerRequestFilter có bao phủ SSE kéo dài không?**  
Không nhất thiết. Filter chain có thể return sớm khi Servlet async bắt đầu; cần completion-aware instrumentation.

**12. Vì sao cần histogram để có p95 tổng trên nhiều pods?**  
Vì percentile không cộng hay trung bình được; cần aggregate buckets/samples thống nhất.

**13. Closed-loop load generator có thể đánh giá thấp tail latency khi overload không?**  
Có. Khi response chậm, nó phát request mới chậm hơn, dẫn đến coordinated omission.

**14. `server.tomcat.max-connections`, `threads.max` và `accept-count` có giống nhau không?**  
Không. Chúng liên quan connections, worker threads và incoming connection backlog theo các semantics khác nhau.

**15. Đạt 100 RPS với p99=10 giây và 20% lỗi có phải “chịu được 100 RPS” theo SLA?**  
Chỉ có thể nói hoàn tất tổng 100 responses/s. Muốn khẳng định capacity theo SLA phải kiểm tra goodput, errors và tail latency theo yêu cầu.

**16. Có thể dùng metrics `/demo/resources` để xác định memory leak trong 1 request không?**  
Không. Đó là snapshot; memory leak cần quan sát xu hướng, GC, heap dump/profiling được phép và context về cache/load.

**17. Vì sao Java 21 virtual threads không loại bỏ nhu cầu bulkhead và DB pool?**  
Chúng giảm chi phí giữ threads khi chờ nhưng không tạo thêm CPU, DB connections hay downstream capacity.

**18. Khi latency giảm nhưng throughput vẫn giữ nguyên thì chắc chắn hệ thống tốt hơn?**  
Không đủ kết luận. Phải kiểm tra traffic mix, error rate, client/gateway queue, resource utilization và SLO. Nhưng nếu cùng workload và success rate, latency giảm thường là tín hiệu tích cực.

## 20. Tài liệu chính thức và hướng học tiếp

- Spring Boot 3.5 — **Common Application Properties**, gồm `server.tomcat.threads.max`, `server.tomcat.max-connections`, `server.tomcat.accept-count` và `server.tomcat.mbeanregistry.enabled`: https://docs.spring.io/spring-boot/3.5/appendix/application-properties/
- Spring Boot — **Actuator Metrics**, HTTP server `http.server.requests`, Tomcat and JVM metrics, per-meter histograms: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- Spring Boot 3.5 — **Actuator Metrics Endpoint API**: https://docs.spring.io/spring-boot/3.5/api/rest/actuator/metrics.html
- Spring Boot — **Actuator Endpoints and Exposure Security**: https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html
- Spring Framework — **Asynchronous Requests in Spring MVC**, `Callable`, `DeferredResult`, `StreamingResponseBody`, thread/IO semantics: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-async.html
- Spring Framework — **WebFlux vs MVC**: https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html
- Micrometer — **Timers**, COUNT/TOTAL_TIME/MAX and percentile histograms: https://docs.micrometer.io/micrometer/reference/concepts/timers.html
- Micrometer — **Histograms and Percentiles**: https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html
- Prometheus — **Histograms and Summaries**: https://prometheus.io/docs/practices/histograms/
- Prometheus — **Querying Functions** (`rate`, `histogram_quantile`): https://prometheus.io/docs/prometheus/latest/querying/functions/
- OpenTelemetry — **Metrics Concepts**: https://opentelemetry.io/docs/concepts/signals/metrics/
- Spring Boot 3.5.16 — **Release, End of OSS Support**: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/

**Kết luận:** trong Spring Boot web runtime, **thông lượng** đo số request hoàn tất/giây; **độ trễ** đo thời gian của từng request và cả phân phối p50/p95/p99; **đồng thời** đo số request chưa kết thúc; **mức sử dụng tài nguyên** đo CPU/memory/threads/connections/queues so với giới hạn thật. Chúng liên hệ qua Little's Law khi đo đúng boundary và steady state, nhưng không thể thay thế nhau. Khi tải tăng gần saturation, queue và tail latency có thể tăng mạnh dù RPS dừng tăng. Hãy đo đồng thời **RPS + goodput + tail latency + in-flight + CPU/quota + pool queues + errors**, kiểm thử theo workload có kiểm soát và đánh giá theo SLO chứ không chỉ một con số benchmark.