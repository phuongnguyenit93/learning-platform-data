# Kiểm thử tải, tinh chỉnh cấu hình và bàn giao dịch vụ API

Một Java serverless API chỉ sẵn sàng production khi nhóm chứng minh được API xử lý đúng nghiệp vụ ở mức tải dự kiến, giữ latency trong SLO, không làm quá tải database hoặc dịch vụ phụ thuộc, có chi phí phù hợp và có quy trình vận hành rõ ràng. Việc gọi thử một vài request thành công hoặc benchmark riêng Java handler chưa đủ để kết luận dịch vụ có thể phục vụ traffic thật.

Bài học này sử dụng mô hình tham chiếu **Amazon API Gateway + AWS Lambda Java + database**. Các nguyên tắc kiểm thử và bàn giao cũng áp dụng cho HTTP function trên Azure Functions, Google Cloud Run hoặc nền tảng serverless khác. Nội dung đi theo ba việc: thiết kế và chạy load test, tinh chỉnh cấu hình dựa trên số liệu, rồi bàn giao dịch vụ API cho đội vận hành.

Kết quả mong đợi là một **capacity envelope** có bằng chứng: API chịu được bao nhiêu request mỗi giây trong điều kiện đã thử, p95/p99 là bao nhiêu, giới hạn concurrency và dependency nằm ở đâu, chi phí trên mỗi giao dịch thành công ra sao, và điều gì phải làm khi hệ thống vượt ngưỡng.

## 1. Mục tiêu của load testing

Load testing kiểm tra hành vi của hệ thống khi nhiều request đến đồng thời hoặc liên tục. Với serverless, bài test cần bao phủ toàn bộ đường đi của request:

~~~mermaid
flowchart LR
    C["Load generator"] --> E["Internet / DNS / TLS"]
    E --> G["API Gateway"]
    G --> L["Java Lambda"]
    L --> D["Database / cache"]
    L --> X["External APIs"]
    L --> R["Response"]
    R --> C
    G --> M["API metrics"]
    L --> O["Logs / traces / metrics"]
    D --> P["Database metrics"]
~~~

Các mục tiêu chính:

- Đo throughput mà API duy trì được trong điều kiện tải xác định.
- Đo latency p50, p95, p99 và tỷ lệ lỗi.
- Xác định giới hạn ở API Gateway, Lambda concurrency, Java runtime, database, cache hoặc external API.
- Kiểm tra hành vi khi traffic tăng nhanh, giảm nhanh hoặc kéo dài nhiều giờ.
- Phát hiện memory pressure, thread contention, connection exhaustion và cold start.
- Xác minh timeout, retry, rate limit, idempotency và graceful degradation.
- Ước lượng chi phí ở mức tải bình thường, peak và burst.
- Tạo bằng chứng để quyết định cấu hình production và bàn giao vận hành.

Một test chỉ gọi trực tiếp Lambda bằng Invoke API không đo được latency và throttling của API Gateway. Ngược lại, chỉ gọi endpoint từ bên ngoài mà không quan sát Lambda và database thì khó xác định bottleneck. Cần kiểm tra cả end-to-end lẫn từng tầng.

## 2. Xác định SLO và tiêu chí thành công trước khi test

Không có một con số RPS hoặc latency phù hợp cho mọi API. Owner nghiệp vụ và kỹ thuật phải thống nhất SLO dựa trên trải nghiệm người dùng, thời gian xử lý nghiệp vụ và khả năng dependency.

Một SLO có thể bao gồm:

| Chỉ số | Ý nghĩa | Ví dụ minh họa |
|---|---|---|
| Availability | Tỷ lệ request hợp lệ được xử lý thành công | 99,9% trong tháng |
| p95 latency | 95% request hoàn tất nhanh hơn ngưỡng | Dưới 400 ms |
| p99 latency | 99% request hoàn tất nhanh hơn ngưỡng | Dưới 900 ms |
| Sustained throughput | Mức tải duy trì liên tục | 300 RPS trong 30 phút |
| Burst throughput | Mức tăng tải ngắn hạn | 600 RPS trong 1 phút |
| Error rate | Tỷ lệ lỗi ngoài lỗi nghiệp vụ dự kiến | Dưới 0,5% |
| Recovery time | Thời gian trở lại bình thường sau burst hoặc dependency failure | Dưới 2 phút |

Các giá trị trên chỉ là ví dụ. Phải định nghĩa rõ mẫu số, loại request, cửa sổ thời gian, lỗi được tính và điều kiện loại trừ. Ví dụ, HTTP 400 do input không hợp lệ có thể là hành vi đúng của API, còn HTTP 500 hoặc timeout là lỗi dịch vụ.

Phân biệt:

- **SLO:** mục tiêu chất lượng dịch vụ.
- **SLI:** chỉ số thực tế dùng để đo SLO.
- **SLA:** cam kết chính thức với khách hàng, có thể kèm điều khoản hỗ trợ hoặc bồi thường.
- **Error budget:** phần lỗi có thể chấp nhận trong một khoảng thời gian theo SLO.

Không chọn ngưỡng chỉ vì một công cụ benchmark mặc định dùng 500 ms. Hãy xuất phát từ thời gian người dùng chờ được, deadline của caller và latency của các bước nghiệp vụ phía sau.

## 3. Mô hình hóa workload thật

Trước khi viết script, mô tả traffic thực tế:

- Các route và tỷ trọng request của từng route.
- Tỷ lệ GET, POST, PUT/PATCH và DELETE.
- Kích thước request/response.
- Số lượng record trả về và pagination.
- Tỷ lệ request có authentication hoặc authorization.
- Tỷ lệ cache hit/miss nếu có cache.
- Thời gian xử lý database và external API.
- Traffic trung bình, peak, burst và chu kỳ theo giờ/ngày.
- Tenant hoặc client có mức sử dụng khác nhau.
- Request thành công, validation error và retry.

Ví dụ workload cho một API quản lý đơn hàng:

| Route | Tỷ trọng | Đặc điểm | Dependency chính |
|---|---:|---|---|
| GET /products | 45% | Read nhiều, payload nhỏ | Cache, database |
| GET /orders/{id} | 25% | Read theo khóa | Database |
| POST /orders | 20% | Ghi và kiểm tra tồn kho | Database, inventory API |
| PATCH /orders/{id} | 7% | Cập nhật trạng thái | Database |
| POST /orders/{id}/confirm | 3% | Side effect nghiệp vụ | Database, payment API |

