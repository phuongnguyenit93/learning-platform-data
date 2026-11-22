# Đối soát chênh lệch và khôi phục khi mất một đoạn luồng thay đổi

Một hệ thống đặt chỗ lưu dữ liệu gốc trong NoSQL, đồng thời duy trì chỉ mục tìm kiếm và bảng tổng hợp bằng **Change Data Capture (CDC)**. Mỗi khi booking được tạo, thay đổi hoặc xóa, một luồng sự kiện thông báo cho các consumer cập nhật những bản dữ liệu dẫn xuất. Trong nhiều tháng, pipeline hoạt động bình thường. Sau đó một worker ngừng chạy khi đang xử lý sự kiện số 104. Khi worker được khởi động lại, dữ liệu được giữ trong change stream đã hết hạn đối với một phần thời gian gián đoạn. Consumer tiếp tục nhìn thấy sự kiện 110 nhưng **không có các sự kiện 105–109**.

Nếu hệ thống chỉ tiếp tục xử lý sự kiện 110, chỉ mục tìm kiếm có thể thiếu booking, thống kê doanh thu sai và một record đã bị xóa vẫn xuất hiện. Nguy hiểm hơn, dashboard CDC có thể trở lại trạng thái “đang chạy” dù dữ liệu dẫn xuất đã **lệch nguồn**.

Bài học thuộc **Database No SQL → Sự kiện và CDC**, tập trung vào hai năng lực vận hành bổ sung cho CDC:

1. **Đối soát chênh lệch (reconciliation):** xác định các bản dữ liệu dẫn xuất có còn phản ánh đúng nguồn dữ liệu có thẩm quyền trong phạm vi và mức nhất quán đã cam kết hay không.
2. **Khôi phục khi mất một đoạn luồng thay đổi (gap recovery):** phát hiện điểm phục hồi không còn hợp lệ; lựa chọn replay, backfill theo phạm vi hoặc tái dựng projection từ snapshot; sau đó bắt kịp sự kiện mới và kiểm chứng trước khi đưa kết quả vào sử dụng.

Một thiết kế đáng tin cậy không chỉ hỏi “consumer có nhận event không?” mà còn hỏi:

- Event nào **có thể đã bị bỏ lỡ**?
- Có bằng chứng về khoảng mất hay chỉ có **lag**?
- Cursor/offset nào được lưu bền và thuộc partition/epoch nào?
- Còn có thể replay sự kiện cũ không, hay đã vượt retention?
- Nguồn sự thật có thể được chụp thành snapshot nhất quán tại một ranh giới thay đổi không?
- Một consumer đang tái dựng có tránh ghi dữ liệu cũ đè lên bản mới không?
- Làm thế nào xác minh mọi create, update, delete và thay đổi schema đã được phản ánh?
- Khi nào có thể **chuyển traffic sang projection mới** mà không mất tính sẵn sàng hoặc vi phạm nghiệp vụ?

> **Nguyên tắc:** CDC là **cơ chế truyền thay đổi**, không phải bằng chứng tự động rằng mọi hệ dẫn xuất đã đúng. **Consumer lag** khác **missing history**. Một nguồn sự thật có thể đã commit đầy đủ nhưng read model vẫn sai; cách khôi phục phải dựa vào ranh giới version/cursor, idempotent apply, khả năng snapshot và kiểm chứng chênh lệch, chứ không chỉ khởi động lại worker hoặc “seek tới latest”.

> **Phạm vi:** Các thuật ngữ offset, resume token, shard sequence, oplog, changelog và checkpoint có ngữ nghĩa riêng ở MongoDB, DynamoDB Streams, Kafka/Connect, Debezium, Redis Streams và các NoSQL khác. Bài dùng pseudocode và Java 21 minh họa mô hình tổng quát; cần đối chiếu contract, phiên bản và cấu hình cụ thể trước khi vận hành.

## 1. CDC nằm ở đâu trong một kiến trúc NoSQL?

Một kiến trúc thường gặp:

~~~~mermaid
flowchart LR
    API["Java application"] --> SOURCE[("NoSQL source of truth")]
    SOURCE --> CDC["CDC / transaction log"]
    CDC --> RELAY["Connector / relay"]
    RELAY --> BUS[("Stream / broker")]
    BUS --> PROJ["Projector consumer"]
    PROJ --> SEARCH[("Search index")]
    PROJ --> VIEW[("Query read model")]
    PROJ --> METRICS[("Aggregates")]
    RECON["Reconciliation job"] --> SOURCE
    RECON --> SEARCH
    RECON --> VIEW
~~~~

- **NoSQL source:** nơi thao tác nghiệp vụ được commit theo transaction/conditional-write contract.
- **CDC stream:** phản ánh những thay đổi mà hệ cung cấp trong phạm vi theo dõi.
- **Connector/relay:** đọc thay đổi, chuyển đổi và publish.
- **Broker:** giữ events để consumer xử lý theo retention/ordering của broker.
- **Projector:** biến events thành data phục vụ truy vấn.
- **Checkpoint:** vị trí consumer xác nhận đã xử lý bền.
- **Reconciliation:** so nguồn và projection bằng key, version, hash hoặc các bất biến khác.
- **Recovery coordinator:** điều phối replay/backfill/rebuild và cutover.

### 1.1. Nguồn sự thật và bản dẫn xuất

Ví dụ booking B-901:

**Source NoSQL:**

~~~~json
{
  "tenantId": "T-42",
  "bookingId": "B-901",
  "version": 18,
  "status": "CANCELLED",
  "amountMinor": 1250000
}
~~~~

**Search projection:**

~~~~json
{
  "tenantId": "T-42",
  "bookingId": "B-901",
  "sourceVersion": 16,
  "status": "CONFIRMED",
  "amountMinor": 1250000
}
~~~~

Projection đang ở v16 trong khi source đã ở v18. Đó là **một chênh lệch cần giải thích**, nhưng chưa chắc là incident nếu hệ đã công bố độ trễ tối đa và event v17–v18 vẫn đang chờ xử lý. Ngược lại, nếu v17–v18 không còn trong stream và checkpoint đã chuyển qua mốc sau, đây có thể là **mất một đoạn lịch sử cần repair**.

### 1.2. Projection không tự trở thành authority

Search index, reporting table và cache có thể:
- Chưa thấy update mới.
- Nhận event trùng.
- Nhận event ngoài thứ tự.
- Bị reset/mất shard.
- Có dữ liệu từ schema cũ.

Không dùng một read model stale để quyết định:
- Có được xác nhận booking cuối cùng hay không.
- Một thanh toán đã commit hay chưa.
- Quyền truy cập vừa bị thu hồi có còn hiệu lực hay không.
- Số dư hiện hành có đủ chi tiêu hay không.

Những quyết định cần dựa vào authority thích hợp theo hợp đồng nghiệp vụ.

## 2. Các khái niệm: gap, lag, drift và replay

| Thuật ngữ | Ý nghĩa | Dấu hiệu |
| --- | --- | --- |
| **CDC lag** | Consumer chậm hơn vị trí mới nhất nhưng lịch sử cần thiết vẫn còn | Backlog tăng, cursor còn hợp lệ |
| **Gap / missing segment** | Một đoạn thay đổi cần thiết không thể đọc hoặc đã bị bỏ qua | Invalid resume token, expired retention, sequence discontinuity có ý nghĩa |
| **Projection drift** | Giá trị/kết quả ở read model không khớp source tại ranh giới so sánh hợp lệ | Version/hash/value khác |
| **Lost update in projector** | Event đã có nhưng apply bị bỏ qua/ghi lỗi | Checkpoint tiến trước durable apply |
| **Duplicate delivery** | Một event xuất hiện lại | At-least-once replay, retry |
| **Out-of-order delivery** | Events đến khác thứ tự cần thiết | Version mới được apply trước version cũ |
| **Backfill** | Đọc nguồn hiện tại để sửa một vùng/key set | Recompute theo source |
| **Replay** | Phát lại một chuỗi events có sẵn | Từ checkpoint/cursor còn hợp lệ |
| **Full rebuild** | Tái dựng read model từ nguồn và các thay đổi mới | Snapshot + stream catch-up |
| **Reconciliation** | So và sửa khác biệt theo quy tắc | Diff keys/versions/hashes |
| **Checkpoint** | Vị trí xử lý được lưu bền | Offset/token per stream partition |
| **Watermark** | Mốc tiến độ/ranh giới có semantics đã định | Source commit sequence hoặc per-partition frontier |
| **Tombstone** | Bằng chứng một entity đã bị xóa | Delete event, versioned marker |

### 2.1. Lag có thể hồi phục bằng catch-up

Consumer dừng 10 phút, stream giữ thay đổi 24 giờ, checkpoint vẫn còn hợp lệ. Sau restart:
- Tiếp tục từ vị trí cuối đã xử lý bền.
- Đọc phần backlog.
- Apply idempotently.
- Đo thời gian bắt kịp.

Không nhất thiết rebuild toàn bộ chỉ vì consumer lag.

### 2.2. Gap có thể không khôi phục bằng replay

Consumer dừng vượt retention; broker/CDC log không còn đoạn cũ. Hành động “resume từ cursor cũ” thất bại hoặc không đọc được những events cần thiết. Nếu tự nhảy tới latest:
- Projection đang thiếu mọi thay đổi giữa cursor cũ và latest.
- Future events có thể vẫn được xử lý.
- Nhưng lịch sử cũ **không tự được tạo lại**.

Cần **reconciliation/backfill/snapshot rebuild** trước khi tuyên bố phục hồi hoàn chỉnh.

### 2.3. Drift không luôn chứng minh có gap

Projection lệch nguồn có thể do:
- CDC event bị mất.
- Apply lỗi nhưng checkpoint vẫn tiến.
- Transformation bug.
- Schema migration sai.
- Search index bị mất dữ liệu.
- Event duplicate gây cộng dồn hai lần.
- Đọc snapshot nguồn và projection tại hai thời điểm khác nhau.
- Legitimate eventual lag.

Phải xác minh nguyên nhân, không tự suy mọi diff là stream missing.

## 3. Những kiểu mất đoạn luồng thay đổi

### 3.1. Consumer downtime vượt retention

~~~~text
Source commits: 101 102 103 104 105 106 107 108 109 110
Consumer last durable checkpoint: 104
Oldest retained event after outage: 108
Missing required history: 105 106 107
~~~~

Nếu events 105–107 không có bản sao ở một lưu trữ khác, không thể replay chúng từ stream gốc nữa.

### 3.2. Cursor bị vô hiệu hóa

Một resume token có thể không còn hợp lệ khi:
- Change history cần thiết đã bị dọn.
- Nguồn/cấu trúc stream thay đổi.
- Collection/table bị drop/recreate theo semantics engine.
- Consumer cố resume qua một loại invalidation không cho phép.
- Snapshot/backup restore dẫn tới lineage hoặc epoch khác.

Không khắc phục bằng cách giả mạo token hoặc tự tăng sequence trừ khi API hỗ trợ rõ.

### 3.3. Connector báo thành công sai

Một relay publish một batch rồi ghi checkpoint rằng đã phát xong, nhưng một phần events không được broker xác nhận bền. Nếu retry/ack order không đúng:
- Checkpoint có thể nhảy qua event chưa bền.
- Broker không có đoạn bị bỏ.
- Consumer downstream không thể tự phát hiện nếu event metadata không có chuỗi tuần tự đủ chặt.

### 3.4. Consumer ghi checkpoint trước khi apply

Timeline:

~~~~text
1. Consumer reads event 105.
2. Consumer stores checkpoint=105.
3. Process crashes before updating projection.
4. Restart from after 105.
5. Event 105 never applied.
~~~~

Đây là **mất event ở application level**, ngay cả khi broker còn giữ event trong retention.

### 3.5. Apply partial nhưng checkpoint vẫn tiến

Một batch chứa 100 events:
- 80 writes thành công.
- 20 writes fail.
- Consumer commit offset sau batch.
- 20 entity bị lệch.

Phải lưu trạng thái từng event/partition phù hợp, không tuyên bố batch hoàn tất khi những updates cần thiết chưa durable.

### 3.6. Consumer nhận event nhưng không hiểu schema

Nếu event v3 có field bắt buộc nhưng projector v2 bỏ qua hoặc parse sai:
- Stream không hề mất.
- Projection vẫn lệch.
- Replay bằng cùng code lỗi có thể tạo lại sai y hệt.

Cần phân loại **transformation bug** khác **retention gap**.

### 3.7. Xóa không được phản ánh

Delete event có thể bị:
- Lọc sai.
- Drop khỏi một compacted topic.
- Xử lý như null payload bỏ qua.
- Đến ngoài thứ tự rồi bị overwrite bởi stale update.

Kết quả là **phantom record** tồn tại ở search dù source đã xóa.

## 4. Không phải mọi offset số đều liên tiếp

Một lưu ý kỹ thuật quan trọng: **khoảng nhảy giữa hai offset không tự chứng minh đã mất event cần thiết**.

