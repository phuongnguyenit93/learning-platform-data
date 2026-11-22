# Tasklet cleanup sau xử lý trong Spring Batch

Sau khi một Job xử lý dữ liệu, ứng dụng thường còn những tài nguyên tạm cần thu hồi: file trung gian, thư mục làm việc, dữ liệu staging, bản export chưa publish hoặc trạng thái khóa phục vụ riêng cho lô. Nếu để các tài nguyên này tồn tại mãi, dung lượng lưu trữ và database sẽ tăng, đồng thời việc vận hành các lần chạy tiếp theo trở nên khó kiểm soát.

Trong Spring Batch, một cách tổ chức rõ ràng là tạo **Tasklet Step dành riêng cho cleanup** và đặt nó sau các Step xử lý, kiểm tra hoặc publish kết quả. Tasklet thực hiện công việc dọn dẹp trong vòng đời được Job quản lý, có trạng thái thực thi riêng và có thể được restart khi cleanup thất bại.

Cleanup cần được thiết kế cẩn thận. Xóa file hoặc staging data quá sớm có thể làm mất dữ liệu cần cho restart hoặc điều tra. Một thao tác xóa trên filesystem cũng không tự rollback khi transaction database thất bại. Bài học này trình bày cách đặt cleanup đúng vị trí, triển khai Tasklet, quản lý transaction và restart, cũng như bảo đảm việc dọn dẹp an toàn và có thể quan sát.

## 1. Cleanup là giai đoạn nào trong Job?

Một Job xử lý dữ liệu thường có nhiều giai đoạn:

1. Chuẩn bị đầu vào và thư mục làm việc.
2. Đọc, xử lý và ghi dữ liệu.
3. Kiểm tra số lượng hoặc tính hợp lệ của kết quả.
4. Publish kết quả ra vị trí chính thức.
5. Dọn các tài nguyên tạm không còn cần thiết.

Cleanup thường nằm ở cuối luồng thành công, sau khi kết quả đã được ghi bền vững và các bước kiểm tra cần thiết đã hoàn tất.

~~~mermaid
flowchart TD
    A["Prepare input"] --> B["Process data"]
    B --> C["Validate / reconcile"]
    C --> D["Publish output"]
    D --> E["Cleanup Tasklet"]
    E --> F["Job completed"]
    B -. "Failure" .-> G["Job failed; giữ tài nguyên cần restart"]
    C -. "Failure" .-> G
    D -. "Failure" .-> G
~~~

Ví dụ một Job nhập dữ liệu có thể tạo file chuẩn hóa trong thư mục tạm. Sau khi dữ liệu đã được ghi vào database và đối soát thành công, Tasklet cleanup xóa file trung gian. Nếu Step nhập dữ liệu thất bại, cleanup không nên tự động xóa file cần thiết để restart hoặc điều tra.

### Những tài nguyên thường cần cleanup

| Tài nguyên | Ví dụ | Thời điểm có thể dọn |
|---|---|---|
| File tạm | File CSV đã chuẩn hóa, file trung gian | Sau khi kết quả chính thức đã được xác nhận |
| Thư mục làm việc | Thư mục riêng của một batch | Sau khi mọi Step cần dùng thư mục đã hoàn tất |
| Bảng staging | Các dòng staging theo batch ID | Sau khi dữ liệu đã được chuyển và đối soát |
| File export chưa publish | File tạm trước khi đổi tên hoặc upload | Sau khi publish thành công hoặc theo quy trình phục hồi |
| Lock hoặc lease nghiệp vụ | Trạng thái giữ quyền xử lý một lô | Khi công việc đã kết thúc và không còn cần khóa |
| Tài nguyên tạm bên ngoài | Upload session, temporary object | Sau khi hệ thống đích xác nhận kết quả |

Không phải mọi tài nguyên đều do Tasklet cleanup đóng. Reader, writer và các thành phần hỗ trợ ItemStream có vòng đời open, update, close riêng. Hãy để framework đóng các tài nguyên mà nó quản lý; Tasklet cleanup chỉ xử lý những tài nguyên nghiệp vụ hoặc tài nguyên tạm được giao cho giai đoạn cuối.

## 2. Vì sao nên dùng một Tasklet Step riêng?

Tasklet phù hợp với thao tác có phạm vi rõ ràng, chẳng hạn xóa file, xóa staging data theo mã lô, giải phóng trạng thái hoặc đánh dấu batch đã kết thúc.

Một Tasklet có hợp đồng:

~~~java
public interface Tasklet {
    RepeatStatus execute(
        StepContribution contribution,
        ChunkContext chunkContext
    ) throws Exception;
}
~~~

Mỗi lần execute được framework gọi trong vòng đời của Tasklet Step. Tasklet trả về:

- `RepeatStatus.FINISHED` khi công việc đã hoàn tất.
- `RepeatStatus.CONTINUABLE` khi cần được gọi lại để tiếp tục công việc.

Tasklet Step có transaction theo từng lần gọi Tasklet, dựa trên transaction manager được cấu hình cho Step. Với cleanup bằng JDBC, thao tác database có thể tham gia transaction đó. Với thao tác filesystem hoặc API bên ngoài, transaction database không tự hoàn tác các tác động đã xảy ra.

### Lợi ích của cleanup Step riêng

- **Có trạng thái riêng:** biết cleanup đã bắt đầu, hoàn tất hay thất bại.
- **Có thể restart:** nếu cleanup thất bại, Job có thể chạy lại Step đó theo metadata.
- **Có log và metrics riêng:** dễ phân biệt lỗi xử lý dữ liệu với lỗi dọn dẹp.
- **Có transaction rõ ràng:** các thao tác database có thể commit hoặc rollback theo lần gọi Tasklet.
- **Có vị trí rõ trong Job flow:** cleanup chỉ chạy khi luồng điều khiển đi đến Step đó.

