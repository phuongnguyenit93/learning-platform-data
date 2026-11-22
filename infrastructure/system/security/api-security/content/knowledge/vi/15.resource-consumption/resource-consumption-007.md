# Load test và cost guardrail cho endpoint đắt

Một endpoint có thể hoạt động đúng với vài request mỗi giây nhưng làm cạn CPU, database connection, bộ nhớ hoặc ngân sách dịch vụ khi tải tăng. Những endpoint như tìm kiếm nhiều bộ lọc, tạo báo cáo, export dữ liệu, xử lý tệp, tính toán tổng hợp hoặc gọi nhiều service bên ngoài thường tiêu tốn tài nguyên lớn hơn một thao tác đọc đơn giản.

Load test giúp xác định hệ thống chịu được mức tải nào, độ trễ và tỷ lệ lỗi thay đổi ra sao khi tải tăng, cũng như điểm bắt đầu bão hòa. Cost guardrail đặt giới hạn để một caller, tenant hoặc luồng nghiệp vụ không thể tiêu thụ tài nguyên vượt ngân sách dự kiến. Hai việc cần đi cùng nhau: load test đo hành vi dưới tải; guardrail giới hạn công việc mà hệ thống chấp nhận và thực thi.

Trong API Security, đây là cách giảm nguy cơ *Unrestricted Resource Consumption*. Một người dùng đã xác thực vẫn có thể lạm dụng endpoint đắt bằng cách gửi request quá thường xuyên, yêu cầu phạm vi dữ liệu quá lớn, tạo nhiều job song song hoặc khiến service gọi dependency tốn phí. Authentication và authorization cần được kết hợp với giới hạn tài nguyên theo endpoint, caller và tenant.

## 1. Nhận diện endpoint có chi phí cao

Không nên chỉ dựa vào thời gian phản hồi trung bình để xác định endpoint đắt. Một request có thể trả nhanh nhưng kích hoạt nhiều công việc bất đồng bộ, truy vấn lớn hoặc lời gọi dịch vụ tính phí sau khi response đã được gửi.

Các nhóm endpoint thường cần guardrail riêng:

| Nhóm | Ví dụ | Tài nguyên có thể bị tiêu hao |
|---|---|---|
| Search/filter | Tìm kiếm với nhiều điều kiện, wildcard hoặc sort tùy ý | CPU, RAM, index I/O, database I/O |
| Report/aggregate | Tổng hợp doanh thu, thống kê theo thời gian dài | CPU, database scan, memory, temporary storage |
| Export | CSV/PDF hoặc tải toàn bộ dữ liệu tenant | Database, CPU, storage, network egress, queue worker |
| File processing | OCR, chuyển đổi định dạng, nén hoặc quét tệp | CPU, RAM, storage, thời gian worker |
| Fan-out API | Một request gọi nhiều service hoặc provider | Connection pool, network, chi phí provider, retry |
| Batch/bulk | Một request chứa hàng nghìn ID hoặc thao tác | Database, lock, transaction log, queue |
| AI/compute task | Phân tích hoặc tính toán theo payload lớn | GPU/CPU, token hoặc phí theo lần gọi |

Với mỗi endpoint, hãy xác định yếu tố làm chi phí tăng: số bản ghi, khoảng thời gian, kích thước tệp, số service được gọi, số bước xử lý, độ sâu lồng nhau, số lần retry hay mức độ song song. Đó là các đầu vào cần giới hạn và đưa vào kịch bản kiểm thử.

## 2. Đặt SLO và ngân sách trước khi chạy load test

Load test chỉ có ý nghĩa khi biết hệ thống cần đạt điều gì. Trước khi chạy, hãy thống nhất:

- **Throughput:** số request hoặc job hoàn tất mỗi giây/phút.
- **Latency:** thời gian phản hồi ở p50, p95 và p99; với job bất đồng bộ, đo cả thời gian chờ trong queue và thời gian hoàn tất.
- **Error rate:** tỷ lệ lỗi tổng thể và theo loại lỗi, gồm timeout, `429`, `5xx` và lỗi nghiệp vụ.
- **Availability:** tỷ lệ request hợp lệ được xử lý trong điều kiện tải mục tiêu.
- **Resource saturation:** CPU, memory, thread, connection pool, database IOPS, queue depth và network.
- **Cost:** chi phí hoặc đơn vị tài nguyên cho mỗi request/job thành công và theo tenant.

