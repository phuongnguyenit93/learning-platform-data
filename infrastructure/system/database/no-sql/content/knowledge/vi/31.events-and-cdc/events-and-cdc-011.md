# Replay, rebuild dữ liệu dẫn xuất và kiểm soát tốc độ

Một hệ thống đặt hàng lưu dữ liệu giao dịch trong NoSQL, đồng thời duy trì **search index**, **dashboard doanh thu**, **cache tổng hợp** và **read model** dành cho nhân viên vận hành. Một ngày, team phát hiện logic tính doanh thu bị sai hoặc mapping của search index cần thay đổi. Không thể chỉ sửa code consumer rồi chờ các đơn hàng mới: hàng triệu bản ghi đã được xử lý bằng logic cũ, còn các bản ghi cũ không tự phát lại.

Giải pháp là **replay** dữ liệu/sự kiện lịch sử và **rebuild** dữ liệu dẫn xuất (derived data). Nhưng chạy lại một triệu events cũng có thể tạo một triệu lượt đọc, ghi, index và network calls trong thời gian ngắn. Nếu không giới hạn tốc độ, chính công việc sửa hệ phân tích có thể làm NoSQL transaction source bị nghẽn, khiến API đặt hàng chậm hoặc timeout.

Trong chương **Sự kiện và CDC** của module **Database No SQL**, bài học này trình bày đầy đủ vòng đời từ xác định nguồn dữ liệu, snapshot + CDC, replay/idempotency, phiên bản projection, checkpoint, validation, cutover, đến **rate limiting/backpressure**. Trọng tâm là **tái xây dựng đúng dữ liệu, có thể tiếp tục khi lỗi, không làm mất thay đổi mới, và không gây quá tải cho nguồn nghiệp vụ**.

> **Nguyên tắc xuyên suốt:** Replay là thực thi lại dữ liệu đã tồn tại theo một hợp đồng; rebuild là tạo lại một trạng thái dẫn xuất. Thêm sự kiện vào một queue không tự bảo đảm tính đúng đắn của projection, còn tăng worker lên thật nhiều không tự làm rebuild an toàn hơn.

Các số liệu latency, throughput, retention và kích thước dùng trong bài là **giả định minh họa**, không phải cam kết của một sản phẩm/phiên bản NoSQL hay broker. Trong vận hành thực tế phải tham chiếu semantics của connector, source log, snapshot, transaction boundary và cấu hình đang sử dụng.

## 1. Replay và rebuild nghĩa là gì?

**Replay** là đọc lại dữ liệu lịch sử từ một nguồn có thể truy cập và đưa nó qua một hoặc nhiều bước xử lý. Nguồn có thể là:

- Append-only event log hoặc event store.
- CDC log/change stream mà retention còn đủ.
- Snapshot/export của database kèm một dải CDC tiếp nối.
- Một tập immutable fact files trong object storage.
- Một queue/topic cho phép consumer đọc lại từ offset cũ.
- Một bảng nguồn được quét tuần tự theo checkpoint, nếu có hợp đồng consistency phù hợp.

**Rebuild** là dựng lại một hoặc nhiều đại diện dữ liệu được tạo từ nguồn, chẳng hạn:

- Elasticsearch/OpenSearch search index.
- MongoDB reporting collection hoặc document projection.
- Bảng tổng hợp doanh thu theo ngày/SKU.
- Recommendation feature store, ranking, top-K.
- Graph edges hoặc materialized relationship view.
- Cache warm set nếu cần tạo lại sau deploy/outage.

Replay mô tả **quá trình đọc/xử lý lịch sử**; rebuild mô tả **mục tiêu tạo trạng thái mới**. Một hệ có thể replay để kiểm tra audit nhưng không ghi projection; hoặc rebuild từ snapshot nguồn mà không cần event-sourcing log đầy đủ.

## 2. Source of truth và dữ liệu dẫn xuất khác nhau

Giả sử nguồn có Order:

~~~json
{
  "orderId": "O1001",
  "customerId": "u42",
  "status": "CONFIRMED",
  "items": [
    {"sku": "SKU-A", "quantity": 2, "unitPriceMinor": 120000}
  ],
  "sourceVersion": 8
}
~~~

Các dẫn xuất có thể là:

~~~text
Transactional NoSQL source:
  orders/O1001 -> version 8, CONFIRMED

Search projection:
  order_search/O1001 -> searchable fields

Reporting projection:
  sales_fact/O1001/SKU-A -> quantity, amount, date

Materialized aggregate:
  revenue_by_day/2026-11-14 -> total net amount
~~~

Thông tin trong search/index/report có thể được **tính lại** từ nguồn, nhưng chỉ nếu nguồn và quy tắc nghiệp vụ còn đủ thông tin. Ví dụ một record hiện tại có `status=REFUNDED` chưa chắc đủ để tái tạo dòng lịch sử `PENDING → CONFIRMED → REFUNDED` nếu nghiệp vụ yêu cầu biết thời điểm từng chuyển trạng thái; khi đó cần facts hoặc event history được lưu bền.

**Không mặc định “có CDC” nghĩa là mọi event lịch sử đều còn.** CDC thường phục vụ truyền thay đổi trong một retention window, khác với event store dài hạn.

## 3. Phân biệt CDC, event sourcing và outbox

| Khái niệm | Tạo ra dữ liệu nào? | Có thể replay từ đầu? | Chú ý |
|---|---|---|---|
| **CDC** | Thay đổi đã ghi ở database theo cơ chế capture | Chỉ trong retention/archives có sẵn | Có thể là before/after image hoặc operation envelope |
| **Event sourcing** | Business events là nguồn chính của state | Nếu log đầy đủ, còn và có thể diễn giải | Replay rules/versioning là phần cốt lõi |
| **Transactional outbox** | Ý định phát business/integration event ghi cùng transaction phù hợp | Tùy thời gian lưu outbox/broker/archive | Relay có thể gửi lặp |
| **Snapshot/export** | State tại một mốc xác định | Có thể bootstrap current-state projection | Không tự chứa toàn bộ lịch sử |
| **Message broker** | Kênh chuyển/lưu records theo retention | Nếu vẫn còn offsets hoặc archived topics | Không phải mọi broker/queue đều cho seek/replay tùy ý |

Ví dụ: MongoDB change stream hay DynamoDB Streams có thể hỗ trợ CDC cho một khoảng thời gian. Nếu source cần rebuild dữ liệu nhiều năm mà retention không đủ, phải dựa vào snapshot/export, event archive hoặc quét nguồn với protocol phù hợp.

Khi lựa chọn pipeline, viết rõ: **người phát hiện thay đổi**, **nơi lưu lịch sử**, **mốc có thể replay sớm nhất**, **cách biết dữ liệu đã commit** và **cách khôi phục khi log có gap**.

## 4. Khi nào cần replay/rebuild?

Các nguyên nhân thông dụng:

1. **Bug fix:** bản cũ tính tổng, đếm hoặc map field sai.
2. **Schema evolution:** thêm field trong search index, đổi kiểu một trường trong projection.
3. **New read model:** xây một bảng denormalized theo access pattern mới.
4. **Data corruption:** một nhóm projection records bị hỏng hoặc thiếu.
5. **Consumer downtime:** process nghỉ lâu, backlog chưa được xử lý.
6. **Lost offsets:** consumer phải khởi tạo lại checkpoint sau khi xác minh nguồn.
7. **Algorithm change:** tính ranking/segmentation theo version mới.
8. **Privacy/deletion:** phản ánh các thay đổi hợp lệ vào projection/export.
9. **Region migration:** dựng bản sao dẫn xuất ở cluster mới.
10. **Disaster recovery:** xây lại read model sau khi mất cluster báo cáo.

Các trường hợp có mức nguy hiểm khác nhau. Rebuild search index từ complete product snapshot có thể tương đối đơn giản; rebuild **financial ledger** từ event history thiếu một số events có thể không hợp lệ. Trước khi chạy phải xác định **rebuildable hay không, rebuild từ đâu, có chấp nhận dữ liệu tạm lệch không**.

## 5. Kiến trúc mẫu: source, capture, log, consumers và projections

~~~mermaid
flowchart LR
    API["Giao dịch"] --> DB["NoSQL source of truth"]
    DB --> CDC["CDC / Outbox capture"]
    CDC --> LOG["Durable event log / archive"]
    LOG --> LIVE["Live projection consumer"]
    LOG --> REPLAY["Replay / rebuild workers"]
    LIVE --> P1["Projection hiện tại v1"]
    REPLAY --> P2["Projection mới v2"]
    P1 --> R["Read API"]
    P2 -. "Cutover sau verify" .-> R
~~~

Thiết kế tách hai luồng:

- **Live pipeline:** cập nhật dữ liệu dẫn xuất đang phục vụ người dùng theo thay đổi mới.
- **Rebuild pipeline:** xử lý lượng lớn lịch sử có kiểm soát, ghi vào **không gian dữ liệu mới** để không phá bản đang chạy.

Đường rebuild có thể dùng cùng event log nhưng **consumer group/offset/checkpoint và concurrency riêng**. Dùng cùng group với live consumer mà reset offset tùy tiện có thể làm live pipeline không còn theo dõi đúng tiến độ.

## 6. Mục tiêu đúng đắn trước mục tiêu tốc độ

Một rebuild được coi là đáng tin khi:

- **Complete:** đủ tập entities/events nằm trong phạm vi yêu cầu.
- **No duplicates in effect:** duplicate deliveries không làm tăng counts, charge hay tạo bản ghi trùng.
- **Correct ordering where required:** event version mới không bị event cũ ghi đè.
- **Correct deletion:** tombstones/delete được phản ánh.
- **Consistent semantics:** tính theo business rules/schema version được công bố.
- **Trackable progress:** biết đã xử lý tới checkpoint/watermark nào.
- **Recoverable:** crash giữa chừng có thể chạy lại không mất dữ liệu.
- **Isolated:** rebuild không phá transaction SLO và live projection.
- **Auditable:** biết nguồn, khoảng thời gian, code version và ai thực hiện.
- **Cutover-safe:** người đọc chỉ thấy projection mới sau khi đủ điều kiện.

**“Consumer xử lý hết messages” không đủ để chứng minh projection đúng**: có thể bỏ sót từ đầu vì mất retention, ignore poison event hoặc áp event sai thứ tự.

## 7. Hai loại rebuild chính: current state và lịch sử sự kiện

