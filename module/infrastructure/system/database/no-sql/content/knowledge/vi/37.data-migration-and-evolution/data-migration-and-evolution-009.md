# Đối soát nguồn/đích bằng số dòng, giá trị và quy tắc nghiệp vụ

Một dự án di chuyển dữ liệu NoSQL thường báo cáo: “Nguồn có một triệu bản ghi, đích cũng có một triệu bản ghi, vậy là hoàn thành”. Kết luận ấy **không đủ**. Một booking có thể biến mất, một booking khác bị chèn thừa; số lượng vẫn bằng nhau. Một khoản tiền có thể bị làm tròn từ 125.500 thành 125.000; số bản ghi không đổi. Một sự kiện bị xử lý hai lần có thể làm tồn kho giảm hai đơn vị, dù mọi document và event đều đã được chuyển qua.

**Đối soát nguồn/đích (source–target reconciliation)** là hoạt động so sánh có hệ thống dữ liệu nguồn và dữ liệu đích tại **một trạng thái logic có thể đối chiếu**, theo nhiều lớp: số lượng, tập khóa, giá trị/phiên bản, quan hệ và các **bất biến nghiệp vụ**. Mục tiêu không phải làm hai hệ có cùng con số dễ báo cáo, mà chứng minh hệ đích bảo toàn đúng thông tin và hành vi mà hệ nguồn có trách nhiệm cung cấp.

Trong chương **Di chuyển và thay đổi** của module **Database No SQL**, bài học này hướng dẫn thiết lập hợp đồng đối soát khi migration, snapshot + CDC, dual-write, đổi schema hoặc chuyển kiến trúc; xác định **watermark nhất quán**, so sánh đếm theo bucket, tập khóa, giá trị chuẩn hóa, hash/checksum, phiên bản, TTL/deletes và business invariants; thiết kế quy trình sửa sai có kiểm soát; viết một chương trình Java 17 đối soát độc lập và đánh giá các bẫy của MongoDB, DynamoDB, Cassandra, Redis và search projections.

> **Nguyên tắc cốt lõi:** **Số dòng bằng nhau chưa chứng minh dữ liệu bằng nhau; dữ liệu bằng nhau chưa chứng minh nghiệp vụ đúng.** Cần kiểm cả **tập định danh, nội dung, thời điểm, quan hệ và hiệu ứng kinh doanh**.

## 1. Những câu hỏi phải trả lời trước khi chạy đối soát

1. Nguồn nào là **source of truth** và đích đóng vai trò gì?
2. Chúng ta so sánh **ở thời điểm/commit position nào**?
3. Những collection/table/partition/tenant và loại bản ghi nào thuộc phạm vi?
4. Khóa nhận diện duy nhất một bản ghi theo nghiệp vụ là gì?
5. Source schema và target schema có khác nhau không? Mapping được định nghĩa ở đâu?
6. Dữ liệu nào hợp lệ khi khác nhau, chẳng hạn cache, TTL, metadata hoặc eventual-consistency lag?
7. Làm sao kiểm đầy đủ, không chỉ samples?
8. Những quy tắc nghiệp vụ nào phải bất biến sau migration?
9. Có thể phát hiện missing/extra/duplicate và value drift với chi phí nào?
10. Nếu sai, sửa bằng cách nào mà **không ghi đè cập nhật mới ở đích**?
11. Điều kiện để cho phép cutover là gì?
12. Sau cutover, ai theo dõi divergence và trong bao lâu?

Nếu chưa trả lời được câu hỏi về thời điểm và khóa, một báo cáo “99,99% records match” rất dễ mang ý nghĩa sai.

## 2. Ví dụ xuyên suốt: chuyển booking từ NoSQL A sang NoSQL B

Giả sử một ứng dụng cho thuê có:

~~~text
Users / Java Booking API
            |
            v
      Source NoSQL
       (authority)
            |
         Snapshot
            |
            v
        Target NoSQL
            ^
            |
          CDC tail

Reconciliation worker:
  Read source snapshot/watermark
  Read target at matching watermark
  Compare identities, values and invariants
  Produce signed/approved discrepancy manifest
~~~

Ứng dụng chuyển từ một document-store sang một key-value/document API managed. Source record:

~~~json
{
  "tenantId": "T1",
  "reservationId": "R101",
  "status": "CONFIRMED",
  "amountMinor": 125000,
  "currency": "VND",
  "version": 7,
  "updatedAt": "2026-11-14T03:00:00Z"
}
~~~

Target có thể dùng composite key `(pk, sk)`, lưu số tiền, version và status dưới tên field khác. Đối soát phải hiểu **mapping nghiệp vụ**, không chỉ so byte-for-byte hai JSON.

## 3. Năm tầng bằng chứng đối soát

| Tầng | Câu hỏi | Ví dụ kiểm tra |
| --- | --- | --- |
| 1. Phạm vi và thời điểm | Có đang so cùng tập dữ liệu? | Source cutoff và target applied watermark |
| 2. Số lượng | Số bản ghi phù hợp nhau? | Count theo tenant/status/day |
| 3. Định danh | Có missing/extra/duplicate keys? | Set difference, unique key |
| 4. Giá trị | Mỗi bản ghi có nội dung đúng? | Canonical fields, hash, versions |
| 5. Nghiệp vụ | Invariants/side effects đúng? | No double booking, ledger sum, CDC freshness |

Thứ tự kiểm tra giúp khoanh vùng lỗi: count lệch thường đáng điều tra trước; nhưng **count bằng nhau không phải điều kiện đủ để bỏ những tầng còn lại**.

## 4. “Số dòng” trong NoSQL nghĩa là gì?

Ở relational SQL, row thường có cấu trúc tương đối rõ. Trong NoSQL:

- MongoDB: số **documents** trong collection/query scope.
- DynamoDB: số **items** theo table/key condition, có thể gồm các loại entity trong single-table design.
- Cassandra: cần phân biệt partition, clustering rows, logical records và tombstones.
- Redis: số **keys** trong keyspace không tương đương số booking objects; một hash/list có thể chứa nhiều entities.
- Search engine: document có thể là denormalized projection, không phải một record authority.
- Event store: số events không bằng số aggregate states.

Do đó, trước khi nói “source 1 triệu, target 1 triệu”, phải ghi **đơn vị đếm và filter xác định đối tượng nào**.

## 5. Hợp đồng so sánh: reconciliation contract

Một mẫu hợp đồng:

~~~yaml
reconciliation:
  name: "booking-migration"
  source: "authoritative-reservations"
  target: "new-booking-store"
  scope:
    tenants: "all approved tenants"
    entityType: "Reservation"
    includeStatuses: ["CONFIRMED", "CANCELLED", "PENDING"]
    deletedRule: "handled via tombstone mapping"
  identity:
    fields: ["tenantId", "reservationId"]
  comparison:
    asOf: "source CDC watermark W0"
    values:
      - "status"
      - "amountMinor"
      - "currency"
      - "version"
      - "customerRef"
    exclude:
      - "targetIngestedAt"
      - "targetInternalShardId"
  acceptance:
    criticalInvariantViolations: 0
    unresolvedMissingCriticalRecords: 0
  approval:
    dataOwner: "booking-domain"
    technicalOwner: "data-platform"
~~~

Đây là cấu hình mô tả ý tưởng, **không phải schema của một tool cụ thể**. Mỗi quy tắc phải được thống nhất với domain owner, có version và có tests. Không tự coi mọi field khác nhau là lỗi nếu migration cố ý biến đổi representation.

## 6. Chọn khóa định danh đúng

Một reservation ID có thể chỉ duy nhất **trong phạm vi tenant**:

~~~text
Tenant T1, reservation R101
Tenant T2, reservation R101
~~~

Nếu chỉ so theo `reservationId`, hai record bị nhập nhằng, thậm chí có thể coi một bản của T1 thay thế cho T2.

### Định danh chuẩn

\[
Key=(tenantId,\ reservationId)
\]

Với dữ liệu versioned/event:

\[
EventKey=(tenantId,\ aggregateId,\ eventId)
\]

hoặc một sequence có uniqueness được đảm bảo theo aggregate.

### Nguyên tắc

- Dùng **business identity ổn định**, không dùng offset/auto-generated target ID làm khóa so.
- Bao gồm entity type nếu một table chứa nhiều loại entity.
- Ghi rõ normalization cho casing và Unicode nếu business key có text.
- Không bỏ partition/clustering key fields khi chúng là thành phần định danh.
- Nếu ánh xạ một nguồn thành nhiều đích, định nghĩa quan hệ một-nhiều rõ ràng.

## 7. Ví dụ số lượng bằng nhau nhưng dữ liệu sai

Nguồn:

| Key | Amount | Version |
| --- | ---: | ---: |
| T1/R1 | 125.000 | 4 |
| T1/R2 | 80.000 | 2 |
| T2/R3 | 200.000 | 5 |

Đích:

| Key | Amount | Version |
| --- | ---: | ---: |
| T1/R1 | 125.000 | 4 |
| T1/R2 | 75.000 | 2 |
| T2/R4 | 200.000 | 1 |

~~~text
Source count = 3
Target count = 3

T1/R1: MATCH
T1/R2: VALUE MISMATCH (80,000 vs 75,000)
T2/R3: MISSING IN TARGET
T2/R4: EXTRA IN TARGET
~~~

Tổng số bằng nhau nhưng có **ba sai lệch có ý nghĩa**. Nếu T2/R4 là duplicate business booking hoặc dữ liệu tenant khác, tác động thậm chí lớn hơn một value mismatch.

## 8. Đếm theo scope, không dùng tổng cluster

Nên có:

~~~text
count(entityType, tenant, status, timeBucket, partition)
~~~

Ví dụ:

| Scope | Source | Target | Delta |
| --- | ---: | ---: | ---: |
| Tenant T1, CONFIRMED | 120.000 | 120.000 | 0 |
| Tenant T1, CANCELLED | 5.200 | 5.198 | -2 |
| Tenant T2, CONFIRMED | 90.000 | 90.004 | +4 |
| Tenant T2, CANCELLED | 7.000 | 6.998 | -2 |

Tổng delta bằng 0 nhưng **có các bucket sai**. Bucket hóa hỗ trợ khoanh vùng migration jobs, key ranges, thời gian hoặc consumers nào có vấn đề.

### Chọn bucket

- Partition/hash range hoặc prefix của key.
- Tenant/project.
- Created-at/event-time window.
- Trạng thái nghiệp vụ.
- Entity type.
- Region/shard.

Giữ kích thước bucket vừa đủ để chạy đối soát/điều tra mà không tạo hàng triệu series hoặc quá nhiều scans.

## 9. Count API không luôn là count chính xác

Một số database có:

- Estimated collection count hoặc cached statistics.
- Count từ table metadata.
- Scan-based exact count.
- Approximate distinct count.
- Count theo index query.
- Delayed search index counts.

Vì thế phải ghi rõ:

| Thuộc tính | Giá trị cần ghi |
| --- | --- |
| Exact hay approximate? | Đếm trực tiếp hay thống kê? |
| Snapshot/read consistency? | Có thấy state tại cutoff không? |
| Filter? | TTL, soft delete, entity types |
| Scope? | Tenant, partition, key ranges |
| Time? | Lúc nguồn/đích được đọc |
| Duplicates? | Đếm records hay distinct business IDs? |

**Estimated count phù hợp để quan sát xu hướng nhưng không nên dùng làm chứng cứ duy nhất cho migration acceptance**.

## 10. Sai lệch đếm: missing, extra, duplicate

Định nghĩa:

\[
S=\text{set of expected source keys}
\]

\[
T=\text{set of actual target keys}
\]

\[
Missing=S\setminus T
\]

\[
Extra=T\setminus S
\]

\[
MatchedKeys=S\cap T
\]

Lưu ý: set semantics **ẩn duplicate** nếu raw data cho phép nhiều rows cùng business key. Phải kiểm uniqueness trước khi chuyển dữ liệu sang tập keys.

~~~text
Source IDs: A, B, C
Target IDs: A, B, B, D

Raw source row count: 3
Raw target row count: 4
Target distinct keys: 3
Duplicate target key: B
Missing key: C
Extra key: D
~~~

Một bản báo cáo đầy đủ phải ghi **raw count**, **distinct-key count**, **missing**, **extra** và **duplicates**.

## 11. Phương trình hữu ích nhưng không đủ

Nếu mỗi key là unique và cùng scope:

\[
|S|-|T|=|Missing|-|Extra|
\]

Ví dụ 10 missing và 10 extra dẫn đến difference bằng 0. Đó là lý do tổng count có thể đánh lừa.

### Một cách phân loại

~~~text
For every expected key:
  no target key         → MISSING
  one target key, equal → MATCH
  one target key, diff  → VALUE_MISMATCH
  many target keys      → DUPLICATE

For every target key not expected:
  → EXTRA
~~~

Chưa xét sai lệch nghiệp vụ; tầng đó kiểm riêng.

## 12. Ranh giới thời gian: không so hai ảnh chụp ở hai thời điểm

Một hệ đang nhận writes:

~~~text
10:00:00 Read source count = 1,000,000
10:00:01 New booking committed
10:00:02 Read target count = 1,000,001
~~~

Delta 1 **có thể hoàn toàn bình thường** vì dữ liệu thay đổi giữa hai lần đo. Không nên bắt nguồn/đích có cùng count “ngay lúc này” nếu chúng không cùng một logical cutoff.

### Yêu cầu

Đối soát phải gắn với **as-of commit position/event sequence/watermark**, hoặc tạm freeze writes đủ an toàn để chụp một ảnh logic nhất quán khi kiến trúc cho phép.

## 13. Snapshot + CDC: pattern phổ biến

~~~text
              SOURCE AUTHORITY
                 |          |
       Snapshot at W0     CDC after W0
                 |          |
                 v          v
              TARGET  ←  ordered/idempotent apply
                 |
      Applied watermark >= W1
                 |
                 v
       Reconcile state at W1
~~~

Điều kiện:

1. Snapshot chứa state của mốc W0 theo semantics được bảo đảm.
2. CDC bắt đầu từ đúng vị trí để không có gap.
3. Consumer áp changes sau W0 ít nhất một lần với dedupe/idempotency.
4. Ordering đủ bảo vệ mỗi aggregate.
5. Target báo applied watermark sau **durable apply**, không chỉ nhận message.
6. Reconciliation so source và target tại **cùng mốc logic W1**.

Đây là một **mẫu kiến trúc**; API cụ thể của mỗi NoSQL/CDC tool có giới hạn về snapshot consistency và resume position.

## 14. High-watermark là gì?

High-watermark có thể là:

- MongoDB change-stream resume/cluster time trong phạm vi hỗ trợ.
- DynamoDB Streams position/sequence metadata theo shard và consumer.
- Cassandra CDC segment/offset hoặc vị trí do connector quản lý.
- Database commit sequence hoặc binlog position.
- Event-store aggregate version.
- Kafka topic-partition offsets (theo từng partition).

**Không nhất thiết có một số nguyên duy nhất cho toàn hệ.** Một stream gồm nhiều partitions có thể cần **vector watermarks**:

~~~text
Partition P0 applied through offset 120
Partition P1 applied through offset  75
Partition P2 applied through offset 204
~~~

Đích chỉ “bắt kịp” tới cutoff đã chọn khi **mọi partition liên quan** đã được xử lý bền đến vị trí tương ứng. Chỉ nhìn offset lớn nhất của một partition có thể bỏ sót phần còn lại.

## 15. Watermark không đồng nghĩa thời gian trên đồng hồ

Một event có:

~~~text
businessTime = 10:00:00
sourceCommitTime = 10:00:03
CDCObservedTime = 10:00:05
targetAppliedTime = 10:00:06
~~~

Event-time cũ không có nghĩa event đã được commit trước một checkpoint. Clock skew, delayed writes và retries có thể làm thứ tự timestamps khác thứ tự commit.

### Khuyến nghị

- Ưu tiên source commit positions/monotonic aggregate versions.
- Phân biệt `createdAt` của nghiệp vụ với `committedAt` và `ingestedAt`.
- Nếu chỉ có timestamps, công bố **giới hạn tin cậy** và xử lý late-arriving data.
- Tránh tuyên bố hai snapshot nhất quán toàn cục nếu engine chỉ có per-partition guarantees.

## 16. Nếu không có consistent snapshot toàn hệ

Một số NoSQL hoặc deployment không cung cấp snapshot atomic trên nhiều shards/tables. Lúc đó:

- Ghi snapshot position riêng theo partition/table.
- Dùng change feed để nối khoảng biến động.
- Thiết kế record-version checks hoặc quiescence window nếu được phép.
- So từng aggregate sau khi cả nguồn/đích đã qua một commit cutoff an toàn.
- Đối soát lặp lại các bucket bị thay đổi giữa các passes.
- Gắn “uncertain window” với records chưa thể kết luận.

**Một backup hoàn chỉnh về vật lý chưa chắc tương ứng một database transaction snapshot duy nhất xuyên mọi dataset**.

## 17. Độ trễ CDC và khác biệt tạm thời

Ví dụ:

~~~text
Source latest update version = 18
Target latest applied version = 16
CDC consumer backlog = 45 seconds
~~~

Ngay lúc này value mismatch có thể do target chưa bắt kịp, không phải mapping sai.

Phải phân loại:

| Trạng thái | Ý nghĩa | Xử lý |
| --- | --- | --- |
| LAGGING | Target watermark chưa qua cutoff | Chờ/apply catch-up |
| MATCH | Đủ watermark, values match | Pass |
| MISSING | Đủ watermark nhưng thiếu key | Điều tra |
| EXTRA | Target có key không mong đợi | Điều tra |
| VALUE_MISMATCH | Key có cả hai, canonical values khác | Điều tra |
| CONFLICT | Concurrent writes/versions không thể quy đổi | Domain review |
| UNKNOWN | Missing evidence/unsupported semantics | Không tự pass |

Không được “sửa” bằng cách xóa target data khi target chỉ đang lag hoặc source state đã thay đổi ngoài phạm vi so.

## 18. Canonicalization: so ý nghĩa, không so JSON text

Hai documents:

~~~json
{"amount":125.00,"currency":"USD","status":"CONFIRMED"}
~~~

~~~json
{"status":"CONFIRMED","currency":"USD","amount":125.0}
~~~

JSON bytes khác do **field order và numeric formatting**, nhưng có thể tương đương theo business contract.

### Canonical representation

Trước so/hash, cần:

1. Xác định danh sách trường bắt buộc.
2. Ánh xạ source/target fields về một logical schema.
3. Định nghĩa type và units.
4. Quy tắc null/missing/empty.
5. Sắp thứ tự map keys nếu maps không có ý nghĩa thứ tự.
6. Giữ thứ tự arrays nếu thứ tự có ý nghĩa.
7. Chuẩn hóa timestamp/timezone.
8. Chuẩn hóa case/Unicode **chỉ khi domain cho phép**.
9. Loại bỏ operational metadata không nằm trong contract.
10. Serialize không nhập nhằng trước khi hash.

Một hàm canonicalization tùy tiện có thể làm hai giá trị thực sự khác nhau bị coi là bằng nhau.

## 19. Tiền tệ: không đối soát bằng floating-point

Sai về semantic precision:

~~~text
source amount = 0.1 + 0.2
target amount = 0.3
Compare raw IEEE-754 double bits
~~~

Binary floating-point không biểu diễn chính xác nhiều số thập phân.

Ưu tiên:

- **Integer minor units** theo contract (và đúng đơn vị từng currency).
- `BigDecimal` với scale/currency rules.
- Không âm thầm làm tròn khi migration.
- Kiểm range/overflow.
- Kiểm sum theo currency, không cộng lẫn các loại tiền.

Ví dụ amount source `125000` trong đơn vị nhỏ nhất và target `125.000` trong một đơn vị khác **không thể so trực tiếp** nếu chưa định nghĩa conversion.

### Kiểm business money

\[
\sum_{\text{tenant,currency}}SourceAmount
=
\sum_{\text{tenant,currency}}TargetAmount
\]

Tổng tiền bằng nhau là một invariant bổ sung, **không thay việc so từng transaction**.

## 20. Thời gian, múi giờ và độ phân giải

Nguồn:

~~~text
2026-11-14T03:30:00.000Z
~~~

Đích:

~~~text
2026-11-14T10:30:00+07:00
~~~

Hai chuỗi diễn đạt cùng một instant. So string trực tiếp sẽ báo mismatch giả.

### Quy tắc

- So `Instant` sau khi parse timezone/offset rõ.
- Nếu domain dùng local date (ngày check-in), giữ **local date semantics**, không ép tất cả thành UTC instant nếu ý nghĩa khác.
- Ghi precision: milliseconds, microseconds, nanoseconds; không làm tròn vô tình.
- Khi source và target chỉ lưu độ phân giải khác nhau, định nghĩa tolerance và chứng minh nó không làm hỏng nghiệp vụ.
- Kiểm DST/timezone conversion cho ngày/giờ địa phương.

Không dùng một tolerance mơ hồ “±1 ngày” để che lỗi timezone trong booking dates.

## 21. Null, missing và default values

Ba trạng thái:

~~~json
{"phone":null}
~~~

~~~json
{}
~~~

~~~json
{"phone":""}
~~~

có thể mang ý nghĩa khác nhau:

- Null: đã biết không có giá trị.
- Missing: field chưa được khai báo/không áp dụng.
- Empty string: người dùng nhập rỗng hoặc giá trị hợp lệ tùy schema.

Một migration đặt default `false` cho missing boolean có thể làm thay đổi ý nghĩa **unknown vs false**.

### Viết hợp đồng

| Field | Source semantics | Target mapping |
| --- | --- | --- |
| `deletedAt` | Missing hoặc null nghĩa active | Giữ phân biệt nếu cần |
| `phone` | Optional | Không ép empty thành null nếu không cho phép |
| `discount` | Missing là chưa tính | Không mặc định 0 nếu domain khác |
| `currency` | Bắt buộc | Reject khi missing |
| `version` | Monotonic | Không reset về 1 khi import |

**Canonicalization chỉ được hợp nhất hai trạng thái khi domain owner xác nhận chúng tương đương.**

## 22. String normalization, Unicode và case

Ví dụ:

~~~text
"Café" (composed)
"Café" (decomposed combining mark)
~~~

Hai chuỗi nhìn giống nhau nhưng Unicode code points có thể khác. Tùy domain, có thể chuẩn hóa NFC trước khi so.

Tuy nhiên:

- Email/usernames có chính sách case/normalization riêng.
- Passwords, cryptographic identifiers, opaque tokens **không được tự normalize**.
- Collation/sort order có thể khác giữa DBs.
- Whitespace, dấu, locale có thể mang nghĩa thật.
- Nếu key normalization đổi, có nguy cơ collision giữa hai keys trước đó khác nhau.

**Trước khi normalize key, phải kiểm collisions**: mapping hai source IDs thành một target ID là mất dữ liệu dù count được điều chỉnh cho đẹp.

## 23. Arrays, sets và thứ tự

Source:

~~~json
{"amenities":["wifi","pool"]}
~~~

Target:

~~~json
{"amenities":["pool","wifi"]}
~~~

Nếu amenities là **tập tính năng**, có thể coi tương đương sau sort/dedupe theo rule. Nếu array chứa **event history, ordered itinerary, transaction lines**, thứ tự là một phần dữ liệu và không được sort tùy ý.

Tương tự, duplicate array elements có thể có hoặc không có nghĩa:

- Tags: duplicate thường không có giá trị.
- Cart items: duplicate line items có thể đại diện nhiều ý định.
- Ledger: duplicate transaction tuyệt đối không được tự bỏ.

Hợp đồng so sánh phải nêu set/list/multiset semantics cho từng field.

## 24. Schema evolution và intentional transformation

Nguồn:

~~~json
{
  "totalPrice": "125000",
  "country": "VN"
}
~~~

Đích:

~~~json
{
  "amountMinor": 125000,
  "currency": "VND",
  "countryCode": "VN"
}
~~~

Khác tên và type không nhất thiết là dữ liệu khác. Cần **mapping có version**:

~~~text
target.amountMinor = strictParseInteger(source.totalPrice)
target.currency    = "VND" only if source domain guarantees VND
target.countryCode = validatedIsoCode(source.country)
~~~

### Không tự gán default khi thiếu bằng chứng

Nếu source có nhiều currencies, gán mặc định VND cho mọi record có thể khiến counts/keys khớp nhưng giá trị tiền tệ sai. Mỗi chuyển đổi phải có input assumptions, error policy, overflow/range checks và expected examples.

## 25. Hash một record sau canonicalization

Giả sử canonical payload:

~~~text
Key: T1/R101
Status: CONFIRMED
AmountMinor: 125000
Currency: VND
Version: 7
~~~

Tạo SHA-256 trên **bytes được mã hóa ổn định**:

\[
h(k)=SHA256(Canonical(k,value))
\]

Đối với mỗi key ở cả hai phía:

~~~text
sourceKey == targetKey?
sourceHash == targetHash?
~~~

Hash giúp phát hiện khác biệt hiệu quả, nhưng:

- Hash equality không phải một lời chứng tuyệt đối cho business correctness.
- Hash collisions về lý thuyết vẫn có thể xảy ra.
- Hai record sai giống hệt nhau ở source và target vẫn hash match.
- Nếu canonicalization bỏ field quan trọng, hash không phát hiện khác biệt ở field ấy.
- Không ghi raw PII/secrets vào logs chỉ để điều tra hash mismatch.

## 26. Canonical serialization phải không nhập nhằng

Cách nối chuỗi sai:

~~~text
fields ["ab", "c"] → "abc"
fields ["a", "bc"] → "abc"
~~~

Hai records khác nhau tạo cùng chuỗi **trước cả khi hash**. Sử dụng format canonical với escaping hoặc length-prefix.

Ví dụ length-prefix:

~~~text
["ab","c"] → "2:ab1:c"
["a","bc"] → "1:a2:bc"
~~~

Với nested objects/arrays, cần type tags và quy tắc serialize đệ quy rõ, không dùng một hàm `toString()` bất ổn theo ngôn ngữ/locale.

## 27. Hash theo bucket và Merkle tree

Nếu có hàng tỷ records, đọc/so từng record qua mạng tốn chi phí. Có thể:

1. Chia keyspace thành các buckets có boundary xác định.
2. Tính count và deterministic digest cho mỗi bucket.
3. So các bucket-level digests.
4. Chỉ drill-down những buckets lệch.

~~~text
                  Root digest
                /             \
          Bucket group A      Bucket group B
            /     \            /     \
           A1     A2          B1      B2
                 mismatch!
                    |
            Compare individual keys
~~~

**Merkle tree** là một cách tổ chức digests theo cây để khoanh vùng sai lệch; còn nhiều implementation details về key ordering, hashing, versioning và dữ liệu động cần thiết kế riêng.

### Cẩn thận với phép gộp đơn giản

Không dùng XOR của hashes mà không xét duplicates: hai bản sao giống nhau có thể triệt tiêu trong XOR, làm mất dấu một số sai lệch. Một digest tập hợp đáng tin hơn phải có count, unique-key rules, thứ tự ổn định/commit cutoff và chống ambiguity.

## 28. Sampling: hữu ích nhưng không đủ cho dữ liệu quan trọng

Một kiểm tra mẫu ngẫu nhiên 1.000 trong một triệu records có thể không bắt được một sai lệch hiếm nhưng nghiêm trọng.

Sampling phù hợp để:

- Kiểm transformation mapping sớm.
- Theo dõi health liên tục giữa các đợt full scan.
- Kiểm nhiều query shapes.
- Phát hiện systemic corruption.

Nhưng nếu business yêu cầu **không thiếu transaction nào**, cần đối soát full keyspace hoặc cơ chế đầy đủ có chứng cứ tương đương cho critical records, không chỉ sampling.

### Stratified sampling

Chọn mẫu theo tenant, tuổi dữ liệu, trạng thái, record size, numeric edge cases, nested arrays và hot/cold partitions. Random toàn bộ có thể bỏ lỡ nhóm nhỏ nhưng rủi ro cao.

## 29. Tổng hợp kiểm tra count, checksum và full diff

Một pipeline có thể theo dạng:

~~~text
Stage A: Scope + watermark completeness
   |
   v
Stage B: Exact counts by bucket
   |
   v
Stage C: Distinct keys + duplicate detection
   |
   v
Stage D: Bucket digests
   |
   +→ match → record evidence
   |
   +→ mismatch → key-level diff and canonical value compare
   |
   v
Stage E: Cross-record business invariant checks
   |
   v
Acceptance / remediation decision
~~~

**Hash mismatch không phải nơi dừng báo cáo**. Phải có khả năng xuất ra affected keys và mismatch types để sửa đúng và giải thích cho domain owner.

## 30. Quy tắc nghiệp vụ: tầng đối soát không thể thiếu

Hai hệ có thể có **đúng cùng documents** nhưng documents không còn đáp ứng nghiệp vụ vì migration làm sai quan hệ hoặc consumers tạo side effects:

- Booking confirmed nhưng inventory chưa reserve đúng.
- Một payment bị capture hai lần.
- Loyalty points được cộng thêm vì replay event.
- Voucher đã expired bị hồi sinh.
- Tổng tiền ledger khác tổng số tiền giao dịch.
- Trạng thái booking không hợp lệ theo workflow.
- Search projection quảng cáo chỗ còn trống trong khi authority hết chỗ.

Tầng business invariants phải được triển khai thành queries/validators độc lập với hash.

## 31. Bất biến “không double booking”

Ví dụ một phòng có capacity 1 cho mỗi ngày:

\[
ConfirmedAllocations(room,date)\le Capacity(room,date)
\]

Đây là **điều kiện nghiệp vụ cần được đảm bảo tại authority**, không chỉ là báo cáo để xem sau. Reconciliation có thể phát hiện sai lệch:

~~~text
room=R1, date=2026-11-20
source CONFIRMED allocations = 1
target CONFIRMED allocations = 2
physical capacity = 1
~~~

Nếu target có hai bookings cùng slot dù count toàn hệ khớp, migration không được cutover.

### Điều cần kiểm

- Full key của inventory: resource + date/time + tenant nếu cần.
- Status nào giữ chỗ thực sự?
- Hold/expiry/reservation window.
- Idempotency key cho một intent.
- Concurrent writes và conditional transaction.

Không tự quyết định chỉ dựa trên dữ liệu search/cache eventual; business authority phải quyết định.

## 32. Ledger và tổng tiền theo currency

Ví dụ nguồn và đích:

| Tenant | Currency | Source amountMinor sum | Target amountMinor sum |
| --- | --- | ---: | ---: |
| T1 | VND | 25.400.000 | 25.400.000 |
| T2 | VND | 11.300.000 | 11.250.000 |
| T3 | USD | 320.00 | 320.00 |

T2 lệch 50.000 (đơn vị minh họa). Nhưng ngay cả T1 có tổng khớp, vẫn cần so **từng transaction/payment ID**: một giao dịch +100.000 và giao dịch khác -100.000 có thể triệt tiêu.

### Quy tắc

- Tổng riêng theo currency và tenant/account.
- Định nghĩa signed amounts, refunds, voids, chargebacks.
- Không trộn VND/USD bằng một tỷ giá tùy tiện.
- Kiểm transaction uniqueness và event idempotency.
- Với tiền tệ, ưu tiên integer minor units/decimal chính xác và audit ledger bất biến.

**Aggregate sums là tín hiệu mạnh, nhưng không thay identity-level reconciliation.**

## 33. Cross-record referential rules trong NoSQL

NoSQL có thể không enforce foreign keys:

~~~text
Reservation
  listingId = L101
  customerId = U101
  paymentRef = P101
~~~

Các checks:

- `listingId` có tham chiếu resource hợp lệ không?
- `customerId` có đúng tenant không?
- Payment reference có phải duy nhất và trạng thái hợp lệ?
- Parent/child counts sau denormalization có đúng không?
- Một booking CANCELLED có còn active allocation trái policy không?

Nếu migration chuyển một bảng booking thành nhiều documents/materialized views, **đếm documents giữa nguồn/đích không thể so 1:1**. Đối soát theo **business entities và relations**.

## 34. Kiểm workflow trạng thái

Một quy trình:

~~~text
PENDING → CONFIRMED → COMPLETED
    |          |
    +→ CANCELLED
~~~

Không phải mọi transition đều hợp lệ. Kiểm:

- Status đích có nằm trong enum/transition contract?
- Version tăng monotonically theo aggregate?
- Một booking đã CANCELLED có bị về PENDING do CDC out-of-order không?
- Các transition có timestamps/actor hợp lý?
- Duplicate event có làm side effect lần hai?

Một record source và target có status giống nhau nhưng version thấp hơn expected watermark có thể che một **lost update** sau migration.

## 35. TTL, soft delete và retention

Nguồn:

~~~json
{
  "reservationId":"R101",
  "deletedAt":"2026-11-14T08:00:00Z"
}
~~~

Đích:

~~~text
No item exists because deletion was applied.
~~~

Hai representations có thể tương đương nếu target contract là hard delete và CDC đã áp đúng. Nhưng phải phân biệt:

- Xóa theo yêu cầu người dùng.
- Soft delete vì nghiệp vụ.
- TTL expiry hợp lệ.
- Purge theo compliance.
- Bad delete/accidental cleanup.

**Không coi “missing” là lỗi** khi target policy phải xóa record đó; cũng không tự hồi sinh record đã hết retention chỉ để count khớp.

## 36. Tombstone và timestamp trong Cassandra

Trong Cassandra/wide-column, xóa có thể tạo tombstones, và các giá trị/tombstones được kết hợp theo timestamp/merge semantics của engine.

Những bẫy:

- Đếm row từ storage files không tương đương logical live rows.
- TTL có thể khiến dữ liệu không còn đọc được trước khi compaction reclaim physical bytes.
- Snapshot cũ chứa values mà tombstone mới hơn sẽ che.
- Việc ghi lại dữ liệu cũ với timestamp tùy ý có thể gây **data resurrection** hoặc overwrite legitimate writes.
- Replicas chưa repair có thể quan sát state khác tùy consistency.

Khi migration từ/to Cassandra, xác định **logical read contract, TTL/tombstone semantics và scope của timestamp**. Không dùng tổng SSTable rows làm source-of-truth count.

## 37. DynamoDB: composite keys và Streams

DynamoDB thường mô hình hóa bằng partition key, có thể kèm sort key. Khi đối soát:

- So **full primary key**, không chỉ `pk` nếu table có `sk`.
- Phân biệt nhiều entity types trong single-table design.
- Không dùng table metadata `ItemCount` vốn có thể không real-time exact làm chứng cứ cuối duy nhất.
- Scan/Query có cost và page limits; xử lý pagination hoàn chỉnh.
- Đọc eventual-consistency có thể làm xuất hiện mismatch tạm thời; chọn consistency theo API/requirement.
- DynamoDB Streams có stream records theo shards/retention; không coi offset một shard là toàn hệ.
- Global Tables và multi-region replication có conflict semantics cần thiết kế riêng.

Đối soát nên theo business IDs/versions và so target tại source watermark hợp lệ.

## 38. MongoDB: counts, change streams và documents

Một quy trình MongoDB:

1. Định nghĩa collection/query scope, soft-deleted states.
2. Chọn snapshot/cutoff phù hợp với topology và write concerns.
3. Dùng count có semantics chính xác cho query, không chỉ estimate.
4. Đọc documents theo stable `_id`/business key và deterministic projection.
5. Normalize BSON types: Decimal128, ObjectId, dates, arrays, null/missing.
6. Đối soát indexes và query behavior sau migration, không chỉ persisted values.
7. Theo dõi change streams cùng resume positions và retention nếu sử dụng CDC.

### BSON khác JSON

MongoDB BSON có types đặc thù; stringify sang JSON thông thường có thể mất thông tin type/precision. Canonicalization phải bảo toàn giá trị thực mà business cần, không ép mọi numeric/date thành chuỗi tùy ý.

## 39. Redis, cache và search: không áp count 1:1 sai mục đích

Redis cache:

~~~text
Source DB has 1,000,000 listings.
Redis currently caches 50,000 hot listings.
~~~

Count Redis và DB **không cần bằng nhau** khi cache được phép lưu subset.

Search index:

~~~text
One listing → one denormalized document plus nested fields.
Some listings intentionally excluded from search.
~~~

Một count mismatch có thể đúng theo projection rules.

### Hợp đồng dành cho derived stores

- Những authoritative entities nào **phải xuất hiện**?
- Những entities nào phải **bị loại trừ**?
- Các fields/aggregates nào phải tương ứng?
- Freshness SLO và version watermark?
- Khi source delete, đích phải mất record trong bao lâu?
- Có thể rebuild từ source không?

Không lấy Redis hoặc search làm authority thay database nguồn của booking khi semantics không cho phép.

## 40. Đối soát materialized views và denormalization

Giả sử source:

~~~text
Booking R101
  3 line items
  2 guests
~~~

Target:

~~~text
booking-summary:R101
booking-lines:R101:1..3
guest-view:R101:1..2
~~~

Source count=1, target count=6. Đây không phải mismatch nếu mapping thiết kế một-nhiều.

### Cách kiểm

1. Đối soát **aggregate booking identity**.
2. Kiểm child counts 3 và 2.
3. Kiểm foreign-key-like references.
4. Kiểm summary total bằng sum(lines).
5. Kiểm duplicated denormalized fields đồng nhất.
6. Kiểm source version được projection áp.

Phải xây một **logical reconciliation view** thay vì so số physical documents trực tiếp.

## 41. Dual-write và outbox: tránh hai nguồn sự thật

Một migration có thể giai đoạn đầu:

~~~text
Java service
    |
    +→ write Source
    |
    +→ write Target
~~~

Rủi ro:

- Source write thành công, target timeout.
- Target write thành công, source timeout.
- Hai writes có ordering khác.
- Retry gây duplicate.
- Cross-store transaction thường không có atomicity tự nhiên.

### Giải pháp được cân nhắc

- Một authority rõ ràng, target theo CDC/outbox.
- Event IDs/idempotency.
- Reconciliation thường xuyên.
- Version guard ở đích.
- Ghi trạng thái unknown outcome cho write timeouts.
- Nếu dual-write bắt buộc, thiết kế compensation và phân biệt partial-success.

**Dual-write không tự tạo exactly-once cross-database**, dù cả hai APIs đều trả success trong phần lớn trường hợp.

## 42. Phân loại sai lệch theo nguyên nhân

