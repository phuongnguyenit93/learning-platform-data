# 18.9 Kiểm chứng thay đổi bằng phân bố độ trễ và số thao tác thành công dưới cùng tải

## 1. Mục tiêu của bài

Sau khi chỉnh code I/O, connection pool, batching, asynchronous execution, buffer size, cache hoặc timeout, một số đo trung bình đẹp hơn **không đủ chứng minh hệ thống tốt hơn**. Thay đổi có thể giảm thời gian của các thao tác thành công nhưng đồng thời làm tăng timeout, bỏ request hoặc trả sai dữ liệu. Để kết luận, cần đo **phân bố độ trễ** và **số thao tác thực sự thành công** với **cùng mức tải được yêu cầu**.

Sau bài này, bạn có thể:

1. Phân biệt **offered load**, issued rate, completed throughput, **goodput**, success rate, errors, timeouts, dropped và in-flight requests.
2. Đọc và so sánh **p50, p90, p95, p99, p99.9**, histogram/CDF, max, mean và tỷ lệ vượt deadline; hiểu giới hạn về sample size.
3. Thiết kế thử nghiệm A/B đúng: cùng workload, arrival rate, trạng thái cache, data size, tài nguyên, timeouts, điều kiện warm-up và cách định nghĩa success.
4. Tránh **coordinated omission** và sai lệch khi test closed-loop tự giảm tốc độ phát request lúc server chậm.
5. Đối chiếu client end-to-end latency với số liệu JVM, JFR SocketRead/SocketWrite/FileRead/FileWrite, queue, CPU/GC và metrics hệ điều hành.
6. Đặt tiêu chí **PASS / FAIL / INCONCLUSIVE** trước khi chạy, thay vì chỉ chọn chỉ số có lợi sau khi biết kết quả.

**Thông điệp cốt lõi:** thay đổi là cải thiện khi dưới **cùng tải có thể kiểm chứng**, số thao tác **đúng và thành công/giây** không bị đánh đổi lấy con số p95 đẹp, và tail latency cùng các guardrail đều đạt mục tiêu.

## 2. Định nghĩa thao tác, điểm đo và deadline

Trước phép thử, xác định **một operation** là gì: một HTTP request, một transaction nghiệp vụ, một database query, một lần đọc/ghi file, một batch hay một message được xác nhận. Nếu A báo throughput theo batch còn B theo row, hai giá trị không so sánh trực tiếp được.

Ví dụ thao tác HTTP gọi database:

~~~text
Load generator có kế hoạch phát request ở t0
        |
        +-- có thể trễ lịch hoặc dropped vì generator thiếu resources
        v
Client thực sự bắt đầu gửi request
        |
        +-- network / connection pool / TLS
        v
Server nhận request
        |
        +-- queue / thread scheduling / GC
        +-- application CPU / database / file / socket I/O
        v
Server hoàn tất response
        |
        +-- network / client decode / validate payload
        v
Client xác định SUCCESS / ERROR / TIMEOUT ở t1
~~~

Cần quyết định đo khoảng nào:

| Tên | Phạm vi | Mục đích |
| --- | --- | --- |
| **Client end-to-end** | Từ lúc client gửi đến nhận kết quả hoặc deadline | Trải nghiệm bên gọi |
| **Scheduled-to-completion** | Từ **thời điểm dự kiến** phát đến khi hoàn tất | Phản ánh queueing/missed schedule trong bài test arrival-rate |
| **Server request duration** | Khi server nhận đến khi hoàn tất theo instrumentation | Phân tích server, không gồm toàn bộ client network |
| **Downstream I/O duration** | Lúc code chờ đọc/ghi socket/file/database | Tìm thành phần gây chậm, không phải tổng request |
| **Queue wait** | Lúc enqueued đến lúc bắt đầu xử lý | Phát hiện backlog và giới hạn worker/pool |

**Không đối chiếu client p99 của A với server p99 của B.** Chúng đo khoảng khác nhau. Với Java, dùng **System.nanoTime()** và hiệu hai mốc để đo duration bên trong cùng process; System.currentTimeMillis() phù hợp với mốc wall-clock/log nhưng đồng hồ hệ thống có thể điều chỉnh.

Đặt **deadline** trước khi chạy, ví dụ 250 ms. Một operation timeout sau 250 ms là một **kết quả thất bại**, cần được đếm và lưu thời gian chờ tới timeout theo định nghĩa test. Không âm thầm xóa nó khỏi thống kê. Nếu request chưa được generator phát, đó là **dropped/not issued**, không phải một latency đã đo được.

Một HTTP 200 chỉ là thành công nếu **nội dung và hậu điều kiện nghiệp vụ** đúng. Một job ghi dữ liệu báo OK nhưng làm mất record, ghi trùng không hợp lệ hoặc chưa bền vững theo contract thì không tính là useful success.

