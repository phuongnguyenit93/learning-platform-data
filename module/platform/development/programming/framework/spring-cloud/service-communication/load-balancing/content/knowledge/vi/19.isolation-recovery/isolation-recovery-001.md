# Phân biệt cân bằng tải, retry và circuit breaker

Trong hệ thống microservices, một request từ **Order Service** đến **Inventory Service** có thể thất bại vì bản sao vừa dừng, lỗi mạng thoáng qua, thời gian phản hồi quá dài hoặc toàn bộ dịch vụ đang quá tải. Ba cơ chế thường xuất hiện cùng nhau trong Spring Cloud là **client-side load balancing**, **retry** và **circuit breaker**. Chúng đều liên quan đến khả năng chịu lỗi nhưng **trả lời ba câu hỏi khác nhau**:

- **Load balancing:** *Nên gửi lần gọi này đến ServiceInstance nào?*
- **Retry:** *Sau một lỗi có khả năng phục hồi, có nên thử thực hiện lại lời gọi?*
- **Circuit breaker:** *Dựa vào các lỗi gần đây, có nên tiếp tục cho phép lời gọi tới phụ thuộc này không?*

Không thể thay thế một cơ chế bằng cơ chế khác. LoadBalancer có thể chọn đúng instance nhưng backend vẫn trả 503; retry có thể đổi instance nhưng không cứu được một dịch vụ đã hỏng toàn bộ; circuit breaker có thể bảo vệ caller bằng cách từ chối sớm, nhưng bản thân nó **không tìm instance mới và không tự thử lại**.

Bài học trình bày vai trò, thứ tự kết hợp, kịch bản khôi phục và cách áp dụng cho **RestClient, RestTemplate, WebClient, OpenFeign** với Spring Cloud LoadBalancer. Đồng thời làm rõ sự khác nhau giữa circuit breaker, **timeout**, **bulkhead**, **fallback** và **health check** để thiết kế giao tiếp giữa các dịch vụ ổn định.

> **Phạm vi:** Các API và thuộc tính được minh họa theo Spring Cloud Commons/LoadBalancer, Spring Cloud CircuitBreaker và Resilience4j hiện hành. Giá trị cấu hình là ví dụ cần hiệu chỉnh theo SLO và BOM Spring Boot–Spring Cloud của dự án. Trong Spring Cloud, **bật một thuộc tính retry không đồng nghĩa mọi client và mọi HTTP method sẽ tự được retry**; còn tùy dependency, filter và đường tích hợp.

## 1. Ba cơ chế đứng ở đâu trong luồng gọi?

Giả sử Order Service gọi một URI logic:

~~~http
GET http://inventory-service/api/stock/BOOK-01
~~~

Discovery cung cấp các bản sao:

| Service ID | Instance ID | Host/port | Tình trạng minh họa |
| --- | --- | --- | --- |
| inventory-service | inventory-a | 10.20.0.11:8080 | UP |
| inventory-service | inventory-b | 10.20.0.12:8080 | UP nhưng chậm |
| inventory-service | inventory-c | 10.20.0.13:8080 | Có lỗi kết nối thoáng qua |

Luồng dưới đây mô tả một **thiết kế có chủ đích**, không phải thứ tự tự động của mọi Spring Cloud application:

~~~mermaid
flowchart TD
    A["Order Service muốn đọc tồn kho"] --> B{"Circuit breaker cho phép?"}
    B -->|OPEN, từ chối| C["Fail fast / fallback có kiểm soát"]
    B -->|CLOSED hoặc thử nghiệm HALF_OPEN| D["LoadBalancer chọn ServiceInstance"]
    D --> E["Gửi HTTP đến một bản sao"]
    E --> F{"Kết quả"}
    F -->|Thành công| G["Trả response và ghi nhận success"]
    F -->|Lỗi không retryable| H["Báo lỗi, ghi nhận outcome"]
    F -->|Lỗi retryable| I{"Còn attempts và deadline?"}
    I -->|Có| D
    I -->|Không| H
    G --> J["Circuit breaker cập nhật thống kê"]
    H --> J
~~~

Trong sơ đồ này, circuit breaker bao quanh **một lời gọi logic** có thể gồm nhiều attempts, nên nó thấy kết quả cuối cùng. Nếu đặt circuit breaker **bên trong retry**, nó có thể ghi nhận từng attempt và chuyển OPEN sớm hơn. Hai cách đều có thể hợp lệ, nhưng phải chọn dựa trên mục tiêu đo lỗi và bảo vệ downstream.

### 1.1. Ba trục thiết kế khác nhau

| Cơ chế | Quyết định cốt lõi | Dữ liệu đầu vào | Hành động |
| --- | --- | --- | --- |
| LoadBalancer | Chọn *đích* | Danh sách ServiceInstance, zone/hint/health/metadata | Chọn instance và tái dựng URI |
| Retry | Có *lặp lại* không? | Exception/status, HTTP method, attempts, deadline | Gửi lại cùng thao tác, có thể chọn lại instance |
| Circuit breaker | Có *cho phép* không? | Thống kê lỗi/chậm, trạng thái breaker, ngưỡng | Cho qua, thử probe hạn chế hoặc từ chối ngay |

**LoadBalancer chọn nơi gửi; retry quyết định gửi thêm lần nữa; circuit breaker quyết định có được gửi tiếp hay không.**

## 2. Load balancing: phân phối lưu lượng, không phải tự khôi phục mọi lỗi

Trong Spring Cloud LoadBalancer, **ServiceInstanceListSupplier** cung cấp danh sách bản sao theo service ID. Chuỗi supplier có thể sử dụng discovery, caching, health check, zone preference, hints hoặc retry-aware filter. **RoundRobinLoadBalancer** hoặc **RandomLoadBalancer** chọn từ danh sách cuối cùng.

~~~text
Order Service
   |
   | URI logic: inventory-service
   v
ServiceInstanceListSupplier -> [A, B, C]
   |
   | Round Robin / Random
   v
ServiceInstance B
   |
   v
HTTP http://10.20.0.12:8080/api/stock/BOOK-01
~~~

LoadBalancer đảm nhiệm:

1. Xác định **service ID** từ URI logic.
2. Truy xuất danh sách bản sao từ supplier.
3. Áp dụng các chính sách sắp xếp/lọc đã cấu hình.
4. Chọn một ServiceInstance.
5. Tái dựng URI vật lý giữ path, query và scheme phù hợp.

Nhưng nó **không tự bảo đảm**:

- Instance vừa chọn sẽ trả lời thành công.
- HTTP 503 sẽ được gửi lại sang instance khác.
- Mọi bản sao sẽ bị loại ngay khi có một request thất bại.
- Backend quá tải sẽ phục hồi chỉ vì thay thuật toán chọn.
- Request ghi dữ liệu có thể được gửi lại an toàn.

### 2.1. Instance health khác với request outcome

Discovery/HealthCheck có thể đánh giá bản sao đang UP và tiếp tục giữ nó trong danh sách. Tuy nhiên, một endpoint riêng có thể trả 500 trong khi health endpoint vẫn trả 200. Ngược lại, một request gặp timeout chưa chắc instance đã chết; có thể chỉ là truy vấn chậm.

**Health-check supplier** cung cấp trạng thái ứng viên trong thời gian gần đây; **circuit breaker** đánh giá chuỗi kết quả các lời gọi nằm trong phạm vi mà bạn bọc nó. Hai góc nhìn này bổ sung nhau nhưng không tương đương.

### 2.2. Không có instance không đồng nghĩa circuit breaker OPEN

Nếu supplier trả **[]**, LoadBalancer không thể chọn đích. Đó là lỗi discovery/availability đầu vào, không phải bằng chứng circuit breaker đang OPEN. Cần chẩn đoán registry, cache, health filter, service ID và metadata trước khi thay ngưỡng circuit breaker.

## 3. Retry: thực hiện lại sau một lỗi được phân loại

Retry là chính sách **thử lại** sau một lỗi mà hệ thống đánh giá có khả năng phục hồi. Một lời gọi logic có thể bao gồm một lần đầu và một hoặc nhiều lần thử lại (**attempts**).

~~~text
Attempt 1:  chọn A -> connection reset
Backoff:    100 ms
Attempt 2:  chọn B -> HTTP 200
Kết quả:    thành công sau 2 attempts
~~~

Retry có thể thực thi:

- **Cùng ServiceInstance**, khi lỗi được dự đoán là thoáng qua.
- **ServiceInstance khác**, khi muốn tránh bản sao vừa gặp lỗi.
- **Một HTTP client hoặc application wrapper khác**, tùy nơi cấu hình retry.

**Quan trọng:** retry chỉ đổi số lần gửi; việc chọn lại instance phụ thuộc vào cơ chế LoadBalancer và context retry. Một retry ở Reactor/Resilience4j có thể tái subscribe HTTP call, nhưng **không mặc nhiên bảo đảm attempt thứ hai đi B**. Muốn xác nhận phải kiểm tra URI/instance ID của từng attempt.

### 3.1. Khi nào nên thử lại?