Tùy broker và consumer:
- Topic có compacted records.
- Partition có control records.
- Transaction bị abort.
- Consumer đọc qua filter/selection.
- Shard split/merge tạo sequence domains khác nhau.
- Một phần events không thuộc entity/subscription đang theo dõi.
- Source sequence không được cấp liên tiếp trên toàn bộ cluster.

Ví dụ:

~~~~text
Observed offset: 100 -> 104
~~~~

không đủ để kết luận events 101–103 bị mất. Có thể đó là các offset hợp lệ nhưng không thuộc record được consumer trả, hoặc là hệ thống không hứa sequence liên tục theo consumer view.

### 4.1. Mức độ bằng chứng

| Bằng chứng | Có thể kết luận |
| --- | --- |
| Consumer lag tăng | Đang chậm, chưa biết có mất |
| Resume token trả lỗi hết hạn | Không thể resume an toàn từ vị trí cũ theo API |
| Oldest retained position mới hơn checkpoint | Có nguy cơ đoạn backlog đã không còn |
| Per-key version từ 17 tới 20 | Có thay đổi trung gian hoặc version allocation semantics cần hiểu |
| Audit ledger có event IDs 105–109 nhưng broker thiếu | Có cơ sở kiểm tra segment missing |
| Source row v20, projection v17 | Có drift; nguyên nhân cần xác minh |
| Source vs projection hash mismatch tại cùng boundary | Có drift trong phạm vi hash |
| Offset nhảy từ 100 lên 104 | **Không đủ** nếu không có guarantee liền mạch |

### 4.2. Đừng tự tạo một global sequence từ nhiều shards

Mỗi shard/partition có:
- Offset riêng.
- Leader epoch/generation.
- Ordering riêng.
- Retention riêng.
- Có thể split/merge/rebalance.

Một consumer có thể hoàn thành offset 800 ở partition A nhưng chỉ 300 ở partition B. Không được dùng max(800,300) làm một “global checkpoint 800”.

### 4.3. Checkpoint vector

~~~~json
{
  "subscription": "booking-to-search",
  "checkpoints": {
    "partition-A": {"offset": 800, "epoch": 11},
    "partition-B": {"offset": 300, "epoch": 7}
  }
}
~~~~

Đây là một **mô hình metadata minh họa**, không phải token có thể tự gửi cho mọi broker. Một số systems dùng opaque resume token chứ không cung cấp số offset có thể so bằng toán học.

## 5. Những phương pháp phát hiện thiếu thay đổi

### 5.1. Resume error hoặc checkpoint không còn trong retention

Đây là bằng chứng vận hành mạnh:
- Consumer lưu checkpoint C.
- Stream API không cho resume từ C.
- Không có khả năng đọc mọi changes cần thiết qua một đường khác.

Phải chuyển sang recovery path đã định, không âm thầm seek latest.

### 5.2. Source version per aggregate

Một domain aggregate có thể tăng version khi commit:

~~~~text
Booking B-901: v16 -> v17 -> v18 -> v19
~~~~

Nếu read model đang v16 và nhận event v19:
- Có khoảng chênh cần xử lý.
- Nếu projection cần state từng version, phải recover v17/v18.
- Nếu v19 là full authoritative snapshot của aggregate và operation là upsert state, có thể apply v19 trực tiếp để đạt final state, nhưng **không khôi phục side effects/historical analytics** của v17/v18.

### 5.3. Commit ledger hoặc immutable event IDs

Nếu source có durable event/outbox ledger với:
- AggregateId.
- OperationId.
- AggregateVersion.
- EventId.
- Commit timestamp.
- Payload/schema version.

reconciliation có thể kiểm chứng events nào đã được publish/consumed. Nhưng nếu ledger cũng hết retention, không thể giả định lịch sử luôn phục hồi.

### 5.4. Heartbeat và progress watermark

Một pipeline có thể publish heartbeat/progress markers. Chúng giúp đo:
- Nguồn còn hoạt động.
- Connector còn đọc log.
- Consumer đã tiếp cận mốc nào.
- End-to-end lag.

Nhưng heartbeat **không chứng minh mọi data event đã được apply** nếu data/checkpoint path không có invariant tương ứng.

### 5.5. Row-level checksums và version comparison

Có thể so:
- Source key có tồn tại không?
- Source version lớn hơn projection version?
- Canonical projected fields có cùng hash?
- Delete marker có được phản ánh không?

Đây là đối soát **trạng thái hiện tại**. Nó không đủ để chứng minh mọi event trung gian đã chạy nếu cần lịch sử để tính aggregates hoặc external side effects.

### 5.6. Aggregates và invariant checks

Ví dụ:
- Tổng confirmed bookings theo ngày.
- Số booking theo tenant.
- Tổng amountMinor theo currency/status.
- Danh sách IDs đã xóa.
- Tỷ lệ stale versions.

Một total mismatch giúp phát hiện vấn đề nhưng không tự chỉ ra đúng record; cần drill down theo partition, tenant, time window rồi key.

## 6. Reconciliation cần một ranh giới so sánh hợp lệ

Nếu nguồn vẫn đang có writes, so source và projection tại hai thời điểm khác nhau có thể tạo **false positives**.

Ví dụ:
1. Reconciler đọc source v20.
2. Source cập nhật v21.
3. Projector nhận v21.
4. Reconciler đọc projection v21.
5. So source v20 với projection v21 → “mismatch”.

Không có gap; vấn đề là **khác thời điểm quan sát**.

### 6.1. Các chiến lược tạo boundary

- Database snapshot nhất quán tại commit/read timestamp H nếu engine hỗ trợ.
- CDC high watermark H và projection checkpoint theo H.
- Versioned source records và điều kiện chỉ so khi projection đã bắt kịp version cần.
- Range scan theo snapshot token/consistent read mode thích hợp.
- Pause writes trong maintenance window nhỏ, khi chấp nhận được.
- Reconcile nhiều lần và chỉ xác nhận drift bền sau grace window.

### 6.2. High watermark không tự là global clock

Nếu stream có nhiều partitions:
- H có thể là **vector các per-partition checkpoints**.
- Không thể lấy một timestamp không có đảm bảo đồng bộ rồi coi là transactionally consistent global snapshot.
- Khi một event chuyển từ partition A sang B do reshard, cần protocol ownership/epoch.

### 6.3. Eventual index cần cửa sổ ổn định

Một search index có thể tự refresh theo chu kỳ. Nếu vừa index document xong mà query ngay:
- Document có thể chưa searchable.
- Không nhất thiết projection write thất bại.

Reconciler phải biết **visibility/refresh semantics** của target và chỉ kết luận mismatch khi đã vượt cửa sổ cho phép hoặc đã dùng một read/checkpoint path thích hợp.

### 6.4. Không so hash của hai JSON có hình thức khác

Nếu source:

~~~~json
{"status":"CONFIRMED","amountMinor":1250000}
~~~~

projection có thêm fields tính toán, sorting khác, format timestamp khác, raw byte hash sẽ khác dù semantic đúng.

Phải định nghĩa canonical projection:

~~~~text
normalize(source business fields)
  -> transform using schema/policy version
  -> canonical serialize
  -> stable digest
~~~~

Rồi so với **cùng transformation version** của target.

## 7. Những loại chênh lệch cần đối soát

| Loại | Source | Projection | Hành động thường gặp |
| --- | --- | --- | --- |
| Missing document | Có | Không | Backfill/upsert từ source |
| Phantom document | Không/đã xóa | Có | Versioned delete/tombstone |
| Stale document | v20 | v18 | Replay hoặc replace bằng state v20 |
| Wrong field | Cùng version nhưng hash khác | Transform/index bug | Recompute, sửa code |
| Duplicate aggregate effect | 1 event logic | Counter bị cộng 2 lần | Rebuild/dedup ledger |
| Wrong tenant mapping | Tenant A | Tenant B | Incident bảo mật, quarantine |
| Wrong schema | v3 fields | v2 mapping | Reindex sau migration |
| Missing delete | Tombstone v7 | Document vẫn searchable | Apply delete/rebuild |
| Out-of-order overwrite | v12 | v10 sau late event | Version guard và repair |
| Partial index failure | Write accepted bởi broker | Target reject | Retry/DLQ/rebuild |
| Unverifiable historical effects | State hiện tại đúng | Audit/event history thiếu | Không thể suy lịch sử từ snapshot |

### 7.1. Đối soát trạng thái khác đối soát lịch sử

Nếu source hiện tại có quantity=12:
- Ta có thể tái dựng **snapshot quantity=12**.
- Không biết nó được tạo bởi những thao tác +4, -1, +9 nào nếu không có event log.

Vì vậy với:
- Audit.
- Billing.
- Notifications.
- Financial ledger.
- Usage metering có event-time windows.

mất events trung gian có thể **không thể khôi phục bằng một current-state snapshot**. Cần durable operation log khác, đối soát nguồn thứ ba hoặc đánh dấu vùng dữ liệu lịch sử không thể phục hồi đầy đủ.

### 7.2. Delete có thể biến mất khỏi full snapshot

Khi scan source chỉ thấy những records còn tồn tại, một key từng có rồi bị xóa không xuất hiện. Muốn xóa phantom khỏi projection, phải:
- So membership keys của projection với source tại cùng boundary.
- Hoặc đọc tombstone/delete ledger còn đủ retention.
- Hoặc rebuild target vào index/table mới từ source snapshot và cutover.
- Hoặc dùng một versioned delete feed được đảm bảo.

Chỉ chạy “upsert mọi source rows” lên target cũ **không dọn được phantom documents**.

## 8. Chọn cách khôi phục theo mức độ mất

| Tình huống | Lịch sử còn không? | Cách tiếp cận |
| --- | --- | --- |
| Consumer lag, cursor hợp lệ | Có | Resume/replay idempotent |
| Worker crash sau apply trước checkpoint | Có | Replay từ checkpoint cũ, dedup |
| Một event bị DLQ vì schema | Có trong DLQ/source | Sửa transformation, replay event |
| Broker còn events nhưng projection thiếu một phạm vi | Có | Replay phạm vi với version guard |
| Resume token hết hạn, source rows còn | Thiếu | Snapshot/backfill + stream cutover |
| Chỉ một số keys stale | Source state còn | Targeted reconciliation/backfill |
| Target index mất hoàn toàn | Source state còn | Full rebuild staging index |
| Source đã hard delete, tombstones cũng mất | Không đủ | Snapshot membership rebuild / restore backup nếu hợp lệ |
| Cần audit từng event nhưng source chỉ giữ current state | Không đủ | Đối chiếu external durable ledger; có thể không thể phục hồi chính xác |
| Source of truth cũng lỗi/mất dữ liệu | Không | Đây là source recovery, không chỉ CDC recovery |

### 8.1. Hành động bị cấm trong recovery nghiêm túc

Không nên:
- Tự seek latest rồi đánh dấu healthy.
- Tự tạo lại missing events từ current state như thể giống event gốc.
- Ghi checkpoint tiến lên khi apply chưa bền.
- Replay notifications/payments như lần chạy đầu.
- Xóa target cũ trước khi staging rebuild được kiểm chứng.
- Bỏ qua deletes vì chỉ quan tâm creates/updates.
- Dùng offset lớn nhất giữa nhiều partitions làm global checkpoint.

## 9. Replay từ checkpoint còn hợp lệ

Nếu stream vẫn giữ đủ dữ liệu:

~~~~text
Durable checkpoint C
       |
       v
Subscribe/resume from C
       |
       v
Read events in source-supported order
       |
       v
Validate schema / dedup / apply idempotently
       |
       v
Commit target updates
       |
       v
Advance durable checkpoint
~~~~

### 9.1. Checkpoint sau durable apply

Sai:

~~~~text
read event E
save checkpoint after E
apply target E
~~~~

Process crash giữa hai bước có thể **mất E**.

Cách thường an toàn hơn cho at-least-once:

~~~~text
read E
apply target idempotently and durably
save checkpoint after E
~~~~

Nếu crash sau apply trước checkpoint, E được phát lại. Idempotence/version guard giúp không nhân đôi hiệu ứng.

### 9.2. Nếu checkpoint và target cùng một DB transaction

Khi target và checkpoint nằm trong cùng database hỗ trợ transaction phù hợp, có thể commit **projection update + checkpoint** nguyên tử. Điều này giúp giảm cửa sổ duplicate/loss.

Nhưng:
- Transaction scope có giới hạn.
- External search index không thể tự tham gia một NoSQL transaction.
- Broker acknowledgement có cơ chế riêng.
- Side effects ngoài target vẫn cần idempotency.

### 9.3. Batch processing

Nếu một batch 100 events:
- 99 apply thành công.
- Một event fail.

Không được commit checkpoint sau event 100 nếu event lỗi cần thiết chưa durable. Có thể:
- Retry có giới hạn.
- Chuyển DLQ cùng trạng thái cần reconcile.
- Dừng partition trước event lỗi.
- Sử dụng per-key reorder nếu business cho phép.

