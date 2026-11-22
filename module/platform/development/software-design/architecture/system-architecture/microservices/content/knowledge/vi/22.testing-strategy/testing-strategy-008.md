# Kiểm thử tải, cạnh tranh dữ liệu và sức chịu đựng

## 1. Mục tiêu của bài học

Một hệ thống microservices có thể phản hồi nhanh khi chỉ có vài người dùng, nhưng trở nên chậm, sinh lỗi hoặc tạo dữ liệu sai khi nhiều yêu cầu đến cùng lúc. Các lỗi này không phải lúc nào cũng xuất hiện trong unit test: hai request cùng tranh một đơn hàng, nhiều consumer xử lý trùng một sự kiện, retry sau timeout tạo thanh toán kép, connection pool cạn, queue cứ dài dần, hoặc memory leak chỉ lộ rõ sau nhiều giờ.

**Kiểm thử tải (load testing)** đánh giá hành vi của hệ thống trước khối lượng công việc xác định. **Kiểm thử cạnh tranh dữ liệu (concurrency/race testing)** kiểm tra các bất biến nghiệp vụ khi nhiều tác vụ cùng đọc và ghi tài nguyên. **Kiểm thử sức chịu đựng (endurance/soak testing)** kiểm tra khả năng duy trì hiệu năng, độ đúng và trạng thái tài nguyên trong thời gian dài. Trong hệ thống phân tán, cần kết hợp chúng với **stress, spike, recovery và fault-injection testing** để hiểu giới hạn và khả năng phục hồi.

Sau bài này, bạn có thể:

1. Chuyển mục tiêu kinh doanh và SLO thành workload, ngưỡng chấp nhận và kịch bản kiểm thử cụ thể.
2. Phân biệt load, stress, spike, capacity, soak và concurrency testing.
3. Dựng kịch bản tải thực tế đi qua API Gateway, service, database, message broker và đối tác ngoài.
4. Phát hiện race condition, lost update, duplicate side effect, deadlock và sai lệch trạng thái nghiệp vụ.
5. Thiết kế kiểm thử với nhiều thread/process/instance, đồng hồ và đồng bộ hợp lý.
6. Phân tích throughput, tail latency, saturation, queue backlog, memory/connection leaks và recovery.
7. Kết nối kết quả test với quyết định release, capacity planning và runbook vận hành.

Ví dụ xuyên suốt là luồng đặt hàng: `API Gateway → Order Service → Payment Service → Inventory Service → Message Broker → Fulfillment Service`. Tất cả số liệu và ngưỡng trong ví dụ là giả định dùng cho học tập, cần thay bằng baseline và mục tiêu của dự án.

## 2. Bản đồ các loại kiểm thử

| Loại | Câu hỏi cần trả lời | Cách tạo điều kiện | Kết quả quan trọng |
|---|---|---|---|
| **Baseline** | Hệ thống hoạt động thế nào khi gần như không tải? | Ít request, dữ liệu ổn định | Latency cơ sở, số lỗi, số tài nguyên |
| **Load** | Hệ thống đáp ứng tải dự kiến không? | Tải mục tiêu và phân bố nghiệp vụ bình thường | SLO, throughput, error rate, business completion |
| **Stress** | Điểm gãy và cách suy giảm khi quá tải là gì? | Tăng dần đến khi vượt công suất | Knee point, saturation, failure mode, backpressure |
| **Spike** | Hệ thống ứng phó với tăng/giảm đột ngột không? | Tải tăng nhanh rồi trở về bình thường | Thời gian phục hồi, queue, autoscaling, timeout |
| **Capacity** | Chịu được bao nhiêu tải trong giới hạn chi phí/SLO? | Thử nhiều mức tải và số replica | Maximum sustainable throughput, headroom |
| **Soak / Endurance** | Chạy lâu có rò tài nguyên, sai dữ liệu, queue tích lũy không? | Tải đại diện kéo dài nhiều giờ/ngày | Memory slope, connection leaks, backlog, lỗi theo thời gian |
| **Concurrency** | Nhiều tác vụ tranh cùng dữ liệu có giữ bất biến không? | Cố tình va chạm cùng SKU/order/payment | No double charge, no oversell, đúng idempotency |
| **Resilience / Chaos** | Một thành phần lỗi thì toàn luồng ứng xử thế nào? | Delay, packet loss, restart, failover | Graceful degradation, recovery, data integrity |

**Load testing** và **concurrency testing** bổ trợ nhau nhưng không thay thế nhau. Một bài test 10.000 requests/giây dùng 10.000 tài khoản và 10.000 SKU khác nhau có thể không hề tạo va chạm dữ liệu; ngược lại, chỉ cần hai request đồng thời cùng trừ tồn kho còn một sản phẩm cũng có thể bộc lộ race nghiêm trọng.

Soak testing cũng không chỉ là “load test chạy lâu hơn”. Nó cần kiểm đường tăng trưởng của bộ nhớ, file descriptor, connection, retry queue, DLQ, backlog, chi phí và sự đúng đắn của trạng thái tích lũy.

## 3. Bắt đầu bằng câu hỏi nghiệp vụ và bất biến

Trước khi viết script tạo tải, xác định **hệ thống phải giữ điều gì đúng**.

### 3.1. Bất biến trong ví dụ đặt hàng

- Một đơn hàng có `idempotency_key` hợp lệ chỉ được tạo **một** kết quả nghiệp vụ dù client retry nhiều lần.
- Không thể giữ kho vượt số lượng khả dụng: `available >= 0` theo quy tắc inventory đã chọn.
- Không thu tiền hai lần vì retry, network timeout hoặc webhook gửi lặp.
- Một payment attempt chỉ chuyển trạng thái theo các cạnh hợp lệ trong state machine.
- Không giao hai lần cùng một fulfillment item do event redelivery.
- Nếu đã thu tiền nhưng không thể giữ hàng, quy trình phải bù trừ hoặc mở case xử lý; không mất workflow.
- Không truy cập sai tenant dù các request song song.
- Khi dependency quá tải, hệ thống phải giới hạn concurrency và báo lỗi/thời gian chờ theo contract, không suy giảm vô hạn.

### 3.2. SLO và chỉ tiêu kiểm thử

Ví dụ giả định cho luồng checkout:

| Chỉ tiêu | Mục tiêu minh họa | Phạm vi đo |
|---|---|---|
| Checkout API latency P95 | Dưới 800 ms | Request được nhận hợp lệ tại gateway ở tải mục tiêu |
| Checkout API latency P99 | Dưới 1.500 ms | Cùng tập request, gồm slow tail |
| Technical error rate | Dưới 1% | 5xx, timeout hoặc lỗi hạ tầng theo contract |
| Business completion | Ít nhất 99% trong thời hạn đã định | Đếm distinct workflow ID, không đếm HTTP 200 |
| Duplicate charge | 0 | So sánh payment attempt, PSP record và ledger |
| Oversell | 0 | Tồn kho và reservation sau chạy |
| Stuck paid order | 0 vượt hạn phục hồi | Workflow đã thu tiền chưa terminal/compensated |
| Queue recovery | Backlog trở về ngưỡng bình thường trong 10 phút | Sau khi ngắt spike |

Các giá trị chỉ minh họa. Một bài test có thể đạt P95 nhưng vẫn trượt bất biến tài chính; **tính đúng đắn nghiệp vụ là release gate riêng, không bù trừ bằng điểm hiệu năng**.

### 3.3. Hợp đồng thành công

Phải phân biệt:

- `HTTP 200/201`: API đồng bộ trả kết quả theo contract.
- `HTTP 202`: công việc được nhận để xử lý bất đồng bộ; chưa phải hoàn tất nghiệp vụ.
- `OrderCreated`: đơn đã được ghi nhận.
- `PaymentAuthorized`: thanh toán đã được authorize; có thể chưa capture.
- `InventoryReserved`: hàng đã giữ thành công.
- `OrderCompleted`: terminal state theo đúng định nghĩa nghiệp vụ.

Nếu chỉ đo response time của endpoint trả 202, bạn chưa đo thời gian từ người dùng bấm “Đặt hàng” đến khi đơn thật sự hoàn tất hoặc thất bại rõ ràng.

## 4. Kiến trúc và điểm đo của một kịch bản E2E

