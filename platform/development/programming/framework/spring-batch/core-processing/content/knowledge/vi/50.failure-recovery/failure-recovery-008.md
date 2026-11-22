# File system đầy: phục hồi Spring Batch khi hết dung lượng lưu trữ

## 1. Tình huống và mục tiêu

Một Job Spring Batch chạy lúc 02:00 để đọc dữ liệu từ database rồi xuất file CSV. Khi xử lý tới item thứ 700.000, writer ném lỗi:

~~~text
java.io.IOException: No space left on device
~~~

Một phần file đã được tạo. Các chunk trước đó có thể đã commit; chunk đang ghi có thể bị rollback; database lưu metadata có thể vẫn hoạt động hoặc cũng bị hết dung lượng. Nếu chỉ mở rộng ổ đĩa rồi khởi chạy một JobInstance mới, hệ thống có nguy cơ xuất trùng, thiếu dòng hoặc làm mất khả năng restart.

Trong **Spring Batch Core Processing**, xử lý **file system đầy** thuộc nhóm **Failure recovery**. Mục tiêu là phục hồi dung lượng, giữ được dữ liệu đã xử lý hợp lệ, tiếp tục đúng JobInstance và phát hiện sớm lần đầy ổ tiếp theo.

Bài học này trình bày:

- Các nguyên nhân của lỗi hết dung lượng và cách phân biệt với inode/quota/permission.
- Vùng lưu trữ nào trong batch pipeline có thể bị ảnh hưởng.
- Các bước chẩn đoán trên Linux, Windows và Kubernetes.
- Ý nghĩa của JobRepository, StepExecution và ExecutionContext sau lỗi.
- Hành vi của FlatFileItemReader/FlatFileItemWriter khi ghi file bị ngắt.
- Thiết kế staging/publish, idempotency và restart an toàn.
- Ví dụ cấu hình writer, chèn lỗi IOException, chiến lược kiểm thử.
- Monitoring, capacity planning và runbook phục hồi.

## 2. Phân biệt các lỗi storage

Không phải mọi lỗi ghi file đều do số GB trống bằng 0.

| Nguyên nhân | Triệu chứng | Cách kiểm tra |
| --- | --- | --- |
| Hết block vật lý | `No space left on device`, thường là ENOSPC | `df -h`, dung lượng khả dụng của mountpoint. |
| Hết inode | Không tạo được file mới dù còn nhiều GB | `df -i`, số file nhỏ trên filesystem. |
| Disk quota | `Disk quota exceeded`, thường là EDQUOT | Quota user/project/container/volume. |
| Temporary directory đầy | Sort, unzip, nén, upload hoặc tạo file tạm thất bại | `java.io.tmpdir` và thư mục scratch. |
| Volume của container đầy | Pod bị eviction hoặc writer báo lỗi | Ephemeral-storage limit, `emptyDir`, writable layer. |
| PVC/PV đầy | Dữ liệu persistent không ghi tiếp được | Capacity, quota và storage backend. |
| Filesystem read-only | `Read-only file system`/EROFS | Trạng thái mount, lỗi kernel/device. |
| Hết file descriptor | `Too many open files`/EMFILE | Ulimit và file handle leak. |
| Thiếu quyền | `Permission denied`/EACCES | Ownership, ACL, user chạy Job. |
| Database WAL/tablespace đầy | JDBC writer hoặc JobRepository báo lỗi SQL | Volume và log của database server. |

**Nguyên tắc đầu tiên:** truy ra chính xác **đường dẫn và mountpoint** của thao tác ghi bị lỗi. Root filesystem có thể còn trống trong khi volume output hoặc `/tmp` đã đầy. Ngược lại, output còn trống nhưng database lưu bảng `BATCH_*` không thể ghi metadata.

## 3. File system nằm ở đâu trong batch pipeline?

~~~text
                   Scheduler
                       |
                       v
                  Spring Batch Job
                       |
         +-------------+------------------+
         |             |                  |
         v             v                  v
      Input file     Temporary files     Output file
       / reader      sort / unzip        / writer
         |             |                  |
         +-------------+------------------+
                       |
                       v
                  JobRepository
                       |
                       v
                 JDBC metadata
             JobInstance / Execution
                ExecutionContext
                       |
                       v
                 Database storage
~~~

Tác động tùy chỗ đầy:

| Vùng lỗi | Khả năng hỏng | Điều phải xác minh |
| --- | --- | --- |
| Input directory | Job không tải thêm được input, snapshot không hoàn chỉnh | File đầu vào có nguyên vẹn và bất biến không? |
| Output directory | Writer chỉ ghi một phần file hoặc một dòng CSV | File hiện tại và checkpoint có khớp không? |
| Temp/scratch | File tạm bỏ dở, thao tác nén/sort không hoàn tất | Có đủ dung lượng để tạo lại temp hay không? |
| Log directory | Mất log chẩn đoán, logging bị chặn | Có số liệu OS và trạng thái JobRepository không? |
| Metadata database | Không ghi được `FAILED` hoặc ExecutionContext mới nhất | Trạng thái persisted và trạng thái process có mâu thuẫn không? |
| Business database | Commit hoặc rollback nghiệp vụ thất bại | Dữ liệu nào đã commit thực sự? |

Filesystem và transaction database thường là **hai resource khác nhau**. Không có bảo đảm một rollback JDBC sẽ tự loại bỏ các byte đã ghi ra file hoặc tác dụng của HTTP call.

## 4. Chuyện gì xảy ra khi lỗi giữa chunk?

Giả sử Step dùng `chunk(100)` và writer đang xuất dữ liệu 1–1.000:

~~~text
Execution #120
  item 1..100     -> write, COMMIT
  item 101..200   -> write, COMMIT
  item 201..300   -> write, COMMIT
  item 301..350   -> filesystem ENOSPC
                            |
                            v
                    chunk đang xử lý lỗi
                            |
                            v
              JobExecution có thể FAILED
~~~

Với reader và writer có hỗ trợ ItemStream, trạng thái checkpoint thường được cập nhật theo chu kỳ chunk. Các chunk trước có thể đã commit, còn chunk hiện tại thất bại. Tuy nhiên, **lỗi ghi file có thể xảy ra giữa một lần write**, khi một phần byte đã xuất hiện trên disk trước khi exception được ném.

Do đó, đừng mặc định file CSV chỉ còn đúng 300 dòng hoàn chỉnh. Phải phân biệt:

- Số item đã commit trong metadata của Step.
- Vị trí file mà writer đã lưu trong `ExecutionContext`.
- Số byte và dòng thực tế của output sau lỗi.
- Cơ chế buffering theo transaction và rollback/restart của writer.
- Có process bên ngoài nào sửa/move file trong lúc Job lỗi không.

Đặc biệt, không nên tự chỉnh các key nội bộ của writer trong ExecutionContext chỉ vì nhìn thấy file dài hơn checkpoint. Key và cách diễn giải state phụ thuộc chính implementation và version.

## 5. Quy trình phản ứng đầu tiên

1. **Dừng các trigger mới** đang ghi vào cùng volume để tránh tình trạng xấu thêm. Với Job đang chạy, dùng cơ chế stop có kiểm soát khi phù hợp.
2. Ghi lại tên Job, JobInstance ID, JobExecution ID, identifying JobParameters, Step lỗi, exception, đường dẫn file, host/pod và timestamp.
3. Xác minh worker cũ còn chạy hay đã chết, tránh hai execution cùng ghi file khi phục hồi.
4. Kiểm dung lượng byte, inode, quota và mountpoint thực tế.
5. Khôi phục headroom bằng mở rộng volume hoặc dọn/di chuyển dữ liệu **đã được xác nhận có thể dọn**. Giữ nguyên metadata và file staging cần restart.
6. Kiểm trạng thái database lưu `BATCH_*`, kiểm file input/output và checkpoint.
7. Quyết định restart cùng JobInstance, recover execution bị kẹt, retry bước publish hay dùng quy trình tái tạo file riêng.
8. Theo dõi execution mới tới trạng thái cuối; đối soát row count, checksum, business keys và kết quả downstream.

Tránh các thao tác như xóa toàn bộ thư mục working, truncate file staging hoặc xóa bảng `BATCH_*` chỉ để tạo thêm dung lượng. Những thao tác đó có thể phá hỏng checkpoint và lịch sử xử lý.

## 6. Chẩn đoán trên Linux

Các lệnh quan sát không sửa dữ liệu:

~~~bash
# Dung lượng của mọi filesystem đang mount.
df -h

# Inode khả dụng.
df -i

# Kiểm đúng thư mục đang chứa file output.
df -h /var/lib/batch/output
df -i /var/lib/batch/output

# Xem phân bố dung lượng trong khu vực batch.
du -h -d 1 /var/lib/batch

# File đã bị xóa tên nhưng còn process giữ handle.
lsof +L1

# Filesystem thật của output.
findmnt /var/lib/batch/output
~~~

Hai lệnh `df` và `du` có thể đưa ra số khác nhau: file bị xóa nhưng process còn mở vẫn giữ block; filesystem metadata/reserved space và mount khác nhau cũng ảnh hưởng kết quả.

