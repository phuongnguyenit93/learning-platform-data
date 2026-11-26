# Test transaction rollback trong Spring Batch khi xử lý đồng thời

## 1. Vì sao test “job FAILED” chưa chứng minh dữ liệu đã rollback?

Giả sử một job xử lý 100.000 giao dịch bằng **remote partitioning**, mỗi worker ghi kết quả theo chunk 500 dòng. Worker A chèn 300 dòng rồi một item không hợp lệ làm `ItemWriter` ném exception. Spring Batch báo partition `FAILED`. Nhưng truy vấn database lại thấy 300 dòng “đã ghi”, trong khi worker B vẫn tiếp tục commit các chunk thuộc partition khác.

Điều này có thể **đúng hoặc là lỗi nghiêm trọng**, tùy phạm vi transaction:

- Nếu cả 300 câu `INSERT` thuộc **cùng transaction của chunk lỗi**, chúng phải bị rollback khi transaction đó thật sự rollback.
- Nếu chúng đã được commit bởi một transaction khác (chẳng hạn `REQUIRES_NEW`, datasource/transaction manager khác hoặc auto-commit), rollback transaction ngoài **không hoàn tác** chúng.
- Những chunk **đã commit trước đó** vẫn tồn tại. Một job thất bại **không có nghĩa mọi kết quả của toàn job được rollback**.
- Những worker/partition khác có transaction **độc lập**; một partition lỗi không tự rollback dữ liệu của partition khác.
- Nếu worker đã commit business DB rồi crash trước khi cập nhật metadata/reply, trạng thái `FAILED`/`STARTED` không đủ kết luận rằng business output không tồn tại.

Do đó, bài **“Test transaction rollback”** thuộc chương **Testing concurrency** của module `SPRING_BATCH_SCALING_OPERATIONS` không chỉ kiểm tra mã lỗi: bài thiết kế các phép kiểm tra thực tế để chứng minh **phần nào đã rollback, phần nào vẫn commit, có bị ghi trùng khi retry/restart hay không**, và liệu nhiều worker có phá bất biến nghiệp vụ hay không.

Mục tiêu của module là mở rộng Spring Batch cho workload lớn qua multi-threaded step, parallel steps, partitioning và các mô hình phân tán; học đo nút thắt, bảo đảm thread safety, retry/restart, vận hành job và lựa chọn kiến trúc theo tài nguyên thực tế.

Sau bài, bạn có thể:

1. Vẽ đúng ranh giới **chunk transaction**, `StepExecution`, `JobExecution` và các resource (business DB, `JobRepository`, broker, file/API).
2. Viết test một chunk lỗi giữa `write()` và `COMMIT`, đọc lại database bằng transaction độc lập để xác nhận rollback.
3. Kiểm tra nhiều chunk: chunk trước đã commit, chunk lỗi rollback, job `FAILED` không đồng nghĩa toàn job atomic.
4. Tách rollback do reader/processor/writer lỗi, commit failure, deadlock, `40001` và timeout.
5. Test `retry/skip/noRollback` theo fault-tolerant policy mà không làm sai business data.
6. Xử lý rollback khi hai thread, parallel steps hoặc remote workers cùng truy cập database.
7. Nhận diện side effect **không tham gia transaction**: HTTP, email, broker, file, `REQUIRES_NEW` và JPA flush.
8. Kiểm tra restart cùng `JobInstance`, checkpoint, idempotency, duplicate delivery và “unknown commit outcome”.
9. Tạo test có barrier/fault injection, deadline hữu hạn và runbook điều tra rollback failure.

**Phạm vi phiên bản:** ví dụ sử dụng Java 17+, Spring Batch 5.2.x, Spring Boot 3.x, JUnit 5, Spring JDBC, PostgreSQL và Testcontainers. Với Spring Batch 6.x/Spring Boot 4.x, cần đối chiếu API và cách auto-configuration theo version cụ thể. Các đoạn minh họa rõ phần nào là **code độc lập**, phần nào cần project/test configuration đi kèm.

## 2. Chunk transaction: đơn vị rollback thường là một chunk

Với một chunk-oriented step:

~~~java
return new StepBuilder("paymentWorkerStep", jobRepository)
        .<PaymentInput, PaymentOutput>chunk(250, businessTransactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
~~~

Đây là **đoạn wiring minh họa**, giả định các bean `jobRepository`, `businessTransactionManager`, `reader`, `processor`, `writer` và DTOs có sẵn. Với Spring Batch 5.x, `chunk(250, transactionManager)` xác định transaction manager cho chunk step.

Trong cấu hình đơn giản với một JDBC datasource và transaction manager đúng, flow thường là:

~~~mermaid
sequenceDiagram
    participant S as Spring Batch Step
    participant R as ItemReader
    participant P as ItemProcessor
    participant W as ItemWriter
    participant D as Business DB
    S->>D: BEGIN chunk transaction
    loop Tối đa 250 items/chunk
        S->>R: read()
        R-->>S: item
        S->>P: process(item)
        P-->>S: output
    end
    S->>W: write(Chunk<Output>)
    W->>D: INSERT/UPDATE trong transaction
    D-->>W: SQL execution returned
    S->>D: COMMIT
    D-->>S: Commit acknowledged
    Note over S,D: Chunk thành công; chunk trước đã durable theo DB policy
~~~

Nếu một exception khiến **transaction manager quyết định rollback**, toàn bộ SQL thuộc **đúng physical transaction đó** phải bị hoàn tác. Các transaction khác và side effects ngoài transaction không được hoàn tác tự động.

### 2.1. Ba phạm vi không nên lẫn

| Phạm vi | Đơn vị | Khi một chunk lỗi |
|---|---|---|
| **Chunk transaction** | Một nhóm item trong một worker step | Những thay đổi **tham gia cùng transaction** bị rollback |
| **StepExecution** | Một lần chạy step/partition | Có thể chuyển `FAILED` dù các chunk trước đã commit |
| **JobExecution** | Một lần chạy toàn job | Có thể `FAILED` trong khi nhiều step/partition khác đã commit |

**Spring Batch không cung cấp một transaction bao phủ toàn job kéo dài hàng giờ** chỉ vì mọi step thuộc cùng `JobExecution`. Cố giữ transaction toàn job sẽ gây lock/undo/connection cost lớn và không giải quyết commit của broker/API/file tách biệt.

### 2.2. Ví dụ chunk size 3

Input `[1,2,3,4,5,6,7]`, `chunk(3)`:

| Chunk | Items | Kết quả SQL | Trạng thái kỳ vọng |
|---|---|---|---|
| 1 | 1, 2, 3 | COMMIT | Ba row tồn tại |
| 2 | 4, 5, 6 | Writer xử lý một phần rồi throw trước COMMIT | Toàn bộ DB writes **trong transaction này** bị rollback |
| 3 | 7 | Chưa bắt đầu trong step fail-fast | Không có row |

Sau job `FAILED`, output hợp lệ **có thể chứa 1,2,3**. Nếu test assert output phải rỗng vì job fail, test đó hiểu sai transaction boundary. Ngược lại, nếu thấy 4/5/6 đã commit dù chúng dùng cùng business transaction, cần kiểm tra auto-commit, transaction propagation, datasource wiring và điểm inject lỗi.

## 3. Định nghĩa test oracle: muốn chứng minh rollback phải đo gì?

Một rollback test tốt cần **ba nhóm điều kiện**, không phải chỉ một exception:

### 3.1. Metadata oracle

- `JobExecution.getStatus()` phản ánh `FAILED`/`COMPLETED`/`STOPPED` theo policy và điểm lỗi.
- Worker `StepExecution.getRollbackCount()` có phản ánh rollback được framework xử lý hay không; **số đếm này phụ thuộc cơ chế fault-tolerance/transaction**, không luôn chính xác bằng số business rollbacks ở mọi external resource.
- `readCount`, `writeCount`, `commitCount`, `filterCount`, `skipCount` có giá trị phù hợp với chunk lifecycle.
- `ExecutionContext` checkpoint không vượt qua các item cần xử lý lại khi restart.
- Với remote partitions, manager tổng hợp đúng worker execution states, không coi reply/ACK là bằng chứng commit.

### 3.2. Business-data oracle

- Query từ **connection/transaction độc lập** sau step kết thúc xác nhận row của chunk lỗi **không được commit**.
- Chunk trước đó đã commit vẫn tồn tại.
- Các partition/transaction độc lập có thể hoàn tất, theo contract.
- Tập **business keys**, payload/checksum và aggregate cuối đúng sau restart; không chỉ tổng `writeCount`.
- Duplicate delivery/retry không làm tác động nghiệp vụ diễn ra hai lần.

### 3.3. Recovery oracle

- Lỗi được phân loại retryable hay permanent; retry có giới hạn, không treo.
- Nếu commit outcome chưa chắc chắn, ứng dụng dùng idempotency/reconciliation thay vì đoán.
- Restart sử dụng cùng identifying `JobParameters` và input snapshot/partition plan ổn định.
- Stale worker không tiếp tục tạo side effect khi work unit đã được giao lại trái contract.
- Không có pending job/partition bị bỏ quên vô hạn sau fault injection.

**Test pass** khi metadata, output và kết quả recovery nhất quán. Một test chạy xanh với `assertThat(jobExecution.getStatus()).isEqualTo(FAILED)` nhưng không đọc database **chưa kiểm chứng rollback**.

## 4. Nguồn dữ liệu thử nghiệm phải bất biến và cô lập

Sử dụng PostgreSQL thay vì chỉ H2 để kiểm tra transaction, unique key, lock waits và SQL semantics mà production dùng.

### 4.1. Schema test tối thiểu

~~~sql
CREATE TABLE source_payments (
    snapshot_key VARCHAR(80) NOT NULL,
    payment_id BIGINT NOT NULL,
    account_id BIGINT NOT NULL,
    amount_cents BIGINT NOT NULL,
    PRIMARY KEY (snapshot_key, payment_id)
);

CREATE TABLE posted_payments (
    snapshot_key VARCHAR(80) NOT NULL,
    payment_id BIGINT NOT NULL,
    account_id BIGINT NOT NULL,
    amount_cents BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (snapshot_key, payment_id)
);
~~~

Với 1.003 event cố định:

~~~sql
INSERT INTO source_payments
    (snapshot_key, payment_id, account_id, amount_cents)
SELECT
    'rollback-snap-001',
    n,
    MOD(n, 17),
    n * 10
FROM generate_series(1, 1003) AS g(n);
~~~

Nếu output là identity transform, expected là **1.003 unique keys** và tổng tiền `5.035.060` đơn vị cents. Đây là dữ liệu **staging/test**, không phải business production.

### 4.2. Xác minh theo tập khóa, không chỉ COUNT(*)

~~~sql
-- Input có nhưng output thiếu:
SELECT payment_id, account_id, amount_cents
FROM source_payments
WHERE snapshot_key = 'rollback-snap-001'
EXCEPT
SELECT payment_id, account_id, amount_cents
FROM posted_payments
WHERE snapshot_key = 'rollback-snap-001';
~~~

~~~sql
-- Output sai hoặc dư:
SELECT payment_id, account_id, amount_cents
FROM posted_payments
WHERE snapshot_key = 'rollback-snap-001'
EXCEPT
SELECT payment_id, account_id, amount_cents
FROM source_payments
WHERE snapshot_key = 'rollback-snap-001';
~~~

Hai tập phải rỗng sau một run/restart thành công của **identity pipeline**. `EXCEPT` dùng semantics tập hợp; nếu output không có unique constraint, cần kiểm tra multiplicity/deduplication riêng. Với job có filter/transform, expected phải là **tập đã biến đổi theo quy tắc nghiệp vụ**.

### 4.3. Cleanup đúng phạm vi

- Test có database/schema riêng hoặc snapshot namespace riêng.
- Seed fixture và COMMIT **trước khi manager/worker đọc**, tránh test `@Transactional` giữ input chưa commit mà worker process khác không nhìn thấy.
- Dọn `posted_payments` theo snapshot trong test DB; không `TRUNCATE` shared DB của suite/worker khác.
- Spring Batch metadata schema `BATCH_*` phải phù hợp với **đúng Spring Batch version**; không dựng metadata table rút gọn rồi tin kết quả restart tương đương repository chuẩn.
- Một test restart cần giữ metadata của chính `JobInstance` qua hai executions; đừng cleanup repository giữa lần fail và lần restart.

## 5. Phân loại điểm lỗi và expected rollback

| Điểm inject | Có thể xảy ra gì? | Test phải xác minh |
|---|---|---|
| `ItemReader.read()` lỗi | Chunk không hoàn tất, writer có thể chưa được gọi | Transaction/reader checkpoint, state và retry policy |
| `ItemProcessor.process()` lỗi | Chunk đang xử lý dở | Không commit output của chunk lỗi trừ skip policy được thiết kế |
| `ItemWriter.write()` lỗi **sau SQL** | Một số câu SQL đã execute trong transaction | Toàn bộ SQL cùng transaction rollback |
| `EntityManager.flush()` rồi throw | Hibernate gửi SQL nhưng chưa commit | Row không visible/committed sau rollback |
| JDBC `executeBatch()` lỗi | Một phần statements có thể execute trước khi exception | Rollback physical transaction; không tin update counts |
| JDBC `COMMIT` lỗi/mất kết nối | Client có thể **không biết** đã commit hay chưa | Reconcile business keys; replay idempotent |
| Deadlock `40P01` | PostgreSQL aborts transaction/victim | Rollback, bounded retry **toàn transaction** |
| Serialization failure `40001` | Transaction không thể commit theo isolation | Retry toàn transaction theo policy |
| Unique violation `23505` | Transaction statement lỗi nếu không xử lý | Business duplicate hay poison data? Không retry mù |
| External HTTP/email xảy ra trước rollback | Side effect có thể đã diễn ra | Outbox/idempotency hoặc compensation; DB rollback không undo API |
| Broker ACK trước business COMMIT | Message có thể bị coi đã xử lý khi DB lỗi | ACK/transaction/replay policy đúng |
| Metadata DB khác business DB | Có hai commit boundaries | Không giả định atomicity giữa JobRepository và output |

**Điểm cốt lõi:** một exception **không tự động chứng minh** mọi thay đổi đã rollback. Muốn chắc chắn, phải biết transaction manager nào áp dụng lên connection/resource nào, trạng thái commit thực tế và invariant nghiệp vụ nào phải giữ.

## 6. Integration test thật: writer ghi SQL rồi throw trước COMMIT

Mục tiêu test:

1. Spring Batch thực sự mở transaction cho chunk.
2. `JdbcTemplate` và chunk transaction sử dụng **cùng datasource/transaction manager**.
3. `ItemWriter` đã gửi `INSERT` thành công rồi ném exception.
4. Job/step thất bại và **database không chứa row từ chunk lỗi**.

Không dùng mock database cho oracle số 4. Có thể dùng **Testcontainers PostgreSQL** và Spring Boot Test để có transaction behavior sát môi trường production.

### 6.1. Phụ thuộc tối thiểu cho test

Một ứng dụng Gradle/Maven cần các thành phần tương ứng:

~~~text
runtime:
  spring-boot-starter-batch
  spring-boot-starter-jdbc
  postgresql JDBC driver

test:
  spring-boot-starter-test (JUnit 5 + AssertJ)
  spring-batch-test
  testcontainers-junit-jupiter
  testcontainers-postgresql
~~~

Danh sách mô tả **vai trò dependencies**, không áp đặt cùng tên artifact/group/version cho mọi Spring Boot/Testcontainers release. Chọn BOM và dependency coordinates theo phiên bản dự án; môi trường test cần Docker/compatible container runtime.

### 6.2. Một test class tự chứa, chỉ chạy một job

Ví dụ sau dùng **một PostgreSQL datasource** cho cả Spring Batch metadata và bảng business test `tx_probe`. Nhờ đó `JdbcTemplate` tham gia cùng transaction manager do Spring Boot cấu hình cho chunk. Test deliberately **không** đánh dấu method `@Transactional`.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.support.ListItemReader;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@Testcontainers
@SpringBootTest(
        classes = ChunkRollbackIT.TestApplication.class,
        properties = {
            "spring.batch.job.enabled=false",
            "spring.batch.jdbc.initialize-schema=always"
        })
class ChunkRollbackIT {

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine")
                    .withDatabaseName("rollback_test")
                    .withUsername("test")
                    .withPassword("test");

    @DynamicPropertySource
    static void dataSourceProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {

        @Bean
        Job rollbackJob(JobRepository repository, Step failingStep) {
            return new JobBuilder("rollbackJob", repository)
                    .start(failingStep)
                    .build();
        }

        @Bean
        Step failingStep(
                JobRepository repository,
                PlatformTransactionManager transactionManager,
                JdbcTemplate jdbc) {

            // Một test job một lần: reader không cần restart/checkpoint.
            ListItemReader<Long> reader =
                    new ListItemReader<>(List.of(1L, 2L, 3L));

            ItemWriter<Long> failingWriter = chunk -> {
                for (Long id : chunk) {
                    // Cùng JDBC datasource và transaction của chunk.
                    jdbc.update(
                            "INSERT INTO tx_probe(payment_id) VALUES (?)",
                            id);
                }
                // Đã execute SQL; transaction CHƯA COMMIT.
                throw new IllegalStateException(
                        "Injected failure after SQL, before commit");
            };

            return new StepBuilder("failingStep", repository)
                    .<Long, Long>chunk(3, transactionManager)
                    .reader(reader)
                    .writer(failingWriter)
                    .build();
        }
    }

    @Autowired JobLauncher jobLauncher;
    @Autowired Job rollbackJob;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void createBusinessFixture() {
        jdbc.execute("""
            CREATE TABLE IF NOT EXISTS tx_probe (
                payment_id BIGINT PRIMARY KEY
            )
            """);
        jdbc.update("DELETE FROM tx_probe");
    }

    @Test
    void failedChunkRollsBackAllItsBusinessRows() throws Exception {
        JobExecution execution = jobLauncher.run(
                rollbackJob,
                new JobParametersBuilder()
                        .addString("testRun", UUID.randomUUID().toString())
                        .toJobParameters());

        assertThat(execution.getStatus())
                .isEqualTo(BatchStatus.FAILED);
        assertThat(execution.getStepExecutions())
                .singleElement()
                .satisfies(step ->
                        assertThat(step.getRollbackCount())
                                .isGreaterThan(0));

        // Query từ test method sau khi job đã kết thúc,
        // không nằm trong chunk transaction đã rollback.
        Long rows = jdbc.queryForObject(
                "SELECT count(*) FROM tx_probe", Long.class);
        assertThat(rows).isZero();
    }
}
~~~

**Điều kiện để chạy:** Spring Boot Batch auto-configuration phải thực sự cung cấp `JobRepository`, `JobLauncher` và `PlatformTransactionManager` cho datasource test; database metadata được khởi tạo từ Spring Batch schema theo version. Nếu ứng dụng có nhiều transaction managers, phải chọn **đúng business transaction manager** bằng qualifier và xác minh datasource wiring. Đây là một **integration test một lần**, không phải mẫu dùng `ListItemReader` singleton để chạy lại cùng bean nhiều lần: `ListItemReader` giữ cursor trong memory, không cung cấp checkpoint/restart như JDBC `ItemStreamReader`.

**Tại sao test không có `@Transactional`?** Nếu JUnit test method tự mở transaction rồi rollback khi kết thúc, một lỗi cấu hình có thể bị che: query thấy 0 row chỉ vì **test transaction rollback** chứ không phải chunk rollback. Ngoài ra, metadata/worker threads thường dùng transaction riêng và có thể không thấy fixture chưa commit trong test method.

### 6.3. Những assertion không nên có

Tránh:

~~~java
// Sai ý nghĩa: writer đã được gọi nên không thể kết luận commit.
assertThat(writerInvocationCount).isEqualTo(1);
// Sai ý nghĩa: Job FAILED không tự chứng minh output rỗng.
assertThat(execution.getStatus()).isEqualTo(BatchStatus.FAILED);
// Không đọc DB thì chưa test rollback.
~~~

Kết quả đúng cần **cả step failure lẫn business table rỗng** đối với chunk đã cố tình lỗi, với DB fixture và transaction boundary được xác minh.

## 7. Test chunk trước đã COMMIT, chunk sau rollback

Đây là test khác với phần 6. Với `chunk(3)` và input `[1,2,3,4,5,6,7]`, mục tiêu là:

- Chunk đầu chứa `1,2,3` commit thành công.
- Writer chunk tiếp theo chèn `4,5,6` rồi **throw trước commit**.
- Output cuối chứa **chính xác `1,2,3`**, không chứa `4,5,6,7`.

Một writer minh họa cho test:

~~~java
ItemWriter<Long> failOnSecondChunk = chunk -> {
    for (Long id : chunk) {
        jdbc.update(
                "INSERT INTO tx_probe(payment_id) VALUES (?)",
                id);
    }
    if (chunk.getItems().contains(5L)) {
        throw new IllegalStateException(
                "Inject failure into second chunk");
    }
};
~~~

Đặt writer này trong **một Step khác** với reader mới chứa `1..7` và `chunk(3, businessTransactionManager)`. Test theo flow:

~~~text
Given:
    tx_probe empty
    input = 1..7
When:
    launch job with a distinct identifying testRun
Then:
    JobExecution.status == FAILED
    committed tx_probe.payment_id == {1, 2, 3}
    StepExecution has rollback evidence
    no output key 4, 5, 6 or 7
~~~

Không tái sử dụng `ListItemReader` đã bị tiêu thụ từ test khác; mỗi testcase nên có **reader instance fresh**, test context riêng hoặc `@StepScope` với reader/checkpoint phù hợp. Test này chứng minh **chunk là transaction boundary**, không phải toàn job.

### 7.1. Mở rộng sang chunk commit và metadata

So song song:

~~~sql
SELECT payment_id
FROM tx_probe
ORDER BY payment_id;
~~~

với `StepExecution.getCommitCount()` và `getRollbackCount()`. Các count được Spring Batch quản lý cho cả lifecycle của step, có thể bao gồm những transaction khác kỳ vọng trực giác “1 chunk = đúng 1 transaction”; **không bắt cứng mọi test rằng commitCount=1** khi chưa hiểu version/listener/retry/reader operations. Trọng tâm là **ràng buộc business rows** và evidence rollback có ý nghĩa.

### 7.2. Khi transaction manager bị chọn sai

Một bug điển hình:

~~~text
Step.chunk(..., batchMetadataTransactionManager)
Writer JdbcTemplate dùng businessDataSource
businessDataSource vẫn autoCommit=true
Writer INSERT 4,5,6
Writer throw, metadata transaction rollback
Business rows 4,5,6 vẫn tồn tại
~~~

Đây là **kiểu lỗi cần test phát hiện**, không phải mô hình cấu hình được khuyến nghị. Với hai datasource, cần test transaction manager đúng resource; nếu muốn metadata/business commit cùng nguyên tử, cần topology transaction có thể thực sự cung cấp thuộc tính đó, không chỉ đặt chung một annotation `@Transactional`.

## 8. Phân biệt JDBC execute, JPA flush, COMMIT và rollback

Nhiều bài kiểm thử bị sai vì nhầm **SQL đã được gửi** với **transaction đã commit**.

### 8.1. JDBC batch: executeBatch có thể thành công trước commit

~~~java
ItemWriter<Payment> writer = chunk -> {
    for (Payment p : chunk) {
        jdbcTemplate.update("""
            INSERT INTO posted_payments
                (snapshot_key, payment_id, account_id, amount_cents)
            VALUES (?, ?, ?, ?)
            """,
            p.snapshotKey(), p.paymentId(),
            p.accountId(), p.amountCents());
    }
    throw new IllegalStateException("Fail before chunk commit");
};
~~~

Nếu tất cả JDBC operations dùng **cùng transaction-bound connection** trong chunk, cuối cùng không có rows của chunk lỗi. Nếu writer dùng một connection khác có auto-commit hoặc gọi API bên ngoài, kết quả có thể khác.

JDBC `BatchUpdateException#getUpdateCounts` mô tả execution results của statements, **không xác nhận transaction đã commit**. Driver có thể báo một số statements thành công trước khi lỗi; test phải rollback và đọc output ở **transaction độc lập**.

### 8.2. JPA/Hibernate: flush không phải commit

~~~java
@PersistenceContext
private EntityManager entityManager;

public void writeAndFail(List<PaymentEntity> payments) {
    for (PaymentEntity p : payments) {
        entityManager.persist(p);
    }
    entityManager.flush(); // SQL có thể đã được thực thi.
    throw new IllegalStateException("Failure after flush");
}
~~~

Nếu EntityManager tham gia **cùng chunk transaction**, rollback phải hoàn tác những DB changes chưa commit. Nhưng:

- `EntityManager.flush()` không tự là `COMMIT`.
- `saveAndFlush` không mặc định làm transaction durable.
- Persistence context cần được clear/reset phù hợp sau rollback nếu còn dùng lại.
- Database sequences/auto-increment values, external triggers và side effects khác có thể **không rollback theo cách đơn giản**.
- Không dùng EntityManager chưa bind đúng transaction để test “rollback”.

Với Hibernate batch SQL, kiểm tra cả `flush/clear`, memory và checkpoint; không dùng việc SQL log in ra làm bằng chứng row đã commit.

### 8.3. Callback trước commit và sau commit

| Điểm quan sát | Kết luận có thể rút | Không được kết luận |
|---|---|---|
| `ItemWriteListener.afterWrite` | Writer trả về bình thường theo callback lifecycle | Chunk transaction đã COMMIT |
| SQL `executeBatch` returned | DB/driver đã xử lý statement theo kết quả API | Transaction đã durable |
| `EntityManager.flush` | Persistence context đã đồng bộ SQL theo JPA | COMMIT thành công |
| `ChunkListener.afterChunk` | Chunk lifecycle báo thành công sau xử lý | Resource ngoài DB đều exactly-once |
| Transaction synchronization `afterCommit` | Commit thuộc **transaction được hook** đã thành công | Chắc chắn callback được scrape/log sau process crash |
| `StepExecution.COMPLETED` | Metadata step đã được ghi nhận thành công | External API/broker/file side effects nguyên tử cùng DB |

Không dùng metric timer trên `ItemWriter.write` làm **committed write latency**. Cần đo transaction/commit ở tầng phù hợp và business output ở database.

## 9. Spring Batch fault tolerance: retry và skip thay đổi kỳ vọng rollback

Khi Step có `.faultTolerant()`, mục tiêu của nhiều lỗi là **retry hoặc skip** để job vẫn hoàn tất theo policy, không còn “hễ exception là job FAILED”.

~~~java
return new StepBuilder("faultTolerantWorkerStep", jobRepository)
        .<PaymentInput, PaymentOutput>chunk(200, businessTxManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidPaymentException.class)
        .skipLimit(10)
        .build();
~~~

Đây là **wiring minh họa**, có class `InvalidPaymentException` do ứng dụng định nghĩa và các beans đã cấu hình. `TransientDataAccessException` là kiểu Spring được dùng cho một số lỗi database, nhưng **không nên retry tất cả trường hợp chỉ vì chúng thuộc một class chung**; phân loại theo SQLState/business semantics và thiết kế idempotency.

### 9.1. Retry có thể rollback rồi thử lại cùng chunk

Giả sử chunk chứa 100 items:

~~~text
Attempt 1:
  writer executes 100 SQL operations
  deadlock/serialization failure
  transaction rollback

Attempt 2:
  processor/writer được gọi lại theo fault-tolerant lifecycle
  transaction COMMIT

Business DB:
  expected 100 unique business outcomes, không phải 200

Telemetry:
  attempted writer items có thể > 100
  StepExecution writeCount có thể phản ánh committed contributions
~~~

**Thứ tự retry và những items nào được đọc/process lại phụ thuộc reader buffering/transactional reader và cấu hình fault-tolerance.** Test không nên bắt cứng số lần gọi `process()` mà không xác nhận policy của phiên bản/case cụ thể.

### 9.2. Skip trong writer phức tạp hơn skip ở processor

Khi một chunk writer gặp một item không hợp lệ, framework có thể phải **rollback, replay/scan** để xác định item gây lỗi, rồi skip theo policy. Lúc này writer có thể được gọi nhiều lần với các nhóm items khác nhau. Một writer có **side effects không nằm trong transaction** rất nguy hiểm vì các lần gọi replay có thể gửi email/API hoặc cộng tiền nhiều lần.

Test phải kiểm:

- Item lỗi không xuất hiện trong output nếu policy quy định skip.
- Items hợp lệ vẫn được commit **một lần về mặt nghiệp vụ**.
- `writeSkipCount`/`processSkipCount` tăng theo expected policy.
- Không vượt `skipLimit` mà job vẫn `COMPLETED`.
- Kết quả đúng khi exception xảy ra **sau một số SQL statements đã thực thi**.
- Idempotency guard hoạt động khi writer được phát lại cùng item.

### 9.3. `noRollback(...)` không biến database error thành an toàn

Spring Batch có các cách cấu hình exception không gây rollback trong phạm vi được hỗ trợ. Nhưng:

- Không dùng `noRollback` cho một transaction database **đã bị PostgreSQL đánh dấu aborted** sau SQL error; mọi statement tiếp theo trong transaction có thể thất bại cho tới khi rollback.
- Không dùng `noRollback` chỉ để `writeCount` đẹp hơn hoặc tránh reprocessing khi writer đã tạo side effects ngoài transaction.
- Test phải chứng minh kết quả business/transaction phù hợp với exception classification thực tế.

**Policy retry/skip/noRollback là một phần contract cần test**, không phải tối ưu throughput có thể thay đổi mà không xét correctness.

## 10. Test hai transaction đồng thời: một rollback, một commit

Rollback của worker A **không tự hoàn tác** transaction đã commit của worker B. Đây là một invariant cốt lõi khi dùng parallel steps, multi-threaded steps hoặc remote partitioning.

### 10.1. Timeline cần tạo có chủ đích

~~~mermaid
sequenceDiagram
    participant T1 as Worker A / Tx A
    participant DB as PostgreSQL
    participant T2 as Worker B / Tx B
    T1->>DB: BEGIN; INSERT payment 101
    T2->>DB: BEGIN; INSERT payment 202
    Note over T1,T2: Barrier: cả hai đã execute INSERT nhưng chưa commit
    T1->>DB: THROW -> ROLLBACK
    T2->>DB: COMMIT
    Note over DB: Expected committed IDs = {202}
~~~

Đặt hai business keys **khác nhau** để cô lập test **transaction independence** trước; kiểm thử cùng hot key/lock contention ở phần tiếp theo.

### 10.2. JUnit 5 + TransactionTemplate + CountDownLatch

Đoạn dưới là **method bổ sung** cho test class có `JdbcTemplate jdbc`, bảng `tx_probe` và transaction manager trỏ đúng PostgreSQL ở phần 6. Test tạo hai threads, mỗi thread chạy **một transaction JDBC riêng**, không đặt `@Transactional` trên test method.

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

// Field bổ sung trong ChunkRollbackIT:
@Autowired PlatformTransactionManager transactionManager;

@Test
void oneTransactionRollsBackButOtherCommits() throws Exception {
    TransactionTemplate tx = new TransactionTemplate(transactionManager);
    CountDownLatch bothInserted = new CountDownLatch(2);
    CountDownLatch allowFinish = new CountDownLatch(1);
    ExecutorService pool = Executors.newFixedThreadPool(2);

    Callable<Void> failA = () -> {
        tx.executeWithoutResult(status -> {
            jdbc.update(
                    "INSERT INTO tx_probe(payment_id) VALUES (101)");
            bothInserted.countDown();
            awaitOrFail(allowFinish);
            throw new IllegalStateException("Injected rollback A");
        });
        return null;
    };
    Callable<Void> commitB = () -> {
        tx.executeWithoutResult(status -> {
            jdbc.update(
                    "INSERT INTO tx_probe(payment_id) VALUES (202)");
            bothInserted.countDown();
            awaitOrFail(allowFinish);
        });
        return null;
    };

    try {
        Future<Void> a = pool.submit(failA);
        Future<Void> b = pool.submit(commitB);
        assertThat(bothInserted.await(10, TimeUnit.SECONDS)).isTrue();

        // PostgreSQL READ COMMITTED: hai INSERT chưa commit
        // không visible với connection độc lập của test.
        Long visibleBefore = jdbc.queryForObject(
                "SELECT count(*) FROM tx_probe", Long.class);
        assertThat(visibleBefore).isZero();

        allowFinish.countDown();
        assertThatThrownBy(() -> a.get(15, TimeUnit.SECONDS))
                .isInstanceOf(ExecutionException.class)
                .hasCauseInstanceOf(IllegalStateException.class);
        b.get(15, TimeUnit.SECONDS);

        List<Long> committed = jdbc.queryForList(
                "SELECT payment_id FROM tx_probe ORDER BY payment_id",
                Long.class);
        assertThat(committed).containsExactly(202L);
    } finally {
        allowFinish.countDown();
        pool.shutdownNow();
    }
}

private static void awaitOrFail(CountDownLatch latch) {
    try {
        if (!latch.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Barrier timeout");
        }
    } catch (InterruptedException interrupted) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException(interrupted);
    }
}
~~~