## 3. Bộ đếm phải cân đối

Trong một cửa sổ test, ký hiệu:

- **P / planned**: số operation đã được lập lịch gửi.
- **I / issued**: số operation thực sự được phát đi.
- **D / dropped**: đã có lịch nhưng generator không phát được.
- **C / completed**: đã có kết quả cuối cùng, kể cả lỗi và timeout.
- **S / success**: completed operation đúng cả protocol và nghiệp vụ.
- **F / failed**: completed operation lỗi, timeout, rejected, sai dữ liệu hoặc bị hủy theo contract.
- **O / outstanding**: issued nhưng chưa có kết quả khi chốt số liệu.

Nếu mỗi logical operation được ghi nhận đúng một lần:

~~~text
P = I + D
I = C + O
C = S + F

issued_rate           = I / thời_gian_đo
completed_throughput  = C / thời_gian_đo
goodput               = S / thời_gian_đo
success_rate_finished = S / C      (chỉ khi C > 0)
success_per_planned   = S / P      (chỉ khi P > 0)
~~~

**Goodput** là số thao tác thành công và hữu ích/giây, không phải số attempts/giây. Nếu một request retry ba lần rồi hoàn tất một nghiệp vụ, hãy đếm **một logical success** và ghi **ba physical attempts** trong metric riêng. Đếm retries thành successes khiến throughput bị phóng đại và che chi phí I/O.

**S/C đẹp chưa đủ**: nếu generator chỉ gửi 100 trong 1.000 requests dự kiến và cả 100 thành công, S/C = 100% nhưng S/P = 10%. Vì vậy báo cả P, I, D, C, S, F và O. Với asynchronous work, phải ghi rõ thời gian **drain** và công việc còn outstanding để không so A có queue dài với B đã drain hết.

Ví dụ planned = 60.000, issued = 59.500, dropped = 500, completed = 59.400, outstanding = 100, success = 58.000 và failed = 1.400. Những số này cân đối. Goodput sau 120 giây đo là 58.000/120 ≈ 483,33 successful operations/s. Không được dùng 59.400/120 rồi gọi là goodput.

### Mối quan hệ với năng lực phục vụ

Nếu server nhận 500 ops/s nhưng chỉ hoàn tất 400 ops/s trong thời gian dài, **backlog tăng**; tổng requests nhận cao không chứng minh hệ thống khỏe. Trong trạng thái ổn định, Little's Law liên hệ lượng công việc trung bình đang nằm trong hệ thống với arrival/completion rate và average response time, nhưng không thay thế phép đo queue và không đúng máy móc khi hệ thống đang tăng backlog không ổn định.

## 4. Tại sao phải xem cả phân bố?

**Average** có thể che outliers. **p50** mô tả phần giữa, **p95** phần đuôi, **p99/p99.9** phần rất chậm. Một tối ưu giúp số đông nhanh hơn nhưng làm 1% request chờ rất lâu vẫn có thể phá SLO.

Với các quan sát đã sắp tăng dần:

| Chỉ số | Diễn giải |
| --- | --- |
| **p50** | Khoảng 50% observations không vượt mức này |
| **p90/p95** | Thấy phần đuôi thường gặp |
| **p99/p99.9** | Thấy slow tail hiếm, cần nhiều observations |
| **max** | Chậm nhất đã quan sát, nhạy với outlier và cỡ mẫu |
| **Mean** | Trung bình, hữu ích cho capacity math nhưng không thay thế tail |
| **Deadline breach rate** | Tỷ lệ chậm hơn ngưỡng SLO đã định trước |
| **Histogram / CDF / CCDF** | Hình dạng toàn bộ phân bố và tỷ lệ vượt từng ngưỡng |

**p99 không nhất thiết là request chậm nhất.** Cách tính nearest-rank cho N=100 quan sát dùng observation thứ 99, còn max là thứ 100. Histogram systems có thể dùng interpolation, nên A/B phải cùng thuật toán và bucket boundaries.

**p99.9 với 1.000 observations gần giá trị lớn nhất** và dễ biến động mạnh. Cần số mẫu lớn và lặp lại nhiều lần cho tail. Không có một mức mẫu tối thiểu đúng cho mọi workload; độ tin cậy phụ thuộc effect size, variability, serial correlation và số run độc lập.

**Không lấy trung bình p99 của từng pod hoặc từng phút rồi coi là p99 của toàn bộ requests.** Percentiles không cộng gộp tuyến tính. Với Prometheus classic histograms, cần **cộng bucket counts** của các nguồn tương thích trước, rồi dùng histogram_quantile. Với summary quantiles được tính sẵn ở mỗi instance, trung bình các quantiles không tạo ra global quantile.

