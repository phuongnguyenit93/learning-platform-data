# Test profile trong Spring Batch: cấu hình hạ tầng kiểm thử tách biệt

## 1. Test profile giải quyết vấn đề gì?

Trong ứng dụng Spring Batch, một job có thể sử dụng `DataSource`, `JobRepository`, `PlatformTransactionManager`, scheduler, message broker, file storage, API bên ngoài và các cấu hình như chunk size, đường dẫn tệp, retry policy. Nếu integration test vô tình sử dụng các thiết lập của môi trường chạy thật, kết quả có thể không ổn định hoặc làm thay đổi dữ liệu ngoài phạm vi kiểm thử.

**Test profile** là một tập cấu hình Spring được kích hoạt khi chạy test nhằm lựa chọn property và bean phù hợp cho môi trường thử nghiệm. Thông thường, ta dùng profile tên `test`, khai báo trong `application-test.yml` và bật bằng `@ActiveProfiles("test")`.

Mục tiêu của profile kiểm thử Spring Batch:

- Chọn database riêng cho test, có metadata schema `BATCH_*` và schema nghiệp vụ cần thiết.
- **Không tự khởi chạy job lúc ApplicationContext khởi động**; test chủ động chạy từng job hoặc step.
- Thay thế hoặc mô phỏng các phụ thuộc ngoài hệ thống như HTTP client, email gateway hoặc storage mà tình huống test không cần truy cập thật.
- Dùng dữ liệu đầu vào cố định, đường dẫn tạm và thông số có thể lặp lại.
- Kiểm soát vòng đời metadata trong `JobRepository`, tránh test này ảnh hưởng test khác.
- Giữ sự khác biệt giữa cấu hình test và production minh bạch để dễ phân tích khi test thất bại.

Test profile **không tự chạy test** và cũng **không thay thế** các công cụ test như JUnit, `@SpringBatchTest`, `JobLauncherTestUtils`, `@Sql` hay Testcontainers. Profile chọn môi trường; các công cụ đó điều khiển bài kiểm thử.

```text
JUnit test
   |
   +-- @ActiveProfiles("test")
   |          |
   |          +-- application.yml (cấu hình chung)
   |          +-- application-test.yml (cấu hình riêng test)
   |          +-- Bean @Profile("test") (nếu có)
   |
   +-- @SpringBootTest / @SpringBatchTest
              |
              +-- Test ApplicationContext
                     |
                     +-- Test DataSource + JobRepository
                     +-- Job / Step / transaction manager
                     +-- Mock/fake external dependencies
```

## 2. Phân biệt profile, property source và môi trường test

Trong Spring, **profile** là tên nhóm môi trường có thể kích hoạt (ví dụ `dev`, `test`, `staging`, `prod`). Spring Boot hỗ trợ property riêng cho profile thông qua các file `application-{profile}.properties` hoặc `application-{profile}.yml`. Spring Framework còn hỗ trợ `@Profile` để điều kiện hóa việc đăng ký bean.

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| `@ActiveProfiles("test")` | Kích hoạt profile khi chạy Spring Test | `@SpringBootTest` dùng `application-test.yml` |
| `application-test.yml` | Cung cấp cấu hình riêng khi profile `test` đang active | URL H2, `spring.batch.job.enabled=false` |
| `@Profile("test")` | Chỉ tạo bean khi profile `test` active | Fake gateway dùng trong test |
| `@Profile("!test")` | Chỉ tạo bean khi profile `test` **không** active | Gateway kết nối dịch vụ thật |
| `@TestPropertySource` | Gắn một tập property/nguồn property vào Spring Test | Override nhanh một cấu hình trong một test class |
| `@SpringBootTest(properties = ...)` | Override property tại chỗ trong một test Boot | Thay chunk size cho một tình huống |
| `@DynamicPropertySource` | Cung cấp property động trước khi ApplicationContext được tạo | JDBC URL, username/password của Testcontainers |

**Cấu hình chung** vẫn được đọc từ `application.yml` khi profile `test` active. Các property có cùng key trong `application-test.yml` có thể ghi đè giá trị chung, trừ khi nguồn cấu hình ưu tiên cao hơn (chẳng hạn một override dành riêng cho test) xác định giá trị khác.

Một mẫu tổ chức đơn giản:

```text
src/
  main/
    java/.../BatchApplication.java
    resources/
      application.yml
      application-prod.yml
  test/
    java/.../OrderJobIntegrationTest.java
    resources/
      application-test.yml
      sql/
        schema-test.sql
        orders-seed.sql
        orders-clean.sql
```

File đặt dưới `src/test/resources` chỉ có trong **test classpath** của cấu hình build thông thường. Điều này giúp các thiết lập test tránh đi theo artifact production. Việc tách file chưa đủ để bảo đảm an toàn; cần kích hoạt đúng profile và bảo đảm database đích là database thử nghiệm.

## 3. Cấu hình test profile cơ bản cho Spring Batch 5.x

