# Đo tải bằng dịch vụ thật trước khi điều chỉnh cấu hình sản xuất

## Mục tiêu học tập

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, Spring Boot kết nối với database, cache, messaging, object storage và compute managed của AWS, Azure và Google Cloud. Mỗi dịch vụ có độ trễ mạng, giới hạn tài nguyên, quota, autoscaling và mô hình tính phí riêng. Một cấu hình chạy tốt với mock hoặc emulator chưa chắc đạt cùng hiệu năng khi ứng dụng gọi dịch vụ managed thật.

Bài học hướng dẫn cách đo tải có kiểm soát trước khi thay đổi cấu hình production:

1. Xây dựng workload model từ traffic, user journey, dữ liệu và SLO thực tế.
2. Dựng môi trường pre-production dùng dịch vụ managed thật với region, network, tier và security gần production.
3. Phân biệt smoke, baseline, load, stress, spike, soak và breakpoint test.
4. Dùng k6, JMeter hoặc Gatling để điều khiển arrival rate, concurrency và thời gian chạy.
5. Đo đồng thời client-side metrics, Spring Boot metrics và metrics của từng managed service.
6. Nhận diện bottleneck ở application, connection pool, database, cache, queue, network hoặc load generator.
7. Thử thay đổi từng cấu hình, so sánh cùng workload và kiểm tra latency, reliability lẫn cost.
8. Quản lý quota, budget, test data, quyền truy cập và điều kiện dừng để tránh ảnh hưởng hệ thống.
9. Triển khai cấu hình đã được kiểm chứng qua canary/gradual rollout và có phương án rollback.

## 1. Vì sao cần đo tải bằng dịch vụ managed thật?

### 1.1. Mock và emulator không đại diện cho hiệu năng production

Unit test dùng mock để xác minh logic của service. Emulator hoặc container database cục bộ giúp kiểm tra API, schema và hành vi tích hợp. Các phương pháp đó rất hữu ích, nhưng không tái tạo đầy đủ:

- Độ trễ từ ứng dụng đến endpoint managed qua VPC/VNet, private service access hoặc public endpoint.
- TLS handshake, DNS, connection establishment và connection reuse.
- Authentication, IAM, token refresh và authorization của provider.
- CPU, memory, IOPS, connection limit và throughput của tier managed thực tế.
- Autoscaling, cold start, instance concurrency và thời gian scale-out.
- Rate limit, quota, throttling và retry behavior.
- Replication lag, failover, backup, maintenance và network behavior.
- Chi phí request, compute, storage, egress và observability.

Ví dụ, một repository mock có thể trả kết quả trong 1 ms. Database managed thật có thể mất thêm thời gian thiết lập connection, chờ pool, thực thi query, truyền dữ liệu và xử lý TLS. Nếu chỉ benchmark mock, nhóm phát triển sẽ không biết giới hạn thực tế của connection pool hoặc database tier.

### 1.2. Đo cả ứng dụng lẫn dịch vụ phía sau

~~~mermaid
flowchart TD
    GEN["Load generator<br/>k6 / JMeter / Gatling"] --> LB["Ingress / Load Balancer / API Gateway"]
    LB --> APP["Spring Boot instances"]
    APP --> DB["Managed database"]
    APP --> CACHE["Managed cache"]
    APP --> MSG["Managed messaging"]
    APP --> OBJ["Object storage"]
    APP --> THIRD["External service"]
    APP --> OBS["Micrometer / OpenTelemetry"]
    DB --> MON["Cloud monitoring"]
    CACHE --> MON
    MSG --> MON
    OBJ --> MON
    OBS --> MON
    GEN --> CLIENT["Client metrics<br/>latency / throughput / errors"]
~~~

Kết quả test phải cho biết request chậm ở đâu. Chỉ nhìn response time của client không đủ để kết luận cần tăng CPU cho Spring Boot, tăng database tier hay thay đổi connection pool.

### 1.3. Nguyên tắc quan trọng

- Dùng dịch vụ managed thật trong bài kiểm tra hiệu năng tích hợp cuối cùng.
- Dùng môi trường riêng có cấu hình gần production; không mặc định bắn tải lớn vào hệ thống production đang phục vụ khách hàng.
- Mô phỏng hành vi người dùng và dữ liệu thực tế, không chỉ lặp một endpoint với một payload giống nhau.
- Đo cả client, application, dependency và load generator.
- Chốt SLO/acceptance criteria trước khi chạy.
- Chỉ thay đổi một nhóm cấu hình mỗi lần để biết yếu tố nào tạo ra kết quả.
- Ghi lại version ứng dụng, cấu hình, region, loại tài nguyên và test data để có thể chạy lại.

## 2. Xây dựng workload model

### 2.1. Bắt đầu từ user journey

Một hệ thống đặt chỗ có thể có các luồng:

| Luồng | Các bước | Tải lên dependency |
| --- | --- | --- |
| Xem danh sách | API → database/cache → response | Nhiều read, cache hit/miss |
| Xem chi tiết | API → database → object storage | Read theo ID, tải metadata |
| Tìm kiếm | API → database/search service | Query/filter/sort |
| Tạo reservation | API → database transaction → outbox | Read + write + lock |
| Thanh toán | API → payment provider → database | Network latency, retry |
| Upload tài liệu | API → object storage → metadata database | Upload bytes, write metadata |
| Xem báo cáo | API → analytics database | Query nặng, đọc nhiều dữ liệu |

Không phải tất cả request đều có chi phí giống nhau. Một test chỉ gọi GET health endpoint không thể đại diện cho traffic tạo reservation, thanh toán hoặc tải file.

### 2.2. Tỷ lệ traffic và think time

Hãy ước lượng tỷ lệ request dựa trên access log, analytics hoặc giả định nghiệp vụ đã được xác nhận.

Ví dụ một workload tổng hợp:

| Luồng | Tỷ lệ request | Ghi chú |
| --- | ---: | --- |
| Browse/search | 45% | Read-heavy |
| Product/detail | 25% | Có thể cache |
| Reservation create/update | 15% | Transaction và contention |
| Payment status | 10% | Gọi database và provider |
| Report/export | 5% | Query nặng, payload lớn |

Các tỷ lệ trên chỉ là ví dụ để minh họa. Thay bằng phân bố của hệ thống cần đo.

