# `JobScopeTestUtils` trong Spring Batch: kiểm thử bean `@JobScope`

Trong Spring Batch, không ít thành phần xử lý dữ liệu cần nhận giá trị khi **job thực sự bắt đầu chạy**: mã khách hàng từ `JobParameters`, chế độ chạy từ `JobExecutionContext`, hoặc tên job từ `JobExecution`. Những bean đó thường được khai báo với `@JobScope`. Khi viết unit test cho một thành phần riêng lẻ, ta lại không muốn phải khởi chạy cả job chỉ để cung cấp các giá trị này.

`JobScopeTestUtils` giải quyết đúng tình huống đó: tạo môi trường **job scope đang hoạt động** trong một đoạn mã kiểm thử, để ta có thể gọi bean `@JobScope` với một `JobExecution` do chính bài test chuẩn bị.

## 1. Vì sao bean `@JobScope` khó kiểm thử như bean thông thường?

Một bean singleton thường được Spring tạo và sử dụng ngay sau khi khởi tạo application context. Ngược lại, bean `@JobScope` gắn với **một lần thực thi job** (`JobExecution`). Spring chỉ xác định target thực sự của bean khi có job context tương ứng.

Ví dụ, một processor cần biết tenant đang được xử lý:

```java
@Bean
@JobScope
PrefixingProcessor prefixingProcessor(
        @Value("#{jobParameters['tenant']}") String tenant) {
    return new PrefixingProcessor(tenant);
}
```

Ở đây, `tenant` được lấy từ tham số của **lần chạy job hiện tại**. Spring thường tiêm một *scoped proxy* cho bean; proxy có thể được inject vào test, nhưng việc gọi phương thức của nó khi không có job scope đang hoạt động sẽ thất bại. Chỉ tạo `JobParameters` riêng lẻ hoặc chỉ inject processor là chưa đủ.

Phân biệt ba khái niệm:

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| `JobParameters` | Tham số đầu vào của một lần chạy job | `tenant=north`, `date=2026-11-16` |
| `JobExecution` | Đối tượng đại diện cho một lần thực thi job; giữ job parameters và execution context | Lần chạy `processFiles` có ID `101` |
| `JobExecution.getExecutionContext()` | Dữ liệu trạng thái cấp job, có thể được cập nhật trong quá trình chạy | `prefix=READY` |

`JobScopeTestUtils` dùng `JobExecution` làm nguồn ngữ cảnh cho việc phân giải bean theo job scope.

## 2. API cốt lõi của `JobScopeTestUtils`

Class này nằm trong gói `org.springframework.batch.test` của dependency **`spring-batch-test`**. Phương thức được sử dụng là:

```java
public static <T> T doInJobScope(
        JobExecution jobExecution,
        Callable<T> callable) throws Exception;
```

- `jobExecution`: lần chạy job giả lập hoặc được chuẩn bị cho test; chứa các job parameters và job execution context mà bean sẽ đọc.
- `callable`: phần code cần thực thi khi job scope đang hoạt động. Có thể gọi một hoặc nhiều phương thức của bean `@JobScope` bên trong lambda.
- `T`: kiểu kết quả do `Callable` trả về; với code không cần trả kết quả, có thể `return null`.
- `throws Exception`: lỗi do `callable` phát sinh có thể truyền ra test để JUnit xác nhận hoặc báo lỗi.

Về mặt khái niệm, luồng hoạt động là:

```text
Test tạo JobParameters và JobExecution
                |
                v
JobScopeTestUtils.doInJobScope(jobExecution, callable)
                |
                v
Đăng ký JobContext cho luồng đang chạy test
                |
                v
Thực thi callable
  -> gọi scoped proxy
  -> tạo/tìm target bean theo JobExecution
  -> phân giải jobParameters / jobExecutionContext
                |
                v
Kết thúc callable -> dọn ngữ cảnh đã đăng ký
                |
                v
Trả về kết quả hoặc chuyển tiếp ngoại lệ
```

Điểm mấu chốt: **phải gọi bean `@JobScope` bên trong `callable`**. Nếu gọi ở ngoài, scope đã chưa được mở hoặc đã kết thúc.

## 3. Chuẩn bị dependency và cấu hình test

