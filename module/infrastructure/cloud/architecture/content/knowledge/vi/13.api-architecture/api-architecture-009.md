# Kiểm thử hợp đồng và quản lý vòng đời API

## 1. Vì sao API cần hợp đồng và vòng đời rõ ràng?

API là ranh giới giao tiếp giữa các thành phần có thể được phát triển và triển khai độc lập: web/mobile client, backend service, đối tác tích hợp, worker, hệ thống dữ liệu và API gateway. Một thay đổi nhỏ như đổi tên field, chuyển kiểu dữ liệu hoặc thay mã lỗi có thể khiến consumer đang hoạt động bị lỗi, dù provider vẫn build và deploy thành công.

Trong module **CLOUD_ARCHITECTURE**, thiết kế API gắn với kiến trúc mạng, compute, dữ liệu, bảo mật, khả năng mở rộng và vận hành. Do đó, API không chỉ cần chạy được hôm nay; nó cần có hợp đồng có thể kiểm tra, quy trình thay đổi có thể dự đoán và chính sách hỗ trợ consumer trong suốt vòng đời.

**API contract** mô tả cách hai phía giao tiếp: endpoint hoặc operation, phương thức, tham số, cấu trúc request/response, kiểu dữ liệu, mã trạng thái, xác thực, lỗi và các quy tắc quan trọng khác. **Contract testing** kiểm tra việc triển khai có tuân thủ những kỳ vọng đã thống nhất. **API lifecycle management** quản lý các giai đoạn thiết kế, phát hành, vận hành, thay đổi, deprecate và retire.

Sau bài này, bạn có thể:

- Phân biệt API specification, provider contract, consumer expectation và implementation test.
- Thiết kế hợp đồng REST/HTTP rõ ràng bằng OpenAPI và ví dụ request/response.
- Chọn kiểm thử schema, consumer-driven contract, provider verification và integration test phù hợp.
- Đánh giá thay đổi là backward-compatible hay breaking change.
- Xây chính sách versioning, deprecation, thông báo, migration và retirement.
- Tích hợp contract tests vào CI/CD, API gateway và quy trình quản trị.
- Đánh giá trade-off giữa tốc độ phát triển, khả năng tương thích, bảo mật, chi phí và vận hành theo tư duy Well-Architected.

## 2. API contract gồm những gì?

Một hợp đồng API tốt phải đủ cụ thể để hai nhóm độc lập có thể triển khai mà không cần đoán ý nhau. Với REST/HTTP, hợp đồng thường mô tả:

| Thành phần | Nội dung cần thống nhất | Ví dụ |
|---|---|---|
| Resource và operation | URI, HTTP method, ý nghĩa nghiệp vụ | `GET /v1/bookings/{bookingId}` |
| Request | Path/query/header/body, kiểu dữ liệu, trường bắt buộc | `bookingId` là UUID; `Idempotency-Key` khi tạo đơn |
| Response | Status code, header, body, nullability và collection | `200` với Booking; `404` khi không tìm thấy/không được phép theo chính sách |
| Error model | Cấu trúc lỗi ổn định, mã lỗi máy đọc được | `code`, `message`, `traceId`, `details` |
| Authentication | Cách chứng minh danh tính | OAuth 2.0 bearer token |
| Authorization | Quyền nào được thực hiện trên resource | Chỉ chủ đơn hoặc nhân viên có quyền mới xem |
| Semantics | Idempotency, pagination, ordering, concurrency, retry | Lặp POST cùng key không tạo đơn thứ hai |
| Operational behavior | Timeout, rate limit, quota, caching, deprecation | `429` kèm `Retry-After` khi phù hợp |
| Compatibility | Quy tắc thêm/bỏ/sửa field, enum và endpoint | Field mới optional; consumer cũ bỏ qua được |

Không phải mọi API đều dùng REST. gRPC có Protocol Buffers và service definitions; GraphQL có schema và operation; event API có event schema, topic, key và delivery semantics. Nguyên tắc chung là **hợp đồng phải mô tả cả cấu trúc lẫn hành vi mà consumer thực sự phụ thuộc**.

### 2.1. Phân biệt specification và contract đang được thực thi

- **API specification** (ví dụ OpenAPI) là tài liệu máy đọc được về interface.
- **Provider contract** là tập quy tắc provider cam kết thực hiện: endpoint, schema, response, error, authorization và semantics.
- **Consumer expectation** là phần consumer thực sự sử dụng hoặc yêu cầu: các field cần có, status code được xử lý, thứ tự event, timeout và behavior.
- **Implementation** là code, gateway, middleware, service và dependency đang chạy.
- **Contract test** kiểm tra implementation có phù hợp với specification/expectation liên quan.

