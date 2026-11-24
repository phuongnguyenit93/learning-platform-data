# Đo overhead với tải bình thường, lỗi liên tục và mạch mở

Đánh giá hiệu năng Circuit Breaker cần tách chi phí mà nó thêm vào một lời gọi bình thường khỏi lợi ích khi dependency lỗi. Ở trạng thái `CLOSED`, mỗi request được kiểm tra quyền thực thi và kết quả được ghi vào sliding window; đây là overhead cần đo khi hệ thống hoạt động tốt. Khi lỗi liên tục, Circuit Breaker phải thu thập đủ mẫu để quyết định mở mạch. Khi đã `OPEN`, request bị từ chối nhanh và không nên tiếp tục tạo tải lên dependency.

Không có một con số overhead cố định áp dụng cho mọi ứng dụng. Kết quả phụ thuộc phiên bản Resilience4j/Spring Cloud, kiểu lời gọi đồng bộ hay reactive, kích thước cửa sổ, số thread, logging, metrics, fallback, client HTTP và tải nền. Cần đo trong môi trường có thể lặp lại, với cùng offered load và cùng cấu hình tài nguyên.

## 1. Xác định câu hỏi và phạm vi đo

Trước khi chạy benchmark, xác định rõ đang đo lớp nào:

- **Overhead vi mô của thư viện:** chi phí gọi trực tiếp so với gọi qua Circuit Breaker trong cùng JVM, không có mạng hoặc server bên ngoài. Dùng JMH để cô lập chi phí kiểm tra trạng thái, ghi nhận kết quả và từ chối lời gọi.
- **Overhead của ứng dụng:** chi phí của factory/proxy, fallback, metrics, logging, executor, serialization và HTTP client trong một service Spring thực tế.
- **Hiệu quả dưới tải đầu-cuối:** throughput, latency và tài nguyên khi request đi qua API, Circuit Breaker và dependency. Dùng load test với dependency giả lập có thể điều khiển độ trễ/lỗi.

JMH không thay thế load test. Benchmark vi mô trả lời chi phí của một thao tác trong JVM; load test trả lời hệ thống phục vụ được bao nhiêu request, latency thay đổi ra sao và có bị nghẽn thread/connection hay không.

## 2. Các chỉ số cần thu thập

| Nhóm | Chỉ số | Ý nghĩa |
| --- | --- | --- |
| Lưu lượng | Request rate, throughput, số request hoàn tất, dropped iterations | Hệ thống có xử lý đủ lượng tải được gửi tới không? |
| Độ trễ | p50, p95, p99 và max latency | Overhead ảnh hưởng tới phần lớn request hay tail latency? |
| Lỗi | HTTP 5xx, timeout, exception, fallback, `CallNotPermittedException` | Request thất bại vì dependency, timeout hay bị breaker từ chối? |
| Circuit Breaker | State, failure rate, slow-call rate, not-permitted calls, số lần chuyển trạng thái | Mạch mở khi nào và có giữ được trạng thái mong muốn không? |
| Dependency | Số request tới stub, latency, số kết nối và lỗi | Khi mạch `OPEN`, lưu lượng tới dependency có thực sự giảm không? |
| Tài nguyên | CPU, heap/RSS, allocation rate, GC pause, thread count | Overhead có làm tăng chi phí CPU hoặc bộ nhớ không? |
| Hàng đợi | Executor queue, Bulkhead queue, active threads, rejected tasks, connection pool wait | Hệ thống có chuyển nút thắt sang pool hoặc queue khác không? |

Đo riêng latency của API và latency gọi dependency. Khi dependency mất 500 ms, phần overhead vài micro giây của Circuit Breaker có thể bị che khuất trong tổng thời gian request. Ngược lại, khi mạch `OPEN`, latency của API chủ yếu phản ánh thời gian từ chối, fallback và serialization.

## 3. Thiết kế ma trận thử nghiệm

Giữ cùng một artifact, payload, số instance, giới hạn CPU/bộ nhớ, JVM flags, HTTP client, connection pool và cấu hình logging giữa các lần chạy. Thay đổi đúng một yếu tố mỗi lần. Ma trận tối thiểu nên có:

| Kịch bản | Trạng thái/điều kiện | Mục tiêu đo |
| --- | --- | --- |
| A. Baseline trực tiếp | Gọi dependency mà không đi qua Circuit Breaker; dependency thành công | Mốc latency, throughput và CPU/request |
| B. CLOSED, không lỗi | Circuit Breaker bật; dependency thành công ổn định | Overhead trên đường gọi bình thường |
| C. CLOSED, có độ trễ thực tế | Dependency thành công nhưng có latency cố định hoặc phân phối latency gần production | Ảnh hưởng khi network/client chiếm phần lớn thời gian |
| D. Lỗi liên tục và chuyển trạng thái | Dependency trả lỗi hoặc timeout liên tục cho đến khi breaker đạt ngưỡng mở | Số request cần để mở mạch, thời gian phát hiện và tải phát sinh trước khi mở |
| E. OPEN ổn định | Breaker đã mở; tiếp tục gửi cùng offered load | Latency từ chối, chi phí fallback và số request còn tới dependency |
| F. HALF_OPEN và phục hồi | Hết thời gian mở mạch; dependency phục hồi hoặc tiếp tục lỗi | Số probe, concurrency và thời gian ổn định lại |

Thực hiện baseline và kịch bản B với cùng đường xử lý càng nhiều càng tốt. Nếu baseline bỏ qua cả serialization, client hoặc service layer thì chênh lệch không còn là overhead riêng của Circuit Breaker.

## 4. Chuẩn bị dependency giả lập

Dùng mock server hoặc service stub riêng để điều khiển response. Nên có các chế độ cấu hình được trước mỗi lần chạy:

- `success`: trả response thành công với payload cố định.
- `slow`: trả response sau một độ trễ cố định hoặc phân phối có kiểm soát.
- `error`: trả 5xx liên tục.
- `timeout`: giữ request lâu hơn timeout của client/TimeLimiter.
- `recover`: sau một khoảng lỗi, chuyển sang trả thành công để đo `HALF_OPEN`.

Stub cần đếm số request nhận được, latency và response code. Bộ đếm này là bằng chứng quan trọng để xác nhận Circuit Breaker đang mở thực sự ngừng gửi request mới. Đặt stub và load generator trên máy riêng hoặc ít nhất theo dõi CPU của chúng; nếu generator bị nghẽn, số liệu throughput phía ứng dụng không còn phản ánh offered load.

Đặt cấu hình Circuit Breaker rõ ràng trong profile benchmark. Ví dụ:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
        automaticTransitionFromOpenToHalfOpenEnabled: false
```

Với cấu hình này, breaker cần tối thiểu 10 mẫu trước khi đánh giá tỷ lệ lỗi. Khi đủ mẫu và tỷ lệ lỗi đạt ngưỡng, mạch mở. Số request thất bại trước thời điểm mở phụ thuộc `minimumNumberOfCalls`, cửa sổ, tỷ lệ lỗi, concurrency và thời điểm các kết quả hoàn tất. Không giả định breaker sẽ mở ngay ở lỗi đầu tiên.

Trong kịch bản lỗi liên tục, ghi lại thời điểm request đầu tiên thất bại, thời điểm đạt đủ mẫu và thời điểm chuyển `OPEN`. Trong kịch bản `OPEN`, chờ xác nhận state đã mở trước khi bắt đầu cửa sổ đo ổn định; nếu không, số liệu sẽ trộn lẫn giai đoạn phát hiện lỗi với giai đoạn từ chối nhanh.

## 5. Microbenchmark với JMH

JMH phù hợp để đo chi phí gọi supplier trực tiếp, supplier qua Circuit Breaker đang `CLOSED` và đường từ chối khi breaker `OPEN`. Đặt benchmark trong module benchmark riêng, không chạy JMH bên trong request handler.

Ví dụ benchmark tối giản:

```java
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import org.openjdk.jmh.annotations.*;

import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.function.Supplier;

@State(Scope.Thread)
@BenchmarkMode(Mode.AverageTime)
@OutputTimeUnit(TimeUnit.NANOSECONDS)
@Fork(3)
@Warmup(iterations = 5, time = 1)
@Measurement(iterations = 8, time = 1)
public class CircuitBreakerOverheadBenchmark {
    private Supplier<Integer> direct;
    private Supplier<Integer> closed;
    private Supplier<Integer> openWithFallback;