### CDF và CCDF làm rõ phần đuôi

- **CDF(x)** = tỷ lệ observations có latency ≤ x.
- **CCDF(x)** = 1 − CDF(x) = tỷ lệ observations có latency > x.
- Ở ngưỡng 200 ms, CCDF=0,03 nghĩa là khoảng 3% observations đã đo vượt 200 ms.
- Nếu failures/timeouts không được instrument vào tập latency đó, phải tách số vi phạm/censoring và không được gọi CCDF của successes là CCDF của mọi operations.

Với I/O, thường cần xem **tail-over-time** nữa: một p99 cho toàn bộ 30 phút có thể che một spike kéo dài 20 giây đủ gây incident.

## 5. “Cùng tải” không có nghĩa “cùng 100 threads”

Một bài test **closed-loop** thường tạo N clients, mỗi client gửi request kế tiếp **sau khi response trước hoàn tất**. Nếu server chậm đi, clients gửi ít requests hơn. Hai run đều có “100 virtual users” nhưng hệ thống có thể nhận tải khác nhau.

~~~text
Run A: 100 clients → khoảng 1.000 requests/s được phát
Run B: 100 clients → khoảng 450 requests/s được phát
~~~

Không thể kết luận B có latency tốt hơn **ở cùng 1.000 requests/s** nếu B thực tế chỉ nhận 450/s. “Cùng số connections” cũng không bảo đảm cùng offered load.

Trong mô hình **open-loop/arrival-rate**, generator lập lịch request độc lập với completion của request trước, chẳng hạn 500 requests/s. Tuy nhiên generator có thể trễ lịch nếu thiếu worker, CPU, sockets hoặc connections. Vì vậy phải đo:

1. **Target arrival rate** được cấu hình.
2. **Scheduled/issued rate** theo timestamps thực tế.
3. **Late starts/dropped iterations** do generator không theo kịp.
4. **Server arrival rate** có thực sự khớp điều client phát không.
5. **Actual goodput** và errors/timeouts.

### Coordinated omission

Nếu hệ thống bị stall 1 giây, một closed-loop client đang chờ response không tạo các request kế tiếp đáng lẽ phải đến theo nhịp người dùng. Histogram của các request *đã thực sự phát* bỏ sót những lượt đến bị chặn đó, khiến tail latency trông quá lạc quan.

**Coordinated omission** là thiên lệch đo do không quan sát đủ các requests mà một mô hình arrivals độc lập lẽ ra sẽ đưa vào. Để giảm sai lệch, dùng load generator hỗ trợ rate schedule và đo latency dựa trên **intended start time**; đồng thời kiểm tra generator có theo kịp không. Nếu không, báo missed schedule riêng và **không tự điền số liệu giả thành latency có thật**.

Công cụ **wrk2** dùng lịch constant throughput và ghi latency có cân nhắc thời điểm request đáng lẽ phải được phát. Điều này giúp so sánh cùng offered rate, nhưng không thay thế việc đếm business successes và kiểm tra generator saturation.

### Cố định các biến gây nhiễu

| Nhóm | Cần tương đương A/B |
| --- | --- |
| **Input** | Tỷ lệ đọc/ghi, payload size, số key, data distribution, request route mix, random seed |
| **Arrival schedule** | Offered RPS, duration, ramp-up, burst pattern, steady-state windows |
| **State** | Warm/cold cache theo kế hoạch, database size/index, connection reuse và pool warm-up |
| **Resources** | CPU quota, memory, replicas, disk/network tier, JVM/JDK/GC, limits, autoscaling policy |
| **Network** | RTT, TLS, HTTP version, load balancer, keep-alive, pool sizing ngoài treatment |
| **Failure policy** | Timeout, retry budget, rate-limit, circuit breaker, validation và success predicate |
| **Measurement** | Client/server instrumentation, sampling, histogram buckets, units, generator version |
| **Environment** | Noisy neighbors, background jobs, data reset, clock skew, observability overhead |

Nếu thay đổi **có chủ ý** là tăng connection pool 32→64, phải ghi đó là **treatment**; không bắt pool bằng nhau rồi nói đã kiểm chứng đúng thay đổi. Nhưng CPU quota, DB capacity và offered load vẫn cần so sánh được. Nếu B dùng gấp đôi số replicas, phải đưa **chi phí tài nguyên** vào quyết định.

## 6. Thiết kế một thử nghiệm trước–sau có thể lặp lại

### Bước 1. Chốt giả thuyết và guardrails trước khi chạy

Ví dụ: “Batched I/O cải thiện p99 client latency mà không làm giảm successful throughput”. Đặt tiêu chí minh họa:

- Offered load: **500 planned ops/s** trong 120 giây steady-state.
- Goodput ≥ **495 successful ops/s**.
- Success/planned ≥ **99,9%**.
- p99 end-to-end ≤ **250 ms**.
- Data correctness = **100%** theo validator.
- Timeout/reject/dropped không tăng ngoài ngân sách đã quy định.
- CPU/memory/connection usage không vượt capacity budget.

Không phải hệ thống nào cũng cần các con số trên; đó là **ví dụ cách định nghĩa pass/fail**, không phải chuẩn chung.

### Bước 2. Warm-up theo workload cần đo

Java có JIT, class loading, GC, pool creation và cache warm-up. Đo A cold, B warm rồi kết luận B nhanh hơn sẽ sai. Warm-up cùng loại traffic hoặc **tách hẳn cold-start benchmark** nếu đó mới là SLO cần kiểm tra.

### Bước 3. Thử một đường cong tải

Chạy ở nhiều mức như **100, 300, 500, 650 ops/s** với cùng payload mix. Đo p95/p99 và goodput tại mỗi mức. Điểm “knee” khi hệ thống gần bão hòa quan trọng hơn giá trị tại một RPS quá thấp.

Khi quá tải, kiểm tra **queue depth, in-flight, rejected, timeout và phục hồi sau tải**. Một hệ thống biết từ chối có kiểm soát có thể an toàn hơn hệ thống queue vô hạn, nhưng success/planned vẫn phải báo trung thực.

### Bước 4. Bảo vệ benchmark khỏi generator bottleneck

Dùng máy phát tải có đủ CPU/network/file descriptors; theo dõi CPU, socket errors, missed arrivals, actual rate và client-side throttling. Nếu generator bão hòa, kết quả **INCONCLUSIVE**, không thể gắn khác biệt cho server.

### Bước 5. Lặp và kiểm soát drift

Ưu tiên nhiều runs A/B, có thể xếp **A–B–B–A** hoặc random hóa thứ tự theo block, reset data, cooldown và giữ cùng resource tier. Không chạy A lúc hệ thống vắng, B lúc database bị batch job chiếm tài nguyên rồi coi là thí nghiệm so sánh sạch.

### Bước 6. Chốt window, drain và artifacts

Ghi riêng warm-up, steady state, cooldown/drain. Không chấm p99 cho B trước khi các slow requests hoàn tất còn A đã drain. Bảo quản run ID, config, metric snapshots, histogram, JFR và số lượng planned/issued/completed/failed.

### Bước 7. Quan sát độ bất định

Nếu p99 giữa các lần chạy dao động 200–450 ms, chênh lệch “210→205 ms” trong một run chưa đủ căn cứ. Dùng repeated runs, CI/uncertainty phù hợp, bootstrap theo run/block nếu có serial correlation. **Không bootstrap ngây thơ từng request liên quan chặt theo thời gian** rồi tuyên bố confidence quá hẹp.

## 7. Ví dụ kết luận đúng từ bảng trước/sau

Cùng offered **500 ops/s trong 120 giây**, planned = **60.000** thao tác; tất cả số dưới đây **giả định**:

| Metric | Baseline A | Candidate B |
| --- | ---: | ---: |
| Planned | 60.000 | 60.000 |
| Issued | 59.950 | 59.900 |
| Dropped by generator | 50 | 100 |
| Completed after drain | 59.950 | 59.900 |
| Business successes | 59.880 | 58.800 |
| Failed / timeout | 70 | 1.100 |
| Goodput | **499,0/s** | **490,0/s** |
| Success / planned | **99,80%** | **98,00%** |
| Client p50 | 42 ms | **32 ms** |
| Client p95 | 140 ms | **95 ms** |
| Client p99 | **380 ms** | **540 ms** |

Kiểm tra:

- A: **59.880/120 = 499 successful ops/s**.
- B: **58.800/120 = 490 successful ops/s**.
- Mỗi bản đều thỏa P=I+D, C=S+F và không còn outstanding sau drain.

B có p50/p95 đẹp hơn nhưng **p99, errors, dropped và goodput đều tệ hơn**. Nếu guardrail yêu cầu p99 ≤250 ms, success/planned ≥99,9% và goodput ≥495/s, cả hai chưa đạt đầy đủ; đặc biệt **B không đạt**, không thể công bố “tối ưu thành công” chỉ dựa vào p95.

Giải thích có thể là B trả lỗi sớm, overload, mất request hoặc một nhóm operations bị queue lâu. Nhưng **bảng chưa chứng minh nguyên nhân**: cần timeline và dữ liệu JFR/metrics.

## 8. Histogram, OpenTelemetry và Prometheus

### Đo đúng đơn vị và nhãn

Trong OpenTelemetry HTTP semantic conventions, **http.server.request.duration** và **http.client.request.duration** là histogram đo bằng **seconds**. Server/client khác phạm vi, không so trực tiếp nếu chưa thống nhất điểm đo.