| Kết quả lần gọi | Retry thường phù hợp? | Lý do |
| --- | --- | --- |
| TCP connection reset trước response | Có thể | Lỗi mạng thoáng qua, nhưng với request ghi vẫn cần idempotency |
| Connect timeout | Có thể | Instance hoặc mạng có sự cố tạm thời |
| HTTP 502/503/504 | Có thể | Downstream/gateway không sẵn sàng, cần backoff và giới hạn |
| HTTP 429 | Có thể | Tôn trọng Retry-After và rate limit |
| HTTP 400/422 | Thông thường không | Payload sai; gửi lại y nguyên hiếm khi sửa được |
| HTTP 401/403 | Thông thường không | Thiếu quyền; không retry mù |
| HTTP 404 | Thông thường không | Tài nguyên có thể thực sự không tồn tại |
| HTTP 409 | Tùy domain | Có thể cần đọc trạng thái mới, không gửi lại y nguyên |
| JSON decode sai schema | Không | Lỗi contract, retry dễ chỉ tăng tải |
| Circuit breaker OPEN | Không | Bị từ chối có chủ đích; retry liên tục gây storm |

Không nên hardcode “mọi 5xx đều retry” nếu request có side effect. Phải xét **HTTP method, idempotency, server contract, deadline và tải downstream**.

### 3.2. Backoff, jitter và giới hạn attempts

Một retry policy hoàn chỉnh cần:

- **max attempts**: số lần gửi tối đa.
- **retryable status/exceptions**: điều kiện rõ ràng.
- **backoff**: khoảng nghỉ giữa attempts.
- **jitter**: xáo trộn khoảng chờ để tránh các caller cùng retry một thời điểm.
- **overall deadline**: giới hạn thời gian của *lời gọi logic*, gồm các attempts và backoff.
- **retry budget**: giới hạn mức lưu lượng retry so với lưu lượng gốc.

Ví dụ có **một** retry:

~~~text
Attempt 1: 350 ms -> 503
Backoff:   100 ms
Attempt 2: 420 ms -> 200
------------------------
Tổng:      870 ms
~~~

Nếu Request SLA chỉ 700 ms, chính sách đó vượt ngân sách dù lần thứ hai thành công. Timeout **per attempt** không phải **total deadline**.

### 3.3. Retry có thể khuếch đại quá tải

Giả sử Inventory nhận 1.000 request/giây; mọi request đều 503 và caller cấu hình tối đa 3 attempts (1 lần đầu + 2 retries). Nếu tất cả caller đều retry đến giới hạn, Inventory có thể nhận **3.000 attempts/giây**. Nếu tầng Gateway cũng retry 3 lần, tải thực tế có thể lên tới **9.000 attempts/giây** theo cấu trúc nhân tầng, tùy cách wrapper được áp dụng.

Hãy tránh retry storm bằng backoff/jitter, deadline, số lần nhỏ, giới hạn đồng thời và circuit breaker. **Retry không phải một cách tăng availability miễn phí**.

## 4. Circuit breaker: ngắt đường gọi khi thất bại lặp lại

Circuit breaker theo dõi kết quả lời gọi theo **một khóa định danh breaker** như inventory-read. Khi tỷ lệ lỗi hoặc tỷ lệ gọi chậm vượt ngưỡng đã cấu hình, nó chuyển sang **OPEN** để **từ chối các lời gọi mới** mà không tiếp tục gây tải cho downstream.

Trong Resilience4j có ba trạng thái thông dụng:

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN : Failure/slow-call rate vượt ngưỡng
    OPEN --> HALF_OPEN : Hết wait duration và có thử nghiệm
    HALF_OPEN --> CLOSED : Probe đạt tiêu chí
    HALF_OPEN --> OPEN : Probe tiếp tục lỗi/chậm
~~~

| Trạng thái | Hành vi | Tác động tới backend |
| --- | --- | --- |
| **CLOSED** | Cho request qua, ghi nhận success/failure/slow calls | Backend tiếp tục nhận traffic |
| **OPEN** | Từ chối phần lớn lời gọi mới nhanh chóng, thường sinh CallNotPermittedException | Backend được giảm tải từ caller đó |
| **HALF_OPEN** | Cho phép số lượng probe giới hạn để đo khả năng phục hồi | Backend nhận một lượng thử nghiệm có kiểm soát |

Resilience4j còn có các trạng thái đặc biệt như **DISABLED, FORCED_OPEN, METRICS_ONLY**; chúng không thuộc chu trình phục hồi bình thường và phải được dùng đúng mục đích.

### 4.1. Một breaker không phải một backend

Giả sử circuit breaker có tên **inventory-read** bọc tất cả lời gọi tới service ID inventory-service. Nếu A lỗi nhưng B/C vẫn khỏe, một breaker có thể bị OPEN và chặn luôn cơ hội chọn B/C. Đây là hệ quả của **phạm vi thống kê breaker**.

Có hai cách đặt phạm vi:

- **Per dependency / operation**: ví dụ inventory-read, gom kết quả mọi instance cho một thao tác; đơn giản, bảo vệ caller trước sự cố toàn bộ downstream.
- **Per instance**: tạo breaker theo instance ID/host để cô lập bản sao lỗi riêng lẻ; khó quản lý vòng đời khi instance thay đổi và phải tránh cardinality tăng vô hạn.

Trong đa số hệ thống, trước tiên đặt breaker **theo service hoặc operation**; dùng health-aware selection/retry để xử lý bản sao lỗi riêng lẻ. Chỉ làm per-instance breaker khi thật sự có yêu cầu, dữ liệu định danh bền vững và cách dọn dẹp breaker phù hợp.

**Circuit breaker không tự đọc ServiceInstanceListSupplier để gỡ một instance khỏi registry.** Nó bọc lời gọi đã định nghĩa, có thể ở trên hoặc dưới bước chọn instance tùy kiến trúc.

### 4.2. Breaker ghi nhận lỗi theo chính sách, không mặc định mọi 4xx

Resilience4j đánh giá lỗi dựa trên **exception**, kết quả (nếu được adapter chuyển thành lỗi), threshold và các predicate như **recordExceptions**, **ignoreExceptions** hoặc recordFailurePredicate. Nếu HTTP client không ném ngoại lệ cho HTTP 503, breaker có thể ghi nhận một success dù nghiệp vụ coi đó là thất bại.

Ví dụ:

- HTTP 404 vì SKU không tồn tại có thể là **kết quả domain hợp lệ**, không nên làm breaker OPEN.
- HTTP 503 do server quá tải thường đáng ghi nhận là lỗi.
- Timeout và kết nối reset thường đáng ghi nhận, với điều kiện lỗi gốc chưa bị fallback nuốt.
- Một lỗi validation của caller không nên khiến toàn bộ Inventory bị coi là không khỏe.

Chính sách phân loại lỗi phải đặt rõ tại lớp HTTP adapter và breaker. **Một fallback trả giá trị thành công ở bên trong breaker có thể làm nó không thấy lỗi gốc**, dẫn đến số liệu sai.

## 5. Circuit breaker không phải bulkhead, timeout hay rate limiter

Các khái niệm có thể xuất hiện trong cùng thư viện Resilience4j:

| Cơ chế | Câu hỏi chính | Ví dụ |
| --- | --- | --- |
| **LoadBalancer** | Gửi tới instance nào? | Chọn Inventory B |
| **Retry** | Có gửi lại không? | Thử B sau khi A lỗi |
| **Circuit breaker** | Có nên cho phép lời gọi tiếp theo? | OPEN: từ chối request mới |
| **Bulkhead** | Cho phép tối đa bao nhiêu công việc đồng thời? | Tối đa 20 cuộc gọi Inventory đang xử lý |
| **Timeout / TimeLimiter** | Chờ tối đa bao lâu? | 800 ms cho một attempt hoặc 1,5 s cho toàn lời gọi |
| **RateLimiter** | Cho phép bao nhiêu request theo tốc độ? | 100 request/giây |
| **Fallback** | Trả kết quả gì khi không thực hiện được? | Đọc tồn kho từ cache kèm nhãn stale |
| **Health check** | Instance đang được coi là available? | Loại C khỏi danh sách ứng viên |

**Một circuit breaker CLOSED có thể cho hàng nghìn request đồng thời đi qua.** Sliding window size của breaker là số mẫu thống kê, **không phải giới hạn số request concurrent**. Nếu cần giới hạn đồng thời để bảo vệ thread/connection pool, dùng **bulkhead**, pool limit hoặc backpressure.

### 5.1. Circuit breaker khác timeout

Circuit breaker thu thập *lịch sử kết quả* để quyết định khả năng cho phép request mới. Timeout là *giới hạn thời gian* một request hoặc một giai đoạn.

Nếu backend treo 60 giây và client không có timeout, circuit breaker không nhất thiết mở sớm: nó cần lời gọi hoàn tất hoặc bị báo chậm/lỗi theo cách ghi nhận tương ứng. Vì vậy cần timeout (và có thể TimeLimiter) để lời gọi chậm được kết thúc/phân loại.

Ngược lại, timeout=500 ms không tự tạo ra cơ chế **OPEN/HALF_OPEN**. Nó chỉ giới hạn chờ một lời gọi, không ghi nhớ tỷ lệ lỗi cho các lời gọi kế tiếp.

### 5.2. TimeLimiter của Spring Cloud CircuitBreaker có cấu hình riêng

Khi tích hợp Spring Cloud CircuitBreaker với Resilience4j, ngoài CircuitBreakerConfig còn có **TimeLimiterConfig**. Tài liệu hiện hành cho phép khai báo:

~~~yaml
resilience4j:
  timelimiter:
    instances:
      inventory-read:
        timeoutDuration: 1500ms
        cancelRunningFuture: true
~~~

