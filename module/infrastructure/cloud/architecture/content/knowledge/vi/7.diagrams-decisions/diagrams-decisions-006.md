# Mô tả hợp đồng API, sự kiện và quyền sở hữu thành phần

> **Chương:** Sơ đồ và quyết định  
> **Module:** CLOUD_ARCHITECTURE  
> **Phạm vi:** Thiết kế kiến trúc ứng dụng trên đám mây từ yêu cầu nghiệp vụ đến lựa chọn mạng, compute, dữ liệu và mô hình triển khai. Bài học tập trung vào cách ghi rõ giao tiếp và trách nhiệm giữa các thành phần để có thể đánh giá độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo tư duy Well-Architected.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **hợp đồng API**, **hợp đồng sự kiện** và **hợp đồng quyền sở hữu**, đồng thời giải thích vì sao sơ đồ kiến trúc cần liên kết được với cả ba.
2. Mô tả một API đủ để client và server phát triển độc lập: endpoint, xác thực, dữ liệu, ý nghĩa nghiệp vụ, lỗi, idempotency, tương thích và yêu cầu vận hành.
3. Mô tả sự kiện tích hợp: thời điểm phát, nguồn sự thật, payload, phiên bản schema, tính thứ tự, cách giao nhận lại, xử lý lỗi và cơ chế phát lại.
4. Chỉ định chủ sở hữu dữ liệu, service, hợp đồng, hạ tầng và trách nhiệm on-call để tránh khoảng trống khi thay đổi hoặc gặp sự cố.
5. Vẽ sơ đồ container/luồng tương tác, chỉ ra ranh giới đồng bộ–bất đồng bộ, dữ liệu, niềm tin và điểm chịu trách nhiệm.
6. Dùng ADR, contract test và bảng đánh giá Well-Architected để biện minh và kiểm chứng quyết định thiết kế.

## 1. Vì sao phải mô tả hợp đồng cùng với sơ đồ?

Một sơ đồ có ba hộp **Frontend → Booking API → Database** chỉ cho biết có thành phần giao tiếp. Nó chưa trả lời được:

- Frontend gửi dữ liệu nào; API trả gì khi đã ghi thành công, khi bị tranh chấp chỗ hoặc khi hết thời gian chờ?
- API có được gọi lại an toàn sau lỗi mạng không? Làm thế nào để không tạo hai booking?
- Sau khi lưu booking, ai công bố sự kiện cho hệ thống thông báo? Sự kiện có thể bị giao trùng không?
- Ai là nơi duy nhất được quyết định trạng thái booking; các nhóm khác có được sửa trực tiếp dữ liệu không?
- Nhóm nào cập nhật hợp đồng, xử lý lỗi production, thu hồi dữ liệu và thông báo thay đổi phá vỡ tương thích?

**Hợp đồng (contract)** là tập cam kết quan sát được tại ranh giới giữa các thành phần. Nó mô tả **đầu vào, đầu ra, ý nghĩa, hành vi khi thất bại, quy tắc tương thích và trách nhiệm duy trì**. Một hợp đồng tốt giúp thành phần có thể thay đổi bên trong mà thành phần khác vẫn hoạt động trong phạm vi đã thống nhất.

Ba nhóm hợp đồng liên quan nhau:

| Nhóm | Trao đổi giữa ai | Cần xác định | Ví dụ |
|---|---|---|---|
| **API contract** | Client và service được gọi, thường đồng bộ | Đường dẫn/phương thức, schema, auth, mã phản hồi, timeout, idempotency, rate limit | Client gọi tạo booking; API trả booking ID hoặc lỗi rõ ràng |
| **Event contract** | Producer và các consumer, thường bất đồng bộ | Tên sự kiện, thời điểm phát, payload, schema, delivery/retry/ordering, retention, phiên bản | Booking Service phát BookingConfirmed để Notification Service xử lý |
| **Ownership contract** | Nhóm phát triển, chủ dữ liệu, platform và vận hành | Ai sở hữu thành phần, dữ liệu và hợp đồng; ai phê duyệt thay đổi; ai on-call | Nhóm Booking sở hữu trạng thái booking; nhóm Notification sở hữu logic gửi tin |

Hợp đồng **không nhất thiết là một file duy nhất**. OpenAPI hoặc AsyncAPI mô tả phần máy đọc được; ADR ghi lý do và đánh đổi; catalog/team registry ghi owner; dashboard và runbook thể hiện yêu cầu vận hành. Điều quan trọng là các nguồn này có thể liên kết, kiểm chứng và có người cập nhật.

### 1.1. Từ yêu cầu nghiệp vụ tới ranh giới giao tiếp

Giả sử thiết kế hệ thống đặt lịch dịch vụ:

- Người dùng phải biết chắc khi nào booking **đã được xác nhận**.
- Không có hai booking cùng chiếm một tài nguyên và khung giờ độc quyền.
- Thông báo qua email/SMS có thể đến chậm vài phút; lỗi nhà cung cấp thông báo không được làm sai giao dịch đặt lịch.
- Dịch vụ phân tích có thể nhận dữ liệu chậm, nhưng không được xem dữ liệu phân tích là nguồn sự thật để kiểm tra chỗ còn trống.

Từ đó suy ra: việc **ghi booking** cần hợp đồng API có hành vi đồng bộ và khả năng gửi lại an toàn; việc **thông báo** phù hợp với event sau khi transaction đã được commit; **Booking Service** sở hữu trạng thái giao dịch; **Notification Service** chỉ sở hữu trạng thái gửi thông báo.

### 1.2. “Hợp đồng” rộng hơn schema

Hai thành phần có thể dùng cùng schema JSON nhưng vẫn không tương thích về ý nghĩa:

- Field trạng thái chuyển từ “đã xác nhận” sang “đang chờ” mà không đổi tên.
- API trước đây trả lỗi khi hết chỗ, nay im lặng tạo booking ở danh sách chờ.
- Producer đổi thời điểm phát event từ **sau commit** thành **trước commit**, khiến consumer quan sát dữ liệu chưa tồn tại.
- Tên timestamp vẫn giống nhau, nhưng thay ý nghĩa từ thời điểm nghiệp vụ phát sinh sang thời điểm message được gửi.

Vì vậy phải ghi **ngữ nghĩa bất biến (invariant)**, điều kiện trước/sau, hành vi lỗi và giới hạn bảo đảm, không chỉ mô tả field và kiểu dữ liệu.

## 2. Định vị hợp đồng trên sơ đồ kiến trúc

### 2.1. Chọn góc nhìn phù hợp

Sơ đồ phục vụ các câu hỏi khác nhau:

| Góc nhìn | Giúp hiểu | Nên ghi rõ |
|---|---|---|
| **System context** | Tác nhân và hệ thống ngoài, ranh giới sản phẩm | Người dùng, bên thứ ba, giao tiếp và trách nhiệm cấp hệ thống |
| **Container/component** | Các service, datastore, queue, gateway và mối phụ thuộc | Ranh giới triển khai/dữ liệu, API đồng bộ, event bất đồng bộ, owner |
| **Sequence** | Trình tự tương tác của một luồng nghiệp vụ và khi lỗi | Transaction, request/response, event, trạng thái và đường thất bại |
| **Deployment** | Thành phần nằm ở region, zone, network và compute nào | Ranh giới tin cậy, public/private, HA, secret, đường kết nối |
| **Data lineage/event flow** | Ai tạo, biến đổi và tiêu thụ dữ liệu | Nguồn sự thật, tên event, topic, retention, consumer và độ trễ |

Không cố nhét mọi chi tiết vào một sơ đồ. Một bản overview dễ đọc nên dùng tên thành phần và mũi tên, sau đó **tham chiếu** đến hợp đồng chi tiết tại mỗi mũi tên.

### 2.2. Ví dụ container view

~~~mermaid
flowchart LR
    C[Web / Mobile] -->|HTTPS POST /v1/bookings| G[API Gateway]
    G -->|HTTPS + danh tính người dùng| B[Booking Service]
    B -->|SQL transaction| DB[(Booking Database)]
    B -->|Ghi cùng transaction| O[(Outbox)]
    O -->|Dispatcher: publish| Q[(Event Broker)]
    Q -->|booking.confirmed.v1| N[Notification Service]
    Q -->|booking.confirmed.v1| A[Analytics Consumer]
    N -->|HTTPS API| P[Email / SMS Provider]

    subgraph BookingDomain[Miền trách nhiệm: Team Booking]
        B
        DB
        O
    end
    subgraph NotificationDomain[Miền trách nhiệm: Team Notification]
        N
    end
    subgraph AnalyticsDomain[Miền trách nhiệm: Team Data]
        A
    end
~~~

Mỗi mũi tên có một dạng hợp đồng riêng:

- **Client → Gateway/Booking:** API contract đồng bộ, phải mô tả auth, phản hồi và lỗi.
- **Booking → Database/Outbox:** ràng buộc dữ liệu và transaction nội bộ Booking; không cấp cho consumer khác quyền cập nhật bảng booking.
- **Outbox → Broker → Consumer:** event contract, có khả năng giao lại thông điệp.
- **Notification → Provider:** API bên ngoài, cần timeout, retry và chính sách xử lý trạng thái kết quả không chắc chắn.