Một bộ custom metrics ví dụ:

- **api_operation_seconds**: classic histogram durations của logical operation, ghi rõ có bao gồm failures/timeouts không.
- **api_operations_total{operation,result}**: counter mỗi logical operation hoàn tất một lần; result=success/failure/timeout.
- **api_operations_scheduled_total**, **api_operations_dropped_total**: counters từ load generator nếu có.
- **api_inflight_operations**: gauge công việc chưa kết thúc.
- **api_retries_total**: physical retries để thấy overhead ẩn.

Không dùng **request ID, user ID, full URL động, raw error message** làm metric labels: cardinality có thể tăng bùng nổ. Route template và loại lỗi giới hạn là lựa chọn hợp lý hơn.

### Tính p99 từ classic histogram

~~~promql
histogram_quantile(
  0.99,
  sum by (le) (
    rate(api_operation_seconds_bucket{operation="read"}[5m])
  )
)
~~~

Đây là **ước lượng p99 bằng seconds** cho một classic histogram có các bucket ranh giới nhất quán. Nếu histogram có buckets quá thô (ví dụ 0.1s rồi 1s), p99 quanh 0.25s có thể có độ bất định lớn.

**Sai:** lấy trung bình percentiles của nhiều instances:

~~~promql
avg(instance_request_p99{operation="read"})
~~~

Nó không cho p99 thực của toàn bộ requests. Native histogram có syntax tương ứng khác; không tự thêm **le** vào metric native histogram không có label đó.

### Goodput từ success counter

~~~promql
sum(
  rate(api_operations_total{
    operation="read", result="success"
  }[5m])
)
~~~

Counter này chỉ là goodput khi app **đếm một lần trên mỗi logical success**. Nếu instrumentation đếm mỗi retry attempt hoặc completion từ callback nhiều lần, query vẫn trả số đẹp nhưng sai ngữ nghĩa.

Success rate among completed:

~~~promql
sum(rate(api_operations_total{operation="read",result="success"}[5m]))
/
sum(rate(api_operations_total{operation="read"}[5m]))
~~~

Không thay nó cho **success/planned** nếu generator dropped operations hoặc còn outstanding.

### Tỷ lệ trong giới hạn 250 ms

Nếu bucket **le="0.25"** có thật:

~~~promql
sum(rate(api_operation_seconds_bucket{
  operation="read", le="0.25"
}[5m]))
/
sum(rate(api_operation_seconds_count{
  operation="read"
}[5m]))
~~~

Nếu histogram chỉ ghi **successful responses**, tỷ lệ này **không phản ánh failures/timeouts** và chỉ là SLO đối với nhóm đã thành công. Cần thêm error accounting ở phía client và tỷ lệ thành công trên planned load.

Các exporters có thể đổi tên metrics hoặc dùng labels khác; xác nhận **actual exposed metric** trước khi chạy query. Giữ histogram boundaries và sampling đồng nhất giữa các phiên bản A/B.

## 9. Ví dụ load test theo constant arrival rate

Với **wrk2** (executable thường tên **wrk**):

~~~bash
# Chỉ chạy trên hệ thống thử nghiệm được cấp quyền.
# -R là target rate, không phải throughput thực tế.
wrk -t4 -c100 -d3m -R500 --latency \
  http://127.0.0.1:8080/api/items
~~~

- **-t4**: 4 worker threads trên generator.
- **-c100**: 100 connections.
- **-d3m**: 3 phút đo.
- **-R500**: target 500 requests/giây.
- **--latency**: in thống kê latency.

wrk2 tính latency với lịch request dự kiến để hạn chế coordinated omission. Tuy nhiên phải **đối chiếu actual arrival rate**, errors, status validation và generator saturation. Một công cụ HTTP benchmark không tự biết mọi ràng buộc nghiệp vụ; với write API, cần validator đọc lại dữ liệu, xác nhận số records, idempotency hoặc checksum.

Đừng thử tải nặng lên production không được phép. Phải có giới hạn, khả năng stop/rollback và lưu ý side effects của các requests ghi.

## 10. Java 17+ runnable: minh họa quyết định bằng số liệu tất định

Chương trình dưới đây là **so sánh số liệu giả lập** có thể biên dịch và chạy độc lập. Nó không phát HTTP hay đo I/O thật; mục tiêu là minh họa cách tính **success count, goodput, p50/p95/p99** cho **cùng 20 planned operations trong 2 giây**. Để test production, phải đo arrival schedule và ghi nhận đủ operations với histogram/số mẫu thực.

Tạo file **SameLoadLatencyCheck.java**:

~~~java
import java.util.Arrays;
import java.util.Locale;

