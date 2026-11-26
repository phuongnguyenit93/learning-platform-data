# Kiểm thử tích hợp Batch và Integration trong Spring Batch

## Mục tiêu bài học

Một luồng **remote chunking** có thể chạy đúng với một worker trong máy phát triển nhưng thất bại khi triển khai nhiều JVM: reply về không đúng thứ tự, manager hết thời gian chờ dù writer đã commit, request bị giao lại, consumer không còn kết nối broker hoặc một worker khác cố chạy lại partition đang hoạt động. Những lỗi này thường không được phát hiện bằng unit test của `ItemProcessor` hay bằng một lần chạy job có trạng thái `COMPLETED`.

**Kiểm thử tích hợp Batch và Integration** phải xác minh cả hai lớp:

- **Spring Batch:** `Job`, `Step`, `JobRepository`, `StepExecution`, `ExecutionContext`, transaction, chunk, retry và restart.
- **Spring Integration/middleware:** message channel, gateway, adapter, serialization, routing, correlation, timeout, ACK/redelivery, error channel và reply.

Bài thuộc chương **Spring Batch Integration** của module **SPRING_BATCH_SCALING_OPERATIONS**. Mục đích cuối cùng là mở rộng workload dữ liệu lớn qua multi-threaded step, parallel steps, partitioning và kiến trúc phân tán mà vẫn giữ **đúng dữ liệu, thread safety, khả năng phục hồi, hiệu năng và tính vận hành được**.

Học xong, bạn có thể:

- Thiết kế ma trận kiểm thử từ component đến end-to-end nhiều JVM.
- Sử dụng `spring-batch-test`, `JobLauncherTestUtils` và `StepScopeTestUtils` đúng mục đích.
- Kiểm thử Spring Integration flow ở mức in-memory mà không nhầm nó với kiểm thử broker thật.
- Tổ chức kiểm thử RabbitMQ/Kafka bằng Testcontainers và phân biệt các cam kết delivery/ordering.
- Tạo tình huống reply đảo thứ tự, duplicate, timeout và worker chết trước/sau commit.
- Xác nhận `JobRepository`, checkpoint, partition identity và writer idempotent sau restart.
- Viết assertion **theo business key** thay vì chỉ đếm message hoặc nhìn trạng thái job.
- Tránh flaky test bất đồng bộ, xây test data có thể tái hiện và thu thập metric cho scaling.

## 1. “Tích hợp thành công” phải có định nghĩa kiểm chứng được

Một test gửi được message từ manager sang worker chỉ chứng minh **một đường truyền hoạt động**. Nó chưa trả lời:

1. Worker có đọc đúng dữ liệu theo phạm vi đã được giao không?
2. DB đã commit đúng một lần theo business key chưa?
3. Reply có gắn đúng request khi nhiều worker hoàn thành đảo thứ tự không?
4. Nếu reply bị mất, manager có phân biệt “chưa xử lý” với “đã xử lý nhưng chưa xác nhận” không?
5. Khi job restart, checkpoint có khớp dữ liệu đã commit không?
6. Khi broker redeliver, side effect có bị nhân đôi không?
7. Nếu một partition lỗi, trạng thái JobExecution và các partition còn lại có hợp lý không?
8. Nếu tăng worker từ 2 lên 8, DB có bị nghẽn connection/lock hay không?

Vì vậy một kết quả kiểm thử đạt yêu cầu phải bao gồm **tính đúng đầu ra, trạng thái thực thi và hành vi phục hồi**, bên cạnh việc giao tiếp qua middleware.

### Ba loại kết quả khác nhau

| Kết quả quan sát | Nó chứng minh gì? | Chưa chứng minh điều gì? |
| --- | --- | --- |
| Broker nhận request | Message đã tới một điểm vận chuyển theo cấu hình | Worker đã chạy và commit |
| Manager nhận reply `COMPLETED` | Giao thức đã nhận kết quả thực thi phù hợp | Mọi side effect ngoài transaction đúng một lần |
| JobExecution `COMPLETED` | Framework đánh dấu job hoàn thành | Đích không thiếu, trùng, ghi sai business key hoặc sót late data |

**Định nghĩa “PASS” nên dựa vào business invariant**, ví dụ: tập `transaction_id` ở đích bằng tập hợp lệ ở nguồn, giá trị được chuẩn hóa đúng, không có side effect bị thực hiện quá số lần cho phép.

## 2. Bản đồ các thành phần cần kiểm thử

Với remote chunking, đường đi dữ liệu điển hình là:

~~~mermaid
flowchart LR
    SRC[("Nguồn nghiệp vụ")] --> MR["Manager Reader"]
    MR --> MC["Manager chunk"]
    MC --> OUT["Integration outbound"]
    OUT --> BQ[["Broker request"]]
    BQ --> IN["Worker inbound"]
    IN --> PW["Processor / Writer"]
    PW --> DST[("Đích nghiệp vụ")]
    PW --> RQ[["Broker reply"]]
    RQ --> AGG["Manager nhận/đối chiếu"]
    AGG --> JR[("JobRepository")]
~~~

Trong remote partitioning:

~~~mermaid
flowchart TB
    M["Manager Partitioner"] --> E["Các StepExecution + ExecutionContext"]
    E --> JR[("JobRepository")]
    E --> RQ[["Request channel"]]
    RQ --> W1["Worker JVM A tự đọc range A"]
    RQ --> W2["Worker JVM B tự đọc range B"]
    W1 --> SRC[("DB nguồn")]
    W2 --> SRC
    W1 --> DST[("DB đích")]
    W2 --> DST
    W1 --> JR
    W2 --> JR
    W1 -. "Result" .-> REP[["Reply/status"]]
    W2 -. "Result" .-> REP
    REP -.-> M
~~~

**Điểm khác biệt:** remote chunking chuyển item/chunk đã được manager đọc; remote partitioning yêu cầu worker tự đọc theo StepExecution. Test không nên dùng một giả định “worker = partition” cho cả hai mô hình.

Một bản đồ kiểm thử phải nêu rõ **ai sở hữu việc đọc, ai sở hữu transaction ghi, ai cập nhật metadata và ai chờ reply**.

## 3. Test pyramid phù hợp cho hệ thống Batch + Integration

Không nên chạy toàn bộ test trên Docker nhiều JVM: chậm, khó xác định nguyên nhân và dễ flaky. Thay vào đó có nhiều lớp với trách nhiệm khác nhau.

| Lớp | Mục tiêu | Công cụ thường dùng | Giới hạn |
| --- | --- | --- | --- |
| **Unit test** | Partition range, mapper, retry classifier, idempotency rule | JUnit 5, AssertJ, fake objects | Không xác minh container, DB và broker |
| **Step/component integration** | Reader/processor/writer, StepScope, transaction, checkpoint | `spring-batch-test`, DB test | Không chứng minh request/reply qua mạng |
| **In-memory IntegrationFlow** | Header, router, transformer, gateway logic, splitter/aggregator | `spring-integration-test`, channels | Không có delivery/serialization thật của broker |
| **Broker integration** | Converter, queue/topic, correlation, redelivery, DLQ | Testcontainers RabbitMQ/Kafka | Có thể vẫn là một JVM |
| **Distributed end-to-end** | Manager và worker khác process, JobRepository chung, crash/restart | Hai JVM/container + DB/broker | Nặng hơn, cần chọn lọc kịch bản |
| **Load/soak/fault tests** | SLA, throughput, contention, memory/connection leak, phục hồi | Environment đại diện, metrics | Không thay thế correctness assertions |

**Nguyên tắc:** test rẻ giúp tìm lỗi nhanh; test nhiều JVM chứng minh những ranh giới mà in-memory test không thấy. Không dùng một test nhỏ để kết luận toàn kiến trúc đã sẵn sàng production.

## 4. Viết hợp đồng và invariant trước khi viết code test

Ví dụ một batch chuẩn hóa hóa đơn:

- Nguồn có 50.000 bản ghi với `invoice_id` duy nhất.
- Processor có thể filter hóa đơn bị hủy theo quy tắc đã định.
- Writer upsert vào `invoice_summary`.
- Batch chạy theo `businessDate` được chốt trước.
- Có thể nhận lại chunk do broker redelivery.
- Worker có thể chết giữa chunk hoặc sau commit trước reply.

Invariant tối thiểu:

\[
\operatorname{Keys}(\mathrm{target})
=
\operatorname{Keys}(\mathrm{eligibleSource})
\]

Với từng khóa `k`:

\[
\mathrm{target}[k]
=
f(\mathrm{source}[k])
\]

và số bản ghi không trùng ngoài hợp đồng. Nếu writer gọi API ngoài, phải có định nghĩa riêng cho số lần **side effect hợp lệ**.

### Ma trận acceptance đơn giản

| Tình huống | Job/Step status kỳ vọng | Invariant dữ liệu |
| --- | --- | --- |
| Happy path | `COMPLETED` | Đủ khóa, đúng giá trị |
| Một item bị filter hợp lệ | `COMPLETED` | Không ghi item bị filter, số filter đúng |
| Lỗi dữ liệu không skip | `FAILED` | Chỉ phần đã commit tồn tại và restart an toàn |
| Lỗi tạm thời có retry | `COMPLETED` nếu retry thành công | Không ghi trùng |
| Worker chết giữa transaction | Có trạng thái thất bại/chưa rõ cần khôi phục | Không có nửa chunk ngoài transaction |
| Worker chết sau commit trước reply | Manager có thể timeout hoặc phải reconcile | Side effect không nhân đôi |
| Duplicate request/reply | Theo protocol và recovery policy | Không hoàn thành/ghi hai lần |
| Partition input sai/overlap | Test phải phát hiện/fail | Không âm thầm ghi trùng |

Không nên buộc mọi trường hợp lỗi phải có cùng `BatchStatus`: status phụ thuộc điểm lỗi, cấu hình handler và thời điểm điều phối. Điều cần chứng minh là **trạng thái có thể giải thích và phục hồi đúng**.

## 5. Fixture dữ liệu phải quyết định được và có trường hợp biên

Một fixture tốt không chỉ có ba bản ghi “đẹp”. Nên bao gồm:

- ID đầu, cuối của từng partition, đúng tại ranh giới `[from, to)`.
- Hai item có cùng timestamp nhưng ID khác.
- Một item bị filter đúng quy tắc.
- Dữ liệu lỗi định dạng/vi phạm nghiệp vụ.
- Hai sự kiện cùng business key nhưng khác source version, nếu nghiệp vụ cho phép.
- Một business key xuất hiện trong chunk sát thời điểm lỗi.
- Một partition rỗng và một partition lớn hơn phần còn lại.
- Dữ liệu đến muộn nếu có watermark/cutoff.
- Giá trị Unicode, null, số lớn nếu reader/serializer cần hỗ trợ.

Đặt expected output từ **quy tắc nghiệp vụ độc lập** thay vì chỉ chép lại logic của processor; nếu test và production cùng dùng một hàm sai, test có thể PASS dù kết quả sai.

### Fixture SQL ví dụ

~~~sql
INSERT INTO invoice_source(invoice_id, business_date, amount_cents, status)
VALUES
  (1, DATE '2026-11-25', 1200, 'PAID'),
  (2, DATE '2026-11-25', 3500, 'CANCELLED'),
  (3, DATE '2026-11-25', 2700, 'PAID'),
  (100001, DATE '2026-11-25', 4900, 'PAID');
~~~

Nếu quy tắc chỉ lấy `PAID`, expected keys là `{1,3,100001}`. Hãy dùng snapshot và một `businessDate` cố định khi test, không tạo dữ liệu dựa vào `LocalDate.now()` không kiểm soát.

## 6. Unit test Partitioner trước khi kéo theo broker

Với remote partitioning, một lỗi chia phạm vi gây mất/trùng dữ liệu ngay cả khi broker hoạt động hoàn hảo.

Giả sử Partitioner trả về:

~~~text
partition-0: [1, 50001)
partition-1: [50001, 100001)
partition-2: [100001, 150001)
~~~

Các phép kiểm tra:

1. Tên partition deterministic, không trùng.
2. Mỗi `minInclusive < maxExclusive`.
3. End của partition trước bằng start của partition sau.
4. Tổng các khoảng phủ đúng phạm vi được chốt.
5. Chạy lại với cùng tham số trả cùng partition names và ranges.
6. Không phụ thuộc vào `Instant.now()` hoặc dữ liệu nguồn thay đổi khi restart.
7. Có chính sách cho partition rỗng hoặc số partition lớn hơn số item.

Mẫu assertion logic độc lập:

~~~java
static void assertContiguous(
        List<long[]> orderedRanges,
        long expectedFrom,
        long expectedToExclusive) {

    long cursor = expectedFrom;

    for (long[] range : orderedRanges) {
        if (range.length != 2
                || range[0] != cursor
                || range[0] >= range[1]) {
            throw new AssertionError("Gap, overlap or empty range");
        }
        cursor = range[1];
    }

    if (cursor != expectedToExclusive) {
        throw new AssertionError("Incomplete partition coverage");
    }
}
~~~

Đây là helper Java minh họa; khi dùng thật cần chuyển `Map<String, ExecutionContext>` thành danh sách range được sắp đúng và so thêm danh tính partition.

**Bẫy:** chỉ kiểm tra tổng số readCount không đủ. Hai partition có thể đọc trùng 10 record và đồng thời bỏ sót 10 record mà tổng vẫn đúng.

## 7. Kiểm thử reader @StepScope với StepScopeTestUtils

Bean `@StepScope` lấy input theo `StepExecution`, ví dụ `minIdInclusive` và `maxIdExclusive`. Trong một unit test không có active StepExecution, late binding có thể không hoạt động.

Thư viện `spring-batch-test` cung cấp `StepScopeTestUtils` để chạy code test trong một step context được thiết lập có chủ đích.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.item.ExecutionContext;
import org.springframework.batch.item.ItemStreamReader;
import org.springframework.batch.test.MetaDataInstanceFactory;
import org.springframework.batch.test.StepScopeTestUtils;

class RangeReaderScopeTest {

    private final ItemStreamReader<OrderRow> rangeReader;

    RangeReaderScopeTest(ItemStreamReader<OrderRow> rangeReader) {
        this.rangeReader = rangeReader;
    }

    @Test
    void readerUsesAssignedPartitionRange() throws Exception {
        StepExecution step =
                MetaDataInstanceFactory.createStepExecution();

        step.getExecutionContext().putLong(
                "minIdInclusive", 10L);
        step.getExecutionContext().putLong(
                "maxIdExclusive", 20L);

        long count = StepScopeTestUtils.doInStepScope(
                step, () -> {
                    ExecutionContext checkpoint =
                            new ExecutionContext();

                    rangeReader.open(checkpoint);
                    try {
                        long n = 0L;
                        OrderRow item;
                        while ((item = rangeReader.read()) != null) {
                            if (item.id() < 10L || item.id() >= 20L) {
                                throw new AssertionError(
                                        "Reader escaped its partition");
                            }
                            n++;
                        }
                        return n;
                    } finally {
                        rangeReader.close();
                    }
                });

        assertEquals(10L, count);
    }
}
~~~

**Giới hạn minh họa:** đoạn code giả định test được chạy trong Spring test context có `@StepScope` reader và dependency injection phù hợp, bảng nguồn chứa đủ mười ID `10..19`, record `OrderRow` có `id()`, và bean thực hiện `ItemStreamReader`. Nếu sử dụng JUnit + Spring Test, phải đăng ký context (ví dụ `@SpringJUnitConfig` hoặc `@SpringBootTest`) và cách inject bean thích hợp; class ở trên chỉ tập trung vào phép thử scope.

### Vì sao cần test scope riêng?

- Phát hiện sai tên key `stepExecutionContext`.
- Phát hiện reader dùng nhầm range cố định/singleton.
- Phát hiện logic cận `>= from AND < to` sai.
- Kiểm tra `ItemStream.open/update/close` theo contract.
- Chuẩn bị cho restart test với `ExecutionContext` lưu checkpoint.

**Quan trọng:** StepScope tạo target theo StepExecution, **không** theo chunk thread. Nếu bật multi-threaded step trong cùng StepExecution, reader stateful có thể vẫn bị chia sẻ.

## 8. Kiểm thử Job và Step với spring-batch-test

Với `spring-batch-test`, `@SpringBatchTest` hỗ trợ các tiện ích như `JobLauncherTestUtils` và `JobRepositoryTestUtils` trong Spring test context phù hợp. Đây là lớp kiểm thử xác minh **Spring Batch workflow** mà không nhất thiết có middleware phân tán.

