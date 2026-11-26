# Replay event production

## Replay event production là gì?

Replay event production là thao tác đưa một hoặc nhiều event đã được tạo trước đó trở lại luồng xử lý để khôi phục consumer, sửa projection, hoàn tất publication bị lỗi hoặc xử lý lại dữ liệu sau khi một lỗi vận hành được khắc phục.

Replay là thao tác có tác động thật. Một event được xử lý lại có thể cập nhật database, tạo shipment, ghi sổ kế toán, gửi email, gọi API bên ngoài hoặc kích hoạt một event tiếp theo. Vì vậy, trước khi replay phải xác định mục tiêu, phạm vi, nguồn dữ liệu, consumer đích và side effect được phép xảy ra.

Trong Spring Modulith, cần phân biệt publication chưa hoàn tất được phục hồi qua Event Publication Registry với việc phát lại lịch sử event đã hoàn tất. Registry theo dõi vòng đời publication theo listener; nó không mặc nhiên là event store lưu toàn bộ lịch sử nghiệp vụ. Replay message từ Kafka, RabbitMQ, DLQ hoặc archive cũng có cơ chế và rủi ro riêng.

Một quy trình production an toàn cần trả lời: replay event nào, cho ai, từ mốc nào, với tốc độ bao nhiêu, giữ identity nào, làm sao tránh tác động trùng và khi nào dừng.

~~~mermaid
flowchart TD
    A[Incident or replay request] --> B[Define goal and scope]
    B --> C[Identify source and target consumer]
    C --> D[Dry run and validate selection]
    D --> E{Approved and safe?}
    E -->|No| X[Stop and report]
    E -->|Yes| F[Replay with checkpoint and throttle]
    F --> G[Observe results and failures]
    G --> H{Reconciliation passes?}
    H -->|No| I[Pause, quarantine, investigate]
    H -->|Yes| J[Close replay and record audit]
~~~

## Xác định mục tiêu trước khi replay

Không bắt đầu bằng thao tác reset offset hoặc requeue toàn bộ DLQ. Trước hết phải phân loại mục tiêu vì mỗi mục tiêu có cách chọn dữ liệu và cách kiểm tra kết quả khác nhau.

| Mục tiêu | Ví dụ | Kết quả cần đạt |
|---|---|---|
| Resubmit publication lỗi | Listener Spring Modulith thất bại sau commit | Listener hoàn tất publication còn pending |
| Redrive message lỗi | Message nằm trong retry queue hoặc DLQ | Message được xử lý sau khi nguyên nhân lỗi được khắc phục |
| Rebuild projection | Read model bị sai hoặc cần thêm field | Projection mới phản ánh đúng lịch sử event |
| Backfill consumer mới | Một consumer mới cần xử lý event lịch sử | Consumer mới nhận đúng tập event cần thiết |
| Phục hồi sau outage | Consumer ngừng hoạt động trong một khoảng thời gian | Xử lý hết backlog mà không mất hoặc nhân đôi tác động |
| Điều tra và sửa dữ liệu | Phát hiện sai mapping hoặc bug xử lý | Dữ liệu được sửa theo kế hoạch có thể đối soát |

Không dùng replay để thay thế mọi loại sửa dữ liệu. Nếu event gốc sai về mặt nghiệp vụ, phát một correction event có định danh mới hoặc thực hiện quy trình sửa dữ liệu có audit có thể phù hợp hơn replay nguyên trạng event sai.

Cần phân biệt replay event với chạy lại command. Replay tái xử lý sự kiện đã xảy ra; command có thể tạo ra thay đổi nghiệp vụ mới và phát event mới. Không gọi lại endpoint tạo đơn hàng, hoàn tiền hoặc giao hàng chỉ vì muốn phát lại event cũ.

## Phân biệt các nguồn replay

Nguồn dữ liệu quyết định khả năng chọn lọc, thứ tự và độ bền của replay.