Với cleanup quan trọng, đây là cách dễ theo dõi hơn việc giấu toàn bộ thao tác xóa trong một callback không có Step riêng.

## 3. Đặt cleanup sau các Step cần thiết

Một Job đơn giản có thể nối Step xử lý với Step cleanup bằng `next(...)`:

~~~java
@Bean
Job importCustomersJob(
        JobRepository jobRepository,
        Step processCustomersStep,
        Step validateOutputStep,
        Step cleanupStep) {

    return new JobBuilder("importCustomersJob", jobRepository)
        .start(processCustomersStep)
        .next(validateOutputStep)
        .next(cleanupStep)
        .build();
}
~~~

Trong flow này, cleanup chỉ được chạy sau khi Step xử lý và Step kiểm tra kết thúc theo đường đi bình thường. Nếu Step trước thất bại và Job không có transition đưa flow đến cleanup, cleanup sẽ không chạy.

Đây thường là hành vi phù hợp với tài nguyên cần giữ để restart. Tuy nhiên, nếu nghiệp vụ yêu cầu cleanup cả khi Job thất bại, hãy thiết kế một nhánh xử lý lỗi riêng và xác định chính xác tài nguyên nào được phép xóa trong nhánh đó.

### Chỉ cleanup sau khi kết quả đã bền vững

Trước khi xóa tài nguyên đầu vào hoặc trung gian, cần xác nhận:

- Writer đã ghi dữ liệu đích thành công.
- Các chunk cần thiết đã commit.
- Các Step đối soát đã hoàn tất.
- File hoặc dữ liệu đầu ra đã được publish ở vị trí chính thức.
- Audit hoặc thông tin cần cho vận hành đã được lưu.
- Không còn Step tiếp theo cần dùng tài nguyên tạm.

Ví dụ, nếu Job tạo file báo cáo rồi upload lên object storage, không xóa file local ngay sau khi bắt đầu upload. Chỉ cleanup sau khi hệ thống đích xác nhận upload thành công và file đã được kiểm tra theo yêu cầu.

### Flow có điều kiện

Với Job có nhiều nhánh, cần cấu hình transition để cleanup chỉ chạy ở những nhánh đã hoàn tất đúng điều kiện. Không nên nối cleanup một cách máy móc nếu một nhánh thất bại hoặc một nhánh cần giữ lại dữ liệu để điều tra.

Có thể dùng ExitStatus tùy chỉnh để phân biệt kết quả, nhưng phải xác định rõ nhánh nào được cleanup và nhánh nào phải giữ tài nguyên.

## 4. Viết Tasklet xóa file tạm

Ví dụ một Tasklet xóa file trung gian sau khi xử lý thành công:

~~~java
@Bean
Tasklet cleanupTemporaryFileTasklet(
        TemporaryFileService temporaryFileService) {

    return (contribution, chunkContext) -> {
        temporaryFileService.deleteProcessedTemporaryFiles();
        return RepeatStatus.FINISHED;
    };
}
~~~

Phần xóa file được đặt trong service để tách trách nhiệm truy cập filesystem khỏi cấu hình Step.

Một cách triển khai service đơn giản:

~~~java
@Service
public class TemporaryFileService {

    public void deleteIfExists(Path file) throws IOException {
        Files.deleteIfExists(file);
    }
}
~~~

`Files.deleteIfExists(...)` có tính idempotent ở mức thao tác: nếu file đã không còn tồn tại, lời gọi vẫn hoàn tất mà không báo lỗi chỉ vì file vắng mặt. Điều này hữu ích khi Tasklet được chạy lại sau một lần cleanup dở dang.

Trong ứng dụng thực tế, không nên hard-code đường dẫn file hoặc xóa theo wildcard rộng. Hãy giới hạn cleanup vào thư mục làm việc và mã batch cụ thể.

### Lấy đường dẫn từ JobParameters hoặc JobExecutionContext

Đường dẫn đầu vào hoặc thư mục làm việc thường được cung cấp lúc khởi chạy Job. Có thể dùng `@StepScope` để lấy giá trị runtime:

~~~java
@Bean
@StepScope
Tasklet cleanupWorkDirectoryTasklet(
        @Value("#{jobExecutionContext['workDirectory']}")
        String workDirectory,
        @Value("#{jobParameters['batchId']}")
        String batchId) {

    return (contribution, chunkContext) -> {
        Path root = Path.of(workDirectory)
            .toAbsolutePath()
            .normalize();

        Path marker = root.resolve("work-" + batchId + ".tmp")
            .normalize();

        if (!marker.startsWith(root)) {
            throw new IllegalArgumentException(
                "Cleanup path nằm ngoài thư mục làm việc."
            );
        }

        Files.deleteIfExists(marker);

        return RepeatStatus.FINISHED;
    };
}
~~~

Trong ví dụ:

- `workDirectory` được lưu ở JobExecutionContext bởi Step chuẩn bị.
- `batchId` là tham số nhận diện lô.
- Đường dẫn được chuẩn hóa trước khi xóa.
- Kiểm tra `startsWith(root)` giúp ngăn đường dẫn sau khi chuẩn hóa thoát ra ngoài thư mục được phép.
- File không tồn tại được coi là đã dọn xong.

Cần xác thực batch ID và quyền truy cập thư mục ở lớp đầu vào. Không cho phép người gọi truyền một đường dẫn tùy ý khiến Tasklet có thể xóa file ngoài vùng làm việc của Job.

## 5. Dọn cả thư mục làm việc

