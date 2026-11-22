# Spring TestContext trong kiểm thử Spring Batch

**Spring TestContext Framework** là hạ tầng kiểm thử của Spring Framework giúp test sử dụng các thành phần do Spring quản lý: tạo `ApplicationContext`, inject dependency, áp dụng profile và property dành cho test, quản lý transaction của test, chuẩn bị dữ liệu, chạy các `TestExecutionListener` và tái sử dụng context giữa nhiều test. Trong **Spring Batch Core Processing**, TestContext đặc biệt quan trọng khi cần kiểm thử reader, processor, writer, bean `@StepScope`/`@JobScope`, hoặc chạy job với `JobRepository`, `JobLauncher` và transaction manager thực tế.

JUnit chịu trách nhiệm phát hiện và chạy test; Spring TestContext cung cấp **môi trường Spring** mà các test ấy cần. Hai phần phối hợp thông qua `SpringExtension` ở JUnit Jupiter (JUnit 5).

## 1. TestContext giải quyết vấn đề gì?

Hãy xét một `ItemProcessor` phụ thuộc vào service tra cứu dữ liệu và một số cấu hình:

```java
@Component
public class OrderProcessor implements ItemProcessor<Order, ProcessedOrder> {
    private final PricingService pricingService;

    public OrderProcessor(PricingService pricingService) {
        this.pricingService = pricingService;
    }

    @Override
    public ProcessedOrder process(Order order) {
        return pricingService.calculate(order);
    }
}
```

Unit test có thể khởi tạo `OrderProcessor` trực tiếp bằng một `PricingService` giả; loại test đó **không cần** Spring TestContext. Nhưng nếu mục tiêu là xác nhận bean có được Spring tạo đúng hay không, cấu hình test có hoạt động không, proxy của bean scope có lấy đúng `JobParameters` hay không, hoặc job thực thi với repository thật có hoạt động hay không, bài test cần một `ApplicationContext`. Spring TestContext cung cấp hạ tầng chung cho các tình huống ấy.

| Nhu cầu kiểm thử | Cách tiếp cận phù hợp | Vai trò của TestContext |
| --- | --- | --- |
| Kiểm tra logic thuần của processor | JUnit + mock/stub, khởi tạo object trực tiếp | Không bắt buộc |
| Kiểm tra wiring, dependency injection, property, profile | `@SpringJUnitConfig` và context nhỏ | Tạo context, inject bean, áp dụng cấu hình |
| Kiểm tra bean `@StepScope`/`@JobScope` | Spring TestContext + Spring Batch test scope utilities/listeners | Inject scoped proxy và mở scope có `StepExecution`/`JobExecution` |
| Kiểm tra job/step tích hợp | `@SpringBatchTest` kết hợp cấu hình Spring phù hợp | Quản lý context và cung cấp Batch test utilities |
| Kiểm tra dữ liệu qua database | Spring TestContext + `@Sql`, `@Transactional`, test database | Chuẩn bị dữ liệu và quản lý transaction thuộc test |

## 2. Các thành phần chính

```text
                  JUnit Jupiter
                       |
                       v
                 SpringExtension
                       |
                       v
               TestContextManager
                       |
             +---------+----------+
             |                    |
             v                    v
      TestContext              TestExecutionListener
             |                    |
             v                    +-- DependencyInjection...
      ApplicationContext          +-- Transactional...
             |                    +-- SqlScripts...
             |                    +-- Batch scope listeners
             v
      BeanFactory / Beans
             |
             +-- ItemReader / ItemProcessor / ItemWriter
             +-- Job / Step / JobRepository / JobLauncher
             +-- Proxy của @JobScope / @StepScope
```

**Những vai trò cần phân biệt:**

- **`SpringExtension`** tích hợp Spring TestContext với lifecycle của JUnit Jupiter, ví dụ chuẩn bị test instance, xử lý dependency injection và gọi callback trước/sau test.
- **`TestContextManager`** điều phối các bước trong quá trình test; các bước này được ủy quyền cho những `TestExecutionListener` đã đăng ký.
- **`TestContext`** giữ thông tin về lớp test, phương thức đang kiểm thử, cấu hình và `ApplicationContext` đang sử dụng.
- **`ApplicationContext`** chứa các bean Spring và hạ tầng Batch. Những bean được inject vào test thường đến từ context này.
- **`TestExecutionListener`** thực hiện các hoạt động theo vòng đời test: injection, quản lý transaction, chạy script SQL, mở scope khi tích hợp Spring Batch, v.v.

