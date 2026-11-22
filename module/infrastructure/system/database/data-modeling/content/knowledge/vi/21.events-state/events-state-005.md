# Định danh luồng, thứ tự phiên bản và cập nhật đồng thời

## 1. Vì sao ba quyết định này là nền móng của mô hình sự kiện?

Một hệ thống có thể lưu đầy đủ sự kiện `OrderPlaced`, `OrderPaid`, `OrderCancelled` và `OrderShipped` nhưng vẫn cho ra trạng thái sai nếu không biết **sự kiện thuộc luồng nào**, **sự kiện nào đi trước trong luồng đó** và **hai yêu cầu đến đồng thời được chấp nhận theo thứ tự nào**.

Ví dụ, hai nhân viên cùng mở đơn `ORD-842` khi đơn ở trạng thái `READY`:

- Nhân viên A gửi lệnh `CancelOrder` vì khách đổi ý.
- Nhân viên B gửi lệnh `ConfirmShipment` vì hàng vừa được bàn giao.

Cả hai đều nhìn thấy trạng thái cũ và có thể tin rằng thao tác của mình hợp lệ. Nếu hệ thống chỉ đọc trạng thái rồi tự thêm sự kiện mà không kiểm soát phiên bản, nó có nguy cơ ghi cả `OrderCancelled` và `OrderShipped` trong một diễn tiến trái quy tắc.

Để thiết kế dữ liệu đúng, cần phân biệt ba lớp:

| Câu hỏi | Cơ chế đáp ứng | Tác dụng |
| --- | --- | --- |
| **Dữ liệu thuộc đối tượng nào?** | Stream identity (định danh luồng). | Quy định ranh giới lịch sử và các bất biến áp dụng. |
| **Diễn tiến nào đã được chấp nhận?** | Version/sequence tăng theo luồng. | Cho phép replay đúng thứ tự và phát hiện sự kiện thiếu/lặp. |
| **Ai được ghi tiếp khi có cạnh tranh?** | Expected version, khóa hoặc giao dịch phù hợp. | Ngăn ghi đè logic và quyết định dựa trên trạng thái lỗi thời. |

Ba lớp này gắn trực tiếp với yêu cầu chuyển quy tắc nghiệp vụ thành **aggregate, khóa chính, ràng buộc duy nhất, chỉ mục và transaction**. Chúng đặc biệt quan trọng với event sourcing, nhưng nhiều nguyên tắc cũng áp dụng cho state + audit log, document versioning và các mô hình đồng bộ thay đổi.

## 2. Định danh luồng: một sự kiện phải thuộc đúng ranh giới nghiệp vụ

**Event stream** là dãy sự kiện đã được chấp nhận của một đối tượng hoặc aggregate theo một thứ tự logic xác định. Thường chọn khóa luồng là tổ hợp:

~~~text
stream_key = (tenant_id, aggregate_type, aggregate_id)
~~~

Ví dụ:

~~~text
(tenant-hcm, Order, ORD-842)      -> luồng đơn hàng
(tenant-hcm, Payment, PAY-590)    -> luồng thanh toán
(tenant-dn,  Order, ORD-842)      -> đơn khác, nếu ID chỉ duy nhất trong tenant
~~~

Định danh `ORD-842` **không tự đủ** khi nhiều loại aggregate dùng cùng định dạng ID hoặc nhiều tenant có ID trùng. Nếu toàn hệ thống đã dùng UUID duy nhất toàn cục và chỉ một loại aggregate, khóa đơn giản hơn có thể hợp lệ; vẫn cần ghi rõ quy ước, thay vì tự suy từ tên cột.

### Stream khác event, command và correlation

| Định danh | Đại diện cho | Phạm vi/ý nghĩa |
| --- | --- | --- |
| `stream_key` | Đối tượng sở hữu lịch sử sự kiện. | Dùng gom nhóm, bảo vệ bất biến và replay. |
| `event_id` | **Một sự kiện đã ghi**. | Thường duy nhất toàn event store; dùng truy vết và khử lặp event. |
| `stream_version` | Vị trí của một event trong một stream. | Duy nhất theo stream; không phải số thứ tự toàn hệ thống. |
| `command_id` / `idempotency_key` | Một ý định xử lý có thể được gửi lại. | Phạm vi chống lặp được quy định theo người gọi/tenant/thao tác. |
| `correlation_id` | Một tiến trình gồm nhiều bước. | Có thể nối các stream, dịch vụ, message. |
| `causation_id` | Hành động/thông điệp trực tiếp tạo ra event. | Hỗ trợ truy nguyên nguyên nhân, không quy định thứ tự toàn cục. |
| `schema_version` | Phiên bản cấu trúc của **loại event**. | Không tăng theo số event trong stream. |

