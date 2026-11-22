# Di chuyển dữ liệu, đối soát và xác minh toàn vẹn

## 1. Vì sao migration cần quy trình kiểm chứng?

Di chuyển dữ liệu là việc chuyển dữ liệu và khả năng phục vụ nghiệp vụ từ nguồn sang đích: đổi database engine, nâng cấp phiên bản, chuyển lên cloud, tách một hệ thống lớn thành nhiều service, thay schema hoặc đưa dữ liệu lịch sử sang nền tảng mới. Công việc này không kết thúc khi lệnh copy trả về thành công. Hệ thống chỉ có thể chuyển sang trạng thái vận hành mới khi chứng minh dữ liệu đích đầy đủ, đúng ý nghĩa, nhất quán và các ứng dụng có thể tiếp tục xử lý nghiệp vụ.

Một lần migration có thể gặp nhiều rủi ro:

- Record bị thiếu, lặp, cắt cụt hoặc chuyển kiểu sai.
- Mất quan hệ giữa bảng, khóa ngoại hoặc tham chiếu logic.
- Dữ liệu thay đổi ở nguồn trong lúc copy nên snapshot và đích không cùng một thời điểm.
- Schema mới diễn giải timestamp, tiền tệ, collation, null hoặc encoding khác nguồn.
- Trigger, sequence, identity, default, index, constraint hay permission không được chuyển đúng.
- CDC hoặc dual-write bỏ lỡ thay đổi, áp dụng sai thứ tự hoặc phát lại cùng một change nhiều lần.
- Cutover hoàn tất nhưng ứng dụng, báo cáo, job nền hoặc consumer vẫn ghi vào nguồn cũ.
- Rollback không đơn giản vì dữ liệu mới đã phát sinh ở hệ thống đích.

Do đó, một kế hoạch migration cần trả lời bốn câu hỏi: **chuyển cái gì, chuyển như thế nào, chứng minh đúng ra sao, và làm gì khi phát hiện sai?**

Trong module **CLOUD_ARCHITECTURE**, di chuyển dữ liệu phải được thiết kế như một thay đổi kiến trúc có ảnh hưởng tới độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành. Đối soát và xác minh toàn vẹn là cơ sở để quyết định có tiếp tục cutover, dừng lại hay khôi phục.

### Mục tiêu học tập

Sau bài học, bạn có thể:

1. Lập inventory dữ liệu, dependency, schema và yêu cầu downtime trước khi migration.
2. Chọn offline migration, online migration, snapshot, replication hoặc CDC.
3. Xây dựng chiến lược expand-migrate-contract và cutover có kiểm soát.
4. Thiết kế batch, checkpoint, retry và migration job có thể chạy lại an toàn.
5. Đối soát số lượng, tổng hợp, checksum, khóa, quan hệ và invariant nghiệp vụ.
6. Xử lý dữ liệu thay đổi trong lúc migration, duplicate event và sai lệch giữa nguồn/đích.
7. Chuẩn bị rollback, reconciliation, quan sát và tiêu chí nghiệm thu.

## 2. Phân biệt migration, replication, synchronization và reconciliation

Các thuật ngữ này có liên hệ nhưng không đồng nghĩa:

| Khái niệm | Mục đích | Ví dụ |
|---|---|---|
| **Migration** | Chuyển dữ liệu hoặc workload sang hệ thống/schema/địa điểm mới | Database từ VM sang managed database |
| **Replication** | Duy trì bản sao dữ liệu từ nguồn sang một hoặc nhiều đích | Read replica nhận transaction log |
| **Synchronization** | Giữ hai tập dữ liệu cập nhật theo quy tắc đã định | Đồng bộ hồ sơ khách hàng giữa hai service |
| **CDC (Change Data Capture)** | Thu thập thay đổi phát sinh tại nguồn sau một mốc | Đọc WAL/binlog/change stream rồi áp dụng ở đích |
| **Reconciliation (đối soát)** | So sánh dữ liệu hoặc kết quả giữa các phía để phát hiện sai lệch | So sánh tổng booking theo ngày và danh sách record khác nhau |
| **Integrity verification** | Kiểm tra dữ liệu còn nguyên vẹn theo cấu trúc và nội dung | Checksum file, constraint, hash theo batch |

Replication có thể chạy tốt nhưng đích vẫn sai do mapping schema hoặc logic transform. Hai hệ thống có cùng số record nhưng giá trị field khác nhau. Checksum giống nhau trên file dump không chứng minh ứng dụng truy vấn và tính toán đúng sau import. Vì vậy cần nhiều lớp kiểm chứng.

## 3. Bắt đầu bằng inventory và phân tích tác động

Không nên chọn công cụ trước khi biết dữ liệu và dependency nào cần chuyển.

### 3.1. Inventory dữ liệu

Với mỗi dataset/table/collection/file group, ghi nhận:

| Thuộc tính | Nội dung cần thu thập |
|---|---|
| Owner | Team chịu trách nhiệm nghiệp vụ và kỹ thuật |
| Source / destination | Hệ thống, database, schema, bucket, region |
| Volume | Số record/object, dung lượng, tốc độ tăng |
| Change rate | Số insert/update/delete mỗi giây hoặc mỗi ngày |
| Access pattern | Đọc/ghi, truy vấn chính, batch job và báo cáo |
| Schema | Column/type, index, key, constraint, enum, collation |
| Relationship | Foreign key, reference logic, join, event contract |
| Sensitivity | PII, payment data, secret, classification |
| Retention | Thời hạn, legal hold, yêu cầu xóa và bản sao |
| Downtime tolerance | Thời gian gián đoạn cho phép |
| Recovery | RPO, RTO và phương án quay lại |
| Validation | Count, aggregate, checksum, invariant và sample query |

