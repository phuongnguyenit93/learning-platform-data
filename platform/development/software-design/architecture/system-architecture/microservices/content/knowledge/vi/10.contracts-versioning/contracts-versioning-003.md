# OpenAPI, Protocol Buffers và lược đồ sự kiện

> **Chủ đề:** Software Design Architecture → System Architecture → Microservices  
> **Nhóm kiến thức:** Hợp đồng và phiên bản

## 1. Vì sao microservices cần hợp đồng giao tiếp rõ ràng?

Khi hai module nằm trong cùng tiến trình, trình biên dịch có thể phát hiện ngay nhiều lỗi khi đổi tên phương thức hoặc đổi kiểu dữ liệu. Khi chúng chạy thành những microservice riêng, các bên có thể được triển khai vào thời điểm khác nhau và giao tiếp qua mạng. Lỗi hợp đồng có thể chỉ xuất hiện tại runtime: client gửi trường mà server không hiểu, server trả một giá trị enum mới mà client chưa xử lý, hoặc consumer không giải mã được thông điệp đã được lưu trên broker.

**Hợp đồng giao tiếp (communication contract)** là tập cam kết công khai giữa bên cung cấp và bên sử dụng, bao gồm cả cấu trúc lẫn ý nghĩa: thao tác hoặc sự kiện là gì, dữ liệu nào được phép gửi/nhận, trường nào bắt buộc, khi nào thao tác được xem là thành công, các trường hợp lỗi, và một thay đổi sẽ được đưa vào hệ thống ra sao.

Một hợp đồng tốt trả lời ít nhất bốn câu hỏi:

1. **Cú pháp:** Bên gửi và bên nhận biểu diễn thông điệp bằng dạng nào, trường nào có kiểu dữ liệu gì?
2. **Ngữ nghĩa:** `CONFIRMED`, `authorizedAmount`, `OrderPlaced` thực sự có nghĩa gì trong nghiệp vụ?
3. **Hành vi:** Timeout, retry, quyền truy cập, idempotency, thứ tự và trạng thái chuyển tiếp được xử lý thế nào?
4. **Tương thích:** Consumer cũ có làm việc được với producer/server mới không, và ngược lại?

OpenAPI, Protocol Buffers và các lược đồ sự kiện đều giúp **cụ thể hóa một phần hợp đồng**, nhưng chúng phục vụ những dạng giao tiếp khác nhau. Chúng không thay thế thiết kế bounded context, quyền sở hữu dữ liệu hay quy tắc nghiệp vụ.

## 2. Phân biệt ba nhóm công cụ

| Công cụ / dạng mô tả | Đối tượng mô tả chính | Thường dùng ở đâu | Những điều không tự bảo đảm |
| --- | --- | --- | --- |
| **OpenAPI** | Các thao tác và dữ liệu của một HTTP API: path, method, request, response, status code, security scheme | REST/HTTP API công khai hoặc nội bộ | Server triển khai đúng, idempotency, độ sẵn sàng, tính đúng đắn nghiệp vụ |
| **Protocol Buffers (Protobuf)** | Schema dữ liệu có kiểu, ID trường và quy tắc mã hóa; thường dùng làm hợp đồng message của gRPC | RPC, nội bộ service-to-service, event payload, lưu trữ/trao đổi dữ liệu | Bản thân Protobuf không tạo RPC, routing, authorization hoặc bảo đảm xử lý message đúng một lần |
| **Lược đồ sự kiện (event schema)** | Dạng và ý nghĩa dữ liệu của một event được phát/nhận | Broker, pub/sub, stream, webhook, event-driven integration | Event đã commit đúng nghiệp vụ, không mất/trùng/thứ tự sai, consumer thật sự phản ứng đúng |

Một event schema có thể viết bằng JSON Schema, Avro hoặc Protobuf. Một API dùng HTTP có thể nhận/trả JSON và mô tả bằng OpenAPI, trong khi một API gRPC thường có định nghĩa `.proto` chứa cả service/RPC method và message type. **Không nên hiểu OpenAPI, Protobuf và event schema là ba công nghệ loại trừ nhau.**

Ví dụ cùng một năng lực Payment có thể:

- Công bố HTTP endpoint tạo yêu cầu thanh toán bằng **OpenAPI**.
- Dùng **gRPC + Protobuf** cho một truy vấn nội bộ có yêu cầu RPC rõ ràng.
- Phát event `PaymentAuthorized` lên broker, với **JSON Schema hoặc Protobuf** để consumer giải mã và xác minh payload.

Ba hợp đồng này liên quan cùng domain nhưng có thể có vòng đời, đối tượng sử dụng và chính sách phiên bản khác nhau.

## 3. Contract không đồng nghĩa với entity hay database schema

Giả sử PaymentService có class nội bộ `PaymentJpaEntity` gồm cột `db_id`, `provider_raw_response`, `retry_count`, `risk_signal` và `payment_state_code`.

Không nên tự động lấy đối tượng này làm request DTO, Protobuf message hoặc event công khai. Những trường đó có thể là chi tiết lưu trữ, bí mật của đối tác hoặc trạng thái kỹ thuật mà consumer không được phụ thuộc.

Hợp đồng công khai nên diễn đạt khái niệm nghiệp vụ ổn định:

| Nội bộ Payment | Contract có thể công bố | Lý do |
| --- | --- | --- |
| `db_id` (khóa bảng) | `paymentId` (định danh nghiệp vụ) | Cho phép thay đổi cách lưu trữ |
| `payment_state_code=7` | `status=AUTHORIZED` | Ý nghĩa được đặt tên và giải thích |
| `provider_raw_response` | `declineReason` hoặc `providerReference` khi thật sự được phép | Tránh rò rỉ cấu trúc và bí mật đối tác |
| `retry_count` | Thường không có trong contract nghiệp vụ | Không buộc consumer hiểu chiến lược retry nội bộ |
| `capture_time_db` | `capturedAt` theo chuẩn thời gian đã công bố | Consumer hiểu mốc thời gian nghiệp vụ |

Với event, không phải mọi thay đổi cột đều là một sự kiện doanh nghiệp. `PaymentAuthorized` biểu diễn một sự thật quan trọng; `PaymentRowUpdated` có thể chỉ mô tả biến động kỹ thuật. Nếu muốn dùng CDC để đồng bộ dữ liệu, cần phân biệt **data change feed** với **domain/integration event**.

## 4. OpenAPI: mô tả hợp đồng HTTP

**OpenAPI Specification** cung cấp cấu trúc mô tả các HTTP operation và dữ liệu mà chúng trao đổi. Tài liệu thường được viết bằng YAML hoặc JSON, gồm `openapi`, `info`, `servers`, `paths`, `components` và các schema tham chiếu qua `$ref`.

