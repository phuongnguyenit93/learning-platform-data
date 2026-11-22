# Phân biệt dữ liệu nghiệp vụ với metadata của Spring Batch

Trong hệ thống **SPRING_BOOT_INTEGRATION**, Spring Boot không chỉ gọi HTTP client, database, cache hoặc message broker mà còn cần xử lý những luồng dữ liệu có số lượng lớn: nhập hóa đơn từ CSV, đồng bộ sản phẩm từ đối tác, đối soát thanh toán, xuất báo cáo hoặc nhận dữ liệu từ một hệ thống cũ. **Spring Batch** giúp tổ chức các công việc đó thành **Job** và **Step**, theo dõi quá trình thực thi, kiểm soát giao dịch theo từng chunk và tiếp tục công việc sau lỗi.

Để thiết kế batch đáng tin cậy, cần phân biệt hai lớp dữ liệu có mục đích rất khác nhau:

- **Dữ liệu nghiệp vụ (business data):** hóa đơn, đơn hàng, khách hàng, số tiền, trạng thái đối soát, dữ liệu hợp lệ hoặc bị từ chối. Những giá trị này do **hợp đồng và quy tắc nghiệp vụ** quyết định.
- **Metadata của Spring Batch (batch metadata):** Job nào đã được chạy, với tham số nào, lần chạy nào thành công/thất bại, Step nào đọc/ghi bao nhiêu item, checkpoint để tiếp tục từ đâu. Những giá trị này phục vụ **điều phối, giám sát và restart kỹ thuật**.

Hai lớp thường được lưu trong cùng hệ quản trị cơ sở dữ liệu, đôi khi thậm chí cùng một database, nhưng **không vì vậy mà có cùng chủ sở hữu, vòng đời hoặc ý nghĩa**. Spring Batch quản lý metadata thông qua **JobRepository**; ứng dụng chịu trách nhiệm về dữ liệu nghiệp vụ thông qua repository, SQL writer, API và các chính sách nhất quán của riêng mình.

## 1. Bài toán xuyên suốt: nhập hóa đơn từ CSV

Giả sử mỗi ngày hệ thống nhận một tệp hóa đơn của đối tác A:

~~~csv
sourceInvoiceId,customerId,amountVnd
INV-001,CUS-01,125000
INV-002,CUS-02,99000
INV-003,CUS-03,325000
~~~

Job **importInvoicesJob** có một Step tên **invoiceImportStep**: đọc từng dòng, kiểm tra giá trị và ghi vào bảng **business_invoice**. Batch xử lý theo chunk gồm 100 dòng và cho phép restart sau lỗi.

~~~mermaid
flowchart TD
    SRC["CSV hóa đơn từ đối tác"] --> READER["ItemReader"]
    READER --> PROCESSOR["ItemProcessor: kiểm tra/chuẩn hóa"]
    PROCESSOR --> WRITER["ItemWriter: ghi business_invoice"]
    WRITER --> DOMAIN[("Business tables: hóa đơn và đối soát")]
    JR["JobRepository"] <--> META[("BATCH_* metadata tables")]
    JR -. "Job/Step status, counts, checkpoint" .-> READER
    JR -. "Lưu tiến độ và lỗi" .-> WRITER
    DOMAIN --> API["API và báo cáo nghiệp vụ"]
    META --> OPS["Giám sát Job/Step và restart"]
~~~

Sau khi nhập 300 dòng, hệ thống có thể đồng thời lưu:

| Nơi lưu | Giá trị minh họa | Câu hỏi được trả lời |
| --- | --- | --- |
| **business_invoice** | INV-001, CUS-01, 125000 VND | Hóa đơn nào tồn tại, khách hàng nào, số tiền bao nhiêu? |
| **BATCH_JOB_INSTANCE** | importInvoicesJob với tập tham số định danh | Đây là **công việc logic** nào? |
| **BATCH_JOB_EXECUTION** | Execution 712, status COMPLETED | Lần chạy thứ 712 kết thúc kỹ thuật ra sao? |
| **BATCH_STEP_EXECUTION** | readCount=300, writeCount=300, commitCount=3 (minh họa) | Step đã xử lý bao nhiêu item/chunk? |
| **BATCH_STEP_EXECUTION_CONTEXT** | Vị trí/tiến độ của reader | Khi restart, reader có thể tiếp tục từ đâu? |

**Số lượng item được writer xử lý không nhất thiết bằng số bản ghi nghiệp vụ mới được tạo.** Nếu dùng lệnh SQL **ON CONFLICT DO NOTHING**, writer có thể nhận 300 item nhưng một số đã có trong database. Do đó, **writeCount** không phải chỉ số thay thế đáng tin cậy cho doanh thu, số hóa đơn mới hoặc số lượng hóa đơn được duyệt.

## 2. Ai sở hữu và sử dụng hai lớp dữ liệu?

| Tiêu chí | Dữ liệu nghiệp vụ | Metadata Spring Batch |
| --- | --- | --- |
| Chủ sở hữu ngữ nghĩa | Domain service, quy tắc nghiệp vụ và chủ dữ liệu | Spring Batch framework, JobRepository |
| Nơi lưu | Bảng/domain schema, kho dữ liệu, đối tác ngoài | Bộ bảng metadata Spring Batch, thường có prefix **BATCH_** |
| Định danh | invoiceId, orderId, customerId, sourceBatchId | JobInstanceId, JobExecutionId, StepExecutionId |
| Tính đúng đắn | Hóa đơn phải hợp lệ, không ghi trùng, số tiền đúng | Trạng thái/lần chạy/tiến độ được ghi đúng để điều phối |
| Khi Job FAILED | Những bản ghi của các chunk đã commit vẫn có thể tồn tại | Ghi nhận execution FAILED và checkpoint gần nhất |
| Khi Job COMPLETED | **Chưa chứng minh** toàn bộ nghiệp vụ đã đối soát | Chứng minh các Step kết thúc theo flow và chính sách lỗi đã cấu hình |
| Khi chạy lại | Có thể cần upsert, dedupe, reconciliation, sửa dữ liệu | Xác định có restart cùng JobInstance hay tạo JobInstance mới |
| Dọn dẹp | Theo quy định lưu trữ hóa đơn/audit và nghiệp vụ | Theo thời gian giữ execution history và nhu cầu restart |
| Người sử dụng | API, báo cáo, đối soát, các service khác | JobLauncher, JobExplorer, JobOperator, dashboard vận hành |

