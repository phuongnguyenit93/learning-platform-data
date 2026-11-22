# Tài liệu hóa hợp đồng và trách nhiệm của từng bên tham gia

## Mục tiêu

Trong hệ thống messaging, producer và consumer cần thống nhất cách gửi, nhận và diễn giải thông điệp. Nếu route, payload, metadata, lỗi hoặc quy tắc retry chỉ tồn tại trong code, các bên dễ triển khai không tương thích và khó xử lý khi hệ thống thay đổi.

Bài học này tập trung vào hợp đồng thông điệp trong Spring RSocket. Sau bài này, bạn có thể:

- Xác định các thành phần cần có trong một message contract.
- Tài liệu hóa route, kiểu tương tác, payload, metadata, lỗi và vòng đời.
- Phân định trách nhiệm của requester, responder, service owner và đội vận hành.
- Quản lý phiên bản hợp đồng và thay đổi tương thích ngược.
- Thiết kế ví dụ, kiểm thử hợp đồng và quy trình công bố thay đổi.
- Tổ chức tài liệu để nhóm khác có thể tích hợp mà không phải đọc implementation nội bộ.

## 1. Message contract là gì?

Message contract là thỏa thuận có thể kiểm tra được giữa các bên trao đổi thông điệp. Nó mô tả những gì một bên được phép gửi, những gì bên kia phải hiểu và kết quả mà mỗi bên có thể mong đợi.

Một contract tốt trả lời được các câu hỏi:

1. Ai gửi thông điệp và ai xử lý?
2. Route nào được gọi, route có ý nghĩa gì?
3. Dùng kiểu tương tác RSocket nào?
4. Payload có cấu trúc và kiểu dữ liệu ra sao?
5. Metadata nào bắt buộc, metadata nào tùy chọn?
6. Thành công, từ chối nghiệp vụ và lỗi kỹ thuật được biểu diễn thế nào?
7. Có bảo đảm thứ tự, thời hạn, retry hoặc idempotency không?
8. Ai sở hữu contract, ai duyệt thay đổi và ai hỗ trợ khi có sự cố?

Contract là ranh giới giao tiếp công khai giữa các service. Implementation có thể thay đổi bên trong miễn là vẫn đáp ứng contract đã công bố.

### 1.1. Phân biệt contract với implementation

| Contract | Implementation |
|---|---|
| Route orders.submit | Tên method Java trong controller |
| Payload SubmitOrder | Cách lưu đơn hàng trong database |
| Response OrderAccepted | Repository, transaction manager và câu lệnh SQL |
| Mã lỗi ORDER_REJECTED | Exception class nội bộ |
| Metadata tenant và correlation ID | Cách hệ thống lấy thông tin tenant từ security context |
| Timeout tối đa được công bố | Cấu hình timeout cụ thể trong từng client |

Không đưa chi tiết nội bộ như tên bảng database, package riêng, stack trace hoặc thuật toán không cần thiết vào contract. Chỉ công bố những chi tiết consumer cần để tích hợp và vận hành đúng.

### 1.2. Contract là thỏa thuận hai chiều

Requester chịu trách nhiệm gửi payload hợp lệ, dùng route đúng, cung cấp metadata bắt buộc và xử lý response hoặc lỗi. Responder chịu trách nhiệm xác thực đầu vào, thực hiện đúng ngữ nghĩa đã công bố và trả kết quả theo contract.

Hai bên cần cùng thống nhất timeout, cancellation, retry, versioning và cách xử lý khi kết quả chưa rõ. Một contract không đầy đủ nếu chỉ mô tả request DTO mà bỏ qua lỗi, stream termination hoặc trách nhiệm khi mất kết nối.

## 2. Những thành phần cần tài liệu hóa

### 2.1. Định danh và quyền sở hữu

Mỗi contract nên có:

- Tên API hoặc capability, ví dụ Inventory Reservation.
- Mã định danh ổn định, ví dụ inventory-reservation.
- Phiên bản contract và ngày hiệu lực.
- Service sở hữu responder và nhóm liên hệ hỗ trợ.
- Các consumer đã đăng ký hoặc phụ thuộc vào contract.
- Link tới schema, ví dụ, changelog và hướng dẫn vận hành.
- Trạng thái: draft, active, deprecated hoặc retired.

Tên service và tên route nên ổn định. Không dùng tên class hoặc method làm định danh contract vì implementation có thể đổi tên mà không làm thay đổi API.

### 2.2. Transport và encoding

Với RSocket, ghi rõ:

- Transport: TCP hoặc WebSocket.
- Host/port hoặc WebSocket mapping path trong từng môi trường.
- Data MIME type, ví dụ application/json.
- Metadata MIME type, ví dụ message/x.rsocket.composite-metadata khi dùng composite metadata.
- Codec hoặc quy tắc serialization được hỗ trợ.
- TLS và yêu cầu xác thực kết nối.
- Giới hạn kích thước payload và metadata.
- Keepalive, timeout và chính sách reconnect/resume nếu consumer cần biết.

Không ghi credentials, token thật hoặc địa chỉ hạ tầng nhạy cảm vào tài liệu công khai. Dùng placeholder và cung cấp thông tin môi trường qua kênh cấu hình an toàn.

### 2.3. Route và kiểu tương tác

Route là tên logic mà requester dùng để định tuyến message đến handler. Với Spring, route thường được ánh xạ bằng @MessageMapping.

Ghi rõ cho từng route:

- Tên route chính xác, phân biệt chữ hoa/thường nếu hệ thống có quy ước như vậy.
- Mục đích nghiệp vụ.
- Requester và responder.
- Interaction model.
- Kiểu payload đầu vào và đầu ra.
- Cardinality: một response hay nhiều response.
- Ordering: có bảo đảm thứ tự hay không.
- Điều kiện hoàn tất và điều kiện lỗi.
- Timeout, retry, idempotency và giới hạn tải.

Bốn interaction model phổ biến:

| Kiểu RSocket | Hợp đồng cần nêu |
|---|---|
| Request-Response | Một request, một response hoặc một lỗi. |
| Request-Stream | Một request, zero hoặc nhiều response payload, sau đó complete hoặc error. |
| Request-Channel | Hai phía trao đổi payload theo luồng; mô tả riêng chiều vào và chiều ra. |
| Fire-and-Forget | Không có response payload nghiệp vụ; mô tả cách xác nhận hoặc truy vấn trạng thái ở route khác nếu cần. |

Với stream, phải ghi rõ điều gì xảy ra khi client cancel, server error, kết nối mất hoặc producer không còn dữ liệu. Không giả định một stream luôn phát ít nhất một phần tử.

### 2.4. Payload schema

Mỗi payload cần mô tả:

- Tên field và ý nghĩa nghiệp vụ.
- Kiểu dữ liệu, định dạng và đơn vị.
- Bắt buộc hay tùy chọn.
- Null có hợp lệ không.
- Quy tắc validation và giới hạn độ dài.
- Giá trị mặc định nếu có.
- Quy tắc tương thích khi thêm hoặc loại bỏ field.
- Ví dụ request/response hợp lệ và ví dụ không hợp lệ.

Không dùng tên field mơ hồ như value, data hoặc status nếu không có định nghĩa. Với số tiền, ghi rõ currency và quy tắc precision. Với thời gian, ghi rõ định dạng, timezone và ý nghĩa của timestamp.

Ví dụ schema request:

~~~json
{
  "requestId": "req-2026-0042",
  "customerId": "cust-101",
  "amount": 125000,
  "currency": "VND"
}
~~~

Ý nghĩa:

| Field | Kiểu | Bắt buộc | Quy tắc |
|---|---|---|---|
| requestId | string | Có | ID duy nhất cho request logic; giữ nguyên khi retry cùng thao tác. |
| customerId | string | Có | ID khách hàng do hệ thống định danh cấp. |
| amount | integer | Có | Số tiền theo đơn vị nhỏ nhất được quy định trong contract; ví dụ này dùng VND nguyên đồng. |
| currency | string | Có | Mã tiền tệ ISO 4217, ví dụ VND. |

Nếu cần decimal, phải quy định rõ precision, scale và cách làm tròn. Tránh để consumer tự đoán đơn vị hoặc quy tắc làm tròn.

### 2.5. Metadata

Metadata thường mang thông tin điều khiển hoặc ngữ cảnh không thuộc payload nghiệp vụ, ví dụ:

- Authentication credentials hoặc token theo cơ chế bảo mật đã thống nhất.
- Correlation ID và trace context.
- Tenant hoặc organization context.
- Locale hoặc client capability nếu thực sự cần.
- Deadline hoặc thông tin ưu tiên theo chính sách hệ thống.

Mỗi metadata field cần có tên, encoding, nguồn tạo, tính bắt buộc, phạm vi áp dụng và quy tắc xác thực. Phân biệt metadata ở cấp kết nối SETUP với metadata gắn từng request. Một giá trị được gửi trong SETUP có thể tồn tại theo kết nối; không dùng nó cho thông tin thay đổi theo từng request nếu contract yêu cầu cập nhật.

