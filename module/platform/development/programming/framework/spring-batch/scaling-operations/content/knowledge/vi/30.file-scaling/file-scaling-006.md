# Process indicator cho file

Một Spring Batch job xử lý 50.000 file CSV thường cần trả lời những câu hỏi tưởng đơn giản: **file nào đã sẵn sàng, file nào đang được một worker xử lý, file nào thực sự hoàn tất, file nào lỗi và có thể chạy lại?** Nếu chỉ liệt kê `inbox/*.csv` rồi cho nhiều tiến trình đọc, hai worker có thể xử lý trùng file. Nếu chuyển file sang thư mục `processed` ngay khi đọc hết dòng cuối, transaction ghi database vẫn có thể rollback hoặc worker khác còn đang xử lý. **Process indicator cho file** là cơ chế gắn **trạng thái tiến độ và kết quả xử lý** với **danh tính một file bất biến**, giúp điều phối, quan sát và khôi phục công việc một cách có căn cứ.

Bài học thuộc chương **File scaling** của module **SPRING_BATCH_SCALING_OPERATIONS**. Module hướng đến mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và mô hình phân tán, cùng việc đo nút thắt, bảo đảm thread safety, retry/restart, vận hành job và chọn kiến trúc theo nguồn lực thực tế. Nội dung này tập trung vào **process indicator cấp file**: marker file, bảng manifest, state machine, claim/lease, liên hệ với `JobRepository` và `ExecutionContext`, cách ngăn ghi trùng khi worker lỗi và cách kiểm thử đa tiến trình.

> **Điều cần ghi nhớ ngay:** process indicator là **bằng chứng trạng thái theo một protocol được thống nhất**, không tự động là transaction, file lock hay chứng nhận exactly-once. Một cờ `PROCESSED` chỉ đáng tin khi ứng dụng xác định **ai được đổi cờ, dựa trên điều kiện nào, và phải làm gì nếu output đã commit nhưng cờ chưa kịp cập nhật**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Định nghĩa process indicator, phân biệt indicator **trên file**, **trong database**, **trong object metadata** và **trong JobRepository**.
2. Thiết kế trạng thái `READY → PROCESSING → PROCESSED` cùng các nhánh `FAILED`, `RETRYABLE` và `QUARANTINED` có ý nghĩa rõ.
3. Giải thích **file identity** theo `batchKey`, `fileId`, `version/checksum` và vì sao filename đơn thuần không đủ.
4. Phân biệt **marker file, OS FileLock, atomic move, DB claim, lease và fencing**.
5. Cài đặt claim/heartbeat/completion nguyên tử bằng PostgreSQL, bao gồm kiểm tra `workerId` và `leaseEpoch`.
6. Kết hợp reader theo `@StepScope`, `ExecutionContext`, `StepExecution` và checkpoints của Spring Batch 5.x.
7. Xử lý chính xác trường hợp commit business DB thành công nhưng cập nhật process indicator thất bại.
8. Ngăn stale worker sau lease expiry, duplicate business effects và tình trạng indicator được đánh dấu thành công quá sớm.
9. Thiết kế archive/publish, kiểm tra record coverage, checksum, skip/retry và đối soát.
10. Xây test đa JVM/process, crash injection, recovery/replay và runbook vận hành.

**Tình huống xuyên suốt:** mỗi ngày có 12.000 file CSV bất biến trong `/data/ready/`. Hai Spring Batch managers và tám worker JVM có thể cùng nhìn thấy một vùng lưu trữ. Mỗi file chứa vài nghìn giao dịch cần import vào PostgreSQL. Nếu `orders-042.csv` được xử lý bởi worker A, worker B phải biết nó đã có owner; nếu A chết sau khi commit 70% dữ liệu, B phải khôi phục an toàn thay vì nhập trùng hoặc đánh dấu sai rằng file hoàn tất.

## 2. Process indicator là gì?

**Process indicator** là thông tin biểu diễn **trạng thái đã/đang/chưa xử lý** của một đơn vị công việc. Ở mức file, đơn vị ấy phải là **một logical file version**, không chỉ một đường dẫn có thể đổi nội dung.

Các hình thức thường dùng:

| Hình thức | Ví dụ | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- |
| **Marker file (sidecar)** | `file.csv.ready`, `file.csv.processing`, `file.csv.done` | Trực quan, dễ tích hợp shell/legacy | Race, stale marker, không có transaction chung với DB |
| **Đổi thư mục/trạng thái file** | `ready/file.csv → processing/file.csv → archive/file.csv` | Dễ quan sát, có thể dùng rename nguyên tử | Cross-filesystem, stale owner, không nói gì về DB commit |
| **Database manifest** | Hàng `file_ingestion` có `state=PROCESSING` | Query/CAS/claim nguyên tử, audit, chung giữa JVM | Cần DB khỏe; state khác business commit nếu resource khác |
| **Object metadata/tag** | `status=processed`, object version | Hữu ích trên cloud object store | Tag/metadata update không mặc định là CAS/transaction với DB |
| **JobRepository** | `JobExecution`, `StepExecution`, `ExecutionContext` | Framework quản lý step, checkpoint, restart | Không tự là catalog trạng thái của mọi file trên inbox |

**Indicator không phải nguồn chân lý duy nhất cho mọi thứ.** Khi business output nằm trong DB còn file nằm trên NFS/S3, trạng thái tối ưu là **indicator + transaction/checkpoint + input snapshot + business reconciliation**.

## 3. Khác biệt giữa indicator, lock và completion

| Công cụ | Câu hỏi được trả lời | Không được suy ra |
| --- | --- | --- |
| `state=READY` | File đủ điều kiện được lấy theo policy? | Chưa process nào đã bắt đầu nếu claim không nguyên tử |
| `state=PROCESSING` | Một owner được ghi nhận đang/đã nhận file? | Process chắc chắn còn sống và có quyền vô hạn |
| `state=PROCESSED` | File đã đạt tiêu chí xử lý được quy định? | Mọi event/API ngoài DB được gửi đúng một lần |
| `state=FAILED` | Lần xử lý hiện tại không đạt? | Toàn bộ chunk đã commit trước đó rollback |
| `FileLock` | Có process đang giữ OS lock? | File đã processed, DB đã commit |
| `ATOMIC_MOVE` | Tên file chuyển như một thao tác atomic theo FS hỗ trợ? | Ranh giới commit chung với JobRepository |
| `leaseEpoch` | Phiên ownership nào mới hơn? | Stale worker không thể ghi nếu sink không kiểm epoch |
| `BatchStatus.COMPLETED` | Framework hoàn thành execution theo flow? | Tập business keys chắc chắn được đối soát |

Điểm tinh tế: một file có thể ở trạng thái **PROCESSING** trong manifest nhưng worker đã chết; hoặc có thể **business output hoàn tất** nhưng manifest vẫn **PROCESSING** vì worker chết trước khi update. Đây không nhất thiết là dữ liệu bị hỏng — đó là **khoảng hở giữa các resource** cần được xử lý bằng recovery protocol.

## 4. Hai mức độ indicator: file và record

Trong hệ sinh thái Spring Batch, từ *process indicator* đôi khi dùng cho **cờ xử lý trên từng record** trong database, ví dụ `processed_flag` hoặc `status` trên bảng nguồn. Bài này tập trung vào **indicator cho cả file**, nhưng phải hiểu sự khác nhau:

~~~text
File indicator:
  file-42.csv  PROCESSING

Record indicators bên trong file:
  record-001  COMMITTED
  record-002  COMMITTED
  record-003  BAD_RECORD
  record-004  PENDING
~~~

**File PROCESSING** không cho biết chính xác bao nhiêu record đã commit. **File PROCESSED** phải là kết quả **kiểm tra toàn bộ tập record** theo policy: output hợp lệ + filtered hợp lệ + quarantined được phép, hoặc một tập kết quả khác đã định nghĩa rõ.

Khi một file chứa hàng triệu record, indicator cấp file thường phối hợp với **Spring Batch checkpoint** của reader, **unique keys ở sink**, và có thể với **record-level ledger** nếu nghiệp vụ yêu cầu. Không tạo hàng triệu cờ record chỉ để thay thế reader checkpoint khi không có nhu cầu.

## 5. Định nghĩa state machine của một logical file

Một bộ trạng thái minh họa:

~~~mermaid
stateDiagram-v2
    [*] --> DISCOVERED
    DISCOVERED --> READY: producer sealed and validated
    READY --> PROCESSING: atomic claim
    PROCESSING --> VERIFYING: all worker chunks finished
    VERIFYING --> PROCESSED: coverage and business validation OK
    PROCESSING --> FAILED: non-retryable failure
    VERIFYING --> FAILED: validation mismatch
    PROCESSING --> RETRYABLE: recoverable failure
    RETRYABLE --> PROCESSING: new claim / epoch
    FAILED --> QUARANTINED: manual review
    QUARANTINED --> READY: approved correction/new version
    PROCESSED --> ARCHIVED: move/retention completed
~~~

Đây là **state machine của ứng dụng**, không phải enum hay cơ chế tự động của Spring Batch.

| State | Hợp đồng tối thiểu | Ai được chuyển trạng thái? |
| --- | --- | --- |
| `DISCOVERED` | Đã thấy metadata/file, producer có thể còn ghi | Ingestion coordinator |
| `READY` | Nguồn bất biến, đã được publish và có identity/version | Producer/ingestion service sau verify |
| `PROCESSING` | Đã claim owner/lease; có thể commit từng chunk | Worker được cấp quyền |
| `VERIFYING` | Xử lý kết thúc, đang đối soát | Worker/coordinator được ủy quyền |
| `PROCESSED` | Toàn file đạt policy về output, skip và coverage | Verifier/coordinator |
| `RETRYABLE` | Có thể thử lại cùng snapshot mà không mất tính đúng | Recovery coordinator |
| `FAILED` | Không được coi hoàn tất; cần điều tra | Worker/coordinator |
| `QUARANTINED` | File bị cách ly do integrity/security/schema issue | Operator/workflow có quyền |
| `ARCHIVED` | File đã được archive và target đã xác minh | Archive coordinator |

