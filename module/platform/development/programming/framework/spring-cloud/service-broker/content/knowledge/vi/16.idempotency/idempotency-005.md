# Liên kết request identity với nghiệp vụ mà không thay thế instance_id

## Bối cảnh

Service broker theo Open Service Broker API (OSB API) nhận nhiều request từ Platform để provision, update, deprovision service instance hoặc tạo và xóa service binding. Khi có timeout, retry, xử lý bất đồng bộ hay nhiều replica broker, đội vận hành cần biết request HTTP nào đã gây ra một thay đổi nghiệp vụ. Đồng thời, broker phải nhận diện đúng tài nguyên và bảo đảm request lặp không tạo side effect trùng.

OSB API định nghĩa header tùy chọn **X-Broker-API-Request-Identity** để Platform gắn một định danh cho request khi request đi qua hệ thống. Header này hữu ích cho logging và request tracing. Nó nhận diện **một request HTTP**, còn **instance_id** nhận diện **service instance** trong vòng đời OSB. Hai định danh phục vụ hai mục đích khác nhau và không thể thay thế cho nhau.

Một thao tác nghiệp vụ có thể đi qua nhiều request HTTP. Ví dụ, Platform gửi PUT provision, broker trả 202 Accepted, sau đó Platform gửi nhiều GET last_operation để polling. Mỗi request có thể mang một request identity khác nhau, nhưng tất cả vẫn liên quan tới cùng instance_id và cùng operation. Nếu broker dùng request identity làm khóa service instance, mỗi lần polling hoặc retry có thể bị hiểu nhầm thành một tài nguyên mới.

Trong module SPRING_CLOUD_SERVICE_BROKER, cần liên kết request identity với service instance, binding và operation để phục vụ idempotency, audit và tracing; đồng thời giữ nguyên các định danh nghiệp vụ mà OSB API đã quy định.

## 1. Phân biệt các loại định danh

Broker cần phân biệt ít nhất năm loại định danh:

| Định danh | Nơi xuất hiện | Đối tượng được nhận diện | Vòng đời |
|---|---|---|---|
| **instance_id** | Path của provision/update/deprovision | Service instance OSB | Xuyên suốt vòng đời instance |
| **binding_id** | Path của create/delete binding | Một binding thuộc instance | Xuyên suốt vòng đời binding |
| **operation ID** | Response async và query last_operation | Một thao tác bất đồng bộ | Từ lúc chấp nhận operation đến khi kết thúc/retention |
| **X-Broker-API-Request-Identity** | HTTP request/response header | Một request HTTP | Theo lần gọi request và chính sách trace |
| **X-Broker-API-Originating-Identity** | HTTP request header | Người dùng Platform khởi tạo hành động | Theo người dùng/hành động, nếu Platform hỗ trợ |

Ngoài ra, ứng dụng có thể có trace_id, span_id, request ID nội bộ hoặc idempotency key riêng. Các giá trị này phải được đặt tên và quản lý rõ ràng để không bị nhầm với định danh do OSB API hoặc Platform cung cấp.

### instance_id là định danh tài nguyên

Ví dụ:

~~~http
PUT /v2/service_instances/db-orders-42?accepts_incomplete=true
X-Broker-API-Version: 2.17
~~~

db-orders-42 là instance ID do Platform dùng để tham chiếu cùng service instance trong các thao tác tiếp theo. Broker dùng ID này trong khóa tra cứu nghiệp vụ, kết hợp với phạm vi Platform nếu broker phục vụ nhiều Platform.

Khi Platform retry provision cho cùng instance, broker vẫn phải tra cứu cùng instance ID. Khi update hoặc deprovision, path tiếp tục dùng ID đó. Request identity của mỗi lần gọi không làm thay đổi danh tính tài nguyên.

### Request identity là định danh request

Ví dụ:

~~~http
PUT /v2/service_instances/db-orders-42?accepts_incomplete=true HTTP/1.1
X-Broker-API-Version: 2.17
X-Broker-API-Request-Identity: 7c0c1f7e-3b9c-4a67-a64e-32b3c0e98e2a
Content-Type: application/json
~~~

Giá trị header giúp broker liên kết log và trace với request mà Platform gửi. Nó không xác định service instance, không chứa plan ID và không phải credential xác thực.

## 2. Ý nghĩa của X-Broker-API-Request-Identity

OSB API cho phép Platform hỗ trợ request identity. Nếu Platform hỗ trợ tính năng này, Platform phải gửi X-Broker-API-Request-Identity trên mọi request OSB API. Giá trị phải là chuỗi không rỗng; GUID được khuyến nghị. Giá trị có thể được tạo riêng cho từng request. Broker có thể đưa giá trị này vào log và nên trả lại header tương ứng trong response.