**Chú ý log rotation:** nếu xóa file log lớn nhưng JVM/log appender vẫn giữ file handle, dung lượng có thể chưa được giải phóng. Dùng quy trình rotate/reopen/restart service phù hợp sau khi xác định an toàn. Không xóa file writer đang mở trong lúc Job chạy.

Trước khi chạy `du` toàn bộ một volume lớn, nên giới hạn vào thư mục nghi vấn vì lệnh này có thể tiêu tốn nhiều metadata I/O.

### Temporary directory cũng có thể đầy

Nhiều library sử dụng `java.io.tmpdir`, `TMPDIR` hoặc vùng tạm ứng dụng quy định. Một quy trình đọc 2 GB file ZIP có thể cần nhiều GB trống để giải nén, sort/merge và đóng gói kết quả. Việc output directory còn 20 GB không giúp nếu `/tmp` chỉ còn vài MB.

## 7. Chẩn đoán trên Kubernetes

Với batch chạy trong Pod:

~~~bash
kubectl get pods -n batch
kubectl describe pod batch-worker-abc -n batch
kubectl get events -n batch --sort-by=.lastTimestamp
kubectl get pvc -n batch

# Khi pod còn chạy:
kubectl exec -n batch batch-worker-abc -- df -h
kubectl exec -n batch batch-worker-abc -- df -i
~~~

Cần phân biệt:

- **Container writable layer**: dữ liệu có thể bị mất khi Pod mới được tạo.
- **emptyDir**: dùng ephemeral storage hoặc RAM tùy cấu hình; có thể gây eviction khi vượt giới hạn.
- **PVC**: storage bền vững, nhưng vẫn có quota và giới hạn khả năng mở rộng.
- **Database metadata**: có thể ở service khác; cần kiểm vùng chứa JDBC JobRepository riêng.
- **Stdout/stderr logs**: cũng có thể chiếm ephemeral storage trên node.

Pod được Kubernetes tạo lại **không đồng nghĩa** Spring Batch đã restart JobInstance. Controller Kubernetes quản lý Pod/Job theo tầng riêng, còn Spring Batch dùng JobRepository và JobParameters để xác định JobInstance.

Nếu file staging bị mất do lưu trên writable layer trong khi metadata JDBC còn giữ checkpoint, restart có thể không tái tạo file đúng cách. File đầu ra cần restart nên nằm trên storage đủ bền vững hoặc có quy trình xây lại an toàn.

## 8. Chẩn đoán trên Windows

Trong PowerShell, có thể kiểm dung lượng bằng:

~~~powershell
Get-PSDrive -PSProvider FileSystem
Get-Volume

Get-CimInstance Win32_LogicalDisk |
    Select-Object DeviceID, Size, FreeSpace
~~~

Hãy kiểm đúng ổ đĩa chứa output, log và thư mục TEMP của **tài khoản dịch vụ** chạy ứng dụng. Windows có thể báo “There is not enough space on the disk” thay vì cụm tiếng Anh ENOSPC thường thấy trên Linux.

## 9. Nếu JobRepository không thể ghi metadata

Trong điều kiện bình thường, một Step gặp IOException sẽ được Spring Batch đưa về trạng thái lỗi và metadata được lưu:

~~~text
StepExecution: FAILED
JobExecution:  FAILED
ExitStatus:    FAILED
~~~

Nhưng nếu volume của database cũng đầy hoặc JVM bị kill giữa lỗi, bảng metadata có thể vẫn hiển thị:

~~~text
StepExecution: STARTED
JobExecution:  STARTED
~~~

`STARTED` trong database **không đủ chứng minh process còn chạy**, và cũng **không thể tự coi là FAILED**.

Quy trình cần làm:

1. Xác minh process, Pod hoặc worker sở hữu execution đã thật sự dừng.
2. Xác định những transaction, file writes và side effects đã hoàn tất.
3. Khôi phục dung lượng và đảm bảo JobRepository hoạt động.
4. Áp dụng cơ chế recovery metadata phù hợp với phiên bản Spring Batch.
5. Chỉ restart khi checkpoint và dữ liệu có thể tiếp tục an toàn.

Spring Batch 6.x có API `JobOperator.recover(JobExecution)` hỗ trợ xử lý execution bị kẹt `STARTED` sau shutdown đột ngột, nhưng chỉ dùng sau khi xác minh worker cũ không chạy. Với Spring Batch 5.2.x, cần quy trình phù hợp phiên bản; không sửa trực tiếp cột `STATUS` của bảng `BATCH_JOB_EXECUTION` để qua bước kiểm tra.

