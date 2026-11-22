# Mock external service trong kiểm thử Spring Batch

## 1. Vì sao cần mock dịch vụ ngoài?

Trong Spring Batch, một job có thể đọc dữ liệu từ file hoặc database, sau đó gọi HTTP API, gRPC service, hệ thống thanh toán, dịch vụ tra cứu khách hàng hoặc một hệ thống nội bộ trước khi quyết định ghi output. Những phụ thuộc này có thể chậm, tạm thời mất kết nối, giới hạn số request hoặc trả dữ liệu thay đổi theo thời gian.

Khi kiểm thử batch processing, **mock external service** là cách thay thế ranh giới giao tiếp với hệ thống ngoài bằng một đối tượng hoặc server có hành vi được kiểm soát. Test có thể chủ động tạo câu trả lời thành công, phản hồi nghiệp vụ từ chối, timeout, HTTP 429/503 và dữ liệu phản hồi sai schema mà không phụ thuộc vào dịch vụ thật.

Mục tiêu không dừng ở việc khẳng định một method đã được gọi. Một test Spring Batch có mock dịch vụ ngoài cần chứng minh:

- Dữ liệu đầu vào nào được gửi đến dịch vụ và khi nào.
- Job biến đổi hoặc lọc item đúng theo kết quả trả về.
- Retry, skip và fail diễn ra theo chính sách đã cấu hình.
- Các counter của Step và dữ liệu ghi cuối cùng phù hợp.
- Lỗi dịch vụ không dẫn đến công bố output sai hoặc xử lý trùng khi restart.

Ví dụ, job nhập đơn hàng cần gọi **CustomerRiskClient** để nhận điểm rủi ro cho từng khách hàng:

~~~text
orders.csv / staging_order
          |
          v
       ItemReader
          |
          v
      ItemProcessor --------> CustomerRiskClient --------> Dịch vụ thật
          |                       ^
          |                       |
          |                 Mock trong test
          v
       ItemWriter
          |
          v
    approved_order
~~~

Trong bài kiểm thử, cùng một job và processor được chạy nhưng phần phụ thuộc **CustomerRiskClient** được thay bằng hành vi xác định trước. Điều này giúp tập trung vào logic batch, giới hạn lỗi và transaction của Step.

## 2. Chọn đúng mức mock cho mục tiêu kiểm thử

Không có một kiểu mock phù hợp với mọi trường hợp. Ranh giới mô phỏng quyết định phần nào được kiểm chứng và phần nào vẫn cần một test khác.

| Phương pháp | Thay thế tại đâu? | Kiểm tra được | Chưa kiểm tra được |
|---|---|---|---|
| **Mockito mock interface** | Interface client được inject vào processor/writer | Quy tắc nghiệp vụ, retry/skip, tham số gọi, counter, output | HTTP serialization, status code, header, timeout thực |
| **Fake client có trạng thái** | Cùng interface client | Kịch bản nhiều lần gọi, request log, idempotency đơn giản | Giao thức và cấu hình network thật |
| **WireMock/MockWebServer** | HTTP server chạy cục bộ | URL, method, JSON, header, status, timeout, mapping lỗi trong adapter | Hành vi toàn bộ hệ thống production |
| **Service ảo trong môi trường tích hợp** | Endpoint mạng mô phỏng bằng container/service | Kết nối mạng, cấu hình auth thử nghiệm, flow end-to-end | Cam kết tương thích với dịch vụ thật nếu thiếu contract test |
| **Test contract/sandbox được cấp phép** | Dịch vụ tương thích thật | Tương thích schema, protocol và phiên bản API | Thường kém ổn định hơn test mock cục bộ |

Một cấu trúc thường dùng là:

1. **Unit test processor**: Mockito cho interface dịch vụ, kiểm tra quyết định trên từng item.
2. **Spring Batch integration test**: chạy Job/Step thật với mock client và database test, xác minh status, số lần retry, skip và output.
3. **HTTP adapter test**: dùng server giả lập cục bộ để kiểm tra endpoint, JSON, status, timeout và chuyển lỗi.
4. **Contract/integration test giới hạn**: kiểm tra tương thích với dịch vụ thật khi có môi trường phù hợp.

Không nên đặt mock quá sâu trong code xử lý. Nếu processor tự tạo HTTP client bằng toán tử **new**, test khó thay thế phụ thuộc; nên đưa lời gọi dịch vụ qua interface và dependency injection.

## 3. Ví dụ nghiệp vụ để xây dựng test

Giả sử job **importOrdersJob** xử lý mỗi đơn gồm **orderId**, **customerId** và **amount**. Processor gọi dịch vụ để lấy điểm rủi ro nguyên từ 0 đến 100.

Hợp đồng nghiệp vụ của ví dụ:

| Kết quả từ dịch vụ | Hành vi mong đợi |
|---|---|
| Điểm 0–75 | Chấp nhận đơn, ghi vào bảng approved_order |
| Điểm 76–100 | Lọc đơn, processor trả về null; tăng filterCount |
| Điểm ngoài 0–100 | Dữ liệu phản hồi không hợp lệ; ném InvalidRiskResponseException; có thể skip theo policy |
| Dịch vụ tạm không khả dụng | Ném RiskTimeoutException; retry có giới hạn |
| Lỗi đã retry hết lần mà vẫn không thành công | Step FAILED nếu exception không được phép skip |
| Không tìm được file đầu vào hoặc mất kết nối DB ghi output | Step FAILED theo chính sách vận hành |

Điểm rủi ro cao được **lọc** theo nghiệp vụ, không phải lỗi kỹ thuật. Phản hồi điểm 120 là lỗi dữ liệu của dịch vụ, còn timeout là lỗi tạm thời. Phân biệt ba loại giúp cấu hình đúng **filter**, **skip** và **retry**.

Để tập trung vào logic batch, giả sử một item đầu vào sinh tối đa một bản ghi đích và writer dùng database cùng transaction manager của Step.

## 4. Tách interface dịch vụ ngoài khỏi processor

Đầu tiên, định nghĩa hợp đồng Java mà batch sử dụng:

~~~java
public interface CustomerRiskClient {
    int scoreFor(String customerId);
}

public record RawOrder(
        String orderId,
        String customerId,
        java.math.BigDecimal amount) {
}

public record ApprovedOrder(
        String orderId,
        String customerId,
        java.math.BigDecimal amount,
        int riskScore) {
}

public class RiskTimeoutException extends RuntimeException {
    public RiskTimeoutException(String message) {
        super(message);
    }
}

public class InvalidRiskResponseException extends RuntimeException {
    public InvalidRiskResponseException(String message) {
        super(message);
    }
}
~~~

Trong ứng dụng thật, một HTTP adapter triển khai **CustomerRiskClient** và chuyển phản hồi từ dịch vụ sang dữ liệu domain. Các trường hợp 503, connection timeout và response JSON không hợp lệ cần được phân loại rõ theo contract; nếu ném chung **RuntimeException** thì cấu hình retry/skip khó bảo đảm chính xác.

Processor không biết URL, token hay HTTP client. Nó chỉ dùng interface:

~~~java
import org.springframework.batch.item.ItemProcessor;
import org.springframework.context.annotation.Bean;

@Bean
public ItemProcessor<RawOrder, ApprovedOrder> riskProcessor(
        CustomerRiskClient customerRiskClient) {

    return order -> {
        int score = customerRiskClient.scoreFor(order.customerId());

        if (score < 0 || score > 100) {
            throw new InvalidRiskResponseException(
                    "Invalid risk score for orderId=" + order.orderId());
        }

        if (score > 75) {
            return null; // Filter theo quy tắc nghiệp vụ
        }

        return new ApprovedOrder(
                order.orderId(),
                order.customerId(),
                order.amount(),
                score);
    };
}
~~~

Khi test, Mockito có thể quyết định giá trị trả về của **scoreFor** mà không phải sửa processor hoặc thay code production. Nếu dịch vụ thực cung cấp thông tin lý do, version của thuật toán chấm điểm hoặc thời điểm quyết định, hãy đưa các trường đó vào response object thay vì ép mọi kết quả vào số nguyên.

### Lưu ý về tính lặp lại

Một lần retry có thể gọi lại processor. Nếu điểm rủi ro thay đổi giữa các lần gọi, cùng item có thể nhận quyết định khác nhau. Đối với dữ liệu nhạy cảm hoặc job phải restart ổn định, cần quy định rõ phiên bản kết quả của dịch vụ, cache/snapshot theo batch, hoặc kiểm soát thời điểm request. Mock test nên tạo được cả tình huống kết quả ổn định lẫn thay đổi có chủ đích.

## 5. Cấu hình Job/Step để test được với mock

Ví dụ dưới dùng phong cách Spring Batch 5+ với **JobRepository** và **PlatformTransactionManager** được inject. Tập trung vào cách ghép reader, processor, writer và fault tolerance.

### 5.1. Reader nhận file qua job parameter

~~~java
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.core.io.FileSystemResource;

@Bean
@StepScope
public FlatFileItemReader<RawOrder> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<RawOrder>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .linesToSkip(1)
            .delimited()
            .names("orderId", "customerId", "amount")
            .fieldSetMapper(fields -> new RawOrder(
                    fields.readString("orderId"),
                    fields.readString("customerId"),
                    fields.readBigDecimal("amount")))
            .build();
}
~~~

**@StepScope** bảo đảm file được resolve khi Step chạy với job parameter của lần thực thi cụ thể. Reader stateful không nên bị chia sẻ giữa các job execution đồng thời.

### 5.2. Writer ghi output có thể đối soát

Giả sử bảng đích trong database test:

~~~sql
CREATE TABLE approved_order (
    order_id    VARCHAR(50) PRIMARY KEY,
    customer_id VARCHAR(50) NOT NULL,
    amount      DECIMAL(18, 2) NOT NULL,
    risk_score  INTEGER NOT NULL
);
~~~