Đây là một tính năng tùy chọn ở phía Platform. Do đó:

- Broker không được mặc định mọi Platform đều gửi header.
- Khả năng hỗ trợ phụ thuộc Platform và revision OSB API/profile mà hai bên tích hợp; cần xác minh trong hợp đồng triển khai thực tế.
- Khi header không có, broker vẫn xử lý request theo hợp đồng OSB API bình thường.
- Khi header có mặt, broker nên ghi nhận và truyền nó qua các log/trace liên quan tới lần xử lý request.
- Response nên echo lại đúng giá trị request identity nhận được, theo hợp đồng của OSB API.
- Không tự tạo một giá trị khác rồi ghi đè header do Platform gửi.

Ví dụ response đồng bộ:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
X-Broker-API-Request-Identity: 7c0c1f7e-3b9c-4a67-a64e-32b3c0e98e2a

{
  "dashboard_url": "https://console.example.com/services/db-orders-42"
}
~~~

Nếu Platform không gửi request identity, broker không cần giả vờ rằng một giá trị tự sinh là ID do Platform cấp. Broker có thể tạo internal_request_id để quan sát nội bộ, nhưng phải lưu riêng nguồn của giá trị đó.

### Không phải idempotency key

X-Broker-API-Request-Identity giúp nhận diện request trên đường đi qua hệ thống. Nó không được OSB API định nghĩa như khóa idempotency cho service instance hoặc operation.

Không nên dùng header này làm:

- Primary key của service instance.
- Khóa duy nhất của binding.
- Operation ID.
- Khóa duy nhất của request nghiệp vụ qua mọi lần retry.
- Bằng chứng xác thực Platform hoặc người dùng.
- Thông tin phân quyền tenant.

Platform có thể tạo một request identity mới khi retry. Ngay cả khi Platform gửi lại cùng giá trị, broker cũng không nên dựa duy nhất vào header để quyết định request có cùng ý định nghiệp vụ hay không. Idempotency phải dựa trên định danh tài nguyên, loại thao tác và dữ liệu nghiệp vụ đã chuẩn hóa.

## 3. Phân biệt request identity với originating identity

OSB API còn có header X-Broker-API-Originating-Identity. Hai header có tên gần nhau nhưng ý nghĩa khác nhau:

| Header | Câu hỏi trả lời | Mục đích chính |
|---|---|---|
| X-Broker-API-Request-Identity | Đây là request nào? | Correlation, logging và tracing |
| X-Broker-API-Originating-Identity | Người dùng Platform nào khởi tạo hành động? | Audit và authorization theo danh tính người dùng |

Originating identity có định dạng gồm tên Platform và giá trị Base64 của JSON do Platform quy định. Ví dụ minh họa:

~~~http
X-Broker-API-Originating-Identity: cloudfoundry eyJ1c2VyX2lkIjoiYXV0aC11c2VyLTQyIn0=
X-Broker-API-Request-Identity: 7c0c1f7e-3b9c-4a67-a64e-32b3c0e98e2a
~~~

Giá trị Base64 ở đây chỉ là ví dụ minh họa. Broker phải giải mã theo profile của Platform đang tích hợp, xác thực cấu trúc và xử lý dữ liệu theo chính sách bảo mật.

Không dùng request identity thay originating identity khi cần audit người dùng. Một request có thể được tạo bởi Platform automation mà không gắn với người dùng cuối; khi đó request identity vẫn có thể tồn tại trong khi originating identity không có.

Cũng không dùng originating identity thay instance ID. Người dùng có thể tạo nhiều service instance và nhiều binding; danh tính người dùng chỉ cho biết ai khởi tạo hành động, không xác định tài nguyên cụ thể.

## 4. Liên kết request với nghiệp vụ

Một request HTTP cần được liên kết với tài nguyên và operation mà nó tác động. Có thể mô hình hóa quan hệ:

~~~text
Platform
  |
  +-- ServiceInstance(instance_id)
        |
        +-- Operation(operation_id)
        |     |
        |     +-- RequestIdentity(req-001)  PUT provision
        |     +-- RequestIdentity(req-002)  GET last_operation
        |     +-- RequestIdentity(req-003)  GET last_operation
        |
        +-- Binding(binding_id)
              |
              +-- Operation(operation_id)
                    |
                    +-- RequestIdentity(req-004)  PUT binding
                    +-- RequestIdentity(req-005)  DELETE binding