OpenAPI hợp lệ về cú pháp chưa chứng minh server thực tế trả đúng response. Ngược lại, một test gọi endpoint thành công chưa chứng minh mọi consumer được hỗ trợ. Cần kiểm tra hợp đồng ở cả phía provider và consumer, đồng thời có integration test cho hành vi phụ thuộc.

## 3. Ví dụ hợp đồng API cho BookingCloud

Giả sử ứng dụng đặt lịch thuê thiết bị có API tra cứu và tạo booking. Hợp đồng nên nói rõ loại field, trạng thái và quyền truy cập.

### 3.1. Request và response minh họa

Tạo một booking:

~~~http
POST /v1/bookings HTTP/1.1
Host: api.booking.example.com
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: 6c78f6f0-12c3-4f25-8ed7-6c9c1f6e0101

{
  "deviceId": "dev-017",
  "slotId": "slot-2026-12-02-0900",
  "note": "Giao tại quầy"
}
~~~

Response thành công:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /v1/bookings/bkg-8124

{
  "id": "bkg-8124",
  "deviceId": "dev-017",
  "slotId": "slot-2026-12-02-0900",
  "status": "confirmed",
  "createdAt": "2026-11-18T09:00:00Z"
}
~~~

Các giá trị trong ví dụ là dữ liệu giả định. Hợp đồng thực tế cần định nghĩa rõ:

- `deviceId` và `slotId` có định dạng nào, có phân biệt hoa thường không, và có giới hạn độ dài không.
- `note` optional hay được phép null; giới hạn độ dài và nội dung nào bị từ chối.
- `Idempotency-Key` được giữ trong bao lâu, phạm vi key theo user hay client, và điều gì xảy ra nếu cùng key nhưng payload khác.
- `201 Created` chỉ được trả sau khi đơn đã commit bền vững; email thông báo có thể được xử lý bất đồng bộ.
- Nếu slot đã được người khác đặt, trả lỗi conflict theo hợp đồng; không chỉ trả HTTP 200 với một chuỗi mô tả tự do.

### 3.2. Error model ổn định

Một error response có thể dùng cấu trúc chung:

~~~json
{
  "code": "SLOT_UNAVAILABLE",
  "message": "Khung giờ không còn khả dụng.",
  "traceId": "01JCV2N7X5",
  "details": {
    "slotId": "slot-2026-12-02-0900"
  }
}
~~~

Không đưa stack trace, SQL, tên host nội bộ, token hay dữ liệu cá nhân không cần thiết vào response. `message` dành cho hiển thị/log phù hợp; client nên dựa vào `code` ổn định để xử lý logic thay vì phân tích câu chữ.

| Status code | Ý nghĩa trong ví dụ | Consumer nên làm gì |
|---|---|---|
| `400 Bad Request` | Body hoặc tham số không hợp lệ | Sửa input; không retry y nguyên |
| `401 Unauthorized` | Thiếu hoặc không hợp lệ thông tin xác thực | Làm mới/đăng nhập theo flow |
| `403 Forbidden` | Đã xác thực nhưng không có quyền | Không retry như lỗi mạng |
| `404 Not Found` | Resource không tồn tại hoặc bị ẩn theo chính sách | Xử lý theo semantics đã thống nhất |
| `409 Conflict` | Slot đã bị đặt hoặc xung đột trạng thái | Hiển thị xung đột; chọn slot khác |
| `429 Too Many Requests` | Vượt rate limit/quota | Backoff và tuân thủ `Retry-After` nếu có |
| `5xx` | Provider hoặc dependency gặp lỗi | Retry có giới hạn khi operation an toàn |

Status code là một phần của contract. Không đổi `409` thành `400` chỉ vì muốn gom mọi lỗi vào một nhóm; consumer có thể đang dùng mã đó để hiển thị trạng thái tranh chấp.

### 3.3. OpenAPI specification rút gọn

~~~yaml
openapi: 3.1.0
info:
  title: Booking API
  version: 1.0.0
paths:
  /v1/bookings:
    post:
      operationId: createBooking
      summary: Create a booking
      security:
        - bearerAuth: []
      parameters:
        - in: header
          name: Idempotency-Key
          required: true
          schema:
            type: string
            minLength: 16
            maxLength: 128
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/CreateBookingRequest"
      responses:
        "201":
          description: Booking created
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/Booking"
        "409":
          description: Slot conflict
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ApiError"
        "429":
          description: Rate limited
          headers:
            Retry-After:
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ApiError"
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
  schemas:
    CreateBookingRequest:
      type: object
      additionalProperties: false
      required: [deviceId, slotId]
      properties:
        deviceId:
          type: string
          minLength: 1
        slotId:
          type: string
          minLength: 1
        note:
          type: string
          maxLength: 500
    Booking:
      type: object
      required: [id, deviceId, slotId, status, createdAt]
      properties:
        id:
          type: string
        deviceId:
          type: string
        slotId:
          type: string
        status:
          type: string
          enum: [pending, confirmed, cancelled]
        createdAt:
          type: string
          format: date-time
    ApiError:
      type: object
      required: [code, message, traceId]
      properties:
        code:
          type: string
        message:
          type: string
        traceId:
          type: string
        details:
          type: object
          additionalProperties: true
