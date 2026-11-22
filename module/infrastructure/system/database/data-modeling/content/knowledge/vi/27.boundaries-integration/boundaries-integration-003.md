# Hợp đồng API hoặc sự kiện như phép chiếu có mục đích

## Mục tiêu học tập

Trong học phần **DATABASE_DATA_MODELING**, chúng ta rèn kỹ năng biến yêu cầu nghiệp vụ thành mô hình dữ liệu rõ ràng, từ thực thể, quan hệ và ràng buộc đến lược đồ vật lý. Nhưng khi dữ liệu vượt qua **ranh giới của một hệ thống hoặc một miền nghiệp vụ**, câu hỏi quan trọng không còn là “có thể xuất bao nhiêu cột?” mà là: **bên tiêu thụ thực sự cần biết điều gì, để làm việc gì, với cam kết ngữ nghĩa và thời gian ra sao?**

Một **hợp đồng API** hoặc **hợp đồng sự kiện** (*event contract*) có thể xem là **phép chiếu có mục đích** (*purposeful projection*) của sự thật nghiệp vụ. Nó chỉ lựa chọn những thông tin cần thiết, có thể đổi tên, chuẩn hóa kiểu, tổng hợp, ẩn trường, xác định thời điểm và ràng buộc khả năng tiến hóa. Nó **không phải bản sao vô điều kiện của entity, bảng hay document nội bộ**.

Sau bài này, bạn có thể:

1. Phân biệt **mô hình nội bộ**, **API query**, **integration event** và **read model**.
2. Thiết kế phép chiếu theo **mục đích, người tiêu thụ, chủ sở hữu, grain, thời gian và quyền truy cập**.
3. Công bố định danh, trạng thái, thời gian và tiền với ngữ nghĩa đủ rõ để kiểm chứng.
4. Giải thích vì sao API trả **trạng thái hiện hành**, còn event thường công bố **sự việc đã xảy ra**.
5. Chọn cách quản lý tương thích, versioning, idempotency, thứ tự, outbox và replay.
6. Viết OpenAPI/JSON Schema, SQL ánh xạ và các phép thử hợp đồng/bảo mật.
7. Giảm sự phụ thuộc giữa các nhóm khi đổi lược đồ quan hệ, document, đồ thị và hệ phân tích.

## 1. “Phép chiếu có mục đích” nghĩa là gì?

Trong đại số quan hệ, phép chiếu \(\pi_A(R)\) chọn các thuộc tính \(A\) của quan hệ \(R\). Phép chiếu ở **ranh giới tích hợp** còn rộng hơn: nó có thể **JOIN, tính toán, lọc theo quyền, chuyển đổi tên và kiểu, ánh xạ trạng thái, chọn phiên bản lịch sử**.

~~~text
Mô hình nội bộ (nguồn chân lý)
   ├── Bảng/document, khóa, phụ thuộc và ràng buộc
   ├── Lịch sử trạng thái, metadata kỹ thuật
   └── Những trường nhạy cảm hoặc chỉ dùng nội bộ
                  |
                  | Lọc theo mục đích và quyền
                  | Chọn, biến đổi, tổng hợp, đặt tên
                  | Xác định grain, ngữ nghĩa, thời gian, version
                  v
          API / Integration event
                  |
                  v
         Consumer có hợp đồng ổn định
~~~

Có thể hình dung:

\[
C=\operatorname{Project}_{P,V,S}(M),
\]

với \(M\) là mô hình nguồn, \(P\) là **mục đích**, \(V\) là **phiên bản và ngữ nghĩa thời gian**, \(S\) là **phạm vi chia sẻ/quyền**, còn \(C\) là hợp đồng công bố. Đây là **mô hình tư duy**, không phải phép toán chính thức mới trong đại số quan hệ.

### Vì sao không xuất bản nguyên entity?

Giả sử hệ Orders có:

~~~text
orders(
    id, tenant_id, public_order_number, customer_id,
    status_code, confirmed_at, currency_code,
    version, internal_risk_score, payment_token_ref,
    created_by_service, deleted_at
)
~~~

Nếu một API serialize toàn bộ hàng này:

- Consumer bị phụ thuộc vào `status_code`, `version` và các trường kỹ thuật có thể thay đổi khi refactor.
- Dữ liệu như `internal_risk_score` hoặc tham chiếu thanh toán có thể bị lộ ngoài mục đích được phê duyệt.
- Mỗi lần đổi bảng/ORM có thể kéo theo việc sửa hàng loạt consumer.
- Consumer tự suy diễn trạng thái, tiền và thời gian mà không có hợp đồng nghiệp vụ.

Thay vào đó, một phép chiếu có thể chỉ trả **mã đơn, trạng thái hiển thị, ngày xác nhận, dòng hàng và giá trị hàng đặt**. Thay đổi cấu trúc bảng bên trong không nhất thiết làm thay đổi giao diện này.

## 2. Bắt đầu từ nhu cầu người tiêu thụ

Giả sử cùng hệ Orders có ba người tiêu thụ:

| Consumer | Công việc cần làm | Thông tin đủ dùng | Giao diện có thể phù hợp |
|---|---|---|---|
| Customer portal | Mở **trạng thái hiện hành** của một đơn | ID, status, ngày, dòng hàng, số tiền | **Query API** |
| Fulfillment | Biết **đơn vừa được xác nhận** để bắt đầu xử lý | Event ID, order ID, thời điểm, tham chiếu cần thiết | **Integration event** |
| Data warehouse | Tính **giá trị hàng đã đặt** theo ngày, sản phẩm | Grain dòng hàng, giá tại thời điểm mua, dimension lịch sử | **Fact projection** từ nguồn/event |

Ba người tiêu thụ không cần cùng một JSON. Ví dụ hệ Fulfillment có thể chỉ nhận một thông báo xác nhận với `orderId`, rồi gọi API có quyền để lấy phần chi tiết khi bắt đầu công việc. Nếu Fulfillment phải **tự hoạt động khi Orders API không khả dụng**, hợp đồng event có thể cần thêm dữ liệu đã được xét duyệt. Lựa chọn đó phụ thuộc yêu cầu tự chủ, độ trễ và bảo mật.

Trước khi định nghĩa field, lập bảng:

| Nội dung | Câu hỏi phải trả lời |
|---|---|
| **Mục đích** | Consumer sẽ ra quyết định hoặc thực hiện thao tác gì? |
| **Owner** | Hệ/bounded context nào sở hữu sự thật nghiệp vụ? |
| **Grain** | Một response, một event hoặc một dòng read model đại diện cho gì? |
| **Thời gian** | Trạng thái hiện hành, tại thời điểm xác nhận, hay lúc nhận dữ liệu? |
| **ID** | Định danh ổn định theo tenant, cửa hàng hay toàn hệ? |
| **Độ trễ** | Có chấp nhận eventual consistency không? |
| **Thông tin tối thiểu** | Các trường nào thật sự được dùng; trường nào không chia sẻ? |
| **Phiên bản** | Ai triển khai trước; dữ liệu cũ có được phát lại không? |
| **Bảo vệ** | Quyền, retention, dữ liệu nhạy cảm, replay và bản sao dẫn xuất? |
| **Kiểm chứng** | Test nào chứng minh dữ liệu có đúng ngữ nghĩa? |

## 3. Ví dụ xuyên suốt: mô hình nội bộ Orders