    @Setup(Level.Trial)
    public void setup() {
        direct = () -> 42;

        CircuitBreaker closedBreaker = CircuitBreaker.of(
                "closed", CircuitBreakerConfig.ofDefaults());
        closed = CircuitBreaker.decorateSupplier(closedBreaker, direct);

        CircuitBreakerConfig openConfig = CircuitBreakerConfig.custom()
                .slidingWindowSize(2)
                .minimumNumberOfCalls(2)
                .failureRateThreshold(50)
                .waitDurationInOpenState(Duration.ofHours(1))
                .build();
        CircuitBreaker openBreaker = CircuitBreaker.of("open", openConfig);

        // Hai lỗi trong cửa sổ hai mẫu làm breaker chuyển sang OPEN.
        for (int i = 0; i < 2; i++) {
            try {
                openBreaker.executeSupplier(() -> {
                    throw new IllegalStateException("simulated failure");
                });
            } catch (IllegalStateException ignored) {
                // Chỉ tạo trạng thái OPEN trong setup, không đo ở benchmark.
            }
        }

        openWithFallback = () -> {
            try {
                return openBreaker.executeSupplier(direct);
            } catch (CallNotPermittedException ignored) {
                return -1;
            }
        };
    }

    @Benchmark
    public Integer directCall() {
        return direct.get();
    }

    @Benchmark
    public Integer closedCircuitBreaker() {
        return closed.get();
    }

    @Benchmark
    public Integer openCircuitBreakerWithFallback() {
        return openWithFallback.get();
    }
}
```

Ví dụ dùng `CircuitBreaker` trực tiếp để cô lập overhead của thư viện. Nó không đo Spring AOP proxy, factory, HTTP client, Micrometer exporter hay network. Nếu ứng dụng dùng Spring Cloud factory hoặc annotation, bổ sung một benchmark tích hợp riêng để đo đường gọi thực tế. Cấu hình `waitDurationInOpenState` dài giúp breaker không tự chuyển khỏi `OPEN` trong thời gian benchmark.

Chạy benchmark với nhiều fork và warmup như ví dụ, giữ cùng JVM, CPU và JDK. Có thể bật profiler allocation/GC của JMH để xem chi phí bộ nhớ. Không so sánh một lần chạy ngắn giữa hai máy hoặc hai cấu hình JVM khác nhau rồi kết luận overhead.

## 6. Load test bằng k6 với offered load cố định

Đối với hệ thống đầu-cuối, dùng load generator có thể giữ tốc độ request ổn định. Ví dụ k6 với executor `constant-arrival-rate`:

```javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    steady_load: {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV.RATE || 200),
      timeUnit: '1s',
      duration: __ENV.DURATION || '5m',
      preAllocatedVUs: 50,
      maxVUs: 200,
    },
  },
};