Ví dụ giả định PaymentService nhận lệnh bắt đầu ủy quyền thanh toán. Hợp đồng có thể được mô tả như sau:

```yaml
openapi: 3.1.0
info:
  title: Payment API
  version: 1.0.0
servers:
  - url: https://payments.example.test
paths:
  /payments/authorizations:
    post:
      operationId: createPaymentAuthorization
      summary: Tiếp nhận yêu cầu ủy quyền thanh toán
      security:
        - bearerAuth: []
      parameters:
        - in: header
          name: Idempotency-Key
          required: true
          schema:
            type: string
            minLength: 1
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/AuthorizationRequest'
      responses:
        '202':
          description: Đã tiếp nhận; kết quả có thể chưa hoàn tất
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/AuthorizationAccepted'
        '400':
          description: Yêu cầu không hợp lệ
        '401':
          description: Chưa xác thực
        '409':
          description: Xung đột trạng thái hoặc khóa idempotency
        '429':
          description: Bị giới hạn lưu lượng
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
  schemas:
    AuthorizationRequest:
      type: object
      required: [orderId, amountMinor, currency]
      properties:
        orderId:
          type: string
          minLength: 1
        amountMinor:
          type: integer
          minimum: 0
          description: Số tiền theo đơn vị nhỏ nhất của tiền tệ
        currency:
          type: string
          description: Mã tiền tệ theo quy ước của hệ thống
    AuthorizationAccepted:
      type: object
      required: [paymentId, status]
      properties:
        paymentId:
          type: string
        status:
          type: string
          enum: [PENDING]
```

Điều quan trọng trong ví dụ không chỉ là syntax:

- HTTP `202 Accepted` ở hợp đồng này có nghĩa **đã tiếp nhận yêu cầu**, không đồng nghĩa ngân hàng đã ủy quyền thành công.
- `Idempotency-Key` yêu cầu phía server có hành vi chống tạo giao dịch lặp theo một phạm vi và thời hạn lưu khóa được công bố.
- `amountMinor` phải có quy ước tiền tệ rõ ràng; không nên để từng client tự suy đoán cách làm tròn.
- Nếu client cần kết quả cuối cùng, contract phải có cách đọc trạng thái hoặc nhận thông báo. Endpoint tạo yêu cầu không thể tự hứa về thời điểm xác nhận.
- Mục `security` mô tả cơ chế dự kiến; quyền truy cập, scope và kiểm tra thực tế vẫn phải được triển khai ở server.

Đây là **một ví dụ OpenAPI 3.1**. Cú pháp `type`, `required`, `enum` giúp công cụ kiểm tra cấu trúc; chính sách idempotency, nghĩa của PENDING và quy trình đối soát vẫn cần tài liệu và kiểm thử hành vi.

### 4.1. OpenAPI dùng để làm gì?

Từ một tài liệu OpenAPI, nhóm phát triển có thể:

1. Hiển thị tài liệu API có thể điều hướng và thử request.
2. Sinh hoặc cập nhật client SDK và một phần interface/server stub tùy công cụ.
3. Kiểm tra request/response trong một số bài kiểm thử.
4. So sánh phiên bản schema để phát hiện thay đổi có nguy cơ phá vỡ client.
5. Thảo luận contract trước khi triển khai và xác định trách nhiệm giữa các nhóm.

**Sinh code không bảo đảm đúng nghĩa nghiệp vụ.** Nếu OpenAPI nói 202 khi tiếp nhận nhưng server thật luôn trả 200, hoặc implementation vẫn tạo thanh toán trùng, generated client không thể tự sửa lỗi đó.

### 4.2. Những phần contract HTTP dễ bị bỏ quên

- Mã trạng thái khi dữ liệu không tồn tại, request sai, quyền không đủ, xung đột hoặc quá tải.
- Cách phân biệt lỗi kỹ thuật với lỗi nghiệp vụ; có `errorCode` ổn định hay không.
- Query parameter, phân trang, sorting, filtering và giới hạn số phần tử.
- Deadline, retry và rate limit, bao gồm ý nghĩa `Retry-After` khi có.
- Idempotency của operation có side effect; GET được thiết kế an toàn không đồng nghĩa mọi cách triển khai thực tế đều đúng.
- Versioning và chính sách đổi trường bắt buộc, enum, định dạng thời gian, số tiền.
- Bảo mật và phân quyền theo đối tượng, không chỉ có bearer token.
- Nghĩa của việc nhận HTTP 202, 200, 201 hoặc 204.
- Quy ước trường `null`, trường vắng mặt và giá trị mặc định.

Một schema kiểm tra được JSON hợp lệ vẫn có thể bỏ sót những khác biệt quan trọng giữa “thanh toán đang chờ” và “thanh toán đã hoàn tất”.

## 5. Protocol Buffers: hợp đồng có kiểu và ID trường ổn định

**Protocol Buffers** là định dạng mô tả cấu trúc dữ liệu và cơ chế mã hóa gọn, thường xuất hiện cùng gRPC. File `.proto` định nghĩa message, enum và có thể định nghĩa service/RPC method. Công cụ `protoc` và các plugin sinh mã cho những ngôn ngữ được hỗ trợ.

Ví dụ một hợp đồng truy vấn trạng thái PaymentService:

```protobuf
syntax = "proto3";

package payments.v1;

option java_package = "com.example.contracts.payments.v1";
option java_multiple_files = true;

service PaymentQuery {
  rpc GetPayment (GetPaymentRequest)
      returns (GetPaymentResponse);
}

message GetPaymentRequest {
  string payment_id = 1;
}

message GetPaymentResponse {
  string payment_id = 1;
  PaymentStatus status = 2;
  optional string authorized_at = 3;

  // Các tag/tên này từng được sử dụng và không được dùng lại.
  reserved 9, 10;
  reserved "legacy_customer_email";
}

enum PaymentStatus {
  PAYMENT_STATUS_UNSPECIFIED = 0;
  PAYMENT_STATUS_PENDING = 1;
  PAYMENT_STATUS_AUTHORIZED = 2;
  PAYMENT_STATUS_DECLINED = 3;
}
```

File này nêu rõ hình dạng request, response, service method và tên kiểu. Khi dùng gRPC, phần `service PaymentQuery` cung cấp định nghĩa RPC; khi dùng Protobuf như payload của message broker, ứng dụng có thể chỉ sử dụng phần `message` mà không hề dùng gRPC.

**Phân biệt:**

