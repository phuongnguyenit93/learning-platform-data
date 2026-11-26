# Replay sau di trú

Replay sau di trú là quá trình đọc lại các event đã được lưu trữ và áp dụng chúng vào consumer, projection hoặc mô hình dữ liệu mới sau khi hệ thống thay đổi schema, kiến trúc hoặc cách xử lý. Replay giúp hệ thống mới xây dựng lại trạng thái từ lịch sử đã có, đồng thời cho phép kiểm tra kết quả trước khi chuyển traffic. Đây là thao tác có ảnh hưởng đến dữ liệu và side effect, vì vậy cần có nguồn event đáng tin cậy, checkpoint rõ ràng, idempotency, kiểm soát thứ tự và kế hoạch cutover/rollback.

Trong Spring Modulith, application events là hợp đồng giao tiếp giữa các module. `@ApplicationModuleListener` xử lý event bất đồng bộ sau commit, còn Event Publication Registry theo dõi trạng thái publication đến transactional listener. Registry hỗ trợ phát hiện và phục hồi publication chưa hoàn tất; nó không mặc nhiên là event store lưu toàn bộ lịch sử để replay sau nhiều tháng. Muốn replay sau di trú, cần xác định nguồn lịch sử riêng như broker retention, event store, outbox/archive hoặc snapshot kết hợp event sau snapshot.

## 1. Khi nào cần replay sau di trú?

Replay thường cần thiết khi một phần của hệ thống thay đổi nhưng dữ liệu lịch sử vẫn phải được diễn giải theo mô hình mới:

- **Thay đổi schema event:** consumer mới cần đọc V1 và V2, hoặc dữ liệu cũ cần được chuyển đổi sang canonical model mới.
- **Thay đổi projection/read model:** cấu trúc bảng, cách tổng hợp hoặc logic hiển thị đã thay đổi và cần dựng lại dữ liệu đọc.
- **Tách hoặc hợp nhất module:** consumer mới tiếp nhận trách nhiệm trước đây thuộc module cũ.
- **Di chuyển broker hoặc topic:** message cần được chuyển từ hạ tầng cũ sang hạ tầng mới mà không bỏ sót event.
- **Sửa lỗi xử lý:** logic projection cũ đã tạo dữ liệu sai và cần tính lại từ nguồn lịch sử.
- **Khôi phục sau sự cố:** một read model hoặc consumer state cần được dựng lại từ nguồn dữ liệu bền vững.

Replay không phải lúc nào cũng là lựa chọn đúng. Nếu chỉ cần chuyển dữ liệu hiện tại, snapshot hoặc database migration có thể đơn giản hơn. Nếu lịch sử không đầy đủ, event không mang đủ dữ liệu và nguồn hiện tại không thể tái tạo trạng thái cũ, replay có thể tạo ra một kết quả thiếu hoặc sai.

## 2. Phân biệt replay, retry và resubmit

Ba hoạt động này có mục đích khác nhau và cần được vận hành riêng:

| Hoạt động | Phạm vi | Mục tiêu |
| --- | --- | --- |
| Retry | Một lần xử lý thất bại hoặc một message chưa hoàn tất. | Thử lại cùng công việc sau lỗi tạm thời. |
| Resubmit publication | Một publication cụ thể chưa hoàn tất trong cơ chế theo dõi publication. | Giao lại event đến transactional listener theo cơ chế framework. |
| Replay | Một tập event lịch sử theo khoảng thời gian, partition, aggregate hoặc checkpoint. | Dựng lại hoặc chuyển đổi trạng thái của consumer/projection. |

Event Publication Registry của Spring Modulith theo dõi publication đến listener và trạng thái hoàn tất. Registry có thể giúp phục hồi publication incomplete theo API/cơ chế của phiên bản đang dùng, nhưng không thay thế nguồn lịch sử đầy đủ. Không dùng bảng registry làm event store hoặc giả định rằng mọi event đã hoàn tất đều còn trong registry để replay.

Khi vận hành, hãy xác định rõ đang retry một event lỗi, resubmit publication incomplete hay chạy một replay migration. Mỗi hoạt động có checkpoint, quyền phê duyệt, metric và rủi ro side effect khác nhau.