### 3.2. Dependency inventory

Database không chỉ được sử dụng bởi một API. Cần tìm tất cả thành phần có thể đọc hoặc ghi:

- Web/mobile API và internal service.
- Background worker, scheduled job và serverless function.
- Data warehouse, BI dashboard, ETL/ELT và export.
- Search index, cache, materialized view và read replica.
- Webhook, event consumer, integration partner và reconciliation job.
- Admin console, script thủ công và tác vụ vận hành.

Nếu bỏ sót một writer, sau cutover nó có thể tiếp tục ghi vào source cũ, làm dữ liệu phân nhánh. Một reader bỏ sót có thể vẫn hiển thị dữ liệu cũ dù API chính đã chuyển.

### 3.3. Khảo sát đặc tính dữ liệu

Kiểm tra trước:

- Primary key có duy nhất, ổn định và không null không?
- Có record thiếu foreign key hoặc reference tới object đã bị xóa không?
- Có timestamp không timezone, decimal precision, số âm, giá trị cực lớn hoặc encoding đặc biệt không?
- Dữ liệu có duplicate theo business key dù primary key khác nhau không?
- Có trigger, stored procedure, generated column, sequence, identity hay default phụ thuộc engine không?
- Có transaction dài, lock contention, table partition, large object hoặc dữ liệu nén không?
- Có row-level security, encryption, collation, case sensitivity hoặc khác biệt sort order không?

Đây là nơi phát hiện sớm các khác biệt giữa engine nguồn và đích trước khi chúng biến thành dữ liệu sai sau cutover.

## 4. Chọn chiến lược migration

### 4.1. Offline migration (cắt dịch vụ trong cửa sổ)

Ứng dụng tạm ngừng ghi hoặc vào chế độ maintenance; dữ liệu được export, transform, import, kiểm chứng rồi mở dịch vụ ở đích.

**Phù hợp khi:** dataset vừa/nhỏ, downtime được chấp nhận, có cửa sổ bảo trì rõ hoặc hệ thống ít thay đổi.

**Ưu điểm:** quy trình đơn giản hơn, có thể dùng một snapshot nhất quán, ít phức tạp về đồng bộ song song.

**Đánh đổi:** downtime tăng theo dung lượng, tốc độ export/import và thời gian kiểm tra. Nếu bản chuyển thất bại, cần giữ nguồn phục vụ hoặc phục hồi từ backup.

### 4.2. Online migration (giảm downtime)

Copy baseline trong khi source vẫn phục vụ, đồng thời capture thay đổi để đưa đích gần bắt kịp. Khi cutover, hệ thống tạm dừng hoặc giới hạn write ngắn, chờ replication lag về ngưỡng, xác minh rồi chuyển traffic.

**Phù hợp khi:** database lớn, thay đổi liên tục, downtime thấp hoặc yêu cầu kinh doanh cao.

**Đánh đổi:** vận hành phức tạp hơn; cần xử lý thứ tự transaction, delete, schema change, duplicate, lag, consistency và failure recovery.

### 4.3. So sánh các cách chuyển

| Phương pháp | Đặc điểm | Rủi ro chính |
|---|---|---|
| Full export/import | Dump toàn bộ rồi nạp vào đích | Downtime, snapshot consistency, tốc độ và dung lượng file |
| Snapshot/backup restore | Tạo snapshot nhất quán rồi phục hồi | Engine/version compatibility, log replay và restore time |
| Replication | Nguồn liên tục gửi thay đổi sang đích | Lag, format/version compatibility, failover behavior |
| CDC | Thu thay đổi từ transaction log/change stream | Checkpoint, offset, ordering, schema evolution và duplicate |
| Dual-write ở ứng dụng | Ứng dụng ghi cả source và destination | Partial success, khác biệt transaction và retry |
| Bulk batch migration | Chuyển theo key range/partition/time window | Batch boundary, checkpoint, record bị bỏ sót hoặc xử lý lặp |

Không có một phương pháp tốt nhất cho mọi dataset. Có thể kết hợp bulk load cho baseline, CDC cho delta và reconciliation trước cutover.

## 5. Chiến lược online migration: baseline + CDC

Luồng tổng quát:

~~~mermaid
flowchart TD
    Source[("Source database")]
    Snapshot["Consistent snapshot + watermark"]
    Bulk["Bulk copy / transform"]
    Target[("Target database")]
    Log["Transaction log / change stream"]
    CDC["CDC capture + apply"]
    Reconcile["Reconciliation"]
    Cutover["Controlled cutover"]
    Source --> Snapshot
    Snapshot --> Bulk
    Bulk --> Target
    Source --> Log
    Log --> CDC
    CDC --> Target
    Target --> Reconcile
    Reconcile --> Cutover
~~~

Một quy trình tham khảo:

1. Tạo mốc snapshot/watermark có thể liên kết với transaction log hoặc CDC position.
2. Export baseline tại snapshot nhất quán.
3. Load baseline vào target theo batch và ghi checkpoint.
4. Capture các thay đổi phát sinh sau watermark.
5. Áp dụng CDC vào target, theo đúng thứ tự và semantics transaction mà công cụ hỗ trợ.
6. Theo dõi replication lag, lỗi apply, record bị bỏ qua và schema compatibility.
7. Chạy đối soát song song trên source/target.
8. Tạm dừng writer hoặc bật write fence ở thời điểm cutover.
9. Chờ delta cuối cùng được áp dụng, xác minh invariant và chuyển traffic.
10. Theo dõi đích, giữ source theo trạng thái read-only/standby trong giai đoạn rollback được duyệt.