Đừng test chỉ một route dễ chạy rồi suy rộng cho toàn API. Route tạo đơn có nhiều dependency và side effect hơn route đọc danh mục. Hãy test từng route quan trọng và một workload hỗn hợp theo tỷ trọng gần production.

## 4. Các kiểu kiểm thử tải

| Loại test | Mục đích | Cách chạy |
|---|---|---|
| Smoke test | Xác nhận môi trường và script hoạt động | Vài request hoặc tải rất thấp |
| Baseline test | Đo hiệu năng ở mức tải nhỏ | Tải ổn định trong thời gian ngắn |
| Load test | Kiểm tra tải dự kiến | Duy trì mức RPS mục tiêu |
| Stress test | Tìm giới hạn và cách hệ thống suy giảm | Tăng tải vượt mức dự kiến |
| Spike test | Kiểm tra burst đột ngột | Tăng nhanh từ thấp lên cao |
| Soak test | Phát hiện vấn đề tích lũy | Duy trì tải nhiều giờ |
| Capacity test | Xác định capacity an toàn | Tăng tải theo từng nấc |
| Recovery test | Xác minh hệ thống phục hồi | Giảm tải sau khi vượt ngưỡng hoặc dependency lỗi |

Smoke và baseline nên chạy trước mọi bài test lớn. Stress và spike cần giới hạn phạm vi, quota và chi phí. Soak test giúp phát hiện connection leak, memory growth, cache growth, log volume và lỗi xuất hiện sau thời gian dài.

## 5. Chuẩn bị môi trường kiểm thử an toàn

Load test tạo ra request thật và có thể tạo dữ liệu thật. Ưu tiên một AWS account hoặc environment riêng có cấu hình gần production.

Trước khi chạy:

1. Dùng API stage và Lambda alias dành cho load test.
2. Dùng database, cache và queue test riêng.
3. Dùng tenant và account giả lập.
4. Dùng payment/email/SMS sandbox hoặc stub.
5. Tắt hoặc cô lập các side effect không cần thiết.
6. Đặt budget alarm và giới hạn chi phí thử nghiệm.
7. Kiểm tra Service Quotas của API Gateway, Lambda, database và dịch vụ phụ thuộc.
8. Xác nhận load generator đủ CPU, network và số worker.
9. Đặt ngưỡng dừng tự động và người chịu trách nhiệm.
10. Chuẩn bị dọn dữ liệu test sau khi hoàn tất.

AWS khuyến nghị tách load test khỏi production để tránh tiêu thụ quota của workload thật và tránh truy cập dữ liệu khách hàng. Nếu tổ chức buộc phải kiểm thử production, cần có phê duyệt riêng, cửa sổ thử nghiệm, rate cap, test tenant, monitoring và phương án dừng tức thì.

Không dùng dữ liệu PII hoặc credential production trong script. Token phải được cấp qua secret store của CI/load generator và không in ra log.

## 6. Chuẩn bị test data và request hợp lệ

Dữ liệu thử nghiệm cần đại diện cho kích thước và phân bố thực tế:

- ID có phân bố đủ rộng để tránh một hot key.
- Payload nhỏ, trung bình và lớn.
- Các trạng thái nghiệp vụ khác nhau.
- Record có quan hệ và index giống production.
- Tenant có mức dữ liệu khác nhau.
- Các request hợp lệ và một lượng nhỏ request lỗi có chủ đích.

Nếu tất cả request đọc cùng một record, cache có thể che giấu bottleneck database. Nếu tất cả request ghi cùng một khóa, test có thể tạo contention không đại diện. Tạo data set riêng và ghi rõ cache state trước từng lần chạy.

Với POST/PATCH, tạo idempotency key duy nhất theo từng operation. Nếu client retry, dùng lại key của operation đó. Không tạo cùng key cho tất cả virtual users vì API có thể deduplicate và làm số lượng giao dịch thấp hơn tải dự kiến.

Sau test, xác minh số bản ghi đã tạo, cập nhật hoặc xóa. Không chỉ dựa vào số response 2xx từ load generator.

## 7. Chọn công cụ load test

Một số lựa chọn thường gặp:

| Công cụ | Phù hợp với |
|---|---|
| k6 | Script JavaScript, arrival-rate executor, threshold và CI |
| Gatling | Scenario phức tạp, mô hình người dùng và báo cáo |
| JMeter | Test plan dạng GUI, protocol đa dạng và hệ sinh thái plugin |
| Locust | Kịch bản Python và hành vi user tùy chỉnh |
| Distributed Load Testing on AWS | Chạy nhiều load generator trên AWS cho tải phân tán |

Dù dùng công cụ nào, cần phân biệt **closed workload** và **open workload**:

- Closed workload giữ số virtual users cố định; khi server chậm, tốc độ phát request cũng giảm theo.
- Open workload đặt tốc độ đến độc lập; khi server chậm, request vẫn tiếp tục được phát theo lịch, phù hợp hơn để kiểm tra khả năng đáp ứng một RPS mục tiêu.

Nếu mục tiêu là 500 request/giây, arrival-rate test giúp xác minh hệ thống thực sự nhận gần 500 request/giây. Với closed workload, response chậm có thể làm generator tự giảm tốc và che giấu quá tải.

## 8. Ví dụ k6 kiểm thử API

Ví dụ dưới đây gửi request tạo đơn với arrival rate cố định. URL và token được truyền từ environment; không hardcode credential trong script.

~~~javascript
import http from "k6/http";
import { check } from "k6";
import { Rate } from "k6/metrics";

const businessSuccess = new Rate("business_success");

export const options = {
  scenarios: {
    steady_load: {
      executor: "constant-arrival-rate",
      rate: Number(__ENV.TARGET_RPS || 100),
      timeUnit: "1s",
      duration: __ENV.DURATION || "5m",
      preAllocatedVUs: 50,
      maxVUs: 200
    }
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<500", "p(99)<1000"],
    dropped_iterations: ["count==0"],
    business_success: ["rate>0.995"]
  }
};

