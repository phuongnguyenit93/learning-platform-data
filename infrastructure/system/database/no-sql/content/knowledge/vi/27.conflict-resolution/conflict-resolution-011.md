# Đối soát định kỳ khi ứng dụng duy trì dữ liệu lặp

Trong một hệ **Database No SQL**, ứng dụng thường sao chép có chủ đích một phần dữ liệu sang nhiều mô hình đọc: document nguồn trong MongoDB, Search index, Redis cache, bảng truy vấn theo tenant, báo cáo tổng hợp hoặc read model của một service khác. Đây là **denormalization**. Nó giúp tăng tốc các access pattern quan trọng nhưng đặt ra một vấn đề: khi nguồn thay đổi, bản sao có thể không theo kịp hoặc bị cập nhật sai.

Một event có thể bị mất, consumer crash, queue phát lại sự kiện cũ, indexer đang ngừng hoạt động, snapshot migration chưa backfill đủ hoặc một bản ghi đã xóa ở nguồn vẫn tồn tại trong Search. Vì vậy nhiều hệ thống cần **đối soát định kỳ (periodic reconciliation)**: quét, so sánh và sửa dữ liệu suy diễn theo một nguồn có thẩm quyền, đồng thời lưu bằng chứng về sai khác chưa được khắc phục.

Bài học này thuộc chương **Xung đột và đồng bộ** của **Database No SQL**. Trọng tâm là cách thiết kế một vòng đối soát có thể chạy lặp lại mà **không ghi đè dữ liệu mới hơn**, không biến lỗi đọc tạm thời thành lệnh xóa hàng loạt và không nhầm snapshot lịch sử hợp lệ với bản sao hiện hành bị stale.

> **Đối soát đúng không chỉ làm hai tài liệu trông giống nhau; nó phải biết ai sở hữu dữ liệu, trạng thái nào được coi là đúng, sửa theo phiên bản nào và làm sao chứng minh quá trình sửa đã hội tụ.**

## 1. Vì sao ứng dụng cần dữ liệu lặp?

Một hệ bán hàng có thể dùng:

~~~text
Catalog:
  Product(id, title, categoryId, status, version)

Pricing:
  CurrentPrice(productId, amountMinor, currency, version)

Inventory:
  Stock(sku, available, version)

Search:
  ProductCard(id, title, price, available, sourceVersions)

Redis:
  product-card:{id} -> cached ProductCard

Order:
  OrderLine(productId, titleAtPurchase, unitPriceAtPurchase)

Reporting:
  DailyCategoryRevenue(day, categoryId, amount, dataAsOf)
~~~

Các bản sao phục vụ các mục đích khác nhau: Search để lọc sản phẩm, Redis để trả trang nhanh, OrderLine để chứng minh mức giá đã bán, Reporting để tổng hợp. Cùng một field tên **price** nhưng không nhất thiết có cùng vòng đời.

Do vậy, trước khi lập job đối soát phải phân loại **bản sao hiện hành, projection có biến đổi, cache, historical snapshot và aggregate**.

## 2. Bốn kiểu dữ liệu lặp cần phân biệt

| Loại | Ý nghĩa | Quy tắc đối soát |
|---|---|---|
| Exact mirror | Sao chép field hiện hành từ một owner | So khóa, version và canonical values |
| Derived projection | Kết hợp/biến đổi nhiều nguồn | Tính lại theo transformation và source versions |
| Cache | Bản sao có TTL hoặc invalidation | Evict, refresh hoặc chờ hết hạn theo SLO |
| Historical snapshot | Lưu giá trị được chấp nhận tại một thời điểm nghiệp vụ | Đối chiếu nguồn giao dịch lịch sử, không đồng bộ với giá hiện tại |
| Aggregate | Tổng hợp nhiều entity/event | Recompute theo mốc dữ liệu hoặc contribution ledger |

Ví dụ, Product hôm nay giá 1.300.000 đồng, OrderLine của đơn tuần trước ghi `unitPriceAtPurchase=1.000.000`. Đây **không phải drift** cần sửa. Nếu đối soát bằng giá hiện tại, job sẽ phá chứng từ lịch sử.

## 3. Nguồn có thẩm quyền và quyền sở hữu field

**Source of truth** là nơi có quyền quyết định một thông tin nghiệp vụ. Một Search document có thể được tạo từ nhiều owners:

| Field ở Search Card | Source owner | Có được sửa ngược nguồn không? |
|---|---|---|
| `title` | Catalog Service | Không |
| `priceMinor` | Pricing Service | Không |
| `isAvailable` | Inventory Service | Không |
| `ratingAverage` | Review Aggregator | Không |
| `sourceVersions` | Projection pipeline | Không, chỉ metadata |
| `indexedAt` | Search indexer | Không, metadata nội bộ |

Nếu ứng dụng cho người dùng chỉnh `displayLabel` trực tiếp trong Search trong khi Catalog cũng đồng bộ `title`, cần thiết kế hai field riêng hoặc quy tắc ưu tiên. Job không thể quyết định “bản nào thắng” nếu **quyền sở hữu còn mơ hồ**.

## 4. Một sơ đồ đồng bộ hai đường

~~~mermaid
flowchart TD
    A["Business command"] --> B["Source of truth"]
    B --> C["Transactional outbox / CDC"]
    C --> D["Event bus"]
    D --> E["Projection updater"]
    E --> F["Search / Cache / Read model"]
    B --> G["Scheduled reconciler"]
    F --> G
    G --> H["Compare, classify, guard"]
    H -->|"Safe repair"| F
    H --> I["Metrics, checkpoint, audit"]
~~~

- **Event pipeline** giảm độ trễ đồng bộ thông thường.
- **Reconciliation** phát hiện event bị bỏ qua, consumer bug, target bị sửa ngoài luồng hoặc migration chưa hoàn tất.
- **Source validation ở thời điểm ghi** bảo vệ các invariant quan trọng như tồn kho và quyền đặt hàng.

Reconciler không thay thế hai lớp còn lại; nó đóng vai trò **cơ chế phục hồi và kiểm chứng hội tụ**.

## 5. Tại sao bản sao có thể lệch?

Những nguyên nhân thực tế:

1. Transaction nguồn commit nhưng publish event thất bại.
2. Event được publish nhưng consumer crash trước khi apply.
3. Consumer apply thành công nhưng ACK với queue thất lạc, event gửi lại.
4. Event v12 đến sau event v13.
5. Search index tạm unavailable, retry/DLQ bị bỏ quên.
6. Cache invalidation không tới tất cả vùng.
7. Code mapping thay đổi schema nhưng chưa rebuild dữ liệu cũ.
8. Backfill chạy dở giữa chừng.
9. Job cron bị tắt hoặc checkpoint lỗi.
10. Xóa nguồn nhưng mất delete event.
11. ID/tenant mapping sai sau migration.
12. Một bản sao bị chỉnh trực tiếp ngoài service owner.
13. Replica nguồn đọc được còn lag.
14. Lỗi chuyển đổi currency, decimal, timezone hoặc Unicode.
15. Quyền dữ liệu thay đổi nhưng projection quyền truy cập chậm cập nhật.

Mỗi nguyên nhân đòi **phân loại** thay vì luôn áp một lệnh overwrite.

## 6. Từ eventual lag đến drift vượt ngưỡng

Một bản sao có thể cũ vài giây vì pipeline bất đồng bộ nhưng vẫn nằm trong freshness SLO. Một bản stale nhiều giờ có thể là sự cố.

Cần định nghĩa:

- **Expected lag:** thời gian đồng bộ bình thường.
- **Grace window:** khoảng chưa gắn nhãn drift cần sửa.
- **Detection delay:** thời gian từ khi sai khác xuất hiện đến khi bị phát hiện.
- **Repair delay:** từ lúc phát hiện đến khi sửa được.
- **Visibility delay:** từ lúc target được sửa đến khi read API nhìn thấy.
- **Maximum tolerated staleness:** chỉ coi là hard bound nếu hạ tầng thực sự bảo đảm.

Một cron chạy mỗi đêm không thể tự hứa mọi Search Card mới trong một phút. Ngược lại một Read API dùng Search stale có thể chấp nhận ở trang discovery nhưng không an toàn cho xác nhận thanh toán.

## 7. Các trạng thái đối soát

| Trạng thái | Dấu hiệu | Hành động phù hợp |
|---|---|---|
| `IN_SYNC` | Version/schema/payload đúng theo contract | Ghi nhận |
| `MISSING_TARGET` | Source có, target không | Conditional create |
| `STALE_TARGET` | Target `sourceVersion` thấp hơn | Rebuild có version guard |
| `SAME_VERSION_MISMATCH` | Version bằng nhưng canonical payload khác | Audit, xem mapping/corruption |
| `SCHEMA_MISMATCH` | Projection được tạo bằng transformation cũ | Schema-aware rebuild |
| `AHEAD_TARGET` | Target version cao hơn source được quan sát | Không downgrade; đọc source lại |
| `ORPHAN_TARGET` | Target còn record mà authoritative source đã xóa/hết hợp lệ | Xóa/tombstone có bằng chứng |
| `DEFERRED_LAG` | Chênh lệch vẫn trong grace window | Chờ kiểm lại |
| `UNKNOWN` | Không đủ dữ liệu để kết luận do timeout/permission/migration | Không sửa mù; retry/escalate |

Các trạng thái là **quy ước của ứng dụng** chứ không phải enum chung có sẵn ở mọi database.

## 8. Thiết kế metadata để so sánh

Document nguồn:

~~~json
{
  "tenantId": "t-17",
  "productId": "p-101",
  "title": "Bàn phím cơ",
  "status": "ACTIVE",
  "version": 42,
  "generation": 1
}
~~~

Projection:

~~~json
{
  "_id": "t-17#p-101",
  "title": "Bàn phím cơ",
  "status": "ACTIVE",
  "sourceVersion": 42,
  "generation": 1,
  "projectionSchemaVersion": 3,
  "digestAlgorithm": "sha256-canonical-v1",
  "contentDigest": "illustrative-value"
}
~~~

Metadata có ích:

- **Stable key**: tenant + entity ID.
- **Source version**: tăng đơn điệu theo entity hoặc scope được định nghĩa.
- **Generation/epoch**: phân biệt một ID bị xóa rồi tái tạo.
- **Projection schema version**: cho biết transformation nào đã tạo target.
- **Content digest**: xác minh payload chuẩn hóa.
- **Delete/tombstone marker**: không cho event cũ làm record sống lại.
- **Checkpoints/watermarks**: cho biết vùng dữ liệu đã quét.

Một timestamp như `lastProjectedAt` hữu ích cho vận hành nhưng **không thay thế version**.

## 9. Version có phạm vi

Product v42 và Inventory v900 không có nghĩa Inventory “mới hơn Product”; chúng thuộc hai stream khác nhau. Để đồng bộ Search Card đa nguồn, có thể lưu:

~~~json
{
  "productVersion": 42,
  "pricingVersion": 18,
  "inventoryVersion": 900,
  "ratingVersion": 137,
  "projectionSchemaVersion": 4
}
~~~

Khi nhận Product event v43, so nó với **productVersion=42**, không so với max của mọi version (900). Một global version chỉ có nghĩa nếu một protocol thực sự định nghĩa thứ tự toàn cục đó.

## 10. Version khác timestamp

Không lấy công thức `now - updatedAt` làm thước đo drift mặc định:

- Record không đổi trong ba năm vẫn có thể là bản mới nhất.
- Target vừa được cache lại có thể vẫn chứa state cũ nếu nguồn đọc là follower stale.
- Event time do client cung cấp khác commit time.
- Đồng hồ nhiều region có clock skew.
- Index refresh có độ trễ riêng với commit.

Nên dùng **source commit version/sequence**, và khi đo độ trễ theo thời gian phải ghi rõ hai mốc thời gian nào được so sánh.

## 11. Canonical projection và digest

Source có những field ngoài projection:

~~~json
{
  "productId": "p-101",
  "title": "Bàn phím cơ",
  "status": "ACTIVE",
  "auditNote": "changed by admin",
  "updatedAt": "2026-11-14T09:00:00Z"
}
~~~

Search chỉ cần:

~~~json
{
  "id": "p-101",
  "label": "Bàn phím cơ",
  "status": "ACTIVE"
}
~~~

Định nghĩa một pure transformation:

~~~text
project(source):
    return {
        id: source.productId,
        label: normalizeText(source.title),
        status: source.status
    }

digest = SHA256(canonicalJson(project(source)))
~~~

