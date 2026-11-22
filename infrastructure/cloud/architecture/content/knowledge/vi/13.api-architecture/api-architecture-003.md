# Phiên bản API và khả năng tương thích khi thay đổi

API là hợp đồng giữa một bên cung cấp chức năng (producer/provider) và các ứng dụng sử dụng nó (consumer). Khi producer thay đổi request, response, quy tắc nghiệp vụ hoặc cách xác thực, các ứng dụng đang dùng phiên bản cũ có thể vẫn chạy trong nhiều ngày hoặc nhiều tháng. Nếu thay đổi không được quản lý, một bản phát hành backend có thể làm hỏng ứng dụng di động chưa được cập nhật, tích hợp của đối tác hoặc một dịch vụ nội bộ mà nhóm phát triển không biết đang phụ thuộc.

**Versioning API** là cách quản lý các phiên bản hợp đồng API theo thời gian. **Backward compatibility (tương thích ngược)** mô tả khả năng phiên bản mới tiếp tục hỗ trợ consumer cũ; **forward compatibility (tương thích xuôi)** mô tả khả năng consumer cũ xử lý dữ liệu hoặc hành vi mới từ producer. Hai thuộc tính này liên quan nhưng không giống nhau.

Trong module **CLOUD_ARCHITECTURE**, quản lý phiên bản API giúp hệ thống phát hành độc lập, mở rộng nhiều consumer, kết nối dịch vụ cloud và đối tác, đồng thời kiểm soát đánh đổi về độ tin cậy, bảo mật, hiệu năng, chi phí và vận hành. Mục tiêu là hiểu khi nào một thay đổi vẫn tương thích, khi nào cần phiên bản mới và cách chuyển đổi an toàn.

## 1. API contract là gì và vì sao phải quản lý thay đổi?

Một API contract mô tả cách consumer tương tác với producer. Với HTTP API, contract thường gồm:

- **Endpoint và method:** URL, HTTP method như GET, POST, PATCH, DELETE.
- **Request:** Path/query parameter, header, body, kiểu dữ liệu và trường bắt buộc.
- **Response:** Status code, header, cấu trúc body và semantics của từng trường.
- **Quy tắc nghiệp vụ:** Ý nghĩa thao tác, điều kiện thành công/thất bại và side effect.
- **Authentication và authorization:** Cách xác thực, scope/role cần thiết và quyền của từng hành động.
- **Error contract:** Mã lỗi, nội dung lỗi, khả năng retry và cách consumer xử lý.
- **Operational contract:** Timeout, rate limit, pagination, idempotency và giới hạn payload.

Ví dụ, Booking API cung cấp thao tác tạo đặt chỗ:

~~~http
POST /api/bookings
Content-Type: application/json
Authorization: Bearer <access-token>
Idempotency-Key: 1c7f...

{
  "resourceId": "ROOM-101",
  "startAt": "2026-12-01T09:00:00Z",
  "endAt": "2026-12-01T10:00:00Z"
}
~~~

Response có thể là:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /api/bookings/BK-9081

{
  "id": "BK-9081",
  "status": "CONFIRMED",
  "startAt": "2026-12-01T09:00:00Z",
  "endAt": "2026-12-01T10:00:00Z"
}
~~~

Nếu đổi tên trường resourceId thành resourceCode bắt buộc phải gửi, đổi status từ chuỗi sang object hoặc đổi ý nghĩa 201 Created, consumer cũ có thể không còn hoạt động. Thay đổi API vì vậy cần được đánh giá theo **tất cả consumer đang tồn tại**, không chỉ theo code của producer.

| Vai trò | Trách nhiệm |
|---|---|
| **API producer/provider** | Công bố contract, duy trì behavior, xác thực request, hỗ trợ phiên bản, thông báo thay đổi và deprecation |
| **API consumer/client** | Gửi request đúng contract, xử lý response/error, timeout và retry, theo dõi thay đổi và nâng cấp khi được thông báo |
| **API owner/platform team** | Quản lý catalog, policy, telemetry, gateway, quy trình versioning và vòng đời phiên bản |
| **Security/operations** | Kiểm tra quyền, dữ liệu, logging, rate limit, SLO và phương án ứng phó |

Một API nội bộ vẫn là hợp đồng giữa các nhóm. Việc hai service thuộc cùng một repository hoặc cùng tổ chức không đảm bảo chúng được deploy cùng lúc.

## 2. Backward compatibility và forward compatibility

### 2.1. Tương thích ngược

Một thay đổi là **backward-compatible** khi consumer đang sử dụng contract cũ vẫn có thể gọi producer sau khi producer được cập nhật, trong phạm vi behavior đã cam kết.

Ví dụ:
- Thêm một field response tùy chọn mà consumer cũ bỏ qua field lạ.
- Thêm endpoint mới nhưng giữ endpoint cũ.
- Thêm một header tùy chọn mà consumer cũ không cần gửi.
- Mở rộng response với metadata mới, không thay đổi ý nghĩa các field đã có.