## 10. FlatFileItemWriter và khả năng restart

Để xuất file text/CSV, `FlatFileItemWriter` hỗ trợ `ItemStream` và ghi nhận trạng thái trong `StepExecution.ExecutionContext`. Ví dụ **Spring Batch 5.2.x**, Java 17:

~~~java
import java.nio.file.Path;
import java.time.LocalDate;

import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemWriter;
import org.springframework.batch.item.file.builder.FlatFileItemWriterBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
FlatFileItemWriter<ExportRow> ordersWriter(
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    // Chặn input không phải ngày hợp lệ trước khi dùng làm tên file.
    LocalDate.parse(businessDate);

    Path output = Path.of(
        "/var/lib/batch/output",
        "orders-" + businessDate + ".csv.part");

    return new FlatFileItemWriterBuilder<ExportRow>()
        .name("ordersWriter")
        .resource(new FileSystemResource(output))
        .lineAggregator(row -> row.id() + "," + row.amount())
        .saveState(true)
        .transactional(true)
        .build();
}
~~~

`ExportRow` là model nghiệp vụ của ứng dụng, ví dụ Java record có `id()` và `amount()`. Thư mục output trong ví dụ cần được cấu hình cho môi trường thực.

| Cấu hình | Tác dụng |
| --- | --- |
| `@StepScope` | Tạo writer cho từng StepExecution, giảm nguy cơ chia sẻ state giữa nhiều luồng chạy. |
| `name("ordersWriter")` | Cung cấp tên ổn định cho key trong ExecutionContext. |
| `saveState(true)` | Cho phép writer lưu state phục vụ restart. |
| `transactional(true)` | Hỗ trợ buffer ghi theo transaction trong đường xử lý chuẩn; **không biến filesystem và JDBC thành một transaction phân tán**. |
| Tên file theo businessDate | Giữ cùng artifact staging cho những execution thuộc cùng JobInstance. |
| Hậu tố `.part` | Dấu hiệu file còn trong quá trình tạo, downstream chưa nên đọc. |

Writer có các tùy chọn như `appendAllowed` và `shouldDeleteIfExists` liên quan tới file có sẵn hoặc khi restart. Không bật append tùy tiện khi file đã bị ghi dở; hãy giữ state/config tương thích với hành vi restart của writer và kiểm output sau sự cố.

**Không nên đổi tên staging file sang một tên mới theo JobExecution ID mỗi khi restart**, trừ khi đang triển khai một giao thức xuất nhiều file riêng có cơ chế đối soát. Checkpoint writer có thể gắn với resource đã sử dụng trước đó.

## 11. Input file cũng phải được giữ nguyên

Nếu Job dùng `FlatFileItemReader` hoặc `MultiResourceItemReader`, checkpoint của reader chỉ còn đáng tin cậy khi:

- Resource đầu vào vẫn tồn tại và không bị ghi đè.
- Nội dung, encoding, thứ tự dòng và danh sách file đầu vào giữ ổn định.
- Reader lưu state bằng `saveState(true)` và được đăng ký theo Step scope phù hợp.
- Tên/pattern của file input không đột ngột chọn thêm những file mới trong lúc restart.
- Không có cleanup job khác xóa input sau khi phần đầu đã được xử lý.

Có thể lưu checksum, kích thước và version của input snapshot vào audit nghiệp vụ để xác minh trước khi restart. Với nguồn thay đổi liên tục, cần chiến lược checkpoint theo business key hoặc snapshot thay vì chỉ dựa vào offset/dòng.

## 12. Staging và publish sau khi Job thành công

Cách xuất file an toàn hơn là viết vào artifact trung gian và chỉ công bố file hoàn chỉnh:

~~~text
Job bắt đầu
    |
    v
orders-2026-11-16.csv.part
    |
    +-- FAILED --> giữ staging để kiểm/restart
    |
    +-- COMPLETED
           |
           v
   Kiểm row count, checksum, schema
           |
           v
   Đảm bảo file đã đóng
           |
           v
      Atomic rename
           |
           v
orders-2026-11-16.csv
    |
    v
Downstream mới được phép đọc
~~~

Ví dụ Java NIO:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

Path staging = Path.of(
    "/var/lib/batch/output/orders-2026-11-16.csv.part");
Path published = Path.of(
    "/var/lib/batch/output/orders-2026-11-16.csv");

Files.move(
    staging,
    published,
    StandardCopyOption.ATOMIC_MOVE);
~~~

Giới hạn:

- Atomic rename thường cần hai đường dẫn thuộc **cùng filesystem** và filesystem hỗ trợ `ATOMIC_MOVE`.
- Nếu bị `AtomicMoveNotSupportedException`, không âm thầm fallback sang copy rồi tuyên bố đã publish atomically.
- Rename không tự bảo đảm `fsync` dữ liệu xuống thiết bị lưu trữ trước sự cố mất nguồn.
- Việc đồng thời publish file và cập nhật database khác resource cần giao thức riêng, chẳng hạn manifest/version marker hoặc outbox.

Nếu Job đã `COMPLETED` nhưng bước publish sau đó lỗi vì disk đầy, nên thiết kế **retry publish riêng**. Một JobInstance đã hoàn thành thường không được restart bằng cùng identifying JobParameters.

## 13. Quyết định restart sau khi dung lượng đã được khôi phục

| Trạng thái hiện tại | Hành động |
| --- | --- |
| `FAILED` và checkpoint/file/input hợp lệ | Restart cùng JobInstance. |
| `STOPPED` sau dừng có kiểm soát | Xác minh policy rồi restart. |
| `STARTING`/`STARTED`/`STOPPING` | Xem worker còn chạy không; không tự mở execution mới. |
| `STARTED` nhưng process đã chết | Cần quy trình recovery metadata phù hợp phiên bản. |
| `COMPLETED` | Không restart lô cũ; nếu publish lỗi, retry publish. |
| `ABANDONED` | Không restart theo cơ chế thông thường; cần quy trình vận hành khác. |
| Output hỏng/mất trong khi checkpoint còn | Chưa đủ điều kiện restart; cần đối soát hoặc quy trình tái tạo. |

Với Spring Batch **5.2.x**, dùng `JobOperator.restart(long executionId)` sau khi đã xác minh điều kiện:

~~~java
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.launch.JobOperator;

public class SafeRestartService {

    private final JobExplorer jobExplorer;
    private final JobOperator jobOperator;

    public SafeRestartService(
            JobExplorer jobExplorer,
            JobOperator jobOperator) {
        this.jobExplorer = jobExplorer;
        this.jobOperator = jobOperator;
    }

    public long restartFailed(long failedExecutionId) throws Exception {
        JobExecution previous =
                jobExplorer.getJobExecution(failedExecutionId);

        if (previous == null) {
            throw new IllegalArgumentException(
                    "Unknown execution: " + failedExecutionId);
        }

        if (previous.getStatus() != BatchStatus.FAILED) {
            throw new IllegalStateException(
                    "Execution is not FAILED: " + previous.getStatus());
        }

        // Kiểm disk, input, output và worker phải được thực hiện
        // bởi tầng vận hành trước khi đến đây.
        return jobOperator.restart(failedExecutionId);
    }
}
~~~

`restart` tạo JobExecution mới cho **cùng JobInstance**. Nếu tạo identifying timestamp hoặc `run.id` mới, Spring Batch có thể tạo JobInstance mới, bắt đầu đọc lại từ đầu và ghi duplicate.

Với Spring Batch **6.x**, API điều hành dùng `jobOperator.restart(previousJobExecution)`, trong đó execution có thể đọc qua `jobRepository.getJobExecution(id)`. Khác biệt cú pháp không thay đổi nguyên tắc identity/checkpoint.

### Restart không bảo đảm exactly-once ở mọi hệ thống

Nếu writer ghi cả file, database và gửi một request HTTP, mỗi resource có thể commit hoặc thất bại tại thời điểm khác nhau. Khi làm lại có thể gửi lại request đã thành công. Cần idempotency key ổn định theo nghiệp vụ, unique constraint, outbox hoặc quy trình đối soát.

## 14. Retry IOException có giúp không?

Retry ngay trong một Step có thể hữu ích với một số lỗi I/O tạm thời; nhưng **filesystem thật sự đầy** thường không tự hết sau vài mili giây.

| Cơ chế | Dùng khi |
| --- | --- |
| Retry trong Step | Lỗi ngắn, writer có thể gọi lại an toàn, retry limit và backoff nhỏ. |
| Restart Job | Dung lượng đã được giải quyết và metadata/file state còn phù hợp. |
| Retry publish | Job đã hoàn thành nhưng thao tác đổi tên/công bố file lỗi. |
| Tái tạo artifact theo quy trình riêng | Output mất hoặc hỏng, checkpoint không còn tương thích. |
| Recover metadata | Execution stale `STARTED` sau crash, worker đã thực sự ngừng. |