Một command có thể tạo **0, 1 hoặc nhiều event**. Một sự kiện có thể được phát lại cho nhiều consumer. Một correlation có thể nối hàng trăm event thuộc nhiều stream. Vì vậy không dùng `command_id`, `event_id` hoặc `correlation_id` làm thay thế tùy tiện cho `stream_key`.

### Chọn ranh giới aggregate từ bất biến

Nếu quy tắc là “một đơn không được vừa hủy vừa xác nhận bàn giao”, việc xác nhận hai hành động phải được tuần tự hóa **trong cùng ranh giới kiểm tra quy tắc**. Luồng `Order` có thể phù hợp.

Nếu một đơn gồm nhiều kiện, mỗi kiện có lịch vận chuyển độc lập, có thể cần luồng `Shipment` cho từng kiện. Khi đó không được giả định một khóa luồng `Order` tự động bảo vệ tất cả bất biến của nhiều `Shipment`; phải thiết kế phối hợp hoặc thay đổi ranh giới dữ liệu.

**Nguyên tắc:** chọn aggregate và stream trước từ quy tắc nhất quán, rồi mới quyết định bảng, document, phân vùng và chỉ mục. Tổ chức luồng theo “một luồng cho mọi sự kiện của hệ thống” thường gây điểm nóng ghi và làm mờ ranh giới nghiệp vụ; tổ chức quá nhỏ có thể khiến bất biến bắt buộc trải nhiều transaction.

## 3. Thứ tự phiên bản: cái gì được bảo đảm và cái gì không?

Giả sử event store đã nhận các sự kiện cho `ORD-842`:

| stream_version | event_type | Ý nghĩa |
| ---: | --- | --- |
| 1 | `OrderPlaced` | Đơn được tạo. |
| 2 | `PaymentCaptured` | Tiền được thu thành công. |
| 3 | `OrderPrepared` | Hàng đã được chuẩn bị. |
| 4 | `OrderReadyForShipment` | Sẵn sàng bàn giao. |
| 5 | `OrderCancelled` | Đơn bị hủy hợp lệ. |

Một quy ước đơn giản là stream mới bắt đầu ở **version 0** (chưa có sự kiện); sự kiện đầu tiên mang version 1. Mỗi lần append một event, version tăng 1. Nếu một command hợp lệ sinh ba event, nó chiếm ba version liên tiếp. Cần quy định quy tắc rõ và giữ nhất quán trong toàn hệ thống.

Những ý nghĩa cần tách:

- **`stream_version`:** thứ tự nghiệp vụ đã được chấp nhận **trong stream**. Nó là trục chính cho replay aggregate và phát hiện khoảng trống.
- **`schema_version`:** số phiên bản payload của `event_type`, ví dụ `PaymentCaptured.v2`. Một stream ở version 87 vẫn có event schema version 1.
- **`occurred_at`:** thời điểm sự việc xảy ra theo nguồn được công nhận; có thể sớm hơn event đã ghi trước do thông tin đến muộn.
- **`recorded_at`:** thời điểm event được ghi nhận vào store; không nên dùng thay version để kiểm tra cập nhật đồng thời.
- **Global offset, transaction log position hoặc broker offset:** vị trí trong một hệ lưu trữ/log/partition cụ thể. Không mặc nhiên thể hiện thứ tự commit hoặc nhân quả trên mọi stream và dịch vụ.

**Không nên chỉ `ORDER BY occurred_at` để replay một aggregate.** Hai event có thể cùng timestamp; đồng hồ nguồn có thể sai; thông báo về một sự việc cũ có thể được xử lý muộn. Thứ tự apply là thứ tự được event store cam kết trong stream, còn thời điểm nghiệp vụ phục vụ phân tích và diễn giải riêng.

### Vì sao version không được có lỗ hổng trong một stream hoàn chỉnh?

Nếu luồng có `1, 2, 4` mà thiếu `3`, projection không thể biết event 3 bị mất, chưa đến hay bị xóa. Với hệ sử dụng version liên tiếp, event store phải **ghi version và event atomically**, không commit `current_version = 4` khi version 3 chưa có.

Khoảng trống có thể xuất hiện trong **global sequence** sinh bằng database sequence do rollback hoặc phân phối, nhưng điều đó không đồng nghĩa có event bị mất; không nên áp dụng yêu cầu “không gap” từ version trong một stream lên mọi ID toàn hệ thống.

## 4. Cập nhật đồng thời: lost update ở mức nghiệp vụ