Những thay đổi này thường có thể phát hành trong cùng major version, nếu contract và consumer thực tế hỗ trợ cách mở rộng.

### 2.2. Tương thích xuôi

Một consumer có **forward compatibility** nếu nó có thể xử lý dữ liệu hoặc behavior mới từ producer. Ví dụ, consumer bỏ qua field JSON không biết thay vì thất bại khi gặp field mới.

Tuy nhiên, consumer không phải lúc nào cũng forward-compatible:
- Generated client có thể deserialize nghiêm ngặt và từ chối field mới.
- Enum parser có thể lỗi khi nhận giá trị mới.
- Code switch/case có thể không có nhánh default.
- Schema validation có thể cấm field chưa khai báo.
- Logic nghiệp vụ có thể giả định chỉ có một tập trạng thái cố định.

Do đó, “thêm field là an toàn” chỉ đúng khi **consumer, schema, SDK, proxy và validator** chấp nhận mở rộng đó.

### 2.3. Tương thích không chỉ là cấu trúc JSON

Ngay cả khi schema không đổi, behavior cũng có thể phá vỡ consumer.

Ví dụ:
- API trước đây trả booking theo thời gian tạo, nay đổi sang thứ tự cập nhật.
- API trước đây cho phép gọi lặp idempotent, nay mỗi lần retry lại tạo một booking.
- API trước đây trả 404 khi không tìm thấy, nay trả 200 với body rỗng.
- API trước đây coi timestamp là UTC, nay trả thời gian local.
- API trước đây cho phép page size 100, nay giới hạn còn 10 mà không thông báo.
- API trước đây giữ trạng thái trong 30 ngày, nay tự xóa sau 24 giờ.

Những thay đổi này có thể làm hỏng consumer mà không thay JSON schema. Khi đánh giá compatibility, cần kiểm tra **syntax, semantics, security, timing và operational behavior**.

## 3. Phân loại thay đổi API

Một quy tắc hữu ích là phân loại thay đổi thành **mở rộng tương thích (additive)**, **thay đổi cần phối hợp (behavioral/conditional)** và **phá vỡ hợp đồng (breaking)**.

| Thay đổi | Rủi ro compatibility | Hướng xử lý thường gặp |
|---|---|---|
| Thêm endpoint mới | Thấp nếu không thay endpoint hiện có | Giữ contract cũ, công bố endpoint mới |
| Thêm response field tùy chọn | Thường thấp, nhưng consumer có thể deserialize nghiêm ngặt | Kiểm tra SDK/schema; coi field là optional |
| Thêm request field tùy chọn | Thấp nếu server xử lý mặc định nhất quán | Quy định default và semantics rõ |
| Thêm request field bắt buộc | Cao | Hỗ trợ default hoặc tạo phiên bản contract mới |
| Xóa field response | Cao | Deprecate, đo consumer, chuyển đổi rồi mới xóa |
| Đổi tên field | Cao | Giữ field cũ trong giai đoạn chuyển tiếp hoặc version mới |
| Đổi kiểu dữ liệu | Cao | Thường là breaking; thêm field mới hoặc version mới |
| Thu hẹp giá trị hợp lệ | Cao | Có thể làm request cũ bị từ chối |
| Thêm enum value | Phụ thuộc consumer | Consumer xử lý unknown value; cân nhắc parser strict |
| Đổi HTTP method/path | Cao | Giữ route cũ hoặc phát hành phiên bản mới |
| Đổi status code/error shape | Có thể cao | Kiểm tra logic client, retry và error mapping |
| Đổi auth scope hoặc quyền bắt buộc | Có thể breaking về bảo mật/vận hành | Thông báo, hỗ trợ credential mới và migration |
| Đổi pagination/default sort/limit | Có thể làm sai nghiệp vụ | Đánh giá semantics và công bố thay đổi |
| Thay timeout/rate limit | Có thể ảnh hưởng client ở tải thực | Thông báo, đo và cung cấp retry/backoff |

### Những trường hợp dễ hiểu nhầm

**Thêm field response:** Thường được coi là additive nếu consumer bỏ qua field chưa biết. Nhưng nếu consumer dùng strict schema, generated model hoặc signature payload, thêm field có thể gây lỗi. Hãy kiểm tra contract thực tế.

**Thêm enum value:** Có thể phá consumer viết logic chỉ chấp nhận tập giá trị hiện có. API nên khuyến khích consumer có nhánh unknown/fallback; có thể dùng enum mở hoặc string thay vì giả định tập giá trị bất biến.

**Thay đổi default:** Nếu query parameter mặc định trước đây trả 20 kết quả nay trả 100, schema không đổi nhưng tải, paging và logic UI có thể khác. Default là một phần của contract hành vi.

