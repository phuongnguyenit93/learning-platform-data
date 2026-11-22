# Load testing cho Cloud Run, GKE và ứng dụng dữ liệu

Một API Java hoặc Spring Boot có thể trả lời nhanh khi chỉ có vài người sử dụng, nhưng chậm đáng kể khi hàng trăm request đồng thời truy cập Cloud SQL, Cloud Storage hoặc Pub/Sub. Trên Google Cloud, khả năng mở rộng của Cloud Run và Google Kubernetes Engine (GKE) giúp xử lý tải biến động, nhưng **autoscaling không loại bỏ giới hạn của dependency**. CPU, connection pool, số lượng kết nối database, quota API, retry và hàng đợi đều có thể trở thành nút thắt.

**Load testing** là quá trình tạo lưu lượng đại diện cho hành vi sử dụng dự kiến, đo phản hồi của hệ thống và tìm giới hạn trước khi triển khai hoặc tăng quy mô. Mục đích không chỉ là xác định hệ thống chịu được bao nhiêu request/giây mà còn kiểm chứng độ trễ, tỷ lệ lỗi, hành vi tự mở rộng, khả năng khôi phục, chi phí và tính đúng đắn của dữ liệu.

Bài học này trình bày cách thiết kế kịch bản tải, đo SLI/SLO, sử dụng công cụ như k6, phân tích đặc điểm của Cloud Run và GKE, kiểm thử các ứng dụng có Cloud SQL, Pub/Sub và dịch vụ dữ liệu khác, rồi đưa kết quả vào quy trình phát hành.

## 1. Load testing khác gì các loại kiểm thử khác?

Load testing là một phần của performance testing nhưng không đồng nghĩa với mọi loại kiểm thử hiệu năng.

| Loại kiểm thử | Mục tiêu | Ví dụ |
|---|---|---|
| Unit/integration | Kiểm tra logic và kết nối thành phần | Repository ghi đúng transaction vào PostgreSQL |
| E2E functional | Kiểm tra một hành trình nghiệp vụ hoàn chỉnh | Tạo đơn hàng, phát sự kiện và xác nhận trạng thái |
| Load | Đánh giá hệ thống ở lưu lượng mục tiêu | 200 request/giây trong 15 phút |
| Stress | Tăng tải vượt ngưỡng thiết kế để tìm điểm gãy | Tăng dần cho đến khi p95/5xx vượt ngưỡng |
| Spike | Đánh giá phản ứng trước đột biến ngắn | Lưu lượng tăng gấp nhiều lần trong thời gian ngắn |
| Soak/endurance | Tìm suy giảm do tải kéo dài | Chạy 2 giờ ở lưu lượng ổn định để phát hiện memory leak |
| Capacity | Ước lượng tài nguyên và chi phí cho mức tải | Số instance, Pod, CPU và DB connections cần thiết |
| Resilience/fault | Kiểm tra hành vi khi có lỗi có kiểm soát | Một node mất kết nối trong lúc đang có lưu lượng |

Một bài load test có thể đạt throughput mục tiêu nhưng vẫn thất bại nếu ghi trùng đơn hàng hoặc làm đầy hàng đợi. Vì vậy, phải theo dõi cả **hiệu năng** và **tính đúng đắn của kết quả nghiệp vụ**.

### Cần chọn đúng đơn vị tải

Tùy ứng dụng, tải có thể được biểu diễn bằng:

- Request mỗi giây (RPS) hoặc transaction mỗi giây (TPS).
- Số virtual users (VU) đồng thời.
- Message mỗi giây qua Pub/Sub.
- Số truy vấn database mỗi giây và số kết nối.
- Số object/byte được đọc hoặc ghi vào Cloud Storage.
- Số event hoặc byte cần xử lý qua pipeline dữ liệu.

Không thể suy ra đơn giản rằng 100 virtual users tương đương 100 request/giây. Một virtual user có thể gửi một request rồi chờ vài giây, hoặc liên tục phát nhiều request. Cần định nghĩa hành vi và pacing.

## 2. Xây dựng mô hình tải từ hành vi thật

Một load test tốt mô phỏng các hành trình chính của người dùng thay vì chỉ gọi liên tục một endpoint dễ cache.

Ví dụ ứng dụng thương mại có ba luồng:

| Hành trình | Tỷ trọng lưu lượng minh họa | Đặc điểm |
|---|---:|---|
| Đọc danh sách sản phẩm | 65% | Đọc nhiều, có thể cache |
| Xem chi tiết đơn hàng | 25% | Đọc DB, cần kiểm tra quyền |
| Tạo đơn hàng | 10% | Ghi DB, phát event, yêu cầu idempotency |

Nếu mục tiêu 100 request/giây và tỷ trọng trên đúng với hành vi thực, có thể xây kịch bản khoảng 65 request đọc danh sách, 25 request xem đơn và 10 request tạo đơn mỗi giây. Đây chỉ là ví dụ: tỷ trọng, thời gian nghĩ và kích thước payload phải lấy từ dữ liệu vận hành hoặc giả định nghiệp vụ đã ghi rõ.

Cần mô tả:

1. Tỷ lệ request đọc/ghi.
2. Kích thước request và response.
3. Tỷ lệ cache hit/miss.
4. Tỷ lệ authentication thành công và bị từ chối.
5. Kích thước dữ liệu trong database và độ phân bố của key.
6. Thời gian giữa các hành động người dùng (think time).
7. Độ phân bố traffic theo khu vực, giờ cao điểm và client.
8. Tần suất gọi dependency và số retry phát sinh.

Đặc biệt, ứng dụng dữ liệu phải được thử với bộ dữ liệu đủ lớn. Truy vấn trên một bảng có 100 dòng có thể không đại diện cho production có hàng chục triệu dòng và index phân bố khác hẳn.

### Open model và closed model

Có hai cách điều khiển tải phổ biến.

- **Closed model:** duy trì số virtual users cố định. Mỗi user đợi xong request rồi mới gửi request kế tiếp. Khi server chậm, tốc độ tạo request có thể giảm.
- **Open model:** điều khiển tốc độ request/iteration được khởi tạo, ví dụ một số iteration mỗi giây, dù phản hồi của server đang chậm. Phù hợp mô phỏng một luồng request đến từ bên ngoài không tự giảm theo thời gian xử lý.

Đối với API có lượng request đầu vào được đo bằng RPS, arrival-rate thường giúp giữ mức tải mục tiêu rõ ràng hơn. Với hành trình tương tác có think time, VU model có thể phù hợp hơn.

