# Gọi dịch vụ bên ngoài

## 1. Gọi dịch vụ bên ngoài trong tích hợp ứng dụng

Một ứng dụng hiếm khi hoạt động độc lập. Nó thường cần trao đổi dữ liệu với hệ thống thanh toán, dịch vụ định danh, nền tảng vận chuyển, CRM, ERP, hệ thống thông báo, dịch vụ dữ liệu hoặc một ứng dụng do đối tác vận hành. Việc gọi các hệ thống đó tạo nên ranh giới tích hợp giữa ứng dụng hiện tại và môi trường bên ngoài.

Trong một ngôn ngữ miền chuyên biệt (Domain-Specific Language — DSL) dành cho tích hợp ứng dụng, **gọi dịch vụ bên ngoài (external service invocation)** là khả năng mô tả và thực hiện một yêu cầu tới hệ thống khác, nhận phản hồi hoặc theo dõi kết quả bất đồng bộ, rồi chuyển dữ liệu và trạng thái đó vào quy trình nội bộ.

Ví dụ một DSL tích hợp đơn hàng:

~~~text
service payment_gateway {
    protocol = http
    base_url = "https://payments.example"
    authentication = oauth2("payment-client")
}

task "authorize-payment" {
    call payment_gateway.post(
        "/v1/authorizations",
        body = {
            orderId = order.id,
            amount = order.total.amount,
            currency = order.total.currency
        }
    )
    timeout = 3s
}
~~~

Ví dụ chỉ minh họa ý tưởng cú pháp. Một DSL thực tế cần xác định rõ cách phân giải endpoint, xác thực, serialize request, kiểm tra response, xử lý lỗi, timeout, retry, quyền truy cập và cách ghi nhận kết quả.

Gọi dịch vụ bên ngoài không chỉ là gửi một HTTP request. Đây là một thao tác qua ranh giới tin cậy và độ tin cậy khác nhau. Hệ thống gọi không kiểm soát hoàn toàn trạng thái, hiệu năng, dữ liệu hoặc lịch phát hành của hệ thống được gọi. Vì vậy, DSL cần cung cấp một hợp đồng tích hợp có thể kiểm tra, quan sát và vận hành.

## 2. Vì sao cần mô hình hóa lời gọi dịch vụ

Nếu mọi lời gọi được viết rải rác trong code, các quy tắc endpoint, authentication, timeout và error handling dễ bị lặp lại hoặc không nhất quán. Một DSL tích hợp có thể gom những quyết định này thành khai báo có cấu trúc.

Các lợi ích chính:

- Mô tả dịch vụ, operation và dữ liệu trao đổi bằng khái niệm gần với nghiệp vụ.
- Tách logic quy trình khỏi chi tiết HTTP client hoặc SDK.
- Tái sử dụng cấu hình endpoint, authentication và connection policy.
- Kiểm tra request và response theo schema.
- Chuẩn hóa timeout, retry, circuit breaker và rate limit.
- Quản lý version API và khả năng tương thích.
- Kiểm soát quyền truy cập tới dịch vụ và dữ liệu.
- Theo dõi lời gọi qua log, metric và distributed trace.
- Hỗ trợ mock, sandbox và contract testing.

Ví dụ, nhiều workflow có thể cùng dùng dịch vụ customer. Thay vì mỗi workflow tự tạo URL, header và cách xử lý lỗi, DSL có thể tham chiếu một service definition đã được quản lý tập trung.

### 2.1. Tách ý định nghiệp vụ khỏi giao thức

Một quy trình có thể cần kiểm tra trạng thái giao hàng. Ý định nghiệp vụ là lấy trạng thái của shipment theo mã vận đơn. Cách triển khai có thể là REST, GraphQL, gRPC hoặc message query. Nếu DSL gắn trực tiếp toàn bộ logic vào một thư viện HTTP, việc thay giao thức sẽ làm workflow phụ thuộc implementation.

Có thể biểu diễn một operation ở mức miền:

~~~text
shipment = shipping.lookup(tracking_number)
~~~

Adapter phía dưới chịu trách nhiệm chuyển operation đó thành request phù hợp với hệ thống đối tác.

### 2.2. Không che giấu semantics quan trọng

Trừu tượng hóa không được làm mất thông tin về timeout, consistency, idempotency hoặc lỗi. DSL nên cho thấy các thuộc tính ảnh hưởng đến hành vi và chi phí vận hành, ngay cả khi che giấu chi tiết socket hoặc HTTP header.

## 3. Các kiểu giao tiếp với dịch vụ bên ngoài

Không phải mọi hệ thống đều cung cấp cùng một giao thức. DSL cần có mô hình đủ linh hoạt để tích hợp nhiều kiểu giao tiếp.

### 3.1. REST và HTTP API

REST API thường trao đổi resource hoặc operation qua HTTP method và URL:

- GET để đọc resource.
- POST để tạo resource hoặc thực hiện operation.
- PUT để thay thế biểu diễn resource theo contract.
- PATCH để cập nhật một phần.
- DELETE để yêu cầu xóa hoặc hủy resource.

HTTP status code, header và body cùng tạo nên phản hồi. Client cần tuân theo semantics của API cụ thể, không chỉ dựa trên method.

### 3.2. GraphQL

GraphQL thường cung cấp một endpoint, trong đó client gửi query hoặc mutation mô tả dữ liệu cần lấy hoặc thay đổi. Mapping cần xử lý schema, variable, selection set, lỗi ở cấp field và trường hợp HTTP response thành công nhưng GraphQL payload có errors.

### 3.3. gRPC

gRPC sử dụng service contract và message type, thường được định nghĩa bằng Protocol Buffers. Nó hỗ trợ unary call và streaming. Client cần hiểu deadline, status code, metadata, channel lifecycle và compatibility của protobuf schema.

### 3.4. SOAP và XML service

Một số hệ thống doanh nghiệp vẫn sử dụng SOAP, WSDL và XML schema. Adapter cần xử lý namespace, envelope, fault, certificate và quy tắc serialization riêng.

### 3.5. Message broker

Thay vì gọi trực tiếp và chờ response, ứng dụng có thể gửi message tới queue hoặc topic. Producer và consumer giao tiếp gián tiếp qua broker. Cần định nghĩa delivery semantics, message key, schema, acknowledgment, retry và dead-letter handling.

### 3.6. Webhook

Webhook là lời gọi ngược từ dịch vụ bên ngoài vào endpoint của ứng dụng khi có event. Ứng dụng cần xác minh chữ ký, kiểm tra timestamp, deduplicate event và phản hồi nhanh trước khi xử lý công việc dài.

### 3.7. File transfer

Một số tích hợp dùng SFTP, object storage hoặc trao đổi file theo lịch. DSL có thể mô tả nơi nhận, format, checksum, encryption, naming convention và trạng thái import/export.

### 3.8. Database link hoặc connector

Một số hệ thống tích hợp qua connector hoặc truy vấn database. Đây là ranh giới đặc biệt nhạy cảm vì client có thể truy cập dữ liệu trực tiếp. Cần giới hạn quyền, schema và transaction boundary.

### 3.9. Chọn giao thức

