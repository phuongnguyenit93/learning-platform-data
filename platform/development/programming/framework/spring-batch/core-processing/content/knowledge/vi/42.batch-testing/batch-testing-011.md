# Kiểm thử restart trong Spring Batch

## 1. Mục tiêu của bài học

Trong hệ thống batch, lỗi mạng, dữ liệu không hợp lệ, database tạm thời không sẵn sàng hoặc tiến trình bị dừng có thể khiến một **Job** thất bại sau khi đã xử lý thành công một phần dữ liệu. Chỉ kiểm thử rằng Job chạy từ đầu đến cuối với trạng thái `COMPLETED` là chưa đủ: hệ thống còn phải **khởi động lại đúng phần chưa hoàn thành**, giữ nguyên thành quả đã commit và không tạo ra dữ liệu trùng.

Sau bài học này, bạn có thể:

- Phân biệt chạy lại cùng **JobInstance** với tạo một JobInstance mới.
- Thiết kế kịch bản cho Job thất bại có chủ đích, sau đó restart bằng đúng **JobParameters**.
- Kiểm chứng checkpoint của reader, ranh giới transaction/chunk và dữ liệu đầu ra.
- Kiểm tra cách xử lý step đã hoàn thành, job không cho restart và trạng thái bất thường.
- Xây dựng bài kiểm thử tích hợp với `spring-batch-test`, JUnit Jupiter và JobRepository lưu trong cơ sở dữ liệu.

## 2. Restart thực sự có nghĩa gì?

Spring Batch lưu thông tin chạy trong **JobRepository**. Các khái niệm chính:

| Khái niệm | Ý nghĩa đối với kiểm thử restart |
| --- | --- |
| `Job` | Định nghĩa quy trình, tên Job và các Step. |
| `JobInstance` | Một lần xử lý *theo nghĩa nghiệp vụ*, được xác định bởi tên Job và các **identifying JobParameters**. |
| `JobExecution` | Một lần cố gắng chạy JobInstance; một JobInstance có thể có nhiều JobExecution. |
| `StepExecution` | Một lần cố gắng chạy một Step trong một JobExecution. |
| `ExecutionContext` | Trạng thái được lưu để Step/Job có thể tiếp tục, ví dụ vị trí đọc đã checkpoint. |
| `BatchStatus` | Trạng thái thực thi như `STARTED`, `FAILED`, `STOPPED`, `COMPLETED`. |

Đối với một Job tên `importOrdersJob`, giả sử chỉ dùng tham số định danh `businessDate=2026-11-16`:

~~~text
Job: importOrdersJob
JobParameters: businessDate=2026-11-16 (identifying)
        |
        v
JobInstance #42
   |
   +-- JobExecution #100 -> FAILED
   |       +-- StepExecution loadStep -> FAILED
   |
   +-- JobExecution #101 -> COMPLETED    (restart)
           +-- StepExecution loadStep -> COMPLETED
~~~

Điểm cần chứng minh trong bài test:

1. Hai lần gọi có **cùng tên Job** và **cùng tập tham số định danh**.
2. Hai lần chạy có **JobExecution ID khác nhau**, nhưng **JobInstance ID giống nhau**.
3. Lần đầu kết thúc `FAILED`; lần sau kết thúc `COMPLETED`.
4. Phần dữ liệu đã commit không bị mất; phần chưa commit được xử lý lại; dữ liệu cuối cùng đúng và không trùng.

**Cạm bẫy:** `JobOperatorTestUtils.startJob()` (Spring Batch 6) hoặc `JobLauncherTestUtils.launchJob()` (Spring Batch 5) khi **không truyền tham số** có thể tự tạo tham số ngẫu nhiên để chạy JobInstance mới. Muốn kiểm thử restart, hãy **truyền chính xác cùng đối tượng `JobParameters` cho cả hai lần**. Nếu thêm `run.id` hay timestamp định danh mới ở lần hai, đó là một JobInstance khác, không phải restart.

