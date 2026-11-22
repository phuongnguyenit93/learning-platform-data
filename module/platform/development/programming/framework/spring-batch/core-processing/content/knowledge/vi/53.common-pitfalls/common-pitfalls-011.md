# Không dọn file tạm sau failure trong Spring Batch

## 1. Vấn đề: Job FAILED nhưng file tạm còn lại

Trong Spring Batch Core Processing, các Step có thể tạo file trung gian để tải dữ liệu, giải nén, sắp xếp, chuyển đổi hoặc xuất kết quả. Nếu Job gặp lỗi, những file này không tự biến mất chỉ vì **BatchStatus** chuyển sang **FAILED**. Khi không có chính sách quản lý, thư mục tạm tăng dần, có thể làm đầy đĩa, khiến một Job khác đọc nhầm dữ liệu cũ hoặc làm lộ dữ liệu nhạy cảm.

Ví dụ một Job xuất đơn hàng:

~~~text
01:00 importOrdersJob khởi động
          |
          +-- downloadStep
          |     work/batch-A/input.csv
          |
          +-- transformStep
          |     work/batch-A/orders.csv.part
          |       Chunk 1: commit
          |       Chunk 2: commit
          |       Chunk 3: FAILED
          |
          +-- publishStep không chạy
          |
          v
      Job FAILED

Sau failure:
  input.csv       vẫn tồn tại
  orders.csv.part  vẫn tồn tại
  scratch/*.tmp    có thể vẫn tồn tại
~~~

Sau hàng chục lần lỗi, không chỉ dung lượng bị chiếm dụng mà các thư mục cũ còn gây khó khăn cho vận hành. Nhưng **xóa toàn bộ file ngay khi Job thất bại cũng nguy hiểm**: input snapshot và output staging có thể là dữ liệu cần thiết cho lần **restart**.

Vì vậy, bài toán không phải “xóa file tạm càng sớm càng tốt”, mà là **dọn đúng file, đúng thời điểm, đúng phạm vi sở hữu và vẫn giữ khả năng phục hồi dữ liệu**.

Bài này hướng dẫn phân loại file, thiết kế thư mục, hiểu cơ chế checkpoint của Spring Batch, cleanup theo lifecycle, tạo orphan sweeper sau crash, tránh xóa nhầm, kiểm thử failure/restart và giám sát dung lượng.

## 2. Phân loại file trước khi quyết định cleanup

Tên đuôi **.tmp** hoặc **.part** không đủ để biết file có thể xóa hay không. Cần xét vai trò thực tế:

| Loại | Ví dụ | Chính sách khi FAILED |
| --- | --- | --- |
| Scratch có thể tái tạo | File sort trung gian, cache giải nén, buffer phụ | Có thể dọn khi không còn worker sử dụng |
| Input snapshot | Bản sao bất biến của CSV/JSON đầu vào | Giữ nếu restart cần cùng input |
| Output staging | orders.csv.part đã ghi một số chunk | Giữ nếu writer restart dựa vào file/checkpoint |
| Download chưa hoàn tất | input.download.part | Tùy chiến lược resume hoặc tải lại |
| Rejected records | rejected-records.csv | Giữ theo quy trình xử lý lỗi và audit |
| Checksum/manifest | manifest.json, sha256.txt | Giữ để xác minh phục hồi/phát hành |
| Published artifact | published/orders.csv | Không xem là scratch; áp dụng retention riêng |
| Log/audit artifact | failure-report.json | Theo yêu cầu bảo mật và lưu trữ |

Có ba nhóm cần nhớ:

**Scratch:** file phụ có thể tái tạo từ dữ liệu bền vững. Đủ điều kiện dọn khi execution sở hữu nó đã dừng, không worker nào còn sử dụng.

**Staging:** file chưa công bố nhưng chứa công việc có giá trị. Ví dụ FlatFileItemWriter đã ghi và checkpoint nhiều chunk. Không xóa vô điều kiện sau failure.

**Artifact:** kết quả đã được xác minh và công bố cho downstream. Nó có vòng đời nghiệp vụ riêng, không thuộc quy tắc cleanup scratch.

Một thiết kế tốt đặt các nhóm này ở những thư mục khác nhau để giảm nguy cơ dọn nhầm.

## 3. Vì sao không cleanup gây ra lỗi thực tế?

### Hết dung lượng hoặc inode

Một lỗi để lại 2 GB file tạm; 30 lần thất bại có thể để lại khoảng 60 GB. Nếu có hàng triệu file nhỏ, filesystem còn có thể hết inode trước khi hết byte. Job mới gặp IOException hoặc không ghi được output.

### Đọc nhầm dữ liệu cũ

Hai lần chạy cùng dùng tên **/tmp/output.csv**. Lần sau có thể đọc hoặc append vào file cũ, khiến output chứa dữ liệu của hai kỳ nghiệp vụ dù Job hoàn tất bình thường.