Những ví dụ dưới đây áp dụng cho **Spring Boot 3.x, Spring Batch 5.x, JUnit Jupiter và Gradle**. Các phiên bản khác, đặc biệt Spring Boot 4.x/Spring Batch 6.x, có thể thay đổi package, API và quy tắc cấu hình; cần đối chiếu tài liệu theo phiên bản dự án.

### 3.1. Khai báo dependency

Ví dụ `build.gradle` dạng Groovy khi ứng dụng đã dùng plugin/BOM của Spring Boot để quản lý phiên bản:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-batch-test` cung cấp các tiện ích như `@SpringBatchTest`, `JobLauncherTestUtils`, `JobRepositoryTestUtils` và `StepScopeTestUtils`. H2 tạo database in-memory phục vụ những kiểm thử JDBC đơn giản.

### 3.2. Cấu hình production/common

Giả sử `src/main/resources/application.yml` chứa những giá trị không đặc thù môi trường:

```yaml
spring:
  application:
    name: order-batch

app:
  batch:
    chunk-size: 100
    input-directory: /var/app/orders
```

Các thông số như `app.batch.chunk-size` là **property do ứng dụng tự định nghĩa**, không phải property tự có của Spring Batch. Chúng chỉ có tác dụng nếu code ứng dụng thực sự đọc và sử dụng chúng, ví dụ qua `@ConfigurationProperties` hoặc `@Value`.

### 3.3. Cấu hình trong `src/test/resources/application-test.yml`

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:order_batch_test;DB_CLOSE_DELAY=-1
    driver-class-name: org.h2.Driver
    username: sa
    password: ''

  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always

  sql:
    init:
      mode: always
      schema-locations: classpath:sql/schema-test.sql

app:
  batch:
    chunk-size: 3
    input-directory: build/test-input

logging:
  level:
    org.springframework.batch: INFO
```

Ý nghĩa từng phần:

| Key | Tác dụng trong test |
|---|---|
| `spring.datasource.url` | Chọn H2 database riêng tên `order_batch_test`. |
| `DB_CLOSE_DELAY=-1` | Giữ H2 in-memory database sau khi kết nối cuối đóng, tới khi tiến trình JVM kết thúc. |
| `spring.batch.job.enabled=false` | Tắt cơ chế Spring Boot tự chạy các job khi application startup. Test sẽ tự gọi launcher. |
| `spring.batch.jdbc.initialize-schema=always` | Cho phép Spring Boot khởi tạo bảng và đối tượng sinh ID của `JobRepository` bằng script tương ứng platform. |
| `spring.sql.init.mode=always` | Bật khởi tạo SQL thông thường của ứng dụng. |
| `spring.sql.init.schema-locations` | Chỉ định script tạo bảng **nghiệp vụ** phục vụ test. |
| `app.batch.chunk-size` | Override tham số nghiệp vụ để test chunk boundary dễ hơn, nếu ứng dụng có sử dụng property này. |
| `app.batch.input-directory` | Đưa việc ghi/đọc tệp vào vùng dữ liệu test do ứng dụng quản lý. |

`spring.batch.jdbc.initialize-schema` dùng cho **metadata Spring Batch**; `spring.sql.init.schema-locations` dùng cho schema nghiệp vụ của ứng dụng. Nếu ứng dụng quản lý `BATCH_*` bằng Flyway hoặc Liquibase, đặt `spring.batch.jdbc.initialize-schema=never` trong test profile và chạy migration tương ứng, tránh tạo cùng bảng hai lần.

**Lưu ý phạm vi:** `spring.batch.job.enabled=false` chỉ chặn Spring Boot tự khởi chạy job lúc startup. Nó không cấm `JobLauncher`, `JobOperator`, scheduler hoặc code ứng dụng chủ động khởi chạy job. Nếu có `@Scheduled` tự chạy batch, cần kiểm soát thêm scheduler trong test.

## 4. Kích hoạt test profile đúng cách

### 4.1. Dùng `@ActiveProfiles("test")`

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class OrderJobIntegrationTest {

    @Test
    void applicationContextStartsWithTestConfiguration() {
        // Spring context được tạo với profile "test".
    }
}
```

`@ActiveProfiles` thuộc **Spring Test**. Nó được xử lý khi tạo `ApplicationContext` cho test class. Annotation này không tự kích hoạt profile cho lần chạy `java -jar` ngoài test, và cũng không thay đổi toàn bộ cấu hình JVM cho các class test khác.

Muốn dùng nhiều profile, có thể khai báo:

```java
@ActiveProfiles({"test", "integration"})
```

Khi hai profile định nghĩa cùng một key, thứ tự và thứ bậc property source có thể quyết định giá trị cuối; vì vậy tránh để nhiều profile đặt những giá trị xung đột không cần thiết. Một số test base class có thể khai báo `@ActiveProfiles` để các lớp con kế thừa. Khi thay đổi danh sách profile kế thừa, hãy xác định rõ ý định của từng lớp test.

### 4.2. Không đặt `spring.profiles.active` trong file dành riêng cho profile

Đây là cấu hình nên tránh:

```yaml
# application-test.yml — KHÔNG cấu hình như sau:
spring:
  profiles:
    active: test