Một Job có thể tạo nhiều file trung gian trong một thư mục riêng cho từng batch. Khi cần xóa toàn bộ thư mục, nên dùng một hàm chuyên trách có kiểm tra đường dẫn.

Ví dụ minh họa:

~~~java
public void deleteWorkDirectory(Path workRoot, String batchId)
        throws IOException {

    Path root = workRoot.toAbsolutePath().normalize();
    Path target = root.resolve(batchId).normalize();

    if (!target.startsWith(root) || target.equals(root)) {
        throw new IllegalArgumentException(
            "Thư mục cleanup không hợp lệ."
        );
    }

    if (!Files.exists(target)) {
        return;
    }

    try (Stream<Path> paths = Files.walk(target)) {
        paths.sorted(Comparator.reverseOrder())
            .forEach(path -> {
                try {
                    Files.deleteIfExists(path);
                } catch (IOException ex) {
                    throw new UncheckedIOException(ex);
                }
            });
    } catch (UncheckedIOException ex) {
        throw ex.getCause();
    }
}
~~~

Đoạn mã duyệt cây thư mục và xóa từ phần tử sâu nhất lên thư mục cha. Cần giới hạn thư mục mục tiêu theo batch ID, kiểm tra quyền và tránh đi theo các symbolic link không mong muốn. Trong hệ thống có yêu cầu bảo mật cao, có thể dùng service quản lý file riêng với allowlist thư mục thay vì để Tasklet tự xây dựng đường dẫn.

Không xóa thư mục gốc dùng chung của ứng dụng. Chỉ xóa thư mục con được tạo riêng cho lần xử lý hoặc lô cụ thể.

## 6. Dọn staging data trong database

Một số Job ghi dữ liệu đầu vào vào bảng staging trước khi chuyển sang bảng nghiệp vụ. Sau khi dữ liệu được xử lý và đối soát, Tasklet có thể xóa staging rows của đúng batch.

Ví dụ:

~~~java
@Bean
@StepScope
Tasklet cleanupStagingTasklet(
        JdbcTemplate jdbcTemplate,
        @Value("#{jobParameters['batchId']}") String batchId) {

    return (contribution, chunkContext) -> {
        int deleted = jdbcTemplate.update(
            "DELETE FROM customer_import_stage WHERE batch_id = ?",
            batchId
        );

        contribution.incrementWriteCount(deleted);

        return RepeatStatus.FINISHED;
    };
}
~~~

Điều kiện `WHERE batch_id = ?` rất quan trọng. Không xóa toàn bộ bảng staging nếu bảng đó có thể chứa dữ liệu của các Job hoặc batch khác đang hoạt động.

Nếu JdbcTemplate dùng cùng DataSource và transaction manager của Step, câu lệnh DELETE tham gia transaction của Tasklet. Nếu Tasklet thất bại trước khi transaction commit, thao tác xóa có thể rollback cùng transaction.

### Xóa staging theo từng đợt

Một câu DELETE xóa hàng triệu dòng có thể tạo transaction lớn, giữ lock lâu và làm tăng transaction log. Với dữ liệu lớn, hãy xóa theo batch nhỏ.

Ví dụ service xóa tối đa một số dòng trong mỗi lần gọi:

~~~java
@Service
public class StagingCleanupService {

    private final JdbcTemplate jdbcTemplate;

    public StagingCleanupService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public int deleteNextBatch(String batchId, int limit) {
        return jdbcTemplate.update(
            """
            DELETE FROM customer_import_stage
            WHERE stage_id IN (
                SELECT stage_id
                FROM customer_import_stage
                WHERE batch_id = ?
                ORDER BY stage_id
                FETCH FIRST ? ROWS ONLY
            )
            """,
            batchId,
            limit
        );
    }
}
~~~

Cú pháp giới hạn số dòng trong DELETE phụ thuộc database. Ví dụ trên chỉ minh họa ý tưởng; cần thay bằng cú pháp tương ứng với hệ quản trị đang dùng và kiểm tra execution plan.

Tasklet có thể tiếp tục chạy theo từng batch:

~~~java
@Bean
@StepScope
Tasklet cleanupStagingInBatches(
        StagingCleanupService cleanupService,
        @Value("#{jobParameters['batchId']}") String batchId) {

    return (contribution, chunkContext) -> {
        int deleted = cleanupService.deleteNextBatch(batchId, 1000);

        contribution.incrementWriteCount(deleted);

        return deleted > 0
            ? RepeatStatus.CONTINUABLE
            : RepeatStatus.FINISHED;
    };
}
~~~

Với Tasklet trả về `CONTINUABLE`, framework gọi lại Tasklet để xử lý batch tiếp theo. Mỗi lần gọi có transaction theo cấu hình Tasklet Step. Khi không còn dòng nào cần xóa, Tasklet trả về `FINISHED`.

Nếu database hỗ trợ câu lệnh DELETE có giới hạn khác, hãy dùng cú pháp phù hợp. Không dùng thứ tự hoặc giới hạn không ổn định nếu các lần lặp có thể xóa nhầm dữ liệu của batch khác.

## 7. Cấu hình cleanup Step trong Spring Batch 5

Sau khi có Tasklet, tạo Step riêng bằng `StepBuilder`:

~~~java
@Bean
Step cleanupStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet cleanupStagingTasklet) {

    return new StepBuilder("cleanupStep", jobRepository)
        .tasklet(cleanupStagingTasklet, transactionManager)
        .build();
}
~~~

Sau đó nối vào Job:

~~~java
@Bean
Job customerImportJob(
        JobRepository jobRepository,
        Step importStep,
        Step reconcileStep,
        Step cleanupStep) {

    return new JobBuilder("customerImportJob", jobRepository)
        .start(importStep)
        .next(reconcileStep)
        .next(cleanupStep)
        .build();
}
~~~

