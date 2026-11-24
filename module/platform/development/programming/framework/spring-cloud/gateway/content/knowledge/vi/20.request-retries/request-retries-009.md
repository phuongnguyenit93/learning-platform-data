# Tránh khuếch đại tải khi nhiều tầng cùng thử lại

## 1. Khi một request của người dùng biến thành hàng chục request nội bộ

**Spring Cloud Gateway** thường đứng ở ranh giới giữa client và các microservices. Sau khi chọn route bằng predicate, Gateway xử lý filter chain, biến đổi đường dẫn/header, khám phá service bằng `lb://`, áp dụng xác thực, rate limiting, circuit breaker, TLS và quan sát request. Trong chuỗi này, nhiều thành phần có thể cùng nghĩ: **“Upstream lỗi tạm thời, thử lại một lần nữa là được.”**

Retry có thể cải thiện khả năng chịu lỗi với lỗi ngắn hạn như kết nối vừa bị reset hoặc instance vừa thay đổi. Tuy nhiên, nếu **client, Gateway, service A, service B và SDK** đều tự retry, một thao tác duy nhất của người dùng có thể tạo ra hàng chục hoặc hàng trăm lần gọi tới cùng dependency. Khi backend vốn đang chậm, số request bổ sung lại làm backend chậm hơn, khiến nhiều timeout hơn và sinh thêm retry: đây là **khuếch đại tải do retry** (*retry amplification*).

~~~mermaid
flowchart LR
    C["Client: retry"] --> G["Spring Cloud Gateway: Retry filter"]
    G --> O["Orders service: retry client"]
    O --> P["Payment/Inventory SDK: retry"]
    P --> D["Dependency đang suy giảm"]
    D -. "Timeout / 503" .-> P
~~~

Ví dụ người dùng chỉ bấm một lần vào nút “Xem đơn hàng”, nhưng:

- Client thử tối đa **3 attempts** (lần đầu + 2 lần thử lại).
- Gateway thử tối đa **3 attempts** cho mỗi lần client gửi.
- Orders service thử tối đa **3 attempts** đối với một lời gọi dependency.

Trong kịch bản tất cả những lần thử đều đi tới tầng tiếp theo, số lần gọi dependency có thể đạt:

\[
A_{\text{dependency,max}} = 3 \times 3 \times 3 = 27
\]

Tức là **1 thao tác của người dùng có thể sinh 27 lượt gọi** ở tầng sâu nhất. Mỗi lượt còn có thể giữ connection, cấp phát buffer, ghi log, thực hiện truy vấn DB hoặc tiêu thụ quota. Nếu 100 thao tác như vậy xảy ra cùng lúc, số lần thử ở dependency có thể lên tới 2.700, trước khi tính fan-out, retries ở DB client hoặc hoạt động nền.

**Mục tiêu bài học** thuộc chương **Thử lại yêu cầu** là giúp bạn nhận ra và kiểm soát tải phát sinh ở mọi tầng, không chỉ cấu hình một `Retry` filter cho chạy được.

Sau khi học, bạn có thể:

1. Phân biệt một **user operation**, một **HTTP request**, một **attempt** và một **retry**.
2. Tính cận trên của tải khi các tầng retry lồng nhau và khi có fan-out.
3. Chọn **một tầng chịu trách nhiệm retry chính**, hoặc chia chính sách/budget rõ ràng nếu nhiều tầng thực sự cần.
4. Thiết lập **retry budget, deadline, backoff, jitter** và phân loại lỗi được retry.
5. Cấu hình **Retry GatewayFilter Factory** của Spring Cloud Gateway Server WebFlux mà không mặc định retry mọi method hay mọi status.
6. Giải thích nguy cơ replay body, double charge/double order, request cancellation và lỗi sau response commit.
7. Kết hợp retry với rate limiting, circuit breaker, load balancing, connection pool và service discovery.
8. Đo **client requests so với upstream attempts** và kiểm thử được rằng Gateway không khuếch đại tải ngoài giới hạn.

> **Phạm vi phiên bản:** Ví dụ hướng tới **Spring Cloud Gateway Server WebFlux** trên Reactor Netty, không phải Gateway Server Web MVC. Tên starter, prefix YAML, semantics cấu hình và filter ordering có thể thay đổi giữa các dòng Spring Boot/Spring Cloud; luôn kiểm tra bản thực tế. Các con số cấu hình là **minh họa để học**, không phải giá trị mặc định hoặc khuyến nghị dùng nguyên vào production.

## 2. Mô hình số lần thử: cần đếm đúng đơn vị

Một lỗi rất phổ biến là dùng từ “retry” để chỉ cả lần gọi đầu tiên. Cần tách:

| Khái niệm | Định nghĩa trong bài | Ví dụ |
| --- | --- | --- |
| **User operation** | Một hành động logic mà client muốn hoàn thành | Xem đơn `O-42` hoặc đặt đơn mới |
| **HTTP request** | Một request client thực sự gửi tới Gateway | `GET /api/orders/O-42` |
| **Attempt** | Một lần một tầng cố thực hiện lời gọi downstream | Một lần Gateway proxy tới Orders |
| **Retry** | Lần attempt **thêm** sau attempt đầu tiên | Thử lần 2 hoặc lần 3 |
| **Fan-out** | Một operation gọi nhiều downstream nhánh | Orders gọi cả Inventory và Pricing |
| **Deadline** | Thời điểm cuối cùng một operation còn được phép chờ | Còn 800 ms trong ngân sách 2 giây |
| **Retry budget** | Giới hạn số lần thử lại/tài nguyên retry được phép tiêu thụ | Tối đa 5% requests tăng thêm theo cửa sổ, nếu chính sách chọn như vậy |

Ví dụ một cấu hình `retries: 2` trong **Retry GatewayFilter** thường nghĩa là **tối đa 2 lần thử lại ngoài lần đầu**, tức **3 attempts** khi mọi lần đều hội đủ điều kiện. Không nhầm nó với “chỉ có 2 attempts”.

### Công thức cận trên cho các tầng lồng nhau

Giả sử có \(n\) tầng. Tầng \(i\) cho phép tối đa \(r_i\) lần retry và **mỗi attempt ở tầng đó đi qua toàn bộ tầng tiếp theo**. Cận trên của số attempts tại dependency cuối:

\[
A_{\max} = \prod_{i=1}^{n}(1+r_i)
\]

Nếu client có 2 retries, Gateway có 1 retry, SDK Orders có 3 retries:

\[
A_{\max}=(1+2)(1+1)(1+3)=3\times2\times4=24
\]

**24 là cận trên, không phải bảo đảm hệ thống thật sẽ tạo đúng 24 requests.** Một số attempts có thể lỗi trước khi gửi downstream, circuit breaker có thể OPEN, deadline có thể hết, client có thể hủy request hoặc retry policy không coi mã lỗi là retryable.

### Bảng so sánh độ khuếch đại

| Client | Gateway | Service/SDK | Attempts tối đa ở dependency sâu nhất | Mức khuếch đại lý thuyết |
| --- | --- | --- | ---: | ---: |
| 1 | 1 | 1 | 1 | 1× |
| 2 | 1 | 1 | 2 | 2× |
| 2 | 2 | 1 | 4 | 4× |
| 3 | 3 | 1 | 9 | 9× |
| 3 | 3 | 3 | 27 | 27× |
| 3 | 4 | 3 | 36 | 36× |

Các số trong ba cột đầu là **attempts tối đa ở mỗi tầng**, không phải giá trị `retries` trong YAML. Nếu mỗi tầng đặt `retries: 2` thì mỗi tầng cho phép 3 attempts, tạo hàng cuối tương ứng **27 lần** với ba tầng.

### Fan-out và gọi chuỗi không giống nhau

Nếu Orders cần gọi song song Inventory và Pricing, tổng calls còn phụ thuộc **số nhánh**. Với mỗi nhánh có cận trên \(a_j\), số lần gọi ở các nhánh gần nhất có thể tăng theo tổng:

\[
A_{\text{all branches,max}}=\sum_{j=1}^{m} a_j
\]

Còn một dependency nằm **sâu trên một nhánh lồng nhau** có thể bị khuếch đại theo tích các attempts của các tầng trước nó. Nếu cùng một thao tác vừa fan-out vừa retry theo nhiều tầng, phải vẽ **call graph thực tế** trước khi tính; không áp một công thức nhân cho mọi service mà không xét các nhánh điều kiện.

## 3. Vòng phản hồi dương: càng chậm càng bị gọi nhiều

Khuếch đại tải nguy hiểm nhất khi backend vốn đã gần giới hạn CPU, thread pool, connection pool hoặc database:

~~~mermaid
flowchart TD
    A["Backend chậm / quá tải"] --> B["Latency tăng"]
    B --> C["Nhiều timeout hoặc 502/503"]
    C --> D["Client / Gateway / SDK cùng retry"]
    D --> E["Upstream attempts tăng"]
    E --> F["CPU, DB, queue, connection bão hòa hơn"]
    F --> A
~~~

Đây là **positive feedback loop**: cơ chế dự phòng làm tình trạng lỗi nặng thêm. Một số biểu hiện:

- QPS thực đến dependency tăng nhanh hơn QPS từ người dùng.
- Kết nối HTTP outbound và `pending acquire` trong Reactor Netty tăng.
- Thời gian chờ TCP connect, TLS, response và queueing tăng.
- Phần lớn request hết deadline trước khi backend kịp xử lý.
- Log lỗi tràn vì mỗi attempt đều tạo nhiều dòng log/trace.
- Autoscaling phản ứng chậm hoặc scale không đủ vì nút nghẽn nằm ở DB, không phải CPU service.
- Load balancer liên tục chọn lại instance đã quá tải, hoặc retry làm tăng áp lực lên mọi instance.
- Circuit breaker mở, đóng rồi lại mở nếu probe/retry không được điều phối.