```

Trong Spring Boot, `spring.profiles.active` thuộc phần cấu hình **không đặc thù profile**; đưa nó vào một tài liệu được kích hoạt bởi profile có thể gây lỗi cấu hình. Hãy đặt `@ActiveProfiles("test")` trên Spring Test, hoặc chọn profile từ lệnh chạy/chế độ launch phù hợp.

### 4.3. Các cách override cho từng tình huống

Nếu một test cần chunk size khác mặc định:

```java
@SpringBootTest(properties = "app.batch.chunk-size=1")
@ActiveProfiles("test")
class SingleItemChunkTest {
    // Khi context được tạo, property này có hiệu lực trong test.
}
```

Để nạp một file property test chuyên biệt:

```java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(locations = "classpath:overrides/retry-test.properties")
class RetryPolicyIntegrationTest {
}
```

Đây là **các lớp test minh họa riêng**. Với cùng một ứng dụng, thường dùng `application-test.yml` cho mặc định hạ tầng và chỉ dùng override mức test khi thực sự có tình huống khác biệt. Mỗi tập property khác nhau có thể khiến Spring Test tạo một context riêng, làm suite khởi động chậm hơn.

## 5. Tạo và cô lập dữ liệu test

Profile chọn database; các file SQL chuẩn bị cấu trúc và fixture.

### 5.1. Schema nghiệp vụ

Ví dụ `src/test/resources/sql/schema-test.sql`:

```sql
CREATE TABLE TEST_ORDER (
    ID BIGINT PRIMARY KEY,
    CUSTOMER_CODE VARCHAR(40) NOT NULL,
    STATUS VARCHAR(16) NOT NULL,
    TOTAL_AMOUNT DECIMAL(12, 2) NOT NULL
);
```

Các bảng `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION`, các bảng context và sequence/bảng sinh ID của chúng được tạo bởi Spring Batch initializer như mục 3.3. Không cần copy nguyên DDL `BATCH_*` vào `schema-test.sql` khi đã có initializer chạy thành công.

### 5.2. Seed và cleanup theo test method

`src/test/resources/sql/orders-seed.sql`:

```sql
INSERT INTO TEST_ORDER (ID, CUSTOMER_CODE, STATUS, TOTAL_AMOUNT) VALUES
    (1, 'A001', 'NEW', 125.50),
    (2, 'B002', 'NEW', 80.00),
    (3, 'C003', 'HOLD', 250.00);
```

`src/test/resources/sql/orders-clean.sql`:

```sql
DELETE FROM TEST_ORDER;
```

Sử dụng `@Sql` để thiết lập fixture theo từng test method:

```java
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.Sql.ExecutionPhase;

@Sql(scripts = "/sql/orders-seed.sql",
     executionPhase = ExecutionPhase.BEFORE_TEST_METHOD)
@Sql(scripts = "/sql/orders-clean.sql",
     executionPhase = ExecutionPhase.AFTER_TEST_METHOD)
```

Đoạn annotation trên được đặt ở lớp hoặc phương thức test. Schema tạo một lần trong quá trình khởi động context; seed được đưa vào trước mỗi test. Đừng đặt toàn bộ dữ liệu fixture dành riêng cho test method trong `schema-test.sql`, vì dữ liệu đó sẽ không tự được tạo lại mỗi khi method chạy.

**Cẩn trọng với cùng URL H2:** `jdbc:h2:mem:order_batch_test;DB_CLOSE_DELAY=-1` có thể tiếp tục tồn tại trong cùng JVM sau khi một context đóng. Nếu tạo nhiều context độc lập sử dụng cùng tên DB và đều khởi tạo schema, có thể gặp lỗi bảng đã tồn tại. Có thể chọn DB name riêng cho từng test context hoặc dùng cơ chế tạo/dọn schema phù hợp. Khi chạy song song, nên đảm bảo mỗi nhóm test có database/repository độc lập.

## 6. Chạy job có kiểm soát trong test profile

`@SpringBatchTest` tích hợp các tiện ích test Spring Batch. Với Spring Batch 5.x, có thể kết hợp nó cùng `@SpringBootTest` và `@ActiveProfiles("test")`:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.jdbc.Sql;
import org.springframework.test.context.jdbc.Sql.ExecutionPhase;

@SpringBatchTest
@SpringBootTest
@ActiveProfiles("test")
@Sql(scripts = "/sql/orders-seed.sql",
     executionPhase = ExecutionPhase.BEFORE_TEST_METHOD)
@Sql(scripts = "/sql/orders-clean.sql",
     executionPhase = ExecutionPhase.AFTER_TEST_METHOD)
class OrderBatchProfileIT {

    @Autowired
    private JobLauncherTestUtils launcherTestUtils;

    @Autowired
    private JobRepositoryTestUtils repositoryTestUtils;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    @Qualifier("orderJob")
    private Job orderJob;

    @BeforeEach
    void prepare() {
        repositoryTestUtils.removeJobExecutions();
        launcherTestUtils.setJob(orderJob);
    }

    @AfterEach
    void removeBatchMetadata() {
        repositoryTestUtils.removeJobExecutions();
    }

    @Test
    void processesOnlyNewOrders() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", "2026-11-16")
                .addLong("run.id", 582L)
                .toJobParameters();

        JobExecution execution = launcherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());

        Integer processed = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM TEST_ORDER WHERE STATUS = 'DONE'",
                Integer.class);
        assertEquals(2, processed);

        Integer untouched = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM TEST_ORDER WHERE STATUS = 'HOLD'",
                Integer.class);
        assertEquals(1, untouched);
    }
}
```