Không tin tenant ID hoặc role chỉ vì consumer tự gửi trong metadata. Responder phải xác thực danh tính và kiểm tra quyền trên tài nguyên cụ thể.

## 3. Tài liệu hóa lỗi và kết quả

Một contract phải giúp consumer phân biệt kết quả nghiệp vụ với lỗi giao thức hoặc hạ tầng.

### 3.1. Ba nhóm kết quả

| Nhóm | Ví dụ | Cách biểu diễn |
|---|---|---|
| Thành công | Đơn hàng đã được chấp nhận. | Response payload theo schema. |
| Từ chối nghiệp vụ | Hết hạn mức, sản phẩm không còn hàng. | Kết quả nghiệp vụ có code ổn định hoặc error theo quy ước đã công bố. |
| Lỗi kỹ thuật | Service unavailable, lỗi kết nối, lỗi không mong đợi. | RSocket ERROR hoặc lỗi transport; có thể kèm mã lỗi đã chuẩn hóa. |

Với trường hợp nghiệp vụ consumer cần xử lý bình thường, thường nên trả một response DTO có trạng thái và mã lỗi rõ ràng. Không dùng exception cho mọi trường hợp từ chối nghiệp vụ nếu điều đó khiến consumer phải phân tích chuỗi message không ổn định.

Lỗi kỹ thuật nên được phân loại đủ để consumer quyết định có thể retry hay cần dừng. Không công bố stack trace, SQL, tên host nội bộ hoặc thông tin xác thực trong error payload.

### 3.2. Error code ổn định

Ví dụ một response nghiệp vụ:

~~~json
{
  "requestId": "req-2026-0042",
  "status": "REJECTED",
  "code": "LIMIT_EXCEEDED",
  "message": "The requested amount exceeds the allowed limit",
  "retryable": false
}
~~~

Mỗi code nên có định nghĩa, điều kiện phát sinh, hành động consumer cần thực hiện và quy tắc retry. Message dành cho con người có thể thay đổi hoặc được bản địa hóa; consumer nên dựa trên code ổn định.

Một danh mục lỗi có thể gồm:

| Code | Ý nghĩa | Retry |
|---|---|---|
| VALIDATION_FAILED | Payload không hợp lệ. | Không; sửa request. |
| NOT_AUTHORIZED | Danh tính không có quyền thực hiện. | Không; xử lý quyền. |
| RESOURCE_NOT_FOUND | Tài nguyên không tồn tại. | Thường không; kiểm tra ID. |
| BUSINESS_RULE_REJECTED | Quy tắc nghiệp vụ từ chối. | Không tự động. |
| TEMPORARY_UNAVAILABLE | Phụ thuộc tạm thời không sẵn sàng. | Có thể, với backoff và giới hạn. |
| REQUEST_TIMEOUT | Không nhận được kết quả trong deadline. | Truy vấn trạng thái trước khi retry thao tác có side effect. |
| INTERNAL_ERROR | Lỗi không mong đợi. | Theo chính sách retry; cần correlation ID để điều tra. |

### 3.3. Timeout và kết quả không xác định

Timeout không chứng minh responder chưa xử lý request. Server có thể đã commit side effect nhưng response chưa đến consumer.

Với thao tác có side effect, contract nên quy định:

- Request ID hoặc idempotency key ổn định.
- Route tra cứu trạng thái nếu consumer có thể mất response.
- Thời hạn lưu trạng thái và thời gian consumer có thể truy vấn.
- Cách retry mà không tạo side effect trùng.
- Cách xử lý trạng thái PROCESSING hoặc UNKNOWN.

Đừng mô tả timeout là một kết quả FAILED chắc chắn nếu server chưa xác nhận trạng thái nghiệp vụ.

## 4. Phân định trách nhiệm của từng bên

Trong một hệ thống messaging, trách nhiệm cần được chia rõ. Không nên để consumer phải đoán quy tắc nội bộ của responder hoặc để responder phụ thuộc vào hành vi không được công bố của consumer.

### 4.1. Requester / Consumer

Requester chịu trách nhiệm:

1. Đọc và tuân thủ phiên bản contract đã công bố.
2. Gửi đúng route, payload schema và metadata bắt buộc.
3. Validate dữ liệu phía client để phát hiện lỗi sớm, nhưng không thay thế validation phía server.
4. Thiết lập deadline/timeout phù hợp với nghiệp vụ.
5. Xử lý response, error, stream completion và cancellation.
6. Chỉ retry khi contract cho phép; giữ nguyên idempotency key cho cùng thao tác logic.
7. Không giả định timeout nghĩa là thao tác chưa xảy ra.
8. Bảo vệ credentials và dữ liệu nhạy cảm trong log.
9. Kiểm thử tương thích với phiên bản responder được hỗ trợ.
10. Thông báo cho service owner khi cần thay đổi contract hoặc phát hiện hành vi khác tài liệu.

