# Kiểm thử hợp đồng

Trong một hệ thống phần mềm, một thành phần thường không hoạt động độc lập. Ứng dụng gọi API, API đọc và ghi dữ liệu, service trao đổi message, DSL compiler gọi backend, còn các công cụ khác tiêu thụ artifact do hệ thống tạo ra. Mỗi ranh giới như vậy đều có những giả định về cấu trúc, kiểu dữ liệu, hành vi và lỗi. Nếu một phía thay đổi mà phía còn lại không biết, hệ thống có thể vẫn build thành công nhưng lỗi khi tích hợp hoặc khi chạy thực tế.

**Kiểm thử hợp đồng (contract testing)** xác minh rằng các bên giao tiếp tuân thủ một thỏa thuận đã xác định. Hợp đồng mô tả những gì một bên cung cấp, những gì bên kia được phép yêu cầu, định dạng dữ liệu được trao đổi và hành vi có thể dự đoán. Kiểm thử hợp đồng tập trung vào ranh giới giữa các thành phần, giúp phát hiện sớm thay đổi không tương thích.

Trong ngữ cảnh **Computer Science Domain Specific Language**, đặc biệt ở chương **DSL API và dữ liệu**, hợp đồng có thể tồn tại ở nhiều lớp:

- Cấu trúc và semantics của DSL API.
- Request, response, status code và error format.
- Schema dữ liệu và quy tắc serialization.
- Message hoặc event giữa các service.
- Query model, repository và database schema.
- AST, intermediate representation và compiler plugin API.
- Interface giữa DSL runtime với backend hoặc external provider.

Ví dụ, một DSL mô tả API:

~~~text
endpoint "GET /orders/{orderId}" {
    response 200 {
        body = OrderResponse
    }

    response 404 {
        body = ErrorResponse
    }
}
~~~

Hợp đồng không chỉ nói endpoint tồn tại. Nó còn quy định path parameter, kiểu response, field bắt buộc, status code, error shape và các điều kiện truy cập. Contract test xác minh implementation thực tế vẫn tuân thủ các quy tắc đó.

Kiểm thử hợp đồng không thay thế unit test, integration test hoặc end-to-end test. Nó bổ sung một lớp kiểm tra có mục tiêu rõ ràng: phát hiện sự không tương thích tại ranh giới mà các thành phần phụ thuộc vào nhau.

## 1. Hợp đồng phần mềm là gì?

**Contract** là thỏa thuận có thể kiểm chứng giữa hai hoặc nhiều thành phần về cách chúng tương tác. Hợp đồng thường xác định:

- Tên và phiên bản interface.
- Các operation hoặc message được hỗ trợ.
- Input, output và kiểu dữ liệu.
- Field bắt buộc, tùy chọn, nullable hoặc có default.
- Quy tắc validation và constraint.
- Thứ tự hoặc semantics của thao tác.
- Side effect và trạng thái có thể thay đổi.
- Error condition và cách biểu diễn lỗi.
- Authentication, authorization và các yêu cầu bảo mật.
- Timeout, retry, idempotency và các giới hạn vận hành.
- Quy tắc tương thích khi interface thay đổi.

Ví dụ, một API tạo đơn hàng có hợp đồng khái niệm:

~~~yaml
operation: createOrder
method: POST
path: /orders
request:
  required:
    - customerId
    - items
  properties:
    customerId:
      type: string
    items:
      type: array
      minItems: 1
responses:
  201:
    body: OrderResponse
  400:
    body: ValidationError
  401:
    body: AuthenticationError
~~~

Implementation phải nhận input phù hợp và trả kết quả theo hợp đồng. Nếu implementation đổi tên customerId thành clientId mà không có migration hoặc version mới, consumer cũ có thể bị hỏng.

### 1.1. Provider và consumer

Trong mô hình phổ biến:

- **Provider** là thành phần cung cấp API, event, schema hoặc dịch vụ.
- **Consumer** là thành phần sử dụng interface đó.

Ví dụ:

~~~mermaid
flowchart LR
    C[Consumer application] -->|Request| P[Provider API]
    P -->|Response| C
    K[Contract] -. defines .-> C
    K -. defines .-> P
~~~

Consumer có thể là frontend, service khác, CLI, plugin hoặc DSL-generated client. Provider có thể là HTTP service, database adapter, message broker integration hoặc compiler backend.

### 1.2. Contract khác với implementation

Contract mô tả hành vi quan sát được tại ranh giới. Nó không nhất thiết quy định provider phải dùng framework, database hoặc thuật toán nào bên trong.

Ví dụ, hợp đồng có thể yêu cầu API trả danh sách đơn hàng theo cursor. Provider có thể dùng SQL, document database hoặc cache miễn là kết quả tuân thủ semantics đã công bố.

### 1.3. Contract có thể là tài liệu hoặc artifact máy đọc được

Hợp đồng có thể được mô tả bằng:

- OpenAPI cho HTTP API.
- AsyncAPI cho event-driven API.
- JSON Schema hoặc Avro Schema cho dữ liệu.
- Protocol Buffers hoặc interface definition language.
- DSL grammar và semantic specification.
- Schema riêng cho plugin hoặc compiler extension.
- Tài liệu quy tắc cùng executable examples.

Một contract test hiệu quả thường dùng một biểu diễn có thể được kiểm tra tự động, nhưng không phải mọi quy tắc đều có thể diễn đạt trong schema.

## 2. Contract testing là gì?

**Contract testing** là kỹ thuật kiểm thử xác nhận provider và consumer tuân thủ hợp đồng giao tiếp. Thay vì chỉ kiểm tra một thành phần có chạy được hay không, contract test kiểm tra một phía có cung cấp đúng interface mà phía kia kỳ vọng hay không.

Ví dụ:

1. Consumer gửi request có customerId và danh sách items.
2. Provider nhận request.
3. Provider trả status 201 cùng OrderResponse.
4. Contract test xác minh response có đúng cấu trúc, kiểu và semantics được công bố.

Contract testing có thể được thực hiện ở thời điểm build, trong CI, khi phát hành schema hoặc trước khi triển khai.

### 2.1. Contract test trả lời câu hỏi nào?

- Consumer có gửi request đúng định dạng không?
- Provider có chấp nhận request hợp lệ không?
- Provider có từ chối input không hợp lệ theo cách được mô tả không?
- Response có đúng field, type và status code không?
- Event có tuân thủ schema và version không?
- Thay đổi provider có làm consumer hiện tại bị hỏng không?
- Hai phiên bản DSL/compiler có cùng hiểu một artifact theo contract không?

### 2.2. Contract test không chứng minh điều gì?

Một contract test thành công không chứng minh:

- Toàn bộ nghiệp vụ là đúng.
- Hệ thống có thể chịu tải production.
- Database và external service luôn sẵn sàng.
- Mọi luồng end-to-end đều hoạt động.
- Authorization policy đã bao phủ mọi tình huống.
- Implementation không có bug ngoài phạm vi contract.

Contract test chỉ cung cấp bằng chứng cho các tương tác và trường hợp được đưa vào hợp đồng và bộ test.

## 3. Vì sao cần kiểm thử hợp đồng?

Trong hệ thống có nhiều service hoặc nhiều consumer, một thay đổi nhỏ có thể ảnh hưởng rộng.

Ví dụ provider đổi kiểu orderId từ string sang integer. Provider có thể vẫn chạy tốt với dữ liệu mới, nhưng consumer đang xử lý ID dưới dạng string có thể lỗi khi parse hoặc so sánh.