Ví dụ minh họa Spring Batch 5.x, Spring Boot 3.x và JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBatchTest
@SpringBootTest(classes = BatchTestApplication.class)
class InvoiceJobIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    @Qualifier("invoiceJob")
    private Job invoiceJob;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @BeforeEach
    void setJob() {
        jobLauncherTestUtils.setJob(invoiceJob);
    }

    @Test
    void completedJobWritesExpectedBusinessKeys()
            throws Exception {

        JobParameters params = new JobParametersBuilder()
                .addString("businessDate", "2026-11-25")
                .addString(
                        "testRunId",
                        UUID.randomUUID().toString())
                .toJobParameters();

        JobExecution execution =
                jobLauncherTestUtils.launchJob(params);

        assertEquals(BatchStatus.COMPLETED,
                execution.getStatus());

        Long count = jdbcTemplate.queryForObject(
                """
                SELECT COUNT(*)
                FROM invoice_summary
                WHERE business_date = ?
                """,
                Long.class,
                "2026-11-25");

        assertEquals(3L, count);
    }
}
~~~

**Giả định cần chuẩn bị:** `BatchTestApplication` là lớp cấu hình test của ứng dụng; có bean `invoiceJob`, DataSource, JobRepository và schema bảng đã khởi tạo. Test phải seed đúng fixture và bảo đảm dữ liệu riêng biệt; truy vấn COUNT theo businessDate chỉ an toàn khi mỗi test có DB/fixture tách biệt hoặc cleanup đáng tin cậy. Với các test chạy song song, nên lọc thêm namespace `testRunId`/tenant phù hợp hoặc dùng database container riêng.

**Không dừng ở COUNT = 3:** thêm assertions cho tập `invoice_id`, giá trị chuẩn hóa, `filterCount`, `writeCount`, `rollbackCount` và ràng buộc uniqueness. Status `COMPLETED` chỉ là một điều kiện, không phải bằng chứng đầy đủ.

### Khi nào dùng launchStep?

`JobLauncherTestUtils.launchStep(...)` hữu ích để kiểm tra một step độc lập. Tuy nhiên với remote partitioning, phép thử một worker step **không** kiểm chứng manager dispatch, request/reply hoặc logic tổng hợp trạng thái nhiều partition. Cần thêm test cho toàn job/topology.

## 9. Test `ExecutionContext`, checkpoint và restart

Spring Batch dùng `ExecutionContext` để lưu state phục vụ restart của `ItemStream` và dữ liệu liên quan đến StepExecution. Tính đúng phải được kiểm tra tại ranh giới chunk commit.

Một kiểm thử restart nên:

1. Tạo JobInstance với **JobParameters cố định** và input snapshot.
2. Chạy job tới một điểm lỗi **có chủ đích**.
3. Xác nhận trạng thái lần đầu là `FAILED` hoặc trạng thái phù hợp với kiểu lỗi.
4. Chụp read/write count, business keys đã commit và checkpoint được lưu.
5. Gỡ điều kiện lỗi **mà không thay JobParameters nhận dạng**.
6. Gọi lại job theo cơ chế restart của cấu hình được kiểm thử.
7. Đối soát đầu ra cuối với baseline không lỗi.
8. Bảo đảm không có item bị bỏ sót hoặc side effect bị áp dụng hai lần.

~~~mermaid
flowchart LR
    A["JobExecution #1"] --> C1["Commit chunk 1"]
    C1 --> C2["Commit chunk 2"]
    C2 --> F["Lỗi trước chunk tiếp"]
    F --> R[("JobRepository checkpoint")]
    R --> B["JobExecution #2: restart"]
    B --> N["Phục hồi từ checkpoint"]
    N --> O["Đối soát output cuối"]
~~~

**Lưu ý:** JobExecution mới sau restart có thể có ID khác, còn JobInstance vẫn biểu diễn công việc logic cũ. Không đổi `businessDate`, range partition, tên partition hoặc nguồn snapshot khi đang kiểm tra restart cùng JobInstance.

### Đừng “sửa” test bằng cách đổi testRunId

Nếu JobExecution đầu thất bại, việc thêm một `testRunId` mới vào **identifying JobParameters** có thể tạo JobInstance khác thay vì restart. Test vẫn ghi đủ dữ liệu nhưng không chứng minh checkpoint của job trước hoạt động.

Với mỗi test, dùng một run key duy nhất **trước lần chạy đầu**, rồi **giữ nguyên key đó khi restart**. Phân biệt test case khác với một lượt restart của cùng test.

## 10. Test Spring IntegrationFlow in-memory

In-memory flow giúp kiểm tra **routing, header propagation, transformer và request/reply logic** mà chưa phụ thuộc broker. Một ví dụ sử dụng `DirectChannel` cho request và `QueueChannel` cho reply.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.EnableIntegration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;

@Configuration
@EnableIntegration
public class WorkerFlowTestConfig {

    public record WorkRequest(String workId, int value) {}
    public record WorkReply(String workId, int result) {}

    @Bean
    public MessageChannel testRequests() {
        return new DirectChannel();
    }

    @Bean
    public PollableChannel testReplies() {
        return new QueueChannel();
    }

    @Bean
    public IntegrationFlow testWorkerFlow() {
        return IntegrationFlow.from("testRequests")
                .handle((payload, headers) -> {
                    WorkRequest request = (WorkRequest) payload;

                    return MessageBuilder
                            .withPayload(new WorkReply(
                                    request.workId(),
                                    request.value() * 2))
                            .setHeader(
                                    "batchCorrelationKey",
                                    headers.get(
                                            "batchCorrelationKey"))
                            .build();
                })
                .channel("testReplies")
                .get();
    }
}
~~~

Test:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.PollableChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = WorkerFlowTestConfig.class)
class WorkerFlowTest {

    @Autowired
    @Qualifier("testRequests")
    MessageChannel requests;

    @Autowired
    @Qualifier("testReplies")
    PollableChannel replies;

    @Test
    void preservesCorrelationAndTransformsPayload() {
        Message<WorkerFlowTestConfig.WorkRequest> request =
                MessageBuilder.withPayload(
                    new WorkerFlowTestConfig.WorkRequest(
                            "work-42", 7))
                    .setHeader(
                            "batchCorrelationKey", "corr-42")
                    .build();

        assertTrue(requests.send(request));

        Message<?> reply = replies.receive(2_000);
        assertNotNull(reply);
        assertEquals(
                "corr-42",
                reply.getHeaders().get("batchCorrelationKey"));

        var result =
                (WorkerFlowTestConfig.WorkReply) reply.getPayload();
        assertEquals("work-42", result.workId());
        assertEquals(14, result.result());
    }
}
~~~

Đây là **flow thử nghiệm của ứng dụng**, không phải flow remote chunking hoàn chỉnh. Nó chứng minh có thể gửi một request, chuyển đổi và giữ header qua các channel **trong cùng ApplicationContext**.

**Không suy luận** từ test này rằng `correlationId`, `replyChannel`, message converter hoặc các kiểu payload của Spring Batch Integration sẽ tự được bảo toàn khi đi qua RabbitMQ/Kafka. Cần kiểm thử transport thật.

## 11. Test header và correlation ở ranh giới message

Khi nhiều worker chạy, reply B có thể đến trước reply A. Test phải cố ý tạo tình huống đó.

~~~text
Request A: correlation=req-A
Request B: correlation=req-B

Reply B đến trước
Reply A đến sau
~~~

Kỳ vọng:

- Reply B được ghép với req-B, không phải req-A.
- Reply A được ghép với req-A.
- Không tăng completed count hai lần với duplicate reply.
- Reply trễ sau timeout được ghi nhận hoặc xử lý theo protocol.
- Header ứng dụng chỉ được giữ khi adapter/header mapper được cấu hình.
- Correlation ID không bị tái sử dụng giữa các JobExecution đang hoạt động theo phạm vi thiết kế.

### Phân biệt các loại ID

| Định danh | Dùng để làm gì | Không thay thế |
| --- | --- | --- |
| `MessageHeaders.ID` | Envelope message | Idempotency nghiệp vụ |
| Request correlation ID | Ghép request/reply | Business transaction ID |
| `sequenceNumber`/`sequenceSize` | Group do splitter/aggregator quản lý | Thứ tự commit DB |
| JobExecution/StepExecution ID | Metadata Spring Batch | Deduplication xuyên mọi restart |
| Business event ID | Idempotency/đối soát | Protocol reply channel |
| Trace ID | Liên kết observability | Quyền thực thi hoặc khóa nghiệp vụ |