~~~

Đây là ví dụ rút gọn để minh họa cách mô tả API, chưa phải specification hoàn chỉnh cho production. Cần bổ sung server, operation cho đọc/cập nhật/hủy, security scopes, response lỗi đầy đủ, pagination, schema format chính xác và các quy tắc nghiệp vụ. Đặc biệt, `additionalProperties: false` ở request có thể khiến việc thêm field bị xem là breaking với validator/consumer nghiêm ngặt; phải chọn policy phù hợp.

## 4. Các loại kiểm thử hợp đồng

### 4.1. Schema/specification validation

Kiểm tra OpenAPI/AsyncAPI/Protobuf có hợp lệ: tham chiếu schema, kiểu dữ liệu, required fields, response definitions, security scheme và format. Nó phát hiện tài liệu sai cú pháp hoặc thiếu cấu trúc, nhưng không xác nhận implementation thật tuân thủ.

### 4.2. Provider contract test

Chạy test trực tiếp với provider implementation để xác minh endpoint thực tế:

- Response status và content type đúng specification.
- JSON field/type/required constraints đúng.
- Headers như `Location`, `Retry-After`, cache/security headers phù hợp.
- Authentication/authorization được áp dụng đúng.
- Error response giữ cấu trúc ổn định.
- Các semantics quan trọng như idempotency, pagination và concurrency hoạt động.

Provider test nên chạy trong CI hoặc môi trường kiểm thử có dữ liệu kiểm soát. Không dùng dữ liệu production nhạy cảm chỉ để kiểm tra contract.

### 4.3. Consumer-driven contract testing

Consumer-driven contract (CDC) bắt đầu từ những gì consumer thực sự cần. Consumer định nghĩa kỳ vọng về request/response/event mà nó sử dụng; provider xác minh các kỳ vọng đó trước khi phát hành.

Ví dụ mobile app chỉ đọc các field `id`, `status`, `createdAt`. Một consumer test có thể phát hiện provider bỏ `status` hoặc đổi `createdAt` thành kiểu không còn parse được, dù schema provider vẫn có thêm nhiều field khác.

Luồng điển hình:

~~~mermaid
flowchart LR
    C["Consumer test<br/>Mobile / Web / Partner"] --> PACT["Contract artifact"]
    PACT --> BROKER["Contract broker / registry"]
    PROVIDER["Provider verification<br/>Booking API"] --> BROKER
    BROKER --> COMPAT["Compatibility result"]
    COMPAT --> PIPE["CI/CD release gate"]
~~~

CDC đặc biệt hữu ích khi nhiều team deploy độc lập và provider không thể chạy end-to-end test cho tất cả consumer ở mỗi lần phát hành. Nhưng CDC chỉ kiểm tra các kỳ vọng đã khai báo; nếu consumer không test behavior nào đó, hợp đồng sẽ không tự phát hiện rủi ro ở behavior đó.

### 4.4. Integration và end-to-end testing

Contract tests không thay thế integration test. Chúng thường không chứng minh:

- Authentication provider, database, queue hoặc hệ thống đối tác thật phối hợp đúng trong mọi tình huống.
- Transaction, locking, consistency, timeout và retry giữa nhiều dependency.
- Hiệu năng dưới tải, behavior khi failover hoặc khả năng chịu lỗi toàn hệ thống.
- UI, routing DNS, network policy, WAF và deployment thực tế hoạt động đúng.

Chọn test theo rủi ro:

| Loại test | Phát hiện tốt | Giới hạn |
|---|---|---|
| Specification lint/validation | OpenAPI sai cấu trúc, thiếu field | Không kiểm tra server runtime |
| Provider contract | Implementation không tuân hợp đồng | Có thể thiếu góc nhìn consumer thực tế |
| Consumer-driven contract | Breaking change với các consumer đã khai báo | Không đại diện consumer chưa có test |
| Integration | Dependency và protocol phối hợp không đúng | Môi trường có thể chậm/khó ổn định |
| End-to-end | Hành trình nghiệp vụ xuyên hệ thống | Chậm, dễ flaky, khó xác định lỗi gốc |
| Load/resilience | SLO, saturation, timeout và failover | Tốn tài nguyên; cần mô hình tải đại diện |

