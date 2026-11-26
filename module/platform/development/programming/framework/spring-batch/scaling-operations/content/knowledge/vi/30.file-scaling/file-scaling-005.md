# Atomic move sau khi xử lý

Một pipeline Spring Batch xử lý hàng nghìn file có thể làm đúng tất cả phép tính nhưng vẫn gặp sự cố khi **đưa kết quả ra cho downstream** hoặc **chuyển file nguồn vào archive**. Ví dụ, worker import thành công 100.000 giao dịch rồi chết ngay trước khi di chuyển file CSV; ở lần chạy tiếp theo, scheduler nhìn thấy file vẫn nằm trong inbox và có thể nhập lại toàn bộ. Trường hợp ngược lại cũng nguy hiểm: worker di chuyển file sang archive trước khi DB commit, sau đó transaction rollback; hệ thống không còn nhìn thấy file trong inbox mặc dù dữ liệu chưa được lưu.

**Atomic move sau khi xử lý** là một kỹ thuật giúp thay đổi tên hoặc vị trí file theo một bước mà observer không nhìn thấy trạng thái “file mới chỉ được chuyển một nửa”, **khi filesystem thực sự hỗ trợ tính nguyên tử cho thao tác đó**. Nhưng một thao tác rename nguyên tử **không đồng nghĩa** với transaction ACID bao phủ Spring Batch, database, broker và các file khác.

Bài học thuộc chương **File scaling** của module **SPRING_BATCH_SCALING_OPERATIONS**. Module tập trung mở rộng Spring Batch cho workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và những mô hình xử lý phân tán phù hợp; đo nút thắt, bảo đảm thread safety, retry/restart, vận hành job và chọn kiến trúc theo tài nguyên thực tế. Nội dung ở đây tập trung vào **Java NIO `Files.move(..., ATOMIC_MOVE)`, publication pattern, lưu trữ file nguồn sau khi xử lý, ranh giới commit, race giữa nhiều process, recovery và kiểm thử filesystem thực tế**.

> **Nguyên tắc cốt lõi:** atomic move giúp một file chuyển từ tên/đường dẫn cũ sang tên/đường dẫn mới **một cách nguyên tử ở cấp filesystem**. Nó **không rollback** những row đã ghi vào database và không tự ngăn một worker khác xử lý cùng logical file. Vì thế phải kết hợp **input bất biến, ownership/claim, idempotent business writer, recovery state và reconciliation**.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Hiểu atomic rename/move giải quyết vấn đề **visibility** nào và không giải quyết vấn đề **durability** hoặc global commit nào.
2. Phân biệt hai luồng **producer publish file kết quả** và **consumer archive file nguồn sau xử lý**.
3. Sử dụng `Files.move(source, target, StandardCopyOption.ATOMIC_MOVE)` đúng điều kiện, xử lý `AtomicMoveNotSupportedException` mà không đánh tráo semantics.
4. Hiểu vì sao chuyển file **giữa hai filesystem hoặc sang object storage** thường không có cùng atomic move semantics.
5. Thiết kế temp file, checksum, close/flush, atomic rename và manifest để downstream không đọc bản ghi dở.
6. Xác định các khoảng lỗi giữa **DB commit, JobRepository checkpoint, file move, manifest COMPLETED và broker reply**.
7. Xây tasklet archive **idempotent sau crash/restart**, kể cả khi nguồn đã biến mất nhưng đích tồn tại.
8. Phối hợp nhiều JVM/process bằng stable file identity, claim/lease/fencing; không dùng `Files.exists` làm khóa.
9. Kiểm thử failure injection, atomic visibility, process crash, xử lý trùng và khôi phục trên đúng filesystem của production.
10. Đo throughput, archive backlog, move latency, duplicate/unknown outcome và chọn giải pháp phù hợp khối lượng file thực tế.

**Tình huống xuyên suốt:** mỗi đêm, Spring Batch nhập 10.000 file CSV được producer bàn giao vào `/data/ready/`, mỗi file có `fileId` và checksum. Nhiều worker xử lý những file khác nhau rồi đưa chúng sang `/data/archive/`. Song song, một bước khác tổng hợp báo cáo CSV vào `/data/staging/` và công bố tại `/data/published/`. Hệ thống phải chịu được worker bị kill trước/sau thao tác move, retry cùng file, rolling deploy với hai manager, và sự khác biệt giữa local disk, NFS/SMB và object storage.

## 2. “Atomic” ở đây chính xác có nghĩa gì?

Về trực giác, một atomic move trên filesystem có semantics phù hợp khiến observer nhìn thấy:

~~~text
Trước move thành công: /staging/result.part tồn tại
                       /published/result.csv chưa có

Sau move thành công:   /staging/result.part không còn dưới tên cũ
                       /published/result.csv xuất hiện
~~~

Trong phạm vi được hệ thống tệp bảo đảm, observer không thấy quá trình **copy dở 35%** từ `staging` sang `published` khi thao tác thực chất là **rename nguyên tử**.

~~~mermaid
flowchart LR
    W["Writer tạo file .part"] --> V["Close + validate checksum/count"]
    V --> M["Atomic move"]
    M --> P[("Tên published xuất hiện")]
    P --> D["Downstream mở file hoàn chỉnh"]
~~~

**Ba thuộc tính khác nhau:**

| Thuộc tính | Câu hỏi | Atomic move bảo đảm? |
| --- | --- | --- |
| **Atomic visibility** | Downstream có thấy một file chỉ copy được một phần? | Có, **nếu filesystem hỗ trợ thao tác atomic move trong trường hợp cụ thể** |
| **Crash durability** | Sau khi OS/broker/storage mất điện, rename và bytes chắc chắn còn? | **Không mặc định**; phụ thuộc flush/fsync, journal, thiết bị và filesystem |
| **Cross-resource atomicity** | Rename và business DB COMMIT cùng thành công hoặc rollback? | **Không**; là hai tài nguyên/giao dịch khác nhau |
| **Exclusive ownership** | Có bảo đảm chỉ một worker được quyền thực hiện move? | **Không**; cần claim/lock/định danh đích |
| **Exactly-once effect** | Retry import cùng file có ghi trùng record? | **Không**; cần business idempotency |

Không nên diễn giải “file đã được rename” thành “tất cả side effect và metadata liên quan đều đã commit”.

## 3. Hai ứng dụng cần phân biệt: publish và archive

**A. Publish kết quả:** worker tạo `report.csv.part`, validate dữ liệu, rồi atomic move thành `report.csv`. Mục tiêu là **downstream không nhìn thấy file đang ghi**.

**B. Archive nguồn:** job đã xử lý input `ready/input-42.csv` và chuyển sang `archive/input-42.csv`. Mục tiêu là **đánh dấu file không còn nằm trong tập sẵn sàng xử lý** và giúp lưu bản gốc để audit/replay.

| Chiều di chuyển | Điều kiện trước move | Ý nghĩa sau move | Rủi ro chính |
| --- | --- | --- | --- |
| `staging/output.part → published/output.csv` | Output đầy đủ, đóng file, verify version/checksum | Bản output có thể được downstream nhìn thấy | Publish trước validation; overwrite kết quả khác; crash sau rename trước manifest |
| `ready/input.csv → archive/input.csv` | Business processing đã commit và đối soát per-file đạt | Không còn input dưới tên ready | Crash sau DB commit trước archive; DB rollback sau archive; xử lý trùng |
| `incoming/file.part → ready/file.csv` | Producer hoàn tất và xác nhận input | Worker mới được phép đọc immutable file | Producer mở lại/chỉnh file sau publish |
| `ready/file.csv → processing/file.csv` | Worker claim ownership | Dấu hiệu dispatch tạm | Crash ở processing; stale worker; không chứng minh đã xử lý |

Đặc biệt, `ready → processing` là **claim/bàn giao trước xử lý**, khác với yêu cầu **atomic move sau khi xử lý**. Hai bước không nên bị gộp trong tài liệu vận hành vì state recovery và rủi ro business commit khác nhau.

## 4. Java NIO: Files.move và ATOMIC_MOVE

Trong Java 17+, dạng cơ bản:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

Path source = Path.of("/data/staging/report-42.csv.part");
Path target = Path.of("/data/published/report-42.csv");

Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
~~~

`StandardCopyOption.ATOMIC_MOVE` yêu cầu file provider thực hiện **atomic filesystem move**. Nếu không thể thực hiện theo semantics ấy, `Files.move` có thể ném `AtomicMoveNotSupportedException`; các lỗi I/O, permission, target hoặc khóa file khác có thể là `IOException`/exception liên quan.

**Ba lưu ý quan trọng theo hợp đồng Java NIO:**

1. Nếu cung cấp `ATOMIC_MOVE`, **các copy options khác bị bỏ qua** cho thao tác atomic move; đừng giả định `REPLACE_EXISTING` kết hợp với `ATOMIC_MOVE` bảo đảm overwrite/compare-and-swap như bạn mong muốn.
2. **Khi target đã tồn tại, hành vi phụ thuộc implementation/provider**: có thể thay thế target hoặc thất bại. Không xây logic no-overwrite/claim chỉ từ việc target tồn tại.
3. Ngay cả với move **không atomic**, khi ném lỗi giữa chừng thì trạng thái source/target có thể không xác định. Phải kiểm tra lại filesystem rồi đối soát, không mặc định source còn nguyên.

### Catch lỗi đúng ý nghĩa

~~~java
try {
    Files.move(source, target, StandardCopyOption.ATOMIC_MOVE);
} catch (AtomicMoveNotSupportedException unsupported) {
    // Tính nguyên tử là một phần của contract:
    // FAIL và chuyển sang workflow copy/verify/publish
    // được thiết kế riêng, không silently degrade.
    throw new IllegalStateException(
            "Atomic move is required for this filesystem", unsupported);
}
~~~

Một fallback phổ biến nhưng **nguy hiểm** là catch `AtomicMoveNotSupportedException` rồi tự động `Files.copy(source, finalTarget)`. Trong thời gian copy, downstream có thể mở `finalTarget` và đọc được **file chưa hoàn chỉnh**. Nếu bắt buộc chạy cross-filesystem, cần **copy vào file tạm tại filesystem đích**, xác minh rồi **atomic rename tại chính filesystem đích** hoặc publish qua manifest/DB có kiểm soát.

