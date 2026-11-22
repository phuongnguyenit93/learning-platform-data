# Đánh giá giới hạn kích thước bản ghi, phân vùng và tác vụ

Khi lựa chọn một hệ quản trị NoSQL, câu hỏi “có mở rộng được không?” thường chưa đủ. Một dịch vụ có thể lưu hàng tỷ bản ghi nhưng vẫn thất bại khi **một bản ghi lớn vượt giới hạn tài liệu**, **một partition key trở thành điểm nóng**, hoặc **một tác vụ scan/transaction/batch xử lý quá nhiều dữ liệu trong một lần**. Ngược lại, một hệ có giới hạn cứng về item nhỏ vẫn có thể đáp ứng rất tốt khi mô hình dữ liệu tách hợp lý, có định danh ổn định, lưu blob bên ngoài và thiết kế thao tác theo access patterns.

Ví dụ, một hệ cho thuê lưu:

```text
listingId = L-1001

Listing:
    title, location, status
    amenities (array)
    description (rich text)
    photo metadata (array)
    review previews (array)
    availability by day (array)
```

Ban đầu document vài KB. Sau ba năm, ứng dụng thêm hàng nghìn reviews, thời gian khả dụng cho nhiều năm và lịch sử thay đổi trực tiếp vào cùng document. Ở một mức nào đó, việc cập nhật một status nhỏ có thể phải gửi/đọc document rất lớn, gây tăng latency, write amplification, contention và có thể chạm giới hạn kích thước của engine. Nếu gom toàn bộ booking của một căn hộ vào cùng partition, chỉ một listing nổi tiếng đã có thể gây hot key trong khi cả cluster còn nhiều tài nguyên rảnh.

Bài **Database No SQL → Đánh giá và lựa chọn → Đánh giá giới hạn kích thước bản ghi, phân vùng và tác vụ** hướng dẫn cách:

1. Lập bảng giới hạn **cứng** của bản ghi, partition và các thao tác theo sản phẩm/phiên bản.
2. Đặt các ngưỡng **mềm** về latency, throughput, kích thước truy vấn, chi phí và phục hồi dựa trên workload thực.
3. Dùng dữ liệu mẫu, công thức ước lượng và kiểm thử để quyết định mô hình dữ liệu, partition key, thao tác batch, query và đường lưu trữ thay thế.
4. Tạo **decision record** so sánh các NoSQL engine mà không nhầm “khả năng toàn cluster” với “khả năng một key/partition/tác vụ”.

> **Lưu ý về con số:** giới hạn NoSQL thay đổi theo edition, phiên bản, cấu hình, API, Region, loại bảng/tài nguyên và đặc tính managed/self-managed. Các con số sản phẩm trong bài là ví dụ tham chiếu thường gặp để minh họa cách kiểm, **không phải cam kết áp dụng cho triển khai hiện tại**. Trước quyết định production, xác minh tài liệu nhà cung cấp đúng phiên bản, quota thực của tài khoản và thực nghiệm trên chính workload.

---

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **kích thước bản ghi logic**, kích thước serialized trên wire, kích thước lưu trữ và kích thước sau index/replication.
- Phân biệt **hard limit**, **soft operating limit**, **service quota** và **business SLO**.
- Giải thích vì sao dữ liệu tổng thể nhỏ vẫn có thể quá tải một partition/hot key.
- Đánh giá document growth, array/map growth, field-name overhead, encryption/compression và schema evolution.
- Thiết kế kích thước partition theo data skew, access patterns, paging, compaction, repairs, backup và TTL.
- Đặt ngân sách cho **query, scan, batch, transaction, aggregation, CDC event, stream message, import/export và restore job**.
- Phân biệt số requests mỗi giây với số business operations hoàn tất đúng.
- Thiết kế giới hạn an toàn ở API, driver, database và workers mà không cắt mất dữ liệu một cách âm thầm.
- Xây thử nghiệm với phân bố P50/P95/P99/max và mẫu dữ liệu có extreme cases.
- Lập ma trận lựa chọn MongoDB, DynamoDB, Cassandra/ScyllaDB, Redis và hệ read model khác theo **giới hạn đã kiểm chứng**.
- Ghi quyết định thiết kế có phương án khi tăng trưởng vượt dự kiến.

## 2. Ba trục giới hạn khác nhau

```text
                  NoSQL capacity evaluation
                            |
       +--------------------+--------------------+
       |                    |                    |
  Record size          Partition/key size     Operation size
       |                    |                    |
   Document/item        Bytes and records       One read/write
   Fields/arrays        Hot key throughput      Query/scan page
   Value encoding       Routing/skew            Batch/transaction
   Codec/metadata       Repair/migration        Aggregation/CDC
```

**Giới hạn bản ghi (record):** một đối tượng riêng lẻ có thể mang bao nhiêu bytes và fields?

**Giới hạn phân vùng (partition):** một khóa/nhóm dữ liệu có thể lưu, đọc, ghi, sửa, di chuyển và phục hồi ở mức nào?

**Giới hạn tác vụ (operation/job):** một lệnh hoặc workflow có thể xử lý bao nhiêu bytes, items, partitions, thời gian, bộ nhớ và retries trước khi bị từ chối hoặc vi phạm SLO?

Một hệ có giới hạn document vài MB vẫn có thể xử lý dataset nhiều TB nếu được phân vùng phù hợp. Ngược lại, hàng nghìn documents nhỏ cùng tranh chấp một partition có thể gây nghẽn mặc dù từng document rất nhỏ.

## 3. Giới hạn cứng và giới hạn mềm

| Nhóm | Định nghĩa | Ví dụ |
| --- | --- | --- |
| **Hard limit** | Engine/API từ chối vượt ngưỡng | Maximum BSON document/item size |
| **Configurable limit** | Giới hạn có thể cấu hình trong biên nhà cung cấp | Max request body, memory limit |
| **Service quota** | Hạn mức tài khoản/tài nguyên/Region có thể tăng theo quy trình | Table throughput/account quotas |
| **Operational soft limit** | Mốc phải tránh để hệ vẫn đạt SLO và đủ recovery headroom | Partition quá lớn gây timeout/repair chậm |
| **Business limit** | Rule miền nghiệp vụ hoặc hợp đồng sản phẩm | Mỗi đơn tối đa N line items |
| **Safety limit** | Ranh giới để bảo toàn dữ liệu hoặc tránh overload | Max unverified replay batch |

Đừng chờ đến **hard limit** mới xử lý. Một document có thể dưới giới hạn cứng nhưng mỗi update mang 4 MB vẫn làm API p99 không đạt yêu cầu. Một partition hợp lệ về cú pháp có thể tốn hàng giờ để rebuild, vi phạm RTO.

## 4. Đánh giá giới hạn theo phạm vi, không chỉ theo sản phẩm

Một công nghệ có nhiều tầng:

```text
API gateway
  -> HTTP body / timeout
      -> Java serializer / driver
          -> DB wire protocol
              -> service API / DB server
                  -> collection/table
                      -> partition/shard/replica
                          -> disk/index/CDC
```

Giới hạn **thực tế của đường yêu cầu** thường là giới hạn nghiêm ngặt nhất trong chuỗi:

\[
L_{\text{effective}} \le \min(L_{\text{gateway}},L_{\text{driver}},L_{\text{DB API}},L_{\text{business}})
\]

Công thức chỉ xét **cùng một đại lượng**, ví dụ payload bytes; không được lấy min giữa bytes và requests/s. Thêm thời gian/chính sách/authorization để có tập điều kiện đầy đủ.

Ví dụ database cho phép document lớn nhưng API gateway từ chối body nhỏ hơn: request vẫn không thể thành công. Upload qua object storage với metadata trong NoSQL có thể là kiến trúc hợp lý hơn.

## 5. Kích thước logic, wire và vật lý khác nhau

Với một item:

```text
Logical content:
    1,000 characters of description

Serialized:
    field names + type tags + value bytes + lengths

Network:
    protocol headers + retries + TLS overhead

Stored:
    internal metadata + indexes + compression/encryption

Replicated:
    copies across nodes/failure domains
```

Không dùng:

```java
description.length()
```

làm kích thước UTF-8 payload. `String.length()` trong Java đếm **UTF-16 code units**, khác với bytes UTF-8 và cũng khác số code points.

Ví dụ:

```text
"A"       -> 1 UTF-8 byte
"á"       -> thường 2 UTF-8 bytes khi NFC
"😀"      -> 4 UTF-8 bytes, Java String.length() = 2
```

Một trường tên dài lặp ở hàng triệu items có thể ảnh hưởng kích thước và chi phí; một bản ghi có nhiều fields nhỏ không nhất thiết rẻ như cộng giá trị text đơn thuần.

## 6. Công thức kích thước bản ghi gần đúng

Đối với object có \(n\) fields:

\[
S_{\text{serialized}} \approx
S_{\text{envelope}} +
\sum_{i=1}^{n}
\big(S_{\text{fieldName},i}
+ S_{\text{type},i}
+ S_{\text{value},i}
+ S_{\text{length/metadata},i}\big)
\]

Các thành phần phụ thuộc codec và protocol:

- Encoding UTF-8 của key/value.
- BSON type tags, element names, document length và terminators.
- JSON punctuation/escaping.
- DynamoDB AttributeValue representations và item size accounting.
- CQL binary protocol và collection/value framing.
- Redis key/value encoding và internal data structures.
- Client-side encryption/nonces/authentication tags.
- Compression/encryption envelope.
- Internal index and storage metadata.

**Đo bằng serializer thật** trên dữ liệu đại diện khi cần chính xác. Không đánh đồng HTTP JSON size với BSON document size hoặc DynamoDB item-size accounting.

## 7. Lập phân bố thay vì chỉ đo trung bình

Đừng thiết kế theo:

```text
Average document = 8 KB.
```

Nên đo:

| Cohort | Số lượng | P50 | P95 | P99 | Max | Tăng trưởng |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| New listings | ... | ... | ... | ... | ... | ... |
| Old listings | ... | ... | ... | ... | ... | ... |
| Premium listing | ... | ... | ... | ... | ... | ... |
| Imported data | ... | ... | ... | ... | ... | ... |
| One listing with many photos | ... | ... | ... | ... | ... | ... |

P99 của kích thước bản ghi **không thay thế max**, vì hard limit là ranh giới cho từng object. Nếu có một request 2% hiếm gặp cực lớn, nó có thể làm lỗi nghiệp vụ lớn dù average nhỏ.

Báo cả:

- **Current** distributions.
- Growth per entity/tenant.
- Worst-case legally allowed input.
- Historical outliers.
- Future feature expansion.
- Payload value count và field count.
- Max depth/nesting.
- Data imported from external partners.

## 8. Document tăng trưởng không giới hạn là nợ kiến trúc

Mô hình:

```json
{
  "listingId": "L-1001",
  "status": "ACTIVE",
  "photos": [ "... thousands of entries ..." ],
  "reviews": [ "... millions of entries over time ..." ]
}
```

Có ba vấn đề:

1. **Kích thước:** bản ghi có thể vượt hard limit.
2. **Concurrency:** nhiều người review cùng update một aggregate.
3. **Access cost:** lấy status lại phải duyệt/serialize một object rất lớn nếu không có projection/partial read hiệu quả.

Giải pháp thường cân nhắc:

```text
listings:
    identity + current metadata + summary counters

listing_photos:
    listingId + photoId + metadata

listing_reviews:
    listingId + reviewId + rating + text

listing_availability:
    listingId + bounded time bucket
```

Khi tách, phải đánh giá **bất biến xuyên records**, read amplification và cập nhật summaries. Tách mọi field nhỏ cũng không tối ưu nếu thao tác cần atomic một aggregate cục bộ.

## 9. Khi nào embed và khi nào reference?

**Embed** hữu ích khi:

- Các fields luôn được đọc cùng nhau.
- Kích thước có bound rõ.
- Cần atomic update trong cùng object.
- Không có fan-out/array growth lớn.
- Quan hệ có cardinality thấp và ổn định.

**Reference/tách collection/table** hữu ích khi:

- Quan hệ one-to-many tăng vô hạn.
- Child records có lifecycle và TTL riêng.
- Truy vấn/page riêng.
- Child có hot writes cạnh tranh.
- Media/blob quá lớn.
- Có nhu cầu partition/retention độc lập.

Không chọn embed/reference chỉ theo hard size limit; đánh giá cả atomicity, query count, cache, read/write amplification và RTO.

## 10. Blob, ảnh và file media không nên mặc định nằm trong record

Thực tế phổ biến:

```text
Object storage:
    image/video/file bytes

NoSQL:
    object key, content type, length,
    checksum, ownership, state, reference
```

Lợi ích:

- Không để record vượt ngưỡng.
- Upload/download phù hợp streaming và CDN.
- Có lifecycle/retention độc lập.
- Index metadata không bị binary payload chi phối.

Rủi ro:

- Ghi DB thành công nhưng upload object thất bại, hoặc ngược lại.
- Xóa DB record nhưng object chưa được xóa.
- Private URL/ACL sai gây lộ dữ liệu.
- Signed URL expiration và idempotency.
- Backups phải bao gồm cả DB và object store.
- Integrity checksum có thể cần bảo đảm xuyên hai systems.

Cần workflow upload-state + reconciliation và authorization của object store. **Tách blob không làm dữ liệu liên hệ tự nhiên trở thành atomic**.

## 11. Giới hạn trường, nesting và collection types

Ngoài tổng bytes, cần kiểm:

- Số fields/attributes.
- Tên field có ký tự hạn chế không?
- Độ sâu nesting.
- Kích thước một field/value.
- Độ dài key/partition key.
- Độ dài arrays/maps/sets.
- Index entry lengths.
- Cấp số của các nested updates.
- Empty/null/missing semantics.
- Schema validation thresholds.

Một object chưa chạm giới hạn bytes có thể vướng **naming, nesting, key length, expression size hoặc API constraints**. Dùng data generators ở edge cases, không chỉ sample bình thường.

## 12. Encryption và compression làm size thay đổi

Một field mã hóa có thể chứa:

```text
nonce + authentication tag + key/version metadata + ciphertext
```

so với plaintext, payload thường tăng kích thước một phần. Nếu base64 để đưa binary qua JSON, kích thước cũng tăng.

Compression có thể làm payload nhỏ hơn nhưng:

- Tỷ lệ nén phụ thuộc dữ liệu.
- Encrypted ciphertext thường khó nén.
- CPU/GC tăng.
- Random access một field có thể đắt hơn.
- Debug/restore cần codec version.
- Không được dựa vào tỷ lệ nén tốt nhất để vượt hard limit.

**Quy định ngân sách trên kích thước mà engine/API thực sự kiểm**, không trên plaintext hoặc compressed size theo suy đoán.

## 13. Kích thước record và write amplification

Một document lưu 1 MB, mỗi lần đổi `status` vài bytes:

```text
logical change: 5 bytes
wire/DB/internal write: could be substantially larger
```

Tùy engine và update operator, có thể tối ưu partial updates nhưng vẫn phải xét:

- Replication log/change stream.
- Index maintenance.
- Storage rewrite/WAL.
- Cache invalidation.
- Backup size.
- Conflict/concurrency.
- Compression CPU.
- Network retries.

Không mặc định mọi engine ghi lại toàn document cho một patch; cũng không mặc định mọi patch luôn rẻ. Đo **bytes written and I/O per logical mutation**.