public final class SameLoadLatencyCheck {
    record Observation(long latencyMillis, boolean success) {}
    record Run(String name, int scheduled, long seconds,
               Observation[] completed, int dropped, int inFlight) {}

    private static long percentile(long[] sorted, double fraction) {
        if (sorted.length == 0) {
            throw new IllegalArgumentException("empty observations");
        }
        int rank = (int) Math.ceil(fraction * sorted.length);
        int index = Math.min(sorted.length - 1, Math.max(0, rank - 1));
        return sorted[index];
    }

    private static Run baseline() {
        Observation[] data = new Observation[20];
        for (int i = 0; i < 18; i++) {
            data[i] = new Observation(10, true);
        }
        data[18] = new Observation(20, true);
        data[19] = new Observation(100, true);
        return new Run("baseline", 20, 2, data, 0, 0);
    }

    private static Run candidate() {
        Observation[] data = new Observation[20];
        for (int i = 0; i < 15; i++) {
            data[i] = new Observation(8, true);
        }
        for (int i = 15; i < 19; i++) {
            data[i] = new Observation(12, i < 18);
        }
        data[19] = new Observation(200, false);
        return new Run("candidate", 20, 2, data, 0, 0);
    }

    private static void report(Run run) {
        if (run.scheduled() != run.completed().length
                + run.dropped() + run.inFlight()) {
            throw new IllegalStateException("incomplete accounting");
        }
        long successes = Arrays.stream(run.completed())
                .filter(Observation::success)
                .count();
        long[] sorted = Arrays.stream(run.completed())
                .mapToLong(Observation::latencyMillis)
                .sorted()
                .toArray();

        System.out.printf(
                Locale.ROOT,
                "%s scheduled=%d completed=%d success=%d failed=%d "
                + "goodput=%.1f/s p50=%dms p95=%dms p99=%dms%n",
                run.name(),
                run.scheduled(),
                run.completed().length,
                successes,
                run.completed().length - successes,
                successes / (double) run.seconds(),
                percentile(sorted, 0.50),
                percentile(sorted, 0.95),
                percentile(sorted, 0.99)
        );
    }

    public static void main(String[] args) {
        report(baseline());
        report(candidate());
    }
}
~~~

Chạy với JDK 17+:

~~~bash
javac SameLoadLatencyCheck.java
java SameLoadLatencyCheck
~~~

**Stdout chính xác:**

~~~text
baseline scheduled=20 completed=20 success=20 failed=0 goodput=10.0/s p50=10ms p95=20ms p99=100ms
candidate scheduled=20 completed=20 success=18 failed=2 goodput=9.0/s p50=8ms p95=12ms p99=200ms
~~~

Lý do:

- Baseline có 18 mẫu **10 ms**, một **20 ms**, một **100 ms**. Với nearest-rank, p95 là mẫu thứ **ceil(0,95×20)=19** → 20 ms; p99 là mẫu thứ 20 → 100 ms.
- Candidate có 15 mẫu **8 ms**, bốn **12 ms** và một **200 ms**. p95=12 ms nhưng p99=200 ms.
- Candidate chỉ có 18 successes (ba mẫu 12 ms đầu trong nhóm cuối thành công, một mẫu 12 ms và mẫu 200 ms thất bại). Goodput giảm từ **20/2=10,0/s** xuống **18/2=9,0/s**.

Bài demo cố tình cho p95 tốt hơn nhưng goodput/p99 tệ hơn. **20 observations quá ít cho ước lượng p99 production**; đây là minh họa thuật toán, không phải benchmark thực.

### Instrumentation Java cho một operation thực

Đo duration tại client qua nanoTime, ghi outcome và thời gian **cả khi có lỗi**:

~~~java
// Fragment, chưa phải chương trình độc lập.
// Giả định đã có HttpClient client, HttpRequest request,
// hàm validatePayload và recordResult do ứng dụng định nghĩa.
long beginNanos = System.nanoTime();
boolean success = false;
try {
    var response = client.send(
            request,
            java.net.http.HttpResponse.BodyHandlers.ofString());
    success = response.statusCode() == 200
            && validatePayload(response.body());
} finally {
    long elapsed = System.nanoTime() - beginNanos;
    recordResult(elapsed, success);
}
~~~

Đoạn này cần đặt trong method xử lý **IOException/InterruptedException** theo hợp đồng API. Không nuốt interrupt; nếu code chủ động bắt InterruptedException thì khôi phục interrupt status hoặc truyền lên phù hợp. **recordResult** phải đếm chính xác một logical completion và duration; nếu chưa gửi request do generator thiếu tài nguyên, cần đếm dropped ở cơ chế scheduler.