Giả sử dịch vụ Orders sở hữu:

~~~text
orders(
    id, tenant_id, public_order_number, customer_id,
    status_code, confirmed_at, currency_code,
    row_version, internal_risk_score
)

order_items(
    order_id, line_no, product_id, quantity,
    unit_price_at_order, discount_amount
)

order_status_history(
    order_id, sequence_no, old_status, new_status, changed_at
)
~~~

Quy tắc giả định:

- `orders.id` là định danh nội bộ ổn định; `public_order_number` là mã hiển thị và có thể chỉ duy nhất theo `tenant_id`.
- Một dòng `order_items` có grain `(order_id,line_no)`.
- Đơn giá và chiết khấu trong ví dụ là **ảnh chụp lúc xác nhận**, không phải giá danh mục hiện hành.
- `status_code` chứa các trạng thái kỹ thuật chi tiết, có thể cần ánh xạ sang trạng thái công bố.
- Những trường nội bộ như điểm rủi ro **không** được trả chỉ vì chúng có mặt trong DB.

~~~mermaid
flowchart LR
    O["Orders domain\norders + items + history"] --> A["GET /orders/{id}\nTrạng thái hiện hành"]
    O --> E["OrderConfirmed\nSự thật đã xảy ra"]
    O --> F["fact_order_lines\nẢnh chụp lúc xác nhận"]
    A --> UI["Customer portal"]
    E --> W["Fulfillment"]
    F --> BI["Data warehouse"]
~~~

**Không nhất thiết** có ba bản sao toàn bộ dữ liệu. Ba mũi tên biểu thị **ba phép chiếu với mục đích và ngữ nghĩa khác nhau**.

## 4. Phép chiếu API: trả điều consumer cần biết ở thời điểm truy vấn

Ví dụ `GET /v1/orders/{orderId}` dành cho người được phép xem đơn.

### 4.1. Response JSON minh họa

~~~json
{
  "orderId": "ord_87342",
  "orderNumber": "ORD-2026-00123",
  "status": "CONFIRMED",
  "confirmedAt": "2026-11-21T09:15:30Z",
  "currency": "VND",
  "items": [
    {
      "lineNo": 1,
      "productCode": "BOOK-01",
      "quantity": 2,
      "unitPrice": "100000.00",
      "discountAmount": "0.00"
    },
    {
      "lineNo": 2,
      "productCode": "PEN-02",
      "quantity": 1,
      "unitPrice": "50000.00",
      "discountAmount": "10000.00"
    }
  ],
  "bookedAmount": "240000.00"
}
~~~

Giả định **một đơn vị tiền VND**, không gồm thuế hay phí vận chuyển:

\[
\text{bookedAmount}
=\sum_i(\text{quantity}_i\times\text{unitPrice}_i-\text{discountAmount}_i)
=240.000.
\]

`bookedAmount` là **giá trị hàng được đặt sau giảm giá**, không mặc nhiên là tiền đã thu, doanh thu kế toán hoặc giá trị ròng sau hoàn trả. Các trường tiền dùng **chuỗi thập phân** để tránh phụ thuộc vào cách xử lý số thực nhị phân của consumer; ứng dụng phải parse chúng theo quy tắc tiền tệ, không cộng chuỗi.

### 4.2. Bảng ánh xạ hợp đồng

| Field công bố | Nguồn/biến đổi | Ý nghĩa ổn định |
|---|---|---|
| `orderId` | ID public ổn định ánh xạ từ `orders.id` | Định danh dùng trong API, không tái sử dụng |
| `orderNumber` | `public_order_number` | Mã chứng từ hiển thị, namespace rõ ràng |
| `status` | Ánh xạ từ `status_code` | Tập trạng thái có ý nghĩa cho consumer |
| `confirmedAt` | `confirmed_at` | Mốc xác nhận nghiệp vụ, không phải thời gian đọc |
| `items[]` | Chiếu từng `order_items` có thứ tự theo `line_no` | Một dòng đúng một lần |
| `currency` | `currency_code` | Đơn vị của các trường tiền |
| `bookedAmount` | Tổng dòng theo công thức đã công bố | Không tính nhầm payment/ship |
| Không công bố | Risk score, token tham chiếu, metadata kỹ thuật | Không phục vụ mục đích hoặc không được phép |

API có thể đổi lớp ORM, schema nội bộ hoặc cách tính giá trị trung gian mà **không** bắt consumer đổi code, miễn giữ nguyên nghĩa của hợp đồng.

### 4.3. OpenAPI rút gọn

~~~yaml
openapi: 3.0.3
info:
  title: Orders Query API
  version: 1.0.0
paths:
  /v1/orders/{orderId}:
    get:
      summary: Lấy đơn trong phạm vi người gọi được phép xem
      parameters:
        - name: orderId
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Phép chiếu trạng thái đơn hiện hành
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/OrderView"
        "401":
          description: Chưa xác thực
        "404":
          description: Không tìm thấy trong phạm vi được phép
components:
  schemas:
    OrderView:
      type: object
      required: [orderId, orderNumber, status, currency, items, bookedAmount]
      properties:
        orderId:
          type: string
        orderNumber:
          type: string
        status:
          type: string
          description: Trạng thái công bố theo tài liệu nghiệp vụ
        confirmedAt:
          type: string
          format: date-time
          nullable: true
        currency:
          type: string
          minLength: 3
          maxLength: 3
        bookedAmount:
          type: string
          description: Giá trị hàng đặt, dạng thập phân theo currency
        items:
          type: array
          items:
            $ref: "#/components/schemas/OrderItem"
    OrderItem:
      type: object
      required: [lineNo, productCode, quantity, unitPrice, discountAmount]
      properties:
        lineNo:
          type: integer
          minimum: 1
        productCode:
          type: string
        quantity:
          type: integer
          minimum: 1
        unitPrice:
          type: string
        discountAmount:
          type: string
~~~

Đây là **ví dụ rút gọn**, chưa chứa `securitySchemes`, timeout, rate limit, mã lỗi đầy đủ, các chính sách phân trang/cache và SLA. API thật cần bổ sung những phần đó.

`confirmedAt` không nằm trong `required`, nhưng nếu được trả có thể là `null`. Nếu yêu cầu nghiệp vụ là “**luôn có mặt nhưng được phép null**”, phải đặt vào `required`. **Vắng mặt**, `null`, chuỗi rỗng và mảng rỗng không tự động có cùng nghĩa.

### 4.4. Quyền và độ mới

Một API query thường thể hiện **trạng thái lúc phục vụ truy vấn**; `status` có thể thay đổi từ `CONFIRMED` sang `SHIPPED` giữa hai lần GET.

Hợp đồng cần quy định:

- Đọc từ primary, cache hay replica; độ trễ được chấp nhận?
- Người gọi có quyền xem tài nguyên trong tenant hay không? **Biết ID không đồng nghĩa có quyền.**
- Khi không có quyền, dùng `403`, `404` hoặc chính sách khác để không lộ sự tồn tại của đối tượng?
- `items[]` là toàn bộ hay có phân trang, thứ tự có được bảo đảm?
- Cơ chế cache, `ETag`, version hoặc optimistic concurrency nếu có ghi dữ liệu?

## 5. Phép chiếu sự kiện: công bố điều đã xảy ra

