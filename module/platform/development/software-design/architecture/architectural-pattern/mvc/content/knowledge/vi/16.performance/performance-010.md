# Kiểm thử tải và xác định điểm nghẽn thực tế

Trong module **MODEL_VIEW_CONTROLLER**, một request thường đi qua nhiều thành phần: bộ lọc bảo mật, định tuyến, Controller, tầng ứng dụng, Model, repository, cơ sở dữ liệu và View. Một trang có thể chạy nhanh khi chỉ có một người dùng nhưng chậm rõ rệt khi nhiều người cùng truy cập. Nguyên nhân có thể nằm ở truy vấn dữ liệu, pool kết nối, thread xử lý request, gọi dịch vụ ngoài, render template hoặc cách ứng dụng giữ trạng thái.

**Kiểm thử tải (load testing)** giúp đo hành vi của ứng dụng dưới một mức tải xác định. Mục tiêu không chỉ là biết hệ thống chịu được bao nhiêu request, mà còn xác định ở mức tải nào độ trễ tăng, lỗi xuất hiện và tài nguyên bị bão hòa. Kết hợp kết quả kiểm thử với số liệu giám sát và profiling sẽ giúp tìm điểm nghẽn thực tế, sau đó xác minh việc tối ưu có cải thiện đúng vấn đề hay không.

## 1. Kiểm thử tải giải quyết câu hỏi nào?

Kiểm thử tải tạo ra lưu lượng gần với cách người dùng thật tương tác và quan sát hệ thống phản hồi. Nó giúp trả lời các câu hỏi:

- Ứng dụng đáp ứng ra sao ở tải sử dụng bình thường và tải cao điểm?
- Bao nhiêu người dùng đồng thời hoặc bao nhiêu request mỗi giây vẫn đáp ứng mục tiêu dịch vụ?
- Endpoint nào có độ trễ cao hoặc tỷ lệ lỗi tăng nhanh?
- Tài nguyên nào chạm giới hạn trước: CPU, heap, thread, connection pool, database hay dịch vụ ngoài?
- Khi tăng tải, độ trễ tăng đều hay đột ngột do một giới hạn cụ thể?
- Sau khi giảm tải, hệ thống có phục hồi hay vẫn còn hàng đợi, bộ nhớ hoặc kết nối bị chiếm?
- Một thay đổi về code, truy vấn hoặc cấu hình có thực sự cải thiện kết quả không?

Kiểm thử tải khác với việc chỉ gửi nhiều request thật nhanh. Một bài kiểm thử có ích phải có mục tiêu, kịch bản, dữ liệu và điều kiện thành công rõ ràng. Nếu chỉ tạo lưu lượng ngẫu nhiên, kết quả có thể không phản ánh đường đi quan trọng trong ứng dụng MVC.

## 2. Phân biệt các loại kiểm thử hiệu năng

| Loại kiểm thử | Mục đích | Ví dụ |
| --- | --- | --- |
| **Load test** | Đo hệ thống ở mức tải dự kiến | Duy trì 300 người dùng ảo trong 20 phút |
| **Stress test** | Tăng tải vượt mức dự kiến để tìm giới hạn và cách hệ thống suy giảm | Tăng dần số người dùng đến khi độ trễ hoặc lỗi vượt ngưỡng |
| **Spike test** | Kiểm tra phản ứng với mức tăng tải đột ngột | Lưu lượng tăng gấp 5 lần trong thời gian ngắn |
| **Soak/endurance test** | Phát hiện vấn đề chỉ xuất hiện khi chạy lâu | Duy trì tải ổn định vài giờ để quan sát memory leak hoặc pool cạn |
| **Capacity test** | Xác định năng lực tối đa trong điều kiện và tiêu chí đã chọn | Tìm thông lượng cao nhất vẫn đạt SLA |
| **Scalability test** | Đo khả năng cải thiện khi tăng tài nguyên hoặc số instance | So sánh 2, 4 và 8 instance ứng dụng |

Các loại kiểm thử có thể dùng chung kịch bản nhưng trả lời những câu hỏi khác nhau. Không nên gọi một bài chạy ngắn ở tải cao là soak test, hoặc dùng kết quả stress test để tuyên bố hệ thống đáp ứng tải sản xuất bình thường.