Ví dụ luồng đơn đang ở version 4, trạng thái `READY`. Hai command được gửi gần như cùng lúc:

~~~text
T0: Order ORD-842 đang ở version 4, status=READY

A đọc version 4                B đọc version 4
A kiểm tra CancelOrder          B kiểm tra ConfirmShipment
A định append OrderCancelled    B định append OrderShipped
~~~

Nếu cả hai đều append dựa trên bản đọc cũ mà không có kiểm tra phiên bản khi ghi, hệ thống có thể:

- Ghi hai sự kiện cùng `stream_version = 5`, làm replay mơ hồ.
- Tự đánh số 5 và 6 nhưng vẫn coi cả hai command hợp lệ theo trạng thái version 4; lịch sử sau cùng vi phạm quy tắc.
- Ghi sự kiện mà projection chỉ áp dụng một phần, khiến trạng thái khác sự thật trong log.

**Optimistic concurrency control (OCC)** giải quyết phần tranh chấp bằng **expected version**: command tuyên bố “tôi đã ra quyết định dựa trên stream version 4”. Append chỉ thành công nếu current version vẫn là 4 ở **thời điểm kiểm tra atomically với ghi**.

Một diễn tiến hợp lệ:

| Thời điểm | A: CancelOrder | B: ConfirmShipment |
| --- | --- | --- |
| Đọc ban đầu | Dựa trên version 4 | Dựa trên version 4 |
| Append | Thành công: ghi `OrderCancelled` version 5 | Thất bại: expected 4, thực tế 5 |
| Xử lý tiếp | Trả kết quả đã hủy | Nạp state version 5, đánh giá lại điều kiện; trong ví dụ phải từ chối bàn giao |
| Lịch sử | Version 1 đến 5 liên tiếp | Không thêm event `OrderShipped` trái quy tắc |

Nếu B giành quyền append trước và quy tắc cấm hủy sau bàn giao, A sẽ bị từ chối theo chiều ngược lại. Hệ thống không cam kết một actor luôn thắng; nó cam kết **mỗi lệnh chỉ được chấp nhận dựa trên state mới nhất tại điểm tuần tự hóa**.

### Expected version khác idempotency

Hai command **khác nhau** cùng expected version cần cơ chế tranh chấp. Một command **giống hệt được gửi lại** cần cơ chế nhận biết yêu cầu đã xử lý. Nếu client timeout ngay sau commit thành công rồi thử lại, phiên bản stream đã tăng, nhưng việc chỉ trả “version conflict” có thể khiến client không biết yêu cầu ban đầu thành công hay chưa. Cần lưu idempotency receipt hoặc một định danh nghiệp vụ duy nhất có thể đối chiếu.

## 5. Lược đồ PostgreSQL: khóa luồng và ràng buộc không trùng phiên bản

Một phương án lưu event sourcing bằng PostgreSQL sử dụng **hai bảng**: bảng giữ vị trí hiện tại của stream và bảng lưu sự kiện. Ở đây một tenant có thể có nhiều loại aggregate; khóa chính dùng cả ba thành phần.

~~~sql
CREATE TABLE event_stream (
    tenant_id        UUID NOT NULL,
    aggregate_type   VARCHAR(80) NOT NULL,
    aggregate_id     VARCHAR(100) NOT NULL,
    current_version  BIGINT NOT NULL DEFAULT 0
                     CHECK (current_version >= 0),
    PRIMARY KEY (tenant_id, aggregate_type, aggregate_id)
);

CREATE TABLE domain_event (
    event_id         UUID PRIMARY KEY,
    tenant_id        UUID NOT NULL,
    aggregate_type   VARCHAR(80) NOT NULL,
    aggregate_id     VARCHAR(100) NOT NULL,
    stream_version   BIGINT NOT NULL CHECK (stream_version > 0),
    event_type       VARCHAR(100) NOT NULL,
    schema_version   SMALLINT NOT NULL CHECK (schema_version > 0),
    occurred_at      TIMESTAMPTZ NOT NULL,
    recorded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    command_id       UUID,
    correlation_id   UUID,
    causation_id     UUID,
    payload          JSONB NOT NULL
                     CHECK (jsonb_typeof(payload) = 'object'),
    FOREIGN KEY (tenant_id, aggregate_type, aggregate_id)
        REFERENCES event_stream
        (tenant_id, aggregate_type, aggregate_id),
    UNIQUE (tenant_id, aggregate_type, aggregate_id, stream_version)
);

CREATE INDEX ix_domain_event_type_time
    ON domain_event (event_type, occurred_at);
~~~

Những điều được bảo đảm và chưa được bảo đảm:

- **Khóa chính `event_stream`:** không có hai dòng quản lý cùng một stream.
- **`UNIQUE(tenant_id, aggregate_type, aggregate_id, stream_version)`:** không có hai event đã commit ở một vị trí của stream. Ràng buộc này tạo chỉ mục phù hợp để đọc một luồng theo thứ tự version.
- **`PRIMARY KEY(event_id)`:** phân biệt từng event; định danh này không thay thế unique trên stream + version.
- **`FOREIGN KEY`:** event phải tham chiếu một stream tồn tại.
- **`CHECK(jsonb_typeof(payload) = 'object')`:** mới kiểm tra hình thức payload; chưa kiểm tra kiểu và ràng buộc của `OrderCancelled` hay `PaymentCaptured`.
- **`current_version` và dãy event nhất quán:** cần **quy trình giao dịch** bảo vệ; chỉ khai báo một cột counter chưa buộc mọi writer phải append đúng event tương ứng.
- **Chỉ mục phụ theo loại/thời gian:** chỉ hữu ích nếu thực sự có truy vấn theo `event_type` và khoảng thời gian. Kiểm tra workload trước khi thêm để tránh tăng chi phí ghi.

Việc append cần được kiểm soát tập trung qua một service/repository hoặc thủ tục có quyền ghi thích hợp. Nếu nhiều thành phần có quyền `UPDATE event_stream` độc lập với `INSERT domain_event`, bất biến về `current_version` vẫn có thể bị phá. Có thể bổ sung quyền truy cập, trigger hoặc kiểm tra ràng buộc ở tầng ghi tùy yêu cầu tin cậy.

### Ví dụ đọc một stream theo đúng thứ tự

~~~sql
SELECT stream_version, event_id, event_type,
       schema_version, occurred_at, payload
FROM domain_event
WHERE tenant_id = :tenant_id
  AND aggregate_type = 'Order'
  AND aggregate_id = :order_id
ORDER BY stream_version;
~~~

Câu lệnh minh họa dùng tham số `:tenant_id` và `:order_id` do ứng dụng truyền; nếu chạy trực tiếp bằng công cụ SQL cần cú pháp binding thích hợp.

## 6. Append có điều kiện trong một transaction

Cách dễ diễn giải nhất là khóa **dòng stream** trong transaction, nạp state mới nhất, kiểm tra command rồi ghi event cùng version tiếp theo.

~~~text
BEGIN;

-- Nếu stream mới, tạo dòng version=0 bằng thao tác
-- được bảo vệ bởi PRIMARY KEY và quy tắc khởi tạo aggregate.
INSERT INTO event_stream (
    tenant_id, aggregate_type, aggregate_id, current_version
)
VALUES (:tenant_id, 'Order', :order_id, 0)
ON CONFLICT DO NOTHING;

-- Khóa đúng stream; các writer cùng stream phải chờ nhau.
SELECT current_version
FROM event_stream
WHERE tenant_id = :tenant_id
  AND aggregate_type = 'Order'
  AND aggregate_id = :order_id
FOR UPDATE;

-- Ứng dụng kiểm tra current_version == expected_version,
-- nạp sự kiện/snapshot hợp lệ và áp dụng quy tắc nghiệp vụ.
-- Nếu không hợp lệ: ROLLBACK, không thêm event.

-- Giả sử current_version = :expected_version:
INSERT INTO domain_event (
    event_id, tenant_id, aggregate_type, aggregate_id,
    stream_version, event_type, schema_version, occurred_at, payload
)
VALUES (
    :event_id, :tenant_id, 'Order', :order_id,
    :expected_version + 1, 'OrderCancelled', 1, :occurred_at, :payload
);

UPDATE event_stream
SET current_version = :expected_version + 1
WHERE tenant_id = :tenant_id
  AND aggregate_type = 'Order'
  AND aggregate_id = :order_id;

COMMIT;
~~~

Đây là **mã minh họa SQL kết hợp các bước ứng dụng**, không phải một script độc lập có thể chạy không cần biến và câu lệnh kiểm tra. Điểm quan trọng là:

1. Phải **khóa trước khi đưa ra quyết định cuối cùng**. Đọc state ở ngoài transaction, chờ khóa rồi không kiểm tra lại là cách tạo ra quyết định dựa trên dữ liệu cũ.
2. Phiên bản kỳ vọng được so với phiên bản **đang được khóa**. Nếu khác, ứng dụng phải dừng hoặc nạp lại state và đánh giá lại command.
3. `INSERT domain_event` và `UPDATE event_stream` phải cùng transaction; lỗi ở một bước khiến toàn bộ rollback.
4. Với command sinh nhiều event, phân bổ một **dãy liên tiếp** `expected + 1` đến `expected + N`, rồi đặt `current_version = expected + N` trong cùng transaction.
5. Khi dùng stream mới, chỉ command khởi tạo hợp lệ mới được phép tạo lịch sử đầu tiên; việc `INSERT ... ON CONFLICT DO NOTHING` không thay kiểm tra nghiệp vụ. Hai lệnh khởi tạo cạnh tranh vẫn cần xử lý xung đột version hoặc trạng thái.

