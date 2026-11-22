# Khôi phục tính nhất quán giữa nhiều nguồn dữ liệu trong microservices

## 1. Vấn đề: hệ thống khởi động lại chưa có nghĩa dữ liệu đã đúng

Trong một hệ thống microservices, dữ liệu của một nghiệp vụ thường xuất hiện ở nhiều nơi: PostgreSQL lưu giao dịch đơn hàng, Kafka giữ sự kiện, Elasticsearch phục vụ tìm kiếm, Redis giữ cache, object storage giữ hóa đơn, một dịch vụ thanh toán bên ngoài giữ trạng thái giao dịch và một kho phân tích nhận dữ liệu qua CDC hoặc ETL. Mỗi nơi có cơ chế backup, replication, retention và điểm khôi phục khác nhau.

Sau một sự cố mất vùng hạ tầng, xóa nhầm bảng, hỏng cluster hoặc triển khai migration sai, nhóm vận hành có thể restore từng thành phần thành công nhưng nghiệp vụ vẫn sai:

- Database Orders trở về 10:00, trong khi Kafka còn các event tới 10:12.
- Consumer offset được phục hồi ở 10:12 nhưng projection database chỉ có dữ liệu tới 10:00: 12 phút sự kiện có thể bị bỏ qua.
- Kafka đã phát `OrderPaid`, nhưng Orders DB được restore trước lúc ghi nhận thanh toán.
- Elasticsearch còn document của order đã bị rollback khỏi database.
- Cache chứa giá và quyền truy cập cũ, trái với trạng thái database đã restore.
- Payment provider đã thu tiền thật, trong khi internal ledger không còn bản ghi tương ứng.
- Object storage còn file hóa đơn nhưng metadata trỏ tới file đã bị xóa hoặc đổi version.

**Disaster recovery (DR) thành công không chỉ là đưa các process lên trạng thái Running.** Kết quả cần là một trạng thái có thể giải thích được, các **invariant nghiệp vụ** được giữ hoặc được khôi phục có kiểm soát, không mất dữ liệu quá giới hạn và không nhân đôi side effect khi replay.

Bài học tập trung vào **cross-source consistency recovery**: cách chọn nguồn dữ liệu có thẩm quyền, xác định recovery cut, phối hợp restore, replay, rebuild projection, reconciliation và mở lại traffic một cách an toàn.

### Mục tiêu học tập

Sau bài này, bạn có thể:
1. Phân biệt restore availability với restore consistency, RPO với RTO và physical với logical consistency.
2. Lập dependency map cho database, broker, cache, search, object storage và hệ thống bên ngoài.
3. Xác định source of truth theo nghiệp vụ thay vì giả định có một nguồn duy nhất cho toàn hệ thống.
4. Chọn recovery point/cut dựa trên timeline, log position và trạng thái đã xác nhận.
5. Hiểu vì sao DB transaction, CDC log và Kafka offset không tự tạo một global transaction.
6. Thiết kế cơ chế outbox/inbox, idempotency, versioning và replay an toàn.
7. Lập runbook cô lập ghi, restore theo thứ tự, đối soát và mở dịch vụ trở lại.
8. Kiểm tra các invariant như thanh toán không trùng, tồn kho không âm và thứ tự trạng thái.
9. Xây thử nghiệm DR định kỳ chứng minh cả khả năng phục vụ và tính đúng đắn của dữ liệu.

## 2. Sơ đồ nhiều nguồn dữ liệu trong một nghiệp vụ

Xét luồng đặt hàng:

```text
                Client / Gateway
                       |
                       v
                   Order Service
                       |
             +---------+---------+
             |                   |
             v                   v
       Orders PostgreSQL      Transactional Outbox
             |                   |
             |                   v
             |             CDC / Relay
             |                   |
             |                   v
             |                Kafka
             |              /    |    \
             v             v     v     v
      Order Query API   Search  Stock  Analytics
                         |       |
                         v       v
                    OpenSearch  Inventory DB

             Payment Service ----> Payment Provider
                   |
                   v
              Payments DB
                   |
                   v
             Object Storage
             (receipts/files)

       Redis caches, IAM, DNS, secrets and backups
       sit around this flow.
```

Trong ví dụ, một lần checkout có thể để lại:
- **Order record** trong Orders DB.
- **Outbox event** trong cùng transaction với order.
- **Kafka record** đã được relay phát.
- **Search document** hoặc read projection từ consumer.
- **Inventory reservation** trong Inventory DB.
- **Payment authorization/capture** ở provider bên ngoài.
- **Payment ledger** trong Payments DB.
- **Receipt object** trong object storage và metadata tham chiếu.
- **Cache entry** tại Redis.

Khi phục hồi, các bản sao có thể ở những thời điểm khác nhau. Nếu chỉ cố đưa tất cả hệ thống về cùng một chuỗi thời gian đồng hồ như “10:05:00”, ta có thể vẫn sai vì network delay, commit times khác nhau, các producer phát event chậm và độ trễ replication.

Vì vậy cần xác định **quan hệ nhân quả và nguồn gốc giao dịch**, không chỉ so timestamp.

## 3. Ba tầng nhất quán phải phân biệt

### 3.1 Physical consistency

Dữ liệu trên disk có cấu trúc nội bộ hợp lệ để database hoặc broker đọc được. PostgreSQL recovery có thể dùng WAL để đưa một instance về trạng thái transaction nhất quán theo cơ chế của nó. Một snapshot block storage được lấy sai cách có thể không tự bảo đảm tính nhất quán ứng dụng nếu không phối hợp với database.

**Physical recovery của từng hệ** là điều kiện cần, nhưng chưa đủ để bảo đảm những quan hệ nghiệp vụ xuyên nhiều hệ.

### 3.2 Logical/data consistency

Các dữ liệu có quan hệ với nhau không mâu thuẫn theo hợp đồng:
- Payment ledger của order đã xác nhận có giao dịch tương ứng.
- Inventory không vừa báo bán hàng đã trừ vừa ghi reservation vẫn active không đúng.
- Một event được consumer áp dụng đúng số lần về mặt side effect.
- Search projection phản ánh phiên bản dữ liệu nguồn hoặc lag trong giới hạn cho phép.

Logical consistency có thể cần **reconciliation và correction**, không chỉ restore backup.

### 3.3 Business consistency

Những bất biến nghiệp vụ được giữ:
- Không thu tiền hai lần cho một operation.
- Không hoàn tất đơn nếu payment chưa được xác nhận theo quy trình.
- Tổng ledger debit/credit cân đối trong phạm vi transaction cần cân bằng.
- Không phát hành hai hóa đơn chính thức cho cùng một sự kiện nếu luật nghiệp vụ không cho phép.
- Trạng thái workflow đi theo state machine và compensation hợp lệ.

Một hệ thống có thể **physically consistent, logically inconsistent, và business-invalid** cùng lúc: DB đều khởi động thành công nhưng hai hệ ghi nhận khác nhau về một khoản tiền.

### 3.4 Strong, eventual và bounded consistency

- **Strong consistency** trong phạm vi một DB/transaction được hệ thống hỗ trợ không tự mở rộng sang các service khác.
- **Eventual consistency** cho phép bản sao/projection chậm hơn trong khoảng thời gian, với điều kiện cuối cùng hội tụ nếu không có thay đổi mới và cơ chế truyền đạt hoạt động đúng.
- **Bounded staleness** quy định độ trễ chấp nhận được, chẳng hạn search index phải bắt kịp source trong 60 giây theo SLO.
- **Causal/order constraints** quy định tác động A phải đứng trước B, ví dụ `OrderCreated` trước `OrderPaid` trong state machine.

Khi DR, phải tuyên bố rõ **mục tiêu nhất quán tại từng bước**. Không nên chờ mọi cache và search index đạt trạng thái giống DB trước khi cho phép mọi chức năng, nếu cache có thể xóa và search được phục hồi dần; nhưng không thể mở chức năng thu tiền khi ledger/idempotency chưa nhất quán.

## 4. RPO, RTO và điểm phục hồi: các mục tiêu khác nhau

| Thuật ngữ | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **RPO – Recovery Point Objective** | Mức mất dữ liệu tối đa có thể chấp nhận tính từ thời điểm sự cố? | Mất tối đa 5 phút commit đã xác nhận |
| **RTO – Recovery Time Objective** | Cần khôi phục chức năng trong bao lâu? | Checkout quay lại chế độ cho phép giao dịch trong 30 phút |
| **Recovery point** | Tập dữ liệu/log nào thực tế đã restore tới? | Orders WAL tới LSN cụ thể |
| **Consistency cut** | Ranh giới trạng thái nào được xem là nhất quán xuyên các nguồn? | Mọi nghiệp vụ tới watermark W đã có đủ bằng chứng |
| **Reconciliation window** | Khoảng thời gian cần đối soát sau khi các nguồn lệch nhau? | 10:00–10:15 |
| **Catch-up time** | Thời gian replay/rebuild projection sau restore | 25 phút xử lý backlog |

RTO cần tính **đưa dịch vụ về trạng thái nghiệp vụ được phép**, không chỉ “pod chạy” hoặc “database accepting connections”. Nếu DB restore trong 10 phút nhưng phải mất 3 giờ để đối soát thanh toán trước khi mở checkout, RTO thực của checkout có thể gần 3 giờ.

RPO phải xét dữ liệu đã **acknowledge/commit** cho người dùng. Một bản backup hàng giờ không đủ để hứa RPO 5 phút nếu không có WAL/replication hoặc cơ chế durability bổ sung. Các dịch vụ khác nhau có thể có RPO khác nhau theo criticality, nhưng cần kiểm tra các RPO có tương thích với nhau không.

Ví dụ:
- Orders DB: RPO 5 phút.
- Kafka: log còn tối thiểu 24 giờ và replication theo thiết kế.
- Elasticsearch: có thể rebuild từ nguồn, RPO logical gần 0 nếu source và log còn đủ.
- Redis cache: có thể xóa và làm ấm lại.
- Payment provider: không thể rollback cùng tổ chức; cần xác nhận trạng thái thực tế.

