# Thiết kế JobParameters định danh lần chạy trong Spring Batch

## 1. Bối cảnh dự án thực hành

Trong Spring Batch Core Processing, **JobParameters** không chỉ là tập giá trị truyền vào Job. Những tham số được đánh dấu **identifying** quyết định Spring Batch có xem một yêu cầu là công việc nghiệp vụ đã tồn tại, cần restart, hay là một công việc mới hoàn toàn.

Một ứng dụng nhập đơn hàng theo ngày có thể nhận các yêu cầu sau:

- Scheduler của hai pod cùng kích hoạt Job lúc 02:00.
- Một API client gửi lại request sau khi bị timeout.
- Lần chạy đầu thất bại giữa chunk và cần restart.
- Đối tác gửi phiên bản sửa đổi của file trong cùng ngày.
- Người vận hành được phê duyệt chạy lại một kỳ đã COMPLETED.

Nếu mỗi lần kích hoạt đều sinh **run.id** ngẫu nhiên, các yêu cầu cùng nghiệp vụ có thể tạo nhiều JobInstance và xử lý trùng. Nếu chỉ dùng **businessDate** làm identity, dữ liệu của hai tenant hoặc hai snapshot trong cùng ngày lại có thể bị gom nhầm.

Bài thực hành này thiết kế một Job **importOrdersJob** theo bốn chiều:

~~~text
tenantId         = tenant-a
businessDate     = 2026-11-15
sourceSnapshotId = snap-a-20261115-v1
generation       = 1
~~~

Mục tiêu cuối bài:

1. Nhận diện **một lô nghiệp vụ duy nhất** bằng identifying JobParameters có ý nghĩa.
2. Phân biệt **JobInstance** với **JobExecution** và request HTTP.
3. Restart một lần chạy lỗi bằng **cùng identifying parameters**, không tạo instance mới.
4. Tạo instance mới **có chủ đích** khi thay đổi snapshot hoặc generation.
5. Đảm bảo scheduler, API và người vận hành dùng cùng quy tắc tạo parameters.
6. Giữ đầu vào bất biến và đầu ra idempotent để kết quả đúng sau retry/restart.
7. Kiểm thử các trường hợp trùng, hoàn thành, thất bại, chạy lại và concurrent launch.

Các ví dụ sử dụng **Java 17, Spring Boot 3.x, Spring Batch 5.x, Spring JDBC và PostgreSQL**. Các mã nguồn minh họa được ghép vào ứng dụng đã có JobRepository, DataSource và transaction manager phù hợp.

## 2. Job, JobInstance và JobExecution

**Job** là định nghĩa quy trình, ví dụ **importOrdersJob** có các Step đọc file, xử lý item, ghi vào database và đối soát.

**JobInstance** là một công việc được xác định bởi **tên Job và tập identifying JobParameters**. Trong ví dụ, đây là lô nhập của tenant-a, ngày 2026-11-15, snapshot v1, generation 1.

**JobExecution** là một **lần cố gắng thực thi** JobInstance. Nếu execution đầu FAILED rồi được restart, framework tạo một JobExecution mới cho **cùng JobInstance**, sử dụng metadata/checkpoint phù hợp.

~~~text
Job definition
  importOrdersJob
         |
         v
JobInstance #31
  tenant-a / 2026-11-15 / snap-v1 / generation=1
         |
    +----+------------------+
    |                       |
    v                       v
JobExecution #101       JobExecution #105
    FAILED                  COMPLETED
    |                       |
StepExecution #501      StepExecution #508
  đã commit một số chunk   tiếp tục từ checkpoint
~~~

**JobExecution ID không phải tham số định danh cần sinh trước lúc chạy**; ID do JobRepository cấp khi một execution mới được tạo. Không đưa execution ID vào business key.

Khi launch trùng cùng identity, hành vi thường là:

| Trạng thái hiện có | Hành vi khi launch cùng identity |
| --- | --- |
| Chưa có JobInstance | Tạo JobInstance và JobExecution mới |
| Đang chạy | Có thể bị từ chối bằng **JobExecutionAlreadyRunningException** |
| Đã COMPLETED | Có thể bị từ chối bằng **JobInstanceAlreadyCompleteException** |
| FAILED hoặc STOPPED | Có thể tạo JobExecution mới để restart nếu Job cho phép |
| Không được phép restart | Có thể nhận **JobRestartException** |
| Parameters không hợp lệ | **JobParametersInvalidException** nếu validator phát hiện |

Điều kiện chi tiết phụ thuộc trạng thái thực và cấu hình Job. Đừng sửa bảng BATCH_JOB_EXECUTION bằng SQL chỉ để “ép chạy”.

## 3. Identifying và non-identifying parameters

Một **JobParameter** có kiểu dữ liệu, giá trị và cờ **identifying**.

- **Identifying = true:** tham gia định danh JobInstance.
- **Identifying = false:** được truyền vào execution nhưng không tham gia định danh.

Ví dụ:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("tenantId", "tenant-a", true)
        .addString("businessDate", "2026-11-15", true)
        .addString("sourceSnapshotId", "snap-a-20261115-v1", true)
        .addLong("generation", 1L, true)
        .addString("requestedBy", "scheduler", false)
        .addString("traceId", "req-4281", false)
        .toJobParameters();
~~~

Bốn tham số đầu xác định lô công việc. **requestedBy** và **traceId** phục vụ audit và tracing. Nếu người vận hành gửi cùng identity nhưng traceId khác, Spring Batch vẫn nhận diện **cùng JobInstance**.