**Tăng độ nghiêm ngặt validation:** Từ chấp nhận khoảng trắng hoặc field không chuẩn sang từ chối có thể làm consumer cũ không còn gửi được request. Validation security là cần thiết, nhưng phải đánh giá tác động và cung cấp migration rõ.

## 4. Chọn chiến lược versioning

Không có một cách đánh số phiên bản phù hợp mọi API. Điều quan trọng là phiên bản phải **dễ nhận biết, ổn định, có chính sách hỗ trợ và có đường chuyển đổi**.

### 4.1. Version trong URL path

Ví dụ:

~~~text
GET /api/v1/bookings/BK-9081
GET /api/v2/bookings/BK-9081
~~~

Ưu điểm:
- Dễ quan sát trong log, metric, gateway và dashboard.
- Dễ route tới handler hoặc deployment phù hợp.
- Dễ thử phiên bản mới song song.

Đánh đổi:
- Version xuất hiện trong URL và có thể tạo nhiều route/endpoint.
- Cần quản lý deprecation và tránh nhân đôi logic nghiệp vụ.
- Nếu mỗi version là một deployment riêng, chi phí vận hành có thể tăng.

Đây là lựa chọn phổ biến cho public API vì dễ giải thích và vận hành.

### 4.2. Version qua header

Ví dụ custom header:

~~~http
GET /api/bookings/BK-9081
API-Version: 2
Accept: application/json
~~~

Hoặc dùng media type versioning:

~~~http
GET /api/bookings/BK-9081
Accept: application/vnd.example.booking.v2+json
~~~

Ưu điểm:
- URL tập trung vào resource.
- Có thể định tuyến phiên bản theo request metadata.
- Phù hợp hệ thống muốn quản lý content negotiation.

Đánh đổi:
- Khó quan sát nếu log/gateway không ghi header.
- Cache/proxy cần phân biệt response theo header, ví dụ cấu hình Vary: Accept phù hợp.
- Consumer và công cụ debug phải biết cách gửi header đúng.

### 4.3. Version qua query parameter

Ví dụ:

~~~text
GET /api/bookings/BK-9081?version=2
~~~

Cách này dễ thử nghiệm và quan sát, nhưng thường kém rõ ràng hơn path hoặc media type khi version là một phần lớn của contract. Cũng cần xem cache key và policy ở gateway để không trả response sai phiên bản.

### 4.4. Không version explicit

Một số API chỉ phát hành thay đổi tương thích và không đưa version vào URL/header. Cách này giảm số phiên bản phải hỗ trợ, nhưng đòi hỏi kỷ luật compatibility cao và quy trình change management nghiêm túc. Nếu có breaking change, cần chiến lược nâng cấp có phối hợp hoặc một kênh mới.

| Chiến lược | Dễ quan sát | Hỗ trợ song song | Điểm cần chú ý |
|---|---|---|---|
| URL path | Cao | Cao | Quản lý nhiều route và version |
| Header | Trung bình nếu không log đầy đủ | Cao | Cache, proxy và observability |
| Media type | Trung bình | Cao | Consumer phải thương lượng content type |
| Query parameter | Cao | Cao | Cache key và semantics URL |
| Không version explicit | Tùy telemetry | Thấp hơn khi breaking changes | Cần compatibility discipline rất tốt |

Chọn một quy ước nhất quán cho cùng một API family. Đừng đưa version vào path, header và body cùng lúc nếu không có lý do rõ ràng; nhiều nguồn version tạo ra mâu thuẫn như path là v2 nhưng header lại yêu cầu v1.

## 5. Semantic versioning và API version là hai khái niệm khác nhau

**Semantic Versioning (SemVer)** thường có dạng MAJOR.MINOR.PATCH, mô tả mức độ thay đổi của một sản phẩm/package:
- MAJOR: thay đổi không tương thích.
- MINOR: thêm chức năng tương thích ngược.
- PATCH: sửa lỗi tương thích.

Đối với HTTP API, path /v1 thường biểu thị **major contract line**, không nhất thiết phản ánh từng lần deploy patch. Không nên đổi /v1.2.3 mỗi khi sửa code hoặc nâng container image nếu hợp đồng public không đổi.

Ví dụ:
- API /v1 có thể có nhiều lần release backend 1.4.1, 1.4.2, 1.5.0 mà vẫn giữ cùng major contract.
- Khi đổi cấu trúc response theo cách breaking, nhóm có thể công bố /v2.
- Một SDK client có version riêng theo SemVer; version SDK và version HTTP API không tự động đồng bộ.

Cần ghi rõ quy ước trong tài liệu:
1. API version biểu thị contract nào?
2. Một thay đổi patch/minor có thể thêm field hay endpoint ở mức nào?
3. Khi nào cần major version mới?
4. Các phiên bản được hỗ trợ trong bao lâu?
5. SDK có tương thích với những API version nào?