Cấu hình này tạo một Step có tên ổn định là `cleanupStep`. Spring Batch lưu StepExecution riêng cho nó. Nếu cleanup thất bại, trạng thái lỗi có thể được tra cứu trong JobRepository và Job có thể được restart theo chính sách của Job.

Tên Step nên ổn định giữa các lần triển khai để metadata và restart history được nhận diện nhất quán.

## 8. Transaction của cleanup Tasklet

Tasklet Step chạy trong transaction manager được truyền vào phương thức `tasklet(...)`. Tuy nhiên, khả năng rollback phụ thuộc vào tài nguyên mà thao tác cleanup sử dụng.

| Thao tác cleanup | Có thể rollback cùng transaction database? | Ghi chú |
|---|---|---|
| DELETE staging qua JdbcTemplate cùng DataSource | Có | Nếu tham gia transaction manager của Step |
| UPDATE trạng thái batch trong cùng database | Có | Cùng điều kiện transaction |
| Xóa file bằng Files.delete | Không | Filesystem không tham gia transaction JDBC |
| Đổi tên file | Không tự động | Có thể cần thao tác bù hoặc retry |
| Xóa object trên object storage | Không tự động | Cần API idempotent và theo dõi trạng thái |
| Gọi API giải phóng tài nguyên | Không tự động | Hệ thống bên ngoài quản lý side effect |

### Xóa file không thể rollback bằng transaction database

Giả sử Tasklet thực hiện:

1. Xóa file tạm.
2. Xóa staging rows.
3. Cập nhật trạng thái batch.
4. Transaction database thất bại khi commit.

Database có thể rollback việc xóa staging rows và cập nhật trạng thái, nhưng file đã xóa không tự xuất hiện trở lại.

Vì vậy, không nên xem toàn bộ thao tác trong một Tasklet là nguyên tử chỉ vì Step có transaction. Với nhiều loại tài nguyên, cần thiết kế thứ tự thao tác và khả năng chạy lại.

### Chia cleanup thành các Step theo tài nguyên khi cần

Nếu cleanup gồm nhiều thao tác độc lập, có thể tách thành các Step:

- Xác nhận output đã publish.
- Xóa staging data trong database.
- Xóa file trung gian.
- Giải phóng tài nguyên bên ngoài.
- Ghi trạng thái cleanup hoàn tất.

Cách chia này tạo trạng thái rõ hơn khi một phần cleanup thất bại. Tuy nhiên, mỗi Step cần có thể chạy lại an toàn và flow phải xử lý đúng trường hợp Step trước đã hoàn tất.

## 9. Thiết kế cleanup idempotent

Cleanup thường được gọi lại khi Job restart. Một Tasklet tốt cần chịu được trường hợp tài nguyên đã được xóa ở lần chạy trước.

**Idempotent** có nghĩa là thực hiện lại cùng thao tác cleanup không làm trạng thái cuối trở nên sai hoặc tạo side effect không mong muốn.

Ví dụ:

~~~java
Files.deleteIfExists(temporaryFile);
~~~

Nếu file đã bị xóa, lần gọi tiếp theo vẫn hoàn tất.

Với staging data:

~~~sql
DELETE FROM customer_import_stage
WHERE batch_id = :batchId;
~~~

Nếu không còn dòng nào thuộc batch đó, câu lệnh xóa 0 dòng và vẫn thành công. Đây là hành vi phù hợp cho cleanup theo mã lô.

Với API bên ngoài, cần dùng mã yêu cầu hoặc idempotency key ổn định nếu API hỗ trợ. Không tạo một request ID mới cho mỗi lần restart nếu muốn hệ thống đích nhận diện đó là cùng một thao tác cleanup.

### Các quy tắc giúp cleanup có thể chạy lại

- Xóa theo batch ID hoặc resource ID cụ thể.
- Xem tài nguyên không tồn tại là trạng thái đã dọn nếu nghiệp vụ cho phép.
- Không dùng câu DELETE không có điều kiện giới hạn.
- Không xóa dữ liệu mà Step khác có thể vẫn đang sử dụng.
- Lưu trạng thái hoàn tất sau khi thao tác thực sự thành công.
- Nếu có nhiều thao tác, xác định thứ tự và khả năng tiếp tục sau khi một phần đã hoàn tất.
- Dùng API có hỗ trợ idempotency hoặc kiểm tra trạng thái trước khi gửi lại.

## 10. Restart khi cleanup thất bại

Giả sử Job có ba Step:

~~~mermaid
flowchart TD
    A["processStep: COMPLETED"] --> B["publishStep: COMPLETED"]
    B --> C["cleanupStep: FAILED"]
    C -. "Restart JobInstance" .-> D["cleanupStep chạy lại"]
~~~

Khi restart cùng JobInstance, Spring Batch có thể bỏ qua các Step đã hoàn tất theo chính sách restart mặc định và tiếp tục ở Step chưa hoàn tất nếu Step đó cho phép restart.

Trong ví dụ:

- Dữ liệu đã được xử lý và publish thành công.
- Cleanup thất bại khi xóa một file.
- JobExecution mới được tạo khi restart.
- Các Step đã hoàn tất thường không chạy lại.
- cleanupStep được thực thi lại.
- Nếu một số file đã xóa trước khi lỗi, Tasklet idempotent sẽ bỏ qua file không còn tồn tại và tiếp tục.

Đây là lý do cleanup cần được tách thành Step riêng và thao tác dọn dẹp phải có khả năng chạy lại.

### Nếu cleanup đã hoàn tất