Với Gradle, thêm Spring Batch test utilities vào phạm vi test (giả sử dự án đã có Spring Batch Core, Spring Test và JUnit Jupiter qua dependency quản lý phiên bản):

```groovy
dependencies {
    implementation 'org.springframework.batch:spring-batch-core'
    testImplementation 'org.springframework.batch:spring-batch-test'
    testImplementation 'org.springframework:spring-test'
    testImplementation 'org.junit.jupiter:junit-jupiter'
}

test {
    useJUnitPlatform()
}
```

Hãy dùng các phiên bản Spring Batch nhất quán với Spring Framework và BOM/Spring Boot của dự án. Không cần một database, `JobRepository` hay `JobLauncher` **chỉ để** thử một bean `@JobScope` với `JobScopeTestUtils`.

Test vẫn cần một Spring application context có đăng ký `JobScope`. Trong ứng dụng Batch thông thường, cấu hình Batch đảm nhận việc này; với một context nhỏ chỉ dùng cho test, ta có thể đăng ký bean `JobScope` trực tiếp như ví dụ tiếp theo.

## 4. Ví dụ đầy đủ: test một `ItemProcessor` dùng job parameters và job execution context

Tình huống: job xử lý hóa đơn theo từng tenant. Processor nhận `tenant` từ `jobParameters` và `prefix` từ `jobExecutionContext`; việc xử lý một item là ghép các giá trị thành chuỗi `prefix/tenant/item`.

Ví dụ sau dùng **Spring Batch 5.x**, **JUnit Jupiter** và Spring Test. Có thể đặt toàn bộ mã vào `src/test/java/.../JobScopeTestUtilsExampleTest.java` (đổi package cho phù hợp):

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.configuration.annotation.JobScope;
import org.springframework.batch.core.scope.JobScope;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.test.JobScopeTestUtils;
import org.springframework.batch.test.MetaDataInstanceFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(JobScopeTestUtilsExampleTest.Config.class)
class JobScopeTestUtilsExampleTest {

    // Spring tiêm scoped proxy; target sẽ được lấy khi job scope hoạt động.
    @Autowired
    private PrefixingProcessor processor;

    @Test
    void processorReadsJobParametersAndJobExecutionContext() throws Exception {
        // 1. Chuẩn bị tham số của lần chạy job.
        JobParameters parameters = new JobParametersBuilder()
                .addString("tenant", "north")
                .toJobParameters();

        // 2. Tạo JobExecution cho test, không khởi chạy job thật.
        JobExecution execution = MetaDataInstanceFactory.createJobExecution(
                "processFiles", 7L, 101L, parameters);
        execution.getExecutionContext().putString("prefix", "READY");

        // 3. Chỉ truy cập processor trong job scope của execution vừa tạo.
        String result = JobScopeTestUtils.doInJobScope(
                execution,
                () -> processor.process("invoice-42"));

        // 4. Xác nhận late binding hoạt động đúng.
        assertEquals("READY/north/invoice-42", result);
    }

    @Configuration
    static class Config {

        // Dùng cho context test tối giản. Trong app có Batch config đầy đủ,
        // thường không cần đăng ký lại JobScope.
        @Bean
        static JobScope jobScope() {
            return new JobScope();
        }

        @Bean
        @JobScope
        PrefixingProcessor prefixingProcessor(
                @Value("#{jobParameters['tenant']}") String tenant,
                @Value("#{jobExecutionContext['prefix']}") String prefix) {
            return new PrefixingProcessor(tenant, prefix);
        }
    }

    public static class PrefixingProcessor implements ItemProcessor<String, String> {

        private final String tenant;
        private final String prefix;

        public PrefixingProcessor(String tenant, String prefix) {
            this.tenant = tenant;
            this.prefix = prefix;
        }

