# Thông lượng, các phân vị độ trễ và cùng một tải thử nghiệm

Khi so sánh Spring Boot chạy trên JVM với ứng dụng đã biên dịch thành **GraalVM Native Image**, một kết quả như “native nhanh hơn” chỉ có ý nghĩa khi hai phiên bản nhận cùng một tải và được đo trong điều kiện tương đương. Cần xem đồng thời **thông lượng (throughput)**, **phân vị độ trễ (latency percentiles)**, tỷ lệ lỗi và mức tiêu thụ tài nguyên. Một con số trung bình đơn lẻ có thể che khuất những request chậm hoặc những lần hệ thống không đáp ứng được tải đã đặt.

Trong module **`SPRING_BOOT_NATIVE_IMAGE`**, mục tiêu là dùng Spring AOT để biên dịch ứng dụng, đánh giá startup và memory, kiểm thử tương thích, đóng gói container và vận hành bản native. Bài học này xây dựng quy trình benchmark có thể lặp lại: định nghĩa workload, cố định dữ liệu và môi trường, chọn mô hình tải phù hợp, đo RPS cùng p50/p95/p99, phát hiện điểm bão hòa và lập bảng so sánh JVM/native có thể giải thích được.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt throughput, offered load, completed requests và successful throughput.
- Đọc p50, p95, p99 và hiểu vì sao tail latency quan trọng.
- Chọn open workload model hoặc closed workload model theo mục tiêu đo.
- Thiết kế cùng một request mix, dữ liệu, thời lượng và cấu hình tải cho JVM/native.
- Dùng k6 `constant-arrival-rate` để giữ tốc độ bắt đầu iteration ổn định.
- Theo dõi `http_req_duration`, `http_req_waiting`, `http_req_failed` và `dropped_iterations`.
- Tách thời gian warm-up khỏi cửa sổ đo steady-state.
- Đo CPU, RSS/container memory và GC bên cạnh latency/throughput.
- Xác định mức tải tối đa vẫn đáp ứng SLO.

## 2. Ba nhóm chỉ số cần đo

Một benchmark dịch vụ HTTP cần tối thiểu ba nhóm chỉ số:

| Nhóm | Chỉ số | Câu hỏi cần trả lời |
|---|---|---|
| Lưu lượng | Offered requests/s, completed requests/s, successful requests/s | Hệ thống nhận và xử lý được bao nhiêu request mỗi giây? |
| Độ trễ | p50, p90, p95, p99, đôi khi p99.9 | Người dùng phải chờ bao lâu, đặc biệt ở phần đuôi phân phối? |
| Độ tin cậy | HTTP error rate, business failure rate, timeout, dropped iterations | Hệ thống có xử lý đúng và duy trì được tải đã đặt không? |

Nên ghi thêm CPU, RSS/container working set, heap, GC pause, thread/connection pool và database utilization. Các chỉ số này giúp giải thích vì sao throughput hoặc latency thay đổi.

### 2.1. Throughput và RPS

**Throughput** là lượng công việc hoàn thành trong một đơn vị thời gian. Với API HTTP, thường dùng requests per second (RPS):

\[
\text{RPS} = \frac{\text{số request hoàn thành trong cửa sổ đo}}{\text{số giây của cửa sổ đo}}
\]

Phân biệt ba giá trị:

- **Offered load:** tốc độ load generator cố gắng bắt đầu request/iteration.
- **Completed throughput:** số request đã có response hoàn tất mỗi giây.
- **Successful throughput:** số request hoàn tất và thỏa điều kiện nghiệp vụ mỗi giây.

Nếu test đặt 100 iteration/s nhưng chỉ có 85 iteration/s được hoàn tất, hệ thống chưa chứng minh được khả năng phục vụ 100 request/s. Nếu mỗi iteration gửi một HTTP request, iteration rate gần tương ứng với request rate. Nếu một iteration gọi ba endpoint, request rate có thể gần gấp ba iteration rate.

Không lấy số request thành công chia cho tổng thời gian bao gồm warm-up, ramp-up hoặc thời gian dừng test nếu cửa sổ đo chỉ là steady-state. Hãy dùng đúng khoảng thời gian mà tải mục tiêu được giữ ổn định.

### 2.2. Latency và percentile

Latency là thời gian từ lúc client gửi request đến khi nhận được response theo định nghĩa metric đang dùng. Thay vì chỉ nhìn average, hãy xem phân phối:

| Phân vị | Cách đọc |
|---|---|
| p50 | 50% request có latency bằng hoặc thấp hơn giá trị này; gần với median |
| p90 | 90% request không chậm hơn giá trị này |
| p95 | 95% request không chậm hơn giá trị này; 5% còn lại chậm hơn |
| p99 | 99% request không chậm hơn giá trị này; 1% còn lại nằm ở tail |
| p99.9 | Quan sát phần đuôi rất nhỏ; cần lượng mẫu lớn hơn nhiều để diễn giải ổn định |