Một test pyramid hợp lý có nhiều test unit/schema/contract nhỏ, một số integration quan trọng và ít end-to-end cho hành trình nghiệp vụ cốt lõi.

## 5. Quy trình contract testing trong CI/CD

### 5.1. Pipeline cho provider

~~~mermaid
flowchart TD
    CHANGE["Pull request: code + API spec"] --> LINT["Lint / validate specification"]
    LINT --> DIFF["Compare với phiên bản đã phát hành"]
    DIFF --> PTEST["Provider contract tests"]
    PTEST --> CDC["Verify consumer contracts"]
    CDC --> INT["Integration / security tests"]
    INT --> REVIEW["Review breaking change và release note"]
    REVIEW --> GATE{"Release gate đạt?"}
    GATE -->|"Không"| FIX["Sửa implementation hoặc version/plan"]
    FIX --> LINT
    GATE -->|"Có"| DEPLOY["Deploy canary / staged rollout"]
    DEPLOY --> VERIFY["Smoke + telemetry + rollback check"]
~~~

Một cách sắp xếp công việc:

1. Developer cập nhật code và specification trong cùng pull request.
2. Linter kiểm tra naming, schema, security definitions và quy ước nội bộ.
3. Công cụ diff so sánh với bản contract đã phát hành để phát hiện xóa operation, đổi type, required field hoặc behavior được mô tả.
4. Provider tests chạy trên implementation được build.
5. Provider xác minh consumer contracts đang còn hiệu lực trong registry/broker.
6. Integration/security tests kiểm tra các ranh giới quan trọng.
7. Reviewer xem release note, migration guide, deprecation policy và ngày retire nếu có.
8. Deploy theo canary/staged rollout; theo dõi telemetry trước khi mở rộng.

### 5.2. Pipeline cho consumer

Consumer cũng có trách nhiệm. Khi consumer thay đổi cách gọi API:

- Cập nhật kỳ vọng trong contract artifact.
- Kiểm tra contract với provider version đang hỗ trợ.
- Chạy test xử lý các status code, optional fields, timeout và error code.
- Không giả định mọi field ngoài phần consumer dùng sẽ luôn có hoặc không bao giờ thay đổi.
- Kiểm tra version tối thiểu của provider mà phiên bản consumer mới cần.

Một broker/registry có thể lưu contract artifact, kết quả verification và mapping phiên bản consumer/provider. Release pipeline dùng kết quả đó để đánh giá cặp phiên bản dự kiến tương thích.

### 5.3. Ma trận tương thích trước khi deploy

| Consumer | Provider hiện tại | Provider candidate | Kết luận cần có |
|---|---|---|---|
| Mobile v4 | API v1.2 | API v1.3 | Consumer contract pass? |
| Web v8 | API v1.2 | API v1.3 | Có field/behavior nào bị đổi? |
| Partner X | API v1.2 | API v1.3 | Consumer đã công bố contract hay SLA riêng? |
| Internal worker v3 | API v1.2 | API v1.3 | Retry/idempotency có còn đúng? |

Không nhất thiết mọi consumer phải cập nhật cùng lúc. Mục tiêu là provider candidate tương thích với các consumer trong phạm vi hỗ trợ đã công bố, hoặc có kế hoạch chuyển đổi được đồng thuận.

## 6. Thay đổi tương thích và breaking change

Một thay đổi là **backward-compatible** khi consumer cũ vẫn hoạt động đúng theo hợp đồng đã cam kết. Tuy nhiên, tính tương thích phụ thuộc cách schema được diễn giải và độ nghiêm ngặt của consumer.

### 6.1. Ví dụ thay đổi thường tương thích

- Thêm endpoint mới mà không thay đổi endpoint hiện có.
- Thêm response field optional khi consumer được yêu cầu bỏ qua field chưa biết.
- Thêm request field optional khi server có default/behavior phù hợp.
- Thêm header không bắt buộc, không làm thay đổi semantics cũ.
- Tăng giới hạn rate/size trong khi không vi phạm cam kết/quota khác.

Không được mặc định rằng mọi consumer đều bỏ qua field mới. Một generated client hoặc JSON validator có thể từ chối unknown property. Do đó phải kiểm tra contract và cách codegen/consumer xử lý.

### 6.2. Ví dụ thường là breaking change