**Điều kiện chạy đúng:** pool JDBC cần đủ connections cho **hai transactions + query kiểm tra từ thread JUnit** (thường tối thiểu ba concurrent connections). Nếu Hikari pool chỉ có hai slots, phép query `visibleBefore` có thể chờ pool rồi timeout; lỗi này liên quan **test capacity**, không phải PostgreSQL isolation. Config test nên đặt `maximumPoolSize` phù hợp, dùng datasource đúng transaction manager, tránh reuse fixture từ testcase khác.

Trong ví dụ, `TransactionTemplate` phải được đặt trên mỗi thread để Spring bind đúng connection/transaction. `@Transactional` ở test JUnit **không truyền ngầm** sang `ExecutorService` threads.

### 10.3. Điều test chứng minh và không chứng minh

Đã chứng minh:

- Hai transactions có thể tồn tại đồng thời trên những connection khác nhau.
- Row của A bị rollback; row của B được commit.
- Dữ liệu chưa commit của cả hai không visible trong transaction READ COMMITTED khác.

Chưa chứng minh:

- Một remote partition request chạy đúng trên hai **process** khác nhau.
- Duplicate message/ACK semantics của broker.
- Reader/checkpoint/restart của toàn job.
- Hai transactions cùng update **một aggregate row** là an toàn.

Để kiểm chứng nhiều worker remote, phải nâng test lên **multi-process integration** với shared `JobRepository` và broker thật.

## 11. Khi hai workers tranh cùng một row: lock, deadlock và lost update

Hai partition có **input ranges không overlap** vẫn có thể ghi vào cùng bảng aggregate, ví dụ giao dịch thuộc hai file cùng cập nhật balance của `account_id=42`. Điều này tạo cạnh tranh ở **write ownership**, không phải lỗi partition reader.

### 11.1. Lost update nếu tính toán sai trong application

Anti-pattern:

~~~text
Worker A SELECT balance = 100
Worker B SELECT balance = 100
Worker A UPDATE balance = 110
Worker B UPDATE balance = 120
Expected business balance = 130
Actual = 120 (lost update)
~~~

Không dùng test hai transaction INSERT vào **hai khóa khác nhau** để tuyên bố không có lost update. Cần test hai transactions cùng đọc/ghi **cùng một row** và tính đúng nghiệp vụ sau concurrent commits.

Một phép update cộng dồn có tính nguyên tử ở PostgreSQL:

~~~sql
UPDATE account_balances
SET balance_cents = balance_cents + :deltaCents
WHERE account_id = :accountId;
~~~

PostgreSQL serialize các writes tranh chấp row lock phù hợp, nhưng **không** giải quyết việc **cùng event được redeliver hai lần**: nếu lệnh chạy hai lần thì balance vẫn cộng hai lần.

### 11.2. Event ledger và aggregate update phải commit cùng nhau

Một mô hình idempotent cho **một event**:

~~~sql
WITH accepted_event AS (
    INSERT INTO applied_events
        (snapshot_key, event_id, account_id, delta_cents)
    VALUES
        (:snapshotKey, :eventId, :accountId, :deltaCents)
    ON CONFLICT (snapshot_key, event_id) DO NOTHING
    RETURNING account_id, delta_cents
)
UPDATE account_balances AS b
SET balance_cents = b.balance_cents + a.delta_cents
FROM accepted_event AS a
WHERE b.account_id = a.account_id;
~~~

**Điều kiện:** `applied_events` có unique key `(snapshot_key,event_id)`, `account_balances` đã có row cho account và cả ledger insert lẫn balance update thuộc **một transaction**. Nếu event được insert nhưng không có row balance để update, transaction **không được âm thầm commit một ledger “đã áp dụng”**: kiểm tra affected-row count hoặc business invariant rồi throw để rollback. Nếu có nhiều event trong một statement/batch, cần điều chỉnh SQL/logic để cộng đúng theo account.

### 11.3. Deadlock và serialization failure

Ở PostgreSQL:

- `40P01`: deadlock detected; transaction bị abort/rollback.
- `40001`: serialization failure trong transaction isolation phù hợp; phải retry **toàn transaction**.
- Sau một SQL error khiến PostgreSQL transaction aborted, không thể đơn giản catch và retry statement tiếp theo **trong cùng transaction**.

**Test đúng:** ép hai transactions khóa rows theo **thứ tự ngược nhau**, dùng barrier sau khóa đầu, bắt bounded retry/rollback, rồi xác nhận final business balances/ledger chính xác. Không dùng sleep để hy vọng deadlock xuất hiện.

### 11.4. Isolation levels và test oracle

| Isolation | Điều cần test | Điều không được giả định |
|---|---|---|
| `READ_COMMITTED` | Uncommitted rows không visible; mỗi statement có snapshot riêng | Không có lost update với read-modify-write ở application |
| `REPEATABLE_READ` | Snapshot đọc ổn định theo PostgreSQL semantics | Không bao giờ cần retry khi concurrent update |
| `SERIALIZABLE` | Một số anomalies dẫn đến `40001` và transaction retry | Tất cả concurrent operations sẽ tự hoàn tất không lỗi |

Tùy DB/driver/version, behavior và error SQLState có thể khác. Với Spring Batch dùng PostgreSQL, test trên **đúng database engine** trước khi thay isolation level để “chữa” race.