## 3. Xác định nguồn event và khả năng replay

Trước khi chạy replay, lập danh sách nguồn dữ liệu và xác nhận nguồn nào có thể cung cấp lịch sử cần thiết.

| Nguồn | Có thể dùng để replay? | Điều cần xác minh |
| --- | --- | --- |
| Event store | Có, nếu lưu event bất biến và hỗ trợ đọc theo stream/sequence. | Tính đầy đủ, thứ tự, retention, schema cũ và checkpoint. |
| Kafka topic | Có trong thời gian retention còn hiệu lực. | Offset theo từng partition, retention, compaction, key và quyền đọc. |
| RabbitMQ queue | Có thể, nếu message vẫn còn trong queue hoặc archive. | Message đã ack có bị xóa không, dead-letter/TTL, ordering và khả năng export. |
| Outbox table | Có nếu bản ghi được giữ lại sau khi publish. | Cleanup policy, trạng thái publish, event ID và thứ tự. |
| Archive/object storage | Có nếu format và metadata đủ để đọc lại. | Integrity, encryption, schema version, manifest và thứ tự. |
| Event Publication Registry | Chủ yếu phục vụ trạng thái publication chưa hoàn tất. | Không mặc định chứa lịch sử hoàn tất lâu dài hoặc toàn bộ event. |
| Snapshot database | Có thể làm điểm bắt đầu kết hợp event sau snapshot. | Watermark/version của snapshot và tính nhất quán với event tiếp theo. |

Một nguồn replay tốt cần giữ được tối thiểu event ID, event type, schema version, aggregate ID, aggregate version/sequence, occurred time và payload. Với broker partitioned, cần thêm topic, partition và offset gốc. Nếu thiếu metadata để xác định thứ tự hoặc phạm vi, cần bổ sung manifest hoặc quy tắc chuyển đổi trước khi replay.

Không lấy thời gian tạo file archive làm thứ tự nghiệp vụ. Timestamp có thể trùng, lệch đồng hồ hoặc phản ánh thời điểm lưu trữ thay vì thời điểm event xảy ra. Ưu tiên sequence/version do nguồn phát sinh cung cấp; dùng offset trong partition cho thứ tự đọc của partition đó.

## 4. Xác định mục tiêu replay trước khi đọc lịch sử

Replay cần có mục tiêu cụ thể. Một chiến dịch có thể:

- tạo một projection mới từ event lịch sử;
- chuyển đổi payload V1 sang canonical model;
- đưa dữ liệu từ topic cũ sang topic mới;
- sửa một read model bị sai;
- kiểm chứng consumer mới trong chế độ shadow.

Mỗi mục tiêu có yêu cầu khác nhau về side effect. Rebuild projection thường chỉ ghi vào read model mới; replay để chuyển broker có thể chỉ publish message sang destination mới; replay business event để chạy lại quy trình thanh toán hoặc gửi thông báo có thể tạo tác động ngoài đời thực.

Trước khi bắt đầu, ghi rõ:

1. Consumer/projection đích và chủ sở hữu dữ liệu.
2. Khoảng lịch sử hoặc tập aggregate cần xử lý.
3. Schema version đầu vào và canonical/output version.
4. Những bảng, topic hoặc hệ thống ngoài được phép ghi.
5. Side effect nào phải tắt, mô phỏng hoặc chuyển sang outbox riêng.
6. Tiêu chí hoàn tất, đối soát và rollback.

Không dùng một cờ `replay=true` chung để âm thầm thay đổi mọi hành vi của ứng dụng. Chế độ replay cần có chính sách rõ ràng theo từng handler và được kiểm thử trước khi chạy dữ liệu thật.

## 5. Giữ nguyên danh tính và metadata của event

Khi phát lại cùng một sự kiện, hãy giữ nguyên `eventId`, `eventType`, `occurredAt`, `aggregateId`, `aggregateVersion` và `causationId`/`correlationId` gốc nếu chúng thuộc contract. Các giá trị này giúp consumer nhận diện duplicate, khôi phục quan hệ nhân quả và đối chiếu kết quả với nguồn.