- Xóa hoặc đổi tên field đang được consumer sử dụng.
- Đổi kiểu dữ liệu từ string sang number hoặc thay format không tương thích.
- Chuyển field optional thành required.
- Thay semantics của enum hoặc loại bỏ giá trị enum cũ.
- Xóa endpoint, đổi HTTP method, path hoặc status code mà consumer phụ thuộc.
- Thay auth scope, quyền truy cập, pagination hoặc ordering theo cách làm behavior cũ không còn đúng.
- Siết validation khiến request hợp lệ trước đây bị từ chối.
- Thay default hoặc ý nghĩa nghiệp vụ dù schema không đổi.

### 6.3. Quy tắc cho enum và response fields

Thêm giá trị enum vào response có thể phá consumer dùng exhaustive switch. Ví dụ client chỉ biết `pending`, `confirmed`, `cancelled`; provider thêm `expired`. Client có thể crash hoặc xử lý sai. Contract cần nói rõ consumer phải có nhánh unknown/default và provider phải xem đây là thay đổi có rủi ro.

Với request enum, thêm giá trị mới có thể an toàn nếu provider chấp nhận nhưng consumer cũ không gửi giá trị đó. Với response enum, consumer nhận giá trị mới nên được kiểm tra.

### 6.4. Ma trận thay đổi

| Thay đổi | Mặc định | Lý do phải rà soát |
|---|---|---|
| Thêm response field optional | Thường tương thích nếu consumer bỏ qua unknown field | Generated client/strict parser |
| Thêm request field optional | Thường tương thích nếu server có default | Validation, payload signing, schema strict |
| Xóa response field | Breaking | Consumer cũ có thể cần field |
| Optional → required | Breaking | Request cũ thiếu field |
| Đổi string → integer | Breaking | Deserialization và logic |
| Thêm enum response value | Có rủi ro | Exhaustive switch, unknown handling |
| Đổi status code | Có rủi ro hoặc breaking | Retry/UI/business branch |
| Đổi ý nghĩa field nhưng giữ schema | Breaking về semantics | Consumer hiểu khác nội dung |
| Siết rate limit | Có thể breaking về vận hành | Consumer bị 429 nhiều hơn |
| Đổi auth scope/claim | Breaking với consumer hiện tại | Token và quyền không còn đủ |

Backward compatibility không chỉ là so sánh JSON schema. Cần xét **semantics**, quyền, vận hành và các giả định chưa ghi thành schema.

## 7. Versioning API: chọn cách thay đổi có thể quản lý

### 7.1. URL/path versioning

Ví dụ `GET /v1/bookings` và `GET /v2/bookings`. Ưu điểm là dễ nhìn, routing/cache/log tách rõ và consumer có thể chọn version. Nhược điểm là nhiều phiên bản cần duy trì song song và dễ nhân đôi code nếu không quản lý tốt.

### 7.2. Header/media type versioning

Client gửi version trong header hoặc media type, ví dụ `Accept: application/vnd.example.booking-v2+json`. URI ổn định hơn nhưng khó quan sát bằng mắt và cần gateway/tooling xử lý. Phải quy định behavior khi thiếu hoặc version không được hỗ trợ.

### 7.3. Không version mỗi lần thay đổi

Với API có policy tương thích chặt, thay đổi additive có thể phát hành trong cùng major contract. Không cần tạo `v2` chỉ vì thêm field optional nếu đã kiểm chứng consumer tương thích. Ngược lại, breaking change cần một chiến lược migration rõ: phiên bản mới, thời gian song song và lịch retire.

| Cách | Ưu điểm | Đánh đổi |
|---|---|---|
| URL version | Dễ quan sát, routing rõ | URL/version mới, nhiều code path |
| Header/media type | URI ít đổi, có thể phân loại representation | Khó debug hơn, phụ thuộc gateway/client |
| Backward-compatible evolution | Ít phiên bản và giảm phân mảnh | Cần kỷ luật hợp đồng và test mạnh |

Không có chiến lược versioning duy nhất tốt cho mọi API. Quan trọng là chính sách được công bố, có test và consumer hiểu cách lựa chọn version.

### 7.4. Không nhầm API version với application version

Phiên bản container image hoặc release service có thể tăng mỗi lần deploy, trong khi contract API vẫn là v1.2. Không nhất thiết mỗi build sinh một API version mới. Cần phân biệt:

- Build/release version: phiên bản artifact/service.
- API contract version: mức tương thích interface được công bố.
- Schema/event version: phiên bản payload/event có vòng đời riêng.

## 8. Deprecation và retirement có trách nhiệm

Deprecation nghĩa là provider thông báo operation/version sẽ không còn được khuyến nghị hoặc hỗ trợ trong tương lai. Retirement/sunset là thời điểm provider ngừng cung cấp. **Đánh dấu deprecated không đồng nghĩa xóa ngay**; consumer cần thời gian chuyển đổi.

### 8.1. Vòng đời API