## 12. Multi-threaded Step: một StepExecution nhưng nhiều chunk threads

Trong **multi-threaded chunk step**, các chunk có thể chạy đồng thời trong **cùng logical `StepExecution`**. Đây là tình huống khác remote partitioning: `@StepScope` tạo bean **theo StepExecution**, không phải tự động một reader instance cho mỗi chunk thread.

### 12.1. Rủi ro của stateful reader/writer

Một `JdbcCursorItemReader`, file reader hoặc custom reader có mutable cursor/index có thể không thread-safe khi được chia sẻ giữa chunks. Nếu hai threads đọc cùng reader:

- Đọc lặp hoặc bỏ qua item.
- Checkpoint trở nên không nhất quán với input được xử lý.
- Sau rollback/restart có thể đọc lại không đúng phạm vi.
- Một test đếm đúng `writeCount` tổng vẫn có thể bỏ một business key và nhân đôi key khác.

Không coi `synchronized` trên toàn reader là giải pháp mặc định: nó có thể tuần tự hóa toàn I/O và làm mất lợi ích concurrency, vẫn phải xét transaction/checkpoint semantics.

### 12.2. Per-chunk rollback có thể chồng lấn

~~~text
Thread A: Chunk A begins -> writes A1, A2 -> exception -> ROLLBACK
Thread B: Chunk B begins -> writes B1, B2 -> COMMIT

Expected:
  A1, A2 không có từ Tx A
  B1, B2 tồn tại từ Tx B
  StepExecution state và restart xử lý đúng dữ liệu chưa commit
~~~

Nếu chunk threads dùng đúng **transaction manager và thread-bound JDBC connections**, transaction rollback của A không hoàn tác chunk B. Nhưng nếu writer chia sẻ một mutable JDBC `Connection`/`EntityManager` bên ngoài transaction scope giữa threads, kết quả có thể không còn đúng như giả định.

### 12.3. Checklist cho test đồng thời

- Reader/writer/processor có thực sự thread-safe hoặc state tách biệt?
- Mỗi chunk có connection/transaction identity đúng không?
- Có rollback một chunk trong khi chunk khác commit thành công không?
- Thử lại sau rollback có bảo toàn **exact business key set** không?
- Metadata/checkpoint có phản ánh tương quan tiến độ với ordering không?
- `TaskExecutor` có giới hạn, Hikari pool đủ nhưng không gây DB overload?
- Các listener/metric counters có thread safety, không mất delta khi callbacks chạy song song?
- Có test **restart** sau exception ở giữa các chunks không?

**Tránh test bằng `Thread.sleep` rồi tuyên bố concurrency đã được kiểm chứng.** Sử dụng barrier/latch/controlled failure và đo actual overlapping transaction intervals.

## 13. Parallel steps và local partitioning: transaction độc lập

Khi chạy hai flows/steps song song hoặc local partitioning với `TaskExecutorPartitionHandler`:

~~~mermaid
flowchart TD
    J["JobExecution"]
    J --> A["StepExecution A / Partition P0"]
    J --> B["StepExecution B / Partition P1"]
    A --> TA["Business Transaction A"]
    B --> TB["Business Transaction B"]
    TA --> DB[(Shared DB)]
    TB --> DB
    A --> MA[(JobRepository)]
    B --> MA
~~~

Nếu P0 fail và P1 commit, business output có thể chứa P1; manager step/job thường không thể báo toàn bộ partitioning thành công nếu một required partition vẫn failed. Test phải xét:

1. **Không overlap** input ranges/keys ngoài plan.
2. Bản ghi P0 thuộc chunk lỗi không được commit.
3. Các chunk thành công P0 trước lỗi vẫn tồn tại, theo transaction design.
4. P1 output đã commit tồn tại và không bị “undo” vì P0 fail.
5. Các `StepExecution`/`ExecutionContext` có status/checkpoint đúng.
6. Restart không xử lý lại partition completed trái contract hoặc tạo duplicate effects.

`gridSize=8` **không bảo đảm** tám worker threads/pods chạy đồng thời; concurrency thực phụ thuộc executor, handler, broker consumer/prefetch, pool và hạ tầng. Khi test concurrency, phải chứng minh có **hai execution intervals overlap**, không chỉ manager tạo tám partitions.

### 13.1. Với worker dùng step-scoped reader

Một reader Spring Batch partitioning thường late-bind:

~~~java
@Bean
@StepScope
public JdbcCursorItemReader<Payment> partitionReader(
        @Value("#{stepExecutionContext['fromInclusive']}")
            Long fromInclusive,
        @Value("#{stepExecutionContext['toExclusive']}")
            Long toExclusive,
        @Value("#{jobParameters['snapshotKey']}")
            String snapshotKey,
        @Qualifier("businessDataSource")
            DataSource businessDataSource) {
    // Dùng [fromInclusive, toExclusive) và ORDER BY key ổn định.
    // Return một reader mới cho từng worker StepExecution.
    return new JdbcCursorItemReaderBuilder<Payment>()
            .name("partitionPaymentReader")
            .dataSource(businessDataSource)
            .sql("""
                SELECT snapshot_key, payment_id, account_id, amount_cents
                FROM source_payments
                WHERE snapshot_key = ?
                  AND payment_id >= ?
                  AND payment_id < ?
                ORDER BY payment_id
                """)
            .preparedStatementSetter(ps -> {
                ps.setString(1, snapshotKey);
                ps.setLong(2, fromInclusive);
                ps.setLong(3, toExclusive);
            })
            .rowMapper((rs, n) -> new Payment(
                    rs.getString("snapshot_key"),
                    rs.getLong("payment_id"),
                    rs.getLong("account_id"),
                    rs.getLong("amount_cents")))
            .saveState(true)
            .build();
}
~~~

Đoạn này là **method minh họa**: cần imports tương ứng `@Bean`, `@StepScope`, `@Value`, `@Qualifier`, `DataSource`, `JdbcCursorItemReader`/builder và record `Payment` của ứng dụng. Nó không tự định nghĩa manager/worker Job. Khi restart, **reader name** và `ExecutionContext` keys phải giữ ổn định; nếu input snapshot thay đổi trong lúc chạy, checkpoint theo vị trí/sort key có thể không còn phù hợp.

## 14. Remote partitioning: rollback ở worker không phải rollback ở manager

Trong remote partitioning, manager tạo worker `StepExecution` và gửi request qua transport. Worker tự tải metadata đã lưu và chạy reader/process/writer trên resource của nó:

~~~mermaid
sequenceDiagram
    participant M as Manager
    participant J as Shared JobRepository
    participant Q as Broker
    participant W1 as Worker A
    participant W2 as Worker B
    participant D as Business DB
    M->>J: Persist partition StepExecutions P0/P1
    M->>Q: Dispatch P0/P1
    Q->>W1: Request P0
    Q->>W2: Request P1
    W1->>D: P0 chunk SQL -> ERROR -> ROLLBACK
    W2->>D: P1 chunk SQL -> COMMIT
    W1->>J: P0 FAILED / rollback count
    W2->>J: P1 COMPLETED
    W1-->>Q: Reply/error theo topology
    W2-->>Q: Reply theo topology
    Q-->>M: Results / state observations
    Note over M,J: Manager phải tổng hợp trạng thái từng StepExecution
~~~

### 14.1. Oracle cho remote rollback

Một integration test đúng cần:

- Manager, broker và **ít nhất hai worker processes/contexts** dùng chung JobRepository.
- P0 nhận exception sau business SQL trước commit; P1 commit thành công.
- `JobExplorer`/repository cho thấy **P0 failed, P1 completed** theo execution identity.
- Business output **không có keys của chunk P0 lỗi**, nhưng có keys P1 committed.
- Nếu P0 đã commit chunks trước đó, chúng vẫn tồn tại.
- Manager không báo toàn job `COMPLETED` giả khi required partition failed.
- Sau restart, P0 xử lý phần cần tiếp tục, P1 không tạo duplicate business effects.

Nếu chỉ dùng mock `MessageChannel` hoặc chạy manager và worker trong cùng context, test **chưa chứng minh** socket crash/ACK/redelivery của broker. Testcontainers broker cùng PostgreSQL và worker process riêng giúp kiểm tra gần production hơn.

### 14.2. Reply và ACK không chứng minh rollback/commit

Broker có thể ACK message theo transport contract trước hoặc sau việc worker làm xong; reply có thể trễ, trùng hoặc mất. Một reply `COMPLETED` có thể không phản ánh cùng transaction resource với business DB nếu thiết kế sai. Để kết luận rollback, phải đọc **business output** chứ không chỉ đếm request/reply.

### 14.3. Không phát lại request cho stale worker một cách mù quáng

Khi manager nghĩ worker A chết nhưng A vẫn đang xử lý, worker B có thể nhận cùng partition do redelivery. Thế là hai transaction **có thể đồng thời** trên cùng business keys. Cần idempotency, lease/fencing ở resource thật khi cần, và recovery policy không tạo duplicate side effects. Một token trong metadata **không tự ngăn** worker cũ commit nếu business DB không kiểm tra token hoặc unique business key.

## 15. Hai datasources, propagation và Spring Batch JobRepository

Một hệ thống production có thể dùng:

~~~text
metadataDataSource -> JobRepository, BATCH_JOB_EXECUTION, BATCH_STEP_EXECUTION
businessDataSource -> source_payments, posted_payments, balances
brokerDataSource / external message broker -> request/reply/ACK
~~~

Ngay cả khi hai PostgreSQL datasources trỏ về cùng **database server**, không được tự coi chúng cùng một local transaction nếu sử dụng **khác physical connection/transaction manager**.

### 15.1. Phân biệt các tổ hợp

| Topology | Có thể rollback business output khi chunk fail? | Có phải metadata và business luôn atomic? |
|---|---|---|
| Business JDBC cùng `DataSourceTransactionManager`, một connection bind với chunk | Có, với SQL tham gia transaction | Không suy rộng sang side effects/resource khác |
| Batch metadata và business thao tác trên cùng local transaction thực sự | Có theo local transaction boundary | **Chỉ** các thao tác thật sự tham gia cùng transaction mới atomic |
| Metadata DB A, business DB B, mỗi DB local transaction manager | Business rollback riêng | **Không**, không có XA/JTA/distributed coordination tự động |
| Writer mở connection auto-commit riêng | SQL có thể commit ngay | **Không**; chunk rollback bên ngoài không undo |
| Writer gọi method `REQUIRES_NEW` để ghi ở datasource riêng | Inner transaction có thể commit độc lập | **Không**; outer rollback không undo inner committed result |
| Writer gọi HTTP/email/object storage | Side effects có thể diễn ra trước/ngoài DB commit | **Không** |
| JTA/XA có resource enlistment đúng và recovery được vận hành | Tùy cấu hình, provider/resources | Cần test distributed transaction/failure riêng, không tự động “exactly-once business” |

### 15.2. Trường hợp `REQUIRES_NEW` làm test rollback thất bại

~~~java
@Service
public class PaymentAuditService {

    @Transactional(
        transactionManager = "auditTransactionManager",
        propagation = Propagation.REQUIRES_NEW)
    public void insertAudit(Payment payment) {
        // Ghi audit riêng và có thể COMMIT trước chunk transaction.
        auditRepository.insert(payment);
    }
}
~~~

**Đoạn trên là anti-pattern nếu nghiệp vụ đòi audit rollback cùng payment**, cần imports `@Service`, `@Transactional`, `Propagation`, `Payment` và `auditRepository` ứng dụng. Khi outer writer sau đó throw và chunk rollback, audit record có thể **vẫn tồn tại**.

Nếu audit cần là một phần của cùng atomic business effect, hãy ghi audit trong **cùng resource/transaction**. Nếu audit được thiết kế là “attempt log” lưu cả lần xử lý thất bại, separate commit có thể **cố ý đúng**; test phải mô tả rõ audit không được coi là completed payment.

### 15.3. Transaction manager được chọn ở đâu?

Trong Spring Batch 5.x chunk builder:

~~~java
.chunk(250, businessTransactionManager)
~~~

Chính bean `businessTransactionManager` quyết định transaction resource của step. Nếu có nhiều `PlatformTransactionManager`, cần `@Qualifier`/bean selection rõ ràng, tránh vô tình inject metadata manager cho writer database.

**Test wiring tối thiểu:**

1. Writer dùng `JdbcTemplate`/EntityManager trỏ tới business resource dự kiến.
2. Throw sau SQL, trước COMMIT.
3. Business table không chứa row sau failed chunk.
4. Nếu intentionally chạy bằng wrong transaction manager trong test lab, test phải **đỏ** vì output tồn tại.
5. Metadata state có ý nghĩa, nhưng không dùng nó làm bằng chứng duy nhất của business rollback.

Không thử sửa lỗi bằng cách bọc toàn bộ remote job trong một `@Transactional` ở manager: worker process không tự kế thừa thread-bound transaction context của manager.