Một DLQ entry **không tự chứng minh projection đã đúng**; phải có vận hành phục hồi và alert.

### 9.4. Ack mất sau apply

Nếu target đã commit nhưng consumer không nhận ACK:
- Có thể retry event.
- Apply phải idempotent.
- Không tạo order/payment/notification lần hai.
- Không coi timeout là bằng chứng target rollback.

## 10. Idempotent projection theo key và version

Một event envelope minh họa:

~~~~json
{
  "eventId": "evt-2026-445-105",
  "sourceId": "booking-service",
  "tenantId": "T-42",
  "aggregateId": "B-901",
  "aggregateVersion": 19,
  "operationId": "OP-901-19",
  "type": "BOOKING_CHANGED",
  "schemaVersion": 3,
  "sourcePartition": "p-2",
  "sourcePosition": "opaque-token-or-offset",
  "payload": {
    "status": "CANCELLED",
    "amountMinor": 1250000
  }
}
~~~~

### 10.1. Full-state upsert

Nếu event mang **full authoritative state**, một rule:

~~~~text
if incomingVersion > storedVersion:
    replace projected fields with incoming state
else:
    ignore duplicate / older version
~~~~

Giúp chống out-of-order old update overwrite new value. Nhưng cần:
- Atomic compare-and-set tại target.
- Version tăng theo một authority phù hợp.
- Schema transformation deterministic.
- Xử lý delete marker.
- Không giả định mọi event là full snapshot.

### 10.2. Delta event khác full-state event

Nếu event v19 là:

~~~~json
{"type":"GUEST_COUNT_INCREMENTED","delta":1}
~~~~

không thể bỏ v17/v18 và chỉ apply v19 rồi tuyên bố state đúng. Deltas phụ thuộc chuỗi operation.

Muốn repair projection sau gap:
- Lấy full current state từ source.
- Hoặc tìm lại mọi deltas qua ledger/replay.
- Hoặc recompute từ một snapshot ở trước gap và đủ events sau đó.

### 10.3. Exactly-once effect cần phạm vi rõ

Một consumer có thể nhận event hai lần nhưng nhờ dedup tạo **một logical update** ở target. Điều đó không có nghĩa end-to-end exactly-once cho email, webhook, payment provider, cache và mọi projection.

Định nghĩa per-sink:
- Idempotent upsert.
- EventId dedup ledger.
- Versioned overwrite.
- Conditional update.
- Transactional outbox.
- External operationId hoặc reconciliation.

### 10.4. Delete event

~~~~json
{
  "aggregateId": "B-901",
  "aggregateVersion": 20,
  "type": "BOOKING_DELETED",
  "deleted": true
}
~~~~

Tombstone v20 phải ngăn một update v18 đến muộn hồi sinh record. Nếu target xóa cả version marker quá sớm, một stale event có thể tạo lại document.

## 11. Java 21: mô hình ChangeEnvelope và trạng thái apply

Một mô hình typed envelope:

~~~~java
public enum ChangeKind {
    UPSERT,
    DELETE
}

public record ChangeEnvelope<K, V>(
        String eventId,
        String sourcePartition,
        String cursor,
        K key,
        long sourceVersion,
        int schemaVersion,
        ChangeKind kind,
        V value
) {
    public ChangeEnvelope {
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("eventId");
        }
        if (sourceVersion < 0) {
            throw new IllegalArgumentException("sourceVersion");
        }
    }
}

public enum ApplyResult {
    APPLIED,
    ALREADY_APPLIED,
    STALE_EVENT_REJECTED,
    RETRYABLE_FAILURE,
    PERMANENT_FAILURE
}
~~~~

Đây là dạng envelope dành cho **nguồn có version per key**. Cursor được giữ opaque dưới dạng String trong ví dụ, không được parse/tăng số tùy ý nếu provider không cho phép.

### 11.1. Một interface projection

~~~~java
public interface VersionedProjection<K, V> {

    // Atomically compares sourceVersion and writes the
    // corresponding projected state/tombstone.
    ApplyResult apply(ChangeEnvelope<K, V> change);

    // Reads a row including tombstone/version metadata.
    ProjectionSnapshot<V> get(K key);
}

public record ProjectionSnapshot<V>(
        boolean exists,
        boolean deleted,
        long sourceVersion,
        V value
) {}
~~~~

### 11.2. Lưu ý về ordering

Nếu một key được phân phối sang các partitions khác nhau theo thời gian, ordering per partition chưa đủ chứng minh per-key order. Version guard cần phù hợp source ownership/reshard protocol.

### 11.3. Không dùng eventId làm bản thay thế sourceVersion

EventId có thể là UUID không có thứ tự. Nó hữu ích cho dedup, nhưng không thể tự suy UUID “lớn hơn” là event mới hơn.

### 11.4. Xóa cũng mang version

Một projection row bị delete nên giữ tombstone/version metadata theo retention phù hợp. Nếu DELETE chỉ xóa item và bỏ version, event UPSERT cũ đến muộn có thể tái tạo dữ liệu.

## 12. Java: projector commit và checkpoint

Một processor giả lập:

~~~~java
public interface EventSource<E> {
    E readNext(String partition, String checkpoint) throws Exception;
}

public interface DurableCheckpointStore {
    String get(String consumerId, String partition);
    void save(String consumerId, String partition, String cursor);
}

public final class ProjectorRunner<K, V> {
    private final VersionedProjection<K, V> projection;
    private final DurableCheckpointStore checkpoints;

    public ProjectorRunner(
            VersionedProjection<K, V> projection,
            DurableCheckpointStore checkpoints
    ) {
        this.projection = projection;
        this.checkpoints = checkpoints;
    }

    public ApplyResult handle(
            String consumerId,
            ChangeEnvelope<K, V> event
    ) {
        ApplyResult result = projection.apply(event);

        if (result == ApplyResult.APPLIED
                || result == ApplyResult.ALREADY_APPLIED
                || result == ApplyResult.STALE_EVENT_REJECTED) {

            // Checkpoint only after durable, acceptable apply.
            // A real implementation must enforce per-partition
            // ordering and checkpoint ownership/epoch.
            checkpoints.save(
                    consumerId,
                    event.sourcePartition(),
                    event.cursor()
            );
        }

        return result;
    }
}
~~~~

### 12.1. Mã mẫu chưa đủ cho production

- Chưa xử lý transaction giữa target và checkpoint.
- Chưa kiểm tra checkpoint monotonicity hoặc partition epoch.
- Chưa xử lý rebalances/fencing zombie consumer.
- Chưa có idempotency ledger cho delta/events.
- Chưa có schema registry/upcast.
- Chưa có retry/deadline/DLQ policy.
- Chưa phát hiện cursor hết retention.
- Chưa có backpressure.
- Chưa định nghĩa stale-event-rejected có hợp lệ cho mọi event hay không.
- Chưa có logic delete/target visibility.
- Chưa có auth/tenant isolation.

**Chỉ checkpoint STALE_EVENT_REJECTED khi contract xác nhận event đó không có side effect cần xử lý khác.**

### 12.2. Consumer ownership epoch

Nếu partition chuyển từ consumer A sang B:
- A có thể bị pause rồi tỉnh.
- B đã xử lý các events mới.
- A không được ghi checkpoint cũ đè checkpoint mới.

Cần partition generation/lease ownership/fencing hoặc consumer-group protocol và durable compare-and-set.

## 13. Phát hiện missing history qua checkpoints

Một checkpoint nên mô tả:

~~~~json
{
  "consumer": "booking-search-projector",
  "source": "cdc-booking",
  "partitionId": "p-2",
  "ownershipEpoch": 17,
  "checkpointToken": "opaque-provider-cursor",
  "checkpointedAt": "2026-11-14T09:04:00Z",
  "lastAppliedEventId": "evt-104",
  "lastAppliedAggregateVersion": null,
  "schemaPolicyVersion": "booking-projection-v4"
}
~~~~

### 13.1. Opaque token phải được giữ nguyên

Một resume token có thể là cấu trúc nhị phân/opaque. Không:
- Tách bằng dấu hai chấm rồi tự cộng một.
- Dùng lexicographic compare để suy thứ tự.
- Suy token của collection A dùng được cho collection B.
- Sửa token khi leader epoch đổi.

Chỉ dùng API resume/seek được provider cho phép.

### 13.2. Retention budget

Đặt:

\[
R=\text{stream retention window}
\]

\[
O=\text{consumer outage duration}
\]

\[
B=\text{worst-case catch-up time}
\]

Một điều kiện an toàn sơ bộ:

\[
R > O + B + \text{safety margin}
\]

Nhưng chỉ là kiểm tra capacity, không thay semantics cụ thể:
- Retention có thể phụ thuộc size/traffic, không chỉ thời gian.
- Oplog window biến động theo write rate.
- Shard-specific retention.
- Paused connector có thể làm backlog ở nhiều nơi.
- Oldest available cursor cần đo thực.

### 13.3. Khả năng catch-up

Giả sử:
- Source tạo 20.000 events/s.
- Consumer sau hồi phục xử lý 25.000 events/s.

Tốc độ **giảm backlog** lý tưởng:

\[
25.000-20.000=5.000\text{ events/s}
\]

Nếu backlog 18 triệu events:

\[
18.000.000 / 5.000=3.600\text{ s}\approx 1\text{ giờ}
\]

Không phải 18 triệu /25.000, vì source vẫn đang tạo sự kiện. Nếu consumer processing rate thấp hơn hoặc bằng event arrival rate, backlog **không thể giảm** trong điều kiện ổn định.

### 13.4. Retention có đủ qua thời gian bắt kịp?

Nếu oldest unread event sắp hết retention và consumer catch-up net rate thấp:
- Có thể mất thêm events trong lúc đang cố phục hồi.
- Cần tăng capacity/retention theo giới hạn được provider cho phép hoặc chuyển rebuild path.
- Không lặng lẽ tiếp tục cho tới khi cursor lỗi.

## 14. Khôi phục có đủ lịch sử: replay có kiểm soát

Một quy trình thực dụng:

1. Xác nhận stream giữ đủ history kể từ durable checkpoint.
2. Chốt source namespace/partition identity và consumer group ownership.
3. Dừng hoặc fencing các consumer cũ ghi cùng projection/checkpoint.
4. Khôi phục consumer từ checkpoint hợp lệ.
5. Apply events idempotently; giữ thứ tự cần thiết per key.
6. Đo per-partition catch-up và target visibility.
7. Kiểm chứng một mẫu hoặc toàn bộ phạm vi ảnh hưởng.
8. Chỉ sau verify mới đánh dấu healthy.

### 14.1. Nếu event cũ đã được apply

Replay có thể nhận event E lần nữa. Nếu E là full-state upsert v18 và target đã v19:
- Versioned apply từ chối E không làm target đi lùi.
- Không tính thêm aggregate.
- Không gửi notification lại.

Nếu E là delta +10:
- Phải có eventId dedup ledger hoặc tái dựng từ source state.
- Không thể chỉ “cộng lại vì Kafka replay”.

### 14.2. Idempotence nên ở gần target

Một service có thể dedup trong process memory, nhưng sau restart sẽ quên. Nếu cần chống duplicate vững:
- Dùng durable dedup/version state ở target hoặc transactionally cùng target update.
- Giữ retention của dedup IDs phù hợp replay horizon.
- Không xóa ledger trước khi duplicate có thể quay lại.

## 15. Khi không thể replay: tái dựng từ snapshot và CDC mới

Nếu đoạn lịch sử đã mất, **current source snapshot + những thay đổi mới** thường là lựa chọn để đưa read model trạng thái trở lại đúng. Nhưng nó phải được thực hiện ở một **ranh giới** tránh miss/overwrite writes đang xảy ra.

~~~~mermaid
flowchart TD
    GAP["Gap unrecoverable"] --> SCOPE["Define affected source/target scope"]
    SCOPE --> BOUND["Establish snapshot/stream boundary"]
    BOUND --> STAGE["Build staging projection from source"]
    STAGE --> TAIL["Apply all changes across boundary"]
    TAIL --> CATCH["Catch up to target watermark"]
    CATCH --> VERIFY{"Reconciliation passes?"}
    VERIFY -->|No| FIX["Repair gaps/transform errors"]
    FIX --> TAIL
    VERIFY -->|Yes| SWITCH["Controlled cutover"]
    SWITCH --> MONITOR["Monitor + rollback plan"]
~~~~

### 15.1. Không xóa target cũ ngay lập tức

Nếu phục hồi search index:
- Tạo **staging index** mới.
- Giữ index hiện tại phục vụ đọc trong khi rebuild, với trạng thái degraded/freshness phù hợp.
- Backfill source vào staging.
- Replay changes mới vào staging.
- Verify.
- Switch alias/routing atomically nếu target hỗ trợ.
- Giữ khả năng rollback trong cửa sổ đã định.