| Nhu cầu | Kiểu tích hợp thường phù hợp |
|---|---|
| Đọc hoặc thao tác resource qua HTTP | REST |
| Client chọn cấu trúc dữ liệu truy vấn | GraphQL |
| Giao tiếp service-to-service có contract chặt | gRPC |
| Hệ thống doanh nghiệp dùng XML contract | SOAP |
| Xử lý tách rời và bất đồng bộ | Message broker |
| Nhận thông báo khi event xảy ra | Webhook |
| Trao đổi batch hoặc file lớn | File transfer |

Lựa chọn cuối cùng còn phụ thuộc năng lực của đối tác, yêu cầu latency, throughput, bảo mật và vận hành.

## 4. Khai báo service trong DSL

Một service definition mô tả cách ứng dụng kết nối với một hệ thống bên ngoài.

### 4.1. Thông tin service

Các thuộc tính thường gặp:

- Tên logic của service.
- Protocol hoặc transport.
- Base endpoint.
- API version.
- Authentication scheme.
- Request/response schema.
- Timeout mặc định.
- Connection pool.
- Retry và circuit breaker policy.
- TLS và certificate policy.
- Rate limit.
- Environment binding.

### 4.2. Service declaration minh họa

~~~text
service "customer-directory" {
    protocol = http
    base_url = env("CUSTOMER_API_URL")
    api_version = "v2"
    authentication = workload_identity("customer-reader")
    timeout = 2s
    tls = required
}
~~~

Base URL lấy từ cấu hình môi trường hoặc service discovery. Không nên nhúng credential vào URL hoặc source DSL.

### 4.3. Service alias

Workflow nên gọi service bằng tên logic thay vì lặp lại host:

~~~text
customer = customer_directory.get_customer(customer_id)
~~~

Alias cho phép đổi endpoint giữa development, staging và production mà không sửa logic nghiệp vụ.

### 4.4. Service catalog

Một hệ thống lớn có thể có catalog định nghĩa service, owner, purpose, operations, data classification, SLA và contact vận hành. DSL có thể tham chiếu catalog để compiler kiểm tra tên và contract.

### 4.5. Environment binding

~~~text
environment "development" {
    bind customer_directory -> "https://customer-dev.example"
}

environment "production" {
    bind customer_directory -> "https://customer.example"
}
~~~

Binding phải được kiểm soát để một workflow chạy ở production không vô tình gọi endpoint thử nghiệm hoặc ngược lại.

### 4.6. Service ownership

Mỗi service definition nên có owner hoặc nhóm chịu trách nhiệm. Khi endpoint hoặc contract thay đổi, nhóm tích hợp cần biết ai có quyền phê duyệt và ai nhận cảnh báo.

## 5. Operation contract

Service definition cho biết kết nối tới đâu; operation contract mô tả một hành động cụ thể.

### 5.1. Operation name

Tên operation nên phản ánh ý nghĩa miền, ví dụ lookupCustomer, authorizePayment hoặc createShipment. Tên không nên chỉ là một HTTP method chung nếu có thể cung cấp tên nghiệp vụ rõ hơn.

### 5.2. Input schema

Input schema định nghĩa field, type, required/optional, constraint và ý nghĩa của từng giá trị.

### 5.3. Output schema

Output schema định nghĩa response thành công và các variant có thể trả về. Không nên coi mọi response là một object duy nhất nếu API có nhiều trạng thái.

### 5.4. Error contract

Operation nên mô tả error code, nhóm lỗi, retryability và hành động phù hợp. Message tự do không phải hợp đồng ổn định.

### 5.5. Side-effect declaration

Operation đọc dữ liệu thường có rủi ro khác operation tạo giao dịch hoặc xóa resource. DSL có thể đánh dấu read-only, idempotent, mutating hoặc irreversible để áp dụng policy phù hợp.

### 5.6. Example contract

~~~text
operation "authorize-payment" {
    service = payment_gateway
    method = POST
    path = "/v1/authorizations"

    input {
        order_id: String required
        amount: Money required
        payment_method: PaymentMethod required
    }

    output PaymentAuthorization

    errors {
        INSUFFICIENT_FUNDS
        INVALID_PAYMENT_METHOD
        RATE_LIMITED retryable
        TEMPORARY_UNAVAILABLE retryable
    }
}
~~~

Đây là cú pháp minh họa. Contract nên được kiểm tra với OpenAPI, protobuf hoặc schema chính thức của đối tác nếu có.

## 6. Xây dựng request

Một request thường gồm endpoint, method, path parameter, query parameter, header và body.

### 6.1. Path parameter

Path parameter định danh resource:

~~~text
GET /v2/customers/{customerId}
~~~

Giá trị phải được encode theo quy tắc URI. Không nối trực tiếp dữ liệu không tin cậy vào URL.

### 6.2. Query parameter

Query parameter thường dùng cho filter, pagination, sort hoặc projection:

~~~text
GET /v2/orders?status=PAID&limit=50
~~~

DSL cần xử lý encoding, repeated key và quy tắc khi giá trị null hoặc collection rỗng.

### 6.3. Header

Header có thể chứa content type, accept, correlation ID, idempotency key, conditional request và metadata theo contract. Không đưa secret vào header tùy tiện hoặc log toàn bộ header.

### 6.4. Request body

Body có thể là JSON, XML, protobuf hoặc binary. Serializer phải tuân schema và content type của API.

### 6.5. Request composition

Request nên được tạo từ typed input hoặc DTO. Việc chuyển trực tiếp object nội bộ thành payload có thể vô tình gửi field không được phép.

### 6.6. Validation trước khi gửi

Kiểm tra required field, range, format, enum và invariant trước khi gọi mạng. Điều này tránh gửi request chắc chắn bị từ chối và giúp lỗi được báo ngay tại nơi cấu hình.

### 6.7. Request size

Giới hạn kích thước body, số phần tử và độ sâu nested object. Payload quá lớn có thể làm tăng memory, latency hoặc bị gateway từ chối.

## 7. Endpoint, DNS và service discovery

Endpoint có thể cố định hoặc được phân giải động.

### 7.1. Static endpoint

Endpoint tĩnh phù hợp hệ thống nhỏ hoặc đối tác có địa chỉ ổn định. Nên quản lý trong cấu hình môi trường, không rải URL trong nhiều workflow.

### 7.2. Service discovery

Trong môi trường cloud hoặc microservice, địa chỉ instance có thể thay đổi. Service discovery tìm endpoint hiện hành qua registry hoặc nền tảng điều phối.

### 7.3. DNS

DNS resolve hostname thành địa chỉ IP. Cần xem xét TTL, cache, split-horizon DNS và hành vi khi record thay đổi.

### 7.4. Load balancing

Request có thể được phân phối qua load balancer. Client cần hiểu connection reuse, health check, retry và session affinity nếu service yêu cầu.

### 7.5. Endpoint allowlist

Với endpoint do người dùng cấu hình, cần allowlist host hoặc domain phù hợp. Không cho phép DSL tùy ý gọi địa chỉ nội bộ hoặc metadata endpoint vì có thể tạo SSRF.

### 7.6. Proxy