Consumer không được tự suy diễn field mới, enum mới hoặc error code chưa được định nghĩa. Nếu gặp giá trị chưa biết, nên có fallback an toàn theo quy tắc tương thích đã thống nhất.

### 4.2. Responder / Provider

Responder chịu trách nhiệm:

1. Công bố route, interaction model, payload và metadata.
2. Validate request ở ranh giới service.
3. Xác thực danh tính và authorize từng thao tác.
4. Thực hiện đúng ngữ nghĩa nghiệp vụ và ranh giới transaction đã công bố.
5. Trả response hoặc error theo schema và quy tắc ổn định.
6. Thực hiện idempotency khi contract cam kết hỗ trợ retry an toàn.
7. Không làm lộ chi tiết nội bộ hoặc dữ liệu nhạy cảm trong response.
8. Duy trì khả năng tương thích trong thời gian hỗ trợ các consumer hiện tại.
9. Cung cấp changelog, ví dụ và hướng dẫn migration.
10. Theo dõi lỗi, latency và mức sử dụng route để phát hiện tác động của thay đổi.

Responder không được âm thầm thay đổi ý nghĩa field, đơn vị, ordering hoặc error semantics mà consumer đang dựa vào.

### 4.3. Service owner / Contract owner

Contract owner chịu trách nhiệm về chất lượng và vòng đời của tài liệu:

- Xác định mục đích và phạm vi API.
- Chỉ định requester/responder và nhóm chịu trách nhiệm.
- Duyệt schema, route, error model và thay đổi tương thích.
- Quản lý version, changelog, deprecation và ngày retirement.
- Duy trì ví dụ có thể kiểm tra và contract tests.
- Phối hợp với các consumer bị ảnh hưởng trước khi thay đổi breaking.
- Xác định kênh hỗ trợ và escalation khi có sự cố.

Contract owner có thể là service team sở hữu responder. Một người phụ trách tài liệu nên được chỉ định để tránh contract không có người cập nhật.

### 4.4. Platform / Operations

Đội platform và operations chịu trách nhiệm về môi trường chạy:

- Cung cấp transport endpoint, DNS, port, certificate và TLS policy.
- Quản lý capacity, connection limits và network timeout.
- Theo dõi kết nối, stream, lỗi transport, latency và saturation.
- Thiết lập cảnh báo và runbook.
- Quản lý rollout, rollback và cấu hình môi trường.
- Hỗ trợ chẩn đoán sự cố xuyên service bằng correlation ID/trace ID.

Đội vận hành không quyết định ý nghĩa nghiệp vụ của payload. Những quyết định này thuộc service owner và domain owner.

### 4.5. Security / Data owner

Nhóm security hoặc data owner xác định:

- Cách xác thực kết nối và danh tính requester.
- Quyền được phép gọi từng route và truy cập từng tenant/resource.
- Metadata nhạy cảm nào được phép truyền.
- Quy tắc mã hóa, retention, audit và redaction.
- Phân loại dữ liệu trong payload.
- Các yêu cầu tuân thủ liên quan đến dữ liệu.

Service owner triển khai các yêu cầu này trong responder; consumer bảo vệ credentials và dữ liệu của mình khi gửi/nhận.

### 4.6. Bảng trách nhiệm tổng hợp

| Công việc | Consumer | Responder owner | Contract owner | Platform/Ops | Security/Data |
|---|---|---|---|---|---|
| Gửi payload hợp lệ | Chịu trách nhiệm | Định nghĩa schema | Duyệt contract | Hỗ trợ công cụ | Định nghĩa data policy |
| Validate và xử lý nghiệp vụ | Tuân thủ response | Chịu trách nhiệm | Duyệt semantics | Theo dõi sức khỏe | Duyệt rule truy cập |
| Route và transport | Dùng endpoint công bố | Công bố route | Duyệt contract | Vận hành endpoint | Duyệt bảo vệ transport |
| Retry/idempotency | Tuân thủ chính sách | Triển khai cam kết | Định nghĩa quy tắc | Theo dõi retry/load | Rà soát rủi ro |
| Versioning/deprecation | Nâng cấp consumer | Hỗ trợ phiên bản | Điều phối và phê duyệt | Hỗ trợ rollout | Rà soát tác động |
| Incident response | Cung cấp correlation ID | Điều tra lỗi service | Điều phối contract issue | Điều tra hạ tầng | Hỗ trợ sự cố bảo mật |