### 15.4. Savepoints và nested transactions

`PROPAGATION_NESTED` có thể sử dụng savepoint khi transaction manager/driver/resource hỗ trợ. Rollback tới savepoint **khác** rollback toàn physical transaction. `REQUIRES_NEW` mở transaction độc lập (theo khả năng resource/config), còn `REQUIRED` thường tham gia transaction đang active.

Một test chỉ gọi method được annotate `@Transactional` từ **cùng bean qua self-invocation** có thể không đi qua proxy, nên propagation không được áp như tưởng tượng. Nếu định test behavior `REQUIRES_NEW`/`NESTED`, hãy gọi qua Spring bean/proxy đúng cấu hình và đọc DB sau mỗi boundary.

## 16. Side effects ngoài transaction: rollback không phải nút “undo mọi thứ”

Ví dụ worker:

~~~text
1. INSERT payment vào business DB (chưa commit)
2. Gửi email "đã thanh toán" qua HTTP API
3. Cập nhật một file/object storage
4. SQLException trước DB COMMIT
5. ROLLBACK business DB
~~~

Kết quả có thể là **khách hàng đã nhận email** nhưng DB không có payment. Spring Batch rollback chunk transaction không thu hồi được email hoặc xóa object đã publish, trừ khi ứng dụng thiết kế compensation/commit coordination.

### 16.1. Transactional outbox

Thay vì phát message/email ngay trong writer:

~~~sql
BEGIN;

INSERT INTO posted_payments
    (snapshot_key, payment_id, account_id, amount_cents)
VALUES
    (:snapshotKey, :paymentId, :accountId, :amountCents);

INSERT INTO payment_outbox
    (event_key, event_type, payload_json, state)
VALUES
    (:eventKey, 'PAYMENT_POSTED', :payloadJson, 'PENDING');

COMMIT;
~~~

Nếu hai bảng ở **cùng database transaction**, lỗi trước COMMIT làm cả payment và outbox event rollback. Một outbox relay riêng gửi message sau đó, với retry/dedupe; relay/broker có thể giao trùng, consumer/downstream vẫn cần idempotency.

**Đừng gọi outbox là exactly-once message delivery**. Nó giúp **atomic business change + event intent** tại database boundary; network delivery vẫn có thể at-least-once.

### 16.2. Test outbox rollback

Test hai trường hợp:

| Test | Fault point | Oracle |
|---|---|---|
| Writer throw trước commit | Sau `posted_payments` và `payment_outbox` INSERT | Cả hai bảng **không có row** của chunk lỗi |
| Business COMMIT, relay chết trước broker ACK | Relay gửi/không rõ ACK | Outbox vẫn discoverable, retry/dedupe không tạo duplicate business effect |

Nếu dùng broker trực tiếp với `send()` trong chunk transaction nhưng không có transaction coordinator đủ mạnh, rollback business DB **không chắc rollback message đã gửi**. Test phải mô tả ACK mode và protocol thực tế.

### 16.3. File output và JPA/broker

Một file writer có thể flush buffer hoặc ghi tệp trước khi database transaction hoàn tất. Nếu sau đó chunk rollback, bytes đã ghi có thể không tự biến mất. Spring Batch `ItemStream` có thể lưu checkpoint và quản lý restart, nhưng **không đồng nghĩa mọi filesystem là transactional resource**.

Đối với output quan trọng:

- Ghi file tạm theo run/partition, không cho downstream đọc file chưa validate.
- Cân nhắc append/checkpoint/truncate semantics của writer và storage đang dùng.
- Sau khi hoàn tất, đối soát checksum/count rồi publish versioned output.
- Chấp nhận rằng DB commit, file publish và broker ACK thường không atomic mặc định.

Đối với object storage, rename không nhất thiết là atomic như trên filesystem cùng mount; hãy sử dụng publish marker/version/object listing contract phù hợp.

### 16.4. Compensation không phải DB rollback

Nếu đã gọi API tính tiền hoặc gửi email, có thể cần **compensating action** (“hoàn tiền”, “thu hồi thông báo”) thay vì rollback. Compensation bản thân có thể thất bại, cần idempotency và audit. Test phải phân biệt:

- **Physical rollback**: một resource transaction chưa commit bị hoàn tác.
- **Compensation**: một tác động đã diễn ra được cân bằng bởi hành động nghiệp vụ mới.

Hai khái niệm có timing, failure mode và invariant khác nhau.

## 17. Fault injection đúng commit boundary

“Kill worker bất kỳ lúc nào” giúp chaos test rộng, nhưng không chắc tái hiện lỗi **sau SQL trước commit**. Để kiểm thử rollback có thể lặp lại, đặt fault point có chủ đích.

### 17.1. Các mốc cần phân biệt

~~~text
F0  Trước reader.open()/chunk begin
F1  Sau reader/process, trước writer
F2  Sau một hoặc nhiều SQL statements trong writer
F3  Writer trả về, trước physical transaction COMMIT
F4  Khi COMMIT được gửi, kết quả phản hồi chưa rõ
F5  Business COMMIT đã được xác nhận
F6  Metadata/ExecutionContext update/reply/ACK
F7  Manager aggregation / job completion
~~~

Ở F2/F3, nếu transaction đúng, rollback sẽ không để output chunk lỗi. Ở F4, client **không thể giả định** commit thất bại; ở F5 trở đi, không thể “rollback” một business transaction đã commit bằng cách ném exception trong Java.

### 17.2. Test hook trước commit với transaction synchronization

Một writer test-only có thể đăng ký callback:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.batch.item.ItemWriter;

AtomicBoolean failOnce = new AtomicBoolean(true);

ItemWriter<Payment> writer = chunk -> {
    // Delegate đã ghi SQL trên connection thuộc chunk transaction.
    jdbcDelegate.write(chunk);

    if (failOnce.compareAndSet(true, false)) {
        if (!TransactionSynchronizationManager
                .isSynchronizationActive()) {
            throw new IllegalStateException(
                    "No active transaction synchronization");
        }
        TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void beforeCommit(boolean readOnly) {
                        throw new IllegalStateException(
                                "Injected failure before COMMIT");
                    }
                });
    }
};
~~~

Đoạn này là **snippet trong test**, giả định có `jdbcDelegate`/`Payment` và Spring transaction synchronization active. Callback `beforeCommit` được gọi trong quá trình commit; nếu throw trước khi physical commit và local transaction manager rollback thành công, output chunk phải vắng mặt. Không dùng hook này trong production và **không giả định** transaction manager/provider nào cũng có cùng thứ tự callbacks/commit failure behavior.

### 17.3. Test lỗi sau commit

Một `TransactionSynchronization.afterCommit()` callback chỉ chạy **sau khi physical commit được xem là thành công** trong transaction manager đang dùng. Nếu callback ném lỗi:

- Database **không thể bị rollback chỉ vì callback throw sau commit**.
- Application/step có thể ghi nhận lỗi ở lifecycle tiếp theo.
- Worker có thể chưa kịp publish reply/ACK.

Đây là test rất hữu ích để chứng minh **trạng thái exception và business durability không phải một**. Nếu application cần thông báo downstream, đừng rely hoàn toàn vào callback in-memory; dùng outbox/ledger có thể recover sau crash.

### 17.4. Network cut quanh COMMIT

Đối với case khó F4, có thể sử dụng fault proxy/network injection trong **staging**:

~~~text
Worker  -->  Fault proxy  -->  PostgreSQL
                     |
               DROP connection
               đúng giai đoạn COMMIT
~~~

Không phải lúc nào fault proxy cũng chứng minh được server đã xử lý COMMIT trước khi kết nối đứt. Vì thế test outcome phải phân thành **confirmed rollback**, **confirmed commit**, **unknown** dựa trên dữ liệu đọc từ connection mới và business key reconciliation. Không “định nghĩa” tất cả connection reset là rollback.

**Không tiêm lỗi vào production để chạy bài test.** Staging phải có data giả, khả năng reset/restore và không làm hỏng workload khác.

## 18. Restart sau rollback: tiến độ không được vượt qua dữ liệu chưa commit

Trong Spring Batch, một job `FAILED` thường có thể restart khi cấu hình/JobInstance cho phép. Khi restart:

1. Dùng **cùng identifying `JobParameters`** cho cùng input snapshot.
2. Dựa vào `JobRepository` và `ExecutionContext` đã persist để tìm progress hợp lệ.
3. Giữ names của job/step/reader/partition ổn định.
4. Reader phải hỗ trợ checkpoint và sort key/input ordering nhất quán.
5. Writer phải idempotent với những items/chunks có thể bị phát lại.
6. Không để worker cũ còn xử lý work unit đồng thời mà side effects không được bảo vệ.
7. Cuối cùng đối soát tập business keys, không chỉ `writeCount`.

### 18.1. Một ví dụ diễn tiến

~~~text
Input snapshot: payments 1..1,003
Chunk size: 250

Commit chunk 1: 1..250
Commit chunk 2: 251..500
Chunk 3:        501..750 (writer throws, ROLLBACK)
Job FAILED

Restart cùng JobInstance:
  checkpoint hợp lệ cuối ~ 500 (theo reader/stream semantics)
  xử lý lại dữ liệu chưa commit
  commit 501..750, 751..1,000, 1,001..1,003

Expected output cuối:
  exactly 1,003 unique payment IDs
~~~

`checkpoint hợp lệ cuối ~500` là **minh họa về logic**, không phải bảo đảm tuyệt đối của mọi reader khi paging/cursor/multi-threaded step hoặc database schema khác nhau. Test cần kiểm tra `ItemStream`/`ExecutionContext` thực tế; không tự suy từ `readCount` rằng resume bắt đầu ở row 501.

### 18.2. Idempotent writer với unique business key

~~~sql
INSERT INTO posted_payments
    (snapshot_key, payment_id, account_id, amount_cents)
VALUES
    (:snapshotKey, :paymentId, :accountId, :amountCents)
ON CONFLICT (snapshot_key, payment_id) DO NOTHING;
~~~

Với unique key, một row đã commit trước crash sẽ không bị insert thêm khi replay. Nhưng nếu cùng key có payload/amount khác, `DO NOTHING` che vi phạm dữ liệu; cần checksum/version validation và immutable snapshot contract.

Với update cộng dồn, unique constraint **trên aggregate row** không đủ bảo đảm idempotency: cần **event ledger cùng transaction** với việc áp dụng delta (như phần 11).

### 18.3. JobInstance, JobExecution và StepExecution

| Thực thể | Identity | Ảnh hưởng đến rollback/restart |
|---|---|---|
| `JobInstance` | Job name + identifying JobParameters | Định danh logical job cần restart |
| `JobExecution` | Một lần chạy/attempt của JobInstance | Retry/restart có thể tạo execution mới |
| `StepExecution` | Một lần chạy step/partition | Có counts/context/status riêng |
| **Business key** | Ví dụ `snapshotKey + paymentId` | Phải ổn định qua executions/retries để chống double effect |

**Không dùng `stepExecutionId` làm business idempotency key duy nhất**, vì restart cùng logical input có thể tạo attempt với ID khác.

### 18.4. Không dùng random run.id để “chữa” một job fail

Nếu mỗi lần gửi lại:

~~~text
JobParameters: snapshotKey=rollback-snap-001, run.id=<random>
~~~

thì Spring Batch thường xem đó là một **JobInstance mới**; metadata/checkpoint của failed instance cũ không được dùng theo cách restart chuẩn. Có thể vô tình chạy lại toàn bộ business input và tạo duplicate effects nếu writer không idempotent.

Chỉ tạo instance mới khi business contract thật sự muốn **một run khác**, không để che rollback/metadata failure.

## 19. Remote chunking: rollback nằm ở hai đầu pipeline

**Remote chunking** khác remote partitioning: manager thường **đọc item và tạo chunk**, worker nhận chunk, process/write và trả kết quả qua messaging. Vì reader ở manager, checkpoint của nguồn không thể được hiểu như reader của một remote partition worker.

~~~mermaid
flowchart LR
    R["Manager ItemReader"] --> C["Manager chunks + request messages"]
    C --> Q[(Broker)]
    Q --> W["Worker ItemProcessor / ItemWriter"]
    W --> DB[(Business DB)]
    W --> A["Reply / ACK"]
    A --> M["Manager aggregates/checkpoints"]
~~~

### 19.1. Test nào phải bổ sung?

- Worker đã ghi SQL rồi throw: **business chunk transaction** rollback đúng, manager nhận lỗi/retry theo contract.
- Worker business commit thành công nhưng reply mất: manager có thể gửi lại **cùng chunk**; writer idempotent.
- Manager reader/metadata checkpoint trước khi worker thực sự commit: test chứng minh không bỏ mất item khi worker crash.
- Broker redelivery cùng chunk: không tạo duplicate business output.
- Manager restart với pending messages: correlation của chunk/attempt không biến message cũ thành job mới.
- Concurrent worker chunks xử lý cùng aggregate key: tránh lost update/lock contention và double-applied event.