Contract testing giúp:

- Phát hiện breaking change trước khi release.
- Giảm phụ thuộc vào môi trường tích hợp lớn.
- Cho phép team provider và consumer phát triển độc lập.
- Làm rõ interface và ownership.
- Xác nhận schema được thực thi đúng trong implementation.
- Hỗ trợ versioning và migration.
- Ngăn thay đổi vô tình trong serialization hoặc error format.
- Cung cấp bằng chứng tương thích trong CI/CD.

### 3.1. Phát hiện lỗi tại ranh giới

Unit test có thể xác nhận hàm provider hoạt động theo logic nội bộ. Consumer unit test có thể dùng mock. Nhưng mock có thể không giống provider thật. Contract test kiểm tra chính thỏa thuận giữa hai phía và phát hiện mock hoặc implementation lệch nhau.

### 3.2. Giảm chi phí phối hợp

Nếu hợp đồng được công bố sớm, consumer có thể phát triển dựa trên schema và example mà không phải chờ provider hoàn thiện. Provider có thể chạy contract verification để biết thay đổi của mình có tương thích với consumer đã đăng ký.

### 3.3. Hỗ trợ tiến hóa API

Contract cung cấp mốc để đánh giá thay đổi:

- Thêm field optional thường có thể tương thích.
- Xóa field đang được dùng có thể phá consumer.
- Đổi kiểu field có thể là breaking change.
- Thay đổi semantics của status code có thể phá logic retry.

Contract test biến một phần quy tắc tương thích thành kiểm tra tự động.

## 4. Các loại kiểm thử hợp đồng

Có nhiều cách phân loại. Các loại sau thường được dùng kết hợp.

| Loại | Trọng tâm | Ví dụ |
|---|---|---|
| Consumer-driven contract | Nhu cầu thực tế của consumer | Frontend cần field id và total |
| Provider contract | Provider tuân thủ interface công bố | Response khớp OpenAPI |
| Schema contract | Cấu trúc và kiểu dữ liệu | Event khớp JSON Schema |
| Message contract | Producer và consumer trao đổi message | Event order-created có field bắt buộc |
| Protocol contract | Quy tắc giao tiếp | HTTP method, status, headers |
| DSL/compiler contract | Grammar và semantics | AST hoặc generated output ổn định |
| Database contract | Schema và repository boundary | Migration không phá query consumer |

### 4.1. Consumer-driven contract testing

Consumer mô tả tương tác mà nó thực sự sử dụng. Contract được lưu hoặc publish để provider xác minh.

Ví dụ consumer chỉ cần:

~~~json
{
  "id": "ord-100",
  "status": "PAID",
  "total": 125.50
}
~~~

Provider có thể trả thêm field khác. Consumer contract nên tập trung vào những field và semantics mà consumer phụ thuộc, tránh khóa provider vào toàn bộ implementation detail.

### 4.2. Provider contract testing

Provider chạy test trên implementation thật để xác nhận mọi operation đáp ứng schema và behavior được công bố.

Ví dụ:

- Request hợp lệ được chấp nhận.
- Request sai kiểu bị từ chối.
- Response 201 có đúng body.
- Error response có đúng schema.
- Header content-type đúng.

### 4.3. Schema contract testing

Schema contract xác nhận dữ liệu được serialize hoặc deserialize đúng schema. Nó đặc biệt hữu ích cho event, file exchange, API payload và message queue.

### 4.4. Message contract testing

Message contract kiểm tra producer và consumer thống nhất về event name, schema, key, ordering expectation và delivery semantics.

### 4.5. Protocol contract testing

Protocol contract kiểm tra method, path, headers, status, framing, version và các quy tắc tương tác khác. Với HTTP, contract có thể quy định status code và header caching. Với message broker, nó có thể quy định content type, routing key và acknowledgment semantics.

## 5. Contract testing trong DSL API và dữ liệu

DSL có thể tạo ra hoặc mô tả API và data model. Do đó, hợp đồng có thể nằm ở cả source DSL lẫn artifact sinh ra.

Ví dụ:

~~~text
model Order {
    id: OrderId
    customerId: CustomerId
    total: Money
    status: OrderStatus
}

api OrderApi {
    get "/orders/{id}" -> Order
}
~~~

Từ khai báo này, toolchain có thể sinh:

- OpenAPI document.
- Server route hoặc controller interface.
- Client SDK.
- JSON Schema.
- Serialization code.
- Validation code.

Contract test nên xác minh các artifact và runtime implementation vẫn nhất quán với source DSL.

### 5.1. DSL source là nguồn hợp đồng

Nếu DSL là source of truth, schema và API contract nên được sinh từ cùng semantic model. Việc duy trì một bản DSL và một bản OpenAPI thủ công có thể tạo drift.

### 5.2. Generated artifact cũng cần contract

Compiler có thể sinh API definition hoặc code. Test cần xác nhận output có đúng cấu trúc, version và semantics mà downstream tools kỳ vọng.

### 5.3. Runtime phải tuân thủ generated contract

Việc sinh OpenAPI thành công không bảo đảm server implementation thực sự trả đúng response. Cần chạy contract test trên provider runtime hoặc adapter.

### 5.4. DSL compiler là provider của compiler API

Nếu plugin hoặc tool khác gọi compiler API, compiler là provider. Contract có thể quy định input AST, diagnostic format, plugin lifecycle và compatibility giữa các phiên bản.

## 6. Xác định phạm vi hợp đồng

Trước khi viết test, cần xác định chính xác ranh giới được kiểm tra.

Các câu hỏi:

- Ai là provider?
- Ai là consumer?
- Interface là HTTP, message, function API, file hay AST?
- Dữ liệu nào đi qua ranh giới?
- Phiên bản contract nào đang được dùng?
- Hành vi nào là public contract?
- Hành vi nào chỉ là implementation detail?
- Những consumer nào đang phụ thuộc?
- Điều kiện bảo mật và vận hành nào thuộc contract?

Ví dụ, với DSL-generated HTTP API:

~~~mermaid
flowchart TD
    A[DSL source] --> B[Compiler]
    B --> C[OpenAPI contract]
    B --> D[Generated server/client]
    D --> E[Provider runtime]
    F[Consumer application] --> E
    C --> G[Contract verification]
    E --> G
    F --> H[Consumer expectations]
    H --> G
~~~

Phạm vi rõ giúp test không trở thành một bộ integration test lớn không biết đang xác minh hợp đồng nào.

## 7. Thiết kế một contract tốt

Hợp đồng nên đủ cụ thể để máy có thể kiểm tra và đủ ổn định để các bên phụ thuộc.

### 7.1. Input contract

Mô tả:

- Tên field.
- Kiểu dữ liệu.
- Required/optional.
- Nullable.
- Range, length và format.
- Enum và pattern.
- Default behavior.
- Quy tắc unknown field.

Ví dụ:

~~~yaml
type: object
required:
  - customerId
  - items
properties:
  customerId:
    type: string
    minLength: 1
  items:
    type: array
    minItems: 1
additionalProperties: false
~~~

### 7.2. Output contract

Mô tả:

- Field được trả về.
- Kiểu và nullability.
- Field có thể bị bỏ qua hay không.
- Format ngày, tiền tệ và identifier.
- Ordering của collection nếu có ý nghĩa.
- Content type và encoding.

### 7.3. Error contract

Mô tả:

- Error code ổn định.
- HTTP status hoặc message type.
- Error body schema.
- Validation detail.
- Retryability.
- Correlation identifier.
- Quy tắc không tiết lộ dữ liệu nhạy cảm.

### 7.4. Behavioral contract

Schema không diễn đạt được mọi hành vi. Behavioral contract có thể quy định:

- Một request tạo đúng một resource.
- Idempotency key ngăn tạo trùng.
- Update không thay đổi field ngoài phạm vi.
- Pagination cursor không bỏ sót bản ghi theo semantics đã công bố.
- Event chỉ được phát sau khi transaction commit.
- Operation có thể retry an toàn hay không.

### 7.5. Security contract

Có thể quy định:

- Authentication scheme.
- Required scope hoặc role.
- Tenant boundary.
- Field-level visibility.
- Rate limit.
- Secret handling.
- Audit event.

Không nên coi schema validation là thay thế authorization.

## 8. Contract testing cho HTTP API

HTTP API thường có contract gồm method, path, parameters, headers, request body, response body và status code.

Ví dụ OpenAPI rút gọn:

~~~yaml
paths:
  /orders/{orderId}:
    get:
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Order found
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Order"
        "404":
          description: Order not found
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Error"
~~~

### 8.1. Request verification

Kiểm tra client hoặc generated SDK tạo request đúng:

- Method và path.
- Path/query/header parameter.
- Content-Type.
- Authorization header.
- Request body.
- Encoding và date format.

### 8.2. Response verification

Kiểm tra provider:

- Trả status code đã công bố.
- Trả đúng content type.
- Response body khớp schema.
- Không thiếu required field.
- Không trả kiểu sai.
- Có behavior phù hợp khi resource không tồn tại.

### 8.3. Header contract

Header cũng là một phần của API contract. Ví dụ ETag, Location, Retry-After, Cache-Control và correlation ID có thể ảnh hưởng hành vi consumer.

### 8.4. Status code semantics

Không chỉ kiểm tra status code xuất hiện. Cần xác định ý nghĩa:

- 200: request thành công và có response representation.
- 201: resource được tạo.
- 202: request được chấp nhận để xử lý bất đồng bộ.
- 204: thành công nhưng không có response body.
- 400: request không hợp lệ.
- 401: thiếu hoặc sai authentication.
- 403: đã xác thực nhưng không được phép.
- 404: resource hoặc route không tồn tại theo contract.
- 409: conflict với trạng thái hiện tại.
- 429: rate limit.
- 5xx: lỗi phía server hoặc dependency.

Provider đổi từ 404 sang 200 với body rỗng có thể làm consumer xử lý sai dù request vẫn hoàn tất.

### 8.5. Negative cases

Contract test nên bao gồm request thiếu field, sai kiểu, enum không hợp lệ, path parameter sai format và body quá lớn nếu giới hạn đó thuộc contract.

## 9. Contract testing cho schema dữ liệu

Data contract quy định cấu trúc, kiểu và semantics của dữ liệu trao đổi.

Ví dụ Order schema:

~~~json
{
  "type": "object",
  "required": ["id", "status", "total"],
  "properties": {
    "id": { "type": "string" },
    "status": {
      "type": "string",
      "enum": ["PENDING", "PAID", "CANCELLED"]
    },
    "total": {
      "type": "number",
      "minimum": 0
    },
    "createdAt": {
      "type": "string",
      "format": "date-time"
    }
  }
}
~~~

### 9.1. Required và optional

Consumer có thể giả định field required luôn tồn tại. Nếu provider bắt đầu bỏ field đó, consumer có thể lỗi. Field optional có thể vắng mặt và consumer phải xử lý.

### 9.2. Nullable và absent

Absent và null không nhất thiết tương đương:

- Absent: field không xuất hiện.
- Null: field có mặt với giá trị null.
- Empty: field có giá trị rỗng như chuỗi hoặc danh sách rỗng.

Contract phải xác định semantics vì các client và serializer có thể xử lý khác nhau.

### 9.3. Numeric precision

Với tiền tệ, decimal precision và scale là một phần contract. Nếu một phía serialize decimal thành floating-point không chính xác, consumer có thể nhận giá trị sai.

### 9.4. Date/time

Contract cần quy định timezone, format, precision và semantics UTC/local. Không nên chỉ ghi kiểu string mà bỏ qua định dạng mong đợi.

### 9.5. Unknown fields

Khi schema mở rộng, consumer cũ có thể nhận field mới. Contract nên quy định consumer có phải bỏ qua field chưa biết hay không. Provider cần biết consumer nào có strict deserializer.

## 10. Contract testing cho serialization và deserialization

DSL thường có serializer chuyển semantic model thành JSON, YAML, binary hoặc một định dạng wire. Deserializer thực hiện chiều ngược lại.

Contract test có thể xác nhận:

- Field name và casing.
- Enum representation.
- Numeric representation.
- Null và absent semantics.
- Date/time encoding.
- Unicode và escaping.
- Default handling.
- Unknown field behavior.
- Round-trip properties khi contract yêu cầu.

Ví dụ:

~~~text
Order(id = "ord-1", status = PAID, total = Money(125.50))
       |
       v
JSON serialization
       |
       v
{"id":"ord-1","status":"PAID","total":125.50}
~~~

### 10.1. Golden file

Golden test lưu một representation mong đợi rồi so sánh output serializer. Nó hữu ích để phát hiện thay đổi format hoặc ordering.

Golden test không nên khóa những chi tiết không thuộc contract, ví dụ thứ tự property JSON nếu consumer không được phép phụ thuộc vào thứ tự đó.

### 10.2. Round-trip test

Serialize rồi deserialize có thể xác nhận dữ liệu giữ nguyên theo semantics:

~~~text
decode(encode(value)) == value
~~~

Equality cần được định nghĩa. Ví dụ timestamp có thể được chuẩn hóa về UTC hoặc decimal có thể được canonicalize.

### 10.3. Cross-version test

Thử deserialize dữ liệu được tạo từ phiên bản trước bằng phiên bản hiện tại và ngược lại theo compatibility policy.

### 10.4. Binary format

Với Protocol Buffers hoặc Avro, cần test field number, schema evolution và default semantics. Đổi field number hoặc tái sử dụng số đã xóa có thể phá compatibility dù tên field nhìn vẫn hợp lý.

## 11. Consumer-driven contract testing

Consumer-driven contract (CDC) bắt đầu từ nhu cầu thật của consumer.

Quy trình cơ bản:

1. Consumer xác định operation và response fields mà nó sử dụng.
2. Consumer test tạo interaction mong đợi.
3. Contract được publish tới contract broker hoặc repository.
4. Provider lấy các contract liên quan.
5. Provider chạy verification trên implementation.
6. Kết quả được publish để release pipeline kiểm tra.

~~~mermaid
sequenceDiagram
    participant C as Consumer
    participant B as Contract repository
    participant P as Provider
    C->>B: Publish consumer contract
    P->>B: Fetch relevant contracts
    P->>P: Verify against provider implementation
    P->>B: Publish verification result
    B-->>C: Compatibility status
~~~

### 11.1. Vì sao consumer-driven?

OpenAPI hoặc schema provider có thể mô tả mọi capability, nhưng không chỉ ra consumer nào đang dùng field nào. CDC làm rõ những phần interface mà consumer thực sự phụ thuộc.

### 11.2. Không biến contract thành snapshot tùy tiện

