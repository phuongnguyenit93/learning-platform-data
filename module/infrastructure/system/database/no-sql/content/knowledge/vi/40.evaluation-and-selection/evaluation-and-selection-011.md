# Đánh giá rủi ro phụ thuộc nhà cung cấp và phương án di chuyển

Một doanh nghiệp vận hành nền tảng đặt hàng trên một dịch vụ NoSQL managed. Nhờ tự động sao chép, mở rộng dung lượng và tích hợp với hạ tầng cloud, nhóm nhỏ có thể phục vụ hàng triệu yêu cầu mà không phải trực tiếp quản trị từng node. Sau vài năm, chi phí tăng, một số khu vực chưa được hỗ trợ và công ty cần cân nhắc chuyển nhà cung cấp. Nhóm lập tức phát hiện: dữ liệu có thể xuất được, nhưng application phụ thuộc vào truy vấn theo partition key, global secondary index, conditional write, TTL, stream event, IAM và cách xử lý lỗi riêng của dịch vụ. Việc **chuyển dữ liệu** chỉ là một phần; việc **chuyển hợp đồng vận hành và hành vi nghiệp vụ** mới quyết định mức rủi ro thực.

Trường hợp ngược lại cũng có thể xảy ra. Một nhóm tránh mọi khả năng đặc thù của nhà cung cấp với hy vọng “đổi database bằng một dòng cấu hình”, rồi tự xây lớp trừu tượng hóa quá rộng, không dùng được transaction, query planner hay tính năng backup sẵn có. Ứng dụng trở nên phức tạp, hiệu năng giảm nhưng khi chuyển hệ vẫn phải viết lại mô hình dữ liệu. **Giảm phụ thuộc không có nghĩa phải từ bỏ mọi tính năng chuyên biệt**; cần chọn phụ thuộc có chủ đích, hiểu giá trị mà nó đem lại và kiểm chứng được lối thoát.

Bài học thuộc chương **Đánh giá và lựa chọn**, module **Database No SQL**. Nội dung hướng dẫn nhận diện **vendor lock-in**, chấm điểm rủi ro kỹ thuật, vận hành, bảo mật, pháp lý và thương mại; lập phương án rời nền tảng (*exit strategy*); so sánh các cách di chuyển offline/online; bảo toàn consistency, schema, index, TTL, CDC và quyền truy cập; tính chi phí, tổ chức diễn tập và ra quyết định dựa trên bằng chứng.

> **Nguyên tắc:** Khả năng di chuyển không được chứng minh bằng câu “có thể export JSON/CSV”. Nó phải được chứng minh bằng một lần **khôi phục dữ liệu và tái tạo những đường đọc/ghi quan trọng trên đích**, với tính đúng, bảo mật, khả năng vận hành và RPO/RTO phù hợp.

Tất cả điểm số, bảng chi phí và thời gian trong bài là **ví dụ giả định**. Năng lực, chính sách, tính năng và giá của các hệ NoSQL thay đổi theo phiên bản, nhà cung cấp, khu vực và gói dịch vụ; khi làm dự án thật phải xác minh hợp đồng và tài liệu hiện hành.

## 1. Vendor lock-in là gì?

**Vendor lock-in** là mức độ mà việc thay thế một nhà cung cấp hoặc nền tảng trở nên khó, chậm, đắt, hoặc có rủi ro do ứng dụng, dữ liệu, con người và quy trình đã phụ thuộc vào đặc điểm riêng của hệ đó.

Các phụ thuộc không chỉ nằm ở database engine:
- Cú pháp query và khả năng index.
- Data model, partition key, transaction boundaries.
- Consistency, replication, failover, error semantics.
- SDK/driver, retry behavior, streams.
- Backup/PITR, restore format, encryption keys.
- IAM, network, audit, monitoring và automation.
- Chi phí xuất dữ liệu, băng thông, licensing.
- Năng lực đội ngũ, hỗ trợ và điều khoản thương mại.

Lock-in là **một phổ**, không phải một nhãn “có/không”. Một hệ dễ export data có thể vẫn khó chuyển ứng dụng nếu các query dựa sâu vào tính năng của nhà cung cấp.

## 2. Phân biệt lock-in với việc chọn công nghệ phù hợp

Giả sử hệ nguồn hỗ trợ conditional writes rất tốt. Dùng nó cho idempotency đơn hàng có thể đem lại tính đúng và tiết kiệm công sức.

Không nên tự kết luận “dùng tính năng chuyên biệt = thiết kế tồi”. Câu hỏi đúng là:
1. Tính năng đó tạo giá trị kinh doanh gì?
2. Phần nào của ứng dụng phụ thuộc trực tiếp vào nó?
3. Có biểu diễn được **business invariant** bằng một hợp đồng rõ ràng không?
4. Một hệ đích có thể đáp ứng bằng cơ chế khác không?
5. Chi phí/rủi ro khi chuyển là bao nhiêu?
6. Có bài test chứng minh khả năng thay thế không?

**Phụ thuộc có chủ đích, được đo và có kế hoạch thoát** thường tốt hơn “không phụ thuộc” chỉ trên sơ đồ kiến trúc.

## 3. Các dạng phụ thuộc chính

| Nhóm | Ví dụ | Hệ quả khi rời nền tảng |
|---|---|---|
| Mô hình dữ liệu | Single-table design, document nesting, partition clustering | Thiết kế lại schema và các đường truy cập |
| API/truy vấn | Query language, filters, aggregation, pagination token | Thay code và test semantics |
| Tính nhất quán | Read-after-write, CAS, transaction scope, multi-region conflict | Nguy cơ sai bất biến |
| Vận hành | Managed failover, autoscale, repair, compaction | Phải xây năng lực tương đương |
| Dữ liệu tăng thêm | Stream/CDC/outbox, checkpoint, event ordering | Di chuyển online khó |
| Backup/DR | Proprietary snapshots, PITR, cross-region restore | Restore không trực tiếp ở đích |
| Bảo mật | IAM, KMS, audit, row/tenant authorization | Thiếu quyền hoặc cấp quá rộng |
| Công cụ/hệ sinh thái | SDK, connector, dashboards, deployment pipeline | Thay mã và quy trình |
| Thương mại | Pricing units, egress, support, enterprise license | Chi phí chuyển và chi phí duy trì |
| Con người | Kiến thức vận hành, tài liệu, quy trình on-call | Giảm hiệu quả, tăng rủi ro sự cố |

Một hồ sơ đánh giá tốt đi qua **từng nhóm**, không chỉ đo thời gian export.

## 4. Ba chiến lược tổng quát

1. **Chấp nhận phụ thuộc có kiểm soát:** Dùng tính năng mạnh của nguồn nhưng có owner, risk register, dữ liệu xuất được và kế hoạch dự phòng.
2. **Giảm phụ thuộc chọn lọc:** Cô lập những semantics dễ thay thế qua domain port, event contract, config/IaC, nhưng giữ tính năng quan trọng nếu lợi ích lớn.
3. **Di chuyển hoặc xây khả năng đa nền tảng:** Thực hiện migration tới hệ khác, hoặc hỗ trợ nhiều backend khi nhu cầu thực và chi phí vận hành biện minh được.

Chiến lược thứ ba **không mặc định tốt nhất**. Multi-cloud/dual-database có thể tăng độ phức tạp, chi phí dữ liệu hai nơi và khả năng phân kỳ; việc có hai nhà cung cấp không tự tạo ra portability.

## 5. Lập danh sách phụ thuộc theo luồng nghiệp vụ

Thay vì kiểm “database hỗ trợ CRUD không?”, chọn một flow quan trọng, ví dụ đặt hàng:

~~~text
Client gửi CreateOrder.
API xác thực tenant.
Kiểm idempotency key.
Kiểm tồn kho.
Ghi order có điều kiện.
Phát OrderCreated qua outbox/stream.
Đọc lại order theo ID.
Liệt kê đơn của tenant trong 30 ngày.
Hủy order và cập nhật trạng thái.
Lưu backup, audit và kiểm RPO/RTO.
~~~

Mỗi bước có thể đang gắn với query/index, transaction, IAM, retry hoặc stream riêng. Nếu bỏ sót một bước, migration có thể thành công với dữ liệu mà **thất bại ở nghiệp vụ thật**.

## 6. Phân biệt yêu cầu nghiệp vụ với API nguồn

Ví dụ yêu cầu: “Một checkout chỉ tạo tối đa một đơn hàng”.

Một hệ có thể thực hiện bằng:
- Unique business key + insert có điều kiện.
- Transaction ghi operation ledger.
- Atomic update trên một document/partition.
- Cơ chế khác có điều kiện và idempotent retry.

API nguồn chỉ là **một cách hiện thực hóa bất biến**. Hợp đồng cần ghi:
- Scope của idempotency (tenant, operation, key).
- Payload fingerprint.
- Kết quả khi retry sau response loss.
- Durability đã cam kết.
- Kết quả khi hai requests cạnh tranh.
- Retention của operation identity.

Nếu target có API khác nhưng vẫn giữ đúng bất biến qua tests, đó là **khả năng chuyển đổi semantics** thật.

## 7. Mô hình “sổ đăng ký phụ thuộc”

Một bản ghi:

~~~yaml
dependency:
  id: "order-idempotent-create"
  businessOwner: "checkout-team"
  providerFeature: "conditional-write-and-unique-key"
  criticality: "high"
  affectedPaths:
    - "POST /orders"
    - "checkout-worker"
  expectedSemantics:
    - "at-most-one logical order per checkout"
    - "retry with same key returns same logical result"
  alternative:
    design: "unique index plus operation ledger"
    evidence: "pending-target-integration-test"
  migrationCostClass: "medium"
  failureImpact: "duplicate-order-or-charge"
  mitigation: "idempotency-contract-tests"
~~~

Đây là manifest minh họa. Một dependency nên có **owner, mức quan trọng, vị trí sử dụng, semantics, phương án thay thế và bằng chứng**, không chỉ ghi “dùng API X”.

## 8. Đo mức độ phụ thuộc bằng độ sâu sử dụng

Hai hệ đều dùng cùng một database nhưng rủi ro khác nhau:

**Hệ A**
- Chỉ lưu sessions theo key.
- Có thể tạo lại từ nguồn khác.
- Không có transaction xuyên keys.
- TTL chỉ để dọn cache.

**Hệ B**
- Dùng conditional updates cho thanh toán.
- Dùng nhiều indexes phục vụ API quan trọng.
- Phụ thuộc vào stream ordering.
- Có giao dịch nhiều records.
- Có multi-region writes.

Hệ B chuyển khó hơn vì phải giữ **behavior**, không chỉ giữ các records. Một con số “90% câu lệnh query viết bằng API chung” không mô tả đúng rủi ro của 10% còn lại nếu chúng bảo vệ tiền hoặc quyền truy cập.

## 9. Các tiêu chí phi chức năng không thể bỏ qua

Trước khi chọn đích phải lượng hóa:
- Read/write QPS và peak burst.
- Payload sizes, data growth, hotspot distribution.
- p95/p99 latency theo operation.
- Required availability và failure domains.
- Durability/consistency và transaction invariants.
- RPO/RTO và backup retention.
- Data residency, encryption, compliance.
- Peak recovery/rebuild time.
- Số regions, tenant isolation.
- On-call headcount và mức tự động hóa cần thiết.

Một đích “có CRUD” nhưng không đạt p99 hoặc durability requirement **không phải phương án tương đương**.

## 10. Dependency graph làm lộ các điểm khóa chéo

~~~mermaid
flowchart TD
    APP["Java services"] --> SDK["Provider SDK / query API"]
    APP --> IAM["IAM / service identities"]
    SDK --> DB["NoSQL authoritative data"]
    DB --> INDEX["Index / partition model"]
    DB --> CDC["Streams / CDC"]
    DB --> BK["Backup / PITR"]
    CDC --> SEARCH["Search / analytics / cache"]
    IAM --> KEY["KMS / encryption"]
    KEY --> BK
    DEPLOY["IaC, CI/CD, monitoring"] --> DB
    DEPLOY --> IAM
    DB --> EXIT["Migration / recovery plan"]
    CDC --> EXIT
    BK --> EXIT
    KEY --> EXIT
~~~

Khi đánh giá “có thể rời nhà cung cấp?”, phải hỏi **nếu nhà cung cấp hoặc account nguồn không còn truy cập được thì các đường tới EXIT nào vẫn hoạt động**.

## 11. Phân loại rủi ro: khả năng xảy ra và hậu quả

Một cách đơn giản:

\[
R_i=P_i\times I_i
\]

Trong đó:
- \(P_i\): mức khả năng xảy ra, ví dụ thang 1–5.
- \(I_i\): mức tác động đến nghiệp vụ, ví dụ 1–5.

Nếu muốn bổ sung **khó phát hiện/khó khắc phục**, hãy ghi tiêu chí riêng thay vì nhân số tùy tiện và gọi là xác suất thật.

Ví dụ:

| Rủi ro | P (1–5) | I (1–5) | Điểm | Bằng chứng còn thiếu |
|---|---:|---:|---:|---|
| Chi phí đọc tăng khi đổi workload | 3 | 3 | 9 | Cost simulation theo query mix |
| Không thể restore backup ở vùng DR | 2 | 5 | 10 | Restore drill với KMS role |
| Target thiếu atomicity cho checkout | 3 | 5 | 15 | Concurrency/fault test |
| Connector CDC hết retention giữa migration | 4 | 4 | 16 | Throughput/retention test |
| Vendor ngừng cung cấp tính năng đang dùng | 2 | 4 | 8 | Hợp đồng, lifecycle, thay thế |

**Điểm là công cụ ưu tiên điều tra, không phải xác suất tổn thất đã được đo**. Rủi ro hiếm nhưng làm mất dữ liệu có thể cần ưu tiên hơn điểm trung bình.

## 12. Độ tin cậy của bằng chứng là một cột bắt buộc

Hai dòng đều có điểm 12 nhưng:
- Dòng A đã được kiểm bằng restore drill thực tế.
- Dòng B là nhận định từ slide bán hàng.

Nên ghi:
- Evidence type: test, documentation, contract, estimate.
- Evidence date và version.
- Confidence: high/medium/low.
- Owner xác minh.
- Ngày đánh giá lại.
- Điều kiện làm kết luận mất hiệu lực.

Không dùng bảng chấm điểm trông chính xác để che việc **chưa kiểm năng lực engine/version đích**.

## 13. Chọn hệ đích theo các đường truy cập thật

Ví dụ các query:
1. Get order theo `(tenantId, orderId)`.
2. Liệt kê đơn theo tenant và `createdAt DESC`.
3. Lọc đơn đang chờ theo status và time range.
4. Tìm theo `externalCheckoutId` bảo đảm duy nhất.
5. Ghi conditional update theo `revision`.
6. Xuất dữ liệu cho tenant theo kỳ.

Đối với từng query, mô tả:
- Partition/index path ở nguồn.
- Path/plan dự kiến ở đích.
- Selectivity, hotspot và cardinality.
- Consistency khi đọc.
- QPS, p99, egress và cost.
- Pagination/sort semantics.
- Thời gian tạo và duy trì index.

**Mô hình dữ liệu của NoSQL thường được tối ưu theo truy vấn.** Export nguyên document mà không thiết kế lại indexes/partitions chưa phải migration xong.

## 14. Query portability thường là phần tốn kém nhất

Các khác biệt có thể nằm ở:
- Query bằng khóa/partition vs filters tùy ý.
- Aggregation pipelines, joins, graph traversal.
- Index dạng compound, GSI/LSI, secondary indexes.
- Sort order và collation.
- Pagination offset, cursor hoặc opaque token.
- Null/missing field semantics.
- Full-text/search/geospatial features.
- Transaction/read semantics.

Đừng coi hai cú pháp `getById` giống nhau là mọi query có thể map 1:1. Một API đích có thể **vẫn trả kết quả đúng nhưng yêu cầu full scan**, khiến latency và chi phí tăng ngoài mức cho phép.

## 15. Data model có thể cần chuyển đổi cấu trúc

Ví dụ source tối ưu theo access pattern:

~~~json
{
  "pk": "TENANT#t7",
  "sk": "ORDER#o101",
  "entityType": "ORDER",
  "status": "PAID",
  "createdAt": "2026-11-14T10:00:00Z"
}
~~~

Target document model:

~~~json
{
  "_id": "t7:o101",
  "tenantId": "t7",
  "orderId": "o101",
  "status": "PAID",
  "createdAt": "2026-11-14T10:00:00Z",
  "schemaVersion": 2,
  "revision": 12
}
~~~

Không chỉ đổi tên `pk` thành `_id`. Phải thiết kế lại:
- Uniqueness và tenant scope.
- Index theo tenant/time.
- Query theo externalCheckoutId.
- TTL/retention.
- Version/conditional updates.
- Transaction grouping.
- Event/outbox schema.

**Data portability là semantic transformation**, không đơn giản là đổi định dạng JSON.

## 16. Không gán nhãn “schema-less” cho một hợp đồng không định hình

Hệ document có thể linh hoạt, nhưng business contract vẫn quy định:
- Field names/types.
- Required/optional/null.
- Versioning.
- Precision của money/time.
- Array/nested structure.
- Indexes và uniqueness.
- Validator và authorization.
- TTL, delete semantics.

Khi sang engine khác, cần kiểm **schema validation ở đâu được thực thi**: database, application hay cả hai. Nếu nguồn có constraint mà đích chỉ dựa vào convention, phải xây guard ở một ranh giới phù hợp và chứng minh bằng integration tests.

## 17. Numeric, timestamp và null là điểm lỗi phổ biến

Một hệ có số dạng BSON Int64/Decimal128, hệ khác có Number/attribute types; Java serializers có thể âm thầm ép kiểu.

Cần test:
- Tiền ở integer minor units hoặc decimal đã định nghĩa.
- Integer overflow và precision.
- Timezone và timestamp precision.
- Missing vs null vs empty.
- Enum/value unknown.
- Unicode normalization và collation.
- Binary payload/attachment encoding.
- TTL expiration timestamp.
- Negative zero hoặc floating-point NaN nếu input có thể chứa.

Một migration có record counts bằng nhau nhưng làm tròn sai giá tiền vẫn **không đạt tính đúng**.