~~~mermaid
flowchart LR
    L[Load generator] --> G[API Gateway]
    G --> O[Order Service]
    O --> P[Payment Service]
    O --> I[Inventory Service]
    O --> B[(Message Broker)]
    P --> D1[(Payment DB)]
    I --> D2[(Inventory DB)]
    B --> F[Fulfillment Consumer]
    P --> X[PSP Sandbox]
    O --> T[Tracing / Logs / Metrics]
    P --> T
    I --> T
    F --> T
    B --> T
~~~

Mọi thành phần trên đường request có thể trở thành nút thắt. Nếu chỉ đo một service bằng mock dependency, kết quả mô tả **khả năng của service trong điều kiện mock**, không phải năng lực checkout toàn hệ thống.

Ghi rõ:

1. Điểm bắn tải: public API qua Gateway hay nội bộ trực tiếp.
2. Luồng nghiệp vụ: read, write, checkout, refund, search, admin, event consumer.
3. Số lần gọi xuống mỗi dependency và hành vi retry.
4. Connection pool, timeout, cache, circuit breaker, rate limit, autoscaling.
5. Database, broker, cache, object storage và PSP sandbox có cùng đặc tính giới hạn với môi trường cần dự báo không.
6. Điểm đo terminal outcome: dữ liệu DB, event, workflow projection hay response API.

### 4.1. Ma trận điểm đo

| Lớp | Cần thu thập | Dấu hiệu |
|---|---|---|
| Client / generator | Arrival rate, request latency, timeouts, dropped iterations | Injector không giữ được tải mong muốn |
| Gateway | RPS, 4xx/5xx, P95/P99, rate limit, upstream timeout | Chặn tải hay quá tải upstream |
| Application | Queue/thread pool, request latency, heap, GC, CPU, retries | Saturation, blocking, leak |
| Database | Active connections, lock wait, deadlock, slow query, IOPS | Transaction contention |
| Broker | Publish latency, lag, oldest age, DLQ, redelivery | Backpressure hoặc consumer chậm |
| External dependency | Timeout, 429, response error, per-provider rate limit | Đối tác giới hạn hoặc lỗi |
| Workflow | Started/completed/failed/stuck, duplicate side effect | Hệ thống “xanh” nhưng nghiệp vụ sai |
| Infrastructure | CPU/memory/disk/network, autoscaling events | Tài nguyên hoặc giới hạn hạ tầng |

Không đưa `user_id`, `order_id` và `workflow_id` làm label metric có cardinality lớn. Giữ chúng trong log/trace/event store được phân quyền và dùng correlation để drill down.

## 5. Mô hình workload phải đại diện thực tế

Một script gọi lặp một endpoint với một payload cố định không phản ánh đủ workload production. Cần hiểu:

- Tỷ lệ read/write; ví dụ 60% xem sản phẩm, 20% tìm kiếm, 15% checkout, 5% đọc trạng thái đơn.
- Phân bố dữ liệu: SKU hot, SKU hiếm, giỏ hàng 1–20 mặt hàng, đơn giá trị cao/thấp.
- Tần suất retry của client và gateway; các thao tác có/không có idempotency key.
- Tỷ lệ cache hit/miss; warm cache và cold cache.
- Đa vùng, nhiều tenant, thiết bị/kết nối khác nhau.
- Traffic theo thời gian: cao điểm, thứ tự tăng tải, chu kỳ khuyến mãi, batch cuối ngày.
- Các bước chờ tự nhiên: think time, polling, webhook hoặc event không đồng bộ.
- Tải nền: job, indexing, backup, analytics, outbox publisher, message consumer.

Ví dụ workload dự kiến:

| Journey | Tỷ trọng minh họa | Yêu cầu |
|---|---:|---|
| Xem sản phẩm / catalog | 55% | Read-heavy, cache |
| Tìm kiếm | 20% | Search index và query |
| Bắt đầu checkout | 10% | Khởi tạo workflow |
| Đặt hàng / giữ hàng | 10% | Ghi DB, contention, outbox |
| Theo dõi đơn / refund | 5% | Read + state transition |

Tỷ trọng cần được lấy từ analytics/prod traffic hoặc giả định kinh doanh được ghi rõ. Nếu test nhằm phát hiện oversell, cố ý tạo **hot SKU** với mức contention cao thay vì dùng phân bố bình thường.

### 5.1. Arrival rate và virtual users

Hai cách cấp tải phổ biến:

**Closed model:** một số virtual users cố định, mỗi user đợi response rồi mới gửi tiếp (thường thêm think time). Khi server chậm, vòng lặp của user chậm lại, dẫn tới **arrival rate có thể giảm**. Đây là mô hình phù hợp cho một số hành vi người dùng, nhưng có thể che khuất sự suy giảm do tải.

**Open model:** phát request theo arrival rate mục tiêu (ví dụ 200 iterations/giây) bất kể response chậm; cần đủ VUs/worker để giữ lịch gửi. Phù hợp đo hệ thống trước tốc độ yêu cầu độc lập với thời gian phản hồi.

**Little’s Law** trong trạng thái ổn định:

\[
L = \lambda W
\]

Trong đó `L` là số công việc đang tồn tại trung bình, `λ` là throughput/arrival rate thực sự, `W` là thời gian công việc trung bình. Nếu có 100 requests/giây và mean latency 0,4 giây, số request in-flight trung bình khoảng 40. Công thức chỉ áp dụng theo giả định ổn định và ranh giới đo nhất quán; không thay thế capacity test khi hệ thống đang backlog không ổn định.

### 5.2. Đừng để load generator là nút thắt

Nếu máy bắn tải dùng hết CPU/network, connection hoặc số VUs, kết quả có thể phản ánh injector thay vì hệ thống. Luôn đo:

- Target arrival rate so với actual sent rate.
- `dropped_iterations` hoặc tương đương.
- CPU, memory, file descriptors, network của generator.
- DNS/TLS handshakes, connection reuse và client-side timeouts.
- Khoảng cách giữa intended rate và completed throughput.

Khi cần, dùng nhiều injector phân tán ở vùng phù hợp, đồng bộ thời gian và tách các luồng sinh tải khỏi hệ thống đo.

## 6. Thiết kế các kịch bản tải

### 6.1. Baseline

Chạy ít request và không tranh chấp mạnh; kiểm kết quả nghiệp vụ và cấu hình đo đạc. Baseline giúp phát hiện lỗi script, auth, môi trường hoặc dữ liệu giả trước khi tăng tải.

### 6.2. Normal load

Duy trì tải dự kiến trong khoảng đủ dài để thấy autoscaling và queue tiến tới trạng thái ổn định. Kiểm P95/P99, error, business completion, tài nguyên và backlog.

### 6.3. Peak load

Đặt mức dự báo cao điểm, ví dụ 2–3 lần bình thường nếu đó là giả định kinh doanh có cơ sở. Kiểm headroom và SLO; không tự coi một hệ số tùy ý là yêu cầu production.

### 6.4. Spike

Tăng tải nhanh như mở flash sale rồi hạ lại. Quan sát rate limit, HPA, cold start, connection burst, queue backlog và **thời gian quay về mức bình thường**. Spike có thể nguy hiểm dù tải trung bình thấp.

### 6.5. Stress và break point

Tăng tải có bậc từ mức bền vững tới mức hệ thống không còn giữ SLO. Ghi “knee point” khi latency/queue tăng phi tuyến, mức lỗi xuất hiện, loại lỗi và trạng thái sau khi giảm tải. Điểm gãy không chỉ là CPU 100%: có thể là số connection DB, lock contention, quota PSP hoặc giới hạn consumer.

### 6.6. Soak

Chạy workload đại diện liên tục đủ lâu để phát hiện leak tích lũy, tắc queue, tăng disk, rotation/logging, retry storm hoặc rác dữ liệu test. Quan sát trend theo giờ, không chỉ summary cuối. Nếu quá ít workload, bài test chạy lâu có thể không lộ rò rỉ liên quan transaction nóng.

### 6.7. Recovery / fault injection

Trong lúc giữ tải đại diện, gây lỗi có kiểm soát: restart pod, tăng latency Payment, ngắt một consumer, failover DB hoặc giới hạn egress. Đo khả năng đưa workflow đến trạng thái terminal, backlog drain, phục hồi tài nguyên và bất biến sau sự cố.

## 7. Một test plan có thể triển khai

Ví dụ test plan cho Order Checkout trong staging chuyên dụng:

| Giai đoạn | Mức tải minh họa | Thời lượng | Mục tiêu |
|---|---:|---:|---|
| Warm-up | 10 req/s | 5 phút | Làm nóng cache/JIT, kiểm dữ liệu |
| Baseline | 20 req/s | 10 phút | Chuẩn đo tại tải thấp |
| Normal | 100 req/s | 20 phút | Kiểm SLO ngày thường |
| Peak | 200 req/s | 20 phút | Kiểm tải cao điểm |
| Spike | 50 → 400 → 50 req/s | 5 phút | Kiểm burst và drain backlog |
| Stress | Tăng 100 req/s mỗi bậc | Theo điều kiện dừng | Xác định giới hạn |
| Soak | 100 req/s | 6–24 giờ | Phát hiện drift/leak |
| Recovery | 100 req/s + fault injection | Theo kịch bản | Kiểm khi lỗi phụ thuộc |

Đây là **ví dụ các bài thử riêng hoặc các giai đoạn có kiểm soát**, không yêu cầu thực hiện tất cả liên tục trong một lần. Nếu test dữ liệu có side effect, phải dọn dữ liệu/đối soát giữa các giai đoạn hoặc sử dụng namespace/test IDs để tách kết quả.

### 7.1. Điều kiện bắt đầu và dừng

Trước khi chạy:

- Có môi trường, dữ liệu, quyền và thời điểm thử đã được thống nhất.
- Có dashboard/trace/log và hệ thống đo business outcome.
- Snapshot cấu hình, phiên bản code, replica, giới hạn CPU/memory, DB sizing, broker partitions.
- PSP ở sandbox hoặc mock có giới hạn rõ, tránh giao dịch thật.
- Có khả năng reset dữ liệu và biết cách xử lý giao dịch đang dở.
- Generator đủ công suất để tạo target traffic.
- Có điều kiện abort nếu xuất hiện double charge, corruption, queue không kiểm soát, hoặc tác động tới hệ thống dùng chung.

**Điều kiện dừng phải theo rủi ro thực tế**. Một bài stress có thể cố ý vượt SLO, nhưng không nên tiếp tục vô hạn khi có lỗi ghi dữ liệu hoặc ảnh hưởng môi trường chung.

## 8. Ví dụ load test với k6

Ví dụ dưới dùng mô hình **constant arrival rate** để bắn yêu cầu tạo đơn ở endpoint giả định `POST /api/orders`. Dữ liệu và idempotency key phải được phân biệt theo workflow; khi muốn test retry cùng key, dùng một scenario riêng.

~~~javascript
import http from 'k6/http';
import { check } from 'k6';
import exec from 'k6/execution';

const baseUrl = __ENV.BASE_URL || 'https://staging.example.invalid';
const token = __ENV.TEST_TOKEN || '';

