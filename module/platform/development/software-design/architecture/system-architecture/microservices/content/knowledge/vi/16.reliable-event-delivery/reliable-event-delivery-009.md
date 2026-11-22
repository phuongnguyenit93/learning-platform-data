# Đối soát dữ liệu khi nguồn sự kiện và bản chiếu sai lệch

## 1. Bối cảnh: sự kiện đúng nhưng dữ liệu đọc vẫn có thể sai

Trong một hệ thống microservices, dịch vụ sở hữu nghiệp vụ thường ghi dữ liệu ở một nơi, sau đó phát sự kiện để xây các bản dữ liệu phục vụ đọc (*projection*, *read model*, *materialized view*, *search index* hoặc bảng tổng hợp). Cách tổ chức này giúp tách lưu lượng ghi khỏi truy vấn, hỗ trợ CQRS, tìm kiếm và báo cáo. Nhưng việc nhận và xử lý sự kiện thường **bất đồng bộ**, nên bản chiếu có thể bị trễ hoặc sai lệch.

Ví dụ Order Service đã xác nhận một đơn và phát OrderConfirmed. Reporting Consumer nhận sự kiện để cập nhật bảng doanh thu. Nếu consumer crash sau khi cập nhật tổng nhưng trước khi ACK, broker có thể giao lại, và doanh thu có thể bị cộng hai lần nếu handler không idempotent. Ngược lại, nếu hệ thống đánh dấu offset đã xử lý trước khi commit database rồi crash, sự kiện có thể bị bỏ sót. Khi event đã bị xóa do hết retention, replay có thể không còn đủ dữ liệu để tự khôi phục.

Vấn đề cần giải quyết không chỉ là “đưa lại message vào queue”. Một kế hoạch **đối soát (reconciliation)** phải trả lời:

1. Đâu là **nguồn dữ liệu có thẩm quyền** để xác định trạng thái đúng?
2. Bản chiếu đang **chậm hợp lệ** hay đã **sai lệch thực sự**?
3. Sai lệch thuộc loại **thiếu, trùng, sai thứ tự, sai nội dung, thiếu xóa** hay do schema/logic?
4. Làm sao **phát hiện chính xác** chứ không chỉ nhìn tỷ lệ message thành công?
5. Có thể **tái xử lý an toàn** không, hay cần dựng lại projection?
6. Làm sao sửa mà **không ghi đè những cập nhật mới** đang tới?
7. Ai sở hữu quy trình, dashboard, cảnh báo, audit và tiêu chí kết thúc?

**Nguyên tắc trung tâm:** coi projection là một mô hình được duy trì theo hợp đồng, có thể kiểm chứng và phục hồi; đừng coi việc broker đã phát event là bằng chứng projection luôn đúng.

## 2. Những khái niệm phải phân biệt

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Source of truth | Nơi có thẩm quyền về trạng thái nghiệp vụ | Order DB hoặc event store nếu dùng event sourcing |
| Source event | Thông điệp mô tả thay đổi/sự kiện được công bố | OrderConfirmed(orderId, version) |
| Event log | Dòng sự kiện được lưu theo offset/sequence và retention | Kafka topic hoặc event store |
| Projection / read model | Dữ liệu dẫn xuất để phục vụ một truy vấn cụ thể | Bảng đơn theo khách, search index |
| Projector | Consumer cập nhật projection | OrderReadModelUpdater |
| Checkpoint | Dấu tiến độ đã được commit an toàn | Offset theo partition hoặc event cursor |
| Watermark | Ranh giới tiến độ mà dữ liệu được cho là đã áp dụng | Lần đọc đến offset 9180 |
| Lag | Độ trễ xử lý so với nguồn | Event phát 5 giây trước, chưa hiển thị |
| Drift | Khác biệt không hợp lệ giữa trạng thái kỳ vọng và projection | Đơn đã CONFIRMED nhưng search vẫn PENDING lâu quá ngưỡng |
| Replay | Đọc lại events để xử lý lại | Consumer group mới đọc từ offset trước |
| Backfill | Nạp dữ liệu lịch sử bị thiếu | Scan Orders rồi ghi projection |
| Rebuild | Tạo lại projection từ nguồn có thẩm quyền | Dựng search index mới |
| Repair | Chỉnh có kiểm soát các records sai lệch | Recompute một order theo source |

**Lưu ý về thẩm quyền:** Nếu ứng dụng dùng **event sourcing**, event store có thể là nguồn sự thật, còn bảng Order là projection. Nếu ứng dụng dùng **transactional database + outbox/CDC**, Order DB thường là nguồn sự thật, còn Kafka topic là kênh truyền thay đổi. Không được mặc định “Kafka luôn đúng hơn DB” hoặc ngược lại mà chưa xác định mô hình của hệ thống.

### 2.1. Projection không nhất thiết là database độc lập

Projection có thể là bảng SQL, tài liệu trong search index, cache, Redis key, graph edge, time-series aggregate hoặc materialized view. Nó có thể nằm cùng engine với source hoặc trên hạ tầng khác. Điều quan trọng là **dữ liệu đã được biến đổi để phục vụ nhu cầu đọc** và phải có quy tắc đồng bộ.

### 2.2. Đối soát không phải luôn sửa dữ liệu ngay

Đối soát có thể gồm ba giai đoạn riêng:

- **Detect:** phát hiện record, aggregate, partition hoặc thời kỳ có nghi vấn.
- **Diagnose:** xác minh nguyên nhân, mức độ trễ và nguồn có thẩm quyền.
- **Repair:** cập nhật/rebuild có guard, kiểm tra lại và ghi audit.

Với dữ liệu tài chính, đôi khi bước đúng là **quarantine/manual review**, không phải tự động ghi đè theo một phép so sánh thiếu ngữ cảnh.

## 3. Phân loại các dạng sai lệch

### 3.1. Thiếu sự kiện hoặc thiếu bản ghi

Source có order O-8421 ở trạng thái CONFIRMED nhưng projection không có order này. Nguyên nhân có thể là:

- Publisher chưa phát event sau khi DB commit.
- Broker retention xóa event trước khi consumer đọc.
- Consumer ACK trước khi ghi DB rồi crash.
- Event bị đưa vào DLQ nhưng workflow không theo dõi.
- Bộ lọc, tenant mapping hoặc schema transform bỏ qua event.
- Backfill không bao phủ một time range hoặc partition.

Không nên chỉ nhìn một row thiếu mà kết luận broker đánh mất message; cần lần theo outbox, event log, offset, inbox và logs.

### 3.2. Event được xử lý trùng

Một event OrderConfirmed được giao hai lần. Với projection dạng “set status=CONFIRMED”, xử lý lặp có thể vô hại nếu có guard. Với projection “revenue += amount”, xử lý lặp có thể nhân đôi doanh thu.

~~~text
Initial revenue = 1.000.000
Event E100 amount=250.000 applied once -> 1.250.000
Redelivery E100 applied again -> 1.500.000  (sai)
~~~

Duplicate delivery là điều bình thường trong nhiều hệ message at-least-once. Phải chọn thuật toán cập nhật phù hợp với khả năng replay.

### 3.3. Sự kiện đến sai thứ tự

~~~text
OrderCreated(version=1)
OrderConfirmed(version=2)
OrderCancelled(version=3)
~~~

Nếu version 3 tới trước và version 2 tới sau, một handler “last message wins” có thể ghi CONFIRMED sai. Cần aggregate version/sequence, conditional update và quy tắc xử lý event tới không đúng thứ tự.

### 3.4. Nội dung sai do chuyển đổi/schema

Sự kiện có đủ nhưng một deploy mới thay đổi cách tính total hoặc mapping currency. Projection sau deploy khác dữ liệu nguồn. Replay cùng event qua code mới có thể cho kết quả khác trước nếu logic không deterministic hoặc schema migration bị thiếu.

### 3.5. Thiếu thao tác xóa

Source đã xóa hoặc vô hiệu hóa product nhưng search index vẫn có tài liệu cũ. Nếu chỉ phát các event tạo/cập nhật mà bỏ Delete/Tombstone, index có thể hiển thị dữ liệu không còn hợp lệ hoặc thông tin đáng lẽ bị xóa.

### 3.6. Dữ liệu đọc đang trễ hợp lệ

Sau khi Order commit, search index chưa nhận event trong 2 giây. Nếu public contract chấp nhận lag 10 giây, đây chưa phải drift cần sửa. Reconciliation phải có **ngưỡng thời gian**, tránh spam alert và xung đột với luồng update bình thường.

## 4. Kiến trúc chuẩn: owner, event delivery và read model

Một đường dữ liệu điển hình:

~~~mermaid
flowchart LR
    API["Order API"] --> DB[("Order DB")]
    DB --> O[("Transactional Outbox")]
    O --> P["Publisher / CDC"]
    P --> B[("Event Broker")]
    B --> C["Projection Consumer"]
    C --> R[("Order Read Model")]
    DB --> V["Reconciliation Worker"]
    R --> V
    V --> Q[("Repair Queue / Audit")]
~~~

**Order Service** sở hữu trạng thái đơn. **Projector** có quyền biến các thay đổi của Order thành read model. **Reconciliation Worker** kiểm tra sự nhất quán, tìm nguyên nhân và sửa phần dữ liệu do projection owner quản lý.

Một hệ event-sourced có sơ đồ khác: event store có thẩm quyền, state của Order và các read models đều được dựng từ event stream. Trong trường hợp đó, so sánh cần chọn đúng **event store + snapshot/version** chứ không tự coi bảng Order hiện tại là nguồn duy nhất.

### 4.1. Không được để read model thành nguồn ghi của domain

Nếu Search Service thấy dữ liệu không giống Order DB, nó không nên cập nhật trực tiếp Order DB để “đồng bộ”. Cần xác định bên có thẩm quyền. Sửa projection thường là **tính lại từ source**, còn sửa source cần quy trình nghiệp vụ hoặc data correction riêng.

### 4.2. Nhiều projection độc lập

Một OrderConfirmed có thể xây:

- OrderByCustomer projection.
- RevenueDaily projection.
- SearchIndex projection.
- Notification history.
- Analytics warehouse feed.

