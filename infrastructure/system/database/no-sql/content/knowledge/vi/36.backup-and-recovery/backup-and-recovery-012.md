# Khôi phục kho dẫn xuất bằng phát lại hoặc xây dựng lại

## 1. Tình huống mở đầu: Elasticsearch mất dữ liệu, MongoDB vẫn còn nguyên

Một ứng dụng Java có kiến trúc:

```text
                  Nguồn sự thật (authoritative source)
                             MongoDB Orders
                                   |
                              Change Stream
                                   |
                                   v
                              Kafka topic
                                   |
                  +----------------+----------------+
                  |                                 |
                  v                                 v
          Elasticsearch Search                Analytics Store
                  |
                  v
             Search API
```

Vào một buổi sáng, chỉ mục `orders-search-v7` bị xóa nhầm. API tra cứu đơn hàng báo lỗi, nhưng collection `Orders` trong MongoDB vẫn hoạt động, các giao dịch đã xác nhận không mất. Nhóm vận hành phải quyết định:

1. **Restore backup của Elasticsearch** nếu snapshot phù hợp còn dùng được.
2. **Replay event log** từ Kafka nếu log chứa đủ sự kiện và còn trong retention.
3. **Rebuild** bằng cách quét MongoDB rồi tái tạo toàn bộ documents tìm kiếm.
4. **Kết hợp snapshot/backfill + tail events** để bắt kịp những ghi mới trong lúc dựng lại.
5. Chuyển tạm API sang đường truy vấn nguồn, giới hạn chức năng hoặc thông báo trạng thái trong thời gian khôi phục.

Thách thức không phải chỉ là “đẩy lại 20 triệu documents”. Trong lúc rebuild, đơn hàng tiếp tục được tạo, sửa, hủy hoặc xóa. Dữ liệu đã xóa không được sống lại, cùng một event có thể phát lại nhiều lần, consumer có thể crash sau khi ghi thành công nhưng trước checkpoint, và search index chỉ được nhận traffic khi kiểm chứng đúng.

Bài này nằm trong chương **Sao lưu và phục hồi** của **Database No SQL**. Mục tiêu là thiết kế quy trình **khôi phục kho dẫn xuất bằng phát lại (replay) hoặc xây dựng lại (rebuild)**, với yêu cầu rõ về nguồn dữ liệu, độ mới, tính đúng đắn, tính sẵn sàng, khả năng lặp lại và điểm chuyển traffic.

## 2. Kho dẫn xuất là gì?

**Kho dẫn xuất (derived store)** là nơi lưu trạng thái được tính, sao chép, biến đổi hoặc lập chỉ mục từ một hay nhiều nguồn dữ liệu khác. Nó giúp một kiểu truy cập nhanh và thuận tiện hơn, nhưng thông thường **không phải nơi ra quyết định cuối cùng về dữ liệu nghiệp vụ**.

Ví dụ:

| Kho dẫn xuất | Nguồn có thẩm quyền | Mục đích |
|---|---|---|
| Elasticsearch/OpenSearch index | MongoDB hoặc Cassandra | Full-text/filter/sort/search |
| Redis cache | PostgreSQL/NoSQL source | Đọc nhanh key hoặc session projection |
| Product read model | Orders/Inventory/Price source | Tối ưu truy vấn giao diện |
| Materialized view do ứng dụng quản lý | Base table/source events | Query theo access path khác |
| OLAP/analytics warehouse | Transactional database + events | Báo cáo, phân tích |
| Vector index | Nội dung gốc + embedding model | Semantic search |
| Graph projection | Entities/relationships từ source | Traversal, recommendation |
| CQRS read side | Write model + domain events | Query độc lập với write model |
| Denormalized customer summary | Nhiều collections/services | Tối ưu màn hình tổng hợp |
| CDC-driven audit projection | Change feed + nguồn khác | Điều tra thay đổi theo policy |

### 2.1. Không phải mọi dữ liệu trong Redis đều có thể bỏ

Nếu Redis chỉ cache sản phẩm, có thể xóa và dựng lại từ source. Nhưng nếu Redis đang là **nguồn duy nhất** giữ session cần thiết, queue, counter hoặc state nghiệp vụ, nó không thể mặc nhiên được xem là kho dẫn xuất có thể xóa.

### 2.2. Search index có thể chứa dữ liệu không còn trong source?

Ví dụ, search enrichment do con người biên tập thủ công mà không được ghi về nguồn. Khi đó index chứa một phần **dữ liệu không thể tái dựng**. Trước khi xóa/rebuild, phải xác định chỗ nào là authoritative cho phần enrichment ấy.

### 2.3. Mối quan hệ có thể là nhiều nguồn

Một `ProductSearchDocument` có thể lấy dữ liệu từ Product, Inventory, Price, Seller và Category. Khôi phục đúng phải xác định các versions/temporal snapshots của **tất cả** nguồn cần thiết, không chỉ copy Product.

## 3. Phân biệt nguồn sự thật, nhật ký và projection

Ba lớp thường bị gộp nhầm:

```text
Authoritative State             Change History              Derived State
-------------------             --------------              -------------
Order DB                       OrderChanged event          OrderSearchIndex
Payment ledger                 PaymentCaptured event       Revenue summary
Inventory DB                   StockAdjusted event         AvailableStockView
```

- **Nguồn sự thật (source of truth):** nơi nghiệp vụ xác định kết quả hợp lệ cuối cùng.
- **Event log/CDC stream:** lịch sử hoặc chuỗi thông báo thay đổi, có thể đầy đủ hoặc không, tùy retention và event contract.
- **Projection/derived store:** trạng thái được tái tạo bằng cách áp các thay đổi hoặc tính lại từ nguồn.

### 3.1. Kafka không tự trở thành nguồn sự thật

Một Kafka topic có thể là authoritative event log nếu hệ được thiết kế event sourcing với retention, backup, ordering, schema và governance thích hợp. Nhưng một topic CDC với retention bảy ngày không thể khôi phục toàn bộ lịch sử ba năm chỉ vì “có Kafka”.

### 3.2. Projection còn phụ thuộc logic biến đổi

Để rebuild giống cũ, cần biết code mapping, schemaVersion, business rules, enrichment sources, model version và index settings. Chỉ có raw events chưa chắc tạo lại được cùng một tài liệu.

### 3.3. Không khôi phục ngược nguồn từ projection nếu không có kế hoạch

Search index có thể chứa dữ liệu trễ, thiếu, được tokenize hoặc mất field; **không nên đẩy ngược nó để ghi đè nguồn có thẩm quyền** chỉ vì source đang lỗi, trừ khi đây là một quy trình recovery được thiết kế và kiểm chứng riêng.

## 4. “Có thể dựng lại” là một giả thiết cần chứng minh

Một derived store thực sự rebuildable khi có đủ:

1. **Nguồn đầy đủ:** state hiện tại hoặc lịch sử events cần thiết vẫn tồn tại.
2. **Logic xác định:** biết cách biến nguồn thành projection, bao gồm schema và version.
3. **Thông tin xóa:** biết records nào đã bị delete/expire/revoke.
4. **Thứ tự/version:** xử lý cập nhật trùng hoặc out-of-order đúng.
5. **Bí mật/khóa/cấu hình:** có quyền truy cập, encryption keys, tokenizer, embedding models.
6. **Tài nguyên:** đủ thời gian, CPU, I/O, network, capacity để rebuild.
7. **Điểm cắt dữ liệu:** xác định snapshot và những thay đổi xảy ra trong lúc rebuild.
8. **Cách nghiệm thu:** có phép kiểm chứng projection đủ chính xác.
9. **Kế hoạch chuyển traffic:** không để user đọc index chưa sẵn sàng.

### 4.1. Bảo vệ sự thật nghiệp vụ trước hết

Nếu duy nhất nơi ghi `lastViewedAt` là Redis cache, field đó có thể mất sau cache flush. Muốn rebuild, chuyển nó thành source event hoặc chấp nhận mất dữ liệu không quan trọng theo policy.

### 4.2. Không nhầm dữ liệu tính toán được với dữ liệu giá trị thấp

Một vector index có thể dựng lại bằng embedding model, nhưng tốn hàng ngày GPU và tiền. Tính rebuildable về logic không đồng nghĩa **RTO có thể chấp nhận**.

### 4.3. Bản thân mã rebuild cũng là dependency phục hồi

Nếu logic transform chỉ tồn tại trong code đã xóa, image cũ không còn hoặc model artifact bị mất, nguồn dữ liệu thô vẫn không bảo đảm khôi phục projection như cũ.

## 5. Các mục tiêu phục hồi: đúng, đủ, mới và kịp thời

Một recovery có ít nhất bốn mục tiêu:

| Thuộc tính | Câu hỏi |
|---|---|
| Correctness | Projection có phản ánh đúng business rules và quyền truy cập? |
| Completeness | Có bỏ mất keys, deletes, versions hoặc tenants? |
| Freshness | Trễ bao lâu so với authoritative source? |
| Availability/RTO | Mất bao lâu để user dùng lại đường đọc hợp lệ? |

### 5.1. RPO của kho dẫn xuất có nghĩa gì?

**RPO (Recovery Point Objective)** truyền thống là lượng dữ liệu có thể mất ở recovery point. Với kho dẫn xuất, có thể chấp nhận bản sao tạm chậm, miễn **nguồn không mất dữ liệu và có đường bắt kịp**. Tuy nhiên, một search index dùng cho kiểm tra tuân thủ có thể có yêu cầu freshness rất chặt.

### 5.2. RTO không chỉ là copy xong dữ liệu

RTO gồm phát hiện sự cố, cấp cluster/index mới, load dữ liệu, replay lag, validation, cutover, cache warmup và xác minh sau cutover.

### 5.3. Recovery SLO theo chức năng

Ví dụ:

```text
Order source:
  no confirmed writes lost

Order Search:
  restore searchable read path within 60 minutes
  stale results <= 2 minutes after cutover
  deleted orders must not appear
  tenant visibility invariants preserved
```

Đây là policy minh họa, không phải mức SLO phổ quát.

## 6. Hai chiến lược chính: replay và rebuild

### 6.1. Replay — phát lại sự kiện/thay đổi

```text
Durable event / CDC log
        |
        v
Read from checkpoint / replay boundary
        |
        v
Projector with schema/version logic
        |
        v
Derived Store
```

Phù hợp khi event log còn đủ lịch sử cần thiết, events mang thông tin tái tạo trạng thái và consumer có thể áp dụng lại một cách idempotent.

### 6.2. Rebuild — xây từ trạng thái nguồn

```text
Authoritative Source
        |
        v
Consistent snapshot / bounded scan
        |
        v
Transform/enrich
        |
        v
Fresh derived index
```

Phù hợp khi nguồn hiện tại đầy đủ, event log thiếu/đã hết retention, projection logic thay đổi hoặc muốn tạo index theo schema mới.

### 6.3. Hybrid — snapshot + tail

```text
Source snapshot --------------> Backfill -----------+
        |                                            |
        +---- Change stream after boundary ---------+--> Catch up
                                                         |
                                                         v
                                                   Verify/cutover
```

Đây thường là phương án thực tế khi source vẫn có writes và lượng dữ liệu lớn.

## 7. Bảng chọn chiến lược

| Điều kiện | Replay | Rebuild | Hybrid |
|---|---|---|---|
| Log còn đầy đủ từ điểm gốc | Rất phù hợp | Có thể | Có thể |
| Log retention ngắn, kho mất toàn bộ | Thường không đủ | Phù hợp nếu nguồn đầy đủ | Phù hợp |
| Chỉ thiếu sự kiện 10 phút | Có thể replay gap | Không nhất thiết | Tùy scope |
| Thay mapping/index schema lớn | Cần transform lại lịch sử | Phù hợp | Thường phù hợp |
| Muốn tạo index v2 không gián đoạn | Replay vào index mới nếu log đủ | Snapshot vào index mới | Thường phù hợp |
| Dữ liệu nguồn mất, log còn full event sourcing | Có thể là phương án chính | Không từ nguồn mất | Phải thiết kế riêng |
| Phải bảo đảm deletes/corrections lịch sử | Chỉ khi events đủ | Source hiện tại phản ánh state | Snapshot + tail + reconcile |
| Embedding model thay đổi | Không thể chỉ copy vectors cũ | Recompute | Recompute + tail |
| Kho dẫn xuất chỉ là cache | Có thể không cần | Lazy warmup | Prefill + live updates |
| Workload cực lớn, RTO ngắn | Replay có thể chậm | Rebuild có thể chậm | Prebuilt snapshots + tail |

### 7.1. Không chọn chỉ theo tốc độ dự kiến

Replay nhanh hơn nếu chỉ cần 100.000 events; rebuild có thể nhanh hơn nếu log có 10 tỷ updates nhưng snapshot có 1 triệu keys sống. Phải tính kích thước, event churn, transform cost và available throughput.

### 7.2. Đặt correctness làm điều kiện tiên quyết

Một phương án “phục hồi trong 10 phút” nhưng không xử lý DELETE không thể đáp ứng yêu cầu bảo mật, dù throughput rất cao.

## 8. Tính thời gian khôi phục sơ bộ

Giả sử derived index có 24 triệu documents. Nguồn có thể đọc bền 20.000 docs/s, sink có thể ghi 12.000 docs/s sau khi tính overhead.

Throughput hữu ích bị giới hạn bởi nút chậm hơn, khoảng 12.000 docs/s:

\[
T_{\text{backfill}}\approx
\frac{24.000.000}{12.000}
=2.000\ \text{s}\approx33{,}3\ \text{phút}
\]

Đây là **thời gian lý tưởng cho backfill**, chưa tính API rate limits, biến thiên kích thước documents, index build, retries, nguồn đang cập nhật, validation và cutover.

### 8.1. Catch-up vẫn có thể mất thêm thời gian

Nếu source phát 5.000 events/s khi backfill chạy 2.000 giây, log có thể tăng khoảng 10 triệu events. Consumer replay 15.000 events/s thì thời gian xử lý backlog ban đầu khoảng 11,1 phút nếu không có sự kiện mới; khi nguồn vẫn sinh 5.000/s, tốc độ thu hẹp backlog ròng chỉ 10.000/s, nên thời gian gần 16,7 phút theo giả thiết ổn định.

