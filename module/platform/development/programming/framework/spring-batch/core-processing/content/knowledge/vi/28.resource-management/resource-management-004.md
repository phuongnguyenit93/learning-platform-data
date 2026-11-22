# Tệp tạm và cleanup

Trong Spring Batch, một Job thường phải làm việc với nhiều tài nguyên dạng file: file đầu vào tải từ hệ thống ngoài, file giải nén, dữ liệu trung gian, file output đang ghi dở hoặc file staging chờ được công bố. Những file này có thể cần tồn tại qua nhiều Step, qua lần restart hoặc chỉ trong thời gian ngắn của một thao tác. Vì vậy, quản lý tệp tạm cần gắn với vòng đời thực thi của Job/Step và chính sách restart.

Cleanup không đơn giản là xóa mọi file có đuôi `.tmp` khi một Step kết thúc. Nếu xóa file đầu vào hoặc staging cần cho restart, Job có thể không tiếp tục được. Nếu giữ mọi file vô thời hạn, thư mục làm việc sẽ đầy dung lượng và lộ dữ liệu cũ. Thiết kế tốt cần xác định rõ ai tạo file, ai sở hữu, khi nào file hết giá trị, file có cần cho restart hay không và thao tác xóa có an toàn khi chạy lại không.

## 1. Các loại tệp tạm trong Batch Job

Một quy trình Batch có thể tạo nhiều loại file với vòng đời khác nhau:

| Loại file | Ví dụ | Vòng đời thường gặp |
|---|---|---|
| Bản sao input | File tải từ SFTP hoặc object storage về local | Giữ đến khi Job hoàn tất và không còn cần restart. |
| File giải nén | CSV được giải nén từ ZIP | Giữ trong các Step đọc dữ liệu, sau đó có thể xóa. |
| File trung gian | File sort, merge, normalize hoặc spill dữ liệu | Chỉ giữ trong các Step sử dụng nó. |
| Output staging | `orders.csv.part` đang được writer tạo | Giữ khi Step cần restart; chỉ publish khi output hoàn chỉnh. |
| File reject/error | Các dòng không hợp lệ cần xử lý lại | Giữ theo chính sách nghiệp vụ và retention. |
| File log/manifest | Checksum, metadata, trạng thái export | Giữ đủ lâu để audit hoặc đối soát. |

Điều đầu tiên cần làm là phân loại file theo mục đích. Một file có đuôi `.tmp` chưa chắc là file có thể xóa ngay; có thể đó là checkpoint hoặc output staging mà lần restart tiếp theo cần dùng.

## 2. Tách file tạm có thể xóa khỏi file cần restart

Nên phân biệt ít nhất ba nhóm:

- **Scratch file:** dữ liệu trung gian có thể tạo lại từ input và không cần giữ sau khi thao tác kết thúc. Có thể xóa khi resource đóng hoặc khi Step thành công.
- **Restartable staging:** file trung gian hoặc output đang ghi mà Job cần mở lại để tiếp tục sau lỗi. Phải giữ qua `FAILED`/`STOPPED` và chỉ xóa sau khi không còn cần restart.
- **Published artifact:** file output đã được xác nhận hoàn chỉnh và công bố cho hệ thống/người dùng. Không được xóa trong cleanup thông thường của Job; áp dụng retention riêng.

Ví dụ, file giải nén có thể là scratch nếu Job luôn tải và giải nén lại được. Nhưng nếu file input gốc đã bị xóa khỏi SFTP sau khi tải, bản sao local có thể là restartable input và cần giữ đến khi Job hoàn tất.

Với output, file `.part` thường là restartable staging. File `.csv` cuối cùng là published artifact. Cleanup sau thành công có thể xóa file `.part` còn sót và thư mục scratch, nhưng phải giữ file output cuối.

## 3. Đặt thư mục làm việc và quy tắc tên file

Không nên tạo file tạm tùy ý trong thư mục hiện hành của process. Hãy cấu hình một thư mục làm việc riêng cho ứng dụng, ví dụ:

```text
/var/lib/my-batch/
  work/
    order-import/
      instance-8124/
        input/
        scratch/
        staging/
  published/
    orders/
  rejected/
  archive/
```

Tổ chức theo Job và JobInstance giúp phân biệt tài nguyên giữa các lần nghiệp vụ. Một thư mục có thể gồm:

- `input/`: bản sao input cần giữ cho restart.
- `scratch/`: file trung gian có thể tạo lại.
- `staging/`: output chưa publish.
- `published/`: artifact đã hoàn tất.
- `rejected/`: file hoặc bản ghi lỗi cần đối soát.

Tên file nên có định danh ổn định và dễ truy vết, ví dụ:

```text
orders-2026-11-15-instance-8124.input.csv
orders-2026-11-15-instance-8124.output.part
orders-2026-11-15-instance-8124.output.csv
orders-2026-11-15-instance-8124.manifest.json
```

Không dùng một tên chung như `temp.csv` cho mọi execution. Hai Job chạy đồng thời có thể ghi đè hoặc xóa file của nhau.

### Dùng JobInstance identity thay vì JobExecution ID cho file cần restart

Một JobInstance có thể có nhiều JobExecution do restart. Nếu file cần được mở lại ở lần restart, đường dẫn của nó phải ổn định qua các JobExecution thuộc cùng JobInstance.

Không nên tạo tên staging cần restart chỉ từ `jobExecution.getId()`, vì restart tạo JobExecution mới. Có thể dùng JobInstance ID hoặc một business key ổn định từ identifying JobParameters để tạo thư mục. Nếu file chỉ tồn tại trong một lần thử và không cần restart, tên chứa JobExecution ID có thể phù hợp.

Ví dụ, `business.date` và `tenant.id` có thể tạo một operation key ổn định nếu chúng thực sự xác định một lần nghiệp vụ. Cần bảo đảm hai Job khác nhau không dùng chung namespace ngoài ý muốn.

## 4. Tạo file tạm bằng Java NIO

Với file scratch chỉ dùng trong một thao tác, `Files.createTempFile` tạo tên duy nhất và tránh đụng tên với execution khác:

```java
Path scratchFile = Files.createTempFile(
        configuredScratchDirectory,
        "orders-",
        ".tmp");

try {
    transformInput(scratchFile);
    consumeIntermediateFile(scratchFile);
} finally {
    Files.deleteIfExists(scratchFile);
}
```

`deleteIfExists` có tính idempotent ở mức thao tác xóa: file đã bị xóa thì lần gọi sau không tạo lỗi chỉ vì file không còn tồn tại. Tuy nhiên, cần xử lý các lỗi quyền truy cập, file đang được mở hoặc filesystem không sẵn sàng.

Với file cần restart, không nên tạo tên ngẫu nhiên mới mỗi lần Step mở. Hãy tạo một đường dẫn ổn định theo JobInstance hoặc lưu đường dẫn đã tạo trong `ExecutionContext`, sau đó mở lại đúng file đó khi restart.

### Tạo thư mục riêng cho một execution

```java
Path workDirectory = configuredWorkRoot
        .resolve("order-import")
        .resolve("instance-" + jobInstanceId)
        .normalize();

Files.createDirectories(workDirectory.resolve("scratch"));
Files.createDirectories(workDirectory.resolve("staging"));
```

`createDirectories` có thể gọi nhiều lần cho cùng đường dẫn. `jobInstanceId` phải được lấy từ metadata đáng tin cậy, không lấy trực tiếp một chuỗi tùy ý từ người dùng để ghép đường dẫn.

## 5. Giữ file input ổn định qua restart

Nếu Job đọc file từ SFTP, HTTP hoặc object storage, nên xác định thời điểm tải và cách giữ bản sao local.

Một quy trình an toàn thường là:

1. Tải input về file `.download.part` trong thư mục riêng của JobInstance.
2. Kiểm tra kích thước, checksum hoặc manifest theo hợp đồng nguồn.
3. Đóng file và đổi tên thành input staging hoàn chỉnh.
4. Lưu đường dẫn/checksum của input vào metadata hoặc một manifest bền vững.
5. Các Step sau chỉ đọc bản input đã xác nhận.
6. Chỉ xóa bản input khi Job hoàn tất và chính sách restart/retention cho phép.

Nếu process bị kill giữa lúc tải, file `.download.part` có thể chưa hoàn chỉnh. Khi restart, kiểm tra manifest/checksum và tải lại hoặc tiếp tục download theo khả năng của nguồn. Không đọc một file dở dang như input hoàn chỉnh.

Với input bất biến, có thể dùng checksum để xác nhận file restart đúng là file của lần nghiệp vụ ban đầu. Không chỉ dựa vào tên file, vì nguồn có thể thay thế nội dung tại cùng đường dẫn.

## 6. Dùng Resource trong Spring Batch

Spring Batch sử dụng abstraction `Resource` của Spring để làm việc với file và các nguồn dữ liệu khác. Một số implementation thường gặp:

| Resource | Nguồn |
|---|---|
| `FileSystemResource` | File trên filesystem. |
| `ClassPathResource` | Tài nguyên trong classpath. |
| `UrlResource` | Tài nguyên truy cập qua URL. |
| `ByteArrayResource` | Dữ liệu byte trong bộ nhớ. |
| `InputStreamResource` | Một InputStream đã được cung cấp. |