**Không tự đánh dấu `PROCESSED` khi reader gặp EOF**. EOF có thể xuất hiện trước khi chunk cuối commit, trước khi worker reply đến manager, trước khi skip policy được đánh giá hoặc trước khi report validation đạt.

## 6. Danh tính file phải bất biến và đủ phân biệt

Ví dụ hai file cùng tên có thể được producer gửi vào hai ngày:

~~~text
2026-11-26 /tenant-a/orders.csv  sha256=aaa...
2026-11-27 /tenant-a/orders.csv  sha256=bbb...
~~~

Nếu indicator chỉ có key `orders.csv`, status `PROCESSED` của hôm qua có thể làm hệ thống **bỏ qua file hôm nay**. Tương tự, hai tenant có thể có file cùng tên.

Nên mô hình hóa:

~~~json
{
  "fileId": "tenant-a/2026-11-26/orders-v3",
  "batchKey": "daily-orders-2026-11-26",
  "tenantId": "tenant-a",
  "sourceUri": "file:///data/ready/tenant-a/orders.csv",
  "sourceVersion": "sha256:4df5...91ac",
  "expectedLogicalRecords": 25000,
  "schemaVersion": "orders-v3"
}
~~~

Đây là **metadata envelope ứng dụng**. Với object store, dùng object version/generation (và checksum nếu cần), không coi ETag luôn đồng nghĩa SHA-256 nội dung. Với CSV nhiều dòng trong một field, `expectedLogicalRecords` khác số dòng vật lý.

**Quy tắc:** cùng một fileId phải tham chiếu **một immutable source version** theo hợp đồng. Nếu bytes đã thay đổi, cần sourceVersion/fileId hoặc correction batch mới, không sửa ngầm sau khi StepExecution đã checkpoint.

## 7. Marker file: cách đơn giản nhất nhưng dễ sai

Một hệ thống legacy có thể dùng sidecar:

~~~text
inbox/orders-42.csv
inbox/orders-42.csv.ready
inbox/orders-42.csv.processing
inbox/orders-42.csv.done
inbox/orders-42.csv.failed
~~~

Không có nghĩa mọi marker đều cùng tồn tại. Cần một **protocol rõ về sự tồn tại và chuyển trạng thái**:

- `.ready`: producer đã đóng file, checksum/manifest có thể xác minh, consumer mới được claim.
- `.processing`: có worker đang/đã nhận file theo giao thức claim.
- `.done`: file thỏa điều kiện **business processing hoàn tất**, không chỉ “đã đọc hết”.
- `.failed`: file chưa xử lý thành công; có reason và owner/attempt để điều tra.

**Hai vấn đề quan trọng:**

1. Kiểm tra `Files.exists(processingMarker)` rồi tạo file **không nguyên tử**; hai worker có thể cùng thấy marker chưa có.
2. Sự tồn tại của `.processing` sau worker crash **không chứng minh worker vẫn đang sống**. Tự xóa theo tuổi file có thể tạo hai owners khi worker cũ chỉ bị tạm dừng.

### Ví dụ tối thiểu để claim bằng CREATE_NEW

~~~java
Path marker = Path.of("/data/markers/orders-42.processing");
try {
    Files.createFile(marker); // Atomic create nếu filesystem provider hỗ trợ.
    // Có được marker chưa đồng nghĩa business file đã xử lý xong.
} catch (FileAlreadyExistsException alreadyClaimed) {
    // Worker khác đã tạo marker hoặc marker stale cần recovery.
}
~~~

`Files.createFile` có hành vi **kiểm tra-và-tạo nguyên tử theo API/provider**, tốt hơn `if (!Files.exists(...)) Files.createFile(...)`. Nhưng `CREATE_NEW` **không có lease/fencing/recovery tự động**, không được giả định semantics trên mọi remote FS/object storage. Nếu process chết, marker có thể còn và giữ file ở trạng thái chờ vô thời hạn.

## 8. Marker .done phải được publish như artifact hoàn chỉnh

Nếu dùng sidecar `.done` chứa status, checksum, số record và version, **đừng ghi trực tiếp vào tên .done** để downstream đọc ngay khi mới ghi một nửa.

~~~text
orders-42.done.tmp.attempt-17
   -> ghi đầy đủ JSON
   -> close/verify
   -> Files.move(temp, orders-42.done, ATOMIC_MOVE)
~~~

Mẫu JSON minh họa:

~~~json
{
  "fileId": "tenant-a/orders-42-v1",
  "sourceVersion": "sha256:4df5...91ac",
  "batchKey": "daily-orders-2026-11-26",
  "outcome": "PROCESSED",
  "processedRecords": 24997,
  "quarantinedRecords": 3,
  "verified": true
}
~~~

**Lưu ý:** `ATOMIC_MOVE` chỉ cung cấp atomic visibility trên filesystem có hỗ trợ; **khi target đã tồn tại, replace/fail có thể phụ thuộc provider** và không tự có no-clobber/CAS. Nếu hai attempts đồng thời có thể publish cùng `.done`, phải có **single owner/publisher**, target version riêng và content verification. Cũng không có transaction chung giữa file .done và database business output.

## 9. Trước khi dùng marker, quyết định nguồn sự thật

Nếu chỉ một batch script trên local filesystem và chấp nhận xử lý lại thủ công, sidecar marker có thể đủ đơn giản. Với nhiều JVM/pod, lease/restart và yêu cầu đối soát, **database manifest** thường dễ kiểm soát hơn.

| Yêu cầu | Chọn marker file | Chọn DB manifest |
| --- | --- | --- |
| Một process, local folder nhỏ | Có thể hợp lý | Có thể quá nhiều overhead |
| Nhiều process trên cùng host | Chỉ khi create/lock/recovery protocol đã test | Thường dễ quản lý hơn |
| Nhiều managers/pods | Không dùng sự tồn tại marker đơn thuần | CAS claim chung, lease/epoch |
| File trên NFS/SMB/CSI | Phải kiểm thử semantics create/rename/lock | DB claim + file identity ổn định |
| S3/Blob | Không dùng Java FileLock như POSIX | Versioned object + manifest hoặc conditional requests |
| Cần truy vấn SLA/đối soát | Phải quét và parse rất nhiều marker | Query index, audit trạng thái |
| Cần strong stale-worker protection | Marker không tự có fencing | Manifest kết hợp sink fencing |

Đừng duy trì **hai nguồn chân lý độc lập** (`.done` và database state) mà không có reconciliation protocol. Có thể dùng DB làm authoritative state, marker làm **projection** cho legacy consumer; nếu projection cập nhật chậm, hệ thống phải biết phục hồi/sửa trạng thái thay vì suy ra một tài nguyên luôn khớp tài nguyên kia.

## 10. Schema process indicator bằng PostgreSQL

Một bảng minh họa hỗ trợ file identity, ownership và vận hành:

~~~sql
CREATE TABLE file_processing (
    file_id          VARCHAR(180) PRIMARY KEY,
    batch_key        VARCHAR(120) NOT NULL,
    tenant_id        VARCHAR(120),
    source_uri       VARCHAR(600) NOT NULL,
    source_version   VARCHAR(160) NOT NULL,
    expected_records BIGINT NOT NULL CHECK (expected_records >= 0),
    state            VARCHAR(24) NOT NULL
                     CHECK (state IN (
                         'DISCOVERED','READY','PROCESSING','VERIFYING',
                         'PROCESSED','RETRYABLE','FAILED',
                         'QUARANTINED','ARCHIVED')),
    claimed_by       VARCHAR(180),
    lease_epoch      BIGINT NOT NULL DEFAULT 0,
    lease_until      TIMESTAMPTZ,
    processed_count  BIGINT,
    skip_count       BIGINT,
    output_hash      VARCHAR(128),
    last_error_code  VARCHAR(100),
    processed_at     TIMESTAMPTZ,
    archived_at      TIMESTAMPTZ,
    UNIQUE (batch_key, tenant_id, source_uri, source_version)
);

CREATE INDEX idx_file_processing_claim
    ON file_processing (state, lease_until, file_id);

CREATE INDEX idx_file_processing_batch
    ON file_processing (batch_key, state);
~~~

**Điều kiện dữ liệu:** `tenant_id` trong unique key có thể `NULL`; PostgreSQL thường coi nhiều NULL là khác nhau trong unique constraints theo mặc định. Nếu cần ngăn duplicate khi tenant thiếu, dùng một **tenant scope không-null được xác thực** hoặc unique index/`NULLS NOT DISTINCT` theo phiên bản DB và business contract, không tin mù unique constraint trên cột nullable.

Schema này là **hợp đồng ví dụ**, không do Spring Batch tự tạo. `processed_count` và `skip_count` chỉ là bằng chứng bổ sung; **không đủ** để chứng minh mọi business key đúng. Với workload lớn, tách bảng audit event để lưu từng lần claim/transition thay vì overwrite toàn bộ lịch sử ở một row.

## 11. Claim file phải là thao tác nguyên tử

**Sai về concurrency:**

~~~text
Worker A: SELECT state = READY
Worker B: SELECT state = READY
Worker A: UPDATE state = PROCESSING
Worker B: UPDATE state = PROCESSING
Hai worker cùng nghĩ mình có quyền.
~~~

Thay bằng một thao tác **compare-and-set (CAS) trên database**:

~~~sql
UPDATE file_processing
SET state = 'PROCESSING',
    claimed_by = :workerId,
    lease_epoch = lease_epoch + 1,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '120 seconds'
WHERE file_id = :fileId
  AND state IN ('READY', 'RETRYABLE')
RETURNING file_id, batch_key, source_uri,
          source_version, expected_records,
          lease_epoch, lease_until;
~~~

Hai workers cùng giành một row `READY` sẽ được PostgreSQL xử lý với locking/đánh giá điều kiện UPDATE; chỉ **một transition hợp lệ từ READY sang PROCESSING** trả kết quả cho claim ấy. Worker không nhận row từ `RETURNING` phải **không xử lý file**, chứ không được coi đó là file đã hoàn tất.

**Điều kiện vận hành:**