~~~mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> Reviewed: contract + threat review
    Reviewed --> Released: tests pass
    Released --> Supported: production verified
    Supported --> Deprecated: migration plan announced
    Deprecated --> Retired: sunset date reached
    Deprecated --> Supported: deprecation cancelled
    Retired --> [*]
~~~

### 8.2. Nội dung thông báo deprecation

Một thông báo đủ dùng nên có API/operation/version bị deprecate và phạm vi consumer; lý do; API thay thế và hướng dẫn mapping; ngày bắt đầu deprecation, ngày sunset dự kiến; cách nhận hỗ trợ; cách kiểm tra mức sử dụng và owner liên hệ.

Có thể dùng response header `Deprecation` và `Sunset` theo chuẩn/phương án được tổ chức hỗ trợ, kèm tài liệu và dashboard; header không thay thế việc thông báo chủ động cho các đối tác quan trọng.

### 8.3. Kế hoạch migration theo giai đoạn

1. **Announce:** công bố version/operation thay thế, lý do và lịch sunset.
2. **Prepare:** phát hành tài liệu, SDK, sample và migration guide.
3. **Dual support:** duy trì version cũ và mới cùng lúc trong khoảng hỗ trợ đã công bố.
4. **Measure:** dùng access logs/telemetry theo client ID/API key đã quản lý để xác định consumer còn gọi version cũ.
5. **Migrate:** phối hợp từng consumer, chạy contract tests với version mới.
6. **Warn:** gửi cảnh báo trước hạn, có thể gắn header/deprecation telemetry.
7. **Sunset:** ngừng nhận traffic theo chính sách; có thông tin lỗi rõ và trang trạng thái nếu phù hợp.
8. **Remove:** xóa code, routing, secret, quota và hạ tầng cũ sau khi không còn dependency.

### 8.4. Đặt thời gian hỗ trợ dựa trên dữ liệu

Không chọn một mốc 30/60/90 ngày như quy luật chung. Consumer mobile có thể mất nhiều tuần để người dùng cập nhật app; đối tác B2B cần lịch release và phê duyệt; internal service có thể triển khai nhanh hơn. Thời gian deprecation phải dựa trên cam kết hợp đồng/SLA, khả năng cập nhật consumer, rủi ro bảo mật, traffic còn lại và chi phí duy trì nhiều phiên bản.

Nếu API cũ có lỗ hổng nghiêm trọng, tổ chức có thể phải sunset nhanh hơn, nhưng cần kế hoạch giảm tác động và truyền thông tương ứng.

## 9. Quản lý schema cho API bất đồng bộ

Không phải mọi giao tiếp đều là HTTP request/response. BookingCloud có event `booking.created` được gửi qua queue tới notification worker và reporting consumer. Event schema cũng là contract.

Ví dụ:

~~~json
{
  "eventId": "evt-9182",
  "eventType": "booking.created",
  "schemaVersion": 1,
  "occurredAt": "2026-11-18T09:00:00Z",
  "data": {
    "bookingId": "bkg-8124",
    "deviceId": "dev-017"
  }
}
~~~

Quy tắc cần có:

- Consumer xử lý duplicate event theo `eventId` hoặc cơ chế idempotency phù hợp.
- Event chỉ được phát sau khi nghiệp vụ commit; transactional outbox giữ liên hệ giữa DB transaction và publication.
- Payload tối thiểu hóa dữ liệu cá nhân; consumer lấy thêm dữ liệu theo quyền khi cần.
- Schema registry/contract repository cần quy tắc compatibility như backward, forward hoặc full compatibility.
- Thay đổi field required, enum hoặc semantics phải xem xét tất cả consumer; không deploy producer trước khi consumer tương thích nếu delivery có thể xảy ra ngay.
- DLQ/replay giữ schema version và có quy trình nâng cấp consumer khi xử lý message cũ.

**Backward compatibility** cho event thường có nghĩa consumer mới đọc được event cũ; **forward compatibility** nghĩa consumer cũ có thể bỏ qua hoặc xử lý an toàn event mới. Cần xác định rõ schema registry đang kiểm tra chiều nào và theo policy nào. Một policy compatible không tự bảo đảm business semantics đúng.

## 10. Bảo mật và quản trị API contract

Hợp đồng API cần nói rõ security requirements nhưng không chứa secret. Những điểm review quan trọng:

### 10.1. Authentication và authorization

- Security scheme mô tả cách xác thực; scope/role mô tả quyền ở mức operation khi phù hợp.
- API kiểm tra quyền ở **từng resource/object**, ví dụ người dùng A không được xem booking của B chỉ vì JWT hợp lệ.
- Tài liệu phân biệt 401 và 403 theo behavior đã thống nhất.
- Client secret, signing key, access token và dữ liệu nhạy cảm không được commit vào OpenAPI examples hoặc repository.