**Rebuild current-state projection**: lấy state hiện tại của mỗi entity (có thể từ snapshot) rồi chuyển sang schema mới. Thích hợp cho product search theo document hiện thời, user profile view hoặc dashboard chỉ hỏi trạng thái mới nhất.

~~~text
Source snapshot at checkpoint S
  -> transform every current product
  -> write index product_v2
  -> replay changes after S
~~~

**Rebuild history-based projection**: cần các events/facts lịch sử và chính sách tính toán. Thích hợp cho revenue movement, balances, funnel/cohort hoặc audit.

~~~text
Event/fact log from business start
  -> consume in valid order
  -> apply business reducer v2
  -> build daily revenue facts
~~~

Nếu chỉ có current state `REFUNDED`, bạn có thể không tính được lúc nào Order đã phát sinh doanh thu rồi hoàn tiền. **Chọn nguồn replay theo thông tin mà projection cần**, không dựa vào source nào dễ truy cập nhất.

## 8. Hợp đồng dữ liệu nguồn cho replay

Một event envelope minh họa:

~~~json
{
  "eventId": "evt-order-O1001-v8",
  "source": "orders-service",
  "aggregateType": "Order",
  "aggregateId": "O1001",
  "aggregateVersion": 8,
  "eventType": "ORDER_STATUS_CHANGED",
  "eventSchemaVersion": 2,
  "occurredAt": "2026-11-14T09:20:00Z",
  "committedAt": "2026-11-14T09:20:00.120Z",
  "payload": {
    "fromStatus": "PENDING",
    "toStatus": "CONFIRMED"
  }
}
~~~

Các trường mang ý nghĩa khác nhau:

- `eventId`: chống áp trùng một event.
- `aggregateId`: xác định thứ tự/cạnh tranh của một business entity.
- `aggregateVersion`: biết phiên bản entity, hỗ trợ gap detection khi protocol bảo đảm số liên tục.
- `eventSchemaVersion`: chọn parser/upcaster phù hợp.
- `occurredAt`: business time, không nhất thiết là commit order.
- `committedAt`: mốc commit theo semantics nguồn; không tự là global order.
- `payload`: snapshot hay delta? Thông tin cần tái tạo có đủ không?

Không tự suy eventId luôn unique hoặc aggregateVersion luôn tuần tự nếu producer chưa cam kết. **Rebuild correctness bắt đầu từ contract nguồn**, không từ số lượng consumers.

## 9. Full-state event và delta event phải xử lý khác nhau

**Full-state event:**

~~~json
{
  "aggregateId": "O1001",
  "aggregateVersion": 8,
  "kind": "ORDER_SNAPSHOT",
  "value": {"status": "CONFIRMED", "totalMinor": 240000}
}
~~~

Nếu projection chỉ cần current state, có thể áp chính sách **upsert khi incoming version mới hơn current**, miễn là event đã chứa toàn bộ trường cần thiết và delete/tombstone semantics rõ.

**Delta event:**

~~~json
{
  "aggregateId": "O1001",
  "aggregateVersion": 8,
  "kind": "ORDER_INCREMENT",
  "deltaMinor": 240000
}
~~~

Không được bỏ event v7 chỉ vì event v8 đến trước: v8 có thể cần applied state sau v7. Với delta phải có **per-aggregate order, dedup và gap handling**, hoặc dùng một reducer có tính giao hoán/lũy đẳng được chứng minh.

Một event version cao hơn không tự chứng minh có thể bỏ mọi bản thấp hơn. Cần biết **đó là state snapshot hay operation cần lịch sử**.

## 10. Retention: replay được bao xa?

Trước khi chạy, xác định:

~~~text
Required history:        từ 2024-01-01
Earliest broker offset:  2026-11-10
Earliest CDC log:        2026-11-13
Old snapshot available:  2026-11-01
Business event archive:  2024-01-01 đến hiện tại
~~~

Nếu chỉ có CDC trong vài ngày nhưng cần rebuild từ 2024, reset consumer offset không giải quyết gì. Một số hướng:

- Dùng event archive bền.
- Bootstrap từ snapshot còn hợp lệ, rồi replay CDC nối tiếp.
- Quét source hiện tại nếu projection chỉ cần current state.
- Dùng historical fact tables/exports có đủ thông tin.
- Reconcile với source và đánh dấu những khoảng không tái dựng được.

Nếu nguồn lịch sử thiếu và không thể suy từ current state, cần báo **rebuild không đầy đủ**. Không tạo một dashboard “final” từ dữ liệu không còn đủ nguồn.

## 11. Snapshot + CDC handoff: điểm khó nhất khi bootstrap

Giả sử snapshot bắt đầu lúc T0 và chạy 3 giờ. Trong thời gian đó live source vẫn có writes. Nếu quét toàn bộ rồi **mới bật CDC**, các cập nhật trong 3 giờ có thể bị mất.

~~~text
T0: Snapshot scan starts
T1: Order O42 changes from PENDING to CONFIRMED
T2: Snapshot reaches O42 (before or after write depending order)
T3: Snapshot completes
T4: Consumer starts CDC too late
~~~

Cần cơ chế **cột mốc giao nhau** giữa snapshot và changes:

~~~mermaid
flowchart TD
    A["Capture checkpoint / log position S"] --> B["Establish snapshot semantics at S"]
    B --> C["Backfill rows/documents"]
    C --> D["Replay changes since S"]
    D --> E["Catch up to moving head"]
    E --> F["Validate and expose projection"]
~~~

Lưu ý: sơ đồ là **mục tiêu logic**, không phải quy trình áp dụng trực tiếp cho mọi NoSQL engine. Một snapshot toàn cục chính xác tại S có thể cần khả năng snapshot/read timestamp hoặc connector hỗ trợ. Nếu quét dữ liệu đang thay đổi mà không có snapshot consistency, phải có protocol đánh version/offset/merge để tránh bỏ sót hoặc áp sai.

## 12. Cửa sổ snapshot/stream: bốn tình huống cần thử

| Tình huống | Snapshot lấy gì? | CDC chứa gì? | Kết quả mong muốn |
|---|---|---|---|
| Entity không đổi | State ổn định | Không có event liên quan | Một bản đúng |
| Update trước khi snapshot đọc key | Có thể đã là state mới | Event update được replay | Không nhân effect |
| Update sau khi snapshot đọc key | State cũ | Event update mới | Kết quả cuối mới |
| Delete trong lúc snapshot | Có thể còn hoặc không | Tombstone/delete | Không hồi sinh record |
| Insert sau checkpoint | Có thể hoặc không xuất hiện trong scan | Create event | Có đúng một entity |
| Nhiều updates cùng key | Snapshot có thể thấy một mốc | Nhiều versions | Không ghi lùi, không bỏ delta |

Các tình huống **overlap** có thể tạo duplicate logical state. Một projection xây theo full-state upsert/version dễ xử lý trùng hơn một aggregate “cứ event đến là cộng”. Với event delta cần tách logic chống double-count rõ ràng.

## 13. Checkpoint và offset: biết đã xử lý đến đâu

Consumer thường đọc các stream partitions và ghi vị trí:

~~~json
{
  "rebuildId": "rebuild-order-v2-20261114",
  "source": "orders-cdc",
  "projectionVersion": "v2",
  "checkpoints": {
    "partition-0": 120045,
    "partition-1": 99234,
    "partition-2": 107115
  },
  "updatedAt": "2026-11-14T11:00:00Z"
}
~~~

**Checkpoint phải biểu diễn phần dữ liệu đã được áp dụng bền vào projection**, không chỉ offset đã được poll hoặc message đã parse. Nếu checkpoint đi trước kết quả ghi đích, một process crash có thể khiến event bị bỏ vĩnh viễn.

Một quy tắc an toàn:

~~~text
Read event batch
  -> validate/order/dedup
  -> apply updates durably to projection
  -> commit processed IDs/version if needed
  -> only then advance checkpoint
~~~

Nếu projection write và checkpoint nằm ở **hai hệ riêng**, không mặc nhiên có transaction atomic giữa chúng. Cần thiết kế **at-least-once replay + idempotent consumer** để khi crash sau apply nhưng trước checkpoint, batch được replay mà không tạo double effect.

## 14. Crash matrix: lỗi ở đâu thì replay ra sao?

Xem consumer nhận event E có ID `evt-1001`:

| Điểm crash | Projection đã cập nhật? | Checkpoint đã tăng? | Khi khởi động lại |
|---|---|---|---|
| Trước khi đọc E | Chưa | Chưa | Đọc E lần đầu |
| Sau khi đọc, trước khi ghi | Chưa | Chưa | Đọc lại E |
| Ghi projection thành công, chưa checkpoint | Có | Chưa | E được đọc lại; cần dedup |
| Sau ghi và checkpoint | Có | Có | Tiếp theo offset sau E |
| Checkpoint trước khi ghi | Chưa | Có | **Nguy cơ mất effect của E** |
| Sau update một trong hai projections | Một phần | Tùy | Cần checkpoint/recovery riêng |

Một pipeline ghi cả Search và Reporting không nên dùng chung checkpoint “đã xử lý” nếu Search thành công nhưng Reporting thất bại, trừ khi có transaction/protocol bảo đảm cả hai. Mỗi projection nên có **rebuild job/checkpoint riêng**.

### 14.1. At-least-once + idempotent effect

Broker có thể đảm bảo một số delivery semantics trong phạm vi của nó, nhưng consumer còn gọi database đích hoặc storage bên ngoài. Rebuild nên chịu được **một event bị phát lại nhiều lần** mà trạng thái cuối không sai:

\[
\operatorname{apply}(\operatorname{apply}(S,E),E)
=
\operatorname{apply}(S,E).
\]

Một phép `SET currentStatus=CONFIRMED` có kiểm tra version có thể idempotent; `dailyRevenue += 100` sẽ **không idempotent** khi thiếu dedup ledger.

## 15. Idempotent projection theo source version

Với full-state upsert, record đích:

~~~json
{
  "orderId": "O1001",
  "status": "CONFIRMED",
  "totalMinor": 240000,
  "sourceVersion": 8,
  "projectionSchema": 2
}
~~~

Logic khái niệm:

~~~text
if projection absent:
    insert subject to generation/tombstone protocol
else if incoming.sourceVersion > stored.sourceVersion:
    atomically replace projection fields + sourceVersion
else:
    ignore duplicate or stale update
~~~