Sơ đồ logic trên **chưa thể hiện mạng, zone hoặc region**. Khi chuyển sang deployment view, cần thêm public/private boundary, workload identity, quản lý secret, mã hóa, quota và các thành phần dự phòng phù hợp. Nhãn “Team Booking” là trách nhiệm nghiệp vụ; owner hạ tầng broker hoặc account cloud có thể là Platform.

### 2.3. Mẫu chú giải cho mũi tên

Thay vì đặt mũi tên mơ hồ “calls” hoặc “uses”, nên ghi:

| Trường chú giải | Ví dụ |
|---|---|
| Kiểu giao tiếp | HTTPS đồng bộ / event bất đồng bộ / SQL nội bộ |
| Tên hợp đồng | CreateBooking API v1 / booking.confirmed.v1 |
| Chiều gọi hoặc phát | Web → Booking / Booking → Broker |
| Danh tính và quyền | JWT người dùng; service identity; quyền subscribe topic |
| Bảo đảm quan trọng | API chỉ trả 201 sau commit; event có thể được giao lại |
| Owner và liên kết tài liệu | Booking team; liên kết OpenAPI/AsyncAPI/catalog/ADR |

Khi sử dụng Mermaid, có thể gắn mũi tên với tên hợp đồng ngắn; chi tiết trường và semantics để trong bảng hay tài liệu cạnh sơ đồ. Sơ đồ không cần chứa toàn bộ payload.

## 3. Hợp đồng API: mô tả hành vi mà caller có thể dựa vào

### 3.1. Các phần tối thiểu

Một API contract chất lượng cần mô tả:

1. **Mục đích:** hành động nghiệp vụ nào, ai được phép gọi, điều kiện thành công.
2. **Địa chỉ và phương thức:** base path, HTTP method, cách định danh resource, version.
3. **Xác thực và phân quyền:** loại credential, scope/role, kiểm soát owner/tenant, thao tác bị từ chối.
4. **Request:** path/query/header/body, field bắt buộc, kiểu và định dạng, giới hạn kích thước, validation, định nghĩa thời gian/đơn vị.
5. **Response:** status code, schema thành công, Location hoặc trạng thái xử lý, header quan trọng.
6. **Error:** status code, mã lỗi máy đọc được, cấu trúc phản hồi, có thể retry hay không.
7. **Tính đúng đắn:** invariant, transaction boundary, idempotency, xử lý cạnh tranh.
8. **Vận hành:** timeout, rate limit, quota, SLO, trace/correlation ID, observability, khả năng tương thích và chính sách sunset.

OpenAPI có thể là **nguồn hợp đồng máy đọc được**, nhưng những điều khó biểu diễn hết bằng schema như “chỉ xác nhận sau commit” cần mô tả rõ ở phần description, tài liệu hành vi hoặc contract test.

### 3.2. Ví dụ yêu cầu tạo booking

Giả sử client gọi **POST /v1/bookings** qua HTTPS, dùng bearer access token và header **Idempotency-Key**. Client chỉ gửi định danh tài nguyên và slot. API xác định người dùng/tenant từ danh tính đã xác thực; không tin một customerId do client tự khai để cấp quyền.

Ví dụ request:

~~~http
POST /v1/bookings HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: 01JY-BOOKING-REQUEST-001
X-Request-Id: req-7a21

{
  "resourceId": "doctor-42",
  "slotId": "slot-2026-11-20T09:00:00+07:00"
}
~~~

Ví dụ response sau **commit thành công**:

~~~http
HTTP/1.1 201 Created
Content-Type: application/json
Location: /v1/bookings/bkg-817
X-Request-Id: req-7a21

{
  "id": "bkg-817",
  "resourceId": "doctor-42",
  "slotId": "slot-2026-11-20T09:00:00+07:00",
  "status": "CONFIRMED",
  "createdAt": "2026-11-18T05:00:00Z"
}
~~~

**Invariant:** nếu loại slot chỉ cho phép một booking, transaction ở nguồn dữ liệu chuẩn phải bảo đảm tối đa một booking xác nhận cho mỗi cặp tài nguyên/slot. Kiểm tra “slot còn trống” rồi ghi mà không có transaction/ràng buộc phù hợp có thể gây đặt trùng khi nhiều request đồng thời.

Nếu cùng Idempotency-Key và cùng ý định được gửi lại sau khi client mất response, server phải trả lại kết quả được lưu (hoặc trạng thái xử lý nếu chưa xong), không tạo một booking mới. Khóa cần được scope theo định danh caller và operation, có thời hạn lưu được công bố; cùng khóa nhưng payload khác phải được từ chối. Việc tạo khóa và bảo vệ yêu cầu đồng thời cần được thực hiện bền vững, tránh race condition.

### 3.3. Bảng phản hồi và chính sách lỗi

| Tình huống | HTTP status điển hình | Mã lỗi nghiệp vụ minh họa | Caller nên làm gì |
|---|---|---|---|
| Booking đã commit | **201 Created** | — | Lưu booking ID và Location |
| JSON/request không hợp lệ về cú pháp | **400 Bad Request** | INVALID_REQUEST | Sửa request; không retry y nguyên |
| Chưa xác thực/hết phiên | **401 Unauthorized** | UNAUTHENTICATED | Xác thực lại theo cơ chế hợp lệ |
| Đã xác thực nhưng không có quyền | **403 Forbidden** | ACCESS_DENIED | Không retry bằng cùng quyền; xem lại authorization |
| Slot đã bị người khác chiếm | **409 Conflict** | SLOT_UNAVAILABLE | Cho người dùng chọn slot khác |
| Cùng idempotency key nhưng ý định khác | **409 Conflict** | IDEMPOTENCY_CONFLICT | Tạo key mới cho ý định mới, không ghi đè key cũ |
| Dữ liệu hợp lệ về cú pháp nhưng vi phạm quy tắc input | **422 Unprocessable Content** nếu hệ thống chọn quy ước này | VALIDATION_FAILED | Sửa field theo thông tin lỗi |
| Vượt quota/rate limit | **429 Too Many Requests** | RATE_LIMITED | Retry theo Retry-After/backoff nếu phù hợp |
| Dependency quan trọng tạm ngừng | **503 Service Unavailable** | TEMPORARILY_UNAVAILABLE | Có thể retry có giới hạn với cùng key, theo deadline |

Không phải mọi lỗi 409 hoặc 5xx đều nên retry. Ví dụ hết slot là xung đột nghiệp vụ cần người dùng chọn lại; HTTP timeout có thể xảy ra **sau khi booking đã commit**. Client cần tra cứu bằng booking ID hoặc gọi lại với cùng idempotency key để giảm nguy cơ trùng.

Ví dụ lỗi có cấu trúc ổn định:

~~~json
{
  "code": "SLOT_UNAVAILABLE",
  "message": "Khung giờ đã được đặt.",
  "requestId": "req-7a21",
  "details": {
    "slotId": "slot-2026-11-20T09:00:00+07:00"
  }
}
~~~

Mã lỗi có tính máy đọc được phải ổn định qua phiên bản tương thích. Message hướng tới người dùng có thể thay đổi/ngôn ngữ hóa; client không nên dựa vào chuỗi thông báo để rẽ nhánh nghiệp vụ. Tránh đưa stack trace, connection string, secret hoặc dữ liệu nhạy cảm vào body lỗi và log.

### 3.4. Ví dụ OpenAPI rút gọn

Đây là một tài liệu **OpenAPI 3.0.3** minh họa một endpoint; tên server, quyền và giới hạn là giả định của bài học. Các chính sách vận hành và invariant vẫn cần giải thích trong tài liệu đi kèm.

~~~yaml
openapi: 3.0.3
info:
  title: Booking API
  version: 1.0.0
servers:
  - url: https://api.example.test
paths:
  /v1/bookings:
    post:
      operationId: createBooking
      summary: Tạo booking xác nhận nếu slot còn trống
      description: >
        Trả 201 chỉ sau khi transaction booking được commit.
        Cùng một Idempotency-Key và cùng yêu cầu sẽ không tạo booking thứ hai.
        Caller được nhận diện từ bearer token.
      security:
        - bearerAuth: []
      parameters:
        - name: Idempotency-Key
          in: header
          required: true
          description: Khóa riêng cho một ý định tạo booking.
          schema:
            type: string
            minLength: 1
            maxLength: 128
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateBookingRequest'
      responses:
        '201':
          description: Đã tạo và commit booking
          headers:
            Location:
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Booking'
        '400':
          description: Request không hợp lệ
        '401':
          description: Chưa xác thực
        '403':
          description: Không có quyền
        '409':
          description: Slot hoặc idempotency key xung đột
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ApiError'
        '429':
          description: Đã vượt giới hạn yêu cầu
        '503':
          description: Tạm thời không khả dụng
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
  schemas:
    CreateBookingRequest:
      type: object
      required: [resourceId, slotId]
      additionalProperties: false
      properties:
        resourceId:
          type: string
          minLength: 1
        slotId:
          type: string
          minLength: 1
    Booking:
      type: object
      required: [id, resourceId, slotId, status, createdAt]
      properties:
        id:
          type: string
        resourceId:
          type: string
        slotId:
          type: string
        status:
          type: string
          enum: [CONFIRMED]
        createdAt:
          type: string
          format: date-time
    ApiError:
      type: object
      required: [code, message, requestId]
      properties:
        code:
          type: string
        message:
          type: string
        requestId:
          type: string