Thông tin riêng của chiến dịch replay nên được thêm tách biệt:

| Metadata gốc | Metadata replay |
| --- | --- |
| `eventId` | `replayRunId` |
| `occurredAt` | `replayedAt` |
| `aggregateVersion` | `replaySource` / `sourceCheckpoint` |
| `correlationId` | `replayOperator` hoặc `migrationChangeId` theo audit policy |
| `schemaVersion` | `transformationVersion` |

Không thay `occurredAt` bằng thời điểm replay. Nếu cần ghi thời điểm chạy lại, dùng `replayedAt`. Không cấp event ID mới cho cùng event chỉ để vượt qua inbox/deduplication; làm vậy có thể khiến side effect được áp dụng lần nữa.

Nếu replay đã chuyển đổi payload sang schema mới, giữ được nguồn gốc bằng cách lưu `sourceSchemaVersion`, `targetSchemaVersion` hoặc metadata transformation trong log/manifest. Không âm thầm ghi đè bản event lịch sử gốc nếu nguồn được dùng làm bằng chứng hoặc audit.

## 6. Version hóa và chuyển đổi payload trong replay

Replay sau di trú thường đọc nhiều schema version. Consumer nên tách bước giải mã/chuyển đổi khỏi logic nghiệp vụ bằng một canonical model.

```java
public record EventEnvelope<T>(
        UUID eventId,
        String eventType,
        int schemaVersion,
        UUID aggregateId,
        long aggregateVersion,
        Instant occurredAt,
        T payload
) {}
```

```java
public CanonicalOrderEvent toCanonical(EventEnvelope<JsonNode> envelope) {
    return switch (envelope.schemaVersion()) {
        case 1 -> v1Mapper.toCanonical(envelope.payload(), envelope);
        case 2 -> v2Mapper.toCanonical(envelope.payload(), envelope);
        default -> throw new UnsupportedEventVersionException(
                envelope.eventType(), envelope.schemaVersion()
        );
    };
}
```

`CanonicalOrderEvent`, `v1Mapper` và `v2Mapper` là abstraction minh họa. Mỗi mapper cần có test cho payload thực tế của version tương ứng, trường thiếu, enum chưa biết, đơn vị tiền tệ và semantics. Không được tự suy ra giá trị bị thiếu nếu không có quy tắc nghiệp vụ đáng tin cậy.

Upcasting có thể chuyển V1 sang V2 hoặc chuyển trực tiếp mọi version về canonical model. Chuyển về canonical model thường giúp business handler không phải biết chi tiết schema lịch sử. Tuy nhiên, canonical model phải giữ được semantics cần thiết; không được bỏ thông tin quan trọng chỉ vì schema mới không có trường tương đương.

## 7. Checkpoint và watermark

Replay cần biết đã đọc và xử lý đến đâu để có thể tiếp tục sau sự cố mà không bỏ sót dữ liệu. Checkpoint là vị trí tiến độ đã được xác nhận; watermark là ranh giới lịch sử được chọn cho một lần chạy hoặc một giai đoạn migration.

Với Kafka, offset là tiến độ theo từng partition. Một checkpoint có thể là vector:

| Topic | Partition | Offset đã xử lý liên tục |
| --- | ---: | ---: |
| `orders-v1` | 0 | 1250 |
| `orders-v1` | 1 | 980 |
| `orders-v1` | 2 | 1442 |

Không dùng một offset toàn cục cho topic nhiều partition. Khi xử lý song song, chỉ ghi checkpoint đến offset liên tục cao nhất đã hoàn tất; không commit vượt qua record còn đang xử lý hoặc thất bại ở phía trước.

Với event store theo aggregate, checkpoint có thể là sequence cuối cùng của từng stream hoặc một global position nếu event store thực sự cung cấp thứ tự toàn cục. Với archive chia file, manifest cần ghi phạm vi sequence/partition và checksum.

