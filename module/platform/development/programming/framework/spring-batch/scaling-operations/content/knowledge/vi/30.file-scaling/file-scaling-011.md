# Đối soát file đầu vào đầu ra trong Spring Batch

## Mục tiêu bài học

Một Spring Batch job đọc tệp 40 triệu bản ghi, chia thành 16 partitions, chạy trên nhiều thread hoặc worker JVM rồi tạo các tệp kết quả. JobRepository báo `COMPLETED`, tổng `readCount` và `writeCount` đều hợp lý. Nhưng liệu **mọi bản ghi hợp lệ ở đầu vào đã xuất hiện đúng ở đầu ra**, không thiếu, không trùng, không sai giá trị và không bị ghi nhầm phân vùng? Liệu downstream đang đọc **đúng phiên bản output đã được kiểm chứng**?

**Đối soát file đầu vào đầu ra** (input–output reconciliation) là quá trình chứng minh dữ liệu đã đi qua pipeline đúng theo hợp đồng biến đổi, từ tệp đầu vào bất biến, qua reader–processor–writer và partition/merge, đến tập tệp được công bố cho downstream. Đối soát **không chỉ** là so số dòng hoặc kiểm tra StepExecution có status `COMPLETED`.

Bài thuộc chương **File scaling**, module **SPRING_BATCH_SCALING_OPERATIONS**. Module tập trung mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và mô hình phân tán; đồng thời học đo bottleneck, bảo đảm thread safety, retry/restart và vận hành theo tài nguyên. Với file scaling, phải tăng throughput mà vẫn **chứng minh được đầu ra đúng, đầy đủ, có thể phục hồi**.

Sau bài, bạn sẽ biết:

- Phân biệt đối soát **bytes/tệp**, **bản ghi logic** và **ngữ nghĩa nghiệp vụ**.
- Chốt source snapshot/version, schema, encoding, business key và transformation contract.
- Tính checksum SHA-256 streaming và canonical record digest.
- Xây manifest cho từng partition, tổng hợp toàn job và phát hiện thiếu/trùng.
- Phân loại accepted, filtered, rejected, deduplicated và các mô hình one-to-many/many-to-one.
- Dùng multiset, SQL `EXCEPT ALL` hoặc external sort để đối chiếu dữ liệu lớn.
- Hiểu giới hạn của Spring Batch counters và file writer khi rollback/restart.
- Ghi output vào staging, đối soát rồi publish theo commit protocol rõ.
- Kiểm thử crash, partial files, remote workers, merge, input mutation và object storage.
- Giám sát SLA chất lượng dữ liệu, lỗi thiếu/trùng và throughput hữu ích.

## 1. Vì sao `COMPLETED` chưa phải là chứng nhận đối soát?

Một job có thể hoàn thành mọi StepExecutions nhưng output sai vì:

- Input bị thay đổi sau khi một partition đã đọc.
- Partitioner tạo range overlap/gap hoặc cắt nhầm record boundary.
- Reader đếm nhầm header/trailer, CSV quoted multiline hoặc UTF-8 BOM.
- Processor filter hợp lệ, nhưng nhóm vận hành tưởng record bị mất.
- Writer rollback chunk nhưng một phần bytes vẫn đã ra file.
- Worker retry/restart append một dòng lần thứ hai.
- Hai JVM cùng ghi chung output file làm xen kẽ bytes.
- Merge bỏ sót một partition file hoặc lấy hai attempts của cùng partition.
- File copy/upload bị truncate hoặc downstream đọc tệp trước khi close.
- Hai records sai lệch bù trừ khiến số lượng/tổng tiền vẫn khớp.

Ví dụ:

~~~text
Input expected IDs : [A, B, C, D]
Output actual IDs  : [A, B, B, D]

Expected count = 4
Actual count   = 4
Missing        = C
Duplicate      = B
~~~

`readCount=4` và `writeCount=4` không phát hiện lỗi. Cần kiểm tra **identity và nội dung của mỗi occurrence**, không chỉ kích thước tập dữ liệu.

## 2. Ba tầng đối soát

| Tầng | Câu hỏi | Phép kiểm chính |
| --- | --- | --- |
| **File/byte** | Tệp có đủ bytes và đúng phiên bản, không hỏng/copy nhầm? | Size, SHA-256, file inventory, object version, compression integrity |
| **Record/logical** | Các bản ghi mong đợi có đủ, không trùng/khác giá trị? | Count, business-key multiset, canonical hash, missing/extra/mismatch |
| **Business semantics** | Quy tắc xử lý có đúng? | Tổng tiền theo currency, version, trạng thái, nhóm reject/filter, aggregate totals |

Các tầng **bổ sung chứ không thay thế** nhau:

- Raw hash khác nhau là bình thường nếu output được sắp xếp lại hoặc đổi encoding.
- Raw SHA-256 giống chứng minh bytes gần như chắc chắn giống với bản đã hash, không chứng minh input đúng nghiệp vụ.
- Tổng số bản ghi hoặc tổng tiền đúng vẫn có thể có missing bù bằng duplicates.
- Record diff đúng nhưng file nén/trailer/copy dở dang vẫn có thể làm downstream đọc lỗi.
- Tệp đúng bytes nhưng URI trỏ vào version khác vẫn là lỗi publication.

Không có một con số `checksum` dùng cho mọi loại biến đổi dữ liệu.

## 3. Định nghĩa dữ liệu đúng trước khi chạy

Một **data contract** nên xác định:

| Thành phần | Ví dụ | Mục đích |
| --- | --- | --- |
| `logicalRunId` | `orders-2026-11-25-v1` | Định danh tập xử lý |
| `sourceVersion` | Version ID/generation của object | Không trộn nhiều ảnh chụp nguồn |
| `schemaVersion` | `orders.csv.v3` | Cố định parser và fields |
| `encoding` | UTF-8 | Cách hiểu bytes |
| `csvDialect` | comma, quoted multiline, double-quote escape | Ranh giới record logic |
| `businessKey` | `order_id + source_version` | So missing/duplicate |
| `transformVersion` | `normalize-orders-v5` | Tái lập expected output |
| `filterPolicy` | Loại cancelled records | Diễn giải count |
| `rejectionPolicy` | Invalid rows vào reject inventory | Không mất dữ liệu âm thầm |
| `ordering` | Theo key hay không yêu cầu global order? | Quy định sort/merge |
| `outputSchema` | `normalized-orders.v2` | Cách parse và đối soát |
| `publication` | Sau khi validation toàn job PASS | Không lộ partial output |

Nếu một đầu vào sinh nhiều output, hoặc nhiều đầu vào gộp thành một output, phải công bố phép ánh xạ trước. Không áp `N_in = N_out` một cách máy móc cho mọi pipeline.

### Cần phân loại duplicate rõ ràng

Hai records cùng `order_id` có thể là hai versions hợp lệ, hai giao dịch khác nhau hoặc một event bị redeliver. Key dedup quyết định kết quả đối soát; không chọn chỉ dựa vào một cột “trông duy nhất”.

## 4. Chốt input snapshot bất biến

Một rủi ro khi đọc song song:

~~~text
09:00 partition-A đọc input version V1
09:05 upstream ghi đè file cùng path thành V2
09:08 partition-B đọc input version V2
09:15 merge tạo output pha trộn V1 + V2
~~~

Muốn tái lập kết quả, mọi worker phải đọc **cùng source snapshot**. Cách làm:

- Dùng immutable source path đã hoàn tất việc upload/close.
- Object storage: lưu version ID/generation khi có versioning và đọc theo identity đó.
- Directory nhiều file: chốt **danh sách từng file + version/size/checksum** trước partition.
- Local/shared filesystem: producer ghi vào temporary path, hoàn tất rồi bàn giao final path bất biến.
- Reader/partitioner dùng đúng input manifest, không tự lấy `latest` ở mỗi lần restart.
- Verify SHA-256 hoặc checksum nguồn từ nguồn tin cậy trước khi chạy.

**Path, last-modified time và ETag không mặc nhiên là checksum nội dung.** Một số object store ETag khác MD5/SHA-256, đặc biệt multipart/encryption; cần đọc semantics của provider.

## 5. Manifest là gì?

**Manifest** là bản khai dữ liệu chứa identity, định dạng, danh sách file, phiên bản và kết quả validation. Nó nên có schema version, run identity và dấu mốc lifecycle.

Input manifest minh họa:

~~~json
{
  "manifestSchemaVersion": 1,
  "logicalRunId": "orders-2026-11-25-v1",
  "source": {
    "uri": "input/orders-2026-11-25.csv.gz",
    "generation": "source-generation-12345",
    "sizeBytes": 8234501234,
    "rawSha256": "<must-be-a-real-64-char-hex-digest>",
    "format": "CSV",
    "compression": "GZIP",
    "encoding": "UTF-8",
    "schemaVersion": "orders.v3"
  },
  "transformVersion": "normalize-orders-v5",
  "outputContract": "accepted-one-to-one-plus-reject-inventory"
}
~~~

Giá trị `rawSha256` trong ví dụ là **placeholder**, không phải digest thật. Production cần tính SHA-256 sau khi nguồn hoàn tất và bảo đảm bên đọc kiểm chứng được.

Manifest không có giá trị đối soát nếu toàn bộ counts/hash được copy từ “writer tự khai” mà không kiểm tra bytes và records **thực sự đang có trên storage**.

## 6. CSV: dòng vật lý khác record logic

CSV có thể chứa quoted multiline:

~~~csv
order_id,description,amount
1001,"Lô hàng
có ghi chú hai dòng",150000
1002,"Lô hàng tiếp theo",200000
~~~

Có bốn dòng vật lý nhưng hai **data records logic** cùng một header. Nếu worker cắt file tại mỗi newline, nó có thể tạo records sai.

Cần định nghĩa:

- Header, trailer, blank lines, comments được xử lý ra sao.
- UTF-8 BOM, line endings LF/CRLF, UTF-8 code point ở cuối block.
- Delimiter/quote/escape và quoted embedded newline.
- NULL khác empty string thế nào.
- Timestamp timezone và decimal scale/rounding.
- Record length limit và trường không hợp lệ.
- Compression format, concatenated gzip members, charset validation.
- File có footer chứa record count/control totals không.

**Đừng parse CSV bằng `String.split(",")`.** Dùng thư viện hiểu dialect, nhất là khi split input theo byte ranges; partition boundaries phải nằm trên **records logic an toàn** hoặc có bước tiền xử lý tạo index offsets.

## 7. Các phép kiểm và giới hạn