Không nên cấu hình `retry(IOException.class)` với số lần quá lớn cho ENOSPC cố định. Nó có thể giữ transaction lâu, sinh nhiều log và tăng áp lực trên một volume vốn đã đầy.

## 15. Kiểm thử bằng cách chèn lỗi có kiểm soát

Không nên cố tình lấp đầy ổ đĩa chung của máy developer hoặc CI. Tách hai lớp kiểm thử:

**Lớp 1 — Fault injection:** ném `IOException` có chủ đích trong ItemWriter để kiểm logic `FAILED`, checkpoint, restart và dữ liệu cuối.

**Lớp 2 — Storage test cách ly:** dùng volume/quota nhỏ chỉ dành riêng cho bài test để mô phỏng ENOSPC thực, kiểm hành vi ghi được một phần byte, flush, close và filesystem. Cần quản lý tài nguyên test sao cho không ảnh hưởng workload khác.

Ví dụ wrapper `ItemStreamWriter` trong Spring Batch 5.2.x:

~~~java
import java.io.IOException;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.batch.item.Chunk;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemStreamException;
import org.springframework.batch.item.ItemStreamWriter;

public final class DiskFullFaultWriter<T>
        implements ItemStreamWriter<T> {

    private final ItemStreamWriter<T> delegate;
    private final AtomicBoolean faultEnabled;
    private final AtomicInteger chunkCalls = new AtomicInteger();

    public DiskFullFaultWriter(
            ItemStreamWriter<T> delegate,
            AtomicBoolean faultEnabled) {
        this.delegate = delegate;
        this.faultEnabled = faultEnabled;
    }

    @Override
    public void write(Chunk<? extends T> chunk) throws Exception {
        int call = chunkCalls.incrementAndGet();

        if (faultEnabled.get() && call == 3) {
            throw new IOException(
                "Simulated ENOSPC: No space left on device");
        }

        delegate.write(chunk);
    }

    @Override
    public void open(ExecutionContext context)
            throws ItemStreamException {
        delegate.open(context);
    }

    @Override
    public void update(ExecutionContext context)
            throws ItemStreamException {
        delegate.update(context);
    }

    @Override
    public void close() throws ItemStreamException {
        delegate.close();
    }
}
~~~

Wrapper phải là writer được Step quản lý để các callback ItemStream được forward tới delegate. Nếu reader và writer cần checkpoint, cả hai phải được đăng ký và dùng state tương thích. Trong integration test, đặt cờ lỗi là `true` cho execution đầu, sau khi Job `FAILED` đặt thành `false` rồi restart.

**Giới hạn:** lỗi được ném **trước** lần ghi chunk thứ ba, nên không mô phỏng tình huống kernel đã viết một phần dòng trước khi báo ENOSPC. Dùng storage test cách ly khi cần xác minh trường hợp partial write.

### Kiểm thử failed rồi restart

Giả sử có 10 item, chunk size 2, reader có thứ tự ổn định và writer vừa nêu:

~~~java
// Khung assertion trong Spring Batch 5.x:
// - JDBC JobRepository test có đầy đủ BATCH_*.
// - Reader/writer lưu state và output nằm trong thư mục test.
// - Không xóa metadata giữa hai execution.

JobParameters params = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16")
        .toJobParameters();

faultEnabled.set(true);
JobExecution first = launcherTestUtils.launchJob(params);
assertEquals(BatchStatus.FAILED, first.getStatus());

// Khôi phục storage giả lập, dùng cùng JobInstance:
faultEnabled.set(false);
long resumedId = jobOperator.restart(first.getId());

JobExecution resumed = jobExplorer.getJobExecution(resumedId);
assertEquals(first.getJobInstance().getInstanceId(),
             resumed.getJobInstance().getInstanceId());

// Nếu chạy bất đồng bộ, phải chờ trạng thái cuối:
// assert COMPLETED; đọc file và kiểm đủ 10 key không trùng.
~~~

Chạy qua nhiều test độc lập thì dọn metadata **trước** mỗi test, nhưng không dọn giữa lần fail và restart. Với JobOperator bất đồng bộ, phải chờ execution đạt trạng thái terminal thay vì assert ngay khi lệnh restart trả về.

### Ma trận kiểm thử

| Điểm gây lỗi | Điều cần chứng minh |
| --- | --- |
| Trước khi mở file | Job fail an toàn; không làm mất input. |
| Sau ít nhất một chunk commit | Restart giữ phần đã commit, không lặp dữ liệu. |
| Giữa một dòng file | File không được publish dở; phục hồi theo writer/state. |
| Khi cập nhật ExecutionContext | Metadata và output được đối soát; không giả định khớp tự động. |
| Khi flush/close | Có xử lý trạng thái file và kết quả Job đúng. |
| Sau COMPLETED, trước publish | Retry publish độc lập. |
| Database metadata không ghi được | Execution có thể stale; recovery được kiểm soát. |
| Pod bị evict | Staging trên persistent storage vẫn còn, hoặc có chiến lược tái tạo. |