| Nguồn | Dữ liệu có thể replay | Cơ chế thường dùng |
|---|---|---|
| Event Publication Registry | Publication còn incomplete theo listener | Resubmission theo API/cấu hình của Spring Modulith |
| Kafka topic | Record còn trong retention | Consumer group mới, offset reset có kiểm soát hoặc công cụ redrive |
| RabbitMQ DLQ/retry queue | Message bị reject, hết TTL hoặc chuyển dead-letter | Chuyển tiếp hoặc publish lại message |
| Transactional outbox | Event đã lưu bền vững chờ publish hoặc cần redrive | Relay đọc lại bản ghi theo trạng thái |
| Event store/archive | Lịch sử event đã lưu lâu dài | Replay theo event ID, aggregate, thời gian hoặc checkpoint |
| File/object storage | Batch event đã export | Import có kiểm tra, checkpoint và idempotency |

Không giả định một nguồn có thể cung cấp mọi event lịch sử. Kafka chỉ giữ record trong retention được cấu hình; RabbitMQ queue thường loại message sau acknowledgement; publication registry có thể dọn record hoàn tất theo chính sách lưu trữ. Nếu cần replay dài hạn, phải có event store, archive hoặc nguồn dữ liệu bền vững khác.

## Replay publication chưa hoàn tất với Spring Modulith

Spring Modulith Event Publication Registry ghi nhận publication cho các listener được quản lý, thường gắn với transaction phát event. Publication chưa hoàn tất có thể được quan sát và resubmit theo cơ chế mà phiên bản Spring Modulith và persistence implementation cung cấp.

Trước khi resubmit:

- Xác định listener và publication target bị lỗi.
- Kiểm tra nguyên nhân lỗi đã được khắc phục.
- Xem publication có đang được một instance khác xử lý hay không.
- Kiểm tra handler có idempotent.
- Xác định số publication pending và tuổi của publication lâu nhất.
- Chọn tập publication cần resubmit, tránh kích hoạt toàn bộ backlog ngoài ý muốn.

Registry phục vụ theo dõi trạng thái giao event tới listener. Nó không thay thế event store và không bảo đảm mọi event đã hoàn tất đều còn sẵn để replay vô hạn. Khả năng resubmit, lọc theo listener và dọn publication phụ thuộc phiên bản cùng cấu hình thực tế; dùng API chính thức của phiên bản dự án, không thao tác trực tiếp vào bảng nội bộ bằng SQL tùy tiện.

Một publication được resubmit có thể làm listener chạy lại với cùng event. Giữ nguyên event ID và áp dụng idempotency ở listener. Nếu listener đã commit side effect nhưng lỗi xảy ra trước khi registry ghi nhận hoàn tất, lần resubmit có thể giao lại event; đây là tình huống cần được thiết kế trước.

Không đánh dấu publication hoàn tất thủ công chỉ để xóa pending nếu chưa xác minh side effect đã xảy ra. Làm vậy có thể khiến tác động nghiệp vụ bị mất vĩnh viễn.

## Replay Kafka an toàn

Kafka giữ record trong topic theo retention và phân phối theo partition. Offset được quản lý theo consumer group, không phải trạng thái xử lý duy nhất của từng event.

Các cách replay thường gặp:

- Dùng consumer group mới để đọc lại lịch sử trong retention mà không thay offset của group production.
- Reset offset của group hiện tại khi consumer đã dừng và có kế hoạch rõ về việc xử lý lại side effect.
- Đọc một khoảng offset có giới hạn bằng một replay worker riêng.
- Copy record sang topic replay chuyên biệt khi cần cô lập routing và policy xử lý.

Dùng consumer group mới thường an toàn hơn cho bước kiểm tra hoặc rebuild projection vì không thay đổi tiến độ group đang chạy. Tuy nhiên, consumer mới vẫn có thể tạo side effect nếu kết nối tới hệ thống production. Hãy cấu hình chế độ dry-run hoặc target dữ liệu tách biệt.