Watermark phải được định nghĩa theo semantics của công cụ: log sequence number, binlog position, change token hoặc snapshot ID. Không dùng một timestamp tùy tiện thay thế checkpoint nếu các transaction cùng thời điểm có thể được ghi/commit theo thứ tự khác nhau.

## 6. Schema migration và expand-migrate-contract

Migration dữ liệu thường đi cùng thay đổi schema. Thay schema đột ngột có thể làm ứng dụng cũ và mới không tương thích.

Mẫu **expand-migrate-contract** chia thay đổi thành các giai đoạn:

1. **Expand:** thêm cột/bảng/index mới theo cách tương thích ngược; chưa xóa field cũ.
2. **Dual-compatible application:** phiên bản ứng dụng có thể đọc/ghi schema cũ và mới theo chiến lược được kiểm soát.
3. **Backfill:** chuyển dữ liệu cũ sang field/schema mới theo batch.
4. **Verify:** kiểm tra dữ liệu mới đầy đủ và ứng dụng đọc đúng.
5. **Switch reads/writes:** chuyển dần code sang schema mới; theo dõi sai lệch.
6. **Contract:** chỉ xóa cột/bảng/API cũ sau khi chắc chắn không còn consumer hoặc writer phụ thuộc.

~~~mermaid
flowchart LR
    A["Schema cũ"] --> B["Expand: thêm schema mới"]
    B --> C["App tương thích cả hai"]
    C --> D["Backfill dữ liệu cũ"]
    D --> E["Verify và switch traffic"]
    E --> F["Contract: loại bỏ schema cũ"]
~~~

### Ví dụ thêm cột mới

Giả sử cần đổi cột full_name thành display_name:

~~~sql
ALTER TABLE customers
ADD COLUMN display_name VARCHAR(200);
~~~

Không xóa cột full_name ngay. Ứng dụng mới có thể tạm đọc display_name nếu có, fallback sang full_name; backfill các giá trị cũ; sau khi mọi client đã chuyển và dữ liệu được xác minh mới cân nhắc contract.

### Lưu ý khi dual-write field

Nếu ứng dụng ghi cả field cũ và mới, hai field có thể lệch khi một write thành công còn write kia thất bại. Nên định nghĩa một field source of truth, cách retry/reconcile và thời điểm ngừng dual-write. Với schema thay đổi lớn, dùng CDC hoặc backfill có version/checkpoint thay vì dựa hoàn toàn vào logic dual-write ở nhiều phiên bản app.

## 7. Batch processing, checkpoint và idempotency

Với dữ liệu lớn, chuyển theo batch giúp giới hạn memory, thời gian transaction và khả năng retry. Tuy nhiên cần định nghĩa batch boundary rõ.

### 7.1. Chọn batch key

Có thể phân vùng theo:

- Primary key range nếu key ổn định và phân bố phù hợp.
- Time window nếu dữ liệu có timestamp đáng tin và ít late-arriving records.
- Partition có sẵn của database.
- Hash bucket nếu cần phân phối đều tải.

Tránh OFFSET pagination lớn vì có thể chậm và thay đổi vị trí khi dữ liệu nguồn bị insert/delete. Keyset pagination theo khóa ổn định thường dễ checkpoint hơn.

### 7.2. Checkpoint

Mỗi batch nên ghi tối thiểu:

| Trường | Ý nghĩa |
|---|---|
| migration_id | Định danh đợt migration |
| dataset/table | Phạm vi dữ liệu |
| lower_bound / upper_bound | Khoảng key hoặc partition xử lý |
| source_watermark | Mốc nguồn hoặc CDC position |
| status | PENDING, RUNNING, VERIFIED, FAILED |
| rows_read / rows_written | Số bản ghi nguồn và đích |
| checksum/aggregate | Bằng chứng batch |
| attempt | Số lần thực hiện |
| started_at / completed_at | Theo dõi thời gian |
| error_reference | Link/log tham chiếu lỗi, không chứa secret |

### 7.3. Job phải chạy lại an toàn

Một migration job cần idempotent hoặc có cơ chế xác định batch đã hoàn tất. Ví dụ dùng deterministic key và upsert có kiểm soát, nhưng upsert không tự giải quyết conflict nếu source thay đổi sau watermark.

Quy tắc:

- Không đánh dấu batch VERIFIED trước khi dữ liệu đích được kiểm tra.
- Nếu job chết sau load nhưng trước checkpoint, lần chạy lại phải phát hiện hoặc xử lý duplicate an toàn.
- Không dùng timestamp của worker làm bằng chứng duy nhất về thứ tự dữ liệu.
- Ghi lại số record bị transform reject, quarantine hoặc skip; không im lặng bỏ qua.
- Có giới hạn tốc độ để không làm cạn connection, IOPS hoặc throughput của source/target.

~~~text
for each key_range in migration_plan:
    if checkpoint[key_range] == VERIFIED:
        continue

    source_rows = read_source_consistently(key_range)
    transformed = transform_and_validate(source_rows)
    write_target_idempotently(transformed)

    result = compare_batch(source_rows, transformed, target_rows)
    if result.matches:
        save_checkpoint(key_range, VERIFIED, result.metrics)
    else:
        save_checkpoint(key_range, FAILED, result.error_reference)
        stop_or_quarantine_according_to_policy()
~~~

Đây là pseudocode mô tả logic; cách tạo snapshot, transaction, upsert và checkpoint phụ thuộc database và migration tooling.