export default function () {
  const operationId = "load-" + __VU + "-" + __ITER;

  const payload = JSON.stringify({
    customerId: "load-test-customer-" + __VU,
    items: [
      {
        sku: "TEST-SKU-" + __VU,
        quantity: 1
      }
    ]
  });

  const response = http.post(
    __ENV.API_BASE_URL + "/orders",
    payload,
    {
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + __ENV.API_TOKEN,
        "Idempotency-Key": operationId
      },
      tags: {
        route: "POST /orders"
      }
    }
  );

  const httpAccepted = check(response, {
    "response is successful": (r) =>
      r.status >= 200 && r.status < 300
  });

  let businessOk = false;
  if (httpAccepted) {
    try {
      const body = response.json();
      businessOk = Boolean(body.orderId) && body.status === "CREATED";
    } catch (error) {
      businessOk = false;
    }
  }
  businessSuccess.add(businessOk);
}
~~~

Các threshold trong ví dụ là mục tiêu minh họa. Thay bằng SLO của API. Chuẩn bị sẵn customer và SKU test tương ứng với số VU; nếu mọi VU cùng ghi một record, test có thể tạo hot key không đại diện. Đảm bảo tồn kho test đủ cho tổng số iteration hoặc reset dữ liệu theo từng lượt; nếu hết hàng, lỗi nghiệp vụ có thể bị nhầm thành lỗi capacity. Ví dụ kiểm tra cả HTTP status, orderId và trạng thái nghiệp vụ CREATED. Nếu endpoint trả 202 Accepted cho công việc bất đồng bộ, cần kiểm tra response contract và theo dõi kết quả xử lý ở downstream, không chỉ coi 202 là nghiệp vụ đã hoàn tất.

Chạy ví dụ:

~~~bash
k6 run \
  -e API_BASE_URL=https://load-test.example.com \
  -e TARGET_RPS=100 \
  -e DURATION=5m \
  api-load.js
~~~

Cấp API_TOKEN qua secret environment của runner hoặc CI. Không ghi token vào file script, command history hoặc báo cáo test.

Nếu API áp dụng rate limit theo client hoặc tenant, một token dùng chung cho mọi VU có thể chỉ kiểm tra quota của một client. Hãy tạo tập test identity đại diện cho cách traffic production được phân bổ, nhưng giữ mọi credential trong secret store.

Nếu k6 báo dropped iterations, generator không phát đủ tốc độ theo lịch. Cần tăng preAllocatedVUs/maxVUs hoặc thêm load generator, sau đó kiểm tra lại. Không được kết luận API không đạt 100 RPS nếu load generator chỉ phát được 70 RPS.

## 9. Thiết kế profile cho từng lần chạy

Một test plan có thể chia thành các giai đoạn:

~~~text
Phase 1: Warm-up
  10 RPS trong 2 phút

Phase 2: Baseline
  25 RPS trong 5 phút

Phase 3: Expected load
  100 RPS trong 15 phút

Phase 4: Peak load
  200 RPS trong 10 phút

Phase 5: Spike
  400 RPS trong 1 phút

Phase 6: Recovery
  25 RPS trong 5 phút
~~~

Đây chỉ là profile mẫu. Thay bằng traffic forecast, peak thực tế và SLO của dịch vụ. Có thể thêm soak test 1–4 giờ sau khi load test ngắn đạt yêu cầu.

Mỗi phase phải có thời gian ổn định đủ để metric phản ánh trạng thái. Ghi rõ thời điểm bắt đầu/kết thúc từng phase để đối chiếu với CloudWatch và application logs.

## 10. Tách warm request và cold start

Với Java Lambda, cần đo cả invocation đầu tiên và invocation sau khi execution environment được tái sử dụng.

Các yếu tố ảnh hưởng startup:

- JVM startup.
- Class loading và static initialization.
- Framework bootstrap.
- Dependency injection.
- AWS SDK client creation.
- Database connection.
- Deployment package size.
- Runtime và architecture.

Không trộn một cold start đơn lẻ vào latency trung bình rồi kết luận toàn API chậm. Ghi Init Duration trong Lambda logs và phân tích riêng các request có initialization.

Các phương án giảm startup:

- Giảm dependency không cần thiết.
- Dùng framework và DI container có startup phù hợp.
- Khởi tạo client dùng chung ngoài handler.
- Tránh gọi network hoặc query nặng trong static initializer.
- Dùng SnapStart hoặc Provisioned Concurrency nếu workload và runtime hỗ trợ, sau khi đo hiệu quả và chi phí.
- Tối ưu package/JAR và cấu trúc deployment.

Với Java, khởi tạo SDK client và database connection ngoài handler giúp tái sử dụng giữa các invocation của cùng execution environment. Không lưu request state hoặc dữ liệu nhạy cảm trong global mutable state.

## 11. Đo concurrency từ request rate và duration

Concurrency là số request đang được xử lý đồng thời. Công thức ước lượng:

\[
Concurrency \approx RPS \times AverageDurationSeconds
\]

Ví dụ API nhận 250 RPS và Lambda xử lý trung bình 0,24 giây:

\[
250 \times 0.24 = 60
\]

Mức concurrency trung bình ước lượng là 60. Khi duration tăng do database chậm, concurrency cũng tăng dù RPS không đổi.

Dùng peak RPS và duration đo trong load test để sizing. Công thức trung bình không thay thế việc kiểm tra burst, tail latency, scaling rate và quota. Tính riêng từng function nếu API route được tách thành nhiều Lambda.

Không nhầm RPS với concurrency. Một function có duration 50 ms có thể xử lý nhiều request mỗi giây trên mỗi environment hơn function có duration 1 giây, nhưng vẫn bị giới hạn bởi concurrency và request-rate quota.

## 12. Kiểm tra quota API Gateway

API Gateway có throttling theo account/Region và có thể có giới hạn theo stage hoặc route. Cơ chế throttling dùng token bucket với rate và burst; khi vượt mục tiêu, client có thể nhận HTTP 429.

Các throttle setting là mục tiêu best-effort, không phải một hard ceiling tuyệt đối. Hãy kiểm tra cả AWS quota, account-level quota và route-level setting; không suy ra capacity thực tế chỉ từ giá trị cấu hình trên stage.

Trước load test, kiểm tra:

- API type: HTTP API, REST API hay WebSocket API.
- Account-level throttle quota trong đúng Region.
- Route/stage throttling đã cấu hình.
- Usage plan hoặc client-level limit nếu dùng API key.
- Service quota và giới hạn do AWS áp dụng.
- Các API khác trong cùng account/Region có dùng chung quota không.