| Parameter | Identifying | Giải thích |
| --- | --- | --- |
| tenantId | Có | Cùng kỳ nhưng khác tenant là công việc khác |
| businessDate | Có | Mỗi ngày nghiệp vụ là một kỳ xử lý |
| sourceSnapshotId | Có | Snapshot nguồn mới là dữ liệu mới |
| generation | Có | Lần xử lý/công bố lại được phê duyệt |
| requestedBy | Không | Ai khởi chạy không đổi dữ liệu cần xử lý |
| traceId | Không | Mỗi HTTP request có thể khác ID |
| retryCount | Không | Số lần thử không tạo nghiệp vụ mới |
| hostname/podId | Không | Nhiều pod vẫn có thể cùng xử lý một lô |
| processingRuleVersion | Phải chốt theo hợp đồng | Nếu làm thay đổi kết quả, cần nằm trong identity hoặc một snapshot/generation bất biến |

**Đặt identifying=false không mã hóa hay ẩn giá trị.** Non-identifying parameters vẫn có thể được lưu trong metadata. Không lưu mật khẩu, API key hoặc token thực ở đây.

### Cảnh báo khi restart

Framework có thể nhận một bộ non-identifying values mới mà vẫn xác định cùng JobInstance. Điều đó chỉ an toàn khi các giá trị ấy **không quyết định kết quả nghiệp vụ**.

Nếu **taxRate**, **currency**, **inputFile** hoặc **ruleVersion** được đặt non-identifying và thay đổi giữa hai execution, Job có thể xử lý chunk đầu theo quy tắc cũ, chunk sau theo quy tắc mới. Vì vậy, mọi yếu tố ảnh hưởng input/output cần được **cố định theo business run key**.

## 4. Định nghĩa business run key trước khi viết code

Đơn vị công việc của dự án là:

~~~text
ImportRunKey = (
    tenantId,
    businessDate,
    sourceSnapshotId,
    generation
)
~~~

Đây là hợp đồng nghiệp vụ do ứng dụng thiết kế. Spring Batch còn gắn **tên Job** vào danh tính JobInstance của mình.

Tại sao cần từng chiều?

**tenantId:** bảo đảm hai khách hàng độc lập không bị gộp thành một lô. Cần kiểm tra người yêu cầu được phép truy cập tenant đó.

**businessDate:** định nghĩa kỳ theo lịch kinh doanh, không nhất thiết là ngày hệ thống đang chạy. Khi backfill tháng trước, vẫn dùng ngày gốc của dữ liệu.

**sourceSnapshotId:** chỉ tới bản dữ liệu nguồn đã được chốt. Nếu đối tác gửi bản sửa sau đó, phải có snapshot ID/version mới.

**generation:** cho phép chạy lại có chủ đích sau khi một instance đã hoàn tất, chẳng hạn khi sửa thuật toán và cần tạo bản output thay thế. Nó không phải retry counter tự động.

Một số quyết định cần được thống nhất trước khi triển khai:

- Một tenant/ngày có thể có bao nhiêu snapshot?
- Snapshot có bảo đảm bất biến sau khi chốt không?
- Nếu file cùng tên bị ghi đè, có object version hoặc digest để phân biệt không?
- Khi chạy generation 2, output cũ được giữ, thay thế hay hủy?
- Ai có quyền yêu cầu generation mới?
- Một bước restart có phải tiếp tục đúng snapshot và rule version cũ không?
- Nếu dữ liệu vào chưa chốt, Job từ chối hay hoãn chạy?

**JobParameters tốt không thể cứu một input mutable**: nếu snapshotId cũ trỏ tới dữ liệu đã bị thay đổi, checkpoint của reader có thể không còn đúng dù identity không đổi.

## 5. Chuẩn hóa kiểu và giá trị để các entry point cùng nhận diện một lô

Hai cách biểu diễn tưởng giống nhau có thể tạo identity khác nhau:

~~~text
tenant-a    và TENANT-A
2026-11-15  và 15/11/2026
Long 1      và String "1"
snap-v1     và " snap-v1 "
~~~

Phải thiết kế một chuẩn biểu diễn:

- Dùng **LocalDate** cho businessDate ở tầng domain, chuyển thành chuỗi **ISO yyyy-MM-dd** trong JobParameters.
- Dùng **Long** cho generation; không chỗ dùng Long, chỗ dùng String.
- Dùng một quy tắc tenant ID nhất quán: có hoặc không phân biệt chữ hoa tùy nghiệp vụ.
- Loại khoảng trắng không có nghĩa và từ chối ký tự không hợp lệ ở snapshot ID.
- Giữ tên parameter ổn định qua các phiên bản ứng dụng.
- Với kỳ giờ/phút, biểu diễn window start/end theo **timezone và khoảng thời gian được quy định** thay vì dùng thời gian hiện tại bất kỳ.

Đặc biệt tránh cách tạo key như:

~~~java
JobParameters wrong = new JobParametersBuilder()
        .addLong("run.id", System.currentTimeMillis(), true)
        .toJobParameters();
~~~

Nếu hai pod cùng thực hiện cron, thời điểm hiện tại khác nhau sẽ tạo hai JobInstance. **run.id** chỉ phù hợp khi contract thực sự coi mỗi lần chạy là công việc mới; nó không phải giải pháp mặc định cho lô hằng ngày cần idempotency.

## 6. Xây kiểu dữ liệu ImportRunKey

Một value object giúp scheduler, controller và test dùng chung quy tắc:

~~~java
import java.time.LocalDate;
import java.util.Locale;
import java.util.Objects;
import java.util.regex.Pattern;

import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;