~~~

Quan hệ này cho thấy một operation có thể được quan sát qua nhiều request, còn một instance có thể có nhiều operation trong suốt vòng đời. Request identity là thuộc tính correlation của lần gọi; operation ID là định danh công việc; instance ID là định danh tài nguyên.

### Ví dụ luồng provision bất đồng bộ

1. Platform gửi PUT cho instance_id=db-orders-42 với request identity req-001.
2. Broker xác thực, tạo operation op-7001, lưu instance ở PROVISIONING và trả 202.
3. Worker tiếp tục gọi provider.
4. Platform gửi GET last_operation với request identity req-002.
5. Platform polling lần nữa với request identity req-003.
6. Cả hai request polling đều tra cứu op-7001 của db-orders-42.
7. Worker hoàn tất, Platform nhận state succeeded.

~~~mermaid
sequenceDiagram
    participant P as Platform
    participant B as Broker API
    participant DB as Operation DB
    participant W as Worker
    participant PR as Provider

    P->>B: PUT instance_id=db-orders-42, request-id=req-001
    B->>DB: Create instance + operation op-7001
    B-->>P: 202 operation=op-7001, echo req-001
    W->>DB: Load op-7001
    W->>PR: Provision resource
    P->>B: GET last_operation op-7001, request-id=req-002
    B->>DB: Read op-7001
    B-->>P: in progress, echo req-002
    PR-->>W: Resource ready
    W->>DB: Mark op-7001 succeeded
    P->>B: GET last_operation op-7001, request-id=req-003
    B->>DB: Read op-7001
    B-->>P: succeeded, echo req-003
~~~

Không đổi operation ID theo request identity của từng lần polling. Nếu làm như vậy, Platform sẽ không thể theo dõi một operation xuyên suốt nhiều request.

## 5. Idempotency phải gắn với ý định nghiệp vụ

Idempotency có nghĩa là một ý định nghiệp vụ được gửi lặp không tạo ra hiệu ứng ngoài dự kiến. Broker cần xác định khóa idempotency dựa trên loại tài nguyên và thao tác.

Ví dụ các khóa nghiệp vụ:

| Thao tác | Khóa phạm vi tài nguyên | Dữ liệu cần so sánh |
|---|---|---|
| Provision | platform_id + instance_id | service_id, plan_id, parameters đã chuẩn hóa |
| Update | platform_id + instance_id + operation/type hoặc revision | plan đích, parameters, previous values có ý nghĩa |
| Deprovision | platform_id + instance_id | service_id, plan_id và trạng thái instance |
| Create binding | platform_id + instance_id + binding_id | app/resource identity, parameters và quyền |
| Delete binding | platform_id + instance_id + binding_id | Trạng thái binding và operation thu hồi |

Request identity có thể được lưu cùng bản ghi lần gọi để truy vết, nhưng không thay thế các khóa trên.

### Provision lặp

Nếu hai PUT cùng instance_id có cùng service, plan và parameters đã chuẩn hóa, broker có thể nhận diện đây là retry của cùng ý định và trả kết quả đã có theo hợp đồng. Nếu cùng instance ID nhưng plan hoặc parameters khác, broker phải xử lý như xung đột hoặc request không hợp lệ theo trạng thái hiện tại; không tạo instance thứ hai.

### Update lặp

Hai PATCH có cùng request payload có thể là retry của một update, nhưng hai PATCH khác nhau trên cùng instance là hai ý định nghiệp vụ khác nhau. Broker cần serialize các thao tác thay đổi cùng instance, dùng operation/fingerprint hoặc revision để phân biệt và tránh worker cũ ghi đè trạng thái mới.

### Binding lặp

PUT binding lặp với cùng binding ID và cùng consumer/parameters phải được xử lý idempotent. Nếu binding ID đã thuộc consumer hoặc quyền khác, broker không được trả credential của binding cũ cho request mới.

### Deprovision và delete binding lặp

DELETE lặp phải tuân theo status code và semantics riêng của OSB API. Request identity chỉ giúp truy vết từng lần DELETE; nó không quyết định tài nguyên đã tồn tại hay đã bị xóa.

## 6. Request fingerprint và idempotency key

Khi không có một idempotency key chuẩn được Platform gửi trong OSB API request, broker có thể tạo fingerprint từ nội dung nghiệp vụ đã chuẩn hóa. Fingerprint không phải request identity.

Ví dụ fingerprint cho provision:

~~~text
fingerprint = SHA-256(
    platform_id
    + instance_id
    + service_id
    + plan_id
    + canonical_json(parameters)
)
~~~

Các bước chuẩn hóa:

1. Xác định platform scope từ credential/configuration đã xác thực.
2. Đọc instance ID từ path.
3. Chuẩn hóa service ID và plan ID theo quy tắc so sánh của broker.
4. Chuẩn hóa JSON parameters theo cách không phụ thuộc thứ tự key.
5. Loại bỏ trường không ảnh hưởng tới ý định nghiệp vụ nếu contract cho phép.
6. Tạo hash và lưu cùng operation hoặc request record.

Không đưa raw password hoặc secret vào fingerprint theo cách có thể làm lộ giá trị qua log hoặc metric. Nếu parameters chứa secret, cân nhắc canonicalization trong vùng xử lý được bảo vệ và hash bằng HMAC với khóa nội bộ thay vì hash thuần.

### Idempotency key do Platform mở rộng

Một Platform hoặc integration riêng có thể thỏa thuận thêm header như Idempotency-Key. Đây là extension ngoài header X-Broker-API-Request-Identity của OSB API. Chỉ sử dụng khi hai bên thống nhất:

- Tên header và định dạng.
- Phạm vi duy nhất của key: theo Platform, endpoint, instance hay operation.
- Thời hạn lưu key và kết quả.
- Hành vi khi cùng key nhưng payload khác.
- Cách xử lý key khi Platform retry sau timeout.

Không tự coi X-Broker-API-Request-Identity là Idempotency-Key. Nếu không có thỏa thuận extension, dùng instance/binding identity kết hợp request fingerprint và operation state để thực hiện idempotency.

## 7. Mô hình dữ liệu liên kết request, instance và operation

Không nên dùng một cột request_id duy nhất trong bảng service_instance để ghi đè mỗi lần có request mới. Cách đó làm mất lịch sử request, không biểu diễn được polling và có thể khiến request cuối cùng bị hiểu nhầm là request tạo instance.

Một mô hình tham khảo:

~~~sql
CREATE TABLE service_instance (
    platform_id       VARCHAR(128) NOT NULL,
    instance_id       VARCHAR(128) NOT NULL,
    service_id        VARCHAR(128) NOT NULL,
    plan_id           VARCHAR(128) NOT NULL,
    lifecycle_state   VARCHAR(32) NOT NULL,
    current_operation_id VARCHAR(128),
    version           BIGINT NOT NULL DEFAULT 0,
    created_at        TIMESTAMP NOT NULL,
    updated_at        TIMESTAMP NOT NULL,
    PRIMARY KEY (platform_id, instance_id)
);

CREATE TABLE service_operation (
    operation_id        VARCHAR(128) PRIMARY KEY,
    platform_id         VARCHAR(128) NOT NULL,
    instance_id         VARCHAR(128) NOT NULL,
    operation_type      VARCHAR(32) NOT NULL,
    request_fingerprint VARCHAR(128) NOT NULL,
    state               VARCHAR(24) NOT NULL,
    created_at          TIMESTAMP NOT NULL,
    completed_at        TIMESTAMP
);

CREATE TABLE broker_request (
    internal_request_id VARCHAR(128) PRIMARY KEY,
    platform_id         VARCHAR(128) NOT NULL,
    request_identity    VARCHAR(256),
    instance_id         VARCHAR(128),
    binding_id          VARCHAR(128),
    operation_id        VARCHAR(128),
    http_method         VARCHAR(16) NOT NULL,
    route_template      VARCHAR(256) NOT NULL,
    received_at         TIMESTAMP NOT NULL,
    response_status     INTEGER,
    trace_id            VARCHAR(128)
);
~~~

Đây là schema minh họa; cần bổ sung foreign key, index, retention và phân vùng theo quy mô triển khai. internal_request_id là khóa nội bộ do broker tạo cho từng lần nhận request. request_identity lưu nguyên giá trị header nếu có. Không đặt unique constraint trên request_identity nếu broker chưa có cam kết rằng mọi Platform luôn gửi một giá trị duy nhất và không tái sử dụng; specification cho phép giá trị có thể unique theo request và khuyến nghị GUID, nhưng broker nên tránh phụ thuộc quá mức vào giả định đó.

Các index hữu ích:

- (platform_id, instance_id) trên service_instance để tra cứu tài nguyên.
- (platform_id, instance_id, created_at) trên service_operation để lấy lịch sử thao tác.
- operation_id trên broker_request để tìm tất cả request liên quan tới một operation.
- request_identity để tra cứu log/tracing khi Platform cung cấp header.
- (platform_id, instance_id, binding_id) cho binding record.

