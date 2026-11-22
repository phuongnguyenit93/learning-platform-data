# Phát lại sự kiện để dựng lại dữ liệu dẫn xuất

## 1. Mục tiêu bài học

Trong hệ thống microservices, ngoài database chứa dữ liệu nghiệp vụ chuẩn, nhiều thành phần còn giữ **dữ liệu dẫn xuất (derived data)** như search index, materialized view, bảng reporting, cache, read model của CQRS và projection trạng thái workflow. Các bản sao này phục vụ truy vấn nhanh hoặc một nhu cầu đọc cụ thể, nhưng không nhất thiết là nguồn sự thật.

Ví dụ: Order Service sở hữu đơn hàng; nó phát `OrderPlaced`, `OrderPaid`, `OrderCancelled`. Search Service cập nhật index, Reporting Service tính tổng doanh thu, Customer Portal dựng màn hình lịch sử đơn và Analytics Pipeline duy trì dữ liệu phân tích. Khi index bị mất hoặc code reporting có bug, có thể **phát lại sự kiện (event replay)** để dựng một projection mới mà không cần tạo lại đơn hàng hay gọi nhà cung cấp thanh toán.

Bài học này thuộc chủ đề **Khôi phục thảm họa**. Mục tiêu là hiểu không chỉ “đọc Kafka từ đầu” mà toàn bộ thiết kế an toàn:

1. Xác định nguồn sự thật, lịch sử sự kiện và dữ liệu có thể rebuild.
2. Đánh giá retention, snapshots, event schemas và tính đầy đủ của nguồn.
3. Xây projector có tính xác định, idempotent và chịu được event trùng/sai thứ tự.
4. Cô lập replay khỏi side effects như charge tiền, gửi email hoặc xuất kho.
5. Chạy replay theo batch, checkpoint, throttle và catch-up với luồng live.
6. Dựng shadow projection, xác minh rồi cutover/rollback.
7. Đo RPO, RTO, lag, throughput, mismatches và tính đúng dữ liệu.
8. Tạo runbook và diễn tập khôi phục trước khi xảy ra sự cố.

Ví dụ dùng Java, SQL và Kafka; ý tưởng tương tự áp dụng với CDC, event store hoặc broker khác. Các địa chỉ, số liệu và version bên dưới chỉ minh họa.

## 2. Phân biệt dữ liệu gốc và dữ liệu dẫn xuất

| Loại | Ví dụ | Nguồn thẩm quyền | Cách khôi phục hợp lý |
|---|---|---|---|
| Domain state | Đơn, thanh toán, số dư, tồn kho | DB/event store thuộc domain owner | Backup/restore, ledger, reconciliation |
| Event history | `OrderPlaced`, `PaymentCaptured` | Durable event log/archive nếu đủ lịch sử | Restore event history/verify integrity |
| Search index | Truy vấn sản phẩm/đơn | Projection từ domain data | Snapshot, full replay, snapshot + delta |
| CQRS read model | Màn hình trạng thái checkout | Domain events/state machine | Rebuild bằng projector |
| Analytics mart | Doanh thu theo giờ/vùng | Events + corrections/ledger | Recompute có version và đối soát |
| Cache | Summary, hot object | DB/read model có thẩm quyền | Warm lại; không phải lúc nào cần replay |
| Workflow projection | Trạng thái saga hiện tại | Orchestrator hoặc event history hợp lệ | Rebuild có quy tắc pending/compensation |
| External side effect | PSP charge, email đã gửi, đơn đã giao | Nhà cung cấp/ledger và domain DB | **Không tạo lại bằng replay command** |
| Manual corrections | Điều chỉnh thủ công, refund ngoại lệ | Nguồn đã audit | Chỉ rebuild nếu correction được lưu |

Một bảng có vẻ là “derived” nhưng chứa sửa đổi thủ công chưa được ghi vào nguồn có thể **không thể dựng lại hoàn toàn**. Để bảo đảm rebuildable, mọi correction có ý nghĩa phải có lineage: ai sửa, sửa gì, tại sao và dữ liệu nguồn tương ứng.

**Nguyên tắc cốt lõi:** event replay nhằm tái tạo *cách nhìn về một sự thật đã xảy ra*, không nhằm *kích hoạt lại hành động kinh doanh*.

## 3. Event sourcing, domain events và CDC không giống nhau

### 3.1. Event sourcing

Trong event sourcing, trạng thái của một aggregate được tính bằng cách áp sự kiện lịch sử:

~~~text
OrderCreated
  -> ItemAdded
  -> PaymentAuthorized
  -> InventoryReserved
  -> OrderCompleted
~~~

Nếu lịch sử đầy đủ và reducer tương thích, có thể rebuild aggregate state hoặc một projection mới. Snapshot thường giảm thời gian tính toán.

### 3.2. Domain events + transactional outbox

Nhiều service dùng DB làm nguồn sự thật rồi ghi outbox event trong cùng transaction. Publisher gửi sự kiện qua broker; consumer tạo search index, báo cáo hoặc read model.

Trong mô hình này, **outbox và broker không mặc định là event store vĩnh viễn**. Outbox có thể bị xóa sau khi publish, Kafka topic có thể chỉ giữ bảy ngày. Muốn rebuild index hai năm, cần full archive hoặc snapshot + delta từ mốc đủ gần.

### 3.3. Change Data Capture (CDC)

CDC đọc transaction log của DB và xuất các thay đổi bản ghi. CDC giúp đồng bộ latest state và dựng index, nhưng một record `UPDATE order SET status=PAID` không nhất thiết có ngữ nghĩa đầy đủ bằng `PaymentCaptured` hoặc `OrderPaymentSettled`.

| Khía cạnh | Event sourcing | Domain event + outbox | CDC |
|---|---|---|---|
| Nguồn sự thật chính | Event history | Domain DB | Domain DB |
| Event mang ngữ nghĩa nghiệp vụ | Thường có | Thường có | Không nhất thiết |
| Full replay từ ngày đầu | Nếu lịch sử giữ đầy đủ | Phụ thuộc archive/retention | Thường cần snapshot + transaction log |
| Schema evolution | Event version/upcaster | Event contract/upcaster | DB schema mapping |
| Dùng dựng projection | Có | Có | Có |
| Rủi ro chính | History/schema/snapshot | Gap do retention | LSN/snapshot/schema changes |

Không được kết luận “Kafka còn hoạt động nên có thể replay từ đầu”. Phải kiểm những đoạn lịch sử cụ thể còn hay không.

## 4. Khi nào nên phát lại sự kiện?

Các trường hợp có giá trị:

- Search index bị xóa, hỏng mapping hoặc mất một region.
- Reporting Service đã cộng trùng doanh thu do event redelivery.
- Read model cần thêm trường mới có trong event history.
- Migration từ search/index engine cũ sang engine mới.
- Consumer lỗi làm projection thiếu sự kiện trong một khoảng thời gian.
- Phục hồi một bảng tổng hợp từ snapshot sau thảm họa.
- Dựng lại CQRS projection theo reducer version mới.
- Kiểm tra một bản projection có thể tái tạo đúng bằng cách replay.
- Chuyển sang region dự phòng và catch up dữ liệu dẫn xuất.
- Backfill một khoảng lịch sử bị ảnh hưởng bởi bug.
- Khôi phục cache/materialized view sau data corruption.