Checkpoint chỉ được nâng sau khi tác động đích đã commit bền vững. Nếu ghi checkpoint trước khi cập nhật projection, sự cố có thể khiến event bị bỏ qua. Nếu cập nhật projection trước rồi dừng trước checkpoint, event có thể được xử lý lại; do đó consumer vẫn phải idempotent.

## 8. At-least-once và idempotency trong replay

Không giả định replay là exactly-once. Process có thể dừng sau khi ghi dữ liệu đích nhưng trước khi ghi checkpoint. Lần chạy tiếp theo sẽ đọc lại event. Cách an toàn phổ biến là at-least-once kết hợp idempotency.

Các cơ chế thường dùng:

- Inbox với unique key `(consumer_name, event_id)` để nhận diện event đã áp dụng.
- Upsert projection theo aggregate ID và chỉ nhận aggregate version mới hơn.
- Unique constraint theo business key để ngăn tạo bản ghi trùng.
- Ghi dữ liệu projection và checkpoint trong cùng transaction khi chúng nằm trong cùng database.
- Lưu replay run ID để phân biệt chiến dịch và phục vụ audit, nhưng không dùng nó thay event ID.

Ví dụ upsert có điều kiện version:

```sql
INSERT INTO order_summary (
    order_id, status, total_amount, source_version, updated_at
)
VALUES (
    :order_id, :status, :total_amount, :source_version, CURRENT_TIMESTAMP
)
ON CONFLICT (order_id) DO UPDATE
SET status = EXCLUDED.status,
    total_amount = EXCLUDED.total_amount,
    source_version = EXCLUDED.source_version,
    updated_at = CURRENT_TIMESTAMP
WHERE order_summary.source_version < EXCLUDED.source_version;
```

Đây là cú pháp PostgreSQL minh họa. Với event delta, chỉ so sánh version có thể không đủ nếu bỏ qua event trung gian làm mất tác động. Cần sequence liên tục, inbox theo event ID hoặc snapshot mới nhất phù hợp với semantics.

## 9. Giữ thứ tự khi replay

Thứ tự quan trọng khi event biểu diễn các thay đổi nối tiếp của cùng aggregate. Ví dụ `OrderCreated`, `OrderConfirmed`, `OrderShipped` phải được diễn giải theo thứ tự nghiệp vụ. Replay đảo thứ tự có thể tạo trạng thái không hợp lệ hoặc làm handler từ chối event.

Các nguyên tắc:

- Giữ thứ tự trong từng aggregate stream hoặc partition theo contract nguồn.
- Dùng aggregate version/sequence để phát hiện event thiếu, trùng hoặc đến sai thứ tự.
- Không giả định timestamp tạo ra một total order đáng tin cậy.
- Khi xử lý song song, phân vùng theo aggregate key hoặc chỉ commit đến sequence liên tục đã hoàn tất.
- Nếu phát hiện gap, dừng/đưa aggregate vào quarantine hoặc lấy snapshot đáng tin cậy; không tự bỏ qua gap.

Kafka bảo đảm thứ tự trong một partition, không phải thứ tự toàn cục giữa mọi partition. Nếu producer dùng aggregate ID làm message key, các event của cùng aggregate có thể được giữ trong một partition theo cấu hình topic. Khi thay đổi số partition hoặc key strategy, cần đánh giá lại giả định ordering trước khi replay.

## 10. Replay đồng thời với traffic mới

Một thách thức lớn là hệ thống vẫn phát event mới trong khi replay lịch sử. Nếu không xác định ranh giới, có thể bỏ sót event phát sinh trong lúc chuyển đổi hoặc áp dụng một event hai lần.

### Cách 1: Dừng ghi trong thời gian ngắn

1. Tạm dừng publisher hoặc command tạo event liên quan.
2. Ghi nhận watermark cuối cùng của nguồn.
3. Replay đến hết watermark.
4. Đối soát projection và dữ liệu nguồn.
5. Chuyển consumer/traffic sang hệ thống mới.
6. Mở lại publisher.

Cách này dễ hiểu nhưng tạo downtime hoặc hạn chế chức năng ghi. Chỉ phù hợp khi thời gian replay ngắn và nghiệp vụ chấp nhận khoảng dừng.