Một biến thể là **compare-and-swap**:

~~~sql
UPDATE event_stream
SET current_version = current_version + 1
WHERE tenant_id = :tenant_id
  AND aggregate_type = 'Order'
  AND aggregate_id = :order_id
  AND current_version = :expected_version
RETURNING current_version;
~~~

Nếu không có hàng được trả về, version đã thay đổi hoặc stream không tồn tại. Nếu có đúng một hàng, ứng dụng nhận được version mới để chèn event **trong cùng transaction**; nếu chèn thất bại phải rollback để counter không tăng một mình. Việc kiểm tra bất biến theo state mới nhất vẫn bắt buộc. Không kết luận command hợp lệ chỉ từ thành công của lệnh `UPDATE`.

### Khóa bi quan hay OCC?

| Cách làm | Ưu điểm | Đánh đổi |
| --- | --- | --- |
| **`SELECT ... FOR UPDATE`** | Tuần tự hóa thao tác trên một stream trong DB; dễ giải thích điểm kiểm tra state. | Writer phải chờ khóa; stream “nóng” gây nghẽn, cần giới hạn thời gian transaction. |
| **OCC bằng expected version** | Cho phép tính toán trước khi ghi; phát hiện xung đột rõ. | Dưới cạnh tranh cao có thể retry nhiều; phải kiểm tra lại bất biến trên state mới. |
| **Serializable transaction** | Có thể bảo vệ một số quy tắc phức tạp trên nhiều hàng khi thiết kế đúng. | Có thể gặp serialization failure, cần retry toàn transaction; không thay thế idempotency. |

Ngay cả khi dùng khóa bi quan, **expected version** vẫn hữu ích nếu command đến từ giao diện dựa trên state cũ: hệ thống có thể báo người dùng rằng đơn đã thay đổi, thay vì âm thầm áp dụng yêu cầu lên một phiên bản khác mà họ chưa xem.

## 7. Idempotency khi command bị gửi lại

Cập nhật đồng thời và gửi lặp là hai tình huống khác nhau. Trong một mạng thực tế, client có thể timeout sau khi event đã commit thành công, rồi tự gửi lại cùng request. Không có idempotency, request thứ hai có thể tạo event thứ hai hoặc bị từ chối theo version mới dù yêu cầu đầu đã thành công.

Một thiết kế hữu ích là giữ **command receipt** theo phạm vi nhận diện request:

~~~sql
CREATE TABLE command_receipt (
    tenant_id        UUID NOT NULL,
    caller_id        VARCHAR(100) NOT NULL,
    idempotency_key  VARCHAR(160) NOT NULL,
    request_hash     VARCHAR(128) NOT NULL,
    result           JSONB NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, caller_id, idempotency_key)
);
~~~

Luồng xử lý:

1. Tra receipt theo khóa đúng phạm vi. Nếu có và `request_hash` trùng, trả lại kết quả đã commit; nếu cùng khóa mà nội dung khác, trả lỗi xung đột.
2. Nếu chưa có, xử lý command và kiểm tra phiên bản. Lưu event, `current_version` và receipt **trong cùng transaction**, bảo đảm hoặc tất cả cùng commit hoặc không phần nào commit.
3. Hai request cùng khóa đến đồng thời phải được điều phối bằng ràng buộc `PRIMARY KEY`, khóa hoặc thao tác chiếm quyền xử lý tương đương. Request thua cuộc sau khi giao dịch kia commit đọc receipt và trả kết quả cũ; nếu giao dịch kia rollback thì có thể xử lý lại.
4. Nếu command tạo nhiều event, receipt gắn với **một command**, không ép `command_id` phải duy nhất trên từng event. Có thể lưu ID và dải version của các event đã tạo trong `result`.

`request_hash` phải được tính từ biểu diễn chuẩn của nội dung có nghĩa (và phạm vi thao tác) để tránh trường hợp cùng khóa được dùng cho hai lệnh khác nhau. Thời hạn lưu receipt cần phù hợp cửa sổ retry thực tế và yêu cầu nghiệp vụ; với giao dịch tài chính, có thể còn cần khóa nghiệp vụ duy nhất độc lập với receipt.