public record ImportRunKey(
        String tenantId,
        LocalDate businessDate,
        String sourceSnapshotId,
        long generation) {

    private static final Pattern TENANT =
            Pattern.compile("[a-z0-9][a-z0-9_-]{0,31}");

    private static final Pattern SNAPSHOT =
            Pattern.compile("[A-Za-z0-9_-]{1,80}");

    public ImportRunKey {
        Objects.requireNonNull(tenantId, "tenantId");
        Objects.requireNonNull(businessDate, "businessDate");
        Objects.requireNonNull(sourceSnapshotId, "sourceSnapshotId");

        tenantId = tenantId.trim().toLowerCase(Locale.ROOT);
        sourceSnapshotId = sourceSnapshotId.trim();

        if (!TENANT.matcher(tenantId).matches()) {
            throw new IllegalArgumentException("Invalid tenantId");
        }
        if (!SNAPSHOT.matcher(sourceSnapshotId).matches()) {
            throw new IllegalArgumentException("Invalid snapshot ID");
        }
        if (generation < 1L) {
            throw new IllegalArgumentException(
                    "generation must be positive");
        }
    }

    public JobParameters toParameters(
            String requestedBy, String traceId) {

        return new JobParametersBuilder()
                .addString("tenantId", tenantId, true)
                .addString("businessDate", businessDate.toString(), true)
                .addString("sourceSnapshotId", sourceSnapshotId, true)
                .addLong("generation", generation, true)
                .addString("requestedBy", requestedBy, false)
                .addString("traceId", traceId, false)
                .toJobParameters();
    }
}
~~~

Với record compact constructor, việc gán lại local parameter trong constructor dùng để chuẩn hóa các thành phần được lưu. Ví dụ giả định **requestedBy** và **traceId** không null và được kiểm tra từ lớp tiếp nhận; ứng dụng thật cần giới hạn độ dài, xử lý optional values và không đưa thông tin nhạy cảm vào metadata.

Chỉ **lowercase tenantId** nếu nghiệp vụ xác nhận tenant không phân biệt hoa/thường. Nếu **ABC** và **abc** là hai tenant khác nhau, canonicalization phải giữ nguyên sự khác biệt đó.

## 7. Snapshot nguồn: khóa của Job phải trỏ tới dữ liệu bất biến

Có thể quản lý snapshot bằng bảng:

~~~sql
CREATE TABLE source_snapshot (
    tenant_id        VARCHAR(32) NOT NULL,
    snapshot_id      VARCHAR(80) NOT NULL,
    business_date    DATE NOT NULL,
    content_digest   VARCHAR(128) NOT NULL,
    status           VARCHAR(20) NOT NULL,
    finalized_at     TIMESTAMP,
    PRIMARY KEY (tenant_id, snapshot_id)
);

CREATE TABLE source_order (
    tenant_id        VARCHAR(32) NOT NULL,
    snapshot_id      VARCHAR(80) NOT NULL,
    order_id         VARCHAR(64) NOT NULL,
    amount           DECIMAL(18, 2) NOT NULL,
    PRIMARY KEY (tenant_id, snapshot_id, order_id)
);
~~~

Quy tắc ví dụ:

1. File được upload vào khu vực chưa hoàn tất.
2. Kiểm tra schema, checksum và số dòng.
3. Tạo snapshot ID và manifest chứa content digest.
4. Đánh dấu snapshot **FINALIZED**.
5. Không cập nhật lại các dòng nguồn của snapshot đã FINALIZED.
6. Job chỉ được launch nếu snapshot thuộc đúng tenant/businessDate và đang FINALIZED.

Dữ liệu minh họa:

~~~text
Snapshot: snap-a-20261115-v1
Tenant  : tenant-a
Date    : 2026-11-15

order_id    amount
--------    ------
O-101       100.00
O-102       250.00
O-103        75.00
O-104       125.00

Số dòng: 4; tổng tiền: 550.00
~~~

Nếu đối tác sửa số tiền O-102, hãy tạo **snap-a-20261115-v2** hoặc version/manifest mới thay vì ghi đè dữ liệu của v1. Nhờ đó restart và audit có thể truy lại chính input ban đầu.

## 8. Output cũng phải phản ánh phạm vi định danh

Bảng đích minh họa:

~~~sql
CREATE TABLE imported_order (
    tenant_id          VARCHAR(32) NOT NULL,
    business_date      DATE NOT NULL,
    source_snapshot_id VARCHAR(80) NOT NULL,
    generation         BIGINT NOT NULL,
    order_id           VARCHAR(64) NOT NULL,
    amount             DECIMAL(18, 2) NOT NULL,
    PRIMARY KEY (
        tenant_id, business_date,
        source_snapshot_id, generation, order_id
    )
);
~~~

Phạm vi khóa này giúp:

- Retry/restart cùng JobInstance ghi đúng vùng dữ liệu.
- Snapshot v2 không ghi nhầm vào vùng output của snapshot v1.
- Generation mới có vùng kết quả riêng để đối soát trước khi công bố.
- Các tenant tách biệt nhau.

Nhưng **không được truy vấn cả generation 1 lẫn generation 2 để tính doanh thu cuối cùng** nếu doanh nghiệp chỉ muốn một bản công bố. Cần publication pointer hoặc policy chọn kết quả hợp lệ đã được duyệt.

Idempotency của writer phải được thiết kế độc lập. Nếu writer gửi email, gọi API hay thực hiện giao dịch ngoài database, một khóa chính trong bảng imported_order không ngăn mọi tác dụng phụ bị lặp.

## 9. Cấu hình reader đọc theo JobParameters

Các model:

~~~java
import java.math.BigDecimal;
import java.time.LocalDate;

public record SourceOrder(
        String orderId,
        BigDecimal amount) {}

public record ImportedOrder(
        String tenantId,
        LocalDate businessDate,
        String sourceSnapshotId,
        Long generation,
        String orderId,
        BigDecimal amount) {}
~~~

Reader Spring Batch 5.x:

~~~java
@Bean
@StepScope
JdbcCursorItemReader<SourceOrder> sourceOrderReader(
        DataSource dataSource,
        @Value("#{jobParameters['tenantId']}") String tenantId,
        @Value("#{jobParameters['sourceSnapshotId']}")
                String snapshotId) {

    return new JdbcCursorItemReaderBuilder<SourceOrder>()
            .name("sourceOrderReader")
            .dataSource(dataSource)
            .sql("""
                SELECT order_id, amount
                FROM source_order
                WHERE tenant_id = ? AND snapshot_id = ?
                ORDER BY order_id
                """)
            .preparedStatementSetter(ps -> {
                ps.setString(1, tenantId);
                ps.setString(2, snapshotId);
            })
            .rowMapper((rs, rowNum) -> new SourceOrder(
                    rs.getString("order_id"),
                    rs.getBigDecimal("amount")))
            .saveState(true)
            .build();
}
~~~