Tính năng TimeLimiter có thể **được bật mặc định trong tích hợp Spring Cloud CircuitBreaker**. Đừng nhầm với connect/read timeout của HTTP transport. Khi dùng synchronous HTTP client, việc hủy Future hoặc timeout tầng wrapper **không bảo đảm đã hủy ngay** một socket đang chờ và không rollback transaction phía server.

Với WebClient reactive, cancellation thường được truyền xuống Publisher, nhưng thực tế đóng connection/hủy network I/O vẫn phụ thuộc connector và thời điểm request. Cần kiểm tra bằng test chậm mạng.

### 5.3. Bulkhead cô lập tài nguyên, breaker cô lập traffic theo trạng thái

Ví dụ:

~~~text
inventory-service đang phản hồi chậm nhưng chưa lỗi:

Không bulkhead:
  hàng trăm request có thể giữ connection, thread/buffer và làm Order quá tải

Có bulkhead:
  tối đa 30 request Inventory đồng thời
  request vượt giới hạn bị từ chối/đợi có kiểm soát

Có circuit breaker:
  sau khi lỗi/chậm vượt ngưỡng, request mới bị từ chối sớm
~~~

Hai cơ chế bổ sung cho nhau. Với Spring Cloud CircuitBreaker Resilience4j, nếu module bulkhead có trên classpath thì **tích hợp bulkhead có thể được áp dụng tự động**; lựa chọn giữa semaphore và thread-pool bulkhead phụ thuộc phiên bản/cấu hình. Điều này phải được xác minh khi đo latency và thread usage.

## 6. Cùng một lỗi nhưng ba cơ chế phản ứng khác nhau

### 6.1. Bản sao A chết, B còn khỏe

~~~text
Discovery: [A, B]
Attempt đầu: LoadBalancer chọn A
Kết quả: connection refused
Retry policy: thử một lần, chọn lại instance
Attempt hai: LoadBalancer chọn B -> 200
Breaker per-service: nhìn thấy kết quả cuối thành công nếu bọc ngoài retry
~~~

Ở đây **LoadBalancer + retry** có thể phục hồi được. Breaker không nhất thiết cần OPEN chỉ vì A lỗi một lần. Nhưng nếu retry không có context tránh A, attempt thứ hai **có thể lại chọn A**.

### 6.2. Cả A và B đều trả 503 trong thời gian dài

~~~text
Attempt 1: A -> 503
Attempt 2: B -> 503
Attempt 3: A/B -> 503
Breaker ghi nhận failure
Đủ số mẫu + vượt threshold => OPEN
Request kế tiếp => từ chối sớm, không gửi đến Inventory
~~~

Khi toàn bộ downstream lỗi, **retry nhiều lần chỉ làm tăng tải**. Circuit breaker giúp caller không liên tục làm tình hình xấu hơn và có thể bảo vệ thread/pool.

### 6.3. Inventory khỏe nhưng Order thiếu thread

~~~text
Inventory: HTTP 200, latency 1.500 ms
Order: 500 request đồng thời, pool connection chỉ có 30
Hàng đợi acquire tăng, thread bị giữ
~~~

LoadBalancer vẫn có thể chọn instance đúng. Retry lại có thể làm tải tăng. Breaker chỉ OPEN khi outcome/slow-call policy đáp ứng ngưỡng. **Bulkhead, pool-acquire timeout và overall deadline** mới là công cụ trực tiếp để cô lập tài nguyên trong tình huống này.

### 6.4. Lỗi nghiệp vụ 404/409

Nếu Inventory trả 404 vì SKU không tồn tại hoặc 409 vì optimistic locking, việc đổi instance không nhất thiết sửa được lỗi. Retry 404/409 y nguyên và ghi nhận chúng như outage có thể làm sai thống kê breaker. Cần phân loại theo API contract trước.

## 7. Cách kết hợp thứ tự: breaker bên ngoài hay bên trong retry?

**Thứ tự decorator quyết định circuit breaker đo cái gì.**

### 7.1. Circuit breaker bên ngoài retry: đo kết quả lời gọi logic

~~~text
CircuitBreaker(
    Retry(
        LoadBalancerChooseAndHttpCall()
    )
)
~~~

Nếu A lỗi lần đầu, B thành công lần sau, breaker ngoài cùng có thể ghi **một success** cho toàn lời gọi logic (nhưng tổng latency có thể lớn). Cách này hợp lý khi breaker bảo vệ một *operation* và muốn đánh giá outcome cuối của operation.

Lợi điểm: lỗi thoáng qua được retry phục hồi không lập tức đẩy breaker tới OPEN. Rủi ro: nhiều attempts lỗi vẫn có thể bị gộp thành một failure; số lượng request thực tế xuống backend lớn hơn số liệu breaker. Cần theo dõi **attempt metrics riêng**.

### 7.2. Retry bên ngoài circuit breaker: đo từng attempt

~~~text
Retry(
    CircuitBreaker(
        LoadBalancerChooseAndHttpCall()
    )
)
~~~

Nếu A lỗi hai lần rồi B thành công, breaker có thể ghi **hai failures và một success**. Nó mở nhanh hơn khi có nhiều attempt lỗi, nhưng nếu breaker đang OPEN và bên ngoài vẫn retry **CallNotPermittedException**, hệ thống tạo các lần từ chối không mang giá trị.

Phải cấu hình retry **không retry CallNotPermittedException**, và xác định retry policy có nên ngừng hoàn toàn khi breaker OPEN. Không nhầm thứ tự ký hiệu wrapper với thứ tự thực thi lúc đánh giá lỗi.

### 7.3. Annotation AOP không mặc định có cùng thứ tự với Reactor operators

Resilience4j có cơ chế annotation/AOP và functional decorators. Tài liệu Resilience4j nêu thứ tự aspect mặc định dạng **Retry(CircuitBreaker(RateLimiter(TimeLimiter(Bulkhead(function)))))** trong cấu hình annotation điển hình. Nếu tự ghép operator Reactor hoặc Spring Cloud factory, thứ tự do **code của bạn** quyết định và có thể khác hẳn.

Không kết luận tất cả dự án đều có cùng thứ tự chỉ vì chúng khai báo **@Retry và @CircuitBreaker**. Kiểm tra thực tế configuration, aspect order, method proxying và các wrapper auto-configured.

**Một lưu ý thường bỏ sót:** Spring Cloud LoadBalancer có cơ chế retry riêng; nếu bạn cũng đặt Resilience4j @Retry hoặc Reactor retryWhen ở ngoài, có thể xuất hiện **retry lồng nhau**. Điều đó ảnh hưởng cả số attempts lẫn thống kê circuit breaker.

## 8. Ví dụ tính ngân sách: breaker không thay deadline

Giả sử Order API phải hoàn thành trong **1.800 ms**. Bạn thiết kế:

| Hạng mục | Giới hạn minh họa |
| --- | ---: |
| Chọn instance/lookup | 50 ms |
| Connect + response per attempt | 600 ms |
| Backoff giữa attempts | 100 ms |
| Một retry tối đa | 1 |
| Xử lý domain + response | 150 ms |
| Deadline toàn lời gọi | 1.800 ms |

Hai attempts có thể cần:

~~~text
T ~= 50 + 600 + 100 + 600 + 150 = 1.500 ms
~~~

Trong trường hợp network jitter, pool acquire hoặc decode làm tăng thêm 400 ms, tổng có thể vượt **1.800 ms** dù cả attempt timeout đều đặt là 600 ms. Vì vậy, cần một **overall deadline** bao quanh retry/backoff, không chỉ đặt connect/read timeout ở transport.

Breaker có thể OPEN và giúp một request được từ chối trong vài mili giây, nhưng **không thay deadline** cho các request được cho qua. SLO phải được bảo vệ bằng timeout, retry budget và giới hạn tài nguyên, rồi mới kết hợp breaker.

## 9. Đâu là ranh giới của fallback?

**Fallback là cách ứng dụng xử lý khi không thể lấy kết quả từ downstream**, không phải chức năng mặc định của LoadBalancer. Spring Cloud CircuitBreaker có API nhận fallback function, nhưng callback đó phải tuân theo domain contract.

Ví dụ đọc thông tin tồn kho:

~~~text
Inventory online:  STOCK=7 (fresh)
Inventory lỗi:    STOCK=7 (cached, stale=true, cacheAge=10s)
~~~

Nếu ứng dụng có read-only cache đã được xây dựng để chịu stale data, fallback như vậy **có thể** hữu ích. Phải trả cả metadata freshness, không giả mạo nó là số liệu mới.

Ngược lại:

~~~text
POST /reservations bị timeout
Fallback: trả success dù chưa biết backend đã commit chưa
~~~

Đây là **lỗi nghiệp vụ nghiêm trọng**. Không được coi “không rõ kết quả” là “đã đặt thành công”; cần idempotency key, operation-status API, hoặc một trạng thái pending/unknown để đối soát.

### 9.1. Không fallback mọi exception

Một fallback “trả cache cho tất cả lỗi” có thể che:

- 401/403: cấu hình xác thực sai.
- 400/422: request không hợp lệ.
- 404: SKU thực sự không tồn tại.
- 409: xung đột trạng thái.
- NullPointerException: lỗi lập trình ở caller.

Chỉ fallback với các loại lỗi phù hợp như downstream unavailable, breaker OPEN hoặc một tập timeout đã được xác nhận. Ghi nhận trạng thái degraded và theo dõi **fallback usage**, không chỉ HTTP 200 tổng thể.