## 3. Xác định mục tiêu và tiêu chí đạt

Trước khi tạo tải, cần xác định điều gì được xem là thành công. Một mục tiêu có thể bao gồm:

- Tải dự kiến: số người dùng đồng thời, số phiên hoạt động hoặc request mỗi giây.
- Phân bố thao tác: tỷ lệ xem danh sách, xem chi tiết, tìm kiếm, gửi biểu mẫu và cập nhật dữ liệu.
- Mục tiêu độ trễ: ví dụ p95 của endpoint quan trọng không vượt quá 500 ms trong điều kiện đã xác định.
- Mục tiêu lỗi: tỷ lệ lỗi HTTP và lỗi nghiệp vụ không vượt quá ngưỡng đã thống nhất.
- Mục tiêu tài nguyên: CPU, heap, pool kết nối và database vẫn còn khoảng dự phòng.
- Thời gian duy trì: đủ lâu để hệ thống đạt trạng thái ổn định và bộc lộ vấn đề tích lũy.

Ví dụ mục tiêu minh họa:

| Chỉ số | Mục tiêu thử nghiệm |
| --- | --- |
| Người dùng ảo | 250 |
| Thời gian duy trì tải | 20 phút sau giai đoạn tăng tải |
| p95 của GET /products | Dưới 400 ms |
| p95 của GET /orders/{id} | Dưới 600 ms |
| Tỷ lệ lỗi kỹ thuật | Dưới 1% |
| CPU ứng dụng | Trung bình dưới 75%, không duy trì bão hòa |
| Connection pool | Không cạn, không có timeout lấy kết nối |

Đây chỉ là ví dụ để minh họa cách đặt tiêu chí, không phải chuẩn chung cho mọi ứng dụng. Mục tiêu thực tế cần xuất phát từ yêu cầu sản phẩm, hành vi người dùng, năng lực hạ tầng và thỏa thuận mức dịch vụ.

## 4. Xây dựng kịch bản tải giống người dùng thật

Ứng dụng MVC có nhiều đường đi khác nhau. Một trang danh sách có thể chỉ đọc dữ liệu và render template; một thao tác tạo đơn có thể xác thực, kiểm tra tồn kho, ghi database và phát thông báo. Nếu chỉ kiểm thử một endpoint nhẹ, ta không biết hệ thống chịu tải ra sao ở những luồng nghiệp vụ quan trọng.

Một kịch bản tổng hợp có thể gồm:

1. Người dùng mở trang đăng nhập hoặc lấy token qua cơ chế xác thực dành cho kiểm thử.
2. Xem danh sách sản phẩm có phân trang.
3. Tìm kiếm theo từ khóa và bộ lọc.
4. Mở trang chi tiết sản phẩm hoặc đơn hàng.
5. Gửi biểu mẫu tạo đơn với dữ liệu hợp lệ.
6. Xem lịch sử đơn hàng và trạng thái.
7. Một tỷ lệ nhỏ người dùng thực hiện cập nhật hoặc hủy theo quy tắc nghiệp vụ.

Không phải mọi người dùng đều thực hiện tất cả thao tác theo cùng thứ tự. Hãy xác định tỷ lệ thao tác dựa trên log, analytics hoặc giả định đã được chủ sản phẩm xác nhận. Kịch bản cần có think time hoặc khoảng nghỉ hợp lý để tránh mô hình hóa người dùng như máy gửi request liên tục không có thời gian đọc trang.

Ví dụ phân bố tải:

| Thao tác | Tỷ lệ request giả định |
| --- | ---: |
| Xem danh sách | 40% |
| Tìm kiếm và lọc | 20% |
| Xem chi tiết | 25% |
| Gửi biểu mẫu tạo/cập nhật | 10% |
| Xem trạng thái hoặc lịch sử | 5% |

Các tỷ lệ trên chỉ là dữ liệu mẫu. Nếu luồng thực tế có bước xác thực, CSRF token, cookie session hoặc dữ liệu phụ thuộc request trước, script kiểm thử phải mô phỏng đúng chuỗi tương tác. Một request POST thiếu token hoặc payload không hợp lệ có thể bị từ chối sớm và tạo ra kết quả tải không đại diện cho nghiệp vụ.