Một Step đã COMPLETED thường không chạy lại khi restart cùng JobInstance. Đây là hành vi phù hợp nếu cleanup đã hoàn tất và không cần lặp.

Có thể cấu hình `allowStartIfComplete(true)` để cho phép Step đã hoàn tất được chạy lại khi JobInstance được restart:

~~~java
return new StepBuilder("cleanupStep", jobRepository)
    .tasklet(cleanupTasklet, transactionManager)
    .allowStartIfComplete(true)
    .build();
~~~

Chỉ bật tùy chọn này khi có yêu cầu rõ ràng. Cleanup phải idempotent và không được xóa tài nguyên mới được tạo bởi một lần chạy khác. Nếu không cần chạy lại Step đã hoàn tất, hãy giữ hành vi mặc định.

### Không xóa dữ liệu cần cho restart

Nếu cleanup xóa file nguồn trước khi Job hoàn tất, một Step trước đó có thể cần file đó khi restart nhưng không còn khả năng đọc lại.

Ví dụ, Job có Step nhập dữ liệu rồi Step đối soát đọc lại file gốc. Không xóa file cho đến khi cả hai Step hoàn tất. Nếu Job thất bại trước đối soát, file cần được giữ để restart.

## 11. Cleanup khi Job thất bại

Cleanup sau xử lý thường chỉ chạy trên đường thành công. Khi một Step thất bại, giữ tài nguyên tạm có thể hữu ích cho:

- Restart Job.
- Điều tra dữ liệu lỗi.
- Đối chiếu đầu vào và đầu ra.
- Khôi phục một file đã được chuyển đổi.
- Xác định nguyên nhân của lỗi writer hoặc hệ thống đích.

Không nên xóa toàn bộ tài nguyên trong một callback luôn chạy khi Job kết thúc nếu chưa phân biệt trạng thái thành công và thất bại.

### Có cần cleanup cả khi thất bại không?

Một số tài nguyên có thể cần giải phóng ngay cả khi Job thất bại, chẳng hạn lock hoặc lease có thời hạn. Một số tài nguyên khác cần được giữ, chẳng hạn file đầu vào hoặc reject file.

Hãy phân loại:

| Tài nguyên | Khi Job thành công | Khi Job thất bại |
|---|---|---|
| Lock tạm | Giải phóng | Thường cần giải phóng theo cơ chế an toàn |
| File nguồn | Archive hoặc xóa sau retention | Giữ để restart hoặc điều tra |
| File reject | Lưu theo chính sách | Giữ để xử lý lỗi |
| File trung gian có thể tái tạo | Xóa sau khi output đã publish | Giữ nếu restart cần; nếu không, dọn bằng TTL sau |
| Staging rows | Xóa sau đối soát | Giữ nếu cần restart hoặc audit |
| Output đã publish | Giữ theo chính sách nghiệp vụ | Không xóa chỉ vì Step sau thất bại |

Có thể tạo nhánh xử lý lỗi riêng để giải phóng lock hoặc ghi nhận trạng thái. Không nên dùng chung một Tasklet xóa tất cả tài nguyên cho cả nhánh thành công và thất bại.

### Dọn tài nguyên bị bỏ lại bằng maintenance Job

Nếu Job thất bại và tài nguyên tạm phải được giữ một thời gian, có thể tạo một maintenance Job riêng để dọn các thư mục hoặc staging rows đã hết hạn.

Maintenance Job cần kiểm tra:

- Batch tương ứng đã kết thúc và không còn chạy.
- Không còn khả năng restart theo chính sách.
- Thời hạn lưu đã hết.
- Tài nguyên không được Job khác sử dụng.
- Có audit về những gì được dọn.

Cơ chế TTL là phương án xử lý phần tài nguyên bị bỏ lại do sự cố, không thay thế cleanup Step trên đường thành công.

## 12. Phân biệt Tasklet cleanup với listener

Spring Batch có các listener như StepExecutionListener và JobExecutionListener. Chúng cung cấp callback để thực hiện logic trước hoặc sau Step, Job.

Tuy nhiên, cleanup nghiệp vụ quan trọng thường nên là một Tasklet Step riêng.

| Tiêu chí | Tasklet cleanup Step | Listener |
|---|---|---|
| Có StepExecution riêng | Có | Không tạo Step mới |
| Trạng thái thành công/thất bại riêng | Có | Gắn với vòng đời Step hoặc Job hiện tại |
| Có transaction của Step | Có, theo cấu hình Tasklet | Phụ thuộc callback và transaction đang có |
| Có thể restart như một Step | Có | Không có Step riêng để restart |
| Phù hợp | Xóa staging, dọn file, publish hoặc giải phóng tài nguyên quan trọng | Logging, metrics, audit sự kiện, thông báo |

### Dùng listener cho quan sát

StepExecutionListener phù hợp để ghi nhận thời điểm bắt đầu và kết thúc, log số lượng hoặc phát metrics. JobExecutionListener có thể phù hợp cho thông báo sau khi Job kết thúc.

Không nên dựa vào afterJob listener làm cơ chế duy nhất cho cleanup quan trọng cần retry và restart. Listener không tạo một StepExecution riêng để Job có thể tiếp tục cleanup như một giai đoạn độc lập.

### Không nhầm close() với cleanup nghiệp vụ

Các reader và writer hỗ trợ ItemStream có phương thức close() để đóng resource. Đây là vòng đời kỹ thuật của thành phần, ví dụ đóng file handle hoặc cursor.

Cleanup nghiệp vụ có mục tiêu khác: xóa file trung gian, xóa staging rows, archive kết quả hoặc giải phóng trạng thái batch. Không nên đặt các thao tác xóa dữ liệu quan trọng vào close() vì close là bước đóng tài nguyên, không phải một Step cleanup có trạng thái riêng.