export default function () {
  const baseUrl = __ENV.BASE_URL;
  const response = http.get(`${baseUrl}/api/inventory/SKU-42`, {
    tags: { scenario: __ENV.SCENARIO || 'closed' },
  });

  check(response, {
    'server returned an HTTP response': (r) => r.status > 0,
  });
}
```

Chạy mỗi kịch bản thành một lần riêng, ví dụ:

```bash
k6 run -e BASE_URL=http://localhost:8080 -e SCENARIO=closed -e RATE=200 -e DURATION=5m circuit-breaker.js
```

Trước mỗi lần chạy, cấu hình stub và breaker vào đúng trạng thái. Với kịch bản `OPEN`, chờ state mở rồi mới chạy k6. Ghi lại `http_req_duration`, `http_reqs`, `http_req_failed`, response code và `dropped_iterations`. Nếu `dropped_iterations` tăng, generator không phát đủ offered load; không được diễn giải throughput của server như thể nó đã nhận đủ request.

Constant arrival rate giúp giữ offered load tương đối ổn định khi response chậm. Với kịch bản có lỗi dự kiến, xác định rõ response fallback nào được chấp nhận theo hợp đồng API. Không bỏ qua response 5xx chỉ để làm tỷ lệ test xanh; giữ lại response code để phân tích SLI và lỗi phục vụ.

## 7. Quy trình chạy từng giai đoạn

Để kết quả có thể so sánh, dùng cùng thời lượng và tải cho từng lần chạy:

1. **Chuẩn bị:** cố định phiên bản ứng dụng, JDK, JVM flags, CPU/memory limit, số instance, cấu hình HTTP client và payload. Xác nhận Prometheus scrape và stub metrics hoạt động.
2. **Warm-up:** chạy tải nhẹ rồi tăng dần cho tới khi JIT, connection pool và cache ổn định. Không lấy giai đoạn khởi động làm số liệu chính.
3. **Baseline:** chạy đường gọi trực tiếp với dependency thành công. Ghi throughput, latency, CPU/request, GC và số request tới stub.
4. **CLOSED khỏe mạnh:** bật Circuit Breaker, giữ dependency thành công và gửi cùng offered load. Chênh lệch so với baseline là overhead của đường gọi trong điều kiện bình thường.
5. **CLOSED có độ trễ:** thêm độ trễ thực tế vào stub. Xác nhận overhead của breaker không bị nhầm với thời gian mạng và xử lý dependency.
6. **Lỗi liên tục:** cho stub trả 5xx hoặc timeout. Đo thời gian từ lỗi đầu tiên tới lúc breaker `OPEN`, số request được gửi trong giai đoạn đó và chi phí fallback.
7. **OPEN ổn định:** tiếp tục cùng offered load khi breaker đã mở. Đo latency từ chối, CPU, fallback và xác nhận bộ đếm request của stub gần như không tăng từ các request bị chặn.
8. **HALF_OPEN/phục hồi:** chuyển stub về success sau thời gian mở. Ghi số probe, latency và thời gian tới khi breaker `CLOSED` ổn định.
9. **Lặp lại:** chạy mỗi kịch bản ít nhất ba lần hoặc đủ số lần để độ biến thiên ổn định; đảo thứ tự kịch bản nếu có thể để giảm ảnh hưởng của nhiệt độ CPU, cache và tải nền.

Chọn thời lượng steady-state đủ dài để có đủ mẫu p95/p99. Với traffic thấp, cần thời gian dài hơn để có percentile đáng tin cậy. Dùng cùng offered load thay vì chỉ cùng số virtual users nếu mục tiêu là so sánh throughput dưới tải cố định.

## 8. Tính overhead và so sánh kết quả

Với cùng offered load và cùng môi trường, có thể tính chênh lệch latency:

```text
latency_overhead_ms = p95_closed_ms - p95_baseline_ms

relative_latency_overhead_pct =
    (p95_closed_ms - p95_baseline_ms) / p95_baseline_ms * 100