`TestExecutionListener` của Spring TestContext **khác** `JobExecutionListener`/`StepExecutionListener` của Spring Batch. Loại thứ nhất chạy theo vòng đời **JUnit test**; loại thứ hai chạy theo vòng đời **job hoặc step** khi batch thực thi. Hai loại có mục đích và thời điểm kích hoạt khác nhau.

## 3. Cấu hình dependency

Ví dụ với Gradle và **Spring Batch 5.x / Spring Framework 6.x / JUnit Jupiter**. Dự án Spring Boot có thể đã nhận các dependency này qua starter và dependency management, nên chỉ khai báo phần còn thiếu:

```groovy
dependencies {
    implementation 'org.springframework.batch:spring-batch-core'

    testImplementation 'org.springframework:spring-test'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testImplementation 'org.junit.jupiter:junit-jupiter'
}

test {
    useJUnitPlatform()
}
```

Nếu dùng Spring Boot, `spring-boot-starter-test` thường cung cấp Spring Test và JUnit Jupiter. `spring-batch-test` cung cấp các tiện ích riêng của Batch, ví dụ `JobLauncherTestUtils`, `JobRepositoryTestUtils`, `StepScopeTestUtils`, `JobScopeTestUtils` và annotation `@SpringBatchTest`.

Không trộn tùy ý các major version của Spring Framework, Spring Batch và Spring Boot. Các ví dụ dùng import của **Spring Batch 5.x**; khi dự án dùng Spring Batch 6.x, đối chiếu lại API/package theo phiên bản thực tế.

## 4. Kiểm thử Spring context nhỏ bằng `@SpringJUnitConfig`

`@SpringJUnitConfig` là annotation tiện lợi kết hợp `@ExtendWith(SpringExtension.class)` và `@ContextConfiguration`. Nó thích hợp cho test cần một số bean Spring nhưng không cần khởi động toàn bộ ứng dụng.

Ví dụ đầy đủ dưới đây kiểm tra việc inject một dịch vụ định dạng mã đơn hàng theo property của môi trường test. Mã có thể đặt trong `src/test/java/.../OrderTaggerContextTest.java`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(OrderTaggerContextTest.Config.class)
@TestPropertySource(properties = "batch.region=APAC")
class OrderTaggerContextTest {

    @Autowired
    private OrderTagger tagger;

    @Test
    void injectsBeanAndResolvesTestProperty() {
        assertEquals("APAC:42", tagger.tag("42"));
    }

    @Configuration
    static class Config {

        @Bean
        OrderTagger orderTagger(@Value("${batch.region}") String region) {
            return new OrderTagger(region);
        }
    }

    static class OrderTagger {
        private final String region;

        OrderTagger(String region) {
            this.region = region;
        }

        String tag(String orderId) {
            return region + ":" + orderId;
        }
    }
}
```

Trong ví dụ:

1. JUnit Jupiter chạy test; SpringExtension nạp context từ lớp `Config`.
2. Spring tạo bean `OrderTagger` qua phương thức `@Bean`.
3. `@TestPropertySource` cung cấp `batch.region=APAC` cho context test.
4. `DependencyInjectionTestExecutionListener` đưa bean vào field `@Autowired`.
5. Assertion xác nhận cấu hình Spring và hành vi bean phối hợp đúng.

Đây là **integration test rất nhỏ ở cấp Spring context**. Nó nhanh và dễ cô lập hơn việc khởi động cả ứng dụng Batch, đồng thời vẫn kiểm tra được dependency injection thật.

### Khi nào dùng `@SpringBootTest`?

`@SpringBootTest` khởi tạo một Spring Boot application context theo cấu hình của ứng dụng. Nó phù hợp khi cần auto-configuration, repository, transaction manager, datasource hoặc batch job definitions thực tế. Không nhất thiết phải dùng `@SpringBootTest` để kiểm thử một processor chỉ có vài dependency.

Với ứng dụng Spring Boot, `@SpringBootTest` đã tích hợp Spring TestContext/JUnit Jupiter; thông thường không cần viết thêm `@ExtendWith(SpringExtension.class)`.

## 5. `ApplicationContext` cache và vòng đời test

Tạo Spring context có thể tốn thời gian, đặc biệt khi có `DataSource`, schema migration, nhiều bean hoặc repository. Spring TestContext lưu `ApplicationContext` trong **cache dùng chung trong quá trình chạy test** và có thể tái sử dụng khi các test có cấu hình tương thích.

```text
Test A -- cấu hình X --+
                      +--> ApplicationContext X trong cache