Ví dụ minh họa: p95 = 250 ms nghĩa là 95 trong 100 request có latency không quá 250 ms theo phân phối mẫu; khoảng 5% còn lại chậm hơn. Nếu p50 là 80 ms nhưng p99 là 1.8 s, phần lớn request nhanh nhưng một nhóm nhỏ người dùng vẫn phải chờ lâu.

Average có thể hữu ích để tính tổng chi phí xử lý, nhưng dễ bị kéo bởi outlier và không mô tả được tail. Không kết luận dịch vụ đạt SLO chỉ dựa trên average.

### 2.3. Phân vị cần đủ mẫu

p99 là điểm ở 1% cuối phân phối. Với 100 mẫu, vùng 1% cuối chỉ tương ứng khoảng một quan sát; con số p99 khi đó rất nhạy với từng request. Hãy tạo đủ hàng nghìn hoặc nhiều hơn request trong cửa sổ đo, tùy mức ổn định cần đạt, và báo cáo số mẫu đi kèm percentile.

Không cộng hoặc lấy trung bình số p95 của nhiều lần chạy rồi gọi kết quả đó là p95 tổng. Hãy giữ kết quả từng lần chạy; có thể báo cáo median và khoảng dao động của các p95 theo từng run. Nếu gộp raw samples, phải bảo đảm các run có cùng định nghĩa metric và cùng phân phối tải.

## 3. Chọn mô hình tải phù hợp

Load generator có thể điều khiển tải theo số virtual users (VU) hoặc theo tốc độ request/iteration đến hệ thống. Hai mô hình thường gặp là **closed model** và **open model**.

### 3.1. Closed model: số người dùng đồng thời cố định

Trong closed model, một VU chỉ bắt đầu iteration tiếp theo sau khi iteration trước hoàn tất. Nếu server chậm đi, VU chờ lâu hơn và tự giảm tốc độ gửi iteration mới.

Mô hình này phù hợp khi muốn mô phỏng một nhóm người dùng đồng thời thực hiện hành động có thời gian suy nghĩ (think time), ví dụ 200 nhân viên thao tác trên màn hình. Tuy nhiên, khi mục tiêu là kiểm tra dịch vụ chịu được một arrival rate cố định, closed model có thể làm tải giảm theo chính độ trễ của server. Hiện tượng này thường được gọi là **coordinated omission**.

### 3.2. Open model: tốc độ đến độc lập với thời gian response

Trong open model, iteration mới được lên lịch theo arrival rate đã cấu hình, không chờ iteration trước hoàn tất. Khi response chậm, hệ thống vẫn tiếp tục nhận các iteration mới cho tới khi giới hạn VU của load generator bị chạm.

Mô hình này phù hợp khi cần trả lời: “Dịch vụ có duy trì được 100 request/s trong 5 phút không?”. k6 hỗ trợ open model qua `constant-arrival-rate` và `ramping-arrival-rate`.

| Mục tiêu benchmark | Mô hình phù hợp |
|---|---|
| Giữ 100 iteration bắt đầu mỗi giây | Open model, `constant-arrival-rate` |
| Tăng từ 50 lên 200 iteration bắt đầu mỗi giây | Open model, `ramping-arrival-rate` |
| Mô phỏng 100 người dùng luôn hoạt động và chờ response trước hành động tiếp theo | Closed model, `constant-vus` |
| Mô phỏng phiên người dùng có think time | Closed model, VU cố định và sleep/think time có chủ đích |

Không có mô hình nào đúng cho mọi câu hỏi. Hãy chọn theo hành vi production cần mô phỏng và ghi rõ trong báo cáo.

## 4. Định nghĩa workload trước khi đo

“Cùng một tải thử nghiệm” nghĩa là hai phiên bản nhận cùng workload theo một hợp đồng được ghi lại. Cần cố định ít nhất:

1. **Request mix:** tỷ lệ GET/POST/PUT, endpoint, message type hoặc nghiệp vụ.
2. **Payload:** kích thước JSON, file upload, số record và kiểu dữ liệu.
3. **Danh tính:** cùng kiểu authentication, JWT claims/roles và tenant distribution.
4. **Dữ liệu:** cùng dataset, số lượng row, index, trạng thái transaction và mức cache.
5. **Arrival rate:** cùng lịch tăng tải và cùng tốc độ ở mỗi bước.
6. **Thời lượng:** cùng warm-up, ramp-up, steady-state window và cooldown.
7. **Kết nối:** cùng HTTP version, TLS, keep-alive, connection reuse và network path.
8. **Phụ thuộc:** cùng database, cache, message broker và service bên ngoài.