Ví dụ mục tiêu cho một endpoint xem trước báo cáo có thể là p95 dưới 800 ms, p99 dưới 2 giây, tỷ lệ lỗi dưới 1% ở tải 20 request/giây, đồng thời không vượt ngưỡng CPU hoặc database connection đã thống nhất. Đây chỉ là số minh họa; SLO thật phải dựa trên nhu cầu sản phẩm, dependency và năng lực hạ tầng.

Không chỉ đặt mục tiêu latency. Một hệ thống có thể đạt p95 thấp bằng cách từ chối nhiều request với `429`; khi đó cần đánh giá cả throughput được chấp nhận và tỷ lệ request bị từ chối. Với endpoint export trả `202 Accepted`, SLO nên đo thời gian nhận job và thời gian hoàn tất job riêng biệt.

## 3. Xây dựng workload model sát thực tế

Kịch bản tải cần phản ánh cách người dùng và hệ thống tích hợp thực sự gọi API. Chỉ lặp một request nhỏ với một tài khoản duy nhất thường không phát hiện được các vấn đề về tenant fairness, cache, connection pool hoặc dữ liệu lớn.

Xác định các thành phần sau:

| Thành phần | Câu hỏi cần trả lời |
|---|---|
| Arrival rate | Có bao nhiêu request mới được gửi mỗi giây? Tải có tăng theo giờ cao điểm không? |
| Concurrency | Có bao nhiêu request hoặc job đang chạy cùng lúc? |
| Mix endpoint | Bao nhiêu phần trăm là preview, search, export, polling và thao tác thông thường? |
| Payload | Request nhỏ, trung bình và lớn có tỷ lệ ra sao? |
| Data cardinality | Tenant có 1 nghìn, 100 nghìn hay hàng triệu bản ghi? |
| Tenant distribution | Tải phân bố đều hay có một vài tenant lớn tạo phần lớn traffic? |
| Caller distribution | Một người dùng, nhiều người dùng, API key hoặc service account? |
| Cache behavior | Request lặp lại có cache hit hay thường truy vấn dữ liệu mới? |
| Dependency behavior | Service ngoài có độ trễ, lỗi và quota như thế nào? |
| Retry behavior | Client/proxy có retry khi timeout hoặc nhận `429`/`5xx` không? |

Hãy đưa vào cả trường hợp trung bình và trường hợp biên hợp lệ: khoảng thời gian báo cáo dài nhất được cho phép, page size tối đa, số filter tối đa, file gần giới hạn và tenant có dữ liệu lớn. Không tạo payload vượt hợp đồng chỉ để làm hệ thống quá tải; mục tiêu là xác minh server xử lý đầu vào hợp lệ trong giới hạn đã công bố.

### Open model và closed model

- **Closed workload model:** một số lượng virtual users cố định gửi request tiếp theo sau khi request trước hoàn tất hoặc sau think time. Khi hệ thống chậm, tốc độ gửi request tự giảm.
- **Open workload model:** đặt trước tốc độ request đến, ví dụ 20 request/giây, bất kể response trước nhanh hay chậm. Mô hình này phù hợp để kiểm tra hệ thống trước một arrival rate xác định và phát hiện queue tăng khi service không theo kịp.

Với API có traffic đến từ webhook, scheduler hoặc nhiều client độc lập, open model thường giúp mô phỏng offered load rõ hơn. Closed model vẫn hữu ích khi muốn mô phỏng số người dùng đồng thời và hành vi chờ của người dùng. Nên chọn mô hình theo câu hỏi cần trả lời, không coi một mô hình là đúng cho mọi bài test.

## 4. Chọn loại load test phù hợp

| Loại test | Cách chạy | Mục đích |
|---|---|---|
| Smoke/load sanity | Tải nhỏ trong thời gian ngắn | Xác minh script, dữ liệu, authentication và metric hoạt động |
| Baseline | Tải ổn định ở mức thông thường | Ghi nhận latency, throughput và cost cơ sở |
| Load test | Tải dự kiến trong giờ cao điểm | Kiểm tra SLO ở điều kiện vận hành mục tiêu |
| Stress test | Tăng dần vượt mức dự kiến | Tìm điểm bão hòa và cách hệ thống suy giảm |
| Spike test | Tăng tải đột ngột | Kiểm tra burst, queue, autoscaling và admission control |
| Soak test | Duy trì tải trong thời gian dài | Phát hiện memory leak, pool exhaustion và queue tích tụ |
| Capacity test | Tăng tải theo bước có kiểm soát | Xác định năng lực tối đa trước khi SLO không còn đạt |
| Dependency failure test | Làm chậm hoặc mô phỏng lỗi dependency | Kiểm tra timeout, circuit breaker, retry và load shedding |