- Chỉ ứng dụng có quyền mới được đưa file vào `READY`/`RETRYABLE` sau khi kiểm chứng input.
- Các worker chỉ dùng claim metadata do database trả về; không tự thay `sourceUri` hoặc `sourceVersion`.
- `claimed_by` đại diện cho **attempt/owner cụ thể**, không dùng một giá trị hostname cố định cho mọi lần khởi động.
- `lease_epoch` tăng mỗi lần ownership chuyển; nó có ý nghĩa cho fencing nếu sink **thực sự kiểm tra** token.
- Không tự chọn worker thứ hai chỉ vì lần đầu thấy `PROCESSING` hơn một phút; cần một recovery decision.

## 12. Tìm work với FOR UPDATE SKIP LOCKED

Nếu có hàng nghìn file, worker không nên quét toàn thư mục rồi cùng cố claim `file-001`. Database có thể **phân phát các row READY khác nhau** cho workers:

~~~sql
WITH candidate AS (
    SELECT file_id
    FROM file_processing
    WHERE state IN ('READY', 'RETRYABLE')
    ORDER BY file_id
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE file_processing AS f
SET state = 'PROCESSING',
    claimed_by = :workerId,
    lease_epoch = f.lease_epoch + 1,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '120 seconds'
FROM candidate AS c
WHERE f.file_id = c.file_id
RETURNING f.file_id, f.source_uri, f.source_version,
          f.batch_key, f.lease_epoch;
~~~

`FOR UPDATE SKIP LOCKED` giúp concurrent workers **bỏ qua row đang bị khóa** thay vì chờ cùng một file. Đây là pattern chọn công việc kiểu queue trên PostgreSQL; nó không phải reader API mặc định của Spring Batch.

Nên thực hiện trong **transaction ngắn**: claim và commit rồi mới xử lý file. Đừng giữ DB transaction chứa `FOR UPDATE` mở hàng giờ khi đọc một CSV rất lớn; nó giữ connection/lock và làm những worker khác nghẽn.

### Lỗi có thể xảy ra sau claim

Nếu claim commit xong mà worker crash **trước khi đọc file**, manifest sẽ ở `PROCESSING` với `lease_until` cũ. Recovery coordinator phải xác minh liveness/worker ownership hoặc áp dụng **fencing protocol**, rồi mới đưa file trở lại `RETRYABLE`/cấp epoch mới. Không xóa thẳng row manifest để “cho scan lại”.

## 13. Heartbeat và lease: quyền xử lý có hạn

Một worker xử lý file 50 GiB có thể cần hàng giờ. Lease 120 giây chỉ có tác dụng nếu worker **gia hạn định kỳ**, phát hiện khi mất quyền và ngừng những write không được bảo vệ.

~~~sql
UPDATE file_processing
SET lease_until = CURRENT_TIMESTAMP + INTERVAL '120 seconds'
WHERE file_id = :fileId
  AND state = 'PROCESSING'
  AND claimed_by = :workerId
  AND lease_epoch = :epoch
  AND lease_until >= CURRENT_TIMESTAMP;
~~~

Nếu kết quả update bằng **0 row**, worker không còn chứng minh được ownership: có thể lease đã hết, state bị chuyển, hoặc epoch đã đổi. Nó phải **ngừng ghi theo protocol**; không kéo dài công việc rồi tùy tiện mark `PROCESSED`.

### Tại sao lease expiry chưa chứng minh worker cũ đã chết?

~~~text
T0: Worker A claim file-42, epoch = 7.
T1: Worker A xử lý và commit 20 chunks.
T2: A GC pause 4 phút hoặc tạm mất kết nối coordinator.
T3: Lease A hết hạn.
T4: Worker B được cấp quyền mới, epoch = 8.
T5: A phục hồi, vẫn cầm dữ liệu và DB connection.
T6: Nếu sink không có fencing, cả A lẫn B có thể ghi.
~~~

**Không chỉ dùng một heartbeat thread để bảo vệ data correctness.** Khi A bị pause/mạng lỗi, heartbeat có thể thất bại nhưng business thread vẫn ghi dữ liệu nếu không kiểm quyền; lease là một **hợp đồng giữa coordinator và worker**, muốn mạnh phải có **fencing tại resource nhận write**.

## 14. Fencing token: ngăn worker cũ sau khi đổi owner

`lease_epoch` là một **fencing token tăng đơn điệu**: epoch 8 phải thay thế epoch 7 đối với **cùng fileId**. Nhưng có token trong manifest chưa đủ. Mọi operation cần chặn stale worker phải được sink kiểm tra.

~~~mermaid
sequenceDiagram
    participant A as Worker A epoch=7
    participant M as Manifest DB
    participant B as Worker B epoch=8
    participant O as Business sink
    A->>M: claim epoch 7
    Note over A: pause / mất mạng
    B->>M: recovery claim epoch 8
    B->>O: write authorized epoch 8
    A->>O: stale write epoch 7
    O-->>A: REJECT / transaction rollback
~~~

**Một cách đơn giản khi manifest và output dùng cùng PostgreSQL database:** mọi transaction chunk cần ghi sẽ khóa row file manifest và xác minh owner/epoch **trong cùng transaction** trước khi ghi output.

~~~sql
BEGIN;

SELECT state, claimed_by, lease_epoch, lease_until
FROM file_processing
WHERE file_id = :fileId
FOR UPDATE;

-- Trong cùng transaction của ứng dụng:
-- VERIFY state='PROCESSING'
--    AND claimed_by=:workerId
--    AND lease_epoch=:epoch
--    AND lease_until >= CURRENT_TIMESTAMP
-- Nếu invalid: ROLLBACK/throw; KHÔNG ghi business data.

-- Ghi các business effects của chunk dưới cùng transaction.

COMMIT;
~~~

Một worker B muốn đổi epoch phải UPDATE cùng row và chờ transaction đang giữ row lock kết thúc. Worker A trong **transaction kế tiếp** sẽ thấy quyền mới và phải dừng. Giữ mỗi chunk ngắn; thiết kế lock ordering và timeout để tránh biến manifest row thành bottleneck dài hạn.

**Giới hạn:** nếu business sink ở DB khác, API hoặc file output, row lock PostgreSQL trên manifest **không trực tiếp chặn write ở tài nguyên đó**. Cần chính sink kiểm tra epoch hoặc dùng một publisher/coordinator được serialize, immutable result/manifest và idempotency tương ứng. Fencing không thay thế business dedup.

## 15. Đổi indicator sang PROCESSED khi nào?

Đừng chỉ dùng `reader.read() == null` hay `processor.process()` thành công để tuyên bố hoàn tất. Một điều kiện tốt cho file:

1. Worker được cấp owner đúng `fileId/sourceVersion` và owner hợp lệ khi chuyển trạng thái.
2. Reader đã xử lý nguồn **bất biến**, không bị append/replace giữa các lần checkpoint.
3. **Mọi transaction chunk đã commit** hoặc có outcome phục hồi an toàn; không còn chunk pending/unknown.
4. `StepExecution` tương ứng đạt trạng thái hoàn tất phù hợp hoặc có bằng chứng orchestration tương đương.
5. Các record bị filter/skip có policy và audit; không có lỗi hạ tầng bị skip nhầm.
6. Business output được đối soát **theo tập khóa và giá trị** — không chỉ một biến `writeCount`.
7. Không còn stale worker được phép sửa output của file sau validation.
8. Chuyển `PROCESSED` bằng CAS/transaction với owner/epoch và evidence đã xác minh.

Quy trình:

~~~mermaid
flowchart TD
    A["Worker processing chunks"] --> B{"Worker StepExecution thành công?"}
    B -- "Không" --> F["FAILED / RETRYABLE, giữ bằng chứng commit"]
    B -- "Có" --> C["VERIFYING: đối soát input/output/filter/skip"]
    C --> D{"Đủ record, đúng dữ liệu?"}
    D -- "Không" --> F
    D -- "Có" --> E["PROCESSED: CAS owner/epoch + durable evidence"]
    E --> G["Archive/publish theo protocol riêng"]
~~~

Nếu nghiệp vụ yêu cầu **chỉ công bố khi toàn batch đủ file**, `file.state=PROCESSED` mới có nghĩa file đã hoàn thành; batch còn cần **global publication barrier**.

## 16. SQL chuyển VERIFYING → PROCESSED

Chỉ verifier/coordinator đã được cấp quyền mới nên ghi status cuối:

~~~sql
UPDATE file_processing
SET state = 'PROCESSED',
    processed_count = :validatedOutputCount,
    skip_count = :approvedSkipCount,
    output_hash = :verifiedOutputHash,
    processed_at = CURRENT_TIMESTAMP,
    lease_until = NULL
WHERE file_id = :fileId
  AND state = 'VERIFYING'
  AND claimed_by = :ownerId
  AND lease_epoch = :epoch
RETURNING file_id, processed_at;
~~~

**CAS thành công là điều kiện cần, không phải điều kiện đủ.** Validation phải hoàn tất đúng và **writer không còn được phép thay đổi output** trước lúc chuyển trạng thái. Nếu validator đã check xong nhưng writer khác có thể ghi vào output giữa check và UPDATE, hệ thống có race. Cần **writer quiescence hoặc locking/publication protocol** được chứng minh.

### Tại sao không cập nhật PROCESSED trong ChunkListener.afterChunk?

`afterChunk` diễn ra sau một chunk, **không phải sau toàn file**. Một file có 2.000.000 record và chunk 200 cần hàng nghìn chunk; callback chunk đầu thành công không có nghĩa toàn file xong.

`ItemReadListener.afterRead` hay `ItemWriteListener.afterWrite` còn dễ bị dùng sai hơn vì diễn ra trong logic xử lý item/chunk, trước khi hệ thống có thể chứng minh toàn step đã hoàn thành. Chọn **step/flow cuối + validation** hoặc coordinator quản lý file completion theo metadata của Spring Batch, thay vì tùy ý sửa indicator từ bất kỳ listener nào.

## 17. Spring Batch 5.x: reader theo @StepScope và ExecutionContext

Trong partitioning theo file, manager có thể tạo một `ExecutionContext` cho mỗi file (hoặc file group). Worker step dùng reader riêng cho file được giao.

~~~java
record FileWork(String fileId, String sourceUri, String sourceVersion) {}

final class FileManifestPartitioner implements Partitioner {
    private final List<FileWork> files;

    FileManifestPartitioner(List<FileWork> immutableSnapshot) {
        this.files = List.copyOf(immutableSnapshot);
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        Map<String, ExecutionContext> parts = new LinkedHashMap<>();
        for (FileWork file : files.stream()
                .sorted(Comparator.comparing(FileWork::fileId))
                .toList()) {
            ExecutionContext ctx = new ExecutionContext();
            ctx.putString("fileId", file.fileId());
            ctx.putString("sourceUri", file.sourceUri());
            ctx.putString("sourceVersion", file.sourceVersion());
            parts.put("file-" + file.fileId(), ctx);
        }
        return parts;
    }
}
~~~

**Giới hạn của ví dụ:** một `StepExecution` cho **mỗi file**, không nhất thiết đúng bằng `gridSize` partitions. Với 50.000 file, 50.000 StepExecutions có thể tăng overhead JobRepository; cân nhắc group file theo một số partitions ổn định hoặc sử dụng manifest claim loop. File IDs phải được chuẩn hóa để partition names ổn định và không xung đột.

### Reader theo StepScope

~~~java
@Bean
@StepScope
FlatFileItemReader<OrderInput> fileReader(
        @Value("#{stepExecutionContext['fileId']}") String fileId,
        @Value("#{stepExecutionContext['sourceUri']}") String sourceUri,
        @Value("#{stepExecutionContext['sourceVersion']}") String version) {

    Path file = Path.of(URI.create(sourceUri));
    // Validate fileId/version/checksum against immutable manifest.
    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("fileReader-" + fileId)
            .resource(new FileSystemResource(file))
            .linesToSkip(1)
            .lineMapper(orderLineMapper())  // Bean ứng dụng cung cấp.
            .saveState(true)
            .build();
}

@Bean
Step importFileWorkerStep(
        JobRepository jobRepository,
        PlatformTransactionManager businessTx,
        ItemReader<OrderInput> fileReader,
        ItemProcessor<OrderInput, OrderOutput> processor,
        ItemWriter<OrderOutput> writer) {
    return new StepBuilder("importFileWorkerStep", jobRepository)
            .<OrderInput, OrderOutput>chunk(200, businessTx)
            .reader(fileReader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

Đây là **bộ khung** cần `OrderInput`/`OrderOutput`/`orderLineMapper`, datasource/JobRepository, imports, Job flow và ownership integration do ứng dụng cung cấp. `@StepScope` tạo reader per StepExecution, **không** phải distributed lock. Nếu cùng file được giao cho hai StepExecutions, step scope vẫn tạo **hai reader**; cần manifest claim/partition uniqueness.

**Reader checkpoint** trong `ExecutionContext` phản ánh vị trí đọc/trạng thái `ItemStream` khi restart theo Spring Batch contract, trong khi process indicator phản ánh **toàn file**. Chúng giải quyết hai cấp độ khác nhau; `saveState(true)` không cứu được restart nếu source content bị sửa hoặc không giữ thứ tự.

## 18. JobRepository và process indicator không phải cùng một transaction

Spring Batch quản lý `JobInstance`, `JobExecution`, `StepExecution`, counts và `ExecutionContext` qua `JobRepository`. Database chứa business output và bảng `file_processing` có thể trùng hoặc khác với metadata database.

~~~mermaid
sequenceDiagram
    participant W as Worker
    participant B as Business DB
    participant J as JobRepository
    participant M as Process indicator
    W->>M: Claim file PROCESSING
    M-->>W: Owner/epoch
    W->>B: Chunk 1 COMMIT
    W->>B: Chunk 2 COMMIT
    W->>J: Checkpoint và state theo Batch
    W->>B: Chunk cuối COMMIT
    W->>J: StepExecution COMPLETED
    W->>M: VERIFYING -> PROCESSED
~~~

Sơ đồ là **mô hình logic**. Trong một setup cụ thể, JobRepository có thể tham gia một số transaction với business writer nếu cùng resource/manager đúng cấu hình, nhưng **không được giả định** tất cả update metadata, commit của mọi chunk và process indicator là một ACID transaction toàn job.

### Phân biệt status

| Quan sát | Có thể kết luận gì? | Không được kết luận |
| --- | --- | --- |
| `JobExecution FAILED` | Luồng điều phối thất bại | Những chunks trước đó rollback toàn bộ |
| Worker `StepExecution COMPLETED` | Step xong theo framework | Mọi input/output đã đối soát nghiệp vụ |
| `file_processing.PROCESSING` | Claim đang được ghi nhận | Owner chắc chắn còn sống |
| `file_processing.PROCESSED` | Protocol ứng dụng đã đánh dấu file hoàn tất | Broker/API ngoài DB exactly-once |
| `archive/*.csv` tồn tại | Có artifact ở đích | Business processing file ấy chắc chắn đạt |

Không tự sửa bảng `BATCH_STEP_EXECUTION` thành `COMPLETED` để “khớp” với một process indicator có vẻ đúng. Cần một recovery/reconciliation step hoặc kế hoạch vận hành có hiểu trạng thái thực.

## 19. Chống trùng khi indicator chưa cập nhật sau commit

Kịch bản nguy hiểm:

~~~text
T0: file-42 PROCESSING, worker A epoch 7
T1: chunk 1..20 COMMIT vào PostgreSQL
T2: worker A crash trước cập nhật VERIFYING/PROCESSED
T3: Recovery worker B tiếp quản cùng file/version
T4: B có thể đọc lại một phần hoặc toàn bộ file
~~~

**Giải pháp không phải đơn giản “nếu PROCESSING thì bỏ qua mãi”.** Cần bảo toàn dữ liệu khi partial processing và replay:

1. **Snapshot input bất biến** với cùng fileId/version và partition mapping.
2. **Chunk checkpoint** cùng JobInstance khi khả thi, nhưng thiết kế chịu được tình huống metadata trễ so với business DB.
3. **Writer idempotent theo business operation**, không dựa `leaseEpoch` hay hostname.
4. **Fencing** để worker cũ không tiếp tục ghi sau khi B nhận ownership.
5. **Business reconciliation** trước khi mark `PROCESSED`; không chỉ đếm chunks đã chạy.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE imported_order (
    batch_key    VARCHAR(120) NOT NULL,
    order_id     BIGINT NOT NULL,
    source_file  VARCHAR(180) NOT NULL,
    source_hash  VARCHAR(128) NOT NULL,
    net_amount   NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (batch_key, order_id)
);

INSERT INTO imported_order(
    batch_key, order_id, source_file, source_hash, net_amount)
VALUES (
    :batchKey, :orderId, :fileId, :sourceHash, :netAmount)
ON CONFLICT (batch_key, order_id) DO NOTHING;
~~~

Unique key ngăn tạo **hai rows** cho một order trong batch, nhưng `DO NOTHING` có thể che giấu record mới **khác amount/source hash**. Production cần xác minh dữ liệu hiện có khớp kỳ vọng hoặc **fail/alert** nếu conflict khác nội dung. Với hiệu ứng cộng/trừ tiền, dùng ledger `operationId` và update business effect trong **cùng transaction**; một atomic increment đơn lẻ vẫn có thể áp dụng hai lần khi replay.

## 20. Khi nào nên dùng Process Indicator Pattern ở mức record?

Nếu nguồn của job là **bảng database** chứ không phải file, có thể có cột `process_indicator`/`processed` trên từng row để worker claim record, xử lý và đánh dấu hoàn tất. Nó có một số điểm tương tự:

~~~sql
CREATE TABLE staged_record (
    batch_key       VARCHAR(120) NOT NULL,
    record_id       BIGINT NOT NULL,
    processing_state VARCHAR(20) NOT NULL
                     CHECK (processing_state IN (
                         'READY','PROCESSING','PROCESSED','FAILED')),
    PRIMARY KEY (batch_key, record_id)
);
~~~

Process Indicator Pattern ở mức row có thể giảm phụ thuộc vào checkpoint vị trí đọc **nếu reader luôn query những row chưa xử lý và state được cập nhật đúng transaction/claim**. Tuy nhiên, `SELECT WHERE processed=false` rồi update thiếu locking vẫn có race; nguồn mutable và transaction boundaries vẫn quan trọng.

Với **file input**, không thể chỉ đặt một cột `PROCESSED` ở manifest mà mặc nhiên biết dòng nào đã ghi. File-level indicator cần **checkpoint hoặc per-record ledger** cho khả năng phục hồi partial work. Khi thiết kế, hãy xác định **đơn vị replay thực sự**: toàn file, chunk, range hay từng record.

## 21. Mã Java: claim file bằng NamedParameterJdbcTemplate

Ví dụ sử dụng Java 17+, Spring JDBC và PostgreSQL. Đây là một **adapter ứng dụng**, không phải API mặc định của Spring Batch:

~~~java
record ClaimedFile(
        String fileId,
        String batchKey,
        String sourceUri,
        String sourceVersion,
        long epoch) {}

final class FileClaimRepository {
    private final NamedParameterJdbcTemplate jdbc;

    FileClaimRepository(NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    Optional<ClaimedFile> claim(String fileId, String workerId) {
        String sql = """
                UPDATE file_processing
                SET state = 'PROCESSING',
                    claimed_by = :worker,
                    lease_epoch = lease_epoch + 1,
                    lease_until = CURRENT_TIMESTAMP + INTERVAL '120 seconds'
                WHERE file_id = :id
                  AND state IN ('READY','RETRYABLE')
                RETURNING file_id, batch_key, source_uri,
                          source_version, lease_epoch
                """;

        MapSqlParameterSource params = new MapSqlParameterSource()
                .addValue("id", fileId)
                .addValue("worker", workerId);

        List<ClaimedFile> candidates = jdbc.query(
                sql, params, (rs, index) -> new ClaimedFile(
                        rs.getString("file_id"),
                        rs.getString("batch_key"),
                        rs.getString("source_uri"),
                        rs.getString("source_version"),
                        rs.getLong("lease_epoch")));

        return candidates.stream().findFirst();
    }
}
~~~

**Lưu ý:**

- `Optional.empty()` là **claim không thành công**, không chứng minh file đã PROCESSED.
- `workerId` phải định danh attempt/caller, không sử dụng tùy tiện một ID trùng nhau trên các instance đang chạy.
- API dùng parameterized SQL, tránh nối chuỗi `fileId` vào câu lệnh.
- Transaction claim nên **ngắn**; chỉ sau khi commit claim mới bắt đầu xử lý dài.
- Claim được cấp quyền không thay thế **source checksum/version validation**.

Trong môi trường có scheduler và lease, mã còn cần heartbeat, transition CAS, failure handling, metrics và cấu hình quyền DB. Đừng dùng adapter ví dụ này một mình rồi tuyên bố đã có đầy đủ failover.

## 22. Xử lý quá trình nhiều bước: reader EOF ≠ PROCESSING xong

Với một file 10 triệu records, reader có thể đã đọc tới EOF nhưng một vài chunks vẫn đang chờ ghi DB hoặc thực hiện side effect. Quy trình an toàn:

~~~text
Worker CLAIM PROCESSING
  - mở đúng immutable file version
  - đọc + process + write theo chunks
  - mọi chunk có outcome commit rõ hoặc được recovery
  - Spring Batch worker step hoàn tất theo contract
  - xác minh input/output/skip/filter

Coordinator/Verifier:
  PROCESSING -> VERIFYING
  VERIFYING -> PROCESSED (CAS owner/epoch)
~~~

Không dùng file size, offset cuối, reader `read()==null` hoặc `StepContribution.writeCount` riêng lẻ để đánh dấu PROCESSED. Một file có nhiều record filtered/skipped hợp lệ và số `writeCount` không bằng expected input count; ngược lại một số count đúng vẫn có thể giấu lỗi dữ liệu **trùng và thiếu business key bù trừ**.

### Khi StepExecution thành công nhưng file status chưa đổi

Một worker có thể hoàn thành step và commit metadata nhưng mất mạng với manifest DB trước khi update `PROCESSED`. Recovery coordinator nên nhận biết **outcome được xác minh**, rồi **hoàn tất status transition** nếu owner/epoch và source version vẫn hợp lệ; không bắt buộc chạy lại reader nếu không cần.

## 23. Producer handoff và input bất biến

Process indicator `READY` phải có ý nghĩa hơn “nhìn thấy path”.

~~~text
Producer ghi: incoming/file-42.csv.part
  -> flush/close, kiểm chứng định dạng/size/checksum
  -> chuyển sang immutable ready file/version hoặc publish manifest
  -> cập nhật file_processing READY

Worker chỉ claim từ READY
  -> đọc đúng fileId/sourceVersion
~~~

Nếu producer append thêm dữ liệu sau `READY`, checkpoint của `FlatFileItemReader` có thể mất ý nghĩa, và hai worker đọc ở thời điểm khác nhau có thể thấy tập record khác nhau.

**Đừng dùng “file không đổi size trong 2 giây” để chứng minh producer đã xong.** Producer có thể tạm ngừng I/O hoặc ghi từng đợt. Tốt hơn là **ready marker/immutable snapshot/versioned object** do producer công bố theo hợp đồng.

### Quy tắc trên object storage

Với S3/Blob/GCS, một object key có thể trỏ tới nhiều versions nếu được overwrite. File indicator phải giữ **version/generation ID** đúng. “File tồn tại” không đủ để khẳng định reader đang mở cùng bytes mà producer đã verify. Object metadata/tag update không tự là transaction của business DB hay Spring Batch JobRepository.

## 24. Indicator và atomic move/archive là hai bước khác nhau

Một pipeline có thể dùng state:

~~~text
READY
  -> PROCESSING
  -> VERIFYING
  -> PROCESSED
  -> ARCHIVED
~~~

**PROCESSED**: nội dung file đã được xử lý và đối soát theo policy. **ARCHIVED**: source artifact đã chuyển/lưu đến vị trí archive theo retention contract. Nếu move thất bại, file vẫn có thể **PROCESSED nhưng chưa ARCHIVED**; không được vì lỗi archive mà import lại một cách mù quáng.

~~~mermaid
sequenceDiagram
    participant W as Worker Step
    participant B as Business DB
    participant M as Manifest DB
    participant F as File System
    W->>B: Chunks COMMIT
    W->>M: VERIFYING
    W->>B: Reconcile output
    W->>M: PROCESSED
    W->>F: Atomic move ready -> archive (nếu hỗ trợ)
    W->>M: ARCHIVED
    Note over W,M: Crash có thể xảy ra giữa mọi thao tác
~~~

Lưu ý: sơ đồ là **trình tự logic** và chưa mô tả một transaction chung giữa DB và FS. Nếu worker chết sau move nhưng trước cập nhật ARCHIVED, recovery phải nhận ra **source mất, target tồn tại, checksum/version khớp**, rồi hoàn tất status; không tự import lại.

**Đừng phát hành marker .done chỉ vì đã move file vào archive.** Move có thể xảy ra nhầm/từ process khác, trong khi output chưa đạt. Downstream phải dựa vào source of truth có evidence verified.

## 25. Indicator khi nhiều file cần được công bố theo một batch

Trong một batch có 4 files, có thể xảy ra:

~~~text
file-A PROCESSED
file-B PROCESSED
file-C PROCESSED
file-D FAILED

=> Cả batch CHƯA HOÀN THÀNH theo hợp đồng all-or-nothing.
~~~

File indicator cấp file hữu ích cho recovery **từng file**, nhưng downstream muốn toàn batch nhất quán cần **global quality/publication gate**:

- Số file trong manifest đúng **snapshot kỳ vọng**; không chỉ đếm `state='PROCESSED'`.
- Mọi file expected có final state phù hợp và không còn worker hoạt động ghi vào output.
- Source records của từng file được đối soát với business output, filtered/quarantined được phép.
- Không còn lỗi consistency/security nghiêm trọng chưa giải quyết.
- Business totals, references và rule version đúng toàn batch.
- Chỉ khi đủ, batch manifest/pointer mới được chuyển sang `PUBLISHED` theo cơ chế CAS/transaction kiểm soát.

Một **per-file .done marker** không tự tạo atomic visibility cho toàn bộ batch. Nếu downstream quét những file .done và kết hợp báo cáo ngay, có thể đọc một tập chưa đủ; nên query **batch publication state** hoặc một immutable manifest version đã công bố.

## 26. Kiểm soát skip/retry và dead-letter theo file

Trong Spring Batch, một file có thể chứa record lỗi và step vẫn `COMPLETED` khi lỗi được **skip theo chính sách**. Vì vậy `file.state=PROCESSED` không nên đồng nghĩa **100% input đều tạo output** nếu business policy cho phép quarantine.

Ví dụ:

~~~text
Expected logical records = 25,000
Valid processed records  = 24,990
Approved filtered        = 5
Approved quarantined     = 5
Total coverage           = 25,000

Nếu business cho phép 5 quarantined -> file có thể PROCESSED
theo policy; nhưng batch vẫn có thể bị quality gate chặn.
~~~

Nếu policy cấm skip hoặc số skip vượt budget, state phải `FAILED`/`QUARANTINED` theo kết quả xác minh. `skipLimit` của Spring Batch là **per StepExecution**; nếu một file trải trên nhiều worker steps, cần tổng hợp đúng, không đọc riêng một counter rồi suy ra budget toàn file.

**Không phân loại DB timeout thành bad record chỉ để file sớm chuyển PROCESSED.** Lỗi hạ tầng thuộc retry/fail, còn data quality skip phải có reason code và durable quarantine record.

## 27. File status không đủ cho recovery từng chunk

Giả sử file có 40.000 records, chunk size 200; worker đã commit 120 chunks rồi chết.

~~~text
File indicator: PROCESSING
JobRepository: checkpoint có thể ở chunk 120 hoặc trễ hơn
Business DB: dữ liệu của một số chunks đã commit
~~~

Nếu restart chỉ đọc từ đầu mà writer cộng dồn, kết quả sai. Nếu bỏ qua file vì đã có `PROCESSED` giả, dữ liệu thiếu. Phải kết hợp:

1. Reader state trong `ExecutionContext` và source snapshot bất biến.
2. Business unique key/idempotent operation ledger.
3. StepExecution/JobExecution metadata theo đúng JobInstance.
4. File indicator như **đơn vị scheduling**, không dùng thay checkpoint.
5. Per-file reconciliation trước final status.

Khi lựa chọn checkpoint là offset của CSV, lưu ý record separator, encoding và thứ tự đầu vào; nếu file bị viết lại, cùng offset có thể chỉ sang record khác. Nếu thiếu source snapshot, **fail/quarantine** tốt hơn tự cố tiếp tục.

## 28. Remote partitioning và remote chunking đặt indicator ở đâu?

| Nội dung | Remote partitioning | Remote chunking |
| --- | --- | --- |
| ItemReader chính | Thường ở worker | Thường ở manager |
| File identity | Trong worker `ExecutionContext`/manifest | Trong reader/manager source manifest |
| Chỗ cập nhật file indicator | Worker/coordinator theo completion toàn file | Manager/coordinator sau khi đủ chunk outcomes |
| Rủi ro khi mất reply | Worker đã commit nhưng manager chưa nhận status | Worker chunk đã commit nhưng reply mất |
| Điều không được làm | Dispatch lại cùng partition khi owner cũ có thể còn ghi | Mark file PROCESSED khi mới gửi hết chunks |

**Remote partitioning:** worker StepExecution nhận một hoặc nhiều file, xử lý và commit theo chunk. Một broker timeout không chứng minh worker chết; coordinator không được tự cấp owner mới nếu không có quiescence/fencing. File indicator trong DB chung cho phép các JVM nhìn cùng trạng thái, nhưng **không tự tạo distributed lock** nếu UPDATE claim sai.

**Remote chunking:** manager thường đọc file và gửi `ChunkRequest` tới workers. Khi manager đã đọc tới EOF, vẫn có thể còn chunk in-flight chưa nhận `ChunkResponse`. File indicator chỉ nên PROCESSED sau khi **tất cả chunk của file có outcome hợp lệ**, các business effects đã đối soát và metadata phù hợp. Worker chỉ nhận một chunk không nên tự đổi trạng thái toàn file.

## 29. Hai manager chạy cùng lúc: process indicator phải là global

Giả sử scheduler vô tình chạy **JobExecution 845** và **JobExecution 846** cùng batch, cả hai đều quét cùng `/ready`. Nếu mỗi manager tạo một `HashMap<fileId,status>` riêng hoặc chỉ kiểm `StepExecution` của job mình, hai manager vẫn có thể tạo partitions chứa cùng file.

**Cần:**

- Một **catalog chung** của logical file identities (manifest DB hoặc coordination store).
- Claim nguyên tử ở cấp file, **không phụ thuộc JobExecution ID** làm key duy nhất khi cả hai jobs cùng nguồn.
- Stable `batchKey`, tenant scope, immutable `sourceVersion`.
- Một policy xử lý duplicate launches: fail, chờ hoặc skip **với bằng chứng đã processed**, không đánh dấu success giả.
- Worker ownership/lease/fencing khi recovery; mỗi process sử dụng identity khác nhau cho claim attempts.
- Business writer idempotent để bảo vệ khi job bị phát lại hợp lệ.

**Nhắc lại:** `synchronized`, `ConcurrentHashMap`, `@StepScope` hoặc local `FileLock` không tự bảo vệ các JVM ở những host khác nhau; cần coordination đã được kiểm thử trên topology thực tế.

## 30. Trường hợp marker file bị stale hoặc mâu thuẫn

Khi dùng sidecar, có thể thấy:

~~~text
orders-42.csv.ready      EXISTS
orders-42.csv.processing EXISTS
orders-42.csv.done       MISSING
~~~

Không kết luận ngay rằng worker đang chạy. Cần **worker heartbeat/status**, **JobRepository**, **manifest owner**, **business DB** và source version.

| Dấu hiệu | Các khả năng | Hành động an toàn |
| --- | --- | --- |
| `.processing` còn lâu | Worker chết, pause hoặc lock sidecar stale | Kiểm liveness/ownership; không xóa theo tuổi mù quáng |
| `.done` có, manifest PROCESSING | Marker công bố xong trước DB update hoặc ghi nhầm | Verify marker content + DB output, CAS reconciliation |
| Manifest PROCESSED, `.done` không có | Projection marker chưa gửi, lỗi filesystem | Regenerate marker **idempotent** sau verification |
| `.done` có nhưng checksum sai | File khác version/corruption | Quarantine/alert, không mark success |
| `.failed` có và `.done` có | Attempts khác hoặc marker cleanup sai | So fileId/version/epoch và audit history |
| File source biến mất | Đã archive, move lỗi hoặc bị xóa | Kiểm archive/backup, không tự tạo input trống |

Nếu marker là projection của DB, **nguồn chân lý được xác định từ trước** phải thắng khi có lệch; việc cập nhật lại projection cần cẩn trọng để không ghi đè marker version mới.

## 31. Đối soát record theo file trước PROCESSED

Định nghĩa tập input snapshot cố định và tập output chứa business key/source identity. Ví dụ:

~~~sql
CREATE TABLE file_source_record (
    batch_key      VARCHAR(120) NOT NULL,
    file_id        VARCHAR(180) NOT NULL,
    record_id      BIGINT NOT NULL,
    PRIMARY KEY (batch_key, file_id, record_id)
);

-- Ví dụ này giả định imported_order có batch_key, order_id
-- và source_file như phần idempotent writer.
~~~

Kiểm tra **input chưa có output**:

~~~sql
SELECT s.record_id
FROM file_source_record AS s
LEFT JOIN imported_order AS o
  ON o.batch_key = s.batch_key
 AND o.source_file = s.file_id
 AND o.order_id = s.record_id
WHERE s.batch_key = :batchKey
  AND s.file_id = :fileId
  AND o.order_id IS NULL;
~~~

Kiểm tra **output không thuộc file input snapshot**:

~~~sql
SELECT o.order_id
FROM imported_order AS o
LEFT JOIN file_source_record AS s
  ON s.batch_key = o.batch_key
 AND s.file_id = o.source_file
 AND s.record_id = o.order_id
WHERE o.batch_key = :batchKey
  AND o.source_file = :fileId
  AND s.record_id IS NULL;
~~~

**Giới hạn minh họa:** giả định `record_id` trong file tương ứng với `order_id` đầu ra và mỗi input sinh đúng một output; schema thực có thể khác. Nếu nghiệp vụ cho phép **filter/quarantine**, đối soát phải tính đầy đủ những tập được phép ấy, và bảo đảm mỗi input thuộc **đúng một trạng thái cuối hợp lệ**. Khi một record sinh nhiều outputs, khóa và phép kiểm cũng phải thể hiện cardinality đó.

### Không chỉ kiểm COUNT(*)

Input có 25.000 keys và output cũng 25.000 rows không bảo đảm tập khóa bằng nhau. Có thể một source record bị mất còn record khác bị ghi vào file/tenant sai; số lượng vẫn khớp. Do đó kết hợp **set difference, source version hash, value/checksum, business totals và ownership**.

**Quarantine record-level** cũng phải bền vững và có reason code. Không coi tất cả `skipCount` là đã giải trình khi store dead-letter gặp lỗi hoặc khi listener không tham gia đúng transaction chunk.

## 32. Lưu lịch sử transition để phục hồi có bằng chứng

Chỉ lưu state mới nhất khiến incident khó giải thích: một file có thể đã bị claim 3 lần, worker đầu chết sau 800 chunks, worker thứ hai gặp source mismatch, worker thứ ba hoàn tất. Một bảng event/audit giúp xem **ai đã đổi trạng thái và vì sao**.

~~~sql
CREATE TABLE file_processing_event (
    event_id       VARCHAR(160) PRIMARY KEY,
    file_id        VARCHAR(180) NOT NULL,
    batch_key      VARCHAR(120) NOT NULL,
    owner_id       VARCHAR(180),
    lease_epoch    BIGINT,
    from_state     VARCHAR(24),
    to_state       VARCHAR(24) NOT NULL,
    reason_code    VARCHAR(100),
    observed_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_file_event_timeline
    ON file_processing_event(file_id, observed_at);
~~~

Nên ghi **state change và audit event trong cùng DB transaction**. Nếu ghi audit lên broker khác resource, dùng outbox hoặc reconciliation; không đánh mất sự kiện cấp quyền hoặc completion trong những lúc network fail. `event_id` có thể là UUID của transition nếu mỗi transition thực sự chỉ commit một lần, nhưng audit dedup/retry vẫn cần một policy rõ nếu request update outcome không chắc chắn.

**Audit không thay thế authoritative state.** Một consumer đọc event stream có thể trễ; worker muốn claim file vẫn phải dùng phép CAS trên nguồn trạng thái được chọn.

## 33. Unit/integration test claim đúng dưới concurrency

Một test concurrency có giá trị cần hai worker bắt đầu gần đồng thời, nhưng assertion dựa trên **DB claim atomic**, không dựa `Thread.sleep`:

~~~java
@Test
void onlyOneWorkerCanClaimReadyFile() throws Exception {
    // Arrange: file_processing(file_id='f42', state='READY')
    // với DB thật/Testcontainers PostgreSQL.
    CountDownLatch start = new CountDownLatch(1);
    ExecutorService executor = Executors.newFixedThreadPool(2);

    Callable<Boolean> a = () -> {
        start.await();
        return fileClaimRepository.claim("f42", "worker-A")
                .isPresent();
    };
    Callable<Boolean> b = () -> {
        start.await();
        return fileClaimRepository.claim("f42", "worker-B")
                .isPresent();
    };

    try {
        Future<Boolean> fa = executor.submit(a);
        Future<Boolean> fb = executor.submit(b);
        start.countDown();

        int winners = (fa.get(15, TimeUnit.SECONDS) ? 1 : 0)
                    + (fb.get(15, TimeUnit.SECONDS) ? 1 : 0);
        assertEquals(1, winners);
    } finally {
        start.countDown();
        executor.shutdownNow();
    }
}
~~~

Đây là ví dụ JUnit 5/Java 17, cần `fileClaimRepository` và fixture DB được cung cấp bởi test. Nên xác nhận thêm **state=PROCESSING, epoch tăng đúng một lần, claimed_by thuộc winner**, không có business write từ loser. PostgreSQL Testcontainers giúp kiểm tra row locking và `UPDATE RETURNING` sát thực hơn H2 nếu production dùng PostgreSQL.

### Test marker CREATE_NEW không đủ cho restart

Test hai processes cùng `Files.createFile(processingMarker)` có thể cho một winner, nhưng khi kill winner sau khi tạo marker thì marker vẫn còn. Từ đó chứng minh **marker tồn tại không bằng worker còn sống** và cần recovery. Thử nghiệm trên local filesystem không thay kiểm thử trên NFS/SMB/CSI nếu production dùng các loại storage ấy.

## 34. Failure injection: khoảng hở commit và indicator

| Kịch bản | Điểm gây lỗi | Kết quả phải xác minh |
| --- | --- | --- |
| A. Crash trước claim | Worker chưa đổi READY | File vẫn claim được |
| B. Crash sau claim, trước read | Manifest PROCESSING, chưa output | Recovery lease/owner an toàn |
| C. Crash giữa chunks | Đã commit một số chunks | Restart/replay không duplicate business effect |
| D. DB business commit, indicator update fail | Output đủ, manifest PROCESSING/VERIFYING | Reconcile rồi transition, không import lại mù quáng |
| E. Indicator PROCESSED quá sớm | Vẫn còn chunk pending | Test phải phát hiện, chặn publication |
| F. Source file thay nội dung | Checksum/version khác | Fail/quarantine, không resume checkpoint cũ |
| G. Hai workers tranh claim | Concurrent SQL | Một owner, loser không ghi |
| H. Lease expired khi owner A pause | B claim epoch mới | Stale A không được commit sau khi phục hồi |
| I. Broker reply mất | Worker đã commit nhưng manager không biết | Correlation/restart và business dedup |
| J. Marker .done publish rồi DB update fail | .done tồn tại, DB state cũ | Đối soát và sửa projection/manifest |
| K. Marker viết dở | Kill trước atomic rename | Downstream không thấy .done hoàn chỉnh giả |
| L. Archive move xong, manifest chưa ARCHIVED | Source missing/target exists | Verify target rồi CAS, không import lại |
| M. Quarantine DB lỗi | Skip được định nhưng không lưu bằng chứng | Step fail/rollback theo hợp đồng, không fake PROCESSED |
| N. Global quality gate không đạt | File steps đã COMPLETED | Batch vẫn không PUBLISHED |

Các điểm dừng test nên được tạo bằng **hook sau transaction commit thực**, `CountDownLatch` (khi cùng JVM) hoặc handshake giữa processes; một callback `writer.write()` trả về **chưa** chứng minh commit thành công.

### Probe trước khi cập nhật PROCESSED

~~~java
final class CompletionProbe {
    final CountDownLatch businessCommitConfirmed =
            new CountDownLatch(1);
    final CountDownLatch allowIndicatorUpdate =
            new CountDownLatch(1);

    void afterVerifiedCommitBeforeIndicator()
            throws InterruptedException {
        businessCommitConfirmed.countDown();
        if (!allowIndicatorUpdate.await(15, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Test timed out");
        }
    }
}
~~~

Test runner đợi `businessCommitConfirmed`, kiểm tra DB output ở một transaction khác, rồi kill worker hoặc làm manifest update fail. Sau restart, assertion phải kiểm tra **đúng tập business keys** và indicator cuối cùng, không chỉ `BatchStatus.COMPLETED`. Phải release latch trong `finally` khi test không crash process thật.

## 35. Kiểm thử hai JVM/manager thật

Với workload phân tán, test hai thread trong một JVM không đủ chứng minh tác dụng của manifest/global indicator. Một integration test nên:

1. Chuẩn bị immutable file version, PostgreSQL manifest/JobRepository/business DB và broker nếu kiến trúc cần.
2. Khởi động **hai JVM workers/managers** với cùng `batchKey` và `fileId` trên shared storage.
3. Bắt đầu cùng lúc bằng barrier ngoài process hoặc test coordinator.
4. Assert **một claim thắng**, worker còn lại không đụng business writer.
5. Worker A commit nhiều chunks; kill A trước process indicator final update.
6. Khôi phục JobInstance/ownership theo protocol; verify idempotent records và status cuối.
7. Tạo scenario A mất kết nối chỉ trong thời gian lease expiry, B nhận epoch cao hơn; A phục hồi và **sink từ chối write epoch cũ**.
8. Khi có remote messaging, inject reply duplicate/late hoặc broker redelivery; status file không bị cập nhật hai lần/đánh dấu file khác.
9. Kiểm tra marker .done projection và archive path nếu những cơ chế này được dùng.

**Một test dùng `DirectChannel` trong cùng JVM không mô phỏng được ACK/durability/redelivery của broker thật**. Nếu production dùng RabbitMQ/Kafka/JMS hoặc NFS, phải có test tương ứng loại transport/storage, không suy diễn từ mock.

### Điều kiện pass quan trọng hơn số lần retry

Không cần giả định message sẽ redeliver đúng **một lần** trên mọi broker. Điều bắt buộc là **dù replay bao nhiêu lần trong policy**, hiệu ứng nghiệp vụ cuối cùng và process indicator vẫn nhất quán. Test tốt cố tình tạo duplicate requests và outcome commit chưa rõ.

## 36. Performance: số file lớn và overhead manifest

Với 50.000 file, tạo một StepExecution cho từng file, một row manifest, nhiều audit events và heartbeat định kỳ có chi phí đáng kể. Một số dấu hiệu:

- JobRepository quá nhiều StepExecutions và ExecutionContext updates.
- Manifest DB CPU tăng do hàng nghìn workers liên tục poll cùng `READY` rows.
- `FOR UPDATE SKIP LOCKED` giúp phân phối nhưng query/index/transaction vẫn có overhead.
- Lease heartbeat quá dày làm tăng write IOPS và lock contention.
- File size skew khiến nhiều workers rảnh dù một file khổng lồ vẫn chạy.
- Marker file sidecar làm tăng directory entries và metadata I/O trên NFS.
- Full checksum của hàng nghìn file lớn tiêu thụ I/O; phiên bản/chứng cứ từ producer phải được tin cậy theo đúng SLA.

| Cách tổ chức | Khi phù hợp | Tradeoff |
| --- | --- | --- |
| Một StepExecution / file | Hàng trăm, vài nghìn file vừa phải | Restart rõ, metadata nhiều |
| Một partition / file group | Rất nhiều file nhỏ | Ít StepExecution hơn, per-file checkpoint/indicator phức tạp hơn |
| Dynamic manifest claim loop | File đến liên tục, workers lấy work linh hoạt | Cần ownership/lease/recovery rõ |
| Pre-shard file lớn | Vài file rất lớn | Cần record-boundary index, source snapshot |
| Remote partitioning | Worker tự đọc file/region | Coordinator/network/JobRepository complexity |
| Remote chunking | Manager đọc file, worker xử lý/ghi | Chunk request/reply, broker, replay semantics |

**Đo đúng chỉ số:** không chỉ `records/second` mà là **thời gian từ READY đến PROCESSED/PUBLISHED**, số files stuck, DB commit latency, indicator contention, retry overhead và thời gian khôi phục sau worker crash.

## 37. Monitoring và alerting

| Metric | Câu hỏi vận hành | Dấu hiệu cảnh báo |
| --- | --- | --- |
| `files_ready_total` | Backlog file đủ điều kiện xử lý? | Tăng liên tục so với ingestion SLA |
| `files_processing_total` | Bao nhiêu file đã có owner? | Vượt concurrency budget, treo lâu |
| `files_processing_oldest_age` | File lâu nhất ở PROCESSING bao lâu? | Quá ngưỡng tương ứng file size |
| `lease_renew_failure_total` | Worker có đang mất ownership? | Spike khi DB/network sự cố |
| `file_claim_conflict_total` | Có quá nhiều workers tranh một file? | Tăng do polling/manager trùng |
| `files_verifying_total` | Bao nhiêu file chờ quality check? | Tích tụ do validation bottleneck |
| `files_processed_total` | Bao nhiêu logical files đã được xác minh? | Lệch khỏi expected manifest |
| `files_failed_total` | File nào thất bại theo reason? | Lỗi đồng loạt hoặc source-specific |
| `stale_owner_write_rejected_total` | Fencing đang chặn epoch cũ? | Bất kỳ spike nào cần điều tra |
| `indicator_cas_failure_total` | Status update bị từ chối do owner/state không còn phù hợp? | Race/retry storm |
| `source_version_mismatch_total` | Input bị thay sau handoff? | Bất kỳ mismatch trái hợp đồng |
| `reconciliation_mismatch_total` | Input/output có thiếu/trùng/sai? | Chặn PROCESSED/PUBLISHED |
| `archive_pending_total` | File đã PROCESSED nhưng chưa ARCHIVED? | Vượt archive SLA |
| `job_restart_recovery_lag` | Crash bao lâu thì workload hội tụ? | Vượt recovery objective |

**Cardinality:** không dùng `fileId`, source path hoặc ID hàng triệu input files làm metric tags. Chúng phù hợp với log/tracing/manifests có quyền truy cập, còn metric tổng hợp theo batch, source class, tenant group, worker pool, state và reason code được kiểm soát.

### Log/trace nên tách các mốc

~~~text
FILE_READY       fileId=f042 sourceVersion=v3
CLAIM_GRANTED    fileId=f042 owner=worker-A epoch=7
CHUNK_COMMITTED  fileId=f042 committedRecords=200
VERIFY_STARTED   fileId=f042 epoch=7
VERIFY_OK        fileId=f042 coverage=100% valueMatch=true
FILE_PROCESSED   fileId=f042 epoch=7
ARCHIVE_OK       fileId=f042 archiveVersion=av1
~~~

**Không log `FILE_PROCESSED` chỉ vì đã gọi SQL nhưng transaction chưa commit**, cũng không tăng `CHUNK_COMMITTED` lúc processor trả về khi transaction còn mở.

## 38. Security, tenant isolation và retention

Process indicator là dữ liệu điều phối có quyền lực: ai được chuyển `PROCESSED` hoặc đổi source URI có thể làm job **bỏ qua dữ liệu chưa xử lý** hoặc đưa dữ liệu tenant này sang tenant khác.

**Yêu cầu bảo vệ:**

1. Validate `fileId`, `batchKey`, `tenantId` và nguồn từ manifest; không nhận absolute path do bên ngoài nhập trực tiếp.
2. DB role cho worker chỉ nên có quyền **claim/renew/transition được giới hạn**; quyền operator sửa `FAILED → READY` phải audit.
3. Source URI phải nằm trong **root/namespace đã phê duyệt**. Chống `..`, symlink và TOCTOU khi path không tin cậy.
4. Marker file nên ở directory quyền chặt, tránh world-writable `.processing`/`.done` có thể bị process lạ giả mạo.
5. Không lưu token, signed URL, mật khẩu, raw PII hoặc full exception message có secret trong indicator/marker/log.
6. Tách namespace tenant trong logical file ID; file cùng tên ở hai tenant không được chia chung status.
7. File DONE/PUBLISHED có retention, backup và quy trình correction; không cho worker tự xóa/ghi đè immutable artifact đã công bố.
8. Audit mọi thay đổi state do người vận hành, nhất là `PROCESSED`, `ARCHIVED` và `QUARANTINED`.
9. Với object storage, dùng version/generation và quyền bucket/container phù hợp; không coi tag write là authorization hoặc fencing.

**Indicator status không phải cơ chế xác thực quyền truy cập.** Một worker có claim hợp lệ chưa đủ để được đọc dữ liệu tenant bất kỳ; authorization là lớp độc lập phải kiểm soát.

## 39. Runbook khi file kẹt PROCESSING

Một tình huống thường gặp: dashboard báo file `f042` PROCESSING hơn hai giờ, worker cũ không gửi heartbeat, nhưng DB đã có 70% kết quả.

1. **Khoanh vùng:** `fileId`, `batchKey`, tenant, `sourceVersion`, JobInstance/JobExecution, worker StepExecution, owner/epoch.
2. **Kiểm tra input:** producer đã bàn giao immutable file chưa, checksum/size có đúng, source vẫn đọc được không?
3. **Xác minh liveness:** worker cũ đang chạy hay chỉ mất network/GC pause? Có instance khác cùng xử lý file không?
4. **Xác minh ownership:** `state`, `claimed_by`, `lease_epoch`, `lease_until`; có recovery attempt nào đã nhận epoch mới?
5. **Kiểm tra DB output và JobRepository:** chunk nào đã commit, checkpoint nào bền vững, StepExecution có COMPLETED/FAILED/STARTED/UNKNOWN?
6. **Xem marker sidecar nếu dùng:** `.processing` tồn tại không có nghĩa worker còn giữ OS lock; `.done` có cũng chưa đủ nếu checksum/DB chưa khớp.
7. **Đối soát record coverage:** source keys vs output/filter/quarantine, business totals, rule/snapshot version.
8. **Phân loại tình huống:** cần tiếp tục checkpoint, reprocess idempotent, reconcile và mark PROCESSED, hay quarantine vì source mismatch?
9. **Chống stale owner:** không cấp quyền cho worker mới khi worker cũ vẫn có thể ghi nếu chưa có fencing/quiescence protocol.
10. **Thực hiện recovery:** thông qua coordinator/state transition CAS có audit; giữ nguyên snapshot/identifying JobParameters của JobInstance khi restart.
11. **Xác nhận kết quả:** một owner hợp lệ, dữ liệu đúng, StepExecution/indicator final state phù hợp; nếu cần mới archive/publish.
12. **Đóng incident:** ghi root cause, recovery latency, số replay, duplicate conflicts, lỗ hổng lock/lease và test cần bổ sung.

### Tình huống A — đã commit đủ, chỉ indicator trễ

~~~text
manifest state = VERIFYING
worker StepExecution = COMPLETED
source version = match
business output = all expected keys and values
no active stale writer

=> Recovery coordinator có thể transition tới PROCESSED
   bằng CAS hợp lệ; không chạy lại file chỉ để đổi cờ.
~~~

### Tình huống B — output một phần, owner đã chết

~~~text
manifest state = PROCESSING
worker StepExecution = FAILED / UNKNOWN
output = partial committed chunks
source version = match
old worker confirmed stopped or sink fencing active

=> Recovery theo JobRepository/checkpoint và idempotent writer.
   Chỉ PROCESSED sau khi mọi record đạt policy và đối soát.
~~~

**Không xóa marker stale theo tuổi, không reset tất cả file PROCESSING thành READY, không sửa trực tiếp JobRepository thành COMPLETED, và không DELETE toàn bộ business output** khi chưa xác định side effects nào đã commit. Những thao tác đó có thể tạo duplicate hoặc làm mất bằng chứng khôi phục.

## 40. Các lỗi thiết kế phổ biến

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| File bị xử lý hai lần | Hai workers kiểm `state=READY` rồi cùng UPDATE | Atomic CAS claim/`RETURNING`, owner epoch |
| File kẹt PROCESSING mãi | Marker `.processing` không có recovery | Lease/liveness/recovery coordinator |
| Worker cũ vẫn ghi sau timeout | Lease hết nhưng sink không fencing | Sink-level epoch enforcement/quiescence |
| PROCESSED nhưng thiếu record | Đổi cờ khi reader EOF hoặc chỉ nhìn count | Step completion + coverage/value validation |
| DB đủ nhưng state PROCESSING | Crash sau commit trước indicator update | Reconcile, transition idempotent |
| Job FAILED, output còn | Tưởng JobExecution là transaction toàn file | Chấp nhận chunk commits, idempotent replay |
| File mới bị bỏ qua | Chỉ dùng filename làm key | FileId + immutable version + batch/tenant |
| Marker DONE có nội dung nửa chừng | Ghi trực tiếp `.done` | Temp + atomic publish/manifest |
| Hai manager cùng lấy một file | Indicator chỉ có trong HashMap/JVM | Global manifest/coordination store |
| Restart đọc sai record | Source CSV bị sửa hoặc partition map đổi | Immutable snapshot, stable ExecutionContext |
| Writer tăng tiền hai lần | Replay không có operation ledger | Business idempotency + unique constraint |
| Skip count thấp nhưng nhiều file lỗi | Chỉ kiểm một StepExecution | Per-file và global quality gate |
| Processed file chưa archive nhưng bị import lại | Quét theo thư mục thay vì authoritative state | PROCESSED → ARCHIVED riêng, recovery |
| Broker message DLQ nhưng file PROCESSED | Mark sau dispatch/ACK thay vì outcome | Correlation/reply, per-file completion barrier |
| File của tenant khác được mark done | Identity/authorization không chứa tenant scope | Validated owner and namespaced keys |
| Indicator DB và sidecar lệch mãi | Hai nguồn chân lý không có reconcile | Authoritative state + projection repair |

## 41. Bài thực hành tổng hợp

Xây một pipeline nhập **100 file CSV bất biến** (tổng khoảng 1 triệu records), chia công việc cho **bốn worker**. Mỗi logical file có `fileId`, `batchKey`, `sourceVersion`, expected record count và indicator row trong PostgreSQL. Output được ghi theo unique business key, và downstream chỉ đọc batch đã PUBLISHED.

**Bài A — State và claim**

1. Producer publish file bất biến và tạo indicator `READY`.
2. Hai workers cố claim cùng file bằng một câu `UPDATE ... RETURNING`; assert một owner được cấp quyền.
3. Worker mất heartbeat; recovery coordinator xác minh và chuyển ownership theo protocol.
4. Tạo stale worker epoch cũ; xác minh business sink từ chối write sau khi owner mới được cấp.

**Bài B — Spring Batch và completion**

5. Giao mỗi worker `fileId/sourceUri/sourceVersion` qua `ExecutionContext`; reader `@StepScope` đọc đúng file.
6. Dùng chunk size 200; ghi output idempotent. Kill worker sau khi một số chunks đã commit.
7. Restart cùng JobInstance và input snapshot, kiểm tra không có business effect trùng.
8. Thiết lập verifier: input keys phải thuộc output/filter/quarantine đúng policy, giá trị business khớp.
9. Chỉ chuyển `PROCESSED` sau StepExecution thành công và validation; đồng thời thử test âm mark quá sớm.

**Bài C — Marker, archive và monitoring**

10. Ghi `.done` qua temp + atomic move trên filesystem có hỗ trợ, phát hiện duplicate target.
11. Mô phỏng crash sau business commit nhưng trước `PROCESSED`; recovery thực hiện reconciliation thay vì import lại mù quáng.
12. Mô phỏng crash sau archive nhưng trước `ARCHIVED`; verify target rồi cập nhật state.
13. Chạy hai manager JVM cùng nhìn một file; confirm global claim không overlap.
14. Đo claim success/conflict, lease renew failure, PROCESSING age, per-file validation latency và toàn batch publication latency.

**Tiêu chí đạt:** mỗi logical file có trạng thái đúng với bằng chứng durable; một file có thể được replay nhưng **không nhân đôi business effect**, dữ liệu được đối soát đầy đủ, stale owner bị chặn, và batch không được công bố chỉ vì các marker `.done` cùng xuất hiện.

## 42. Checklist trước production

- [ ] Đã định nghĩa **process indicator cấp file** và phân biệt với record-level indicator/checkpoint.
- [ ] FileId, batch/tenant scope, source version và checksum/manifest bất biến qua restart.
- [ ] `READY` chỉ xuất hiện sau producer handoff/validation; không đọc file đang được ghi.
- [ ] Claim file bằng phép **nguyên tử** ở coordination store, không `SELECT` rồi `UPDATE` rời rạc.
- [ ] Marker `.processing` không được coi là lock mạnh nếu thiếu atomic create, recovery và liveness.
- [ ] Marker `.done` được công bố hoàn chỉnh, tránh overwrite bằng stale attempt.
- [ ] Có owner/lease/epoch và policy reclaim; không coi timeout là chứng cứ worker đã chết.
- [ ] Fencing được **sink thực sự kiểm tra** khi cần strong stale-worker protection.
- [ ] Reader `@StepScope`, `ExecutionContext` và JobRepository không bị dùng nhầm làm distributed lock.
- [ ] Không mark `PROCESSED` lúc reader EOF, writer callback hoặc chunk đầu thành công.
- [ ] Completion dựa trên **committed outcomes, StepExecution và reconciliation** rõ ràng.
- [ ] Writer idempotent theo logical business key, phát hiện duplicate khác content/value.
- [ ] Có trạng thái riêng cho `PROCESSED` và `ARCHIVED`, không import lại chỉ vì archive lỗi.
- [ ] Remote chunking/partitioning giữ correlation đúng và chịu được duplicate/late replies.
- [ ] Global quality/publication gate không chỉ dựa per-file done marker.
- [ ] Recovery có phân biệt complete-but-indicator-lag, partial-committed và source-mismatch.
- [ ] Có test hai JVM/process, crash giữa commit và indicator, lease expiry, stale writer, source change.
- [ ] Có metric per state, oldest age, claim failures, reconciliation mismatch và recovery SLA.
- [ ] Có bảo mật tenant/path, audit state transitions và retention phù hợp.
- [ ] Runbook cấm reset/xóa indicator/JobRepository hoặc business output mù quáng.

**Ghi nhớ:** **process indicator cho file** giúp hệ thống file scaling biết **ai đang xử lý và outcome của từng logical file**, nhưng chỉ đáng tin khi **định danh input bất biến, claim nguyên tử, owner/lease/fencing, transaction-boundary rõ và validation trước completion**. Spring Batch cung cấp JobRepository/ExecutionContext cho checkpoint và restart; indicator là lớp điều phối **cấp file** bổ sung, không thay thế. Khi process chết sau business commit nhưng trước khi đổi cờ, hệ thống phải **đối soát, replay an toàn và chuyển trạng thái có điều kiện**, thay vì dùng sự tồn tại của marker hoặc một status đơn lẻ để suy ra dữ liệu đã hoàn tất.
