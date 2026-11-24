# Khoảng chờ tăng dần và giới hạn tổng thời gian xử lý trong Spring Cloud Gateway

Khi một microservice tạm thời trả `503 Service Unavailable` hoặc Gateway không kết nối được đến một instance, **thử lại request (retry)** có thể cứu một yêu cầu mà không cần khách hàng gọi lại. Nhưng retry quá nhanh khiến backend đang quá tải càng khó phục hồi; retry quá lâu lại khiến client hết thời gian chờ. Vì vậy cần thiết kế **khoảng chờ tăng dần (exponential backoff)** đi kèm **ngân sách thời gian xử lý tổng thể (end-to-end time budget/deadline)**.

Trong **SPRING_CLOUD_GATEWAY**, `Retry` GatewayFilter Factory điều khiển số lần thử lại, nhóm status/exception, method và backoff. Tuy nhiên, **`maxBackoff` chỉ giới hạn một khoảng chờ giữa các lượt, không tự giới hạn thời gian hoàn tất toàn bộ request**. Đây là khác biệt quan trọng nhất của bài học thuộc chương **Thử lại yêu cầu**.

Bài kết nối retry với route predicates, filter chain, đường dẫn/header, service discovery/load balancing, xác thực, rate limiting, circuit breaker, TLS và quan sát request: một request của client có thể biến thành **nhiều outbound attempts**, nên các lớp này cần phối hợp chặt chẽ.

> **Phạm vi phiên bản:** Ví dụ hướng tới **Spring Cloud Gateway Server WebFlux** và cú pháp `spring.cloud.gateway.routes` phổ biến ở một số dòng Gateway 4.x. Gateway Server MVC và những dòng phát hành mới có thể có tên starter, namespace, DSL hoặc chi tiết hỗ trợ khác. Kiểm tra phiên bản Spring Boot/Spring Cloud/Gateway thực tế trước khi triển khai. Các timeout và hạn mức ở đây chỉ phục vụ bài học, không phải khuyến nghị áp dụng chung cho mọi API.

## 1. Một lần thử lại nghĩa là bao nhiêu lần gọi backend?

Trong cấu hình `Retry`, tham số `retries` biểu thị **số lần thử lại sau lần gọi ban đầu**, không phải tổng số lượt gọi.

| `retries` | Lần gọi ban đầu | Số lượt retry tối đa | Tổng attempts tối đa |
|---:|---:|---:|---:|
| 0 | 1 | 0 | 1 |
| 1 | 1 | 1 | 2 |
| 2 | 1 | 2 | 3 |
| 3 | 1 | 3 | 4 |
| 5 | 1 | 5 | 6 |

Con số trên là **trần theo cấu hình**, không phải cam kết tất cả lần retry đều xảy ra: nếu lần đầu thành công, Gateway không cần retry. Nếu response không thuộc nhóm status cho phép retry, method không phù hợp, exception không khớp hoặc request đã không còn khả năng gửi lại, filter cũng có thể không retry.

Ví dụ:

~~~text
Client gửi 1 request GET /api/catalog/42
   attempt #1 -> backend trả 503
   attempt #2 -> backend trả 503
   attempt #3 -> backend trả 200

retries=2 là đủ để thử tối đa 3 attempts.
Client thường chỉ nhận response cuối (200) nếu chưa có response nào bị commit.
~~~

Điều này ảnh hưởng capacity: **1 request ở mép Gateway có thể tạo 3 request tới downstream**. Một bảng dashboard chỉ đếm HTTP requests từ client mà không đếm downstream attempts sẽ đánh giá thấp mức tải thật.

### Retry và CircuitBreaker không giống nhau

| Cơ chế | Mục tiêu | Câu hỏi nó trả lời |
|---|---|---|
| **Retry** | Thử lại lỗi tạm thời khi còn cơ hội thành công | *Thử thêm một lần có đáng không?* |
| **Backoff** | Giãn khoảng cách giữa các lượt retry | *Nếu thử lại, nên chờ bao lâu?* |
| **Timeout** | Giới hạn thời gian của một hoạt động/attempt | *Một lượt được phép chờ bao lâu?* |
| **Overall deadline** | Chặn toàn bộ chuỗi vượt ngân sách | *Còn bao nhiêu thời gian cho cả request?* |
| **CircuitBreaker** | Ngừng gọi tạm thời khi downstream có lỗi hệ thống | *Có nên gọi downstream lúc này không?* |
| **Rate limiter** | Kiểm soát lưu lượng được phép từ client | *Đây là lưu lượng của ai và có vượt ngưỡng không?* |

Không một cơ chế riêng lẻ nào thay thế được toàn bộ các cơ chế còn lại.

## 2. Vì sao retry cần khoảng chờ tăng dần?

Nếu 1.000 Gateway requests đều nhận lỗi trong cùng một thời điểm, việc mỗi request retry **ngay lập tức** có thể khiến backend bị thêm hàng nghìn cuộc gọi nữa đúng lúc nó đang quá tải: hiện tượng **retry storm** hay **thundering herd**.

Khoảng chờ tăng dần cho downstream thời gian hồi phục và giảm mật độ attempt.

Ví dụ backoff tăng theo hệ số 2:

~~~text
Attempt 1 lỗi
    chờ 100 ms
Attempt 2 lỗi
    chờ 200 ms
Attempt 3 lỗi
    chờ 400 ms
Attempt 4 lỗi
    chờ 500 ms (bị chặn bởi maxBackoff)
Attempt 5 ...
~~~

Đặt:

- `firstBackoff = 100ms`: khoảng chờ cơ sở.
- `factor = 2`: hệ số tăng.
- `maxBackoff = 500ms`: khoảng chờ **tối đa giữa hai lượt**.
- `basedOnPreviousValue = false`: lựa chọn cách tính theo mốc cơ sở và số lần lặp theo contract của factory.

Với mô hình minh họa, khoảng chờ thứ `i` có thể diễn giải:

\[
d_i = \min\left(d_{\max},\;d_0\times f^{i-1}\right),\quad i=1,2,\ldots,r
\]

Trong đó `r` là số lần retry **thực sự có thể xảy ra**, `d_0` là `firstBackoff` và `f` là `factor`. Cách triển khai chính xác của chỉ số vòng lặp và `basedOnPreviousValue` có thể khác đôi chút giữa các phiên bản; kiểm chứng bằng log timestamp.

| Retry lần | Chờ theo cấp số nhân chưa cap | Chờ sau giới hạn `maxBackoff=500ms` | Tổng thời gian chờ tích lũy |
|---:|---:|---:|---:|
| 1 | 100 ms | 100 ms | 100 ms |
| 2 | 200 ms | 200 ms | 300 ms |
| 3 | 400 ms | 400 ms | 700 ms |
| 4 | 800 ms | 500 ms | 1.200 ms |
| 5 | 1.600 ms | 500 ms | 1.700 ms |

Bảng là **dự toán khoảng chờ**, chưa tính thời gian attempt, network, serialization, authentication, chọn instance hay phản hồi cho client.

### `maxBackoff` không phải `totalTimeout`

Với `maxBackoff=500ms`, bạn **chỉ chặn từng lần chờ ở mức xấp xỉ 500ms**. Nếu có nhiều lần retry hoặc mỗi attempt mất hàng giây, tổng thời gian xử lý vẫn có thể rất dài. Đây là lỗi thiết kế phổ biến khi chỉ nhìn ba tham số `firstBackoff`, `factor` và `maxBackoff`.

## 3. Cấu hình Retry với exponential backoff