Ví dụ **giả định ứng dụng đã đăng ký bean `Job` tên `orderJob`** xử lý đơn hàng `NEW` thành `DONE`, đã cấu hình transaction manager và dùng bảng `TEST_ORDER`. `@SpringBootTest` khởi động application context của ứng dụng và `@SpringBatchTest` hỗ trợ các bean test. Nếu dự án có nhiều job, chỉ định chính xác job cần launch như ví dụ để không phụ thuộc vào tự động lựa chọn bean.

Các điểm cần chú ý:

1. `spring.batch.job.enabled=false` giúp **không tự chạy** `orderJob` khi test context startup; `launcherTestUtils.launchJob(parameters)` mới thực thi job.
2. `@ActiveProfiles("test")` bảo đảm test dùng H2/profile test, **nếu cấu hình và dependency wiring ứng dụng không tự override DataSource bằng bean khác**.
3. `JobParameters` có ý nghĩa định danh job instance. Nếu chạy lại job đã `COMPLETED` với cùng identifying parameters mà giữ metadata, Spring Batch có thể từ chối bằng `JobInstanceAlreadyCompleteException`.
4. `JobRepositoryTestUtils.removeJobExecutions()` xóa toàn bộ executions trong **repository mà tiện ích đang trỏ tới**. Chỉ dùng với repository dành riêng cho test, không dùng khi các test khác đang chia sẻ repository đó.
5. `@Sql` dọn dữ liệu nghiệp vụ, còn `JobRepositoryTestUtils` dọn metadata. Đây là hai nhóm dữ liệu khác nhau.
6. Thông thường không đặt `@Transactional` bao toàn bộ test method có gọi `launchJob()`; transaction của job/step có thể commit độc lập, khiến ý tưởng “rollback test sẽ dọn hết dữ liệu” không đúng trong nhiều trường hợp.

### 6.1. Chỉ chạy một step

Nếu cần kiểm thử riêng một step với hạ tầng Batch được nạp từ profile `test`, có thể dùng:

```java
JobExecution execution = launcherTestUtils.launchStep("processOrdersStep");
assertEquals(BatchStatus.COMPLETED, execution.getStatus());
```

`launchStep` là API có trong `JobLauncherTestUtils` của Spring Batch 5.x. Step được chạy trong một job test được tiện ích dựng để phục vụ test, nên các job-level listener hoặc transition của job gốc không nhất thiết được thực thi như khi launch toàn job. Khi mục tiêu là kiểm tra toàn bộ flow, hãy launch job thực sự.

## 7. Dùng `@Profile` để thay bean theo môi trường

Profile còn điều khiển bean được đăng ký trong Spring container. Giả sử job gửi thông báo sau khi hoàn thành và production dùng API bên ngoài. Trong integration test, ta muốn ghi nhận thông báo trong bộ nhớ.

```java
public interface NotificationGateway {
    void send(String orderId);
}
```

Bean production:

```java
@Configuration
@Profile("!test")
class ProductionGatewayConfiguration {

    @Bean
    NotificationGateway notificationGateway(ExternalNotificationClient client) {
        return orderId -> client.sendOrderNotification(orderId);
    }
}
```

Bean test:

```java
@TestConfiguration
class NotificationTestConfiguration {

    @Bean
    @Primary
    NotificationGateway notificationGateway() {
        return orderId -> {
            // Test fake: có thể lưu orderId vào danh sách để assertion.
        };
    }
}
```

Với phương án `@TestConfiguration`, test có thể import rõ ràng:

```java
@SpringBootTest
@ActiveProfiles("test")
@Import(NotificationTestConfiguration.class)
class NotificationBatchIT {
}
```

Các lớp `ExternalNotificationClient` và implementation cụ thể ở trên là **thành phần giả định của ứng dụng**, không phải API Spring Batch. `@Primary` giúp chọn fake khi có nhiều bean cùng kiểu, nhưng không cứu được trường hợp production bean đã khởi tạo và tự gọi dịch vụ ngoài ngay tại startup. Khi cần tắt hoàn toàn integration thật trong test, điều kiện hóa cấu hình production bằng profile/property hoặc cấu hình dependency injection rõ ràng.