Không nên so sánh hai kết quả nếu cách tạo tải khác nhau mà không chuẩn hóa điều kiện.

## 3. Xác định SLI, SLO và điều kiện đạt

Trước khi viết kịch bản, cần định nghĩa chất lượng được kỳ vọng và các dấu hiệu phải dừng thử nghiệm.

### Chỉ số quan trọng

- **Throughput:** số request hoặc transaction được xử lý thành công mỗi giây.
- **Latency:** thời gian hoàn thành request/operation, nên theo dõi p50, p95 và p99.
- **Error rate:** tỷ lệ lỗi ứng dụng, HTTP 5xx, timeout hoặc operation thất bại.
- **Saturation:** CPU, memory, connection pool, hàng đợi, quota và giới hạn autoscaling.
- **Correctness:** số đơn hàng tạo thành công, bản ghi trùng, message bị mất hoặc sai lệch dữ liệu.
- **Recovery:** thời gian trở về trạng thái bình thường sau spike hoặc khi dừng tải.

Ví dụ một SLO để minh họa:

> Với 150 request/giây trong 15 phút, tối thiểu 99,5% request hợp lệ thành công và p95 latency không vượt 600 ms; không có đơn hàng bị ghi trùng.

Ngưỡng này chỉ là giả định học tập. SLO thật phải đến từ yêu cầu sản phẩm, dữ liệu sản xuất và error budget.

### Đừng dùng trung bình để che đuôi phân phối

Nếu 95% request kết thúc dưới 300 ms nhưng 5% còn lại cần 5 giây, thời gian trung bình có thể trông chấp nhận được trong khi một nhóm người dùng vẫn gặp trải nghiệm tệ. Theo dõi p95/p99 và độ phân bố theo endpoint, trạng thái cache và loại request.

Latency nên được đo ở nhiều lớp:

| Lớp đo | Bao gồm | Câu hỏi |
|---|---|---|
| Client end-to-end | DNS, TLS, network, gateway, server và response | Người dùng thực sự chờ bao lâu? |
| Load balancer/Cloud Run request | Phần request được nền tảng ghi nhận | Chậm ở network ngoài hay trong service? |
| Application timer | Logic và lời gọi dependency trong app | Code nào chậm? |
| Dependency timer | Cloud SQL, Pub/Sub, Storage hoặc HTTP service khác | Nút thắt nằm ở đâu? |
| Queue latency | Thời gian chờ để xử lý message | Event có được xử lý kịp hạn không? |

### Hiểu throughput và concurrency

Một xấp xỉ hữu ích theo Little's Law trong trạng thái ổn định:

\[
L \approx \lambda W
\]

Trong đó `L` là số công việc đang xử lý trung bình, `\lambda` là số request hoàn thành mỗi giây và `W` là thời gian trung bình mỗi request (giây). Ví dụ, với 200 request/giây và 0,25 giây mỗi request, số request đang xử lý trung bình có thể gần 50.

Đây chỉ là quan hệ trung bình khi hệ thống ổn định; nó không nói rằng cứ cấu hình 50 concurrency là đủ. Burst, p99 latency, retry, kết nối DB và thời gian scale-up có thể cần nhiều capacity hơn.

## 4. Guardrail: phạm vi, phê duyệt và ngân sách

Load test có thể tạo hóa đơn đáng kể và làm cạn quota hoặc ảnh hưởng dịch vụ thật. Cần có guardrail trước khi sinh lưu lượng.

### Môi trường thử nghiệm

Ưu tiên project/namespace/bucket/database được tạo dành riêng cho test. Nếu phải dùng staging chia sẻ, cần:

- Có owner ứng dụng và người vận hành chấp thuận.
- Ghi rõ project, region, endpoint, thời gian và tốc độ tải tối đa.
- Không truy cập dữ liệu khách hàng không được phép.
- Không chạy kịch bản ghi/xóa trên production nếu chưa có kế hoạch được phê duyệt.
- Giới hạn số VU/RPS và thời lượng; có nút dừng được người vận hành kiểm soát.
- Có budget, quota, cảnh báo chi phí và kế hoạch cleanup.
- Dùng danh tính riêng cho load generator với quyền tối thiểu.

Không đặt điều kiện dừng chỉ dựa trên lỗi HTTP. Nếu DB CPU hoặc connection count đã chạm giới hạn nguy hiểm, nên dừng ngay cả khi API vẫn trả HTTP 200.

### Dữ liệu và endpoint an toàn

- Dùng dữ liệu tổng hợp hoặc dữ liệu đã ẩn danh theo chính sách.
- Gắn mọi object, event, record với `runId` để kiểm tra và dọn dẹp.
- Đặt idempotency key cho write operation.
- Tránh kích hoạt email thật, thanh toán, SMS hoặc webhook đối tác khi tạo tải.
- Không gửi access token, session ID hoặc dữ liệu cá nhân vào tags của metrics.
- Giới hạn retention của log/artifact theo chính sách bảo mật.

### Điều kiện dừng mẫu

| Tín hiệu | Ngưỡng hành động minh họa |
|---|---|
| HTTP 5xx vượt ngưỡng | Dừng hoặc giảm tải khi kéo dài hơn cửa sổ đã định |
| p99 latency tăng mạnh | Kiểm tra saturation, tránh tiếp tục stress mù quáng |
| Cloud SQL gần chạm connection limit | Hạ RPS, ngăn pool exhaustion và mất dịch vụ |
| Pub/Sub backlog tăng liên tục | Dừng publish, cho consumer xử lý phần tồn |
| Load generator CPU quá cao | Không dùng kết quả làm kết luận về server |
| Chi phí hoặc quota vượt budget | Dừng thử nghiệm và cleanup |

Ngưỡng cụ thể phải được định nghĩa trong test plan, không chọn một giá trị chung cho mọi hệ thống.

## 5. Kiến trúc một lượt load test

Một thử nghiệm có thể chạy từ runner độc lập (VM, Kubernetes Job hoặc hệ thống load generator chuyên dụng), gọi vào API và thu số liệu từ cả client lẫn Cloud Monitoring.

~~~mermaid
flowchart TD
    A[Test plan and SLO] --> B[Prepare isolated data and environment]
    B --> C[Load generator]
    C --> D[Cloud Run or GKE API]
    D --> E[Cloud SQL and storage]
    D --> F[Pub/Sub]
    F --> G[Async consumers]
    C --> H[Client metrics]
    D --> I[Cloud Monitoring and Logging]
    E --> I
    F --> I
    G --> I
    H --> J[Correlate results by run ID]
    I --> J
    J --> K[Pass fail report and remediation]