| Kiểm tra | Giá trị | Không chứng minh |
| --- | --- | --- |
| File size | Byte count | Contents không đổi |
| SHA-256 raw | Byte identity gần như chắc chắn | Quy tắc business đúng |
| CRC32/CRC32C | Phát hiện hỏng ngẫu nhiên | Chống giả mạo có chủ đích |
| Record count | Số records theo parser | Missing bù duplicate |
| Sum amount | Business control total | Đúng từng amount/key |
| Min/max key | Giá trị biên | Không có gap |
| Count distinct | Số keys duy nhất | Giá trị từng record đúng |
| Canonical sorted digest | Tập records logic sau chuẩn hóa | Raw file bytes giống |
| Multiset/key diff | Missing/extra/mismatch | Transform logic vốn đúng |
| Aggregate invariants | Tổng theo nhóm/date/currency | Record completeness đầy đủ |

**Không dùng XOR của record hashes làm bằng chứng đầy đủ**: hai occurrences giống nhau có thể triệt tiêu nhau. Cộng checksums hay tổng tiền cũng có va chạm/sai lệch bù trừ. Nếu cần proof nội dung, hãy so **multiset chuẩn hóa** hoặc per-business-key versions.

## 8. Java: tính SHA-256 streaming cho file lớn

Ví dụ Java 17 không đưa toàn file vào heap:

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class FileHashing {

    private FileHashing() {}

    public static String sha256(Path path) throws IOException {
        MessageDigest digest;
        try {
            digest = MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                    "SHA-256 unavailable", ex);
        }

        try (InputStream in = Files.newInputStream(path)) {
            byte[] block = new byte[1024 * 1024];
            int size;

            while ((size = in.read(block)) != -1) {
                if (size > 0) {
                    digest.update(block, 0, size);
                }
            }
        }

        return HexFormat.of().formatHex(digest.digest());
    }
}
~~~

Hash **bytes vật lý**. SHA-256 của `.gz` đại diện bytes nén, không phải logical CSV content sau giải nén. Đừng tính hash file đang được writer append, hoặc dùng một `Path` có thể bị overwrite trong lúc đọc.

Nếu đo cả `Files.size(path)` lẫn SHA-256 bằng **hai lần đọc** và nguồn thay đổi giữa hai lần, manifest có thể không nhất quán; cố định snapshot hoặc tính byte count và digest trong một lượt. Hash không xác minh business transformation vốn được code sai.

## 9. Canonicalization: so logic thay vì layout

Cùng bản ghi có thể có các byte representations khác nhau:

~~~text
File A: 1001,100.00 + LF
File B: 1001,100.0  + CRLF
~~~

Nếu business coi cả hai là cùng số tiền, raw hash khác nhưng canonical record giống. Canonicalization cần:

1. Parse đúng schema/dialect.
2. Ánh xạ NULL/empty/whitespace theo chính sách.
3. Chuẩn hóa decimal: integer minor units hoặc scale cố định.
4. Chuẩn hóa timestamp precision/timezone.
5. Unicode normalization nếu contract có yêu cầu.
6. Chốt field order, field types và schema version.
7. Dùng **length-prefixed encoding** hoặc serializer chuẩn hóa không mơ hồ.
8. Nếu output không có thứ tự bắt buộc, sort canonical records hoặc so theo key/multiset.

Không chỉ nối chuỗi bằng dấu `|`: hai field lists `["A|B", "C"]` và `["A", "B|C"]` sẽ cho cùng kết quả nối `A|B|C`.

## 10. Java: hash canonical record có field framing

Đoạn Java 17 sau nhận **các field đã chuẩn hóa**, encode UTF-8 với length-prefix trước khi SHA-256:

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class CanonicalRecordHash {

    private CanonicalRecordHash() {}

    public static String sha256(
            String businessKey,
            String sourceVersion,
            String amountMinorUnits,
            String status) {

        MessageDigest digest;
        try {
            digest = MessageDigest.getInstance("SHA-256");
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(ex);
        }

        field(digest, businessKey);
        field(digest, sourceVersion);
        field(digest, amountMinorUnits);
        field(digest, status);

        return HexFormat.of().formatHex(digest.digest());
    }

    private static void field(
            MessageDigest digest, String value) {

        if (value == null) {
            digest.update(ByteBuffer.allocate(4)
                    .putInt(-1).array());
            return;
        }

        byte[] bytes = value.getBytes(
                StandardCharsets.UTF_8);
        digest.update(ByteBuffer.allocate(4)
                .putInt(bytes.length).array());
        digest.update(bytes);
    }
}
~~~

Hàm không tự parse CSV, decimal, timezone hay Unicode. Canonicalizer version và thứ tự fields phải ổn định; đừng dùng hash như business ID xuyên nâng cấp nếu quy tắc canonicalization có thể đổi mà chưa có migration plan.

Muốn hash **toàn bộ multiset** theo thứ tự độc lập, sort canonical representations rồi hash với framing từng record, hoặc so bằng external-sort merge diff. Việc hash từng row **không tự biến tập records thành chứng nhận không trùng**.

## 11. Count accounting cho pipeline một-một

Giả sử mỗi data record đầu vào được phân loại **chính xác một nhóm**:

- `ACCEPTED`: hợp lệ, tạo một output record.
- `FILTERED`: bị loại theo business rule.
- `REJECTED`: parse/validation lỗi, có reject inventory.

Khi không có dedup/fanout:

\[
N_\text{input} =
N_\text{accepted} + N_\text{filtered} + N_\text{rejected}
\]

Và:

\[
N_\text{outputExpected}=N_\text{accepted}
\]

Điều kiện thực:

\[
N_\text{outputActual}=N_\text{outputExpected}
\]

**Cộng count chỉ là điều kiện cần**. Còn cần:

\[
\operatorname{Multiset}(\text{expected normalized accepted})
=\operatorname{Multiset}(\text{actual output})
\]

Ví dụ:

~~~text
Input logical records:      1,000,000
Accepted:                    970,000
Filtered by contract:         20,000
Rejected:                     10,000
Expected output records:     970,000
Actual output records:       970,000
Reject inventory:             10,000
~~~

Những con số khớp không loại trừ trường hợp record C thiếu và B trùng. Cần key/value diff.

## 12. Accounting khi loại duplicate

Nếu hợp đồng cho phép loại duplicate events:

\[
N_\text{input}
= N_\text{uniqueAccepted}
+N_\text{duplicatesSuppressed}
+N_\text{filtered}
+N_\text{rejected}
\]

Và trong mô hình một output trên mỗi event duy nhất:

\[
N_\text{outputExpected}=N_\text{uniqueAccepted}
\]

Ví dụ:

~~~text
Input                   1,000,000
Unique accepted           960,000
Duplicate suppressed       10,000
Filtered                   20,000
Rejected                   10,000
Output expected           960,000
~~~

**Các nhóm phải vừa không giao nhau, vừa phủ toàn bộ input.** Nếu một duplicate cũng malformed, hợp đồng cần quy định ưu tiên classification; không đếm một occurrence vào hai nhóm.

Business key có thể là `event_id` hoặc `(source_system, entity_id, source_version)`. Nếu hai occurrences giống nội dung vẫn là hai giao dịch hợp lệ, phải giữ cả hai bằng occurrence index/ID riêng.

## 13. One-to-many, many-to-one và tổng hợp

| Transform | Count kỳ vọng | Kiểm tra chi tiết |
| --- | --- | --- |
| One-to-one | Bằng accepted | Key/version/value |
| Filter | Bằng số accepted sau filter | Filter reason |
| Dedup | Bằng số unique accepted | Duplicate inventory |
| One-to-many | Tổng expected child counts | Children theo parent key |
| Many-to-one | Số output groups/buckets | Membership + totals |
| Group-by ngày/tiền tệ | Số business buckets | Sum/count per bucket |
| Split file không đổi record | Tổng partition output bằng nguồn | Coverage/gap/overlap |
| Merge nhiều files | Global multiset theo hợp đồng | Không thiếu/trùng partition file |

Một đầu vào có thể sinh ba output lines; lúc đó `N_in != N_out` là đúng. Việc đối soát phải thực hiện trên phép ánh xạ theo source key thay vì dùng equality count.

Với aggregation, cùng grand total có thể che giấu sai lệch bù trừ: `+100` và `-100`. Đối soát theo currency, date, group key và nghiệp vụ, không chỉ một tổng tiền.

## 14. Control totals bổ sung cho key-level diff

Các control totals thường có ích:

- Count theo recordType/status/filterReason.
- `sum(amountMinorUnits)` theo currency và business date.
- `countDistinct(event_id)` theo source partition.
- `min/max(event_time)` và source versions.
- Sum quantity theo product/shard.
- Debits vs credits theo accounting invariants.
- Rejected bytes/rows theo reason và partition.

**Không dùng `double` cho tiền** rồi so chính xác; dùng integer minor units, `BigDecimal` đã chốt scale/rounding, hoặc SQL DECIMAL/NUMERIC.

Ví dụ:

~~~text
USD / 2026-11-25:
  accepted source count = 100000
  output count          = 100000
  source amount cents   = 89220001567
  output amount cents   = 89220001567
  key/version diff      = 0
~~~

Count + sum + key diff là nhiều lớp bảo vệ, nhưng vẫn phải kiểm tra **toàn bộ fields cần đúng** và version/schema.

## 15. Vì sao cần multiset chứ không chỉ set?

~~~text
Expected = [A, B, B, C]
Actual   = [A, B, C, C]

Set(Expected) = {A, B, C}
Set(Actual)   = {A, B, C}
→ So set bỏ sót B thiếu và C thừa.

Multiset(Expected) ≠ Multiset(Actual)
→ Phát hiện đúng multiplicity của từng record.
~~~

Một record mismatch có thể được thể hiện dưới dạng **một missing + một extra** khi so toàn bộ canonical row. Nếu muốn báo mismatch theo business key, so key/version sau đó so từng field.

Trước khi JOIN, phải biết khóa có unique không. JOIN hai bảng có nhiều occurrences cùng key có thể tạo **row multiplication** và báo sai.

## 16. PostgreSQL: multiset diff bằng EXCEPT ALL

Đưa expected canonical records và actual output records vào hai staging tables dành riêng một logical run:

~~~sql
CREATE TABLE reconcile_expected (
    run_id TEXT NOT NULL,
    business_key TEXT NOT NULL,
    source_version BIGINT NOT NULL,
    amount_minor_units BIGINT NOT NULL,
    normalized_status TEXT NOT NULL
);

CREATE TABLE reconcile_actual (
    run_id TEXT NOT NULL,
    business_key TEXT NOT NULL,
    source_version BIGINT NOT NULL,
    amount_minor_units BIGINT NOT NULL,
    normalized_status TEXT NOT NULL
);
~~~

Missing occurrences:

~~~sql
WITH missing_rows AS (
    SELECT business_key, source_version,
           amount_minor_units, normalized_status
    FROM reconcile_expected WHERE run_id = :runId

    EXCEPT ALL

    SELECT business_key, source_version,
           amount_minor_units, normalized_status
    FROM reconcile_actual WHERE run_id = :runId
)
SELECT COUNT(*) AS missing_occurrences FROM missing_rows;
~~~

Extra occurrences:

~~~sql
WITH extra_rows AS (
    SELECT business_key, source_version,
           amount_minor_units, normalized_status
    FROM reconcile_actual WHERE run_id = :runId

    EXCEPT ALL

    SELECT business_key, source_version,
           amount_minor_units, normalized_status
    FROM reconcile_expected WHERE run_id = :runId
)
SELECT COUNT(*) AS extra_occurrences FROM extra_rows;
~~~

`EXCEPT ALL` **giữ số lần xuất hiện**; `EXCEPT` thường loại duplicates. Hai sides phải dùng cùng canonical schema/transform version và được đọc từ snapshots nhất quán.

**Chi phí:** với hàng trăm triệu records, staging/EXCEPT ALL có thể gây I/O, temp spill, index/locking load. Cần benchmark query plan, DB resource budget; external-sort diff có thể phù hợp hơn khi DB đang là bottleneck.

## 17. Streaming merge diff sau external sort

Khi dữ liệu vượt RAM, không đưa toàn bộ keys vào `HashMap` của worker. Một pipeline so sánh:

1. Parse hai file sets thành canonical records theo contract.
2. External sort dữ liệu từng phía theo một **total ordering key**.
3. Stream qua hai sorted inputs, so từng record và **số lần xuất hiện**.
4. Xuất inventories: missing, extra và changed.
5. Ghi reconciliation report với counts, sample mismatches, hashes và locations.

~~~mermaid
flowchart LR
    E[["Expected canonical records"]] --> ES["External sort"]
    A[["Actual output records"]] --> AS["External sort"]
    ES --> M["Streaming merge diff"]
    AS --> M
    M --> MISS["Missing"]
    M --> EXTRA["Extra"]
    M --> DIFF["Value mismatches"]
    M --> R["Reconciliation report"]
~~~

Sau khi sort, bước merge là **O(N+M)**; external sort thông thường **O(N log N)** cùng I/O nhiều lượt. Dùng comparator có cả `businessKey`, `sourceVersion`, `eventId`, occurrence index nếu hợp đồng cần giữ duplicates.

**Đừng dùng timestamp làm key duy nhất** khi nhiều event có timestamp trùng hoặc timezone/precision khác nhau.

## 18. Đối soát ranh giới partition trước khi so output

Ví dụ manager chia ID ranges:

~~~text
partition-0000 = [1, 250001)
partition-0001 = [250001, 500001)
partition-0002 = [500001, 750001)
partition-0003 = [750001, 1000001)
~~~

Một Partitioner tốt bảo đảm ranges không gap/overlap, deterministic và dùng cùng input snapshot. Với mỗi partition cần lưu:

- `partitionName` và stable logical range/record boundary.
- `sourceId`, `sourceVersion` và `inputManifestId`.
- `fromInclusive/toExclusive` hoặc một record-range index đã kiểm chứng.
- `stagedOutputPath` do controller cấp, không do worker đoán từ thread name.
- `attemptId`/`stepExecutionId` tách khỏi tên partition logic.
- Thông tin để có thể tìm lại input khi retry/restart.

**Không suy record count từ khoảng ID**: range 250.000 giá trị không có nghĩa có đúng 250.000 records nếu ID có gaps hoặc nhiều versions. Trừ khi domain contract chứng minh 1 ID = 1 record, hãy đếm **logical records thực**.

### Partition theo byte offset

Khi chia file text thành ranges byte:

- Không cắt giữa UTF-8 multibyte character.
- Không cắt giữa CSV quoted multiline record.
- Không tính một record hai lần ở hai partitions.
- Không bỏ record đầu/cuối khi seek tới boundary.
- Không áp dụng logic split thô trên gzip stream không có index chia an toàn.
- Mọi worker phải tham chiếu **cùng byte snapshot**, không path đang được append.

Nếu không chứng minh được record boundary, nên tiền xử lý thành các shard files hợp lệ rồi xử lý chúng song song, thay vì chia arbitrary bytes.

## 19. Manifest cho từng worker partition

Worker ghi ra staging file, sau đó một bước validator đọc lại **file thực** và tạo partition manifest:

~~~json
{
  "manifestSchemaVersion": 1,
  "logicalRunId": "orders-2026-11-25-v1",
  "partitionName": "partition-0002",
  "attemptId": "attempt-03",
  "source": {
    "generation": "source-generation-12345",
    "fromInclusive": 500001,
    "toExclusive": 750001
  },
  "output": {
    "stagedUri": "staging/orders-v1/partition-0002/attempt-03/data.jsonl",
    "sizeBytes": 18402391,
    "rawSha256": "<real-sha256-required>",
    "verifiedLogicalRecords": 249000,
    "schemaVersion": "normalized-orders.v2"
  },
  "accounting": {
    "sourceLogicalRecords": 250000,
    "accepted": 249000,
    "filtered": 900,
    "rejected": 100,
    "duplicatesSuppressed": 0
  },
  "validationState": "VALIDATED"
}
~~~

Đây là **ví dụ dữ liệu**, checksum placeholder cần thay bằng digest thực. Các số count minh họa giả định nguồn **thật sự có** 250.000 records trong vùng này; không suy từ `toExclusive - fromInclusive`.

Một số quy tắc:

1. `partitionName` là danh tính logic, không thay khi restart cùng logical work.
2. `attemptId` có thể đổi khi có lần ghi output mới.
3. `rawSha256` và count chỉ được gắn `VALIDATED` sau khi writer close và validator đọc lại.
4. Source version, transform version, output schema phải khớp manifest tổng.
5. Output file không được chỉnh sửa sau validation; storage version/generation nên được pin.
6. Nếu có rejected records, reject inventory cũng cần checksum và phân quyền truy cập.

**Không để một worker tự báo VALIDATED ngay khi gọi write() thành công.** Nó có thể chưa flush/close, file vẫn dở dang hoặc bị truncate sau callback.

## 20. Tổng hợp manifest toàn job

Finalizer đối chiếu **danh sách partitions kỳ vọng** từ input manifest với các partition manifests đã VALIDATED:

~~~mermaid
flowchart TB
    I["Input manifest bất biến"] --> P["Partitioner"]
    P --> A["Worker A → staged A + manifest A"]
    P --> B["Worker B → staged B + manifest B"]
    P --> C["Worker C → staged C + manifest C"]
    A --> G["Global reconciliation gate"]
    B --> G
    C --> G
    I --> G
    G -->|PASS| PUB["Publish manifest / commit marker"]
    G -->|FAIL| QUAR["Quarantine + discrepancy report"]
~~~

Global gate cần xác minh:

- Tập expected partition names **bằng chính xác** tập outputs được chọn.
- **Đúng một validated output attempt** cho mỗi partition; không gộp hai attempts.
- Cùng logicalRunId, source version, schema và transform version.
- Input ranges phủ đúng source inventory và không overlap.
- Mọi staged file tồn tại, đúng size/hash và parse được schema output.
- Tổng counts phù hợp accounting equations.
- Không có duplicate business keys **giữa partitions** khi contract yêu cầu uniqueness.
- Không có missing/extra/mismatch canonical records.
- Business control totals đúng theo currency/date/shard.
- Rejects/skips nằm trong chính sách được phê duyệt.
- Chưa có consumer nào được cung cấp output final trước khi tất cả PASS.

### Vì sao từng partition PASS vẫn chưa đủ?

Hai partitions có thể tự đối soát “đúng” trên vùng input mà chúng được giao, nhưng **vùng input bị chồng lấn** hoặc **bỏ sót** do lỗi Partitioner. Cross-partition diff và input coverage global mới phát hiện.

## 21. Spring Batch counters có thể giúp gì?

Trong chunk-oriented step, Spring Batch có `StepExecution` counters:

- `getReadCount()`, `getWriteCount()`.
- `getFilterCount()`.
- `getReadSkipCount()`, `getProcessSkipCount()`, `getWriteSkipCount()`.
- `getCommitCount()`, `getRollbackCount()`.

Chúng hữu ích để quan sát tiến độ và giải thích kết quả, **nhưng không thay việc đọc lại file vật lý**.

| Counter | Giới hạn của cách hiểu |
| --- | --- |
| readCount | Không phải số dòng vật lý hay luôn là số logical CSV records gốc |
| writeCount | Không nhất thiết bằng số dòng xuất ra nếu writer gộp/split record |
| filterCount | Phản ánh items do processor filter; không gồm mọi business discard ngoài framework |
| skip counts | Phụ thuộc read/process/write skip policy, không mặc nhiên trùng reject inventory |
| commitCount | Đếm commits theo step lifecycle, không chứng minh bytes output đã publish |
| rollbackCount | Không phải số lần item được lặp lại trong mọi cấu hình retry |
| BatchStatus.COMPLETED | Không chứng minh checksum/canonical output đúng |

### Không cộng attempts bừa bãi

Nếu partition A chạy lần đầu đọc 500.000 items rồi fail, restart đọc lại 200.000 items trước khi hoàn tất, phép cộng `readCount` qua executions có thể vượt số unique records nguồn. Đối soát global phải dựa vào **logical output attempt đã chọn** và source snapshot, không lấy tổng attempts làm tổng dữ liệu.

## 22. Java: StepExecutionListener log counters đúng phạm vi

Ví dụ Java 17, Spring Batch 5.x; listener không giữ mutable current partition state trong singleton field:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.stereotype.Component;

@Component
public final class PartitionAccountingListener
        implements StepExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(
                    PartitionAccountingListener.class);

    @Override
    public void beforeStep(StepExecution step) {
        log.info(
            "event=partition_started stepExecutionId={} " +
            "partitionName={} sourceVersion={}",
            step.getId(),
            step.getExecutionContext()
                    .getString("partitionName", "missing"),
            step.getExecutionContext()
                    .getString("sourceVersion", "missing"));
    }

    @Override
    public ExitStatus afterStep(StepExecution step) {
        log.info(
            "event=partition_batch_counters " +
            "stepExecutionId={} partitionName={} status={} " +
            "read={} write={} filter={} readSkip={} " +
            "processSkip={} writeSkip={} commit={} rollback={}",
            step.getId(),
            step.getExecutionContext()
                    .getString("partitionName", "missing"),
            step.getStatus(),
            step.getReadCount(),
            step.getWriteCount(),
            step.getFilterCount(),
            step.getReadSkipCount(),
            step.getProcessSkipCount(),
            step.getWriteSkipCount(),
            step.getCommitCount(),
            step.getRollbackCount());

        return null; // Giữ nguyên ExitStatus do framework xác định.
    }
}
~~~