## 8. Đối soát dữ liệu nhiều lớp

Một phép so sánh duy nhất hiếm khi đủ. Đối soát tốt đi từ số lượng tổng quát tới nội dung chi tiết và invariant nghiệp vụ.

### 8.1. Layer 1 — Row/object count

So sánh tổng record/object theo dataset, partition, time window và trạng thái.

Ví dụ:

~~~sql
SELECT status, COUNT(*) AS row_count
FROM reservations
GROUP BY status
ORDER BY status;
~~~

Chạy cùng logic ở source và target tại snapshot/checkpoint tương ứng. Hai tổng số có thể bằng nhau dù một record bị thiếu và một record bị duplicate, vì vậy count chỉ là bước đầu.

### 8.2. Layer 2 — Aggregate đối soát

So sánh các tổng hợp như:

- Tổng amount theo currency, trạng thái và ngày.
- Tổng số booking theo tenant/property.
- Min/max timestamp hoặc ID.
- Tổng quantity, balance hoặc count theo partition.
- Số null, số giá trị ngoài miền, số duplicate theo business key.

~~~sql
SELECT
    currency,
    status,
    COUNT(*) AS txn_count,
    SUM(amount) AS total_amount
FROM payments
GROUP BY currency, status
ORDER BY currency, status;
~~~

Không cộng tiền từ nhiều currency thành một tổng nếu không có quy tắc quy đổi và thời điểm tỷ giá được xác định. Decimal precision/rounding cũng phải nhất quán.

### 8.3. Layer 3 — Key-level comparison

Đối chiếu tập primary key/business key:

- Key có ở source mà thiếu ở target.
- Key có ở target nhưng không có trong source.
- Duplicate theo business key.
- Key bị transform/truncate hoặc đổi format.

Nếu dataset rất lớn, có thể phân vùng key space, dùng anti-join, hash bucket hoặc manifest. Cần chạy trên cùng snapshot/CDC watermark; so sánh hai hệ thống ở hai thời điểm khác nhau dễ tạo false mismatch.

### 8.4. Layer 4 — Field-level comparison

So sánh các field quan trọng theo mapping:

- Nullability và default.
- Kiểu số, precision, scale, overflow.
- Timestamp, timezone và độ chính xác.
- String encoding, Unicode normalization, collation và case sensitivity.
- Enum/code mapping.
- JSON/document structure.
- Binary/blob content.

Không nhất thiết phải so byte-for-byte khi chuyển engine có representation khác nhưng cùng semantics. Cần có canonicalization rule được định nghĩa trước để so sánh tương đương nghiệp vụ.

### 8.5. Layer 5 — Referential và business invariant

Ví dụ:

- Mọi reservation đã CONFIRMED phải tham chiếu property hợp lệ.
- Mọi payment capture phải liên kết được với một payment intent/booking hợp lệ.
- Balance ledger phải thỏa tổng debit/credit theo quy tắc.
- Một property không có hai booking CONFIRMED chồng lấn thời gian nếu chính sách không cho phép.
- Tenant của child record phải khớp tenant của parent.
- Số lượng inventory không âm.

Đây là lớp quan trọng nhất về ngữ nghĩa: dữ liệu có thể có cùng count và checksum nhưng vẫn vi phạm quy tắc nghiệp vụ nếu transform hoặc mapping sai.

## 9. Checksum, hash và giới hạn của chúng

Checksum/hash giúp phát hiện khác biệt nội dung, đặc biệt với file, batch hoặc object.

### 9.1. Hash theo batch

Quy trình khái niệm:

1. Chọn cùng tập record bằng key range và source watermark.
2. Chuẩn hóa các field theo quy tắc được thống nhất.
3. Serialize theo thứ tự xác định, encoding xác định.
4. Tính hash từng record hoặc chunk.
5. So sánh hash aggregate/manifest ở source và target.
6. Khi mismatch, chia nhỏ chunk để khoanh vùng record khác nhau.

Không hash JSON theo thứ tự property tùy ý rồi kết luận nội dung khác; cần canonical serialization. Với field nhạy cảm, không đưa plaintext vào manifest hoặc log.

### 9.2. Checksum file không chứng minh logic database đúng

Nếu hash file export và file transfer giống nhau, ta biết byte của file không đổi trong quá trình truyền theo thuật toán hash đã dùng. Điều đó không chứng minh:

- Import đã nạp đủ record.
- Schema mapping đúng.
- Index/constraint hoạt động.
- Trigger/default/sequence được thiết lập đúng.
- Dữ liệu truy vấn và nghiệp vụ cho kết quả như source.

Do đó checksum cần đi cùng row count, aggregate, key comparison, constraint validation và test ứng dụng.

## 10. Referential integrity và thứ tự nạp dữ liệu

Nếu database có foreign key, thứ tự load và constraint strategy rất quan trọng.

Một thứ tự phổ biến:

1. Lookup/reference tables.
2. Parent/master entities.
3. Child/detail entities.
4. Association/join tables.
5. Ledger/event/history theo dependency.
6. Materialized view, search index và dữ liệu dẫn xuất có thể tái tạo.

Tùy engine có thể defer constraint hoặc disable rồi validate lại sau load. Không để constraint bị tắt khi đưa hệ thống vào vận hành; cần xác minh constraint được enable/validated.

### Kiểm tra orphan record

~~~sql
SELECT r.reservation_id
FROM reservations r
LEFT JOIN properties p ON p.property_id = r.property_id
WHERE p.property_id IS NULL;
~~~

