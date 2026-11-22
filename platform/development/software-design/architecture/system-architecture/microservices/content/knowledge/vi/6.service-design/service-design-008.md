# Tài liệu hóa đầu vào, đầu ra và những bảo đảm của dịch vụ

## 1. Mục tiêu của bài học

Trong kiến trúc microservices, một dịch vụ không chỉ là chương trình có endpoint. Nó là một **đơn vị chịu trách nhiệm** cho năng lực nghiệp vụ và công bố cách những thành phần khác có thể tương tác với mình. Khi các nhóm triển khai độc lập, điều giữ hệ thống hoạt động ổn định là **hợp đồng dịch vụ** (*service contract*) có thể hiểu, kiểm thử và tiến hóa an toàn.

Tài liệu dịch vụ cần trả lời ba nhóm câu hỏi:

1. **Đầu vào:** Ai được gọi? Gọi ở đâu? Phải gửi những trường nào, kiểu dữ liệu, phạm vi giá trị, tiền điều kiện và cơ chế xác thực ra sao?
2. **Đầu ra:** Người gọi nhận kết quả nào? Mã trạng thái, schema, lỗi, sự kiện, hiệu ứng nghiệp vụ và thông tin tương quan được biểu diễn thế nào?
3. **Bảo đảm:** Sau khi lời gọi được chấp nhận hoặc hoàn tất, dịch vụ cam kết điều gì về tính đúng đắn, trạng thái, idempotency, nhất quán, thời gian phản hồi, khả dụng và khả năng tương thích?

**Điểm cốt lõi:** người dùng của một dịch vụ phải biết điều gì *được bảo đảm* và điều gì *có thể xảy ra*, kể cả khi mạng mất kết nối hoặc dữ liệu được cập nhật bất đồng bộ. Các bảo đảm cần đủ chính xác để kiểm thử được.

Bài học hướng đến việc tạo một bản mô tả đủ dùng cho thiết kế, triển khai, code review, tích hợp, vận hành và xử lý sự cố. Ví dụ xuyên suốt sử dụng dịch vụ **Inventory Reservation** (giữ trước tồn kho) trong hệ thống bán hàng; tên, thời lượng, mã lỗi và ngưỡng vận hành đều là **giả định minh họa**, không phải mặc định áp dụng cho mọi hệ thống.

## 2. Hợp đồng dịch vụ gồm những lớp nào?

Hợp đồng không chỉ là danh sách URL. Nó gồm các lớp bổ sung cho nhau:

| Lớp hợp đồng | Nội dung cần công bố | Người sử dụng |
|---|---|---|
| Năng lực và trách nhiệm | Dịch vụ sở hữu hành vi, dữ liệu và bất biến nào | Kiến trúc sư, domain expert, đội tích hợp |
| Giao diện đồng bộ | HTTP/gRPC method, path, request, response, mã lỗi | Client, frontend, service tiêu thụ |
| Giao diện bất đồng bộ | Event/command, topic, schema, điều kiện phát và cách giao | Consumer, đội nền tảng |
| Ngữ nghĩa nghiệp vụ | Tiền điều kiện, hậu điều kiện, trạng thái và cách xử lý xung đột | Product Owner, QA, developer |
| Bảo đảm dữ liệu | Atomicity, consistency, idempotency, ordering, độ trễ đồng bộ | Developer, DBA, đội tích hợp |
| Bảo đảm vận hành | SLO, timeout, giới hạn tải, retry, circuit breaking, quota | SRE, đội on-call, client |
| Bảo mật và quyền | Xác thực, phân quyền, tenant isolation, dữ liệu nhạy cảm | Security, platform, consumer |
| Tiến hóa và tương thích | Version, deprecated fields, migration, kiểm thử contract | Các nhóm triển khai độc lập |

Không phải mọi hệ thống đều cần tài liệu dài. Tuy nhiên, các thông tin **có thể làm client hiểu sai hoặc gây mất dữ liệu** phải được ghi rõ: ai là nguồn sự thật, khi nào thao tác được coi là thành công, liệu retry có an toàn và kết quả nào có thể đến trễ.

Một số thuật ngữ cần phân biệt:

- **API specification** mô tả hình dạng giao thức và schema, chẳng hạn OpenAPI cho HTTP và AsyncAPI cho message.
- **Contract nghiệp vụ** mô tả hành vi và bất biến, như “một đơn vị tồn kho không thể được giữ hai lần”.
- **SLO** là mục tiêu chất lượng nội bộ được đo trong một khoảng thời gian; **SLA** là cam kết có tính thỏa thuận với bên sử dụng và có thể kèm chế tài.
- **Runbook** hướng dẫn vận hành, xử lý sự cố và cách phản ứng khi bảo đảm bị đe dọa.

## 3. Bắt đầu bằng thẻ mô tả dịch vụ

Trước khi viết từng endpoint, ghi một trang giới thiệu:

```yaml
service:
  name: inventory-reservation
  purpose: "Giữ tồn kho tạm thời cho đơn hàng trước khi xác nhận"
  owner_team: "Inventory Team"
  business_capability: "Inventory allocation"
  source_of_truth:
    - "reservation records"
    - "available-to-promise quantity"
  does_not_own:
    - "checkout order"
    - "payment transaction"
  public_interfaces:
    http: "/v1/reservations"
    events:
      - "inventory.reservation.created.v1"
      - "inventory.reservation.expired.v1"
  critical_invariant:
    - "Không cấp hai lượt giữ hợp lệ cho cùng một đơn vị tồn kho"
  support:
    runbook: "<đường dẫn runbook>"
    metrics: "<đường dẫn dashboard>"
```