Nếu muốn dùng `@Profile("test")` để chọn fake qua component scan, thay `@TestConfiguration` bằng một `@Configuration` thích hợp và đảm bảo cấu hình đó nằm trong vùng scan/import. Chỉ đặt `@Profile` lên một class chưa được Spring đăng ký thì không có hiệu lực.

### 7.1. Phân biệt fake, mock và integration thật

| Kiểu phụ thuộc | Tình huống nên dùng | Giới hạn |
|---|---|---|
| Fake triển khai interface | Test cần theo dõi dữ liệu, không phụ thuộc mạng | Phải tự xây dựng hành vi fake đủ đại diện. |
| Mockito mock | Test chỉ cần xác minh call/argument hoặc trả dữ liệu giả | Không kiểm chứng giao thức kết nối thật. |
| Test container/service thật ở môi trường test | Test tích hợp SQL, message broker, transaction hoặc protocol | Chậm hơn và cần quản lý vòng đời hạ tầng. |

Khi kiểm thử logic xử lý batch nhưng không quan tâm gateway, mock/fake thường phù hợp. Khi kiểm tra hợp đồng với Kafka, database hoặc storage, profile `test` nên trỏ tới dịch vụ test có thực (có thể chạy bằng container) và giữ nguyên interface/config quan trọng.

## 8. Điều khiển scheduler và tự khởi động job

Hai cơ chế thường bị nhầm:

- `spring.batch.job.enabled=false`: chặn cơ chế Boot tự chạy `Job` lúc application startup.
- `@Scheduled`: một phương thức ứng dụng được scheduler kích hoạt theo thời gian, có thể tự gọi `JobLauncher`.

Nếu một scheduled method vẫn hoạt động trong test, job có thể chạy song song với assertion. Nên làm cho scheduler có điều kiện:

```java
@Configuration
@EnableScheduling
@Profile("!test")
class BatchSchedulingConfiguration {
    // Đăng ký các @Scheduled task của production ở đây.
}
```

Trong ứng dụng có phương thức `@Scheduled` nằm rải rác ở các bean đã được tạo, chỉ đặt `@Profile` lên một configuration chứa `@EnableScheduling` có thể chưa phù hợp với cách scheduler được kích hoạt bởi những configuration khác. Thiết kế tốt hơn là gom việc đăng ký scheduling vào một phần cấu hình có thể bật/tắt bằng profile hoặc property, rồi khởi chạy job trực tiếp bằng tiện ích test.

Một lựa chọn dùng property riêng:

```java
@Configuration
@ConditionalOnProperty(
    prefix = "app.batch.scheduler",
    name = "enabled",
    havingValue = "true")
@EnableScheduling
class BatchSchedulerConfiguration {
}
```

Trong `application-test.yml`:

```yaml
app:
  batch:
    scheduler:
      enabled: false
```

`app.batch.scheduler.enabled` là key tự định nghĩa của ứng dụng; mẫu này chỉ có tác dụng khi scheduler được quản lý qua configuration tương ứng. Nếu có nhiều bean đang trực tiếp dùng `@Scheduled`, cần áp dụng cùng chiến lược quản lý tại những nơi đó.

## 9. Testcontainers: giữ profile test nhưng dùng database giống production

H2 thích hợp cho nhiều test, nhưng với PostgreSQL/MySQL/Oracle, SQL vendor-specific, transaction isolation và locking có thể khác đáng kể. Có thể dùng cùng profile `test` nhưng lấy kết nối từ container PostgreSQL để kiểm tra hạ tầng sát production hơn.

Ví dụ dependencies cho Spring Boot 3.1+:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}
```

### 9.1. Cung cấp datasource qua `@ServiceConnection`

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.test.context.ActiveProfiles;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
@ActiveProfiles("test-postgres")
class PostgresBatchIT {

    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @Test
    void appStartsUsingPostgres() {
        // Bổ sung truy vấn/job assertion theo mục tiêu test.
    }
}
```

Đặt `src/test/resources/application-test-postgres.yml`:

```yaml
spring:
  batch:
    job:
      enabled: false
    jdbc:
      initialize-schema: always
  sql:
    init:
      mode: always
      schema-locations: classpath:sql/schema-postgres-test.sql
```

Không khai báo URL H2 tĩnh trong profile này. `@ServiceConnection` cung cấp connection details phù hợp từ PostgreSQL container; framework tạo `DataSource` tới database tạm thời. Script metadata `BATCH_*` được chọn theo platform khi database được nhận diện đúng. Nếu Flyway/Liquibase sở hữu schema, hãy dùng migrations và chuyển `initialize-schema` sang `never`.

### 9.2. Cung cấp property bằng `@DynamicPropertySource`

Khi dự án không sử dụng `@ServiceConnection`, có thể cung cấp dữ liệu kết nối động:

```java
@Testcontainers
@SpringBootTest
@ActiveProfiles("test-postgres")
class PostgresBatchWithDynamicPropertiesIT {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void postgresProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }
}
```