Mỗi projection có owner, checkpoint, dedup, schema và thời gian cập nhật riêng. Không vì RevenueDaily đúng mà suy ra SearchIndex đã cập nhật. Reconciliation cần **theo projection type** và data contract riêng.

## 5. Xác định source of truth trước khi so sánh

Một bảng quyết định:

| Hệ thống | Nguồn sự thật thường gặp | Projection cần đối soát |
| --- | --- | --- |
| Order DB + Outbox | Order DB tại snapshot/version hợp lệ | Search, read-only views, analytics |
| Event sourcing | Event store, event sequence và aggregate rules | Current-state views, indexes, reports |
| CDC từ MySQL/PostgreSQL | Database source, CDC log theo commit order | Downstream data store |
| Data warehouse nhiều nguồn | Từng domain owner cho facts; semantic contract cho metrics | Data marts/reporting |
| Payments qua provider | Payment Service state kết hợp đối soát provider theo contract | Order/payment summary read model |

Nếu nguồn sự thật cũng có thể sai do bug nghiệp vụ, reconciliation **không tự chứng minh sự thật ngoài đời**. Ví dụ Payment DB ghi PENDING nhưng provider đã thu tiền, cần đối soát Payment Service với provider trước khi sử dụng Payment DB để sửa báo cáo.

### 5.1. Không so sánh các thời điểm khác nhau như cùng snapshot

Khi source liên tục thay đổi, một scan mất 10 phút có thể so snapshot lúc 10:00 với projection lúc 10:10. Khác biệt quan sát được chưa chắc là drift.

Cần định nghĩa ranh giới so sánh:

- Snapshot nhất quán tại một thời điểm hoặc commit sequence.
- Source watermark với giới hạn event đã được công bố.
- Projection applied checkpoint đã được commit.
- Khoảng “grace period” cho dữ liệu trễ.
- Chiến lược giữ nguyên snapshot hoặc so lại sau khi cả hai bên bắt kịp cùng mốc.

**Không so sánh current source với arbitrary projection rồi sửa ngay** trong hệ thống đang ghi liên tục.

## 6. Hợp đồng sự kiện hỗ trợ đối soát

Một event có cấu trúc đủ tốt:

~~~json
{
  "eventId": "evt-order-8421-v7",
  "eventType": "OrderStatusChanged",
  "schemaVersion": 2,
  "aggregateType": "Order",
  "aggregateId": "O-8421",
  "aggregateVersion": 7,
  "occurredAt": "2026-11-11T10:45:00Z",
  "payload": {
    "orderId": "O-8421",
    "status": "CONFIRMED",
    "totalMinor": 250000,
    "currency": "VND"
  }
}
~~~

Các thành phần có vai trò khác nhau:

- **eventId:** dedup một sự kiện cụ thể.
- **aggregateId:** xác định entity cần cập nhật.
- **aggregateVersion:** giúp phát hiện event cũ, event gap và concurrency.
- **eventType:** xác định phép biến đổi có ý nghĩa.
- **schemaVersion:** giúp giải mã event cũ.
- **occurredAt:** để quan sát thời gian phát sinh; không tự bảo đảm ordering.
- **payload:** đủ thông tin theo public/internal event contract, tránh lộ PII không cần thiết.
- **tenantId** nếu dữ liệu đa tenant, được bảo vệ và validate theo boundary.

Nếu một event chỉ có status không có key/version, reconciliation sau sự cố sẽ khó phân biệt nhiều lần thay đổi cùng một aggregate.

### 6.1. EventId không thay business operation ID

Hai event khác nhau có thể nói về cùng trạng thái của Order. Cùng eventId được redeliver, hoặc hai eventId phản ánh hai business transitions khác nhau. Dedup theo eventId cần kết hợp với **version và invariant** của projection.

### 6.2. Clock timestamp không thay sequence

Máy chủ có thể lệch đồng hồ; event từ nhiều partitions có thể đến không theo timestamp. Nếu quyết định state update dựa hoàn toàn vào occurredAt, một event cũ phát trễ có thể ghi đè event mới. Nên dùng **sequence/aggregateVersion có thẩm quyền** khi yêu cầu ordering theo aggregate.

### 6.3. Event payload và quyền riêng tư

Đối soát cần định danh, không nhất thiết cần toàn bộ thông tin khách hàng. Tránh đưa dữ liệu thẻ, token hoặc PII vào event chỉ vì tiện rebuild. Có thể dùng reference đến nguồn có thẩm quyền, nhưng khi replay từ sự kiện cần xem xét source endpoint có còn dữ liệu lịch sử cần thiết không.

## 7. Bảo đảm phát sự kiện từ nguồn bằng Outbox/CDC

Một nguyên nhân drift bắt đầu từ dual-write:

~~~text
1. UPDATE orders SET status='CONFIRMED'
2. COMMIT database
3. Publish OrderConfirmed
4. Process crash trước bước 3
~~~

Nếu không có cơ chế phục hồi, source đã thay đổi nhưng event không bao giờ ra broker.

**Transactional Outbox:** business state và outbox record được commit trong cùng transaction cục bộ.

~~~sql
BEGIN;

UPDATE orders
SET status = 'CONFIRMED', version = version + 1
WHERE order_id = 'O-8421';

INSERT INTO outbox (
    event_id, aggregate_id, aggregate_version, event_type, payload
)
VALUES (
    'evt-order-8421-v7',
    'O-8421',
    7,
    'OrderStatusChanged',
    '{"orderId":"O-8421","status":"CONFIRMED"}'
);

COMMIT;
~~~

Ví dụ SQL minh họa; production cần version guard, eventId được tạo an toàn và bảo đảm payload phù hợp state đã commit. Publisher/CDC đọc outbox rồi gửi tới broker.

Outbox làm giảm rủi ro **commit business state nhưng mất ý định publish**. Publisher vẫn có thể phát event trùng khi crash sau publish trước khi đánh dấu đã gửi; consumer phải idempotent.

### 7.1. CDC có thể phát lại

Change Data Capture đọc transaction log hoặc dữ liệu thay đổi; connector có thể restart, snapshot, gặp schema changes hoặc retry. Không nên giả định CDC luôn phát chính xác một lần đến mọi downstream. Tùy công nghệ, phải quản lý offsets, snapshot barriers, retention và duplicate.

### 7.2. Lưu outbox đủ lâu cho recovery

Nếu publisher bị lỗi ba ngày nhưng outbox chỉ giữ một ngày và tự xóa record chưa gửi, source và projection có thể lệch vĩnh viễn. Retention phải dựa trên lag xấu nhất, failure policy và khả năng rebuild; không xóa pending outbox chỉ vì quá tuổi.

### 7.3. Thiết kế khả năng audit

Với mỗi cập nhật quan trọng, nên có dấu vết:

- Transaction hoặc aggregate version đã commit.
- Outbox event liên quan.
- Thời điểm publish/ACK.
- Broker topic/partition/offset nếu có.
- Consumer/checkpoint đã commit.
- Projection version sau xử lý.

Không phải mọi hệ phải lưu toàn bộ ở cùng một bảng; nhưng hệ thống điều tra cần liên kết được những dấu này bằng ID ổn định.

## 8. Idempotent projector: chống cộng trùng và xử lý lại an toàn

Projector thường chạy theo at-least-once delivery. Một thiết kế cơ bản ghi marker xử lý event cùng transaction cập nhật read model.

~~~sql
CREATE TABLE projection_inbox (
    projection_name TEXT NOT NULL,
    event_id TEXT NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (projection_name, event_id)
);