### 10.2. Input, output và thông tin lỗi

- Giới hạn payload, độ dài string, số phần tử, depth và kiểu dữ liệu.
- Quy định validation, normalization và xử lý unknown fields.
- Response chỉ trả dữ liệu consumer được phép xem.
- Error không lộ stack trace, SQL, internal hostname hay PII không cần thiết.
- Audit các thay đổi quan trọng; có trace/correlation ID nhưng tránh ghi token/request body nhạy cảm.

### 10.3. API gateway không thay thế provider contract

Gateway có thể áp TLS termination, authentication, rate limiting, quota, routing, schema validation và observability. Nhưng policy gateway và code provider phải thống nhất:

- Gateway không vô tình biến status/body thành contract khác.
- Authentication ở gateway không loại bỏ authorization theo business object trong service.
- Version routing và deprecation behavior có test.
- Rate limit và timeout được truyền/diễn giải nhất quán.
- Direct origin access không bypass policy dự kiến.

## 11. API catalog, ownership và governance

Khi số lượng API tăng, cần một catalog để trả lời ai sở hữu, ai tiêu thụ và trạng thái hỗ trợ của từng contract.

| Metadata | Mục đích |
|---|---|
| API name / domain | Nhận diện service và miền nghiệp vụ |
| Provider owner / on-call | Nhóm chịu trách nhiệm kỹ thuật và sự cố |
| Consumer list | Các ứng dụng/dịch vụ/đối tác sử dụng |
| Spec location / version | Nguồn hợp đồng có thẩm quyền |
| Lifecycle state | Draft, supported, deprecated, retired |
| Security classification | Loại dữ liệu và yêu cầu kiểm soát |
| SLO/SLA | Availability, latency, quota hoặc support commitment |
| Deprecation/sunset | Lịch chuyển đổi và trách nhiệm thông báo |
| Runbook/observability | Dashboard, alert, hướng xử lý |

Một API không có owner hoặc không biết consumer nào đang dùng rất khó deprecate an toàn. Access logs, API keys/client identity và service catalog cần phối hợp để nhận diện usage; không dùng IP đơn lẻ nếu nhiều consumer chia sẻ NAT.

## 12. Đo lường chất lượng hợp đồng và vòng đời

Đừng chỉ đếm số lượng contract tests. Đo liệu chúng có giúp phát hiện vấn đề và hỗ trợ thay đổi an toàn hay không.

| Chỉ số | Ý nghĩa | Cách dùng |
|---|---|---|
| Consumer contract coverage | Tỷ lệ consumer quan trọng có contract test được duy trì | Xác định blind spot |
| Provider verification pass rate | Mức provider đáp ứng consumer contracts | Release gate |
| Breaking change detected pre-release | Số thay đổi phá vỡ bị phát hiện trước production | Đánh giá hiệu quả kiểm soát |
| Contract-related incidents | Sự cố do incompatibility sau phát hành | Chọn cải tiến test/spec |
| Deprecated version traffic | Mức sử dụng API đang deprecate | Quyết định sunset |
| Consumer migration completion | Tỷ lệ consumer hoàn tất chuyển đổi | Quản lý retirement |
| Time to adopt new contract | Thời gian consumer tích hợp version mới | Đánh giá độ khó migration |
| API error/latency by version | Behavior vận hành theo version | Phát hiện regression/consumer cụ thể |

Các chỉ số cần có định nghĩa và mẫu số rõ ràng. “100% contract tests pass” không có nghĩa 100% consumer production đã được kiểm tra nếu chỉ có hai trong mười consumer khai báo test.

## 13. Đánh giá theo Well-Architected

| Góc nhìn | Câu hỏi review | Bằng chứng |
|---|---|---|
| **Operational Excellence** | Ai sở hữu contract, release gate và deprecation communication? | API catalog, pipeline, runbook, change record |
| **Security** | Contract có mô tả auth, authorization và data classification; lỗi có lộ dữ liệu không? | Security tests, scopes, audit, log redaction |
| **Reliability** | Consumer cũ có hoạt động khi provider deploy; retry/idempotency có đúng không? | CDC/provider tests, canary, rollback, incident metrics |
| **Performance Efficiency** | Payload, pagination, rate limit và timeout có đáp ứng tải không? | Load test, latency theo version, throughput |
| **Cost Optimization** | Duy trì nhiều version, gateway route và test environment tốn bao nhiêu? | Usage theo version, cost per API call, retirement plan |
| **Sustainability** | Có API cũ/unused, dữ liệu trùng và hạ tầng test dư thừa không? | Deprecation traffic, catalog cleanup, resource lifecycle |