Nếu reset offset của group production, dừng consumer hoặc kiểm soát deployment để tránh instance khác cùng commit offset trong lúc reset. Xác định partition và offset bắt đầu/kết thúc, lưu lại offset trước khi thay đổi và có phương án khôi phục.

Kafka ordering được bảo đảm trong phạm vi partition theo thứ tự record được ghi. Replay nhiều partition đồng thời không tạo ra thứ tự toàn cục. Nếu cần giữ thứ tự theo aggregate, producer nên dùng aggregate ID làm key và replay worker phải giữ thứ tự record trong từng partition hoặc áp dụng kiểm tra aggregate version ở consumer.

Không giả định record còn tồn tại chỉ vì offset đã biết. Retention, compaction và thao tác quản trị có thể làm mất record cần replay. Kiểm tra earliest/latest offset và dữ liệu thực tế trước khi lập kế hoạch.

## Replay RabbitMQ, retry queue và DLQ

RabbitMQ queue không có cơ chế rewind offset như Kafka. Khi message đã được acknowledge, nó thường bị loại khỏi queue. Muốn replay, cần nguồn lưu khác hoặc đưa message từ DLQ/archive trở lại luồng.

Các cách thường dùng:

- Publish lại message từ DLQ sang exchange đích sau khi sửa nguyên nhân lỗi.
- Dùng retry queue có TTL để thử lại sau một khoảng chờ.
- Export message sang kho lưu trữ trước khi redrive nếu cần kiểm toán.
- Dùng công cụ vận hành để chuyển message theo batch có giới hạn.

Trước khi redrive, kiểm tra routing key, exchange, header, content type, schema version và event ID. Nếu message đi qua nhiều lần dead-letter, header x-death có thể chứa lịch sử dead-letter; không xóa metadata này nếu nó cần cho điều tra hoặc policy retry.

Không cấu hình requeue vô hạn cho poison message. Một payload không hợp lệ hoặc lỗi logic không thể tự hết bằng retry liên tục. Giới hạn số lần thử, chuyển DLQ và yêu cầu điều tra.

Nếu publish lại một message, publisher confirms và mandatory returns giúp kiểm tra broker đã nhận và route message theo policy. Redrive thành công ở mức broker vẫn chưa chứng minh consumer đã xử lý nghiệp vụ.

## Xác định phạm vi replay

Phạm vi phải đủ hẹp để giảm nguy cơ side effect ngoài dự kiến. Có thể lọc theo:

- Event type.
- Event ID hoặc danh sách ID.
- Producer hoặc source.
- Aggregate ID.
- Tenant.
- Khoảng occurredAt.
- Schema version.
- Partition và offset.
- Publication target hoặc consumer name.
- Trạng thái retry/DLQ.

Ghi lại điều kiện lọc chính xác và số lượng event dự kiến. Với event tài chính hoặc thao tác không thể đảo ngược, nên yêu cầu đối soát danh sách event trước khi chạy.

Không dùng timestamp duy nhất làm khóa chọn nếu clock có thể lệch hoặc nhiều event cùng thời điểm. Kết hợp event ID, aggregate version, partition/offset hoặc checkpoint ổn định.

Nếu replay theo tenant, xác minh tenant ID nằm trong phần dữ liệu đã được xác thực và consumer không thể bị điều hướng sang tenant khác do metadata sai.

## Dry run trước khi thực thi

Dry run đọc và kiểm tra tập event nhưng không gọi side effect nghiệp vụ. Đây là bước để xác nhận selection, schema và kế hoạch vận hành.

Dry run nên báo cáo:

- Số event tìm thấy và số event bị loại.
- Phân bố theo event type, tenant, producer và schema version.
- Khoảng thời gian hoặc offset được chọn.
- Event ID trùng hoặc payload có dấu hiệu không nhất quán.
- Event thiếu schema hoặc không deserialize được.
- Số event có thể tạo side effect ngoài.
- Tốc độ dự kiến, thời gian ước lượng và checkpoint đầu/cuối.
- Các consumer/handler sẽ nhận event.