## 18. Consistency contract phải được viết bằng tình huống

Không chỉ ghi “source strong, target eventual”. Hãy định nghĩa:

~~~text
Sau khi POST /orders trả success:
  GET /orders/{id} trong cùng session phải nhìn thấy order.

Sau conditional update revision 7 -> 8:
  không writer nào được commit tiếp dựa trên revision 7.

Sau DELETE tài khoản được xác nhận:
  không read path nào được tái tạo dữ liệu cũ trái policy.
~~~

Hệ nguồn và đích có thể cung cấp những điều này qua API khác nhau, read/write concern hoặc architecture khác. **Phải test các lịch sử thao tác thực**, nhất là failover, retry và reads từ replicas.

## 19. Transactions và nguyên tử khác nhau giữa NoSQL

Một số sản phẩm hỗ trợ multi-document/item transactions trong điều kiện nhất định; những hệ khác tập trung vào atomicity per key/partition và cần saga/outbox cho nhiều bước.

Khi đánh giá:
- Atomic scope thực sự?
- Isolation level và anomaly được phép?
- Conflict detection/retry?
- Transaction size/duration limits?
- Cross-region transaction semantics?
- Điều gì xảy ra khi commit response mất?
- Chi phí và latency dưới tải?

Nếu nguồn cho phép một checkout transaction toàn cụm mà đích chỉ atomic một partition, có thể phải **đổi phân nhóm dữ liệu hoặc workflow**, không chỉ đổi driver.

## 20. Conditional write là một contract, không phải cú pháp

Ví dụ:

~~~text
CREATE order only if operationId does not exist.
UPDATE order only if revision == expectedRevision.
DELETE only if owner/tenant matches trusted identity.
```

Khi chuyển từ hệ nguồn sang đích:
- Xem atomic condition được đánh giá ở đâu.
- Có uniqueness bảo vệ đồng thời không?
- Có cách phân biệt conflict với timeout không?
- Retry same operationId có idempotent không?
- Có lưu result sau commit không?
- Có nguy cơ duplicate khi client reconnect?

Đây là một trong những nhóm tests cần chạy **trước khi copy data**, vì sai có thể ảnh hưởng tiền, tồn kho và quyền truy cập.

## 21. Đánh giá migration theo trạng thái và events

Dữ liệu tại một thời điểm chỉ là **state**. Trong môi trường đang ghi, di chuyển đúng còn cần **change history**.

Các nguồn thường được cân nhắc:
- Database-native CDC/change stream.
- Transactional outbox ở application/source.
- Transaction log/managed replication tool được hỗ trợ.
- Domain event log có đủ coverage.
- Snapshot + reconciliation nếu không có stream đầy đủ.

Không coi log ứng dụng, Redis keyspace notifications hay một stream bị giới hạn retention như **bằng chứng mặc định của mọi writes**. Cần xác minh semantics từng nền tảng, xóa/TTL, ordering, replay và checkpoint.

## 22. Snapshot và CDC phải nối được qua một mốc

~~~mermaid
flowchart LR
    CLIENT["Application writes"] --> S["Source authoritative"]
    S --> SNAP["Consistent snapshot at L0"]
    S --> CDC["Capture changes after L0"]
    SNAP --> APPLY["Transform + backfill"]
    CDC --> IDEMP["Idempotent incremental apply"]
    APPLY --> T["Target"]
    IDEMP --> T
    T --> VERIFY["Compare at common watermark"]
    S --> GATE["Final write barrier Lc"]
    GATE --> VERIFY
    VERIFY --> CUT{"GO cutover?"}
    CUT -->|"Yes"| ROUTE["Fence old writer / route to target"]
    CUT -->|"No"| FIX["Repair or NO-GO"]
~~~

`L0` và `Lc` là **mốc có hợp đồng với nguồn**, không nhất thiết là timestamp hoặc số đếm. Một resume token opaque không được tự xem là version có thể so sánh trên mọi shards.

## 23. Lỗi khi bắt CDC quá muộn

~~~text
10:00 Snapshot bắt đầu.
10:03 Order A đổi sang PAID.
11:00 Backfill hoàn tất.
11:01 Mới bật CDC.
```

Thay đổi 10:03 có thể không được đưa sang target nếu snapshot/backfill đã đọc A trước đó.

Hướng phù hợp:
- Snapshot nhất quán gắn với log position khi engine/tool hỗ trợ.
- Bắt capture đủ sớm rồi backfill có version-aware apply.
- Hoặc write gate ngắn cùng reconciliation có thể chứng minh.

**Hai thời điểm wall-clock gần nhau không tự tạo mốc không mất event.**

## 24. Race snapshot và CDC

~~~text
T0: Backfill đọc order v5.
T1: Source cập nhật order -> v6.
T2: CDC apply v6 vào target.
T3: Backfill UPSERT v5 ghi đè v6.
```

Nếu dùng overwrite vô điều kiện, đích tụt lại.

Một hợp đồng apply:

~~~text
If incoming.sourceVersion > target.sourceVersion:
    conditional upsert incoming.
Else:
    ignore as stale/duplicate.
```

Phải thực hiện điều kiện **atomic theo key/aggregate**. Read trước rồi write không có guard có thể tạo race ở target. Nếu nguồn không có per-key version đáng tin, ưu tiên protocol đồng bộ tuần tự hoặc checkpoint/lock phù hợp.

## 25. DELETE bị hồi sinh là lỗi nghiêm trọng

~~~text
Backfill đọc document có tồn tại.
Source DELETE.
CDC DELETE áp dụng ở target.
Backfill UPSERT document cũ sau DELETE.
```

Một **tombstone có source delete version** hoặc cơ chế stream-then-snapshot ordering giúp từ chối bản cũ.

Cần phân biệt:
- Hard delete.
- Soft delete.
- TTL expiration.
- Purge theo quyền riêng tư.
- Background compaction.
- Dữ liệu được tạo lại hợp lệ với generation mới.

Không xóa tombstone quá sớm nếu backfill/old client vẫn có khả năng tái tạo bản ghi. Đối với yêu cầu xóa dữ liệu cá nhân, migration không được làm sống lại dữ liệu đã được xóa hợp lệ.

## 26. TTL không nên bị reset khi copy

Ví dụ:
~~~text
Cache/session record hết hạn lúc 12:00.
Được copy sang target lúc 11:30.
Target đặt TTL 2 giờ từ lúc copy.
```

Record sống đến 13:30 thay vì 12:00. Nếu TTL liên quan session security hoặc retention pháp lý, hành vi sai nghiêm trọng.

Nên truyền **absolute expiresAt hoặc remaining TTL dựa trên nguồn đáng tin** theo semantics của target; kiểm clock skew và trường hợp record đã hết hạn. Không giả định mọi engine phát event TTL giống user DELETE.

## 27. At-least-once và idempotent apply

Một CDC relay có thể:
1. Đọc event.
2. Ghi target thành công.
3. Crash trước checkpoint.
4. Khởi động lại và áp dụng lại event.

Các phép `SET status` cùng version có thể an toàn hơn `INCREMENT balance`, nhưng còn side effects downstream.

Cần:
- Stable event ID.
- Dedup/inbox hoặc versioned upsert.
- Checkpoint chỉ sau effect đã được ghi bền.
- Retry bounded và dead-letter/reconciliation.
- Per-key ordering khi cần.
- Không tự hứa exactly-once xuyên hai stores.

## 28. Data volume và backlog làm lộ rủi ro về thời gian

Gọi:
- \(D\): bytes dữ liệu cần backfill.
- \(b\): throughput copy hữu ích bytes/s.
- \(\lambda\): events mới/s.
- \(\mu\): events áp dụng được/s.

Ước tính thô:

\[
T_{\text{backfill}}\approx D/b
\]

Nếu \(\lambda>\mu\), backlog tăng xấp xỉ \((\lambda-\mu)t\), chưa tính bytes/event và burst.

Ví dụ giả định:
- Data 12 TB.
- Throughput hữu ích 100 MB/s.
- 24h có hơn 86.000 giây.

Thời gian copy lý tưởng có thể vượt một ngày; còn indexes, throttling, retries, kiểm parity và cutover. Nếu CDC source chỉ giữ thay đổi trong thời gian ngắn hơn, phương án phải được thiết kế lại, **không đơn giản chạy nhanh hơn theo cảm tính**.

## 29. RPO/RTO của migration khác mục tiêu copy

**RPO**: dữ liệu được phép mất theo recovery/cutover contract.

**RTO**: thời gian nghiệp vụ phải phục hồi tới mức dịch vụ đã định.

Trong live migration còn cần:
- Write-gate duration.
- Time to CDC catch-up.
- Time to index rebuild.
- Time to safe route switch.
- Time to restore SLO.
- Time to rollback/rollforward.
- Acceptable read staleness.
- Maximum projection lag.

“Copy 100% bytes” không phản ánh **RPO/RTO hoặc mức đúng của writes mới**.

## 30. Mô hình chi phí thực của việc rời nhà cung cấp

Một ước tính:

\[
C_{\text{exit}} =
C_{\text{export}} +
C_{\text{network}} +
C_{\text{target-build}} +
C_{\text{dual-run}} +
C_{\text{engineering}} +
C_{\text{verification}} +
C_{\text{risk}} +
C_{\text{retirement}}
\]