Nên bắt đầu bằng smoke test rồi baseline trước khi tăng tải. Stress và spike test cần có ngưỡng dừng để không làm ảnh hưởng môi trường dùng chung. Soak test giúp phát hiện vấn đề không xuất hiện trong bài test vài phút.

## 5. Chuẩn bị môi trường và dữ liệu an toàn

Ưu tiên môi trường load test có cấu hình gần production nhưng được cô lập về dữ liệu và dependency. Nếu cần dùng production-like service hoặc dữ liệu có dung lượng tương tự, tạo dữ liệu giả lập có phân bố và kích thước gần thực tế.

Trước khi chạy:

- Dùng tenant và tài khoản thử nghiệm được cấp riêng; không dùng token hoặc dữ liệu cá nhân production.
- Xác định rõ môi trường, endpoint, thời gian chạy, tốc độ tối đa và người chịu trách nhiệm.
- Kiểm tra test có thể gửi email, webhook, SMS, thanh toán hoặc gọi provider thật hay không; thay bằng sandbox/mock khi có thể.
- Đặt giới hạn dừng khi error rate, CPU, queue depth, DB connection hoặc chi phí vượt ngưỡng.
- Tắt hoặc giới hạn autoscaling ngoài dự kiến nếu mục tiêu là đo năng lực cố định; nếu mục tiêu là kiểm tra autoscaling, ghi lại cấu hình và giới hạn scale.
- Đồng bộ thời gian và correlation ID để nối request với trace, log và metric.
- Thông báo cho nhóm vận hành và tránh chạy đồng thời với migration hoặc release lớn.

Không chạy stress test vào production nếu chưa có phê duyệt, cửa sổ thử nghiệm và cơ chế dừng an toàn. Một bài test có thể tạo chi phí provider thật hoặc ảnh hưởng tenant khác dù endpoint chỉ đọc.

## 6. Ví dụ load test bằng k6

Ví dụ dưới đây mô phỏng một endpoint xem trước báo cáo bằng open model với tốc độ 10 request/giây trong 5 phút. Token và base URL được truyền qua biến môi trường, không ghi bí mật vào source code.

```javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    report_preview: {
      executor: 'constant-arrival-rate',
      rate: 10,
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 20,
      maxVUs: 80,
    },
  },
  thresholds: {
    'http_req_duration{endpoint:report-preview}': [
      'p(95)<800',
      'p(99)<2000',
    ],
    'http_req_failed': ['rate<0.01'],
    'checks': ['rate>0.99'],
  },
};

export default function () {
  const response = http.get(
    `${__ENV.BASE_URL}/api/reports/preview?period=last-30-days`,
    {
      headers: {
        Authorization: `Bearer ${__ENV.ACCESS_TOKEN}`,
      },
      tags: { endpoint: 'report-preview' },
      timeout: '10s',
    },
  );

  check(response, {
    'status is 200': (r) => r.status === 200,
    'response is JSON': (r) =>
      (r.headers['Content-Type'] || '').includes('application/json'),
  });
}
```

Chạy trong môi trường đã chuẩn bị, ví dụ:

```bash
BASE_URL=https://load-test.example.test \
ACCESS_TOKEN="$LOAD_TEST_ACCESS_TOKEN" \
k6 run report-preview.js
```

Đây là ví dụ kịch bản, không phải tải mục tiêu áp dụng cho mọi hệ thống. `preAllocatedVUs` và `maxVUs` cần đủ để tạo arrival rate mong muốn; nếu thiếu VU, k6 có thể không phát đủ request và kết quả phải được đọc cùng metric dropped iterations. Hãy bắt đầu ở tốc độ thấp, tăng theo từng bước và kiểm tra giới hạn dừng.

Để kiểm tra tenant fairness, chuẩn bị nhiều access token/tenant thử nghiệm và phân phối request giữa các tenant. Không dùng một tenant duy nhất nếu production có nhiều tenant với quy mô khác nhau. Cũng nên có kịch bản payload nhỏ, trung bình và lớn theo giới hạn contract.

## 7. Đo cả response và tài nguyên phía sau

Client load generator chỉ cho biết những gì client quan sát. Nó không cho biết database scan bao nhiêu dòng, queue tăng bao nhiêu hoặc provider tính phí bao nhiêu. Cần kết hợp metric, trace và log phía server.