Nếu rebuild trực tiếp lên target đang nhận traffic, người dùng có thể thấy:
- Items mất rồi xuất hiện lại.
- Duplicate records.
- Mapping/schema lỗi.
- Nhiều lần reindex dưới tải production.

### 15.2. Snapshot nhất quán là vấn đề khó

Một scan kéo dài 2 giờ đọc từng page:
- Page 1 đọc lúc 09:00.
- Page cuối đọc lúc 11:00.
- Source vẫn đổi suốt 2 giờ.

Chúng không tự đại diện cho **một snapshot nhất quán tại thời điểm H**. Nếu chỉ đọc scan rồi “bắt đầu CDC sau scan”, có thể bỏ mọi write trong cửa sổ scan.

### 15.3. Cần overlap có kiểm soát

Một thiết kế tổng quát:
1. Chọn **một vị trí stream còn hợp lệ trước khi bắt đầu snapshot**, hoặc lấy snapshot và stream cursor tại cùng một transactionally defined boundary nếu provider hỗ trợ.
2. Bảo đảm các changes từ boundary được giữ đủ lâu.
3. Chụp nguồn tại một consistent snapshot boundary hoặc dùng thuật toán snapshot+stream đã được provider chứng minh đúng.
4. Build staging projection.
5. Replay CDC từ boundary, chống trùng và dùng version/order guards.
6. Tiếp tục tailing cho tới khi bắt kịp watermark.
7. Reconcile cùng boundary và cutover.

Đây là **khung tư duy**. Chi tiết phức tạp vì “cursor trước scan” và snapshot không nhất quán vẫn có race cần xử lý.

### 15.4. Vì sao snapshot-before-stream có thể mất write?

~~~~text
09:00 Start source scan
09:30 Booking B updates v7 -> v8
10:00 Finish source scan
10:01 Start CDC subscription at current head
~~~~

Nếu scan đã đọc Booking B trước 09:30, staging có v7. Change v8 xảy ra trước khi subscribe và không được replay → staging thiếu v8.

### 15.5. Vì sao stream-before-snapshot vẫn cần version guard?

~~~~text
09:00 CDC cursor C captured
09:10 Booking B updated v8 (event captured)
09:30 Snapshot scan reads B v8
10:00 Replay event v8
~~~~

Không mất event nhưng có duplicate logical application nếu event là delta và snapshot đã bao gồm effect. Version guard hoặc snapshot boundary giúp phân loại.

### 15.6. Một consistent snapshot H

Một lý tưởng khi provider hỗ trợ:
- Snapshot cho mọi included keys tương ứng tới H.
- CDC replay đúng các changes **sau H**.
- Mọi changes tại hoặc trước H đã nằm trong snapshot.
- Mọi changes sau H được replay.
- H đủ định nghĩa trên partitions/shards.

Không tự giả định mọi NoSQL scanner hoặc CDC API hỗ trợ exact H. Có thể cần connector-specific snapshot protocol, maintenance window hoặc migration method.

## 16. Một thuật toán rebuild khi nguồn không có global snapshot

Nếu provider không hỗ trợ snapshot H toàn cục, có thể cần một thuật toán **scan có overlap + versioned replay** với những giả định rõ:

1. Bắt đầu capture stream từ một cursor C hợp lệ trước scan, giữ events liên tục.
2. Scan từng key nguồn và ghi current sourceVersion vào staging.
3. Replay toàn bộ events từ C, với per-key idempotence/version ordering và delete semantics.
4. Dùng cơ chế reliable capture để không mất creates/deletes sau khi scan qua một range.
5. Đảm bảo một event cũ không thể xóa/ghi đè version mới đã scan.
6. Khi thấy gap trong captured stream, **bắt đầu lại hoặc chuyển recovery method**, không cắt tiếp tới latest.
7. Đạt checkpoint frontier đủ mới, reconcile sample/ranges và cutover.

### 16.1. Vì sao overlap chỉ an toàn khi event đủ ngữ nghĩa?

Giả sử scan thấy v8, replay một delta v7:
- Nếu chỉ có “increment +1” mà không biết version snapshot đã bao gồm delta chưa, có thể cộng hai lần.
- Cần dedup ledger, versioned state transitions hoặc full-state refresh.
- Với delete/update, phải ngăn bản cũ hồi sinh.

### 16.2. Scan và delete giữa các pages

Một key có thể:
- Chưa được scan thì bị delete.
- Đã được scan rồi mới bị delete.
- Được tạo sau khi scan qua range của nó.
- Di chuyển partition trong lúc scan.

Cơ chế capture replay phải bao phủ mọi trường hợp này hoặc có một postscan reconciliation đủ mạnh trước cutover. Nếu không thể chứng minh, cần dừng writes/consistent snapshot/provider-native bootstrap.

### 16.3. Không coi scan và stream là hai phần độc lập

Đây là bài toán **atomic snapshot+stream handshake**. Mỗi provider có semantics và limitations riêng; phải đánh giá đúng chiến lược phù hợp thay vì dùng công thức chung không chứng minh correctness.

## 17. Bù dữ liệu theo phạm vi thay vì full rebuild

Nếu chỉ 2.000 keys lệch trên 100 triệu keys, full rebuild có thể rất tốn kém. Có thể backfill có mục tiêu:

~~~~text
Identify affected tenant/key range/shard
  -> obtain authoritative source state/version
  -> compare target
  -> conditional upsert/delete
  -> verify after catch-up
~~~~

### 17.1. Khi nào targeted repair đủ?

- Có danh sách keys bị ảnh hưởng đáng tin.
- Projection chỉ giữ current-state fields.
- Delete semantics có thể khôi phục.
- Transformer hiện tại đúng.
- Stream mới không có gap trong lúc repair.
- Có version guard ngăn target đi lùi.

### 17.2. Khi nào targeted repair không đủ?

- Không biết phạm vi keys bị mất.
- Mất create/delete events không có index key ledger.
- Aggregates tính bằng incremental deltas nhưng không thể rederive từ current rows.
- Data mapping/schema cũ sai toàn bộ.
- Search index mất lớn hơn một shard.
- Source hard deletes và no tombstone make membership unknown.
- Có external side effects thiếu event history.

Khi đó thường cần rebuild phạm vi rộng hơn hoặc dùng ledger/backups khác.

### 17.3. Repair cũng là write cạnh tranh

Trong lúc repair:
- Projector bình thường có thể update target.
- Backfill đọc source phiên bản cũ hơn.
- Repair write đến muộn có thể ghi đè target mới.

Dùng version-aware conditional write hoặc tách staging/cutover, không thực hiện blind PUT.

## 18. Reconciliation theo key, version và nội dung

Một row source:

~~~~json
{
  "key": "T42#B901",
  "sourceVersion": 20,
  "deleted": false,
  "businessPayload": {
    "status": "CANCELLED",
    "amountMinor": 1250000
  }
}
~~~~

Projection:

~~~~json
{
  "key": "T42#B901",
  "sourceVersion": 18,
  "deleted": false,
  "businessPayload": {
    "status": "CONFIRMED",
    "amountMinor": 1250000
  }
}
~~~~

Diff có thể xác định:
- Key tồn tại ở cả hai.
- Source version lớn hơn.
- Status khác.
- Target cần rebuild/upsert.

### 18.1. Không dùng sourceVersion duy nhất

Hai data rows có cùng version nhưng nội dung khác nếu:
- Transformer bug.
- Schema migration.
- Manual edit vào target.
- Target corruption.

Vì vậy có thể kết hợp **version + canonical digest**, ở boundary hợp lệ.

### 18.2. Canonical digest

Một hashing procedure nên thống nhất:
- Field subset mà projection phải phản ánh.
- Field ordering.
- Unicode normalization.
- Null vs missing.
- Decimal precision/currency.
- Date/time zone.
- Schema/transform version.
- Delete semantics.

Ví dụ:

~~~~text
canonicalPayload =
  "status=CANCELLED|amountMinor=1250000|currency=VND"

digest = SHA-256(canonicalPayload)
~~~~

Không nhất thiết lưu raw PII ở đối soát nếu có thể dùng digest và key có quyền kiểm soát. Nhưng digest của giá trị ít entropy có thể bị đoán; không xem hash như anonymization tuyệt đối.

### 18.3. Hash có giới hạn

- Hai kết quả hash khác → có bằng chứng payload khác trong phạm vi canonicalization.
- Hash giống → xác suất collision cực thấp với cryptographic hash phù hợp, nhưng còn có thể cả hai cùng được transform sai logic.
- Hash không chứng minh mọi business invariant của toàn bộ hệ.
- Version/digest của projection phải tương ứng đúng schema policy.

## 19. Đối soát theo range, bucket và Merkle tree

Với hàng trăm triệu records, đọc và so từng row liên tục có thể quá tốn.

Một chiến lược theo cấp:

1. Chia keyspace thành ranges hoặc buckets theo tenant/shard/prefix.
2. Tính count và digest theo range tại cùng logical boundary.
3. So source range với target range.
4. Khoanh những ranges lệch.
5. Chia nhỏ tiếp tới cấp key.
6. Repair keys lệch.
7. Verify lại range.

### 19.1. Tại sao không chỉ so row count?

Source và target đều có 1.000.000 records nhưng:
- Source thiếu A, có B.
- Target có A, thiếu B.

Count vẫn bằng nhau. Cần membership/key digest và value digest.

### 19.2. Merkle tree trực giác

~~~~mermaid
flowchart TD
    ROOT["Root digest"] --> L["Bucket 0-49 digest"]
    ROOT --> R["Bucket 50-99 digest"]
    L --> L1["0-24"]
    L --> L2["25-49"]
    R --> R1["50-74"]
    R --> R2["75-99"]
~~~~

Nếu root khác:
- So child digests.
- Chỉ đi sâu vào branches lệch.
- Có thể giảm số rows phải truyền khi khác biệt ít.

### 19.3. Những điều kiện Merkle cần

- Cùng key partitioning.
- Cùng sort order.
- Cùng canonical projection.
- Snapshot boundary tương thích.
- Delete/missing semantics rõ.
- Hash version/policy thống nhất.

Nếu source và target đang thay đổi không đồng bộ trong lúc scan, Merkle root mismatch có thể phản ánh **khác thời điểm**, không nhất thiết lost history.

### 19.4. Range scan có thể làm NoSQL quá tải

- Full table scan có thể cạnh tranh IO/CPU với interactive writes.
- Query qua secondary index có eventual lag.
- Pagination tokens có expiry/snapshot semantics riêng.
- Hot partitions có thể nặng hơn.
- Tenants lớn cần quota.

Reconcile phải có **read budget, rate limits, shard-aware schedule**.

## 20. Delete/tombstone và phantom records

Một event delete có thể bị mất:

~~~~text
Source:
  B-901: deleted at version 20

Target:
  B-901: CONFIRMED at version 19
~~~~

Khi rebuild từ snapshot hiện tại:
- Source không còn B-901.
- Nếu staging target bắt đầu trống, B-901 không được tạo.
- Nếu repair in-place chỉ upsert source keys, B-901 vẫn còn trong target.

### 20.1. Các cách dọn phantom

- Scan target keys, xác minh source existence và xóa khi thật sự không tồn tại tại boundary.
- Dùng delete/tombstone event ledger có đủ retention.
- So sorted key sets tại consistent boundary.
- Build new index từ empty và cutover, không copy phantom từ old index.
- Dùng authoritative deletion registry khi business cần.

### 20.2. Tombstone chống resurrection

Nếu target nhận event:
1. DELETE v20.
2. UPSERT v19 đến muộn.

Không được tạo lại B-901 từ v19. Giữ tombstone/version watermark đủ lâu để từ chối stale event.

### 20.3. Tombstone garbage collection

Retention phải xét:
- Max CDC replay horizon.
- Offline consumers.
- Source repair/backup restore.
- Event reordering.
- Rebuild/reindex thời gian dài.
- Privacy erasure requirements.

Nếu xóa tombstone sớm rồi event cũ quay lại, record có thể hồi sinh.

### 20.4. Privacy deletion khác audit retention

Bài toán reconciliation thường thích giữ history lâu, nhưng dữ liệu cá nhân có erasure/retention policy. Cần:
- Xóa nội dung tại source và projections.
- Dọn cache/index/backups theo policy.
- Giữ audit tối thiểu được phép.
- Tránh tái nhập PII từ snapshot cũ không được phép.

## 21. Aggregates: một current-state rebuild có đủ không?

Giả sử read model doanh thu được cập nhật bằng events:
- BookingConfirmed +1.250.000.
- BookingCancelled -1.250.000.
- BookingRefunded +adjustment theo accounting rules.

Nếu mất BookingCancelled:
- Current booking có status CANCELLED.
- Có thể recompute một **current booking status count**.
- Nhưng không thể khôi phục chính xác event-time financial ledger hoặc notification history nếu mọi thông tin lịch sử đã mất.

### 21.1. State-derived aggregate

Ví dụ “số booking hiện đang CONFIRMED”:
- Có thể scan source hiện tại.
- Đếm theo tenant/region.
- Build aggregate from state.
- Tailing CDC để bắt kịp.