### 8.2. Điều kiện bắt kịp

Nếu source tạo \(r_{\text{in}}\) events/s và projector hoàn thành \(r_{\text{out}}\) events/s:

\[
\frac{dB}{dt}\approx r_{\text{in}}-r_{\text{out}}
\]

Khi \(r_{\text{out}}\le r_{\text{in}}\) liên tục, backlog không thể giảm về 0 chỉ bằng cách chờ.

### 8.3. Bytes và documents là hai mẫu số khác

12.000 docs/s với document 1 KiB khác 12.000 docs/s với document 1 MiB. Dùng cả bytes/s, CPU cost, external embedding calls và DB request units.

## 9. Phát lại log chỉ có ích khi log thực sự đủ

Một event log muốn dùng phục hồi phải giải đáp:

- Log bắt đầu từ thời điểm nào?
- Retention theo time/size/segment ra sao?
- Có compaction hay delete records cũ không?
- Log chứa **full state**, **delta**, hay **domain event**?
- Delete và TTL có được ghi?
- Events trước/sau schema upgrade đọc được không?
- Ordering bảo đảm theo key/partition hay toàn cục?
- Có gaps do connector downtime hoặc source log rollover không?
- Có snapshots/checkpoints để tránh replay từ đầu không?
- Có encryption keys, credentials, topic ACL và backup log không?
- Có event ID hoặc source version để chống trùng?
- Có đủ context để tính lại enrichment không?

### 9.1. Retention là một phần của recovery plan

Ví dụ DynamoDB Streams có cửa sổ lưu giữ giới hạn; không thiết kế kế hoạch rebuild kéo dài nhiều ngày với giả định stream còn lịch sử vô hạn. Kafka topic cũng có retention và cleanup policy cụ thể; phải ghi cấu hình thực.

### 9.2. Log compaction không đồng nghĩa có lịch sử sự kiện hoàn chỉnh

Một compacted Kafka topic có thể giữ trạng thái mới nhất theo key (và cơ chế tombstones/retention của nó), phù hợp cho một số state reconstruction nhưng **không giữ mọi domain event theo thời gian**. Những projection cần tổng doanh thu theo từng giao dịch có thể không tính lại được từ các bản ghi trạng thái cuối.

### 9.3. CDC không phải event sourcing

CDC thường ghi **thay đổi của storage**; event sourcing ghi các sự kiện miền được thiết kế là lịch sử có nghĩa nghiệp vụ. Chúng có độ đầy đủ, ordering, retention và semantics khác nhau.

## 10. Event sourcing và CDC: rebuild khác nhau thế nào?

| Thuộc tính | Event-sourced log | CDC feed |
|---|---|---|
| Ý nghĩa event | Hành động/sự kiện domain | Row/document mutation |
| Nguồn authoritative | Có thể chính event store | Thường là database |
| Retention | Thường theo yêu cầu audit/replay, nhưng phụ thuộc cấu hình | Thường giới hạn bởi log/oplog/stream |
| Payload | Domain intent hoặc state transition | Before/after/delta/key |
| Replay | Có thể tái lập aggregate/projection nếu đủ events | Có thể phục hồi projections trong retention/snapshot |
| Delete | Cần event hợp lệ | Delete/tombstone mutation |
| Schema evolution | Event version migration | Source schema/connector converter changes |
| Gap handling | Event log integrity/seq number | Change feed cursor/retention/checkpoint |

### 10.1. Không mặc định CDC là một bản backup hoàn chỉnh

Nếu source data bị xóa và CDC chỉ giữ changes gần đây, CDC không giúp tái tạo các records chưa hề đổi trong thời gian retention.

### 10.2. Không mặc định event-sourcing replay không mất dữ liệu

Nếu event log bị truncate, schema cũ không đọc được hoặc side effects không idempotent, replay vẫn có thể sai.

## 11. Sự kiện toàn phần và delta mutation

Một event **full state**:

```json
{
  "eventId": "evt-17",
  "entityId": "O100",
  "version": 7,
  "type": "ORDER_UPSERT",
  "after": {
    "status": "PAID",
    "amountMinor": 250000,
    "customerId": "U42"
  }
}
```

Một event **delta**:

```json
{
  "eventId": "evt-17",
  "entityId": "O100",
  "version": 7,
  "type": "ORDER_STATUS_CHANGED",
  "status": "PAID"
}
```

### 11.1. Full-state upsert

Nếu projector có sourceVersion guard, có thể ghi tài liệu mới nhất mà không cần mọi intermediate events, nhưng cần xử lý xóa và những fields thu thập từ nhiều nguồn.

### 11.2. Delta bắt buộc có baseline

Không thể áp `+5 availableStock` vào một kho trống mà không biết số ban đầu hoặc đủ toàn bộ events từ origin. Nếu một event bị thiếu, tổng sai.

### 11.3. `Set` và `Increment` không cùng tính idempotent

Áp `set stock=10,version=3` hai lần có thể an toàn. Áp `increment stock by +10` hai lần có thể làm số tồn tăng gấp đôi. Vì vậy cần idempotency key/deduplication/transaction.

## 12. Version và event identity

Một envelope hữu ích:

```json
{
  "eventId": "01J...opaque",
  "source": "OrderService",
  "aggregateType": "Order",
  "aggregateId": "O100",
  "aggregateVersion": 42,
  "schemaVersion": 3,
  "operation": "UPSERT",
  "occurredAt": "2026-11-14T09:00:00Z",
  "payload": {
    "status": "PAID"
  }
}
```

### 12.1. Khác biệt giữa event ID và aggregate version

- **Event ID:** phân biệt từng event để deduplicate.
- **Aggregate version:** thứ tự logic của các thay đổi trên cùng entity.
- **Partition offset:** vị trí trong một shard/log partition.
- **Wall-clock timestamp:** hỗ trợ audit nhưng không đủ để áp total ordering.
- **Projection version:** phiên bản logic transformer/index format.

Không dùng một trường thay thế tất cả.

### 12.2. Event ID có thể không tồn tại trong CDC native

Một số change feeds dùng resume token/sequence number/source transaction metadata. Adapter phải thiết kế identity dedupe phù hợp. Không tự sinh UUID mới mỗi lần đọc nếu muốn chống trùng qua retries.

### 12.3. Timestamps không phải luôn đơn điệu

Clock skew, backfill, event delivery delays và multi-region writes khiến timestamp cũ đến sau timestamp mới. Ưu tiên source version/sequence và domain conflict rule.

## 13. Ordering: theo key, partition, transaction và toàn cluster

Nhiều hệ stream bảo đảm ordering **trong một partition/shard** hoặc cho một entity nếu tất cả events của nó vào cùng partition, chứ không có một total order toàn cluster.

Ví dụ:

```text
Partition 0: O100 v1 -> O100 v2 -> O100 v3
Partition 1: O200 v1 -> O200 v2
```

### 13.1. Partition by aggregate ID

Một quy tắc thường hữu ích: chọn `aggregateId` làm message key để giữ thay đổi của cùng entity trong cùng partition theo thời gian phù hợp. Nhưng việc resize/reshard topics, transaction boundaries và source-specific rules vẫn cần đánh giá.

### 13.2. Multi-entity projection

Một `CustomerSummary` kết hợp Order và Payment từ hai streams có thể không có total order chung. Cần join theo IDs, version vectors, event-time watermarks hoặc reconciliation, tùy guarantee yêu cầu.

### 13.3. Gap detection

Nếu nhận `O100 v8` sau `v6`, không nên áp `v8` như delta liên tục nếu `v7` chưa xử lý. Có thể buffer có giới hạn, fetch source state authoritative, hoặc đưa record vào retry/quarantine.

### 13.4. Không chỉ dùng arrival order

Network và consumer rebalance có thể đổi thời gian sự kiện đến worker; ordering phải bám contract của source.

## 14. Idempotency: sự kiện lặp không được tạo dữ liệu lặp

Một consumer thường có delivery **at least once**: khi crash, event đã apply có thể lại được đọc. Hệ phải chấp nhận replay mà không làm sai projection.

### 14.1. Upsert theo key và version

```text
apply(event):
  if event.version <= stored.sourceVersion:
      skip
  else:
      replace projection with event state
      set sourceVersion = event.version
```

Quy tắc này hợp với **full-state snapshot** cùng version đơn điệu; không tự áp cho delta thiếu intermediate events.

### 14.2. Dedupe record

Có thể lưu `processedEventIds` hoặc watermark per aggregate. Nhưng lưu vô hạn mọi event ID trong DB sẽ tốn storage; chọn chiến lược theo replay window và semantics.

### 14.3. Idempotency có phạm vi

Một event dẫn đến cập nhật search index **và** gửi email thì replay không được gửi lại email cho khách. Recovery projector nên tách side-effecting actions khỏi pure projection, hoặc dùng idempotency riêng.

### 14.4. Exactly-once claim cần xét cả hai hệ

Broker transactions chỉ bảo đảm một phạm vi; không tự tạo transaction atomic giữa Kafka offsets và Elasticsearch/Redis/graph store. Thực tế thường là at-least-once + idempotent sink + checkpoint sau commit.

## 15. Checkpoint: ghi nhận điều gì đã áp dụng thành công?

Consumer có một checkpoint/offset:

```text
Read event 100
  |
  v
Transform
  |
  v
Write derived store
  |
  v
Confirm persistence/visibility contract
  |
  v
Commit checkpoint 100
```

### 15.1. Sai thứ tự gây mất dữ liệu

```text
Commit checkpoint 100
  |
  v
Crash before sink write
```

Khi restart từ 101, event 100 có thể bị **bỏ vĩnh viễn** khỏi projection.

### 15.2. Ghi trước rồi checkpoint

```text
Sink write event 100 succeeds
  |
  v
Crash before checkpoint
  |
  v
Replay event 100 again
```

Đây là tình huống **duplicate**, cần xử lý bằng idempotency. Nó thường an toàn hơn mất event nếu sink thiết kế đúng.

### 15.3. Checkpoint không nhất thiết đồng nghĩa search visible

Elasticsearch có refresh/visibility lifecycle; một bulk write ACK không tự chứng minh query đã thấy version mới ngay. Phải định nghĩa checkpoint theo sink durability và nghiệm thu cutover kiểm tra visibility riêng.

## 16. Atomic apply + checkpoint khi nào cần?

Nếu sink và checkpoint nằm trong **cùng một transactional store**, có thể commit dữ liệu + vị trí atomically. Nếu checkpoint ở Kafka mà index ở Elasticsearch, không có distributed transaction chung chỉ vì app dùng `@Transactional`.

### 16.1. Mô hình at-least-once đáng vận hành

- Đọc event.
- Validate schema và source version.
- Áp vào sink idempotently.
- Chờ ACK theo semantics.
- Commit/checkpoint source position.
- Retry nếu lỗi tạm.
- Quarantine nếu lỗi dữ liệu.
- Monitor sink lag và duplicate attempts.

### 16.2. Nếu sink đã thành công nhưng ACK mất

Client thấy timeout nhưng index có thể đã ghi xong. Retry cùng event ID/version và upsert semantics giúp không sinh hai bản ghi.

### 16.3. Long-running batch

Nếu batch 1000 records và 10 fail, không commit checkpoint vượt qua failed records nếu contract yêu cầu xử lý đầy đủ và không có durable retry ledger. Tách success/partial failures rõ theo API.

## 17. Deletes, tombstones và dữ liệu bị sống lại

Delete thường là nơi rebuild sai nghiêm trọng nhất.

Tình huống:

```text
T0: snapshot contains User U42
T1: source deletes U42
T2: CDC emits DELETE U42
T3: projector deletes U42 from new index
T4: slow snapshot worker writes old U42 again
```

Nếu không có giao thức thứ tự/version, **dữ liệu đã bị xóa có thể xuất hiện lại**.

### 17.1. Tombstone trong projection

Một cách là giữ tombstone/version marker:

```json
{
  "id": "U42",
  "sourceVersion": 18,
  "deleted": true
}
```

Trong read path, không trả tombstones. Cơ chế xóa vật lý sau retention phải tôn trọng việc event/snapshot cũ còn có thể phát lại.

### 17.2. Snapshot sau event

Khi replay/tail và backfill chạy đồng thời, cần **version-gated writes** hoặc tập trung tail apply sau backfill với protocol snapshot boundary rõ; không để snapshot cũ overwrite DELETE mới.

### 17.3. Delete event có thể không chứa full object

CDC thường có delete key và metadata, không nhất thiết có `after` document. Projector phải xử lý theo operation type, không coi `after=null` là lỗi parse.

### 17.4. Data removal & privacy

Delete mang nghĩa quyền riêng tư/tuân thủ không thể chờ “sau này compaction tự xử lý” nếu query vẫn hiển thị data. Recovery phải tôn trọng deletion ledger/retention policy và không recreate erased PII từ backup lịch sử trái policy.

## 18. TTL và dữ liệu hết hạn khi rebuild

TTL có thể áp dụng tại source, cache hoặc derived store. Các lựa chọn khác nhau:

```text
Source expires item at expiresAt
Derived store follows source expiration
```

### 18.1. Không reset thời hạn vô tình

Nếu bản ghi tạo T0, TTL 24 giờ, rebuild tại T0+23 giờ và set TTL mới 24 giờ từ lúc rebuild, nó sống lâu thêm 23 giờ so với nguồn. Nếu domain yêu cầu expiration tuyệt đối, tái dựng bằng `expiresAt` từ source.

### 18.2. Key đã expired không xuất hiện trong snapshot

Khi rebuild từ current source state, expired items có thể đã biến mất. Nếu event log có record cũ, projector không được tái tạo nó mà bỏ qua policy expiration.

### 18.3. Async TTL deletions

Một số database thực thi TTL cleanup bất đồng bộ; không mặc định sẽ có delete event đúng tại timestamp expire cho mọi system/stream. Dùng `expiresAt` và đọc state theo policy hoặc reconciliation.

### 18.4. Search freshness

Một item hết hạn có thể còn trong search index cho đến khi delete/invalidation được xử lý. Nếu đây là quyền hiển thị quan trọng, áp filter expiration/authorization tại read path hoặc một cơ chế xóa được kiểm chứng.