## 14. Kích thước record và read amplification

Công thức gần đúng:

\[
A_{\mathrm{read}} =
\frac{\text{bytes examined or fetched internally}}
{\text{bytes actually needed by user}}
\]

Nếu API chỉ cần `listing.status`, nhưng query fetch/decode một document rất lớn, amplification có thể cao.

Cần kiểm:

- Projection support.
- Covering index hoặc access-pattern table.
- Partial field retrieval.
- Number of network round trips.
- Storage pages/SSTables touched.
- JSON/BSON decode and object allocation.
- Serializer backpressure.

**Trả ít fields** có thể giảm network payload nhưng không nhất thiết giảm mọi storage I/O; phải đo theo engine.

## 15. Định nghĩa “partition” theo từng công nghệ

Từ “partition” thường chỉ những thực thể khác nhau:

| Công nghệ | Khái niệm liên quan | Điểm cần nhớ |
| --- | --- | --- |
| MongoDB sharded cluster | Shard key range/hashed chunks, shard placement | Chunk không phải một document; shard key và jumbo ranges ảnh hưởng migration |
| DynamoDB | Partition key và các physical partitions nội bộ | Một logical key nóng có thể chạm giới hạn localized dù bảng tổng rộng |
| Cassandra/ScyllaDB | CQL partition gồm partition key và nhiều clustering rows | Có thể tạo partition cực lớn dù từng row nhỏ |
| Redis Cluster | Hash slots, keys và slot ownership | Một key lớn/hot không tự được tách nhờ có nhiều slots |
| Search engine | Index shards/segments | Một query fan-out có thể đụng nhiều shards |
| Graph store | Supernode/adjacency fanout và placement | Một node cực nhiều cạnh có thể tạo truy vấn/hotspot |

Không lấy ngưỡng “partition size” của Cassandra rồi áp cho DynamoDB physical partition hay MongoDB chunk. **Phải định nghĩa đúng đơn vị kỹ thuật đang đo**.

## 16. Giới hạn dung lượng toàn cluster khác giới hạn một partition

Giả sử:

```text
Cluster capacity:      10 TB
Tenant T1 data:       500 GB
Tenant T2 data:       500 GB
Hot key K of T1:      100 GB worth of related rows
```

Dù tổng chỉ 1 TB, workload quanh K có thể:

- Bị dồn vào một physical partition/range.
- Gây p99 cao.
- Tốn hàng giờ stream/repair.
- Vượt memory/paging budget.
- Làm một token range/shard mất cân bằng.
- Gây failed/timeout queries trên K.

**Khả năng thêm node không tự tách một logical partition key** nếu data model đặt mọi row dưới cùng key.

## 17. Partition size không chỉ tính bytes

Đánh giá ít nhất:

```text
partition bytes
row/item count
key cardinality
per-key read/write throughput
number of clients/concurrent writers
partition time-span
update/delete rate
tombstone count
read fan-out and result-page count
repair/stream/recovery time
```

Một partition vài MB nhưng có hàng nghìn conditional updates/s trên cùng item có thể nóng hơn một partition lớn chỉ đọc hiếm. “Large” và “hot” liên quan nhưng không đồng nghĩa.

## 18. Công thức ước lượng partition growth

Với thiết kế time-bucket:

\[
S_{\mathrm{partition}}\approx
N_{\mathrm{eventsPerBucket}}\times S_{\mathrm{eventAvg}}
+ S_{\mathrm{partitionOverhead}}
\]

Ví dụ:

```text
tenant T1:
    30,000 events/day
    average event item 2 KiB
    monthly bucket with 30 days
```

Ước lượng phần payload:

\[
30000\times 30\times 2\,\mathrm{KiB}
= 1\,800\,000\,\mathrm{KiB}
\approx 1.72\,\mathrm{GiB}
\]

Chưa kể metadata và storage amplification.

Nếu 1 tháng/quản lý entity tạo partition quá lớn so với **ngưỡng vận hành đã chứng minh**, có thể dùng daily/hourly buckets hoặc thêm sub-buckets, với điều kiện query path được thiết kế lại.

Đừng chọn bucket size chỉ từ trung bình: ngày cao điểm có thể gấp 20 lần.

## 19. Bucket size có trade-off với read fan-out

Chia theo ngày:

```text
partitionKey = tenantId + day
```

giúp giới hạn size và writes, nhưng query:

```text
Get last 12 months of history
```

có thể phải chạm ~365 partitions thay vì 12.

Do đó có trade-off:

- Bucket nhỏ → giảm large partitions/hotspots; tăng fan-out/metadata.
- Bucket lớn → giảm fan-out; tăng size, contention, restore time.
- Hash sub-buckets → phân tán writes; query một entity phải đọc nhiều buckets.
- Hierarchical index → cần thêm summary/access patterns.
- Different read models → tăng storage và sync complexity.

**Chọn bucket theo queries**, không chỉ theo storage.

## 20. Hot key và hot partition phải đo ở P99/key

Một dataset có:

```text
1 million partition keys.
Average = 20 RPS/key.
One key = 50,000 RPS.
```

Average không mô tả key nóng.

Cần thống kê:

- RPS/WPS per logical key hoặc anonymized buckets.
- P50/P95/P99/max trên distribution của keys.
- Hot-key concentration, top-N share.
- Per-key mutation contention.
- Retry/throttle rate.
- In-flight operations.
- Physical partition placement khi telemetry có.
- Per-tenant concurrency/fairness.
- Skew theo giờ cao điểm.

Không cho raw PII hoặc tenant IDs vào labels có cardinality vô hạn; dùng aggregation/sampling có kiểm soát.

## 21. Chỉ số độ lệch và nguy cơ noisy neighbor

Một chỉ số đơn giản:

\[
H_{k} =
\frac{\text{ops/s của key nóng nhất}}
{\text{ops/s trung bình theo key đang hoạt động}}
\]

Nếu \(H_k\gg1\), key distribution có skew; nhưng không có ngưỡng phổ quát cho mọi engine.

Cần kiểm thêm:

- Physical placement: hai logical keys nóng có nằm trên cùng resource không?
- Peak burst duration.
- CPU/IO/transaction lock.
- Tenant budget, quota và scheduler fairness.
- Capacity reservation cho workloads quan trọng.
- Autothrottle và backpressure.
- Failover sau khi một node/Region giảm capacity.

Một noisy tenant có thể đẩy latency của người khác lên cao dù tổng throughput toàn cluster chưa chạm quota.

## 22. Không dùng hash partition key mà không hiểu truy vấn

Giả sử truy vấn thường xuyên:

```text
Find all bookings of listing L1 between dates D1 and D2.
```

Một key tự nhiên:

```text
listingId + month
```

cho phép range-oriented access nhưng có thể nóng với listing nổi tiếng.

Thêm hash suffix:

```text
listingId + month + randomBucket
```

phân tán writes nhưng làm query cần fan-out nhiều buckets. Nếu một booking phải bảo đảm không double-book date, phân tán keys có thể **phá atomicity boundary** và cần một cơ chế reservation/slot-owner khác.

Các câu hỏi:

1. Bất biến nào phải được bảo vệ trên cùng key/partition?
2. Query chủ yếu point lookup hay range scan?
3. Tỷ lệ writes/reads theo hot entities?
4. Có thể dùng hash deterministic theo stable bookingId không?
5. Có need global sorting/aggregation?
6. Có thể dùng materialized read model với contract eventual không?

**Không giải hot key bằng random sharding nếu hành động đó phá correctness.**

## 23. Large partitions ảnh hưởng repair/backup/restore

Một partition cực lớn có thể gây:

- Streaming/repair kéo dài.
- Snapshot/backup chunk skew.
- Disk temp space pressure.
- Compaction/tombstone overhead.
- Query timeout hoặc OOM.
- Unbalanced token/shard movement.
- Longer mean time to recover.
- Retry với partial results/paging.
- Thời gian range reconciliation không đạt RTO.

Lập bảng:

| Đơn vị | Kích thước | Thời gian cần xử lý | Rủi ro |
| --- | --- | --- | --- |
| Median partition | ... | ... | ... |
| P99 partition | ... | ... | ... |
| Max partition | ... | ... | ... |
| Single hottest partition | ... | ... | ... |

Đừng chỉ hỏi “hệ cho phép lưu partition 5GB không?”. Cần hỏi “repair, failover, range query, backup và restore partition ấy trong thời gian nào?”.

## 24. Giới hạn tác vụ là một vector đa chiều

Một operation có ít nhất:

```text
maximum request bytes
maximum response bytes
maximum items/actions
maximum partitions touched
maximum execution time
maximum read/write capacity
maximum memory/temp/disk budget
maximum retries
maximum concurrency
maximum consistency/transaction scope
```

Ví dụ một batch 500 items có thể:

- Vượt API max actions.
- Vượt aggregate payload limit.
- Vượt transaction scope.
- Chứa một item riêng lẻ vượt hard limit.
- Chạm nhiều hot partitions.
- Timeout dù không vượt hạn mức bytes.
- Tạo partial success cần retry phần chưa xử lý.

**Không có “batch size” tối ưu chỉ từ một con số items**.

## 25. Sự khác biệt giữa một request và một nghiệp vụ

Ví dụ nghiệp vụ tạo đơn:

```text
Create order
Reserve inventory
Write payment intent
Append outbox event
```

Một **business operation** có thể cần nhiều DB commands. Nếu cố nhét tất cả vào một database transaction, kiểm:

- Engine hỗ trợ atomicity của những records/partitions đó không?
- Có giới hạn số actions, bytes hoặc thời gian không?
- Thao tác có cần external payment provider không?
- Có cách dùng saga/outbox hay aggregate redesign không?
- Retry/timeout outcome có idempotent không?

Một API báo `200` cho request tạo đơn không tự chứng minh cả bốn effects đã commit theo contract.

## 26. Single-record atomicity không bằng cross-partition transaction

NoSQL thường tối ưu thao tác trên một document/item/partition, nhưng phạm vi giao dịch khác nhau theo engine.

Một lựa chọn:

```text
One giant document:
    simpler atomic update
    higher size/contention

Many documents:
    better growth and query structure
    possible cross-document invariant/transaction cost
```

Cần cân bằng:

- Kích thước bản ghi.
- Transaction scope.
- Write conflict.
- Read paths.
- Data consistency.
- Stream/outbox behavior.
- Failure recovery.
- Cost.

Không chọn “một document cực lớn để có atomicity” nếu sớm đụng hard limit, và không tách mà bỏ qua invariant đang được atomic update bảo vệ.

## 27. Query/scan giới hạn page và result set

Các thao tác `Query`/`Scan` thường có:

- Pagination.
- Response-size cap.
- Per-page internal work cap.
- Timeout.
- Read capacity cost.
- Token/cursor validity.
- Consistency scope.
- Sort/fan-out constraints.

Một client gọi một lần:

```text
query(limit=1000)
```

không nhất thiết nhận 1.000 logical results. Có thể:

- API giới hạn bytes trước 1.000 results.
- Filter loại phần lớn entries.
- Có continuation token.
- Một page không chứa đủ records.
- Cursor bị hết hạn.
- Tổng kết quả thay đổi nếu concurrent writes.

**Một bài kiểm phải tiếp tục cursor hợp lệ đến đúng termination condition**, không suy `items.length < limit` nghĩa hết toàn bộ dữ liệu nếu API cung cấp token còn.

## 28. Pagination không được làm mất kết quả

Một anti-pattern:

```java
var response = query(...);
return response.items(); // ignore continuation token
```

Trên data nhỏ test có thể pass; trên production nhiều partitions, chỉ trả page đầu.

Một contract:

```text
Expected logical key set at snapshot W.
Read all pages using supported cursor.
Deduplicate only under defined semantics.
Preserve sort tie-breaker.
Verify no missing/extra keys.
```

Với cursor ngoài snapshot consistency, concurrent inserts/deletes có thể làm việc duyệt không bằng một cut. Nếu yêu cầu exact export, cần snapshot/frozen data hoặc cơ chế phiên bản phù hợp.

## 29. Batch operations: giảm round trips nhưng tăng blast radius

Lợi ích:

- Giảm network overhead.
- Tăng throughput theo workload.
- Có thể tận dụng engine batch API.

Rủi ro:

- Payload quá lớn.
- Một item invalid làm toàn bộ request thất bại.
- Partial success.
- Hot key/hot partition.
- Retries nhân đôi effects.
- Driver buffer memory tăng.
- Transaction locks và contention tăng.
- Failure domain lớn hơn.
- Khó phân loại UNKNOWN sau timeout.

Không tự coi một batch là transaction atomic. **Batch API và transaction API có semantics khác nhau.**

## 30. Bounded batching dựa trên số items và bytes

Một phương pháp:

```text
Take next item.
Compute serialized-size estimate or exact encoded size.
If adding item would exceed item-count cap or byte cap:
    flush current batch.
Start next batch.
```

Có thể còn:

- Max transaction actions.
- Max single item size.
- Per-key grouping.
- Source-order requirements.
- Rate budget.
- Deadline.
- Batch retry budget.
- Maximum in-flight batches.

Với estimate, giữ safety headroom vì service size accounting khác JSON wire size. Khi cần chính xác phải dùng encoder đúng API/schema.

## 31. Transaction size và time budget

Một transaction rất lớn có thể:

- Vượt giới hạn request/actions/bytes.
- Giữ locks/versions lâu.
- Tăng conflict retries.
- Tiêu tốn memory.
- Gây timeout/UNKNOWN commit.
- Tăng replication overhead.
- Giới hạn khả năng retry theo idempotency.

Ví dụ nghiệp vụ nhập 1 triệu events, không nên cố biến cả triệu bản ghi thành **một transaction xuyên hệ**. Thường cần:

```text
Chunked import
Durable checkpoint
Idempotent chunks
Per-chunk verification
Final reconciliation
Atomic publication of generation pointer when safe
```

Tuy nhiên chunking **không tự làm toàn workflow atomic**; cần cơ chế chỉ công bố dữ liệu khi mọi chunks hợp lệ.

## 32. Aggregation và memory/temporary disk

Một aggregation:

```text
Group 500 million events by a high-cardinality key.
Sort all groups.
Return top 100.
```

Có thể chỉ trả 100 results nhưng phải xử lý lượng dữ liệu lớn.

Chi phí:

- Scan nhiều partitions.
- In-memory hash table/sort.
- Spill to disk nếu engine hỗ trợ.
- Network shuffle giữa shards.
- Intermediate result size.
- Query timeout.
- Resource throttling.

Cần đo `examined`, `processed`, `spilled`, `intermediate bytes`, `fan-out` và `peak memory`, không chỉ response bytes.

Một global aggregation đúng nhưng mất hàng giờ không nên đặt trực tiếp trên synchronous API nếu SLO vài trăm ms.

## 33. CDC event cũng là một dạng payload có giới hạn

Một mutation có thể phát sinh:

```text
source log entry
CDC envelope
schema metadata
before/after image
broker message
consumer event object
read-model update
```

Nếu record lớn:

- CDC message có thể vượt broker/connector limits.
- Consumer cần buffer lớn.
- Retry/replay tốn network.
- Full-document lookup có thể chậm.
- Log retention có thể hết trước khi consumer bắt kịp.
- Outbox entry có thể vượt transaction/payload limits.
- Một event bị kẹt làm lag tăng.