Nếu dry run phát hiện payload sai, tenant không khớp hoặc event ngoài phạm vi, dừng và điều tra. Không biến replay thành cách thử xem production có chạy được hay không.

Với replay lớn, lưu manifest của lần chạy gồm replayRunId, nguồn, bộ lọc, số lượng dự kiến, người yêu cầu, người phê duyệt, thời điểm và phiên bản consumer.

## Giữ nguyên event identity và metadata gốc

Khi replay, event ID phải giữ nguyên. Consumer dùng event ID để deduplicate; tạo ID mới cho mỗi lần replay khiến cùng một sự kiện có thể tạo tác động lặp.

Nên giữ nguyên các dữ liệu lịch sử:

- eventId.
- eventType và schemaVersion gốc.
- occurredAt.
- producer/source gốc.
- aggregateId và aggregateVersion.
- causationId và correlationId gốc nếu có.
- Payload gốc đã được xác minh.

Bổ sung metadata vận hành riêng, ví dụ replayRunId, replayedAt, replayedBy, replayReason, replayAttempt và originalDestination. Không ghi đè occurredAt bằng thời điểm replay vì nó làm sai thời điểm nghiệp vụ đã xảy ra.

Nếu chữ ký event bao phủ envelope, việc thêm metadata replay có thể làm chữ ký không còn hợp lệ. Hãy thiết kế metadata replay ngoài phần payload đã ký hoặc ký lại bằng một cơ chế có thẩm quyền, đồng thời giữ được bằng chứng về event gốc. Không tự sửa payload hoặc chữ ký của event lịch sử.

## Idempotency và bảo vệ side effect

Replay có thể giao lại event đã xử lý một phần hoặc toàn bộ. Consumer phải chịu được duplicate delivery.

Các biện pháp:

- Dùng unique constraint theo consumer và event ID.
- Ghi nhận processed event trong cùng transaction với thay đổi dữ liệu của consumer.
- Dùng business key để chống tạo trùng thực thể, ví dụ một shipment cho một order.
- Gửi idempotency key ổn định tới API bên ngoài nếu API hỗ trợ.
- Dùng outbox cho tác động tiếp theo cần publish.
- Xác định side effect nào được phép chạy lại và side effect nào phải bị suppress.

Ví dụ bảng inbox:

~~~sql
CREATE TABLE processed_event (
    consumer_name VARCHAR(150) NOT NULL,
    event_id UUID NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
~~~

Consumer cố gắng insert khóa deduplication trước khi áp dụng side effect trong cùng transaction. Nếu insert bị conflict, event đã được xử lý theo scope consumer đó và có thể bỏ qua tác động lần nữa.

Với hệ thống ngoài database, transaction cục bộ không thể bảo đảm nguyên tử cùng HTTP API. Cần idempotency key ở hệ thống đích, outbox/workflow state hoặc quy trình đối soát trạng thái không chắc chắn.

Không xóa processed-event record trước khi hết mọi cửa sổ retry và replay được cho phép. Nếu replay lịch sử sau nhiều tháng, retention của deduplication cũng phải đáp ứng khoảng thời gian đó hoặc có unique business constraint lâu dài.

## Replay projection và replay side effect

Đây là một phân biệt quan trọng. Rebuild read model thường có thể thực hiện trong projection mới hoặc bảng shadow. Gửi lại email, thu tiền, tạo vận đơn hoặc cấp quyền có thể gây tác động không thể đảo ngược.

| Loại consumer | Cách replay khuyến nghị |
|---|---|
| Read model/projection | Rebuild vào bảng hoặc index mới, đối soát rồi cutover |
| Search index/cache | Rebuild có checkpoint, có thể thay index sau khi xác minh |
| Notification | Suppress gửi ra ngoài hoặc dùng chế độ preview; chỉ phát lại khi có phê duyệt |
| Billing/payment | Không chạy lại side effect mặc định; dùng ledger đối soát và quy trình correction |
| Fulfillment/shipping | Kiểm tra trạng thái thực tế ở hệ thống vận hành trước khi tạo lại |
| Audit/analytics | Replay vào target riêng và giữ provenance |

Không coi mọi consumer là một projection có thể xóa rồi dựng lại. Mỗi listener cần policy replay riêng được chủ sở hữu nghiệp vụ xác nhận.

Với projection, có thể tạo consumer group hoặc bảng mới, replay toàn bộ tập event, kiểm tra số lượng và invariant rồi chuyển traffic đọc sang projection mới. Giữ projection cũ trong thời gian rollback nếu dung lượng cho phép.

## Ordering và aggregate consistency

Replay event cũ có thể làm event đến consumer sai thứ tự so với event mới đang được xử lý trực tiếp.

Ví dụ OrderConfirmed version 8 được replay sau OrderCancelled version 9. Consumer không có kiểm tra version có thể làm trạng thái đơn hàng quay ngược.

Các biện pháp:

- Replay theo thứ tự aggregate version khi nghiệp vụ yêu cầu.
- Dùng aggregate ID làm Kafka key để giữ event của aggregate trên cùng partition.
- Tạm dừng live consumer hoặc route replay sang target riêng khi cần snapshot nhất quán.
- Consumer từ chối event có version cũ hơn trạng thái đã áp dụng.
- Consumer incremental kiểm tra version kế tiếp và phát hiện gap.
- Ghi nhận event bị bỏ qua do stale version để đối soát.

Không dựa vào occurredAt để xác định thứ tự tuyệt đối. Timestamp có thể trùng hoặc lệch; aggregate version/sequence thường là tín hiệu ordering nghiệp vụ rõ hơn.

Nếu replay một khoảng event giữa lịch sử trong khi live traffic vẫn tiếp tục, cần xác định quy tắc merge. Có thể replay tới snapshot watermark rồi chuyển sang live tail, hoặc rebuild trong target riêng rồi cutover sau khi bắt kịp watermark.

## Checkpoint, batch và khả năng tiếp tục

Replay lớn cần checkpoint để có thể tiếp tục sau restart mà không bắt đầu lại từ đầu.

Checkpoint có thể gồm:
- Replay run ID.
- Source partition và offset hoặc event cursor.
- Aggregate ID và version nếu xử lý theo aggregate.
- Batch sequence.
- Số event đọc, thành công, bỏ qua và lỗi.
- Thời điểm checkpoint.
- Consumer/schema version.

Checkpoint chỉ nên tiến sau khi batch side effect đã commit. Nếu checkpoint được ghi trước rồi tiến trình dừng trước khi commit dữ liệu, event có thể bị bỏ qua. Nếu dữ liệu commit nhưng checkpoint chưa ghi, batch có thể chạy lại; idempotency phải xử lý trường hợp này.

Với Kafka, offset commit và transaction nghiệp vụ ở database là hai hệ thống khác nhau trừ khi dùng một thiết kế giao dịch tích hợp cụ thể. Không giả định commit offset và commit database là một thao tác nguyên tử. Inbox/idempotency là lớp bảo vệ quan trọng.

Với batch archive, lưu cursor ổn định và dùng unique event ID để tránh duplicate giữa các batch. Ghi lại checkpoint trước/sau mỗi batch và kiểm tra có khoảng trống hoặc event bị đọc lặp.

## Throttle và backpressure trong production

Replay không được làm live traffic mất khả năng phục vụ. Tăng tốc replay quá nhanh có thể gây CPU saturation, connection pool cạn, database lock contention, broker queue tăng hoặc API downstream bị rate limit.

Kiểm soát bằng:
- Giới hạn event mỗi giây và batch size.
- Giới hạn consumer concurrency.
- Pause/resume theo ngưỡng queue depth và resource utilization.
- Tách replay workload khỏi live workload khi có thể.
- Dùng rate limit cho HTTP/API bên ngoài.
- Theo dõi latency và error rate của live traffic.
- Có kill switch để dừng nhanh.

Bắt đầu với tốc độ thấp, tăng dần khi metric ổn định. Đặt ngưỡng dừng tự động khi backlog live tăng nhanh, p95/p99 vượt SLO, database lock hoặc lỗi downstream vượt mức cho phép.

Không dùng toàn bộ năng lực consumer cho replay nếu hệ thống còn phải xử lý event mới. Dành capacity riêng cho live traffic theo SLO.

## Retry, poison event và quarantine

Một event có thể thất bại vì lỗi tạm thời hoặc lỗi dữ liệu vĩnh viễn.

| Loại lỗi | Cách xử lý |
|---|---|
| Network/database tạm thời | Retry có backoff và giới hạn |
| Downstream rate limit | Throttle và retry theo retry-after |
| Schema không hỗ trợ | Quarantine, nâng cấp consumer hoặc upcast có kiểm soát |
| Payload không hợp lệ | Dừng event, lưu bằng chứng và điều tra producer |
| Authorization thất bại | Reject và xử lý theo security policy |
| Business invariant không còn đúng | Không ép xử lý; đối soát và correction |
| Cùng event ID nhưng payload khác | Dừng replay và ghi nhận integrity incident |

Không retry vô hạn poison event. Một event lỗi cần được quarantine cùng event ID, source, replayRunId, error category và payload đã được bảo vệ theo chính sách dữ liệu.

Sau khi sửa lỗi, chỉ redrive các event đã được xác minh và còn phù hợp với trạng thái nghiệp vụ. Không tự động phát lại toàn bộ DLQ sau một lần sửa code nếu trong DLQ có nhiều loại lỗi khác nhau.

## Replay và schema evolution

Event lịch sử có thể dùng schema version cũ. Consumer hiện tại cần deserialize và diễn giải được event cũ theo contract đã công bố.

Trước replay:
- Xác định phân bố schema version.
- Kiểm tra consumer hỗ trợ các version được chọn.
- Dùng upcaster hoặc adapter chuyển đổi khi cần.
- Giữ payload gốc để audit.
- Không đổi event ID khi upcast.
- Ghi nhận version sau chuyển đổi trong processing metadata nếu cần.

Upcast nên là phép chuyển đổi xác định và không tạo side effect. Nếu upcast làm thay đổi ý nghĩa nghiệp vụ, cần review contract và kiểm thử compatibility trước khi replay production.

Event mới có field tùy chọn có thể được consumer cũ bỏ qua nếu serializer/schema policy cho phép. Ngược lại, consumer mới phải xử lý event cũ thiếu field. Kiểm thử cả hai chiều trước khi replay khối lượng lớn.

## An toàn, quyền truy cập và phê duyệt

Replay có thể phát lại dữ liệu nhạy cảm hoặc kích hoạt hành động tài chính. Chỉ người và service account có quyền phù hợp mới được chạy replay.

Runbook nên quy định:
- Ai có quyền yêu cầu, phê duyệt và thực thi.
- Replay scope và consumer target nào được phép.
- Tenant nào nằm trong phạm vi.
- Có được chạy side effect bên ngoài không.
- Cách xử lý dữ liệu cá nhân và payload trong log/archive.
- Audit log bắt buộc.
- Cơ chế dừng và liên hệ incident owner.

Áp dụng nguyên tắc least privilege. Replay worker chỉ cần quyền đọc nguồn, ghi target và phát tới destination đã được cấp; không cần quyền quản trị toàn broker nếu không cần thiết.

Không ghi payload nhạy cảm đầy đủ vào log hoặc replay manifest. Ghi event ID, schema version, checksum, nguồn và trạng thái; payload cần được lưu trong kho có kiểm soát quyền truy cập.

## Runbook replay production

Một runbook có thể tổ chức thành các giai đoạn sau:

### 1. Tiếp nhận và phân loại

- Ghi incident/ticket, mục tiêu và owner nghiệp vụ.
- Xác định đây là registry resubmission, broker redrive, projection rebuild hay historical replay.
- Xác định side effect có thể xảy ra.
- Xác định tiêu chí thành công và điều kiện dừng.

### 2. Chuẩn bị

- Xác định nguồn dữ liệu, target consumer và bộ lọc.
- Kiểm tra schema version, event ID và ordering.
- Xác nhận idempotency và retention.
- Kiểm tra capacity, backlog live và downstream rate limit.
- Tạo replay manifest và checkpoint ban đầu.
- Thực hiện dry run và review số lượng event.

### 3. Phê duyệt và thực thi

- Nhận phê duyệt theo policy.
- Bật chế độ dry-run/side-effect suppression nếu cần.
- Bắt đầu với batch nhỏ và tốc độ thấp.
- Theo dõi metric sau mỗi batch.
- Tăng tốc từng bước khi kết quả ổn định.
- Ghi checkpoint sau khi side effect commit.

### 4. Đối soát

- So sánh số event được chọn, đọc, thành công, duplicate, quarantine và bỏ qua.
- Đối chiếu aggregate count, projection version hoặc ledger invariant.
- Xác nhận không có event ngoài scope.
- Xác nhận live traffic vẫn trong SLO.
- Kiểm tra publication hoặc queue backlog đã về mức mục tiêu.

### 5. Kết thúc

- Dừng replay worker và thu hồi quyền tạm thời.
- Lưu manifest, checkpoint, log và kết quả đối soát.
- Ghi lại event lỗi còn lại cùng owner xử lý.
- Xác nhận consumer live hoạt động bình thường.
- Đóng incident theo tiêu chí đã thống nhất.

## Observability trong lúc replay

Theo dõi metric theo replayRunId trong log/trace và theo các label có cardinality giới hạn trong metrics.

Chỉ số nên có:
- Event được chọn, đọc, xử lý thành công, duplicate và quarantine.
- Replay throughput và batch duration.
- Checkpoint hiện tại và tuổi checkpoint.
- Consumer lag hoặc queue depth.
- Retry count và error rate theo category.
- Publication incomplete và tuổi publication lâu nhất.
- Database connection/lock, CPU, memory và downstream latency.
- Live traffic p95/p99 và SLO burn rate.

Không dùng event ID, aggregate ID hoặc replayRunId làm metric label nếu tạo cardinality lớn. Những ID này phù hợp với structured log và trace. Metrics có thể nhóm theo event type, consumer, source, result và schema version.

Một dashboard replay cần hiển thị cả tiến độ replay và sức khỏe live system. Replay throughput cao không phải thành công nếu nó làm live consumer lag hoặc downstream service quá tải.

## Đối soát và tiêu chí hoàn tất

Không kết thúc replay chỉ vì worker đã đọc hết nguồn. Cần chứng minh kết quả cuối đúng.

Các đối soát hữu ích:

- Số event nguồn trong scope bằng tổng thành công, duplicate hợp lệ, skipped có lý do và quarantine.
- Không có khoảng trống checkpoint ngoài dự kiến.
- Mỗi aggregate đạt version hoặc trạng thái mục tiêu.
- Projection mới khớp invariant nghiệp vụ và nguồn chuẩn.
- Không tạo duplicate business record hoặc side effect ngoài policy.
- Publication pending và queue backlog đạt ngưỡng mục tiêu.
- Các event lỗi còn lại có owner và kế hoạch xử lý.

Với tài chính, đối soát bằng ledger, amount/currency và business key. Với fulfillment, xác minh trạng thái shipment ở hệ thống đích. Với projection, so sánh count, checksum hoặc các invariant trên tập dữ liệu đã chọn.

## Rollback và dừng replay

Replay thường không thể rollback toàn bộ side effect như một database transaction duy nhất. Khi có lỗi, ưu tiên dừng tiến trình, giữ checkpoint và xác định chính xác batch đã commit.

Có thể:
- Pause replay worker.
- Giữ lại source và manifest.
- Khôi phục offset/checkpoint chỉ khi hiểu rõ tác động.
- Xóa projection shadow và rebuild lại nếu target tách biệt.
- Phát correction event hoặc chạy compensation theo nghiệp vụ nếu side effect đã xảy ra.
- Không reset trạng thái processed-event một cách tùy tiện để ép replay lại.

Nếu replay ghi trực tiếp vào projection production, việc quay lui có thể cần restore snapshot hoặc rebuild từ nguồn. Với side effect bên ngoài, phải dùng quy trình compensation riêng; không thể giả định gửi lại event ngược sẽ đảo ngược hành động trước.

Sau khi dừng, ghi lại event ID và batch cuối cùng đã commit, các tác động đã xảy ra và trạng thái downstream để lần tiếp theo tiếp tục an toàn.

## Kiểm thử runbook trước production

Replay quy mô lớn cần được diễn tập trên môi trường staging với dữ liệu đại diện:

- Chạy dry run và xác minh số lượng.
- Mô phỏng consumer lỗi giữa batch.
- Restart replay worker và tiếp tục từ checkpoint.
- Giao lại duplicate event.
- Kiểm tra event đến sai thứ tự.
- Thử event schema cũ và payload không hợp lệ.
- Kiểm tra DLQ/quarantine.
- Đo tải database và broker khi throttle.
- Xác nhận live traffic được bảo vệ.
- Diễn tập pause, resume và compensation.

Không chỉ test happy path. Sự cố thường xảy ra khi tiến trình dừng giữa side effect và checkpoint, khi broker acknowledgement không rõ ràng hoặc khi một event cũ không còn phù hợp với trạng thái hiện tại.

## Checklist trước khi chạy replay

1. Mục tiêu và owner nghiệp vụ đã rõ.
2. Đã phân loại đúng nguồn replay.
3. Consumer target và side effect được xác định.
4. Bộ lọc, số lượng và khoảng thời gian đã được dry-run.
5. Event ID và metadata gốc được giữ nguyên.
6. Consumer idempotent và có unique/business key phù hợp.
7. Ordering và aggregate version được kiểm soát.
8. Schema cũ được hỗ trợ hoặc có upcaster.
9. Checkpoint chỉ tiến sau commit.
10. Batch size, throughput và concurrency có giới hạn.
11. Live traffic có capacity và kill switch.
12. DLQ/quarantine có policy rõ.
13. Quyền truy cập và phê duyệt được ghi audit.
14. Tiêu chí đối soát và hoàn tất đã định nghĩa.
15. Runbook pause/resume/compensation đã được diễn tập.

Replay event production là một quy trình vận hành có kiểm soát, không chỉ là gửi lại message. Khi phân biệt đúng registry resubmission, broker redrive và historical replay; giữ nguyên event identity; bảo vệ side effect bằng idempotency; kiểm soát ordering, checkpoint và tốc độ; đồng thời đối soát kết quả trước khi đóng replay, hệ thống có thể phục hồi dữ liệu và consumer an toàn hơn.

## Tài liệu tham khảo

- Spring Modulith Reference — Event Publication Registry and Application Events: https://docs.spring.io/spring-modulith/reference/events.html
- Apache Kafka Documentation — Consumer Groups and Offset Management: https://kafka.apache.org/documentation/#consumerconfigs
- RabbitMQ Documentation — Dead Letter Exchanges: https://www.rabbitmq.com/docs/dlx
- RabbitMQ Documentation — Consumer Acknowledgements and Publisher Confirms: https://www.rabbitmq.com/docs/confirms
- Spring for Apache Kafka Reference — Listener Containers and Transactions: https://docs.spring.io/spring-kafka/reference/
- CloudEvents Specification 1.0: https://github.com/cloudevents/spec/blob/v1.0.2/cloudevents/spec.md