Quy tắc thiết kế: **business data trả lời “điều gì đã xảy ra trong nghiệp vụ”; batch metadata trả lời “một Job/Step được thực thi thế nào”.** Hai câu hỏi có thể liên quan nhưng không đồng nhất.

### 2.1. Metadata không phải kho dữ liệu trung gian

Không nên đưa toàn bộ CSV, danh sách một triệu invoiceId, toàn bộ HTTP response hoặc object domain lớn vào **ExecutionContext**. ExecutionContext là state cho cơ chế restart, được serialize để lưu bền vững; payload lớn làm tăng chi phí cập nhật metadata, kích thước transaction và rủi ro tương thích khi thay đổi class.

Nếu cần một tập dữ liệu chờ duyệt, bảng staging hoặc bảng rejection, hãy tạo **bảng nghiệp vụ riêng** với khóa, trạng thái, vòng đời và quyền truy cập rõ ràng. JobRepository không tự đảm nhận kiểm soát chất lượng dữ liệu, chống trùng theo khóa hóa đơn hay lưu lý do duyệt/từ chối có giá trị pháp lý.

## 3. Các thực thể metadata cần hiểu

Spring Batch diễn tả một công việc theo hệ phân cấp:

~~~mermaid
flowchart TD
    JOB["Job: importInvoicesJob"] --> INST["JobInstance: tên Job + identifying JobParameters"]
    INST --> EXEC1["JobExecution #1: FAILED"]
    INST --> EXEC2["JobExecution #2: COMPLETED (restart)"]
    EXEC1 --> STEP1["StepExecution: invoiceImportStep #1"]
    EXEC2 --> STEP2["StepExecution: invoiceImportStep #2"]
    EXEC1 --> CTX1["Job ExecutionContext"]
    EXEC2 --> CTX2["Job ExecutionContext"]
    STEP1 --> SCTX1["Step ExecutionContext: checkpoint"]
    STEP2 --> SCTX2["Step ExecutionContext: checkpoint mới"]
~~~

### 3.1. Job, JobInstance và JobExecution

**Job** là định nghĩa luồng xử lý, ví dụ: nhập hóa đơn, kiểm tra, ghi vào DB rồi tạo báo cáo. Tên Job là một phần định danh logic.

**JobInstance** định danh **một lần xử lý logic** của Job dựa trên:

\[
\text{JobInstance} = (\text{jobName},\ \text{identifying JobParameters})
\]

**JobExecution** là **một lần thử thực thi** JobInstance. Nếu lần chạy đầu thất bại, restart có thể tạo **JobExecution mới** thuộc **cùng JobInstance**. Nếu một JobInstance đã COMPLETED, chạy lại với cùng tập identifying parameters thường bị Spring Batch từ chối thay vì tạo thêm một execution mới giống hệt.

**JobParameters** là các giá trị cung cấp lúc launch, ví dụ:

- **inputFile**: đường dẫn file đầu vào.
- **sourceBatchId**: định danh lô do đối tác cấp.
- **requestedBy**: người/kênh yêu cầu chạy, chỉ phục vụ audit.

Chỉ những JobParameter được đánh dấu **identifying** mới tham gia định danh JobInstance. **requestedBy** có thể là non-identifying, vì thay đổi người yêu cầu không nên biến cùng một lô thành công việc logic khác.

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFile", "/data/invoices/partner-a-2026-11-21.csv", true)
        .addString("sourceBatchId", "PARTNER-A-2026-11-21", true)
        .addString("requestedBy", "operations", false)
        .toJobParameters();

JobExecution execution = jobLauncher.run(importInvoicesJob, parameters);
~~~

Đoạn mã dùng API Spring Batch **5+**: tham số boolean cuối của các phương thức addString xác định identifying hay non-identifying. Để **restart**, dùng cùng tham số định danh và một JobInstance còn ở trạng thái restart được. Đổi **sourceBatchId**, thay đường dẫn file, hoặc dùng **RunIdIncrementer** để tăng identifying run.id sẽ tạo một **JobInstance khác**, tức là một lượt xử lý logic mới; nó **không phải restart của lần trước**.

Không để timestamp ngẫu nhiên hay requestId mới mặc định thành identifying parameter mỗi khi thử lại một lô: như vậy Spring Batch sẽ mất khả năng liên hệ các execution với cùng một công việc logic. Ngược lại, khi nghiệp vụ thật sự có lô nhập mới, cần xác định một sourceBatchId mới để phân biệt.

### 3.2. StepExecution và bộ đếm kỹ thuật

Một Job có thể chứa nhiều Step, chẳng hạn **download**, **validate**, **import**, **publishResult**. **StepExecution** ghi trạng thái của **một lượt chạy Step**, cùng các số liệu:

- **readCount:** số item reader phát ra cho quá trình xử lý.
- **filterCount:** số item được processor lọc ra.
- **writeCount:** số item được chuyển đến writer.
- **readSkipCount, processSkipCount, writeSkipCount:** các loại item được skip theo chính sách fault tolerance.
- **commitCount, rollbackCount:** số lần giao dịch/chunk được commit/rollback.
- **BatchStatus, ExitStatus, startTime, endTime:** trạng thái và kết quả kỹ thuật của Step.

