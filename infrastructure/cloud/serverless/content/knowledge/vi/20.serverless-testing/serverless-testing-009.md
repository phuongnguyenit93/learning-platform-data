# Load test cho cold start, concurrency và giới hạn downstream

Ứng dụng serverless có thể mở rộng nhanh khi lưu lượng tăng, nhưng tốc độ scale không đồng nghĩa mọi thành phần phía sau đều có thể chịu tải tương ứng. Một Java function có thể khởi động chậm khi tạo execution environment mới, tăng số invocation đồng thời trong vài giây và mở hàng loạt kết nối tới database hoặc API bên ngoài. Nếu chỉ đo throughput trung bình, nhóm phát triển có thể bỏ sót cold start, tail latency, throttling và tình trạng downstream quá tải.

Load test cho serverless cần trả lời ba câu hỏi:

1. **Cold start:** request đầu tiên trên một execution environment mới mất bao lâu, và tỷ lệ request bị ảnh hưởng là bao nhiêu?
2. **Concurrency:** function scale đến mức nào trước khi latency, error rate hoặc throttling vượt SLO?
3. **Downstream limits:** database, connection pool, API đối tác, queue hoặc KMS chịu được bao nhiêu request/kết nối trước khi trở thành nút thắt?

Bài học này trình bày cách thiết kế workload, tách cold và warm start, ước tính concurrency, mô phỏng tải HTTP và queue, giới hạn áp lực lên dependency, thu thập metrics và diễn giải kết quả. Ví dụ dùng Java serverless và k6; các nguyên tắc áp dụng được cho AWS Lambda, Azure Functions, Google Cloud Functions/Cloud Run và những nền tảng FaaS tương tự.

## 1. Load test serverless khác gì kiểm thử ứng dụng luôn chạy?

Với server chạy cố định, nhóm thường kiểm tra số request mỗi giây mà một cụm instance xử lý được. Serverless thêm một số biến số:

- Nền tảng tạo hoặc tái sử dụng execution environment theo lưu lượng và cấu hình.
- Request có thể chờ quá trình khởi tạo runtime, tải class, khởi tạo framework và kết nối dependency.
- Concurrency tăng có thể tạo nhiều JVM/process/container và nhiều connection pool độc lập.
- Nền tảng có giới hạn concurrency, scale rate, quota và thời gian thực thi.
- Trigger khác nhau có semantics khác nhau: HTTP trả response trực tiếp, queue có backlog và retry, stream có partition/shard và checkpoint.
- Chi phí có thể tăng theo số invocation, thời gian chạy, memory/CPU, request tới dịch vụ phụ thuộc và lưu lượng mạng.

Do đó, cần đo cả function lẫn toàn bộ đường đi của request. Một handler có thể xử lý nhanh trong JVM nhưng tổng thời gian vẫn cao do cold start, DNS/TLS, chờ connection pool hoặc API đối tác chậm.

### Bốn nhóm kết quả cần tách riêng

| Nhóm | Câu hỏi cần trả lời | Ví dụ chỉ số |
|---|---|---|
| Latency | Request mất bao lâu từ client tới kết quả cuối? | p50, p95, p99 end-to-end và duration của function |
| Capacity | Hệ thống xử lý ổn định bao nhiêu tải? | RPS, throughput, concurrency, queue drain rate |
| Reliability | Tải làm phát sinh bao nhiêu lỗi? | 5xx, timeout, throttling, retry, dropped iterations |
| Resource/cost | Tài nguyên và dependency bị sử dụng thế nào? | CPU, memory, DB connections, API quota, invocation cost |

Không kết luận hệ thống đạt yêu cầu chỉ vì throughput cao. Nếu p99 vượt SLO hoặc downstream bị throttling, hệ thống chưa đạt mục tiêu vận hành.

## 2. Xác định mục tiêu trước khi tạo tải

Load test có ích khi bắt đầu từ một giả thuyết và tiêu chí pass/fail cụ thể. Ví dụ:

> Khi tải tăng từ 50 lên 300 request/giây, Java HTTP function phải giữ p95 dưới 500 ms, tỷ lệ lỗi dưới 1%, không vượt giới hạn 80 kết nối database và không làm queue age tăng liên tục.

Các con số trên chỉ minh họa. SLO thật phải xuất phát từ yêu cầu sản phẩm, quota dịch vụ và ngân sách của dependency.

Trước khi chạy, xác định:

1. **Workload:** endpoint hoặc event nào được gọi, tỷ lệ đọc/ghi, kích thước payload và fan-out tới dịch vụ phía sau.
2. **Traffic profile:** tải bình thường, giờ cao điểm, burst, lịch định kỳ và tỷ lệ tăng trưởng dự kiến.
3. **SLO:** latency p95/p99, tỷ lệ lỗi, thời gian xử lý queue và độ trễ cold start chấp nhận được.
4. **Dependency budget:** giới hạn request/giây, concurrent connection, transaction, quota và timeout của database/API.
5. **Scale limits:** max concurrency/instances, reserved concurrency, queue dispatch rate hoặc giới hạn scale-out của hosting plan.
6. **Test boundary:** môi trường, account/project, dữ liệu thử, thời gian chạy, chi phí tối đa và người trực theo dõi.

### Ma trận workload

