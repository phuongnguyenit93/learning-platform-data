# Phân biệt sự kiện miền, sự kiện tích hợp và bản ghi thay đổi lưu trữ

## 1. Ba loại thông tin có thể mô tả cùng một thay đổi, nhưng trả lời các câu hỏi khác nhau

Giả sử nền tảng thương mại điện tử đã giao một đơn hàng cho đơn vị vận chuyển. Trong hệ thống có thể xuất hiện đồng thời ba bản ghi:

1. **Domain event (sự kiện miền)**: `OrderHandedToCarrier` — bộ phận giao vận xác nhận đã bàn giao đơn cho nhà vận chuyển.
2. **Integration event (sự kiện tích hợp)**: `OrderShipmentConfirmed.v1` — dịch vụ giao vận công bố cho các hệ thống đăng ký nhận rằng đơn đã được bàn giao, kèm dữ liệu cần thiết theo hợp đồng tích hợp.
3. **Change Data Capture record (bản ghi thay đổi lưu trữ, thường gọi là CDC record)**: cơ sở dữ liệu ghi nhận một hàng trong bảng `orders` đã đổi `fulfillment_status` từ `READY` sang `SHIPPED`.

Cả ba có thể liên quan cùng một diễn tiến, nhưng không thể coi là ba cách viết tương đương:

- **Domain event** trả lời: *Sự thật nghiệp vụ nào đã xảy ra trong một ranh giới nghiệp vụ?*
- **Integration event** trả lời: *Hệ thống khác được thông báo sự thật hoặc kết quả nghiệp vụ nào, qua hợp đồng nào?*
- **Storage change record** trả lời: *Bản ghi kỹ thuật nào của hệ lưu trữ đã được thêm, sửa hoặc xóa?*

Nếu đồng nhất chúng, hệ thống có thể phụ thuộc chặt vào cấu trúc bảng, gửi nhầm trạng thái trung gian ra ngoài, làm lộ dữ liệu không cần thiết hoặc khiến báo cáo lịch sử suy diễn sai ý nghĩa của một lần `UPDATE`.

Trong thiết kế mô hình dữ liệu, phân biệt ba loại này giúp quyết định **thực thể nào là nguồn sự thật**, nơi đặt ràng buộc nghiệp vụ, cấu trúc thông điệp được chia sẻ, khóa định danh, chỉ mục và cách tiến hóa lược đồ theo thời gian.

## 2. So sánh đặc điểm và phạm vi sử dụng

| Tiêu chí | Domain event | Integration event | Storage change record / CDC |
| --- | --- | --- | --- |
| **Đơn vị ý nghĩa** | Một sự việc đã được xác nhận trong miền nghiệp vụ. | Một thông tin nghiệp vụ được công bố cho bên tiêu thụ ngoài ranh giới nguồn. | Một thay đổi hàng/cột hoặc thao tác ghi nhận ở tầng lưu trữ. |
| **Ví dụ** | `OrderHandedToCarrier`. | `OrderShipmentConfirmed.v1`. | `UPDATE orders SET fulfillment_status='SHIPPED'`. |
| **Nguồn tạo** | Logic xử lý nghiệp vụ/aggregate sau khi quy tắc thỏa mãn. | Thành phần xuất bản, thường ánh xạ từ kết quả/domain event. | Cơ chế log giao dịch, trigger hoặc công cụ bắt thay đổi. |
| **Đối tượng dùng** | Logic và thành phần trong ranh giới miền; đôi khi các projection nội bộ. | Hệ thống khác: thông báo, đối soát, phân tích, đối tác. | Đồng bộ dữ liệu, replica, chỉ mục tìm kiếm, pipeline dữ liệu, outbox relay. |
| **Hợp đồng** | Ngôn ngữ nghiệp vụ nội bộ, bất biến và ranh giới aggregate. | Hợp đồng công khai hơn: version, quyền truy cập, tương thích, độ trễ. | Phụ thuộc schema và metadata của hệ lưu trữ/công cụ CDC. |
| **Thứ tự** | Có thể có thứ tự trong aggregate, không mặc định toàn cục. | Phụ thuộc khóa phân vùng, broker và hợp đồng phát. | Thường có thứ tự log/offset trong một nguồn cụ thể; không đồng nghĩa thứ tự nghiệp vụ toàn hệ thống. |
| **Giá trị kiểm toán** | Tốt nếu giữ được nghĩa và lịch sử một cách tin cậy. | Hữu ích cho truy vết trao đổi giữa hệ thống. | Chính xác về thay đổi kỹ thuật đã ghi nhận; có thể thiếu lý do nghiệp vụ. |
| **Dữ liệu cần lưu** | Dữ liệu đủ hiểu sự việc và bảo vệ bất biến trong ngữ cảnh của nó. | Dữ liệu tối thiểu, ổn định, được phép chia sẻ và đủ cho consumer. | Ảnh trước/sau hoặc biểu diễn log thay đổi tùy database và cấu hình. |