Các import bổ sung: `org.springframework.test.context.DynamicPropertyRegistry` và `org.springframework.test.context.DynamicPropertySource`. Đây là **một cách thay thế** cho ví dụ `@ServiceConnection`, không cần dùng cả hai để thiết lập cùng datasource. Testcontainers cần Docker hoặc container runtime phù hợp trên máy/CI.

### 9.3. Cô lập giữa các test dùng container

Container có thể bị dùng lại theo phạm vi test class hoặc cache của Spring context. Nếu test A và B cùng làm sạch `JobRepository` đang được test khác dùng, chạy song song sẽ gây lỗi ngẫu nhiên. Cần quy định rõ quyền sở hữu database và thời điểm dọn fixture/metadata; với test restart, cần giữ nguyên database và identifying parameters giữa lần chạy lỗi và lần chạy lại.

## 10. Khi nào tách nhiều test profile?

Một profile `test` có thể đủ cho đa số module, nhưng với ứng dụng lớn có thể chia theo loại hạ tầng:

| Profile | Hạ tầng | Ví dụ tình huống |
|---|---|---|
| `test` | H2, gateway fake, job startup disabled | Integration test nhanh với SQL tương thích H2. |
| `test-postgres` | PostgreSQL Testcontainers, schema/migration thật | Test JDBC reader/writer và locking trên PostgreSQL. |
| `test-s3` | Object storage fake/emulator hoặc test endpoint riêng | Test job đọc/ghi tệp qua storage API. |
| `test-restart` | Database có lifecycle điều khiển, giữ metadata giữa hai lần launch | Test checkpoint và restart. |

Tên trên chỉ là **quy ước gợi ý**, không phải các profile mặc định của Spring Batch. Tránh tạo quá nhiều profile chỉ khác một key; thay bằng override cấp test hoặc helper configuration khi thích hợp. Chỉ tách khi hạ tầng và vòng đời test thực sự khác nhau.

## 11. Test profile và kiểm thử `@StepScope`, `@JobScope`

Bean `@StepScope`/`@JobScope` đọc tham số hoặc execution context khi scope hoạt động. Profile test cung cấp bean và property, còn **scope test utilities** cung cấp ngữ cảnh thực thi giả lập.

Ví dụ step-scoped bean:

```java
@Bean
@StepScope
public OrderFileReader orderFileReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {
    return new OrderFileReader(inputFile);
}
```

Để gọi bean này trong unit/integration test có Spring context:

```java
JobParameters params = new JobParametersBuilder()
        .addString("inputFile", "build/test-input/orders.csv")
        .toJobParameters();

StepExecution stepExecution =
        MetaDataInstanceFactory.createStepExecution(params);

String fileName = StepScopeTestUtils.doInStepScope(
        stepExecution,
        () -> orderFileReader.getFileName());

assertEquals("build/test-input/orders.csv", fileName);
```

`OrderFileReader` là class tự định nghĩa, `getFileName()` chỉ là API minh họa của ứng dụng. Để code chạy, test phải tạo/tiêm được scoped proxy từ Spring context và có cấu hình scope tương ứng. `MetaDataInstanceFactory` chỉ tạo metadata trong bộ nhớ; `StepScopeTestUtils` mới mở `StepContext` trong phạm vi callback. `@ActiveProfiles("test")` **không tự kích hoạt step scope**.

Trong Spring Batch 5.x, `@SpringBatchTest` hỗ trợ cấu hình các test listener dành cho step/job scope; có thể khai báo factory method trả về `StepExecution` trong test để listener lấy metadata tùy chỉnh.

## 12. Property precedence và lỗi cấu hình khó phát hiện

Giả sử `application-test.yml` khai báo:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:safe_test
```

Nhưng một test class có:

```java
@SpringBootTest(properties =
    "spring.datasource.url=jdbc:postgresql://example-host:5432/orders")
```

Property được đưa từ test annotation có thể ghi đè URL H2. Vì vậy, **đang ở profile `test` không đồng nghĩa chắc chắn đã kết nối vào H2**. Cần hiểu thứ tự ưu tiên của property sources, đặc biệt khi CI hoặc IDE cung cấp environment variables, system properties, `@TestPropertySource`, `@DynamicPropertySource` hay command-line flags.

Một test có thể tự xác nhận một số thuộc tính môi trường quan trọng:

```java
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.env.Environment;

class ActiveProfileCheck {

    @Autowired
    private Environment environment;