Điều kiện compare+replace phải **atomic trong consistency boundary** hoặc xử lý theo per-key sequence. Một đoạn `read version → compare → unconditional write` vẫn có race giữa hai workers.

Giả định phải công bố: version được nguồn cấp monotonic và không va chạm trong cùng aggregate, full-state event chứa đủ trường cho projection, tombstones ngăn dữ liệu cũ hồi sinh. Scalar version **không mô tả mọi concurrent forks** nếu nhiều writers độc lập; khi đó cần protocol nhân quả riêng.

## 16. Rebuild aggregate: không được nhân đôi doanh thu

Giả sử mỗi event `OrderConfirmed` có amount 240.000. Nếu E đến hai lần:

~~~text
dailyRevenue += 240000
dailyRevenue += 240000
~~~

Báo cáo bị gấp đôi. Một số thiết kế:

**A. Immutable fact theo unique event ID**

~~~text
confirmed_order_facts:
  eventId unique
  orderId
  amountMinor
  businessDate

Aggregate from:
  SUM(facts.amountMinor)
~~~

**B. Per-order contribution rồi tính delta**

~~~text
Before: O1001 contributes 0
After:  O1001 contributes 240000
Delta: +240000

On refund:
Before: contributes 240000
After:  contributes 0
Delta: -240000
~~~

Update per-order contribution và aggregate total cần **atomicity hoặc cơ chế reconciliation**, nếu hai nơi lưu riêng. Một update lỗi giữa chừng có thể khiến tổng lệch.

**C. Recompute từ facts đã dedup**: rebuild bảng facts trước, rồi aggregate theo batch. Tốn compute hơn nhưng tách source correctness khỏi việc increment online.

Replaying `OrderConfirmed` **không có nghĩa phải gọi cổng thanh toán lần thứ hai**. Rebuild chỉ ghi dữ liệu dẫn xuất, không được replay side effect bên ngoài theo mặc định.

## 17. Ordering, partitioning và parallelism

Tăng số worker không đồng nghĩa an toàn nếu events cần xử lý tuần tự:

~~~text
Partition P0: Order O1 versions 1,2,3,4
Partition P1: Order O2 versions 1,2,3
~~~

Có thể xử lý P0/P1 song song nếu aggregates độc lập. Nhưng để O1 v3 xử lý sau v4 mà không có version guard có thể ghi lùi trạng thái.

- Partition key theo `aggregateId` nếu cần per-aggregate order.
- Một active consumer/partition theo broker protocol.
- Full-state snapshot có thể bỏ version cũ **nếu** snapshot đủ thông tin.
- Delta events phải kiểm soát gaps và thứ tự.
- Tăng số partitions/consumers chỉ khi sink/source có capacity.
- Một operation liên aggregate vẫn có thể cần transaction/reconciliation riêng.

**Parallelism an toàn phụ thuộc conflict domain và tính giao hoán/idempotent của reducer**, không chỉ số CPU.

### 17.1. Event time không phải commit order

Một event `occurredAt` sớm hơn chưa chắc commit trước ở máy khác. Clock skew và delayed messages khiến event time không thích hợp để xác định total order. Dùng per-aggregate sequence, source log position hoặc causal metadata theo contract khi thứ tự quan trọng. Broker partition order không đảm bảo global order xuyên mọi partitions.

## 18. Delete, TTL và tombstone phải có mặt trong replay

Nếu snapshot có O3 nhưng sau đó nguồn xóa O3, projection mới không được giữ O3 mãi.

~~~json
{
  "eventId": "evt-delete-O3-v10",
  "aggregateId": "O3",
  "aggregateVersion": 10,
  "eventType": "ORDER_DELETED",
  "payload": {"deleted": true}
}
~~~

Một versioned tombstone:

~~~text
O3 -> {deleted:true, sourceVersion:10}
~~~

sẽ chặn snapshot cũ v8 hồi sinh record. Khi dọn tombstone, phải hiểu liệu vẫn có bản cũ từ snapshot/replay đến trễ hay không.

- Source delete phải được ánh xạ sang sink delete.
- TTL expiry có semantics capture riêng của từng engine; không mặc định luôn tạo event.
- Privacy deletion phải propagate tới index/warehouse/artifacts trong phạm vi chính sách.
- Soft delete và hard delete có ý nghĩa khác nhau.
- Delete sau snapshot cần có trong CDC replay.
- Rebuild từ archive cũ không được tái tạo PII đã bị yêu cầu xóa trái chính sách.

## 19. Event schema evolution và business rule version

Archive nhiều năm chứa các format:

~~~json
{
  "eventSchemaVersion": 1,
  "eventType": "ORDER_CONFIRMED",
  "payload": {"total": "120.00", "currency": "USD"}
}
~~~

Dạng mới:

~~~json
{
  "eventSchemaVersion": 3,
  "eventType": "ORDER_CONFIRMED",
  "payload": {"totalMinor": 12000, "currency": "USD"}
}
~~~

Consumer cần pipeline:

~~~text
historical event
  -> identify schema version
  -> matching decoder
  -> upcast/normalize
  -> reducer version v3
  -> projection write
~~~

Dùng decimal arithmetic rõ ràng thay cho chuyển tiền từ floating point vô kiểm soát. Một schema có thể không đổi nhưng **nghĩa doanh thu hoặc cách tính refund** đã đổi; khi đó projection cũng phải ghi business rule/algorithm version để giải thích vì sao rebuild cho kết quả khác.

## 20. Poison event và lựa chọn có được bỏ qua hay không

Một event có schema lạ hoặc payload không hợp lệ có thể khiến consumer không xử lý được. Các lựa chọn:

1. **Dừng partition và alert** nếu event bắt buộc để giữ tính đúng đắn.
2. **Quarantine/DLQ** với event ID, position, error class và payload reference an toàn.
3. **Sửa upcaster rồi replay** cùng vị trí.
4. **Repair từ source lookup** nếu projection chỉ cần current state và việc đọc lại đủ thông tin.
5. **Skip có chủ đích**, chỉ khi data contract cho phép thiếu event và có nhãn kết quả incomplete.

Không dùng `catch(Exception) {commitOffset();}` cho dữ liệu quan trọng. Với delta streams, bỏ version 7 rồi áp version 8 có thể khiến số liệu sai.

**DLQ chỉ cho biết còn công việc chưa giải**, không tự làm projection đầy đủ. Kỳ báo cáo không được gắn nhãn FINAL nếu DLQ còn ảnh hưởng phạm vi cần chốt.

## 21. Blue–green rebuild: dựng projection mới song song

Không nên xóa trực tiếp search index đang phục vụ hàng nghìn người rồi dựng lại từ đầu.

~~~text
orders_search_v1    <- current read traffic
orders_search_v2    <- rebuild workers

Rebuild v2:
  snapshot/backfill
  replay CDC to catch up
  compare/reconcile
  switch alias/routing
  continue live updates to v2
  keep v1 temporarily for rollback
~~~

Ví dụ routing logic:

~~~text
orders_search_current -> orders_search_v1
orders_search_next    -> orders_search_v2

After validation:
orders_search_current -> orders_search_v2
~~~

Ưu điểm:

- Live read path tiếp tục dùng bản đã biết hoạt động.
- Job có thể dừng/retry mà không phá v1.
- Shadow-compare hai projection ở cùng cutoff.
- Rollback routing khi v2 lỗi mà v1 vẫn được update.

Đổi lại: cần đủ storage cho hai phiên bản, double processing trong một số giai đoạn, và kế hoạch alias/switch phù hợp engine.

Việc đổi alias có thể atomic theo khả năng sản phẩm nhưng **không tự biến toàn hệ phân tán thành atomic**: clients có cache/cursor, background jobs hoặc readers dùng tên index cố định có thể còn thấy v1.

## 22. Khi nào in-place rebuild chấp nhận được?

Một projection nhỏ có thể clear rồi tạo lại nếu:

- Có planned downtime hoặc API trả REBUILDING.
- Dữ liệu nhỏ và rebuild thời gian được dự đoán bằng kiểm thử.
- Không có consumers khác giả định kết quả luôn đầy đủ.
- Có cách rollback, checkpoint và idempotent replay.
- Không có business invariant phụ thuộc projection trong thời gian đó.

Với projection lớn, in-place rất rủi ro:

~~~text
Delete derived collection.
Backfill 20%.
Admin API queries incomplete data as if complete.
~~~

Nếu vẫn làm in-place, cần **khóa đường phục vụ hoặc công bố incomplete status/watermark**. Không để dashboard “tổng doanh thu toàn kỳ” trả số mới bằng 20% dữ liệu mà không có cảnh báo.

## 23. Cutover: điều kiện chuyển read traffic

Một quy trình:

1. v2 đã chứa đầy đủ snapshot/backfill trong phạm vi.
2. CDC đã replay từ handoff checkpoint tới watermark mục tiêu.
3. Không còn gaps/DLQ ảnh hưởng phạm vi bắt buộc.
4. Counts/sums/fingerprints khớp nguồn theo **cùng cutoff**.
5. Query semantics, tenant scope, auth và latency được kiểm chứng.
6. Clients/cursors/API tương thích schema mới.
7. Sau switch, v2 vẫn nhận live changes.
8. Router/alias được đổi theo khả năng engine.
9. Theo dõi divergence, lag, p95/p99 và errors sau cutover.
10. v1 được giữ đủ lâu cho rollback theo policy.

**Lag=0 không đủ để chứng minh đúng:** consumer có thể bỏ 100 poison events rồi vẫn đuổi kịp log head. Cần **data reconciliation**, không chỉ offsets.

### 23.1. Watermark và cutover là hai khái niệm khác nhau

Watermark mô tả dữ liệu đã được xử lý đến mốc nào theo một contract. Cutover là **quyết định phục vụ người dùng bằng projection nào**. Một projection có thể catch up hoàn toàn nhưng chưa đúng quyền truy cập/aggregations; không nên tự cutover chỉ vì watermark đã tăng.

## 24. Rollback projection không phải rollback transactions

Nếu v2 có bug, chuyển traffic về v1 chỉ an toàn nếu:

- v1 còn hoạt động và nhận đủ changes.
- Không có schema-breaking clients cần v2-only response.
- Caches/cursors có generation để không trộn dữ liệu.
- Các writes nghiệp vụ ở source vẫn được giữ nguyên.
- Có runbook bắt lại v2/v3 từ checkpoint hợp lệ.
- Phát hiện lỗi và quyết định rollback trước khi xóa v1.