Những đường dẫn trong mẫu là chỗ điền thực tế, không phải endpoint đang tồn tại.

Đặc biệt phải ghi **dịch vụ không sở hữu gì**. Ví dụ, Reservation có thể nhận `orderId` để liên hệ nghiệp vụ nhưng không có quyền tự thay đổi trạng thái Order do Checkout sở hữu. Đó là cách ngăn ranh giới dịch vụ bị xói mòn thành shared database hoặc “mọi service đều có thể sửa mọi dữ liệu”.

## 4. Tài liệu hóa đầu vào

### 4.1. Danh tính thao tác và cách gọi

Mỗi operation nên ghi:

- Tên và mục đích nghiệp vụ; bên nào được phép sử dụng.
- Giao thức, method, URL/topic, version, content type và encoding.
- Xác thực (ví dụ OAuth2 access token hoặc mTLS) và quyền thực hiện.
- Request body, path/query/header, trường bắt buộc hay tùy chọn.
- Kiểu dữ liệu, đơn vị, định dạng, độ dài, phạm vi hợp lệ và giá trị mặc định.
- Quy tắc kiểm tra chéo nhiều trường; yêu cầu trạng thái hiện tại.
- Idempotency key, correlation/request ID và cơ chế truyền context.
- Giới hạn kích thước request, deadline và rate limit nếu áp dụng.

**Ví dụ yêu cầu tạo lượt giữ hàng:**

```http
POST /v1/reservations HTTP/1.1
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: order-8472-line-1

{
  "orderId": "ord_8472",
  "sku": "SKU-RED-42",
  "quantity": 2
}
```

Các giá trị trong ví dụ chỉ mang tính minh họa. Với hệ thống nhiều tenant, tenant phải được xác định từ danh tính được xác thực hoặc cơ chế tin cậy đã thiết kế; không được mặc nhiên tin một `tenantId` do client tùy ý nhập.

### 4.2. Bảng hợp đồng đầu vào

| Trường | Kiểu | Bắt buộc | Ràng buộc | Ý nghĩa |
|---|---|---|---|---|
| `orderId` | string | Có | ID không rỗng, thuộc phạm vi được ủy quyền | Đơn hàng yêu cầu giữ tồn kho |
| `sku` | string | Có | SKU đang được hỗ trợ | Loại hàng cần giữ |
| `quantity` | integer | Có | 1–100 trong ví dụ | Số lượng đơn vị |
| `Authorization` | header | Có | Bearer token hợp lệ với scope thích hợp | Danh tính/quyền caller |
| `Idempotency-Key` | header | Có | Không rỗng, duy nhất theo caller và thao tác trong cửa sổ lưu trữ | Nhận diện thao tác logic khi retry |
| `X-Correlation-Id` | header | Không | Nếu có phải đúng định dạng cho phép | Truy vết qua dịch vụ |

Các ngưỡng như 1–100 chỉ nên xuất hiện khi có quyết định nghiệp vụ và được thực thi đồng nhất. Nếu tài liệu nói “số lượng dương” nhưng server chấp nhận 0 hoặc số âm, hợp đồng mất giá trị.

### 4.3. Tiền điều kiện (preconditions)

Các trường hợp phải thỏa trước khi thao tác có hiệu lực:

1. Caller được xác thực và có quyền giữ tồn kho cho đơn hàng đó.
2. SKU tồn tại, đang cho phép giữ hàng và số lượng hợp lệ.
3. Yêu cầu chưa vi phạm hạn mức nghiệp vụ và chính sách chống lạm dụng.
4. Dịch vụ có thẩm quyền xác định tồn kho có thể giữ.
5. Idempotency key không được dùng cho **nội dung khác** trong cùng phạm vi khóa.

Phân biệt **kiểm tra cú pháp** với **điều kiện nghiệp vụ**. `quantity = -3` là đầu vào không hợp lệ; `quantity = 3` nhưng chỉ còn hai món là xung đột nghiệp vụ. Hai trường hợp có thể cần mã lỗi và hành động client khác nhau.

## 5. Tài liệu hóa đầu ra

### 5.1. Kết quả thành công

Với ví dụ này, `201 Created` có ý nghĩa: **bản ghi giữ hàng đã được tạo và cam kết trong nguồn dữ liệu chính của Reservation**. Nếu thao tác chỉ đưa việc xử lý vào hàng đợi mà chưa cấp giữ hàng, nên dùng ngữ nghĩa như `202 Accepted` và cung cấp cơ chế kiểm tra trạng thái; không tuyên bố “đã giữ thành công” khi mới nhận yêu cầu.

```http
HTTP/1.1 201 Created
Location: /v1/reservations/rsv_9c41
Content-Type: application/json

{
  "reservationId": "rsv_9c41",
  "orderId": "ord_8472",
  "sku": "SKU-RED-42",
  "quantity": 2,
  "status": "ACTIVE",
  "createdAt": "2026-11-11T08:00:00Z",
  "expiresAt": "2026-11-11T08:15:00Z"
}
```

Tài liệu phải nói rõ ý nghĩa từng trường:

| Trường đầu ra | Ý nghĩa và bảo đảm |
|---|---|
| `reservationId` | Định danh lượt giữ; ổn định trong vòng đời bản ghi |
| `orderId` | Đơn liên quan; không khẳng định Order đã thanh toán |
| `sku`, `quantity` | Nội dung giữ được chấp thuận |
| `status` | Trạng thái nghiệp vụ theo mô hình công bố |
| `createdAt` | Thời điểm dịch vụ ghi nhận lượt giữ |
| `expiresAt` | Thời điểm hết hiệu lực theo đồng hồ phía server; dùng UTC ISO 8601 |
| `Location` | Địa chỉ truy vấn trạng thái chính thức |

Mỗi trường cần xác định có thể null không, có thể thay đổi trong tương lai không, đơn vị/thời gian/múi giờ gì, và có phải thông tin nhạy cảm không. **Response schema đúng cú pháp không đủ** nếu client chưa biết trạng thái nào là cuối cùng.

### 5.2. Trạng thái và chuyển trạng thái

Ví dụ vòng đời:

```text
        POST /reservations
               |
               v
             ACTIVE
           /    |    \
   confirm      |      release
        v       |          v
     CONFIRMED  |       RELEASED
                |
            hết hạn
                v
             EXPIRED
```

Một tài liệu rõ ràng phải phân biệt thao tác nào nằm trong API hiện tại với thao tác nào là workflow ở nội bộ hoặc API khác. Nếu chỉ công bố `POST` và `GET`, không nên khiến client tưởng rằng `confirm` hoặc `release` đã có endpoint công khai.

Ví dụ bảo đảm hết hạn: sau `expiresAt`, hệ thống từ chối mọi nỗ lực xác nhận lượt giữ ngay cả khi job dọn dẹp bản ghi chưa chạy. Việc cập nhật trạng thái hiển thị `EXPIRED` có thể diễn ra bất đồng bộ nếu hợp đồng quy định như vậy. Cần nêu rõ trạng thái nào có thể quan sát được sau hạn và cơ chế đọc trạng thái hiệu lực.

### 5.3. Lỗi được máy và người hiểu

Thiết kế một **error envelope** thống nhất:

```json
{
  "code": "STOCK_NOT_AVAILABLE",
  "message": "Không đủ tồn kho khả dụng để giữ số lượng yêu cầu",
  "correlationId": "req_ab12",
  "retryable": false
}
```

Không nên dựa vào chuỗi `message` để phân nhánh logic client; `code` mới là giá trị ổn định được tài liệu hóa. `correlationId` giúp hỗ trợ truy vết nhưng không tiết lộ token hay dữ liệu nhạy cảm.

| HTTP status | Mã lỗi ví dụ | Nguyên nhân | Hành động client |
|---|---|---|---|
| 400 | `MALFORMED_REQUEST` | JSON không phân tích được | Sửa cấu trúc request |
| 401 | `UNAUTHENTICATED` | Thiếu hoặc sai thông tin xác thực | Xin token hợp lệ |
| 403 | `FORBIDDEN` | Không đủ quyền thực hiện | Không retry y nguyên |
| 404 | `SKU_NOT_FOUND` | SKU không tồn tại/không truy cập được | Kiểm tra SKU theo quyền |
| 409 | `STOCK_NOT_AVAILABLE` | Không đáp ứng lượng giữ yêu cầu | Thay số lượng hoặc thông báo hết hàng |
| 409 | `IDEMPOTENCY_KEY_REUSED` | Dùng cùng key với payload khác | Không tái sử dụng key cho yêu cầu khác |
| 422 | `INVALID_QUANTITY` | Số lượng ngoài quy tắc nghiệp vụ | Sửa trường đầu vào |
| 429 | `RATE_LIMITED` | Vượt hạn mức được công bố | Chờ theo `Retry-After` nếu được cung cấp |
| 500 | `INTERNAL_ERROR` | Lỗi ngoài dự kiến | Có thể tra trạng thái trước khi retry |
| 503 | `SERVICE_UNAVAILABLE` | Service không thể phục vụ tạm thời | Backoff, giới hạn retry, kiểm tra trạng thái |

Mã HTTP và error code là ví dụ thiết kế, cần thống nhất với tiêu chuẩn API thực tế. Không trả stack trace, SQL hay bí mật hệ thống cho caller. Hạn chế leak sự tồn tại của dữ liệu khác tenant khi phân biệt 403 và 404.

## 6. Tài liệu hóa những bảo đảm nghiệp vụ

Phần này trả lời câu hỏi khó nhất: **người tiêu thụ có thể tin điều gì sau mỗi kết quả quan sát được?**

### 6.1. Tiền điều kiện, hậu điều kiện và bất biến

- **Tiền điều kiện:** request hợp lệ, caller có quyền, tồn kho khả dụng đủ.
- **Hậu điều kiện khi thành công:** tồn tại một reservation `ACTIVE` với đúng SKU và số lượng yêu cầu; số lượng có thể cấp tiếp đã giảm tương ứng theo nguồn dữ liệu có thẩm quyền.
- **Bất biến:** tổng lượng đã bán/giữ còn hiệu lực không vượt quá tồn kho có thể phân bổ trong phạm vi định nghĩa của dịch vụ.
- **Khi thất bại nghiệp vụ:** nếu trả lỗi `STOCK_NOT_AVAILABLE` trước khi cấp giữ, không tạo reservation có hiệu lực cho yêu cầu này.

Đây là **ví dụ về hợp đồng mong muốn**, không phải suy luận tự động từ endpoint. Bất biến cần được bảo vệ bằng transaction, optimistic locking, điều kiện cập nhật atomic hoặc cơ chế tương đương phù hợp với kho dữ liệu.