Nếu Spring Integration gateway đã sở hữu `correlationId`, đừng ghi đè bằng một group ID chung; có thể dùng custom header riêng như `batchLogicalCorrelationId` cho log. Không giả định mọi header từ Spring Message đều serialize được qua broker.

## 12. Test splitter/aggregator, timeout và group state

Nếu flow dùng `Splitter`/`Aggregator`, cần test độc lập với request/reply của Spring Batch:

1. Các phần tử trong một group có cùng correlation key.
2. Các phần tử của hai JobExecution khác nhau **không** bị gom chung.
3. Sequence 1/3, 2/3, 3/3 có thể đến đảo thứ tự mà aggregator vẫn gộp đúng.
4. Duplicate một phần tử không làm group hoàn thành sai.
5. Thiếu một phần tử thì timeout/release strategy theo chính sách.
6. JVM chết giữa quá trình gộp: in-memory MessageStore có thể mất state.
7. Group state cũ không bị ghép với message của execution mới sau restart.
8. Có chính sách cleanup/expiry để tránh bộ nhớ tăng vô hạn.

~~~mermaid
flowchart TD
    A["Group X, seq 2/3"] --> G["Aggregator X"]
    B["Group Y, seq 1/2"] --> H["Aggregator Y"]
    C["Group X, seq 1/3"] --> G
    D["Group X, seq 3/3"] --> G
    G --> O["Release X đủ ba phần tử"]
    H --> P["Chờ Y phần còn lại"]
~~~

**Không dùng `JobName` đơn lẻ làm group key** nếu hai lần chạy có thể chồng lên nhau. Đồng thời, aggregator nhận đủ reply **không chứng minh** tất cả side effect nghiệp vụ đã đúng; phải kiểm tra status và dữ liệu đích.

## 13. Vì sao cần broker thực trong integration test?

`DirectChannel` và `QueueChannel` không mô phỏng đầy đủ:

- Serialization/deserialization qua wire.
- Exchange, routing key, queue binding hoặc topic partition.
- ACK/NACK, offset commit và redelivery.
- Consumer concurrency/prefetch.
- Reply-to và correlation mapper của gateway.
- Message TTL, retention, delayed retry và DLQ.
- Network disconnect, broker restart hoặc delivery tới process khác.
- Kích thước payload, giới hạn message và backpressure.

Vì vậy phải có ít nhất một lớp **broker integration test** cho transport thật của dự án. Nếu production dùng RabbitMQ, một test in-memory Kafka không thay thế được RabbitMQ; nếu production dùng Kafka, một mock AMQP không chứng minh semantics của offset và topic.

## 14. Ví dụ Testcontainers: RabbitMQ và PostgreSQL

Ví dụ dưới đây chỉ minh họa cách cấp broker và DB thật cho Spring Boot test. Nó **không** bao gồm flow manager/worker; các bean của ứng dụng và migration/schema vẫn phải được tạo trong test context.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.containers.RabbitMQContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest
class BrokerDatabaseIntegrationTest {

    @Container
    static final RabbitMQContainer rabbit = new RabbitMQContainer(
            DockerImageName.parse("rabbitmq:3.13-management"));

    @Container
    static final PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>(
                    DockerImageName.parse("postgres:16-alpine"));

    @DynamicPropertySource
    static void register(DynamicPropertyRegistry registry) {
        registry.add(
                "spring.rabbitmq.host", rabbit::getHost);
        registry.add(
                "spring.rabbitmq.port", rabbit::getAmqpPort);

        registry.add(
                "spring.datasource.url", postgres::getJdbcUrl);
        registry.add(
                "spring.datasource.username", postgres::getUsername);
        registry.add(
                "spring.datasource.password", postgres::getPassword);
    }

    @Test
    void infrastructureIsAvailable() {
        // Chạy test flow thật của ứng dụng:
        // publish -> consume -> commit -> reply -> assert DB.
        // Test này chỉ là skeleton phần hạ tầng.
    }
}
~~~

### Cần bổ sung để thành một integration test hoàn chỉnh

- Dựng exchange/queue/binding hoặc cấu hình broker đúng production.
- Khởi tạo schema Spring Batch metadata và schema nghiệp vụ.
- Gắn inbound/outbound adapter, gateway và message converter.
- Khởi chạy manager/worker flow ở context phù hợp.
- Seed fixture, phát request và chờ kết quả với timeout hữu hạn.
- Assert business keys, trạng thái execution và correlation.
- Kiểm tra redelivery/DLQ/timeout theo transport đang dùng.

Ví dụ dùng API Testcontainers thường gặp với Spring Boot 3.x, Testcontainers tương ứng và Java 17. Image tag chỉ là **mốc minh họa**, cần pin phiên bản được tổ chức chấp thuận và tương thích với production. Test yêu cầu Docker runtime; nếu CI không có Docker, phải có tầng test thay thế rõ và không tuyên bố broker test đã chạy.

## 15. Nếu transport là Kafka

Với Kafka, môi trường test phải tạo:

- Request topic và reply topic phù hợp.
- Số topic partitions và consumer groups được kiểm soát.
- Producer/consumer serializers và header mappers thật.
- Quy tắc offset commit theo adapter.
- Retry topic/DLT nếu production dùng.
- Cách tìm reply đúng request khi nhiều request outstanding.
- Cách chờ lag về ngưỡng mong đợi, không ngủ cứng.

Một test cần chứng minh rằng **record được xử lý lại** khi DB đã commit nhưng offset chưa commit không làm lặp side effect. Một test khác cần chứng minh **retry topic không phá thứ tự nghiệp vụ** nếu có sequence theo aggregate.

Kafka bảo đảm thứ tự log trong **mỗi topic partition**, không bảo đảm mọi worker commit DB theo cùng thứ tự. Key dùng định tuyến partition **không mặc nhiên là correlation hoặc idempotency key**.

Không dùng chung một tập assertions transport-specific giữa RabbitMQ và Kafka rồi giả định ACK và offset là tương đương hoàn toàn. Nên tách **contract tests** chung (tính đúng dữ liệu) khỏi **delivery tests** của broker cụ thể.

## 16. Test end-to-end thật với hai JVM riêng

Một test chạy manager và worker trong cùng Spring ApplicationContext có thể chứng minh bean wiring nhưng **không** kiểm chứng các lỗi do ranh giới process.

Một topology kiểm thử mạnh hơn:

~~~mermaid
flowchart TB
    M["Container/JVM manager"] --> B[["Broker Testcontainer"]]
    B --> W1["Container/JVM worker A"]
    B --> W2["Container/JVM worker B"]
    M --> JR[("PostgreSQL JobRepository")]
    W1 --> JR
    W2 --> JR
    W1 --> DATA[("DB nguồn/đích")]
    W2 --> DATA
    OBS["Test harness"] --> M
    OBS --> B
    OBS --> JR
    OBS --> DATA
~~~

**Bài kiểm tra phải xác định vai trò từng process**:

- Manager có step/job tương ứng, adapter và chính sách điều phối.
- Worker có handler, reader/processor/writer hoặc worker Step tùy mô hình.
- Các process dùng chung metadata store phù hợp khi remote partitioning cần truy xuất StepExecution.
- Cùng hiểu serializer, message schema và phiên bản thư viện.
- Có network alias/endpoint hoạt động trong Docker network.
- Có log và health readiness để biết worker thật sự đã sẵn sàng tiêu thụ.

### Một luồng kiểm thử điển hình

1. Tạo DB và broker container.
2. Áp dụng migrations cho metadata và business schema.
3. Start worker process, đợi readiness có timeout.
4. Start manager process với JobParameters xác định.
5. Chờ trạng thái cuối bằng polling có deadline.
6. Query DB và đối soát toàn bộ output.
7. Thu status của từng StepExecution, chunk/reply metrics và broker state.
8. Dừng/cleanup process và dữ liệu test.

**Readiness khác với container process running.** Container chạy chưa chắc listener đã subscribe, StepLocator đã đăng ký hoặc DB schema đã sẵn sàng. Test cần xác nhận điều kiện sẵn sàng thực, không dùng thời gian ngủ cố định.