Test B -- cấu hình X --+

Test C -- cấu hình Y ----> ApplicationContext Y trong cache
```

Các thuộc tính như configuration classes, active profiles, test property sources, context customizers và context hierarchy có thể ảnh hưởng đến khóa cache. Hai lớp test có vẻ giống nhau nhưng dùng cấu hình động khác nhau vẫn có thể tạo context riêng. Context cache thường nằm trong tiến trình JVM đang chạy test; tách mỗi lớp test sang một JVM riêng sẽ không tận dụng được cache giữa các tiến trình ấy.

`@DirtiesContext` báo cho TestContext Framework rằng context đã bị làm bẩn, cần loại khỏi cache và tạo lại khi cần. Ví dụ một test thay đổi cấu hình hoặc trạng thái singleton không thể hoàn nguyên có thể dùng:

```java
import org.springframework.test.annotation.DirtiesContext;

@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class MutatingContextIntegrationTest {
    // Các test cố ý thay đổi state của context mà không thể reset sạch.
}
```

Không nên thêm `@DirtiesContext` cho mọi test một cách mặc định. Nó làm mất lợi ích cache và khiến suite chậm; trạng thái database, message queue hoặc `JobRepository` cũng không tự động được dọn sạch chỉ vì context được đóng.

Một quy tắc thiết kế hữu ích: **tái sử dụng Spring context khi cấu hình giống nhau, nhưng cô lập dữ liệu và trạng thái mà từng test thay đổi**.

## 6. Kết hợp Spring TestContext với `@SpringBatchTest`

`@SpringBatchTest` là annotation của `spring-batch-test`, hỗ trợ những thành phần kiểm thử đặc thù của Spring Batch. Trong Spring Batch 5.x, annotation này đăng ký các test utilities như `JobLauncherTestUtils` và `JobRepositoryTestUtils`, đồng thời cấu hình listener hỗ trợ test scope.

`@SpringBatchTest` **không tự thay thế** việc chỉ định Spring application context. Thông thường cần kết hợp với `@SpringBootTest` hoặc `@SpringJUnitConfig`/`@ContextConfiguration` để framework biết phải nạp những bean nào.

Ví dụ kiểm thử job đã được ứng dụng cấu hình:

```java
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
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBatchTest
@SpringBootTest(classes = BatchApplication.class)
@ActiveProfiles("test")
@TestPropertySource(properties = "spring.batch.job.enabled=false")
class ImportOrdersJobIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private Job importOrdersJob;

    @BeforeEach
    void selectJobUnderTest() {
        jobLauncherTestUtils.setJob(importOrdersJob);
    }

    @Test
    void runsJobWithControlledParameters() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", "2025-01-15")
                .addString("testScenario", "runsJobWithControlledParameters")
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
    }
}
```

**Điều kiện để ví dụ hoạt động:** project có `BatchApplication` (class `@SpringBootApplication`), bean `Job` tên `importOrdersJob`, cùng `JobRepository`, transaction manager và database test được cấu hình hợp lệ. `@SpringBootTest` nạp hạ tầng đó, còn `@SpringBatchTest` bổ sung công cụ kiểm thử. Nếu ứng dụng có nhiều bean kiểu `Job`, `@Autowired` vào field phải có tên bean phù hợp hoặc `@Qualifier` rõ ràng.

`spring.batch.job.enabled=false` tránh để Spring Boot tự khởi chạy job ngay khi context được tạo. Trong test, ta chủ động gọi `launchJob(parameters)` với dữ liệu xác định. Tham số `testScenario` giúp phân biệt kịch bản ở **một repository dùng chung** nhưng không thay thế việc cô lập repository giữa các lượt test.

Nếu một `JobInstance` với cùng job name và identifying parameters đã `COMPLETED` trong `JobRepository`, chạy lại có thể báo `JobInstanceAlreadyCompleteException`. Đây là quy tắc batch. Test tích hợp cần có chiến lược dữ liệu riêng: repository dành riêng cho test, schema được làm sạch có kiểm soát hoặc test database được tạo mới. Với test restart, giữ lại metadata của lần chạy thất bại và **không đổi** identifying parameters.

## 7. TestContext và bean `@StepScope`/`@JobScope`

Một bean `@StepScope` hoặc `@JobScope` thường được Spring inject dưới dạng proxy. Proxy cần `StepExecution` hoặc `JobExecution` hiện hành để phân giải target và biểu thức như:

```java
@Value("#{jobParameters['businessDate']}")
@Value("#{jobExecutionContext['source']}")
@Value("#{stepExecutionContext['readCount']}")
```

Khi chạy job thật, Spring Batch mở các scope tương ứng trong quá trình thực thi. Khi chỉ kiểm thử một bean, Spring TestContext có thể tạo bean/proxy nhưng scope có thể chưa hoạt động. Đó là lúc dùng `StepScopeTestUtils`, `JobScopeTestUtils` hoặc những listener được `@SpringBatchTest` hỗ trợ.

### Ví dụ: Spring TestContext + `StepScopeTestUtils`

Ví dụ sau dùng một context nhỏ và **không khởi chạy toàn bộ job**. Scope được mở chỉ trong đoạn code cần thiết:

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.scope.StepScope;
import org.springframework.batch.test.MetaDataInstanceFactory;
import org.springframework.batch.test.StepScopeTestUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(StepScopedFormatterTest.Config.class)
class StepScopedFormatterTest {

    @Autowired
    private Formatter formatter;

    @Test
    void resolvesParameterInsideStepScope() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("batchTag", "demo")
                .toJobParameters();

        StepExecution stepExecution =
                MetaDataInstanceFactory.createStepExecution(parameters);

        String result = StepScopeTestUtils.doInStepScope(
                stepExecution,
                () -> formatter.format("42"));

        assertEquals("demo-42", result);
    }

    @Configuration
    static class Config {

        @Bean
        static StepScope stepScope() {
            return new StepScope();
        }

        @Bean
        @StepScope
        Formatter formatter(@Value("#{jobParameters['batchTag']}") String tag) {
            return new Formatter(tag);
        }
    }

    static class Formatter {
        private final String tag;

        Formatter(String tag) {
            this.tag = tag;
        }

        String format(String input) {
            return tag + "-" + input;
        }
    }
}
```