~~~

Trước test, lưu trạng thái:

- Commit, container image digest, service revision hoặc Deployment version.
- CPU/memory, concurrency, autoscaling, min/max instances hoặc replica.
- Database tier, số kết nối, query/index và kích thước dataset.
- Quota, region, networking, load balancer và cache.
- Cấu hình generator, region của runner, số VU/RPS và thời gian.

Không đổi nhiều biến trong lúc đo baseline; nếu thay CPU, số replica, cache hoặc pool size cùng lúc thì khó xác định yếu tố tạo ra cải thiện.

## 6. Chọn công cụ tạo tải

| Công cụ | Đặc điểm | Phù hợp |
|---|---|---|
| k6 | Script JavaScript, thresholds, nhiều executor và kết quả dễ tự động hóa | API HTTP/gRPC và quality gate |
| Apache JMeter | Test plan, protocol samplers và hệ sinh thái plugin | HTTP và một số protocol doanh nghiệp |
| Gatling | Mô hình scenario theo code, tích hợp tốt với JVM ecosystem | Kiểm thử HTTP có luồng phức tạp |
| Locust | Scenario Python, mô phỏng hành vi user và distributed workers | Hành trình người dùng tùy chỉnh |
| Benchmark/SDK chuyên biệt | Đo tác vụ database, storage hoặc messaging | Workload không phản ánh tốt bằng HTTP |

Khi ứng dụng xử lý nhiều event bất đồng bộ, không nên chỉ gửi request HTTP rồi dừng. Có thể cần workload generator publish message trực tiếp vào Pub/Sub topic thử nghiệm và một bộ đối chiếu tiến độ consumer.

### Quy tắc chọn runner

- Đặt runner đủ gần workload để đo latency của ứng dụng, hoặc đặt ở vị trí client thật khi cần đo end-to-end.
- Bảo đảm runner có CPU, memory và network đủ cho tải mục tiêu.
- Đừng tạo traffic vô hạn từ một máy nhỏ; khi CPU runner đầy, số đo latency có thể sai.
- Nếu dùng nhiều runner, đồng bộ thời gian và tổng hợp kết quả bằng cùng run ID.
- Tính cả chi phí runner, Cloud NAT, egress, load balancer và dịch vụ đích.

Bản thân Cloud Run cũng có thể chạy job phát tải trong phạm vi kiểm soát, nhưng phải xem giới hạn thời gian, concurrency, quotas và chi phí. Đặt generator trên môi trường khác không có nghĩa là chi phí mạng và dịch vụ đích biến mất.

## 7. Kịch bản k6 cho một API chỉ đọc

Ví dụ dưới đây tạo 20 iteration mỗi giây trong 5 phút đến endpoint đọc không gây side effect. Trước khi chạy, phải thay `BASE_URL` bằng endpoint của môi trường thử nghiệm và bảo đảm endpoint được phép test.

~~~javascript
import http from 'k6/http';
import { check } from 'k6';

