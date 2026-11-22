# Lưu sự kiện làm nguồn dữ liệu (event sourcing) và giới hạn áp dụng

## 1. Event sourcing giải quyết bài toán gì?

Trong mô hình dữ liệu truyền thống, hệ thống thường lưu một bản ghi thể hiện **trạng thái mới nhất**. Chẳng hạn, bảng `rental_contract` có thể cho biết hợp đồng thuê thiết bị `RENT-204` đang ở trạng thái `CLOSED` và tiền cọc đã hoàn. Những giá trị này phục vụ tra cứu nhanh nhưng không tự giải thích đầy đủ **đã có những sự việc gì**, chúng diễn ra theo thứ tự nào và điều gì khiến hệ thống đi đến trạng thái hiện tại.

**Event sourcing** là một lựa chọn kiến trúc trong đó chuỗi **sự kiện đã được chấp nhận và lưu bền vững** trở thành **nguồn sự thật chính cho trạng thái của aggregate**. Thay vì lấy trạng thái cuối làm bản ghi chuẩn rồi chỉ bổ sung lịch sử, hệ thống khôi phục trạng thái bằng cách áp dụng các sự kiện theo thứ tự logic của chúng.

Nói ngắn gọn về quan hệ dữ liệu:

~~~text
Trạng thái hiện tại = fold(trạng thái ban đầu, các sự kiện đã lưu theo đúng thứ tự)
~~~

Ở đây, `fold` nghĩa là lần lượt áp dụng hàm chuyển trạng thái cho từng sự kiện. Một **projection** (hình chiếu dữ liệu) có thể vật hóa kết quả thành bảng trạng thái hiện hành, chỉ mục tìm kiếm hoặc bảng phân tích để đáp ứng truy vấn.

Phân biệt ba cách thiết kế:

| Cách thiết kế | Nguồn sự thật | Khả năng xem lại diễn tiến |
| --- | --- | --- |
| **State-only** | Bản ghi trạng thái hiện tại, thường được `UPDATE`. | Phụ thuộc vào lịch sử có được lưu ở nơi khác hay không. |
| **State + audit/event log** | Bản ghi trạng thái vẫn là chuẩn; log là dữ liệu bổ sung. | Có thể truy vết một phần hoặc nhiều thay đổi, nhưng log chưa chắc đủ để xây lại state. |
| **Event sourcing** | Chuỗi sự kiện được công nhận là nguồn sự thật cho aggregate; state là kết quả dẫn xuất. | Có thể replay nếu event, thứ tự và bộ diễn giải đầy đủ, còn tương thích. |

**Điểm quyết định không phải có bảng tên `events`, có Kafka hay có JSON.** Đó là việc **hệ thống coi dữ liệu nào là chuẩn khi cần phục hồi hoặc giải quyết bất đồng**. Nếu trạng thái chính thức nằm ở `rental_contract` và bảng sự kiện chỉ ghi thêm khi tiện, hệ thống chưa triển khai event sourcing nhất quán.

## 2. Ví dụ xuyên suốt: hoàn tất hợp đồng thuê thiết bị

Giả sử nghiệp vụ của dịch vụ thuê thiết bị yêu cầu:

- Biết khách đã lấy và trả thiết bị vào lúc nào, có gia hạn thời hạn trả hay không.
- Tính được tiền cọc đã thu, khoản phí phát sinh và tiền cọc đã hoàn.
- Giải thích vì sao hợp đồng đóng và ai/chủ thể nào phê duyệt nghiệm thu.
- Kiểm chứng không hoàn tiền vượt số tiền có thể hoàn.
- Có thể dựng lại trạng thái hợp đồng nếu bảng tra cứu bị mất hoặc logic báo cáo cần thay đổi.

Một **event stream** minh họa cho aggregate `Rental` với ID `RENT-204`:

| stream_version | Sự kiện | Dữ liệu nghiệp vụ trọng tâm |
| ---: | --- | --- |
| 1 | `RentalStarted` | Thiết bị, thời hạn trả, tiền cọc và đơn vị tiền tệ. |
| 2 | `DepositCaptured` | Số tiền đã thu và định danh giao dịch thanh toán. |
| 3 | `RentalDueDateExtended` | Thời hạn cũ, thời hạn mới, lý do được duyệt. |
| 4 | `EquipmentDroppedOff` | Thiết bị, điểm nhận và chứng từ bàn giao. |
| 5 | `EquipmentReturnAccepted` | Kết quả nghiệm thu, người xác nhận và thời điểm. |
| 6 | `DepositRefunded` | Số tiền thực tế đã hoàn và tham chiếu nhà thanh toán. |
| 7 | `RentalClosed` | Hợp đồng được đóng khi các điều kiện đã hoàn tất. |

Từ chuỗi này, hệ thống có thể tính `rental_status = CLOSED`, thời hạn trả cuối, số cọc đã thu, số cọc đã hoàn và các cột phục vụ màn hình khách hàng. Nhưng **event nào được chấp nhận** vẫn phải được xác định bởi quy tắc nghiệp vụ; ví dụ `DepositRefunded` chỉ phát sau khi nguồn có thẩm quyền xác nhận hoàn tiền thành công, không phải ngay khi nhân viên bấm “Hoàn cọc”.