### Ranh giới của ví dụ

- Logger xuất **Batch counters**, không đánh dấu reconciled PASS.
- Listener có thể không chạy `afterStep` nếu JVM chết đột ngột.
- StepExecution counters phản ánh framework semantics, không phải ledger per-business key.
- Với multi-threaded chunks, phải kiểm tra listener/reader/writer thread safety và ordering.
- Với remote workers, thêm `jobExecutionId`, worker instance và source snapshot vào structured logs.
- Sau khi step hoàn tất, bước validator **đọc staged output và source inventory** để kết luận.

## 23. File output không có transaction giống database

JDBC writer có thể rollback business UPDATE trong DB transaction. Nhưng đối với tệp, bytes ghi ra filesystem hoặc object storage thường **không tự rollback atomically cùng Spring Batch transaction**.

~~~text
Chunk 1: viết 1.000 lines → commit checkpoint
Chunk 2: viết thêm 1.000 lines
Chunk 2: processor/writer lỗi → rollback chunk transaction
File: có thể đã nhận một phần bytes của chunk 2
JobRepository: checkpoint có thể vẫn ở chunk 1
~~~

Behavior cụ thể phụ thuộc `FlatFileItemWriter`, buffering, `ItemStream` state, transaction-aware output và version cấu hình. **Không coi mọi file writer đều flush bytes ngay lập tức, nhưng cũng không coi rollback JVM tương đương rollback filesystem.**

### Những điều phải kiểm chứng

- Writer có transaction-aware buffering không?
- `saveState` có bật để restart không?
- `open/update/close` được framework gọi và lưu trạng thái thế nào?
- Khi chunk rollback, bytes/offset được xử lý ra sao?
- Khi process bị kill trước `close`, staged file hiện ở trạng thái nào?
- Khi restart, writer truncate, resume hay append từ checkpoint nào?
- Khi chuyển worker JVM, nó có nhìn thấy cùng staged storage và file state không?
- Có bao giờ hai workers mở **cùng một path** để ghi đồng thời không?

**Một file được ghi dở là staging artifact**, không được phát cho downstream trước khi validator chấp nhận.

## 24. Spring Batch 5.x: writer riêng cho mỗi partition

Một cấu hình mẫu cho output dạng JSON Lines đã được processor serialize thành `String` hợp lệ. Dùng `@StepScope` để late-bind path riêng từ `ExecutionContext`:

~~~java
import org.springframework.batch.item.file.FlatFileItemWriter;
import org.springframework.batch.item.file.builder.FlatFileItemWriterBuilder;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
public FlatFileItemWriter<String> partitionJsonlWriter(
        @Value("#{stepExecutionContext['stagedOutputPath']}")
                String stagedOutputPath) {

    return new FlatFileItemWriterBuilder<String>()
            .name("partitionJsonlWriter")
            .resource(new FileSystemResource(stagedOutputPath))
            .lineAggregator(value -> value)
            .saveState(true)
            .shouldDeleteIfExists(false)
            .build();
}
~~~

### Cách hiểu đúng

- Reader/processor chịu trách nhiệm tạo **một JSON object hợp lệ trên một dòng**; đoạn writer không serialize JSON hay escape nội dung.
- `stagedOutputPath` phải là path được controller cấp từ manifest, đã validate nằm trong vùng staging cho phép; không lấy path chưa kiểm tra từ input user.
- Mỗi partition StepExecution phải ghi **file riêng**, không để các partition cùng append một tệp.
- `saveState(true)` lưu ItemStream state cần thiết theo Spring Batch lifecycle, **không bảo đảm** mọi cửa sổ file crash/rollback an toàn trên mọi filesystem.
- `shouldDeleteIfExists(false)` giúp tránh ghi đè im lặng trong trường hợp cấu hình/rerun; đường restart cần được test theo trạng thái ItemStream và sự tồn tại của file.
- Không dùng `@StepScope` để suy ra từng chunk thread có writer target riêng: scope theo StepExecution.
- Đây là bean minh họa; Step, JobRepository, TransactionManager, source reader và serialization cần được định nghĩa ngoài ví dụ.

### Khi retry với output dở dang

Có hai chiến lược cần chọn rõ:

1. **Resume cùng staged file:** rely on tested ItemStream checkpoint/seek/truncation semantics cho đúng filesystem, kết hợp source snapshot và writer state.
2. **Viết lại attempt file mới:** chọn staged output attempt mới từ input immutable rồi cuối cùng chỉ publish **một validated attempt**. Cách này đơn giản hơn để lý giải khi worker process đã chết trước khi close, nhưng có chi phí đọc/ghi lại.

Không trộn hai chiến lược mà không có protocol; đặc biệt không append vào file cũ chỉ vì file tồn tại.

## 25. Quy ước tên staging file và attempt ID

Một layout an toàn hơn việc dùng tên thread:

~~~text
staging/
  orders-2026-11-25-v1/
    partition-0000/
      attempt-01/
        data.jsonl
        data.manifest.json
    partition-0001/
      attempt-01/
        data.jsonl
        data.manifest.json
      attempt-02/
        data.jsonl
        data.manifest.json
~~~

Nguyên tắc:

- `logicalRunId` ổn định cho cùng dataset/business run.
- `partitionName` ổn định cho input range.
- `attemptId` duy nhất trong phạm vi phần việc khi tạo **attempt file mới**.
- Một output manifest chỉ trỏ tới **file cụ thể + version/generation + hash**.
- Finalizer chỉ chọn output attempt đã validated, theo một selection policy có audit.
- Attempt dở dang được giữ/quarantine trong retention window để điều tra.
- Không dùng tên JVM/thread làm khóa chính; worker có thể đổi sau restart.

### Idempotency giữa các lần chạy

Nếu cùng source snapshot + transform version + logicalRunId đã có published dataset, một rerun không được âm thầm overwrite. Có thể trả về existing validated manifest nếu business contract cho phép, hoặc tạo run revision mới; luôn giữ lineage/previous version để đối soát.

## 26. Local filesystem: staging rồi publish có kiểm soát

Với local/shared filesystem hỗ trợ thao tác rename atomic **trong cùng filesystem**, có thể:

1. Ghi `output.tmp` trong staging.
2. Flush/close writer; đảm bảo bytes đã được sync theo durability policy.
3. Validator đọc lại, tính SHA-256, count và business diff.
4. Ghi staged manifest cho output đã PASS.
5. Move/rename sang final path **đã dành riêng cho logicalRunId** bằng primitive atomic được filesystem hỗ trợ.
6. Công bố **ready manifest/marker** sau khi mọi file/partition có sẵn.
7. Downstream chỉ đọc khi thấy marker/manifest trạng thái COMMITTED.

Java ví dụ atomic move cho **một file**:

~~~java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

public final class PublishOneFile {

    public static void atomicMove(
            Path staged, Path finalPath) throws IOException {

        Files.move(
            staged, finalPath,
            StandardCopyOption.ATOMIC_MOVE);
    }
}
~~~

### Các giới hạn không được bỏ qua

- `ATOMIC_MOVE` có thể không được hỗ trợ, nhất là cross-filesystem; khi đó có thể nhận `AtomicMoveNotSupportedException`. **Không fallback copy rồi gọi đó là atomic.**
- Khi target đã tồn tại, behavior cụ thể có thể phụ thuộc filesystem/provider; cần cơ chế reserve run/version và chống overwrite có kiểm soát.
- Atomic visibility của rename **không đồng nghĩa fsync/durability tuyệt đối khi mất điện**; cần kiểm tra storage/OS guarantees và flush file/directory theo yêu cầu.
- Move một file không atomic với move **16 files khác**. Dataset cần một **commit marker/final manifest** để consumer thấy bộ file đã hoàn chỉnh.
- Với NFS/SMB/shared storage, phải test rename, cache consistency, close visibility và crash semantics theo provider thực.
- Không công bố final URI trong khi vẫn còn worker có quyền sửa file.

## 27. Object storage: "rename" thường không phải atomic move

Ở object storage (ví dụ S3-compatible), thao tác rename path thường được thực hiện bằng **copy + delete**, không phải một filesystem-level atomic rename. Tải nhiều partition objects cũng không phải một transaction trên cả dataset.

Một publication protocol thích hợp:

~~~mermaid
sequenceDiagram
    participant W as Worker/Writer
    participant S as Object storage
    participant V as Validator/Finalizer
    participant C as Downstream

    W->>S: Upload immutable staged partition objects
    V->>S: Read exact object generations
    S-->>V: Bytes + metadata
    V->>V: Hash, records, coverage, business diff
    V->>S: Write final manifest with exact object versions
    V->>S: Conditional publish COMMITTED marker
    C->>S: Discover committed marker
    C->>S: Read manifest and listed object versions
~~~

**Commit marker** chỉ được viết sau khi toàn bộ objects được upload/validate thành công. Downstream phải **tôn trọng protocol**: không liệt kê mọi object trong staging rồi tự coi chúng là dataset đã publish.

### Chống publish race

Nếu hai finalizers cùng cố commit logicalRunId:

- Dùng conditional create/compare-and-swap trên manifest pointer nếu storage API hỗ trợ, hoặc
- Dùng một DB ledger với unique key/status transition transactionally.
- Chỉ một run revision được ghi nhận COMMITTED; các attempts khác không được ghi đè.
- Khi cập nhật pointer, gắn exact object versions/generations đã validated.

Không suy rằng mọi object store có cùng consistency/conditional-write semantics; kiểm chứng provider đang dùng. Với một số providers, dữ liệu được đọc theo version/generation mới là cách chắc chắn tránh người khác overwrite path.

## 28. Tại sao marker phải là bước cuối?

Nếu finalizer công bố marker khi mới có 15/16 partition files, consumer có thể đọc thiếu một phần rồi ghi kết quả sai xuống database downstream.

Một marker nên chứa hoặc trỏ tới:

~~~json
{
  "logicalRunId": "orders-2026-11-25-v1",
  "manifestVersion": 1,
  "status": "COMMITTED",
  "sourceManifestId": "input-manifest-sha256",
  "outputManifestUri": "manifests/orders-2026-11-25-v1.json",
  "partitionsExpected": 16,
  "partitionsValidated": 16,
  "reconciliation": {
    "missingOccurrences": 0,
    "extraOccurrences": 0,
    "mismatchedBusinessKeys": 0
  }
}
~~~

Ví dụ trên là schema tự định nghĩa. **Bản thân marker không đủ bảo vệ** nếu downstream không xác minh hoặc nếu output manifest trỏ tới objects có thể bị ghi đè.

Quy trình đọc chuẩn:

1. Đọc COMMITTED marker của logical run/version.
2. Lấy output manifest đã pin version.
3. Kiểm tra danh sách file/generation/schema/hash nếu yêu cầu.
4. Đọc **chính các object versions** được khai báo, không lấy latest path bất kỳ.
5. Nếu bất kỳ file thiếu/hash khác, dừng/quarantine và báo lỗi; không tự đọc partial fallback.
6. Khi cần reprocess, tạo logical run revision và manifest mới thay vì sửa manifest đã commit.

## 29. Restart và checkpoint: tệp không tự rollback theo JobRepository

Khi worker crash giữa chunk:

~~~text
T0  Worker đọc partition-0002
T1  Ghi một phần staged output
T2  Metadata checkpoint ở chunk trước
T3  JVM bị kill trước close/flush
T4  Manager restart cùng logical partition
~~~

Có hai sự thật độc lập:

- JobRepository/ExecutionContext mô tả **checkpoint mà framework biết**.
- Storage chứa **bytes thực tế** của partial staged file, có thể có phần chưa commit hoặc đã buffered.

**Không tự append từ EOF** rồi giả định file khớp checkpoint. Cần:

- Kiểm thử thực tế `FlatFileItemWriter` với restart/saveState/transaction-aware buffering.
- Hoặc chọn **attempt mới** và replay partition từ source snapshot, rồi validate.
- Giữ input range/transform version ổn định.
- Không phát file từ unsuccessful attempt.
- Dọn dữ liệu attempts cũ **sau** khi final publication/retention policy cho phép.
- Nếu object storage không hỗ trợ seek/truncate như local file, ưu tiên immutable attempt objects và publish selector.

Một `StepExecution` có thể hoàn thành nhưng upload/copy/manifest thất bại sau đó; toàn job nên có **reconciliation/publish step** có trạng thái riêng và có thể restart idempotently.

## 30. Retry một partition không được nhân đôi output

Giả sử worker A xử lý partition P, ghi 900.000 lines rồi chết. Worker B được điều phối chạy P lại, tạo 1.000.000 lines đúng.

**Sai:** global merge ghép output A và B, thu 1.900.000 lines.

**Đúng:** finalizer biết P là **một logical partition**; chọn **chính xác một validated output attempt** (B) và không bao gồm A.

~~~text
Partition P:
  attempt-A → PARTIAL, not selected
  attempt-B → VALIDATED, selected

Global manifest:
  partition P → attempt-B only
~~~

Nếu A vẫn đang chạy khi B được khởi động, đó là vấn đề **worker ownership/fencing** khác; không chỉ dựa vào việc B gửi file trước. Cần JobRepository/recovery policy/lease khi phù hợp để tránh hai writers được nhận làm authoritative cùng lúc.

### Một điểm đáng chú ý

Nếu dữ liệu đầu ra phụ thuộc thứ tự nondeterministic, timestamp “now” hoặc random ID được sinh khi xử lý, attempt A/B có thể khác ngay cả khi cùng input. Muốn reproducible reconciliation, cần chốt **clock/cutoff/seed/transformVersion** hoặc có comparison semantics không yêu cầu byte-identical khi business contract cho phép.

## 31. Failure matrix của file scaling

| Failure window | Trạng thái file | Metadata có thể thấy | Hành động an toàn |
| --- | --- | --- | --- |
| Writer lỗi trước chunk commit | Partial staging | Step rollback/retry | Resume test-safe hoặc attempt mới |
| Worker chết sau một số chunk commits | Partial staging | Checkpoint tồn tại | Đối chiếu state, không publish partial |
| Worker chết trước writer close | Có thể thiếu buffered bytes | Step có thể RUNNING stale | Reconcile/restart từ snapshot |
| Hai workers ghi cùng path | Bytes lẫn nhau | Hai executions cạnh tranh | Cấm concurrent writer, fenced attempt path |
| Copy/upload bị ngắt | Object/file partial hoặc lỗi | Worker có thể đã COMPLETED | Upload retry, validate hash/generation |
| Mất manifest một partition | Data file có thể tồn tại | Worker COMPLETED | Rebuild manifest bằng validator độc lập |
| Manifest sai checksum | File không khớp khai báo | Counters vẫn đúng | Quarantine, không publish |
| Finalizer chết trước commit marker | Staged files đã đủ | Chưa published | Idempotent publish retry |
| Marker đã commit nhưng reply mất | Published dataset có thể sẵn | Manager timeout | Đọc ledger/marker; không tạo revision trùng |
| Input path bị ghi đè giữa run | Source snapshot không nhất quán | Workers có thể vẫn COMPLETED | Fail run, buộc immutable version |
| Merge lấy cả failed attempt | Output thừa/duplicate | Tổng Step counts có thể lệch | Exact-one-attempt rule |
| Downstream đọc trước marker | Có thể thấy thiếu files | Job chưa hoàn tất | Consumer protocol phải chặn |
| Cleanup xóa staging sớm | Không đủ bytes để validate/restart | Step metadata vẫn còn | Retention/recovery policy |
| DB/outbox downstream commit lỗi | File đã published | Downstream state incomplete | Downstream idempotency và reconciliation |

**Một bất biến cốt lõi:** **Không công bố dataset khi chưa có bằng chứng PASS cho đúng source snapshot và đúng bộ output files.**

## 32. Multi-threaded step và parallel steps

Với **multi-threaded step**, nhiều chunks chạy trong một StepExecution. Những thành phần như `ItemReader`, `ItemWriter` và `ItemStream` có thể giữ mutable state; `@StepScope` là scope theo StepExecution, **không phải mỗi chunk thread một instance**.

Rủi ro:

- State reader bị tranh chấp, đọc thiếu/đọc trùng.
- Writer chia sẻ buffer/offset, dòng xen kẽ.
- Chunk commit order khác input order.
- Checkpoint không còn đại diện duy nhất cho các chunk inflight.
- Một lỗi khiến rollback/retry một phần nhưng bytes từ chunk khác đã ghi ra.
- File manifest được tính trước khi worker threads thực sự hoàn tất.

### Phương án dễ kiểm soát hơn

Đối với file lớn cần scaling, thường có thể ưu tiên **file-per-partition** với một worker StepExecution sở hữu writer riêng, rồi merge/manifest cuối. Đó là cách giảm shared mutable writer và giúp kiểm tra độc lập từng phần.

**Không tuyên bố partitioning luôn nhanh hơn**. Phải đo tổng overhead tạo shards, parse, I/O contention, sort, merge và checksum. Một tệp trên một disk spindle đơn lẻ có thể bão hòa I/O trước khi CPU đạt trần.

Với **parallel steps**, nếu hai steps độc lập cùng viết một output path, vẫn có race; Step tên khác nhau không tạo transactional isolation cho filesystem.

## 33. File nén, archive và validation sau giải nén

Một file `orders.csv.gz` có hai lớp nội dung:

1. **Bytes nén vật lý**: nhận diện bằng `sizeBytes` và SHA-256 raw.
2. **Records sau giải nén/parse**: nhận diện bằng logical count, canonical digest và business keys.

Hai gzip files có thể giải nén ra cùng records nhưng bytes nén khác do compression level/metadata/implementation. Vì vậy raw SHA-256 khác **không tự chứng minh** bản ghi nghiệp vụ khác.

### Các kiểm tra cần thêm

- Gzip/trailer/checksum của compression format được xác minh khi đọc hết stream.
- Số bytes giải nén được kiểm soát; phòng chống input có compression ratio bất thường hoặc zip bomb.
- Character encoding được validate; không âm thầm thay bytes lỗi bằng replacement characters nếu business cần chính xác.
- Header/trailer của business file phải được kiểm tra sau giải nén.
- CSV parser phải chịu quoted multiline record, không đếm newline vật lý là record.
- Archive có nhiều files cần inventory từng entry, cấm duplicate/traversal paths nếu giải nén vào filesystem.
- Không cho reader đọc input sau khi file vẫn đang được ghi hoặc upload.
- Nếu tệp được nén lại, hash cả raw output và các logical records sau giải nén khi hợp đồng yêu cầu.

### Gzip có chia theo byte offset song song được không?

Một gzip stream thông thường không cho arbitrary workers tự bắt đầu giải nén ở một offset tùy ý mà vẫn tái lập đúng records. Có thể:

- Tạo **nhiều gzip shards độc lập** trước khi chạy partitions.
- Dùng indexed/splittable compression format có reader tương ứng.
- Giải nén một lần có kiểm soát thành staging shards, mỗi shard là các records hoàn chỉnh.
- Sử dụng storage layout dạng block/splittable file format như Parquet khi hợp đồng và hệ sinh thái cho phép.

Không nâng concurrency bằng cách để mỗi worker skip số bytes tùy ý trong tệp gzip rồi mong không thiếu/trùng.

## 34. Remote workers và shared output storage

Khi worker JVM khác nhau trên các máy/container:

- `file:/tmp/output.csv` của worker A **không phải** cùng filesystem với `file:/tmp/output.csv` của worker B.
- Reader/merger ở manager không được giả định nhìn thấy local paths của worker.
- Shared NFS/SMB có cache/locking/failure semantics riêng.
- Object storage có upload/version/commit-marker semantics riêng.
- Worker phải công bố file bằng **URI/generation bền vững** mà validator truy cập được.
- Nếu kết quả đưa qua middleware như remote chunking, cần định nghĩa message-level dedup và output ownership riêng.

**Remote partitioning:** mỗi worker StepExecution có input range và output path riêng, ghi partition manifest để manager tổng hợp. Không dùng worker hostname làm identity duy nhất vì partition có thể chạy ở JVM khác sau restart.

**Remote chunking:** manager đọc/chia chunk, worker nhận item để xử lý/ghi. Nếu mỗi worker tự append vào cùng shared file, nguy cơ interleaving/duplicate rất lớn. Có thể chọn sharded outputs theo logical work/request ID với dedup, hoặc để một writer/merge owner duy nhất; phải xác định **đơn vị atomic input/output** của kiến trúc chứ không gọi mỗi chunk là partition mặc định.

### Broker ACK không chứng minh file output đã publish đúng

Một worker có thể ACK request sau khi write nhưng trước khi finalizer validate/publish. Broker delivery state và file reconciliation state là **hai ranh giới khác nhau**. Nếu cần downstream chỉ thấy output đúng, phải có publication manifest/commit marker độc lập.

## 35. Chi phí đối soát khi dữ liệu rất lớn

Tính hash, parse lại, sort và merge tạo thêm I/O. Không thể chỉ tối ưu tốc độ writer rồi bỏ qua **thời gian validation cuối**.

Một mô hình gần đúng:

\[
T_\text{end-to-end}
=T_\text{ingest}
+T_\text{transform}
+T_\text{reconcile}
+T_\text{publish}
\]