Giả sử backend xử lý bền vững khoảng **1.000 calls/s**, còn người dùng gửi 800 operations/s. Nếu policy tạo trung bình **1,5 attempts tại backend trên mỗi operation**, backend thấy:

\[
\lambda_{\text{upstream}}=800\times1.5=1.200\ \text{calls/s}
\]

Tải này **cao hơn năng lực bền vững 1.000 calls/s** trong ví dụ, dù traffic ban đầu chỉ 800 operations/s. Hàng đợi tăng, latency tăng và retry có thể tiếp tục tăng tỷ lệ attempts. **Chênh lệch 200 calls/s không thể tự hết** nếu không có shedding, phục hồi năng lực hoặc giảm lưu lượng.

### Kiểm tra hệ số khuếch đại khi vận hành

Với một route và khoảng thời gian được xác định nhất quán:

\[
\text{Amplification ratio}
= \frac{\text{Outbound upstream attempts}}{\text{Accepted inbound requests}}
\]

Nếu 1.000 inbound requests tạo 1.400 upstream attempts, tỷ lệ là **1,4×**. Nhưng cần cẩn trọng:

- Một API có **fan-out hợp lệ** tới hai backend thì tỷ lệ tổng calls/inbound có thể lớn hơn 1 ngay cả khi không có retry.
- Các request bị authentication/rate limiting chặn không nên trộn vào mẫu của một route khác khi đánh giá retry.
- Một request có thể không có upstream call vì circuit breaker OPEN; tỷ lệ thấp **không chứng minh hệ thống khỏe**.
- Khi nhiều Gateway replicas, phải tổng hợp đúng khoảng thời gian và tags; retry của client xảy ra **ngoài Gateway** nên inbound request count cũng có thể tăng.

Vì vậy, một chỉ số hữu ích hơn là **attempts theo logical operation, route và dependency**, đồng thời có metrics riêng cho retry attempts, rejected calls và fan-out.

## 4. Điểm phát sinh retry trong một chuỗi microservices

Retry có thể được bật ở nhiều nơi mà không nằm trong file cấu hình Gateway:

| Tầng | Cơ chế thử lại thường thấy | Điều có thể bị bỏ sót |
| --- | --- | --- |
| Browser/mobile SDK | Automatic network retry, ứng dụng nhấn “thử lại” | Người dùng bấm lần nữa khi request cũ vẫn chạy |
| CDN / Edge proxy | Retry upstream khi một instance không phản hồi | Cùng request có thể vào Gateway nhiều lần |
| Ingress / Load balancer | Retry khi upstream reset, 502/503 | Tạo attempts mới ở phía trước Gateway |
| Spring Cloud Gateway | `Retry GatewayFilter`, custom filters | Nhân số lời gọi tới backend |
| Orders / Account service | `WebClient.retryWhen(...)`, SDK client | Thử lại lời gọi Inventory/Payments ở tầng sâu |
| Service mesh / sidecar | Envoy/Istio HTTP retry policy | Tạo retry ngoài ứng dụng |
| DB/queue client | Reconnect hoặc retry của driver | Phát sinh tác vụ nội bộ nhiều lần, thậm chí side effect |

**Mọi tầng phải được kiểm kê**. Một câu “Gateway chỉ retry hai lần” không bảo đảm tải chỉ tăng ba lần nếu ingress và SDK downstream cũng đang retry.

### Sơ đồ phân tầng attempts

~~~mermaid
flowchart TB
    U["1 logical user operation"] --> C["Client: 2 HTTP attempts"]
    C --> G1["Gateway invocation #1"]
    C --> G2["Gateway invocation #2"]
    G1 --> A1["Gateway upstream attempt #1"]
    G1 --> A2["Gateway upstream attempt #2"]
    G2 --> A3["Gateway upstream attempt #1"]
    G2 --> A4["Gateway upstream attempt #2"]
    A1 --> S["Orders SDK: 3 attempts per received call"]
    A2 --> S
    A3 --> S
    A4 --> S
    S --> D["Tối đa 12 calls tới dependency cuối"]
~~~

Trong sơ đồ trên, các cạnh vào node “Orders SDK” là **quan hệ tổng hợp về số lượng**, không phải bốn request có thể dùng chung một publisher hoặc cùng một transaction.

Nếu retry xảy ra **sau khi backend đã ghi dữ liệu** mà response chưa về, Gateway hoặc client không thể suy ra “backend chưa xử lý”. Đây là nguyên nhân dẫn tới double booking, double charge hoặc ghi dữ liệu lặp, ngoài vấn đề tải.

## 5. Lỗi nào đáng thử lại và lỗi nào không?

Một chính sách retry an toàn cần phân biệt **tính chất tạm thời**, **phương thức HTTP**, **deadline còn lại**, **thao tác đã có side effect hay chưa** và **khả năng backend chịu thêm tải**.

| Tình huống | Retry từ Gateway? | Ghi chú |
| --- | --- | --- |
| GET bị connection reset trước khi có response | Có thể, số lần ít và có budget | Không chắc server đã xử lý hay chưa; GET phải thực sự an toàn |
| HTTP 502/503 của upstream | Có thể có điều kiện | Không retry ồ ạt lúc backend quá tải |
| HTTP 504 / response timeout | Cẩn trọng | Server có thể vẫn đang xử lý; deadline client có thể sắp hết |
| HTTP 429 Too Many Requests | Thường **không** retry ngay | Tôn trọng `Retry-After`, quota và chính sách backpressure |
| HTTP 400 Bad Request | Không | Caller cần sửa request |
| HTTP 401 Unauthorized | Không | Thiếu hoặc sai credential; retry nguyên token không sửa lỗi |
| HTTP 403 Forbidden | Không | Quyền truy cập không hợp lệ |
| HTTP 404 Not Found | Thường không | Có thể là kết quả nghiệp vụ bình thường |
| HTTP 409 Conflict | Chỉ theo contract đặc biệt | Retry mù có thể làm xung đột nặng hơn |
| HTTP 422 Unprocessable Entity | Không | Request vi phạm quy tắc dữ liệu |
| POST thanh toán bị timeout | **Không tự động** | Có thể đã được charge; cần idempotency + trạng thái nghiệp vụ |
| SSE/WebSocket đã stream một phần | Không retry như HTTP request ngắn | Cần cơ chế reconnect/resume riêng |

**Không có một bảng status nào thay thế được contract nghiệp vụ.** Ví dụ POST tạo đơn có thể được thiết kế idempotent với `Idempotency-Key`, nhưng chỉ an toàn nếu backend thực sự lưu kết quả theo khóa và trả lại cùng kết quả khi request lặp, chứ không phải chỉ thêm header vào request.

### HTTP 503 và Retry-After

Backend có thể phản hồi:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 10
Cache-Control: no-store
Content-Type: application/json

{"code":"UPSTREAM_BUSY","message":"Thử lại sau"}
~~~

`Retry-After` có thể là **số giây** hoặc một **HTTP-date**, hướng dẫn thời điểm thử lại nếu client lựa chọn. Với một retry policy có thời gian chờ tối đa ngắn hơn 10 giây, không nên bỏ qua header rồi gọi lại ngay; có thể trả lỗi cho client để nó thử trong một lượt operation mới nếu policy cho phép. **Không mặc định Retry GatewayFilter tự phân tích và tôn trọng Retry-After trong mọi phiên bản.**

## 6. Chọn tầng chịu trách nhiệm retry: đừng bật ở mọi nơi

Một nguyên tắc thiết kế có ích là **một tầng sở hữu quyết định retry chính cho mỗi dependency/operation**. Những tầng khác có thể áp deadline, circuit breaker hoặc giới hạn lưu lượng mà không tự phát sinh thêm attempts.

Ví dụ hệ thống dùng browser → CDN → Gateway → Orders → Inventory:

~~~mermaid
flowchart LR
    B["Browser: deadline, UX"] --> E["CDN: không retry API ghi"]
    E --> G["Gateway: retry GET có budget"]
    G --> O["Orders: không retry lại cùng call đã được Gateway thử"]
    O --> I["Inventory: health/readiness + timeout"]
~~~

Tuy nhiên, **không phải lúc nào chỉ một tầng retry trong toàn hệ thống**. Nếu Orders gọi Inventory theo một operation nội bộ khác với Gateway → Orders, Orders có thể có retry riêng cho Inventory **nếu** có lý do, budget và deadline chung. Điều cần tránh là nhiều tầng **độc lập retry cùng một sự cố** mà không có quyền sở hữu và giới hạn tổng.

### Ma trận chủ sở hữu mẫu

| Dependency/công việc | Tầng retry chính | Tầng còn lại nên làm | Lý do |
| --- | --- | --- | --- |
| Public Catalog GET | Gateway (1 retry có điều kiện) | Client có UX retry thủ công, SDK không tự lặp vô hạn | Lỗi kết nối ngắn có thể hồi phục |
| Orders GET theo user | Gateway **hoặc** client theo contract | Tầng kia không tự retry mặc định | Giữ deadline rõ và tránh nhân attempts |
| Orders gọi Inventory GET | Orders service (nếu cần) | Gateway không nhân retry cho toàn request | Orders hiểu thời điểm/chi phí gọi Inventory |
| Create order POST | Backend idempotency, không blind retry | Gateway fail nhanh khi kết quả không rõ | Tránh đơn hàng trùng |
| Payment authorization | Client/backend payment workflow chuyên biệt | Gateway không tự động retry | Bảo vệ giao dịch tiền và quyền quyết định |
| SSE/WebSocket | Client protocol reconnect/resume | Gateway không replay toàn stream | Stream đã gửi một phần không thể “chạy lại” an toàn |

Một **retry policy inventory** nên ghi rõ: tên API, người sở hữu, trạng thái được retry, loại exception, số attempts, deadline, jitter, ngân sách retry, idempotency, phép đo và thử nghiệm xác nhận.

### Vì sao “client retry sau khi Gateway đã retry” dễ bị bỏ sót?