Đây là một stream **theo hợp đồng**, nên `stream_version = 5` có nghĩa là sự kiện thứ năm đã được chấp nhận của `RENT-204`. Nó không đồng nghĩa sự kiện thứ năm trong toàn database, và không xác định thứ tự giữa hai hợp đồng khác nhau.

### Trạng thái được dựng lại như thế nào?

Giả sử state cần tính gồm:

~~~json
{
  "rental_id": "RENT-204",
  "status": "ACTIVE",
  "deposit_captured_minor": 0,
  "deposit_refunded_minor": 0,
  "due_at": null,
  "returned_at": null
}
~~~

Khi replay:

- `RentalStarted` đặt `status = ACTIVE`, thiết lập thời hạn trả và thông tin thiết bị.
- `DepositCaptured` làm tăng `deposit_captured_minor` theo khoản thu **đã xác nhận**, không tăng khi mới gửi yêu cầu thu.
- `RentalDueDateExtended` cập nhật thời hạn có hiệu lực theo giá trị được chấp thuận trong event.
- `EquipmentDroppedOff` ghi nhận thời điểm bàn giao; chưa mặc nhiên có nghĩa việc nghiệm thu đã đạt.
- `EquipmentReturnAccepted` đánh dấu thiết bị được chấp nhận trả sau kiểm tra.
- `DepositRefunded` làm tăng số tiền thực tế hoàn.
- `RentalClosed` chuyển sang `CLOSED` khi tất cả nghĩa vụ thuộc quy tắc đóng hợp đồng đã thỏa.

Nhiều trạng thái như “đang thuê”, “đã trả thiết bị”, “đã hoàn cọc” nên được mô hình hóa **thành các chiều riêng** khi nghiệp vụ có các bước độc lập. Một trường `status` duy nhất dễ khiến hệ thống bỏ mất thông tin tài chính hoặc vận hành.

## 3. Kiến trúc điển hình: command, event stream và read model

~~~mermaid
flowchart TD
    C["Command: AcceptEquipmentReturn"] --> V{"Kiểm tra bất biến & phiên bản Rental"}
    V -->|Không hợp lệ| R["Từ chối command"]
    V -->|Hợp lệ| E["Append EquipmentReturnAccepted"]
    E --> ES[("Event store - nguồn sự thật")]
    ES --> RE["Replay/fold theo stream_version"]
    RE --> S["State của Rental"]
    ES --> P["Projector / Consumer"]
    P --> RM[("Read model: rental_current")]
    P --> A[("Read model: lịch sử và phân tích")]
    ES --> O["Outbox / phát thông điệp cần thiết"]
    O --> I["Integration event cho dịch vụ khác"]
~~~

Đây là cấu trúc logic; triển khai vật lý có thể khác. Hệ thống xử lý command thường **nạp state** của aggregate bằng replay từ sự kiện, hoặc từ **snapshot hợp lệ + các sự kiện sau snapshot**, kiểm tra bất biến rồi append event mới. Các read model được tạo từ event để trả lời truy vấn hiệu quả.

Một số khái niệm cần tách rõ:

| Khái niệm | Trách nhiệm |
| --- | --- |
| **Command** | Yêu cầu thay đổi: `AcceptEquipmentReturn`; có thể bị từ chối. |
| **Domain event** | Sự thật nghiệp vụ sau khi được chấp nhận: `EquipmentReturnAccepted`. |
| **Aggregate** | Ranh giới áp dụng bất biến và thứ tự sự kiện, ví dụ `Rental`. |
| **Event store** | Lưu event bền vững, thứ tự và định danh để khôi phục state. |
| **Projection/read model** | Dữ liệu dẫn xuất phục vụ truy vấn, có thể tái tạo. |
| **Snapshot** | Trạng thái dẫn xuất tại một phiên bản stream đã xác định, nhằm giảm chi phí replay. |
| **Integration event** | Hợp đồng thông báo cho hệ thống khác; có thể được tạo từ domain event nhưng không bắt buộc giống hệt. |

**CQRS** (tách cách ghi và cách đọc) thường kết hợp tốt với event sourcing nhưng hai khái niệm độc lập. Một hệ thống có thể dùng CQRS mà vẫn lưu trạng thái là nguồn sự thật; hoặc dùng event sourcing với bộ đọc rất đơn giản. Broker và CDC cũng chỉ là phương tiện truyền/thay đổi dữ liệu, không tự thay thế event store.

## 4. Thiết kế hợp đồng của một sự kiện đủ dùng lâu dài

Một event trong kho sự kiện nên diễn đạt một **sự thật bất biến về nghiệp vụ**. Thông thường, metadata và payload cần đủ để xác định:

| Trường | Mục đích | Cảnh báo |
| --- | --- | --- |
| `event_id` | Định danh duy nhất cho một sự kiện đã ghi. | Dùng để truy vết/khử lặp khi tiêu thụ; không dùng thay phiên bản stream. |
| `aggregate_type`, `aggregate_id` | Xác định event stream của aggregate. | Định nghĩa rõ phạm vi tenant nếu ID chỉ duy nhất trong từng tenant. |
| `stream_version` | Số thứ tự logic của sự kiện trong một stream. | Phải duy nhất trong stream; không suy ra thứ tự toàn hệ thống. |
| `event_type` | Tên sự thật nghiệp vụ. | Tránh tên kỹ thuật như `RowUpdated`. |
| `schema_version` | Phiên bản cấu trúc của loại event. | Khác với `stream_version`. |
| `occurred_at` | Khi sự việc nghiệp vụ xảy ra theo nguồn xác nhận. | Có thể đến muộn hoặc chịu sai lệch đồng hồ nguồn. |
| `recorded_at` | Khi event được lưu trong event store. | Dùng giám sát độ trễ; không thay thế occurred_at. |
| `payload` | Dữ kiện cần diễn giải/khôi phục nghiệp vụ. | Tránh tham chiếu dữ liệu có thể thay đổi mà không có phiên bản phù hợp. |
| `correlation_id`, `causation_id` | Nối các bước cùng tiến trình và nguyên nhân trực tiếp. | Không thay thế aggregate ID hay khóa chống gửi lặp. |

Ví dụ `DepositRefunded`:

~~~json
{
  "event_id": "f615cb42-6f42-4b60-a0d5-4e57d45b44fb",
  "aggregate_type": "Rental",
  "aggregate_id": "RENT-204",
  "stream_version": 6,
  "event_type": "DepositRefunded",
  "schema_version": 1,
  "occurred_at": "2026-11-20T05:20:00Z",
  "recorded_at": "2026-11-20T05:20:03Z",
  "correlation_id": "1b21a7ce-a103-4d96-9499-9f8b1edfe286",
  "payload": {
    "refund_id": "REF-706",
    "payment_id": "PAY-903",
    "amount_minor": 400000,
    "currency": "VND",
    "provider_confirmation_id": "GATEWAY-888"
  }
}
~~~

`amount_minor` là số nguyên theo đơn vị tiền nhỏ nhất được quy định cho mã tiền tệ, tránh lỗi của số thực nhị phân. Các ID và thời điểm chỉ mang tính minh họa. Với nhiều loại tiền, quy tắc chuyển đổi đơn vị phải dựa trên mã tiền tương ứng.

**Tối thiểu nhưng đầy đủ:** nếu replay cần số tiền đã được phê duyệt, event phải chứa con số này hoặc một tham chiếu đến dữ liệu phiên bản **không đổi**. Chỉ lưu `refund_id` rồi đọc thông tin hiện tại từ dịch vụ thanh toán có thể làm replay cũ thay đổi kết quả. Ngược lại, không nên nhúng toàn bộ hồ sơ khách hàng vào event khi một ID là đủ; dữ liệu cá nhân lưu lâu dài làm tăng rủi ro về quyền riêng tư.

## 5. Thiết kế event store bằng cơ sở dữ liệu quan hệ

Event sourcing là **cách tổ chức nguồn sự thật**, không phải tên một sản phẩm database. PostgreSQL, một hệ lưu trữ tài liệu, hoặc event store chuyên dụng đều có thể đáp ứng nếu hỗ trợ các yêu cầu về ghi nhất quán, thứ tự per stream, đọc lịch sử, truy xuất và khôi phục.

Ví dụ dưới đây sử dụng PostgreSQL. Một bảng `event_stream` giữ phiên bản cuối để phối hợp ghi; `event_store` giữ lịch sử đã xác nhận. Trong hệ đa tenant, cần bổ sung tenant vào khóa và quyền truy cập nếu ID aggregate chỉ duy nhất trong từng tenant.

~~~sql
CREATE TABLE event_stream (
    aggregate_type  VARCHAR(80) NOT NULL,
    aggregate_id    VARCHAR(80) NOT NULL,
    current_version BIGINT NOT NULL DEFAULT 0
                    CHECK (current_version >= 0),
    PRIMARY KEY (aggregate_type, aggregate_id)
);

CREATE TABLE event_store (
    event_id        UUID PRIMARY KEY,
    aggregate_type  VARCHAR(80) NOT NULL,
    aggregate_id    VARCHAR(80) NOT NULL,
    stream_version  BIGINT NOT NULL CHECK (stream_version > 0),
    event_type      VARCHAR(100) NOT NULL,
    schema_version  SMALLINT NOT NULL CHECK (schema_version > 0),
    occurred_at     TIMESTAMPTZ NOT NULL,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    correlation_id  UUID,
    causation_id    UUID,
    payload         JSONB NOT NULL
                    CHECK (jsonb_typeof(payload) = 'object'),
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb
                    CHECK (jsonb_typeof(metadata) = 'object'),
    FOREIGN KEY (aggregate_type, aggregate_id)
        REFERENCES event_stream (aggregate_type, aggregate_id),
    UNIQUE (aggregate_type, aggregate_id, stream_version)
);