## 5. Vì sao phải cùng filesystem và hiểu FileStore?

Rename nguyên tử trên nhiều filesystem POSIX thường là thao tác thay đổi directory entries trong **một filesystem**. Nếu `source` và `target` nằm trên hai mount/filesystem khác nhau, thay đổi đó thường không thể thực hiện thành một atomic rename; Java có thể ném `AtomicMoveNotSupportedException`.

~~~text
Trường hợp thường khả thi (nếu provider hỗ trợ):
  /mnt/data/staging/report.part
  /mnt/data/published/report.csv

Trường hợp không thể mặc định atomic:
  /mnt/fast-ssd/staging/report.part
  /mnt/archive-hdd/published/report.csv
~~~

Có thể thực hiện một **preflight**, nhưng nó không thay thế thử move thực tế:

~~~java
FileStore srcStore = Files.getFileStore(source);
FileStore dstStore = Files.getFileStore(target.getParent());

if (!srcStore.equals(dstStore)) {
    // Gợi ý nhiều filesystem khác nhau.
    // Tùy provider, kết quả này chưa phải phép kiểm duy nhất.
}
~~~

`target.getParent()` phải **tồn tại** và có permission thích hợp. `FileStore.equals` là một chỉ báo provider-level, không phải bằng chứng đầy đủ rằng atomic move sẽ được hỗ trợ. Ngoài việc cùng mount, còn cần xem filesystem type, rename semantics, network server, ACL và những hạn chế của provider.

## 6. Publication pattern: ghi tạm, kiểm tra rồi mới move

Một pipeline an toàn khi **tạo output file**:

~~~text
1. Tạo tên output logic/version ổn định.
2. Mỗi worker ghi vào một temp path duy nhất, thuộc cùng filesystem đích.
3. Đóng writer/stream; flush dữ liệu theo durability policy.
4. Kiểm chứng file: format, checksum, record count, business totals.
5. Đảm bảo không còn writer cũ có quyền sửa temp.
6. Atomic move từ temp sang tên public/final.
7. Đối soát kết quả move và cập nhật publication manifest.
8. Downstream chỉ đọc file/version được công bố hợp lệ.
~~~

~~~mermaid
stateDiagram-v2
    [*] --> WRITING
    WRITING --> SEALED: close and finalize
    SEALED --> VALIDATED: checksum and business validation
    VALIDATED --> PUBLISHED: atomic move + policy
    VALIDATED --> FAILED: verification error
    PUBLISHED --> [*]
~~~

Đây là state machine ứng dụng, **không phải enum mặc định của Spring Batch**. Trong hệ thống có hai bước commit (move rồi cập nhật DB manifest), cần state trung gian và khôi phục khi một bước đã thành công còn bước khác chưa, thay vì coi toàn bộ thao tác là một transaction.

## 7. Ghi temp output theo tên riêng từng lần thử

Giả sử hai worker cùng cố tạo `report.csv.part`. Dù sau cùng chỉ một người được publish, họ đã có thể ghi đè/trộn nội dung temp. Hãy đặt **tên temp duy nhất cho từng attempt/owner**, đồng thời có **logical final identity cố định**.

~~~text
Logical final:
  /data/published/run-845/part-0007.csv

Worker A attempt 1:
  /data/staging/run-845/part-0007.worker-A.attempt-1.tmp

Worker B attempt 2:
  /data/staging/run-845/part-0007.worker-B.attempt-2.tmp
~~~

**Tách hai loại khóa:**

- `attempt temp path` khác nhau để worker không đè nhau khi đang ghi.
- `logical output key` giống nhau qua retry để hệ thống biết hai attempt cạnh tranh cho **cùng một kết quả nghiệp vụ**.

Chỉ có temp path duy nhất **không tự ngăn hai process cùng overwrite logical final**. Trước publish cần ownership/claim hoặc giao thức chọn winner và kiểm tra idempotency nội dung.

## 8. Flush, close, fsync và atomic rename không đồng nghĩa

Khi `BufferedWriter.close()` trả về, bộ đệm ở lớp Java đã được đẩy theo semantics stream, nhưng không mặc định tất cả data và directory entries đã tới **stable storage** nếu thiết bị hoặc OS bất ngờ mất điện.

Với local filesystem có hỗ trợ, một trình tự **durability-aware** có thể gồm:

1. Ghi file tạm qua channel/stream.
2. Dùng `FileChannel.force(true)` để yêu cầu đẩy data và metadata liên quan xuống thiết bị theo contract của provider.
3. Đóng/nhả writer và xác minh checksum/record count.
4. `Files.move(temp, target, ATOMIC_MOVE)`.
5. Khi yêu cầu power-loss durability mạnh, cân nhắc đồng bộ metadata **directory** theo API/hệ điều hành hỗ trợ.

Ví dụ về force khi ghi bằng `FileChannel`:

~~~java
try (FileChannel channel = FileChannel.open(
        temporary,
        StandardOpenOption.CREATE_NEW,
        StandardOpenOption.WRITE)) {
    ByteBuffer bytes = StandardCharsets.UTF_8.encode(content);
    while (bytes.hasRemaining()) {
        channel.write(bytes);
    }
    channel.force(true);
}
Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE);
~~~

**Giới hạn quan trọng:** `FileChannel.force(true)` không phải cam kết phổ quát cho network filesystems, object storage hoặc mọi thiết bị. Mở và `force` một **directory** bằng Java có thể không được provider hỗ trợ; không giả định một đoạn Java portable duy nhất bảo đảm cả directory fsync. Nếu yêu cầu durability sau mất điện là bắt buộc, cần tài liệu/kiểm thử cụ thể cho filesystem và OS.

**Phân biệt rõ:** atomic rename bảo đảm **visibility của thay đổi tên** theo contract; `force/fsync` hướng tới **độ bền sau crash**. Dùng một trong hai không thay thế được cái còn lại.

## 9. Copy cross-filesystem không được publish thẳng final path

Khi input và output nằm ở hai filesystem khác nhau, thường phải copy. Nếu copy thẳng vào tên final:

~~~text
/mnt/ssd/source.csv --copy 10%--> /mnt/archive/report.csv
                                 downstream đã thấy tên final
                                 và có thể đọc dữ liệu thiếu
~~~

Một workflow an toàn hơn:

~~~text
Filesystem nguồn:
  /mnt/ssd/source.csv

Filesystem đích:
  /mnt/archive/staging/report.csv.tmp
     <- copy bytes
     <- flush/close
     <- verify checksum/count
  /mnt/archive/published/report.csv
     <- ATOMIC_MOVE nội bộ filesystem đích (nếu hỗ trợ)
~~~

Chỉ **sau khi target đã được xác minh và publish**, nguồn mới được xem xét xóa/archive theo retention policy. Nếu move thất bại do cross-device, không xóa nguồn rồi mong target đủ dữ liệu. Nếu nguồn là dữ liệu cần audit hoặc phục vụ restart, **không xóa ngay** trước khi kết quả business đã bền vững và đối soát.

### Không mặc định là atomic khi dùng hai bước copy + rename

Copy + verify + rename chỉ có thể mang lại **atomic visibility ở đích** cho một file, **không phải atomic move giữa hai filesystem**. Có thể tồn tại đồng thời source và target. Nếu việc xóa source thất bại, phải khôi phục theo manifest trạng thái; không giải thích đó là lỗi nghiêm trọng dẫn tới việc ghi đè output đã công bố.

## 10. Thư mục published không phải lúc nào cũng là “đã xong cả batch”

Khi một job chạy nhiều partition, mỗi partition có thể atomic publish một file riêng:

~~~text
T0: part-0001.csv PUBLISHED
T1: part-0002.csv PUBLISHED
T2: part-0003.csv chưa có do worker lỗi
~~~

Downstream quét `published/*.csv` ngay ở T1 sẽ thấy **một tập kết quả chưa đầy đủ** dù mỗi file riêng lẻ đều atomic. Khi nghiệp vụ yêu cầu **hoặc thấy toàn bộ batch hoặc không thấy batch**, cần **publication barrier ở cấp batch**.

~~~mermaid
flowchart TD
    P0["Worker P0 → part-0001 ready"] --> V["Validation toàn batch"]
    P1["Worker P1 → part-0002 ready"] --> V
    P2["Worker P2 → part-0003 ready"] --> V
    V --> Q{"Đủ coverage + checksum + rules?"}
    Q -- "Chưa" --> H["Giữ trạng thái UNPUBLISHED"]
    Q -- "Đạt" --> M["Commit manifest PUBLISHED"]
    M --> D["Downstream đọc version trong manifest"]
~~~

Các worker có thể ghi file final/versioned sớm nhưng downstream **chỉ dùng các file được manifest PUBLISHED chỉ tới**. Việc công bố một cờ manifest trong DB transaction hoặc một **manifest pointer/version** có compare-and-swap phù hợp có thể tạo **atomic logical visibility của cả bộ file**; không yêu cầu rename hàng nghìn file cùng lúc.

**Không có atomic rename một lần cho cả tập file ở nhiều filesystem.** Nếu dùng rename cả thư mục trên cùng filesystem, cũng phải kiểm tra nguyên tắc target directory, OS/provider semantics, state manifest và quyền writer, không tự suy ra nó là global commit với business DB.

## 11. Archive file đầu vào **sau khi xử lý**: thứ tự nào an toàn?

Trong file import job, một yêu cầu phổ biến là “đọc và ghi DB xong thì chuyển file sang archive”. Hãy phân biệt **process đã đi qua dòng cuối** và **business transaction đã commit/đối soát xong**.

~~~text
Sai:
  worker mở input
  đọc dòng cuối
  move input -> archive
  transaction DB còn đang mở
  DB COMMIT thất bại

Kết quả: input không còn trong ready, output có thể thiếu.
~~~

Thứ tự gợi ý cho một file:

~~~text
1. Producer đã bàn giao immutable input.
2. Worker được cấp ownership hợp lệ.
3. Spring Batch đọc/transform/write các chunk.
4. Chunk cuối COMMIT; StepExecution xử lý file đạt COMPLETED
   theo hợp đồng Batch/JobRepository.
5. Đối soát tập record, checksum, skip/filter và business output.
6. Chuyển file ready -> archive bằng atomic move nếu hỗ trợ.
7. Xác minh trạng thái source/target và ghi manifest ARCHIVED.
8. Chỉ khi toàn batch đạt quy tắc công bố mới đánh dấu FINAL.
~~~

**Vẫn có khoảng lỗi giữa bước 4, 6 và 7.** Vì move thuộc filesystem, còn trạng thái StepExecution và manifest thường ở database, chúng không chung một transaction. Phải thiết kế **restart idempotent** để bất kỳ bước nào đã thành công cũng có thể được nhận biết ở lần chạy sau.

### Khi có nhiều files trong một step

Nếu một StepExecution đọc liên tục từ nhiều file bằng `MultiResourceItemReader`, bạn **không được coi callback “đọc xong file” là bằng chứng DB đã commit tất cả chunk của file đó**, vì transaction có thể chứa record của cả hai file hoặc checkpoint có thể chưa bền vững. Một lựa chọn an toàn là **một worker step/file hoặc per-file completion protocol** với boundary rõ, hoặc **archive tập file sau khi toàn step đã hoàn tất và được đối soát**.

## 12. Các khoảng lỗi giữa DB, filesystem và metadata

~~~mermaid
sequenceDiagram
    participant W as Spring Batch Worker
    participant DB as Business DB
    participant J as JobRepository
    participant FS as Filesystem
    participant M as File Manifest
    W->>DB: Commit business chunks
    DB-->>W: Commit OK
    W->>J: Step status COMPLETED
    W->>M: READY_TO_ARCHIVE
    W->>FS: Files.move(ready, archive, ATOMIC_MOVE)
    FS-->>W: Move OK
    W->>M: ARCHIVED
    Note over W,M: Có thể crash giữa các bước
~~~

Sơ đồ trình bày **các mốc logic**, không cam kết thứ tự JDBC metadata transaction cụ thể của mọi cấu hình Spring Batch. Ở hệ thống thật, bước xác nhận business transaction và trạng thái metadata phải được kiểm thử trên đúng transaction manager/datasource.

| Mốc worker chết | Source ở ready | File ở archive | DB/metadata có thể | Recovery |
| --- | --- | --- | --- | --- |
| Trước ghi DB | Có | Không | Chưa có effect | Restart import có owner |
| Giữa các chunk | Có | Không | DB đã commit một phần | Checkpoint + idempotent writer |
| DB xong, chưa move | Có | Không | Step đã xử lý xong | Thực hiện archive, **không import lại vô điều kiện** |
| Move xong, trước manifest update | Không | Có | Manifest còn READY_TO_ARCHIVE | Verify target rồi mark ARCHIVED |
| Manifest update thành công nhưng response mất | Không | Có | Có thể bị dispatch lại | Đối soát; no-op idempotent |
| Rename thất bại, state không rõ | Có/không | Có/không | Chưa biết | Kiểm tra source/target/hash, không đoán |
| Target bị sửa sau move | Không | Có nhưng hash khác | Metadata có thể ARCHIVED | Fail/alert, không coi là recovery thành công |

**Quy tắc recovery:** trạng thái `READY_TO_ARCHIVE` chỉ là **ý định**, không phải bằng chứng rename đã xảy ra. Trạng thái `ARCHIVED` cũng cần đối chiếu dữ liệu thực khi nghi ngờ storage corruption hoặc đường dẫn thay đổi.

## 13. Archive Tasklet Spring Batch 5.x: idempotent theo source/target

Một cách tổ chức dễ suy luận là tách **import step** và **archive step**: chỉ chạy archive sau khi import step thành công. Mã sau là khung cho **một file đã có owner/manifest rõ**, không thay thế broker/DB coordination ở môi trường nhiều manager.

~~~java
@Bean
@StepScope
Tasklet archiveFileTasklet(
        @Value("#{jobParameters['sourceUri']}") String sourceUri,
        @Value("#{jobParameters['archiveUri']}") String archiveUri,
        @Value("#{jobParameters['expectedSha256']}") String expectedSha256) {

    return (contribution, chunkContext) -> {
        Path source = Path.of(URI.create(sourceUri));
        Path archive = Path.of(URI.create(archiveUri));
        boolean sourceExists = Files.isRegularFile(source);
        boolean archiveExists = Files.isRegularFile(archive);

        if (!sourceExists && archiveExists) {
            // Có thể lần chạy trước đã move thành công rồi crash.
            verifySha256(archive, expectedSha256);
            return RepeatStatus.FINISHED;
        }
        if (!sourceExists && !archiveExists) {
            throw new IllegalStateException(
                    "Source and archive both missing");
        }
        if (sourceExists && archiveExists) {
            // Không ghi đè vào artifact có sẵn khi chưa điều tra.
            throw new IllegalStateException(
                    "Ambiguous: source and archive both exist");
        }

        // Đường hợp lệ theo state: source tồn tại, archive chưa có.
        // Không dùng state trên như một lock chống process khác.
        verifySha256(source, expectedSha256);
        Files.move(source, archive, StandardCopyOption.ATOMIC_MOVE);
        verifySha256(archive, expectedSha256);
        return RepeatStatus.FINISHED;
    };
}