## 16. Monitoring để tránh hết dung lượng

Các tín hiệu thường dùng:

| Metric | Nguồn | Ý nghĩa |
| --- | --- | --- |
| `node_filesystem_avail_bytes` | Node exporter | Số byte khả dụng của mountpoint. |
| `node_filesystem_size_bytes` | Node exporter | Tổng dung lượng filesystem. |
| `node_filesystem_files_free` | Node exporter | Số inode còn trống. |
| `kubelet_volume_stats_available_bytes` | Kubelet khi hỗ trợ | Dung lượng khả dụng của volume Kubernetes. |
| Kích thước output/staging đang tạo | Metric tùy chỉnh | Phát hiện batch vượt kích thước dự kiến. |
| Job FAILED theo failure category | Log/metric Batch | Nhận biết sự cố storage từ sớm. |
| Tuổi file `.part` chưa publish | Scanner/audit | Tìm artifact bị bỏ quên sau lỗi. |

Ví dụ PromQL cho phần trăm dung lượng còn lại của mountpoint:

~~~promql
100 *
node_filesystem_avail_bytes{
  mountpoint="/var/lib/batch/output"
}
/
node_filesystem_size_bytes{
  mountpoint="/var/lib/batch/output"
}
~~~

Ngưỡng dưới 15% có thể là cảnh báo sớm, dưới 5% là mức nguy hiểm; các con số chỉ minh họa. Với volume rất lớn, nên kết hợp **byte còn lại** và **số byte dự kiến cần để hoàn thành Job**.

Một quy trình tạo file trung gian và copy sang volume khác có thể cần không gian lưu trữ cho cả hai bản. Nếu chỉ atomic rename trên cùng filesystem, thường không cần bản copy đầy đủ, nhưng vẫn cần headroom cho log, metadata và các Job đồng thời.

Công thức ước tính sơ bộ:

~~~text
expected_output_bytes
    ~= expected_record_count * average_bytes_per_record

required_available_bytes
    >= expected_output_bytes
     + temp_or_copy_overhead
     + concurrent_job_headroom
     + operational_safety_margin
~~~

Phải tính đến giá trị lớn bất thường của từng record và số Job chạy song song, thay vì chỉ dùng trung bình của một ngày bình thường.

## 17. Runbook phục hồi mẫu

| Bước | Thao tác | Kỳ vọng |
| --- | --- | --- |
| 1 | Nhận alert ENOSPC/EDQUOT hoặc Job FAILED | Có execution ID, Step, volume và timestamp. |
| 2 | Tạm ngừng trigger ghi vào volume | Không phát sinh thêm output làm nặng lỗi. |
| 3 | Kiểm worker cũ, mountpoint, byte/inode/quota | Xác định lỗi thực và tiến trình còn chạy hay không. |
| 4 | Mở rộng volume hoặc giải phóng dung lượng hợp lệ | Có đủ headroom cho lô còn lại. |
| 5 | Kiểm input, output staging, checkpoint và `BATCH_*` | Biết có thể restart an toàn hay không. |
| 6 | Nếu metadata còn STARTED sau crash, recover đúng quy trình | Không tạo execution song song với worker cũ. |
| 7 | Restart đúng JobInstance hoặc phục hồi publish | Không tạo lô mới ngoài ý muốn. |
| 8 | Kiểm Job COMPLETED và dữ liệu cuối | Row count, checksum và business keys đầy đủ, không trùng. |
| 9 | Publish file khi đã đóng/validate | Downstream nhận artifact hoàn chỉnh. |
| 10 | Lưu incident, bổ sung alert/capacity plan | Giảm khả năng lặp lại. |

Mẫu ghi nhận sự cố:

~~~text
Job: exportOrdersJob
Identity: businessDate=2026-11-16
Failed JobExecution: 120
Step: exportCsvStep
Storage: /var/lib/batch/output (PVC)
Cause: ENOSPC
Action: volume expanded; old writer process confirmed stopped
Metadata: FAILED, checkpoint persisted
Recovery: restart same JobInstance -> JobExecution 121
Validation: COMPLETED, row count and checksum matched
Publish: .part renamed after validation
~~~