Một rebuild thất bại thường cần **rebuild projection v3 hoặc sửa transform**, không sửa lại lịch sử business source tùy tiện.

## 25. Rebuild metadata và audit trail

Một record quản trị:

~~~json
{
  "rebuildId": "orders-search-v2-20261114",
  "projection": "orders_search_v2",
  "source": "orders-service",
  "scope": {"tenant": "t01", "from": "2025-01-01T00:00:00Z"},
  "algorithmVersion": "search-transform-2.3",
  "schemaVersion": 2,
  "snapshotId": "snapshot-20261114-01",
  "startingSourcePosition": {"p0": "12345", "p1": "9912"},
  "state": "RUNNING",
  "createdAt": "2026-11-14T10:00:00Z"
}
~~~

Nên lưu:

- Ai yêu cầu/phê duyệt và phạm vi tenant.
- Source retention, checkpoint/snapshot ID.
- Code/reducer/schema version và immutable build hash.
- Throttle/concurrency policy, capacity budget.
- Số events processed, skipped, duplicate, retry, quarantined.
- Tiến độ/checkpoints và completeness/watermark.
- Reconciliation result, cutover time, rollback decision.
- Chi phí/ảnh hưởng OLTP trong thời gian chạy.

**Metadata là bằng chứng tiến trình**, không thay data quality verification.

## 26. Partial rebuild: sửa đúng vùng bị ảnh hưởng

Không phải mọi lỗi đều cần replay hàng tỷ events.

Ví dụ:

- Tính sai doanh thu một SKU trong 3 ngày: rebuild facts và aggregates ảnh hưởng.
- Search mapping đổi cho mọi products: có thể reindex toàn bộ.
- Một shard projection thiếu keys: repair vùng keys/partitions thiếu.
- Tenant migration: rebuild một tenant với cutoff riêng.
- Một ranking model đổi weights: có thể rebuild feature/rankings chứ không cần copy raw events mới.

Partial rebuild cần **dependency closure**: sửa SKU-B có thể ảnh hưởng ranking top-20 của các SKU khác; sửa revenue event phải cập nhật cả daily/monthly aggregates liên quan. Nếu một entity thuộc nhiều denormalized views, phải rebuild tất cả views bị ảnh hưởng để không lệch.

Lưu scope và xác minh phạm vi còn lại; mục tiêu không phải replay ít nhất có thể bằng mọi giá, mà **replay đủ để projection đúng theo contract**.

## 27. Replay một event log khác với quét source

**Replay từ log** thuận tiện khi cần chuyển trạng thái theo events, có thể seek offset và giữ ordering. Nhưng còn phụ thuộc retention và tính đầy đủ.

**Quét source hiện tại** thuận tiện khi chỉ cần current-state projection, nhưng có rủi ro:

- Scan tốn read capacity/CPU/I/O.
- Các writes xảy ra trong lúc scan tạo kết quả không đồng nhất.
- Không có lịch sử sự kiện đã mất.
- Pagination/continuation token có thể không tương đương snapshot.
- Tombstones/TTL/deleted records khó phục hồi nếu chỉ nhìn current state.
- Source scale và partition distribution có thể làm một số shards nóng hơn.

Trong thực tế, **snapshot + CDC** thường kết hợp hai lợi thế: bootstrap state hiện tại, rồi đuổi theo thay đổi mới. Nhưng phải có mốc giao nhau, versioning và reconciliation rõ ràng.

## 28. Tại sao replay phải kiểm soát tốc độ?

Nguồn NoSQL còn đang phục vụ người dùng. Một rebuild không giới hạn có thể tạo thêm hàng chục nghìn lượt scan và index writes mỗi giây, chiếm CPU, disk I/O, memory, network, connections hoặc write capacity của cụm. Kết quả: API checkout vượt p99 SLO dù rebuild chỉ đọc giao dịch đã xảy ra.

Cần giới hạn **source reads/s, bytes/s, CDC polling, sink writes/s, số requests đang chạy, retries và fan-out**. Một tham số `maxWorkers` không bảo vệ được tất cả: mỗi worker có thể phát hàng trăm operations, và item sizes khác nhau rất lớn.

## 29. Rate limit, concurrency limit và deadline khác nhau

| Giới hạn | Bảo vệ | Không tự bảo vệ |
|---|---|---|
| 500 events/s | Tốc độ nhận events | Kích thước/fan-out khác nhau |
| 50 MiB/s | Bandwidth | CPU xử lý từng event |
| 8 DB requests in-flight | Concurrency | QPS nếu mỗi call rất ngắn |
| 5% retry budget | Lượng retry phụ thêm | Một retry có thể đắt |
| 2 seconds/request | Thời gian một attempt | Tổng CPU trong 2 giây |
| 4 workers/partition | Parallelism | Ordering nếu cùng key bị ghi đồng thời |

Kết hợp **rate + concurrency + timeouts** để ngăn số việc khởi động, số việc chạy đồng thời và thời gian giữ tài nguyên.

Với hệ ổn định, Little's Law:

\[
L=\lambda W.
\]

Nếu trung bình 1.000 writes/s, mỗi write tồn tại 20 ms, lượng in-flight trung bình gần `1.000 × 0,02 = 20`. Đây không phải đảm bảo p99 hay đúng bằng số connections: queueing, bursts và retries làm tình hình khác.

## 30. Token bucket: một cơ chế rate limit

Một token bucket có capacity `B`, refill rate `r` tokens/s; operation tiêu `c` tokens. Khi thiếu tokens, worker phải đợi có cancellation hoặc từ chối/tạm pause. Bucket cho phép burst tích lũy tối đa B.

Ví dụ:

~~~text
Source request tokens:
  rate = 500 GETs/s
  burst capacity = 1000 GETs

Source byte tokens:
  rate = 20 MiB/s
  burst capacity = 40 MiB
~~~

Một source read có thể phải vượt qua **cả hai quota**. Với DynamoDB, cost token có thể phản ánh consumed read capacity; với search index, cần tính writes phát sinh từ một event.

Pseudocode:

~~~text
while running:
    if source or sink unhealthy:
        reduce rate / pause for cooldown
    else if tokens and concurrency slot available:
        read bounded batch
        apply idempotently
        checkpoint only after durable write
    else:
        wait with cancellation
~~~

Không advance offset chỉ để giải phóng queue khi sink chưa xử lý xong.

## 31. Giới hạn đa chiều: một event có thể tạo nhiều writes

Một Order event có thể tạo một search update, bốn line-item facts, hai aggregates và một activity record: **8 sink operations cho một source event**.

Vì vậy cần đo source GET/s, bytes scanned, events parsed/s, CPU transform, sink writes/s, write capacity, event fan-out, retry attempts, throttling, in-flight calls và queue bytes. Giới hạn 1.000 events/s không đủ nếu mỗi event nở thành 8.000 writes/s.

## 32. Batching: tối ưu overhead nhưng không tạo spike

Batch nhỏ quá gây nhiều round trips; lớn quá tiêu RAM, giữ connection lâu, vượt payload limit, tạo indexing burst, tăng retry cost và làm checkpoint chậm.

Dùng đồng thời:

~~~text
maxRecordsPerBatch
maxBytesPerBatch
maxBatchBuildTime
maxConcurrentBatches
maxSourceRate
maxSinkRate
~~~

Một batch 10 items vẫn có thể chứa item 100 MiB; vì thế **bytes và số records** đều cần upper bound.

Nếu một batch 100 events thành công 99 và 1 failed, cần retry failed item hoặc replay toàn batch **idempotently**; không commit offset qua event lỗi nếu điều đó làm sai reducer. Sink báo accepted chưa chắc đồng nghĩa data đã durable/visible theo mọi API.

## 33. Backpressure: sink chậm thì poller phải giảm

Giả sử nguồn đưa vào 10.000 events/s nhưng sink chỉ xử lý 3.000/s. Nếu poller không dừng, queue tăng 7.000/s, tức **25,2 triệu events sau một giờ**.

~~~mermaid
flowchart LR
    L["Durable log"] --> P["Bounded poller"]
    P --> Q["Bounded queue"]
    Q --> W["Workers giới hạn"]
    W --> S["Projection sink"]
    S -. "Throttling / latency" .-> W
    W -. "Pause / reduce intake" .-> P
~~~

Khi queue gần đầy:

- Pause polling theo connector/broker protocol.
- Giữ checkpoint ở vị trí đã được áp bền, không chỉ đã poll.
- Đợi slot/tokens có cancellation.
- Không drop events bắt buộc để giảm memory.
- Alert nếu source retention có nguy cơ hết trước khi consumer bắt kịp.
- Nếu mất log gap, chuyển sang repair/snapshot recovery.

**Backpressure ngăn overload, không làm backlog tự biến mất**. Muốn backlog giảm cần processing capacity thực sự lớn hơn arrival rate.

## 34. Tính thời gian bắt kịp backlog

Giả sử source liên tục phát:

\[
\lambda_{\mathrm{live}}=1.000\ \mathrm{events/s}.
\]

Consumer rebuild có thể xử lý an toàn tổng cộng:

\[
\mu_{\mathrm{rebuild}}=4.000\ \mathrm{events/s}.
\]

Nếu backlog ban đầu `B=12.000.000` events, tốc độ giảm backlog khi arrival ổn định:

\[
\mu_{\mathrm{rebuild}}-\lambda_{\mathrm{live}}
=3.000\ \mathrm{events/s}.
\]

\[
T_{\mathrm{catchup}}\approx
\frac{12.000.000}{3.000}=4.000\ \mathrm{s}
\approx66{,}7\ \mathrm{phút}.
\]

Không tính `12 triệu / 4.000` vì **trong lúc replay còn có events mới đến**. Mô hình bỏ qua retry, stall, backfill overhead và rate thay đổi.

Nếu `\mu_{\mathrm{rebuild}}\leq\lambda_{\mathrm{live}}`, backlog không thể về 0 trong điều kiện ổn định. Tăng thời gian chờ không giúp; cần thêm capacity an toàn, tối ưu reducer, thay cách bootstrap hoặc thương lượng mức chậm chấp nhận.

### 34.1. Live và rebuild có nguồn capacity riêng

Một live consumer v1 và rebuild v2 có thể dùng broker chung nhưng sink khác. Không nên cộng nhầm throughput của v1 vào năng lực v2. Phải đo **effective apply throughput của projection v2**, cùng giới hạn broker/source/network và stream changes mà v2 phải xử lý.