Think time là khoảng thời gian người dùng chờ hoặc đọc trước hành động tiếp theo. Không tạo traffic bằng cách gọi API liên tục không nghỉ nếu người dùng thực tế có khoảng dừng. Với API machine-to-machine hoặc webhook, arrival rate có thể liên tục và không có think time.

### 2.3. Arrival rate và concurrency

Hai mô hình tải thường gặp:

- **Closed workload model:** số virtual users cố định; mỗi user gửi request, chờ response rồi mới bắt đầu iteration tiếp theo. Khi hệ thống chậm, tốc độ request tự giảm.
- **Open workload model:** tốc độ request đến được điều khiển độc lập với response time. Phù hợp để mô phỏng hệ thống nhận traffic theo arrival rate cố định.

Nếu dùng closed model để tìm giới hạn, khi latency tăng, test có thể vô tình gửi ít request hơn và che giấu quá tải. Với API nhận traffic liên tục, open model như arrival-rate executor trong k6 giúp kiểm soát requests/second rõ hơn.

Có thể dùng định luật Little để ước lượng số request đang xử lý:

\[
L = \lambda \times W
\]

Trong đó L là số request trung bình đang in-flight, lambda là arrival rate (request/second), W là thời gian xử lý trung bình (second). Ví dụ, 80 request/second với thời gian xử lý trung bình 0,25 giây cần khoảng 20 request in-flight ở trạng thái ổn định. Đây là ước lượng trung bình, không thay thế phép đo p95/p99 và burst.

### 2.4. Mô hình dữ liệu phải giống production

Dữ liệu test cần phản ánh:
- Số lượng row/document và kích thước bảng.
- Tỷ lệ key phổ biến và key hiếm.
- Mức độ trùng lặp và cardinality.
- Phân bố dữ liệu theo tenant, trạng thái và thời gian.
- Index, partition, clustering và schema.
- Kích thước object, message và response.
- Tỷ lệ cache hit dự kiến.

Một database rỗng thường cho kết quả quá lạc quan. Index nhỏ nằm hoàn toàn trong memory có thể không thể hiện được behavior của production. Dùng dữ liệu synthetic hoặc bản sao đã ẩn danh, với volume và distribution gần production.

### 2.5. Đặt SLO và acceptance criteria

Trước test, ghi rõ mục tiêu:

| Chỉ số | Ví dụ acceptance criteria | Cách xác định |
| --- | --- | --- |
| Error rate | Dưới 1% ở expected peak | SLO/API contract |
| p95 latency | Dưới 500 ms cho browse | Product SLO |
| p99 latency | Dưới 1,2 s cho browse | Tail latency objective |
| Throughput | Duy trì 100 request/s | Forecast traffic |
| Database connections | Dưới 80% giới hạn an toàn | Database capacity |
| Queue backlog | Không tăng liên tục sau peak | Processing SLA |
| CPU/memory | Có headroom để scale | Capacity policy |
| Cost per 1.000 request | Không vượt ngân sách | Unit economics |

Các con số trong bảng chỉ là ví dụ. Không sao chép ngưỡng này sang production nếu chưa dựa trên SLO, user experience, quota và chi phí của hệ thống thật.

## 3. Chuẩn bị môi trường pre-production

### 3.1. Dùng dịch vụ managed thật, tách biệt production

Môi trường staging/performance nên có:
- Project AWS, subscription Azure hoặc project Google Cloud riêng.
- VPC/VNet, subnet, firewall, private endpoint và DNS tương tự production.
- Database managed, cache, queue, object storage thật.
- Cùng loại engine/version, tier hoặc machine family gần production.
- Cùng vùng địa lý và đường network với application runtime production.
- Authentication và IAM tương đương, dùng service account/role riêng cho test.
- Index, schema, partition và connection pool cùng cấu trúc.
- Autoscaling, min/max instances và timeout gần cấu hình dự kiến.

Nếu staging nhỏ hơn production nhiều lần, kết quả vẫn hữu ích để tìm regression, nhưng không thể kết luận capacity production chỉ bằng cách nhân tuyến tính. Một số service có ngưỡng scale, quota hoặc topology khác nhau.

### 3.2. Dùng managed service thật cho từng dependency

| Dependency | Cần kiểm tra bằng tài nguyên thật | Điều cần quan sát |
| --- | --- | --- |
| Relational database | Cloud SQL, Amazon RDS/Aurora, Azure SQL | Query latency, CPU, IOPS, connections, lock |
| NoSQL database | Firestore, DynamoDB, Cosmos DB | Request latency, throughput, throttling, hot key/partition |
| Cache | Memorystore, ElastiCache, Azure Managed Redis | Hit ratio, latency, memory, connection, eviction |
| Messaging | Pub/Sub, SQS/SNS, Service Bus | Publish/consume rate, backlog, oldest message, retry |
| Object storage | Cloud Storage, S3, Blob Storage | Throughput, latency, request rate, egress |
| Compute | Cloud Run/GKE, ECS/EKS, App Service/AKS | Startup, CPU, memory, concurrency, instance count |

Emulator vẫn phù hợp cho functional integration test. Dùng managed service thật khi mục tiêu là đo network, tier capacity, authentication, quota, scaling và provider behavior.

### 3.3. Giữ topology gần production

Một số khác biệt có thể làm test mất giá trị:

- Load generator ở cùng máy hoặc cùng zone với database trong khi production ở region khác.
- Dùng public endpoint trong staging nhưng private endpoint trong production.
- Dùng database tier lớn hơn hoặc nhỏ hơn đáng kể.
- Tắt TLS hoặc dùng credential khác với runtime.
- Không bật autoscaling trong khi production bật.
- Bỏ qua gateway, WAF, load balancer hoặc service mesh.
- Dùng dataset nhỏ hơn nhiều so với production.
- Dùng cache đã warm sẵn nhưng production thường xuyên cold start.

Ghi lại topology và mọi khác biệt. Nếu không thể tái tạo đầy đủ, đánh dấu kết quả là có giới hạn thay vì suy diễn.

### 3.4. An toàn dữ liệu và quyền

- Chỉ dùng dữ liệu synthetic hoặc đã ẩn danh.
- Tạo tenant và user dành riêng cho test.
- Dùng service account/role có quyền tối thiểu.
- Không dùng token production hoặc secret cá nhân.
- Gắn test run ID vào request header, log và metric nếu có thể.
- Không chạy endpoint xóa dữ liệu hoặc thanh toán thật nếu chưa có sandbox/test mode.
- Chuẩn bị cleanup job cho dữ liệu test.
- Cấu hình rate limit, quota và budget alert trước khi tăng tải.