Proxy có thể được dùng cho egress control, audit hoặc kết nối qua mạng riêng. Cần cấu hình TLS và certificate validation đúng, đồng thời tránh để proxy trở thành nơi ghi lại secret.

### 7.7. Multi-region

Endpoint theo region có thể giúp giảm latency và tăng availability. Cần xác định dữ liệu có được phép chuyển vùng hay không, cách chọn region và hành vi failover.

## 8. Authentication và authorization

Gọi dịch vụ bên ngoài cần chứng minh danh tính của caller và được cấp quyền thực hiện operation.

### 8.1. API key

API key là credential đơn giản, thường được gửi trong header. Cần giới hạn scope, rotation, expiry và quyền truy cập. Không nhúng key vào source hoặc query string nếu có thể tránh.

### 8.2. OAuth 2.0

OAuth 2.0 cho phép client lấy access token theo grant phù hợp. Service-to-service thường dùng client credentials hoặc workload federation tùy nền tảng. Token cần audience, scope và expiry đúng.

### 8.3. OpenID Connect

OIDC bổ sung lớp xác thực danh tính trên OAuth 2.0. ID token mô tả danh tính người dùng/client trong một ngữ cảnh; access token dùng để truy cập resource server. Không dùng nhầm ID token thay access token.

### 8.4. Mutual TLS

mTLS yêu cầu cả client và server xác thực bằng certificate. Nó hữu ích cho service-to-service trong mạng có kiểm soát. Cần quản lý cấp phát, renewal, trust chain và revocation.

### 8.5. Workload identity

Workload identity cho phép ứng dụng dùng danh tính do nền tảng cấp thay vì lưu access key dài hạn. DSL có thể tham chiếu identity alias nhưng runtime phải xác minh identity thực.

### 8.6. Secret reference

Nếu cần API key hoặc client secret, DSL chỉ nên giữ secret reference. Runtime resolve từ secret manager theo workload identity và quyền tối thiểu.

### 8.7. Token refresh

Access token có thời hạn. Client cần refresh hoặc lấy token mới theo protocol. Nếu nhiều request cùng phát hiện token hết hạn, nên phối hợp refresh để tránh token refresh storm.

### 8.8. Scope và audience

Token cần chỉ có scope và audience cần thiết. Token có quyền rộng hoặc audience sai có thể bị lạm dụng ở dịch vụ khác.

### 8.9. Authorization theo operation

Có credential hợp lệ không đồng nghĩa được phép gọi mọi operation. Quyền nên giới hạn theo service, resource, tenant và hành động.

## 9. TLS và bảo vệ kênh truyền

Request và response có thể chứa dữ liệu cá nhân, credential hoặc thông tin nghiệp vụ.

### 9.1. TLS

TLS mã hóa dữ liệu trên đường truyền và xác thực server theo certificate chain. Client cần bật certificate validation và hostname verification.

### 9.2. Certificate trust

Không tắt kiểm tra certificate chỉ để khắc phục lỗi môi trường. Nếu dùng private CA, cần cấu hình trust store đúng và quản lý vòng đời certificate.

### 9.3. mTLS certificate lifecycle

Client certificate cần được cấp, phân phối, gia hạn và thu hồi. Certificate hết hạn có thể làm toàn bộ lời gọi thất bại.

### 9.4. Data minimization

Chỉ gửi field cần thiết cho operation. Không gửi toàn bộ customer profile nếu dịch vụ chỉ cần customer ID và country code.

### 9.5. Sensitive payload

Không log request body, response body hoặc header nhạy cảm mặc định. Dùng redaction theo schema và sensitivity label.

### 9.6. Encryption không thay authorization

TLS bảo vệ kênh truyền nhưng không chứng minh caller được phép truy cập dữ liệu. Authentication và authorization vẫn phải được kiểm tra.

## 10. Timeout và deadline

Network call có thể bị chậm hoặc không trả phản hồi. Timeout giới hạn thời gian chờ để tài nguyên không bị giữ vô hạn.

### 10.1. Connection timeout

Giới hạn thời gian thiết lập kết nối tới endpoint.

### 10.2. Read hoặc response timeout

Giới hạn thời gian chờ dữ liệu phản hồi sau khi request được gửi.

### 10.3. Overall request timeout

Giới hạn toàn bộ lời gọi, có thể bao gồm resolve, connect, write và read tùy client.

### 10.4. Workflow deadline

Deadline của workflow bao gồm cả thời gian chờ, retry và xử lý tiếp theo. Không nên đặt timeout từng request độc lập mà bỏ qua deadline tổng.

### 10.5. Timeout propagation

Nếu service A gọi B rồi B gọi C, deadline còn lại nên được truyền xuống. Nếu mỗi tầng tự đặt timeout dài hơn caller, request có thể tiếp tục chạy sau khi caller đã bỏ cuộc.

### 10.6. Timeout không đồng nghĩa hủy side effect

Client timeout chỉ nói rằng client ngừng chờ. Server có thể vẫn đang xử lý hoặc đã commit. Với operation tạo giao dịch, cần idempotency key và status lookup.

## 11. Xử lý response

Response có thể chứa dữ liệu thành công, lỗi, metadata hoặc trạng thái chưa hoàn tất.

### 11.1. HTTP status

Client cần phân biệt status thành công, redirect, client error và server error. Tuy nhiên, status code cần được diễn giải theo API contract; một số API dùng status thành công nhưng body chứa business rejection.

### 11.2. Content type

Kiểm tra Content-Type trước khi parse body. Không giả định mọi response là JSON.

### 11.3. Schema validation

Parse thành DTO hoặc typed response rồi kiểm tra schema. Nếu response thiếu field bắt buộc hoặc chứa type sai, đây là lỗi contract/data.

### 11.4. Empty response

Một số operation hợp lệ trả 204 No Content hoặc body rỗng. DSL cần hỗ trợ output void hoặc optional response.

### 11.5. Partial response

API có thể trả một phần dữ liệu hoặc một số field phụ thuộc quyền. Không tự động coi field thiếu là null hoặc giá trị mặc định.

### 11.6. Response metadata

Header có thể chứa pagination cursor, rate limit, request ID, retry-after hoặc version. Adapter cần giữ lại metadata cần thiết cho workflow.

### 11.7. Large response

Với response lớn, streaming parser giúp giảm memory. Cần giới hạn kích thước và đóng response body để giải phóng connection.

## 12. Error mapping

Lỗi từ hệ thống ngoài nên được chuyển thành mô hình lỗi nội bộ có cấu trúc.

### 12.1. Transport error

Ví dụ DNS failure, connection refused, TLS handshake failure hoặc socket reset. Chúng thường xảy ra trước khi nhận được business response.

### 12.2. Protocol error

Ví dụ status không mong đợi, malformed response, content type sai hoặc schema mismatch.

### 12.3. Authentication error

Credential hết hạn, sai audience, certificate không hợp lệ hoặc token bị từ chối.

### 12.4. Authorization error

Caller đã xác thực nhưng không có quyền thực hiện operation.

### 12.5. Business error

Ví dụ insufficient funds, inventory unavailable hoặc account suspended. Đây là kết quả nghiệp vụ cần được biểu diễn thành variant rõ ràng.

### 12.6. Error normalization

Một adapter có thể chuẩn hóa lỗi:

~~~text
ExternalError {
    category
    code
    retryable
    retry_after
    correlation_id
    safe_message
}
~~~

Không nên chỉ chuyển mọi lỗi thành một exception chung vì workflow sẽ không thể quyết định retry, fallback hay compensation đúng cách.

### 12.7. Preserve cause

Giữ nguyên nguyên nhân kỹ thuật để điều tra nhưng không đưa secret hoặc payload nhạy cảm vào message công khai. Có thể lưu exception cause trong log nội bộ được bảo vệ.

### 12.8. Unknown outcome

Nếu request đã được gửi nhưng client không biết server đã xử lý chưa, hãy biểu diễn trạng thái unknown. Đừng biến unknown thành failed một cách tùy tiện.

## 13. Retry và resilience khi gọi dịch vụ

External dependency có thể tạm thời không sẵn sàng. Resilience policy giúp giới hạn tác động lên ứng dụng.

### 13.1. Retry có điều kiện

Chỉ retry lỗi có khả năng phục hồi. Không retry validation, permission hoặc business rejection trừ khi contract chỉ ra lý do cụ thể.

### 13.2. Backoff và jitter

Exponential backoff tăng thời gian chờ giữa các attempt. Jitter phân tán thời điểm retry để giảm đồng bộ tải.

### 13.3. Idempotency

Operation có side effect cần idempotency key hoặc cơ chế dedup. Không retry một lệnh tạo thanh toán hoặc tạo đơn hàng nếu không có cách tránh giao dịch trùng.

### 13.4. Circuit breaker

Circuit breaker tạm ngừng gọi dependency khi lỗi vượt ngưỡng:

- Closed: cho phép request.
- Open: chặn nhanh request trong thời gian cooldown.
- Half-open: cho phép một số probe để xác nhận dependency phục hồi.

### 13.5. Bulkhead

Giới hạn worker, connection hoặc concurrency theo dependency để một dịch vụ chậm không chiếm hết tài nguyên ứng dụng.

### 13.6. Rate limiting

Giới hạn tốc độ gọi theo client, tenant hoặc operation. Tôn trọng quota và Retry-After của đối tác.

### 13.7. Fallback

Fallback có thể dùng cache, dữ liệu dự phòng hoặc nhánh nghiệp vụ khác. Cần ghi rõ dữ liệu có thể stale và khi nào fallback được phép.

### 13.8. Retry budget

Giới hạn tổng lượng retry để tránh khuếch đại tải khi dependency suy giảm. Budget có thể được quản lý ở cấp service hoặc workflow.

### 13.9. Không che giấu lỗi

Fallback thành công không nên làm mất dấu việc dependency chính đang lỗi. Ghi metric và trạng thái degradation để operator biết hệ thống đang chạy ở chế độ suy giảm.

## 14. Idempotency và side effect

Lời gọi dịch vụ có thể đọc dữ liệu hoặc tạo thay đổi không thể lặp tùy tiện.

### 14.1. Read operation

GET thường được thiết kế để đọc, nhưng vẫn có thể tiêu tốn quota hoặc kích hoạt audit. Retry thường an toàn hơn nhưng vẫn phải tuân rate limit và deadline.

### 14.2. Mutating operation

POST, payment, reservation hoặc create operation có thể tạo side effect. Cần idempotency key ổn định theo logical operation.

### 14.3. Idempotency key lifecycle

Key cần được tạo trước attempt đầu tiên và giữ nguyên qua retry. Server cần lưu kết quả hoặc trạng thái theo key trong một khoảng retention đủ dài.

### 14.4. Operation status lookup

Nếu response bị mất, client có thể query operation ID để xác định đã hoàn tất, đang xử lý hay chưa được tiếp nhận.

### 14.5. Exactly-once effect

Không nên hứa rằng network call chỉ được gửi đúng một lần trong mọi tình huống. Thường cần delivery at-least-once kết hợp idempotency, deduplication và reconciliation để tạo hiệu ứng nghiệp vụ tương đương một lần.

### 14.6. Compensation

Nếu nhiều service đã tạo side effect và một bước sau thất bại, workflow có thể cần compensation như cancel reservation hoặc refund. Compensation là operation mới, cũng cần timeout, idempotency và audit.

## 15. Đồng bộ và bất đồng bộ

Không phải lời gọi nào cũng nên giữ request đang chạy cho đến khi có kết quả cuối.

### 15.1. Synchronous call

Caller gửi request và chờ response trong cùng luồng xử lý. Phù hợp khi dependency phản hồi nhanh và kết quả cần ngay.

### 15.2. Asynchronous request

Caller gửi yêu cầu, nhận operation ID hoặc acknowledgment rồi tiếp tục công việc khác. Kết quả được lấy sau hoặc gửi về qua callback.

### 15.3. Polling

Client định kỳ truy vấn operation status. Cần backoff, timeout tổng và giới hạn số lần poll.

### 15.4. Callback

Service ngoài gọi callback URL khi operation hoàn tất. Endpoint cần xác thực nguồn gọi, correlation ID, deduplication và kiểm soát replay.

### 15.5. Webhook

Webhook thường là event push. Receiver nên xác minh chữ ký hoặc cơ chế xác thực tương đương, kiểm tra timestamp, lưu event ID và trả acknowledgment nhanh.

### 15.6. Queue-based integration

Producer gửi message vào broker, consumer xử lý sau. Đây là cách tách rời thời gian sống của caller và provider nhưng đòi hỏi quản lý duplicate, ordering, retry và DLQ.

### 15.7. Chọn sync hay async

| Tiêu chí | Đồng bộ | Bất đồng bộ |
|---|---|---|
| Kết quả cần ngay | Phù hợp | Cần chờ hoặc truy vấn |
| Thời gian xử lý dài | Dễ timeout | Phù hợp hơn |
| Coupling thời gian | Cao | Thấp hơn |
| Theo dõi trạng thái | Qua response | Cần operation ID/event |
| Độ phức tạp vận hành | Thường thấp hơn | Cần state và reconciliation |

## 16. Pagination, filtering và batching

API thường giới hạn số record trả về hoặc số thao tác trong một request.

### 16.1. Offset pagination

Client truyền offset và limit. Cách này dễ hiểu nhưng có thể bỏ sót hoặc lặp record nếu dữ liệu thay đổi giữa các trang.

### 16.2. Cursor pagination

Server trả cursor để lấy trang tiếp theo. Cursor thường ổn định hơn với tập dữ liệu thay đổi nhưng cần được giữ nguyên và xử lý theo contract.

### 16.3. Page termination

Client cần biết khi nào dừng: không còn next cursor, page rỗng, total count đạt tới hoặc server báo end-of-stream.

### 16.4. Filtering và sorting

DSL nên biểu diễn filter bằng cấu trúc có kiểu thay vì nối chuỗi query tùy ý. Cần kiểm tra field được phép filter/sort để tránh lộ dữ liệu hoặc query tốn kém.

### 16.5. Batch API

Batch giảm số network round trip nhưng cần xử lý partial success, giới hạn kích thước và kết quả từng item.

### 16.6. Concurrency khi pagination