Một API contract có thể tương thích schema nhưng vẫn vi phạm mục tiêu performance nếu response tăng payload lớn hoặc pagination biến mất. Cần xem xét nhiều góc nhìn trước khi phê duyệt.

## 14. Bài thực hành: thay đổi hợp đồng mà không làm hỏng consumer

Booking API v1 đang được ba consumer dùng:

- Mobile app v4 chỉ đọc `id`, `status`, `createdAt`.
- Web v8 hiển thị thêm `deviceId` và `slotId`.
- Partner X tạo booking và xử lý `409` khi slot bị chiếm.

Provider đề xuất phát hành:

1. Thêm response field `pickupLocation` optional.
2. Đổi `status` từ string sang object gồm `code` và `label`.
3. Thêm enum `expired`.
4. Yêu cầu request tạo booking phải có `customerPhone`.
5. Ngừng hỗ trợ endpoint `/v1/bookings`.
6. Thay `409` bằng `400` cho xung đột slot.

Hãy thực hiện:

**Bài 1 — Phân loại:** đánh dấu thay đổi nào additive, có rủi ro hoặc breaking; nêu consumer có thể bị ảnh hưởng và vì sao.

**Bài 2 — Contract test:** viết ít nhất ba kỳ vọng consumer và ba provider verification cases. Bao gồm một case negative cho authorization hoặc validation.

**Bài 3 — Versioning:** chọn cách phát hành thay đổi status/required field; giải thích có cần v2 hay có thể thay đổi tương thích trong v1.

**Bài 4 — Migration:** viết thông báo deprecation cho v1 với API thay thế, timeline có cơ sở, migration guide và cách đo consumer còn sử dụng.

**Bài 5 — CI/CD:** thiết kế release gate từ OpenAPI lint, schema diff, provider verification, consumer contract, security/integration test tới canary.

**Bài 6 — Vận hành:** xác định owner, dashboard theo API version, metric sunset và điều kiện ngừng hỗ trợ.

### Khung đáp án tự kiểm tra

| Thay đổi | Đánh giá khởi đầu | Điều phải chứng minh |
|---|---|---|
| Thêm `pickupLocation` optional | Thường additive | Consumer bỏ qua field mới; không làm lộ PII hoặc payload quá lớn |
| Đổi `status` thành object | Breaking | Cần mapping/version hoặc chuyển tiếp có thời hạn |
| Thêm enum `expired` | Có rủi ro với consumer exhaustive | Consumer có unknown/default branch |
| Thêm `customerPhone` required | Breaking với request cũ | Có thể cung cấp default/migration; xác định lý do nghiệp vụ và dữ liệu |
| Xóa `/v1/bookings` | Breaking | Consumer đã di chuyển và sunset được thông báo |
| `409` thành `400` | Có thể breaking về semantics | Consumer xử lý conflict riêng; phải giữ semantics hoặc version |

Không chỉ dựa vào bảng này để phê duyệt. Cần test consumer thật, kiểm tra implementation và đánh giá security/operational behavior.

## 15. Checklist trước khi phát hành hoặc deprecate API

- [ ] Specification là nguồn hợp đồng có version và có owner.
- [ ] Request/response/error/auth/authorization và semantics nghiệp vụ được mô tả.
- [ ] Schema lint, provider contract test và consumer expectations chạy trong CI.
- [ ] Integration/security tests kiểm tra dependency và ranh giới tin cậy quan trọng.
- [ ] Diff với phiên bản được hỗ trợ phát hiện breaking changes.
- [ ] Unknown fields, enum evolution, optional/required và nullability có policy rõ.
- [ ] Idempotency, retry, pagination, timeout và rate limit được kiểm tra.
- [ ] Release gate có thể chặn candidate không tương thích; canary có telemetry và rollback.
- [ ] API catalog biết provider owner, consumer, SLO, security classification và runbook.
- [ ] Deprecation có lý do, API thay thế, migration guide, ngày sunset và kênh hỗ trợ.
- [ ] Usage theo version/consumer được đo trước khi retire.
- [ ] Sau retirement, routing, code, secret, quota, tài liệu và hạ tầng cũ được dọn có kiểm soát.

Kiểm thử hợp đồng giúp provider và consumer phát hiện bất tương thích trước khi phát hành; quản lý vòng đời giúp cả hai phía biết khi nào và bằng cách nào phải thay đổi. Kết hợp specification có thể kiểm tra, contract tests, compatibility policy, telemetry và governance rõ ràng sẽ giúp API phát triển độc lập mà vẫn giữ được độ tin cậy của toàn hệ thống cloud.