export const options = {
  scenarios: {
    steady_read: {
      executor: 'constant-arrival-rate',
      rate: 20,
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 20,
      maxVUs: 100,
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<600'],
    checks: ['rate>0.99'],
  },
};

export default function () {
  const baseUrl = __ENV.BASE_URL;
  if (!baseUrl) {
    throw new Error('BASE_URL must point to an approved test service');
  }

  const response = http.get(baseUrl + '/health/ready', {
    timeout: '10s',
    tags: { operation: 'readiness' },
  });

  check(response, {
    'readiness returns 200': (r) => r.status === 200,
  });
}
~~~

Chạy:

~~~bash
k6 run --env BASE_URL="https://YOUR-STAGING-SERVICE-URL" load-read.js
~~~

Điểm cần hiểu:

- `constant-arrival-rate` điều khiển số **iteration được bắt đầu mỗi giây**; mỗi iteration trong ví dụ gửi đúng một request nên mới gần tương ứng với RPS.
- `preAllocatedVUs` là số VU chuẩn bị sẵn; `maxVUs` cho phép mở rộng số VU khi iteration chạy lâu hơn.
- `http_req_failed` đo tỷ lệ request lỗi theo tiêu chí mà k6 áp dụng; nên bổ sung assertion nghiệp vụ.
- Threshold có thể làm k6 trả exit code thất bại để pipeline chặn promotion.
- `/health/ready` thường nhẹ hơn hành trình nghiệp vụ thật; dùng nó để học cách tạo tải, **không dùng nó để kết luận capacity của toàn ứng dụng**.

### Authentication khi test Cloud Run private service

Nếu Cloud Run yêu cầu xác thực, test runner phải lấy **ID token có audience đúng** bằng workload identity được ủy quyền. Cấu hình token dưới dạng secret runtime hoặc biến môi trường được bảo vệ, không ghi token cứng vào script.

Ví dụ dùng token đã được cấp cho runner:

~~~javascript
const response = http.get(__ENV.BASE_URL + '/api/orders/demo', {
  headers: {
    Authorization: 'Bearer ' + __ENV.ID_TOKEN,
  },
  tags: { operation: 'get_order' },
});
~~~

Đây là đoạn trích để minh họa header, không phải một script k6 hoàn chỉnh. ID token có thời hạn ngắn: bài test kéo dài cần cơ chế refresh hoặc cấp lại token an toàn. Nếu muốn đo user-authentication thực, không được thay thế toàn bộ yêu cầu bằng một token đặc quyền duy nhất.

## 8. Thiết kế các giai đoạn tải

Một bài load test thường có bốn giai đoạn:

1. **Warm-up:** sinh tải nhỏ để ổn định runtime, JIT, cache và connection pool.
2. **Ramp-up:** tăng tải theo bước để quan sát điểm mà latency hoặc resource tăng mạnh.
3. **Steady-state:** giữ tải mục tiêu đủ lâu để đo p95/p99, throughput và error rate.
4. **Ramp-down/recovery:** hạ tải, đo thời gian autoscaling, queue và hệ thống trở lại bình thường.

Ví dụ lịch thử nghiệm:

| Giai đoạn | Tải mục tiêu minh họa | Thời gian | Mục đích |
|---|---:|---:|---|
| Warm-up | 10 RPS | 3 phút | Làm nóng service và dependency |
| Ramp-up 1 | 30 RPS | 5 phút | Kiểm tra phản ứng ban đầu |
| Ramp-up 2 | 60 RPS | 5 phút | Quan sát autoscaling |
| Steady | 80 RPS | 15 phút | So sánh với SLO |
| Spike | 150 RPS | 1 phút | Kiểm tra burst và queue |
| Recovery | 10 RPS | 5 phút | Kiểm tra hệ thống trở lại ổn định |

Không gộp spike và steady-state thành một con số trung bình. Kết quả của 1 phút spike có thể bị ảnh hưởng mạnh bởi cold start và bursty traffic, còn steady-state phản ánh khả năng chịu tải lâu hơn.

### Ví dụ k6 ramp-up theo số VU

~~~javascript
import http from 'k6/http';

export const options = {
  stages: [
    { duration: '2m', target: 10 },
    { duration: '5m', target: 30 },
    { duration: '5m', target: 60 },
    { duration: '5m', target: 0 },
  ],
  thresholds: {
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<600'],
  },
};

export default function () {
  http.get(__ENV.BASE_URL + '/catalog', { timeout: '10s' });
}
~~~

Kịch bản này điều khiển **VU**, không bảo đảm 10/30/60 RPS. Để test chính xác arrival rate, dùng `ramping-arrival-rate` và định nghĩa stages theo iteration rate. Chọn executor phù hợp với câu hỏi cần trả lời.

### Kiểm soát coordinated omission

Khi dùng closed model, server chậm làm user ảo gửi ít request hơn và có thể khiến tải giảm ngay lúc hệ thống đang quá tải. Kết quả latency có nguy cơ đẹp giả tạo. Với traffic đến độc lập, arrival-rate giúp giảm hiện tượng này, nhưng vẫn phải theo dõi `dropped_iterations` của k6: nếu runner không đủ VU để bắt đầu iteration, tải thực tế thấp hơn mục tiêu.

## 9. Load testing Cloud Run

Cloud Run tự động điều chỉnh số instance theo request và cấu hình của service. Việc tăng instance có thể giúp xử lý thêm request, nhưng phụ thuộc vào concurrency, CPU, memory, startup time, max instances và giới hạn downstream.

### Những tham số cần ghi lại

| Tham số | Tác động |
|---|---|
| Request concurrency | Số request có thể được xử lý đồng thời trên mỗi instance |
| CPU và memory | Năng lực tính toán và xử lý của từng instance |
| Min instances | Giảm một phần cold-start latency bằng cách duy trì instance sẵn sàng |
| Max instances | Giới hạn quy mô thông thường, chi phí và tải lên dependency |
| Request timeout | Thời gian tối đa request được phép chạy |
| Startup behavior | Thời gian để container sẵn sàng phục vụ |
| Region và ingress | Độ trễ mạng, cách traffic đi vào service |
| CPU allocation | Ảnh hưởng background processing và billing theo cấu hình |

Ví dụ xem cấu hình Cloud Run trước test:

~~~bash
gcloud run services describe orders-api \
  --region="asia-southeast1" \
  --project="PROJECT_ID" \
  --format=yaml
~~~

Đây là lệnh đọc trạng thái. Không chỉnh max instances hoặc concurrency giữa các vòng chạy khi chưa ghi một baseline riêng cho mỗi cấu hình.

### Per-instance concurrency và JDBC pool

Một Cloud Run instance có thể xử lý nhiều HTTP request đồng thời. Nếu Java application dùng HikariCP pool 10 connection/instance, khi service scale lên 30 instance có thể tạo nhu cầu tối đa gần 300 connections, chưa kể service hoặc job khác.

Đây chỉ là phép tính **giới hạn cấu hình**, không có nghĩa mọi connection sẽ luôn được mở. Nhưng nó cho thấy autoscaling service có thể đẩy Cloud SQL đến gần connection limit dù CPU của Cloud Run vẫn còn dư.

Ví dụ ước lượng:

\[
\text{PotentialConnections} =
  \text{Instances} \times \text{MaxPoolPerInstance}
\]

Khi đánh giá, cũng phải tính admin connections, migrations, read replicas và các workload chia sẻ database.

### Quan sát khi tăng tải

- Service request count và request latency trong Cloud Monitoring.
- Số instance đang chạy, cold start hoặc startup delay.
- CPU/memory utilization, concurrency và throttling.
- HTTP 429, 503, 504 và client timeouts theo ngữ cảnh.
- Cloud SQL connection count, query latency và DB CPU.
- Log, trace và các lỗi startup, connection pool timeout.

Không quy mọi lỗi 429/503 cho autoscaling; chúng có thể do application rate limiter, Cloud Armor, quota hoặc service khác. Phân tách lỗi theo lớp nhận request.

### Điều kiện vượt qua

Cloud Run đạt kịch bản khi throughput thành công đáp ứng mục tiêu, p95/p99 và error rate trong SLO, không có sai lệch nghiệp vụ và autoscaling không làm cạn downstream. Cần kiểm tra chi phí trên mỗi request thành công, không chỉ nhìn mức RPS tối đa.

## 10. Load testing GKE

Trên GKE, capacity phụ thuộc cấu hình Pod, số replica, node pool, resource requests/limits, Horizontal Pod Autoscaler (HPA), cluster autoscaler và khả năng của dependency.

### Các lớp mở rộng cần quan sát

1. **Application:** JVM threads, connection pool, GC, cache và hiệu quả xử lý request.
2. **Pod:** CPU/memory utilization, restart, readiness, OOMKilled và throttling.
3. **HPA:** current/desired replicas, metric CPU hoặc custom metrics dùng để scale.
4. **Scheduler:** Pod Pending do thiếu CPU, memory, quota hoặc topology constraints.
5. **Cluster autoscaler:** node mới được thêm theo điều kiện và giới hạn cấu hình.
6. **Network:** Service, ingress/load balancer, DNS và policy.
7. **Dependency:** Cloud SQL, Pub/Sub, Storage hoặc external API.

Có thể đọc trạng thái trước và trong lúc test:

~~~bash
kubectl get deploy,hpa -n load-lab
kubectl get pods -n load-lab -o wide
kubectl describe hpa orders-api -n load-lab
kubectl get nodes
~~~

Lệnh `kubectl top pods` hoặc `kubectl top nodes` cần metrics API tương ứng đang hoạt động và cung cấp ảnh chụp ngắn hạn, không thay thế dashboard theo thời gian.

### HPA và Pod startup

Một HPA có thể tăng số replica khi CPU cao, nhưng:

- CPU requests quá thấp hoặc không phù hợp khiến tín hiệu scale khó diễn giải.
- Pod mới cần thời gian pull image, startup, readiness và kết nối dependency.
- HPA không tự tạo node nếu cluster hết tài nguyên.
- Cluster autoscaler có thể bị giới hạn bởi quota, capacity region/zone hoặc min/max nodes.
- Một số workload có metric CPU thấp nhưng vẫn nghẽn do DB, I/O, lock hoặc network.

Nếu CPU dưới ngưỡng mà p99 vẫn cao, cần kiểm tra DB pool, queue và thread starvation trước khi chỉ tăng replicas.

### Readiness và traffic

Trong load test, kiểm tra Pod mới chỉ nhận traffic khi đã Ready. Liveness probe quá nhạy có thể tạo restart loop dưới tải. PodDisruptionBudget hỗ trợ một số trường hợp voluntary disruption, nhưng không tự giải quyết overload hoặc OOM.

### HPA có thể làm tăng áp lực vào database

Ví dụ mỗi Pod có HikariCP pool 12 connection và HPA tối đa 25 replica thì số kết nối tiềm năng có thể đạt 300. HPA bảo vệ service khỏi quá tải CPU nhưng có thể làm tăng số kết nối Cloud SQL.

Nên kiểm soát pool size, request concurrency, queue, autoscaling bounds và deadline cùng nhau. Một ứng dụng scale-out quá nhanh có thể tạo **connection storm** và khiến p99 của toàn hệ thống tăng.

## 11. Load testing ứng dụng Java/Spring Boot

Khi API sử dụng Java, các thông số của JVM và framework có thể trở thành nút thắt:

- Thời gian warm-up JIT và class loading.
- Garbage collection pauses và allocation rate.
- Heap/non-heap memory và container memory limit.
- Servlet thread pool hoặc event loop.
- HTTP client connection pool và keep-alive.
- HikariCP max pool size, acquisition timeout và connection lifetime.
- Database transaction duration và lock contention.
- JSON serialization, payload compression và object allocation.
- Retry budget, circuit breaker và timeout giữa các dependency.

### Instrumentation

Micrometer, OpenTelemetry và Cloud Monitoring có thể hỗ trợ đo:

| Metric | Ý nghĩa |
|---|---|
| HTTP server request duration | Độ trễ request ứng dụng |
| JVM heap usage/GC pause | Áp lực bộ nhớ và garbage collection |
| Executor active/queued tasks | Thread pool có đang cạn? |
| HikariCP active/idle/pending connections | Ứng dụng có phải chờ connection DB? |
| DB query duration | Truy vấn nào chậm dưới tải? |
| HTTP client duration | Dependency nào gây chậm? |
| Retry attempts/timeouts | Retry có khuếch đại traffic? |

Phân tách metric theo route template như `/orders/{id}`, không theo raw URL chứa hàng triệu ID. Tránh gắn user ID, request ID hoặc email làm label metrics vì cardinality và rủi ro riêng tư.

### Đối chiếu log và trace

Một request p99 chậm có thể có trace thể hiện:

1. 10 ms đi qua controller.
2. 550 ms chờ lấy JDBC connection.
3. 50 ms chạy query.
4. 20 ms serialization và trả response.

Nếu chỉ nhìn query execution duration, nhóm có thể tưởng database không có vấn đề. Connection acquisition time và pool saturation mới là nút thắt. Phân tích thời gian chờ và thời gian xử lý riêng biệt.

### Không tối ưu từ một con số

Một kết quả p95 cải thiện sau khi đổi CPU có thể bị ảnh hưởng bởi cache ấm hơn, dataset nhỏ hơn hoặc độ trễ mạng khác. Chạy ít nhất vài lượt với cùng dữ liệu và môi trường, ghi độ biến thiên và so sánh trong điều kiện tương đương trước khi quyết định.

## 12. Cloud SQL và kiểm thử tải đọc/ghi

Ứng dụng dùng Cloud SQL cần load test cả lớp API và các hành vi database, vì khả năng scale API không đồng nghĩa khả năng scale transaction.

### Thiết kế dataset

- Dùng schema và migration gần với production.
- Tạo đủ số record và độ phân bố key để index/query planner phản ánh thực tế.
- Giữ tỷ lệ đọc/ghi giống workload mục tiêu.
- Mô phỏng các truy vấn phổ biến và truy vấn đắt tiền.
- Có cleanup an toàn, hoặc tái tạo database lab từ snapshot/dataset tổng hợp.

Không chạy truy vấn ghi đè hoặc xóa diện rộng vào Cloud SQL production để kiểm tra hiệu năng.

### Metric và dấu hiệu nghẽn

| Metric | Khi tăng bất thường cần kiểm tra |
|---|---|
| Database CPU utilization | Query nặng, thiếu index, CPU saturation |
| Memory usage | Buffer/cache pressure |
| Active connections | Pool size, connection leak, autoscaling storm |
| Query latency | SQL plan, lock, index, storage I/O |
| Lock wait/deadlock | Transaction kéo dài hoặc tranh chấp |
| Disk IOPS/latency | I/O saturation và truy vấn scan nhiều |
| Replication lag | Khả năng read replica theo kịp workload |
| JDBC pool pending | App đang chờ lấy connection |

### Thử các tình huống cạnh tranh

Ví dụ hai request cùng tạo order với cùng idempotency key. Test cần xác minh:

- Chỉ một bản ghi chính có hiệu lực.
- Request còn lại trả kết quả hoặc trạng thái conflict theo hợp đồng.
- Không phát hai event nghiệp vụ nếu thiết kế yêu cầu exactly-once effect.
- Không có transaction bị treo khi nhiều request chạy đồng thời.

Nếu ứng dụng dùng Cloud SQL Auth Proxy hoặc JDBC connector, kiểm tra phương thức kết nối đúng với runtime thật. Testcontainers PostgreSQL giúp kiểm tra SQL/transaction, nhưng **không chứng minh** giới hạn kết nối, network, IAM database authentication hoặc tính sẵn sàng của Cloud SQL trong production.

### Không dùng connection count làm SLO duy nhất

Một database có thể chịu nhiều connection đang idle nhưng nghẽn vì lock ở một bảng hoặc query chậm. Phải kết hợp latency, throughput, query plan và transaction behavior.

## 13. Pub/Sub và kiểm thử tải bất đồng bộ

Với kiến trúc sự kiện, throughput của publisher không đủ để kết luận toàn hệ thống xử lý được tải. Consumer có thể chậm hơn producer, làm backlog tăng liên tục.

### Các chỉ số cần đo

- Publish success rate và publish latency.
- Message publish/receive/ack rate.
- `num_undelivered_messages` hoặc backlog tương ứng.
- Tuổi của message chưa ack lâu nhất.
- Consumer processing duration và concurrency.
- Redelivery, retry, nack và dead-letter count.
- Tỷ lệ message tạo ra side effect nghiệp vụ đúng.
- Thời gian từ sự kiện được publish đến khi nghiệp vụ hoàn tất.

### Ví dụ kiểm thử backlog

Giả sử producer publish 500 message/giây trong 10 phút, còn consumers xử lý ổn định 400 message/giây. Nếu tốc độ này duy trì và không có throttling, backlog có thể tăng khoảng 100 message/giây, tương đương 60.000 message sau 10 phút.

Đây là xấp xỉ để giải thích năng lực; kết quả thật phụ thuộc batch, retry, redelivery, subscriber ack và thay đổi tốc độ xử lý.

### Đánh giá khả năng drain backlog

Một thử nghiệm gồm:

1. Ghi số message và tuổi backlog trước test.
2. Publish message tổng hợp có run ID.
3. Theo dõi tốc độ nhận, ack và xử lý nghiệp vụ.
4. Dừng publisher sau khoảng thời gian xác định.
5. Tiếp tục quan sát đến khi backlog trở về baseline.
6. Xác minh tất cả event ID đã được xử lý đúng.
7. Kiểm tra duplicate processing và dead-letter topic.

Không dọn subscription bằng cách xóa toàn bộ backlog khi cần bằng chứng về kết quả thử nghiệm. Dùng subscription riêng hoặc prefix/run ID để cô lập dữ liệu.

### Exactly-once effect và idempotency

Trong nhiều cấu hình Pub/Sub, message có thể được giao lại. Kịch bản tải nên cố tình gửi logical event trùng và kiểm tra consumer không ghi dữ liệu trùng. Tính đúng đắn là **một side effect nghiệp vụ cho mỗi event ID**, không nhất thiết một lần callback trong process.

Đừng tạo load test chỉ dựa trên số message được publish mà không kiểm tra downstream database, vì có thể "thành công" ở publisher nhưng consumer vẫn đang nợ backlog rất lớn.

## 14. Cloud Storage, Firestore và các dịch vụ dữ liệu khác

Mỗi dịch vụ dữ liệu có mô hình throughput, latency, quota và billing khác nhau. Kịch bản cần phản ánh thao tác thực thay vì tái sử dụng chung một bài GET HTTP.

| Dịch vụ | Kịch bản tải | Cần theo dõi |
|---|---|---|
| Cloud Storage | Upload/download nhiều kích thước object, range read, metadata read | Request latency, errors, egress, bytes/s và object generation |
| Firestore | Read/write transaction, query và contention trên document | Latency, errors, quota, index, contention và retry |
| Bigtable | Read/write theo key distribution, scan/range | Node CPU, latency, hot key và throughput |
| Spanner | Transactional reads/writes, query và commit | CPU, transaction abort/retry, latency, locking |
| BigQuery | Truy vấn phân tích với dataset đại diện | Slot usage, query latency, bytes processed và chi phí |
| Cloud SQL | Read/write transactions, connection pooling | DB CPU, lock, I/O, pool wait và query latency |

### Cloud Storage

- Thử object nhỏ và lớn, không chỉ file vài byte.
- Đo throughput byte/s và latency thao tác metadata riêng.
- Với write test, dùng bucket lab và object prefix riêng.
- Khi overwrite, sử dụng generation precondition nếu nghiệp vụ yêu cầu tránh ghi đè.
- Kiểm tra egress nếu client và bucket ở khu vực khác nhau.

### Firestore

- Dùng dữ liệu lab đủ lớn và index gần production.
- Không tạo hotspot do mọi write dồn vào một document/key.
- Đo contention và transaction retries, không chỉ số write thành công.
- Test quota, IAM và network ở dịch vụ thật; emulator không mô phỏng đầy đủ performance, quota hoặc operational semantics.

### BigQuery

BigQuery là hệ thống phân tích dữ liệu, không phải database OLTP cho từng request nhỏ. Load test cần định nghĩa concurrency query, kích thước scan, partition pruning, caching và slot capacity. Kết quả có thể bị ảnh hưởng bởi query cache và dataset size. Ghi rõ có bật cache hay không.

Thử nghiệm BigQuery có thể tạo chi phí lớn theo mô hình billing của project. Dùng limit, budget và dataset test; không chạy unbounded scan trên bảng production chỉ để tìm throughput.

### Bigtable/Spanner

Với Bigtable, phân bố row key ảnh hưởng hotspot và throughput. Với Spanner, transaction contention, abort/retry và placement ảnh hưởng latency. Sử dụng workload generator phù hợp với client library và dữ liệu thật; đo error và retry một cách tường minh.

## 15. Dashboard và phân tích đa lớp trong Cloud Monitoring

Load testing cần kết hợp kết quả từ generator với Cloud Monitoring, Cloud Logging và Cloud Trace. Không chỉ nhìn báo cáo k6 rồi kết luận.

Một dashboard tối thiểu nên có:

| Nhóm | Tín hiệu | Cách đọc |
|---|---|---|
| Client | Offered RPS/iteration rate, achieved RPS, dropped iterations | Generator có thực sự tạo được tải dự kiến? |
| API | Request count, 5xx, p95/p99 latency | Dịch vụ có đạt SLO? |
| Compute | Instance/Pod count, CPU, memory, throttling | Autoscaling và saturation |
| Database | Connections, CPU, query latency, lock wait | Nút thắt dữ liệu |
| Messaging | Publish rate, backlog, oldest unacked age | Consumer có theo kịp? |
| Business | Orders created, duplicate ID, processing completion | Kết quả nghiệp vụ có đúng? |
| Cost | Instance/CPU time, egress, DB cost, API usage | Chi phí trên mỗi request/transaction thành công |

### Gắn kết quả bằng run ID

Lưu run ID trong metadata của test report và, khi phù hợp, ở request header không nhạy cảm:

~~~text
X-Test-Run-Id: load-2026-11-19-a1b2
~~~

Không dùng run ID có giá trị gần như duy nhất làm Prometheus metric label cho mọi request ở production, vì dễ gây cardinality cao. Thay vào đó, có thể lưu run ID trong log/traces được sampling, còn metrics được tổng hợp theo route hoặc operation.

### Đọc timeline

Quan sát các mốc:

- T0: bắt đầu warm-up.
- T1: tăng tải.
- T2: CPU/latency hoặc queue bắt đầu tăng.
- T3: autoscaler bổ sung instance/Pod.
- T4: tải ổn định hoặc hệ thống đạt giới hạn.
- T5: kết thúc test, đo recovery.

Nếu p95 tăng trước khi CPU tăng, có thể cần kiểm tra DB locks, network hoặc connection pool. Nếu API latency giảm sau scale-out nhưng backlog Pub/Sub vẫn tăng, pipeline bất đồng bộ chưa đạt năng lực cần thiết.

## 16. Đánh giá kết quả và xác định điểm gãy

Không nên công bố "chịu được 1.000 RPS" nếu tại mức đó request lỗi nhiều hoặc data consistency không được kiểm chứng. Điểm gãy thường là mức tải mà một tiêu chí dịch vụ bị vi phạm.

Ví dụ báo cáo giả định:

| Tải mục tiêu | RPS thành công | p95 | Lỗi 5xx | Kết luận |
|---|---:|---:|---:|---|
| 25 RPS | 25 | 180 ms | 0% | Đạt |
| 50 RPS | 49,8 | 260 ms | 0,1% | Đạt |
| 100 RPS | 98 | 520 ms | 0,8% | Cần so với SLO |
| 150 RPS | 130 | 1.400 ms | 8% | Không đạt |
| Recovery | Trở về baseline | 240 ms | 0% | Cần xác nhận dữ liệu và queue |

Dữ liệu này chỉ minh họa cách đọc bảng, không đại diện cho năng lực mặc định của Cloud Run/GKE.

### Cách kết luận có trách nhiệm

- Chỉ so sánh những lần chạy có cấu hình và dataset tương đương.
- Tách warm-up, steady-state, spike và recovery.
- Xác định tải **được yêu cầu** và tải **thật sự được gửi**.
- Báo cáo request thành công, không chỉ tổng số request.
- Kiểm tra lỗi theo lớp: 4xx do test data, 5xx, quota, timeout, DB.
- Đối chiếu request latency với database/queue metrics và replica count.
- Kiểm tra không có tác động nghiệp vụ ngoài ý muốn.
- Ghi lại các giới hạn chưa đo được hoặc chưa mô phỏng được.

Khi thử nghiệm bị giới hạn bởi generator, network client hoặc quota thử nghiệm, không được coi đó là giới hạn capacity của ứng dụng.

### Định nghĩa kết quả Pass/Fail

Ví dụ định nghĩa:

- Pass: đạt 80 RPS thành công ở steady-state, p95 không quá 600 ms, error rate không quá 0,5%, không có duplicate order và backlog quay lại baseline trong 5 phút sau test.
- Fail: bất kỳ điều kiện quan trọng nào bị vi phạm.
- Inconclusive: generator không đủ capacity, thay đổi môi trường giữa chừng hoặc thiếu metric để đánh giá.

Mức ngưỡng phải được đội ứng dụng/SRE duyệt trước test. Không thay threshold sau khi nhìn kết quả chỉ để test trở thành Pass.

## 17. Tích hợp load testing vào CI/CD

Một pipeline hợp lý nên kiểm tra theo thứ tự từ rẻ đến đắt:

1. Unit, integration và contract tests.
2. Build image, scan và lưu image digest.
3. Deploy lên staging có cấu hình gần production.
4. Chạy smoke và load test ngắn ở mức an toàn.
5. Kiểm tra SLO, dữ liệu và cost guardrails.
6. Phê duyệt release hoặc chặn promote.
7. Sau production deploy, theo dõi canary và production SLI.

Đối với Cloud Build/Cloud Deploy, test result cần gắn với commit SHA, image digest, target, revision và run ID. Nếu tạo image mới, không tái sử dụng kết quả load test cũ như bằng chứng cho artifact khác.

### Quality gate bằng k6

K6 có thể trả exit code non-zero khi threshold thất bại. Dùng exit code trong CI để chặn promotion. Tuy nhiên, threshold của client không thay thế việc kiểm tra resource saturation, backlog và consistency từ Cloud Monitoring.

Kịch bản tốn kém như stress/soak test dài nên chạy theo lịch hoặc trước các thay đổi hạ tầng quan trọng, không nhất thiết trên mỗi pull request.

### Kiểm soát thay đổi baseline

Sau khi thay:

- Cloud Run concurrency hoặc CPU.
- GKE HPA target hoặc Pod resource requests.
- Cloud SQL tier, index hoặc pool size.
- Region, load balancer hoặc cache.
- Phiên bản JVM hay client SDK.

Hãy chạy lại baseline với dữ liệu và điều kiện tương đương, lưu cấu hình cũ/mới và so sánh p95, throughput, error rate và chi phí.

## 18. Tình huống thực hành: Orders API trên Cloud Run, worker trên GKE

Giả sử hệ thống có:

- Java/Spring Boot `orders-api` trên Cloud Run.
- Cloud SQL for PostgreSQL lưu order và outbox.
- Pub/Sub truyền `OrderCreated`.
- Worker Java trên GKE xác nhận đơn.
- Cloud Storage lưu hóa đơn PDF.
- Cloud Monitoring, Cloud Logging và Cloud Trace dùng để quan sát.

Mục tiêu giả định: xử lý ổn định 80 request tạo đơn/giây trong 15 phút; p95 API dưới 600 ms; tỷ lệ request thất bại dưới 0,5%; đơn hàng không bị tạo trùng; sự kiện tồn không kéo dài quá 5 phút sau khi dừng tải.

### Bước 1 — Chuẩn bị test project

- Tạo môi trường staging có Cloud Run, GKE, Cloud SQL, Pub/Sub và Storage được cô lập.
- Dùng database chứa dataset tổng hợp và index gần production.
- Dùng service account load test có quyền gọi API và đọc kết quả thử nghiệm.
- Không phát event sang consumer production hoặc payment gateway thật.
- Xác nhận budget, quota và thời gian cleanup.
- Ghi image digest, revision, cấu hình Cloud Run/GKE và DB tier.

### Bước 2 — Thiết kế kịch bản

- Sinh request `POST /orders` với payload tổng hợp hợp lệ.
- Mỗi logical order có idempotency key riêng.
- Thêm một nhóm request retry cùng key để xác minh không tạo trùng.
- Theo dõi API response và order ID.
- Sau khi gửi, kiểm tra worker cập nhật trạng thái `CONFIRMED`.
- Kiểm tra hóa đơn trong prefix dành riêng cho run ID.

### Bước 3 — Chạy baseline và tăng tải

1. Chạy smoke test 5 RPS để kiểm tra auth và test data.
2. Warm-up ở 10 RPS.
3. Tăng lên 30 rồi 60 RPS.
4. Giữ 80 RPS trong 15 phút.
5. Nếu được phê duyệt, thử spike ngắn cao hơn baseline.
6. Hạ tải, giữ monitoring để đo backlog drain và recovery.

Không chuyển sang stress test nếu database đã gần giới hạn connections hoặc consumer backlog đang tăng không kiểm soát.

### Bước 4 — Đo đa lớp

- k6: request bắt đầu/thành công, p95/p99, timeout, dropped iterations.
- Cloud Run: concurrency, instances, CPU, memory, 429/5xx.
- Cloud SQL: connections, query latency, lock wait, CPU.
- Pub/Sub: oldest unacked age, backlog và ack rate.
- GKE: consumer replicas, Pod readiness, JVM metrics và HPA.
- Nghiệp vụ: số order duy nhất, event ID trùng, hóa đơn tạo đúng.

### Bước 5 — Phân tích

Ví dụ, API vẫn đáp ứng 80 RPS nhưng backlog tăng liên tục. Điều này nghĩa là HTTP tier đủ capacity trước mắt, **không chứng minh toàn bộ hệ thống đạt yêu cầu**. Cần kiểm tra consumer throughput, transaction lock, JDBC pool hoặc autoscaling GKE.

Nếu Cloud SQL connections tăng cùng số Cloud Run instances, có thể giảm pool per instance, giới hạn concurrency hoặc điều chỉnh cách scale; phải chạy lại test để kiểm chứng.

### Bước 6 — Kết thúc

- Dừng toàn bộ load generator.
- Chờ hàng đợi trở lại baseline hoặc xử lý riêng backlog.
- Kiểm tra tất cả order test và hóa đơn tương ứng.
- Dọn tài nguyên chỉ thuộc run ID.
- Lưu báo cáo, dashboard snapshot, config và kết luận.
- Tạo action item với owner và deadline nếu có nút thắt.

## 19. Troubleshooting khi kết quả không như kỳ vọng

| Triệu chứng | Giả thuyết | Hướng kiểm tra |
|---|---|---|
| RPS thực tế thấp hơn target | Runner không đủ VU/CPU/network | k6 dropped iterations, VU usage, runner CPU |
| p95 cao, CPU app thấp | DB pool wait, lock, network, external API | Trace, HikariCP pending, DB metrics |
| 429 tăng khi spike | Rate limit, capacity/quota hoặc upstream | Cloud Run/load balancer/app logs, quota |
| 503 tăng khi ramp-up | Startup, readiness, backend health hoặc dependency | Cloud Run revision/GKE Pod events |
| Cloud Run instances tăng, DB errors tăng | Connection storm hoặc DB saturation | Pool * instances, Cloud SQL connections |
| GKE HPA tăng nhưng Pod Pending | Cluster thiếu node/quota/topology capacity | Scheduler events, cluster autoscaler |
| Pub/Sub publish ổn, backlog tăng | Consumer throughput thấp | Ack rate, oldest unacked age, GKE worker |
| Test lúc đầu nhanh, sau chậm | Memory leak, pool leak, cache, GC hoặc throttling | JVM, connections, GC, DB |
| Kết quả các lần chạy dao động mạnh | Dataset/caching/runner/region không ổn định | So sánh cấu hình và thứ tự test |
| Test tạo nhiều record trùng | Idempotency hoặc retry chưa đúng | Unique constraint, event ID, transaction logs |

Chỉ thay đổi một nhóm nguyên nhân ở mỗi vòng thử nghiệm nếu có thể. Mỗi lần thay đổi nên tạo baseline mới và so sánh cùng điều kiện.

## 20. Checklist tổ chức load test

### Trước khi chạy

- [ ] Mục tiêu tải, SLI/SLO và điều kiện dừng đã được duyệt.
- [ ] Endpoint, project, region và các tài nguyên test được xác định chính xác.
- [ ] Người vận hành và owner dịch vụ biết lịch chạy.
- [ ] Dữ liệu tổng hợp, run ID và cleanup an toàn đã chuẩn bị.
- [ ] Load generator có capacity và connectivity phù hợp.
- [ ] Có budget/quota và giới hạn tốc độ/thời lượng.
- [ ] Cấu hình Cloud Run/GKE/DB được lưu làm baseline.
- [ ] Dashboard, logs và traces đã sẵn sàng.

### Trong khi chạy

- [ ] Ghi thời điểm bắt đầu mỗi giai đoạn.
- [ ] Đo offered load, achieved throughput, p95/p99 và error rate.
- [ ] Theo dõi CPU/memory, autoscaling, instance/Pod, quota.
- [ ] Theo dõi Cloud SQL pool, transaction và lock.
- [ ] Theo dõi Pub/Sub backlog và xử lý trùng.
- [ ] Xác minh đúng dữ liệu nghiệp vụ, không chỉ HTTP 200.
- [ ] Dừng hoặc hạ tải ngay khi chạm guardrail.

### Sau khi chạy

- [ ] Dừng generator và xác nhận không còn traffic thử nghiệm.
- [ ] Hàng đợi và resource trở lại baseline.
- [ ] Dữ liệu test được đối chiếu và dọn đúng phạm vi.
- [ ] Kết quả được gắn với commit, image digest và cấu hình.
- [ ] Phân biệt Pass, Fail và Inconclusive dựa trên ngưỡng đã định.
- [ ] Báo cáo throughput, latency, errors, saturation và cost.
- [ ] Nút thắt có owner, remediation và kế hoạch chạy lại.

Load testing trên GCP không chỉ là tăng request/giây cho đến khi API trả lỗi. Một thử nghiệm tốt phải thể hiện hành vi người dùng, quan sát đúng các lớp Cloud Run, GKE và dịch vụ dữ liệu, bảo vệ môi trường thử nghiệm, đồng thời xác minh kết quả nghiệp vụ và khả năng phục hồi. Khi SLO, guardrail, kịch bản tải và dashboard được thiết kế nhất quán, nhóm có thể đưa ra quyết định capacity và phát hành dựa trên dữ liệu thay vì giả định.

