# Tính lặp an toàn của GET so với thao tác ghi dữ liệu

## 1. Vì sao retry có thể vừa cứu request vừa tạo dữ liệu trùng?

Trong hệ thống microservices, **Spring Cloud Gateway** làm cổng vào chung: nó chọn route bằng predicate, chạy filter chain, biến đổi path/header, khám phá instance của dịch vụ và chuyển request đến backend. Một request có thể gặp lỗi mạng ngắn hạn, timeout, HTTP 502/503 hoặc instance vừa bị ngắt khi triển khai.

**Retry (thử lại)** nghĩa là phát lại một thao tác sau khi attempt trước không mang lại kết quả mong muốn. Với `GET /api/catalog/products/42`, việc thử lại sau lỗi tạm thời thường hợp lý. Nhưng với `POST /api/payments`, một timeout có thể xảy ra **sau khi backend đã trừ tiền**: phát lại POST có thể trừ thêm một lần.

Chủ đề **“Tính lặp an toàn của GET so với thao tác ghi dữ liệu”** thuộc chương **Thử lại yêu cầu**, module **SPRING_CLOUD_GATEWAY**. Bài này giải thích:

1. Phân biệt **safe**, **idempotent** và “response giống nhau”.
2. Đánh giá GET so với POST, PUT, DELETE, PATCH theo HTTP semantics và nghiệp vụ.
3. Hiểu các trạng thái không xác định khi backend đã xử lý nhưng Gateway chưa nhận response.
4. Cấu hình `Retry GatewayFilter` chỉ cho GET bằng YAML ở Gateway Server WebFlux.
5. Bảo vệ thao tác ghi bằng **Idempotency-Key**, unique constraint và khôi phục trạng thái.
6. Kiểm thử số lần upstream thật sự nhận request, cùng các vấn đề backoff, body caching, timeout, rate limiting, circuit breaker, TLS và observability.

> **Phạm vi:** Spring Cloud Gateway **Server WebFlux** và `Retry GatewayFilter`. Ví dụ route minh họa namespace mới `spring.cloud.gateway.server.webflux.routes` và namespace `spring.cloud.gateway.routes` thường dùng ở nhánh 4.x. Server MVC là stack khác, đặc biệt khi cache/replay request body; luôn kiểm tra tài liệu đúng phiên bản.

## 2. Safe và idempotent là hai thuộc tính khác nhau

### 2.1. Safe: client chỉ yêu cầu đọc

Theo **RFC 9110**, một phương thức *safe* có ngữ nghĩa chủ yếu là đọc dữ liệu: client không yêu cầu thay đổi trạng thái tài nguyên. Các method được định nghĩa safe gồm **GET, HEAD, OPTIONS, TRACE**.

Ví dụ:

~~~http
GET /api/catalog/products/42 HTTP/1.1
Host: api.example.test
~~~

Client muốn xem sản phẩm 42. Hệ thống vẫn có thể ghi access log, metric hoặc đếm lượt xem phụ trợ mà không vi phạm ý định read-only của client. Nhưng nếu API cài `GET /api/payments/charge?id=42` để **trừ tiền thật**, endpoint đang sai ngữ nghĩa HTTP; không được coi nó an toàn để retry chỉ vì method là GET.

### 2.2. Idempotent: lặp lại vẫn có cùng hiệu ứng dự định

Một request có tính *idempotent* nếu thực hiện **cùng yêu cầu nhiều lần** có hiệu ứng dự định lên tài nguyên như thực hiện một lần.

Ví dụ:

~~~http
PUT /api/users/42/settings HTTP/1.1
Content-Type: application/json

{"language":"vi","darkMode":true}
~~~

Nếu PUT thực sự **đặt** giá trị của settings, hai PUT giống nhau vẫn để lại trạng thái cuối giống một PUT. Nhưng:

~~~http
POST /api/wallets/42/credits HTTP/1.1
Content-Type: application/json

{"amount":100000}
~~~

Nếu POST nghĩa là **cộng thêm 100.000 đồng**, lặp lại hai lần sẽ cộng 200.000 đồng. Cùng một payload không có nghĩa cùng một operation đã được khử trùng lặp.

### 2.3. Bảng so sánh HTTP methods

| Method | Safe theo HTTP? | Idempotent theo HTTP? | Hướng xử lý khi muốn retry |
| --- | --- | --- | --- |
| **GET** | Có | Có | Thường là lựa chọn đầu tiên, nếu endpoint thật sự chỉ đọc |
| **HEAD** | Có | Có | Thường phù hợp khi lỗi tạm thời |
| **OPTIONS** | Có | Có | Về semantics có thể, nhưng chỉ bật khi có nhu cầu thực tế |
| **TRACE** | Có theo đặc tả | Có | Nhiều hệ thống vô hiệu hóa vì bảo mật; không nên bật tự động |
| **PUT** | Không | Có | Cần đúng semantics và bảo vệ side effect phụ, version/concurrency |
| **DELETE** | Không | Có | Cần đảm bảo hiệu ứng xóa và side effect không nhân đôi |
| **POST** | Không | Không bảo đảm | **Không auto-retry** nếu chưa có idempotency/dedup |
| **PATCH** | Không | Không bảo đảm | Xem từng operation; có patch idempotent, có patch không |

**Idempotent không có nghĩa response giống nhau.** Một DELETE đầu có thể trả 204, lần sau 404, nhưng tài nguyên đều ở trạng thái “không tồn tại”. Một GET lặp lại có thể nhận giá mới vì người khác vừa cập nhật dữ liệu; bản thân thao tác GET vẫn không yêu cầu thay đổi tài nguyên.