**Chống lặp ở consumer là vấn đề khác:** message có thể được broker phát nhiều lần. Consumer cần dùng `event_id` hoặc `stream_key + stream_version` để tránh cộng số dư, tăng số lượt hoặc gửi thông báo trùng, ngay cả khi command nguồn chỉ được ghi một lần.

## 8. Đọc, replay và projection khi event đến trễ hoặc sai thứ tự

Hàm xây trạng thái từ một stream nên có tính **tất định**:

~~~text
state = initial_state
for event in load_events(stream_key, order_by=stream_version):
    state = apply(state, upcast_if_needed(event))
return state
~~~

`apply` không nên gọi API ngoài, đọc đồng hồ hiện tại, phát thông báo hay truy vấn biểu phí hiện hành để tạo một quyết định mới. Nếu một giá trị ảnh hưởng state, event hoặc tham chiếu dữ liệu bất biến có phiên bản phải cho phép khôi phục cùng kết quả.

Một projector dùng `last_applied_version` có thể áp dụng quy tắc:

~~~text
incoming_version <= last_applied_version:
    bỏ qua sự kiện đã áp dụng hoặc kiểm tra sự nhất quán

incoming_version == last_applied_version + 1:
    áp dụng event
    cập nhật state và last_applied_version trong cùng transaction

incoming_version > last_applied_version + 1:
    thiếu một hoặc nhiều version
    tạm dừng stream này và lấy lại các event còn thiếu
~~~

Mặc dù event store lưu liên tục, **truyền thông điệp** có thể đến trễ, lặp hoặc đổi thứ tự do phân vùng, mạng và retry. Đừng chỉ dựa vào thứ tự nhận message. Cũng không được coi một event có `occurred_at` cũ là version cũ: `occurred_at` và `stream_version` trả lời hai câu hỏi khác nhau.

Ví dụ bảng read model:

~~~sql
CREATE TABLE order_current (
    tenant_id            UUID NOT NULL,
    order_id             VARCHAR(100) NOT NULL,
    order_status         VARCHAR(30) NOT NULL,
    last_applied_version BIGINT NOT NULL DEFAULT 0
                         CHECK (last_applied_version >= 0),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, order_id)
);
~~~

Khi xử lý `version = 6`, việc thay `order_status` và nâng `last_applied_version` lên 6 phải được ghi atomically. Nếu projector crash sau khi đổi trạng thái nhưng trước khi lưu checkpoint, cùng message có thể bị áp dụng lại và gây sai nếu thao tác là cộng dồn không idempotent. Dữ liệu của consumer cần ràng buộc hoặc transaction bảo vệ tình huống đó.

### Snapshot là mốc tối ưu, không phải nguồn sự thật thay thế

Nếu stream có hàng chục nghìn event, snapshot tại version `N` giúp replay từ `N + 1`. Snapshot phải ghi rõ `stream_key`, `stream_version`, phiên bản schema snapshot và được tạo từ chuỗi event nhất quán. Khi command cần state mới nhất, snapshot quá cũ phải được bù đủ event sau nó. Snapshot sai có thể xóa và xây lại từ event store; nếu không thể replay event lịch sử, bảo đảm này không còn đúng.

## 9. Ranh giới nhất quán: một stream không giải quyết mọi xung đột

Khóa `Order` bảo vệ quy tắc riêng của một đơn. Nhưng một số bất biến vượt khỏi một stream:

- **Tồn kho:** hai đơn khác nhau cùng đặt chiếc sản phẩm cuối cùng. Khóa từng `Order` riêng không bảo vệ tổng `available_stock`; cần một điểm nhất quán cho `InventoryItem`, reservation hoặc constraint nguồn.
- **Ghế sự kiện:** hai booking khác nhau không được chiếm cùng ghế. Cần khóa/unique constraint theo `event_id + seat_id` hoặc aggregate bảo vệ phân bổ ghế; chỉ version của từng `Booking` là chưa đủ.
- **Số dư ví:** hai lệnh chi tiêu từ hai nghiệp vụ không được làm số dư âm. Có thể cần ledger/aggregate `Wallet` hoặc kiểm soát giao dịch phù hợp trên cùng nguồn.
- **Quy trình nhiều dịch vụ:** thanh toán thành công và kho chưa xác nhận không được bị hiểu thành toàn bộ đơn đã hoàn tất. Cần sự kiện có ý nghĩa riêng cho từng nguồn, cơ chế phối hợp và bù trừ khi cần.