| Nhóm đo | Metric nên theo dõi |
|---|---|
| API | Request rate, accepted/rejected rate, p50/p95/p99, status code, timeout |
| Application | CPU, heap, allocation, GC pause, thread pool, worker utilization |
| Database | Query latency, rows scanned/returned, connection usage, lock wait, IOPS, temp spill |
| Cache | Hit ratio, miss rate, eviction, memory và key cardinality |
| Queue | Queue depth, age of oldest message, enqueue/dequeue rate, retry và dead-letter |
| Dependency | Request count, latency, error, quota usage và phí theo provider |
| Network/storage | Egress bytes, storage read/write, temporary file và file size |
| Tenant fairness | Accepted work, rejected work, concurrency và cost theo tenant |

Dùng distributed tracing để tìm đoạn xử lý chiếm phần lớn latency/cost. Một endpoint có thể trả chậm do database, nhưng cũng có thể do chờ một service ngoài hoặc retry nhiều lần. Correlation ID cần đi qua các service và background job để kết nối thời gian xử lý với chi phí.

Metric nên có nhãn tenant ở dạng an toàn và có cardinality được kiểm soát. Không tạo label cho mọi user ID hoặc object ID trên metric hệ thống vì cardinality cao có thể tự làm tăng chi phí monitoring. Với tenant lớn hoặc điều tra riêng, dùng log/audit có kiểm soát hoặc bảng tổng hợp thay vì đưa mọi ID vào metric label.

## 8. Đo cost per request, job và tenant

Chi phí của một endpoint có thể đến từ nhiều thành phần. Mô hình đơn giản:

\[
C_{total}=\sum_i Q_i\times P_i
\]

Trong đó `Q_i` là lượng tài nguyên loại `i` đã sử dụng và `P_i` là đơn giá hoặc hệ số quy đổi tương ứng. Tài nguyên có thể là CPU-second, GB-second, database I/O, storage byte-month, network egress, số lần gọi provider hoặc đơn vị compute chuyên dụng.

Một số cách nhìn hữu ích:

- **Cost per request:** tổng chi phí phân bổ cho endpoint chia cho số request hoàn tất thành công.
- **Cost per job:** chi phí thực tế của một báo cáo/export, gồm thời gian queue, worker, database và storage.
- **Cost per tenant:** chi phí tài nguyên được quy cho tenant trong một khoảng thời gian.
- **Marginal cost:** chi phí tăng thêm khi nhận thêm một request/job, hữu ích để đặt quota.
- **Fixed/shared cost:** chi phí nền hoặc hạ tầng dùng chung; cần quy tắc phân bổ rõ nếu muốn so sánh tenant.

Không nên lấy tổng hóa đơn cloud chia cho tổng request rồi coi đó là chi phí chính xác của từng endpoint. Hạ tầng dùng chung, autoscaling, cache và batch processing khiến việc phân bổ chỉ là ước tính nếu không có instrumentation. Hãy ghi rõ phương pháp phân bổ và dùng cùng một phương pháp khi so sánh trước/sau tối ưu.

Ví dụ, một report job dùng 12 CPU-second, 0,5 GB-hour temporary storage, 3 database read-unit và 2 provider calls. Có thể quy đổi từng loại sang cost unit nội bộ để so sánh với budget. Nếu provider có phí theo request, ghi nhận số lần gọi và model/operation tương ứng. Không hardcode đơn giá cloud vào logic nghiệp vụ; lấy đơn giá từ billing/configuration hoặc dùng đơn vị nội bộ ổn định.

## 9. Thiết kế cost budget theo endpoint

Mỗi endpoint đắt nên có ngân sách công việc tối đa. Budget có thể bao gồm:

- Số bản ghi tối đa được đọc hoặc xuất.
- Khoảng thời gian tối đa của báo cáo.
- Số filter, sort key và điều kiện lồng nhau tối đa.
- Kích thước request, file upload và response tối đa.
- Số item tối đa trong batch.
- Số dependency call tối đa cho một request.
- Thời gian xử lý và deadline tổng.
- Số job đang chạy và số job đang chờ trên mỗi tenant.
- Cost unit tối đa cho một request/job và quota theo thời gian.

Ví dụ guardrail cho endpoint export:

| Giới hạn | Giá trị minh họa | Lý do |
|---|---:|---|
| Khoảng thời gian tối đa | 90 ngày | Hạn chế scan dữ liệu quá rộng |
| Số dòng tối đa | 100.000 | Giới hạn database và file output |
| Kích thước file tối đa | 100 MB | Hạn chế storage và egress |
| Job đang chạy mỗi tenant | 2 | Ngăn một tenant chiếm worker pool |
| Job đang chờ mỗi tenant | 5 | Giới hạn queue backlog |
| Deadline xử lý | 10 phút | Ngăn worker bị giữ vô hạn |
| Cost unit mỗi job | 50 | Bảo vệ ngân sách tài nguyên |

Các con số chỉ để minh họa cách viết policy. Giá trị thật phải dựa trên benchmark, nhu cầu nghiệp vụ, dung lượng dữ liệu và hạ tầng. Giới hạn cần được công bố trong contract hoặc tài liệu API để client có thể chia nhỏ yêu cầu.

## 10. Rate limit theo request cost, không chỉ theo số request

Rate limit kiểu “100 request/phút” coi mọi request có giá như nhau. Nhưng một request đọc một object và một request export 100.000 dòng có mức tiêu hao rất khác nhau.

Có thể gán cost weight theo loại thao tác:

| Operation | Cost weight minh họa |
|---|---:|
| Đọc chi tiết một object | 1 |
| Search có filter và page size giới hạn | 3 |
| Report preview | 8 |
| Export dữ liệu | 30 |
| Bulk operation lớn | 40 |

Token bucket hoặc quota theo cost unit có thể giới hạn tổng công việc trong một cửa sổ thời gian. Ví dụ tenant có budget 500 cost unit/phút; request export tiêu thụ 30 unit, request đọc chi tiết tiêu thụ 1 unit. Khi hết budget, server trả `429 Too Many Requests` và có thể cung cấp `Retry-After` nếu biết thời điểm quota được bổ sung.

Một policy thực tế thường có nhiều tầng:

- Per principal hoặc API key để giới hạn một caller.
- Per tenant để bảo đảm fairness giữa các tenant.
- Per endpoint/operation để bảo vệ chức năng đắt.
- Global limit để bảo vệ capacity của service và dependency.
- Per dependency/provider quota để tránh vượt giới hạn hoặc phí của bên ngoài.

Không dùng IP làm khóa duy nhất: nhiều người dùng có thể chung NAT, còn attacker có thể đổi IP. Với API key hoặc principal, kết hợp tenant và loại operation. Khi tenant vượt quota, không để một caller khác trong cùng tenant né giới hạn bằng cách dùng credential thứ hai nếu quota nghiệp vụ áp dụng ở cấp tenant.

## 11. Giới hạn concurrency và dùng queue có backpressure

Rate limit kiểm soát tốc độ nhận request; concurrency limit kiểm soát số công việc đang chạy cùng lúc. Cả hai đều cần thiết. Nếu một endpoint xử lý 30 giây, chỉ 5 request/giây cũng có thể tích tụ nhiều công việc đang chạy.

Với tác vụ nặng như export, mô hình bất đồng bộ thường phù hợp:

1. API xác thực caller, kiểm tra permission và object/tenant scope.
2. Server validate kích thước, phạm vi và cost estimate.
3. Kiểm tra quota, số job đang chạy và queue capacity.
4. Tạo job với idempotency key và trạng thái `QUEUED`.
5. Trả `202 Accepted` cùng job ID.
6. Worker lấy job theo concurrency limit và kiểm tra lại tenant/lifecycle trước khi đọc dữ liệu.
7. Khi hoàn tất, lưu kết quả có TTL và cho phép tải qua endpoint kiểm tra authorization.

Queue phải có giới hạn độ dài, tuổi message, số retry và dead-letter policy. Queue không giới hạn chỉ chuyển overload từ API sang worker và storage. Khi queue đầy, server nên từ chối công việc mới có kiểm soát thay vì tiếp tục nhận rồi để backlog tăng vô hạn.

Ví dụ pseudocode:

```java
ExportResponse requestExport(Principal principal, ExportRequest request) {
    authorization.require(principal, "reports:export");
    ExportScope scope = scopeResolver.requireAllowedScope(principal, request);
    ExportCost cost = estimator.estimate(scope);

    quota.requireAvailable(principal.tenantId(), cost);
    concurrency.requireSlot(principal.tenantId(), "report-export");
    queueCapacity.requireAvailable("report-export");

    ExportJob job = jobService.createIdempotently(
            principal, scope, cost);
    return ExportResponse.accepted(job.id());
}
```

Đây là pseudocode. Việc reserve quota/concurrency slot và tạo job cần xử lý nguyên tử hoặc có cơ chế bù khi enqueue thất bại. Không giữ slot vĩnh viễn nếu client bỏ polling; slot phải được giải phóng khi job kết thúc, timeout hoặc bị hủy.