### 21.2. Event-derived aggregate

Ví dụ “tổng số lần chuyển CONFIRMED→CANCELLED theo từng giờ”:
- Cần lịch sử transitions/time.
- Current status một mình không đủ.
- Có thể cần audit/event store khác hoặc đánh dấu không thể reconstruct chính xác.

### 21.3. Ledger và payment

Một payment event bị mất **không được tái dựng thành một payment mới** rồi gọi provider để “bù”. Điều đó có thể charge trùng.

Cần:
- Đối soát provider transaction IDs.
- Source operation ledger.
- Idempotency keys.
- Quy trình điều chỉnh/reversal nếu được phép.
- Audit xác nhận nguồn dữ liệu thứ ba.

### 21.4. Notifications

Rebuild search projections không nên gửi lại email “Booking confirmed” của 6 tháng trước. Consumer phải phân biệt:
- Projection replay/backfill.
- Business side effects.
- User notifications.

Replay mode có thể chặn side effects và tạo một event/state recompute riêng theo contract.

## 22. Kafka: offsets, retention, compaction và recovery

Kafka thường được dùng như broker cho CDC/outbox. Những điểm cần nắm:

### 22.1. Offset thuộc partition

Một topic có nhiều partitions:
- Mỗi partition có offset độc lập.
- Consumer group phối hợp assignment.
- Khi rebalance, owner có thể đổi.
- Committed offset không đồng nghĩa mọi external sink writes đã durable nếu ứng dụng không bảo đảm.

Không lấy max offset trên topic làm vị trí global.

### 22.2. Retention

Kafka giữ records theo policy retention/cleanup và storage capacity. Một consumer chậm vượt vùng được giữ có thể không đọc lại đoạn cũ.

Cần đo:
- Earliest retained offset per partition.
- Consumer committed position.
- Event production/catch-up rate.
- Time-to-retention-risk.

### 22.3. Log compaction

Một compacted topic có thể giữ state mới nhất theo key thay vì mọi intermediate update. Nó có thể phù hợp cho **state restore** trong một số model, nhưng **không thể dùng như immutable audit history** của mọi transition.

### 22.4. Kafka tombstone

Trong compacted topics, record có key và null value thường có ý nghĩa tombstone xóa theo semantics broker/connector. Tombstone retention/cleanup có giới hạn; một consumer quá chậm có thể không còn đủ lịch sử delete để rebuild in-place an toàn.

### 22.5. Transactional producer/consumer có phạm vi

Kafka transactions có thể liên kết một số writes vào Kafka topics với offset commits theo design, nhưng không tự biến một external NoSQL search index write thành cùng một transaction Kafka. Cần target idempotence/reconciliation.

### 22.6. Partition reassignment và leader epoch

Recovery phải tôn trọng partition/leader epoch và offset APIs. Không tự dùng một offset từ partition A cho B hoặc coi leader change là bằng chứng event loss nếu broker vẫn có history.

## 23. MongoDB Change Streams và resume tokens

MongoDB Change Streams có thể theo dõi những thay đổi được công bố từ database/collection/deployment phù hợp, thường dựa trên oplog/change history và các điều kiện deployment.

### 23.1. Resume token

Một event có thể có opaque resume token. Ứng dụng lưu token khi đã xử lý event theo checkpoint policy.

Khi restart:
- Mở change stream với resume option phù hợp.
- Tiếp tục sau vị trí đã lưu nếu còn hợp lệ.
- Apply idempotently.

**Không tự parse resume token để tính offset.**

### 23.2. Oplog retention window

Khả năng resume phụ thuộc vùng history còn tồn tại. Nếu token cũ vượt history được giữ, resume có thể thất bại. Khi đó không phải cứ retry cùng token liên tục sẽ khôi phục được đoạn đã bị dọn.

Cần:
- Alert theo oplog/change stream lag.
- Giảm downtime.
- Kéo dài window/capacity nếu deployment cho phép.
- Snapshot/backfill recovery plan.

### 23.3. Invalidate event

Change Stream có những semantics riêng khi collection/database bị drop/rename hoặc stream bị invalidate. Một số resume API phân biệt **resumeAfter** và **startAfter** đối với invalidation. Phải dùng option theo contract và token/event type thực tế, không gộp mọi lỗi vào “cursor expired”.

### 23.4. fullDocument và update events

Một update event có thể không mang full state nếu không cấu hình lookup phù hợp. Một option lấy current document sau update **không tự bảo đảm đó là đúng exact post-image của event trong mọi race**; cần đọc semantics cụ thể và sử dụng pre/post images hoặc versioned source state khi cần.

### 23.5. Snapshot + Change Stream

Một full collection scan và start change stream **sau** scan có thể bỏ writes ở giữa. Phải dùng một snapshot/resume boundary và protocol bootstrap được chứng minh đúng cho phiên bản/topology đang chạy.

### 23.6. Reconciliation

Nếu source MongoDB B-901 v20, search index v18:
- Có thể reread authoritative MongoDB document.
- Recompute search representation.
- Conditional upsert target.
- Nếu document deleted, cần target membership scan hoặc tombstone ledger để xóa phantom.

Không dựa vào search index eventual để kết luận source state.

## 24. DynamoDB Streams: shards, retention và snapshot rebuild

DynamoDB Streams có stream records/shards với sequence identifiers/iterators và retention window hữu hạn theo hợp đồng dịch vụ. Trong nhiều deployment, retention tương đối ngắn so với yêu cầu disaster recovery dài ngày; cần kiểm tra giới hạn hiện hành của dịch vụ và cấu hình.

### 24.1. Stream view type

Stream có thể cung cấp dữ liệu theo kiểu:
- Keys only.
- New image.
- Old image.
- Old and new images.

Khả năng rebuild projection từ **một event duy nhất** phụ thuộc stream view type và projection semantics.

Nếu chỉ có keys, projector có thể phải query source; source current state có thể đã thay đổi nhiều lần giữa event và lookup.

### 24.2. Shard ordering

- Ordering có phạm vi shard/partition theo contract.
- Shards có thể split/rollover.
- Không dùng một sequence number như global total order.
- Cần checkpoint theo shard và lifecycle.

### 24.3. Hết retention

Nếu consumer downtime vượt window:
- Không thể tự recover mọi events bằng iterator cũ.
- Có thể phải export/scan source và dựng projection mới với change capture overlap hợp lệ.
- Nếu chỉ cần current state, rebuild có thể khả thi.
- Nếu cần mọi transitions, phải có durable event ledger/other archive.

### 24.4. DynamoDB global tables

Trong multi-region systems, các mode replication và ordering có ngữ nghĩa khác nhau. Không giả định stream từ một region phản ánh mọi conflict theo một total order toàn cầu. Reconciliation phải xác định **region/source authority và đúng consistency mode**.

### 24.5. DynamoDB GSI khác CDC projection

GSI cũng có freshness/visibility contract riêng. Không dùng GSI lag làm bằng chứng source table đã rollback hay stream event không tồn tại.

## 25. Debezium và connector-based CDC

Debezium thường được dùng để đọc database change logs và publish structured events tới Kafka hoặc nền tảng tương ứng. Dù ví dụ phổ biến là relational database logs, những khái niệm snapshot/offset/connector recovery rất hữu ích cho NoSQL CDC.

### 25.1. Connector offset

Connector có thể lưu:
- Source log position.
- Snapshot status.
- Partition info.
- Schema metadata.
- Transaction boundary metadata.

Offset phải được commit đúng với delivery guarantee; nếu connector offset tiến trước khi publish durable, downstream có thể không còn event.

### 25.2. Snapshot modes

Connector có thể có:
- Initial snapshot.
- Incremental snapshot.
- Snapshot khi log không còn đủ history.
- Schema-only hoặc no-snapshot modes tùy connector.

Không giả định reset offset rồi restart tự tạo exactly-one consistent snapshot cho mọi connector. Phải đọc semantics **cụ thể** của source connector.

### 25.3. Schema history

Một connector có thể cần schema history để giải mã events cũ. Nếu schema history bị mất:
- Payload cũ có thể không decode được.
- Chỉ replay broker messages chưa chắc đủ.
- Cần restore connector state/schema history hoặc rebuild phù hợp.

### 25.4. Transaction metadata

Nếu source thay đổi nhiều entities trong một transaction, event stream có thể mang boundary metadata (tùy connector). Projection cần biết có bắt buộc áp một snapshot transactionally consistent hay không; không coi mọi collection event độc lập khi invariant liên quan nhiều bản ghi.

## 26. Redis Streams, Cassandra CDC và HBase

### 26.1. Redis Streams

Redis Streams hỗ trợ stream IDs, consumer groups và pending entries trong phạm vi cơ chế của Redis. Lưu ý:
- Pending entries là records đã giao nhưng chưa ACK.
- ACK/claim/retry có thể dẫn tới duplicate delivery.
- Trimming/retention có thể xóa stream entries dù có consumer chậm.
- Một stream ID nhảy không tự chứng minh event loss nếu ứng dụng không có continuity contract.
- Redis Streams không tự là permanent audit log; persistence/replication và trimming phải được thiết kế.

Nếu stream entry đã bị trim và không có alternate ledger, consumer không thể “claim” lại nội dung đã mất. Cần backfill/rebuild từ source.

### 26.2. Cassandra CDC

Cassandra có những cơ chế CDC và log lifecycle theo phiên bản/cấu hình. Cần xem:
- CDC-enabled tables.
- Commitlog/CDC segment storage.
- Disk budgets và retention.
- Consumer acknowledgments.
- Table/partition ordering.
- Replay và backfill limitations.

Không tự giả định các CDC files còn vĩnh viễn hoặc cung cấp một global sequence duy nhất.

### 26.3. HBase/WAL replication

HBase có WAL/replication/change processing semantics riêng:
- Log retention/replication lag.
- Region splits/moves.
- Row-key ordering.
- Snapshot/recovery tools theo deployment.

Một recovery algorithm phải tôn trọng region lifecycle và checkpoint semantics, không chỉ “tăng offset”.

### 26.4. Elasticsearch/OpenSearch làm sink

Search sink có:
- Refresh/visibility delay.
- Bulk request partial failures.
- Mapping errors.
- Document versioning/external version options tùy API.
- Aliases/staging index cutover.

Một bulk response HTTP 200 có thể chứa **per-item failures**; projector không được checkpoint cả batch nếu một số document updates cần thiết thất bại.

## 27. Reconciliation workflow có trạng thái rõ ràng

Một recovery coordinator có thể dùng:

~~~~text
DETECTED
   |
   v
SCOPED
   |
   v
PAUSED_OR_FENCED
   |
   +----> REPLAYING
   |         |
   |         v
   |       VERIFYING
   |
   +----> SNAPSHOTTING
             |
             v
           CATCHING_UP
             |
             v
           VERIFYING
             |
             v
        READY_FOR_CUTOVER
             |
             v
           CUTOVER
             |
             v
           MONITORING
             |
             v
           COMPLETE
~~~~

Các trạng thái khác:
- BLOCKED_SOURCE_UNAVAILABLE.
- BLOCKED_HISTORY_EXPIRED.
- INVALID_SCHEMA.
- RECONCILIATION_MISMATCH.
- ROLLBACK_REQUIRED.
- MANUAL_INTERVENTION_REQUIRED.

### 27.1. Recovery operation ID

Mỗi lần rebuild nên có:

~~~~json
{
  "recoveryId": "REC-2026-445",
  "projection": "booking-search-v4",
  "scope": {
    "tenants": ["T-42"],
    "sourcePartitions": ["p-2"]
  },
  "mode": "SNAPSHOT_AND_TAIL",
  "state": "CATCHING_UP",
  "snapshotBoundary": "provider-specific",
  "tailCheckpoints": {
    "p-2": "opaque-cursor"
  },
  "policyVersion": "booking-projection-v4",
  "startedAt": "2026-11-14T09:05:00Z"
}
~~~~

Có stable recoveryId giúp:
- Resume work khi coordinator restart.
- Tránh hai rebuild jobs cùng cutover.
- Audit operator decision.
- Gắn metrics và staging resources.
- Có rollback khi cutover lỗi.

### 27.2. Fencing các worker cũ

Nếu projection có hai writers:
- Old worker còn đang apply event v17.
- New rebuild đã tới v20.
- Old worker tiếp tục ghi v17 vào target.

Cần:
- Tách staging target.
- SourceVersion CAS.
- Consumer group ownership/epoch.
- Stop/fence workers.
- Cutover barrier.

Đừng chỉ “kill process” rồi hy vọng không còn async writes đang chạy.

## 28. Cutover sang projection mới

### 28.1. Điều kiện cutover

Tối thiểu:
- Staging snapshot hoàn tất và phạm vi rõ.
- Tail CDC không có gap.
- Per-partition checkpoints đủ mới so watermark.
- Reconciliation tại boundary hợp lệ đạt ngưỡng.
- Delete/phantom handling đã được kiểm tra.
- Schema/transform version đúng.
- Target search refresh/visibility hoàn tất khi cần.
- Có rollback/routing plan.
- Latency/capacity của staging đủ cho production traffic.