## 19. Replay sau thay đổi schema và logic projection

Một event v1:

```json
{
  "schemaVersion": 1,
  "total": "123.45",
  "currency": "USD"
}
```

Event v3:

```json
{
  "schemaVersion": 3,
  "totalMinor": 12345,
  "currencyCode": "USD"
}
```

### 19.1. Reader supports historical versions

Một projector muốn replay lịch sử phải đọc được **mọi event version còn trong retained log hoặc snapshot**, không chỉ phiên bản mới nhất.

### 19.2. Upcaster

Có thể chuyển payload cũ về logical model chung:

```text
Event v1 --upcast--> Canonical Event v3
Event v2 --upcast--> Canonical Event v3
Event v3 ------------> Canonical Event v3
```

Cần version, tests và mã transform đủ ổn định.

### 19.3. Nghiệp vụ đã thay đổi

Nếu từ năm ngoái tới nay business rule tính chiết khấu đổi, replay old events bằng rule hiện tại có thể cho kết quả khác lịch sử. Phải quyết định muốn **reproduce old projection** hay **recompute with current business semantics**, và ghi choice.

### 19.4. External enrichment

Một event cũ thiếu tên sản phẩm; projector gọi Product Service hiện tại sẽ lấy tên mới. Muốn historical view đúng phải có as-of data/version, hoặc công bố đây là **current-state projection**.

## 20. Multi-source projections và join không nguyên tử

Ví dụ một search document:

```json
{
  "orderId": "O100",
  "customerName": "Lan",
  "paymentState": "CAPTURED",
  "warehouse": "HCM-1"
}
```

Nó có thể kết hợp Orders, Customers, Payments và Warehouse.

### 20.1. Nhiều sources không chung snapshot point

Nếu Orders snapshot ở T0 và Payments ở T1, một projection có thể tạo trạng thái chưa bao giờ cùng tồn tại. Cần temporal consistency policy hoặc chấp nhận eventual joins với reconciliation.

### 20.2. Version vector

Một document có thể lưu:

```text
orderVersion: 12
paymentVersion: 7
customerVersion: 3
warehouseVersion: 9
projectionVersion: 4
```

Điều này giúp biết các nguồn nào còn trễ; không mặc định một timestamp đủ.

### 20.3. Missing dependencies

Nếu Order event đến trước Customer record, projector có thể giữ pending join có giới hạn, fetch authoritative source, hoặc tạo partial document với marker theo policy; cần quyết định rõ khi phục hồi.

### 20.4. Tái tạo đúng không đồng nghĩa identical byte-for-byte

Search tokenization, field order hay các metadata nội bộ có thể khác mà kết quả nghiệp vụ tương đương. Chọn verification theo semantics của projection.

## 21. Chọn ranh giới phục hồi: toàn kho hay một phạm vi?

Các chiến lược có thể ở các mức:

- Toàn bộ search index.
- Một tenant.
- Một collection/table.
- Một Kafka partition.
- Một token range/shard.
- Một aggregate ID.
- Một khoảng thời gian.
- Một nhóm keys có version mismatch.
- Một bộ materialized view.

### 21.1. Targeted rebuild nhanh nhưng cần điều kiện

Nếu chỉ một tenant bị lỗi, rebuild riêng tenant có thể giảm RTO. Nhưng cần chắc input scope đầy đủ, query/ACL target đúng và không bỏ changes cross-tenant liên quan.

### 21.2. Per-key reproject

Với record thiếu ở search, có thể fetch state hiện tại từ source rồi upsert/delete theo key. Đây là giải pháp repair nhỏ, nhưng không thay full reconciliation nếu không biết còn bao nhiêu keys sai.

### 21.3. Quét theo time không phải lúc nào đủ

Một lỗi indexing từ T0 đến T1 có thể ảnh hưởng records được **xóa sau đó**, và records có `updatedAt` sai hoặc late events. Scope phải xác định bằng nguồn/offset/changelog, không chỉ `updatedAt` nếu nó không bảo đảm coverage.

## 22. Hướng tiếp cận recovery theo mức độ mất dữ liệu

```text
Derived store unhealthy?
          |
          v
Can restore verified backup and replay retained tail?
          |
      yes +--> Restore + catch up + validate
          |
         no
          |
          v
Is full event history available and sufficient?
          |
      yes +--> Replay from origin/checkpoint
          |
         no
          |
          v
Is authoritative current state available?
          |
      yes +--> Snapshot/backfill + tail + reconcile
          |
         no
          |
          v
Escalate authoritative data recovery;
do not invent missing business state
```

### 22.1. Backup restore có thể tiết kiệm thời gian

Một verified snapshot của search index chỉ cần replay 15 phút thay đổi thường nhanh hơn full rebuild, nếu format/version/permissions phù hợp.

### 22.2. Backup cũ có thể chứa records đã xóa

Restore phải **replay deletes** hoặc chạy reconciliation với source trước khi công bố phục hồi. Đặc biệt thận trọng với dữ liệu nhạy cảm.

### 22.3. Restore không phải lúc nào rẻ hơn rebuild

Nếu snapshot/index format không tương thích target version, một fresh index rebuild có thể an toàn hơn ép restore.

## 23. Phát lại sự kiện: thuật toán khái quát

```text
Input:
  source stream + persisted checkpoint
  projection transformation version
  target index/bucket/schema

for each source partition:
  load checkpoint and source retention boundary
  verify checkpoint is still recoverable

  while events available:
    read next event batch
    validate event schema / operation
    transform into derived mutation
    apply idempotently to target
    inspect partial failures
    persist checkpoint after successful apply

  report lag, blocked events and verification status
```

### 23.1. Sai lầm: commit offset khi chưa xử lý lỗi

Nếu batch có failed documents mà consumer commit tới offset cuối, missing records có thể không còn được replay tự động.

### 23.2. Không xử lý quá vô hạn

Giới hạn batch size, bytes, in-flight operations, retries, memory queue và deadline. Một lần replay hàng tỷ events cần backpressure.

### 23.3. Watermark khác wall clock

Vị trí bền vững trong log như partition+offset, resume token hoặc shard sequence có giá trị tái đọc chính xác hơn một `updatedAt` của app nếu clock/ordering không bảo đảm.

### 23.4. Không tự đo “đã hoàn tất 100%” với log liên tục

Khi source vẫn ghi, target moving; có thể đạt **lag dưới ngưỡng và không còn gap** chứ không đòi 0 events mới vĩnh viễn.

## 24. Rebuild bằng snapshot: yêu cầu về tính nhất quán

Một bản sao dữ liệu từ source có thể là:

1. **Consistent point-in-time snapshot:** trạng thái dữ liệu tại một mốc logic đã xác định.
2. **Paginated scan trên dữ liệu đang thay đổi:** mỗi page có thể phản ánh thời điểm khác nhau.
3. **Backup/snapshot file do database tạo:** có metadata/consistency guarantees phụ thuộc engine.
4. **Export qua API:** có thể được biến đổi, lọc tenant hoặc bỏ fields.
5. **Full database cursor:** hiệu quả cho streaming nhưng không nhất thiết cung cấp snapshot isolation xuyên toàn collection.

### 24.1. Chọn snapshot consistency rõ ràng

Một yêu cầu “scan tất cả records” không bảo đảm mỗi record biểu thị cùng một thời điểm. Dữ liệu được thêm/xóa giữa các trang có thể gây duplicates hoặc misses theo query/pagination semantics.

### 24.2. Không lấy total count làm điều kiện duy nhất

Trong lúc source đổi, `count=20M` tại T0 và 20M tại T1 không chứng minh hai sets có cùng keys.

### 24.3. Mức độ nhất quán tùy sản phẩm

MongoDB, Cassandra, DynamoDB và các hệ managed có khả năng point-in-time snapshot, transactional reads hoặc backup/export khác nhau. Chọn **API thực sự bảo đảm** snapshot boundary cần thiết, thay vì suy từ từ “snapshot”.

### 24.4. Không giữ transaction read cực lớn một cách mù quáng

Một transaction snapshot kéo dài nhiều giờ có thể gây pin versions, tăng log/storage và ảnh hưởng nguồn. Dùng backup/export facility hoặc một thiết kế backfill theo version/cursor phù hợp.

## 25. Quy trình snapshot + tail không mất khoảng trống

Mục tiêu: vừa nạp dữ liệu hiện có, vừa bắt kịp writes mới.

Một mô hình an toàn phải tạo được quan hệ rõ giữa **snapshot state** và **change stream bắt đầu từ đâu**.

```text
t0: Start durable change capture / record valid stream boundary
     |
     +-------------------+
     |                   |
     v                   v
Take consistent       Persist stream cursor/log position
source snapshot       (for changes during and after snapshot)
     |
     v
Backfill snapshot -> New index, no public traffic
     |
     v
Replay/tail captured changes in correct order
     |
     v
Catch up to near-live source
     |
     v
Verify source/index parity + ACL/deletes
     |
     v
Atomic/controlled cutover of read alias
```

**Điều kiện then chốt:** stream cursor và snapshot phải tạo thành một handoff có coverage. Nếu source snapshot có timestamp/version S, stream phải cho phép replay đủ mọi thay đổi sau S mà không có gap. Không thể tùy tiện lấy “thời điểm bắt đầu scan” làm token nếu API không cung cấp bảo đảm tương ứng.

### 25.1. Capture-before-scan khi không có atomic snapshot+cursor API

Một phương án là bắt đầu capture bền trước khi quét, giữ toàn bộ changes suốt backfill, sau đó áp changes với chiến lược version/gap handling. Cách này giảm rủi ro bỏ sót, nhưng **không tự biến một scan không nhất quán thành một snapshot nhất quán**; cần protocol xử lý races và reconciliation.

### 25.2. Không áp tail rồi để snapshot ghi đè

Nếu projector ghi `DELETE` sau T0 rồi một page snapshot cũ ghi `UPSERT`, record bị sống lại. Có thể áp tail **sau** hoàn tất snapshot theo thứ tự đáng tin, hoặc dùng per-key version/tombstone để từ chối dữ liệu cũ.

### 25.3. Ranh giới các sources khác nhau

Khi projection có nhiều sources, snapshot boundary và stream cursor có thể khác theo source. Cần vector checkpoints và join policy, không tự dùng một global timestamp chung khi source không hỗ trợ.

## 26. Watermark: đã xử lý tới đâu?

Có nhiều watermark:

```text
Source latest committed position:  P_source
CDC connector published position:  P_capture
Consumer read position:            P_read
Sink applied position:             P_applied
Sink query-visible position:       P_visible (if tracked)
```

### 26.1. Lag theo các điểm khác nhau

- Source→capture lag.
- Capture→consumer lag.
- Consumer→sink apply lag.
- Apply→visible lag.
- End-to-end data freshness lag.

### 26.2. Không lấy offset lớn nhất của các partitions làm một global offset

Các partitions không có cùng sequence space. Dùng checkpoint map:

```json
{
  "topic": "orders-events",
  "partitions": {
    "0": 125000,
    "1": 99200,
    "2": 130012
  }
}
```

Đây chỉ là ví dụ một vector offset. Một shard split/merge hoặc topic repartitioning cần thêm identity/generation metadata.

### 26.3. Watermark ứng dụng

Để cutover, có thể chụp **cutover barrier** là source position sau khi hoàn tất backfill, sau đó yêu cầu từng sink partition áp tới barrier và query correctness checks pass. Nếu system không expose cross-partition atomic barrier, nêu giới hạn và dùng bounded freshness SLO.

### 26.4. Không đồng nhất “lag 0” với dữ liệu đúng

Consumer có thể bỏ event invalid vào DLQ rồi commit offset; lag về 0 nhưng projection thiếu dữ liệu. Kiểm chứng gap/failed records riêng.

## 27. Backfill không nên dùng offset pagination tùy tiện

Ví dụ:

```text
SELECT ... OFFSET 500000 LIMIT 1000
```

Trong source đang thay đổi, offset sâu có thể tốn scan, và insert/delete trước trang làm records bị lặp hoặc bỏ sót.

### 27.1. Keyset/continuation pagination

Ưu tiên pagination bằng stable ordering key hoặc continuation token do API cung cấp:

```text
after = lastProcessedKey
page = scan(after, pageSize)
persist lastProcessedKey
```

### 27.2. Key phải thật sự ổn định

Nếu sort theo `updatedAt` có thể đổi giữa pages, record di chuyển; keyset chỉ an toàn khi ordering/scan consistency thỏa policy. Một unique immutable key hoặc source-native cursor thường phù hợp hơn.

### 27.3. Chia ranges

Với dữ liệu rất lớn, chia bằng partition keys, hash ranges, token ranges hoặc shard-specific export. Lưu worker assignments và range checkpoints để restart không quét lại tất cả.

### 27.4. Đảm bảo không bỏ deletes

Một key đã xóa trong lúc scan sẽ không còn trong snapshot. Tail phải mang thông tin DELETE hoặc reconciliation phải xóa key ở target, không chỉ nạp các records còn sống.

### 27.5. Rate limit

Page size 1000 không bảo đảm mỗi page < 1 MiB. Giới hạn cả response bytes, concurrency và memory buffers.

## 28. Snapshot worker và tail worker chạy song song có an toàn không?

Có thể, nếu thiết kế điều phối đúng. Có ba pattern phổ biến.

### 28.1. Pattern A: backfill trước, tail sau

```text
Capture buffered events from valid boundary
       |
       v
Backfill source snapshot fully
       |
       v
Replay buffered events in source order
       |
       v
Cutover
```

Dễ lý giải thứ tự, nhưng cần đủ retention/buffer cho mọi thay đổi trong lúc backfill và xử lý snapshot consistency boundary chính xác.

### 28.2. Pattern B: đồng thời với version fencing

```text
Backfill row with sourceVersion=20
Tail event with sourceVersion=21
Sink applies only if incomingVersion > currentVersion
```

Có thể giảm catch-up time, nhưng cần **atomic compare-and-set/update** tại sink hoặc cơ chế serialization per key. Nếu `read version -> check -> write` không atomic, hai workers vẫn race.

### 28.3. Pattern C: per-key barrier/ownership