Không suy từ `reader.readCount` của manager rằng worker database đã commit tương ứng. **ACK/reply và JDBC commit ở hai resource boundaries**, trừ khi topology thực sự cung cấp transaction phối hợp mạnh và đã được kiểm thử failure mode.

### 19.2. Transactional queue reader và buffering

Trong một số kiến trúc Batch, item reader nhận từ một queue transaction-aware; rollback có thể khiến message được **đưa lại vào queue**. Spring Batch có cấu hình liên quan tới “reader is transactional queue” theo version để điều chỉnh buffering/replay. Chọn nhầm chế độ có thể gây:

- Item bị xử lý hai lần khi cả framework buffer lẫn broker redelivery.
- Mất item nếu message đã ACK bên ngoài transaction rồi chunk fail.
- Test “chỉ với ListItemReader” chạy xanh nhưng production JMS/Kafka khác semantics.

Vì vậy, test reader/broker thực với **ACK/offset commit**, transaction manager và retry settings, không mặc định mọi `ItemReader` có cùng behavior sau rollback.

## 20. Kiểm tra transaction rollback count và trạng thái metadata cho đúng nghĩa

`StepExecution` chứa:

- `getReadCount()`, `getWriteCount()`, `getFilterCount()`.
- `getReadSkipCount()`, `getProcessSkipCount()`, `getWriteSkipCount()`.
- `getCommitCount()`, `getRollbackCount()`.
- `getStatus()`, `getExitStatus()`.
- `ExecutionContext` với trạng thái reader/writer nếu `ItemStream` lưu checkpoint.

### 20.1. Vì sao `rollbackCount` không phải “số SQL bị rollback”?

Một rollback có thể hoàn tác **500 SQL statements**, hoặc **không có SQL** nếu reader lỗi trước writer. Một SQL batch có thể gửi nhiều statements trước khi transaction rollback. Ngược lại, một lỗi ở external API có thể ném exception nhưng side effect không thể rollback.

`rollbackCount` giúp điều tra **framework transaction attempts**, không đo số row bị loại bỏ. `writeCount` không phải committed new-row count khi có `ON CONFLICT DO NOTHING`, skip/retry, bulk writer hoặc writer side effects không chuẩn.

### 20.2. Đọc metadata sau test

Trong PostgreSQL dùng Spring Batch 5.x metadata schema tương ứng:

~~~sql
SELECT STEP_EXECUTION_ID,
       JOB_EXECUTION_ID,
       STEP_NAME,
       STATUS,
       EXIT_CODE,
       READ_COUNT,
       WRITE_COUNT,
       FILTER_COUNT,
       READ_SKIP_COUNT,
       PROCESS_SKIP_COUNT,
       WRITE_SKIP_COUNT,
       COMMIT_COUNT,
       ROLLBACK_COUNT
FROM BATCH_STEP_EXECUTION
WHERE JOB_EXECUTION_ID = :jobExecutionId
ORDER BY STEP_EXECUTION_ID;
~~~

Đây là **truy vấn read-only**, cần kiểm tra column names theo version/schema được cài thật. Với remote partitioning, phải xem **cả manager step và từng worker partition `StepExecution`**. Một manager `FAILED` có thể chứa worker steps completed; điều đó không sai nếu các chunk/partition ấy đã commit.

### 20.3. Khi test thất bại phải giải thích bằng evidence

Một báo cáo tốt có:

~~~text
jobExecutionId: 720
stepExecutionId: 1234
workerInstanceId: worker-a
partitionName: partition-0003
failurePoint: AFTER_SQL_BEFORE_COMMIT
businessTransactionManager: businessTxManager
businessDataSource: paymentsDb
metadataDataSource: batchDb
expectedChunkKeys: [501..750]
committedChunkKeysAfterFailure: []
previousCommittedKeys: [1..500]
jobStatus: FAILED
rollbackCount: > 0 (observed)
~~~

Đây là **mẫu báo cáo**, không phải result thực tế hay log của một job được chạy. Trường `failurePoint` phải được instrument tại boundary thật; đừng gán `AFTER_SQL_BEFORE_COMMIT` cho một exception xảy ra sau khi writer return mà không kiểm soát commit.

## 21. Observability: theo dõi rollback nhưng không tạo số liệu ảo

Một dashboard đáng dùng khi job lỗi phải nối ba loại evidence:

| Nguồn | Metric/log | Giải thích |
|---|---|---|
| Spring Batch | Job/Step status, commit/rollback/skip/retry counts | Framework progress |
| Worker | Writer-call duration, chunk error count, transaction retry category | Attempts và xử lý lỗi |
| Business DB | Unique committed keys, checksum, transaction/wait/lock evidence | Kết quả thực |
| JobRepository DB | Metadata write/read latency, stale `STARTED` executions | Điều phối và checkpoint |
| Broker | Queue age, redelivery, ACK/reply, DLQ | Recovery/routing |
| JVM/Pool | Hikari active/pending/acquire p95, CPU/GC, thread activity | Resources gây rollback/timeout |

### 21.1. PostgreSQL transaction và wait metrics

Tổng quan transactions tại database level:

~~~sql
SELECT datname,
       xact_commit,
       xact_rollback,
       deadlocks,
       conflicts,
       stats_reset
FROM pg_stat_database
WHERE datname = current_database();
~~~

Các counters này là **tích lũy ở mức database** và có thể bao gồm nhiều applications, không thể gán mỗi rollback cho một Spring Batch worker. Để tính rate, lấy delta giữa hai thời điểm và nêu workloads khác trên cùng DB.

Khi nghi DB lock:

~~~sql
SELECT pid,
       application_name,
       state,
       wait_event_type,
       wait_event,
       now() - xact_start AS transaction_age,
       pg_blocking_pids(pid) AS blocking_pids
FROM pg_stat_activity
WHERE datname = current_database()
ORDER BY transaction_age DESC NULLS LAST;
~~~

`transaction_age` là thời lượng transaction, **không** phải lock wait chính xác. Dùng `pg_blocking_pids` và log/trace SQL/transaction identity để xác định blocker. Không dùng query monitor nặng từng giây trên production nếu gây thêm tải.

### 21.2. Metric stages cần tách

Các tên sau là **đề xuất custom instrumentation**, không mặc định Spring Batch đã export:

~~~text
batch.chunk.writer.items.attempted
batch.chunk.write.call.duration
batch.chunk.rollback.observed
batch.chunk.commit.duration
batch.step.retry.attempts
batch.step.skip.events
batch.business.unique.keys.committed
batch.worker.active.executions
batch.broker.redelivery
~~~

Nếu increment counter trong `ItemWriter`, nó là **attempted** chứ không phải committed. Nếu increment trong `afterCommit`, callback in-memory có thể **không chạy sau crash** và không tự biết `ON CONFLICT DO NOTHING` insert bao nhiêu new rows. Business ledger/output cần là nguồn đối soát.

### 21.3. Metric labels tránh cardinality cao

Prometheus labels nên có giá trị giới hạn: `logicalJobName`, `stepRole`, `errorCategory`, `poolName`, `environment`, `statusCategory`. `jobExecutionId`, `stepExecutionId`, `requestId`, `partitionName`, raw input path và business keys nên ở structured logs/traces hoặc audit store, không là label giữ lâu cho mỗi data point.

Không tạo một time series cho mỗi item lỗi; scale job 10 triệu items có thể làm monitoring system bão hòa.

## 22. Thiết kế integration test với PostgreSQL và broker thật

Một test unit với `SimpleMeterRegistry`/mock writer có thể kiểm tra callback, nhưng không chứng minh physical JDBC rollback. Một integration test với H2 có thể khác PostgreSQL ở SQLState, row locks, transaction isolation, `ON CONFLICT` hoặc savepoints.

### 22.1. Hạ tầng Testcontainers tối thiểu

Ở phần 6 đã có `PostgreSQLContainer` cho chunk rollback. Nếu dùng remote worker, thêm **broker container phù hợp transport** đang chạy (RabbitMQ/Kafka/JMS) và tách contexts/processes:

~~~text
JUnit/Test harness
     |
     +--> PostgreSQL (Spring Batch metadata + business schema)
     +--> Broker thật (durable request/reply theo config)
     +--> Worker process A  ---+
     +--> Worker process B  ---+--> Shared metadata and DB
     +--> Manager process
~~~

**Hai workers chạy trên hai threads trong cùng JVM** là một concurrency integration test hữu ích nhưng **chưa chứng minh** socket disconnect, separate application context, process kill, broker reconnection và mixed-version delivery. Khi test remote partitioning, workers cần dùng đúng `JobRepository`/step names/converters.

### 22.2. Kịch bản E2E rollback

1. Seed immutable input snapshot và bảng output rỗng.
2. Tạo 4 partitions nửa mở `[1,252)`, `[252,503)`, `[503,754)`, `[754,1004)`.
3. Khởi động ít nhất hai worker processes, bảo đảm broker consumers ready.
4. Manager tạo `StepExecution` rồi dispatch.
5. Inject writer failure trước commit ở partition chứa key 600, đồng thời partition khác commit.
6. Chờ job failure với **deadline hữu hạn**; lấy JobRepository state và logs.
7. Query business DB: chunk lỗi rollback, các chunks/partitions đã commit vẫn còn.
8. Stop/drain worker cũ, restart cùng `JobInstance`/snapshot/partition plan.
9. Đối soát **1.003 expected keys** và tổng tiền `5.035.060`.
10. Xác minh duplicate request/reply/ACK không gây double effect.

Mốc inject phải nằm ở **physical transaction boundary** của business DB. Nếu lỗi tạo ở manager trước khi worker bắt đầu, đó là test dispatch failure, **không phải rollback sau writer SQL**.

### 22.3. Tối thiểu hai loại test

| Loại test | Công cụ | Chứng minh |
|---|---|---|
| **Business rollback** | Spring Batch Test + real PostgreSQL, một worker | Chunk transaction và DB output |
| **Distributed recovery** | Real broker + shared repository + ≥2 worker processes | Redelivery, crash, metadata/correlation và idempotency |

Không bỏ test đầu để chỉ chạy end-to-end ngẫu nhiên: nếu E2E fail do broker, khó biết lỗi transaction. Và cũng không dừng ở test đầu để kết luận whole remote topology an toàn.

## 23. Ma trận test transaction rollback theo cấp độ

Một test suite tốt nên có **các biến thể cụ thể** với expected output và expected metadata, không chỉ một test “writer throw”.

| Test ID | Kịch bản | Expected business output | Expected metadata/recovery |
|---|---|---|---|
| TX-01 | Writer throw sau SQL, trước commit chunk 1 | **Không có rows chunk 1** | Step/Job FAILED, rollback evidence |
| TX-02 | Chunk 1 commit, chunk 2 throw | Chỉ rows chunk 1 | Job FAILED, restart từ tiến độ hợp lệ |
| TX-03 | Reader throw trước writer | Không có writes chunk lỗi | Retry/failure theo policy |
| TX-04 | Processor fail permanent | No partial business writes của chunk lỗi | Skip/fail theo configured policy |
| TX-05 | JDBC batch statement thứ k sai constraint | Không có new committed rows từ **cùng transaction lỗi** | Rollback; lỗi không bị giấu |
| TX-06 | JPA flush rồi throw | DB không giữ entity rows của transaction lỗi | Step FAILED, persistence context được xử lý đúng |
| TX-07 | Retry transient fault một lần | Chỉ một bộ unique outcomes | Retry bounded và Step status hợp lệ |
| TX-08 | Skip một item lỗi | Items hợp lệ commit đúng một lần | SkipCount/ExitStatus đúng |
| TX-09 | Vượt skip limit | Chỉ chunks đã commit theo policy | Step FAILED, không success giả |
| TX-10 | `REQUIRES_NEW` audit commit, outer rollback | Audit có thể còn, payment rollback | Test giải thích side-effect split |
| TX-11 | Hai transactions cùng lúc, A rollback/B commit | Chỉ output B | Không cross-rollback |
| TX-12 | Hai workers tranh cùng balance row | Balance đúng theo tất cả unique events đã commit | Không lost update/double apply |
| TX-13 | PostgreSQL deadlock `40P01` | Không có partial effect từ aborted transaction | Retry toàn transaction có giới hạn |
| TX-14 | PostgreSQL serialization `40001` | Kết quả serializable theo contract | Retry đúng isolation semantics |
| TX-15 | Commit response mất | Output có thể đã commit hoặc chưa | Reconcile before replay |
| TX-16 | Crash sau business commit, trước metadata | Output có; metadata có thể stale | Idempotency và restart |
| TX-17 | Broker redelivery request | Một logical business effect | No duplicate even after ACK loss |
| TX-18 | Manager crash, worker vẫn chạy | Không double execution side effect | Ownership/recovery correct |
| TX-19 | Worker A rollback, worker B commit | A chunk không có, B chunks tồn tại | P0 FAILED, P1 COMPLETED |
| TX-20 | Restart cùng identifying params | Exact expected key set | Resume/JobInstance đúng |
| TX-21 | Restart khác partition plan | Phải detect/không silently pass | Checkpoint contract được bảo vệ |
| TX-22 | External API trong chunk fail sau gửi | Side effect đã gửi không tự rollback | Outbox/compensation test |
| TX-23 | Outbox row + business row cùng transaction | Cả hai rollback cùng nhau khi throw | Retry relay sau commit đúng |
| TX-24 | Pool starvation khi hai worker transactions | Không mất dữ liệu | Deadline và pressure metrics |
| TX-25 | Multi-threaded step reader state race | Exact output không trùng/thiếu | Reader/StepExecution thread-safety |