| Loại | Nguyên nhân ví dụ | Bước tiếp theo |
| --- | --- | --- |
| MISSING | CDC gap, failed insert, wrong filter | Replay/repair có guard |
| EXTRA | Bad delete propagation, filter mismatch | Kiểm legitimacy trước delete |
| DUPLICATE | Missing unique key/idempotency | Reconcile business identity |
| VALUE_MISMATCH | Mapping/rounding/truncation | Fix transform và reprocess |
| STALE_VERSION | CDC lag/out-of-order | Wait/catch-up, then compare |
| TYPE_MISMATCH | Integer/decimal/timestamp encoding | Canonicalize và validate |
| TTL_MISMATCH | Different expiry policy | So intended state as-of cutoff |
| WRONG_TENANT | Key mapping/cross-tenant bug | Security incident + stop cutover |
| INVARIANT_FAILURE | Double booking, ledger mismatch | Stop cutover, domain review |
| INDETERMINATE | Missing watermark/evidence | Bổ sung evidence, không tự pass |

“Lệch” là một trạng thái kỹ thuật; **kết luận phải dựa trên loại lệch và hậu quả**, không chỉ % records khác nhau.

## 43. Java 17: bài lab đối soát bản ghi độc lập

Chương trình dưới đây **tự chạy bằng Java 17**, không cần thư viện NoSQL hay kết nối mạng. Nó so danh sách booking từ source và target, chuẩn hóa một số field, phát hiện raw duplicate business keys, missing, extra và value mismatches. Bài lab giả định dữ liệu đã được trích xuất ở **cùng một logical watermark**, không tự xử lý CDC.

Tạo `BookingReconciliationDemo.java`:

~~~java
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.ArrayList;
import java.util.HexFormat;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.SortedMap;
import java.util.TreeMap;
import java.util.TreeSet;

public final class BookingReconciliationDemo {
    record Key(String tenantId, String reservationId)
            implements Comparable<Key> {
        @Override
        public int compareTo(Key other) {
            int first = tenantId.compareTo(other.tenantId);
            return first != 0 ? first
                    : reservationId.compareTo(other.reservationId);
        }

        @Override
        public String toString() {
            return tenantId + "/" + reservationId;
        }
    }

    record Booking(
            Key key,
            String status,
            BigDecimal amount,
            String currency,
            long version,
            boolean deleted) {}

    static SortedMap<Key, Booking> indexLive(
            List<Booking> rows, String label) {

        SortedMap<Key, Booking> index = new TreeMap<>();
        for (Booking booking : rows) {
            // Contract of this demo: exclude deleted state.
            if (booking.deleted()) {
                continue;
            }

            Booking duplicate = index.putIfAbsent(
                    booking.key(), booking);
            if (duplicate != null) {
                throw new IllegalArgumentException(
                    label + " duplicate key " + booking.key());
            }
        }
        return index;
    }

    static String field(String text) {
        // Length prefix prevents ["ab","c"] and
        // ["a","bc"] from serializing the same way.
        return text.length() + ":" + text;
    }

    static String canonical(Booking b) {
        String status = b.status()
                .trim().toUpperCase(Locale.ROOT);
        String currency = b.currency()
                .trim().toUpperCase(Locale.ROOT);
        String amount = b.amount()
                .stripTrailingZeros().toPlainString();

        return field(status)
                + field(currency)
                + field(amount)
                + field(Long.toString(b.version()));
    }