Writer minh họa:

~~~java
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@Bean
public ItemWriter<ApprovedOrder> approvedOrderWriter(
        JdbcTemplate jdbcTemplate) {

    return chunk -> {
        for (ApprovedOrder order : chunk) {
            jdbcTemplate.update(
                    """
                    INSERT INTO approved_order
                        (order_id, customer_id, amount, risk_score)
                    VALUES (?, ?, ?, ?)
                    """,
                    order.orderId(),
                    order.customerId(),
                    order.amount(),
                    order.riskScore());
        }
    };
}
~~~

Ở môi trường production, bảng nên có khóa **batchId** hoặc business key phù hợp, cùng quy tắc idempotency để chống duplicate khi restart. Writer JDBC tham gia rollback của chunk khi dùng datasource và transaction manager nhất quán; lời gọi HTTP không tự động là một phần của transaction DB.

### 5.3. Retry và skip có chủ đích

~~~java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step riskStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        FlatFileItemReader<RawOrder> orderReader,
        ItemProcessor<RawOrder, ApprovedOrder> riskProcessor,
        ItemWriter<ApprovedOrder> approvedOrderWriter) {

    return new StepBuilder("riskStep", jobRepository)
            .<RawOrder, ApprovedOrder>chunk(2, transactionManager)
            .reader(orderReader)
            .processor(riskProcessor)
            .writer(approvedOrderWriter)
            .faultTolerant()
            .retry(RiskTimeoutException.class)
            .retryLimit(3)
            .skip(InvalidRiskResponseException.class)
            .skipLimit(1)
            .build();
}

@Bean
public Job importOrdersJob(JobRepository jobRepository, Step riskStep) {
    return new JobBuilder("importOrdersJob", jobRepository)
            .start(riskStep)
            .build();
}
~~~

Trong cấu hình minh họa:

- **RiskTimeoutException** được retry tối đa ba lần thử, tính cả lần đầu. Nếu vẫn thất bại, exception này không thuộc nhóm skip và Step sẽ FAILED.
- **InvalidRiskResponseException** được phép skip tối đa một item trong Step.
- Điểm rủi ro lớn hơn 75 là filter theo nghiệp vụ; **filterCount** tăng, không tăng **processSkipCount**.
- **skipLimit** áp dụng cho tổng skip của Step, không phải mỗi loại exception.

Chính sách retry và skip phải phản ánh tính chất dịch vụ ngoài. Không cấu hình **skip(Exception.class)** hoặc retry mọi exception vì có thể che giấu lỗi lập trình, xác thực, dữ liệu nhạy cảm hoặc lỗi cấu hình.

## 6. Thiết kế dữ liệu test và kịch bản mock

File dữ liệu test **orders.csv**:

~~~csv
orderId,customerId,amount
O001,C001,120.00
O002,C002,80.50
O003,C003,60.00
~~~

Định nghĩa kết quả mock:

| Item | Call tới dịch vụ | Response mock | Kỳ vọng |
|---|---|---|---|
| O001 | scoreFor("C001") | 20 | Ghi vào approved_order |
| O002 | scoreFor("C002") | 90 | Filter, không ghi |
| O003 | scoreFor("C003") | 120 | Process skip do response ngoài khoảng |

Với file trên và Step đã định nghĩa:

| Chỉ số/kết quả | Expected |
|---|---:|
| readCount | 3 |
| readSkipCount | 0 |
| filterCount | 1 |
| processSkipCount | 1 |
| writeSkipCount | 0 |
| writeCount | 1 |
| Số dòng output | 1 |
| order_id xuất hiện ở đích | O001 |
| Job BatchStatus | COMPLETED |

Test nên kiểm tra cả **counter** và **dữ liệu thực tế**. Nếu chỉ kiểm tra mock được gọi ba lần, vẫn có thể bỏ sót lỗi khi processor ghi nhầm O002 hoặc ghi sai risk_score.

## 7. Integration test Spring Batch với Mockito

Spring Batch Test hỗ trợ khởi chạy Job trong kiểm thử qua **JobLauncherTestUtils**. Với Spring Framework 6.2+/Spring Boot tương thích, dùng **@MockitoBean** để thay bean client bằng mock trong application context. Với phiên bản Spring Boot cũ hơn, dự án có thể dùng **@MockBean** theo API của phiên bản đó.

Các điều kiện của ví dụ:

1. Có ứng dụng Spring Boot chứa các bean Job, Step, reader, processor, writer ở trên.
2. Context test có **một Job** phù hợp hoặc JobLauncherTestUtils được cấu hình trỏ đúng Job.
3. Database test đã có schema metadata Spring Batch và bảng **approved_order**.
4. Tự điều khiển launch thay vì để Boot chạy job khi khởi động context.
5. Mỗi test có output database được cô lập, không ảnh hưởng các test chạy song song.

Với dự án dùng Spring Boot dependency management, có thể khai báo các thư viện test tương ứng:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
}
~~~