Ví dụ một workload API có thể gồm:

| Nhóm request | Tỷ trọng minh họa | Dữ liệu |
|---|---:|---|
| Đọc catalog | 60% | Cùng tập product ID |
| Đọc order | 20% | Cùng tập order ID và trạng thái |
| Tạo order | 15% | Payload và quy tắc idempotency giống nhau |
| Đọc báo cáo | 5% | Cùng filter và khoảng thời gian |

Các tỷ lệ chỉ là ví dụ. Hãy lấy request mix từ production telemetry hoặc use case đã xác định. Nếu một endpoint nặng bị bỏ khỏi benchmark, kết quả không đại diện cho workload thực tế.

### 4.1. Cố định dữ liệu và trạng thái hệ thống

Native và JVM cần bắt đầu từ trạng thái dữ liệu tương đương:

- Khôi phục cùng database snapshot hoặc seed dataset.
- Xóa/khôi phục các bản ghi do test tạo ra giữa các lần chạy.
- Quyết định rõ cache warm hay cache cold; không để một phiên bản được warm cache còn phiên bản kia không.
- Giữ nguyên index, schema, connection pool và database configuration.
- Dùng cùng JWT claims, user roles, tenant và quyền truy cập.
- Nếu test ghi dữ liệu, dùng ID duy nhất hoặc reset database để tránh lần chạy sau nhận workload khác.

Một bài test GET trên cache warm không thể so sánh công bằng với lần chạy phải query database. Cũng không nên để JVM được hưởng cache đã lấp đầy từ lần benchmark trước trong khi native bắt đầu với cache rỗng.

### 4.2. Cố định request sequence khi cần độ lặp cao

Nếu workload có nhiều loại request, hãy dùng cùng script và cùng file dữ liệu cho cả hai binary. Nếu cần tái lập chính xác từng chuỗi request, dùng một lịch request cố định hoặc dữ liệu có seed ổn định thay vì để hai lần chạy tự chọn các input ngẫu nhiên khác nhau.

Khi chỉ dùng tỷ trọng ngẫu nhiên, hai lần chạy có thể có số lượng request mỗi loại hơi khác nhau. Điều đó vẫn có thể dùng cho benchmark tổng quan nếu tỷ lệ đủ lớn và dao động nhỏ, nhưng nên đo latency theo từng endpoint/tag để phát hiện sai lệch.

## 5. Giữ môi trường JVM và Native Image tương đương

Khác biệt runtime là một phần của phép so sánh; khác biệt môi trường ngoài ý muốn sẽ làm sai kết luận. Ghi lại các thông tin sau cho từng run:

| Thành phần | Điều cần giữ giống hoặc ghi lại |
|---|---|
| Host | Cùng loại CPU, số core, kiến trúc, kernel và máy chạy load generator |
| Container | Cùng CPU quota, memory limit, số replica và network mode |
| Ứng dụng | Cùng commit, Spring Boot/Spring Framework version, dependency và endpoint logic |
| Database/cache | Cùng phiên bản, cấu hình, dataset và vị trí mạng |
| Connection pool | Cùng min/max pool size, timeout và connection reuse |
| HTTP | Cùng HTTP/1.1 hoặc HTTP/2, TLS, keep-alive và payload |
| Security | Cùng auth flow, token validation, claim mapping và authorization rules |
| Runtime tuning | Ghi rõ JVM heap/GC flags và Native Image GC/heap/build options |

Đặt load generator trên máy riêng hoặc xác nhận máy đó còn đủ CPU/network. Nếu k6 dùng hết CPU hoặc băng thông, kết quả sẽ phản ánh giới hạn của load generator thay vì ứng dụng.

### 5.1. So sánh CPU và memory đúng cách

Không chỉ so sánh Java heap với Native Image heap. RSS/container working set còn gồm code, metaspace/code cache (JVM), native allocations, thread stacks, runtime và các vùng bộ nhớ khác. Native Image và HotSpot có cách tổ chức memory khác nhau.

Nên thu thập:

- Container memory working set/RSS và peak RSS.
- Heap used/committed và GC metrics từ runtime tương ứng.
- CPU usage theo container và theo host.
- GC count, pause time và allocation rate nếu có.
- Thread count, connection pool usage và queue depth.

Đặt cùng memory limit và CPU quota để so sánh hành vi dưới cùng ngân sách tài nguyên. Các tuning flags riêng của JVM hoặc Native Image có thể khác nhau; ghi lại chúng thay vì giả vờ rằng hai runtime dùng cùng một cấu hình nội bộ.

## 6. Warm-up và steady-state

JVM HotSpot cần thời gian để JIT biên dịch các method nóng. Native Image đã biên dịch code trước khi chạy và không có cùng quá trình HotSpot JIT, nhưng vẫn có thể có biến động khi ứng dụng tạo connection pool, tải cache, khởi tạo client, nạp dữ liệu và làm nóng database/cache.