| Profile | Mô tả | Mục đích |
|---|---|---|
| Baseline | Lưu lượng thấp, ổn định | Đo latency và tài nguyên khi hệ thống bình thường |
| Ramp/load | Tăng dần đến tải mục tiêu | Xác định capacity và ngưỡng bắt đầu suy giảm |
| Spike | Tăng tải đột ngột | Quan sát tốc độ scale, cold start và khả năng bảo vệ downstream |
| Stress | Tăng vượt tải dự kiến | Xác định giới hạn và cách hệ thống thất bại |
| Soak | Giữ tải ổn định trong thời gian dài | Phát hiện rò rỉ, pool exhaustion, backlog và drift theo thời gian |
| Recovery | Giảm tải sau stress/spike | Đo thời gian phục hồi và xử lý backlog |
| Dependency limit | Giới hạn DB/API giả lập hoặc thật trong sandbox | Xác minh backpressure, timeout, retry và circuit breaker |

Không bắt đầu bằng stress test cực đại. Chạy baseline, kiểm tra tải sinh ra đúng như dự kiến rồi mới tăng dần để dễ xác định nguyên nhân.

## 3. Hiểu cold start và warm start

Cold start xảy ra khi nền tảng cần tạo execution environment mới hoặc khởi tạo lại runtime trước khi xử lý invocation. Với Java, các công việc có thể góp phần vào startup time gồm:

- Tạo process/container và khởi động JVM.
- Nạp class, resolve dependency và thực hiện static initialization.
- Khởi tạo dependency injection container như Spring.
- Tạo client SDK, HTTP connection pool, database pool hoặc TLS context.
- Nạp configuration/secret và thực hiện health/init logic.
- Với một số cấu hình, restore snapshot hoặc khởi tạo runtime bổ sung.

Warm invocation dùng execution environment đã khởi tạo trước đó nên thường tránh được phần lớn chi phí startup. Tuy nhiên, warm không bảo đảm mọi request có latency như nhau: GC, JIT compilation, pool contention, network và tải downstream vẫn có thể làm request chậm.

### Cold start không phải một con số cố định

Cold start phụ thuộc runtime, memory/CPU, framework, kích thước artifact, vùng triển khai, dependency và cấu hình scale. Một ứng dụng Java dùng framework nặng có thể có startup profile khác đáng kể so với một handler Java nhỏ không dùng DI container.

Không chỉ so sánh average. Hãy báo cáo phân phối cold start riêng: p50, p95, p99, min/max và số mẫu. Cold start có thể chỉ chiếm một tỷ lệ nhỏ tổng request nhưng vẫn làm p99 vượt SLO.

### Đo cold start trên AWS Lambda

Với Lambda, log `REPORT` trong CloudWatch Logs có thể hiển thị `Init Duration` cho invocation có giai đoạn initialization được ghi nhận. Với SnapStart, log có thể cung cấp thông tin restore tương ứng như `Restore Duration`. Cần phân tích đúng log/runtime version và loại invocation; không suy luận mọi request thiếu trường `Init Duration` đều đại diện cho một cold start có cùng điều kiện.

Các metric hữu ích gồm:

- `Duration`: thời gian thực thi handler, không bao gồm toàn bộ thời gian client nhìn thấy.
- `ConcurrentExecutions`: số invocation đồng thời.
- `Throttles`: invocation bị giới hạn.
- `Errors`: invocation lỗi.
- `Invocations`: số lần gọi.
- `ProvisionedConcurrencySpilloverInvocations`: request vượt phần provisioned concurrency và phải dùng concurrency khác.

Để đo end-to-end, client load generator phải ghi thời gian từ lúc gửi request đến lúc nhận response. Kết hợp client timing với log initialization và trace để tách startup, handler và dependency latency.

### Đo cold start trên các nền tảng khác

Với Cloud Run, cold start có thể xuất hiện khi tạo instance mới hoặc scale từ zero; request latency và telemetry startup/instance cần được đối chiếu với instance count và cấu hình min instances. Với Azure Functions, hành vi phụ thuộc hosting plan, worker model và scale controller; hãy dùng telemetry của host/Application Insights cùng request timing. Tên metric và mức chi tiết khác nhau giữa plan/runtime, vì vậy cần xác nhận bằng tài liệu và dashboard đúng nền tảng.

Không dùng một metric duy nhất của cloud để đại diện cho mọi cold start. Ghi nhận cả thời điểm request, instance/environment ID nếu telemetry hỗ trợ, thời gian init và thời gian xử lý handler.

## 4. Thiết kế phép đo cold start đúng cách

Cold start khó đo hơn warm start vì nền tảng có thể tái sử dụng environment. Gửi nhiều request liên tiếp tới cùng endpoint thường tạo ra phần lớn warm invocation, không tạo ra một cold start mới cho mỗi request.

### Tách hai thí nghiệm

**Thí nghiệm warm:**

1. Gửi một đợt request để tạo và khởi tạo environment.
2. Chờ đến khi traffic ổn định.
3. Duy trì tải trong khoảng thời gian đã định.
4. Đo p50/p95/p99, throughput, handler duration và dependency latency.

**Thí nghiệm cold/scale-out:**

1. Dùng môi trường thử nghiệm riêng với cấu hình gần production.
2. Đặt min instances/provisioned concurrency bằng 0 nếu mục tiêu là đo scale-from-zero và nền tảng cho phép.
3. Tạo các đợt traffic cách nhau đủ để environment có cơ hội bị thu hồi theo chính sách nền tảng, hoặc dùng một deployment/environment riêng cho mỗi đợt khi cần cô lập.
4. Tăng tải đột ngột để quan sát việc tạo environment mới và startup distribution.
5. Gắn correlation ID và đối chiếu client timing với startup logs/traces.