Kết quả mong muốn là không có record orphan, trừ trường hợp nghiệp vụ cho phép reference lịch sử được lưu dưới dạng snapshot hoặc tombstone. Nếu có ngoại lệ, phải định nghĩa rõ và không che giấu bằng cách bỏ qua constraint.

### Duplicate business key

~~~sql
SELECT tenant_id, external_reference, COUNT(*) AS duplicates
FROM payments
GROUP BY tenant_id, external_reference
HAVING COUNT(*) > 1;
~~~

Business key cần được xác định theo domain. Hai record có primary key khác nhau vẫn có thể đại diện cùng một giao dịch nghiệp vụ.

## 11. Migration dữ liệu thay đổi liên tục: CDC và ordering

CDC đưa thay đổi từ nguồn sang đích trong khi hệ thống vẫn hoạt động. Cần hiểu:

- **Capture point:** thay đổi được lấy từ WAL/binlog/change feed hay trigger?
- **Checkpoint/offset:** vị trí nào đã được đọc và xác nhận?
- **Ordering:** thứ tự trong một partition/table/transaction có được bảo toàn không?
- **Delete:** delete được biểu diễn bằng tombstone hay operation riêng?
- **Schema evolution:** thay đổi cột/type có tương thích với consumer không?
- **Duplicate:** consumer có thể nhận lại change khi restart/failover không?
- **Backpressure:** target chậm thì lag tăng ra sao, log nguồn có bị giữ lâu tới mức tăng storage?
- **Snapshot coordination:** baseline và change stream có tránh overlap/gap không?

CDC thường có semantics ít nhất một lần hoặc có khả năng phát lại tùy công cụ. Consumer/apply process cần idempotent hoặc dùng source transaction identity để không áp dụng cùng change hai lần một cách sai lệch.

Không nên giả định mọi event được phát theo một thứ tự toàn cục. Nhiều hệ thống chỉ bảo toàn thứ tự trong partition hoặc theo key. Nếu một entity cần tuần tự hóa, partition key và apply logic phải được thiết kế theo entity đó.

## 12. Reconciliation job sau cutover

Đối soát không chỉ chạy một lần trước cutover. Trong giai đoạn vận hành song song hoặc sau chuyển đổi, cần job định kỳ phát hiện dữ liệu trôi lệch.

Một reconciliation pipeline:

~~~mermaid
flowchart TD
    Schedule["Scheduled reconciliation"] --> Scope["Chọn dataset / time window"]
    Scope --> Extract["Đọc source / target snapshot"]
    Extract --> Compare["Count + aggregate + key + invariant"]
    Compare --> Result{"Match?"}
    Result -->|Có| Record["Ghi manifest và kết quả"]
    Result -->|Không| Classify["Phân loại mismatch"]
    Classify --> Repair["Repair / replay / manual review"]
    Repair --> Verify["Chạy lại đối soát"]
    Verify --> Result
    Record --> Monitor["Dashboard / alert"]
~~~

### Phân loại sai lệch

| Loại mismatch | Ví dụ | Cách xử lý |
|---|---|---|
| Missing | Source có record, target thiếu | Replay theo key/checkpoint hoặc reload batch |
| Extra | Target có record không có trong source | Xác định duplicate, write mới hợp lệ hay dữ liệu rác |
| Value mismatch | Amount/timezone/status khác | Kiểm tra transform, rounding, mapping và source of truth |
| Relationship mismatch | Foreign key/reference không hợp lệ | Khôi phục parent, mapping ID hoặc xử lý orphan theo policy |
| Timing mismatch | Một bên có thay đổi mới hơn | Đợi CDC bắt kịp hoặc so sánh cùng watermark |
| Business invariant violation | Inventory âm, payment không có booking | Dừng cutover hoặc sửa bằng workflow nghiệp vụ có audit |

Không tự động ghi đè source hoặc target chỉ dựa trên phía nào có timestamp mới hơn. Cần xác định hệ thống nào là source of truth cho từng field và có operation nào đã được người dùng/đối tác thực hiện sau migration không.

## 13. Cutover: chuyển quyền phục vụ có kiểm soát

Cutover là thời điểm traffic hoặc quyền ghi chuyển từ source sang target. Đây là bước có rủi ro cao nhất vì có thể tạo hai nguồn sự thật.

### 13.1. Cutover checklist theo trình tự

1. Đóng băng schema và code change liên quan, trừ thay đổi đã được kiểm soát.
2. Xác nhận backup/source recovery point đã sẵn sàng.
3. Kiểm tra target capacity, index, constraint, permission, monitoring và security.
4. Chạy baseline reconciliation và kiểm tra CDC lag.
5. Thông báo maintenance/degraded mode nếu cần.
6. Tạm dừng hoặc fence toàn bộ source writer; xác nhận không còn writer bị bỏ sót.
7. Chờ transaction cuối và CDC apply tới watermark đã chọn.
8. Chạy final validation trên dữ liệu và invariant trọng yếu.
9. Chuyển connection string, DNS, routing hoặc feature flag theo kế hoạch.
10. Chạy smoke test/read-write test bằng luồng có kiểm soát.
11. Theo dõi error rate, latency, connection, constraint failure và nghiệp vụ.
12. Giữ source ở trạng thái không ghi trong giai đoạn rollback được phê duyệt.

### 13.2. Write fence

Write fence ngăn hệ thống cũ tiếp tục ghi sau mốc chuyển. Có thể thực hiện bằng maintenance mode, revoke write permission, application feature flag, routing policy hoặc cơ chế khác phù hợp. Một feature flag trong một service không đủ nếu còn batch job, admin script hay integration khác ghi trực tiếp.

