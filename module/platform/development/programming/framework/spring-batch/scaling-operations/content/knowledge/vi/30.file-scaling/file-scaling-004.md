# Lock file khi nhiều process

Khi một Spring Batch job đọc hàng nghìn tệp lớn, cách mở rộng tự nhiên là chạy **nhiều worker/process** cùng quét một thư mục hoặc xử lý các file được manager phân phối. Nếu hai process cùng chọn một file, cả hai có thể đọc và ghi kết quả cho cùng những record. Hệ quả không chỉ là lãng phí CPU/I/O: output có thể bị **ghi trùng, cộng dồn hai lần, ghi dở hoặc bị đánh dấu hoàn tất khi một worker thực tế thất bại**. Vì thế, cần cơ chế xác định **process nào được quyền xử lý file nào, quyền đó tồn tại bao lâu, và điều gì xảy ra khi process chết giữa chừng**.

Bài học thuộc chương **File scaling** của module **SPRING_BATCH_SCALING_OPERATIONS**. Module tập trung mở rộng Spring Batch cho workload dữ liệu lớn bằng multi-threaded step, parallel steps, partitioning và các mô hình phân tán phù hợp; học cách đo nút thắt, bảo đảm thread safety, retry/restart, vận hành job và chọn kiến trúc theo tài nguyên thực tế. Chủ đề **“Lock file khi nhiều process”** đi sâu vào khóa file ở mức hệ điều hành, lựa chọn claim/lease bằng cơ sở dữ liệu, cách giữ input snapshot ổn định và các biện pháp chống xử lý trùng trong Spring Batch.

**Nguyên tắc cốt lõi:** **file lock là cơ chế phối hợp quyền truy cập**, không phải cơ chế exactly-once processing. Một lock có thể ngăn hai process hợp tác cùng đọc một file tại một thời điểm, nhưng **không tự rollback output đã commit, không thay JobRepository, không bảo vệ side effect ngoài file và không đảm bảo đúng trên mọi network filesystem**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện race condition khi nhiều JVM, worker hoặc container cùng quét thư mục.
2. Phân biệt **advisory OS file lock**, **sidecar lock file**, **atomic rename**, **manifest/DB claim** và **lease + fencing token**.
3. Sử dụng Java NIO `FileChannel.tryLock()` / `FileLock` đúng vòng đời, hiểu `OverlappingFileLockException`, process crash và sự khác biệt giữa các hệ điều hành.
4. Giải thích vì sao kiểm tra `Files.exists(path)` rồi tạo file hoặc thấy file `.lock` tồn tại **không đủ làm lock an toàn**.
5. Thiết kế bàn giao file bất biến từ producer sang Spring Batch để worker không đọc khi file đang được ghi.
6. Kết hợp phân chia theo file với `Partitioner`, `ExecutionContext`, `@StepScope`, JobRepository và snapshot đầu vào bất biến.
7. Thực hiện claim/lease bằng database với thao tác nguyên tử và biết khi nào cần **fencing** để ngăn worker cũ.
8. Thiết kế writer idempotent và manifest trạng thái `READY → PROCESSING → COMPLETED` để restart không xử lý sai.
9. Kiểm thử **hai process thật**, crash, mạng lỗi, lock hết hạn, stale worker và hai worker giành cùng file.
10. Đánh giá throughput, file skew, I/O contention, khóa và overhead để lựa chọn mô hình scale phù hợp.

**Tình huống xuyên suốt:** thư mục inbox chứa 8.000 file CSV được gửi theo từng giờ; mỗi file có mã phiên bản và hàng nghìn giao dịch. Hai manager Spring Batch cùng chạy ở hai pod do rolling deployment; mỗi manager có nhiều worker. Nếu cả hai cùng quét inbox và lấy `transactions-042.csv`, record của file này có thể được nhập hai lần. Ta cần một hợp đồng phối hợp rõ: file phải **được công bố hoàn chỉnh**, một worker được nhận ownership, dữ liệu được xử lý có checkpoint/replay an toàn, và file chỉ được đánh dấu hoàn tất khi kết quả nghiệp vụ đã bền vững.

## 2. Vì sao nhiều process cùng đụng một file?

Một tình huống điển hình khi mọi worker đều quét cùng thư mục:

~~~text
12:00:00.000 Worker A: liệt kê inbox/*.csv
12:00:00.001 Worker B: liệt kê inbox/*.csv
12:00:00.002 Worker A: thấy file-042.csv là READY
12:00:00.003 Worker B: thấy file-042.csv là READY
12:00:00.004 Worker A: mở file-042.csv
12:00:00.005 Worker B: mở file-042.csv
12:00:00.100 Cả A và B cùng ghi giao dịch của file-042.csv
~~~

Đây là lỗi **check-then-act/TOCTOU**: quan sát file đang rảnh ở thời điểm kiểm tra **không bảo đảm** nó còn rảnh khi bắt đầu xử lý.

~~~mermaid
sequenceDiagram
    participant A as Worker A
    participant F as Shared File
    participant B as Worker B
    A->>F: exists / status = READY?
    B->>F: exists / status = READY?
    F-->>A: Có
    F-->>B: Có
    A->>F: Đọc và xử lý
    B->>F: Đọc và xử lý
    Note over A,B: Cả hai tưởng mình là owner
~~~

**Các kiểu cạnh tranh khác:**

- **Hai reader** cùng đọc một file bất biến: về mặt đọc vật lý có thể không gây lỗi, nhưng **cùng thực hiện business effect** sẽ gây xử lý trùng.
- **Reader và producer** cùng mở file đang được ghi: reader có thể thấy dữ liệu chưa hoàn chỉnh, cuối file tạm thời hoặc bản ghi bị cắt.
- **Hai writer** cùng ghi một output file: có thể trộn bytes, ghi đè, lỗi rename hoặc tạo file không hợp lệ.
- **Worker mới và worker cũ** cùng xử lý sau timeout/lease expiry: hai process đều có thể tiếp tục chạy nếu không có fencing.
- **Hai JobExecution** cùng dùng chung inbox và business DB: lock ở cấp Java thread không đủ.

## 3. File lock, job ownership và idempotency là ba vấn đề khác nhau

| Cơ chế | Nó trả lời câu hỏi | Phạm vi thường có | Điều không bảo đảm |
| --- | --- | --- | --- |
| **OS FileLock** | Ai đang giữ quyền khóa vùng file? | Process/JVM trên hệ điều hành và filesystem hỗ trợ | Business effect exactly-once, fencing qua network partition |
| **Sidecar lock file** | Có một đối tượng điều phối tương ứng file không? | Đường dẫn tệp `.lck`; chỉ đúng khi có atomic operation/protocol | Chỉ tồn tại file không chứng minh owner còn sống |
| **Atomic rename/claim** | Ai đã chuyển file sang trạng thái xử lý trước? | Một filesystem có semantics rename phù hợp | Restart, lease expiry, external DB side effect |
| **DB manifest claim** | Worker nào sở hữu logical file entry trong catalog? | Mọi process dùng DB chung | Worker cũ ngừng ghi nếu sink không có fencing |
| **Lease** | Quyền xử lý có còn hạn? | Trạng thái có expiry được kiểm soát | Worker cũ chắc chắn đã dừng khi hết hạn |
| **Fencing token** | Lần sở hữu nào được phép ghi mới nhất? | Sink phải kiểm tra token | Không có tác dụng nếu writer bỏ qua token |
| **Idempotent writer** | Cùng logical record được replay có tạo hiệu ứng trùng? | Business DB/API có khóa operation | Tự phân bổ ownership hoặc bảo toàn snapshot |
| **JobRepository** | Step/JobExecution đã chạy đến đâu? | Metadata Spring Batch | Thay được business dedup/OS lock |

Đối với file scaling, cần kết hợp nhiều lớp: **producer handoff → file identity/manifest → worker ownership → transactional processing + checkpoint → idempotent sink → completion/reconciliation**. Chỉ thêm `synchronized` ở một service Java không giải quyết cạnh tranh giữa các JVM.

## 4. OS file lock thực sự hoạt động thế nào?

Java NIO cung cấp `FileChannel.lock()` và `FileChannel.tryLock()` trả về `java.nio.channels.FileLock`. Lock gắn với vùng byte của một file được mở và chịu ảnh hưởng của **hệ điều hành/file provider**.

~~~text
Process A                       File system                       Process B
   | FileChannel.tryLock()           |                                |
   |-------------------------------->|                                |
   |  nhận lock                      |                                |
   |<--------------------------------|                                |
   |                                 |<-------------------------------|
   |                                 |           tryLock()
   |                                 |------------------------------->|
   |                                 |          lock unavailable      |
   | process kết thúc/close lock     |                                |
   |-------------------------------->|                                |
   |                                 |          Process B có thể thử lại
~~~

### Các thuộc tính quan trọng

- `tryLock()` cố gắng lấy lock **ngay**, có thể trả `null` nếu vùng lock bị process khác giữ; `lock()` chờ (blocking) theo semantics API.
- Trong cùng JVM, yêu cầu lock vùng đang chồng lấn có thể ném `OverlappingFileLockException` thay vì trả `null`. Java file locks mang phạm vi **JVM**, không phải mutex per-thread.
- `FileLock` cần được **release/close**; đóng channel liên quan cũng giải phóng lock. Khi process chết, OS thường giải phóng khóa nội bộ; **một sidecar `.lck` vẫn có thể còn trên đĩa**.
- Trên nhiều hệ POSIX, file locks có tính **advisory**: process không tham gia protocol vẫn có thể đọc/ghi file. Một số nền tảng/kiểu filesystem có hành vi mandatory hoặc lỗi access khác; phải kiểm thử.
- API không tự bảo đảm lock xuyên mọi network filesystem, object storage, container mount hoặc trạng thái failover. NFS/SMB có semantics, cache và timeout riêng.

**Lock thành công chỉ chứng minh OS/filesystem báo đã cấp khóa tại thời điểm đó.** Nó không chứng minh input đã được ghi xong, không chứng minh doanh nghiệp chỉ nhập một lần, và không tự thay thế checkpoint/restart.

## 5. Đoạn mã Java NIO dùng sidecar lock đúng vòng đời

Một pattern thực dụng cho **các process trên cùng host hoặc shared filesystem đã kiểm chứng lock semantics** là khóa một **file sidecar có đường dẫn cố định** tương ứng với input. Ưu điểm: không cần mở input ở chế độ ghi, tất cả worker dùng chung đối tượng lock.

~~~java
import java.io.IOException;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.channels.OverlappingFileLockException;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.concurrent.Callable;

final class LocalFileLockCoordinator {
    /**
     * Trả false nếu có owner khác đang giữ OS lock.
     * Action được chạy đồng bộ hoàn toàn trước khi release.
     */
    boolean tryProcess(Path inputFile, Callable<Void> action)
            throws Exception {
        Path lockPath = inputFile.resolveSibling(
                inputFile.getFileName().toString() + ".lck");

        try (FileChannel channel = FileChannel.open(
                lockPath,
                StandardOpenOption.CREATE,
                StandardOpenOption.WRITE)) {
            FileLock acquired;
            try {
                acquired = channel.tryLock();
            } catch (OverlappingFileLockException busyInSameJvm) {
                return false;
            }
            if (acquired == null) {
                return false; // Another process holds this region.
            }

            try (FileLock ignored = acquired) {
                action.call();
                return true;
            }
        }
    }
}
~~~