Cần thiết kế:
- Reference tới blob hoặc chunk protocol có integrity.
- Versioned event schemas.
- Bounded envelope.
- End-to-end idempotency.
- Checkpoint và gap handling.
- Delete/tombstone semantics.
- Backfill path khi event quá lớn/stream gap.

**Database chấp nhận record không có nghĩa downstream messaging pipeline chấp nhận event tương ứng**.

## 34. Backup/restore, export/import cũng là tác vụ cần giới hạn

Đánh giá:

```text
backup unit/chunk size
parallelism
I/O and network bandwidth
disk headroom
restore concurrency
checkpoint and resumption
data encryption
snapshot consistency
replay/log retention
verification time
```

Một cluster có thể lưu 50TB nhưng nếu chỉ restore được 1TB/giờ thì **RTO 30 phút** không thể đạt khi phải phục hồi toàn bộ 50TB từ snapshot mà không có phương án khác.

Cần đo restore trên **dữ liệu và topology tương đương**, bao gồm:
- Index rebuild.
- Replication catch-up.
- TTL/tombstone.
- Schema/roles/KMS.
- CDC replay.
- Business reconciliation.
- Warm-up và user-facing SLO.

“Backup job succeeded” không chứng minh “recovery objective met”.

## 35. Ước lượng time budget cho một tác vụ

Với \(N\) items và tốc độ xử lý ổn định \(r\) items/s:

\[
T_{\mathrm{minimum}}\approx \frac{N}{r}
\]

Ví dụ:

```text
500,000 items
2,000 verified items/s
```

Thời gian xử lý thuần tối thiểu:

\[
T \approx 250s \approx 4.17\text{ phút}
\]

Chưa tính:
- Discovery/pagination.
- DB throttling.
- Retries/duplicates.
- Network and queueing.
- Checkpoint overhead.
- Verification.
- Contention with production traffic.
- Failure/recovery.

Nếu task timeout 60 giây, cần chunking, worker orchestration, backpressure hoặc cơ chế asynchronous job, không chỉ tăng max timeout vô hạn.

## 36. Giới hạn tác vụ phải bảo vệ khỏi quá tải

Một API:

```text
GET /reports?tenantId=T1&from=2000&to=2026
```

có thể vô tình yêu cầu nhiều năm dữ liệu và chạm hàng triệu partitions. Giới hạn:

- Time-range window.
- Max result count/payload bytes.
- Concurrency per tenant.
- Cursor pagination.
- Scanned bytes/estimated cost.
- Deadline.
- Read capacity budget.
- Async export cho reports lớn.
- Abort/cancel semantics.
- Partial result contract rõ.

Không âm thầm trả page đầu rồi đánh dấu “report complete”. Nếu cần kết quả toàn bộ, chuyển sang async export có manifest/coverage.
## 37. Bảng định hướng theo các NoSQL engine

Bảng sau chỉ để nhận diện **nơi phải tra cứu và đo**, không phải danh mục giới hạn cuối cùng:

| Hệ | Giới hạn bản ghi cần hỏi | Rủi ro partition/key | Giới hạn tác vụ thường quan trọng |
| --- | --- | --- | --- |
| **MongoDB** | Kích thước BSON document; nesting, index keys | Shard key skew, unbounded arrays, jumbo data ranges | Aggregation memory/result docs, bulk writes, transaction time/resource, cursor |
| **DynamoDB** | Item size, key/attribute sizing | Hot partition key, physical partition capacity, GSI hot keys | Query/Scan page, BatchGet/BatchWrite, Transactions, throttling/quotas |
| **Cassandra/ScyllaDB** | Cell/value sizes và encoding | CQL partition chứa quá nhiều clustering rows/tombstones | Large read partitions, range scans, LWT, batch, repair/compaction |
| **Redis** | Key/value/aggregate data type, memory | Hot single key, hash slot skew | Multi-key commands, Lua/Functions blocking time, pipelines, Streams trimming |
| **Search engines** | Document/source size và index mapping | Shard skew, high-cardinality fields | Query fan-out, result windows, aggregations, reindex, scroll/export |
| **Graph databases** | Property payload và adjacency | Supernodes/high-degree vertices | Traversal breadth/depth, path explosion, transaction size |

Cùng một công nghệ có nhiều chế độ triển khai. Không dựa vào con số từ một tài liệu phiên bản cũ rồi ghi thành SLO mặc định.

## 38. MongoDB: giới hạn BSON document

Một mốc thường gặp trong MongoDB là **giới hạn BSON document khoảng 16 MiB** cho một document thông thường. Cần xác minh giới hạn và các ngoại lệ theo bản triển khai, không lấy kích thước JSON gửi qua HTTP để so trực tiếp.

Ví dụ:

```javascript
// Chỉ đo BSON size của một document trên mongosh.
// Không phải lệnh thay đổi dữ liệu.
const doc = db.listings.findOne({ listingId: "L-1001" });
if (doc) {
  print(Object.bsonsize(doc));
}
```

Trong mongosh, `Object.bsonsize` có thể hữu ích để quan sát dữ liệu mẫu, nhưng không chứng minh tất cả documents dưới giới hạn. Cần scan/aggregate distribution có ngân sách và chọn các bản ghi lớn nhất theo phương pháp phù hợp.

Hỏi:

- BSON bytes thực đo P50/P99/max bao nhiêu?
- Array/embedded document nào tăng không giới hạn?
- Có nguy cơ một update đưa document vượt hard limit?
- Index keys/nested fields có giới hạn riêng không?
- `updateOne`/`findOneAndUpdate` có cạnh tranh trên hot document không?
- Thay schema có làm codec nhận object lớn hơn không?
- Dữ liệu lịch sử có cần tách theo thời gian không?

**GridFS** là một lựa chọn cho file lớn trong hệ sinh thái MongoDB, nhưng object storage có thể phù hợp hơn tùy kiến trúc, chi phí, security và backup requirements.

## 39. MongoDB: document dưới hard limit vẫn có thể nóng

Mô hình:

```json
{
  "listingId": "L1",
  "availableUnits": 1,
  "reservations": [
    "... growing records ..."
  ]
}
```

Mọi booking đều cập nhật cùng document. Mặc dù document chỉ vài MB, concurrency có thể:

- Tạo write conflicts.
- Tăng retry/lock contention.
- Tăng oplog/change stream traffic.
- Làm reads/serialization tốn kém.
- Gây hotspot và p99 cao.

Có thể chuyển reservations thành records riêng cùng business operation ID và giữ một counter/slot owner có conditional update.

Nhưng **không được tách mà làm mất bất biến không đặt vượt số lượng còn lại**. Nếu booking trải nhiều documents, dùng transaction/protocol phù hợp hoặc một model đơn-key cho quyết định availability và ledger để đối soát.

## 40. MongoDB: shard key và vùng dữ liệu khó di chuyển

Một shard key:

```text
tenantId
```

với một tenant lớn có thể phân bố kém hoặc tạo workload nóng. Chọn:

```text
(tenantId, hashed entityId)
```

có thể tăng phân tán nhưng làm range queries theo tenant phức tạp hơn.

Khi so sánh ứng viên shard key, xem:

- Cardinality và phân bố.
- Monotonic insertion/hot trailing ranges.
- Targeted query vs scatter-gather.
- Unique constraint scope.
- Chunk/data range sizes.
- Migration/balancer pressure.
- Resharding feasibility.
- Shard-aware transaction needs.
- Tenant isolation, co-location và multi-Region.

Đừng tự tin rằng **sharding tự động khắc phục document quá lớn**: một BSON document vẫn không thể bị chia thành nhiều shards để vượt giới hạn document.

## 41. MongoDB: aggregation và result-size limits

Một aggregation:

```javascript
db.bookings.aggregate([
  { $match: { tenantId: "T1" } },
  { $group: { _id: "$listingId", bookings: { $push: "$$ROOT" } } }
]);
```

có thể sinh một group result chứa hàng trăm nghìn documents, khiến **một output BSON document** quá lớn dù từng input document nhỏ.

Cần phân biệt:

- Kích thước một output document.
- Internal aggregation stage memory.
- External spill-to-disk support/cấu hình.
- Cursor batch behavior.
- Transaction execution window.
- Index usage.
- Số shards tham gia.
- Disk headroom và temp files.

Một số aggregation stages có cách giới hạn bộ nhớ/cho phép dùng disk khác nhau theo server version; kiểm tài liệu phiên bản thực. **Cho phép spill không giúp một output document vượt hard BSON document size**.

Thiết kế khác:

```text
Count/group into bounded summary records.
Stream detailed results by cursor/page.
Use separate offline job for full exports.
```

## 42. MongoDB: bulk write khác transaction

Một `bulkWrite` có thể gửi nhiều operations để giảm round trips. Nhưng:

- Bulk write không mặc nhiên là một transaction ACID cho toàn bộ các operations.
- Ordered/unordered modes có error handling khác.
- Có giới hạn internal/API batching theo driver/server.
- Một thao tác có thể lỗi sau khi trước đó đã áp những thao tác khác.
- Retry cần stable business operation IDs.
- Transaction đa document có lifetime/lock/resource constraints riêng.

Một import cần:

```text
chunkId
idempotency marker
batch outcome
per-record error map
source and target checkpoint
```

thay vì “gửi 100k writes một lần và coi success nếu response cuối cùng 200”.

## 43. DynamoDB: item size

Một mốc phổ biến của DynamoDB là **giới hạn item 400 KB**, tính theo quy tắc kích thước item của dịch vụ. Không dùng `JSON.stringify(item)` để khẳng định item dưới 400 KB, vì DynamoDB account cả tên thuộc tính và biểu diễn dữ liệu theo quy tắc riêng.

Mô hình không an toàn:

```text
PK=USER#U1
item stores all notifications ever sent to user U1
```

Tăng trưởng không giới hạn dẫn đến hard-limit failure.

Mô hình có bound:

```text
PK=USER#U1
SK=PROFILE
    current profile fields

PK=USER#U1
SK=NOTIFICATION#timestamp#notificationId
    one notification per item
```

Nhưng cùng logical partition key `USER#U1` vẫn có thể nóng nếu mọi notifications của user này có lưu lượng lớn. Cần đánh giá phân phối, query access và physical partition behavior; tách thành nhiều items **không tự động giải hot partition**.

## 44. DynamoDB: Query/Scan page limit và pagination

Một mốc quan trọng là mỗi lần `Query`/`Scan` thường xử lý tối đa khoảng **1 MB dữ liệu trước khi cần phân trang**, theo semantics của API, bên cạnh các tham số `Limit`, filter và `LastEvaluatedKey`.

Ví dụ Java pseudo-code:

```java
String lastKey = null;
do {
    Page page = queryWithExclusiveStartKey(lastKey);
    consume(page.items());
    lastKey = page.lastEvaluatedKey();
} while (lastKey != null);
```

`Page` và method ở đây là abstraction, **không phải mã Java AWS SDK chạy được**.

Lưu ý:

- `Limit` có thể giới hạn số items được đọc/đánh giá, không bảo đảm số kết quả sau filter.
- Có thể có `Count` và `ScannedCount` khác nhau.
- Filter không nhất thiết giảm read cost như key condition.
- GSI reads có consistency restrictions khác base table.
- Pagination nhiều pages với writes đồng thời không tự tạo snapshot nhất quán toàn tập.
- `LastEvaluatedKey` cần được bảo quản theo resource/query scope và security.
- Không suy “page nhỏ” nghĩa đã hết kết quả nếu continuation còn.

## 45. DynamoDB: batch và transaction là giới hạn khác nhau

Những mốc thường được nhắc đến và cần kiểm với API/phiên bản hiện hành:

```text
BatchWriteItem:
    maximum number of write requests per API call is limited
    (commonly 25 requests per call).

BatchGetItem:
    item-count and overall response-size constraints apply
    (commonly up to 100 requested items, subject to size limits).

TransactWriteItems:
    transaction action count and aggregate item payload limits apply
    (commonly up to 100 actions with a 4 MB aggregate limit).
```

Không phải mọi loại batch đều atomic như transaction:

- `BatchWriteItem` có thể trả `UnprocessedItems`; client cần retry phần đó với backoff.
- `BatchGetItem` có thể trả `UnprocessedKeys`; phải tiếp tục cho đến khi complete hoặc báo partial result.
- Transaction có các precondition, conflict, size và Region/account restrictions riêng.
- 400 KB per-item limit vẫn áp cho item dù tổng request nhỏ.
- Throttling có thể do hot partition, index hoặc quotas, không chỉ total table capacity.

Tách **API request size**, **logical transaction size**, **individual item size** và **capacity use** thành những cột khác nhau trong bảng lựa chọn.

## 46. DynamoDB: mô hình partition key có hot writes

Ví dụ:

```text
PK = POPULAR_LISTING#L1
SK = BOOKING#<bookingId>
```

Nếu listing L1 được ghi hàng nghìn bookings/giây, các writes có thể tập trung theo partition key.

Một phương án hash sharding:

```text
PK = LISTING#L1#BUCKET#00...15
```

có thể phân tán bookings nhưng query list bookings phải đọc nhiều buckets. Nếu cần kiểm **availability một slot ngày duy nhất**, phải có source of truth/conditional write bảo vệ slot, không tách rời quyết định đặt trùng cùng một room/date sang nhiều buckets mà thiếu coordination.

Đo:

- Consumed/provisioned read/write capacity.
- Throttled requests.
- Per-key/skew telemetry có thể thu thập.
- GSI update/index heat.
- Transaction conflict.
- SDK retry amplification.
- Read/write consistency cost.

Auto scaling tổng capacity không đảm bảo sửa mọi hot-key bottleneck.

## 47. DynamoDB: item collections và secondary indexes

Khi dùng local secondary indexes (LSI), các giới hạn về **item collection** theo partition key có thể tác động thiết kế; cần tra cứu đúng tính năng và quota, không tự lấy giới hạn này áp cho mọi bảng không có LSI.

Ngoài ra:

- GSI có projected fields và additional write costs.
- Mỗi item update có thể tạo writes lên nhiều indexes.
- Index key attributes có size/type rules.
- Query shape quyết định liệu một partition key có phải là hot path hay không.
- Sparse index/TTL có thể làm số kết quả khác authoritative base table.
- Index key schema không nhất thiết tương đương business uniqueness.

Nếu business cần lịch sử vô hạn per customer/listing, việc dùng một logical key chung phải được đánh giá cùng item-collection constraints, query pages và eventual read models.

## 48. Cassandra/ScyllaDB: partition là nhiều rows, không phải một row

Một bảng CQL:

```sql
CREATE TABLE bookings_by_listing (
    listing_id text,
    month_bucket text,
    created_at timestamp,
    booking_id uuid,
    state text,
    PRIMARY KEY ((listing_id, month_bucket), created_at, booking_id)
) WITH CLUSTERING ORDER BY (
    created_at DESC, booking_id DESC
);
```

Mọi row cùng `(listing_id, month_bucket)` nằm trong một **CQL partition**; query theo partition key/range clustering có thể hiệu quả nếu partition được giới hạn hợp lý.

Một thiết kế thiếu bucket:

```sql
PRIMARY KEY ((listing_id), created_at, booking_id)
```