### 2.4. Đừng đánh đồng GET với dữ liệu bất biến

GET là safe/idempotent theo hợp đồng HTTP, nhưng response có thể đổi theo thời gian, người dùng hoặc version. Nếu nghiệp vụ cần tính nhất quán phiên bản, hãy thiết kế ETag/conditional requests, snapshot hoặc kiểm soát phiên bản phù hợp; **Retry không cung cấp transaction isolation**.

## 3. Các thao tác ghi có rủi ro như thế nào?

### 3.1. POST tạo đơn hàng hoặc thanh toán

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json

{"customerId":"u-42","items":[{"sku":"book-1","quantity":1}]}
~~~

Giả sử order-service tạo `orderId=1001`, nhưng Gateway mất kết nối trước khi nhận response. Nếu Gateway tự retry POST, service có thể tạo tiếp `orderId=1002`. Client chỉ thấy một request từ trình duyệt nhưng database có hai đơn hàng.

Điều quan trọng là **hiệu ứng nghiệp vụ**, không phải byte của JSON có trùng nhau hay không.

### 3.2. PUT có tính idempotent nhưng không tự bảo vệ mọi side effect

~~~http
PUT /api/users/42/profile HTTP/1.1
Content-Type: application/json

{"displayName":"Lan"}
~~~

Nếu backend luôn **đặt** displayName bằng Lan, trạng thái chính là idempotent. Tuy nhiên:

- Gửi email “Profile Updated” **mỗi attempt** có thể tạo hai email.
- Phát hai event Kafka không được dedup có thể gây side effect tại consumer.
- Một handler **tăng revision counter** sai cách có thể làm lệch nghĩa idempotent.
- Khi có sửa đổi đồng thời, retry một PUT cũ có thể ghi đè dữ liệu mới.

Với trạng thái có version, nên cân nhắc `If-Match` và ETag. Nếu server trả `412 Precondition Failed`, không tự retry một PUT mù quáng để vượt qua kiểm tra version.

### 3.3. DELETE idempotent về trạng thái, nhưng có thể sai ở các sự kiện phụ

~~~http
DELETE /api/carts/42/items/7 HTTP/1.1
~~~

Lặp lại một DELETE có thể vẫn để item ở trạng thái “đã xóa”, nhưng nếu handler tạo hai tác vụ hoàn tiền hoặc hai domain events dẫn đến charge/refund, hệ thống vẫn có vấn đề. Việc retry write request cần xem **toàn bộ hệ quả quan trọng**, không chỉ hàng dữ liệu chính.

### 3.4. PATCH phụ thuộc operation

Một PATCH “đặt status thành PAID” có thể idempotent theo cách cài đặt; một PATCH “tăng stock lên 1” thì thường không. Không suy luận an toàn retry chỉ từ method PATCH; cần hợp đồng operation, transaction và version.

## 4. Timeout: Gateway không biết chắc backend đã commit hay chưa

Một trường hợp nguy hiểm là **ambiguous outcome**: backend đã làm xong nhưng response thất lạc.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant G as Gateway
    participant S as payment-service
    participant D as Database
    C->>G: POST /api/payments
    G->>S: POST /payments
    S->>D: COMMIT payment P-1001
    D-->>S: OK
    Note over G,S: Mất kết nối trước response
    G-->>C: 504 / lỗi timeout
    Note over G,C: Không có bằng chứng payment chưa được tạo
    C->>G: POST lại cùng body, không có dedup
    G->>S: POST /payments lần 2
    S->>D: COMMIT payment P-1002
~~~

Nếu `TimeoutException` hoặc `504 Gateway Timeout` xảy ra, **không có nghĩa backend chưa xử lý request**. Một số thời điểm lỗi có độ rủi ro khác nhau:

| Vị trí lỗi | Điều Gateway thấy | Điều có thể khẳng định |
| --- | --- | --- |
| DNS thất bại trước khi gửi request | Unknown host | Chưa kết nối đến điểm đích đó |
| TCP connect refused trước khi gửi | Connect error | Thường chưa có lời gọi nghiệp vụ tới instance này |
| Gửi một phần body rồi mất kết nối | I/O error | Không chắc backend có áp dụng gì chưa |
| Backend commit thành công, response mất | Timeout/504 | Side effect **có thể đã xảy ra** |
| Proxy trung gian trả 502/503 | HTTP error | Không chắc endpoint cuối đã/ chưa xử lý |
| Response đã bắt đầu gửi đến client | Response committed | Không thể coi như chưa có phản hồi để retry nguyên vẹn |

**Nguyên tắc an toàn:** với thao tác **không idempotent**, không tự động phát lại nếu không có bảo đảm idempotency theo hợp đồng hoặc bằng chứng chắc chắn request chưa được áp dụng. RFC 9110 cũng nêu giới hạn về automatic retry cho request không idempotent.

## 5. Retry GatewayFilter trong Spring Cloud Gateway

### 5.1. Điều gì xảy ra khi thêm Retry vào route?

Trong **Spring Cloud Gateway Server WebFlux**, `Retry` là một **GatewayFilter factory**. Nó có thể chạy lại phần **filter chain phía sau** khi response status hoặc exception phù hợp chính sách.

~~~mermaid
flowchart TD
    C["Client request"] --> P{"Route predicate?"}
    P -->|"Khớp"| R["Retry GatewayFilter"]
    P -->|"Không"| N["Route khác / không có route"]
    R --> F["Filter phía sau + HTTP routing"]
    F --> O{"Kết quả attempt"}
    O -->|"Thành công hoặc không cần retry"| A["Response cuối"]
    O -->|"Lỗi match và còn retry"| B["Chờ backoff"]
    O -->|"Hết retry budget"| A
    B --> F