Một **integration event** thường diễn đạt **sự thật nghiệp vụ đã xác nhận**: “Đơn `ord_87342` đã được xác nhận tại thời điểm X”. Nó khác **command** `ConfirmOrder` (“hãy xác nhận đơn”). Event thường được đặt tên ở thì quá khứ như `OrderConfirmed`, `PaymentCaptured`, `ShipmentDispatched`.

### 5.1. Ví dụ event envelope + payload

~~~json
{
  "eventId": "7c2fd18a-ec77-47a9-a0a2-54a25e278d17",
  "eventType": "order.confirmed",
  "schemaVersion": 1,
  "tenantId": "T01",
  "aggregateId": "ord_87342",
  "aggregateVersion": 4,
  "occurredAt": "2026-11-21T09:15:30Z",
  "correlationId": "workflow_20261121_001",
  "payload": {
    "orderId": "ord_87342",
    "orderNumber": "ORD-2026-00123",
    "confirmedAt": "2026-11-21T09:15:30Z",
    "currency": "VND",
    "bookedAmount": "240000.00"
  }
}
~~~

| Trường | Hợp đồng ngữ nghĩa |
|---|---|
| `eventId` | Nhận diện một **sự kiện logic**; khi gửi lại cùng sự kiện phải giữ ID |
| `eventType` | Loại sự việc nghiệp vụ đã xảy ra |
| `schemaVersion` | Phiên bản **hình dạng/ý nghĩa event**, không phải version đơn |
| `tenantId` | Phạm vi sở hữu dữ liệu và truy cập |
| `aggregateId` | ID đối tượng nghiệp vụ để liên hệ những event của cùng đơn |
| `aggregateVersion` | Chỉ có ý nghĩa sắp thứ tự nếu producer thật sự bảo đảm tăng tuần tự **theo một đơn** |
| `occurredAt` | Thời điểm nghiệp vụ xảy ra, không đồng nghĩa thời gian broker nhận |
| `correlationId` | Gắn nhiều bước trong workflow để tra cứu, không thay event ID |
| `payload` | Thông tin tối thiểu cho mục đích tích hợp đã phê duyệt |

Event này **không** gửi email, địa chỉ giao hàng, token thanh toán, risk score hoặc toàn bộ dòng hàng vì ví dụ consumer chỉ cần nhận sự kiện và dùng ID để bắt đầu workflow. Một consumer cần xử lý độc lập khi API bị gián đoạn có thể phải nhận payload rộng hơn, nhưng cần **căn cứ nghiệp vụ, phân quyền, retention và kiểm thử riêng**.

### 5.2. JSON Schema rút gọn

~~~json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "OrderConfirmedV1",
  "type": "object",
  "required": [
    "eventId", "eventType", "schemaVersion",
    "tenantId", "aggregateId", "occurredAt", "payload"
  ],
  "properties": {
    "eventId": { "type": "string", "format": "uuid" },
    "eventType": { "const": "order.confirmed" },
    "schemaVersion": { "const": 1 },
    "tenantId": { "type": "string", "minLength": 1 },
    "aggregateId": { "type": "string", "minLength": 1 },
    "aggregateVersion": { "type": "integer", "minimum": 1 },
    "occurredAt": { "type": "string", "format": "date-time" },
    "correlationId": { "type": "string" },
    "payload": {
      "type": "object",
      "required": [
        "orderId", "orderNumber", "confirmedAt",
        "currency", "bookedAmount"
      ],
      "properties": {
        "orderId": { "type": "string", "minLength": 1 },
        "orderNumber": { "type": "string" },
        "confirmedAt": { "type": "string", "format": "date-time" },
        "currency": { "type": "string", "pattern": "^[A-Z]{3}$" },
        "bookedAmount": {
          "type": "string",
          "pattern": "^[0-9]+(\\.[0-9]{1,2})?$"
        }
      }
    }
  }
}
~~~

`aggregateVersion` và `correlationId` ở đây là **tùy chọn**. Trong JSON Schema, `format` có thể cần bật cấu hình **assertion** tùy validator; đừng giả định mọi thư viện đều từ chối UUID/date-time sai định dạng. Schema kiểm tra **hình dạng**, không chứng minh trạng thái đơn thật, tổng tiền đúng hay event đã được phát sau commit.

### 5.3. Khác biệt giữa API và event

| Câu hỏi | API query | Integration event |
|---|---|---|
| Thể hiện lúc nào? | Thường là **hiện hành** hoặc snapshot được định nghĩa | **Đã xảy ra** tại `occurredAt` |
| Cách nhận | Consumer chủ động gọi | Consumer đăng ký nhận bất đồng bộ |
| Trạng thái đổi | GET tiếp theo có thể khác | Phát **event mới**, không sửa event cũ |
| Consumer đến muộn | Gọi API đọc mới nhất | Cần replay/backfill nếu cần lịch sử |
| Rủi ro chính | Timeout, phân quyền, cache, pagination | Trùng, sai thứ tự, trễ, replay, DLQ |

**`OrderConfirmed` không có nghĩa “đơn hiện đang CONFIRMED”.** Đơn có thể đã giao hoặc hủy sau khi event này được phát. Consumer cần theo dõi các event đời sau hoặc truy vấn API hiện hành khi thực sự cần biết trạng thái mới nhất.

## 6. Domain event khác integration event

**Domain event** có thể biểu diễn chuyển trạng thái trong bounded context Orders:

~~~text
OrderAggregateConfirmed(orderId, aggregateVersion, internalContext)
~~~

Không nên gửi thẳng entity/domain event nội bộ ra broker nếu consumer sẽ phụ thuộc vào cấu trúc ấy. Một **integration event** được ánh xạ sang hợp đồng công bố riêng:

~~~text
order.confirmed v1 {
    eventId, tenantId, orderId,
    confirmedAt, currency, bookedAmount
}
~~~

Lớp ánh xạ giúp:

- Thay entity/ORM/schema mà không phá consumer.
- Giữ riêng các trường nhạy cảm/metadata kỹ thuật.
- Tách vòng đời phiên bản public contract khỏi version nội bộ.
- Kiểm tra ngữ nghĩa event độc lập với cách lưu trong DB.

Thuật ngữ **domain event** không nhất thiết nói rằng event chỉ sống trong RAM, và **integration event** không bắt buộc phải dùng một loại broker cụ thể. Điểm khác nhau là **ranh giới sở hữu và cam kết với consumer**.

## 7. Bounded context và anti-corruption layer

Hai hệ thống cùng dùng một từ nhưng có thể **khác nghĩa**:

- Orders dùng `customerId` để nhận diện **người mua**.
- Billing cần bên **chịu trách nhiệm thanh toán**, có thể là tổ chức.
- Fulfillment cần **người nhận hàng**, có thể khác người mua.

Nếu tất cả dùng `customer_id` với giả định cùng một đối tượng, JSON hợp lệ nhưng dữ liệu vẫn có thể sai. Cần:

1. Xác định **bounded context** sở hữu mỗi khái niệm.
2. Đặt tên theo **vai trò** như `buyerId`, `billToPartyId`, `recipientId` khi nghiệp vụ phân biệt.
3. Dùng **anti-corruption layer** để chuyển đổi model từ hệ cũ hoặc đối tác, không rải mapping tùy ý tới từng consumer.
4. Ghi trường hợp thiếu dữ liệu/không ánh xạ được; không tự giả định quan hệ một-một.
5. Không cho consumer đọc trực tiếp bảng DB của domain khác để bù field thiếu trong API.