Canonical form phải quy định thứ tự key, precision tiền, định dạng ngày giờ, Unicode, null so với missing, array order có ý nghĩa hay không, và các field được phép loại bỏ. Hash cho biết payload khác nhau, **không tự cho biết bản nào đúng**.

## 12. Same-version mismatch không phải lag thông thường

Giả sử source và target đều v42, projection schema đều v3, nhưng digest khác. Có thể có:

- Mapping bug hoặc thay đổi code nhưng quên tăng schema version.
- Source field thay đổi mà version không tăng.
- Target bị sửa bằng một script riêng.
- Serialize decimal không nhất quán.
- Sự cố mất dữ liệu.

Cần ghi metric riêng `sameVersionMismatch`, lưu fingerprint/schema metadata và triage. Rebuild theo source có thể đúng, nhưng **không được tự động xóa mất bằng chứng nguyên nhân hệ thống**.

## 13. Target ahead phải tránh downgrade

~~~text
Source read: v42
Target:      v43
~~~

Không ép target về v42. Source read có thể đến từ replica trễ; event processor có thể đã nhận v43 trước. Cũng có thể là reuse ID, generation hoặc migration bug.

Cách xử lý:

1. Xác minh key/tenant/generation.
2. Đọc authoritative source với consistency phù hợp.
3. Nếu vẫn không khớp, kiểm tra event/commit sequence.
4. Ghi `AHEAD_TARGET` hoặc quarantine.
5. Chỉ sửa sau khi xác định mốc đúng.

## 14. Chỉ sao chép field do projection sở hữu

Một Search document có thể có:

~~~json
{
  "productId": "p-101",
  "sourceTitle": "Bàn phím cơ",
  "customDisplayLabel": "Bàn phím yêu thích",
  "effectiveLabel": "Bàn phím yêu thích"
}
~~~

Nếu Catalog đổi `sourceTitle`, job không nên xóa `customDisplayLabel` do người dùng đặt nếu field này có owner khác. Cách đúng là tách field và quy tắc tính `effectiveLabel`, hoặc dùng transformation có ownership rõ.

## 15. Vì sao cần quét hai chiều?

**Source → Target**:

- Source có entity nhưng target thiếu.
- Target version cũ.
- Projection schema sai.
- Digest khác.

**Target → Source**:

- Target còn ghost của record đã xóa ở source.
- Target có duplicate key/generation cũ.
- Target mang tenant mapping sai.
- Target giữ dữ liệu do migration không còn hợp lệ.

Nếu chỉ quét source, một record đã hard-delete ở nguồn có thể biến mất khỏi mọi source scan nhưng vẫn hiện diện trong Search mãi mãi.

## 16. Delete event là trường hợp khó

Timeline:

~~~text
t0: Source Product ACTIVE v20
t1: Source delete, tombstone v21
t2: Delete event v21 bị mất
t3: Target vẫn ACTIVE v20
~~~

Có tombstone v21, job biết delete mới hơn v20. Nhưng nếu hard-delete ngay và không có deletion log, `source.get()` trả null có thể đồng nghĩa:

- Entity đã xóa.
- Đọc sai tenant.
- Replica chưa bắt kịp.
- Migrate đang chạy.
- Đường nguồn tạm unavailable.
- Entity chưa từng tồn tại.

**Không xóa hàng loạt target chỉ vì source API timeout**. Cần authoritative absence/deletion manifest, policy xác minh và grace period phù hợp.

## 17. Tombstone và ID generation

Tombstone:

~~~json
{
  "tenantId": "t-17",
  "productId": "p-101",
  "generation": 2,
  "deleted": true,
  "sourceVersion": 43,
  "deletedAt": "2026-11-14T09:30:00Z"
}
~~~

Nếu event cũ `ProductUpdated(v42)` tới sau delete v43, target phải từ chối để không **resurrect** record.

Retention của tombstone/version marker phải xét:

- Thời gian một consumer có thể offline.
- Retention của message queue và retry/DLQ.
- Restore backup cũ.
- Chính sách ID reuse.
- Privacy/PII deletion requirements.
- Chi phí lưu metadata tối thiểu không nhạy cảm.

Không mặc định giữ payload PII vô hạn chỉ để chống replay.

## 18. Sửa có điều kiện để không tạo drift mới

Một race điển hình:

~~~text
Reconciler đọc Source v42
Source đổi thành v43
Event Worker ghi Target v43
Reconciler tiếp tục ghi Target v42
~~~

Nếu job update target vô điều kiện, nó **lùi dữ liệu**. Cần guard tại đích:

\[
targetVersion_{after} \ge targetVersion_{before}
\]

với cùng entity/generation và cùng semantics phiên bản. Version check **trước** write trên worker không đủ, vì target có thể đổi giữa check và write.

## 19. Thuật toán reconcileOne

~~~text
reconcileOne(key):
    source = readAuthoritativeSource(key)
    if source unavailable:
        return UNKNOWN

    target = readTarget(key)
    if target unavailable:
        return UNKNOWN

    if source is verified tombstone:
        return deleteTargetConditionally(key, source, target)

    if source absent without verified deletion:
        return DEFER_ORPHAN_VERIFICATION

    expected = project(source, currentSchema)

    if target missing:
        return createIfAbsent(key, expected)

    if target.generation > expected.generation:
        return AHEAD_TARGET

    if same generation and target.sourceVersion > expected.sourceVersion:
        return AHEAD_TARGET

    if target.sourceVersion == expected.sourceVersion
       and target.schemaVersion == expected.schemaVersion
       and target.digest == expected.digest:
        return IN_SYNC

    if same version but different digest:
        recordIntegrityMismatch(key)

    return compareAndReplaceAtTarget(
        key,
        expectedTargetGeneration=target.generation,
        expectedTargetVersion=target.sourceVersion,
        newValue=expected
    )
~~~

Sau CAS thất bại, job phải đọc lại hoặc bỏ qua với trạng thái race; **không retry vô điều kiện bằng expected payload cũ**.

## 20. CAS và tính hội tụ

Một thao tác apply version hợp lệ cần có những kết quả:

~~~text
Target v40 + incoming v42 -> apply v42
Target v42 + incoming v42 -> no-op hoặc verify digest
Target v43 + incoming v42 -> reject stale
Target tombstone v44 + incoming v42 -> reject resurrection
Target missing + incoming v42 -> conditional create
~~~

Tùy engine, guarded upsert/insert-if-absent có thể trả duplicate key khi một writer khác chen vào. Đây thường là **race cần đọc lại**, không phải lý do để xóa rồi insert lại.