Ví dụ JUnit 5:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.UUID;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
class RiskEnrichmentBatchIT {

    @MockitoBean
    CustomerRiskClient riskClient;

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @TempDir
    Path workDir;

    @BeforeEach
    void clearOutput() {
        // Chỉ chạy trong DB test riêng dành cho class này.
        jdbcTemplate.update("DELETE FROM approved_order");
    }

    @Test
    void handlesApprovalFilteringAndInvalidResponse() throws Exception {
        when(riskClient.scoreFor("C001")).thenReturn(20);
        when(riskClient.scoreFor("C002")).thenReturn(90);
        when(riskClient.scoreFor("C003")).thenReturn(120);

        JobExecution execution = launch(
                """
                orderId,customerId,amount
                O001,C001,120.00
                O002,C002,80.50
                O003,C003,60.00
                """);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        StepExecution step = execution.getStepExecutions().stream()
                .filter(e -> "riskStep".equals(e.getStepName()))
                .findFirst()
                .orElseThrow();

        assertEquals(3L, step.getReadCount());
        assertEquals(0L, step.getReadSkipCount());
        assertEquals(1L, step.getFilterCount());
        assertEquals(1L, step.getProcessSkipCount());
        assertEquals(0L, step.getWriteSkipCount());
        assertEquals(1L, step.getWriteCount());

        List<String> ids = jdbcTemplate.queryForList(
                "SELECT order_id FROM approved_order ORDER BY order_id",
                String.class);
        assertEquals(List.of("O001"), ids);

        Integer score = jdbcTemplate.queryForObject(
                "SELECT risk_score FROM approved_order WHERE order_id = ?",
                Integer.class, "O001");
        assertEquals(20, score);

        verify(riskClient).scoreFor("C001");
        verify(riskClient).scoreFor("C002");
        verify(riskClient).scoreFor("C003");
    }

    private JobExecution launch(String csvContent) throws Exception {
        Path input = workDir.resolve(UUID.randomUUID() + ".csv");
        Files.writeString(input, csvContent, StandardCharsets.UTF_8);

        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", input.toAbsolutePath().toString())
                .addString("testRunId", UUID.randomUUID().toString())
                .toJobParameters();

        return jobLauncherTestUtils.launchJob(parameters);
    }
}
~~~

Các phương thức test sau có thể được thêm vào cùng class, sử dụng hàm **launch** ở trên. Khi có nhiều Job trong context, cần set đúng Job cho **JobLauncherTestUtils** thay vì để nó chọn ngẫu nhiên. Nếu test chạy song song, cách xóa toàn bảng bằng **@BeforeEach** có thể gây tranh chấp; nên dùng database riêng, transaction cô lập hoặc partition dữ liệu theo test ID.

**Điểm cần phân biệt:** mock ở interface **CustomerRiskClient** giúp xác minh batch logic nhưng không thực hiện HTTP request. Nó không chứng minh URL, JSON, request header hoặc cách adapter dịch lỗi HTTP đã chính xác.

## 8. Mock lỗi tạm thời để kiểm tra retry

Khi dịch vụ tạm thời timeout, retry cần gọi lại đúng item và tiếp tục ghi khi dịch vụ phục hồi. Với một item duy nhất và processor side effect-free, Mockito có thể mô phỏng hai lần lỗi rồi thành công.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@Test
void retriesTransientRiskServiceFailureAndThenSucceeds() throws Exception {
    when(riskClient.scoreFor("C001"))
            .thenThrow(new RiskTimeoutException("temporary timeout"))
            .thenThrow(new RiskTimeoutException("temporary timeout"))
            .thenReturn(25);

    JobExecution execution = launch(
            """
            orderId,customerId,amount
            O001,C001,120.00
            """);

    assertEquals(BatchStatus.COMPLETED, execution.getStatus());
    verify(riskClient, times(3)).scoreFor("C001");

    assertEquals(1L, jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM approved_order",
            Long.class));
}
~~~

Nếu mock luôn ném timeout:

~~~java
@Test
void failsWhenRiskServiceRetryIsExhausted() throws Exception {
    when(riskClient.scoreFor("C001"))
            .thenThrow(new RiskTimeoutException("still unavailable"));

    JobExecution execution = launch(
            """
            orderId,customerId,amount
            O001,C001,120.00
            """);

    assertEquals(BatchStatus.FAILED, execution.getStatus());
    verify(riskClient, times(3)).scoreFor("C001");
}
~~~

Trong trường hợp minh họa, **retryLimit(3)** quy định tối đa ba lần thử (lần đầu và những lần retry). Tên exception phải nằm trong cấu hình retry; nếu HTTP adapter bọc nó thành một kiểu exception khác, cần sửa phân loại lỗi hoặc cấu hình phù hợp.

**Không dùng số lần gọi mock làm bằng chứng duy nhất về retry trong mọi job.** Nếu lỗi xảy ra khi writer, rollback chunk có thể làm processor được gọi lại. Với chunk nhiều item, stateful retry, cache và các bước xử lý khác, số lần gọi tổng thể có thể khác mô hình một item ở ví dụ trên.