~~~

Để đưa thành hợp đồng sản xuất, cần bổ sung ví dụ và schema lỗi cho tất cả phản hồi, ủy quyền theo tài nguyên/tenant, yêu cầu bảo vệ PII, versioning, quy định timeout và quota, chính sách key hết hạn, endpoint tra cứu và các điều kiện hợp lệ về thời gian. Phần OpenAPI chỉ mô tả **bề mặt giao tiếp**, không tự hiện thực transaction, IAM hoặc chống đặt trùng.

### 3.5. Đồng bộ hay bất đồng bộ ở tầng API?

Khi API chỉ trả sau commit, **201 Created** có ý nghĩa kết quả đã bền vững trong phạm vi cam kết. Nếu hệ thống nhận yêu cầu để xử lý nền và chưa xác nhận booking, nên dùng cơ chế như **202 Accepted** với operation ID và endpoint kiểm tra trạng thái; không trả trạng thái CONFIRMED khi chưa có bằng chứng hoàn tất.

Ví dụ:

| Thiết kế | Thời điểm client biết kết quả | Khi nào phù hợp | Rủi ro |
|---|---|---|---|
| Tạo booking đồng bộ | Sau transaction, trả 201 hoặc lỗi/xung đột | Giao dịch ngắn, cần biết ngay có giữ được slot | Tác vụ kéo dài có thể làm tăng độ trễ và tài nguyên chờ |
| Nhận xử lý bất đồng bộ | Trả 202 và operation ID, sau đó poll/callback | Công việc có thời gian lâu hoặc cần nhiều bước độc lập | Phải thiết kế trạng thái, TTL, callback, retry và lỗi cuối |

Không chọn 202 chỉ để giảm độ trễ hiển thị nếu người dùng thực sự cần biết giao dịch đã thành công. Những thao tác thanh toán hoặc đặt chỗ phải mô tả chính xác trạng thái cuối và cách xử lý trạng thái chưa chắc chắn.

### 3.6. Hợp đồng phi chức năng của API

Ngoài schema, nên công bố các giới hạn **đo được**:

| Thuộc tính | Ví dụ yêu cầu phải thống nhất |
|---|---|
| SLO | Tỷ lệ request thành công và p95/p99 ở tải định nghĩa, cửa sổ đo và điểm đo |
| Timeout | Deadline toàn luồng, giới hạn kết nối và việc hủy yêu cầu |
| Quota | Số request theo caller/tenant, hành vi 429, header Retry-After nếu có |
| Kích thước | Giới hạn body, số phần tử, pagination và sort/filter được hỗ trợ |
| Bảo mật | TLS, bearer identity, tenant isolation, audit và che PII trong log |
| Theo dõi | Correlation/request ID, trace span, metric lỗi theo mã ổn định |
| Phục hồi | Retry policy, xử lý request trùng và lỗi phụ thuộc |
| Vòng đời | Version hỗ trợ, chính sách deprecation, kênh thông báo consumer |

Các mục tiêu là ví dụ để thiết kế và kiểm chứng, không phải lời hứa rằng dùng API Gateway hoặc managed compute sẽ tự động đáp ứng SLO.

## 4. Hợp đồng sự kiện: mô tả điều đã xảy ra và cách bên khác nhận biết

### 4.1. Phân biệt event, command và request

Trong kiến trúc bất đồng bộ, không phải thông điệp nào cũng có cùng ý nghĩa:

| Loại | Ý nghĩa | Ví dụ | Đặc điểm cần lưu ý |
|---|---|---|---|
| **Event** | Một sự kiện đã xảy ra; mô tả sự thật trong quá khứ | BookingConfirmed | Producer công bố; nhiều consumer có thể quan tâm |
| **Command** | Yêu cầu một thành phần thực hiện hành động | SendBookingNotification | Có đích/trách nhiệm xử lý rõ; có thể thành công hoặc thất bại |
| **Query** | Yêu cầu thông tin, không chủ ý thay đổi trạng thái | GetBooking | Cần làm rõ tính mới/nhất quán của dữ liệu |

Event nên có tên ở thì quá khứ hoặc thể hiện trạng thái đã phát sinh. **BookingConfirmed** chỉ được phát sau khi trạng thái booking được commit. Một message có nội dung “hãy xác nhận booking” thực chất là command; gọi nó là event sẽ làm mơ hồ ai chịu trách nhiệm quyết định kết quả.

Phân biệt thêm:

- **Domain event:** phản ánh sự kiện trong ranh giới nghiệp vụ, có thể chứa chi tiết nội bộ; không mặc nhiên là hợp đồng cho dịch vụ khác.
- **Integration event:** phiên bản được chủ động công bố cho consumer ngoài ranh giới; payload tối giản, ổn định và có quy trình thay đổi.

Không nên tự động đưa tất cả domain event ra broker công khai. Điều đó làm lộ cấu trúc nội bộ, tăng coupling và có thể phát tán dữ liệu nhạy cảm.

### 4.2. Nội dung hợp đồng sự kiện

Một hợp đồng sự kiện cần ghi ít nhất:

1. **Tên, ý nghĩa và điều kiện phát:** sự kiện phản ánh chính xác trạng thái nào, chỉ phát trước hay sau commit?
2. **Producer và nguồn sự thật:** service nào quyết định sự kiện đúng; ai có quyền publish?
3. **Channel/topic và consumer:** nơi công bố, người đăng ký, các quy tắc truy cập.
4. **Envelope metadata:** event ID, event type, version, timestamp, aggregate ID, correlation ID, tenant scope khi cần.
5. **Payload:** field, kiểu, ý nghĩa, optional/required, quy tắc thời gian và dữ liệu nhạy cảm.
6. **Bảo đảm giao nhận:** at-most-once, at-least-once hoặc mức bảo đảm thực tế ở từng đoạn; có thể bị lặp/mất thứ tự không?
7. **Ordering và partition key:** thứ tự quan trọng theo booking, customer hay toàn hệ thống?
8. **Retry, DLQ, retention và replay:** điều gì xảy ra khi consumer chết, bị quá tải hoặc cần xây lại projection?
9. **Tương thích:** schema version, quy tắc thêm/bỏ field, thời gian hỗ trợ song song, owner phê duyệt.
10. **Yêu cầu vận hành:** độ trễ từ commit đến publish/consume, đo backlog, cảnh báo và quy trình ứng cứu.

Các tiêu chí trên cần được **ghi thành hợp đồng có thể tìm thấy**, không chỉ giả định thông qua hành vi hiện tại của một consumer.

### 4.3. Ví dụ event booking.confirmed phiên bản 1

Giả sử Booking Service đã commit một booking thành công và tạo integration event sau commit:

~~~json
{
  "eventId": "evt-80231",
  "eventType": "booking.confirmed",
  "schemaVersion": 1,
  "producer": "booking-service",
  "aggregateType": "booking",
  "aggregateId": "bkg-817",
  "aggregateVersion": 1,
  "occurredAt": "2026-11-18T05:00:00Z",
  "correlationId": "req-7a21",
  "data": {
    "bookingId": "bkg-817",
    "resourceId": "doctor-42",
    "slotId": "slot-2026-11-20T09:00:00+07:00",
    "status": "CONFIRMED"
  }
}
~~~

Giải thích những field quan trọng:

| Trường | Ý nghĩa | Quy tắc cần chốt |
|---|---|---|
| **eventId** | Định danh một lần phát sinh sự kiện logic | Ổn định nếu broker giao lại cùng event; dùng để deduplicate |
| **eventType** | Loại sự kiện nghiệp vụ | Không đổi ý nghĩa im lặng khi cùng tên |
| **schemaVersion** | Phiên bản cấu trúc payload | Quy tắc hỗ trợ/vòng đời và cách consumer phân biệt phiên bản |
| **producer** | Dịch vụ công bố sự kiện | Quyền publish và owner của hợp đồng |
| **aggregateId** | Định danh đối tượng nghiệp vụ | Dùng liên kết, partition/ordering nếu có |
| **aggregateVersion** | Phiên bản trạng thái đối tượng sau chuyển đổi | Hỗ trợ phát hiện event cũ, lặp hoặc đến sai thứ tự |
| **occurredAt** | Thời điểm sự kiện nghiệp vụ xảy ra | Định nghĩa UTC, phân biệt thời điểm publish và consume |
| **correlationId** | Nối giao dịch từ HTTP qua worker | Giúp trace/audit, không phải khóa chống trùng |
| **data** | Thông tin nghiệp vụ consumer cần | Tối thiểu hóa, tài liệu hóa các field và bảo vệ PII |