Công thức thể hiện các giai đoạn tuần tự ở một pipeline đơn giản. Nếu các giai đoạn được **pipeline/overlap**, tổng wall-clock không còn bằng phép cộng trực tiếp; cần đo trên timeline thực.

### Tối ưu đúng chỗ

| Biện pháp | Lợi ích | Cẩn trọng |
| --- | --- | --- |
| Streaming SHA-256 | O(bytes), RAM nhỏ | Thêm lần đọc I/O |
| Hash ngay trong luồng ghi | Giảm đọc lại cho metric ban đầu | Không đủ làm validator độc lập |
| Partition-level validation | Song song trên shards | Cần global cross-partition diff |
| External sort/merge | Bounded memory cho datasets lớn | Temp disk, I/O nhiều lượt |
| SQL staging + EXCEPT ALL | Dễ query mismatch theo business schema | DB temp/sort/hash memory, pool budget |
| Raw + canonical digest | Kiểm tra file lẫn logical content | Phải pin canonical schema |
| Sampling bản ghi | Nhanh để phát hiện sớm | Không được xem là chứng minh đầy đủ |
| Incremental reconciliation | Chỉ so thay đổi khi có lineage đáng tin | Phải xử lý deletions/replays/version drift |
| Manifest chỉ danh sách shards | Không cần ghép monolithic file | Downstream phải hỗ trợ đọc nhiều shards |
| Đồng bộ I/O được chia hợp lý | Tăng throughput khi storage còn capacity | Quá nhiều readers làm nghẽn disk/network |

### Bounded memory không có nghĩa bounded disk

External sort với nhiều runs có thể cần nhiều vùng temporary files. Phải budget input/output files, sort spill, retry attempts và staging retention. Nếu disk tạm đầy giữa reconciliation, **không publish partial result**.

## 36. Mức tin cậy: sampling, control totals và full diff

Có thể chia ba mức:

**Level A — Fast screening:** size, file count, checksum, count, min/max, business totals. Phù hợp phát hiện lỗi phổ biến nhanh, nhưng không là chứng nhận 100% record correctness.

**Level B — Deterministic record verification:** expected/actual canonical records bằng multiset diff, record key/version checks và aggregate invariants. Phù hợp dữ liệu tài chính, ledger hoặc pipeline bắt buộc không thiếu/trùng.

**Level C — End-to-end business reconciliation:** ngoài record diff còn kiểm tra side effects và downstream dataset đã dùng đúng published manifest, schema, cutoff, version; tính đúng khi retry/restart.

### Sampling dùng thế nào?

Có thể kiểm tra ngẫu nhiên một tỷ lệ records sau khi **đã có cơ chế kiểm soát đầu đủ** để phát hiện sớm lệch schema/field mapping. Nhưng một sample 1% **không chứng minh** 99% còn lại đúng. Đừng viết `reconciliation=PASS` chỉ vì sample không tìm được mismatch nếu contract yêu cầu full proof.

### Hash canonical toàn tập có phải chứng minh chính xác mọi record không?

Một SHA-256 của canonical **sorted, length-framed** records là fingerprint mạnh để kiểm tra equality giữa hai tập được xây độc lập, nhưng việc tạo **expected** vẫn phải dựa trên logic/nguồn đáng tin. Nếu expected và actual dùng cùng hàm biến đổi bị sai, hai hash có thể giống nhau trong khi business rule sai. Cần golden datasets, property tests và business invariants độc lập.

## 37. Reconciliation report: phát biểu kết quả có bằng chứng

Một report tự chứa nên nêu:

~~~json
{
  "reportSchemaVersion": 1,
  "logicalRunId": "orders-2026-11-25-v1",
  "sourceManifestId": "input-manifest-v1",
  "transformVersion": "normalize-orders-v5",
  "state": "PASS",
  "partitionsExpected": 16,
  "partitionsSelected": 16,
  "sourceLogicalRecords": 50000000,
  "acceptedUnique": 49200000,
  "filtered": 400000,
  "duplicatesSuppressed": 300000,
  "rejected": 100000,
  "outputRecordsVerified": 49200000,
  "keyMissing": 0,
  "keyUnexpected": 0,
  "valueMismatch": 0,
  "businessTotalMismatch": 0,
  "outputManifestUri": "manifests/orders-2026-11-25-v1.json"
}
~~~

Mọi số đều **minh họa**, nhưng accounting equation nhất quán:

\[
50{,}000{,}000
=49{,}200{,}000
+400{,}000
+300{,}000
+100{,}000
\]

### Metadata audit cần thêm

- Ngày giờ UTC của source snapshot, processing, validation và publish.
- Tool/library/parser/canonicalizer versions.
- JobInstance/JobExecution/StepExecution references.
- File URIs + object versions/generations + SHA-256.
- Phương pháp đối soát: full multiset, hash, sampling và giới hạn của mỗi phép.
- Mismatch inventories có URI/hash/row count và quyền truy cập.
- Người/hệ thống phê duyệt ngoại lệ nếu có.
- Validation code/version để có thể tái hiện report.
- Dataset commit marker/immutable manifest pointer khi thành công.

**Report chính là một artifact phải được bảo vệ.** Nếu report có `PASS` nhưng output object đã bị ghi đè sau đó, proof không còn đúng; pin version hoặc dùng immutable paths.

## 38. Quality gate: PASS, FAIL và ngoại lệ được phê duyệt

Một state machine minh bạch:

~~~mermaid
stateDiagram-v2
    [*] --> PREPARING
    PREPARING --> WRITING: Input snapshot validated
    WRITING --> VALIDATING: Worker outputs closed
    VALIDATING --> RECONCILED: All checks PASS
    VALIDATING --> QUARANTINED: Mismatch / missing file
    RECONCILED --> COMMITTED: Publish marker succeeds
    RECONCILED --> RECONCILED: Publish retry after uncertain result
    QUARANTINED --> VALIDATING: Remediate and revalidate
    COMMITTED --> [*]
~~~

Đây là state machine **do ứng dụng thiết kế**, không phải enum Spring Batch mặc định.

### Có cho phép reject không?

Phụ thuộc nghiệp vụ:

- Dữ liệu tài chính bắt buộc đủ: `rejected=0` hoặc điều kiện nghiệp vụ được phê duyệt.
- ETL analytics có thể cho reject dưới threshold với **reject inventory đầy đủ**, alert và remediation.
- Batch làm sạch dữ liệu có thể kỳ vọng một tỷ lệ filter nhưng phải xác minh filter rule.
- Một file thiếu hoặc checksum sai thường là **hard FAIL**, không nên bỏ qua chỉ vì reject rate thấp.

**Ngưỡng chất lượng phải được định nghĩa trước run**, không sửa threshold sau khi thấy mismatch rồi coi đó là PASS mặc định. Ngoại lệ có thể được chấp nhận nhưng cần audit, phạm vi ảnh hưởng, sign-off và trạng thái riêng như `PASS_WITH_APPROVED_EXCEPTIONS` nếu tổ chức dùng.

### Khi publication thất bại sau đối soát PASS

Không cần xử lý lại 50 triệu records chỉ vì ghi marker bị timeout. Đọc trạng thái commit marker/ledger và retry **idempotent publish**. Tách reconciliation outcome khỏi publication outcome để tránh double output.

## 39. Metrics và cảnh báo vận hành

| Metric gợi ý | Mục đích |
| --- | --- |
| `file_input_snapshot_mismatch_total` | Source version/hash bị thay đổi |
| `file_partition_expected_count` | Số partitions phải có |
| `file_partition_validated_count` | Số validated outputs |
| `file_partition_failed_count` | Bao nhiêu partitions không PASS |
| `file_reconciliation_missing_total` | Số missing occurrences |
| `file_reconciliation_extra_total` | Số unexpected occurrences |
| `file_reconciliation_value_mismatch_total` | Số value mismatches |
| `file_reconciliation_rejected_total` | Số reject records |
| `file_reconciliation_validation_seconds` | Thời gian validation |
| `file_output_publish_lag_seconds` | Thời gian từ close đến commit marker |
| `file_output_bytes_verified_total` | Bytes thực đã hash/verify |
| `file_merge_read_bytes_total` | I/O merge |
| `file_staging_orphan_count` | Partial attempts chưa cleanup |
| `file_publication_failures_total` | Commit marker/upload/move lỗi |
| `batch_job_end_to_end_seconds` | SLA toàn pipeline |

Tên metrics trên là **gợi ý schema**, không mặc nhiên là metrics do Spring Batch tạo ra.

### Tránh high cardinality

`filePath`, `sourceGeneration`, `jobExecutionId` và `partitionName` có thể tăng không giới hạn nếu dùng làm metric labels. Ưu tiên metrics tổng hợp theo `job`, `stage`, `status`, `errorCategory`; để exact path/ID trong structured logs và reconciliation report.

### Hai metric bắt buộc xem cùng nhau

- `outputRecordsVerified` và `sourceLogicalRecords` theo accounting rules.
- `validationDuration` và `jobEndToEndDuration`.

Một job xử lý nhanh nhưng validation kéo dài quá SLA vẫn không đạt mục tiêu. Một job nhanh với missing/duplicate records cũng không đạt.

## 40. Bảo mật và dữ liệu nhạy cảm trong báo cáo đối soát

Đối soát có thể vô tình tạo **bản sao dữ liệu** ở nhiều nơi:

- Staged raw/canonical files.
- Reject files chứa dòng lỗi nguyên văn.
- Mismatch samples.
- SQL staging tables.
- Hash inventories.
- Debug logs và report attachments.
- Temporary sort files trên local disk.
- Archived old attempts.

### Chính sách cần có

- Không log raw row có PII chỉ để chứng minh missing.
- Dùng surrogate ID/pseudonymized key khi đủ.
- Áp dụng ACL và encryption cho staging, reject và report artifacts.
- Xóa/rotate temp files sau retention, nhất là external-sort spills.
- Pin source/output versions và kiểm tra integrity trước khi dùng.
- Quản lý keys riêng nếu dùng HMAC/chữ ký; SHA-256 alone **không chứng minh nguồn đáng tin**.
- Hạn chế path traversal, archive extraction traversal và output paths lấy từ user input.
- Có chính sách cleanup theo business/legal retention, không tự xóa failed attempts trước khi điều tra xong.

**Hash không làm dữ liệu trở thành vô hại.** Hash của một ID có entropy thấp có thể bị đoán bằng dictionary; không coi hash business key mặc định là ẩn danh hóa hoàn toàn.

## 41. Unit test những bất biến đối soát

Unit tests nên bắt lỗi dù không có worker cluster thật:

1. Accounting equations giữ đúng khi accepted/filtered/rejected/dedup.
2. Count bằng nhau nhưng key multiset khác → FAIL.
3. Duplicate hợp lệ theo contract được giữ đúng multiplicity.
4. Canonicalizer phân biệt NULL, empty, delimiter và Unicode theo schema.
5. Đổi LF ↔ CRLF hoặc column formatting không làm semantic comparison sai nếu contract cho phép.
6. Một payload canonical field đổi → digest/field diff thay.
7. CSV quoted multiline được parser coi là một record.
8. Range coverage không có gap/overlap.
9. One-to-many expected children được đếm đúng.
10. Amount sum dùng integer minor units/decimal scale chính xác.

### Ví dụ JUnit 5: count bằng vẫn FAIL

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;

import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;

class ReconcileBagTest {

    @Test
    void equalRowCountsDoNotMeanEqualMultisets() {
        List<String> expected =
                List.of("A", "B", "B", "C");
        List<String> actual =
                List.of("A", "B", "C", "C");

        assertEquals(expected.size(), actual.size());
        assertNotEquals(bag(expected), bag(actual));
    }

    private static Map<String, Long> bag(List<String> rows) {
        return rows.stream().collect(
            Collectors.groupingBy(
                Function.identity(),
                Collectors.counting()));
    }
}
~~~

Ví dụ dùng in-memory `Map` chỉ dành cho dataset nhỏ/unit test. Với vài chục triệu rows, dùng staging DB hoặc external sort theo phần 16–17.

## 42. Integration tests với Spring Batch và storage thật

Một integration test cần dựng input snapshot, JobRepository, reader/writer và validator; với remote worker, thêm shared storage và middleware tương ứng.

| Kịch bản | Assertions |
| --- | --- |
| Một file nhỏ, không lỗi | PASS, count/hash/key diff đúng |
| CSV quoted multiline | Parser không chia record sai |
| UTF-8 BOM và CRLF | Header/record count đúng contract |
| Invalid row | Reject inventory có reason; accounting balanced |
| Filtered data | Không báo missing nếu rule loại hợp lệ |
| Duplicate input event | Unique accepted và duplicatesSuppressed đúng |
| Partition gap | Global validation FAIL |
| Partition overlap | Cross-partition duplicate detect FAIL |
| Hai partitions song song | Output paths riêng, không interleaving |
| Same partition retry | Chỉ một validated attempt được selected |
| Chunk rollback | Partial staged bytes không được publish |
| Writer crash trước close | Artifact không được coi VALIDATED |
| Storage copy interrupted | Output checksum/generation mismatch FAIL |
| Merge thiếu một file | Partition inventory mismatch FAIL |
| Manifest chứa wrong version | Source snapshot mismatch FAIL |
| Object commit marker timeout | Idempotent recovery, không publish revision trùng |
| Producer ghi đè input trong run | Fail hoặc lock đúng immutable version |
| Worker JVM khác nhau | Manifest URIs đều accessible |
| Reconciliation fails | Không có COMMITTED marker |

**Đừng chỉ assert StepExecution COMPLETED.** Kiểm tra **bytes thực**, records logic, business key/version values và publication state.

### Tránh test flaky

Dùng polling theo điều kiện với deadline hữu hạn, không dựa vào `Thread.sleep(3000)` cố định để chờ remote workers. Inject failure tại các mốc transaction/file-close/upload/commit-marker rõ, không dựa hoàn toàn vào timing ngẫu nhiên.

## 43. Fault injection: kiểm tra crash windows thực

Một ma trận lỗi cần thiết cho production:

~~~mermaid
sequenceDiagram
    participant S as Source snapshot
    participant W as Worker
    participant O as Staging storage
    participant V as Validator
    participant P as Publication ledger/marker
    participant C as Consumer

    S->>W: Immutable input
    W->>O: Write staged partition
    W--xO: Crash trước close
    Note over W,O: Partial attempt phải bị loại
    W->>O: Retry attempt mới
    V->>O: Read and validate
    O-->>V: Exact bytes/version
    V->>P: Commit manifest khi PASS
    P-->>C: Visible committed version
~~~

### Những lần inject lỗi quan trọng

- Trước và sau chunk checkpoint.
- Ngay trước writer `close()` và ngay sau writer close.
- Khi file đang hash/upload.
- Sau validation, trước ghi output manifest.
- Sau manifest tạo, trước commit marker.
- Commit marker thành công nhưng worker/finalizer không nhận reply.
- Hai finalizers cùng cố publish một logicalRunId.
- Hai worker cùng nhận một logical partition do timeout/ownership bug.
- Storage đầy trong bước external sort.
- Object version bị thay khi consumer đang đọc.
- Worker bị kill trước khi flush log/metric.
- Cleanup chạy nhầm trước khi reconciliation kết thúc.

Assertions phải xác nhận **không có partial dataset được công bố**, recovery idempotent và final manifest chỉ chứa đúng một output per partition.

## 44. Case study: 50 triệu giao dịch, 16 partitions

Một hệ thống chuẩn hóa **50.000.000 giao dịch** trong **60 phút**, từ tệp CSV nén và xuất các shards JSONL cho downstream. Input được chốt theo immutable generation. Job chạy 16 partitions trên 8 worker JVM.

Throughput nguồn lý tưởng tối thiểu:

\[
R_\text{required}
=\frac{50{,}000{,}000}{60\times60}
\approx 13{,}889\ \mathrm{records/s}
\]

Đây là tốc độ nguồn cần thiết **nếu không có overhead**; SLA thực còn bao gồm extract/sharding, validation, merge/publish, retries và tail latency.

### Phân loại đầu vào

Giả định theo business contract:

| Nhóm | Số lượng |
| --- | ---: |
| Unique accepted | 49.200.000 |
| Business filtered | 400.000 |
| Duplicate suppressed | 300.000 |
| Rejected | 100.000 |
| **Input tổng** | **50.000.000** |

Output đúng theo hợp đồng one-to-one cho unique accepted là **49.200.000 records**. Chỉ nhìn `readCount - writeCount = 800.000` không đủ biết mất dữ liệu hay lọc hợp lệ; các nhóm trên giải thích từng occurrence.

### Thiết kế ban đầu có lỗi

- Input được chia theo newline byte offset, làm một số CSV multiline records bị cắt đôi.
- Workers ghi file names dựa vào thread name và đôi lúc reuse path.
- Một partition retry để lại partial file, merge lấy cả attempt cũ.
- JobRepository báo các steps cuối COMPLETED, nhưng output có missing/trùng.
- Không có commit marker nên consumer có thể đọc output khi merge còn chạy.

**Root cause:** scaling song song được triển khai trước khi định nghĩa source snapshot và publication/reconciliation contract.

### Thiết kế cải tiến

1. Khóa immutable source generation và source SHA-256.
2. Dùng CSV-aware sharding thành 16 nguồn records hợp lệ.
3. Mỗi partition có deterministic identity và output attempt path riêng.
4. Worker ghi staging, không publish trực tiếp.
5. Partition validator đóng/đọc lại file, xác minh SHA/count/format/record inventory.
6. Global reconciler tính accounting 50 triệu và full key/version multiset diff.
7. Đối chiếu totals theo currency/date, không chỉ một grand total.
8. Finalizer tạo immutable manifest và COMMITTED marker cuối cùng.
9. Consumer chỉ xử lý exact object generations trong committed manifest.
10. Crash/restart chỉ chọn một validated attempt, giữ audit failed attempts.

### Benchmark giả định

| Cấu hình | Throughput xử lý nguồn | Thời gian lý tưởng 50M/R | Đối soát |
| --- | ---: | ---: | --- |
| 4 workers, merge serial | 9.000 records/s | 92,6 phút | Chưa hoàn chỉnh |
| 8 workers, storage contention | 12.000 records/s | 69,4 phút | Có discrepancy |
| 8 workers, sharding an toàn | 16.200 records/s | 51,4 phút | PASS khi chưa cộng validation |
| 12 workers, cùng storage bottleneck | 16.400 records/s | 50,8 phút | PASS, lợi ích biên nhỏ |
| 8 workers, optimized validation/merge | 16.200 records/s | 51,4 phút xử lý | PASS end-to-end chỉ nếu validation/publish trong ngân sách |

Số liệu **giả định**, không phải benchmark thực của Spring Batch. Dòng cuối chưa chứng minh đạt 60 phút: validation và publish phải hoàn tất trong khoảng **8,6 phút còn lại**, hoặc được pipeline an toàn để giảm tổng wall-clock.

### Tiêu chí nghiệm thu

- Source manifest pin immutable generation.
- Đủ 16 partition outputs hợp lệ, không double-attempt.
- Accounting: 50M = 49,2M + 0,4M + 0,3M + 0,1M.
- Đúng 49,2M output records, key/value multiset diff = 0.
- Reject inventory đủ 100.000 rows có reason/audit.
- Hash/size của mọi output đúng và không bị sửa sau validation.
- COMMITTED marker chỉ xuất hiện sau PASS.
- Thử kill worker giữa chunk, merge, marker vẫn recovery an toàn.
- **Tổng thời gian end-to-end** dưới SLA với headroom cho lỗi thông thường.

**Bài học:** scaling file chỉ thành công khi **throughput, tính đúng dữ liệu và publication integrity** cùng đạt mục tiêu.

## 45. Runbook khi phát hiện output mismatch

Khi validation FAIL, **không công bố dataset** và không retry ngẫu nhiên cả job ngay lập tức.

**Bước 1 — Cố định bằng chứng.** Giữ source manifest, exact input generation, staged output versions, partition manifests, JobExecution IDs và mismatch report.

**Bước 2 — Phân loại sai lệch.** Missing file, wrong SHA, parse error, count mismatch, duplicate, missing key, changed value, business total mismatch hay wrong source version?

**Bước 3 — Kiểm tra partition coverage.** Danh sách expected vs actual partitions, ranges và file-per-partition attempt selection.

**Bước 4 — Kiểm tra retries.** Có partial attempt được gộp, writer append trùng hoặc job restart đọc lại input mới không?

**Bước 5 — Kiểm tra parser.** CSV quotes/multiline, BOM, encoding, gzip boundaries, null/decimal/timestamp canonicalization.

**Bước 6 — So record inventories.** Lấy sample missing/extra với business key+version, sau đó chạy full diff để xác định phạm vi.

**Bước 7 — Kiểm tra merge/publish.** Downstream có đang dùng manifest/generation cũ? Marker có được công bố quá sớm không?

**Bước 8 — Chọn remediation.** Sửa partitioner/parser/writer, chạy lại **chỉ logical partitions bị ảnh hưởng** khi có thể chứng minh ổn định; hoặc tạo một run revision mới nếu source/transform contract thay đổi.

**Bước 9 — Validate lại độc lập.** Hash staged files, counts, multiset diff và business totals; không dùng kết quả “PASS cũ” sau khi sửa artifact.