Consumer không nên yêu cầu toàn bộ response phải giống một fixture nếu chỉ quan tâm một số field. Snapshot quá rộng khiến provider khó mở rộng và gây breaking change giả.

### 11.3. Một provider có nhiều consumer

Provider có thể phải xác minh nhiều contract. Một thay đổi chỉ tương thích với consumer A nhưng phá consumer B vẫn là breaking change đối với hệ sinh thái.

### 11.4. Consumer contract không phải quyền kiểm soát provider

Consumer mô tả nhu cầu quan sát được, không nên áp đặt cấu trúc nội bộ hoặc database schema của provider.

## 12. Provider verification

Provider verification chạy contract test trên implementation thật hoặc một instance có cấu hình gần thực tế.

Một provider verification thường:

1. Đọc contract.
2. Khởi động provider hoặc kết nối instance test.
3. Thiết lập trạng thái dữ liệu cần thiết.
4. Gửi request/message theo interaction.
5. So sánh response với expected contract.
6. Ghi kết quả và diagnostics.

### 12.1. Provider state

Một interaction có thể cần trạng thái ban đầu, ví dụ order đã tồn tại. Contract test nên định nghĩa provider state setup:

~~~text
given "an order exists for the authenticated customer"
when GET /orders/ord-100
then response status is 200
and response body conforms to Order
~~~

Provider state setup cần cô lập dữ liệu test và không phụ thuộc vào thứ tự chạy test.

### 12.2. Test data

Dùng dữ liệu deterministic, có thể tạo và xóa. Tránh phụ thuộc vào dữ liệu production hoặc fixture dùng chung có thể bị test khác thay đổi.

### 12.3. External dependencies

Nếu provider gọi dịch vụ ngoài, có thể dùng test double ở boundary phù hợp. Nhưng contract verification vẫn cần kiểm tra provider API thật, không chỉ mock toàn bộ provider.

### 12.4. Authentication

Contract test cần mô phỏng identity hoặc token phù hợp. Nếu bỏ authentication để tiện test, có thể bỏ sót behavior thuộc public contract.

## 13. Contract testing cho event và message

Trong hệ thống event-driven, producer phát message và consumer xử lý nó. Hai phía có thể được triển khai ở thời điểm khác nhau nên schema compatibility rất quan trọng.

Ví dụ event:

~~~json
{
  "eventId": "evt-901",
  "eventType": "order.created",
  "occurredAt": "2026-11-15T03:00:00Z",
  "data": {
    "orderId": "ord-100",
    "customerId": "cus-12",
    "total": 125.50
  }
}
~~~

### 13.1. Message envelope

Envelope có thể chứa:

- Event ID.
- Event type.
- Schema version.
- Timestamp.
- Producer/source.
- Correlation ID.
- Trace context.
- Payload.

### 13.2. Payload schema

Contract quy định field bắt buộc, type, enum, format và semantics của payload. Producer test xác nhận message phát ra đúng schema; consumer test xác nhận có thể đọc message được công bố.

### 13.3. Ordering và delivery semantics

Nếu thứ tự event có ý nghĩa, contract cần mô tả ordering scope, partition key hoặc aggregate key. Delivery có thể at-most-once, at-least-once hoặc có semantics khác. Consumer thường cần idempotency để xử lý duplicate.

### 13.4. Retry và dead-letter

Contract vận hành có thể mô tả message nào retry được, số lần retry, backoff và điều kiện đưa vào dead-letter queue.

### 13.5. Event evolution

Thêm field optional có thể tương thích nếu consumer bỏ qua field lạ. Đổi ý nghĩa hoặc xóa field đang dùng có thể phá consumer dù schema vẫn parse được.

## 14. Contract testing cho database và repository

Database schema cũng là một contract giữa ứng dụng, migration và các consumer dữ liệu.

Ví dụ repository contract:

~~~text
OrderRepository.findById(orderId)
    returns Order when present
    returns None when absent

OrderRepository.save(order)
    persists required fields
    preserves order identity
~~~

### 14.1. Repository contract suite

Một bộ test dùng chung có thể chạy trên nhiều implementation repository:

- In-memory adapter.
- SQL adapter.
- Document database adapter.
- Remote API adapter.

Mỗi adapter phải tuân thủ cùng semantics quan sát được.

### 14.2. Migration contract

Migration test xác nhận:

- Schema mới có field và constraint đúng.
- Dữ liệu cũ được chuyển đổi đúng.
- Query cũ còn hoạt động trong giai đoạn tương thích.
- Rollback hoặc forward migration có hành vi được định nghĩa.

### 14.3. Database schema là chi tiết nội bộ hay contract?

Nếu chỉ một service sở hữu database, schema có thể là implementation detail. Nếu nhiều service hoặc báo cáo truy cập trực tiếp, schema đã trở thành một contract thực tế và cần quản lý version, ownership và compatibility.

### 14.4. Tránh coupling trực tiếp

Chia sẻ database giữa nhiều service khiến thay đổi schema có thể ảnh hưởng consumer ngoài quyền kiểm soát. API hoặc event contract thường tạo boundary rõ hơn.

## 15. Contract testing cho DSL grammar và compiler

Với một Domain-Specific Language, grammar và semantic model cũng là hợp đồng.

Ví dụ:

~~~text
service "catalog" {
    replicas = 3
}
~~~

Hợp đồng ngôn ngữ có thể quy định:

- Keyword và syntax hợp lệ.
- Precedence của expression.
- Kiểu literal.
- Scope và name resolution.
- Diagnostic code và source range.
- Semantics của default.
- Cách sinh IR hoặc target artifact.

### 15.1. Grammar contract

Parser test xác nhận source hợp lệ được chấp nhận và source sai bị từ chối với diagnostic phù hợp. Khi grammar thay đổi, cần biết thay đổi đó có làm source cũ không còn parse được hay không.

### 15.2. Semantic contract

Hai source có thể parse được nhưng có semantics khác nhau. Contract test cần xác nhận binding, type, default, evaluation và dependency theo đặc tả.

### 15.3. AST contract

Nếu plugin hoặc công cụ ngoài sử dụng AST, shape và node identity có thể là public API. Thay đổi tên node, field hoặc enum có thể phá plugin.

### 15.4. IR contract

Intermediate representation có thể được lưu, cache hoặc trao đổi giữa compiler stages. Nếu IR được dùng xuyên phiên bản, cần version và migration strategy.

### 15.5. Diagnostic contract

IDE, editor và CI có thể phụ thuộc diagnostic code, severity, range và structured metadata. Message text có thể thay đổi ít nhiều, nhưng machine-readable fields cần ổn định theo contract.

### 15.6. Generated code contract

Nếu DSL sinh client SDK hoặc server interface, test cần xác nhận public method, type, nullability và serialization behavior của artifact.

## 16. Contract test và các loại test khác

Các loại test có mục tiêu khác nhau và bổ sung cho nhau.

| Loại test | Phạm vi | Câu hỏi chính |
|---|---|---|
| Unit test | Hàm hoặc class | Logic cục bộ có đúng không? |
| Component test | Một component cùng dependency test | Component có hoạt động độc lập không? |
| Contract test | Ranh giới provider-consumer | Hai bên có cùng tuân thủ interface không? |
| Integration test | Nhiều thành phần thật | Các thành phần có phối hợp được không? |
| End-to-end test | Luồng hệ thống hoàn chỉnh | Người dùng có hoàn tất nghiệp vụ không? |
| Performance test | Tải và tài nguyên | Hệ thống đáp ứng dưới tải ra sao? |
| Security test | Quyền và threat | Hệ thống chống được hành vi trái phép không? |