Ví dụ reader đọc file local:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['input.file']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("orderId", "customerId", "amount")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
```

Reader có thể mở resource trong vòng đời Step và lưu trạng thái đọc để restart. Việc xóa file input phải xảy ra sau khi mọi Step cần nó đã hoàn tất, không xóa trong lúc reader còn sử dụng.

Với `InputStreamResource`, cần lưu ý stream thường chỉ đọc được một lần. Nếu Job phải restart, nên dùng một resource có thể mở lại như file local hoặc URL/resource có semantics mở lại ổn định, thay vì giữ một InputStream đã tiêu thụ.

## 7. Vòng đời ItemStream và đóng resource

Reader/writer có thể triển khai `ItemStream`. Spring Batch quản lý các callback:

```java
public interface ItemStream {
    void open(ExecutionContext executionContext)
            throws ItemStreamException;

    void update(ExecutionContext executionContext)
            throws ItemStreamException;

    void close() throws ItemStreamException;
}
```

- `open`: mở file, stream hoặc cursor và khôi phục state.
- `update`: lưu state cần restart vào `ExecutionContext`.
- `close`: đóng handle, stream, cursor hoặc resource.

`close()` là nơi giải phóng resource đang mở, ví dụ đóng stream hoặc xóa một scratch file chỉ thuộc vòng đời reader. Nhưng không nên xóa input hoặc staging cần cho restart tại đây. `close()` cũng không được bảo đảm chạy khi JVM bị kill đột ngột.

Nếu tự triển khai reader/writer giữ file handle, hãy đóng trong `close()` và bảo đảm thao tác đóng an toàn khi được gọi trong các đường kết thúc khác nhau. Với resource được tạo bên ngoài stream, hãy xác định rõ thành phần sở hữu và thành phần chịu trách nhiệm xóa.

## 8. Dùng FlatFileItemWriter với output staging

Đối với output file, một cách phổ biến là ghi vào file staging trước, sau đó publish khi Step/Job hoàn tất. Ví dụ writer:

```java
@Bean
@StepScope
FlatFileItemWriter<OrderOutput> orderWriter(
        @Value("#{jobParameters['output.staging.file']}") String stagingFile) {

    return new FlatFileItemWriterBuilder<OrderOutput>()
            .name("orderWriter")
            .resource(new FileSystemResource(stagingFile))
            .delimited()
            .names("orderId", "amount", "tax")
            .saveState(true)
            .shouldDeleteIfExists(false)
            .build();
}
```

Đường dẫn `output.staging.file` cần ổn định cho cùng JobInstance nếu muốn restart tiếp tục output đã ghi. `saveState(true)` cho phép writer lưu vị trí/tiến độ cần thiết trong ExecutionContext. Không bật xóa file khi mở lại nếu mục tiêu là tiếp tục output cũ; cấu hình cụ thể cần khớp với semantics restart và phiên bản Spring Batch đang dùng.

Sau khi writer đóng thành công và Step/Job đã xác nhận hoàn tất, một bước publish có thể đổi tên file staging thành file đích. Đừng publish file khi writer còn mở hoặc trước khi mọi validation cần thiết đã hoàn thành.

## 9. Publish file hoàn chỉnh bằng atomic move

Nếu staging và output cuối nằm trên cùng filesystem và filesystem hỗ trợ atomic rename, có thể dùng `Files.move` với `ATOMIC_MOVE`:

```java
Files.move(
        stagingPath,
        finalPath,
        StandardCopyOption.ATOMIC_MOVE);
```

Đổi tên atomic giúp người tiêu thụ nhìn thấy file cuối sau khi nội dung đã hoàn chỉnh, thay vì đọc một file đang được ghi dở. Đây là lý do nên ghi vào `.part` hoặc staging trước.

Tuy nhiên, atomic move có giới hạn:

- Nguồn và đích cần ở cùng filesystem/volume theo khả năng của provider.
- Filesystem/provider có thể không hỗ trợ `ATOMIC_MOVE`.
- Hành vi khi file đích đã tồn tại phụ thuộc provider và options.
- Atomic rename không tạo transaction chung với JobRepository hoặc database nghiệp vụ.

Nếu `ATOMIC_MOVE` không được hỗ trợ, hãy quyết định rõ có cho phép fallback sang move thông thường hay phải fail để vận hành xử lý. Không âm thầm copy file lớn rồi xóa nguồn nếu người tiêu thụ có thể đọc file đích trong lúc copy.

### Publish cần idempotent

Process có thể chết sau khi move thành công nhưng trước khi JobRepository ghi nhận Step publish hoàn tất. Khi restart, Step có thể được gọi lại và staging file không còn tồn tại vì đã được move.

Publish Tasklet cần kiểm tra trạng thái:

- Nếu staging tồn tại và final chưa tồn tại: thực hiện move.
- Nếu staging không tồn tại nhưng final tồn tại và checksum đúng: coi output đã được publish.
- Nếu cả hai tồn tại: so sánh checksum/manifest và xử lý theo chính sách, không ghi đè tùy tiện.
- Nếu cả hai không tồn tại: báo lỗi vì output chưa được tạo hoặc đã bị xóa ngoài ý muốn.

Không chỉ dựa vào việc file đích tồn tại; file đó có thể thuộc một lần chạy khác hoặc có nội dung không hoàn chỉnh.

## 10. Tạo Publish Step và Cleanup Step

Nên tách ghi output, publish và cleanup thành các giai đoạn rõ ràng. Ví dụ flow:

```text
Download Input
      |
      v