Không nên lấy nhiều trang song song nếu cursor hoặc thứ tự phụ thuộc trang trước. Với partition độc lập, có thể chạy song song theo contract.

## 17. Streaming và long-lived connection

Một số giao thức giữ kết nối lâu để truyền nhiều message hoặc dữ liệu liên tục.

### 17.1. Server-Sent Events

SSE cho phép server đẩy event một chiều tới client qua HTTP. Client cần xử lý reconnect, event ID và duplicate.

### 17.2. WebSocket

WebSocket hỗ trợ giao tiếp hai chiều trên kết nối lâu dài. Cần heartbeat, reconnect, authentication renewal và backpressure.

### 17.3. gRPC streaming

gRPC hỗ trợ client-streaming, server-streaming và bidirectional streaming. Cần xác định flow control, cancellation và trạng thái kết thúc stream.

### 17.4. Backpressure

Consumer chậm không nên khiến buffer tăng vô hạn. Cần giới hạn queue, pause/resume hoặc từ chối dữ liệu theo semantics.

### 17.5. Reconnection

Reconnect không có nghĩa message trước đó chưa được xử lý. Cần sequence number, cursor hoặc deduplication để phục hồi đúng.

## 18. API contract và schema

Tích hợp bền vững cần contract rõ giữa provider và consumer.

### 18.1. OpenAPI

OpenAPI mô tả HTTP path, method, parameter, request/response schema, authentication và response code. DSL có thể import hoặc tham chiếu OpenAPI để kiểm tra operation.

### 18.2. Protocol Buffers

Protobuf mô tả message và service cho gRPC. Cần tuân quy tắc field number, reserved field và compatibility khi thay đổi schema.

### 18.3. JSON Schema

JSON Schema mô tả cấu trúc và constraint của JSON. Cần thống nhất dialect và cách xử lý format, reference và unknown property.

### 18.4. WSDL và XML Schema

SOAP contract có thể được mô tả bằng WSDL và XSD. Adapter cần giữ namespace và fault semantics.

### 18.5. Contract-first và code-first

- Contract-first: định nghĩa schema/API trước rồi sinh code hoặc adapter.
- Code-first: định nghĩa API trong code rồi sinh contract.

Contract-first giúp nhiều bên review schema độc lập. Code-first có thể thuận tiện trong một codebase nhưng cần kiểm soát contract được phát hành.

### 18.6. Schema compatibility

Thêm field optional thường dễ tương thích hơn thêm field required hoặc đổi type. Tuy nhiên, compatibility thực tế phụ thuộc reader/writer behavior và strictness của validator.

### 18.7. Consumer-driven contract

Consumer-driven contract ghi lại phần API mà consumer thực sự sử dụng. Provider có thể chạy kiểm tra để phát hiện thay đổi làm hỏng consumer trước khi phát hành.

### 18.8. Contract drift

Nếu tài liệu, generated client và server implementation không đồng bộ, integration có thể lỗi dù code client không thay đổi. Nên quản lý version và kiểm tra contract trong pipeline phát triển.

## 19. Adapter và kiến trúc tích hợp

Không nên để domain logic phụ thuộc trực tiếp vào một HTTP client hoặc SDK cụ thể.

### 19.1. Port và adapter

Application hoặc domain layer định nghĩa interface mô tả nhu cầu:

~~~text
PaymentPort.authorize(command) -> AuthorizationResult
~~~

Adapter bên ngoài triển khai interface đó bằng REST, gRPC hoặc SDK của nhà cung cấp.

### 19.2. Hexagonal architecture

Domain ở trung tâm; inbound và outbound adapter kết nối domain với API, database, queue và UI. Lời gọi bên ngoài đi qua outbound port.

~~~text
Workflow / Application
         |
         v
   Payment Port
         |
         v
   REST Adapter
         |
         v
   Payment Provider
~~~

### 19.3. Anti-corruption layer

Adapter có thể chuyển mô hình và thuật ngữ của đối tác thành khái niệm miền nội bộ. Điều này ngăn thay đổi hoặc sự phức tạp của hệ thống ngoài lan vào domain model.

### 19.4. Vendor-specific behavior

Nếu provider A dùng trạng thái AUTHORIZED còn provider B dùng APPROVED, adapter chuẩn hóa thành trạng thái nội bộ thống nhất nhưng cần giữ metadata gốc khi cần điều tra.

### 19.5. Adapter testing

Domain logic có thể kiểm thử với fake port. Adapter được kiểm thử riêng với contract hoặc sandbox của provider.

## 20. Mapping dữ liệu ở ranh giới dịch vụ

Mỗi dịch vụ có thể dùng schema và semantics riêng.

### 20.1. Request mapping

Chuyển domain command thành request DTO, chỉ gửi field được contract cho phép.

### 20.2. Response mapping

Chuyển response DTO thành domain result hoặc domain event. Không đưa raw provider object vào toàn bộ ứng dụng nếu không cần.

### 20.3. Unit và currency

Đối tác có thể dùng minor units (ví dụ cents) trong khi domain dùng Decimal. Mapping phải xác định scale, currency exponent và rounding policy.

### 20.4. Time mapping

API có thể trả UTC timestamp, epoch milliseconds hoặc local time. Chuyển đổi phải rõ timezone và precision.

### 20.5. Enum mapping

Giá trị provider chưa biết có thể được giữ thành Unknown variant hoặc đưa vào error channel. Không tự map về trạng thái mặc định nếu điều đó có thể thay đổi ý nghĩa nghiệp vụ.

### 20.6. Correlation metadata

Giữ request ID, operation ID và provider reference để liên kết request, response, webhook và log.

## 21. Bảo mật khi gọi dịch vụ bên ngoài

External call là ranh giới có thể gửi dữ liệu ra ngoài hoặc nhận payload không tin cậy.

### 21.1. Least privilege

Credential chỉ nên có quyền cần cho operation và resource cụ thể. Một integration chỉ đọc trạng thái giao hàng không cần quyền tạo hoặc hủy shipment.

### 21.2. Secret management

Lưu API key, client secret và certificate private key trong secret manager hoặc cơ chế bảo vệ tương đương. DSL giữ reference, runtime resolve theo identity.

### 21.3. SSRF

Nếu người dùng có thể khai báo URL tùy ý, họ có thể khiến server gọi localhost, private network hoặc metadata endpoint. Dùng allowlist, validate DNS/IP sau resolve và chặn địa chỉ không được phép.

### 21.4. Redirect policy

Không tự động chuyển credential sang host khác khi theo redirect. Kiểm tra redirect target và giới hạn số lần redirect.

### 21.5. Request signing

Một số API yêu cầu ký request. Canonicalization của method, path, timestamp và body phải theo đúng contract. Không tự xây signature format nếu provider đã cung cấp SDK hoặc spec.

### 21.6. Replay protection

Webhook hoặc signed request cần timestamp, nonce hoặc event ID để giảm replay. Receiver cần lưu dấu đã xử lý trong cửa sổ phù hợp.

### 21.7. Input validation

Response từ bên ngoài vẫn là dữ liệu không tin cậy. Validate schema, kích thước, encoding và nội dung trước khi sử dụng.

### 21.8. XML external entity