**eventId, aggregateVersion, correlationId phục vụ mục đích khác nhau.** Một correlation ID có thể nối nhiều event và nhiều request; không nên dùng nó thay event ID để chống trùng. Với hệ thống đa tenant, quy định rõ cách xác định tenant và kiểm soát quyền truy cập theo tenant; không chỉ tin một tenant ID trong payload nếu consumer có thể nhận thông điệp từ nguồn chưa được tin cậy.

Phạm vi payload cần được quyết định cùng với dữ liệu và quyền truy cập. Ví dụ này **không chứa email, số điện thoại hay tên bệnh nhân**. Notification Service có thể dùng tham chiếu booking ID và danh tính dịch vụ có quyền phù hợp để lấy thông tin cần thiết, hoặc nhận một payload tối thiểu đã được cấp phép tùy nhu cầu độ trễ và coupling. Chọn cách nào cũng phải cân nhắc PII, quyền truy cập, dữ liệu lưu trong DLQ, log và retention.

### 4.4. Catalog hợp đồng sự kiện

Một catalog YAML nội bộ có thể ghi các cam kết khó đặt hết trong JSON Schema. Đây là **mẫu minh họa riêng**, không tuyên bố là schema chuẩn của AsyncAPI hay CloudEvents:

~~~yaml
name: booking.confirmed
schemaVersion: 1
meaning: "Booking đã commit với trạng thái CONFIRMED."
producer:
  service: booking-service
  owningTeam: booking
channel:
  logicalName: booking.events
  partitionKey: aggregateId
consumers:
  - notification-service
  - analytics-consumer
delivery:
  assumption: at-least-once
  duplicatesPossible: true
  globalOrderGuaranteed: false
  consumerMustBeIdempotent: true
  orderingScope: "theo booking khi broker/cấu hình hỗ trợ"
failure:
  retry: "backoff có giới hạn"
  deadLetter: true
  replay: "chỉ theo quy trình đã được kiểm soát"
schema:
  required: [eventId, eventType, schemaVersion, aggregateId, occurredAt, data]
security:
  containsPersonalData: false
  publisherScope: booking-service-only
  subscriberPolicy: approved-consumers-only
operations:
  alertOwner: booking
  publishLagSlo: "theo mức dịch vụ được thỏa thuận"
~~~

AsyncAPI có thể mô tả kênh, message, payload, operation và schema cho API hướng sự kiện. JSON Schema hoặc schema registry hỗ trợ validation/compatibility; catalog quyền sở hữu và runbook vẫn cần bổ sung policy và hành vi vận hành. Hợp đồng sự kiện nên đi cùng version và pipeline như hợp đồng API.

### 4.5. Giao nhận không đồng nghĩa xử lý thành công chính xác một lần

Broker hoặc client có thể giao lại cùng message sau timeout, crash hoặc mất acknowledgement. Vì vậy cần phân biệt:

| Bảo đảm | Hệ quả | Điều cần thiết kế |
|---|---|---|
| **At-most-once delivery** | Có thể mất message, ít khả năng nhận lặp tại đoạn giao nhận đó | Dùng khi mất message được chấp nhận |
| **At-least-once delivery** | Message có thể được nhận nhiều lần | Consumer xử lý idempotent và có cơ chế ghi nhận tiến độ |
| **Exactly-once processing** trong phạm vi một nền tảng | Có thể áp dụng cho một số thao tác nội bộ dưới điều kiện cụ thể | Không suy diễn thành exactly-once end-to-end khi có API và hệ thống ngoài |

Với notification worker, các bước thông thường là: nhận message, xác minh schema/quyền, kiểm tra đã xử lý event ID hay chưa, thực hiện công việc, ghi trạng thái và acknowledge. Nhưng thao tác gọi email provider có thể thành công rồi worker crash trước khi lưu trạng thái; khi nhận lại sẽ có nguy cơ gửi trùng. Dùng idempotency token do provider hỗ trợ, hoặc có chính sách xử lý gửi trùng rõ ràng.

**Không dùng việc consumer nhận event như bằng chứng booking vừa được tạo.** Booking được xác nhận tại transaction của Booking Service; event là cơ chế thông báo sự thật đó. Queue bị trễ có thể làm Notification Service trễ mà không làm thay đổi trạng thái booking.

### 4.6. Transactional outbox giải quyết vấn đề dual-write

Nếu Booking Service thực hiện hai lệnh độc lập:

1. Ghi database thành công.
2. Publish event lên broker.

thì có thể crash giữa hai lệnh: booking đã tồn tại nhưng event không được phát. Đổi thứ tự cũng không giải quyết hoàn toàn: event có thể được phát nhưng transaction database thất bại.

**Transactional outbox** lưu booking và bản ghi event vào cùng transaction của database. Sau commit, một dispatcher đọc outbox để publish. Kết quả là có thể phát lại các event chưa xác nhận đã gửi, nhưng dispatcher có thể publish trùng nếu crash sau publish mà trước khi đánh dấu đã xử lý.

~~~mermaid
sequenceDiagram
    actor Client as Web / Mobile
    participant API as Booking API
    participant DB as Booking DB + Outbox
    participant Dispatcher as Outbox Dispatcher
    participant Broker as Event Broker
    participant Consumer as Notification Worker
    Client->>API: POST /v1/bookings + Idempotency-Key
    API->>DB: Transaction: kiểm tra slot, ghi booking, ghi outbox
    alt Commit thành công
        DB-->>API: booking ID
        API-->>Client: 201 Created
        Dispatcher->>DB: Đọc outbox đã commit
        DB-->>Dispatcher: booking.confirmed event
        Dispatcher->>Broker: Publish event
        Broker-->>Dispatcher: Ack publish
        Dispatcher->>DB: Đánh dấu đã publish
        Broker->>Consumer: Giao event (có thể lặp)
        Consumer->>Consumer: Deduplicate + xử lý
        Consumer-->>Broker: Ack sau xử lý theo policy
    else Không còn slot
        DB-->>API: Conflict / rollback
        API-->>Client: 409 Slot unavailable
    end
~~~

Những cam kết phải ghi vào contract:

- Event chỉ biểu diễn booking đã commit, không biểu diễn ý định trước khi commit.
- Publisher có thể phát lại cùng event ID; consumer phải xử lý lặp an toàn.
- Thời gian từ commit đến event được publish **không phải bằng 0**; cần theo dõi publish lag và backlog.
- Nếu dispatcher hoặc broker chết, outbox tồn tại để phát về sau trong giới hạn lưu trữ/retention và khả năng khôi phục đã thiết kế.
- Cần cơ chế cleanup outbox, replay, retry và cảnh báo tránh lưu tích tụ không kiểm soát.

### 4.7. Ordering, replay và sự kiện đến muộn

Không mặc nhiên giả định mọi event trong broker có **thứ tự toàn cục**. Nếu consumer phải xử lý tuần tự trạng thái của từng booking, cần thống nhất:

- **Ordering key:** ví dụ aggregateId là booking ID; broker/partition có đảm bảo thứ tự theo key trong trường hợp cấu hình và retry thực tế không?
- **Aggregate version:** consumer xử lý thế nào nếu nhận phiên bản 3 trước phiên bản 2?
- **Event tới muộn:** sự kiện booking.cancelled đến trước booking.confirmed thì projection phải làm gì?
- **Replay/backfill:** khi xây lại read model, có thể phát lại event cũ mà không gửi lại email hoặc tạo hiệu ứng bên ngoài không?
- **Retention:** broker giữ message bao lâu, DLQ giữ bao lâu, dữ liệu cá nhân đã xóa có còn bị phát lại không?

Ví dụ Analytics Consumer có thể lưu phiên bản mới nhất của từng booking và bỏ qua event có aggregateVersion không cao hơn phiên bản đã xử lý. Tuy nhiên, nếu logic phụ thuộc vào **tất cả chuyển đổi trung gian**, bỏ qua bản cũ là không đủ; phải có cơ chế chờ/gap detection/reconciliation phù hợp.

**Replay cho analytics và replay cho thông báo có ý nghĩa khác nhau.** Analytics có thể tái tạo projection; notification phải tránh gửi email xác nhận từ tháng trước khi phát lại sự kiện lịch sử. Contract phải mô tả chính sách replay của từng loại consumer.

### 4.8. Versioning và thay đổi hợp đồng sự kiện

Thêm một optional field có default/semantics rõ ràng thường ít rủi ro hơn đổi tên hoặc đổi nghĩa field đang dùng. Một quy trình phù hợp:

1. Xác định producer owner và danh sách consumer đang hoạt động.
2. Thêm schema mới, kiểm tra tương thích với các consumer còn được hỗ trợ.
3. Nếu có thay đổi phá vỡ, cung cấp **phiên bản event mới hoặc kênh chuyển tiếp** với giai đoạn hỗ trợ song song.
4. Triển khai consumer có thể đọc phiên bản mới trước khi producer ngừng phiên bản cũ.
5. Đo consumer adoption, message lỗi, DLQ và replay trước khi kết thúc hỗ trợ cũ.
6. Ghi ngày deprecation, phương án rollback và cách phục hồi projection.