**Ranh giới quan trọng:** domain event không bắt buộc phải được lưu vĩnh viễn; nó có thể chỉ tồn tại trong luồng xử lý của một giao dịch. Chỉ khi **chuỗi event là nguồn sự thật chính để khôi phục trạng thái** mới gọi là event sourcing. Tương tự, có message broker, bảng outbox hoặc pipeline CDC không tự động biến hệ thống thành event-sourced system.

## 3. Domain event: mô tả sự thật và quy tắc bên trong miền

Một **domain event** nên có tên thể hiện việc *đã xảy ra* và được công nhận, thay vì tên thao tác kỹ thuật. Ví dụ:

- `OrderPlaced`: yêu cầu mua hàng đã được chấp nhận thành một đơn.
- `PaymentCaptured`: khoản thu tiền đã được nguồn có thẩm quyền xác nhận.
- `OrderHandedToCarrier`: việc bàn giao thực tế cho đơn vị vận chuyển đã được xác nhận.
- `RefundApproved`: một quyết định duyệt hoàn tiền đã được thông qua; không đồng nghĩa tiền đã về tài khoản khách.
- `RefundCompleted`: việc hoàn tiền thực sự thành công theo tiêu chí đã định nghĩa.

Đừng nhầm **command** `CapturePayment` với **event** `PaymentCaptured`. Command có thể bị từ chối vì số tiền sai, vượt hạn mức hoặc trạng thái không hợp lệ. Event mô tả kết quả sau khi điều kiện được chấp nhận.

### Đặt sự kiện ở đúng ranh giới nhất quán

Giả sử aggregate `Order` quản lý trạng thái hoàn tất chuẩn bị và bàn giao. Quy tắc có thể là:

> Chỉ chấp nhận `OrderHandedToCarrier` nếu đơn đang ở `READY`, có mã bàn giao hợp lệ và chưa ghi nhận bàn giao cho cùng kiện hàng.

Hệ thống phải kiểm tra bất biến này trong cùng phạm vi nhất quán với thay đổi tương ứng. Thứ tự của các domain event thuộc một đơn có thể biểu diễn bằng `order_version` hoặc `sequence_no`, nhưng các đơn khác nhau không mặc nhiên có một thứ tự nghiệp vụ chung.

Nếu thực tế hoạt động **bàn giao** được quản lý trong aggregate `Shipment` độc lập, `ShipmentHandedOver` có thể phù hợp hơn; không ép mọi sự kiện vào aggregate `Order`. Quyết định nên dựa vào ràng buộc nghiệp vụ và quyền sở hữu dữ liệu.

Một domain event nội bộ minh họa:

~~~json
{
  "event_id": "242093fc-144d-4b3b-a027-a3cc09adb73e",
  "event_type": "OrderHandedToCarrier",
  "aggregate_type": "Order",
  "aggregate_id": "ORD-842",
  "aggregate_version": 12,
  "occurred_at": "2026-11-20T03:05:00Z",
  "actor_type": "STAFF",
  "actor_id": "STAFF-18",
  "payload": {
    "shipment_id": "SHP-331",
    "carrier_id": "CARRIER-07",
    "handover_receipt_id": "HND-945",
    "warehouse_id": "WH-HCM-02"
  }
}
~~~

Mục đích của event này là diễn tả một sự thật trong ngữ cảnh nghiệp vụ. `aggregate_version` ở đây là phiên bản logic của đơn, không phải offset của Kafka hoặc số thứ tự toàn cơ sở dữ liệu. `occurred_at` là thời điểm được nguồn có thẩm quyền xác nhận bàn giao; thời điểm lưu log hay phát message có thể muộn hơn.

### Những điều domain event **không** tự bảo đảm