có thể khiến một listing tích lũy nhiều năm lịch sử trong một partition. Hệ có thể gặp latency/compaction/repair vấn đề **trước khi đụng một hard limit cụ thể**.

## 49. Cassandra/ScyllaDB: đánh giá large partition bằng số liệu thật

Đo:

```text
partition bytes distribution
rows per partition
tombstones per partition/read
cell/value sizes
compaction backlog
SSTables examined
read latency by large/hot partition
paging and coordinator memory
stream/repair times
```

Không đưa một ngưỡng universal như “partition tối đa 100 MB” thành luật bất biến cho mọi workload. Nhiều tài liệu vận hành có các **khuyến nghị soft size** phụ thuộc engine, compaction strategy, storage medium, TTL, consistency, repair và version.

Thử các partition worst-case trên cấu hình gần production, không chỉ metadata estimates.

## 50. Cassandra/ScyllaDB: các loại thao tác có phạm vi khác nhau

Một số mẫu:

```text
Point read by full partition key.
Range read by partition key + clustering range.
Full table scan with token-range iteration.
LWT/CAS conditional write.
Batch statement across partitions.
Repair/rebuild/stream token ranges.
```

Các rủi ro khác nhau:

- Truy vấn không có partition key đúng có thể không được hỗ trợ hiệu quả.
- Batches không phải công cụ tối ưu bulk import mặc định.
- Cross-partition logged batch có chi phí khác single-partition grouping.
- LWT tăng latency/contention.
- Tải full partition lớn vào memory có thể OOM.
- Paging state mất hiệu lực/expired trong một số điều kiện.
- Counters và TTL/tombstones có semantics riêng.
- Repair gây network/disk load lớn.

Một CQL batch **không tự biến thao tác xuyên các partitions thành transaction ACID tổng quát như quan hệ**. Phải tách workload throughput với semantic guarantee.

## 51. Cassandra/ScyllaDB: write-heavy + TTL

Một table lưu events theo TTL:

```text
insert rate = 10,000 events/s
TTL = 30 days
```

Ước lượng live logical events:

\[
N_{\mathrm{live}}\approx 10000 \times 30 \times 86400
=25{,}920{,}000{,}000
\]

Đây là số records logic trong toàn tập nếu tốc độ ổn định, **không phải** size một partition. Cần nhân bytes/event rồi phân bổ theo key và bucket. Tối ưu compaction cũng cần headroom vì tombstones, SSTables và cleanup không ngay lập tức.

Phải đánh giá:

- Burst traffic hơn average.
- TTL waves.
- Anti-entropy/repair windows.
- Tombstone GC policy.
- Legal retention.
- Hot keys.
- Per-node disk and write amplification.

Không chỉ dựa vào `TTL=30d` rồi mặc định disk usage đúng bằng số live items × serialized size.

## 52. Redis: giới hạn một key và tổng memory

Redis không chỉ là string cache. Có các loại:

```text
String
Hash
List
Set
Sorted set
Stream
HyperLogLog / probabilistic structures
Module-defined types
```

Mỗi loại có giới hạn/encoding đặc thù, và một số thao tác có độ phức tạp tỷ lệ với số members hoặc bytes.

Một key:

```text
listing_reviews:L1 -> list of all reviews ever created
```

có thể gây:
- Hot key contention.
- Memory spike.
- Long-running read/write.
- Network payload lớn.
- RDB/AOF fork/copy-on-write overhead.
- Replication/recovery pressure.
- Eviction behavior không mong muốn.

Redis key count nhỏ không đồng nghĩa memory/latency thấp. Theo dõi `MEMORY USAGE` theo scope và `INFO memory`, `SLOWLOG`, persistence/replication metrics phù hợp quyền và phiên bản.

## 53. Redis: string size vs aggregate structures

Các phiên bản Redis có giới hạn khác nhau cho string/value và container data structures; không coi một con số duy nhất là tối đa chung cho toàn keyspace.

Với structure lớn:

```text
HGETALL bigHash
LRANGE list 0 -1
SMEMBERS giantSet
ZRANGE hugeSortedSet 0 -1
```

có thể trả payload rất lớn hoặc làm client giữ quá nhiều trong memory. Dùng các phương án bounded:

- `HSCAN`/`SSCAN`/`ZSCAN`/`SCAN` theo semantics.
- `LRANGE` theo page range.
- Incremental iteration.
- Capped histories.
- Time-bucket keys.
- Partial field retrieval.
- Application rate limits.

**SCAN không cung cấp một snapshot transactionally consistent của keyspace đang thay đổi**; một export exact cần cơ chế phù hợp, không chỉ lặp SCAN rồi đếm.

## 54. Redis: tác vụ đồng bộ có thể block event loop

Redis xử lý nhiều commands theo event loop; một command/Lua script hoặc function quá lâu có thể làm requests khác chờ.

Đánh giá:

```text
worst-case runtime of Lua/function
number of keys accessed
data structure cardinality
server CPU
slowlog
latency spikes
script timeout/interruption semantics
```

Không nhầm “một lệnh duy nhất atomic” với “một lệnh không gây tác động đến các clients khác”.

Với Redis Cluster, multi-key operations còn cần xem **hash slot** và tính tương thích khi keys nằm ở nhiều slots. Sharding nhiều slots không giúp chia nhỏ **một key lớn**.

## 55. Redis Streams: giới hạn stream length và consumer workload

Một stream tăng mãi nếu không có retention policy.

Cần:

- Stream length/bytes theo thời gian.
- Entry payload max size.
- Trimming strategy.
- Consumer groups/Pending Entries List.
- Oldest unprocessed entry age.
- Recovery/replay window.
- `XREADGROUP` count/block budgets.
- Connection and client memory.
- Deduplication receipt retention.
- Persistence RDB/AOF durability.

Không chỉ dùng `XTRIM` để giữ memory đẹp nếu event chưa xử lý phải được bảo toàn. Retention phải đủ cho **maximum outage + retry + replay** theo business contract.

## 56. Search engine: limit theo document, query và shard

Trong hệ như Elasticsearch/OpenSearch, các giới hạn có thể xuất hiện ở:

- Maximum request body/transport message.
- Source document and mappings.
- Field count/depth.
- Index shard sizes.
- Result windows/deep pagination.
- Aggregation bucket limits.
- Script execution/resource.
- Reindex/scroll/PIT contexts.
- Search fan-out và heap/circuit breakers.

Một query:

```text
from=1,000,000
size=100
```

có thể không được hỗ trợ hợp lý bằng deep `from/size` vì phải xem nhiều kết quả trước. Cần `search_after`/PIT hoặc export strategy phù hợp công nghệ/phiên bản.

Không lấy một kết quả tìm kiếm nhanh từ index stale làm bằng chứng source of truth đúng; indexing/refresh lag là cổng riêng.

## 57. Graph databases: supernode và traversal explosion

Một vertex:

```text
user U1 follows 10,000,000 accounts
```

có thể là supernode. Một traversal:

```text
friends-of-friends-of-friends
```

có độ fan-out rất lớn dù mỗi node/property nhỏ.

Đánh giá:

- Degree distribution.
- Hops/depth.
- Paths per step.
- Duplicate path count.
- Memory/temporary intermediate results.
- Hot node locality.
- Query timeout.
- Traversal limits.
- Permission filters along edges.
- Transaction/update granularity.

Đặt traversal budgets và paginate, nhưng **không âm thầm cắt graph result** nếu business hứa kết quả đầy đủ. Có thể dùng precomputed ranking/summary với approximation contract rõ.

## 58. Dữ liệu multi-tenant: giới hạn theo tenant

Một thiết kế cần trả lời:

```text
What if one tenant is 1,000x larger?
What if one tenant sends 90% of traffic?
Can one tenant block backups or repairs?
Can a tenant cause another tenant to time out?
```

Các lựa chọn:

- Tenant-isolated database/collection/table khi phù hợp.
- Tenant + bucket keys.
- Per-tenant concurrency/cost quotas.
- Priority pools.
- Workload isolation.
- Per-tenant restore/export boundaries.
- Hot-key protection.
- Differentiated consistency classes.

Đánh giá cả **chi phí quản trị của rất nhiều tenant resources**; không mặc định tạo một database/table riêng cho từng tenant là luôn tối ưu.

## 59. Kích thước khóa ảnh hưởng index và routing

Một composite key:

```text
tenantId + region + listingId + date + version
```

có thể dài và được lặp trong index, replica logs, CDC, cursor và cache key.

Cần:

- Max partition/range/sort key length.
- UTF-8 bytes/encoding.
- Index prefix/compression.
- Query selectivity.
- Collision/uniqueness.
- Stable key format version.
- Hot key distribution.
- Tránh PII trong keys/logs.
- Hashing có ảnh hưởng range queries không?
- Composite serialization tránh delimiter ambiguity.

Hash key để ngắn không tự giải quyết collision/security. Nếu dùng hash, giữ mapping hoặc domain identity khi cần verify.

## 60. Kích thước index và write amplification

Một entity 2 KB có thể xuất hiện trong:
- Primary index.
- Một số secondary indexes.
- Full-text index.
- Reverse lookup table.
- Materialized views.
- CDC/outbox stream.

Tổng storage/work có thể lớn hơn nhiều lần 2 KB.

Ước lượng:

\[
S_{\mathrm{total}}\approx
S_{\mathrm{primary}}\times \mathrm{replicationFactor}
+S_{\mathrm{indexes}}
+S_{\mathrm{views}}
+S_{\mathrm{logs}}
+S_{\mathrm{backup/temporary}}
\]

Công thức là **mô hình chi phí**, tránh nhân replication factor hai lần nếu index/view storage đã được tính replicated. Nêu rõ giả định trong worksheet.

Một hệ tiết kiệm document bytes nhưng nhân dữ liệu qua nhiều GSIs/views có thể không rẻ hoặc dễ phục hồi như trông ban đầu.

## 61. Tác vụ lớn thường có failure amplification

Một batch nhận 10.000 operations nhưng gồm một operation invalid có thể:

- Bị từ chối toàn bộ nếu atomic transaction.
- Thành công một phần nếu API batch non-transactional.
- Timeout khiến caller không rõ phần nào đã commit.
- Retry toàn batch tạo duplicates nếu không idempotent.
- Tạo log event quá lớn.
- Gây lock/partition contention.
- Không thể rollback không có journal.

Vì vậy **batch kích thước tối đa API cho phép chưa chắc là batch kích thước nên dùng**.

Giới hạn mềm phải dựa trên:
- Failure scope chấp nhận.
- Idempotent replay.
- Per-operation error classification.
- Memory pressure.
- Deadline/SLI.
- Retry budget.
- Progress checkpoints.

## 62. Tác vụ asynchronous và backpressure

Với import 10 triệu records, thường nên:

```text
HTTP request -> validate -> enqueue durable job
    -> bounded workers
    -> idempotent chunks
    -> checkpoint
    -> verify
    -> publish completion
```

Thiết kế cần:

- `jobId` ổn định.
- Work units có size/byte budget.
- Durable queue/lease.
- Bounded concurrency per tenant.
- Timeouts và retry limits.
- Idempotency marker/receipt.
- Checkpoint không tiến trước khi effect durable.
- Progress/status API.
- Cancellation semantics.
- DLQ/quarantine khi data invalid.
- Final counts/digests/business invariants.

Một API trả 202 nhanh **không đồng nghĩa job hoàn tất đúng**. Đo `accepted latency`, `time to business completion` và `recovery/retry` riêng.

## 63. Worker memory và Java heap

Một Java service có thể lấy batch 10.000 items × 400 KB:

\[
10{,}000\times 400\,\mathrm{KB}
\approx 4\,\mathrm{GB}
\]

chỉ tính dữ liệu nominal, chưa kể:
- Java objects.
- `String`/byte arrays.
- JSON/BSON decoded structures.
- Driver buffers.
- Compression/decompression.
- Retries và copies.
- Concurrent batches.
- GC overhead.

Nếu heap chỉ 2 GB, workload không thể an toàn dù DB chấp nhận từng item.

Nên dùng streaming/pagination, bounded queue và limits theo **bytes**, không chỉ số items.

## 64. Concurrency nhân kích thước bộ nhớ

Một ước lượng:

\[
M_{\mathrm{inflight}}\approx
C\times B\times S_{\mathrm{item}}\times A_{\mathrm{object}}
\]

với:

- \(C\): số batches đồng thời.
- \(B\): số items mỗi batch.
- \(S_{\mathrm{item}}\): payload bytes trung bình.
- \(A_{\mathrm{object}}\): hệ số overhead/duplication của JVM và buffers.

Ví dụ minh họa:

```text
C = 8 concurrent batches
B = 100 items
S = 50 KiB
A = 3x
```

\[
M\approx 8\times100\times50\,\mathrm{KiB}\times3
\approx 117.2\,\mathrm{MiB}
\]

Chỉ tính batch buffers, chưa gồm heap khác và worst-case outliers. Khi P99 item size lớn hơn average, bộ nhớ đột biến có thể vượt ước lượng.

## 65. Tác vụ cần ngân sách thời gian và timeout semantics

Một request có nhiều deadlines:

```text
API request deadline
driver server-selection timeout
connection pool acquire timeout
socket/read timeout
database operation timeout
queue/job processing deadline
```

Nếu API deadline 500 ms nhưng một query scan mất 60 giây:

- Caller timeout.
- DB operation có thể tiếp tục chạy tùy engine/cancel.
- Connection/resource vẫn bận.
- Retry tạo work amplification.
- User có thể gửi request trùng.

Nên có:
- Bounded operation budgets.
- Cancellation/interrupt behavior được kiểm.
- Stable idempotency keys cho writes.
- Async workflow cho tác vụ dài.
- Tách timeout UNKNOWN khỏi chắc chắn FAILED.
- Đo accepted-vs-completed effects.

Không tăng timeout vô hạn chỉ để giảm tỷ lệ lỗi; nó có thể làm queues và p99 tệ hơn.

## 66. Size limit không thay security/data limits

Một client gửi:

```json
{
  "tenantId": "T2",
  "filter": {},
  "limit": 10000000
}
```

Dù query dưới DB request size, hệ có thể cho phép tenant T1 scan dữ liệu T2 nếu auth guard sai.

Cần:

- Tenant extracted from verified identity, không tin client.
- Maximum permitted query scope.
- Per-tenant pagination/rate budget.
- No unrestricted debug export.
- Query templates, allowlisted sorts/projections.
- Bound aggregate and script complexity.
- No raw PII in instrumentation.
- Secret handling in backup/export.
- TTL/retention constraints.

Một **giới hạn tác vụ** cũng là công cụ bảo vệ multi-tenant isolation và availability, không chỉ tuning.

## 67. Thử nghiệm hard limit phải không phá production

Một test gửi item lớn, batch vượt quota hoặc truy vấn quét toàn bảng có thể:

- Tạo load không cần thiết.
- Đầy disk/stream logs.
- Block Redis event loop.
- Tiêu tốn cloud charges.
- Gây sự cố với other tenants.
- Làm API rate limit tràn.
- Lộ dữ liệu trong logs.

Thiết kế test:

1. Isolated account/cluster.
2. Representative engine version/config.
3. Synthetic data không chứa PII.
4. Explicit budgets và cleanup.
5. Stop conditions.
6. Negative cases at boundary.
7. Read-only probes trước destructive/fault tests.
8. Ghi expected error code/retry behavior.
9. Kiểm không có partial writes ngoài dự kiến.
10. Không chạy destructive production tests không được phê duyệt.