CREATE TABLE order_read_model (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    status TEXT NOT NULL,
    total_minor BIGINT NOT NULL,
    currency CHAR(3) NOT NULL,
    last_source_version BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Đường xử lý:

~~~text
Receive event E
BEGIN local projection DB
  Atomically insert (projectionName, eventId) into inbox
  If already present: no-op
  Else:
    Check aggregate version and state transition
    Apply projection changes
COMMIT
ACK broker / commit offset
~~~

Nếu crash trước commit, inbox và projection update cùng rollback. Nếu crash sau commit trước ACK, redelivery thấy marker và không áp dụng hai lần.

### 8.1. Tại sao chỉ có inbox chưa đủ?

Hai event khác eventId nhưng sai thứ tự vẫn có thể làm read model lỗi. Một event có version thấp hơn last_source_version không được ghi đè entity version mới. Nếu event version cao hơn nhiều cấp, có thể đang **thiếu gap**; cần policy chờ/replay hoặc reconcile source.

### 8.2. Dùng set/update có điều kiện thay vì increment mù

Nếu projection lưu order status, cập nhật theo version có thể kiểm tra đơn điệu:

~~~sql
UPDATE order_read_model
SET status = 'CONFIRMED',
    last_source_version = 7
WHERE order_id = 'O-8421'
  AND last_source_version < 7;
~~~

Nhưng phép này chỉ đúng khi event version 7 chứa trạng thái đầy đủ cần cho projection hoặc có cách xử lý gap. Nếu event là delta như ItemAdded, bỏ qua version 6 rồi áp version 7 có thể làm mất tác dụng của version 6. Cần phân biệt **state replacement event** và **delta event**.

### 8.3. Đối với aggregate/counter

Một event RevenueAdded không nên được cộng thêm nhiều lần. Có thể lưu một fact theo eventId với UNIQUE rồi tính tổng hoặc cập nhật tổng **trong cùng transaction với marker**. Khi cần sửa, cách an toàn thường là **recompute từ facts có thẩm quyền**, không chỉ cộng thêm “phần thiếu” dựa trên số chênh lệch chưa rõ nguyên nhân.

## 9. Ordering và event gap

Giả sử Order O-8421 có version 10 ở source. Projection đã áp dụng version 8, nhưng nhận event version 10 trước version 9.

Các chiến lược:

1. **Buffer:** chờ version 9 trong một thời gian giới hạn, rồi áp lần lượt.
2. **Replay:** truy xuất lại event version 9 từ log/event store.
3. **Refresh aggregate:** nếu source có API lấy trạng thái đầy đủ phù hợp, tính lại projection tới version 10, rồi bỏ qua các delta cũ.
4. **Mark for reconciliation:** nếu thiếu dữ liệu, chuyển record vào hàng đối soát có owner.

Không nên im lặng áp delta version 10 khi cần version 9 để tính đúng.

### 9.1. Broker ordering có giới hạn

Kafka bảo đảm thứ tự trong một partition theo offset, không phải thứ tự toàn cục giữa partitions. Partition key theo aggregateId có thể giữ các event cùng aggregate đi vào một partition nếu producer/config giữ quy tắc đó. Tuy nhiên migration, multiple sources, retries hoặc thay đổi partitioning vẫn cần state/version guard.

### 9.2. Event đến muộn sau sửa dữ liệu

Reconciliation sửa projection lên version 10. Sau đó projector nhận lại event version 9. Nếu không có conditional version guard, bản chiếu có thể bị lùi. **Mọi đường ghi projection, gồm live projector và repair worker, phải cùng tuân thủ monotonic version policy**.

## 10. Checkpoint: dấu tiến độ không phải bằng chứng dữ liệu đúng

Một consumer có thể ghi:

~~~text
topic=orders
partition=2
committedOffset=9180
~~~

Điều đó chỉ cho biết vị trí tiêu thụ đã được ghi nhận theo cơ chế broker; nó **không tự chứng minh** mọi event trước offset đều được áp dụng vào projection nếu mã xử lý ACK sớm, nuốt exception hoặc có write lỗi.

Với at-least-once, thứ tự thường an toàn hơn là:

1. Đọc event.
2. Commit projection DB transaction (inbox + read model).
3. Commit offset/ACK.

Nếu crash sau bước 2 trước bước 3, event có thể được giao lại, nhưng xử lý idempotent chặn duplicate effect. Nếu commit offset trước bước 2, có nguy cơ bỏ sót.

### 10.1. Checkpoint theo partition

Một hệ có nhiều partitions không thể chỉ lưu “offset lớn nhất toàn topic”. Cần theo dõi tiến độ từng partition hoặc chính xác theo nguồn có hỗ trợ. Khi parallel processing trong một partition, commit offset phải phản ánh **các records liên tiếp đã hoàn tất**, không được nhảy qua một event chưa xử lý mà không có policy.

### 10.2. Checkpoint cho backfill và repair

Một reconciliation job quét theo key range có thể lưu:

- Job ID, projection name và source watermark.
- Bắt đầu/kết thúc scan theo partition/range.
- Cursor/lastKey đã hoàn tất.
- Số record đã so sánh, số mismatch và số đã sửa.
- Các lỗi phải retry và thời gian tiếp theo.
- Trạng thái STOPPED/RUNNING/COMPLETED/NEEDS_REVIEW.

Cursor chỉ được đánh dấu tiến khi phần dữ liệu tương ứng **đã được kiểm tra và ghi nhận kết quả bền vững**, tránh mất phạm vi sau restart.

## 11. Phân biệt projection lag với dữ liệu sai lệch

Một bản chiếu có thể có trạng thái đúng nhưng chậm do backlog.

Ví dụ:

~~~text
10:00:00 Order O-8421 version 7 COMMIT
10:00:01 Outbox record được publish
10:00:02 Broker ghi event
10:00:03 Projector đang xử lý backlog
10:00:06 Read model cập nhật version 7
~~~

Nếu contract cho phép staleness 10 giây thì điều này là bình thường. Nếu sau 30 phút read model vẫn version 6, cần điều tra.

### 11.1. Định nghĩa freshness SLO

Một nhóm có thể đặt:

- 99% changes được phản ánh trong projection trong 10 giây ở tải mục tiêu.
- 99,9% changes được phản ánh trong 60 giây, ngoại trừ maintenance có công bố.
- Mọi mismatch đã vượt grace period có owner và quy trình đối soát.

Con số chỉ minh họa. Cần xác định phép đo từ thời điểm nào: business commit, outbox creation, broker publish hay event consumption. Nếu đo từ broker publish, các event bị kẹt trong outbox sẽ không xuất hiện trong metric này; nên đo cả **end-to-end freshness**.

### 11.2. Hiểu lag theo nhiều tầng

| Tầng | Chỉ báo |
| --- | --- |
| Source -> Outbox | Records chưa publish, tuổi outbox lớn nhất |
| Outbox -> Broker | Publish latency/errors |
| Broker -> Consumer | Consumer lag theo partition |
| Consumer -> Projection | Commit latency, DB write errors |
| Projection -> API | Cache TTL, read replica lag, index refresh delay |
| Reconciliation | Queue age, mismatch age, repair completion |

Không quy mọi bất thường thành “Kafka lag”. Có thể broker trống nhưng projection stale vì cache cũ hoặc indexing refresh.

## 12. Xác định điều kiện đúng của projection

Trước khi đối soát, phải mô tả **invariant / expected function**.

Ví dụ với OrderByCustomer:

~~~text
Projection(OrderId) =
  {
    customerId,
    latestStatus,
    totalMinor,
    currency,
    aggregateVersion
  }
theo trạng thái Order ở sourceVersion đã thống nhất.
~~~

Với RevenueDaily:

~~~text
Revenue(day, currency) =
  SUM(eligible confirmed payment facts)
  - SUM(eligible refund facts)
theo chính sách kế toán đã định.
~~~

Công thức doanh thu là ví dụ; production phải chốt thời điểm ghi nhận, timezone, currency conversion, settlement/refund logic và hạch toán. Một báo cáo “sai” có thể thực ra do hai nhóm dùng định nghĩa metric khác nhau, không phải mất event.

### 12.1. Định nghĩa phép chiếu có version

Nếu logic projection thay đổi từ chỉ tính OrderConfirmed sang tính cả Refund, cần gắn projectionDefinitionVersion và schemaVersion. So sánh dữ liệu nguồn theo định nghĩa cũ với projection mới sẽ báo mismatch giả.

### 12.2. Tránh non-determinism

Một projection dễ rebuild khi cùng source và cùng definition version tạo cùng kết quả. Nếu code dùng thời điểm hiện tại, random, tỷ giá “hiện hành” hoặc dịch vụ lookup thay đổi mà không lưu dữ liệu lịch sử, replay có thể tạo kết quả khác.

Nên phân biệt dữ liệu được **ghi tại thời điểm event**, dữ liệu cần lookup theo một version và dữ liệu có thể chấp nhận giá trị hiện hành. Với nhu cầu audit, phải lưu đủ facts/versions để rebuild nhất quán.

## 13. Kỹ thuật đối soát theo khóa bản ghi

Kỹ thuật phổ biến là so sánh projection với source theo một tập khóa và thời điểm thích hợp:

1. Lấy danh sách aggregate IDs trong một partition/range.
2. Đọc authoritative state tại snapshot/watermark.
3. Tính expected projection theo definition version.
4. Đọc actual projection cùng key.
5. Chuẩn hóa dữ liệu và so sánh các trường có ý nghĩa.
6. Ghi mismatch classification: missing, extra, outdated, content mismatch.
7. Repair nếu đủ điều kiện an toàn; nếu không thì queue review.
8. Kiểm tra lại sau khi projection đuổi kịp watermark.

### 13.1. Đừng so chuỗi JSON nguyên văn khi không cần

JSON có thể khác thứ tự key, khoảng trắng, kiểu số, serialization timestamp mà vẫn cùng nghĩa. So sánh cần canonicalization:

- Chọn field nghiệp vụ thực sự thuộc projection.
- Chuẩn hóa timezone và precision của thời gian.
- Chuẩn hóa số tiền về minor units + currency, tránh float mơ hồ.
- Quy định null khác missing field hay không.
- Sắp xếp phần tử nếu domain coi array là tập, giữ thứ tự nếu domain yêu cầu.
- Chuẩn hóa Unicode khi hợp đồng cần.
- Tách metadata như updatedAt/traceId không liên quan đến kết quả.

### 13.2. Hash/checksum có giúp không?

Có thể tính hash của canonical business fields để phát hiện mismatch nhanh:

~~~text
expectedHash = hash(canonical(expectedProjection))
actualHash   = hash(canonical(actualProjection))
~~~

Hash khác nhau chứng minh canonical data khác; hash giống nhau là bằng chứng mạnh nhưng không phải chứng minh logic định nghĩa đúng, và có rủi ro collision lý thuyết. Dùng thuật toán hash phù hợp và lưu **canonicalization version** nếu cần so qua nhiều deploy.

Không hash nguyên object có các trường non-deterministic như generatedAt, replicaLatency, hoặc thứ tự JSON không ổn định.

## 14. Đối soát theo partition, time bucket và aggregate version

Với hàng tỷ records, so từng key mỗi giờ có thể quá đắt. Có thể tổ chức nhiều tầng:

**Tầng 1 — Thống kê tổng quan:** số records, max version, min/max timestamp, tổng amount theo currency/time bucket.

**Tầng 2 — Checksum phân vùng:** hash tổng hợp có deterministic order theo partition/tenant/time bucket; dùng để tìm nhóm nghi vấn.

**Tầng 3 — Key-level diff:** so chi tiết các aggregate IDs trong nhóm sai.

**Tầng 4 — Repair:** tính lại từng aggregate hoặc rebuild shard/index.

Cần chú ý:

- Count bằng nhau không chứng minh dữ liệu giống.
- Tổng amount bằng nhau có thể che hai lỗi bù trừ nhau.
- Hash phụ thuộc cách canonicalize và cách chọn phạm vi.
- Time bucket theo event time khác processing time.
- Kết quả giữa các thời điểm khác nhau gây false positives.

### 14.1. Sampling và full reconciliation

Sampling tiết kiệm chi phí và phát hiện xu hướng, nhưng có thể bỏ sót record hiếm mà tác dụng lớn. Với dữ liệu tài chính hoặc dữ liệu nhạy cảm, có thể cần full scan theo lịch, partition rotation hoặc kiểm tra trên tất cả changed keys.

Kế hoạch thường kết hợp:
- Near-real-time drift signals theo version/lag.
- Incremental reconciliation cho keys vừa thay đổi.
- Periodic deep reconciliation theo partition.
- Full rebuild/test restore khi schema thay đổi hoặc incident lớn.

## 15. Snapshot và watermark: không sửa bằng ảnh chụp đã cũ

Giả sử reconciliation đọc source ở version 12, mất 5 giây để tính lại. Trong thời gian đó live projector đã áp dụng version 13. Nếu repair worker upsert version 12 vô điều kiện, nó làm dữ liệu lùi.

Một chiến lược an toàn:

~~~text
Source snapshot for O-8421: version=12
Expected projection computed for version 12
Actual projection now: version=13
Repair write with guard:
  only update if actualVersion < 12
Result: no-op because actual version 13 is newer.
~~~

Nếu cần sửa **nội dung sai ở cùng version** (version=12 nhưng hash không khớp), phải có cách nhận diện projectionDefinitionVersion/generation và điều kiện concurrency rõ. Không thể chỉ so version rồi kết luận nội dung đúng.

### 15.1. Checkpoint không thay source snapshot

Checkpoint broker offset 9180 không cung cấp tự động một snapshot nhất quán của PostgreSQL tại thời điểm đó. Cần phối hợp commit sequence/CDC LSN hoặc cơ chế snapshot và capture stream tương ứng với công nghệ được dùng.

### 15.2. CDC snapshot + streaming

Khi nạp lại nhiều dữ liệu, một mô hình khả thi:

1. Đặt ranh giới CDC hoặc snapshot watermark.
2. Đọc snapshot nguồn nhất quán theo hỗ trợ của database.
3. Build projection từ snapshot.
4. Consume changes phát sinh từ watermark trở đi.
5. Catch up đến một ranh giới mới rồi cutover.
6. Tiếp tục stream bình thường.

Phải kiểm tra chính xác CDC connector xử lý snapshot, transaction boundaries, offsets, DDL và event ordering thế nào; không tự đoán rằng snapshot timestamp là đủ để tránh gap.

## 16. Khi nào nên repair từng bản ghi, khi nào rebuild?

| Tình huống | Phương án thường phù hợp | Vì sao |
| --- | --- | --- |
| Vài order thiếu trong read model | Recompute/upsert theo key | Phạm vi nhỏ, dễ kiểm chứng |
| Một partition mất một khoảng events | Replay từ checkpoint nếu còn retention | Giữ semantics stream và giảm scan source |
| Logic transform bị lỗi trên hàng triệu records | Rebuild projection với code đã sửa | Sửa từng key dễ bỏ sót |
| Search index đổi mapping/analyzer | Build index mới rồi alias swap | Tránh reindex in-place gây downtime |
| Event store authoritative, cần projection mới | Deterministic replay | Có lịch sử đủ để dựng |
| Event đã hết retention, source DB còn dữ liệu | Backfill từ source + CDC catch-up | Replay log không đủ |
| Sai lệch liên quan tiền thực | Source verification + controlled repair/manual review | Không tự cập nhật theo phép đếm đơn giản |
| Projection chưa chắc sai, chỉ lag vài giây | Chờ within SLO/monitor | Tránh sửa đè event đang tới |

Không dùng rebuild như phản xạ cho mọi sự cố. Một rebuild toàn hệ thống có thể tốn nhiều giờ, làm tăng tải source và gây egress rất lớn.

### 16.1. Repair có thể làm mất lịch sử nếu chỉ dùng current state

Nếu projection cần historical facts, current Order state không đủ tái dựng những biến động đã qua. Ví dụ tổng doanh thu theo ngày dựa trên payment settlement events: xem đơn hiện tại không nhất thiết cho biết ngày hoàn tiền hay trạng thái settlement trước đây. Khi đó cần event store/ledger/historical source đã được giữ theo policy.

## 17. Incremental repair theo bản ghi: giải pháp có guard

Một repair command có thể chứa:

~~~json
{
  "repairId": "repair-2026-11-O8421",
  "projection": "OrderByCustomer",
  "aggregateId": "O-8421",
  "expectedSourceVersion": 12,
  "projectionDefinitionVersion": 4,
  "reason": "MISSING_OR_STALE",
  "requestedAt": "2026-11-11T11:00:00Z"
}
~~~

Worker:
1. Xác thực quyền chạy và ranh giới tenant.
2. Đọc authoritative source/state theo contract.
3. Tính lại expected projection ở version phù hợp.
4. Đọc actual projection.
5. Chỉ update khi điều kiện version/generation an toàn.
6. Ghi audit before/after hash/version, không lưu PII dư thừa.
7. Đánh dấu repair thành công sau commit.
8. Xác minh lại qua readback/metrics.

### 17.1. Repair job phải idempotent

Nếu repair được giao lại sau crash, nó không được nhân đôi counter hoặc xóa projection mới hơn. Nên dùng stable repairId, action “set/recompute to expected state” có version guard, thay vì cộng phần chênh lệch mù.

### 17.2. Không xóa record “thừa” trước khi xác minh

Projection có product P100 nhưng source scan không thấy. Có thể source snapshot thiếu tenant partition, filter sai hoặc record đã được chuyển archive. Trước khi xóa, phải xác minh thẩm quyền, xóa mềm/hard delete contract và phạm vi snapshot. Với dữ liệu pháp lý hoặc audit, một lệnh xóa thiếu kiểm soát có thể gây mất bằng chứng.

## 18. Rebuild projection có thể chuyển đổi không downtime

Khi drift lan rộng hoặc transform logic thay đổi, dựng mới có thể an toàn hơn sửa tại chỗ.

Một workflow rebuild:

~~~mermaid
flowchart TD
    A["Select source snapshot + watermark"] --> B["Create new projection generation"]
    B --> C["Backfill / replay historic data"]
    C --> D["Catch up live events after watermark"]
    D --> E["Validate counts, versions, hashes, queries"]
    E --> F{"Acceptance criteria met?"}
    F -- "No" --> G["Investigate / retry without cutover"]
    F -- "Yes" --> H["Atomic pointer / alias cutover"]
    H --> I["Monitor new generation"]
    I --> J["Retire old generation after rollback window"]
~~~

### 18.1. Dùng generation riêng

Tạo projection v2 hoặc index_v2 thay vì xóa index cũ rồi build lại trong lúc client đang dùng. Khi dữ liệu mới đã đủ và được xác minh, chuyển alias hoặc routing pointer atomically nếu hạ tầng hỗ trợ.

Với SQL read model, có thể dùng tables/generation column và một lớp routing hoặc view switch có kế hoạch. Điều kiện atomicity phụ thuộc engine và cách deploy.

### 18.2. Catch up với live stream

Nếu build mất 4 giờ, events phát trong 4 giờ vẫn phải được áp dụng. Có thể:

- Snapshot + CDC from watermark.
- Dual-consume live events vào generation mới.
- Replay từ offset đã bảo vệ.
- So checkpoint/versions rồi cutover.

Phải tránh **gap** (mất updates ở ranh giới snapshot/stream) và **overlap tạo trùng** (cùng update từ snapshot và CDC được áp hai lần). Thiết kế idempotent + version guards giải quyết overlap khi phù hợp; CDC snapshot semantics phải được thử.

### 18.3. Kiểm chứng trước cutover

Không chỉ so count:

- Số records theo tenant/partition.
- Status distribution và business aggregates.
- Version và checksum/key-level diff.
- Query correctness trên mẫu đủ đa dạng.
- API latency và search relevance nếu áp dụng.
- Access control/tenant isolation.
- Freshness/lag khi chuyển sang stream.
- Khả năng rollback và chi phí duy trì song song.

### 18.4. Rollback

Giữ projection cũ một khoảng đủ theo chính sách để có thể chuyển lại nếu generation mới có lỗi. Không xóa ngay sau cutover. Nếu dữ liệu đã tiến hóa tiếp, rollback cũng cần kế hoạch catch up, không đơn giản trỏ về index cũ đã ngừng nhận events lâu.

## 19. Event sourcing: nguồn sự kiện chính là dữ liệu có thẩm quyền

Trong **event sourcing**, aggregate state được dựng bằng cách fold chuỗi sự kiện:

~~~text
OrderCreated
ItemAdded
ItemAdded
OrderConfirmed
PaymentCaptured
OrderCancelled
~~~

Projection của trạng thái hiện tại có thể được tính:

~~~text
state_0 = initialState
state_1 = apply(state_0, event_1)
...
state_n = apply(state_(n-1), event_n)
~~~

Điều kiện:

- Event schema đủ thông tin.
- Thứ tự theo aggregate được xác định.
- Transformation có versioning và deterministic behavior.
- Event log còn đủ lịch sử hoặc có snapshot đáng tin.
- Side effects như email/charge không được phát lại khi rebuild read model.

### 19.1. Snapshot không thay event history theo mọi use case

Snapshot giúp giảm thời gian rebuild, nhưng cần biết snapshot tại aggregateVersion nào và những events tiếp theo. Nếu snapshot cũ hoặc bị corrupt, có thể cần replay thêm từ event store. Không xóa events quan trọng chỉ vì đã có snapshot mà không có retention/compaction policy rõ.

### 19.2. Một lỗi ở projection không có nghĩa event store sai

Nếu event store giữ chuỗi sự kiện hợp lệ, projection có thể được rebuild. Nhưng event store cũng có thể chứa command sai/bug nghiệp vụ đã commit; khi đó phải dùng correction/compensating event theo domain, không âm thầm sửa hoặc xóa lịch sử ngoài contract.

## 20. Transactional DB + Outbox: nguồn không nhất thiết là event log

Trong kiến trúc không dùng event sourcing, event có thể chỉ chứa **thông báo thay đổi**, không đủ lịch sử tái tạo đầy đủ state. Ví dụ:

~~~json
{
  "eventType": "ProductUpdated",
  "productId": "P100",
  "aggregateVersion": 18
}
~~~

Nếu consumer bị chậm hoặc event mất, có thể query Catalog Service/DB để lấy state mới nhất. Nhưng nếu cần báo cáo lịch sử giá từng giờ, current Product state không đủ; phải có history/ledger hoặc events có nội dung đầy đủ theo contract.

**Quy tắc:** quyết định rebuild từ **event log**, **snapshot database** hay **business ledger** phải dựa trên điều gì là authoritative và lịch sử nào cần bảo toàn.

## 21. Đối soát aggregate/counter cần cẩn trọng hơn bản ghi trạng thái

Với projection order-by-id, có thể recompute toàn bộ record từ Order source. Với revenue/counter, nguy cơ double count và ordering cao hơn.

Ví dụ RevenueDaily:

~~~text
PaymentCaptured(paymentId=P1, amount=200000, currency=VND)
PaymentCaptured(paymentId=P2, amount=300000, currency=VND)
RefundSucceeded(refundId=R1, paymentId=P1, amount=50000)
Expected net (minh họa) = 450000 VND
~~~

Nếu P1 được phát lại, một handler cộng thêm 200000 có thể tạo doanh thu 650000. Nếu RefundSucceeded bị bỏ sót, báo cáo lại cao 50000.

Cách bảo vệ:

- Lưu facts với business IDs unique.
- Định nghĩa rõ payment/refund nào được tính và ngày ghi nhận.
- Tổng hợp từ facts thay vì chỉ counter không có lịch sử.
- Upsert facts idempotent.
- Recompute partition ngày/currency từ authoritative facts khi reconciliation.
- Kiểm soát late transactions, timezone, partial refund và adjustment.

**Không dùng SUM của một projection bị nghi sai để chứng minh chính projection đó đúng.** Cần nguồn tham chiếu độc lập có thẩm quyền.

### 21.1. Sửa counter bằng delta có an toàn không?

Chỉ khi biết chắc chênh lệch và nguyên nhân, có concurrency guard và tránh áp delta lần hai. Nếu không, recompute/set expected total theo snapshot/version thường dễ kiểm chứng hơn. Với reporting, rebuild theo partition/time bucket có thể phù hợp.

### 21.2. Định nghĩa metric có thể khác dữ liệu nguồn

OrderCancelled không đồng nghĩa mọi khoản thanh toán đã hoàn tiền; RefundPending khác RefundSucceeded. Nếu báo cáo doanh thu quy định loại trừ chưa settled thì đối soát phải dùng **đúng quy tắc kế toán**, không chỉ so số đơn CONFIRMED.

## 22. Xử lý deletes, tombstones và TTL

Một projection có thể bị sai theo hai hướng:

- Record bị thiếu dù source còn hiệu lực.
- Record còn tồn tại dù source đã xóa hoặc phải ẩn.

Một **tombstone/delete event** mang identity/version và semantics xóa có thể giúp downstream xóa hoặc vô hiệu hóa record. Nhưng cần cẩn trọng:

- “Xóa mềm” khác xóa cứng.
- Hết TTL ở cache không đồng nghĩa source đã xóa nghiệp vụ.
- Search index phải xóa tài liệu cũ theo tenant.
- Retention của event log có thể làm mất dấu xóa nếu rebuild từ snapshot không đầy đủ.
- Khôi phục từ backup cũ có thể vô tình làm sống lại record đã bị xóa.
- Quy định quyền riêng tư yêu cầu xóa/ẩn ở read models, logs, archives tùy chính sách pháp lý.

### 22.1. Guard theo version cho delete

Nếu event Delete(version=12) đến sau Create(version=13), không được xóa record mới chỉ vì delete vừa tới. Có thể lưu tombstone với version ngay cả khi tài liệu đã bị xóa, để chặn các event update cũ “hồi sinh” record.

### 22.2. Data retention và sự kiện lịch sử

Một hệ cần khả năng rebuild trong 12 tháng nhưng broker chỉ giữ 7 ngày phải có archive/event store hoặc snapshot/backfill đáng tin. Retention của projection, event log, source history và backup phải được thiết kế cùng nhau.

## 23. Schema evolution: vì sao replay code mới có thể khác dữ liệu cũ?

Sự kiện tồn tại lâu hơn nhiều vòng deploy. Ví dụ version 1 dùng total là số tiền VND dạng decimal; version 2 dùng totalMinor kiểu integer; version 3 thêm currency.

Nếu projector xử lý event v1 như v3, có thể nhân/chi sai số hoặc lỗi serialization. Hệ cần:

1. Gắn schemaVersion trong event.
2. Có serializer/upcaster hoặc compatibility layer.
3. Kiểm tra default/missing fields.
4. Có test với fixtures event cũ.
5. Gắn projectionDefinitionVersion.
6. Định nghĩa khi nào phải rebuild toàn bộ.
7. Không xóa code xử lý event cũ khi còn replay/backfill cần nó.

### 23.1. Biến đổi dữ liệu phụ thuộc external lookup

Nếu event ProductPriceChanged chỉ có sku và projectors lookup giá hiện tại, replay quá khứ có thể tạo một mức giá khác thời điểm phát event. Khi cần lịch sử chính xác, event hoặc authoritative history phải lưu dữ liệu đủ và versioned reference.

### 23.2. Schema migrations có thể tạo false drift

Một projection v2 có thêm field mới không có trong v1. Nếu đối soát so hash của v1 với hash v2 theo byte, mọi record đều mismatch. Phải dùng canonical business fields và cùng projection definition version.

## 24. Một service có nhiều tenant và bảo vệ phạm vi đối soát

Một SaaS có nhiều khách hàng có thể dùng chung broker/topic/index, nhưng dữ liệu vẫn phải có tenant boundary. Trong reconciliation:

- Mọi source lookup và projection query phải có tenant authorization.
- Composite key cần gồm tenantId nếu business ID chỉ unique theo tenant.
- Rebuild không được merge dữ liệu tenant A vào tenant B.
- Search aliases/filters phải bảo vệ visibility.
- Repair logs không nên chứa payload PII hoặc dữ liệu của tenant khác.
- Job batch phải có rate limits/fairness để một tenant lớn không làm nghẽn các tenant khác.

Một lỗi data drift do thiếu tenant filter có thể nghiêm trọng hơn thiếu record: nó có thể làm **rò rỉ dữ liệu**. Cần coi đây là sự cố bảo mật và xử lý theo quy trình phù hợp.

## 25. Mô hình lưu trạng thái đối soát bền vững

Một reconciliation job có thể kéo dài nhiều giờ, nên cần state bền vững:

~~~sql
CREATE TABLE reconciliation_jobs (
    job_id TEXT PRIMARY KEY,
    projection_name TEXT NOT NULL,
    projection_generation TEXT,
    definition_version INTEGER NOT NULL,
    source_watermark TEXT,
    state TEXT NOT NULL,
    next_cursor TEXT,
    scanned_count BIGINT NOT NULL DEFAULT 0,
    mismatch_count BIGINT NOT NULL DEFAULT 0,
    repaired_count BIGINT NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE reconciliation_findings (
    job_id TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    tenant_id TEXT,
    expected_version BIGINT,
    actual_version BIGINT,
    finding_type TEXT NOT NULL,
    state TEXT NOT NULL,
    expected_hash TEXT,
    actual_hash TEXT,
    last_error_code TEXT,
    PRIMARY KEY (job_id, aggregate_id, tenant_id)
);
~~~

Đây là ví dụ logic, không phải schema cố định; lựa chọn primary key cần theo đặc tính nullable/tenant của database thực tế. Có thể dùng một non-null tenant scope key để tránh semantics UNIQUE với NULL gây nhận trùng ngoài ý muốn.

### 25.1. Vì sao cần job cursor?

Nếu job quét một triệu records rồi process crash ở record thứ 900.000, lưu cursor giúp resume mà không cần quét lại toàn bộ. Nhưng cursor phải được cập nhật **sau khi findings của batch được ghi bền vững**. Nếu cursor nhảy trước commit, một đoạn dữ liệu có thể bị bỏ qua.

### 25.2. Lưu repair audit

Mỗi repair nên có:

- Repair/job ID.
- Projection name, generation và source watermark.
- Key/tenant theo quyền cho phép.
- Expected vs actual version/hash.
- Loại sai lệch.
- Điều kiện guarded update và kết quả.
- Tác nhân tự động/người phê duyệt.
- Thời điểm, lý do và liên kết incident.
- Trạng thái post-repair verification.

Không cần lưu toàn bộ bản ghi chứa thông tin nhạy cảm nếu hash/reference đủ cho điều tra.

## 26. Thuật toán reconciliation hai pha

Một luồng thực dụng:

### Pha A — Discover

~~~text
start reconciliation job with source watermark W
for each assigned partition or key range:
    read source snapshot at/compatible with W
    compute expected projection under definition D
    read actual projection and its version
    classify differences:
        MISSING, EXTRA, STALE, CONTENT_MISMATCH, GAP
    write findings durably
    commit batch cursor
~~~

### Pha B — Repair

~~~text
for each unresolved finding:
    fetch authoritative state again if needed
    ensure tenant and definition version are correct
    calculate expected state and sourceVersion
    read current projection version/generation
    if a newer correct state already exists:
        mark finding RESOLVED_BY_LIVE_STREAM
    else if guarded update is safe:
        upsert/delete projection using version guard
        verify post-write state
        mark finding REPAIRED
    else:
        mark NEEDS_REVIEW with reason and owner
~~~

Tách discover và repair giúp kiểm soát rủi ro và có thể duyệt thay đổi trước khi ghi. Một hệ nhỏ có thể thực hiện từng batch trong cùng worker, nhưng **không bỏ qua snapshot/guard** khi live traffic vẫn tiếp tục.

### 26.1. Không sử dụng một update vô điều kiện

Ví dụ:

~~~sql
UPDATE order_read_model
SET status = 'CONFIRMED',
    last_source_version = 12
WHERE order_id = 'O-8421'
  AND last_source_version < 12;
~~~

Câu lệnh chỉ minh họa một guard. Nếu projection đã ở version 12 nhưng nội dung sai, cần cơ chế repair khác và generation/version của definition. Nếu projection version 13, lệnh trên no-op, tránh downgrade.

### 26.2. Đối soát một record vẫn có thể cần nhiều bảng

OrderByCustomer có thể gồm một bảng root và bảng items. Sửa một bảng mà không sửa bảng kia có thể tạo read model không nhất quán. Nếu cùng database, nên commit các thay đổi liên quan trong local transaction. Nếu projection gồm nhiều stores, cần mô hình publish/swap generation hoặc workflow repair có thể phục hồi.

## 27. Java/Spring Boot: phác thảo projector có version guard

Ví dụ mã minh họa cơ chế, không phải project chạy sẵn:

~~~java
@Service
public class OrderProjectionHandler {

    private final ProjectionInboxRepository inbox;
    private final OrderReadRepository readModel;

    public OrderProjectionHandler(
            ProjectionInboxRepository inbox,
            OrderReadRepository readModel) {
        this.inbox = inbox;
        this.readModel = readModel;
    }

    @Transactional
    public void onOrderStatusChanged(OrderStatusChanged event) {
        boolean fresh = inbox.tryInsert(
            "order-read-model", event.eventId());

        if (!fresh) {
            return;  // Duplicate message.
        }

        var current = readModel.findByOrderIdForUpdate(
            event.orderId());

        if (current.isPresent()
                && current.get().sourceVersion() >= event.version()) {
            return;  // Older or same-version state.
        }

        if (event.isFullStateEvent()) {
            readModel.upsertFromEvent(event);
        } else {
            readModel.applyDeltaWithGapCheck(event);
        }
    }
}
~~~

Các điều kiện production:

- Inbox marker và projection update dùng **cùng transaction** thực.
- tryInsert phải atomic nhờ UNIQUE/upsert, không phải check rồi insert không khóa.
- Nếu handler gặp gap version, không nên commit marker rồi đánh mất khả năng áp delta: có thể lưu event vào pending-gap queue và quản lý trạng thái riêng, hoặc rollback để retry theo policy.
- readModel cần business key/tenant scope, concurrency guard và schema validation.
- Broker ACK/offset được commit sau DB transaction theo framework semantics.
- Trường hợp invalid schema/permanent error phải có DLQ/quarantine và owner.
- Không dùng listener này để gửi email/charge trong replay mode.

**Cảnh báo:** ví dụ code coi sự kiện full-state có thể bỏ qua các version trung gian trong phạm vi projection trạng thái hiện tại; nếu projection còn có side effects/counters phụ thuộc mọi delta, phải xử lý đầy đủ các biến đổi.

## 28. Java/Spring Boot: phác thảo repair theo source version

Một repair service có thể nêu ranh giới:

~~~java
@Service
public class OrderProjectionRepair {

    private final OrderAuthoritativeClient source;
    private final OrderReadRepository readModel;
    private final RepairAuditRepository audit;

    public OrderProjectionRepair(
            OrderAuthoritativeClient source,
            OrderReadRepository readModel,
            RepairAuditRepository audit) {
        this.source = source;
        this.readModel = readModel;
        this.audit = audit;
    }

    public void repair(String tenantId, String orderId, String repairId) {
        // Call source outside local read-model DB transaction.
        var authoritative = source.getOrderState(tenantId, orderId);
        var expected = OrderProjectionMapper.map(authoritative);

        // In production: execute guarded upsert and audit atomically.
        boolean applied = readModel.upsertIfVersionOlder(
            tenantId, orderId, expected, authoritative.version());

        audit.recordRepairAttempt(
            repairId, tenantId, orderId,
            authoritative.version(), applied);
    }
}
~~~

Mã chỉ phác thảo; còn thiếu transaction boundaries, retries, same-version corruption handling, snapshot coherence, permission checks và bảo vệ race. Production nên:
- Đảm bảo guarded upsert và audit cùng transaction nếu cần.
- Dùng nguồn được phân quyền, không trực tiếp truy cập DB của service khác trái ownership.
- Có retry budget và deadline cho source lookup.
- Nếu source không xác định được trạng thái, không xóa projection mù.
- Repair task idempotent bằng repairId/operation identity.
- Không cho một repair cũ ghi đè live update có version mới hơn.

## 29. Case study 1: OrderByCustomer thiếu đơn sau outage

**Giả định:** Order DB chứa O-8421, version 8, status CONFIRMED. Bảng OrderByCustomer có version 6, status PENDING. Broker từng outage 40 phút; một số events còn trong outbox.

### 29.1. Chẩn đoán

1. Kiểm tra Order authoritative state/version.
2. Xác định outbox event version 7/8 đã commit và đã publish chưa.
3. Kiểm tra broker retention/partition/offset.
4. Kiểm tra projector lag, retry và DLQ.
5. Kiểm tra inbox event IDs/version.
6. Xác định read-model DB write có lỗi hoặc một consumer đã ACK sớm.
7. Phân biệt “chưa đến” và “đã qua checkpoint nhưng state vẫn cũ”.

### 29.2. Phục hồi

Nếu event còn và projector có logic đúng, có thể replay từ một checkpoint an toàn với idempotency. Nếu event đã không còn hoặc cần trạng thái hiện tại, recompute O-8421 từ Order source và guarded upsert version 8.

Sau sửa, kiểm tra:
- status và version đúng.
- customerId/tenant đúng.
- những live events mới hơn không bị ghi đè.
- outbox/broker/consumer không còn backlog bất thường.
- drift monitor không báo lại cùng mismatch sau grace period.

Không chỉ sửa một row rồi bỏ qua nguyên nhân vì những order khác có thể cũng bị mất.

## 30. Case study 2: Search index giữ sản phẩm đã xóa

**Giả định:** Catalog đã ngừng hiển thị product P100, nhưng Search API vẫn trả P100.

Khả năng:

- Không phát ProductDeleted/ProductUnpublished.
- Tombstone bị bỏ qua.
- Consumer search index lỗi nhưng ACK message.
- Search refresh/cache trễ.
- Index alias đang trỏ generation cũ.
- Tenant filter hoặc status filter sai.
- Một event ProductUpdated cũ đã “hồi sinh” document sau delete.

### 30.1. Phương án xử lý

1. Xác minh Catalog authoritative state và version.
2. Kiểm tra delete/unpublish event, outbox và indexing logs.
3. Kiểm tra index document version/alias/cache.
4. Nếu document phải bị xóa, gửi **versioned delete** theo policy.
5. Chặn stale update event tạo lại document cũ.
6. Bổ sung tombstone/version retention thích hợp.
7. Test replay, index rebuild và data deletion/privacy obligations.

Với sản phẩm chỉ bị unpublish tạm thời, có thể cần cập nhật status/filter chứ không xóa metadata hoàn toàn. Quyết định phụ thuộc domain.

## 31. Case study 3: báo cáo doanh thu bị nhân đôi

**Giả định:** payment event E100 được redeliver sau consumer crash. RevenueDaily projection tăng doanh thu lần hai.

### 31.1. Phát hiện

- Source payment facts có mỗi paymentId duy nhất.
- RevenueDaily tổng lớn hơn số liệu tính lại từ facts có thẩm quyền.
- Inbox thiếu marker E100 hoặc marker không commit cùng counter.
- Broker có redelivery sau outage.

### 31.2. Phục hồi

Không nên đơn giản trừ một khoản bằng tay nếu có khả năng nhiều duplicates khác. Nên:

1. Xác định business definition của doanh thu theo currency/day.
2. Chọn snapshot/watermark và authoritative payment/refund facts.
3. Recompute từng affected bucket/partition.
4. Ghi kết quả với generation/version guard hoặc swap bảng tổng hợp.
5. Sửa consumer để dedup atomically.
6. Replay/fault-test crash sau commit trước ACK.
7. Audit điều chỉnh báo cáo và nguyên nhân sự cố.

Nếu dữ liệu ảnh hưởng báo cáo tài chính chính thức, cần quy trình phê duyệt/đối chiếu theo governance; không tự coi read model là sổ cái kế toán.

## 32. Case study 4: event sourcing có projection version lỗi

**Giả định:** event store chứa 10 triệu Order events. Một phiên bản projector dùng sai logic tính discount trong 2 ngày, ảnh hưởng nhiều bản ghi.

Phương án phù hợp có thể là:

1. Sửa logic/definition và gắn version mới.
2. Dùng event store authoritative và snapshot/replay tương thích schema cũ.
3. Build projection generation mới song song với live.
4. Catch up tới watermark và so kết quả.
5. Chạy domain acceptance tests trên nhiều kiểu đơn.
6. Alias/routing cutover khi đã đủ bằng chứng.
7. Giữ generation cũ trong rollback window.
8. Có kế hoạch nếu found mismatch sau cutover.

Không dùng một script UPDATE giảm total đồng loạt nếu discount rules thay đổi qua thời gian và cần replay chính xác.

## 33. Observability cho projection integrity

Một bộ chỉ số hữu ích:

| SLI / metric | Ý nghĩa |
| --- | --- |
| End-to-end propagation latency p50/p95/p99 | Source commit tới projection được áp dụng |
| Outbox oldest pending age | Intent chưa được publish |
| Broker consumer lag per partition | Consumer theo sau bao xa |
| Projection write failure rate | DB/index update thất bại |
| Inbox duplicate hit rate | Redelivery được phát hiện |
| Version gap count | Thiếu sequence theo aggregate |
| Out-of-order event count | Nhận version thấp hơn hiện tại |
| Drift findings by type | MISSING/EXTRA/STALE/CONTENT_MISMATCH |
| Drift rate per million aggregates | Tỷ lệ sai lệch theo quy mô |
| Oldest unresolved drift age | Sai lệch tồn đọng lâu nhất |
| Reconciliation scan coverage | Bao nhiêu keys/partitions đã kiểm |
| Reconciliation duration/cost | Chi phí chạy đối soát |
| Repair success/failure/conflict | Hiệu quả sửa và race với live |
| Projection generation freshness | Bản rebuild có bắt kịp live |
| DLQ backlog and age | Message không thể xử lý |
| Business anomaly rate | Doanh thu sai, sản phẩm bị lộ, đơn thiếu |

Các metric cần label vừa đủ. Đừng gắn mỗi orderId làm metrics label gây cardinality quá lớn; orderId phù hợp cho structured logs/traces/audit thay vì time-series metrics.

### 33.1. Alert phải phân biệt lag và drift

Một alert “consumer lag > 1 phút” và alert “bản chiếu có 500 records lệch quá 1 giờ” có ý nghĩa khác nhau. Lag có thể giảm khi tăng consumer capacity, còn drift do ACK sớm có thể không tự hết sau khi lag về 0.

### 33.2. Recovery SLO

Ví dụ minh họa:
- 99% source changes visible trong 30 giây.
- Drift trên dữ liệu đặt hàng được phát hiện trong 15 phút.
- Mismatch đã xác minh có owner trong 30 phút và hướng xử lý trong 2 giờ.
- Các projection quan trọng có kế hoạch rebuild và thời gian khôi phục được diễn tập.

Con số phải được thống nhất với nghiệp vụ, tải và chi phí; không áp một bộ SLO minh họa cho mọi hệ thống.

## 34. Chi phí của reconciliation

Đối soát không miễn phí. Nó tiêu tốn:

- Read I/O trên authoritative DB.
- Data transfer giữa regions/cloud accounts.
- CPU cho canonicalization/hash/aggregation.
- Storage cho snapshots, staging/index generations.
- Broker replay và consumer resources.
- Write amplification khi repair/reindex.
- Nhân sự vận hành, audit và xử lý ngoại lệ.

### 34.1. Tránh đè tải production

Không scan toàn bảng Order ở giờ checkout cao điểm nếu ảnh hưởng latency giao dịch. Có thể:
- Dùng read replica/snapshot phù hợp consistency.
- Batch nhỏ với rate limit.
- Partition theo tenant/date/key.
- Ưu tiên changed keys và critical projections.
- Tạm dừng khi source quá tải.
- Có concurrency cap, retry backoff và circuit breaker.
- Cân bằng deadline với mức độ quan trọng của dữ liệu.

Một job reconciliation gây outage cho source sẽ làm vấn đề tồi hơn sai lệch ban đầu.

### 34.2. Chọn tần suất theo rủi ro

Một search index sản phẩm có thể chấp nhận eventual consistency vài giây và scan theo ngày. Một ledger/revenue projection cho quyết định tài chính có thể cần đối soát chặt hơn, theo từng batch hoặc song song với luồng transaction. Phải dựa trên **chi phí của sai lệch**, không chỉ chi phí chạy job.

## 35. Quản trị quyền truy cập và audit

Reconciliation worker có thể được cấp quyền đọc nhiều dữ liệu và sửa projection hàng loạt, nên là thành phần nhạy cảm:

- Dùng service identity riêng, least privilege.
- Không cho repair worker sửa authoritative source trừ quy trình được cho phép riêng.
- Hạn chế phạm vi tenant, entity và field có thể sửa.
- Dùng approval cho high-impact repair.
- Bảo vệ secrets, audit logs và dữ liệu nhạy cảm.
- Có dry-run mode để xem số record dự kiến đổi.
- Ghi jobId, actor, timestamp, scope, evidence và kết quả.
- Quản lý retention của findings và backup theo quy định.

Nếu repair script không có guard hoặc chạy nhầm tenant, nó có thể gây sự cố lớn hơn drift. Cần cơ chế dừng, giới hạn batch, canary và rollback.

## 36. Khôi phục sau mất event do retention hoặc DLQ

### 36.1. Event còn trong broker

Nếu log còn nguyên và logic projector đã sửa, có thể tạo consumer group/replay từ offset phù hợp hoặc reset offset theo quy trình kiểm soát. Nhưng phải tránh:
- Giao lại commands gây external side effects.
- Ghi trùng counters.
- Áp event cũ lên projection mới hơn.
- Bỏ qua schema evolution.
- Commit offset không tương ứng projection transaction.

### 36.2. Event không còn

Nếu retention xóa mất events cần replay:
- Xác định authoritative source còn dữ liệu hiện tại/historical facts gì.
- Backfill từ snapshot/historical database/object archive.
- Catch up live changes qua CDC/watermark.
- Nếu không thể tái tạo lịch sử cần thiết, báo rõ **giới hạn khôi phục** và escalate nghiệp vụ; không bịa số liệu từ current state.

### 36.3. Event trong DLQ

DLQ giữ record lỗi, nhưng không tự sửa projection. Cần phân loại schema lỗi, temporary failure, permission error và poison message. Sau khi sửa nguyên nhân, replay có kiểm soát; xác nhận inbox/version/offset rồi kiểm tra lại projection.

### 36.4. Sau disaster recovery

Nếu restore projection từ backup cũ, phải replay changes sau snapshot hoặc rebuild từ source. Nếu restore source về thời điểm cũ nhưng projection chứa dữ liệu mới hơn, không thể chỉ cho live projector chạy tiếp mà không đánh giá consistency và những external side effects đã xảy ra. Cần disaster recovery runbook phối hợp các stores.

## 37. Runbook xử lý incident sai lệch dữ liệu

**Bước 1 — Phát hiện.** Alert drift, version gap, DLQ hoặc người dùng báo một record sai.

**Bước 2 — Bảo vệ nghiệp vụ.** Nếu data sai dẫn đến quyết định nguy hiểm (giá checkout, tồn kho, dữ liệu tenant), cân nhắc dùng source trực tiếp hoặc tắt read path phụ thuộc projection theo kế hoạch.

**Bước 3 — Xác định authoritative source.** Order DB, event store hoặc provider? Đừng sửa trước khi xác minh thẩm quyền.

**Bước 4 — Phân loại.** Lag chưa vượt SLO, missing, duplicate, out-of-order, content mismatch hay tombstone?

**Bước 5 — Chặn nguyên nhân lặp.** Ví dụ pause projector đang dùng logic sai, sửa consumer ACK order, khôi phục outbox publisher hoặc fix schema decoder.

**Bước 6 — Chọn watermark/snapshot.** Ghi rõ ranh giới dữ liệu để so sánh công bằng.

**Bước 7 — Ước lượng phạm vi.** Theo tenant, partition, time range, aggregate type và projection generation.

**Bước 8 — Dry run.** Thống kê expected changes, chi phí và rủi ro; duyệt nếu cần.

**Bước 9 — Repair hoặc rebuild.** Dùng stable job IDs, batches và version guards, có giới hạn tải.

**Bước 10 — Catch up live.** Đảm bảo events mới trong khi sửa không bị mất hoặc ghi đè.

**Bước 11 — Verify.** So count/hash/version/business invariants ở cùng watermark; kiểm tra sample API behavior và authorization.

**Bước 12 — Resume và monitor.** Theo dõi lag, mismatch recurrence, DLQ, read errors và performance.

**Bước 13 — Postmortem.** Ghi lý do, dữ liệu ảnh hưởng, thời gian sai lệch, chi phí/thiệt hại và các test/cảnh báo cần bổ sung.

Một script chạy thành công nhưng không xác minh sau repair **không** đủ để kết luận incident đã được giải quyết.

## 38. Những anti-pattern cần tránh

**1. Coi broker ACK là bằng chứng projection đúng.**  
ACK chỉ là một phần của giao thức, không chứng minh data transformation và DB commit đúng.

**2. So current source với projection ở một thời điểm khác.**  
Dễ báo sai lệch giả và sửa đè dữ liệu mới.

**3. Reset offset rồi replay mọi thứ ngay trên production.**  
Có thể duplicate side effect, quá tải và sai ordering.

**4. Cộng thêm giá trị chênh lệch mù vào counter.**  
Dễ nhân đôi khi job retry, hoặc che sai logic tổng hợp.

**5. Chỉ so record count.**  
Count bằng nhau không chứng minh content đúng.

**6. Hash raw JSON không canonicalize.**  
Thứ tự field và format timestamp có thể làm false mismatch.

**7. Chọn timestamp làm ordering duy nhất.**  
Clock skew và event delay có thể gây ghi đè sai.

**8. Sửa projection bằng event version cũ mà không guard.**  
Reconciliation có thể làm read model lùi.

**9. Sửa source theo projection vì projection “trông mới hơn”.**  
Phá quyền sở hữu và có thể ghi đè dữ liệu authoritative.

**10. Rebuild nhưng bỏ qua events đến trong lúc backfill.**  
Projection mới thiếu một khoảng thay đổi.

**11. Rebuild từ current state khi cần lịch sử.**  
Không tái tạo được payment/refund facts đã xảy ra.

**12. Bỏ qua delete/tombstone.**  
Dữ liệu đã xóa có thể tái xuất hiện và vi phạm quyền riêng tư.

**13. Không quản lý schema/projection definition version.**  
Replay code mới có thể tạo kết quả khác mà không biết tại sao.

**14. Dùng repair script không có idempotency.**  
Crash/retry làm nhân hiệu lực hoặc dữ liệu bị sửa nhiều lần.

**15. Không có owner cho DLQ và finding tồn đọng.**  
Workflow kẹt vĩnh viễn dù alert đã tắt.

**16. Quét source quá mạnh trong giờ cao điểm.**  
Đối soát tự gây outage.

**17. Dùng shared admin credentials để sửa mọi DB.**  
Vi phạm least privilege và tăng blast radius.

**18. Không phân biệt lag và drift.**  
Sửa dữ liệu chưa đến trong cửa sổ consistency hợp lệ.

**19. Không có rollback/cutover plan khi rebuild.**  
Search index mới sai nhưng đã xóa index cũ.

**20. Coi “exactly once” là miễn cần reconciliation.**  
Bảo đảm của broker có phạm vi; business projections và external effects vẫn cần xác minh.

## 39. Ma trận kiểm thử failure-injection

| Kịch bản | Kết quả phải kiểm chứng |
| --- | --- |
| Source DB commit, publisher crash trước publish | Outbox/CDC phát sau restart |
| Publisher publish thành công nhưng mất ACK | Redelivery không làm projection nhân hiệu lực |
| Consumer crash trước projection DB commit | Transaction rollback, event được retry |
| Consumer crash sau DB commit trước broker ACK | Inbox dedup, không cộng trùng |
| Event version 9 đến sau version 10 | Version guard ngăn ghi lùi |
| Consumer thấy gap version 8 -> 10 | Đưa vào replay/reconciliation, không áp delta sai |
| Schema v1 event replay với code v3 | Upcaster/compatibility đúng, không mất fields |
| Source đổi trong lúc repair scan | Snapshot/version guard tránh false repair |
| Repair worker crash sau một batch | Resume từ durable cursor, không bỏ phạm vi |
| Repair và live projector cùng ghi một key | Không overwrite version mới hơn |
| Rebuild index trong lúc live events đến | Catch-up không có gap/duplicate effect |
| Delete event đến muộn | Tombstone/version policy không xóa record mới |
| Consumer DLQ event vĩnh viễn | Finding có owner, replay sau fix |
| Broker retention mất events | Backfill hoặc báo giới hạn lịch sử minh bạch |
| Projection restore từ backup cũ | Replay/catch-up đến source watermark |
| Reconciliation chạy quá tải | Batch throttle, không làm p99 source vượt ngưỡng |
| Tenant A và B có cùng orderId | Không so/sửa chéo tenant |
| Duplicate payment/refund facts | Revenue aggregate không bị cộng hai lần |

Nên test bằng database/broker gần môi trường thật cho các ranh giới commit, UNIQUE và ordering. Unit mocks dễ bỏ qua race và transaction behavior.

## 40. Mẫu Architecture Decision Record

~~~markdown
# ADR: Đối soát OrderByCustomer projection

Trạng thái: Accepted (ví dụ)
Owner: Order Read Model Team

## Bối cảnh
- Order DB là authoritative source.
- Order Service publish changes qua transactional outbox.
- Kafka có thể redeliver và events có thể tới trễ.
- Read model phục vụ GET orders theo customer.
- Sai lệch kéo dài có thể ảnh hưởng hiển thị cho người dùng.

## Quyết định
- Events mang eventId, aggregateId, aggregateVersion, schemaVersion.
- Consumer ghi inbox marker và read model trong một local transaction.
- Mỗi record lưu lastSourceVersion và projectionDefinitionVersion.
- Có realtime lag monitoring, version gap alerts và periodic reconciliation.
- Reconciliation dùng source snapshot/watermark, key-level diff và guarded repair.
- Khi drift lớn, dựng projection generation mới và catch up CDC trước cutover.
- Mọi repair job có owner, audit, retry budget và rate limit.

## Giới hạn
- Read model là eventual consistent trong freshness SLO.
- Kafka offset không chứng minh business data correctness.
- Current Order state không tự tái dựng mọi historical metrics.
- External payment outcomes cần xác minh tại Payment owner/provider.
- Rebuild có thể mất thời gian và tiêu tốn thêm storage/compute.

## Kiểm chứng
- Crash trước/sau projection DB commit.
- Duplicate/out-of-order event.
- Snapshot/backfill + live catch-up.
- Repair concurrency với live updates.
- Tenant isolation và delete tombstone.
- Restore/drill và drift SLO.

## Triggers xem lại
- Drift rate hoặc age vượt ngưỡng.
- Rebuild mất quá lâu.
- Cost scanning tăng ngoài dự kiến.
- Source/broker retention không đủ.
~~~

ADR cần nêu **nguồn có thẩm quyền, phạm vi đúng, mức trễ được chấp nhận và giới hạn của cách sửa**.

## 41. Checklist triển khai đối soát đáng tin cậy

- [ ] Đã định nghĩa authoritative source theo từng aggregate/fact.
- [ ] Đã phân biệt event-sourced và DB + outbox/CDC architectures.
- [ ] Projection có owner, source mapping và definition version.
- [ ] Events có stable ID, aggregate ID, version và schema version.
- [ ] Source commit và publish có cơ chế đáng tin hoặc recovery.
- [ ] Consumer xử lý idempotent và ACK sau durable effect.
- [ ] Có gap/out-of-order detection theo aggregate.
- [ ] Có business invariants để biết projection thế nào là đúng.
- [ ] Có freshness SLO và grace period trước khi kết luận drift.
- [ ] Có watermark/snapshot strategy cho so sánh nhất quán.
- [ ] Có canonicalization rõ khi compare/hash.
- [ ] Có incremental scan hoặc partition-level reconciliation phù hợp quy mô.
- [ ] Repair theo stable job ID và có version/generation guards.
- [ ] Live projector và repair cùng tuân concurrency rules.
- [ ] Có kịch bản replay/backfill khi event log không còn đủ.
- [ ] Có rebuild generation, CDC catch-up, cutover và rollback plan.
- [ ] Xử lý delete/tombstone/retention và dữ liệu nhạy cảm.
- [ ] Có DR restore test và recovery runbook.
- [ ] Có metrics lag, drift, repair age, DLQ, outbox backlog và SLO.
- [ ] Có owner/escalation/manual review khi không thể xác minh.
- [ ] Có rate limits và cách dừng job để không gây sự cố mới.
- [ ] Đã fault-test crash, duplicate, late events, live repair race và tenant boundaries.

## 42. Bài tập thực hành

### Bài tập A — OrderProjection chậm hay sai?

Order DB chứa 10.000 đơn được cập nhật trong một giờ. Search/read model có 9.980 records đã nhìn thấy, consumer lag 4 phút và freshness SLO là 10 phút.

Hãy xác định:
1. Vì sao chưa thể kết luận 20 records là mất vĩnh viễn.
2. Những chỉ số nào cần xem ở outbox, broker, DLQ và projector.
3. Khi nào mismatch trở thành drift cần repair.
4. Cách chọn watermark để so sánh.
5. Cách xác minh sau khi consumer catch up.

### Bài tập B — Duplicate revenue

Consumer nhận PaymentCaptured event hai lần vì crash sau commit trước ACK. Projection lưu một counter duy nhất và bị tăng trùng. Hãy thiết kế inbox/business-key uniqueness, authoritative facts, partition recompute và post-repair verification.

### Bài tập C — Rebuild search index không downtime

Catalog có một triệu products, index v1 dùng analyzer cũ. Cần dựng v2 trong khi products vẫn được cập nhật. Hãy mô tả snapshot barrier, backfill, live catch-up, kiểm tra version/hash, alias swap và rollback.

### Bài tập D — Out-of-order + delete

Product P100 nhận ProductDeleted(version=12) rồi ProductUpdated(version=11). Làm sao đảm bảo product không “sống lại”? Nếu sau đó ProductRecreated(version=13) hợp lệ, làm sao cho phép trạng thái mới?

### Bài tập E — Event log không đủ retention

Một consumer bị dừng 20 ngày, broker chỉ lưu 7 ngày, projection cần lịch sử 12 tháng. Hãy xác định dữ liệu nào còn có thể khôi phục từ DB hiện tại, dữ liệu nào cần event archive/ledger và cách báo giới hạn nếu thiếu lịch sử.

### Bài tập F — Multi-tenant repair

Hai tenant đều có orderId O-100. Một job quét toàn hệ thống rồi upsert theo orderId mà không có tenantId. Hãy chỉ ra lỗi, thiết kế composite keys, quyền truy cập và audit để ngăn rò dữ liệu.

### Bài tập G — Repair race

Repair đọc source version=12, live consumer ghi version=13, repair sau đó ghi status của version=12. Hãy thiết kế optimistic/CAS guard, xử lý same-version hash mismatch và retry policy.

## 43. Tự kiểm tra kiến thức

1. Source event, event log, source of truth và projection khác nhau ở đâu?
2. Vì sao Kafka offset đã commit chưa chứng minh projection đúng?
3. Khi nào lag là hợp lệ và khi nào là drift?
4. Có những loại mismatch nào ngoài missing record?
5. Tại sao duplicate event nguy hiểm hơn với phép cộng counter?
6. Vì sao cần eventId và aggregateVersion cùng lúc?
7. Khi nào event version 10 có thể áp mà không cần version 9?
8. CDC/outbox giúp tránh lỗi gì giữa DB và broker?
9. Tại sao publisher/consumer vẫn cần idempotency?
10. Watermark và snapshot giúp tránh false positive nào?
11. Vì sao raw JSON hash có thể báo mismatch giả?
12. Count bằng nhau có đủ chứng minh hai projection giống nhau?
13. Repair từng key nên dùng version guard gì?
14. Tại sao rebuild phải catch up live changes?
15. Projection generation và alias swap giúp giảm downtime thế nào?
16. Khi nào event log không đủ để tái tạo historical report?
17. Delete tombstone cần version để làm gì?
18. Projection definition version khác event schema version thế nào?
19. Đối soát payment facts cần thẩm quyền từ đâu?
20. Khi nào phải manual review thay vì auto repair?
21. Những metric nào giúp phân biệt lỗi publisher, broker và projector?
22. Làm sao tránh reconciliation scan gây quá tải source?
23. Một job bị crash giữa batch nên resume thế nào?
24. Vì sao không dùng traceId làm dedup business key?
25. Làm sao kiểm chứng kết quả repair thay vì chỉ tin script chạy xong?

## 44. Kết luận

**Truyền sự kiện tin cậy không kết thúc ở việc message được gửi và ACK.** Giá trị của một event pipeline nằm ở việc những dữ liệu phục vụ đọc luôn có thể được giải thích, kiểm chứng và phục hồi theo nguồn sự thật có thẩm quyền.

Để đối soát khi nguồn sự kiện và bản chiếu sai lệch, cần xác định **authority**, **consistency window**, **event identity/version**, **checkpoint/watermark**, **invariants** và **khả năng rebuild**. Outbox/CDC giúp không bỏ quên thay đổi sau commit; inbox/idempotency giúp redelivery không nhân đôi effect; version guards và snapshot-consistent comparisons giúp repair không làm dữ liệu lùi trong lúc live events tiếp tục.

Reconciliation hiệu quả không chỉ tìm mismatch rồi ghi đè. Nó phải phân loại độ trễ và sai lệch thật, chọn replay/repair/rebuild phù hợp, bảo vệ quyền truy cập và business invariants, đo chi phí cũng như có audit, owner và post-repair verification. Khi những cơ chế này được thiết kế từ đầu, projection có thể bị gián đoạn tạm thời nhưng hệ thống vẫn có **đường khôi phục rõ ràng, an toàn và có thể kiểm chứng**.