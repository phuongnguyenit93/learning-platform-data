# Thêm retry lỗi tạm thời trong dự án thực hành Spring Batch

## 1. Mục tiêu thực hành

Trong một dự án **Spring Batch Core Processing**, job nhập đơn hàng thường không chỉ đọc file và ghi database. Nó còn có thể gọi dịch vụ ngoài để lấy điểm rủi ro, tỷ giá, thông tin khách hàng hoặc trạng thái hợp đồng. Nếu dịch vụ đó có vài lần timeout hoặc trả HTTP 503 do quá tải ngắn, việc dừng toàn bộ job ngay ở lỗi đầu tiên có thể không cần thiết. Ngược lại, gọi lại vô hạn hoặc retry nhầm lỗi vĩnh viễn làm tốn tài nguyên, chậm deadline và có thể tạo side effect trùng.

Trong bài **Dự án thực hành → Thêm retry lỗi tạm thời**, ta xây một job đọc CSV, gọi **CustomerRiskClient** trong processor và ghi output qua JDBC. Spring Batch sẽ thử lại khi dịch vụ phát sinh exception được phân loại là **transient**, có **retry limit** và **backoff** rõ ràng. Nếu dịch vụ phục hồi, job tiếp tục; nếu hết số lần thử, job FAILED thay vì âm thầm bỏ record.

~~~text
orders.csv
    |
    v
FlatFileItemReader
    |
    v
ItemProcessor ---------> CustomerRiskClient
    |                           |
    |                     risk-service HTTP
    |                           |
    |                   timeout / 429 / 503
    |                           |
    |                   RETRY + BACKOFF
    v
ItemWriter (JDBC)
    |
    v
enriched_order
~~~

Sau khi thực hành, bạn cần nắm được:

- Phân biệt lỗi **transient** với lỗi **permanent** và lỗi dữ liệu.
- Cấu hình **faultTolerant**, **retry**, **retryLimit**, **backOffPolicy**.
- Xác minh một item lỗi hai lần rồi thành công ở lần thứ ba.
- Xác minh lỗi kéo dài gây **FAILED** và không xuất bản output thiếu.
- Hiểu retry khác **skip**, **filter**, **restart** và transaction rollback thế nào.
- Đảm bảo writer và các external side effects có chính sách **idempotency**.
- Viết test Spring Batch, test HTTP adapter và thu thập log/metric đúng mức.

Ví dụ dùng phong cách **Spring Batch 5+**, Java 17, JUnit 5 và Spring Boot. Chi tiết annotation test và cấu hình infrastructure có thể khác theo phiên bản framework đang dùng; những phần phụ thuộc phiên bản sẽ được chú thích.

## 2. Retry là gì?

Retry nghĩa là **thử lại một hoạt động đã gặp lỗi nhưng có khả năng phục hồi**, không phải xử lý lại mọi exception không phân biệt nguyên nhân.

Ví dụ:

~~~text
Attempt #1: gọi /risk/C001 -> timeout
                 |
               backoff
                 |
Attempt #2: gọi /risk/C001 -> HTTP 503
                 |
               backoff
                 |
Attempt #3: gọi /risk/C001 -> HTTP 200, score=35
                 |
                 v
          Processor thành công
                 |
                 v
          Writer + chunk commit
~~~

Với **retryLimit(3)** trong ví dụ này, số lần **attempt tối đa là ba, tính cả lần đầu**. Nếu lần thứ ba vẫn ném lỗi retryable, operation hết retry và Step xử lý lỗi theo các chính sách còn lại; nếu không có skip tương ứng, job thường FAILED.

### Retry không phải skip hoặc restart

| Cơ chế | Ý nghĩa | Ví dụ |
|---|---|---|
| Retry | Thử lại hoạt động đã lỗi | HTTP 503 rồi 200 |
| Skip | Chấp nhận bỏ qua item lỗi theo policy | Dòng CSV hỏng được phép đưa vào reject |
| Filter | Processor trả về null theo nghiệp vụ | Đơn hàng CANCELLED không cần output |
| Fail | Không thể tiếp tục theo policy hiện tại | API lỗi sau tất cả attempts |
| Restart | Tạo JobExecution mới cho cùng JobInstance đã FAILED/STOPPED khi đủ điều kiện | Chạy tiếp từ checkpoint đã lưu |

Retry xảy ra **trong một lần thực thi Step**; restart xảy ra sau một JobExecution khác đã kết thúc không thành công hoặc bị dừng. Một JobInstance có thể có nhiều JobExecution, nhưng mỗi lần retry processor **không tạo JobExecution mới**.

## 3. Chính sách retry của dự án

Giả sử risk-service trả điểm nguyên từ **0 tới 100**. Job cần ghi điểm đã xác thực vào bảng kết quả.

| Tình huống | Phân loại | Cách xử lý |
|---|---|---|
| HTTP 200, score hợp lệ | Thành công | Ghi output |
| Connect/read timeout tạm thời | Transient | Retry nếu replay an toàn |
| HTTP 502/503/504 | Transient theo API contract | Retry |
| HTTP 429 | Throttling | Retry có backoff và xem Retry-After |
| HTTP 400/422 | Permanent | Fail hoặc nghiệp vụ riêng, không retry mù |
| HTTP 401/403 | Xác thực/ủy quyền | Fail và cảnh báo |
| HTTP 404 | Tùy contract | Không mặc định retry |
| HTTP 200 nhưng thiếu score | Sai response | Fail, không chấp nhận điểm mặc định |
| Score âm hoặc trên 100 | Sai business response | Fail hoặc quy trình kiểm soát riêng |
| Amount bằng 0 hoặc âm | Lỗi input | Không retry để mong số tiền tự thay đổi |
| NullPointerException | Lỗi lập trình | Không retry chung |

Chính sách bài này:

1. **TransientRiskServiceException** được retry tối đa ba lần.
2. Dùng **fixed backoff 200 ms** trong bản demo.
3. **PermanentRiskServiceException** và **InvalidOrderException** không retry.
4. Không skip lỗi transient hết retry; Job FAILED để không đánh mất đơn hàng.
5. API chấm điểm chỉ đọc dữ liệu, không tạo side effect ở phía dịch vụ.
6. Output phải có một hàng cho mỗi order hợp lệ, được đối soát theo business key.