## 5. Mô hình hóa người dùng đồng thời và tốc độ gửi request

Hai cách mô hình hóa tải phổ biến:

- **Virtual users (VUs):** mô phỏng một số người dùng ảo thực hiện chuỗi hành động. Mỗi người dùng có thể chờ giữa các thao tác.
- **Arrival rate / request rate:** xác định số lượt bắt đầu hoặc số request được tạo trong một đơn vị thời gian, phù hợp khi muốn kiểm soát thông lượng đầu vào.

Số người dùng đồng thời không giống số request mỗi giây. Theo định luật Little, trong trạng thái ổn định, số request đang ở trong hệ thống xấp xỉ thông lượng nhân với thời gian phản hồi trung bình:


Công thức được viết là:

\[
L = \lambda W
\]

Trong đó:

- \(L\) là số request trung bình đang được xử lý hoặc chờ.
- \(\lambda\) là thông lượng, tính bằng request mỗi giây.
- \(W\) là thời gian trung bình trong hệ thống, tính bằng giây.


Ví dụ, nếu ứng dụng xử lý trung bình 80 request/giây và mỗi request mất 0,5 giây, số request đang ở trong hệ thống xấp xỉ 40. Khi thời gian phản hồi tăng, số request tồn đọng có thể tăng theo ngay cả khi tốc độ gửi không đổi.

Vì vậy, báo cáo cần ghi cả mô hình tải, thông lượng thực đạt và độ trễ. Chỉ ghi “đã chạy 500 người dùng” là chưa đủ để so sánh hai lần kiểm thử.

## 6. Các chỉ số cần theo dõi

### Latency và percentile

Độ trễ (latency) là thời gian từ khi client bắt đầu request đến khi nhận được response. Không nên chỉ nhìn giá trị trung bình vì một nhóm request rất chậm có thể bị che khuất.

| Chỉ số | Ý nghĩa |
| --- | --- |
| p50 | Một nửa request hoàn thành trong thời gian này hoặc nhanh hơn |
| p90 | 90% request hoàn thành trong thời gian này hoặc nhanh hơn |
| p95 | 95% request hoàn thành trong thời gian này hoặc nhanh hơn |
| p99 | 99% request hoàn thành trong thời gian này hoặc nhanh hơn |
| Max | Request chậm nhất quan sát được; nhạy với ngoại lệ và kích thước mẫu |

Ví dụ p95 = 700 ms nghĩa là 95% request trong tập đo hoàn thành trong 700 ms hoặc nhanh hơn; 5% còn lại chậm hơn. p99 hữu ích để phát hiện tail latency, nhưng cần đủ số mẫu và hiểu cách công cụ tính percentile.

### Throughput và tỷ lệ lỗi

- **Throughput:** số request hoặc giao dịch hoàn thành trong một đơn vị thời gian.
- **Error rate:** tỷ lệ request thất bại theo định nghĩa của bài kiểm thử.
- **Apdex:** chỉ số tổng hợp mức hài lòng dựa trên ngưỡng thời gian phản hồi, nếu tổ chức sử dụng.
- **Business success rate:** tỷ lệ thao tác nghiệp vụ thực sự thành công, không chỉ HTTP status là 2xx.

Một endpoint có thể trả HTTP 200 nhưng chứa lỗi nghiệp vụ trong body, hoặc trả 302/303 là hành vi bình thường cho form HTML. Vì vậy, cần phân biệt lỗi kỹ thuật, lỗi nghiệp vụ dự kiến và response thành công theo hợp đồng của từng endpoint.

### Tài nguyên hệ thống

Theo dõi đồng thời:

- CPU, load average và mức sử dụng bộ nhớ.
- Heap, non-heap, garbage collection và số lần pause.
- Số thread đang hoạt động, thread bị block và hàng đợi executor.
- Số kết nối database đang dùng, đang chờ và thời gian lấy connection.
- CPU, I/O, lock, buffer/cache và số kết nối ở database.
- Độ trễ, timeout và tỷ lệ lỗi của dịch vụ ngoài.
- Độ dài queue, tuổi của message cũ nhất và số worker đang bận.
- Dung lượng mạng, disk I/O và kích thước response.

Đo đồng bộ phía client và server để phân biệt thời gian xử lý ứng dụng với thời gian mạng, proxy hoặc tải tài nguyên tĩnh.