Những mô hình này phải được xác thực bằng backup restore drill, retention thực và contract của provider.

## 5. Một “source of truth” cho mọi thứ thường không tồn tại

Trong hệ phân tán, quyền xác nhận sự thật thường **theo domain và loại dữ liệu**:

| Thông tin | Nguồn có thẩm quyền có thể là | Bản sao/dữ liệu dẫn xuất |
| --- | --- | --- |
| Order workflow state | Orders DB/event log có quy tắc sở hữu rõ | Search, cache, analytics |
| Inventory availability | Inventory DB và reservation ledger | Cache tồn kho, catalog |
| Settlement thực tế | Payment provider/bank ledger và internal payment ledger đối soát | Order status, dashboard |
| User identity/roles | Identity service theo policy | JWT claims/cached permissions trong thời hạn |
| Object contents | Versioned object storage và checksum | Search metadata, CDN cache |
| Audit transaction | Durable append-only audit log theo chính sách | Operational dashboard |
| Customer preferences | Service sở hữu dữ liệu người dùng | Recommendation profile projection |

Không thể kết luận “Kafka luôn là truth” hoặc “PostgreSQL luôn là truth”. Kafka có thể chỉ giữ events trong retention ngắn; DB có thể chứa aggregate state mới hơn log vì relay chưa publish; một bên ngoài như Payment provider có thể đã hoàn tất giao dịch chưa ghi vào nội bộ.

Một recovery plan phải trả lời:
1. Ai sở hữu quyết định cuối cùng cho từng business fact?
2. Facts nào bất biến và có thể đối soát từ bên ngoài?
3. Facts nào là projection có thể rebuild?
4. Facts nào là transient cache có thể hủy?
5. Có retention/legal hold nào ngăn việc xóa hoặc thay data?
6. Khi hai nguồn mâu thuẫn, rule và owner nào giải quyết?

**Không chọn nguồn có timestamp mới nhất làm truth mặc định.** Timestamp có thể sai do clock skew, replication lag, replay và sự kiện đến ngoài thứ tự.

## 6. Recovery consistency graph: xác định mối quan hệ thực tế

Dựng đồ thị dependency giữa các **data stores và luồng sao chép**, không chỉ giữa service HTTP.

```text
Orders DB ──Outbox──> Kafka orders.events
  |                         |
  |                         +──> Search Projection
  |                         +──> Analytics
  |                         +──> Notification
  |
  +──> Query API / cache

Payments DB ──Outbox──> Kafka payments.events
  |                         |
  +──> Provider API          +──> Orders payment state

Inventory DB ──Outbox──> Kafka stock.events
  |
  +──> Reservations

Object Storage ←── Receipt writer / metadata DB
```

Với mỗi cạnh, ghi:
- Direction: source → sink.
- Kiểu: transaction, CDC, outbox relay, API, event, batch import.
- Identity: event ID, operation ID, aggregate ID, tenant, trace ID.
- Ordering key và version/sequence.
- Offset/watermark/log position nếu có.
- Durability, retention, checkpoint và replay mechanism.
- At-least-once/at-most-once semantics, deduplication.
- Các giao dịch bên ngoài không thể rollback.
- Owner, runbook, reconciliation query và SLO catch-up.

Đồ thị giúp trả lời “restore X trước hay Y trước?” và “nguồn nào dùng để rebuild?” thay vì cố restore mọi thành phần độc lập rồi mới phát hiện mâu thuẫn.

## 7. Consistency cut là gì?

Trong một database đơn, ta có thể chọn mốc log recovery. Trong nhiều nguồn không có global transaction, **không có một thời điểm đồng hồ duy nhất luôn tương đương trạng thái nhất quán**.

Một consistency cut là tập các mốc/điều kiện cho phép tái dựng một trạng thái không vi phạm ràng buộc nhân quả và nghiệp vụ đã định nghĩa.

Ví dụ:

```text
Order DB WAL:        ... LSN A ---- LSN B ---- LSN C
Outbox table:        ... O100 ---- O101 ----- O102
Kafka orders topic:  ... K520 ---- K521 ----- K522
Search consumer:     ... C517 ---- C518 ----- C519

Business transaction Tx42:
  - Order row committed at LSN B
  - Outbox O101 committed in same DB transaction
  - Kafka K521 published later
  - Search projection updated later at C519
```

Nếu Orders DB được restore trước LSN B nhưng Kafka vẫn giữ K521, event có thể mô tả một order không tồn tại trong database nguồn đã restore. Nếu Orders DB được restore tới LSN B nhưng search chỉ tới C517, search lag có thể được giải quyết bằng rebuild/replay.

Để chọn cut:
1. Xác định các **committed business facts** phải bảo tồn hoặc phải được đối soát.
2. Ánh xạ facts tới transaction IDs/log positions/outbox event IDs.
3. Xác định downstream watermark thực sự đã xử lý bền vững, không chỉ đã fetch.
4. Chọn tập recovery points bảo toàn các phụ thuộc nhân quả hoặc ghi rõ cửa sổ phải reconcile.
5. Không dùng offset Kafka và LSN database như thể chúng thuộc cùng một trục số.
6. Khi không thể tạo consistent snapshot đa nguồn, dùng **restore + deterministic replay + reconciliation**.

Consistency cut thường là **logic**, thể hiện bằng manifest và bằng chứng, không phải một flag của hạ tầng.

## 8. Backup phối hợp và restore manifest

Khi lập kế hoạch DR, nên tạo metadata cho các bản backup:

```yaml
recovery_manifest:
  incident_id: "dr-2026-11-12-example"
  recovery_target: "pre-corruption boundary"
  orders:
    backup_id: "orders-base-20261112-0800"
    wal_replay_target: "recorded-LSN-or-timestamp"
    schema_version: "orders-schema-37"
  payments:
    backup_id: "payments-base-20261112-0800"
    wal_replay_target: "recorded-LSN-or-timestamp"
    schema_version: "payments-schema-22"
  kafka:
    cluster_snapshot_ref: "kafka-snapshot-ref"
    topics:
      - "orders.events"
      - "payments.events"
    partition_offsets:
      note: "capture per topic/partition with provenance"
  object_storage:
    inventory_ref: "versioned-object-manifest"
    checksum_catalog: "sha256-manifest"
  projections:
    search:
      strategy: "rebuild-from-orders-source"
  validation:
    expected_invariants:
      - "no-double-capture"
      - "orders-reference-valid-payments"
      - "inventory-reservations-reconciled"
```

Đây là **schema minh họa** cho hồ sơ quyết định, không phải file cấu hình được PostgreSQL/Kafka hiểu trực tiếp. Một manifest thực phải chứa references bất biến và quyền truy cập phù hợp, không lưu credentials.

Các trường nên có:
- Thời điểm backup bắt đầu/kết thúc và quá trình ghi đang hoạt động ra sao.
- LSN/GTID/SCN/log positions, transaction IDs hoặc watermark theo DBMS.
- Snapshot type: application-consistent, crash-consistent hay logical dump.
- Offset/partition và metadata version của broker nếu phù hợp.
- Schema version, migration revision, producer/consumer code versions.
- Object IDs, versions, ETags/checksums và quy tắc retention.
- Key/certificate requirements để decrypt dữ liệu.
- Checksum và bằng chứng restore test gần nhất.
- RPO/RTO expected và kết quả thực tế sau DR.

**Một bản backup tồn tại không chứng minh restore thành công.** Cần kiểm tra integrity, quyền decrypt, compatibility và khả năng replay dưới phiên bản ứng dụng được dùng.

## 9. Xác định cửa sổ mất mát và sai lệch

Một sự cố lúc 10:15, các nguồn có recovery points:

| Thành phần | Recovery point | Ý nghĩa ban đầu |
| --- | --- | --- |
| Orders DB | 10:05 | Có thể mất commit đã ack trong 10 phút |
| Payments DB | 10:07 | Có thể lệch Orders 2 phút |
| Kafka orders.events | 10:14 | Chứa events có thể mới hơn Orders DB |
| Kafka payments.events | 10:12 | Chứa events trước thời điểm sự cố |
| Search index | 10:11 | Dẫn xuất có thể chứa order không còn trong restored DB |
| Object storage | Versioned tới 10:15 | File còn nhưng metadata có thể mất |
| Payment provider | trạng thái live | Không đi theo internal rollback |

Không thể chỉ so sánh các con số rồi kết luận thứ tự. Ta phải xây **reconciliation window** dựa trên các sự kiện thực và điểm chốt đã xác nhận.

Ví dụ khung điều tra:
1. Xác định những operation IDs được trả thành công cho client từ 10:05–10:15.
2. Truy outbox/event log để tìm events của những operation đó.
3. Đối chiếu orders/payment/inventory state ở nguồn có thẩm quyền.
4. Phân biệt “đã commit”, “đã gửi nhưng chưa ack”, “đã xử lý bên ngoài nhưng chưa lưu nội bộ”.
5. Chọn hướng khôi phục từng trường hợp: replay, reconstruct, compensate, refund hoặc manual review.
6. Lập danh sách các facts không đủ bằng chứng, không tự phán đoán là thất bại hay thành công.

Các hệ thống giao dịch tài chính cần thêm ledger đối ứng và chứng từ đối soát theo yêu cầu nghiệp vụ/quy định; không nên tự ý ghi đè trạng thái thanh toán chỉ vì restore DB nội bộ.

## 10. Thứ tự khôi phục: ưu tiên nguồn có thẩm quyền rồi dữ liệu dẫn xuất

Một trình tự phổ biến, phải điều chỉnh theo dependency graph:

```text
Declare incident / preserve evidence
             |
             v
Fence writes and prevent duplicate leaders
             |
             v
Recover identity, network, secrets, storage basics
             |
             v
Restore source-of-truth databases + audit/event logs
             |
             v
Reconcile durable business facts / external side effects
             |
             v
Restore or rebuild outbox/inbox/CDC/consumers
             |
             v
Rebuild search/materialized views, clear stale caches
             |
             v
Verify invariants and end-to-end flows
             |
             v
Open read-only traffic -> limited write -> full traffic
             |
             v
Monitor lag, reconciliation, anomalies and close incident
```

Trong thực tế, một số hệ phải phục hồi Kafka trước DB để có dữ liệu replay, một số cần restore identity infrastructure để truy cập backup, và một số phải khôi phục database schema trước khi chạy CDC. Trình tự này là **mẫu phụ thuộc logic**, không phải thứ tự công cụ cố định.

Điều quan trọng nhất là **không cho phép writer/consumer chưa được kiểm soát tiếp tục tạo tác dụng phụ trong khi trạng thái đang được tái dựng**.

## 11. Fencing và cô lập writes trước khi restore

Một rủi ro DR nghiêm trọng là **split brain**: primary region cũ chưa thực sự dừng, trong khi secondary region mới nhận ghi; hoặc một consumer cũ tiếp tục chạy trên dữ liệu trước restore. Hai nơi có thể phát event và tạo payment requests cạnh tranh.

Biện pháp:
- Xác định incident commander và một người chịu trách nhiệm cho trạng thái write-enabled.
- Dừng/cô lập các writer cần thiết; hạn chế API mutation nhưng có thể giữ read-only.
- Fencing primary cũ bằng cơ chế quản trị hạ tầng được kiểm chứng; DNS change một mình có thể không ngăn worker cũ tiếp tục chạy.
- Dừng outbox relays/CDC connectors và consumer có side effects, hoặc chuyển chúng sang trạng thái kiểm soát.
- Khóa hoặc hạn chế scheduled jobs có khả năng phát lệnh thanh toán, xuất hàng, gửi email.
- Cố định routing, epoch/generation token hoặc leader lease nếu hệ thống hỗ trợ.
- Ghi chính xác thời điểm chuyển quyền và danh sách instance còn active.

**Không mở lại write traffic chỉ vì secondary đã Ready.** Trước tiên phải xác nhận primary cũ không thể tiếp tục tạo commit cạnh tranh, nếu không quá trình reconciliation có thể không bao giờ hội tụ.

Với hệ multi-region active-active, logic phức tạp hơn: cần cơ chế conflict resolution được thiết kế từ trước theo data type, causal metadata và domain. Không có một thủ thuật restore nào tự bảo đảm mọi active-active conflict là hợp lệ.

## 12. PostgreSQL PITR và ranh giới transaction

PostgreSQL có cơ chế backup và Point-In-Time Recovery (PITR) dựa trên base backup và WAL. Khi cấu hình đầy đủ, hệ thống có thể replay WAL tới target. Việc chọn target dùng timestamp, transaction ID, LSN hoặc restore point theo tính năng/phiên bản cần được xác minh.

Các điểm cần hiểu:
- WAL đảm bảo tính toàn vẹn transaction **trong PostgreSQL instance/cluster theo cơ chế của PostgreSQL**; không bao gồm transaction của Kafka hay provider API.
- Base backup và WAL archives phải đủ, không thiếu đoạn log, và phải giải mã được.
- Chọn restore target không đồng nghĩa có thể hoàn tác side effects ngoài database.
- Schema tại recovery point có thể khác version ứng dụng đang deploy.
- Logical dump không có cùng semantics với physical backup/WAL.
- Restore vào một môi trường cô lập trước khi thay production giúp bảo toàn bằng chứng và giảm sai sót.

Ví dụ khái niệm:

```text
Base backup 08:00
  + WAL 08:00 ... 10:05
  → restore Orders DB to agreed target

Then:
  verify schema version
  verify committed order facts
  inspect outbox rows and replay boundary
  reconcile external operations after target
```

**Không giả định thời điểm trên hai database PostgreSQL khác nhau tạo atomic cross-database snapshot.** Nếu Orders và Payments tách cluster, mỗi cluster có WAL và transaction timeline riêng.

### Transactional outbox giúp điều gì?

Nếu Orders ghi:
1. Order state.
2. Outbox event mô tả state change.

... trong **cùng một DB transaction**, sau restore không nên có trạng thái “Order commit trong DB nhưng outbox row của chính transaction đó chưa commit”, miễn transaction recovery đúng và code thực sự dùng transaction chung.

Outbox **không tự chứng minh event đã được relay publish đúng một lần**. Relay có thể publish rồi crash trước khi mark processed; khi phục hồi nó publish lại. Consumers cần dedup.

## 13. Kafka log và offset: lưu ý tính bất biến của lịch sử

Kafka lưu record theo topic/partition và offset. Trong một consumer group, committed offset cho biết **vị trí đọc tiếp theo dự kiến**, không phải toàn bộ business side effects đã được xác nhận vĩnh viễn ở mọi sink.

Sau DR:
- Kafka log có thể còn record đã publish sau recovery point của DB.
- Consumer group offset có thể vượt quá dữ liệu đã được restore trong sink.
- Producer có thể retry/re-publish outbox tạo record trùng.
- Retention có thể đã xóa record cần replay.
- Partition count, key routing và schema evolution có thể thay đổi.
- Consumer mới với code/schema khác có thể không giải mã được record cũ.

Quy tắc:
1. Ghi lại topic, partition, offset và consumer group trước khi điều chỉnh.
2. Đừng coi offset bằng transaction ID hoặc WAL LSN.
3. Xác định **checkpoint tại sink đã commit**, không chỉ offset broker đã nhìn thấy.
4. Replay từ boundary sớm đủ để không bỏ sót sự kiện.
5. Bảo đảm idempotency khi replay đi qua những event đã áp dụng.
6. Không rewind toàn group production không kiểm soát vì có thể nhân side effects.
7. Cân nhắc dựng **recovery consumer group** hoặc isolated replay job để rebuild projection trước khi chuyển traffic.

Một checkpoint mạnh có thể là:
- Mỗi partition, “offset tiếp theo cần đọc” đã ghi trong **cùng transaction** với trạng thái projection (nếu mô hình lưu trữ cho phép).
- Per aggregate sequence/version đã áp dụng ở sink.
- Event ID đã lưu trong inbox/dedup table cùng business update.
- CDC watermark có provenance và logic xác định.

Nếu chưa có các bằng chứng này, quá trình phục hồi có thể cần replay từ mốc sớm hơn và chấp nhận xử lý trùng **an toàn**, thay vì cố chọn mốc quá muộn.

## 14. Trường hợp nguy hiểm: consumer offset mới hơn database sink

Giả sử consumer xử lý event Orders để xây read model PostgreSQL:

```text
10:00  Projection DB backup, applied up to Kafka offset 500
10:05  Consumer applied records 501..550
10:06  Consumer committed group offset 551
10:10  Projection DB lost
10:12  Restore projection DB from 10:00 (applied to 500)
10:13  Kafka group still says offset 551
```

Nếu khởi động consumer với committed offset 551, projection bị thiếu records 501–550. Nó có thể hiển thị trạng thái cũ **vĩnh viễn** cho những aggregate không còn event mới.

Hướng xử lý:
1. Ngăn consumer live ghi vào projection đang restore.
2. Xác nhận projection backup đã áp dụng bền vững tới offset nào cho từng partition.
3. Khởi chạy replay từ `501` trong ví dụ (hoặc mốc an toàn sớm hơn).
4. Xây handler idempotent/monotonic để replay không phá record đã có.
5. Theo dõi catch-up watermark, backlog age và dữ liệu đối soát.
6. Chuyển sang consumer bình thường chỉ khi checkpoint và readiness hợp lệ.

**Không chỉ reset offset group về earliest một cách mù quáng** nếu event có side effects bên ngoài hoặc retention rất dài; một projection có thể rebuild từ đầu, nhưng billing/payment/email consumer không được đối xử như search index.

## 15. Trường hợp ngược: database nguồn được restore cũ hơn Kafka

Giả sử Orders DB được khôi phục tới 10:00, nhưng Kafka còn `OrderCreated`, `OrderPaid` tới 10:10. Khi application query Orders DB có thể không thấy order, trong khi Payments đã xử lý nó.

Có ba khả năng cần phân biệt:

**A. Event mô tả transaction thực đã commit nhưng bị mất vì DB restore cũ.** Nếu log/outbox/audit đủ tin cậy và có đầy đủ dữ liệu, có thể tái dựng một phần state bằng replay theo domain rule, sau đó đối soát các hiệu ứng khác. Không giả định event chỉ chứa ID là đủ để reconstruct toàn bộ record.

**B. Event là kết quả publish không được bảo đảm gắn với DB commit.** Có thể là ghost event do dual write sai. Cần kiểm tra provenance trước khi dùng làm source of truth.

**C. Event đúng nhưng provider bên ngoài đã thực hiện side effect mà DB không biết.** Cần query/reconciliation với provider, không chỉ replay event.

Cách vận hành:
- Xác nhận nguồn event, event ID, aggregate ID, transaction correlation và sequence.
- Phân biệt event đã được durable publish với event đã được external provider xử lý.
- Xác định business state hợp lệ tiếp theo, có thể `PENDING_RECONCILIATION` thay vì `CONFIRMED`.
- Dùng API/hồ sơ đối soát có quyền phù hợp, không trực tiếp “update status confirmed” từ một log không đủ bằng chứng.
- Ghi mọi correction bằng cơ chế có audit trail, không lén sửa dữ liệu rồi bỏ qua lịch sử.

Một log publish sau DB commit không đồng nghĩa log đó có thể thay thế DB đầy đủ trong mọi thiết kế.

## 16. Outbox, inbox và CDC: tạo “đường hồi phục” từ lúc thiết kế

### Transactional outbox

Producer ghi business row và outbox row trong một transaction:

```sql
BEGIN;

INSERT INTO orders (order_id, status, version)
VALUES ('ord-42', 'CREATED', 1);

INSERT INTO outbox_events
  (event_id, aggregate_id, aggregate_version, event_type, payload)
VALUES
  ('evt-42-v1', 'ord-42', 1, 'OrderCreated',
   '{"orderId":"ord-42","status":"CREATED","version":1}');

COMMIT;
```

Ví dụ SQL minh họa; schema thực cần constraint, dữ liệu tenant, transaction isolation và cơ chế sinh ID riêng. Tính nguyên tử chỉ áp dụng nếu cả hai bảng thuộc transaction DB thật sự.

Outbox relay/CDC:
- Đọc các outbox rows đã commit.
- Publish vào broker theo contract.
- Lưu tiến độ phát một cách có thể khôi phục.
- Chấp nhận có thể publish lại sau crash.
- Có idempotency/dedup ở consumer.

**Outbox giảm nguy cơ “DB đã ghi nhưng event mất vì dual write”**. Nó không xóa yêu cầu replay, schema version và consumer idempotency.

### Inbox/dedup consumer

Consumer có thể ghi event ID cùng business update vào một DB transaction:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(120) NOT NULL,
    event_id VARCHAR(160) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Pseudo workflow:

```text
BEGIN DB TRANSACTION
  INSERT processed_events(consumer, event_id)
  IF unique conflict:
      already processed -> no duplicate side effect
  ELSE:
      apply business change
COMMIT
then commit broker offset
```

Nếu DB commit xong nhưng Kafka offset commit lỗi, record được replay; inbox nhận ra event đã xử lý. Nếu sink DB được restore từ backup cũ, inbox cũng có thể quay về trước event đó, và replay sẽ áp lại business update. Điều này đúng **nếu business write và inbox state được khôi phục cùng một transaction boundary**, nhưng vẫn phải xét các side effects bên ngoài không nằm trong DB.

### CDC checkpoint

Với Debezium hoặc một CDC pipeline khác, cần ghi nhận:
- Source log position/LSN/GTID có provenance.
- Schema history và snapshot mode.
- Connector state, offsets và sink checkpoint.
- Quy tắc resume sau khi source được PITR hoặc failover sang timeline khác.
- Khả năng tạo duplicate/snapshot events khi restart.

Không copy checkpoint cũ giữa những database incarnation khác nhau mà chưa hiểu semantics của connector. Một source đã PITR sang timeline mới có thể khiến position cũ không còn chỉ đúng lịch sử dữ liệu tương ứng.

## 17. Event versioning và thứ tự khi replay

Một dữ liệu projection chỉ có thể rebuild đúng nếu consumer hiểu các events lịch sử cần thiết.

Nên cân nhắc schema:

```json
{
  "eventId": "evt-42-v3",
  "eventType": "OrderStatusChanged",
  "schemaVersion": 2,
  "aggregateId": "ord-42",
  "aggregateVersion": 3,
  "occurredAt": "2026-11-12T10:05:00Z",
  "data": {
    "status": "PAID"
  }
}
```

Các trường có vai trò:
- `eventId`: dedup và audit.
- `aggregateId`: xác định state cần cập nhật.
- `aggregateVersion` hoặc sequence: phát hiện event cũ/ngoài thứ tự.
- `schemaVersion`: chuyển đổi payload giữa các phiên bản consumer.
- `occurredAt`: thông tin nghiệp vụ/quan sát; **không thay thế** sequence hoặc commit order.
- Correlation/causation IDs: truy vết quan hệ nhân quả giữa các service.

Một projection dùng optimistic versioning có thể:
- Chấp nhận event version đúng next sequence.
- Bỏ qua event đã áp dụng.
- Đặt event ahead-of-sequence vào trạng thái cần chờ hoặc phát hiện gap.
- Yêu cầu snapshot/reconciliation khi thiếu event bắt buộc.
- Không đơn thuần lấy `max(timestamp)` vì đồng hồ producer có thể lệch.

Nếu schema v1 đã bị consumer v3 bỏ hỗ trợ trong khi backup và Kafka retention vẫn có v1, DR replay có thể thất bại. **Version compatibility của dữ liệu lịch sử là một yêu cầu DR**, không chỉ cho rolling deploy.

## 18. Cache: thường xóa và làm ấm lại, không cố giữ state cũ

Redis/memory caches thường là **derived hoặc disposable state**, nhưng có một số ngoại lệ như session, idempotency token, rate limit state hoặc distributed locks. Phải phân loại trước khi wipe.

Với cache đọc thuần:
1. Ngăn writer mới ghi giá trị trong khi nguồn canonical chưa restore.
2. Xóa hoặc version namespace cho cache có khả năng stale.
3. Khởi chạy service với cache miss được hỗ trợ.
4. Làm ấm theo traffic hoặc job có rate limit.
5. Tránh cache stampede bằng single-flight/TTL jitter/concurrency limit.
6. Theo dõi database load khi cache cold.

Với session/idempotency/locks:
- Không xóa mù nếu dữ liệu chứa quyền/định danh hoặc hàng rào tránh thao tác trùng.
- Xác định durable authority và quy trình khôi phục hoặc cấp lại an toàn.
- Không để distributed lock cũ khiến workflow treo, nhưng cũng không giải phóng lock khi writer cũ chưa bị fence.

Ví dụ Orders DB restore về `version=8` nhưng Redis còn object `version=12`. Cache key chứa version hoặc epoch giúp ngăn đọc trạng thái cũ sau DR; nếu không có cơ chế đó, flush có chọn lọc là lựa chọn an toàn hơn việc tin giá trị cache.

## 19. Search index, read model và data warehouse

Elasticsearch/OpenSearch và các read models thường có thể **rebuild** từ nguồn canonical và event stream:

```text
Orders Source DB / Durable Events
              |
              v
        Reindex pipeline
              |
              v
     New index generation v2
              |
              v
       Validate + compare
              |
              v
        Switch read alias
```

Cách an toàn:
- Tạo generation/index mới tách khỏi index đang phục vụ.
- Quét snapshot nguồn có điểm chốt rõ, kèm cursor/version.
- Replay hoặc catch up events sau snapshot watermark.
- Chống duplicate và out-of-order bằng aggregate version/sequence.
- Kiểm tra số record, key coverage, aggregate sums và sampled query correctness.
- Chuyển alias/index routing một lần theo cơ chế được platform hỗ trợ.
- Theo dõi indexing lag và rollback đường đọc nếu cần.

Không nên:
- Giữ index cũ làm chân lý nếu source database đã bị restore ngược.
- Reindex đồng thời với live writes mà không có watermark/catch-up protocol.
- Đọc event có retention thiếu nhưng vẫn tuyên bố projection hoàn chỉnh.
- Coi số document bằng nhau là đủ nếu thiếu relationship và semantic checks.
- Để analytics dashboard phát số liệu như “đã chốt” khi dữ liệu đang rebuild mà chưa đánh dấu trạng thái.

Với warehouse, ETL/CDC có thể cần chạy lại theo watermark hoặc batch ID. Khi replay, sử dụng idempotent upsert/merge, partition overwrite có kiểm soát hoặc versioned datasets. Nếu pipeline tạo dữ liệu tổng hợp, cần kiểm tra double-counting khi cùng batch được chạy lại.

## 20. Object storage: nội dung, version và metadata phải nhất quán

Một nghiệp vụ có thể gồm DB row trỏ tới object file:

```text
invoice_metadata:
  invoice_id = inv-83
  object_key = invoices/2026/inv-83.pdf
  object_version = version-7
  checksum = sha256:...
```

Sau DR, có thể xảy ra:
- Metadata đã restore nhưng object tương ứng không còn.
- Object còn nhưng metadata DB đã bị rollback.
- Key bị ghi đè bằng nội dung khác và thiếu version ID.
- Object đã chuyển retention tier, phải phục hồi quyền đọc.
- Encryption key không khả dụng ở DR region.

Các cơ chế:
1. Bật versioning/immutable retention phù hợp với yêu cầu dữ liệu.
2. Lưu object ID/version/checksum bên cạnh metadata business.
3. Thiết kế upload theo pattern staging → validate → commit metadata → publish event theo hợp đồng.
4. Duy trì orphan-object reconciliation và missing-object detection.
5. Khi restore, so checksum và object version được tham chiếu.
6. Không tự xóa orphan objects ngay; chúng có thể là bằng chứng cần đối soát hoặc chịu legal hold.
7. Với file chứng từ có giá trị pháp lý, thao tác reissue/cancel cần quy trình riêng thay vì tái tạo âm thầm.

Object storage versioning giúp bảo vệ dữ liệu, nhưng **không tự cung cấp transaction nguyên tử giữa object và database**.

## 21. External side effects: nơi restore nội bộ không thể “quay ngược thời gian”

Payment capture, chuyển tiền, email, SMS, tạo shipment hoặc gọi provider bên ngoài đều có thể hoàn tất trước khi DR restore về mốc cũ.

Ví dụ:
1. Orders DB ghi `PENDING`.
2. Payment provider nhận capture `op-42` và thành công.
3. Internal Payments DB ghi `CAPTURED`.
4. Sự cố xảy ra.
5. Payments DB restore từ backup trước bước 3.

Nếu consumer replay event mà gửi một **capture mới với operation ID khác**, khách hàng có thể bị tính tiền hai lần.

Cần mô hình:
- **Stable operation ID/idempotency key** được gán trước khi gọi external API.
- Durable request journal hoặc ledger của operation.
- Reconcile với provider qua API/report/webhook theo quyền được cấp.
- Trạng thái `UNKNOWN/PENDING_RECONCILIATION` khi response mất.
- Compensation/refund nếu business đã thực hiện sai; không mô phỏng rollback bằng xóa row.
- Manual approval cho khoản tiền lớn hoặc state không thể xác minh.
- Audit mọi quyết định, truy vấn và correction.