### 23.1. Dữ liệu expected cho từng test

**Không hardcode `JobStatus=FAILED` cho mọi scenario.** Trong test có retry rồi thành công, job có thể `COMPLETED`. Trong test skip hợp lệ, job cũng có thể thành công theo policy. Trong test crash hard-kill, metadata có thể tạm `STARTED` cho tới khi recovery; không ép nó lập tức `FAILED` nếu hạ tầng không có cơ chế đó.

Với mỗi test nên ghi:

~~~text
inputSnapshot
expectedInitialBusinessState
failureBoundary / injectedException
expectedRollbackScope
expectedCommittedBusinessKeys
expectedStepExecutionStates
expectedRetries / skips
expectedEndStateAfterRestart
timeout / cleanup
~~~

### 23.2. Test rollback có nhiều kết quả hợp lệ không?

Ví dụ mất network đúng lúc COMMIT: **client không biết** server đã commit. Test không thể yêu cầu mọi lần inject network đều ra **cùng trạng thái trước khi kiểm tra DB**. Nhưng **sau reconciliation**, kết quả cuối phải thỏa invariant:

- Không có double business effect.
- Không bỏ sót valid business input.
- Metadata/retry state có thể khôi phục.
- Unknown commit outcome được phát hiện và xử lý bằng read-after-failure/unique key.

Test có thể có **hai nhánh thực tế** (commit hoặc rollback), nhưng cả hai phải dẫn tới **một final business outcome đúng** sau recovery.

## 24. Chia test suite theo CI gate

Không cần chạy fault injection nhiều process cho mỗi unit test. Nhưng cần biết lớp nào đang được kiểm tra:

| Gate | Công cụ | Tần suất gợi ý | Yêu cầu |
|---|---|---|---|
| **G1 Unit** | JUnit 5, mock writer/policy, pure functions | Mỗi PR | Exception classification, retry/skip business rules, partition ranges |
| **G2 JDBC transaction** | PostgreSQL Testcontainers + Spring Batch step | Mỗi PR | Writer throw-before-commit, partial chunks, metadata/data oracle |
| **G3 Concurrency** | Real PostgreSQL, threads/barriers | Mỗi PR quan trọng | A rollback/B commit, hot keys, pool, isolation |
| **G4 Messaging/remote** | Broker thật, shared JobRepository, ≥2 worker processes | Merge/release | Worker crash/redelivery, manager aggregation, stale worker |
| **G5 Resilience/load** | Staging fault proxy, chaos controls, benchmark | Định kỳ/release | Unknown commit, network partition, rolling deployment, retry storm |

Những cấp test là **đề xuất quy trình**, không phải khả năng Spring Batch có sẵn. Khi CI không có Docker, phải ghi **gate không chạy được** và giữ G2/G4 ở runner có container runtime; không thay một Testcontainers integration test bằng mock rồi tuyên bố fidelity tương đương.

### 24.1. Chống flaky bằng điều kiện thay vì sleep

- Sử dụng `CountDownLatch`/`CyclicBarrier`/test hook để chặn transactions đúng mốc.
- Dùng `Future.get(timeout)` hoặc Awaitility cho trạng thái repository/DB, với deadline hữu hạn.
- Tạo transaction riêng cho từng thread/process; không dùng một shared JDBC `Connection` tùy tiện.
- Chạy cùng immutable snapshot, schema/constraints và input ordering.
- Tránh race cleanup: worker cũ phải dừng trước khi xóa fixture/schema.
- Lưu fault point, DB SQLState, transaction status và process identity.
- Khi test timeout, giữ metadata/logs/DB wait state để phân tích, không chỉ tăng timeout.
- Không đặt performance p95 threshold quá cứng trên runner CI dùng chung.

### 24.2. Bảo vệ môi trường test

Fault hook, deliberate deadlock, connection kill và poison messages chỉ được bật trong **test/staging** với dữ liệu giả. Không xây một public endpoint có thể tự do kill worker, thay `BATCH_STEP_EXECUTION` hay làm rớt transaction của hệ thống production.

## 25. Runbook khi transaction rollback không như kỳ vọng

Một incident thường bắt đầu bằng một trong các biểu hiện:

- Job `FAILED` nhưng vẫn có output của chunk được cho là rollback.
- Worker retry cùng item và tạo double amount.
- Chunk rollback liên tục, Hikari pending/DB locks tăng.
- Job `COMPLETED` nhưng output thiếu valid business keys.
- Worker/broker reply trễ, manager không biết transaction business đã commit chưa.

### Bước 1 — Khóa phạm vi kiểm tra

Ghi `jobName`, identifying `JobParameters`, input snapshot/cutoff, `JobInstance`, `JobExecution`, worker `StepExecution` và tên partition. Nếu một worker cũ vẫn active, xác định ownership trước khi phát lại work.

### Bước 2 — Xác nhận điểm lỗi

Lỗi trước writer, trong JDBC batch, sau `executeBatch` trước COMMIT, trong COMMIT, hay sau COMMIT trước reply? **Đây là câu hỏi đầu tiên**, không phải “job có exception không?”. Nếu không biết mốc, không tự suy ra rollback.

### Bước 3 — Kiểm tra transaction manager và physical resource

- Step builder đang dùng `PlatformTransactionManager` nào?
- `JdbcTemplate`/EntityManager của writer trỏ vào datasource nào?
- Có auto-commit/connection thứ hai/`REQUIRES_NEW`/external API?
- Business DB và metadata DB có cùng local transaction không?
- Có custom listener gọi resource ngoài transaction?

Nếu sai manager, sửa wiring + tạo regression test “write then throw”; không chỉ đổi exception handling.

### Bước 4 — Đọc database ở transaction độc lập

So exact keys/amount/checksum của chunk lỗi và các chunks trước. Với PostgreSQL, dùng connection khác sau job/worker đã dừng để xác nhận **committed state**. Không chỉ đọc `writeCount` hoặc log SQL đã execute.

### Bước 5 — Phân tích fault-tolerance policy

Kiểm tra `retryLimit`, `skipLimit`, `noRollback`, exception classification và transaction propagation. Nếu DB transaction aborted, phải rollback trước retry; không tiếp tục gọi SQL trong cùng physical transaction bị lỗi.

### Bước 6 — Xem contention và resource pressure

Lấy `pg_stat_activity`/`pg_blocking_pids`, Hikari active/pending/acquire, DB CPU/WAL/IO và rollback/deadlock counters. Deadlock `40P01` hoặc serialization `40001` có thể là **kết quả concurrency** chứ không phải business validation error.

### Bước 7 — Chặn double side effect khi recovery

Trước khi restart/redispatch:

- Xác minh business rows đã commit.
- Đảm bảo writer có unique business keys/event ledger.
- Đánh giá external API/file/broker side effects đã xảy ra.
- Kiểm tra worker cũ còn hoạt động/stale request/lease/fencing.
- Đảm bảo input snapshot và partition plan không đổi.

Nếu commit outcome unknown, **reconcile trước khi retry**. Không dùng random `run.id` để ép một job mới khi mục tiêu là restart.

### Bước 8 — Restart theo lifecycle Spring Batch

Dùng API/JobOperator/JobRepository process phù hợp version và quyền vận hành; không sửa trực tiếp `BATCH_*` metadata. Giữ identifying parameters; khôi phục/replay các chunks chưa commit theo `ExecutionContext`/reader semantics. Với remote worker, theo dõi `StepExecution` cụ thể và manager aggregation.

### Bước 9 — Đối soát toàn bộ business output

Không chỉ kiểm tra count: dùng `EXCEPT` hai chiều, checksum/aggregate và unique constraints. Nếu một row bị thiếu và một row khác bị trùng, tổng vẫn có thể bằng nhau. Nếu output transform/filter, so expected transformed set.

### Bước 10 — Khôi phục tải từ từ và thêm regression

Nếu lỗi do DB lock/pool starvation, giới hạn worker concurrency/partition in-flight và retry storm trong lúc phục hồi. Sau khi output đúng, lưu failure boundary/SQLState/transaction topology và tạo test deterministic để không tái diễn.

## 26. Những anti-pattern nguy hiểm

| Anti-pattern | Vì sao test có thể sai | Cách sửa |
|---|---|---|
| Chỉ assert `JobExecution.FAILED` | Không biết business DB đã commit gì | Query committed keys từ connection độc lập |
| Đánh dấu JUnit method `@Transactional` rồi query 0 rows | Test transaction có thể che side effect thật | Commit fixture riêng, không auto-rollback test oracle |
| Mock `JdbcTemplate.update` rồi tuyên bố rollback | Mock không có physical transaction | Testcontainers PostgreSQL |
| Catch exception trong writer rồi không throw | Framework có thể COMMIT chunk lỗi | Phân loại lỗi, propagate/mark rollback theo contract |
| `REQUIRES_NEW` cho mọi SQL để “không mất dữ liệu” | Inner commit thoát khỏi rollback chunk | Ghi chung transaction hoặc intentional separate ledger |
| Gọi `flush()` là COMMIT | Flush có thể rollback | Test sau transaction boundary |
| Dùng `BatchUpdateException.updateCounts` như committed rows | SQL executed ≠ transaction durable | Read DB after transaction resolution |
| Coi job FAILED là rollback mọi chunks | Các chunk trước đã COMMIT | Test partial progress và restart |
| Coi một partition fail rollback toàn cluster | Các workers có transactions riêng | Test P0 failed/P1 completed cùng lúc |
| Đếm `rollbackCount` thành số row rollback | Counter là framework transaction metric | Query affected committed business keys |
| Dùng `Thread.sleep` để tạo race | Flaky/không chứng minh overlap | Latch/barrier/fault hook |
| Dùng một JDBC Connection/EntityManager across threads | Không đảm bảo thread safety/tx isolation | TransactionTemplate/thr-bound resources |
| Dùng H2 cho PostgreSQL deadlock/SQLState behavior | Semantics khác | Real PostgreSQL integration |
| Dùng `run.id` ngẫu nhiên khi “restart” | Tạo JobInstance mới, bỏ checkpoint | Same identifying parameters |
| Dùng `stepExecutionId` làm business dedupe key | ID đổi qua restart | `snapshotKey + businessEventId` |
| Cho broker ACK trước durable handoff không kiểm tra | Mất message khi worker crash | Test ACK/replay/outbox |
| Test chỉ có 1 worker nhưng gọi là concurrency test | Không tạo overlap | ≥2 threads/processes và evidence |
| Đổi partition plan khi restart | Checkpoint và work ownership lệch | Stable plan hoặc migration riêng |
| Chỉnh trực tiếp bảng `BATCH_*` để ép success | Phá lifecycle/version/context | Restart API, reconcile |
| Đặt timeout quá nhỏ trong mọi CI run | Flaky do runner contention | Functional deadline hợp lý, performance benchmark riêng |

## 27. Checklist trước khi đưa rollback policy lên production