```

Ví dụ nếu p95 baseline là 40 ms và p95 khi `CLOSED` là 41 ms, chênh lệch là 1 ms, tương đương 2,5%. Đây là ví dụ tính toán, không phải mức overhead dự kiến của Resilience4j.

Đối với CPU, xem xét CPU-seconds trên mỗi request hoàn tất thay vì chỉ so sánh tổng CPU khi throughput khác nhau. Với throughput, so sánh request hoàn tất mỗi giây ở cùng offered load và cùng tỷ lệ response hợp lệ. Khi kịch bản `OPEN` trả fallback 200, tách số request dùng fallback khỏi số request được dependency phục vụ thành công.

Đối chiếu ít nhất các kết quả:

| Kịch bản | p95/p99 API | CPU/request | Dependency request rate | Fallback/rejection |
| --- | --- | --- | --- | --- |
| Baseline | Mốc so sánh | Mốc so sánh | Gần bằng offered load | Không có breaker rejection |
| CLOSED khỏe mạnh | Overhead đường bình thường | Chi phí ghi nhận mẫu | Gần bằng offered load | Thấp hoặc bằng 0 |
| Lỗi liên tục | Thay đổi trong giai đoạn phát hiện | Chi phí lỗi/logging/metrics | Giảm sau khi mạch mở | Tăng theo lỗi và rejection |
| OPEN ổn định | Thời gian từ chối + fallback | Chi phí xử lý local | Gần 0 đối với request bị chặn | Rejection/fallback tăng |
| HALF_OPEN | Có thể biến động do probe | Chi phí probe và chuyển trạng thái | Chỉ một số probe được gửi | Phụ thuộc kết quả phục hồi |

Không kết luận chỉ từ average latency. Một cấu hình có average tốt nhưng p99 tăng mạnh có thể vẫn làm vi phạm SLO. Đọc percentile cùng throughput, dropped iterations, response code và tài nguyên.

## 9. Phân tích ba trạng thái dưới góc độ hiệu năng

### CLOSED — chi phí trên đường thành công

Ở `CLOSED`, mỗi kết quả cần được ghi nhận vào sliding window. Overhead có thể đến từ đồng bộ hóa trạng thái, cập nhật thống kê cửa sổ, đo thời gian, tag metrics và aspect/proxy nếu dùng annotation. Kích thước cửa sổ và loại `COUNT_BASED`/`TIME_BASED` có thể ảnh hưởng chi phí bộ nhớ và xử lý; hãy đo với cấu hình giống production.

Nếu JMH cho thấy chi phí thư viện nhỏ nhưng load test cho thấy p99 tăng, kiểm tra proxy, logging, metrics exporter, thread contention và connection pool. Đừng quy toàn bộ chênh lệch cho Circuit Breaker chỉ vì nó vừa được bật.

### Lỗi liên tục — chi phí trước và trong khi mở mạch

Breaker không thể biết dependency đã hỏng trước khi nhận kết quả lỗi hoặc chậm. Trong giai đoạn đầu, request vẫn đi tới dependency cho tới khi đủ `minimumNumberOfCalls` và tỷ lệ lỗi vượt ngưỡng. Thời gian này phụ thuộc tốc độ request, độ trễ của dependency và sliding window.

Khi lỗi là timeout, các request đang chờ có thể tiếp tục chiếm thread/connection cho tới khi timeout của client hoặc TimeLimiter kết thúc. Circuit Breaker không tự giải phóng mọi tác vụ đang chạy chỉ vì đã chuyển `OPEN`. Đo số request in-flight, thread đang chờ, connection đang dùng và thời gian từ lỗi đầu tới khi tài nguyên được giải phóng.

### OPEN — đường từ chối nhanh

Ở `OPEN`, Circuit Breaker từ chối request mới bằng `CallNotPermittedException` trước khi gọi dependency. Đường này thường có latency thấp hơn việc chờ connect/read timeout, nhưng tổng latency vẫn bao gồm fallback, cache, serialization và response tới client.

Xác minh bằng bộ đếm request ở stub: khi breaker mở ổn định, số request từ các lời gọi bị chặn không được tiếp tục tăng. Nếu vẫn tăng, có thể có đường gọi khác không đi qua breaker, breaker ID khác, hoặc một request đã được gửi trước khi trạng thái mở.

### HALF_OPEN — tải thăm dò có giới hạn

Sau thời gian mở, breaker cho phép số probe được cấu hình. Nếu nhiều instance ứng dụng cùng có breaker riêng, mỗi instance có thể thực hiện probe của nó; tổng probe toàn hệ thống có thể lớn hơn con số cấu hình trên một instance. Khi đánh giá tải phục hồi, tính cả số instance và số breaker ID.

Không tăng `permittedNumberOfCallsInHalfOpenState` chỉ để tăng tốc phục hồi nếu dependency chưa chịu được tải đó. Mục tiêu là lấy đủ tín hiệu phục hồi với lượng request nhỏ và có kiểm soát.

## 10. Tránh sai lệch trong benchmark

- **JIT và warm-up:** JVM cần thời gian biên dịch nóng; bỏ qua warm-up làm kết quả lần đầu cao bất thường.
- **Coordinated omission:** mô hình chỉ gửi request mới sau khi request cũ hoàn tất có thể che giấu latency khi server chậm. Dùng offered load cố định nếu cần đánh giá khả năng chịu tải.
- **Load generator bão hòa:** theo dõi CPU, memory và dropped iterations của generator; chạy nó trên máy riêng khi có thể.
- **Connection pool:** giữ số kết nối, keep-alive và timeout giống nhau giữa baseline và các lần có breaker.
- **GC và cache:** ghi lại GC pause, heap, warm cache/cold cache và không trộn các trạng thái cache khác nhau.
- **Log và metrics:** giữ cùng cấu hình exporter/logging ở các lần so sánh; nếu đang đo overhead của chúng, thay đổi từng yếu tố trong một lượt thử riêng.
- **Concurrency:** giữ cùng số instance, thread và offered load. Với WebFlux, không so sánh một lần chạy event-loop khỏe mạnh với lần chạy có blocking trên event-loop.
- **Trạng thái Circuit Breaker:** xác nhận state trước khi bắt đầu đo từng pha; không gộp mẫu `CLOSED`, chuyển tiếp và `OPEN` vào một percentile duy nhất.
- **Response semantics:** tách HTTP 2xx fallback, 503, 504 và lỗi kết nối; không coi tất cả response có status là phục vụ thành công.

## 11. Tiêu chí đánh giá và quyết định

Đặt tiêu chí trước khi chạy để tránh chọn kết quả thuận mắt:

- Overhead p95/p99 ở `CLOSED` nằm trong ngân sách latency của API.
- CPU-seconds/request và allocation/request không tăng vượt ngân sách tài nguyên.
- Throughput ở offered load mục tiêu không giảm đáng kể ngoài mức chấp nhận của SLO.
- Khi lỗi liên tục, breaker mở sau số mẫu và khoảng thời gian dự kiến; số request phát sinh trong giai đoạn phát hiện nằm trong giới hạn chịu tải.
- Khi `OPEN`, dependency không tiếp tục nhận request mới từ đường đã bảo vệ; fallback đáp ứng SLA.
- Khi `HALF_OPEN`, tổng probe trên toàn bộ instance không gây quá tải dependency đang hồi phục.
- Không có queue, thread hoặc connection bị giữ lại lâu sau timeout ngoài giới hạn thiết kế.

Nếu overhead `CLOSED` lớn, kiểm tra trước tiên các yếu tố có thể cấu hình: metrics, logging, kích thước sliding window, contention, proxy và cách gọi. Nếu đường `OPEN` chậm, đo riêng fallback/cache và serialization. Nếu lỗi liên tục làm hệ thống cạn thread, kiểm tra timeout và Bulkhead; chỉ mở Circuit Breaker không tự dừng các request đã được gửi.

## 12. Mẫu báo cáo kết quả

Ghi kết quả mỗi lượt chạy cùng metadata để có thể lặp lại:

| Trường | Giá trị cần ghi |
| --- | --- |
| Build | Git revision, Spring Boot, Spring Cloud, Resilience4j, JDK |
| Runtime | CPU/memory limit, JVM flags, số instance, container/VM |
| Workload | Offered rate, concurrency, payload, thời lượng, warm-up |
| Dependency | Stub mode, latency, error rate, timeout và connection pool |
| Circuit Breaker | Window type/size, minimum calls, threshold, wait duration, half-open permits |
| Kết quả | Throughput, p50/p95/p99, error ratio, CPU/request, GC, thread/queue |
| Bảo vệ | Thời điểm OPEN, dependency request count, not-permitted, fallback, probe count |

Không công bố một con số overhead duy nhất nếu không kèm cấu hình, tải, phần cứng, phiên bản và phương pháp đo. Báo cáo nên nêu cả median giữa các lần chạy và độ dao động giữa các lần chạy.

## Tài liệu tham khảo

- [Resilience4j – CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker): sliding window, minimum calls, failure threshold và các trạng thái.
- [Resilience4j – Micrometer](https://resilience4j.readme.io/docs/micrometer): metrics Circuit Breaker và cách quan sát lời gọi.
- [OpenJDK JMH](https://github.com/openjdk/jmh): framework benchmark JVM, warm-up, fork, measurement và profiler.
- [Grafana k6 – Constant arrival rate executor](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/): tạo offered load theo tốc độ request cố định.
- [Spring Boot – Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): Micrometer, HTTP server metrics và histogram.