Không hardcode quota mặc định trong tài liệu thành capacity được bảo đảm. Quota có thể khác theo Region, account profile và thay đổi theo thời gian. Kiểm tra Service Quotas và cấu hình thực tế trước khi test.

Throttling là cơ chế bảo vệ. Không tăng limit chỉ để bài test xanh nếu Lambda hoặc database không thể xử lý mức tải đó.

## 13. Kiểm tra Lambda concurrency và scaling

Lambda tự mở rộng execution environment theo số request đồng thời, nhưng vẫn có account quota, function concurrency và tốc độ scale-up.

Theo dõi:

- ConcurrentExecutions.
- UnreservedConcurrentExecutions.
- Throttles.
- Invocations và Errors.
- Duration.
- ProvisionedConcurrencySpilloverInvocations nếu có PC.
- ClaimedAccountConcurrency khi cần phân tích account capacity.

Reserved Concurrency giới hạn concurrency tối đa của function và dành phần concurrency đó cho function. Nó không làm nóng execution environment.

Provisioned Concurrency cấp trước environment đã khởi tạo. Nó phù hợp khi cold start ảnh hưởng SLO và có thể sizing theo traffic baseline. PC có chi phí riêng, và invocation vượt phần đã provision vẫn có thể chạy bằng standard concurrency.

Trước khi yêu cầu tăng quota, xác định bottleneck có thực sự là Lambda hay nằm ở database/API đối tác. Tăng concurrency có thể làm downstream quá tải nhanh hơn.

## 14. Tinh chỉnh API Gateway

Các thông số cần xem xét:

- Route-level throttling rate và burst.
- Request/response payload size.
- Integration timeout và timeout phía client.
- Access logging và execution logging.
- Detailed metrics theo route.
- Caching nếu dùng API type và route hỗ trợ.
- Authentication/authorizer latency.
- WAF hoặc edge layer nếu có.
- Custom domain, TLS và DNS path.

API Gateway có metric Latency và IntegrationLatency. Latency đo thời gian từ lúc Gateway nhận request tới khi trả response; IntegrationLatency đo thời gian Gateway chờ backend. Chênh lệch giữa hai metric giúp nhận biết phần overhead ở gateway/auth/routing.

Detailed route metrics có thể phát sinh thêm chi phí CloudWatch. Chỉ bật cho route cần chẩn đoán hoặc trong thời gian điều tra, rồi review lại.

Ví dụ đặt throttling cho HTTP API route:

~~~bash
aws apigatewayv2 update-stage \
  --api-id API_ID \
  --stage-name prod \
  --route-settings '{"POST /orders":{"ThrottlingBurstLimit":50,"ThrottlingRateLimit":100}}'
~~~

Giá trị 50 burst và 100 RPS là minh họa. Thay bằng mức đã kiểm chứng với Lambda và downstream. Throttling limits là target best-effort; không xem chúng là hard real-time guarantee.

## 15. Tinh chỉnh memory và CPU cho Java Lambda

AWS Lambda cấp CPU tỷ lệ với memory. Vì vậy, tăng memory có thể làm Java xử lý nhanh hơn nếu workload bị giới hạn bởi CPU, class loading hoặc serialization.

Một quy trình benchmark:

1. Chọn các mức memory khác nhau, ví dụ 512, 1.024, 1.769 và 3.072 MB.
2. Dùng cùng artifact, payload, dependency và traffic.
3. Chạy warm test và cold-start test riêng.
4. Đo Duration, Max Memory Used và error rate.
5. Tính GB-seconds và cost per successful request.
6. Chọn cấu hình đáp ứng SLO với tổng chi phí phù hợp.

Ở mức 1.769 MB, Lambda cấp lượng CPU tương đương một vCPU theo tài liệu hiện hành. Đây là mốc tham khảo, không phải cấu hình tối ưu cho mọi API.

Ví dụ minh họa:

| Memory | Duration | Compute gần đúng |
|---:|---:|---:|
| 512 MB | 400 ms | 0,20 GB-s |
| 1.024 MB | 230 ms | 0,23 GB-s |
| 1.769 MB | 120 ms | 0,21 GB-s |
| 3.072 MB | 90 ms | 0,27 GB-s |

Số liệu là giả định để minh họa. Cấu hình memory lớn hơn có thể giảm duration nhưng làm compute cost tăng. Hãy đo trên workload thật thay vì chọn theo số MB thấp nhất.

## 16. Tinh chỉnh Java handler và framework

Các điểm cần kiểm tra:

- Tách handler khỏi domain logic để test độc lập.
- Giảm package size và chỉ đóng gói dependency cần dùng.
- Khởi tạo AWS SDK client ngoài handler.
- Tái sử dụng HTTP client và connection pool có giới hạn.
- Giảm reflection/classpath scanning không cần thiết.
- Tránh tạo object lớn hoặc serialize lặp lại trong hot path.
- Tránh blocking call tuần tự khi có thể gộp query an toàn.
- Tránh thread pool lớn hơn khả năng CPU hoặc downstream.
- Không giữ mutable request data trong static field.
- Kiểm tra GC pause, heap usage và allocation rate khi stress test.

Nếu API dùng Spring Boot, Quarkus, Micronaut hoặc framework khác, benchmark chính ứng dụng đó. Không suy luận startup hoặc memory chỉ từ benchmark framework mẫu.

## 17. Tái sử dụng HTTP client và SDK

Mở kết nối mới cho mỗi request làm tăng latency và CPU, đặc biệt khi Java function scale lên nhiều execution environment.

Nên:

- Khởi tạo SDK client và HTTP client dùng chung ở initialization.
- Bật connection reuse/keep-alive phù hợp.
- Đặt connection pool max theo concurrency và downstream limit.
- Đặt connect timeout, response timeout và idle timeout.
- Phát hiện connection stale và reconnect.
- Không để request-specific header hoặc credential bị giữ lại giữa invocation.
- Không để pool tạo số lượng connection không giới hạn.

Execution environment có thể được tái sử dụng nhưng không được bảo đảm tồn tại vĩnh viễn. Lambda có thể đóng idle connection; code cần xử lý connection reset và tái kết nối.

## 18. Database là giới hạn phổ biến của serverless API

Lambda có thể scale nhanh hơn khả năng mở connection của database. Nếu mỗi environment mở nhiều connection, một burst có thể làm database hết connection dù CPU của Lambda vẫn thấp.