Giả sử Gateway dành 2 retries và cuối cùng trả 503. SDK của client thấy 503 nên cũng thử lại **toàn bộ request**, khiến Gateway lại thực hiện tối đa 3 attempts nữa. Cùng một sự cố được khởi động lại từ đầu với ngân sách mới; nếu không có **operation-level budget**, mỗi tầng có thể tuân thủ giới hạn riêng nhưng tổng vẫn rất lớn.

Để giảm rủi ro, chọn một trong các phương án có chủ đích:

1. Gateway chịu retry GET ngắn; client chỉ hiển thị lỗi, có nút thử lại do người dùng quyết định và áp rate limit/UX phù hợp.
2. Client sở hữu retry và deadline; Gateway không thêm retry cho route đó, chỉ proxy với timeout, rate limit và circuit breaker.
3. Nhiều tầng retry vì yêu cầu đặc biệt, nhưng giới hạn **tổng attempts** bằng retry budget/deadline được thực thi ở ranh giới đáng tin.

**Không tin header do Internet client tự khai** như `X-Retry-Count: 0` hay `X-Max-Attempts: 100` để quyết định Gateway được phép tạo bao nhiêu calls. Chỉ sử dụng thông tin từ nguồn tin cậy; nếu truyền budget giữa service, xác định cơ chế xác thực, chuẩn hóa và giới hạn giá trị.

## 7. Retry budget: giữ số lần thử lại trong một quỹ hữu hạn

`retries: 2` giới hạn attempts **của một HTTP request tại một tầng**. Nhưng khi có 100.000 requests đang lỗi, ngay cả 2 retries/request vẫn có thể quá tải. Cần một ngân sách chung ở cấp route/service hoặc caller.

### Hai kiểu budget khác nhau

**Per-operation budget** — giới hạn với mỗi thao tác logic:

~~~text
GET order #42:
  Max total attempts across chosen owner = 2
  Deadline = 1.5 s
  Retry only on eligible failure
  No retry after response commit
~~~

**Fleet-level retry budget** — giới hạn tổng retries trong một khoảng thời gian, ví dụ cho phép retries bổ sung tối đa **5% số requests thành công/hợp lệ** hoặc theo một quota/tokens có thiết kế rõ:

\[
R_{\text{allowed}}(T) \le B(T)
\]

Trong đó \(R_{\text{allowed}}(T)\) là số retry attempts được phép trong cửa sổ \(T\), còn \(B(T)\) là budget được tính từ thông lượng thực hoặc quota cố định. Cách định nghĩa **mẫu số** phải rõ: lấy successful original calls, accepted requests hay một token bucket cấu hình? Mỗi lựa chọn có đặc tính khác nhau khi xảy ra outage.

Ví dụ giả định một chính sách quota:

~~~text
Inbound accepted operations trong 60 s = 10.000
Giới hạn retry bổ sung                 = 5%
Budget toàn nhóm                       = 500 retry attempts
Nếu đã tiêu hết budget                 = không retry thêm; trả lỗi có kiểm soát
~~~

**Đây là một cách xây policy minh họa, không phải tính năng tự động xuất hiện** khi chỉ thêm `Retry GatewayFilter`. Để bảo đảm 500 attempts trên toàn cụm, cần cơ chế quota/budget thực sự được chia sẻ hoặc phân bổ có giới hạn giữa các Gateway replica.

### Budget không được làm hại request đầu tiên

Khi hệ thống quá tải, **ưu tiên phục vụ requests đầu tiên** hơn là dành toàn bộ năng lực cho retries. Một chiến lược hợp lý:

- Có quota riêng nhỏ cho retries.
- Ngừng retry khi error rate, queue depth hoặc circuit-open rate vượt ngưỡng.
- Không retry khi không còn đủ deadline để kết quả có ích cho client.
- Dùng backoff + jitter để giảm đồng bộ yêu cầu.
- Phân loại traffic ưu tiên và tenant nếu cần, tránh một tenant dùng hết budget của tất cả tenant khác.

Một token bucket cho retry attempts có thể được hiện thực ở tầng ứng dụng hoặc edge policy, nhưng **không nên nhầm với RequestRateLimiter mặc định**: rate limiter thường kiểm soát inbound requests ở Gateway, không tự hiểu attempts nội bộ phát sinh sau filter Retry. Phải xác minh thứ tự filter và cách quota được tính.

### Khi nhiều Gateway replica cùng retry

Nếu có 5 Gateway replicas và mỗi replica có ngân sách local 500 retries/60 s, toàn cụm có thể cho phép tới 2.500 retries trong cùng thời gian, nếu không có phối hợp. Để đặt **fleet budget 500**, có thể:

1. Phân bổ quota cục bộ cố định, ví dụ mỗi replica tối đa 100; cần điều chỉnh khi autoscale.
2. Dùng nguồn phân bổ quota phân tán đáng tin (có độ trễ, HA và fail behavior rõ).
3. Dùng adaptive control dựa trên tải thực của upstream và hệ thống quan sát tập trung; kiểm chứng tính ổn định.

Không có giải pháp nào miễn phí: quota phân tán có thể là dependency mới và điểm lỗi mới. Hãy xác định hành vi khi không đọc được budget: với retry optional, lựa chọn **fail closed đối với việc retry thêm** thường an toàn hơn là phát sinh attempts không giới hạn.

## 8. Deadline: không retry khi kết quả đã quá muộn

Số lần retry thấp vẫn có thể vô ích nếu mỗi attempt dùng hết timeout rồi mới thử lại. Hãy phân biệt **per-attempt timeout** và **end-to-end deadline** của một user operation.

Ví dụ client muốn nhận kết quả trong **2 giây**:

~~~text
Operation deadline: T0 + 2.000 ms

T0 + 000 ms : attempt #1 bắt đầu
T0 + 600 ms : attempt #1 timeout
T0 + 700 ms : sau backoff, attempt #2 bắt đầu
T0 + 1.300ms: attempt #2 timeout
T0 + 1.450ms: còn 550 ms; có nên bắt đầu attempt #3?
T0 + 2.000ms: client deadline
~~~

Nếu backend bình thường cần p95 khoảng 700 ms, attempt #3 bắt đầu khi chỉ còn 550 ms có xác suất rất thấp hoàn tất. Nó có thể chỉ tăng tải mà client không nhận được kết quả.

### Một nguyên tắc kiểm tra trước mỗi retry

Gọi \(D\) là deadline operation, \(t\) là thời điểm hiện tại, \(b\) là backoff phải chờ và \(a\) là ngân sách cần dành cho attempt kế tiếp:

\[
\text{Chỉ retry nếu } D-t > b+a
\]

Trong thực tế \(a\) có thể là per-attempt timeout tối thiểu hoặc estimate thời gian cần thiết có dự phòng. Nếu không đủ, **trả lỗi/hủy phù hợp** thay vì cố gọi để rồi kết quả bị bỏ.

### Timeout tại nhiều hop phải phối hợp

| Tầng | Ví dụ policy | Rủi ro nếu không phối hợp |
| --- | --- | --- |
| Browser/mobile | Tổng deadline 2 s | Gateway tiếp tục xử lý sau khi client đã bỏ |
| Ingress | Timeout 2.5 s | Có thể cắt giữa các attempts của Gateway |
| Gateway | Response timeout 700 ms mỗi attempt | Hai retries + backoff có thể vượt client deadline |
| Orders | Timeout 500 ms tới Inventory | Retry ở Orders có thể vượt thời gian Gateway còn chờ |
| DB/SDK | Timeout riêng | Có thể giữ tài nguyên sau khi request cấp trên kết thúc |

**Không có một công thức “cứ tầng dưới ngắn hơn tầng trên 100 ms” áp dụng cho mọi hệ thống.** Network jitter, processing time, pool acquire, TLS handshake và response streaming khiến deadline cần được đo thực nghiệm. Quan trọng hơn là **mỗi tầng có nhận thức về tổng thời gian còn lại** và có cơ chế hủy công việc khi kết quả không còn hữu ích.

### Timeout của Retry không đồng nghĩa timeout toàn operation

Trong Spring Cloud Gateway Server WebFlux, `httpclient.connect-timeout` giới hạn TCP connect cho connection mới; `httpclient.response-timeout` điều khiển chờ response theo semantics của Reactor Netty/Gateway version. Với `Retry` filter, nhiều attempts có thể khiến tổng thời gian request **vượt một lần response timeout** vì còn backoff, pool acquire và các pha khác. Nếu cần tổng deadline, phải thiết kế và kiểm chứng riêng.

## 9. Exponential backoff và jitter: tránh cả cụm cùng dồn lại

Nếu 1.000 clients cùng nhận 503 và tất cả retry **ngay tức khắc**, backend sẽ thấy đợt tải thứ hai đúng lúc đang suy giảm. Nếu tất cả cùng backoff **đúng 1 giây**, có thể tạo một “retry wave” mới sau mỗi giây.

**Exponential backoff** tăng khoảng chờ sau mỗi lần lỗi, thường có mức trần:

\[
b_k = \min(b_{\max}, b_0 \times q^{k-1})
\]

Trong đó:

- \(b_0\): khoảng chờ cơ sở, ví dụ 100 ms.
- \(q\): hệ số tăng, ví dụ 2.
- \(b_{\max}\): khoảng chờ tối đa, ví dụ 800 ms.
- \(k\): số thứ tự lần **retry**; lần gọi đầu tiên không cần backoff.

Với \(b_0=100\text{ ms}\), \(q=2\), \(b_{\max}=800\text{ ms}\):

| Retry thứ | Backoff trước attempt tiếp theo |
| ---: | ---: |
| 1 | 100 ms |
| 2 | 200 ms |
| 3 | 400 ms |
| 4 | 800 ms |
| 5 | 800 ms, đã đạt trần |

**Jitter** ngẫu nhiên hóa thời điểm retry, giúp các client không đồng thời quay lại:

~~~text
Không jitter:   100 ms, 200 ms, 400 ms, 800 ms...
Có jitter:      74 ms, 167 ms, 309 ms, 612 ms...  (một mẫu minh họa)
~~~