## 9. Mock lỗi không thể bỏ qua và skip-limit

Mô phỏng hai item có response sai trong khi cấu hình chỉ cho phép **skipLimit(1)**:

~~~java
@Test
void failsWhenMoreThanOneInvalidResponseIsSkipped() throws Exception {
    when(riskClient.scoreFor("C001")).thenReturn(120);
    when(riskClient.scoreFor("C002")).thenReturn(-1);

    JobExecution execution = launch(
            """
            orderId,customerId,amount
            O001,C001,120.00
            O002,C002,80.50
            """);

    assertEquals(BatchStatus.FAILED, execution.getStatus());
}
~~~

Kết quả **FAILED** là chủ đích: quá nhiều phản hồi không hợp lệ chứng tỏ không thể tin cậy vào output. Trong job thực tế, cần thêm dấu trạng thái xuất bản để consumer không đọc nhầm output còn dở dang.

Cần có một test riêng cho exception **không được retry và không được skip**, ví dụ lỗi xác thực bắt buộc hoặc lỗi cấu hình endpoint. Mục tiêu là chứng minh policy không nuốt mọi exception. Với response HTTP 404, 401 hay 429, quyết định retry/skip/fail phải xuất phát từ contract API cụ thể; không thể suy ra một chính sách chung đúng cho tất cả dịch vụ.

## 10. Mock HTTP server để test chính adapter

Mockito ở interface rất nhanh, nhưng bỏ qua lớp giao thức. Nếu cần kiểm tra URL, query parameter, header, mapping JSON, HTTP 503, response body sai schema và timeout, hãy dựng một **HTTP stub server** chạy cục bộ bằng WireMock hoặc OkHttp MockWebServer, sau đó để HTTP adapter thật gọi đến cổng do test cấp.

Ví dụ hợp đồng REST giả định:

~~~http
GET /risk/C001 HTTP/1.1
Accept: application/json
X-Correlation-Id: test-run-123
~~~

Response thành công:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"score":20}
~~~

Response báo lỗi tạm thời:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{"code":"TEMPORARILY_UNAVAILABLE"}
~~~

Ví dụ thiết lập WireMock theo phong cách JUnit 5:

~~~java
import static com.github.tomakehurst.wiremock.client.WireMock.get;
import static com.github.tomakehurst.wiremock.client.WireMock.okJson;
import static com.github.tomakehurst.wiremock.client.WireMock.urlEqualTo;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.wireMockConfig;

import com.github.tomakehurst.wiremock.junit5.WireMockExtension;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.RegisterExtension;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

class CustomerRiskHttpAdapterIT {

    @RegisterExtension
    static WireMockExtension riskApi = WireMockExtension.newInstance()
            .options(wireMockConfig().dynamicPort())
            .build();

    @DynamicPropertySource
    static void riskProperties(DynamicPropertyRegistry registry) {
        registry.add("risk.base-url", riskApi::baseUrl);
    }

    @Test
    void mapsSuccessfulHttpResponse() {
        riskApi.stubFor(get(urlEqualTo("/risk/C001"))
                .willReturn(okJson("{\"score\":20}")));

        // Gọi CustomerRiskClient HTTP adapter thật từ Spring context.
        // Assert kết quả scoreFor("C001") == 20 và request đã khớp stub.
    }
}
~~~

Đoạn trên minh họa phần **server stub**; để chạy nguyên vẹn cần bổ sung **@SpringBootTest** hoặc cấu hình test context, inject adapter thật và có dependency WireMock tương thích. Tên property **risk.base-url** phải khớp property HTTP adapter của ứng dụng. Lớp này **không dùng @MockitoBean cho CustomerRiskClient**, vì làm vậy sẽ thay adapter thật và server giả lập không bao giờ nhận request.

Một bộ test adapter nên xác minh:

| Tình huống stub HTTP | Kết quả mong đợi từ adapter |
|---|---|
| 200 + JSON đúng schema | Parse thành điểm rủi ro đúng |
| 200 + JSON thiếu trường bắt buộc | Lỗi response data được phân loại rõ |
| 200 + JSON sai kiểu hoặc score ngoài khoảng | Không âm thầm nhận giá trị mặc định sai |
| 503, 429 theo hợp đồng | Exception tạm thời phù hợp cơ chế retry và backoff |
| 401/403 do credential không hợp lệ | Phân loại lỗi xác thực; thường fail và cảnh báo |
| 404 | Theo ngữ nghĩa API: not found hợp lệ hay lỗi nghiêm trọng |
| Kết nối bị đóng, response chậm vượt timeout | Lỗi mạng được chuyển thành exception retryable khi phù hợp |
| Header thiếu, URL hoặc body không đúng | Stub không khớp và test thất bại rõ nguyên nhân |