Ghi rõ giới hạn bảo đảm: nếu các hệ thống khác vẫn có thể sửa trực tiếp cùng bản ghi tồn kho mà bỏ qua Reservation, dịch vụ **không thể một mình** bảo đảm không bán vượt. Quyền sở hữu ghi dữ liệu là một phần của hợp đồng kiến trúc.

### 6.2. Atomicity và phạm vi giao dịch

Nêu việc nào là cùng một thao tác atomic, việc nào xảy ra sau:

```text
Bên trong Reservation:
  kiểm tra + cấp lượng giữ + ghi bản ghi reservation
  → cùng ranh giới nhất quán của nguồn dữ liệu có thẩm quyền

Bên ngoài Reservation:
  cập nhật Order, gửi email, đồng bộ hệ thống khác
  → có thể diễn ra sau qua API/event
```

Không hứa một giao dịch ACID xuyên các microservices khi thiết kế chỉ có local transaction và event bất đồng bộ. Nếu yêu cầu workflow nhiều bước, tài liệu hóa trạng thái trung gian, cơ chế xử lý lỗi, bù trừ và điểm kết thúc.

### 6.3. Nhất quán khi đọc

Những câu cần trả lời:

- Sau `201`, gọi `GET /v1/reservations/{id}` có thấy dữ liệu ngay không?
- API `GET` đọc nguồn chính, replica hay projection?
- Dashboard tồn kho, tìm kiếm hoặc báo cáo có được cập nhật ngay không?
- Nếu có delay, contract cam kết cửa sổ trễ hay chỉ công bố rằng dữ liệu có thể trễ?

Ví dụ:

> `GET /v1/reservations/{id}` là điểm đọc trạng thái có thẩm quyền và phản ánh lượt giữ đã được commit. Các màn hình tổng hợp tồn kho nhận dữ liệu từ event có thể cập nhật sau, không dùng chúng để quyết định có thể giữ thêm hàng.

Nếu không có số liệu hay cơ chế đủ mạnh để bảo đảm cập nhật trong 1 giây, **đừng** viết “eventual consistency tối đa 1 giây”. Hãy ghi mức có thể kiểm chứng hoặc công bố giới hạn hiện tại.

## 7. Idempotency, retry và timeout

Mạng phân tán làm nảy sinh một tình huống quan trọng: client gửi `POST`, server thực hiện thành công, nhưng response bị mất vì timeout. Client **không biết thao tác đã hoàn tất hay chưa**. Nếu gửi lại với một key mới hoặc không có idempotency, có thể giữ tồn kho hai lần.

### 7.1. Hợp đồng idempotency rõ ràng

Ví dụ chính sách minh họa:

1. Client cung cấp `Idempotency-Key` cho mỗi thao tác logic.
2. Scope của key là `caller + operation + key`; server lưu fingerprint của payload chuẩn hóa.
3. Trong **24 giờ** kể từ lần nhận đầu, request lặp lại với cùng key và cùng payload không được tạo thêm reservation mới.
4. Khi thao tác đầu tiên đã hoàn tất, lời gọi lại nhận kết quả tương ứng với thao tác đó; trong lúc xử lý song song, server có thể trả một trạng thái “đang xử lý” được mô tả rõ.
5. Cùng key nhưng payload khác bị từ chối `409 IDEMPOTENCY_KEY_REUSED`.
6. Sau cửa sổ 24 giờ, server có thể không còn nhớ key; client **không được** coi retry sau hạn là an toàn nếu không kiểm tra trạng thái nghiệp vụ.

Nếu API có thể trả `201` ban đầu và kết quả cache sau retry là `200`, tài liệu phải nêu chính xác. Không cần hứa lặp lại byte-for-byte mọi header nếu hệ thống chỉ bảo đảm **cùng hiệu ứng nghiệp vụ**.

### 7.2. Retry có kiểm soát

Nêu rõ những lỗi nào có thể retry, với idempotency key và exponential backoff có jitter; giới hạn số lần retry/deadline để tránh tạo bão tải. Không retry vô hạn lỗi `400`, `403`, `422` hoặc lỗi nghiệp vụ không đủ tồn kho. `429` có thể kèm `Retry-After`; `503` có thể thử lại có giới hạn.

Timeout không tự chứng minh thất bại. Khi không chắc kết quả, client có thể:

- Dùng lại **cùng idempotency key** trong cửa sổ bảo đảm.
- Truy vấn `GET` bằng reservation ID nếu đã nhận ID.
- Truy vấn operation status/lookup theo idempotency key nếu API công bố khả năng này.
- Escalate sang reconciliation nếu không thể xác minh kết quả.

Không tuyên bố “exactly once delivery” cho HTTP/message thông thường; nên mô tả **at-least-once delivery có thể lặp** và **effectively-once business effect** nếu đã triển khai idempotency đúng.

## 8. Hợp đồng sự kiện bất đồng bộ

Một microservice có thể trả response đồng bộ và phát sự kiện. Hai giao diện này cần tài liệu riêng.

Ví dụ sau khi tạo reservation thành công, dịch vụ phát:

```json
{
  "eventId": "evt_35ea",
  "eventType": "inventory.reservation.created.v1",
  "occurredAt": "2026-11-11T08:00:00Z",
  "aggregateId": "rsv_9c41",
  "aggregateVersion": 1,
  "correlationId": "req_ab12",
  "payload": {
    "reservationId": "rsv_9c41",
    "orderId": "ord_8472",
    "sku": "SKU-RED-42",
    "quantity": 2,
    "expiresAt": "2026-11-11T08:15:00Z"
  }
}
```