Consumer có thể lưu **read model cục bộ** của những dữ liệu cần thiết. Đây là bản sao **có chủ đích**, có độ trễ và quy tắc rebuild, không phải quyền sao chép toàn bộ DB nguồn.

## 8. Mức hạt và định danh của hợp đồng

| Thành phần | Grain: một phần tử là gì? | Khóa quan trọng |
|---|---|---|
| `orders` nguồn | Một đơn hiện hành | `orders.id` |
| `order_items` | Một dòng của đơn | `(order_id,line_no)` |
| API `GET /orders/{id}` | Một đơn cùng các dòng được phép hiển thị | Public `orderId` + quyền |
| `OrderConfirmed` | Một lần xác nhận hợp lệ | `eventId` (sự kiện), `aggregateId` (đơn) |
| `fact_order_lines` | Một dòng hàng tại xác nhận | `(order_id,line_no)` theo quy tắc phiên bản |
| `fact_payment_transactions` | Một giao dịch thanh toán | `paymentTransactionId` |

Một `orderId` có thể xuất hiện **một lần trong API response**, **một lần trong event xác nhận**, nhưng **nhiều lần trong fact dòng hàng và thanh toán**. Không được dùng `orderId` như khóa duy nhất của mọi bảng/sự kiện.

Nếu `orderNumber='000123'` chỉ duy nhất theo cửa hàng hoặc tenant, contract phải có **namespace** như `tenantId`/ `storeId`, hoặc ID public được bảo đảm duy nhất toàn hệ. Không tự suy tính duy nhất từ dữ liệu mẫu.

Một số hệ cấp mã tạm khi tạo đơn và mã chính thức khi xác nhận; khi đó cần phân biệt **stable ID** với **mã hiển thị theo thời điểm**. `eventId` cũng không được dùng thay cho `orderId`: một đơn có thể có nhiều event.

## 9. Tiền, thời gian, trạng thái và giá trị vắng mặt

### 9.1. Đơn vị tiền và công thức

`bookedAmount="240000.00"` chỉ rõ ý nghĩa khi hợp đồng nói:

~~~text
bookedAmount = sum(quantity × unitPriceAtOrder - lineDiscount)
currency     = VND
taxIncluded  = false theo ví dụ
shippingFee  = không bao gồm
rounding     = quy tắc được phê duyệt
~~~

Có thể chọn **số nguyên đơn vị nhỏ nhất** hoặc **chuỗi thập phân**; lựa chọn phải thống nhất theo tiền tệ, chính sách làm tròn và khả năng xử lý chính xác của consumer. Tránh `DOUBLE` cho số tiền cần độ chính xác thập phân.

### 9.2. Các loại thời gian

| Trường | Ý nghĩa |
|---|---|
| `confirmedAt` | Đơn được xác nhận theo nghiệp vụ |
| `occurredAt` | Sự kiện được coi là đã xảy ra |
| `publishedAt` | Publisher phát thông điệp |
| `receivedAt` | Consumer/broker nhận thông điệp |
| `updatedAt` | Trạng thái hiện hành được sửa |

Các thời điểm này **không nhất thiết trùng nhau**. Với báo cáo số đơn xác nhận theo tháng, chọn mốc `confirmedAt` và timezone nghiệp vụ đã phê duyệt, không tự dùng ngày consumer nhận event.

### 9.3. Ánh xạ trạng thái

Nguồn có thể có `CREATED`, `VALIDATING`, `PAYMENT_PENDING`, `CONFIRMED`, `ALLOCATING_STOCK`, `SHIPPED`, `DELIVERED`, `CANCELLED`. API UI có thể công bố ít trạng thái hơn: `PENDING`, `CONFIRMED`, `IN_TRANSIT`, `COMPLETED`, `CANCELLED`.

Việc gộp trạng thái phải được owner xác nhận. Consumer dùng switch exhaustive có thể lỗi khi producer thêm giá trị enum mới; **mở rộng enum không luôn an toàn**.

### 9.4. Omitted, null và rỗng

| Biểu diễn | Nghĩa có thể có theo hợp đồng |
|---|---|
| Trường **vắng mặt** | Phiên bản/đường đọc này không công bố trường |
| `field: null` | Chưa biết, chưa áp dụng hoặc bị xóa, **nếu được định nghĩa** |
| `field: ""` | Chuỗi rỗng thực sự |
| `items: []` | Danh sách được xác định là rỗng |
| `amount: "0.00"` | Giá trị tiền bằng không, **không** có nghĩa thiếu dữ liệu |

Không để mỗi consumer tự biến `null` thành 0 hoặc coi `items: []` là lỗi. Phải có phép thử cụ thể cho các trường hợp này.

## 10. Không để hợp đồng làm lộ dữ liệu vượt mục đích

Phép chiếu có mục đích cũng là **giảm lượng dữ liệu được chia sẻ** (*data minimization*). Dữ liệu nội bộ như điểm rủi ro, tham chiếu token thanh toán, thông tin định danh cá nhân, địa chỉ hoặc log nghiệp vụ chi tiết không mặc nhiên cần có trong API/event.

Trước khi công bố một field, hãy hỏi:

1. Consumer dùng field để **ra quyết định hoặc thực hiện bước nào**?
2. Consumer có quyền nhận field này ở **phạm vi tenant/người dùng** tương ứng không?
3. Giá trị có cần ở dạng gốc, hay chỉ cần nhóm trạng thái/định danh thay thế?
4. Consumer sẽ lưu field bao lâu, và nó có được sao chép tới search, cache, warehouse, log hoặc backup không?
5. Nếu giá trị bị sửa hoặc có yêu cầu xóa hợp lệ, các bản sao dẫn xuất sẽ xử lý như thế nào?

Một event có thể được lưu trong broker, ghi vào dead-letter queue, phát lại, sao chép sang nhiều consumer và giữ lâu. Vì vậy, rủi ro phát tán dữ liệu của **event chứa dư field** có thể đặc biệt khó xử lý.

**Không chỉ bỏ cột là đủ:** nếu endpoint cho phép đoán `orderId` của người khác, việc không trả email vẫn không thay thế **kiểm tra phân quyền**. Cần bảo vệ theo danh tính, tenant, quyền, mức nhạy cảm và chính sách lưu giữ ở từng đường đọc/phát sự kiện.

## 11. API và event có hợp đồng vận hành khác nhau

### 11.1. Với API: lỗi, độ mới và thao tác lặp lại

Hợp đồng API nên xác định:

- HTTP method/đường dẫn, query parameter và ý nghĩa lọc.
- Mã lỗi như `400`, `401`, `403`, `404`, `409` theo trường hợp áp dụng, và quy tắc **không làm lộ sự tồn tại** của tài nguyên ngoài quyền.
- Phân trang khi kết quả lớn, thứ tự ổn định hoặc cursor để tránh trùng/mất bản ghi giữa các trang.
- Timeout, retry, rate limit và idempotency cho API ghi nếu cần.
- Độ mới khi dùng cache/read replica; có bảo đảm **read-your-writes** hay không?
- `ETag`/version khi có optimistic concurrency control.

API `GET` hai lần liên tiếp có thể trả status khác nhau nếu đơn đã tiến triển. Đó không phải lỗi nếu contract là **trạng thái hiện hành** và mô tả đúng giới hạn độ trễ.

### 11.2. Với event: at-least-once, trùng và sai thứ tự