Đừng thay những bất biến xuyên stream bằng câu “broker sẽ gửi theo thứ tự”. Thứ tự message không biến các cập nhật ở hai database thành một giao dịch nguyên tử. Với giao dịch cục bộ nhiều hàng, có thể dùng khóa, unique constraint, isolation level phù hợp; với dịch vụ phân tán, sử dụng quy trình có trạng thái, idempotency và đối soát.

### Stream nóng và điểm nghẽn ghi

Một luồng nhận rất nhiều command mỗi giây (chẳng hạn “stream của toàn bộ người dùng”) sẽ tạo tranh chấp cao vì tất cả writer cần tuần tự hóa. Trước khi chia stream, xác định lại các bất biến: có thể tách theo account, order, instrument hoặc vị trí tồn kho không? Nếu tách, phải xác định chính sách nhất quán cho quy tắc xuyên ranh giới. Không chia chỉ để tăng throughput nếu điều đó làm mất khả năng bảo vệ nghiệp vụ.

## 10. Thiết kế vật lý và vận hành theo đặc tính truy vấn

Việc chọn cơ sở dữ liệu không thay đổi ý nghĩa của stream identity và version; nó thay đổi cách hiện thực ràng buộc:

| Mô hình lưu trữ | Cách thể hiện | Cần xác minh |
| --- | --- | --- |
| **Quan hệ** | Bảng event + khóa luồng/version + transaction, read model tách bảng. | Unique constraint, khóa, transaction, index, phân vùng và kế hoạch replay. |
| **Document** | Document aggregate có version và danh sách event, hoặc event là các document riêng. | Giới hạn kích thước document, atomic conditional update, thứ tự khi phân tán, indexing. |
| **Đồ thị** | Quan hệ nhân quả và liên kết các sự kiện/đối tượng dưới dạng nút/cạnh. | Thường là góc nhìn phục vụ phân tích quan hệ; cần quy tắc nguồn sự thật và commit riêng. |
| **Kho phân tích** | Bảng sự kiện đã làm sạch, dữ liệu theo thời gian và khóa phân vùng. | Độ trễ ingest, dữ liệu đến muộn, deduplicate và định nghĩa chỉ số. |

Trong PostgreSQL, `UNIQUE(tenant_id, aggregate_type, aggregate_id, stream_version)` đồng thời hỗ trợ tra cứu theo luồng và thứ tự. Chỉ thêm index khi truy vấn chứng minh cần thiết: số lượng index quá nhiều làm mỗi lần append tốn chi phí hơn. Nếu partition event store theo thời gian hoặc tenant, cần kiểm tra khả năng thực thi **unique toàn cục** theo cơ chế phân vùng của hệ quản trị; một thiết kế partition có thể yêu cầu khóa duy nhất gồm partition key, khiến ràng buộc `event_id`/version phải được điều chỉnh. Không coi việc thêm partition là thay đổi chỉ thuần hiệu năng.

Các chỉ số quan sát vận hành nên gồm: tỷ lệ xung đột version, độ trễ chờ khóa, số command retry, tỷ lệ lặp idempotency, độ trễ projection theo stream/partition, số event bị thiếu khi consumer áp dụng, thời gian replay và tỷ lệ bất nhất giữa projection với replay chuẩn.

### Quyền truy cập và bảo vệ dữ liệu

Event log thường giữ lịch sử lâu dài. Đặt `tenant_id` vào khóa và bộ lọc chưa đủ bảo đảm cách ly tenant nếu ứng dụng cho phép truy vấn thiếu điều kiện. Cần kiểm soát quyền ở tầng ứng dụng và database phù hợp; trong trường hợp yêu cầu nghiêm ngặt có thể dùng row-level security hoặc phân tách vật lý.

Hạn chế thông tin cá nhân trong payload; cân nhắc tham chiếu đến kho dữ liệu quản lý xóa/ẩn danh và lưu chỉ dữ kiện cần cho replay. Nguyên tắc append-only không loại bỏ nghĩa vụ lưu giữ có thời hạn, quyền sửa/xóa hợp pháp hay chính sách bảo mật.

## 11. Các sai lầm phổ biến khi triển khai