**Bảng cần công bố cho mỗi event:**

| Thuộc tính | Ví dụ | Cần bảo đảm gì |
|---|---|---|
| Tên + phiên bản | `inventory.reservation.created.v1` | Ý nghĩa của sự kiện và schema ổn định trong phiên bản |
| Thời điểm phát | Sau khi dữ liệu Reservation được commit | Consumer không nhận “created” cho bản ghi chưa thành công |
| Schema | Các trường JSON ở trên | Required/optional, format, nullability |
| Delivery | Ít nhất một lần trong phạm vi broker/producer được cấu hình | Có thể có duplicate, consumer phải idempotent |
| Ordering | Chỉ cam kết thứ tự theo reservation nếu hạ tầng và partition key hỗ trợ | Không suy ra thứ tự toàn bộ topic |
| Retention/replay | Cấu hình và giới hạn thực tế | Consumer biết cửa sổ replay/dedup |
| Failure recovery | Retry, dead-letter, cách reprocess | Khi nào phải can thiệp thủ công |
| Dữ liệu nhạy cảm | Tối thiểu thông tin cần thiết | Không phát token hoặc dữ liệu khách hàng không cần thiết |

Với mô hình **transactional outbox**, việc ghi bản ghi reservation và outbox event trong cùng transaction có thể loại bỏ tình huống dữ liệu đã commit nhưng ý định phát event bị mất tại bước ghi outbox. Tuy nhiên outbox vẫn có thể phát **trùng** khi relay retry; consumer phải khử trùng lặp bằng `eventId` hoặc khóa nghiệp vụ thích hợp. Outbox cũng không tự đảm bảo event tới consumer trong một thời hạn cố định nếu không có giám sát và giới hạn vận hành bổ sung.

Tài liệu hóa **command** (yêu cầu làm việc gì) khác với **event** (sự kiện đã xảy ra). Ví dụ, `ReserveInventory` là yêu cầu, còn `InventoryReserved` phản ánh kết quả đã được chấp nhận theo ngữ nghĩa của producer. Consumer không nên coi event như lệnh phải sửa trực tiếp dữ liệu của producer.

Với các kênh message, dùng AsyncAPI hoặc định dạng schema registry tương thích để mô tả payload, topic/channel và version. Schema chỉ bảo vệ hình dạng dữ liệu; phần văn bản vẫn cần nói rõ delivery, ordering và consistency.

## 9. Ví dụ phác thảo OpenAPI

Một mô tả OpenAPI cho phép kiểm tra và sinh client, nhưng phải đi kèm mô tả nghiệp vụ. Đoạn YAML dưới đây minh họa các trường cốt lõi của một thao tác; các response khác được liệt kê ở bảng lỗi phía trên.

```yaml
openapi: 3.1.0
info:
  title: Inventory Reservation API
  version: 1.0.0
paths:
  /v1/reservations:
    post:
      summary: Tạo một lượt giữ tồn kho
      description: >
        Khi trả 201, reservation đã được commit trong nguồn dữ liệu
        có thẩm quyền. Dùng cùng Idempotency-Key khi retry.
      operationId: createReservation
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
              $ref: '#/components/schemas/CreateReservation'
      responses:
        '201':
          description: Reservation đã được tạo
          headers:
            Location:
              schema:
                type: string
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Reservation'
        '409':
          description: Xung đột tồn kho hoặc khóa idempotency
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Error'
        '422':
          description: Đầu vào vi phạm quy tắc nghiệp vụ
        '503':
          description: Dịch vụ tạm thời không thể phục vụ
  /v1/reservations/{reservationId}:
    get:
      summary: Đọc trạng thái lượt giữ có thẩm quyền
      security:
        - bearerAuth: []
      parameters:
        - in: path
          name: reservationId
          required: true
          schema:
            type: string
      responses:
        '200':
          description: Tìm thấy lượt giữ
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Reservation'
        '404':
          description: Không tìm thấy hoặc không được phép tiết lộ
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
  schemas:
    CreateReservation:
      type: object
      required: [orderId, sku, quantity]
      additionalProperties: false
      properties:
        orderId:
          type: string
          minLength: 1
        sku:
          type: string
          minLength: 1
        quantity:
          type: integer
          minimum: 1
          maximum: 100
    Reservation:
      type: object
      required: [reservationId, orderId, sku, quantity, status, createdAt, expiresAt]
      properties:
        reservationId: {type: string}
        orderId: {type: string}
        sku: {type: string}
        quantity: {type: integer}
        status:
          type: string
          enum: [ACTIVE, CONFIRMED, RELEASED, EXPIRED]
        createdAt: {type: string, format: date-time}
        expiresAt: {type: string, format: date-time}
    Error:
      type: object
      required: [code, message, correlationId]
      properties:
        code: {type: string}
        message: {type: string}
        correlationId: {type: string}
        retryable: {type: boolean}
```

Ví dụ trên thể hiện **một phần hợp đồng**, không phải đặc tả đầy đủ mọi lỗi, quota, timeout và lược đồ sự kiện. Khi dùng thật, cần hoàn thiện tất cả response, security scope, ví dụ và mô tả hành vi, rồi kiểm tra spec bằng công cụ OpenAPI. Trong YAML cần dùng dấu nháy khi các key là mã HTTP.

## 10. Bảo đảm về thời gian và vận hành