Quy tắc khẩn cấp: **không cho replay tự động kích hoạt lại thao tác tài chính hoặc gửi thông báo thật cho tới khi bảo đảm idempotency/side-effect safety**. Có thể dựng dry-run, shadow processor hoặc môi trường cô lập để kiểm tra trước.

## 22. Phân biệt replay, redrive, rebuild và compensation

| Hành động | Ý nghĩa | Áp dụng thường gặp | Rủi ro |
| --- | --- | --- | --- |
| **Replay** | Đọc lại event/history theo thứ tự và logic đã định | Rebuild projection, xử lý event bị bỏ sót | Double side effect, schema incompatibility |
| **Redrive** | Đưa message từ DLQ/retry store vào luồng xử lý | Event lỗi tạm thời hoặc đã được sửa | Đảo thứ tự, lặp nghiệp vụ |
| **Rebuild** | Tạo dữ liệu dẫn xuất mới từ canonical state/snapshot | Search index, cache, analytics | Sai watermark, thiếu event |
| **Reconciliation** | So sánh nhiều nguồn để tìm mâu thuẫn và quyết định sửa | Payment, inventory, object metadata | Chọn sai source of truth |
| **Compensation** | Thực hiện giao dịch nghiệp vụ đảo tác động hợp lệ | Refund, release reservation, cancel shipment | Không hoàn nguyên mọi side effect |
| **Restore** | Phục hồi storage từ backup/log | Database, object store, broker | Mốc khác nhau, data loss |

Những hành động này có thể xuất hiện trong cùng DR plan nhưng **không thay thế nhau**. Restore PostgreSQL không tự redrive DLQ. Rebuild search không thay payment reconciliation. Refund là **giao dịch mới có audit**, không phải thao tác quay lại quá khứ.

## 23. Thiết kế idempotency xuyên các cửa sổ khôi phục

Idempotency cần được kiểm tra sau khi restore vì chính **dedup store** có thể bị phục hồi về thời điểm cũ. Nếu idempotency key được lưu trong Redis với TTL 24 giờ nhưng broker retention 7 ngày, replay event cũ có thể xảy ra sau khi key hết hạn.

Biện pháp:
- Xác định **thời gian sống của dedup records** phù hợp cửa sổ retry/replay/DR.
- Dùng durable inbox/operation journal cho side effects quan trọng thay vì chỉ cache TTL ngắn.
- Có unique business key ở nguồn canonical.
- Với external provider, sử dụng idempotency key có thời hạn và semantics được provider công bố; nếu cửa sổ hết hạn thì cần reconcile trước khi retry.
- Trong một DB transaction, ghi business change và dedup record cùng nhau.
- Giữ stable correlation ID xuyên các service; không sinh operation ID mới mỗi lần retry.
- Sau restore, rà soát những operation có idempotency state bị mất và lập danh sách cần đối soát.

Một consumer có “at-least-once delivery” không thể bảo đảm exactly-once side effect chỉ bằng Kafka producer idempotence. Tính đúng đắn phải được xây ở ranh giới chứa side effect.

## 24. Multi-database và Saga: consistency theo invariant, không theo global rollback

Với Orders, Inventory và Payments có database riêng, thường không có transaction ACID duy nhất bao trùm tất cả. Workflow có thể dùng Saga:

```text
OrderCreated
   |
   v
ReserveInventory
   |
   v
AuthorizePayment
   |
   v
ConfirmOrder
```

Nếu thanh toán lỗi sau khi đã reserve tồn kho, workflow có thể dùng compensation `ReleaseInventory`. Khi DR cắt ngang, phải phục hồi **trạng thái của Saga**, không chỉ từng bảng.

Một state machine minh họa:

```text
NEW
 -> INVENTORY_RESERVED
 -> PAYMENT_PENDING
 -> CONFIRMED

Failure:
 -> COMPENSATING
 -> RESERVATION_RELEASED
 -> CANCELLED

Unknown:
 -> PENDING_RECONCILIATION
```

Những invariant cần kiểm tra:
- Một order không đồng thời ở `CONFIRMED` và `CANCELLED` không hợp lệ.
- Một payment capture liên kết đúng với một business operation.
- Reservation không bị giữ mãi nếu order đã cancel mà không có ngoại lệ hợp đồng.
- Không refund trước khi xác định capture thực đã xảy ra.
- Mọi state transition có audit/causation record phù hợp.

Sự kiện có thể đến trễ hoặc trùng sau DR; handler phải kiểm tra state/version trước khi áp dụng. Nếu đã gửi compensation trước sự cố nhưng trạng thái DB restore không biết, không nên tự gửi lại compensation với identity mới.

## 25. Thứ tự phục hồi một Saga bị gián đoạn

Ví dụ checkout ở thời điểm sự cố:

```text
10:03:00  Order CREATED
10:03:01  Inventory RESERVED
10:03:02  Payment authorized at provider
10:03:03  Payments DB CAPTURED recorded
10:03:04  Order confirmation event emitted
10:03:05  Regional incident
```

Sau restore:
- Orders DB chỉ có `CREATED`.
- Inventory DB có reservation.
- Payments DB chỉ thấy `PENDING`.
- Provider đã capture.
- Kafka còn `PaymentCaptured` và `OrderConfirmed`.

Không nên chỉ chọn “phiên bản DB mới nhất” hay “trạng thái event cuối cùng” làm kết quả. Quy trình:
1. Dùng `orderId/paymentOperationId` gom facts từ các nguồn.
2. Xác minh capture với provider nếu có nghi ngờ.
3. Ghi nhận authoritative payment result và idempotency record theo policy.
4. Reconcile inventory reservation/capture status.
5. Áp dụng transition hợp lệ đến `CONFIRMED` hoặc `PENDING_RECONCILIATION`.
6. Không phát lại side effect đã hoàn tất; nếu cần, phát **recovery event** có identity và causation rõ.
7. Kiểm tra các consumer phụ thuộc nhận đúng version của state sau correction.
8. Audit quyết định và người/automation thực hiện.

Đây là phục hồi nhất quán theo **nghĩa vụ nghiệp vụ và bằng chứng**, không phải cố quay mọi nguồn về cùng timestamp.

## 26. Reconciliation: từ so sánh đến sửa chữa có thể kiểm soát

Một reconciliation pipeline thường gồm:

```text
Extract canonical facts and external evidence
                    |
                    v
Normalize IDs, schema versions and time windows
                    |
                    v
Join on business operation/event identity
                    |
                    v
Classify discrepancy
  ├─ Missing internal record
  ├─ Missing external record
  ├─ Duplicate side effect
  ├─ State/version mismatch
  ├─ Pending beyond deadline
  ├─ Missing object/projection
  └─ Unknown / insufficient evidence
                    |
                    v
Choose safe action
  ├─ Replay projection
  ├─ Reconcile provider
  ├─ Apply state correction with audit
  ├─ Compensate under business rules
  └─ Quarantine for manual review
                    |
                    v
Verify invariants and record outcome
```

Các trường cần có trong record đối soát:
- `incidentId` và nguồn/phiên bản extraction.
- `businessOperationId`, `eventId`, `aggregateId`, tenant.
- Source state, sink state, provider evidence, timestamps/positions.
- Mismatch class và mức độ nghiêm trọng.
- Action được phép, actor/owner, approval nếu cần.
- Before/after facts và audit event ID.
- Result, retry count, next investigation step.

Tránh script dạng “UPDATE tất cả status theo bảng có timestamp mới nhất” vì nó bỏ qua side effects, schema version và quan hệ causality.

## 27. SQL mẫu để phát hiện mâu thuẫn

Giả sử trong một database đối soát có các bảng staging:
- `recovered_orders(order_id, status, payment_operation_id)`.
- `provider_payments(payment_operation_id, provider_status, amount_minor)`.
- `ledger_entries(payment_operation_id, entry_type, amount_minor)`.

Một truy vấn tìm order `CONFIRMED` thiếu bằng chứng payment thành công:

```sql
SELECT o.order_id, o.payment_operation_id, o.status
FROM recovered_orders AS o
LEFT JOIN provider_payments AS p
  ON p.payment_operation_id = o.payment_operation_id
WHERE o.status = 'CONFIRMED'
  AND (p.payment_operation_id IS NULL
       OR p.provider_status NOT IN ('AUTHORIZED', 'CAPTURED'));
```

Đây chỉ là **cảnh báo điều tra**. Những domain yêu cầu capture mới được confirmed thì status `AUTHORIZED` có thể chưa đủ, còn những domain chỉ cần authorization thì hợp lệ. Rule phải được xác định theo business contract.

Truy vấn xác định một operation xuất hiện nhiều lần trong staging ledger:

```sql
SELECT payment_operation_id,
       COUNT(*) AS entry_count
FROM ledger_entries
WHERE entry_type = 'CAPTURE'
GROUP BY payment_operation_id
HAVING COUNT(*) > 1;
```

Nhiều ledger entries không tự kết luận double capture nếu một operation được phân bổ nhiều accounting lines; cần join theo provider transaction ID, capture identity và quy tắc accounting tương ứng. SQL là công cụ tìm **ứng viên mâu thuẫn**, không thay thế quyết định nghiệp vụ.

Với accounting ledger double-entry, cần thêm invariant sum(debits)=sum(credits) trong đúng journal/transaction scope và currency; không tự cộng lẫn tiền tệ.

## 28. Checkpoint và watermark cho dữ liệu dẫn xuất

Một projection muốn rebuild nhanh thường cần:
- Snapshot của state ở một mốc có ghi provenance.
- Watermark của nguồn đã được áp dụng đầy đủ.
- Cơ chế nhận event sau watermark.
- Logic chống replay trùng và out-of-order.

Ví dụ:

```text
Projection snapshot:
  taken_at = 10:00
  kafka_offsets:
    orders.events P0: next=1201
    orders.events P1: next=987
    orders.events P2: next=2250

After restore:
  start P0 at 1201
  start P1 at 987
  start P2 at 2250
  catch up until all partitions reach desired watermark
```