Trong context test tối giản, phương thức `@Bean static StepScope stepScope()` đăng ký scope để Spring biết cách xử lý `@StepScope`. Ở ứng dụng đã cấu hình Spring Batch đầy đủ, không nên đăng ký trùng scope nếu hạ tầng đã cung cấp. `MetaDataInstanceFactory` tạo metadata thử nghiệm, còn `StepScopeTestUtils` gắn `StepExecution` vào đoạn lambda. Gọi `formatter.format(...)` ngoài scope này sẽ không có ngữ cảnh step hợp lệ.

Với bean `@JobScope`, ý tưởng tương tự nhưng dùng `JobExecution` và `JobScopeTestUtils.doInJobScope(jobExecution, callable)`. Chú ý `jobExecutionContext` là ngữ cảnh **cấp job**, còn `stepExecutionContext` là ngữ cảnh **cấp step**; chọn đúng loại scope và metadata cho dữ liệu mà bean cần.

### Các listener của Spring Batch trong TestContext

Hai listener quan trọng là:

- **`StepScopeTestExecutionListener`**: hỗ trợ tạo/kích hoạt step context cho phương thức test, có thể phát hiện một `StepExecution` được cung cấp từ test.
- **`JobScopeTestExecutionListener`**: hỗ trợ kích hoạt job context cho phương thức test, có thể sử dụng `JobExecution` mà test cung cấp.

Khi dùng `@SpringBatchTest` theo phiên bản hỗ trợ, framework đăng ký các listener này để các bài test truy cập bean theo scope thuận tiện hơn. Khi dùng `StepScopeTestUtils`/`JobScopeTestUtils`, test tự quyết định đoạn nào cần scope; cách này thường rõ ràng hơn cho một unit/integration test rất nhỏ.

## 8. Các annotation Spring TestContext thường gặp