### 13.3. Canary và gradual cutover

Với hệ thống hỗ trợ, có thể chuyển một tỷ lệ nhỏ traffic hoặc một nhóm tenant trước. Cần xác định rõ một tenant/request chỉ có một writer authoritative tại một thời điểm. Nếu một phần request ghi source còn phần khác ghi target mà không có replication/ownership rule, dữ liệu sẽ phân nhánh.

## 14. Rollback và roll-forward

Rollback migration không luôn là đổi connection string về source. Sau cutover, target có thể đã nhận dữ liệu mới mà source không có.

### 14.1. Trạng thái trước và sau cutover

| Giai đoạn | Source | Target | Khả năng quay lại |
|---|---|---|---|
| Trước baseline | Authoritative | Trống | Không cần rollback |
| Baseline copy | Authoritative | Bản copy ban đầu | Dừng job và giữ source |
| CDC catch-up | Authoritative + change capture | Replica cập nhật | Có thể dừng và sửa pipeline nếu source chưa thay đổi vai trò |
| Final sync trước cutover | Tạm fence writer | Đã bắt kịp | Có thể mở lại source nếu final validation fail |
| Sau cutover, target-only writes | Read-only/standby | Authoritative | Quay lại source cần reverse migration/CDC hoặc replay write |

### 14.2. Khi nào roll-forward an toàn hơn?

Nếu target đã nhận write mới và source không nhận các thay đổi đó, quay lại source có thể làm mất giao dịch. Khi lỗi chỉ là bug ứng dụng hoặc cấu hình target có thể sửa nhanh, roll-forward có thể an toàn hơn. Nếu buộc rollback, phải:

- Dừng/fence target writer.
- Xác định toàn bộ write phát sinh từ cutover.
- Reverse replicate hoặc export/replay về source theo mapping đã kiểm chứng.
- Đối soát và xác nhận invariant trước khi mở source.
- Xử lý ID/sequence/transaction mới và side effect external.

Không cam kết rollback hai chiều nếu chưa thiết kế reverse CDC/schema compatibility. Dữ liệu của hai phiên bản schema có thể không ánh xạ ngược đầy đủ.

## 15. Hiệu năng và giới hạn khi migration

Bulk copy, checksum và CDC có thể gây tải lớn cho cả source lẫn target.

### Các tham số cần kiểm soát

- Batch size và số worker song song.
- Read/write throughput, IOPS, network bandwidth.
- Connection pool và transaction size.
- Lock duration, replication log retention và CDC lag.
- Index build, constraint validation và vacuum/maintenance theo engine.
- Thời gian snapshot/export/import/restore.
- Thời gian reconciliation và mức độ ảnh hưởng đến workload online.

### Quy tắc thực hành

1. Chạy benchmark bằng mẫu dữ liệu đại diện, không chỉ empty database.
2. Tăng concurrency từ từ và theo dõi source latency.
3. Giới hạn migration throughput để bảo vệ production.
4. Tách transform CPU-heavy khỏi database I/O khi phù hợp.
5. Tránh một transaction khổng lồ cho toàn bộ dataset nếu engine không phù hợp.
6. Có pause/resume và backpressure.
7. Ước lượng thời gian bắt kịp CDC từ change rate và apply throughput.

Nếu source phát sinh 5.000 changes/giây và target chỉ apply được 3.000 changes/giây, lag sẽ tiếp tục tăng ngay cả khi bulk copy đã hoàn thành. Cần nâng throughput, giảm nguồn thay đổi có kiểm soát hoặc chọn cửa sổ cutover khác.

## 16. Bảo mật và quản trị trong migration

Dữ liệu trong quá trình chuyển vẫn phải tuân thủ phân loại và policy như khi đang phục vụ:

- Dùng identity riêng cho migration job, chỉ đọc source và chỉ ghi target đúng phạm vi.
- Truyền dữ liệu qua kênh mã hóa; mã hóa file trung gian và xóa file tạm theo quy trình.
- Không ghi row chứa PII, payment credential hoặc secret vào log lỗi.
- Nếu cần dữ liệu test, dùng synthetic/masked data theo policy.
- Đặt source/target trong region và network được phép; kiểm soát cross-region transfer.
- Quản lý secret/credential của job và rotate sau migration.
- Audit ai khởi chạy, thay đổi mapping, đọc dữ liệu, chạy lại batch và phê duyệt cutover.
- Bảo vệ manifest/checksum để người không có quyền không thể sửa bằng chứng đối soát.

Nếu migration sử dụng vendor hoặc managed service bên ngoài, xác định data processing boundary, quyền truy cập operator, retention của staging copy và quy trình xóa bản trung gian.

## 17. Quan sát, manifest và bằng chứng nghiệm thu

Mỗi migration nên có một manifest tổng hợp phạm vi, checkpoint, kết quả và người phê duyệt.

### 17.1. Metrics

| Metric | Ý nghĩa | Cảnh báo |
|---|---|---|
| Rows read / written | Tiến độ copy | Written thấp hơn dự kiến |
| Batch verified / failed | Mức hoàn tất được kiểm chứng | Batch failed hoặc pending kéo dài |
| CDC lag | Khoảng cách giữa source và target | Lag tăng liên tục hoặc vượt ngưỡng cutover |
| Apply errors | Thay đổi không ghi được | Lỗi schema, constraint hoặc permission |
| Mismatch count | Sai lệch đối soát | Mismatch ở field/invariant trọng yếu |
| Throughput | Khả năng copy/apply | Không bắt kịp change rate |
| Source latency | Tác động đến production | Tăng vượt SLO |
| Restore/rollback duration | Khả năng phục hồi | Không đạt RTO |
| Quarantine count | Record bị từ chối transform | Tăng bất thường hoặc chưa có owner |