### 16.1. Contract test và mock

Mock có thể giúp unit test chạy nhanh, nhưng mock thường được viết theo giả định của consumer. Nếu mock không khớp provider thật, test có thể pass dù tích hợp sẽ fail.

Contract test xác minh mock hoặc expectation với provider contract. Một số hệ thống có thể generate mock từ contract để giảm drift.

### 16.2. Contract test và integration test

Contract test thường nhỏ hơn integration test và tập trung vào interface. Integration test vẫn cần để xác nhận transaction, network, authentication và nhiều dependency hoạt động cùng nhau.

### 16.3. Contract test và end-to-end test

E2E test kiểm tra hành vi xuyên nhiều lớp nhưng thường chậm và dễ bị ảnh hưởng bởi môi trường. Contract test có thể phát hiện mismatch sớm hơn, giảm số lượng E2E cần thiết nhưng không loại bỏ hoàn toàn E2E.

## 17. Test double, mock và stub

Test double thay thế một dependency trong test. Các loại thường gặp:

- **Stub:** trả dữ liệu cố định cho lời gọi.
- **Mock:** ghi nhận lời gọi và xác minh interaction.
- **Fake:** implementation đơn giản nhưng hoạt động thật trong phạm vi nhỏ.
- **Service virtualization:** mô phỏng service từ contract hoặc behavior model.

### 17.1. Dùng test double đúng ranh giới

Consumer unit test có thể dùng stub để mô phỏng response. Nhưng provider contract verification cần chạy trên provider implementation thực tế.

### 17.2. Mock không phải nguồn chân lý

Nếu mock được chỉnh để làm test pass mà không cập nhật contract hoặc provider, mismatch vẫn tồn tại. Contract nên là artifact được quản lý, không chỉ là kỳ vọng trong một mock class.

### 17.3. Fake implementation

Fake repository hữu ích cho test nghiệp vụ, nhưng cần chạy shared contract suite để xác nhận fake và database adapter có cùng semantics.

## 18. Contract compatibility và versioning

Contract thay đổi theo thời gian. Một thay đổi tương thích với consumer cũ thường được gọi là backward-compatible. Một thay đổi yêu cầu consumer cập nhật thường là breaking change.

### 18.1. Thay đổi thường tương thích

Tùy contract và quy tắc consumer:

- Thêm endpoint mới.
- Thêm response field optional.
- Thêm enum value nếu consumer xử lý unknown value.
- Thêm request field optional có default.
- Thêm metadata không ảnh hưởng semantics.

Không có thay đổi nào tự động an toàn trong mọi hệ thống. Ví dụ thêm enum value có thể phá client dùng exhaustive switch.

### 18.2. Thay đổi thường phá tương thích

- Xóa endpoint hoặc field đang dùng.
- Đổi tên field.
- Đổi kiểu dữ liệu.
- Chuyển field optional thành required.
- Thu hẹp range hợp lệ.
- Đổi semantics của status code.
- Thay đổi error format.
- Thay đổi thứ tự message khi ordering được bảo đảm.
- Đổi field number trong Protocol Buffers.

### 18.3. Semantic breaking change

Một thay đổi có thể giữ schema nhưng đổi ý nghĩa. Ví dụ total trước đây là giá trị đã gồm thuế, sau đó chuyển thành chưa gồm thuế. JSON Schema vẫn hợp lệ nhưng consumer tính toán sai.

### 18.4. Versioning strategy

Có thể version qua:

- URL path như /v1 và /v2.
- Header hoặc media type.
- Schema version trong message envelope.
- Package/module version.
- DSL language version.
- Compiler plugin API version.

Versioning cần đi cùng deprecation policy và thời gian migration.

## 19. Backward compatibility và forward compatibility

**Backward compatibility** thường hỏi liệu phiên bản mới có tiếp tục hỗ trợ consumer hoặc dữ liệu cũ hay không.

**Forward compatibility** hỏi liệu consumer hoặc reader cũ có xử lý được dữ liệu được tạo bởi phiên bản mới hay không.

Ví dụ:

- Reader mới đọc message cũ: backward compatibility của reader.
- Reader cũ đọc message mới: forward compatibility của reader.

Các thuật ngữ có thể được dùng khác nhau giữa công nghệ; tài liệu dự án cần nói rõ chiều tương thích đang xét.

### 19.1. Unknown field

Consumer có thể bỏ qua field chưa biết để hỗ trợ schema mở rộng. Với một số format hoặc API strict, unknown field có thể bị từ chối.

### 19.2. Enum evolution

Consumer nên có behavior rõ khi nhận enum value mới. Có thể dùng fallback, unknown variant hoặc báo lỗi có kiểm soát.

### 19.3. Default evolution

Thay đổi default có thể đổi semantics của dữ liệu cũ không khai báo field đó. Default cần được xem là một phần contract.

### 19.4. Consumer capability

Một provider có thể cung cấp nhiều version. Contract registry có thể lưu phiên bản consumer đang hỗ trợ để xác định có thể bỏ endpoint cũ hay chưa.

## 20. Contract registry và contract broker

Trong hệ thống nhiều service, contract có thể được lưu ở repository, package registry hoặc contract broker.

Một registry có thể quản lý:

- Provider name.
- Consumer name.
- Contract version.
- Schema artifact.
- Branch hoặc commit.
- Verification result.
- Deployment version.
- Compatibility matrix.
- Deprecation state.

### 20.1. Publish contract

Consumer pipeline publish contract sau khi test. Contract cần gắn với commit hoặc version để provider biết nó đến từ đâu.

### 20.2. Provider verification result

Provider publish kết quả xác minh gồm version provider, contract version, test environment và thời điểm kiểm tra.

### 20.3. Compatibility matrix

Registry có thể hiển thị provider version nào tương thích với consumer version nào.

### 20.4. Broker không thay thế source control

Contract broker lưu và phân phối artifact. Source definition, review và lịch sử thay đổi vẫn cần được quản lý trong quy trình phát triển.

## 21. Contract testing trong CI/CD

Contract test nên chạy đủ sớm để ngăn breaking change đi tới môi trường dùng chung.

Pipeline minh họa:

~~~mermaid
flowchart TD
    A[Commit] --> B[Unit tests]
    B --> C[Generate or load contract]
    C --> D[Consumer contract tests]
    D --> E[Provider verification]
    E --> F[Compatibility check]
    F --> G{Compatible?}
    G -->|No| H[Fail and report mismatch]
    G -->|Yes| I[Build artifact]
    I --> J[Integration tests]
    J --> K[Release candidate]
~~~

### 21.1. Consumer pipeline

Consumer có thể:

1. Chạy unit test với stub.
2. Tạo hoặc cập nhật contract.
3. Validate contract schema.
4. Publish contract theo commit/branch.

### 21.2. Provider pipeline

Provider có thể:

1. Build implementation.
2. Start provider test instance.
3. Lấy contract consumer cần verify.
4. Thiết lập provider state.
5. Chạy interactions.
6. Publish verification result.
7. Chặn release nếu contract bắt buộc không tương thích.

### 21.3. Main branch và deployed version

Một provider có thể pass contract với source main nhưng version đang deploy ở production vẫn cũ. Pipeline cần phân biệt verified version, released version và deployed version.