## 21. Ví dụ MongoDB: guarded update

Giả sử đích cũng là MongoDB:

~~~javascript
// Job đã đọc target với sourceVersion=40.
const result = db.productCards.updateOne(
  {
    _id: "t-17#p-101",
    sourceVersion: NumberLong("40")
  },
  {
    $set: {
      sourceVersion: NumberLong("42"),
      projectionSchemaVersion: 3,
      title: "Bàn phím cơ",
      status: "ACTIVE"
    }
  }
);
~~~

Khi `matchedCount=0`, có thể bản v43 đã được cập nhật hoặc target đã bị xóa; phải đọc lại, không ép `upsert` cho ra một bản duplicate.

**Cẩn thận:** `upsert` với filter `sourceVersion: {$lt: 42}` có thể không match record hiện hành v43 và sau đó cố insert cùng `_id`, tạo duplicate-key error. Không xem nó là một atomic monotonic upsert hoàn hảo mà không có nhánh xử lý.

## 22. Ví dụ Redis: cache thường nên bị invalidated

Redis cache:

~~~text
key=product:t-17:p-101
sourceVersion=40
TTL=120s
~~~

Source đã v42. Hướng sửa:

- Evict cache, để lần đọc sau load authoritative source.
- Hoặc refresh bằng version guard.
- Nếu vẫn trong allowed staleness, có thể defer.
- Giới hạn refresh traffic để tránh cache stampede.

Pseudo logic:

~~~text
observed = GET(key)
if observed.sourceVersion < source.version:
    compareAndDelete(key, observed.version)
~~~

`compareAndDelete` là abstraction ứng dụng, không phải tên lệnh Redis mặc định. Có thể dùng Lua/transaction primitive phù hợp. Một `DEL` sau khi cache vừa được làm mới có thể xóa bản tốt và gây miss không cần thiết.

## 23. Search index có visibility riêng

Với Elasticsearch/OpenSearch hoặc hệ tương tự, cần phân biệt:

- Request index được xác nhận.
- Document đã được ghi ở index.
- Search refresh đã làm document visible cho query.
- Replica search shard đã theo kịp.
- SourceVersion được áp có đúng hay không.

Một GET/search chưa thấy document ngay sau indexing không chứng minh write thất bại vĩnh viễn. Reconciler nên dùng source version hoặc cơ chế optimistic/external versioning theo khả năng engine; nếu không có guard phù hợp, dùng một writer/queue có thứ tự.

Search Card stale không được là nguồn quyết định cuối cho checkout hoặc quyền truy cập nhạy cảm.

## 24. Projection hợp nhất nhiều nguồn

Search Card:

~~~json
{
  "productId": "p-101",
  "title": "Bàn phím cơ",
  "priceMinor": 1290000,
  "isAvailable": true,
  "productVersion": 42,
  "priceVersion": 18,
  "inventoryVersion": 900
}
~~~

Một event Product v43 phải được so với `productVersion=42`, không với `inventoryVersion=900`. Không có thứ tự tổng quát giữa version của hai owner.

Với nhiều nguồn, cần biết consistency contract của phép join: có chấp nhận eventual snapshot của nhiều thời điểm không, hay nghiệp vụ đòi snapshot giao dịch được phối hợp? Đọc lần lượt từ ba service không tự tạo global atomic snapshot.

## 25. Schema migration cũng cần reconciliation

Nếu sourceVersion vẫn 42 nhưng projection schema đổi từ 3 sang 4, target cần rebuild theo transformation mới. Kế hoạch:

1. Version hóa projection schema.
2. Triển khai consumer mới có guard schema generation.
3. Backfill target cũ từ source.
4. Chặn consumer cũ ghi schema 3 lên bản v4.
5. Đo tỷ lệ target đã chuyển schema.
6. Cutover read path.
7. Có rollback và re-reconcile theo generation.

Không xem cùng sourceVersion là luôn `IN_SYNC` khi payload schema đã đổi.

## 26. Incremental path không thay full coverage

Có thể dùng:

~~~text
Write source -> outbox/CDC -> consumer -> target

Every few minutes:
  scan recently changed keys / lagging partitions

Every day or week:
  source-to-target sweep
  target-to-source sweep

After schema change or incident:
  focused rebuild + verification
~~~

Những khoảng thời gian là minh họa. Lịch cần dựa trên freshness SLO, dung lượng dữ liệu, khả năng read scan và mức rủi ro khi consumer bị lỗi.

Incremental sweep có thể bỏ lỡ một key nếu event nguồn bị mất và nguồn không có change history đầy đủ. Full scan giúp tìm lỗi tồn lâu hơn.

## 27. Pagination và keyset scan

Không thể load hàng triệu document vào RAM rồi so một lần. Một pseudo scan:

~~~text
cursor = loadCheckpoint(bucket)

while true:
    page = source.scanAfter(cursor, batchSize=500)
    if page.empty:
        markBucketComplete()
        break

    for entity in page:
        compareAndQueueRepair(entity)

    persistCheckpoint(page.lastCompletedKey)
~~~

Cần dùng **cursor/pagination được engine hỗ trợ**. MongoDB có thể dùng indexed keyset scan; DynamoDB có `LastEvaluatedKey`; Cassandra có paging state/partition-range strategy.

Không mặc định deep `skip/offset` là cách tối ưu cho dataset lớn. Đồng thời, keyset scan trên dữ liệu biến động vẫn cần xử lý snapshot/concurrent updates.

## 28. Checkpoint phải phản ánh việc đã xử lý

Ví dụ:

~~~json
{
  "jobName": "product-search-reconcile",
  "runId": "run-2026-11-14",
  "bucket": "bucket-07",
  "lastCompletedKey": "t-17#p-100",
  "schemaVersion": 4,
  "snapshotOrWatermark": "supported-value-if-any"
}
~~~

Chỉ nâng checkpoint khi record đã so sánh/sửa thành công hoặc work item được enqueue bền vững theo policy. Nếu một item lỗi, không ghi “toàn bộ bucket clean”.

Phân biệt `SCANNED`, `COMPARED`, `REPAIRED`, `DEFERRED` và `VERIFIED`. Resume sau crash có thể xử lý lại trang cũ nên **repair phải idempotent**.

## 29. Scan đang chạy thì nguồn vẫn đổi