**Bước 10 — Publish có kiểm soát.** Commit manifest/marker idempotent, thông báo consumer đúng version rồi dọn orphan staging theo retention.

Không tự đánh dấu PASS do sự khác biệt nhỏ “có vẻ chấp nhận được” khi chưa có policy được duyệt.

## 46. Các ngộ nhận cần tránh

| Ngộ nhận | Thực tế |
| --- | --- |
| “Job COMPLETED là mọi file đã đúng.” | Step status không đọc lại contents của output. |
| “readCount = writeCount nghĩa không mất record.” | Missing có thể được bù bởi duplicate. |
| “Cùng SHA-256 là business đúng.” | Hash xác nhận bytes, không xác nhận logic nguồn. |
| “Khác raw hash tức dữ liệu logic khác.” | Encoding/order/compression khác vẫn có thể cùng records. |
| “CSV mỗi dòng vật lý là một record.” | Quoted multiline phá giả định này. |
| “Chia .gz theo byte offsets dễ như text.” | Gzip stream thường không splittable tùy ý. |
| “Partition ranges có tên khác là không overlap.” | Phải kiểm chứng boundaries và source inventory. |
| “@StepScope tạo writer riêng cho từng chunk thread.” | Scope theo StepExecution. |
| “Rollback chunk tự xóa bytes file.” | File không mặc nhiên transactional như JDBC. |
| “Ghi file cùng path trên hai JVM vẫn an toàn.” | Có thể interleaving/truncate/race. |
| “Writer báo DONE thì file đã flush/close.” | Cần kiểm chứng lifecycle và storage. |
| “Atomic rename một file publish được toàn dataset.” | Nhiều files cần commit marker/manifest. |
| “Object storage rename là atomic.” | Thường copy+delete; phải có publication protocol. |
| “ETag luôn là MD5 raw content.” | Không đúng với mọi provider/multipart. |
| “EXCEPT thay được EXCEPT ALL.” | EXCEPT loại multiplicities, bỏ sót lỗi duplicate. |
| “Hash XOR toàn file là proof mạnh.” | Duplicates có thể triệt tiêu. |
| “Merge tất cả attempts sẽ đủ dữ liệu.” | Có thể nhân đôi partial output. |
| “Thêm worker luôn làm nhanh validation.” | Storage/I/O/sort/DB có thể bão hòa. |
| “Sampling 1% chứng minh 100% đúng.” | Sampling chỉ phát hiện xác suất. |
| “Không có reject nghĩa dữ liệu chuẩn.” | Có thể silent filter/parser loss. |
| “Consumer có thể tự quét staging.” | Có thể đọc partial output trước commit marker. |
| “Read count cộng qua restarts bằng input unique.” | Replays có thể bị đếm nhiều lần. |

## 47. Checklist đưa vào production

- [ ] Có source manifest cho **immutable file/directory snapshot**.
- [ ] Input path/version/generation được pin qua retry/restart.
- [ ] Schema, CSV dialect, encoding, compression và transform version rõ.
- [ ] Parser xử lý quoted multiline, UTF-8/BOM và trailer đúng.
- [ ] Quy tắc accepted/filtered/rejected/dedup disjoint và đầy đủ.
- [ ] Hợp đồng one-to-one/one-to-many/aggregation được tài liệu hóa.
- [ ] Business key/version/occurrence identity đủ cho multiset diff.
- [ ] File SHA-256 và logical canonical comparison được phân biệt rõ.
- [ ] Canonical schema có framing, decimal/timezone/null semantics cố định.
- [ ] Partitioner không gap/overlap và deterministic qua restart.
- [ ] Mỗi partition ghi staged file riêng, không concurrent append chung path.
- [ ] File writer restart/checkpoint được kiểm chứng trên storage thật.
- [ ] Có output attempt identity và policy chọn **đúng một validated attempt**.
- [ ] Partition manifest được tạo **sau close và readback output**.
- [ ] Global gate đối chiếu expected partition inventory và source snapshot.
- [ ] Counts, business totals, key/value multiset và reject inventory đúng.
- [ ] Validation không chỉ dựa vào StepExecution counters.
- [ ] Merge không thiếu/trùng files và ordering được định nghĩa.
- [ ] Không publish khi bất kỳ file/hash/schema/record check quan trọng FAIL.
- [ ] Local filesystem atomic move chỉ dùng khi provider hỗ trợ.
- [ ] Object storage dùng immutable artifacts và commit marker/manifest pointer.
- [ ] Publication idempotent và chống race hai finalizers.
- [ ] Consumer chỉ đọc exact committed manifest/object generations.
- [ ] Có ngân sách cho checksum/validation/sort/merge trong **SLA end-to-end**.
- [ ] Có temp disk, storage và connection pool budgets toàn cluster.
- [ ] Có retention/cleanup cho partial attempts, rejects và reports.
- [ ] Logs/metrics không làm lộ PII hoặc tạo high-cardinality labels vô hạn.
- [ ] Có unit tests của accounting, canonicalization, duplicates và boundaries.
- [ ] Có integration tests cho restart, rollback, crash, upload và merge.
- [ ] Có fault injection trước/sau close/validate/commit marker.
- [ ] Có runbook khi mismatch và chính sách phê duyệt ngoại lệ.
- [ ] Chỉ công nhận hoàn thành khi **output đúng và đã được công bố an toàn**.

## 48. Câu hỏi tự kiểm tra

**1. Vì sao cùng số dòng giữa input và output chưa chứng minh đúng?**

Vì một record thiếu có thể được bù bằng một record trùng. Cần key/version multiset hoặc canonical content diff.

**2. Tệp CSV có trường quoted chứa newline. Vì sao không split theo newline bytes?**

Vì một logical record có thể trải qua nhiều dòng vật lý; split ở giữa quoted field khiến parser hoặc partition coverage sai.

**3. Khi nào nên so SHA-256 raw input/output trực tiếp?**

Khi yêu cầu **byte-for-byte equality** (ví dụ copy nguyên vẹn). Nếu có transformation/compression/order khác, dùng canonical record/business reconciliation.

**4. Vì sao ETag không phải checksum SHA-256 phổ quát?**

Semantics phụ thuộc provider, multipart upload và encryption. Phải kiểm chứng thuật toán và phạm vi bytes được đảm bảo.

**5. accepted 970.000, filtered 20.000, rejected 10.000 thì input kỳ vọng là bao nhiêu?**

1.000.000 logical records, với điều kiện ba nhóm không giao nhau và phủ toàn bộ input.

**6. Hai records cùng order_id nhưng khác source_version có phải duplicate không?**

Không mặc nhiên; có thể là hai event versions hợp lệ. Identity/dedup contract phải quyết định.

**7. Vì sao EXCEPT ALL hữu ích hơn EXCEPT khi so hai tập output có duplicates hợp lệ?**

EXCEPT ALL giữ multiplicity. EXCEPT thường chỉ so set nên không phát hiện thiếu/thừa occurrences của cùng record.

**8. Vì sao không dùng XOR row hashes làm proof toàn dữ liệu?**

Vì hai occurrences giống nhau XOR triệt tiêu, khiến một số lỗi duplicates bị che khuất.

**9. Một StepExecution COMPLETED nhưng output file bị truncate trong lúc upload. Gate phải làm gì?**

Hash/size/readback sẽ FAIL; không publish. Upload/rebuild attempt rồi validate lại theo cùng source snapshot.

**10. Tại sao cần attemptId khác partitionName?**

PartitionName xác định phần việc logic; attemptId xác định một lần ghi output. Khi restart có thể nhiều artifacts, finalizer chọn đúng một validated attempt.

**11. @StepScope có tự tạo một writer cho mỗi chunk thread không?**

Không. Scope gắn với StepExecution; multi-threaded chunks có thể truy cập cùng target bean nên cần thread safety.

**12. Khi object storage không có atomic rename, làm sao ngăn downstream đọc partial dataset?**

Upload các immutable objects, validate, tạo final manifest trỏ exact generations, rồi commit marker/pointer cuối; consumer chỉ đọc khi marker đã COMMITTED.

**13. Vì sao marker phải được tạo sau validation toàn job?**

Nếu marker xuất hiện khi một partition chưa có, consumer có thể đọc thiếu data rồi ghi kết quả sai.

**14. Nếu merge lấy cả attempt-A partial và attempt-B thành công thì sao?**

Output bị duplicate. Chỉ chọn một validated attempt cho mỗi logical partition.

**15. Vì sao đọc lại output là cần thiết dù writer đã tự báo hash/count khi ghi?**

Writer tự báo không chứng minh file được flush, upload, copy hoặc lưu đúng. Independent readback kiểm tra bytes/records thật trên storage.

**16. Sampling 1% không tìm thấy lỗi có được công bố PASS khi hợp đồng yêu cầu full reconciliation?**

Không. Sampling không chứng minh 99% còn lại; cần full multiset/key comparison theo contract.

**17. Một job 50 triệu records có accepted 49,2 triệu, filtered 0,4 triệu, duplicate 0,3 triệu, rejected 0,1 triệu. Có bị mất 0,8 triệu không?**

Không nếu mọi nhóm theo contract được ghi nhận và output đúng 49,2 triệu unique accepted records. Cần xác minh reject inventory, duplicate reason và key-level diff.

**18. Một pipeline xử lý nhanh trong 50 phút nhưng reconciliation/publish tốn thêm 20 phút, SLA 60 phút thì đạt không?**

Không; end-to-end là 70 phút, quá SLA. Cần tối ưu toàn pipeline và giữ validation như gate không thể bỏ qua.

**19. Worker crash sau khi viết 80% file và JobRepository checkpoint đã commit phần nào. Có thể append từ EOF không?**

Không tự động. Cần kiểm chứng writer/ItemStream restart semantics và file offset; hoặc ghi attempt mới rồi chọn validated output.

**20. Thước đo cuối cùng của file scaling thành công là gì?**

Dữ liệu được ghi đúng theo source snapshot/transform contract, không thiếu/trùng sai, có checksum/manifest và publication an toàn, có thể restart/reconcile, đồng thời đạt throughput và SLA end-to-end.

---

**Ghi nhớ:** Đối soát file đầu vào đầu ra không chỉ là `readCount = writeCount` hay `JobExecution COMPLETED`. Phải cố định **input snapshot**, diễn giải **mọi record** theo accepted/filtered/rejected/dedup contract, đối chiếu **business key/version/multiset và control totals**, rồi **đọc lại file thực** để xác minh size/hash/format. Khi scaling nhiều workers, mỗi partition cần output attempt riêng; global validator chọn đúng một validated attempt và chỉ **publish immutable manifest/commit marker sau khi toàn bộ dataset PASS**. Tính đúng dữ liệu, khả năng restart an toàn và SLA end-to-end quan trọng ngang throughput.