Nếu muốn bảo đảm cùng một request identity không được gắn với hai request trong một khoảng thời gian, hãy áp dụng policy riêng sau khi xác định khả năng của Platform. Không dùng constraint đó làm điều kiện duy nhất cho idempotency nghiệp vụ.

## 8. Thu thập và phản hồi request identity trong Spring

Trong Spring Boot, có thể đọc X-Broker-API-Request-Identity tại HTTP boundary bằng filter hoặc interceptor. Việc đọc header nên tập trung ở một nơi để tất cả endpoint OSB có cùng cách xử lý.

Một filter Servlet minh họa:

~~~java
public class RequestIdentityFilter extends OncePerRequestFilter {

    static final String HEADER = "X-Broker-API-Request-Identity";
    static final String ATTRIBUTE = "brokerRequestIdentity";

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain) throws ServletException, IOException {

        String requestIdentity = request.getHeader(HEADER);
        if (requestIdentity != null && requestIdentity.isBlank()) {
            response.sendError(
                    HttpServletResponse.SC_BAD_REQUEST,
                    "X-Broker-API-Request-Identity must not be empty");
            return;
        }

        request.setAttribute(ATTRIBUTE, requestIdentity);
        try {
            if (requestIdentity != null) {
                response.setHeader(HEADER, requestIdentity);
            }
            chain.doFilter(request, response);
        } finally {
            // Clear request-scoped logging context here if one was added.
        }
    }
}
~~~

Đây là ví dụ kiến trúc. Khi triển khai thực tế:

- Chỉ áp dụng filter cho route OSB API.
- Không làm thay đổi authentication/authorization filter.
- Kiểm soát độ dài header và từ chối ký tự không hợp lệ theo policy HTTP server.
- Không đưa giá trị chưa được kiểm tra vào log format hoặc response header.
- Dùng OncePerRequestFilter đúng với Servlet stack; WebFlux cần WebFilter và Reactor Context.
- Nếu Spring Cloud Open Service Broker đã cấu hình interceptor xử lý request identity, không đăng ký thêm interceptor thứ hai gây echo header trùng.

Spring Cloud Open Service Broker có thành phần RequestIdentityInterceptor trong các phiên bản cung cấp hỗ trợ này. Interceptor đọc header từ request và đặt cùng giá trị vào response header. Hãy kiểm tra tài liệu và auto-configuration của phiên bản dependency đang dùng; không giả định mọi phiên bản cũ đều có cùng hành vi.

### Không tự ghi đè response header

Nếu framework đã echo header, filter tự viết không nên set thêm một giá trị khác. Response có hai giá trị hoặc giá trị bị nối lặp có thể làm client khó xác định request identity. Kiểm thử HTTP thực tế để xác nhận response chỉ chứa đúng một giá trị.

## 9. Gắn request identity vào log và trace

Broker nên ghi request identity vào structured log cùng với các định danh nghiệp vụ:

~~~json
{
  "event": "osb.request.completed",
  "request_identity": "7c0c1f7e-3b9c-4a67-a64e-32b3c0e98e2a",
  "internal_request_id": "req-local-9001",
  "platform_id": "cf-prod",
  "instance_id": "db-orders-42",
  "operation_id": "provision-7f31a9",
  "http_method": "PUT",
  "route": "/v2/service_instances/{instance_id}",
  "status": 202
}
~~~

Một log của worker có thể giữ operation ID và internal trace context:

~~~json
{
  "event": "provider.provision.started",
  "operation_id": "provision-7f31a9",
  "instance_id": "db-orders-42",
  "provider_resource_ref": "resource-8821",
  "trace_id": "0af7651916cd43dd8448eb211c80319c"
}
~~~

Worker có thể chạy sau khi HTTP request kết thúc và ở process khác. Không phụ thuộc MDC hoặc ThreadLocal của request ban đầu để truyền context sang worker. Hãy lưu correlation metadata cần thiết trong operation/outbox, sau đó tạo trace/span mới khi worker thực thi và liên kết với trace ban đầu bằng span link hoặc thuộc tính correlation phù hợp.

### Request identity không thay thế trace context

X-Broker-API-Request-Identity là định danh request theo OSB API. W3C Trace Context (traceparent, tracestate) hoặc tracing framework quản lý trace/span có mục đích và semantics riêng. Một request identity có thể được ghi vào span attribute, nhưng không tự động trở thành trace ID hoặc span ID.