Trong đó:
- Export/egress có thể tính phí theo loại storage, vùng và dịch vụ.
- Target ingestion tạo read/write IOPS, index build và storage.
- Dual-run duy trì cả source lẫn target.
- Engineering gồm đổi query/schema/SDK.
- Verification gồm test correctness và performance.
- Risk bao gồm quỹ dự phòng/expected incident impact được ước tính riêng.
- Retirement gồm xóa staging, thu hồi keys/permissions và retention.

Không gọi công thức này là báo giá. Đơn vị giá, quota, mức phí và điều khoản phải được lấy từ nguồn chính thức/contract tại thời điểm quyết định.

## 31. Bài toán egress và data gravity

Data gravity mô tả chi phí và khó khăn khi dữ liệu lớn kéo theo các hệ phụ trợ:
- Search, analytics, fraud detection.
- CDC consumers.
- Object storage backups.
- Streaming/broker.
- BI/ETL pipelines.
- Regional services cần latency thấp.

Chuyển database có thể khiến một phần query đi qua vùng/cloud khác, làm tăng:
- Network latency.
- Egress.
- Cross-region transfer.
- Operational blast radius.
- Data residency risk.

**Đếm bytes trong bảng chính là quá ít**: cần kiểm toàn bộ dữ liệu dẫn xuất, retention, backups và đồng bộ liên tục.

## 32. TCO, chứ không chỉ giá mỗi request

**Total Cost of Ownership (TCO)** nên xét:
- Compute/storage/IOPS/read-write units.
- Provisioned capacity hoặc autoscale.
- Backup/PITR, snapshots, replicas.
- Streaming và egress.
- Logging/monitoring/alerting.
- Support/license.
- Nhân sự vận hành/incident response.
- Sự cố, downtime, migration/DR drills.
- Chi phí mở rộng và các rủi ro bị khóa.

Một engine self-managed có phí phần mềm thấp nhưng cần DBA/on-call, patching, repair và disaster recovery. Một managed service có chi phí sử dụng cao hơn nhưng chuyển một phần gánh nặng vận hành sang nhà cung cấp. So sánh phải **cùng yêu cầu SLA/SLO và mức bảo vệ dữ liệu**.

## 33. Bảng kịch bản chi phí minh họa

| Kịch bản giả định | Source monthly | Target monthly | Di chuyển một lần | Rủi ro cần xác minh |
|---|---:|---:|---:|---|
| Giữ nguồn và tối ưu | 100 đơn vị | — | 8 đơn vị | Scaling/pricing tương lai |
| Chuyển toàn bộ | 100 trước cutover | 75 sau cutover | 320 đơn vị | Semantics và thời gian thu hồi |
| Hybrid lâu dài | 70 | 55 | 180 đơn vị | Đồng bộ, quản trị hai hệ |

Các số là **đơn vị giả định**, không phải USD hay bảng giá của dịch vụ nào. Với phương án chuyển toàn bộ, tiết kiệm tháng sau cutover là \(100-75=25\) đơn vị/tháng; thời gian hoàn vốn đơn giản \(320/25=12{,}8\) tháng, **chưa tính chi phí song song, downtime, rủi ro và thay đổi tải**.

Không chọn target chỉ vì mô hình đơn giản cho thấy hoàn vốn nhanh nếu chưa chứng minh bảo toàn bất biến nghiệp vụ.

## 34. Chi phí cơ hội của việc tránh mọi lock-in

Một nhóm tự triển khai:
- Scheduler failover.
- Replication.
- Backup và PITR.
- Encryption key rotation.
- Auto scaling.
- Audit.
- Global routing.

để không lệ thuộc nhà cung cấp managed.

Nó có thể tạo **lock-in vào chính bộ công cụ tự viết** cùng gánh nặng bảo trì lớn hơn. Đánh giá phải ghi:
- Khả năng đội ngũ thực hiện/duy trì.
- On-call và đào tạo.
- Recovery drills.
- Tổng chi phí kỹ thuật.
- Bảo mật và tình trạng hỗ trợ.

Mục tiêu là **tối ưu lựa chọn trong dài hạn**, không tối đa hóa số phần phải tự xây.

## 35. Phụ thuộc thương mại và pháp lý

Những câu hỏi cần kiểm trong tài liệu/hợp đồng:
- Quyền sở hữu và quyền export dữ liệu.
- Định dạng export, công cụ và mức hỗ trợ.
- Data residency và quy định vùng lưu trữ.
- SLA, service credits, ngoại lệ và support escalation.
- Termination notice, renewal, thay giá.
- Chính sách chấm dứt dịch vụ/tính năng và thông báo.
- License nếu chạy self-managed hoặc dùng fork.
- Nghĩa vụ xóa, giữ chứng cứ và xác nhận xóa.
- Audit/compliance documents theo ngành/khu vực.
- Khả năng chuyển backup/keys sang boundary khác.

Không giả định **open-source license** đồng nghĩa không có ràng buộc hỗ trợ, công nghệ, quyền dùng dịch vụ managed hay nghĩa vụ về dữ liệu. Với yêu cầu pháp lý cụ thể, phải có đánh giá của bộ phận có thẩm quyền.

## 36. Kế hoạch exit cần được lập trước khủng hoảng

Nếu chỉ bắt đầu tìm cách export khi:
- Giá tăng đột ngột.
- Dịch vụ đổi license.
- Khu vực bị gián đoạn.
- Hợp đồng hết hạn.
- Một tính năng bị ngừng.

thì công ty có thể thiếu thời gian thử đúng. Một exit strategy hợp lý chứa:
1. Inventory data và các workload quan trọng.
2. Ràng buộc contract/provider.
3. Dữ liệu có thể xuất và cách kiểm integrity.
4. Mapping schema/index/query/invariants.
5. Đích tiềm năng và giới hạn.
6. Thời gian/chí phí/nguồn lực.
7. Phương án di chuyển và rollback.
8. Trigger/khi nào phải bắt đầu.
9. Owner, approval, drills và cadence review.

**Exit plan là tài liệu vận hành sống**, không phải một ghi chú “sẽ dùng tool migrate nếu cần”.

## 37. Dự phòng khi vendor/source không còn truy cập được

Một phương án chỉ dựa vào API nguồn đang hoạt động có thể thất bại khi vùng nguồn mất hoàn toàn hoặc tài khoản bị khóa.

Cần cân nhắc:
- Independent backup copies và catalog.
- Khả năng decrypt bằng recovery principal.
- Schema/index/IaC revisions.
- Driver/backup tool phù hợp còn lấy được.
- Snapshot/archived log continuity.
- Phân quyền cross-account/region.
- Runbook dựng môi trường độc lập.
- Giới hạn của recovery từ bản sao offline: có thể chỉ đạt RPO theo lịch backup.

**Live migration và disaster recovery là hai kế hoạch khác nhau**. Nếu source đã mất, không thể kỳ vọng CDC stream tiếp tục cho đến cutover.

## 38. Export data phải có manifest

Một manifest minh họa:

~~~yaml
export:
  id: "orders-exit-2026-11"
  sourceEngine: "documented-source"
  sourceVersion: "recorded-version"
  sourceScope:
    collections: ["orders", "order-operations"]
  consistencyPoint: "source-supported-snapshot-ref"
  dataFormat: "canonical-json-lines-v2"
  files:
    - name: "orders-part-001"
      bytes: 148000000
      checksum: "sha256-opaque-digest"
  schemaRevision: "git-revision"
  indexRevision: "indexes-v9"
  transformRevision: "transform-commit"
  encryption:
    mode: "approved-transport-and-at-rest"
    keyReference: "kms-key-id"
  access:
    exportPrincipal: "approved-migration-role"
  checkpointReference: "source-stream-position-if-supported"
~~~

Không chứa raw secrets hoặc customer PII trong manifest. Một `consistencyPoint` phải dựa trên cơ chế source thực sự hỗ trợ; không gắn tùy ý timestamp rồi gọi snapshot nhất quán.

## 39. Backup độc quyền và logical portability

Một engine-native snapshot có thể rất hiệu quả để restore **cùng engine/version phù hợp**, nhưng không đọc trực tiếp bởi engine khác. Logical export (JSONL, Avro, Parquet hoặc format có schema/codec đã chọn) có thể dễ chuyển hơn, song:
- Có thể mất type/precision nếu encode thiếu cẩn thận.
- Không tự chứa indexes, validators, roles.
- Có thể không có atomic consistent point trên toàn cluster.
- Cần xử lý binary/large objects.
- Có chi phí scan/transform.
- Có thể không phản ánh mọi CDC changes.

Kế hoạch tốt đôi khi cần **cả backup-native cho DR lẫn logical export path cho exit**.

## 40. Khóa mã hóa và quyền restore là ràng buộc thực

Một backup được copy qua nhà cung cấp mới nhưng vẫn phụ thuộc key KMS cũ:
- Key ID có còn tồn tại?
- Recovery principal có thể decrypt không?
- Có thể re-encrypt/rewrap sang boundary mới không?
- KMS policy và network cho phép?
- Key rotation có giữ khả năng giải mã backup cũ?
- Có thể khôi phục khi region/account nguồn không sẵn sàng?