### Cách 2: Snapshot rồi catch up

1. Chụp snapshot nhất quán tại watermark `W`.
2. Dựng projection mới từ snapshot.
3. Replay event có sequence/position lớn hơn `W`.
4. Trong lúc catch up, tiếp tục ghi nhận event mới vào nguồn bền vững.
5. Khi projection mới đạt gần head position và lag nằm trong ngưỡng, chuyển traffic.

Snapshot và watermark phải được tạo nhất quán. Nếu snapshot không đại diện cho đúng trạng thái tại `W`, replay có thể bỏ sót hoặc áp dụng lặp một khoảng dữ liệu.

### Cách 3: Shadow consumer

Chạy consumer mới song song để ghi vào projection mới, trong khi consumer cũ vẫn phục vụ traffic đọc. So sánh kết quả, độ trễ và lỗi trong một khoảng đủ dài. Consumer shadow không được gửi email, thu tiền hoặc gọi side effect ngoài ý muốn.

Không cho hai consumer cùng ghi vào một bảng đích nếu chưa có cơ chế phân quyền, idempotency và version conflict rõ ràng. Dùng projection/bảng riêng giúp việc so sánh và rollback an toàn hơn.

## 11. Tách replay projection khỏi side effect nghiệp vụ

Một event handler có thể làm nhiều việc: cập nhật projection, gửi email, tạo hóa đơn, gọi payment API hoặc phát event tiếp theo. Khi replay lịch sử để dựng lại read model, thường chỉ muốn tính lại projection; chạy lại toàn bộ side effect có thể gây hậu quả thật.

Nên tách trách nhiệm:

- Projection handler chỉ cập nhật dữ liệu đọc và có thể rebuild.
- Business process handler xử lý command/event mới theo quy tắc nghiệp vụ.
- Notification/payment adapter chỉ chạy khi có một yêu cầu nghiệp vụ mới và idempotency key phù hợp.
- Event phát sinh từ migration/replay có metadata riêng và policy rõ ràng.

Nếu không thể tách handler, dùng một replay policy tường minh để vô hiệu hóa hoặc mô phỏng side effect không được phép. Không dựa vào biến môi trường tùy tiện mà không có test và audit. Mọi side effect được phép trong replay phải có idempotency, giới hạn phạm vi và log đầy đủ.

## 12. Replay và Spring Modulith

Spring Modulith cung cấp application event publication trong cùng ứng dụng và các listener theo ranh giới module. Khi dùng `@ApplicationModuleListener`, listener được xử lý bất đồng bộ sau commit theo cơ chế framework; Event Publication Registry theo dõi publication đến listener.

Đối với migration replay:

- Nếu mục tiêu là resubmit một publication incomplete, dùng API/cơ chế công khai của `EventPublicationRegistry` theo phiên bản Spring Modulith.
- Nếu mục tiêu là replay toàn bộ lịch sử, lấy event từ event store, broker, outbox/archive hoặc snapshot/history được thiết kế riêng.
- Nếu event cũ còn trong publication registry, code mới cần có khả năng deserialize hoặc có quy trình xử lý/quarantine trước khi resubmit.
- Nếu tạo projection mới, ưu tiên listener/consumer đích riêng để tránh ghi đè projection đang phục vụ traffic.
- Theo dõi publication incomplete riêng với replay backlog và broker consumer lag.

Không cập nhật trực tiếp bảng nội bộ của Event Publication Registry để tạo replay hoặc đánh dấu publication hoàn tất. Registry là cơ chế quản lý publication, không phải công cụ migration tổng quát.

## 13. Quy trình replay có kiểm soát

Một quy trình vận hành nên chia thành các giai đoạn có thể dừng và tiếp tục:

### Giai đoạn A — Chuẩn bị

1. Xác định mục tiêu, phạm vi event và consumer đích.
2. Kiểm tra nguồn lịch sử đầy đủ, quyền truy cập và retention.
3. Xác định schema version được hỗ trợ và transformation code.
4. Xác định side effect được phép, bị tắt và cần mô phỏng.
5. Tạo replay run ID, manifest và checkpoint ban đầu.
6. Chọn rate limit, concurrency, timeout và tiêu chí dừng.