Tính tổng connection có thể mở:

\[
PotentialConnections =
LambdaConcurrency \times PoolSizePerEnvironment
\]

Ví dụ 80 environment, mỗi environment có pool 5 connection:

\[
80 \times 5 = 400\ connections
\]

Đây là số connection tiềm năng, không phải lúc nào cũng được mở hết. Tuy nhiên, cần so với max_connections của database và phần capacity dành cho ứng dụng khác, migration, monitoring và admin.

Biện pháp:

- Giới hạn Lambda Reserved Concurrency theo khả năng database.
- Giảm pool size mỗi environment.
- Tái sử dụng connection.
- Dùng query/index phù hợp.
- Giảm N+1 query.
- Dùng pagination và giới hạn result set.
- Dùng RDS Proxy nếu workload tạo nhiều short-lived connection và cần connection pooling/multiplexing.
- Cân nhắc DynamoDB hoặc datastore phù hợp với access pattern nếu relational query không phải yêu cầu bắt buộc.

RDS Proxy giúp quản lý và chia sẻ connection giữa client với database. Nó không làm query nặng chạy nhanh hơn và cũng không thay thế việc giới hạn concurrency, tối ưu SQL hoặc thiết kế index.

## 19. Tinh chỉnh RDS Proxy và connection pool

Theo dõi:

- DatabaseConnections.
- MaxDatabaseConnectionsAllowed.
- DatabaseConnectionsBorrowLatency.
- Connection borrow timeout.
- Query latency và database CPU.
- Connection pinning nếu proxy không multiplex được session.

Nếu borrow latency tăng, proxy có thể đã gần hết connection khả dụng hoặc query giữ connection quá lâu. Tăng pool client không giải quyết vấn đề; đôi khi còn làm tình trạng nặng hơn.

RDS Proxy có chi phí riêng. So sánh chi phí proxy với lợi ích giảm connection churn, giảm lỗi kết nối và tăng khả năng chịu burst.

## 20. Thiết lập timeout theo tầng

Timeout phải có thứ tự hợp lý để request không bị treo ở tầng dưới sau khi caller đã bỏ cuộc.

Một mô hình:

~~~text
Client timeout:            8 seconds
API Gateway integration:   7 seconds
Lambda timeout:            6 seconds
Database query timeout:    3 seconds
External API timeout:      2 seconds
~~~

Các giá trị trên chỉ minh họa. Trong thực tế, tổng thời gian các dependency tuần tự cộng thời gian xử lý phải nằm trong timeout của Lambda và gateway.

Nếu API gọi nhiều dependency song song, tính theo nhánh chậm nhất cộng overhead. Nếu gọi tuần tự, cộng thời gian của từng bước. Dành thời gian cho serialize response và cleanup.

Không để retry ở nhiều tầng nhân lên ngoài dự kiến. Ví dụ client retry 3 lần, gateway retry 2 lần và SDK retry 3 lần có thể tạo nhiều request hơn tải gốc. Chỉ retry lỗi transient, dùng exponential backoff với jitter và bảo đảm operation idempotent.

## 21. Rate limiting và bảo vệ downstream

Rate limit bảo vệ API và dependency trước traffic burst. Có thể giới hạn theo route, API key, tenant hoặc client identity.

Các nguyên tắc:

- Giới hạn route ghi nhạy cảm thấp hơn route đọc nếu dependency cần.
- Dùng 429 và Retry-After khi phù hợp với API contract.
- Client retry với backoff và jitter.
- Không retry vô hạn.
- Giới hạn concurrency ở function.
- Đặt bulkhead cho từng dependency.
- Có circuit breaker cho partner API.
- Trả degraded response nếu nghiệp vụ cho phép.
- Đưa công việc dài sang queue và trả 202 Accepted.

Đừng dùng API Gateway throttle như cơ chế duy nhất để bảo vệ database. Lambda concurrency, application semaphore, connection pool và database capacity đều cần được cấu hình đồng bộ.

## 22. Tối ưu payload, serialization và pagination

Payload lớn làm tăng network time, memory và serialization cost. Một số biện pháp:

- Chỉ trả field client cần.
- Dùng pagination và giới hạn page size.
- Không trả toàn bộ entity graph.
- Dùng DTO riêng cho response.
- Tránh serialize object chứa lazy relationship.
- Nén response nếu client và gateway hỗ trợ và lợi ích lớn hơn CPU cost.
- Đặt request size limit.
- Dùng object storage cho file lớn thay vì truyền qua API function.
- Tránh log toàn bộ request/response.

Nếu response cần hàng trăm nghìn record, API đồng bộ có thể không phù hợp. Dùng export job bất đồng bộ, lưu kết quả vào object storage và trả URL có thời hạn.

## 23. Caching và read-heavy workload

Caching có thể giảm database query và latency cho dữ liệu ít thay đổi.

Các lớp cache có thể gồm:

- Client cache với Cache-Control/ETag.
- CDN hoặc edge cache.
- API Gateway cache nếu dùng REST API và cấu hình hỗ trợ.
- Application cache trong execution environment.
- Redis/ElastiCache hoặc cache service dùng chung.

Cần định nghĩa:

- TTL.
- Cache key và tenant isolation.
- Invalidation khi dữ liệu thay đổi.
- Behavior khi cache unavailable.
- Cache stampede và single-flight.
- Cách tránh lưu dữ liệu nhạy cảm sai tenant.
- Cache hit ratio và cost.

Không dùng in-memory cache của Lambda làm nguồn dữ liệu authoritative. Environment có thể bị tái tạo hoặc nhiều environment có cache khác nhau.

## 24. Thiết kế observability trước khi load test

Không có dashboard thì load test chỉ cho biết client thấy chậm, không cho biết tầng nào chậm.

Nên có ba lớp quan sát:

**API Gateway**
- Count.
- 4xx và 5xx.
- Latency.
- IntegrationLatency.
- DataProcessed.
- Throttling và route-level metrics nếu đã bật.

**Lambda**
- Invocations.
- Errors.
- Throttles.
- Duration.
- ConcurrentExecutions.
- ProvisionedConcurrencyUtilization và Spillover nếu dùng PC.
- Init Duration từ log/trace.
- Max Memory Used từ REPORT log.