## 12. Kiểm soát query và kích thước công việc

Endpoint đắt thường cho phép caller chọn nhiều điều kiện. Server cần giới hạn chúng trước khi tạo truy vấn hoặc công việc:

- Bắt buộc giới hạn page size và số trang tối đa; không hỗ trợ `pageSize=all`.
- Giới hạn khoảng ngày, số filter, số sort key và loại phép tìm kiếm.
- Không cho client tự chọn SQL expression, field tùy ý hoặc script query.
- Đặt statement timeout và query deadline; hủy query khi caller đã hủy request nếu framework hỗ trợ.
- Dùng index phù hợp và kiểm tra query plan trên dữ liệu gần production.
- Tránh N+1 query và truy vấn không có tenant filter.
- Giới hạn số ID và độ sâu object lồng nhau trong batch.
- Giới hạn số dòng export và kích thước file sau khi tạo.

Validation cần xảy ra trước khi service tiêu tốn tài nguyên lớn. Tuy nhiên, đừng chỉ tin `limit` do client gửi; server áp dụng giới hạn tối đa bất kể giá trị request. Nếu request vượt giới hạn, trả lỗi rõ ràng như `400` hoặc `422` theo contract và không bắt đầu job.

## 13. Deadline, timeout và retry budget

Một request có thể chờ nhiều dependency. Nếu mỗi dependency có timeout dài và retry độc lập, tổng thời gian/chi phí có thể nhân lên.

Hãy thiết kế:

- **End-to-end deadline:** tổng thời gian tối đa từ lúc nhận request đến lúc hoàn tất hoặc chuyển thành job.
- **Per dependency timeout:** timeout riêng cho database, search, storage và provider.
- **Retry budget:** giới hạn số lần retry và tổng thời gian retry; chỉ retry lỗi tạm thời phù hợp.
- **Exponential backoff và jitter:** tránh nhiều client retry đồng thời theo cùng nhịp.
- **Idempotency:** bảo đảm retry thao tác tạo job, thanh toán hoặc bulk action không tạo side effect trùng.
- **Cancellation propagation:** khi request/job bị hủy, dừng công việc downstream nếu có thể.

Không retry `400`, `401`, `403` hoặc `429` ngay lập tức. Với `429`, client phải tôn trọng `Retry-After` hoặc backoff. Với `5xx`, retry chỉ khi thao tác an toàn và còn deadline. Retry ở nhiều tầng (client, gateway, service, SDK) có thể khuếch đại tải; cần xác định một ngân sách retry tổng.

## 14. Cache và tái sử dụng kết quả có kiểm soát

Cache có thể giảm chi phí cho report/search lặp lại, nhưng cache sai có thể làm rò rỉ dữ liệu giữa tenant hoặc trả kết quả sau khi quyền đã thay đổi.

Các nguyên tắc:

- Cache key phải bao gồm tenant và mọi tham số ảnh hưởng đến kết quả; nếu response phụ thuộc principal/permission, cần phân vùng theo security context phù hợp.
- Chỉ cache kết quả có thể tái sử dụng an toàn; không dùng key chung cho dữ liệu riêng tư.
- Giới hạn TTL, kích thước object và tổng dung lượng cache.
- Invalidate khi dữ liệu, quyền hoặc tenant lifecycle thay đổi.
- Chống cache stampede bằng request coalescing, single-flight hoặc refresh có giới hạn.
- Không cache lỗi authorization như một quyết định allow lâu dài.
- Đo cache hit ratio cùng cost; cache hit cao nhưng invalidation sai vẫn là lỗi bảo mật.

Với report nặng, có thể cache kết quả theo tenant, bộ lọc chuẩn hóa và data version. Khi caller yêu cầu lại, server vẫn kiểm tra authorization trước khi trả kết quả cache.

## 15. Tenant fairness và ngăn noisy neighbor

Trong hệ thống multi-tenant, một tenant có dữ liệu lớn hoặc gửi nhiều job có thể chiếm worker, connection pool và cache của tenant khác. Rate limit global không đủ để bảo đảm công bằng.

Các biện pháp thường dùng:

- Quota riêng theo tenant và loại operation.
- Giới hạn số job chạy đồng thời của mỗi tenant.
- Weighted fair queue hoặc scheduler để một tenant không chiếm toàn bộ worker.
- Reserved capacity hoặc priority class cho thao tác quan trọng.
- Pool hoặc semaphore riêng cho dependency dễ bị một tenant làm cạn.
- Theo dõi cost, latency, queue age và reject rate theo tenant.
- Giới hạn burst nhưng cho phép mức sử dụng ổn định phù hợp gói dịch vụ.