Process Orders (write staging)
      |
      v
Validate Output
      |
      v
Publish Output
      |
      v
Cleanup Scratch
```

Publish chỉ chạy khi xử lý và validation thành công. Cleanup scratch có thể chạy sau publish. Nếu Job thất bại trước publish, staging cần được giữ nếu restart sẽ tiếp tục writer.

Ví dụ Tasklet publish:

```java
@Bean
@StepScope
Tasklet publishOutputTasklet(
        @Value("#{jobParameters['output.staging.file']}") String stagingName,
        @Value("#{jobParameters['output.final.file']}") String finalName) {

    return (contribution, chunkContext) -> {
        Path staging = Path.of(stagingName).toAbsolutePath().normalize();
        Path target = Path.of(finalName).toAbsolutePath().normalize();

        if (Files.exists(staging)) {
            verifyOutput(staging);
            Files.createDirectories(target.getParent());
            Files.move(staging, target, StandardCopyOption.ATOMIC_MOVE);
        } else if (Files.exists(target)) {
            verifyPublishedOutput(target);
        } else {
            throw new FileNotFoundException(
                    "Neither staging nor final output exists");
        }

        return RepeatStatus.FINISHED;
    };
}
```

Đây là khung minh họa; cần bổ sung kiểm tra root path được phép, xử lý file đích đã tồn tại, kiểm tra checksum và hành vi khi atomic move không được hỗ trợ. Không nhận đường dẫn tùy ý từ người dùng rồi move/xóa mà chưa kiểm tra phạm vi.

Cleanup Step nên chỉ xóa file đã được xác định là scratch và không còn được Step sau hoặc restart sử dụng. Có thể dùng Tasklet riêng để xóa danh sách resource đã được đăng ký trong Job/Step context.

## 11. Cleanup sau khi Job thành công

Khi Job hoàn tất thành công, có thể xóa:

- File giải nén có thể tạo lại.
- File sort/merge trung gian.
- Thư mục scratch riêng của JobInstance.
- File `.part` thừa đã được publish thành công.
- Bản sao input nếu retention policy cho phép và không còn cần cho audit/reprocess.

Không xóa:

- File output đã publish và còn trong retention.
- Reject file cần người dùng xử lý.
- Manifest/checksum cần đối soát.
- Input hoặc staging mà chính sách restart/recovery vẫn cần.

Có thể dùng `JobExecutionListener.afterJob` để thực hiện cleanup chỉ khi Job `COMPLETED`:

```java
public class SuccessfulJobCleanupListener implements JobExecutionListener {

    private final Path allowedWorkRoot;