**Có encrypted bytes không chứng minh có khả năng export dữ liệu hữu ích.** Không bao giờ giải quyết bằng cách đưa raw private key/token vào script hoặc tài liệu migration.

## 41. Chuyển quyền, không chỉ chuyển dữ liệu

Những thành phần cần đối chiếu:
- User/service identities.
- DB roles, ACL, resource policies.
- Tenant authorization boundaries.
- Backup/restore and KMS permissions.
- TLS/mTLS trust.
- Network policies.
- Audit retention và access.
- Privileged admin/break-glass access.
- Data classification/retention rules.

Một hệ đích mà tất cả services đều được cấp admin để “chạy cho được” là **migration thất bại về bảo mật**, dù dữ liệu đầy đủ. Phải test cả access được phép và access bị từ chối.

## 42. Quản lý schema/index trong lúc chuyển

Trước khi nạp dữ liệu:
- Tạo hoặc lập lịch tạo indexes theo chiến lược đã đo.
- Xác định uniqueness/collation/partial index semantics.
- Định nghĩa validators/schema contracts.
- Xử lý legacy versions.
- Bảo vệ tenant uniqueness.
- Lập kế hoạch build/index backfill không làm quá tải target.
- Xác định trạng thái nào chặn cutover.

Một unique index có thể không xây được nếu source có duplicates mà engine nguồn cho phép theo scope khác; phải **làm sạch bằng quy trình nghiệp vụ**, không âm thầm bỏ constraint.

## 43. Migration offline: khi nào phù hợp?

Một kế hoạch offline:

~~~text
Preflight + backup.
Stop/quiesce all writers.
Take consistent snapshot.
Export/transform/import.
Rebuild indexes/permissions.
Validate.
Switch reads/writes.
Resume traffic.
```

Phù hợp khi:
- Dữ liệu không quá lớn.
- Có maintenance window được chấp nhận.
- RPO/RTO và downtime phù hợp.
- Không có writes từ nguồn khác/batch jobs.
- Đích có thể dựng nhanh.
- Rủi ro vận hành online CDC lớn hơn rủi ro downtime.

Ưu điểm: giao thức cutover đơn giản hơn. Nhược: downtime có thể tăng theo data size, index build và validation. Không gọi offline là “không chuyên nghiệp” nếu nó đáp ứng business goals và có khả năng kiểm chứng tốt hơn.

## 44. Migration online: snapshot cộng CDC

~~~text
S authoritative và tiếp tục nhận writes.
Bắt capture ở mốc L0 đáng tin.
Backfill snapshot có kiểm soát.
Apply incremental changes (idempotent).
Reconcile cùng watermark.
Write gate / drain in-flight.
Apply tới barrier Lc.
Verify và switch authority sang T.
```

Phù hợp khi downtime dài không được chấp nhận. Nhưng tăng chi phí:
- Duy trì hai clusters.
- Backfill/CDC pipeline.
- Thời hạn lưu source logs.
- Chống duplicate/out-of-order/delete resurrection.
- So parity và incident runbooks.
- Source write fencing lúc cutover.

**Online không tự đồng nghĩa rủi ro nhỏ hơn**; nó chuyển một phần downtime thành độ phức tạp đồng bộ.

## 45. Dual-write là lựa chọn có điều kiện

Một application ghi cả source S lẫn target T:

| S | T | Vấn đề |
|---|---|---|
| Success | Success | Có thể cùng state ở operation đó |
| Success | Fail | Đích thiếu event |
| Fail | Success | Đích có effect nguồn từ chối |
| Timeout | Success | Source outcome UNKNOWN |
| Success | Timeout | Target outcome UNKNOWN |

Hai commits độc lập không atomic chỉ nhờ `Promise.all` hoặc Java futures. Nếu S vẫn authoritative, một hướng thường an toàn hơn là ghi **business state + transactional outbox ở S** trong atomic boundary được hỗ trợ, rồi relay có retries và idempotency sang T.

Dual-write thực sự chỉ nên chọn khi:
- Có failure matrix và protocol reconcile.
- Biết nguồn có thẩm quyền theo từng key.
- Có dedup/version policy.
- Tính đúng cross-store đã được test.
- Có rollback/rollforward plan.

## 46. Anti-corruption layer giảm phụ thuộc có chọn lọc

Một domain port:

~~~java
interface OrderStore {
    OrderView get(String tenantId, String orderId);

    CreateResult createIfAbsent(
        VerifiedTenant tenant,
        String operationId,
        OrderDraft draft
    );

    UpdateResult updateIfRevision(
        VerifiedTenant tenant,
        String orderId,
        long expectedRevision,
        OrderPatch patch
    );

    Page<OrderView> listByCreatedAt(
        VerifiedTenant tenant,
        Instant from,
        Instant to,
        PageCursor cursor
    );
}
~~~

Đây là **hợp đồng minh họa**, không phải API Java đầy đủ. Những điều còn phải định nghĩa:
- Consistency và durability từng method.
- Error/outcome UNKNOWN.
- Pagination cursor scope/expiry.
- Transaction isolation.
- Idempotency retention.
- Max page size.
- Khi backend không hỗ trợ cùng semantics thì báo lỗi như thế nào.

Không tạo `GenericRepository<T>` chỉ có `save/findAll` rồi giả định mọi NoSQL hoạt động giống nhau. **Domain-specific ports tốt hơn abstraction che giấu điều kiện đúng quan trọng.**

## 47. Tách lỗi nghiệp vụ khỏi lỗi nhà cung cấp

Một domain service nên phân biệt:
- `AlreadyExists` / `IdempotencyConflict`.
- `RevisionMismatch`.
- `NotAuthorized`.
- `ValidationRejected`.
- `RateLimited`.
- `TransientUnavailable`.
- `OutcomeUnknown`.

Adapter ánh xạ từ error/exception nguồn sang contract đã định nghĩa. Nhưng:
- Không biến mọi timeout thành rollback.
- Không coi mọi conditional failure là replay.
- Không retry validation errors vô hạn.
- Không bỏ event/retry key khi đổi backend.

Lỗi **UNKNOWN** phải được giữ nếu chưa biết commit outcome, vì đổi nhà cung cấp không làm biến mất tính bất định của hệ phân tán.

## 48. Kiểm chứng lựa chọn bằng proof of concept

Một PoC có ý nghĩa cần chạy **các business operations thật**, không chỉ CRUD tutorial:
1. Data model và indexes theo query inventory.
2. Ứng dụng Java gọi adapter đích.
3. Idempotent create và conditional update.
4. Read-after-write/consistency test.
5. Mixed-version schema và legacy documents.
6. Bulk import/backfill/CDC replay.
7. DELETE/TTL, retry/timeout/failover.
8. Tenant authorization và KMS/access.
9. Backup/restore to independent environment.
10. Performance/cost theo workload gần production.

Nếu PoC chỉ import 10.000 records rồi đo `GET by ID`, nó chưa kiểm năng lực thay thế.

## 49. Matrix khả năng: ví dụ các hệ NoSQL

| Hệ | Điểm cần đánh giá khi chuyển | Không được tự giả định |
|---|---|---|
| **MongoDB** | Document/BSON, indexes/validators, aggregation, write/read concern, transactions, Change Streams | Mọi deployment có cùng khả năng backup/audit/CDC |
| **DynamoDB** | Partition/sort key design, secondary indexes, conditional writes/transactions, Streams, IAM/PITR | Scan đang ghi là consistent snapshot toàn bảng; IAM đi theo dữ liệu export |
| **Cassandra** | Partition/clustering model, keyspace RF, consistency level, LWT, tombstones/TTL, CDC tooling | Có joins/ad-hoc query hoặc single global ordered change log |
| **Redis** | Key types, TTL, scripts/transactions, Cluster slots, persistence, memory/eviction | Keyspace notifications là durable change log; key-value cache là authoritative store |
| **CouchDB** | Document revisions, conflicts, replication, design docs, `_changes`, delete/purge | Revision ID và `_changes` sequence tự tương đương global business version |

Khả năng còn tùy **phiên bản, cấu hình, edition, dịch vụ managed và trường hợp sử dụng**. Bảng dùng để đặt câu hỏi, không thay kiểm thử nhà cung cấp.

## 50. Ví dụ: chuyển DynamoDB-style model sang MongoDB

Source có:
~~~text
PK = TENANT#t7
SK = ORDER#o101
GSI1: trạng thái và thời gian.
Conditional Put/Update.
Streams cho projection.
```

Target dự kiến:
~~~javascript
db.orders.createIndex(
  { tenantId: 1, orderId: 1 },
  { unique: true, name: "tenant_order_unique" }
);

db.orders.createIndex(
  { tenantId: 1, createdAt: -1 },
  { name: "tenant_created_at" }
);

db.orders.createIndex(
  { tenantId: 1, lifecycle: 1, createdAt: -1 },
  { name: "tenant_status_created_at" }
);
~~~

Đây là **ví dụ thiết kế**, chưa kiểm cardinality, index selectivity, sharding unique-index constraints hay workload thực. Cần quyết định:
- Map PK/SK thành IDs như thế nào?
- Hành vi pagination từ GSI được biểu diễn ra sao?
- Conditional writes chuyển thành filter/version guard thế nào?
- Streams thay bằng Change Streams/outbox ra sao?
- TTL và transaction semantics có giữ được không?
- IAM của dịch vụ cũ map sang authz ứng dụng/DB roles thế nào?

Một phép import JSON không giải quyết những câu hỏi này.

## 51. Ví dụ: chuyển document sang Cassandra

Một collection cho phép:
~~~text
Find orders by any combination of tenant, status, amount, time.
```