Vì vậy, hãy tách hai câu hỏi:

- **Cold start:** từ lúc process được khởi chạy đến khi ứng dụng sẵn sàng nhận traffic.
- **Steady-state performance:** throughput, latency và resource usage sau khi ứng dụng đã ổn định.

Không gộp startup time vào latency của request steady-state. Cũng không đo JVM ngay sau khi start rồi so với native đã chạy ổn định.

### Quy trình warm-up đề xuất

1. Khởi động binary và chờ readiness probe thành công.
2. Gửi một workload warm-up đã định trước, giống nhau cho hai runtime.
3. Không đưa dữ liệu warm-up vào cửa sổ đo steady-state.
4. Bắt đầu cửa sổ đo sau khi latency, CPU và connection pool ổn định.
5. Giữ tải mục tiêu trong cùng thời lượng, ví dụ 5 phút.
6. Thu thập metrics và lưu log của cả ứng dụng lẫn load generator.

Một cấu hình thử nghiệm có thể dùng 60–120 giây warm-up, sau đó 5 phút steady-state; thời lượng thực tế phụ thuộc ứng dụng và thời gian ổn định. Nếu có nhiều cache hoặc tác vụ nền, cần xác định rõ lúc nào hệ thống được coi là ổn định.

## 7. Tạo k6 script với constant arrival rate

Ví dụ sau tạo 100 iteration mỗi giây trong 5 phút. Mỗi iteration gửi đúng một HTTP request GET, do đó arrival rate được cấu hình gần với offered request rate.

~~~javascript
import http from 'k6/http';
import { check } from 'k6';
import { Counter, Rate } from 'k6/metrics';

const baseUrl = __ENV.BASE_URL || 'http://127.0.0.1:8080';
const successfulRequests = new Counter('successful_requests');
const businessSuccess = new Rate('business_success');