## 35. Adaptive throttling theo tình trạng OLTP

Một rate replay cố định 2.000 reads/s có thể an toàn vào ban đêm nhưng gây hại khi peak transactions hoặc một node lỗi. Có thể điều chỉnh dựa trên:

- Transaction API p95/p99 và error rate.
- NoSQL source CPU, disk queue, read capacity/throttling.
- Replica/CDC lag, source log retention headroom.
- Hot partition và read pool wait.
- Sink write p99, indexing queue, compaction pressure.
- Replay retry amplification và queue depth.

Policy khái niệm:

~~~text
if OLTP latency exceeds warning threshold:
    lower rebuild rate gradually
    hold reduction for cooldown period
else if source and sink healthy for several windows:
    increase rebuild rate slowly up to hard maximum

if hard source safety limit exceeded:
    pause rebuild intake, preserve checkpoints
~~~

Các ngưỡng phải do team đặt dựa trên load tests. Dùng **hysteresis, cooldown và smoothing** để tránh mỗi worker đồng loạt tăng rồi giảm rate liên tục.

Không tăng tốc chỉ vì lag lớn nếu source đang overload; sẽ làm source chậm hơn.

## 36. Ưu tiên nguồn giao dịch và phân phối công bằng

Với NoSQL source phục vụ nhiều tenants/shards, limiter toàn cluster có thể không đủ. 1000 reads/s chỉ tới **một hot partition** vẫn nguy hiểm dù tổng cluster còn nhiều capacity.

Các tầng điều tiết:

1. Global cap bảo vệ tổng cluster.
2. Per-node/partition cap bảo vệ hot owner.
3. Per-tenant cap tránh noisy neighbor.
4. Per-job cap tránh một rebuild chiếm hết budget.
5. Retry cap bảo vệ khi lỗi.
6. Concurrency cap chặn số requests dài đồng thời.
7. Dynamic cap theo health metrics.

Nếu có nhiều rebuild jobs, dùng weighted-fair scheduling để một job lớn không bỏ đói job nhỏ quan trọng. Nhưng priority lanes phải có quotas/cost tracking: một high-priority report không nên được quyền quét primary vô hạn.

## 37. Java: skeleton bộ giới hạn concurrency và rate

Một ví dụ minh họa Java 17 dùng `Semaphore` để giới hạn số sink writes đang chạy. Giới hạn QPS ở đây biểu diễn bằng interface `TokenPermit`; implementation có thể là token bucket hoặc dịch vụ rate limiter.

~~~java
import java.time.Duration;
import java.util.concurrent.Semaphore;

public final class BoundedReplay {
    public interface TokenPermit {
        void acquire(long costUnits, Duration waitCap)
                throws InterruptedException;
    }

    public interface ProjectionWriter {
        void applyIdempotently(Event event) throws Exception;
    }

    public record Event(
        String eventId,
        String aggregateId,
        long version,
        byte[] payload
    ) {}

    private final Semaphore inFlight;
    private final TokenPermit sourceOrSinkRate;
    private final ProjectionWriter writer;

    public BoundedReplay(
            int maxConcurrentWrites,
            TokenPermit sourceOrSinkRate,
            ProjectionWriter writer) {
        if (maxConcurrentWrites < 1) {
            throw new IllegalArgumentException("maxConcurrentWrites");
        }
        this.inFlight = new Semaphore(maxConcurrentWrites);
        this.sourceOrSinkRate = sourceOrSinkRate;
        this.writer = writer;
    }

    public void process(Event event) throws Exception {
        // Cost=1 chỉ minh họa. Production cần bytes/WCU...
        sourceOrSinkRate.acquire(1L, Duration.ofSeconds(2));
        inFlight.acquire();
        try {
            writer.applyIdempotently(event);
        } finally {
            inFlight.release();
        }
    }
}
~~~

**Giới hạn:** nếu gọi `process` tuần tự từ một luồng, semaphore không tự tạo parallelism. Khi dùng nhiều workers, cần bảo đảm per-aggregate ordering, checkpointing sau durable apply, timeout/cancel và trả permit đúng trong mọi exception. Nếu acquire token rồi không lấy được slot, quota có thể bị lãng phí; một scheduler production cần chính sách cấp budget và queue phù hợp.

Mã trên chỉ giới thiệu hai loại giới hạn. **Không được coi nó là một consumer hoàn chỉnh**: chưa có source offset management, DLQ, retry policy, dedup ledger hay transactional projection commit.

## 38. Java: event version guard với thao tác điều kiện

Một sink abstraction có thể cung cấp:

~~~java
public interface VersionedProjectionStore {
    // Atomic: update only when stored version is lower.
    // Return false for stale/duplicate events.
    boolean upsertIfNewer(
            String aggregateId,
            long incomingVersion,
            byte[] canonicalView
    ) throws Exception;
}
~~~

Ý tưởng handler:

~~~java
public final class StateProjectionConsumer {
    private final VersionedProjectionStore store;

    public StateProjectionConsumer(VersionedProjectionStore store) {
        this.store = store;
    }

    public void onFullStateEvent(BoundedReplay.Event event)
            throws Exception {
        store.upsertIfNewer(
            event.aggregateId(),
            event.version(),
            event.payload()
        );
        // Advance offset only after the conditional write
        // has committed according to sink semantics.
    }
}
~~~

Chỉ dùng khi payload là **đầy đủ state của projection** và source version đúng. Nếu event là `IncrementRevenue(+100)`, không được bỏ v7 rồi áp v8 như full snapshot. Cần reducer tuần tự, dedup event ID và xử lý gap.

### 38.1. Implementation ở sink

Một số lựa chọn tùy sản phẩm:

- MongoDB: conditional update/replace theo filter chứa `version < incoming` hoặc insert/upsert theo protocol, xử lý race/unique constraint.
- DynamoDB: conditional write `attribute_not_exists(version) OR version < :incoming` trong phạm vi item.
- Cassandra/ScyllaDB: cân nhắc LWT/CAS nếu thật sự cần conditional overwrite theo semantics driver/CL.
- Search index: external versioning/optimistic concurrency control nếu engine và write API hỗ trợ.
- Redis: atomic compare/version qua script/transaction đúng key/slot semantics.

Không dịch cơ học một điều kiện SQL sang mọi NoSQL engine; mỗi engine có syntax, retry/error và atomicity boundary riêng.

## 39. Điều khiển pause/resume phải bảo toàn progress

Một operator có thể nhấn PAUSE khi OLTP p99 tăng. Cần định nghĩa điều gì xảy ra với:

- Các events đã poll nhưng còn trong queue.
- Sink writes đang in-flight.
- Batch một phần đã commit.
- Offset trong memory chưa persisted.
- Temporary files/artifacts đang ghi.
- Distributed leases/locks.
- Worker đang retry/backoff.
- Jobs ở nhiều nodes khác nhau.

Một state machine:

~~~mermaid
flowchart TD
    Q["QUEUED"] --> R["RUNNING"]
    R --> P["PAUSE_REQUESTED"]
    P --> D["DRAIN_INFLIGHT"]
    D --> S["PAUSED / durable checkpoint"]
    S --> R
    R --> F["FAILED_RETRYABLE"]
    F --> R
    R --> C["COMPLETED / validated"]
    S --> X["CANCELLED"]
~~~

**PAUSED không đồng nghĩa checkpoint đã an toàn** nếu còn uncommitted batch chỉ tồn tại trong RAM. Có thể chờ drain, hoặc cho worker từ bỏ batch rồi replay trên resume. Cả hai đều hợp lệ nếu idempotency và checkpoint đúng.

## 40. Throttle source scans khác throttle CDC replay

**Snapshot/backfill scan** trực tiếp tranh read CPU/IOPS/RCU ở nguồn. Rate limiter nên gắn vào source reads/bytes và nóng theo partition.

**CDC replay từ broker archive** chủ yếu tiêu broker egress, transform CPU và sink writes. Source có thể ít bị ảnh hưởng trực tiếp hơn, nhưng vẫn có shared log connectors, network, retention hoặc APIs để bổ sung dữ liệu.

| Giai đoạn | Tài nguyên thường cần bảo vệ |
|---|---|
| Export source snapshot | DB read units, CPU/disk, network, snapshot retention |
| Download snapshot files | Object storage egress, workers/network |
| Parse/transform | CPU, memory, file descriptors |
| Consume historical log | Broker read throughput/retention |
| Write new projection | Sink writes/compaction/indexing |
| Catch-up recent changes | Sink + broker + possible source lookups |
| Reconciliation source lookups | DB reads, per-tenant/partition quotas |

Mỗi giai đoạn có thể cần rate profile khác. Đừng lấy limiter index writes làm bằng chứng rằng snapshot read không gây tải.

## 41. Retry và exponential backoff có jitter

Transient errors có thể retry: connection reset, throttling, leader switch, timeout có contract retry được. Nhưng:

- Đừng retry validation/schema error vô hạn.
- Đừng reset rebuild job deadline mỗi lần thử.
- Đừng cho SDK auto retry và application retry nhân cấp số lần gọi.
- Đừng retry một side effect nghiệp vụ không idempotent.
- Giữ event ID/aggregate ID qua các attempts.
- Đảm bảo checkpoint vẫn phản ánh durable apply.
- Dùng backoff có jitter, giới hạn attempts, time budget và global retry tokens.

Ví dụ:

~~~text
Event evt-1001 write sink fails transiently.

attempt1 -> transient failure
wait 70 ms (jitter)
attempt2 -> throttle
wait 180 ms (jitter)
attempt3 -> success, then advance checkpoint

If budget exhausted -> pause/quarantine/alert.
~~~

Một retry được phép bởi client library **không chứng minh** nó đúng theo business semantics. Nếu trạng thái write sau timeout UNKNOWN, sink idempotency/version guard phải chống double effect.

## 42. Stop condition theo tài nguyên và correctness

Một rebuild nên tự giảm tốc hoặc dừng khi:

- Source transaction p99 vượt safety threshold.
- DB throttling/CPU/disk pressure tăng ngoài mức cho phép.
- CDC source retention headroom xuống thấp.
- Sink rate-limited liên tục, backlog tăng không thể kiểm soát.
- Queue/memory vượt hard bound.
- Lỗi schema/poison events vượt ngưỡng cho phép.
- Data validation divergence tăng.
- Tenant/privacy policy phát hiện vi phạm.
- Operator yêu cầu cancel hoặc maintenance window kết thúc.