Idle period không bảo đảm nền tảng sẽ thu hồi environment ngay lập tức. Không thể ép một request cụ thể chắc chắn là cold start chỉ bằng cách chờ một khoảng cố định. Nếu cần đo từng lần khởi tạo, dùng deployment/target cô lập hoặc telemetry nhận diện environment mới, đồng thời ghi rõ giới hạn của phương pháp.

### Tránh làm sai lệch kết quả

- Không bật provisioned concurrency/min instances trong thí nghiệm đo scale-from-zero nếu mục tiêu là cold start tự nhiên.
- Chạy riêng một thí nghiệm khác để đánh giá provisioned concurrency hoặc min instances.
- Không trộn cold request với warm request rồi báo một average duy nhất.
- Không dùng một lần chạy nhỏ làm kết luận về p99; cần đủ mẫu cold start.
- Giữ cùng artifact, memory/CPU, region, network và dependency giữa các lần so sánh.
- Ghi lại trạng thái JIT, cache và connection pool vì chúng có thể làm warm latency thay đổi theo thời gian.
- Kiểm tra tải generator không phải nút thắt.

### So sánh chiến lược giảm cold start

| Chiến lược | Tác động kỳ vọng | Điều cần đo |
|---|---|---|
| Tăng memory/CPU | Có thể rút ngắn init và handler startup | Init duration, cost/invocation và CPU profile |
| Giảm dependency/classpath | Giảm class loading và initialization | Startup distribution, artifact size |
| Lazy initialization | Chuyển một phần init ra khỏi đường request đầu tiên hoặc chỉ khởi tạo khi cần | First-use latency và warm latency |
| Native image/AOT nếu runtime hỗ trợ | Có thể giảm startup, đổi trade-off build/memory | Startup, throughput, compatibility và memory |
| AWS Lambda SnapStart | Restore environment từ snapshot theo runtime hỗ trợ | Restore duration, hook behavior và request latency |
| Provisioned concurrency/min instances | Giữ capacity đã khởi tạo sẵn | Cold-start rate, spillover, idle cost và scale burst |

Không tối ưu cold start chỉ bằng cách tăng tài nguyên. Nếu p99 chủ yếu do database hoặc API đối tác, startup nhanh hơn có thể không cải thiện end-to-end latency.

## 5. Ước tính concurrency trước khi chạy test

Một ước tính đơn giản dựa trên định luật Little:

\[
L = \lambda \times W
\]

Trong đó:

- `L` là số request trung bình đang ở trong hệ thống (concurrency/in-flight work).
- `λ` là throughput, ví dụ request mỗi giây.
- `W` là thời gian xử lý trung bình tính bằng giây.

Ví dụ, nếu endpoint nhận 200 request/giây và thời gian xử lý trung bình là 0,4 giây:

\[
L = 200 \times 0.4 = 80
\]

Hệ thống cần khoảng 80 request đang xử lý đồng thời ở trạng thái ổn định. Khi latency tăng, concurrency cũng tăng nếu arrival rate giữ nguyên. Vì vậy, một downstream chậm có thể khiến nhiều invocation cùng tồn tại lâu hơn, làm áp lực lên connection pool tăng theo.

Đây là ước lượng trung bình. Capacity planning cần thêm headroom cho burst, phân phối latency, fan-out, retry và giới hạn nền tảng.

### Tính fan-out tới downstream

Một invocation có thể gọi nhiều request downstream. Nếu mỗi invocation gọi 3 API và 1 truy vấn database, concurrency ở dependency không bằng concurrency của function.

Ví dụ:

- 80 invocation đồng thời.
- Mỗi invocation tạo tối đa 2 request song song tới API A.
- Mỗi invocation giữ 1 DB connection trong thời gian xử lý.

Khi đó API A có thể thấy tới khoảng 160 request đồng thời, còn database có thể thấy tới khoảng 80 connection được giữ bởi worker, chưa tính connection từ service khác.

Hãy lập bảng fan-out cho từng dependency, tính cả retry và tác vụ nền được khởi chạy từ handler.

## 6. Tính connection budget cho database và API

Mỗi execution environment/container có thể sở hữu pool kết nối riêng. Tổng connection tiềm năng là tổng pool của mọi instance đang hoạt động.

Ước lượng an toàn:

\[
Connections_{max} \approx Instances_{max} \times PoolSize_{per\ instance}
\]

Ví dụ, Cloud Run được phép chạy tối đa 20 instance và mỗi instance có HikariCP pool tối đa 8 connection:

\[
20 \times 8 = 160\ connections
\]

Nếu database chỉ dành 100 connection cho ứng dụng, cấu hình này có thể vượt ngân sách ngay cả khi mỗi instance hoạt động đúng. Cần tính thêm connection quản trị, migration, dashboard, service khác và headroom.

Với Lambda, concurrency tối đa có thể gần bằng số execution environment đồng thời cho một function thông thường. Nếu mỗi environment mở một pool có thể giữ tối đa 5 connection, upper bound lý thuyết là concurrency nhân 5. Pool thực tế có thể mở lười, nhưng không nên dựa vào điều đó để bỏ qua giới hạn.

### Java HikariCP: đặt pool có giới hạn