Đầu vào/đầu ra đúng schema nhưng response luôn chậm hoặc service thường xuyên lỗi vẫn khiến consumer không thể lập kế hoạch. Vì vậy ghi rõ các cam kết về chất lượng hoạt động.

### 10.1. SLI, SLO và SLA

- **SLI (Service Level Indicator):** phép đo như tỷ lệ request hợp lệ có kết quả thành công, p95 latency hoặc thời gian phát event.
- **SLO (Service Level Objective):** mục tiêu nội bộ cho một SLI trong một cửa sổ.
- **SLA (Service Level Agreement):** cam kết theo thỏa thuận đối với bên sử dụng, có thể kèm điều khoản hỗ trợ/chế tài.

Ví dụ giả định:

| Chỉ số | Mục tiêu minh họa | Phải ghi rõ |
|---|---|---|
| Availability | 99,9% request hợp lệ được phục vụ trong 30 ngày | Cách tính “good request”, loại bỏ lỗi client thế nào |
| API latency | p95 của `POST /v1/reservations` dưới 300 ms | Phạm vi tải và điểm đo |
| Event propagation | p99 trong 5 giây khi broker khỏe | Bắt đầu/kết thúc tính từ đâu; ứng xử khi backlog |
| Error budget | Phần số request lỗi cho phép theo SLO | Cửa sổ, exclusions và cách cảnh báo |
| Rate limit | Ví dụ 100 request/giây mỗi client | Burst, throttling, `429` và `Retry-After` |

Các số trên là mục tiêu **giả định** để minh họa mẫu tài liệu, không phải chuẩn khuyến nghị. Một SLO chỉ có ý nghĩa khi đo được; không được ghi là “bảo đảm” nếu hệ thống chưa có cơ chế đáp ứng.

### 10.2. Timeout và deadline

Ví dụ: server có deadline xử lý tối đa 2 giây, nhưng client có thể đặt timeout 800 ms. Khi client timeout, xử lý phía server **có thể đã hoàn tất**. Vì thế hợp đồng idempotency và truy vấn trạng thái là điều kiện quan trọng của các thao tác có tác dụng phụ.

Để tránh retry storm, công bố:

- Timeout và deadline khuyến nghị theo từng API.
- Thực hành exponential backoff có jitter và số retry tối đa.
- Cách server biểu diễn overload và rate limiting.
- Cách client kiểm tra kết quả chưa rõ sau timeout.
- Tiêu chí circuit breaker, queue/backpressure nếu phù hợp.

### 10.3. Phạm vi chịu lỗi

Không viết chung chung “hệ thống luôn khả dụng”. Nên xác định:

- Nếu provider Payment không hoạt động, Reservation có còn nhận request không?
- Nếu event broker chậm, thao tác REST đã commit có còn trả thành công không?
- Một vùng/cluster không khả dụng thì failover ra sao, có mất dữ liệu hay duplicate không?
- Có cơ chế degrade nào hợp lệ và client nhận biết bằng cách nào?

Các câu trả lời ảnh hưởng cách tích hợp và cần được đối chiếu với kiểm thử lỗi thực tế.

## 11. Bảo mật và phân quyền là một phần hợp đồng

Tài liệu hóa tối thiểu:

1. **Danh tính caller:** token type, OAuth2 scope, mTLS identity hoặc cơ chế đã chọn.
2. **Quyền nghiệp vụ:** caller có được giữ SKU/đơn hàng này hay không.
3. **Tenant isolation:** không thể đọc reservation của tenant khác dù đoán được ID.
4. **Dữ liệu nhạy cảm:** trường nào chứa PII/bí mật, được log và phát qua event đến đâu, thời hạn lưu giữ.
5. **Truyền dữ liệu:** TLS, cơ chế quản lý secret, không đưa credential vào URL hoặc error message.
6. **Audit:** ai thực hiện, thời điểm, kết quả, correlationId và mục đích; kiểm soát quyền xem audit log.

Đặc biệt, tài liệu phải mô tả sự khác nhau giữa **xác thực** và **ủy quyền**. Một token hợp lệ không tự cho phép thay đổi mọi reservation. Đừng để client suy luận quyền từ việc gọi được endpoint.

## 12. Hợp đồng và cấu trúc nội bộ không giống nhau

Một dịch vụ có thể dùng Java Spring Boot, PostgreSQL, Redis và Kafka, nhưng những chi tiết đó không nhất thiết là một phần của public contract. Consumer cần biết **ý nghĩa ổn định** của API và event, chứ không cần phụ thuộc vào entity JPA, tên bảng hay class domain nội bộ.

Ví dụ mã Java minh họa ranh giới API:

```java
public record CreateReservationRequest(
    String orderId,
    String sku,
    int quantity
) {}

public record ReservationResponse(
    String reservationId,
    String orderId,
    String sku,
    int quantity,
    String status,
    Instant createdAt,
    Instant expiresAt
) {}
```

DTO phục vụ API có thể tách với persistence entity và domain aggregate để tránh việc sửa column/database vô tình trở thành thay đổi hợp đồng. Những bảo đảm như uniqueness, idempotency hay không bán vượt phải được thực thi trong tầng phù hợp, không thể chỉ dựa vào annotation validation trên DTO.

Mẫu Java trên chưa xử lý validation, authentication hoặc mapping đầy đủ; nó chỉ minh họa nơi định nghĩa contract dữ liệu.

## 13. Kiểm thử những bảo đảm đã công bố