Ví dụ **COMPLETED + writeCount=300** vẫn không bảo đảm 300 hóa đơn được insert mới: writer có thể upsert, bỏ qua bản ghi trùng, gọi API bên ngoài hoặc ghi nhiều bảng. Nếu processor filter 20 bản ghi thì **readCount=300** và **writeCount=280** cũng không chứng minh 20 dòng đó là dữ liệu sai; việc filter có thể là quyết định nghiệp vụ hợp lệ.

**BatchStatus** là trạng thái thực thi do framework quản lý, thường gặp **STARTING, STARTED, STOPPING, STOPPED, COMPLETED, FAILED, ABANDONED, UNKNOWN**. **ExitStatus** diễn đạt kết quả/đường chuyển Step theo flow và có thể tùy biến. Không dùng hai giá trị này làm trạng thái thanh toán, trạng thái đã đối soát hay đã phê duyệt hóa đơn.

### 3.3. JobExecutionContext và StepExecutionContext

**ExecutionContext** là tập khóa-giá trị mà framework hoặc Step dùng để lưu trạng thái cần thiết cho restart:

| Scope | Ví dụ dữ liệu | Mục đích |
| --- | --- | --- |
| **Job ExecutionContext** | Mã đối tác đã chọn, tên snapshot dùng chung các Step | Truyền state bền vững giữa các Step của JobInstance khi thích hợp |
| **Step ExecutionContext** | Vị trí reader, số dòng đã đọc, cursor/checkpoint | Khôi phục riêng Step sau khi dừng hoặc lỗi |

ExecutionContext là cấu trúc **tồn tại bền vững trong metadata**, khác với thuộc tính chỉ lưu trong RAM của một bean. Spring Batch có cơ chế tự động duy trì state của các **ItemStream** như FlatFileItemReader khi được đăng ký đúng và **saveState** bật.

Một số lưu ý:

- Chỉ lưu state **nhỏ, ổn định, cần cho restart**: offset, lastProcessedKey, tên snapshot, cờ quy trình kỹ thuật.
- Không lưu dữ liệu nhạy cảm (token, mật khẩu, thông tin thẻ), object domain lớn hoặc response thô.
- Nếu tự quản lý offset, cập nhật nó đúng ranh giới commit; sai thời điểm có thể gây bỏ sót hoặc xử lý lại dữ liệu.
- Thay đổi tên key, class serializer hoặc cấu trúc state giữa hai phiên bản ứng dụng có thể khiến restart từ execution cũ bị lỗi.
- Đừng xem **StepExecutionContext** là nguồn chân lý của trạng thái nghiệp vụ. Hóa đơn đã ghi và đã đối soát phải được quyết định từ các bản ghi nghiệp vụ.

## 4. JobRepository lưu metadata ở đâu?

Khi dùng **JDBC JobRepository**, Spring Batch tạo/cập nhật các bảng metadata chuyên dụng. Tên và cấu trúc chi tiết phụ thuộc phiên bản/schema được cài, nhưng các bảng nền tảng gồm:

| Bảng | Nội dung |
| --- | --- |
| **BATCH_JOB_INSTANCE** | Job instance id, job name và job key |
| **BATCH_JOB_EXECUTION** | Mỗi lần thực thi JobInstance: thời gian, trạng thái, kết quả |
| **BATCH_JOB_EXECUTION_PARAMS** | JobParameters của từng JobExecution và cờ identifying |
| **BATCH_STEP_EXECUTION** | Thực thi Step, bộ đếm read/write/skip/commit/rollback |
| **BATCH_JOB_EXECUTION_CONTEXT** | ExecutionContext cấp Job |
| **BATCH_STEP_EXECUTION_CONTEXT** | ExecutionContext cấp Step |
| **BATCH_JOB_SEQ**, **BATCH_JOB_EXECUTION_SEQ**, **BATCH_STEP_EXECUTION_SEQ** | Sequence/bộ cấp ID tùy cơ sở dữ liệu |

Các bảng này phục vụ **JobRepository** và các API đọc/quản trị execution như **JobExplorer**, **JobOperator**. Thông thường **không sửa trực tiếp** các hàng metadata để đánh dấu thành công, nhảy qua Step, hoặc tự tăng readCount: điều đó có thể khiến trạng thái restart không nhất quán. Dùng API Spring Batch và cơ chế vận hành có kiểm soát.

Ví dụ truy vấn quan sát execution (tên bảng/cột tương ứng schema tiêu chuẩn):

~~~sql
SELECT ji.JOB_NAME,
       je.JOB_EXECUTION_ID,
       je.STATUS,
       je.EXIT_CODE,
       je.START_TIME,
       je.END_TIME
FROM BATCH_JOB_EXECUTION je
JOIN BATCH_JOB_INSTANCE ji
  ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'importInvoicesJob'
ORDER BY je.JOB_EXECUTION_ID DESC;
~~~

Truy vấn này trả lời Job **đã chạy thế nào**, không trả lời hóa đơn nào đã lưu đúng. Muốn biết số hóa đơn vừa import, vẫn cần truy vấn nghiệp vụ theo **sourceBatchId** hoặc **importRunId**, với các ràng buộc dữ liệu phù hợp.

### 4.1. Khởi tạo schema metadata

Với Spring Boot khi dùng JDBC JobRepository, môi trường development có thể cho phép tạo schema tự động:

~~~yaml
spring:
  batch:
    jdbc:
      initialize-schema: always  # chỉ thích hợp cho môi trường dev/test có kiểm soát
    job:
      enabled: false             # ví dụ: không tự chạy Job khi app khởi động
~~~

Trong production, nên quản lý thay đổi schema bằng **Flyway/Liquibase** hoặc quy trình migration tương đương, chọn script/schema **đúng phiên bản Spring Batch và loại database**, và sao lưu trước khi nâng cấp. Tách quyền DDL khỏi tài khoản chạy Job khi phù hợp. Việc có bảng **BATCH_*** không có nghĩa dữ liệu hóa đơn đã được tạo; business schema phải có migration và chính sách lưu trữ riêng.