**@StepScope** giúp late binding JobParameters tại thời điểm Step chạy. Reader lọc theo tenant/snapshot; nếu câu SQL không lọc theo identity, thiết kế JobParameters đúng vẫn không ngăn đọc nhầm dữ liệu.

**ORDER BY order_id** tạo thứ tự ổn định trong snapshot, còn khóa chính bảo đảm order_id duy nhất trong phạm vi tenant/snapshot. Với restart, cần kiểm tra reader ItemStream và tình trạng dữ liệu nguồn bất biến.

## 10. Processor và writer gắn cùng key nghiệp vụ

Processor tạo output với đầy đủ bốn chiều:

~~~java
@Bean
@StepScope
ItemProcessor<SourceOrder, ImportedOrder> orderProcessor(
        @Value("#{jobParameters['tenantId']}") String tenantId,
        @Value("#{jobParameters['businessDate']}") String businessDate,
        @Value("#{jobParameters['sourceSnapshotId']}")
                String snapshotId,
        @Value("#{jobParameters['generation']}") Long generation) {

    LocalDate date = LocalDate.parse(businessDate);

    return source -> new ImportedOrder(
            tenantId,
            date,
            snapshotId,
            generation,
            source.orderId(),
            source.amount());
}
~~~

Processor không dùng traceId/requestedBy để thay đổi kết quả. Nếu có version thuật toán làm thay đổi mapping hoặc số tiền, phải chốt nó theo một parameter identifying hoặc manifest/generation bất biến. Đặc biệt khi restart sau deployment mới, không nên âm thầm thay quy tắc ở phần input chưa xử lý.

Writer PostgreSQL sử dụng upsert để không tạo hai dòng cho cùng business key:

~~~java
@Bean
JdbcBatchItemWriter<ImportedOrder> importedOrderWriter(
        DataSource dataSource) {

    return new JdbcBatchItemWriterBuilder<ImportedOrder>()
            .dataSource(dataSource)
            .sql("""
                INSERT INTO imported_order (
                    tenant_id, business_date, source_snapshot_id,
                    generation, order_id, amount
                ) VALUES (
                    :tenantId, :businessDate, :sourceSnapshotId,
                    :generation, :orderId, :amount
                )
                ON CONFLICT (
                    tenant_id, business_date, source_snapshot_id,
                    generation, order_id
                )
                DO UPDATE SET amount = EXCLUDED.amount
                """)
            .beanMapped()
            .build();
}
~~~

Upsert ở đây phù hợp khi dữ liệu và phép biến đổi có tính xác định. Một hệ thống tài chính có thể chọn **từ chối update nếu amount khác** thay vì âm thầm ghi đè; điều đó thuộc quy tắc nghiệp vụ. Upsert cũng không thay thế đối soát hoặc bảo vệ các side effect ngoài transaction.

Khai báo Step và Job:

~~~java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        JdbcCursorItemReader<SourceOrder> reader,
        ItemProcessor<SourceOrder, ImportedOrder> processor,
        JdbcBatchItemWriter<ImportedOrder> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<SourceOrder, ImportedOrder>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}

@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep,
        JobParametersValidator importParametersValidator) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .validator(importParametersValidator)
            .start(importOrdersStep)
            .build();
}
~~~

Cấu hình giả định DataSource và transaction manager tương thích với reader/writer và JobRepository. Nếu metadata và business output dùng hai database khác nhau, phải thiết kế ranh giới transaction, checkpoint và idempotency chặt chẽ; hai transaction manager cục bộ không tự tạo một giao dịch phân tán nguyên tử.

## 11. JobParametersValidator: kiểm tra contract ở ranh giới Job

Controller có thể validate request, nhưng Job còn được kích hoạt qua scheduler, CLI hoặc công cụ quản trị. Gắn **JobParametersValidator** vào chính Job giúp bảo đảm mọi đường gọi tuân thủ cùng hợp đồng.

~~~java
@Bean
JobParametersValidator importParametersValidator() {
    return params -> {
        String tenant = params.getString("tenantId");
        String date = params.getString("businessDate");
        String snapshot = params.getString("sourceSnapshotId");
        Long generation = params.getLong("generation");

        if (tenant == null || tenant.isBlank()
                || date == null || date.isBlank()
                || snapshot == null || snapshot.isBlank()
                || generation == null || generation < 1L) {
            throw new JobParametersInvalidException(
                    "Missing or invalid import identity");
        }

        try {
            LocalDate parsed = LocalDate.parse(date);
            if (!parsed.toString().equals(date)) {
                throw new IllegalArgumentException("Date not canonical");
            }
        } catch (RuntimeException ex) {
            throw new JobParametersInvalidException(
                    "businessDate must use yyyy-MM-dd");
        }

        for (String key : List.of(
                "tenantId", "businessDate",
                "sourceSnapshotId", "generation")) {

            var value = params.getParameters().get(key);

            if (value == null || !value.isIdentifying()) {
                throw new JobParametersInvalidException(
                        key + " must be identifying");
            }
        }

        for (String key : List.of("requestedBy", "traceId")) {
            var value = params.getParameters().get(key);
            if (value != null && value.isIdentifying()) {
                throw new JobParametersInvalidException(
                        key + " must not be identifying");
            }
        }
    };
}
~~~

Cần import **java.time.LocalDate**, **java.util.List**, **JobParametersValidator** và **JobParametersInvalidException** cùng những lớp Spring Batch tương ứng.