## 68. Ranh giới giữa soft limit và hard limit phải có headroom

Nếu hard limit một item là \(L\), có thể đặt cảnh báo tại:

\[
S_{\mathrm{item}} \ge \alpha L,\qquad 0<\alpha<1
\]

Ví dụ \(\alpha=0.75\) **chỉ là một chính sách minh họa**, không phải ngưỡng chung. Nên chọn dựa trên:

- Growth rate.
- Batch/transaction composition.
- Schema/codec overhead.
- Encryption expansion.
- Data imports.
- Outlier distribution.
- Traffic until next migration window.
- Contract và failure consequences.

Headroom của item size khác headroom disk/CPU/quota. Một ngưỡng 75% cho item không suy ra disk cũng dùng 75%.

## 69. Vì sao “max size” chưa nói hết lộ trình tăng trưởng?

Một record hiện 250 KB, hard limit 400 KB:

```text
Current = 250 KB
Recent growth = 10 KB/month
```

Nếu giữ tốc độ tuyến tính, khoảng trống là 150 KB, tương đương ~15 tháng. Nhưng đó chỉ là **ước lượng**:

- Growth có thể theo cấp số nhân.
- Một feature mới thêm trường lớn ngay.
- User cực đại có growth gấp 50 lần.
- Migrations có thể làm payload phình.
- TTL/deletion có thể giảm size.
- Compression/encoder thay đổi.
- Một item update có thể thêm arrays không có bound.

Đánh giá theo **cohort và worst-case**, thêm trigger trước khi đến giới hạn.

## 70. Mẫu dự báo tăng trưởng theo P99 entity

Một worksheet:

```text
Entity type:
Current P99 encoded size:
Current max encoded size:
P99 monthly growth:
Growth confidence/assumptions:
Planned fields/features:
Hard limit:
Operational soft limit:
Time to soft limit:
Current usage by tenant:
Escape hatch:
```

Nếu record sẽ tăng không giới hạn theo nghiệp vụ, không nên dựa vào forecast “còn 18 tháng” để trì hoãn thiết kế tách. Hãy chọn bounded schema/child collections trước khi hard limit trở thành migration khẩn cấp.

## 71. Đánh giá tác động đến RTO khi dữ liệu phân bố lệch

Hai trường hợp cùng 10 TB:

```text
A: 10 TB across many balanced partitions.
B: 10 TB with one oversized/hot partition.
```

Ở B, backup/repair/stream có thể có **straggler partition** quyết định thời gian hoàn thành job. Tốc độ trung bình toàn cluster không phản ánh thời gian chờ lâu nhất.

Có thể ước lượng:

\[
T_{\mathrm{job}} \gtrsim
\max_{p\in\mathrm{partitions}}T_p
\]

khi partitions xử lý song song nhưng job phải đợi tất cả. Còn nếu xử lý tuần tự/ràng buộc, tổng thời gian có thể lớn hơn. Đo P99/max task chunk durations và tail retries.

## 72. Thiết kế giới hạn phục vụ recovery, không chỉ realtime

Khi chọn max partition size hoặc max batch size, tính cả:

- Normal API SLO.
- Failover.
- Repair/rebuild.
- Region migration.
- Snapshot/export.
- Restore.
- Data validation.
- Tenant offboarding/deletion.
- Security incidents.
- Reindex.
- Schema migration.
- Disaster recovery.

Một partition “đọc trong 10ms” nhưng “restore trong 10 giờ” có thể không phù hợp với RTO 30 phút của sản phẩm, dù online latency rất tốt.

## 73. Quản lý thứ tự xử lý khi chia nhỏ tác vụ

Chunking tạo khả năng:
- Retry riêng từng chunk.
- Tiến checkpoint.
- Tăng concurrency.

Nhưng có thể phá causal order:

```text
Chunk A: create order.
Chunk B: mark order paid.
```

Nếu B chạy trước A, có thể bị reject hoặc tạo state sai.

Thiết kế:
- Per-entity order hoặc predecessor revision.
- Concurrency theo disjoint key ranges.
- Idempotency receipts.
- Transaction grouping.
- Gap handling.
- Failure quarantine.
- Final invariant reconciliation.

Không chỉ dùng random worker queues mà không biết thao tác nào phụ thuộc thao tác nào.
## 74. Java 17: đo payload UTF-8 không phải đếm ký tự

Chương trình nhỏ:

```java
import java.nio.charset.StandardCharsets;

public final class Utf8BudgetExample {
    public static void main(String[] args) {
        String value = "Căn hộ 🏠 tại Đà Nẵng";
        int chars = value.length();
        int utf8Bytes = value.getBytes(StandardCharsets.UTF_8).length;

        System.out.println("UTF-16 code units=" + chars);
        System.out.println("UTF-8 bytes=" + utf8Bytes);
    }
}
```

Kết quả hai con số có thể khác nhau; đó là chủ đích. Nhưng:

- `utf8Bytes` chỉ là bytes của **value string**, chưa có field names/headers/types.
- JSON có escaping và punctuation riêng.
- BSON, DynamoDB AttributeValue, CQL, Redis protocol có accounting khác nhau.
- Encryption/compression và driver buffers có thể tăng hoặc giảm sizes.

Bài toán production cần **measure/estimate** theo API thật, và server hard-limit errors phải được xử lý đúng thay vì suy từ `String.length()`.

## 75. Java 17: ví dụ runnable về record và batch budgets

Mẫu sau là một **size budget demo độc lập**, không sử dụng SDK NoSQL. Nó mã hóa một record nhị phân có `UTF-8 id`, length-prefix và payload để minh họa phép kiểm kích thước cả **bản ghi đơn** lẫn **batch**.

```java
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

public final class BoundedNoSqlBatchDemo {

    record DataItem(String id, byte[] payload) {
        DataItem {
            if (id == null || payload == null) {
                throw new IllegalArgumentException("Null input");
            }
        }
    }

    static byte[] encode(DataItem item) {
        try {
            byte[] id = item.id().getBytes(StandardCharsets.UTF_8);
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
            DataOutputStream out = new DataOutputStream(bytes);

            out.writeInt(1); // Codec version.
            out.writeInt(id.length);
            out.write(id);
            out.writeInt(item.payload().length);
            out.write(item.payload());
            out.flush();

            return bytes.toByteArray();
        } catch (IOException impossibleForMemoryStream) {
            throw new IllegalStateException(impossibleForMemoryStream);
        }
    }

    static List<List<DataItem>> makeBatches(
            List<DataItem> items,
            int maxRecordBytes,
            int maxItemsPerBatch,
            int maxBatchBytes) {

        if (maxRecordBytes <= 0
                || maxItemsPerBatch <= 0
                || maxBatchBytes <= 0) {
            throw new IllegalArgumentException(
                    "All budgets must be positive");
        }

        List<List<DataItem>> batches = new ArrayList<>();
        List<DataItem> current = new ArrayList<>();
        long usedBytes = 0;

        for (DataItem item : items) {
            int itemBytes = encode(item).length;

            if (itemBytes > maxRecordBytes) {
                throw new IllegalArgumentException(
                    "Record exceeds budget: " + item.id());
            }

            if (itemBytes > maxBatchBytes) {
                throw new IllegalArgumentException(
                    "Single record exceeds batch budget");
            }

            boolean countExceeded =
                    current.size() >= maxItemsPerBatch;

            boolean byteExceeded =
                    usedBytes > (long) maxBatchBytes - itemBytes;

            if (!current.isEmpty()
                    && (countExceeded || byteExceeded)) {
                batches.add(List.copyOf(current));
                current.clear();
                usedBytes = 0;
            }

            current.add(item);
            usedBytes += itemBytes;
        }

        if (!current.isEmpty()) {
            batches.add(List.copyOf(current));
        }
        return batches;
    }

    static DataItem item(String id, int bytes) {
        if (bytes < 0) {
            throw new IllegalArgumentException("Negative length");
        }
        return new DataItem(id, new byte[bytes]);
    }

    public static void main(String[] args) {
        List<DataItem> input = List.of(
            item("listing-1", 900),
            item("listing-2", 1200),
            item("listing-3", 1500),
            item("listing-4", 600),
            item("listing-5", 1700)
        );

        // Synthetic budgets only, NOT real database limits.
        int maxRecordBytes = 2048;
        int maxItemsPerBatch = 3;
        int maxBatchBytes = 3000;

        List<List<DataItem>> batches = makeBatches(
            input, maxRecordBytes, maxItemsPerBatch, maxBatchBytes);

        for (int i = 0; i < batches.size(); i++) {
            List<DataItem> batch = batches.get(i);
            long encodedBytes = batch.stream()
                .mapToLong(x -> encode(x).length).sum();

            System.out.println(
                "batch=" + (i + 1)
                + " items=" + batch.size()
                + " bytes=" + encodedBytes);
        }
    }
}
```

**Nguyên tắc được minh họa:**

- Một record có budget riêng.
- Một batch có cả cap theo **số items** và **tổng bytes**.
- Không chèn thêm record nếu vượt cap.
- Một item quá lớn phải bị reject/đưa sang kiến trúc khác; không “xẻ bytes” tùy tiện thành nhiều logical records mà không có contract.
- Cả hai kiểu kích thước được tính bằng **codec nhất quán trong demo**.

**Giới hạn:**

- Các con số 2048, 3 và 3000 là **giới hạn giả lập**, không phải quota MongoDB/DynamoDB/CQL.
- Mã giữ data và batches trong memory, không phù hợp stream lớn.
- Chưa tính request envelope, API overhead, compression, encryption, server item-size rules, transaction actions hoặc target hot key.
- `encode(item)` tạo byte array mới; thực tế nên đo bằng codec/size estimator đã hiệu chỉnh và tránh allocations lặp lớn.
- Không có network calls, DB persistence, retry/idempotency hay throttling.
- Một request batch vẫn có thể thành công một phần hoặc có `UNKNOWN` outcome; cần protocol ở các phần tiếp theo.

## 76. Bounded batch planning chưa bảo đảm correctness

Một batch hợp lệ theo size vẫn có thể sai dữ liệu.

Ví dụ:

```text
Batch 1:
    create booking B1
    reserve unit U1

Batch 2:
    publish booking-confirmed event B1
```

Nếu Batch 1 partial failure hoặc Batch 2 chạy sớm:

```text
Event says CONFIRMED but reservation not committed.
```

Cần:

- Business operationId/idempotency.
- Transaction boundary hoặc saga.
- Durable outbox/receipts.
- Expected revision/conditional writes.
- Ordering/gaps.
- Per-item partial failure handling.
- Final invariants.
- Checkpoint chỉ sau khi effect durable.

**Size budget là điều kiện cần của một thao tác, không phải bảo đảm tính đúng dữ liệu.**

## 77. Java 17: mô phỏng độ lệch phân vùng

Một generator nhỏ giúp nhìn vì sao trung bình keys có thể che hot key.

```java
import java.util.HashMap;
import java.util.Map;

public final class HotKeyDistributionDemo {

    static String partitionKey(int requestNumber) {
        // Synthetic distribution: 60% hit the same key.
        if (requestNumber % 10 < 6) {
            return "LISTING#HOT";
        }

        return "LISTING#"
                + (requestNumber % 200);
    }

    public static void main(String[] args) {
        int total = 100_000;
        Map<String, Integer> counts = new HashMap<>();

        for (int i = 0; i < total; i++) {
            counts.merge(partitionKey(i), 1, Integer::sum);
        }

        int max = counts.values().stream()
                .mapToInt(Integer::intValue)
                .max()
                .orElse(0);

        double mean = (double) total / counts.size();

        System.out.println("totalOperations=" + total);
        System.out.println("activeKeys=" + counts.size());
        System.out.println("averagePerKey=" + mean);
        System.out.println("hottestKeyOperations=" + max);
        System.out.println("skewRatio=" + max / mean);
    }
}
```

Trong mô hình giả lập, key `LISTING#HOT` chiếm 60% requests và không thể được suy ra từ average. Nhưng simulation này **không phản ánh physical partition mapping** của một DB cụ thể; phải thu số liệu skew, throttling và partition placement trong thí nghiệm thực.

## 78. Giới hạn API nên được enforce ở nhiều lớp

Một pipeline lý tưởng:

```text
Client input
    |
    v
API validation:
    maximum request bytes and semantic cardinality
    |
    v
Business layer:
    maximum line items / time span / ownership
    |
    v
Driver adapter:
    exact/estimated encoded size,
    batch and transaction budgets
    |
    v
NoSQL service:
    hard limits, capacity and consistency
```

Không chỉ dựa vào database trả lỗi `RequestTooLarge` để bảo vệ app memory/latency. Ngược lại, đừng chặn tất cả nội dung ở một HTTP byte cap mà quên những thao tác nhỏ nhưng **truy vấn ra hàng triệu results**.

Ghi lỗi rõ:

```text
400/413/422 depending API contract and semantics
operation rejected before persistence
```

Tránh biến một validation failure thành retryable 500 và tạo retry storm.

## 79. Budget cho query và job nên có tính toán trước

Trước một report query lớn có thể ước lượng:

```text
Estimated rows to scan
Estimated bytes to scan
Expected partitions touched
Required consistency
Estimated execution time
Tenant quota
Priority
```

Có thể:

- Chặn đồng bộ, hướng sang async export.
- Yêu cầu time-range nhỏ hơn.
- Dùng precomputed summary.
- Giảm concurrency.
- Dùng read replica/analytics store nếu contract cho phép.
- Chia job theo time buckets.

Ước lượng có thể sai; phải có **runtime guard** và stop conditions chứ không chỉ check ở đầu request.

## 80. Giới hạn logic của business quan trọng hơn hard cap engine

Ví dụ engine cho phép item lớn nhưng business quyết định:

```text
One booking may include at most 20 guests.
One report may cover at most 31 days synchronously.
One cart can have at most 200 line items.
One API page may contain at most 100 results.
```

Đây là contract sản phẩm cần kiểm và giải thích cho người dùng, **không phải con số mượn từ server max payload**.

Lợi ích:

- SLO ổn định.
- Error handling rõ.
- Tránh abuse.
- Dễ đo worst-case.
- Bảo vệ writes invariants.
- Dự báo chi phí.

Nếu cần xử lý trường hợp lớn hơn, cung cấp workflow khác thay vì im lặng cắt dữ liệu.

## 81. Thiết kế paging keyset thay offset cho dữ liệu lớn

Với một danh sách sắp xếp:

```text
ORDER BY createdAt DESC, listingId DESC
```

Có thể dùng cursor mang `(createdAt,listingId)` để phân trang. Nhưng:

- Cần tie-breaker ổn định.
- Cursor phải scope theo tenant/filter/index generation.
- Phải bảo vệ token khỏi tampering.
- Concurrent writes/deletes có thể thay kết quả giữa pages.
- Exact export có thể cần snapshot cut.
- Cursor TTL/expiration là một giới hạn operation.
- Không lưu raw PII/secret trong token.

Một `OFFSET 1,000,000` trên search/NoSQL query có thể có chi phí/limits khác keyset pagination; chọn theo engine và access pattern.

## 82. Query fan-out budget