CREATE INDEX ix_event_store_type_time
    ON event_store (event_type, occurred_at);
~~~

**Giải thích ràng buộc:**

- `PRIMARY KEY(event_id)` giúp định danh event trên toàn kho theo giả định ID được sinh duy nhất.
- `UNIQUE(aggregate_type, aggregate_id, stream_version)` bảo đảm không thể có hai event ở cùng vị trí trong một stream. Chỉ mục của ràng buộc này cũng hỗ trợ đọc theo thứ tự phiên bản.
- `current_version` được cập nhật trong cùng transaction với các event mới, sau khi khóa stream hoặc so sánh phiên bản kỳ vọng. Nó giúp phát hiện hai command tranh nhau sửa cùng aggregate.
- Kiểm tra `jsonb_typeof(payload)` **chưa đủ** để bảo đảm một `DepositRefunded` có số tiền hợp lệ. Các schema theo `event_type + schema_version`, quy tắc số tiền và bất biến phải được xác minh trước khi append.
- Chỉ mục `(event_type, occurred_at)` hữu ích khi thường báo cáo theo loại và thời điểm; nó tăng chi phí ghi. Dựa vào workload và `EXPLAIN` trước khi thêm nhiều chỉ mục hoặc partition.

Đọc một stream:

~~~sql
SELECT event_id, stream_version, event_type,
       schema_version, occurred_at, payload
FROM event_store
WHERE aggregate_type = 'Rental'
  AND aggregate_id = 'RENT-204'
ORDER BY stream_version;
~~~

Với truy vấn dòng thời gian của một hợp đồng, `stream_version` xác định thứ tự logic đã được hệ thống chấp nhận. Không nên chỉ `ORDER BY occurred_at`: một sự kiện từ đối tác có thể đến muộn, có đồng hồ sai hoặc có thời điểm nghiệp vụ sớm hơn dù được chấp nhận vào stream sau.

### Ghi đồng thời: một stream phải có một chuỗi hợp lệ

Khi hai command cùng thấy `current_version = 4`, cả hai không được tự ghi “sự kiện 5” thành công độc lập. Có thể chọn khóa dòng hoặc optimistic concurrency:

1. Khởi tạo hàng `event_stream` nếu aggregate mới; xử lý xung đột tạo đồng thời bằng khóa chính.
2. Trong transaction, dùng `SELECT ... FOR UPDATE` để khóa hàng stream, hoặc `UPDATE ... WHERE current_version = expected_version` và kiểm tra số hàng cập nhật.
3. Đọc state phù hợp, kiểm tra bất biến và quyền xử lý command.
4. Append event với phiên bản kế tiếp, cập nhật `current_version` rồi commit atomically.
5. Nếu xung đột phiên bản, tải lại state và đánh giá command từ đầu; không tự lặp một event cũ mà bỏ qua điều kiện mới.

Một lệnh có thể phát **nhiều event**; khi đó chúng phải được thêm với `stream_version` liên tiếp trong cùng transaction, và `current_version` phản ánh phiên bản cuối của nhóm. Ràng buộc duy nhất trên version không thay thế kiểm tra nghiệp vụ hoặc chống một command gửi lặp.

## 6. Command handling, idempotency và bất biến

Ví dụ một nhân viên xác nhận trả thiết bị; quy trình xử lý có thể biểu diễn bằng mã giả:

~~~text
handle(AcceptEquipmentReturn command):
    begin transaction
    ensure stream row exists
    lock stream row, read current_version
    check idempotency_key of this command
      if already committed: return previously recorded result

    state = load_snapshot_if_valid()
    state = replay_events_after_snapshot(state)

    check permissions, equipment identity, inspection evidence
    check not_already_accepted(state, equipment_id)
    new_event = EquipmentReturnAccepted(...)

    append new_event at current_version + 1
    update stream current_version
    save idempotency receipt / outbox records as needed
    commit transaction
    return recorded result
~~~

Về nguyên tắc, cần hoàn tất **kiểm tra và ghi** trong cùng phạm vi nhất quán. Nếu lệnh được gửi lại sau khi client timeout, hệ thống không được thêm một sự kiện nghiệm thu lần nữa chỉ vì response trước chưa đến client.

**Idempotency** thường có hai lớp:

- **Command idempotency:** lưu khóa yêu cầu trong một phạm vi rõ (`caller_id + idempotency_key` hoặc `tenant_id + operation + key`), kèm bản băm nội dung và kết quả xử lý. Cùng khóa/cùng nội dung trả lại kết quả đã ghi; cùng khóa/khác nội dung phải báo xung đột. Nếu một command sinh nhiều event, receipt riêng sẽ phù hợp hơn ràng buộc duy nhất chỉ trên một hàng event.
- **Event consumer idempotency:** mỗi projection/consumer theo dõi đã áp dụng event nào hoặc `last_version` của stream nào để không cộng trùng tiền, số lượt hay trạng thái khi nhận lại cùng thông điệp.