Điều kiện quan trọng: snapshot của projection và checkpoint offsets phải mô tả **cùng một trạng thái bền vững**. Nếu checkpoint lưu bên ngoài DB snapshot mà không phối hợp, ta lại rơi vào lỗi “offset mới hơn dữ liệu”.

Với các nguồn không hỗ trợ snapshot atomic giữa data và metadata, cách an toàn là:
1. Bắt đầu replay sớm hơn có headroom.
2. Dùng idempotency và version guard.
3. Đối soát kết quả sau replay.
4. Chỉ cho phép query traffic khi đạt trạng thái đủ chính xác.

Watermark cũng phải được diễn giải theo nhiều partition: không dùng `max(offsets)` của mọi partition như một con số toàn cục có ý nghĩa.

## 29. Khi retention không đủ để replay

Một rủi ro DR thường chỉ được phát hiện sau restore: sự kiện cần replay đã bị xóa vì Kafka retention ngắn hơn khoảng cách từ backup của sink tới hiện tại.

Ví dụ:
- Projection DB backup mới nhất từ 3 ngày trước.
- Kafka chỉ giữ 24 giờ event.
- DR mất projection và phải rebuild, nhưng thiếu 2 ngày sự kiện.

Nếu không có canonical source cho phép full snapshot/backfill, data có thể **không thể tái dựng hoàn toàn**. Cần đánh giá:
- Full scan từ source DB và versioned snapshot.
- Event archive ở object storage có checksum/index và chính sách replay.
- Audit log hoặc CDC archive dài hạn.
- Business provider reports để đối soát.
- Các facts không thể xác minh phải được đánh dấu unknown và quản lý manual.

Quy hoạch retention:
1. Ước lượng backup interval, thời gian phát hiện lỗi âm thầm, RTO và thời gian catch-up.
2. Đảm bảo event log/archive bao phủ đủ cửa sổ cần replay.
3. Thử phục hồi từ backup cũ nhất vẫn nằm trong cam kết.
4. Xác minh schema history và decryption keys còn dùng được.
5. Định nghĩa rõ dữ liệu mất ngoài RPO và quy trình customer remediation.

**Không thể “retry lại” một event đã mất nếu không còn nguồn tạo lại business fact đó.**

## 30. Dữ liệu không tương thích do migration và version deployment

DR thường restore DB về schema version cũ nhưng cluster đang chuẩn bị chạy application image mới.

Ví dụ:
- Orders v4 yêu cầu column `buyer_display_name`.
- Recovery target là trước khi column này được thêm.
- Deploy lại v4 ngay khiến startup hoặc query thất bại.

Ngược lại, schema mới có thể đã loại column mà application cũ cần khi rollback.

Kế hoạch:
- Manifest ghi ứng dụng, schema và contract versions ở recovery target.
- Chọn application image **tương thích với schema restored** và các consumer events còn được hỗ trợ.
- Chạy migrations forward an toàn sau khi có backup/validation.
- Không tự chạy full startup automation trước khi kiểm tra migration prerequisites.
- Với expand/contract, duy trì old/new fields đủ lâu để hỗ trợ rolling deploy và DR window.
- Giữ các codec/transformer đọc được events lịch sử cần replay.
- Trong multi-region, xác định region nào đã áp schema migration và có divergence hay không.

DR không chỉ là data restore; đó cũng là **code/schema/protocol compatibility recovery**.

## 31. Failover giữa các region và replication lag

Với primary region A và standby region B:

```text
Region A (primary writes)
     |
     +---- asynchronous replication ----> Region B
                                             |
                                        DR promotion
```

Nếu replication bất đồng bộ, khi A mất, B có thể thiếu một số commit đã ACK cho user ở A. RPO thực phụ thuộc replica lag và khả năng truy xuất WAL còn lại. Khi A trở lại, không được bật hai primary writes độc lập nếu hệ thống chưa thiết kế multi-primary conflict resolution.

Runbook:
1. Kiểm tra replication lag và recovery points đã biết.
2. Fence old primary và các writer liên quan.
3. Promote standby theo cơ chế được DB/platform hỗ trợ.
4. Xác định committed transactions có thể đã mất và tạo reconciliation window.
5. Kiểm tra event/CDC offsets so với DB timeline mới.
6. Ngăn old-primary relays publish events từ lịch sử không còn canonical.
7. Mở traffic từng lớp, theo dõi consistency và data loss.
8. Khi đưa region cũ trở lại, rebuild replica từ canonical state mới, không merge mù hai lịch sử.

Synchronous replication có thể giảm RPO trong điều kiện phù hợp nhưng đánh đổi latency/availability và có thể không loại bỏ mọi failure mode. Không chọn topology chỉ từ một số “RPO=0” mà bỏ qua network partition, quorum và tài liệu bảo đảm của hệ thống.

## 32. DR runbook theo pha

### Pha A — Khởi động incident và bảo toàn bằng chứng

- [ ] Tuyên bố incident, owner và phạm vi ảnh hưởng.
- [ ] Xác định incident type: data corruption, deletion, region outage, replication divergence, ransomware hay faulty migration.
- [ ] Ghi request impact, RPO/RTO và ràng buộc pháp lý/bảo mật.
- [ ] Giữ logs, audit, traces, backup metadata, topology và deployment versions.
- [ ] Ngăn những thao tác phục hồi thử nghiệm ghi đè nguồn chứng cứ.
- [ ] Chỉ cho phép operator có quyền phù hợp.

### Pha B — Cô lập ghi và chọn authority

- [ ] Fence writer/leader cũ nếu cần failover.
- [ ] Tạm dừng API mutation và jobs có side effects.
- [ ] Pause broker consumers/CDC/relays theo dependency plan.
- [ ] Xác định source of truth theo domain fact.
- [ ] Tạo recovery manifest cho DB, broker, object store, provider.
- [ ] Chọn recovery cut hoặc xác định reconciliation window nếu không có global snapshot.

### Pha C — Restore nguồn dữ liệu

- [ ] Restore vào môi trường cô lập nếu khả thi.
- [ ] Kiểm tra backup integrity, checksum, decryption, schema.
- [ ] Restore database transaction-consistent theo đúng hệ DB.
- [ ] Xác định committed facts và outbox/inbox ở recovery point.
- [ ] Khôi phục broker/log/archive cần thiết cho replay.
- [ ] Kiểm tra object store versions/metadata.
- [ ] Ghi thực tế RPO và những facts chưa thể xác minh.

### Pha D — Reconcile và rebuild

- [ ] Đối soát external payments/shipments.
- [ ] Khôi phục dedup/idempotency state hoặc thiết lập safety gate.
- [ ] Replay/rebuild projections từ checkpoint đúng.
- [ ] Dọn/invalidate stale caches.
- [ ] Chạy migrations ứng dụng cần thiết mà vẫn đảm bảo compatibility.
- [ ] Kiểm tra lag, record count, checksum và business invariants.
- [ ] Quarantine những trường hợp unknown, có owner và deadline.

### Pha E — Mở traffic có điều kiện

- [ ] Read-only APIs chứng minh dữ liệu cốt lõi có thể truy vấn.
- [ ] Consumer handlers dry-run/shadow nếu có nguy cơ side effects.
- [ ] Cho phép limited writes với canary/tenant scope thích hợp.
- [ ] Kiểm tra payment/inventory idempotency thật theo môi trường được phép.
- [ ] Theo dõi user-journey SLI, backlog age, 5xx, mismatch counts.
- [ ] Mở rộng khi gate đạt, không vì pods đều Running.
- [ ] Ghi action log và incident communication.

### Pha F — Hoàn tất và theo dõi

- [ ] Xác nhận RTO/RPO thực tế và sai lệch so với mục tiêu.
- [ ] Lưu reconciliation evidence và audit trail.
- [ ] Tiếp tục theo dõi late events, DLQ, orphan objects, refund/dispute.
- [ ] Làm postmortem không đổ lỗi, có action items.
- [ ] Bổ sung backup/replay/contract tests cho failure mode vừa xảy ra.
- [ ] Kiểm tra monitoring và alerts không bị tắt sót sau recovery.

Mỗi bước cần owner, lệnh được review, điều kiện thành công và điểm dừng. Không nên chạy script phục hồi dữ liệu thật như một chuỗi lệnh không thể hoàn tác.

## 33. Validation gate: thế nào mới được coi là khôi phục nhất quán?

Một service “healthy” không chứng minh dữ liệu đúng. Cần nhiều lớp kiểm chứng.

| Lớp | Chỉ báo | Ví dụ điều kiện |
| --- | --- | --- |
| Storage | Backup/log consistency | DB có thể chạy recovery, checksum và schema đúng |
| Referential | Quan hệ dữ liệu | Không có order trỏ tới payment ID không tồn tại trong phạm vi hợp đồng |
| Event | Replay completeness | Consumer đã qua watermark cần thiết, không có gap chưa giải thích |
| Derived stores | Projection parity | Counts/checksums/sample queries phù hợp canonical source |
| Domain | Business invariants | Không double capture, trạng thái order hợp lệ |
| External | Provider reconciliation | Không có charge chưa đối soát vượt ngưỡng chấp nhận |
| Security | Auth/data access | Không mở quyền sai tenant sau restore |
| Performance | Catch-up và latency | Backlog không tăng vô hạn, DB không bị rebuild làm nghẽn |
| User journey | E2E critical flow | Checkout, refund/status theo mục tiêu đã định |
| Audit | Evidence | Có manifest, action log và danh sách unknown |

Không yêu cầu search/analytics đạt parity tuyệt đối ngay khi mở read-only nếu có chiến lược bounded staleness được thông báo; nhưng nghiệp vụ thu tiền có thể cần gate chặt hơn.

### Kiểm tra theo sampling và full scan