**200 ms chỉ là số demo.** Production nên cân nhắc exponential backoff, jitter, timeouts, deadline, Retry-After và concurrency limit theo năng lực dịch vụ ngoài.

## 4. Dữ liệu đầu vào và bảng đích

Tạo file **orders.csv**:

~~~csv
orderId,customerId,amount
O001,C001,120.00
O002,C002,50.00
O003,C003,80.50
O004,C004,25.00
~~~

Giả sử service trả:

| Order | Customer | Score |
|---|---|---:|
| O001 | C001 | 35 |
| O002 | C002 | 10 |
| O003 | C003 | 60 |
| O004 | C004 | 20 |

Bảng đích:

~~~sql
CREATE TABLE enriched_order (
    batch_id     VARCHAR(64) NOT NULL,
    order_id     VARCHAR(64) NOT NULL,
    customer_id  VARCHAR(64) NOT NULL,
    amount       DECIMAL(18, 2) NOT NULL,
    risk_score   INTEGER NOT NULL,
    PRIMARY KEY (batch_id, order_id)
);
~~~

**batchId** là định danh lô nghiệp vụ, không phải JobExecutionId. Khi job restart cùng JobInstance, output đã commit trước đó vẫn phải được xét trong cùng batchId. Khóa chính hỗ trợ chống duplicate vật lý, nhưng nếu writer vẫn dùng INSERT thuần, việc replay record đã có có thể phát sinh constraint violation; đây **chưa phải idempotency hoàn chỉnh**.

Job nhận hai JobParameters quan trọng:

- **inputFile**: đường dẫn input snapshot bất biến trong suốt một JobInstance.
- **batchId**: khóa nghiệp vụ để ghi và đối soát output.

Trong test độc lập có thể thêm **testRunId** ngẫu nhiên nhằm tạo JobInstance mới. Khi restart thì **không tự đổi identifying parameters**.

## 5. Dependencies và hạ tầng

Với ứng dụng Spring Boot đã có version management phù hợp, dependencies Gradle minh họa:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}
~~~

Spring Batch sử dụng hạ tầng retry phù hợp với version Spring Retry trong dependency graph. Đừng thêm tùy tiện một version Spring Retry khác với bộ dependency management của dự án.

JobRepository cần schema metadata Spring Batch; datasource nghiệp vụ có bảng **enriched_order**. Trong demo có thể dùng một datasource, với **PlatformTransactionManager** được cấu hình nhất quán để JDBC writer và checkpoint theo chunk có transaction semantics mong muốn. Production cần driver, pooling, credential và timeout riêng của database thật.

## 6. Model, interface và exception

Mỗi class/record bên dưới đặt trong file Java phù hợp với package dự án.

~~~java
package com.example.batch.orders;

import java.math.BigDecimal;

public record RawOrder(
        String orderId,
        String customerId,
        BigDecimal amount) {
}
~~~

~~~java
package com.example.batch.orders;

import java.math.BigDecimal;

public record EnrichedOrder(
        String orderId,
        String customerId,
        BigDecimal amount,
        int riskScore) {
}
~~~

~~~java
package com.example.batch.risk;

public interface CustomerRiskClient {
    int scoreFor(String customerId);
}
~~~

Exception retryable:

~~~java
package com.example.batch.risk;