```java
import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

public final class DataSources {
    private static final HikariDataSource DATA_SOURCE = create();

    private DataSources() {}

    private static HikariDataSource create() {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(System.getenv("JDBC_URL"));
        config.setUsername(System.getenv("DB_USERNAME"));
        config.setPassword(System.getenv("DB_PASSWORD"));
        config.setMaximumPoolSize(2);
        config.setMinimumIdle(0);
        config.setConnectionTimeout(1500);
        config.setValidationTimeout(500);
        config.setPoolName("orders-worker-pool");
        return new HikariDataSource(config);
    }

    public static HikariDataSource get() {
        return DATA_SOURCE;
    }
}
```

Ví dụ chỉ minh họa pool nhỏ cho một execution environment. `maximumPoolSize=2` không phải giá trị phù hợp cho mọi ứng dụng. Chọn theo concurrency toàn hệ thống, số instance tối đa và connection budget của database. Không tạo HikariDataSource mới cho mỗi invocation; tái sử dụng pool trong execution environment và đóng connection sau mỗi thao tác.

Với Lambda kết nối Amazon RDS, cân nhắc RDS Proxy khi phù hợp. Proxy có thể giảm số kết nối database trực tiếp và quản lý pooling, nhưng transaction, session state hoặc một số câu lệnh có thể làm connection bị pin. Vẫn phải load test số client connection, backend connection và tỷ lệ pinning.

### Pool không thay thế giới hạn concurrency

Nếu mỗi instance có pool 2 connection nhưng nền tảng scale lên 500 instance, database vẫn có thể nhận hàng trăm connection. Cần phối hợp:

- Giới hạn tổng concurrency của function/service.
- Giới hạn max instances hoặc concurrency per instance.
- Đặt pool nhỏ và timeout chờ pool hữu hạn.
- Dùng proxy/pooler khi phù hợp.
- Cache dữ liệu đọc an toàn nếu có thể.
- Giảm transaction dài và fan-out không cần thiết.

## 7. Giới hạn downstream và backpressure

Serverless có thể scale nhanh hơn khả năng phục vụ của dependency. Ví dụ một API đối tác chỉ cho phép 100 request/giây, nhưng function có thể tạo 500 request/giây khi burst. Nếu không giới hạn, hệ thống sẽ tạo 429/5xx, retry và làm tải tăng thêm.

Backpressure là cách làm chậm hoặc từ chối tiếp nhận công việc khi downstream gần chạm giới hạn. Các cơ chế thường dùng:

1. **Concurrency cap:** giới hạn số invocation hoặc instance đồng thời.
2. **Rate limit:** giới hạn request mỗi giây tới một dependency.
3. **Bounded connection pool:** giới hạn connection và thời gian chờ lấy connection.
4. **Queue:** tách producer khỏi consumer và dispatch theo tốc độ downstream chịu được.
5. **Bulkhead:** cô lập tài nguyên theo dependency để một hệ thống chậm không chiếm toàn bộ worker.
6. **Circuit breaker:** tạm ngừng gọi dependency đang lỗi liên tục, sau đó thử lại có kiểm soát.
7. **Timeout và retry budget:** giới hạn thời gian và số lần thử, dùng backoff/jitter.

### Không retry mọi lỗi

Phân loại lỗi trước khi retry:

| Lỗi | Hành vi gợi ý |
|---|---|
| Network timeout hoặc lỗi tạm thời | Retry có giới hạn, exponential backoff và jitter |
| HTTP 429 | Tôn trọng `Retry-After` nếu có, giảm tốc độ và giới hạn concurrency |
| HTTP 5xx | Retry có giới hạn nếu thao tác idempotent |
| HTTP 400/validation | Không retry; sửa payload hoặc đánh dấu lỗi nghiệp vụ |
| HTTP 401/403 | Không retry liên tục; kiểm tra credential/permission |
| Database connection pool exhausted | Giảm concurrency, timeout chờ hữu hạn và điều tra pool budget |
| Quota exceeded | Điều tiết tải hoặc yêu cầu tăng quota có kiểm soát |

Nếu SDK retry 3 lần, application retry 3 lần và queue redelivery 5 lần, một message có thể tạo nhiều lần gọi downstream hơn dự kiến. Xác định tầng sở hữu retry, tổng retry budget và idempotency key.

### Ví dụ giới hạn fan-out trong Java

```java
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;

public final class PartnerApiGate {
    // Giới hạn song song trong một execution environment.
    private static final Semaphore PER_INSTANCE = new Semaphore(4);

    public <T> T call(CheckedSupplier<T> operation) throws Exception {
        boolean acquired = PER_INSTANCE.tryAcquire(100, TimeUnit.MILLISECONDS);
        if (!acquired) {
            throw new DownstreamBusyException("Partner API concurrency budget reached");
        }

        try {
            return operation.get();
        } finally {
            PER_INSTANCE.release();
        }
    }

    @FunctionalInterface
    public interface CheckedSupplier<T> {
        T get() throws Exception;
    }

    public static final class DownstreamBusyException extends RuntimeException {
        public DownstreamBusyException(String message) {
            super(message);
        }
    }
}
```

Semaphore này chỉ giới hạn concurrency bên trong một JVM/instance. Nếu nền tảng chạy 50 instance, tổng số request vẫn có thể đạt 200. Để giới hạn toàn hệ thống, kết hợp platform concurrency cap, queue dispatch rate hoặc một distributed rate limiter được thiết kế phù hợp. Đặt timeout cho HTTP client riêng; semaphore không tự dừng một call bị treo.