Validator này tập trung vào bắt buộc/định danh/ngày. Production nên kiểm tra thêm pattern, kiểu dữ liệu, giới hạn độ dài, extra parameters và quyền truy cập snapshot. **JobParametersValidator không thay thế authorization hoặc kiểm tra snapshot FINALIZED**.

## 12. Một dịch vụ launch dùng chung cho mọi entry point

Tránh để controller, scheduler và CLI tự xây JobParameters khác nhau. Dùng một service điều phối:

~~~java
@Service
public class OrderImportLauncher {

    private final JobLauncher jobLauncher;
    private final Job importOrdersJob;
    private final SourceSnapshotService snapshotService;

    public OrderImportLauncher(
            JobLauncher jobLauncher,
            @Qualifier("importOrdersJob") Job importOrdersJob,
            SourceSnapshotService snapshotService) {

        this.jobLauncher = jobLauncher;
        this.importOrdersJob = importOrdersJob;
        this.snapshotService = snapshotService;
    }

    public JobExecution launch(
            ImportRunKey key,
            String requestedBy,
            String traceId) throws Exception {

        snapshotService.requireFinalized(
                key.tenantId(),
                key.businessDate(),
                key.sourceSnapshotId());

        JobParameters params =
                key.toParameters(requestedBy, traceId);

        return jobLauncher.run(importOrdersJob, params);
    }
}
~~~

**SourceSnapshotService** là domain service mà dự án phải triển khai: kiểm tra snapshot thuộc tenant/ngày, đã chốt và nội dung không thay đổi. Một controller còn phải kiểm tra quyền người dùng đối với tenant, generation và quyền reprocess. Giá trị hợp lệ về cú pháp **không có nghĩa caller được phép xử lý nó**.

### Diễn giải các kết quả launch

| Kết quả | Hành động caller |
| --- | --- |
| Trả về JobExecution COMPLETED | Trả thông tin hoàn tất và execution ID |
| Trả về JobExecution FAILED | Ghi lỗi, cung cấp quy trình restart |
| JobInstanceAlreadyCompleteException | Trả kết quả đã xử lý, không tự sinh run.id |
| JobExecutionAlreadyRunningException | Trả trạng thái đang chạy |
| JobRestartException | Điều tra vì không thể restart theo policy |
| JobParametersInvalidException | Báo lỗi tham số hợp lệ |
| Không truy cập được JobRepository | Không giả định Job có hoặc không chạy; kiểm tra metadata trước retry |

Ví dụ giả định launcher chạy **đồng bộ**. Với **TaskExecutorJobLauncher** cấu hình TaskExecutor bất đồng bộ, lời gọi run có thể trả JobExecution ở STARTING/STARTED. Phải truy vấn JobExplorer hoặc chờ completion khi cần trạng thái cuối.

Không catch mọi exception rồi thay generation/UUID để “chạy lại bằng mọi giá”. Đây là cách biến vấn đề metadata thành xử lý trùng.

## 13. Scheduler nhiều instance phải dùng identity giống nhau

Với lịch nhập dữ liệu mỗi ngày lúc 02:00 theo múi giờ nghiệp vụ:

~~~java
@Component
public class DailyOrderScheduler {

    private final OrderImportLauncher imports;
    private final SourceSnapshotService snapshots;
    private final Clock clock;

    public DailyOrderScheduler(
            OrderImportLauncher imports,
            SourceSnapshotService snapshots,
            Clock clock) {

        this.imports = imports;
        this.snapshots = snapshots;
        this.clock = clock;
    }

    @Scheduled(cron = "0 0 2 * * *", zone = "Asia/Ho_Chi_Minh")
    public void importPreviousDay() throws Exception {
        LocalDate businessDate =
                LocalDate.now(clock).minusDays(1);

        String tenantId = "tenant-a";
        String snapshotId = snapshots.finalizedSnapshotId(
                tenantId, businessDate);

        ImportRunKey key = new ImportRunKey(
                tenantId, businessDate, snapshotId, 1L);

        imports.launch(key, "scheduler", "daily-schedule");
    }
}
~~~

Bean clock:

~~~java
@Bean
Clock businessClock() {
    return Clock.system(
            ZoneId.of("Asia/Ho_Chi_Minh"));
}
~~~

Trong ví dụ cần bật **@EnableScheduling** và import các class Spring Scheduling, **Clock**, **ZoneId**, **LocalDate**. Production có thể phải chạy nhiều tenant hoặc nhận kỳ xử lý do orchestration cấp, chứ không hard-code một tenant.

Nếu hai pod cùng tính ra:

~~~text
Pod A -> tenant-a, 2026-11-15, snap-v1, generation=1
Pod B -> tenant-a, 2026-11-15, snap-v1, generation=1
                        |
                        v
                  Cùng JobInstance
~~~

Cả hai cần truy cập **cùng JDBC JobRepository** để nhất quán danh tính. Nếu mỗi pod dùng một H2 in-memory repository hoặc schema riêng, chúng không thực sự điều phối cùng JobInstance.

Scheduler lock có thể hạn chế các pod cùng kích hoạt, nhưng **không thay thế identifying JobParameters**: REST API hoặc người vận hành vẫn có thể launch Job ngoài scheduler lock.

Lưu ý ranh giới ngày và clock: dùng múi giờ xác định; nếu snapshot chưa FINALIZED, không tạo ID ngẫu nhiên để ép chạy. Cần quy tắc hoãn/retry theo kỳ nghiệp vụ.

## 14. Restart phải giữ nguyên identifying parameters

Giả sử Job nhập bảy order, chunk size 3, lỗi có kiểm soát tại item thứ năm:

~~~text
Input: O-101 ... O-107

Execution #201:
  Chunk 1: O-101, O-102, O-103 -> commit
  Chunk 2: O-104, O-105, O-106 -> lỗi, rollback
  Job FAILED