Một request:

```text
Get all bookings in 2 years
    -> 24 monthly partitions
```

Nếu chuyển sang daily buckets:

```text
-> about 730 daily partitions
```

Dữ liệu mỗi partition nhỏ hơn nhưng fan-out lớn hơn.

Có thể đặt:

```text
maxPartitionsPerInteractiveQuery
maxParallelReads
maxTotalScannedBytes
maxOutputRecords
maxExecutionDeadline
```

Với query lớn, chuyển sang async job hoặc một read model tổng hợp. Không làm phép fan-out vô hạn chỉ vì mỗi partition nhỏ.

## 83. Distributed transactions và hàng chờ cạnh tranh

Một transaction chứa 100 actions có thể hợp lệ theo số actions nhưng:
- Chạm quá nhiều hot keys.
- Có nhiều conditional conflicts.
- Bị abort/retry thường xuyên.
- Vượt time budget.
- Tạo high tail latency.
- Gây load lên nhiều replicas.

Do đó đo:

```text
transaction abort/conflict rate
p95/p99 commit latency
retries and UNKNOWN outcomes
per-partition contention
logical business invariant results
```

**Transaction size limit** và **transaction contention limit** khác nhau. Thiết kế chọn batch/transaction size dựa trên cả hai.

## 84. Import/export: manifest và progress coverage

Một export:

```yaml
jobId: "EXPORT-EXAMPLE"
sourceSnapshot: "W"
keyRanges:
  - "range-001"
  - "range-002"
  - "range-003"
status: "IN_PROGRESS"
```

Một manifest cần:
- Tổng số expected ranges/chunks.
- Completed ranges và checksums.
- Item counts/unique IDs.
- Retried/skipped/failed chunks.
- Source logical cut.
- Schema/codec version.
- Destination location/encryption.
- Hash/provenance.
- Data owner approval.
- Final completeness gate.

Không chỉ dựa vào tổng bytes exported nếu một key range bị skip. Hai datasets có cùng count có thể khác logical keys/values, nên verification cần canonical digest và business invariants khi cần.

## 85. Async job retry không được nhân đôi side effects

Một import worker:

```text
Read chunk 5.
Write chunk 5 to target.
Crash before recording completion.
```

Khi resume, chunk 5 chạy lại.

Cần:

- Stable chunkId/operationIds.
- Idempotent writes hoặc dedup ledger.
- Atomic effect/marker trong phạm vi engine cho phép.
- Checkpoint durable sau effect.
- Reconciliation khi outcome UNKNOWN.
- Correct delete/tombstone handling.
- Schema/version mapping.
- Stop on conflict rather than silent overwrite.

Một pipeline có throughput cao nhưng duplicate transactions sau replay **không vượt qua correctness gate**.

## 86. Concurrency, batch size và queueing trade-off

Một hệ có thể tăng throughput khi batch size tăng tới một mức, sau đó p99 và memory tăng đột ngột.

Mẫu thử:

```text
Batch sizes: 1, 10, 25, 50, 100, 200
Concurrent workers: 1, 4, 8, 16
Item sizes: P50, P95, P99, maximum
```

Chọn các giá trị **nằm trong hard limits** của engine/API và workload thực. Với DynamoDB `BatchWriteItem`, không thử 50 hay 100 actions trong một request nếu API cap thấp hơn; thay bằng nhiều requests/batches và điều chỉnh concurrency.

Đo:

- Confirmed correct business effects/s.
- p95/p99 completion latency.
- API throttling.
- Unprocessed items.
- Retry amplification.
- JVM memory/GC.
- DB CPU/IO/network.
- CDC/replication lag.
- Repair/backup impact.

Không chọn theo số `physicalOps/s` một mình.

## 87. Latency gắn với từng kích thước

Tập nhỏ có thể che hiện tượng nonlinear:

```text
Item 1 KiB -> p99 8ms
Item 10 KiB -> p99 10ms
Item 100 KiB -> p99 40ms
Item 300 KiB -> p99 200ms
```

Các con số minh họa, không phải benchmark thực.

Nên có **latency vs size curves** theo:
- Key class/tenant.
- Read vs write.
- Cache hit/miss.
- Partition-hotness.
- Query result bytes.
- Index count.
- Consistency level.
- Concurrent operations.

Một câu “p99 chung 20ms” thiếu ý nghĩa khi P99-size requests bị timeout có thể đã bị loại khỏi histogram.

## 88. Benchmark cần giữ semantics không đổi

Một candidate “nhanh hơn” vì:
- Hạ durability acknowledgment.
- Bỏ CAS/transaction.
- Chỉ trả first page.
- Đọc stale cache.
- Xóa tenant filter.
- Drop CDC events lớn.
- Bỏ tombstones.
- Không ghi audit.

không phải cải thiện hiệu năng tương đương.

Trong evaluation report, đặt:

```text
CORRECTNESS_GATE: PASS/FAIL/INCONCLUSIVE
PERFORMANCE_GATE: PASS/FAIL/INCONCLUSIVE
LIMITS_GATE: PASS/FAIL/INCONCLUSIVE
OPERATIONS_AND_RECOVERY_GATE: PASS/FAIL/INCONCLUSIVE
```

Không trung bình các gates thành một điểm số che mất failure nghiêm trọng.

## 89. Ước lượng chi phí trên mỗi business operation đúng

Một công thức:

\[
C_{\mathrm{correctOp}} =
\frac{\text{tổng cost vận hành trong cửa sổ}}
{\text{số business effects đúng được xác minh}}
\]

Cần ghi:
- Storage primary/index/views.
- Replication/backup.
- Read/write capacity.
- Network egress.
- Compute/worker memory.
- CDC/streaming.
- Operations and recovery.
- Data reconciliation.
- Tenant isolation costs.

Tập trung vào **correct confirmed effects**, không chỉ số database attempts, vì retry storm có thể tăng requests nhưng không tăng nghiệp vụ hoàn thành.

## 90. Một bảng sizing cụ thể

Ví dụ **giả định** cho một hệ booking:

| Dữ liệu | P99 encoded item | Max expected | Growth | Operations | Giải pháp gợi ý |
| --- | ---: | ---: | --- | --- | --- |
| Listing summary | 12 KiB | 40 KiB | Chậm | Point read/update | Một record bounded |
| Photo metadata | 1 KiB | 2 KiB/ảnh | Theo upload | Page list | Child items, blob external |
| Review | 3 KiB | 15 KiB/review | Theo tháng | Time-range list | Child records/time bucket |
| Booking | 4 KiB | 12 KiB | Ổn định | Conditional write | Per-booking record + receipt |
| Availability aggregate | 8 KiB | Phụ thuộc horizon | Theo thời gian | Date lookup/CAS | Bounded date bucket |
| Audit event | 2 KiB | 8 KiB | Rất nhanh | Append/scan/export | Time/tenant buckets |
| Search projection | 5 KiB | 20 KiB | Theo source | Search/read | Async derived view |

**Không lấy số giả định này làm dữ liệu production.** Dùng measurement thực theo phiên bản và business contract. Bảng cần thêm cột hard limit/operating target, per-partition throughput, latency, RTO, consistency và cost.

## 91. Tình huống 1: một listing có 100.000 ảnh

Một document JSON chứa metadata của 100.000 ảnh:

```text
photoCount = 100,000
metadataPerPhoto = 500 bytes
```

Chỉ phần metadata gần:

\[
100000\times500=50{,}000{,}000\text{ bytes}
\]

chưa kể field names và wrappers; vượt nhiều giới hạn document/item phổ biến.

Thiết kế:

```text
Listing record: summary/photoCount/mainPhotoId.
Photo records: (listingId, photoId) -> metadata.
Blob storage: actual photo bytes.
```

Các thao tác:
- `GET listing` nhanh, trả summary.
- `GET photos` qua pagination.
- `POST photo` có idempotent upload transaction/saga.
- `DELETE photo` có retention, object cleanup và reconciliation.

Không chỉ giải kích thước; còn phải bảo đảm quyền truy cập blob và không có orphan objects.

## 92. Tình huống 2: booking của listing hot

Một listing có 5.000 requests đặt một khung ngày trong 1 phút. Nếu tất cả cố ghi:

```text
availableUnits on one item
```

cần phân biệt:
- 5.000 attempts.
- Số reservations hợp lệ thực tế.
- CAS conflicts expected.
- Timeout UNKNOWN.
- Retry amplification.
- Unique booking IDs.
- Double-booking invariant.

Không giải bằng cách chia random key rồi mỗi bucket tự trả `available=true`. Một mô hình có thể dùng một **slot owner/conditional decision** và append ledger theo booking ID, hoặc một booking protocol bảo toàn invariant qua partitions.

Benchmark **số requests/s** phải đi cùng **số reservations được xác nhận đúng/s**.

## 93. Tình huống 3: bảng events theo tháng bị quá lớn

Một tenant nhập 50 triệu events/tháng, mỗi event trung bình 1 KiB:

```text
Monthly logical payload ~ 50,000,000 KiB
                       ~ 47.7 GiB
```

Nếu mọi event nằm dưới **một CQL partition key của tenant+month**, partition có thể rất khó query/repair/stream.

Lựa chọn:
- Daily/hourly buckets.
- Secondary shard suffix phù hợp.
- Query-by-time read model.
- Hot tenant quota.
- Retention/TTL.
- Archive/object storage.
- Range scan/export workflow.

So sánh:
- Max partition bytes.
- Query fan-out.
- Repair/restore time.
- Writer rate per bucket.
- Tombstone/compaction cost.

Đừng đánh giá chỉ qua tổng disk capacity của cả Cassandra cluster.

## 94. Tình huống 4: batch import hợp lệ nhưng partial success

Một import gửi 25 items vào một batch API. Kết quả:

```text
20 items processed.
5 items not processed/throttled.
```

Nếu import tool chỉ thấy HTTP response thành công và tăng progress `25/25`, dữ liệu bị thiếu.

Cần:
- Ghi processed/unprocessed item identities.
- Retry 5 items với exponential backoff/jitter.
- Stable operation IDs.
- Bounded retry budget.
- Checkpoint chỉ khi tất cả item outcomes được xác định.
- Report partial failure.
- Final count+key/digest reconciliation.

Một batch API có thể không hứa atomic all-or-nothing; phải đọc response theo API cụ thể.

## 95. Tình huống 5: read model hiển thị nhanh nhưng không đầy đủ

Search index chứa 99% listings:

```text
Query p99 = 4ms.
Source authority contains 100%.
```

Nếu product hứa tất cả active listings xuất hiện trong một freshness window, cần:
- Source commit watermark.
- Indexer applied watermark.
- Missing keys/tombstones.
- Refresh/CDC lag.
- Per-tenant coverage.
- Search query filters.
- Request latency.

Một index trả 99% dữ liệu cực nhanh có thể **không đạt contract**. Giới hạn tác vụ indexer/backfill phải được đánh giá cùng read model freshness.

## 96. Tình huống 6: restore bị chậm bởi một partition

Một restore 100 partitions:

```text
99 partitions restored in 8 minutes.
1 oversized partition requires 90 minutes.
```

Job completion ít nhất phải đợi partition chậm nếu tất cả cần thiết.

Cách phòng ngừa:
- Chia dữ liệu ngay từ lúc thiết kế.
- Thử restore worst-case.
- Parallelism phù hợp.
- Streaming checkpoint.
- Snapshot/PITR compatibility.
- Verify counts/digests.
- Budget disk/network.
- RTO gate.

**Khả năng lưu trữ là khác với khả năng khôi phục theo thời hạn.**

## 97. Tình huống 7: Redis command quét key quá lớn

Một endpoint gọi:

```text
HGETALL listing:reviews:L1
```

trên một hash khổng lồ. Một request trả response lớn và giữ Redis/server/client bận.

Giải pháp:
- Bounded hash/window hoặc child keys.
- `HSCAN`/read model paging phù hợp.
- Giới hạn output bytes.
- Không gọi `KEYS *` hoặc `MONITOR` đại trà trong production.
- Đo latency tail và memory usage.
- Kiểm không mất review/ordering khi chia.

Đừng giảm thời gian bằng cách chỉ trả 100 reviews **mà không công bố pagination** nếu API hứa tất cả.

## 98. Tình huống 8: giao dịch quá lớn

Một business workflow muốn ghi 500 line items, inventory reservations và outbox trong một transaction.

Cần:
- Xem count/actions/bytes/cross-partition phạm vi thật.
- Phân tích invariants nào cần atomic.
- Giới hạn max line items theo product.
- Một order aggregate hoặc saga với ledger.
- Chia batches nhưng giữ business operationId.
- Không publish `ORDER_COMPLETED` trước khi all required effects durable.
- Recovery sau partial failure.
- Reconciliation khi timeout/UNKNOWN.

Đây là quyết định **data model + workflow semantics**, không chỉ tăng transaction timeout.
## 99. Tạo một limit inventory cho từng sản phẩm

Một bản kiểm cần điền **số liệu đã xác minh**, không copy quota từ một bài blog:

| Hạng mục | MongoDB | DynamoDB | Cassandra/ScyllaDB | Redis |
| --- | --- | --- | --- | --- |
| Phiên bản/edition | ... | ... | ... | ... |
| Hard max record/item/value | ... | ... | ... | ... |
| Key name/length/depth limits | ... | ... | ... | ... |
| Logical partition model | ... | ... | ... | ... |
| Soft max partition/key size | Theo benchmark | Theo workload/quota | Theo benchmark/repair | Theo memory/latency |
| Max batch actions | Theo API/driver | Theo API | Theo CQL/driver | Theo command/pipeline |
| Max transaction scope | Theo engine/config | Theo API | Theo conditional model | Theo Redis semantics |
| Max query/page result | Theo cursor/protocol | Theo Query/Scan pagination | Theo paging/read budget | Theo bounded commands |
| Hot partition behavior | ... | ... | ... | ... |
| Read/write consistency | ... | ... | ... | ... |
| Backup/restore window | ... | ... | ... | ... |
| CDC/event envelope | ... | ... | ... | ... |
| Quota escalation possible? | ... | ... | ... | ... |
| Evidence link/date/owner | ... | ... | ... | ... |

Đừng ghi một giá trị quota không có **đơn vị, nguồn, ngày và điều kiện áp dụng**.

## 100. Phân nhóm tiêu chí: knockout và trade-off

Có hai nhóm:

**Knockout criteria (bắt buộc):**
- Business record có thể biểu diễn trong hard limit.
- Read/write correctness và auth đạt.
- Transaction/conditional model có khả năng giữ invariant.
- RPO/RTO và delete/retention đáp ứng.
- Các API cần thiết hỗ trợ workload.
- Quota có thể được cấp trong môi trường mục tiêu.
- Không có một hot partition không thể giải theo access pattern.

**Trade-off criteria (đánh đổi):**
- P99 latency.
- Cost per correct operation.
- Read/write amplification.
- Operational complexity.
- Flexibility schema.
- Indexing/query expressiveness.
- Scale-out efficiency.
- Developer experience.
- Migration/recovery overhead.

Một hệ có P99 tốt nhất nhưng **không thể biểu diễn một record hoặc transaction bắt buộc** không nên đứng đầu vì điểm trung bình cao.

## 101. Weighted score chỉ sau khi vượt điều kiện bắt buộc