Một event **không nên đổi nghĩa vì tên/version giữ nguyên**. Ví dụ BookingConfirmed trước đây chỉ phát sau khi đã giữ chỗ, nay phát ngay khi bắt đầu chờ thanh toán, là thay đổi phá vỡ ngữ nghĩa dù JSON schema không đổi.

## 5. Quyền sở hữu: ai có quyền quyết định, thay đổi và khôi phục?

### 5.1. Các loại ownership không được đánh đồng

| Đối tượng | “Sở hữu” có nghĩa là gì? | Ví dụ |
|---|---|---|
| **Business capability** | Chịu trách nhiệm quy tắc và kết quả nghiệp vụ | Booking team xác định thế nào là booking xác nhận |
| **Service/component** | Duy trì code, deploy, SLO và runbook của service | Booking team trực Booking Service |
| **Data / source of truth** | Quyết định dữ liệu chuẩn, schema, retention và kiểm soát sửa | Booking team sở hữu dữ liệu booking |
| **API/event contract** | Giữ nghĩa, version, thông báo thay đổi và compatibility | Booking team duy trì CreateBooking và BookingConfirmed |
| **Consumer projection** | Duy trì bảng riêng được tạo từ event, xử lý replay và lỗi consumer | Analytics team sở hữu read model phân tích |
| **Cloud infrastructure** | Chính sách nền tảng, account, network, broker vận hành và quota | Platform team có thể sở hữu broker và landing zone |
| **Security/governance** | Xác định policy IAM, dữ liệu nhạy cảm và ngoại lệ | Security team phê duyệt mức truy cập đặc biệt |
| **Cost/budget** | Chấp nhận chi phí và tối ưu theo giá trị nghiệp vụ | Product/service owner quản ngân sách workload |

Một broker do Platform vận hành **không có nghĩa Platform sở hữu ngữ nghĩa của mọi event**. Tương tự, database do dịch vụ managed cloud vận hành không có nghĩa nhà cung cấp chịu trách nhiệm về quyền truy cập, logic nghiệp vụ hoặc chất lượng dữ liệu khách hàng. Ranh giới trách nhiệm cần nêu rõ theo shared responsibility model của dịch vụ đã chọn.

### 5.2. Đặt ranh giới dữ liệu và quyền ghi

Nguyên tắc định hướng:

- Mỗi dữ liệu nghiệp vụ cần có **nguồn sự thật được chỉ định** và quyền thay đổi được kiểm soát.
- Các service khác truy cập thông qua API/event hoặc một giao thức chia sẻ có hợp đồng rõ; tránh ghi trực tiếp bảng của service khác vì làm phụ thuộc chặt vào schema nội bộ.
- Consumer có thể giữ **read model/cache** của riêng mình; phải công bố độ trễ đồng bộ, replay và hành vi khi dữ liệu cũ.
- Nếu nhiều nhóm cùng cập nhật một nguồn dữ liệu, xác định cơ chế phối hợp, quyền ghi và cách giải quyết xung đột thay vì mặc nhiên xem dữ liệu “không có owner”.

Ví dụ: Booking Service xác nhận slot, Notification Service không tự chuyển booking từ PENDING sang CONFIRMED. Notification Service có thể lưu trạng thái DELIVERY_PENDING/DELIVERED trong dữ liệu riêng của mình; nếu nghiệp vụ cần hiển thị trạng thái gửi thông báo, định nghĩa API/event trao đổi hoặc một projection rõ ràng.

**Không nhất thiết tách database vật lý theo mỗi module.** Với modular monolith hoặc giai đoạn chuyển đổi, vẫn có thể dùng một database vật lý nhưng quy định schema/bảng thuộc module nào, API nội bộ và quyền sửa. Ranh giới sở hữu dữ liệu quan trọng hơn số lượng instance database.

### 5.3. Ví dụ service catalog và contract registry

| Thành phần/hợp đồng | Owning team | Trách nhiệm giao tiếp | Nguồn dữ liệu / dependency | Người trực sự cố |
|---|---|---|---|---|
| Booking API | Booking | CreateBooking, GetBooking; version và mã lỗi | Booking DB | Booking on-call |
| Booking DB | Booking (dữ liệu), Platform (nền tảng) | Transaction và schema booking | Managed relational DB | Booking + Platform theo tầng sự cố |
| booking.confirmed.v1 | Booking | Event semantics, schema, publish lag | Outbox và broker | Booking on-call |
| Event broker | Platform | Throughput, retention, access policy và availability broker | Hạ tầng message | Platform on-call |
| Notification Consumer | Notification | Subscribe, dedup, retry, DLQ, gửi tin | Broker + provider email/SMS | Notification on-call |
| Analytics Read Model | Data/Analytics | Projection, reconciliation, replay | Các integration event được phép | Analytics on-call |
| API gateway | Platform và Booking theo chính sách | Routing/TLS/quotas nền tảng; API auth/semantics do Booking định nghĩa | Edge/network | Platform + Booking theo triệu chứng |

Một catalog thực tế nên bổ sung service ID, repository, environment, channel hỗ trợ, owner dự phòng, link dashboard/runbook, link OpenAPI/AsyncAPI, thời gian hỗ trợ phiên bản, dữ liệu nhạy cảm, SLO và danh sách dependency. **Owner là một vai trò/nhóm có thể được duy trì**, không chỉ địa chỉ của một cá nhân.

### 5.4. RACI cho thay đổi hợp đồng

RACI: **R** thực hiện, **A** chịu trách nhiệm cuối cùng, **C** được tham vấn, **I** được thông báo. Bảng dưới đây chỉ là cách tổ chức minh họa; mỗi tổ chức điều chỉnh theo quy trình riêng.

| Hoạt động | Booking | Notification | Analytics | Platform | Security |
|---|---|---|---|---|---|
| Xác định nghĩa CreateBooking API | **A/R** | C | I | C | C |
| Phát hành schema booking.confirmed mới | **A/R** | C | C | I | C |
| Cập nhật consumer gửi thông báo | C | **A/R** | I | I | C |
| Kiểm soát broker/quota/ACL | C | C | C | **A/R** | C |
| Phê duyệt ngoại lệ dữ liệu nhạy cảm | C | C | C | I | **A/R** |
| Chạy test hợp đồng producer–consumer | **A** | R | R | I | I |
| Xử lý lỗi publish từ outbox | **A/R** | I | I | C | I |
| Xử lý message lỗi trong Notification DLQ | C | **A/R** | I | C | I |

Khi một sự cố trải qua nhiều thành phần, cần định nghĩa cách **phân tuyến và phối hợp incident**; không thể trả lời “broker của Platform nên Platform chịu mọi lỗi event” hoặc “producer đã publish nên consumer phải tự xử lý hết”. Mỗi owner chịu hành vi trong ranh giới, đồng thời hỗ trợ truy vết xuyên dịch vụ.

### 5.5. Hợp đồng ownership cần có chu kỳ bảo trì

Những trường nên có trong hồ sơ:

~~~yaml
componentId: booking-service
businessCapability: bookings
owningTeam: booking
onCall: booking-oncall
dataOwner: booking
apiContracts:
  - create-booking-v1
eventContracts:
  - booking.confirmed.v1
dependencies:
  - booking-database
  - event-broker
runtime:
  environment: production
  regionPolicy: approved-regions
assurance:
  runbook: "link-to-controlled-runbook"
  dashboard: "link-to-controlled-dashboard"
  securityContact: security-review
review:
  cadence: "theo chính sách tổ chức"
  lastVerified: "2026-11-18"
~~~

Đây là **mẫu catalog nội bộ**, không phải schema chuẩn bắt buộc. Địa chỉ on-call và link phải trỏ đến hệ thống quản trị có quyền phù hợp, không nhúng mật khẩu hay khóa.

Khi dịch vụ đổi chủ sở hữu, cần chuyển quyền truy cập, dashboard, runbook, hợp đồng đang công bố, danh sách consumer và trách nhiệm xử lý sự cố. Một sản phẩm có thể vận hành tốt hôm nay nhưng trở nên khó thay đổi khi catalog và owner không được cập nhật theo nhân sự và cấu trúc đội.

## 6. Biểu diễn luồng lỗi và ranh giới tin cậy

### 6.1. Sơ đồ trình tự có đường thành công và thất bại

Sơ đồ container cho thấy quan hệ tĩnh; sequence diagram giải thích thứ tự và kết quả khi các thành phần phối hợp. Khi vẽ một luồng quan trọng, nên có ít nhất **nhánh thành công, lỗi nghiệp vụ, lỗi phụ thuộc và cách xử lý request lặp**.