## 8. Chọn open workload hay closed workload

Load generator có thể tạo tải theo hai mô hình:

- **Closed model:** cố định số virtual users; mỗi user gửi request rồi đợi response trước khi gửi tiếp.
- **Open model:** cố định arrival rate; request mới được tạo theo tốc độ đặt trước, bất kể request trước đã hoàn thành chưa.

Closed model hữu ích khi mô phỏng một số lượng người dùng đồng thời. Nhưng khi service chậm, mỗi VU gửi ít request hơn nên offered load giảm. Điều này có thể che giấu tình trạng quá tải. Open model phù hợp để kiểm tra hệ thống có chịu được một arrival rate cố định không; nếu service chậm, số request đang chờ tăng lên và hệ thống bộc lộ vấn đề.

Đối với API có traffic đến theo sự kiện hoặc request burst, nên có ít nhất một bài test open-model. Kiểm tra cả `dropped_iterations` hoặc chỉ số tương tự của load generator để biết công cụ có tạo đủ tải hay không.

## 9. Ví dụ load test HTTP bằng k6

k6 hỗ trợ mô hình arrival-rate, ramping, thresholds và custom tags. Ví dụ sau tăng dần request rate tới endpoint tạo job. Các ngưỡng latency là placeholder; thay bằng SLO của hệ thống.

```javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    orders_api: {
      executor: 'ramping-arrival-rate',
      startRate: 10,
      timeUnit: '1s',
      preAllocatedVUs: 30,
      maxVUs: 300,
      stages: [
        { target: 25, duration: '2m' },
        { target: 50, duration: '3m' },
        { target: 100, duration: '3m' },
        { target: 150, duration: '3m' },
        { target: 0, duration: '1m' }
      ]
    }
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500', 'p(99)<1000'],
    dropped_iterations: ['count<1']
  }
};

export default function () {
  const runId = __ENV.TEST_RUN_ID;
  const baseUrl = __ENV.BASE_URL;
  const payload = JSON.stringify({
    testRunId: runId,
    requestId: `${__VU}-${__ITER}`,
    orderType: 'load-test'
  });

  const response = http.post(`${baseUrl}/api/orders`, payload, {
    headers: {
      'Content-Type': 'application/json',
      'X-Load-Test': runId
    },
    tags: { test_run: runId }
  });

  check(response, {
    'accepted or created': (res) => res.status === 202 || res.status === 201
  });
}
```

Chạy trong môi trường test bằng biến môi trường được cấp riêng:

```bash
k6 run -e BASE_URL=https://test-api.example.internal \
  -e TEST_RUN_ID=serverless-capacity-001 orders-load.js
```

Script gửi tải theo arrival rate. `preAllocatedVUs` và `maxVUs` cần đủ để tạo rate đã định; nếu VU không đủ, k6 có thể ghi nhận dropped iterations. Kiểm tra CPU/memory của load generator và kết quả k6 trước khi kết luận serverless bị giới hạn.

### Test cold start riêng

Không thể đảm bảo mỗi iteration của script trên là cold start. Dùng script này để tạo traffic burst sau khi môi trường được scale về zero hoặc sau khi triển khai một target thử mới; đối chiếu từng request với platform logs để phân loại cold/warm.

```javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 1,
  iterations: 20,
  thresholds: {
    http_req_failed: ['rate<0.01']
  }
};

export default function () {
  const response = http.get(`${__ENV.BASE_URL}/health/ready`, {
    headers: { 'X-Load-Test': __ENV.TEST_RUN_ID }
  });
  check(response, { 'health is ready': (res) => res.status === 200 });
  sleep(2);
}
```

Đoạn script này đo latency của các request được gửi cách nhau, nhưng không tự chứng minh request nào là cold. Dùng nó cùng telemetry instance/init và thử nghiệm scale-from-zero có kiểm soát. Để đo burst cold scale-out, tăng VU/rate và xem số instance mới được tạo; để đo warm, duy trì tải sau khi hệ thống đã ổn định.

## 10. Load test queue-triggered function

Với queue trigger, chỉ đo thời gian producer gửi message là chưa đủ. Cần đo thời gian từ lúc message được enqueue đến khi worker hoàn tất, throughput consumer, backlog và tuổi message lâu nhất.

Các chỉ số quan trọng:

- Messages sent/received/deleted.
- Queue depth hoặc số message visible/not visible.
- Age of oldest message.
- Lambda/Function invocation, concurrency, duration, errors và throttles.
- Số record xử lý thành công, retry, duplicate và DLQ.
- Thời gian end-to-end từ enqueue tới business completion.
- Connection/throughput của downstream database/API.

### Thiết kế test queue

1. Sinh message có `testRunId`, `eventId` duy nhất và payload gần kích thước production.
2. Tăng producer rate theo từng nấc, ví dụ 10, 25, 50, 100 message/giây.
3. Cấu hình queue/trigger với batch size và concurrency cap tương ứng workload.
4. Worker xử lý idempotent và ghi completion timestamp vào nơi có thể đo.
5. Theo dõi queue age, backlog, worker concurrency và downstream.
6. Dừng producer, tiếp tục đo thời gian queue drain về mức bình thường.
7. Kiểm tra DLQ và xác nhận không có message bị mất hoặc xử lý trùng ngoài dự kiến.