Có thể chấm trong tập ứng viên hợp lệ:

| Tiêu chí | Trọng số gợi ý | Cách đo |
| --- | ---: | --- |
| Query latency P99 | 20% | Load test representative |
| Verified goodput | 15% | Correct business operations/s |
| Cost per verified operation | 20% | Resource/capacity/accounting |
| Data model flexibility | 15% | Migration/feature tests |
| Partition hot-key behavior | 15% | Skewed load tests |
| Recovery/operations burden | 15% | Restore/repair drills |

Trọng số là minh họa; tổ chức phải chọn dựa trên mục tiêu sản phẩm. **Không dùng bảng này để cho phép data correctness FAIL được bù bằng latency PASS**. Knockout gates phải đạt trước khi score.

## 102. Ma trận size/partition/operation theo 3 mức tải

Một thử nghiệm phải có ít nhất:

| Workload | Normal | Peak | Stress/edge |
| --- | --- | --- | --- |
| Record size | P50 | P99 | Max allowed/import |
| Partition size | P50 partition | P99 partition | Largest/highest-growth |
| Hot key | Typical | Top 1% traffic | Single viral key |
| Query result | 1 page | Many pages | Large export |
| Batch/transaction | Typical actions | Max planned | Near hard limit |
| CDC | Normal envelope | Large document update | Gap/replay after outage |
| Restore | Small sample | Realistic production subset | Full worst-case + failover |
| Concurrency | Baseline | Peak actual | Burst/fault/retry storm |

`Normal/Peak/Stress` ở đây là **nhãn workload**, không phải ba số lần thử mặc định. Chọn tối thiểu dữ liệu đại diện và các kịch bản tập trung rủi ro.

## 103. Ma trận quyết định bằng điều kiện thay vì trực giác

Giả sử yêu cầu:

```text
Item/document max business payload: 600 KiB
One tenant may have 100 million events
Point reads need p99 < target
Per-booking conditional reservation mandatory
Reports scan last 2 years asynchronously
Restore RTO < specified bound
```

Quy trình:

1. Kiểm MongoDB document hard size, DynamoDB item hard size, CQL/Redis value model.
2. Nếu một hệ không nhận 600 KiB trong **một item**, đánh giá redesign split liệu vẫn giữ được transaction/invariant.
3. Dựng partition/key design cho 100 triệu events.
4. Tính số partitions/query fan-out.
5. Test hot tenant peak, không chỉ average.
6. Test conditional reservation correctness và conflicts.
7. Test async export paging/checkpoint.
8. Test full restore/verification within RTO.
9. So cost/SLO giữa các ứng viên **đã đạt knockout gates**.

Không kết luận “DynamoDB không phù hợp” chỉ vì item 600 KiB nếu nghiệp vụ có thể tách child records mà không phá invariant. Ngược lại, không chọn DynamoDB rồi giả tách luôn khả thi mà không thử transaction/access requirements.

## 104. Một scorecard có PASS/FAIL/INCONCLUSIVE

Ví dụ:

```yaml
candidate: "engine-X"
version: "<exact-version>"
deployment: "<region/topology/edition>"
recordSize:
  result: "PASS"
  evidence: "<measured-encoded-max>"
  hardLimitReference: "<official-doc-version>"
partition:
  result: "INCONCLUSIVE"
  reason: "hot-tenant 10x peak not tested"
operations:
  result: "PASS"
  evidence: "<batch-query-transaction-matrix>"
correctness:
  result: "PASS"
  evidence: "<invariants-and-history>"
performance:
  result: "PASS"
  evidence: "<histograms-and-goodput>"
recovery:
  result: "INCONCLUSIVE"
  reason: "full restore not rehearsed"
decision: "NO_GO_PENDING_EVIDENCE"
```

Khi còn một knockout `INCONCLUSIVE`, không tự điền PASS theo lời quảng cáo của vendor.

## 105. Quy trình đo kích thước bản ghi

1. Lấy fixture synthetic và mẫu production đã được ẩn danh theo policy.
2. Nhóm theo entity type/tenant/age/schema version.
3. Encode bằng driver/serializer thực.
4. Đo encoded bytes và accounting theo DB/API.
5. Đo logical content bytes riêng.
6. Ghi P50/P95/P99/max và sample coverage.
7. Kiểm Unicode/numbers/binary/nested fields.
8. Thử field mới, arrays lớn, encrypted values.
9. Cố tạo record gần hard limit **trong môi trường cô lập**.
10. Ghi error class/retryability và partial effects.
11. Đặt soft limit và cảnh báo tăng trưởng.
12. Thiết kế escape hatch: split child/blob/archival.

Không dùng một object “đại diện” để suy maximum trong tương lai.

## 106. Quy trình đo partition distribution

1. Xác định partition key logic và physical mapping khi có.
2. Thu bytes, rows và time-span per logical partition.
3. Đo request rate, write conflicts, retries per hot key.
4. Nhóm theo tenant/key cohort.
5. Kiểm skew/hot key trong peak periods.
6. Tính growth theo ngày/tháng.
7. Thử worst-case bucket/tenant.
8. Đo read fan-out và page count.
9. Đo compaction/repair/stream/restore tail.
10. So với resource headroom và SLO.
11. Thử alternate keys/buckets mà không phá invariants.
12. Đặt re-partition trigger trước khi soft limit bị vượt.

Không lấy `node CPU average=40%` để kết luận partition không nóng.

## 107. Quy trình đo giới hạn tác vụ

1. Inventory các operations: point read/write, query, scan, batch, transaction, aggregate, CDC, import/export, restore.
2. Chọn input/output size distribution.
3. Xác định max actions, bytes, partitions, time, memory và capacity cho API.
4. Dùng workload generator có offered load thật.
5. Ghi logical operations và physical attempts.
6. Đo partial/unprocessed items và retry.
7. Đo p95/p99 cùng errors/timeouts/UNKNOWN.
8. Kiểm CPU, disk, network, JVM heap/GC.
9. Kiểm background load, compaction, CDC lag.
10. Test cancellation/deadline/restart.
11. Xác minh business invariants.
12. Đặt bounded batch/concurrency/queue limits và alert.

Một benchmark “bulk writes 100k/s” thiếu idempotency/response-level evidence không đủ cho quyết định production.

## 108. Tình huống thất bại cần có trong kế hoạch

| Mã | Tình huống | Điều cần chứng minh |
| --- | --- | --- |
| F01 | Record vượt hard cap | Reject rõ và không partial business effect |
| F02 | Một field quá dài | Validation đúng encoding |
| F03 | Nested document sâu | Fail có kiểm soát |
| F04 | Array tăng không giới hạn | Bounded model/escape hatch |
| F05 | UTF-8 multibyte | Không nhầm char count với bytes |
| F06 | Client-side encryption expansion | Giới hạn trên encoded value |
| F07 | Blob upload thành công, DB metadata lỗi | Reconcile/orphan cleanup |
| F08 | DB commit, blob upload lỗi | Không công bố artifact sai |
| F09 | Hot single item | CAS/contention correctness |
| F10 | Hot tenant key | Quota/fairness |
| F11 | Partition vượt soft-size budget | Alert/split plan |
| F12 | Partition repair kéo dài | RTO/stop conditions |
| F13 | Hash bucketing tăng fan-out | Query SLO vẫn đạt |
| F14 | Time bucket có peak 20x | Headroom đo được |
| F15 | Full result > one page | Pagination đầy đủ |
| F16 | Continuation token hết hạn | Resume/error semantics |
| F17 | Page scan filter trả 0 item nhưng còn token | Không kết luận hết dữ liệu |
| F18 | Batch vượt item count cap | Client chunking trước gửi |
| F19 | Batch vượt byte cap | Flush theo size |
| F20 | Batch partial success | Retry only unprocessed |
| F21 | Batch timeout UNKNOWN | Receipt/idempotency reconcile |
| F22 | Transaction vượt action/byte cap | Bounded workflow alternative |
| F23 | Multi-key transaction contention | Invariant + retry budget |
| F24 | Aggregation tạo một output quá lớn | Bound output/group |
| F25 | Aggregation memory spill | Resource/deadline policy |
| F26 | CDC envelope quá lớn | Quarantine/rebuild no silent drop |
| F27 | CDC retention gap do consumer lag | Recovery plan |
| F28 | Redis huge hash/lua | Slowlog, event-loop health |
| F29 | Redis stream trimming events chưa ACK | Data safety gate |
| F30 | Cassandra huge partition/tombstones | Bounded query, repair |
| F31 | DynamoDB GSI write amplification | Cost/throttle |
| F32 | Mongo jumbo shard range | Migration path |
| F33 | Search deep pagination | Supported cursor/export |
| F34 | Graph supernode traversal | Fan-out bound |
| F35 | Import worker OOM | Heap/in-flight byte guard |
| F36 | Import job restart | Checkpoint/idempotent resume |
| F37 | Restore bottleneck oversized partition | Tail recovery SLA |
| F38 | Backup file valid nhưng logical records thiếu | Data verification |
| F39 | Tenant input gây unbounded scan | Auth/query budgets |
| F40 | API returns 200 with silently truncated results | Contract FAIL |
| F41 | 2xx batch ACK but skipped item | Per-item outcome checks |
| F42 | Retry storm inflates ops/s | Logical goodput |
| F43 | Large deletion reappears after replay | Tombstone/revision checks |
| F44 | Downgrade data model loses fields | Compatibility gate |
| F45 | Hot partition fails over to smaller capacity | Failover SLO |
| F46 | Sizing assumptions change after release | Alert/re-evaluate |
| F47 | One tenant exceeds quota and affects others | Isolation/fairness gate |
| F48 | Vendor quota increase not granted | Alternate architecture |

Các faults về dữ liệu/mất quyền/chuyển topology phải được chạy trong sandbox hoặc game day được phê duyệt. Không làm destructive production tests để có bằng chứng khi chưa kiểm soát blast radius.

## 109. Acceptance criteria cho bài đánh giá NoSQL

| Mã | Tiêu chí | Bằng chứng |
| --- | --- | --- |
| AC-01 | Mỗi limit ghi rõ đơn vị, scope, product version | Limit inventory |
| AC-02 | Hard vs soft vs quota được phân biệt | Scorecard |
| AC-03 | Có dẫn chứng quota chính thức đúng phiên bản | Source registry |
| AC-04 | Max item encoded size đã đo | Serializer/DB probe |
| AC-05 | P50/P95/P99/max của entity sizes có coverage | Size histogram |
| AC-06 | Unicode/null/nested/encrypted data được thử | Edge-case fixtures |
| AC-07 | Bounded growth cho arrays/collections | Schema review |
| AC-08 | Blob/media storage có consistency/recovery plan | Data flow and tests |
| AC-09 | Business invariants giữ khi tách records | Atomicity tests |
| AC-10 | Partition semantics engine-specific rõ | Data model |
| AC-11 | Per-key/per-tenant hotness đo dưới peak | Load report |
| AC-12 | P99/max partition bytes và rows được ghi | Distribution |
| AC-13 | Query fan-out sau bucket hóa chấp nhận | Access-pattern benchmark |
| AC-14 | Hot-key contention không phá correctness | CAS/ledger tests |
| AC-15 | Large partition recovery/repair được thử | RTO evidence |
| AC-16 | Batch count/byte/action limits được enforce | Client guard tests |
| AC-17 | Partial/unprocessed response được xử lý | Retry tests |
| AC-18 | UNKNOWN write outcome không bị coi failed | Receipt reconciliation |
| AC-19 | Max transaction scope và conflict rate được đo | Transaction tests |
| AC-20 | Pagination không bỏ token hoặc dữ liệu | Full result comparison |
| AC-21 | Aggregation memory/output size được giới hạn | Query plan/metrics |
| AC-22 | CDC event envelope/retention được xét | Stream checks |
| AC-23 | Import/export có checkpoints và coverage | Job manifest |
| AC-24 | Restore/backup có thử dữ liệu lớn nhất | Recovery drill |
| AC-25 | JVM heap/GC/in-flight bytes nằm trong budget | Profiling/metrics |
| AC-26 | Offered load vs confirmed goodput được phân biệt | Load report |
| AC-27 | Retry/timeout/throttle không bị giấu khỏi p99 | Outcome histogram |
| AC-28 | Tenant permissions/scope đúng dưới workload lớn | Auth negative tests |
| AC-29 | Không có silent truncation/drop | Correctness tests |
| AC-30 | Có forecast tới soft limit và trigger hành động | Capacity plan |
| AC-31 | Chi phí storage/index/replication/backup đủ scope | Cost model |
| AC-32 | Lựa chọn cuối cùng có knockout gates PASS | Signed decision |
| AC-33 | Các chỗ thiếu chứng cứ được ghi INCONCLUSIVE | Evidence report |
| AC-34 | Có phương án split/repartition/archival | Migration design |
| AC-35 | Có stop conditions khi job/cluster quá tải | Runbook |
| AC-36 | Sizing được review sau đổi schema/workload | Review cadence |

Một phần quota được mô tả trong marketing có thể không hiện diện với exact edition/version trong tổ chức; không ghi PASS cho điều chưa được kiểm.

## 110. Bài tập 1: tính kích thước document

Một document chứa:

```text
Fixed fields and metadata:       12 KiB
200 photos metadata:            800 bytes/photo
500 reviews previews:           300 bytes/review
```

Yêu cầu:

1. Tính payload gần đúng, phân biệt KiB với KB.
2. Nêu overhead chưa tính.
3. Nếu tăng lên 10.000 reviews, rủi ro nào xuất hiện?
4. Thiết kế lại với child records.
5. Giữ summary counters thế nào mà không sai?
6. Chọn phép đo encoded BSON/item thực.

## 111. Bài tập 2: hot partition trên một tenant

```text
Tenant T1: 1000 writes/s to one partition key.
Tenant T2..T1000: each 1 write/s.
```

Hỏi:

- Trung bình writes/key có phản ánh hotspot không?
- Tính key concentration.
- Nếu dùng 16 hash buckets, query tất cả records tăng fan-out thế nào?
- Một invariant đặt phòng cùng ngày bị ảnh hưởng gì?
- Có thể dùng per-slot owner/ledger không?
- Chọn metric và negative correctness tests.

## 112. Bài tập 3: giới hạn batch theo bytes

Giả sử **budget giả lập**:

```text
Max item encoded bytes: 2000
Max batch items: 3
Max batch bytes: 4000
Item sizes: 1500, 1800, 1000, 1900, 2500
```

Yêu cầu:

1. Phân nhóm items hợp lệ thành batches.
2. Item nào phải reject/redirect?
3. Nếu `UnprocessedItems` xuất hiện, retry thế nào?
4. Vì sao không dùng HTTP 200 làm batch-complete evidence?
5. Nếu mỗi retry đổi operationId thì có rủi ro gì?

## 113. Bài tập 4: time bucket trade-off

Một listing có:

```text
100,000 events/day
2 KiB/event
```

Yêu cầu:

- Tính payload một ngày và 30 ngày.
- Đánh giá partition size theo two bucket strategies.
- Truy vấn 365 ngày cần bao nhiêu partitions?
- Chọn workload cần async export.
- Dự báo ngày peak gấp 5 lần.
- Mô tả repair/restore test.

## 114. Bài tập 5: DynamoDB item và Query page