Khi parse XML từ provider, tắt các tính năng external entity và external DTD không cần thiết để tránh XXE và truy cập tài nguyên ngoài ý muốn.

### 21.9. Logging và privacy

Không log token, password, payment data hoặc toàn bộ payload cá nhân. Dùng redaction và retention policy.

### 21.10. Egress control

Chỉ cho phép workload gọi ra các destination cần thiết. Network policy có thể bổ sung allowlist ở tầng ứng dụng.

## 22. Observability và correlation

Khi một workflow gọi qua nhiều hệ thống, cần khả năng nối các sự kiện thành một luồng quan sát.

### 22.1. Correlation ID

Một correlation ID liên kết các bước trong cùng một nghiệp vụ. Có thể truyền qua header hoặc message metadata theo contract.

### 22.2. Trace context

Distributed tracing dùng trace ID và span ID để liên kết lời gọi giữa các service. Không ghi đè trace context không hợp lệ một cách mù quáng; cần validate và áp dụng policy.

### 22.3. Structured logging

Log nên ghi service alias, operation, endpoint template, status, duration, attempt và correlation ID. Tránh ghi raw URL nếu query có dữ liệu nhạy cảm.

### 22.4. Metrics

Các metric hữu ích:

- Request count theo operation và status.
- Error rate theo category.
- Latency percentile.
- Timeout rate.
- Retry count.
- Circuit breaker state.
- Rate limit response.
- In-flight request.
- Connection pool utilization.

### 22.5. High-cardinality labels

Không dùng customer ID, request ID hoặc URL đầy đủ làm metric label vì cardinality có thể tăng rất lớn. Đặt các giá trị định danh vào trace hoặc log có kiểm soát.

### 22.6. Provider request ID

Giữ request ID do provider trả về để hỗ trợ đối soát và yêu cầu hỗ trợ.

### 22.7. Health và readiness

Không nên để một dependency không thiết yếu làm ứng dụng mất readiness hoàn toàn. Phân loại critical dependency và degraded mode theo yêu cầu nghiệp vụ.

## 23. Performance và connection management

Lời gọi bên ngoài thường có latency cao hơn thao tác trong bộ nhớ hoặc database local.

### 23.1. Connection pooling

Tái sử dụng connection giúp giảm handshake và chi phí thiết lập. Cần cấu hình pool size, idle timeout, max lifetime và giới hạn concurrency phù hợp.

### 23.2. Keep-alive

HTTP keep-alive cho phép tái sử dụng connection. Cần phối hợp timeout client, proxy và server để tránh dùng connection đã bị đóng.

### 23.3. Async I/O

Async client có thể xử lý nhiều request đồng thời mà không cần một thread chờ cho mỗi request. Tuy nhiên, code cần quản lý cancellation, backpressure và error propagation.

### 23.4. Concurrency limit

Giới hạn số request đồng thời tới mỗi dependency để tránh quá tải provider và ứng dụng.

### 23.5. Caching

Cache phù hợp với dữ liệu đọc có thể stale trong một khoảng thời gian được chấp nhận. Cần xác định TTL, invalidation và consistency.

### 23.6. Request coalescing

Nếu nhiều caller cùng yêu cầu một dữ liệu, có thể gộp các request đồng thời thành một lời gọi upstream. Cần đảm bảo quyền và tenant context tương thích.

### 23.7. Batch

Batch API giảm round trip nhưng tăng payload và có thể trả partial failure. Đo trade-off bằng workload thực tế.

### 23.8. Compression

Nén payload có thể giảm bandwidth nhưng tăng CPU và latency xử lý. Chỉ bật khi hai bên hỗ trợ và có giới hạn giải nén an toàn.

## 24. Rate limit và quota

Provider có thể giới hạn số request theo API key, tenant hoặc thời gian.

### 24.1. Quota window

Quota có thể tính theo giây, phút, ngày hoặc tổng mức sử dụng. Client cần biết giới hạn và cách reset.

### 24.2. Response metadata

Một số API trả remaining quota, reset time hoặc Retry-After. Adapter có thể chuyển các giá trị này thành metadata nội bộ.

### 24.3. Client-side limiter

Giới hạn phía client giúp tránh gửi vượt quota. Với nhiều instance, limiter cục bộ có thể không đủ; cần phối hợp hoặc chia quota.

### 24.4. Fairness

Một tenant không nên chiếm toàn bộ quota của service dùng chung. Có thể phân bổ budget theo tenant hoặc priority.

### 24.5. Backpressure

Khi quota cạn, workflow có thể chờ, xếp hàng hoặc trả trạng thái deferred. Không nên retry liên tục mà không tôn trọng thời gian reset.

## 25. Testing external integrations

Không nên phụ thuộc hoàn toàn vào dịch vụ production trong mỗi lần chạy test.

### 25.1. Unit test với fake adapter

Domain workflow có thể dùng fake implementation của port để mô phỏng response và lỗi.

### 25.2. HTTP stub

Stub server trả response đã định nghĩa cho request cụ thể. Có thể kiểm tra method, path, header, body và timeout behavior.

### 25.3. Contract test

Consumer kiểm tra request và response theo contract; provider kiểm tra implementation tương thích với contract đã công bố.

### 25.4. Sandbox

Sandbox của đối tác dùng để kiểm tra luồng tích hợp gần thực tế. Sandbox có thể khác production về dữ liệu, latency, quota hoặc behavior.

### 25.5. Fault injection

Giả lập timeout, connection reset, 429, 500, malformed response, slow response và duplicate callback.

### 25.6. Security test

Kiểm tra token không xuất hiện trong log, redirect không làm lộ credential, TLS validation được bật và endpoint ngoài allowlist bị chặn.

### 25.7. Deterministic test

Dùng clock giả, scheduler giả và random seed cố định để kiểm thử timeout, retry và backoff mà không phải chờ thật.

### 25.8. Test data

Không dùng thông tin cá nhân hoặc credential production trong fixture. Dùng synthetic data và test credential có scope hẹp.

### 25.9. Test provider outage

Kiểm tra ứng dụng hoạt động thế nào khi dependency ngừng phản hồi, phục hồi chậm hoặc trả lỗi không ổn định.

## 26. Triển khai lời gọi HTTP bằng Java

Java cung cấp HTTP Client trong package java.net.http từ Java 11. Ví dụ sau minh họa cách tạo client và gửi request đồng bộ.

### 26.1. Tạo client

~~~java
import java.net.http.HttpClient;
import java.time.Duration;

HttpClient client = HttpClient.newBuilder()
    .connectTimeout(Duration.ofSeconds(2))
    .followRedirects(HttpClient.Redirect.NEVER)
    .build();
~~~

Client có thể được tái sử dụng thay vì tạo mới cho từng request. Redirect được kiểm soát tường minh để tránh chuyển credential sang host ngoài ý muốn.

### 26.2. Tạo request

~~~java
import java.net.URI;
import java.net.http.HttpRequest;
import java.time.Duration;

HttpRequest request = HttpRequest.newBuilder()
    .uri(URI.create("https://api.example/v1/customers/C-42"))
    .timeout(Duration.ofSeconds(3))
    .header("Accept", "application/json")
    .GET()
    .build();
~~~