**Bất biến** vẫn phải rõ. Ví dụ tổng `refunded_minor` không vượt tổng `captured_minor`, một thiết bị không được nghiệm thu hai lần trong cùng vòng thuê, và hợp đồng không được đóng nếu còn nghĩa vụ chưa hoàn tất. Event sourcing không tự ngăn event sai; code điều khiển command phải ngăn từ trước.

Hàm replay cần **tất định (deterministic)** với cùng đầu vào. Nó không nên truy vấn bảng giá **hiện tại**, gọi API thanh toán, đọc thời gian máy hiện tại hay phát thông báo ra ngoài. Side effect xảy ra khi xử lý command hoặc trong workflow riêng; replay chỉ biến đổi trạng thái trong bộ nhớ hoặc xây read model.

## 7. Projection: tận dụng lịch sử mà vẫn truy vấn nhanh

Để hiển thị “hợp đồng đang có hiệu lực và số tiền còn phải hoàn”, không nên mỗi lần mở trang lại quét toàn bộ lịch sử của tất cả hợp đồng. Ta tạo **projection** theo nhu cầu đọc.

Ví dụ:

~~~sql
CREATE TABLE rental_current (
    rental_id             VARCHAR(80) PRIMARY KEY,
    rental_status         VARCHAR(24) NOT NULL,
    deposit_captured_minor BIGINT NOT NULL DEFAULT 0
                            CHECK (deposit_captured_minor >= 0),
    deposit_refunded_minor BIGINT NOT NULL DEFAULT 0
                            CHECK (deposit_refunded_minor >= 0),
    currency              CHAR(3) NOT NULL,
    last_applied_version  BIGINT NOT NULL DEFAULT 0
                          CHECK (last_applied_version >= 0),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (deposit_refunded_minor <= deposit_captured_minor)
);
~~~

Một projector đọc event `RENT-204` theo thứ tự version, áp dụng hàm `apply` và cập nhật `last_applied_version`. Nếu nhận lại phiên bản đã xử lý thì bỏ qua; nếu thấy version 7 trong khi mới áp dụng tới 5 thì cần lấy lại version 6 trước khi cập nhật. Với projector bất đồng bộ, những thao tác này phải được gắn với transaction cập nhật projection để không mất dấu đã xử lý.

Những đặc điểm cần công bố cho người dùng dữ liệu:

- **Độ trễ:** sau khi command commit event, projection bất đồng bộ có thể chưa đổi. Không mặc định một read model eventual consistency phản ánh thay đổi ngay lập tức.
- **Read-your-writes:** nếu giao diện cần đọc ngay kết quả command, có thể trả state/version từ command, đợi projection đạt version cần thiết trong giới hạn phù hợp, hoặc cập nhật projection quan trọng trong cùng transaction.
- **Kiểu truy vấn:** có thể tạo một projection phục vụ màn hình hợp đồng, một projection tính tỷ lệ trả trễ và một projection phân tích tiền cọc. Chúng có schema và chỉ mục khác nhau, nhưng phải có quy tắc nguồn và phiên bản rõ.
- **Rebuild:** nếu projector có lỗi, có thể tái tạo bảng dẫn xuất từ event store bằng hàm đọc phiên bản tương thích. Quá trình rebuild cần kế hoạch chuyển đổi, bắt kịp event mới và kiểm tra sai lệch; không xóa projection đang phục vụ production một cách tùy tiện.

Cũng cần xác định liệu một projection được tính từ event của **một aggregate** hay nhiều aggregate. Các ràng buộc xuyên aggregate có thể cần workflow và cách đồng bộ riêng, không được suy rằng một transaction cập nhật local aggregate sẽ làm mọi read model nhất quán tức thời.

## 8. Snapshot, replay và tiến hóa schema

### Snapshot giúp tăng tốc nhưng vẫn là dữ liệu dẫn xuất

Khi một hợp đồng có hàng nghìn event, dựng state từ đầu cho từng command có thể tốn thời gian. **Snapshot** lưu state sau khi áp dụng tới `stream_version = N`; phiên xử lý sau chỉ cần nạp snapshot rồi replay event từ `N + 1`.

~~~text
Snapshot(state@version=500)
    + event(501) + event(502) + ... + event(537)
    => current_state@version=537
~~~

Snapshot cần có `aggregate_id`, `stream_version`, phiên bản serialization/schema của snapshot và dữ liệu state. Phải xác minh snapshot thuộc đúng stream, không vượt phiên bản hiện có, và có thể bị bỏ đi, xây lại. Snapshot không thay thế chuỗi event gốc và không tự sửa event thiếu hoặc sai.

### Event cũ phải còn diễn giải được

Giả sử `DepositRefunded.v1` chỉ chứa `amount_minor` và `currency`; phiên bản 2 thêm `refund_method`. Có thể:

1. Tiếp tục hỗ trợ reader của cả `v1` và `v2`.
2. Dùng **upcaster** chuyển biểu diễn cũ sang cấu trúc chuẩn trong bộ nhớ khi replay.
3. Lập kế hoạch chuyển đổi/migration có kiểm chứng nếu thật sự cần thay event lịch sử.

Không thay đổi âm thầm ý nghĩa `amount_minor` trong cùng schema version. Nếu trước đây “refund” nghĩa là đã gửi yêu cầu, nhưng nay phải nghĩa là ngân hàng đã xác nhận, đó là **thay đổi ngữ nghĩa**; cần event hoặc quy tắc chuyển đổi có căn cứ, không đơn thuần tăng version rồi giả vờ mọi event cũ đều đã hoàn tất.

Thay đổi code của hàm `apply` có thể làm replay lịch sử ra kết quả khác. Điều này chỉ hợp lệ khi có quyết định nghiệp vụ rõ và kiểm chứng dữ liệu. Hãy thử replay trên stream cũ khi nâng cấp, dùng mẫu dữ liệu có các tình huống đặc biệt, và kiểm tra sự nhất quán giữa state dựng lại với state dự kiến.

### Sửa sai lịch sử bằng sự kiện điều chỉnh

Nếu một khoản phí được tính sai, cách xử lý thường là ghi sự kiện `RentalFeeCorrected` hoặc `ChargeReversed` theo quy tắc nghiệp vụ, giữ cả dấu vết cũ và hành động sửa. **Append-only** là nguyên tắc không xóa dấu vết sự thật đã xác nhận; nó không có nghĩa mọi dữ liệu được quyền lưu vĩnh viễn, hoặc sự kiện sai không bao giờ được điều chỉnh.

## 9. Giới hạn khi tích hợp nhiều dịch vụ và hiệu ứng bên ngoài

Một event store có thể bảo đảm thứ tự và tính nguyên tử **trong một aggregate/database transaction**, nhưng không tự tạo giao dịch phân tán cho thanh toán, kho và vận chuyển. Ví dụ nghiệp vụ hoàn cọc:

~~~mermaid
flowchart LR
    R["Rental: chấp nhận đề nghị hoàn"] --> O["Outbox: yêu cầu hoàn cọc"]
    O --> P["Payment service gọi nhà cung cấp"]
    P -->|Xác nhận thành công| E["Payment: RefundConfirmed"]
    E --> I["Integration event"]
    I --> C["Rental ghi DepositRefunded"]
~~~

Đây là luồng minh họa. Nếu nhà cung cấp thanh toán timeout, trạng thái có thể là **chưa biết kết quả**; không tự phát `DepositRefunded` khi chưa có chứng cứ. Phải có khóa idempotency cho lần hoàn tại nhà cung cấp, cơ chế retry và đối soát trước khi xác nhận.

Đối với việc công bố message sau commit, dùng **transactional outbox** hoặc cơ chế có bảo đảm tương đương: ghi bản ghi cần phát trong cùng transaction với event nguồn; relay riêng phát sau. Relay có thể phát trùng khi retry. Consumer phải xử lý lặp một cách idempotent, vì “gửi thành công một lần” không đồng nghĩa “mọi consumer xử lý đúng một lần”.

Sự kiện giữa các aggregate/dịch vụ **không có thứ tự toàn cục mặc định**. Kafka partition, database offset, `recorded_at` và `occurred_at` đều có phạm vi riêng. Để phối hợp nhiều bước, thiết kế orchestration/choreography, timeout, bù trừ, tương quan giao dịch và quan sát độ trễ. Event sourcing không loại bỏ nhu cầu về **saga** hoặc cơ chế điều phối khác khi quy trình trải nhiều dịch vụ.

## 10. Giới hạn và chi phí thực tế của event sourcing

Event sourcing phát huy giá trị trong bài toán cần **diễn tiến làm dữ liệu gốc**. Song nó đòi hỏi nhiều quyết định mà CRUD truyền thống có thể tránh được.