Không dùng request identity làm metric label có cardinality cao. Hãy dùng nó trong log hoặc trace để tra cứu chi tiết; metric nên nhóm theo endpoint, status, operation type và provider.

## 10. Bảo mật và độ tin cậy

Request identity được Platform gửi qua HTTP header nên phải được xem là dữ liệu đầu vào, không phải bằng chứng xác thực.

Các nguyên tắc:

- Xác thực Platform bằng cơ chế OSB đã thỏa thuận trước khi tin request.
- Không dùng request identity để quyết định tenant hoặc quyền truy cập.
- Tra cứu instance theo platform scope đã xác thực và instance_id từ path.
- Không cho phép header chứa CR/LF hoặc dữ liệu có thể tạo log injection.
- Giới hạn độ dài header để tránh lạm dụng bộ nhớ/log.
- Escape hoặc encode giá trị khi ghi structured log.
- Không ghi authorization, secret, password hoặc credentials vào cùng log.
- Không truyền request identity sang provider như một danh tính người dùng nếu chưa có thỏa thuận.
- Lưu retention request log phù hợp với audit/privacy policy.

Nếu Platform không gửi header, broker có thể sinh internal request ID ngẫu nhiên cho observability. Giá trị nội bộ cần được ghi rõ internal_request_id, không đặt tên như thể đó là X-Broker-API-Request-Identity do Platform cấp.

## 11. Xử lý retry và nhiều request cùng một nghiệp vụ

Một retry có thể mang request identity khác với lần đầu. Broker cần dựa trên trạng thái nghiệp vụ:

~~~mermaid
flowchart TD
    A[Nhận request + request identity] --> B[Authenticate Platform]
    B --> C[Resolve platform scope + resource ID]
    C --> D[Normalize business command]
    D --> E[Compute request fingerprint]
    E --> F{Có operation/ý định tương ứng?}
    F -->|Cùng fingerprint đang chạy| G[Trả lại operation hiện có]
    F -->|Cùng fingerprint đã xong| H[Trả kết quả idempotent]
    F -->|Cùng resource nhưng payload xung đột| I[Conflict hoặc serialize theo policy]
    F -->|Ý định mới hợp lệ| J[Tạo operation mới]
    G --> K[Log request identity riêng của lần gọi]
    H --> K
    I --> K
    J --> K
~~~

Ví dụ:

| Lần gọi | instance_id | request identity | operation ID | Kết quả |
|---|---|---|---|---|
| PUT đầu tiên | db-orders-42 | req-001 | op-7001 | 202 Accepted |
| Retry PUT do mất response | db-orders-42 | req-002 | op-7001 | Trả lại operation hiện có |
| GET last_operation | db-orders-42 | req-003 | op-7001 | in progress |
| GET last_operation | db-orders-42 | req-004 | op-7001 | succeeded |
| PATCH thay đổi plan sau đó | db-orders-42 | req-005 | op-7002 | Operation nghiệp vụ mới |

Các request identity khác nhau được liên kết tới cùng operation op-7001 khi chúng cùng đại diện cho retry/polling của một nghiệp vụ. Update sau đó là ý định mới nên có operation ID mới, nhưng vẫn tác động lên cùng instance_id.

## 12. Liên kết với binding và operation bất đồng bộ

Binding cũng có định danh riêng. Một request PUT binding có thể tạo binding ID và credentials; request DELETE sau đó dùng cùng binding ID để thu hồi. Request identity của PUT và DELETE là hai giá trị correlation độc lập.

Ví dụ:

~~~http
PUT /v2/service_instances/db-orders-42/service_bindings/api-17 HTTP/1.1
X-Broker-API-Version: 2.17
X-Broker-API-Request-Identity: req-bind-001
~~~

~~~http
DELETE /v2/service_instances/db-orders-42/service_bindings/api-17?service_id=postgres&plan_id=standard HTTP/1.1
X-Broker-API-Version: 2.17
X-Broker-API-Request-Identity: req-unbind-009
~~~

Broker giữ nguyên binding ID trong dữ liệu nghiệp vụ và lưu mỗi request identity ở bảng request log. Khi unbind bất đồng bộ, operation ID của thao tác thu hồi tiếp tục được dùng cho polling; request identity của từng GET last_operation chỉ phục vụ correlation của lần polling đó.

## 13. Tích hợp với Spring Cloud Open Service Broker

Spring Cloud Open Service Broker cung cấp abstraction cho service instance và binding lifecycle. Request identity nên được thu thập ở HTTP boundary, sau đó đưa vào request-scoped context hoặc logging context. Application service vẫn nhận các định danh nghiệp vụ riêng:

~~~java
public record RequestContext(
        String platformId,
        String requestIdentity,
        String internalRequestId,
        String traceId) {
}

public record ProvisionCommand(
        String instanceId,
        String serviceId,
        String planId,
        Map<String, Object> parameters,
        RequestContext requestContext) {
}
~~~

Khi handler tạo command, instanceId phải đến từ path/request model của OSB; requestIdentity lấy từ header; operationId được sinh hoặc tải từ operation repository. Không gán request identity vào trường instance ID.

Ví dụ mapping ở application boundary:

~~~java
ProvisionResult provision(
        CreateServiceInstanceRequest request,
        RequestContext requestContext) {

    var command = new ProvisionCommand(
            request.getServiceInstanceId(),
            request.getServiceDefinitionId(),
            request.getPlanId(),
            request.getParameters(),
            requestContext);

    return provisioningService.execute(command);
}
~~~

Đây là ví dụ định hướng; chữ ký method và accessor cần theo phiên bản framework đang cài đặt. Nếu framework không cung cấp RequestContext trực tiếp, dùng request attribute, interceptor hoặc Reactor Context để chuyển metadata tới application boundary.

### Phân lớp trách nhiệm

| Thành phần | Trách nhiệm |
|---|---|
| HTTP filter/interceptor | Đọc request identity, tạo internal request ID nếu cần, echo header theo policy |
| Authentication layer | Xác thực Platform và xác định platform scope |
| OSB service implementation | Lấy instance/binding ID và tạo command |
| Application service | Thực hiện idempotency và điều phối nghiệp vụ |
| Operation repository | Lưu operation ID, fingerprint và trạng thái |
| Request/audit repository | Lưu request identity liên kết với instance/operation |
| Provider adapter | Thực hiện side effect theo operation, không tự coi request identity là resource ID |

Không để provider adapter phụ thuộc trực tiếp vào Servlet request hoặc WebFlux ServerRequest. Metadata cần thiết phải được chuyển qua command/context có kiểu rõ ràng.

## 14. Kiểm thử

Kiểm thử phải chứng minh request identity được liên kết đúng nhưng không làm thay đổi định danh nghiệp vụ.

| Tình huống | Kết quả cần xác minh |
|---|---|
| Request có request identity hợp lệ | Broker ghi nhận giá trị và echo đúng trong response |
| Request không có header | Request vẫn được xử lý; internal request ID có thể được tạo riêng |
| Header rỗng hoặc vượt giới hạn | Xử lý theo validation policy, không làm hỏng log/response |
| Hai request cùng instance ID, request identity khác nhau | Cùng tra cứu một instance |
| Retry provision cùng payload | Không tạo instance/provider resource thứ hai |
| Retry provision payload khác | Xử lý conflict theo idempotency policy |
| Poll last_operation nhiều lần | Cùng operation ID dù request identity mỗi lần khác |
| Originating identity khác request identity | Audit người dùng và trace request không bị trộn |
| Header có ký tự CR/LF | Không log injection hoặc response splitting |
| Framework interceptor đã echo header | Response chỉ có một giá trị, không bị duplicate |
| Nhiều Platform có cùng instance ID | Scope platform tách biệt, không truy cập chéo |
| Worker chạy sau khi request kết thúc | Operation context vẫn có correlation metadata cần thiết |

### Test quan trọng: request identity không thay instance ID

1. Gửi PUT với path instance_id=db-orders-42 và header request-identity=req-A.
2. Xác nhận broker tạo đúng một bản ghi instance với ID db-orders-42.
3. Gửi retry PUT cùng path nhưng header request-identity=req-B.
4. Xác nhận broker tìm lại instance db-orders-42, không tạo instance req-B.
5. Xác nhận cả req-A và req-B có thể được liên kết với cùng operation hoặc kết quả idempotent.
6. Gọi GET last_operation với request identity req-C.
7. Xác nhận operation ID không đổi và request log ghi req-C như một lần polling riêng.

Test này phát hiện lỗi thiết kế khi lập trình viên vô tình dùng header request identity làm khóa tài nguyên.

## 15. Quan sát và audit

Log và trace nên có đủ trường để điều tra một request mà không làm phình metric:

- request_identity: giá trị từ Platform nếu có.
- internal_request_id: định danh nội bộ cho lần nhận request.
- trace_id và span_id: định danh tracing.
- platform_id: phạm vi Platform đã xác thực.
- instance_id và binding_id: tài nguyên nghiệp vụ.
- operation_id: công việc bất đồng bộ.
- http_method, route template và status.
- originating_identity đã được chuẩn hóa hoặc reference an toàn nếu policy cho phép.