Một JobInstance đã `COMPLETED` thường không thể được khởi chạy lại với cùng tham số định danh: Spring Batch báo lỗi kiểu `JobInstanceAlreadyCompleteException`. Ngược lại, Job bị `FAILED` có thể restart nếu cấu hình cho phép và trạng thái metadata còn hợp lệ.

### Trạng thái và hành vi cần phân biệt

| Kết quả lần trước | Lần chạy tiếp theo với cùng tham số | Điều cần kiểm thử |
| --- | --- | --- |
| `FAILED` | Thông thường có thể restart | Có JobExecution mới, tiếp tục theo checkpoint. |
| `STOPPED` | Có thể restart sau khi đã dừng hẳn | Không khởi động lại trong lúc Job còn `STOPPING`. |
| `COMPLETED` | Bị từ chối | Không phát sinh ghi dữ liệu lần nữa. |
| `STARTING`/`STARTED` | Job được coi là còn chạy | Không tự ý mở execution đồng thời của cùng JobInstance. |
| `ABANDONED` | Không restart được theo cơ chế thông thường | Cần quy trình khắc phục riêng. |
| Job có `preventRestart()` | Từ chối restart sau thất bại | Nhận `JobRestartException` hoặc lỗi tương ứng từ tầng gọi. |

**Lưu ý sự cố mất điện/kill tiến trình:** metadata có thể còn `STARTED` vì tiến trình không kịp ghi `FAILED`. Không nên chỉnh trạng thái metadata tùy tiện chỉ để bài test qua. Trong vận hành thực tế phải xác minh tiến trình cũ đã dừng, tính nhất quán của dữ liệu và checkpoint trước khi đưa execution về trạng thái phù hợp cho phục hồi.

## 3. Cần kiểm chứng gì ở ranh giới chunk?

Xét Step đọc năm bản ghi theo thứ tự `1, 2, 3, 4, 5`, dùng `chunk(2)`, với lỗi được chèn vào lúc xử lý bản ghi số `3`:

~~~text
Execution 1:
  read 1,2 -> write 1,2 -> COMMIT         (checkpoint sau 2)
  read 3   -> processor ném exception
             -> chunk hiện tại ROLLBACK
  Job = FAILED
  output đã commit = [1,2]

Execution 2 (cùng JobParameters):
  mở reader từ checkpoint trước đó
  read 3,4 -> write 3,4 -> COMMIT
  read 5   -> write 5   -> COMMIT
  Job = COMPLETED
  output cuối = [1,2,3,4,5]
~~~

Khi reader là `ItemStream` có lưu state, vị trí đã commit được ghi vào `StepExecution.ExecutionContext`. Khi restart, reader có thể dùng vị trí đó để bắt đầu lại đúng nơi cần. Với `JdbcCursorItemReader`, cần câu truy vấn có **thứ tự ổn định**, ví dụ `ORDER BY id`, và bật `saveState(true)` (đây cũng là mặc định của reader này). Nếu nguồn dữ liệu thay đổi giữa các lần chạy, offset đã lưu có thể không còn trỏ đến cùng bản ghi; kiểm thử cần dùng snapshot ổn định hoặc chiến lược đọc dựa trên khóa/checkpoint thích hợp.

Đặc biệt, **restartability không tự động đồng nghĩa với exactly-once** ở mọi hệ thống. Nếu writer gửi email, gọi HTTP API hay ghi sang hệ thống khác transaction với JobRepository, một phần side effect có thể đã xảy ra ngay cả khi metadata chưa commit. Cần bổ sung idempotency key, unique constraint, upsert, outbox hoặc cơ chế đối soát phù hợp.

## 4. Chuẩn bị môi trường kiểm thử tích hợp

Ví dụ dưới đây minh họa **Spring Batch 6.x**, Spring Boot, JUnit Jupiter và cơ sở dữ liệu H2 trong cùng một test context. Nếu dùng Spring Batch 5.x, xem phần điều chỉnh API ở cuối bài.