Chuyển sang wide-column cần xác định **những query cụ thể sẽ phục vụ**. Có thể phải tạo:
~~~text
orders_by_tenant_and_day
orders_by_tenant_and_status
orders_by_id
```

Những bảng này denormalize dữ liệu và cần workflow cập nhật nhất quán. Hậu quả:
- Một business write thành nhiều physical writes.
- Repair/reconciliation phức tạp hơn.
- Atomicity qua partitions có giới hạn khác.
- TTL/tombstone phải được đánh giá kỹ.
- Index và query planner khác.
- Read path và cost mô hình lại.

**Không chuyển một collection vào một table Cassandra rồi mong giữ mọi phép lọc tùy ý như nguồn.**

## 52. Ví dụ: chuyển Redis thành cache khác hoặc authoritative store

Nếu Redis là cache-aside:
- State có thể tái tạo từ nguồn có thẩm quyền.
- Cần bảo vệ key namespace, TTL, serialization và cache invalidation.
- Có thể chọn cold cutover/prewarm có giới hạn.
- Đo cache miss storm.

Nếu Redis giữ session/counter/queue duy nhất:
- Không thể mặc định bỏ keys.
- Cần RPO/RTO và persistence/replication.
- `INCR`, queue ordering, scripts và transaction semantics cần thay thế đúng.
- Failover/duplicate reply có thể làm sai counts.
- Phải test idempotency và delivery.

**Cùng một công nghệ có rủi ro exit khác nhau tùy vai trò nguồn dữ liệu.**

## 53. Open-source engine không tự bảo đảm không lock-in

Một hệ tự quản lý có thể ràng buộc:
- Storage format và version upgrade path.
- Repair/compaction tools.
- Driver protocol/extension.
- Third-party plugins.
- Operating expertise.
- Monitoring and backup stack.
- Support/patch cadence.
- Licensing cho những extension đang dùng.

Đánh giá phải xét **khả năng duy trì, nâng cấp, thay đội ngũ và restore**, không chỉ khả năng tải source code. Vendor lock-in có thể được thay bằng **operational lock-in**.

## 54. Multi-cloud không phải phép màu loại bỏ rủi ro

Chạy active-active hai dịch vụ khác nhau có thể phát sinh:
- Conflict resolution khác nhau.
- Cross-region latency.
- Cần distributed coordination.
- Duplicate writes/events.
- Divergent schema/indices.
- Chi phí egress lâu dài.
- Mất một cloud làm app không đạt consistency.
- Security/IAM và incident response nhân đôi.

Một chiến lược ít phức tạp hơn có thể là **một source authoritative + independent backup/restore drill + tested exit adapter**, nếu đáp ứng RPO/RTO và yêu cầu kinh doanh.

## 55. Đường thoát theo từng lớp, không nhất thiết di chuyển ngay

Một tổ chức có thể chia:
1. **Data portability:** export canonical data, schema và key references.
2. **Application portability:** domain-specific contracts, adapters, tests.
3. **Operational portability:** IaC, observability, backup/restore runbook.
4. **Security portability:** roles, tenant authz, KMS/TLS policy mapping.
5. **Migration readiness:** PoC, CDC strategy, cost/quorum gates.
6. **Commercial readiness:** terms, notice periods, budget/capacity.

Chọn lớp nào đầu tư trước theo risk register. Không phải lúc nào cũng cần duy trì live replication sang nhà cung cấp thứ hai.

## 56. Quy trình lựa chọn có trọng số

Ví dụ chấm **lợi ích/khả năng đáp ứng**, thang 1–5 (5 tốt nhất):

| Tiêu chí | Trọng số | Phương án A | Phương án B |
|---|---:|---:|---:|
| Đáp ứng bất biến nghiệp vụ | 30% | 5 | 4 |
| Khả năng exit/portability | 20% | 2 | 4 |
| Vận hành/SLO | 15% | 5 | 3 |
| TCO dự kiến | 15% | 3 | 4 |
| Security/compliance | 10% | 5 | 4 |
| Năng lực đội và hệ sinh thái | 10% | 4 | 3 |
| **Tổng có trọng số** | **100%** | **4,00** | **3,75** |

Cách tính A:
\[
0{,}30(5)+0{,}20(2)+0{,}15(5)+0{,}15(3)+0{,}10(5)+0{,}10(4)=4{,}00
\]

Cách tính B:
\[
0{,}30(4)+0{,}20(4)+0{,}15(3)+0{,}15(4)+0{,}10(4)+0{,}10(3)=3{,}75
\]

Ví dụ A có tổng cao hơn dù portability thấp hơn. Nhưng **điểm tổng không được vượt qua điều kiện bắt buộc**: nếu B không đáp ứng bất biến thanh toán, B phải bị loại cho workload đó dù điểm các mục khác cao.

## 57. Phân tích độ nhạy trước khi chốt lựa chọn

Trọng số 20% cho portability là một quyết định kinh doanh, không phải hằng số kỹ thuật. Hãy thử:
- Nếu egress giá cao gấp đôi?
- Nếu data growth 3×?
- Nếu support team giảm một nửa?
- Nếu latency SLO chặt hơn?
- Nếu region thứ hai bắt buộc?
- Nếu pháp lý yêu cầu data residency mới?
- Nếu vendor ngừng một tính năng?

Nếu phương án thắng chỉ dưới một bộ giả định rất hẹp, hãy ghi **độ nhạy và trigger đánh giá lại**, không tô nó thành quyết định chắc chắn mãi mãi.

## 58. Gate quyết định migration

~~~mermaid
flowchart TD
    A["Đánh giá lock-in và trigger"] --> B["Inventory semantics / cost / contract"]
    B --> C{"Có phương án đích đáp ứng hard requirements?"}
    C -->|"Không"| ALT["Optimize source / giảm phụ thuộc / nghiên cứu thêm"]
    C -->|"Có"| POC["Proof of concept + compatibility tests"]
    POC --> D{"Correctness/security/performance đạt?"}
    D -->|"Không"| ALT
    D -->|"Có"| PLAN["Backup + migration + rollback plan"]
    PLAN --> E{"Rehearsal và RPO/RTO đạt?"}
    E -->|"Không"| ALT
    E -->|"Có"| GO["Controlled rollout / cutover"]
    GO --> POST["Monitor + reconcile + retire source"]
~~~

Một NO-GO có bằng chứng là **kết quả tốt của đánh giá**, không phải thất bại quản lý dự án. Nó ngăn việc chuyển trên một assumption chưa chứng minh.

## 59. Canary và shadow-read

Trước cutover:
- Ứng dụng tiếp tục trả response từ source.
- Shadow-read target cho một phần truy vấn an toàn.
- So business values với source tại cùng version/watermark khi có thể.
- Theo dõi mismatch, p99, query plans và security.
- Không để shadow requests tạo side effects.
- Tránh ghi raw PII vào diff logs.

Nếu đọc source ở thời điểm \(t_1\), target ở \(t_2\) khi đang nhận CDC, mismatch có thể là **độ trễ hợp lệ**, không phải corruption. Cần phân loại theo nguồn version và window.

Canary **write** rủi ro hơn vì tạo nhiều nguồn authoritative theo tenant/key; chỉ dùng khi có routing/fencing và rollback protocol rõ.

## 60. Cutover: chuyển quyền ghi, không chỉ đổi DNS

Một phương án:
1. Ngừng/fence writers cũ ở một điểm kiểm soát chung.
2. Drain in-flight requests và xác minh commit outcomes.
3. Ghi final source barrier.
4. Apply mọi CDC changes tới barrier.
5. Reconcile counters/checksums/business invariants.
6. Đổi routing/credentials theo epoch được quản lý.
7. Mở writes trên target cho canary.
8. Tăng traffic, theo dõi errors/lag/p99.
9. Giữ old source read-only theo policy.
10. Audit quyết định và thời điểm cutover.

Chỉ đổi DNS có thể không ngăn batch jobs hoặc clients giữ connection pools tiếp tục ghi nguồn cũ. **Source writes sau cutover cần bị phát hiện và chặn**, nếu không hai hệ có thể diverge.

## 61. Rollback trước và sau cutover khác nhau

**Trước cutover** nếu target chưa nhận business writes, thường có thể dừng migration và giữ nguồn cũ authoritative.

**Sau cutover** target có writes mới. Quay lại source cũ cần:
- Reverse CDC/outbox có coverage.
- Transform có thể đảo hoặc reconciliation có kiểm soát.
- Duplicate/conflict handling.
- DELETE/TTL/tombstone semantics.
- External side-effect accounting.
- Fresh backup của target.
- Một write gate mới trước khi đảo quyền.

Nếu transform mất thông tin hoặc không có reverse feed, **rollback không phải “đổi connection string trở lại”**. Có thể phải rollforward trên target hoặc khôi phục/đối soát bằng một quy trình riêng.

## 62. Đừng đánh đồng “rời nhà cung cấp” với “xóa dữ liệu nguồn ngay”

Sau cutover:
- Xác nhận target có backup/PITR và restore test.
- Kiểm event consumers/search/indexes đã bắt kịp.
- Thu hồi quyền migration.
- Giữ audit evidence theo policy.
- Theo dõi old-write attempts.
- Xử lý retention/legal hold và yêu cầu xóa dữ liệu.
- Làm sạch staging, temporary exports, logs có PII.
- Chấm dứt resources/contract theo lịch.
- Xác nhận deletion phù hợp policy, kể cả snapshots/bản sao.

Hủy source quá sớm có thể mất khả năng điều tra dữ liệu thiếu hoặc những events chưa đối soát. Giữ source vô hạn lại tạo chi phí, bề mặt tấn công và rủi ro privacy. Cần **lộ trình retire có owner**.

## 63. Khả năng di chuyển cần diễn tập định kỳ

Một exit drill không nhất thiết di chuyển toàn bộ production. Có thể:
1. Chọn dataset synthetic hoặc một tập con được phép.
2. Export theo format và schema đã định.
3. Kiểm checksum/manifest.
4. Dựng đích cô lập bằng IaC.
5. Tái tạo index/validator/roles.
6. Restore bằng recovery identity.
7. Thử các query và conditional writes trọng yếu.
8. Chạy CDC/replay trên đoạn dữ liệu thử.
9. Đo time-to-service/cost.
10. Ghi blockers và thay đổi risk register.

Sau mỗi thay đổi lớn về schema, query, KMS hoặc provider feature, exit drill cần được xem xét lại. **Một plan không diễn tập có thể chỉ là giả thuyết**.

## 64. Chỉ số theo dõi vendor dependency và exit readiness

| Chỉ số | Câu hỏi |
|---|---|
| `provider_specific_api_paths` | Bao nhiêu flow phụ thuộc trực tiếp API chuyên biệt? |
| `critical_dependencies_without_alternative` | Rủi ro nào chưa có phương án? |
| `unverified_consistency_contracts` | Những bất biến nào chưa test ở đích? |
| `last_verified_export_age` | Bao lâu chưa thử xuất? |
| `last_verified_restore_age` | Bao lâu chưa thử restore? |
| `export_completion_time` | Với data hiện tại cần bao lâu? |
| `cdc_retention_headroom` | Source log có đủ cho backfill/outage? |
| `target_reconciliation_mismatch_count` | Dữ liệu đích có khác? |
| `rollback_readiness` | Có đường quay lại có kiểm chứng không? |
| `target_p99_and_error_rate` | Đích có đạt SLO? |
| `schema_config_permission_drift` | Metadata/quyền có lệch? |
| `projected_egress_and_dual_run_cost` | Migration có vượt ngân sách? |
| `exit_drill_blockers_open` | Có blocker chưa đóng? |
| `source_writes_after_cutover` | Có writer bỏ qua fencing? |

Không gắn user IDs/tenant IDs tùy ý thành metric labels. Evidence về hợp đồng và chi phí phải được phân quyền và cập nhật đúng thời hạn.

## 65. Runbook: nhà cung cấp tăng giá hoặc thay điều khoản

1. Xác minh thông báo, ngày hiệu lực và điều khoản contract.
2. Lập workload/cost baseline, không chỉ dùng số tổng trên hóa đơn.
3. Tìm khả năng tối ưu source: index, cache, access pattern, reserved capacity.
4. Cập nhật risk register và exit cost model.
5. Kiểm portability qua PoC với workload quan trọng.
6. Ước tính export/egress và dual-run window.
7. Kiểm security/compliance cùng legal/procurement.
8. So kết quả theo kịch bản và độ nhạy.
9. Quyết định giữ, tối ưu, đàm phán hoặc di chuyển.
10. Ghi trigger tiếp theo và owner.

Không bắt đầu di chuyển dữ liệu production ngay chỉ vì một bảng giá mới trông bất lợi; **chi phí chuyển có thể lớn hơn lợi ích** hoặc đích không giữ được contract nghiệp vụ.

## 66. Runbook: migration có CDC lag không thể bắt kịp

1. Đo tốc độ phát source \(\lambda\) và apply target \(\mu\).
2. Xem lag theo từng stream shard/partition.
3. Kiểm disk/network/index-build/backpressure target.
4. Throttle backfill để nhường capacity cho incremental apply.
5. Kiểm retention và cursor validity.
6. Không skip events hoặc reset cursor sang latest.
7. Tăng throughput khi vẫn giữ per-key ordering.
8. Xử lý poison events/quarantine có owner.
9. Nếu log sẽ hết hạn, NO-GO và resnapshot hoặc đổi strategy.
10. Reconcile trước khi quyết định lại.

**Bắt kịp số lượng events không có nghĩa tự động bảo toàn DELETE/TTL và transaction semantics**.

## 67. Runbook: cutover xong phát hiện sai bất biến

1. Ngừng tăng traffic và cân nhắc write gate theo incident policy.
2. Giữ evidence: source/target state, audit, CDC history, operation IDs.
3. Xác định ảnh hưởng theo tenant/key/workflow.
4. Kiểm cùng recovery watermark, không so hai thời điểm tùy ý.
5. Phân loại transform error, missing event, duplicate, stale version, TTL, authorization.
6. Đánh giá rollback feasibility với target writes mới.
7. Ưu tiên bảo toàn acknowledged writes và external side effects.
8. Thực hiện correction/replay idempotent có audit.
9. Chạy lại business invariant tests.
10. Chỉ tiếp traffic khi safety gates được xác minh.

Không “sửa” bằng cách copy toàn bộ source cũ đè target nếu source đã stale sau cutover.

## 68. Bảng những ngộ nhận cần tránh

| Ngộ nhận | Vì sao nguy hiểm | Hướng đúng |
|---|---|---|
| Export JSON là portability | Thiếu semantics/index/rights | End-to-end restore/test |
| Chọn open source là hết lock-in | Có operational/protocol dependency | Review cả vận hành |
| Abstraction chung cho CRUD đủ | Che consistency/transactions | Domain-specific ports |
| Managed service quá đắt mặc định | Chưa tính on-call/DR | TCO cùng SLO |
| Không dùng tính năng vendor nào | Mất lợi ích và tăng tự xây | Chấp nhận có kiểm soát |
| Hai NoSQL đều có key-value nên giống | Query/index/TTL khác | Capability matrix |
| Có data count bằng nhau nghĩa đúng | Giá, status, deletes sai | Business reconciliation |
| Backup snapshot luôn đọc được ở đích | Native formats khác | Logical export + schema |
| Backup có file là DR-ready | Có thể thiếu key/roles | Restore drill |
| KMS alias mới tự giải mã bản cũ | Key identity/history khác | Key dependency inventory |
| IAM tự đi theo dump | Identity riêng | Permission matrix |
| TTL copy giữ nguyên lifetime | Có thể reset clock | Absolute expiry |
| CDC bắt đầu sau snapshot cũng được | Gap của changes | Coordinated fence |
| Snapshot upsert vô điều kiện | Có thể đè version mới | Version guard |
| DELETE chỉ cần xóa ở target | Backfill hồi sinh | Tombstone/barrier |
| Every stream event exactly once | Retry/replay | Idempotent apply |
| Lag bằng 0 là đủ cutover | Có thể thiếu shard/gaps | Coverage + parity |
| Dual-write là atomic | Hai commits riêng | Failure protocol/outbox |
| DNS đổi là source dừng ghi | Stale clients/direct jobs | Fencing |
| Rollback chỉ đổi URL về S | S thiếu target writes mới | Reverse sync/reconcile |
| Đích chạy GET nhanh là đạt | Chưa kiểm peak/failover/security | Full workload PoC |
| Multi-cloud loại hết rủi ro | Conflict/egress/cost tăng | So theo mục tiêu |
| Một bảng điểm quyết định mọi thứ | Hard constraints bị che | Mandatory gates |
| Giá hiện tại quyết định 5 năm | Load/contracts đổi | Scenario/sensitivity |
| Hợp đồng không phải việc kỹ thuật | Exit rights/support quyết định | Legal/procurement review |
| Cùng seed load test là cùng workload | Env/schedule khác | Versioned fixtures/config |
| Không cần thử exit nếu chưa chuyển | Plan có thể lỗi âm thầm | Periodic drills |
| Xóa nguồn ngay sau switch | Mất rollback/evidence | Controlled retirement |
| Giữ source mãi mãi an toàn | Tăng cost/PII footprint | Lifecycle/retention |

## 69. Bài tập thực hành

### Bài tập 1 — Nhận diện lock-in

Một ứng dụng dùng database managed cho session cache, một ứng dụng khác dùng nó cho checkout payment ledger. Phân loại phụ thuộc về schema, consistency, vận hành, IAM và data exit; giải thích vì sao mức rủi ro khác.

### Bài tập 2 — Sổ đăng ký phụ thuộc

Tạo YAML entry cho thao tác “create order nếu idempotency key chưa tồn tại” với owner, invariant, provider feature, phương án thay thế, evidence và mức rủi ro.

### Bài tập 3 — Phân biệt portability và đúng nghiệp vụ

Một tool xuất/import đủ 100 triệu records. Hãy nêu ít nhất tám lý do hệ mới vẫn có thể trả kết quả sai hoặc không đạt SLO.

### Bài tập 4 — Hard requirements

Một nền tảng yêu cầu không double-charge, dữ liệu trong khu vực được duyệt và p99 dưới giới hạn. Phân biệt điều kiện bắt buộc với tiêu chí có thể tính điểm/trade-off.

### Bài tập 5 — Ma trận query

Liệt kê query theo tenant/time/status và external order key; map access path ở source và đích, tính rủi ro full scans/hot partitions.

### Bài tập 6 — Data model mapping

Chuyển cấu trúc `PK=TENANT#t7, SK=ORDER#o101` thành document model. Thiết kế indexes/uniqueness và test mapping cùng tenant isolation.