export const options = {
  discardResponseBodies: true,
  scenarios: {
    steady_load: {
      executor: 'constant-arrival-rate',
      rate: 100,
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 80,
      maxVUs: 300,
    },
  },
  thresholds: {
    http_req_duration: ['p(95)<250', 'p(99)<750'],
    http_req_failed: ['rate<0.01'],
    business_success: ['rate>0.99'],
    dropped_iterations: ['count==0'],
  },
  summaryTrendStats: ['avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
};

export default function () {
  const response = http.get(baseUrl + '/api/catalog', {
    tags: { name: 'GET /api/catalog' },
  });

  const ok = check(response, {
    'status is 200': (res) => res.status === 200,
  });

  businessSuccess.add(ok);
  if (ok) {
    successfulRequests.add(1);
  }
}
~~~

Các ngưỡng p95, p99 và success rate trong ví dụ chỉ là giá trị minh họa. Thay bằng SLO của dịch vụ. `discardResponseBodies` giảm chi phí giữ response body khi test chỉ cần status; nếu cần kiểm tra payload, bỏ tùy chọn này hoặc bật lại body cho request tương ứng.

Chạy trên Linux/macOS:

~~~bash
BASE_URL=http://127.0.0.1:8080 k6 run benchmark.js
~~~

Trên PowerShell:

~~~powershell
$env:BASE_URL = "http://127.0.0.1:8080"
k6 run benchmark.js
~~~

Để so sánh, chạy cùng file script lần lượt với base URL hoặc port của JVM và native. Giữ nguyên rate, duration, thresholds, data và môi trường phụ thuộc.

### 7.1. Hiểu cấu hình arrival rate

| Tùy chọn | Ý nghĩa |
|---|---|
| `rate` | Số iteration cần bắt đầu trong mỗi `timeUnit` |
| `timeUnit` | Khoảng thời gian dùng để tính rate |
| `duration` | Thời gian duy trì arrival rate |
| `preAllocatedVUs` | Số VU được chuẩn bị trước khi chạy |
| `maxVUs` | Giới hạn VU tối đa k6 được phép cấp phát |

Với một iteration chứa một request, `rate: 100` và `timeUnit: '1s'` nghĩa là k6 cố bắt đầu khoảng 100 iteration/request mỗi giây. Tốc độ thực tế có thể thấp hơn nếu không đủ VU để chạy iteration hoặc load generator bị giới hạn.

Không thêm `sleep()` ở cuối iteration khi dùng arrival-rate executor. Executor đã điều tiết tốc độ bắt đầu iteration theo `rate` và `timeUnit`.

## 8. Đảm bảo load generator đủ VU

Một iteration cần một VU đang rảnh. Khi request chậm hơn, nhiều iteration cùng tồn tại và cần nhiều VU hơn để duy trì arrival rate.

Ước lượng ban đầu:

\[
\text{VU cần thiết} \approx \text{arrival rate} \times \text{thời gian iteration (giây)}
\]

Ví dụ, 100 iteration/s và thời gian iteration khoảng 0.2 giây cần xấp xỉ 20 VU đang hoạt động, cộng thêm biên cho biến động. Đây chỉ là ước lượng; hãy kiểm tra số VU thực tế và `dropped_iterations`.

Nếu không có VU rảnh, k6 không thể bắt đầu iteration đúng lịch và tăng metric `dropped_iterations`. Nguyên nhân có thể là:

- `preAllocatedVUs` hoặc `maxVUs` quá thấp.
- Iteration dài lên do SUT chậm.
- Load generator thiếu CPU hoặc memory để chạy thêm VU.
- Test script làm nhiều việc cục bộ ngoài HTTP request.

Tăng VU chỉ giải quyết thiếu capacity ở load generator. Nếu SUT đã bão hòa, tăng `maxVUs` có thể làm tải dồn lên server và latency/error tăng mạnh; cần ghi nhận đây là kết quả của bài stress test.

Một run dùng để so sánh phải có `dropped_iterations` bằng 0 hoặc nằm trong error budget đã định. Nếu một bản có nhiều dropped iterations, không thể coi hai bản đã nhận cùng offered load.

## 9. Đọc các metric HTTP của k6

k6 cung cấp các metric mặc định:

| Metric | Ý nghĩa |
|---|---|
| `http_reqs` | Tổng số HTTP request được thực hiện |
| `http_req_duration` | Thời gian gửi + chờ response + nhận response body |
| `http_req_waiting` | Thời gian chờ response, thường dùng làm TTFB |
| `http_req_connecting` | Thời gian thiết lập TCP connection |
| `http_req_tls_handshaking` | Thời gian TLS handshake |
| `http_req_blocked` | Thời gian chờ slot connection trước khi gửi |
| `http_req_failed` | Tỷ lệ request bị đánh dấu thất bại |
| `dropped_iterations` | Số iteration không thể bắt đầu đúng lịch |

`http_req_duration` không bao gồm DNS lookup, thời gian chờ slot connection, TCP connect hoặc TLS handshake ban đầu. Các pha đó có metric riêng. Vì thế:

- Dùng `http_req_duration` để so sánh thời gian request ở phía server/response path trong điều kiện connection đã được thiết lập.
- Dùng `http_req_waiting` để quan sát thời gian tới byte đầu tiên (TTFB).
- Xem `http_req_connecting` và `http_req_tls_handshaking` nếu benchmark bao gồm kết nối mới hoặc TLS setup.
- Giữ cùng keep-alive/connection reuse nếu muốn tập trung vào chi phí xử lý request.

Metric `http_req_failed` phản ánh quy tắc response callback của k6; nó không biết mọi lỗi nghiệp vụ. Ví dụ HTTP 200 nhưng response chứa business status REJECTED có thể vẫn được coi là HTTP thành công. Dùng `check()` và custom `Rate`/`Counter` để đo business success riêng.

## 10. Đo request mix thay vì chỉ một endpoint

Script ở trên là ví dụ một endpoint. Với benchmark đại diện, hãy mở rộng cùng một script để gọi đúng request mix đã xác định. Có thể dùng `group()` để tách metric theo luồng hoặc tag request bằng tên ổn định:

Đoạn mã dưới đây là phần minh họa bổ sung cho script trước và dùng lại biến `baseUrl` đã khai báo ở đó.

~~~javascript
import { group } from 'k6';
import http from 'k6/http';

export default function () {
  group('catalog-read', () => {
    http.get(baseUrl + '/api/catalog', {
      tags: { name: 'GET /api/catalog' },
    });
  });

  group('order-read', () => {
    http.get(baseUrl + '/api/orders/ORDER-100', {
      tags: { name: 'GET /api/orders/{id}' },
    });
  });
}
~~~

Đây chỉ minh họa cách nhóm và đặt tên metric; khi dùng trong test thật, hãy điều chỉnh số lần gọi/tỷ lệ để khớp workload đã định. Nếu mỗi iteration gọi hai endpoint, `rate` là số workflow bắt đầu mỗi giây, không phải số HTTP request mỗi giây.

Luôn xem percentile theo endpoint hoặc nhóm nghiệp vụ. p95 tổng hợp của một workload có thể bị chi phối bởi endpoint chiếm đa số và che khuất endpoint hiếm nhưng rất chậm.

## 11. Xác định cửa sổ đo và lặp lại benchmark

Một quy trình steady-state có thể thực hiện như sau:

1. Khởi động database, cache, message broker và các dependency.
2. Khởi động đúng một phiên bản ứng dụng; đợi readiness.
3. Chạy warm-up workload với rate và request mix đã định.
4. Bắt đầu cửa sổ đo cố định, ví dụ 5 phút ở 100 iteration/s.
5. Lưu k6 summary, metrics time series, application metrics và container metrics.
6. Dừng ứng dụng, reset dữ liệu nếu test có ghi.
7. Chạy phiên bản còn lại với cùng điều kiện.
8. Lặp lại mỗi phiên bản nhiều lần; đổi thứ tự JVM/native giữa các lượt để giảm ảnh hưởng do thời điểm chạy.

Không chạy đồng thời JVM và native trên cùng host nếu chúng tranh CPU, memory hoặc database connection mà mục tiêu là so sánh từng binary riêng. Nếu cần kiểm tra capacity của cả hai service khi chạy song song, đó là một workload khác và phải được báo cáo riêng.

### Số lần chạy

Một lần chạy có thể bị ảnh hưởng bởi nhiễu hệ thống, GC, background jobs hoặc network. Nên có ít nhất vài lần lặp ổn định; lưu từng run và báo cáo median/range của throughput, p95, p99 và error rate.

Nếu các lần chạy dao động mạnh, tìm nguyên nhân trước khi kết luận. Đừng loại một run chỉ vì nó cho kết quả không thuận lợi; chỉ loại khi có lý do kỹ thuật được ghi nhận như load generator lỗi, dependency restart hoặc test bị gián đoạn.

## 12. Lập bảng kết quả JVM và Native Image

Dùng một bảng thống nhất cho từng run:

| Chỉ số | Spring Boot JVM | Spring Boot Native | Điều kiện |
|---|---:|---:|---|
| Offered load (iteration/s) | Ghi kết quả | Ghi kết quả | Cùng rate |
| Completed HTTP RPS | Ghi kết quả | Ghi kết quả | Cùng cửa sổ đo |
| Successful RPS | Ghi kết quả | Ghi kết quả | Cùng business checks |
| p50 latency | Ghi kết quả | Ghi kết quả | Cùng metric/endpoint |
| p95 latency | Ghi kết quả | Ghi kết quả | Cùng metric/endpoint |
| p99 latency | Ghi kết quả | Ghi kết quả | Cùng metric/endpoint |
| HTTP failure rate | Ghi kết quả | Ghi kết quả | Cùng response rules |
| Dropped iterations | Ghi kết quả | Ghi kết quả | Nên bằng 0 |
| CPU trung bình/peak | Ghi kết quả | Ghi kết quả | Cùng CPU quota |
| RSS/working set peak | Ghi kết quả | Ghi kết quả | Cùng memory limit |

Khi báo cáo, luôn ghi thêm:

- Số request/sample trong cửa sổ đo.
- Phiên bản code, Spring Boot, JDK/GraalVM và build flags.
- Kích thước container, CPU/memory limit và số replica.
- Database/cache version, dataset và trạng thái cache.
- k6 version, script revision, rate, duration và VU allocation.
- Các lần chạy bị loại cùng lý do.

### Ví dụ cách diễn giải

Giả sử hai bản đều nhận đủ 100 request/s và không có dropped iterations:

- Native có p50 thấp hơn nhưng p99 cao hơn: phần lớn request nhanh hơn, nhưng tail có thể xấu hơn; cần xem GC, queueing, database hoặc outlier.
- Native có p95 thấp hơn nhưng successful RPS thấp hơn: latency của request hoàn tất tốt hơn, nhưng có thể có nhiều request lỗi hoặc không hoàn tất; chưa thể kết luận tốt hơn.
- Native dùng ít RSS hơn nhưng CPU cao hơn: có thể giảm memory footprint nhưng tăng chi phí CPU; cần xem mục tiêu triển khai và ngân sách tài nguyên.
- JVM có p99 tăng mạnh khi CPU đạt giới hạn: có thể đã vào vùng saturation; cần kiểm tra thread pool, queue, GC và dependency.

Không kết luận một runtime thắng toàn diện nếu chỉ một chỉ số tốt hơn.

## 13. Tìm điểm bão hòa và mức throughput bền vững

Benchmark không chỉ nên đo một rate duy nhất. Hãy tăng tải theo từng nấc, ví dụ 25, 50, 75, 100, 125 và 150 iteration/s; giữ cùng request mix và cùng thời lượng mỗi nấc.

Ở mỗi nấc, ghi:

- Offered arrival rate và completed/successful RPS.
- p50, p95, p99.
- Error rate và dropped iterations.
- CPU, RSS, GC, queue depth và database utilization.

Điểm bão hòa thường xuất hiện khi tăng offered load nhưng completed throughput gần như không tăng, trong khi latency tail, lỗi hoặc queue tăng nhanh. Mức **sustainable throughput** là mức tải cao nhất vẫn giữ được SLO và error budget trong cửa sổ đo đủ dài.

~~~mermaid
flowchart LR
    A["Tăng offered load"] --> B["Throughput tăng"]
    B --> C["Đạt vùng saturation"]
    C --> D["Throughput gần như đứng"]
    D --> E["p95/p99 và error tăng"]
    E --> F["Xác định sustainable rate dưới SLO"]
~~~

Không dùng rate cao nhất mà server từng trả được trong vài giây làm capacity production. Capacity cần duy trì được trong khoảng thời gian đại diện và còn headroom cho traffic burst, background jobs và biến động dependency.

## 14. Tách startup benchmark khỏi throughput benchmark

Startup time và steady-state throughput là hai bài đo khác nhau:

| Bài đo | Điểm bắt đầu/kết thúc | Điều cần kiểm soát |
|---|---|---|
| Cold startup | Process start đến readiness/health endpoint sẵn sàng | Process mới, dependency sẵn sàng, cùng readiness definition |
| First request | Request đầu tiên đến response đầu tiên | Cache, connection và lazy initialization |
| Steady-state throughput | Sau warm-up, trong cửa sổ tải ổn định | Cùng offered load, request mix và thời lượng |
| Memory steady-state | Sau warm-up và trong cửa sổ ổn định | RSS/working set, heap và GC |

Đo cold startup bằng nhiều lần khởi động process mới. Không dùng một lần startup rồi khẳng định kết quả ổn định. Với JVM, phân biệt thời gian app ready với thời gian JIT warm-up; với native, phân biệt app ready với thời gian cache/connection ổn định.

## 15. PGO và các runtime tuning là biến thể riêng

Native Image hỗ trợ Profile-Guided Optimization (PGO). PGO dùng profile thu từ workload đại diện để hướng dẫn compiler tối ưu code khi build. Đây có thể là một biến thể hữu ích nếu mục tiêu là throughput, nhưng profile phải được tạo từ workload phù hợp và được quản lý như một phần của build.

Khi đánh giá:

1. Đo native binary mặc định trước.
2. Nếu thử PGO, tạo profile bằng workload đại diện với request mix tương tự production.
3. Build binary PGO riêng và ghi rõ profile/build flags.
4. Chạy lại đúng benchmark đã dùng cho JVM và native mặc định.
5. Báo cáo PGO như một biến thể riêng, không gộp với kết quả native mặc định.

Tương tự, nếu thay GC, heap maximum, optimization level, CPU architecture target (`-march`) hoặc container resource limit, hãy tạo một cấu hình benchmark riêng. Những thay đổi này có thể cải thiện một chỉ số nhưng làm thay đổi memory, latency tail hoặc tính tương thích phần cứng.

## 16. Những lỗi làm benchmark mất giá trị

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| So sánh hai request mix khác nhau | Throughput/latency không còn tương đương | Dùng cùng script, data và tỷ trọng endpoint |
| Chỉ nhìn average latency | Bỏ qua tail latency | Báo p50, p95, p99 và sample count |
| Dùng closed model để khẳng định fixed RPS | Arrival rate giảm khi server chậm | Dùng open model cho fixed arrival rate |
| Không theo dõi dropped iterations | Tưởng đã gửi đủ tải dù load generator bỏ iteration | Đặt threshold và kiểm tra metric |
| Load generator hết CPU | Đo giới hạn của client thay vì server | Tách load generator và giám sát tài nguyên |
| JVM đo ngay sau start, native đo sau warm-up | JVM bị bất lợi do JIT/cache | Warm-up hai bên theo cùng quy tắc |
| Cache/database state khác nhau | Kết quả phụ thuộc trạng thái dữ liệu | Reset/seed và quy định warm/cold cache |
| Một bản có nhiều request lỗi hơn | Latency mẫu có thể chỉ còn các request thành công | Báo error rate và successful throughput |
| Gộp mọi endpoint vào một percentile | Endpoint hiếm nhưng chậm bị che khuất | Tag và phân tích theo endpoint |
| Chỉ chạy một lần | Nhiễu hệ thống quyết định kết quả | Lặp lại, lưu từng run và báo dao động |
| Thay flags giữa hai binary mà không ghi nhận | Không biết khác biệt đến từ runtime hay tuning | Ghi rõ build/runtime configuration |

## 17. Quy trình benchmark có thể lặp lại

~~~mermaid
flowchart TD
    A["Chọn SLO và câu hỏi benchmark"] --> B["Định nghĩa request mix + dataset"]
    B --> C["Cố định host/container/dependencies"]
    C --> D["Build JVM và Native từ cùng code"]
    D --> E["Khởi động và warm-up"]
    E --> F["Chạy open-load ở rate cố định"]
    F --> G["Thu throughput, percentiles, errors, CPU, RSS"]
    G --> H["Lặp lại và đổi thứ tự runtime"]
    H --> I["Tăng rate để tìm saturation"]
    I --> J["Phân tích sustainable throughput"]
    J --> K["Lưu script, config và báo cáo"]
~~~

Checklist:

- [ ] Xác định SLO cho p95/p99, error rate và throughput.
- [ ] Xác định request mix, payload, authentication và dataset.
- [ ] Chọn open/closed model theo mục tiêu đo.
- [ ] Dùng cùng k6 script và cùng request data cho JVM/native.
- [ ] Tách load generator khỏi máy chạy ứng dụng.
- [ ] Cố định CPU/memory quota, replicas và dependency versions.
- [ ] Quy định warm-up và steady-state window trước khi chạy.
- [ ] Theo dõi `http_req_duration`, `http_req_waiting`, `http_req_failed`.
- [ ] Theo dõi `http_reqs`, successful RPS và `dropped_iterations`.
- [ ] Thu thập CPU, RSS/container memory, GC và queue/pool metrics.
- [ ] Lặp lại benchmark nhiều lần và lưu từng run.
- [ ] Phân tích latency theo endpoint, không chỉ percentile tổng.
- [ ] Tăng tải từng nấc để tìm saturation và sustainable throughput.
- [ ] Ghi mọi build flag, GC setting và PGO variant.

## 18. Bài tập tự kiểm tra

**Câu 1.** p95 = 300 ms có nghĩa gì?

**Gợi ý:** khoảng 95% request trong tập mẫu có latency không quá 300 ms; 5% còn lại chậm hơn.

**Câu 2.** Vì sao average latency không đủ để đánh giá trải nghiệm người dùng?

**Gợi ý:** average không mô tả phần đuôi; một nhóm request rất chậm có thể bị che khuất.

**Câu 3.** Khi cần giữ offered load ở 100 request/s, vì sao nên cân nhắc `constant-arrival-rate`?

**Gợi ý:** đây là open model, iteration start độc lập với thời gian response của iteration trước.

**Câu 4.** `dropped_iterations` khác `http_req_failed` thế nào?

**Gợi ý:** dropped iteration chưa bắt đầu do thiếu VU/không đủ khả năng lập lịch; failed request là request đã chạy nhưng bị đánh dấu thất bại.

**Câu 5.** Vì sao không thể so sánh JVM chạy ngay sau startup với native đã warm-up?

**Gợi ý:** JVM có JIT warm-up; cả hai runtime còn có cache, connection và initialization ảnh hưởng kết quả.

**Câu 6.** Nếu p50 native tốt hơn nhưng p99 tệ hơn, cần xem thêm gì?

**Gợi ý:** queueing, CPU saturation, GC, database latency, thread/connection pools và phân phối theo endpoint.

**Câu 7.** Vì sao cần đo successful RPS bên cạnh `http_reqs`?

**Gợi ý:** request count có thể gồm response lỗi hoặc business rejection; successful RPS thể hiện throughput hữu ích.

## 19. Tài liệu tham khảo

- [Grafana k6 — Open and closed models](https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/open-vs-closed/): khác biệt giữa closed model và open model, cùng hiện tượng coordinated omission.
- [Grafana k6 — Constant arrival rate](https://grafana.com/docs/k6/latest/using-k6/scenarios/executors/constant-arrival-rate/): cấu hình arrival rate, duration và VU allocation.
- [Grafana k6 — Dropped iterations](https://grafana.com/docs/k6/latest/using-k6/scenarios/concepts/dropped-iterations/): nguyên nhân và cách diễn giải `dropped_iterations`.
- [Grafana k6 — Built-in metrics](https://grafana.com/docs/k6/latest/using-k6/metrics/reference/): `http_req_duration`, `http_req_waiting`, `http_reqs`, errors và các metric khác.
- [Grafana k6 — Thresholds](https://grafana.com/docs/k6/latest/using-k6/thresholds/): điều kiện p95/p99 và cách làm test pass/fail.
- [GraalVM Native Image — Optimizations and Performance](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/): optimization levels, PGO và các lựa chọn tối ưu throughput.
- [GraalVM Native Image — Memory Management](https://www.graalvm.org/latest/reference-manual/native-image/optimizations-and-performance/MemoryManagement/): heap và garbage collector trong Native Image.

**Ghi nhớ:** Một phép so sánh JVM/native có giá trị khi cả hai nhận cùng workload, cùng dữ liệu và cùng ngân sách tài nguyên. Hãy báo cáo throughput, successful RPS, p50/p95/p99, lỗi và dropped iterations cùng nhau; tách startup khỏi steady-state; lặp lại nhiều lần và tìm mức tải cao nhất vẫn đáp ứng SLO thay vì chọn một con số latency đẹp nhất.