### 3.5. Kiểm tra giới hạn và ngân sách trước test

Load test có thể tạo chi phí lớn ở cả generator và dịch vụ đích. Trước khi chạy:
1. Kiểm tra service quota, request limit, database connection limit và autoscaling maximum.
2. Xác định quota nào có thể cần tăng trước khi test.
3. Ước lượng thời gian và mức tải.
4. Đặt budget alert và cảnh báo theo metric.
5. Định nghĩa stop condition khi cost, error rate hoặc resource utilization vượt ngưỡng.
6. Đảm bảo nhóm vận hành biết test window và có người theo dõi.

Google Cloud khuyến nghị xem xét quota và chi phí, đồng thời đặt billing budget alert khi chuẩn bị load test workload quan trọng. [Hướng dẫn conduct load testing của Google Cloud](https://docs.cloud.google.com/support/docs/peak-events/conduct-load-testing).

## 4. Các loại kiểm thử tải

| Loại test | Mục tiêu | Hình dạng tải | Câu hỏi cần trả lời |
| --- | --- | --- | --- |
| Smoke | Xác minh script và môi trường hoạt động | Rất ít VU/request | Endpoint, auth, dữ liệu có đúng? |
| Baseline | Đo hiệu năng ở tải thấp/điển hình | Tải ổn định | Latency và tài nguyên bình thường là bao nhiêu? |
| Load | Kiểm tra expected peak | Tăng đến tải dự kiến rồi giữ | Có đạt SLO ở tải dự kiến? |
| Stress | Tìm giới hạn | Tăng dần vượt peak | Bottleneck đầu tiên ở đâu? |
| Spike | Kiểm tra traffic surge | Tăng tải rất nhanh | Autoscaling, queue và cold start phản ứng thế nào? |
| Soak | Kiểm tra thời gian dài | Giữ tải ổn định nhiều giờ | Có memory leak, connection leak hoặc backlog tăng? |
| Breakpoint/capacity | Tìm mức tải tối đa đạt SLO | Tăng từng bậc đến khi threshold fail | Capacity an toàn và headroom là bao nhiêu? |
| Failover/resilience | Kiểm tra behavior khi dependency suy giảm | Tải có kiểm soát + lỗi được mô phỏng | Retry, timeout, failover có giữ được SLO? |

### 4.1. Smoke test

Chạy một vài request để xác minh load generator truy cập được endpoint, authentication hợp lệ, test data tồn tại, response đúng schema/status, script không tạo dữ liệu ngoài ý muốn và metrics/trace được ghi nhận. Nếu smoke test thất bại, không chuyển sang tải lớn.

### 4.2. Baseline test

Chạy ở mức tải thấp hoặc tải trung bình có thể lặp lại. Ghi lại throughput, p50/p95/p99, error rate, app CPU/memory, database/cache/queue metrics và chi phí hoặc usage units. Baseline là mốc để so sánh sau mỗi thay đổi. Nên chạy cùng script, cùng data seed và cùng thời lượng.

### 4.3. Load test

Tăng dần đến expected peak, giữ tải đủ lâu để autoscaling và connection pool ổn định. Không chỉ chạy ramp-up vài giây rồi kết luận. Theo dõi thời gian hệ thống scale-out, queue backlog và tail latency.

### 4.4. Stress và breakpoint test

Tăng từng bậc qua mức peak đã dự báo cho đến khi p95/p99 vượt SLO, error/throttle tăng, queue backlog tăng không giảm, CPU/memory/connection/IOPS bão hòa, autoscaling đạt max instance hoặc chi phí vượt mức chấp nhận. Dừng khi chạm điều kiện an toàn. Mục tiêu là tìm giới hạn và failure mode, không phải phá hỏng môi trường.

### 4.5. Spike test

Mô phỏng traffic tăng đột ngột như chiến dịch, email notification hoặc sự kiện. Theo dõi cold start, pending request, instance creation, connection storm, cache stampede, queue backlog và retry burst.

Cloud Run có hướng dẫn kiểm tra container concurrency, cold start và scale-out trước khi dùng kết quả để điều chỉnh production. [Cloud Run load testing best practices](https://docs.cloud.google.com/run/docs/about-load-testing).

### 4.6. Soak test

Giữ tải ở mức dự kiến trong thời gian dài để phát hiện memory leak, connection không được trả về pool, cache key tăng không giới hạn, queue consumer bị tụt lại, token refresh hoặc scheduled task gây spike, log/metric volume làm tăng chi phí và disk/storage tăng dần.

Đừng chỉ quan sát average CPU. Kiểm tra xu hướng memory, open connection, thread count, queue age và error rate theo thời gian.

## 5. Dùng k6 để tạo workload có kiểm soát

### 5.1. Vì sao cần kiểm soát tốc độ tải?

Load generator phải biết bao nhiêu request được khởi tạo mỗi giây, có bao nhiêu virtual users, thời gian ramp-up/hold/ramp-down, think time và phân bố endpoint, khi nào dừng nếu threshold bị vượt.

Google Cloud lưu ý không dùng nguồn traffic mà tốc độ và concurrency không kiểm soát được làm load generator. Một message broker như Pub/Sub không phải công cụ phù hợp để tạo traffic test nếu không biết chính xác arrival rate và số client. [Cloud Run load testing best practices](https://docs.cloud.google.com/run/docs/about-load-testing).

### 5.2. Ví dụ k6 với arrival rate

Script sau minh họa GET endpoint catalog. BASE_URL, API_TOKEN và TEST_RUN_ID được truyền qua environment variables; không commit secret vào script.

~~~javascript
import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  scenarios: {
    catalog_load: {
      executor: 'ramping-arrival-rate',
      startRate: 5,
      timeUnit: '1s',
      preAllocatedVUs: 20,
      maxVUs: 100,
      stages: [
        { target: 10, duration: '2m' },
        { target: 25, duration: '5m' },
        { target: 40, duration: '5m' },
        { target: 0, duration: '1m' },
      ],
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500', 'p(99)<1200'],
    checks: ['rate>0.99'],
  },
};

export default function () {
  const response = http.get(
    __ENV.BASE_URL + '/api/v1/catalog?limit=20',
    {
      headers: {
        Authorization: 'Bearer ' + __ENV.API_TOKEN,
        'X-Test-Run': __ENV.TEST_RUN_ID,
      },
      tags: { endpoint: 'catalog-list' },
    },
  );

  check(response, {
    'status is 200': (r) => r.status === 200,
    'response is JSON': (r) =>
      r.headers['Content-Type']?.includes('application/json'),
  });

  sleep(1);
}
~~~

Các ngưỡng 500 ms, 1.200 ms và 1% trong ví dụ chỉ để minh họa. Hãy thay bằng SLO của API thực tế.

Chạy script:

~~~bash
k6 run \
  -e BASE_URL=https://staging-api.example.internal \
  -e API_TOKEN="$PERF_TEST_TOKEN" \
  -e TEST_RUN_ID=perf-2026-11-24-01 \
  catalog-load.js
~~~

Trong CI, lấy token từ secret store hoặc CI secret variable. Không in token ra log.

### 5.3. Arrival rate, VU và dropped iterations

Với executor arrival-rate, k6 cố gắng bắt đầu iteration theo tốc độ đã cấu hình. Nếu không đủ VU để thực hiện iteration, metric dropped iterations có thể tăng.

Khi thấy dropped iterations:
- Kiểm tra maxVUs/preAllocatedVUs.
- Kiểm tra CPU/memory/network của load generator.
- Kiểm tra iteration duration có tăng do SUT chậm không.
- Không tăng VU vô hạn; nếu generator bị nghẽn, kết quả không phản ánh chính xác capacity của dịch vụ.

Scenarios trong k6 cho phép tổ chức nhiều profile tải độc lập. [k6 scenarios](https://grafana.com/docs/k6/latest/using-k6/scenarios/).

### 5.4. Checks và thresholds khác nhau

- Hàm check() xác minh response hoặc điều kiện nghiệp vụ của từng request.
- Thresholds đặt tiêu chí pass/fail cho toàn test run.

Một check thất bại không tự động khiến toàn bộ k6 process trả trạng thái thất bại nếu không có threshold tương ứng. Vì vậy hãy đặt threshold cho error rate, latency và check rate. [k6 thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/).

### 5.5. Tách scenario theo user journey

Một test thực tế nên có nhiều scenario: browse/search, read detail, create/update với test data duy nhất, upload/download object, publish/consume message và report query.

Gắn tag cho endpoint và scenario để phân tích latency riêng. Không để một endpoint rất nhanh che giấu endpoint thanh toán chậm trong average chung.

### 5.6. Test write và cleanup

Với API tạo dữ liệu:
- Sinh unique test ID cho mỗi iteration.
- Dùng idempotency key nếu API hỗ trợ.
- Chỉ ghi vào tenant/test dataset.
- Không tạo thanh toán thật hoặc gửi email/SMS tới khách hàng.
- Có cleanup hoặc TTL cho dữ liệu test.
- Theo dõi số record tăng trong database và storage.
- Tách test transaction rollback khỏi test commit thật vì hai hành vi tạo tải khác nhau.

## 6. Công cụ kiểm thử và lựa chọn

| Công cụ | Điểm mạnh | Khi phù hợp |
| --- | --- | --- |
| k6 | Script-as-code, arrival rate, thresholds, CI integration | API load test, regression automation |
| Apache JMeter | GUI, thread groups, protocol support rộng | Team đã có test plan JMeter, cần kịch bản phức tạp |
| Gatling | Code-based scenarios, reports, high-throughput testing | Test service/API với kịch bản có thể version hóa |
| Azure Load Testing | Managed test execution, tích hợp Azure Monitor | Workload chạy trên Azure hoặc cần managed test service |
| Browser-based load tool | Đo trải nghiệm người dùng thật | Một số ít browser VU kết hợp protocol load |

Không có công cụ nào tự tạo workload chính xác nếu kịch bản sai. Chọn công cụ dựa trên protocol, khả năng điều khiển tải, năng lực generator và kỹ năng vận hành của nhóm.

Có thể kết hợp protocol-level test cho phần lớn tải với browser-based test ở số VU nhỏ hơn để quan sát trải nghiệm trình duyệt. [k6 load testing guide](https://grafana.com/docs/k6/latest/testing-guides/load-testing-websites/).

## 7. Đo client-side và server-side metrics

### 7.1. Client-side metrics

Từ k6/JMeter/Gatling, thu thập request rate (RPS), throughput bytes/second, p50/p90/p95/p99 latency, error rate theo status và endpoint, timeout/connection error, check failure, dropped iterations, payload size và DNS/connect/TLS/TTFB nếu tool cung cấp.

Dùng percentile thay vì chỉ dùng average. Average có thể thấp trong khi một nhóm nhỏ request có p99 rất cao.

### 7.2. Spring Boot metrics

Spring Boot Actuator và Micrometer có thể cung cấp:
- HTTP server request count và latency.
- JVM heap/non-heap, GC pause.
- Thread count và executor queue.
- HikariCP active/idle/pending connections.
- HTTP client pool metrics.
- Cache hit/miss/eviction nếu provider instrumented.
- Custom business metrics như reservation success/failure.

OpenTelemetry có thể bổ sung distributed traces để thấy thời gian nằm ở controller, repository, remote client hoặc messaging consumer.

Không bật metric label có cardinality vô hạn như user ID, order ID hoặc raw URL. Dùng endpoint template, tenant tier hoặc bounded tag.

### 7.3. Metrics của managed service

| Loại dịch vụ | Metrics nên theo dõi |
| --- | --- |
| Relational database | CPU, memory, connections, query latency, IOPS, disk queue, locks, deadlocks, replica lag |
| NoSQL | Request latency, consumed capacity/RU, throttled requests, hot partition/key, retry |
| Cache | Hit/miss, evictions, memory, connection count, command latency, replication lag |
| Messaging | Publish/consume rate, queue depth, oldest message age, unacked messages, redelivery, DLQ |
| Object storage | Request count, latency, throughput, error/throttle, egress |
| Compute | Instance count, startup latency, CPU, memory, concurrency, pending request, scale events |

Không nhìn riêng CPU. Database CPU thấp nhưng connection pool pending cao có thể là vấn đề pool hoặc lock. Queue backlog tăng trong khi CPU consumer thấp có thể là consumer concurrency hoặc I/O dependency.

### 7.4. AWS: CloudWatch

Với Amazon RDS, CloudWatch có các metric như CPUUtilization, DatabaseConnections, FreeableMemory, FreeStorageSpace, ReadLatency, WriteLatency, ReadIOPS, WriteIOPS, DiskQueueDepth và ReplicaLag (tùy engine/topology).

Với ElastiCache, theo dõi engine CPU, memory, evictions, connections, cache hits/misses và replication lag tùy engine. Với SQS, quan sát queue depth và age of oldest message; với Lambda/ECS/EKS, xem concurrency, throttles, task/instance count và resource utilization.

CloudWatch thu thập metric RDS theo chu kỳ mặc định một phút; dùng Enhanced Monitoring/Performance Insights hoặc tracing/log phù hợp khi cần phân tích sâu hơn. [Amazon RDS CloudWatch metrics](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-metrics.html) và [CloudWatch monitoring overview](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/monitoring-cloudwatch.html).

### 7.5. Azure: Azure Monitor và Azure Load Testing

Azure Load Testing có thể tích hợp Azure Monitor để thu thập server-side resource metrics của các app component được khai báo trong test. Dashboard cho phép so sánh:
- Client response time, throughput và error rate.
- Server-side metrics của App Service, Azure SQL, Cosmos DB và các resource được hỗ trợ.
- Engine health của load generator như CPU, memory, network và virtual users.

Nếu load generator đạt CPU/memory/network saturation, kết quả có thể phản ánh giới hạn của generator thay vì application. [Azure Load Testing server-side metrics](https://learn.microsoft.com/en-us/azure/app-testing/load-testing/how-to-monitor-server-side-metrics) và [test run results dashboard](https://learn.microsoft.com/en-us/azure/app-testing/load-testing/how-to-understand-test-run-results-dashboard).

Với Azure SQL, Cosmos DB và Azure Managed Redis, theo dõi metric riêng của service như CPU/worker, data IO, RU consumption/throttling, cache memory/latency và connection.

### 7.6. Google Cloud: Cloud Monitoring

Với Cloud Run, theo dõi request count và request latency, container CPU/memory utilization, instance count và maximum concurrent requests, container startup latency, billable instance time, pending latency và user execution latency khi có metric breakdown phù hợp.

Với Cloud SQL, theo dõi CPU, memory, active connections, storage, read/write operations, query insights và replication lag nếu có replica. Với Pub/Sub, Cloud Storage và Memorystore, xem backlog/oldest unacked message, request latency, throughput, cache memory/hit và connection theo service.

Cloud Run có metrics tích hợp trong Cloud Monitoring; Cloud SQL cung cấp metric về CPU, connection, storage và I/O. [Cloud Run monitoring](https://docs.cloud.google.com/run/docs/monitoring), [Cloud SQL monitoring](https://docs.cloud.google.com/sql/docs/mysql/monitor-instance).

### 7.7. Correlate bằng timestamp và test run ID

Mọi hệ thống cần dùng cùng một cửa sổ thời gian và có test run ID:
- Load generator ghi run ID và scenario.
- Spring Boot log/trace ghi run ID hoặc trace context.
- Database query comment/label nếu an toàn và được hỗ trợ.
- Message attribute chứa run ID.
- Dashboard monitoring đánh dấu thời điểm ramp-up, hold, ramp-down.
- Ghi lại deployment revision và config revision.

Nếu không có correlation, một spike metric có thể đến từ workload khác hoặc scheduled job ngoài test.

## 8. Phân tích bottleneck

### 8.1. Đọc tín hiệu trước khi thay cấu hình

| Dấu hiệu | Khả năng nguyên nhân | Bước xác minh |
| --- | --- | --- |
| p95 tăng, app CPU cao | CPU-bound, serialization hoặc business logic | Profile JVM, thread dump, CPU flame graph |
| p95 tăng, app CPU thấp, pool pending cao | Connection pool cạn hoặc dependency chậm | Xem active/idle/pending, query latency |
| Database CPU/IO cao | Query/index/schema hoặc tier thiếu capacity | Query Insights, slow query, execution plan |
| Database connection chạm giới hạn | Pool mỗi instance quá lớn hoặc instance scale-out quá nhanh | Tính tổng connection, xem max connection |
| Cache hit thấp | Key không ổn định, TTL quá ngắn hoặc data pattern | Phân tích hit/miss theo cache name |
| Cache memory/eviction cao | Working set lớn hoặc entry không có giới hạn | Kiểm tra key cardinality, value size, TTL |
| Queue backlog tăng | Consumer chậm, batch nhỏ, downstream bị chặn | Đo processing rate, oldest message age, retry |
| Throttling tăng | Quota/RU/capacity limit | Kiểm tra service quota và request pattern |
| Pending latency tăng khi spike | Cold start hoặc thiếu instance | Xem startup latency, min/max instance |
| Dropped iterations tăng | Load generator thiếu VU hoặc bị bão hòa | Xem generator CPU/memory/network |
| Latency tăng theo region | Network path hoặc cross-region call | So sánh DNS/connect/TLS và region |
| Error tăng sau retry | Retry storm hoặc operation không idempotent | Kiểm tra retry policy, idempotency key |

### 8.2. Connection pool và số instance

Với Spring Boot dùng HikariCP, tổng connection có thể tăng theo số application instance:

\[
C_{total} = N_{instances} \times P_{max} + C_{background}
\]

Trong đó N_instances là số instance tối đa có thể chạy cùng lúc, P_max là maximumPoolSize mỗi instance, C_background là connection từ worker, migration, admin, monitoring hoặc service khác.

Ví dụ 12 instance, mỗi instance pool tối đa 20 connection, cộng 40 connection background tạo khả năng 280 connection. Nếu database chỉ cho phép ít hơn mức đó, scale-out có thể khiến connection bị từ chối.

Đừng tăng maximumPoolSize chỉ vì thấy request chờ. Nếu database đã bão hòa, pool lớn hơn có thể làm tình hình tệ hơn. Đo query latency, active connections, pool pending và database capacity cùng lúc.

### 8.3. Autoscaling và concurrency

Với compute managed:
- Concurrency quá cao có thể khiến mỗi instance giữ nhiều request và connection cùng lúc.
- Concurrency quá thấp có thể tạo quá nhiều instance và connection.
- Min instances thấp có thể tăng cold start.
- Max instances thấp có thể tạo pending request hoặc throttle.
- Startup time và readiness probe ảnh hưởng thời điểm instance nhận traffic.

Thử từng tham số với cùng workload. Kiểm tra chi phí instance time và database connections sau mỗi lần scale.

### 8.4. Queue và consumer throughput

Nếu API chỉ publish message rồi trả response, latency API có thể thấp dù consumer không theo kịp. Cần đo end-to-end latency từ publish đến xử lý xong.

Consumer có thể bị giới hạn bởi số worker/partition, batch size, ack deadline hoặc visibility timeout, database write rate, external API rate limit, retry/DLQ, ordering key hoặc hot partition.

Không tăng consumer concurrency mà chưa xác nhận downstream database/cache chịu được tốc độ write tăng.

## 9. Điều chỉnh cấu hình production dựa trên bằng chứng

### 9.1. Một vòng tối ưu có thể lặp lại

~~~mermaid
flowchart TD
    SLO["Define SLO and workload"] --> BASE["Run baseline on real managed services"]
    BASE --> OBS["Correlate client, app and provider metrics"]
    OBS --> BOT["Identify the first bottleneck"]
    BOT --> HYP["Form one configuration hypothesis"]
    HYP --> CHANGE["Change one variable in staging"]
    CHANGE --> TEST["Repeat the same test"]
    TEST --> COMPARE["Compare latency, errors, capacity and cost"]
    COMPARE --> PASS{"SLO and cost improved?"}
    PASS -->|Yes| CANARY["Canary / gradual production rollout"]
    PASS -->|No| ROLLBACK["Revert and test another hypothesis"]
    CANARY --> MON["Monitor and keep rollback ready"]
~~~

### 9.2. Thay đổi một biến mỗi lần

Ví dụ muốn tăng throughput:
1. Baseline với instance size và concurrency hiện tại.
2. Tăng CPU hoặc memory, giữ concurrency không đổi.
3. Chạy lại cùng test.
4. Khôi phục baseline.
5. Thay concurrency, giữ CPU/memory không đổi.
6. Chạy lại và so sánh.
7. Kiểm tra cả database connections, cost và tail latency.

Nếu thay đồng thời CPU, pool, cache TTL và database tier, bạn sẽ không biết thay đổi nào tạo ra cải thiện hoặc regression.

### 9.3. Những nhóm cấu hình thường được điều chỉnh

| Thành phần | Tham số có thể thử | Rủi ro cần kiểm tra |
| --- | --- | --- |
| Spring Boot runtime | CPU/memory, thread pool, max concurrency | GC, queueing, instance cost |
| Autoscaling | Min/max instances, target utilization, scale delay | Cold start, scale burst, quota |
| HikariCP | maximumPoolSize, connectionTimeout, idleTimeout | Database connection limit |
| Database | Machine tier, storage/IOPS, index, query plan | Chi phí, lock, replication |
| Cache | TTL, max memory, eviction, pool size | Stale data, cache stampede |
| Messaging | Consumer count, batch size, prefetch, ack | Backlog, duplicate, downstream overload |
| HTTP client | Connection pool, timeout, keep-alive | Pending acquire, socket exhaustion |
| Retry | Max attempts, backoff, jitter | Retry storm, duplicate write |
| Object storage | Multipart threshold, concurrency, buffer size | Memory, request cost, egress |

Không thay cấu hình bảo mật hoặc tắt TLS để cải thiện benchmark. Hiệu năng cần được đo trên security posture dự kiến cho production.

### 9.4. Tối ưu theo bottleneck

- **CPU-bound:** profile code, giảm serialization, tối ưu thuật toán, sau đó mới tăng CPU hoặc instance.
- **Database-bound:** tối ưu query/index, giảm N+1, batch, giảm lock; chỉ tăng tier sau khi xác minh.
- **Pool-bound:** tính tổng connection, xem leak/pending, điều chỉnh pool theo capacity database.
- **Network-bound:** kiểm tra region, private endpoint, TLS reuse, payload và cross-region traffic.
- **Cache-bound:** xem hit ratio, key design, TTL, stampede và eviction.
- **Queue-bound:** đo processing rate, tăng consumer có giới hạn, tối ưu batch và downstream.
- **Cold-start-bound:** giảm startup work, pre-warm hoặc điều chỉnh min instances nếu cost chấp nhận.
- **Quota-bound:** xem quota thực tế, giảm request, batch hoặc yêu cầu quota increase trước production event.

### 9.5. So sánh cost cùng hiệu năng

Một thay đổi chỉ được coi là tốt nếu không đánh đổi reliability hoặc chi phí vượt mức chấp nhận.

Theo dõi cost per 1.000 successful requests, cost per processed message, cost per GB hoặc object operation, database tier cost và storage/IOPS, cache memory-hours, egress và cross-region traffic, observability ingestion/retention và load generator cost.

Ví dụ, tăng cache size có thể giảm database reads nhưng tăng chi phí memory. Tăng min instances có thể giảm cold start nhưng tăng billable instance time. So sánh unit cost, không chỉ tổng hóa đơn trong một lần test ngắn.

## 10. Quota, chi phí và điều kiện dừng

### 10.1. Quota khác capacity

Quota là giới hạn được provider áp dụng cho project/account/region/service. Capacity là khả năng xử lý của tài nguyên được provision. Một workload có thể chạm quota trước khi CPU hoặc memory đạt mức cao.

Theo dõi:
- API request quota.
- Concurrent request/instance quota.
- Database connection limit.
- NoSQL read/write capacity hoặc RU/s.
- Message publish/receive quota.
- Storage request rate.
- Load testing engine capacity.
- Regional resource quota.

Khi thấy throttling, không chỉ tăng retry. Xác định quota, partition hot spot, burst limit hoặc service tier.

### 10.2. Budget và stop condition

Đặt trước điều kiện dừng, ví dụ:
- Error rate vượt ngưỡng trong một khoảng liên tục.
- p99 vượt ngưỡng an toàn.
- Database connection đạt mức bảo vệ.
- Queue backlog vượt giới hạn.
- Service throttling tăng nhanh.
- Generator CPU/network bão hòa.
- Cost dự kiến vượt ngân sách test.
- Có ảnh hưởng đến tenant hoặc workload ngoài test.

Người điều hành cần có quyền dừng generator và rollback cấu hình ngay. Không chờ test kết thúc theo lịch nếu hệ thống đã chạm stop condition.

### 10.3. Không dùng production làm môi trường stress tùy tiện

Production load test chỉ phù hợp khi có kế hoạch và kiểm soát riêng:
- Có lịch test và người chịu trách nhiệm.
- Bounded traffic, canary hoặc traffic replay có rate limit.
- Không gửi dữ liệu hoặc giao dịch gây tác động khách hàng.
- Có kill switch và rollback.
- Đã thông báo cho bên vận hành/dependency owner.
- Theo dõi SLO và error budget.
- Không thử phá giới hạn hoặc failover ngoài cửa sổ được phê duyệt.

Thông thường, stress/spike/soak test nên chạy ở staging production-like. Production có thể dùng canary, synthetic monitoring hoặc controlled experiment ở mức an toàn để xác nhận behavior thực tế.

## 11. Quy trình thực hiện một đợt performance test

### Bước 1 — Chốt câu hỏi

Ví dụ: “API browse có duy trì 100 RPS với p95 dưới 500 ms và error rate dưới 1% khi chạy trên Cloud Run và Cloud SQL staging không?”

Một câu hỏi rõ giúp chọn workload, metrics và thời lượng.

### Bước 2 — Chuẩn bị môi trường

- Deploy đúng artifact/version cần đo.
- Cấu hình managed dependencies thật.
- Nạp test data gần production.
- Kiểm tra region/network/IAM.
- Đặt quota, budget alert và stop condition.
- Bật metrics, logs và tracing.

### Bước 3 — Smoke test

Chạy một vài request. Xác minh response, test data, cleanup và monitoring.

### Bước 4 — Baseline

Chạy workload nhỏ và lưu kết quả. Ghi lại p50/p95/p99, RPS, error rate, resource usage và cost.

### Bước 5 — Load/stress/spike/soak

Chọn profile phù hợp với câu hỏi. Tăng tải theo từng bậc và giữ đủ lâu để resource scaling ổn định.

### Bước 6 — Tìm bottleneck

Ghép client metrics với application trace và provider metrics. Xác định thành phần đầu tiên bão hòa hoặc tạo latency.

### Bước 7 — Đặt giả thuyết và thay cấu hình

Chỉ thay một tham số hoặc một nhóm có quan hệ chặt chẽ. Ghi lại config revision.

### Bước 8 — Chạy lại cùng điều kiện

Giữ workload, test data, region, generator và thời lượng giống baseline. Nếu điều kiện khác, ghi rõ khác biệt.

### Bước 9 — So sánh và quyết định

So sánh SLO, capacity, error, cost và headroom. Chấp nhận thay đổi khi kết quả lặp lại và không làm giảm reliability.

### Bước 10 — Canary và theo dõi production

Triển khai dần, quan sát metrics thật, giữ rollback. Không xem một lần benchmark staging là bảo đảm tuyệt đối cho mọi traffic pattern production.

## 12. Báo cáo kết quả test

Một báo cáo đủ để nhóm khác tái lập cần có:

| Trường | Nội dung |
| --- | --- |
| Test run ID | ID duy nhất |
| Application version | Git SHA/image digest |
| Configuration revision | Hash hoặc version của config |
| Infrastructure | Region, service tier, instance size, network |
| Dependency versions | Engine/version, cache tier, queue config |
| Data profile | Row count, object size, distribution, seed |
| Load generator | Tool/version, location, instance count |
| Workload | Scenario, RPS/VU, think time, duration |
| Test type | Smoke/load/stress/spike/soak |
| Client results | Throughput, p50/p95/p99, errors |
| App results | CPU, memory, GC, thread, pool |
| Dependency results | CPU, connections, latency, throttles, backlog |
| Cost | Usage/cost estimate, egress, generator |
| Findings | Bottleneck, evidence, root cause |
| Change tested | Một cấu hình đã thay |
| Decision | Accept/reject/retest |
| Limitations | Khác biệt với production, quota hoặc missing metric |

### 12.1. So sánh trước và sau

Ví dụ bảng kết quả (số liệu minh họa):

| Metric | Baseline | Candidate | Nhận xét |
| --- | ---: | ---: | --- |
| Throughput | 80 RPS | 100 RPS | Tăng 25% |
| p95 | 620 ms | 430 ms | Cải thiện |
| p99 | 1.800 ms | 1.050 ms | Tail latency giảm |
| Error rate | 0,8% | 0,4% | Cải thiện |
| DB CPU | 88% | 82% | Vẫn cần headroom |
| DB connections | 170 | 185 | Kiểm tra giới hạn |
| Cost/1.000 request | 1,00 đơn vị | 1,12 đơn vị | Tăng 12% |

Không kết luận Candidate tốt hơn chỉ vì p95 giảm. Cần xác định p99, error, resource headroom và cost có nằm trong mục tiêu hay không.

## 13. Lỗi thường gặp khi đo tải

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Test đạt nhưng production chậm | Staging khác tier, data volume hoặc network | Ghi rõ khác biệt, tái tạo topology |
| Kết quả mỗi lần khác nhau | Workload/data seed không cố định hoặc background job | Cố định test data, time window và dependency |
| RPS không tăng dù tăng VU | Arrival-rate chưa cấu hình hoặc generator bão hòa | Kiểm tra executor, max VU và generator health |
| Dropped iterations cao | Không đủ VU hoặc SUT quá chậm | Kiểm tra generator và iteration duration |
| Average tốt nhưng p99 rất cao | Tail latency do lock, queue, GC hoặc network | Phân tích percentile, trace và outlier |
| App CPU thấp nhưng request chờ | Pool, connection hoặc dependency bottleneck | Xem pending pool, connection và remote span |
| Database CPU cao | Query scan/lock/index hoặc tier thiếu | Query Insights, execution plan |
| Connection refused | Pool tổng vượt max connection hoặc failover | Tính connection budget và kiểm tra DB limit |
| Cache test quá tốt | Cache đã warm hoặc key lặp quá mức | Test cold/warm riêng, dùng realistic key distribution |
| Queue backlog tăng sau test | Consumer throughput thấp hơn publish rate | Đo oldest message age và processing rate |
| Throttling tăng | Quota/capacity/partition limit | Kiểm tra quota, capacity và request distribution |
| Cloud bill tăng bất ngờ | Autoscaling, egress hoặc test duration | Budget alert, cap resource và stop condition |
| Kết quả không lặp lại | Nhiều tham số đổi cùng lúc | Chỉ thay một biến, lặp test |
| Metric không giải thích được latency | Sampling granularity quá thưa | Dùng logs/traces chi tiết hơn và correlation ID |
| Test generator là bottleneck | CPU, memory, network hoặc file descriptor cạn | Scale generator hoặc giảm protocol overhead |

## 14. Bài tập thực hành

### Bài A — Xây workload model

Từ một API Spring Boot, chọn ba user journey. Xác định tỷ lệ request, think time, payload size, RPS peak và SLO p95/p99.

### Bài B — Dựng staging với managed services

Tạo project/subscription riêng, deploy Spring Boot cùng database, cache và messaging managed. So sánh region, network, tier và IAM với production; ghi lại các khác biệt.

### Bài C — Smoke và baseline bằng k6

Viết script k6 có checks và thresholds. Chạy smoke test, sau đó baseline ở tải thấp. Lưu kết quả JSON và test run ID.

### Bài D — Load và stress test

Dùng ramping-arrival-rate tăng dần traffic. Xác định mức RPS cao nhất mà p95, p99 và error rate vẫn đạt SLO.

### Bài E — Spike test autoscaling

Tạo traffic tăng nhanh. Đo startup latency, pending request, instance count, database connections và queue backlog. Kiểm tra cold start và scale-out.

### Bài F — Soak test

Giữ tải ở mức 60–70% expected peak trong thời gian đủ dài theo mục tiêu kiểm thử. Theo dõi heap, GC, connection, cache memory và queue age.

### Bài G — Kiểm tra database pool

Thử hai cấu hình HikariCP khác nhau, giữ nguyên các tham số khác. Tính tổng connection tối đa theo số instance và so sánh với giới hạn database.

### Bài H — Theo dõi metrics theo cloud

Chạy cùng workload với AWS CloudWatch/RDS metrics, Azure Load Testing/Azure Monitor và Google Cloud Monitoring/Cloud Run/Cloud SQL metrics. Xác định metrics nào giải thích được bottleneck.

### Bài I — Tối ưu từng biến

Chọn một bottleneck đã chứng minh. Thay một cấu hình, chạy lại cùng test và so sánh p95/p99, throughput, error, resource headroom và cost.

### Bài J — Viết báo cáo và rollout

Tạo báo cáo theo mẫu. Đề xuất cấu hình production, canary rollout, alert và rollback condition. Giải thích các khác biệt staging/production còn tồn tại.

### Câu hỏi tự kiểm tra

1. Vì sao mock và emulator không thay thế được performance test với managed service thật?
2. Những khác biệt nào giữa staging và production có thể làm sai kết quả?
3. Workload model cần các thông tin nào?
4. Closed workload khác open workload ra sao?
5. Định luật Little giúp ước lượng điều gì?
6. Vì sao phải xác định SLO trước khi test?
7. Smoke test khác baseline test như thế nào?
8. Stress, spike và soak test trả lời những câu hỏi nào?
9. Vì sao không nên dùng một endpoint duy nhất để đại diện toàn bộ traffic?
10. Arrival-rate executor trong k6 kiểm soát yếu tố nào?
11. Dropped iterations cho biết điều gì?
12. Hàm check() khác thresholds như thế nào?
13. Vì sao cần theo dõi load generator health?
14. Những metrics nào cần lấy từ Spring Boot?
15. CloudWatch có thể giúp phát hiện bottleneck RDS nào?
16. Azure Load Testing tích hợp server-side metrics qua dịch vụ nào?
17. Cloud Run pending latency khác user execution latency như thế nào?
18. Vì sao CPU thấp vẫn có thể đi cùng latency cao?
19. Làm thế nào tính tổng connection khi ứng dụng autoscale?
20. Vì sao tăng connection pool không phải lúc nào cũng tăng throughput?
21. Queue backlog và oldest message age cho biết điều gì?
22. Vì sao phải kiểm tra quota trước stress test?
23. Làm thế nào đặt stop condition và budget alert?
24. Vì sao nên thay một cấu hình mỗi lần?
25. Một báo cáo performance test cần ghi lại những thông tin nào?
26. Khi nào có thể kiểm thử trên production và cần những guardrails nào?
27. Vì sao cần so sánh cost per successful request?
28. Vì sao staging pass không bảo đảm production luôn đạt SLO?

**Kết quả mong đợi:** người học xây dựng được workload model, chạy được smoke/load/stress/spike/soak test với dịch vụ managed thật trong môi trường an toàn, thu thập được client/application/provider metrics, xác định bottleneck có bằng chứng, thử thay đổi cấu hình có kiểm soát và đề xuất production rollout dựa trên SLO, quota, reliability và cost.

## Tài liệu tham khảo

- [Google Cloud — Conduct load testing](https://docs.cloud.google.com/support/docs/peak-events/conduct-load-testing)
- [Cloud Run — Load testing best practices](https://docs.cloud.google.com/run/docs/about-load-testing)
- [Cloud Run — Monitor health and performance](https://docs.cloud.google.com/run/docs/monitoring)
- [Cloud SQL — Monitor instances](https://docs.cloud.google.com/sql/docs/mysql/monitor-instance)
- [AWS — Monitoring Amazon RDS metrics with CloudWatch](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/monitoring-cloudwatch.html)
- [AWS — Amazon RDS metrics reference](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-metrics.html)
- [Azure Load Testing — Monitor server-side metrics](https://learn.microsoft.com/en-us/azure/app-testing/load-testing/how-to-monitor-server-side-metrics)
- [Azure Load Testing — Understand test run results](https://learn.microsoft.com/en-us/azure/app-testing/load-testing/how-to-understand-test-run-results-dashboard)
- [Grafana k6 — Scenarios](https://grafana.com/docs/k6/latest/using-k6/scenarios/)
- [Grafana k6 — Thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/)
- [Grafana k6 — Test for performance](https://grafana.com/docs/k6/latest/examples/get-started-with-k6/test-for-performance/)
- [Grafana k6 — Automated performance testing](https://grafana.com/docs/k6/latest/testing-guides/automated-performance-testing/)