    public SuccessfulJobCleanupListener(Path allowedWorkRoot) {
        this.allowedWorkRoot = allowedWorkRoot.toAbsolutePath().normalize();
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        if (jobExecution.getStatus() != BatchStatus.COMPLETED) {
            return;
        }

        ExecutionContext context = jobExecution.getExecutionContext();
        if (!context.containsKey("batch.scratch.directory")) {
            return;
        }

        Path scratchDirectory = Path.of(
                context.getString("batch.scratch.directory"))
                .toAbsolutePath()
                .normalize();

        if (scratchDirectory.equals(allowedWorkRoot)
                || !scratchDirectory.startsWith(allowedWorkRoot)) {
            throw new IllegalStateException(
                    "Scratch directory is outside the allowed work root");
        }

        deleteDirectoryTree(scratchDirectory);
    }
}
```

`batch.scratch.directory` phải được ghi vào Job ExecutionContext bởi code tin cậy trong lúc chuẩn bị Job. Listener chỉ được phép xóa thư mục con của root cấu hình. Không lấy đường dẫn từ payload hoặc tham số không được kiểm soát rồi xóa trực tiếp.

`afterJob` không chạy nếu process bị kill đột ngột. Ngoài ra, nếu cleanup ném exception sau khi Job đã kết thúc, cần quyết định cách biểu diễn cleanup failure và cách retry cleanup; không nên để một lỗi xóa file che mất kết quả xử lý nghiệp vụ đã commit.

## 12. Xóa thư mục đệ quy an toàn

Java NIO có thể duyệt cây thư mục và xóa file trước thư mục cha:

```java
static void deleteDirectoryTree(Path directory) {
    if (!Files.exists(directory)) {
        return;
    }

    try (Stream<Path> paths = Files.walk(directory)) {
        paths.sorted(Comparator.reverseOrder())
                .forEach(path -> {
                    try {
                        Files.deleteIfExists(path);
                    } catch (IOException exception) {
                        throw new UncheckedIOException(exception);
                    }
                });
    } catch (IOException | UncheckedIOException exception) {
        throw new IllegalStateException(
                "Could not clean directory " + directory,
                exception);
    }
}
```

Ví dụ này minh họa thứ tự xóa; triển khai production nên quyết định cách xử lý symlink, file đang được sử dụng và lỗi từng file. `Files.walk` mặc định không đi theo symbolic link, nhưng việc xóa symlink và kiểm tra root path vẫn cần được thiết kế cẩn thận.

Không gọi hàm đệ quy này trên root chung như `/tmp`, thư mục data hoặc thư mục được chia sẻ bởi nhiều Job. Hãy xóa đúng thư mục sở hữu của một JobInstance sau khi đã kiểm tra nó nằm dưới work root được cấu hình.

## 13. Cleanup khi Job thất bại hoặc bị stop

Không nên áp dụng cùng một chính sách xóa cho mọi trạng thái cuối.

| Trạng thái | Scratch có thể tạo lại | Input cần restart | Output staging cần restart |
|---|---|---|---|
| `COMPLETED` | Có thể xóa | Xóa/archive theo retention | Publish xong thì xóa phần thừa. |
| `FAILED` | Có thể xóa nếu không còn cần chẩn đoán | Giữ | Giữ nếu restart tiếp tục writer. |
| `STOPPED` | Tùy checkpoint và flow | Thường giữ | Thường giữ nếu Job sẽ restart. |
| `ABANDONED` | Xóa theo quy trình kết thúc | Có thể archive rồi xóa | Chỉ xóa sau khi xác nhận không restart. |
| Process bị kill | Không có callback cleanup | Giữ cho đến recovery decision | Giữ cho đến khi xác định trạng thái commit/restart. |

Với Job thất bại, có thể xóa scratch thuần túy nếu chắc chắn nó có thể tạo lại và không cần điều tra. Nhưng cần giữ log, manifest, reject file hoặc file trung gian cần thiết để khôi phục. Một lựa chọn an toàn là đánh dấu thư mục execution thành `FAILED` và để retention sweeper xử lý sau một khoảng thời gian.

Không xóa input hoặc output staging ngay trong `afterStep` khi Step thất bại nếu Job có thể được restart. Restart có thể cần chính file đó.

## 14. Cleanup trong close() khác cleanup sau Job

`ItemStream.close()` giải phóng resource mà reader/writer đang mở. Đây là cleanup ở cấp component:

```java
@Override
public void close() {
    if (reader != null) {
        reader.close();
    }
}
```

`JobExecutionListener.afterJob()` hoặc Cleanup Step quản lý resource ở cấp Job: xóa thư mục scratch, file input tạm hoặc staging không còn cần.

Không nên trộn hai trách nhiệm:

- `close()` đóng handle, stream, cursor và resource đang mở.
- Cleanup Step/listener xóa file hoặc thư mục đã hết vòng đời.
- Retention sweeper xử lý tài nguyên mồ côi sau crash hoặc quá hạn.

Một reader có thể được đóng khi Step kết thúc nhưng file input vẫn cần cho Step sau hoặc restart. Đóng file không có nghĩa là xóa file.

## 15. Cleanup khi process bị kill: orphaned temporary files

Nếu JVM bị kill, `finally`, `close()`, `afterStep()` và `afterJob()` có thể không chạy. File scratch hoặc staging có thể còn lại sau khi JobRepository ghi nhận execution stale hoặc sau khi process được khởi động lại.

Vì vậy, production thường cần một cơ chế dọn file mồ côi riêng, chẳng hạn:

- Một scheduled cleanup Job chạy định kỳ.
- Một tác vụ vận hành kiểm tra các thư mục execution quá hạn.
- Một startup recovery task kiểm tra file của execution đã kết thúc.
- Một retention service đọc manifest và JobRepository để xác định tài nguyên không còn được tham chiếu.

Không nên chỉ xóa mọi file có thời gian sửa đổi cũ hơn N ngày. Một Job dài ngày hoặc đang chờ phê duyệt có thể vẫn cần file cũ. Sweeper nên kết hợp tuổi file với trạng thái execution, owner/lease và loại resource.

### Manifest cho thư mục tạm

Mỗi thư mục JobInstance có thể có manifest mô tả file và mục đích:

```json
{
  "jobName": "orderImportJob",
  "jobInstanceId": 8124,
  "businessKey": "tenant-42-2026-11-15",
  "resources": [
    {
      "path": "input/orders.csv",
      "kind": "RESTARTABLE_INPUT",
      "checksum": "sha256:..."
    },
    {
      "path": "scratch/unpacked.csv",
      "kind": "SCRATCH",
      "checksum": "sha256:..."
    },
    {
      "path": "staging/orders.csv.part",
      "kind": "RESTARTABLE_OUTPUT",
      "checksum": null
    }
  ]
}
```

Manifest cần được cập nhật theo một quy tắc nhất quán và chỉ chứa path tương đối dưới thư mục sở hữu. Nó giúp sweeper phân biệt file cần giữ với file có thể xóa.

## 16. Retention và cleanup Job định kỳ

Cleanup định kỳ nên có chính sách retention theo loại tài nguyên:

| Resource | Chính sách retention ví dụ |
|---|---|
| Scratch file | Xóa sau khi Job hoàn tất; orphan có thể giữ vài ngày để điều tra. |
| Download staging chưa hoàn tất | Xóa sau khi xác nhận execution không còn hoạt động và quá thời hạn. |
| Restartable input | Giữ đến khi Job terminal và hết cửa sổ restart/reprocess. |
| Output staging | Giữ khi Job `FAILED`/`STOPPED`; xóa sau publish thành công hoặc abandon có kiểm soát. |
| Published output | Theo yêu cầu nghiệp vụ, audit và thời hạn lưu trữ. |
| Reject file | Theo SLA xử lý dữ liệu lỗi và chính sách lưu trữ. |
| Manifest/checksum | Giữ đủ lâu để audit, xác minh và đối soát. |

Một cleanup Job nên:

1. Đọc danh sách thư mục execution dưới work root.
2. Đọc manifest và xác định JobInstance/JobExecution liên quan.
3. Kiểm tra execution có đang chạy, đang dừng hoặc có lease còn hiệu lực không.
4. Chỉ chọn resource đã hết vòng đời và vượt retention.
5. Ghi audit về những file được xóa.
6. Xóa theo thứ tự file rồi thư mục.
7. Ghi metric số file, tổng dung lượng và lỗi cleanup.
8. Có thể chạy lại an toàn nếu lần trước dừng giữa chừng.

Cleanup Job cũng là một Batch Job; nó cần idempotent và có giới hạn phạm vi rõ ràng.

## 17. An toàn đường dẫn và quyền truy cập

Cleanup có thể xóa dữ liệu quan trọng nếu đường dẫn được ghép hoặc kiểm tra sai. Một số nguyên tắc:

- Cấu hình work root ở phía ứng dụng, không nhận root path tùy ý từ JobParameters.
- Chuẩn hóa path bằng `toAbsolutePath().normalize()`.
- Xác nhận path cần xóa là thư mục con của root được phép và không bằng chính root.
- Dùng thư mục riêng theo JobInstance để tránh xóa tài nguyên của Job khác.
- Không follow symlink khi duyệt cây nếu không có yêu cầu rõ ràng.
- Không dùng wildcard delete trên thư mục chia sẻ.
- Giới hạn quyền filesystem cho user chạy Batch.
- Không lưu secret trong tên file hoặc manifest.
- Ghi audit cho thao tác xóa dữ liệu quan trọng.

Ví dụ kiểm tra path:

```java
static Path requireChildOf(Path allowedRoot, Path candidate) {
    Path root = allowedRoot.toAbsolutePath().normalize();
    Path target = candidate.toAbsolutePath().normalize();

    if (target.equals(root) || !target.startsWith(root)) {
        throw new IllegalArgumentException(
                "Path is outside the allowed work directory");
    }

    return target;
}
```

Kiểm tra lexical path bằng `normalize()` là một lớp bảo vệ, nhưng nếu có symbolic link hoặc thư mục do người dùng khác có thể thay đổi, cần kiểm tra filesystem thực tế và quyền truy cập phù hợp. Không coi việc `startsWith` đơn thuần là đủ trong môi trường có untrusted filesystem writers.

## 18. Dọn file khi nhiều Job chạy đồng thời

Nhiều Job hoặc nhiều replica có thể cùng sử dụng một work root. Cleanup phải biết quyền sở hữu resource.

Các biện pháp:

- Tạo thư mục riêng theo Job name và JobInstance ID.
- Không dùng chung file tạm có tên cố định.
- Ghi owner metadata gồm JobExecution ID, JobInstance ID, host/container và thời gian tạo.
- Dùng lease/lock nếu nhiều process có thể quản lý cùng một thư mục.
- Sweeper chỉ xóa khi owner không còn hoạt động và lease đã hết hạn.
- Tránh cleanup theo thời gian sửa đổi đơn thuần vì file đang được sử dụng có thể không thay đổi liên tục.

Với restart, JobExecution ID thay đổi nhưng JobInstance ID giữ nguyên. Do đó, manifest có thể lưu cả JobInstance ID và danh sách JobExecution ID đã sử dụng thư mục để phục vụ audit.

## 19. Xử lý lỗi cleanup

Cleanup có thể thất bại do file đang mở, permission denied, disk I/O error hoặc network filesystem không sẵn sàng. Cần xác định cleanup là yêu cầu bắt buộc hay công việc hậu xử lý có thể retry.

Hai mô hình thường dùng:

### Cleanup là một phần bắt buộc của flow

Nếu Job chỉ được xem là hoàn tất khi tài nguyên đã được dọn, dùng một Cleanup Step rõ ràng trước khi Job kết thúc. Cleanup Step có thể retry lỗi transient và fail nếu không thể xóa theo yêu cầu.

### Cleanup là tác vụ hậu xử lý

Nếu dữ liệu nghiệp vụ đã hoàn tất và việc xóa file có thể trì hoãn, ghi cleanup request hoặc để sweeper xử lý. Job chính vẫn phản ánh kết quả nghiệp vụ; cleanup failure được ghi metric/audit và có thể thử lại.

Không nên nuốt mọi `IOException` mà không ghi nhận. Điều đó khiến dung lượng đĩa tăng dần mà không có cảnh báo. Ngược lại, cũng không nên làm Job nghiệp vụ thất bại chỉ vì xóa một file scratch không còn quan trọng nếu có cơ chế cleanup bền vững riêng.

## 20. Không dùng deleteOnExit làm cơ chế cleanup chính

`File.deleteOnExit()` chỉ yêu cầu JVM xóa file khi JVM thoát bình thường. Nó không phù hợp làm cơ chế cleanup chính cho Batch service chạy lâu dài:

- File không được xóa ngay sau khi Step kết thúc.
- JVM có thể chạy nhiều ngày, khiến file tích tụ.
- Process bị kill hoặc máy crash có thể không chạy shutdown hook.
- Danh sách delete-on-exit có thể tăng theo số file.
- Không hỗ trợ retention theo JobInstance hoặc restart.

Hãy dùng `try/finally`, `ItemStream.close`, Cleanup Step, listener có điều kiện hoặc retention sweeper tùy vòng đời resource.

## 21. Kiểm thử vòng đời tệp tạm

Test cần xác nhận cả file được tạo, giữ lại khi cần restart và xóa đúng lúc.

Các trường hợp nên kiểm tra:

- Job thành công: scratch được xóa, output cuối còn tồn tại.
- Job thất bại: input và staging cần restart vẫn còn.
- Job bị stop: resource cần cho restart không bị xóa.
- Process bị kill: file mồ côi được nhận diện bởi sweeper sau khi xác minh execution không còn hoạt động.
- Publish Step chạy lại: file đã publish được xác minh và không bị tạo bản thứ hai.
- Cleanup chạy hai lần: lần thứ hai không lỗi chỉ vì file đã biến mất.
- Path traversal: path ngoài work root bị từ chối.
- Symlink: cleanup không xóa nhầm dữ liệu ngoài thư mục sở hữu.
- Hai Job đồng thời: cleanup của Job này không ảnh hưởng file của Job kia.
- File đang mở: cleanup báo lỗi hoặc trì hoãn theo chính sách, không xóa một phần không kiểm soát.
- Disk full/permission denied: lỗi được ghi nhận và có cơ chế retry hoặc cảnh báo.

Ví dụ unit test cho thao tác xóa idempotent:

```java
@Test
void cleanupCanRunMoreThanOnce() throws IOException {
    Path directory = Files.createTempDirectory("batch-cleanup-test-");
    Path file = Files.writeString(directory.resolve("scratch.tmp"), "data");

    deleteDirectoryTree(directory);
    deleteDirectoryTree(directory);

    assertThat(Files.exists(file)).isFalse();
    assertThat(Files.exists(directory)).isFalse();
}
```

Test này xác nhận thao tác xóa có thể gọi lại trên một thư mục đã xóa. Integration test cần bổ sung kiểm tra metadata Job, restart và file staging thực tế.

## 22. Những lỗi thường gặp

### Xóa input ngay khi reader đóng

Reader có thể đóng sau Step nhưng Job chưa hoàn tất hoặc còn cần file cho restart. Chỉ xóa input khi mọi consumer đã xong và chính sách restart cho phép.

### Xóa staging khi Job thất bại

Writer có thể cần mở lại file để tiếp tục. Giữ staging qua `FAILED`/`STOPPED` nếu nó thuộc hợp đồng restart.

### Dùng tên file tạm cố định

Các Job đồng thời có thể ghi đè hoặc xóa file của nhau. Namespace theo JobInstance/operation.

### Tạo tên mới theo JobExecution ID cho file cần restart

Restart tạo JobExecution mới nên có thể không tìm thấy file cũ. Dùng path ổn định theo JobInstance hoặc lưu path trong metadata.

### Publish khi writer chưa đóng

File có thể thiếu buffer cuối hoặc đang được ghi. Đóng writer, flush và validate trước khi move.

### Nghĩ atomic move đồng nghĩa transaction với JobRepository

Filesystem rename không commit cùng database metadata. Process có thể chết giữa move và cập nhật trạng thái; publish Step cần idempotent và có checksum.

### Cleanup chỉ trong finally/close

Process kill không chạy cleanup callback. Cần sweeper/retention cho orphaned file.

### Xóa mọi file cũ hơn một số ngày

Job dài ngày hoặc đang chờ restart có thể vẫn cần file. Kiểm tra JobRepository, owner, manifest và retention theo loại resource.

### Dùng deleteOnExit trong server lâu dài

File chỉ được yêu cầu xóa khi JVM thoát và có thể tích tụ trong lúc ứng dụng chạy. Dùng cleanup theo vòng đời.

### Nuốt lỗi xóa file

Dung lượng có thể tăng mà không ai biết. Ghi log/metric và cung cấp retry hoặc cảnh báo.

## 23. Quy trình thiết kế tệp tạm và cleanup

Khi thêm một file vào Batch Job, hãy xác định vòng đời trước khi viết code:

1. Xác định file là input, scratch, restartable staging, reject hay published output.
2. Xác định component tạo file và component sở hữu việc đóng/xóa.
3. Chọn work root riêng và namespace theo JobInstance/operation.
4. Chọn tên ổn định cho file cần restart; dùng tên duy nhất cho scratch.
5. Lưu path/checksum/manifest nếu cần khôi phục hoặc đối soát.
6. Dùng Resource/ItemStream để mở, cập nhật checkpoint và đóng file đúng vòng đời.
7. Ghi output vào staging, đóng và validate trước khi publish.
8. Publish bằng atomic move khi filesystem hỗ trợ; làm publish Step idempotent.
9. Chỉ xóa scratch sau khi chắc chắn không còn Step hoặc restart cần nó.
10. Giữ input/staging khi Job `FAILED` hoặc `STOPPED` nếu restart cần.
11. Dùng Cleanup Step/listener cho Job kết thúc bình thường và sweeper cho process crash.
12. Kiểm tra path nằm dưới root được phép, không xóa symlink/resource ngoài phạm vi.
13. Áp dụng retention theo loại resource và trạng thái execution.
14. Ghi audit, metric và xử lý lỗi cleanup có thể retry.
15. Kiểm thử success, failure, stop, restart, process kill, concurrent Job và cleanup lặp.

| Nhu cầu | Cơ chế phù hợp |
|---|---|
| File chỉ dùng trong một thao tác | `Files.createTempFile` và `try/finally`. |
| Reader/writer giữ file handle | `ItemStream.open/close`. |
| File cần tiếp tục sau restart | Path ổn định theo JobInstance và checkpoint/manifest. |
| Output chỉ công bố khi hoàn chỉnh | Staging file, validate, rồi atomic move nếu hỗ trợ. |
| Xóa scratch sau Job thành công | Cleanup Step hoặc `JobExecutionListener` có điều kiện. |
| Dọn file sau process crash | Retention sweeper đối chiếu JobRepository và owner metadata. |
| Nhiều Job dùng chung work root | Thư mục riêng, ownership/lease và path validation. |

## Kết luận

Quản lý tệp tạm trong Spring Batch cần gắn với vòng đời resource, transaction và khả năng restart. Hãy phân loại scratch file, restartable input/staging và published artifact; dùng thư mục riêng cùng tên ổn định theo JobInstance cho file cần khôi phục; để `ItemStream` đóng handle đúng cách; ghi output vào staging rồi validate và publish; chỉ cleanup khi chắc chắn không còn Step hoặc restart cần resource. `close`, `finally` và `afterJob` không chạy khi process bị kill, vì vậy production cần retention sweeper đối chiếu JobRepository, manifest và owner trước khi xóa file mồ côi. Cleanup phải idempotent, giới hạn trong work root được phép và có audit/metric để tránh xóa nhầm hoặc tích tụ dữ liệu.