### Giai đoạn B — Dry run

1. Đọc một tập mẫu đại diện cho mọi event type/version.
2. Deserialize và upcast payload.
3. Kiểm tra aggregate ID, sequence, event ID và dữ liệu bắt buộc.
4. Tính trước số lượng bản ghi dự kiến và các nhóm lỗi.
5. Chạy vào projection thử nghiệm hoặc chế độ không ghi.
6. Đối chiếu kết quả với nguồn và xác nhận không có side effect ngoài phạm vi.

### Giai đoạn C — Chạy replay

1. Đọc theo partition/stream/sequence và checkpoint đã chọn.
2. Áp dụng transformation xác định, có thể chạy lặp.
3. Ghi projection/inbox và checkpoint theo transaction phù hợp.
4. Giới hạn tốc độ để không làm quá tải database hoặc broker.
5. Đưa event lỗi không thể xử lý vào quarantine/DLQ có metadata gốc.
6. Ghi tiến độ theo replay run và nguồn dữ liệu.

### Giai đoạn D — Đối soát và cutover

1. Xác nhận đã đọc đến watermark mục tiêu.
2. Xác nhận không có partition/aggregate bị bỏ sót.
3. Đối chiếu số lượng, tổng hợp, version và các mẫu nghiệp vụ.
4. Kiểm tra lag của live consumer và xử lý phần event mới phát sinh.
5. Chuyển read traffic hoặc consumer ownership theo kế hoạch.
6. Theo dõi lỗi và giữ khả năng rollback trong cửa sổ đã định.

## 14. Checkpoint và ví dụ tiến độ replay

Một checkpoint nên ghi rõ nguồn, phạm vi, vị trí cuối cùng đã xử lý liên tục và replay run. Ví dụ cấu trúc lưu trạng thái:

```java
public record ReplayCheckpoint(
        UUID replayRunId,
        String sourceName,
        String streamOrTopic,
        int partition,
        long lastCompletedPosition,
        Instant updatedAt
) {}
```

Đây là mô hình minh họa. Với event store theo aggregate, khóa checkpoint có thể là aggregate ID và sequence. Với nguồn nhiều partition, cần một checkpoint riêng cho từng partition. Nếu consumer xử lý song song, chỉ ghi `lastCompletedPosition` đến vị trí liên tục cao nhất đã hoàn tất.

Checkpoint cần được cập nhật nguyên tử với projection khi cả hai ở cùng database transaction. Nếu checkpoint nằm ở hệ thống khác, thiết kế theo at-least-once và idempotency; không giả định hai lần ghi độc lập sẽ commit đồng thời.

Một replay run cũng nên có manifest chứa:

- source identity và khoảng thời gian/sequence/offset;
- schema version đầu vào và transformation version;
- target projection/topic;
- thời điểm bắt đầu/kết thúc;
- số event đọc, áp dụng, bỏ qua, lỗi và quarantine;
- checkpoint cuối của từng partition/stream;
- checksum hoặc thông tin integrity của archive nếu có.

## 15. Xử lý event lỗi trong replay

Replay có thể gặp payload hỏng, schema không hỗ trợ, aggregate version bị gap, dữ liệu tham chiếu đã bị xóa hoặc lỗi database tạm thời. Cần phân loại:

| Nhóm lỗi | Cách xử lý gợi ý |
| --- | --- |
| Lỗi tạm thời | Retry có giới hạn và backoff; giữ checkpoint trước event chưa hoàn tất. |
| Schema không hỗ trợ | Quarantine với raw payload được bảo vệ, event ID và schema version; cập nhật mapper rồi replay lại. |
| Payload không hợp lệ | Không tự sửa dữ liệu; ghi nhận nguyên nhân và yêu cầu xử lý nguồn. |
| Sequence gap | Dừng aggregate/partition theo policy hoặc lấy snapshot đáng tin cậy. |
| Duplicate | Inbox/version check nhận diện và bỏ qua an toàn. |
| Vi phạm nghiệp vụ lịch sử | Đưa vào exception workflow; không ép trạng thái hiện tại theo quy tắc mới nếu semantics cũ khác. |