**Database/dependency**
- CPU, memory, connections.
- Query latency.
- Lock wait.
- Connection borrow latency.
- Cache hit/miss.
- Partner API latency và 429/5xx.
- Network error và timeout.

API Gateway HTTP API gửi metric mặc định theo chu kỳ một phút. Detailed route metrics có thể phát sinh thêm chi phí CloudWatch; bật khi cần phân tích route cụ thể.

## 25. Trace và correlation ID

Dùng một request/correlation ID xuyên suốt:

~~~text
Client
  -> API Gateway request ID
  -> Lambda context request ID
  -> Application correlation ID
  -> Database query / external API
  -> Response
~~~

Log nên có:

- Timestamp.
- Correlation ID.
- Lambda request ID.
- Route và HTTP method.
- Status code.
- Application duration.
- Dependency duration.
- Retry count.
- Release/version identifier.
- Error code.

Dùng AWS X-Ray hoặc OpenTelemetry để trace các span quan trọng. Không log access token, password, secret, authorization header hoặc raw PII.

Nếu tracing tạo overhead đáng kể, dùng sampling phù hợp và đo lại sau khi bật. Tránh bật trace 100% lâu dài nếu cost hoặc throughput bị ảnh hưởng và không có lý do cần thiết.

## 26. Chẩn đoán bottleneck từ metric

| Triệu chứng | Nguyên nhân có thể | Kiểm tra tiếp |
|---|---|---|
| API Latency tăng, IntegrationLatency ổn định | Gateway/auth/edge/client path | Authorizer, WAF, TLS, DNS và client network |
| IntegrationLatency tăng cùng Lambda Duration | Function hoặc dependency | Lambda logs, trace và downstream span |
| Lambda Duration tăng, memory gần giới hạn | Memory pressure, GC hoặc payload lớn | Max Memory Used, heap và GC |
| Throttles tăng | Lambda concurrency hoặc scaling/quota | ConcurrentExecutions, reserved/account quota |
| API Gateway 429 tăng | Gateway throttle target hoặc quota | Route/account limits và client rate |
| Lambda 5xx tăng, database CPU cao | Query/database bottleneck | Query plan, locks, connections |
| Database borrow latency tăng | Proxy/pool gần cạn | RDS Proxy metrics và pool settings |
| p99 tăng nhưng p50 ổn | Cold start hoặc outlier dependency | Init Duration, trace và slow query |
| Error tăng sau thời gian dài | Leak, pool exhaustion, memory growth | Soak test, heap, connections và thread |
| Throughput không tăng dù thêm VUs | Generator, quota hoặc downstream đã bão hòa | Load generator CPU, dropped iterations, throttle |
| Chi phí tăng nhanh hơn traffic | Retry, duration, logging hoặc dependency | Cost per success và request breakdown |

Không điều chỉnh cấu hình trước khi xác định bottleneck. Tăng memory khi database là nút thắt chỉ tăng chi phí Lambda mà không cải thiện throughput.

## 27. Quy trình tinh chỉnh từng biến

Một vòng tối ưu có kiểm soát:

1. Chạy baseline với cấu hình hiện tại.
2. Lưu artifact, environment, payload và test profile.
3. Xác định bottleneck chính.
4. Chọn một biến để thay đổi.
5. Chạy lại cùng workload.
6. So sánh latency, throughput, errors, resource và cost.
7. Chạy regression test cho correctness.
8. Giữ cấu hình nếu đạt SLO và unit cost tốt hơn.
9. Nếu không đạt, rollback cấu hình và ghi lý do.
10. Lặp lại với biến tiếp theo.

Không thay đổi memory, timeout, reserved concurrency, pool size và route throttle cùng lúc. Nếu kết quả tốt hơn, nhóm sẽ không biết thay đổi nào tạo ra hiệu quả.

## 28. Ma trận cấu hình cần benchmark

| Biến | Các mức thử | Metric quyết định |
|---|---|---|
| Lambda memory | 512 / 1.024 / 1.769 / 3.072 MB | Duration, GB-seconds, memory peak |
| Lambda timeout | Theo latency budget và tail duration | Timeout rate, duration |
| Reserved concurrency | Theo dependency capacity | Throttles, DB connections |
| Provisioned Concurrency | Baseline/peak có dự báo | Init, spillover, utilization, cost |
| Java framework | Framework/config hiện tại và bản tối giản | Init Duration, memory, package size |
| HTTP connection pool | Nhỏ/vừa/lớn có giới hạn | Pool wait, connection errors |
| DB pool | Theo concurrency và DB max connections | DB CPU, borrow latency |
| API Gateway throttle | Rate/burst theo route | 429, downstream saturation |
| Cache TTL | Theo freshness requirement | Hit ratio, stale response, DB load |
| Payload/page size | Nhỏ/vừa/lớn | Serialization, network, memory |

Giá trị trong bảng chỉ là dải thử nghiệm minh họa. Không triển khai mức cấu hình mới nếu chưa kiểm tra giới hạn của service và dependency.

## 29. Ví dụ cập nhật cấu hình Lambda

Ví dụ thay memory và timeout:

~~~bash
aws lambda update-function-configuration \
  --function-name orders-api \
  --memory-size 1769 \
  --timeout 10
~~~

Ví dụ đặt Reserved Concurrency:

~~~bash
aws lambda put-function-concurrency \
  --function-name orders-api \
  --reserved-concurrent-executions 80
~~~

Các lệnh chỉ minh họa. Thay function name và giá trị bằng cấu hình đã benchmark, kiểm tra quota account và phê duyệt thay đổi trước khi áp dụng production.

Nếu dùng alias/version, đảm bảo API Gateway integration trỏ đúng version/alias và có quy trình publish/rollback. Không giả định cập nhật $LATEST sẽ tự động thay đổi mọi caller theo cùng một cách.

## 30. Xác định capacity envelope

Sau khi test, ghi lại giới hạn đã chứng minh:

| Thành phần | Kết quả cần bàn giao |
|---|---|
| API | Sustained RPS, burst RPS, p95/p99 |
| Lambda | Memory, timeout, peak concurrency, throttles |
| API Gateway | Route/account throttle settings, 429 behavior |
| Database | Connection limit, tested query throughput, CPU headroom |
| Cache | Hit ratio, throughput và memory |
| External API | Rate limit, timeout, retry policy |
| Load generator | Số worker/VU, CPU/network utilization |
| Cost | Chi phí trên 1.000 request và giao dịch thành công |