Quy tắc dừng phải đi cùng **lý do, checkpoint cuối bền, tác động lên projected freshness và cách resume**. Không xóa dữ liệu v2 đang xây khi pause trừ khi có yêu cầu cleanup riêng.

## 43. Rate plan theo giai đoạn

Một kế hoạch minh họa cho build v2:

| Giai đoạn | Mục tiêu | Giới hạn |
|---|---|---|
| Bootstrap | Đọc snapshot lịch sử | Source read cap + per-shard limit |
| Bulk load | Đưa snapshot vào sink | Sink bytes/s + worker concurrency |
| Catch-up | Replay CDC từ checkpoint | Broker poll cap + sink write cap |
| Validation | So với source theo cutoff | Bounded sampling/scan |
| Cutover | Chuyển readers | Không tăng nguồn read đột ngột |
| Stabilization | Theo dõi v2 live | Normal consumer policy |
| Cleanup | Xóa v1/artifacts cũ | Storage/retention/access policy |

Tốc độ tối ưu ở bulk load có thể khác catch-up. Ví dụ bulk load có thể hưởng lợi từ một index ingest mode, còn live consumer cần latency thấp; thay đổi các mode này phụ thuộc engine và cần hiểu recovery/visibility semantics.

## 44. MongoDB: change streams, resume token và rebuild collection

Với MongoDB, change streams cho phép theo dõi thay đổi theo khả năng và điều kiện triển khai. Một flow cho projection:

~~~text
MongoDB source collection
  -> snapshot/export for bootstrap
  -> change stream with resume position
  -> transformer
  -> reporting collection v2 / search index v2
~~~

Cần phân biệt:

- **Resume token** phục vụ tiếp tục stream theo contract, không thay một archive lịch sử vô hạn.
- Khả năng resume phụ thuộc oplog/history retention và topology.
- Change stream event payload có thể chứa full document theo tùy chọn/cấu hình nhất định; không mặc định mọi operation đều có snapshot đầy đủ.
- Nếu nguồn thay đổi khi scan, phải có cách handoff snapshot/stream nhất quán.
- Drop/rename collection, invalidate event hoặc topology events có thể cần xử lý riêng tùy driver.
- Replay vào MongoDB sink nên dùng conditional version update/unique document key để idempotent.
- Index build/aggregation trên source có thể làm OLTP chậm; muốn report nặng nên dùng cluster/projection tách biệt.

Ví dụ **logic** upsert theo version trong sink, không phải lệnh nguyên xi cho mọi schema:

~~~javascript
db.orders_projection_v2.updateOne(
  {
    _id: "O1001",
    sourceVersion: { $lt: 8 }
  },
  {
    $set: {
      status: "CONFIRMED",
      sourceVersion: 8,
      projectionSchema: 2
    }
  }
);
~~~

**Lưu ý:** đoạn này chỉ khớp khi record đã tồn tại với version nhỏ hơn. Record chưa tồn tại, tombstone, unique key và các workers đồng thời cần **nhánh insert/upsert/transaction hoặc protocol tương ứng**; không coi ví dụ là handler đầy đủ. Với sharded collection, còn phải thiết kế đúng shard key và phạm vi atomicity.

## 45. DynamoDB: snapshot/export, Streams và bản sao dẫn xuất

Với DynamoDB, một số lựa chọn phục vụ rebuild tùy chức năng và cấu hình:

- Export/snapshot table tới S3 hoặc quét source có kiểm soát.
- DynamoDB Streams để nhận changes gần đây theo retention và stream view type.
- Event archive/outbox ở nơi bền hơn nếu cần lịch sử lâu năm.
- Ghi projection ở table/search/warehouse khác.
- Conditional writes theo version/idempotency để tránh ghi lùi.

Một mô hình:

~~~text
DynamoDB Orders source
  -> snapshot/export at compatible point
  -> stream/archive changes after checkpoint
  -> process by item identity/version
  -> reporting sink with conditional update
~~~

Quan trọng:

1. **Streams retention có giới hạn**, không mặc định đủ cho months-long replay.
2. Export snapshot và stream checkpoint cần handoff đúng contract; không suy chúng có global atomic cutoff chỉ vì cùng timestamp.
3. GSI có eventual/update semantics riêng; không đồng nhất with full history log.
4. Một parallel scan trực tiếp trên production source có thể tiêu consumed read capacity, ảnh hưởng transaction.
5. Condition check failure do incoming version cũ có thể là duplicate/stale event, không phải transient error cần retry vô hạn.
6. Mỗi tenant/partition nóng cần throttle riêng.

Ví dụ điều kiện cho một **bản full-state projection** có authoritative version, ở mức khái niệm:

~~~text
Put item if no stored version or stored version < incoming version.
On duplicate:
  do not increment aggregate again.
On old version:
  skip after confirming source ordering semantics.
On gap in delta event:
  stop/buffer/reconcile.
~~~

API cụ thể và semantics condition/transaction phụ thuộc SDK, table design và sink.

## 46. Cassandra/ScyllaDB: CDC không phải một API phổ quát

Họ Cassandra/ScyllaDB có mô hình phân vùng rộng và có những cách CDC khác nhau tùy sản phẩm, phiên bản, connector và cấu hình. Không được giả định “bật CDC là tự có một event store đầy đủ để replay từ ngày đầu”.

Cần xác định:

- Capture changes từ commitlog/cơ chế CDC cụ thể ra sao?
- Có records bị thiếu khi connector xuống lâu không?
- Retention và storage capacity của CDC artifacts?
- Partition-key routing và consistency level của source/sink?
- Updates/tombstones/TTL được biểu diễn thế nào?
- Số lần capture có thể trùng; có event ID/version đủ cho dedup?
- Cần quét source qua token ranges để bootstrap không?
- Backfill có gây tombstone scans/compaction pressure không?

Một query đúng partition key có thể hiệu quả, nhưng full-table reprocessing vẫn là workload lớn. Có thể scan theo token ranges/buckets với per-node quotas, rồi đưa dữ liệu sang read model/analytics store khác. Nếu source không hỗ trợ replay lịch sử đủ tin cậy, dùng **application outbox/event log** ngay từ lúc thiết kế hoặc phục hồi từ snapshot/facts được giữ bền.

## 47. Redis: không dùng cache notifications như durable replay log

Redis có thể là **đích dữ liệu dẫn xuất**: hot product views, leaderboards hoặc counters. Nếu cache bị flush, source/outbox/stream khác phải đủ để làm mới nếu muốn gọi là cache tái tạo được.

Không mặc định keyspace notifications là một event log durable đáp ứng replay sau outage. Notifications dạng pub/sub có thể bị mất khi consumer offline; TTL expiry/failover không thay một lịch sử được lưu bền.

Một cache rebuild có thể:

~~~text
Durable source / event archive
  -> bounded backfill
  -> Redis keys with generation prefix + TTL
  -> health/coverage checks
  -> switch application cache namespace
~~~

Ví dụ namespace:

~~~text
hot-products:g1:t01:SKU-A
hot-products:g2:t01:SKU-A

Before cutover:
  readers use generation g1
Rebuild:
  fill g2 with selected hot keys
After cutover:
  readers use g2, retire g1 by TTL
~~~

Không prewarm toàn bộ database vào Redis nếu working set nhỏ; bảo vệ source reads và Redis memory/eviction. Không dùng cached stock để xác nhận giữ hàng cuối cùng.

## 48. Search index: reindex, alias và độ trễ hiển thị

Một search engine thường có:

- Write/indexing acknowledgment.
- Refresh/visibility behavior khác với thời điểm accepted.
- Bulk indexing API và per-item failures.
- Index mappings/analyzers cần thay bằng index generation mới.
- Alias/routing cho blue–green cutover nếu engine hỗ trợ.
- Shard/hot routing, heap/indexing queue và merge pressure.

Một kế hoạch:

~~~text
orders_v1 -> serves traffic
orders_v2 -> receives backfill
orders_v2 -> catches up CDC
orders_v2 -> refresh/validate visibility
alias switch: orders_current -> orders_v2
orders_v1 retained for rollback
~~~

Không chỉ đo “bulk accepted 100%” rồi cutover; cần kiểm tra **search results visibility, sample queries, delete handling, tenant filters và document count theo cùng cutoff**. Bulk response có thể thành công một phần; handler phải xử lý từng item.

Nếu search dùng một source record tạo nhiều index documents, phải có stable document IDs để replay không tạo duplicates.

## 49. Nhiều sink cùng nhận event: không chia checkpoint bừa

Một event có thể cập nhật:

~~~text
Order event E
  -> search index
  -> reporting facts
  -> recommendation features
  -> cache invalidation
~~~

Các consumers có logic, tốc độ, phiên bản và error handling khác nhau. Một event apply thành công vào Search không có nghĩa Reporting/Feature Store đã đúng.

Một thiết kế:

- Separate consumer groups/checkpoints cho mỗi projection.
- Versioned transformations riêng.
- Per-sink lag/watermark và DLQ.
- Source retention/archive đủ cho consumer chậm nhất nếu cần.
- Cost/fan-out budget khi replay nhiều projections đồng thời.
- Có thể pause consumer không critical mà không chặn transaction, theo durability contract.

Nếu muốn một event được áp đồng thời vào nhiều sinks như **một transaction nguyên tử**, đó là yêu cầu khó hơn, thường cần protocol/reconciliation thay vì giả định broker ACK sẽ giải quyết.

## 50. Bảo mật, tenant và dữ liệu đã bị xóa

Replay từ archive cũ có thể tái tạo dữ liệu mà hệ nguồn đã xóa vì quyền riêng tư hoặc retention policy. Rebuild phải tuân thủ:

1. Tenant isolation của source, event archive và sink.
2. Quyền operator được phép truy cập payload lịch sử.
3. Encryption, secret management và access logging.
4. PII masking/redaction trong dữ liệu dẫn xuất.
5. Deletion/tombstone propagation kể cả khi snapshot cũ chứa dữ liệu.
6. Data retention/consent hoặc legal holds theo chính sách áp dụng.
7. Không lưu raw event payload nhạy cảm trong DLQ/log plaintext.
8. Artifact exports/index backups cũng phải theo retention.
9. Khi rebuild một tenant, không kéo nhầm records khác qua partition scan.
10. Kiểm tra search filters/row-level authorization trước cutover.