## 6. Thiết kế API để dễ mở rộng tương thích

### 6.1. Thiết kế response có thể mở rộng

- Consumer nên bỏ qua field không biết nếu schema/SDK cho phép.
- Field mới nên optional hoặc có default rõ ràng.
- Không đổi ý nghĩa field cũ.
- Không tái sử dụng tên field đã xóa cho ý nghĩa khác.
- Date/time và numeric format phải được định nghĩa ổn định.
- Enum consumer nên có nhánh unknown hoặc fallback hợp lý.

Ví dụ response bổ sung displayLabel:

~~~json
{
  "id": "BK-9081",
  "status": "CONFIRMED",
  "displayLabel": "Phòng 101"
}
~~~

Consumer cũ chỉ sử dụng id và status có thể tiếp tục hoạt động nếu parser bỏ qua field không biết. Consumer mới có thể hiển thị thêm label.

### 6.2. Thiết kế request có default an toàn

Thêm field request optional thường ít phá vỡ hơn bắt buộc ngay lập tức:

~~~json
{
  "resourceId": "ROOM-101",
  "startAt": "2026-12-01T09:00:00Z",
  "endAt": "2026-12-01T10:00:00Z",
  "notifyByEmail": true
}
~~~

Nếu notifyByEmail không có, server cần xác định default. Default nên nhất quán và được ghi trong contract. Nếu thêm trường bắt buộc mà không có giá trị mặc định tương thích, consumer cũ sẽ bị từ chối.

### 6.3. Error contract ổn định

Nên duy trì cấu trúc lỗi có mã máy đọc được và thông điệp phù hợp:

~~~json
{
  "type": "https://api.example.com/errors/slot-unavailable",
  "title": "Slot is unavailable",
  "status": 409,
  "code": "SLOT_UNAVAILABLE",
  "detail": "The selected slot is no longer available.",
  "traceId": "trace-abc123"
}
~~~

Consumer nên phân loại bằng HTTP status và machine-readable code, không parse chuỗi detail để quyết định logic. Thông điệp có thể được cải thiện mà không đổi code nghiệp vụ; ngược lại, đổi status code hoặc code lỗi có thể phá vỡ retry/error mapping.

### 6.4. Unknown fields và enum

Consumer robust nên:
- Bỏ qua field không biết khi phù hợp.
- Xử lý enum chưa biết bằng fallback hoặc hiển thị trạng thái không xác định.
- Không giả định property order của JSON.
- Không giả định field optional luôn xuất hiện.
- Dùng parser/schema settings phù hợp với contract.

Producer cũng cần cân nhắc: việc nhận field lạ trong request có thể bị từ chối có chủ đích vì security hoặc typo detection. Không có quy tắc buộc mọi API phải chấp nhận unknown request fields; điều cần thiết là quy định rõ behavior và tránh vô tình thay đổi.

## 7. OpenAPI và schema là nguồn hợp đồng có thể kiểm tra

Đối với HTTP API, mô tả OpenAPI giúp công bố endpoint, method, parameter, schema, response và security requirement. Tệp schema nên được version control, review cùng code và dùng trong pipeline để phát hiện thay đổi.

Ví dụ rút gọn:

~~~yaml
openapi: 3.1.0
info:
  title: Booking API
  version: 1.0.0
paths:
  /api/v1/bookings:
    post:
      operationId: createBooking
      security:
        - bearerAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required:
                - resourceId
                - startAt
                - endAt
              properties:
                resourceId:
                  type: string
                startAt:
                  type: string
                  format: date-time
                endAt:
                  type: string
                  format: date-time
                notifyByEmail:
                  type: boolean
                  default: true
      responses:
        "201":
          description: Booking created
        "409":
          description: Slot unavailable
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
~~~

Đây là ví dụ minh họa. Schema thực tế cần mô tả response body, error format, headers, pagination và các quy tắc khác. Trường default trong JSON Schema/OpenAPI mô tả giá trị mặc định nhưng không phải mọi validator hoặc server đều tự áp dụng; producer phải triển khai behavior tương ứng.

### Contract diff và compatibility checks

Pipeline có thể:
1. So sánh OpenAPI schema hiện tại với phiên bản đã phát hành.
2. Phát hiện endpoint/field bị xóa, đổi kiểu hoặc trở thành required.
3. Kiểm tra breaking change theo rule của tổ chức.
4. Chạy consumer contract tests.
5. Yêu cầu review/ADR cho thay đổi có rủi ro.
6. Lưu artifact schema và phiên bản phát hành.

Công cụ diff không hiểu hoàn toàn semantics nghiệp vụ. Đổi ý nghĩa một field string không làm schema khác; thay đổi default hay thứ tự sắp xếp cũng có thể bị bỏ qua. Vì vậy cần kết hợp contract diff với test và review.

## 8. Consumer-driven contract testing