## 10. Các lớp nên sở hữu trách nhiệm gì?

Một thiết kế dễ bảo trì có thể chia thành:

| Lớp | Trách nhiệm |
| --- | --- |
| Domain Service | Chọn chính sách phục hồi phù hợp nghiệp vụ; quyết định stale/cached result có được chấp nhận không |
| HTTP Adapter | Ánh xạ HTTP status, exception/timeout và DTO thành kết quả domain ổn định |
| Spring Cloud LoadBalancer | Lấy danh sách ServiceInstance, chọn URI vật lý |
| Retry policy | Xác định điều kiện retry, attempts, backoff/jitter, deadline |
| Circuit breaker | Đo kết quả đã chọn và điều khiển CLOSED/OPEN/HALF_OPEN |
| Bulkhead/RateLimiter | Cô lập concurrency và tốc độ truy cập |
| Observability | Theo dõi instance, attempt, outcome, breaker state, fallback, latency |

Nên tránh một service method vừa tự quản lý DiscoveryClient, vừa lặp retry bằng while(true), vừa ghi một biến boolean circuitOpen, rồi tự trả fallback. Việc trộn trách nhiệm làm khó kiểm chứng **khi nào request được gửi thật**, **bao nhiêu lần** và **vì sao bị từ chối**.

## 11. Cấu hình retry trong Spring Cloud LoadBalancer

Spring Cloud LoadBalancer hỗ trợ retry tùy đường tích hợp, HTTP client, classpath và release train. Một cấu hình minh họa:

~~~yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: true
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1
        retry-on-all-operations: false
        retry-on-all-exceptions: false
        retryable-status-codes:
          - 503
        backoff:
          enabled: true
          min-backoff: 100ms
          max-backoff: 500ms
          jitter: 0.3
~~~

Ý nghĩa:

| Thuộc tính | Ý định |
| --- | --- |
| retry.enabled | Cho phép hỗ trợ retry khi các thành phần cần thiết tồn tại |
| max-retries-on-same-service-instance=0 | Không cấu hình retry trên chính instance vừa chọn |
| max-retries-on-next-service-instance=1 | Cho phép tối đa một lần retry theo nhánh chọn instance tiếp theo |
| retry-on-all-operations=false | Không mở retry hàng loạt cho mọi HTTP method |
| retryable-status-codes=[503] | Xác định status muốn thử lại |
| backoff.enabled | Bật khoảng nghỉ retry trên đường reactive có hỗ trợ |
| min/max-backoff, jitter | Kiểm soát khoảng chờ và tránh đồng bộ retry |

**Cảnh báo:** Retry của **RestTemplate blocking** cần **Spring Retry** đúng phiên bản trên classpath; tích hợp WebClient reactive sử dụng cơ chế Reactor retry và cấu hình hỗ trợ tương ứng. OpenFeign có retry mặc định riêng; không nên giả định cùng một khối YAML trên tự động chi phối tất cả Feign clients.

Thêm vào đó, thuộc tính **retry.enabled** không tự cho phép retry mọi lỗi hoặc mọi thao tác ghi. Cần xem **retryable-exceptions, status codes, HTTP method, retry policy**, đồng thời có integration test xác nhận số attempts thật.

### 11.1. Tránh instance vừa lỗi khi retry

**RetryAwareServiceInstanceListSupplier** có thể ưu tiên loại instance trước đó khỏi danh sách khi còn ứng viên thay thế. Thuộc tính **spring.cloud.loadbalancer.retry.avoid-previous-instance** liên quan tới việc áp dụng decorator này; mặc định và điều kiện kích hoạt phụ thuộc dependency/configuration.

Giả sử danh sách trước retry:

~~~text
Lần 1: [A, B, C]  -> chọn A -> lỗi
Lần 2: [B, C]     -> có cơ hội chọn B hoặc C
~~~

Nhưng nếu danh sách sau health/zone/hint chỉ còn **[A]**, retry-aware không thể tạo thêm instance B/C. Bên cạnh đó, **chọn instance tiếp theo không bảo đảm khác instance cũ** khi không có ứng viên thay thế hoặc context retry không được truyền đúng.

Đừng gọi tính năng tránh instance trước đó là **circuit breaker cho từng instance**. Nó là một filter ưu tiên trong quá trình chọn ứng viên, không ghi nhớ failure rate hoặc có trạng thái OPEN/HALF_OPEN như circuit breaker.

### 11.2. Retry của mỗi HTTP client không hoàn toàn giống nhau

| Client | Đường thực thi | Điểm cần kiểm tra |
| --- | --- | --- |
| RestTemplate | BlockingLoadBalancerClient, Spring Retry khi tích hợp | Dependency Spring Retry, status/exception policy |
| RestClient | Blocking LoadBalancer integration | Hỗ trợ retry theo release train/interceptor đang dùng; không suy ra từ cấu hình RestTemplate |
| WebClient | ReactorLoadBalancerExchangeFilterFunction / retry-aware filter khi có | Filter auto-configured, Reactor retry, backoff, cancellation |
| OpenFeign | FeignBlockingLoadBalancerClient và Feign retryer | Retryer của Feign, policy riêng, circuit-breaker wrapper |

Theo tài liệu Spring Cloud OpenFeign, mặc định có bean **Retryer.NEVER_RETRY**, khác với hành vi mặc định của Feign core. Vì vậy, muốn retry Feign cần xác định rõ Retryer/custom configuration và không kết luận từ tên service ID rằng Feign tự retry.

**Đếm request thực sự ở backend**, không chỉ đếm số lần method Java được gọi. Retry xảy ra trong filter/transport có thể gửi nhiều HTTP attempts dù method nghiệp vụ chỉ được invoke một lần.

## 12. Bổ sung Spring Cloud CircuitBreaker với Resilience4j

Spring Cloud CircuitBreaker cung cấp abstraction cho circuit breaker. Một implementation được dùng rộng rãi là **Resilience4j**.

Dependencies minh họa theo Gradle, với Spring Boot BOM và Spring Cloud BOM tương thích:

~~~gradle
dependencies {
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")

    // Ứng dụng synchronous (RestClient / RestTemplate):
    implementation("org.springframework.cloud:spring-cloud-starter-circuitbreaker-resilience4j")

    // Với ứng dụng reactive (WebClient) dùng starter reactive thay cho
    // starter synchronous khi phù hợp:
    // implementation("org.springframework.cloud:spring-cloud-starter-circuitbreaker-reactor-resilience4j")
}
~~~

Các ví dụ không yêu cầu thêm cả hai CircuitBreaker starters vào cùng ứng dụng. Chọn starter theo stack và tránh dependency dư thừa. Circuit breaker không được thêm tự động chỉ vì ứng dụng có **spring-cloud-starter-loadbalancer**.

### 12.1. Cấu hình một breaker có ngưỡng rõ ràng

Ví dụ cấu hình Resilience4j:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryRead:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallRateThreshold: 60
        slowCallDurationThreshold: 800ms
        waitDurationInOpenState: 5s
        permittedNumberOfCallsInHalfOpenState: 3
  timelimiter:
    instances:
      inventoryRead:
        timeoutDuration: 1500ms
        cancelRunningFuture: true
~~~

Đây là một policy **minh họa**, không phải giá trị khuyến nghị chung. Nó có nghĩa:

- Tối đa **20 calls gần nhất** được xem trong sliding window count-based.
- Phải ghi nhận **ít nhất 10 calls** trước khi đánh giá ngưỡng failure/slow rate.
- Failure rate đạt **50% trở lên** có thể làm breaker OPEN.
- Slow-call rate đạt **60% trở lên**, với slow call dài hơn **800 ms**, cũng có thể làm OPEN.
- Khi OPEN đủ 5 giây, circuit có thể bước vào HALF_OPEN lúc được kiểm tra/được trigger theo chính sách tự chuyển trạng thái; không mặc định cần một background thread.
- Ở HALF_OPEN, cho phép **3 probe calls** để quyết định quay CLOSED hay OPEN.

**Quan trọng:** Circuit breaker tính trên kết quả mà **decorated operation** trả về. Nếu operation bên trong đã retry rồi thành công, breaker ngoài thấy một success. Nếu 404 chưa được ánh xạ thành domain result/exception phù hợp, nó có thể bị đếm theo chính sách recordExceptions.

### 12.2. Đặt tên breaker theo thao tác, không mặc định theo host/port

Ví dụ tên:

~~~text
inventoryRead
inventoryReserve
paymentCapture
catalogSearch
~~~

Các endpoint có đặc tính hoàn toàn khác nhau (GET đọc cache, POST giữ tồn kho, gọi thanh toán) không nên mặc định dùng chung một breaker và fallback. Ngược lại, nếu tạo một breaker mới cho **mỗi request ID**, bạn sẽ không tích lũy được đủ mẫu để đánh giá trạng thái.

Cần chọn khóa breaker **ổn định qua các request cùng operation**, tránh high-cardinality theo user ID, SKU, session ID, trace ID hoặc instance ngắn hạn.

## 13. Ví dụ blocking: RestClient + LoadBalancer + CircuitBreaker

Một cấu hình HTTP client tối thiểu:

~~~java
@Configuration(proxyBeanMethods = false)
class InventoryHttpConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Một adapter dùng circuit breaker cho **read operation**:

~~~java
@Service
class InventoryReader {

    private final RestClient client;
    private final CircuitBreakerFactory<?, ?> breakers;