~~~

**Điều cần nhớ:** filter **phía sau Retry** có thể được chạy lại nhiều lần. Spring Security `WebFilter` ở ngoài Gateway route chain không tự động bị chạy lại theo cùng cách. Custom filter ghi log, cộng counter, thay header hoặc gọi hệ thống khác phía sau Retry phải chịu được việc thực thi nhiều lần.

### 5.2. Tham số và mặc định

| Tham số | Công dụng | Lưu ý |
| --- | --- | --- |
| `retries` | Số **lần retry thêm**, không tính attempt đầu | `retries: 2` → tối đa 3 attempts |
| `methods` | Chỉ định HTTP methods được phép retry | Mặc định của filter khi bật là **GET** |
| `series` | HTTP status series được retry | Mặc định nhóm **5xx** |
| `statuses` | Status cụ thể được retry | Cần xét đồng thời với `series` đang có hiệu lực |
| `exceptions` | Loại exception làm phát sinh retry | Tài liệu WebFlux nêu mặc định `IOException`, `TimeoutException` |
| `backoff` | Trì hoãn giữa attempts | Mặc định không bật |
| `jitter` | Dao động ngẫu nhiên theo backoff | Có trong các bản mới; kiểm tra version |
| `timeout` | Giới hạn thời gian theo cơ chế Retry | Version-dependent; không nhầm timeout toàn luồng |

Tài liệu Spring Cloud Gateway WebFlux mô tả các mặc định quan trọng khi gắn Retry: **3 lần retry**, **GET**, **series 5xx**, **IOException/TimeoutException**, **không có backoff**. Như vậy một request có thể tạo đến **4 attempts** nếu mỗi attempt đều match policy và chưa bị chặn sớm.

Không phải mọi route GET đều tự retry: **phải có `Retry` filter** trong route hoặc cơ chế cấu hình riêng.

### 5.3. Status code khác exception

- **Status-based retry:** backend/proxy trả response như `502` hoặc `503`; Retry đánh giá `series` hoặc `statuses`.
- **Exception-based retry:** kết nối đóng, timeout hoặc lỗi I/O không nhận được response; Retry đánh giá exception type.

Một `500` vì bug cố định thường **không** phục hồi khi retry. Một `503` do quá tải có thể cần chờ lâu hơn retry window. Chính sách phải xét dữ liệu thực tế, không cứ gặp 5xx là thử lại vô hạn.

## 6. Cấu hình Retry chỉ cho GET bằng YAML

### 6.1. Ví dụ Server WebFlux namespace mới

Giả sử Gateway ở `localhost:8080`, `catalog-service` ở `localhost:8081`. Client gọi `GET /api/catalog/products/42`; backend xử lý `GET /catalog/products/42`.