Cần có các dependency tương ứng với phiên bản Spring Boot đang dùng: Spring Batch, Spring JDBC, `spring-batch-test` (test scope), `spring-boot-starter-test` và H2 (test/runtime scope). Spring Boot quản lý phiên bản phụ thuộc thông qua BOM. Nên dùng một **JobRepository JDBC thật** để test checkpoint và metadata; repository không lưu state bền vững sẽ không chứng minh được hành vi restart.

Trong `src/test/resources/application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:restartdb;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

spring.batch.jdbc.initialize-schema=always
spring.batch.job.enabled=false
spring.sql.init.mode=always
spring.sql.init.schema-locations=classpath:schema.sql
~~~

Tệp `src/test/resources/schema.sql` chỉ tạo bảng nghiệp vụ; Spring Batch khởi tạo riêng các bảng `BATCH_*`:

~~~sql
CREATE TABLE source_item (
    id INTEGER PRIMARY KEY
);

CREATE TABLE processed_item (
    id INTEGER PRIMARY KEY
);
~~~

Tắt tự động chạy Job lúc khởi động test (`spring.batch.job.enabled=false`) để mỗi execution đều do test chủ động tạo. **Không đặt `@Transactional` trên toàn bộ phương thức integration test**: test cần nhìn thấy transaction thực đã commit hoặc rollback của từng chunk. Khi kiểm tra restart sau khi khởi động lại JVM, hãy thay H2 in-memory bằng một database tồn tại qua hai tiến trình.

## 5. Ví dụ Job có điểm chèn lỗi

Cấu hình sau có một reader JDBC lưu vị trí, processor có thể cố ý ném lỗi khi gặp ID `3`, và writer ghi dữ liệu qua `JdbcTemplate`. Tại lần chạy đầu, hai bản ghi đầu được commit; khi tắt cờ gây lỗi rồi restart, Step tiếp tục từ bản ghi `3`.

`RestartJobConfig.java`:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;
import javax.sql.DataSource;

import org.springframework.batch.core.job.Job;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.Step;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.infrastructure.item.database.JdbcCursorItemReader;
import org.springframework.batch.infrastructure.item.database.builder.JdbcCursorItemReaderBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration(proxyBeanMethods = false)
public class RestartJobConfig {

    @Bean
    AtomicBoolean failOnThree() {
        return new AtomicBoolean(false);
    }

    @Bean
    @StepScope
    JdbcCursorItemReader<Integer> orderedReader(DataSource dataSource) {
        return new JdbcCursorItemReaderBuilder<Integer>()
                .name("orderedReader")
                .dataSource(dataSource)
                .sql("SELECT id FROM source_item ORDER BY id")
                .rowMapper((rs, rowNum) -> rs.getInt("id"))
                .saveState(true)
                .build();
    }

    @Bean
    Step loadStep(JobRepository jobRepository,
                  PlatformTransactionManager transactionManager,
                  JdbcCursorItemReader<Integer> orderedReader,
                  JdbcTemplate jdbcTemplate,
                  AtomicBoolean failOnThree) {

        return new StepBuilder("loadStep", jobRepository)
                .<Integer, Integer>chunk(2)
                .transactionManager(transactionManager)
                .reader(orderedReader)
                .processor(id -> {
                    if (failOnThree.get() && id == 3) {
                        throw new IllegalStateException("Injected failure at id=3");
                    }
                    return id;
                })
                .writer(chunk -> {
                    for (Integer id : chunk.getItems()) {
                        jdbcTemplate.update(
                            "INSERT INTO processed_item(id) VALUES (?)", id);
                    }
                })
                .build();
    }

    @Bean
    Job importJob(JobRepository jobRepository, Step loadStep) {
        return new JobBuilder("importJob", jobRepository)
                .start(loadStep)
                .build();
    }
}
~~~

Các chi tiết quan trọng:

- Reader được khai báo `@StepScope` để mỗi StepExecution nhận một reader mới với trạng thái mở từ `ExecutionContext`. Tên reader ổn định giúp giữ key checkpoint.
- `ORDER BY id` làm thứ tự đọc xác định trong bộ dữ liệu test.
- `chunk(2)` tạo ranh giới commit để kiểm chứng phần đã ghi trước khi lỗi.
- Lỗi nằm ở **processor** trước khi writer của chunk chứa `3` thực hiện; không phụ thuộc vào lỗi mạng ngẫu nhiên.
- Writer dùng cùng transaction manager/data source của Step, nên rollback chunk sẽ rollback các lần `INSERT` của chunk đó. Bảng đích có primary key để lỗi ghi trùng dễ bị phát hiện.
- Cờ `AtomicBoolean` chỉ phục vụ **fault injection trong test**, không phải cơ chế nghiệp vụ trong production.

## 6. Viết integration test: FAILED → restart → COMPLETED

Giả sử có ứng dụng Spring Boot cấu hình Batch và đã import `RestartJobConfig`. Test dưới đây dùng `@SpringBatchTest` để nhận `JobOperatorTestUtils` và `JobRepositoryTestUtils`. Nếu dự án có nhiều Job bean, phải chỉ rõ Job cần kiểm thử bằng `@Qualifier` rồi truyền cho utility.

`RestartJobIT.java` (thay `YourBatchApplication.class` bằng lớp application của dự án, bảo đảm `RestartJobConfig` được nạp vào test context):

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.job.Job;
import org.springframework.batch.core.job.JobExecution;
import org.springframework.batch.core.job.parameters.JobParameters;
import org.springframework.batch.core.job.parameters.JobParametersBuilder;
import org.springframework.batch.core.step.StepExecution;
import org.springframework.batch.test.JobOperatorTestUtils;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.*;

@SpringBatchTest
@SpringBootTest(classes = YourBatchApplication.class)
class RestartJobIT {

    @Autowired
    private JobOperatorTestUtils jobTestUtils;

    @Autowired
    private JobRepositoryTestUtils repositoryTestUtils;

    @Autowired
    @Qualifier("importJob")
    private Job importJob;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private AtomicBoolean failOnThree;

    @BeforeEach
    void prepare() {
        jobTestUtils.setJob(importJob);
        failOnThree.set(false);

        // Dọn metadata chỉ trong database test; không xóa metadata thật.
        repositoryTestUtils.removeJobExecutions();

        jdbc.update("DELETE FROM processed_item");
        jdbc.update("DELETE FROM source_item");
        for (int id = 1; id <= 5; id++) {
            jdbc.update("INSERT INTO source_item(id) VALUES (?)", id);
        }
    }

    @Test
    void restartResumesAfterCommittedChunkWithoutDuplicates() throws Exception {
        JobParameters params = new JobParametersBuilder()
                .addString("businessDate", "2026-11-16")
                .toJobParameters();

        // Execution đầu tiên: fail tại ID=3, sau khi chunk [1,2] commit.
        failOnThree.set(true);
        JobExecution first = jobTestUtils.startJob(params);

        assertEquals(BatchStatus.FAILED, first.getStatus());
        assertEquals(2, jdbc.queryForObject(
                "SELECT COUNT(*) FROM processed_item", Integer.class));

        // Restart: dùng CHÍNH XÁC cùng params và metadata còn lưu.
        failOnThree.set(false);
        JobExecution restarted = jobTestUtils.startJob(params);

        assertEquals(BatchStatus.COMPLETED, restarted.getStatus());
        assertNotEquals(first.getId(), restarted.getId());
        assertEquals(first.getJobInstance().getInstanceId(),
                     restarted.getJobInstance().getInstanceId());

        // Kết quả nghiệp vụ phải đầy đủ, không ghi trùng.
        List<Integer> ids = jdbc.queryForList(
                "SELECT id FROM processed_item ORDER BY id", Integer.class);
        assertEquals(List.of(1, 2, 3, 4, 5), ids);

        // Lần restart chỉ đọc lại ba item chưa commit.
        StepExecution resumedStep =
                restarted.getStepExecutions().iterator().next();
        assertEquals(BatchStatus.COMPLETED, resumedStep.getStatus());
        assertEquals(3L, resumedStep.getReadCount());
    }
}
~~~

**Vì sao cần nhiều assertion như vậy?** Chỉ kiểm `restarted.getStatus() == COMPLETED` có thể cho kết quả xanh ngay cả khi bạn vô tình tạo JobInstance mới, đọc lại cả nguồn, hoặc ghi dữ liệu trùng mà không phát hiện. Test tốt cần chứng minh đồng thời **cùng instance**, **execution mới**, **checkpoint được sử dụng**, và **kết quả nghiệp vụ chính xác**.

Nếu dự án không dùng Spring Boot, có thể thay `@SpringBootTest` bằng `@SpringJUnitConfig` và cấu hình rõ `DataSource`, `JobRepository`, transaction manager, batch infrastructure, schema; phần ý tưởng và assertion không thay đổi.

### Đọc metadata để quan sát

Các bảng thường gặp của JDBC JobRepository:

- `BATCH_JOB_INSTANCE`: một dòng cho JobInstance theo tập tham số định danh.
- `BATCH_JOB_EXECUTION`: hai dòng riêng biệt cho lần fail và lần restart.
- `BATCH_STEP_EXECUTION`: trạng thái, số lượng đọc/ghi, rollback/commit theo từng StepExecution.
- `BATCH_STEP_EXECUTION_CONTEXT`: checkpoint và dữ liệu phục hồi của Step.
- `BATCH_JOB_EXECUTION_PARAMS`: thông tin JobParameters.

Ví dụ câu SQL quan sát các execution trong môi trường test (tên cột cụ thể theo schema Spring Batch của phiên bản đang chạy):

~~~sql
SELECT ji.JOB_NAME,
       je.JOB_INSTANCE_ID,
       je.JOB_EXECUTION_ID,
       je.STATUS,
       je.EXIT_CODE
FROM BATCH_JOB_INSTANCE ji
JOIN BATCH_JOB_EXECUTION je
  ON ji.JOB_INSTANCE_ID = je.JOB_INSTANCE_ID
WHERE ji.JOB_NAME = 'importJob'
ORDER BY je.JOB_EXECUTION_ID;
~~~

Kỳ vọng: **hai execution ID**, **một instance ID**, lần đầu `FAILED`, lần sau `COMPLETED`. Có thể xem `BATCH_STEP_EXECUTION` để đối chiếu `READ_COUNT`, `WRITE_COUNT`, `COMMIT_COUNT` và `ROLLBACK_COUNT`; không nên đóng đinh số lần commit nội bộ nếu chưa xác định chính xác logic Step và phiên bản sử dụng.

## 7. Ma trận các kịch bản restart nên kiểm thử

| Kịch bản | Cách gây điều kiện | Điều cần khẳng định |
| --- | --- | --- |
| Thất bại trước commit đầu tiên | Ném lỗi ở item `1` | Không có dữ liệu đích đã commit; restart xử lý từ đầu. |
| Thất bại sau ít nhất một commit | Ném lỗi ở item `3` với chunk size `2` | Dữ liệu `1,2` giữ nguyên; restart xử lý `3,4,5`. |
| Lỗi bên trong writer | Ném lỗi khi ghi chunk thứ hai | Chunk lỗi rollback; không có ghi dở dang trong cùng transaction. |
| Hai Step, Step A đã hoàn thành, Step B lỗi | Cố ý fail tại Step B | Restart mặc định bỏ qua Step A đã `COMPLETED`, chạy lại Step B. |
| `allowStartIfComplete(true)` | Đặt trên Step A | Step A được chạy lại khi restart Job; dữ liệu/side effect của A phải an toàn. |
| `preventRestart()` | Cho Job fail rồi gọi lại cùng params | Framework từ chối restart. |
| `startLimit(n)` | Gây fail lặp tới giới hạn start của Step | Bị từ chối khi vượt số lần cho phép, không âm thầm tạo execution thứ n+1. |
| Job đã `COMPLETED` | Chạy lại cùng tham số định danh | Không chạy lại và không thay đổi bảng đích. |
| Thay tham số định danh | Đổi `businessDate` | Tạo JobInstance mới; không được lấy làm bằng chứng của restart. |
| Tạm dừng có kiểm soát | Yêu cầu stop, đợi `STOPPED` | Chỉ restart sau khi Step/Job đã dừng ổn định. |
| Nguồn có bản ghi lỗi cố định | Không gỡ dữ liệu lỗi | Restart lại fail đúng chỗ hoặc theo cấu hình skip/retry; không báo hoàn tất giả. |
| Thay đổi nguồn giữa hai lần chạy | Chèn/xóa bản ghi trước vị trí đọc | Chứng minh giải pháp vẫn xác định được bản ghi cần xử lý, hoặc ghi rõ điều kiện nguồn phải bất biến. |

Một số chiến lược cần test riêng:

- **Skip/retry:** retry xử lý lại cùng item trong *một execution*, còn restart tạo *execution mới* sau thất bại. Test tách hai hành vi; kiểm cả skip count, retry/rollback và kết quả cuối. Một lỗi được cấu hình skip có thể khiến Job `COMPLETED`, vì vậy không dùng nó để mô phỏng `FAILED` nếu muốn kiểm thử restart.
- **Reader không lưu state:** `saveState(false)` chỉ phù hợp nếu thiết kế xử lý dữ liệu lại theo cờ trạng thái, khóa hoặc điều kiện nghiệp vụ. Nếu reader bắt đầu từ đầu sau restart, writer phải chống trùng và test phải xác minh khả năng đó.
- **Step đã hoàn thành:** mặc định khi restart Job, Step `COMPLETED` trước đó được bỏ qua. `allowStartIfComplete(true)` thay đổi hành vi này; phải kiểm idempotency của Step được chạy lại.
- **Bất đồng bộ/partition:** kiểm thử trạng thái từng partition, không giả định thứ tự xử lý ổn định và không dùng reader có state chia sẻ không an toàn giữa các thread.

## 8. Những sai lầm thường khiến bài test “xanh giả”

**1. Đổi tham số định danh ở lần restart.** Thêm timestamp hoặc `run.id` mới khiến framework tạo JobInstance mới và chạy từ đầu. Hãy dùng cùng JobParameters khi kiểm tra restart. Nếu cần một thuộc tính phục vụ logging mà không đổi instance, có thể thêm tham số **non-identifying** và hiểu rõ hệ quả của nó đối với ứng dụng.

**2. Chỉ kiểm trạng thái Job.** `COMPLETED` không chứng minh dữ liệu đúng, không trùng, không mất và không được ghi lại. Cần đối chiếu ID, số lượng, tổng nghiệp vụ hoặc checksum của dữ liệu cuối.

**3. Xóa bảng `BATCH_*` giữa hai lần chạy.** Làm mất lịch sử JobInstance và checkpoint; lần hai không còn là restart. Chỉ dọn metadata giữa **các test case độc lập**, không dọn giữa hai execution trong cùng test.

**4. Dùng test bao bởi transaction chung.** Có thể che mất commit/rollback thực tế, khiến dữ liệu kiểm tra không phản ánh hành vi của Batch.

**5. Phụ thuộc lỗi ngẫu nhiên.** Các bài test dùng timeout, mạng thật hoặc tiến trình bên ngoài dễ không ổn định. Hãy chèn lỗi có điều kiện xác định theo item/step và tắt lỗi rõ ràng trước lần restart.

**6. Dùng `run.id` mới để “sửa” lỗi JobInstanceAlreadyComplete.** Cách này hợp lệ nếu nghiệp vụ chủ ý chạy một lô mới; nó không chứng minh restart lô cũ.

**7. Cho rằng checkpoint tự đảm bảo dữ liệu chính xác.** Transaction giữa JobRepository và dữ liệu nghiệp vụ có thể khác nhau; file output, message broker và API bên ngoài có thể không rollback theo DB. Test bắt buộc kiểm side effect/idempotency và tình huống lỗi ngay sau khi side effect thành công.

**8. Bỏ qua tính ổn định của dữ liệu nguồn.** Reader dùng offset, truy vấn thiếu `ORDER BY` hoặc nguồn đổi khi đang restart có thể tạo mất/trùng bản ghi. Hãy kiểm thử trên snapshot rõ ràng hoặc dùng thiết kế checkpoint theo khóa nghiệp vụ.

**9. Chỉ restart trong cùng process rồi cho rằng đã kiểm thử crash recovery.** Integration test trong cùng JVM chứng minh logic JobRepository/checkpoint. Bài test phục hồi sau crash cần hai process và database bền vững, đồng thời xác nhận không còn execution đang chạy thực sự.

## 9. Bài tập thực hành

Từ ví dụ trên, hãy mở rộng Job thành hai Step: `validateStep` và `loadStep`.

1. `validateStep` ghi một dấu vết kiểm thử khi chạy, sau đó thành công.
2. `loadStep` được cấu hình lỗi tại item `3` trong lần chạy đầu.
3. Restart cùng `JobParameters`; kiểm tra `validateStep` không chạy lại theo mặc định.
4. Đặt `allowStartIfComplete(true)` lên `validateStep`, chạy kịch bản với một JobInstance kiểm thử mới và xác nhận Step này chạy lại khi Job restart.
5. Thử đổi `ORDER BY id` thành câu query không có thứ tự rồi suy luận vì sao test checkpoint trở nên thiếu tin cậy (không dùng kết quả không xác định này làm assertion chính).
6. Chuyển writer sang API bên ngoài giả lập và thêm một khóa idempotency; mô phỏng việc API đã nhận yêu cầu nhưng Step fail trước khi lưu checkpoint.

**Tiêu chí hoàn thành:** test xác nhận trạng thái của cả hai lần chạy, nhận diện JobInstance, các StepExecution cần/không cần chạy lại, dữ liệu cuối đầy đủ không trùng và khả năng lặp lại ổn định trên database test sạch.

## 10. Ghi chú khác biệt phiên bản

Bài ví dụ dùng API **Spring Batch 6.x**:

- `JobOperatorTestUtils.startJob(params)` là tiện ích test được khuyến nghị cho 6.x.
- Các type Job/JobExecution, JobParameters và StepExecution thuộc các package `org.springframework.batch.core.job.*`, `org.springframework.batch.core.job.parameters.*`, `org.springframework.batch.core.step.*`.
- JDBC reader và writer đã chuyển sang `org.springframework.batch.infrastructure.item.*`.
- Khai báo chunk theo `new StepBuilder("loadStep", repository).<I, O>chunk(2).transactionManager(txManager)`.

Với **Spring Batch 5.2.x**, có thể dùng `JobLauncherTestUtils.launchJob(params)`, `new StepBuilder("loadStep", repository).<I, O>chunk(2, txManager)`, và các import đời 5 như `org.springframework.batch.core.JobExecution`, `org.springframework.batch.core.JobParametersBuilder`, `org.springframework.batch.item.database.builder.JdbcCursorItemReaderBuilder`. Trong Spring Batch 6, `JobLauncherTestUtils` đã được đánh dấu deprecated để chuyển sang `JobOperatorTestUtils`. Các **quy tắc nghiệp vụ restart, kiểm chứng checkpoint và dữ liệu đầu ra** vẫn là trọng tâm của test ở cả hai dòng phiên bản.

### Tài liệu tham khảo chính thức

- [Spring Batch — Unit Testing](https://docs.spring.io/spring-batch/reference/testing.html)
- [Spring Batch — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html)
- [Spring Batch — Configuring a Job / Restartability](https://docs.spring.io/spring-batch/reference/job/configuring.html)
- [Spring Batch — The Domain Language of Batch](https://docs.spring.io/spring-batch/reference/domain.html)
- [Spring Batch 6 Migration Guide](https://github.com/spring-projects/spring-batch/wiki/Spring-Batch-6.0-Migration-Guide)