Nếu ứng dụng dùng nhiều DataSource/transaction manager, phải cấu hình rõ **DataSource của JobRepository**, **DataSource của ItemWriter** và transaction manager của Step. Việc framework và nghiệp vụ đều dùng PostgreSQL **không tự chứng minh** chúng tham gia cùng một transaction nếu trỏ vào hai database/connection manager khác nhau.

## 5. Thiết kế bảng dữ liệu nghiệp vụ và chống trùng

Ví dụ PostgreSQL cho dữ liệu hóa đơn:

~~~sql
CREATE TABLE business_invoice (
    id                  bigserial PRIMARY KEY,
    source_system       varchar(40) NOT NULL,
    source_invoice_id   varchar(100) NOT NULL,
    customer_id         varchar(100) NOT NULL,
    amount_vnd          numeric(18,2) NOT NULL,
    imported_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT business_invoice_amount_positive CHECK (amount_vnd > 0),
    CONSTRAINT business_invoice_source_unique
        UNIQUE (source_system, source_invoice_id)
);
~~~

**source_system + source_invoice_id** là ví dụ về **khóa chống trùng nghiệp vụ**. Nó khác hoàn toàn **JobExecutionId**: cùng hóa đơn có thể xuất hiện trong hai file hoặc hai lần import, nhưng không được tạo hai hóa đơn chỉ vì Job chạy lại. Khóa chống trùng phải được lựa chọn theo hợp đồng nguồn; nếu invoiceId chỉ duy nhất trong phạm vi một đối tác, cần kết hợp source_system.

Khi yêu cầu lưu trạng thái một lô import để người dùng theo dõi và phê duyệt, có thể có bảng nghiệp vụ:

~~~sql
CREATE TABLE invoice_import_run (
    import_id           uuid PRIMARY KEY,
    source_batch_id     varchar(120) NOT NULL UNIQUE,
    business_status     varchar(24) NOT NULL,
    accepted_count      bigint NOT NULL DEFAULT 0,
    rejected_count      bigint NOT NULL DEFAULT 0,
    created_at          timestamptz NOT NULL DEFAULT now(),
    finished_at         timestamptz
);
~~~

**invoice_import_run.business_status** có thể là **RECEIVED, VALIDATING, WAITING_APPROVAL, APPROVED, REJECTED, PUBLISHED**, theo chính sách sản phẩm. Trạng thái này **khác** BatchStatus **COMPLETED/FAILED**. Một Job import có thể COMPLETED nhưng lô đang **WAITING_APPROVAL**; đây không phải mâu thuẫn mà là hai vòng đời khác nhau.

Nếu cùng mã hóa đơn trở lại với số tiền khác, **ON CONFLICT DO NOTHING** có thể bỏ qua khác biệt nguy hiểm. Khi đó cần so sánh nội dung hiện tại với payload mới và ghi vào bảng reconciliation/error nghiệp vụ; unique constraint chỉ ngăn insert trùng, không tự phát hiện tính đúng đắn của dữ liệu.

## 6. Ví dụ cấu hình Job/Step Spring Batch 5+ và writer nghiệp vụ

Ví dụ dưới đây cho thấy các thành phần làm việc riêng: **JobRepository** lo metadata; **ItemReader/ItemWriter** đọc CSV và ghi bảng hóa đơn. Mẫu giả định ứng dụng đã cấu hình Spring Batch JDBC metadata, một DataSource PostgreSQL và transaction manager phù hợp. Để tập trung vào nguyên lý, các import Java được lược bỏ và mỗi kiểu có thể tách sang file riêng.

### 6.1. DTO đầu vào

~~~java
public record InvoiceRow(
        String sourceInvoiceId,
        String customerId,
        BigDecimal amountVnd) {}
~~~

### 6.2. Reader có khả năng checkpoint

~~~java
@Bean
@StepScope
FlatFileItemReader<InvoiceRow> invoiceReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    DelimitedLineTokenizer tokenizer = new DelimitedLineTokenizer();
    tokenizer.setNames("sourceInvoiceId", "customerId", "amountVnd");

    DefaultLineMapper<InvoiceRow> mapper = new DefaultLineMapper<>();
    mapper.setLineTokenizer(tokenizer);
    mapper.setFieldSetMapper(fields -> new InvoiceRow(
            fields.readString("sourceInvoiceId"),
            fields.readString("customerId"),
            fields.readBigDecimal("amountVnd")));

    return new FlatFileItemReaderBuilder<InvoiceRow>()
            .name("invoiceReader")
            .resource(new FileSystemResource(inputFile))
            .linesToSkip(1)
            .lineMapper(mapper)
            .saveState(true)
            .build();
}
~~~

**@StepScope** tạo reader trong context của một StepExecution và cho phép lấy **inputFile** từ JobParameters lúc chạy, thay vì lúc ứng dụng khởi động. Reader có tên ổn định và **saveState(true)** để lưu thông tin vị trí đọc vào Step ExecutionContext thông qua cơ chế **ItemStream**, khi đăng ký reader/stream đúng trong Step.

Checkpoint chỉ có ý nghĩa nếu **input file giữ nguyên nội dung** giữa lần chạy thất bại và lần restart. Nếu đối tác ghi đè file nhưng vẫn giữ tên cũ, trạng thái dòng đã đọc có thể trỏ vào dữ liệu khác. Nên dùng file snapshot bất biến cùng sourceBatchId/checksum; nếu cần, checksum được lưu trong bảng nghiệp vụ/audit và kiểm tra trước khi restart.

### 6.3. Writer ghi business_invoice