| Sai lầm | Tình huống lỗi | Cách xử lý |
| --- | --- | --- |
| Dùng timestamp làm version | Hai event cùng thời điểm hoặc event đến muộn. | Sequence logic riêng theo stream. |
| Dùng `MAX(stream_version)+1` ngoài transaction | Hai writer cùng thấy số lớn nhất giống nhau. | Khóa stream hoặc expected-version CAS trong transaction. |
| Dùng unique trên version nhưng vẫn xác nhận command theo state cũ | Một command bị ép sang version sau dù quy tắc không còn hợp lệ. | Nạp lại state và đánh giá lại bất biến khi xung đột. |
| Dùng `event_id` thay idempotency key của command | Retry tạo event ID mới, ghi lại cùng hành động. | Receipt/khóa nghiệp vụ chống lặp ở cấp command. |
| Dùng `schema_version` thay `stream_version` | Không thể xác định thứ tự event. | Version schema và version stream là hai cột khác nhau. |
| Cập nhật `current_version` ngoài transaction append | Counter chỉ đến event chưa tồn tại. | Ghi cả counter và event atomically. |
| Tin thứ tự nhận broker luôn đúng | Consumer nhận version 8 trước version 7. | Checkpoint per stream, phát hiện lỗ hổng và lấy lại event thiếu. |
| Dùng read model bất đồng bộ để kiểm tra bất biến tại ghi | Projection chậm dẫn đến chấp nhận điều kiện lỗi thời. | Kiểm tra theo nguồn sự thật và điểm tuần tự hóa hợp lệ. |
| Chỉ khóa từng order để bảo vệ tồn kho chung | Hai order giữ cùng một sản phẩm cuối. | Ranh giới inventory/reservation và constraint chung. |
| Mỗi lần retry đều áp dụng side effect | Thông báo hoặc hoàn tiền bị gửi hai lần. | Outbox, idempotency phía consumer và khóa nghiệp vụ nhà cung cấp. |

## 12. Bài tập: từ yêu cầu đặt vé đến khóa và transaction

**Tình huống:** một nền tảng đặt vé sự kiện có 200 ghế. Người dùng có thể giữ chỗ, thanh toán, hủy và đổi ghế. Hai thiết bị của cùng khách có thể gửi lệnh giữ chỗ đồng thời; dịch vụ thanh toán có thể gửi callback lặp. Hệ thống cần xem lịch sử mọi thay đổi của một booking và không cho hai người dùng giữ cùng ghế.

Hãy thực hiện:

1. **Định danh luồng:** đề xuất `stream_key` cho `Booking` và `SeatInventory` (hoặc một mô hình khác). Nêu trường nào cần `tenant_id`, trường nào cần `event_id`, `booking_id`, `seat_id`.
2. **Version:** lập diễn tiến 5 event cho một booking, bắt đầu version 1; phân biệt `stream_version` với `schema_version`.
3. **Cạnh tranh:** hai command `ReserveSeat` cùng dựa trên phiên bản 8 của cùng inventory/seat. Mô tả kết quả mong đợi khi một command thắng và command kia xung đột.
4. **Ràng buộc:** thiết kế khóa/unique constraint để cùng một ghế không thể được giữ bởi hai booking đang hiệu lực. Giải thích tại sao một unique thông thường chỉ theo `seat_id` có thể cản trở việc giữ lại ghế sau khi đã hủy; đề xuất bảng reservation hiện hành hoặc quy tắc phù hợp.
5. **Idempotency:** khi callback thanh toán gửi lại cùng `provider_payment_id`, chứng minh lịch sử chỉ có một lần thu tiền được xác nhận; nêu cách xử lý khi hai callback đến cùng thời điểm.
6. **Projection:** nêu cấu trúc read model cho màn hình đặt vé và quy tắc dùng `last_applied_version` khi version 11 đến trước version 10.
7. **Giới hạn:** xác định những bất biến nào nằm trong một stream, những bất biến nào cần một điểm nhất quán khác hoặc cơ chế điều phối xuyên dịch vụ.

**Tiêu chí kiểm chứng:**

- Cùng stream có phiên bản liên tiếp, không có hai event đã commit cùng version.
- Hai command tranh chấp không cùng được chấp nhận dựa trên state lỗi thời.
- Command gửi lặp không tạo sự kiện nghiệp vụ hoặc khoản tiền lần hai.
- Replay theo version cho kết quả tất định; projection phát hiện lặp và lỗ hổng.
- Kiểm tra tồn kho/ghế không bị “lọt” vì khóa chỉ bảo vệ từng booking.
- Lược đồ vật lý thể hiện đúng phạm vi khóa và đáp ứng truy vấn thực tế.

**Kết luận thiết kế:** `stream_key` cho biết lịch sử thuộc đối tượng nào; `stream_version` cho biết thứ tự những thay đổi được chấp nhận; transaction cùng expected-version/khóa giúp chỉ một tiến trình ghi được bước tiếp theo hợp lệ. Ba cơ chế này chỉ đáng tin khi gắn với **bất biến nghiệp vụ, idempotency và ranh giới nhất quán** được định nghĩa rõ từ yêu cầu ban đầu.