**Timeout** thường cần cấu hình thời gian chờ của client ngắn trong test, thay vì để test đợi theo timeout production. **Backoff** cũng có thể cấu hình thấp cho test, đồng thời tách logic chọn delay ra thành thành phần có thể kiểm thử nếu cần xác minh thời gian.

Để tránh test rời rạc, cần có ít nhất một đường đi kết hợp: HTTP stub trả 503 rồi 200, HTTP adapter chuyển lỗi thành **RiskTimeoutException**, Step retry và cuối cùng ghi đúng một record. Đây là cách xác nhận việc gắn nối giữa adapter và Spring Batch mà mock interface đơn lẻ chưa chứng minh.

## 11. Ghi nhận tham số gọi và hành vi quan trọng

Mockito cho phép xác minh processor gửi đúng **customerId**, không gửi nhầm **orderId**:

~~~java
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.never;
import static org.mockito.ArgumentMatchers.anyString;

verify(riskClient).scoreFor("C001");
verify(riskClient, never()).scoreFor("O001");
~~~

Nếu API nhận một request object chứa batchId, requestId và idempotency key, có thể sử dụng **ArgumentCaptor** để kiểm tra các trường đó:

~~~java
// Ví dụ tổng quát với một interface khác:
// ArgumentCaptor<RiskRequest> captor =
//         ArgumentCaptor.forClass(RiskRequest.class);
// verify(riskClient).evaluate(captor.capture());
// assertEquals("BATCH-42", captor.getValue().batchId());
~~~

Chỉ assert các tham số là **hợp đồng nghiệp vụ**. Tránh test buộc processor phải gọi service theo đúng thứ tự khi job được phép chạy song song hoặc khi rollback làm item được xử lý lại. Các assertion quá gắn với chi tiết triển khai dễ hỏng dù output vẫn đúng.

Với dịch vụ có thao tác ghi, ví dụ **chargePayment**, **reserveInventory**, hoặc **sendNotification**, chỉ mock response thành công là chưa đủ. Cần assert request có khóa idempotency ổn định, và ở test tích hợp giả lập phải xác định việc lặp cùng request có gây side effect mới hay không.

## 12. Mô phỏng side effect, retry và idempotency

Khi processor chỉ **tra cứu** dịch vụ, retry thường ít rủi ro hơn khi processor **thay đổi trạng thái** của dịch vụ. Với hoạt động tạo giao dịch bên ngoài, một tình huống quan trọng là:

~~~text
Batch gửi request thanh toán
       |
       v
Dịch vụ ngoài đã xử lý thành công
       |
       v
Response về Batch bị timeout
       |
       v
Batch retry cùng yêu cầu
~~~

Nếu request thứ hai dùng khóa khác, có thể tạo giao dịch trùng. Test nên giả lập “xử lý thành công nhưng mất response”, thay vì chỉ giả lập “dịch vụ chưa xử lý gì và trả 503”.

Một **fake có trạng thái** có thể lưu khóa idempotency và kết quả theo khóa:

~~~java
import java.util.HashMap;
import java.util.Map;

final class FakeReservationService {
    private final Map<String, String> reservationIdsByKey = new HashMap<>();
    private int newReservations;

    String reserve(String idempotencyKey) {
        return reservationIdsByKey.computeIfAbsent(idempotencyKey, key -> {
            newReservations++;
            return "RES-" + newReservations;
        });
    }

    int newReservations() {
        return newReservations;
    }
}
~~~

Đây là fake **không an toàn cho truy cập đa luồng** và chỉ dùng cho test tuần tự. Nếu Step chạy với task executor hoặc partitioning, dùng cấu trúc đồng bộ phù hợp hoặc server stub có log request thread-safe; tránh tạo race condition trong chính test.

Với hai lần gọi cùng idempotencyKey, test cần nhận cùng reservation ID và **newReservations() = 1**. Với hai khóa độc lập, số reservation mới là hai. Bộ test này kiểm tra cơ chế chống side effect trùng; nó không chứng minh dịch vụ thật đã triển khai idempotency đúng, nên vẫn cần contract/integration test khi có thể.

## 13. Mô phỏng phục hồi sau lỗi và restart

Spring Batch lưu checkpoint và metadata của **JobInstance / JobExecution / StepExecution**. Một job FAILED có thể được restart theo chính sách tương ứng. Khi test restart, mock dịch vụ ngoài phải mô phỏng cả hai lần thực thi, nhưng cần phân biệt:

- **Chạy lại cùng JobInstance**: giữ các identifying job parameters, dùng cơ chế restart sau execution FAILED hoặc STOPPED.
- **Chạy JobInstance mới**: thay đổi identifying parameters, dùng để kiểm thử các lần nhập độc lập.
- **Mock reset giữa hai lần chạy**: chỉ reset có chủ đích; nếu trạng thái dịch vụ là một phần của kịch bản restart thì phải giữ lại bằng fake/server phù hợp.

Kịch bản ví dụ:

1. Lần đầu, O001 nhận score 20 và một chunk commit; O002 gọi API bị timeout đến hết retry limit, job FAILED.
2. Dịch vụ phục hồi; job restart cùng input và JobInstance theo cơ chế Batch.
3. Test kiểm tra tập output cuối có mỗi order_id đúng một lần, đúng score, không tạo output trùng.
4. Chỉ sau khi job và bước đối soát hoàn tất, hệ thống mới đánh dấu batch READY.

Mock trả kết quả thành công trong lần hai chưa đủ để bảo đảm output không bị trùng. Test cần dùng **database state thật** hoặc fake mô phỏng side effect, kết hợp unique constraint và quy tắc upsert/skip phù hợp.

Khi reader dùng checkpoint theo vị trí của file, **không thay đổi nội dung file giữa các lần restart**. Nếu cần sửa input, dùng batch/version mới theo quy trình đã thiết kế. Điều này giúp test phản ánh cách khôi phục thực tế.

## 14. Concurrent Step, partitioning và rate limit

Với Step nhiều luồng, partitioning hoặc remote chunking, các lời gọi service có thể thực hiện đồng thời và thứ tự không xác định.

Một số nguyên tắc test:

- Không dựa vào **thứ tự gọi** nếu contract không yêu cầu thứ tự.
- Không chia sẻ iterator, queue hoặc counter mutable không đồng bộ giữa nhiều thread.
- Mock cần trả response theo **request key** (ví dụ customerId) thay vì chỉ theo thứ tự **thenReturn(A, B, C)**.
- Với partitioning, tách dữ liệu và output theo partition/batchId để dễ đối soát.
- Test rate limit bằng response 429 có chính sách retry/backoff xác định; nếu API có **Retry-After**, adapter cần parse và áp dụng theo thiết kế.
- Chú ý tổng request sau retry có thể lớn hơn readCount, đặc biệt khi chunk rollback.

Ví dụ test rate limit có thể cho server stub ghi timestamp các request để kiểm tra backoff, nhưng không nên dùng những ngưỡng thời gian quá sát khiến CI chạy chậm dễ thất bại ngẫu nhiên. Khi điều quan trọng là **quy tắc backoff**, tách policy hoặc sleeper/clock ra để kiểm tra độc lập; một integration test nhỏ chỉ cần xác minh client phản ứng đúng với 429/503.

## 15. Quản lý dữ liệu test, mock và trạng thái context

Các vấn đề khiến test phụ thuộc môi trường thường đến từ phần hạ tầng test, không phải logic batch:

| Vấn đề | Cách tổ chức phù hợp |
|---|---|
| Job tự chạy khi Spring Boot test khởi động | Thiết lập spring.batch.job.enabled=false |
| Có nhiều Job bean, utility không biết chọn Job nào | Gán Job cụ thể vào JobLauncherTestUtils |
| Reader singleton giữ state sau một execution | Dùng @StepScope và tạo reader theo execution |
| JobInstance đã COMPLETED nên không chạy lại cùng parameters | Dùng identifying parameter mới cho lần chạy độc lập |
| Test khác để lại dữ liệu ở bảng output | Database/schema test cô lập hoặc cleanup theo test/batchId |
| Mock còn stubbing hoặc interaction từ test trước | Theo vòng đời/reset của framework; kiểm soát state thủ công nếu dùng fake |
| HTTP mock trỏ tới port cố định | Dùng dynamic port và truyền base URL vào adapter |
| Test bị gọi đến endpoint thật | Inject mock client hoặc base URL server cục bộ; cô lập outbound network |
| Test concurrent có kết quả ngẫu nhiên | Mô phỏng theo request key, không dùng shared mutable state thiếu đồng bộ |
| Retry làm test chờ quá lâu | Timeout/backoff ngắn trong profile test |

Mock dùng trong test nên tạo ra **sai lệch rõ ràng khi thiếu stubbing**. Ví dụ, phương thức trả **int** của Mockito mặc định có thể trả **0**; nếu 0 là điểm rủi ro hợp lệ thì một call chưa stub có thể âm thầm được chấp thuận. Có thể cấu hình mock với câu trả lời mặc định nghiêm ngặt, đổi interface trả về object có thể kiểm soát null, hoặc xác minh đầy đủ các request/kết quả quan trọng trong test. Không nên coi default return value là phản hồi hợp lệ của dịch vụ.

Với dữ liệu nhạy cảm, không log nguyên access token, header Authorization, PII hoặc body thanh toán khi lưu interaction của mock server. Dùng dữ liệu tổng hợp và chỉ log correlation ID, loại lỗi, khóa test và thông số cần thiết.

## 16. Ma trận test nên có cho external service trong Batch