Với SQS và Lambda, `MaximumConcurrency` của event source mapping hoặc reserved concurrency có thể được dùng để điều tiết consumer. Với Azure Queue/Service Bus trigger hoặc Google Cloud Tasks/Pub/Sub, dùng cơ chế concurrency/dispatch tương ứng của dịch vụ. Không giả định batch size, ordering hoặc retry giống nhau giữa các nền tảng.

### Throughput của batch consumer

Một ước lượng gần đúng cho queue worker:

\[
Throughput \approx \frac{ConcurrentInvocations \times BatchSize}{AverageBatchDuration}
\]

Ví dụ 10 invocation đồng thời, batch size 5 và thời gian xử lý batch 2 giây cho throughput lý thuyết khoảng 25 message/giây. Thực tế còn phụ thuộc thời gian xử lý từng record, partial batch failures, giới hạn poller, downstream và thời gian message bị ẩn.

Nếu mỗi message tạo nhiều truy vấn hoặc API call, tính dependency load theo số record và fan-out, không chỉ theo số invocation.

## 11. Metrics và tracing cần thu thập

Load test cần một bộ quan sát thống nhất từ client tới dependency.

| Lớp | Metrics/log/traces |
|---|---|
| Load generator | Offered RPS, completed RPS, VU, dropped iterations, p50/p95/p99, network errors |
| API/gateway | Request count, 4xx/5xx, 429, latency, throttling, auth failures |
| Function platform | Invocations, concurrency, duration, errors, throttles, init/restore, memory, CPU/instance count |
| Java runtime | Startup phase, GC pause, heap, thread count, connection pool active/idle/pending |
| Queue | Visible/not-visible messages, age of oldest, receive/delete, retry, DLQ |
| Database | Active connections, pool wait, CPU, IOPS, lock wait, query latency, transaction errors |
| External API | RPS, 429/5xx, latency, timeout, quota usage |
| KMS/secret service | Request count, throttling, AccessDenied, latency và retry |

### Phân biệt platform duration và end-to-end latency

Function duration thường chỉ đo phần thực thi mà nền tảng ghi nhận. Client còn chịu DNS, TLS handshake, gateway, network, cold start hoặc thời gian queue chờ trước khi worker bắt đầu. Với queue, request producer có thể trả thành công ngay nhưng công việc còn chờ trong backlog.

Đặt correlation ID hoặc trace ID xuyên suốt. Với HTTP, ghi timestamp tại client, gateway, handler và dependency. Với queue, truyền event ID và timestamp enqueue, rồi ghi completion timestamp. Không log payload nhạy cảm để phục vụ load test.

### Đo tail latency

Báo cáo p50, p90, p95, p99 và nếu đủ mẫu thì p99.9. Average có thể che giấu một nhóm nhỏ request bị cold start hoặc chờ pool lâu. Khi so sánh hai cấu hình, giữ workload và số mẫu tương đương, đồng thời ghi rõ confidence/biến động giữa các lần chạy.

## 12. Thiết kế test cho giới hạn concurrency

Mục tiêu là xác định điểm mà tăng concurrency không còn cải thiện throughput hoặc bắt đầu làm SLO xấu đi.

Một quy trình:

1. Bắt đầu ở concurrency thấp và đo baseline.
2. Tăng arrival rate theo nấc, giữ mỗi nấc đủ lâu để autoscaling ổn định.
3. Ghi nhận actual concurrency, số instance, throughput và p95/p99.
4. Tìm điểm đầu tiên có throttling, queue age tăng, error rate tăng hoặc downstream pool wait tăng.
5. Giảm tải để xác nhận hệ thống phục hồi.
6. Lặp lại với max concurrency/instance limit khác để đánh giá trade-off.

Các giới hạn nền tảng cần ghi lại:

- AWS Lambda: account/function concurrency, reserved concurrency, provisioned concurrency, event source mapping maximum concurrency và quota liên quan.
- Cloud Run: maximum instances, concurrency per instance, minimum instances và CPU/memory allocation.
- Azure Functions: hosting plan, scale-out limit, per-instance concurrency và giới hạn trigger/worker tương ứng.

Tên cấu hình và semantics thay đổi theo plan/runtime/region. Đọc cấu hình thực tế và quota account trước khi test; đừng dựa vào default không được ghi nhận.

### Concurrency cap nên dựa trên dependency budget

Nếu database chỉ dành 60 connection cho worker và mỗi instance có pool tối đa 3 connection, giới hạn instance ban đầu có thể được suy ra từ budget đó, sau khi trừ headroom và connection từ hệ thống khác. Nếu function gọi API ngoài có rate limit 100 RPS, cần tính cả concurrency và thời gian trung bình của call để chọn cap. Có thể cần rate limiter thay vì chỉ concurrency cap vì latency API biến động.

Không đặt max concurrency bằng giới hạn account rồi hy vọng downstream tự điều tiết. Concurrency platform là một trong những hàng rào bảo vệ quan trọng nhất cho dependency.

## 13. Test timeout, retry và overload behavior

Một hệ thống serverless có thể thất bại theo nhiều cách khi quá tải:

- Function bị throttled trước khi chạy.
- Request chờ gateway rồi timeout.
- Connection pool hết chỗ và handler chờ quá lâu.
- Database/API trả 429 hoặc 5xx.
- Function timeout sau khi đã tạo side effect.
- Queue retry làm cùng message được xử lý lại.
- Retry ở nhiều tầng khuếch đại tải.