### 28.2. Alias/route switch

Với search target hỗ trợ alias/routing cutover:
- Old index tiếp tục phục vụ.
- New index được build và tail.
- Verify.
- Switch alias.
- Bảo đảm ongoing CDC writes chuyển sang new index.
- Giữ old index trong retention phù hợp rollback.

Một alias switch có thể atomic về routing nhưng **không tự atomic cùng consumer checkpoint**; phải thiết kế publisher/consumer transition và tránh bỏ events ở cutover.

### 28.3. Nếu new index vẫn đang catch-up

Có thể:
- Tiếp tục tail cho đến lag nhỏ theo SLO.
- Dùng barrier tại H.
- Quiesce rất ngắn để swap.
- Dual-write projection có idempotence trong transition.

Không hứa zero lag chỉ vì source và target counts tạm bằng nhau.

### 28.4. Rollback

Nếu cutover xong có mapping/query errors:
- Route lại old target nếu vẫn đủ hợp lệ.
- Không rollback sang target cũ đã quá stale mà không thông báo/degraded mode.
- Có cách replay changes mới cho old target nếu rollback.
- Không xóa staging/checkpoints quá sớm.

## 29. Đối soát dưới tải production

### 29.1. Read budget

Full source scan có thể làm:
- Hot partitions chậm.
- Compaction/GC tăng.
- Read amplification và disk IO tăng.
- p99 của API chính tăng.

Thiết kế:
- Rate limit theo region/shard.
- Adaptive concurrency.
- Pauses khi source saturation.
- Off-peak windows.
- Sampling/changed-range prioritization.
- Separate read replicas chỉ khi consistency phù hợp.

### 29.2. Backfill write budget

Search bulk indexing có thể:
- Tạo segment merge pressure.
- Làm query p99 tăng.
- Gây refresh lag.
- Vượt heap/memory.
- Trả partial errors.

Cần small batches, backoff, per-item failure accounting và kiểm chứng.

### 29.3. Tenant fairness

Không để một tenant cực lớn chiếm toàn bộ recovery queue. Phân chia:
- Priority business-critical.
- Per-tenant quotas.
- Oldest drift.
- Region fault domain.
- SLA tiers theo hợp đồng.

### 29.4. Reconciliation không được tự tạo incident khác

Một job full scan không được đẩy source read pool tới saturation và khiến CDC lag tiếp tục tăng. Phải quan sát phản hồi:
- Source CPU/IO.
- Backlog growth.
- Read p99.
- Index write throughput.
- Error budgets.

## 30. Metrics cần có trước khi xảy ra gap

| Chỉ số | Câu hỏi |
| --- | --- |
| Per-partition consumer lag | Có đang chậm không? |
| Oldest available cursor vs checkpoint | Gần hết retention chưa? |
| Time-to-history-expiry | Bao lâu nữa không thể resume? |
| Connector source/publish lag | Sự kiện đang tắc ở đâu? |
| Checkpoint age | Bao lâu chưa checkpoint bền? |
| Events received/applied/failed | Có drop apply không? |
| Duplicate delivery rate | Retry/rebalance có tăng không? |
| DLQ size and oldest age | Poison events bị tồn bao lâu? |
| Schema decode failures | Có mapping bất tương thích? |
| Per-key sourceVersion lag | Projection chậm tới đâu? |
| Count/hash drift by bucket | Có vùng dữ liệu sai? |
| Missing target rows | Create/update không được apply? |
| Phantom target rows | Delete bị bỏ? |
| Stale overwrite rejects | Có late events bị chặn? |
| Recovery snapshot progress | Backfill bao nhiêu phần trăm? |
| Tail catch-up net rate | Có bắt kịp source được không? |
| Reconciliation mismatch rate | Rebuild có chính xác? |
| Search visibility lag | Sink write đã searchable chưa? |
| Cutover verification failures | Staging đã ready chưa? |
| External side-effect replay attempts | Có vô tình gửi lại? |
| Resource budget | Source/sink có quá tải? |
| Data freshness SLO | Người dùng chịu độ lệch bao lâu? |

### 30.1. Lag cần đo nhiều tầng

~~~~text
NoSQL committed
  -> CDC extracted
  -> connector published
  -> broker stored
  -> consumer read
  -> target write durable
  -> search visible
  -> query sees update
~~~~

Nếu chỉ đo broker consumer lag, một target mapping error vẫn có thể làm read model sai dù consumer offsets đang tiến.

### 30.2. Data correctness SLO

Ngoài latency:
- Mức source–projection drift tối đa.
- Thời gian từ source commit tới searchable.
- Tuổi lớn nhất của unresolved mismatch.
- Số phantom records.
- Phần trăm deletes được phản ánh trong bound.
- RTO cho rebuild khi stream history expired.
- RPO của audit/event-history pipeline.

### 30.3. Không nhầm zero lag với correctness

Consumer ở latest offset chưa chắc đúng vì:
- Có events bị bỏ trước checkpoint.
- Schema transform sai.
- Target write partial failure.
- Old CDC gap đã xảy ra trước đó.

**Zero offset lag không phải bằng chứng không có drift.**

## 31. Một ví dụ đối soát theo bucket

Giả sử T-42 có 1 triệu bookings, chia 256 buckets theo hash của bookingId.

~~~~text
bucket = stableHash(tenantId + bookingId) mod 256
~~~~

Mỗi bucket có:
- Source count.
- Target count.
- Canonical digest tổng hợp.
- Snapshot boundary/watermark.
- Last reconciliation timestamp.

### 31.1. Scan nhanh

Nếu 255 buckets có count/hash khớp, bucket 17 lệch:
- Chỉ scan sâu bucket 17.
- So source/target key set.
- Đối chiếu versions/hashes.
- Repair rows.
- Verify lại bucket.

### 31.2. Delete phantom

Bucket 17 có source 10.000 keys, target 10.001 keys:
- Có thể một phantom.
- Nhưng count 10.001 cũng có thể do một create mới chưa phản ánh trong source snapshot boundary.
- Chỉ kết luận nếu cùng boundary và target catch-up đủ.

### 31.3. Stable hash

Không dùng hash random của process runtime nếu mỗi lần khởi động đổi kết quả. Phải có canonical key encoding, hash algorithm và bucket count cố định theo reconciliation policy version.

### 31.4. Migration bucket count

Nếu đổi 256→512 buckets:
- So source 512 với target 256 sẽ tạo mismatch giả.
- Cần versioned partitioning and recompute.

## 32. Java 21: một mô hình quyết định repair

Giả sử đã đọc **hai state tại boundary tương thích**.

~~~~java
public record ReconcileRow<K>(
        K key,
        long version,
        boolean deleted,
        String canonicalDigest
) {}

public enum DiffKind {
    MATCH,
    MISSING_TARGET,
    PHANTOM_TARGET,
    STALE_TARGET,
    TARGET_AHEAD_OR_INCOMPARABLE,
    PAYLOAD_MISMATCH
}

public final class Reconciler {
    private Reconciler() {}

    public static <K> DiffKind compare(
            ReconcileRow<K> source,
            ReconcileRow<K> target
    ) {
        if (source == null && target == null) {
            return DiffKind.MATCH;
        }
        if (source != null && target == null) {
            return DiffKind.MISSING_TARGET;
        }
        if (source == null) {
            return DiffKind.PHANTOM_TARGET;
        }
        if (target.version() < source.version()) {
            return DiffKind.STALE_TARGET;
        }
        if (target.version() > source.version()) {
            return DiffKind.TARGET_AHEAD_OR_INCOMPARABLE;
        }
        if (target.deleted() != source.deleted()) {
            return DiffKind.PAYLOAD_MISMATCH;
        }
        if (!java.util.Objects.equals(
                target.canonicalDigest(),
                source.canonicalDigest())) {
            return DiffKind.PAYLOAD_MISMATCH;
        }
        return DiffKind.MATCH;
    }
}
~~~~

### 32.1. Giới hạn của hàm

- Source null không tự chứng minh đã delete; phải biết scan scope/completeness.
- Target ahead có thể là timing artifact, không nhất thiết corruption.
- Version comparison chỉ hợp lệ khi source định nghĩa monotonic version cùng domain.
- Deleted records có thể cần tombstone.
- Source/target digest phải cùng canonical projection.
- Đây là **diff classifier**, chưa làm repair.
- Không thay snapshot boundary hoặc transactional consistency.
- Không đưa read model credentials/tenant data vào raw logs.

### 32.2. Repair worker tách khỏi classifier

Một handler có thể quyết định:
- MATCH → không làm gì.
- MISSING_TARGET → upsert current source state có guard.
- STALE_TARGET → upsert newer source state.
- PHANTOM_TARGET → confirm authoritative absence rồi versioned delete.
- PAYLOAD_MISMATCH → recompute transform/reindex.
- TARGET_AHEAD_OR_INCOMPARABLE → reread/cross-check; không tự overwrite.

Không tự động xóa/ghi đè chỉ dựa vào một diff từ hai eventually consistent reads.

## 33. Schema evolution trong recovery

Một projection rebuild có thể đọc:
- Source schema v5.
- Historical events schema v1, v2, v3.
- Target index mapping v4.

Nếu chỉ replay events bằng decoder mới:
- Unknown field bị bỏ.
- Type conversion lỗi.
- Timestamp/amount precision thay đổi.
- Delete semantics không còn đúng.
- Old event type không có handler.

### 33.1. Schema version trong envelope

~~~~json
{
  "eventId": "evt-105",
  "schemaVersion": 2,
  "aggregateVersion": 19,
  "type": "BOOKING_CHANGED",
  "payload": {"amount": "12500.00"}
}
~~~~

Một migration có thể chuyển sang amountMinor long ở v3. Cần:
- Versioned decoder.
- Upcaster.
- Validation.
- Consistent canonical hash.
- Replay tests.
- Audit policy version.

### 33.2. Rebuilding current state khác historical replay

Nếu source đã schema v5, có thể build current-state projection trực tiếp theo transformer v5. Nhưng nếu cần event-time report v2, phải có historical schema semantics để giải thích events cũ.

### 33.3. Policy version

Ngay cả với schema không đổi, business transform có thể đổi:
- Status labels.
- Revenue recognition logic.
- User-visible search fields.

Một replay với policy mới có thể cố ý tạo kết quả khác trước đây. Reconciliation phải so theo **cùng policy version**, không coi mọi difference là event loss.

## 34. Multi-region, partition và failover

Một hệ ba vùng VN/EU/US:
- Mỗi vùng có local CDC.
- Replication bất đồng bộ.
- Failover có thể đổi source owner.
- Một event có thể được nhìn thấy ở nhiều vùng.

### 34.1. Đừng gộp token các vùng tùy tiện

MongoDB resume token ở một deployment không tự là token portable sang deployment khác. Kafka partition offset ở EU không chứng minh VN offset có vị trí tương đương.

Cần ghi:
- Source cluster/region identity.
- Partition/shard identity.
- Epoch/generation.
- Cursor/token semantics.
- Global business version nếu có authority.

### 34.2. Double delivery khi failover

Một event E có thể được relay từ vùng A và B. Consumer phải:
- Dedup eventId/operationId.
- Version guard per aggregate.
- Không nhân đôi aggregates.
- Tôn trọng owner/authority theo failover protocol.

### 34.3. Concurrent writes

Nếu hai vùng cùng update một record mà không có total order:
- Current-state projection cần conflict-resolution policy.
- Một numeric version cùng số không đủ.
- Reconciliation phải biết authoritative winner hoặc siblings semantics.
- Không tự chọn event nhận sau cùng.

### 34.4. Resharding

Khi shard split/merge:
- Cursor lifecycle đổi.
- Consumer assignment chuyển.
- Ordering domains thay đổi.
- Checkpoint mapping phải dùng provider-supported protocol.

Không suy mọi offset gap sau reshard là lost event; nhưng cũng không bỏ qua event ownership gaps khi API yêu cầu theo dõi parent/child shards.

## 35. Đưa dữ liệu về đúng sau mất một đoạn: một tình huống trọn vẹn

Giả sử:
- Source NoSQL lưu 10 triệu bookings.
- CDC source → broker → search index.
- Consumer ngừng 30 giờ.
- Retention stream chỉ còn phần gần đây, không chứa một số thay đổi đầu outage.
- Source vẫn nhận 5.000 writes/s.
- Search index đang thiếu creates, updates và deletes.
- Index vẫn phục vụ queries cho khách hàng.

### 35.1. Điều tra ban đầu

Xác minh:
- Last durable checkpoint C.
- Oldest available position hiện tại.
- Scope partitions mất history.
- Search index checkpoint/version.
- Có durable outbox ledger hoặc backup stream không.
- Data types và business impact.
- Có phép đánh dấu degraded freshness không.

### 35.2. Không seek latest