| Annotation | Tác dụng | Lưu ý trong kiểm thử Batch |
| --- | --- | --- |
| `@SpringJUnitConfig` | Kết hợp JUnit 5 extension và cấu hình Spring context | Phù hợp test bean, service, processor hoặc cấu hình nhỏ |
| `@ContextConfiguration` | Chọn class/XML/initializer để nạp context | Có thể đi cùng `@ExtendWith(SpringExtension.class)` |
| `@SpringBootTest` | Nạp context Spring Boot | Phù hợp khi cần job, repository, database, Boot auto-configuration |
| `@SpringBatchTest` | Bổ sung Batch test utilities và scope listeners | Cần context có hạ tầng tương ứng |
| `@ActiveProfiles("test")` | Kích hoạt Spring profile `test` | Chọn datasource, service stub và batch settings dành cho test |
| `@TestPropertySource` | Thêm/ghi đè property ở cấp test | Dùng đường dẫn fixture, batch flag và cấu hình có tính lặp lại |
| `@DynamicPropertySource` | Cung cấp property động qua phương thức static | Hữu ích cho database container có URL/port được cấp khi chạy test |
| `@Sql` | Chạy SQL script trước/sau phương thức hoặc lớp test | Seed/cleanup dữ liệu nghiệp vụ trong test database |
| `@Transactional` | Mở transaction do test quản lý và thường rollback khi test kết thúc | Không mặc nhiên rollback các transaction do job/step chạy ở thread khác quản lý |
| `@DirtiesContext` | Đánh dấu context cần loại khỏi cache | Chỉ dùng khi test làm biến đổi context không thể phục hồi |
| `@TestExecutionListeners` | Bổ sung hoặc thay danh sách listener | Cẩn thận giữ các listener mặc định cần thiết |

Nếu cần tự thêm listener, sử dụng merge mode để bảo tồn những listener mà hạ tầng Spring và Batch đã đăng ký:

```java
import org.springframework.test.context.TestExecutionListeners;

@TestExecutionListeners(
        listeners = MyTestExecutionListener.class,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS)
class BatchWithCustomTestListener {
    // ...
}
```

Ví dụ minh họa cách khai báo; lớp `MyTestExecutionListener` phải được triển khai nếu sử dụng. Nếu chỉ định danh sách listener tùy chỉnh theo cách thay thế mặc định, có thể vô tình làm mất dependency injection, hỗ trợ transaction, SQL scripts hoặc listener scope mà test đang dựa vào.

## 9. Quản lý test data và transaction

Spring TestContext hỗ trợ chuẩn bị dữ liệu bằng `@Sql`:

```java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.jdbc.Sql;

@Sql(
        scripts = "/sql/seed-test-orders.sql",
        executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
class OrderRepositoryIntegrationTest {

    @Test
    void readsPreparedOrders() {
        // Gọi repository/service được Spring inject.
    }
}
```

File `seed-test-orders.sql` được đặt trong `src/test/resources/sql/`. Bài test muốn dùng `@Sql` phải có Spring TestContext và datasource/transaction infrastructure được cấu hình phù hợp.

`@Transactional` trên một test Spring thường tạo **test-managed transaction** được rollback sau test. Tuy nhiên, batch step có thể mở transaction riêng qua `PlatformTransactionManager`, và job có thể chạy trên thread khác. Vì vậy **không được giả định** rằng `@Transactional` trên phương thức JUnit sẽ rollback toàn bộ dữ liệu mà job đã ghi.

Phân biệt ba vùng trạng thái:

1. **Dữ liệu nghiệp vụ** trong các bảng như `orders`, `invoice`, `payment`.
2. **Metadata Batch** trong bảng của `JobRepository` (job instance, execution, step execution, execution context).
3. **Bean state / context state** nằm trong memory của Spring application context.

Rollback của test, làm sạch database và `@DirtiesContext` tác động lên các vùng này theo những cách khác nhau. Với integration test chạy job, nên dùng database test cô lập và quy trình setup/cleanup rõ ràng. `JobRepositoryTestUtils.removeJobExecutions()` có thể hỗ trợ dọn metadata Batch trong repository test, nhưng không xóa dữ liệu nghiệp vụ và không nên dùng trên repository chia sẻ với hệ thống khác.

Một số lưu ý khi test song song: hai test cùng chạy batch trên một repository có thể tranh chấp `JobInstance`, khóa database hoặc dữ liệu fixture. Cô lập schema/repository theo test suite hoặc điều phối các test integration cần tài nguyên chung; đừng dựa vào thứ tự chạy test để duy trì tính đúng đắn.

## 10. Chọn mức tải context phù hợp

Chi phí khởi tạo context ảnh hưởng đáng kể đến thời gian CI, nhất là khi một dự án Batch có nhiều job hoặc datasource. Có thể tổ chức test theo tầng:

| Tầng | Kiểm tra | Cách thiết lập |
| --- | --- | --- |
| Unit test | Logic chuyển đổi/validate của `ItemProcessor` | JUnit + constructor injection + stub/mock, không tải Spring |
| Context test nhỏ | Bean definition, wiring, property, profile, scope | `@SpringJUnitConfig`, chỉ khai báo bean cần thiết |
| Batch component integration | Reader/writer truy cập database/file, scope, transaction | Spring TestContext + cấu hình datasource/scope và fixture |
| Batch job integration | Luồng step/job, status, restart, metadata | `@SpringBatchTest` + application context + test `JobRepository` |