Bảng này là mẫu phân công. Mỗi tổ chức có thể gộp vai trò, nhưng phải chỉ rõ một người hoặc nhóm chịu trách nhiệm cuối cùng cho từng quyết định.

## 5. Ví dụ contract RSocket

Giả sử có API chấp nhận một yêu cầu đặt hàng. Consumer gửi một request và responder trả một response tổng hợp.

### 5.1. Bản mô tả contract

~~~yaml
contract:
  id: order-submission
  version: 1.0.0
  owner: order-service-team
  status: active

transport:
  protocol: rsocket
  transport: tcp
  dataMimeType: application/json
  metadataMimeType: message/x.rsocket.composite-metadata
  tls: required

route:
  name: orders.submit
  interaction: request-response
  requester: checkout-service
  responder: order-service
  request: SubmitOrder
  response: OrderAccepted
  timeout: 3s
  idempotency: required

requestFields:
  - name: requestId
    type: string
    required: true
    description: Stable identifier for this logical submission
  - name: customerId
    type: string
    required: true
    description: Customer identifier
  - name: items
    type: array
    required: true
    description: At least one order item

responseFields:
  - name: orderId
    type: string
    required: true
  - name: status
    type: string
    required: true
    allowedValues: [ACCEPTED, REJECTED]
  - name: acceptedAt
    type: string
    format: date-time
    required: false

errors:
  - code: VALIDATION_FAILED
    retryable: false
  - code: BUSINESS_RULE_REJECTED
    retryable: false
  - code: TEMPORARY_UNAVAILABLE
    retryable: true

responsibilities:
  requester:
    - Validate required fields
    - Preserve requestId across retries
    - Handle timeout and query status when outcome is unknown
  responder:
    - Validate payload and authorize customer
    - Enforce idempotency for requestId
    - Return a response that follows this schema
~~~

Đây là một format YAML minh họa để nhóm lưu trữ contract trong repository. Nó không phải schema chuẩn bắt buộc của RSocket. Tổ chức có thể chọn JSON Schema, Avro, Protobuf hoặc một format nội bộ; điều quan trọng là schema được version hóa và có thể kiểm tra tự động.

### 5.2. Payload ví dụ

Request:

~~~json
{
  "requestId": "checkout-2026-0042",
  "customerId": "customer-101",
  "items": [
    {
      "sku": "BOOK-001",
      "quantity": 2
    }
  ]
}
~~~

Response:

~~~json
{
  "orderId": "order-9001",
  "status": "ACCEPTED",
  "acceptedAt": "2026-11-07T10:30:00Z"
}
~~~

Ví dụ này giả định một request tạo một đơn hàng. Nếu hệ thống cho phép chấp nhận từng item độc lập, response cần có danh sách kết quả item thay vì chỉ một status tổng thể.

### 5.3. DTO và responder trong Spring

DTO dùng chung trong ví dụ được đặt ở ba file riêng trong package `com.example.orders.contract`.

**File `OrderItem.java`:**

~~~java
package com.example.orders.contract;

public record OrderItem(String sku, int quantity) {}
~~~

**File `SubmitOrder.java`:**

~~~java
package com.example.orders.contract;

import java.util.List;

public record SubmitOrder(
    String requestId,
    String customerId,
    List<OrderItem> items
) {}
~~~

**File `OrderAccepted.java`:**

~~~java
package com.example.orders.contract;

public record OrderAccepted(
    String orderId,
    String status,
    String acceptedAt
) {}
~~~

Responder:

~~~java
package com.example.orders;

import com.example.orders.contract.OrderAccepted;
import com.example.orders.contract.SubmitOrder;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;
import reactor.core.publisher.Mono;

@Controller
public class OrderRSocketController {

    private final OrderApplicationService service;

    public OrderRSocketController(OrderApplicationService service) {
        this.service = service;
    }

    @MessageMapping("orders.submit")
    public Mono<OrderAccepted> submit(
        @Payload SubmitOrder command
    ) {
        return service.submitIdempotently(command);
    }
}
~~~

OrderApplicationService là service nghiệp vụ do ứng dụng triển khai. Contract yêu cầu service bảo vệ requestId khỏi việc tạo đơn hàng trùng và chỉ trả OrderAccepted khi trạng thái chấp nhận đã được lưu bền vững.

### 5.4. Requester trong Spring