~~~mermaid
sequenceDiagram
    actor User as Người dùng
    participant API as Booking API
    participant DB as Booking DB
    participant D as Outbox Dispatcher
    participant MQ as Event Broker
    participant W as Notification Worker
    User->>API: POST booking (token, idempotency key)
    API->>API: Authenticate + authorize + validate
    API->>DB: Begin transaction, check slot and idempotency
    alt Slot hợp lệ, chưa có booking
        API->>DB: Insert booking and outbox, commit
        DB-->>API: Commit OK
        API-->>User: 201 Created, booking ID
        D->>DB: Poll committed outbox
        DB-->>D: Event data
        D->>MQ: Publish booking.confirmed.v1
        MQ->>W: Deliver event
        W->>W: Deduplicate, process
    else Slot bị tranh chấp
        DB-->>API: Constraint conflict
        API-->>User: 409 SLOT_UNAVAILABLE
    else Request với key cũ và cùng payload
        DB-->>API: Saved booking result
        API-->>User: Kết quả đã lưu, không tạo mới
    end
    Note over User,W: HTTP success và notification delivery là hai trạng thái khác nhau
~~~

Đối với timeout, có thể không biết phía server đã commit hay chưa. Client cần dùng **cùng idempotency key** khi retry hoặc dùng API tra cứu trạng thái theo hợp đồng. Với một API trả 202, sơ đồ cần bổ sung operation state, polling/callback và trạng thái thất bại cuối cùng.

### 6.2. Ranh giới bảo mật và dữ liệu trên sơ đồ

Những điểm bắt buộc xem khi kiến trúc chạy trên cloud:

| Ranh giới | Câu hỏi | Cách ghi trên sơ đồ/hợp đồng |
|---|---|---|
| Internet → Edge | HTTPS/TLS, WAF, DDoS protection, rate limit và route? | Đánh dấu public ingress, cơ chế bảo vệ và owner |
| Edge → Booking | Token/identity được chuyển và xác minh thế nào? | Auth method, token audience, workload identity và quyền |
| Booking → DB | DB có private access, least privilege, encryption và timeout không? | Kênh private, data owner, transaction boundary |
| Producer → Broker | Ai được publish đúng topic, event có chứa PII không? | Publish ACL, schema/data classification, retention |
| Broker → Consumer | Ai được subscribe; có tách tenant và giới hạn replay không? | Subscribe ACL, identity, audit và DLQ access |
| Consumer → Provider | Bí mật được cất ở đâu, lỗi/response được xử lý thế nào? | Secret manager, timeout/retry và provider contract |

Các boundary cần được đánh dấu trên deployment/network view. Có WAF hoặc TLS **không thay thế** kiểm soát đối tượng/tenant ở Booking Service; một user hợp lệ vẫn có thể bị từ chối đọc booking của người khác.

### 6.3. Mối liên hệ giữa hợp đồng và kiến trúc vật lý

Hợp đồng API/event chủ yếu định nghĩa **hành vi logic**, nhưng khả năng đáp ứng còn phụ thuộc triển khai:

- API SLO phụ thuộc tải, số instance, load balancer, database, pool và vùng triển khai.
- Event publish-lag phụ thuộc outbox, dispatcher, broker, partition, quota, lưu trữ và backlog.
- Quyền sở hữu hạ tầng cần rõ ở account/project, network, identity, KMS, database và broker.
- Khả năng chịu lỗi zone/region cần xét **tất cả** thành phần trên đường đi, không suy ra chỉ từ số replica Booking API.
- Chi phí bao gồm network egress, broker throughput/retention, trace/log, database, queue, dự phòng và các môi trường thử nghiệm.

Một lời cam kết “sự kiện đến consumer trong 2 giây” chỉ có ý nghĩa khi biết cách đo từ **commit** đến **consumer nhận/xử lý**, điều kiện tải và percentile/ngoại lệ. Sơ đồ nên dẫn đến metric và dashboard kiểm chứng cam kết đó.

## 7. Quản lý thay đổi và kiểm thử hợp đồng

### 7.1. Phân biệt thay đổi tương thích và thay đổi phá vỡ

Một thay đổi được coi là **tương thích** khi mọi consumer đang thuộc phạm vi hỗ trợ tiếp tục hoạt động đúng theo cam kết. Đây là đánh giá theo **hành vi và cách consumer dùng hợp đồng**, không chỉ theo kết quả so sánh hai file schema.

| Thay đổi | Có thể tương thích? | Điều kiện cần kiểm tra |
|---|---|---|
| Thêm field **optional** trong response API | Thường có thể | Client bỏ qua field lạ, không phụ thuộc thứ tự field |
| Thêm field **bắt buộc** vào request | Thường phá vỡ | Client cũ không gửi được; cần optional/default hoặc version mới |
| Xóa/đổi tên field response | Thường phá vỡ | Consumer có thể đang dựa vào field cũ |
| Đổi ý nghĩa enum/status hoặc phát event sớm hơn | Có thể phá vỡ dù schema giống | Từng consumer có giả định nghiệp vụ gì? |
| Thêm field optional vào event | Có thể tương thích | Consumer xử lý unknown field và thiếu field theo version |
| Đổi type string thành number | Thường phá vỡ | Parser/validation, dữ liệu lưu trước đó và replay |
| Đổi thứ tự giao event | Có thể phá vỡ | Consumer có phụ thuộc thứ tự trạng thái không? |
| Đổi chính sách idempotency hoặc retention | Có thể phá vỡ | Client retry trong khoảng bao lâu, consumer cần replay từ lúc nào? |
| Giảm quota hoặc rút ngắn timeout | Có thể phá vỡ vận hành | SLO và profile tải đang dựa vào giới hạn cũ không? |

**Versioning không chữa được việc đổi nghĩa âm thầm.** Có thể đặt major version trong URL, header hoặc định danh message tùy quy ước tổ chức, nhưng phải công bố thời gian hỗ trợ, migration và cách phát hiện consumer cũ trước khi ngừng hợp đồng.

### 7.2. Quy trình thay đổi hợp đồng có owner

Một vòng phát hành có thể mô tả:

~~~mermaid
flowchart TD
    A[Đề xuất thay đổi API / event] --> B[Owning team phân tích invariant và compatibility]
    B --> C[Tra cứu consumer / owner / chính sách dữ liệu]
    C --> D{Có phá vỡ hợp đồng?}
    D -- Không --> E[Cập nhật schema + docs + tests]
    D -- Có --> F[Thiết kế version mới / migration / hỗ trợ song song]
    F --> E
    E --> G[CI: lint + schema + contract + security tests]
    G --> H{Đạt và được review?}
    H -- Chưa --> B
    H -- Có --> I[Triển khai và quan sát canary / môi trường thử]
    I --> J[Consumer xác nhận tương thích]
    J --> K[Rollout, theo dõi SLI + lỗi + DLQ]
    K --> L[Chỉ deprecate bản cũ khi đủ điều kiện]
~~~

Với hợp đồng bất đồng bộ, thường cần **consumer có khả năng đọc bản mới trước** khi producer ngừng bản cũ. Với API, producer có thể hỗ trợ hai version đồng thời cho đến khi client cập nhật. Không có thứ tự triển khai duy nhất cho mọi hệ thống; phải xét đường dữ liệu và mức backward/forward compatibility thực tế.

### 7.3. Các lớp kiểm thử nên có

| Phép thử | Phát hiện vấn đề gì? | Ví dụ áp dụng |
|---|---|---|
| **Schema lint/validation** | Thiếu field, sai kiểu, naming/version không theo quy ước | Kiểm tra OpenAPI, JSON Schema hoặc AsyncAPI trong CI |
| **Provider contract test** | Producer/API thực tế không tuân thủ spec | POST booking trả 201 với schema và header cam kết |
| **Consumer-driven contract test** | Producer thay đổi làm hỏng giả định consumer | Notification yêu cầu các field của booking.confirmed.v1 |
| **Backward compatibility check** | Thay đổi xóa/đổi field hoặc enum phá vỡ | So sánh schema mới với contract đã công bố |
| **Integration test** | Routing/auth/transaction/broker khác thực tế | Test API → DB/outbox → broker → consumer |
| **Concurrency/idempotency test** | Duplicate, race condition, response mất | Gửi cùng key nhiều lần, tranh chấp slot đồng thời |
| **Failure/replay test** | Retry/DLQ/ordering không đúng | Kill consumer sau xử lý trước ack, replay event cũ |
| **Security test** | Thiếu auth, phân quyền tenant, rò PII | Gọi booking của tenant khác, đọc topic không được cấp quyền |
| **Performance test** | Hợp đồng SLO không đạt tại tải đã định | p95 API, publish lag, oldest message age, backlog |

**Contract test không thay thế integration test hoặc thử lỗi.** Schema đúng không chứng minh database transaction chính xác; mock provider thành công không cho biết production sẽ xử lý timeout và giao lại message ra sao.

Ví dụ bộ kiểm thử hành vi cho API tạo booking:

~~~text
Given: slot A còn trống, caller có quyền, key K chưa sử dụng
When: POST /v1/bookings với resource/slot A và K
Then: 201, trả booking ID và Location, DB chỉ có một booking xác nhận.

Given: kết quả của key K đã được commit
When: gửi lại cùng request và K
Then: trả cùng kết quả nghiệp vụ, không tạo thêm booking/event logic.

Given: key K đã gắn với slot A
When: dùng lại K cho slot B
Then: trả xung đột, không ghi booking mới.