| Giới hạn/chi phí | Hệ quả thường thấy | Cách đánh giá hoặc giảm rủi ro |
| --- | --- | --- |
| **Phức tạp mô hình** | Mọi thay đổi phải có ngữ nghĩa event và logic replay. | Chỉ chọn các aggregate có lịch sử thật sự mang giá trị nghiệp vụ. |
| **Nhiều dữ liệu dẫn xuất** | Read model, projector, checkpoint và cache cần theo dõi. | Quy định độ trễ chấp nhận, kịch bản rebuild và kiểm tra projection drift. |
| **Độ dài stream tăng** | Replay từ đầu chậm, dung lượng lưu và chỉ mục tăng. | Snapshot, phân vùng/lưu trữ hợp lý, đo thời gian replay thực tế. |
| **Schema tồn tại lâu** | Mã mới phải đọc event cũ; thay đổi ngữ nghĩa khó. | Version contract và kiểm thử replay với dữ liệu lịch sử. |
| **Dữ liệu sai được ghi nhận** | Sửa bằng event bù trừ phức tạp hơn `UPDATE` hàng. | Thiết kế bất biến, kiểm tra đầu vào, quy trình correction có bằng chứng. |
| **Eventual consistency** | Người dùng có thể thấy state cũ trên read model. | Xác định độ trễ, read-your-writes, thông báo trạng thái xử lý khi phù hợp. |
| **Bảo mật và quyền riêng tư** | Lịch sử lâu dài có thể giữ dữ liệu nhạy cảm cần xóa. | Giảm payload, mã hóa, phân quyền, retention, ẩn danh hoặc thiết kế tách thông tin cá nhân. |
| **Giao tiếp liên dịch vụ** | Event không tự bảo đảm hoàn thành side effect. | Outbox, idempotency, đối soát, monitoring, bù trừ. |
| **Khó truy vấn trực tiếp** | Event log không tối ưu mọi truy vấn tổng hợp. | Thiết kế projection/analytics theo yêu cầu, không dùng event store làm OLAP mặc định. |
| **Lịch sử không đầy đủ từ lúc chuyển đổi** | Hệ thống cũ chỉ có trạng thái, không thể “phục dựng” sự kiện chưa từng lưu. | Đánh dấu rõ snapshot/initialization; không ngụy tạo lịch sử đã xảy ra. |

### Event sourcing không tự động có “cỗ máy thời gian”

Replaying đến version 20 cho biết state **được dựng theo diễn giải hiện tại đối với 20 event đầu**, nếu code và dữ liệu tham chiếu đủ ổn định. Nó không mặc nhiên cho biết mọi sự thật của thế giới tại một thời điểm lịch, hoặc “hệ thống đã biết gì” vào thời điểm đó.

Khi cần cả **thời điểm sự việc có hiệu lực** và **thời điểm hệ thống biết/ghi nhận**, hãy mô hình hóa các mốc riêng (`effective_at`, `occurred_at`, `recorded_at`) và cân nhắc yêu cầu bitemporal nếu nghiệp vụ cần. Một sự kiện đến muộn có `occurred_at` trước nhưng `stream_version` sau không nên bị chèn ngược tùy tiện vào lịch sử đã xác nhận.

### Quyền xóa dữ liệu và giới hạn append-only

Không được lấy “log bất biến” làm lý do bỏ qua chính sách xóa dữ liệu, retention hay yêu cầu pháp lý. Tùy bài toán có thể tách dữ liệu cá nhân khỏi event (chỉ lưu ID tham chiếu), áp dụng mã hóa theo chủ thể, kiểm soát truy cập và chính sách hủy khóa hoặc xóa dữ liệu theo quy trình được phép. Các phương án này phải được đánh giá về tính thực thi, khả năng replay và nghĩa vụ pháp lý cụ thể; không có một mẹo duy nhất phù hợp mọi hệ thống.

## 11. Khi nào nên, khi nào không nên dùng event sourcing?

### Những tín hiệu ủng hộ

Event sourcing có thể đáng cân nhắc khi **ít nhất một số yêu cầu sau là trọng tâm**, có chi phí vận hành được chấp nhận:

- Nghiệp vụ cần giải thích **chuỗi quyết định** và quá trình biến đổi trạng thái (tài chính, kiểm toán nghiệp vụ, hợp đồng, workflow phức tạp).
- Cần dựng lại nhiều góc nhìn dữ liệu từ cùng lịch sử có ngữ nghĩa, ví dụ số dư theo thời kỳ, diễn tiến cấp quyền, thời gian hoàn thành từng bước.
- Có nhu cầu tái tính toán projection khi sửa lỗi logic, và có khả năng lưu schema event đủ lâu để replay.
- Quy tắc nhất quán có ranh giới aggregate xác định và đội ngũ có khả năng thiết kế command/event/version/idempotency.
- Yêu cầu truy vết nghiệp vụ quan trọng hơn tính đơn giản của CRUD, và có kế hoạch giám sát/phục hồi.

### Những tín hiệu không nên áp dụng rộng

Một hệ thống quản lý danh mục đơn giản, cấu hình giao diện hoặc dữ liệu cập nhật thường xuyên nhưng không cần lịch sử diễn tiến hiếm khi thu được giá trị tương xứng từ event sourcing. Nếu chỉ cần một báo cáo ai đã sửa trường nào, **state + audit log** có thể đủ. Nếu mục tiêu chỉ là sao chép bảng sang kho phân tích, **CDC** có thể phù hợp hơn. Nếu mục tiêu chỉ là thông báo khi nghiệp vụ hoàn tất, **integration event + outbox** có thể đáp ứng mà không cần đổi nguồn sự thật thành event store.