Không đưa request identity, instance ID hoặc tenant ID vào metric label có cardinality không giới hạn. Dùng metric theo route, operation type, status class và provider; dùng log/trace để tra cứu giá trị cụ thể.

Audit log có thể lưu request identity cùng originating identity để trả lời hai câu hỏi: request nào đã được xử lý và ai khởi tạo hành động. Cần kiểm soát quyền đọc audit log, retention và masking theo chính sách dữ liệu của tổ chức.

## 16. Lỗi thiết kế thường gặp

### Dùng request identity làm instance ID

Mỗi lần retry hoặc polling có thể có một request identity mới, khiến broker tạo nhiều bản ghi instance cho cùng tài nguyên. Luôn lấy instance ID từ path OSB.

### Dùng request identity làm operation ID

Một operation có thể được theo dõi qua nhiều request. Operation ID phải được tạo và lưu riêng, sau đó liên kết các request identity liên quan.

### Coi request identity là idempotency key

Header phục vụ nhận diện request và tracing. Idempotency phải dựa trên khóa tài nguyên, loại thao tác, fingerprint và trạng thái operation.

### Coi request identity là user identity

Request identity không nói ai đã thực hiện hành động. Dùng originating identity và cơ chế authorization đã xác thực khi cần danh tính người dùng.

### Bắt buộc header trên mọi Platform

OSB API cho phép Platform không hỗ trợ tính năng này. Broker không nên từ chối request chỉ vì header vắng mặt.

### Ghi đè header hoặc echo trùng

Nếu framework đã echo request identity, interceptor tùy chỉnh có thể làm response chứa nhiều giá trị. Chỉ có một nơi chịu trách nhiệm echo và kiểm thử response thực tế.

### Truyền request context qua ThreadLocal sang worker

Worker có thể chạy ở thread/process khác sau khi HTTP request kết thúc. Hãy lưu metadata cần thiết trong operation/outbox và dựng context mới khi xử lý nền.

## 17. Checklist triển khai

- [ ] instance_id tiếp tục là khóa tài nguyên service instance theo OSB API.
- [ ] binding_id tiếp tục nhận diện binding riêng trong instance.
- [ ] operation_id được lưu riêng cho công việc bất đồng bộ.
- [ ] X-Broker-API-Request-Identity chỉ được dùng để correlation/tracing request.
- [ ] Broker chấp nhận request không có request identity nếu Platform không hỗ trợ.
- [ ] Khi header có mặt, broker lưu và echo đúng giá trị theo hợp đồng.
- [ ] X-Broker-API-Originating-Identity được xử lý riêng cho user identity/audit.
- [ ] Request identity không được dùng làm credential, tenant key hoặc idempotency key.
- [ ] Retry được nhận diện bằng resource identity, operation state và request fingerprint.
- [ ] Nhiều request polling có thể liên kết tới cùng operation.
- [ ] Request log liên kết được request identity, platform scope, instance/binding và operation.
- [ ] Internal request ID được phân biệt rõ với header do Platform gửi.
- [ ] Log chống injection và không chứa secret.
- [ ] Worker nhận correlation metadata qua operation/outbox, không dựa vào HTTP thread context.
- [ ] Có integration test chứng minh request identity không thay instance_id.

## Kết luận

X-Broker-API-Request-Identity giúp nhận diện một request HTTP khi request đi qua Platform và Service Broker. instance_id vẫn là định danh service instance; binding_id xác định binding; operation ID xác định công việc bất đồng bộ; còn originating identity mô tả người dùng Platform khởi tạo hành động. Broker nên lưu request identity để log, trace và liên kết với instance/operation, đồng thời echo lại header khi Platform gửi. Idempotency phải được thực hiện bằng định danh tài nguyên, loại thao tác, fingerprint và trạng thái nghiệp vụ. Tách rõ các loại ID giúp retry, polling, audit và xử lý bất đồng bộ hoạt động nhất quán mà không tạo tài nguyên trùng.

## Tài liệu tham khảo

- [Open Service Broker API specification — Request Identity](https://github.com/cloudfoundry/servicebroker/blob/master/spec.md#request-identity)
- [Spring Cloud Open Service Broker — RequestIdentityInterceptor API](https://docs.spring.io/spring-cloud-open-service-broker/docs/current/apidocs/org/springframework/cloud/servicebroker/autoconfigure/web/servlet/RequestIdentityInterceptor.html)