    InventoryReader(
            @LoadBalanced RestClient.Builder builder,
            CircuitBreakerFactory<?, ?> breakers) {
        this.client = builder.baseUrl("http://inventory-service").build();
        this.breakers = breakers;
    }

    StockResponse read(String sku) {
        return breakers.create("inventoryRead").run(
                () -> client.get()
                        .uri("/api/stock/{sku}", sku)
                        .retrieve()
                        .body(StockResponse.class),
                error -> {
                    // Demo: chuyển lỗi thành domain exception, không trả
                    // số tồn kho giả khi Inventory đang unavailable.
                    throw new InventoryUnavailableException(
                            "Inventory read unavailable", error);
                });
    }
}
~~~

Đoạn này giả định **StockResponse** và **InventoryUnavailableException** do ứng dụng định nghĩa, bean **CircuitBreakerFactory** đã được starter tạo và client có discovery source cho inventory-service. Với production code, nên kiểm tra body null và phân loại 404/409/5xx trước khi chuyển thành domain exception.

**Hạn chế đáng lưu ý:** fallback function trong ví dụ chỉ **ném exception domain**, không tự thực hiện retry. Nếu muốn retry, cần cấu hình LoadBalancer retry hoặc một retry wrapper khác và xác định nó nằm trong hay ngoài breaker.

### 13.1. Không sử dụng fallback đồng loạt với 404

Ví dụ trên cố tình đơn giản nên 404 cũng bị chuyển sang InventoryUnavailableException. Trong hệ thống thật, 404 là SKU không tồn tại có thể cần:

~~~java
try {
    return reader.read(sku);
} catch (StockNotFoundException ex) {
    return Optional.empty();
}
~~~

Một cách đúng hơn là để **HTTP adapter** ánh xạ 404 thành kết quả domain hoặc exception mà breaker được cấu hình **ignore**, rồi breaker chỉ ghi nhận lỗi hạ tầng đúng ý định.

**Đừng copy demo này như một error mapping cuối cùng cho production**. Trách nhiệm của ví dụ là minh họa vị trí bọc circuit breaker quanh RestClient được load balance.

## 14. Ví dụ reactive: WebClient + ReactiveCircuitBreakerFactory

WebClient là HTTP client không blocking; không nên gọi **block()** để bọc nó bằng một circuit breaker đồng bộ trong WebFlux request thread. Spring Cloud có abstraction **ReactiveCircuitBreakerFactory** dành cho Mono/Flux.

~~~java
@Service
class ReactiveInventoryReader {

    private final WebClient webClient;
    private final ReactiveCircuitBreakerFactory<?, ?> breakers;

    ReactiveInventoryReader(
            @LoadBalanced WebClient.Builder builder,
            ReactiveCircuitBreakerFactory<?, ?> breakers) {
        this.webClient = builder
                .baseUrl("http://inventory-service")
                .build();
        this.breakers = breakers;
    }

    Mono<StockResponse> read(String sku) {
        Mono<StockResponse> source = webClient.get()
                .uri("/api/stock/{sku}", sku)
                .retrieve()
                .bodyToMono(StockResponse.class);

        return breakers.create("inventoryRead").run(
                source,
                error -> Mono.error(new InventoryUnavailableException(
                        "Reactive inventory read unavailable", error)));
    }
}
~~~

Đây là mẫu API tương ứng với tài liệu **Spring Cloud Circuit Breaker**: một ReactiveCircuitBreaker bọc Mono/Flux và nhận fallback function để tùy chọn xử lý lỗi. Mỗi subscription có thể kích hoạt một request thật, nên khi thêm retry cần xác định **đặt retry operator ở đâu**.

### 14.1. Retry bên trong hay bên ngoài reactive breaker?

Giả sử có một **Mono cold** thực hiện HTTP request:

~~~java
Mono<StockResponse> source = webClient.get()
        .uri("http://inventory-service/api/stock/{sku}", sku)
        .retrieve()
        .bodyToMono(StockResponse.class);
~~~

Thứ tự A: retry xảy ra trước khi breaker quan sát outcome cuối:

~~~java
Mono<StockResponse> withRetry = source.retryWhen(
        Retry.backoff(1, Duration.ofMillis(100))
                .filter(error ->
                        error instanceof WebClientResponseException ex
                                && ex.getStatusCode().value() == 503));

Mono<StockResponse> protectedCall =
        breakers.create("inventoryRead").run(withRetry);
~~~

Thứ tự B: breaker quan sát từng lần subscribe của source, còn retry ở ngoài:

~~~java
Mono<StockResponse> protectedAttempt =
        breakers.create("inventoryRead").run(source);

Mono<StockResponse> retryOutside = protectedAttempt.retryWhen(
        Retry.backoff(1, Duration.ofMillis(100))
                .filter(error ->
                        error instanceof WebClientResponseException ex
                                && ex.getStatusCode().value() == 503));
~~~

**Vì sao chọn filter 503?** Nó ngăn operator retry gọi lại mọi loại lỗi, đặc biệt **CallNotPermittedException**, lỗi auth hoặc decode schema. Hai đoạn code chỉ minh họa thứ tự; khi Spring Cloud LoadBalancer cũng tự retry, cần **tắt một tầng hoặc kiểm kê cả hai**.

Các import Reactor tương ứng là **reactor.core.publisher.Mono**, **reactor.util.retry.Retry**, **java.time.Duration**. Import cho ReactiveCircuitBreakerFactory thuộc Spring Cloud CircuitBreaker API và WebClientResponseException thuộc Spring WebFlux.

### 14.2. TimeLimiter có thể làm thay đổi kết quả

Nếu ReactiveCircuitBreakerFactory còn áp dụng TimeLimiter theo cấu hình, Mono có thể bị timeout trước khi một số retry hoàn tất. Vì vậy, hãy kiểm tra **timeout của HTTP connector**, **TimeLimiter**, **Reactor timeout operator** và **tổng deadline** cùng nhau. Nếu có nhiều lớp timeout, lỗi nhận được phản ánh lớp đồng hồ nổ trước tiên.

Không nên đặt TimeLimiter 200 ms rồi cấu hình retry hai lần, mỗi lần response timeout 2 giây; hầu hết retries sẽ không có cơ hội hoàn thành, khiến config khó hiểu.

## 15. OpenFeign: load balancing và circuit breaker là hai tích hợp khác nhau

Spring Cloud OpenFeign có thể dùng:

~~~java
@FeignClient(name = "inventory-service")
interface InventoryFeignClient {

    @GetMapping("/api/stock/{sku}")
    StockResponse getStock(@PathVariable("sku") String sku);
}
~~~

Khi có **spring-cloud-starter-loadbalancer**, Feign có thể resolve service ID qua LoadBalancer thay vì URL cố định. Để bọc các method Feign bằng Spring Cloud CircuitBreaker, cần thêm implementation CircuitBreaker tương ứng và bật:

~~~yaml
spring:
  cloud:
    openfeign:
      circuitbreaker:
        enabled: true
~~~

Tài liệu OpenFeign hiện hành nêu thuộc tính **spring.cloud.openfeign.circuitbreaker.enabled** mặc định **false**, nên không thể nói “đã dùng Feign + LoadBalancer thì tự có circuit breaker”. Các breaker name có thể dựa trên tên interface/method và được điều chỉnh bởi CircuitBreakerNameResolver.

### 15.1. Feign retry không mặc định bật như Feign core

Spring Cloud OpenFeign tạo **Retryer.NEVER_RETRY** theo mặc định. Feign core có retry behavior riêng, nhưng Spring Cloud override khi tích hợp. Nếu cần Feign retry, cần khai báo Retryer và điều kiện an toàn một cách có chủ đích.

Khi đã có:

- Retry của Feign,
- Retry của Spring Cloud LoadBalancer,
- CircuitBreaker wrapper,
- Service mesh/proxy retry,

phải kiểm tra số HTTP attempts thật và thứ tự áp dụng. Một lời gọi Java duy nhất có thể tạo nhiều request nếu vài tầng retry bị xếp chồng.

### 15.2. Fallback cho Feign cần hiểu loại lỗi

Spring Cloud OpenFeign hỗ trợ fallback/fallbackFactory khi circuit breaker integration được dùng. Nhưng một fallback trả **StockResponse(sku, 0)** cho mọi lỗi là nguy hiểm: số 0 có thể bị hiểu là chắc chắn hết tồn kho thay vì **không biết do hệ thống đang lỗi**.

Hợp đồng tốt hơn là:

~~~text
StockQueryResult:
  status = FRESH / STALE / UNAVAILABLE
  available = 7 (chỉ có khi nguồn hợp lệ)
  observedAt = ...
~~~

Đối với thao tác **capture payment, place order, reserve stock**, fallback không được giả mạo success hoặc kết quả chưa xác định. Có thể trả **PENDING_RECONCILIATION** theo contract nghiệp vụ và dùng operation ID để kiểm tra sau.

## 16. Circuit breaker phải phân biệt các exception nào?