~~~java
package com.example.checkout;

import com.example.orders.contract.OrderAccepted;
import com.example.orders.contract.SubmitOrder;
import org.springframework.messaging.rsocket.RSocketRequester;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class OrderClient {

    private final RSocketRequester requester;

    public OrderClient(RSocketRequester.Builder builder) {
        this.requester = builder.tcp("order-service", 7000);
    }

    public Mono<OrderAccepted> submit(SubmitOrder command) {
        return requester
            .route("orders.submit")
            .data(command)
            .retrieveMono(OrderAccepted.class);
    }
}
~~~

Ví dụ giả định builder đã được Spring Boot cấu hình và môi trường có thể phân giải host order-service. Consumer vẫn cần xử lý timeout, lỗi transport và kết quả không xác định theo contract. Trong production, cấu hình timeout, authentication metadata và lifecycle disposal theo chính sách của ứng dụng.

## 6. Versioning và thay đổi tương thích

Contract tồn tại lâu hơn một lần triển khai. Service owner cần quy tắc để consumer có thể nâng cấp có kế hoạch.

### 6.1. Thay đổi thường tương thích

Các thay đổi sau thường có thể tương thích nếu serializer và consumer tuân theo quy tắc bỏ qua field không biết:

- Thêm một field optional có default an toàn.
- Thêm route mới mà không thay đổi route cũ.
- Thêm error code mới nếu consumer có fallback cho code chưa biết.
- Thêm metadata optional mà responder không yêu cầu từ consumer cũ.

Dù vậy, phải kiểm tra serializer cụ thể. Một consumer strict có thể từ chối field mới hoặc enum mới. Không mặc định mọi consumer đều bỏ qua dữ liệu chưa biết.

### 6.2. Thay đổi có nguy cơ breaking

Các thay đổi sau thường cần major version hoặc kế hoạch migration:

- Đổi tên hoặc xóa route.
- Đổi kiểu dữ liệu, đơn vị hoặc ý nghĩa field.
- Chuyển field optional thành required.
- Thay đổi semantics từ Request-Response sang stream hoặc ngược lại.
- Thay đổi thứ tự, cardinality hoặc điều kiện kết thúc stream.
- Đổi error code hoặc biến một lỗi retryable thành non-retryable mà không thông báo.
- Thay đổi quy tắc idempotency, authorization hoặc timeout theo cách làm consumer cũ không còn đúng.

Không chỉ nhìn schema để đánh giá compatibility. Thay đổi semantics cũng là thay đổi contract, ngay cả khi JSON vẫn giống nhau.

### 6.3. Quy trình deprecation

Một quy trình thực tế:

1. Công bố route hoặc version mới cùng lý do thay đổi.
2. Cập nhật tài liệu, ví dụ và contract tests.
3. Thông báo consumer bị ảnh hưởng và thời gian migration.
4. Chạy song song version cũ và mới trong thời hạn đã thống nhất.
5. Theo dõi traffic của version cũ.
6. Xác nhận consumer đã chuyển đổi hoặc có kế hoạch ngoại lệ.
7. Ngừng hỗ trợ version cũ vào ngày công bố.
8. Cập nhật changelog và trạng thái contract thành retired.

Không xóa route cũ chỉ vì consumer mới đã triển khai. Phải dựa vào dữ liệu sử dụng hoặc xác nhận của các consumer có trách nhiệm.

### 6.4. Semantic versioning cho contract

Có thể dùng quy ước:

- MAJOR: thay đổi breaking.
- MINOR: thêm khả năng tương thích.
- PATCH: sửa tài liệu, ví dụ hoặc làm rõ mà không đổi semantics.

Đây là chính sách versioning của tổ chức, không phải yêu cầu của giao thức RSocket. Hãy công bố cách áp dụng rõ ràng trong repository.

## 7. Bảo mật và quyền truy cập trong contract

Contract phải mô tả ranh giới bảo mật đủ để consumer tích hợp đúng:

- Transport có bắt buộc TLS hay không.
- Cách xác thực kết nối và cách gửi credentials.
- Route nào yêu cầu quyền nào.
- Tenant hoặc resource được xác định từ đâu.
- Metadata nào được phép gửi và metadata nào không được tin cậy.
- Quy tắc che dữ liệu trong log và trace.
- Thời gian hiệu lực và cách xoay vòng credentials.

RSocket là giao thức hai chiều. Một phía có thể khởi tạo request và phía còn lại cũng có thể gửi request trên cùng kết nối. Vì vậy, đừng mặc định mọi quyền chỉ áp dụng theo một chiều. Contract cần nói rõ principal nào được phép gọi route nào ở mỗi hướng.