**Một rebuild “đầy đủ” về mặt kỹ thuật có thể vi phạm pháp lý/bảo mật nếu nó hồi sinh dữ liệu không còn được phép giữ.** Tính đúng của projection gồm cả quy tắc xóa và phạm vi truy cập.

## 51. Metrics: progress, throughput, lag và correctness

Một dashboard chỉ hiển thị `eventsProcessed/s` không đủ: job có thể chạy nhanh nhưng bỏ poison events hoặc làm source quá tải.

| Metric | Câu hỏi |
|---|---|
| Source records/s, bytes/s | Đọc nguồn nhanh cỡ nào? |
| Sink writes/s, applied records/s | Tiến độ ghi đích thực |
| Backlog count, oldest unprocessed event age | Còn cách head bao xa? |
| Per-partition durable checkpoint | Có thể resume từ đâu? |
| Snapshot keys/pages done | Backfill bao nhiêu? |
| Duplicate/skipped events | Replay có xử lý trùng hoặc bỏ dữ liệu? |
| Out-of-order/gap count | Thứ tự/sequence có đúng? |
| Retry, DLQ và schema errors | Phần nào đang lỗi? |
| Missing IDs/totals/fingerprints | Projection khớp nguồn? |
| Watermark per source/scope | Có thể công bố dữ liệu đến đâu? |
| OLTP p95/p99, throttling, pool wait | Rebuild có hại nguồn giao dịch? |
| Sink p99, queue, compaction | Đích có quá tải? |
| Worker CPU/RAM, in-flight, queue bytes | Có nguy cơ OOM? |
| Cost/read units/egress | Đang tiêu bao nhiêu? |
| PII/privacy violations | Có vượt quyền hoặc hồi sinh dữ liệu đã xóa? |

**Lag count khác lag time:** hai partitions cùng còn 10.000 events nhưng event cũ nhất có thể là 3 giờ hoặc 2 giây trước. Theo dõi cả counts, tuổi events và watermark.

ETA theo net drain rate là một **ước lượng có điều kiện**, không phải lời hứa.

## 52. Reconciliation theo cùng cutoff

Chọn một cutoff C có semantics rõ:

~~~text
Source confirmed IDs at cutoff C:
  O1, O2, O3, O4

Projection v2 IDs at cutoff C:
  O1, O2, O4

Missing: O3
Unexpected: none
~~~

Các phép đối soát:

- Counts theo tenant/ngày/partition.
- Unique IDs và source versions.
- Hash/fingerprint các fields quan trọng.
- Sums amounts/quantities theo business definition.
- Tombstone/delete coverage.
- Status transitions hợp lệ.
- Các queries trọng yếu so giữa v1/v2/source.
- DLQ/gaps trong phạm vi cần công bố.
- Tenant filters, masking và permissions.

Nếu source đã có O5 sau C mà v2 chưa có, không được gán lỗi “missing” khi chúng không cùng cutoff. Nếu O3 trước C bị bỏ, lag=0 không cứu được dữ liệu.

### 52.1. Sampling vs full reconciliation

- Full key compare có coverage mạnh hơn nhưng tốn nguồn.
- Sampling giúp canary nhanh nhưng có thể bỏ lỗi hiếm.
- Chunked checksums giảm dữ liệu truyền nhưng cần normalization và hiểu giả định hash collision.
- Aggregates có thể khớp dù một vài IDs bị mất/bị thừa.
- Với kỳ tài chính chốt, mức validation có thể cần nghiêm ngặt hơn dashboard tạm thời.

Reconciliation cũng là **workload đọc nguồn** và phải được throttle.

## 53. Fault injection: chứng minh restart an toàn

Chỉ thử trong môi trường được phép:

~~~text
T0: Start rebuild from snapshot S.
T1: Apply event E.
T2: Kill worker after sink commit, before checkpoint.
T3: Restart and reread E.
T4: Verify idempotent effect.
T5: Inject sink throttling.
T6: Verify poller backpressure and bounded memory.
T7: Pause with in-flight batch.
T8: Resume from durable checkpoint.
T9: Inject out-of-order event and delete.
T10: Reconcile at cutoff C.
~~~

Acceptance criteria:

1. Không mất event effect sau crash.
2. Duplicate không double-count.
3. Checkpoint không vượt durable applied position.
4. Full-state event cũ không ghi lùi version mới.
5. Delta gap được phát hiện.
6. Tombstone không bị snapshot cũ hồi sinh.
7. Throttling giảm intake, không làm queue vô hạn.
8. Pause/resume giữ ordering.
9. OLTP p99 còn trong safety budget.
10. Log gap hoặc retention exhausted tạo lỗi/recovery path rõ.
11. Tenant/privacy scope đúng.
12. Có thể rollback routing nếu v2 không đạt contract.

Không kill production nodes tùy tiện để diễn tập nếu chưa có quy trình cho phép và kiểm soát rủi ro.

## 54. Bài tập A — Bootstrap snapshot và CDC

Snapshot S:

~~~text
O1 v4 CONFIRMED
O2 v7 PENDING
O3 v2 CONFIRMED

CDC sau S:
O1 v5 REFUNDED
O4 v1 CREATED
O2 v8 CONFIRMED
O3 v3 DELETED
~~~

Hãy:

1. Tạo projection ban đầu từ S.
2. Thiết kế sourceVersion/idempotency cho mỗi record.
3. Replay CDC đúng thứ tự per Order.
4. Xác định state cuối của O1, O2, O3, O4.
5. Xử lý O1 v5 đến hai lần.
6. Tránh O2 v7 snapshot ghi đè O2 v8.
7. Tránh O3 tombstone bị snapshot cũ hồi sinh.
8. Nếu mất offset, cần nguồn/handoff nào để phục hồi?
9. Định nghĩa cutoff để đối soát CONFIRMED count.
10. Viết report progress/duplicates/errors/watermark.

Với full-state versioned events đúng protocol: O1 REFUNDED v5, O2 CONFIRMED v8, O3 deleted v3, O4 CREATED v1. Với delta events cần reducer và gap handling, không được nhảy thẳng lên version cao hơn.

## 55. Bài tập B — Tính quota và thời gian catch-up

~~~text
Live events:               1.500/s
Backlog at start:       9.000.000
Sink processing cap:        6.000 events/s
Source replay cap:          4.500 events/s
Worker pool cap:             32 concurrent calls
~~~

Hãy:

1. Xác định upper-bound throughput khi source cap nhỏ hơn sink cap.
2. Tính net backlog drain rate.
3. Tính ETA nếu mọi tốc độ không đổi.
4. Nếu peak khiến replay cap giảm còn 2.000/s, net drain còn bao nhiêu?
5. Arrival tăng lên 2.500/s thì chuyện gì xảy ra?
6. Nếu mỗi event tạo 3 writes trung bình, sink QPS cần tính lại thế nào?
7. Khi p99 event size 1 MiB, tại sao event/s chưa đủ?
8. Chọn token bucket burst capacity và giải thích trade-off.
9. Thêm per-tenant quotas vào thiết kế.
10. Vì sao không tăng workers vô hạn khi lag lớn?

Đây là mô hình số học có giả định. Effective rate có thể thấp hơn do retries, fan-out, CPU và shared resource contention.

## 56. Bài tập C — Crash giữa write và checkpoint

~~~text
Offset=100: event E100
Consumer applies +100 to dailyRevenue
Worker crashes
Checkpoint remains at offset=99
Restart reads E100 again
~~~

Hãy:

1. Vì sao tổng có thể bị cộng hai lần?
2. Thiết kế eventId ledger với uniqueness.
3. Đề xuất transaction ghi ledger + aggregate nếu sink hỗ trợ.
4. Nếu không có multi-record transaction, dùng immutable facts và aggregate lại thế nào?
5. Sink ACK timeout nhưng commit đã xảy ra: retry ra sao?
6. Khi nào có thể checkpoint offset=100?
7. Nếu E101 đến trước E100 trong cùng aggregate, xử lý gì?
8. Nếu E100 payload sai schema, DLQ có đủ chưa?
9. Viết test restart lặp nhiều lần, kiểm tra không double-count.
10. Metric nào bắt được checkpoint tiến nhanh hơn facts thực áp?

## 57. Bài tập D — Bảo vệ OLTP khi rebuild search index

Một hệ NoSQL đang có:

~~~text
OLTP checkout p99 SLO:             300 ms
Baseline checkout p99:             180 ms
Source read capacity usable:   12.000 operations/s
Transaction read load:           8.000 operations/s

Rebuild job:
  wants 20.000 source reads/s
  emits 3 sink writes/source read
  has 48 worker threads
~~~

Hãy:

1. Giải thích vì sao chạy thẳng ở 20.000 reads/s có thể gây overload.
2. Đặt source read budget có headroom thay vì lấy toàn bộ “capacity còn trống”.
3. Giới hạn sink writes/s theo fan-out.
4. Chọn per-partition rate và worker concurrency cap.
5. Thiết kế giảm tốc khi checkout p99 vượt warning threshold.
6. Khi source node failover, rebuild nên pause hay tiếp tục?
7. Nếu replay backlog tăng trong giờ peak, ưu tiên hành động nào?
8. Thiết kế snapshot/CDC handoff để không mất update mới.
9. Chọn tiêu chí cutover của index v2.
10. Nếu v2 query latency xấu hơn v1 sau switch, rollback thế nào?
11. Cần metric nào để bảo đảm không ghi lại dữ liệu đã xóa do privacy policy?
12. Nếu report source read quota không cho catch up, có thể thay bootstrap strategy ra sao?

Thành công không phải đạt tốc độ rebuild cao nhất, mà là **projection hoàn chỉnh với correctness và chi phí chấp nhận, trong khi checkout vẫn đạt SLO**.

## 58. Runbook: khi replay gây timeout hoặc dữ liệu v2 sai

Giả sử sự cố:

~~~text
Checkout p99:          180 ms -> 950 ms
Source read throttle:  0.2% -> 18%
Rebuild scan QPS:      0 -> 16.000
Sink batch retry:      1.1 -> 3.8 attempts/item
CDC oldest lag:        2 min -> 45 min
~~~

Quy trình:

1. **Xác định scope:** source table/shard, tenants, replay job/version nào?
2. **Bảo vệ giao dịch trước:** giảm/pause replay source reads, không hạ consistency để cứu throughput.
3. **Giữ checkpoint:** stop intake hoặc drain in-flight an toàn; không commit offsets trước durable apply.
4. **Giảm retry storm:** xem SDK/application retries và backoff/jitter.
5. **Điều tra điểm nghẽn:** source IOPS/CPU, pool waits, hot partitions, sink indexing backlog, broker egress.
6. **Kiểm tra data correctness:** mismatch có phải do cutoff khác nhau, schema bug, duplicate hay gap?
7. **Cách ly projection lỗi:** không cutover; nếu đã cutover thì rollback routing khi v1 còn hợp lệ.
8. **Xử lý poison/DLQ:** sửa decoder/transform, replay từ checkpoint đúng; không skip âm thầm.
9. **Xác định retention headroom:** nếu CDC sắp hết log, cần giải pháp snapshot/archive, không chỉ retry nhanh hơn.
10. **Khôi phục dần:** tăng rate theo metrics và cooldown, không mở max workers ngay.
11. **Reconcile theo cutoff:** key counts, versions, sums và tombstones.
12. **Ghi lại incident:** root cause, data impact, checkpoint, công việc phục hồi và controls mới.

Cần phân biệt **mitigation ngắn hạn** (pause, limiter, giảm concurrency) với **sửa thiết kế** (chuyển snapshot load sang cluster riêng, cải thiện event retention, idempotent sink hoặc data model). Đừng chỉ nâng timeout và hy vọng rebuild sẽ tự hoàn thành.

### 58.1. Khi source retention hết trước khi catch up

Nếu earliest CDC position đã vượt checkpoint của consumer:

- Dừng tuyên bố projection complete.
- Đánh dấu gap và phạm vi ảnh hưởng.
- Tìm archived log/fact store có đủ thông tin.
- Nếu current-state projection, tạo snapshot mới và bootstrap lại bằng handoff hợp lệ.
- Nếu history-based projection cần các events đã mất, xác định có thể khôi phục từ nguồn nào; nếu không, báo limitation rõ.
- Không tự reset offset sang “latest” rồi coi mọi dữ liệu trước đó đã được xử lý.

Đây là tình huống **mất khả năng replay**, không phải chỉ một transient timeout.

## 59. Những hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao sai | Cách làm đúng |
|---|---|---|
| “CDC lưu toàn bộ lịch sử” | Có retention/capture scope | Archive hoặc snapshot+CDC |
| “Replay là phát lại business side effects” | Có thể double charge/email/hold | Chỉ apply read model, giữ idempotency |
| “Reset offset là rebuild xong” | Có thể thiếu dữ liệu trước retention | Kiểm tra earliest available position |
| “Scan xong rồi bật CDC” | Có window mất updates | Snapshot/stream handoff |
| “Event ID unique không cần validate” | Producer có thể lỗi/va chạm | Contract + dedup constraints |
| “Broker exactly-once đủ cho mọi sink” | External DB boundary khác | Idempotent apply và checkpoint |
| “Event version lớn hơn thì bỏ hết version nhỏ” | Delta cần intermediate effects | Phân biệt full state và delta |
| “Timestamp sắp thứ tự mọi events” | Clock skew/partition order | Per-aggregate version/causality |
| “Write succeeded rồi checkpoint sớm” | Có thể sink chưa durable/visible | Ack semantics rõ |
| “Commit offset trước ghi giúp nhanh” | Mất effect sau crash | Apply rồi checkpoint |
| “DLQ là đã xử lý dữ liệu” | Vẫn còn events bị lỗi | Repair/replay/mark incomplete |
| “Delete record là đủ, không cần tombstone” | Snapshot cũ có thể hồi sinh | Versioned deletion |
| “Chỉ cần so document count” | Dữ liệu có thể sai/trùng | IDs, versions, sums, cutoff |
| “Lag=0 nghĩa đúng” | Có thể skip events | Reconciliation |
| “Backfill vào index live sẽ ổn” | Reader có thể thấy dữ liệu 20% | Blue–green hoặc explicit unavailable |
| “Alias switch sửa hết client caches” | Nhiều tầng có state | Generation/invalidation plan |
| “Thêm workers luôn nhanh hơn” | Ordering, throttle, contention | Rate+concurrency đo được |
| “Giới hạn event/s là đủ” | Sizes/fan-out thay đổi | Bytes/s, writes/s, read units |
| “Limit concurrency thay rate limit” | Calls ngắn vẫn tạo QPS cao | Dùng cả hai |
| “Batch càng lớn càng tốt” | RAM/spike/partial failure | Bounded records+bytes |
| “Queue đầy thì drop event cho nhanh” | Gây incomplete projection | Backpressure/durable backlog |
| “Rate cố định an toàn mọi thời điểm” | OLTP tải thay đổi | Adaptive safe throttle |
| “Đợi lâu hơn sẽ bắt kịp backlog” | Net drain rate có thể ≤ 0 | Tăng safe capacity/đổi chiến lược |
| “Broker lag chỉ là chuyện consumer” | Retention có thể mất khả năng replay | Theo dõi oldest age/headroom |
| “Source snapshot luôn globally consistent” | Engine có giới hạn snapshot | Giao thức handoff cụ thể |
| “Analytics có thể đọc mọi tenant khi rebuild” | Privacy và tenant isolation | RBAC/scope/audit |
| “Archive cũ luôn được phép replay” | Có thể chứa dữ liệu đã xóa | Respect deletion/retention |
| “Rollback projection nghĩa rollback orders” | Dữ liệu nghiệp vụ đã commit | Rollback read routing, không sửa source |
| “Thao tác chưa có dữ liệu dùng latest offset” | Có thể bỏ toàn bộ lịch sử cần thiết | Bootstrap đầy đủ trước |

## 60. Câu hỏi tự kiểm tra

1. Replay và rebuild khác nhau về khái niệm thế nào?
2. Derived data có thể gồm những loại nào?
3. Tại sao CDC khác event sourcing?
4. Outbox giúp giải quyết vấn đề tích hợp ở ranh giới nào?
5. Một log retention ngắn có tác động gì lên replay lịch sử?
6. Khi nào current-state snapshot đủ cho projection?
7. Khi nào cần event history thay vì latest document?
8. Vì sao snapshot và CDC phải có handoff checkpoint?
9. Nếu update xảy ra giữa snapshot scan và CDC subscription, nguy cơ gì?
10. Full-state event và delta event khác nhau khi đến sai thứ tự thế nào?
11. Event ID, aggregate version và event schema version có vai trò gì?
12. Checkpoint nên được ghi trước hay sau durable projection apply?
13. Vì sao at-least-once delivery cần idempotent sink?
14. Crash sau sink write nhưng trước checkpoint gây gì?
15. Một aggregate revenue increment có idempotent không nếu thiếu ledger?
16. Khi replay OrderConfirmed, có được gọi payment provider lại không?
17. Per-aggregate order khác global order ra sao?
18. Tombstone giúp ngăn điều gì?
19. TTL expiry có luôn tạo CDC delete event không?
20. Schema upcaster cần xử lý event cũ như thế nào?
21. Poison event cần được quarantine ra sao?
22. DLQ còn event lỗi có ảnh hưởng nhãn FINAL không?
23. Blue–green rebuild khác in-place rebuild như thế nào?
24. Cutover phải kiểm tra những điều kiện nào ngoài lag=0?
25. Rollback read routing có thay đổi transaction source không?
26. Partial rebuild phải xét dependency closure vì sao?
27. Rate limiting và concurrency limiting khác nhau gì?
28. Token bucket có hai tham số chính nào?
29. Vì sao event count/s không đủ để bảo vệ sink?
30. Tại sao batch cần giới hạn cả records và bytes?
31. Backpressure phải làm gì khi queue đầy?
32. Cần điều kiện gì để backlog giảm?
33. Vì sao live event arrival phải trừ khỏi catch-up throughput?
34. Adaptive throttling dựa trên các tín hiệu nào?
35. Khi OLTP p99 tăng, tăng replay workers có phù hợp không?
36. Pause request với in-flight batches nên xử lý ra sao?
37. Mong muốn source scan rate khác CDC replay rate ở đâu?
38. Per-tenant/partition throttle giúp tránh điều gì?
39. MongoDB resume token có thay thế long-term event archive không?
40. DynamoDB Streams có được mặc định giữ lịch sử vĩnh viễn không?
41. Redis keyspace notification có là durable event log không?
42. Search bulk write accepted đã chắc user query thấy dữ liệu mới chưa?
43. Vì sao cần checkpoint riêng cho Search và Reporting?
44. Reconciliation phải cùng cutoff để tránh vấn đề gì?
45. Khi nguồn CDC retention hết, phải phản hồi thế nào?

## 61. Tổng kết: đúng dữ liệu trước, tốc độ theo ngân sách sau

**Replay** cho phép xử lý lại dữ liệu/sự kiện đã tồn tại; **rebuild** tạo một trạng thái dẫn xuất mới từ nguồn đáng tin cậy. Trong kiến trúc NoSQL có CDC, hai việc này cần được thiết kế như một **quy trình dữ liệu có checkpoint, version, quyền truy cập và safety budget**, không phải một script quét tất cả rồi ghi thật nhanh.

Trình tự thực hành:

~~~text
1. Xác định projection, nguồn dữ liệu và lịch sử thực sự cần.
2. Phân biệt event store, CDC retention, snapshot và archive.
3. Xây snapshot+stream handoff không tạo gap.
4. Thiết kế eventId, version, schema upcasting, tombstone.
5. Áp projection idempotently; checkpoint sau durable apply.
6. Giữ per-aggregate order và xử lý delta gaps.
7. Dựng v2 trong namespace riêng nếu cần phục vụ live liên tục.
8. Giới hạn source reads, sink writes, bytes/s, in-flight và retries.
9. Backpressure, pause/resume và adaptive throttle theo OLTP health.
10. Theo dõi backlog net drain, retention headroom, DLQ và watermark.
11. Reconcile dữ liệu theo cùng cutoff và kiểm tra quyền/deletion.
12. Cutover có kiểm soát, giữ rollback path, dọn bản cũ theo retention.
~~~

Một rebuild thành công phải đáp ứng **ba điều kiện cùng lúc**: dữ liệu dẫn xuất **đúng và đủ**, hệ thống **phục hồi được sau crash/retry**, và tốc độ xử lý **không làm nguồn giao dịch vượt giới hạn an toàn**. Ưu tiên correctness, điều tiết tải theo khả năng thực tế và lưu bằng chứng đối soát giúp việc replay trở thành thao tác vận hành đáng tin cậy thay vì một nguy cơ đối với production.