- `Protobuf schema`: định nghĩa cấu trúc và cách mã hóa dữ liệu.
- `gRPC`: framework RPC sử dụng hợp đồng method và message, thường qua HTTP/2, nhưng có thể hoạt động với cấu hình transport của môi trường triển khai.
- `Service discovery`, TLS, authentication, deadline, retry: các vấn đề triển khai/vận hành nằm ngoài bản thân schema `.proto`.

### 5.1. Vì sao field number rất quan trọng?

Trong wire format của Protobuf, mỗi field được đánh dấu bởi **số field** và thông tin kiểu mã hóa. Tên `payment_id` giúp code dễ đọc, nhưng khi dữ liệu nhị phân được giải mã, số `1` mới là định danh quan trọng.

Ví dụ:

```protobuf
message PaymentResponse {
  string payment_id = 1;
  string status = 2;
}
```

Nếu đổi tên `payment_id` thành `payment_reference` nhưng giữ field number và wire type tương thích, khả năng đọc dữ liệu nhị phân có thể vẫn giữ được, dù tên accessor trong generated code hoặc JSON mapping có thể thay đổi và phá source compatibility. Ngược lại, nếu đổi field number của một trường đang được sử dụng, consumer cũ có thể không còn giải mã đúng ý nghĩa đó.

**Không tái sử dụng field number đã xóa cho một nghĩa khác.** Dùng `reserved` để bảo vệ các tag và tên cũ đã ngừng sử dụng. Những thay đổi wire type không tương thích hoặc tái diễn giải cùng tag sang nghĩa khác cần được coi là breaking change.

### 5.2. Proto3 và sự hiện diện của trường

Trong Proto3, nhiều trường scalar bình thường có giá trị mặc định khi chưa được gửi. Ví dụ `int32 quantity = 4` có thể trả về `0` khi dữ liệu vắng mặt theo cách truy cập thông thường. Nếu nghiệp vụ phải phân biệt “không được cung cấp” với “được cung cấp giá trị 0”, cần dùng cơ chế presence phù hợp như `optional` khi được công cụ hỗ trợ, wrapper hoặc thiết kế message khác.

Ví dụ `optional string authorized_at = 3` thể hiện việc thời gian ủy quyền có thể chưa có. Không nên tự diễn giải chuỗi rỗng là “đã ủy quyền lúc thời gian rỗng”.

### 5.3. Enum nên có trạng thái mặc định rõ ràng

Trong Proto3, enum phải có một phần tử số 0. Dùng `PAYMENT_STATUS_UNSPECIFIED = 0` giúp diễn đạt trường hợp chưa được gán hoặc chưa biết. Không nên đặt `AUTHORIZED = 0`, vì một trường bị thiếu có thể bị hiểu nhầm là thành công.

Consumer cũng phải có hành vi khi gặp giá trị enum mới chưa được biết, chẳng hạn hiển thị trạng thái không hỗ trợ hoặc từ chối quyết định nghiệp vụ nhạy cảm. Không chuyển một giá trị lạ thành `AUTHORIZED` chỉ để tránh lỗi parse.

### 5.4. Giới hạn của tính tương thích Protobuf

Protobuf có thể giữ tương thích nhị phân ở nhiều thay đổi thêm trường, nhưng **tương thích wire không đồng nghĩa tương thích hành vi**. Nếu producer đổi nghĩa `amount_minor` từ “tiền đã thu” sang “tiền dự định thu”, consumer vẫn giải mã được nhưng có thể ghi nhận doanh thu sai.

Các dạng tương thích cần kiểm tra riêng:

1. **Wire compatibility:** dữ liệu nhị phân cũ/mới giải mã được.
2. **Source compatibility:** client code sinh từ schema mới/cũ có biên dịch được không?
3. **JSON interoperability:** khi serialize Protobuf sang JSON, tên trường và cách biểu diễn có còn tương thích?
4. **Semantic compatibility:** giá trị sau giải mã vẫn mang cùng ý nghĩa nghiệp vụ không?
5. **Operational compatibility:** deadline, lỗi, quyền và thứ tự deploy có phù hợp không?

## 6. Lược đồ sự kiện: hợp đồng bất đồng bộ

**Event** là một thông điệp báo rằng một sự thật có ý nghĩa với nghiệp vụ đã xảy ra. Thường dùng tên ở thì quá khứ như `PaymentAuthorized`, `OrderConfirmed`, `ShipmentDispatched`. Producer sở hữu ý nghĩa sự kiện; consumer phản ứng theo trách nhiệm của mình.

Ví dụ event từ PaymentService:

```json
{
  "eventId": "8c40e2ca-4b69-45f4-9cc2-34028f3377b5",
  "eventType": "payment.authorized",
  "eventVersion": 1,
  "occurredAt": "2026-11-11T09:00:00Z",
  "producer": "payments",
  "aggregateId": "pay-8042",
  "correlationId": "checkout-8042",
  "data": {
    "paymentId": "pay-8042",
    "orderId": "ord-8042",
    "authorizedAmountMinor": 154000,
    "currency": "VND"
  }
}
```

Các giá trị trong ví dụ là giả định. `eventVersion` thể hiện phiên bản hợp đồng thông điệp, **khác** với phiên bản trạng thái aggregate hoặc số lần một transaction đã đổi trạng thái.