**Consumer-driven contract testing** giúp consumer ghi rõ phần contract mà nó phụ thuộc, sau đó kiểm tra producer có tiếp tục đáp ứng không.

Quy trình:
1. Consumer định nghĩa request và response cần thiết cho use case.
2. Contract được lưu và công bố trong pipeline hoặc broker.
3. Producer chạy provider verification để xác nhận behavior thực tế thỏa contract của các consumer.
4. Khi contract thay đổi, consumer và producer phối hợp cập nhật trước khi phát hành.
5. CI ngăn triển khai nếu contract quan trọng bị phá vỡ ngoài chính sách cho phép.

Ví dụ:
- Mobile app chỉ cần id, status, startAt.
- Admin portal cần thêm customerName.
- Reporting service đọc event booking được công bố.

Producer không nhất thiết phải trả cùng payload cho mọi consumer nếu có API composition hoặc projection, nhưng phải giữ contract của từng consumer đã cam kết.

**Contract test không thay thế integration test hoặc end-to-end test.** Nó kiểm tra tương tác ở ranh giới contract; các vấn đề như network policy, IAM, timeout, database consistency và độ sẵn sàng cần kiểm thử riêng.

## 9. Versioning cho event và message schema

Trong hệ thống cloud, API không chỉ là HTTP. Queue, event bus và streaming platform cũng có contract giữa producer và consumer. Một producer phát event:

~~~json
{
  "eventId": "evt-9381",
  "eventType": "BookingConfirmed",
  "occurredAt": "2026-12-01T08:00:00Z",
  "data": {
    "bookingId": "BK-9081",
    "resourceId": "ROOM-101"
  }
}
~~~

Nếu thêm field optional vào event, consumer bỏ qua field mới thường có thể tiếp tục hoạt động. Nhưng xóa/đổi kiểu field, đổi semantics hoặc gửi eventType mới có thể phá consumer cũ.

Nguyên tắc:
- Có event ID ổn định để consumer xử lý idempotent.
- Có schema/version metadata hoặc quy ước compatibility phù hợp.
- Không đổi nghĩa field hiện hữu hoặc tái sử dụng field cho mục đích khác.
- Consumer xử lý event type/field chưa biết theo policy.
- Schema registry hoặc contract repository có thể kiểm tra compatibility nếu nền tảng hỗ trợ.
- Xác định retention/replay và thời gian consumer phải đọc event cũ.

Với event, **forward compatibility** đặc biệt quan trọng vì message cũ có thể tồn tại trong queue/log và được đọc lại bởi consumer mới. Consumer mới cần đọc được event đã phát hành trước đó; producer mới cũng cần cân nhắc consumer cũ đang đọc event mới.

## 10. Thay đổi database mà vẫn giữ API tương thích

Một thay đổi API có thể cần thay đổi schema database. Nếu deploy producer mới trước khi database sẵn sàng, hoặc migration xóa cột trước khi consumer cũ ngừng dùng, release sẽ gây lỗi.

Chiến lược **expand-contract**:

~~~mermaid
flowchart LR
    A["1. Expand<br/>Thêm field/cột mới, giữ cột cũ"] --> B["2. Deploy compatible code<br/>Đọc được cũ và mới"]
    B --> C["3. Migrate data<br/>Backfill và đồng bộ"]
    C --> D["4. Switch consumers<br/>Chuyển sang field mới"]
    D --> E["5. Verify<br/>Không còn truy cập cũ"]
    E --> F["6. Contract<br/>Xóa field/cột cũ ở release sau"]
~~~

Ví dụ đổi customer_name sang display_name:
1. Thêm cột display_name, không xóa customer_name.
2. Code mới ghi cả hai hoặc có cơ chế đồng bộ an toàn.
3. Backfill dữ liệu cũ.
4. API mới đọc display_name; consumer dần chuyển sang field mới.
5. Theo dõi log/tracing để xác nhận không còn consumer dùng contract cũ.
6. Sau thời gian hỗ trợ, mới xóa cột cũ trong migration riêng.

Không phải migration nào cũng có thể dual-write đơn giản. Có thể phát sinh race condition, dữ liệu ghi không nhất quán và chi phí lưu trữ. Cần xác định nguồn dữ liệu chuẩn và chiến lược rollback rõ ràng.

## 11. Rollout, coexistence và deprecation

Khi cần breaking change, không nên phát hành v2 rồi xóa v1 ngay. Hãy có **giai đoạn cùng tồn tại (coexistence)**:

1. Công bố phiên bản mới và migration guide.
2. Triển khai v2 mà không làm thay đổi behavior v1.
3. Chuyển một số consumer thử nghiệm sang v2.
4. Theo dõi traffic, lỗi, latency và consumer identity theo version.
5. Mở rộng chuyển đổi, hỗ trợ consumer gặp vấn đề.
6. Công bố deprecation cho v1 và deadline dự kiến.
7. Theo dõi traffic còn lại và làm việc với owner consumer.
8. Ngừng v1 theo chính sách hỗ trợ đã thông báo, sau khi đáp ứng điều kiện đã công bố.