Ví dụ gọi:

~~~java
Path input = Path.of("/data/inbox/transactions-042.csv");
boolean owner = new LocalFileLockCoordinator().tryProcess(
        input,
        () -> {
            // Đọc file snapshot, xử lý đồng bộ và kiểm tra outcome.
            // JobRepository/business DB xác định liệu work đã COMPLETED.
            runFileImportSynchronously(input);
            return null;
        });

if (!owner) {
    // Không coi là lỗi dữ liệu; bỏ qua file đang có owner khác
    // hoặc đưa vào lịch retry/backoff theo chính sách.
}
~~~

**Phạm vi minh họa:** `runFileImportSynchronously` là hàm nghiệp vụ cần triển khai riêng. Không chỉ gọi một phương thức **launch async job** rồi return: khi `action.call()` kết thúc, `FileLock` sẽ được thả, và worker khác có thể nhận lock trong khi job thực tế vẫn chạy. Lock phải bao phủ **toàn bộ khoảng thời gian yêu cầu exclusivity**.

### Những quy tắc thiết yếu cho sidecar lock

1. **Tất cả** process phải tính **cùng một lock path** cho cùng logical input. Chuẩn hóa nguồn, version, đường dẫn và namespace tenant trước khi chọn khóa.
2. **Không tự xóa file `.lck` khi release lock**. Đối với filesystem có inode semantics, process A có thể giữ lock trên inode cũ, xóa file rồi process B tạo inode mới ở cùng tên và cũng giữ lock thành công: **split-brain**.
3. Đừng dựa vào `Files.exists(lockPath)` để kết luận có lock; **file có thể tồn tại nhưng không có OS lock**. File sidecar có thể giữ vĩnh viễn, còn quyền xử lý được xác định bằng lock đang nắm giữ.
4. Không dùng `CREATE_NEW` đơn lẻ rồi quên stale cleanup: nếu process chết, file sẽ ở lại và chặn mọi người mãi. Stale removal cũng là một race nếu không có protocol.
5. Không dùng lock file ở directory world-writable hoặc cho phép symlink tùy ý. Xác nhận root/canonical identity, quyền truy cập và threat model, nhất là trên Windows/Linux khác nhau.
6. Đóng `FileChannel` khác trỏ cùng file lock tùy tiện có thể ảnh hưởng semantics khóa ở một số OS. Giữ lifecycle lock và channel rõ, tránh chia sẻ/chồng lấn không cần thiết.
7. `tryLock()` có thể ném `IOException` do lỗi I/O/permission. **Không phân loại lỗi hạ tầng thành “file đang bận”**; fail/alert hoặc retry có giới hạn theo policy.

## 6. File lock không phải khóa nghiệp vụ

Giả sử cả worker A và B đều tuân theo sidecar lock. A lấy lock, nhập 99% record và commit DB theo nhiều chunk, rồi crash. OS giải phóng lock. B lấy lock và nhập lại file từ đầu:

~~~text
Worker A: lock acquired
  chunks 1..20 COMMIT
  process crash

OS: file lock released

Worker B: lock acquired
  starts file from beginning
  chunks 1..20 replay
~~~

Nếu writer thực hiện `UPDATE balance SET amount = amount + :delta`, cùng giao dịch có thể cộng hai lần. **FileLock không rollback 20 chunk đã commit**. Giải pháp là checkpoint cùng JobInstance khi phù hợp, nguồn file bất biến, và writer **idempotent theo business key**.

### Phân biệt ba thời điểm

| Mốc | Ý nghĩa | Không chứng minh |
| --- | --- | --- |
| Có file lock | Process được cấp quyền tương tác với file theo protocol | File đã xử lý chưa, DB đã commit chưa |
| Chunk DB commit | Một số business effects đã bền vững | Toàn file hoàn tất, manifest được mark COMPLETED |
| File COMPLETED trong manifest | Hợp đồng xử lý file đã hoàn tất theo logic ứng dụng | Các API/event ngoài DB đúng một lần nếu không có dedup |

Kết quả tin cậy đòi hỏi **ownership, checkpoint, business idempotency và manifest trạng thái** được thiết kế nhất quán, chứ không chỉ khóa được file.

## 7. Đừng đọc file khi producer còn ghi

Ngay cả **chỉ một reader** cũng có thể đọc dữ liệu chưa đủ nếu producer đang append vào file và **không tuân theo cùng lock**. Hợp đồng đưa file vào inbox quan trọng không kém lock.

**Mẫu producer handoff trong cùng filesystem:**

~~~text
Producer writes:
  incoming/transactions-042.csv.part
  -> flush/close, xác nhận checksum và record count khi cần
  -> Files.move(.part, ready/transactions-042.csv, ATOMIC_MOVE)