Việc đặt tên đúng không tự bảo đảm transaction hợp lệ, thứ tự sự kiện, lưu lịch sử, khả năng replay hay việc consumer xử lý đúng một lần. Đó là trách nhiệm của thiết kế giao dịch, cơ chế lưu trữ, ràng buộc dữ liệu và xử lý thông điệp.

## 4. Integration event: hợp đồng chia sẻ giữa các hệ thống

**Integration event** thường được tạo khi một dịch vụ cần công bố kết quả đã xác nhận để hệ thống khác phản ứng. Consumer có thể là dịch vụ thông báo, dịch vụ chăm sóc khách hàng, đối tác vận chuyển hoặc nền tảng phân tích.

Khác với domain event nội bộ, integration event là **giao diện dữ liệu có người dùng khác phụ thuộc**. Vì vậy, khi đặt tên và chọn payload, phải xét:

1. **Ngữ nghĩa ổn định:** consumer hiểu rõ sự việc được công bố, điều kiện sự kiện được phát và liệu đây là sự kiện cuối cùng hay chỉ là một mốc trong quy trình.
2. **Hợp đồng dữ liệu:** event name, version, định danh thông điệp, subject, thời điểm, trường bắt buộc/tùy chọn, enum, tiền tệ và đơn vị đo.
3. **Quyền chia sẻ:** không xuất bản thông tin nội bộ, hồ sơ cá nhân hoặc thông tin bí mật nếu consumer không cần.
4. **Tương thích:** bên phát có thể thay đổi DB nội bộ mà không buộc mọi consumer sửa ngay.
5. **Giao hàng:** cần quy định idempotency, retry, khả năng đến muộn, thứ tự theo khóa nào và cách xử lý lỗi.

Ví dụ thông điệp tích hợp được chuyển đổi từ domain event ở trên:

~~~json
{
  "message_id": "c8d3d1cf-dc59-4ccd-8ff7-50489db160a7",
  "event_type": "OrderShipmentConfirmed",
  "schema_version": 1,
  "occurred_at": "2026-11-20T03:05:00Z",
  "published_at": "2026-11-20T03:05:04Z",
  "subject": {
    "type": "Order",
    "id": "ORD-842"
  },
  "data": {
    "order_id": "ORD-842",
    "shipment_id": "SHP-331",
    "carrier_code": "CARRIER-07",
    "handover_at": "2026-11-20T03:05:00Z"
  }
}
~~~

Thông điệp không nhất thiết chứa `actor_id`, `warehouse_id` hoặc mã biên bản nội bộ nếu các consumer không được phép hoặc không cần biết. `message_id` là định danh của thông điệp giao tiếp; có thể sử dụng cùng ID domain event nếu thiết kế công bố một-một, nhưng **không bắt buộc** và cần quy tắc nhất quán khi retry. `published_at` do thành phần xuất bản gán; trong một hệ thống outbox, một bản ghi outbox có thể tồn tại trước khi message thực sự được phát.

### Không yêu cầu ánh xạ một-một

Domain event và integration event không nhất thiết tương ứng một-một:

- Một domain event có thể tạo **nhiều** integration event theo nhóm consumer hoặc hợp đồng khác nhau.
- Nhiều thay đổi nội bộ có thể chỉ tạo **một** sự kiện công bố kết quả tổng hợp, khi quy trình đạt điểm chốt rõ ràng.
- Một số domain event **không được công bố** ra ngoài, ví dụ đánh giá rủi ro nội bộ.
- Một integration event có thể phản ánh kết quả của quy trình phối hợp qua nhiều miền; cần xác định chủ thể công bố có thẩm quyền và điều kiện chốt.

Cách làm này giảm phụ thuộc giữa mô hình dữ liệu nội bộ và hợp đồng bên ngoài. Chẳng hạn thay bảng `orders` thành `orders` + `shipments` có thể không làm thay đổi ý nghĩa `OrderShipmentConfirmed.v1`, nếu dữ liệu và cam kết của hợp đồng vẫn được đáp ứng.

## 5. Storage change record và CDC: mô tả điều cơ sở dữ liệu đã ghi