**Lưu ý:** một chương trình gọi **client.send tuần tự trong vòng lặp** vẫn là closed-loop. Muốn test cùng arrival rate, phải có scheduler/concurrency độc lập với kết quả request trước và đủ worker.

## 11. Khi latency khác, đối chiếu bằng JFR và JVM/OS

Độ trễ của operation gồm nhiều tầng. Khi B p99 xấu đi, JFR và JVM metrics giúp **kiểm tra giả thuyết**, không phải thay thế end-to-end latency từ client.

| Dấu hiệu | Nguồn quan sát | Ý nghĩa |
| --- | --- | --- |
| Đọc socket chậm | **jdk.SocketRead** | Thời lượng đọc/network/downstream khi event được thu |
| Ghi socket chậm | **jdk.SocketWrite** | Phần thời gian ghi và khả năng backpressure |
| File/disk I/O | **jdk.FileRead**, **jdk.FileWrite** | Operations file có duration và bytes liên quan |
| Thread chờ | **jdk.ThreadPark**, **jdk.JavaMonitorEnter** | Đợi queue/lock/park |
| GC pause | **jdk.GarbageCollection**, GC phase events | Có trùng latency spike không |
| CPU | **jdk.ExecutionSample**, CPULoad | CPU có bị dùng ở một method/path cụ thể không |
| Allocation | **jdk.ObjectAllocationSample** | Allocation pressure có gây GC/overhead không |
| Backlog/pool | Metrics thread pool, queue depth, active/pending connections | Có chuyển bottleneck sang queue không |
| OS/container | CPU throttle, disk utilization, network retransmit, RSS | Có khác giới hạn tài nguyên không |

Ví dụ CLI:

~~~bash
jfr summary before.jfr
jfr metadata --events jdk.SocketRead,jdk.SocketWrite,jdk.FileRead,jdk.FileWrite before.jfr
jfr print --events jdk.SocketRead,jdk.SocketWrite before.jfr

jfr summary after.jfr
jfr metadata --events jdk.SocketRead,jdk.SocketWrite,jdk.FileRead,jdk.FileWrite after.jfr
jfr print --events jdk.SocketRead,jdk.SocketWrite after.jfr
~~~

JFR có threshold, settings, sampling và khoảng recording riêng. **Count=0 không chứng minh operation chưa xảy ra**. JFR SocketRead duration **không phải toàn bộ end-to-end client latency**; còn queue, CPU, GC, network phần khác, connection pool và payload parsing. Quan sát cùng timestamps mới có thể nối chứng cứ.

Trường hợp hay gặp: B giảm latency của SocketRead nhưng tăng số ThreadPark hoặc queue wait, dẫn tới p99 request xấu. Như vậy thay đổi có thể đã **dời bottleneck**, không phải giải quyết nó.

## 12. Cách đọc kết quả và quyết định rollout

Một báo cáo đầy đủ nên chia ba lớp:

**A. Chất lượng phép đo**

- Có cùng offered rate và arrival schedule thực tế không?
- Dữ liệu, resource budgets, GC/JDK, cache state, connection reuse, warm-up và window có phù hợp không?
- Generator có theo kịp lịch và không bị CPU/network bottleneck không?
- Mỗi run có đủ số scheduled/issued/dropped/completed/success/failure/outstanding không?
- Histograms có cùng đơn vị, bucket boundaries và measurement points không?

**B. Kết quả**

- Bảng goodput, success/planned, error/timeout/retry, p50/p95/p99, tỷ lệ vượt deadline, max và CPU/IO.
- Time-series và distribution curves; không chỉ trung bình toàn run.
- Repeated runs, độ biến động, confidence/uncertainty phù hợp.
- Tài liệu tương quan JFR/metrics tại cùng mốc; ghi rõ phần dữ liệu thiếu.

**C. Quyết định đã định trước**

| Trạng thái | Điều kiện |
| --- | --- |
| **PASS** | Goodput, correctness, failures, p99/tail latency và resource guardrails đạt ở các mức tải quan trọng |
| **FAIL / ROLLBACK** | Giảm goodput, tăng lỗi/timeout/drops, mất dữ liệu, tail xấu hoặc vượt resource budget |
| **INCONCLUSIVE** | Load generator không theo kịp, thiếu dữ liệu, sample quá ít, môi trường khác, results biến động hơn hiệu ứng cần kiểm chứng |

Tối ưu latency có thể có trade-off hợp lệ, nhưng phải được nêu rõ và **được chấp nhận theo SLO nghiệp vụ**, không thể tự gọi là cải thiện toàn diện khi số thao tác thành công giảm. Giữ mọi runs, gồm runs thất bại, để tránh chọn số đẹp (cherry-picking).

## 13. Những lỗi dễ mắc