Capacity envelope chỉ đúng với artifact, cấu hình, Region, dữ liệu, dependency và test profile đã ghi. Nếu thay framework, schema, query, memory, route hoặc database class, cần đánh giá lại.

## 31. Tính chi phí trên mỗi request thành công

Chi phí serverless API có thể gồm:

- API Gateway request và data processing.
- Lambda request và GB-seconds.
- Provisioned Concurrency nếu bật.
- CloudWatch Logs, metrics và tracing.
- Data transfer, NAT và VPC networking.
- RDS/RDS Proxy, cache và storage.
- External API hoặc dịch vụ phụ thuộc.
- Retry, duplicate và request thất bại.

Công thức đơn giản:

\[
CostPerSuccess =
\frac{TotalTestCost}{SuccessfulBusinessTransactions}
\]

Và:

\[
CostPer1000Success =
CostPerSuccess \times 1000
\]

Không chia cho tổng số invocation nếu một giao dịch có thể retry nhiều lần. Dùng số nghiệp vụ hoàn tất và hợp lệ làm mẫu số.

Tách chi phí load test khỏi steady-state production. Load test tạo traffic nhân tạo, logging và tracing bổ sung; hãy ghi riêng để không nhầm với cost forecast.

## 32. Release gate trước khi production

Trước khi mở traffic production, kiểm tra:

**Correctness**
- Contract và response schema đúng.
- Authentication/authorization hoạt động.
- Validation và error mapping đúng.
- Idempotency cho write operation.
- Pagination và data consistency đúng.

**Performance**
- Sustained và peak load đạt SLO.
- p95/p99 đạt mục tiêu.
- Error rate trong error budget.
- Không có unexplained dropped iterations.
- Database và external API còn headroom.

**Reliability**
- Timeout và retry có giới hạn.
- Throttling trả đúng status.
- Circuit breaker/backpressure hoạt động.
- Alarm và dashboard đã bật.
- Rollback đã được diễn tập.

**Security**
- IAM least privilege.
- Secret nằm trong secret store.
- Không log token/PII.
- Rate limit và abuse protection.
- Test data được dọn theo policy.

**Cost**
- Cost per successful transaction nằm trong ngân sách.
- Logging/tracing volume được kiểm soát.
- Provisioned capacity có lý do và schedule nếu cần.
- Cost anomaly/budget alert có owner.

## 33. Canary và rollout sau load test

Load test đạt không có nghĩa cần chuyển 100% traffic ngay lập tức. Có thể triển khai theo các bước:

~~~text
Stage 1: 1% traffic
Stage 2: 5% traffic
Stage 3: 10% traffic
Stage 4: 25% traffic
Stage 5: 50% traffic
Stage 6: 100% traffic
~~~

Mỗi stage cần thời gian quan sát đủ dài. Theo dõi p95/p99, 4xx/5xx, Lambda Throttles, database connections, business success và cost.

Dùng alias, weighted routing hoặc cơ chế deployment phù hợp. Đặt ngưỡng rollback trước khi bắt đầu. Nếu error rate hoặc business invariant vượt ngưỡng, dừng tăng traffic và chuyển về version ổn định.

## 34. Chuẩn bị operational handover

Bàn giao không chỉ là gửi source code và endpoint. Đội nhận vận hành cần hiểu cách hệ thống hoạt động, giới hạn tải, cách xử lý lỗi và cách khôi phục.

Gói bàn giao nên có:

| Nhóm | Nội dung |
|---|---|
| Service overview | Mục đích API, owner, dependency và sơ đồ kiến trúc |
| API contract | OpenAPI, route, request/response schema, error code |
| Authentication | Auth flow, role, scope, token lifetime và secret reference |
| Deployment | IaC, artifact, runtime, version/alias và release process |
| Configuration | Memory, timeout, concurrency, throttle, environment variable names |
| Networking | VPC, subnet, security group, endpoint và DNS |
| Data | Database schema, migration, index, backup và retention |
| Observability | Dashboard, alarms, log group, trace và correlation ID |
| Capacity | Tested RPS, p95/p99, concurrency, dependency limits |
| Cost | Monthly forecast, cost per transaction và budget alarm |
| Operations | Runbook, on-call owner, escalation và incident process |
| Recovery | Rollback, backup restore và DR assumptions |
| Security | IAM policy, secret location, data classification và audit |

Không đưa secret value hoặc private key vào tài liệu bàn giao. Chỉ ghi tên secret, ARN/reference và quy trình xin quyền truy cập.

## 35. Dashboard và alarm cần bàn giao

Dashboard tối thiểu nên có:

**API Gateway**
- Request count.
- 4xx/5xx.
- Latency và IntegrationLatency.
- Throttle/429.

**Lambda**
- Invocations, Errors, Throttles.
- Duration p50/p95/p99.
- ConcurrentExecutions.
- Init Duration từ log/trace.
- Max Memory Used từ REPORT logs hoặc Lambda Insights.
- Provisioned Concurrency utilization/spillover nếu có.

**Database**
- CPU/memory.
- Connections.
- Query latency.
- Lock wait.
- Proxy borrow latency nếu dùng RDS Proxy.

**Business**
- Orders created/confirmed.
- Payment success/failure.
- Validation rejection.
- Duplicate/idempotency conflict.
- Business transaction success rate.

Alarm cần có owner, severity, threshold, evaluation window và hành động khi kích hoạt. Tránh tạo alarm chỉ để có màu xanh trên dashboard; mỗi alarm cần liên kết với một runbook hoặc quyết định cụ thể.

## 36. Runbook xử lý sự cố API

Một runbook ngắn nên hướng dẫn:

| Triệu chứng | Hành động đầu tiên |
|---|---|
| HTTP 429 tăng | Kiểm tra Gateway throttle, Lambda concurrency và client retry |
| HTTP 5xx tăng | Phân biệt Lambda error, integration error và dependency failure |
| p99 tăng | Kiểm tra Init Duration, database latency và external API |
| Lambda Throttles tăng | Kiểm tra account quota, reserved concurrency và scaling |
| Database connections cao | Kiểm tra pool, Lambda concurrency và RDS Proxy |
| Memory gần giới hạn | Kiểm tra heap, payload, allocation và GC |
| Cost tăng bất thường | Kiểm tra request volume, retry loop, logs và recursive invocation |
| API không truy cập được | Kiểm tra DNS, custom domain, API deployment, IAM/resource policy |
| Release mới lỗi | Dừng rollout và rollback alias/version |
| Data inconsistency | Dừng side effect nguy hiểm, đối soát và chạy recovery procedure |