Mỗi key/range có giai đoạn snapshot và tail riêng. Worker đánh dấu range backfill complete rồi chuyển quyền apply stream changes cho range ấy. Hữu ích ở các hệ có snapshot streaming protocol, nhưng phức tạp về coordinator/checkpoint.

### 28.4. Không tự lấy timestamp khách hàng làm version

Nếu source `updatedAt` do client gửi, một event mới có timestamp cũ vẫn có thể hợp lệ. Cần version do authority cấp hoặc conflict-resolution policy có thể kiểm chứng.

## 29. Dựng index mới và cutover bằng alias

Khi search index hiện tại còn phục vụ, không nên rebuild trực tiếp bằng cách xóa sạch nó rồi nạp lại nếu có thể dùng **versioned index**.

```text
orders-search-v6  <-- public read alias: orders-search
orders-search-v7  <-- backfill, replay, validate (hidden)
```

Sau khi v7 đủ điều kiện:

```text
Alias orders-search
    remove v6
    add    v7
```

### 29.1. Atomic alias switch

Elasticsearch/OpenSearch có cơ chế update aliases trong một thao tác cluster metadata phù hợp; cần dùng API và điều kiện hỗ trợ cụ thể. Với cache/read models khác, có thể dùng routing config, feature flag hoặc pointer do app quản lý.

### 29.2. Trước cutover

- New index mappings/analyzers đúng.
- Source-to-index key/version parity.
- Deletes/tombstones không bị sống lại.
- Query results/projection ACL đúng.
- CDC tail lag dưới ngưỡng.
- Cluster đủ capacity để chịu production reads.
- Refresh/visibility behavior phù hợp.
- Retry/error/DLQ không còn trạng thái chưa xử lý nghiêm trọng.

### 29.3. Sau cutover

Giữ old index trong một khoảng rollback window nếu policy/PII retention cho phép, nhưng **đừng khôi phục về old index nếu nó tiếp tục stale** và không có đồng bộ ngược. Thử query và đo SLO sau switch.

### 29.4. Không xóa old index quá sớm

Một query mapping bug phát hiện sau 10 phút có thể cần quay alias; tuy nhiên rollback alias chỉ đúng nếu dữ liệu cũ vẫn được tail-sync hoặc freshness contract cho phép. Quay lại bản stale trái bảo mật là không chấp nhận được.

## 30. Shadow reads và so kết quả trước chuyển traffic

Thay vì chuyển khách hàng trực tiếp sang index mới, có thể chọn một phần reads để chạy **song song** trên index cũ và mới:

```text
Client query
     |
     v
Primary read -> old index -> response
     |
     +--> shadow read -> new index -> compare; no user response
```

### 30.1. Những điều cần so

- Missing/extra document IDs.
- Status, price, tenant visibility.
- Sort order, page token validity.
- Search relevance/top-K overlap.
- Query latency và error rates.
- Data version/freshness.

### 30.2. So sánh đúng loại kết quả

Full-text relevance và ANN vector search có thể không deterministic tuyệt đối; chọn metric phù hợp như recall@K, click/business relevance và deterministic filters/invariants.

### 30.3. Shadow traffic cũng tốn tải

Không shadow 100% production QPS lên index mới chưa đủ capacity. Sample và rate-limit, không nhân đôi writes có side effects.

### 30.4. PII/authorization

Shadow queries phải dùng cùng tenant/ACL scope, không log raw search results nhạy cảm và không vô tình cấp quyền rộng cho runner.

## 31. Recovery khi nguồn tiếp tục tạo traffic

Một chiến lược khôi phục tốt cho cả source và sink:

- Không để backfill làm source CPU/disk quá tải.
- Dùng read replicas hoặc snapshot export nếu consistency/availability cho phép.
- Giữ đủ retention cho CDC.
- Cho foreground transactions quyền ưu tiên cao hơn.
- Tăng sink bulk throughput từ từ.
- Quan sát lag và tốc độ drain.
- Có tạm ngừng/điều chỉnh worker khi SLO bị ảnh hưởng.
- Không đóng băng writes nghiệp vụ trừ khi đã có kế hoạch/phê duyệt rõ.

### 31.1. Điều kiện hoạt động ổn định

Nếu source generates 10k events/s, sink xử lý sustained 11k/s, backlog 100 triệu events sẽ mất rất lâu để giảm. Có thể cần tăng capacity, tối ưu transform hoặc tạo snapshot mới thay vì chỉ cố replay.

### 31.2. Parallelism phải tôn trọng key ordering

Tăng worker concurrency có thể giúp throughput, nhưng events cùng key phải được serialize hoặc dùng version guards. Không tối ưu tốc độ bằng cách phá thứ tự.

### 31.3. Network/data transfer costs

Rebuild 20 TiB xuyên vùng có thể tốn tiền và saturate WAN. Đặt recovery region/topology và bandwidth budget trong plan.

## 32. Backpressure, batching và partial failures

Pipeline:

```text
Source scan/stream
        |
        v
Bounded in-memory queue
        |
        v
Transformer / enrichment workers
        |
        v
Batch writer
        |
        v
NoSQL derived sink
```

### 32.1. Bounded queue

Nếu ingress nhanh hơn sink, queue cần có giới hạn. Khi đầy, source reader giảm tốc/stop polling hoặc spill an toàn; không tạo `List` vô hạn.

### 32.2. Batch size

Theo số documents **và** bytes:

```text
maxItemsPerBatch: 500
maxBytesPerBatch: 4 MiB
maxInFlightBatches: 8
```

Giá trị minh họa. Một item rất lớn cần được xử lý riêng, reject hoặc chuyển sang đường thích hợp.

### 32.3. Partial success

Nhiều bulk APIs có response per item. HTTP 200 ở batch không đồng nghĩa mọi document đã được ghi. Commit checkpoint chỉ sau khi tất cả entries quan trọng xử lý thành công hoặc có durable recovery ledger.

### 32.4. Retry storm

Tăng concurrency khi sink đang trả 429/503 có thể làm lỗi tăng. Dùng exponential backoff, jitter, quotas và retry budget.

### 32.5. Poison items

Một document sai mapping có thể bị lỗi vĩnh viễn. Phải phân biệt lỗi transient và lỗi deterministic schema/data, tránh retry vô tận làm kẹt toàn stream.

## 33. Recovery theo tenant hoặc partition để giảm blast radius

Một kho dẫn xuất multi-tenant có thể chia recovery:

```text
Tenant A -> backfill + tail -> verify -> cutover
Tenant B -> backfill + tail -> verify -> cutover
Tenant C -> backfill + tail -> verify -> cutover
```

### 33.1. Ưu điểm

- Khôi phục dịch vụ từng phần.
- Giảm tải đột ngột lên source.
- Dễ đo correctness per tenant.
- Giới hạn phạm vi nếu mapping bug.

### 33.2. Rủi ro

- Một index chung có mappings/aliases toàn cục.
- Quan hệ cross-tenant có thể xuất hiện trong dữ liệu.
- Partition assignments đổi khi rebalancing.
- Traffic load không đều.
- Tenant nào được ưu tiên có thể liên quan SLA/hợp đồng.

### 33.3. Chính sách cutover

Mỗi tenant có state:

```text
NOT_STARTED -> SNAPSHOTTING -> REPLAYING
             -> VALIDATING -> SERVING
             -> FAILED/PAUSED
```

Không route tenant sang target nếu chưa qua guardrails.

## 34. Recovery graph projection

Graph projection có thể xây từ các entities và relationships trong nguồn:

```text
Users -----> Follow edges
Products --> Similarity edges
Orders ----> PurchasedBy edges
```

### 34.1. Node và edge là hai pha có phụ thuộc

Nếu build edges trước nodes, có thể tạo dangling references hoặc failed writes tùy graph DB. Một pattern là:

1. Tạo nodes/entities với stable IDs.
2. Tạo relationships sau khi endpoints có mặt.
3. Replay edge additions/deletions.
4. Reconcile orphan edges và property versions.

### 34.2. Deletes và cascade

Xóa một User có thể yêu cầu xóa edges tham chiếu và các derived recommendations, không chỉ node. Tránh tái tạo erased relationships từ old event log.

### 34.3. Business correctness

Một graph recommendation có thể approximate, nhưng graph ACL/ownership phải chính xác. Shadow comparisons nên tập trung connectivity invariants, reachability và restricted edges.

### 34.4. Version mapping

Nếu key format của nodes thay đổi giữa schema versions, cần deterministic migration để không tạo hai nodes đại diện cùng entity.

## 35. Khôi phục vector index và embeddings

Một semantic-search index thường có:

```text
Source document
    |
    v
Chunking / normalization
    |
    v
Embedding model
    |
    v
Vector metadata + ANN index
```

### 35.1. Không chỉ khôi phục vectors

Để tạo lại đúng, cần:

- Source content version.
- Chunking algorithm/version.
- Embedding model ID/version.
- Vector dimension.
- Normalization/distance metric.
- Metadata filters và ACL.
- ANN index parameters.
- Delete propagation.

### 35.2. Model drift

Một mô hình embeddings mới có thể tạo vectors khác từ cùng văn bản. Nếu muốn **exact restore**, cần lưu model artifacts và preprocessing version; nếu muốn **rebuild with new model**, đó là migration có đánh giá relevance.

### 35.3. Chunk identities

Chọn stable IDs ví dụ `(documentId, contentVersion, chunkIndex, modelVersion)` để upsert/dedupe. Nếu chunking thay đổi, cần xóa old chunks không còn tương ứng.

### 35.4. Rebuild cost

GPU/API inference có thể là bottleneck lớn hơn DB write. Cần budget cho model calls, rate limits, failures, data privacy và RTO.

### 35.5. Retrieval correctness

Ngoài count/vectors, kiểm tra exact metadata filters, tenant ACL, recall@K, top-K overlap và latency.

## 36. Khôi phục Redis cache

Với **cache thuần dẫn xuất**, phục hồi có thể là:

1. Cold-start/lazy repopulate từ authoritative source.
2. Prefetch hot keys trước cutover.
3. Rebuild cache từ snapshot/source scan.
4. Tiếp tục invalidation/update events.
5. Dùng hai namespaces (`cache:v1`/`cache:v2`) trong migration.

### 36.1. Không đòi restore mọi cache key

Cache là tối ưu hiệu năng; nếu toàn bộ keys có thể được tải lại và RTO cho cache miss chấp nhận, warmup có chọn lọc có thể rẻ hơn bulk rebuild.

### 36.2. Cache stampede

Khi cache trống, hàng nghìn requests có thể cùng fetch key nóng. Cân nhắc request coalescing, bounded concurrency, TTL jitter, read-through policy hoặc hot-key prewarming.

### 36.3. TTL gốc

Không biến item sắp hết hạn thành item sống thêm cả ngày vì rebuild lại TTL từ đầu. Dùng `expiresAt`/source validity policy.

### 36.4. Cache invalidation

Một cache mới xây từ snapshot cần bắt kịp updates/deletes. Nếu không, cache trả dữ liệu cũ ngay sau cutover.

### 36.5. Không gọi Redis data authority là cache

Redis có thể là hệ chính cho session/counters/queues. Chỉ xóa/flush khi đã chứng minh nó là derived state hoặc dữ liệu có thể mất theo policy.

## 37. Khôi phục search index Elasticsearch/OpenSearch

Một recovery plan có thể:

```text
Create orders-v8 with mapping/settings
     |
Bulk index authoritative source snapshot
     |
Tail CDC / application events
     |
Refresh / verify
     |
Switch read alias from orders-v7 to orders-v8
     |
Monitor after cutover
```

### 37.1. Mapping/analyzer phải được version hóa

Index mới có thể thay tokenization, `keyword`/`text` fields, date formats hoặc vector dimensions. Rebuild sai mapping không sửa được bằng replay data đơn giản.

### 37.2. Stable document `_id`

Dùng ID có tính xác định từ authoritative source, ví dụ `tenantId:orderId` nếu IDs không globally unique, để replay không tạo duplicates.

### 37.3. Version-aware writes

Nếu snapshot và CDC cạnh tranh, có thể dùng cơ chế optimistic/external versioning khi được engine hỗ trợ và phù hợp version semantics, hoặc serialize per key qua ứng dụng. Không chỉ đọc `_source` version rồi ghi lại không atomic.

### 37.4. Bulk retries

Kiểm tra per-item outcomes, mappings conflicts, 429, 5xx. Chunk batches bounded, retry only retriable items; malformed documents cần dead-letter record và investigation.

### 37.5. Visibility

Search index có refresh semantics. Bulk ACK không đồng nghĩa vừa refresh xong; nghiệm thu bằng query trên target sau refresh theo policy.

### 37.6. Snapshot restore vs reindex

Nếu Elasticsearch snapshot đã được kiểm chứng và tương thích target cluster/index version, có thể restore nhanh rồi replay tail. Nếu không, reindex mới từ source thường rõ semantics hơn ép mở snapshot không hỗ trợ.

## 38. Khôi phục analytics/read model tổng hợp

Một kho phân tích không chỉ có một document cho mỗi source key. Nó có thể chứa:

```text
RevenueByDay
OrdersByStatusByRegion
TopProducts
CustomerLifetimeValue
InventoryTrend
```

### 38.1. Phép tính không phải luôn idempotent

Consumer gặp event `OrderPaid` hai lần mà chạy `totalRevenue += amount` hai lần sẽ tạo doanh thu gấp đôi. Cần dedupe hoặc recompute từ authoritative facts.

### 38.2. Rebuild từ raw facts

Một pattern ổn định là xây aggregates từ snapshots/facts đã được version hóa, group theo dimension và time window, rồi tail events sau barrier.

### 38.3. Retractions/corrections

Đơn hàng refund/reversal/cancel có thể tạo **negative contribution** hoặc phải recompute bucket; nếu chỉ phát lại increments cũ mà không xử lý corrections, tổng sẽ sai.

### 38.4. Event-time vs processing-time

Báo cáo theo ngày giao dịch phải gắn timezone/event time semantics. Rebuild bằng thời điểm consumer nhận lại events có thể chuyển doanh thu lịch sử sang ngày hôm nay — sai.

### 38.5. Reconciliation

So total với ledger/source query cho cùng watermark và currency/region; kiểm tra sum, count, unique IDs, refund corrections chứ không chỉ số rows.