**Change Data Capture (CDC)** là cơ chế thu nhận các thay đổi dữ liệu, thường từ transaction log (ví dụ WAL hoặc binlog), đôi khi từ trigger hoặc kỹ thuật khác. Nó có thể cho biết **bảng nào, khóa hàng nào, thao tác INSERT/UPDATE/DELETE nào** đã được hệ lưu trữ ghi nhận, cùng metadata vị trí trong log và ảnh dữ liệu trước/sau nếu nguồn/cấu hình hỗ trợ.

Ví dụ sau là **biểu diễn đơn giản hóa, không phải định dạng chuẩn của mọi công cụ CDC**:

~~~json
{
  "source": "orders-db",
  "table": "orders",
  "operation": "UPDATE",
  "primary_key": {
    "order_id": "ORD-842"
  },
  "before": {
    "fulfillment_status": "READY",
    "shipment_id": null
  },
  "after": {
    "fulfillment_status": "SHIPPED",
    "shipment_id": "SHP-331"
  },
  "transaction_position": "illustrative-log-position-1904"
}
~~~

Tùy hệ quản trị và công cụ, CDC có thể chỉ cung cấp **after image**, `before` một phần hoặc không có `before`; một số công cụ phát các **snapshot record** khi khởi tạo đồng bộ. Snapshot đọc một hàng hiện có **không có nghĩa** doanh nghiệp vừa tạo đối tượng đó tại thời điểm snapshot. Offset/log position chỉ mang ý nghĩa trong bối cảnh nguồn cụ thể, không nên suy ra timestamp nghiệp vụ hoặc thứ tự toàn hệ thống.

### Vì sao CDC khác domain event?

Một thao tác cập nhật `fulfillment_status = SHIPPED` không cho biết sự thay đổi này là:

- Bàn giao thành công theo nghiệp vụ;
- Nhân viên sửa sai dữ liệu;
- Batch job đồng bộ từ hệ thống cũ;
- Tác vụ nhập lại snapshot;
- Hoặc một bước kỹ thuật chưa hoàn thành điều kiện của quy trình.

Chỉ từ giá trị trước/sau của cột không đủ suy ra **ý nghĩa** và **lý do**. Nếu cần biết đã bàn giao với biên bản nào, ai xác nhận và khi nào sự việc xảy ra, dữ liệu đó phải được mô hình hóa ở đúng nơi nguồn dữ liệu có thể xác thực.

CDC vẫn rất hữu ích cho đồng bộ kho dữ liệu, xây chỉ mục tìm kiếm, cấp dữ liệu cho hệ phân tích hoặc truyền **outbox**. Nhưng nếu consumer nhận trực tiếp CDC của bảng nghiệp vụ, họ bị ràng buộc vào tên bảng, cấu trúc cột, thao tác migration và dữ liệu nội bộ. Đây là đánh đổi phải chấp nhận có chủ đích.

### Còn audit log thì sao?

**Audit log** thường hướng đến câu hỏi ai sửa gì, lúc nào, từ giá trị nào sang giá trị nào, và theo quyền hạn nào. Audit log có thể được tạo bởi ứng dụng hoặc database, có một số trường giống CDC nhưng mục tiêu là truy vết trách nhiệm và tuân thủ. Audit log không mặc nhiên là domain event, cũng không nhất thiết đủ dữ liệu để replay toàn bộ trạng thái nghiệp vụ. CDC có thể hỗ trợ xây audit log, nhưng các yêu cầu về danh tính, toàn vẹn, bằng chứng và thời hạn lưu trữ thường cần thiết kế bổ sung.

## 6. Nhìn cả ba trong một luồng nghiệp vụ

Sơ đồ logic dưới đây mô tả **một phương án thực hiện**, không phải quy trình bắt buộc cho mọi kiến trúc:

~~~mermaid
flowchart TD
    C["Command: ConfirmHandover"] --> D["Logic nghiệp vụ Order/Shipment"]
    D --> V{"Ràng buộc hợp lệ?"}
    V -->|Không| X["Từ chối command"]
    V -->|Có| E["Domain event: OrderHandedToCarrier"]
    E --> TX["Giao dịch DB: cập nhật trạng thái + ghi outbox"]
    TX --> WAL["Transaction log của DB"]
    TX --> O["Outbox row đã commit"]
    O --> P["Publisher / relay"]
    WAL -.-> P
    P --> I["Integration event: OrderShipmentConfirmed"]
    I --> N["Notification service"]
    I --> A["Analytics / downstream services"]
~~~