| Câu hỏi ra quyết định | Nếu câu trả lời là “Có” | Nếu câu trả lời là “Không” |
| --- | --- | --- |
| Cần khôi phục state chính xác từ diễn tiến? | Cân nhắc event stream làm nguồn sự thật. | Trạng thái hiện hành + lịch sử chọn lọc có thể đủ. |
| Sự kiện có ngữ nghĩa được người nghiệp vụ thống nhất? | Có nền tảng tốt để định nghĩa event contract. | Làm rõ nghiệp vụ trước; tránh biến mọi update thành event mơ hồ. |
| Có năng lực quản lý version, replay, projection và vận hành? | Có thể thử nghiệm với aggregate phạm vi hẹp. | Giảm phạm vi hoặc chọn phương án đơn giản hơn. |
| Có thể xử lý quyền riêng tư/retention của lịch sử? | Xây chính sách lưu trữ song hành với thiết kế. | Không nên chọn lịch sử bất biến dài hạn khi chưa có giải pháp. |
| Giá trị của lịch sử lớn hơn chi phí tăng thêm? | Event sourcing có thể là lựa chọn phù hợp. | Ưu tiên mô hình trạng thái/quan hệ trực tiếp. |

**Chiến lược thực tế:** có thể dùng event sourcing cho **một bounded context hoặc aggregate**, chẳng hạn sổ cái giao dịch hoặc vòng đời hợp đồng, trong khi các phần còn lại tiếp tục CRUD. Điều quan trọng là xác định ranh giới nguồn sự thật, dữ liệu trao đổi và hành vi nhất quán giữa chúng; không buộc cả hệ thống phải có một kiểu lưu trữ.

## 12. Bài tập thiết kế và tiêu chí kiểm chứng

**Tình huống:** hệ thống đặt vé sự kiện lưu mỗi đơn bằng `booking_status`. Người dùng có thể giữ chỗ, thanh toán, hủy, được hoàn tiền; có thể xảy ra timeout ở cổng thanh toán và trùng callback. Bộ phận vận hành cần giải thích lịch sử của từng đặt vé, số tiền thực thu/đã hoàn, và xây lại báo cáo khi đổi quy tắc tính chỉ số.

Hãy thực hiện:

1. Xác định aggregate (ví dụ `Booking` và `Payment` có thể thuộc bounded context khác nhau). Nêu các **bất biến**: không xác nhận số ghế vượt sức chứa, không hoàn quá số tiền đã thu, không xử lý hai lần cùng callback.
2. Đề xuất event đã hoàn tất, chẳng hạn `SeatsReserved`, `PaymentCaptured`, `BookingCancelled`, `RefundConfirmed`. Phân biệt `CapturePaymentRequested` với `PaymentCaptured`.
3. Thiết kế envelope JSON gồm `event_id`, `aggregate_id`, `stream_version`, `event_type`, `schema_version`, `occurred_at`, `recorded_at`, và payload đủ hiểu giá vé/tiền tệ theo chính sách có phiên bản.
4. Mô tả transaction append theo phiên bản kỳ vọng, xử lý idempotency của callback và outbox phát integration event sang dịch vụ thông báo.
5. Định nghĩa ít nhất hai projection: bảng trạng thái đặt vé phục vụ màn hình và bảng phân tích tỷ lệ hủy sau thanh toán. Chỉ ra khóa, chỉ mục và độ trễ cập nhật chấp nhận.
6. Giải thích cách rebuild projection từ event stream và snapshot; mô tả cách đọc một event cũ khi schema thay đổi.
7. Đưa ra một **phương án thay thế không dùng event sourcing** (`bookings` + audit log + outbox) và chứng minh yêu cầu nào phương án này đáp ứng/không đáp ứng.

**Bảng kiểm tự đánh giá:**

| Phép kiểm | Kết quả mong đợi |
| --- | --- |
| **Replay** | Cùng event + cùng quy tắc diễn giải cho cùng state; không phát sinh side effect. |
| **Concurrent commands** | Không có hai event cùng phiên bản stream; command thất bại được đánh giá lại. |
| **Idempotency** | Callback gửi lặp không thu/hoàn hai lần và không làm projection cộng trùng. |
| **Tách nguồn sự thật** | Phân biệt event store, projection, outbox và dữ liệu của dịch vụ ngoài. |
| **Tương thích ngược** | Reader mới còn hiểu event được ghi bằng phiên bản schema cũ. |
| **Khôi phục** | Có thể rebuild read model với checkpoint phù hợp và đối chiếu kết quả. |
| **Bảo vệ dữ liệu** | Payload, quyền truy cập và thời hạn lưu phù hợp yêu cầu nghiệp vụ. |
| **Giá trị/chi phí** | Giải thích được vì sao chọn event sourcing thay vì state + audit/outbox. |

Lưu sự kiện làm nguồn dữ liệu là một **quyết định mô hình hóa**: lựa chọn ghi lại điều đã xảy ra làm dữ liệu gốc, rồi dẫn xuất trạng thái và các góc nhìn cần thiết. Giá trị của nó nằm ở lịch sử có ngữ nghĩa, khả năng replay và sự linh hoạt của read model; giới hạn nằm ở độ phức tạp, tính nhất quán, tiến hóa schema, vận hành và quản trị dữ liệu. Chỉ nên áp dụng khi những lợi ích này giải quyết trực tiếp yêu cầu nghiệp vụ và có cách kiểm chứng rõ ràng.