Nếu seek latest rồi resume:
- Future updates vẫn được apply.
- Nhưng entities chỉ thay đổi trong đoạn mất vẫn lệch vĩnh viễn.
- Một deleted booking có thể tiếp tục searchable.

Thay bằng một recovery plan.

### 35.3. Bảo vệ production

- Chặn search-based confirmation của booking.
- Nêu degraded freshness cho UI nếu cần.
- Duy trì authoritative booking writes tại source.
- Giới hạn recovery read/write budgets.
- Bảo vệ source p99 và customer-facing workload.

### 35.4. Dựng staging projection

- Tạo search index mới theo mapping version đã xác nhận.
- Thiết lập change capture boundary đủ an toàn.
- Scan source vào staging với pagination/checkpoint.
- Áp versioned CDC tail.
- Đảm bảo deletes và creates sau scan đã được bao phủ.

### 35.5. Kiểm chứng

- So key membership/source counts theo tenant/range tại một boundary hợp lệ.
- Compare sourceVersion và canonical digest.
- Kiểm tra phantom records.
- Kiểm tra search visibility.
- Xác minh per-partition CDC catch-up.
- Test queries nghiệp vụ.
- Kiểm tra tenant authorization.

### 35.6. Cutover

- Canary queries tới staging.
- Switch alias/routing.
- Tiếp tục tail events không gián đoạn.
- Theo dõi p99, errors, drift, lag.
- Giữ old target tạm để rollback theo policy.

### 35.7. Post-incident

- Vì sao consumer ngừng?
- Vì sao retention budget không đủ?
- Alert time-to-expiry có thiếu?
- Có gaps nào không thể phục hồi lịch sử events?
- Có cập nhật runbook và diễn tập recovery?
- Có đo RTO/RPO thực tế không?

## 36. Retry, backoff và lỗi chưa xác định

Một CDC event apply vào target có thể timeout sau khi target đã commit. Nếu consumer coi timeout chắc chắn là failure rồi gửi lại:
- Có thể apply duplicate.
- Versioned upsert thường chịu được nếu đúng.
- Incremental aggregate cần eventId dedup.
- External notification cần idempotency riêng.

### 36.1. Phân loại

| Lỗi | Xử lý |
| --- | --- |
| Temporary network timeout | Bounded retry/backoff + idempotence |
| Target rate limit | Retry-After/admission |
| Source cursor expired | Không retry token mãi; chuyển recovery |
| Unknown schema | Quarantine, fix/upcast |
| Permission denied | Sửa auth/roles, không retry vô hạn |
| Permanent invalid record | DLQ + tracked reconciliation |
| Checkpoint conflict/rebalance | Fence old consumer/reassign |
| Snapshot boundary invalid | Restart capture/rebuild protocol |
| Target version newer than event | Dedup/version guard; không overwrite |
| Delete/absence ambiguous | Authoritative recheck trước delete |

### 36.2. Retries cần deadline

Nếu một event lỗi lâu:
- Không để một partition tắc mãi mà không alert.
- Không skip mù để checkpoint tiến.
- Có DLQ/quarantine theo contract.
- Vận hành phục hồi, owner và SLA rõ.
- Theo dõi event age và impact.

### 36.3. Không trộn retry với replay

**Retry:** xử lý lại một attempt/event thất bại.

**Replay:** xử lý lại một đoạn lịch sử từ checkpoint hoặc source ledger.

**Rebuild:** tạo projection lại từ source state + changes.

Ba việc có cost, correctness conditions và blast radius khác nhau.

## 37. Fault injection và kiểm chứng mất đoạn

| Kịch bản | Cách gây lỗi | Kết quả đúng kỳ vọng |
| --- | --- | --- |
| Worker crash sau target apply trước checkpoint | Kill giữa hai bước | Duplicate replay không nhân side effects |
| Worker crash sau checkpoint trước apply | Giả lập anti-pattern | Test phát hiện lost event/drift |
| Consumer offline trong retention | Pause ngắn | Resume và catch-up |
| Consumer offline vượt retention | Pause dài | Fail rõ, không seek latest mù |
| Invalid resume token | Cung cấp token đã hết hiệu lực | Recovery state chuyển đúng |
| Connector publish partial batch | Drop một broker ack | Không checkpoint qua missing durable event |
| Out-of-order events | v20 trước v19 | Target không đi lùi |
| Duplicate events | Phát cùng eventId 3 lần | Một logical effect |
| Lost delete | Bỏ delete v20 | Reconciliation phát hiện phantom |
| Snapshot scan while writes | Update/create/delete giữa pages | Không bỏ biến động |
| Rebuild without snapshot boundary | Start stream after scan | Test cho thấy race và từ chối phương án |
| Staging tail gap | Mất event khi rebuild | Không cutover |
| Old worker zombie | Resume worker cũ sau failover | Fencing/version guard bảo vệ target |
| Search bulk partial failure | Một item lỗi mapping | Batch không falsely complete |
| Schema v1/v3 mix | Historical event khác schema | Upcast/quarantine đúng |
| Source count same but keys differ | Swap A/B | Digest/key comparison phát hiện |
| Hard delete + stale target | Source absence, target exists | Phantom dọn theo boundary |
| Source current matches but audit missing | Mất intermediate events | Không tuyên bố historical recovery đầy đủ |
| Region failover | Đổi stream source owner | Token/epoch handling đúng |
| Consumer no net catch-up | Produce >= process rate | Alert, capacity action |
| Connector backlog near expiry | Retention margin nhỏ | Cảnh báo trước gap |
| Data privacy erase | Rebuild từ backup cũ | Không hồi sinh PII trái policy |

### 37.1. Bài test nên ghi gì?

- Source events/commit boundary.
- Durable checkpoints trước và sau.
- Oldest retained position.
- Partition/shard/epoch.
- Target versions và row hashes.
- Event apply/audit log.
- Recovery decisions.
- Missing/phantom keys.
- Search visibility.
- End-to-end freshness.
- Invariant validation.
- Time-to-recover.

### 37.2. Không chỉ kiểm tra consumer “RUNNING”

Một test pass cần chứng minh:
- No missing required state.
- Deletes reflected.
- Target không bị stale overwrite.
- Không duplicate business effects.
- Per-partition progress hợp lệ.
- Reconciliation đạt boundary.
- API queries trả đúng dữ liệu/tenant.

## 38. Runbook khi mất một đoạn CDC

### Bước 1 — Dừng giả định “chỉ lag”

- Xem error của resume/subscription.
- Đối chiếu checkpoint và oldest available stream position.
- Kiểm tra connector offsets, broker retention, DLQ.
- Xác định các partitions/tenants/tables ảnh hưởng.

### Bước 2 — Giữ chứng cứ

- Lưu checkpoint token/metadata hiện có mà không sửa bằng tay.
- Lưu error category và timestamps.
- Ghi source/sink deployment versions.
- Không đăng raw payload PII/secret lên ticket công khai.
- Giữ logs/archives trong retention được phép.

### Bước 3 — Đánh giá tác động nghiệp vụ

- Search results thiếu/stale?
- Reports sai?
- Delete/privacy requests chưa phản ánh?
- Customer-facing booking API có dựa vào projection?
- Có event-derived audit/billing history mất không?
- Có cần degrade/block chức năng rủi ro cao?

### Bước 4 — Chọn replay hay rebuild

- Còn full history → replay từ checkpoint.
- Chỉ vài keys lệch, nguồn còn đầy đủ → targeted backfill.
- History mất rộng, cần current-state projection → staging snapshot + CDC tail.
- Event-time history mất và source chỉ có current state → đối soát external ledger và công bố giới hạn phục hồi.

### Bước 5 — Thiết lập boundary

- Đặt stream capture và snapshot frontier phù hợp provider.
- Chặn gaps mới trong giai đoạn rebuild.
- Fence old writers.
- Giới hạn read/write budgets.
- Ghi recoveryId và state.

### Bước 6 — Thực thi

- Backfill nguồn theo canonical transformation.
- Apply tail changes idempotently.
- Xử lý delete/tombstones.
- Theo dõi all partitions.
- Quarantine schema/target failures.
- Không checkpoint trước durable apply.

### Bước 7 — Verify

- Counts và membership.
- Versions và canonical digests.
- Phantom/delete checks.
- Aggregate invariants.
- Per-partition watermark.
- Search refresh visibility.
- Tenant permission isolation.
- Event-derived history coverage.

### Bước 8 — Cutover

- Canary.
- Controlled alias/routing switch.
- Active CDC tail continuation.
- Rollback route.
- Monitor p99, drift, lag và errors.

### Bước 9 — Kết thúc

- RecoveryId COMPLETE chỉ sau verify.
- Liệt kê những dữ liệu lịch sử không thể phục hồi nếu có.
- Làm postmortem.
- Tăng retention budget/alerting, sửa checkpoint/connector.
- Lập lịch diễn tập gap recovery.

## 39. Những hiểu nhầm thường gặp

1. **“Consumer lag nghĩa đã mất event.”** Lag có thể recover nếu retention còn.
2. **“Consumer ở latest nghĩa dữ liệu đúng.”** Có thể đã skip/miss event trước đó.
3. **“Offset nhảy số nghĩa mất event.”** Không đúng nếu semantics offset/filters khác.
4. **“Một global max offset đại diện mọi partitions.”** Mỗi partition có checkpoint riêng.
5. **“Resume token có thể tự tăng như số nguyên.”** Nhiều token opaque.
6. **“Cursor expired cứ retry tiếp sẽ tự được.”** History có thể đã bị xóa.
7. **“Seek latest là cách repair nhanh.”** Chỉ tiếp tục tương lai, không sửa phần đã bỏ.
8. **“Restart connector tự tạo events đã hết retention.”** Không.
9. **“Checkpoint trước apply giúp tránh duplicates.”** Có thể mất event.
10. **“Checkpoint sau apply bảo đảm exactly-once.”** Có thể duplicate, cần idempotence.
11. **“Broker transaction là external index transaction.”** Không tự đồng nhất.
12. **“DLQ có event là projection đã đúng.”** Cần reprocess/repair.
13. **“Full-state event v20 cần mọi event trước để cập nhật current-state projection.”** Có thể không, nếu full authoritative snapshot và semantics cho phép.
14. **“Delta event v20 có thể áp trực tiếp bỏ v17–v19.”** Không chắc.
15. **“Current-state snapshot tái dựng được audit toàn bộ.”** Không có historical transitions.
16. **“Một notification có thể replay như projection upsert.”** Có thể gửi trùng tới người dùng.
17. **“Rebuild current financial balance đồng nghĩa phục hồi ledger.”** Không.
18. **“Scan source xong mới subscribe stream là an toàn.”** Bỏ writes giữa scan.
19. **“Capture stream trước scan là đủ trong mọi provider.”** Vẫn cần snapshot/version/delete semantics.
20. **“Scan nhiều page tự là một snapshot H.”** Không nếu thiếu consistent read boundary.
21. **“Compare source và target ngay lập tức là đúng.”** Có timing/visibility lag.
22. **“Raw JSON hash khác nghĩa state sai.”** Canonicalization/fields có thể khác.
23. **“Row count bằng nhau nghĩa projection đúng.”** Có thể key A/B bị hoán đổi.
24. **“Projection version bằng nghĩa data đúng.”** Transformation bug vẫn có thể xảy ra.
25. **“Hash bằng nghĩa mọi business invariant đúng.”** Chỉ so phạm vi đã canonicalize.
26. **“Chỉ upsert mọi source rows sẽ sửa deletes.”** Phantom target rows vẫn còn.
27. **“DELETE khỏi target không cần tombstone.”** Stale event có thể resurrect.
28. **“Tombstone giữ mãi không có chi phí.”** Retention/privacy/space.
29. **“Retention đủ lúc bắt đầu recovery là luôn đủ tới cuối.”** Backlog có thể tăng quá nhanh.
30. **“Consumer throughput 25k, source 20k nghĩa xử lý backlog 25k/s.”** Net catch-up chỉ 5k/s theo mô hình.
31. **“Compacted topic giữ mọi historical transitions.”** Có thể chỉ giữ state theo key.
32. **“Kafka offset 800 ở partition A và 300 ở B thành global 800.”** Không.
33. **“MongoDB resume token portable và có thể chỉnh tay.”** Không.
34. **“Change Stream fullDocument lookup luôn là exact post-image tại event.”** Không tự suy khi concurrent updates.
35. **“DynamoDB Streams có thể làm permanent audit log không giới hạn.”** Có retention hữu hạn.
36. **“Redis Streams pending entries sẽ tồn tại dù stream được trim.”** Không được giả định payload luôn còn.
37. **“Schema replay luôn dùng decoder mới cho event cũ.”** Cần schema versions/upcasting.
38. **“Bulk HTTP success nghĩa mọi index item thành công.”** Có per-item failures.
39. **“Một alias switch tự đồng bộ consumer checkpoint.”** Cần cutover protocol.
40. **“Rebuild in-place luôn ít rủi ro hơn staging.”** Có thể tạo partial visibility.
41. **“Full scan không ảnh hưởng NoSQL production.”** Có IO/CPU/latency impact.
42. **“Read replica nào cũng đủ mới để reconcile.”** Consistency contract khác nhau.
43. **“Replaying old events có thể xác nhận booking lần nữa.”** Nguy hiểm business side effects.
44. **“Versioned upsert tự giải quyết multi-leader conflict.”** Cần version order/authority.
45. **“Recovery COMPLETE chỉ cần job chạy hết.”** Cần verify.
46. **“Một data correction luôn cần replay mọi event.”** State repair có thể targeted nếu semantics phù hợp.
47. **“Một mismatch chắc chắn là lost CDC event.”** Có thể index refresh/schema/lag.
48. **“Có đủ source snapshot nghĩa mọi GDPR erasure vẫn an toàn.”** Rebuild từ backup cũ có thể hồi sinh PII.
49. **“Không cần tập dượt mất đoạn vì hiếm gặp.”** Retention và outages khiến recovery rất cần chuẩn bị.
50. **“Đo một metric consumer lag đủ.”** Cần end-to-end freshness và reconciliation.