| Kịch bản | Hành vi mock | Điều quan trọng cần assert |
|---|---|---|
| Response thành công | Trả điểm hợp lệ | Output đúng giá trị và Job COMPLETED |
| Quy tắc lọc | Trả điểm nằm trong vùng từ chối | filterCount tăng; không sinh output |
| Response bất hợp lệ | Trả điểm ngoài khoảng/schema sai | Exception đúng loại; skip hoặc FAILED theo policy |
| Timeout rồi phục hồi | Hai lần timeout, lần ba thành công | Retry đúng giới hạn; ghi một bản ghi |
| Timeout kéo dài | Luôn ném retryable exception | Job FAILED; không công bố output |
| Skip đúng ngưỡng | Một response invalid khi skipLimit=1 | Job tiếp tục; processSkipCount=1 |
| Skip vượt ngưỡng | Hai response invalid | Job FAILED |
| Lỗi không được phép bỏ qua | Ném exception khác policy | Job FAILED ngay |
| HTTP 503 / 429 | Server stub trả status có retry | Adapter map lỗi đúng; test retry/backoff |
| HTTP 401 / 403 | Server stub trả lỗi auth | Không nuốt lỗi; cảnh báo/FAILED |
| Phản hồi JSON thiếu trường | Server stub trả body sai schema | Không dùng giá trị mặc định dẫn đến output sai |
| Timeout sau side effect thành công | Fake lưu side effect nhưng mất response | Retry giữ idempotency key, không nhân đôi side effect |
| Restart sau FAILED | Lần đầu lỗi, lần sau service phục hồi | JobInstance được restart đúng; output không trùng |
| Hai batch song song | Response khác nhau theo batch/request key | Không lẫn dữ liệu và không rò rỉ state |

Các assertion được ưu tiên theo bằng chứng: **Job/Step status → skip/retry/filter counters → output DB/file → giao tiếp với mock theo hợp đồng**. Tùy bài toán, có thể bổ sung audit, metric, tracing và kiểm tra trạng thái READY cho downstream.

## 17. Những sai lầm cần tránh

**Mock trực tiếp processor thay vì mock external client.** Khi đó test bỏ qua chính logic cần kiểm tra: mapping response, filter, retry/skip và quyết định ghi. Mock nên nằm ở ranh giới dịch vụ ngoài khi mục tiêu là kiểm thử Batch.

**Chỉ gọi processor thủ công rồi khẳng định Batch xử lý đúng.** Unit test processor cần thiết nhưng không kiểm tra chunk transaction, StepExecution, checkpoint, restart, skipLimit hoặc Job flow. Cần integration test dùng JobLauncherTestUtils cho các yêu cầu đó.

**Mock toàn bộ JDBC và JobRepository.** Có thể khiến test thiếu tín hiệu về transaction và dữ liệu thực đã commit. Đối với integration test, nên dùng database test có transaction semantics phù hợp.

**Mọi 4xx/5xx đều được retry hoặc skip.** HTTP status chỉ là tín hiệu kỹ thuật; retryability phụ thuộc contract, idempotency và ngữ cảnh nghiệp vụ.

**Trả response dựa vào thứ tự gọi ở Step song song.** Thứ tự không ổn định làm test flakiness. Tạo response theo khóa request và dùng bộ đếm thread-safe nếu cần.

**Không kiểm tra đầu ra thật.** Mockito verification có thể thành công ngay cả khi writer bỏ sót record, ghi nhầm khách hàng hoặc output trùng. Phải đối soát tập dữ liệu và giá trị cần thiết.

**Nhầm filter với skip.** Processor trả null là filter; ném exception skippable mới là skip. Kết quả và cảnh báo nghiệp vụ có thể khác nhau đáng kể.

**Quên tính đến retry khi dịch vụ có side effect.** Transaction database không rollback thanh toán hoặc request đã xử lý bên ngoài. Cần idempotency key, quy trình reconcile và test mất response sau thành công.

**Mock HTTP rồi vẫn inject mock của interface adapter.** Server giả lập không nhận request vì HTTP adapter đã bị thay thế. Test ở mỗi ranh giới phải rõ thành phần nào là thật, thành phần nào được mock.

**Chạy test phụ thuộc vào endpoint thật.** Điều này tạo chậm, tốn quota, dữ liệu khó lặp và có nguy cơ thay đổi state ngoài môi trường test. Mock cục bộ cho các trường hợp deterministic; tách contract test thật theo môi trường riêng.

## 18. Áp dụng vào một test infrastructure đáng tin cậy

Với Spring Batch Core Processing, một hạ tầng kiểm thử external service tốt có ba thành phần:

1. **Interface hoặc adapter rõ ràng** tách lời gọi dịch vụ ra khỏi ItemProcessor/ItemWriter.
2. **Fixture và mock có hành vi xác định** cho thành công, filter, invalid response, timeout, retry, skip-limit và lỗi không được phép bỏ qua.
3. **Bằng chứng từ Spring Batch và output** gồm JobExecution, StepExecution, dữ liệu đích, audit và khả năng restart không trùng.

Cách tổ chức này giúp kiểm thử được các quyết định thực sự ảnh hưởng tới kết quả batch, chủ động tái hiện lỗi dịch vụ ngoài và xác minh rằng job chỉ tiếp tục hoặc hoàn tất khi dữ liệu đầu ra vẫn đáp ứng hợp đồng đã định nghĩa.