public class TransientRiskServiceException
        extends RuntimeException {

    public TransientRiskServiceException(String message) {
        super(message);
    }

    public TransientRiskServiceException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Exception không retry:

~~~java
package com.example.batch.risk;

public class PermanentRiskServiceException
        extends RuntimeException {

    public PermanentRiskServiceException(String message) {
        super(message);
    }

    public PermanentRiskServiceException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

~~~java
package com.example.batch.orders;

public class InvalidOrderException extends RuntimeException {

    public InvalidOrderException(String reasonCode) {
        super(reasonCode);
    }
}
~~~

Thay vì để processor tự phân tích mọi HTTP status, adapter **CustomerRiskClient** chuyển lỗi kỹ thuật thành exception theo hợp đồng. Step chỉ retry class cần retry.

Không đưa access token, raw response, email hoặc toàn bộ request body vào exception message. Exception có thể bị ghi ra log hoặc lưu metadata; tốt hơn là **reason code cố định** và một correlation ID an toàn.

## 7. Reader: đọc CSV theo dòng

~~~java
package com.example.batch.config;

import com.example.batch.orders.RawOrder;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.batch.item.file.builder.FlatFileItemReaderBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;

@Configuration
public class OrderReaderConfiguration {

    @Bean
    @StepScope
    public FlatFileItemReader<RawOrder> orderReader(
            @Value("#{jobParameters['inputFile']}") String inputFile) {

        return new FlatFileItemReaderBuilder<RawOrder>()
                .name("retryPracticeOrderReader")
                .resource(new FileSystemResource(inputFile))
                .linesToSkip(1)
                .delimited()
                .names("orderId", "customerId", "amount")
                .fieldSetMapper(fields -> new RawOrder(
                        fields.readString("orderId"),
                        fields.readString("customerId"),
                        fields.readBigDecimal("amount")))
                .saveState(true)
                .build();
    }
}
~~~

**@StepScope** resolve đường dẫn khi Step chạy, tránh dùng chung một reader stateful giữa nhiều execution. **saveState(true)** cho phép reader lưu tiến độ vào ExecutionContext khi có checkpoint phù hợp.

Reader đọc từng dòng, không đưa toàn bộ file vào List. Lỗi parse một dòng thường không tự phục hồi nếu đọc lại nguyên dòng, do đó **không retry mọi FlatFileParseException** trong bài này.

## 8. Processor: bổ sung điểm rủi ro

~~~java
package com.example.batch.config;

import com.example.batch.orders.EnrichedOrder;
import com.example.batch.orders.InvalidOrderException;
import com.example.batch.orders.RawOrder;
import com.example.batch.risk.CustomerRiskClient;
import com.example.batch.risk.PermanentRiskServiceException;
import java.math.BigDecimal;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OrderProcessorConfiguration {

    @Bean
    public ItemProcessor<RawOrder, EnrichedOrder> riskProcessor(
            CustomerRiskClient riskClient) {

        return order -> {
            if (order.amount() == null
                    || order.amount().compareTo(BigDecimal.ZERO) <= 0) {
                throw new InvalidOrderException("INVALID_AMOUNT");
            }

            int score = riskClient.scoreFor(order.customerId());

            if (score < 0 || score > 100) {
                throw new PermanentRiskServiceException(
                        "INVALID_RISK_SCORE");
            }

            return new EnrichedOrder(
                    order.orderId(),
                    order.customerId(),
                    order.amount(),
                    score);
        };
    }
}
~~~

Processor không biết HTTP URL, auth header hay exception của RestClient; nó chỉ dùng interface. **Retry config ở Step** quyết định có gọi lại processor sau một lỗi được phân loại hay không.

Trong bản demo CustomerRiskClient là hoạt động đọc. Nếu thay bằng một API **tạo thanh toán hoặc giữ chỗ**, retry cần idempotency key/receipt để tránh tạo side effect mới khi response của attempt trước bị mất.

### Tránh nuốt lỗi để trả giá trị mặc định

Phản mẫu:

~~~java
try {
    return riskClient.scoreFor(customerId);
} catch (Exception ignored) {
    return 0; // Không an toàn: biến lỗi mạng thành score hợp lệ.
}
~~~

Nếu score=0 là một giá trị hợp lệ, job có thể ghi kết quả sai rồi báo COMPLETED. Lỗi tạm thời phải đi qua retry/failure policy thay vì bị giấu bởi default value.

## 9. Writer: ghi output theo batchId

~~~java
package com.example.batch.config;

import com.example.batch.orders.EnrichedOrder;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

@Configuration
public class OrderWriterConfiguration {

    @Bean
    @StepScope
    public ItemWriter<EnrichedOrder> orderWriter(
            JdbcTemplate jdbcTemplate,
            @Value("#{jobParameters['batchId']}") String batchId) {

        return chunk -> {
            for (EnrichedOrder order : chunk) {
                jdbcTemplate.update(
                        """
                        INSERT INTO enriched_order
                          (batch_id, order_id, customer_id,
                           amount, risk_score)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        batchId,
                        order.orderId(),
                        order.customerId(),
                        order.amount(),
                        order.riskScore());
            }
        };
    }
}
~~~

Writer tham gia transaction của Step nếu datasource và transaction manager được cấu hình tương ứng. Một lệnh JDBC update trả về thành công **chưa chứng minh chunk đã commit**: commit diễn ra sau writer.

Với rủi ro retry/restart, INSERT thuần chưa đủ cho mọi kịch bản. Hệ thống production cần key nghiệp vụ ổn định, merge/upsert/reconcile và đánh giá trường hợp commit thành công nhưng checkpoint chưa được cập nhật do sự cố.

## 10. Cấu hình fault-tolerant Step

Phần trọng tâm: khai báo **retry(TransientRiskServiceException.class)**, giới hạn số attempt và backoff.

~~~java
package com.example.batch.config;

import com.example.batch.orders.EnrichedOrder;
import com.example.batch.orders.RawOrder;
import com.example.batch.risk.TransientRiskServiceException;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.item.file.FlatFileItemReader;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.retry.backoff.FixedBackOffPolicy;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class RetryPracticeJobConfiguration {

    @Bean
    public Step enrichOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            FlatFileItemReader<RawOrder> orderReader,
            ItemProcessor<RawOrder, EnrichedOrder> riskProcessor,
            ItemWriter<EnrichedOrder> orderWriter) {

        FixedBackOffPolicy backOff = new FixedBackOffPolicy();
        backOff.setBackOffPeriod(200L);

        return new StepBuilder("enrichOrdersStep", jobRepository)
                .<RawOrder, EnrichedOrder>chunk(2, transactionManager)
                .reader(orderReader)
                .processor(riskProcessor)
                .writer(orderWriter)
                .faultTolerant()
                .retry(TransientRiskServiceException.class)
                .retryLimit(3)
                .backOffPolicy(backOff)
                .build();
    }

    @Bean
    public Job importOrdersJob(
            JobRepository jobRepository, Step enrichOrdersStep) {

        return new JobBuilder("importOrdersJob", jobRepository)
                .start(enrichOrdersStep)
                .build();
    }
}
~~~

| Thành phần | Ý nghĩa |
|---|---|
| **chunk(2, transactionManager)** | Commit interval hai item trong demo |
| **faultTolerant()** | Bật cơ chế chịu lỗi ở chunk Step |
| **retry(TransientRiskServiceException.class)** | Chỉ class này thuộc nhóm retryable |
| **retryLimit(3)** | Tối đa ba attempts, gồm attempt đầu |
| **backOffPolicy(backOff)** | Nghỉ giữa các attempts theo policy |
| Không cấu hình skip cho transient | Hết retry thì Step FAILED thay vì mất record |

Với lỗi trong processor, Spring Batch có thể thử lại thao tác xử lý item theo retry policy. Với lỗi writer, rollback chunk hoặc commit failure, số lần xử lý thực tế có thể khác do cách Step phục hồi transaction. Không mặc định mọi exception ở commit đều được retry bằng cùng semantics như processor.

### Phân biệt hai lần retry với ba attempts

~~~text
Attempt 1 -> transient failure
      | 200 ms
Attempt 2 -> transient failure
      | 200 ms
Attempt 3 -> success hoặc exhausted
~~~

Hai khoảng nghỉ minh họa tổng khoảng 400 ms, chưa tính thời gian thực hiện request, commit, scheduling và xử lý lỗi.

## 11. Viết HTTP adapter phân loại lỗi

Trong production, CustomerRiskClient có thể triển khai bằng **RestClient** của Spring Framework 6.1+. Adapter có nhiệm vụ chuyển các lỗi HTTP/network thành exception nghiệp vụ phù hợp với retry policy của Step.

~~~java
package com.example.batch.risk;

import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;

@Component
public class HttpCustomerRiskClient implements CustomerRiskClient {

    private final RestClient restClient;

    public HttpCustomerRiskClient(RestClient restClient) {
        this.restClient = restClient;
    }

    @Override
    public int scoreFor(String customerId) {
        try {
            RiskResponse response = restClient.get()
                    .uri("/risk/{customerId}", customerId)
                    .retrieve()
                    .body(RiskResponse.class);

            if (response == null || response.score() == null) {
                throw new PermanentRiskServiceException(
                        "RISK_RESPONSE_MISSING_SCORE");
            }
            return response.score();

        } catch (RestClientResponseException error) {
            int status = error.getStatusCode().value();

            if (status == 429 || status == 502
                    || status == 503 || status == 504) {
                throw new TransientRiskServiceException(
                        "RISK_TEMPORARY_UNAVAILABLE", error);
            }

            throw new PermanentRiskServiceException(
                    "RISK_HTTP_ERROR_" + status, error);

        } catch (ResourceAccessException error) {
            throw new TransientRiskServiceException(
                    "RISK_NETWORK_FAILURE", error);
        }
    }

    public record RiskResponse(Integer score) {
    }
}
~~~

Response thành công theo contract giả định:

~~~json
{"score":35}
~~~

Base URL có thể cấu hình qua Environment:

~~~java
package com.example.batch.config;

import java.util.Objects;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.web.client.RestClient;

@Configuration
public class RiskClientConfiguration {

    @Bean
    public RestClient riskRestClient(
            RestClient.Builder builder,
            Environment environment) {

        String baseUrl = Objects.requireNonNull(
                environment.getProperty("risk.base-url"),
                "risk.base-url must be configured");
        return builder.baseUrl(baseUrl).build();
    }
}
~~~

Ví dụ application.yml:

~~~yaml
risk:
  base-url: https://risk-service.internal.example
~~~

Ở production phải cấu hình **connect timeout, read/response timeout**, credential provider và connection pooling bằng HTTP client/request factory phù hợp. Retry chỉ diễn ra sau khi attempt phát lỗi; một request bị treo vô thời hạn không được sửa bằng retryLimit.

### Không phân loại chỉ theo một bảng status code cứng

Đoạn adapter là **quy tắc minh họa cho API risk-service**. 429 có thể mang header **Retry-After**; fixed backoff 200 ms không nhất thiết phù hợp. 404 có API xem là not found vĩnh viễn, có API lại xem là trạng thái eventual consistency. ResourceAccessException đôi khi là lỗi DNS/certificate không tự phục hồi; nên phân tích nguyên nhân và contract trước khi retry.

HTTP 401/403 cần fail và cảnh báo, thay vì retry token sai hàng nghìn lần. Response body hoặc exception message có thể chứa PII/secret; log nên ghi **failureCategory** và HTTP status thay vì raw body.

## 12. Backoff và tránh retry storm

Nếu hàng trăm job hoặc partition nhận 503 rồi lập tức retry, dịch vụ vốn quá tải có thể càng khó phục hồi.

**Fixed backoff**:

~~~text
Attempt 1 --200ms--> Attempt 2 --200ms--> Attempt 3
~~~

**Exponential backoff**:

~~~text
Attempt 1 --200ms--> Attempt 2 --400ms--> Attempt 3
~~~

**Jitter** bổ sung dao động ngẫu nhiên có giới hạn để nhiều worker không cùng gọi lại vào đúng một thời điểm.

Ví dụ đổi policy trong Step:

~~~java
import org.springframework.retry.backoff.ExponentialBackOffPolicy;

ExponentialBackOffPolicy backOff =
        new ExponentialBackOffPolicy();
backOff.setInitialInterval(200L);
backOff.setMultiplier(2.0);
backOff.setMaxInterval(3000L);

// Sau đó dùng:
// .backOffPolicy(backOff)
~~~

Với retryLimit=3 chỉ có tối đa hai khoảng nghỉ giữa ba attempts. Để phục vụ SLA, phải kiểm soát **tổng thời gian** gồm response timeout, backoff và xử lý chunk.

Nếu HTTP client tự retry ba attempts và Spring Batch lại retry ba attempts, một item có thể tạo khoảng **chín request**, chưa kể gateway/service mesh. Thiết kế phải ghi rõ tầng nào chịu trách nhiệm retry và tổng request tối đa.

### Không giải quyết mọi vấn đề bằng retryLimit lớn

RetryLimit quá cao có thể:

- Kéo dài transaction hoặc JobExecution.
- Giữ connection và tài nguyên thread.
- Làm tăng request tới dependency đang quá tải.
- Gây lặp side effect nếu request không idempotent.
- Khiến batch trễ deadline mà không có tín hiệu fail rõ ràng.

Khi service outage kéo dài, fail có kiểm soát, circuit breaker hoặc chờ scheduler restart sau khi upstream phục hồi có thể phù hợp hơn.

## 13. Chạy thử với bốn đơn hàng

Cho mock/client trả:

~~~text
C001 -> score 35 ngay
C002 -> timeout, HTTP 503, score 10
C003 -> score 60 ngay
C004 -> score 20 ngay
~~~

Luồng mong muốn với chunk size hai:

~~~text
Chunk #1:
  O001: risk score 35
  O002: attempt 1 timeout
        attempt 2 HTTP 503
        attempt 3 score 10
  Writer: O001 + O002
  Commit

Chunk #2:
  O003: risk score 60
  O004: risk score 20
  Writer: O003 + O004
  Commit

Job status: COMPLETED
~~~

Với pipeline minh họa không filter/skip:

| Chỉ số | Mong đợi |
|---|---:|
| readCount | 4 |
| writeCount | 4 |
| processSkipCount | 0 |
| writeSkipCount | 0 |
| filterCount | 0 |
| Rows của batch | 4 |
| Unique business keys | 4 |
| Job status | COMPLETED |

Đừng chỉ nhìn read/write counts hoặc số lần mock được gọi. Cần query output để xác nhận mỗi order có một bản ghi và score, amount đúng.

## 14. Integration test với JUnit 5 và Mockito

Spring Batch Test cho phép chạy **Job thật** qua JobLauncherTestUtils trong Spring context. Ta thay **CustomerRiskClient** bằng mock, để lỗi transient xảy ra deterministically mà không gọi mạng.

Điều kiện môi trường:

1. Job, Step, reader, processor và writer bean đã được đăng ký.
2. Database test riêng có schema JobRepository.
3. Bảng output được tạo trước khi chạy test.
4. Không cho Spring Boot tự chạy Job khi context khởi động.
5. Chỉ có một Job được chọn hoặc cấu hình rõ Job cho JobLauncherTestUtils.

Với Spring Boot 3.4+/Spring Framework 6.2+, có thể dùng **@MockitoBean**; các dự án Boot cũ hơn thường dùng **@MockBean** tương ứng phiên bản.

~~~java
package com.example.batch;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;

import com.example.batch.risk.CustomerRiskClient;
import com.example.batch.risk.PermanentRiskServiceException;
import com.example.batch.risk.TransientRiskServiceException;
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
@SpringBootTest(properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always",
        "spring.datasource.url=jdbc:h2:mem:retrytest;DB_CLOSE_DELAY=-1"
})
class RiskRetryBatchIT {

    @MockitoBean
    CustomerRiskClient riskClient;

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @TempDir
    Path tempDir;

    @BeforeEach
    void prepareDatabase() {
        jdbcTemplate.execute(
                """
                CREATE TABLE IF NOT EXISTS enriched_order (
                    batch_id VARCHAR(64) NOT NULL,
                    order_id VARCHAR(64) NOT NULL,
                    customer_id VARCHAR(64) NOT NULL,
                    amount DECIMAL(18, 2) NOT NULL,
                    risk_score INTEGER NOT NULL,
                    PRIMARY KEY (batch_id, order_id)
                )
                """);

        // Chỉ sử dụng database test riêng.
        jdbcTemplate.update("DELETE FROM enriched_order");
    }

    @Test
    void retriesTwiceAndThenWritesOneRecord()
            throws Exception {

        when(riskClient.scoreFor("C001"))
                .thenThrow(new TransientRiskServiceException(
                        "TEMPORARY_TIMEOUT"))
                .thenThrow(new TransientRiskServiceException(
                        "TEMPORARY_503"))
                .thenReturn(35);

        JobExecution execution =
                launchOne("B-RETRY-SUCCESS", "O001", "C001");

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        verify(riskClient, times(3)).scoreFor("C001");

        StepExecution step = execution.getStepExecutions().stream()
                .filter(e -> "enrichOrdersStep".equals(e.getStepName()))
                .findFirst()
                .orElseThrow();

        assertEquals(1L, step.getReadCount());
        assertEquals(1L, step.getWriteCount());
        assertEquals(0L, step.getProcessSkipCount());

        Long rows = jdbcTemplate.queryForObject(
                """
                SELECT COUNT(*) FROM enriched_order
                WHERE batch_id = ? AND order_id = ?
                """,
                Long.class,
                "B-RETRY-SUCCESS", "O001");
        assertEquals(1L, rows);

        Integer score = jdbcTemplate.queryForObject(
                """
                SELECT risk_score FROM enriched_order
                WHERE batch_id = ? AND order_id = ?
                """,
                Integer.class,
                "B-RETRY-SUCCESS", "O001");
        assertEquals(35, score);
    }

    @Test
    void failsAfterRetryLimitIsExhausted()
            throws Exception {

        when(riskClient.scoreFor("C002"))
                .thenThrow(new TransientRiskServiceException(
                        "STILL_UNAVAILABLE"));

        JobExecution execution =
                launchOne("B-RETRY-FAIL", "O002", "C002");

        assertEquals(BatchStatus.FAILED, execution.getStatus());
        verify(riskClient, times(3)).scoreFor("C002");

        Long rows = jdbcTemplate.queryForObject(
                """
                SELECT COUNT(*) FROM enriched_order
                WHERE batch_id = ?
                """,
                Long.class, "B-RETRY-FAIL");
        assertEquals(0L, rows);
    }

    @Test
    void doesNotRetryPermanentFailure()
            throws Exception {

        when(riskClient.scoreFor("C003"))
                .thenThrow(new PermanentRiskServiceException(
                        "RISK_HTTP_ERROR_400"));

        JobExecution execution =
                launchOne("B-PERMANENT", "O003", "C003");

        assertEquals(BatchStatus.FAILED, execution.getStatus());
        verify(riskClient, times(1)).scoreFor("C003");
    }

    private JobExecution launchOne(
            String batchId, String orderId, String customerId)
            throws Exception {

        Path input = tempDir.resolve(
                UUID.randomUUID() + "-orders.csv");
        Files.writeString(
                input,
                "orderId,customerId,amount\n"
                + orderId + "," + customerId + ",120.00\n",
                StandardCharsets.UTF_8);

        JobParameters params = new JobParametersBuilder()
                .addString("inputFile",
                        input.toAbsolutePath().toString())
                .addString("batchId", batchId)
                .addString("testRunId",
                        UUID.randomUUID().toString())
                .toJobParameters();

        return jobLauncherTestUtils.launchJob(params);
    }
}
~~~

**Phạm vi chứng minh:** test chạy Job/Step thật, mock ở interface RiskClient và writer dùng DB test. Kịch bản **một item, Step đồng bộ** giúp xác minh retryLimit=3 trực tiếp qua số lần gọi.

Đối với Job có nhiều Step, cấu hình JobLauncherTestUtils trỏ đúng Job; với test chạy song song, không xóa toàn bảng trong một database chung. Nếu framework/context có cơ chế reset mock khác nhau, cần reset giữa test để stubbing và interaction không bị rò.

Đoạn test này không chứng minh HTTP adapter tạo URL/JSON/headers đúng; cần test adapter bằng HTTP stub riêng.

### Khi số lần gọi mock khác kỳ vọng

Cần kiểm tra:

- Có retry ở tầng HTTP client hoặc gateway hay không?
- Writer/transaction có rollback khiến processor bị gọi lại không?
- Có nhiều item/chunk đang xử lý đồng thời không?
- Exception thực tế có đúng class được cấu hình retry không?
- Có JobExecution khác dùng cùng mock hoặc context không?
- Có một lớp wrapper chuyển exception sang class khác không?

Không tăng retryLimit chỉ để test xanh nếu chưa biết nguyên nhân số lần request thay đổi.

## 15. Kiểm thử hai item trong một chunk

Mở rộng fixture:

~~~csv
orderId,customerId,amount
O001,C001,120.00
O002,C002,50.00
~~~

Mock:

~~~java
when(riskClient.scoreFor("C001")).thenReturn(35);
when(riskClient.scoreFor("C002"))
        .thenThrow(new TransientRiskServiceException(
                "TEMPORARY_TIMEOUT"))
        .thenReturn(10);
~~~

Expected:

- Job COMPLETED.
- Hai record **O001** và **O002** tồn tại đúng một lần.
- Risk scores tương ứng 35 và 10, amount không sai.
- Không có item bị skip.
- Không phát hành output chưa commit.

Với lỗi trong writer/transaction, một số item có thể được xử lý lại; vì vậy không dùng số lần gọi method như bằng chứng duy nhất về output. **Đối soát kết quả cuối** luôn quan trọng hơn.

## 16. HTTP adapter test bằng mock server

Mockito CustomerRiskClient cô lập logic Batch rất tốt, nhưng không kiểm tra protocol. Để xác minh adapter, dùng **WireMock** hoặc **MockWebServer** chạy cục bộ.

Contract giả định:

~~~http
GET /risk/C001 HTTP/1.1
Accept: application/json
~~~

Lần đầu trả:

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{"code":"TEMPORARILY_UNAVAILABLE"}
~~~

Lần sau trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"score":35}
~~~

Các tình huống stub nên có:

| Response / tình huống | Điều cần assert |
|---|---|
| HTTP 200, score hợp lệ | Parse đúng score |
| HTTP 503 | TransientRiskServiceException |
| HTTP 429 | Xử lý throttling/Retry-After theo contract |
| HTTP 400 | PermanentRiskServiceException |
| HTTP 401/403 | Không retry mù |
| HTTP 200 thiếu score | Không chấp nhận response sai schema |
| HTTP 200 score ngoài 0..100 | Processor báo permanent data error |
| Connect/read timeout | Timeout hữu hạn và mapping lỗi |
| Sai URL/header/body | Stub không khớp, test fail có thông tin |

Trong **test HTTP adapter**, không được đồng thời thay CustomerRiskClient bằng @MockitoBean, vì như vậy request không đi qua HTTP client thật. Base URL nên trỏ tới **dynamic port** của mock server.

Test toàn tuyến có thể cho server trả 503 rồi 200, chạy Job thật và đối soát bảng output đúng một record. Điều đó xác nhận kết nối giữa HTTP adapter, exception mapping và Step retry.

## 17. Transaction, rollback và checkpoint

Một retry trong processor thường là lỗi trước writer, nhưng Spring Batch vẫn tổ chức work theo chunk transaction và fault-tolerant Step semantics:

~~~text
Chunk 1:
  O001 -> risk score 35
  O002 -> timeout -> retry -> risk score 10
  Writer INSERT O001, O002
  COMMIT, checkpoint

Chunk 2:
  O003 -> score 60
  Writer INSERT O003
  COMMIT -> connection error, outcome unclear
~~~

Không phải mọi exception xảy ra ở transaction manager **commit()** đều được xử lý như một processor retry. Có thể DB đã commit nhưng ứng dụng mất xác nhận, hoặc metadata checkpoint chưa cập nhật đồng bộ.

Nếu dữ liệu nghiệp vụ và Batch metadata dùng **cùng datasource/transaction thật**, commit của chunk có thể giúp chúng nhất quán hơn. Nhưng external API, file, Kafka, logs và các resource khác không tự tham gia transaction đó.

Vì thế:

- Không mặc định writer đã ghi xong là transaction đã commit.
- Không dùng retry(Exception.class) để xử lý lỗi commit không xác định.
- Không xem writeCount là bằng chứng mọi output ngoài đã được persist.
- Khi restart, đối soát theo business key thay vì tin hoàn toàn vào số item đã xử lý.

## 18. Idempotency khi phải gọi lại

Ở bài này RiskClient chỉ **đọc** điểm. Đó là một thao tác thuận lợi cho retry, nhưng ngay cả read-only service cũng có thể trả dữ liệu khác nhau giữa các lần thử hoặc restart.

~~~text
Attempt #1 -> timeout
Attempt #2 -> score 35
Ngày hôm sau restart -> score 60
~~~

Nếu nghiệp vụ yêu cầu kết quả ổn định theo batch, cần **source snapshot, effective date, version của mô hình chấm điểm hoặc caching có kiểm soát**. Tính lặp lại là một phần của hợp đồng dữ liệu.

### Lời gọi có side effect

Giả sử đổi RiskClient thành ReserveInventoryClient:

~~~text
Batch gửi POST reserve
       |
       v
Service đã tạo reservation R123
       |
       v
Response bị timeout
       |
       v
Batch retry POST reserve
~~~

Nếu lần thứ hai tạo reservation khác thì retry đã làm sai nghiệp vụ. Cần một **idempotency key ổn định** theo batchId/orderId/operation, API hỗ trợ kiểm tra kết quả theo key và thời hạn lưu key phù hợp.

~~~http
POST /reservations
Idempotency-Key: B42-O001-RESERVE
Content-Type: application/json

{"orderId":"O001","quantity":1}
~~~

Chỉ thêm header chưa đủ: dịch vụ đích phải cam kết và thực thi cơ chế idempotency. Nếu không, cần chọn workflow khác, ví dụ outbox, receipt lookup hoặc compensation có kiểm soát.

### Idempotency ở writer

Với JDBC, một policy replay thường là:

- Không có key -> INSERT.
- Có key và payload khớp -> chấp nhận replay.
- Có key nhưng nội dung khác -> báo conflict, không âm thầm overwrite.

Ví dụ ý tưởng PostgreSQL:

~~~sql
INSERT INTO enriched_order
    (batch_id, order_id, customer_id, amount, risk_score)
VALUES
    (:batchId, :orderId, :customerId, :amount, :riskScore)
ON CONFLICT (batch_id, order_id)
DO UPDATE SET amount = enriched_order.amount
WHERE enriched_order.customer_id = EXCLUDED.customer_id
  AND enriched_order.amount = EXCLUDED.amount
  AND enriched_order.risk_score = EXCLUDED.risk_score
RETURNING order_id;
~~~

Nếu key xung đột nhưng payload khác, điều kiện WHERE không đạt và không có row trả về; ứng dụng có thể phân loại conflict. **UPDATE no-op có thể kích hoạt trigger hoặc tạo version** theo database, nên đây là minh họa chính sách, không phải SQL tối ưu cho mọi hệ thống. Database khác có cú pháp khác.

## 19. Hết retry: fail hay skip?

Trong bài cơ bản, retry exhausted dẫn tới **FAILED**:

~~~text
Attempt #1 -> timeout
Attempt #2 -> timeout
Attempt #3 -> timeout
        |
        v
Retry exhausted
        |
        v
Step FAILED -> Job FAILED
~~~

Lý do: contract yêu cầu mọi đơn hợp lệ phải có risk score. Nếu sau ba lần timeout mà tự bỏ qua item rồi vẫn COMPLETED, output có thể thiếu record và downstream không biết.

Trong một hệ thống **best-effort** có thể cho phép skip sau retry, nhưng cần:

1. Skip limit có chủ đích.
2. Reject/quarantine store riêng.
3. Audit reasonCode và batchId.
4. Quy trình replay record đã bỏ qua.
5. Đối soát expected output theo chính sách partial success.

Ví dụ mở rộng để skip **lỗi input không hợp lệ**, độc lập với transient outage:

~~~java
.faultTolerant()
.retry(TransientRiskServiceException.class)
.retryLimit(3)
.skip(InvalidOrderException.class)
.skipLimit(2)
~~~

**skipLimit không phải retryLimit.** Skip đếm các item bị loại, không phải số lần một item được retry rồi thành công. Tránh skip(Exception.class) vì có thể che lỗi DB, auth hoặc lỗi code.

## 20. Restart khi dependency phục hồi

Nếu service lỗi kéo dài hơn retryLimit, JobExecution có thể FAILED. Sau khi dịch vụ trở lại, Job có thể restart cùng JobInstance theo checkpoint nếu thỏa điều kiện.

~~~text
JobInstance importOrdersJob(batchId=B42, inputFile=...)
       |
       +-- JobExecution #900: FAILED
       |      Chunk 1 đã commit
       |      Chunk 2 retry exhausted
       |
       +-- JobExecution #908: restart
              Khôi phục checkpoint
              Tiếp tục xử lý
              COMPLETED
~~~

Ví dụ:

~~~java
long failedExecutionId = 900L;

// jobOperator được inject; chỉ restart khi execution hợp lệ.
Long restartedExecutionId =
        jobOperator.restart(failedExecutionId);
~~~

Điều quan trọng:

- Không thêm identifying parameter ngẫu nhiên để gọi lần chạy mới là restart.
- Không sửa file input khi reader checkpoint theo vị trí.
- Không mặc định những gì đã commit trong execution trước sẽ xuất hiện trong writeCount của execution mới.
- Không bắt đầu execution thứ hai trước khi xác nhận execution cũ đã kết thúc và không còn worker đang ghi.
- Có idempotent writer hoặc reconcile cho trường hợp replay sau commit không rõ kết quả.

### Kịch bản restart kiểm thử

1. Input sáu item, chunk size hai.
2. Hai item đầu thành công và commit.
3. Item thứ ba ném transient exception ba lần; Job FAILED.
4. Kiểm tra output của chunk đầu đã lưu.
5. Thay hành vi mock để item thứ ba trả score hợp lệ.
6. Dùng JobOperator.restart với execution ID đã FAILED.
7. Xác nhận JobExecution mới COMPLETED và output cuối đủ sáu business keys.
8. Kiểm tra không thiếu/trùng và các giá trị được ghi đúng.

Việc ghép kết quả từ nhiều JobExecution thuộc cùng JobInstance là một phần quan trọng của kiểm thử recovery.

## 21. Quan sát retry trong log và metrics

Job có thể cuối cùng COMPLETED nhưng việc phải retry hàng nghìn lần làm duration tăng và là tín hiệu dependency không ổn định.

Các metric nên có:

| Chỉ số | Mục đích |
|---|---|
| Retry attempts | Số lần thử lại trên từng dependency |
| Retry exhausted | Số lần dùng hết retry limit |
| Dependency error rate | Tỷ lệ 429/502/503/504/timeout |
| Dependency latency | Phân phối thời gian request |
| Job/Step duration | Ảnh hưởng tới deadline |
| read/write/skip counts | Tình trạng xử lý dữ liệu |
| rollbackCount | Số lần rollback |
| last successful batch | Theo dõi kết quả công bố |

Ví dụ structured log an toàn:

~~~text
event=external.retry
jobExecutionId=900
stepName=enrichOrdersStep
dependency=risk-service
failureCategory=HTTP_503
attempt=2
maxAttempts=3

event=external.retry.exhausted
jobExecutionId=900
dependency=risk-service
failureCategory=TEMPORARY_UNAVAILABLE
~~~

Đây là schema minh họa. Khi cần attempt chính xác ở Step, sử dụng instrumentation phù hợp với cơ chế retry của Spring Batch (ví dụ RetryListener) hoặc adapter, đồng thời phân biệt **HTTP request attempts**, **Step retries** và **processor re-invocations do rollback**.

Không gắn customerId, orderId, jobExecutionId thành nhãn Prometheus có cardinality cao; ID động phù hợp cho log/traces/audit, còn metric nên dùng jobName, stepName, dependency, outcome và failure category. Không ghi raw response, Authorization header hoặc PII vào log retry.

### Các cảnh báo đáng quan tâm

- Retry exhausted tăng đột ngột.
- HTTP 429/503 cao trong thời gian liên tục.
- Job duration tăng dù input volume không đổi.
- Step STARTED nhưng không có tiến độ chunk.
- Không có batch READY trước deadline.

Tùy loại workload, đặt ngưỡng để không gây báo động vì một timeout lẻ đã tự phục hồi.

## 22. Nhiều thread và partition có thể tạo retry storm

Một job có bốn partition:

~~~text
Partition A -> retry C001
Partition B -> retry C201
Partition C -> retry C401
Partition D -> retry C601
~~~

Mỗi worker retryLimit=3 nhưng tổng requests có thể tăng rất nhanh. Với 100 partition, một outage ngắn có thể phát sinh hàng trăm request lại cùng lúc.

Các biện pháp:

- Backoff có jitter.
- Rate limit/chặn tổng concurrency tới dependency.
- Timeout tổng cho một item/request.
- Circuit breaker khi outage kéo dài.
- Queue và worker pool có giới hạn.
- Giám sát tổng request không chỉ số retry của từng item.
- Đảm bảo reader/writer và retry state tương thích với execution model.

Trong test đa luồng, stub response **theo customerId hoặc request key**, không dựa vào thứ tự gọi toàn cục. Tránh dùng static mutable counter không thread-safe.

## 23. Những lỗi thường gặp

**Retry mọi RuntimeException.** Lỗi validation, lỗi code hoặc auth không tự phục hồi sau vài trăm mili giây.

**Nhầm retryLimit với số lần retry cộng thêm.** RetryLimit(3) cho tối đa ba attempts, gồm lần đầu.

**Không đặt HTTP timeout.** Một attempt kẹt vô hạn khiến retry không bắt đầu.

**Backoff bằng 0 và nhiều worker.** Dễ gây retry storm.

**Hai hoặc ba tầng đều retry.** Tổng số requests có thể nhân lên không kiểm soát.

**Trả score mặc định khi service lỗi.** Làm job ghi dữ liệu sai nhưng báo thành công.

**Dùng retry cho API có side effect mà không có idempotency.** Gây giao dịch hoặc thông báo trùng.

**Tưởng transaction DB rollback được HTTP/Kafka.** Không có distributed transaction tự động.

**Skip transient outage sau khi retry hết mà không có contract.** Gây missing record âm thầm.

**Tạo JobInstance mới khi muốn restart.** Có thể đọc lại toàn bộ file.

**Sửa input giữa hai executions.** Checkpoint theo vị trí có thể không còn hợp lệ.

**Tin vào writeCount thay vì đối soát database.** Writer call không nhất thiết tương đương output bền vững của hệ thống ngoài.

**Retry lỗi commit không rõ outcome.** Có thể đã commit rồi mất ACK; phải reconcile.

**Assert số lần gọi mock cho mọi transaction phức tạp.** Rollback và đa luồng có thể làm method được gọi thêm.

**Không quan sát retry rate.** Job vẫn COMPLETED nhưng service đang gần quá tải.

**Log raw request/response khi debug.** Có nguy cơ lộ token, PII và dữ liệu nghiệp vụ.

## 24. Bài tập mở rộng

### A. Exponential backoff

Thay fixed backoff bằng exponential, đặt max interval. Test lỗi hai lần rồi thành công; không cần assert thời gian chính xác tới mili giây trên CI. Với rate limiting, cân nhắc jitter.

### B. HTTP 429 và Retry-After

Mock server trả 429 với Retry-After rồi 200. Adapter phải phân loại throttling và áp dụng delay hợp đồng; Step hoàn tất với một output và không tạo quá nhiều requests.

### C. Lỗi 400 không được retry

Mock HTTP 400, xác nhận adapter ném PermanentRiskServiceException; Step FAILED ngay theo policy, không gọi HTTP ba lần.

### D. Restart sau retry exhausted

File sáu record, chunk hai, lỗi tại chunk thứ hai. Lần đầu FAILED, lần hai restart đúng JobInstance và COMPLETED. Đối soát output đủ sáu khóa, không duplicate.

### E. API có side effect

Thay RiskClient bằng ReserveInventoryClient. Mô phỏng service đã tạo reservation thành công nhưng response timeout. Retry cùng idempotency key phải trả cùng reservation, không tạo cái mới.

### F. Test nhiều worker

Chạy partitioning với mock phản hồi theo request key; kiểm tra global rate limit và timeout, đảm bảo không lẫn retry state giữa partition.

## 25. Tiêu chí nghiệm thu của dự án

| Nội dung | Bằng chứng cần có |
|---|---|
| Exception taxonomy | Tách transient, permanent, invalid input |
| Retry Step | faultTolerant, retry đúng class, retryLimit hữu hạn |
| Backoff | Có delay rõ ràng, tránh retry dồn dập |
| Phục hồi lần ba | Job COMPLETED, output một record đúng |
| Hết retry | Job FAILED, không báo hoàn tất giả |
| Lỗi vĩnh viễn | Không bị retry mù |
| Output | Key/amount/score chính xác, không duplicate |
| Test | Mockito Job test và HTTP adapter test theo phạm vi |
| Transaction | Hiểu commit/checkpoint và replay |
| Restart | Cùng JobInstance, input snapshot ổn định |
| Side effect | Idempotency hoặc cơ chế reconcile thích hợp |
| Observability | Phân biệt attempts, exhausted và status |

Thêm một lệnh retry đơn lẻ chưa làm batch trở nên đáng tin cậy. Retry chỉ thực sự có giá trị khi **exception được phân loại đúng, attempts và backoff có giới hạn, các thao tác replay an toàn, trạng thái Job được phản ánh trung thực và output cuối được đối soát**. Khi áp dụng những nguyên tắc đó, Spring Batch có thể đi qua các gián đoạn tạm thời của external service mà không biến chúng thành thiếu dữ liệu, retry storm hoặc side effect trùng.