Một chiến lược phổ biến gọi là **full jitter** chọn khoảng chờ trong khoảng từ 0 đến mức backoff tối đa đang áp dụng:

\[
b_k^{\text{jitter}} \sim U(0,\min(b_{\max},b_0q^{k-1}))
\]

Trong hệ thống thực, chọn jitter strategy theo hành vi mong muốn; nếu cho phép khoảng 0 ms, vẫn cần budget và concurrency limits để ngăn retry tức thời khi có nhiều failures. Các giải thuật equal jitter/decorrelated jitter cũng có thể phù hợp, nhưng **đừng đặt tên “exponential backoff” rồi mặc nhiên cho rằng đã có jitter**.

### Đừng làm phức tạp thời gian chờ hơn Retry-After

Khi upstream trả `429` hoặc `503` với `Retry-After`, một client hỗ trợ có thể chờ theo tín hiệu đó, đồng thời áp deadline và budget của mình. Không được giả định rằng Gateway Retry filter sẽ tự tuân theo header này; nếu policy yêu cầu, phải triển khai/kiểm chứng ở tầng được chọn làm chủ retry.

Nếu `Retry-After` dài hơn deadline operation, **không nên giữ một HTTP request treo để đợi**; có thể trả response phù hợp để client quyết định thử trong một thao tác khác. Không biến `Retry-After` thành lệnh buộc client retry bất chấp giới hạn.

## 10. Cấu hình Retry GatewayFilter Factory với phạm vi hẹp