Tài liệu có giá trị khi các bảo đảm quan trọng có bằng chứng kiểm thử.

| Bảo đảm | Kiểm thử đề xuất | Bằng chứng cần lưu |
|---|---|---|
| Schema đầu vào/đầu ra | Schema validation và contract tests | Request/response mẫu, kết quả chạy CI |
| Validation | Boundary tests: missing field, null, số âm, vượt max | Mã lỗi ổn định |
| Phân quyền | Tenant A không truy cập reservation tenant B | 403/404 theo chính sách, không lộ dữ liệu |
| Không bán vượt | Nhiều request song song trên tồn kho giới hạn | Tổng giữ thành công không vượt available |
| Idempotency | Retry cùng key/payload, đồng thời; key trùng payload khác | Một hiệu ứng nghiệp vụ, lỗi nhất quán |
| Timeout không rõ kết quả | Server commit rồi giả lập mất response | Client xác minh được, không double reserve |
| Event contract | Producer/consumer schema compatibility | Schema version, contract CI |
| Delivery trùng | Gửi cùng event hai lần | Consumer không tạo hiệu ứng phụ hai lần |
| Thứ tự nếu có cam kết | Trộn/replay event theo aggregate version | Xử lý được reorder hoặc từ chối dữ liệu cũ |
| Tương thích phiên bản | Client cũ chạy với provider mới | Contract tests và kiểm tra backward compatibility |
| SLO | Load test + số liệu production theo cửa sổ | Dashboard latency/availability/error budget |

Khi dùng consumer-driven contract tests, cần phân biệt kiểm thử **giao diện** và kiểm thử **hành vi**. Một provider có thể trả đúng JSON nhưng vẫn làm sai nghiệp vụ dưới cạnh tranh cập nhật. Do đó, invariant và integration test luôn có vị trí riêng.

### Ví dụ tình huống cạnh tranh

Giả sử còn đúng 1 đơn vị SKU. Hai client gửi yêu cầu giữ cùng lúc, mỗi yêu cầu số lượng 1 với idempotency key khác nhau. Kết quả hợp lệ là **tối đa một** lượt giữ thành công nếu không có bổ sung tồn kho đồng thời. Hệ thống không được trả hai phản hồi thành công rồi mới “sửa lại” số lượng bằng cách âm thầm hủy một lượt giữ, trừ khi contract nghiệp vụ đã mô tả rõ mô hình đặt chỗ tạm khác.

Đây là kiểm thử hành vi chứng minh bảo đảm quan trọng hơn việc chỉ so khớp response schema.

## 14. Tiến hóa hợp đồng để các nhóm triển khai độc lập

Một service thường thay đổi qua nhiều phiên bản. Mọi thay đổi cần được phân loại và thông báo dựa trên tác động tới consumer.

**Thay đổi thường có thể tương thích ngược**, tùy chính sách consumer:

- Thêm trường response không bắt buộc, khi client bỏ qua field không biết.
- Thêm endpoint mới không ảnh hưởng endpoint cũ.
- Thêm giá trị optional trong request với default bảo toàn hành vi cũ.
- Tối ưu nội bộ nhưng giữ ngữ nghĩa và SLO như đã công bố.

**Thay đổi có thể phá vỡ tương thích:**

- Đổi kiểu dữ liệu, đổi tên/bỏ trường required.
- Biến optional thành required.
- Đổi ý nghĩa của `status`, `quantity` hoặc mã lỗi.
- Siết validation khiến request cũ từng hợp lệ bị từ chối.
- Thêm giá trị enum mà consumer cũ không xử lý được (nếu enum được coi đóng).
- Đổi cơ chế idempotency, thời gian giữ hoặc ngữ nghĩa `201`.
- Đổi thứ tự/delivery guarantee của event khi consumer phụ thuộc vào nó.

Không thể mặc định “thêm enum là backward compatible”; tài liệu phải quy định consumer có chịu được giá trị mới hay không. Tránh dùng cùng tên event và version để thay đổi ngữ nghĩa cốt lõi.

### Quy trình thay đổi hợp đồng

1. Xác định consumer đang dùng operation/event nào, có thể thông qua catalog, telemetry hoặc trao đổi với nhóm sở hữu.
2. Phân loại sự thay đổi: thêm tương thích, cần điều phối hay breaking.
3. Cập nhật OpenAPI/AsyncAPI, schema registry, tài liệu ngữ nghĩa và ví dụ.
4. Chạy provider/consumer contract tests và các kiểm thử bất biến.
5. Với breaking change, công bố phiên bản mới, thời gian chuyển đổi và chính sách deprecation.
6. Cho phép chạy song song phiên bản cũ/mới trong cửa sổ cần thiết; theo dõi mức sử dụng trước khi ngừng bản cũ.
7. Ghi lại ngày áp dụng, người sở hữu quyết định và đường rollback phù hợp.

Không buộc mọi thay đổi của nhiều service triển khai đồng thời nếu có thể dùng cơ chế **expand → migrate → contract** an toàn cho schema/API.

## 15. Mẫu tài liệu hợp đồng dịch vụ có thể tái sử dụng