- Full scan với aggregate sums và key coverage khi khả thi.
- Partition/batch checksum để so lượng lớn data có thể tái hiện.
- Sample theo tenant, loại order, phiên bản schema, timestamp và record có side effects.
- So sánh business totals với provider ledger theo currency và ngày.
- Phát hiện record duplicate và missing relation.
- Chú ý false positives từ eventual consistency và repair đang chạy; cần watermark trước khi kết luận.

Một checksum giống nhau không tự bảo đảm mọi **semantic invariant**; một set record hoàn chỉnh vẫn có thể chứa giao dịch bị xử lý hai lần.

## 34. RTO thực tế: restore data có thể nhanh nhưng đối soát chậm

Một timeline DR minh họa:

| Pha | Thời gian giả định |
| --- | ---: |
| Phát hiện và cô lập writes | 5 phút |
| Chọn recovery point, xác minh backup | 10 phút |
| Restore Orders/Payments DB | 20 phút |
| Broker/CDC recovery và replay | 15 phút |
| Payment/inventory reconciliation | 25 phút |
| Search rebuild và cache warmup | 30 phút |
| User-journey validation | 10 phút |

Tổng các bước không phải lúc nào cộng tuyến tính; một số công việc chạy song song, một số có dependency bắt buộc. Nếu phải đợi payment reconciliation để mở checkout, **critical path** có thể dài hơn restore database đơn thuần. Nếu search rebuild chạy nền và UI chấp nhận tìm kiếm chưa cập nhật trong cửa sổ, có thể mở các chức năng khác sớm hơn.

RTO phải được **diễn giải theo chức năng**:
- RTO đọc lịch sử đơn.
- RTO cho phép tạo đơn mới.
- RTO hoàn tất thanh toán.
- RTO cho full search/analytics fidelity.

Một mục tiêu “hệ thống lên trong 30 phút” quá mơ hồ nếu không nêu các chức năng và tiêu chí consistency cần đạt.

## 35. Quan sát và cảnh báo sau phục hồi

Các chỉ số hữu ích:

| Metric/indicator | Ý nghĩa |
| --- | --- |
| `recovery_point_age_seconds` | Tuổi backup/log point hiện có |
| `replication_lag_bytes` / `seconds` | Sai lệch giữa primary và standby theo hệ DB |
| `wal_archive_gap_count` | Đo log archiving không đầy đủ |
| `outbox_pending_events` | Giao dịch đã ghi nhưng chưa phát event |
| `cdc_source_lag_seconds` | CDC chậm so với nguồn |
| `consumer_group_lag` per partition | Consumer còn bao nhiêu record chưa đọc |
| `oldest_unprocessed_event_age` | Độ trễ nghiệp vụ, không chỉ số messages |
| `reconciliation_mismatch_count` | Những facts chưa phù hợp giữa các nguồn |
| `reconciliation_unknown_count` | Trường hợp không đủ bằng chứng |
| `duplicate_side_effect_detected_total` | Dấu hiệu idempotency bị vượt qua |
| `projection_version_gap_count` | Read model thiếu sequence |
| `orphan_object_count` | Object/metadata chưa khớp |
| `pending_payment_age_seconds` | Payment chưa có kết quả cuối |
| `rebuild_progress` | Phần projection đã rebuild |
| `business_journey_good_rate` | Người dùng nhận kết quả đúng |
| `recovery_gate_status` | Trạng thái cho phép mở từng chức năng |

Tên metric minh họa; cần instrument phù hợp môi trường và tránh label có cardinality lớn. Không đặt raw payment/customer IDs thành Prometheus labels hoặc log chứa secrets.

Cảnh báo sau DR cần ưu tiên:
- Reconciliation mismatch tăng thay vì giảm.
- Backlog age vượt retention hoặc SLO.
- Có tác dụng phụ trùng, nhất là capture/refund/shipment.
- Còn writer ở region cũ sau failover.
- Schema/contract errors khi consumer replay events cũ.
- Cache cold làm database saturation.
- Corruption hoặc missing WAL/backup segment.

**Không tắt cảnh báo lâu dài chỉ để dashboard xanh trong lúc restore**. Nếu cần suppress có thời hạn, phải ghi rõ owner và điều kiện bật lại.

## 36. Kiểm thử DR định kỳ: đừng chỉ kiểm tra “backup có tồn tại”

Một DR drill có giá trị nên tái hiện **mismatch giữa các nguồn**:

### Drill 1 — Projection DB bị mất, Kafka còn log

- Restore search/read-model DB từ snapshot cũ hơn consumer offset.
- Xác định checkpoint đúng và replay.
- Xác minh không thiếu ẩn record và không nhân aggregate.
- Đo catch-up time, p95 query latency và parity.

### Drill 2 — Source DB restore về trước outbox publish

- Tạo order transaction kèm outbox.
- Publish event rồi làm giả lập restore DB về mốc trước transaction.
- Xem event còn trong Kafka và quyết định reconciliation.
- Kiểm tra ghost event được phát hiện, không tự tạo order trái hợp đồng.

### Drill 3 — External payment thành công, nội bộ mất ack

- Provider sandbox nhận operationId và trả thành công.
- Giả lập crash trước internal DB persist.
- Restart/replay với cùng operationId.
- Xác minh reconciliation nhận trạng thái đúng, không charge thêm.

### Drill 4 — Outbox relay publish trùng

- Relay publish event rồi crash trước ghi checkpoint.
- Khởi động lại để publish duplicate.
- Xác minh inbox/consumer idempotency ngăn double effect.

### Drill 5 — Kafka retention không đủ

- Restore projection từ snapshot cũ hơn log retention.
- Xác định thiếu event, fallback full snapshot/archive.
- Không tuyên bố success nếu không rebuild được dữ liệu.

### Drill 6 — Old primary trở lại sau failover

- Trong test environment, promote secondary và fence old primary.
- Khởi động lại old writer, bảo đảm nó không chấp nhận writes.
- Kiểm tra không phát stale outbox events từ lịch sử cũ.

### Drill 7 — Schema mismatch

- Restore DB về schema cũ, chạy image mới trong test.
- Xác minh compatibility/migration plan và rollback gates.
- Replay event schema version cũ bằng consumer hiện tại.

### Drill 8 — Object metadata divergence

- Restore metadata DB cũ nhưng giữ object storage version mới.
- Tìm missing references và orphan objects.
- Xác minh version/checksum và retention.

Với từng drill, ghi **RPO/RTO thực tế, số mismatch phát hiện, thời gian xử lý, lỗi manual steps và phần không thể tự động hóa**. Đây là bằng chứng để điều chỉnh kế hoạch, không chỉ một ô “backup test PASS”.

## 37. Recovery tabletop exercise cho đội liên nhóm

Tình huống: 10:20 phát hiện Orders PostgreSQL lỗi storage. Replica cũng chứa corrupted data do replication tiếp diễn; backup usable mới nhất 10:00. Kafka còn sự kiện tới 10:19, Payments DB tới 10:18 và provider settlement report có giao dịch tới 10:19.

Những người cần tham gia:
- Incident commander/DR owner.
- Orders owner và DBA.
- Payments owner và người có quyền provider reconciliation.
- Inventory owner.
- Messaging/CDC platform owner.
- Security/Identity owner khi cần secrets/decryption/access.
- Product/support owner truyền thông user impact.

Bài tập:
1. Có nên dừng nhận đơn mới ngay? Chức năng nào còn chạy read-only?
2. Ai đảm bảo old primary không ghi cạnh tranh?
3. Chọn restore target cho Orders DB dựa trên bằng chứng nào?
4. Từ Kafka, event nào có đủ provenance để reconstruct order?
5. Những payment nào provider xác nhận nhưng Orders DB không còn?
6. Inbox/outbox checkpoint còn phù hợp với DB timeline mới không?
7. Cache và search cần invalidate hay rebuild theo watermark nào?
8. Các invariant nào bắt buộc đạt trước khi mở checkout?
9. Người dùng có thể đã nhận thông báo order thành công nhưng nội bộ chưa có bản ghi; xử lý thế nào?
10. Nếu mục tiêu RPO 5 phút không đạt, ai quyết định và truyền thông về khoảng mất dữ liệu đã xác nhận?

Kết quả mong đợi là **runbook có quyết định, owner, công cụ và bằng chứng**, không phải “restore backup rồi mọi thứ sẽ tự đồng bộ”.

## 38. Anti-patterns thường dẫn tới mất nhất quán sau DR

**“Tất cả backup lấy lúc 10:00 nên chắc chắn đồng bộ.”** Timestamp giống nhau không bảo đảm transaction causality hay đồng hồ các hệ nhất quán.

**“PostgreSQL đã recovery thành công nên không cần đối soát.”** Đúng transaction trong DB không chứng minh payment provider, Kafka và read models đúng.

**“Giữ nguyên Kafka group offsets sau khi restore sink.”** Offsets có thể mới hơn trạng thái sink và âm thầm bỏ qua sự kiện cần replay.

**“Rewind Kafka group tới earliest cho mọi consumer.”** Có thể kích hoạt double payment/shipment/email hoặc chạy quá retention, phá ordering.

**“Kafka là source of truth vì event còn đầy đủ.”** Event có thể chỉ là notification, không chứa full state hoặc không được phát atomically với DB.

**“Chọn row có updated_at mới nhất.”** Đồng hồ lệch và event đến trễ có thể làm trạng thái sai.

**“Xóa Redis toàn bộ cho đơn giản.”** Một số keys chứa idempotency, locks hoặc state khác không thể mất tùy tiện.

**“Khôi phục từ provider bằng cách gửi lại payment request.”** Timeout không phải bằng chứng provider chưa xử lý; cần reconcile bằng stable operation ID.

**“Tắt mọi kiểm tra để mở traffic nhanh.”** Có thể làm phát sinh giao dịch trùng và tăng chi phí sửa chữa.

**“Rebuild Elasticsearch trong khi source đang thay đổi mà không có watermark.”** Search có thể liên tục miss hoặc ghi bản cũ đè mới.

**“Bật secondary nhưng quên fence primary.”** Split brain có thể gây divergence lớn hơn outage ban đầu.