~~~text
Scan đã qua key K050
Một writer cập nhật K050
Scan tiếp tục K051...
~~~

Nếu scan không dùng snapshot/watermark đúng, update K050 có thể không được kiểm lại trong lượt này.

Những hướng xử lý:

- Snapshot read theo semantics DB hỗ trợ.
- Ghi high-watermark của source change log, scan và replay events sau mốc.
- Chạy sweep lặp lại theo chu kỳ.
- Dùng overlap window và version guard.
- Theo dõi coverage theo partition/snapshot.
- Không tuyên bố một live scan tự bao quát mọi concurrent write.

**Full scan là coverage của một quy trình đọc; nó không mặc định là snapshot nhất quán toàn database.**

## 30. Watermark không phải timestamp mới nhất của một node

Một pipeline có ba partition, mỗi partition ở offset khác:

~~~text
P1 applied through 150
P2 applied through 147
P3 applied through 160
~~~

Không thể đơn giản nói “đã xử lý đến offset 160 trên toàn hệ” nếu các offset là namespace riêng. Cần lưu checkpoint per partition hoặc một global watermark có semantics được định nghĩa.

Phân biệt source commit time, event time, ingest time, replica applied time và search refresh time. `dataAsOf` phải mô tả đúng mốc đã bao phủ, không phải lúc dashboard được render.

## 31. Chia việc theo bucket và tenant

Một reconciler lớn có thể chia theo:

- Tenant.
- Hash bucket của entity ID.
- Shard/partition token range.
- Thời gian, với trường hợp record có time key.
- Loại projection.
- Mức độ khẩn cấp.

Nhưng mỗi bucket cần checkpoint riêng và kế hoạch bao phủ. Nếu source rebalance hoặc chunk migrate, việc dựa vào shard ownership thay đổi có thể bỏ record. Nên có **partition plan ổn định** hoặc cơ chế traversal phù hợp.

Tránh hai worker cùng sửa một key mà không có CAS/idempotency/lease/fencing thích hợp.

## 32. Tối ưu bằng bucket digest

Với dữ liệu rất lớn:

1. Chia key theo bucket deterministically.
2. Tính digest cho canonical records ở nguồn tại một mốc.
3. Tính digest theo cùng schema/mốc cho target.
4. Bucket hash khớp thì có thể bỏ qua so chi tiết theo confidence của thuật toán.
5. Bucket mismatch thì drill down tới từng key.
6. Repair có guard và verify lại.

~~~text
Bucket 00: sourceHash=A, targetHash=A -> no detail scan
Bucket 01: sourceHash=B, targetHash=C -> inspect keys
Bucket 02: sourceHash=D, targetHash=D -> no detail scan
~~~

Nếu hai bên tính trên snapshot khác nhau hoặc normalize khác nhau, hash mismatch có thể là false alarm. Hash bằng nhau cũng không chứng minh mọi field đúng nếu rule bỏ mất một field quan trọng.

## 33. Reconciliation của aggregate khó hơn mirror

Ví dụ DailyRevenue:

~~~text
DailyRevenue(day,category).total
  = SUM(committed OrderLine amount for that day/category)
~~~

Nếu expected=1.000.000, target=900.000, một job làm `INCREMENT 100000` mà không idempotent có thể cộng lại lần nữa sau crash.

Hai hướng:

- **Recompute-and-replace** tổng từ nguồn theo snapshot/watermark ổn định, có version guard.
- **Contribution ledger** lưu mỗi OrderLine/event ID đã áp, cộng hoặc trừ đúng một lần.

Delta retry mà không biết contribution nào đã applied dễ tạo sai số lặp. Đối soát aggregate phải xét cả **quy tắc cập nhật hồi tố** như refund hoặc late event.

## 34. Java worker minh họa

Pseudocode Java (không phải SDK build trực tiếp):

~~~java
enum DriftType {
    IN_SYNC, MISSING_TARGET, STALE_TARGET,
    SAME_VERSION_MISMATCH, SCHEMA_MISMATCH,
    AHEAD_TARGET, ORPHAN_TARGET, UNKNOWN
}

ReconcileResult reconcileOne(EntityKey key) {
    SourceRead source = sourceRepo.readAuthoritatively(key);
    if (!source.isKnown()) {
        return ReconcileResult.defer(DriftType.UNKNOWN);
    }

    TargetRead target = targetRepo.read(key);
    if (!target.isKnown()) {
        return ReconcileResult.defer(DriftType.UNKNOWN);
    }

    if (source.isVerifiedDeleted()) {
        return deletionPolicy.deleteConditionally(
            key, source.tombstone(), target
        );
    }

    if (source.isAbsentWithoutDeletionEvidence()) {
        return ReconcileResult.defer(DriftType.UNKNOWN);
    }

    ExpectedProjection expected =
        projectionFactory.build(source.record());

    if (target.isMissing()) {
        boolean created = targetRepo.insertIfAbsent(expected);
        return created ? ReconcileResult.created()
                       : ReconcileResult.retryableRace();
    }

    if (target.record().isNewerThan(expected)) {
        return ReconcileResult.defer(DriftType.AHEAD_TARGET);
    }

    if (target.record().matches(expected)) {
        return ReconcileResult.inSync();
    }

    auditDriftWithoutSensitivePayload(key, expected, target);

    boolean applied = targetRepo.compareAndReplace(
        key,
        target.record().generation(),
        target.record().sourceVersion(),
        expected
    );

    return applied ? ReconcileResult.repaired()
                   : ReconcileResult.retryableRace();
}
~~~

Muốn dùng trong ứng dụng thật phải map `readAuthoritatively`, `compareAndReplace`, errors, timeout, schema generation và delete semantics sang API DB/SDK cụ thể.

**Đặc tính chính:** pure transformation từ source, không sửa source từ target, guarded repair và audit.

## 35. Event worker và reconciler phải dùng cùng ordering rule

Nếu event handler bỏ qua event cũ nhưng reconciler lại overwrite vô điều kiện, hai đường sẽ đánh nhau.

Nên chuẩn hóa một apply contract:

~~~text
apply(targetKey, incomingGeneration, incomingVersion, payload):
    reject if incoming generation older than target generation
    reject if same generation and incoming version older
    if same version:
        compare schema/digest and apply specific migration rules
    otherwise:
        atomic conditional replace
~~~