~~~yaml
spring:
  cloud:
    gateway:
      server:
        webflux:
          routes:
            - id: catalog-get-with-retry
              uri: http://localhost:8081
              predicates:
                - Path=/api/catalog/**
                - Method=GET
              filters:
                - StripPrefix=1
                - name: Retry
                  args:
                    retries: 2
                    methods: GET
                    series: SERVER_ERROR
                    backoff:
                      firstBackoff: 100ms
                      maxBackoff: 500ms
                      factor: 2
                      basedOnPreviousValue: false
~~~

Phân tích:

1. **`Path` và `Method=GET` predicate**: chỉ chọn tuyến đọc GET.
2. **`methods: GET` trong Retry**: hạn chế thêm nếu sau này thay đổi route.
3. **`retries: 2`**: 1 lần đầu + tối đa 2 lần thử lại.
4. **`series: SERVER_ERROR`**: ví dụ chấp nhận retry với nhóm 5xx; trên production cân nhắc giảm xuống status 502/503/504 nếu không muốn thử lại lỗi ứng dụng 500.
5. **`backoff`**: thêm khoảng chờ lũy tiến, có trần.
6. **`StripPrefix=1` đặt trước Retry**: backend nhận path `/catalog/products/42`; bước sửa path này không cần nằm trong phần filter được thử lại.
7. URI upstream là ví dụ; có thể dùng `lb://CATALOG-SERVICE` nếu LoadBalancer/discovery đã được cấu hình đúng.

Đây là một **demo GET**. Nó không tự bật Spring Security, rate limiter, circuit breaker hay service registry.

### 6.2. Cấu hình tương ứng ở WebFlux 4.x

~~~yaml
spring:
  cloud:
    gateway:
      routes:
        - id: catalog-get-with-retry
          uri: http://localhost:8081
          predicates:
            - Path=/api/catalog/**
            - Method=GET
          filters:
            - StripPrefix=1
            - name: Retry
              args:
                retries: 2
                methods: GET
                series: SERVER_ERROR
                backoff:
                  firstBackoff: 100ms
                  maxBackoff: 500ms
                  factor: 2
                  basedOnPreviousValue: false
~~~

**Hai đoạn chỉ là hai namespace thay thế theo version**, không khai báo cả hai route trong một ứng dụng. Kiểm tra effective routes sau nâng cấp để tránh trường hợp namespace sai khiến Retry không được load.

### 6.3. Route POST thanh toán không có auto-retry

Đặt **một route riêng** cho API ghi:

~~~yaml
# Một mục trong danh sách routes, không phải file YAML độc lập:
- id: payment-write-no-auto-retry
  uri: http://localhost:8082
  predicates:
    - Path=/api/payments
    - Method=POST
  filters:
    - StripPrefix=1
~~~

Route này **không gắn Retry GatewayFilter**; nhưng client, ingress, service mesh hoặc SDK ở tầng khác vẫn có thể retry. Khi review tác vụ ghi quan trọng, cần xét **tất cả các tầng**.

### 6.4. Cấu hình status cụ thể

`Retry` hỗ trợ `statuses`, ví dụ:

~~~yaml
# Ví dụ tùy chọn trong args:
retries: 2
methods: GET
statuses: BAD_GATEWAY
~~~

**Không mặc định khẳng định chỉ 502 được retry** nếu default `series=SERVER_ERROR` vẫn có hiệu lực. Hãy kiểm tra effective configuration và test thực tế của release dùng trong dự án khi muốn giới hạn chính xác tập status.

## 7. Backoff, jitter và retry budget

### 7.1. Tránh retry storm

Nếu 1.000 request cùng gặp backend 503 và mỗi request tạo 3 retries tức thì, số lần upstream được gọi có thể tiến gần 4.000 attempts trong thời gian ngắn. Đó là **load amplification**, có thể làm sự cố nặng hơn.

Để tránh:

- Giới hạn `retries` và tổng deadline của request.
- Dùng **exponential backoff** với `maxBackoff`.
- Dùng **jitter** khi version hỗ trợ để các client không retry đồng bộ.
- Không retry những lỗi cố định như validation 400, thiếu quyền 403.
- Theo dõi concurrency và sức khỏe upstream; cân nhắc circuit breaker, bulkhead và load shedding.
- Không để browser, Gateway, mesh, service SDK đều cùng retry ba lần mà không tính tổng.

### 7.2. Minh họa backoff

Với:

~~~yaml
backoff:
  firstBackoff: 100ms
  maxBackoff: 500ms
  factor: 2
  basedOnPreviousValue: false
~~~

Các khoảng chờ lý thuyết có thể xấp xỉ 100 ms, 200 ms, 400 ms rồi bị giới hạn bởi 500 ms. Đây không phải đồng hồ chính xác vì scheduling bất đồng bộ, tải hệ thống và jitter.

Các phiên bản WebFlux mới còn hỗ trợ:

~~~yaml
# Phần bổ sung trong args ở version hỗ trợ:
jitter:
  randomFactor: 0.5
~~~

Không giả định mọi release cũ có cùng thuộc tính `jitter` và `timeout`. Cần đối chiếu docs và thử bind property thực tế.

### 7.3. Retry-After và 429

Response có thể báo:

~~~http
HTTP/1.1 503 Service Unavailable
Retry-After: 10
~~~

hoặc 429 kèm Retry-After. **Không giả định Retry GatewayFilter tự diễn giải mọi Retry-After** chỉ vì response có header; nếu muốn tôn trọng delta-seconds/HTTP-date, cần policy/client hỗ trợ và test riêng. Với rate limiting, không tự động retry 429 tức thì và không vượt tổng budget.

### 7.4. Timeout gây ambiguous write

Nếu timeout Gateway chỉ 300 ms mà backend đôi lúc xử lý payment 500 ms, Gateway có thể báo lỗi ngay cả khi payment hoàn tất sau đó. **Đừng chỉ tăng số retries để “chữa timeout”**. Cần điều chỉnh SLO, timeout, API bất đồng bộ hoặc cơ chế tra cứu operation ID.

## 8. Idempotency-Key: cách hỗ trợ POST thử lại có kiểm soát

### 8.1. Một key cho một ý định nghiệp vụ

**Idempotency key** là định danh ổn định do client tạo **một lần cho một ý định nghiệp vụ**, rồi dùng lại khi thử lại chính lệnh đó.

~~~http
POST /api/payments HTTP/1.1
Host: api.example.test
Content-Type: application/json
Idempotency-Key: 2b3c16bb-2026-4fbf-8e19-a632c0001122

{"orderId":"ord-42","amount":500000,"currency":"VND"}
~~~

Nếu response bị mất, client gửi lại **cùng key và payload**. Không sinh key mới cho mỗi attempt, vì backend có thể coi key mới là một giao dịch khác.

**Bản thân header không làm thao tác trở nên idempotent.** Payment service hoặc nhà cung cấp thanh toán phải triển khai dedup và xử lý đúng key. Gateway có thể chuyển header nhưng không tự khử trùng lặp cho mọi upstream.

### 8.2. Hợp đồng thường dùng

| Tình huống | Hành vi minh họa của backend |
| --- | --- |
| Key mới, input hợp lệ | Giữ key và tạo một operation |
| Key đã xử lý xong, cùng payload | Trả lại cùng kết quả/resource; không tạo operation mới |
| Cùng key nhưng payload khác | Từ chối xung đột, ví dụ 409 |
| Cùng key khi lần đầu còn chạy | Trả 202/in progress hoặc chờ có giới hạn; không chạy song song |
| Không có key ở endpoint bắt buộc | Trả lỗi xác thực input theo contract |
| Key hết hạn | Hành vi tái sử dụng được định nghĩa rõ trong retention policy |
| Hai tenant dùng cùng chuỗi key | Tách key theo principal/tenant đã xác thực |

Status cụ thể (`200`, `201`, `202`, `409`, v.v.) phụ thuộc API contract. Điều cốt lõi là **không nhân đôi tác động nghiệp vụ**.

Ví dụ lần đầu:

~~~http
HTTP/1.1 201 Created
Location: /api/payments/pay-1001
Content-Type: application/json

{"paymentId":"pay-1001","status":"SUCCEEDED"}
~~~

Khi gửi lại cùng key và payload, backend có thể trả chính resource `pay-1001` thay vì tạo `pay-1002`. Kết quả được trả và status replay cần được tài liệu hóa rõ.

### 8.3. Key không được là dữ liệu nhạy cảm

- Tạo key ngẫu nhiên đủ mạnh (ví dụ UUID ngẫu nhiên) cho từng operation.
- Không dùng raw access token, số thẻ, email hoặc số điện thoại làm key.
- Phân vùng theo tenant/client đã được xác minh, kiểm tra chiều dài/ký tự.
- Lưu fingerprint của payload để phát hiện cùng key nhưng body khác.
- Định nghĩa TTL/retention dài hơn khoảng retry/recovery dự kiến.
- Không log key kèm toàn bộ body/token trong hệ thống observability.

## 9. Chống trùng phải nguyên tử ở backend

### 9.1. Race condition khi hai POST cùng key đến đồng thời

Cách sai:

~~~text
Request A: SELECT key -> chưa có
Request B: SELECT key -> chưa có
Request A: tạo payment P-1
Request B: tạo payment P-2
Request A: INSERT key -> OK
Request B: INSERT key -> unique violation, nhưng P-2 đã tạo
~~~

Không thể chỉ “SELECT trước, nếu chưa có thì xử lý” mà coi đã có dedup. Cần **unique constraint**, transaction, locking hoặc một cách điều phối nhất quán trước khi thực hiện side effect.

### 9.2. Bảng dữ liệu minh họa

~~~sql
CREATE TABLE idempotency_requests (
    tenant_id          VARCHAR(80)  NOT NULL,
    idempotency_key    VARCHAR(160) NOT NULL,
    request_hash       CHAR(64)     NOT NULL,
    state              VARCHAR(20)  NOT NULL,
    resource_id        VARCHAR(120),
    response_status    INTEGER,
    created_at         TIMESTAMP    NOT NULL,
    PRIMARY KEY (tenant_id, idempotency_key)
);
~~~

Đây chỉ là schema học thuật. Ứng dụng thật phải thiết kế transaction isolation, retention, trạng thái `IN_PROGRESS`/`SUCCEEDED`/`FAILED`, xử lý record kẹt và quyền truy cập.

### 9.3. Luồng xử lý khuyến nghị

~~~mermaid
flowchart TD
    A["POST + Idempotency-Key"] --> B["Auth principal + validate input"]
    B --> C{"Chiếm key nguyên tử được?"}
    C -->|"Key mới"| D["Ghi IN_PROGRESS"]
    D --> E["Chạy nghiệp vụ an toàn"]
    E --> F["Lưu kết quả và resource ID"]
    F --> G["Trả response"]
    C -->|"Key cũ"| H{"Fingerprint giống?"}
    H -->|"Không"| I["Conflict"]
    H -->|"Có"| J{"Đã hoàn tất?"}
    J -->|"Có"| K["Trả kết quả đã lưu"]
    J -->|"Đang chạy"| L["202/PENDING hoặc chờ giới hạn"]
~~~

Nếu hệ thống gọi **payment provider bên ngoài**, một transaction database nội bộ không bảo đảm atomicity ở provider. Cần dùng cùng idempotency key tại provider nếu họ hỗ trợ, hoặc outbox/reconciliation và quy trình phục hồi rõ ràng. Không tuyên bố “exactly once” xuyên mọi service chỉ vì có bảng idempotency.

### 9.4. API tra cứu trạng thái thay vì retry mù

Nếu client gặp timeout sau POST, một thiết kế tốt có thể trả/ghi nhận operation ID và cung cấp:

~~~http
GET /api/payments/pay-1001 HTTP/1.1
~~~

Client truy vấn trạng thái thay vì gửi lại cùng lệnh tạo vô hạn. Nếu client không nhận được resource ID nhưng có idempotency key, backend có thể cung cấp một API tra cứu **được xác thực** theo key/operation ID. Tránh lộ trạng thái giao dịch của tenant khác.

## 10. Vì sao không mở Retry cho POST chỉ bằng methods?

Framework cho phép chọn methods; nhưng **có thể cấu hình** không đồng nghĩa **an toàn để vận hành**.

~~~yaml
# CẢNH BÁO: không dùng cho payment nếu chưa có dedup thực sự!
filters:
  - name: Retry
    args:
      retries: 3
      methods: GET,POST
      series: SERVER_ERROR
~~~

Một POST đã commit nhưng trả 500/timeout có thể bị phát lại. Trước khi bật retry cho POST, phải chứng minh:

1. Cùng key/payload không thể tạo side effect hai lần.
2. External side effects (payment, email, event, webhook) có dedup.
3. Body có thể replay đúng và nằm trong budget memory.
4. Method, statuses/exceptions được giới hạn cụ thể.
5. Retry ở client, Gateway, mesh, SDK có budget end-to-end.
6. Có cách reconcile khi response vẫn không tới client.
7. Timeout và circuit breaker không khiến hệ thống tự báo “thành công” giả.

**Gateway Retry không thay thế một idempotency implementation ở service nghiệp vụ.**

## 11. Request body và nguy cơ bộ nhớ trong WebFlux

### 11.1. GET dễ retry hơn về mặt transport

GET thường không có request body lớn. POST/PUT/PATCH thường mang JSON, multipart hoặc upload stream. Trong WebFlux, body có thể chỉ đọc một lần nên việc phát lại cần cơ chế **cache/replay body**.

Tài liệu Gateway Server WebFlux lưu ý rằng khi dùng Retry cho HTTP method có body, **body có thể được cache**, làm Gateway thiếu bộ nhớ khi tải lớn. Body được lưu trong exchange attribute `ServerWebExchangeUtils.CACHED_REQUEST_BODY_ATTR` dưới dạng `DataBuffer` ở implementation được mô tả trong tài liệu.

~~~text
100 requests đồng thời x body 1 MiB  -> đáng kể, nhưng còn tùy overhead
100 requests đồng thời x body 50 MiB -> nguy cơ RAM/direct-memory rất lớn
~~~

Đây là minh họa về quy mô dữ liệu, không phải phép tính memory footprint chính xác. Vì vậy không nên bật Retry body cho upload lớn mà chưa có memory budget, size limit, concurrency limit và load test.

### 11.2. RequestSize và codec limit không thay thế thiết kế

`RequestSize` có thể giới hạn kích thước request, nhưng một số phiên bản dựa nhiều vào `Content-Length` và cần kiểm tra hành vi với chunked/streaming. `spring.codec.max-in-memory-size` không phải giới hạn tổng upload cho mọi request chỉ proxy stream.

Hãy phối hợp giới hạn body ở ingress, upstream, gateway, giới hạn concurrent uploads và timeout. Nếu upload lớn, cân nhắc resumable upload hoặc signed URL tới object storage thay vì retry toàn bộ body qua Gateway.

### 11.3. Không sao chép cacheBody của Server MVC vào WebFlux

Server MVC có cơ chế riêng như `cacheBody` và `AdaptCachedBody`. Không tự thêm `cacheBody: true` từ ví dụ **Server MVC** vào WebFlux, vì factory và cách replay body khác nhau. Đối chiếu đúng tài liệu Server WebFlux/version.

## 12. Thứ tự filter, rate limiter, circuit breaker và LoadBalancer

Một `Retry` có thể thực thi lại **những filter phía sau**. Ví dụ sơ đồ ý tưởng:

~~~text
RequestRateLimiter
  -> Retry
       -> StripPrefix / custom filter
       -> LoadBalancer / HTTP routing
~~~

Khi retry:

- Custom filter phía sau có thể ghi log, gọi service phụ hoặc thêm header nhiều lần.
- RequestRateLimiter ở trước Retry có thể đếm **request client**, trong khi ở sau Retry có thể tiêu thụ quota khác.
- CircuitBreaker đặt trước hoặc sau Retry có thể quan sát tập lỗi khác nhau.
- Retry không bảo đảm attempt sau sẽ chọn một instance **khác** trong `lb://`.
- Nếu Netty đã gửi response body tới client, retry không thể “rút lại” byte đã commit.

Ví dụ chỉ mô tả cơ chế, không bảo đảm thứ tự hiệu lực từ thứ tự YAML đơn thuần khi có `GlobalFilter`, `OrderedGatewayFilter` và filter nội bộ. Kiểm tra effective order bằng integration test và tài liệu version.

| Cơ chế | Mục tiêu | Rủi ro nếu cấu hình sai |
| --- | --- | --- |
| **Retry** | Thử lỗi tạm thời có giới hạn | Khuếch đại tải, side effect lặp |
| **Circuit breaker** | Ngắt request khi upstream bất ổn | Mở/ngắt sai, fallback che lỗi |
| **Rate limiting** | Giới hạn tần suất theo principal/tenant | Retry ở nhiều tầng làm lệch quota |
| **Timeout/deadline** | Giới hạn thời gian chờ | Timeout khi backend đã commit |
| **LoadBalancer** | Chọn instance | Retry không tự đảm bảo instance mới |
| **Idempotency** | Ngăn hiệu ứng ghi trùng | Không được framework retry tạo ra |

Không để browser, Gateway, mesh, HTTP SDK và database client mỗi tầng retry ba lần mà không tính **số attempts tổng**.

## 13. HTTP status nào đáng retry?

| HTTP status | GET/read API | POST/write API |
| --- | --- | --- |
| **2xx** | Không cần retry | Không cần retry |
| **400/422** | Input không đúng, sửa request | Không tự retry cùng body |
| **401/403** | Xác thực/quyền sai; retry không giải quyết | Tương tự |
| **404** | Thường không; eventual consistency có chính sách riêng | Không mù quáng gửi lại |
| **409** | Phân tích conflict | Với cùng key nhưng body khác, phải sửa input |
| **412** | Version/precondition không khớp | Không ghi đè mù quáng |
| **429** | Giảm tốc, Retry-After/backoff nếu có | Không auto-retry write nếu không idempotent |
| **500** | Chỉ thử khi có bằng chứng lỗi tạm thời | Có thể lỗi **sau commit** |
| **502** | Thường có thể retry GET với budget | Không chứng minh lệnh ghi chưa áp dụng |
| **503** | Có thể retry GET với backoff/jitter | Không retry nếu chưa có dedup |
| **504** | Có thể retry GET khi còn thời gian | **Ambiguous outcome** với thao tác ghi |

Đây là hướng dẫn thiết kế, không phải bảng default chính xác cho mọi Spring Gateway phiên bản. Không retry liên tục một 500 do bug cố định, và không coi mọi GET an toàn nếu backend lạm dụng GET để thay đổi nghiệp vụ.

## 14. Kiểm thử bằng mock upstream và curl

### 14.1. Chuẩn bị hệ thống test

Giả sử:

- Gateway `http://localhost:8080`.
- Mock catalog-service `http://localhost:8081`.
- Mock payment-service `http://localhost:8082`.
- Route GET với `Retry`, `retries: 2`, `series: SERVER_ERROR`.
- Route POST payment **không có Retry**.

Mock catalog-service cần điều khiển response theo attempt:

~~~text
GET /catalog/products/42
  call #1 -> 502 Bad Gateway
  call #2 -> 200 OK
  call #3 -> không gọi vì #2 đã thành công
~~~

Đừng dựa vào `200 OK` duy nhất để kết luận Retry hoạt động: cần **đếm số request backend thực nhận** và reset counter trước từng ca.

### 14.2. GET: retry thành công

~~~bash
curl -i "http://localhost:8080/api/catalog/products/42"
~~~

Kỳ vọng của test mock:

~~~text
Client -> Gateway: 1 request GET
Gateway -> catalog-service: 2 attempts GET
Client <- Gateway: 200 OK sau attempt thành công
~~~

Đây là expected test outcome, không phải kết quả đã chạy. Nếu thử thật, kiểm tra route ID, upstream counter và log attempt.

### 14.3. GET: hết retry budget

Mock trả 503 liên tục:

~~~bash
curl -i "http://localhost:8080/api/catalog/products/42"
~~~

Với `retries: 2`, tối đa 3 attempts khi lỗi luôn match policy và không bị chặn bởi deadline/cancellation. Response cuối phụ thuộc loại lỗi và error handler thực tế.

### 14.4. POST: không tự thử lại và dùng key khi cần

~~~bash
curl -i \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: demo-payment-001" \
  -d '{"orderId":"ord-42","amount":500000,"currency":"VND"}' \
  "http://localhost:8080/api/payments"
~~~

Cho mock payment-service **ghi thành công** rồi đóng kết nối trước response. Vì POST route không có Retry, Gateway không được tự tạo một attempt thứ hai bằng `Retry GatewayFilter`.

Sau đó client có thể gửi lại **cùng key** vào backend test có dedup. Assert **một payment resource** dù có hai HTTP requests. Không dùng một `demo-payment-001` cố định cho nhiều giao dịch thật.

### 14.5. Ma trận test tích hợp

| Ca | Tình huống | Assertion cần có |
| --- | --- | --- |
| G1 | GET: 502 rồi 200 | 1 request client, 2 attempts upstream, cuối 200 |
| G2 | GET: 503 liên tục | Attempts không vượt retry budget |
| G3 | GET: 400/404 | Không retry nếu policy chỉ gồm 5xx |
| G4 | GET: IOException/TimeoutException | Chỉ retry khi exception nằm trong policy |
| G5 | GET streaming response đã commit rồi ngắt | Không đòi tạo lại response nguyên vẹn |
| W1 | POST route không Retry | Không thêm attempt ở Gateway |
| W2 | Cùng key và payload, hai POST | Một resource duy nhất nếu dedup đúng |
| W3 | Cùng key nhưng payload khác | Backend báo conflict, không tạo lệnh khác |
| W4 | Hai POST cùng key đồng thời | Transaction/unique constraint chặn side effect trùng |
| W5 | PUT với If-Match sai ETag | 412, không ghi đè bừa |
| W6 | DELETE hai lần | Trạng thái cuối đúng, event phụ được dedup |
| O1 | Gateway + client + mesh cùng retry | Đếm tổng attempts và thời gian |
| O2 | RateLimiter và Retry khác thứ tự | Quota được trừ đúng policy |
| O3 | POST lớn vô tình được retry | Theo dõi heap/direct memory và cancellation |
| O4 | Upstream commit rồi timeout | Có cách GET/reconcile kết quả |

Giữ test trên **mock hoặc staging được kiểm soát**, không thử tạo payment thật. Không đưa bearer token, dữ liệu thanh toán, session cookie vào report/log.

## 15. Quan sát retries và chẩn đoán sự cố

### 15.1. Một request client có thể thành ba attempts

Ví dụ log đã làm sạch:

~~~text
traceId: test-abc-123
routeId: catalog-get-with-retry
method: GET
clientRequests: 1
upstreamAttempts: 3
outcomes: [502, 503, 200]
finalStatus: 200
totalLatencyMs: 340
~~~

Nếu chỉ đo finalStatus 200, bạn có thể bỏ qua hai lỗi backend trước đó. Nên có metrics **số attempts**, số retry, status/exception theo attempt, tổng backoff, p95/p99 latency và operation ID nếu có.

### 15.2. Retry và latency

Một attempt mất 400 ms rồi timeout, sau đó attempt khác lại mất 400 ms, có thể đẩy tổng thời gian vượt SLO dù cuối cùng nhận 200. **Retry không miễn phí**: nó chiếm tài nguyên, có thể làm đuôi phân phối latency xấu đi.

Với API ghi, cần đo **tỷ lệ kết quả không rõ**, số operation đang xử lý và reconciliation. Không xem HTTP access log nhiều attempts là nhiều giao dịch hợp lệ.

### 15.3. Những lỗi suy luận thường gặp

| Hiện tượng | Lý do có thể | Cách xử lý |
| --- | --- | --- |
| POST tạo hai đơn sau timeout | Auto-retry không có dedup | Tắt retry hoặc triển khai idempotency key nguyên tử |
| GET gọi backend nhiều lần | Retry đang match 5xx/exception | Kiểm tra counter và policy |
| PUT xong nhưng gửi hai email | Side effect không idempotent | Outbox/dedup event |
| DELETE lần hai trả 404 | Nhầm response với hiệu ứng cuối | Xem trạng thái tài nguyên |
| PATCH increment cộng hai lần | Coi PATCH luôn idempotent | Phân tích operation |
| Retry 500 không giúp | Bug cố định | Sửa upstream, giới hạn status |
| Retry 429 tức thì | Không tuân thủ rate limit/backoff | Dừng, chờ hoặc retry có budget |
| `retries: 3` tạo 4 attempts | Nhầm số retry với tổng attempts | Tính 1 + retries |
| POST lớn làm Gateway thiếu RAM | Cache request body | Không retry upload lớn; giới hạn đồng thời |
| Custom filter chạy nhiều lần | Nằm phía sau Retry | Sửa order/đảm bảo filter an toàn khi lặp |
| 504 nhưng DB đã commit | Timeout chỉ nói response không về | Idempotency + query operation |
| Cùng key vẫn tạo trùng | Dedup không nguyên tử hoặc external PSP lặp | Unique/transaction/provider key/reconciliation |
| GET tạo giao dịch | Sai HTTP semantics | Đổi endpoint thành write method |
| Retry luôn chọn instance lỗi | Không có bảo đảm chọn backend khác | Kiểm tra LB selection/health |

## 16. Bài thực hành: catalog GET và payment POST

**Bối cảnh:** Gateway công khai API đọc sản phẩm và tạo thanh toán. Catalog thỉnh thoảng trả 502; payment service có thể xử lý xong nhưng mất kết nối.

Yêu cầu:

1. Tạo route `GET /api/catalog/**` với Retry giới hạn, backoff và method GET.
2. Tạo route `POST /api/payments` **không** có retry Gateway.
3. Mock catalog trả 502 rồi 200; assert backend nhận hai GET, client chỉ gửi một GET.
4. Mock catalog trả 503 liên tục; assert số attempts tối đa không vượt cấu hình.
5. Mock payment commit rồi mất response; xác minh Gateway không tự phát lại POST.
6. Triển khai Idempotency-Key ở payment-service với unique constraint theo tenant.
7. Test cùng key/cùng body, cùng key/body khác và hai request cùng key đồng thời.
8. Nếu payment dùng provider bên ngoài, kiểm tra provider hỗ trợ idempotency/reconciliation.
9. Thêm circuit breaker, rate limiting và timeout theo policy rồi đo tác động của filter order.
10. Đặt retry budget end-to-end và đo p95/p99 latency, tránh retry storm.
11. Giữ trace/request ID và operation ID, không ghi bí mật vào log.
12. Viết hướng dẫn client khi kết quả thanh toán **không rõ**: truy vấn trạng thái thay vì tự gửi lệnh mới.

### Checklist trước production

- [ ] GET endpoint thật sự chỉ đọc, không giấu thao tác ghi trong query.
- [ ] `retries` là số lần **bổ sung** sau attempt đầu.
- [ ] `methods`, `series`, `statuses`, `exceptions` được kiểm thử trên đúng version.
- [ ] Backoff/jitter/deadline phù hợp SLO và giới hạn concurrency.
- [ ] POST/PATCH không auto-retry nếu chưa có idempotency contract.
- [ ] PUT/DELETE bảo toàn semantics, kiểm soát side effect phụ và version.
- [ ] Key cho một operation ổn định xuyên attempts; không dùng key mới cho retry.
- [ ] Dedup thực hiện nguyên tử, có fingerprint, TTL, xử lý trạng thái đang chạy.
- [ ] Các hiệu ứng ngoài DB (Kafka, email, PSP) có cơ chế khử trùng lặp/khôi phục.
- [ ] Body cache không gây memory pressure; upload lớn dùng thiết kế riêng.
- [ ] Đã kiểm tra filter order, rate limiter, breaker, LoadBalancer và response commit.
- [ ] Không tự retry lỗi 400/401/403/409/412 hoặc 429 ngay lập tức.
- [ ] Có metric upstream attempts, final result, latency và ambiguous outcomes.
- [ ] Có API tra cứu kết quả lệnh sau timeout và quy trình reconcile.
- [ ] Client, Gateway, mesh và SDK có một retry budget được quản lý.

## 17. Tổng kết

**GET** là safe và idempotent theo HTTP, vì vậy thường phù hợp nhất với retry có giới hạn sau lỗi tạm thời. **PUT và DELETE** idempotent về **hiệu ứng dự định**, nhưng vẫn cần bảo vệ các side effect khác. **POST và PATCH** không mặc nhiên idempotent: timeout, 502 hoặc 504 không bảo đảm backend chưa commit.

Trong Spring Cloud Gateway Server WebFlux, `Retry GatewayFilter` hỗ trợ method, status/series, exception và backoff, với mặc định đáng chú ý là retry **GET** khi filter được bật. Các filter phía sau Retry có thể chạy lại; request có body có thể cần cache và tiêu tốn RAM.

Với thao tác ghi quan trọng như thanh toán và tạo đơn, tính đúng đắn phải dựa vào **idempotency key, unique constraint, transaction, bảo vệ side effect và reconciliation**. Không dùng cấu hình retry để thay cho những bảo đảm đó. Kết hợp retry budget, timeout, circuit breaker, rate limiting, TLS và quan sát attempts mới giúp Gateway tăng khả dụng mà không làm nhân đôi dữ liệu.

### Tài liệu tham khảo

- [RFC 9110 — Safe và Idempotent Methods](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.2).
- [Spring Cloud Gateway Server WebFlux — Retry GatewayFilter Factory](https://docs.spring.io/spring-cloud-gateway/reference/spring-cloud-gateway-server-webflux/gatewayfilter-factories/retry-factory.html).
- [Spring Cloud Gateway 4.x — GatewayFilter Factories](https://docs.spring.io/spring-cloud-gateway/docs/current/reference/html/).
- [RFC 5789 — PATCH Method for HTTP](https://www.rfc-editor.org/rfc/rfc5789).