Trong sơ đồ, đường nét đứt từ transaction log đến relay chỉ một **cách triển khai**: CDC có thể theo dõi thay đổi của bảng outbox để kích hoạt xuất bản. Relay cũng có thể tự đọc bảng outbox. CDC còn có thể thu nhận thay đổi của bảng `orders` riêng phục vụ đồng bộ dữ liệu; luồng này khác mục đích với phát thông điệp tích hợp. Không coi một message phát thành công là bằng chứng mọi consumer đã xử lý xong.

### Quy tắc nhất quán cần xác định

Nếu ghi bảng `orders` thành công nhưng tiến trình chết trước khi gửi message trực tiếp, các hệ thống khác có thể không bao giờ biết trạng thái đã đổi. Nếu gửi trước khi commit, một message có thể mô tả thay đổi cuối cùng không được ghi. Đây là vấn đề **dual write**.

**Transactional outbox** khắc phục phần “ghi dữ liệu và ghi ý định phát” trong cùng database transaction. Relay sau đó phát các thông điệp chưa gửi. Việc relay gửi lặp khi retry vẫn có thể xảy ra, nên consumer phải xử lý idempotent. Hệ thống không nên khẳng định bảo đảm “exactly once” xuyên suốt database, broker và mọi consumer chỉ dựa trên việc dùng outbox.

## 7. Ví dụ thiết kế vật lý: trạng thái, outbox và CDC

Một hệ thống dùng trạng thái hiện hành làm nguồn sự thật có thể lưu bảng `orders` và một bảng `integration_outbox`. Thiết kế này **không bắt buộc event sourcing**:

~~~sql
CREATE TABLE orders (
    order_id             VARCHAR(64) PRIMARY KEY,
    fulfillment_status   VARCHAR(24) NOT NULL,
    shipment_id          VARCHAR(64),
    shipped_at           TIMESTAMPTZ,
    version              BIGINT NOT NULL DEFAULT 0
                         CHECK (version >= 0)
);

CREATE TABLE integration_outbox (
    message_id           UUID PRIMARY KEY,
    aggregate_id         VARCHAR(64) NOT NULL,
    aggregate_version    BIGINT NOT NULL CHECK (aggregate_version > 0),
    event_type           VARCHAR(100) NOT NULL,
    schema_version       SMALLINT NOT NULL CHECK (schema_version > 0),
    occurred_at          TIMESTAMPTZ NOT NULL,
    payload              JSONB NOT NULL
                         CHECK (jsonb_typeof(payload) = 'object'),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at         TIMESTAMPTZ,
    UNIQUE (aggregate_id, aggregate_version, event_type)
);

CREATE INDEX ix_outbox_pending
    ON integration_outbox (created_at, message_id)
    WHERE published_at IS NULL;
~~~

Bảng `integration_outbox` lưu **thông điệp dự kiến công bố**. Nó không tự chứa tất cả domain event, không nhất thiết đủ để dựng lại trạng thái đơn hàng và **không phải event store**. Trường `aggregate_version` trong ví dụ cần được tăng và kiểm tra atomically khi thay đổi đơn. Ràng buộc duy nhất bên trên giả định mỗi aggregate version chỉ phát tối đa một thông điệp của cùng `event_type`; nếu quy tắc phát cho phép nhiều thông điệp cùng loại, phải chọn khóa nghiệp vụ khác.

Luồng ghi trong một giao dịch:

~~~text
BEGIN TRANSACTION
  Đọc Order và kiểm tra version/lock trong cùng giao dịch
  Kiểm tra: status hiện tại cho phép bàn giao, chứng từ không trùng
  UPDATE orders:
    fulfillment_status = SHIPPED
    shipment_id = SHP-331
    shipped_at = occurred_at hợp lệ
    version = version + 1
  INSERT integration_outbox:
    message_id ổn định cho lần công bố này
    event_type = OrderShipmentConfirmed
    payload theo schema_version = 1
COMMIT
~~~

Nếu có cập nhật đồng thời, dùng `SELECT ... FOR UPDATE` hoặc câu lệnh `UPDATE ... WHERE version = expected_version` và kiểm tra số hàng cập nhật; một thao tác thất bại phải được đánh giá lại theo trạng thái mới. Cơ chế chống gửi trùng command có thể cần thêm **idempotency key** riêng, ví dụ ràng buộc duy nhất theo `source_system` và `handover_receipt_id`. Một `UNIQUE` theo version không thay thế hoàn toàn quy tắc nghiệp vụ về trùng chứng từ.