### Bài tập 7 — SchemaVersion và kiểu số

Dữ liệu tiền có BigDecimal/Decimal128/Double/Int64 ở các nguồn. Xác định canonical contract và test precision, overflow, currency, null/missing.

### Bài tập 8 — Conditional writes

Chuyển một API Put-if-absent sang MongoDB insert/unique index. Test concurrent same-key, replay after timeout và same key different payload.

### Bài tập 9 — Transaction boundary

Nguồn dùng transaction trên nhiều items; đích chỉ cho atomic per partition. Thiết kế lại dữ liệu hoặc workflow để giữ inventory/order invariant.

### Bài tập 10 — Rủi ro replica/consistency

So read-after-write và CAS behavior ở hai backend theo một lịch sử thao tác gồm write, failover và read. Những điều gì cần đo thay vì chỉ đọc docs?

### Bài tập 11 — Quản lý stream

Hệ nguồn dùng change stream để cập nhật search. Khi sang đích, cần kiểm event fields, ordering, replay, TTL/delete và checkpoint như thế nào?

### Bài tập 12 — Mốc snapshot/CDC

Snapshot 10:00, update 10:05, CDC bắt đầu 11:00. Giải thích gap và thiết kế protocol capture có mốc nhất quán.

### Bài tập 13 — Delete resurrection