Execution #202:
  Restart cùng JobInstance
  Đọc lại từ checkpoint được hỗ trợ
  Hoàn tất các phần chưa commit
  Job COMPLETED
~~~

Đoạn gọi:

~~~java
ImportRunKey key = new ImportRunKey(
        "tenant-a",
        LocalDate.of(2026, 11, 15),
        "snap-a-20261115-v1",
        1L);

JobParameters params =
        key.toParameters("integration-test", "restart-case");

JobExecution first = jobLauncher.run(importOrdersJob, params);
// Giả định lần đầu có lỗi và trả về FAILED.

// Bỏ điều kiện lỗi, KHÔNG thay key/params.
JobExecution restarted = jobLauncher.run(importOrdersJob, params);
~~~

Điều kiện quan trọng:

1. Input snapshot giữ nguyên bytes, nội dung và thứ tự reader.
2. JobRepository/ExecutionContext không bị xóa hoặc sửa thủ công.
3. Reader/writer ItemStream được cấu hình checkpoint/restart đúng.
4. Writer và side effect có transaction/idempotency phù hợp.
5. Các tham số làm thay đổi business output không được đổi giữa restart.
6. Nếu Step đã COMPLETED, restart mặc định có thể bỏ qua Step ấy; khi cần reprocess phải có workflow riêng.

Dùng timestamp identifying mới ở execution thứ hai **không phải restart**. Nó tạo JobInstance khác, có thể đọc lại từ đầu và gây duplicate.

## 15. HTTP retry khác restart Job

Một client gọi API để launch rồi timeout. Nó không biết server đã tạo JobExecution chưa, nên gửi lại request.

Hai request HTTP không nhất thiết là hai đơn vị nghiệp vụ. Thiết kế đúng:

~~~text
HTTP request A: requestId=req-100
HTTP request B: requestId=req-101 (retry)

Business identity cả hai:
  tenant-a / 2026-11-15 / snap-v1 / gen=1
~~~

Có thể dùng **HTTP Idempotency-Key** ở tầng API, nhưng **business run key** vẫn cần ổn định dù requestId thay đổi.

Luồng xử lý gợi ý:

1. Xác định và chuẩn hóa ImportRunKey.
2. Kiểm tra quyền và snapshot FINALIZED.
3. Tra cứu tình trạng hiện tại nếu cần hiển thị.
4. Gọi JobLauncher với cùng identifying parameters.
5. Xử lý trường hợp COMPLETED, RUNNING hoặc FAILED theo contract.
6. Không tạo generation mới khi chỉ đang retry HTTP.
7. Nếu có race giữa tra cứu và launch, dựa vào JobRepository constraints/transaction để nhận kết quả cạnh tranh.

**Tra cứu trước rồi launch không phải thao tác nguyên tử.** Hai thread có thể cùng thấy “chưa tồn tại”; một JobRepository JDBC được cấu hình đúng mới là lớp kiểm soát nền, không phải một check-then-act trong controller.

## 16. Reprocess sau COMPLETED bằng generation có chủ đích

JobInstance generation 1 đã hoàn thành, nhưng doanh nghiệp yêu cầu tính lại sau khi sửa một thuật toán. Không nên thêm current timestamp chỉ để vượt qua **JobInstanceAlreadyCompleteException**.

~~~text
Generation 1:
  tenant-a / 2026-11-15 / snap-v1 / generation=1
  JobInstance #31
  COMPLETED

Generation 2 (được duyệt):
  tenant-a / 2026-11-15 / snap-v1 / generation=2
  JobInstance #47
  Kết quả xử lý lại
~~~

Nếu input thay đổi, dùng snapshot mới:

~~~text
Trước: snap-v1, generation=1
Sau:   snap-v2, generation=1
~~~

Ý nghĩa khác nhau:

- **snapshot v2**: nguồn dữ liệu khác.
- **generation 2**: tạo một bản kết quả xử lý/phát hành mới có chủ đích trên nguồn và quy tắc đã chốt.

Cần audit **ai yêu cầu, lý do, thời gian, phiên bản thuật toán, generation trước, kết quả đối soát và phê duyệt publish**. Không cho người dùng tùy ý tăng generation để tạo vô hạn JobInstance hoặc xử lý trùng giao dịch.

Nếu writer có tác dụng ngoài database như gửi email/chuyển tiền, generation mới có thể tạo tác dụng phụ lặp. Phải có quy tắc reprocess, idempotency key hoặc compensation riêng, không coi generation là đủ để bảo vệ.

## 17. Bảng quyết định các tình huống quan trọng

| Tình huống | Identifying values | JobInstance kỳ vọng |
| --- | --- | --- |
| Hai pod chạy cùng kỳ/snapshot | Giống nhau | Cùng |
| API bị timeout rồi retry | Giống nhau | Cùng |
| Job FAILED và restart | Giống nhau | Cùng, JobExecution mới |
| Job COMPLETED bị launch lại | Giống nhau | Bị từ chối chạy lại, không tạo instance mới |
| Hai tenant cùng ngày | tenantId khác | Khác |
| Cùng tenant/ngày nhưng snapshot mới | snapshotId khác | Khác |
| Reprocess được phê duyệt | generation khác | Khác |
| Đổi requestedBy/traceId | Identifying không đổi | Cùng |
| Đổi run.id ngẫu nhiên | Identifying khác | Khác, thường không mong muốn |
| Đổi processing rule làm output khác | Phải chốt revision theo key | Khác hoặc có workflow version hóa |

**Không phải UUID luôn sai**. Nếu Job được thiết kế xử lý từng thông điệp và message ID thực sự là danh tính nghiệp vụ bền vững, UUID của thông điệp có thể là identifying hợp lệ. Sai lầm là dùng ID ngẫu nhiên **cho mỗi attempt** trong khi các attempt cùng xử lý một lô.