Authentication xác định danh tính; authorization quyết định danh tính đó được phép thực hiện hành động nào. Responder phải kiểm tra quyền ở server ngay cả khi consumer đã ẩn nút hoặc kiểm tra quyền ở UI.

Không đưa token thật vào ví dụ. Dùng placeholder như TOKEN_FROM_SECRET_STORE và không ghi token vào log.

## 8. Observability và vận hành

Một contract có thể dùng được trong production cần quy định cách truy vết request.

### 8.1. Correlation và tracing

Mỗi request nên có correlation ID hoặc trace context để nối log giữa consumer, responder và các dịch vụ downstream. Ghi rõ:

- Metadata key hoặc chuẩn tracing được dùng.
- Bên nào tạo trace ID.
- Cách truyền context qua các lời gọi downstream.
- Cách trả correlation ID khi có lỗi.
- Quy tắc log và redaction.

Không dùng correlation ID thay cho request ID hoặc idempotency key. Correlation ID phục vụ quan sát; idempotency key phục vụ nhận diện thao tác logic.

### 8.2. Metrics và SLO

Service owner và platform team nên thống nhất:

- Request rate theo route.
- Tỷ lệ success, business rejection và technical error.
- Latency p50, p95, p99.
- Số connection đang mở và số stream đang hoạt động.
- Số lần reconnect, resume và retry.
- Số request timeout hoặc bị cancel.
- Kích thước payload và tỷ lệ payload vượt ngưỡng.

SLO cần định nghĩa phạm vi đo, chẳng hạn tỷ lệ Request-Response hoàn thành trong deadline, không chỉ là uptime của TCP connection. Một connection mở không có nghĩa route nghiệp vụ đang hoạt động tốt.

### 8.3. Runbook

Tài liệu vận hành nên nêu:

1. Dashboard và metric cần kiểm tra.
2. Log field hoặc trace ID cần tìm.
3. Các lỗi phổ biến và cách phân biệt lỗi consumer, responder, transport và dependency.
4. Cách kiểm tra route đang được gọi và version đang chạy.
5. Cách xử lý retry storm hoặc reconnect storm.
6. Kênh escalation và nhóm sở hữu service.
7. Quy trình rollback hoặc tắt một route nếu có sự cố.

## 9. Kiểm thử hợp đồng

Tài liệu chỉ đáng tin khi có kiểm thử giữ cho implementation phù hợp với nó.

### 9.1. Schema tests

Kiểm tra:

- Payload hợp lệ được deserialize.
- Payload thiếu field required bị từ chối.
- Kiểu dữ liệu sai được xử lý theo quy ước.
- Field optional có default đúng.
- Enum hoặc error code mới không làm consumer crash ngoài dự kiến.
- Payload lớn vượt giới hạn được xử lý có kiểm soát.

### 9.2. Provider contract tests

Test responder phải xác nhận:

- Route đúng được đăng ký.
- Request hợp lệ trả response đúng schema.
- Validation và authorization được thực hiện.
- Error code và retry semantics đúng.
- Idempotency hoạt động khi gửi cùng request nhiều lần.
- Stream phát đúng kiểu payload, ordering và terminal signal.
- Cancellation và timeout không làm mất kết quả đã commit.

### 9.3. Consumer contract tests

Test consumer phải xác nhận:

- Gửi đúng route và payload.
- Đọc được response theo schema.
- Xử lý unknown field hoặc unknown code theo fallback.
- Không retry lỗi không thể phục hồi.
- Truy vấn trạng thái khi kết quả không xác định.
- Hủy stream và giải phóng resource đúng cách.

### 9.4. Integration tests với RSocketRequester

Một integration test có thể khởi chạy server và dùng requester thật để gọi route. Ví dụ phần kiểm tra response:

~~~java
StepVerifier.create(
    requester
        .route("orders.submit")
        .data(command)
        .retrieveMono(OrderAccepted.class)
)
.expectNextMatches(response ->
    response.orderId() != null
        && response.status().equals("ACCEPTED")
)
.verifyComplete();
~~~

Đoạn test giả định có RSocket server đang chạy, command hợp lệ và test đã cấu hình Reactor Test. Kiểm thử nên xác nhận cả route, codec, metadata và error path; chỉ gọi method Java trực tiếp sẽ không kiểm tra được phần mapping và serialization của RSocket.

## 10. Mẫu checklist cho mỗi route

Trước khi công bố một route, điền các trường sau:

- [ ] Route name và mục đích nghiệp vụ.
- [ ] Requester, responder và contract owner.
- [ ] Interaction model: Request-Response, Request-Stream, Channel hoặc Fire-and-Forget.
- [ ] Request schema và response schema.
- [ ] Data MIME type, metadata MIME type và codec.
- [ ] Metadata required/optional và cách xác thực.
- [ ] Error codes, business rejection và retryability.
- [ ] Timeout, ordering, cardinality và stream termination.
- [ ] Idempotency, operation status và unknown outcome nếu có side effect.
- [ ] Security, authorization và data classification.
- [ ] Payload limits, rate/capacity constraints và backpressure.
- [ ] Version, compatibility, changelog và deprecation policy.
- [ ] Examples, schema tests, provider tests và consumer tests.
- [ ] Metrics, tracing, dashboard, runbook và support contact.

## 11. Cấu trúc repository đề xuất

Có thể lưu contract gần service sở hữu responder:

~~~text
order-service/
  contracts/
    orders-v1/
      contract.yaml
      schemas/
        submit-order.json
        order-accepted.json
        order-error.json
      examples/
        submit-order.request.json
        order-accepted.response.json
      CHANGELOG.md
      README.md
  src/
    main/
    test/
~~~

Ý nghĩa:

- contract.yaml mô tả route, interaction, metadata và trách nhiệm.
- schemas chứa schema máy đọc được.
- examples giúp consumer thử tích hợp nhanh.
- CHANGELOG ghi rõ thay đổi giữa các phiên bản.
- README giải thích cách kết nối, authentication, test và liên hệ owner.
- Contract tests trong source bảo đảm implementation không lệch tài liệu.

Nếu nhiều service dùng chung một contract repository, cần chỉ rõ owner, quy trình review và cách đồng bộ version với từng service release. Không để nhiều bản sao không có nguồn chuẩn.

## 12. Những lỗi tài liệu thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Chỉ mô tả DTO, bỏ qua route | Consumer không biết gọi ở đâu. | Ghi route và interaction model cho từng message. |
| Không nêu ai sở hữu contract | Thay đổi không có người duyệt hoặc hỗ trợ. | Chỉ định service owner và contract owner. |
| Bỏ qua metadata | Consumer thiếu auth, trace hoặc tenant context. | Tài liệu hóa metadata, encoding và validation. |
| Không mô tả error semantics | Consumer retry sai hoặc bỏ qua lỗi. | Công bố error code, retryability và hành động. |
| Chỉ dùng ví dụ thành công | Không thể tích hợp error path và edge case. | Có ví dụ validation, rejection, timeout và stream error. |
| Không quy định compatibility | Thay đổi nhỏ cũng có thể làm consumer cũ hỏng. | Có versioning, changelog và deprecation policy. |
| Đưa implementation nội bộ vào contract | Consumer phụ thuộc vào chi tiết dễ thay đổi. | Chỉ công bố hành vi và schema ở ranh giới service. |
| Không có test contract | Tài liệu và code dần lệch nhau. | Tự động kiểm tra schema, route và response. |
| Dùng correlation ID như idempotency key | Không ngăn side effect trùng. | Dùng hai định danh với mục đích riêng. |
| Không có runbook hoặc support contact | Sự cố kéo dài và khó chuyển đúng nhóm. | Gắn dashboard, owner và quy trình escalation. |

## Kết luận

Một message contract tốt phải đủ rõ để consumer biết cách gửi request, hiểu response, xử lý lỗi và nâng cấp an toàn. Nó cũng phải chỉ ra responder chịu trách nhiệm gì, ai duyệt thay đổi, ai vận hành transport và ai hỗ trợ khi có sự cố.

Với Spring RSocket, hãy tài liệu hóa route và interaction model cùng payload, metadata, MIME type, error semantics, timeout, cancellation, idempotency và versioning. Kết hợp contract với schema, ví dụ và automated tests để tài liệu luôn phản ánh hành vi thực tế.

## Tài liệu tham khảo

- [Spring Framework Reference — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): RSocketRequester, annotated responders, route mapping và metadata.
- [Spring Boot Reference — RSocket](https://docs.spring.io/spring-boot/reference/messaging/rsocket.html): auto-configuration, server transport và requester builder.
- [RSocket Protocol](https://rsocket.io/about/protocol/): interaction models, setup, metadata, error và stream lifecycle.
- [Project Reactor Reference](https://projectreactor.io/docs/core/release/reference/): Mono, Flux, backpressure, cancellation và retry.
- [JSON Schema](https://json-schema.org/): mô tả và kiểm tra cấu trúc payload JSON.