Không để tenant tự khai `tenantId` để chọn quota. Tenant key phải đến từ principal đã xác minh. Nếu có tenant parent/child hoặc delegated client, cần quy định quota áp dụng ở cấp nào để không thể né giới hạn bằng cách tạo nhiều sub-account.

## 16. Load shedding và graceful degradation

Khi service gần bão hòa, tiếp tục nhận mọi request có thể khiến latency tăng, timeout lan rộng và retry tạo thêm tải. Load shedding từ chối công việc mới trước khi toàn hệ thống mất khả năng phục vụ.

Có thể áp dụng:

- Từ chối sớm request vượt quota bằng `429`.
- Từ chối tạm thời request khi service hoặc queue đã quá tải bằng `503 Service Unavailable` và `Retry-After` nếu có thể ước lượng.
- Tắt tạm tính năng phụ tốn tài nguyên, ví dụ export định dạng hiếm hoặc thống kê không thiết yếu.
- Trả dữ liệu cache đã được xác minh còn phù hợp nếu nghiệp vụ cho phép.
- Giảm mức chi tiết hoặc kích thước kết quả theo quy tắc công bố, không âm thầm bỏ qua điều kiện lọc bảo mật.
- Dùng circuit breaker để ngừng gọi dependency đang lỗi và tránh retry storm.
- Dùng bulkhead để lỗi ở endpoint export không chiếm hết thread/connection của API đăng nhập hoặc thao tác thiết yếu.

Graceful degradation không được bỏ qua authentication, authorization, tenant filter hoặc validation. Khi quá tải, server có thể từ chối; không được trả dữ liệu rộng hơn hoặc dùng quyền mặc định để duy trì response.

## 17. Cost guardrail ở nhiều lớp

Không đặt mọi giới hạn trong một middleware duy nhất. Một số kiểm soát cần thực thi ở các lớp khác nhau:

| Lớp | Guardrail |
|---|---|
| API gateway | Rate limit, body size, request timeout, burst limit |
| Application | Permission, per-tenant quota, cost estimate, max page/range/batch |
| Worker scheduler | Concurrency, queue capacity, fairness, job deadline |
| Database | Statement timeout, connection pool, query plan, row limit và tenant filter |
| Cache | TTL, memory budget, key namespace và stampede control |
| External provider | Quota, timeout, retry budget, circuit breaker và spend limit |
| Storage/network | File size, retention, egress budget và signed URL TTL |
| Operations | Budget alert, anomaly detection, kill switch và runbook |

Gateway có thể chặn burst trước khi vào service, nhưng không biết chính xác số dòng hoặc số lần provider call mà một request sẽ tạo. Application cần ước lượng cost dựa trên tham số và áp dụng quota nghiệp vụ. Database và worker vẫn cần giới hạn riêng để bảo vệ khi application logic có lỗi.

## 18. Theo dõi ngân sách và cảnh báo chi phí

Cost guardrail cần có quan sát để biết nó đang bảo vệ hệ thống hay chặn nhầm hoạt động hợp lệ. Theo dõi:

- Cost unit theo endpoint, tenant, client và loại job.
- Số request/job được nhận, từ chối, hủy và hoàn tất.
- Ước lượng cost trước khi chạy so với cost thực tế.
- Tỷ lệ job vượt thời gian hoặc budget.
- Provider spend, quota usage và egress theo thời gian.
- Queue age, worker saturation và retry count.
- Tỷ lệ `429`/`503` theo tenant và operation.

Đặt alert ở nhiều ngưỡng: cảnh báo sớm khi dùng 70% budget, cảnh báo cao khi dùng 90%, và hành động giới hạn khi chạm 100% nếu policy yêu cầu. Các tỷ lệ này chỉ là ví dụ; cần dựa trên tốc độ tiêu thụ, thời gian phản ứng và khả năng tăng budget hợp lệ.

Phân biệt spike hợp lệ do chiến dịch hoặc kỳ báo cáo với hành vi bất thường. Có thể dùng baseline theo giờ/ngày, tenant size và operation mix. Không tự động khóa toàn bộ tenant chỉ vì một metric tăng; policy nên ưu tiên giới hạn operation đắt và giữ khả năng truy cập chức năng thiết yếu.