Hãy thử các trường hợp có kiểm soát:

| Kịch bản | Cách tạo | Kết quả mong đợi |
|---|---|---|
| Function concurrency cap | Giảm cap trong môi trường test và tăng RPS | Có throttling có thể dự đoán; client retry theo policy; downstream không bị quá tải |
| DB pool exhaustion | Hạ pool size hoặc giảm DB connection budget trong sandbox | Pool wait có timeout; không treo vô hạn; error được phân loại |
| API 429 | Mock server trả 429 sau ngưỡng RPS | Client giảm tốc độ, tôn trọng Retry-After và không tạo retry storm |
| API timeout | Mock server trì hoãn response vượt timeout client | Call bị hủy/timeout, thread không bị giữ vô hạn |
| Function timeout | Dùng handler test có thời gian chạy vượt timeout | Quan sát retry/redelivery và xác nhận idempotency |
| Queue backlog | Producer nhanh hơn consumer trong thời gian giới hạn | Queue age tăng có thể dự đoán và giảm sau khi dừng producer |
| Recovery | Khôi phục dependency sau khi lỗi | Backlog drain và latency trở về baseline |

Không tạo lỗi bằng cách làm hỏng dependency production. Dùng mock/stub, sandbox hoặc quota được cấp riêng để kiểm tra overload.

## 14. Kiểm tra autoscaling và recovery

Autoscaling cần đủ thời gian để scale-out, nhưng downstream có thể đã bị dồn tải trước khi instance mới sẵn sàng. Đo:

- Thời gian từ lúc arrival rate tăng đến khi instance/concurrency tăng.
- Tỷ lệ request được xử lý bởi environment mới.
- Thời gian từ peak load đến khi backlog giảm.
- Số instance còn hoạt động sau khi tải giảm.
- Số connection còn mở và thời gian pool co lại.
- Số lỗi/throttle còn kéo dài sau khi dependency phục hồi.

Với queue, đo queue drain time sau khi producer dừng. Với HTTP, đo thời gian latency và error rate trở về baseline. Với scheduled workload, kiểm tra các lần chạy tiếp theo có bị chồng lấn với backlog cũ không.

### Test min instances/provisioned capacity riêng

Nếu sản phẩm yêu cầu latency thấp ở request đầu tiên, chạy một test riêng với min instances/provisioned concurrency. So sánh:

- Cold-start rate và p95/p99.
- Thời gian scale-out khi vượt capacity đã provision.
- Spillover/concurrency ngoài phần provisioned.
- Chi phí idle khi không có traffic.
- Khả năng xử lý burst lớn hơn capacity giữ ấm.

Provisioned capacity giảm một số cold start nhưng không xóa bỏ giới hạn downstream hoặc startup của các instance vượt mức đã provision.

## 15. Kết quả và cách tìm bottleneck

Không nhìn một metric đơn lẻ. Ghép các tín hiệu để tìm thành phần giới hạn.

| Dấu hiệu | Khả năng nguyên nhân | Hướng kiểm tra |
|---|---|---|
| Client p99 cao, function duration thấp | Gateway, network, cold start hoặc queue delay | So sánh client timing, init log, trace và queue age |
| Init duration cao, warm duration tốt | JVM/framework/classpath/startup logic | Profile class loading, DI, static init, artifact và memory |
| Concurrency tăng, DB connections chạm cap | Pool per instance quá lớn hoặc max instances quá cao | Tính lại connection budget, dùng proxy/pooler, giảm concurrency |
| Throughput đứng yên, p95 tăng, DB CPU/lock cao | Database là bottleneck | Query plan, index, transaction, connection và write contention |
| Function throttles, downstream còn rảnh | Function/account concurrency cap hoặc quota | Kiểm tra reserved/max concurrency và account quota |
| API 429 tăng cùng retry count | Rate limit đối tác và retry storm | Giảm dispatch rate, tôn trọng Retry-After, bounded retry |
| Queue age tăng dù function concurrency cao | Worker chậm, downstream nghẽn hoặc batch lỗi | Xem duration, partial failure, DLQ và dependency latency |
| Dropped iterations ở k6 | Load generator thiếu VU/tài nguyên hoặc rate không đạt | Tăng generator capacity, phân tán generator, kiểm tra CPU/network |
| Latency tăng dần trong soak test | Leak, pool/thread accumulation, GC hoặc cache growth | Heap/GC, connection leak, thread count và memory trend |
| Hệ thống phục hồi chậm sau spike | Backlog, retry schedule hoặc dependency cooldown | Queue drain, retry budget, circuit breaker và scale-in behavior |

### Tìm bottleneck bằng cách thay đổi một biến

Khi thấy latency tăng, không đổi cùng lúc memory, concurrency, pool size và timeout. Thay một biến mỗi lần hoặc dùng ma trận thí nghiệm nhỏ để xác định tác động. Ghi lại cấu hình, artifact hash, region, workload và kết quả để có thể tái lập.

## 16. SLO và ngưỡng pass/fail

Đặt threshold trước khi chạy. Một ví dụ cho HTTP endpoint:

| Chỉ số | Ngưỡng ví dụ |
|---|---:|
| p95 end-to-end latency | Dưới 500 ms |
| p99 end-to-end latency | Dưới 1.000 ms |
| HTTP 5xx + timeout | Dưới 1% |
| Dropped iterations | 0 |
| DB connection usage | Dưới 80% budget dành cho service |
| Downstream 429 | Không tăng liên tục ở tải mục tiêu |
| Queue age | Không vượt SLA xử lý đã định |