Không phải mọi tình huống cần full replay. Nếu thiếu vài trăm events mà source log vẫn còn, có thể catch up từ checkpoint. Nếu lỗi chỉ ảnh hưởng một region hoặc tenant, targeted rebuild có thể phù hợp. Nếu lịch sử không đủ, khôi phục từ domain DB snapshot hoặc data warehouse có thể là lựa chọn duy nhất.

## 5. Kiến trúc tham chiếu

~~~mermaid
flowchart LR
    D[(Domain Database)] --> O[(Transactional Outbox)]
    O --> B[(Event Log / Archive)]
    B --> L[Live Consumer]
    L --> P[(Current Projection)]
    B --> R[Isolated Replay Consumer]
    S[(Verified Snapshot)] --> R
    R --> N[(Shadow Projection)]
    N --> V[Validate and Reconcile]
    V --> C[Controlled Cutover]
    C --> A[Read API / Search Alias]
    P --> A
~~~

Kiến trúc có hai đường:

- **Live path** tiếp tục phục vụ production nếu bản dữ liệu hiện tại còn an toàn.
- **Replay path** dùng một consumer group và target riêng, xử lý lịch sử, kiểm tra kết quả rồi mới chuyển người đọc.

Nếu current projection đã corrupt, có thể phải degrade capability tạm thời hoặc restore backup trước khi replay. Không được cho người dùng đọc dữ liệu sai chỉ để giữ màu xanh của dashboard.

### 5.1. Ranh giới phục hồi

Đường replay cần quyền **đọc** event history và **ghi** shadow read model. Nó không cần quyền thu tiền, xuất kho, gửi email hay publish business commands. Đó là một bảo vệ quan trọng hơn việc chỉ đặt biến `replayMode=true`.

## 6. Các điều kiện tiên quyết để rebuild đáng tin

Trước khi lên kế hoạch RTO bằng replay, kiểm:

1. **History completeness:** có đủ dữ liệu từ sự kiện đầu hoặc một snapshot tương thích.
2. **Durability:** event log, archive và snapshot được bảo vệ khỏi lỗi cùng failure domain.
3. **Identity:** event ID, aggregate ID và version có thể nhận diện duplicates.
4. **Ordering:** có sequence, partitioning hoặc quy tắc nhân quả đủ cho reducer.
5. **Schema:** đọc được mọi event version trong phạm vi replay.
6. **Determinism:** cùng input cho cùng projection result theo định nghĩa.
7. **Idempotency:** retry/redelivery không làm cộng trùng.
8. **Side-effect isolation:** projector không phát command hay gọi external APIs.
9. **Checkpoints:** có thể restart batch từ mốc durable.
10. **Consistency:** snapshot và offsets có ranh giới rõ.
11. **Capacity:** đọc/ghi đủ nhanh mà không làm ảnh hưởng hệ thống live.
12. **Validation:** có nguồn đối soát và tiêu chí cutover.
13. **Security/privacy:** không hồi sinh thông tin đã xóa hợp lệ.

Thiếu một điều kiện có thể khiến full replay không còn là phương án khôi phục khả thi. Cần ghi rõ limitation thay vì mặc định “event-driven thì rebuild được”.

## 7. Thiết kế event envelope

Một event minh họa:

~~~json
{
  "event_id": "evt-93a7",
  "event_type": "OrderStatusChanged",
  "event_version": 3,
  "aggregate_type": "Order",
  "aggregate_id": "ord-10492",
  "aggregate_sequence": 17,
  "workflow_id": "checkout-10492",
  "producer": "order-service",
  "source_region": "apac",
  "occurred_at": "2026-11-12T02:24:12Z",
  "recorded_at": "2026-11-12T02:24:13Z",
  "correlation_id": "checkout-10492",
  "causation_id": "evt-93a6",
  "payload": {
    "status": "INVENTORY_RESERVED",
    "currency": "VND"
  }
}
~~~

Các ID và timestamp chỉ để minh họa; payload production cần chính sách bảo vệ PII.

| Trường | Vai trò |
|---|---|
| `event_id` | De-dup cùng event khi redelivery |
| `event_type` | Xác định loại state transition |
| `event_version` | Upcast payload cũ |
| `aggregate_id` | Gom các event thuộc cùng thực thể |
| `aggregate_sequence` | Phát hiện gap hoặc event cũ |
| `workflow_id` | Nối các service cùng một hành trình |
| `occurred_at` | Mốc thời gian nghiệp vụ |
| `recorded_at` | Mốc event được lưu |
| `producer` / `source_region` | Provenance và DR scope |
| `correlation_id` / `causation_id` | Liên kết chuỗi nhân quả |

Không có yêu cầu tất cả event phải có sequence toàn cục. Sequence **theo aggregate** thường đủ cho projection của một entity. Projections kết hợp nhiều domain cần consistency rule riêng.

## 8. Retention và archive: lịch sử còn đến đâu?

Một topic có `retention.ms` hoặc giới hạn dung lượng có thể xóa messages cũ. Log compaction giữ latest value theo key nhưng thường không giữ mọi lần chuyển trạng thái. Không thể tái tạo số lần payment retry chỉ từ bản trạng thái cuối cùng.

| Nguồn | Dựng được gì? | Hạn chế |
|---|---|---|
| Full immutable event log | Replay transitions từ đầu | Dung lượng, privacy retention, integrity |
| Snapshot + event delta | Current state sau mốc snapshot | Snapshot cần cutoff và schema đúng |
| Compacted topic | Latest state của key | Mất transition history |
| Domain DB snapshot | Latest domain view | Không nhất thiết có lịch sử giao dịch |
| CDC snapshot + log | Backfill latest state rồi cập nhật | Phải map LSN/schema đúng |
| Data warehouse/archive | Analytics lịch sử, một số backfills | Trễ, thiếu kỹ thuật hoặc correction |
| Projection backup | Restore nhanh | Có thể chứa bug, corruption hoặc sai version |

### 8.1. Retention không chỉ là kỹ thuật

Nếu event chứa PII, yêu cầu xóa/retention theo chính sách có thể cấm giữ nguyên raw events mãi mãi. Cần mô hình lưu thông tin nghiệp vụ cần thiết nhưng không làm tái xuất thông tin cá nhân đã được xóa hợp lệ. Replay phải áp tombstones, deletion/correction events hoặc dùng dữ liệu đã được biến đổi đúng.

### 8.2. Archive phải có thể restore

Một object storage chứa các file archive nhưng chưa từng thử giải nén, kiểm checksum, map offsets và schema versions không phải bằng chứng đủ cho DR. Cần diễn tập restore, kiểm coverage theo date/topic/partition và khả năng đọc thực tế trong time budget.

## 9. Chọn full replay, snapshot + delta hay backfill

### 9.1. Full replay

~~~text
Empty target
  + event 1
  + event 2
  + ...
  + event N
  = rebuilt projection
~~~