## 7. Đặt tải vào đúng đường đi MVC

Để tìm điểm nghẽn, cần biết request tiêu tốn thời gian ở tầng nào:

~~~mermaid
flowchart TD
    A[Load generator] --> B[Network / Load balancer]
    B --> C[Security filters]
    C --> D[DispatcherServlet / Routing]
    D --> E[Controller]
    E --> F[Application service / Model]
    F --> G[Repository / ORM]
    G --> H[(Database)]
    F --> I[External services]
    E --> J[View rendering / Serialization]
    J --> K[HTTP response]
~~~

Các tầng có thể chồng lấp hoặc gọi nhau nhiều lần. Ví dụ Controller gọi service, service truy vấn database nhiều lần, sau đó View truy cập quan hệ lazy và kích hoạt thêm truy vấn. Vì vậy, tổng thời gian response không thể tự chỉ ra chính xác nơi bị chậm.

Hãy dùng trace hoặc instrumentation để đo từng đoạn: filter, handler, use case, repository, truy vấn SQL, lời gọi HTTP ngoài và render/serialize. Dùng correlation ID hoặc trace ID để liên kết log và span của cùng một request.

## 8. Nhận diện các dấu hiệu điểm nghẽn

Điểm nghẽn thường biểu hiện qua một hoặc nhiều dấu hiệu:

| Dấu hiệu | Nguyên nhân có thể | Dữ liệu cần kiểm tra |
| --- | --- | --- |
| CPU gần 100%, latency tăng theo tải | Tính toán nặng, serialization, regex, mã hóa hoặc vòng lặp tốn CPU | CPU profile, flame graph, thời gian từng span |
| CPU thấp nhưng request chờ lâu | I/O, lock, pool hoặc dịch vụ ngoài | Thread dump, thời gian chờ connection, distributed trace |
| Connection pool thường xuyên đầy | Truy vấn lâu, transaction dài hoặc pool nhỏ so với tải | Active/idle/pending connections, slow query, thời gian giữ connection |
| Database CPU/I/O cao | Query thiếu index, quét nhiều dòng, N+1 hoặc contention | Query plan, slow query log, lock wait |
| Heap tăng dần trong soak test | Giữ tham chiếu không cần thiết, cache không giới hạn hoặc leak | Heap usage sau GC, heap dump, allocation profile |
| p99 tăng mạnh nhưng p50 ổn định | Một số request bị block, GC pause, lock hoặc downstream chậm | Tail trace, GC log, thread dump |
| Queue tăng liên tục | Worker không đủ năng lực hoặc downstream chậm | Queue depth, oldest message age, worker throughput |
| Chỉ một endpoint chậm | Truy vấn hoặc xử lý riêng của endpoint đó | Trace, SQL, payload và view model |
| Tất cả endpoint cùng chậm | Tài nguyên dùng chung bị bão hòa | CPU, DB, network, pool và dịch vụ chung |

Một chỉ số đơn lẻ hiếm khi đủ kết luận. Ví dụ CPU database cao có thể do truy vấn xấu, nhưng cũng có thể do lượng request hợp lệ tăng. Cần đối chiếu với thông lượng, số truy vấn, query plan và thời gian thực thi.

## 9. Các điểm nghẽn thường gặp trong ứng dụng MVC

### Truy vấn database và N+1

Một trang danh sách lấy 50 đơn hàng, rồi mỗi đơn lại truy vấn khách hàng hoặc dòng hàng riêng. Tổng số truy vấn có thể tăng theo số bản ghi. Đây là dạng N+1 query.

Cách phát hiện:

- Đếm số query trên mỗi request.
- Xem trace để xác định nhiều truy vấn giống nhau lặp liên tiếp.
- Kiểm tra ORM fetch plan và quan hệ lazy.
- Đọc execution plan của truy vấn chậm.

Cách cải thiện có thể gồm projection chỉ lấy trường cần thiết, fetch join hoặc batch fetching có kiểm soát, thêm index đúng theo điều kiện truy vấn và phân trang. Không thêm index tùy tiện vì index làm tăng chi phí ghi và dung lượng lưu trữ.

### Connection pool