### Publish nhầm file chưa hoàn chỉnh

Một tác vụ downstream quét toàn bộ thư mục bằng wildcard và nhìn thấy **orders.csv.part**, tưởng đó là file xuất xong. Hậu quả là hệ thống bên nhận xử lý một phần giao dịch.

### Xóa nhầm file của Job khác

Ngược lại, một cleanup quá rộng chạy khi Job A thất bại có thể xóa file mà Job B vẫn đang ghi nếu cả hai dùng chung work root.

### Tồn dư dữ liệu nhạy cảm

File input hoặc output có thể chứa thông tin cá nhân, giao dịch, tên khách hàng hay token bị ghi nhầm. Thư mục tạm không được xem là vùng “an toàn mặc định”.

### Mất dữ liệu phục hồi

Nếu cleanup xóa output staging trong khi JobRepository còn giữ ExecutionContext trỏ đến vị trí checkpoint, restart có thể thất bại hoặc tạo output không nhất quán.

Giải pháp cần phòng ngừa cả **không dọn** và **dọn quá mức**.

## 4. Phân biệt JobInstance và JobExecution để đặt tên thư mục

Spring Batch xác định **JobInstance** bằng tên Job và identifying JobParameters. Một lần restart sử dụng cùng identifying parameters nhưng tạo JobExecution mới.

Vì vậy nên chia thư mục:

~~~text
/data/batch/
  inbound/
    batch-A/
      input.csv

  work/
    batch-A/
      orders.csv.part
      attempts/
        1001/
          scratch/
        1002/
          scratch/

  published/
    batch-A/
      orders.csv
      manifest.json
~~~

Trong đó:

- **batch-A** là định danh ổn định của một lô/JobInstance.
- **orders.csv.part** là staging cần có thể mở lại ở lần restart.
- **1001** và **1002** là JobExecution ID khác nhau.
- **scratch/** thuộc từng attempt, có thể dọn sau khi attempt kết thúc.
- **published/** chỉ dành cho artifact đã xác minh.

Ví dụ identifying JobParameters:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("batchId", "orders-20261115", true)
        .addString("businessDate", "2026-11-15", true)
        .toJobParameters();
~~~

Không tạo identifying batchId mới chỉ để restart cùng kỳ, vì điều đó có thể tạo JobInstance khác và bỏ qua checkpoint của lần thất bại.

Đặt staging theo **batchId**, còn scratch theo **executionId** giúp tách vòng đời của file cần restart và file tạm có thể tái tạo.

## 5. Checkpoint và FlatFileItemWriter

Trong Step chunk-oriented, Spring Batch thường lưu trạng thái tại các ranh giới commit thông qua **ExecutionContext**. Reader/writer có khả năng **ItemStream** có thể đóng góp state phục vụ restart.

Ví dụ writer output staging:

~~~java
@Bean
@StepScope
FlatFileItemWriter<ExportRow> exportWriter(
        @Value("#{jobParameters['batchId']}") String batchId,
        WorkspacePaths paths) {

    Path staging = paths.stagingOutput(batchId);

    return new FlatFileItemWriterBuilder<ExportRow>()
            .name("ordersExportWriter")
            .resource(new FileSystemResource(staging.toFile()))
            .lineAggregator(row ->
                    row.orderId() + "," + row.amount().toPlainString())
            .saveState(true)
            .build();
}
~~~

Giả định **ExportRow** là record nghiệp vụ và **WorkspacePaths** kiểm soát đường dẫn. Thư mục cha phải được tạo trước khi writer mở file; input cũng phải ổn định khi restart.

**saveState(true)** cho phép writer lưu state cần cho restart trong ExecutionContext; nó không biến filesystem thành một phần của database transaction. Nếu file bị xóa, đổi đường dẫn hoặc bị ghi bởi process khác, metadata checkpoint có thể không còn tương ứng với nội dung file.

Một failure có thể xảy ra sau khi file được ghi nhưng trước khi checkpoint cập nhật. Vì vậy restart cần dựa vào logic phục hồi đã được kiểm thử của reader/writer, không đơn giản mở file ở chế độ append rồi tiếp tục.

Đặc biệt:

- Không xóa staging chỉ vì **BatchStatus.FAILED**.
- Không giả định **commitCount** tương đương số dòng file đã công bố.
- Không sửa thủ công ExecutionContext để bỏ qua các dòng lỗi.
- Không dùng cùng output resource cho hai JobInstance độc lập đang chạy.
- Nếu restart có thể chuyển sang pod khác, staging phải tiếp cận được trên storage phù hợp hoặc phải có cơ chế tái tạo được chứng minh.

## 6. Các trạng thái quyết định cleanup

| Trạng thái | Scratch riêng execution | Staging cần restart | Published output |
| --- | --- | --- | --- |
| COMPLETED, publish đã xác nhận | Dọn được | Dọn sau khi không còn phụ thuộc | Giữ theo retention |
| FAILED, có thể restart | Dọn sau khi worker ngừng | Giữ | Không publish output lỗi |
| STOPPED, sẽ resume | Dọn scratch tái tạo được | Giữ | Không thay đổi |
| STARTED / STARTING | Không dọn khi còn hoạt động | Không dọn | Không can thiệp |
| UNKNOWN hoặc không đọc được repository | Không xóa tự động | Giữ và cảnh báo | Giữ |
| ABANDONED | Theo quy trình vận hành | Chỉ xóa khi đã xác nhận không restart | Theo retention |
| Process crash trước listener | Sweeper xử lý sau xác nhận an toàn | Giữ tới khi có kết luận | Không publish |

**FAILED không phải trạng thái cho phép xóa mọi dữ liệu.** Người vận hành có thể restart batch sau vài giờ hoặc vài ngày. Retention cần thống nhất với thời gian cho phép khôi phục.

**COMPLETED cũng chưa chắc cho phép xóa staging ngay**, nếu việc đối soát hoặc công bố cho downstream chạy bất đồng bộ sau Job.

## 7. Quản lý đường dẫn an toàn

Một nguy cơ khác là lấy trực tiếp tham số người dùng làm path, tạo lỗi path traversal hoặc xóa nhầm thư mục cha.

Ví dụ một lớp quản lý đường dẫn:

~~~java
import java.nio.file.Path;
import java.util.regex.Pattern;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public final class WorkspacePaths {

    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,80}");

    private final Path root;

    public WorkspacePaths(
            @Value("#{environment.getProperty('app.batch.work-root')}")
            String configuredRoot) {

        this.root = Path.of(configuredRoot)
                .toAbsolutePath()
                .normalize();
    }

    public Path batchDirectory(String batchId) {
        if (batchId == null
                || !SAFE_ID.matcher(batchId).matches()) {
            throw new IllegalArgumentException("Invalid batchId");
        }

        Path path = root.resolve(batchId).normalize();

        if (!path.startsWith(root)) {
            throw new SecurityException("Outside workspace");
        }

        return path;
    }

    public Path stagingOutput(String batchId) {
        return batchDirectory(batchId)
                .resolve("orders.csv.part");
    }

    public Path scratchDirectory(String batchId, long executionId) {
        if (executionId <= 0) {
            throw new IllegalArgumentException("Invalid executionId");
        }

        return batchDirectory(batchId)
                .resolve("attempts")
                .resolve(Long.toString(executionId))
                .resolve("scratch");
    }
}
~~~

Cấu hình:

~~~properties
app.batch.work-root=/var/lib/my-batch/work
~~~

Đây là kiểm tra đường dẫn ở mức **lexical path**. Nó không tự phòng được tất cả tấn công symlink/junction khi người khác có quyền thay đổi thư mục. Production cần đặt workspace ở nơi chỉ service đáng tin có quyền ghi, giới hạn quyền filesystem và dùng cơ chế thao tác directory an toàn theo môi trường.

Không dùng một tên file cố định chung cho tất cả batch. Không nhận một đường dẫn tùy ý từ API quản trị rồi gọi recursive delete.

## 8. Dọn đúng scratch của một JobExecution

Có thể dùng Java NIO để xóa thư mục scratch của đúng attempt sau khi attempt không còn hoạt động:

~~~java
import java.io.IOException;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;

import org.springframework.stereotype.Component;

@Component
public class ScratchCleaner {

    private final WorkspacePaths paths;

    public ScratchCleaner(WorkspacePaths paths) {
        this.paths = paths;
    }

    public void clean(String batchId, long executionId)
            throws IOException {

        Path scratch = paths.scratchDirectory(batchId, executionId);

        if (!Files.exists(scratch)) {
            return;
        }

        Files.walkFileTree(scratch, new SimpleFileVisitor<>() {

            @Override
            public FileVisitResult visitFile(
                    Path file, BasicFileAttributes attrs)
                    throws IOException {

                Files.delete(file);
                return FileVisitResult.CONTINUE;
            }

            @Override
            public FileVisitResult postVisitDirectory(
                    Path dir, IOException error)
                    throws IOException {

                if (error != null) {
                    throw error;
                }
                Files.delete(dir);
                return FileVisitResult.CONTINUE;
            }
        });
    }
}
~~~

**Files.walkFileTree** mặc định không theo symbolic link bên trong cây, nhưng phải bảo đảm root và parent không bị một process không đáng tin thay bằng symlink hoặc junction trong lúc xóa. Nếu không kiểm soát được điều đó, cần một cơ chế cấp thư mục/handle an toàn hơn và không dựa vào ví dụ đơn giản này.

Cleaner's scope cố ý không bao gồm:

- input snapshot;
- file orders.csv.part của JobInstance;
- published output;
- scratch của một execution khác.

Không nuốt **IOException** âm thầm. Trên Windows, file đang mở có thể không xóa được; trên Linux, một file đã unlink có thể vẫn giữ dung lượng nếu process còn giữ file descriptor.

## 9. Dùng JobExecutionListener để cleanup bình thường

**JobExecutionListener.afterJob** là vị trí hữu ích để dọn scratch sau khi Job kết thúc bình thường hoặc qua đường lỗi framework quản lý:

~~~java
import java.io.IOException;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class FileCleanupListener implements JobExecutionListener {

    private static final Logger log =
            LoggerFactory.getLogger(FileCleanupListener.class);

    private final ScratchCleaner cleaner;

    public FileCleanupListener(ScratchCleaner cleaner) {
        this.cleaner = cleaner;
    }

    @Override
    public void afterJob(JobExecution execution) {
        String batchId =
                execution.getJobParameters().getString("batchId");
        Long executionId = execution.getId();

        if (batchId == null || executionId == null) {
            log.warn("Cannot resolve scratch cleanup ownership");
            return;
        }

        try {
            cleaner.clean(batchId, executionId);
        } catch (IOException ex) {
            log.error(
                    "Scratch cleanup failed for batchId={}, executionId={}",
                    batchId, executionId, ex);
            // Ghi thêm sự kiện retry cleanup nếu cần.
        }

        if (execution.getStatus() != BatchStatus.COMPLETED) {
            log.info(
                    "Keep restartable staging after status={}, batchId={}",
                    execution.getStatus(), batchId);
        }
    }
}
~~~

Gắn listener vào Job:

~~~java
@Bean
Job exportJob(
        JobRepository repository,
        Step prepareStep,
        Step exportStep,
        Step publishStep,
        FileCleanupListener cleanupListener) {

    return new JobBuilder("exportJob", repository)
            .start(prepareStep)
            .next(exportStep)
            .next(publishStep)
            .listener(cleanupListener)
            .build();
}
~~~

Cách này có ý nghĩa rõ ràng: **chỉ dọn scratch tái tạo được của attempt hiện tại**, giữ file staging nếu Job FAILED.

Tuy nhiên, listener không phải cơ chế cleanup tuyệt đối. Nếu process bị kill, mất điện, OOM nghiêm trọng hoặc container bị dừng trước khi callback chạy, **afterJob có thể không được gọi**. Vì vậy phải có một tác vụ định kỳ dọn file mồ côi.

Đừng ném exception từ **afterJob** chỉ với hy vọng Spring Batch tự chuyển một Job COMPLETED thành FAILED. Nếu cleanup là một điều kiện nghiệp vụ bắt buộc cho Job thành công, hãy thiết kế một Step/flow có kết quả được kiểm soát thay vì phụ thuộc hiệu ứng của listener.

## 10. Dọn sau thành công: publish trước, cleanup sau

Đối với Job xuất file, có thể thêm bước **publishStep** sau khi writer Step đã hoàn thành và tài nguyên được đóng:

~~~text
Writer tạo orders.csv.part
             |
             v
Kiểm tra số dòng, checksum, business rules
             |
             v
Publish/promote thành orders.csv
             |
             v
Ghi manifest / trạng thái phát hành bền vững
             |
             v
Cleanup staging theo retention
~~~

Nếu filesystem hỗ trợ atomic rename cùng volume, có thể dùng:

~~~java
try {
    Files.move(
            stagingPath,
            publishedPath,
            StandardCopyOption.ATOMIC_MOVE);
} catch (AtomicMoveNotSupportedException ex) {
    throw new IllegalStateException(
            "Atomic publication required by the workflow", ex);
}
~~~

Các path và directory phải được chuẩn bị phù hợp. Không phải mọi filesystem hoặc network mount hỗ trợ **ATOMIC_MOVE**. Với object storage như S3, rename thường không phải một thao tác filesystem nguyên tử; có thể cần copy, verify và commit marker/manifest.

**Không tự động fallback sang copy rồi xóa** nếu downstream có thể đọc file đang copy. Một lựa chọn là copy vào một key/path staging riêng tại đích, kiểm tra checksum rồi mới đánh dấu published.

### Crash giữa publish và cập nhật JobRepository

Có thể xảy ra:

~~~text
1. Move orders.csv.part -> orders.csv thành công
2. JVM crash trước khi Spring Batch ghi Step COMPLETED
3. Restart publishStep
4. File orders.csv đã tồn tại, .part không còn
~~~

Filesystem và database JobRepository không mặc nhiên có transaction nguyên tử chung. Do đó **publishStep phải idempotent**: khi target đã tồn tại, xác minh target thuộc đúng batch và checksum/manifest khớp, rồi quyết định coi là đã công bố hay chuyển sang điều tra. Không xóa target và publish lại vô điều kiện.

Filename đúng chưa chứng minh nội dung đúng; việc xác minh cần một nguồn đáng tin cậy.

## 11. Orphan sweeper khi listener không chạy

Một **orphan sweeper** là tác vụ định kỳ tìm file không còn thuộc execution đang hoạt động, sau đó dọn theo chính sách. Không nên chỉ dùng tuổi file:

~~~bash
# Nguy hiểm khi dùng không có metadata/ownership:
find /data/batch/work -type f -mtime +1 -delete
~~~

File của Job FAILED hôm qua có thể cần restart hôm nay. Một scratch mới tạo cách đây mười phút lại có thể thuộc process đã crash. Tuổi file chỉ là một phần điều kiện.

Thuật toán an toàn:

~~~text
Cho mỗi candidate:
  1. Xác định batchId, executionId và loại file.
  2. Xác minh file nằm trong workspace được quản lý.
  3. Truy vấn JobRepository / JobExplorer.
  4. Nếu không truy vấn được metadata: KHÔNG XÓA.
  5. Nếu Job STARTING / STARTED / UNKNOWN: KHÔNG XÓA.
  6. Nếu execution đã kết thúc và hết grace period:
        chỉ dọn scratch tái tạo được.
  7. Nếu muốn dọn staging:
        cần bằng chứng publish hoàn tất hoặc
        restart không còn được cho phép theo retention.
  8. Ghi audit số file, bytes và kết quả cleanup.
~~~

Ví dụ dùng JobExplorer:

~~~java
JobExecution execution =
        jobExplorer.getJobExecution(jobExecutionId);

if (execution == null) {
    // Thiếu metadata: không đoán rằng file đã mồ côi.
    return;
}

BatchStatus status = execution.getStatus();

if (status == BatchStatus.STARTED
        || status == BatchStatus.STARTING
        || status == BatchStatus.UNKNOWN) {
    return;
}

// Còn phải xét loại file, thời gian an toàn,
// quyền sở hữu và khả năng restart.
~~~

JobRepository có thể còn báo **STARTED** sau khi process thực sự chết. Cần phối hợp heartbeat/lease, tình trạng node và quy trình vận hành để xác định execution đã dừng an toàn. Khi không chắc, **giữ file và cảnh báo**.

Nếu có nhiều scheduler instance cùng chạy sweeper, cần distributed lock hoặc cơ chế claim để tránh tranh cùng candidate. Giữa lúc check trạng thái và xóa file, một Job có thể restart; cần phối hợp lifecycle/ownership để tránh **time-of-check/time-of-use race**.

## 12. Retention không nên chỉ là một TTL chung

Ví dụ bảng retention:

| Loại | Mốc tính thời gian | Lưu ý |
| --- | --- | --- |
| Scratch per attempt | Execution đã terminal | Dọn sớm sau grace period |
| Input snapshot của batch FAILED | Job thất bại / case được mở | Giữ đủ lâu để restart và điều tra |
| Output staging .part | Publish đã xác minh hoặc restart chính thức đóng | Không xóa khi còn checkpoint phụ thuộc |
| Reject/quarantine report | Theo quy trình data quality | Có thể cần audit |
| Published artifact | Sau ngày công bố | Theo SLA downstream và chính sách lưu trữ |
| Manifest/checksum | Theo yêu cầu đối soát | Có thể giữ lâu hơn scratch |
| JobRepository metadata | Theo retention repository riêng | Không xóa metadata cần cho restart |

TTL 7 ngày cho staging chỉ hợp lý nếu không có Job nào được restart sau 7 ngày và tổ chức đã chấp nhận giới hạn đó. Không triển khai xóa tự động staging chỉ dựa trên timestamp mà thiếu quyết định nghiệp vụ.

Metadata và file cũng có vòng đời khác nhau. Không xóa BATCH_* tùy tiện cùng file tạm: có thể làm mất checkpoint hoặc lịch sử phục vụ điều tra.

## 13. Quyền filesystem và dữ liệu nhạy cảm

Một thư mục tạm vẫn có thể chứa dữ liệu cá nhân, giao dịch, khóa hệ thống hoặc log lỗi. Chính sách bảo mật cần:

- Dùng tài khoản dịch vụ có quyền tối thiểu trên work root.
- Không để thư mục world-readable nếu chứa dữ liệu nội bộ.
- Không ghi token/password vào tên file, nội dung tạm hoặc log.
- Bảo vệ volume, snapshot và backup bằng cơ chế mã hóa phù hợp.
- Đánh giá retention cho file chứa dữ liệu nhạy cảm.
- Không cho API nhận đường dẫn bất kỳ để xóa recursive.
- Theo dõi sự kiện xóa, lỗi quyền và truy cập không hợp lệ.
- Giữ manifest/checksum phục vụ audit, nhưng hạn chế lộ payload.

**Files.delete không phải lời bảo đảm xóa byte không thể khôi phục** trên mọi SSD/filesystem. Với yêu cầu xóa bảo mật cần dựa vào chính sách encryption, key lifecycle và tiêu chuẩn storage.

## 14. Khác biệt giữa các môi trường lưu trữ

### Linux/POSIX

Một file bị unlink có thể vẫn chiếm dung lượng khi process còn giữ descriptor mở. Vì vậy đã gọi delete không có nghĩa dung lượng khả dụng tăng ngay. Cần kiểm tra process giữ file và quyền thao tác.

### Windows

File đang được mở có thể bị khóa và không xóa/rename được. Cleanup phải bắt IOException, ghi metric và retry khi tài nguyên đã được đóng.

### NFS hoặc volume dùng chung

Semantics của cache, lock và atomic rename phụ thuộc backend. Không mặc định một thao tác chạy đúng trên local ext4 sẽ giống trên mọi NFS mount.

### Kubernetes

Dùng **emptyDir** cho scratch có thể tái tạo là hợp lý trong nhiều trường hợp; nhưng dữ liệu cần restart qua pod reschedule có thể cần PersistentVolume hoặc một nguồn dữ liệu bền vững độc lập. **emptyDir** không phải nơi đáng tin để giữ staging khi pod bị xóa.

### Object storage

Với S3/GCS hoặc hệ thống tương tự, rename thường được mô phỏng bằng copy/delete chứ không phải atomic move. Nên dùng object key staging, checksum, manifest và trạng thái publish rõ ràng. Lifecycle rule tự động phải tránh xóa object cần cho restart.

## 15. Failure trong Tasklet, chunk và partition

### Tasklet download

Tasklet có thể tải file thành **download.part** rồi chỉ đổi thành **input.csv** sau khi tải đủ và verify checksum. Nếu tải lỗi:

- Giữ download.part khi có cơ chế resume an toàn.
- Xóa và tải lại nếu không có resume nhưng nguồn còn bất biến.
- Không dùng download.part như input hoàn chỉnh.

### Chunk-oriented Step

Writer có thể đã checkpoint một số chunk. Không xóa resource có liên quan tới **ItemStream** và ExecutionContext trước khi quyết định restart. Nếu writer ghi filesystem ngoài transaction của JobRepository, cần test sự cố ở ranh giới commit.

### Multi-threaded Step

Scratch nên gắn thêm partition ID/worker ID để một worker không xóa file của worker khác. Nếu một partition FAILED nhưng partition khác vẫn STARTED, không dọn toàn bộ thư mục batch.

### Remote partitioning

Worker có thể ở một pod khác, dùng storage khác hoặc vẫn đang xử lý sau khi manager thấy lỗi. Cleanup cần xác minh worker đã dừng, lease đã hết và resource thực sự thuộc owner nào.

### File đã được downstream mở

Nếu downstream cần thời gian đọc, cleanup không nên xóa artifact theo thời điểm publish của producer. Dùng acknowledgement hoặc retention đã thỏa thuận.

## 16. Kiểm thử failure và restart

Một test tốt phải tạo file tạm **trước khi failure**. Nếu exception xảy ra trước lúc file được ghi, test sẽ không chứng minh cleanup hoạt động.

Fixture:

~~~text
Input: 7 bản ghi
Chunk size: 3
Lỗi có kiểm soát tại bản ghi #5

Execution 1:
  Chunk 1 (1,2,3) commit
  Chunk 2 gặp lỗi
  Job FAILED

Execution 2:
  Restart cùng identifying JobParameters
  Job COMPLETED
~~~

Assertion cần có:

1. Lần chạy đầu đạt BatchStatus.FAILED.
2. Scratch của JobExecution #1 được dọn hoặc được sweeper xử lý theo SLA.
3. Output staging và input snapshot cần restart vẫn tồn tại.
4. Không có published output được báo là hoàn chỉnh khi Job còn FAILED.
5. Lần thứ hai dùng **cùng identifying parameters**, tạo execution mới trên cùng JobInstance.
6. Output cuối có đủ bảy bản ghi đúng và không trùng.
7. File của batch khác và execution đang chạy không bị cleanup.
8. Cleanup khi file locked/permission denied có log và cơ chế thử lại.

Ví dụ skeleton integration test dùng Spring Batch Test và AssertJ:

~~~java
@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class TemporaryFileRecoveryTest {

    @Autowired
    private JobLauncherTestUtils launcher;

    @Autowired
    private WorkspacePaths paths;

    @Test
    void preservesStagingForRestart() throws Exception {
        String batchId = UUID.randomUUID().toString();

        // Fixture input và failure injection được chuẩn bị trước.
        JobParameters params = new JobParametersBuilder()
                .addString("batchId", batchId, true)
                .toJobParameters();

        JobExecution first = launcher.launchJob(params);

        assertThat(first.getStatus())
                .isEqualTo(BatchStatus.FAILED);

        assertThat(Files.exists(paths.stagingOutput(batchId)))
                .isTrue();

        assertThat(Files.exists(
                paths.scratchDirectory(batchId, first.getId())))
                .isFalse();

        // Hủy điều kiện lỗi trước lần restart.
        JobExecution restarted = launcher.launchJob(params);

        assertThat(restarted.getStatus())
                .isEqualTo(BatchStatus.COMPLETED);

        // Đối soát output published theo business key/checksum.
    }
}
~~~

Ví dụ cần Job và fixture được cấu hình tương ứng; **JobLauncherTestUtils** phải nhắm đúng Job và launcher đồng bộ. Test nên dùng workspace riêng, chẳng hạn với **@TempDir** được truyền vào cấu hình test, không bao giờ dùng path production.

### Test cleaner riêng

Tạo một cấu trúc:

~~~text
work/
  batch-A/
    orders.csv.part
    attempts/1001/scratch/a.tmp
  batch-B/
    attempts/1002/scratch/b.tmp
~~~

Khi gọi **clean("batch-A", 1001)**, chỉ a.tmp và thư mục scratch của execution 1001 bị xóa. orders.csv.part và b.tmp vẫn tồn tại.

Cần thêm test với batchId không hợp lệ, thư mục không tồn tại, symlink, file lock, quyền thiếu và backend metadata không khả dụng.

## 17. Monitoring cleanup

Cleanup nên có metrics như các thành phần vận hành khác:

| Metric | Mục đích |
| --- | --- |
| batch_temp_files_count | Số file tạm theo loại |
| batch_temp_bytes | Tổng dung lượng scratch/staging |
| batch_orphan_candidates | Số candidate cần xử lý |
| batch_cleanup_success_total | Số lần cleanup thành công |
| batch_cleanup_failure_total | Số lần cleanup lỗi |
| batch_cleanup_bytes_freed_total | Tổng dung lượng được giải phóng |
| oldest_temp_age_seconds | Tuổi file cần chú ý |
| filesystem_free_bytes | Dung lượng còn lại |
| filesystem_free_inodes | Inode còn lại khi filesystem hỗ trợ |

Không xem staging FAILED còn cần restart là leak giống scratch mồ côi. Nên phân loại theo file_type, job và outcome trong metric.

Tránh dùng batchId, executionId, path duy nhất làm label trong Prometheus vì cardinality cao. Những ID đó phù hợp hơn với log/audit có kiểm soát.

Cảnh báo khi work-root tăng liên tục, số cleanup errors vượt ngưỡng, sweeper không chạy, file quá hạn chưa có quyết định remediation hoặc volume còn quá ít dung lượng. Cảnh báo **không nên tự động kích hoạt xóa toàn bộ work-root**.

## 18. Sai lầm thường gặp

### Xóa toàn bộ thư mục trong catch

~~~java
try {
    runJob();
} catch (Exception ex) {
    deleteEverything(workRoot);
    throw ex;
}
~~~

Cách này có thể phá restart và xóa dữ liệu của Job khác. Phải phân loại file và giới hạn ownership.

### Chỉ cleanup trong finally hoặc afterJob

SIGKILL, container crash hoặc mất điện có thể khiến callback không chạy. Cần sweeper định kỳ.

### Chọn TTL mà không kiểm tra trạng thái

File cũ có thể còn cần restart. TTL chỉ là một phần điều kiện xóa.

### Dùng chung /tmp/output.csv

Nhiều execution có thể ghi/xóa chéo nhau. Cần đường dẫn theo batch và attempt.

### Công bố file .part

Downstream có thể đọc output chưa hoàn thành. Chỉ published artifact được coi là hoàn chỉnh.

### Xóa target rồi publish lại trong restart

Nếu file đã publish thành công trước crash, ghi đè có thể phá dữ liệu đúng. Cần xác minh bằng manifest/checksum và idempotency.

### Nuốt IOException khi xóa

File tiếp tục tích tụ mà hệ thống không phát hiện. Ghi log, metric và retry.

### Xóa khi JobRepository không truy vấn được

Không có metadata không có nghĩa file an toàn để xóa. Fail closed và cảnh báo.

## 19. Quy trình áp dụng trong production

1. Kiểm kê các file do từng Step tạo: input, scratch, staging, rejected, manifest và published.
2. Định nghĩa ownership theo **batchId**, **JobExecution ID**, partition hoặc worker.
3. Tách scratch tái tạo được khỏi staging phục vụ restart.
4. Chuẩn hóa đường dẫn và giới hạn quyền filesystem.
5. Đặt cleanup theo lifecycle cho scratch, không xóa staging theo trạng thái FAILED đơn thuần.
6. Xây sweeper sau crash, đọc JobRepository và xác nhận không còn owner đang hoạt động.
7. Thiết kế bước publish được verify và idempotent.
8. Xác định retention riêng cho input, staging, reject report và published artifact.
9. Kiểm thử crash giữa chunk, giữa publish và metadata update, restart và cleanup cạnh tranh.
10. Theo dõi dung lượng, file quá hạn, bytes freed và cleanup errors.

### Checklist nhanh

- [ ] Không có filename dùng chung giữa các batch độc lập.
- [ ] Staging có đường dẫn ổn định qua restart.
- [ ] Scratch có ownership theo attempt/partition.
- [ ] FAILED/STOPPED không xóa file cần cho checkpoint.
- [ ] Downstream chỉ đọc published, không quét staging.
- [ ] Listener cleanup có xử lý IOException.
- [ ] Sweeper không xóa khi trạng thái còn chạy/UNKNOWN hoặc metadata mất kết nối.
- [ ] Có kiểm soát path traversal, symlink, quyền thư mục và dữ liệu nhạy cảm.
- [ ] Có chính sách cleanup theo retention và workflow nghiệp vụ.
- [ ] Có test failure, restart, idempotency và output correctness.

## 20. Kết luận

**Không dọn file tạm sau failure** là một lỗi vận hành có thể tích tụ âm thầm trước khi khiến hệ thống hết dung lượng, đọc nhầm dữ liệu cũ hoặc lộ dữ liệu nhạy cảm. Nhưng **dọn toàn bộ ngay sau failure** cũng có thể xóa checkpoint resource và phá khả năng restart.

Thiết kế đúng phải phân biệt ba vòng đời: **scratch có thể dọn khi execution đã ngừng; input snapshot và staging cần giữ khi còn khả năng restart; published artifact có retention nghiệp vụ riêng**. Kết hợp cleanup bình thường, orphan sweeper sau crash, đường dẫn an toàn, publish idempotent và test failure/restart sẽ giúp Spring Batch tránh tồn dư dữ liệu mà vẫn bảo toàn tính chính xác của quá trình phục hồi.