Consumer sees:
  chỉ quét ready/*.csv
  -> xác thực manifest/snapshot
  -> claim file, đọc immutable content
~~~

~~~java
Files.move(tempFile, readyFile,
           StandardCopyOption.ATOMIC_MOVE);
~~~

**Điều kiện/giới hạn:** `ATOMIC_MOVE` chỉ được hỗ trợ trong phạm vi mà filesystem/file provider cho phép (thường cùng filesystem); nếu không, có thể ném `AtomicMoveNotSupportedException`. Nó giúp thay đổi tên xuất hiện nguyên tử theo semantics FS, **không bảo đảm tự động fsync dữ liệu và directory metadata khi mất điện**, và cũng không thay thế file ownership cho nhiều consumer. Việc target đã tồn tại khi dùng `ATOMIC_MOVE` có hành vi phụ thuộc provider; hãy chọn tên/version không xung đột và policy rõ.

**Không** coi `Thread.sleep(500)` sau khi thấy file là cách xác định file đã ghi xong. File có thể bị tạm ngừng ghi lâu hơn hoặc được producer mở lại. Với object storage, dùng **object version/ETag/manifest/ready marker** và hợp đồng publish phù hợp; không giả định POSIX rename/lock tồn tại.

## 8. Vì sao một file .lock hiện hữu chưa đủ?

Một implementation sai phổ biến:

~~~java
if (!Files.exists(lockPath)) {
    Files.createFile(lockPath);
    process(inputFile);
}
~~~

Hai process có thể đều thấy “không tồn tại” rồi cạnh tranh tạo file. `createFile` (tương tự `CREATE_NEW`) giúp **một process thắng tạo file** ở filesystem hỗ trợ atomic create, nhưng **chỉ tạo file** chưa có cơ chế phục hồi ownership. Khi process thắng chết, file còn mãi.

Một implementation sai khác:

~~~text
Nếu .lock tồn tại hơn 10 phút:
  Process B xóa .lock rồi tạo lại.

Nhưng Process A có thể vẫn đang xử lý chậm hoặc bị network pause.
Process A và B có thể cùng nghĩ mình sở hữu file.
~~~

**Xóa stale lock bằng tuổi file** chỉ hợp lệ trong một protocol đã giải quyết **liveness, fencing, atomic owner change và sink behavior**. Chỉ so timestamp rồi xóa file không ngăn worker cũ tiếp tục commit.

## 9. Atomic rename để claim file: điểm mạnh và giới hạn

Một pattern khác là chuyển file từ thư mục `ready` sang `processing/<worker-id>/`. Nếu rename được thực hiện **nguyên tử** trên đúng filesystem, một file không thể đồng thời được hai worker chuyển khỏi cùng nguồn thành công theo cùng protocol.

~~~text
ready/file-042.csv
   -> Worker A atomic rename ->
processing/worker-A/file-042.csv

Worker B cố rename source cũ -> không còn source, claim thất bại.
~~~

**Ưu điểm:** đơn giản, hữu ích trong local filesystem/same mount và có thể giảm số worker phải đọc cùng file. **Giới hạn:**

- Rename **không giải quyết crash recovery**: file nằm trong `processing` sau khi worker chết; cần quyết định khi nào chuyển lại `ready`, ai được quyền và ngăn worker cũ còn chạy.
- `Files.move` qua **filesystem khác** không thể giả định atomic; copy+delete không phải atomic claim.
- Không được mặc định `ATOMIC_MOVE` cung cấp no-overwrite semantics giống một lệnh “compare-and-swap”; hãy tránh target collision và kiểm tra provider.
- Trên NFS/SMB cần test chính xác rename visibility và failover semantics; với S3/object storage không có POSIX rename thực sự.
- Nếu input được downstream trỏ tới bằng path cố định, move có thể phá đường dẫn/snapshot. Manifest + read-only immutable object có thể phù hợp hơn.

**Khi một job restart**, file trong `processing` chưa chứng minh đã được xử lý thành công; phải kiểm tra output/checkpoint/JobRepository và ownership trước khi quyết định requeue.

## 10. Tại sao NFS, SMB và object storage cần thiết kế riêng?

Không phải mọi môi trường chia sẻ file đều có semantics khóa giống local disk.

| Môi trường | Điều kiện cần kiểm tra | Rủi ro |
| --- | --- | --- |
| Local ext4/XFS/NTFS | OS lock behavior, quyền, path canonicalization, process crash | Advisory access, overlap trong cùng JVM, stale sidecar |
| NFS | Server-side lock manager/protocol version, session, reconnect và node failover | Lock mất hiệu lực hoặc recovery delay, client cache, split brain khi mạng lỗi |
| SMB | Share modes, lease/oplock, reconnect, server failover | Hành vi lock/rename khác giữa client/server và hệ điều hành |
| Kubernetes shared volume | CSI driver, mount options, network FS semantics, pod reschedule | Các pod có thể thấy file khác thời điểm, lock có thể không đúng như local |
| S3/Blob/Object storage | Versioning, ETag, conditional requests, consistency của provider | Không có `FileChannel` POSIX lock, rename thường là copy/delete |

**Không khẳng định “NFS luôn không hỗ trợ lock” hoặc “NFS lock luôn an toàn”**: cần xác nhận phiên bản NFS, server, mount options, failover và library. Nếu mất kết nối kéo dài, một client cũ có thể **tưởng vẫn sở hữu quyền**, trong khi coordinator cấp quyền cho worker khác. Khi business effect quan trọng, nên đưa ownership về database/coordination service và dùng **fencing token được sink kiểm tra**.

Với object storage, có thể dùng **conditional PUT/If-Match/If-None-Match** khi provider hỗ trợ và hợp đồng đã được thử nghiệm, hoặc đơn giản hơn là manifest ở database. Không mô phỏng khóa POSIX bằng cách kiểm tra object `.lock` tồn tại rồi ghi đè tùy ý.

## 11. File identity phải ổn định trước khi chọn lock

Một file có thể có nhiều đường dẫn khác nhau (symlink, mount alias, đường dẫn tương đối), hoặc cùng tên nhưng nội dung/phiên bản thay đổi. Nếu lock path được xây từ tên tùy ý, hai worker có thể khóa **hai sidecar khác nhau** nhưng đọc **cùng dữ liệu**.

**Một manifest entry lý tưởng** gồm:

- `fileId`: ID bất biến của logical source artifact hoặc một immutable version.
- `sourceUri`: đường dẫn/URI canonical theo namespace hợp lệ.
- `sourceVersion`: object version, generation hoặc checksum/manifest version.
- `sizeBytes`, `expectedRecords`, `checksum` nếu cần kiểm chứng integrity.
- `batchKey`, `tenantId`, `partitionKey`: phạm vi job và ownership.
- `status`, `claimedBy`, `leaseEpoch`, `leaseUntil`, timestamps và error reason.

Ví dụ:

~~~json
{
  "fileId": "inbox-20261126-0042",
  "batchKey": "settlement-2026-11-26",
  "sourceUri": "file:///data/ready/transactions-042.csv",
  "sourceVersion": "sha256:20cb...87a9",
  "expectedRecords": 25000,
  "tenantId": "tenant-a",
  "partitionKey": "file-0042"
}
~~~

Đây là **envelope minh họa**, không phải kiểu dữ liệu do Spring Batch tự sinh. Khi file thay đổi nội dung, không được vô tình tái sử dụng `fileId` như thể input cũ còn nguyên. Với object storage, version ID thường mạnh hơn so sánh tên file; ETag có thể không phải checksum toàn file trong mọi chế độ upload, vì vậy cần hiểu contract của provider.

### Input bất biến là điều kiện để restart

Reader Spring Batch lưu checkpoint vào `ExecutionContext` nhưng checkpoint chỉ đúng khi file **giữ cùng nội dung và thứ tự record**. Nếu producer append hoặc thay file trong khi job chạy, “đọc lại từ record 20.001” có thể dẫn tới bỏ sót/trùng do nội dung đã dịch chuyển. Chốt snapshot/version trước khi claim, và **fail/reconcile** nếu nhận thấy checksum/size/metadata thay đổi trái hợp đồng.

## 12. Manifest trong database: cách phối hợp nhiều máy

Khi worker chạy trên nhiều node và filesystem không bảo đảm lock đủ mạnh, database có thể làm **điểm phân xử ownership**. Mỗi file là một dòng manifest; claim được thực hiện bằng một thao tác transaction nguyên tử, không dùng “SELECT READY rồi UPDATE” không khóa.

~~~sql
CREATE TABLE file_manifest (
    file_id          VARCHAR(160) PRIMARY KEY,
    batch_key        VARCHAR(100) NOT NULL,
    source_uri       VARCHAR(500) NOT NULL,
    source_version   VARCHAR(160) NOT NULL,
    tenant_id        VARCHAR(100),
    expected_records BIGINT NOT NULL CHECK (expected_records >= 0),
    state            VARCHAR(20) NOT NULL
                     CHECK (state IN (
                         'READY', 'PROCESSING', 'COMPLETED',
                         'FAILED', 'QUARANTINED')),
    claimed_by       VARCHAR(160),
    lease_epoch      BIGINT NOT NULL DEFAULT 0,
    lease_until      TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    last_error_code  VARCHAR(80),
    UNIQUE (batch_key, source_uri, source_version)
);

CREATE INDEX idx_file_claim
    ON file_manifest (state, lease_until, file_id);
~~~

**Quan trọng:** một file **không phải** một lock per Java object; nó là một work item được cấp quyền theo `file_id`/`source_version`. Các worker chia sẻ cùng database có thể giành claim qua unique constraints và transactional update. Tuy nhiên, manifest chỉ ghi nhận **ai đang được cho là owner**; nó **chưa tự chặn** một worker cũ tiếp tục ghi vào sink khi lease đã hết.

### Một trạng thái hợp lệ cho file

~~~mermaid
stateDiagram-v2
    [*] --> READY: producer publish immutable file
    READY --> PROCESSING: worker claim
    PROCESSING --> COMPLETED: verified output + CAS completion
    PROCESSING --> FAILED: permanent failure/policy
    PROCESSING --> READY: recoverable failure / safe requeue
    PROCESSING --> PROCESSING: lease renewal or safe re-claim
    FAILED --> READY: approved repair/replay
    FAILED --> QUARANTINED: manual review
~~~

Đây là state machine **ứng dụng minh họa**. Không tự tái sử dụng `COMPLETED` thành `READY` trong cùng snapshot khi downstream đã tiêu thụ output; replay cần business idempotency hoặc correction job có version riêng.

## 13. Claim file bằng PostgreSQL: một câu UPDATE nguyên tử

Worker muốn nhận `file-0042` có thể chạy trong **transaction ngắn**:

~~~sql
UPDATE file_manifest
SET state = 'PROCESSING',
    claimed_by = :workerId,
    lease_epoch = lease_epoch + 1,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '90 seconds'
WHERE file_id = :fileId
  AND (
      state = 'READY'
      OR (
          state = 'PROCESSING'
          AND lease_until < CURRENT_TIMESTAMP
      )
  )
RETURNING file_id, source_uri, source_version, lease_epoch, lease_until;
~~~

**Diễn giải:**

- PostgreSQL lấy row lock khi UPDATE; nếu hai worker cùng claim, chỉ một người có thể chuyển state phù hợp tại một thời điểm theo cơ chế kiểm tra điều kiện cập nhật.
- Không trả dòng nào: file **không claim được theo điều kiện hiện tại**, không được tự xử lý.
- Trả một dòng: worker có `lease_epoch` mới và metadata nguồn để bắt đầu.
- Mọi lần claim lại sau lease expiry đều tăng epoch; token mới thể hiện **thế hệ owner mới**.

Đặt lease TTL theo workload và có **heartbeat renewal**. Không mặc định “file này chắc chắn xử lý xong dưới 90 giây” nếu job có bước processor chậm hoặc bị GC pause. Dùng thời gian do **DB** quyết định để tránh chênh lệch đồng hồ giữa các pod.

### Đừng giữ DB row lock cho cả thời gian xử lý file

**Sai về vận hành:** mở transaction, `SELECT FOR UPDATE` file manifest rồi giữ DB lock hàng giờ trong khi đọc/ghi file. Điều đó giữ connection/lock quá lâu, làm contention và tăng rủi ro timeout.

**Đúng:** claim bằng transaction ngắn, **commit claim**, xử lý file, gia hạn lease theo nhịp, rồi update trạng thái hoàn tất bằng CAS khi đã xác minh outcome. Với yêu cầu strong fencing, business sink cần kiểm tra quyền thế hệ owner **trong từng transaction ghi** hoặc một cơ chế fencing tương đương.

## 14. Heartbeat và completion theo owner/epoch

Một worker đang xử lý có thể gia hạn lease:

~~~sql
UPDATE file_manifest
SET lease_until = CURRENT_TIMESTAMP + INTERVAL '90 seconds'
WHERE file_id = :fileId
  AND claimed_by = :workerId
  AND lease_epoch = :epoch
  AND state = 'PROCESSING'
  AND lease_until >= CURRENT_TIMESTAMP;
~~~

**Số dòng bị cập nhật phải bằng 1.** Nếu là 0, worker đã mất quyền theo protocol; nó phải **ngừng ghi/từ chối commit** hoặc chuyển sang chế độ đối soát, không tiếp tục âm thầm xử lý hàng triệu bản ghi.

Khi đã hoàn thành và đối soát:

~~~sql
UPDATE file_manifest
SET state = 'COMPLETED',
    completed_at = CURRENT_TIMESTAMP,
    lease_until = NULL
WHERE file_id = :fileId
  AND claimed_by = :workerId
  AND lease_epoch = :epoch
  AND state = 'PROCESSING'
  AND lease_until >= CURRENT_TIMESTAMP;
~~~

Nếu update completion trả 0, **không được kết luận đã hoàn thành ownership hợp lệ**. Có thể lease đã hết, một worker khác đã nhận việc, hoặc state đã thay đổi. Cần kiểm tra output, stale worker và recovery policy.

**Lỗi hay gặp:** heartbeat chạy ở thread riêng nhưng business writer không kiểm tra lease/token. Worker A mất quyền trong lúc network pause, B nhận claim mới, A vẫn tiếp tục commit trên DB vì thread writer không biết. Heartbeat giúp phát hiện mất quyền sớm hơn nhưng **không phải fencing tuyệt đối**.

## 15. Lease expiry không đồng nghĩa worker cũ đã chết

Một kịch bản split-brain:

~~~text
T0 Worker A claim file-042, epoch=7, TTL 90s.
T1 Worker A dừng lâu do GC pause/network partition.
T2 Lease hết hạn; Worker B claim epoch=8.
T3 Worker B bắt đầu ghi output.
T4 Worker A sống lại, vẫn cầm dữ liệu đã đọc.
T5 Nếu sink không kiểm epoch, A cũng ghi output.
~~~

~~~mermaid
sequenceDiagram
    participant A as Worker A (epoch 7)
    participant DB as Manifest DB
    participant B as Worker B (epoch 8)
    participant S as Business Sink
    A->>DB: claim(epoch 7)
    Note over A: GC pause / mất mạng
    B->>DB: claim(expired) -> epoch 8
    B->>S: write(epoch 8)
    A->>S: write(epoch 7, stale)
    Note over S: Phải reject epoch 7 theo fencing protocol
~~~

Một **fencing token** là số thế hệ tăng đơn điệu (ví dụ `lease_epoch`). Sink được thiết kế phải **từ chối tác động của epoch cũ** khi owner mới đã được cấp token mới.

### Điều kiện để fencing có giá trị

- Mỗi lần grant ownership của cùng file **tăng epoch**.
- Mọi business write chịu rủi ro từ worker cũ đều **mang epoch** hoặc được kiểm quyền trong một transaction có coordination rõ.
- Sink **thực sự từ chối epoch stale**; chỉ thêm trường `epoch` vào log là chưa đủ.
- Nếu sink là DB khác, API ngoài hoặc file output, cần một cách thực thi fencing tại **chính sink ấy**, hoặc thiết kế operation idempotent/chỉ publish sau validation với giới hạn phù hợp.
- **Fencing và idempotency giải quyết hai thứ khác nhau**: fencing ngăn owner cũ ghi; idempotency ngăn cùng logical effect bị áp dụng lặp.

Một DB row lưu epoch trong manifest **không đủ** nếu output writer hoàn toàn bỏ qua nó. Đối với các hiệu ứng quan trọng, cân nhắc cùng database transaction kiểm tra lock/epoch của manifest trước khi ghi, hoặc sink sở hữu last-accepted-epoch theo key và từ chối request cũ.

## 16. Minh họa fencing khi manifest và sink ở cùng database

Một cách dễ suy luận hơn cho PostgreSQL là buộc mỗi transaction ghi **xác thực ownership dưới row lock của manifest**, rồi ghi business effect ngay trong **cùng transaction**:

~~~text
BEGIN business transaction
  SELECT file_id, lease_epoch, claimed_by, state, lease_until
  FROM file_manifest WHERE file_id = :fileId FOR UPDATE

  Verify:
    claimed_by == workerId
    lease_epoch == acquiredEpoch
    state == PROCESSING
    lease_until >= DB current time

  If invalid: ROLLBACK, stop/abort worker
  If valid: write idempotent records of this chunk
COMMIT
~~~

**Cơ chế vì sao hữu ích:** một claim mới cũng phải UPDATE cùng manifest row; nếu write transaction đang giữ row lock, claim mới không thể đổi epoch cho tới khi write transaction kết thúc. Sau đó worker cũ ở transaction tiếp theo nhìn thấy epoch mới và bị từ chối. Cần xử lý transaction isolation, timeouts, lock ordering và giữ mỗi chunk **ngắn** để tránh serialize mọi thứ quá lâu.

**Đừng dùng một `SELECT` không khóa trước khi ghi rồi tin rằng quyền còn nguyên suốt transaction**: ownership có thể đổi giữa check và business write. Với output nằm ngoài database manifest, không có giao dịch nguyên tử như trên, vì vậy yêu cầu **fencing tại sink** hoặc protocol mạnh hơn.

### Ví dụ cập nhật kết quả có khóa nghiệp vụ

~~~sql
CREATE TABLE imported_sale (
    batch_key      VARCHAR(100) NOT NULL,
    file_id        VARCHAR(160) NOT NULL,
    transaction_id VARCHAR(120) NOT NULL,
    net_amount     NUMERIC(18, 2) NOT NULL,
    source_version VARCHAR(160) NOT NULL,
    PRIMARY KEY (batch_key, transaction_id)
);

INSERT INTO imported_sale (
    batch_key, file_id, transaction_id, net_amount, source_version)
VALUES (
    :batchKey, :fileId, :transactionId, :netAmount, :sourceVersion)
ON CONFLICT (batch_key, transaction_id) DO NOTHING;
~~~

`DO NOTHING` ngăn hai **dòng** trùng khóa nhưng phải **kiểm tra giá trị và file owner/source version khi conflict** để không che giấu trường hợp cùng transactionId xuất hiện với số tiền khác hoặc trong file sai. Với hiệu ứng cộng/trừ tiền, cần ledger operation id và update cùng transaction; khóa file không đủ.

## 17. Mô hình có thể đơn giản hơn: chia file sẵn cho PartitionStep

Nếu một **manager** đã tạo danh sách file immutable và partition chúng **không trùng nhau**, từng worker StepExecution có thể nhận **một hoặc nhiều file khác nhau** qua `ExecutionContext`. Khi chỉ **một manager** sở hữu job, không phải file nào cũng cần một OS lock riêng.

~~~mermaid
flowchart TD
    M["Spring Batch Manager Step"]
    P["Partitioner tạo tập file bất biến"]
    M --> P
    P --> W0["worker:partition0 → file-A.csv"]
    P --> W1["worker:partition1 → file-B.csv"]
    P --> W2["worker:partition2 → file-C.csv"]
    W0 --> DB[("Business DB")]
    W1 --> DB
    W2 --> DB
~~~

**Điều kiện:** manager không tạo cùng file vào nhiều partitions, danh sách/ownership không bị hai manager khác độc lập chạy trùng, JobRepository/restart contract rõ, và sink idempotent. Nếu hai JobExecution khác nhau (do scheduler trùng trigger, deploy đồng thời hoặc rolling update) vẫn quét cùng inbox, partitioning **không** ngăn chúng xử lý cùng file; cần thêm **global manifest claim** hoặc cơ chế điều phối cấp job.

### Bảng so sánh nơi nên khóa

| Mô hình | Cơ chế phối hợp chính | Khi nào FileLock có ích? |
| --- | --- | --- |
| Một JVM, reader tuần tự | Spring Batch checkpoint + JobRepository | Ít cần, trừ producer/consumer cùng file |
| Local partitioning, manifest tĩnh | Partition map không giao nhau | Phòng thủ nếu có process khác ngoài manager |
| Multi-process cùng host và lock semantics đã test | Sidecar `FileLock` | Đơn giản để chặn xử lý đồng thời một file |
| Remote partitioning trên nhiều pod | DB claim/lease/fencing + JobRepository | Chỉ bổ sung nếu shared FS hỗ trợ và cần |
| NFS/SMB với failover nghiêm ngặt | DB/coordination service + sink fencing | Không dùng OS lock như hàng rào duy nhất |
| Object storage versioned files | Immutable object manifest + DB ownership | `FileChannel` không áp dụng trực tiếp |

## 18. `Partitioner` không nên phân phối file dựa vào lịch quét biến động

Khi tạo partitions cho Spring Batch, một cách đơn giản là lấy **manifest snapshot đã đóng**, sắp xếp theo file ID và gán một tập file cho mỗi worker:

~~~text
batchKey = settlement-2026-11-26
snapshotVersion = manifest-v3

partition0 -> file-0001, file-0002
partition1 -> file-0003, file-0004
partition2 -> file-0005, file-0006
~~~

Không được tạo `partition0` từ “hai file đầu tiên của `Files.list()` hiện tại” mà không snapshot/sort/persist, vì sau restart thư mục có thể chứa file mới, file biến mất hoặc thứ tự directory listing khác. `ExecutionContext` phải tham chiếu cùng **file identity + source version**, không chỉ tên `partition0`.

### Ví dụ Java Partitioner minh họa cho một file mỗi partition

~~~java
record ImmutableFileRef(
        String fileId, String uri, String version) {}

final class SnapshotFilePartitioner implements Partitioner {
    private final List<ImmutableFileRef> manifestSnapshot;

    SnapshotFilePartitioner(List<ImmutableFileRef> snapshot) {
        this.manifestSnapshot = List.copyOf(snapshot);
    }

    @Override
    public Map<String, ExecutionContext> partition(int gridSize) {
        Map<String, ExecutionContext> result = new LinkedHashMap<>();
        List<ImmutableFileRef> ordered = manifestSnapshot.stream()
                .sorted(Comparator.comparing(ImmutableFileRef::fileId))
                .toList();

        for (ImmutableFileRef file : ordered) {
            ExecutionContext ctx = new ExecutionContext();
            ctx.putString("fileId", file.fileId());
            ctx.putString("sourceUri", file.uri());
            ctx.putString("sourceVersion", file.version());
            result.put("file-" + file.fileId(), ctx);
        }
        return result;
    }
}
~~~

**Chú ý:** đây là mẫu **một StepExecution cho mỗi file**, không phải chunked `gridSize` partitions. Với 8.000 file, tạo 8.000 StepExecutions có overhead JobRepository; có thể gom nhiều file vào mỗi partition hoặc dùng manifest claim loop để workers tự lấy file. `gridSize` trong API **không tự bắt buộc** số partition bằng giá trị ấy, nhưng implementation nên thiết kế theo ngân sách metadata và concurrency thực tế.

**Không đưa danh sách file tùy biến quá lớn vào một `ExecutionContext`**. Nếu danh sách rất lớn, lưu manifest bền vững bên ngoài và truyền một ID/phạm vi key ổn định qua context.

## 19. `@StepScope` và reader theo file đã được giao

Trong một worker step, reader phải nhận **file của partition đó**, không dùng chung mutable reader giữa các worker:

~~~java
@Bean
@StepScope
FlatFileItemReader<SaleInput> saleFileReader(
        @Value("#{stepExecutionContext['sourceUri']}") String sourceUri,
        @Value("#{stepExecutionContext['fileId']}") String fileId,
        @Value("#{stepExecutionContext['sourceVersion']}") String version) {

    Path file = Path.of(URI.create(sourceUri));
    // Bổ sung logic xác minh fileId/version/checksum theo manifest.

    return new FlatFileItemReaderBuilder<SaleInput>()
            .name("saleFileReader-" + fileId)
            .resource(new FileSystemResource(file))
            .linesToSkip(1)
            .lineMapper(saleLineMapper()) // Bean do bài thực hành cung cấp.
            .saveState(true)
            .build();
}
~~~

Ví dụ là **bộ khung Spring Batch 5.x/Java 17+**, cần `SaleInput`, `saleLineMapper()`, imports, mã validate và factory bean phù hợp. `@StepScope` tạo instance per StepExecution; reader state được checkpoint vào ExecutionContext theo hợp đồng JobRepository.

**Điểm cần chú ý:**

- Một `FlatFileItemReader` thường không an toàn để nhiều thread cùng đọc nếu dùng chung state.
- Đừng dùng `@StepScope` như một lock phân tán; nó chỉ điều chỉnh scope bean trong Spring.
- Nếu file không đổi nhưng JobExecution restart, checkpoint có thể giúp tiếp tục; **nếu file đã sửa hoặc reader mapping đổi**, checkpoint không bảo đảm đúng.
- Nếu mỗi file có ID khác nhau, tên `ItemStream` và state phải được quản lý tránh collision phù hợp với cấu trúc worker StepExecution.
- Khi worker bị fail trước commit, reader có thể đọc lại một phần item; business writer vẫn phải idempotent.

## 20. Lock và JobRepository phải đi với nhau khi restart

Spring Batch quản lý `JobInstance`, `JobExecution`, `StepExecution` và `ExecutionContext`. File lock/manifest lại quản lý **ownership tài nguyên**. Hai lớp có thể khác thời điểm:

~~~text
T0 worker A claim file-042.
T1 worker A commit chunks 1..5.
T2 worker A crash trước khi cập nhật COMPLETED.
T3 OS lock được giải phóng, DB lease hết hạn.
T4 worker B claim file-042.
T5 JobRepository cho biết đã checkpoint tới chunk 5,
   hoặc metadata chưa được ghi đầy đủ tùy failure boundary.
~~~

**Không xử lý dựa chỉ trên một dấu hiệu:**

- Có thể **file đã commit output** nhưng manifest vẫn PROCESSING.
- Có thể JobRepository ghi checkpoint nhưng business DB không tham gia cùng transaction (misconfigured datasource).
- Có thể process cũ chưa thực sự chết sau timeout, chỉ mất kết nối với manager.
- Có thể cùng file được một JobInstance khác claim trùng do scheduler/launcher thiếu kiểm soát.

Thiết kế recovery cần **xác định owner, dữ liệu đã commit, checkpoint, snapshot và business idempotency** trước khi phát lại file.

### Không giữ file lock cho toàn JobExecution nếu không cần

Nếu một job dài hàng giờ xử lý nhiều file độc lập, khóa toàn inbox từ đầu đến cuối khiến worker khác không làm được việc. Nên chọn **độ hạt khóa theo file hoặc file group** khi hợp đồng cho phép, và chỉ giữ lock trong quá trình đọc/ghi phần việc tương ứng. Ngược lại, một file có thể gồm nhiều chunk nhưng cần lock **xuyên các commit** nếu mỗi file chỉ được một owner active; giải phóng lock sau mỗi chunk sẽ cho worker khác chen vào xử lý.

## 21. Idempotent writer: khóa file không chống được duplicate business effect

Xét hai lần xử lý cùng file do worker A crash và worker B restart. Nếu transaction chỉ `INSERT` không có unique constraint, hai lượt có thể tạo duplicate rows. Nếu transaction `balance = balance + amount`, cùng record có thể cộng hai lần. Cần **khóa operation theo nghiệp vụ** độc lập với `fileId`/broker message ID.

Ví dụ PostgreSQL:

~~~sql
CREATE TABLE normalized_transaction (
    batch_key       VARCHAR(100) NOT NULL,
    transaction_id  VARCHAR(120) NOT NULL,
    source_file_id  VARCHAR(160) NOT NULL,
    source_version  VARCHAR(160) NOT NULL,
    net_amount      NUMERIC(18, 2) NOT NULL,
    PRIMARY KEY (batch_key, transaction_id)
);

INSERT INTO normalized_transaction (
    batch_key, transaction_id, source_file_id,
    source_version, net_amount)
VALUES (
    :batchKey, :transactionId, :fileId,
    :sourceVersion, :netAmount)
ON CONFLICT (batch_key, transaction_id) DO NOTHING;
~~~

Khóa chính bảo đảm tối đa một **dòng dữ liệu** cho mỗi `(batchKey,transactionId)`. Nhưng `DO NOTHING` **chưa đủ** cho chất lượng dữ liệu: nếu cùng key có số tiền khác hoặc thuộc file/version khác, phải **báo conflict** thay vì âm thầm bỏ qua. Cần kiểm tra row hiện hữu theo rule version/hash và thiết kế transaction an toàn trước concurrent conflict.

### Với tác động tăng/giảm số dư

~~~sql
CREATE TABLE applied_file_operation (
    batch_key       VARCHAR(100) NOT NULL,
    operation_id    VARCHAR(180) NOT NULL,
    payload_hash    VARCHAR(128) NOT NULL,
    PRIMARY KEY (batch_key, operation_id)
);
~~~

Trong **cùng transaction**:

~~~text
INSERT operationId bằng unique constraint
Nếu operation mới: ghi tác động business vào sink
Nếu đã tồn tại: verify payload_hash và không áp dụng lại
COMMIT
~~~

Một operation ID nên gắn với **logical business effect**, ví dụ `batchKey/transactionId/capture`, chứ không chỉ `workerId` hoặc `lease_epoch`. Worker epoch có thể khác trong lần retry hợp lệ, nhưng business effect **vẫn phải được áp dụng một lần**. Nếu gửi event hoặc gọi API, cần idempotency key tại downstream hoặc transactional outbox.

### Fencing không thay thế idempotency

- **Fencing**: từ chối worker cũ epoch 7 sau khi owner epoch 8 được cấp quyền.
- **Idempotency**: worker epoch 8 có thể xử lý lại record worker 7 đã commit, nhưng **không tạo side effect trùng**.
- **Reconciliation**: xác nhận mọi expected business key đều có đúng một kết quả với giá trị chuẩn.

Trong hệ thống tin cậy, thường cần cả ba.

## 22. Khi nhiều process cùng tạo output file

Nếu công việc là **ghép/chuyển đổi file**, không chỉ ghi DB, phải quyết định output ownership. Hai worker cùng ghi `output/result.csv` bằng append có thể trộn dòng hoặc tạo bản ghi cắt nửa, kể cả input files khác nhau.

**Mô hình an toàn hơn:** mỗi partition/worker ghi vào **file tạm riêng**, xác nhận dữ liệu hoàn chỉnh, rồi một bước merge/publish có kiểm soát:

~~~text
input:
  file-A.csv, file-B.csv, file-C.csv

worker 1 -> staging/run-845/p0/part-0001.csv.tmp
worker 2 -> staging/run-845/p1/part-0002.csv.tmp
worker 3 -> staging/run-845/p2/part-0003.csv.tmp

Sau khi mỗi output đã hoàn chỉnh và verified:
  staging manifest xác nhận checksum/count của từng part
  publish step tạo versioned result manifest
  downstream chỉ đọc các parts có trong manifest PUBLISHED
~~~

**Tránh nhiều worker append chung một file** trừ khi đã có một protocol ghi đồng thời thật sự (bao gồm file system semantics, record atomicity, ordering và recovery). `synchronized` của một JVM không giải quyết hai pod; `FileLock` chỉ giúp process hợp tác và không tự làm output đúng sau crash.

### Dùng tệp tạm, checksum và atomic publish khi phù hợp

~~~java
Path temporary = outputRoot.resolve("run-845-p0.csv.part");
Path finalName = outputRoot.resolve("run-845-p0.csv");

// Ghi hoàn chỉnh temporary; flush/close, kiểm tra size/hash.
writeResultToTemporaryFile(temporary);
verifyChecksumAndCount(temporary);

Files.move(temporary, finalName,
           StandardCopyOption.ATOMIC_MOVE);
~~~

Ví dụ minh họa workflow, cần implementation `writeResultToTemporaryFile` và `verifyChecksumAndCount`. Hành vi rename/failover tùy filesystem, và `ATOMIC_MOVE` không tự giải quyết trường hợp process crash **sau move nhưng trước manifest completion**. Khi restart, phải phát hiện final output của cùng logical operation đã tồn tại, kiểm tra checksum, không ghi đè bất kỳ phiên bản khác mà không có CAS/protocol.

**Không dùng một tên tạm chung** như `output.tmp` cho mọi worker; nếu hai worker cùng dùng sẽ va chạm ngay ở bước ghi.

## 23. Không có một transaction bao trùm file, DB và JobRepository

Với file input và PostgreSQL output, những mốc sau không phải một ACID transaction duy nhất:

~~~mermaid
sequenceDiagram
    participant W as Worker
    participant F as File System
    participant B as Business DB
    participant M as Manifest DB
    participant J as JobRepository
    W->>M: claim file / epoch 8
    M-->>W: owner granted
    W->>F: read immutable file
    W->>B: write chunk 1 / COMMIT
    W->>B: write chunk 2 / COMMIT
    W->>J: checkpoint/StepExecution state
    W->>M: mark COMPLETED
    Note over W,M: Mất kết nối có thể xảy ra giữa mọi mốc
~~~

Đây là sơ đồ logic; metadata transaction thực tế phụ thuộc datasource và cấu hình Spring Batch. Nếu JobRepository dùng DB khác business sink, không được tự suy ra checkpoint và output commit nguyên tử.

### Bốn tình huống crash điển hình

| Mốc crash | Trạng thái có thể | Nguyên tắc recovery |
| --- | --- | --- |
| Trước claim | File còn READY | Worker khác claim |
| Sau claim, trước ghi output | PROCESSING, chưa có output | Lease/owner recovery an toàn |
| Sau vài chunk commit | Output một phần, StepExecution có thể chưa phản ánh hết | Restart checkpoint + idempotent writer |
| Sau toàn output, trước mark COMPLETED | DB đủ nhưng manifest vẫn PROCESSING | Reconcile và CAS completion/replay an toàn |

**Một `FileLock` được thả khi process chết không chứng minh file chưa xử lý**. Ngược lại, trạng thái `PROCESSING` trong manifest không chắc worker còn sống, vì worker có thể chết trước khi update. Do đó cần một **recovery state machine** và đối soát, không chỉ nhìn trạng thái lock.

## 24. Chọn cơ chế locking theo môi trường

| Bối cảnh | Phương án nên cân nhắc | Điều cần xác minh |
| --- | --- | --- |
| Hai JVM trên cùng host, shared local filesystem | Sidecar `FileChannel.tryLock` + idempotent sink | OS lock, crash/release, path consistency |
| Producer và consumer trong cùng FS | `.part` → ready atomic handoff | Producer đã close/flush, reader chỉ đọc immutable ready |
| Nhiều worker trong một Spring Batch Job | Stable file manifest + partitioning/StepScope | Không overlap partitions, restart metadata |
| Nhiều manager/pod cùng lấy từ inbox | DB claim + lease/epoch/fencing | Race, stale workers, shared DB availability |
| NFS/SMB và mạng có thể partition | Coordination durable + sink fencing | Server lock/failover semantics thực tế |
| S3/Object storage | Versioned object manifest + conditional claim hoặc DB | Version identity, provider conditional semantics |
| Nhiều writer cùng ghi một output | Per-worker parts + publish/merge | Không có concurrent append, atomic manifest publish |

**Không dùng một thiết kế cho tất cả**. Khi input file chỉ đọc và có thể phân phối không trùng từ một manager, thêm OS lock phức tạp đôi khi không tăng tính đúng đắn. Khi nhiều manager cùng quét inbox, **chỉ partitioning trong từng manager** lại không ngăn duplicate giữa hai job. Mô hình ownership phải khớp với **ranh giới cạnh tranh thực tế**.

## 25. Lock contention và thiết kế backpressure

Khi hàng nghìn worker liên tục thử lấy lock cùng file hot, có thể xảy ra “thundering herd”:

~~~text
100 workers poll ready/file-042.csv mỗi 100 ms.
Chỉ 1 worker thực sự cần xử lý file đó.
99 workers tiêu tốn metadata I/O và CPU vô ích.
~~~

Nên:

1. Chia công việc thành **nhiều immutable file IDs**, không để mọi worker quét toàn directory với cùng thứ tự.
2. Khi `tryLock()` trả busy, dùng **bounded backoff có jitter**, thay vì vòng lặp spin liên tục.
3. Dùng manifest/queue làm **nguồn assignment**, để worker nhận file khác khi một file đang bận.
4. Giới hạn active workers theo **disk throughput, network FS IOPS, DB pool và downstream capacity**.
5. Theo dõi file size skew: một file 100 GiB và 1.000 file 1 MiB có hành vi điều phối rất khác nhau.

### File skew

Nếu mỗi worker xử lý một file và có file lớn gấp 100 lần file khác, tail latency có thể bị file lớn chi phối dù phần lớn worker rảnh. Lựa chọn:

- Chia file trước thành **nhiều immutable shards** bằng quy trình có record-boundary index.
- Dùng **byte-range partitioning** chỉ khi định dạng, parser và seek/record boundary cho phép; CSV có quoted newline không thể chỉ chia byte offset tùy ý.
- Chia theo **logical record index** đã stage, thay vì cắt file thô.
- Cân nhắc local/remote partitioning để workers đọc những vùng dữ liệu ổn định, hoặc remote chunking nếu manager reader nhanh nhưng xử lý/ghi mới là nút thắt.

**Không dùng lock để bù cho partitioning kém**. Một lock cho cả file 100 GiB chỉ đảm bảo một owner, không tự tận dụng được nhiều worker để xử lý file ấy.

## 26. Bảo mật: khóa file cũng là một bề mặt tấn công

File names và directory entries từ nguồn không đáng tin có thể chứa `..`, symlink, hardlink hoặc tên trùng nhau sau chuẩn hóa. Nếu worker có quyền write rộng và tạo `.lck` bằng path ghép chuỗi tùy ý, nó có thể khóa/chạm file ngoài inbox hoặc làm theo policy sai.

**Các biện pháp tối thiểu:**

- Chỉ nhận `fileId`/path từ **manifest đã xác thực**, không trực tiếp từ tên do client gửi mà chưa sanitize.
- Giới hạn input root; chuẩn hóa và kiểm tra path nằm dưới **đúng root thực**. Với directory có thể bị thay symlink giữa check và open, cần bảo vệ TOCTOU thêm bằng quyền filesystem, no-follow semantics hoặc API mở file theo descriptor phù hợp.
- Tách thư mục **ready**, **processing**, **locks**, **output staging** với quyền least privilege; worker không thể sửa manifest nguồn tùy ý.
- Không đặt tenant secret, token, signed URL hoặc PII trực tiếp trong lock file name/log.
- Lock path cần có namespace **tenant + file identity** an toàn khi hai tenant có file cùng tên, và tránh xung đột/hash collision của cách đặt tên.
- Đừng cho worker xóa `.lck` của process khác; với file-sidecar OS lock, file thường nên **tồn tại bền vững**.
- Kiểm soát ai có quyền đổi trạng thái `FAILED → READY`, sửa checksum/snapshot hoặc hoàn tất manifest.
- Với DB claim, sử dụng parameterized SQL, transaction, DB roles và audit owner transitions.

**Không coi “đang giữ file lock” là chứng minh người dùng có quyền đọc tenant ấy**. Authorization và locking là hai lớp khác nhau.

## 27. Monitoring: đừng đo chỉ bằng số file còn trong inbox

| Metric/tín hiệu | Nó giúp trả lời điều gì? | Khi bất thường |
| --- | --- | --- |
| `ready_file_count` | Còn bao nhiêu file chưa claim? | Backlog tăng kéo dài |
| `ready_oldest_age` | File lâu nhất đợi xử lý bao lâu? | Vượt SLA ingestion |
| `file_claim_success_total` | Worker nhận file thành công? | Thấp bất thường dù còn READY |
| `file_claim_conflict_total` | Nhiều workers cùng tranh file? | Race, polling quá dày |
| `lease_renew_failure_total` | Worker mất quyền khi đang xử lý? | Network/DB issue, stale owner |
| `stale_worker_write_rejected_total` | Sink có từ chối epoch cũ? | Split brain đang xảy ra |
| `file_processing_duration` | File nào bị chậm? | Tail latency/file size skew |
| `file_bytes_processed_total` | Throughput đọc thực? | I/O bottleneck |
| `worker_db_commit_latency` | Sink đã bão hòa? | Pool wait, lock contention |
| `file_completed_count` | Bao nhiêu logical files verified? | Không khớp với output |
| `duplicate_business_key_total` | Replay/overlap có xảy ra? | Duplicate khác value phải alert |
| `manifest_snapshot_mismatch` | File nguồn có bị sửa? | Bất kỳ mismatch |
| `restart_recovery_lag` | Sau lỗi bao lâu batch hội tụ? | Vượt recovery SLA |

**Không dùng `fileId`/source path của mỗi file làm time-series tag** khi có hàng triệu files: cardinality sẽ bùng nổ. Ghi file identity vào log/tracing và manifest; metrics tổng hợp theo batch, worker, loại lỗi, file size bucket và source class.

### Phân biệt trạng thái có thật

~~~text
FILE LOCK HELD     = một process đang giữ OS lock (nếu FS bảo đảm)
FILE CLAIMED       = DB manifest cấp quyền theo epoch
FILE PROCESSED     = worker đã đi qua dữ liệu (có thể rollback)
FILE DB COMMITTED  = business data được commit
FILE COMPLETED     = manifest xác nhận outcome theo policy
FILE PUBLISHED     = downstream được phép đọc version kết quả
~~~

Các trạng thái này **không đồng nghĩa**. Một process cầm lock có thể chưa ghi item nào; một file đã DB COMMITTED vẫn có thể chưa COMPLETED vì manager mất reply; một file COMPLETED chưa chắc được downstream phép đọc nếu có publication barrier toàn batch.

## 28. Kiểm thử FileLock bắt buộc dùng hai process thật

Một unit test với hai thread cùng JVM có thể gặp `OverlappingFileLockException` nhưng **không chứng minh** khóa hoạt động đúng giữa hai JVM. Để kiểm tra file lock, cần tạo **hai process riêng biệt** cùng truy cập một sidecar path thực tế.

### Một chương trình probe tối giản

~~~java
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.nio.channels.FileChannel;
import java.nio.channels.FileLock;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;

public final class FileLockProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException("Require sidecar lock path");
        }

        try (FileChannel channel = FileChannel.open(
                Path.of(args[0]),
                StandardOpenOption.CREATE,
                StandardOpenOption.WRITE)) {

            FileLock lock = channel.tryLock();
            if (lock == null) {
                System.out.println("BUSY");
                System.exit(10);
            }

            try (FileLock ignored = lock) {
                System.out.println("ACQUIRED");
                System.out.flush();
                // Giữ lock tới khi test runner gửi newline
                // hoặc giết process nhằm mô phỏng crash.
                new BufferedReader(new InputStreamReader(System.in))
                        .readLine();
            }
        }
    }
}
~~~

Với **hai process riêng** và cùng sidecar path:

~~~text
Process A khởi động, in ACQUIRED, vẫn giữ stdin mở.
Process B khởi động, kỳ vọng BUSY, exit code 10.
Test runner kill process A.
Process C khởi động, kỳ vọng ACQUIRED.

Sau khi A chết, file .lck có thể vẫn tồn tại,
nhưng OS lock đã được giải phóng.
~~~

**Chi tiết test runner:** khi dùng `ProcessBuilder`, phải giữ input stream của A mở nếu muốn `readLine()` tiếp tục chờ; nếu đóng stdin, A có thể thoát sớm và test tạo false positive. Dùng cơ chế barrier/handshake để đợi chuỗi `ACQUIRED` thay vì `Thread.sleep` đoán thời gian; kill/terminate thật khi cần test crash. Chạy B trên **cùng máy** trước, sau đó trên **hai host/pod khác nhau** nếu production dùng shared NFS/SMB/CSI mount.

**Lưu ý:** `System.exit(10)` trong code probe làm kết thúc process thử nghiệm, không nên đặt trong thư viện quản lý lock của ứng dụng Spring Batch. Trong production, trả trạng thái hoặc ném exception theo chính sách.

## 29. Kiểm thử Spring Batch với hai JobExecution hoặc hai manager

Một bài kiểm thử chỉ chạy **một JobInstance trên một JVM** là chưa đủ nếu môi trường thật có hai manager cùng quét inbox. Dùng DB/JobRepository và shared storage giống production:

1. Tạo manifest với file ID/version bất biến và business records có source key duy nhất.
2. Chạy **hai manager JVM** hoặc hai JobExecution theo cấu hình được phép cùng lúc, cố để cả hai nhìn thấy một file READY.
3. Với DB claim, xác minh **chỉ một UPDATE claim trả row** tại một thời điểm.
4. Với sidecar `FileLock`, xác minh **chỉ một process có ACQUIRED** và worker còn lại không ghi dữ liệu.
5. Kiểm tra claim loser **không đánh dấu file COMPLETED** và có thể xử lý file khác hoặc retry theo policy.
6. Tạo lỗi sau một số chunk DB đã commit nhưng trước manifest COMPLETED.
7. Khởi động lại bằng JobInstance và input snapshot phù hợp; kiểm tra writer không nhân đôi effect.
8. Đối soát input keys, output keys, giá trị, StepExecution status và manifest state sau recovery.

### Không tự coi lock-busy là “đã xong”

Nếu worker nhận file trong `ExecutionContext` rồi `tryLock()` trả busy, không nên **trả COMPLETED** một cách im lặng cho StepExecution như thể nó đã xử lý file. Cần fail/đặt trạng thái chờ, requeue hoặc giao công việc khác theo **scheduling contract**, và chỉ đánh dấu completed sau khi đã có bằng chứng output. Quyết định retry/busy phải được phân biệt với **bad file** hay exception dữ liệu nghiệp vụ.

### Spring Batch partition name và restart

Trong local/remote partitioning, danh tính partition cần ổn định qua restart, ví dụ `file-0042` gắn đúng source version. **Một StepExecution COMPLETED có thể được framework bỏ qua khi restart** tùy job/step contract. Do đó không thay đổi tùy tiện danh sách file/partition mapping trong cùng JobInstance, và không dùng JobParameters mới để “chạy lại” file đã có output nếu không có idempotency/recovery rõ ràng.

## 30. Test crash, lease expiry và stale worker

| Kịch bản | Failure injection | Điều phải chứng minh |
| --- | --- | --- |
| A. Hai process cùng lock | Cho A giữ lock, B tryLock cùng sidecar | Chỉ một ACQUIRED, B không xử lý |
| B. Process chết khi giữ OS lock | Kill -9/TerminateProcess A | B có thể nhận lock sau khi OS phục hồi, `.lck` không cần xóa |
| C. Input producer ghi dở | Giữ producer còn mở `.part` | Worker không đọc file chưa vào ready manifest |
| D. Chuyển file sang processing rồi crash | Kill sau rename, trước DB write | Có recovery cho processing orphan, không mất file |
| E. Crash sau vài chunk commit | Kill worker trước file completion | Restart/replay không nhân đôi business effects |
| F. Lease hết khi worker A pause | Dừng heartbeat A, B claim epoch mới | A không được ghi sau khi trở lại |
| G. Hai writers có epoch khác nhau | Cố ghi từ A(epoch 7), B(epoch 8) | Sink từ chối epoch cũ theo fencing contract |
| H. Mất network DB manifest | Worker không renew được lease | Worker không tiếp tục commit vô hạn khi quyền chưa rõ |
| I. File bị thay nội dung | Sửa source sau khi claim | Checksum/version mismatch khiến job fail/reconcile |
| J. Hai managers + shared reply queue | Chạy concurrent remote partitioning | Không ghép nhầm completion hoặc dispatch trùng file |
| K. Mất reply sau business commit | Chặn broker reply, cho replay | Business output vẫn idempotent |
| L. Output file tạm còn dở | Kill giữa write/rename | Downstream không đọc partial result |

**Điểm khó nhất:** kiểm thử stale worker không chỉ cần giả lập **worker A bị tạm dừng**, mà còn phải chứng minh A **bị sink từ chối ghi** sau khi B đã nhận epoch mới. Một flag `stale` trong log không ngăn A áp dụng business effect.

### Sử dụng latch cho các test cùng JVM

Trong kiểm thử business writer/claim code, có thể dùng `CountDownLatch` để tạo một race:

~~~java
final class OwnerRaceProbe {
    final CountDownLatch ownerACheckedLease =
            new CountDownLatch(1);
    final CountDownLatch allowOwnerAWrite =
            new CountDownLatch(1);

    void pauseAfterLeaseCheck() throws InterruptedException {
        ownerACheckedLease.countDown();
        if (!allowOwnerAWrite.await(15, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Test timeout");
        }
    }
}
~~~

Một test **âm** cố ý kiểm lease trước write bằng SELECT không khóa, dừng A ở khoảng giữa, cho B claim epoch mới, rồi mở A. Nếu code sai, A vẫn có thể commit. Một test **dương** sử dụng fencing atomic (ví dụ locking manifest row trong cùng transaction ghi DB) phải từ chối A. **Không dùng `Thread.sleep` làm bằng chứng race chắc chắn xảy ra**; mọi latch cần timeout và giải phóng trong `finally` để tránh treo CI.

### Đừng nhầm crash test với “delete volume”

Restart broker/process/container **trên cùng storage** khác hoàn toàn việc xóa volume rồi tạo lại một môi trường sạch. Nếu bạn xóa luôn input/lock/manifest data, kết quả không còn phản ánh semantics crash/restart đã đặt ra.

## 31. Kiểm thử I/O, checksum và filesystem thực tế

Trong bài học file scaling, một phần quan trọng là **môi trường storage**, không chỉ Spring Batch code. Bảng kiểm chứng nên bao gồm:

| Nền tảng | Thử nghiệm | Kết quả cần ghi lại |
| --- | --- | --- |
| Local Linux | Hai process `tryLock` cùng path, kill owner | Busy/lock release, inode và quyền |
| Windows | Hai Java processes cùng sidecar, đóng channel | Lock conflicts, permission/access behavior |
| NFS | Hai hosts/pods, network disconnect, reconnect/failover | Semantics lock lease/recovery thực tế |
| SMB | Hai hosts/containers, server reconnect | Share mode/oplock behavior, visibility |
| Kubernetes CSI | Hai pods mount cùng volume | Lock/path consistency, pod reschedule |
| Object storage | Concurrent conditional claim/ETag, version read | CAS semantics, version mismatch và retry |

**Không đưa một kết quả từ local temp directory lên production NFS rồi giả định tương đương.** Với các quyết định ảnh hưởng tiền hoặc dữ liệu khách hàng, cần test trên **đúng loại FS, mount options và topology** đang dùng.

### Kiểm tra integrity trước và sau xử lý

Nếu có manifest checksum, xác minh **cùng phiên bản input** sau khi producer bàn giao và khi worker đọc xong. Không phát hành `COMPLETED` khi checksum/record count không khớp. Tuy nhiên, việc hash lại file rất lớn cũng tạo I/O overhead: có thể dùng checksum do producer cung cấp trong protocol trusted và sample/full verification theo SLA, nhưng **không bỏ qua source-version consistency**.

## 32. Runbook: file bị kẹt PROCESSING hoặc nhiều worker xử lý trùng

Khi dashboard cho thấy một file PROCESSING quá lâu hoặc duplicate output:

1. **Khoanh vùng:** batchKey, fileId, sourceVersion, partitionKey, worker owner, claim epoch và thời điểm claim.
2. **Xác minh input:** producer đã bàn giao immutable file chưa, checksum/size/manifest có khớp không?
3. **Tìm worker active:** container/JVM nào còn xử lý, JobExecution/StepExecution tương ứng đang ở trạng thái nào, có worker cũ mất heartbeat nhưng chưa chết không?
4. **Kiểm tra lock:** nếu dùng sidecar OS lock, file `.lck` **tồn tại không có nghĩa đang bị lock**; kiểm tra qua protocol/process thực. Không xóa sidecar để “giải phóng”.
5. **Kiểm tra manifest/lease:** `claimed_by`, `lease_epoch`, `lease_until` và lần heartbeat cuối; có epoch mới hay stale worker writes bị từ chối không?
6. **Kiểm tra business sink:** output đã commit bao nhiêu record/key, có conflict khác payload/rule version, checkpoint có tương thích không?
7. **Kiểm tra broker/manager:** với remote partitioning, request/reply có thiếu, duplicate hoặc đến muộn không? Timeout không chứng minh worker đã chết.
8. **Ngăn hai owner tiếp tục ghi:** dừng/quiesce owner cũ hoặc dùng sink fencing đã được kiểm chứng, hạn chế claim mới nếu outcome chưa rõ.
9. **Chọn recovery:** retry/restart cùng JobInstance/snapshot nếu hợp lệ, hoặc correction batch theo policy; không tự đổi file version.
10. **Đối soát:** source keys, output values, manifest state, StepExecution và side effects. Chỉ mark COMPLETED sau khi đúng.
11. **Đóng incident:** ghi nguyên nhân, storage semantics, lock contention, lost ownership, thời gian recovery và bài kiểm thử cần bổ sung.

**Không tự xóa toàn bộ `.lck`, không di chuyển mọi file PROCESSING về READY, không DELETE business output và không sửa trực tiếp JobRepository thành COMPLETED** khi chưa xác định tác động đã commit. Những thao tác đó có thể làm tăng duplicate hoặc che giấu mất dữ liệu.

## 33. Những lỗi thiết kế thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Hai JVM xử lý cùng file | Chỉ dùng `synchronized`/check exists | Dùng OS lock hoặc DB claim chung giữa processes |
| Process chết, file mãi không được nhận | Dùng `CREATE_NEW` rồi giữ `.lock` vĩnh viễn | OS lock với sidecar bền hoặc lease/claim có recovery |
| Hai process cùng giữ “lock” | Xóa sidecar khi process khác vẫn giữ inode cũ | Không unlink sidecar; dùng cùng path và OS lock đúng |
| Khi scan inbox, reader thấy file dở | Producer viết thẳng vào ready path | Immutable publish handoff `.part` → ready |
| Restart đọc khác nội dung | File bị sửa/append sau checkpoint | Snapshot/version/checksum và manifest ổn định |
| Job COMPLETED nhưng DB duplicate | FileLock không ngăn replay sau crash | Business-key idempotency và reconciliation |
| Lease vừa hết mà worker cũ còn ghi | Không có fencing tại sink | Epoch-based fencing hoặc ownership check atomic với write |
| NFS test khác local | Tin vào POSIX lock semantics chung | Test đúng FS/protocol/mount/failover |
| Nhiều workers cùng append output | Output path shared, chỉ khóa input | Per-worker outputs + merge/publish manifest |
| Lock-busy bị coi là file đã xử lý | Worker bỏ qua file và trả COMPLETED | Requeue/retry, chỉ mark done khi có outcome |
| JobRepository trạng thái lệch DB | Hai resource không cùng transaction | Idempotency, checkpoint and reconciliation |
| Claim contention cực cao | Mọi worker scan cùng thứ tự mỗi 100ms | DB assignment/partition map, bounded backoff |
| Một file rất lớn làm chậm cả job | Không chia file skew | Pre-shard logical records hoặc partition theo index |
| File cùng tên từ hai tenant bị gộp | Lock/manifest key thiếu namespace | Stable tenant-scoped identity |
| Object storage “rename” bị mất dữ liệu | Dùng copy+delete như POSIX atomic move | Versioned manifest + conditional publish |

## 34. Bài thực hành tổng hợp

**Bài thực hành:** nhập 1 triệu giao dịch từ 100 immutable CSV files, mỗi file có `fileId` và `sourceVersion`. Chạy bốn worker JVM trên cùng host để thử `FileLock`, sau đó hai manager ở hai node/pod để thử **DB claim + lease/epoch**. Output là PostgreSQL có unique business key, downstream chỉ tiêu thụ batch đã đối soát.

Các lượt thực hành:

1. **Baseline:** chạy một worker, đo thời gian import và xác nhận output đúng từng business key.
2. **Hai JVM giành lock:** cùng trỏ vào một sidecar; một process `ACQUIRED`, process kia `BUSY`.
3. **Crash khi giữ lock:** kill owner; worker khác tiếp nhận sau khi lock được giải phóng, không xóa file `.lck`.
4. **Handoff:** cho producer giữ `.part` chưa đóng; worker không được đọc. Sau ready publish, worker mới nhận immutable file.
5. **DB claim cạnh tranh:** hai worker chạy UPDATE cùng `file_id`; một claim thắng, loser không tạo output.
6. **Lease timeout:** pause owner epoch 7, cho owner mới lấy epoch 8; epoch 7 bị từ chối ở sink khi tiếp tục.
7. **Crash giữa các chunk:** worker đã commit một phần rồi chết; restart/checkpoint và idempotency không tạo duplicate.
8. **Output publication:** worker ghi part riêng; file/result cuối chỉ được công bố khi checksum/record coverage đạt.
9. **NFS/CSI negative test:** chạy hai pods với shared FS; ghi rõ lock semantics hoặc chuyển sang DB ownership nếu không đáng tin.
10. **Load test:** so sánh worker count 1/2/4/8, chunk size, IOPS, lock contention, DB pool, file skew và recovery duration.

### Checklist trước production

- [ ] Đã xác định thực sự có cạnh tranh **giữa threads, JVMs, pods hay managers**.
- [ ] Input file được producer bàn giao **bất biến**; có manifest ID/version/checksum.
- [ ] Không dùng `Files.exists` rồi xử lý như một khóa nguyên tử.
- [ ] Nếu dùng Java `FileLock`, tất cả process cùng sidecar path, thử `tryLock` và release đúng lifecycle.
- [ ] Không xóa `.lck` để release; file tồn tại không đồng nghĩa OS lock đang bị giữ.
- [ ] Có quy tắc khi lock busy, không đánh dấu StepExecution/file hoàn tất giả.
- [ ] NFS/SMB/CSI hoặc object storage đã được test **đúng topology** về lock, rename, failover.
- [ ] Nếu có nhiều manager/node, sử dụng manifest claim/lease và **fencing thực thi tại sink** khi cần.
- [ ] Không coi lease expired là bằng chứng worker cũ đã chết; có protocol ngăn stale writes.
- [ ] Worker `@StepScope` dùng đúng file identity; `ExecutionContext`/partition map ổn định khi restart.
- [ ] Writer idempotent theo business key, phát hiện duplicate **khác nội dung**.
- [ ] File output được ghi vào part tạm/riêng, có verify và publication barrier.
- [ ] Có đối soát input/output/manifest/JobRepository, không chỉ kiểm queue/file count.
- [ ] Có test hai **process thật**, crash, lease expiry, stale worker, concurrent claim và source mutation.
- [ ] Có metric lock contention, claim conflicts, lease failures, output duplicates và recovery latency.
- [ ] Có runbook giữ nguyên bằng chứng trước khi replay, xóa file hay sửa metadata.

**Ghi nhớ:** khi nhiều process cùng xử lý file, **khóa chỉ là một lớp điều phối**. `FileChannel.tryLock()` hữu ích với filesystem hỗ trợ và mọi process đều hợp tác; **atomic rename** giúp bàn giao/claim đơn giản trong một phạm vi được bảo đảm; **manifest claim + lease/fencing** phù hợp hơn cho nhiều node, network partitions và failover nghiêm ngặt. Để Spring Batch xử lý đúng sau crash hoặc restart, luôn kết hợp **input snapshot bất biến, JobRepository/ExecutionContext, idempotent writer, đối soát và publication có kiểm soát**, thay vì giả định giữ được file lock là đã đạt exactly-once.