    @Test
    void testProfileIsActive() {
        assertTrue(environment.acceptsProfiles(
                org.springframework.core.env.Profiles.of("test")));
    }
}
```

Đoạn test phải nằm trong một Spring Test class có context được bật bằng `@ActiveProfiles("test")` và annotation khởi tạo context tương ứng, như `@SpringBootTest`. Việc kiểm tra profile có tác dụng hỗ trợ debug, còn khi cần chứng minh datasource thực sự trỏ vào môi trường test thì cần xác minh connection metadata/URL theo chính sách dự án, tránh chỉ dựa vào tên profile.

### 12.1. Thứ tự áp dụng properties

Quy tắc tổng quát: **nguồn cấu hình có ưu tiên cao hơn sẽ quyết định key trùng nhau**. Trong bối cảnh Spring Boot test, `@DynamicPropertySource` và các property khai báo trực tiếp cho test thường có thể ghi đè cấu hình đọc từ `application-test.yml`. Thứ bậc chính xác của toàn bộ nguồn phụ thuộc phiên bản Boot và cách khởi động; tham khảo phần *Externalized Configuration* của tài liệu Spring Boot khi nhiều nguồn cùng định nghĩa một key.

Để giảm xung đột, chỉ định cùng một key ở ít nơi nhất có thể; đặt hạ tầng mặc định trong `application-test.yml` và chỉ override tại lớp test có nhu cầu khác biệt rõ ràng.

## 13. Các lỗi thường gặp khi cấu hình Test profile

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `@ActiveProfiles("test")` nhưng test kết nối DB ngoài | `DataSource` custom hoặc property ưu tiên cao hơn đang ghi đè | Kiểm tra bean datasource, property sources và URL kết nối thực tế. |
| Job tự chạy khi context startup | Thiếu `spring.batch.job.enabled=false`, scheduler hoặc code tự launch | Tắt auto-run trong profile; kiểm soát scheduler/launcher ứng dụng riêng. |
| `Table BATCH_JOB_INSTANCE not found` | JDBC metadata chưa được khởi tạo, sai datasource/schema hoặc initializer bị tắt | Bật đúng Batch schema initializer hoặc chạy migration metadata. |
| `Table TEST_ORDER not found` | Chưa có DDL nghiệp vụ | Kiểm tra `schema-locations`, `mode` và đường dẫn resource. |
| `Table ... already exists` | Schema được tạo lại trên DB chưa reset hoặc có nhiều initializer | Tách database, chỉ dùng một chủ sở hữu DDL, quản lý lifecycle. |
| `No qualifying bean of type Job` hoặc `NoSuchBeanDefinitionException` | Job chưa được scan/import hoặc điều kiện profile đã loại bean | Xác minh component scan, `@Import`, `@Profile` và config properties. |
| `JobInstanceAlreadyCompleteException` | Cùng identifying parameters với instance đã hoàn tất | Dọn metadata test hoặc dùng instance mới; không làm vậy với restart test. |
| Test fail khi chạy song song | Dùng chung H2 database, repository hoặc cleanup toàn cục | Cô lập database/test context, tránh xóa dữ liệu của test khác. |
| `@StepScope` bean không hoạt động trong test | Chưa mở step scope | Dùng `StepScopeTestUtils`, listener hỗ trợ scope hoặc chạy step thật. |
| Test local qua, CI lỗi | Khác profile, biến môi trường, filesystem, timezone, database hoặc container runtime | Xác định đầy đủ active profiles và tài nguyên CI; giảm phụ thuộc môi trường máy cá nhân. |
| Test nhận gateway thật thay vì fake | Cả hai bean cùng được tạo hoặc fake không được import | Kiểm tra điều kiện `@Profile`, `@Primary` và cấu hình scan/import. |
| Data bị leak giữa các test | Seed và cleanup không đối xứng, job transaction commit độc lập | Dùng `@Sql` trước/sau, reset metadata đúng phạm vi, tách database theo test. |

## 14. Các lưu ý về độ tin cậy và khả năng bảo trì

### 14.1. Tránh phụ thuộc thời gian và filesystem máy cá nhân

Nhiều batch job dùng ngày hiện tại hoặc tên file gắn timestamp. Test profile nên cho phép ứng dụng nhận `Clock`, ngày nghiệp vụ hoặc input path có thể kiểm soát qua dependency injection/property. Ví dụ dùng `Clock.fixed(...)` trong một bean test nếu logic sản xuất đã được thiết kế để tiêm `Clock`. Việc chỉ giảm chunk size trong YAML không làm những giá trị phụ thuộc thời gian trở nên cố định.

Đường dẫn như `build/test-input` là tương đối theo working directory. Với test đọc/ghi file, có thể dùng `@TempDir` của JUnit để tạo vùng riêng cho test và truyền đường dẫn vào job qua `JobParameters` thay vì hard-code một thư mục dùng chung.

### 14.2. Giữ cấu hình gần production khi mục tiêu là integration test

Nếu test cần xác minh transaction, SQL paging, partitioning, restartability hoặc locking, nên giữ lại các cấu hình có ảnh hưởng và thay đúng hạ tầng ngoài bằng môi trường test tương đương. Một test sử dụng repository trong bộ nhớ nhưng production dùng JDBC `JobRepository` không kiểm chứng được các ràng buộc và transaction của database thật.

### 14.3. Không chia sẻ metadata khi đang kiểm thử restart

Trong restart test, lần chạy đầu phải thật sự thất bại, metadata `FAILED` và `ExecutionContext` cần được lưu; lần hai dùng cùng identifying parameters để Spring Batch xác định lại job instance tương ứng. Nếu dọn `JobRepository` giữa hai lần thì không còn là bài test restart. Hãy sử dụng repository riêng cho mỗi test restart hoặc một fixture được cô lập.

### 14.4. Không xem profile là cơ chế bảo mật

Profile chỉ là cơ chế lựa chọn cấu hình/bean. Test profile cần được thiết kế để không chứa production credentials và không cho phép một override vô ý kết nối môi trường thật. Credential test cũng nên đi qua biến môi trường hoặc cơ chế quản lý secret nếu cần thiết; không đưa bí mật vào repository.

### 14.5. Kiểm soát context caching

Spring Test có thể cache `ApplicationContext` giữa các lớp test có cấu hình tương thích, giúp tăng tốc. Các lớp dùng profile/property khác nhau có thể tạo context mới. Một context được tái sử dụng có thể tiếp tục giữ H2 in-memory database và singleton state. Vì vậy, khi quyết định dùng chung context, dữ liệu nghiệp vụ, trạng thái bean và metadata Batch phải được reset hoặc cô lập đúng phạm vi. Chỉ dùng `@DirtiesContext` khi thực sự cần tạo lại context, vì nó làm test suite tốn thời gian khởi động hơn.

## 15. Quy trình áp dụng Test profile cho dự án Spring Batch

Có thể xây dựng hạ tầng test theo thứ tự:

1. **Xác định loại bài kiểm thử:** unit test, test reader/writer, chạy step, chạy toàn job hay restart. Không khởi động Spring context/database cho unit test thuần nếu không cần.
2. **Chọn profile:** dùng `test` cho hạ tầng cơ bản; tạo `test-postgres` hoặc profile riêng khi có nhu cầu khác biệt thực sự.
3. **Tạo property file:** khai báo datasource test, tắt job auto-run, thiết lập chiến lược khởi tạo schema và các property nghiệp vụ test.
4. **Kích hoạt profile trong Spring Test:** dùng `@ActiveProfiles("test")`, kết hợp `@SpringBootTest` và `@SpringBatchTest` nếu chạy job/step.
5. **Xác định chủ sở hữu schema:** Batch initializer cho metadata, SQL initializer hoặc migration cho bảng nghiệp vụ, tránh chạy DDL trùng lặp.
6. **Nạp fixture dễ dự đoán:** dùng `@Sql`, builders hoặc test-data factories; giữ riêng DDL và dữ liệu seed.
7. **Điều khiển vòng đời job:** gọi `JobLauncherTestUtils` với `JobParameters` rõ ràng, không để startup/scheduler chạy hộ.
8. **Xác minh kết quả:** kiểm tra trạng thái job/step, dữ liệu nghiệp vụ và metadata khi mục tiêu cần đến repository.
9. **Dọn dữ liệu đúng phạm vi:** reset cả business data và batch metadata, tránh xóa dữ liệu của test khác đang chạy song song.
10. **Chuyển sang database thật khi cần:** với SQL vendor-specific hoặc transaction/concurrency, dùng Testcontainers và migrations để giữ độ tương đồng với production.

### Bài tập thực hành

Xây dựng hai bài test cho một job chuyển trạng thái đơn hàng:

**Bài 1 — H2 test profile:**

- Tạo `application-test.yml` với H2 in-memory và `spring.batch.job.enabled=false`.
- Tạo `TEST_ORDER` gồm các bản ghi `NEW` và `HOLD` bằng `@Sql`.
- Dùng `@SpringBatchTest` + `JobLauncherTestUtils.launchJob(...)` để chạy job.
- Kiểm tra số đơn hàng đã xử lý và dữ liệu còn nguyên trạng; cleanup dữ liệu và metadata.

**Bài 2 — PostgreSQL integration profile:**

- Tạo profile `test-postgres` với Testcontainers và migration schema đúng PostgreSQL.
- Chạy cùng ca kiểm thử nghiệp vụ ở bài 1.
- Thử đưa một ràng buộc unique/foreign key vào schema để quan sát khả năng test phát hiện lỗi dữ liệu.
- Đảm bảo hai nhóm test có repository riêng và có thể chạy độc lập trong CI.

Qua hai bài này, người học nhận thấy **test profile quyết định hạ tầng mà bài test dựa vào**, còn assertion và fixture mới quyết định điều kiện kiểm tra hành vi batch.

## 16. Tài liệu tham khảo

- [Spring Boot Reference — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html): kích hoạt profile, profile-specific files và cấu hình theo môi trường.
- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property sources, thứ tự ưu tiên và override.
- [Spring Boot Reference — SQL Database Initialization](https://docs.spring.io/spring-boot/reference/how-to/data-initialization.html): Batch metadata schema, SQL initialization và migrations.
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html): `@SpringBatchTest`, `JobLauncherTestUtils` và kiểm thử scoped beans.
- [Spring Framework Reference — Context Configuration with `@ActiveProfiles`](https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-activeprofiles.html): cách Spring Test chọn active profiles.
- [Spring Boot Reference — Testcontainers](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): container database và `@ServiceConnection` trong integration test.