## 18. Kiểm thử JobInstance bằng Spring Batch Test

Nên kiểm tra identity trên **JobRepository thực**, không chỉ tự ghép chuỗi và so sánh.

Ví dụ với JUnit 5, Spring Batch Test, Spring Boot Test, AssertJ; giả định Job được cấu hình và có fixture snapshot bất biến:

~~~java
@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class ImportJobIdentityTest {

    @Autowired
    private JobLauncher jobLauncher;

    @Autowired
    @Qualifier("importOrdersJob")
    private Job importOrdersJob;

    @Test
    void refusesSecondLaunchAfterCompleted() throws Exception {
        String snapshotId = createFinalizedSnapshotFixture();

        ImportRunKey key = new ImportRunKey(
                "tenant-a",
                LocalDate.of(2026, 11, 15),
                snapshotId,
                1L);

        JobParameters parameters =
                key.toParameters("test", "trace-a");

        JobExecution first =
                jobLauncher.run(importOrdersJob, parameters);

        assertThat(first.getStatus())
                .isEqualTo(BatchStatus.COMPLETED);

        assertThatThrownBy(
                () -> jobLauncher.run(importOrdersJob, parameters))
                .isInstanceOf(JobInstanceAlreadyCompleteException.class);
    }
}
~~~

**createFinalizedSnapshotFixture()** là helper cần tự triển khai, làm nhiệm vụ chèn dữ liệu nguồn và đánh dấu snapshot FINALIZED. Đoạn này trình bày phần assertion identity. Test phải cấu hình database/schema, bean Job và launcher đồng bộ hoặc chủ động đợi hoàn thành.

Nếu trong context có nhiều Job, inject bằng **@Qualifier** để trỏ đúng Job. Không dùng chung một snapshot cố định cho tất cả test độc lập nếu chúng có thể chạy song song.

### Test đổi non-identifying không tạo JobInstance mới

~~~java
JobParameters firstParams =
        key.toParameters("scheduler", "trace-1");

JobParameters anotherRequest =
        key.toParameters("operator", "trace-2");

JobExecution first =
        jobLauncher.run(importOrdersJob, firstParams);

assertThat(first.getStatus()).isEqualTo(BatchStatus.COMPLETED);

assertThatThrownBy(
        () -> jobLauncher.run(importOrdersJob, anotherRequest))
        .isInstanceOf(JobInstanceAlreadyCompleteException.class);
~~~

Nếu test này tạo JobInstance khác, có khả năng **traceId** hoặc **requestedBy** bị gắn identifying=true ở một code path.

### Test snapshot/generation khác tạo JobInstance khác

~~~java
ImportRunKey keyV1 =
        new ImportRunKey("tenant-a", date, "snapshot-v1", 1L);

ImportRunKey keyV2 =
        new ImportRunKey("tenant-a", date, "snapshot-v2", 1L);

JobExecution v1 = jobLauncher.run(
        importOrdersJob, keyV1.toParameters("test", "t1"));

JobExecution v2 = jobLauncher.run(
        importOrdersJob, keyV2.toParameters("test", "t2"));

assertThat(v1.getJobInstance().getId())
        .isNotEqualTo(v2.getJobInstance().getId());
~~~

Cần tạo và chốt cả hai snapshot trước khi chạy. Test này chỉ kiểm tra identity; để xác nhận nghiệp vụ, phải đối soát đúng output của từng snapshot.

### Test restart dùng cùng JobInstance

~~~java
JobParameters params =
        key.toParameters("test", "restart-case");

JobExecution failed = jobLauncher.run(importOrdersJob, params);
assertThat(failed.getStatus()).isEqualTo(BatchStatus.FAILED);

// Tắt failure injection của fixture test.
JobExecution recovered =
        jobLauncher.run(importOrdersJob, params);

assertThat(recovered.getStatus()).isEqualTo(BatchStatus.COMPLETED);
assertThat(recovered.getId()).isNotEqualTo(failed.getId());
assertThat(recovered.getJobInstance().getId())
        .isEqualTo(failed.getJobInstance().getId());
~~~

Để có giá trị, test cần tạo failure **sau một chunk đã commit**, giữ input bất biến, sau đó kiểm tra bản ghi đầu ra không thiếu/trùng. Chỉ assert JobInstance ID là chưa đủ để khẳng định restart đúng dữ liệu.

## 19. Kiểm thử hai scheduler launch đồng thời

Một hệ thống có nhiều pod cần chứng minh hai yêu cầu song song với cùng key **không tạo hai JobInstance**.

~~~text
Thread A --+
           +--> launch(same Job, same identifying parameters)
Thread B --+
                         |
                         v
                Shared JDBC JobRepository
                         |
                         +--> Một JobInstance cho business key
                         +--> Trạng thái execution quyết định
                              yêu cầu nào được phép chạy
~~~

Thiết kế integration test:

1. Tạo snapshot riêng và một ImportRunKey.
2. Khởi chạy hai thread gần đồng thời bằng **CountDownLatch** hoặc **CyclicBarrier**.
3. Giữ Job hoạt động đủ lâu nếu cần xác minh trạng thái STARTED.
4. Ghi nhận execution/exception của mỗi yêu cầu, **không giả định thread A luôn thắng**.
5. Truy vấn JobRepository để xác minh chỉ một JobInstance ứng với key.
6. Kiểm tra output cuối có một tập bản ghi đúng, không bị ghi trùng.

Không chỉ dùng **Thread.sleep** làm đồng bộ test; timing ngẫu nhiên tạo flaky test. Hai repository H2 in-memory độc lập cũng không phải bằng chứng điều phối nhiều JVM. Hãy dùng chung một JDBC repository như kiến trúc thật.

## 20. Các lỗi thiết kế thường gặp

### Tự tạo run.id khác nhau cho mọi lần chạy

~~~java
new JobParametersBuilder()
        .addLong("run.id", System.currentTimeMillis())
        .toJobParameters();