Given: slot A đã được đặt bởi giao dịch khác
When: caller khác đặt cùng slot
Then: trả lỗi xung đột, DB vẫn chỉ có một booking xác nhận.

Given: email provider ngừng hoạt động
When: booking đã commit
Then: trạng thái booking không đổi; event chờ xử lý/retry theo policy.
~~~

Ví dụ kiểm thử consumer:

~~~text
Given: event E đã xử lý thành công
When: broker giao lại cùng eventId E
Then: không tạo hiệu ứng nghiệp vụ trùng ngoài chính sách.

Given: consumer nhận schemaVersion không được hỗ trợ
When: validate event
Then: xử lý theo policy lỗi/parking/DLQ, cảnh báo và không im lặng mất sự kiện.

Given: event booking.cancelled đến trước event booking.confirmed
When: projection có yêu cầu đảm bảo trạng thái mới nhất
Then: dựa trên aggregateVersion và quy tắc reconciliation đã cam kết.
~~~

### 7.4. Sự ổn định cần có trong CI/CD

Một pipeline thực tế nên có điểm kiểm tra tương ứng:

1. **Trước merge:** lint spec, schema compatibility, auth/security review, tests provider/consumer và kiểm tra docs/owner.
2. **Trước deploy:** inventory consumer, kế hoạch version/schema, quyền API/broker, chiến lược rollout và rollback.
3. **Khi canary:** theo dõi error rate từng mã lỗi, p95, tỷ lệ booking thành công, publish lag, consumer lag và DLQ.
4. **Sau deploy:** xác nhận phiên bản đang phục vụ, ghi nhận adoption, theo dõi retry/backlog, cập nhật catalog và ADR.
5. **Trước deprecation:** có bằng chứng không còn consumer được hỗ trợ lệ thuộc phiên bản cũ, có thông báo và phương án xử lý dữ liệu lưu lịch sử.

Đặc biệt, **rollback producer không chắc rollback được schema/data/event đã phát**. Event đã được consumer đọc hoặc dữ liệu đã migrate có thể không thể đảo ngược đơn giản; kế hoạch cần xác định biện pháp bù trừ/reconciliation khi cần.

## 8. Ghi quyết định kiến trúc bằng ADR

**Architecture Decision Record (ADR)** lưu lại một quyết định có ảnh hưởng dài hạn, lý do, lựa chọn khác và cách kiểm chứng. ADR phù hợp với các chủ đề khó nhìn thấy chỉ qua sơ đồ: tại sao booking trả 201 thay vì 202, vì sao dùng transactional outbox, vì sao Booking Service sở hữu dữ liệu và vì sao Notification không được ghi trực tiếp database đó.

### 8.1. Mẫu ADR cho việc phát event sau commit

~~~text
ADR-006 — Sử dụng transactional outbox cho booking.confirmed

Trạng thái: Accepted
Owner: Booking team
Ngày ghi nhận: 2026-11-18

Bối cảnh:
- Booking đã được commit phải có đường thông báo cho các consumer.
- Không thể dùng transaction database để commit atomically với broker
  khi hai hệ thống không có cơ chế giao dịch chung đã được chứng minh.
- Queue và worker có thể gặp lỗi và xử lý trùng.

Quyết định:
- Booking transaction ghi booking + outbox trong cùng DB.
- Dispatcher publish event sau commit.
- Event có eventId, schemaVersion, aggregateId và correlationId.
- Consumer xử lý idempotent; owner theo dõi publish lag và DLQ.

Lựa chọn đã xem:
A. Gọi trực tiếp Notification API trước khi trả kết quả.
B. Ghi DB rồi publish event bằng hai lệnh độc lập.
C. Transactional outbox + broker + consumer idempotent.

Lý do chọn C:
- Tách lỗi Notification khỏi kết quả transaction booking.
- Có bản ghi event bền vững để publish lại sau lỗi.
- Phù hợp nhiều consumer mà không buộc Booking gọi từng consumer.

Đánh đổi và rủi ro còn lại:
- Cần dispatcher, xử lý phát trùng, cleanup outbox, monitoring.
- Event đến trễ; không đảm bảo thứ tự toàn cục hoặc exactly-once end-to-end.
- Chi phí broker, log, retries, retention và vận hành tăng.

Bằng chứng kiểm chứng:
- Crash trước/sau publish; event không mất logic và consumer chống lặp.
- Đo publish lag và oldest message age ở tải mục tiêu.
- Kiểm tra ACL: chỉ Booking được publish event này.
- Test schema compatibility và đường replay được kiểm soát.

Xem xét lại khi:
- SLO/chi phí/volume hoặc mô hình transaction thay đổi đáng kể.
~~~

Một ADR không cần quá dài. Nó cần đủ thông tin để người đến sau hiểu **quyết định trả lời nhu cầu nào**, **đánh đổi đang được chấp nhận**, **ai chịu trách nhiệm** và **bằng chứng nào chứng minh đủ tốt**. Nếu kiến trúc thay đổi, tạo ADR mới thay thế hoặc cập nhật trạng thái thay vì xóa lịch sử lý do.

### 8.2. Liên kết ADR với hợp đồng và sơ đồ

Mỗi quyết định quan trọng nên truy vết theo hướng:

~~~text
Yêu cầu nghiệp vụ / SLO / ràng buộc
    ↓
ADR (quyết định + đánh đổi + owner)
    ↓
Sơ đồ container / sequence / deployment
    ↓
OpenAPI / event schema / ownership catalog
    ↓
Test + dashboard + runbook
    ↓
Quan sát thực tế → xem xét lại ADR hoặc hợp đồng
~~~

Ví dụ nếu yêu cầu thay đổi từ “thông báo trong vài phút” sang “thông báo trong 5 giây ở p99” thì cần rà soát cả ADR outbox, capacity dispatcher/queue/worker, hợp đồng event về publish/processing lag, chi phí và SLO. Chỉ đổi một dòng tài liệu mà không kiểm chứng hệ thống là chưa hoàn thành thay đổi kiến trúc.

## 9. Đánh giá hợp đồng và ownership theo Well-Architected

Well-Architected giúp kiểm tra thiết kế ở nhiều góc độ. Bảng sau sử dụng sáu trụ cột của **AWS Well-Architected** như bộ câu hỏi tham chiếu; việc áp dụng không yêu cầu dùng AWS.

| Trụ cột | Câu hỏi về hợp đồng API/event và ownership | Bằng chứng cần có |
|---|---|---|
| **Operational Excellence** | Có catalog owner, dashboard, runbook và quy trình thay đổi hợp đồng không? | Contract registry, on-call, CI/CD checks, incident drill |
| **Security** | API có auth/authorization, broker có ACL, payload có hạn chế dữ liệu nhạy cảm không? | Test truy cập sai tenant, policy IAM, encryption, audit |
| **Reliability** | Timeout, retry, idempotency, DLQ, outbox và recovery có được xác định rõ? | Duplicate/replay test, fault injection, restore và SLO |
| **Performance Efficiency** | Có giới hạn API, tải event, partition key, consumer lag và capacity plan không? | Load test, p95/p99, backlog, DB pool, throughput |
| **Cost Optimization** | Có đo chi phí request, egress, broker retention, logs, DLQ và dự phòng không? | Cost allocation theo service, budget, tối ưu retention |
| **Sustainability** | Có tránh duplicate work, event payload thừa, lưu trữ và replay không cần thiết không? | Bằng chứng sử dụng tài nguyên, lifecycle dữ liệu, scale-in |

### 9.1. Các đánh đổi thực tế

| Quyết định | Lợi ích | Chi phí/rủi ro mới |
|---|---|---|
| API đồng bộ trả kết quả sau commit | Caller biết ngay booking đã xác nhận | Độ trễ/request concurrency tăng khi DB chậm |
| Event thông báo sau commit | Giảm coupling và cho phép xử lý nền độc lập | Eventual consistency, outbox/queue, replay, DLQ |
| Payload event chứa nhiều dữ liệu | Consumer ít phải gọi lại producer | Tăng nguy cơ PII, coupling, egress, retention |
| Payload chỉ chứa tham chiếu | Tối thiểu dữ liệu, ít lộ thông tin | Consumer cần fetch, tăng phụ thuộc/rủi ro truy cập khi replay |
| Broker dùng chung | Dễ vận hành, tăng hiệu quả sử dụng | Shared quota và blast radius; yêu cầu ACL, tenant isolation |
| Broker/topic cô lập theo miền nghiệp vụ | Giảm ảnh hưởng chéo và phân quyền rõ | Tăng số tài nguyên, vận hành và chi phí |
| API/event có owner rõ | Thay đổi/ứng cứu nhanh và nhất quán | Cần đầu tư cập nhật catalog, phối hợp consumer |

Không có lựa chọn luôn tối ưu. Một đội nhỏ có thể bắt đầu bằng modular monolith với API nội bộ và outbox/queue đơn giản. Khi consumer, tải và yêu cầu độc lập tăng, có thể tách service nhưng vẫn giữ **hợp đồng và ownership đã định nghĩa** làm ranh giới.

### 9.2. Kịch bản đánh giá lỗi