### 21.4. Branch-aware verification

Contract từ branch thử nghiệm có thể được kiểm tra trước khi merge. Cần xác định policy cho contract branch tạm thời, tránh xóa hoặc bỏ sót consumer contract đang được phát triển.

### 21.5. Gating theo môi trường

Test có thể chạy ở CI, staging hoặc trước production. Không nên đợi đến production mới phát hiện response schema không tương thích.

## 22. Contract testing cho nhiều phiên bản cùng tồn tại

Trong rolling deployment, phiên bản cũ và mới có thể cùng chạy trong một khoảng thời gian. Event producer và consumer cũng có thể được cập nhật lệch thời điểm.

Vì vậy, compatibility cần xét các cặp:

- Consumer cũ với provider mới.
- Consumer mới với provider cũ.
- Producer cũ với consumer mới.
- Producer mới với consumer cũ.

### 22.1. Expand-contract

Một quy trình thay đổi an toàn có thể:

1. Thêm field mới mà không xóa field cũ.
2. Deploy provider hỗ trợ cả hai.
3. Deploy consumer chuyển sang field mới.
4. Theo dõi consumer cũ đã ngừng sử dụng field cũ.
5. Xóa field cũ trong một release sau khi hết thời gian tương thích.

### 22.2. Dual read và dual write

Trong một số migration dữ liệu, consumer có thể đọc cả field cũ và mới; producer có thể ghi cả hai trong thời gian chuyển đổi. Cần quy định nguồn nào là authoritative và khi nào dừng dual mode.

### 22.3. Compatibility window

Contract có thể công bố thời gian hỗ trợ nhiều phiên bản. Client cần biết thời điểm ngừng hỗ trợ và cách migrate.

## 23. Contract testing cho error và retry behavior

Error là một phần của API contract. Nếu provider trả error khác cấu trúc hoặc thay đổi retry semantics, consumer có thể xử lý sai.

Ví dụ error contract:

~~~json
{
  "code": "ORDER_NOT_FOUND",
  "message": "The requested order does not exist.",
  "correlationId": "req-901"
}
~~~

### 23.1. Stable error code

Consumer nên dựa vào code ổn định thay vì parse message text. Message có thể được chỉnh sửa hoặc dịch ngôn ngữ.

### 23.2. Retryability

Contract cần xác định lỗi nào retry được. Ví dụ 429 hoặc một số 503 có thể retry sau Retry-After; lỗi validation 400 thường không nên retry nguyên request.

### 23.3. Idempotency

Với operation tạo hoặc thanh toán, retry có thể tạo side effect lặp. Contract có thể yêu cầu idempotency key và quy định thời hạn lưu key.

### 23.4. Timeout

Consumer cần biết timeout expectation và provider cần biết cách xử lý request vẫn chạy sau khi client timeout. Timeout không tự động hủy operation phía server.

### 23.5. Error detail và security

Contract nên giới hạn thông tin lỗi được công khai. Không trả stack trace, SQL text, secret hoặc internal host name cho consumer không được phép.

## 24. Contract testing cho security và authorization

Một interface có thể đúng schema nhưng sai về quyền.

Contract security có thể mô tả:

- Authentication scheme.
- Required role/scope.
- Tenant context.
- Field visibility.
- Resource ownership.
- Rate limits.
- Audit behavior.

### 24.1. Positive authorization cases

Kiểm tra caller có quyền truy cập resource được phép và nhận đúng representation.

### 24.2. Negative authorization cases

Kiểm tra caller không thể:

- Đọc resource của tenant khác.
- Thay đổi owner field không được phép.
- Gọi admin operation bằng token thông thường.
- Truy cập field nhạy cảm.
- Bỏ qua policy bằng query parameter.

### 24.3. Authentication failure

Kiểm tra token thiếu, sai, hết hạn hoặc không đủ scope. Contract cần định nghĩa status và error shape.

### 24.4. Security contract không chỉ là schema

JSON Schema có thể xác nhận field userId là string, nhưng không thể tự chứng minh user hiện tại có quyền đọc dữ liệu tương ứng. Cần test với identity và authorization policy thực tế.

## 25. Contract test cho DSL compiler API và plugin

Compiler có thể expose API để plugin truy cập AST, register rule, nhận diagnostics hoặc sinh code. Đây là một contract riêng.

Ví dụ interface khái niệm:

~~~typescript
interface CompilerPlugin {
  name: string;
  apiVersion: string;
  initialize(context: PluginContext): void;
  analyze(module: ModuleNode): Diagnostic[];
}
~~~

Contract test có thể xác nhận:

- Plugin API version được nhận diện đúng.
- Lifecycle callback được gọi theo thứ tự.
- Context cung cấp đúng capability.
- AST node có field và type đã công bố.
- Diagnostic schema không đổi ngoài compatibility policy.
- Plugin lỗi được cô lập theo quy định.
- Cancellation và resource limit được tôn trọng.

### 25.1. AST evolution

Nếu thêm node type, plugin cũ có thể gặp unknown node. API cần quy định plugin phải có default handler hay compiler phải từ chối version không hỗ trợ.

### 25.2. Binary compatibility

Plugin biên dịch thành binary có thể phụ thuộc ABI, runtime version hoặc package version. Contract test cần kiểm tra version range được hỗ trợ.

### 25.3. Capability contract

Plugin có thể được cấp quyền đọc file, network hoặc ghi artifact. Capability cần được khai báo và test; không nên để plugin mặc định có toàn bộ quyền của compiler process.

## 26. Contract test cho generated client SDK

DSL hoặc API schema có thể sinh client SDK cho nhiều ngôn ngữ.

Contract test nên xác nhận:

- Operation name và method.
- URL/path construction.
- Query/header encoding.
- Request serialization.
- Response deserialization.
- Error mapping.
- Optional và nullable field.
- Enum unknown value behavior.
- Authentication hook.

### 26.1. Generated code compile test

Generated SDK nên compile với toolchain version được hỗ trợ. Compile thành công không chứng minh wire behavior đúng, nhưng phát hiện nhiều breaking change ở public API.

### 26.2. Runtime compatibility test

Chạy SDK trên provider test instance hoặc contract mock để xác nhận request/response behavior.

### 26.3. Golden generated artifact

Có thể so sánh generated public surface hoặc schema output với golden artifact. Cần review diff có ý nghĩa thay vì khóa mọi whitespace hoặc comment.

### 26.4. Nhiều ngôn ngữ

Nếu DSL sinh Java, TypeScript, Python hoặc Kotlin SDK, mỗi generator cần cùng contract suite để tránh semantics lệch giữa các ngôn ngữ.

## 27. Contract test cho data pipeline và file exchange

Một số hệ thống không giao tiếp qua API trực tiếp mà trao đổi file CSV, JSON, Parquet hoặc một định dạng nội bộ.

Data contract có thể quy định:

- File naming convention.
- Schema và column type.
- Encoding.
- Delimiter và quoting.
- Header presence.
- Null representation.
- Partition key.
- Timestamp semantics.
- Compression.
- Version metadata.
- Data quality constraints.

### 27.1. Schema test

Kiểm tra file output có đúng schema và không thiếu column bắt buộc.

### 27.2. Data quality contract

Ngoài schema, có thể quy định:

- Primary key không null.
- Record count nằm trong range kỳ vọng.
- Foreign key reference hợp lệ.
- Timestamp không nằm ngoài khoảng.
- Giá trị enum thuộc tập cho phép.