Runbook cần chỉ rõ dashboard, log query, người chịu trách nhiệm và điều kiện escalation. Không yêu cầu người trực phải tự tìm tất cả thông tin trong source code.

## 37. Những nội dung phải có trong báo cáo load test

Báo cáo cuối cùng nên lưu:

- Ngày giờ và Region.
- Git commit, artifact digest và Lambda version.
- API stage, route và cấu hình Gateway.
- Memory, timeout, concurrency và database configuration.
- Load generator, số worker/VU và script version.
- Test data profile và tỷ trọng route.
- Các phase: smoke, baseline, load, spike, soak, recovery.
- Actual RPS và dropped iterations.
- p50/p95/p99 latency.
- 4xx/5xx, throttles và timeout.
- Lambda Duration, memory và concurrency.
- Database CPU, connections và query latency.
- Cost estimate và cost per success.
- Giới hạn đã gặp.
- Điều kiện test chưa bao phủ.
- Quyết định cấu hình cuối cùng và người phê duyệt.

Không chỉ gửi ảnh chụp dashboard. Giữ raw result, script và metadata để có thể chạy lại cùng điều kiện.

## 38. Lỗi thường gặp khi load test

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ test handler trực tiếp | Bỏ qua Gateway và auth overhead | Test end-to-end |
| Dùng closed workload cho mục tiêu RPS | Server chậm làm generator tự giảm tốc | Dùng arrival-rate model |
| Load generator không đủ capacity | Tạo bottleneck giả | Theo dõi CPU/network/dropped iterations |
| Test chỉ một route | Bỏ sót route nặng | Dùng workload mix |
| Chỉ dùng một test record | Cache/hot key làm sai kết quả | Dữ liệu phân bố thực tế |
| Không kiểm tra quota | Test fail do account limit | Preflight Service Quotas |
| Retry không idempotent | Tạo duplicate order/payment | Dùng idempotency key |
| Chạy soak test không kiểm soát | Chi phí tăng và data tích lũy | Budget, duration cap và cleanup |
| Tăng Lambda concurrency quá nhanh | Database hết connection | Giới hạn concurrency và pool |
| Chọn memory thấp nhất | CPU-bound function chạy lâu | Benchmark memory/CPU |
| Chỉ nhìn average latency | Bỏ sót tail latency | Đo p95/p99 |
| Không có rollback | Release lỗi kéo dài outage | Runbook và canary gates |

## 39. Checklist bàn giao dịch vụ API

**Kiến trúc và contract**

1. Sơ đồ request path và dependency đã cập nhật?
2. OpenAPI và error contract đã bàn giao?
3. Authentication, authorization và rate limit đã mô tả?
4. Idempotency và pagination đã được giải thích?

**Hiệu năng và capacity**

5. Load test report có thể chạy lại?
6. Capacity envelope có RPS, concurrency, p95/p99?
7. Lambda memory/timeout/concurrency đã ghi?
8. Gateway quota và throttle đã xác nhận?
9. Database connection/pool limit đã ghi?
10. Cost per successful transaction đã tính?

**Vận hành**

11. Dashboard và alarms đã có owner?
12. Runbook cho 429/5xx/timeout/database failure?
13. Rollback version/alias đã thử?
14. On-call và escalation path đã xác định?
15. Backup/restore và DR assumptions đã ghi?

**Bảo mật và quyền truy cập**

16. IAM least privilege đã review?
17. Secret reference và rotation owner đã bàn giao?
18. Log đã loại bỏ token/PII?
19. Load test data đã được dọn hoặc có retention?
20. Quyền truy cập console, log và dashboard đã cấp đúng nhóm?

**Acceptance**

21. Service owner đã nhận source, artifact và IaC?
22. Operations owner đã xác nhận dashboard/runbook?
23. SLO và error budget đã thống nhất?
24. Known limitations và residual risks đã ghi?
25. Có biên bản xác nhận bàn giao và ngày bắt đầu support?

## Tài liệu tham khảo

- [AWS Lambda: How to test serverless functions and applications](https://docs.aws.amazon.com/lambda/latest/dg/testing-guide.html)
- [AWS Lambda: Understanding concurrency and scaling](https://docs.aws.amazon.com/lambda/latest/dg/lambda-concurrency.html)
- [AWS Lambda: Lambda quotas](https://docs.aws.amazon.com/lambda/latest/dg/gettingstarted-limits.html)
- [AWS Lambda: Best practices for Lambda Event Functions](https://docs.aws.amazon.com/lambda/latest/dg/best-practices.html)
- [AWS Lambda: Java handler and code best practices](https://docs.aws.amazon.com/lambda/latest/dg/java-handler.html)
- [Amazon API Gateway: HTTP API CloudWatch metrics](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-metrics.html)
- [Amazon API Gateway: HTTP API throttling](https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-throttling.html)
- [Amazon RDS: Using Lambda with RDS](https://docs.aws.amazon.com/lambda/latest/dg/services-rds.html)
- [Amazon RDS Proxy: Connection considerations](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy-connections.html)
- [Grafana k6: Constant arrival rate executor](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/)

## Kết luận

Kiểm thử tải cho Java serverless API phải đo toàn bộ request path và dùng workload đại diện. Cần phân biệt RPS, concurrency, Gateway throttling và giới hạn downstream; đo p95/p99, error rate, memory, duration, database connection và chi phí trên mỗi giao dịch thành công.

Tinh chỉnh theo số liệu, thay đổi từng biến một và kiểm tra lại cùng profile. Java handler nên tái sử dụng client an toàn, giảm initialization và package overhead, còn concurrency phải phù hợp với khả năng database và external API. Provisioned Concurrency chỉ nên dùng khi startup latency thực sự ảnh hưởng SLO.

Bàn giao hoàn tất khi đội nhận có API contract, artifact/IaC, cấu hình, capacity envelope, dashboard, alarms, runbook, rollback, cost model và owner rõ ràng. Báo cáo load test phải ghi cả giới hạn đã kiểm chứng lẫn những tình huống chưa được thử để tránh coi kết quả benchmark là bảo đảm tuyệt đối cho mọi traffic tương lai.