Sau commit:

1. Relay đọc bản ghi outbox chưa công bố, hoặc công cụ CDC nhận thao tác `INSERT` trên bảng outbox.
2. Relay gửi payload dưới hợp đồng `OrderShipmentConfirmed.v1` đến broker hoặc API đích.
3. Sau khi broker xác nhận nhận, relay đánh dấu `published_at` hoặc cập nhật checkpoint. Nếu relay chết giữa hai bước, message có thể được phát lại.
4. Consumer lưu `message_id` đã xử lý theo phạm vi cần thiết và cập nhật dữ liệu của mình trong giao dịch thích hợp, để phát lại không tạo tác dụng phụ lần hai.

Một hệ thống **event sourcing** có thiết kế khác: event stream của aggregate là nguồn sự thật, còn bảng `orders` (nếu có) là projection. Nó vẫn có thể dùng outbox/integration event/CDC; cần phân biệt nhiệm vụ từng bảng và trách nhiệm nhất quán.

### Thiết kế khóa và chỉ mục theo câu hỏi

- `orders.order_id`: định danh nghiệp vụ của đơn, phục vụ lấy trạng thái hiện tại nhanh.
- `orders.version`: kiểm soát tranh chấp; nếu thực thi update có `WHERE order_id = ? AND version = ?`, chỉ mục khóa chính thường đã đủ tìm hàng, không cần mặc định tạo chỉ mục riêng trên `version`.
- `integration_outbox.message_id`: định danh để deduplicate phía consumer; nếu broker có ID riêng, quy định quan hệ với ID này để retry nhất quán.
- `ix_outbox_pending`: hỗ trợ relay quét message chưa phát; chỉ mục cần xem lại khi tải ghi lớn hoặc dùng CDC theo transaction log.
- Chỉ mục phục vụ báo cáo nghiệp vụ nên đặt ở read model phù hợp, tránh coi outbox là kho phân tích lâu dài.

## 8. Mô hình dữ liệu và hợp đồng thay đổi theo cách khác nhau

**Schema nội bộ** có thể thay đổi vì tối ưu hóa truy vấn: tách bảng `orders` thành `orders` và `shipments`, đổi tên cột, phân vùng theo ngày hoặc chuyển đọc trạng thái sang document database. Một consumer tích hợp không nên phải sửa code chỉ vì các thay đổi vật lý đó.

**Domain event** thay đổi khi miền nghiệp vụ thực sự có khái niệm mới hoặc cần thêm dữ liệu để giải thích sự việc. Khi lưu event lâu dài, nên version schema để reader cũ và mới có thể khôi phục lịch sử. Nếu chỉ phát trong bộ nhớ, cơ chế tiến hóa có thể đơn giản hơn, nhưng logic nghiệp vụ vẫn cần xác định rõ nghĩa.

**Integration event** có vòng đời hợp đồng riêng. Ví dụ `OrderShipmentConfirmed.v2` có thể bổ sung `carrier_tracking_reference` mà không thay đổi ý nghĩa `OrderHandedToCarrier`. Bên phát cần chính sách tương thích: trường nào bắt buộc, trường nào tùy chọn, cách xử lý loại enum chưa biết, thời hạn giữ phiên bản cũ và cách thông báo thay đổi.

**CDC record** thường đổi theo schema và cấu hình của nguồn. Khi rename cột hoặc chuyển bảng, downstream CDC có thể cần cập nhật mapping và chiến lược snapshot, ngay cả khi nghiệp vụ không đổi. Với CDC từ outbox có schema kiểm soát, ảnh hưởng của migration bảng nghiệp vụ sẽ nhỏ hơn.

| Nhu cầu | Lựa chọn thường phù hợp | Điều phải xác minh |
| --- | --- | --- |
| Xử lý quy tắc “đã bàn giao, không thể bàn giao lại” | Domain event/logic aggregate với ràng buộc trạng thái. | Ranh giới nhất quán, cạnh tranh, idempotency. |
| Thông báo cho dịch vụ khách hàng về việc đơn đã giao vận | Integration event có hợp đồng được phiên bản hóa. | Khi nào được công bố, trường cần thiết, bảo mật, retry. |
| Đồng bộ bảng sang công cụ tìm kiếm hoặc kho phân tích | CDC hoặc pipeline thay đổi dữ liệu. | Độ trễ, schema drift, snapshot, upsert/delete. |
| Truy vấn lịch sử quyết định nghiệp vụ | Domain event được lưu bền vững hoặc audit nghiệp vụ thiết kế đủ nghĩa. | Thời gian, actor, nguyên nhân, tính toàn vẹn lịch sử. |
| Đảm bảo không mất message sau khi cập nhật state | Transactional outbox và relay. | Commit atomically, replay, deduplicate. |