Trong ứng dụng thật, URI nên được tạo từ endpoint đã validate và path parameter đã encode. Không nối chuỗi dữ liệu tùy ý vào URL.

### 26.3. Gửi request và đọc response

~~~java
import java.net.http.HttpResponse;

HttpResponse<String> response = client.send(
    request,
    HttpResponse.BodyHandlers.ofString()
);

int status = response.statusCode();
String body = response.body();

if (status >= 200 && status < 300) {
    // Parse and validate the response body.
} else {
    // Map status and provider error into a typed error.
}
~~~

Không nên coi mọi status 2xx là business success nếu API có error payload hoặc operation state riêng. Với body lớn, dùng streaming handler thay vì đọc toàn bộ thành String.

### 26.4. Xử lý interruption

Lời gọi đồng bộ có thể bị interrupt. Cần giữ lại interrupt status khi chuyển exception hoặc hủy operation theo đúng lifecycle:

~~~java
try {
    return client.send(request, HttpResponse.BodyHandlers.ofString());
} catch (InterruptedException error) {
    Thread.currentThread().interrupt();
    throw new ExternalCallCancelledException(error);
}
~~~

### 26.5. Async call

~~~java
var future = client.sendAsync(
    request,
    HttpResponse.BodyHandlers.ofString()
);

future.thenApply(response -> {
    if (response.statusCode() / 100 != 2) {
        throw new ExternalServiceException(response.statusCode());
    }
    return response.body();
});
~~~

Trong ứng dụng thực tế, cần gắn timeout, cancellation, executor policy và xử lý exception trong completion stage. Không để exception bị bỏ qua trong một future không được quan sát.

### 26.6. Authentication header

~~~java
HttpRequest request = HttpRequest.newBuilder()
    .uri(endpoint)
    .header("Authorization", "Bearer " + accessToken)
    .header("Accept", "application/json")
    .GET()
    .build();
~~~

Token phải được lấy từ cơ chế cấp credential phù hợp, không hard-code trong source. Tránh ghi request headers vào log.

### 26.7. Deserialize response

Sau khi nhận body, dùng JSON binding library hoặc generated client để tạo DTO có kiểu. Kiểm tra schema và map sang domain result trước khi đưa vào workflow.

## 27. Khai báo lời gọi trong DSL quy trình

Một DSL tích hợp có thể cung cấp operation declaration và cách gọi trong workflow.

### 27.1. Service và operation

~~~text
service "inventory" {
    protocol = http
    endpoint = env("INVENTORY_URL")
    authentication = workload_identity("inventory-client")

    operation "reserve" {
        method = POST
        path = "/v1/reservations"
        request = ReserveInventoryRequest
        response = InventoryReservation
        timeout = 2s
        idempotent = true
    }
}
~~~

### 27.2. Call trong workflow

~~~text
workflow "fulfill-order" {
    task "reserve-stock" {
        result reservation = inventory.reserve({
            orderId = order.id,
            items = order.items,
            idempotencyKey = run.id + "/reserve-stock"
        })
    }
}
~~~

### 27.3. Typed result

Kết quả nên có kiểu InventoryReservation thay vì map không cấu trúc. Compiler có thể kiểm tra field path được dùng ở các bước tiếp theo.

### 27.4. Error branch

~~~text
on inventory.reserve error {
    when INSUFFICIENT_STOCK -> transition "backorder"
    when RATE_LIMITED -> defer
    otherwise -> fail
}
~~~

### 27.5. Policy inheritance

Service có thể đặt timeout mặc định, còn operation override khi có yêu cầu đặc biệt. Workflow có thể truyền deadline còn lại. Quy tắc hợp nhất phải rõ và compiler nên cảnh báo cấu hình vượt giới hạn policy.

### 27.6. Simulation mode

Trong simulation, service adapter cần được thay bằng fake hoặc sandbox. Một flag trên workflow không đủ nếu runtime vẫn có thể gọi production endpoint.

## 28. API versioning và compatibility

API bên ngoài có thể thay đổi độc lập với ứng dụng gọi.

### 28.1. Version trong URL

Một số API dùng path như /v1 hoặc /v2. Adapter cần pin version và không tự động đổi sang latest nếu chưa kiểm tra compatibility.

### 28.2. Version trong header

Một số provider dùng header để chọn API version. Cần giữ version trong service contract và log metadata phù hợp.

### 28.3. Additive change

Thêm field optional thường ít phá vỡ hơn thay đổi type hoặc xóa field. Tuy nhiên, parser strict có thể reject field mới.

### 28.4. Deprecation

Provider có thể thông báo endpoint sắp ngừng. Service catalog nên lưu deprecation date và owner để nhóm tích hợp lên kế hoạch.

### 28.5. Adapter per version

Có thể giữ nhiều adapter version và chuyển về cùng domain contract nội bộ. Cách này cô lập thay đổi API bên ngoài.

### 28.6. Compatibility testing

Chạy contract test với phiên bản provider được hỗ trợ và kiểm tra payload cũ/mới. Không dựa vào việc endpoint vẫn trả 200 để kết luận contract còn tương thích.

## 29. Quản lý dữ liệu và quyền riêng tư

External integration có thể truyền dữ liệu qua biên tổ chức hoặc biên quốc gia.

### 29.1. Data classification

Phân loại dữ liệu trước khi cho phép gửi ra ngoài: public, internal, confidential, personal hoặc restricted theo chính sách tổ chức.

### 29.2. Purpose limitation

Chỉ gửi dữ liệu cần thiết cho mục đích operation. Không gửi toàn bộ record nếu provider chỉ cần một vài thuộc tính.

### 29.3. Tenant isolation

Không để dữ liệu tenant này xuất hiện trong request của tenant khác do cache, context hoặc mapping bị chia sẻ.

### 29.4. Data residency

Endpoint region có thể quyết định dữ liệu được xử lý ở đâu. Cần áp dụng policy theo loại dữ liệu và yêu cầu hợp đồng.

### 29.5. Retention

Request/response log và trace có thể chứa dữ liệu nhạy cảm. Đặt retention, access control và deletion policy.

### 29.6. Audit

Ghi nhận service, operation, principal, tenant context, purpose và kết quả truy cập ở mức metadata cần thiết. Không ghi raw secret hoặc payload không cần thiết.

## 30. Quản lý sự cố và vận hành tích hợp

Một integration cần có kế hoạch vận hành khi provider lỗi hoặc contract thay đổi.

### 30.1. Service owner

Ghi rõ nhóm sở hữu integration, người liên hệ provider và escalation path.

### 30.2. Runbook

Runbook mô tả cách xác định lỗi DNS, TLS, authentication, quota, schema mismatch và provider outage; cách bật fallback; cách replay hoặc reconcile operation.

### 30.3. Degraded mode

Nếu dependency không thiết yếu gặp lỗi, ứng dụng có thể tiếp tục với dữ liệu cache hoặc chức năng hạn chế. Cần hiển thị trạng thái degraded rõ ràng.

### 30.4. Reconciliation

Với operation có side effect, job đối soát có thể so sánh trạng thái nội bộ và provider để tìm giao dịch unknown, duplicate hoặc thiếu cập nhật.

### 30.5. Credential rotation