## 13. Cleanup file và publish output an toàn

Một quy trình xuất dữ liệu thường có các file:

- File tạm đang được ghi.
- File đã hoàn tất nhưng chưa publish.
- File output chính thức.
- File nguồn cần archive.

Một thứ tự thường dùng:

1. Writer ghi file tạm.
2. Step kiểm tra file: kích thước, header, số dòng hoặc checksum.
3. Step publish file sang vị trí chính thức.
4. Ghi nhận trạng thái publish và mã tham chiếu.
5. Cleanup các file trung gian không còn cần.
6. Archive hoặc xóa file nguồn theo chính sách retention.

Không xóa file tạm trước khi publish hoàn tất. Nếu publish thất bại, file tạm có thể là đầu vào cần thiết để retry mà không phải chạy lại toàn bộ xử lý.

### Đổi tên file và atomic move

Nếu file tạm và file đích nằm trên cùng filesystem, có thể thử dùng ATOMIC_MOVE:

~~~java
Files.move(
    temporaryPath,
    finalPath,
    StandardCopyOption.ATOMIC_MOVE
);
~~~

Không phải mọi filesystem đều hỗ trợ atomic move; thao tác có thể thất bại khi hai đường dẫn nằm trên filesystem khác nhau hoặc provider không hỗ trợ. Cần có xử lý ngoại lệ và quy trình phục hồi.

Nếu file đích đã tồn tại, hãy xác định chính sách: ghi đè, từ chối hay dùng tên theo batch ID. Không tự động ghi đè file chính thức của batch khác.

### Archive trước khi xóa

Nếu cần giữ file nguồn để audit, hãy di chuyển nó vào thư mục archive thay vì xóa ngay. Tên file archive nên chứa mã lô hoặc metadata nhận diện, đồng thời tránh ghi đè file archive cũ.

Archive và cleanup có thể là hai Step khác nhau nếu cần theo dõi riêng hoặc có yêu cầu retry khác nhau.

## 14. Dọn staging data và dữ liệu nghiệp vụ

Bảng staging thường chứa dữ liệu trung gian, nhưng không phải mọi bảng có tên staging đều được phép xóa ngay sau khi xử lý.

Trước khi dọn, xác định:

- Bảng có được dùng cho restart không?
- Có cần giữ dòng reject để điều tra không?
- Có bảng audit tham chiếu đến staging ID không?
- Dữ liệu staging có cần đối soát sau khi Job hoàn tất không?
- Có Job khác đang đọc hoặc xử lý cùng batch ID không?
- Có yêu cầu lưu trữ dữ liệu nguồn trong một khoảng thời gian không?

Nếu dữ liệu đã được chuyển sang bảng nghiệp vụ, có thể xóa staging theo batch ID. Nếu cần lưu lịch sử, có thể chuyển trạng thái sang ARCHIVED hoặc lưu bản sao audit trước khi xóa.

Không xóa JobRepository metadata trong Tasklet cleanup của Job đang chạy. Metadata của JobExecution và StepExecution hiện tại cần cho trạng thái, restart và audit. Retention metadata của Spring Batch là một quy trình bảo trì riêng, có điều kiện và thứ tự xóa riêng.

## 15. Cleanup tài nguyên bên ngoài

Một Tasklet có thể gọi API để giải phóng upload session, xóa temporary object hoặc đóng một tài nguyên từ hệ thống khác.

Ví dụ:

~~~java
@Bean
@StepScope
Tasklet cleanupRemoteUploadTasklet(
        RemoteStorageClient storageClient,
        @Value("#{jobParameters['uploadSessionId']}")
        String uploadSessionId) {

    return (contribution, chunkContext) -> {
        storageClient.deleteTemporaryUpload(uploadSessionId);
        return RepeatStatus.FINISHED;
    };
}
~~~

Lời gọi API không tham gia transaction database của Step trừ khi có cơ chế phối hợp riêng được hỗ trợ. Nếu API đã xóa tài nguyên nhưng response bị mất, lần retry có thể gọi lại thao tác xóa.

API cleanup nên có một trong các hành vi:

- Xóa tài nguyên đã không tồn tại vẫn trả kết quả thành công.
- Hỗ trợ idempotency key.
- Cho phép truy vấn trạng thái để xác nhận kết quả.
- Trả mã lỗi rõ ràng cho trường hợp không thể retry.
- Có timeout và retry có giới hạn.

Nếu API không hỗ trợ idempotency, service có thể kiểm tra trạng thái trước khi xóa, nhưng vẫn phải xử lý race condition giữa lần kiểm tra và lần gọi xóa.

## 16. Dùng ExecutionContext để truyền thông tin cleanup

Một Step chuẩn bị có thể lưu thư mục làm việc hoặc mã lô vào JobExecutionContext để Tasklet cleanup sử dụng.

Ví dụ trong một Tasklet chuẩn bị:

~~~java
@Bean
Tasklet prepareWorkDirectoryTasklet() {
    return (contribution, chunkContext) -> {
        String batchId = contribution.getStepExecution()
            .getJobParameters()
            .getString("batchId");

        Path workDirectory = Path.of("work", batchId);
        Files.createDirectories(workDirectory);

        contribution.getStepExecution()
            .getJobExecution()
            .getExecutionContext()
            .putString(
                "workDirectory",
                workDirectory.toAbsolutePath().toString()
            );

        return RepeatStatus.FINISHED;
    };
}
~~~

Cleanup Step có thể đọc lại giá trị đó bằng late binding hoặc thông qua StepExecution.

ExecutionContext phù hợp để truyền những thông tin nhỏ như:

- Batch ID.
- Đường dẫn thư mục làm việc.
- Tên file tạm.
- Mã upload session.
- Trạng thái cần thiết để tiếp tục quy trình.

Không nên lưu toàn bộ nội dung file hoặc danh sách hàng triệu bản ghi trong ExecutionContext. Dữ liệu lớn nên được lưu trong filesystem, database hoặc object storage.

Giá trị trong ExecutionContext cần được lưu ở đúng phạm vi. JobExecutionContext thích hợp cho thông tin được chia sẻ giữa nhiều Step trong cùng JobExecution; StepExecutionContext thích hợp cho trạng thái riêng của một Step.

## 17. Theo dõi kết quả cleanup

Cleanup là một giai đoạn vận hành nên cần được quan sát riêng.

Có thể ghi nhận:

- Số file đã xóa.
- Số thư mục đã xóa.
- Số staging rows đã xóa.
- Số tài nguyên bên ngoài đã giải phóng.
- Thời gian thực hiện cleanup.
- Batch ID và phạm vi cleanup.
- Tên Step, JobExecution ID và trạng thái cuối.
- Số lần retry hoặc số lỗi.

Ví dụ cập nhật StepContribution khi xóa dữ liệu:

~~~java
int deletedRows = jdbcTemplate.update(
    "DELETE FROM customer_import_stage WHERE batch_id = ?",
    batchId
);

contribution.incrementWriteCount(deletedRows);
~~~

Các bộ đếm trong StepExecution giúp hiển thị số lượng đã xử lý. Tuy nhiên, nếu cleanup gồm nhiều loại tài nguyên, nên có metrics riêng để biết chính xác số file, object hoặc staging row đã dọn.

Không ghi toàn bộ đường dẫn nhạy cảm, token hoặc dữ liệu cá nhân vào log. Có thể dùng batch ID và tên resource đã được làm sạch để truy vết.

### Cleanup hoàn tất nhưng một phần tài nguyên vẫn còn

Một Tasklet có thể cần xóa nhiều tài nguyên. Nếu xóa thành công một số file rồi thất bại ở file tiếp theo, Step sẽ thất bại. Khi restart, Tasklet chạy lại và cần bỏ qua những file đã biến mất, sau đó tiếp tục dọn phần còn lại.

Nếu cần biết chính xác tài nguyên nào đã được xử lý, có thể ghi trạng thái từng resource vào bảng cleanup audit. Bảng audit nên có khóa duy nhất theo batch và resource để việc retry không tạo bản ghi trùng.

## 18. Kiểm soát đồng thời và tránh xóa nhầm

Cleanup có thể chạy đồng thời với Job khác. Nếu hai Job dùng chung thư mục hoặc staging table, một Tasklet có thể xóa tài nguyên mà Job kia vẫn cần.

Các biện pháp:

- Tạo thư mục riêng cho từng batch ID.
- Dùng batch ID hoặc partition key trong mọi câu lệnh DELETE.
- Không dùng tên file chung cho nhiều lần chạy.
- Kiểm tra Job hoặc lease tương ứng còn hoạt động trước khi dọn.
- Dùng lock hoặc cơ chế ownership nếu nhiều worker có thể thao tác cùng resource.
- Không cho phép nhiều cleanup Job chạy chồng lấn trên cùng phạm vi nếu chưa có cơ chế đồng bộ.
- Giới hạn quyền xóa vào thư mục hoặc schema được phép.

Đặc biệt, không xây dựng đường dẫn từ tham số bên ngoài rồi xóa trực tiếp mà không chuẩn hóa và xác thực. Một batch ID chứa thành phần đường dẫn có thể làm đường dẫn mục tiêu thoát khỏi thư mục làm việc.

## 19. Kiểm thử Tasklet cleanup

Tasklet cleanup nên được kiểm thử độc lập và trong Job flow.

| Trường hợp | Kết quả mong đợi |
|---|---|
| File tạm tồn tại | File được xóa |
| File đã bị xóa trước đó | Cleanup vẫn hoàn tất nếu thiếu file được chấp nhận |
| Đường dẫn không hợp lệ | Tasklet báo lỗi và Step thất bại |
| Đường dẫn ngoài thư mục cho phép | Bị từ chối |
| Batch ID không có staging rows | Cleanup hoàn tất với 0 dòng xóa |
| Batch có nhiều staging rows | Chỉ xóa rows thuộc batch đó |
| Lỗi database khi xóa staging | Transaction rollback theo cấu hình |
| Lỗi xóa file giữa chừng | Step thất bại; lần chạy lại tiếp tục an toàn |
| Step xử lý dữ liệu thất bại | Cleanup thành công chỉ không được chạy trên flow thành công |
| Cleanup thất bại rồi restart | Các thao tác đã hoàn tất không gây lỗi hoặc side effect trùng |
| Hai Job chạy đồng thời | Cleanup của một batch không xóa tài nguyên batch còn lại |

### Kiểm thử cleanup file

Có thể dùng thư mục tạm trong JUnit:

~~~java
@Test
void deletesTemporaryFile() throws Exception {
    Path directory = Files.createTempDirectory("batch-cleanup");
    Path file = Files.createFile(directory.resolve("intermediate.tmp"));

    temporaryFileService.deleteIfExists(file);

    assertFalse(Files.exists(file));
}
~~~

Nên có thêm test cho file không tồn tại và đường dẫn không hợp lệ.

### Kiểm thử cleanup database

Dùng database test để xác nhận:

1. Tạo staging rows của hai batch khác nhau.
2. Chạy cleanup cho batch thứ nhất.
3. Xác nhận chỉ rows của batch thứ nhất bị xóa.
4. Xác nhận rows của batch thứ hai vẫn tồn tại.
5. Tạo lỗi trong transaction để kiểm tra rollback.
6. Chạy lại cleanup và xác nhận kết quả idempotent.

### Kiểm thử Job restart

Tạo tình huống cleanup xóa được một phần tài nguyên rồi phát sinh lỗi. Sau đó restart cùng JobInstance và xác nhận:

- Các Step xử lý đã hoàn tất không chạy lại ngoài dự kiến.
- Cleanup Step được chạy lại.
- Tài nguyên đã xóa không làm cleanup thất bại.
- Tài nguyên còn lại được dọn.
- Job kết thúc với trạng thái phù hợp.

## 20. Những sai lầm thường gặp

### Cleanup quá sớm

Xóa file nguồn hoặc staging data ngay sau khi writer chạy có thể làm mất dữ liệu cần cho Step đối soát hoặc restart. Chỉ dọn sau khi mọi Step phụ thuộc đã hoàn tất.

### Xóa toàn bộ staging table

Câu DELETE không có điều kiện theo batch ID có thể xóa dữ liệu của Job khác. Luôn giới hạn phạm vi cleanup.

### Cho rằng filesystem rollback cùng database

Transaction database không thể khôi phục file đã xóa. Thiết kế thao tác file theo hướng idempotent và có thể chạy lại.

### Đặt cleanup quan trọng trong afterJob

Listener không tạo StepExecution riêng để restart và theo dõi cleanup như một giai đoạn. Dùng Tasklet Step cho cleanup cần độ tin cậy vận hành.

### Dọn cả khi Job thất bại mà không phân loại

File nguồn, staging rows hoặc reject data có thể cần cho restart và điều tra. Chỉ giải phóng tài nguyên thật sự cần giải phóng trên nhánh lỗi; giữ các dữ liệu cần thiết.

### Dùng đường dẫn hoặc wildcard quá rộng

Cleanup có thể xóa nhầm file của batch khác hoặc thư mục chung. Chuẩn hóa đường dẫn, giới hạn thư mục gốc và xác thực batch ID.

### Không thiết kế idempotency

Một Tasklet có thể đã xóa một phần tài nguyên trước khi thất bại. Nếu lần chạy lại không chịu được trạng thái một phần, cleanup sẽ liên tục thất bại.

### Dùng một transaction lớn cho lượng dữ liệu rất lớn

Xóa hàng triệu staging rows trong một lần có thể gây lock và transaction log lớn. Hãy xóa theo batch nhỏ hoặc dùng chunk-oriented Step khi phù hợp.

### Xóa metadata của chính Job đang chạy

Không dùng Tasklet cleanup nghiệp vụ để xóa JobRepository metadata của Job hiện tại. Metadata đó cần cho trạng thái, restart và audit; retention metadata phải là quy trình bảo trì riêng.

## 21. Quy trình thiết kế cleanup Tasklet

Khi xây dựng một Tasklet cleanup, có thể làm theo trình tự:

1. **Liệt kê tài nguyên:** xác định file, thư mục, staging rows hoặc tài nguyên bên ngoài cần dọn.
2. **Xác định điều kiện:** quyết định cleanup chỉ chạy sau những Step nào và trạng thái nào.
3. **Bảo vệ dữ liệu restart:** giữ file nguồn, reject data và staging cần thiết cho retry hoặc điều tra.
4. **Giới hạn phạm vi:** dùng batch ID, resource ID và thư mục gốc được phép.
5. **Chọn transaction:** xác định tài nguyên nào tham gia transaction database và tài nguyên nào không thể rollback.
6. **Tách Step:** chia cleanup theo loại tài nguyên nếu cần trạng thái và retry độc lập.
7. **Thiết kế idempotency:** bảo đảm chạy lại sau khi đã dọn một phần vẫn an toàn.
8. **Lưu trạng thái cần thiết:** dùng JobExecutionContext hoặc bảng audit cho thông tin nhỏ và tiến độ cleanup.
9. **Theo dõi:** ghi số lượng đã dọn, thời gian, lỗi và batch ID.
10. **Kiểm thử:** xác nhận cleanup thành công, thất bại, rollback, restart và chạy đồng thời.

## 22. Những điểm cần nhớ

- Cleanup thường là một Tasklet Step riêng ở cuối đường xử lý thành công.
- Chỉ dọn tài nguyên sau khi dữ liệu đầu ra đã được ghi, kiểm tra và publish theo yêu cầu.
- Tasklet Step có trạng thái và transaction riêng, giúp theo dõi và restart cleanup.
- Database cleanup có thể rollback khi dùng cùng transaction manager; xóa file hoặc gọi API bên ngoài không tự rollback.
- Dọn staging theo batch ID và xóa dữ liệu lớn theo từng đợt.
- Cleanup phải idempotent vì có thể chạy lại sau khi một phần thao tác đã hoàn tất.
- Khi Job thất bại, giữ tài nguyên cần cho restart và điều tra; dùng maintenance Job hoặc TTL để dọn phần bị bỏ lại sau này.
- Dùng listener cho logging và metrics; dùng Tasklet Step cho cleanup nghiệp vụ quan trọng.
- Chuẩn hóa đường dẫn và giới hạn quyền xóa để tránh xóa nhầm tài nguyên.
- Không xóa JobRepository metadata của Job đang chạy trong Tasklet cleanup.

Một Tasklet cleanup được đặt đúng vị trí và có thể chạy lại an toàn giúp Job thu hồi tài nguyên sau khi xử lý, giữ được dữ liệu cần thiết khi có lỗi và làm cho vòng đời của mỗi batch rõ ràng hơn.