Nếu mọi request đều cần database nhưng pool chỉ có ít kết nối, request sẽ chờ đến lượt. Tăng kích thước pool không phải lúc nào cũng tốt: database có giới hạn tài nguyên và quá nhiều kết nối đồng thời có thể làm hiệu năng giảm.

Đo thời gian chờ lấy connection, thời gian giữ connection, số kết nối active/idle và số request pending. Kiểm tra transaction có mở quá lâu hoặc gọi dịch vụ ngoài trong khi vẫn giữ connection hay không.

### Thread pool và blocking I/O

Một số request có thể chiếm thread trong khi chờ HTTP client, database hoặc tệp. Nếu số thread bị chặn vượt khả năng pool, request mới phải chờ dù CPU còn rảnh.

Theo dõi active threads, queue depth, rejected tasks và thread dump. Cải thiện bằng timeout rõ ràng, connection pool downstream hợp lý, giảm thời gian blocking hoặc dùng mô hình xử lý bất đồng bộ phù hợp. Không chỉ tăng thread count mà không đo mức tiêu thụ bộ nhớ và khả năng của downstream.

### View rendering và serialization

Template phức tạp, vòng lặp lớn, gọi getter kích hoạt lazy loading hoặc response JSON quá lớn đều có thể làm chậm response.

Hãy đo riêng thời gian render/serialize, kích thước response, số phần tử trong danh sách và số query phát sinh trong lúc render. Giảm trường không cần thiết, phân trang và tạo view model phù hợp thường hiệu quả hơn việc tối ưu template một cách cảm tính.

### Dịch vụ bên ngoài

Một request MVC có thể gọi thanh toán, tìm kiếm, email hoặc API khác. Nếu downstream chậm, thread của ứng dụng có thể bị giữ chờ và làm lan truyền sự cố.

Theo dõi latency, timeout, error rate và số request đồng thời đến từng dịch vụ. Dùng timeout, giới hạn concurrency, retry có backoff và circuit breaker phù hợp. Không retry vô hạn hoặc retry mọi lỗi vì điều đó có thể khuếch đại tải khi dịch vụ đang gặp sự cố.

### Cache

Cache có thể giảm truy vấn nhưng cũng tạo điểm nghẽn nếu miss rate cao, cache key không phù hợp hoặc nhiều request đồng thời cùng tải một khóa. Theo dõi hit ratio, miss ratio, eviction, thời gian tải và kích thước cache. Cần kiểm tra cả tính đúng đắn của dữ liệu và phạm vi người dùng/tenant trước khi cache response.

## 10. Công cụ tạo tải và quan sát

Có thể chọn công cụ dựa trên giao thức, cách mô hình hóa và môi trường:

| Công cụ | Điểm mạnh thường dùng |
| --- | --- |
| **k6** | Kịch bản JavaScript, threshold, arrival-rate và tích hợp CI |
| **Apache JMeter** | Giao diện cấu hình, nhiều protocol và hệ sinh thái plugin |
| **Gatling** | Kịch bản code, mô hình tải và báo cáo chi tiết |
| **wrk / wrk2** | Tạo tải HTTP ở mức thấp, phù hợp benchmark endpoint đơn giản |
| **Locust** | Mô phỏng người dùng bằng Python và định nghĩa hành vi theo task |

Các công cụ quan sát thường kết hợp:

- Metrics: Prometheus và Grafana hoặc nền tảng metrics tương đương.
- Distributed tracing: OpenTelemetry và backend như Jaeger hoặc Tempo.
- Log tập trung: hệ thống log có thể tìm theo trace ID/job ID.
- JVM: Java Flight Recorder (JFR), Java Mission Control, heap dump và thread dump.
- Database: slow query log, query plan, lock wait và thống kê connection.

Không cần dùng tất cả công cụ cùng lúc. Bắt đầu từ metrics và trace đang có, sau đó dùng profiler hoặc công cụ chuyên sâu khi đã có giả thuyết về điểm nghẽn.

## 11. Ví dụ kịch bản tải bằng k6

Ví dụ sau gửi request GET đến endpoint danh sách sản phẩm, tăng dần số người dùng ảo và đặt ngưỡng p95 cùng tỷ lệ lỗi:

~~~javascript
import http from "k6/http";
import { check, sleep } from "k6";