Các threshold phải được thay bằng SLO thật. Với API đồng bộ, p95/p99 end-to-end là quan trọng. Với queue worker, queue age và time-to-completion thường có ý nghĩa hơn latency của invocation riêng lẻ.

Một test chỉ pass nếu offered load đạt mức yêu cầu, generator không nghẽn, error rate trong ngưỡng, tail latency đạt SLO và downstream không vượt budget. Nếu load generator không gửi đủ tải, kết quả không chứng minh service chịu được mức tải đó.

## 17. Chi phí và an toàn khi chạy load test

Load test có thể tạo chi phí lớn vì serverless scale tự động và downstream tính phí theo request/connection/throughput. Trước khi chạy:

- Dùng account/project/subscription và dữ liệu test riêng.
- Đặt budget và giới hạn concurrency/instance ở mức đã phê duyệt.
- Đặt rate limit hoặc mock cho API đối tác.
- Dùng dữ liệu tổng hợp, tránh dữ liệu cá nhân hoặc dữ liệu production.
- Đặt TTL/cleanup cho object, queue, database record và log test.
- Xác định cách dừng test ngay khi vượt ngưỡng chi phí hoặc lỗi.
- Báo cho người vận hành nếu test dùng chung dependency trong môi trường staging.
- Không chạy spike/stress lên production hoặc dịch vụ bên thứ ba nếu chưa có phê duyệt và kế hoạch phối hợp.

Theo dõi cost theo run ID/tag nếu nền tảng hỗ trợ. Tính cả function invocation, memory/time, provisioned capacity, log ingestion, database, NAT, KMS request và data transfer.

## 18. Quy trình load test hoàn chỉnh

Một quy trình có thể lặp lại:

1. **Định nghĩa SLO và workload.** Chọn RPS, payload, tỷ lệ thao tác, burst và thời lượng.
2. **Kiểm tra test boundary.** Xác nhận môi trường, quota, data, downstream mock/sandbox, budget và người trực.
3. **Chụp cấu hình.** Ghi runtime, artifact hash, memory/CPU, timeout, concurrency, min instances, pool size, region và queue policy.
4. **Chạy baseline warm.** Đo p50/p95/p99, duration, resource và dependency.
5. **Chạy cold/scale-from-zero.** Tách init/restore khỏi warm request, đủ mẫu và ghi giới hạn đo.
6. **Chạy ramp/load.** Tăng offered rate theo nấc cho tới tải mục tiêu và vượt ngưỡng có kiểm soát.
7. **Chạy spike/stress.** Đo scale-out, throttling và cách hệ thống bảo vệ dependency.
8. **Chạy dependency-limit test.** Giảm quota hoặc mô phỏng 429/timeout/pool exhaustion trong sandbox.
9. **Chạy soak và recovery.** Giữ tải, dừng tải, đo backlog drain và thời gian phục hồi.
10. **Phân tích bottleneck.** Kết hợp client, platform, Java runtime, queue và dependency metrics.
11. **Điều chỉnh một biến.** Thay memory, concurrency, pool hoặc rate limit rồi chạy lại cùng workload.
12. **Lưu báo cáo.** Ghi kết quả, cấu hình, biểu đồ, giới hạn và hành động tiếp theo.

## 19. Checklist trước khi công bố capacity

- [ ] Workload phản ánh request rate, payload size, fan-out và tỷ lệ đọc/ghi thực tế.
- [ ] Có cả open-model và closed-model khi phù hợp.
- [ ] Load generator không phải bottleneck; dropped iterations được kiểm tra.
- [ ] Cold start và warm invocation được phân tích riêng.
- [ ] Đủ mẫu để đánh giá p95/p99 và startup distribution.
- [ ] Đã tính concurrency từ arrival rate và latency, có headroom cho burst.
- [ ] Connection budget tính theo max instances/concurrency nhân pool size.
- [ ] Đã kiểm tra fan-out, retry và rate limit của từng downstream.
- [ ] Queue test đo backlog, oldest-message age và drain time.
- [ ] Timeout, 429, 5xx, throttling và pool exhaustion được mô phỏng an toàn.
- [ ] Có test recovery sau spike và dependency failure.
- [ ] Provisioned capacity/min instances được test riêng nếu sử dụng.
- [ ] SLO và pass/fail threshold được định nghĩa trước.
- [ ] Chi phí, quota, dữ liệu test và quy trình dừng khẩn cấp được kiểm soát.
- [ ] Kết quả lưu kèm artifact/configuration/run ID để tái lập.

## Kết luận

Load test serverless cần đo đồng thời cold start, warm performance, concurrency và sức chịu tải của downstream. Dùng client timing kết hợp platform logs/traces để tách startup khỏi handler; dùng định luật Little và connection budget để ước tính concurrency; chạy open-arrival workload để kiểm tra offered rate; và theo dõi queue age, pool wait, throttling cùng dependency latency. Một thiết kế đạt yêu cầu phải giữ SLO khi tải mục tiêu, giới hạn được áp lực lên database/API và phục hồi sau burst mà không tạo retry storm. Hãy ghi lại cấu hình và workload để mỗi lần tối ưu Java function đều có thể so sánh bằng phép đo tái lập.