~~~mermaid
flowchart TD
    OLD["v1 đang phục vụ consumer"] --> NEW["Triển khai v2 song song"]
    NEW --> CANARY["Canary / pilot consumer"]
    CANARY --> METRICS["Đo traffic, lỗi, latency"]
    METRICS --> MIGRATE["Chuyển consumer theo nhóm"]
    MIGRATE --> DEPRECATE["Thông báo deprecation và deadline"]
    DEPRECATE --> VERIFY["Xác minh không còn traffic v1"]
    VERIFY --> SUNSET["Ngừng v1 theo chính sách"]
~~~

### Deprecation và Sunset

- **Deprecated:** Phiên bản/endpoint còn hoạt động nhưng không còn được khuyến nghị; consumer nên chuẩn bị chuyển đổi.
- **Sunset:** Thời điểm hoặc giai đoạn API sẽ ngừng cung cấp theo chính sách đã thông báo.
- **Migration guide:** Nêu mapping endpoint/field/error, thay đổi behavior, auth, test và thời gian hỗ trợ.
- **Support window:** Khoảng thời gian producer cam kết duy trì phiên bản hoặc hỗ trợ consumer chuyển đổi.

Nếu API public, có thể công bố metadata deprecation/sunset theo tiêu chuẩn hoặc header phù hợp, ví dụ Deprecation, Sunset và Link, nếu hệ sinh thái hỗ trợ. Header chỉ có giá trị khi thời điểm, timezone, ý nghĩa và tài liệu migration rõ ràng.

Không đặt sunset date tùy tiện. Cần tính lịch phát hành ứng dụng di động, chu kỳ mua sắm/đối tác, thời gian phê duyệt bảo mật và khả năng nâng cấp consumer.

## 12. API Gateway và quản lý nhiều phiên bản

API Gateway có thể định tuyến request tới backend theo path, header, hostname hoặc policy khác tùy sản phẩm. Nó hỗ trợ xác thực, rate limiting, logging, routing và migration, nhưng không tự làm cho hai contract tương thích.

Ví dụ:
- /api/v1/... route tới backend v1.
- /api/v2/... route tới backend v2.
- Gateway ghi version và consumer identity trong telemetry.
- Có thể canary một số consumer/traffic sang v2 nếu policy và semantics cho phép.

Cần tránh:
- Chỉ sửa response ở gateway mà không có contract rõ.
- Giấu lỗi bằng transform làm mất field hoặc thay semantics.
- Dựa vào gateway để duy trì logic nghiệp vụ phức tạp cho nhiều năm.
- Cho v1 và v2 dùng chung database nhưng migration không tương thích.
- Quên cache key, CORS, auth scope và rate limit khi có nhiều version.

**Version ở gateway và version ở application contract phải nhất quán.** Nếu gateway quảng bá v2 nhưng backend chỉ hỗ trợ một số request v2, consumer có thể gặp behavior không ổn định.

## 13. Observability: biết ai còn dùng phiên bản cũ

Không thể deprecate an toàn nếu producer không biết consumer nào đang gọi endpoint cũ.

Nên thu thập:
- Request count theo API version, endpoint, method và consumer/app identity.
- Error rate và status code theo version.
- Latency p50/p95/p99 và timeout.
- Tỷ lệ request sử dụng field/operation cũ nếu có thể đo an toàn.
- Client SDK/app version và nguồn tích hợp.
- Rate limit, retry và lỗi auth theo version.

Không đưa token, password hoặc dữ liệu cá nhân vào metric label. Consumer identity nên là identifier đã được kiểm soát, không phải nội dung nhạy cảm.

Dashboard deprecation nên trả lời:
- Consumer nào còn dùng v1?
- Traffic của consumer đó có giảm không?
- Owner nào chịu trách nhiệm migration?
- Phiên bản mới có đạt SLO chưa?
- Có lỗi tăng sau khi chuyển consumer không?
- Có request v1 từ consumer không xác định không?

Nếu API không thể xác định consumer, cân nhắc bổ sung client ID, API key có scope, OAuth client ID hoặc cơ chế nhận diện phù hợp. Không dùng IP đơn thuần làm định danh lâu dài nếu request đi qua NAT, proxy hoặc gateway chung.

## 14. Bảo mật và quyền tương thích giữa các version

Version mới có thể cần thêm scope hoặc thay đổi cách xác thực. Đây là thay đổi contract quan trọng dù JSON body không đổi.

Ví dụ:
- v1 dùng scope booking.read; v2 yêu cầu booking.read:details.
- v1 trả dữ liệu đã che số điện thoại; v2 cho phép truy cập trường nhạy cảm theo role khác.
- v2 bắt buộc mTLS trong khi v1 dùng bearer token.
- Endpoint cũ có lỗ hổng đã biết và cần ngừng khẩn cấp.