Chỉ điền các trạng thái đã được xác minh. Nếu file staging mất hoặc checkpoint không còn đáng tin cậy, ghi blocker và chuyển sang quy trình đối soát/tái tạo, không ép restart để nhận trạng thái xanh.

## 18. Sai lầm thường gặp

**Chỉ kiểm root filesystem.** Output có thể nằm trên mount khác; luôn kiểm đường dẫn thất bại.

**Xóa file `.part` để lấy dung lượng.** Checkpoint có thể đang tham chiếu tới file đó; xóa làm mất khả năng tiếp tục.

**Xóa metadata `BATCH_*`.** Phá hỏng lịch sử JobInstance, ExecutionContext và kiểm soát duplicate.

**Retry IOException không giới hạn.** Disk vẫn đầy thì các lần thử lại không có tác dụng và có thể gây thêm tải.

**Coi rollback JDBC là rollback file.** File và database không tự cùng một ACID transaction.

**Cho downstream đọc file đang được ghi.** Có thể phát tán dữ liệu thiếu/truncated; dùng staging và publish.

**Đổi file output theo execution ID khi restart.** Có thể làm lệch checkpoint và artifact đang phục hồi.

**Bỏ qua `STARTED` stale.** Khi database không ghi được metadata hoặc process chết, trạng thái persisted có thể chưa cập nhật.

**Không kiểm inode/quota.** Dung lượng byte vẫn còn nhưng file mới không thể được tạo.

**Đặt output trên container writable layer mà yêu cầu restart sau Pod chết.** File có thể mất trong khi metadata JDBC vẫn còn.

**Giả lập ENOSPC trên ổ đĩa CI dùng chung.** Có thể làm hỏng workflow khác; dùng fault injection hoặc storage cách ly.

## 19. Bài tập thực hành

### Bài 1 — Chẩn đoán storage

Trong môi trường test, dùng `df -h`, `df -i`, `findmnt` và `du` để xác định mountpoint chứa output, log và temp. Giải thích vì sao ổ root còn dung lượng không đảm bảo volume output còn trống.

### Bài 2 — Fault injection theo chunk

Tạo Job đọc 10 item, chunk size 2 và xuất CSV. Dùng `DiskFullFaultWriter` gây lỗi trước lần ghi chunk thứ ba. Xác nhận Job `FAILED`, tắt lỗi rồi restart cùng JobInstance; file cuối đủ 10 ID không trùng.

### Bài 3 — Partial write trên volume riêng

Dùng volume test có quota nhỏ để phát sinh ENOSPC thật trong lúc writer ghi file lớn. So sánh kích thước file, số dòng hoàn chỉnh và checkpoint đã lưu; thử phục hồi theo cơ chế writer. Chỉ làm trên **storage test cách ly**.

### Bài 4 — Metadata và output tách volume

Đặt JobRepository JDBC trên volume khác output. Gây lỗi output rồi kiểm `JobExecution` và `ExecutionContext`; sau đó thử lỗi ở volume database trong môi trường riêng để khảo sát trạng thái stale.

### Bài 5 — Publish atomically

Ghi file `.part` rồi chỉ rename sang `.csv` khi Job COMPLETED và checksum/row count hợp lệ. Giả lập sự cố trước publish và chứng minh publish có thể retry mà không cần chạy lại JobInstance đã hoàn thành.

### Bài 6 — Kubernetes storage

Dùng PVC riêng cho output và `emptyDir` cho temp trong môi trường thử nghiệm. Quan sát khác biệt khi Pod được tạo lại, xác minh dữ liệu staging nào còn tồn tại và cách xử lý checkpoint tương ứng.

### Bài 7 — Cảnh báo trước khi đầy ổ

Xây dashboard dung lượng byte còn lại, inode còn lại, Job FAILED theo nguyên nhân và kích thước file staging. Đưa ra ngưỡng dựa vào **lô dữ liệu lớn nhất có thể chạy**, thay vì chỉ dựa trên phần trăm dung lượng.

## 20. Tài liệu tham khảo

- [Spring Batch — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html)
- [Spring Batch — Flat File Item Writer](https://docs.spring.io/spring-batch/reference/readers-and-writers/flat-files/file-item-writer.html)
- [Spring Batch — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html)
- [Spring Batch — JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html)
- [Spring Batch — Advanced Metadata Usage](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html)
- [Spring Batch 5.2 — FlatFileItemWriter Javadoc](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/item/file/FlatFileItemWriter.html)
- [Java NIO — Files.move](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/nio/file/Files.html)
- [Kubernetes — Local Ephemeral Storage](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/#local-ephemeral-storage)
- [Kubernetes — Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)