- [ ] Đã vẽ rõ transaction boundary **chunk / StepExecution / JobExecution**, không nhầm job FAILED với job-wide rollback.
- [ ] Biết Spring Batch step sử dụng **transaction manager** nào.
- [ ] Writer JDBC/JPA tham gia đúng transaction-bound datasource/EntityManager.
- [ ] Không dùng auto-commit connection riêng một cách vô tình.
- [ ] Đã test writer throw **sau khi gửi SQL, trước COMMIT** trên database thật.
- [ ] Đã kiểm tra business data sau rollback từ connection/transaction khác.
- [ ] Đã test chunk 1 COMMIT, chunk 2 rollback, không làm mất chunk 1.
- [ ] Đã test lỗi reader, processor và writer theo policy riêng.
- [ ] Đã test `retry/skip/noRollback` và exception classification/rollback semantics.
- [ ] Không retry SQL trong một PostgreSQL transaction đã bị aborted.
- [ ] Đã kiểm tra trạng thái metadata và business data **độc lập**.
- [ ] Đã phân biệt `getRollbackCount` với số business rows bị rollback.
- [ ] Đã kiểm tra `writeCount` không bị dùng làm số row mới đã commit.
- [ ] Đã test `EntityManager.flush()` rồi throw, không nhầm flush với commit.
- [ ] Nếu dùng nhiều datasources, đã kiểm tra business/metadata transaction atomicity thực tế.
- [ ] Đã kiểm tra `REQUIRES_NEW`, savepoints/nested transaction nếu ứng dụng dùng.
- [ ] External API/email/file/broker side effects không được coi là JDBC-transactional.
- [ ] Nếu dùng outbox, business change và outbox intent được ghi cùng transaction.
- [ ] Có idempotency key/unique business key cho retry/restart/redelivery.
- [ ] Duplicate key khác payload có contract phát hiện và xử lý, không chỉ `DO NOTHING`.
- [ ] Đã test lost update/hot row concurrent transactions trên PostgreSQL thật.
- [ ] Đã test ít nhất hai threads/transactions overlap bằng barrier, không dựa vào sleep.
- [ ] Multi-threaded reader/writer/processor được đánh giá thread safety.
- [ ] `@StepScope` được hiểu là per-StepExecution, không tự là per-chunk-thread.
- [ ] Parallel steps/partitions có input coverage non-overlap và output reconciliation.
- [ ] Remote partitioning có shared `JobRepository`, đúng step names và execution identity.
- [ ] Đã test worker A rollback, worker B commit và manager aggregation.
- [ ] Với remote chunking, đã kiểm tra manager reader checkpoint, worker write và broker replay.
- [ ] Đã test crash trước COMMIT và sau COMMIT **riêng biệt**.
- [ ] Trường hợp COMMIT outcome unknown được giải quyết bằng reconciliation/idempotency.
- [ ] Không ACK broker trước durable handoff nếu policy không cho phép mất work.
- [ ] Restart giữ cùng identifying `JobParameters`, snapshot và partition plan.
- [ ] Không sửa trực tiếp `BATCH_JOB_EXECUTION`/`BATCH_STEP_EXECUTION` để ép status.
- [ ] Có giới hạn retry/backoff/jitter, tránh lock/retry storm.
- [ ] Đã test thiếu/mất reply, duplicate delivery và stale worker trên topology phù hợp.
- [ ] Có metric rollback/retry/lock/commit latency, Hikari pending và broker redelivery.
- [ ] Không dùng JUnit `@Transactional` làm test oracle mơ hồ.
- [ ] CI tách unit, JDBC integration, concurrency, multi-process remote và fault injection.
- [ ] Có timeout hữu hạn, fault-hook xác định, logs/trace và cleanup không phá fixture khác.
- [ ] Sau recovery, exact business keys/checksum/aggregate đúng theo input snapshot.

## 28. Bài tập thực hành

### Bài tập 1 — Chunk rollback cơ bản

Từ code `ChunkRollbackIT` phần 6, cho writer `INSERT` ba ID `1,2,3` rồi throw. Chạy Testcontainers PostgreSQL và assert:

1. `JobExecution.status == FAILED`.
2. `StepExecution.rollbackCount > 0` theo cấu hình.
3. `SELECT count(*) FROM tx_probe == 0` sau khi job kết thúc.
4. Nếu bỏ `throw`, job `COMPLETED` và bảng có đúng ba ID.

Giải thích vì sao phần assert (3) cần đọc từ transaction độc lập và không thể thay bằng Mockito `verify(jdbc.update(...))`.

### Bài tập 2 — Một chunk commit, chunk tiếp theo rollback

Input `1..7`, chunk size 3. Fail sau khi writer đã gửi SQL cho chunk chứa ID 5. Xác nhận:

~~~text
Final business keys before restart: {1, 2, 3}
Job: FAILED
Keys 4, 5, 6, 7: không có trong output
~~~

Sau đó dùng reader có checkpoint thực và restart cùng identifying params; đầu ra cuối phải chứa đúng `1..7`. Không dùng `ListItemReader` singleton từ test một lần làm bằng chứng checkpoint/restart.

### Bài tập 3 — Phá cấu hình transaction manager có chủ đích

Trên staging, cấu hình business writer dùng một datasource khác với chunk transaction manager. Cho writer `INSERT` rồi throw. Quan sát business rows có thể còn vì auto-commit hoặc transaction riêng. Sửa wiring để writer tham gia đúng transaction rồi chạy lại; test phải chuyển từ FAIL sang PASS.

**Chỉ thực hiện trên test database**, không đổi transaction manager của production để tạo lỗi.

### Bài tập 4 — JDBC batch và constraint violation

Tạo unique constraint trên `(snapshot_key,payment_id)`. Cho writer ghi một chunk 100 items, trong đó item thứ 60 cố tình vi phạm unique key. Xem `BatchUpdateException`/SQLState tùy driver, rollback toàn transaction và query DB sau failure. Trả lời: vì sao update counts của JDBC không chứng minh có 59 rows mới đã commit?

### Bài tập 5 — JPA flush sau đó rollback

Dùng `JpaItemWriter` hoặc custom writer với `EntityManager.persist()` và `flush()`. Inject exception **sau flush trước commit**. Query bằng EntityManager/connection mới để xác nhận không có row. Đo thêm Hibernate SQL logs, giải thích vì sao SQL đã execute mà row vẫn không tồn tại sau rollback.

### Bài tập 6 — Hai transactions đồng thời

Áp dụng `CountDownLatch`/`TransactionTemplate` phần 10, thread A insert ID 101 rồi rollback, thread B insert ID 202 rồi commit. Kiểm tra khi cả hai chưa commit, query độc lập chưa thấy row nào; cuối cùng chỉ có ID 202. Thử giảm JDBC pool xuống quá thấp để quan sát **pool starvation** và sửa capacity test.

### Bài tập 7 — Lost update và double application

Hai workers nhận events khác nhau cùng cập nhật `account_id=42`. Tạo race bằng barrier:

- Cách sai: `SELECT balance` rồi `UPDATE balance=<computed>`.
- Cách tốt hơn: `UPDATE balance = balance + delta` trong DB transaction.
- Cách chống duplicate replay: event ledger unique `(snapshot,event_id)` và balance update **cùng transaction**.

Viết test chứng minh ba thiết kế khác nhau về lost update và duplicate delivery.

### Bài tập 8 — Deadlock có thể tái hiện

Trên PostgreSQL staging tạo hai account rows. Thread A lock/update account 1 rồi chờ barrier; thread B lock/update account 2 rồi chờ barrier. Sau barrier, A update account 2 còn B update account 1. Quan sát `40P01` ở một transaction, xác nhận rollback, sau đó retry toàn transaction với max attempts/backoff. Không dùng sleep để “canh” deadlock.

### Bài tập 9 — Retry và skip policy

Chọn một `InvalidPaymentException` permanent, một transient SQL exception và cấu hình:

~~~java
.faultTolerant()
.retry(TransientDataAccessException.class)
.retryLimit(3)
.skip(InvalidPaymentException.class)
.skipLimit(2)
~~~

Viết ba testcase: transient failure một lần rồi success, một invalid item được skip, ba invalid items vượt skip limit. Đối soát exact output, metadata skip/retry/rollback và khả năng writer side effect replay. Phân biệt job `COMPLETED` hợp lệ với job `FAILED` sau limit.

### Bài tập 10 — Side effect không rollback

Writer insert business row, sau đó gửi một test message tới HTTP service giả rồi throw. Query DB để thấy row rollback nhưng fake service đã nhận message. Thay direct send bằng transactional outbox, test writer rollback làm **cả business row lẫn outbox row** mất; sau success commit, relay thử gửi lại và consumer dedupe đúng.

### Bài tập 11 — Remote partitioning rollback thật

Dùng PostgreSQL + broker Testcontainers, manager và hai worker processes. Tạo bốn partitions theo range:

~~~text
P0 [1, 252)
P1 [252, 503)
P2 [503, 754)
P3 [754, 1004)
~~~

Cho worker xử lý P2 throw trước commit khi gặp ID 600, còn P0/P1/P3 tiếp tục theo policy. Kiểm tra output những chunk đã commit, metadata P2 `FAILED`, không tuyên bố toàn job `COMPLETED`. Restart cùng JobInstance rồi so exact 1.003 keys/total amount.

### Bài tập 12 — Remote chunking và lost reply

Manager gửi một chunk 100 items, worker COMMIT thành công nhưng reply bị giữ lại/cắt kết nối. Manager timeout rồi có thể retry theo contract. Dùng writer idempotent để output chỉ có 100 keys, kiểm tra `StepExecution`/message correlation; không dùng broker ACK rate làm committed business rate.

### Bài tập 13 — Kết quả COMMIT chưa chắc chắn

Trên một test DB và fault proxy, cắt kết nối đúng khi COMMIT đang thực thi. Test harness không được mặc định rollback. Sau khi kết nối trở lại:

1. Tra business keys bằng connection mới.
2. Nếu đã commit, không phát lại business effect.
3. Nếu chưa commit, replay idempotently.
4. Trong cả hai nhánh, final business output phải đúng.

Nêu rõ điều gì được instrument để phân biệt **confirmed commit**, **confirmed rollback** và **unknown outcome**.

### Bài tập 14 — Metadata DB tách business DB

Tạo hai PostgreSQL datasources/test schemas độc lập: một dành cho `JobRepository`, một cho business output. Inject lỗi ở các mốc:

- Business SQL execute, chưa commit.
- Business đã commit, metadata chưa kịp phản ánh.
- Worker đã ghi metadata, reply bị mất.

Với mỗi case, viết test expected metadata/business state và recovery policy. Giải thích vì sao một `@Transactional` ở manager không tự biến ba resources thành distributed transaction nguyên tử.

### Bài tập 15 — Viết runbook từ incident

Một job có 16 partitions, sau khi tăng concurrency, logs báo:

~~~text
worker-A: SQLSTATE 40P01 (deadlock)
worker-B: StepExecution COMPLETED
worker-C: Hikari acquisition timeout
manager: 2 partitions FAILED
business DB: một số unique events đã tồn tại
broker: redelivery count tăng
~~~

Xác định:

- Partition nào có chunk committed và chunk nào rollback?
- Có thể tăng pool size ngay không, khi DB đang chờ locks?
- Cần idempotency/ownership nào trước khi redispatch?
- Làm sao restart đúng `JobInstance`?
- Bằng chứng nào cho phép báo completed một cách hợp lệ?

Đề xuất regression test deterministic để phát hiện root cause chứ không chỉ tăng timeout.

### Câu hỏi tự kiểm tra

- Chunk rollback khác toàn job rollback thế nào?
- `JobExecution.FAILED` có chứng minh toàn bộ output đã biến mất không?
- Vì sao `JdbcBatchItemWriter.write`/`executeBatch` thành công chưa đủ chứng minh commit?
- JPA `flush()` khác `COMMIT` ở đâu?
- Một transaction A rollback có hoàn tác transaction B đã commit không?
- Vì sao test `@Transactional` ở JUnit có thể làm oracle sai?
- `StepExecution.rollbackCount` có phải số row rollback không?
- Khi PostgreSQL báo `40P01` hoặc `40001`, retry ở phạm vi nào?
- Tại sao `REQUIRES_NEW` có thể làm audit còn lại sau outer rollback?
- Vì sao HTTP/email và broker ACK không nằm trong JDBC chunk transaction mặc định?
- Khi commit response bị mất, làm sao biết output đã có?
- Vì sao business dedupe key phải ổn định qua `StepExecution` attempts?
- `@StepScope` có làm reader tự thread-safe giữa nhiều chunk threads không?
- Remote partitioning và remote chunking khác nhau về chỗ đặt reader/checkpoint thế nào?
- Vì sao phải giữ partition plan khi restart?
- Thế nào là một test rollback được coi là PASS cả về dữ liệu và metadata?

## 29. Tổng kết

**Test transaction rollback** trong Spring Batch là kiểm tra **physical commit boundary và tính đúng của dữ liệu** khi có lỗi, không chỉ xác nhận một exception đã xuất hiện. Trong chunk-oriented step, rollback thường giới hạn ở **transaction của chunk lỗi**; các chunks đã commit, các worker/partition độc lập và external side effects không được hoàn tác tự động chỉ vì toàn job `FAILED`.

Một chiến lược đáng tin cậy bắt đầu bằng **writer execute SQL rồi throw trước COMMIT trên PostgreSQL thật**, xác minh output qua connection khác; tiếp tục với partial commit nhiều chunks, concurrent transactions, deadlock/isolation, retry/skip, metadata/business DB tách biệt, lost ACK và worker crash. Khi restart, giữ identifying parameters, input snapshot, partition plan và writer idempotent để business outcome chỉ được áp dụng đúng theo contract.

**Tiêu chí cuối cùng:** sau rollback, replay hoặc restart, mỗi business event hợp lệ được xử lý đúng số lần về mặt nghiệp vụ; không có tác động ngoài transaction bị che giấu, không có dữ liệu bị bỏ sót và trạng thái `JobRepository` có thể giải thích bằng bằng chứng transaction thực tế.