| Nhóm lỗi | Nguồn | Nên ghi nhận là failure của breaker? | Có nên retry? |
| --- | --- | --- | --- |
| HTTP 503 backend | Server/gateway | Thường có | Có thể, có giới hạn |
| HTTP 502/504 gateway | Proxy | Thường có | Có thể, có giới hạn |
| Connection refused/reset | HTTP transport | Thường có | Có thể |
| Connect/read timeout | HTTP transport/TimeLimiter | Thường có | Cẩn thận side effect |
| ResourceAccessException/WebClientRequestException | Spring client | Phân loại theo root cause | Tùy cause/method |
| HTTP 429 | Rate limiting | Tùy chính sách; có thể coi downstream quá tải | Tôn trọng Retry-After |
| HTTP 400/422 | Contract/input | Thường không | Thường không |
| HTTP 401/403 | Authentication/authorization | Tùy mục tiêu đo lỗi, thường không coi là availability | Thường không |
| HTTP 404 | Resource không tồn tại | Thường không nếu là kết quả domain hợp lệ | Thường không |
| HTTP 409 | Domain conflict | Tùy nghiệp vụ | Không lặp y nguyên |
| JSON mapping/schema lỗi | Client/contract | Có thể cần alert riêng, không hẳn outage instance | Thường không |
| CallNotPermittedException | Breaker OPEN | **Không nên đếm lại như backend failure** | Không retry liên tục |

Ở Spring Framework, **RestClient** thường ném các HttpClientErrorException/HttpServerErrorException từ retrieve(); **WebClient** thường ném WebClientResponseException; **Feign** có FeignException/RetryableException; **RestTemplate** có HTTP/ResourceAccessException. Việc breaker ghi nhận lỗi phụ thuộc loại exception **sau khi** các adapter/wrapper đã xử lý.

Một lựa chọn hợp lý là chuyển lỗi HTTP sang taxonomy domain (NotFound, Conflict, Unavailable, TransportFailure...), rồi cấu hình predicate để **chỉ ghi nhận những loại phản ánh sức khỏe của dependency**.

**Không gắn retry policy vào mọi exception của RestClientException hoặc RuntimeException**. Một lỗi decode response 200 là tín hiệu bất tương thích schema, retry chỉ khiến cùng payload được tải lại.

## 17. Kiểm thử cơ chế riêng lẻ trước khi kiểm thử kết hợp

Một bài integration test gọi hai backend rồi nhận HTTP 200 **chưa đủ** để chứng minh circuit breaker, retry và LoadBalancer phối hợp đúng. Nên kiểm thử mỗi thành phần độc lập, sau đó mới kiểm thử các wrapper kết hợp.

### 17.1. Unit test trực tiếp trạng thái circuit breaker

Resilience4j cung cấp CircuitBreaker có thể kiểm thử mà không cần Spring Context hoặc HTTP:

~~~java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class CircuitBreakerStateTest {

    @Test
    void opensAfterSufficientFailuresAndRejectsNewCalls() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowSize(4)
                .minimumNumberOfCalls(4)
                .failureRateThreshold(50)
                .waitDurationInOpenState(Duration.ofSeconds(30))
                .build();

        CircuitBreaker breaker =
                CircuitBreaker.of("inventoryReadTest", config);

        AtomicInteger executed = new AtomicInteger();

        for (int i = 0; i < 4; i++) {
            assertThrows(IllegalStateException.class, () ->
                    breaker.executeSupplier(() -> {
                        executed.incrementAndGet();
                        throw new IllegalStateException("backend down");
                    }));
        }

        assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
        assertEquals(4, executed.get());

        assertThrows(CallNotPermittedException.class, () ->
                breaker.executeSupplier(() -> {
                    executed.incrementAndGet();
                    return "should-not-execute";
                }));

        // OPEN đã từ chối trước khi supplier được thực thi.
        assertEquals(4, executed.get());
    }
}
~~~

Test chứng minh **breaker từ chối lời gọi khi OPEN**: số lần thực thi thực tế không tăng. Nó **không kiểm tra** service discovery, retry HTTP hoặc LoadBalancer instance selection; đây là unit test trạng thái thuần Resilience4j.

### 17.2. Kiểm thử HALF_OPEN không phụ thuộc sleep

Một test khác có thể chuyển breaker thủ công sang HALF_OPEN:

~~~java
CircuitBreaker breaker = CircuitBreaker.of(
        "recoveryTest",
        CircuitBreakerConfig.custom()
                .slidingWindowSize(4)
                .minimumNumberOfCalls(4)
                .failureRateThreshold(50)
                .permittedNumberOfCallsInHalfOpenState(2)
                .waitDurationInOpenState(Duration.ofSeconds(30))
                .build());

// Trong unit test, chuyển thủ công để tránh chờ đồng hồ thật.
breaker.transitionToHalfOpenState();

assertEquals("ok1", breaker.executeSupplier(() -> "ok1"));
assertEquals("ok2", breaker.executeSupplier(() -> "ok2"));
assertEquals(CircuitBreaker.State.CLOSED, breaker.getState());
~~~

Đây là **kiểm thử state machine**, không mô phỏng chính xác toàn bộ khoảng OPEN wait duration trong production. Nếu cần kiểm tra timer/automaticTransition, viết một test chuyên biệt với clock/scheduler phù hợp và tránh Thread.sleep tùy tiện.

**Quan trọng:** HALF_OPEN không đồng nghĩa toàn bộ traffic được khôi phục. Chỉ một số probe theo cấu hình được phép; những request còn lại có thể bị từ chối tới khi breaker đủ dữ liệu để quyết định CLOSED hay OPEN.

### 17.3. Unit test retry bằng số lần thực thi

Với Reactor Retry:

~~~java
AtomicInteger attempts = new AtomicInteger();

Mono<String> source = Mono.defer(() -> {
    int n = attempts.incrementAndGet();
    return n == 1
            ? Mono.error(new IllegalStateException("transient"))
            : Mono.just("success");
});

Mono<String> result = source.retryWhen(
        Retry.max(1)
                .filter(error ->
                        error instanceof IllegalStateException));

StepVerifier.create(result)
        .expectNext("success")
        .verifyComplete();

assertEquals(2, attempts.get());
~~~

Test trên chứng minh **một lần retry** sau lỗi. Nó không hề chạy qua LoadBalancer. Để test lựa chọn A rồi B, cần gắn retry với supplier/LoadBalancer hoặc WebClient đã có filter thật và quan sát instance đích.

### 17.4. Unit test LoadBalancer với danh sách cố định

Cho danh sách [A, B] bằng một ServiceInstanceListSupplier giả. Test RoundRobinLoadBalancer với một seed xác định, rồi gọi **choose(Request)** và kiểm tra ServiceInstance trả về.

Các điều cần xác minh:

- Khi chỉ có A, luôn chọn A.
- Khi có A và B, lựa chọn luôn nằm trong tập [A, B].
- Khi danh sách rỗng, trả trạng thái **không có server** tương ứng, không tạo địa chỉ giả.
- Khi retry-aware loại A và còn B, có cơ hội chọn B.

Không suy diễn một unit test kiểm tra retryWhen đã chứng minh các lựa chọn instance trên. Bước chọn đích và bước lặp lại là **hai hợp đồng test khác nhau**.

## 18. Integration test A lỗi, B khỏe: đếm HTTP attempts thực sự

### 18.1. Thiết lập

Chạy hai MockWebServer/WireMock ở port động:

~~~text
inventory-a -> localhost:<portA> -> HTTP 503
inventory-b -> localhost:<portB> -> HTTP 200 JSON
~~~

Tạo một supplier cố định hoặc SimpleDiscoveryClient cung cấp:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

Trong integration test thực tế, nên **thay 8081/8082 bằng port động** từ MockWebServer và đăng ký qua **@DynamicPropertySource**. YAML phía trên chỉ minh họa định dạng SimpleDiscoveryClient.

Với WebClient:

1. Đăng ký **@LoadBalanced WebClient.Builder**.
2. Tạo LoadBalancer supplier [A, B] và kiểm soát chính sách chọn instance.
3. Đặt retry tối đa một lần trên HTTP 503.
4. Tắt retry khác ở application/proxy để kết quả không bị nhân.
5. Dùng **RecordedRequest** của hai server để kiểm tra request được gửi ở đâu.

### 18.2. Assertions quan trọng

| Điều kiểm tra | Kỳ vọng |
| --- | --- |
| Request vào A | Đúng 1 lần, trả HTTP 503 |
| Request vào B | Đúng 1 lần, trả HTTP 200 |
| Tổng request mạng | 2, không phải 3 hoặc 4 |
| Phản hồi caller | 200/DTO hợp lệ |
| Retry attempts | Được ghi nhận là 2 |
| Circuit breaker ngoài retry | Một logical success, nếu operation hoàn tất thành công |
| Circuit breaker trong retry | Có thể ghi một failure và một success |
| Sau khi breaker OPEN | New calls bị từ chối trước khi backend nhận request |

**Điều kiện:** chỉ assert A nhận attempt đầu và B nhận attempt hai khi test đã **cố định selection policy**. Nếu vẫn dùng Round Robin với seed/state không xác định, chỉ có thể assert có hai requests đến các instance hợp lệ, không đảm bảo thứ tự A→B.

### 18.3. Phải phân biệt ba loại 503

- **Backend A trả 503 thật:** server A nhận request và phản hồi 503.
- **Gateway trả 503:** gateway nhận request nhưng không tìm/không gọi được upstream.
- **LoadBalancer không có instance:** filter/client có thể tạo tín hiệu lỗi hoặc phản hồi 503/404 trước khi request tới backend.

Cả ba có thể được dịch thành “service unavailable” ở tầng nghiệp vụ, nhưng cách debug, retry và đánh giá tình trạng breaker không nên giống hệt. Hãy theo dõi **request count ở backend, instance ID, trace và nơi sinh status**.