## 9. Thứ tự, thời gian và dữ liệu đến muộn

Các trường thời gian rất dễ bị dùng sai nếu không xác định **đây là đồng hồ của ai**:

| Trường | Ý nghĩa |
| --- | --- |
| `occurred_at` | Thời điểm sự việc nghiệp vụ xảy ra theo nguồn được công nhận. |
| `recorded_at` | Thời điểm hệ thống nguồn lưu nhận sự kiện hoặc thay đổi. |
| `published_at` | Thời điểm message được phát/xác nhận phát theo định nghĩa của publisher. |
| `consumed_at` | Thời điểm consumer xử lý hoặc ghi nhận thông điệp. |
| `source_position` / `offset` | Vị trí thay đổi hoặc message trong log/partition cụ thể, không phải ngày giờ nghiệp vụ. |

Ví dụ tài xế bàn giao hàng lúc **10:05**, thiết bị offline đồng bộ lúc **10:20**, outbox relay phát lúc **10:21** và hệ thống phân tích tiêu thụ lúc **10:22**. Nếu báo cáo thời gian bàn giao theo `published_at`, số liệu bị lệch 16 phút. Nếu đồng hồ thiết bị không đáng tin cậy, nghiệp vụ phải quy định bằng chứng đối chiếu và mức tin cậy; không thể tự biến timestamp nguồn thành sự thật tuyệt đối.

Thứ tự trong domain event stream có thể là `aggregate_version`; thứ tự của bản ghi CDC có thể là log sequence/transaction position; broker có thể chỉ đảm bảo thứ tự **trong một partition**. Chúng phục vụ những phạm vi khác nhau. Đừng dựa vào timestamp hoặc offset của một hệ thống để kết luận thứ tự mọi sự kiện giữa nhiều dịch vụ.

Khi một bản ghi đến muộn, projection cần xử lý theo khóa, phiên bản và quy tắc nghiệp vụ. Với thông điệp ít nhất một lần (*at least once*), tiêu thụ idempotent là yêu cầu thực tế; chỉ có `message_id` trong payload chưa đủ nếu không có cơ chế ghi nhớ ID đã xử lý cùng thao tác cập nhật.

## 10. Các lỗi thiết kế thường gặp và cách sửa

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Phát `OrderUpdated` cho mọi lần thay đổi | Consumer không biết ý nghĩa thay đổi. | Công bố event nghiệp vụ tại mốc đã được xác nhận. |
| Dùng `status: SHIPPED` từ CDC để khẳng định tài xế đã nhận hàng | Có thể là đồng bộ/sửa tay và thiếu bằng chứng. | Định nghĩa `OrderHandedToCarrier`, chứng từ, nguồn xác nhận và quy tắc chuyển trạng thái. |
| Đưa nguyên hàng database vào integration payload | Lộ dữ liệu nội bộ, schema bị ràng buộc chặt. | Dùng DTO/hợp đồng riêng, chỉ công bố trường cần thiết. |
| Ghi DB rồi gửi message trong thao tác độc lập không bảo vệ lỗi giữa chừng | DB và consumer khác trạng thái, có thể mất thông báo. | Dùng outbox hoặc cơ chế bảo đảm tương đương theo kiến trúc. |
| Xem outbox là event sourcing | Không thể replay đầy đủ vì chỉ lưu thông điệp ra ngoài. | Tách rõ nguồn sự thật, event store và outbox nếu cần cả ba. |
| Dùng cùng một event name cho các mức “đề nghị”, “được duyệt”, “đã hoàn tất” | Hệ thống báo kết quả thành công quá sớm. | Đặt event theo điều kiện chốt riêng của từng mốc. |
| Giả định mỗi lần phát broker là một sự kiện mới | Retry làm nhân đôi doanh số/số lượt giao. | ID ổn định, idempotent consumer và khóa chống lặp. |
| Xem CDC snapshot là một `OrderCreated` mới | Tính sai thời điểm tạo và số lượng sự kiện. | Phân biệt snapshot/load với lịch sử nghiệp vụ thực tế. |
| Xem `schema_version` là đủ để bảo đảm tương thích | Consumer vỡ khi đổi nghĩa trường hoặc enum. | Định nghĩa quy tắc tiến hóa và kiểm tra hợp đồng thực tế. |