export const options = {
  stages: [
    { duration: "2m", target: 50 },
    { duration: "5m", target: 50 },
    { duration: "2m", target: 150 },
    { duration: "5m", target: 150 },
    { duration: "2m", target: 0 }
  ],
  thresholds: {
    http_req_duration: ["p(95)<500"],
    http_req_failed: ["rate<0.01"]
  }
};

export default function () {
  const response = http.get("https://test.example.test/products?page=1");
  check(response, {
    "status is 200": (r) => r.status === 200
  });
  sleep(1);
}
~~~

Đây là ví dụ khởi đầu cho endpoint đọc. Cần thay host, dữ liệu và ngưỡng theo môi trường kiểm thử. Với ứng dụng có xác thực, hãy bổ sung luồng lấy token/cookie an toàn; với form MVC, mô phỏng CSRF token và redirect đúng cách. Không dùng tài khoản hoặc dữ liệu sản xuất nhạy cảm trong môi trường tải thử.

Kịch bản trên dùng số VU và think time, do đó thông lượng thực tế sẽ phụ thuộc vào thời gian response. Nếu cần kiểm soát số lượt bắt đầu request mỗi giây, có thể dùng executor arrival-rate của k6 và cấp đủ VU để tránh generator tự trở thành giới hạn.

## 12. Tách tải generator khỏi tải ứng dụng

Load generator cũng có thể trở thành điểm nghẽn. Nếu máy tạo tải hết CPU, mạng hoặc socket, ứng dụng có thể bị đánh giá thấp hơn năng lực thực tế.

Hãy theo dõi:

- CPU và bộ nhớ của máy tạo tải.
- Số VU thực tế, iteration bị bỏ lỡ và tốc độ gửi đạt được.
- Network throughput, socket và giới hạn file descriptor.
- Tài nguyên của agent nếu chạy phân tán.
- Sai khác giữa request dự kiến và request thực tế đến server.

Nếu generator bị bão hòa, tăng số lượng máy tạo tải hoặc phân phối tải. Ghi lại cấu hình generator trong báo cáo để kết quả có thể lặp lại. Cũng cần đồng bộ thời gian giữa các máy để đối chiếu metrics và trace.

## 13. Chuẩn bị môi trường và dữ liệu thử nghiệm

Kết quả chỉ có ý nghĩa khi môi trường và dữ liệu được mô tả rõ. Một số nguyên tắc:

- Dùng môi trường gần với sản xuất về cấu hình JVM, số instance, database, cache, proxy và giới hạn mạng.
- Không chạy load test phá hủy trên production nếu chưa có kế hoạch, giới hạn tải và phê duyệt vận hành rõ ràng.
- Tạo dữ liệu đủ lớn và có phân bố gần thực tế; vài chục bản ghi không đại diện cho bảng có hàng triệu bản ghi.
- Dùng tài khoản kiểm thử và phân quyền tương tự luồng thực tế.
- Tách dữ liệu thử nghiệm để tránh tác động tới khách hàng hoặc hệ thống khác.
- Ghi lại phiên bản ứng dụng, commit, cấu hình, kích thước máy và trạng thái cache.
- Làm nóng JVM và cache khi mục tiêu là đo trạng thái ổn định; đồng thời có bài riêng nếu cần đo cold start.
- Chạy baseline trước khi thay đổi để có mốc so sánh.

Không so sánh hai lần chạy nếu một lần dùng cache ấm và lần kia cache lạnh mà không ghi nhận khác biệt. Cũng không so sánh trực tiếp hai môi trường có cấu hình database hoặc số instance khác nhau rồi kết luận thay đổi code là nguyên nhân.

## 14. Quy trình tìm điểm nghẽn bằng giả thuyết

Không nên thay nhiều cấu hình cùng lúc vì sẽ khó biết thay đổi nào tạo ra kết quả. Một quy trình thực tế:

1. **Đặt câu hỏi:** ví dụ p95 của GET /orders tăng từ 300 ms lên 1,2 giây khi tải vượt 100 request/giây.
2. **Tạo baseline:** chạy cùng kịch bản, ghi lại p50/p95/p99, throughput, error rate và tài nguyên.
3. **Khoanh vùng:** xem endpoint, trace, database, pool, thread và dịch vụ ngoài để tìm span chiếm thời gian.
4. **Lập giả thuyết:** ví dụ endpoint bị chậm do N+1 query khi danh sách có nhiều đơn.
5. **Thu thập bằng chứng:** đếm query/request, đọc trace và query plan; xác định số query tăng theo số đơn.
6. **Thay một yếu tố:** dùng projection hoặc fetch strategy phù hợp.
7. **Chạy lại cùng kịch bản:** giữ nguyên tải, dữ liệu và môi trường để so sánh.
8. **Đánh giá tác động:** kiểm tra latency, throughput, lỗi, CPU, DB và tính đúng đắn của response.
9. **Ghi nhận kết quả:** lưu giả thuyết, bằng chứng, thay đổi và kết quả đo.

~~~mermaid
flowchart TD
    A[Đặt mục tiêu và SLO] --> B[Thiết kế kịch bản tải]
    B --> C[Chạy baseline]
    C --> D[Thu thập metrics và traces]
    D --> E{Có dấu hiệu bão hòa?}
    E -->|Chưa| F[Tăng tải có kiểm soát]
    F --> D
    E -->|Có| G[Khoanh vùng tầng chậm]
    G --> H[Lập giả thuyết và kiểm chứng]
    H --> I[Thay đổi một yếu tố]
    I --> J[Chạy lại cùng kịch bản]
    J --> K{Đạt mục tiêu và không hồi quy?}
    K -->|Chưa| G
    K -->|Đạt| L[Ghi nhận và theo dõi]
~~~

## 15. Đọc kết quả trước và sau tối ưu

Ví dụ một lần đo minh họa:

| Chỉ số | Trước tối ưu | Sau tối ưu |
| --- | ---: | ---: |
| Throughput | 120 req/s | 180 req/s |
| p50 | 180 ms | 150 ms |
| p95 | 1.200 ms | 520 ms |
| p99 | 2.800 ms | 1.100 ms |
| Error rate | 2,5% | 0,4% |
| Query trung bình/request | 24 | 5 |

Kết quả này gợi ý tối ưu đã giảm số truy vấn và cải thiện tail latency. Tuy nhiên, để kết luận chắc chắn, cần bảo đảm hai lần chạy dùng cùng tải, dữ liệu, cấu hình và điều kiện cache; kiểm tra thêm CPU, database và tính đúng đắn của kết quả.

Không chỉ nhìn một chỉ số. Throughput tăng nhưng error rate tăng mạnh có thể là hệ thống đang quá tải. p95 giảm nhưng p99 tăng có thể cho thấy phần lớn request nhanh hơn trong khi một nhóm nhỏ bị block. Hãy đọc các chỉ số cùng nhau và theo từng endpoint.

## 16. Tránh những kết luận sai khi kiểm thử

| Sai lầm | Vì sao gây hiểu nhầm | Cách tránh |
| --- | --- | --- |
| Chỉ nhìn average latency | Che khuất request chậm ở tail | Theo dõi p50, p95, p99 và max |
| Chỉ kiểm thử một endpoint | Không đại diện luồng nghiệp vụ | Dùng workload mix theo hành vi người dùng |
| Không có think time | Tạo tải phi thực tế | Mô phỏng khoảng nghỉ và chuỗi thao tác |
| Dùng dữ liệu quá nhỏ | Query plan và cache khác thực tế | Tạo tập dữ liệu có quy mô, phân bố phù hợp |
| Chạy một lần duy nhất | Kết quả dễ bị nhiễu | Lặp lại và so sánh nhiều lần |
| Thay nhiều cấu hình cùng lúc | Không biết yếu tố nào tạo khác biệt | Thay từng yếu tố và đo lại |
| Chỉ xem CPU | Có thể bỏ qua I/O, lock và pool | Kết hợp metrics, trace, log và profile |
| Không kiểm tra business success | Request 2xx chưa chắc nghiệp vụ thành công | Xác minh kết quả và trạng thái dữ liệu |
| Để generator quá yếu | Đo năng lực máy tạo tải thay vì ứng dụng | Giám sát và phân tán generator |
| Tối ưu quá sớm | Tăng độ phức tạp mà không cải thiện đáng kể | Đo trước, lập giả thuyết, xác minh sau |