## 19. Integration test khi cả dịch vụ đều lỗi và breaker OPEN

Một kịch bản đáng có trong CI:

1. Mock server A và B đều trả 503 hoặc timeout sau một khoảng nhỏ đã cấu hình.
2. Gửi đủ logical calls để đạt **minimumNumberOfCalls** và **failureRateThreshold**.
3. Kiểm tra circuit breaker chuyển từ CLOSED sang OPEN.
4. Ghi lại tổng HTTP requests trước và sau khi OPEN.
5. Gửi thêm một logical call và xác nhận không có HTTP request mới tới A/B.
6. Xác nhận caller nhận **CallNotPermittedException** hoặc domain fallback phù hợp.
7. Chuyển/đợi HALF_OPEN theo cơ chế test có kiểm soát.
8. Cho một backend trả 200, kiểm tra chỉ số probe được cho phép và trạng thái breaker.

Ví dụ quy tắc số học:

~~~text
slidingWindowSize=10
minimumNumberOfCalls=10
failureRateThreshold=50%

10 logical calls:
    6 lỗi 5xx/timeout
    4 thành công
failureRate = 60% -> OPEN khi đánh giá
~~~

Trong bài test, hãy xem **breaker đo logical calls hay attempts**. Nếu retry ở **bên trong breaker**, một request logic có ba attempts nhưng chỉ cho ra một outcome cuối cùng; số liệu breaker không bằng số HTTP requests ở backend.

### 19.1. Không đếm lỗi breaker OPEN như lỗi backend mới

Một request bị từ chối vì breaker OPEN **không đi tới backend**. Vì vậy, không nên tăng một metric tên “inventory backend 5xx” cho request đó. Tách:

~~~text
inventory_http_5xx
inventory_connect_timeout
inventory_retry_attempts
inventory_circuit_not_permitted
inventory_fallback_used
~~~

Các tên trên là **gợi ý phân loại metric**, không phải tên meter mặc định trong Spring Cloud/Resilience4j. Dùng các meter do thư viện cung cấp khi phù hợp và bổ sung nhãn với cardinality được kiểm soát.

## 20. Observability: xem cả instance, attempts và trạng thái breaker

Khi incident xảy ra, cần trả lời:

1. Lời gọi logic nào thất bại?
2. LoadBalancer đã chọn ServiceInstance nào ở attempt đầu?
3. Retry có thử instance khác không?
4. HTTP client lỗi tại DNS/connect/TLS/read hay nhận HTTP response?
5. Circuit breaker đang CLOSED, OPEN hay HALF_OPEN?
6. Bao nhiêu calls thực sự tới backend và bao nhiêu bị từ chối sớm?
7. Có fallback được sử dụng không? Dữ liệu trả về có phải stale?
8. Thread/connection pool hoặc bulkhead có bị bão hòa không?

Ví dụ event timeline:

~~~text
trace=abc, operation=inventoryRead, breaker=CLOSED
attempt=1, instance=A, outcome=connection_reset, elapsed=90ms
attempt=2, instance=B, outcome=HTTP_200, elapsed=130ms
logicalOutcome=SUCCESS, totalElapsed=270ms
breaker=CLOSED, fallbackUsed=false
~~~

Khi downstream lỗi kéo dài:

~~~text
trace=xyz, operation=inventoryRead, breaker=OPEN
attemptsSent=0, outcome=CALL_NOT_PERMITTED, elapsed=2ms
fallbackUsed=true, fallbackType=CACHED_STOCK, staleAge=8s
~~~

Các log này là **mẫu quan sát**, không phải output mặc định. Không đưa token, cookie, địa chỉ cá nhân, full body hoặc URL có thông tin nhạy cảm vào log.

### 20.1. Một số chỉ số hữu ích

| Nhóm metric | Ý nghĩa |
| --- | --- |
| Logical call success/failure | Chất lượng lời gọi nhìn từ nghiệp vụ |
| HTTP attempts theo service/instance | Retry amplification và instance lỗi |
| Circuit breaker state/gauge | Tỷ lệ dependency đang bị ngắt |
| Failure/slow call rate | Điều kiện breaker chuyển OPEN |
| Not-permitted calls | Số request bị từ chối sớm |
| Retry attempts/exhausted | Hiệu quả/chất lượng retry |
| Timeout per phase | Transport, overall deadline, TimeLimiter |
| Pool active/pending/idle | Nguy cơ thiếu kết nối hoặc chờ acquire |
| Bulkhead permitted/rejected | Quá giới hạn concurrency |
| Fallback rate/staleness | Mức suy giảm chất lượng dữ liệu |

Resilience4j có hỗ trợ metrics qua Micrometer; Spring Boot Actuator/metrics integration cần dependency và cấu hình tương thích. Tránh nhãn metric chứa **SKU, user ID, session hoặc instance ephemeral quá chi tiết** gây high cardinality.

### 20.2. Alert đừng chỉ dựa vào HTTP 200 từ caller

Nếu fallback luôn trả HTTP 200 với cached data, dashboard availability có thể xanh dù Inventory đang hoàn toàn chết. Nên có alert trên:

- Tỷ lệ fallback.
- Staleness của dữ liệu trả về.
- Circuit breaker OPEN duration.
- Số call bị từ chối.
- Retry amplification và P95/P99 latency.
- Instance-level connection errors.

**Success của fallback không đồng nghĩa downstream phục hồi.**

## 21. Một runbook cho incident thực tế

### Tình huống: Order trả 503 tăng, Inventory có 3 instance

Làm theo trình tự:

1. **Xác định phạm vi:** lỗi xảy ra ở mọi Order instance hay chỉ một zone?
2. **Kiểm tra service discovery:** inventory-service có bao nhiêu instance, metadata/health nào được nhìn thấy?
3. **Kiểm tra lựa chọn:** LoadBalancer chọn những instance nào, có tập trung vào bản sao bị lỗi không?
4. **Kiểm tra transport:** backend trả 503 thật hay lỗi connect/timeout/no-instance?
5. **Kiểm tra retry:** số attempts trên một logical call, có retry lồng nhau không, có đổi instance không?
6. **Kiểm tra breaker:** có OPEN không, breaker được đặt theo operation hay per-instance, rate/threshold nào bị vượt?
7. **Kiểm tra tải:** pool pending, CPU, thread, queue, rate limit và bulkhead rejection.
8. **Kiểm tra fallback:** dữ liệu degrade có chấp nhận được không; có ai đang thấy số tồn kho cũ là mới?
9. **Khắc phục:** sửa backend/health/registry, điều chỉnh capacity hoặc cô lập instance theo nguyên nhân thực.
10. **Phục hồi có kiểm soát:** quan sát HALF_OPEN probes, tỷ lệ success và tải tăng trở lại.

**Không phản xạ tăng retry count hoặc tắt circuit breaker khi đang incident**. Nếu toàn bộ Inventory quá tải, hành động đó có thể khiến số HTTP attempts tăng mạnh. Chỉ thay khi có bằng chứng và quan sát được hậu quả.

### 21.1. Khi breaker OPEN nhưng một instance vẫn khỏe

Hỏi:

- Breaker đang đo **toàn service** hay từng instance?
- Tỷ lệ lỗi có bị khuếch đại do retry nằm bên trong/ngoài breaker không?
- Health/zone/hint filter có loại mất instance khỏe không?
- Chính sách retry có bị từ chối trước khi được chọn lại instance không?

Giải pháp không nhất thiết là “tăng waitDurationInOpenState”. Có thể cần sửa fallback, thay vị trí breaker, điều chỉnh nguồn instance hoặc phát hiện backend lỗi trước khi request chạy.

### 21.2. Khi breaker không bao giờ OPEN dù backend chậm

Kiểm tra:

- **minimumNumberOfCalls** có đủ mẫu chưa?
- Slow-call threshold và duration có được cấu hình không?
- HTTP client có timeout để kết thúc lời gọi treo không?
- Fallback ở bên trong breaker có nuốt lỗi và trả success không?
- 503 có bị đổi thành một response domain “thành công” trước khi breaker thấy không?
- Một breaker ID có bị tạo mới cho mỗi request khiến không tích lũy thống kê?

## 22. Các sai lầm phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Coi LoadBalancer là circuit breaker | Instance được chọn vẫn có thể lỗi liên tục | Bổ sung breaker đúng phạm vi |
| Coi retry là failover chắc chắn | Attempt tiếp theo có thể lại chọn instance cũ | Test context retry và RetryAware supplier |
| Retry mọi exception | Retry 400/404/schema error, tăng tải vô ích | Phân loại theo contract |
| Retry ngay không backoff | Retry storm khi downstream lỗi diện rộng | Backoff, jitter, retry budget |
| Dùng breaker để giới hạn concurrency | Breaker CLOSED vẫn cho nhiều request qua | Dùng bulkhead/pool/concurrency limit |
| Đặt breaker ngoài retry rồi đo mỗi attempt bằng breaker metrics | Số liệu breaker chỉ thấy outcome cuối | Thu HTTP attempt metrics riêng |
| Đặt retry ngoài breaker và retry CallNotPermittedException | Gọi lại liên tục dù breaker OPEN | Loại exception đó khỏi retry |
| Circuit breaker per request ID | Không đủ mẫu, số breaker tăng vô hạn | Đặt tên theo service/operation |
| Breaker per-instance không có cleanup | High cardinality/registry stale | Có lifecycle và retention policy |
| Fallback trả success cho POST chưa rõ trạng thái | Duplicate transaction hoặc dữ liệu sai | Idempotency + pending/reconcile |
| 404 làm tăng breaker failure rate | Breaker OPEN vì lỗi nghiệp vụ hợp lệ | Map 404 thành domain result/ignore đúng cách |
| Chỉ đặt connect timeout | Response chậm vẫn giữ tài nguyên | Read/response timeout + deadline |
| Bật nhiều tầng retry | Attempts nhân lên không kiểm soát | Chỉ định một tầng retry chủ đạo |
| Bật CB OpenFeign chỉ vì có starter LB | Feign CB có flag riêng | Bật và test spring.cloud.openfeign.circuitbreaker.enabled |
| Dùng fallback nhưng không đo degradation | HTTP 200 che downstream outage | Metric fallback/stale age |
| Tăng retries khi 503 toàn hệ thống | Thêm tải vào backend đang quá tải | Cắt retry, bảo vệ bằng breaker/bulkhead và sửa backend |