## 39. Khôi phục materialized views/denormalized tables

NoSQL thường denormalize theo access pattern, ví dụ:

```text
orders_by_id
orders_by_customer
orders_by_status
```

### 39.1. Source authoritative là bảng nào?

Nếu `orders_by_id` là authority và hai bảng còn lại là read models, có thể rebuild chúng từ bảng gốc. Nhưng nếu hai bảng được ghi độc lập không có outbox/CDC và một bảng chứa fields riêng, không chắc dựng lại được đầy đủ.

### 39.2. Native materialized views khác application-managed projections

Một DB có engine-managed materialized view/secondary index khác ứng dụng tự viết worker. Tác vụ rebuild/drop/recreate và guarantees phải theo docs của phiên bản. Không tự giả định xóa native materialized view là vô hại.

### 39.3. Đảm bảo key/query access

Bảng read model phải dùng partition/sort key cho query thật. Rebuild đúng records nhưng key design sai có thể phá performance/cost.

### 39.4. Source updates sau snapshot

Mọi denormalized table cần theo nguồn mới, nếu không rebuild xong rồi stale ngay. Tạo CDC/outbox hoặc những cập nhật song song có đảm bảo và reconciliation.

## 40. MongoDB Change Streams và khôi phục index

MongoDB Change Streams có thể dùng để cập nhật derived read model/search, với các điều kiện về deployment, resume tokens, oplog retention và API version.

### 40.1. Resume token

Một consumer thường lưu resume token sau khi sink apply thành công, rồi dùng token đó để tiếp tục sau restart khi token còn hợp lệ.

### 40.2. Oplog retention

Change Streams không giữ history vô hạn. Nếu rebuild mất lâu hơn cửa sổ chứa changes cần thiết, token có thể không còn resumable; phải phát hiện và lập kế hoạch snapshot lại/reconcile.

### 40.3. Full document và update delta

Change event có thể chỉ gồm update description/delta, hoặc tùy options có fullDocument lookup với semantics nhất định. Không coi lookup document là snapshot chính xác ở đúng thời điểm event trong mọi trường hợp.

### 40.4. Snapshot handoff

Một consistent snapshot ở thời điểm cụ thể và change stream boundary cần giao thức/option đúng của MongoDB version. Không lấy timestamp app bất kỳ rồi assume đủ coverage.

### 40.5. Deletes

Delete event thường cần document key để xóa khỏi search. Nếu ID trong index chứa tenant scope, thiết kế index ID/mapping phải khớp source delete metadata.

### 40.6. Sharded source

Streams có thể đến từ nhiều shards; ordering và resuming cần dùng API semantics, không tự giả định một global offset số nguyên.

## 41. DynamoDB Streams và khôi phục GSI/read model ngoài

DynamoDB Streams là change feed cho table items. Nó hữu ích để cập nhật search/cache/analytics, nhưng có retention và view types giới hạn.

### 41.1. View types

Tùy stream configuration, event có thể chứa keys, new image, old image hoặc cả hai. Nếu projector cần full state mà stream chỉ có keys/delta, phải truy vấn source hoặc có snapshot tương thích.

### 41.2. Short retention

DynamoDB Streams giữ records trong khoảng thời gian giới hạn (thường 24 giờ theo dịch vụ). Không xây dựng phương án phục hồi nhiều ngày chỉ dựa vào stream; cần snapshot/export/PITR hoặc log bền riêng.

### 41.3. Shard sequence

Tracking checkpoint theo shards và lineage; không coi sequence numbers giữa shards là so được như một số nguyên global. Khi stream sharding/parent-child shards thay đổi, worker coordination cần theo semantics đúng.

### 41.4. Export/PITR

Có thể dùng export/backup facility làm nguồn backfill theo khả năng dịch vụ, nhưng phải xác định **điểm snapshot và cách nối stream tail**; export riêng không giải quyết changes xảy ra sau snapshot.

### 41.5. GSI native vs external index

DynamoDB GSI được quản lý bởi dịch vụ, khác một Elasticsearch index được user tự project từ Streams. Không áp cùng quy trình drop/rebuild index tùy ý cho native GSI.

### 41.6. Throttling/cost

Backfill read operations có thể tạo RCU/RU/cost và ảnh hưởng foreground traffic. Theo dõi capacity consumption, 429/throttling và per-partition hot spots.

## 42. Cassandra CDC và anti-entropy không phải cùng mục tiêu

Apache Cassandra có cơ chế CDC/commitlog liên quan theo version/distribution, còn các bản sao Cassandra dùng repair/hints để hội tụ dữ liệu.

### 42.1. CDC pipeline

Một CDC connector có thể đọc commitlog/change data, chuyển thành events rồi cập nhật sink. Khả năng đọc lại lịch sử phụ thuộc CDC retention/segment management và connector.

### 42.2. Anti-entropy repair không rebuild search

`nodetool repair` giải quyết sự hội tụ replicas Cassandra theo phạm vi, **không tự dựng lại Elasticsearch/Redis external projection**.

### 42.3. Đồng nhất snapshot và log

Một backfill Cassandra cần token ranges/partition traversal phù hợp và thiết kế handoff với CDC; không tự giả định mọi CDC implementation có global snapshot cursor.

### 42.4. Deletes/tombstones

Cassandra tombstone và TTL semantics ảnh hưởng CDC representation và dữ liệu trả về qua source reads. Projection không được làm resurrect records đã xóa.

### 42.5. Materialized view/index nội bộ

Native indexes/materialized views có quy trình repair/rebuild riêng theo engine, không trộn với application-managed read model.

## 43. Kafka: phát lại từ đâu, trong bao lâu?

Nếu Kafka là stream đưa sự kiện đến sink:

```text
Source -> Connector/Outbox -> Kafka partitions
                                   |
                                   v
                                Projector
                                   |
                                   v
                            Derived NoSQL store
```

### 43.1. Consumer group offsets

Khi tạo consumer group mới, lựa chọn đọc từ earliest/latest **phải phù hợp recovery boundary**. `latest` có thể bỏ qua toàn bộ sự kiện đang cần khôi phục.

### 43.2. Earliest không có nghĩa từ ngày đầu tiên

Kafka `earliest` trỏ tới record sớm nhất **còn được retention/cleanup policy giữ lại**, không phải toàn bộ lịch sử bất biến.

### 43.3. Per-partition offsets

Checkpoint/committed offsets phải có identity topic, partition, generation. Khi offset log không còn, producer-to-source recovery cần được kích hoạt.

### 43.4. Tombstone/compaction

Log-compacted topic có tombstones với cleanup rules. Nếu một key đã bị xóa nhưng tombstone bị cleanup theo policy, consumer rebuild từ compacted topic cần đảm bảo không còn old value được tái tạo do replay/snapshot lệch.

### 43.5. Exactly once

Kafka transactional consumer-producer semantics có thể giải quyết một số pipeline dùng Kafka làm sink/source; **không tự tạo atomicity với MongoDB/Elasticsearch/Redis**. Chọn idempotent sink và checkpoint protocol phù hợp.

## 44. Các kho khác: Couchbase, Cosmos DB, Firestore, graph

### 44.1. Couchbase DCP

Couchbase DCP có thể phục vụ change consumers/replication theo vBuckets và checkpoints, nhưng rollback/retention/stream semantics phải theo SDK/connector version. Nếu stream history không đủ, rebuild từ bucket/source và reconcile.

### 44.2. Azure Cosmos DB Change Feed

Consumer có feed-range leases/checkpoints, partition split/ownership changes và feed modes với semantics khác nhau. Khi rebuild search, cần bảo đảm mode có thông tin deletes cần thiết hoặc dùng separate soft-delete/TTL markers và source reconciliation.

### 44.3. Firestore documents và indexes

Firestore native indexes được dịch vụ quản lý; external projections có thể rebuild từ documents hoặc event triggers, với ordering/at-least-once caveats theo hệ. Index backfill status do dịch vụ cung cấp không tương đương source-to-external-index replay.

### 44.4. Neo4j graph projections

Rebuild từ source entities/relationships cần keys và referential invariants. Nếu source chính là Neo4j và projection là search/analytics, có thể quét graph snapshot hoặc dùng change events với compatibility/support theo version.

### 44.5. Nhận diện giới hạn API

Nếu managed service không expose replay từ điểm rất cũ, không tự phát minh offset/time-travel semantics; chọn backup/export và log bền riêng theo yêu cầu recovery.

## 45. Java: thiết kế envelope và projection contract

Một ví dụ Java 17 đơn giản để biểu diễn event:

```java
import java.time.Instant;

public record ProjectionEvent(
        String eventId,
        String aggregateId,
        long aggregateVersion,
        int schemaVersion,
        Operation operation,
        Instant occurredAt,
        String payloadJson
) {
    public enum Operation {
        UPSERT,
        DELETE
    }
}
```

### 45.1. Dùng typed payload khi hệ đủ ổn định

`payloadJson` ở đây chỉ để tách khỏi vendor SDK. Trong production, parse theo allowlisted schemaVersion/eventType với size/depth limits, không bật unrestricted polymorphic JSON deserialization.

### 45.2. `aggregateVersion` phải đến từ authority

Nếu consumer tự tăng version khi nhận event, event replay có thể đổi thứ tự. Version có tính quyết định cần được cung cấp/derive theo nguồn đáng tin.

### 45.3. Xác định delete semantics

`DELETE` phải gắn stable key và version. Nếu soft delete/retention, sink ghi tombstone marker hoặc remove public document theo policy.

### 45.4. Không dùng event ID để tạo document mới mỗi lần

Search document key phải dựa vào aggregate ID và tenant scope (khi cần); event ID là danh tính thay đổi, không phải danh tính entity.

## 46. Java: áp projection bằng CAS/version guard

Một interface giúp thể hiện điều kiện đúng, chưa gắn với SDK nào:

```java
import java.util.Optional;

public interface ProjectionSink {

    enum ApplyResult {
        APPLIED,
        STALE_IGNORED,
        RETRYABLE_FAILURE,
        PERMANENT_FAILURE
    }

    ApplyResult upsertIfNewer(
            String aggregateId,
            long sourceVersion,
            String canonicalDocument
    );

    ApplyResult deleteIfNewer(
            String aggregateId,
            long sourceVersion
    );

    Optional<Long> currentVersion(
            String aggregateId
    );
}
```

### 46.1. Không triển khai bằng read rồi write rời rạc

Đoạn logic:

```text
current = read version
if incoming > current:
    write incoming
```

có race nếu hai workers cùng cập nhật một entity. Implementation cần atomic conditional update, source-native versioning hoặc per-key serialized apply với fencing phù hợp.

### 46.2. Với Elasticsearch

Có thể dùng versioning/concurrency mechanism được hỗ trợ, hoặc một single-writer-per-key pipeline. Không tự coi `if_seq_no`/`if_primary_term` của Elasticsearch giống aggregateVersion từ source nếu chưa hiểu semantics.

### 46.3. Với Redis

Atomicity có thể dùng transaction/Lua với key scope phù hợp; nếu Redis Cluster, các multi-key operations có hạn chế cross-slot. Một cache thuần có thể dùng replace+invalidate đơn giản hơn nếu consistency được cho phép.

### 46.4. Tombstone retention

Nếu sink xóa vật lý mọi metadata version, một event UPSERT cũ có thể tạo lại document. Cần giữ deletion version/fencing đủ lâu so với replay window hoặc đưa deletion ledger vào design.

## 47. Java: trình xử lý event và điểm checkpoint

Một skeleton logic:

```java
import java.util.List;

public final class ProjectionConsumer {

    private final ProjectionSink sink;
    private final CheckpointStore checkpoints;
    private final EventDecoder decoder;

    public ProjectionConsumer(
            ProjectionSink sink,
            CheckpointStore checkpoints,
            EventDecoder decoder
    ) {
        this.sink = sink;
        this.checkpoints = checkpoints;
        this.decoder = decoder;
    }

    public void processBatch(
            String partition,
            List<RawEvent> batch
    ) throws Exception {

        for (RawEvent raw : batch) {
            ProjectionEvent event = decoder.decode(raw);

            ProjectionSink.ApplyResult result =
                    switch (event.operation()) {
                        case UPSERT -> sink.upsertIfNewer(
                                event.aggregateId(),
                                event.aggregateVersion(),
                                event.payloadJson()
                        );
                        case DELETE -> sink.deleteIfNewer(
                                event.aggregateId(),
                                event.aggregateVersion()
                        );
                    };

            if (result == ProjectionSink.ApplyResult
                    .PERMANENT_FAILURE) {
                throw new IllegalStateException(
                        "Permanent projection error; quarantine"
                );
            }

            if (result == ProjectionSink.ApplyResult
                    .RETRYABLE_FAILURE) {
                throw new IllegalStateException(
                        "Retryable sink error"
                );
            }

            // The write is confirmed, or the version is stale.
            checkpoints.saveAfterApply(
                    partition,
                    raw.sourcePosition()
            );
        }
    }

    public interface CheckpointStore {
        void saveAfterApply(
                String partition,
                String sourcePosition
        );
    }

    public interface EventDecoder {
        ProjectionEvent decode(RawEvent raw);
    }

    public record RawEvent(
            String sourcePosition,
            byte[] value
    ) {}
}
```

### 47.1. Skeleton không phải một exactly-once consumer

`saveAfterApply` nằm sau sink ACK nhưng không trong cùng transaction. Crash giữa hai bước gây replay trùng; cần idempotency. Để production, còn phải xử lý source partition assignment, ordered commits, cancellation, retry policy, DLQ, schema security và metric lag.

### 47.2. Nếu event permanent failure thì sao?

Không được tự commit qua event lỗi khi chưa có xử lý được phê duyệt. Có thể lưu durable quarantine record cùng nguyên nhân và process riêng; khả năng skip phụ thuộc yêu cầu dữ liệu.

### 47.3. Không tạo CPU spin khi sink lỗi

Retry có backoff/jitter, bounded attempts và circuit breaker để không làm sink quá tải khi vừa phục hồi.

## 48. Java: backfill có checkpoint và giới hạn bộ nhớ

Một worker quét nguồn không nên tải toàn bộ collection vào một `List`. Thiết kế interface:

```java
import java.util.List;

public interface SourcePageReader {

    Page readPage(
            String nextCursor,
            int maxRecords
    );

    record SourceRow(
            String key,
            long sourceVersion,
            String canonicalDocument,
            boolean deleted
    ) {}

    record Page(
            List<SourceRow> rows,
            String nextCursor,
            boolean hasMore
    ) {}
}
```

Một backfill skeleton:

```java
public final class BackfillWorker {

    private final SourcePageReader source;
    private final ProjectionSink sink;
    private final BackfillCheckpointStore checkpoints;

    public BackfillWorker(
            SourcePageReader source,
            ProjectionSink sink,
            BackfillCheckpointStore checkpoints
    ) {
        this.source = source;
        this.sink = sink;
        this.checkpoints = checkpoints;
    }

    public void run(String rangeId) {
        String cursor = checkpoints.loadCursor(rangeId);

        while (true) {
            SourcePageReader.Page page =
                    source.readPage(cursor, 200);

            for (SourcePageReader.SourceRow row : page.rows()) {
                ProjectionSink.ApplyResult outcome =
                        row.deleted()
                        ? sink.deleteIfNewer(
                                row.key(), row.sourceVersion())
                        : sink.upsertIfNewer(
                                row.key(),
                                row.sourceVersion(),
                                row.canonicalDocument());

                if (outcome != ProjectionSink.ApplyResult
                        .APPLIED
                        && outcome != ProjectionSink.ApplyResult
                        .STALE_IGNORED) {
                    throw new IllegalStateException(
                            "Stop backfill; do not checkpoint"
                    );
                }
            }

            checkpoints.saveCursor(
                    rangeId,
                    page.nextCursor()
            );

            if (!page.hasMore()) {
                break;
            }

            cursor = page.nextCursor();
        }
    }

    public interface BackfillCheckpointStore {
        String loadCursor(String rangeId);
        void saveCursor(
                String rangeId,
                String nextCursor
        );
    }
}
```

### 48.1. Đây là mô hình, không phải code production hoàn chỉnh

Nó giả định source reader đã có paging consistent theo contract và sink có atomic version guard. Còn thiếu retry/backoff, batch partial failures, cancellation, empty-page cases, end-of-range marker, metrics và durable worker lease.

### 48.2. Cursor semantics phải rõ

Nếu API dùng opaque continuation token, `nextCursor` không nên bị client tự sửa hoặc tái sử dụng sau thay đổi topology nếu token invalid. Lưu kèm source snapshot ID/range/query fingerprint.

### 48.3. Không checkpoint sau page thất bại

Nếu một row không apply và worker vẫn lưu cursor tới page sau, record có thể bị bỏ. Nếu sink write thành công nhưng saveCursor lỗi, page sẽ được phát lại; version guard xử lý trùng.

### 48.4. Một batch có thể ảnh hưởng SLO nguồn

Có thể giới hạn 200 rows/page trong code, nhưng cần additional byte/request-unit quotas và đo latency. Thông số trong ví dụ chỉ minh họa.

## 49. Java: trình điều phối snapshot + tail

Tách các giai đoạn:

```java
public enum RebuildPhase {
    PREPARE,
    CAPTURE_BOUNDARY,
    BACKFILL,
    REPLAY,
    CATCH_UP,
    VALIDATE,
    CUTOVER,
    MONITOR,
    COMPLETED,
    PAUSED,
    FAILED
}
```

Một event lifecycle:

```text
PREPARE
    -> CAPTURE_BOUNDARY (durable source cursor)
    -> BACKFILL (snapshot/range checkpoints)
    -> REPLAY (events from boundary)
    -> CATCH_UP (all partitions meet barrier/freshness)
    -> VALIDATE (counts, keys, samples, ACL, deletes)
    -> CUTOVER (alias/router)
    -> MONITOR (post-cutover guards)
    -> COMPLETED
```

### 49.1. State persistence

Lưu state ở durable control store với job ID, target index version, snapshot ID, source cursors, worker leases, retry attempts và thời gian cập nhật. Nếu orchestration process restart, nó biết cần tiếp tục từ đâu.

### 49.2. Không tự chuyển trạng thái vì elapsed time

`BACKFILL` không tự thành `REPLAY` sau 10 phút; phải dựa trên source ranges hoàn tất và verification đầu vào.

### 49.3. Các task không thuộc phạm vi

Nếu business side effects như email/charging nằm trong event handling cũ, rebuild projector phải dùng **pure read-model logic**, không gọi lại các side-effect handlers.

### 49.4. Không dùng cùng consumer group live và rebuild một cách mù quáng

Một rebuild consumer cần group/offset/ownership rõ; chia cùng group với live consumer có thể chỉ nhận một phần partitions thay vì toàn bộ lịch sử cần replay. Thiết kế consumer topology chủ động.

## 50. Error handling: không trộn ba loại thất bại

| Loại lỗi | Ví dụ | Phản ứng |
|---|---|---|
| Transient infrastructure | 429/503, network timeout, connector restart | Backoff, retry same event/version |
| Deterministic payload/schema | Field mới không parse, vector dimensions sai | Pause/quarantine, sửa converter/mapping |
| Data correctness gap | Missing event, incomplete snapshot, wrong tenant ACL | Ngừng cutover, reconcile/rebuild source |
| Capacity bottleneck | Backlog tăng, source/sink saturation | Throttle, scale, reschedule |
| Unknown write outcome | Sink commit nhưng ACK mất | Retry idempotently; query sourceVersion |
| Target corruption | Index broken, mixed schema documents | Build new target, không ghi đè authority |
| Security/PII breach | Xóa sai tenant, data bị lộ | Incident response, access controls, remediation |

### 50.1. Không retry vĩnh viễn payload cố định sai

Một event có `embeddingDimension=1536` trong index yêu cầu 768 sẽ không tự sửa khi retry 10.000 lần. Cần schema/model compatibility fix hoặc quarantine.

### 50.2. Retry budget

Đặt số lần, tổng thời gian, backoff và hành động khi hết budget. Không để một worker lỗi khiến hàng trăm worker cùng retry dồn dập làm chết sink.

### 50.3. Không silently drop

Với projection phục vụ quyền truy cập, thanh toán hoặc xóa dữ liệu, skip một event phải là quyết định có audit, không phải default exception handler.

## 51. Nếu log bị mất đoạn hoặc hết retention thì sao?

Một recovery có thể bắt đầu tại checkpoint T0, nhưng stream chỉ còn sự kiện từ T1.

```text
Checkpoint ------ missing log gap ------- earliest available
   T0                                         T1
```

**Không thể phát lại chính xác phần không còn tồn tại bằng cách tăng offset tới T1.**

### 51.1. Phát hiện gap

- Checkpoint không còn hợp lệ.
- Source reports resume token expired.
- Sequence/aggregate version discontinuity.
- CDC connector bị dừng lâu hơn history window.
- Kafka partition log start offset vượt checkpoint.
- Dữ liệu projection lệch khỏi authoritative state.

### 51.2. Hướng xử lý

1. **Dừng cutover** nếu không đủ coverage.
2. Ghi ranges/keys/time window nghi thiếu.
3. Nếu có consistent snapshot đủ mới, rebuild từ snapshot và tail từ boundary hợp lệ.
4. Nếu chỉ mất một số keys, fetch authoritative current state và reproject, rồi reconcile toàn scope.
5. Nếu source cũng mất, kích hoạt authoritative backup/restore plan; projection không bịa lịch sử.
6. Nâng retention/giám sát trước run tiếp theo.

### 51.3. Log retention và rebuild duration

Một job phải chạy 12 giờ trong khi stream chỉ giữ 2 giờ sẽ có rủi ro gap nếu không có buffering/durable staging strategy phù hợp. Thiết kế **retention > worst-case backfill + interruption + retry + safety margin** hoặc dùng snapshot handoff được vendor hỗ trợ.

### 51.4. Không cứu history aggregates bằng current state nếu cần chi tiết lịch sử

Current Order state `REFUNDED` không tự cho biết mọi lần thanh toán/hoàn tiền trước đó. Nếu ledger/event history đã mất, xây aggregate lịch sử từ current snapshot có thể không đúng.

## 52. Tính đúng đắn của reconciliation

Một derived store có thể được kiểm chứng theo nhiều mức:

| Mức | Phép kiểm |
|---|---|
| Basic counts | Số documents/items theo tenant/time |
| Key-set parity | Key nào thiếu/thừa giữa source và sink |
| Version parity | Sink sourceVersion có bắt kịp sourceVersion |
| Content parity | Các fields quan trọng trùng theo transform spec |
| Delete parity | Deleted/expired/revoked keys không xuất hiện |
| Referential integrity | Graph edges/nodes, foreign references |
| Aggregate consistency | Sum/count/group totals chính xác |
| Security scope | ACL/tenant filter đúng |
| Search behavior | Query results/filter/sort/relevance |
| Freshness | Source commit → visible tại sink trong SLO |
| Audit completeness | Không bỏ event IDs/retention-critical facts |

### 52.1. Count parity không đủ

Hai sets đều có 10 triệu documents nhưng một key thiếu và một key khác thừa vẫn có counts bằng nhau. Dùng stable IDs/version checks hoặc hash/chunk reconciliation.

### 52.2. Chunked checksums

Có thể chia theo source ranges/tenant và tính hash của canonical key+value+version. Nhưng cần cùng snapshot/read boundary; nếu hai hệ đang nhận writes, direct hash mismatch có thể do data lag hợp lệ.

### 52.3. Source-to-sink equality không phải bytes equality

Elasticsearch tokenization, Redis TTL metadata, vector ANN cấu trúc và MongoDB BSON serialization khác nhau. So **canonical business representation**, không chỉ JSON string bytes.

### 52.4. Source version drift

Khi sink đã apply tới barrier B, kiểm tra samples/keys tương ứng với source snapshot/barrier B. Không lấy source latest T1 và sink tại T0 rồi gọi chênh lệch bất kỳ là corruption.

## 53. Reconciliation chủ động trong vận hành thường ngày

Đừng chờ tới khi cần disaster recovery mới phát hiện không thể xây lại projection.

Một lịch đối soát có thể:

```text
Daily:
  sample source/sink key+version parity

Weekly:
  compare counts/checksums by tenant/range

After index mapping changes:
  run full query/ACL verification

After incident:
  reproject affected keys and verify deletes

Periodically:
  rehearse full rebuild in isolated environment
```

### 53.1. Self-healing có giới hạn

Một reconciliation worker có thể tự fetch source current state và sửa mismatch. Nó cần quota, audit và giới hạn scope để tránh trở thành tác nhân gây tải/mất dữ liệu.

### 53.2. Không sửa authoritative source theo sink

Nếu sourceVersion ở sink lớn hơn do lỗi, không tự copy document sink về source. Đánh dấu mismatch, điều tra lineage, chỉ sửa projection theo nguồn có thẩm quyền.

### 53.3. Chỉ số coverage

Ghi số ranges/tenants/keys đã kiểm tra và thời điểm. `sampled=1%` không đủ chứng minh không còn bất kỳ missing key nào, nhưng hữu ích để theo dõi drift.

## 54. Observability: những metrics cần có

| Metric | Câu hỏi trả lời |
|---|---|
| `rebuild_active_jobs` | Có job nào đang chạy? |
| `rebuild_phase` | Job đang scan, replay hay verify? |
| `backfill_records_total` | Đã đọc/ghi bao nhiêu records? |
| `backfill_bytes_total` | Tốc độ hữu ích theo bytes? |
| `backfill_ranges_completed` | Phạm vi nào đã hoàn tất? |
| `source_latest_position` | Nguồn đang ở đâu? |
| `sink_applied_position` | Projector đã ghi tới đâu? |
| `projection_lag_seconds` | Dữ liệu sinh trễ bao lâu? |
| `pending_records`/`oldest_pending_age` | Backlog đang tăng? |
| `sink_bulk_failures_total` | Ghi lỗi bao nhiêu? |
| `dlq_records_total` | Có events lỗi không được apply? |
| `rebuild_retry_total` | Có retry storm? |
| `reconciliation_mismatch_total` | Source/sink có lệch? |
| `delete_mismatch_total` | Có record đáng xóa vẫn hiện? |
| `alias_cutover_status` | Đã route traffic đúng index? |
| `search_request_p99` | API của người dùng có khỏe? |
| `source_cpu_disk_network` | Rebuild có làm quá tải nguồn? |

**Tên metrics trên là mẫu naming cho hệ observability**, không phải API chuẩn của mọi NoSQL.

### 54.1. Cardinality

Không đưa mỗi `documentId`/UUID/offset vào Prometheus labels; dùng `job`, `phase`, `cluster`, `collection`, `result` hữu hạn. Document IDs để trong logs/reconciliation table được kiểm soát truy cập.

### 54.2. Multi-partition lag

Không lấy raw difference của offsets khác partitions rồi gọi lag seconds. Dùng source-specific lag metrics hoặc timestamp watermark với provenance và clock skew awareness.

### 54.3. Metric missing

Exporter down không đồng nghĩa backlog=0. Giám sát sample freshness và target availability; gate cutover phải PAUSE nếu không có bằng chứng.

## 55. Dashboard phục hồi nên như thế nào?

```text
+-------------------------------------------------------------+
| Rebuild job: orders-search-v8    Phase: CATCH_UP             |
| Status: RUNNING   Source healthy: yes   Sink healthy: yes     |
+-------------------------------------------------------------+
| Snapshot ranges  120/120     Backfill records 23.8M / ~24M   |
| Replay progress  per-partition vector watermark             |
+-------------------------------------------------------------+
| Useful throughput | Backlog age | Retried events | DLQ       |
| 16k docs/s        | 42 seconds | 0.3%           | 0         |
+-------------------------------------------------------------+
| Source CPU/Disk | Sink disk/CPU | API p99 | Delete mismatches |
+-------------------------------------------------------------+
| Validation: keys 99.99% checked, ACL PASS, deletes PASS       |
| Cutover gate: HOLD (freshness must be < 30s)                 |
+-------------------------------------------------------------+
```

### 55.1. Percentage khi nào có nghĩa?