## 17. Kiểm thử hiệu năng cho từng loại endpoint MVC

Mỗi loại endpoint có đặc điểm tải khác nhau:

| Loại endpoint | Điều cần chú ý |
| --- | --- |
| GET danh sách | Phân trang, index, projection, số query và kích thước response |
| GET chi tiết | Fetch relation, N+1 và cache theo phạm vi |
| Search/filter | Query plan, index kết hợp, sort và độ chọn lọc của bộ lọc |
| POST form | Validation, CSRF, transaction, ghi dữ liệu và side effect |
| PUT/PATCH | Lock contention, optimistic locking và cập nhật đồng thời |
| DELETE | Ràng buộc quan hệ, cascade và transaction |
| API JSON | Serialization, payload size và schema mapping |
| Export/report | Job queue, worker throughput, file storage và polling trạng thái |

Đối với endpoint ghi, dùng dữ liệu kiểm thử có thể làm mới hoặc dọn dẹp để các lần chạy không bị ảnh hưởng bởi trạng thái từ lần trước. Đối với endpoint xuất báo cáo, nên kiểm thử riêng luồng tiếp nhận job và luồng worker thực thi; response 202 Accepted nhanh không chứng minh công việc nền hoàn thành đúng hạn.

## 18. Báo cáo kiểm thử có thể tái lập

Một báo cáo nên cho phép người khác hiểu điều kiện và lặp lại phép đo. Ghi lại:

- Mục tiêu và tiêu chí đạt.
- Phiên bản ứng dụng, commit và cấu hình.
- Sơ đồ môi trường, số instance và tài nguyên.
- Nguồn dữ liệu và quy mô dữ liệu thử nghiệm.
- Kịch bản, tỷ lệ thao tác, think time và mô hình tải.
- Thời gian warm-up, ramp-up, steady-state và ramp-down.
- Throughput, latency percentile, error rate và business success rate.
- Metrics của JVM, database, cache, queue, worker và generator.
- Trace hoặc query plan đại diện cho điểm nghẽn.
- Giả thuyết, thay đổi đã thực hiện và kết quả trước/sau.
- Giới hạn của phép đo và các yếu tố có thể gây nhiễu.

Không chỉ lưu ảnh chụp dashboard. Hãy lưu dữ liệu thô hoặc báo cáo công cụ, cấu hình kịch bản và mốc thời gian để có thể đối chiếu khi cần.

## 19. Quy trình thực hiện kiểm thử tải cho ứng dụng MVC

Khi chuẩn bị một đợt kiểm thử, hãy thực hiện theo trình tự:

1. Chọn luồng nghiệp vụ quan trọng và xác định tải dự kiến.
2. Đặt SLO cho latency percentile, throughput, error rate và tài nguyên.
3. Chuẩn bị môi trường, dữ liệu, tài khoản và quyền truy cập thử nghiệm.
4. Viết kịch bản mô phỏng chuỗi request, think time và tỷ lệ thao tác.
5. Kiểm tra kịch bản ở tải nhỏ để chắc chắn request hợp lệ và dữ liệu được xử lý đúng.
6. Chạy warm-up, ramp-up và giai đoạn tải ổn định; ghi lại cấu hình chính xác.
7. Theo dõi client, server, database, cache, queue và dịch vụ ngoài.
8. Khoanh vùng tầng chậm bằng trace, profiler, thread dump hoặc query plan.
9. Thay đổi một yếu tố theo giả thuyết và chạy lại cùng điều kiện.
10. Ghi nhận kết quả, giới hạn và quyết định về năng lực hoặc bước tối ưu tiếp theo.

## Kết luận

Kiểm thử tải giúp đo khả năng đáp ứng của ứng dụng MVC trong điều kiện gần với thực tế; metrics và tracing giúp xác định request đang mất thời gian ở Controller, Model, database, View hay dịch vụ ngoài. Một quy trình tốt bắt đầu bằng mục tiêu và workload rõ ràng, đo latency percentile cùng throughput và error rate, giám sát tài nguyên ở mọi tầng, sau đó kiểm chứng từng giả thuyết bằng phép đo lặp lại. Nhờ vậy, việc tối ưu dựa trên bằng chứng và có thể xác nhận bằng kết quả trước/sau.