Khi xử lý dữ liệu nhạy cảm, cả ba luồng đều phải tuân thủ phân quyền, thời hạn lưu trữ và chính sách xóa/ẩn danh. CDC có thể sao chép dữ liệu cá nhân sang nhiều nơi; integration event có thể tồn tại trong queue và log; domain event được lưu lâu dài có thể gây khó khăn khi cần xóa dữ liệu. Ngay từ lúc thiết kế, hãy cân nhắc ID tham chiếu, trường dữ liệu tối thiểu, mã hóa và phạm vi truy cập.

## 11. Bài tập chuyển yêu cầu sang mô hình dữ liệu

**Tình huống:** nền tảng học trực tuyến có dịch vụ `Enrollment` và `Billing`. Sau khi học viên thanh toán, hệ thống kích hoạt quyền truy cập khóa học và gửi thông báo. Kho phân tích cũng muốn đồng bộ mọi thay đổi đăng ký.

Các sự việc quan sát được:

- API nhận lệnh thanh toán nhưng cổng thanh toán chưa xác nhận.
- Cổng thanh toán xác nhận giao dịch thành công.
- Bảng `payments` đổi `payment_status` từ `PENDING` sang `CAPTURED`.
- Dịch vụ `Enrollment` kích hoạt quyền học cho một khóa học cụ thể.
- Bảng `enrollments` đổi `access_status` từ `INACTIVE` sang `ACTIVE`.
- Dịch vụ `Enrollment` phát thông điệp cho `Notification` để gửi email chào mừng.

**Yêu cầu thực hành:**

1. Phân loại từng dòng thành **command, domain event, integration event, CDC record hoặc hành động xử lý**. Một diễn tiến có thể tạo nhiều loại bản ghi; hãy phân biệt bản chất thay vì gán tùy tiện.
2. Đề xuất tên hai domain event có ý nghĩa, chẳng hạn `PaymentCaptured` và `EnrollmentActivated`. Xác định aggregate, subject, điều kiện phát và thời điểm có thẩm quyền của mỗi event.
3. Thiết kế thông điệp tích hợp `EnrollmentActivated.v1` đủ cho Notification (ID học viên, ID khóa học, thời điểm kích hoạt, message ID), nhưng hạn chế dữ liệu thanh toán và thông tin cá nhân không cần thiết.
4. Vẽ ranh giới transaction của `Enrollment`: ghi trạng thái và outbox trong cùng giao dịch; trình bày cách không cấp quyền học hai lần nếu thông điệp thanh toán đến lặp.
5. Đề xuất pipeline CDC của bảng `enrollments` sang kho phân tích. Trình bày cách xử lý snapshot khởi tạo, INSERT/UPDATE/DELETE, schema migration và dữ liệu đến muộn.
6. Chỉ ra vì sao `UPDATE payments.payment_status` một mình chưa đủ bằng chứng để khẳng định mọi quyền học đã được kích hoạt.

**Tiêu chí tự kiểm chứng:** mô hình phải phân biệt rõ sự thật nghiệp vụ với thay đổi vật lý; xác định nguồn sự thật và ranh giới sở hữu; dữ liệu hợp đồng tích hợp không phụ thuộc trực tiếp schema bảng; xử lý được retry, đồng thời và đến muộn; và cho phép thay đổi cấu trúc lưu trữ mà không buộc consumer công khai đổi theo.

**Ghi nhớ:** domain event cho biết **sự việc gì đã thực sự xảy ra** trong miền; integration event cho biết **sự thật/kết quả nào được cam kết chia sẻ** giữa các hệ thống; CDC cho biết **dữ liệu đã thay đổi ra sao** trong hệ lưu trữ. Tách các mục đích này giúp chọn cấu trúc quan hệ, document, event stream hay kho phân tích đúng với nghiệp vụ, có ràng buộc rõ và có thể kiểm chứng.