Giả sử Notification Consumer bị lỗi 20 phút nhưng Booking API vẫn hoạt động.

1. **Reliability:** booking phải commit đúng; queue đủ retention, retry/backoff và DLQ đã thiết kế; sự kiện không bị mất khi dispatcher/broker khởi động lại.
2. **Operations:** Booking on-call theo dõi publish lag, Notification on-call theo dõi consumer lag; có quy trình phối hợp khi chưa rõ sự cố ở đâu.
3. **Security:** không mở rộng ACL hoặc tắt xác thực để “chữa cháy” backlog; kiểm tra event chứa dữ liệu nào.
4. **Performance:** khi consumer trở lại, giới hạn tốc độ và connection để không làm nghẽn provider hoặc những workload khác.
5. **Cost:** đo queue storage, retry, log và chi phí gửi lại; tránh retry vô hạn.
6. **Sustainability:** xử lý backlog có ưu tiên, không replay vô điều kiện những thông báo đã hết giá trị nghiệp vụ.

Một tuyên bố “kiến trúc đã chịu được lỗi consumer” chỉ có giá trị sau khi **thử ngắt consumer**, đo backlog, kiểm tra hiệu ứng trùng và xác nhận phục hồi theo yêu cầu đã thống nhất.

## 10. Lỗi thiết kế thường gặp

| Dấu hiệu | Hậu quả | Cách khắc phục |
|---|---|---|
| Chỉ vẽ mũi tên “Service A calls B” | Không biết method, auth, thời gian chờ và lỗi | Gắn mũi tên với tên hợp đồng và link spec |
| OpenAPI có schema nhưng không ghi nghĩa nghiệp vụ | Client có thể hiểu sai thời điểm xác nhận | Viết invariant, pre/postconditions và contract test |
| Trả 200/201 khi chỉ mới đưa vào queue | Client tưởng giao dịch đã chắc chắn | Dùng trạng thái/202 phù hợp và hợp đồng kiểm tra tiến độ |
| Retry POST không có idempotency | Tạo booking/giao dịch lặp | Khóa idempotency + transaction/constraint |
| Phát event trước khi DB commit | Consumer xử lý sự kiện chưa thực sự xảy ra | Commit trước khi publish; dùng outbox khi phù hợp |
| Hai thao tác DB write và broker publish không có recovery | Event bị mất khi crash giữa hai bước | Transactional outbox hoặc cơ chế khôi phục được chứng minh |
| Consumer tin mọi message chỉ đến một lần | Trùng gửi tin hoặc trùng ghi dữ liệu | Idempotent processing, dedup, retry/DLQ |
| Tất cả service sửa cùng bảng của nhau | Mất owner và coupling schema nội bộ | Giao diện truy cập có hợp đồng, quyền ghi theo ranh giới |
| Có owner code nhưng không có owner production | Sự cố không biết ai trực, SLA trách nhiệm không rõ | Catalog on-call, runbook, incident routing |
| Version mới đổi nghĩa field âm thầm | Hỏng consumer dù schema vẫn parse được | Quản lý semantic version/contract review |
| Event chứa toàn bộ dữ liệu khách hàng cho tiện | PII lan sang log, DLQ, nhiều consumer | Tối thiểu payload, phân loại dữ liệu và ACL |
| Xóa topic/event cũ ngay khi deploy producer mới | Consumer còn tồn tại hoặc replay thất bại | Migration/dual-read, đo adoption, deprecation có thông báo |

## 11. Bài thực hành: hợp đồng và sơ đồ cho nền tảng đặt lịch

**Tình huống:** Một sản phẩm có Web/Mobile, Booking Service và Booking Database. Sau khi đặt lịch, khách nhận email; Analytics cần dữ liệu về lượt đặt lịch. Nhóm dự kiến dùng một event broker quản lý trên cloud. Khi traffic tăng, hệ thống phải đảm bảo không đặt trùng, không để email provider làm chậm API và cho phép cập nhật consumer độc lập. Booking team, Notification team, Analytics team và Platform team có phạm vi vận hành riêng.

**Các giả định ban đầu để thảo luận:** API tạo booking có mục tiêu phản hồi trong một ngưỡng p95 được đội sản phẩm xác nhận; email được phép trễ vài phút; mỗi slot độc quyền chỉ được xác nhận cho một booking; event có thể giao lại; broker do Platform vận hành. Các con số tải, chi phí và RTO/RPO chưa biết nên phải ghi là cần đo, không tự biến thành cam kết.

Hãy chuẩn bị bộ tài liệu thiết kế gồm:

1. **Sơ đồ container:** thể hiện client, gateway, Booking Service/DB/outbox, broker, Notification, Analytics, provider và nhãn mũi tên sync/async. Ghi owner và ranh giới public/private.
2. **API contract:** định nghĩa POST tạo booking; request/response, bearer auth và tenant ownership, 201/409/429/503, idempotency, mã lỗi và cơ chế tra cứu khi request timeout.
3. **Event contract:** định nghĩa booking.confirmed.v1; trường envelope, payload, thời điểm phát, partition key, duplicate/ordering, retry, DLQ, retention và replay.
4. **Sequence diagram:** có nhánh thành công, slot conflict, request lặp và consumer/provider bị gián đoạn.
5. **Ownership matrix:** chỉ rõ owner của booking data, API schema, event schema, broker ACL, Notification DLQ, projection Analytics, dashboard và on-call.
6. **ADR:** so sánh gửi email trực tiếp sau HTTP request, publish hai lệnh DB+broker và transactional outbox. Chọn phương án có giải thích rủi ro và bằng chứng thử.
7. **Kế hoạch thay đổi:** thêm field vào event rồi thay đổi cách biểu diễn trạng thái, trong khi consumer cũ còn chạy; nêu bước rollout, test và điều kiện deprecate.
8. **Bảng Well-Architected:** nêu ít nhất một rủi ro thuộc mỗi trụ cột, owner và phép thử hoặc bằng chứng giảm rủi ro.

Để tự kiểm tra, điền bảng sau:

| Câu hỏi | Câu trả lời cần có trong tài liệu | Bằng chứng |
|---|---|---|
| Khi nào booking được xác nhận? | Sau commit transaction ở Booking Service | Contract test, concurrency test |
| Timeout có tạo booking trùng không? | Dùng cùng idempotency key, ràng buộc dữ liệu | Replay/concurrency test |
| Ai publish event và khi nào? | Booking Service, sau commit qua outbox | Crash/recovery test |
| Ai có quyền subscribe? | Danh sách consumer được phê duyệt theo ACL | IAM/authorization test |
| Nếu message giao lặp? | Consumer có chính sách idempotency | Duplicate delivery test |
| Nếu Analytics nhận event muộn? | Eventual consistency và reconciliation đã mô tả | Ordering/replay test |
| Nếu consumer bị lỗi 20 phút? | Booking không bị ảnh hưởng; backlog được giám sát | Fault test, queue age, DLQ |
| Ai xử lý từng loại sự cố? | On-call và runbook theo service/broker | Catalog, incident drill |
| Nếu schema đổi phá vỡ? | Có version, thông báo và lộ trình chuyển tiếp | Compatibility test, consumer adoption |

**Tiêu chí hoàn thành:** Một nhóm khác đọc bộ thiết kế phải trả lời được **ai gọi ai, gọi gì, kết quả nào có thể tin cậy, dữ liệu nằm ở đâu, sự kiện thể hiện sự thật nào, lỗi được xử lý ra sao và ai chịu trách nhiệm**. Mọi cam kết về độ trễ, khả dụng hoặc giao nhận cần có cách đo và phép kiểm chứng, không chỉ là nhãn trên sơ đồ.

## 12. Khung ghi nhớ

1. **API contract** mô tả yêu cầu, kết quả, lỗi, xác thực, idempotency và giới hạn vận hành mà caller có thể dựa vào.
2. **Event contract** mô tả một sự thật nghiệp vụ đã xảy ra, payload và bảo đảm giao nhận/thứ tự/replay mà consumer được phép giả định.
3. **Ownership contract** xác định ai sở hữu nghĩa dữ liệu, service, interface, vận hành và thay đổi; Platform vận hành hạ tầng không tự trở thành chủ mọi dữ liệu nghiệp vụ.
4. **Sơ đồ** chỉ hữu ích khi đường giao tiếp và ranh giới có nhãn rõ, liên kết được đến spec, ADR, catalog và test.
5. **Đánh đổi** giữa đồng bộ/bất đồng bộ, payload đầy đủ/tối thiểu, chia sẻ/cách ly và tốc độ thay đổi/độ an toàn phải được ghi nhận và kiểm chứng.

Trong kiến trúc cloud, mạng, compute, dữ liệu, triển khai, độ tin cậy, bảo mật, mở rộng, chi phí và vận hành có quan hệ xuyên suốt. Hợp đồng API/sự kiện và quyền sở hữu là lớp nối **sơ đồ thiết kế** với **hành vi thực tế**: chúng cho biết mỗi thành phần cam kết điều gì, giới hạn đến đâu và ai chịu trách nhiệm duy trì cam kết đó.