### 17.2. Ví dụ manifest

~~~yaml
migration:
  id: booking-db-2026-11
  source: booking-primary
  target: booking-managed
  snapshot_ref: snapshot-2026-11-18T03-00Z
  cdc_watermark: source-log-position-0042
  datasets:
    - name: reservations
      source_count: 1250000
      target_count: 1250000
      missing_keys: 0
      extra_keys: 0
      value_mismatches: 0
      invariant_failures: 0
      status: VERIFIED
  cutover_approved: false
~~~

Đây là manifest minh họa, không phải schema chuẩn của công cụ nào. Trong thực tế cần có checksum reference, thời gian chạy, version transform, CDC lag, danh sách ngoại lệ, người xác minh và chữ ký/phê duyệt phù hợp.

### 17.3. Tiêu chí nghiệm thu

- Toàn bộ dataset thuộc phạm vi có status rõ.
- Missing/extra keys bằng 0 hoặc mọi ngoại lệ được phân loại và phê duyệt.
- Critical aggregates và business invariants khớp.
- Referential integrity được validate.
- CDC lag bằng 0 hoặc dưới ngưỡng được chấp nhận tại final watermark.
- Không còn writer không được quản lý ở source.
- Ứng dụng, batch, report và integration dùng target đúng.
- Backup, restore, monitoring, alert và runbook đã sẵn sàng.
- Owner nghiệp vụ và kỹ thuật phê duyệt cutover.

## 18. Case study: chuyển database đặt phòng lên managed cloud database

**Bối cảnh:** nền tảng cho thuê chỗ ở đang chạy database quan hệ trên VM. Hệ thống có bảng customers, properties, reservations, payments và reservation_events. API cần downtime dưới 10 phút. Database phát sinh thay đổi liên tục, đặc biệt trong giờ cao điểm. Target managed database khác phiên bản engine; một số kiểu dữ liệu và collation cần điều chỉnh.

### 18.1. Phạm vi và rủi ro

| Dataset | Rủi ro | Kiểm chứng chính |
|---|---|---|
| customers | Unicode, email normalization, PII | Count, key, canonical string comparison, access policy |
| properties | Reference, location, status | Orphan check, enum mapping, aggregate theo tenant |
| reservations | Concurrent update và booking overlap | Count/status, business key, inventory invariant |
| payments | Decimal precision và audit | Sum theo currency/status, provider reference, duplicate |
| reservation_events | Dung lượng lớn và ordering | Time range, event ID, partition, ordering/sequence |

### 18.2. Kế hoạch

1. Inventory tất cả writer/reader, stored procedure, report và integration.
2. Benchmark target, xác minh kiểu dữ liệu, collation, index, constraint và connection limits.
3. Tạo snapshot nhất quán và baseline export/import theo key range.
4. Chạy transform có version; record không hợp lệ được quarantine kèm lý do và owner.
5. Bật CDC từ watermark tương ứng, theo dõi lag và apply error.
6. Đối soát count, payment totals theo currency, reservation states, key-level diff và orphan records.
7. Chạy shadow read cho các truy vấn chỉ đọc, so sánh kết quả mà chưa đổi response người dùng.
8. Thử nghiệm cutover/rollback ở staging bằng dữ liệu và tải đại diện.
9. Trong cửa sổ chuyển đổi, fence toàn bộ source writer, chờ CDC bắt kịp, chạy final checks và chuyển endpoint.
10. Chạy smoke tests: tìm property, tạo reservation thử, kiểm tra payment status qua sandbox và đọc lịch sử.
11. Theo dõi SLO, lock, connection, query plan, replication và mismatch trong giai đoạn ổn định.

### 18.3. Quyết định khi có mismatch

- Nếu count thiếu ở một key range: dừng cutover, xác định batch/checkpoint rồi replay và đối soát lại.
- Nếu payment total lệch: phân loại theo currency, status, rounding và duplicate provider reference; không chỉ cộng tổng mọi amount.
- Nếu orphan property: xác định mapping ID hoặc record lịch sử được phép tồn tại; không tự tạo parent giả.
- Nếu CDC lag cao: giữ source authoritative, điều chỉnh throughput và chờ catch-up trong cửa sổ được duyệt.
- Nếu source đã bị fence nhưng final validation fail: chưa mở target traffic; có thể mở lại source theo runbook nếu target chưa nhận write.
- Nếu target đã nhận write mới rồi phát hiện bug nghiêm trọng: dừng writer, đánh giá roll-forward hoặc reverse migration; không đổi endpoint ngược mà bỏ qua dữ liệu mới.

### 18.4. Điều kiện hoàn tất

Chỉ chuyển sang vận hành target khi dữ liệu trọng yếu đã được đối soát, business invariants thỏa, application smoke test thành công, mọi writer cũ được kiểm soát, backup/restore được xác minh và các owner ký nhận. Source cũ chỉ được decommission sau khi hết giai đoạn rollback/retention đã phê duyệt.