Ưu: tái chạy toàn bộ reducer và đổi logic tính toán. Nhược: chi phí/time lớn, phụ thuộc lịch sử và upcasters, khó đáp ứng RTO khi data volume lớn.

### 9.2. Snapshot + delta

~~~text
Verified snapshot at position S
  + all events strictly after S
  = current projection
~~~

Ưu: giảm thời gian. Nhược: snapshot phải nhất quán, có metadata cutoff, không chứa bug và tương thích với projector version.

### 9.3. Domain snapshot + CDC

Nếu không có full event history, dùng snapshot domain DB tại logical point/LSN rồi áp change log sau đó. Thích hợp cho latest-state index; không đủ để tái tính mọi KPI lịch sử nếu chỉ có trạng thái hiện tại.

### 9.4. Selective rebuild

Lọc theo aggregate IDs, khoảng thời gian hoặc loại projection. Phải biết các dependency ngoài phạm vi: Customer Lifetime Value có thể cần tất cả giao dịch của khách, không chỉ phần tháng vừa rồi. Không tự ý lọc event mà không chứng minh state sau cùng đúng.

### 9.5. Restore projection backup

Phục hồi bản backup gần nhất, áp event delta, rồi validate. Nhanh nhưng backup của projection lỗi có thể tái tạo chính lỗi cũ. Cần đánh giá version và thời điểm bug bắt đầu.

## 10. Deterministic reducer: cùng input, cùng kết quả

Mục tiêu projector:

\[
S_{n+1}=f(S_n,E_{n+1})
\]

Trong đó `S_n` là trạng thái trước event, `E_{n+1}` là event canonical. Một reducer tốt không phụ thuộc vào:

- `Instant.now()` để tính ngày nghiệp vụ quá khứ.
- Random values hoặc generated IDs không được cố định.
- Giá/tỷ giá hiện hành thay cho giá/tỷ giá tại thời điểm sự kiện.
- External API response hôm nay để suy ra quyết định lịch sử.
- Default timezone/locale của host đang chạy.
- Thứ tự nhận sự kiện ngẫu nhiên từ nhiều partitions.
- Event schema “được đoán” khi thiếu trường.
- Logic rounding thay đổi không có version.

Ví dụ khi dựng lại tổng tiền năm trước, tỷ giá hoặc chính sách thuế phải đến từ event hoặc historical reference có effective date, không thể tra số hiện tại rồi coi là đúng.

### 10.1. Event là sự thật hay command?

`PaymentCaptured` nói một sự kiện đã xảy ra; có thể dùng để cập nhật bảng thống kê. `CapturePayment` là yêu cầu thực hiện một hành động; nếu “replay” lệnh đó, hệ thống có thể thu tiền lần thứ hai. Phân biệt command với event ngay ở contract và topic layout.

## 11. Cấm replay tạo business side effects

Một thiết kế an toàn:

~~~text
Live path:
  command validation
   -> domain transaction
   -> external side effect when authorized
   -> outbox event
   -> normal consumers

Replay path:
  historical event
   -> schema normalization
   -> pure reducer
   -> shadow projection
   -> durable checkpoint
   -> NO external command
~~~

Các biện pháp nên kết hợp:

- Replay worker dùng identity riêng, quyền đọc source và ghi target hạn chế.
- Không cấp PSP/Email/Shipping credentials cho replay job.
- Chặn egress không cần thiết.
- Không subscribe replay worker vào command topics.
- Không tái dùng một consumer handler vừa cập nhật projection vừa gửi email.
- Test kiểm không gọi outbound HTTP SDK hoặc message producer.
- Phê duyệt run ID, target và source positions trước khi chạy.
- Log replay operations nhưng không log raw sensitive payload.
- Theo dõi các outbound calls trái phép như tín hiệu vi phạm.

Chỉ đặt một flag `isReplay` trong handler rồi tin mọi nhánh đều kiểm flag là chưa đủ khi rủi ro tài chính lớn.

## 12. Duplicate events, idempotency và business identity

At-least-once delivery có thể làm event xuất hiện nhiều lần. Một job replay bản chất đọc lại cả những event đã từng được xử lý bởi live consumer. Với counter/tổng tiền, duplicate event khiến sai số rất lớn nếu chỉ tăng biến đếm.

Các lớp bảo vệ:

1. Unique `event_id` trong bảng processed-events/inbox.
2. `aggregate_id + aggregate_sequence` để không áp version cũ.
3. Unique business key cho logical payment hoặc reservation.
4. Upsert dựa vào entity ID ổn định.
5. Transaction kết hợp projection write và processed-event record.
6. Checkpoint advance sau khi dữ liệu đã commit.
7. Reconciliation độc lập để bắt bug mà de-dup bỏ sót.

### 12.1. Event ID không bảo vệ mọi duplicate

Hai events `E1` và `E2` có ID khác nhau nhưng đều báo cùng PSP transaction. De-dup theo event ID vẫn đếm hai lần nếu producer lỗi. Với tiền, cần đối soát theo payment intent/PSP transaction ID và ledger. Không suy từ “exactly-once broker” rằng external side effects cũng đúng một lần.

## 13. Thứ tự, sequence và event gaps

Ví dụ:

~~~text
Order seq=1 Created
Order seq=2 PaymentAuthorized
Order seq=3 InventoryReserved
Order seq=4 Cancelled
~~~

Nếu seq=4 xử lý trước seq=3, một projector ngây thơ có thể cập nhật `CANCELLED` rồi bị seq=3 ghi đè `INVENTORY_RESERVED`. Cần:

- Partition theo aggregate key nếu broker hỗ trợ.
- Version/sequence checks.
- Phát hiện gap (đợi seq=3 trước khi áp seq=4 hoặc xử lý theo chính sách).
- State-machine guard: không cho transition trái phép.
- Quarantine những record không thể xử lý an toàn.
- Reconciliation khi source thật và projection sai lệch.

### 13.1. Kafka ordering

Kafka có ordering trong phạm vi partition, **không có ordering toàn cục giữa nhiều partitions**. Nếu các event cùng Order đi nhiều topic hoặc dùng partition keys khác nhau, projector phải hiểu dependency/causation thay vì sort toàn bộ bằng timestamp.

### 13.2. Báo cáo kết hợp nhiều services

Order, Payment, Refund có thể không có sequence chung. Báo cáo doanh thu cần event-time window, business transaction identity, late-event policy, watermark hoặc ledger reconciliation. Không coi `occurred_at` là đồng hồ tuyến tính toàn cầu vì clock skew và network delay.

## 14. Schema evolution và upcasting

Các phiên bản sự kiện có thể khác nhau:

- v1: `amount` tính bằng cents nhưng không ghi currency.
- v2: thêm `currency`.
- v3: đổi thành `amountMinorUnits`, thêm tax breakdown.

Để replay lịch sử, xử lý mỗi version rõ ràng:

~~~text
Event v1 / v2 / v3
        |
        v
Deserializer + Version Mapping
        |
        v
Upcaster to CanonicalEvent
        |
        v
Pure Reducer
        |
        v
Versioned Projection
~~~

Java pseudocode:

~~~java
CanonicalPaymentCaptured normalize(EventEnvelope event) {
    return switch (event.version()) {
        case 1 -> upcastV1(event.payload());
        case 2 -> upcastV2(event.payload());
        case 3 -> decodeV3(event.payload());
        default -> throw new UnsupportedEventVersionException(event.version());
    };
}
~~~

Nếu v1 không có currency và không có nguồn lịch sử đáng tin, đừng gán “VND” chỉ vì hệ thống hiện chỉ dùng VND. Có thể cần phục hồi historical reference hoặc đánh dấu thống kê không thể rebuild chính xác.

### 14.1. Không sửa event gốc tùy tiện

Sửa trực tiếp historical event có thể phá signature, audit và snapshot checksum. Ưu tiên immutable events + upcaster + correction event. Nếu bắt buộc migrate event store, phải có backup, kế hoạch consistency, version, provenance và test.

### 14.2. Version projector

Ghi commit/image digest của transformer, schema version của target, supported event versions, reference data version, rounding/timezone semantics và source positions. Một projector mới có thể đổi phép tính theo chủ đích; validation phải phân biệt expected semantic change với corruption.

## 15. Snapshot và cutoff nhất quán

Một snapshot chỉ hữu ích nếu biết **nó đã áp dụng đến sự kiện nào**.

Ví dụ snapshot aggregate Order A tại seq=125. Khi resume phải áp các event seq>125. Nếu áp seq=125 lần nữa với phép cộng không idempotent sẽ tăng sai. Nếu bắt đầu seq=127 sẽ thiếu seq=126.

### 15.1. Multi-partition snapshot

Với Kafka, cutoff thường là **vector offsets**:

~~~json
{
  "snapshot_id": "order-view-20261112",
  "projector_version": "2.3.1",
  "schema_version": 5,
  "topic": "order-domain-events",
  "partition_offsets": {
    "0": 987654,
    "1": 876540,
    "2": 765432
  },
  "checksum": "example-checksum"
}
~~~

Các offsets chỉ minh họa. Cần ghi chúng là **last applied** hay **next to consume**. Sự mơ hồ off-by-one có thể gây mất hoặc trùng event. Snapshot nhiều partitions không tự đại diện cho một điểm nhất quán toàn cục; với aggregate liên kết chéo cần thiết kế consistency model phù hợp.

### 15.2. Snapshot validation

Kiểm:

- Snapshot file/tables có đọc được và checksum đúng không.
- Có đầy đủ data/schemas mà projector mới cần không.
- Source log sau cutoff còn liên tục không.
- Snapshot có thuộc phiên bản code từng gây bug không.
- Privacy tombstones/corrections đã áp chưa.
- Có thể restore trong thời gian dự kiến không.

## 16. Replay khi luồng live vẫn chạy

Trong lúc replay, nguồn tiếp tục có event mới. “Đọc từ đầu tới hiện tại” không có mốc kết thúc cố định nếu người dùng vẫn đặt hàng.

Quy trình:

~~~text
T0 Create isolated shadow target
T1 Capture replay start position and high watermark H
T2 Replay historical events up to H
T3 Continue with live delta after H
T4 Validate target at declared positions
T5 Wait until lag/consistency conditions are met
T6 Cut over readers/writers in controlled sequence
T7 Continue updates from correct positions
T8 Observe, retain rollback option
~~~

Có thể chuyển sang delta/catch-up ngay sau lịch sử, không cần dừng nguồn live. Tuy nhiên, phải bảo đảm không có gap giữa mốc snapshot, event history và delta feed.

### 16.1. Tính thời gian bắt kịp

Với backlog `B` events, projector xử lý `μ` events/giây, nguồn tạo `λ` events/giây, nếu `μ>λ`:

\[
T_{\mathrm{drain}}\approx\frac{B}{\mu-\lambda}
\]

Ví dụ B=6 triệu, replay throughput 5.000/s và live rate 2.000/s:

\[
T_{\mathrm{drain}}=6{,}000{,}000/3{,}000=2{,}000\text{ giây}
\]

Xấp xỉ 33 phút 20 giây, chưa tính restore, validation, throttling, retries hoặc cutover. Nếu `μ≤λ`, backlog không giảm bền vững. Cần tăng capacity, giảm live work có kiểm soát hoặc dùng snapshot gần hơn.

### 16.2. Throttle và bảo vệ production

Replay 100 triệu events có thể làm broker, DB/search cluster hoặc network quá tải. Giới hạn batch size, records/giây, concurrent writes, connection pool và I/O. Theo dõi live SLI, throttling, CPU, memory, queue lag và storage. Rebuild nhanh hơn không có giá trị nếu nó làm Order/Payment hiện tại ngừng phục vụ.

## 17. Consumer group riêng không đồng nghĩa an toàn tuyệt đối

Không reset live consumer group sang earliest nếu consumer đó xử lý commands hoặc side effects. Tạo replay group riêng nhưng còn phải:

- Dùng handler chỉ ghi projection.
- Không cấp quyền gọi PSP/Shipping/Notification.
- Target là shadow DB/index, không phải production domain DB.
- Ghi checkpoint, audit và policy riêng.
- Giới hạn read traffic trên broker và write traffic tới search.
- Không reuse data sửa thủ công trong target cũ.
- Không xóa offsets hoặc metadata của các live consumers.

Một replay group có thể vẫn tiêu thụ tài nguyên từ shared cluster; isolation logic và isolation capacity là hai yêu cầu khác nhau.

## 18. Checkpoint có thể restart

Một job có thể chạy nhiều giờ và gặp crash/rebalance. Metadata ví dụ:

~~~yaml
rebuild:
  runId: "order-view-v5-20261112"
  source: "order-domain-events"
  target: "order_view_v5_shadow"
  projectorVersion: "2.3.1"
  schemaVersion: 5
  nextOffsets:
    partition-0: 987655
    partition-1: 876541
  lastCommittedBatch: 417
  status: "CATCHING_UP"
~~~

Cần định nghĩa:

- Offset là **next unread** hay **last applied**, nhất quán mọi thành phần.
- Checkpoint lưu bền vững, không chỉ local file của container.
- Checkpoint chỉ advance sau projection commit.
- Nếu broker offset và DB write không transactional cùng nhau, consumer phải idempotent khi xử lý lại.
- Chạy lại phải kiểm run ID, source, target, schema/version tránh trộn hai rebuild.
- Với multi-partition phải lưu checkpoint theo partition, không dùng một số chung.

### 18.1. Cửa sổ crash

| Thời điểm crash | Nguy cơ | Cách thiết kế |
|---|---|---|
| Trước projection write | Event chưa áp | Replay lại |
| Sau projection write, trước checkpoint | Event đọc lại | De-dup/idempotent upsert |
| Sau checkpoint, trước DB commit | Bỏ event | Không advance checkpoint trước commit |
| Giữa batch writes | Target dở dang | Transaction hoặc idempotent batch resume |
| Khi cutover | Reader nhìn trạng thái chưa xong | Atomic alias/pointer strategy |
| Sau cutover, writer còn trỏ cũ | Read model stale | Định tuyến writer và cutover gate |