~~~

Trong builder, tham số thường mặc định identifying=true nếu không ghi rõ. Lúc đó cùng dữ liệu có thể bị chạy nhiều lần như những JobInstance khác nhau. Dùng business key ổn định.

### Chỉ định danh bằng businessDate

Nếu một Job xử lý nhiều tenant hoặc nhiều snapshot/ngày, businessDate đơn lẻ không đủ. Một yêu cầu hợp lệ có thể bị từ chối vì instance khác đã COMPLETED.

### Đổi identifying parameters để restart

Restart cần cùng JobInstance. Thay timestamp hoặc generation ngay sau failure có thể bỏ qua checkpoint và xử lý lại từ đầu.

### Dùng sourceSnapshotId non-identifying

Snapshot mới có thể bị gom vào JobInstance cũ hoặc restart với input khác. Xác định rõ nguồn mới là công việc mới hay không.

### Đặt file path mutable làm identity

Đường dẫn **/incoming/orders.csv** có thể bị ghi đè. Cần snapshot ID hoặc object version/digest bất biến.

### Không chốt phiên bản biến đổi nghiệp vụ

Sau deploy, một Job FAILED được restart bằng logic mới, output có thể trộn hai phiên bản. Cần version hóa quy tắc và policy restart/reprocess.

### Trộn các generation trong output

Generation mới có JobInstance riêng nhưng downstream đọc cả hai kết quả. Thiết kế publication pointer hoặc version contract.

### Sửa BATCH_JOB_INSTANCE/BATCH_JOB_EXECUTION bằng SQL

Đổi STATUS, JOB_KEY hoặc xóa metadata để ép chạy có thể phá history và checkpoint. Sử dụng lifecycle API và quy trình vận hành được kiểm soát.

### Lưu secret trong parameters

Identifying=false không phải cơ chế bảo mật. Secret phải nằm ở nơi quản lý bí mật thích hợp.

### Chỉ kiểm tra số JobInstance mà bỏ qua dữ liệu

Một JobInstance duy nhất vẫn có thể ghi sai amount hoặc xử lý input mutable. Cần validation, idempotency và reconciliation.

## 21. Quy trình triển khai trong production

~~~text
Scheduler / API / Operator
           |
           v
Authentication + tenant authorization
           |
           v
Canonicalize business key
           |
           v
Check snapshot FINALIZED + immutable version
           |
           v
Build JobParameters với identifying flags rõ ràng
           |
           v
JobLauncher + shared JobRepository
           |
    +------+--------+---------+
    |               |         |
   NEW          RUNNING     COMPLETED
    |               |         |
    v               v         v
  Run Job        Return      Return
                 status      existing result
    |
    +--> FAILED: restart same identity
    |
    +--> COMPLETED: reconcile and publish
    |
    +--> Approved reprocess: new generation/snapshot
~~~

Lớp điều phối nên log/audit **Job name, tenantId, businessDate, snapshotId, generation, JobInstance ID, JobExecution ID, requestedBy và lý do reprocess**, theo quyền dữ liệu của tổ chức. Không log mật khẩu hoặc raw ExecutionContext.

Hệ thống cần trả lời nhất quán cho request bị retry và race: không tự động tạo một identity mới để tránh exception. Với lỗi repository, trước khi retry hãy xác nhận có execution đã được tạo chưa.

## 22. Checklist hoàn tất dự án thực hành

- [ ] Định nghĩa rõ một **đơn vị công việc nghiệp vụ** của Job.
- [ ] Có một factory/value object tạo identity thống nhất.
- [ ] Tenant, ngày, snapshot và generation có kiểu/giá trị chuẩn.
- [ ] Input snapshot bất biến giữa các lần restart.
- [ ] Tham số ảnh hưởng output được identifying hoặc gắn với version bất biến.
- [ ] requestedBy và traceId không tạo JobInstance mới.
- [ ] JobParametersValidator từ chối thiếu key, sai format và sai identifying flags.
- [ ] Reader chỉ đọc input thuộc đúng tenant/snapshot.
- [ ] Writer ghi đúng vùng dữ liệu và có idempotency.
- [ ] Scheduler/API/operator dùng chung quy tắc tạo parameters.
- [ ] Launch trùng Job COMPLETED không tự thành một lần xử lý mới.
- [ ] Restart FAILED sử dụng cùng identifying parameters.
- [ ] Reprocess sau COMPLETED dùng snapshot/generation mới có phê duyệt.
- [ ] Có test concurrent launch trên JobRepository dùng chung.
- [ ] Có test restart và đối soát output không mất/trùng.
- [ ] Downstream chỉ chọn generation đã được công bố.
- [ ] Không có bí mật trong metadata JobParameters.

## 23. Kết luận

Câu hỏi cốt lõi khi thiết kế **JobParameters** không phải **“làm thế nào để Job chịu chạy lại?”** mà là **“thế nào là một công việc nghiệp vụ duy nhất?”**.

Với dự án nhập đơn hàng nhiều tenant, **tên Job + (tenantId, businessDate, sourceSnapshotId, generation)** tạo identity có ý nghĩa. Nếu lần chạy đầu thất bại, Spring Batch **restart cùng JobInstance** bằng identifying parameters cũ. Nếu có snapshot mới hoặc một lần reprocess được phê duyệt, ứng dụng tạo **JobInstance khác một cách có chủ đích**. Các giá trị như requestedBy/traceId giúp quan sát mà không đổi đơn vị công việc.

Kết hợp **canonicalization, validation, snapshot bất biến, JobRepository dùng chung, writer idempotent và integration test** giúp tránh hai lỗi trái ngược: xử lý trùng cùng dữ liệu hoặc từ chối nhầm một lô mới. Đây là nền tảng để một hệ thống Spring Batch có thể restart, backfill, audit và mở rộng nhiều instance an toàn.