Quy tắc này dùng chung ở event projection, manual repair và periodic job. Nếu có nhiều source versions, cần guard theo từng source component hoặc có owner single-writer phù hợp.

## 36. Repair phải idempotent

Một job có thể được chạy lại vì:

- Worker crash.
- Checkpoint replay.
- Hai job overlap.
- Queue redelivery.
- Manual repair trùng với auto repair.
- Retry sau timeout chưa rõ outcome.

Với cùng version/generation, apply lại nên trở thành no-op hoặc verification, không nhân đôi counter, event, email hoặc payment.

Đối với một target delete, retry cũng phải an toàn: delete đã áp không được tạo lỗi ngẫu nhiên rồi phục hồi entity bằng stale update.

## 37. Không phát ra business event như thể nguồn vừa đổi

Phát hiện Search Card cũ rồi sửa không đồng nghĩa Product đã được user cập nhật. Nếu reconciler publish `ProductChanged` như nguồn, các service khác có thể hiểu nhầm và tạo vòng lặp.

Nếu cần event, dùng loại có nghĩa riêng như `ProjectionRepaired`, có sourceVersion, operationId và consumer idempotency. Dữ liệu nghiệp vụ phải do source owner phát những thay đổi có thẩm quyền.

## 38. Reconciliation không thay business invariant

Search vẫn hiển thị sản phẩm ACTIVE dù Inventory/source đã INACTIVE. Nếu Checkout dựa vào Search Card để xác nhận mua, job đối soát ngày hôm sau không thể sửa lại việc bán sai hôm nay.

Với những thao tác quan trọng:

- Kiểm tra nguồn có thẩm quyền tại lúc commit.
- Dùng conditional update/transaction hoặc invariant enforcement.
- Dùng idempotency cho retry.
- Không xem cache/Search là nguồn quyết định quyền hay tiền.
- Cho UX hiển thị dữ liệu stale nếu business cho phép, nhưng ghi rõ giới hạn.

**Convergence của projection khác correctness của write path.**

## 39. Đối soát không đồng nghĩa sửa hai chiều

Nếu target là read model thuần, hướng sửa thường **source → target**. Nếu hai hệ đều cho phép user chỉnh cùng field, cần domain merge policy riêng, conflict resolution hoặc coordination thích hợp.

Không dùng “timestamp lớn nhất thắng” cho mọi field nếu đồng hồ khác nhau hoặc quyền owner chưa định nghĩa.

## 40. Không tự sửa các trường hợp không đủ bằng chứng

Nên đưa vào quarantine hoặc manual review khi:

- Hai nguồn cùng claim ownership.
- Target version ahead không giải thích được.
- Source read đang stale/unavailable.
- Same-version payload khác và chưa biết mapping bug.
- Tenant key/generation mâu thuẫn.
- Đang đổi projection schema với hai writer chạy song song.
- Legal retention/privacy policy không rõ.
- Projection chứa field người dùng chỉnh trực tiếp.
- Mismatch ảnh hưởng ledger/tài chính và cần audit riêng.

Auto-repair phải có tiêu chí rõ, không chỉ có nút “make source and target equal”.

## 41. Tần suất và độ ưu tiên

Một phương án vận hành minh họa:

| Đường | Tần suất ví dụ | Mục tiêu |
|---|---|---|
| Outbox/CDC | Khi source commit | Cập nhật sớm |
| Targeted drift check | Khi API phát hiện mismatch | Sửa nhanh key cụ thể |
| Incremental sweep | Mỗi vài phút | Phát hiện event trễ/bỏ qua |
| Full source scan | Mỗi ngày/tuần | Bao phủ missing/stale |
| Full reverse scan | Định kỳ | Phát hiện orphan |
| PII deletion verification | Theo deadline policy | Đảm bảo dữ liệu cần xóa đã xử lý |
| Schema backfill | Theo migration | Chuyển projection generation |

Đây là ví dụ; lịch thực tế phụ thuộc SLO, dung lượng, tải và rủi ro từng bản sao.

## 42. Throttling và backpressure

Quét 100 triệu records có thể ảnh hưởng production:

- Source read QPS tăng.
- Network cross-region tăng.
- Search indexing/refresh nặng.
- Cache eviction làm tăng miss.
- Ổ đĩa và compaction quá tải.
- Job repair xếp hàng khiến lag tăng.

Cần:

- Rate limit per shard/tenant.
- Adaptive concurrency theo latency/error.
- Batching phù hợp với engine.
- Retry exponential backoff + jitter.
- Timeout và deadline.
- Queue capacity/backpressure.
- Dry-run/canary trước mass repair.
- Có kill switch khi gây tác động production.
- Ưu tiên read/write nghiệp vụ.

Một job “sửa dữ liệu” không nên tạo ra downtime vì quét/ghi quá mạnh.

## 43. Fairness cho tenant lớn

Một tenant có 5 triệu products, các tenant khác chỉ vài trăm. Nếu quét theo tenant tuần tự, một tenant lớn có thể chiếm toàn bộ thời gian job.

Nên:

- Chia tenant lớn thành hash buckets.
- Round-robin hoặc weighted fairness.
- Checkpoint per bucket.
- Theo dõi starvation và max-unreconciled-age.
- Giới hạn QPS/concurrency từng tenant.
- Ưu tiên những sai khác có ảnh hưởng privacy/security cao.

Không nên giả định cardinality tenant đồng đều.

## 44. Coverage khác “đã xử lý nhiều records”

Một dashboard ghi:

~~~text
scanned = 10,000,000
repaired = 100,000
~~~

chưa đủ. Cần biết:

- Mẫu số expected bao nhiêu?
- Source/target reverse scan đã hoàn tất không?
- Bao nhiêu key timeout/deferred?
- Có bucket nào chưa quét?
- Coverage ở snapshot/window nào?
- Repair đã verify visible state chưa?
- Có orphan mới xuất hiện trong khi scan?
- Có record nào bị lọc khỏi báo cáo không?

Không bỏ 100.000 lỗi timeout rồi tuyên bố “100% in sync” trên phần còn lại.

## 45. Những metric nên theo dõi