**“Chỉ đo downtime, không đo consistency.”** Số pod Running không phản ánh tính đúng đắn giao dịch.

**“Script đối soát tự động sửa mọi discrepancy.”** Thiếu phân loại unknown/financial/legal cases có thể gây hỏng thêm dữ liệu.

**“DR plan không được thử với retention và code version thật.”** Khi sự cố xảy ra, mới biết sự kiện bị xóa hoặc consumer không đọc được schema cũ.

## 39. Decision matrix cho từng nguồn dữ liệu

| Nguồn | Phục hồi ưu tiên | Điều kiện mở traffic | Cần tránh |
| --- | --- | --- | --- |
| Orders PostgreSQL | PITR/restore + business reconciliation | Core orders state hợp lệ, no missing critical operations chưa quản lý | Nhận writes trước khi fence old primary |
| Payments DB | Restore + external provider ledger reconcile | Không có double-charge risk không kiểm soát | Replay payment side effect với ID mới |
| Inventory DB | Restore + reservation reconcile | Số lượng và reservation state theo invariants | Tự tăng stock khi không có bằng chứng |
| Kafka event log | Bảo tồn log/metadata, xác định offsets | Replay policy và consumer idempotency rõ | Reset offsets mù |
| Outbox relay | Restore source/outbox checkpoint | Không phát event không có canonical transaction | Tin exactly-once publish tuyệt đối |
| Consumer inbox | Reconcile với sink business state | Dedupe state bền vững | Xóa inbox sau restore mà không đánh giá replay |
| Search index | New index rebuild + catch up | Parity hoặc staleness trong SLO | Giữ stale index làm truth |
| Redis cache | Invalidate/warmup theo loại key | Không trả stale security/business state | Flush idempotency/session keys tùy tiện |
| Object storage | Version/checksum + metadata reconciliation | References và content integrity đủ | Xóa orphan files ngay |
| Analytics warehouse | Backfill và dedup theo batch/window | Dashboard có watermark và trạng thái dữ liệu | Double count hoặc công bố số chưa đủ |
| External provider | Query/report reconcile | Có bằng chứng kết quả, unknown được quarantine | Gọi lại side effect không cùng identity |

Không có một “đúng thứ tự” duy nhất áp dụng mọi domain; thứ tự thật phải tuân theo **business criticality, dependency graph và safety gates**.

## 40. Checklist chuẩn bị trước khi có sự cố

### Thiết kế và dữ liệu
- [ ] Mọi business fact quan trọng có authoritative owner.
- [ ] Có stable business operation ID và event ID.
- [ ] Có version/sequence cho state cần ordering.
- [ ] Cross-service writes dùng outbox/inbox/transaction strategy đã kiểm chứng.
- [ ] External side effects có idempotency/reconciliation path.
- [ ] Cache và search được phân loại là derived hay authoritative.
- [ ] Mỗi SLO về freshness/correctness có nguồn đo rõ.

### Backup và replay
- [ ] Backups và WAL/archive đủ theo RPO/RTO.
- [ ] Có thử restore, không chỉ tạo backup.
- [ ] Có manifest chứa schema/version/checkpoint và checksum.
- [ ] Broker retention hoặc archive đủ dài cho rebuild.
- [ ] CDC source/sink checkpoint có provenance.
- [ ] Object versioning/checksum và khóa giải mã khả dụng.
- [ ] Có kế hoạch với missing event history và schema version cũ.

### Vận hành
- [ ] Có cơ chế fence writer/old primary.
- [ ] Có quyền dừng jobs, consumers và outbox relays.
- [ ] Có runbook cho read-only/limited-write recovery.
- [ ] Có owner cho provider reconciliation, accounting và inventory.
- [ ] Có monitoring mismatches, backlog age và duplicate side effects.
- [ ] Có DR drill kiểm tra data consistency giữa nhiều nguồn.
- [ ] Có cách truyền thông data loss, pending operations và unknown states.

## 41. Bài tập thực hành

### Bài 1 — Khác biệt mốc restore

Orders DB restore tới 09:00, Kafka còn event tới 09:20 và Search index tới 09:15. Chỉ ra ba dạng mismatch có thể xảy ra, chọn authoritative source theo một ví dụ nghiệp vụ và mô tả cách replay/rebuild an toàn.

### Bài 2 — Offset vượt sink

Projection DB snapshot đã apply tới offset 300 từng partition, trong khi consumer group committed offset 450. Thiết kế recovery checkpoint và logic idempotent replay để khôi phục records 301–449 mà không bỏ sót dữ liệu.

### Bài 3 — Payment provider đã capture

Provider có capture `operationId=pay-83` thành công nhưng Payments DB đã restore về `PENDING`. Thiết kế reconciliation, operation journal, audit và điều kiện nào mới được chuyển order sang `CONFIRMED`. Vì sao không nên gửi capture request bằng operation ID mới?

### Bài 4 — Outbox replay

Một transaction ghi order và outbox, relay publish Kafka rồi crash trước khi đánh dấu event đã gửi. Khi DR, relay publish lại. Hãy mô tả consumer inbox và idempotency phải xử lý ra sao.

### Bài 5 — Object storage versioning

Metadata DB trỏ tới `invoices/83.pdf` version 5 nhưng object storage chỉ còn version 6 ở lớp dữ liệu được phép truy cập. Lập quy trình tra cứu version/checksum, xác định thiếu dữ liệu và cách xử lý không xóa bằng chứng.

### Bài 6 — Recovery manifest

Lập một manifest cho Orders DB, Kafka, Elasticsearch, Redis và Payments provider. Ghi recovery point, schema version, checkpoint và những invariant bắt buộc.

### Bài 7 — Retention thiếu

Kafka chỉ giữ 12 giờ, projection snapshot mới nhất đã 36 giờ. Chọn giữa full snapshot từ source, event archive và kết luận không thể phục hồi; chỉ ra dữ liệu nào phải ghi nhận là unknown.

### Bài 8 — Multi-region split brain

Region A mất kết nối điều khiển nhưng vẫn có một số writer active; Region B được promote. Thiết kế fencing, leader identity, startup gate và cách đưa A trở lại làm replica an toàn.

### Bài 9 — Business invariant

Checkout gồm Inventory reservation, Payment capture và Order confirmation. Viết tối thiểu năm invariant và ba validation queries/logic checks để xác minh sau DR; nêu các trường hợp cần manual review.

### Bài 10 — RTO theo chức năng

Restore Orders DB mất 12 phút, payment reconciliation mất thêm 35 phút, search rebuild mất 60 phút. Hãy phân biệt thời điểm có thể mở API xem lịch sử đơn, API tạo order và search; giải thích vì sao RTO không đơn thuần là thời gian DB startup.

## 42. Ghi nhớ

- **Nhiều dữ liệu được khôi phục riêng thành công không tự bảo đảm nhất quán của toàn bộ nghiệp vụ.**
- **RPO đo độ mất dữ liệu; RTO phải đo thời gian chức năng nghiệp vụ an toàn được khôi phục**, không chỉ process Running.
- **Không có một global transaction hay timestamp tự động cho tất cả DB, Kafka và provider.** Cần recovery cut theo causal facts, checkpoints và reconciliation.
- **Nguồn có thẩm quyền phải xác định theo business fact.** Cache, search và analytics thường là dữ liệu dẫn xuất có thể rebuild; payment provider và ledger cần đối soát.
- **Outbox đảm bảo DB state và event intent trong cùng transaction**, nhưng relay/replay vẫn có thể tạo duplicate.
- **Consumer offsets phải tương thích với sink recovery point**; offset mới hơn DB đã restore có thể khiến dữ liệu mất âm thầm.
- **Idempotency, aggregate versioning và audit** giúp replay an toàn; external side effects cần cùng operation identity và reconciliation.
- **Retention, schema history, encryption keys và backup provenance** quyết định liệu quá trình replay có thật sự khả thi.
- **Fencing writer cũ và đóng băng side effects** là điều kiện trước khi thay đổi canonical state trong DR.
- **Rebuild projection rồi kiểm tra parity, giữ unknown cases và mở traffic theo safety gate.**
- **DR drill phải kiểm thử correctness xuyên nhiều nguồn**, không chỉ kiểm tra file backup tồn tại.

Khôi phục một hệ thống microservices là **tái lập các sự thật nghiệp vụ đáng tin cậy** bằng một chuỗi hành động có thể quan sát, có bằng chứng và có khả năng lặp lại. Mục tiêu là cho phép người dùng tiếp tục giao dịch **mà không làm hệ thống tạo ra những hậu quả sai nghiêm trọng hơn chính sự cố ban đầu**.

### Tài liệu tham khảo

- PostgreSQL — Continuous Archiving and Point-in-Time Recovery: https://www.postgresql.org/docs/current/continuous-archiving.html
- Apache Kafka — Consumer Configuration and Offset Management: https://kafka.apache.org/documentation/
- Debezium — Architecture and Change Data Capture: https://debezium.io/documentation/
- AWS — Disaster Recovery of Workloads on AWS: https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/disaster-recovery-dr.html
- Google SRE Book — Data Integrity: https://sre.google/sre-book/data-integrity/
- Google SRE Book — Managing Critical State: https://sre.google/sre-book/managing-critical-state/
- Microsoft Azure Architecture Center — Compensating Transaction Pattern: https://learn.microsoft.com/en-us/azure/architecture/patterns/compensating-transaction
- Microsoft Azure Architecture Center — Transactional Outbox Pattern: https://learn.microsoft.com/en-us/azure/architecture/databases/guide/transactional-outbox-cosmos
- AWS S3 — Object Versioning: https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html

Các ví dụ, trạng thái và timeline trong bài mang tính minh họa. Khi áp dụng cần kiểm chứng phiên bản database/broker, chuẩn compliance, năng lực provider, RPO/RTO và quyền triển khai thực tế trước khi dùng runbook trên hệ thống production.