## 19. SQL minh họa cho read model

~~~sql
CREATE TABLE order_view_v5 (
    order_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    customer_ref TEXT NOT NULL,
    total_minor_units BIGINT,
    currency CHAR(3),
    aggregate_version BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE order_view_v5_processed_events (
    event_id TEXT PRIMARY KEY,
    aggregate_id TEXT NOT NULL,
    aggregate_sequence BIGINT,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE order_view_v5_checkpoint (
    run_id TEXT NOT NULL,
    partition_id INTEGER NOT NULL,
    next_offset BIGINT NOT NULL,
    projector_version TEXT NOT NULL,
    PRIMARY KEY (run_id, partition_id)
);
~~~

Mẫu chưa bao gồm index tuning, tenant policy, partitioning và retention. Khi event chứa trạng thái snapshot đầy đủ, có thể dùng upsert có version guard:

~~~sql
INSERT INTO order_view_v5 (
    order_id, status, customer_ref, total_minor_units,
    currency, aggregate_version, updated_at
)
VALUES (
    :orderId, :status, :customerRef, :totalMinor,
    :currency, :sequence, :occurredAt
)
ON CONFLICT (order_id)
DO UPDATE SET
    status = EXCLUDED.status,
    customer_ref = EXCLUDED.customer_ref,
    total_minor_units = EXCLUDED.total_minor_units,
    currency = EXCLUDED.currency,
    aggregate_version = EXCLUDED.aggregate_version,
    updated_at = EXCLUDED.updated_at
WHERE order_view_v5.aggregate_version < EXCLUDED.aggregate_version;
~~~

**Chỉ dùng kiểu update này nếu event chứa đủ full state.** Với event delta `ItemAdded`, phải áp reducer và sequence checks; không thể thay state bằng một payload thiếu trường.

Một batch transaction lý tưởng:

~~~text
BEGIN
  normalize and validate events
  skip already processed event IDs
  validate aggregate sequence and state transitions
  apply reducer changes to shadow tables
  write processed IDs
  persist next checkpoint
COMMIT
~~~

Khi projection target là search engine không hỗ trợ multi-document DB transactions, cần stable document IDs, external version/optimistic write, idempotent retries, per-batch progress và reconciliation.

## 20. Java: tách reducer và replay coordinator

### 20.1. Pure reducer

~~~java
public record OrderView(
    String orderId,
    String status,
    long sourceVersion
) {}

public record OrderEvent(
    String orderId,
    long sequence,
    String type
) {}

public final class OrderProjectionReducer {
    public OrderView apply(OrderView previous, OrderEvent event) {
        if (previous != null && event.sequence() <= previous.sourceVersion()) {
            return previous;
        }
        if (previous != null && event.sequence() != previous.sourceVersion() + 1) {
            throw new IllegalStateException("Event gap");
        }
        if (previous == null && event.sequence() != 1) {
            throw new IllegalStateException("Missing initial event");
        }

        String next = switch (event.type()) {
            case "OrderCreated" -> "CREATED";
            case "PaymentAuthorized" -> "PAYMENT_AUTHORIZED";
            case "InventoryReserved" -> "INVENTORY_RESERVED";
            case "OrderCompleted" -> "COMPLETED";
            case "OrderCancelled" -> "CANCELLED";
            default -> throw new IllegalArgumentException(
                "Unsupported type: " + event.type()
            );
        };

        return new OrderView(event.orderId(), next, event.sequence());
    }
}
~~~

Đây là mẫu tối giản, chưa phải state machine hoàn chỉnh. Trong dự án thật, reducer phải kiểm transition hợp lệ, các nhánh compensation, tenant boundaries, event payload và correction history.

### 20.2. Áp event với database transaction

~~~java
public void applyOne(EventEnvelope raw) {
    CanonicalEvent event = upcaster.normalize(raw);

    transactionTemplate.executeWithoutResult(tx -> {
        if (inboxRepository.isProcessed(targetVersion, event.id())) {
            return;
        }

        OrderView before = projectionRepository.find(event.aggregateId());
        OrderView after = reducer.apply(before, event.orderEvent());

        projectionRepository.save(after);
        inboxRepository.markProcessed(targetVersion, event.id());
    });
}
~~~

Các repository, record và service ở đây là interface giả định. Cần **unique constraint** trong DB, vì chỉ kiểm `isProcessed` trước insert có thể bị race khi nhiều worker chạy cùng lúc. Tính atomicity giữa projection write, processed record và checkpoint cần được kiểm trên engine DB thật.

### 20.3. Không tái sử dụng consumer gửi email

Sai:

~~~text
on OrderCompleted:
    update reporting table
    send completion email
~~~

Khi replay hàng triệu `OrderCompleted`, email có thể bị gửi lại. Hãy tách `ReportingProjector` khỏi `NotificationCommandHandler`, và replay không được cấp quyền publish notification command.

## 21. Kafka: offset và commit

Một consumer replay group có thể dùng:

~~~properties
bootstrap.servers=broker.example.invalid:9092
group.id=order-view-v5-replay-20261112
enable.auto.commit=false
auto.offset.reset=earliest
max.poll.records=500
isolation.level=read_committed
~~~

Đây là ví dụ, không phải cấu hình đủ để chạy production. `auto.offset.reset=earliest` chỉ đưa group mới tới **event cũ nhất đang còn trong topic**, không khôi phục event đã bị retention xóa. `isolation.level=read_committed` có ý nghĩa với transactional Kafka producers nhưng không tạo exactly-once khi ghi sang DB/search.

Trình tự:

1. Poll records của partitions được assign.
2. Normalize/upcast, validate sequence.
3. Áp vào projection và processed IDs.
4. Commit transaction bền vững.
5. Lưu checkpoint `next_offset`.
6. Commit Kafka offsets phù hợp.

Nếu DB checkpoint và broker offset nằm ở hai hệ thống khác nhau, có thể phải đọc lại sau crash; idempotency phải xử lý an toàn.

### 21.1. Parallelism

Có thể xử lý nhiều partitions song song, nhưng vẫn giữ ordering theo key. Không tăng consumer threads vô hạn khi search/DB write throughput đã đạt giới hạn. Queue, rate limit, broker quotas và hot partitions cần được quan sát.

## 22. Rebuild search index không gián đoạn

Một cách thực hiện:

~~~text
Current reads --> alias orders-search --> orders-v4
                                           |
Replay job --> create index orders-v5 ------+
                                           |
Validation compares v4 / domain source ----+
                                           |
Atomic alias cutover --> orders-v5
~~~

Các bước:

1. Tạo `orders-v5` với mapping/analyzer và index settings mới.
2. Chọn source snapshot/history và cutoff.
3. Replay bằng stable document ID (ví dụ `order_id`), không auto-generate IDs.
4. Áp version guard để sự kiện cũ không ghi đè trạng thái mới.
5. Xử lý deletes/tombstones và corrections.
6. Theo dõi bulk indexing throughput, memory, disk và search latency.
7. Catch up live delta đến watermark.
8. So document counts, status/amount, query results và access control.
9. Chuyển alias/read pointer nguyên tử theo khả năng engine.
10. Xác nhận live writer chỉ ghi target đúng sau cutover.
11. Giữ index cũ đủ thời gian rollback rồi dọn có phê duyệt.

Alias swap không bảo đảm writer transition tự đúng. Một consumer vẫn ghi v4 sau khi alias đọc đã sang v5 có thể làm v5 stale. Vì vậy cutover phải quản lý cả **đường đọc và đường ghi delta**.

## 23. Rebuild cache, analytics và workflow state

### 23.1. Cache

Cache thường có thể warm từ database/read model. Không cần full replay nếu nguồn đã có latest state. Nhưng cache cold-start có thể gây DB overload; cần pre-warm hot keys, throttle, TTL và fallback theo contract.

### 23.2. Analytics

Báo cáo doanh thu theo vùng phụ thuộc định nghĩa: gross/net, refund, tax, timezone, currency, exchange rate, late events và corrections. Khi đổi projector, báo cáo lịch sử có thể đổi theo chủ đích. Cần versioned metric definition và đối soát với ledger.

### 23.3. Saga/workflow projection

Một checkout có thể ở trạng thái `PaymentAuthorized`, `InventoryReserved`, `Compensating` hoặc `Completed`. Để dựng lại, cần các transitions và outcome từ external providers. Timer và deadline phải được tính từ timestamp đã ghi; không được replay timer command để tự động refund lại.

### 23.4. Materialized views

Shadow SQL tables/views có thể rebuild rồi chuyển read pointer. Nếu code cũ và mới dùng schema khác nhau, phải giữ compatibility trong rollout. Số dòng bằng nhau không chứng minh các quan hệ/giá trị đúng.

## 24. Kiểm tra dữ liệu trước cutover

| Lớp kiểm | Câu hỏi | Cách kiểm |
|---|---|---|
| Completeness | Đã có đủ records/events? | Counts theo date/region/status |
| Schema | Fields/type/enum hợp lệ? | Schema validation |
| Sequence | Có missing aggregate version? | Gap detector |
| Idempotency | Có duplicate record/side effect? | Unique constraints/reconciliation |
| Business invariant | No oversell/no double charge? | Domain/ledger checks |
| State machine | Có terminal→invalid transition? | Invariant queries |
| Privacy | Deleted data có sống lại? | Tombstone/deletion checks |
| Freshness | Source-to-target lag còn bao nhiêu? | Checkpoints, event age |
| Read API | Query/filter/sort/authorization đúng? | Contract/smoke tests |
| Provenance | Biết transformer/snapshot/offset? | Release record |
| Financial | Tổng theo tiền/thuế/refund khớp nguồn? | Ledger reconciliation |

Không chỉ so total row count. Có thể thiếu 100 records ở vùng A và thừa 100 ở vùng B, tổng vẫn bằng nhau. So theo các nhóm thích hợp, dùng checksums/aggregates, sample queries và invariants toàn tập.

### 24.1. Checksum đúng cách

Muốn hash bảng để so, phải chuẩn hóa thứ tự records, field ordering, nulls, decimals, timezone, encoding và schema version. Không so byte-for-byte một bảng v2 đã đổi semantics với v1 rồi kết luận sai. Khi định nghĩa mới, liệt kê expected differences.

### 24.2. Quarantine và dữ liệu thiếu

Khi gặp event không decode được hoặc sequence gap, không skip âm thầm rồi vẫn báo replay complete. Đưa vào quarantine có reason code, dừng hoặc đánh dấu target chưa sẵn sàng theo policy và điều tra source/archive/schema. Một event bị bỏ có thể khiến mọi trạng thái sau của aggregate sai.

## 25. Cutover và rollback

Một readiness gate tối thiểu:

- Target đã dựng đầy đủ theo source positions và schema/version rõ.
- Event lag dưới ngưỡng đã phê duyệt.
- Không có unresolved critical gaps, corruption hoặc privacy violations.
- Business invariants và reconciliation đạt tiêu chí.
- Read query API và authorization tương thích.
- Live writer đã có kế hoạch chuyển sang target mới.
- Đã xác định rollback action, old target retention và người phê duyệt.
- Có dashboard SLI và đội on-call khi chuyển đổi.

Có thể dùng alias/pointer atomically, hoặc feature flag chuyển nhóm nhỏ traffic sang projection mới để canary nếu kiến trúc hỗ trợ.

### 25.1. Rollback không chỉ đổi alias

Nếu live producer đã phát schema event mới mà projector cũ không hiểu, trả traffic sang index cũ có thể làm nó không cập nhật được. Cần giữ compatibility, dual projector trong migration hoặc một đường roll-forward đã diễn tập.

### 25.2. Sau cutover

Theo dõi read latency, errors, event lag, data mismatches và business outcomes. Giữ old target theo thời gian rollback đã thống nhất. Không xóa ngay chỉ vì health checks xanh.

## 26. RPO và RTO cho derived data

**RPO** là mức dữ liệu được phép mất theo mục tiêu. **RTO** là thời gian cần phục hồi capability. Với derived data, nếu source event history vẫn đầy đủ, có thể đạt RPO≈0 đối với **nguồn**, nhưng projection có thể bị trễ trong thời gian replay/catch-up.

Một mô hình ngân sách:

\[
T_{\mathrm{recovery}} =
T_{\mathrm{diagnose}} +
T_{\mathrm{restore}} +
T_{\mathrm{replay}} +
T_{\mathrm{catchup}} +
T_{\mathrm{validate}} +
T_{\mathrm{cutover}}
\]

Các bước có thể chồng nhau tùy thiết kế. Nếu cần khôi phục search trong 20 phút nhưng full replay mất 6 giờ, phải dùng snapshot gần hơn, restore index backup hoặc cung cấp degrade mode có thời hạn phù hợp.

| Metric | Ý nghĩa |
|---|---|
| Source history coverage | Có đủ dữ liệu để rebuild không? |
| Replay events/sec | Tốc độ xử lý bền vững |
| Target writes/sec | Bottleneck DB/search |
| Backlog remaining | Số records chưa áp |
| Oldest unapplied event age | Mức stale của projection |
| Invalid/upcast failures | Sự kiện không thể xử lý |
| Quarantine count | Dữ liệu cần can thiệp |
| Reconciliation mismatches | Sự khác biệt với nguồn |
| Catch-up ETA | Dự kiến khi nào đạt điều kiện cutover |
| Cutover readiness | Tất cả gates đã đạt chưa? |
| Live SLI degradation | Replay có ảnh hưởng traffic hiện tại? |

`Consumer lag=0` không đồng nghĩa khôi phục xong nếu consumer đã bỏ qua events lỗi hoặc target ghi sai. Thành công gồm đầy đủ source, transformation, checkpoint, validation và read cutover.

## 27. Security, privacy và audit

Replay production data có thể cho phép đọc **toàn bộ lịch sử khách hàng** trong khi live API chỉ cần xem vài records. Cần:

1. Workload identity riêng, least privilege, quyền có expiry nếu phù hợp.
2. Source read-only và target shadow write hạn chế.
3. Không cấp payment, shipping hay notification credentials.
4. Encryption in transit/at rest cho event, archive, snapshot và projection.
5. Audit run ID, người phê duyệt, source range, schema/projector version và cutover.
6. Không log PII, tokens, secrets hoặc payload nhạy cảm không cần thiết.
7. Kiểm tenant boundaries/data residency khi khôi phục cross-region.
8. Áp deletion/correction/tombstones để không hồi sinh dữ liệu đã xóa.
9. Cleanup shadow index/temp data theo retention sau incident.
10. Phân quyền truy cập raw event payload, checkpoint metadata và backup.
11. Test trên dữ liệu giả hoặc sanitized nếu không được phép mang production data sang môi trường thử.

Shadow projection chưa nhận traffic vẫn có thể chứa dữ liệu production nhạy cảm; không vì “temporary” mà bỏ security policy.

## 28. Runbook mẫu: mất Order Search index

### Bối cảnh giả định

Order DB vẫn còn, event archive và snapshot đã được xác minh; index `orders-v4` bị hỏng tại region APAC. Search API trả kết quả sai hoặc 503; Order/Payment flows chính vẫn hoạt động.

### Bước 1 — Khai báo incident

Ghi thời gian, region, capability, impact, incident owner. Kiểm domain source còn nguyên vẹn. Không xóa backup hoặc sửa index cũ khi chưa bảo toàn bằng chứng.

### Bước 2 — Chọn nguồn

Kiểm snapshot checksum, schema version, partition offsets, archive coverage và deletion events. Nếu snapshot chứa bug, không dùng làm nguồn chỉ vì restore nhanh.

### Bước 3 — Tạo shadow target

Tạo `orders-v5-shadow` với mapping mới, quyền và quota phù hợp. Không ghi đè current read model đang phục vụ.

### Bước 4 — Bảo vệ side effects

Replay worker không có credentials Payment/Notification. Chỉ đọc source và ghi shadow. Đặt max throughput và abort conditions.

### Bước 5 — Restore snapshot và replay delta

Khôi phục snapshot đã xác minh, đọc events sau cutoff, upcast version cũ, de-dup, checkpoint và theo dõi gaps/errors.

### Bước 6 — Catch up với nguồn live

Ghi high watermark, xử lý delta đến mức lag mục tiêu. Bảo đảm không có gap giữa snapshot, archive và live feed.

### Bước 7 — Reconcile

So số đơn theo status/date/region, deleted records, ACL/tenant boundaries, sample search queries và source versions. Không cutover khi mismatch quan trọng chưa giải quyết.

### Bước 8 — Cutover

Chuyển alias/read pointer đúng khả năng engine, xác định live writer target, chạy smoke tests và đo latency/error.

### Bước 9 — Xác nhận phục hồi

Theo dõi event lag, read SLI, user-facing errors và business workflow metrics. Giữ rollback path trong một khoảng hợp lý; lưu run metadata.

### Bước 10 — Hậu kiểm

Ghi RTO/RPO thực tế, sự cố gặp khi restore, số gap/quarantine, actions và cải tiến retention/snapshot/runbook.

**Không báo kết thúc chỉ vì Pod Ready hoặc Kafka lag về 0.** Phải chứng minh người dùng truy vấn lại được dữ liệu đúng trong giới hạn đã cam kết.

## 29. Tình huống: bug double count trong Reporting

Reporting v3 có bug: khi Kafka redelivery `PaymentCaptured`, nó cộng doanh thu hai lần. Bảng báo cáo bị phóng đại trong 48 giờ; Payment ledger vẫn đúng.

Một chiến lược:

1. Xác định khoảng thời gian, release version và data scope bị nhiễm.
2. Dừng writer lỗi hoặc tách target, không reset live consumer mù.
3. Sửa logic de-dup/unique business identity.
4. Chọn snapshot trước bug hoặc replay full history vào shadow table.
5. Apply projector mới, không gọi PSP, không gửi receipt.
6. Đối soát tổng thanh toán, refunds, currency và correction records với ledger.
7. Ghi expected differences và source lineage.
8. Chuyển read/report pointer sau approval của domain/Finance.
9. Giữ audit chứng minh báo cáo cũ sai và bản mới đã sửa.
10. Thêm integration test duplicate/redelivery vào quy trình release.

Không tự “trừ một số ước lượng” cho nhanh nếu chưa biết các logical operations và correction liên quan.

## 30. Tình huống: thiếu event lịch sử

Kafka giữ 14 ngày, snapshot gần nhất 30 ngày trước, domain DB chỉ giữ latest state. Muốn dựng báo cáo chuyển trạng thái trong 30 ngày, cần events của 16 ngày đã mất.

Phương án:

- Kiểm archive/backup event log khác và checksum.
- Tìm snapshot gần hơn có metadata positions.
- Dùng domain DB latest-state để rebuild các read models không cần toàn bộ lịch sử.
- Dùng ledger/warehouse để tái tạo reporting lịch sử nếu có nguồn đáng tin.
- Công khai khoảng dữ liệu không thể tái tính, đánh dấu degraded quality.
- Mở action cải thiện archive/snapshot cadence.

Không sinh event lịch sử giả với timestamp đoán để che gap. Nếu cần manual correction, phải ghi provenance, audit và độ tin cậy.

## 31. Tình huống: multi-region failover

Khi region chính mất mạng, region dự phòng có thể nhận events bị trễ hoặc thiếu. Nếu hệ thống có dual writers, hai region có thể tạo conflicting aggregate versions.

Cần kiểm:

- Region nào là source authority tại từng thời điểm?
- Replication lag và RPO đo ra sao?
- Có event IDs và aggregate versions để de-dup không?
- Có checkpoint/offset tương đương ở region dự phòng không?
- Có split-brain hoặc dual-writer divergence không?
- PSP/ledger xác nhận side effects ở đâu?
- Dữ liệu phải được reconcile trước khi rebuild projections không?
- Có deletion/privacy records được nhân bản đủ không?

Không chọn payment event “mới nhất theo timestamp” khi hai region xung đột; cần domain conflict resolution và ledger authority trước. Replay chỉ tái dựng một projection từ nguồn **đã được phân xử**.

## 32. Kiểm thử trước disaster

### 32.1. Unit tests

- Cùng input và event order cho cùng output.
- Event duplicate không đổi projection.
- Sequence gap được phát hiện.
- Unsupported event version được quarantine/stop theo policy.
- Correction và deletion events có kết quả đúng.
- Projector không gọi clock/random/external API tùy ý.
- Financial rounding/timezone ổn định.
- Invalid state transition bị từ chối.

### 32.2. Integration tests

- Consumer crash sau DB commit trước offset commit.
- Event out-of-order, duplicate và multi-partition.
- Snapshot offset bị lệch hoặc checksum sai.
- Search target trả 429/503 và job retry có giới hạn.
- Worker restart/rebalance vẫn tiếp tục từ checkpoint.
- Backlog tăng khi live rate cao hơn replay throughput.
- Upcaster xử lý events của các phiên bản cũ.
- Replay không có outbound side-effect permissions.
- Index alias cutover và rollback khi query validation fail.

### 32.3. DR game day

Dựng dữ liệu đại diện, cố ý xóa projection **trong môi trường thử được phép**, chạy snapshot+delta, đo thời gian và đối soát. Để người khác thực hiện runbook, không chỉ tác giả. Kiểm RTO thực tế, quota của broker/DB, ability to catch up và tác động lên live traffic thử nghiệm.

Một bài test trên 1.000 events không chứng minh có thể rebuild hàng tỷ events trong RTO. Test capacity phải phù hợp data volume và schema history.

## 33. Các lỗi thường gặp

1. Reset consumer group production về earliest, kích hoạt lại business side effects.
2. Replay dùng cùng handler có gửi email hoặc gọi PSP.
3. Tưởng Kafka topic giữ lịch sử vĩnh viễn.
4. Không có snapshot cutoff và offset conventions rõ.
5. Checkpoint advance trước khi target writes bền vững.
6. Dựa vào event ID mà bỏ qua duplicate logical payment operation.
7. Sort toàn bộ events theo timestamp, bỏ qua causality/partitioning.
8. Không có upcaster cho schema cũ.
9. Rebuild trực tiếp vào production table đang phục vụ.
10. Dùng auto-generated search document IDs gây duplicates.
11. Không replay tombstones, làm hồi sinh dữ liệu đã xóa.
12. Chạy replay không throttle làm ảnh hưởng live SLO.
13. Cutover khi lag=0 mà chưa reconcile dữ liệu.
14. Không giữ rollback target sau cutover.
15. Snapshot có corruption/bug nhưng được tin vì checksum file đúng.
16. Dùng `Instant.now()` cho business timestamp của event lịch sử.
17. Không lưu projector version và source positions.
18. Không phân quyền run replay hoặc audit.
19. Xem record count bằng nhau là bằng chứng dữ liệu đúng.
20. Không test restore hoặc chỉ test dữ liệu rất nhỏ.
21. Trộn live writer v4 và replay writer v5 trên cùng target không có version guard.
22. Không xử lý event missing và quarantine, vẫn báo “complete”.
23. Đánh đồng projection rebuild với phục hồi domain source of truth.
24. Cho hai region conflict rồi tự chọn event theo đồng hồ không đáng tin.
25. Quên business workflow state sau khi index trở lại healthy.

## 34. Bài tập thực hành

### Bài A — Đánh giá khả năng rebuild

Order DB có 2 năm dữ liệu; outbox xóa sau ba ngày, Kafka giữ 14 ngày, search index bị mất. Có thể full replay 2 năm không? Nếu không, đề xuất snapshot/CDC/archive và nêu những báo cáo lịch sử vẫn không thể dựng từ latest-state DB.

### Bài B — Tính thời gian catch-up

Backlog 8 triệu events, replay throughput 6.000/s, live rate 2.000/s. Tính `T_drain`. Nếu replay chỉ 1.800/s, có khả năng catch-up không? Đề xuất chiến lược tăng throughput hoặc snapshot gần hơn.

### Bài C — Crash sau write trước offset

`OrderCompleted(E9)` đã ghi doanh thu thành công nhưng consumer crash trước commit offset. E9 phát lại. Thiết kế de-dup/transaction/checkpoint để không cộng hai lần.

### Bài D — Schema cũ thiếu currency

`PaymentCaptured v1` chỉ có amount, v2 có currency. Reporting v3 cần tổng theo currency. Khi nào dùng historical reference để upcast, khi nào phải đánh dấu không thể rebuild chính xác? Vì sao default currency hôm nay nguy hiểm?

### Bài E — Shadow index

Thiết kế các bước dựng `orders-v5`, replay, catch-up, validate, alias swap và rollback. Nêu cách bảo đảm writer/consumer không còn trỏ vào index cũ và delete/tombstone được áp đầy đủ.

### Bài F — Side-effect isolation

Một consumer của `OrderCompleted` vừa ghi reporting vừa gửi email. Cần replay 10 triệu events. Hãy tách pure projector và notification command handler, thiết kế IAM/network policy và test không có outbound calls.

### Bài G — DR drill

Lên một game day giả lập mất projection. Ghi nguồn snapshot, retention, owners, recovery budget, failure injection, validation gates, metric, runbook và postmortem. Đo RPO/RTO và số lượng mismatches.

### Bài H — Multi-region

Khi network partition, hai region cùng cập nhật Order với aggregate version giống nhau nhưng payload khác. Có thể chỉ sort theo timestamp không? Nêu authority/conflict resolution và bước reconciliation trước khi replay.

## 35. Checklist vận hành

### Chuẩn bị

- [ ] Biết nguồn sự thật và projections được phép rebuild.
- [ ] Có full event history hoặc snapshot+delta đủ coverage.
- [ ] Retention, compaction và archive được kiểm định thực tế.
- [ ] Event envelope có identity, version, aggregate key/sequence và timestamps.
- [ ] Projector deterministic/idempotent, có upcasters.
- [ ] Đã định nghĩa late events, gaps, corrections, deletion/tombstones.
- [ ] Có workload identity replay không có side-effect credentials.
- [ ] RTO/RPO, capacity và runbook đã được diễn tập.

### Chạy replay

- [ ] Ghi run ID, source/checkpoints, snapshot và projector version.
- [ ] Consumer group và shadow target tách khỏi live.
- [ ] Batch writes và checkpoints không tạo gap khi crash.
- [ ] Quarantine events có nguyên nhân và xử lý rõ.
- [ ] Replay có throttling, theo dõi live SLO.
- [ ] Không phát commands/notifications hoặc thực hiện external side effects.
- [ ] So counts, statuses, money, privacy deletes và state invariants.
- [ ] Catch up tới watermark và điều kiện consistency đã định.

### Cutover và hậu kiểm

- [ ] Owner phê duyệt sau validation.
- [ ] Read alias/pointer và live writer routing đồng bộ.
- [ ] Có rollback path và retention old target.
- [ ] Theo dõi search/read SLI, event lag và business outcomes.
- [ ] Không còn mismatch quan trọng chưa giải quyết.
- [ ] Ghi RTO/RPO thực đo, incident evidence và actions.
- [ ] Thu hồi quyền replay tạm, cleanup shadow/temp theo policy.

## 36. Kết luận

**Replay là công cụ tái tạo dữ liệu dẫn xuất từ một lịch sử đáng tin, không phải thực hiện lại các lệnh nghiệp vụ.** Để khôi phục an toàn, cần biết event history còn đầy đủ không, schema cũ có đọc được không, reducer có deterministic/idempotent không, sự kiện có được xử lý đúng thứ tự không và job có thực sự bị cô lập khỏi Payment/Notification/Shipping hay không.

Một quy trình tốt thường theo chuỗi: **xác minh source/snapshot → tạo shadow projection → replay có checkpoint/throttle → catch-up live → reconciliation → cutover có rollback → quan sát user outcomes**.

Thành công không phải là consumer đã đọc đến cuối topic hoặc Pod đã xanh, mà là **người dùng truy vấn được dữ liệu đúng trong RTO, nguồn dữ liệu không mất quá RPO, mọi correction/deletion còn hiệu lực và không có side effect mới ngoài ý muốn**.