## 19. Đọc kết quả load test và tìm bottleneck

Khi tải tăng theo từng bước, hãy xem latency, throughput và saturation cùng nhau:

- Nếu throughput tăng tuyến tính và latency ổn định, service còn capacity ở vùng tải đó.
- Nếu throughput gần như không tăng nhưng latency/queue tăng nhanh, một thành phần đã bão hòa.
- Nếu CPU thấp nhưng latency cao, kiểm tra lock wait, connection pool, network hoặc dependency.
- Nếu CPU cao và DB scan lớn, kiểm tra query plan, index, payload và phép tính lặp.
- Nếu `429` tăng nhưng latency của request được nhận vẫn ổn định, guardrail đang giới hạn tải; đánh giá quota có phù hợp SLO và fairness không.
- Nếu `5xx` hoặc timeout tăng cùng retry count, kiểm tra retry amplification và deadline propagation.
- Nếu cost per successful job tăng khi tải tăng, kiểm tra cache miss, contention, duplicate work và autoscaling.

Không chỉ lấy giá trị trung bình. p95/p99 và queue age thường cho thấy người dùng bị ảnh hưởng trước khi average latency thay đổi rõ. Ghi lại cấu hình, phiên bản ứng dụng, dataset, load profile và dependency để so sánh lần chạy.

## 20. Tiêu chí dừng và kế hoạch rollback guardrail

Một guardrail quá chặt có thể làm hỏng chức năng hợp lệ; một guardrail quá lỏng không bảo vệ được capacity. Khi rollout:

1. Đo baseline trước khi bật giới hạn mới.
2. Bật metric/shadow mode nếu có thể để quan sát request nào sẽ bị từ chối.
3. Triển khai giới hạn theo từng endpoint hoặc nhóm tenant.
4. Theo dõi tỷ lệ reject, support issue, latency và cost.
5. Điều chỉnh quota dựa trên dữ liệu và policy gói dịch vụ.
6. Giữ kill switch hoặc cấu hình rollback có kiểm soát; không tắt mọi giới hạn khi có sự cố.

Dừng load test nếu error rate vượt ngưỡng đã thống nhất, dependency sandbox gần quota, queue age vượt giới hạn, CPU/memory chạm ngưỡng an toàn hoặc test bắt đầu ảnh hưởng workload khác. Người vận hành phải biết cách dừng generator và hủy job đã tạo.

## 21. Checklist load test và cost guardrail

- [ ] Endpoint đắt, yếu tố tạo chi phí và dependency đã được xác định.
- [ ] SLO cho latency, throughput, error rate và job completion đã được thống nhất.
- [ ] Workload model phản ánh arrival rate, concurrency, payload, data size và tenant distribution.
- [ ] Có smoke, baseline, load, stress/spike và soak test phù hợp.
- [ ] Môi trường, dữ liệu và provider được cô lập; có ngưỡng dừng an toàn.
- [ ] Metric phía client và server được thu thập, gồm database, queue, cache, network và provider.
- [ ] Có cost model và phương pháp phân bổ cost per request/job/tenant rõ ràng.
- [ ] Có giới hạn page size, date range, batch, payload, rows, file size và dependency calls.
- [ ] Có weighted quota/rate limit, concurrency limit và bounded queue.
- [ ] Retry, timeout, deadline, cancellation và idempotency được kiểm soát.
- [ ] Cache key tách tenant/security context và có invalidation phù hợp.
- [ ] Tenant fairness, noisy-neighbor protection và global capacity được kiểm tra.
- [ ] Load shedding không bỏ qua authentication, authorization hoặc tenant isolation.
- [ ] Có dashboard, alert, kill switch, rollout plan và runbook.
- [ ] Test xác minh cả request được nhận, request bị từ chối và chi phí/side effect thực tế.

## Kết luận

Load test cho biết endpoint đắt hoạt động ra sao khi arrival rate, concurrency, dữ liệu và dependency thay đổi. Cost guardrail giới hạn công việc theo caller, tenant, operation và capacity của hệ thống. Để bảo vệ API hiệu quả, cần đo cả latency lẫn tài nguyên phía sau, đặt budget theo cost thực tế, giới hạn kích thước và phạm vi truy vấn, kiểm soát concurrency/queue/retry, đồng thời bảo đảm fairness giữa tenant. Khi các giới hạn được kiểm thử, quan sát và rollout có kiểm soát, hệ thống có thể từ chối tải vượt ngưỡng sớm mà vẫn giữ chất lượng cho các request hợp lệ.