## 23. Bài tập thực hành có đáp án

### 23.1. Tình huống A: một instance lỗi

~~~text
Supplier = [A, B, C]
A = connection refused
B = 200
C = 200
Retry = tối đa 1 lần, tránh previous instance
Breaker = CLOSED
~~~

**Câu hỏi:** Sau khi chọn A và lỗi, cơ chế nào cần để thử B/C? Circuit breaker có tự chuyển đích không?

**Đáp án:** retry quyết định thử lại; LoadBalancer chọn instance trong danh sách ứng viên mới, retry-aware có thể tránh A. Circuit breaker chỉ cho phép/ghi nhận outcome; nó **không tự chọn B**.

### 23.2. Tình huống B: toàn bộ backend lỗi

~~~text
10 logical calls
Mỗi call tối đa 2 attempts
Cả A và B đều HTTP 503
Breaker ngoài retry
minimumNumberOfCalls = 10
failureRateThreshold = 50%
~~~

**Câu hỏi:** Backend có thể nhận bao nhiêu attempts trước khi breaker OPEN? Breaker ghi nhận bao nhiêu outcomes?

**Đáp án:** nếu cả 10 calls đều chạy đủ 2 attempts và không có giới hạn khác, backend có thể nhận **20 attempts**; breaker ngoài retry ghi **10 logical failures**, đủ mở khi tỷ lệ lỗi đạt 100%. Trong môi trường thật, trạng thái breaker có thể chuyển ở thời điểm một call hoàn tất, nên phải đo chính xác concurrency và thứ tự completion.

### 23.3. Tình huống C: POST bị timeout

~~~text
Attempt 1: POST /reservations -> timeout sau 900ms
Server có thể đã commit
Retry policy: thêm 1 attempt
~~~

**Câu hỏi:** Có nên retry sang instance khác ngay không?

**Đáp án:** Chỉ khi backend hỗ trợ **idempotency key** và cơ chế deduplication phù hợp. Nếu chưa có, cần đối soát bằng operation ID hoặc trả trạng thái pending/unknown, không giả mạo thất bại hoặc thành công.

### 23.4. Tình huống D: breaker OPEN, retry vẫn tăng

~~~text
Breaker OPEN
Retry ở ngoài breaker
Retry predicate = tất cả RuntimeException
~~~

**Câu hỏi:** Điều gì có thể xảy ra?

**Đáp án:** Retry có thể lặp **CallNotPermittedException** nhiều lần, dù không có HTTP attempt thật. Điều này lãng phí CPU, kéo dài latency và gây nhiễu metrics. Sửa predicate để loại CallNotPermittedException và áp dụng fallback/fast-fail đúng contract.

### 23.5. Tình huống E: nhiều request bị kẹt, breaker CLOSED

~~~text
500 concurrent calls
Inventory chưa báo lỗi, phản hồi rất chậm
Breaker vẫn CLOSED
~~~

**Câu hỏi:** Dùng cơ chế nào trước?

**Đáp án:** **timeout/deadline** để lời gọi không kéo dài vô hạn; **bulkhead/pool limit** để giới hạn concurrency; sau đó cấu hình **slowCallRateThreshold** để circuit breaker có thể ngắt khi đủ dữ liệu. LoadBalancer/Retry một mình không xử lý được pool starvation.

## 24. Checklist thiết kế trước production

- [ ] Biết rõ **LoadBalancer** chọn instance, **Retry** lặp attempt, **CircuitBreaker** cho phép/từ chối.
- [ ] Đặt ServiceInstanceListSupplier/discovery/health rõ ràng; không đoán registry trạng thái.
- [ ] Retry chỉ áp dụng cho status/exception/method an toàn, có max attempts.
- [ ] Có backoff/jitter, retry budget và **overall deadline**.
- [ ] Không retry lồng nhau giữa HTTP client, LoadBalancer, Feign, Reactor và service mesh.
- [ ] Retry-aware đủ context nếu muốn tránh instance vừa lỗi; không hứa chắc sẽ đổi instance.
- [ ] Circuit breaker có tên ổn định theo service/operation và chính sách record/ignore exceptions.
- [ ] Hiểu tác động của breaker **ngoài retry** so với **trong retry**.
- [ ] Không retry CallNotPermittedException khi breaker OPEN.
- [ ] Có giới hạn concurrency bằng bulkhead/pool nếu cần, không dùng breaker để thay.
- [ ] TimeLimiter/connect/read timeout và deadline có ngân sách nhất quán.
- [ ] Fallback chỉ trả dữ liệu hợp lệ; dữ liệu cached phải có thông tin stale/freshness.
- [ ] POST/PUT có side effect được thiết kế idempotency và xử lý kết quả chưa rõ.
- [ ] Có unit test riêng cho LB, retry và breaker state machine.
- [ ] Có integration test thật khi A lỗi B khỏe, toàn dịch vụ lỗi, OPEN/HALF_OPEN.
- [ ] Đếm **HTTP attempts** ở backend, không chỉ logical calls ở client.
- [ ] Tracing/metrics tách no-instance, transport, 4xx/5xx, retry, breaker OPEN, fallback.
- [ ] Không log authorization token, cookie hoặc dữ liệu nhạy cảm.
- [ ] Xác minh hành vi theo BOM/release train, vì starter và auto-configuration khác nhau.

## 25. Kết luận

**Load balancing, retry và circuit breaker là ba lớp bảo vệ bổ sung, không phải ba tên gọi của cùng một chức năng.** LoadBalancer tìm bản sao thích hợp và tái dựng URI vật lý; retry thực hiện lại lời gọi khi lỗi có thể phục hồi; circuit breaker quan sát thống kê và tạm ngừng cho phép những lời gọi đang gây tổn hại. Timeout kiểm soát thời gian chờ, bulkhead cô lập tài nguyên và fallback quyết định trải nghiệm nghiệp vụ khi dependency không sẵn sàng.

Để vận hành an toàn, hãy **phân loại lỗi theo HTTP contract, giới hạn retry bằng attempts/backoff/deadline, xác định breaker nhìn logical call hay từng attempt và kiểm thử cả hành vi chọn instance lẫn số HTTP requests thật**. Với request có side effect, không bao giờ coi timeout là bằng chứng backend chưa xử lý; cần idempotency và đối soát.

Một hệ thống có khả năng phục hồi tốt không phải hệ thống “retry nhiều nhất”, mà là hệ thống **gửi đúng nơi, thử lại có điều kiện, ngắt đúng lúc, giảm tải có kiểm soát và trả kết quả trung thực**.

## 26. Tài liệu tham khảo

- [Spring Cloud LoadBalancer – Reference](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): ServiceInstanceListSupplier, load-balancing policies, retry và retry-aware supplier.
- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): @LoadBalanced HTTP clients và retry.
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): retry.enabled, max-retries-on-*, retryable-status-codes và related properties.
- [Spring Cloud Circuit Breaker – Abstraction](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-circuitbreaker.html): CircuitBreakerFactory/ReactiveCircuitBreakerFactory và fallback.
- [Spring Cloud CircuitBreaker – Resilience4j](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html): starters, Java config, TimeLimiter, metrics và bulkhead integration.
- [Spring Cloud CircuitBreaker – Properties](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j/circuit-breaker-properties-configuration.html): circuitbreaker/timelimiter configs và độ ưu tiên.
- [Spring Cloud CircuitBreaker – Bulkhead](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j/bulkhead-pattern-supporting.html): SemaphoreBulkhead và ThreadPoolBulkhead.
- [Spring Cloud OpenFeign – Reference](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): FeignBlockingLoadBalancerClient, Retryer.NEVER_RETRY và circuit breaker opt-in.
- [Resilience4j – CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker): CLOSED/OPEN/HALF_OPEN, sliding window, failure/slow rate và CallNotPermittedException.
- [Resilience4j – Retry](https://resilience4j.readme.io/docs/retry): maxAttempts, retryOnException, result predicate, backoff và interval functions.
- [Resilience4j – Getting Started](https://resilience4j.readme.io/docs/getting-started-3): decorator ordering, annotation AOP và cách compose policies.
- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient error semantics và HTTP transport.
- [Spring Framework – WebClient retrieve](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-retrieve.html): HTTP error handling của WebClient.
- [Reactor – Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): retryWhen, error mapping và operator semantics.
- [Reactor – Testing](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier/virtual time để kiểm thử reactive retry và errors.