Một JSON Schema giản lược cho event này:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://schemas.example.test/payment-authorized/v1",
  "type": "object",
  "required": [
    "eventId", "eventType", "eventVersion",
    "occurredAt", "aggregateId", "data"
  ],
  "properties": {
    "eventId": { "type": "string", "minLength": 1 },
    "eventType": { "const": "payment.authorized" },
    "eventVersion": { "const": 1 },
    "occurredAt": { "type": "string", "format": "date-time" },
    "producer": { "type": "string" },
    "aggregateId": { "type": "string", "minLength": 1 },
    "correlationId": { "type": "string" },
    "data": {
      "type": "object",
      "required": [
        "paymentId", "orderId",
        "authorizedAmountMinor", "currency"
      ],
      "properties": {
        "paymentId": { "type": "string" },
        "orderId": { "type": "string" },
        "authorizedAmountMinor": {
          "type": "integer", "minimum": 0
        },
        "currency": { "type": "string" }
      }
    }
  }
}
```

Ví dụ schema cố ý không đóng mọi object bằng `additionalProperties: false`; nếu consumer buộc từ chối trường bổ sung chưa biết, một thay đổi thêm trường có thể phá khả năng đọc của consumer cũ. **Chính sách xử lý unknown fields cần được quy định rõ**, không phụ thuộc vào việc một ví dụ JSON có ít hay nhiều trường.

Lưu ý từ khóa `format: date-time` trong JSON Schema không bảo đảm mọi công cụ validator sẽ từ chối ngày giờ sai nếu chưa bật chế độ kiểm tra format phù hợp. Contract tests nên xác minh quy ước thực tế và timezone.

### 6.1. Event schema không chỉ là payload JSON

Một hợp đồng event hoàn chỉnh còn cần:

| Thành phần | Câu hỏi cần trả lời |
| --- | --- |
| Tên và semantic | Sự thật nào đã xảy ra? Điều kiện phát cụ thể là gì? |
| Producer owner | Service nào là nguồn có thẩm quyền công bố? |
| Trigger | Event phát sau bước commit nào, khi nghiệp vụ ở trạng thái nào? |
| Topic/route | Consumer đăng ký qua kênh gì? Quyền truy cập thế nào? |
| Schema | Payload và metadata có kiểu, trường bắt buộc, quy ước đơn vị |
| Delivery | At-most-once, at-least-once hoặc bảo đảm cụ thể của nền tảng |
| Duplicate | Consumer nhận diện lặp theo khóa nào? |
| Ordering | Thứ tự được đảm bảo theo key/partition/aggregate nào? |
| Retention/replay | Event được giữ bao lâu, xử lý phát lại ra sao? |
| Failure | Retry, backoff, dead-letter, đối soát và poison message |
| Evolution | Consumer đọc event v1/v2 và các bản lịch sử thế nào? |

JSON Schema, Avro và Protobuf giúp mô tả **dạng dữ liệu**. Những câu hỏi về trigger, quyền sở hữu, giao nhận và ngữ nghĩa phải được bổ sung trong tài liệu thiết kế hoặc công cụ mô tả bất đồng bộ.

### 6.2. AsyncAPI và schema payload

**AsyncAPI** là một dạng đặc tả để mô tả giao diện giao tiếp theo thông điệp: kênh, message, operation, binding của giao thức và các schema liên quan. Nó có thể tham chiếu schema payload ở JSON Schema, Avro hoặc Protobuf tùy cách tích hợp và công cụ.

- OpenAPI thường tập trung vào các **HTTP operation**.
- AsyncAPI giúp mô tả những **message-driven interfaces**.
- Schema payload kiểm tra **cấu trúc của một message**.

Có tài liệu AsyncAPI không tự biến một consumer thành idempotent; có broker không tự làm event trở thành đúng nghĩa nghiệp vụ. Cần coi đặc tả, triển khai và kiểm thử như ba phần bổ sung cho nhau.

## 7. Chọn kiểu hợp đồng theo kiểu tương tác

Một hành trình đặt hàng có thể chứa những tương tác khác nhau:

    Client
      |
      | POST /orders (HTTP, OpenAPI)
      v
    Ordering
      |
      | GetPaymentStatus (gRPC/Protobuf hoặc HTTP)
      v
    Payment
      |
      | PaymentAuthorized (event schema)
      v
    Broker -----> Accounting / Notification / Analytics

Sơ đồ là ví dụ để phân biệt vai trò, không phải một workflow bắt buộc. Trong thực tế Ordering có thể gửi command đến Payment, còn Payment phát event khi hoàn tất. Một API HTTP cũng có thể trả 202 và xử lý bất đồng bộ ở phía sau.

| Nhu cầu | Hợp đồng gợi ý | Điều cần ưu tiên |
| --- | --- | --- |
| Người dùng đọc chi tiết tài nguyên qua HTTP | OpenAPI | Path/method, response, lỗi, auth, phân trang |
| Nội bộ service gọi RPC theo interface có kiểu | Protobuf + gRPC hoặc HTTP theo nhu cầu | Method signature, deadline, status, compatibility |
| Phát sự kiện đã xảy ra tới nhiều consumer | Event schema, có thể dùng JSON Schema/Avro/Protobuf | Ý nghĩa event, delivery, replay, schema evolution |
| Gửi command tới worker nền | Message contract, queue semantics | Người chịu trách nhiệm, kết quả và retry |
| Đồng bộ dữ liệu đọc giữa bounded context | Event-carried state/projection contract | Độ mới, sự kiện cũ/trùng, xây lại projection |

Không có quy tắc “microservices bắt buộc dùng gRPC” hoặc “event-driven bắt buộc dùng một sản phẩm broker”. Giao thức chỉ hợp lý khi đáp ứng ranh giới nghiệp vụ và yêu cầu vận hành cụ thể.

## 8. Tương thích trước và sau: ai đọc dữ liệu của ai?

Một hệ thống nhiều service hiếm khi nâng cấp mọi thành phần cùng giây. Vì vậy cần nghĩ tới **nhiều phiên bản chạy đồng thời**.

Khái niệm thường dùng:

- **Backward compatibility:** phiên bản mới vẫn đọc/chấp nhận dữ liệu hoặc request do phiên bản cũ tạo ra.
- **Forward compatibility:** phiên bản cũ có thể đọc/chấp nhận dữ liệu hoặc response mới trong phạm vi được thiết kế, ví dụ bỏ qua trường bổ sung chưa biết.

Các định nghĩa có thể được trình bày theo góc nhìn producer hoặc consumer nên dễ nhầm. Cách thực tế nhất là luôn viết rõ từng cặp:

1. **Client cũ → server mới:** request cũ có tiếp tục được xử lý không?
2. **Client mới → server cũ:** request mới có phụ thuộc tính năng mà server cũ chưa biết không?
3. **Producer mới → consumer cũ:** thông điệp có giải mã và xử lý an toàn không?
4. **Producer cũ → consumer mới:** consumer mới có còn hiểu sự kiện cũ, kể cả khi replay không?

Việc kiểm tra từng cặp có giá trị hơn tuyên bố chung “schema tương thích”.

### 8.1. Một số thay đổi thường gặp

| Thay đổi | Rủi ro | Cách tiếp cận an toàn hơn |
| --- | --- | --- |
| Thêm thuộc tính response không bắt buộc | Client cũ parse quá chặt có thể lỗi | Kiểm tra client bỏ qua trường không biết; rollout từ producer |
| Thêm trường **bắt buộc** vào request | Client cũ không gửi được | Giữ optional hoặc có default/business fallback trong giai đoạn chuyển tiếp |
| Xóa/đổi tên trường đang dùng | Consumer cũ không hiểu | Deprecate, hỗ trợ song song, kiểm tra sử dụng trước khi bỏ |
| Đổi kiểu dữ liệu, đơn vị tiền hoặc timezone | Vừa có thể parse lỗi vừa sai nghiệp vụ | Thêm trường mới, chuyển đổi có kiểm soát |
| Thêm enum value | Client cũ có thể không xử lý | Consumer có nhánh unknown; không diễn giải thành trạng thái thành công |
| Đổi nghĩa của `CONFIRMED` | Cực kỳ nguy hiểm dù schema không đổi | Thiết kế hợp đồng/sự kiện mới với nghĩa rõ |
| Đổi Protobuf field number | Dữ liệu cũ có thể thành unknown hoặc bị hiểu sai | Giữ tag ổn định, reserve tag đã xóa |
| Đổi Protobuf field từ singular sang repeated hay thay wire type | Có thể phá wire hoặc semantic compatibility | Kiểm tra theo quy tắc tương thích cụ thể; thêm field mới khi cần |
| Đổi sự kiện từ `OrderPlaced` sang `OrderConfirmed` | Đây có thể là hai sự thật khác nhau | Không đổi nhãn đơn thuần; định nghĩa trigger và quy trình di trú |
| Thắt chặt validator/unknown field policy | Dữ liệu trước đây hợp lệ bị từ chối | Kiểm tra producer và dữ liệu lưu lịch sử trước khi áp dụng |

**Tương thích cấu trúc là điều kiện cần nhưng chưa đủ.** Một thay đổi cùng kiểu dữ liệu mà thay đổi ý nghĩa có thể gây hậu quả nghiêm trọng hơn việc parse lỗi.

## 9. Mở rộng hợp đồng an toàn theo nhiều đợt triển khai

Giả sử Payment API cần bổ sung `capturePolicy` (quy tắc thu tiền) vào request tạo ủy quyền. Một đợt nâng cấp an toàn có thể diễn ra theo kiểu **expand → migrate → contract**.

### Giai đoạn 1 — Expand

- Server chấp nhận request có hoặc không có `capturePolicy`.
- Hợp đồng OpenAPI cập nhật trường mới là optional và giải thích default rõ.
- Các client cũ tiếp tục chạy bình thường.
- Server đo mức độ sử dụng để biết có client nào đang gửi trường mới.

### Giai đoạn 2 — Migrate

- Client mới bắt đầu gửi `capturePolicy` khi cần.
- Có kiểm thử cả client cũ và mới với server đang triển khai.
- Theo dõi tỷ lệ lỗi, trường hợp retry và hành vi fallback.

### Giai đoạn 3 — Contract

- Chỉ khi mọi consumer liên quan đã chuyển đổi và có chính sách rõ mới xem xét bỏ hỗ trợ cũ.
- Nếu trường mới thật sự bắt buộc theo nghiệp vụ, có thể cần phiên bản endpoint/hợp đồng riêng hoặc cơ chế chuyển tiếp phù hợp.
- Tránh buộc mọi service phát hành cùng lúc chỉ vì một thay đổi schema.

Đối với event có retention dài, giai đoạn contract khó hơn: consumer mới có thể cần đọc lại event cũ từ nhiều tháng trước. Vì vậy việc ngừng **phát** v1 không đồng nghĩa có thể ngừng **đọc** v1 ngay lập tức.

## 10. Versioning: version cái gì và khi nào?

Một hệ thống có thể có nhiều loại version độc lập:

| Phiên bản | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| API contract | `info.version: 1.2.0` trong OpenAPI | Phiên bản tài liệu/hợp đồng HTTP được công bố |
| URI/media type API | `/v1/payments` hoặc media type version | Cơ chế phân biệt các biến thể API |
| Protobuf package | `payments.v1` | Namespace của type và service RPC |
| Event schema version | `eventVersion: 2` | Dạng hợp đồng event |
| Aggregate version | `aggregateVersion: 17` | Thứ tự thay đổi một aggregate theo quy tắc domain |
| Service build/release | `payment-service:2026.11.11` | Phiên bản artifact triển khai |

**Không đồng nhất** các version trên. Một service build mới có thể phục vụ API v1, schema event v2 và đọc dữ liệu v1 để bảo đảm giai đoạn di trú.

### 10.1. OpenAPI không ép một chiến lược URL version

Có thể chọn version trong path, header hoặc media type, hoặc phát triển tương thích trong một API không đổi URL. Lựa chọn phụ thuộc môi trường và người dùng API.

- `/v1` dễ nhận biết và vận hành nhiều phiên bản song song.
- Header/media type có thể giữ URL ổn định nhưng làm client và gateway phức tạp hơn.
- Thay đổi cộng dồn tương thích có thể không cần version path mới cho từng trường nhỏ.

Mọi chiến lược vẫn cần chính sách deprecation, hỗ trợ phiên bản cũ, thông báo migration và đo consumer usage.

### 10.2. Protobuf package version

Ví dụ `payments.v1` giúp tách namespace khi có thay đổi lớn. Tuy nhiên không nên tạo `v2` chỉ vì thêm một optional field tương thích. Phân tích wire/source compatibility trước; khi phá hợp đồng thực sự, có thể cung cấp hai API hoặc hai package trong thời gian chuyển đổi.

### 10.3. Version event

Có thể dùng tên event mới, header `schemaVersion`, subject trong schema registry hoặc nhiều topic theo chiến lược của nền tảng. Điều cần làm rõ là producer phát loại nào, consumer đọc được loại nào, event cũ khi replay được xử lý thế nào và khi nào được loại bỏ hỗ trợ.

Nếu ý nghĩa nghiệp vụ thay đổi hoàn toàn, đôi khi **tạo một event khác** phù hợp hơn là tăng schema version và vẫn dùng tên cũ dễ gây hiểu nhầm.

## 11. Contract-first và quy trình quản trị hợp đồng

**Contract-first** nghĩa là các bên thống nhất hợp đồng trước hoặc đồng thời với phần triển khai, rồi để code và kiểm thử đối chiếu theo hợp đồng đã công bố. Điều đó không có nghĩa mọi tính năng đều phải viết đặc tả dài trước khi thử nghiệm; mục tiêu là bảo vệ những điểm giao tiếp có consumer độc lập.

Quy trình thực tế:

1. **Xác định owner của contract.** Service nào cam kết và vận hành nó? Consumer nào bị ảnh hưởng?
2. **Định nghĩa business operation/event.** Viết rõ tình huống sử dụng, điều kiện thành công và tình trạng lỗi.
3. **Chọn phương thức giao tiếp.** HTTP/REST, RPC, event, command queue hoặc phương án khác theo yêu cầu thời gian và độ tin cậy.
4. **Thiết kế schema công khai.** Tách DTO/message khỏi persistence entity và chi tiết nội bộ.
5. **Định nghĩa quy tắc versioning.** Thêm/bỏ trường, enum, unknown field, deprecation và compatibility window.
6. **Đặt đặc tả trong version control.** Review thay đổi schema cùng thay đổi code, có owner và lịch sử phát hành.
7. **Tự động kiểm tra cấu trúc.** Lint OpenAPI/`.proto`/JSON Schema, kiểm tra quy tắc compatibility với bản đang công bố.
8. **Kiểm thử hành vi và consumer.** Không chỉ parse schema mà phải kiểm tra status, lỗi, idempotency, dữ liệu và semantic.
9. **Rollout từng phần.** Producer/server hỗ trợ song song khi cần; theo dõi consumer và trạng thái thực tế.
10. **Duy trì khi loại bỏ phiên bản.** Công bố lịch ngừng, tài liệu migration, kiểm tra event retention và client đang hoạt động.

### 11.1. Generated code: tiện lợi nhưng cần sở hữu rõ

Sinh client từ OpenAPI hoặc Protobuf giúp giảm lỗi gõ tay và đồng bộ type. Tuy nhiên:

- Không nên đưa generated class như một **mô hình domain dùng chung** cho mọi service.
- Mỗi service nên có lớp ánh xạ từ hợp đồng ngoài vào mô hình nội bộ của mình.
- Không nên biến một thư viện DTO dùng chung thành lý do buộc mọi service cùng deploy.
- Cần quản lý version của thư viện contract/generator và khả năng đọc các phiên bản hiện hành.
- Không mặc định generated validation hoặc generated stub đã bao phủ logic nghiệp vụ.

Hợp đồng giúp các đội thống nhất tại ranh giới, còn nội bộ mỗi service có quyền tổ chức code và dữ liệu riêng.

## 12. Ba lớp kiểm thử hợp đồng

### 12.1. Kiểm tra cấu trúc

- OpenAPI: tài liệu hợp lệ, schema reference đúng, request/response có dạng dự kiến.
- Protobuf: `.proto` biên dịch được, field number không bị tái sử dụng, thay đổi có phù hợp quy tắc compatibility không.
- Event: schema hợp lệ, payload mẫu hợp lệ, producer và consumer có cùng cách diễn giải envelope.

Cần có cả **mẫu hợp lệ và mẫu không hợp lệ**, đặc biệt cho missing field, null, giá trị enum mới và unknown field.

### 12.2. Contract tests giữa provider và consumer

**Provider contract tests** xác nhận server/producer thật có thể đáp ứng hợp đồng công bố. **Consumer-driven contract tests** mô tả những kỳ vọng cụ thể của các consumer và xác nhận provider không phá những kỳ vọng đó.

Ví dụ consumer OrderService mong:

- `GET /payments/{id}` trả trạng thái `AUTHORIZED` khi đã ủy quyền.
- Với `paymentId` không tồn tại, HTTP response đúng theo hợp đồng.
- Một sự kiện `PaymentAuthorized` có `paymentId`, `orderId`, `eventId` và số tiền theo quy ước.

Những bài test này phát hiện sự không tương thích đã mô tả, nhưng **không chứng minh mọi hành vi runtime và mọi consumer chưa biết đều đúng**. Tính đúng đắn của transaction, bảo mật, timeout và message retry vẫn cần kiểm thử khác.

### 12.3. Integration và end-to-end tests

Các tình huống cần kiểm tra:

- Client cũ gọi server mới; server mới trả trường mới.
- Producer mới phát event tới consumer cũ.
- Consumer mới replay event cũ.
- Retry gây request hoặc event trùng.
- Mất phản hồi sau khi server đã xử lý thành công.
- Event đến sai thứ tự hoặc bị trễ.
- API chỉ trả 202 nhưng client tưởng giao dịch hoàn tất.
- Một trường có type đúng nhưng sai đơn vị tiền hoặc timezone.
- Token hợp lệ nhưng không đủ quyền truy cập đối tượng được yêu cầu.

Kết hợp contract tests với integration tests giúp phát hiện lỗi **ở ranh giới** và lỗi **ở hành trình nghiệp vụ**, tránh lệ thuộc vào một bộ kiểm thử khổng lồ chỉ chạy sau khi tất cả service phát hành cùng lúc.

## 13. Tương thích event và bài toán dữ liệu lịch sử

Với HTTP API, request/response thường tồn tại ngắn. Với broker có retention hoặc event store, thông điệp có thể được đọc lại trong tương lai. Điều đó tạo một yêu cầu khác: **schema mới có đọc được dữ liệu lịch sử không?**

Giả sử `PaymentAuthorized` v1 không chứa `country`, v2 bổ sung trường này. Khi tái dựng read model, consumer mới phải xử lý event v1 thiếu `country`.

Một số lựa chọn hợp lệ:

- Cho phép `country` optional và có quy tắc rõ cho trạng thái không biết.
- Upcast v1 thành dạng nội bộ mới khi đọc, bằng phép chuyển đổi được kiểm thử.
- Giữ nhiều decoder/schema version và xử lý theo version của mỗi event.
- Phát event mới khi ý nghĩa nghiệp vụ khác bản cũ; không bịa giá trị lịch sử không tồn tại.

Không nên lấy “quốc gia hiện tại” của khách để lấp vào event lịch sử nếu business cần **quốc gia tại thời điểm thanh toán**. Việc giải mã qua phiên bản phải giữ đúng ngữ nghĩa thời điểm xảy ra sự kiện.

### 13.1. JSON Schema và chính sách trường lạ

Nếu consumer dùng JSON và **từ chối mọi thuộc tính ngoài schema**, thêm trường mới có thể bị xem là lỗi. Nếu bỏ qua trường lạ, nó có thể tiếp tục hoạt động nhưng cũng có nguy cơ bỏ qua một thay đổi quan trọng về ý nghĩa. Vì vậy quy tắc unknown fields phải gắn với versioning và sự phân loại required/optional, không đơn giản là “luôn strict” hay “luôn loose”.

### 13.2. Avro và schema registry

Avro thường được dùng cho dữ liệu có schema, có thể kết hợp registry để kiểm soát version và quy tắc tương thích đọc/ghi. Registry giúp quản lý schema ID và phát hiện một số dạng thay đổi phá vỡ cấu trúc. Tuy nhiên, các câu hỏi “PaymentAuthorized có nghĩa gì?”, “đơn vị tiền là gì?” hoặc “consumer cần xử lý lại thế nào?” vẫn do contract nghiệp vụ quyết định.

## 14. Độ tin cậy thông điệp không đến từ schema

Schema xác minh dạng thông điệp nhưng không quyết định việc event đã được công bố nhất quán với dữ liệu hay chưa.

Xét lỗi:

1. PaymentService commit trạng thái `AUTHORIZED` trong database.
2. Nó cố phát `PaymentAuthorized` nhưng kết nối broker thất bại.
3. Consumer không được thông báo dù trạng thái đã đổi.

Một thiết kế phổ biến là **transactional outbox**:

    Trong cùng DB transaction:
      - cập nhật trạng thái payment
      - ghi outbox_event(eventId, eventType, payload)

    Sau commit:
      - publisher đọc outbox
      - phát event ra broker
      - đánh dấu tiến độ
      - retry có kiểm soát nếu cần

Đây là cách liên kết một sự thật nghiệp vụ đã commit với việc công bố event, tránh phụ thuộc vào một lời gọi mạng sau commit. Nhưng outbox có thể phát lặp nếu broker nhận rồi publisher chưa ghi nhận thành công, nên consumer cần **idempotent processing**.

Một consumer có thể lưu `eventId` đã xử lý cùng transaction thay đổi dữ liệu của chính nó. Với tác dụng phụ bên ngoài như gửi email hoặc chuyển tiền, cần thiết kế riêng cơ chế chống lặp/đối soát, bởi transaction database nội bộ không bao trùm hệ thống khác.

Cũng cần quy định thứ tự xử lý theo khóa nghiệp vụ, dead-letter, poison message, retry/backoff và quan sát lag. **Protobuf nhanh hơn hoặc OpenAPI đầy đủ hơn không tự giải quyết những vấn đề này.**

## 15. Bảo mật và quản lý dữ liệu công khai

Một hợp đồng dễ dùng cũng có thể trở thành kênh phát tán quá nhiều dữ liệu. Cần phân biệt những gì một consumer **có thể giải mã** với những gì nó **được phép truy cập và sử dụng**.

Ví dụ:

- `OrderConfirmed` không cần chứa số thẻ, token đối tác hoặc toàn bộ hồ sơ khách hàng.
- Notification có thể cần địa chỉ liên hệ; Analytics có thể chỉ cần `orderId` và các số liệu đã được cho phép.
- Một gRPC method truy vấn Payment phải xác thực service gọi và kiểm tra quyền trên `paymentId`, không chỉ xác thực kết nối.
- HTTP client không được coi schema OpenAPI là bằng chứng server đã thực thi authorization.
- Event trong dead-letter queue, log hoặc bản sao projection cũng phải được xem xét retention và quyền truy cập.

Với các thông điệp dữ liệu nhạy cảm, có thể dùng topic/queue riêng, trường tham chiếu được kiểm soát quyền, mã hóa đường truyền và chính sách phân quyền producer/consumer. Khi ghi log/tracing nên dùng event ID, correlation ID và error code phù hợp, tránh ghi raw payload nhạy cảm.

**Công bố trường nào cũng là cam kết dữ liệu và trách nhiệm bảo vệ trường đó**, không chỉ là quyết định đặt tên field.

## 16. Ví dụ một thay đổi phá hợp đồng dù schema vẫn hợp lệ

PaymentService ban đầu định nghĩa:

    status = AUTHORIZED
    nghĩa là cổng thanh toán đã chấp nhận ủy quyền,
    nhưng chưa chắc tiền đã được thu (captured).

Sau một đợt cập nhật, nhóm phát triển giữ nguyên enum `AUTHORIZED`, nhưng mô tả mới lại coi đó là “đã thu tiền hoàn tất”. Kiểu dữ liệu không đổi, OpenAPI vẫn parse được, Protobuf vẫn giải mã được, event JSON Schema vẫn validate thành công.

Tuy nhiên consumer Accounting có thể ghi nhận doanh thu sớm, còn Ordering có thể giao hàng sai thời điểm.

Lỗi này chứng minh **semantic contract quan trọng ít nhất ngang syntax contract**. Nếu nghiệp vụ phân biệt authorization và capture, cần mô hình hóa rõ:

- `PaymentAuthorized`: khoản tiền được ủy quyền theo điều kiện đã công bố.
- `PaymentCaptured`: khoản tiền đã được thu theo điều kiện đã công bố.
- `PaymentDeclined`: yêu cầu thanh toán bị từ chối.
- Các trường hợp còn PENDING/UNKNOWN phải có cách tra cứu và đối soát.

Đừng thay nghĩa của một event hoặc enum hiện hữu chỉ để “tiết kiệm” một phiên bản hợp đồng.

## 17. Chiến lược phối hợp giữa các đội

Một nhóm triển khai độc lập cần biết **mình có thể thay đổi gì mà không phá consumer khác**.

Một mô hình tổ chức hữu ích:

- **Producer/provider** sở hữu contract và công bố version, thay đổi, lịch deprecation.
- **Consumer** mô tả kỳ vọng thực tế, có tests và xử lý các trạng thái chưa biết theo hợp đồng.
- **Nền tảng** cung cấp công cụ lint, schema registry, test CI, phân phối artifact và monitoring khi cần.
- **Đội nghiệp vụ/domain** thống nhất nghĩa của trạng thái, sự kiện, số tiền, thời điểm và các bất biến.
- **Vận hành** theo dõi traffic theo phiên bản, lỗi giải mã, consumer lag, DLQ và độ trễ xử lý.

Không nhất thiết mọi service cùng dùng một thư viện domain model. Việc dùng chung DTO “cho tiện” có thể tạo **lockstep releases**, vì thay một class buộc cập nhật nhiều service. Hợp đồng công khai là điểm thống nhất; mô hình nội bộ vẫn có thể khác nhau.

### Mẫu thông tin cần ghi trong một contract

| Mục | Ví dụ cần điền |
| --- | --- |
| Contract owner | PaymentService team |
| Interaction | `POST /payments/authorizations` hoặc `payment.authorized` |
| Consumers | Ordering, Accounting, Notification |
| Business meaning | Điều kiện một giao dịch được ủy quyền |
| Schema | OpenAPI path / Protobuf package / JSON Schema ID |
| Security | Quyền gọi API hoặc quyền subscribe topic |
| Availability/latency | Deadline, SLO hoặc mức xử lý trễ được chấp nhận |
| Delivery semantics | Retry, duplicates, ordering, retention nếu là event |
| Version policy | Mức tương thích, thời gian hỗ trợ, cách deprecate |
| Examples/tests | Request/response, event mẫu, lỗi và contract tests |

## 18. Case study: đổi hợp đồng tổng tiền của một đơn hàng

Hệ thống bán hàng có Ordering, Pricing và Payment. Ban đầu:

- Ordering gọi Pricing bằng HTTP với `amount` là số thực.
- Ordering gửi tổng tiền cho Payment qua gRPC.
- Payment phát event `PaymentCaptured` dạng JSON lên broker.
- Analytics đọc event để tạo báo cáo.

Sau một sự cố làm tròn, doanh nghiệp quyết định chuẩn hóa tiền thành **số nguyên theo đơn vị nhỏ nhất của đồng tiền**, kèm `currency`.

Một cách triển khai rủi ro là đổi luôn `amount: number` thành `amountMinor: integer` trong mọi contract, xóa trường cũ và triển khai các service cùng lúc. Điều này phá client cũ, Protobuf field và event lịch sử nếu không có kế hoạch.

Một kế hoạch di trú có thể là:

1. Định nghĩa rõ `amountMinor` (phụ thuộc mã tiền tệ), tên trường và ý nghĩa xử lý, cùng ví dụ tiền tệ cụ thể.
2. Bổ sung trường mới theo cách tương thích vào API/gRPC/event nếu ngữ nghĩa cho phép, không tái sử dụng field number Protobuf cũ với nghĩa khác.
3. Cập nhật server/provider để hiểu cả request cũ và mới trong giai đoạn chuyển tiếp; tránh tính hai lần từ hai trường mâu thuẫn.
4. Triển khai consumer có khả năng đọc dữ liệu cũ, sau đó mới chuyển producer sang gửi dữ liệu mới.
5. Giữ decoder cho event lịch sử khi replay, hoặc có upcaster đã kiểm thử.
6. Khi mọi client và consumer đã nâng cấp, có chính sách ngừng trường cũ và theo dõi lỗi thực tế.
7. Thêm contract tests về các ca làm tròn, tiền tệ có đơn vị nhỏ nhất khác nhau và giá trị biên.

**Điểm cần lưu ý:** Nếu số thực cũ đã chứa giá trị mơ hồ, không phải mọi bản ghi lịch sử đều có thể chuyển đúng bằng phép nhân. Có thể cần đối soát hoặc quy ước migration được phê duyệt bởi domain owner.

Case study minh họa cách OpenAPI, Protobuf và event schema phải phối hợp nhưng **không nên bị buộc dùng cùng một định dạng hoặc một version number duy nhất**.

## 19. Bài tập thực hành

Hãy tưởng tượng bạn là người phụ trách hợp đồng giữa OrderService và PaymentService:

**Tình huống A — OpenAPI:** Một API `POST /payments` hiện yêu cầu `orderId` và `amount`. Nhóm Payment muốn thêm `currency` bắt buộc và dùng HTTP 202 vì việc xử lý có thể kéo dài.

- Client cũ có tiếp tục gửi request được không?
- Có thể thêm `currency` optional trước và có quy tắc chuyển tiếp an toàn không?
- Khi trả 202, client cần API truy vấn trạng thái hoặc cơ chế thông báo nào?
- Làm sao kiểm tra client không coi 202 là “tiền đã thu thành công”?

**Tình huống B — Protobuf:** Message `PaymentStatus` đang dùng `string payment_id = 1` và `int32 status_code = 2`. Nhóm muốn xóa `status_code` và thay bằng enum rõ nghĩa.

- Có nên dùng lại field number 2 cho enum mới không?
- Vì sao cần `reserved 2` sau khi bỏ trường cũ?
- Client cũ và client mới sẽ được triển khai theo thứ tự nào?
- Nếu `status_code=0` từng có nghĩa “đã thanh toán”, sự kiện nào có thể xảy ra khi client mới dùng default value?

**Tình huống C — Event:** Event `PaymentCaptured` v1 chỉ có `paymentId` và `orderId`. Consumer Analytics cần thêm `capturedAmountMinor` và `currency`.

- Nên phát bản sao toàn bộ PaymentEntity hay thêm những trường nghiệp vụ có chủ đích?
- Event v1 đã lưu trong broker có thể được replay bằng consumer mới như thế nào?
- Nếu producer mới phát v2 khi một consumer còn ở v1, điều gì phải được kiểm tra?
- Nếu consumer xử lý cùng event hai lần, cách bảo vệ tác dụng phụ nghiệp vụ là gì?
- JSON Schema validate thành công đã đủ khẳng định số tiền đúng quy tắc không?

**Gợi ý suy luận:** Với HTTP, bảo vệ client cũ bằng mở rộng contract và giai đoạn di trú. Với Protobuf, giữ ổn định field number và ngữ nghĩa, reserve những tag không còn dùng. Với event, công bố đúng sự thật nghiệp vụ, có schema version và xử lý event lịch sử/trùng lặp. Trong cả ba trường hợp, điều quan trọng nhất là xác định những hệ thống cũ và mới phải cùng hoạt động qua ranh giới phiên bản nào.

## 20. Ghi nhớ

- **OpenAPI** mô tả hình dạng và hành vi dự kiến của HTTP API: operation, request, response, schema và security scheme.
- **Protocol Buffers** định nghĩa message có kiểu và field number; khi kết hợp gRPC có thể định nghĩa RPC service/method. Protobuf không đồng nghĩa với gRPC.
- **Lược đồ sự kiện** định nghĩa payload được công bố bất đồng bộ; có thể dùng JSON Schema, Avro hoặc Protobuf. Một hợp đồng event đầy đủ còn cần trigger, ownership, delivery, retry, idempotency và replay.
- **Hợp đồng là ranh giới công khai**, không phải bản sao entity, schema database hay class generated nội bộ.
- **Tương thích phải xét theo chiều triển khai**: client cũ với server mới; producer mới với consumer cũ; consumer mới với event lịch sử.
- **Versioning có nhiều cấp**: API, `.proto` package, event schema, aggregate và service release. Không ép chúng cùng tăng version.
- **Đúng schema chưa đủ để đúng nghiệp vụ**: đơn vị tiền, nghĩa trạng thái, thời điểm, idempotency và quyền truy cập phải được kiểm thử bằng ví dụ hành vi thực.
- **Cải tiến an toàn theo expand → migrate → contract**, theo dõi consumer và giữ khả năng đọc dữ liệu lịch sử khi cần.

Trong một kiến trúc microservices có thể phát hành độc lập, hợp đồng giao tiếp là **cam kết đủ ổn định để các bên tiến hóa không đồng thời**. Công cụ mô tả giúp phát hiện lỗi cấu trúc sớm; trách nhiệm của thiết kế kiến trúc là bảo đảm những thông điệp đó vẫn truyền đạt đúng ý nghĩa nghiệp vụ qua các phiên bản.