## 19. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Cách cải thiện |
|---|---|---|
| Chỉ so sánh tổng row count | Thiếu một record và thừa record khác vẫn có thể cân bằng | So key-level, aggregate và invariant |
| Copy trong khi source thay đổi nhưng không có watermark | Snapshot và delta có gap/overlap | Phối hợp snapshot với CDC checkpoint |
| Coi checksum file giống nhau là dữ liệu đích đúng | Import/schema/constraint có thể vẫn sai | Kiểm tra sau import và qua query nghiệp vụ |
| Chạy job một lần, không checkpoint | Khó resume, tốn thời gian và dễ duplicate | Batch idempotent, checkpoint và manifest |
| Disable constraint rồi quên validate | Đích có orphan/duplicate | Re-enable và validate trước cutover |
| Cutover khi CDC còn lag | Mất các thay đổi cuối | Fence writer và kiểm tra final watermark |
| Quên batch job hoặc integration là writer | Source và target phân nhánh | Writer inventory và write fence toàn hệ thống |
| Cho phép hai database cùng ghi sau cutover | Conflict và mất khả năng xác định source of truth | Một writer authority, hoặc conflict resolution được thiết kế |
| Rollback bằng cách đổi connection string | Mất dữ liệu mới trên target | Reverse CDC/replay hoặc roll-forward |
| Bật transform không có version | Không thể tái lập hoặc giải thích dữ liệu | Version mapping/code và ghi manifest |
| Bỏ qua record lỗi để migration tiếp tục | Dữ liệu mất âm thầm | Quarantine, metric, owner và acceptance criteria |
| Dùng production data trong test không bảo vệ | Rò PII/secret | Masking, synthetic data và kiểm soát truy cập |

## 20. Checklist review migration

### Khảo sát và thiết kế

- [ ] Có inventory dataset, schema, volume, change rate, owner và dependency.
- [ ] Xác định toàn bộ reader/writer, job, report, integration và admin path.
- [ ] Có access pattern, downtime tolerance, RPO/RTO và data classification.
- [ ] Mapping schema/type/collation/timezone/precision được review.
- [ ] Chọn offline/online/CDC/batch theo yêu cầu và có lý do.
- [ ] Snapshot/watermark và checkpoint semantics rõ.

### Thực thi và đối soát

- [ ] Job có batch boundary, checkpoint, retry và idempotency.
- [ ] Transform code/version được ghi nhận và có quarantine.
- [ ] Count/aggregate/key-level/field-level/relationship/business invariant được kiểm tra.
- [ ] Checksum được canonicalize và hiểu đúng giới hạn.
- [ ] CDC ordering, delete, duplicate, schema evolution và lag được quản lý.
- [ ] Constraint/index/sequence/permission được xác minh ở target.

### Cutover và phục hồi

- [ ] Có write fence bao phủ mọi writer cũ.
- [ ] Final sync và final reconciliation chạy trên watermark xác định.
- [ ] Có cutover checklist, owner và phê duyệt.
- [ ] Có rollback/roll-forward decision tree và đã diễn tập.
- [ ] Xác định cách xử lý target writes phát sinh sau cutover.
- [ ] Backup/restore và RPO/RTO được kiểm thử.

### Bảo mật và vận hành

- [ ] Migration identity theo least privilege, TLS và encryption.
- [ ] File tạm/log/manifest không lộ secret hoặc PII.
- [ ] Có dashboard throughput, lag, mismatch, quarantine, source impact và cost.
- [ ] Có runbook xử lý batch fail, CDC lag, mismatch và incident cutover.
- [ ] Nghiệm thu được owner nghiệp vụ và kỹ thuật xác nhận.

## 21. Bài tập thực hành

**Bối cảnh:** một nền tảng đặt phòng chuyển database từ hệ thống tự quản lý sang managed database. Database có 40 triệu reservation events, dữ liệu booking đang được ghi liên tục, target sử dụng collation khác và downtime tối đa 5 phút. Một báo cáo tài chính đọc dữ liệu từ source; một worker ghi payment status từ webhook.

Hãy xây dựng kế hoạch:

1. Inventory reader/writer/dependency và xác định ai có quyền phê duyệt migration.
2. Chọn baseline snapshot, batch key và CDC watermark.
3. Xác định mapping cho collation, timestamp, decimal, enum và key.
4. Thiết kế checkpoint, retry và quarantine record lỗi.
5. Viết bộ đối soát gồm count theo partition, tổng payment theo currency/status, key diff, orphan và invariant booking.
6. Xác định cách chuyển báo cáo và webhook worker để không còn writer ở source sau cutover.
7. Thiết kế write fence và final sync để downtime dưới ngưỡng.
8. Lập decision tree cho mismatch trước cutover, lỗi sau target write và rollback.
9. Xác định dashboard, alert và manifest bằng chứng.
10. Viết tiêu chí nghiệm thu để owner nghiệp vụ có thể ký nhận.

**Gợi ý tự kiểm tra:** Đừng coi CDC lag gần zero là đủ nếu payment total hoặc invariant reservation còn lệch. Đừng quên webhook worker là writer. Đừng mở target cho traffic ghi trước khi biết cách xử lý nếu phải quay lại source. Mỗi bước cần xác định source of truth, checkpoint và bằng chứng.

## 22. Ghi nhớ

Migration thành công không chỉ là copy đủ byte hay có cùng số record. Nó cần chuyển đúng dữ liệu, quan hệ, ý nghĩa nghiệp vụ và quyền sở hữu thay đổi; đồng thời có bằng chứng đối soát và phương án phục hồi.

Một kế hoạch tốt bắt đầu bằng inventory và invariant, chọn snapshot/bulk/CDC phù hợp, dùng batch có checkpoint và retry an toàn, đối chiếu count/aggregate/key/field/referential/business rules, rồi cutover với write fence và rollback plan. Sau chuyển đổi, tiếp tục reconciliation, theo dõi lag và lỗi, chỉ decommission nguồn cũ sau khi dữ liệu, ứng dụng và vận hành đã được nghiệm thu.