## 17. Ma trận fault injection theo ranh giới commit

Thử lỗi ở vị trí nào quan trọng hơn việc chỉ “kill worker một lần”.

| Vị trí chèn lỗi | Cách mô phỏng | Kỳ vọng cần chứng minh |
| --- | --- | --- |
| Trước khi publish request | Chặn outbound | Không tạo work thành công giả |
| Sau khi broker nhận nhưng trước producer confirm | Cắt kết nối producer | Retry chịu được duplicate publish |
| Sau khi worker receive nhưng trước DB transaction | Kill worker | Request được phục hồi theo ACK/offset policy |
| Trong chunk trước commit | Throw DB exception hoặc kill worker | Rollback/partial state đúng transaction |
| **Sau DB commit nhưng trước ACK/reply** | Kill/cắt kết nối ngay sau commit | **Không áp dụng side effect lần hai** |
| Sau reply publish nhưng trước manager receive | Chặn reply route | Timeout/late reply được đối chiếu đúng |
| Sau manager receive, trước khi ghi nhận hoàn tất | Crash manager | Restart/reconciliation không bỏ sót |
| Trong JobRepository update | Giả lập DB metadata outage | Trạng thái không bị đánh dấu sai |
| Khi nhiều partition đang chạy | Kill một worker | Các partition còn lại đúng; recovery rõ |
| Trong quá trình retry | Broker restart | Không mất ledger/trạng thái durable |

Để chèn lỗi chính xác, có thể bổ sung **test-only failure hook** ở các vị trí boundary; không đưa hook có khả năng làm hỏng dữ liệu vào production profile. Nếu không thể can thiệp chính xác, hãy chứng minh cửa sổ lỗi bằng một test tích hợp thu thập log/transaction phù hợp.

**Cảnh báo:** với remote chunking và remote partitioning, cách manager kết luận lỗi/phục hồi phụ thuộc Spring Batch Integration version, `PartitionHandler` và adapter. Test phải kiểm tra contract thực thay vì buộc mọi phiên bản phản ứng giống nhau.

## 18. ACK, broker delivery và DB commit phải được kiểm thử riêng

Một khi consumer nhận message, có ít nhất ba trạng thái cần quan sát:

1. **Broker delivery:** request đã giao cho consumer.
2. **Business transaction:** worker đã commit/rollback.
3. **Delivery acknowledgement/reply:** message đã ACK/offset commit và kết quả đã đến manager.

Không được giả định chúng nằm trong một transaction nguyên tử.

### Test “commit rồi mất ACK”

~~~text
T0 Broker giao R-42
T1 Worker bắt đầu transaction
T2 DB commit thành công
T3 Worker JVM chết trước ACK/reply
T4 Broker có thể redeliver R-42
T5 Worker mới nhận R-42
T6 Ledger/idempotent writer xác định đã áp dụng
T7 Không có duplicate business effect
~~~

Nếu test chỉ assert worker nhận message hai lần thì chưa đủ. Phải assert **số business operation thực sự được áp dụng**.

### Test “ACK sớm rồi chết”

Nếu adapter được cấu hình ACK khi handler chưa hoàn thành, worker chết có thể khiến message không được redeliver. Đây là bài kiểm tra phát hiện nguy cơ **at-most-once / lost work** tùy cấu hình; cần ghi nhận và sửa policy trước khi mở rộng.

### Phân biệt publisher confirm

Publisher confirm chứng minh broker/producer đạt một bước xác nhận publish theo cấu hình, **không** chứng minh worker đã commit hay manager đã có reply. Test transport cần assert đúng mức cam kết thay vì đánh đồng các loại xác nhận.

## 19. Idempotency test phải ở transaction của nghiệp vụ

Một hệ thống phân tán thường phải chịu **at-least-once delivery** và biến side effect thành lặp lại an toàn. Correlation ID hoặc `messageId` không tự giải quyết được.

Với các sự kiện có `event_id` bất biến, một schema ledger minh họa:

~~~sql
CREATE TABLE applied_event (
    event_id       UUID PRIMARY KEY,
    payload_sha256 CHAR(64) NOT NULL,
    applied_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE account_state (
    account_id     BIGINT PRIMARY KEY,
    balance_cents  BIGINT NOT NULL
);
~~~

Một cách xử lý an toàn ở cấp nguyên tắc:

1. Bắt đầu transaction DB.
2. Cố xác lập event mới trong ledger bằng **unique constraint**.
3. Nếu event đã có, xác minh payload hash; duplicate hợp lệ thì không cộng thêm.
4. Nếu event mới, cập nhật `account_state` theo quy tắc giao dịch.
5. Commit ledger và update cùng transaction hoặc rollback cả hai.

**Không chỉ SELECT trước rồi INSERT sau**: hai worker có thể cùng thấy chưa tồn tại. Cần unique constraint, atomic SQL hoặc locking phù hợp, cùng cách xử lý duplicate/conflict rõ ràng.

### Assertions quan trọng

- Một event gửi hai lần → balance chỉ thay đổi một lần.
- Cùng eventId nhưng payload khác → conflict, không âm thầm bỏ qua.
- Hai worker nhận cùng event đồng thời → chỉ một transaction tạo side effect.
- Crash giữa ledger và update → không có trạng thái “đã đánh dấu nhưng chưa áp dụng” nếu cùng transaction.
- Replay trong JobExecution mới → vẫn đúng theo business event ID.
- Event theo version → không cho version cũ ghi đè dữ liệu mới khi nghiệp vụ yêu cầu.

**Nếu writer gửi HTTP/API**, transaction DB không tự bao trùm API ngoài. Test phải mô phỏng timeout **sau khi API đã thực hiện thao tác** và xác minh idempotency key/outbox hoặc cơ chế đối soát phù hợp.

## 20. Kiểm thử retry, backoff và DLQ

Retry có thể xảy ra ở producer, broker, handler, Spring Batch item hoặc job restart. Không nên bật retry ở mọi nơi rồi chỉ kiểm tra tổng số attempts.

| Kịch bản | Cấu hình test | Kết quả kỳ vọng |
| --- | --- | --- |
| DB timeout tạm thời | Lỗi ở lần đầu, thành công lần hai | Retry hữu hạn; output đúng một lần |
| Payload không hợp lệ | Deserialize/validate fail | Không retry vô hạn; error/DLQ theo policy |
| Broker disconnect | Mất kết nối trong publish/consume | Phục hồi có xác nhận; duplicate an toàn |
| Request ACK bị mất | Redelivery | Idempotent writer |
| Reply đến trễ | Manager timeout trước khi reply đến | Correlation đúng, không ghép request mới |
| Dead-letter | Vượt retry budget | Có alert, metadata và runbook |
| Replay DLQ | Reprocess có kiểm soát | Không đụng execution đang active |
| Downstream outage diện rộng | Nhiều consumer cùng lỗi | Backoff/jitter/backpressure, không retry storm |

### Tại sao phải kiểm tra backoff bằng hành vi?

Một cấu hình `maxAttempts=3` có thể bao gồm lần thử đầu tiên và hai lần thử lại. Test cần quan sát:

- Số lượt thực sự gọi handler.
- Khoảng delay/backoff theo policy với dung sai hợp lý.
- Exception nào được retry và exception nào fail ngay.
- Sau exhaustion, message đi đâu, manager nhận trạng thái gì.
- Có thể dừng job hoặc pause consumer không.
- Retry tổng từ broker + handler + Batch có vượt ngân sách không.

**Không dùng `Thread.sleep()` dài để đo chính xác từng millisecond.** Dùng fake clock/scheduler cho retry unit test khi có thể; integration test xác minh xu hướng/giới hạn trong timeout phù hợp thay vì khớp tuyệt đối lịch thread.

### DLQ không có nghĩa hoàn thành

Nếu một partition request vào DLQ, manager không được mặc nhiên đánh dấu partition `COMPLETED`. DLQ lưu phần việc cần điều tra, không phải bằng chứng side effect đã thực hiện. Test phải xác minh trạng thái JobExecution, alert và phương án replay.

## 21. Test thread safety khi nhiều message đến cùng worker JVM

Một worker JVM có thể có nhiều inbound consumer threads. Dù mỗi message hoặc StepExecution có ID riêng, các singleton bean vẫn có thể được chia sẻ.

Các thành phần cần kiểm tra:

- `ItemReader` có cursor hoặc page state.
- `ItemProcessor` có buffer/cache mutable.
- `ItemWriter` có batch accumulator hoặc request builder.
- Mapper/serializer, formatter, thư viện ngoài.
- JDBC Connection/ResultSet/ORM session.
- `@StepScope` có đúng ranh giới StepExecution không.
- Các listener/callback giữ state chung.
- Rate limiter, circuit breaker và pool capacity.

**Nhắc lại:** `@StepScope` gắn với **StepExecution**, không tạo instance per-thread cho mọi chunk của một multi-threaded step. Trong local/remote partitioning, reader theo StepExecution giúp cô lập range nhưng singleton dependency bên dưới vẫn có thể được chia sẻ trong một JVM.

### Một phép kiểm chứng concurrency

Cho 8 worker threads cùng xử lý 8 partition khác nhau, với fixture có business key không chồng lấn. Chèn barrier hoặc `CountDownLatch` để nhiều worker bắt đầu cùng lúc. Assert:

- Mỗi partition chỉ đọc phạm vi được giao.
- Không business key nào bị ghi trùng ngoài replay đã xác định.
- Reader không dùng sai cursor/state giữa hai StepExecution.
- Writer/SDK không trả về output thuộc item khác.
- Tổng connection và heap không vượt budget.
- Khi một worker fail, các worker khác không bị hỏng state dùng chung.

Một bài load test PASS không chứng minh absence of races; tài liệu thread safety của thư viện và thiết kế object graph vẫn cần được kiểm tra.

## 22. Test ordering khi nghiệp vụ yêu cầu

Không phải job nào cũng cần giữ thứ tự commit; nhiều batch chỉ cần kết quả cuối đúng theo khóa độc lập. Nhưng với event-sourced projection, số dư theo delta hoặc state machine, thứ tự theo `aggregateId` có thể là điều kiện bắt buộc.

Ví dụ:

~~~text
order-42 / seq=1 CREATED
order-42 / seq=2 PAID
order-42 / seq=3 SHIPPED
~~~

Đặt hai chunk vào hai worker để chunk chứa seq=3 hoàn thành trước chunk chứa seq=2. Kỳ vọng:

- Nếu business yêu cầu mọi transition, seq=3 **không được áp dụng** khi còn thiếu seq=2.
- Có sequence guard/gap handling hoặc key-affinity đảm bảo thứ tự theo order.
- Retry/requeue không làm event cũ bị bỏ qua.
- Duplicate seq=2 không tạo transition lần hai.
- Reply đến đảo thứ tự vẫn ghép đúng request, nhưng đó không thay thế ordering nghiệp vụ.

**Broker FIFO không tự bảo đảm DB commit order** khi nhiều consumer xử lý đồng thời. Test phải quan sát trạng thái DB cuối và sequence đã áp dụng, không chỉ thứ tự message nhận.

## 23. Các test bất đồng bộ phải có đồng bộ hóa đáng tin cậy

Lỗi phổ biến:

~~~java
sendMessage();
Thread.sleep(2000);
assertDatabase();
~~~

Nếu CI chậm, 2 giây có thể không đủ; nếu handler bị lỗi nhưng message vẫn còn queue, test có thể pass/fail không ổn định. Không dùng sleep cố định làm điều kiện hoàn tất chính.

### Dùng điều kiện + deadline

Ví dụ với Awaitility:

~~~java
import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;

await()
    .atMost(Duration.ofSeconds(15))
    .pollInterval(Duration.ofMillis(100))
    .untilAsserted(() -> {
        Integer count = jdbcTemplate.queryForObject(
                """
                SELECT COUNT(*)
                FROM invoice_summary
                WHERE business_date = ?
                """,
                Integer.class,
                "2026-11-25");

        assertEquals(3, count);
    });
~~~

Đây là mã minh họa chạy bên trong một test đã có `JdbcTemplate` và fixture cô lập. `Awaitility` là dependency test bổ sung, không thuộc mặc định mọi dự án Spring Batch.

### Điều kiện hoàn tất nên là gì?

- `JobExecution` có trạng thái cuối phù hợp.
- Tất cả expected work IDs đã có outcome xác định.
- Tập business keys/output đã đối soát.
- Broker không còn request đang inflight theo test case.
- DLQ rỗng **nếu** test yêu cầu không có lỗi.
- Reply/late reply đã được ghi nhận theo protocol.

**Chỉ đợi count đạt 3 chưa đủ** nếu còn worker tiếp tục ghi bản ghi thứ tư sau đó. Khi cần chứng minh kết quả cuối ổn định, kết hợp trạng thái execution cuối và ranh giới message đã hoàn tất; không chỉ chờ một điều kiện nhất thời.

### Barrier để tạo lỗi có chủ đích

Dùng `CountDownLatch` hoặc test hook để chặn worker A ngay trước commit, cho B chạy rồi giải phóng A. Cách này giúp tái hiện reply đảo thứ tự một cách quyết định hơn việc hy vọng scheduler tự sắp xếp.

## 24. Isolation giữa các test và JobRepository

Spring Batch lưu metadata qua nhiều lần chạy. Một test có JobInstance đã `COMPLETED` có thể khiến lần chạy sau với cùng identifying JobParameters không khởi chạy lại, hoặc tạo exception phù hợp.

Cần quy tắc isolation:

- Mỗi test case có JobParameters nhận dạng riêng, **trừ** test restart cần giữ nguyên.
- Mỗi test có schema/DB container riêng hoặc cleanup có chủ đích.
- Nếu dùng `JobRepositoryTestUtils` để xóa metadata, chỉ dùng trong dữ liệu test được sở hữu và bảo đảm không còn execution đang chạy.
- Không dùng cleanup kiểu `DELETE FROM BATCH_*` tùy tiện trên DB dùng chung.
- Đừng xóa business data mà vẫn giữ JobRepository state rồi kết luận restart hoạt động.
- Khi test chạy song song, tránh cùng dùng một `businessDate` hoặc cùng queue/group nếu có thể gây đụng dữ liệu.
- Dùng tên queue/topic, consumer group và run key phân biệt hoặc tạo hạ tầng test cô lập.

### Không chạy các failure tests đồng thời thiếu kiểm soát

Nếu test A kill worker trong cùng container mà test B đang dùng, B có thể fail ngẫu nhiên. Với fault injection, cân nhắc **một topology riêng cho mỗi test** hoặc tuần tự hóa những test cùng sở hữu hạ tầng.

### Sự khác biệt giữa reset và restart

- **Reset test data**: xóa dữ liệu để thử một kịch bản mới; thường bắt đầu JobInstance mới.
- **Restart test**: giữ metadata/dữ liệu đã commit của lần thất bại để kiểm tra khả năng tiếp tục **cùng công việc logic**.

Không trộn hai mục đích trong cùng test rồi đánh giá checkpoint sai.

## 25. Observability hỗ trợ test và điều tra lỗi

Khi một bài test mất 30 giây rồi timeout, log chỉ ghi “worker failed” không đủ. Nên lưu mốc:

| Mốc hoặc metric | Câu hỏi |
| --- | --- |
| JobExecution ID, StepExecution ID | Phần việc Spring Batch nào? |
| Partition name / window/range | Worker sở hữu input gì? |
| Request correlation ID | Reply thuộc request nào? |
| Publish timestamp | Manager đã giao việc chưa? |
| Broker queue age / lag | Request đã chờ bao lâu? |
| Worker receive/start timestamp | Có inbound consumer không? |
| Chunk transaction duration | Worker chậm ở DB hay xử lý CPU? |
| DB commit/rollback count | Có transaction thất bại hay đã commit? |
| Reply publish/receive timestamp | Manager chậm vì reply hoặc worker? |
| ACK/redelivery/offset status | Message có thể được giao lại không? |
| Retry attempts / DLQ | Lỗi được phục hồi hay bị cách ly? |
| Connection wait / lock wait | Có bottleneck khi tăng worker không? |

Log ví dụ:

~~~text
jobExecutionId=9301
stepExecutionId=9350
partitionName=partition-4
logicalWorkId=chunk-0071
correlationId=run-9301-step-9350-chunk-71
workerInstance=batch-worker-02
requestReceivedAt=2026-11-26T02:12:03Z
chunkCommitted=true
replyPublished=false
redeliveryCount=1
recoveryAction=RECONCILE
~~~

Đây là dữ liệu minh họa. Không đưa token, payload nhạy cảm hoặc thông tin cá nhân vào log. Các ID động nên phục vụ **structured logs/traces**; tránh dùng chúng làm label metric có cardinality rất lớn.

## 26. Đo throughput mà không bỏ qua correctness

Một benchmark phân tán cần phân biệt **lượng công việc thử xử lý** với **lượng dữ liệu thực sự commit hợp lệ**.

\[
R_{\mathrm{useful}}
=\frac{N_{\mathrm{valid\ committed\ items}}}
{T_{\mathrm{end-to-end}}}
\]

Nếu 20% message bị retry, metric `messages_processed_total` có thể tăng nhưng không đồng nghĩa throughput nghiệp vụ tăng.

### Các số cần so cùng lúc

- Tổng thời gian JobExecution, không chỉ thời gian mỗi worker step.
- `readCount`, `writeCount`, `filterCount`, `skipCount`.
- Business key reconciliation và checksum nội dung.
- p50/p95/p99 chunk duration, queue age, request-to-reply latency.
- Số chunk inflight, retry, rollback, duplicate, DLQ.
- CPU, heap/GC, connection pool wait, DB I/O, lock wait.
- Số worker JVM, consumer threads, partition count, chunk size.
- Thời gian restart và thời gian phục hồi sau worker crash.

### So sánh một biến mỗi lần

Nếu tăng từ bốn lên tám worker, giữ dataset, DB sizing, chunk size và chính sách retry ổn định trước khi kết luận nguyên nhân. Nếu vừa đổi index vừa tăng worker và đổi broker prefetch, không thể biết thay đổi nào tạo ra lợi ích.

**Benchmark chỉ được coi là PASS khi output đúng.** Một cấu hình ghi nhanh nhưng bỏ sót hoặc trùng item không được xếp là phương án hiệu năng tốt.

## 27. Tình huống thực tế: 18 triệu giao dịch và tám worker

Một hệ thống phải xử lý **18.000.000 giao dịch** trong **35 phút**. Manager đọc dữ liệu theo business date, chia chunk 500 item rồi gửi qua RabbitMQ cho các worker để chuẩn hóa và ghi vào DB đích.

Thông lượng tối thiểu lý tưởng:

\[
R_{\mathrm{required}}
=\frac{18.000.000}{35\times60}
\approx 8.571\ \mathrm{items/s}
\]

Số chunk lý tưởng khi không filter và mỗi chunk đủ 500 item:

\[
N_{\mathrm{chunks}}
=\frac{18.000.000}{500}=36.000
\]

Các con số tính toán là lý tưởng: còn overhead khởi tạo, chờ message, retry, transaction và bước cuối.

### Thiết kế test theo cấp

**Cấp 1 — Unit/Step tests**

- Reader trả đúng giao dịch theo ngày.
- Processor chuẩn hóa đúng và filter theo chính sách.
- Writer dùng business key/unique constraint phù hợp.
- Step lưu checkpoint và restart đúng khi lỗi trước commit.

**Cấp 2 — In-memory IntegrationFlow**

- Manager-side transformer/gateway routing hợp lệ.
- Header correlation không bị ghi đè.
- Worker handler nhận payload/metadata kiểu đúng.
- Reply A và B có thể đến đảo thứ tự mà vẫn ghép đúng.

**Cấp 3 — RabbitMQ + PostgreSQL Testcontainers**

- Request qua queue thật và worker nhận được.
- Payload được convert đúng, reply quay về.
- ACK/redelivery theo adapter policy.
- DLQ/error handling hoạt động cho lỗi schema hoặc lỗi vượt retry.
- Không có side effect trùng với duplicate message.

**Cấp 4 — Hai hoặc nhiều JVM**

- Manager và worker chạy khác process.
- Worker A chết giữa chunk, worker B tiếp tục phần việc độc lập.
- Manager timeout khi reply mất, nhưng dữ liệu đã commit không bị ghi lại sai.
- Job restart không thay đổi input snapshot/cutoff.

### Kết quả benchmark giả định

| Cấu hình | Throughput hữu ích | Thời gian xấp xỉ theo N/R | Kết quả dữ liệu |
| --- | ---: | ---: | --- |
| Step tuần tự | 3.500 item/s | 85,7 phút | PASS |
| 2 workers | 6.500 item/s | 46,2 phút | PASS |
| 4 workers | 9.200 item/s | 32,6 phút | PASS |
| 8 workers | 11.600 item/s | 25,9 phút | PASS |
| 12 workers | 11.800 item/s | 25,4 phút | PASS nhưng DB wait tăng |
| 8 workers, duplicate không có idempotency | 12.000 item/s được báo | Không đáng tin | **FAIL** |

Đây là **số liệu giả định** để học cách đánh giá, không phải benchmark mặc định của Spring Batch. Phép `N/R` chỉ là ước lượng và phải được đối chiếu với thời gian JobExecution toàn tuyến.

### Cửa sổ lỗi quan trọng nhất

Trong bài test, worker 3 commit chunk chứa `transaction_id=9421`, sau đó bị kill trước khi reply đến manager. Broker hoặc manager có thể dẫn đến việc request được xem xét lại theo cơ chế phục hồi. Test phải xác nhận:

- Bản ghi `transaction_id=9421` không bị ghi đúp.
- Giá trị chuẩn hóa không thay đổi sai.
- Manager không nhầm reply của chunk kế tiếp với chunk bị trễ.
- JobRepository/manager trạng thái có thể giải thích.
- Khi restart, mọi transaction ID hợp lệ được xử lý đủ.

Nếu thiếu bài test này, hệ thống có thể đạt throughput nhưng chưa chứng minh được **độ tin cậy dưới sự cố thực**.

## 28. Kịch bản test matrix cho CI/CD

Một bộ kiểm thử có thể tổ chức theo mức chi phí:

| Nhóm CI | Thời điểm chạy | Thành phần | Tiêu chí |
| --- | --- | --- | --- |
| **Fast tests** | Mỗi commit | Partitioner, processor, idempotency rule, header mapping | Dưới ngưỡng timeout nhỏ, deterministic |
| **Batch integration** | Mỗi pull request | `JobLauncherTestUtils`, DB test, reader/writer, StepScope | Status + data assertions |
| **Messaging integration** | Mỗi pull request hoặc pipeline tích hợp | Broker Testcontainers + adapter + worker | Serialization, request/reply, retry |
| **Distributed fault suite** | Trước release hoặc pipeline chọn lọc | 2+ JVM, DB/broker, kill/restart | Không mất/trùng dữ liệu |
| **Performance/soak** | Định kỳ/trước thay đổi kiến trúc | Dữ liệu đại diện, monitoring | SLA và resource budget |
| **Disaster recovery drill** | Theo lịch vận hành | Broker/DB/JVM outage, replay | Runbook có thể thực thi |

Không cần làm mọi thứ trong một `@SpringBootTest` khổng lồ. Một test lỗi có mục tiêu rõ sẽ dễ chẩn đoán và ít flaky hơn.

### Test reports nên lưu gì?

- Commit/version ứng dụng và dependency Spring Batch/Integration.
- Cấu hình broker/DB container, message converter.
- Dataset ID, seed, business cutoff và số record.
- JobParameters, JobExecution/StepExecution IDs.
- Số worker JVM, consumer concurrency, chunk size/partition count.
- Fault injection point, thời điểm lỗi.
- Invariant/expected result, actual counts, missing/duplicate keys.
- Log correlation của request/reply bị lỗi.
- Thời gian chạy, queue lag, DB wait và trạng thái phục hồi.

Không cần giữ toàn bộ payload nhạy cảm; dùng record ID và checksum phù hợp khi điều tra.

## 29. Các lỗi phổ biến khi kiểm thử Batch + Integration

| Sai lầm | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| Chỉ assert `BatchStatus.COMPLETED` | Có thể vẫn sai business data | Đối soát keys/values/side effects |
| Chỉ dùng in-memory channel | Không thấy ACK, serialization, redelivery | Có broker integration test thật |
| Chạy manager và worker trong cùng JVM rồi gọi là remote test | Không thấy lỗi process/network | Test ít nhất hai JVM cho kiến trúc phân tán |
| `Thread.sleep(2000)` để đợi kết quả | Flaky hoặc kéo dài CI | Poll theo điều kiện + deadline |
| Test restart bằng identifying JobParameters mới | Không phải restart cùng JobInstance | Giữ nguyên params trong vòng retry/restart |
| Test database dùng chung không cleanup | Lỗi trùng dữ liệu giữa các test | Fixture/DB cô lập |
| Xóa JobRepository trước restart test | Mất checkpoint cần kiểm chứng | Giữ metadata của lần fail |
| Chỉ đếm `writeCount` | Trùng và thiếu có thể bù trừ | Kiểm tra tập business key |
| Không test commit-then-crash | Bỏ sót cửa sổ duplicate quan trọng | Kill sau commit trước ACK/reply |
| Coi broker ACK là DB commit | Hiểu sai delivery semantics | Quan sát cả hai ranh giới |
| Coi correlation ID là idempotency key | Retry khác execution có thể ghi trùng | Khóa nghiệp vụ bền vững |
| Nhiều tầng retry không có budget | Retry storm và backlog | Phân loại lỗi, giới hạn attempts |
| Test worker step nhưng không test manager | Chưa chứng minh dispatch/aggregation | Test topology manager–broker–worker |
| Không kiểm tra scope của reader | Có thể đọc trùng khi concurrency | Test StepScope/partition ranges |
| Không chụp metric DB | Tưởng tăng worker là tăng năng lực | Đo I/O, lock/connection wait |
| Cho fault tests dùng chung worker container | Nhiễu và flaky | Tách topology hoặc tuần tự hóa |
| Bỏ qua reply đến trễ | Ghép nhầm request sau | Correlation và timeout policy |
| DLQ được coi là hoàn thành | Mất work nghiệp vụ | Assert job state và runbook replay |

## 30. Checklist trước khi chấp nhận integration test suite

- [ ] Đã mô tả topology remote chunking hoặc remote partitioning chính xác.
- [ ] Đã chốt business invariant, input snapshot và expected output.
- [ ] Có unit test Partitioner và ranh giới dữ liệu không chồng lấn.
- [ ] Có StepScope test cho reader nhận đúng `ExecutionContext`.
- [ ] Có Batch test chạy Job/Step qua `JobLauncherTestUtils` hoặc API tương đương.
- [ ] Test restart dùng cùng identifying JobParameters.
- [ ] Có test `IntegrationFlow` in-memory cho router/header/transformer.
- [ ] Có broker test thật cho serialization, ACK/offset, retry và reply routing.
- [ ] Có ít nhất một distributed test với manager và worker khác JVM.
- [ ] Có test reply đảo thứ tự và correlation mapping đúng request.
- [ ] Có test duplicate request và duplicate reply.
- [ ] Có test worker chết trước commit, sau commit trước ACK/reply.
- [ ] Có idempotency/unique constraint/ledger hoặc cơ chế tương đương cho side effect.
- [ ] Có test DLQ/poison message và giới hạn retry budget.
- [ ] Có test timeout/late reply và reconciliation.
- [ ] Có kiểm tra thread safety của reader/processor/writer, singleton SDK.
- [ ] Không dùng `Thread.sleep` cố định làm điều kiện thành công chính.
- [ ] Có data isolation, schema migration và cleanup giữa các test.
- [ ] Có metrics read/write/rollback, queue lag, request-to-reply và DB wait.
- [ ] Benchmark chỉ PASS khi dữ liệu đúng sau fault injection và restart.
- [ ] Có báo cáo lỗi đủ IDs/correlation để tái hiện.
- [ ] Phạm vi test trong CI phù hợp thời gian và chi phí hạ tầng.

## 31. Câu hỏi tự kiểm tra

**1. Vì sao unit test ItemProcessor không đủ để xác nhận remote chunking chạy đúng?**

Vì nó không kiểm tra broker serialization, request/reply, transaction, ACK/redelivery, manager timeout hay hành vi khi nhiều worker hoàn thành đảo thứ tự. Cần thêm test flow, broker và nhiều JVM.

**2. Một JobExecution `COMPLETED` nhưng target có 99.999 record thay vì 100.000. Test nên kết luận gì?**

FAIL. Trạng thái framework không thay thế dữ liệu nghiệp vụ. Phải tìm business key thiếu và nguyên nhân từ reader, partition, filter/skip, transaction hoặc retry.

**3. Vì sao cần test kill worker sau DB commit nhưng trước reply?**

Vì đây là cửa sổ trạng thái không chắc chắn: manager chưa nhận xác nhận nhưng side effect đã xảy ra. Redelivery/restart có thể áp dụng lại nếu writer không idempotent.

**4. `StepScopeTestUtils` giúp kiểm tra điều gì?**

Nó tạo ngữ cảnh StepExecution cho test code, hỗ trợ kiểm tra late binding từ `stepExecutionContext`, reader state và `ItemStream` phù hợp. Nó không chứng minh transport qua broker.

**5. Vì sao dùng JobParameters mới cho lần chạy thứ hai không chứng minh restart?**

Nếu identifying params đổi, Spring Batch có thể tạo JobInstance khác. Restart phải tiếp tục cùng công việc logic, giữ metadata và phần dữ liệu đã commit từ lần fail.

**6. In-memory IntegrationFlow test pass có chứng minh Kafka/RabbitMQ header mapper đúng không?**

Không. Message converter, property mapping và byte encoding khi đi qua wire chỉ được kiểm chứng bằng transport/integration test phù hợp.

**7. Khi test reply B về trước A, assertion quan trọng nhất là gì?**

B ghép đúng request B và A ghép đúng A, không đếm duplicate response hai lần và không suy ra business commit order từ reply arrival.

**8. Vì sao một test COUNT(*) = N chưa đủ?**

Có thể có khóa thiếu và khóa trùng bù trừ nhau. Cần kiểm tra tập khóa duy nhất, giá trị theo business key và ràng buộc uniqueness.

**9. Vì sao một worker JVM với 8 consumer vẫn cần thread safety dù remote partitioning dùng nhiều process?**

Vì các consumer trong cùng JVM có thể cùng truy cập singleton reader/processor/writer/SDK không an toàn. Các JVM khác nhau không chia sẻ heap, nhưng cùng JVM vẫn có nhiều thread.

**10. DLQ có thể được xem là xử lý thành công một partition không?**

Không mặc định. DLQ cách ly message lỗi; manager/job phải giữ trạng thái thất bại/chưa hoàn tất theo hợp đồng và có runbook replay/đối soát.

**11. Tại sao cần dùng điều kiện + timeout thay vì sleep cố định trong test bất đồng bộ?**

Vì độ trễ scheduler/CI không cố định. Polling theo trạng thái mong đợi giảm flaky và cho thông tin rõ khi quá hạn.

**12. Khi tăng từ 4 lên 8 workers, throughput tăng 10% nhưng DB lock wait tăng gấp bốn. Có nên tuyên bố scaling thành công?**

Chưa. Cần xác minh SLA, throughput hữu ích, correctness dưới retry/restart, mức tài nguyên chấp nhận được và tính ổn định. Có thể 4 worker là lựa chọn ít rủi ro hơn.

**13. Remote partitioning và remote chunking khác nhau thế nào trong test case?**

Remote partitioning phải kiểm chứng StepExecution/ExecutionContext của từng partition và worker tự đọc phạm vi; remote chunking kiểm chứng manager đọc/chia chunk, broker request/reply và worker process/write. Không áp cùng một giả định về worker StepExecution cho cả hai.

**14. Một event đã commit mà cùng eventId được gửi lại với payload khác. Test phải làm gì?**

Báo conflict theo nghiệp vụ, không âm thầm coi là duplicate hợp lệ. Ledger hoặc version check cần phân biệt cùng ID/cùng payload với cùng ID/nội dung mâu thuẫn.

---

**Ghi nhớ:** **Kiểm thử tích hợp Batch và Integration là kiểm thử tính đúng xuyên qua ranh giới JVM, broker, transaction và checkpoint**. Hãy bắt đầu bằng dữ liệu/invariant xác định, dùng `spring-batch-test` cho execution và StepScope, dùng in-memory flow để kiểm tra routing, rồi dùng broker thật và nhiều JVM để kiểm tra delivery, correlation, timeout, retry, crash và restart. Kết quả chỉ đáng tin khi **JobRepository có trạng thái nhất quán, business data được đối soát, side effect lặp lại an toàn và throughput đáp ứng SLA**.