| Metric | Ý nghĩa |
|---|---|
| `runsStarted / runsCompleted` | Job chạy và kết thúc |
| `partitionsCompleted` | Coverage theo bucket |
| `keysScanned / keysCompared` | Khối lượng thực |
| `missingTargetCount` | Source có, target thiếu |
| `staleTargetCount` | Target chậm sourceVersion |
| `orphanTargetCount` | Ghost sau xóa |
| `sameVersionMismatchCount` | Integrity/mapping bug |
| `aheadTargetCount` | Target vượt mốc nguồn |
| `schemaMismatchCount` | Projection schema cũ |
| `repairSuccess / repairFailure` | Tỷ lệ sửa |
| `guardRejectedCount` | CAS chặn stale overwrite |
| `deferred / unknownCount` | Chưa đủ bằng chứng |
| `maxUnreconciledAge` | Sai khác lâu nhất |
| `eventToProjectionLag` | Độ trễ pipeline sự kiện |
| `sourceReadQps / targetWriteQps` | Chi phí tác động |
| `repairQueueBacklog` | Công việc còn tồn |
| `targetVisibilityDelay` | Bao lâu tới khi read thấy sửa |

Các metric nên tách theo projection, tenant, shard/region, schema generation và severity.

## 46. Freshness SLO và repair SLO khác nhau

Ví dụ một sản phẩm có thể đặt:

- 99,9% Search Cards cập nhật trong 30 giây theo pipeline bình thường.
- Mismatch trên 10 phút được đưa vào queue ưu tiên.
- Full coverage scan hoàn tất theo lịch vận hành.
- PII deletion được xác minh trong deadline của policy.

Không nhầm:

1. Detection delay.
2. Queue wait.
3. Repair execution.
4. Search refresh visibility.
5. Verification.

Một worker báo “repair success” chưa chắc Search query đã thấy bản mới nếu refresh chưa xong.

## 47. Privacy và tenant isolation

Một reconciler thường được cấp quyền đọc rất rộng. Phải bảo đảm:

- Key bao gồm tenant namespace.
- Không sửa record tenant khác do trùng entity ID.
- Credential có least privilege.
- Không log full PII/password/payment data vào drift report.
- Chỉ lưu digest/version/audit metadata cần thiết.
- Deletion manifest và tombstone retention hợp pháp.
- Không export dữ liệu sang region không được phép.
- Audit người/job thực hiện mass repair.
- Có rollback/stop plan với auto-repair diện rộng.

Với yêu cầu xóa PII, việc Search còn bản cũ là vấn đề nghiêm trọng. Cần kiểm kê mọi projection/backup theo retention policy và **ngăn event cũ tạo lại payload đã xóa**.

## 48. Các tình huống kiểm thử quan trọng

| Kịch bản | Điều cần xác minh |
|---|---|
| Lost update event | Job phát hiện target stale và sửa |
| Lost create event | Missing target được tạo |
| Lost delete event | Tombstone/reverse scan phát hiện orphan |
| Old event replay | Không resurrect sau tombstone |
| Event worker ghi v43, reconciler cầm v42 | Guard ngăn downgrade |
| Same version, different digest | Không báo in-sync nhầm |
| Source read timeout | Không xóa target |
| Target ahead | Không ép về version thấp |
| Worker crash sau nửa page | Resume không bỏ key |
| Live scan có concurrent writes | Coverage contract được giữ |
| Schema migration | Old writer không ghi schema cũ lên mới |
| Whale tenant | Job không làm đói tenant khác |
| Two workers repair same key | Idempotency/CAS bảo vệ |
| Privacy deletion | Payload bị xóa, event cũ không tái tạo |
| Search refresh delayed | Metrics phân biệt ACK và visibility |

Chạy fault injection/chaos trong môi trường được phép, có phương án cô lập và phục hồi.

## 49. Bài tập A — Snapshot lịch sử

OrderLine lưu giá 1.000.000, Product hiện tại 1.300.000. Reconciler muốn “sửa” OrderLine lên 1.300.000.

**Hỏi:** có đúng không?

**Hướng giải:** không. Đây là historical snapshot hợp lệ; cần so với giá giao dịch lúc đặt hàng, không giá hiện tại.

## 50. Bài tập B — Source-only scan

Source đã hard-delete Product X, Search còn X. Job chỉ quét mọi Product còn tồn tại ở source.

**Hỏi:** tìm được lỗi không?

**Hướng giải:** không chắc; X không xuất hiện trong source scan. Cần reverse scan hoặc deletion manifest/tombstone.

## 51. Bài tập C — Stale repair

Reconciler đọc source v12; event worker ghi target v13; reconciler định ghi v12.

**Hỏi:** phải làm gì?

**Hướng giải:** CAS/external version guard phải từ chối downgrade; job có thể re-read authoritative source.

## 52. Bài tập D — Cùng version khác digest

Source và target cùng v7, schema v3 nhưng payload canonical khác.

**Hỏi:** có được đánh dấu in-sync không?

**Hướng giải:** không. Cần điều tra mapping/integrity và có thể rebuild có giám sát.

## 53. Bài tập E — Clock và age

Product không thay đổi hai năm; `updatedAt` rất cũ.

**Hỏi:** record có stale không?

**Hướng giải:** không tự động; nếu không có write mới bị thiếu thì vẫn là latest.

## 54. Bài tập F — Source timeout

Target có Product, source GET timeout.

**Hỏi:** delete target vì source không tìm thấy?

**Hướng giải:** không. Timeout là UNKNOWN, không phải authoritative absence.

## 55. Bài tập G — Aggregate cộng hai lần

Reconciler nhận thấy Revenue thiếu 100.000, chạy `INCREMENT 100000`, crash trước checkpoint rồi chạy lại.

**Hỏi:** có thể sai thế nào?

**Hướng giải:** double increment. Dùng recompute-and-replace theo watermark hoặc contribution ledger với dedupe.

## 56. Bài tập H — Đa nguồn

Search Card có Product v20, Inventory v900. Product event v21 đến.

**Hỏi:** có bỏ v21 vì 21 nhỏ hơn 900 không?

**Hướng giải:** không; Product v21 phải so với Product v20, không so với Inventory.

## 57. Bài tập I — Live scan

Job đã quét key A; A đổi ngay sau đó; job đi hết đến Z.

**Hỏi:** có thể kết luận mọi update đã được kiểm không?

**Hướng giải:** không nếu không có snapshot/watermark replay hoặc vòng lặp coverage phù hợp.

## 58. Bài tập J — Delete rồi event cũ

Source tombstone v31, target đã delete; event Update v30 bị phát lại.

**Hỏi:** cần gì để không tạo lại target?