        @Override
        public String process(String item) {
            return prefix + "/" + tenant + "/" + item;
        }
    }
}
```

Phân tích những điểm cần hiểu:

1. `@SpringJUnitConfig` tải Spring context cho JUnit Jupiter, nhờ đó test có thể inject proxy `PrefixingProcessor`.
2. `MetaDataInstanceFactory.createJobExecution(...)` tạo metadata phục vụ test; không ghi hoặc khởi chạy job thông qua repository.
3. `execution.getExecutionContext().putString(...)` chủ động thiết lập trạng thái mà một bước trước đó có thể đã ghi ở cấp job.
4. `JobScopeTestUtils.doInJobScope(...)` kích hoạt job context cho lambda. Trong lambda, proxy mới phân giải `@Value` thành `north` và `READY`.
5. `assertEquals(...)` kiểm tra hành vi xử lý **cùng với** việc late binding lấy đúng nguồn dữ liệu.

Nếu gọi `processor.process("invoice-42")` trước hoặc sau `doInJobScope`, proxy không tìm thấy job context phù hợp và test có thể báo lỗi về scope chưa được kích hoạt.

## 5. Kiểm tra hai lần chạy job có tham số khác nhau

Một lợi ích quan trọng của `@JobScope`: một scoped proxy được inject vào test vẫn có thể trỏ tới **hai target khác nhau** khi dùng hai `JobExecution` khác nhau. Ví dụ dưới có thể thêm làm phương thức test trong class ở mục 4:

```java
@Test
void eachJobExecutionGetsItsOwnScopedValues() throws Exception {
    JobParameters firstParams = new JobParametersBuilder()
            .addString("tenant", "north")
            .toJobParameters();
    JobExecution first = MetaDataInstanceFactory.createJobExecution(
            "processFiles", 7L, 101L, firstParams);
    first.getExecutionContext().putString("prefix", "FIRST");

    JobParameters secondParams = new JobParametersBuilder()
            .addString("tenant", "south")
            .toJobParameters();
    JobExecution second = MetaDataInstanceFactory.createJobExecution(
            "processFiles", 8L, 102L, secondParams);
    second.getExecutionContext().putString("prefix", "SECOND");

    String firstValue = JobScopeTestUtils.doInJobScope(
            first, () -> processor.process("x"));
    String secondValue = JobScopeTestUtils.doInJobScope(
            second, () -> processor.process("x"));

    assertEquals("FIRST/north/x", firstValue);
    assertEquals("SECOND/south/x", secondValue);
}
```

Trong hai lời gọi, code processor không thay đổi. Giá trị đầu vào được phân giải theo `JobExecution` mà test cung cấp. Cách này hữu ích để thử nhiều tenant, ngày xử lý, cờ chức năng và tình huống job context khác nhau mà không cần chạy toàn bộ pipeline.

## 6. Khi nào dùng `JobScopeTestUtils` và khi nào dùng cách khác?

| Công cụ/cách làm | Phạm vi | Nên chọn khi |
| --- | --- | --- |
| `JobScopeTestUtils.doInJobScope(...)` | Một đoạn code cụ thể trong một test | Cần tự kiểm soát `JobExecution` và thời điểm mở scope để kiểm thử bean `@JobScope` |
| `JobScopeTestExecutionListener` | Vòng đời từng phương thức test trong Spring TestContext | Muốn framework chuẩn bị job scope tự động cho test method; có thể cung cấp `JobExecution` qua factory/field test |
| `@SpringBatchTest` | Hạ tầng test của Spring Batch; tích hợp các scope listeners và test utilities thích hợp với phiên bản | Test nhiều thành phần Batch và muốn cấu hình thuận tiện qua annotation |
| `StepScopeTestUtils.doInStepScope(...)` | Scope của `StepExecution` | Bean mang `@StepScope`, cần `stepExecutionContext` hoặc metadata cấp step |
| Chạy job qua test launcher/operator utility | Một job hoặc step thực thi thực tế | Kiểm tra luồng, transaction, reader/writer, trạng thái job/step và tích hợp nhiều thành phần |

`@JobScope` và `@StepScope` khác nhau về vòng đời và dữ liệu mà chúng quản lý. **`JobScopeTestUtils` không thay thế `StepScopeTestUtils`**: nếu bean cần một `StepExecution` đang hoạt động, cần dùng tiện ích cấp step hoặc một test thực thi step thích hợp.

`JobScopeTestExecutionListener` thường được đăng ký khi sử dụng `@SpringBatchTest`. Với `JobScopeTestUtils`, test chọn rõ đoạn nào cần scope; có thể hữu ích trong một test chỉ muốn bật scope cho đúng một lời gọi.

## 7. Những lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `ScopeNotActiveException`, `IllegalStateException` hoặc thông báo không có job context | Gọi phương thức trên scoped proxy ngoài `doInJobScope` | Đưa lời gọi thực sự truy cập bean vào bên trong lambda |
| `No Scope registered for scope name 'job'` | Spring context chưa đăng ký `JobScope` | Bật cấu hình Spring Batch phù hợp hoặc khai báo `JobScope` cho test context tối giản |
| Giá trị `@Value("#{jobParameters['...']}")` bằng `null` | Không tạo đúng khóa/tham số trên `JobExecution` được truyền vào | Tạo `JobParameters` trước, gắn chúng vào chính `JobExecution` dùng cho test |
| Giá trị `jobExecutionContext` không như mong đợi | Đặt dữ liệu vào `StepExecutionContext` hoặc nhầm `JobExecution` | Dùng `execution.getExecutionContext()` của job cần test |
| Bean `@StepScope` vẫn báo không có step scope | Mở job scope không tự tạo step scope | Dùng `StepScopeTestUtils` và một `StepExecution` phù hợp |
| Thử gọi bean từ thread khác bên trong lambda nhưng mất scope | Job context gắn với thread thực thi; không tự chuyển sang thread mới | Chạy đoạn cần test trên cùng thread, hoặc thiết lập context hợp lệ riêng ở mỗi worker thread trong bài test concurrency |

Một số thực hành giúp bài test có ý nghĩa hơn:

- Tạo `JobExecution` riêng cho mỗi kịch bản; thiết lập đầy đủ job parameters và execution context ngay trong test để dễ đọc.
- Chỉ kiểm thử hành vi cần quan sát: dữ liệu đầu ra, tham số được đọc, hoặc các lời gọi tới dependency được mock. `doInJobScope` không xác nhận rằng job thực tế hoàn thành thành công.
- Giữ processor/service dưới test độc lập với hạ tầng database khi mục đích chỉ là kiểm tra late binding hoặc nghiệp vụ.
- Không giữ tham chiếu tới **target** của scoped bean để dùng sau khi job scope kết thúc. Có thể giữ proxy do Spring inject nhưng chỉ gọi nó khi có context hợp lệ.
- Nếu lambda ném exception, hãy để test xác minh exception đó; utility quản lý đoạn scope của nó, thay vì để test tự đăng ký thủ công ngữ cảnh mà không dọn dẹp.

## 8. Phạm vi phiên bản và tài liệu tham khảo

Phương thức `JobScopeTestUtils.doInJobScope(JobExecution, Callable<T>)` có mặt trong tài liệu API Spring Batch 5.x và 6.x. Ví dụ mã đầy đủ phía trên dùng import **Spring Batch 5.x**; khi chuyển sang **Spring Batch 6.x**, cần đối chiếu các package đã được tổ chức lại, ví dụ `JobExecution` thuộc `org.springframework.batch.core.job` và các lớp job parameters thuộc `org.springframework.batch.core.job.parameters`. Ý tưởng kiểm thử với `doInJobScope` vẫn giữ nguyên.

- [API `JobScopeTestUtils` — Spring Batch 5.2.x](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/test/JobScopeTestUtils.html)
- [API `JobScopeTestUtils` — Spring Batch 6.x](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/test/JobScopeTestUtils.html)
- [API `MetaDataInstanceFactory` — tạo metadata cho test](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/test/MetaDataInstanceFactory.html)
- [API `JobScope` — khai báo bean có vòng đời cấp job](https://docs.spring.io/spring-batch/docs/current/api/org/springframework/batch/core/configuration/annotation/JobScope.html)
- [Spring Batch Reference — Testing](https://docs.spring.io/spring-batch/reference/testing.html)

Khi cần kiểm thử trực tiếp một reader, processor, writer hoặc service có `@JobScope`, hãy chuẩn bị `JobExecution` mang các giá trị cần thiết, gọi bean trong `JobScopeTestUtils.doInJobScope(...)`, rồi xác nhận kết quả. Cách này tập trung vào hành vi của thành phần cần test và tái hiện đúng dữ liệu runtime cấp job mà không cần triển khai toàn bộ quá trình chạy batch.