Không tăng checkpoint qua một event lỗi nếu việc đó có thể làm mất thay đổi cần thiết. Nếu policy cho phép bỏ qua event, phải ghi quyết định skip vào manifest/audit với lý do và tác động đã đánh giá.

## 16. Đối soát sau replay

Replay hoàn tất về mặt đọc hết nguồn chưa có nghĩa dữ liệu đích đúng. Cần đối soát theo nhiều góc độ:

- Số event đọc bằng số event được phân loại thành applied, duplicate, skipped có phê duyệt hoặc quarantined.
- Không có khoảng trống offset/sequence trong phạm vi cần xử lý.
- Số aggregate được dựng lại phù hợp với nguồn.
- Tổng số lượng, tổng tiền hoặc các aggregate nghiệp vụ quan trọng khớp theo quy tắc.
- Projection version không thấp hơn watermark mong đợi.
- Không phát sinh side effect ngoài phạm vi replay.
- Consumer live không bị mất event trong giai đoạn cutover.

Với dữ liệu lớn, đối soát theo partition, ngày, tenant hoặc aggregate range. Dùng checksum/canonical representation khi có thể. Sai lệch cần được phân loại trước khi quyết định chạy lại toàn bộ hoặc một phạm vi nhỏ.

## 17. Cutover và rollback

Trước cutover, giữ projection cũ tiếp tục phục vụ traffic đọc trong khi projection mới được dựng và kiểm tra. Khi projection mới đạt watermark và đối soát, chuyển query service hoặc routing sang projection mới theo cách có thể đảo ngược.

Một chiến lược blue-green:

1. Tạo `order_summary_v2` hoặc một projection namespace mới.
2. Replay lịch sử vào V2.
3. Bắt kịp event live sau watermark.
4. So sánh V1 và V2 trên cùng khoảng dữ liệu.
5. Chuyển read traffic sang V2.
6. Theo dõi lỗi và độ trễ; giữ V1 trong cửa sổ rollback.
7. Chỉ xóa V1 sau khi hết thời gian rollback và đã lưu đủ audit.

Rollback read traffic thường đơn giản hơn rollback side effect. Nếu replay đã gửi email, thu tiền hoặc tạo giao dịch ngoài, không thể chỉ đổi pointer database để hoàn tác. Vì vậy, side effect cần được tách và kiểm soát trước khi chạy replay.

## 18. Bảo mật và dữ liệu nhạy cảm trong replay

Replay thường cần đọc lượng lớn dữ liệu lịch sử và có thể đưa payload đến môi trường mới. Cần bảo vệ dữ liệu xuyên suốt:

- Chỉ cấp quyền đọc nguồn và ghi đích tối thiểu cho replay worker.
- Không copy payload nhạy cảm vào log, console, ticket hoặc manifest.
- Dùng TLS và encryption at rest cho archive, broker và database.
- Bảo vệ key giải mã qua KMS/secret manager; không đưa key vào event.
- Giữ retention cho bản sao replay và quarantine theo chính sách dữ liệu.
- Ghi audit người khởi tạo, phạm vi, replay run ID và thao tác cutover.
- Không chạy replay dữ liệu production vào môi trường kém bảo vệ nếu chưa masking/tokenization.

Nếu dữ liệu đã bị xóa theo yêu cầu hợp lệ, replay không được tái tạo lại dữ liệu đó từ event cũ mà không đánh giá chính sách xóa và nghĩa vụ lưu trữ. Cần có quy tắc suppression/tombstone hoặc transformation loại bỏ dữ liệu đã bị hạn chế.

## 19. Metric và quan sát replay

Mỗi replay run nên đo:

- event đọc/giây và event áp dụng/giây;
- số lượng applied, duplicate, skipped, failed và quarantined;
- checkpoint/offset cuối theo partition hoặc stream;
- lag so với watermark và live head;
- thời gian deserialize, transform và ghi projection;
- retry count, retry exhausted và tuổi event lỗi lâu nhất;
- số side effect bị suppress hoặc được phép thực hiện;
- kết quả đối soát và thời gian cutover.

Log/trace nên chứa `replayRunId`, `eventId`, event type, schema version, aggregate ID/version, source position, transformation version và outcome. Không dùng các ID duy nhất làm metric label có cardinality cao; giữ chúng trong log có kiểm soát để truy vết.

Alert nên tập trung vào replay bị đứng, lag không giảm, lỗi schema tăng, checkpoint không tiến triển, partition thiếu dữ liệu hoặc số quarantine vượt ngưỡng. Khi collector không đọc được nguồn hoặc checkpoint, hiển thị trạng thái quan sát lỗi thay vì báo backlog bằng zero.

## 20. Ví dụ pseudo-code cho replay worker

```java
public void replay(ReplayRange range, ReplayRun run) {
    for (SourceRecord record : source.readFrom(range, run.checkpoint())) {
        CanonicalEvent event = decoder.toCanonical(record);

        try {
            target.applyIdempotently(event, run.id(), record.position());
            checkpointStore.markCompleted(record.position());
            metrics.applied(event.type());
        } catch (TransientReplayException exception) {
            metrics.failed("transient");
            throw exception; // giữ checkpoint trước vị trí chưa hoàn tất
        } catch (UnsupportedSchemaException exception) {
            quarantine.store(record, run.id(), exception.code());
            metrics.quarantined(event.type());
            throw exception; // cần quyết định rõ có được skip hay không
        }
    }
}
```

Đây là pseudo-code để minh họa luồng điều khiển, không phải implementation dùng trực tiếp. Trong production, cần bảo đảm `target.applyIdempotently` và checkpoint có transaction boundary phù hợp; nếu checkpoint store khác database đích, phải chấp nhận replay lại và dùng idempotency. Việc quarantine rồi ném exception cũng cần policy cụ thể: giữ checkpoint để dừng tại event lỗi, hoặc ghi nhận skip được phê duyệt và tiến tiếp. Không tự động bỏ qua mọi schema error.

## 21. Checklist trước khi replay sau di trú

- [ ] Mục tiêu replay và consumer/projection đích được xác định rõ.
- [ ] Nguồn lịch sử đầy đủ, có retention và quyền đọc phù hợp.
- [ ] Phân biệt replay với retry/resubmit Event Publication Registry.
- [ ] Event ID, schema version, aggregate version và source position được giữ nguyên.
- [ ] Có transformation/upcaster cho mọi schema version cần hỗ trợ.
- [ ] Có checkpoint/watermark riêng theo partition hoặc stream.
- [ ] Consumer idempotent; duplicate và crash window đã được tính đến.
- [ ] Thứ tự aggregate và sequence gap được xử lý rõ ràng.
- [ ] Side effect ngoài projection được tắt, mô phỏng hoặc bảo vệ bằng idempotency.
- [ ] Có dry run, shadow projection và giới hạn tốc độ.
- [ ] Traffic mới được phối hợp với replay bằng snapshot/watermark/catch-up.
- [ ] Có quarantine, retry policy và quyết định skip có audit.
- [ ] Đối soát số lượng, version, tổng hợp và dữ liệu nghiệp vụ.
- [ ] Có cutover/rollback, retention và bảo vệ dữ liệu nhạy cảm.
- [ ] Có metric theo replay run và log đủ để điều tra.

Replay sau di trú cho phép hệ thống xây dựng lại projection hoặc chuyển consumer sang contract mới mà vẫn giữ được lịch sử nghiệp vụ. Trong Spring Modulith, cần phân biệt publication incomplete do Event Publication Registry theo dõi với replay lịch sử từ event store, broker, outbox hoặc archive. Khi giữ nguyên danh tính event, chuyển đổi schema có kiểm soát, checkpoint theo đúng nguồn, xử lý idempotent và tách side effect khỏi quá trình rebuild, migration có thể được chạy lại, đối soát và cutover an toàn hơn.