Không nên duy trì một phiên bản dễ bị khai thác vô thời hạn chỉ vì consumer chưa nâng cấp. Khi có rủi ro bảo mật nghiêm trọng, cần kế hoạch ngừng hoặc hạn chế API theo mức độ rủi ro, thông báo và hỗ trợ chuyển đổi phù hợp. Security policy có thể yêu cầu migration nhanh hơn lịch deprecation thông thường.

Cần kiểm tra:
- v1/v2 có dùng chung secrets và quyền backend không?
- Consumer v1 có truy cập dữ liệu mới mà không nên thấy không?
- Authorization có được thực thi ở mọi route, kể cả gateway và backend trực tiếp?
- Audit log có phân biệt version và principal không?
- Rate limit có áp dụng phù hợp cho từng consumer/version không?

## 15. Đánh đổi theo Well-Architected

| Khía cạnh | Thiết kế versioning tốt hỗ trợ | Rủi ro cần kiểm soát | Bằng chứng |
|---|---|---|---|
| **Độ tin cậy** | Consumer cũ tiếp tục hoạt động trong thời gian migration; canary và rollback | Nhiều version có thể khác behavior hoặc phụ thuộc database chung | Consumer contract tests, error rate, rollback rehearsal |
| **Bảo mật** | Nâng cấp auth/scope có kế hoạch; hỗ trợ vá lỗ hổng và sunset | Version cũ giữ endpoint yếu hoặc quyền quá rộng | Security review theo version, auth tests, audit |
| **Hiệu năng** | Có thể tối ưu từng version và chuyển tải dần | Gateway routing, transform hoặc code nhiều nhánh tăng latency | p95/p99, throughput và gateway metrics |
| **Khả năng mở rộng** | Consumer tự nâng cấp theo lịch; producer phát hành độc lập hơn | Số version tăng làm phức tạp schema, test và support | Version inventory, consumer usage, compatibility matrix |
| **Chi phí** | Giảm outage do breaking change; deprecation chủ động | Duy trì v1/v2 song song tăng compute, test và vận hành | Cost per version/consumer, sunset plan |
| **Vận hành** | Có migration guide, telemetry, contract checks và ownership | Không xác định consumer hoặc tài liệu lệch code làm migration kéo dài | Dashboard traffic version, OpenAPI diff, ADR, owner list |

Một số quyết định cần cân nhắc:
- Giữ nhiều phiên bản lâu giúp consumer có thời gian nâng cấp, nhưng tăng chi phí bảo trì.
- Version path dễ quản lý qua gateway, nhưng có thể nhân đôi endpoint và test.
- Version header gọn URL, nhưng đòi hỏi logging/cache/proxy chính xác.
- Contract testing giảm rủi ro giữa producer và consumer, nhưng không kiểm chứng toàn bộ hạ tầng hoặc behavior ngoài contract.
- Tách backend theo version có thể cô lập rollout, nhưng làm tăng tài nguyên và migration dữ liệu.
- Duy trì backend chung có thể giảm chi phí, nhưng cần code tương thích và test nhiều nhánh hơn.

## 16. Quy trình quyết định một thay đổi có cần version mới không

Trước mỗi thay đổi contract, hãy trả lời:

1. **Ai đang dùng API?** Xác định consumer nội bộ, mobile/web app, đối tác và job nền.
2. **Thay đổi phần nào?** Path, method, request, response, enum, error, semantics, auth, timeout, rate limit hay data retention?
3. **Consumer cũ xử lý thế nào?** Bỏ qua field mới được không? Có parser strict? Có generated SDK? Có dùng default cũ?
4. **Có cách additive không?** Thêm field optional, endpoint mới, header mới hoặc giai đoạn hỗ trợ song song?
5. **Nếu breaking, version mới giúp gì?** Có thực sự cần contract riêng hay chỉ cần migration code tương thích?
6. **Data migration có an toàn không?** Dùng expand-contract, dual-read/write hoặc phương án khác?
7. **Có đo được adoption không?** Consumer identity, traffic version, error/latency.
8. **Deprecation/sunset cần bao lâu?** Theo chu kỳ nâng cấp và cam kết hỗ trợ của consumer.
9. **Rollback ra sao?** Có thể quay lại backend cũ không? Schema đã thay đổi ngược được không?
10. **Ai phê duyệt và sở hữu?** API owner, consumer owner, security và operations.

### ADR minh họa — Đổi field response