Chỉ khi total records/bytes/ranges được định nghĩa, không tự so completed docs với `source count` đang tăng và hứa ETA chính xác.

### 55.2. Percentiles và error rates

Một bulk worker 20k docs/s nhưng search API p99 tăng 10 lần có thể cần giảm tốc. Phải ghép recovery metrics với foreground SLO.

### 55.3. Recovery không chỉ có trạng thái RUNNING

Có thể `PAUSED`, `BLOCKED`, `RETRYING`, `FAILED`, `VALIDATING`, `SERVING`. Khi job báo SUCCESS mà index alias chưa cutover, user vẫn có thể gặp lỗi.

## 56. RPO/RTO và kế hoạch phục hồi theo tier

Không phải derived stores nào cũng cần cùng thời gian phục hồi.

| Tier | Ví dụ | Recovery policy |
|---|---|---|
| Critical read path | Search tìm đơn đang xử lý | Snapshot/alias, RTO ngắn, correctness chặt |
| High-value read model | Customer order history | Rebuild có catch-up, fallback paginated source |
| Best-effort cache | Redis product cache | Cold start + warm hot keys |
| Analytics daily report | OLAP aggregates | Delay vài giờ nếu business chấp nhận |
| Vector recommendation | ANN index | Rebuild batch, fallback keyword search |
| Audit/compliance | Regulatory logs/read models | Không bỏ records, retention và reconcile nghiêm ngặt |

### 56.1. Fallback phải đúng hợp đồng

Nếu search index mất, UI có thể fallback truy vấn MongoDB point lookup theo `orderId`, nhưng không tự đưa full-text query thành unindexed scan trên source production.

### 56.2. Graceful degradation

Thông báo tính năng tạm hạn chế, dùng cached last-known results nếu freshness/security cho phép, queue requests với deadline hoặc trả lỗi rõ. Không hiển thị dữ liệu đã bị revoke.

### 56.3. Recovery budget

Đối với RTO 20 phút nhưng full rebuild cần 10 giờ, thiết kế phải có ready snapshots/dual index/standby hoặc cải thiện parallelism trước khi sự cố. Runbook không bẻ cong giới hạn vật lý.

## 57. Runbook A: khôi phục toàn bộ index tìm kiếm

Giả sử source Orders vẫn hoạt động, target index hỏng hoàn toàn.

### Bước 1 — Công bố incident và chặn sử dụng index sai

Giữ authoritative writes, tắt hoặc hạn chế query path lỗi, dùng fallback được phê duyệt. Không tiếp tục phục vụ results không đúng.

### Bước 2 — Xác minh nguồn dữ liệu

Kiểm tra source DB quorum/health, snapshot/export availability, change-feed retention, schema và DELETE coverage. Xác nhận projection không chứa unique-only dữ liệu.

### Bước 3 — Chọn phương án

Nếu verified Elasticsearch snapshot phù hợp và CDC tail còn đủ, restore + replay. Nếu snapshot không có hoặc index/schema phải đổi, tạo index mới và rebuild từ source + tail.

### Bước 4 — Tạo target phiên bản mới

Dựng `orders-search-v8` với index settings/mappings/analyzers và capacity. Không ghi đè `orders-search-v7` đang được giữ làm bằng chứng nếu chưa cần.

### Bước 5 — Thiết lập nguồn thay đổi

Có cursor/watermark hợp lệ trước hoặc tương ứng với snapshot. Lưu retention deadline và alert khi lag gần vượt window.

### Bước 6 — Backfill có checkpoint

Phân ranges/tenants, bounded pagination, bulk write idempotently, persisted progress. Không để nguồn/sink SLO vượt ngưỡng.

### Bước 7 — Tail/Catch up

Phát lại changes từ boundary đúng, kiểm tra deletes và out-of-order. Catch up đến cutover watermark hoặc freshness threshold.

### Bước 8 — Verify

Key/version parity, counts, sampled content, ACL, deletes, query results, search relevance và latency. Mọi gaps/unapplied DLQ phải được giải quyết theo policy.

### Bước 9 — Cutover

Đổi search alias/routing tới target qua cơ chế được hỗ trợ và kiểm tra thực tế sau chuyển.

### Bước 10 — Theo dõi và đóng incident

Đo user SLO, source-to-visible lag, indexing failures, disk pressure. Giữ old index/snapshot theo rollback và privacy policy; cập nhật runbook/retention.

## 58. Runbook B: replay một khoảng sự kiện bị bỏ lỡ

**Tình huống:** Một consumer mất kết nối 25 phút; source còn lưu events từ trước lúc downtime.

1. Xác định checkpoint cuối được commit **sau khi apply thành công**.
2. Xác định earliest available source log position và chứng minh không có gap.
3. Dừng consumer lỗi hoặc giới hạn ownership để tránh hai workers cùng ghi sai.
4. Tạo replay job với durable job ID và đúng start position.
5. Sử dụng projector code/schema versions phù hợp.
6. Áp events theo key order hoặc version guard.
7. Retry transient errors có giới hạn; quarantine deterministic failures.
8. Theo dõi lag, throughput, source/sink CPU và retention window.
9. Reconcile key ranges/tenants ảnh hưởng.
10. Chuyển lại live consumer sau khi đã đạt watermark; tránh mất ownership/offset và double-writing không kiểm soát.
11. Xác minh deletes, permissions và business invariants.
12. Ghi incident root cause và cải thiện alert/retention budget.

### 58.1. Không reset offset thành earliest một cách mù quáng

Replay toàn bộ log vào projection hiện hữu có thể rất tốn thời gian và gây duplication nếu sink không idempotent. Chọn đúng checkpoint, hoặc dựng target mới nếu semantics khó kiểm soát.

### 58.2. Khi replay từ now là không thể chấp nhận

Với missing deletes/payment corrections, bỏ khoảng thời gian cũ có thể khiến dữ liệu sai vô thời hạn. Nếu log gap, chuyển phương án rebuild/reconcile.

## 59. Runbook C: phát hiện dữ liệu đã xóa xuất hiện lại

**Tình huống:** Sau rebuild, một sản phẩm đã bị xóa tại source xuất hiện trong search.

### 59.1. Ưu tiên containment

Nếu đó là PII/ACL violation, chặn truy cập ngay, invalidate affected cache/index entries và kích hoạt incident response theo severity.

### 59.2. Truy nguyên lineage

Tìm source key, source deletion version, snapshot sourceVersion, CDC delete event, projector apply logs và index last update metadata.

### 59.3. Nguyên nhân thường gặp

- Old snapshot page viết sau DELETE.
- Replay event không có version guard.
- Physical delete xóa cả tombstone version, sau đó upsert cũ tái tạo record.
- CDC connector bỏ event delete.
- Schema/tenant filter mapping sai.
- Restore backup cũ nhưng không tail deletes.
- TTL được reset trong backfill.

### 59.4. Sửa và chứng minh

Sửa consumer/version fencing, replay missing deletes hoặc rebuild affected scope, chạy reconciliation delete parity, test race tái hiện trong staging, giám sát post-fix.

### 59.5. Không chỉ xóa thủ công một key

Việc xóa một document xử lý triệu chứng, chưa bảo đảm không còn các keys khác và không có worker cũ tiếp tục tái tạo chúng.

## 60. Runbook D: vector index cần thay embedding model

**Tình huống:** Semantic search dùng embeddings model M1 768 dimensions; hệ muốn chuyển M2 1536 dimensions.

### 60.1. Vì sao đây là rebuild?

Vectors thuộc hai spaces khác nhau, không thể chỉ đổi metadata field. Cần tính embeddings lại từ source nội dung bằng đúng M2/preprocessing.

### 60.2. Phương án

1. Giữ vector index M1 cho user traffic.
2. Tạo M2 index mới, dimension/distance settings chính xác.
3. Backfill content theo stable document/chunk IDs.
4. Ghi model ID và contentVersion trên từng chunk.
5. Tail content edits/deletes khi model M2 đang build.
6. Reconcile chunk counts và deleted chunks.
7. Kiểm thử relevance/recall@K, ACL và latency.
8. Canaried queries/shadow reads nếu chi phí cho phép.
9. Cutover routing/alias theo policy.
10. Giữ M1 rollback window hợp lệ, không bỏ delete propagation.

### 60.3. Chi phí và reproducibility

Phải lưu model artifacts/config/version và chunking rules. Nếu dùng external embedding API, có rate limits, model deprecation và data residency cần tính trước.

## 61. Quyền truy cập và an toàn dữ liệu khi rebuild

Một recovery thường cần đọc nhiều dữ liệu hơn API bình thường. Đây là thời điểm dễ lộ PII hoặc vượt quyền.

### 61.1. Least privilege

Worker chỉ cần quyền đọc source scope và ghi derived target scope; quyền xóa toàn collection/index hoặc mở data cross-tenant nên tách khỏi quyền thông thường.

### 61.2. Audit

Ghi job owner, reason, scope, data categories, approvals, start/end, versioned artifacts, access to secrets và cutover decision.

### 61.3. Data minimization

Search index chỉ cần những fields phục vụ tìm kiếm; không copy password hash, access tokens, full payment details hay dữ liệu nhạy cảm không cần thiết.

### 61.4. Backups và right-to-delete

Một snapshot chứa PII đã được xóa sau đó phải được tail delete/reconcile trước khi public. Retention/erasure obligations áp lên old indices/backups/logs theo chính sách/luật phù hợp.

### 61.5. Production logs

Không log raw event body hoặc document toàn phần khi debug. Ghi event IDs, sourceVersion, error class, hashed/stable key references và request correlation.

## 62. Kiểm thử lỗi trước khi sự cố thật

Một kế hoạch fault injection trong staging với dữ liệu giả:

| Test | Sự cố mô phỏng | Kỳ vọng |
|---|---|---|
| T1 | Consumer crash sau sink ACK trước checkpoint | Event replay không tạo duplicate |
| T2 | Checkpoint store timeout | Retry không bỏ event |
| T3 | CDC retention gap | Job phát hiện và dừng cutover |
| T4 | Snapshot worker chậm hơn tail | Old rows không overwrite new events |
| T5 | DELETE tới trong lúc backfill | Deleted key không sống lại |
| T6 | TTL expire giữa rebuild | `expiresAt` vẫn đúng |
| T7 | Kafka partition rebalance | Ownership và offset không mất |
| T8 | 429/503 sink errors | Backoff/jitter, bounded queue |
| T9 | Bulk write một phần thất bại | Failed items không bị checkpoint qua |
| T10 | Mapping schema mismatch | Quarantine/pause, không skip âm thầm |
| T11 | Source schema version cũ | Upcaster/decoder xử lý |
| T12 | Out-of-order event version | SourceVersion guard giữ bản mới |
| T13 | Duplicated increment event | Aggregate không cộng hai lần |
| T14 | Missing join dependency | Pending/fetch/reconcile theo policy |
| T15 | Multi-tenant wrong key | ACL isolation không bị phá |
| T16 | Search index refresh delay | Cutover gate kiểm tra visible |
| T17 | In-flight source updates tại cutover | Watermark/lag không có gap |
| T18 | Monitoring exporter down | Gate `UNKNOWN`, không xanh giả |
| T19 | Target index storage full | Pause, recovery state retained |
| T20 | Worker scale up/down | Range checkpoint, worker lease fencing |
| T21 | Model artifact unavailable | Vector rebuild block, không dùng random substitute |
| T22 | Old index rollback | Cũ vẫn đạt delete/freshness guardrail |
| T23 | Cache stampede | Source queries bounded, p99 kiểm soát |
| T24 | Source slow during backfill | Throttle, foreground SLO giữ |
| T25 | Reconciliation mismatch | No cutover; bounded repair path |

### 62.1. Không thử destructive replay trên production tùy tiện

Replay side-effecting business events có thể gửi lại emails/payments hoặc thay đổi authority. Chỉ chạy recovery projector cô lập, không gọi business command handlers không idempotent.

### 62.2. Thử restore rồi mới tin backup

Một snapshot đã tạo thành công không bảo đảm restore được vào target version, chứa đủ index settings, encryption keys hoặc source log boundary. Restore drill là bằng chứng thiết yếu.

## 63. Những hiểu nhầm dễ làm sai khôi phục

**“Derived store có thể xóa mọi lúc.”** Không nếu còn fields do người dùng ghi riêng hoặc không có source đầy đủ.

**“Có Kafka là phát lại từ ngày đầu.”** Không; retention/cleanup có thể loại events.

**“CDC là event sourcing.”** Không; storage mutations khác domain events.

**“Đọc earliest sẽ lấy mọi bản ghi lịch sử.”** Không; chỉ records còn được lưu.

**“Consumer lag bằng zero nghĩa index đúng.”** Không; có thể đã skip DLQ hoặc sai mappings.

**“Snapshot quét nhiều trang luôn là nhất quán.”** Không; dữ liệu có thể thay đổi giữa pages.

**“Bắt đầu CDC sau khi scan xong vẫn không mất gì.”** Sai nếu có writes trong khoảng giữa.

**“Replay tail trước rồi snapshot sau luôn an toàn.”** Có thể resurrect deletes/overwrite new state.

**“Event ID là document ID.”** Không; một entity thường có nhiều events.

**“Timestamp mới hơn nghĩa version mới hơn.”** Không khi clock skew hoặc backdated events.

**“Có sourceVersion guard nên mọi delta luôn an toàn.”** Không nếu thiếu intermediate deltas.

**“At-least-once nghĩa không lặp.”** Ngược lại, duplicate deliveries là điều phải thiết kế.

**“Commit offset trước sink write giúp chạy nhanh và an toàn.”** Có thể mất event.

**“`@Transactional` trong Java tự atomic Kafka + Elasticsearch.”** Không có transaction chung mặc định.

**“Bulk HTTP 200 nghĩa 100% items đã ghi.”** Phải đọc kết quả từng item.

**“Delete chỉ cần xóa document ngay.”** Nếu không giữ fencing/version, old replay có thể tạo lại.

**“Rebuild TTL bằng thời điểm rebuild vẫn giống nguồn.”** Không; có thể kéo dài retention.

**“Restore backup search cũ là xong.”** Cần replay deletes/updates sau snapshot.

**“Một count bằng nhau chứng minh hai datasets giống nhau.”** Không; key/version parity quan trọng.