1. Chỉ xem average hoặc p50; bỏ qua p99 và số timeout.
2. Chỉ lưu latencies của successes; errors nhanh hay timeouts biến mất khỏi biểu đồ.
3. Giữ cùng số threads/connections rồi tuyên bố cùng offered load.
4. Bỏ qua dropped/late starts gây coordinated omission.
5. So issued RPS với completed RPS hoặc coi attempts là successful operations.
6. Đếm retry attempts thành logical success, che duplicate side effects.
7. Chạy baseline cold còn candidate warm.
8. Dùng workload khác route mix/payload/cache/data state.
9. Dùng timeout khác mà không ghi lại, khiến B trả lỗi nhanh hơn và p95 đẹp hơn.
10. Kết thúc test trước khi các in-flight requests có kết quả.
11. Gộp trung bình p99 từng instance hoặc từng phút.
12. Dùng bucket quá rộng quanh SLO rồi kết luận cải thiện 2–3 ms.
13. So client end-to-end của A với server-only latency của B.
14. Quên độ bền dữ liệu: HTTP 200 có thể không tương đương operation hoàn tất đúng.
15. Generator bị nghẽn CPU/network nhưng không có metric riêng.
16. Chỉ chạy một lần và bỏ qua GC/JIT/DB-cache variability.
17. Candidate dùng nhiều CPU/memory/replicas hơn nhưng báo hiệu năng mà không tính cost.
18. Kết luận I/O cải thiện từ một vài JFR events không phủ toàn bộ request.

## 14. Tự kiểm tra

**Câu 1:** cùng 100 clients, A issue 600 RPS nhưng B chỉ issue 350 RPS. p95 của B thấp hơn. Đã chứng minh B nhanh hơn dưới cùng tải chưa?  
**Đáp án:** Chưa. Closed-loop có thể tự giảm tải khi latency tăng. Cần giữ offered arrival rate và kiểm tra actual issue/dropped/goodput.

**Câu 2:** A có 9.990 successes trên 10.000 planned, B có 9.000; B p99 thấp hơn. Nếu SLO yêu cầu success/planned ≥99,9%, chọn B được không?  
**Đáp án:** Không. B vi phạm correctness/availability guardrail dù p99 của nhóm đã đo thấp hơn.

**Câu 3:** Tại sao không tính trung bình p99 của ba pods?  
**Đáp án:** Percentile không cộng gộp được như counter. Cần raw samples hoặc gộp histogram buckets tương thích trước khi tính global percentile.

**Câu 4:** Client p99 tăng nhưng JFR SocketRead duration giảm. Có mâu thuẫn không?  
**Đáp án:** Không. Queue wait, ThreadPark, CPU, GC, connection pool, retry hoặc network khác có thể tăng; JFR SocketRead chỉ đo một phần và còn phụ thuộc threshold.

**Câu 5:** Target 500/s trong 120 giây nhưng generator chỉ issue 50.000 trong 60.000 planned. Có thể kết luận đạt p99 SLO tại 500/s không?  
**Đáp án:** Chưa. Test không duy trì tải yêu cầu; phải báo khoảng 10.000 scheduled operations không được phát, sửa generator và đo lại.

**Câu 6:** Một histogram chỉ có bucket 100 ms và 1 s, p99 ước lượng 280 ms. Có nên so với 275 ms và công bố tiết kiệm 5 ms không?  
**Đáp án:** Không. Bucket resolution quá thô; cần buckets phù hợp hoặc nguồn mẫu chính xác hơn.

**Câu 7:** Candidate p50 giảm 25%, p99.9 tăng 3 lần, errors tăng và CPU tăng 40%. Kết luận?  
**Đáp án:** Không được gọi là cải thiện toàn diện. Đối chiếu guardrails, lặp test tương đương, tìm bottleneck và tính budget trước rollout.

## Tài liệu tham khảo

- [Prometheus — Histograms and summaries](https://prometheus.io/docs/practices/histograms/): percentiles, histogram aggregation và lỗi trung bình quantiles.
- [OpenTelemetry — HTTP metrics semantic conventions](https://opentelemetry.io/docs/specs/semconv/http/http-metrics/): client/server request duration, seconds, HTTP error attributes.
- [OpenTelemetry — Metrics API](https://opentelemetry.io/docs/specs/otel/metrics/api/): histogram, counter và metric semantics.
- [wrk2 — Constant throughput, correct latency recording](https://github.com/giltene/wrk2): arrival-rate schedule, coordinated omission và ghi latency.
- [Oracle JDK 21 — Troubleshooting Guide, I/O với JFR](https://docs.oracle.com/en/java/javase/21/troubleshoot/troubleshooting-guide.pdf): SocketRead/SocketWrite/FileRead/FileWrite.
- [Oracle JDK 21 — jfr CLI](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jfr.html): summary, metadata và lọc sự kiện.