### 27.3. Producer/consumer coordination

Producer publish schema version trước khi phát file. Consumer xác nhận version được hỗ trợ và báo lỗi rõ nếu không thể đọc.

### 27.4. Schema registry

Registry có thể quản lý schema version và compatibility mode như backward, forward hoặc full compatibility. Cần chọn mode phù hợp với thứ tự deploy producer/consumer.

## 28. Test contract với schema registry và serialization format

Một số serialization format có schema registry hoặc schema ID trong message.

Contract verification cần kiểm tra:

- Schema được đăng ký đúng subject.
- Version mới đáp ứng compatibility policy.
- Producer serialize theo schema đã đăng ký.
- Consumer deserialize được dữ liệu từ version được hỗ trợ.
- Schema ID được gắn đúng vào payload/envelope.

Với Protocol Buffers, field number là định danh wire. Với Avro, reader/writer schema resolution có quy tắc riêng. Với JSON Schema, semantics của required, additionalProperties và union type cần được thống nhất.

Không nên áp dụng một quy tắc compatibility chung cho mọi format.

## 29. Chọn công cụ và framework

Công cụ phụ thuộc loại interface:

| Loại contract | Công cụ hoặc định dạng thường gặp |
|---|---|
| HTTP API | OpenAPI, Pact, Dredd hoặc schema validator |
| Event API | AsyncAPI, schema registry, Avro/Protobuf tooling |
| JSON data | JSON Schema validator |
| RPC | Protocol Buffers và gRPC tooling |
| GraphQL | Schema validation và operation checks |
| DSL grammar | Parser test, grammar test, golden AST |
| Compiler/plugin API | API compatibility checker và integration harness |
| Database | Migration test, repository contract suite |

Tên công cụ là ví dụ. Nên chọn theo runtime, ngôn ngữ, CI và mức độ phức tạp của hệ thống.

### 29.1. Tiêu chí lựa chọn

- Có hỗ trợ provider và consumer workflow không?
- Có thể lưu và version contract không?
- Có kiểm tra compatibility tự động không?
- Có hỗ trợ nhiều branch và nhiều consumer không?
- Có tích hợp CI/CD không?
- Có thể chạy offline hoặc trong môi trường nội bộ không?
- Có hỗ trợ format và protocol mà hệ thống sử dụng không?
- Có cung cấp diagnostics dễ hiểu không?

### 29.2. Không phụ thuộc quá mức vào framework

Hợp đồng nên độc lập với implementation framework khi có thể. Nếu đổi framework server, contract và consumer expectations vẫn nên giữ nguyên.

## 30. Thiết kế bộ contract test

Một bộ contract test hữu ích cần tập trung vào những điều consumer thực sự phụ thuộc và các quy tắc bắt buộc của provider.

Một cấu trúc test có thể gồm:

~~~text
contract-tests/
    api/
        orders-create.contract
        orders-get.contract
    schemas/
        order.schema.json
        error.schema.json
    events/
        order-created.schema.json
    compiler/
        parser.contract
        diagnostic.contract
    compatibility/
        previous-release/
~~~

Đây là cách tổ chức minh họa; tên và extension phụ thuộc toolchain.

### 30.1. Positive interactions

Test các request hợp lệ và response đúng contract.

### 30.2. Negative interactions

Test input sai, quyền thiếu, resource không tồn tại và error response.

### 30.3. Boundary values

Test giá trị min/max, collection rỗng, chuỗi dài, Unicode, timestamp biên và precision.

### 30.4. Compatibility fixtures

Giữ payload hoặc schema của release cũ để test phiên bản mới đọc được theo policy.

### 30.5. Consumer coverage

Ghi nhận consumer nào dùng operation hoặc field nào. Điều này giúp đánh giá tác động khi thay đổi.

## 31. Tránh false confidence và test quá chặt

Contract testing có thể tạo cảm giác an toàn giả nếu contract không phản ánh thực tế hoặc test chỉ kiểm tra một phần nhỏ.

Các vấn đề thường gặp:

- Contract được viết theo implementation hiện tại thay vì nhu cầu consumer.
- Test chỉ kiểm tra schema mà bỏ qua semantics.
- Provider verification dùng mock thay vì implementation thật.
- Consumer contract khóa toàn bộ response snapshot.
- Không test error và authorization behavior.
- Contract registry không cập nhật theo deployed version.
- Compatibility check bỏ qua consumer cũ.
- Schema thay đổi nhưng generated SDK không được test.

### 31.1. Tránh over-specification

Chỉ đưa vào contract những behavior cần ổn định. Không nên quy định thứ tự JSON properties nếu không có ý nghĩa, hoặc yêu cầu một header nội bộ mà consumer không dùng.

### 31.2. Tránh under-specification

Nếu contract chỉ mô tả field type mà không mô tả nullability, enum evolution, error semantics hoặc idempotency, consumer vẫn có thể hiểu khác provider.

### 31.3. Contract phải có owner

Mỗi contract cần owner chịu trách nhiệm review và version. Nếu không có ownership, schema có thể bị sửa để làm test pass mà không đánh giá ảnh hưởng.

## 32. Diagnostics và báo cáo contract mismatch

Khi contract test thất bại, báo cáo nên chỉ ra:

- Contract name và version.
- Provider/consumer version.
- Operation hoặc message liên quan.
- Expected và actual.
- Field path hoặc protocol detail.
- Compatibility classification.
- Gợi ý cách khắc phục nếu có.

Ví dụ:

~~~text
Contract: orders-api / consumer-web / v3
Interaction: GET /orders/{orderId}

Mismatch:
  Path: $.total
  Expected: number
  Actual: string

Provider version: 4.8.0
Consumer version: 2.3.1
Result: FAILED
~~~

Diagnostics nên tránh in token, secret hoặc payload nhạy cảm. Có thể redact giá trị nhưng vẫn giữ field path và kiểu dữ liệu để chẩn đoán.

## 33. Quy trình xử lý khi contract thay đổi

Khi cần thay đổi API hoặc data schema:

1. Xác định consumer và operation bị ảnh hưởng.
2. Phân loại thay đổi: additive, compatible, deprecated hay breaking.
3. Cập nhật contract và version nếu cần.
4. Thêm hoặc cập nhật consumer expectation.
5. Chạy provider verification.
6. Chạy compatibility check với contract của các consumer được hỗ trợ.
7. Cập nhật generated SDK hoặc schema artifact.
8. Lập migration plan nếu có consumer cũ.
9. Deploy theo thứ tự tương thích.
10. Theo dõi usage và chỉ loại bỏ contract cũ khi không còn consumer cần nó.

### 33.1. Deprecation

Deprecation nên có thông báo, replacement, thời hạn và cách đo usage. Một field không nên bị xóa chỉ vì code search không tìm thấy consumer trong một repository nếu còn consumer bên ngoài.

### 33.2. Breaking change

Breaking change có thể cần major version hoặc endpoint mới. Provider cần duy trì thời gian chạy song song để consumer có thời gian migrate.

### 33.3. Emergency change

Với security fix khẩn cấp, có thể cần thay đổi không tương thích. Quy trình cần ghi nhận risk, consumer impact và phương án phối hợp, thay vì bỏ qua contract mà không có trace.

## 34. Contract testing và observability

Contract test chạy trước deployment, nhưng production vẫn cần theo dõi hành vi thực tế.

Observability có thể xác nhận:

- Consumer nào đang gọi operation nào.
- Tỷ lệ request theo API version.
- Error code và status distribution.
- Event schema version đang được phát.
- Consumer lag và dead-letter count.
- Deserialization failure.
- Unknown enum hoặc field usage nếu được instrument.

### 34.1. Usage-based deprecation

Trước khi xóa endpoint cũ, telemetry có thể cho biết consumer nào còn sử dụng. Cần bảo vệ privacy và tránh log payload nhạy cảm.

### 34.2. Contract violation trong production

Runtime validation có thể phát hiện message hoặc response không khớp schema. Hệ thống cần quyết định reject, quarantine, log hoặc route sang dead-letter queue.

### 34.3. Monitoring không thay thế pre-release tests

Phát hiện mismatch trong production đã quá muộn đối với một số lỗi. Monitoring bổ sung bằng chứng vận hành nhưng không thay thế contract verification trước release.

## 35. Ví dụ tổng hợp: DSL mô tả và kiểm thử API đơn hàng

Giả sử DSL khai báo:

~~~text
model OrderResponse {
    id: String
    status: OrderStatus
    total: Decimal
    createdAt: Timestamp
}

model ErrorResponse {
    code: String
    message: String
    correlationId: String?
}

api OrdersApi {
    get "/orders/{orderId}" {
        input {
            orderId: String
        }

        response 200: OrderResponse
        response 404: ErrorResponse
        response 401: ErrorResponse
    }
}
~~~

Compiler có thể sinh API schema và server/client interfaces.

### 35.1. Contract expectations phía consumer

Consumer web cần:

- GET /orders/{orderId}.
- Response 200 chứa id, status, total.
- Response 404 có error code.
- Response 401 khi token không hợp lệ.

### 35.2. Provider verification

Provider test có thể thiết lập:

~~~text
given order "ord-100" exists for tenant "tenant-a"
when authenticated tenant "tenant-a" requests GET /orders/ord-100
then status is 200
and body conforms to OrderResponse
~~~

Một trường hợp khác:

~~~text
given order "ord-200" belongs to tenant "tenant-b"
when authenticated tenant "tenant-a" requests GET /orders/ord-200
then access is denied according to the API policy
~~~

### 35.3. Schema compatibility

Nếu phiên bản tiếp theo thêm field optional:

~~~text
source: String?
~~~

Provider cần xác nhận response mới vẫn đáp ứng consumer cũ và serializer không làm thay đổi các field hiện có.

### 35.4. Generated SDK

Test compile SDK, serialize path parameter, deserialize Decimal và map ErrorResponse. Chạy SDK với provider test instance để xác nhận wire behavior.

### 35.5. CI gate

Pipeline có thể:

1. Compile DSL.
2. Generate OpenAPI và SDK.
3. Validate schema.
4. Run consumer contract.
5. Run provider verification.
6. Check compatibility với release contract.
7. Publish artifact khi các bước bắt buộc pass.

## 36. Quy trình xây dựng contract testing cho một dự án

Có thể triển khai theo các bước:

1. **Lập bản đồ ranh giới:** liệt kê API, message, schema, repository, plugin và compiler interface.
2. **Xác định provider/consumer:** ghi owner và consumer phụ thuộc.
3. **Chọn contract source:** DSL, OpenAPI, JSON Schema, AsyncAPI hoặc IDL.
4. **Đặc tả input/output:** type, required, nullable, constraints và serialization.
5. **Đặc tả behavior:** status, error, retry, idempotency, ordering và side effect.
6. **Đặc tả security:** authentication, authorization, tenant và data visibility.
7. **Viết consumer expectation:** chỉ giữ những behavior consumer thực sự cần.
8. **Viết provider verification:** chạy trên implementation thật hoặc boundary adapter.
9. **Quản lý version:** compatibility mode, deprecation và migration.
10. **Tích hợp CI:** publish contract, verify provider và chặn breaking change.
11. **Theo dõi deployment:** biết version nào đang chạy và consumer nào còn sử dụng.
12. **Review định kỳ:** loại bỏ contract không còn dùng theo quy trình an toàn.

## 37. Những lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ test provider nội bộ | Consumer vẫn có thể hiểu khác | Kiểm tra contract tại ranh giới |
| Chỉ dựa vào mock | Mock lệch implementation thật | Provider verification |
| Contract khóa toàn bộ response | Khó thêm field và mở rộng API | Chỉ ràng buộc phần public contract |
| Không mô tả nullability | Consumer xử lý null/absent sai | Đặc tả presence semantics |
| Không test error response | Client parse lỗi không đúng | Đưa error vào contract |
| Bỏ qua behavior | Schema đúng nhưng semantics sai | Bổ sung behavioral contract |
| Không xác minh authorization | Data leak dù schema hợp lệ | Test identity và access policy |
| Không quản lý version | Không biết consumer nào tương thích | Version và compatibility matrix |
| Xóa field ngay khi không thấy dùng | Consumer ngoài hệ thống bị hỏng | Deprecation và usage tracking |
| Không kiểm tra generated SDK | Schema và client lệch nhau | Generator contract tests |
| Test chỉ trên một backend | Backend khác serialize khác | Shared suite cho từng adapter |
| Không lưu provider state | Test phụ thuộc thứ tự và dữ liệu | Fixture setup deterministic |
| Dùng message text làm API | Đổi câu chữ làm consumer hỏng | Error code ổn định |
| Không ghi deployed version | Kết quả CI không phản ánh production | Liên kết verification với release/deployment |
| Bỏ qua schema evolution | Producer và consumer deploy lệch thời điểm bị lỗi | Compatibility mode và cross-version tests |

## 38. Tiêu chí của một chiến lược contract testing tốt

Một chiến lược tốt xác định rõ ai cung cấp interface, ai sử dụng interface, dữ liệu và hành vi nào được bảo đảm, cũng như cách kiểm tra tương thích qua từng phiên bản. Contract có owner, được version hóa, có thể chạy tự động và gắn với artifact thực tế đang phát hành.

Các câu hỏi quan trọng:

- Provider, consumer và boundary đã được xác định chưa?
- Contract có phải source of truth rõ ràng không?
- Request, response, event và error có schema cụ thể không?
- Required, optional, nullable, default và unknown field được định nghĩa ra sao?
- Behavior như retry, idempotency, ordering và side effect có được mô tả không?
- Consumer-driven contract có phản ánh đúng nhu cầu thực tế không?
- Provider verification chạy trên implementation nào?
- Generated client, AST hoặc compiler plugin API có contract riêng không?
- Compatibility được kiểm tra theo chiều và version nào?
- CI có chặn breaking change trước release không?
- Contract registry có gắn kết quả với deployed version không?
- Có deprecation, migration và usage tracking không?
- Authorization và tenant isolation có được kiểm tra không?
- Diagnostics có chỉ ra mismatch mà không làm lộ dữ liệu nhạy cảm không?

Kiểm thử hợp đồng giúp các thành phần phát triển độc lập mà vẫn giữ được thỏa thuận tại ranh giới giao tiếp. Trong một hệ sinh thái DSL, hợp đồng có thể bao phủ grammar, API, schema, serialization, event, compiler extension và runtime adapter. Khi contract được đặc tả rõ, version hóa và xác minh tự động, thay đổi có thể được đánh giá trước khi phát hành, consumer có thể nâng cấp có kế hoạch và hệ thống giữ được khả năng tương thích khi tiếp tục mở rộng.