**“Index alias switch làm dữ liệu bên trong tự nhất quán.”** Không; chỉ là routing.

**“A/B shadow results chính xác từng thứ tự khi dùng ANN.”** Không nhất thiết; cần relevance/recall.

**“Chỉ tăng concurrency là catch-up được.”** Không nếu sink throughput không hơn source arrival rate.

**“Redis cache luôn không chứa dữ liệu quý.”** Không nếu được dùng làm authority cho sessions/queues/counters.

**“DynamoDB Streams đủ cho replay nhiều tháng.”** Không; retention ngắn.

**“Cassandra repair cũng rebuild external search index.”** Không; repair các replicas nội bộ.

**“Vector index chỉ cần copy vectors sang model mới.”** Không; embeddings không tự tương thích giữa models.

**“Skip poison event cho lag về 0 là hoàn thành.”** Có thể làm mất correctness.

**“Rebuild thành công nghĩa có thể bỏ monitoring.”** Recovery regression có thể lộ tại peak/cold cache.

**“Rollback old index lúc nào cũng an toàn.”** Không khi old index stale hoặc thiếu DELETE.

## 64. Bài tập thực hành

### Bài tập 1 — Kho nào là dẫn xuất?

Redis chỉ cache `ProductById` từ MongoDB.

**Câu hỏi:** Có thể rebuild cache từ MongoDB không?

**Gợi ý:** Có, nếu mọi field cần thiết nằm ở source và policy TTL/ACL được bảo toàn.

### Bài tập 2 — Dữ liệu không thể phục hồi

Search index chứa `manualQualityScore` mà không hệ nào khác lưu.

**Câu hỏi:** Có thể xóa toàn bộ index rồi rebuild chắc chắn đúng không?

**Gợi ý:** Không; trước hết tìm authority của score hoặc backup.

### Bài tập 3 — Event log retention

Kafka giữ changes 3 ngày, search index mất toàn bộ data 6 tháng.

**Câu hỏi:** Replay Kafka đủ chưa?

**Gợi ý:** Không nếu thiếu snapshot/authoritative source.

### Bài tập 4 — Replay vs rebuild

Source MongoDB còn đủ documents, CDC token đã hết hạn.

**Câu hỏi:** Chiến lược nào khả thi hơn?

**Gợi ý:** Snapshot/backfill nguồn + stream boundary mới + reconciliation.

### Bài tập 5 — RTO lý tưởng

24 triệu docs, sink 12.000 docs/s.

**Câu hỏi:** Backfill lý tưởng khoảng bao lâu?

**Gợi ý:** 2.000 giây, 33,3 phút, chưa tính tail/verify.

### Bài tập 6 — Backlog growth

Source 10.000 events/s, sink 8.000 events/s.

**Câu hỏi:** Backlog có tự hết không?

**Gợi ý:** Không; tăng khoảng 2.000 events/s khi rate giữ nguyên.

### Bài tập 7 — Catch-up tốc độ ròng

Source 4.000/s, sink 12.000/s, backlog 800.000 events.

**Câu hỏi:** Thời gian lý tưởng để drain?

**Gợi ý:** 800.000 / (12.000−4.000) = 100 giây.

### Bài tập 8 — Snapshot race

Một key bị delete sau khi snapshot đọc nhưng trước khi index apply.

**Câu hỏi:** Rủi ro?

**Gợi ý:** Dữ liệu bị sống lại; cần tail delete/version fencing.

### Bài tập 9 — Checkpoint ordering

Consumer checkpoint event trước khi sink write.

**Câu hỏi:** Crash sẽ dẫn đến điều gì?

**Gợi ý:** Có thể mất event trong projection.

### Bài tập 10 — Duplicate event

Consumer write thành công rồi crash trước checkpoint.

**Câu hỏi:** Giải pháp?

**Gợi ý:** At-least-once replay cùng version/idempotent sink.

### Bài tập 11 — Increment

Event `stock += 3` được replay hai lần.

**Câu hỏi:** Vì sao không an toàn?

**Gợi ý:** Tạo +6 thay vì +3 nếu không dedupe.

### Bài tập 12 — Version ordering

Sink có `O100 v12`, nhận `O100 v10`.

**Câu hỏi:** Cần xử lý?

**Gợi ý:** Skip stale full-state event với guard phù hợp.

### Bài tập 13 — Missing delta

Sink có v8, nhận delta v10 nhưng v9 không có.

**Câu hỏi:** Có được áp ngay không?

**Gợi ý:** Không mặc nhiên; xử lý gap/fetch state.

### Bài tập 14 — Multi-partition offsets

Kafka partition 0 offset 500, partition 1 offset 1000.

**Câu hỏi:** Có một global offset 1000 không?

**Gợi ý:** Không; checkpoint vector theo partitions.

### Bài tập 15 — Snapshot consistency

Dùng offset pagination trên source đang liên tục insert/delete.

**Câu hỏi:** Có thể thiếu records không?

**Gợi ý:** Có; cần supported snapshot/keyset/boundary protocol.

### Bài tập 16 — Cutover

Search bulk ACK xong nhưng chưa refresh để query visible.

**Câu hỏi:** Có nên route user ngay không?

**Gợi ý:** Chưa nếu contract yêu cầu query đã nhìn thấy.

### Bài tập 17 — GSI/native index

DynamoDB native GSI đang build.

**Câu hỏi:** Có giống external Elasticsearch index dựng từ Streams không?

**Gợi ý:** Không; native GSI là dịch vụ quản lý theo semantics riêng.

### Bài tập 18 — CDC retention

DynamoDB Streams không giữ history cho một lần rebuild kéo dài nhiều ngày.

**Câu hỏi:** Cần bổ sung gì?

**Gợi ý:** Export/snapshot và log durable dài hơn hoặc handoff phù hợp.

### Bài tập 19 — Cassandra

Node replicas không nhất quán, `nodetool repair` được chạy.

**Câu hỏi:** Nó có dựng lại Redis cache không?

**Gợi ý:** Không; repair phạm vi replication nội bộ Cassandra.

### Bài tập 20 — TTL

Record gốc expire sau 1 giờ, rebuild tại phút 50.

**Câu hỏi:** Đặt TTL mới 1 giờ có đúng không?

**Gợi ý:** Không nếu cần giữ absolute expiration.

### Bài tập 21 — Multi-source

Order v5 và Payment v10 từ hai sources độc lập.

**Câu hỏi:** Có thể gắn một timestamp chung để khẳng định snapshot nhất quán không?

**Gợi ý:** Không khi thiếu temporal/transactional boundary.

### Bài tập 22 — Graph

Edges được rebuild trước nodes và có edges tới users đã bị delete.

**Câu hỏi:** Cần gì?

**Gợi ý:** Xây nodes, kiểm tra endpoints, delete propagation, reconcile orphan edges.

### Bài tập 23 — Vector model

Index M1 768 dimensions, M2 1536 dimensions.

**Câu hỏi:** Chỉ đổi index settings rồi tái sử dụng vectors cũ được không?

**Gợi ý:** Không; thường phải recompute embeddings bằng M2.

### Bài tập 24 — Redis stampede

Cache mất hết keys, 20.000 requests/s quay về source.

**Câu hỏi:** Biện pháp?

**Gợi ý:** Prefetch hot keys, coalescing, concurrency limits, fallback.

### Bài tập 25 — Bulk partial failure

500 items gửi thành một batch, 20 items bị 429.

**Câu hỏi:** Có được checkpoint qua tất cả 500 không?

**Gợi ý:** Không nếu failed items chưa được xử lý/durably tracked.

### Bài tập 26 — Poison event

Một record có type mới không parse được và consumer retry vô hạn.

**Câu hỏi:** Cần thiết kế gì?

**Gợi ý:** Schema compatibility, quarantine/DLQ, alert, replay correction.

### Bài tập 27 — Key parity

Source và sink đều có 10.000 keys nhưng không trùng toàn bộ.

**Câu hỏi:** Count parity đã chứng minh đúng chưa?

**Gợi ý:** Chưa; compare key sets/source versions/checksums.

### Bài tập 28 — Rollback alias

Old index có dữ liệu khách đã bị revoke, new index đã xử lý DELETE.

**Câu hỏi:** Có thể quay alias về old index để xử lý latency không?

**Gợi ý:** Không nếu làm lộ revoked data; cần giữ delete parity.

### Bài tập 29 — Backup privacy

Snapshot tìm kiếm từ tháng trước còn PII đã bị xóa tuần này.

**Câu hỏi:** Bước quan trọng trước public restore?

**Gợi ý:** Replay deletes/reconcile privacy retention/ACL.

### Bài tập 30 — Thiết kế toàn bộ

Một Java/Spring Boot platform lưu Orders ở MongoDB, có Kafka Change Streams pipeline, Elasticsearch search, Redis cache và vector search từ mô tả sản phẩm.

**Yêu cầu:** Lập kế hoạch phục hồi khi cả search và Redis gặp sự cố: chọn source authority, backup/replay/rebuild, xác định retention, capture boundary, snapshot scan, checkpoint, version/tombstone handling, Java worker, index alias cutover, source RPO/RTO, validation và chaos tests.

**Gợi ý:** Không sửa MongoDB authority; tạo new search index, snapshot+tail, replay/version guard, verify deletes/ACL, alias cutover; Redis prewarm hot keys và source-load budget; vector index cần model/chunk version. Sau phục hồi test unknown write outcome, CDC gaps và source-to-visible freshness.

## 65. Checklist triển khai và vận hành

- [ ] Đã xác định authoritative source cho mọi field trong derived store.
- [ ] Đã phân loại kho nào thật sự có thể rebuild và kho nào giữ unique state.
- [ ] Đã nêu RPO/RTO/freshness/correctness SLO theo chức năng.
- [ ] Đã xác định backup, snapshot, CDC log và retention khả dụng.
- [ ] Đã phân biệt event sourcing log, CDC feed và compacted topic.
- [ ] Event payload có đủ information để replay hoặc có baseline đầy đủ.
- [ ] Có event ID/aggregate version/source position hợp lệ.
- [ ] Không lấy timestamp khách hàng làm ordering authority.
- [ ] Có schemaVersion/upcaster và transformation code reproducible.
- [ ] Có snapshot + change stream handoff không gap.
- [ ] Không dùng offset scan thiếu tính nhất quán cho nguồn đang thay đổi.
- [ ] Có bounded pagination/streaming và worker range checkpoints.
- [ ] Có per-partition vector watermark; không giả một global numeric offset.
- [ ] Chỉ commit checkpoint sau sink apply thành công theo semantics.
- [ ] Idempotent retries và atomic version guard/per-key serialization đúng.
- [ ] Các delete/tombstone/TTL không bị sống lại hoặc kéo dài sai.
- [ ] Có chính sách source retention và abort khi stream gap.
- [ ] Có strategy cho full-state vs delta mutation và missing intermediate events.
- [ ] Multi-source joins có version/freshness consistency policy.
- [ ] Có mapping/index/analyzer/embedding model/ACL artifacts.
- [ ] Source scan và sink bulk write có capacity/CPU/I/O/cost budget.
- [ ] Có batch partial-failure inspection, retry budgets, DLQ policy.
- [ ] Không replay business side effects như emails/payments vô điều kiện.
- [ ] Có new versioned target và route/alias cutover an toàn khi phù hợp.
- [ ] Cutover chỉ khi target query visible, correctness/freshness gate pass.
- [ ] Có query shadowing/canary và rollback data-freshness policy.
- [ ] Có key/content/version/count/delete/ACL reconciliation.
- [ ] Có metrics source-to-visible lag, backlog, rate, errors, retries.
- [ ] Monitoring missing/unknown không bị coi là progress complete.
- [ ] Có recovery state persistence, worker leases, attempts và ownership.
- [ ] Có plan cho checkpoint invalid, log gap và snapshot failure.
- [ ] Có test race snapshot/delete/out-of-order events.
- [ ] Có test consumer crash trước/sau checkpoint, 429 và schema poison.
- [ ] Có privacy/PII redaction và least-privilege recovery access.
- [ ] Có backup restore drill và khả năng khôi phục trong RTO dự kiến.
- [ ] Có dashboard, incident owner, audit log và post-recovery verification.
- [ ] Đã diễn tập phục hồi trên dữ liệu giả trong môi trường phù hợp.

## 66. Tổng kết

Kho dẫn xuất như **Elasticsearch index, Redis cache, CQRS read model, analytics aggregate, graph projection hay vector index** có thể được khôi phục mà không cần làm mất nguồn sự thật, nhưng chỉ khi nó thực sự **có thể tái tạo từ nguồn đầy đủ và các quy tắc biến đổi được lưu giữ**.

Có ba đường khôi phục chính:

1. **Replay:** phát lại event/CDC log khi log giữ đủ lịch sử hoặc đoạn còn thiếu, event schema đọc được, ordering và idempotency được thiết kế.
2. **Rebuild:** đọc authoritative state từ snapshot/export/scan nhất quán, tính lại projection, tạo target mới.
3. **Snapshot + tail:** kết hợp backfill với stream changes có handoff boundary hợp lệ để không bỏ sót writes/deletes trong khi nguồn tiếp tục hoạt động.

Những điểm quyết định tính an toàn không phải chỉ là tốc độ copy:

- **Coverage:** snapshot và log có thể nối nhau không có gap.
- **Ordering:** per-key version, event identity và checkpoint được xử lý đúng.
- **Correctness:** delta, deletes, tombstones, TTL, schema evolution và ACL không bị sai.
- **Operational safety:** bounded work, retries, capacity, quorums, retained logs và source SLO.
- **Cutover:** target mới được kiểm chứng bằng key/version parity, source-to-visible freshness và những bất biến nghiệp vụ trước khi nhận traffic.

**Nguyên tắc cốt lõi:** *Khôi phục kho dẫn xuất không phải là “copy lại dữ liệu rồi bật API”. Đó là quá trình tái dựng một trạng thái đọc có nguồn gốc rõ ràng, bao phủ toàn bộ thay đổi quan trọng, có thể phát lại sau lỗi, không làm dữ liệu đã xóa sống lại và chỉ được công bố sau khi đã chứng minh đúng so với nguồn có thẩm quyền.*