Backfill đọc v4, CDC delete v5, backfill v4 tới sau. Thiết kế versioned tombstone và test không hồi sinh.

### Bài tập 14 — TTL

Một session hết hạn 12:00 nhưng copy lúc 11:30. Xác định expected target expiration và những caveats về clock/key TTL.

### Bài tập 15 — Throughput

Data 12 TB, copy 100 MB/s trong điều kiện lý tưởng. Ước lượng thời gian raw và liệt kê nguồn overhead thực khiến số này sai lệch.

### Bài tập 16 — CDC backlog

Source phát 8.000 events/s, target apply 6.000/s. Tính backlog sau một giờ, đề xuất strategy để \(\mu>\lambda\) mà không phá ordering.

### Bài tập 17 — Offline vs online

Một dataset 80 GB và một dataset 80 TB, downtime cho phép 20 phút. Chọn migration approach theo điều kiện nào, tránh kết luận chỉ từ size.

### Bài tập 18 — Dual-write failure matrix

Vẽ các outcomes success/fail/timeout ở S/T. Nếu S authoritative, cách nào đảm bảo target bắt kịp mà không ack business effect chưa được S commit?

### Bài tập 19 — Anti-corruption layer

Thiết kế Java `OrderStore` interface có get, createIfAbsent, updateIfRevision, listByCreatedAt. Định nghĩa consistency/error/pagination contract từng method.

### Bài tập 20 — Open source và operational lock-in

Một đội muốn self-host Cassandra để giảm phụ thuộc cloud nhưng chưa có kinh nghiệm repair/backup. Tính cả DR/on-call/upgrade và viết risk register.

### Bài tập 21 — TCO

Nguồn tốn 100 đơn vị/tháng; đích 75; chi phí migration 320. Tính hoàn vốn đơn giản và giải thích vì sao chưa đủ ra quyết định.

### Bài tập 22 — Egress và data gravity

Database có 20 TB raw data, search và BI copies ở cloud nguồn. Lập inventory những đường mạng và phụ thuộc cần tính khi di chuyển.

### Bài tập 23 — Hợp đồng

Lập checklist các điều khoản cần đối chiếu: export rights, SLA, support, data retention/deletion, price, termination, license và vùng dữ liệu.

### Bài tập 24 — KMS và backup

Backup đã copy sang vùng mới nhưng key decrypt ở vùng cũ không truy cập được. Thiết kế kiểm tra khả năng phục hồi mà không xuất raw key material.

### Bài tập 25 — IAM migration

Sau import, mọi service dùng admin role. Tạo matrix least privilege và positive/negative tests để chứng minh tenant isolation.

### Bài tập 26 — Scoring

Dùng bảng sáu tiêu chí/trọng số trong bài, tính lại tổng khi portability tăng từ 20% lên 35% và phân bổ lại trọng số rõ ràng. Kiểm hard requirements trước khi chọn.

### Bài tập 27 — Sensitivity analysis

Xây ba kịch bản: phí egress gấp đôi, data growth 3×, region mới bắt buộc. Khi nào ưu tiên optimize source thay vì migrate?

### Bài tập 28 — PoC kỹ thuật

Lập test plan cho target bao gồm idempotency, partial updates, read-your-writes, retries, failover, duplicate CDC, TTL, security, p99 và backup restore.

### Bài tập 29 — Shadow-read

So response source/target trong khi CDC lag. Làm sao tránh false mismatches và không lộ PII trong diff logs?

### Bài tập 30 — Cutover

Viết runbook có source write gate, drain, final watermark, CDC catch-up, parity, routing epoch, canary và post-cutover monitor.

### Bài tập 31 — Rollback

Target nhận 50.000 orders sau cutover; source cũ read-only. Vì sao không thể trỏ về S? Thiết kế reverse sync hoặc recovery/compensation.

### Bài tập 32 — Exit drill

Tạo kế hoạch diễn tập một tập dữ liệu synthetic, có schema/index, export/checksum, KMS/IAM, restore độc lập, query/conditional write tests, cost và RTO evidence.

### Bài tập 33 — Đánh giá đa hệ

Một ứng dụng dùng MongoDB cho orders, Cassandra cho activity logs, Redis cho cache và DynamoDB cho preferences. Đề xuất chiến lược exit khác nhau cho authoritative vs derived data; nêu portability risks và ownership từng tập.

### Bài tập 34 — Phản biện phương án sai

Một nhóm nói:

~~~text
Chọn hệ nào export JSON được là đủ.
Không cần lưu indexes/validators khi copy.
Một repository generic CRUD sẽ giúp đổi DB chỉ bằng config.
Giữ response timeout như business failure và tự tạo ID mới khi retry.
Bật CDC sau khi snapshot xong.
Đích cứ overwrite dữ liệu theo thứ tự nhận event.
TTL reset từ lúc import vẫn chấp nhận được.
Chuyển traffic chỉ bằng DNS.
Nếu lỗi, quay về source dù target đã nhận writes.
Bỏ qua IAM/KMS vì là vấn đề hạ tầng.
Giá request rẻ hơn nghĩa TCO thấp hơn.
Đổi sang open source là không lock-in.
Không cần chạy thử restore/exit nếu chưa có sự cố.
```

Chỉ ra từng vấn đề và viết lại kế hoạch có business invariants, data/semantics portability, online synchronization, security, cost, cutover và rollback có thể kiểm chứng.

### Bài tập 35 — Đề xuất quyết định cho hội đồng kỹ thuật

Viết một memo ngắn gồm:
1. Hiện trạng và các động lực muốn rời nhà cung cấp.
2. Critical business/data/consistency requirements.
3. Risk register có probability/impact/confidence.
4. Các phương án: optimize source, selective abstraction, offline/online migration, hybrid.
5. Capability matrix và kết quả PoC.
6. TCO/egress/engineering/dual-run estimates.
7. Hard NO-GO gates và các giới hạn chưa chứng minh.
8. Migration, recovery, security và rollback plans.
9. Exit drill, ownership, triggers và milestones.
10. Quyết định có điều kiện kèm tiêu chí đánh giá lại.

---

**Kết luận:** Đánh giá vendor lock-in của NoSQL không chỉ hỏi liệu có thể mang dữ liệu đi nơi khác, mà phải xem **schema/query paths, consistency/transaction invariants, CDC, backup/restore, IAM/KMS, topology, vận hành và điều khoản thương mại** có thể được thay thế trong phạm vi rủi ro chấp nhận không. Không phải mọi phụ thuộc đều xấu: một tính năng chuyên biệt có thể tạo lợi ích lớn, miễn là nhóm hiểu chi phí thoát, lập risk register và giữ các hợp đồng nghiệp vụ rõ ràng. Khi cân nhắc di chuyển, cần **đánh giá đường truy cập và trạng thái dữ liệu cùng mốc, giữ idempotency/DELETE/TTL, chạy PoC với workload thật, tính TCO và egress, diễn tập restore/cutover và xác định rollback sau target writes**. **Khả năng thoát đã được kiểm chứng, thay vì lời hứa “dễ đổi database”, mới giúp tổ chức chọn nhà cung cấp bằng quyền chủ động thực sự.**