Ví dụ Gateway Server WebFlux dành cho **GET/HEAD của Catalog**, không dành cho API thanh toán hay thao tác ghi:

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-read
              uri: lb://catalog-service
              predicates:
                - Path=/api/catalog/**
                - Method=GET,HEAD
              filters:
                - StripPrefix=1
                - name: Retry
                  args:
                    retries: 1
                    statuses:
                      - BAD_GATEWAY
                      - SERVICE_UNAVAILABLE
                      - GATEWAY_TIMEOUT
                    methods:
                      - GET
                      - HEAD
                    backoff:
                      firstBackoff: 100ms
                      maxBackoff: 800ms
                      factor: 2
                      basedOnPreviousValue: false
~~~

**Đọc cấu hình đúng nghĩa:**

1. `Path=/api/catalog/**` và `Method=GET,HEAD` giới hạn API chịu retry ngay từ tầng route predicate.
2. `uri: lb://catalog-service` yêu cầu Spring Cloud LoadBalancer và nguồn ServiceInstance phù hợp; backend thật phải phục vụ path sau `StripPrefix=1`.
3. `retries: 1` cho phép **một lần thử lại ngoài lần đầu** nếu điều kiện retry hội đủ — cận trên là **2 attempts** ở Gateway cho một inbound request.
4. `statuses` giới hạn các mã HTTP được Retry GatewayFilter nhận diện là phù hợp để thử lại; **không tự lấy mọi lỗi client 4xx**.
5. `methods` giới hạn phương thức được retry. Trên một số version, khả năng chỉ định `exceptions` và `series` cũng tồn tại; cần kiểm tra defaults nếu muốn tránh retry exception không mong muốn.
6. `backoff` tạo khoảng chờ có giới hạn giữa attempts theo các property được hỗ trợ.
7. Cấu hình này **không tự tạo fleet-wide retry budget, tổng deadline hay jitter**. Đó là những cơ chế/policy cần kiểm soát riêng và kiểm thử.

**Quan trọng về tính tương thích:** Những dòng Spring Cloud Gateway WebFlux cũ thường dùng `spring.cloud.gateway.routes`, còn các dòng mới có thể dùng `spring.cloud.gateway.server.webflux.routes`. Tên starter, kiểu `Duration`, thứ tự filter và các giá trị property trong phần `backoff` có thể khác release. Hãy xác minh config binding và route thực nạp trên phiên bản ứng dụng; YAML ở đây là **mẫu minh họa**, không phải bằng chứng đã triển khai.

### Tại sao không dùng cấu hình “retry tất cả 5xx”?

Một 500 có thể đến từ lỗi code không tạm thời. Retry sẽ chỉ lặp thất bại và tăng tải. Một 503 có thể đi kèm `Retry-After` dài. Một 504 có thể biểu thị backend **đã thực hiện thao tác ghi nhưng response quá hạn**. Chính sách retry nên là kết quả của **phân loại sự cố và hợp đồng API**, không chỉ một nhãn “SERVER_ERROR”.

### Default behavior của filter phải được kiểm tra

Nếu không khai báo `methods`, `statuses`, `series` hoặc `exceptions`, Gateway có thể áp các giá trị mặc định được định nghĩa theo phiên bản. Trong tài liệu và ví dụ production, **khai báo tường minh những gì cần retry** và kiểm thử các trường hợp không muốn retry. Không dựa vào trí nhớ về default của một release cũ khi nâng cấp.

## 11. Idempotency: điều kiện bắt buộc trước khi replay thao tác ghi

**Retry khuếch đại tải** là vấn đề hiệu năng; **retry thao tác ghi không an toàn** còn là vấn đề tính đúng đắn dữ liệu. Một lời gọi HTTP có thể đã được backend xử lý nhưng response bị mất do TCP reset, timeout hoặc client ngắt giữa chừng. Việc Gateway không nhận được response **không chứng minh backend chưa commit giao dịch**.

### Kịch bản tạo đơn hàng trùng

~~~mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant O as Orders service
    participant DB as Database
    C->>G: POST /api/orders
    G->>O: POST /orders (attempt 1)
    O->>DB: INSERT order O-100
    DB-->>O: COMMIT
    Note over O,G: Response bị mất / timeout
    G->>O: POST /orders (retry attempt 2)
    O->>DB: INSERT order O-101
    DB-->>O: COMMIT
    O-->>G: 201 Created (O-101)
    G-->>C: 201 Created (O-101)
~~~

Trong tình huống xấu này, **một thao tác người dùng đã tạo hai đơn**. Nếu các tầng cùng retry, số giao dịch phụ ngoài ý muốn có thể tăng nhanh.

### Safe method và idempotent operation

| Phương thức | Semantics HTTP thông thường | Có thể retry mù? |
| --- | --- | --- |
| GET | Đọc; được thiết kế là safe và idempotent | Chỉ khi backend thật sự không có side effect đáng kể và budget cho phép |
| HEAD | Đọc metadata, không có response body | Có thể với điều kiện tương tự GET |
| PUT | Idempotent theo semantics khi thực hiện cùng ý định | Không mặc định; điều kiện đồng thời và version/ETag có thể quan trọng |
| DELETE | Idempotent theo semantics hiệu ứng cuối, nhưng response có thể khác | Không mặc định; quyền và side effect như event/email cần xét |
| POST | Không được bảo đảm idempotent | **Không**, trừ khi ứng dụng có contract chống lặp được thực thi |
| PATCH | Không được bảo đảm idempotent nói chung | **Không**, trừ khi operation cụ thể bảo đảm |

**Idempotent theo HTTP không có nghĩa miễn phí khi gọi lặp**. Một GET có thể kích hoạt truy vấn DB đắt, cache fill, billing theo request hoặc nghiệp vụ thiết kế sai. Một DELETE có thể phát event mỗi lần gọi nếu backend không kiểm soát. Retry vẫn cần budget, deadline và đánh giá chi phí.

### Idempotency-Key thực sự phải được enforce ở backend

Một mô hình an toàn hơn cho `POST /orders`:

~~~http
POST /api/orders HTTP/1.1
Authorization: Bearer <redacted-token>
Idempotency-Key: 9c8c0e2e-7e3f-4c10-a0fd-55b16f8d21f0
Content-Type: application/json

{"sku":"SKU-42","quantity":1}
~~~

Backend cần:

1. Ràng buộc key với **người dùng/tenant, loại operation và fingerprint nội dung** để tránh một key áp cho yêu cầu khác.
2. Ghi trạng thái operation và kết quả theo cách **atomic**, chống hai requests đồng thời cùng thực hiện side effect.
3. Với cùng key + payload hợp lệ, trả lại **kết quả đã ghi nhận**, không tạo một đơn mới.
4. Với cùng key nhưng payload khác, trả lỗi theo contract thay vì thực hiện thao tác mới.
5. Xác định TTL, trạng thái đang xử lý, lỗi mơ hồ và quy trình recovery.

Việc chỉ gắn header `Idempotency-Key` vào Gateway **không tự làm POST an toàn để retry**. Thậm chí nếu key được Gateway tạo mới cho mỗi retry thì khả năng chống lặp bị mất; key phải giữ ổn định **cho cùng operation logic**, và được kiểm tra ở nơi sở hữu giao dịch.

**Khuyến nghị khi chưa có idempotency contract:** Không tự bật Retry filter cho thanh toán, chuyển tiền, tạo đơn hoặc thao tác ghi có thể gây thiệt hại. Khi lỗi không rõ backend đã xử lý hay chưa, trả kết quả “chưa xác định” theo contract và cung cấp cách kiểm tra trạng thái qua một định danh nghiệp vụ đáng tin.

## 12. Request body, buffer và chi phí replay trong WebFlux

Trong **Spring Cloud Gateway Server WebFlux**, request body có thể là một luồng `Flux<DataBuffer>`. Không thể mặc định phát lại luồng đã đọc nếu publisher/body không hỗ trợ replay. Để retry một request có body, Gateway có thể cần **cache request body** hoặc dùng cơ chế chuyên biệt của Retry filter theo phiên bản.

Ví dụ POST JSON dung lượng 2 MiB được retry 2 lần, mỗi lần:

- Cần giữ/đọc lại body đúng byte để upstream nhận cùng dữ liệu.
- Có thể tạo áp lực heap/off-heap buffer và tăng GC.
- Có thể kéo dài thời gian giữ kết nối và mức concurrency.
- Có thể gây áp lực upload của client khi connection bị ngắt.

Với 500 requests đồng thời, chỉ riêng việc giữ **2 MiB body/request** có thể tương ứng khoảng:

\[
500\times2\text{ MiB}=1{,}000\text{ MiB}\approx0{,}98\text{ GiB}
\]

Con số này là **minh họa cho một bản body cache/request**, chưa tính object overhead, bộ đệm mạng, TLS, response, duplication hoặc streaming. Lượng bộ nhớ thực tùy cách body được cache, data buffer pooling và lifetime của request.

### Những trường hợp không nên replay mù

| Loại body | Rủi ro |
| --- | --- |
| JSON nhỏ, GET/HEAD không body | Thường đơn giản nhất; không cần cache body |
| JSON POST có side effect | Replay có thể tạo thao tác trùng dù kỹ thuật cache thành công |
| Multipart upload | Body lớn; replay tốn bộ nhớ/đĩa và thời gian |
| Streaming upload | Không nhất thiết có khả năng replay; input chưa được lưu đầy đủ |
| gRPC hoặc long-lived stream | Semantics khác HTTP request/response ngắn |
| Body có token hoặc dữ liệu cá nhân | Caching/retry/logging tăng phạm vi tồn tại dữ liệu nhạy cảm |

Với `DataBuffer` do Netty quản lý, tự giữ buffer rồi dùng lại có rủi ro retain/release sai hoặc leak memory nếu không hiểu vòng đời. **Không tự xây custom retry bằng cách gọi `chain.filter(exchange)` nhiều lần mà không hiểu replay của request body và exchange state.**

### Content-Length, header và body phải đồng bộ

Nếu một filter sửa body giữa các attempts nhưng giữ `Content-Length` cũ, có thể gây lỗi protocol. Khi bảo vệ retry, các attempt phải theo một contract rõ về method, URI, headers và bytes được gửi. Với body được mã hóa/nén, cần bảo toàn Content-Encoding và dữ liệu thực. Tránh ghi raw body vào logs chỉ để kiểm tra retry; dùng stub trả checksum/byte count an toàn khi cần.

## 13. Circuit breaker, rate limiting và load balancing phối hợp ra sao?

Ba cơ chế này liên quan nhưng không đồng nghĩa:

~~~mermaid
flowchart TD
    C["Client"] --> A["Authentication / route selection"]
    A --> RL["Rate limiting / admission control"]
    RL --> RB["Retry policy + budget"]
    RB --> CB["Circuit breaker"]
    CB --> LB["Reactive load balancing: choose instance"]
    LB --> HTTP["HTTP client / connection pool"]
    HTTP --> U["Upstream"]
    CB -. "OPEN" .-> F["Fallback / fail fast"]
    RL -. "429" .-> C
    F --> C
~~~

Đây là sơ đồ **trách nhiệm**, không cam kết filter order cụ thể trong mọi cấu hình. Trên thực tế, `Retry`, `CircuitBreaker` và các GlobalFilter được sắp theo order; vị trí bọc publisher ảnh hưởng việc đo attempt, lỗi và hành vi short-circuit.

### Retry trước hay sau circuit breaker?

Giả sử một HTTP request từ client được Retry tối đa 3 attempts:

- **Breaker nằm trong vòng retry:** Nó có thể thấy **mỗi attempt** và tăng failure count nhiều lần cho một user operation. Khi OPEN, retry attempts sau có thể bị từ chối ngay.
- **Breaker bao ngoài vòng retry:** Nó có thể thấy **kết quả tổng của operation đã retry**; nếu 3 attempts đều lỗi, breaker có thể ghi một failure nhưng backend đã nhận 3 calls.

Cả hai có hệ quả, không có thứ tự nào “đúng tuyệt đối” cho mọi workload. Hãy chọn rõ **đơn vị breaker đang đo** (attempt hay operation), đồng thời kiểm thử số lượt gọi upstream và số mẫu Resilience4j. Không suy diễn từ việc hai filter xuất hiện gần nhau trong YAML.

### Load balancer có luôn chọn instance khác khi retry?

**Không có bảo đảm mặc định.** Điều này phụ thuộc lần retry có đi qua bước load balancing lại không, bộ chọn/supplier có thay đổi ứng viên không và có chính sách tránh instance vừa lỗi hay không. Một retry có thể chọn **cùng instance** và tiếp tục lỗi; hoặc chọn instance mới và tăng tải trên replica còn khỏe.

Nếu instance thật sự không còn sẵn sàng, ưu tiên xử lý **readiness, registry TTL/health, service discovery và connection draining**. Đừng dùng retry để bù vô hạn cho việc instance lỗi vẫn nằm trong danh sách.

### Rate limiter có nhìn thấy retry attempts không?

Một `RequestRateLimiter` ở cạnh Gateway thường đếm **inbound user HTTP requests** theo key. Nếu Retry GatewayFilter tạo thêm upstream attempts **sau** bước rate limiter, những attempts này có thể không được tính vào quota inbound. Ngược lại, nếu client tự retry bằng cách gửi HTTP request mới, nó thường đi qua rate limiter mỗi lần.

Vì vậy hãy có **outbound attempt metrics/budget riêng**, không chỉ tin rằng quota 1.000 inbound requests/s tương đương tối đa 1.000 calls/s tới backend.

### Bulkhead và connection pool

Ngay cả khi giới hạn retries/request, một spike có thể tạo hàng nghìn operations đồng thời. **Bulkhead**, giới hạn concurrency, connection pool và pending queue giúp bảo vệ tài nguyên. Circuit breaker không thay thế bulkhead; retry không tự tôn trọng số socket mà upstream chịu được nếu policy không gắn với capacity.

Một kiểu chính sách an toàn hơn:

~~~text
Admit request theo quota
  -> Kiểm tra deadline và retry budget
  -> Chỉ retry lỗi được phép
  -> Backoff có jitter
  -> Không vượt concurrency / pool capacity
  -> Dừng khi circuit OPEN hoặc budget đã hết
~~~

### Fallback không được tạo một chuỗi retry mới vô hạn

Nếu Gateway CircuitBreaker forward đến một handler fallback và handler đó gọi service B (cũng retry nhiều lần), các attempts đã được “đẩy” sang dependency khác. **Fallback cũng cần budget, timeout, auth và chính sách giảm tải riêng.** Không trả 200 với dữ liệu sai chỉ để che hệ thống đang lỗi.

## 14. Sau khi response đã commit thì không thể “retry từ đầu”

Với GET JSON ngắn, lỗi trước khi Gateway gửi status/body đôi khi có thể được retry để trả kết quả hoàn chỉnh. Nhưng với **SSE**, NDJSON, response tệp lớn hoặc WebSocket, response có thể đã gửi một phần:

~~~text
HTTP/1.1 200 OK
Content-Type: text/event-stream

event: progress
data: 10

event: progress
data: 20

<upstream connection interrupted>
~~~

Sau khi status và headers đã commit:

- Gateway không thể quay lại đổi status 200 thành 503 trên **cùng HTTP response**.
- Gửi lại toàn bộ stream có thể làm client nhận **trùng sự kiện** hoặc bản ghi.
- Một retry tự phát bên trong filter có thể tiếp tục ghi vào response đã commit, gây lỗi framing/protocol.
- Client thường cần **reconnect** và cơ chế resume theo event ID/checkpoint nếu hợp đồng hỗ trợ.

**Không mặc định Retry GatewayFilter cung cấp exactly-once delivery cho streaming**. Hãy test riêng sự cố trước/giữa stream và chọn chính sách không replay vô điều kiện. WebSocket có handshake và kết nối hai chiều, nên không áp policy retry request/response ngắn như trên một socket đã upgrade.

### Client cancellation không nhất thiết hủy mọi side effect

Khi client ngắt kết nối hoặc deadline hết, Reactor có cơ chế cancellation cho publisher. Tuy nhiên, backend có thể đã nhận request và commit dữ liệu; không thể dùng tín hiệu cancel như bằng chứng “operation chưa diễn ra”. Nên truyền deadline/cancel một cách có chủ đích tới các tầng hỗ trợ, dừng retries mới khi client đã bỏ và vẫn dựa vào **idempotency/status lookup** cho thao tác ghi.

## 15. Security, tokens và mỗi attempt outbound

Mỗi retry là một lần Gateway gửi HTTP request mới tới upstream (nếu attempt thật sự được thực hiện). Điều này cũng có nghĩa:

- Header `Authorization` có thể được gửi lại.
- `Cookie`, API key và trace headers có thể được sao chép sang attempt khác.
- Service discovery hoặc route bị sửa có thể khiến attempt sau chọn đích khác.
- Logging ở mỗi attempt có thể làm lộ cùng token nhiều lần nếu bật wiretap/headers dump.

**Không vì cần retry mà nới lỏng authentication/authorization.** Một request trả 401/403 không nên được retry như lỗi dependency; fallback không được biến lỗi không đủ quyền thành 200. Nếu backend chỉ chấp nhận token có audience cụ thể, retry sang service khác không được tự mang theo token của service cũ.

Khi Retry và TokenRelay cùng tồn tại, hãy xác minh **mọi attempt chỉ được gửi đến đích tin cậy** và token vẫn còn hợp lệ cho scope/audience. Không dùng một shared admin token để “làm retry thành công” thay cho token người dùng.

Đối với logging:

~~~text
NÊN:
  route=catalog-read
  attempt=2
  outcome=connect_timeout
  upstreamService=catalog-service

KHÔNG NÊN:
  Authorization=Bearer eyJ...
  Cookie=SESSION=...
  url.full=/api/orders?access_token=...
~~~

Chỉ log metadata không nhạy cảm: route ID, attempt index, status/error type được chuẩn hóa, latency, request/trace ID có kiểm soát và circuit state. Không dump toàn exchange/body khi một retry thất bại.

## 16. Quan sát đúng: đo operation, inbound request và outbound attempt

Nếu chỉ nhìn `HTTP 503/s` tại Gateway, bạn không biết:

- Client đã tự gửi lại bao nhiêu lần?
- Gateway đã thêm bao nhiêu retries?
- Orders/SDK tiếp tục retry bao nhiêu lần?
- Một response thành công có phải attempt thứ ba hay không?
- Gateway CircuitBreaker OPEN nên không gọi backend, hay backend vẫn bị gọi và trả 503?
- Một fallback 200 đang che số request suy giảm hay không?

Để phân biệt, nên có **ít nhất ba lớp quan sát**:

| Lớp đo | Ý nghĩa | Ví dụ nhãn an toàn |
| --- | --- | --- |
| **User operation / logical request** | Một hành động nghiệp vụ được khởi tạo | Loại operation, tenant tier nếu phù hợp, không phải token |
| **Inbound Gateway request** | Mỗi HTTP request thực sự vào Gateway | Route ID, method, final status |
| **Outbound upstream attempt** | Mỗi lần Gateway/SDK thực sự gọi dependency | Service ID, attempt index, outcome |

Nếu có fan-out, phải tách theo dependency/operation để không coi hai calls hợp lệ là một lần retry. Nếu có nhiều Gateway replicas, metrics cần tổng hợp đúng instance và khoảng thời gian.

### Những metric quan trọng

| Metric khái niệm | Cách dùng |
| --- | --- |
| Original requests rate | Lưu lượng khởi tạo ở boundary phù hợp |
| Retry attempts rate | Lượng calls bổ sung do retry |
| Retry ratio | Retries / original requests hoặc accepted operations, phải ghi rõ mẫu số |
| Outbound attempts by route/service | Định vị dependency đang bị nhân tải |
| Attempt outcome by status/exception | Xác định lỗi nào kích hoạt policy |
| Backoff wait histogram | Xem requests có đang đồng loạt retry không |
| Retry budget remaining / exhausted | Biết khi nào policy đang chủ động giảm tải |
| Deadline exceeded / client cancelled | Tìm retries xảy ra quá muộn hoặc vô ích |
| Circuit breaker state/call-not-permitted | Phân biệt fail fast và lỗi backend |
| Rate limiter rejection | Đo request bị chặn ở lớp admission |
| Reactor Netty active/idle/pending connections | Tìm connection pressure do attempts |
| Upstream p95/p99 latency | Kiểm tra retry đang cải thiện hay phá hiệu năng |
| Idempotency replay/deduplication count | Tìm thao tác ghi bị gửi lại và được chặn |

Những tên ở bảng là **khái niệm cần đo**, không phải tên Micrometer meter mặc định được bảo đảm trong mọi release. Spring Cloud Gateway, Reactor Netty, Resilience4j, Micrometer/Actuator và OpenTelemetry có thể cung cấp một phần telemetry khi được bật; cần xác minh metric/tag và chi phí cardinality trên hệ thống thật.

### Tương quan giữa attempts nhưng không dùng token làm ID

Một `operationId` đáng tin có thể giúp gom các attempts cho **cùng thao tác logic**, và một `attemptIndex` giúp xem lần thử nào đã xảy ra. Tuy nhiên:

1. Không dùng `Authorization` hoặc session cookie làm correlation ID.
2. Không đưa user ID, raw URL query hoặc operation ID vô hạn vào **metrics labels**.
3. Nếu nhận correlation ID từ client, kiểm tra độ dài, định dạng và quyền tin cậy trước khi chuyển tiếp hoặc ghi log.
4. Không tin một header `X-Attempt` do client tự khai để cấp thêm budget hoặc cho phép vượt rate limit.
5. Với tracing, có thể dùng các span con cho từng attempt, nhưng không ghi full JWT, Cookie, query hoặc body vào span attributes/baggage.

### Ví dụ đọc số liệu

~~~text
Window: 60 seconds, route=catalog-read
Inbound HTTP requests            : 10.000
Outbound calls to catalog        : 13.000
Additional upstream attempts     :  3.000
Gateway-level amplification      :  1,30x
Retry budget exhausted operations:    800
Circuit denied attempts          :    600
~~~

Đây là số **minh họa**, giả định mỗi inbound request hợp lệ có đúng một intended Catalog call ban đầu và không có fan-out, cache short-circuit hoặc các route phụ. Nếu số lượng bị circuit chặn đáng kể, “additional attempts = outbound − inbound” có thể **không còn là phép đếm retry chính xác**; cần instrument retry filter trực tiếp và phân biệt `attempt_started` với `attempt_rejected`.

## 17. Ví dụ Java khi retry do service sở hữu: luôn chọn một chủ thể

Nếu tổ chức quyết định **Orders service** sẽ tự retry một WebClient GET tới Inventory, thì route Gateway tương ứng **không nên mặc định bật thêm Retry** cho cùng lỗi. Một ví dụ Java minh họa chính sách hẹp:

~~~java
import java.time.Duration;

import org.springframework.http.HttpStatus;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public final class InventoryClient {
    private final WebClient client;

    public InventoryClient(WebClient client) {
        this.client = client;
    }

    public Mono<String> getStock(String sku) {
        return client.get()
                .uri("/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(String.class)
                .retryWhen(
                        Retry.backoff(1, Duration.ofMillis(100))
                                .maxBackoff(Duration.ofMillis(800))
                                .jitter(0.5)
                                .filter(this::isRetryable)
                );
    }

    private boolean isRetryable(Throwable error) {
        if (error instanceof WebClientResponseException responseError) {
            HttpStatus status =
                    HttpStatus.resolve(responseError.getStatusCode().value());
            return status == HttpStatus.BAD_GATEWAY
                    || status == HttpStatus.SERVICE_UNAVAILABLE
                    || status == HttpStatus.GATEWAY_TIMEOUT;
        }
        // Không tự coi mọi exception là retryable.
        return false;
    }
}
~~~

Giải thích:

- `Retry.backoff(1, ...)` cho phép **một retry ngoài attempt đầu** khi lỗi vượt qua filter.
- `.jitter(0.5)` tạo độ lệch ngẫu nhiên cho khoảng chờ ở Reactor Retry; **khác** với cấu hình `backoff` của Retry GatewayFilter đã nêu.
- `.filter(this::isRetryable)` cố tình chỉ thử lại một số status; code mẫu **không retry connection reset hoặc timeout**. Muốn xử lý các exception đó phải phân loại rõ và test. Không thêm `Throwable -> true`.
- `bodyToMono(String.class)` chỉ phù hợp khi kết quả dự kiến nhỏ và dạng text. Với binary, stream hoặc dữ liệu lớn, cần kiểu/body contract khác.
- Đoạn code **chưa có tổng deadline, retry budget chia sẻ, circuit breaker và telemetry**, vì vậy **chưa phải giải pháp production đầy đủ**. Nó minh họa cách gắn chính sách có chọn lọc ở **một tầng**, không hướng dẫn bật retry ở cả Gateway và service.

### Chú ý sự khác biệt giữa status và exception

Trong `WebClient.retrieve()`, HTTP 4xx/5xx thường được ánh xạ thành `WebClientResponseException` khi body được xử lý qua cách gọi ở ví dụ. Trong Gateway, một HTTP response 503 có thể được **Retry GatewayFilter** xét trực tiếp từ status, tùy factory/version. Do đó, code Reactor `retryWhen` không phải bản thay thế có thể copy nguyên vào GatewayFilter: cần hiểu **Publisher mà mỗi tầng đang nhìn thấy**.

### Khi muốn có deadline tổng

Một phần mở rộng production cần tính thời gian còn lại trước mỗi attempt, kết hợp timeout HTTP client và stop condition. Đừng chỉ thêm `.timeout(Duration.ofSeconds(2))` ở một vị trí bất kỳ rồi cho rằng mọi timer, queue và cancellation được xử lý đúng. Vị trí đặt operator có thể giới hạn **toàn bộ publisher** hoặc **từng attempt**, và thứ tự với `retryWhen` sẽ quyết định tổng thời gian; phải kiểm thử.

## 18. Backend stub để đếm attempts thay vì đoán

Để kiểm thử chính sách của Gateway, dùng một backend **giả lập trong môi trường thử nghiệm** có thể trả 503 theo số lần gọi, sau đó trả 200. Nhờ đó có thể xác minh Gateway thực sự dừng ở đúng số attempts.

~~~java
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class CatalogStubController {

    private final AtomicInteger calls = new AtomicInteger();

    @GetMapping("/catalog/items/{id}")
    public Mono<ResponseEntity<Map<String, Object>>> getItem(
            @PathVariable String id) {

        int attempt = calls.incrementAndGet();

        if (attempt <= 1) {
            return Mono.just(ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                    .body(Map.of(
                            "code", "SIMULATED_TEMPORARY_FAILURE",
                            "attempt", attempt)));
        }

        return Mono.just(ResponseEntity.ok(Map.of(
                "itemId", id,
                "attempt", attempt,
                "name", "Test item")));
    }

    int callCount() {
        return calls.get();
    }

    void resetCounter() {
        calls.set(0);
    }
}
~~~

Đây là **stub đơn tiến trình**, chỉ để minh họa/kiểm thử. Nếu nhiều requests chạy đồng thời, counter tăng xen kẽ và kết quả của từng request khó dự đoán. Để integration test đáng tin, chạy **tuần tự hoặc cô lập mỗi test**, reset counter và không expose `resetCounter()` thành endpoint công khai. Trong ví dụ, backend mong đợi `GET /catalog/items/{id}`, khớp với route `StripPrefix=1` của phần 10.

### Kỳ vọng với `retries: 1`

Với counter bắt đầu từ 0 và một request đơn lẻ:

1. Attempt #1: `GET /catalog/items/42` → stub trả 503.
2. `Retry` nhận biết 503 và nếu budget/điều kiện cho phép, chờ backoff.
3. Attempt #2: stub trả 200 với `attempt: 2`.
4. Gateway trả 200 và stub counter là **2**.

Nếu đặt `retries: 0`, Gateway sẽ không retry do filter này; request đầu nhận 503, counter là **1**. Nếu stub luôn trả 503 với `retries: 1`, counter tối đa là **2**, không phải 3, trong điều kiện request đủ đến upstream và không có retries ở tầng khác.

**Thử nghiệm quan trọng:** Nếu client tự gửi lại một HTTP request mới, counter có thể tăng tiếp. Hãy phân biệt “một HTTP inbound request bị Gateway retry” với “hai inbound requests độc lập do client tạo”.

## 19. Từ WebTestClient đến ma trận kiểm thử chịu lỗi

Một test HTTP có thể kiểm tra kết quả cuối, nhưng phải đi kèm **backend counter** để xác minh số lượt gọi thực:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.test.web.reactive.server.WebTestClient;

class CatalogGatewayRetryHttpTest {

    private final WebTestClient client = WebTestClient.bindToServer()
            .baseUrl("http://localhost:8080")
            .build();

    @Test
    void getCanRecoverAfterOneTransientFailure() {
        // Trước test: stub reset counter và không có traffic song song.
        client.get()
                .uri("/api/catalog/items/42")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.attempt").isEqualTo(2);
    }
}
~~~

Đây là **mảnh integration test minh họa**, chưa chạy trong môi trường này. Để hoàn chỉnh cần JUnit/Spring Test, Gateway ở cổng 8080, backend stub được route đúng, reset counter trước test và assertion độc lập ở stub rằng `callCount() == 2`. Không chỉ dựa vào trường `attempt` trong body nếu backend có thể chạy đồng thời hoặc có nhiều instances.

### Ma trận kiểm thử cần có

| Kịch bản | Cấu hình/tác động | Kỳ vọng |
| --- | --- | --- |
| A. GET thành công ngay | Stub trả 200 | 1 outbound attempt, không retry |
| B. GET lỗi tạm thời | Stub trả 503 rồi 200 | 2 attempts với `retries: 1` |
| C. GET luôn lỗi | Stub luôn trả 503 | Tối đa 2 attempts; kết quả cuối lỗi theo contract |
| D. GET trả 400/401/403/404 | Không thuộc `statuses` retry | Không tăng attempts do status đó |
| E. GET trả 429 và Retry-After | Không cấu hình retry 429 | Không retry ngay; preserve policy |
| F. POST/payment | Route không gắn Retry hoặc methods không cho phép | Không tự replay body/side effect |
| G. Response timeout | Stub delay quá deadline | Chỉ retry nếu exception được policy cho phép và còn budget |
| H. Circuit breaker OPEN | Breaker từ chối upstream | Không có HTTP attempt đến backend khi bị từ chối |
| I. Client cancellation | Client đóng trước kết quả | Không sinh retry mới sau hủy; kiểm tra cancellation hiệu quả |
| J. Retry budget hết | Quota/budget test hết | Không retry thêm, giữ hành vi lỗi có kiểm soát |
| K. Hai tầng retry cùng bật | Client và Gateway đều retry | Đo multiplication, sau đó sửa về một chủ sở hữu |
| L. Nhiều Gateway replica | Chạy test/tải có kiểm soát | Budget toàn cụm không vượt ngưỡng đã cam kết |
| M. SSE gửi dở | Stub gửi một phần rồi reset | Không replay vào response đã commit |
| N. Body lớn | POST upload test trong lab | Không cache/replay ngoài policy và tài nguyên |
| O. Đích redirect bất thường | Upstream redirect host không tin cậy | Không chuyển credential hoặc retry sang host ngoài allowlist |

Đừng dùng một backend production đang suy giảm làm “thí nghiệm tải”; hãy sử dụng stub/fault injection có giới hạn trong môi trường an toàn. Khi thử multi-layer retry, phải giới hạn traffic để tránh tự tạo outage.

### Kiểm tra Retry GatewayFilter có thực sự chạy

Một route `Path` không khớp thì filter của route đó không chạy. Khi thấy GET 503, hãy phân biệt:

1. Route có được chọn không?
2. Filter Retry có được khởi tạo đúng không?
3. Status/exception có thuộc policy không?
4. Deadline hoặc budget có cho retry không?
5. Có filter khác đã commit response, chuyển status hoặc short-circuit trước đó không?
6. Request body có thể phát lại an toàn không?
7. Upstream counter có tăng đúng số lần không?

Quan sát đủ các bước giúp tránh phản ứng sai như tăng `retries` từ 1 lên 5 khi thực ra request chưa đi vào route hoặc lỗi đến từ lớp khác.

## 20. Runbook: khi retry amplification đang làm outage nặng hơn

Giả sử hệ thống báo latency p99 tăng mạnh, 503 xuất hiện thường xuyên, và backend CPU/DB queue gần bão hòa. Đồng thời HTTP client logs cho thấy nhiều lần retry. **Không nên tăng retry count để “cải thiện khả năng phục hồi” trước khi xác định tải phát sinh.**

### Bước 1 — Xác định điểm nguồn và dependency bị tác động

Thu thập trong cùng một cửa sổ thời gian:

- Client/user operations rate nếu hệ thống có thể đo.
- Inbound Gateway requests theo route.
- Outbound attempts theo service và loại lỗi.
- Retry attempts ở SDK, service mesh, ingress và client nếu có.
- Rate limiter rejection, circuit breaker state, connection pool pending, backend p95/p99.
- Số Gateway replicas và nguồn service discovery đang cung cấp những instance nào.

Phân biệt nguyên nhân: backend không có instance, lỗi TLS, connect timeout, response timeout, 429 theo quota, 503 vì quá tải, hay DB chậm. **Không phải mọi 503 là cùng một sự cố**.

### Bước 2 — Ước lượng độ khuếch đại

Nếu có đủ số liệu và request vào một route tương ứng với một call backend:

~~~text
Inbound Gateway requests / second     = 900
Outbound attempts / second           = 2.250
Tỷ lệ attempts trên một inbound      = 2,5x
Extra attempt rate                   = 1.350 attempts/s
~~~

Đây là ví dụ giả định. Nếu frontend còn tự retry 3 lần, logical operations ban đầu có thể ít hơn nhiều so với 900 inbound requests/s; cần thêm metric ở frontend hoặc operation-level tracing để đánh giá tổng tải phát sinh.

### Bước 3 — Giảm khuếch đại có kiểm soát

Các biện pháp tùy tình huống:

1. **Tạm giảm hoặc tắt retry ở một tầng** đang nhân attempts mà không cải thiện tỷ lệ thành công, theo quy trình thay đổi cấu hình.
2. **Đặt retry budget** hoặc quota thấp hơn, ưu tiên requests ban đầu.
3. **Cấu hình backoff và jitter** ở tầng sở hữu retry, giảm herd effect.
4. **Giới hạn concurrency và pending queue**, tránh backend bị dồn thêm kết nối.
5. **Circuit breaker** có thể ngắt lời gọi tới dependency suy giảm, nhưng fallback phải trả đúng status/hợp đồng.
6. **Thực hiện load shedding/rate limiting** có chủ đích nếu năng lực phục vụ thấp hơn lượng vào.
7. Nếu instance bị lỗi riêng lẻ, **sửa readiness/health/discovery** để ngừng chọn nó, không để retry tự “tìm đường” vô hạn.

Nếu là hệ thống nhiều replica, thay đổi retry budget tại chỉ một replica có thể không đủ; cần kiểm tra toàn bộ fleet. Khi tắt retry, tỷ lệ thành công ngắn hạn có thể giảm nhưng **backend được giải áp**, tạo cơ hội phục hồi — cần theo dõi cả hai chiều thay vì chỉ nhìn số 200.

### Bước 4 — Khắc phục nguyên nhân nền

Retry amplification thường là **triệu chứng và tác nhân khuếch đại**, không phải nguyên nhân đầu tiên. Điều tra backend CPU, GC, DB connection pool, query chậm, DNS, TLS, giới hạn file descriptor, thread/event-loop blocking, network policy và rolling deployment.

Không hạ xác minh TLS hoặc bỏ authentication chỉ để retry thành công. Nếu dependency đang outage lâu, trả lỗi rõ ràng cho client theo contract, cung cấp `Retry-After` khi có cơ sở, hoặc dùng queue/outbox/deferred processing **nếu nghiệp vụ thực sự hỗ trợ**.

### Bước 5 — Xác nhận recovery và chống tái diễn

1. Backend latency và error rate quay lại ngưỡng chấp nhận.
2. Attempts/inbound ratio trở về mức dự kiến.
3. Retry budget không liên tục cạn, circuit breaker không dao động OPEN/CLOSED bất thường.
4. Inbound request rate không bị che bởi client auto-retry.
5. Không còn attempts sau khi deadline/cancellation.
6. Tỷ lệ duplicate operations được idempotency backend ngăn chặn.
7. Thử fault injection an toàn với cùng chính sách mới và ghi kết quả vào runbook.

Không kết luận hệ thống khỏe chỉ vì một Gateway replica có HTTP 200 trở lại; cần xem toàn cụm và dependency sâu nhất.

## 21. Những phản mẫu cần tránh

| Phản mẫu | Hệ quả | Hướng sửa |
| --- | --- | --- |
| Client, CDN, Gateway, service và SDK cùng retry mặc định | Attempts nhân theo nhiều tầng | Quy định tầng sở hữu retry và tổng budget |
| Nhầm `retries: 3` là tổng 3 attempts | Số lượt gọi lớn hơn dự kiến | Tính attempt đầu + retries theo semantics filter |
| Retry mọi 5xx không phân loại | Lặp lỗi code hoặc lỗi backend lâu dài | Chọn status/exception tạm thời đã kiểm chứng |
| Retry ngay khi 429 có Retry-After dài | Làm quota/throttling nặng hơn | Tôn trọng tín hiệu chờ, deadline và backpressure |
| Backoff cố định không jitter trên hàng nghìn clients | Retry waves đồng bộ | Jitter ở chủ thể retry hỗ trợ |
| Retry sau khi hết client deadline | Tạo tải không còn ích cho người dùng | Tính remaining deadline trước mỗi retry |
| Tăng pool max connections để hấp thụ vô hạn attempts | Cạn socket/CPU/DB và đẩy áp lực downstream | Bounded concurrency, budget, sửa nguồn lỗi |
| Retry POST/Payment không có idempotency | Double charge/double order | Chống lặp atomic ở backend, không blind retry |
| Replay multipart/streaming body vô điều kiện | Buffer phình, body không replay được | Không retry hoặc thiết kế upload resumable |
| Dùng header `X-Attempt` từ client làm quota đáng tin | Client có thể tự nâng budget | Tin nguồn được xác thực, validate/cap giá trị |
| Tự gọi `chain.filter(exchange)` hai lần trong custom filter | Dễ nhân side effect, sai Reactive lifecycle | Dùng factory/operator đã hiểu và return Publisher |
| Retry sau HTTP response commit | Không thể reset status/body; dữ liệu trùng | Reconnect/resume ở cấp ứng dụng |
| Thấy 503 và mặc định retry luôn sang instance mới | Có thể chọn cùng instance hoặc lỗi do service hoàn toàn | Kiểm tra discovery, routing và policy |
| Bật breaker và Retry nhưng không biết filter order | Sai số mẫu breaker, retry storm | Test attempt count, state và precedence |
| Chỉ đo client-facing 200/503 | Không biết backend bị gọi bao nhiêu lần | Đo inbound, outbound attempts và retries riêng |
| Dùng token/raw URL làm trace/metric label | Lộ bí mật, cardinality rất lớn | Metadata allowlist, trace ID an toàn |
| Fallback gọi service khác và retry vô hạn | Chuyển sự cố sang dependency khác | Budget và timeout cho fallback |
| Giảm threshold breaker đến mức rất nhỏ để chống tải | False OPEN, chặn traffic khỏe | Điều chỉnh theo SLO, mẫu và lỗi thực |

### Phân biệt retry với hedging

**Hedged requests** có thể gửi nhiều calls **song song** hoặc có độ trễ ngắn tới nhiều replica để giảm tail latency. Nó khác retry tuần tự sau failure, nhưng vẫn **nhân tải** và có thể tạo side effect nếu không kiểm soát. Nếu hệ thống có hedging ở SDK/mesh, hãy đưa số calls này vào **cùng ngân sách outbound** và chỉ dùng với operations được phép. Không giả định “không có retries” thì hệ thống chỉ tạo một call cho mỗi operation.

### Phân biệt retry với manual resubmission

Khi UI báo timeout, người dùng bấm lại “Thanh toán”. Đó là một **user action mới ở tầng giao diện**, không phải retry filter của Gateway, nhưng **có thể là cùng thao tác nghiệp vụ**. Idempotency và trạng thái giao dịch ở backend phải bao phủ cả hai, đặc biệt khi request đầu đã commit mà response bị mất.

## 22. Bài thực hành: giảm attempts mà vẫn giữ khả năng phục hồi

**Bối cảnh:** Spring Cloud Gateway proxy `GET /api/catalog/items/{id}` tới Catalog service qua `lb://catalog-service`. Client, Gateway và Catalog SDK đều có khả năng retry. Khi Catalog trả 503, số lần gọi tăng và latency p99 xấu đi.

### Phần A — Vẽ call graph và tính cận trên

1. Liệt kê các tầng client → ingress → Gateway → Catalog → Inventory.
2. Ghi **attempts tối đa** của từng tầng, không chỉ tên `retries`.
3. Giả sử client 3 attempts, Gateway 3 attempts, Catalog SDK 2 attempts. Tính:

\[
A_{\max}=3\times3\times2=18
\]

4. Nếu một user operation có thêm fan-out tới Pricing, tính **riêng** calls tới Pricing và Inventory, tránh nhân sai tổng số.
5. Nêu thời điểm nào circuit breaker, deadline hoặc request cancellation có thể khiến số attempts thực nhỏ hơn cận trên.

### Phần B — Chọn tầng retry chính và cấu hình

1. Chọn **Gateway** làm chủ retry **chỉ cho GET/HEAD Catalog**, hoặc chọn client và tắt Retry GatewayFilter. Ghi rõ lý do.
2. Nếu chọn Gateway, áp `Retry` với `retries: 1`, status 502/503/504, backoff có giới hạn.
3. Tắt retry cho cùng lỗi ở các tầng còn lại hoặc giảm budget và chứng minh không còn nhân attempts ngoài thiết kế.
4. Định nghĩa operation deadline và per-attempt timeout; kiểm tra tổng thời gian gồm cả backoff.
5. Đặt retry budget/giới hạn attempts theo route và theo cụm trong mô hình production.
6. Không thêm retry POST Payments; thay bằng contract idempotency và status lookup nếu cần.

### Phần C — Kiểm thử với stub đếm requests

1. Dựng backend stub giống phần 18, cho trả 503 lần đầu, 200 lần kế tiếp.
2. Gửi một GET qua Gateway, xác nhận backend nhận **tối đa 2 attempts** và response cuối đúng JSON.
3. Cho stub luôn trả 503; xác minh số attempts dừng ở giới hạn, không tăng vô hạn.
4. Cho stub trả 400/401/403/404; xác minh **không retry** do status không được cấu hình.
5. Gửi burst ngắn có kiểm soát; đo retries/request và pending connections, không dùng production.
6. Bật thêm retry ở client trong lab để đo amplification, sau đó tắt và so sánh.
7. Thử trường hợp circuit OPEN: outbound HTTP attempts phải giảm, fallback hợp đồng đúng.

### Phần D — Kiểm thử tải và an toàn nghiệp vụ

1. So sánh **success rate, p95/p99 latency, backend QPS, retry attempts và error rate** giữa trước/sau.
2. Kiểm tra retry budget vẫn được giữ khi chạy nhiều Gateway replicas.
3. Với thao tác ghi giả, mô phỏng backend commit rồi mất response; dùng idempotency key để không tạo hai records.
4. Với body lớn, quan sát bộ nhớ/pooled buffers; không tự retry upload chưa hỗ trợ replay.
5. Với SSE, ngắt sau vài event, xác minh không cố replay stream vào response đã commit.
6. Ghi lại hành vi khi nhận `Retry-After` và khi client deadline đã hết.
7. Kiểm tra logs/traces không chứa token, cookie hay full URL có query nhạy cảm trong mọi attempt.

### Bảng kết quả thí nghiệm nên nộp

| Case | Inbound HTTP requests | Outbound attempts | Final status | Nhận xét |
| --- | ---: | ---: | --- | --- |
| 200 ngay | 1 | 1 | 200 | Không retry |
| 503 rồi 200, Gateway `retries: 1` | 1 | 2 | 200 | Một retry được phép |
| 503 liên tục, Gateway `retries: 1` | 1 | 2 | 503/fallback theo policy | Dừng đúng giới hạn |
| 400 từ backend | 1 | 1 | 400 | Không retry |
| 401/403 từ auth layer | 1 | 0 (nếu bị chặn trước proxy) | 401/403 | Bảo toàn auth |
| Client 2 attempts, Gateway 2 attempts | 2 | Tối đa 4 | Theo backend | Khuếch đại 4× so với 1 operation |
| Circuit OPEN | 1 | 0 trong nhánh bị chặn | Fallback | Fail fast |

**Các kết quả trong bảng là kỳ vọng logic trong môi trường kiểm soát**, không phải kết quả đã chạy thực tế. Nếu route có thêm filters, load balancing, caching hoặc auth, cần điều chỉnh preconditions và đo số attempts bằng backend counter.

**Tiêu chí đạt:** Người học giải thích được nguồn khuếch đại, có policy một chủ retry, giới hạn attempt và tổng deadline, tách GET khỏi POST có side effect, chứng minh bằng metrics/stub rằng attempts nằm trong ngân sách, không log credential và có runbook khi backend suy giảm.

## 23. Ghi nhớ

- **Retry hữu ích cho lỗi tạm thời nhưng nguy hiểm khi nhiều tầng cùng bật.** Cận trên của các attempts lồng nhau có thể tăng theo tích \(\prod_i(1+r_i)\), không phải phép cộng.
- **Phân biệt retries và attempts.** Trong Retry GatewayFilter, một `retries` thường là số lần **bổ sung sau lần gọi đầu tiên**; kiểm tra semantics của phiên bản đang chạy.
- **Đặt chủ sở hữu retry theo dependency/operation.** Tránh client, ingress, Gateway và SDK tự retry cùng lỗi mà không có tổng budget.
- **Budget, deadline, backoff và jitter cần đi cùng nhau.** Backoff không mặc nhiên có jitter; retry sau deadline chỉ tăng tải mà ít có giá trị.
- **Chỉ retry lỗi được phép và phương thức phù hợp.** 400/401/403/404 thường không retry; 429/503 có thể có `Retry-After`; POST/payment cần idempotency thực sự ở backend.
- **Request body replay trong WebFlux có chi phí**, nhất là multipart/upload/stream. Không gọi `chain.filter(exchange)` nhiều lần tùy tiện hoặc giữ DataBuffer sai vòng đời.
- **Retry, CircuitBreaker, RequestRateLimiter, LoadBalancer và connection pool có trách nhiệm khác nhau.** Thứ tự filter ảnh hưởng attempts và việc đánh giá lỗi; cần đo bằng stub/metrics.
- **Sau khi response commit, không thể retry cùng response như chưa gửi gì.** Với SSE/WebSocket, dùng reconnect/resume theo hợp đồng.
- **Đo outbound attempts và retry ratio bên cạnh inbound requests**, kết hợp tracing an toàn, circuit state và backend metrics để phát hiện amplification thật.

Một hệ thống **SPRING_CLOUD_GATEWAY** có khả năng phục hồi tốt không phải hệ thống thử lại nhiều nhất, mà là hệ thống **thử lại đúng lỗi, đúng tầng, trong ngân sách hữu hạn và dừng kịp lúc trước khi đẩy dependency vào quá tải**.