Nên dùng mức thấp nhất có thể kiểm chứng yêu cầu của bài test. Một test processor chỉ cần xác nhận phép biến đổi không nên mất thời gian mở toàn bộ application context; một test restart cần giữ metadata và chạy job sẽ không đủ nếu chỉ mock `JobRepository`.

**Tái sử dụng context hiệu quả:** hạn chế tạo cấu hình test khác nhau không cần thiết; giữ profile và property nhất quán giữa các lớp có cùng nhu cầu. **Cô lập dữ liệu hiệu quả:** cố định fixture, dùng database riêng cho integration test, chọn `JobParameters` identifying rõ ràng, dọn state đúng phạm vi và tránh thay đổi bean singleton dùng chung giữa các test.

## 11. Chẩn đoán sự cố phổ biến

| Triệu chứng | Khả năng thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Field `@Autowired` bằng `null` | Không dùng SpringExtension/TestContext; object được tạo trực tiếp bằng `new` | Bổ sung `@SpringJUnitConfig` hoặc `@SpringBootTest`, kiểm tra bean thuộc context |
| `Failed to load ApplicationContext` | Thiếu bean, property, datasource, schema hoặc cấu hình hạ tầng | Đọc nguyên nhân gốc trong exception, thu nhỏ context hoặc bổ sung test configuration |
| Có proxy `@StepScope` nhưng gọi bean lỗi `ScopeNotActiveException` | Chưa kích hoạt step context | Sử dụng scope test utility/listener và truyền `StepExecution` đúng |
| `No Scope registered for scope name 'job'` | Context test thiếu đăng ký `JobScope` | Bật cấu hình Batch phù hợp hoặc khai báo scope trong context nhỏ |
| Job tự chạy trước khi test gọi `launchJob` | Spring Boot auto-run Batch trên startup | Đặt `spring.batch.job.enabled=false` trong cấu hình test |
| `JobInstanceAlreadyCompleteException` | Repository còn metadata cho job đã hoàn tất với cùng identifying parameters | Cô lập/chuẩn bị metadata; phân biệt kịch bản instance mới và restart |
| Dữ liệu còn trong DB dù test có `@Transactional` | Job/step dùng transaction khác test-managed transaction | Dùng database test cô lập, setup/cleanup rõ ràng; không trông cậy rollback của test |
| Suite test chậm do context tạo lại nhiều lần | Dùng `@DirtiesContext` thường xuyên hoặc cấu hình test phân mảnh | Giảm thay đổi context, dùng cache, tách test không cần Spring |
| Thêm `@TestExecutionListeners` làm mất inject hoặc transaction | Đã thay thế danh sách listener mặc định | Dùng `MERGE_WITH_DEFAULTS` khi bổ sung listener |
| Test chạy độc lập nhưng thất bại khi chạy cả suite | Chia sẻ database/context state, có phụ thuộc thứ tự | Cô lập fixtures/repository, reset đúng dữ liệu; tránh shared mutable bean |

## 12. Tài liệu tham khảo

- [Spring Framework Reference — Testing, TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html)
- [Spring Framework Reference — Context Configuration with TestContext](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management.html)
- [Spring Framework Reference — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html)
- [Spring Framework Reference — TestExecutionListener](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tel-config.html)
- [Spring Framework Reference — SpringExtension và JUnit Jupiter](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/support-classes.html)
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html)
- [Spring Batch API — `@SpringBatchTest`](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/test/context/SpringBatchTest.html)
- [Spring Batch API — `StepScopeTestUtils`](https://docs.spring.io/spring-batch/docs/5.2.6/api/org/springframework/batch/test/StepScopeTestUtils.html)

Spring TestContext là nền tảng kết nối JUnit với hệ thống bean và cấu hình của Spring; `spring-batch-test` xây dựng thêm các công cụ dành riêng cho job, step và batch scope trên nền tảng đó. Để viết test Batch đáng tin cậy, hãy xác định rõ điều cần kiểm chứng, chọn context tương ứng, chuẩn bị dữ liệu có thể tái tạo và kiểm soát riêng trạng thái `JobRepository` cùng dữ liệu nghiệp vụ. Khi đó test có thể vừa phản ánh hành vi Spring Batch thực tế, vừa đủ nhanh và ổn định để chạy thường xuyên trong CI.