Một bảng có item 300 KB; query cần đọc 100 items, trong khi API trả pages giới hạn kích thước.

Yêu cầu:

- Vì sao một page không thể chứa cả 100 items?
- Viết logic duyệt `LastEvaluatedKey`.
- Phân biệt `Count` và `ScannedCount`.
- Tính read amplification khi filter bỏ nhiều records.
- So tính đúng của một page với complete logical result.
- Nêu quotas và endpoint variations cần xác minh ở tài liệu hiện hành.

## 115. Bài tập 6: Cassandra large partition

Một CQL partition `(tenant, month)` có 40 triệu rows, còn những partitions khác chỉ vài nghìn.

Yêu cầu:

- Chỉ ra các cơ chế gây read/repair slow.
- Đề xuất hourly/daily/key-shard buckets.
- Tính fan-out query lịch sử.
- Xem TTL/tombstones.
- Nếu yêu cầu CAS toàn tenant, chia partition có tác động gì?
- Xác định stop conditions cho re-partition migration.

## 116. Bài tập 7: Redis hot key

Một cache lưu danh sách 2 triệu item IDs trong một list và dùng `LRANGE 0 -1`.

Yêu cầu:

- Ước lượng output bytes từ item size trung bình.
- Xem list ordering/pagination semantics.
- Đề xuất bounded windows.
- Đo server CPU/network/client memory.
- Nếu Redis là source of truth, yêu cầu durability/backup nào?
- Không làm mất items khi migrate thế nào?

## 117. Bài tập 8: Import 10 triệu records

Một import job:

```text
10 million logical records
average item 2 KiB
safe apply speed 5000 items/s
```

Yêu cầu:
1. Ước lượng thời gian apply tối thiểu.
2. Tính raw logical payload ước lượng.
3. Đặt chunk and worker limits.
4. Thiết kế checkpoint/idempotency receipt.
5. Inject crash after effect before ACK.
6. Kiểm coverage/unique keys/digests.
7. Đánh giá RTO nếu job cần phục hồi sau sự cố.

## 118. Bài tập 9: chọn công nghệ theo knockout gates

Yêu cầu hệ:

```text
600 KiB logical object
critical conditional reservation
hot tenant 1000x normal
large export asynchronous
RTO under 1 hour
```

Hãy:
- Lập bảng record/partition/operation constraints.
- Xem split object có giữ invariant không.
- So MongoDB, DynamoDB, Cassandra/ScyllaDB, Redis theo roles đúng.
- Đặt workload/fault tests.
- Nêu trường hợp cần object storage.
- Chọn `PASS/FAIL/INCONCLUSIVE` cho mỗi gate trước khi score.

## 119. Bài tập 10: truy vấn nhanh nhưng kết quả thiếu

Một optimizer tăng tốc report từ 2 phút xuống 20 giây bằng cách bỏ toàn bộ pages sau page đầu của query.

Yêu cầu:
- Vì sao đây không phải optimization hợp lệ?
- Viết complete-result oracle theo stable keys/cut.
- Đo memory/bytes/time per page.
- Đề xuất async export.
- Thiết kế manifest/cursor/checkpoint.
- Quy định status “partial” rõ với caller.

## 120. Runbook khi xuất hiện record quá lớn

**Trigger:** client/DB báo size/validation error hoặc histogram P99/max tiến gần limit.

1. Xác nhận error là record size hay request/body/index limit.
2. Xác định entity type, schema/codec version và record ID đã redacted.
3. Đo encoded bytes bằng cách được hỗ trợ.
4. Kiểm array/field nào tăng.
5. Xác định item còn có in-flight writes hoặc UNKNOWN outcomes không.
6. Không tiếp tục retry một payload chắc chắn vượt hard limit.
7. Chặn input mới không hợp lệ với error rõ.
8. Chọn split child records/blob/archival hoặc hạn chế business cardinality.
9. Bảo toàn dữ liệu cũ và quan hệ/idempotency.
10. Migration có checkpoint, backup, consistency/cut.
11. Kiểm data completeness/invariants.
12. Đặt monitoring soft limit và regression fixture.

Không “truncate text/array” âm thầm vì làm mất dữ liệu để được một response thành công.

## 121. Runbook khi hot partition làm p99 tăng

**Trigger:** một key/tenant/partition có retry/throttle/latency bất thường.

1. Thu per-key/tenant/partition metrics có redaction.
2. So total cluster vs hotspot utilization.
3. Phân biệt read hot, write hot, CAS contention.
4. Kiểm change gần đây, backfill, TTL wave.
5. Giới hạn competing background jobs nếu policy cho phép.
6. Bật bounded retry/backoff, rate limit không phá service contract.
7. Kiểm cache hoặc read model có phù hợp freshness không.
8. Nếu phân vùng lại, phân tích invariant và query fan-out.
9. Triển khai từng cohort với ownership/migration protocol.
10. Đo business goodput, not just HTTP successes.
11. Reconcile missing/duplicate operations sau failover/retry.
12. Giữ stop condition khi new key design làm lost update.

Không tự giải hot partition bằng giảm consistency/durability nếu nó phá hợp đồng dữ liệu.

## 122. Runbook khi batch/transaction bị từ chối

1. Đọc exact service error code và request/response evidence.
2. Xác định item count/byte/action/timeout/consistency limit.
3. Xem server đã áp subset operations hay outcome UNKNOWN.
4. Giữ logical operation IDs.
5. Nếu API trả unprocessed subset, retry đúng subset với backoff.
6. Không đổi IDs hoặc replay non-idempotent increments tùy tiện.
7. Giảm batch size theo item-count và byte budget.
8. Hạn chế concurrency/hot partition pressure.
9. Với transaction quá lớn, redesign atomic scope/workflow.
10. Đối soát receipts/unique business effects.
11. Ghi retry amplification và goodput.
12. Cập nhật runbook/cảnh báo theo data size distribution.

## 123. Runbook khi import/export hết thời gian hoặc memory

1. Xác định task budget nào bị vượt: heap, disk, request, response, driver timeout, API quota.
2. Dừng retry storm và thu evidence.
3. Đánh giá checkpoint đã durable tới đâu.
4. Xác định chunks có trạng thái UNKNOWN.
5. Chuyển sang streaming/paged/bounded work nếu cần.
6. Kiểm per-tenant concurrency và backpressure.
7. Reconcile source/target logical keys, hashes và deletes.
8. Tiếp tục idempotent chunks với stable IDs.
9. Chỉ đánh job `COMPLETED` khi coverage đầy đủ.
10. Đo RTO và impact tới online API.
11. Cập nhật sizing model từ outlier thực.

## 124. Runbook trước quyết định chọn NoSQL

```text
[ ] Business objects/entities and growth bounds identified.
[ ] Hard item/document/value limits verified for exact version.
[ ] Nested/field/key constraints checked.
[ ] Wire/storage/encoded sizes not confused.
[ ] P50/P95/P99/max record sizes measured.
[ ] Schema evolution/encryption overhead included.
[ ] Blob/offloaded data consistency designed.
[ ] Partition/key model and query access patterns documented.
[ ] Hot tenant/key skew simulated.
[ ] P99/max partition bytes/rows measured.
[ ] Query fan-out and pagination planned.
[ ] Transaction/CAS boundaries preserve invariants.
[ ] Batch count/byte/action limits documented.
[ ] Partial/unprocessed and UNKNOWN outcomes handled.
[ ] CDC event/broker envelope and replay retention checked.
[ ] Async import/export has checkpoint and idempotency.
[ ] JVM heap/concurrency/resource budgets tested.
[ ] Index/storage/replication/backup amplification modeled.
[ ] Full restore and data verification meet RPO/RTO.
[ ] Negative auth/tenant isolation tests passed.
[ ] Performance measured at normal, peak and edge workloads.
[ ] Goodput counts correct confirmed business operations.
[ ] Cost model includes index, CDC, backup and egress.
[ ] Soft limits, alerts and migration triggers set.
[ ] Hard knockout criteria all PASS.
[ ] INCONCLUSIVE items assigned owner and due date.
[ ] Decision record includes evidence sources and versions.
```

## 125. Mẫu tài liệu quyết định

```markdown
# NoSQL Limits Evaluation

## Business and workload
- Critical entities and sizes:
- Growth assumptions and outliers:
- Tenant and hot-key distribution:
- Access patterns and consistency:
- Business invariants:
- Target read/write SLO and RPO/RTO:

## Record constraints
- Logical and serialized size distributions:
- Engine hard cap by version:
- Nesting/key/index constraints:
- Planned feature/data-format growth:
- Soft limits and escape hatches:

## Partition constraints
- Logical partition key:
- P50/P95/P99/max bytes and row count:
- Peak reads/writes per key:
- Hot key skew and fairness:
- Query fan-out:
- Repair/backup/restore tail:

## Operation constraints
- Query/scan page limits:
- Batch/transaction count and bytes:
- Aggregation memory and output:
- Import/export job limits:
- CDC event envelope and retention:
- Timeouts/retries/UNKNOWN behavior:
- Java heap and concurrency budgets:

## Experiments
- Dataset/fixture version:
- Driver/server/edition/Region:
- Normal/peak/stress workload:
- Correctness and security gates:
- Latency/goodput/cost evidence:
- Failure injection and recovery:

## Candidate decision
- Knockout PASS/FAIL/INCONCLUSIVE:
- Trade-offs and weighted score if applicable:
- Migration and rollback strategy:
- Headroom, alerts and re-evaluation triggers:
- Source links, report hashes and approvals:
```

## 126. Những hiểu nhầm cần loại bỏ

**“Cluster lưu được petabytes nghĩa một document không giới hạn.”** Sai; object có hard cap riêng.

**“Item trung bình 5 KB thì mọi item đều nhỏ.”** Extreme cases/max có thể phá API.

**“Java String.length() là bytes lưu trữ.”** Không phải UTF-8/DB encoding.

**“JSON payload size bằng BSON/DynamoDB item size.”** Không; encoding/accounting khác.

**“Compression giúp mọi object vượt hard limit.”** Hard limit được áp theo quy tắc engine, không thể suy từ tỷ lệ nén.

**“Tách ảnh sang object storage là xong.”** Cần owner, integrity, orphan cleanup và restore.

**“Mỗi document dưới cap thì data model ổn.”** Unbounded growth, hot updates, repair và read amplification vẫn có thể sai.

**“Tổng dữ liệu 1TB nhỏ hơn 10TB cluster nên không có hot partition.”** Không suy ra.

**“Một logical partition key luôn phân tán đều lên nhiều nodes.”** Tùy engine.

**“Hash sharding không ảnh hưởng query hoặc transaction.”** Có thể tăng fan-out, phá atomicity.

**“Partition bytes thấp nghĩa không hot.”** Write contention và RPS cũng quan trọng.

**“Phân vùng theo ngày luôn tốt hơn theo tháng.”** Query fan-out và overhead phải cân bằng.

**“Soft limit là con số nhà cung cấp cam kết.”** Soft limit do workload/SLO/recovery quyết định.

**“DynamoDB 400KB item nghĩa 400KB JSON response là hợp lệ.”** Item size accounting có quy tắc riêng.

**“Query có Limit=1000 là chắc trả 1000 rows.”** Pagination và filter semantics có thể khác.

**“Batch API là một ACID transaction.”** Không mặc định.

**“BatchWrite success nghĩa tất cả items đều applied.”** Phải kiểm unprocessed items.

**“Một write timeout nghĩa không commit.”** Có thể commit rồi mất ACK.

**“Chia transaction thành chunks tự giữ atomic toàn workflow.”** Cần publication protocol/reconciliation.

**“Một output aggregation nhỏ nghĩa memory ít.”** Intermediate stages có thể rất lớn.

**“CDC luôn chấp nhận mọi record DB chấp nhận.”** Event envelope/broker/consumer có limits riêng.

**“Redis PING nhanh nên HGETALL key lớn cũng nhanh.”** Độ phức tạp/payload khác nhau.

**“SCAN trả snapshot nhất quán khi keyspace đổi.”** Không mặc định.

**“Cassandra full COUNT không tốn tài nguyên vì database phân tán.”** Có thể quét nhiều partitions.

**“Thêm nodes tự chia một CQL partition key cực lớn.”** Key model không đổi chỉ vì scale-out.

**“Cloud auto scaling xử lý mọi single-key hotspot.”** Localized capacity contention vẫn có thể tồn tại.

**“Một benchmark đọc rất nhanh chứng minh backup phục hồi nhanh.”** RTO phải diễn tập riêng.

**“Một report chạy nhanh nhờ bỏ những pages cuối là tối ưu hợp lệ.”** Đó là sai dữ liệu.

**“API 202 nghĩa import hoàn thành.”** Chỉ là một trạng thái tiếp nhận theo contract.

**“Goodput bằng DB attempts/s.”** Không tính retry/duplicate như business effects mới.

**“Tăng max timeout luôn tốt.”** Có thể tăng queue, in-flight memory và retry storm.

**“Giới hạn kích thước là chuyện DevOps, không ảnh hưởng nghiệp vụ.”** Có thể đổi tính nguyên tử, quyền, consistency và cách phục vụ.

**“Một điểm score cao có thể bù hard-limit FAIL.”** Knockout criteria phải tách.

## Kết luận

**Đánh giá giới hạn kích thước bản ghi, phân vùng và tác vụ** là một bước bắt buộc khi chọn và thiết kế NoSQL, bởi ba loại giới hạn giải quyết ba rủi ro khác nhau. **Bản ghi** có thể chạm hard cap của serializer/engine/API hoặc trở nên quá lớn để đọc/ghi hiệu quả. **Phân vùng** có thể thành hot key, jumbo partition hoặc đuôi phục hồi kéo dài dù tổng dung lượng cluster còn rất lớn. **Tác vụ** có thể vượt giới hạn số actions, bytes, time, memory, transaction scope, paging hoặc CDC envelope, dẫn đến timeout, partial success, retry storm và dữ liệu thiếu/trùng nếu xử lý sai.

Phương pháp đáng tin cậy là tạo **limit inventory đúng phiên bản**, đo phân bố **P50/P95/P99/max và growth**, thiết kế theo **access patterns + business invariants**, rồi thử **normal/peak/edge workloads, failover và restore**. Các biện pháp như tách child records, object storage, time/hash buckets, bounded paging, chunked import và asynchronous jobs có thể giúp mở rộng, nhưng mỗi biện pháp phải được kiểm thêm về **read fan-out, atomicity, idempotency, authorization, delete semantics và phục hồi**. Không đánh đổi dữ liệu đúng lấy một request nhanh hoặc một batch lớn.

Khi so sánh MongoDB, DynamoDB, Cassandra/ScyllaDB, Redis và những NoSQL khác, **hard limits và correctness là điều kiện loại**, còn latency, verified goodput, chi phí và độ phức tạp vận hành là các tiêu chí đánh đổi **sau khi** ứng viên đã qua điều kiện bắt buộc. Nếu thiếu bằng chứng về hot tenant, record outlier, batch partial outcomes hoặc RTO thực, trạng thái đúng là **INCONCLUSIVE**, không phải PASS. Một lựa chọn tốt không chỉ lưu được dữ liệu hôm nay, mà còn **chịu được bản ghi lớn nhất, partition nóng nhất, tác vụ dài nhất và lần phục hồi khó nhất trong phạm vi sản phẩm đã cam kết**.