## 40. Bài tập: khôi phục CDC cho nền tảng đặt chỗ ba vùng

Một hệ thống có:
- Java 21 services.
- NoSQL source lưu Bookings.
- CDC relay tới một broker theo partitions.
- Search index, booking count và analytics là projections.
- 5.000 source writes/s.
- Consumer xử lý tối đa 8.000 events/s khi không lỗi.
- Trong outage, consumer dừng 6 giờ.
- Stream có retention hữu hạn và một số partitions có retention window ngắn hơn outage.
- Một số events delete và price updates nằm trong đoạn bị mất.
- Một người dùng có quyền được thu hồi trong outage.
- Search vẫn phục vụ queries trong degraded mode.
- Có thể tạo staging index mới, nhưng current-state snapshot scan kéo dài 2 giờ.

### Phần A — Phân biệt lag và gap

1. Khi nào 6 giờ outage chỉ tạo lag?
2. Khi nào checkpoint không còn hợp lệ?
3. Vì sao offset nhảy không tự chứng minh missing events?
4. Cần kiểm tra earliest retained position ở phạm vi nào?
5. Vì sao không seek latest để hoàn tất incident?

### Phần B — Tính net catch-up

Giả sử:
- Source 5.000 events/s.
- Consumer sau hồi phục 8.000 events/s.
- Backlog 18 triệu events.

Tính:
- Net catch-up rate.
- Thời gian tối thiểu lý tưởng để bắt kịp nếu cả hai tốc độ ổn định.
- Vì sao retention phải đủ dài tới khi catch-up kết thúc?

**Gợi ý:** Net rate 3.000 events/s; 18 triệu/3.000 = 6.000 s, khoảng 100 phút.

### Phần C — Checkpoint crash

Timeline:
- Đọc event E.
- Lưu checkpoint sau E.
- Crash trước target update.

1. Điều gì sai?
2. Nếu đảo thứ tự apply rồi checkpoint, có rủi ro gì?
3. Cần idempotency/transaction guard thế nào?
4. Khi consumer rebalance, làm sao fence owner cũ?

### Phần D — Snapshot + CDC boundary

Một scan từ 09:00 đến 11:00:
- Booking B updated lúc 09:30.
- Source scanner đã đọc B lúc 09:10.
- Consumer chỉ subscribe CDC từ 11:01.

1. Event nào bị mất?
2. Vì sao stream-before-scan cần overlap/version guard?
3. Một consistent snapshot H sẽ giải quyết ra sao?
4. Nếu provider không hỗ trợ H, cần protocol nào?
5. Nếu retention hết trong lúc staging rebuild thì làm gì?

### Phần E — Missing delete

Source đã delete B-901:
- Search vẫn còn B-901.

1. Vì sao upsert source rows không xóa phantom?
2. Membership scan hoặc tombstone ledger giúp gì?
3. Versioned delete ngăn old update resurrect thế nào?
4. Privacy erasure có rủi ro gì khi rebuild từ backup cũ?

### Phần F — Reconciliation

Cho:

~~~~text
Source:
  A v10 status=CONFIRMED
  B v20 status=CANCELLED
  C deleted v7
  D v5 status=CONFIRMED

Target:
  A v10 status=CONFIRMED
  B v18 status=CONFIRMED
  C v6 status=CONFIRMED
  E v2 status=PENDING
~~~~

1. Phân loại A, B, C, D, E.
2. Rows nào cần upsert?
3. Rows nào cần delete/tombstone?
4. Khi source/target reads không cùng boundary, có thể xuất hiện false diff nào?
5. Có thể dùng counts thôi không?

### Phần G — Hash theo bucket

1. Chia keyspace thành 256 stable buckets.
2. Tính count/digest cùng canonical transform version.
3. Khi bucket 17 lệch, làm sao drill down?
4. Vì sao phải quan tâm snapshot boundary?
5. Canonicalization xử lý decimals/time zones/null như thế nào?

### Phần H — Engine-specific recovery

Đối chiếu:
- MongoDB Change Streams: resume token/oplog window.
- DynamoDB Streams: shard sequence/retention.
- Kafka: partition offsets/compaction/tombstones.
- Redis Streams: consumer groups/PEL/trimming.
- Debezium: connector offset/snapshot/schema history.
- Search sink: bulk per-item errors/refresh/aliases.

Nêu với mỗi loại:
1. Checkpoint nào hợp lệ?
2. Làm sao biết history không còn?
3. Replay semantics là gì?
4. Khi nào cần snapshot/backfill?
5. How to protect target from stale/duplicate writes?

### Phần I — Event-derived vs state-derived projections

Giả sử cần:
- Tổng booking hiện đang CONFIRMED.
- Số lần booking được chuyển CONFIRMED→CANCELLED theo giờ.
- Financial adjustment ledger.
- Search result.

Những mục nào có thể tái dựng từ current-state source? Những mục nào cần historical events/ledger?

### Phần J — Multi-region

1. Vì sao token của VN không dùng cho EU tùy tiện?
2. Khi region failover, cần source identity/epoch?
3. Nếu same event đến từ hai vùng, dedup gì?
4. Nếu hai regions tạo concurrent version cùng số, version guard có đủ không?
5. Resharding ảnh hưởng checkpoint ra sao?

### Phần K — Recovery orchestration

Thiết kế state machine:
- DETECTED.
- SCOPED.
- FENCED.
- REPLAYING hoặc SNAPSHOTTING.
- CATCHING_UP.
- VERIFYING.
- READY_FOR_CUTOVER.
- CUTOVER.
- MONITORING.
- COMPLETE.

Mỗi trạng thái cần:
- Inputs.
- Persisted state/checkpoint.
- Failure handling.
- Owner/operator.
- Metrics.
- Điều kiện chuyển tiếp.

### Phần L — Fault injection

Thiết kế ít nhất 12 tests:
1. Worker crash trước target write nhưng sau checkpoint.
2. Crash sau target write trước checkpoint.
3. Retention expired.
4. Invalid resume token.
5. Broker publish partial batch.
6. Poison schema event.
7. Out-of-order v20 rồi v19.
8. Duplicate delta event.
9. Missing delete.
10. Snapshot scan while create/update/delete.
11. Search bulk partial failure.
12. Zombie worker sau rebalance.
13. Region failover.
14. Tombstone GC sớm.
15. Rebuild replays notification.
16. Index alias switch khi tail vẫn đang chạy.

Ghi expected source/target state, checkpoint, drift, SLO và pass/fail evidence.

### Phần M — Phản biện thiết kế

Một đồng nghiệp nói:

> “Nếu CDC bị mất ba giờ, đặt consumer offset về latest để tiếp tục, rồi chạy full source scan và upsert tất cả records vào search hiện tại. Không cần delete vì bản không tồn tại sẽ không có event. Hash JSON raw là đủ; khi đếm records bằng nhau thì đánh dấu phục hồi. Nếu gặp historical event thì cho email/payment consumer xử lý lại để chắc chắn không thiếu.”

Phân tích các nguy cơ:
- Lost history.
- Snapshot/stream gap.
- Phantom deletes.
- Race với ongoing projector.
- Hash không canonical.
- Count false matches.
- Duplicate business side effects.
- Thiếu consistent boundary.
- Không có staging/cutover/rollback.
- Không đo retention/catch-up/recovery correctness.

### Hướng giải

Một kế hoạch đúng có thể:
- Dừng hành vi skip history.
- Phân phạm vi missing partitions và business impact.
- Replay nếu history còn; nếu không, dùng **consistent snapshot + CDC tail**.
- Dựng staging projection.
- Áp versioned upsert/delete, eventId dedup, sourceWatermark.
- Đối soát membership, versions, hashes và aggregates ở cùng boundary.
- Chỉ cutover khi checkpoints, visibility và correctness đã được xác nhận.
- Không replay email/payment như projection.
- Đo time-to-retention-expiry, drift, recovery RTO/RPO và aftercare.
- Công bố phần historical data không thể tái dựng nếu source chỉ giữ current state.

## 41. Checklist vận hành trước production

1. **Nguồn sự thật và các projections đã xác định rõ?**
2. **Mỗi stream/partition có checkpoint bền và owner epoch?**
3. **Checkpoint chỉ tiến sau khi required target effects durable?**
4. **Có idempotent apply/dedup theo eventId/version?**
5. **Có version guard chống out-of-order stale overwrite?**
6. **Delete/tombstones có được apply và giữ đúng retention?**
7. **Có đo earliest retained position vs checkpoint?**
8. **Có cảnh báo trước khi backlog vượt retention?**
9. **Có biết throughput cần để catch-up không?**
10. **Consumer restart có resume từ token provider hỗ trợ?**
11. **Không tự parse/tăng opaque resume token?**
12. **Có phân biệt invalid cursor, poison event và connection lag?**
13. **Có DLQ với owner/SLA reprocess?**
14. **Có quy trình replay lịch sử còn tồn tại?**
15. **Có recovery plan khi log history đã bị dọn?**
16. **Có snapshot+stream boundary được chứng minh đúng cho provider?**
17. **Có đảm bảo mọi creates/updates/deletes trong scan window được bao phủ?**
18. **Snapshot pagination/read consistency được xác định?**
19. **Có staging projection và controlled cutover khi rebuild lớn?**
20. **Có fencing old workers để tránh zombie writes?**
21. **Có per-partition watermark/catch-up criteria?**
22. **Có repair theo key/range khi phù hợp?**
23. **Có reconciliation counts, membership, versions, canonical digests?**
24. **Có cùng schema/transform policy version khi so?**
25. **Không kết luận từ counts hay raw JSON hash duy nhất?**
26. **Có xử lý phantom target records do missing deletes?**
27. **Có retention chính xác cho tombstone/replay horizon?**
28. **Có phân biệt current-state rebuild với historical event recovery?**
29. **Không replay external side effects vô tình?**
30. **Có nguồn ledger khác cho tài chính/audit nếu CDC mất lịch sử?**
31. **Có giới hạn source scan/backfill resource budgets?**
32. **Có target bulk per-item failure handling?**
33. **Có kiểm tra search visibility sau writes?**
34. **Có read/authorization/tenant correctness tests?**
35. **Có recoveryId, audit trail và rollback plan?**
36. **Có SLO drift, retention risk, projection lag và recovery RTO?**
37. **Có fault injection retention expiry, snapshot race, delete loss và rebalance?**
38. **Có kiểm tra multi-region source identity/epochs/shard lifecycle?**
39. **Có privacy erase/backup restoration controls để không hồi sinh PII?**
40. **Chỉ đánh dấu COMPLETE khi reconciliation tại boundary hợp lệ thành công?**

**Kết luận:** Trong kiến trúc NoSQL dùng **sự kiện và CDC**, consumer có thể vẫn hoạt động sau một outage nhưng **read model vẫn lệch nguồn** nếu một đoạn thay đổi đã bị bỏ qua hoặc hết retention. Cần phân biệt **lag có thể catch-up** với **history gap không thể replay**, lưu checkpoint đúng sau durable apply, xử lý duplicate/out-of-order bằng **eventId và sourceVersion**, đồng thời đối soát **sự tồn tại của key, deletes, phiên bản và nội dung canonical** tại một ranh giới so sánh hợp lệ. Khi lịch sử còn, replay có kiểm soát là đường ngắn nhất; khi mất lịch sử, cần **snapshot nguồn kết hợp CDC tail không có khoảng trống**, thường dựng một staging projection rồi verify/cutover. Không được dùng current snapshot để giả vờ phục hồi những **historical side effects/audit events** đã mất, và không được seek latest rồi tuyên bố healthy. Kiểm chứng bằng **retention-risk metrics, checkpoint lag, source–projection drift, delete/phantom detection, fault injection, recovery RTO và business invariants**, để trạng thái “đã phục hồi” là một kết luận có bằng chứng chứ không chỉ là một worker đang chạy.