**Hướng giải:** version/generation marker hoặc consumer guard giữ được logic tombstone dù payload đã được xóa.

## 59. Bài tập K — Mismatch sau đổi schema

Source v42, Target v42 nhưng projectionSchemaVersion target=3 và code mới=4.

**Hỏi:** có cần sourceVersion tăng mới rebuild?

**Hướng giải:** không; schema generation là một lý do rebuild riêng. Cần guard với writer cũ.

## 60. Bài tập L — Coverage 100%

Job quét một triệu keys, 50.000 source reads timeout nhưng bỏ khỏi báo cáo và tuyên bố 100% sạch.

**Hỏi:** sai ở đâu?

**Hướng giải:** thiếu denominator và deferred errors; không có full coverage, phải báo phần chưa kiểm.

## 61. Bài tập M — Quyền truy cập stale

Redis cache user còn ACTIVE nhưng nguồn đã DISABLED. Job sửa cache mỗi đêm.

**Hỏi:** API nhạy cảm có thể tin cache cho phép giao dịch không?

**Hướng giải:** không nếu business/security yêu cầu current authorization; phải xác minh source khi thực hiện hành động.

## 62. Bài tập N — Bucket hash

Một bucket có sourceHash khác targetHash.

**Hỏi:** có nên overwrite mọi entity trong bucket?

**Hướng giải:** không; drill down theo key và version, sửa guarded cho những record lệch, tránh write amplification.

## 63. Checklist triển khai periodic reconciliation

1. Bản sao thuộc loại mirror, projection, cache, snapshot hay aggregate?
2. Owner của từng field và source-of-truth đã rõ chưa?
3. Key có tenant namespace và generation không?
4. SourceVersion có order semantics tin cậy không?
5. Có projectionSchemaVersion/canonical digest không?
6. Dữ liệu được chuẩn hóa cùng rule trước khi so không?
7. Có grace window cho lag hợp lệ không?
8. Có source-to-target scan cho missing/stale không?
9. Có target-to-source scan cho orphan không?
10. Delete có tombstone/deletion evidence không?
11. Có bảo vệ chống event cũ resurrect dữ liệu không?
12. Khi source unavailable có dừng sửa xóa không?
13. Target ahead có bị ngăn downgrade không?
14. Repair có CAS/guard ở đúng thời điểm write không?
15. Có xử lý same-version digest mismatch riêng không?
16. Schema migration có chống old writer không?
17. Quét phân trang có checkpoint bền vững không?
18. Live scan có snapshot/watermark hoặc replay window không?
19. Retry sau crash có idempotent không?
20. Có phân vùng worker và fairness theo tenant không?
21. Background rate limit có bảo vệ production SLO không?
22. Có dry-run, canary và kill switch không?
23. Có audit không lộ PII, tenant isolation và quyền tối thiểu không?
24. Có metrics về drift, repair, deferred và age không?
25. Có fault tests cho lost event, delete, race, restart không?
26. Có mục tiêu thời gian detect/repair/visibility rõ không?

## 64. Mẫu thiết kế reconciliation job

~~~yaml
job: ProductSearchReconcile
sourceOfTruth:
  owner: CatalogService
  identity: tenantIdAndProductId
  version: monotonicPerEntity
target:
  type: SearchReadModel
  identity: tenantIdAndProductId
  projectionSchemaVersion: 4
contract:
  fields:
    - title
    - status
    - categoryId
  compare:
    - entityGeneration
    - sourceVersion
    - projectionSchemaVersion
    - canonicalDigest
  historicalSnapshotsExcluded: true
scan:
  sourceToTarget: periodic
  targetToSource: periodic
  incremental: changeLogWatermark
  checkpoint: perBucket
  pagination: stableKeyOrSupportedCursor
repair:
  create: insertIfAbsent
  update: compareAndSwapByTargetVersion
  delete: verifiedTombstoneOrAuthoritativeAbsence
  aheadTarget: quarantine
  equalVersionDigestMismatch: investigate
  retries: boundedWithExponentialBackoffAndJitter
operations:
  rateLimit: perShardAndTenant
  dryRun: supported
  piiLogging: prohibited
  audit: metadataOnly
observability:
  - coverageCompleted
  - missingTarget
  - staleTarget
  - orphanTarget
  - sameVersionMismatch
  - guardRejected
  - repairSuccess
  - deferredUnknown
  - maxUnreconciledAge
tests:
  - lostUpdateEvent
  - lostDeleteEvent
  - staleEventReplay
  - raceWithNewerProjection
  - crashAndResume
  - sourceUnavailable
~~~

Đây là **mẫu tài liệu kiến trúc**, không phải cấu hình mà MongoDB, Redis hoặc Search engine tự thực thi. Cần hiện thực từng phần bằng API/SDK và hợp đồng consistency của hệ thật.

## 65. Kết luận

**Dữ liệu lặp trong NoSQL là một đánh đổi có chủ đích, không phải lỗi thiết kế.** Tuy nhiên, một bản sao có thể bị mất event, trở nên stale, đổi schema sai, giữ ghost sau delete hoặc bị ghi đè bởi một bản cũ. Vì vậy cần cả **đường cập nhật nhanh** và **vòng đối soát định kỳ**.

Một thiết kế đối soát đáng tin cậy phải:

- Phân biệt source-of-truth với cache, read projection và historical snapshot.
- So sánh theo stable key, version/generation, schema và canonical payload đúng phạm vi.
- Quét cả hai chiều để phát hiện missing, stale và orphan.
- Có tombstone/deletion evidence cho delete.
- Dùng guarded repair để không overwrite cập nhật mới hơn.
- Có checkpoint, snapshot/watermark và idempotency để chạy lại sau lỗi.
- Giới hạn tải, bảo vệ tenant/PII và quan sát coverage thực.
- Không dùng projection stale làm căn cứ commit nghiệp vụ quan trọng.

> **Mục tiêu của reconciliation không phải “copy cho giống” bằng mọi giá, mà là tạo ra một quy trình phát hiện–sửa–xác minh có thể lặp lại, có giới hạn quyền ghi và không làm hệ thống lùi trạng thái.**

Khi định nghĩa rõ nguồn có thẩm quyền, độ cũ được phép và cách áp version an toàn, ứng dụng có thể hưởng lợi từ denormalization mà vẫn giữ khả năng phục hồi trước lỗi phân tán, sự kiện thất lạc và những lần triển khai chưa hoàn chỉnh.