```markdown
# <Tên dịch vụ> – Service Contract

## A. Mục đích và trách nhiệm
- Năng lực nghiệp vụ:
- Đội sở hữu / liên hệ hỗ trợ:
- Dữ liệu sở hữu và nguồn sự thật:
- Năng lực/dữ liệu không thuộc trách nhiệm:
- Bất biến nghiệp vụ quan trọng:

## B. Các giao diện
| Operation/Event | Protocol/Channel | Version | Consumer chính | Mục đích |

## C. Đầu vào cho từng operation
- Method, path hoặc topic:
- AuthN/AuthZ và tenant scope:
- Headers, path/query, content type:
- Body/schema, required, nullability, range, units:
- Validation liên trường và preconditions:
- Idempotency key và phạm vi:
- Ví dụ request hợp lệ/không hợp lệ:

## D. Đầu ra
- Mã thành công và ý nghĩa đã hoàn tất/được nhận:
- Response schema và ví dụ:
- Trạng thái và vòng đời:
- Error status/code/retryability:
- Correlation/request ID:

## E. Bảo đảm
- Hậu điều kiện thành công/thất bại:
- Bất biến và ranh giới transaction:
- Nguồn dữ liệu có thẩm quyền:
- Read-after-write/eventual consistency:
- Idempotency, duplicate, ordering:
- Deadline/timeout và xử lý kết quả không xác định:

## F. Bất đồng bộ
- Event/command và điều kiện phát:
- Schema/version/partition key:
- Delivery, retry, dead-letter, retention:
- Replay/dedup/ordering:
- Consumer cần xử lý trạng thái trung gian:

## G. Vận hành và bảo mật
- SLI/SLO/SLA, phạm vi đo:
- Rate limit, quotas, max payload:
- Auth, tenant isolation, PII và audit:
- Runbook, dashboard, alerts, on-call:

## H. Tiến hóa và xác minh
- Chiến lược version và deprecation:
- Contract/invariant/integration tests:
- Ví dụ tương thích, edge cases:
- Ngày cập nhật và chủ sở hữu:
```

Mẫu này nên được lưu cạnh spec hoặc trong service catalog để các nhóm dễ tìm. Điều quan trọng là cập nhật tài liệu **cùng pull request thay đổi hành vi**, không để spec và implementation phát triển thành hai nguồn sự thật mâu thuẫn.

## 16. Checklist trước khi công bố một dịch vụ

- [ ] Mục đích, ranh giới sở hữu, nguồn dữ liệu có thẩm quyền và các bất biến được mô tả.
- [ ] Mỗi operation có method/path/topic, version và điều kiện truy cập rõ.
- [ ] Input có schema, required/optional, kiểu dữ liệu, đơn vị và validation.
- [ ] Thành công có trạng thái, schema, ví dụ và hậu điều kiện nghiệp vụ.
- [ ] Lỗi có status, code ổn định và chỉ dẫn retry/truy vấn trạng thái.
- [ ] Có quy tắc idempotency và cách xử lý timeout chưa rõ kết quả.
- [ ] Đã công bố phạm vi transaction, nhất quán khi đọc và giới hạn đồng bộ dữ liệu.
- [ ] Event có điều kiện phát, schema, delivery, ordering, retry và dedup.
- [ ] SLO, deadline, quota và cách đo được ghi rõ khi cần cam kết vận hành.
- [ ] Đã xác định AuthN/AuthZ, tenant isolation, dữ liệu nhạy cảm và audit.
- [ ] Có versioning, compatibility policy và kế hoạch deprecation.
- [ ] Có contract tests và kiểm thử bất biến dưới concurrency/thất bại.

## 17. Bài tập thực hành

Bạn được giao xây dựng **Payment Authorization Service** nhận yêu cầu ủy quyền thanh toán từ Checkout. Hãy viết hợp đồng mà một nhóm Checkout có thể dùng mà không cần đọc code Payment:

1. Xác định **ba đầu vào bắt buộc**, ràng buộc và tiền điều kiện (bao gồm đơn vị tiền tệ, số tiền và idempotency key).
2. Thiết kế response cho ba tình huống: **ủy quyền thành công**, **bị từ chối bởi nhà cung cấp**, **đã nhận nhưng kết quả chưa xác định**.
3. Nêu hậu điều kiện chính xác sau mỗi kết quả; phân biệt rõ giữa **đã nhận request** và **đã ủy quyền**.
4. Thiết kế bảng lỗi: trường hợp nào retry được? Làm sao tránh charge/authorize trùng sau timeout?
5. Chọn một event công khai, nêu schema, delivery, duplicate và ordering guarantee.
6. Viết hai kiểm thử contract, hai kiểm thử bất biến nghiệp vụ và một kiểm thử lỗi mạng.
7. Nêu một thay đổi breaking và kế hoạch nâng phiên bản để Checkout không phải deploy lockstep.

Gợi ý: trường `status = PENDING` có thể cần đường truy vấn trạng thái; không được suy ra kết quả cuối từ một HTTP `202 Accepted`. Giải pháp tốt phải giúp client biết khi nào có thể tiếp tục workflow và khi nào phải đối soát.

## 18. Ghi nhớ

Tài liệu hóa dịch vụ là công bố **đầu vào nào được chấp nhận, đầu ra nào có nghĩa gì và những điều gì được bảo đảm khi hệ thống hoạt động bình thường hoặc gặp lỗi**. Một bản OpenAPI đúng cú pháp chỉ là điểm khởi đầu. Hợp đồng đáng tin cậy còn cần mô tả bất biến, quyền sở hữu dữ liệu, atomicity, consistency, retry/idempotency, event delivery, giới hạn thời gian, bảo mật và chính sách tương thích. Khi các bảo đảm này đủ rõ và được kiểm thử, các nhóm mới có cơ sở để triển khai độc lập mà không phải dựa vào suy đoán.