    static String sha256(String input) {
        try {
            byte[] bytes = MessageDigest
                    .getInstance("SHA-256")
                    .digest(input.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(bytes);
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
    }

    static boolean domainValid(Booking booking) {
        // Illustrative invariant only.
        return switch (booking.status().toUpperCase(Locale.ROOT)) {
            case "CONFIRMED" ->
                    booking.amount().compareTo(BigDecimal.ZERO) > 0;
            case "CANCELLED" -> true;
            default -> false;
        };
    }

    static void reconcile(
            List<Booking> sourceRows,
            List<Booking> targetRows) {

        SortedMap<Key, Booking> source =
                indexLive(sourceRows, "source");
        SortedMap<Key, Booking> target =
                indexLive(targetRows, "target");

        Set<Key> allKeys = new TreeSet<>();
        allKeys.addAll(source.keySet());
        allKeys.addAll(target.keySet());

        int match = 0;
        int missing = 0;
        int extra = 0;
        int mismatch = 0;
        int invalid = 0;

        System.out.println("SOURCE_COUNT=" + source.size());
        System.out.println("TARGET_COUNT=" + target.size());

        for (Key key : allKeys) {
            Booking s = source.get(key);
            Booking t = target.get(key);

            if (s == null) {
                extra++;
                System.out.println("EXTRA " + key);
                continue;
            }
            if (t == null) {
                missing++;
                System.out.println("MISSING " + key);
                continue;
            }

            if (!domainValid(s) || !domainValid(t)) {
                invalid++;
                System.out.println("INVALID_DOMAIN " + key);
            }

            String left = sha256(canonical(s));
            String right = sha256(canonical(t));

            if (left.equals(right)) {
                match++;
                System.out.println("MATCH " + key);
            } else {
                mismatch++;
                System.out.println("DIFFERENT " + key
                        + " source=" + canonical(s)
                        + " target=" + canonical(t));
            }
        }

        System.out.printf(
                "MATCH=%d MISSING=%d EXTRA=%d"
                + " DIFFERENT=%d INVALID=%d%n",
                match, missing, extra, mismatch, invalid);
    }

    public static void main(String[] args) {
        List<Booking> source = List.of(
            new Booking(new Key("T1", "R1"),
                "CONFIRMED", new BigDecimal("125000.00"),
                "VND", 4, false),
            new Booking(new Key("T1", "R2"),
                "CONFIRMED", new BigDecimal("80000"),
                "VND", 2, false),
            new Booking(new Key("T2", "R3"),
                "CANCELLED", new BigDecimal("200000"),
                "VND", 5, false),
            new Booking(new Key("T2", "R0"),
                "CANCELLED", new BigDecimal("0"),
                "VND", 3, true));

        List<Booking> target = List.of(
            new Booking(new Key("T1", "R1"),
                "confirmed", new BigDecimal("125000"),
                "vnd", 4, false),
            new Booking(new Key("T1", "R2"),
                "CONFIRMED", new BigDecimal("75000"),
                "VND", 2, false),
            new Booking(new Key("T2", "R4"),
                "CANCELLED", new BigDecimal("200000"),
                "VND", 1, false));

        reconcile(source, target);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac BookingReconciliationDemo.java
java BookingReconciliationDemo
~~~

Kết quả dự kiến theo logic chương trình:

~~~text
SOURCE_COUNT=3
TARGET_COUNT=3
MATCH T1/R1
DIFFERENT T1/R2 ...
MISSING T2/R3
EXTRA T2/R4
MATCH=1 MISSING=1 EXTRA=1 DIFFERENT=1 INVALID=0
~~~

### Ý nghĩa

- Source và target có count đều bằng 3, nhưng chỉ một business key match.
- `125000.00` và `125000` được coi tương đương theo quy tắc decimal đã định.
- Status/currency được normalize case **chỉ cho mục đích bài lab**; product thực phải xác nhận policy.
- R0 có `deleted=true` được loại theo projection contract minh họa.
- Chương trình phát hiện duplicate raw key (với các live records) thay vì âm thầm ghi đè trong map.

### Giới hạn

- Bộ dữ liệu nhỏ và đọc hết vào RAM. Sản xuất cần streaming/pagination/bucket checkpoints.
- Hash canonical fields không bao gồm customer, room, payment, timestamps hoặc cross-record rules; phải mở rộng contract.
- Chưa chứng minh cùng source/target watermark.
- Chưa xử lý errors từ API, partial scans, retries hoặc network partitions.
- Không tự repair, không tính tổng tiền theo tenant và không kiểm capacity thực.
- So hash không đảm bảo dữ liệu nguồn đúng; có thể cần validator độc lập với hai bên.

## 44. Từ bài lab sang dữ liệu hàng tỷ records

Không nên dùng `Map<Key,Record>` chứa toàn bộ bảng khi có hàng tỷ keys. Một pipeline mở rộng:

~~~text
Source enumerator -- pages --> Canonical sorted key stream
                           \
                            Merge-join by full business key
                           /
Target enumerator -- pages --> Canonical sorted key stream
                            |
                            v
                    Diff manifest + metrics
~~~

Có thể dùng external sorting hoặc partitioned buckets khi hai hệ không hỗ trợ cùng sort order.

### Yêu cầu vận hành

- Stable pagination/resume tokens.
- Retry có backoff, không bỏ pages.
- Deduplication khi scan lại sau failure.
- Checkpoint per bucket/partition.
- Snapshot/watermark consistency.
- Bounded memory, I/O và egress.
- Tránh một scan khổng lồ làm quá tải production.

Một “quét hết bảng” có thể tiêu nhiều request units/IOPS; lập capacity budget và cân nhắc off-peak/replica nếu consistency yêu cầu cho phép.

## 45. Streaming merge-join và external sort

Giả sử hai file logical records đã chuẩn hóa và **sắp xếp theo full key**:

~~~text
Source: A, C, D, G
Target: A, B, D, F
~~~

Thuật toán merge:

1. Nếu hai keys bằng, so canonical value rồi tăng hai cursors.
2. Nếu source key nhỏ hơn, ghi MISSING và tăng source cursor.
3. Nếu target key nhỏ hơn, ghi EXTRA và tăng target cursor.
4. Tiếp tục cho tới hết cả hai streams.

Độ phức tạp so chính: `O(n+m)` khi hai streams đã sorted; chi phí sort phía trước là phần riêng. Không cần giữ toàn bộ records trong memory, chỉ buffers/checkpoints.

**Cần đảm bảo key ordering giống nhau ở cả hai hệ**, đặc biệt với collation, Unicode và binary encoding.

## 46. Bucketed reconciliation và incremental runs

Một kế hoạch:

~~~text
Bucket = hash(canonicalBusinessKey) mod 1024

For each bucket:
  record source cutoff and target applied watermark
  count rows and distinct keys
  digest sorted keys+values
  deep-diff mismatched buckets
  write immutable evidence
~~~

Sau full baseline, incremental runs có thể tập trung vào:

- Keys thay đổi từ CDC.
- Buckets có digest thay đổi.
- Mẫu ngẫu nhiên/stratified ở buckets từng match.
- Những tenant/status có rủi ro cao.

### Cảnh báo

Incremental reconciliation không thể tìm một **CDC event bị mất hoàn toàn** nếu không có periodic full/bucket sweep hoặc cross-source completeness checks. Nên thiết kế cả periodic full checks theo chi phí/rủi ro.

## 47. Metrics cho đối soát

| Metric | Mục đích |
| --- | --- |
| `source_count` / `target_count` | So số lượng theo bucket |
| `missing_keys_total` | Keys đáng lẽ phải có |
| `extra_keys_total` | Keys không mong đợi |
| `duplicate_keys_total` | Vi phạm uniqueness |
| `value_mismatch_total` | Cùng key, khác canonical value |
| `business_invariant_failures_total` | Vi phạm domain |
| `unresolved_conflicts_total` | Cần manual review |
| `source_cutoff_position` | Mốc đối soát |
| `target_applied_watermark` | Target đã catch-up chưa |
| `reconciliation_lag_seconds` | Độ chậm hoàn tất đối soát |
| `repaired_records_total` | Sửa có điều kiện |
| `repair_conflicts_total` | CAS không match |
| `scan_errors_total` | Lỗi/pagination gaps |

Không đưa từng `reservationId`/`userId` làm metric labels. Lưu affected keys ở **manifest/log store có kiểm soát**, metric labels chỉ có low-cardinality dimensions như service, entity type, severity, region và bucket class.

## 48. Phát hiện divergence đang tăng

Một đối soát lặp lại:

~~~text
10:00 mismatched keys = 5
10:10 mismatched keys = 20
10:20 mismatched keys = 200
10:30 mismatched keys = 2,000
~~~

Số lỗi tăng nhanh cho thấy pipeline đang drift. Nhưng muốn diễn giải, phải:

- So cùng scope và cutoff policy.
- Đảm bảo CDC đã bắt kịp.
- Phân biệt new discrepancies với unresolved backlog.
- Gắn deploy/version và source/target capacity changes.

Một alert hữu ích:

~~~text
Critical:
  business invariant violation > 0 in critical scope

Warning:
  validated mismatch rate rising for several windows

Info:
  target watermark still catching up after planned backfill
~~~

Ngưỡng cụ thể phụ thuộc business risk; lỗi tiền tệ hoặc tenant isolation có thể **zero-tolerance**, trong khi một projection eventually consistent có thể chấp nhận lag giới hạn.

## 49. Không sửa sai bằng blind overwrite

Một kết quả diff:

~~~text
Source reservation R101 version=7
Target reservation R101 version=9
Canonical values differ
~~~

Không thể mặc định “source thắng” nếu:

- Target đang nhận những writes hợp lệ mới hơn.
- Source đã ngừng là authority sau cutover.
- Version numbers đã được remap hoặc có hai writers.
- Sai lệch là do intentional transform.

### Trước khi repair

1. Xác định hiện tại ai là authority.
2. Kiểm affected key và source/target commit positions.
3. Phân loại missing/extra/value/stale/conflict.
4. Kiểm business effect của thao tác.
5. Ghi expected state/version.
6. Dùng conditional write/CAS hoặc unique insert.
7. Re-read và verify sau apply.
8. Ghi repair event, reason và idempotency key.

**Đối soát là việc phát hiện và giải thích sai lệch; repair là một thay đổi dữ liệu có rủi ro riêng, cần phê duyệt và guard.**

## 50. Repair manifest và audit

Ví dụ:

~~~json
{
  "reconciliationRunId": "recon-531-001",
  "watermark": "W1",
  "entityKey": "T1/R101",
  "discrepancy": "VALUE_MISMATCH",
  "sourceVersion": 7,
  "targetVersion": 6,
  "plannedAction": "CONDITIONAL_UPDATE",
  "expectedTargetVersion": 6,
  "newTargetVersion": 7,
  "approval": "domain-owner-required"
}
~~~

Không đặt PII hoặc secrets trong manifest nếu chỉ cần keys, field names, hash và references.

Một plan tốt có:

- Dry-run result.
- Approval/owner.
- Preconditions/expected version.
- Rate limit và batch policy.
- Stop conditions.
- Idempotency/repair ID.
- Rollback/compensation plan.
- Post-condition verification.

## 51. Conditional repair trên MongoDB

Giả sử target có `version=6` và cần cập nhật sang source version 7. Pseudocode:

~~~javascript
db.reservations.updateOne(
  { tenantId: "T1", reservationId: "R101", version: 6 },
  {
    $set: {
      status: "CONFIRMED",
      amountMinor: 125000,
      currency: "VND",
      version: 7,
      reconciliationId: "recon-531-001"
    }
  }
)
~~~

### Điều cần kiểm

- Match đúng **full business key** và version.
- Không dùng `upsert:true` khi target key tồn tại nhưng version khác.
- `matchedCount=0` là conflict/changed state, không phải lý do retry unconditional.
- Nếu target đã có version cao hơn, phải kiểm post-cutover writes và authority.
- Nếu cần atomic changes across multiple docs, xem transaction scope thực tế và business invariant.

Đây là ví dụ syntax/phương pháp, không phải lệnh được phép chạy trực tiếp vào production.

## 52. Conditional repair trên DynamoDB

Ý tưởng:

~~~text
UpdateItem
  Key = (pk, sk)
  ConditionExpression = version = :expected
  UpdateExpression =
    SET status = :status,
        amountMinor = :amount,
        version = :newVersion
~~~

Với missing record đã được xác nhận là cần tồn tại, dùng `PutItem` với `attribute_not_exists(pk)` theo full-key uniqueness semantics của table, thay vì overwrite item hiện tại.

### Chú ý

- `ConditionalCheckFailedException` có thể là conflict do concurrent write; phải re-read và đối chiếu, không xóa condition.
- API timeout có outcome không rõ; retry cần idempotency/recheck.
- Transactions có giới hạn về operations/items và semantics của dịch vụ.
- Streams/Global Tables có thể đưa repair write sang các consumers/regions; đảm bảo không nhân đôi side effects.

## 53. Sửa sai trên Cassandra/Redis/search

### Cassandra

- Tôn trọng timestamps/tombstones, TTL và read/write consistency.
- Dùng version/LWT nếu business contract yêu cầu CAS và engine hỗ trợ trong scope đó.
- Không tải old SSTable/ép timestamp chỉ để “ghi đè cho bằng nguồn”.
- Repair dữ liệu không thay thế anti-entropy repair của replicas.

### Redis

- Nếu chỉ là cache: ưu tiên invalidate/rebuild từ authority.
- Không restore snapshot cũ với `REPLACE` trên keys đang có giá trị mới đúng.
- Nếu Redis primary, cần compare full keys/types/TTL và bảo vệ atomic mutation.

### Search index

- Ưu tiên rebuild projection từ source + CDC catch-up.
- Có thể tạo index mới rồi alias cutover sau validation.
- Đo query-visible freshness và excluded-record rules.
- Không coi document count bằng source là acceptance nếu projection có fan-out/filter.

**Chọn repair method theo vai trò của đích và guarantee của storage engine**.

## 54. Sửa sai hàng loạt: canary và stop conditions

Một workflow:

~~~text
Approved discrepancy manifest
        |
        v
Canary 10–100 keys
        |
        v
Verify value + version + invariants + CDC
        |
        v
Bounded batches
        |
        v
Monitor p99, throttling, conflicts, lag
        |
        +→ If unsafe: PAUSE
        |
        v
Complete and final reconciliation
~~~

Số lượng canary/batch chỉ minh họa; capacity và risk profile quyết định mức thực tế.

### Dừng khi

- Conflict count cao bất thường.
- Query/DB latency vượt SLO và không thể throttle.
- Target watermark không tiến.
- Có invariant violation hoặc cross-tenant anomaly.
- Repaired records tạo duplicate external side effects.
- Manifest/approval không khớp scope.
- Mất ability to rollback/reconcile.

Không chạy lại một job sửa sai “cho chắc” nếu chưa biết nó idempotent.

## 55. Cổng quyết định cutover

Một **cutover gate** có thể quy định:

~~~yaml
cutoverGate:
  sourceSnapshot: "valid and reproducible"
  cdcContinuity: "no confirmed gaps"
  targetWatermark: "caught up to agreed W1"
  keySpace:
    criticalMissing: 0
    criticalExtra: 0
    duplicateBusinessKeys: 0
  values:
    criticalFieldsExactMatch: true
    noncriticalExceptions: "approved and bounded"
  business:
    inventoryViolations: 0
    ledgerReconciliationViolations: 0
    crossTenantLeakage: 0
  performance:
    peakReadWriteSlo: "passed"
  operations:
    rollbackRunbook: "approved"
    monitoringAndOncall: "ready"
  decision:
    domainOwner: "approval-required"
    incidentCommander: "approval-required"
~~~

**Mẫu này minh họa tiêu chí**, không phải ngưỡng mặc định. Định nghĩa “critical” và các ngoại lệ phải được công bố trước migration, không điều chỉnh hậu nghiệm chỉ để đạt green dashboard.

## 56. Không để success percentage che dữ liệu quan trọng

Giả sử:

~~~text
Total records: 100,000,000
Mismatch: 100
Match percentage = 99.9999%
~~~

Nghe rất tốt, nhưng 100 mismatches có thể là **100 giao dịch thanh toán bị sai tiền** hoặc dữ liệu của tenant khác. Không thể dựa chỉ vào tỷ lệ tổng.

### Phân tầng severity

| Scope | Acceptance approach |
| --- | --- |
| Payments, inventory commitments | Zero tolerance cho invariant violations |
| User privacy/tenant ownership | Zero tolerance cho leakage/unauthorized access |
| Critical booking state | Không còn missing/invalid records chưa xử lý |
| Historical analytics | Có thể có approved bounded exceptions |
| Cache/search eventual projections | Freshness/error budget và rebuild policy |

Chọn mức chất lượng theo **tác động nghiệp vụ**, không theo con số trung bình dễ trình bày.

## 57. Shadow reads và so hành vi truy vấn

Ngay cả khi record-level state match, query behavior có thể khác:

~~~text
Source query: available listings for dates X–Y
Target query: same business filter
~~~

Kết quả có thể lệch vì:

- Index/range/pagination semantics.
- Collation/string comparison.
- Timezone/date boundaries.
- Null/missing filters.
- Sort stability khi sort fields trùng.
- Eventual consistency trên read paths.
- Query bugs mới.

### Shadow read

Trả response từ authority cũ, đồng thời chạy target query không gây side effect rồi so **business result set** đã chuẩn hóa và SLO latency/cost.

Không đưa shadow reads vào destructive/write APIs nếu chưa có cơ chế bảo vệ; giới hạn tải và quyền truy cập.

## 58. Dual-run trước và sau cutover

Một tiến trình:

~~~text
Phase 1: Backfill historical state.
Phase 2: Apply CDC and reconcile W0.
Phase 3: Shadow reads + query behavior comparisons.
Phase 4: Freeze/coordinate final authority transition.
Phase 5: Cut over write authority and traffic.
Phase 6: Post-cutover reconciliation + rollback window.
Phase 7: Retire old source only after signoff.
~~~

### Chú ý thời điểm đổi authority

Sau cutover, source cũ có thể không còn nhận writes. Một discrepancy mới **không thể luôn sửa bằng cách copy source→target** vì target lúc ấy mới là authority. Phải ghi rõ **authority epoch** và những writes nào thuộc mỗi giai đoạn.

## 59. Rollback và failback không phải đảo chiều một flag

Nếu target đã nhận writes sau cutover, quay traffic về source cũ không đủ nếu source chưa có những writes đó.

~~~text
W1 cutover:
  target becomes authority

W2:
  target receives 1,000 legitimate bookings

Rollback:
  source needs safe replay/reconciliation of W1→W2
~~~

Nếu thiếu reverse CDC/dual replication hoặc export, rollback có thể gây mất dữ liệu. Một kế hoạch rollback phải:

- Biết source/target high-watermarks.
- Chuyển writes theo một authority protocol an toàn.
- Reconcile keys/values/invariants theo hướng ngược lại.
- Tránh split-brain và duplicate business effects.
- Có quiescence/traffic gating nếu cần.

**Rollback plan phải được test bằng writes sau cutover**, không chỉ bằng snapshot trước cutover.

## 60. Báo cáo đối soát mẫu

~~~text
Run ID: recon-531-20261114
Source authority: old-booking-store
Target: new-booking-store
Logical cutoff: W1, all CDC partitions confirmed
Scope: reservations, tenants T1..Tn

Source live entity count:      8,000,000
Target live entity count:      8,000,000
Unique business keys source:   8,000,000
Unique business keys target:   8,000,000

Matches:                       7,999,992
Missing keys:                          2
Extra keys:                            2
Value mismatches:                      4
Duplicate business keys:               0
Critical invariant violations:         1
Unresolved issues:                     9

Decision: NOT READY FOR CUTOVER
Owners: Booking domain and Data Platform
Next action: investigate + conditional repair + rerun
~~~

Ở ví dụ này counts bằng nhau và mismatch fraction rất nhỏ, nhưng **một invariant violation** vẫn đủ để chặn cutover theo policy zero-tolerance.

## 61. Runbook: source/target count lệch

1. Xác nhận đang đếm cùng logical entities, scope và filters.
2. Kiểm source snapshot position và target applied watermark.
3. Kiểm exact vs estimated count.
4. Chia bucket theo tenant/partition/time để khoanh vùng.
5. Kiểm TTL/deletes/soft-delete mapping.
6. Kiểm pagination/scan có bỏ trang hoặc đọc trùng không.
7. Kiểm CDC errors, DLQ, checkpoint/gap.
8. Xuất missing/extra/duplicate keys.
9. Reconcile canonical values và business invariants.
10. Chỉ sửa có condition sau khi xác định authority và nguyên nhân.

Không dùng lệnh “insert thêm records cho bằng tổng count” hoặc “xóa target records thừa” mà thiếu identity/evidence.

## 62. Runbook: counts bằng nhau nhưng values lệch

1. Đảm bảo cùng watermark và target đã catch-up.
2. Lấy representative mismatched keys từ manifest.
3. So canonical fields, type và schemaVersion.
4. Kiểm timezone, decimal, null/missing, string normalization.
5. Kiểm transform version/deploy changes.
6. Kiểm out-of-order events, stale replica reads, retry effects.
7. Kiểm expected source/target authority epoch.
8. Đánh giá business impact, nhất là tiền tệ/trạng thái.
9. Fix mapper/replay hoặc repair có CAS.
10. Chạy lại full bucket check và cross-record invariants.

Nếu mismatch do intentional schema transform đã được chứng minh, cập nhật **reconciliation contract có review/version**, không chỉ tắt checker.

## 63. Runbook: invariant nghiệp vụ sai dù hashes khớp

1. Xác nhận validators không đọc từ stale search/cache.
2. Kiểm chính business rule và nguồn authority.
3. Tìm affected entity groups/tenant/resource.
4. Đối soát inventory/payment/ledger/outbox references.
5. Xác định lỗi đã tồn tại từ source hay do migration.
6. Nếu source cũng sai, **không coi target match là pass**.
7. Dừng cutover hoặc cô lập critical operations.
8. Xây domain-approved compensation, không blind delete.
9. Re-validate sau sửa, kiểm side effects ngoài database.
10. Ghi nguyên nhân và regression tests cho mapper/validator.

**Đối soát thành công không phải “target giống source” khi source vốn đã sai luật nghiệp vụ**. Cần cả định nghĩa correctness độc lập.

## 64. Sai lầm phổ biến

| Sai lầm | Tác hại | Hướng đúng |
| --- | --- | --- |
| Chỉ so tổng count | Missing và extra triệt tiêu | So full keyspace và bucket counts |
| Dùng estimated count làm exact | Kết quả giả | Chọn count semantics đúng |
| So source/target lúc khác thời điểm | Mismatch giả | Common watermark/snapshot |
| Không kiểm pagination | Bỏ/trùng trang | Durable checkpoints và page verification |
| So JSON bytes | Field order/numeric format báo sai | Canonical logical schema |
| Chuyển money sang double | Mất precision | Integer minor units/BigDecimal |
| Normalize mọi string | Gộp IDs khác nhau | Domain-specific normalization |
| Coi null và missing luôn giống nhau | Mất thông tin | Explicit field contract |
| Bỏ qua TTL/deletes | Hồi sinh dữ liệu đã xóa hợp lệ | As-of retention/deletion rules |
| Không kiểm duplicates | Set che trùng lặp | Raw count + unique key detection |
| Hash mỗi bucket bằng XOR | Duplicates có thể triệt tiêu | Deterministic digests và counts |
| Chỉ sample | Bỏ lỗi hiếm nhưng critical | Full audit cho critical scopes |
| Chỉ so từng record | Bỏ ledger/inventory mismatch | Business invariants |
| CDC received là CDC applied | Target còn stale | Durable applied watermark |
| Tự repair bằng upsert | Ghi đè legitimate writes | CAS/conditional writes |
| Dùng snapshot cũ làm authority sau cutover | Lost updates | Authority epoch và conflict rules |
| Một tỷ lệ 99,99% match đủ để cutover | Critical error vẫn còn | Severity-based gates |
| Truyền records PII trong metrics/logs | Lộ dữ liệu | Secure manifests và hashes |
| Rollback bằng routing switch | Mất post-cutover writes | Reverse reconciliation/guard |
| Không đối soát sau cutover | Drift xuất hiện muộn | Continuous checks và signoff |

## 65. Bài tập thực hành

### Bài 1 — Count bằng nhau

Nguồn có A, B, C; đích có A, B, D. Cả hai có ba records. Tìm missing/extra và giải thích vì sao count không đủ.

**Gợi ý:** Missing=C, Extra=D.

### Bài 2 — Giá trị sai

Key T1/R2 có `amountMinor=80000` ở nguồn nhưng `75000` ở đích. Count và key match có đủ để pass không?

### Bài 3 — Composite key

Hai tenants đều có `reservationId=R100`. Viết full key và giải thích nguy cơ khi so chỉ theo reservation ID.

### Bài 4 — Distinct vs raw count

Nguồn có ba unique records; đích có A, B, B, D. Hãy tính raw count, distinct count, duplicates, missing và extra.

### Bài 5 — Bucket counts

Nguồn/đích tổng đều một triệu, nhưng tenant T1 lệch +5 và T2 lệch -5. Nên chia buckets và drill-down như thế nào?

### Bài 6 — Snapshot cutoff

Nguồn được đọc 10:00, đích 10:02, có 200 writes mới. Vì sao count delta 200 chưa chắc là migration error?

### Bài 7 — Watermark

CDC có ba partitions với offsets P0=100, P1=200, P2=300. Target áp tới P0=100, P1=199, P2=350. Target đã catch up toàn cutoff chưa?

**Gợi ý:** P1 chưa đủ.

### Bài 8 — Event vs commit time

Một event có eventTime trước 10:00 nhưng commit sau 10:05. Dựa vào eventTime để chốt snapshot có nguy cơ gì?

### Bài 9 — Canonical decimal

So `125.00` với `125.0` dưới BigDecimal numeric equality. Vì sao `BigDecimal.equals` có thể khác `compareTo`?

### Bài 10 — Money

Nguồn dùng minor units integer, đích dùng decimal major units. Hãy định nghĩa conversion và overflow/rounding policy.

### Bài 11 — Timestamp

`2026-11-14T03:30:00Z` và `2026-11-14T10:30:00+07:00` có cùng instant không? Cách so đúng?

### Bài 12 — Null/missing

Phân biệt `{"phone":null}`, `{}` và `{"phone":""}`. Khi nào có thể normalize thành cùng một trạng thái?

### Bài 13 — Unicode/case

Nếu normalize business key về lowercase và NFC, có thể tạo collision nào? Bạn cần test gì?

### Bài 14 — Arrays

Amenities `["wifi","pool"]` và `["pool","wifi"]` có tương đương không? So với một event history array thì sao?

### Bài 15 — Hash ambiguity

Vì sao nối `["ab","c"]` thành `"abc"` không an toàn? Đề xuất length-prefixed canonical serialization.

### Bài 16 — Bucket digest

Thiết kế bucket digest có counts và ordered key/value hashes. Vì sao XOR đơn thuần có thể che duplicate?

### Bài 17 — Sampling

Bạn lấy mẫu 1.000 trong 100 triệu bookings nhưng chỉ có một record bị sai tiền. Vì sao sample không đủ bảo đảm correctness?

### Bài 18 — TTL

Nguồn có voucher đã expired đúng policy, đích đã xóa. Đây có phải missing error không?

### Bài 19 — Cassandra tombstone

Nguồn dùng TTL/tombstones; một restored snapshot cũ hiển thị record đã xóa. Có nên ép target phục hồi record đó không?

### Bài 20 — DynamoDB

Một target table dùng composite key `(pk,sk)`. Vì sao so `pk` đơn lẻ hoặc dùng cached `ItemCount` có thể sai?

### Bài 21 — MongoDB/BSON

Nguồn lưu Decimal128 và BSON Date. Nêu các nguy cơ khi JSON stringify rồi hash mà không chuẩn hóa theo type.

### Bài 22 — Redis cache

Source có một triệu bookings, Redis chỉ cache 50.000 hot keys. Tại sao counts không bằng nhau vẫn có thể đúng?

### Bài 23 — Denormalized projection

Một booking source biến thành một summary, ba lines và hai guest views. Nêu logical invariants thay vì đòi count 1:1.

### Bài 24 — Business inventory

Một phòng capacity=1 nhưng target có hai confirmed allocations cùng ngày. Counts/field hashes từ một số records có thể đều khớp. Điều kiện nghiệp vụ nào cần chặn cutover?

### Bài 25 — Ledger

Tổng payment amount theo tenant/currency bằng nhau, nhưng một payment thiếu và một payment thừa có cùng số tiền. Cần đối soát thêm khóa gì?

### Bài 26 — Version

Nguồn R101 v7, đích R101 v9 sau cutover. Vì sao không được tự ghi đè đích bằng snapshot nguồn cũ?

### Bài 27 — Dual-write

Source write thành công còn target timeout. Làm sao xác định outcome và khôi phục đồng bộ an toàn?

### Bài 28 — Java

Chạy `BookingReconciliationDemo.java` và giải thích bốn categories MATCH, MISSING, EXTRA, DIFFERENT. Thêm tình huống duplicate key và quan sát xử lý của lab.

### Bài 29 — Java canonicalization

Mở rộng chương trình để so `customerRef`, local booking dates và version; nêu field nào nên loại khỏi canonical hash.

### Bài 30 — Streaming scale

Thiết kế external-sort + merge-join để đối soát một tỷ records mà không giữ toàn bộ keys trong RAM. Cần checkpoint gì?

### Bài 31 — Repair

Target có version 6, source expected version 7, worker muốn apply. Viết conditional update để tránh ghi đè một update v8 diễn ra đồng thời.

### Bài 32 — CDC

Target chỉ mới nhận event tới W0, trong khi cutoff phải là W1. Có nên đánh dấu missing/extra là permanent failures ngay không?

### Bài 33 — Cutover gate

99,9999% match nhưng có một double booking và một leak tenant. Có thể cutover nếu business owner chưa xác nhận không?

### Bài 34 — Rollback

Target nhận 1.000 writes sau cutover. Nếu chuyển traffic lại source cũ ngay, những gì có thể mất và cần chuẩn bị gì?

### Bài 35 — Bài tập tổng hợp

Hãy thiết kế đối soát cho hệ cho thuê chuyển MongoDB booking authority sang DynamoDB, đồng thời xây Redis cache và OpenSearch projection:

1. Xác định authority trước/sau cutover.
2. Lập mapping logical schema và full business keys.
3. Tạo snapshot + CDC watermark plan.
4. Đếm exact live entities theo tenant/status/partition.
5. Phát hiện missing/extra/duplicate keys.
6. So values với decimal/timezone/null/array semantics.
7. Sử dụng hash/bucket digests để tìm mismatches.
8. Kiểm tiền tệ, tồn kho, reference và lifecycle invariants.
9. Phân biệt cache/search projection với authority.
10. Đặt cutover gate và rollback/conditional repair plan.

**Gợi ý:** tạo một báo cáo có **watermark, count, key-level diff, canonical value diff, business invariants và approval**, không chỉ một tỷ lệ “migration success”.

## 66. Checklist vận hành đối soát nguồn/đích

1. Có biết database nào là authority tại từng giai đoạn migration không?
2. Source và target có cùng scope, entity type và full business keys không?
3. Có ghi snapshot/CDC commit positions, không chỉ timestamps không?
4. Target applied watermark đã bao phủ mọi partitions cần thiết chưa?
5. Count là exact hay estimate; có ghi rõ không?
6. Có so counts theo tenant, status, key range/time bucket không?
7. Có so distinct keys và phát hiện duplicates không?
8. Có tập missing/extra rõ ràng không?
9. Canonicalization contract đã được domain owner phê duyệt chưa?
10. Có kiểm integer/decimal precision, currency và overflow không?
11. Có chuẩn hóa instant/timezone nhưng giữ đúng local date semantics không?
12. Có phân biệt null/missing/empty/default không?
13. Có hiểu list/set ordering semantics không?
14. Có phát hiện Unicode/case normalization collisions không?
15. Hash có bao gồm đúng các business fields không?
16. Bucket digests có counts/key ordering và tránh collision do serialization không?
17. Có full check cho critical entities thay vì chỉ sample không?
18. TTL/soft delete/tombstone rules có được áp đúng không?
19. Có kiểm source-to-target CDC lag/freshness không?
20. Có detect gap, out-of-order và duplicate events không?
21. Có kiểm cross-record invariants như inventory và ledger không?
22. Có xác minh customer/tenant ownership để tránh cross-tenant leakage không?
23. Có shadow-read/query behavior tests ngoài record equality không?
24. Repair có version/CAS/unique key/idempotency không?
25. Có dry-run manifest và approval trước destructive changes không?
26. Có canary, throttling và stop conditions khi repair không?
27. Có report unresolved conflicts và người chịu trách nhiệm không?
28. Có SLO, cost/capacity và rollback readiness trong cutover gate không?
29. Có test rollback với post-cutover writes không?
30. Có lịch đối soát sau cutover trước khi retire source không?

## 67. Tổng kết

1. **Đối soát là một bài toán trạng thái logic có thời điểm**, không chỉ chạy count trên hai tables bất kỳ.
2. **Số dòng/count chỉ là tầng đầu**; missing, extra, duplicate keys có thể triệt tiêu nhau khiến tổng count vẫn đúng.
3. **Phải có full business key và cùng watermark** để tránh đọc nhầm tenant hoặc báo mismatch giả khi CDC chưa bắt kịp.
4. **Canonicalization quyết định ý nghĩa so sánh**: decimal, timezone, null/missing, Unicode, arrays, BSON types và schema transforms phải có hợp đồng rõ.
5. **Hashes/checksums giúp khoanh vùng nhanh nhưng không thay business verification** và phải được tạo từ serialization ổn định.
6. **NoSQL có data-model/consistency khác nhau**: MongoDB documents/BSON, Cassandra rows/tombstones, DynamoDB composite keys/Streams, Redis caches và search projections không thể áp chung count semantics.
7. **Business invariants là cổng cuối**: no double booking, số tiền/ledger, tenant isolation, status transitions và idempotency phải đúng kể cả khi records match.
8. **Dual-write, snapshot+CDC và cutover đều cần authority/watermark protocol**; không suy một ACK hay một timestamp thành hoàn tất migration.
9. **Repair phải có điều kiện**, không blind overwrite/upsert; version/CAS, manifest, dry-run, canary và approval là các lớp bảo vệ.
10. **Rollback cần reverse reconciliation** để bảo vệ writes hợp lệ phát sinh sau cutover; đổi DNS/connection string không tự quay lại state đúng.
11. **Đối soát phải để lại bằng chứng** về scope, thời điểm, số lượng, keys, giá trị, bất biến, ngoại lệ và quyết định owner.
12. **Hoàn thành migration chỉ khi hệ đích lưu và phục vụ đúng nghiệp vụ**, không phải khi hai con số trên dashboard tình cờ bằng nhau.

**Nguyên tắc thực hành:** trước khi tuyên bố migration NoSQL thành công, hãy chứng minh **“đang so sánh cùng thời điểm?”, “tập khóa có đầy đủ?”, “giá trị có đúng theo logical schema?”, “quy tắc nghiệp vụ có còn đúng?”, “nếu sai thì sửa có làm mất writes hợp lệ không?”**. Chỉ khi năm câu hỏi có bằng chứng và người chịu trách nhiệm phê duyệt, đối soát mới thực sự bảo vệ tính toàn vẹn dữ liệu.