@Bean
Step archiveFileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        @Qualifier("archiveFileTasklet") Tasklet tasklet) {
    return new StepBuilder("archiveFileStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .build();
}
~~~

`verifySha256(Path,String)` là helper ứng dụng cần tự cài đặt: đọc **đúng phiên bản file** và so sánh hash SHA-256 expected từ manifest đã xác thực; fail nếu mismatch. Mã có chủ đích **không fallback non-atomic**, **không overwrite target tồn tại**, và cho phép recovery trường hợp source đã move nhưng metadata chưa commit.

**Giới hạn không được bỏ qua:** hai lần `Files.isRegularFile` và `Files.move` **không nguyên tử với nhau**. Nếu hai process cùng chạy tasklet mà không có claim/lock, chúng có thể cùng vượt qua precheck. Thêm `ATOMIC_MOVE` **không đảm bảo no-clobber khi target đang tồn tại**. Cần global ownership theo file identity hoặc đường final/version được dành riêng thông qua manifest, và bảo vệ stale worker nếu cần.

### Vì sao Tasklet có transactionManager mà rename vẫn không rollback?

`new StepBuilder(...).tasklet(tasklet, transactionManager)` cấu hình transaction cho step Tasklet theo Spring Batch. Nhưng filesystem rename **không tham gia JDBC transaction**. Nếu move thành công rồi transaction metadata rollback, filesystem vẫn đã move. Vì thế nhánh “source missing / archive exists / checksum matches” không phải tùy chọn thẩm mỹ, mà là một phần của **recovery contract**.

### Cấu hình flow một file

~~~java
@Bean
Job importThenArchive(
        JobRepository jobRepository,
        @Qualifier("importFileStep") Step importStep,
        @Qualifier("archiveFileStep") Step archiveStep) {
    return new JobBuilder("importThenArchive", jobRepository)
            .start(importStep)
            .next(archiveStep)
            .build();
}
~~~

Ví dụ này phù hợp **job xử lý một logical file** với `sourceUri`, `archiveUri`, `expectedSha256` trong JobParameters và một `importFileStep` đã định nghĩa. Khi xử lý nhiều files trong cùng một JobExecution hoặc partitioned step, phải truyền tham chiếu file qua `ExecutionContext`/manifest theo scope tương ứng, không dùng duy nhất một bộ JobParameters cho toàn bộ các partition.

## 14. Không để archive xóa đường dẫn mà worker khác vẫn đang đọc

Trên nhiều hệ Unix, rename không nhất thiết làm những process đã mở file descriptor mất khả năng đọc: reader khác có thể **tiếp tục đọc inode cũ**. Trong Windows hoặc network filesystem, move có thể bị hạn chế bởi open handles/share modes. **Đừng dựa vào rename như tín hiệu hủy toàn bộ reader đang xử lý**.

~~~text
Worker A mở /ready/input-42.csv và đọc 40% file.
Worker B (do scheduler trùng) cho rằng file đã hoàn tất,
move /ready/input-42.csv sang /archive/input-42.csv.
Worker A có thể tiếp tục đọc từ file handle đã mở.
~~~

Trong khi đó một process mới quét `/ready` sẽ không còn thấy file. Cả hai observation có thể cùng đúng trên filesystem nhất định. Vì vậy:

- Worker phải **claim ownership** trước khi xử lý, không phải chỉ scan file path.
- Sau khi import step hoàn tất, đóng reader/stream trước khi archive theo protocol.
- Stale worker phải bị ngăn ghi bởi ownership/fencing hoặc business idempotency.
- Không coi “file không còn ở ready” là bằng chứng “mọi worker đã dừng và business DB đúng”.
- Nếu move thất bại do file đang mở, coi là lỗi có thể retry theo giới hạn; không tự xóa file.

## 15. Manifest trạng thái cho nhiều process

Trong hệ thống nhiều JVM/pod, một bảng manifest thường rõ ràng hơn việc chỉ quan sát directory:

~~~sql
CREATE TABLE file_ingestion (
    file_id          VARCHAR(160) PRIMARY KEY,
    batch_key        VARCHAR(100) NOT NULL,
    source_uri       VARCHAR(500) NOT NULL,
    archive_uri      VARCHAR(500) NOT NULL,
    source_version   VARCHAR(160) NOT NULL,
    checksum_sha256  VARCHAR(64) NOT NULL,
    state            VARCHAR(24) NOT NULL
                     CHECK (state IN (
                         'READY','PROCESSING','READY_TO_ARCHIVE',
                         'ARCHIVED','FAILED','QUARANTINED')),
    claimed_by       VARCHAR(160),
    lease_epoch      BIGINT NOT NULL DEFAULT 0,
    lease_until      TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    last_error_code  VARCHAR(100)
);

CREATE INDEX idx_ingestion_state
    ON file_ingestion(state, lease_until, file_id);
~~~

**Phân biệt ý nghĩa các state:**

- `READY`: producer đã bàn giao immutable input và file có thể được claim.
- `PROCESSING`: một worker có quyền xử lý theo claim/lease.
- `READY_TO_ARCHIVE`: business processing và validation đã đạt; archive vẫn cần thực hiện.
- `ARCHIVED`: target archive đã được xác nhận và trạng thái quản trị đã cập nhật.
- `FAILED`: cần sửa nguyên nhân/recovery có kiểm soát.
- `QUARANTINED`: file cần điều tra vì schema/hash/permission/ownership bất thường.

Không dùng cùng một flag `processed=true` cho tất cả các mốc. Nếu crash giữa bước import và move, cần biết đang ở **trạng thái nghiệp vụ nào** để tiếp tục mà không import lại sai.

## 16. Claim, lease và fencing trước khi archive

Một claim cơ bản trong PostgreSQL:

~~~sql
UPDATE file_ingestion
SET state = 'PROCESSING',
    claimed_by = :workerId,
    lease_epoch = lease_epoch + 1,
    lease_until = CURRENT_TIMESTAMP + INTERVAL '120 seconds'
WHERE file_id = :fileId
  AND (
      state = 'READY'
      OR (
          state = 'PROCESSING'
          AND lease_until < CURRENT_TIMESTAMP
      )
  )
RETURNING file_id, source_uri, archive_uri,
          checksum_sha256, lease_epoch;
~~~

Đây là **atomic database claim** cho các worker chia sẻ cùng database. Khi claim fail (0 row), worker **không được** tự import/archive file. Dùng DB clock để giảm clock skew giữa các pod; heartbeat cần gia hạn lease trong quá trình xử lý dài.

Khi xử lý xong, worker phải chuyển state bằng CAS kiểm owner/epoch:

~~~sql
UPDATE file_ingestion
SET state = 'READY_TO_ARCHIVE'
WHERE file_id = :fileId
  AND claimed_by = :workerId
  AND lease_epoch = :epoch
  AND state = 'PROCESSING'
  AND lease_until >= CURRENT_TIMESTAMP;
~~~

**Một row updated** chỉ chứng minh transition hợp lệ; nó không tự chứng minh business DB đã commit nếu application gọi quá sớm. Phải gọi sau verification phù hợp. Sau khi atomic move và verify target:

~~~sql
UPDATE file_ingestion
SET state = 'ARCHIVED',
    completed_at = CURRENT_TIMESTAMP,
    lease_until = NULL
WHERE file_id = :fileId
  AND claimed_by = :workerId
  AND lease_epoch = :epoch
  AND state = 'READY_TO_ARCHIVE';
~~~

**Điểm cần bổ sung ở production:** khi ownership có thể được lấy lại trong state `READY_TO_ARCHIVE`, cần policy **claim archive riêng**, heartbeat/quyền CAS và recovery fencing được thiết kế nhất quán. Câu UPDATE cuối ở trên là **phác thảo**, không đủ để chống stale worker nếu một quản trị viên hoặc một recovery process có thể chuyển quyền mà không đổi epoch.

### Vì sao lease expiry chưa đủ?

Worker A có thể bị GC pause sau khi đọc `lease_epoch=7`; lease hết hạn và worker B được cấp epoch 8. A tỉnh lại rồi thực hiện move trên cùng source path. DB có thể từ chối A cập nhật state, **nhưng file đã bị move trước khi UPDATE trả 0**.

Do filesystem rename **không tự kiểm epoch DB**, cần **ownership/quiescence protocol** ngăn stale worker thực hiện thao tác nguy hiểm. Các phương án thực tế gồm coordinator duy nhất thực hiện archive, một transaction lock theo batch/file bao quanh bước publish ngắn (hiểu rõ I/O hold), immutable temp/final versions với CAS manifest, hoặc sink/filesystem proxy có fencing. Không coi `lease_epoch` trong log là fencing đã có hiệu lực.

## 17. Fencing trong database và giới hạn với rename

Khi business output cùng DB manifest, một worker có thể giữ row lock của manifest trong **transaction ghi chunk ngắn**, xác minh owner/epoch trước business write, rồi mới commit. Nhưng `Files.move` **không tham gia transaction đó**.

~~~text
DB fencing:
  BEGIN
  SELECT file_ingestion FOR UPDATE
  VERIFY lease_epoch == workerEpoch
  WRITE business data
  COMMIT

Filesystem:
  Files.move(source, archive, ATOMIC_MOVE)

Manifest:
  UPDATE state = ARCHIVED
~~~

Khoảng giữa **DB validation và rename** vẫn có thể có chuyển ownership nếu không serialize các thao tác quản trị. Do đó nếu file archive là tài sản quan trọng, nên:

1. **Chỉ một component quản trị** có quyền archive (file mover/coordinator), worker chỉ ghi `READY_TO_ARCHIVE`.
2. Component quản trị claim file archive work dưới khóa/CAS riêng, xác minh không còn worker active, và triển khai move/reconcile.
3. Dùng **đích archive versioned/unique**, không để stale process overwrite target đã có.
4. Nếu hệ thống đòi strong fencing cho filesystem, dùng protocol cụ thể của shared storage/lock manager đã thử nghiệm; không hứa một DB epoch đơn lẻ chặn được `rename()` của process khác.
5. Khi move outcome không rõ, **kiểm tra thực tế source/target/checksum** rồi quyết định tiếp.

**Idempotent retry** và **strong fencing** là hai lớp khác nhau: idempotency giúp replay không trùng hiệu ứng; fencing chặn process đã mất quyền tạo tác động mới.

## 18. Output publication với manifest thay vì overwrite final file

Khi nhiều process có thể tạo lại cùng `report.csv`, một thiết kế bền hơn là **publish immutable content-addressed/versioned artifacts**, rồi cập nhật một pointer/manifest:

~~~text
Worker A:
  staging/report-run845-attempt1.tmp
  -> artifacts/report-run845-sha256-abc.csv

Worker B (retry):
  staging/report-run845-attempt2.tmp
  -> artifacts/report-run845-sha256-abc.csv

Manifest:
  logicalReport=report-run845
  selectedVersion=sha256-abc
  state=PUBLISHED
~~~

Chú ý **cùng tên artifact** do hash suy ra không tự tạo no-clobber: concurrent move lên một đích có sẵn vẫn cần policy tránh overwrite, kiểm tra content và race. Có thể thay vì hai process đua rename, yêu cầu **một publisher duy nhất** chọn winner trong DB, hoặc ghi mỗi attempt vào tên vật lý duy nhất và công bố pointer đến artifact được chọn.

Ví dụ trạng thái DB:

~~~sql
CREATE TABLE report_publication (
    report_key     VARCHAR(160) PRIMARY KEY,
    artifact_uri   VARCHAR(600),
    artifact_hash  VARCHAR(64),
    state          VARCHAR(20) NOT NULL
                   CHECK (state IN (
                       'PREPARING','VALIDATING','PUBLISHED','FAILED')),
    published_at   TIMESTAMPTZ
);

UPDATE report_publication
SET artifact_uri = :verifiedArtifactUri,
    artifact_hash = :verifiedHash,
    state = 'PUBLISHED',
    published_at = CURRENT_TIMESTAMP
WHERE report_key = :reportKey
  AND state = 'VALIDATING';
~~~

**Quan trọng:** cả query UPDATE và service gọi nó phải chứng minh **artifact đã bất biến, checksum đúng, đủ partition, không có writer còn chỉnh nội dung**. Nếu cập nhật pointer trước khi file thực sự tồn tại hoặc trước khi replicate tới những reader cần thiết, downstream vẫn gặp broken references. Đối với hệ phân tán, publisher/reader phải tuân theo contract availability và consistency của storage.

## 19. Kiểm tra checksum và số record thực sự

Khi gặp trạng thái `source missing / target exists` sau restart, việc chỉ thấy một file tồn tại ở archive **không đủ** để kết luận lần move trước đã thành công. Có thể file đích là artifact của batch khác hoặc đã bị người vận hành thay thế. Cần kiểm tra **file identity, source version/checksum và metadata kỳ vọng**.

Ví dụ helper Java 17 SHA-256:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.HexFormat;

static void verifySha256(Path file, String expectedHex)
        throws Exception {
    MessageDigest digest = MessageDigest.getInstance("SHA-256");
    try (InputStream in = Files.newInputStream(file)) {
        byte[] buffer = new byte[64 * 1024];
        int n;
        while ((n = in.read(buffer)) != -1) {
            digest.update(buffer, 0, n);
        }
    }
    String actual = HexFormat.of().formatHex(digest.digest());
    if (!actual.equalsIgnoreCase(expectedHex)) {
        throw new IllegalStateException("Input/archive checksum mismatch");
    }
}
~~~

Đây là **full-file checksum**: với file 200 GiB, đọc lại toàn bộ có thể tốn nhiều I/O và ảnh hưởng throughput. Có thể dùng hash đã tạo trong quá trình ghi cùng metadata producer đáng tin cậy, nhưng **nếu yêu cầu khẳng định bytes ở archive không đổi** thì vẫn cần cơ chế xác minh end-to-end phù hợp. Một ETag của object storage không phải lúc nào cũng là hash SHA-256 của nội dung.

Đối với dữ liệu nghiệp vụ, checksum bytes **chưa chứng minh** toàn bộ records đã được ghi đúng vào DB. Khi archive file nguồn sau import, nên kiểm tra thêm:

- `expectedRecords` từ manifest/producer theo định nghĩa record logic.
- `readCount`, `writeCount`, `filterCount`, `skipCount` và trạng thái StepExecution theo đúng semantics Spring Batch.
- Tập business keys trong input so với output + approved filters + quarantine.
- Rule/snapshot version, tổng tiền/checksum theo miền nghiệp vụ nếu cần.
- Những side effect ngoài DB (event, payment/API) đã có cơ chế idempotency và đối soát riêng.

**Không dùng mỗi `File.size` hoặc `COUNT(*)` làm bằng chứng đủ dữ liệu**: file cùng số bytes vẫn có thể chứa bytes khác, và output cùng số row vẫn có thể thiếu một key nhưng trùng một key khác.

## 20. Chuyển file ở local disk, NFS, SMB và Kubernetes volume

| Storage | Atomic move có thể? | Những điều phải kiểm chứng |
| --- | --- | --- |
| Local ext4/XFS | Thường có hỗ trợ rename nguyên tử **trong cùng filesystem** | Thư mục đích, fsync/durability, open handles, crash recovery |
| NTFS/Windows | Có cơ chế rename/move nhưng chịu Windows share modes/permissions | File đang được reader mở, antivirus/indexer, provider behavior |
| NFS | Tùy phiên bản/protocol, server/mount và phạm vi rename | Cross-mount, cache, client failover, rename visibility, power-loss behavior |
| SMB | Tùy server/share configuration và OS client | Open handles, lease/oplock, reconnect, target collisions |
| Kubernetes shared PVC | Phụ thuộc CSI backend thực tế, không chỉ tên PVC | Hai pods mount cùng underlying FS? rename/lock semantics? |
| Object storage S3/Blob | **Không có POSIX atomic rename tổng quát** | API copy/delete/version/conditional PUT, manifest publication |

**Không kết luận từ việc chạy thành công trên temp directory của laptop rằng production NFS/CSI cũng atomic.** Cần test trên loại filesystem, mount options, số node và cách failover thực tế.

### Tình huống hai mount cùng server

Hai đường dẫn có thể nằm trên cùng storage server nhưng được mount khác nhau; điều này **không bảo đảm** Java provider xử lý `Files.move` giữa chúng như rename nội bộ. Với NFS và SMB, client/server behavior còn tùy phiên bản và cấu hình. Nếu atomic move là yêu cầu bắt buộc, thử **chính xác cặp source/target directory** trước triển khai và kiểm thử lại khi hạ tầng thay đổi.

### Open files và antivirus

Trên Windows, reader/antivirus/indexing service có thể giữ file handle khiến rename thất bại. Trên Unix, process đã mở descriptor có thể vẫn đọc nội dung sau khi file bị rename. Hai tình huống dẫn tới bài học chung: **close reader khi hoàn tất và đừng dùng move như một lock bảo vệ các process không hợp tác**.

## 21. Object storage: thay rename bằng immutable object + pointer

Với S3/GCS/Azure Blob, khái niệm “move” thường được hiện thực bằng **copy rồi delete**, không phải rename POSIX nguyên tử. Trong lúc copy/delete, hệ thống có thể thấy cả source và target hoặc một trạng thái trung gian; không nên dùng tên `ready`/`archive` để mặc nhiên suy ra đúng một object tồn tại.

Một design an toàn hơn:

~~~text
Producer:
  upload immutable objects/<version-id>
  verify provider checksum/size/version

Workers:
  xử lý đúng object version đã chốt
  ghi output versioned objects, xác minh hoàn chỉnh

Publisher:
  manifest/batch pointer -> VERIFIED object versions
  chuyển trạng thái PUBLISHED bằng DB CAS hoặc
  storage conditional write theo provider contract

Retention:
  archive/expire source object theo lifecycle độc lập
~~~

Lợi ích là downstream chỉ đọc **object versions được manifest chỉ tới**, không phải quét tên `.tmp` hay đoán file đã được move. **Atomicity nằm ở điểm công bố manifest/pointer**, không ở việc “copy object một cách nguyên tử” giữa hai key.

Nếu storage hỗ trợ conditional request (`If-Match`, `If-None-Match`, generation-match, versioned writes), chỉ dùng theo **đúng API và consistency contract** của provider. Không áp dụng mù cách tạo file `.lock` bằng `Files.createFile` lên object storage.

### Không xóa nguồn trước khi có target đã kiểm chứng

Đối với cross-bucket/cross-region archive, copy có thể mất nhiều phút. Xóa source ngay sau khi API copy trả “request accepted” nhưng trước khi target thực sự sẵn sàng là rủi ro mất dữ liệu. Phải có **completion evidence, checksum/version, retention/lifecycle và recovery state**. Với bucket có object versioning, deletion marker không đồng nghĩa bytes nguồn bị loại bỏ vật lý; quy trình vận hành cần hiểu lifecycle semantics.

## 22. Remote partitioning, remote chunking và atomic move

Trong Spring Batch **remote partitioning**, worker thường có `ItemReader` riêng và nhận `ExecutionContext` chứa file ID/URI/version. Một worker có thể xử lý file rồi tạo output hoặc báo hoàn thành partition; nên gắn **ownership file và archive task** với đúng worker StepExecution/manifest, thay vì mỗi node tự quét inbox.

Trong **remote chunking**, manager thường đọc input (có thể là file CSV), đóng `ChunkRequest` chứa item và gửi tới worker. Worker chủ yếu process/write, không nhất thiết có file input vật lý. Vì vậy **archive source file thường thuộc trách nhiệm manager-side orchestration**, sau khi các chunk liên quan đã có outcome hợp lệ và output đã được xác nhận, không phải worker nhận một chunk bất kỳ tự di chuyển file.

| Câu hỏi | Remote partitioning | Remote chunking |
| --- | --- | --- |
| Ai sở hữu ItemReader nguồn? | Worker step | Manager |
| File path nằm ở đâu? | ExecutionContext/manifest cho worker | Reader/config của manager |
| Ai nên quyết định archive? | Worker/coordinator theo file completion protocol | Manager/coordinator sau khi xác nhận toàn bộ file work |
| Khi mất broker reply? | Partition đã commit nhưng manager chưa biết | Worker chunk đã commit nhưng manager chưa correlate response |
| Có được move chỉ vì request đã ACK? | **Không** | **Không** |

**Request ACK, business DB commit, Spring Batch StepExecution COMPLETED, Files.move và manager nhận reply là các sự kiện có thể thuộc resource/transaction khác nhau.** Nếu worker đã commit rồi reply mất, manager có thể phát lại công việc; archive không được làm mất input trước khi có cơ chế restart/đối soát an toàn.

### Khi một file sinh nhiều chunks

Không archive input khi **chunk đầu tiên** của file hoàn tất, cũng không archive chỉ vì reader đã phát hết item mà chưa biết worker chunk cuối commit hay chưa. Cần một **per-file completion barrier** xác định mọi request/chunk của file đã có outcome hợp lệ và các side effects đã được reconciled; nếu manager reader checkpoint khác worker DB transaction, writer phải replay-safe.

## 23. Multi-threaded step và parallel steps: ai thực hiện move?

Nếu nhiều thread trong cùng một step cùng xử lý dữ liệu từ một `FlatFileItemReader`, reader state và file pointer có thể không thread-safe. Move ở một listener tùy ý khi thấy “hết file” có thể xảy ra trong lúc thread khác còn đang write/commit.

**Phương án nên cân nhắc:**

- **Per-file worker StepExecution**: bước archive chỉ chạy khi worker step tương ứng đã thực sự hoàn tất và được validation theo file.
- **Manager/coordinator archive step**: nhận danh sách file đủ điều kiện từ manifest, thực hiện archive sau khi tất cả worker liên quan đã xong.
- **Separate immutable output parts**: mỗi worker viết output của mình, một publisher quyết định công bố toàn bộ sau validation.

Trong **parallel flows**, flow A có thể hoàn tất file A và move archive trước khi flow B thất bại. Điều đó không có global rollback. Nếu nghiệp vụ yêu cầu toàn batch nhất quán, dùng **staging và publication barrier** chứ không trông chờ một transaction chung của JobExecution.

### Không dùng ItemReadListener.afterRead để archive

`afterRead` được gọi khi một item đọc thành công, **không** có nghĩa tất cả business effects đã commit. Tương tự, các listener trước/after write có thể được gọi trong một transaction còn có khả năng rollback. Để biết file đã xử lý xong, cần **bước hoàn thành/validation sau commit** theo pipeline đã định nghĩa, không chỉ nhìn callback đọc.

## 24. Xác nhận ownership trước move: tránh hai process cùng archive

Một race thực tế:

~~~text
Worker A đọc manifest state=READY_TO_ARCHIVE.
Worker B cũng đọc cùng state.
A verify source checksum.
B verify source checksum.
A atomic move source -> archive, thành công.
B move source -> archive, gặp missing source.
~~~

Worker B **không nên** xem missing source đơn thuần là lỗi vĩnh viễn, nhưng cũng **không được** mặc định A đã xử lý hợp lệ. B phải kiểm tra target, content và ownership trước khi quyết định.

**Với nhiều process:**

1. Chỉ cho process có **archive claim/token** hợp lệ thực hiện move.
2. Dành sẵn logical target path/version trong manifest; tránh target được producer khác dùng.
3. Trước move, xác minh source version còn đúng, owner còn hợp lệ và người ghi source đã dừng.
4. Sau move, xác minh target và CAS manifest theo owner/version.
5. Nếu mất quyền, **không retry mù quáng**; chuyển cho recovery coordinator và đối soát.
6. Nếu target đã có nội dung đúng, dùng nhánh idempotent reconciliation, không ghi đè tự động.

**CAS ở database xảy ra sau move không bảo vệ tuyệt đối filesystem move** vì worker có thể mất ownership đúng khoảng giữa. Khi yêu cầu strong fencing, phải serialize publication tại một coordinator duy nhất hoặc cung cấp fencing thực thi tại storage/đường publish, thay vì chỉ lưu epoch nhưng cho mọi worker gọi `Files.move` tự do.

## 25. FileLock và atomic move: hai công cụ hỗ trợ nhau, không tương đương

Một `FileLock` có thể phối hợp process khi cùng truy cập file local/shared filesystem hỗ trợ khóa. `Files.move` có thể công bố file nguyên tử. Hai thao tác giải quyết các câu hỏi khác nhau:

~~~text
FileLock:
  "Ai được phép xử lý/di chuyển logical file này lúc này?"

ATOMIC_MOVE:
  "Observer nhìn thấy tên file chuyển đổi như một bước không?"
~~~

Ví dụ dùng sidecar `.lck` ổn định: worker lấy khóa, verify trạng thái/ownership, làm move, rồi release. Tuy nhiên:

- `FileLock` thường là advisory; process không tham gia protocol vẫn có thể gọi rename.
- OS lock có semantics khác nhau trên NFS/SMB/Windows và có thể bị ảnh hưởng bởi network failures.
- **Đừng xóa sidecar lock file** khi release: process khác có thể đang giữ lock trên inode cũ rồi một file mới cùng tên được tạo, gây hai “owner” hợp lệ trên hai inode.
- Khi process chết, OS lock có thể được giải phóng; file `.lck` vẫn tồn tại. Đó không phải bằng chứng lock còn đang giữ.
- FileLock cũng không hồi phục những DB transactions đã commit trước crash.

Trong hệ nhiều node, một **DB claim + coordinator duy nhất + idempotent storage publication** thường dễ audit hơn việc chỉ dựa vào OS locks trên network FS chưa kiểm chứng.

## 26. Quy trình thất bại khi atomic move không được hỗ trợ

Nếu `Files.move(..., ATOMIC_MOVE)` ném `AtomicMoveNotSupportedException`:

1. **Không xóa nguồn.**
2. Ghi log lỗi với source/target logical IDs và filesystem type **không chứa secrets**.
3. Đánh dấu work `NEEDS_COPY_PUBLISH` hoặc `FAILED` theo state machine (nếu schema hỗ trợ), không báo StepExecution COMPLETED giả.
4. Chuyển qua một **workflow riêng**: copy vào temp **trên filesystem đích**, close/verify checksum, rồi atomic rename nội bộ đích **nếu được hỗ trợ**.
5. Nếu ngay cả rename nội bộ đích không có atomic semantics, sử dụng **manifest/pointer publication** làm điểm công bố; downstream không quét file temp/final tùy ý.
6. Sau khi target xác nhận đúng, cập nhật manifest; việc xóa/retire source là một hành động riêng có thể retry.

**Không chỉ catch rồi gọi `Files.move(source,target)` không option.** Hành vi non-atomic có thể để lại partial target/uncertain state khi lỗi xảy ra. Cũng không nên **silent fallback** nếu SLA cam kết không bao giờ để downstream đọc file dở.

### Quyết định theo điều kiện hạ tầng

| Kết quả kiểm tra | Chiến lược |
| --- | --- |
| Atomic move được hỗ trợ trong cùng FS | Temp + validate + atomic rename |
| Source khác filesystem nhưng đích hỗ trợ atomic rename nội bộ | Copy → temp đích → verify → rename nội bộ |
| Object storage không có rename POSIX | Immutable versioned objects + conditional manifest pointer |
| Không thể bảo đảm downstream không đọc file dở | Dừng công bố/đổi reader contract, không pretend atomic |
| Nhiều worker tranh cùng tên đích | Global claim/CAS, unique physical artifact, một publisher được chọn |

## 27. Test atomic visibility bằng filesystem thực

Kiểm thử `ATOMIC_MOVE` phải sử dụng **đúng source và destination directories** trên cùng loại filesystem như production. Test trên `@TempDir` ở local disk chỉ chứng minh behavior tại local provider, không chứng minh một network mount khác.

Ví dụ JUnit 5 cho một file nhỏ:

~~~java
@Test
void atomicMovePublishesCompletedFile(@TempDir Path dir)
        throws Exception {
    Path staging = Files.createDirectory(dir.resolve("staging"));
    Path published = Files.createDirectory(dir.resolve("published"));
    Path temporary = staging.resolve("report.csv.part");
    Path target = published.resolve("report.csv");

    byte[] expected = "id,amount\\n1,100\\n2,200\\n"
            .replace("\\n", "\n")
            .getBytes(StandardCharsets.UTF_8);
    Files.write(temporary, expected,
            StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE);

    assertFalse(Files.exists(target));
    Files.move(temporary, target, StandardCopyOption.ATOMIC_MOVE);

    assertFalse(Files.exists(temporary));
    assertArrayEquals(expected, Files.readAllBytes(target));
}
~~~

**Giới hạn của test:** nó chứng minh rename thành công, source mất tên cũ và bytes ở target đúng **sau thao tác**. Nó **chưa chứng minh** quá trình quan sát dưới concurrency tuyệt đối không thấy partial target, crash durability sau mất điện, hoặc behavior của NFS/SMB.

Để kiểm thử visibility dưới concurrency:

1. Tạo file tạm lớn đủ để nhận thấy copy dở trong implementation sai.
2. Chạy một process/worker công bố file và một reader process lặp lại việc mở **tên final**.
3. Nếu reader thấy final, nó chỉ chấp nhận **đúng length/hash/manifest version đã niêm phong**; không được thấy phiên bản có bytes dở.
4. Thử cả trường hợp non-atomic copy trực tiếp vào final như **negative control** để chứng minh test phát hiện partial visibility.
5. Ghi lại filesystem, mount options và môi trường; không dùng test để suy ra bảo đảm vượt quá provider contract.

**WatchService event cũng không phải transaction boundary.** Nhận sự kiện `ENTRY_CREATE` ở thư mục `published` không tự xác nhận checksum/DB output đã đúng; downstream phải tuân theo publication contract.

## 28. Test Tasklet archive khi crash sau rename

Một test recovery quan trọng mô phỏng:

~~~text
Step import file đã COMPLETED.
Archive Tasklet gọi Files.move(source, archive, ATOMIC_MOVE) thành công.
Process bị kill trước khi Spring Batch ghi nhận archive StepExecution COMPLETED.
Restart cùng JobInstance và input snapshot.
Archive Tasklet được gọi lại theo JobRepository.
  source missing, archive exists, checksum matches
  -> coi archive operation đã hoàn tất, không move thêm lần nữa.
~~~

**Assertion quan trọng:**

- Không có lần import lại business data chỉ vì archive step cần retry.
- File target đúng SHA-256, đúng source version/tenant và expected records.
- Manifest chuyển sang `ARCHIVED` bằng CAS hợp lệ khi recovery.
- Không có file thứ hai cùng logical ID ở archive và không có overwrite artifact khác.
- StepExecution/JobExecution kết thúc đúng trạng thái sau recovery.

### Cần test cả các trạng thái nguồn/đích

| Source ở ready | Target archive | Checksum target | Hành vi |
| --- | --- | --- | --- |
| Có | Không | — | Verify source rồi move nếu owner hợp lệ |
| Không | Có | **Khớp** | Idempotent success sau khi verify processing outcome |
| Không | Có | **Không khớp** | **Fail/quarantine**; không coi đã xử lý |
| Có | Có | Khớp hoặc không | **Ambiguous**; không tự overwrite/xóa nếu thiếu policy |
| Không | Không | — | **Missing input**; fail/đối soát storage |

**Lưu ý:** nhánh “source missing + target exists + checksum matches” trong Tasklet chỉ an toàn khi **đã có bằng chứng import step/completion được xác nhận**. Nếu ai đó move file thủ công trước khi import, chỉ đúng checksum không chứng minh business output được ghi; validation metadata/DB vẫn bắt buộc.

## 29. Ma trận failure injection cần chạy

| Kịch bản | Điểm gây lỗi | Điều cần xác minh |
| --- | --- | --- |
| A. Crash khi đang ghi temp | Writer chưa đóng file `.part` | Downstream không nhìn thấy `final`; temp được cleanup/recover |
| B. Validation thất bại | Hash/count/business totals sai | Không publish; giữ bằng chứng điều tra |
| C. Atomic move không được hỗ trợ | Source/target khác filesystem | Fail rõ hoặc đi workflow copy-temp-dest/manifest, không copy trực tiếp final |
| D. Crash ngay trước move | DB đã commit, source còn ở ready | Không import lại vô điều kiện; archive có thể tiếp tục |
| E. Crash ngay sau move | Source mất, target có | Restart nhận biết trạng thái và verify checksum |
| F. Target đã có sẵn | Hai attempts cùng logical output | Không overwrite mù quáng; ownership/CAS và content check |
| G. Source/target cùng tồn tại | Copy fallback dở hoặc move khác | Không tự xóa nguồn/đích; đưa vào đối soát |
| H. Nhiều workers race | Hai JVM cùng lấy file/attempt | Chỉ owner hợp lệ publish/archive |
| I. Lease hết nhưng worker cũ sống | A pause, B được cấp quyền mới | Không cho stale worker đổi public state/overwrite target |
| J. Windows open handle | Reader vẫn mở target/source | Lỗi access có policy và không làm mất file |
| K. NFS/network failure | Ngắt mount giữa verify và rename | Không assume source/target; reconcile sau reconnect |
| L. Metadata DB lỗi sau move | Rename xong, UPDATE manifest fail | Recovery cập nhật state theo bằng chứng target |
| M. Broker reply mất sau commit | Worker xử lý/di chuyển nhưng manager chưa biết | Correlate/restart, idempotency và no duplicate |
| N. Partial partition completion | Một file report chưa có | Manifest không publish toàn bộ batch sớm |
| O. Input source bị sửa | Checksum/version thay giữa các lần chạy | Fail, không tiếp tục checkpoint trên nguồn thay đổi |

Để tái hiện đúng các khoảng lỗi, cần **hook/harness tại điểm trước và sau rename/DB commit**, không chỉ gọi `Thread.sleep(500)` rồi kill process theo cảm giác. Dùng `CountDownLatch` cho test cùng JVM; đối với crash thật, dùng child JVM/process với handshake và terminate đúng thời điểm.

### Probe có điểm dừng trước và sau rename

~~~java
final class MoveBoundaryProbe {
    final CountDownLatch beforeMove =
            new CountDownLatch(1);
    final CountDownLatch allowMove =
            new CountDownLatch(1);
    final CountDownLatch afterMove =
            new CountDownLatch(1);

    void pauseBeforeMove() throws InterruptedException {
        beforeMove.countDown();
        if (!allowMove.await(15, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Timeout before move");
        }
    }

    void signalAfterMove() {
        afterMove.countDown();
    }
}
~~~

Ví dụ trên là **test instrumentation**, không phải production lock. Khi test muốn kill process **sau move**, phải xác nhận `afterMove` chỉ được báo **sau khi Files.move trả về thành công**, và kill trước khi marker StepExecution/manifest được commit. Đối với child JVM, có thể thay latch bằng handshake qua stdout/socket/test broker; hai process không chia sẻ một `CountDownLatch` trong memory.

## 30. Kiểm thử hai process và hai manager

Một `Files.move` trên đúng filesystem có thể thành công trong một JVM nhưng pipeline vẫn xử lý trùng vì **hai JobExecution** cùng scan inbox. Do đó tích hợp test cần:

1. Hai manager/worker JVM cùng nhìn thấy một manifest file ở trạng thái READY.
2. Hai process cố claim cùng file ID; DB phải cho **chỉ một claim thắng**.
3. Process còn lại không được gọi writer, move hoặc trả StepExecution success giả.
4. Cho owner xử lý và move; kiểm tra bản ghi business đúng một lần, target/manifest đúng.
5. Kill owner sau DB commit trước move, cho recovery owner thực hiện archive mà không import trùng.
6. Tạo lease expiry/GC pause: owner cũ cố move khi owner mới đã có quyền; hệ thống phải **ngăn public state bị sửa sai**, không chỉ log epoch khác.
7. Kiểm tra routing riêng nếu remote partitioning dùng broker: reply muộn của execution cũ không được khiến manager mới archive file sớm.
8. Xác minh khi target đã tồn tại với content khác, pipeline fail/alert thay vì ghi đè.

### Đừng chỉ kiểm queue depth hoặc số file

Sau recovery, `ready` rỗng và `archive` có 100 file không đảm bảo 100 logical inputs đã được xử lý đúng. Có thể một file bị nhân đôi, một file khác mất và một file có checksum sai. Cần **join theo file ID/source version**, business keys và trạng thái JobRepository.

## 31. Performance: atomic move thường rẻ, validation mới đắt

Trong cùng filesystem hỗ trợ rename, atomic move thường chủ yếu thay đổi **metadata tên file**, không phải copy toàn bộ bytes. Vì vậy việc rename một file 100 GiB có thể nhanh hơn rất nhiều so với copy 100 GiB. Tuy nhiên:

- Hash lại file 100 GiB để verify có thể tiêu tốn nhiều I/O.
- Cross-filesystem copy vẫn tốn network/disk bandwidth theo bytes.
- File đang được mở hoặc permission chặt có thể gây retry/backoff.
- Manifest DB CAS/lock contention trở thành bottleneck nếu có hàng chục nghìn workers tranh cùng queue.
- Nhiều file nhỏ tạo overhead metadata, số lượng directory entries và stat calls lớn.
- Antivirus/indexer/network FS latency có thể làm move chậm hoặc thất bại bất thường.

| Kịch bản | File size | Số file | Yếu tố chủ đạo cần đo |
| --- | --- | --- | --- |
| Nhỏ và rất nhiều | 100 KiB | 1.000.000 | Directory metadata IOPS, manifest DB, scheduler |
| Trung bình | 50 MiB | 20.000 | Hash/copy overhead, worker throughput |
| Rất lớn | 100 GiB | 20 | I/O bandwidth, shard strategy, recovery time |
| Cross-filesystem archive | 10 GiB | 500 | Copy bandwidth, temp disk capacity, checksum |
| Network FS nhiều pod | 200 MiB | 10.000 | Server latency, failover/rename semantics, open handles |

**Tăng số worker không làm atomic rename “nguyên tử hơn”.** Chọn concurrency theo CPU, throughput nguồn/đích, DB connection pool, file skew, broker capacity và thời gian recovery; đo cả **độ đúng** lẫn throughput.

### Có nên hash từng file sau move?

Nếu file được rename nội bộ filesystem (không copy) và nguồn đã được producer xác minh, việc đọc lại full hash sau move có thể là chi phí bổ sung. Có thể chọn policy kiểm hash trước move và metadata-based reconciliation sau move, hoặc hash lại theo risk/SLA. Nhưng khi copy cross-filesystem hoặc có storage trust boundary, **verify target bytes** thường quan trọng hơn. Quyết định dựa trên threat model, lỗi thiết bị và yêu cầu kiểm toán.

## 32. Observability và alerting của file move

| Metric | Ý nghĩa | Khi bất thường |
| --- | --- | --- |
| `files_ready_total` | Số file chưa claim | Tăng liên tục, producer nhanh hơn consumer |
| `files_ready_to_archive` | Business processing đã đạt nhưng archive chưa xong | Backlog archive và I/O bottleneck |
| `files_archived_total` | Archive xác nhận theo manifest | Không khớp với completed files |
| `atomic_move_success_total` | Số move được provider chấp nhận | Giảm bất thường sau deploy |
| `atomic_move_unsupported_total` | Filesystem không hỗ trợ | **Bất kỳ lần nào** nếu atomic là contract |
| `atomic_move_error_total` | Lỗi rename I/O/permission/collision | Spike sau deploy/storage change |
| `atomic_move_latency_seconds` | Thời gian move | Tăng do filesystem/server |
| `archive_checksum_mismatch_total` | Target khác expected bytes | Phải alert và quarantine |
| `archive_ambiguous_state_total` | Source/target both/missing | Recovery incidents |
| `stale_owner_move_attempt_total` | Worker mất ownership vẫn muốn move | Dấu hiệu split-brain |
| `manifest_state_age_seconds` | Một file kẹt ở state quá lâu | READY_TO_ARCHIVE quá SLA |
| `reconciliation_mismatch_total` | Input/output/manifest không khớp | Không publish batch |
| `job_restart_recovery_duration` | Thời gian khôi phục đủ điều kiện | Vượt SLA |

**Không đưa `fileId`, full path, tenant secret hoặc checksum của từng file vào metric labels** ở hệ có hàng triệu files. Dùng các thông tin đó trong logs/tracing/manifest được phân quyền. Metric nên aggregate theo batch, step, storage class, error type, size bucket hoặc worker pool.

### Log đúng trạng thái đã xác nhận

~~~text
worker A  PROCESS_COMPLETED  fileId=f042 outputCount=25000
worker A  ARCHIVE_INTENT     fileId=f042 epoch=8
worker A  ATOMIC_MOVE_OK     fileId=f042 archiveVersion=v1
worker A  ARCHIVE_VERIFIED   fileId=f042 checksum=match
worker A  MANIFEST_ARCHIVED fileId=f042 epoch=8
~~~

Tên sự kiện chỉ minh họa. **Không log `MANIFEST_ARCHIVED` trước khi DB COMMIT thành công**, không log `ATOMIC_MOVE_OK` chỉ vì đã gọi `Files.move` nhưng exception còn chưa xử lý. Nếu checksum có ý nghĩa an toàn hoặc có thể làm lộ thông tin, log trạng thái `match/mismatch` thay vì toàn bộ hash/raw metadata.

## 33. Bảo mật, path traversal và quyền ghi file

Một đường dẫn source/target do hệ thống ngoài gửi đến có thể chứa `..`, symlink, tên tương đối hoặc trỏ tới mount ngoài phạm vi cho phép. Nếu worker được quyền `Files.move` ở bất kỳ path nào, một input độc hại có thể khiến job di chuyển file không thuộc batch.

**Quy tắc triển khai:**

1. Chỉ chọn `fileId` từ **manifest đã xác thực**, không cho request thô quyết định absolute target path.
2. Giữ các thư mục `ready`, `staging`, `archive`, `published` trong **roots có phân quyền** và xác định namespace theo tenant/batch.
3. Chuẩn hóa đường dẫn và chống `..`; kiểm tra path sau resolve nằm dưới root dự kiến.
4. Chú ý symlink/hardlink và **TOCTOU** giữa kiểm tra path và mở/move; dùng quyền filesystem chặt, `NOFOLLOW_LINKS` hoặc API theo file descriptor khi cần, theo đúng hỗ trợ của provider.
5. Worker xử lý dữ liệu chỉ nên có quyền **đọc input**, **ghi temp** và gọi publication API được kiểm soát; không phải worker nào cũng cần quyền move/overwrite thư mục published.
6. Không cho application service account xóa/ghi đè những archive objects đã được công bố theo retention policy nếu nghiệp vụ yêu cầu immutability.
7. Kiểm tra ACL/owner của target directory trước khi move; khi nhận lỗi permission, fail/alert thay vì fallback copy tới một thư mục ít bảo vệ hơn.
8. Không log token, signed URL, secret trong URI, dữ liệu khách hàng hoặc tên file nhạy cảm.

**Atomicity không đồng nghĩa authorization.** Worker giữ lock hoặc có quyền ghi path không phải bằng chứng nó được phép xử lý dữ liệu tenant tương ứng.

### Xóa file nguồn sau archive có cần được phê duyệt?

Nếu nguồn là dữ liệu audit hoặc cần replay nhiều lần, nên **giữ immutable archive** với retention và backup thay vì delete ngay. Với copy cross-filesystem, xóa nguồn là **bước riêng có audit** sau khi target đã verify, manifest hoàn tất và policy cho phép. Khi có legal hold, retention hoặc downstream phụ thuộc source URI, việc xóa phải tôn trọng các ràng buộc đó.

## 34. Runbook khi move thất bại hoặc state bị kẹt

Khi một file kẹt ở `READY_TO_ARCHIVE`, có `AtomicMoveNotSupportedException` hoặc source biến mất nhưng manifest chưa ARCHIVED:

1. **Khoanh vùng:** JobInstance/JobExecution, worker StepExecution, `fileId`, source version, checksum, owner epoch, source/target URI và thời điểm lỗi.
2. **Xác nhận processing outcome:** business DB đã commit đủ keys/values chưa; skip/filter có được phê duyệt; StepExecution thực tế ở trạng thái nào?
3. **Xem manifest:** state trước/sau, `claimed_by`, `lease_epoch`, `lease_until`, có recovery owner mới hay worker cũ vẫn active không?
4. **Quan sát source/target:** có file ở ready không, target đã xuất hiện chưa, checksum/size của từng file có khớp expected không?
5. **Kiểm tra filesystem:** source/target có cùng provider/mount không; thư mục đích có tồn tại/quyền ghi? Có open handles, quota đầy, lỗi NFS/SMB hoặc connectivity không?
6. **Xác định lỗi thuộc nhóm nào:** unsupported atomic move, permission, target collision, missing source, ambiguous both-exist, storage corruption hay timeout/transport.
7. **Không ghi đè target đã có:** nếu logical target path được một attempt khác tạo, kiểm tra identity/content và owner trước mọi action.
8. **Chọn recovery:** retry atomic move với owner hợp lệ; hoặc copy-temp-destination-verify-publish riêng; hoặc công nhận target đã đúng rồi CAS manifest.
9. **Ngăn stale workers:** dừng/quiesce process còn chạy, đảm bảo không có worker mất lease vẫn có quyền sửa result/archive.
10. **Đối soát:** source manifest, business output, archive target, JobRepository và nếu có, broker reply/outbox.
11. **Công bố/đóng incident:** chỉ sau khi tất cả điều kiện đạt; lưu logs, nguyên nhân, metric và test cần bổ sung.

**Không tự di chuyển mọi file `ready` sang `archive` để làm giảm backlog**, không purge `.part`/`.tmp` nếu chưa biết attempt còn sống, không sửa trực tiếp JobRepository thành `COMPLETED`, và không xóa nguồn để che lỗi target chưa được tạo.

### Một quyết định vận hành minh họa

~~~text
fileId = f042
manifest = READY_TO_ARCHIVE
business output = VERIFIED
ready/source.csv = MISSING
archive/source.csv = EXISTS
archive checksum = MATCH
active owner = NONE

=> Recovery coordinator có thể xác nhận move đã xảy ra
   theo protocol, CAS manifest -> ARCHIVED.
   Không import lại file chỉ vì manifest trễ.
~~~

Ngược lại, nếu checksum sai hoặc cả source và archive đều không tồn tại, **không** mark ARCHIVED. Cần điều tra storage/copy và khả năng khôi phục từ immutable source/backup.

## 35. Các lỗi thiết kế thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| Downstream thấy CSV đang copy dở | Copy trực tiếp vào tên public | Ghi temp ở đích, verify rồi atomic publish hoặc manifest |
| Archive file nhưng DB thiếu record | Move trước commit/validation | Archive step sau processing success và đối soát |
| DB đã đủ nhưng scheduler nhập lại file | Crash trước move; coi ready là chưa xử lý | Manifest + JobRepository + idempotent writer |
| Source mất nhưng step archive FAILED | Crash sau move trước metadata commit | Idempotent Tasklet verify target rồi recover |
| Hai workers cùng overwrite final | Tin rằng `ATOMIC_MOVE` có no-overwrite khi target tồn tại | Ownership/CAS + unique artifact, không phụ thuộc provider overwrite behavior |
| Cross-filesystem `ATOMIC_MOVE` lỗi | Rename không được hỗ trợ giữa mounts | Copy đến temp cùng destination FS, verify + publish |
| Move thành công rồi mất file sau power loss | Chỉ dựa atomic rename, bỏ qua durability | Fsync/persistence contract và crash tests phù hợp |
| Move file đang được reader dùng | Không đợi đóng stream hoặc owner quiescence | Close/check ownership, tách archive step |
| Job COMPLETED nhưng thiếu 1 partition output | Per-file publish trước global validation | Batch publication barrier/manifest |
| File đích khác nội dung ở retry | Cùng logical key nhưng khác source/rule version | Fail/alert, version + hash reconciliation |
| NFS chạy khác local | Giả định mọi mount hỗ trợ cùng rename semantics | Test đúng storage topology và failover |
| Object storage archive không atomic | Copy+delete được gọi là move | Immutable versions + conditional pointer |
| Lock còn nhưng worker đã chết | Nhìn tồn tại `.lck` thay vì lock state | OS lock ownership, không xóa sidecar bừa |
| Worker cũ vẫn move sau lease expiry | DB epoch không được storage kiểm tra | Single publisher/quiescence/fencing thực thi |
| Quá nhiều file .tmp orphan | Không có recovery retention policy | Cleanup theo manifest attempt + owner status |
| Rename bị fail do target directory | Không tạo/quản lý directory hoặc thiếu quyền | Preflight directory/ACL, fail rõ, không unsafe fallback |
| File archive đúng bytes nhưng DB xử lý sai | Chỉ verify SHA-256 của file | Business key/value reconciliation và StepExecution |

## 36. Bài thực hành cuối bài

Xây một pipeline Spring Batch 5.x/Java 17+ nhập 100 file CSV bất biến với tổng 1.000.000 records. Mỗi file có `fileId`, `sourceVersion`, checksum và expected record count trong manifest PostgreSQL; business output có unique key `(batchKey, transactionId)`.

**Phần A — Atomic publication của output**

1. Mỗi worker tạo output dưới tên temp riêng theo `fileId/attemptId` trên cùng filesystem với published.
2. Đóng writer, verify checksum/count và move qua `ATOMIC_MOVE`.
3. Viết một reader test chỉ mở tên final; xác minh nó không thấy partial CSV dưới filesystem hỗ trợ.
4. Thử `AtomicMoveNotSupportedException` bằng cách dùng hai volumes; **không** copy thẳng final, thay bằng copy-temp-dest + verify.
5. Dùng manifest `PUBLISHED` để giữ toàn batch ẩn cho tới khi đủ mọi partition.

**Phần B — Archive input sau Spring Batch**

6. Cho import step ghi DB theo chunk 200, archive tasklet chỉ chạy sau import success/validation.
7. Giả lập crash **trước move**; restart cùng JobInstance, đối soát và archive không import duplicate.
8. Giả lập crash **sau move nhưng trước metadata commit**; tasklet restart nhận ra target đúng checksum.
9. Tạo trạng thái cả source và target tồn tại; pipeline phải fail/quarantine thay vì ghi đè.

**Phần C — Nhiều process và vận hành**

10. Chạy hai manager JVM cùng giành một `fileId`; DB claim cho một owner thắng.
11. Pause worker A tới khi lease hết, worker B nhận quyền; test stale A không được công bố output sai.
12. Kiểm tra NFS/SMB/CSI nếu đó là storage production; ghi rõ được/không được hỗ trợ atomic move và behavior khi process crash.
13. Đo thời gian import, hash, move, manifest CAS, DB commit và toàn bộ thời gian tới `PUBLISHED`.
14. Đối soát per-file coverage, business values, archive hashes, JobRepository status và orphan temp files.

**Tiêu chí đạt:** không có file final bị đọc dở, không có business operation bị áp dụng sai hai lần khi retry, file đã archive có thể được xác nhận sau crash, và toàn batch chỉ PUBLISHED khi validation đủ. Chỉ thấy `ready` rỗng **không** được coi là điều kiện đạt.

## 37. Checklist trước production

- [ ] Đã phân biệt **publish output**, **archive input** và **claim file trước xử lý**.
- [ ] Filesystem/provider của chính cặp source/target hỗ trợ atomic move theo contract được kiểm thử.
- [ ] Không giả định `ATOMIC_MOVE` kết hợp `REPLACE_EXISTING` cung cấp no-overwrite hay CAS.
- [ ] Khi không hỗ trợ atomic rename, không silent fallback thành copy trực tiếp vào final.
- [ ] File output được ghi vào temp riêng từng attempt, đóng/flush và validate trước khi public.
- [ ] Khi yêu cầu crash durability mạnh, có policy `force/fsync`/storage phù hợp, hiểu giới hạn Java và network FS.
- [ ] Source file được producer bàn giao immutable, có `fileId`/snapshot/version và checksum đáng tin.
- [ ] Archive chỉ sau khi business processing đã commit và per-file validation đạt.
- [ ] Có state trung gian `READY_TO_ARCHIVE` và nhánh recovery source missing/target matches.
- [ ] Có xử lý rõ khi cả source/target cùng tồn tại, cùng mất hoặc checksum không khớp.
- [ ] Worker/process có ownership/claim hợp lệ, và không tự coi `Files.exists` là lock.
- [ ] Khi nhiều manager, có lease/epoch, single publisher hoặc fencing thực thi ở đúng nơi cần bảo vệ.
- [ ] Writer business idempotent theo logical operation; phát hiện duplicate khác nội dung.
- [ ] JobRepository/ExecutionContext, broker reply và filesystem move không bị nhầm là một transaction.
- [ ] Nếu một file có nhiều chunk hoặc partition, không archive khi chỉ một phần công việc hoàn tất.
- [ ] Batch publication barrier bảo vệ downstream khi cần **whole-batch visibility**.
- [ ] Với S3/Blob, dùng immutable object/version + manifest/pointer, không gọi copy+delete là atomic rename.
- [ ] Có kiểm thử crash trước/sau rename, target collision, cross-volume, NFS/SMB, hai process, stale worker.
- [ ] Có metric move failures, READY_TO_ARCHIVE age, target mismatch, ownership conflict và recovery duration.
- [ ] Có runbook điều tra source/target/DB/metadata trước khi xóa, replay hoặc công bố.

**Ghi nhớ:** **atomic move sau khi xử lý** là một công cụ mạnh để **công bố file hoàn chỉnh** hoặc **chuyển input sang archive bằng một thay đổi tên nguyên tử** trong phạm vi filesystem hỗ trợ. Nó không biến toàn bộ Spring Batch job thành một transaction chung. Giải pháp đúng phải liên kết **immutable input, commit và checkpoint rõ ràng, claim/ownership, idempotent writer, checksum, bước archive có thể chạy lại, trạng thái manifest và publication barrier**. Khi crash xảy ra ở khoảng giữa DB commit, move và cập nhật metadata, hệ thống cần **quan sát sự thật ở cả filesystem lẫn database rồi khôi phục có kiểm soát**, thay vì đoán từ một đường dẫn còn hay mất.