export const options = {
  scenarios: {
    create_order: {
      executor: 'constant-arrival-rate',
      rate: 50,
      timeUnit: '1s',
      duration: '10m',
      preAllocatedVUs: 100,
      maxVUs: 300,
      gracefulStop: '30s',
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    'http_req_duration{scenario:create_order}': ['p(95)<800', 'p(99)<1500'],
    checks: ['rate>0.99'],
    dropped_iterations: ['count==0'],
  },
};

export default function () {
  const unique = String(exec.scenario.iterationInTest);
  const idempotencyKey = 'load-' + unique;
  const body = JSON.stringify({
    customerRef: 'test-customer-' + (exec.vu.idInTest % 500),
    lines: [{ sku: 'test-sku-' + (exec.vu.idInTest % 100), quantity: 1 }],
    clientRequestId: unique,
  });

  const res = http.post(baseUrl + '/api/orders', body, {
    headers: {
      'Content-Type': 'application/json',
      Authorization: 'Bearer ' + token,
      'Idempotency-Key': idempotencyKey,
    },
    timeout: '15s',
    tags: { operation: 'create_order' },
  });

  check(res, {
    'accepted or created': (r) => r.status === 201 || r.status === 202,
    'has correlation header': (r) => Boolean(r.headers['X-Correlation-Id']),
  });
}
~~~

Lệnh chạy minh họa:

~~~bash
BASE_URL=https://staging.example.invalid TEST_TOKEN=sample-test-token k6 run checkout.js
~~~

Lưu ý:

- `BASE_URL` phải là môi trường được phép kiểm thử. `TEST_TOKEN` ở dòng lệnh chỉ là placeholder; production nên dùng cách cấp secret của runner bảo mật, tránh in token vào history/log.
- Mã dựa trên API giả định. Đổi payload, header và status code cho hợp đồng thật.
- `exec.scenario.iterationInTest` cung cấp chỉ số iteration duy nhất của scenario trong lần chạy; khi nhiều lần chạy cùng bộ dữ liệu, nên thêm run ID được cấp an toàn vào idempotency key để tránh đụng key cũ.
- `http_req_duration` đo phản hồi HTTP, không tự chứng minh `OrderCompleted`. Cần bước xác nhận workflow terminal, có thể bằng kiểm tra hậu kỳ từ DB/event hoặc một validation job riêng.
- Ngưỡng `checks` có thể không đạt vì header giả định; phải định nghĩa phù hợp môi trường, không xóa tiêu chí chỉ để xanh.
- `dropped_iterations` cho biết injector không khởi tạo đủ iterations theo lịch; nếu tăng, cần kiểm generator/cấu hình VUs trước khi kết luận về throughput.
- Nếu hệ thống trả 429 theo policy bảo vệ, phân loại rõ “graceful rejection” với lỗi kỹ thuật; SLO phải định nghĩa cách tính.
- Dữ liệu ví dụ có 100 SKU và 500 customer refs; để test tải phân bố thực tế, mô hình phân phối phải lấy từ dữ liệu phù hợp thay vì phép modulo đơn giản.

### 8.1. Khi test idempotency, phải cố tình gửi trùng key

Bài load bình thường dùng key khác nhau để tạo giao dịch mới. Bài test retry chọn **một business operation cụ thể**, gửi đồng thời nhiều request cùng key và cùng payload; xác nhận:

- Tất cả response có ý nghĩa nhất quán theo contract (có thể 201/200/202 hoặc conflict hợp lệ).
- Chỉ một order/payment effect được commit.
- Nếu cùng key nhưng payload khác, hệ thống từ chối hoặc áp chính sách deterministic đã định.
- Khi client timeout, retry cùng key không sinh side effect mới.
- Kết quả giữa nhiều instance vẫn đúng, không chỉ trên một pod.

Không dùng một key cố định xuyên mọi iteration trong bài load capacity thông thường vì đó là tải vào cache idempotency, không phải tải tạo đơn thực tế.

## 9. Đọc số liệu load test đúng cách

### 9.1. Latency, throughput và error rate

- **Latency:** thời gian mỗi yêu cầu hoặc mỗi workflow; nhìn P50/P95/P99 và tối đa khi hữu ích.
- **Throughput:** request/giây, transaction/giây hoặc workflow hoàn tất/giây; nêu đơn vị và grain.
- **Arrival rate:** yêu cầu gửi vào/giây, có thể khác throughput nếu queue tăng.
- **Error rate:** phải phân biệt timeout, 5xx, 429, validation 4xx, decline nghiệp vụ.
- **Saturation:** CPU, memory, thread/connection pool, queue, DB lock waits, broker lag.
- **Backlog:** công việc đang chờ và tuổi công việc lâu nhất.
- **Business correctness:** số đơn hoàn thành, lỗi bù trừ, duplicate side effects.

Tại trạng thái bền vững, arrival rate và completion throughput nên gần nhau trong cửa sổ đủ dài. Nếu gửi 200 req/s nhưng chỉ hoàn thành 150 workflows/s, backlog sẽ tăng khoảng 50 workflows/s, trừ trường hợp một số request bị từ chối/hủy theo contract.

### 9.2. P95 không đủ nói toàn bộ câu chuyện

Giả sử 95% checkout dưới 500 ms, nhưng 5% còn lại mất 20 giây và một số đã thu tiền chưa giữ hàng. P95 có thể đạt, nhưng tail và business state nghiêm trọng. Cần kết hợp:

- P99 và timeout rate.
- Worst-case workflow age theo trạng thái.
- Số stuck workflows và phục hồi.
- Trạng thái của đơn đã có payment side effect.
- Phân đoạn theo route, region, method và phiên bản release.
- Mẫu số và số lượng quan sát để biết percentile có ổn định không.

Đừng chỉ lấy trung bình một batch 5 phút nếu giai đoạn đầu 1 phút tốt, cuối 4 phút backlog tăng liên tục. Plot theo thời gian để tìm drift và điểm bắt đầu suy giảm.

### 9.3. Nút thắt phải tìm bằng bằng chứng

Ví dụ dưới 200 req/s, P99 tăng từ 400 ms lên 3 giây, CPU service chỉ 45%, nhưng DB active connections đạt giới hạn và lock wait tăng. Tăng replica của service có thể làm contention tệ hơn. Hướng điều tra là transaction scope, query/index, lock ordering, connection pool size và số request in-flight.

Tương tự, queue lag tăng có thể do consumer chậm, producer burst, partition skew, poison messages hoặc downstream bị rate limit. Không suy diễn “broker chậm” chỉ từ depth lớn.

## 10. Cạnh tranh dữ liệu: các lỗi cơ bản

**Race condition** là lỗi mà kết quả phụ thuộc vào thứ tự hoặc thời điểm chạy của nhiều tác vụ đồng thời. Trong microservices, tính đồng thời đến từ nhiều HTTP request, thread, pod, worker, consumer group, callback bên thứ ba và retry.

### 10.1. Lost update

Hai request đọc `stock=1`, cả hai quyết định còn hàng, rồi cùng ghi `stock=0` và tạo hai reservation. DB cuối có số 0 nhưng đã bán hai sản phẩm.

~~~text
Request A                   Request B
READ stock=1                READ stock=1
CHECK >= 1                  CHECK >= 1
WRITE stock=0               WRITE stock=0
CREATE reservation A        CREATE reservation B
Result: two reservations for one unit
~~~

Lỗi nằm ở thao tác “đọc → kiểm → ghi” không nguyên tử, không phải do máy tính tính sai.

### 10.2. Check-then-act

Hai worker cùng kiểm “payment attempt chưa tồn tại” rồi cùng insert. Nếu chỉ kiểm trước khi ghi mà không có unique constraint/atomic operation, cả hai có thể tạo payment attempts khác nhau.

### 10.3. Double spend / duplicate side effect

Client gửi thanh toán, PSP xử lý nhưng response bị timeout. Client retry, Payment Service tạo thêm request thu tiền. Không được suy từ “timeout” rằng giao dịch bên ngoài chắc chắn thất bại; cần idempotency key và đối soát.

### 10.4. Write skew

Hai transaction đọc dữ liệu chéo và cập nhật hai dòng khác nhau, riêng từng dòng vẫn hợp lệ nhưng bất biến tổng thể bị phá. Ví dụ lịch trực có ít nhất một người phải on-call; hai người cùng đọc “người kia vẫn đang trực” rồi đều tắt trạng thái của mình. Tùy isolation level, cần constraint, khóa hoặc transaction serializable và xử lý retry.

### 10.5. Deadlock và starvation

Hai transaction khóa A rồi B và B rồi A, dẫn tới deadlock. DB thường chọn một transaction làm nạn nhân; ứng dụng phải bắt lỗi transaction, retry có giới hạn với idempotency phù hợp. Starvation xảy ra khi một số tác vụ liên tục thua tranh chấp hoặc bị queue ưu tiên bỏ quên.

### 10.6. Out-of-order events

`PaymentSucceeded` đến trước `PaymentPending` do consumer/partition khác nhau hoặc replay. Nếu service áp cập nhật trạng thái chỉ theo thời điểm nhận, nó có thể lùi từ thành công về pending. Cần transition guard, version/sequence và logic đối soát.

## 11. Kỹ thuật bảo vệ bất biến khi đồng thời

### 11.1. Atomic conditional update

Thay thao tác đọc rồi ghi bằng update có điều kiện trong DB:

~~~sql
UPDATE inventory
SET available = available - :quantity
WHERE sku = :sku
  AND available >= :quantity;
~~~

Ứng dụng kiểm `rows_updated == 1` để biết reservation có được thực hiện. Điều này giúp tránh oversell ở **một dòng tồn kho** khi database bảo đảm tính nguyên tử của statement. Nhưng vẫn cần:

- Ghi reservation ID và kiểm unique key để xử lý cùng order retry.
- Đảm bảo update và insert reservation cùng transaction.
- Thiết kế cho nhiều kho, nhiều SKU, bundle và trạng thái reserved vs available.
- Xử lý transaction retry/deadlock và khi transaction fail.
- Kiểm tác dụng của isolation level và distributed writes.

Một transaction minh họa:

~~~text
BEGIN
  INSERT reservation(order_id, sku, qty) ... 
    ON CONFLICT (order_id, sku) DO NOTHING;
  if newly inserted:
      UPDATE inventory
      SET available = available - qty
      WHERE sku = skuKey AND available >= qty;
      if no row updated: ROLLBACK
COMMIT
~~~

Pseudocode này cần điều chỉnh cho DB, schema và quy tắc một order nhiều reservation. Mục tiêu là **unique business key + atomic stock deduction + single transaction**, không phải cú pháp copy/paste nguyên xi.

### 11.2. Optimistic locking

Gắn version cho entity; update chỉ thành công nếu version chưa đổi.

~~~sql
UPDATE inventory
SET available = :new_available,
    version = version + 1
WHERE sku = :sku AND version = :expected_version;
~~~

Nếu số dòng cập nhật là 0, đã có transaction khác sửa; đọc lại/đánh giá lại và retry có giới hạn. Với JPA, `@Version` hỗ trợ optimistic locking trên entity phù hợp. Đừng retry vô hạn khi hot SKU bị tranh dữ dội; cần backoff và có thể chuyển sang chiến lược atomic update.

### 11.3. Pessimistic locking

`SELECT ... FOR UPDATE` hoặc cơ chế khóa hàng tương đương có thể bảo vệ đoạn xử lý phụ thuộc nhiều trường. Nhưng lock giữ lâu làm tăng latency và deadlock. Không giữ transaction DB mở trong lúc chờ PSP hoặc network call bên ngoài.

### 11.4. Unique constraints

Unique constraint ở database là tuyến phòng thủ quan trọng cho business identity, ví dụ:

~~~sql
CREATE UNIQUE INDEX uniq_payment_idempotency
ON payment_attempts(merchant_id, idempotency_key);

CREATE UNIQUE INDEX uniq_inventory_reservation
ON inventory_reservations(order_id, sku);
~~~

Các khóa minh họa phụ thuộc domain. Nếu một order hợp lệ được reserve nhiều lần ở nhiều warehouse hoặc attempt, khóa phải phản ánh thiết kế đó. **Chỉ check trong application** mà không có constraint thường không đủ khi nhiều instance chạy đồng thời.

### 11.5. Isolation level và transaction boundaries

| Cơ chế | Ý nghĩa thực hành | Cảnh báo |
|---|---|---|
| Read Committed | Tránh đọc dữ liệu chưa commit | Không tự ngăn lost update/check-then-act |
| Repeatable Read / Snapshot | Ổn định tập dữ liệu nhìn thấy theo DB | Tùy DB vẫn có write skew hoặc đặc tính khác |
| Serializable | Gần với thực thi tuần tự hợp lệ | Cần bắt serialization failure và retry an toàn |
| Row lock | Khóa tài nguyên cụ thể | Có thể contention/deadlock |
| Optimistic version | Phát hiện xung đột tại update | Cần xử lý conflict |
| Atomic conditional update | Đổi trạng thái có điều kiện trong một statement | Cần constraint/business transaction bao quanh |

Đừng suy rằng tên isolation level luôn đồng nghĩa cùng hành vi trên mọi database. Hãy đọc đúng engine/phiên bản và kiểm bằng integration test thật.

## 12. Test concurrency thật sự trong Java

Unit test chạy tuần tự không bộc lộ race. Một concurrency test nên tạo **va chạm có chủ đích** tại cùng tài nguyên, đồng bộ thời điểm bắt đầu và kiểm bất biến sau khi tất cả tác vụ kết thúc.

Ví dụ JUnit 5 minh họa: có duy nhất một đơn vị hàng, 20 luồng cố reserve cùng SKU; chỉ một luồng được thành công.

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;

class InventoryConcurrencyTest {

    // Đây là fixture tích hợp DB thật qua repository/service của dự án.
    private InventoryService inventoryService;
    private InventoryRepository inventoryRepository;

    @Test
    void onlyOneReservationWinsForLastItem() throws Exception {
        String sku = "HOT-SKU";
        inventoryRepository.setAvailableForTest(sku, 1);

        int workers = 20;
        ExecutorService pool = Executors.newFixedThreadPool(workers);
        CountDownLatch ready = new CountDownLatch(workers);
        CountDownLatch start = new CountDownLatch(1);
        List<Future<Boolean>> results = new ArrayList<>();

        try {
            for (int i = 0; i < workers; i++) {
                final String orderId = "order-" + i;
                results.add(pool.submit(() -> {
                    ready.countDown();
                    if (!start.await(10, TimeUnit.SECONDS)) {
                        throw new TimeoutException("start signal missing");
                    }
                    return inventoryService.reserve(orderId, sku, 1);
                }));
            }

            assertTrue(ready.await(10, TimeUnit.SECONDS));
            start.countDown();

            int success = 0;
            for (Future<Boolean> result : results) {
                if (result.get(20, TimeUnit.SECONDS)) {
                    success++;
                }
            }

            assertEquals(1, success);
            assertEquals(0, inventoryRepository.available(sku));
            assertEquals(1, inventoryRepository.countReservations(sku));
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Đây là **mẫu kiểm thử**, không phải file Java tự chạy được vì `InventoryService`, `InventoryRepository` và setup DB của dự án chưa được định nghĩa. Quan trọng là phương pháp: tạo đúng fixture và ranh giới transaction, đồng bộ start, thu kết quả, kiểm invariant cuối.

### 12.1. Tránh “test pass vì không thật sự tranh chấp”

- Số luồng nhiều không bảo đảm cùng chạm code path quan trọng; dùng barrier/latch hoặc fault injection có kiểm soát.
- Nếu test dùng DB H2 in-memory còn production dùng PostgreSQL/MySQL, semantics lock/isolation có thể khác. Với logic transaction, test trên engine gần production, ví dụ Testcontainers với DB thật.
- Test bên trong một `@Transactional` bao ngoài toàn method có thể khiến mọi thao tác dùng transaction test hoặc bị rollback không giống runtime; cần định nghĩa transaction per worker.
- Một lần pass không chứng minh hết race; lặp trên nhiều seed/interleaving, dùng lịch có chủ đích, test nhiều pod/process nếu cần.
- Đo cả kết quả trả về và trạng thái durable: số reservation, tồn kho, payment attempts, outbox events.
- Nếu khi xung đột được phép trả “try again”, test phải xác minh retry có giới hạn và không gây side effect trùng.

## 13. Các kịch bản tranh chấp đặc trưng của microservices

### 13.1. Nhiều người mua cùng SKU cuối cùng

**Tiền điều kiện:** tồn kho một đơn vị, 20 order khác nhau, tất cả cùng thời điểm. **Bất biến:** tổng reservations hợp lệ không quá một, available không âm, đơn thua được thông báo đúng và không bị charge vô cớ.

Kiểm thử cần đi qua Order/Inventory ở ít nhất một scenario E2E, ngoài integration test DB; xem cả trường hợp Payment đã authorize trước khi inventory thất bại và compensation.

### 13.2. Retry cùng idempotency key trên nhiều pod

**Tiền điều kiện:** một logical operation, cùng key + payload, đồng thời qua load balancer tới nhiều pod. **Bất biến:** một order hoặc payment attempt durable; cùng response semantic; không double charge ở PSP.

Biến thể: cùng key nhưng payload khác, key hết TTL, process crash sau commit trước response, network timeout, client retry sau failover. Idempotency phải có scope (user/merchant/resource), TTL và định nghĩa conflict rõ.

### 13.3. Hai webhook cho cùng giao dịch

PSP gửi `PaymentSucceeded` hai lần và một `PaymentPending` đến trễ. Payment Service phải kiểm chữ ký, đối chiếu giao dịch, de-dup và state transition. Không được “lùi trạng thái” hoặc trigger fulfillment hai lần.

### 13.4. Message broker redelivery

Consumer đã commit DB nhưng crash trước ACK. Broker gửi lại. Bất biến: một event chỉ tạo một logical side effect dù được nhận nhiều lần. Test cả redelivery cùng `event_id` và event tương đương có ID khác để kiểm business key.

### 13.5. Concurrent refund và capture

Hai command hợp lệ về auth nhưng cạnh tranh state của cùng payment. Nếu cả refund và capture dùng trạng thái cũ, có thể xuất hiện chuyển đổi không hợp lệ. State machine phải cho phép đúng transition và lock/version phù hợp.

### 13.6. Saga compensation chạy song song với bước tiếp theo

Payment timeout nhưng PSP đã charge; Inventory báo out-of-stock; orchestration bắt đầu refund trong khi một callback thành công đến muộn. Bất biến: kết quả cuối rõ ràng, không tạo fulfillment trái phép, refund không lặp và không mất audit.

### 13.7. Read-after-write trong hệ eventual consistency

Sau `OrderPlaced`, projection tìm kiếm đơn cập nhật sau vài giây. Kiểm thử cần phân biệt “stale read nằm trong contract” với “lost update” hoặc “event thất lạc”. Nếu yêu cầu consistency mạnh cho bước xác nhận, hãy đọc nguồn phù hợp hoặc dùng read-your-writes strategy.

## 14. Idempotency và tính đúng đắn xuyên nhiều transaction

Microservices thường không có một transaction ACID duy nhất bao trùm Order DB, Payment DB, broker và PSP. “Exactly once” ở một broker không bảo đảm side effect bên ngoài đúng một lần.

Một thiết kế phổ biến:

1. Client gắn `idempotency_key` cho logical command.
2. Service ghi bản ghi request/attempt với unique key ở DB.
3. Domain change và outbox event được commit trong cùng transaction nếu phù hợp.
4. Publisher gửi outbox; consumer de-dup bằng event ID hoặc business key.
5. Lời gọi PSP dùng idempotency mechanism theo hợp đồng PSP.
6. Recovery/reconciliation xử lý trường hợp kết quả bên ngoài không rõ.
7. Một workflow chỉ chuyển terminal state theo state machine.

### 14.1. Các cửa sổ lỗi cần test

| Điểm crash/timeout | Rủi ro | Kết quả mong đợi |
|---|---|---|
| Trước DB commit | Command chưa ghi | Retry được xử lý an toàn |
| Sau DB commit, trước HTTP response | Client tưởng chưa thành công | Retry cùng key trả kết quả logic cũ |
| Sau outbox commit, trước publish | Event chưa xuất hiện | Publisher gửi sau khi restart |
| Sau publish, trước mark sent | Event có thể gửi lặp | Consumer idempotent |
| Sau consumer DB commit, trước ACK | Broker redelivery | Không tạo side effect kép |
| Sau PSP charge, trước response | Không biết trạng thái thu tiền | Query/reconcile bằng attempt ID, không tạo charge mới |
| Callback đến sau compensation | State transition cạnh tranh | Không phá terminal invariant |

Test fault injection chính xác tại các điểm này mang lại giá trị cao hơn việc chỉ tăng RPS ngẫu nhiên.

## 15. Thiết kế kiểm thử đa instance và phân tán

Một race có thể chỉ xuất hiện khi nhiều replica xử lý cùng một key. Do đó cần kiểm:

- Nhiều pod/service instance cùng nhận request.
- Load balancer không luôn sticky vào một instance.
- Shared DB, Redis, broker và external API tương tự production.
- Lock phân tán nếu dùng có TTL, lease renewal, fencing token và xử lý lock-holder chết.
- Clock skew, network partition và delayed message.
- State machine chịu được event từ nhiều producer/consumer.
- Không dựa vào `synchronized` trong một JVM để bảo vệ tài nguyên giữa các pod.

Nếu sử dụng distributed lock, bản thân lock cũng cần test: holder pause lâu hơn TTL, holder cũ tỉnh lại và ghi muộn, lock service failover, token fencing. **Distributed lock không thay thế unique constraint và kiểm soát state** khi dữ liệu quan trọng nằm ở database.

### 15.1. Kafka và thứ tự xử lý

Với broker theo partition, thứ tự thường chỉ được bảo đảm trong phạm vi partition/key cụ thể; không giả định toàn bộ topic hoặc nhiều topic có thứ tự toàn cục. Khi cần cùng order xử lý có thứ tự, chọn partition key ổn định và vẫn xử lý replay, duplicate, consumer rebalance và side effects trong database. Test sau tăng số consumer/partition và deploy rolling.

### 15.2. So sánh hai loại workload

- **Wide-key load:** hàng nghìn khách/SKU khác nhau; tốt cho thông lượng và pressure lên hạ tầng.
- **Hot-key contention:** hàng trăm request cùng SKU/order/payment intent; tốt cho lock, unique constraint, queue per key và retry conflict.

Cần cả hai. Một hệ thống tối ưu wide-key vẫn có thể sụp trước một sản phẩm flash sale, dù tổng RPS chưa quá cao.

## 16. Kiểm thử sức chịu đựng (soak/endurance)

Soak chạy tải đại diện đủ lâu để phát hiện **sự suy giảm theo thời gian**. Mục tiêu không chỉ là giữ request rate mà còn giữ **tính đúng đắn và cân bằng tài nguyên**.

### 16.1. Các loại lỗi dài hạn

- Heap tăng do giữ cache/listener hoặc reference không được giải phóng.
- Native/off-heap memory tăng trong client/driver.
- Connection pool leak: borrowed connections tăng mà không trở về.
- File descriptors/socket leak, thread leak.
- Queue backlog tích lũy do consumer throughput thấp hơn producer một ít.
- Retry backlog/DLQ tăng sau lỗi nền, không được xử lý.
- Database bloat, index bloat, log/WAL volume, temporary files.
- Disk/log retention tăng vượt hạn mức.
- Clock/timezone rollover, scheduler chạy trùng vào mốc ngày.
- Token/certificate expiration và rotation làm gián đoạn job lâu.
- Cache growth/eviction bất thường làm P99 tăng dần.
- Garbage collection pause ngày càng dài.
- Data skew tăng theo số order và historical records.
- Đơn hàng/payment workflow bị kẹt khi gặp callback đến muộn.

### 16.2. Phương pháp soak

1. Chạy warm-up để loại JIT/cache cold-start khỏi phân tích trend chính.
2. Đặt workload đủ đại diện, gồm read/write, event, retry, job và trạng thái kết thúc.
3. Chạy liên tục qua các chu kỳ có ý nghĩa: vài giờ, ngày, cron hoặc thời điểm rotation, tùy hệ thống.
4. Chụp metric theo thời gian; so sánh hour 1, hour 3, hour 6, hour 12, v.v.
5. Tách tài nguyên có **sawtooth ổn định** do GC/cache với tài nguyên tăng không trở về baseline.
6. Kiểm data correctness cuối: không oversell, không double charge, không stuck paid workflows, không event mất.
7. Sau dừng tải, tiếp tục quan sát drain backlog và resource return.

**Độ dài 24 giờ không tự chứng minh ổn định cho mọi chu kỳ.** Nếu lỗi chỉ xảy ra sau monthly billing hoặc token rotation hàng tuần, cần thiết kế tình huống mô phỏng chu kỳ đó, không chỉ kéo dài bài thử.

### 16.3. Metric xu hướng theo thời gian

| Metric | Hành vi kỳ vọng | Dấu hiệu bất thường |
|---|---|---|
| Heap used sau GC | Dao động quanh vùng ổn định | Đáy sau GC tăng liên tục |
| Live threads | Ổn định theo mức concurrency | Tăng đều và không giảm |
| DB active/borrowed connections | Tăng theo tải, trở về sau tải | Borrowed cao dai dẳng |
| Queue lag/oldest age | Dao động hữu hạn, drain được | Tăng dần dù tải ổn định |
| Disk/log usage | Theo retention/rotation | Tăng không giới hạn |
| P95/P99 latency | Ổn định tương đối | Tăng theo giờ trong cùng workload |
| Workflow terminal ratio | Theo baseline/cohort | Pending tích lũy |
| Duplicate side effects | 0 | Xuất hiện sau retry/replay |

Một P99 tăng từ 300 ms lên 2 giây trong sáu giờ trong khi RPS không đổi là tín hiệu cần điều tra. Kiểm đồng thời GC, DB pool, disk, queue, dependency và số lượng records; không tự kết luận memory leak nếu chỉ nhìn một đường biểu diễn.

## 17. Kiểm thử khôi phục dưới tải

Trong microservices, resilience testing nên được thực hiện trong khi **workflow đang hoạt động**, bởi lỗi chỉ bộc lộ khi có công việc dở dang.

### 17.1. Ma trận fault injection

| Fault | Tình huống | Điều cần xác minh |
|---|---|---|
| Kill một pod Order | Request đang xử lý | Retry không tạo order trùng, load balancer route lại |
| Payment timeout | PSP đã/ chưa charge | Idempotency và reconciliation; không double charge |
| Broker unavailable | Outbox publisher không gửi được | Event vẫn durable; backlog drain khi broker hồi phục |
| Consumer crash trước ACK | DB đã commit | Redelivery không gây reservation trùng |
| DB failover | Transaction in-flight | Retry đúng loại lỗi, không lost write |
| Network latency 500–2000 ms | Các service gọi lẫn nhau | Timeouts/deadlines, circuit breaker, queue bound |
| Một node/zone lỗi | Hệ thống nhiều replica | HPA/failover và phân phối tải đúng |
| Throttle/rate limit PSP | 429 hoặc quota thấp | Backoff+jitter có giới hạn, không retry storm |
| Secret/certificate rotation | Long-running connections | Refresh/reconnect và quyền đúng |
| Disk/full logs | Soak kéo dài | Alert sớm, graceful degradation hoặc fail safe |

### 17.2. Tiêu chí phục hồi

Sau fault, đo:

- Thời gian từ fault đến service/workflow phục hồi.
- Số request/user/workflow bị ảnh hưởng.
- Tốc độ drain queue/backlog.
- Số workflow còn stuck và phải xử lý thủ công.
- Số compensation bị trễ và kết quả đối soát.
- CPU/memory/connection sau phục hồi có trở về mức ổn định không.
- Có dữ liệu sai, duplicate charge, oversell hoặc trạng thái không thể phục hồi không.

Một service báo healthy trở lại chưa đủ nếu còn hàng nghìn paid orders chưa được giữ kho. **Phục hồi phải được chứng minh bằng terminal business outcome**.

## 18. Backpressure, retry và khả năng chịu quá tải

Khi arrival rate vượt khả năng xử lý, hệ thống phải lựa chọn cách **giới hạn công việc**. Nếu tiếp tục nhận vô hạn vào bộ nhớ/queue, latency và tài nguyên có thể tăng đến sụp hệ thống.

### 18.1. Các cơ chế kiểm soát

- Rate limit theo principal/tenant/endpoint và chính sách quota.
- Bounded queue, giới hạn in-flight requests và bulkhead per dependency.
- Timeout/deadline từ client tới downstream.
- Retry có điều kiện, số lần tối đa, exponential backoff + jitter.
- Circuit breaker để ngừng gọi dependency hỏng tạm thời.
- Load shedding: từ chối sớm với lỗi có thể hiểu hoặc 429/503 theo contract.
- Autoscaling theo chỉ số phù hợp, nhưng có giới hạn tài nguyên thực.
- Idempotency cho write khi retry; không retry mù các thao tác side effect.

### 18.2. Retry amplification

Giả sử Gateway retry 3 lần và Order retry Payment 3 lần. Trong điều kiện xấu, một yêu cầu người dùng có thể tạo tới 9 lời gọi Payment, chưa kể client retry. Khi tải tăng, retry có thể làm downstream càng quá tải. Test phải bật đúng retry policy đang dùng, đo số attempts trên một logical operation và đặt **retry budget**.

### 18.3. Cần đo theo hai góc nhìn

- **External reliability:** người dùng có nhận kết quả/ lỗi rõ, đúng hạn không?
- **Internal containment:** khi quá tải, hệ thống có từ chối có kiểm soát, giữ queue bounded và phục hồi không?

Một request 429 có thể là hành vi bảo vệ đúng; nhưng nếu lượng 429 lớn ở tải mục tiêu, trải nghiệm và capacity vẫn không đạt. Đừng gộp tất cả lỗi vào một biểu đồ mà thiếu phân loại.

## 19. Dữ liệu kiểm thử và môi trường

### 19.1. Môi trường gần production đến mức nào?

Để dự báo capacity, cân nhắc sự khác biệt giữa staging và production:

- CPU, memory, node type, số pod, autoscaling limit.
- Database engine/version, index, partition, data volume, connection limit.
- Broker partitions, retention, throughput quota.
- Cache hit ratio và kích thước keyspace.
- Network latency giữa vùng và đối tác.
- Secret/identity policy, TLS, tracing, sidecar overhead.
- Nền traffic, batch jobs và maintenance.
- Request body size, SKU popularity, customer distribution.

Nếu staging chỉ có 1/10 tài nguyên, cần ghi giới hạn ngoại suy; throughput không luôn tăng tuyến tính theo số replica vì DB/lock/broker có thể là bottleneck chung.

### 19.2. Tạo dữ liệu đủ lớn và có chủ đích

Dùng data generator với run ID để:

- Tạo đủ SKU, customer, orders, payment attempts và lịch sử.
- Có cả distribution bình thường và hot-key contention.
- Tạo dữ liệu random có seed để tái lập khi cần.
- Giữ test fixture độc lập, dễ đối soát và cleanup.
- Có sandbox/mock cho PSP, SMS, shipping; không phát thông báo/giao dịch thật.
- Không dùng thông tin khách hàng thật nếu không có cơ chế xử lý dữ liệu được phê duyệt.

Một bài test chỉ có vài bản ghi nhỏ có thể bỏ qua index selectivity, partitioning và query plan thay đổi khi dữ liệu lớn. Data volume là một trục riêng cần ghi vào báo cáo.

### 19.3. Chống ảnh hưởng môi trường dùng chung

Đặt giới hạn tốc độ và abort condition, namespace riêng, quota tài nguyên, tài khoản test, topic/DB test và budget cho external sandbox. Không cố chạy stress vô hạn lên môi trường production hoặc hệ thống đang phục vụ khách ngoài phạm vi được cho phép. Nếu thử trên production có chủ đích, cần giảm phạm vi và có kế hoạch thao tác, theo dõi cùng owner vận hành.

## 20. Phân tích kết quả và tìm điểm gãy

Mỗi run cần có metadata:

~~~yaml
testRun:
  id: "checkout-peak-2026-11-12"
  environment: "perf-staging"
  serviceVersions:
    order: "2.4.0"
    payment: "2.7.3"
    inventory: "1.9.1"
  configRevision: "git:6f1a2bc"
  dbSize: "approximately-10m-order-records"
  workload:
    arrivalRatePerSecond: 200
    durationMinutes: 20
    scenario: "normal-plus-hot-sku"
  businessChecks:
    noDuplicateCharge: true
    noOversell: true
    noStuckPaidOrders: true
~~~

Metadata là ví dụ, không phải khẳng định kết quả thực tế. Những trường cần lưu: commit/image digest, config revision, infra sizing, số replica, DB snapshot, seed test data, kịch bản, timestamp, dashboard, report generator và nơi lưu artifacts. Nếu thiếu, rất khó so sánh hai run.

### 20.1. Một bảng kết quả minh họa

| Arrival rate | P95 API | P99 API | Tech errors | Queue lag | Nhận định |
|---|---:|---:|---:|---:|---|
| 20 req/s | 120 ms | 220 ms | 0.0% | 0–2 s | Baseline |
| 100 req/s | 350 ms | 800 ms | 0.1% | 2–5 s | Trong ngưỡng |
| 200 req/s | 740 ms | 1.4 s | 0.7% | 5–10 s | Gần giới hạn |
| 300 req/s | 1.9 s | 5.5 s | 4.0% | Tăng liên tục | SLO trượt |
| 400 req/s | 8 s | timeout | 18.0% | Không drain | Quá tải rõ |

Nếu mục tiêu là P95 dưới 800 ms, P99 dưới 1.500 ms và lỗi dưới 1%, 200 req/s *có thể* đạt trong bảng giả định, nhưng phải kiểm thêm workflow completion, correctness, memory và trạng thái backlog sau khi ngừng tải. Với 300 req/s, các tín hiệu chỉ ra điểm gãy trước đó; cần xác định bottleneck thực bằng trace/DB/queue, không chỉ tăng replica ngẫu nhiên.

### 20.2. Các phép kiểm hậu kỳ

Sau test, đối soát:

~~~text
Distinct logical create-order commands
= successful orders
+ rejected/declined commands theo contract
+ workflow đang pending (giải thích được)

Total inventory available + valid reserved + sold
= lượng tồn được mô hình hóa đúng, có xét nhập/xuất bổ sung

Unique payment attempts theo idempotency scope
= số logical payment operations đã chấp nhận

Every captured payment
-> fulfilled or compensated or active recovery case có hạn xử lý

No duplicate charge
No negative stock
No invalid terminal state transitions
No unbounded pending workflow
~~~

Các phương trình trên cần điều chỉnh cho returns, cancel, multiple warehouses và split shipment. Không “pass” chỉ vì HTTP success; kết quả cuối phải đối chiếu với persistent store và external sandbox.

## 21. Thiết kế điều tra khi test thất bại

### 21.1. P99 tăng nhưng CPU thấp

Khả năng: lock contention, DB pool starvation, network latency, synchronous queue/blocking, external dependency hoặc slow query. Tìm trace dài, DB lock wait, connection pool wait, blocked threads và dependency timings.

### 21.2. Throughput ngừng tăng dù thêm replica

Khả năng: bottleneck chung như database, topic partition, cache hot key, PSP quota, distributed lock. Kiểm throughput per component, contention và CPU/IO downstream; scaling service có thể tăng áp lực lên dependency.

### 21.3. API trả 200 nhưng đơn không hoàn tất

Khả năng: event bị mất, outbox backlog, consumer reject schema, DLQ, duplicate hoặc saga state bị kẹt. Kiểm workflow projection và correlation ID xuyên service; đối soát Order DB, Payment DB, broker và consumer logs.

### 21.4. Có hai reservation khi chỉ còn một đơn vị

Khả năng: check-then-act race, transaction boundary sai, unique constraint thiếu hoặc mức isolation không đủ. Tái tạo trên DB thật với đồng bộ tác vụ; xem transaction logs, lock/version, số dòng update và khóa nghiệp vụ.

### 21.5. Lỗi chỉ xuất hiện sau nhiều giờ

Khả năng: memory/connection leak, queue lag tích lũy, data growth, GC, disk, cache, token expiry hoặc scheduled job. So sánh tài nguyên sau GC, borrowed connections, queue age và dữ liệu theo thời gian; dùng heap/thread dump hoặc profiling có kiểm soát nếu cần.

### 21.6. Sau fault mọi pod healthy nhưng backlog còn lớn

Khả năng: consumer công suất thấp, rate limit downstream, poison event hoặc replay. Theo dõi oldest message age và terminal workflow count; tính tốc độ drain với đúng tải nền, tăng worker chỉ khi dependency chịu được.

## 22. Những lỗi thực hành thường gặp

1. **Tăng số VU rồi gọi đó là RPS.** VU không phải arrival rate; nếu server chậm, closed-loop workload có thể tự giảm tải. Cần đo actual sent rate và chọn model phù hợp.
2. **Chỉ đo một endpoint 200 OK.** Chưa đánh giá business completion và async side effects.
3. **Dùng payload cố định.** Cache làm kết quả đẹp, contention phân bố sai, không mô phỏng traffic thật.
4. **Không cố tình tạo hot-key.** Bỏ sót race trên SKU cuối, order ID và payment intent.
5. **Test concurrency chỉ chạy một JVM.** Không tái hiện nhiều pod, distributed lock hoặc network delay.
6. **Dùng H2 để kết luận transaction an toàn trên PostgreSQL.** Semantics khác nhau; test trên engine gần production.
7. **Không kiểm persistent state sau chạy.** Có thể pass latency nhưng dữ liệu đã sai.
8. **Đếm retry như giao dịch mới.** Throughput nghiệp vụ bị phóng đại.
9. **Gộp 4xx hợp lệ với 5xx.** Phân tích failure rate không còn hành động được.
10. **Không đo load generator.** Injector quá tải tạo số liệu giả.
11. **Tăng service replicas khi DB là nút thắt.** Khiến lock/connection pressure tăng thêm.
12. **Chỉ đo 5 phút rồi khẳng định endurance.** Bỏ qua leak, job định kỳ, rotation, backlog tích lũy.
13. **Dừng test ngay khi traffic kết thúc.** Không biết queue có drain và workflow có terminal không.
14. **Không có run ID và config revision.** Khó tái lập/so sánh kết quả.
15. **Chaos test chỉ nhìn pod ready.** Chưa chứng minh tiền/tồn kho/workflow phục hồi đúng.
16. **Coi mọi timeout là thất bại chưa có side effect.** Dễ double charge khi retry.
17. **Chỉ dùng average latency.** Tail latency và stuck workflow bị che khuất.
18. **Thay dữ liệu/infra giữa hai run mà không ghi nhận.** Không thể kết luận cải thiện đến từ code.
19. **Một lần pass chứng minh hết race.** Interleaving không xác định; cần kiểm nhiều điều kiện và ranh giới.
20. **Chạy quá tải không có điều kiện dừng.** Có thể làm hỏng môi trường dùng chung mà không tăng giá trị kiểm thử.

## 23. Quy trình triển khai trong CI/CD và trước release

Không nhất thiết chạy 24 giờ soak trên mỗi pull request. Chia tầng:

| Tầng | Thời điểm | Nội dung | Mục đích |
|---|---|---|---|
| Unit/property tests | Mỗi PR | Pure state transition, invariant, validation | Phát hiện logic sai sớm |
| DB integration concurrency | Mỗi PR hoặc nightly | Multi-thread, transaction, unique constraint, isolation | Phát hiện lost update và race DB |
| Service contract + async | CI | Retry, duplicate event, out-of-order, idempotency | Đảm bảo giao tiếp nhiều service |
| Load smoke | Trước merge/release | Tải vừa, thời gian ngắn, baseline SLO | Chặn regression lớn |
| Peak/stress | Trước release quan trọng | Traffic cao điểm và tìm bottleneck | Xác nhận capacity |
| Soak | Nightly/định kỳ | Nhiều giờ, resource trend và backlog | Phát hiện leak và suy giảm dài hạn |
| Chaos/recovery | Định kỳ / trước thay đổi hạ tầng | Fault injection và audit invariant | Kiểm khả năng phục hồi |

Một **release gate** có thể bao gồm:

- Không có bất biến dữ liệu nào bị phá.
- Tất cả kịch bản concurrency quan trọng pass trên DB thực.
- Normal/peak workload đạt SLO đã thống nhất.
- Business outcome không thất lạc, pending vượt hạn có nguyên nhân rõ.
- Queue drain trong recovery window.
- Không thấy tài nguyên tăng không kiểm soát trong soak phù hợp.
- Báo cáo có run metadata, so sánh baseline và owner phê duyệt kết quả.

Khi có regression, gắn issue với bằng chứng run ID, trace/correlation, workload, bước tái hiện và metric ảnh hưởng. Chỉ một con số “P95 tăng 20%” thiếu bối cảnh chưa đủ kết luận mức độ nguy hiểm.

## 24. Bài tập thực hành

### Bài A — Tính mức concurrency

Một hệ thống nhận 150 requests/giây, mean response time 600 ms trong trạng thái ổn định. Dùng Little’s Law ước lượng số request in-flight trung bình. Nếu response time tăng lên 2 giây trong khi arrival rate giữ nguyên, ước lượng concurrency mới. Giải thích vì sao connection pool 50 có thể trở thành giới hạn và vì sao công thức không áp dụng máy móc khi queue đang tăng vô hạn.

**Gợi ý:** `L = λW`, đơn vị giây. Đừng đồng nhất request in-flight với connection DB: không phải mọi request đều giữ connection trong toàn bộ thời gian.

### Bài B — SKU cuối cùng

Kho có một sản phẩm. 50 khách đặt cùng một SKU trong 100 ms; mỗi request đi vào pod khác nhau. Thiết kế test gồm setup data, cách bắn đồng thời, assertion database, expected API outcomes và kiểm compensation nếu Payment thực hiện trước Inventory.

**Gợi ý:** chỉ một reservation hợp lệ; available không âm; không có duplicate payment; mọi workflow khác có terminal error hoặc refund hợp lệ.

### Bài C — Retry sau timeout PSP

Payment Service gọi PSP. PSP đã thu tiền nhưng TCP response bị mất. Gateway retry tạo đơn và Payment nhận lại cùng idempotency key. Hãy liệt kê cửa sổ lỗi, DB unique key, PSP idempotency mapping, cách query trạng thái và test xác minh không double charge.

### Bài D — Broker redelivery

Inventory consumer nhận `ReserveInventory(event_id=E1)`, commit reservation rồi crash trước ACK. Khi restart, E1 xuất hiện hai lần nữa và E2 (cùng logical order nhưng event ID khác) đến muộn. Thiết kế idempotent consumer với business key, inbox/outbox và state transition; giải thích tại sao chỉ de-dup E1 chưa đủ.

### Bài E — Soak test

Checkout được chạy ổn định 120 req/s trong 8 giờ. P95 tăng đều, active DB connections gần chạm max, queue age cũng tăng. Bạn sẽ kiểm mốc thời gian, connection leak, transaction duration, consumer throughput, retries, data volume và event freshness thế nào? Thiết kế tiêu chí dừng/khôi phục sau test.

### Bài F — Fault injection

Trong lúc Order → Payment → Inventory đang xử lý 100 req/s, restart một Payment pod và làm tăng latency PSP lên 2 giây. Nêu những SLI cần theo dõi, expected degradation, retry budget, recovery window và bước đối soát cuối để chứng minh không có double charge hoặc stuck paid order.

## 25. Checklist chuẩn bị và nghiệm thu

### Trước chạy

- [ ] Có mục tiêu, SLO, business invariants và owner.
- [ ] Chọn đúng loại test: load, stress, spike, concurrency, soak, recovery.
- [ ] Workload có traffic mix, arrival model, dữ liệu, think time và hot-key rõ ràng.
- [ ] Tài nguyên, phiên bản app/config và đặc tính DB/broker đã được ghi nhận.
- [ ] Có test data riêng, PSP sandbox/mock, quyền, cleanup và abort condition.
- [ ] Generator có đủ công suất, đo target/actual rate và dropped iterations.
- [ ] Thu thập latency, throughput, error, saturation, queue lag, workflow outcomes.

### Trong chạy

- [ ] Theo dõi P95/P99 và time series, không chỉ summary cuối.
- [ ] Quan sát memory, GC, threads, DB locks, connections, broker lag, DLQ.
- [ ] Kiểm response semantics và business outcome đang tiến tới terminal state.
- [ ] Có thể xác định trace/workflow instance bị ảnh hưởng khi phát hiện lỗi.
- [ ] Kiểm tải injector và điều kiện dừng an toàn.

### Sau chạy

- [ ] Đối soát no double charge, no oversell, no duplicate reservation.
- [ ] Đếm đúng logical workflows, không đếm trùng retry/events.
- [ ] Đợi backlog drain và xác minh recovery của workflow dở dang.
- [ ] Kiểm memory/connection/disk/queue trở về vùng ổn định.
- [ ] So sánh với baseline có cùng điều kiện, ghi giới hạn ngoại suy.
- [ ] Lưu run ID, commit/config revision, workload, metric, kết luận và bước xử lý.
- [ ] Có người chịu trách nhiệm cho bottleneck và regression đã phát hiện.

## 26. Ghi nhớ cốt lõi

Một hệ thống nhiều dịch vụ “chịu tải tốt” phải thỏa **ba điều kiện đồng thời**:

1. **Nhanh và đủ công suất:** giữ latency, throughput và error rate trong SLO ở workload đã công bố.
2. **Đúng dữ liệu dưới cạnh tranh:** không oversell, double charge, lost update, duplicate side effect hoặc state transition sai khi nhiều tác vụ cùng xử lý.
3. **Ổn định và phục hồi:** không rò tài nguyên, không tích backlog vô hạn, và khi lỗi phụ thuộc có thể tiếp tục hoặc bù trừ để đưa workflow tới kết quả rõ ràng.

Vì vậy, một báo cáo chỉ có “10.000 RPS” chưa đủ chứng minh hệ thống an toàn. Cần mô hình workload thực tế, bất biến nghiệp vụ, điểm đo xuyên service, test đồng thời có chủ đích, soak test đủ chu kỳ và đối soát trạng thái sau khi chạy. Giá trị của bộ kiểm thử nằm ở việc nó giúp nhóm biết **giới hạn ở đâu, vì sao, lỗi nào có thể xảy ra và cách xác minh sửa lỗi đã thực sự bảo vệ người dùng**.