Rotation credential cần phối hợp với provider, rollout và xác nhận không còn instance dùng key cũ. Tránh thay đồng loạt nếu hệ thống cần overlap period.

### 30.6. Capacity planning

Theo dõi request volume, quota, latency và concurrency. Dự báo tải khi mở campaign hoặc thêm tenant để tránh vượt giới hạn provider.

### 30.7. Change management

Thay endpoint, certificate, schema hoặc auth scheme cần có version, người phê duyệt và kế hoạch rollback hoặc forward fix.

## 31. Những sai lầm thường gặp

### 31.1. Hard-code endpoint và credential

URL và token bị rải trong source khiến đổi môi trường khó và tăng nguy cơ lộ. Dùng service catalog, environment binding và secret reference.

### 31.2. Gọi trực tiếp provider từ mọi nơi

Domain logic phụ thuộc SDK hoặc response type của vendor làm thay đổi provider lan rộng. Dùng port và adapter.

### 31.3. Không có timeout

Request có thể giữ worker và connection vô hạn. Đặt connect, response và overall deadline phù hợp.

### 31.4. Retry mọi lỗi

Validation và authorization error không tự phục hồi. Phân loại lỗi và chỉ retry khi contract cho phép.

### 31.5. Retry operation không idempotent

Timeout sau khi server commit có thể tạo giao dịch trùng. Dùng idempotency key và status lookup.

### 31.6. Tin response mà không validate

Payload ngoài có thể sai schema hoặc chứa dữ liệu độc hại. Parse, validate và giới hạn kích thước.

### 31.7. Tắt TLS validation

Bỏ kiểm tra certificate để khắc phục lỗi tạm thời làm mất bảo vệ xác thực server. Cấu hình trust store đúng.

### 31.8. Theo redirect không kiểm soát

Credential có thể bị gửi tới host khác. Kiểm tra redirect target và không chuyển secret qua domain không được tin cậy.

### 31.9. Log toàn bộ request/response

Payload có thể chứa token hoặc dữ liệu cá nhân. Dùng structured logging và redaction.

### 31.10. Không theo dõi quota

Ứng dụng có thể vượt rate limit và tạo retry storm. Dùng client-side limiter và tôn trọng Retry-After.

### 31.11. Xử lý webhook không deduplicate

Provider có thể gửi lại event. Dùng event ID và inbox deduplication.

### 31.12. Coi async acknowledgment là hoàn tất

HTTP 202 hoặc message accepted thường chỉ xác nhận đã tiếp nhận, không chứng minh công việc đã hoàn tất. Theo dõi operation status.

### 31.13. Không pin API version

Provider đổi contract có thể làm workflow hỏng bất ngờ. Quản lý version và compatibility test.

### 31.14. Chỉ kiểm thử với mock

Mock có thể không phản ánh TLS, auth, quota hoặc schema thực. Bổ sung contract test và sandbox.

### 31.15. Không có reconciliation

Operation có outcome unknown có thể tạo trạng thái nội bộ lệch với provider. Cần query status hoặc đối soát định kỳ.

### 31.16. Dùng một credential toàn quyền

Credential rộng làm tăng phạm vi ảnh hưởng nếu bị lộ. Tách identity và scope theo service, operation và môi trường.

## 32. Quy trình thiết kế tích hợp dịch vụ bên ngoài

Một quy trình thực hiện có thể gồm:

1. **Xác định mục tiêu nghiệp vụ.** Nêu rõ ứng dụng cần đọc, tạo hoặc thay đổi điều gì ở hệ thống ngoài.
2. **Chọn giao thức.** REST, GraphQL, gRPC, SOAP, message, webhook hoặc file transfer theo contract và yêu cầu vận hành.
3. **Xác định service owner.** Ghi provider, owner nội bộ, SLA, quota và escalation path.
4. **Thu thập contract.** Lấy OpenAPI, protobuf, WSDL, JSON Schema hoặc tài liệu chính thức.
5. **Khai báo service và operation.** Định nghĩa endpoint, method, input, output, error và side-effect semantics.
6. **Thiết kế authentication.** Chọn workload identity, OAuth, API key hoặc mTLS với scope tối thiểu.
7. **Quản lý endpoint và secret.** Dùng environment binding, service discovery và secret manager.
8. **Thiết kế request/response mapping.** Chuyển domain model sang DTO và ngược lại, kiểm tra schema.
9. **Đặt timeout và deadline.** Phối hợp với latency budget của workflow và service downstream.
10. **Thiết kế resilience.** Retry có điều kiện, backoff, jitter, idempotency, circuit breaker, bulkhead và rate limit.
11. **Chọn sync hoặc async.** Xác định operation ID, polling, callback, webhook hoặc queue khi xử lý dài.
12. **Bảo vệ dữ liệu.** Áp dụng TLS, allowlist, data minimization, tenant isolation và redaction.
13. **Thêm observability.** Correlation ID, trace, metrics, provider request ID và alert.
14. **Kiểm thử contract và lỗi.** Dùng fake, stub, sandbox, fault injection và security test.
15. **Chuẩn bị vận hành.** Có runbook, credential rotation, reconciliation, quota monitoring và deprecation plan.

## 33. Câu hỏi tự kiểm tra

1. Gọi dịch vụ bên ngoài là gì trong ngữ cảnh DSL tích hợp ứng dụng?
2. Vì sao nên tách ý định nghiệp vụ khỏi giao thức và HTTP client cụ thể?
3. REST, GraphQL, gRPC, SOAP, message broker và webhook khác nhau như thế nào?
4. Một service definition nên chứa những thuộc tính nào?
5. Operation contract cần mô tả input, output, error và side effect ra sao?
6. Path parameter, query parameter, header và request body có vai trò gì?
7. Service discovery và endpoint allowlist giải quyết những vấn đề nào?
8. Phân biệt API key, OAuth access token, OIDC ID token, workload identity và mTLS.
9. Vì sao TLS không thay thế authentication và authorization?
10. Connection timeout, response timeout và workflow deadline khác nhau thế nào?
11. Response cần được kiểm tra status, content type và schema ra sao?
12. Transport error, protocol error, authentication error và business error khác nhau như thế nào?
13. Retry, circuit breaker, bulkhead và rate limiting phối hợp ra sao?
14. Idempotency key giúp xử lý timeout với unknown outcome như thế nào?
15. Khi nào nên dùng synchronous call và khi nào nên dùng asynchronous integration?
16. Polling, callback, webhook và queue có trade-off gì?
17. Offset pagination và cursor pagination khác nhau như thế nào?
18. OpenAPI, Protobuf, JSON Schema và WSDL hỗ trợ quản lý contract ra sao?
19. Port, adapter và anti-corruption layer giúp cô lập provider như thế nào?
20. External integration có thể tạo rủi ro SSRF, replay, mass data exposure và tenant leakage ra sao?
21. Correlation ID, trace context, metrics và provider request ID hỗ trợ điều tra thế nào?
22. Vì sao cần contract testing và sandbox bên cạnh unit test với mock?
23. Hãy thiết kế một operation gọi payment provider, bao gồm authentication, request mapping, timeout, idempotency, error mapping và reconciliation.