Giả sử Gateway lắng nghe `localhost:8080` và một catalog backend (chỉ đọc) lắng nghe `localhost:9090`. Chọn chỉ retry `GET` trên một số lỗi hạ tầng tạm thời:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-read
          uri: http://localhost:9090
          predicates:
            - Path=/api/catalog/**
            - Method=GET
          filters:
            - StripPrefix=1
            - name: Retry
              args:
                retries: 3
                statuses:
                  - BAD_GATEWAY
                  - SERVICE_UNAVAILABLE
                  - GATEWAY_TIMEOUT
                methods:
                  - GET
                backoff:
                  firstBackoff: 100ms
                  maxBackoff: 500ms
                  factor: 2
                  basedOnPreviousValue: false
~~~

Với request `GET /api/catalog/items/42`:

1. `Path` và `Method` predicates phải match trước khi route filters chạy.
2. `StripPrefix=1` định hình path downstream là `/catalog/items/42`.
3. `Retry` được cấu hình retry tối đa ba lượt **sau lần gọi ban đầu**.
4. Chỉ các **status** đã liệt kê và điều kiện khác phù hợp mới được retry theo chính sách này.
5. Giữa các lượt retry, filter áp dụng backoff.
6. Nếu các attempts đều thất bại, request cuối cùng trả lỗi theo cơ chế Gateway/downstream/error handling, không phải tự động có fallback JSON.

**Tên status** trong `statuses` là các giá trị tương thích enum HTTP status được factory hỗ trợ ở phiên bản đó. Mã `502`, `503`, `504` được chọn vì có thể biểu thị sự cố tạm thời, nhưng **không phải mọi 5xx đều retry an toàn**. Ví dụ 500 do lỗi nghiệp vụ hoặc bug lặp lại sẽ khó được giải quyết bằng thử thêm.

### Các tham số của Retry factory

| Tham số | Vai trò | Điểm cần chú ý |
|---|---|---|
| `retries` | Số lượt retry tối đa | Tổng attempts = 1 + retries |
| `statuses` | Các HTTP status cụ thể cho phép retry | Không tự mở rộng sang mọi status |
| `series` | Nhóm status (ví dụ 5xx) theo phiên bản | Dễ quá rộng nếu nghiệp vụ không phân biệt lỗi |
| `methods` | HTTP methods được retry | Chỉ đưa method phù hợp tính idempotent |
| `exceptions` | Các loại ngoại lệ được retry | Phải kiểm tra exception thật và inheritance của class |
| `backoff.firstBackoff` | Khoảng chờ đầu | Một Duration, ví dụ `100ms` |
| `backoff.maxBackoff` | Cap cho từng khoảng chờ | **Không phải tổng deadline** |
| `backoff.factor` | Hệ số tăng | Không nên chọn quá lớn dẫn tới chờ dài |
| `backoff.basedOnPreviousValue` | Cách tính bước kế từ khoảng chờ trước/mốc cơ sở | Cần thử thực tế khi bật `true` |

Thông thường, Retry factory hỗ trợ cả retry theo **HTTP status** và theo **exception** xảy ra trong routing. Vì exception cụ thể có thể đến từ Reactor Netty, LoadBalancer hoặc custom filter, không nên mặc định mỗi lần `java.util.concurrent.TimeoutException` hoặc `IOException` đều được gom giống nhau ở mọi cấu hình.

### Dạng shortcut và expanded

Với filter cần nhiều tham số và block `backoff`, **expanded form** dưới `name: Retry` / `args:` dễ đọc và ít nhầm hơn. Đừng trộn các tham số Retry vào một chuỗi shortcut tùy tiện rồi hy vọng framework hiểu được mọi trường.

## 4. `basedOnPreviousValue` và jitter: hai khái niệm khác nhau

Trong factory, `basedOnPreviousValue` điều khiển cách backoff có tham chiếu **giá trị chờ lần trước** hay tính từ tham số cơ sở theo vòng lặp. Với factor và max cap như nhau, những chuỗi đầu tiên có thể giống nhau; không nên tự suy rằng bật `true` là bật ngẫu nhiên.

**Jitter** là phần biến thiên ngẫu nhiên có kiểm soát để các clients/Gateway instances không cùng retry đúng một mốc giờ.

Ví dụ ý tưởng:

~~~text
Không jitter:
  Node A: chờ 100, 200, 400 ms
  Node B: chờ 100, 200, 400 ms
  Node C: chờ 100, 200, 400 ms

Có jitter (minh họa):
  Node A: chờ  87, 180, 350 ms
  Node B: chờ 121, 215, 430 ms
  Node C: chờ  94, 239, 386 ms
~~~

**Không mặc định Retry GatewayFilter Factory có một thuộc tính YAML `jitter` trong mọi phiên bản.** Nếu cần jitter hoặc deadline-aware retry mà factory hiện có không cung cấp, thiết kế custom reactive retry policy (ví dụ Reactor retry API) hoặc đặt resilience tại client downstream có hỗ trợ, rồi kiểm thử tránh retry hai lần ở hai tầng.

Khi thêm jitter, vẫn phải bảo đảm **không chờ vượt ngân sách tổng**. Jitter không phải lý do để bỏ deadline.

## 5. Công thức tính tổng thời gian: attempts + backoff + overhead

Gọi:

- `A = retries + 1` là số attempts tối đa.
- `t_i` là thời gian của attempt `i`, bao gồm thời gian chờ/processing tương ứng.
- `d_j` là backoff trước lần retry thứ `j`.
- `h` là chi phí chung: auth, route/filter chain, serialize, metrics, network/client-facing response và các thành phần còn lại.
- `T_total` là thời gian từ lúc Gateway nhận request đến khi hoàn tất (hoặc bị hủy).

Một mô hình dự toán:

\[
T_{total} \approx \sum_{i=1}^{A}t_i
  + \sum_{j=1}^{A-1}d_j + h
\]

Đây là **mô hình dự toán**; trong thực tế một request có thể hoàn tất sớm, các bước chồng lấn, hoặc bị hủy theo deadline. Khi mọi attempt có upper bound `t_attempt` và các backoff bounded, trần lý thuyết trước overhead có dạng:

\[
T_{max,estimate} \approx A\cdot t_{attempt}
   + \sum_{j=1}^{A-1}d_j
\]

### Ví dụ: per-attempt 800ms, 3 retries

Với:

~~~yaml
retries: 3
backoff:
  firstBackoff: 100ms
  maxBackoff: 500ms
  factor: 2
  basedOnPreviousValue: false
~~~

Giả sử **mỗi attempt có một giới hạn 800ms được thực thi thật** (không chỉ cấu hình mà chưa chứng minh tác dụng):

| Lượt | Thời gian attempt nhiều nhất | Backoff trước lượt | Thời gian tích lũy, chưa tính overhead |
|---|---:|---:|---:|
| Attempt 1 | 800 ms | — | 800 ms |
| Attempt 2 | 800 ms | 100 ms | 1.700 ms |
| Attempt 3 | 800 ms | 200 ms | 2.700 ms |
| Attempt 4 | 800 ms | 400 ms | **3.900 ms** |

Như vậy, một API có mục tiêu **3 giây** vẫn có thể bị vượt dù `maxBackoff=500ms`. Sau khi cộng chi phí của Gateway và network, tổng còn lớn hơn.

**Nếu chỉ cho 2 retries**, dự toán với cùng dữ liệu:

\[
3\times800\text{ ms} + (100+200)\text{ ms}
= 2.700\text{ ms}
\]

Còn khoảng **300ms trước mốc 3 giây** cho overhead nếu tất cả giả định đều đúng. Đó là biên rất mỏng khi mạng biến động; cần đo P95/P99 và để safety margin, không lập kế hoạch tiêu hết toàn bộ SLA.

### Lập kế hoạch với budget

Một cách thiết kế hữu ích:

~~~text
Deadline tổng client/Gateway:          3000 ms
Dự phòng cho Gateway, network, encode:  400 ms
Ngân sách còn lại cho attempts + wait: 2600 ms

Ví dụ chỉ 2 retries:
  3 attempts x 700 ms             = 2100 ms
  2 backoffs (100 + 200)           =  300 ms
  Tổng có dự toán                 = 2400 ms
  Dư trong ngân sách retry         =  200 ms
~~~

Con số chỉ là **bài toán minh họa**, không phải guarantee nếu timeout thực tế không thực thi, body bị streaming, backend có handshakes dài hoặc proxy đợi thêm dữ liệu.

## 6. Phân biệt timeout của từng attempt và tổng deadline

Ở Spring Cloud Gateway Server WebFlux dùng Reactor Netty, có thể cấu hình HTTP client timeout toàn cục (các thuộc tính tùy version):

~~~yaml
spring:
  cloud:
    gateway:
      httpclient:
        connect-timeout: 1000
        response-timeout: 800ms
~~~

Thông thường:

- `connect-timeout` giới hạn thời gian **thiết lập kết nối** theo HTTP client tương ứng; ở những dòng này, giá trị global thường theo **mili giây**.
- `response-timeout` là thời lượng chờ phản hồi của HTTP client theo contract Netty/Gateway và được biểu diễn là **Duration** ở cấu hình toàn cục.
- **Không xem response-timeout là giới hạn end-to-end từ lúc client gửi request đến khi client nhận body xong.** Nó áp dụng ở lớp outbound HTTP client với ngữ nghĩa cụ thể của version, có thể không bao trùm tất cả thời gian route matching, queueing, retry waits, DNS, streaming và downstream xử lý toàn bộ response.

Có những dòng Gateway hỗ trợ timeout theo route bằng metadata:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-read
          uri: http://localhost:9090
          predicates:
            - Path=/api/catalog/**
          metadata:
            connect-timeout: 1000
            response-timeout: 800
          filters:
            - name: Retry
              args:
                retries: 2
                statuses:
                  - SERVICE_UNAVAILABLE
                methods:
                  - GET
                backoff:
                  firstBackoff: 100ms
                  maxBackoff: 200ms
                  factor: 2
~~~

**Chú ý đơn vị:** trong mô hình cấu hình WebFlux này, `response-timeout` của **route metadata** thường dùng **mili giây**, khác với `response-timeout: 800ms` của **global HTTP client** vốn là Duration. Không tự giả định hai vị trí chấp nhận cùng kiểu. Thử startup, kiểm tra effective configuration và request thực trước khi triển khai.

### Ba loại thời gian thường bị gộp thành một

| Giới hạn | Bảo vệ điều gì? | Có bảo đảm tổng thời gian nhiều attempts? |
|---|---|---|
| Connect timeout | Không chờ kết nối đến upstream vô hạn | **Không** |
| Response/read timeout của outbound HTTP client | Không chờ upstream phản hồi quá lâu theo semantics client | **Không**, có thể áp dụng cho từng lần gọi |
| End-to-end deadline | Toàn bộ công việc từ Gateway nhận request đến khi phải hoàn tất/hủy | **Có**, nếu thiết kế và thực thi thật sự bao trùm retry chain |

Bổ sung timeout tại **backend**, **reverse proxy/ingress**, **API client** và có thể cả **load balancer**. Đảm bảo các tầng không mâu thuẫn: nếu client timeout sau 2 giây nhưng Gateway vẫn retry đến 8 giây, nhiều outbound calls trở nên vô ích và có thể gây quá tải.

## 7. Thiết kế deadline tổng cho một chuỗi retry

**Retry factory không nên được hiểu là một bộ lập lịch tự động quan tâm đến deadline tổng.** Ngay cả khi có `maxBackoff`, cần một cơ chế khác để giới hạn **toàn bộ chuỗi**.

### Nguyên tắc deadline-aware

Tại thời điểm nhận request, tính:

~~~text
deadline = startTime + totalBudget

Trước mỗi attempt hoặc lần sleep tiếp theo:
  remaining = deadline - now

  Nếu remaining <= safetyMargin:
      dừng retry, kết thúc theo policy

  Nếu nextBackoff + expectedAttemptBudget > remaining - safetyMargin:
      không lên lịch thêm attempt

  Ngược lại:
      chờ backoff trong ngân sách,
      thực hiện attempt với timeout <= remaining
~~~

Đây là **pseudocode về chính sách**, không phải cấu hình có sẵn của `Retry` GatewayFilter Factory. Nếu hệ thống cần logic chính xác theo `remaining`, hãy triển khai bằng thành phần reactive phù hợp và kiểm thử cancellation/response commit/exception mapping.

### Các lựa chọn triển khai

1. **Thiết kế ngưỡng đủ nhỏ và một overall timeout ở tầng ngoài:** đặt số retry, timeout từng attempt, backoff sao cho tổng worst-case có biên an toàn; đồng thời ingress/client/proxy có deadline rõ ràng.
2. **Reactive wrapper/deadline policy tùy biến:** một `GlobalFilter`/`GatewayFilter` được đặt **bao ngoài chuỗi Retry** có thể áp overall timeout qua Reactor, miễn là thứ tự thực thi được xác minh và response chưa commit. Cần xử lý hủy, HTTP status và cleanup đúng cách.
3. **Truyền deadline còn lại đến downstream qua hợp đồng nội bộ đã xác minh:** chỉ trust header deadline sau khi ingress/Gateway đã chuẩn hóa; backend ngừng công việc khi vượt hạn và không dựa vào timestamp client tự gửi.
4. **Đưa retry vào client library/backend khi phù hợp:** khi chính service nắm rõ idempotency, budget và domain failures hơn Gateway.

**Cảnh báo khi dùng `Mono.timeout(Duration)`:** nó ràng buộc lifecycle của một publisher reactive; không tự bảo đảm backend đã dừng side effect, response chưa commit hoặc mọi socket/công việc ngoài Reactor đều hủy được ngay. Nếu timeout xảy ra sau khi HTTP response đã commit, không thể luôn thay status/body. Đây là lý do một custom timeout filter đòi integration test và kiểm tra phiên bản.

### Đặt tổng budget ở đâu?

- **Client budget** quyết định khi nào khách hàng không còn chờ nữa.
- **Ingress/Gateway budget** nên ngắn hơn hoặc phù hợp client, giữ một khoảng cho truyền response về.
- **Downstream budget** nên nhận phần thời gian còn lại, không bắt đầu một giao dịch mới nếu kết quả chắc chắn đến quá muộn.
- **Operational timeout** có thể chủ động từ chối thay vì giữ request chờ vô hạn.

Nếu business API là tác vụ dài, cân nhắc mô hình **202 Accepted + job ID/polling hoặc webhook**, thay vì tăng timeout và retry một HTTP request đồng bộ tới hàng chục giây.

## 8. Timeline minh họa: khi nào retry trở thành vô ích?

Giả sử client có timeout 2,5 giây, Gateway cấu hình 3 retries, và mỗi lần downstream chờ gần 800ms:

~~~mermaid
flowchart LR
    A["0–800 ms: Attempt 1"] --> B["800–900 ms: Backoff 100 ms"]
    B --> C["900–1700 ms: Attempt 2"]
    C --> D["1700–1900 ms: Backoff 200 ms"]
    D --> E["1900–2700 ms: Attempt 3"]
    E -.-> F["2500 ms: Client deadline xảy ra khi attempt 3 chưa xong"]
    E --> G["2700–3100 ms: Backoff 400 ms"]
    G --> H["3100–3900 ms: Attempt 4 nếu chưa bị hủy"]
~~~

*Sơ đồ mô tả các mốc milliseconds tương đối của từng giai đoạn (không phải dữ liệu đo). Deadline 2.500ms nằm giữa attempt thứ ba, trong khi kế hoạch retry chưa bị giới hạn tổng có thể kéo dài đến 3.900ms.*

Đến **2.500ms**, client có thể đã bỏ cuộc, nhưng Retry chain dự kiến còn attempt 3 và các bước sau. Nếu tầng Gateway không tôn trọng cancellation/deadline, backend tiếp tục nhận tải mà không còn người dùng đợi kết quả.

**Kết luận:** không nên lấy số `retries` lớn làm cơ chế “tăng độ tin cậy” mặc định. Hãy quyết định theo **latency SLO, xác suất lỗi tạm thời, idempotency và sức chứa backend**.

## 9. Retry method nào là an toàn?

HTTP method chỉ là một **tín hiệu sơ bộ**, không đủ chứng minh replay an toàn. Đặc biệt nguy hiểm khi client chưa nhận response nhưng backend đã xử lý thành công rồi kết nối bị ngắt; retry có thể lặp lại side effect.

| Method | Tính chất thường được mong đợi | Khuyến nghị tại Gateway |
|---|---|---|
| `GET` | Đọc, idempotent theo semantics HTTP | Phù hợp retry lỗi hạ tầng **nếu backend thực sự không có side effect quan trọng** |
| `HEAD` | Đọc metadata | Có thể retry theo contract |
| `PUT` | Semantics idempotent khi cùng request tạo trạng thái mong muốn | Chỉ bật sau khi xác minh nghiệp vụ, concurrency và body replay |
| `DELETE` | Semantics idempotent nhưng response có thể khác sau lần đầu | Cân nhắc trạng thái đích và phản hồi khi đã xóa |
| `POST` | Thường tạo resource/thanh toán; không idempotent mặc định | **Không bật retry mù quáng** |
| `PATCH` | Có thể không idempotent | Chỉ retry khi thiết kế operation và deduplication rõ |

### Vì sao POST thanh toán dễ bị tính tiền hai lần?

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway Retry
    participant P as Payment backend
    C->>G: POST /payments
    G->>P: Attempt 1
    P->>P: Ghi giao dịch thành công
    P--xG: Response thất lạc / kết nối đứt
    Note over G: Gateway không biết backend đã ghi hay chưa
    G->>P: Attempt 2
    P->>P: Có nguy cơ ghi thêm giao dịch
    P-->>G: Response
    G-->>C: Status cuối
~~~

Để cho phép retry POST trong một trường hợp thật sự cần thiết, backend cần cơ chế **idempotency key** hoặc request ID đáng tin, deduplicate/transactional guarantee và chính sách xử lý kết quả cho những attempt trùng. Chỉ gắn header `Idempotency-Key` ở Gateway không đủ: **backend phải thực thi semantics idempotent** và bảo vệ kho kết quả khỏi concurrency.

### Body replay và memory

Retry request có body có thể cần **cache/buffer body** để gửi lại. Trong Gateway Server WebFlux, retry với các method có body có thể khiến request body được giữ trong bộ nhớ (ở một số implementation thông qua exchange attribute như `CACHED_REQUEST_BODY_ATTR` và `DataBuffer`). Nếu cho retry các upload lớn hoặc JSON payload lớn ở mức lưu lượng cao, Gateway có thể chịu áp lực heap/direct memory.

**Không dùng retry POST/upload chỉ vì một lần GET thử nghiệm thành công.** Kiểm tra memory, max request size, backpressure, replayability, cancellation và hành vi streaming trong đúng phiên bản.

## 10. Chọn lỗi nào để retry, lỗi nào không?

Hãy ưu tiên **lỗi tạm thời có khả năng phục hồi**. Những status phổ biến cần xem xét:

| Loại lỗi | Retry? | Lý do |
|---|---|---|
| `502 Bad Gateway` | Có thể | Reverse proxy/downstream tạm lỗi |
| `503 Service Unavailable` | Có thể | Backend quá tải/đang bảo trì; cần backoff |
| `504 Gateway Timeout` | Có thể, có điều kiện | Timeout có thể hết sau một attempt khác nhưng có nguy cơ lặp tác vụ |
| `500 Internal Server Error` | Có điều kiện | Nếu là lỗi lặp logic, retry chỉ tăng tải |
| `429 Too Many Requests` | Không mặc định tại Gateway | Có thể có `Retry-After`, quota cần tôn trọng; retry tức thì dễ làm nặng hơn |
| `401 Unauthorized` | Không | Xác thực sai/thiếu token |
| `403 Forbidden` | Không | Phân quyền từ chối |
| `404 Not Found` | Thường không | Resource hoặc route không tồn tại |
| `400/422` | Không | Request không hợp lệ, cần client sửa |
| Connection reset/timeout | Có thể | Cần kiểm tra exception class, phase xảy ra lỗi và idempotency |

### `Retry-After` trên 429 hoặc 503

Theo semantics HTTP, server có thể trả:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 5
~~~

Giá trị `5` biểu thị gợi ý đợi **5 giây** theo semantics của header. Nhưng **đừng tự giả định Retry GatewayFilter tự đọc `Retry-After` và dùng nó thay backoff** ở mọi phiên bản.

Nếu đã nhận yêu cầu chờ 5 giây trong khi **overall deadline chỉ còn 2 giây**, cách hợp lý thường là **không retry trong request đồng bộ đó**, mà trả kết quả phù hợp để client điều phối lượt gọi tiếp theo. Việc chuyển tiếp `Retry-After` ra client cũng phải tuân theo hợp đồng API.

### Kiểm tra `exceptions` theo runtime

Một số exception thường phát sinh từ I/O, timeout, connection pool hoặc DNS. Chúng **không nhất thiết thuộc cùng một class** trong các phiên bản Reactor Netty/HTTP client. Ví dụ Java `TimeoutException` và một exception chuyên biệt của Netty có thể khác hierarchy.

Nếu tùy biến danh sách `exceptions`, đừng sao chép tên class từ một log cũ; hãy kiểm chứng **exception thực tế và cấu hình Retry factory của phiên bản đang chạy**.

## 11. Retry, CircuitBreaker, RateLimiter và LoadBalancer có cộng dồn tác động

Với một Gateway microservices, thứ tự và phạm vi của các filter tạo ra hành vi khác biệt.

~~~mermaid
flowchart LR
    C["1 client request"] --> AUTH["Spring Security"]
    AUTH --> LIMIT["RequestRateLimiter"]
    LIMIT --> RETRY["Retry: có thể nhiều attempts"]
    RETRY --> CB["CircuitBreaker: tùy thứ tự"]
    CB --> LB["LoadBalancer lb://catalog"]
    LB --> I1["Instance A"]
    LB --> I2["Instance B"]
    CB -.-> FB["Fallback khi policy kích hoạt"]
~~~

Sơ đồ **chỉ minh họa các nhóm chức năng**, không ngầm khẳng định thứ tự cố định giữa `Retry`, `CircuitBreaker`, `LoadBalancer` trong mọi bản Gateway. `GlobalFilter` và `GatewayFilter` được sắp xếp theo `Ordered`; thứ tự thật phải được xác minh theo cấu hình/runtime.

### Khi Retry bọc CircuitBreaker

Nếu Retry nằm ngoài CircuitBreaker theo chuỗi reactive, **mỗi attempt** có thể đi qua circuit breaker và ảnh hưởng counters. Khi circuit đã OPEN, attempt tiếp theo có thể bị từ chối ngay. Tuy nhiên, chi tiết lỗi ghi nhận và trạng thái breaker phụ thuộc thứ tự/filter implementation.

### Khi CircuitBreaker bọc Retry

CircuitBreaker có thể nhìn thấy **toàn bộ chuỗi retry** như một call logic, thay vì từng attempt. Một request có thể tiêu nhiều outbound calls trước khi breaker quyết định fallback. Phải test “recorded calls”, "failure rate" và "open state" thay vì suy chỉ từ tên filter.

### Khi RateLimiter đứng trước Retry

Một request client được cho qua limiter **có thể sinh nhiều downstream attempts**. Nếu quota đặt theo client request, request ấy có thể chỉ tiêu một đơn vị quota nhưng tạo ba lượt vào backend. Có thể cần **retry budget** riêng để tránh khuếch đại tải. Đừng trông cậy rate limiting một mình sẽ bảo vệ backend khỏi retry storm.

### Khi có service discovery

URI `lb://catalog-service` có thể chọn instance khác nhau ở những attempt, nhưng **không cam kết mỗi retry sẽ đi sang một instance mới**. Điều đó phụ thuộc LoadBalancer, kết quả discovery, connection reuse và filter order. Nếu chỉ một instance lỗi, retry cùng instance có thể vô ích; cần observability theo instance và health policy.

## 12. Giới hạn tổng thời gian với xác thực, TLS và proxy

Tổng latency không chỉ gồm I/O backend.

| Thành phần | Có thể tiêu hao ngân sách như thế nào? |
|---|---|
| Spring Security / JWT | Xác minh claims, kiểm tra khóa/JWKS theo cache và cấu hình |
| Route predicate / filter chain | Tính toán điều kiện, mutate path/header, đọc metadata |
| Redis RateLimiter | Gọi Redis, timeout và queue |
| DNS / service discovery | Chọn endpoint/instance và giải quyết địa chỉ |
| TCP/TLS | Connect, TLS handshake, certificate validation |
| Backend | Xử lý business, DB/cache, chờ dependency |
| Retry backoff | Thời gian **chủ động chờ** giữa attempts |
| CircuitBreaker | Timeout, fallback, trạng thái breaker |
| Reverse proxy/CDN/client | Buffering, connection, timeout và thời gian gửi response |

Do đó, khi API có SLO 3 giây, không nên dành trọn 3 giây cho `response-timeout` của **mỗi attempt** rồi thêm nhiều retries. Tổng deadline phải tính **end-to-end**, gồm cả budget cho proxy và việc trả dữ liệu về client.

### Truyền deadline qua header

Trong nội bộ, bạn có thể định nghĩa một header như `X-Request-Deadline` để downstream biết thời điểm cuối cùng xử lý có ích. Nhưng:

- Header từ Internet **không được tin mặc định**; ingress/Gateway phải xác minh hoặc tạo lại.
- Thỏa thuận dùng timestamp tuyệt đối hay duration còn lại, đồng hồ và timezone phải rõ ràng.
- Không để một client tự đẩy deadline thành “vô hạn” để làm cạn tài nguyên.
- Một header chỉ chứa deadline **không tự thực hiện hủy tác vụ**; backend phải tôn trọng và ứng dụng vẫn cần timeout.
- Nếu hủy muộn sau khi side effect đã commit, phải có cơ chế idempotency/transaction recovery.

Đây là kiến trúc nâng cao; với API đơn giản, phối hợp budget/timing đủ chặt và timeout ở client/edge/backends có thể phù hợp hơn.

## 13. Bài thực hành: đo retry và khoảng chờ giữa attempts

### Chuẩn bị

Giả sử:

- Gateway Server WebFlux tại `http://localhost:8080`.
- Backend demo WebFlux tại `http://localhost:9090`, endpoint `GET /lab/flaky`.
- Không có retry/circuit breaker thứ hai ở ingress, client hoặc backend test.
- Gateway có route `retry-flaky-lab` với backoff 100/200/400ms và `retries=3`.

Backend demo: trả 503 cho **hai lượt đầu tiên**, rồi 200 ở lượt thứ ba.

~~~java
package example.backend.lab;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class FlakyController {

    private final AtomicInteger attempts = new AtomicInteger();

    @GetMapping("/lab/flaky")
    public Mono<ResponseEntity<Map<String, Object>>> flaky() {
        int current = attempts.incrementAndGet();

        System.out.println("LAB backend attempt #" + current
            + " at " + System.currentTimeMillis());

        if (current <= 2) {
            return Mono.just(ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of("attempt", current, "state", "temporarily-failed")));
        }

        return Mono.just(ResponseEntity.ok(
            Map.of("attempt", current, "state", "ok")));
    }
}
~~~

Đoạn mã dùng **counter toàn cục của một instance** để tiện lab, không phải cách xây backend production. Nếu nhiều client gọi song song hoặc có nhiều backend instances, số thứ tự không còn tương ứng một request. Restart backend để reset thử nghiệm, hoặc quản lý state theo request ID bằng cơ chế test riêng.

Route tương ứng:

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: retry-flaky-lab
          uri: http://localhost:9090
          predicates:
            - Path=/lab/flaky
            - Method=GET
          filters:
            - name: Retry
              args:
                retries: 3
                statuses:
                  - SERVICE_UNAVAILABLE
                methods:
                  - GET
                backoff:
                  firstBackoff: 100ms
                  maxBackoff: 500ms
                  factor: 2
                  basedOnPreviousValue: false
~~~

### Bước 1 — Gọi thẳng backend để hiểu hành vi gốc

~~~bash
curl -i "http://localhost:9090/lab/flaky"
~~~

Backend lần đầu trả 503. Gọi thêm hai lượt sẽ thấy 503 rồi 200, nếu không có client khác làm thay đổi counter. Restart backend trước thử nghiệm qua Gateway để trả state ban đầu.

### Bước 2 — Gọi qua Gateway một lần

~~~bash
curl -i "http://localhost:8080/lab/flaky"
~~~

Dự kiến:

- Client gửi **một** HTTP request.
- Backend log khoảng **ba attempts** (503, 503, 200) nếu response/status matching và retry hoạt động như cấu hình.
- Khoảng cách giữa attempt #1 và #2 có phần backoff khoảng `100ms`; giữa #2 và #3 khoảng `200ms`, cộng thời gian xử lý và overhead.
- Client nhận HTTP 200 từ attempt thứ ba, nếu chưa có response bị commit.

Ghi lại **timestamp backend** và **thời gian tổng ở Gateway**. Không kết luận backoff chính xác chỉ từ một lần đo: timer scheduling, network, CPU và event-loop làm số đo dao động.

### Bước 3 — Đo tổng thời gian client

~~~bash
curl -sS -o /dev/null \
  -w "http_code=%{http_code} total=%{time_total}s\n" \
  "http://localhost:8080/lab/flaky"
~~~

Lệnh trên theo cú pháp cURL trên môi trường POSIX. Nếu dùng Windows, chọn sink/output phù hợp, chẳng hạn `-o NUL`, và dùng `curl.exe` khi PowerShell có alias `curl`.

Trước mỗi lượt đo có đối chứng, reset state backend và loại ảnh hưởng từ cache hoặc request khác. `time_total` là **thời gian nhìn từ client**, gồm cả truyền qua loopback; không phải chỉ tổng `firstBackoff`.

### Bước 4 — Thử số lượt retry không đủ

Đổi `retries: 1`, restart/refresh cấu hình đúng phiên bản và reset backend. Vì backend trả lỗi hai lượt đầu, client có thể nhận 503 sau hai attempts, không đến được lần thứ ba thành công.

### Bước 5 — Thử SLA tổng và timeout từng attempt

Tạo một endpoint backend lab cố tình phản hồi chậm, rồi cấu hình HTTP client response timeout theo phiên bản. Thử lần lượt:

1. **Không retry**: đo thời gian trước khi request thất bại.
2. **Hai retries**: đo số outbound attempts, tổng elapsed và status.
3. **Ba retries**: so sánh với mốc SLA giả định 3 giây.
4. **Có overall deadline ở tầng được thiết kế riêng**: kiểm tra số attempts bị hủy/cắt khi hết ngân sách.

Quan trọng: không giả định một request chậm **luôn được Retry filter nhận diện là exception retryable**. Kết quả phụ thuộc loại timeout/error thực tế, `exceptions` và implementation version. Hãy ghi exception class đã được cho phép trong môi trường test và đối chiếu đúng policy.

### Bước 6 — Thử với nhiều client đồng thời

Trong môi trường lab, dùng công cụ load test có giới hạn concurrency để xác nhận:

- Có hiện tượng nhiều clients cùng retry tại các mốc 100/200/400ms không?
- Redis rate limit có giới hạn **client requests** nhưng downstream attempts tăng nhiều lần không?
- Backend P95/P99 và connection pool có xấu đi sau khi bật retry không?
- Nếu tắt một instance, LoadBalancer có chọn instance khỏe ở lần sau không?
- Khi vượt overall budget, request đã thực sự ngừng tạo outbound attempts mới chưa?

Không stress test một dịch vụ production khi chưa có quyền/giới hạn kiểm thử rõ ràng.

## 14. Troubleshooting: khi backoff hoặc tổng thời gian khác dự tính

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh |
|---|---|---|
| `retries: 3` nhưng thấy 4 backend calls | Đó là 1 lần đầu + 3 retries | Đếm attempts, không nhầm retries với attempts |
| Không thấy retry dù backend trả 503 | Route không match, status/method không trong policy | Xem route ID, filter runtime, request path/method |
| Có retry nhưng không thấy chờ | `backoff` không được bind/đúng cú pháp hoặc thời gian quá nhỏ | Kiểm tra effective config và timestamp backend |
| Backoff vượt `maxBackoff` khi nhìn từ logs | Log đo cả attempt/network/queue, không chỉ thời gian sleep | Đo khoảng giữa **kết thúc lỗi và bắt đầu attempt kế tiếp** |
| Total latency lớn hơn `maxBackoff` | `maxBackoff` chỉ cap từng lần chờ | Tính tổng attempts + waits + overhead |
| Bật `response-timeout: 800ms` nhưng client đợi nhiều giây | Timeout outbound có thể áp theo attempt; retry nhiều lần | Phân biệt per-attempt và end-to-end deadline |
| Client đã timeout nhưng backend vẫn bận | Deadline/cancellation không đi xuyên các tầng hoặc side effect đã bắt đầu | Theo dõi active attempts, aborted client connections |
| POST bị xử lý hai lần | Retry không an toàn với side effect | Tắt retry mặc định cho POST, thiết kế idempotency key/backend dedupe |
| Tăng retry làm tăng 503/429 | Retry storm, backend quá tải, capacity thiếu | Giảm retries, backoff, jitter/budget, kết hợp circuit breaker |
| `429` vẫn được retry liên tục | Đưa 429 vào statuses mà không xử lý quota/Retry-After | Điều chỉnh policy, tôn trọng rate limit |
| Thêm CircuitBreaker làm kết quả khác | Filter order và loại failure được breaker ghi nhận thay đổi | Quan sát attempts vs recorded calls, fallback count |
| Không chuyển sang instance khác | LoadBalancer/connection reuse/discovery policy | Ghi instance ID từng outbound attempt |
| Retry body gây áp lực bộ nhớ | Buffer request body để replay | Theo dõi `DataBuffer`/direct memory; hạn chế upload retry |
| Lỗi lúc response streaming dở | Response đã commit, không thể retry/thay status như trước commit | Thiết kế streaming error contract riêng |
| Dùng route metadata timeout không tác dụng | Sai đơn vị, namespace, metadata key, phiên bản | Xác minh cấu hình runtime và request đo thực |
| Chỉ lỗi trên một vài Gateway nodes | Rollout, route cache, client timeout, config khác nhau | So sánh version, routes, metrics và logs từng node |

### Quy trình kiểm tra từng lớp

1. Xác định **route có match** và `Retry` có được nạp không.
2. Ghi **method**, status hoặc **exception thật** để xác định điều kiện retry.
3. Đếm **attempts** và timestamp của từng attempt.
4. Kiểm tra các giá trị `retries`, `firstBackoff`, `maxBackoff`, `factor`, `basedOnPreviousValue` sau binding.
5. Kiểm tra **timeout per attempt** và tầng nào phát sinh/hủy request.
6. Xác định tổng elapsed tại client/Gateway so với **overall deadline**.
7. Đối chiếu CircuitBreaker, RateLimiter, LoadBalancer và retry ở các tầng client/SDK/backend để tránh **nested retries**.

Đặc biệt, nếu client library đã có 3 retries và Gateway có 3 retries, một request nghiệp vụ có thể tạo nhiều lượt gọi hơn dự kiến do cơ chế **retry lồng nhau**. Hãy xác định rõ tầng sở hữu chính sách và budget tổng.

## 15. Checklist production cho backoff và tổng deadline

- [ ] Tôi biết `retries` là **số lần thử lại**, tổng attempts tối đa bằng `retries+1`.
- [ ] Tôi chỉ retry những status/exception tạm thời **có khả năng phục hồi**.
- [ ] Tôi xác định rõ `methods` và không bật POST/PATCH mù quáng.
- [ ] Tôi hiểu `firstBackoff`, `factor`, `maxBackoff` và `basedOnPreviousValue` trong đúng phiên bản.
- [ ] Tôi biết `maxBackoff` **không giới hạn tổng thời gian** của một request.
- [ ] Tôi đã tính sơ bộ tổng attempts + tổng backoff + overhead so với SLO.
- [ ] Tôi cấu hình connect/response timeout với đúng **đơn vị của global và route metadata**.
- [ ] Tôi có **overall deadline** thực tế ở client/Gateway/ingress hoặc một tầng được thiết kế rõ.
- [ ] Tôi không lên lịch attempt mới nếu còn quá ít budget để hoàn tất có ích.
- [ ] Tôi kiểm thử cancellation, response đã commit và các hoạt động backend có side effect.
- [ ] Tôi không giả định built-in Retry factory có property jitter tùy ý nếu chưa kiểm tra.
- [ ] Tôi đã xác định retry budget và tránh retry đồng loạt khi backend quá tải.
- [ ] Tôi tôn trọng `Retry-After`/quota policy khi gặp 429/503 theo hợp đồng.
- [ ] Tôi không retry 401/403 hoặc lỗi input như 400/422.
- [ ] Tôi hiểu RateLimiter tính client requests có thể khác tổng outbound attempts.
- [ ] Tôi đã test thứ tự Retry/CircuitBreaker và cơ chế fallback để tránh vòng lặp.
- [ ] Tôi đã xác minh `lb://` có chuyển instance không và TLS/network có hoạt động ổn định.
- [ ] Tôi hiểu retry body có thể tốn `DataBuffer` memory và không dùng cho upload lớn khi chưa kiểm chứng.
- [ ] Tôi giám sát attempt count, retry success, elapsed, 429/5xx, downstream saturation và cancellation.
- [ ] Tôi kiểm tra nhiều Gateway instances, rollout, nested client retries và ranh giới tin cậy của timeout headers.
- [ ] Tôi có chiến lược giảm retries/rollback khi biểu hiện của retry storm tăng.

## Tài liệu tham khảo chính thức

- [Spring Cloud Gateway Reference](https://docs.spring.io/spring-cloud-gateway/reference/) — tìm mục **Retry GatewayFilter Factory**, **HTTP timeouts** và **Server WebFlux** đúng phiên bản.
- [Spring Cloud Gateway project](https://spring.io/projects/spring-cloud-gateway) — thông tin release train và hướng dẫn chọn tài liệu phù hợp.
- [Spring Cloud CircuitBreaker Reference](https://docs.spring.io/spring-cloud-circuitbreaker/reference/) — tổ chức circuit breaker/fallback và hợp tác với Retry.
- [Reactor Reference Guide](https://projectreactor.io/docs/core/release/reference/) — các toán tử reactive `retryWhen`, `timeout`, cancellation và xử lý lỗi.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110) — HTTP methods, idempotency, status codes và `Retry-After`.
- [Spring Framework WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html) — xử lý HTTP reactive, streaming và response commit.

**Ghi nhớ:** Retry thành công không chỉ là “thử nhiều lần”. **Exponential backoff giúp giãn attempts; `maxBackoff` chỉ giới hạn một lần chờ; overall deadline mới giới hạn cả chuỗi.** Hãy tính `retries+1` attempts, ngân sách per-attempt + waits + overhead, tránh lặp side effect không idempotent và phối hợp RateLimiter/CircuitBreaker/LoadBalancer để một lỗi tạm thời không biến thành quá tải toàn hệ thống.