~~~java
@Bean
JdbcBatchItemWriter<InvoiceRow> invoiceWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<InvoiceRow>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO business_invoice
                        (source_system, source_invoice_id, customer_id, amount_vnd)
                    VALUES
                        (:sourceSystem, :invoiceId, :customerId, :amountVnd)
                    ON CONFLICT (source_system, source_invoice_id)
                    DO NOTHING
                    """)
            .itemSqlParameterSourceProvider(row ->
                    new MapSqlParameterSource()
                            .addValue("sourceSystem", "partner-a")
                            .addValue("invoiceId", row.sourceInvoiceId())
                            .addValue("customerId", row.customerId())
                            .addValue("amountVnd", row.amountVnd()))
            .assertUpdates(false)
            .build();
}
~~~

Đoạn **ON CONFLICT DO NOTHING** dành cho PostgreSQL và giúp tránh tạo thêm bản ghi khi replay cùng invoiceId; **assertUpdates(false)** chấp nhận các lệnh insert không ảnh hưởng hàng nào. Đây là ví dụ đơn giản cho khóa chống trùng, chưa có logic đối soát khi số tiền của một hóa đơn thay đổi.

### 6.4. Job và chunk Step

~~~java
@Bean
Step invoiceImportStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<InvoiceRow> invoiceReader,
        JdbcBatchItemWriter<InvoiceRow> invoiceWriter) {

    return new StepBuilder("invoiceImportStep", jobRepository)
            .<InvoiceRow, InvoiceRow>chunk(100, transactionManager)
            .reader(invoiceReader)
            .processor(row -> {
                if (row.amountVnd() == null ||
                        row.amountVnd().signum() <= 0) {
                    throw new IllegalArgumentException(
                            "Invalid amount for " + row.sourceInvoiceId());
                }
                return row;
            })
            .writer(invoiceWriter)
            .build();
}

@Bean
Job importInvoicesJob(JobRepository jobRepository,
                      Step invoiceImportStep) {
    return new JobBuilder("importInvoicesJob", jobRepository)
            .start(invoiceImportStep)
            .build();
}
~~~

Code dùng **JobBuilder** và **StepBuilder** nhận **JobRepository**, cùng kiểu cấu hình phổ biến từ **Spring Batch 5**. Với chunk size 100, framework lặp **read → process → write** cho một nhóm item trong ranh giới transaction của Step. Khi lỗi phát sinh và chưa được cấu hình skip/retry, transaction đang hoạt động có thể rollback, Step/Job chuyển sang FAILED; dữ liệu đã commit ở các chunk trước vẫn tồn tại.

Để tự động bỏ qua các dòng lỗi hoặc thử lại, cần cấu hình **faultTolerant, skip/retry policy** đúng theo loại lỗi và ngưỡng; đồng thời có bảng/log lỗi nghiệp vụ nếu cần lưu nguyên nhân từ chối. Đừng bắt mọi exception trong processor rồi lặng lẽ trả null: **null có nghĩa là filter**, thường dẫn tới không ghi dòng đó và có thể làm Job COMPLETED mà không đủ dữ liệu.

> **Ranh giới bảo đảm:** khi JobRepository và ItemWriter dùng **cùng database/transaction manager** và tham gia đúng transaction của chunk, việc commit dữ liệu và checkpoint metadata có thể được đồng bộ ở cấp database cục bộ. Nếu metadata ở database A còn hóa đơn ở database B, hoặc Step gọi HTTP/broker ngoài transaction, không có atomicity xuyên các hệ thống. Cần idempotency/reconciliation phù hợp thay vì dựa vào checkpoint như bảo đảm exactly-once end-to-end.

## 7. Điều gì xảy ra khi Job lỗi giữa các chunk?

Giả sử file có 250 hóa đơn, chunk size 100:

~~~mermaid
sequenceDiagram
    participant B as Spring Batch Step
    participant DB as Business DB
    participant JR as JobRepository
    B->>DB: Chunk 1: ghi item 1..100
    B->>JR: Cập nhật StepExecution/ExecutionContext
    Note over DB,JR: Commit chunk 1
    B->>DB: Chunk 2: ghi item 101..200
    B->>JR: Cập nhật checkpoint
    Note over DB,JR: Commit chunk 2
    B->>DB: Chunk 3: ghi item 201..250
    Note over B: Lỗi ở item 230, chunk 3 rollback
    B->>JR: Ghi trạng thái FAILED
    Note over DB: Hai chunk đầu vẫn đã commit
    B->>JR: Restart cùng identifying JobParameters
    JR-->>B: Khôi phục state reader từ checkpoint
    B->>DB: Xử lý phần còn lại, ghi idempotent
~~~

Nếu tất cả thành phần tham gia đúng giao dịch và reader có restart state ổn định, lần chạy tiếp theo có thể tiếp tục từ checkpoint bền vững gần nhất. **Không phải** restart sẽ luôn xử lý lại toàn bộ file, cũng không phải mọi reader đều tự khôi phục vị trí. Trạng thái và thứ tự xử lý phụ thuộc loại reader, processor, transaction manager và việc dữ liệu nguồn có bất biến hay không.

| Mốc | Dữ liệu nghiệp vụ | Metadata |
| --- | --- | --- |
| Chunk 1 và 2 commit | Khoảng 200 hóa đơn đã ghi | StepExecution cập nhật bộ đếm và checkpoint |
| Chunk 3 lỗi trước commit | Phần thay đổi trong chunk 3 rollback (nếu writer cùng transaction) | Step/Job có thể được ghi FAILED |
| Restart cùng JobInstance | Không được nhân đôi hai chunk đã commit | Tạo JobExecution mới, sử dụng checkpoint có thể khôi phục |
| Restart thành công | Phần còn lại được ghi, kết quả cần đối soát | JobExecution mới có thể COMPLETED |

Cần phân biệt **rollback SQL trong một chunk** với **rollback toàn bộ Job**. Một batch nhiều chunk **không phải một transaction lớn bao quanh tất cả dữ liệu**. Vì vậy, cách xử lý dữ liệu sau lỗi là quyết định thiết kế quan trọng.

### 7.1. Trường hợp checkpoint và business commit không đồng bộ

Nếu dữ liệu nghiệp vụ và JobRepository không dùng cùng transaction, có hai khoảng hở cần xử lý:

1. **Dữ liệu đã commit nhưng checkpoint chưa ghi**: khi restart, một số item có thể được chạy lại. Unique key/upsert/idempotent writer là biện pháp bảo vệ.
2. **Checkpoint tiến xa hơn dữ liệu đã commit**: nếu kiến trúc/cấu hình cho phép metadata ghi trước trong khi side effect nghiệp vụ chưa bền vững, restart có thể bỏ sót dữ liệu. Cần thiết kế transaction, thứ tự commit và cơ chế đối soát để tránh kịch bản này.

Với side effect qua HTTP hoặc message broker, dù Step transaction rollback, lời gọi bên ngoài **có thể đã thành công**. Dùng idempotency key của nghiệp vụ và, nếu cập nhật DB cần phát event, cân nhắc **Transactional Outbox**. Không coi **JobRepository** là một transaction coordinator phân tán.

## 8. Restart khác rerun, retry và reprocess

| Hành động | Diễn giải | Ràng buộc |
| --- | --- | --- |
| **Restart** | Chạy lại **cùng JobInstance** sau lỗi/dừng, thường với **JobExecution mới** | Identifying JobParameters không đổi, Job restartable, trạng thái hợp lệ và state có thể khôi phục |
| **Rerun as new instance** | Tạo JobInstance mới cho lô khác hoặc quyết định chạy lại nghiệp vụ | Identifying parameters khác; cần kiểm soát dữ liệu trùng |
| **Retry trong Step** | Thử lại item/chunk khi gặp lỗi tạm thời | Chính sách fault-tolerant, retry limit và transaction semantics |
| **Reprocess nghiệp vụ** | Chủ động đọc lại dữ liệu để sửa hoặc đối soát | Dùng workflow và quy tắc cập nhật domain; không chỉ sửa BATCH_* |

Một **JobInstance đã COMPLETED** thường không được chạy lại với cùng identifying parameters. Nếu thực sự cần **xử lý lại một lô đã hoàn tất**, hãy coi đây là tác vụ nghiệp vụ có kiểm soát: version lô, ghi lý do reprocess, bảo vệ dữ liệu cũ, xác định bản ghi nào được cập nhật. Không xóa metadata hoặc sửa status thành FAILED để ép Batch chạy lại.

Tương tự, **RunIdIncrementer** hữu ích khi muốn tạo JobInstance mới cho mỗi lượt chạy, nhưng nguy hiểm nếu gắn nó vào thao tác “thử lại cùng file”. Lúc đó Batch không còn biết đây là restart cùng JobInstance; idempotency nghiệp vụ vẫn phải chịu trách nhiệm về dữ liệu.

## 9. Dữ liệu trung gian, reject và audit đặt ở đâu?

Một pipeline nhập liệu thực tế có thể cần lưu nhiều loại dữ liệu ngoài bảng hóa đơn chính:

| Nhu cầu | Nên lưu ở đâu | Vì sao |
| --- | --- | --- |
| Hóa đơn hợp lệ | **business_invoice** | Domain source of truth |
| Dữ liệu chưa chuẩn hóa chờ kiểm tra | **invoice_staging** hoặc object storage | Có contract, retention và khả năng replay |
| Dòng sai định dạng hoặc bị từ chối | **invoice_reject** với sourceBatchId/lineNumber/reasonCode | Phục vụ sửa dữ liệu và đối soát |
| Trạng thái duyệt lô | **invoice_import_run** | Workflow nghiệp vụ, có thể độc lập trạng thái Job |
| Vị trí reader/file checkpoint | **Step ExecutionContext** | Hỗ trợ restart kỹ thuật |
| Tổng số read/write/skip và lỗi Step | **BATCH_STEP_EXECUTION** | Giám sát thực thi |
| Dấu vết tác vụ gọi hệ thống ngoài | Business audit/outbox/integration log phù hợp | Theo dõi side effect và hợp đồng tích hợp |

**ExecutionContext không nên lưu payload của mọi dòng bị từ chối.** Có thể lưu một checkpoint nhỏ như lastProcessedLine và tham chiếu sang bảng reject. Để báo cáo lỗi cho đối tác, hệ thống cần số dòng, định danh nguồn, mã lỗi và trạng thái phê duyệt; các dữ liệu này là một phần nghiệp vụ, không phải số liệu readSkipCount chung chung.

Một Job có thể xử lý 1.000 dòng, skip 20 dòng và COMPLETED vì skipLimit cho phép. Nhưng đối với nghiệp vụ, lô đó có thể là **PARTIAL_ACCEPTED** hoặc **WAITING_REVIEW**. Kết quả sản phẩm phải dựa trên dữ liệu kiểm tra và quy tắc nghiệp vụ, không dựa riêng vào BatchStatus.

## 10. JobParameters và ExecutionContext không thay thế domain identity

Có ba nhóm khóa cần giữ tách biệt:

1. **Khóa nhận diện JobInstance:** jobName + identifying JobParameters, để Batch biết restart hay instance mới.
2. **Khóa checkpoint:** dữ liệu trong ExecutionContext để reader/processor khôi phục tiến độ kỹ thuật.
3. **Khóa chống trùng nghiệp vụ:** ví dụ **(source_system, source_invoice_id)**, để một hóa đơn không bị tạo nhiều lần dù đi qua nhiều batch.

Ví dụ một invoice đã tồn tại:

~~~text
Đối tác A gửi hóa đơn INV-001
    |
    +-- JobInstance sourceBatchId=2026-11-21 --> ghi business_invoice
    |
    +-- JobInstance sourceBatchId=2026-11-22 --> vẫn gặp INV-001
                                              |
                                              +-- Unique key quyết định trùng
~~~

Hai JobInstance hợp lệ có thể cùng gặp một business key. JobRepository không tự phát hiện đây là một invoice trùng. Ngược lại, một JobInstance có thể đọc nhiều invoice; không được dùng JobExecutionId làm business invoiceId.

Đặc biệt với **API phân trang** hoặc **database paging reader**, checkpoint theo **số trang/số bản ghi** có thể không ổn định nếu nguồn thay đổi trong lúc Job chạy. Nên ưu tiên snapshot, thứ tự có khóa ổn định, watermark hoặc keyset pagination khi hợp đồng nguồn cho phép; và kiểm thử restart khi dữ liệu nguồn có insert/update mới.

## 11. Chọn bố trí database và transaction manager

Có ba cách bố trí phổ biến:

| Bố trí | Ưu điểm | Giới hạn cần thiết kế |
| --- | --- | --- |
| **Cùng DB, cùng transaction manager** cho metadata và business writer | Thuận tiện phối hợp commit chunk và checkpoint, ít cấu hình | Phân quyền/schema và contention cần kiểm soát; không bảo vệ side effect ngoài DB |
| **Cùng RDBMS nhưng DB/schema/kết nối tách biệt** | Phân vùng vận hành và quyền truy cập | Không mặc định cùng một transaction; phải xác minh cấu hình datasource/manager |
| **Metadata DB riêng, business DB riêng** | Cô lập quản trị, có thể chia sẻ JobRepository có kiểm soát | Cần chống trùng và reconciliation khi một phía commit còn phía kia lỗi |

Với **JobRepository** dùng JDBC, Batch cần transaction management để cập nhật metadata. **Step** cũng cần **PlatformTransactionManager** cho chunk. Nếu hai thành phần dùng manager khác nhau, đừng suy luận rằng mọi thao tác được rollback cùng lúc chỉ vì có annotation **@Transactional** trong service.

Điểm khác biệt khi dùng **Spring Batch với message broker**: metadata có thể lưu JobExecution/StepExecution trong DB, nhưng việc **ack một message RabbitMQ** hoặc **publish Kafka event** không tự tham gia giao dịch đó. Các adapter cần chính sách ack, retry, idempotency và xử lý kết quả không chắc chắn riêng. Cũng cần chú ý nếu ItemReader gọi HTTP và service nguồn không hỗ trợ replay: checkpoint không thể khôi phục một phản hồi đã biến mất.

## 12. Vận hành metadata đúng cách

### 12.1. API quan sát và điều khiển

| API Spring Batch | Mục đích |
| --- | --- |
| **JobLauncher** | Khởi chạy Job với JobParameters |
| **JobRepository** | Tạo và cập nhật JobInstance, JobExecution, StepExecution, ExecutionContext |
| **JobExplorer** | Tra cứu metadata Job/Step theo API đọc |
| **JobOperator** | Thao tác điều khiển như start/stop/restart theo API và cấu hình hỗ trợ |

Không chỉnh sửa thủ công các trường như **STATUS**, **VERSION**, **READ_COUNT** hoặc nội dung serialized của ExecutionContext để “sửa” Job đang lỗi. Các trường này có ràng buộc tương quan; một thay đổi thủ công có thể gây lỗi optimistic locking hoặc khiến Batch restart từ checkpoint sai.

### 12.2. Retention và nâng cấp

Metadata cần được giữ ít nhất trong khoảng thời gian còn muốn **restart**, điều tra lỗi hoặc audit kỹ thuật. Xóa execution history quá sớm có thể làm mất thông tin restart và truy nguyên sự cố. Ngược lại, giữ không giới hạn có thể khiến bảng **BATCH_*** phình lớn, ảnh hưởng query/backup.

Quy trình retention nên cân nhắc: Job đang chạy, Job FAILED còn cần restart, Job COMPLETED lâu ngày, khóa ngoại giữa các bảng, yêu cầu audit, backup/restore và sự phụ thuộc của dashboard. Tác vụ cleanup phải có quy tắc và thực hiện qua cơ chế phù hợp, không xóa bừa BATCH_JOB_INSTANCE trước các execution phụ thuộc.

Khi nâng cấp Spring Batch, nên kiểm tra cả **schema migration** và **khả năng deserialize ExecutionContext cũ**. Không tự đổi tên bảng, đổi kiểu cột hoặc thay serializer mà không đánh giá ảnh hưởng đến restart của các execution chưa hoàn thành.

### 12.3. An toàn dữ liệu và quyền truy cập

**JobParameters** và **ExecutionContext** có thể được lưu trong metadata database. Vì vậy:

- Không đặt password, API key, access token hoặc thông tin nhạy cảm trong JobParameters.
- Dùng đường dẫn tham chiếu/secret reference an toàn thay vì nhét credential vào metadata.
- Không log toàn bộ business payload, exception có PII hay bản sao nguyên file vào ExecutionContext.
- Giới hạn quyền đọc/ghi metadata cho account vận hành phù hợp, tách quyền báo cáo dữ liệu nghiệp vụ khi cần.

## 13. Kiểm thử phân biệt metadata và business data

Kiểm thử cần nhìn cả **BATCH_*** và các bảng nghiệp vụ để tránh kết luận sai từ trạng thái COMPLETED.

| Kịch bản | Điều cần xác nhận |
| --- | --- |
| Job import file hợp lệ | business_invoice đúng số hóa đơn; JobExecution và StepExecution kết thúc phù hợp |
| Processor lọc item theo quy tắc | filterCount tăng; dữ liệu nghiệp vụ khớp quy tắc lọc |
| Một dòng sai, cấu hình skip | read/skip/write count đúng; có bản ghi reject nghiệp vụ nếu hợp đồng yêu cầu |
| Lỗi ở chunk thứ ba | Hai chunk đầu giữ dữ liệu đã commit, chunk lỗi rollback khi cùng transaction; metadata báo FAILED |
| Restart cùng identifying parameters | JobInstance không đổi, JobExecution mới; dữ liệu không nhân đôi |
| Launch cùng params khi Job đã COMPLETED | Batch từ chối chạy lại cùng JobInstance theo quy tắc restart |
| Tạo JobInstance mới với file chứa invoice cũ | Unique key/upsert nghiệp vụ ngăn bản ghi trùng |
| Đổi file sau khi Step FAILED | Bị chặn bằng checksum/snapshot policy hoặc được nhận diện là reprocess |
| Metadata và business DB tách rời, giả lập crash | Có retry/reconciliation, không bỏ sót hoặc tạo tác động lặp |
| Nâng cấp version ứng dụng giữa hai execution | ExecutionContext cũ vẫn được đọc hoặc có quy trình phục hồi thay thế |

Đối với Spring Boot, **Spring Batch Test** hỗ trợ kiểm thử Job/Step và tra cứu StepExecution; **Testcontainers** có thể cung cấp PostgreSQL hoặc broker thật để kiểm thử ranh giới transaction. Khi dùng PostgreSQL **ON CONFLICT**, không nên kiểm thử writer chỉ trên một database in-memory có SQL dialect khác rồi suy ra behavior production.

### Ví dụ tiêu chí chấp nhận có thể đo được

Với file có 250 hóa đơn hợp lệ và chunk size 100:

1. Sau hai chunk thành công, giả lập lỗi trong chunk thứ ba. Khi giao dịch chung hoạt động đúng, dữ liệu đã commit của hai chunk đầu vẫn tồn tại.
2. JobExecution đầu ghi FAILED; các bước và checkpoint có thể truy vấn từ JobRepository.
3. Restart **cùng** identifying JobParameters bằng input bất biến. Spring Batch tạo JobExecution mới cho JobInstance trước đó, reader tiếp tục theo checkpoint.
4. Sau khi hoàn tất, **business_invoice chứa đúng 250 hóa đơn duy nhất**, còn JobExecution mới COMPLETED; số hàng mới trong business table được xác nhận bằng query domain, không suy luận từ writeCount.
5. Thử chạy một JobInstance **mới** với hóa đơn INV-001 đã tồn tại: unique key hoặc policy reconciliation phải xử lý đúng, không tạo hóa đơn thứ hai.

## 14. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Job COMPLETED nghĩa là tất cả hóa đơn đã được duyệt.” | COMPLETED là kết quả **thực thi Step**; phê duyệt là trạng thái nghiệp vụ khác. |
| “writeCount=500 nghĩa là DB vừa thêm 500 hàng.” | writeCount đo số item được gửi tới writer, không nhất thiết bằng số insert mới hoặc side effect thành công. |
| “ExecutionContext là nơi lưu các hóa đơn đang chờ xử lý.” | ExecutionContext lưu state/checkpoint nhỏ; lưu hóa đơn ở staging/business tables. |
| “Đổi run.id để restart Job lỗi.” | Đổi identifying parameter tạo JobInstance mới; restart phải giữ identity cũ. |
| “Batch có checkpoint nên không bao giờ ghi trùng.” | Retry/restart có thể xử lý lại; unique key/idempotent writer là trách nhiệm nghiệp vụ. |
| “@Transactional bao luôn HTTP và RabbitMQ.” | Transaction chỉ bao các tài nguyên được transaction manager quản lý; side effect ngoài DB cần cơ chế riêng. |
| “Xóa hàng BATCH_ để chạy lại cho sạch.” | Có thể mất trạng thái restart/audit và làm hỏng quan hệ metadata. |
| “JobRepository đã có sẵn nên không cần import_run bảng nghiệp vụ.” | Nếu người dùng cần duyệt/đối soát/tracking lô theo business status, cần model nghiệp vụ riêng. |

## 15. Checklist trước khi đưa Job vào production

- [ ] Phân định rõ **business tables**, **metadata tables**, staging/reject/audit và người sở hữu từng loại dữ liệu.
- [ ] JobParameters có identifying key ổn định; định nghĩa rõ **restart** và **new instance/reprocess**.
- [ ] Reader có chiến lược checkpoint phù hợp; input snapshot bất biến hoặc có version/checksum.
- [ ] Writer có khóa nghiệp vụ, validation và idempotency; không dựa vào writeCount làm số liệu domain.
- [ ] Step transaction manager và JobRepository DataSource được cấu hình có chủ ý; hiểu ranh giới commit.
- [ ] Side effect HTTP/broker có cơ chế retry, idempotency hoặc outbox/inbox và reconciliation phù hợp.
- [ ] Các bản ghi sai được lưu ở domain reject/audit khi nghiệp vụ cần, không nhét vào ExecutionContext.
- [ ] Có metric và dashboard cả **tiến độ kỹ thuật** lẫn **kết quả nghiệp vụ**.
- [ ] Có kế hoạch backup, schema migration, retention và bảo mật bảng BATCH_*.
- [ ] Đã kiểm thử crash/restart, replay, duplicate, input thay đổi, skip/rollback và nâng cấp version.

**Nguyên tắc ghi nhớ:** **Spring Batch quản lý cách một Job thực thi và tiếp tục sau sự cố; ứng dụng quản lý ý nghĩa và tính đúng đắn của dữ liệu được Job xử lý.** Metadata của JobRepository rất quan trọng để restart và vận hành, nhưng **không thay thế domain model, khóa chống trùng, audit nghiệp vụ hay giao dịch xuyên nhiều hệ thống**.

### Tài liệu đọc thêm

- [Spring Batch Reference — Domain Language of Batch](https://docs.spring.io/spring-batch/reference/domain.html)
- [Spring Batch Reference — JobRepository](https://docs.spring.io/spring-batch/reference/job/configuring-repository.html)
- [Spring Batch Reference — Meta-Data Schema](https://docs.spring.io/spring-batch/reference/schema-appendix.html)
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html)
- [Spring Batch Reference — JobParameters](https://docs.spring.io/spring-batch/reference/job/running.html)