Nhiều hệ thông điệp thực tế hoạt động theo ngữ nghĩa **at least once**: một event có thể được gửi **nhiều lần** khi retry hoặc khi consumer xử lý xong nhưng mất ACK.

Consumer phải lường trước:

- **Duplicate**: cùng `eventId` có thể xuất hiện nhiều lần.
- **Out-of-order**: event phiên bản 5 có thể được nhận trước phiên bản 4, tùy partition/routing và cơ chế xử lý.
- **Late event**: sự kiện xảy ra hôm qua, nay mới nhận.
- **Poison message**: không giải mã được hoặc không thể áp dụng hợp lệ.
- **Replay/backfill**: phải xử lý lại event cũ để phục hồi một read model.

Không tuyên bố **exactly once end-to-end** chỉ vì broker có một chế độ giao dịch/đảm bảo đặc biệt. Cần đánh giá toàn chuỗi từ DB nguồn, publisher, broker, consumer tới **tác dụng phụ** như gửi email, ghi API khác hoặc tạo lệnh giao hàng.

### 11.3. Xử lý lặp bằng inbox và bất biến nghiệp vụ

Mẫu DDL PostgreSQL:

~~~sql
CREATE TABLE consumer_inbox (
    consumer_name TEXT NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Quy trình xử lý minh họa:

~~~text
BEGIN TRANSACTION
    Thử INSERT (consumer_name, event_id) vào consumer_inbox

    Nếu đã có khóa:
        Bỏ qua phần cập nhật nghiệp vụ đã được áp dụng

    Nếu đây là event mới:
        Cập nhật read model theo ngữ nghĩa và phiên bản

COMMIT
ACK khi transaction và xử lý cần thiết hoàn tất
~~~

Đây là **mã giả**, không phải SQL độc lập. Nếu cập nhật inbox và read model nằm **cùng DB transaction**, chúng có thể cùng commit/rollback. Nếu consumer còn gọi hệ ngoài hoặc phát sự kiện mới, cần cơ chế **idempotency và outbox riêng cho tác dụng phụ**. Inbox đơn lẻ không bảo đảm một email hoặc một API charge chỉ xảy ra đúng một lần.

### 11.4. Version của aggregate không có nghĩa thứ tự toàn cục

`aggregateVersion=4` hữu ích nếu:

- Producer **thực sự tăng version nhất quán khi chuyển trạng thái của cùng đơn**.
- Consumer biết cách xử lý nhận 5 trước 4 hoặc thiếu version.
- Định danh aggregate được ổn định trong đúng namespace.

Nó **không** bảo đảm event của hai đơn khác nhau có một thứ tự toàn cục; `occurredAt` cũng không phải một sequence tin cậy nếu có lệch đồng hồ.

## 12. Transactional outbox: giữ thay đổi nghiệp vụ và bản ghi cần phát cùng nhau

Một cách viết dễ gặp nhưng có lỗi:

~~~text
1. UPDATE orders SET status = CONFIRMED
2. COMMIT database thành công
3. Publish OrderConfirmed lên broker
4. Tiến trình chết giữa bước 2 và 3
~~~

Kết quả: **đơn đã xác nhận trong DB nhưng consumer không nhận event**. Nếu gửi event **trước** khi commit, việc DB rollback lại có thể tạo thông báo về sự kiện chưa hề xảy ra.

Giải pháp phổ biến là **transactional outbox**:

~~~mermaid
flowchart LR
    T["Một transaction ở Orders DB"] --> U["Cập nhật đơn hàng"]
    T --> X["Ghi integration_outbox"]
    X --> P["Publisher / CDC"]
    P --> B["Broker"]
    B --> C["Consumer idempotent"]
    C --> R["Read model"]
~~~

Trong **cùng một transaction nguồn**:

1. Kiểm tra điều kiện chuyển `PENDING → CONFIRMED`.
2. Cập nhật status, thời điểm và version của đơn.
3. Tính dữ liệu chốt, ghi **outbox chứa integration event** theo contract công bố.
4. Commit hai thay đổi cùng nhau.

Một worker/CDC reader đọc outbox đã commit, gửi lên broker và ghi nhận kết quả để retry.

### DDL outbox minh họa

~~~sql
CREATE TABLE integration_outbox (
    event_id UUID PRIMARY KEY,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    occurred_at TIMESTAMPTZ NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);

CREATE INDEX idx_outbox_unpublished
    ON integration_outbox (created_at, event_id)
    WHERE published_at IS NULL;
~~~

Ví dụ SQL quy trình nghiệp vụ (các `:param` là **tham số ứng dụng**):

~~~sql
BEGIN;

UPDATE orders
SET status_code = 'CONFIRMED',
    confirmed_at = :confirmed_at,
    row_version = row_version + 1
WHERE id = :order_id
  AND status_code = 'PENDING'
RETURNING id, tenant_id, public_order_number,
          confirmed_at, row_version;

-- Ứng dụng phải kiểm tra UPDATE trả đúng một dòng.
-- Dữ liệu dòng hàng/số tiền phải được chốt nhất quán.
-- Nếu UPDATE thất bại: ROLLBACK, không INSERT event.

INSERT INTO integration_outbox (
    event_id, aggregate_type, aggregate_id,
    event_type, schema_version, occurred_at, payload
)
VALUES (
    :event_id, 'order', :order_id,
    'order.confirmed', 1, :confirmed_at, CAST(:payload AS jsonb)
);

COMMIT;
~~~

Mẫu này **không thay thế** logic transaction thật: phải bảo đảm kiểm tra quyền, transition hợp lệ, tính tiền, tính nguyên tử của dữ liệu nguồn và xử lý concurrency. Nếu `UPDATE` không cập nhật dòng nào, ứng dụng phải rollback trước khi phát event. `row_version` dùng để minh họa cơ chế phiên bản; tên cột và quy tắc cập nhật phải khớp nguồn thật.

**Outbox không làm hết khả năng gửi trùng.** Publisher có thể gửi thành công rồi chết trước khi ghi `published_at`, dẫn tới gửi lại. Consumer vẫn phải idempotent.

### CDC không đồng nghĩa integration event

CDC (*change data capture*) có thể đọc các thay đổi đã commit. Nhưng nếu phát **nguyên row `orders` từ WAL/binlog**, consumer sẽ bị buộc vào tên bảng/cột nội bộ. Có thể dùng CDC **trên bảng outbox đã chứa payload hợp đồng**, hoặc ánh xạ CDC qua một lớp anti-corruption/contract có quy tắc rõ.

## 13. Event thành read model có mục đích

Fulfillment có thể xây projection cục bộ:

~~~text
OrderConfirmed
    ↓
Fulfillment read model:
    tenant_id, order_id, confirmed_at, processing_state
~~~

Ví dụ DDL:

~~~sql
CREATE TABLE fulfillment_order_queue (
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL,
    processing_state TEXT NOT NULL,
    source_aggregate_version BIGINT,
    PRIMARY KEY (tenant_id, order_id)
);
~~~

Đây **không phải bản sao mọi thuộc tính của Orders**. Nó chỉ giữ những gì cần để quản lý công việc fulfillment. Hệ này không trở thành owner của trạng thái gốc của đơn chỉ vì có một bảng chứa `order_id`.

### Những giới hạn nhất quán phải thỏa thuận

- **Trễ cập nhật:** API Orders đã trả `CONFIRMED` nhưng queue Fulfillment chưa có dòng. Cần SLO lag, cảnh báo và cách xử lý.
- **Duplicate:** không tạo hai công việc cho một sự kiện logic; dùng event ID và bất biến nghiệp vụ.
- **Out-of-order:** không để event trạng thái cũ ghi đè trạng thái mới.
- **Event thiếu:** có cách phát lại, đối soát hoặc backfill từ owner.
- **Đơn bị hủy:** event `OrderCancelled` hoặc truy vấn owner phải dẫn tới quy tắc ngừng xử lý phù hợp với trạng thái thực tế.
- **Rebuild:** consumer có khả năng tái tạo projection từ event history, snapshot đáng tin cậy hoặc API/bulk export được hỗ trợ.

Nếu consumer cần tự hoạt động khi Orders không khả dụng, projection có thể chứa **nhiều dữ liệu hơn**; đó là quyết định về tính tự chủ và **độ trễ/cá nhân**, không phải lý do sao chép toàn bộ database.

## 14. Kiểm chứng phép chiếu: không nhân số đo khi JOIN

Giả sử một đơn có:

~~~text
3 order_items
2 payment_transactions
2 shipments
~~~

JOIN cả ba bảng theo `order_id` rồi `SUM(item_amount)` có thể tạo:

\[
3\times2\times2=12\text{ dòng}.
\]

Mỗi dòng hàng bị lặp **4 lần**; giá trị hàng đặt có thể tăng sai bốn lần. **JSON hợp lệ vẫn có thể sai nghiệp vụ**.

### 14.1. Tính bookedAmount theo grain cấp dòng rồi tổng hợp cấp đơn

~~~sql
WITH amounts_by_order AS (
    SELECT
        order_id,
        SUM(
            quantity * unit_price_at_order - discount_amount
        ) AS booked_amount
    FROM order_items
    GROUP BY order_id
)
SELECT
    o.id AS order_id,
    o.tenant_id,
    o.public_order_number,
    o.status_code,
    o.confirmed_at,
    o.currency_code,
    a.booked_amount
FROM orders AS o
LEFT JOIN amounts_by_order AS a
  ON a.order_id = o.id
WHERE o.id = :order_id
  AND o.tenant_id = :tenant_id;
~~~

`amounts_by_order` có **một dòng cho mỗi order ID**. Truy vấn ví dụ lọc tenant để tránh trộn phạm vi, nhưng **không thay kiểm tra quyền** của caller. `LEFT JOIN` có thể tạo `booked_amount = NULL` khi đơn không có dòng; contract phải xác định trạng thái này hợp lệ hay cần chặn bằng nghiệp vụ. Với nhiều tiền tệ/phiên bản, tính cùng một phạm vi và quy tắc quy đổi.

### 14.2. Phép thử ánh xạ

~~~text
Given:
    Đơn ord_87342 có hai dòng đã chốt:
    (2 × 100000 - 0)
    (1 × 50000 - 10000)

When:
    Tạo OrderView và OrderConfirmed v1

Then:
    bookedAmount = "240000.00"
    currency = "VND"
    confirmedAt phản ánh mốc xác nhận nghiệp vụ
    không có internalRiskScore hoặc paymentTokenRef
    hai dòng items được trả đúng một lần trong API
~~~

Kiểm tra **kiểu JSON, quyền và nội dung tính toán** là các phép thử riêng. Contract test chỉ xác nhận có field `bookedAmount` kiểu string sẽ không bắt được lỗi tiền bị nhân do JOIN.

## 15. Tiến hóa hợp đồng mà không phá consumer

Thay đổi schema nội bộ không nhất thiết là thay đổi hợp đồng. Nhưng một trường public đổi tên, kiểu hoặc **ý nghĩa nghiệp vụ** có thể làm consumer sai.

| Thay đổi | Thường an toàn với consumer cũ? | Điều phải kiểm tra |
|---|---|---|
| Thêm trường **tùy chọn** trong response/event | **Có điều kiện** | Consumer/schema đóng có thể từ chối field lạ |
| Thêm trường **bắt buộc** trong request | Thường **breaking** | Client cũ không gửi field đó |
| Xóa/đổi tên trường cũ | Thường **breaking** | Consumer cũ còn đọc tên cũ |
| Đổi `orderId` từ string thành number | **Breaking** | Mất leading zero, kiểu và namespace |
| Đổi `bookedAmount` từ tiền hàng đặt sang tiền đã thu | **Breaking về ngữ nghĩa** | Schema validator không phát hiện |
| Thêm giá trị `status` mới | **Có điều kiện** | Consumer có switch exhaustive |
| Đổi `confirmedAt` thành thời gian publish | **Breaking về ngữ nghĩa** | Báo cáo kỳ có thể sai |
| Thêm event type mới | Có thể an toàn | Consumer subscribe wildcard có nhận event mới không? |
| Thay thứ tự `items[]` | Tùy hợp đồng | Consumer có dựa vào thứ tự không? |
| Đổi ID/namespace | Rủi ro cao | Dedupe, quyền và liên kết sự kiện |

### Versioning thực dụng

1. Công bố schema và tài liệu ý nghĩa của trường; chọn chiến lược versioning nhất quán, như `/v1` cho API và `schemaVersion` trong event.
2. Thay đổi không phá vỡ phải được **kiểm tra với consumer thực tế**, không chỉ suy từ quy tắc “thêm field là được”.
3. Với thay đổi breaking, cân nhắc phát **v1 và v2 song song** trong một khoảng chuyển tiếp.
4. Thông báo deprecation, đo consumer còn sử dụng v1 và chốt thời điểm gỡ bỏ theo chính sách.
5. Với event lưu lâu, tính trước **consumer v2 sẽ đọc event v1 khi replay** như thế nào.
6. Khi thay đổi **ý nghĩa** chứ không chỉ đổi tên, phải có quy tắc chuyển đổi thực sự; không upcast dữ liệu cũ bằng cách đoán.

### Backward và forward compatibility

- **Consumer mới đọc được dữ liệu cũ**: cần thiết cho replay/backfill.
- **Consumer cũ đọc được dữ liệu mới**: cần thiết nếu producer được triển khai trước.

Tên `BACKWARD`/`FORWARD` trong registry có thể được định nghĩa theo quan hệ **schema writer–reader**; hãy ghi rõ **ai ghi, ai đọc và thứ tự rollout** để tránh áp dụng nhầm.

## 16. Kiểm thử hợp đồng theo nhiều lớp

### 16.1. Shape/schema test

Kiểm tra OpenAPI/JSON Schema/AsyncAPI ở cấp trường required, kiểu, format, version, enum, nullable/omitted, số thập phân và mảng. Nếu dùng codegen, phải kiểm tra cả khả năng parse trường lạ.

### 16.2. Semantic contract test

Kiểm tra ngữ nghĩa:

- `bookedAmount` bằng tổng từ dòng hàng theo công thức đã xác nhận.
- `OrderConfirmed` chỉ được ghi khi chuyển trạng thái hợp lệ được commit.
- `confirmedAt` là thời điểm nghiệp vụ, không phải giờ consumer nhận.
- `tenantId` và `orderId` định danh đúng phạm vi.
- Dữ liệu nhạy cảm không vượt ranh giới.

### 16.3. Consumer-driven contract

Consumer cung cấp ví dụ/điều kiện về những trường mình **thực sự dùng**; producer chạy phép thử để biết thay đổi mới có làm lỗi consumer. Nhưng consumer-driven test **không thay thế** schema chuẩn, kiểm tra bảo mật hoặc sự phê duyệt ý nghĩa của owner.

### 16.4. Failure/recovery test

| Tình huống | Kết quả mong đợi |
|---|---|
| Commit DB thành công, publisher chết trước gửi | Outbox còn event để retry |
| Publisher gửi xong nhưng chưa đánh dấu đã gửi | Consumer xử lý **event ID trùng** an toàn |
| Event version 5 đến trước version 4 | Không ghi trạng thái cũ đè trạng thái mới |
| Consumer ngừng hoạt động một ngày | Lag được giám sát; có thể replay/backfill |
| Replay v1 trên consumer đã dùng v2 | Đọc được theo schema cũ hoặc upcaster hợp lệ |
| Caller khác tenant | Không nhìn được tài nguyên ngoài quyền |
| Một field nội bộ mới xuất hiện trong ORM | Không tự bị serialize vào API/event |
| Hợp đồng hợp lệ nhưng tiền sai do JOIN | Semantic test và đối soát phát hiện |
| Đổi tên bảng nguồn | Consumer không bắt buộc sửa nếu contract vẫn đúng |
| Read model bị mất | Có thể rebuild từ nguồn được owner hỗ trợ |

### 16.5. Theo dõi vận hành

~~~text
outbox_unpublished_age_seconds
outbox_pending_events
consumer_lag_seconds
duplicate_event_count
invalid_contract_message_count
dead_letter_count
api_contract_error_rate
data_reconciliation_mismatch_count
projection_rebuild_duration
deprecated_version_consumers
~~~

Ngưỡng/SLO phải xuất phát từ nhu cầu thực tế. Event trùng không nhất thiết là sự cố khi thiết kế at-least-once, nhưng **tác dụng phụ không được trùng** và retry bất thường cần có cảnh báo.

## 17. Quy trình thiết kế phép chiếu có mục đích

### Bước 1 — Xác định câu hỏi, hành động và consumer

Ví dụ “Fulfillment cần biết **đơn vừa được xác nhận** để bắt đầu xử lý, không cần điểm rủi ro hay thông tin thanh toán”. Đây là căn cứ chọn **event**.

### Bước 2 — Chọn owner và sự thật nguồn

Hệ nào chịu trách nhiệm định nghĩa “đã xác nhận”, tiền, khách và dòng đơn? Consumer không tự JOIN xuyên DB của domain khác để suy định nghĩa riêng.

### Bước 3 — Chốt grain, ID và thời gian

Viết rõ “một event cho một lần xác nhận đơn hợp lệ”, “một API response cho một đơn hiện hành”. Xác nhận ID ổn định, namespace, timestamp và mức độ trễ.

### Bước 4 — Xây bảng ánh xạ có chủ đích

Với mỗi field: **nguồn → quy tắc biến đổi → kiểu → ý nghĩa → quyền → kiểm thử**. Ghi những trường **không** được chia sẻ. Đừng bê nguyên entity lên network.

### Bước 5 — Thiết kế nhất quán và failure

API cache/replica như thế nào? Event có outbox, retry, ID để dedupe, thứ tự, replay? Consumer cần snapshot ban đầu hay gọi API sau khi nhận event?

### Bước 6 — Chốt evolution và kiểm thử

Ghi version, compatibility và rollout; chạy shape, semantic, security, consumer-driven, duplicate/late event và recovery test.

### Bước 7 — Đo lường và review định kỳ

Theo dõi lag, lỗi hợp đồng, phát lại, sai khác projection, người dùng phiên bản cũ. Khi schema nội bộ đổi, chỉ sửa lớp ánh xạ nếu **ý nghĩa contract vẫn giữ nguyên**.

## 18. Liên hệ mô hình quan hệ, document, đồ thị và phân tích

| Mô hình nội bộ | Có thể lưu gì? | Phép chiếu ra ngoài |
|---|---|---|
| **Quan hệ** | `orders`, `order_items`, FK, FD, trạng thái | API ghép một đơn; event chọn chuyển trạng thái |
| **Document** | Đơn có mảng `items[]`, metadata kỹ thuật | API chọn bớt field, kiểm soát array và quyền |
| **Đồ thị** | Node order/buyer/product và edge | API trả một quan hệ/đường đi đã xác minh, không xuất cả graph |
| **Phân tích** | Fact ở grain sự kiện/dòng/snapshot, dimension lịch sử | Event/fact projection đúng thời điểm và KPI |

**Ranh giới hợp đồng không biến mất khi đổi DBMS.** Một document có nhiều field không buộc API phải trả hết; một truy vấn đồ thị có nhiều đường đi không chứng minh có nhiều sự kiện; một data mart chứa `orderId` không có nghĩa event `OrderConfirmed` phải chứa mọi số đo BI.

## 19. Những nhầm lẫn thường gặp

| Nhầm lẫn | Hậu quả | Cách sửa |
|---|---|---|
| “API cứ serialize entity/ORM” | Lộ schema và trường nhạy cảm | DTO/contract độc lập theo mục đích |
| “Event là hàng DB vừa thay đổi” | CDC thô buộc consumer vào bảng/cột | Integration event có ngữ nghĩa |
| “Phép chiếu chỉ là bớt cột” | Bỏ qua chuyển đổi tiền, trạng thái, quyền | Mapping có kiểm chứng |
| “Biết orderId tức có quyền xem” | Lộ dữ liệu xuyên tenant | Kiểm tra authz và phạm vi |
| “OrderConfirmed nói đơn hiện đang CONFIRMED” | Bỏ qua chuyển trạng thái sau đó | Phân biệt event quá khứ và state hiện hành |
| “eventId và orderId giống nhau” | Không dedupe được các event của một đơn | ID sự kiện riêng, aggregate ID riêng |
| “Broker exactly-once nên consumer khỏi dedupe” | Side effect có thể lặp | Idempotency/inbox và bảo vệ side effect |
| “Commit DB rồi publish không thể mất event” | Crash giữa hai bước | Outbox hoặc cơ chế đáng tin cậy tương đương |
| “Mọi event có thứ tự toàn cục” | Sai khi có partition/consumer song song | Thỏa thuận ordering theo aggregate |
| “Thêm field luôn tương thích” | Client strict có thể lỗi | Contract test và schema compatibility |
| “Đổi ý nghĩa mà giữ kiểu là an toàn” | KPI sai nhưng JSON vẫn parse | Semantic versioning và review |
| “Có orderId thì JOIN mọi fact được” | Fanout nhiều-nhiều | Tổng hợp về grain chung trước |
| “Xóa ở Orders là xóa hết event” | Read model, DLQ, backup còn bản sao | Data lineage, retention và purge |
| “Consumer đọc DB nguồn cho nhanh” | Phá ranh giới sở hữu và version | API/event/bulk export theo hợp đồng |

## 20. Bài luyện tập có lời giải

### Bài 1 — Chọn API hay event

Customer portal cần xem **trạng thái hiện tại** khi người dùng mở đơn; Fulfillment cần biết **đơn vừa được xác nhận**. Nên dùng gì?

**Lời giải:** Portal dùng **query API** có kiểm tra quyền. Fulfillment có thể dùng **`OrderConfirmed` integration event**. Hai hợp đồng phục vụ hai thời điểm và mục đích khác nhau.

### Bài 2 — Chọn field

Entity nội bộ có `orderId`, `confirmedAt`, `internalRiskScore`, `paymentTokenRef`, `customerEmail`. Consumer chỉ cần tạo công việc theo mã đơn.

**Lời giải:** Công bố ID, thời điểm và event metadata cần thiết; không đưa risk score, token hay email nếu không có mục đích/quyền. Nếu cần chi tiết, dùng hợp đồng bổ sung đã thẩm định.

### Bài 3 — Ba loại định danh

Một đơn có `orderId=ord_42`, `orderNumber=HN-2026-0001` và một `eventId` riêng. Chúng khác nhau ra sao?

**Lời giải:** `orderId` nhận diện **đối tượng**, `orderNumber` là mã chứng từ hiển thị có namespace, `eventId` nhận diện **một sự kiện logic**. Một đơn có nhiều event, nên không dùng số đơn làm event ID.

### Bài 4 — Retry nhận cùng event

Một `OrderConfirmed` được gửi hai lần vì mất ACK. Consumer có được tạo hai công việc giao hàng không?

**Lời giải:** Không nếu nghiệp vụ chỉ cho một công việc tương ứng. Dùng **idempotency** theo event ID và bất biến nghiệp vụ; xử lý side effect ngoài DB bằng khóa idempotency riêng.

### Bài 5 — Khoảng hở sau commit

DB đã commit trạng thái `CONFIRMED`, tiến trình chết trước khi publish. Có thể dùng thiết kế gì?

**Lời giải:** **Transactional outbox** ghi thay đổi và bản event cần phát trong cùng transaction; publisher retry từ outbox. Consumer vẫn cần xử lý duplicate.

### Bài 6 — Đổi tên field

Producer đổi `confirmedAt` thành `approvedAt` trong event v1, bỏ tên cũ. Consumer cũ có an toàn không?

**Lời giải:** Thường **không**. Đó là đổi tên breaking; cần giai đoạn chuyển đổi hoặc phiên bản mới. Nếu “approved” còn khác nghĩa “confirmed”, đó là thay đổi **ngữ nghĩa** cần xem xét riêng.

### Bài 7 — Thêm optional field

Producer thêm `salesChannel` tùy chọn trong JSON response. Có chắc consumer cũ hoạt động?

**Lời giải:** Không chắc, vì consumer strict có thể từ chối field chưa biết. Kiểm tra schema writer/reader, codegen và consumer contract tests trước rollout.

### Bài 8 — JOIN làm sai KPI

Đơn D01 có 3 dòng hàng, 2 payment và 2 shipment. JOIN tất cả theo order ID và `SUM(lineAmount)` gây lỗi gì?

**Lời giải:** Tạo tới \(3\times2\times2=12\) dòng; mỗi line amount bị lặp bốn lần. Tính tiền ở **grain dòng → nhóm cấp đơn** trước khi JOIN các nguồn khác. Không dùng `SUM(DISTINCT amount)` làm mẹo sửa.

### Bài 9 — Event đến sai thứ tự

Consumer nhận bản trạng thái aggregate version 6 rồi version 5. Có nên ghi bản 5 đè bản 6?

**Lời giải:** Không nếu đây là projection **trạng thái mới nhất** và producer bảo đảm version tăng theo aggregate. Cần kiểm soát sequence, chỗ thiếu và retry; nếu consumer lưu **event log append-only**, có thể lưu cả hai kèm thời điểm/phiên bản để dựng lại.

### Bài 10 — Namespace mã đơn

Hai tenant đều có `orderNumber=000123`. Consumer lưu `orders_by_number(orderNumber PRIMARY KEY)`. Điều gì sai?

**Lời giải:** Thiếu **namespace**. Dùng khóa `(tenantId,orderNumber)` hoặc ID public duy nhất toàn hệ theo hợp đồng, nếu không sẽ gộp nhầm đơn.

### Bài 11 — Thời điểm event và báo cáo

Đơn xác nhận lúc `2026-10-31T23:59:00Z`, consumer nhận lúc `2026-11-01T00:03:00Z`. Báo cáo theo **ngày xác nhận UTC** xếp vào tháng nào?

**Lời giải:** **Tháng 10**, dùng `confirmedAt`, không dùng giờ nhận. Dữ liệu đến muộn cần quy trình cập nhật hoặc đối soát kỳ đã chốt.

### Bài 12 — Replay sau nâng schema

Event v1 đã lưu suốt một năm, producer nay dùng v2. Consumer mới cần dựng read model từ cả v1/v2.

**Lời giải:** Consumer phải đọc được hai schema hoặc có **upcaster** hợp lệ và metadata phiên bản. Không thể chỉ đổi tên trường nếu v2 đổi **ý nghĩa của số tiền, trạng thái hay mốc thời gian**.

## 21. Checklist trước khi công bố hợp đồng

- [ ] Đã xác định **consumer, mục đích và hành động** cần thực hiện.
- [ ] Đã chỉ rõ **bounded context owner** và nguồn chân lý.
- [ ] Đã phân biệt API trạng thái hiện hành, event quá khứ và read model/fact.
- [ ] Đã khai báo **grain**, định danh ổn định và namespace theo tenant/nguồn.
- [ ] Đã ghi mapping **field → nguồn/biến đổi/kiểu/ý nghĩa/quyền**.
- [ ] Đã chọn **trường tối thiểu**, loại dữ liệu nội bộ hoặc nhạy cảm không cần thiết.
- [ ] Tiền, đơn vị, cách làm tròn và các loại KPI có định nghĩa rõ.
- [ ] Thời gian `occurredAt`, `confirmedAt`, `publishedAt`, `receivedAt` không bị nhầm.
- [ ] `null`, omitted field, empty array, enum lạ có chính sách.
- [ ] API có xác thực, phân quyền, lỗi, cache, pagination/consistency khi cần.
- [ ] Event có event ID, schema version, aggregate ID và quy tắc duplicate/ordering/replay.
- [ ] Có outbox hoặc bảo đảm phát event phù hợp **sau khi commit nghiệp vụ**.
- [ ] Consumer idempotent, có cách xử lý side effects, retry, DLQ, backfill.
- [ ] Đã đối soát dữ liệu công bố với nguồn và kiểm tra JOIN không nhân measure.
- [ ] Có OpenAPI/JSON Schema/AsyncAPI thích hợp, shape test, semantic test và consumer contract test.
- [ ] Có chính sách compatibility, version rollout, deprecation và replay dữ liệu cũ.
- [ ] Có giám sát lag, invalid messages, duplicate, lỗi read model và owner.
- [ ] Có data lineage, retention và xử lý bản sao dẫn xuất khi có yêu cầu sửa/xóa hợp lệ.

**Ghi nhớ:** **API và event contract là phép chiếu có mục đích của sự thật nghiệp vụ qua ranh giới sở hữu**, không phải bản sao một bảng hay entity. Hợp đồng tốt chỉ chia sẻ thông tin cần thiết, có grain, thời gian, ID và ý nghĩa ổn định; đồng thời bảo vệ dữ liệu, có chiến lược tiến hóa và phép thử kiểm chứng. Khi mô hình nội bộ thay đổi mà ngữ nghĩa hợp đồng không đổi, các hệ có thể phát triển độc lập hơn **mà không hy sinh tính đúng đắn của dữ liệu**.