> **Bối cảnh:** Booking API v1 trả field customerName; hệ thống muốn dùng displayName để phản ánh tên hiển thị theo chính sách mới. Mobile app và Admin Portal đang dùng v1.
>
> **Phương án A:** Đổi tên field trực tiếp. Đơn giản nhưng consumer cũ ngừng đọc được dữ liệu.
>
> **Phương án B:** Bổ sung displayName, giữ customerName trong giai đoạn chuyển tiếp. Consumer mới dùng field mới; consumer cũ tiếp tục hoạt động.
>
> **Phương án C:** Phát hành v2 với field mới, giữ v1 riêng. Rõ contract nhưng tăng chi phí hỗ trợ song song.
>
> **Quyết định minh họa:** Chọn B nếu hai field có thể cùng tồn tại mà không vi phạm chính sách dữ liệu và semantics. Nếu ý nghĩa dữ liệu khác nhau hoặc security requirement không cho phép tiếp tục field cũ, chọn C hoặc kế hoạch migration được kiểm soát.
>
> **Kiểm chứng:** Contract tests cho mobile/admin, đo traffic field cũ, xác nhận dữ liệu và quyền truy cập, có ngày deprecation sau khi consumer migration hoàn tất.
>
> **Điều kiện xem xét lại:** Field cũ không còn traffic, consumer đã xác nhận chuyển đổi và yêu cầu bảo vệ dữ liệu cho phép ngừng field.

## 17. Bài tập thực hành

Một nền tảng đặt chỗ công bố API v1. Các consumer gồm:
- Mobile App phiên bản cũ chỉ được cập nhật theo chu kỳ phát hành của cửa hàng ứng dụng.
- Admin Portal có thể deploy hàng ngày.
- Payment service nội bộ được đội khác quản lý.
- Một đối tác bên ngoài tích hợp bằng API key và có quy trình thay đổi dài.

Contract hiện có GET /api/v1/bookings/{id} với response id, status, startAt. Nhóm muốn đổi status thành object chứa code, label, thêm customerEmail và thay bearer token bằng một scope mới.

**Yêu cầu:**

1. Phân loại từng thay đổi: additive, behavioral hay breaking.
2. Đề xuất phương án để consumer cũ tiếp tục hoạt động.
3. Quyết định có cần /v2 hay không; giải thích theo consumer và semantics.
4. Viết kế hoạch coexistence và deprecation.
5. Xác định metric cần theo dõi để biết mobile app, Admin Portal và đối tác còn sử dụng v1.
6. Thiết kế contract test và security test.
7. Mô tả cách rollback nếu v2 lỗi sau khi triển khai.
8. Xác định rủi ro dữ liệu cá nhân khi thêm customerEmail.

### Hướng giải quyết

- Thêm customerEmail có thể là breaking về quyền riêng tư và authorization dù schema chỉ thêm field. Cần review phân quyền theo consumer, masking và audit trước khi công bố.
- Đổi status từ string sang object là breaking với consumer parser/model cũ; có thể thêm field statusDetails trong giai đoạn chuyển tiếp hoặc dùng v2.
- Thay bearer scope là thay đổi xác thực/ủy quyền có thể làm client cũ bị 401/403; cần hỗ trợ credential/scope chuyển tiếp hoặc version/policy rollout có kiểm soát.
- Mobile App và đối tác cần lịch migration dài hơn Admin Portal. Không sunset v1 chỉ vì v2 đã triển khai.
- Theo dõi traffic theo client ID, version, endpoint và status; không log access token hoặc email trong metric.
- Contract test phải xác minh response v1 vẫn có shape cũ; v2 có schema mới; security test xác minh consumer không có quyền không thể đọc email.
- Rollback cần giữ database/schema tương thích với cả v1 và v2 trong giai đoạn coexistence; tránh migration xóa field cũ trước khi hết phụ thuộc.
- Công bố migration guide, deprecation notice, owner và deadline cho từng nhóm consumer.

### Câu hỏi tự kiểm tra

1. Vì sao thêm một field JSON có thể vẫn phá vỡ consumer?
2. Backward compatibility khác forward compatibility như thế nào?
3. Khi nào nên dùng URL path versioning, header versioning hoặc không version explicit?
4. Vì sao API path /v2 không nhất thiết tương ứng với SDK version 2.0.0?
5. Expand-contract giúp tránh sự cố database trong quá trình deploy nhiều phiên bản ra sao?
6. Vì sao consumer-driven contract test không thay thế end-to-end test?
7. Cần dữ liệu nào trước khi công bố sunset date cho một API public?
8. Khi thay đổi auth scope hoặc lộ lỗ hổng ở v1, vì sao lịch hỗ trợ thông thường có thể cần rút ngắn?

Một chiến lược versioning API tốt giữ cho **hợp đồng, consumer và cách triển khai thay đổi theo nhịp có thể kiểm soát**. Bắt đầu bằng thay đổi additive khi có thể; khi phải phá vỡ contract, công bố phiên bản mới, hỗ trợ song song, đo consumer adoption và ngừng phiên bản cũ theo chính sách rõ ràng. Mọi quyết định cần được chứng minh bằng contract tests, telemetry, review bảo mật và khả năng rollback thực tế.
