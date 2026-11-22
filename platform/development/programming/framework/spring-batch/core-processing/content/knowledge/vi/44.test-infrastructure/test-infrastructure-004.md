# TestExecutionListener trong Spring Batch: hạ tầng điều khiển vòng đời kiểm thử

## 1. TestExecutionListener giải quyết vấn đề gì?

Một bài kiểm thử Spring Batch thường cần nhiều thứ hơn một phương thức `@Test`: tạo `ApplicationContext`, inject bean, chuẩn bị `JobExecution`/`StepExecution`, kích hoạt scope cho reader/writer, khởi tạo dữ liệu và dọn dẹp tài nguyên khi test kết thúc.

Trong Spring Test, **`TestExecutionListener`** là hợp đồng cho các thành phần được gọi tại những thời điểm cố định trong **vòng đời chạy test**. Spring TestContext Framework điều phối những listener này, vì vậy nhiều công việc hạ tầng có thể diễn ra tự động và nhất quán giữa các test.

Với chủ đề **Spring Batch Core Processing**, nhóm **Test infrastructure**, hai listener chuyên biệt đặc biệt quan trọng:

- **`StepScopeTestExecutionListener`**: thiết lập `StepExecution` để các bean `@StepScope` có ngữ cảnh khi test.
- **`JobScopeTestExecutionListener`**: thiết lập `JobExecution` để các bean `@JobScope` có ngữ cảnh khi test.

Annotation **`@SpringBatchTest`** giúp đăng ký những listener đó và cung cấp thêm tiện ích kiểm thử batch. Bài học giải thích cả cơ chế Spring Test tổng quát lẫn cách dùng thực tế cho Spring Batch.

Sau bài học, bạn có thể xác định callback nào chạy trước/sau test, cấu hình listener đúng, test bean có step/job scope, viết listener riêng khi thật sự cần, và chẩn đoán lỗi thiếu scope hoặc thiếu `JobParameters`.

## 2. Phân biệt những khái niệm dễ trùng tên

Trong một ứng dụng Spring Batch có thể tồn tại nhiều loại listener; chúng làm việc ở các vòng đời khác nhau.

| Thành phần | Package/nguồn | Được gọi khi nào? | Ví dụ nhiệm vụ |
|---|---|---|---|
| `TestExecutionListener` | `org.springframework.test.context.TestExecutionListener` | Khi Spring Test chạy lớp/phương thức kiểm thử | Tạo ngữ cảnh test, inject bean, gắn scope, dọn dữ liệu test |
| `StepScopeTestExecutionListener` | `org.springframework.batch.test.StepScopeTestExecutionListener` | Trong vòng đời mỗi test | Gắn `StepExecution` vào thread hiện tại để resolve `@StepScope` |
| `JobScopeTestExecutionListener` | `org.springframework.batch.test.JobScopeTestExecutionListener` | Trong vòng đời mỗi test | Gắn `JobExecution` để resolve `@JobScope` |
| `StepExecutionListener` | Spring Batch runtime | Khi **step thật** bắt đầu/kết thúc | `beforeStep`, `afterStep`, cập nhật `ExitStatus` |
| `JobExecutionListener` | Spring Batch runtime | Khi **job thật** bắt đầu/kết thúc | `beforeJob`, `afterJob`, kiểm tra kết quả job |
| `BeforeEachCallback` / `AfterEachCallback` | JUnit Jupiter extension API | Trước/sau test theo vòng đời JUnit | Extension riêng của JUnit |
| `@BeforeEach` / `@AfterEach` | JUnit Jupiter | Chuẩn bị/dọn dẹp trong chính lớp test | Tạo file fixture, reset state cụ thể của test |

Một `TestExecutionListener` **không phải** `StepExecutionListener`. Ví dụ, `StepScopeTestExecutionListener` làm cho bean step-scoped có thể được kiểm thử độc lập; nó không phát sinh một lần thực thi batch step, không chạy `ItemReader.read()` và không gọi `afterStep()` thay cho một step thật.

### Các lớp trong cơ chế thực thi

```text
JUnit Jupiter
    │
    ▼
SpringExtension
    │
    ▼
Spring TestContextManager
    │
    ├── DependencyInjectionTestExecutionListener
    ├── TransactionalTestExecutionListener
    ├── StepScopeTestExecutionListener       (spring-batch-test)
    ├── JobScopeTestExecutionListener        (spring-batch-test)
    └── Custom TestExecutionListener
               │
               ▼
       Các phương thức @Test
               │
               ├── truy cập bean @StepScope/@JobScope
               └── hoặc gọi JobLauncherTestUtils để chạy job/step
```

`SpringExtension` là cầu nối giữa JUnit 5 và Spring TestContext. Các listener được Spring quản lý theo cơ chế callback và thứ tự đã cấu hình.

## 3. Vòng đời TestExecutionListener

Interface `TestExecutionListener` cung cấp các callback mặc định. Một triển khai chỉ cần override những callback có ích cho yêu cầu của mình.

| Callback | Thời điểm điển hình | Dùng làm gì? |
|---|---|---|
| `beforeTestClass(TestContext)` | Trước các test của một lớp | Kiểm tra/chuẩn bị hạ tầng dùng cho cả lớp |
| `prepareTestInstance(TestContext)` | Sau khi tạo instance test | Dependency injection hoặc chuẩn bị instance |
| `beforeTestMethod(TestContext)` | Trước `@BeforeEach` | Gắn scope, thiết lập hạ tầng cho method |
| `beforeTestExecution(TestContext)` | Sau `@BeforeEach`, trước `@Test` | Đo thời gian/cấp tài nguyên cần tồn tại đúng trong thân test |
| `afterTestExecution(TestContext)` | Sau `@Test`, trước `@AfterEach` | Thu thập thông tin lỗi/phép đo |
| `afterTestMethod(TestContext)` | Sau `@AfterEach` | Dỡ context gắn theo method, cleanup cuối method |
| `afterTestClass(TestContext)` | Sau tất cả test trong lớp | Dọn hạ tầng dùng chung |

Một timeline thường gặp khi chạy JUnit Jupiter:

```text
beforeTestClass
  └─ tạo instance test
       └─ prepareTestInstance
            └─ beforeTestMethod
                 └─ @BeforeEach
                      └─ beforeTestExecution
                           └─ @Test
                      ┌─ afterTestExecution
                 ┌─ @AfterEach
            ┌─ afterTestMethod
afterTestClass
```

Đây là **thứ tự khái niệm** cho các callback, chưa tính các extension JUnit khác. Một lớp test có thể được tạo nhiều instance tùy chính sách lifecycle của JUnit.

### Thứ tự nhiều listener

Spring TestContext gọi các listener theo thứ tự được xác định bởi `Ordered`/`@Order` hoặc thứ tự đăng ký, tùy cơ chế phát hiện:

- Với callback **trước** test, listener có thứ tự ưu tiên cao thường chạy trước.
- Với callback **sau** test, thứ tự chạy thường được **đảo ngược**, giúp tháo dỡ đối xứng với các bước chuẩn bị.
- Các listener của Spring mặc định có thứ tự riêng để tránh lỗi như sử dụng transaction trước khi chuẩn bị dependency injection.

Nếu tạo listener mới, hãy dùng `@Order` hoặc triển khai `Ordered` khi có phụ thuộc thứ tự thực sự. Không chỉnh thứ tự listener chỉ để “cho chắc”; việc vô tình đặt cleanup trước listener quản lý transaction/scope có thể gây lỗi khó tìm.

### TestContext chứa gì?

Thông qua `org.springframework.test.context.TestContext`, listener có thể truy cập:

- Lớp test và phương thức test hiện tại.
- Instance đang được kiểm thử.
- `ApplicationContext` và những bean trong context (khi đã có).
- Exception phát sinh từ phương thức test, nếu có.
- Các thuộc tính dùng để truyền dữ liệu giữa listener trong một lượt kiểm thử.

Các thông tin này giúp listener quan sát hoặc chuẩn bị hạ tầng; chúng không có nghĩa listener nên điều khiển trực tiếp mọi logic nghiệp vụ.

## 4. Dependency và cách kích hoạt hỗ trợ Spring Batch Test

Với Spring Boot 3.x, Spring Batch 5.x và JUnit Jupiter, khai báo Gradle điển hình:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-batch'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.batch:spring-batch-test'

    // Chỉ cần khi integration test tạo JobRepository trên H2.
    runtimeOnly 'com.h2database:h2'
}
```

Hoặc Maven:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-batch</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.batch</groupId>
        <artifactId>spring-batch-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Khi dùng Spring Boot, hãy để dependency management quản lý các phiên bản tương thích, tránh gắn riêng các phiên bản Spring Test và Spring Batch khác dòng.

### @SpringBatchTest

Cách ngắn gọn nhất để dùng test infrastructure trong một Spring Batch application:

```java
import org.junit.jupiter.api.Test;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBatchTest
@SpringBootTest(
    classes = BatchApplication.class,
    properties = "spring.batch.job.enabled=false"
)
class PaymentJobTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JobRepositoryTestUtils jobRepositoryTestUtils;

    @Test
    void testInfrastructureIsAvailable() {
        // Dùng jobLauncherTestUtils để launchJob / launchStep,
        // dùng jobRepositoryTestUtils khi cần dọn metadata
        // trong repository cô lập dành riêng cho kiểm thử.
    }
}
```

`@SpringBatchTest` cung cấp các bean tiện ích `JobLauncherTestUtils`/`JobRepositoryTestUtils` và đăng ký `StepScopeTestExecutionListener`, `JobScopeTestExecutionListener`. `@SpringBootTest` nạp application context; tắt tự chạy job của Spring Boot để test có thể kiểm soát lúc khởi chạy.

**Lưu ý:** ví dụ trên giả định ứng dụng thực sự có cấu hình batch, `JobRepository`, `JobLauncher` và các bean cần thiết. Nếu có nhiều `Job`, cần chỉ định job muốn test cho `JobLauncherTestUtils`.

`@SpringBatchTest` không tự tạo dữ liệu input, không bảo đảm job chạy thành công, cũng không thay thế các assertion trên `JobExecution`, `StepExecution` và kết quả dữ liệu.

## 5. StepScopeTestExecutionListener: test bean @StepScope

### 5.1. Bài toán

Giả sử reader nhận tên file từ `StepExecutionContext`:

```java
@Bean
@StepScope
public FlatFileItemReader<Payment> reader(
        @Value("#{stepExecutionContext['inputFile']}") String inputFile) {
    // Tạo reader với resource nằm tại inputFile.
    // ...
}
```

Vì `@StepScope` là scope gắn với **một StepExecution đang hoạt động**, chỉ nạp Spring context thôi chưa đủ. Khi test truy cập proxy của bean mà chưa có step context, thường xuất hiện lỗi kiểu:

```text
Scope 'step' is not active for the current thread
```

`StepScopeTestExecutionListener` giải quyết vấn đề bằng cách cung cấp `StepExecution` trong vòng đời phương thức test. Spring Batch có thể tạo một `StepExecution` mặc định cho test; hoặc bạn cung cấp một method factory trả về `StepExecution` để đặt `ExecutionContext` cần thiết.

### 5.2. Ví dụ đầy đủ bằng Spring TestContext

Ví dụ này dùng Spring Batch 5.x, JUnit Jupiter và một bean đơn giản để tách riêng cơ chế scope khỏi đọc/ghi file hoặc metadata database. Không cần khởi chạy job thật.

```java
package com.example.batchtest;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.scope.StepScope;
import org.springframework.batch.test.MetaDataInstanceFactory;
import org.springframework.batch.test.StepScopeTestExecutionListener;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.TestExecutionListeners;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = StepScopeListenerTest.Config.class)
@TestExecutionListeners(
        listeners = StepScopeTestExecutionListener.class,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class StepScopeListenerTest {

    @Configuration(proxyBeanMethods = false)
    static class Config {

        // Đăng ký StepScope mà không cần khởi động cả JobRepository.
        @Bean
        static StepScope stepScope() {
            return new StepScope();
        }

        @Bean
        @StepScope
        InputDescriptor inputDescriptor(
                @Value("#{stepExecutionContext['inputFile']}") String path) {
            return new InputDescriptor(path);
        }
    }

    // Không khai báo final: @StepScope dùng scoped proxy theo class.
    public static class InputDescriptor {
        private final String file;

        public InputDescriptor(String file) {
            this.file = file;
        }

        public String getFile() {
            return file;
        }
    }

    @Autowired
    private InputDescriptor inputDescriptor;

    // StepScopeTestExecutionListener nhận StepExecution từ factory này.
    public StepExecution getStepExecution() {
        StepExecution execution = MetaDataInstanceFactory.createStepExecution();
        execution.getExecutionContext()
                .putString("inputFile", "fixtures/orders.csv");
        return execution;
    }

    @Test
    void resolvesValueFromStepExecutionContext() {
        assertEquals("fixtures/orders.csv", inputDescriptor.getFile());
    }
}
```

Giải thích dòng chảy:

1. `@SpringJUnitConfig` tích hợp Spring Test với JUnit 5 và nạp cấu hình thử nghiệm.
2. Cấu hình khai báo `StepScope`, sau đó đăng ký bean `InputDescriptor` theo `@StepScope`.
3. `@TestExecutionListeners(...MERGE_WITH_DEFAULTS)` bổ sung listener chuyên biệt mà vẫn giữ các listener mặc định của Spring cần thiết cho injection và hạ tầng test.
4. Listener tìm `StepExecution` do `getStepExecution()` trả về; method này chèn dữ liệu `inputFile` vào `StepExecutionContext`.
5. Khi `@Test` gọi `inputDescriptor.getFile()`, scoped proxy truy cập bean với step context đã được kích hoạt và đọc đúng chuỗi `fixtures/orders.csv`.
6. Sau test, listener giải phóng ngữ cảnh step khỏi thread.

Thực tế, trong ứng dụng đã dùng `@EnableBatchProcessing` hoặc Spring Boot Batch auto-configuration, `StepScope` thường được đăng ký sẵn. Không khai báo thêm bean `StepScope` trùng lặp trong context ứng dụng đó.

### 5.3. Một số lưu ý về factory method

- Đặt tên phương thức `getStepExecution()` và trả về đúng kiểu `StepExecution` giúp listener tìm được ngữ cảnh do test cung cấp.
- Dùng `MetaDataInstanceFactory` để tạo metadata test nhẹ, tránh phải mở kết nối database chỉ để kiểm tra biểu thức scope.
- Nếu test không cung cấp factory, listener có thể tạo `StepExecution` mặc định; tuy nhiên context mặc định không có các key nghiệp vụ như `inputFile`.
- `ExecutionContext` có các mức khác nhau: `stepExecutionContext` thuộc step, `jobExecutionContext` thuộc job. Không đặt key ở một nơi rồi tham chiếu bằng biểu thức của nơi còn lại.
- Tránh lấy bean step-scoped trong constructor của test hoặc static initializer. Scope sẽ hoạt động đúng khi listener đã gắn context trong vòng đời test method.

### 5.4. Khi chỉ muốn kích hoạt scope cho một đoạn code

Một số test cần điều khiển ranh giới scope rõ ràng, không muốn scope hoạt động trong toàn bộ method. `StepScopeTestUtils.doInStepScope` cho phép chạy một `Callable` với `StepExecution` xác định:

```java
StepExecution stepExecution =
        MetaDataInstanceFactory.createStepExecution();
stepExecution.getExecutionContext()
        .putString("inputFile", "fixtures/manual.csv");

String actual = StepScopeTestUtils.doInStepScope(
        stepExecution,
        () -> inputDescriptor.getFile()
);

assertEquals("fixtures/manual.csv", actual);
```

Đoạn code giả định `inputDescriptor` được inject từ Spring context đã đăng ký `StepScope`, và bổ sung import:

```java
import org.springframework.batch.test.StepScopeTestUtils;
```

`doInStepScope` hữu ích khi cần test nhiều bộ `ExecutionContext` trong cùng một method, hoặc khi không muốn cấu hình listener cho cả lớp. Không cần phối hợp cả hai cách nếu một cách đã đáp ứng mục tiêu kiểm thử.

### 5.5. Mức độ kiểm thử thật sự

Một test như trên **chứng minh được late binding** từ `StepExecutionContext` vào scoped bean. Nó chưa chứng minh reader mở được file, processor xử lý đúng hay writer tạo output đúng. Để kiểm tra những việc đó, hãy chạy một step/job thật qua test utility và assert dữ liệu đầu ra.

## 6. JobScopeTestExecutionListener: test bean @JobScope

`@JobScope` có vòng đời rộng hơn `@StepScope`: một bean job-scoped sống trong ngữ cảnh của `JobExecution`. Nó thường được dùng cho thông tin cấu hình dùng chung nhiều step, ví dụ tên tenant, đường dẫn gốc, thời điểm nghiệp vụ hoặc đối tượng cấu hình một lượt chạy.

`JobScopeTestExecutionListener` cung cấp `JobExecution` cho bean đó khi chạy test. Ví dụ độc lập:

```java
package com.example.batchtest;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.configuration.annotation.JobScope;
import org.springframework.batch.core.scope.JobScope;
import org.springframework.batch.test.JobScopeTestExecutionListener;
import org.springframework.batch.test.MetaDataInstanceFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.TestExecutionListeners;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = JobScopeListenerTest.Config.class)
@TestExecutionListeners(
        listeners = JobScopeTestExecutionListener.class,
        mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class JobScopeListenerTest {

    @Configuration(proxyBeanMethods = false)
    static class Config {

        @Bean
        static JobScope jobScope() {
            return new JobScope();
        }

        @Bean
        @JobScope
        RunInfo runInfo(
                @Value("#{jobExecutionContext['runLabel']}") String label) {
            return new RunInfo(label);
        }
    }

    public static class RunInfo {
        private final String label;

        public RunInfo(String label) {
            this.label = label;
        }

        public String getLabel() {
            return label;
        }
    }

    @Autowired
    private RunInfo runInfo;

    public JobExecution getJobExecution() {
        JobExecution execution = MetaDataInstanceFactory.createJobExecution();
        execution.getExecutionContext()
                .putString("runLabel", "daily-settlement");
        return execution;
    }

    @Test
    void resolvesValueFromJobExecutionContext() {
        assertEquals("daily-settlement", runInfo.getLabel());
    }
}
```

Trong ví dụ, listener dùng `JobExecution` do `getJobExecution()` trả về để kích hoạt job scope. `runInfo` được inject dưới dạng proxy, còn đối tượng thực được tạo theo ngữ cảnh job khi test gọi `getLabel()`.

Nếu nguồn giá trị là **JobParameters**, hãy tạo `JobExecution` chứa bộ `JobParameters` tương ứng và dùng biểu thức:

```java
@Value("#{jobParameters['inputFile']}") String inputFile
```

Không đồng nhất `jobParameters` với `jobExecutionContext`: tham số là dữ liệu được truyền lúc chạy job; execution context là trạng thái có thể thay đổi trong quá trình xử lý.

### Khi test cần cả job scope và step scope

Một step-scoped bean có thể tham chiếu dữ liệu ở cả hai cấp. Khi test yêu cầu cả hai, `StepExecution` và `JobExecution` phải có quan hệ nhất quán: step thuộc job execution nào thì dữ liệu job phải được gắn đúng execution đó.

Trong tình huống phức tạp, **chạy step thật với `JobParameters` do test cung cấp** thường dễ kiểm chứng hơn việc tự ghép nhiều ngữ cảnh thủ công. `@SpringBatchTest` giúp đăng ký listener cần thiết khi cả hai scope được sử dụng.

## 7. Tùy chỉnh TestExecutionListener của riêng bạn

Không phải hạ tầng test nào cũng có listener sẵn. Bạn có thể tạo listener để theo dõi thất bại, gắn trace id, thu thập diagnostic hoặc quản lý tài nguyên thử nghiệm chung.

Một cách viết ngắn là kế thừa `AbstractTestExecutionListener`, chỉ override callback cần thiết. Ví dụ ghi log khi method test ném exception:

```java
package com.example.batchtest;

import org.apache.commons.logging.Log;
import org.apache.commons.logging.LogFactory;
import org.springframework.test.context.TestContext;
import org.springframework.test.context.support.AbstractTestExecutionListener;

public class BatchFailureDiagnosticsListener
        extends AbstractTestExecutionListener {

    private static final Log log =
            LogFactory.getLog(BatchFailureDiagnosticsListener.class);

    @Override
    public void afterTestExecution(TestContext testContext) {
        Throwable failure = testContext.getTestException();
        if (failure == null) {
            return;
        }

        String testId = testContext.getTestClass().getSimpleName()
                + "#" + testContext.getTestMethod().getName();

        log.error("Batch test failed: " + testId, failure);
    }
}
```

Đăng ký listener trong test:

```java
import org.springframework.test.context.TestExecutionListeners;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

@SpringJUnitConfig(classes = SomeTestConfig.class)
@TestExecutionListeners(
    listeners = {
        StepScopeTestExecutionListener.class,
        BatchFailureDiagnosticsListener.class
    },
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class ScopedReaderTest {
    // @Autowired reader và các @Test tương ứng
}
```

Trong đoạn khai báo này, thêm import:

```java
import org.springframework.batch.test.StepScopeTestExecutionListener;
```

Listener quan sát lỗi; nó không thay thế assertion và không được che giấu exception để tạo kết quả test giả. Với tình huống thường gặp như tạo fixture riêng cho một method, `@BeforeEach` và `@TempDir` dễ đọc và tường minh hơn việc viết listener tùy chỉnh.

### Chọn callback theo mục đích

| Nhiệm vụ | Nơi thích hợp |
|---|---|
| Tạo file input khác nhau cho từng test | `@BeforeEach` cùng `@TempDir` |
| Cần inject bean từ Spring | `DependencyInjectionTestExecutionListener` mặc định |
| Kích hoạt `StepExecution` cho nhiều test | `StepScopeTestExecutionListener` |
| Kích hoạt `JobExecution` cho nhiều test | `JobScopeTestExecutionListener` |
| Theo dõi thời gian thực thi phần thân `@Test` | `beforeTestExecution` + `afterTestExecution` |
| Thu thập lỗi sau phần thân `@Test` | `afterTestExecution` |
| Tháo tài nguyên dùng suốt cả `@BeforeEach` và `@AfterEach` | `afterTestMethod` |
| Dọn job metadata ở DB test riêng | `JobRepositoryTestUtils`/fixture cleanup rõ ràng |

## 8. Đăng ký listener: tự động, thủ công và kế thừa

### Cách A — dùng @SpringBatchTest

Phù hợp với phần lớn integration test Spring Batch:

```java
@SpringBatchTest
@SpringBootTest
class JobIntegrationTest {
    // Listener cho step/job scope đã được @SpringBatchTest hỗ trợ.
}
```

Ưu điểm: ít cấu hình, đồng bộ với test utility chính thức.

### Cách B — đăng ký tường minh

Phù hợp khi chỉ cần Spring TestContext và một scope, như unit test cho scoped reader:

```java
@SpringJUnitConfig(classes = ReaderConfig.class)
@TestExecutionListeners(
    listeners = StepScopeTestExecutionListener.class,
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class ReaderScopeTest {
}
```

`MERGE_WITH_DEFAULTS` giúp giữ các listener mặc định từ Spring Test. Nếu bỏ lựa chọn này và khai báo danh sách không phù hợp, bạn có thể vô tình làm mất listener injection hoặc transaction mà test đang dựa vào.

### Cách C — bổ sung listener riêng khi đã dùng @SpringBatchTest

Khi thêm một listener tùy chỉnh vào cấu hình đã có `@SpringBatchTest`, cần chú ý **thứ tự và cơ chế kế thừa/merge annotation**. Có thể sử dụng `@TestExecutionListeners(..., mergeMode = MERGE_WITH_DEFAULTS)`, đồng thời đảm bảo các listener batch cần thiết còn xuất hiện trong cấu hình hiệu lực. Nếu cần, khai báo tường minh cả batch listener và custom listener trong test.

Đừng đăng ký trùng listener thủ công và qua annotation meta mà không hiểu cách Spring gộp danh sách. Kiểm tra hành vi ở phạm vi test để chắc chắn scope được kích hoạt đúng thời điểm.

### Cách D — JUnit extension riêng

Nếu bài toán chỉ liên quan JUnit (không cần `TestContext`, `ApplicationContext` hay scope Spring), một `BeforeEachCallback`/`AfterEachCallback` có thể phù hợp hơn. `TestExecutionListener` nên dành cho cơ chế gắn với Spring TestContext.

## 9. Kiểm thử listener và step/job thật liên hệ ra sao?

Các listener test chủ yếu cung cấp **bối cảnh**, còn Spring Batch runtime mới quyết định đọc, xử lý, ghi và commit dữ liệu.

Ví dụ flow kiểm thử một job nhận tên file từ `JobParameters`:

```text
JUnit @Test
  │
  ├─ @SpringBatchTest
  │    ├─ Spring TestContext
  │    ├─ StepScopeTestExecutionListener
  │    └─ JobScopeTestExecutionListener
  │
  └─ JobLauncherTestUtils.launchJob(parameters)
         │
         ├─ JobRepository tạo JobExecution
         ├─ Step thực thi trong transaction/chunk
         │    ├─ @StepScope reader lấy inputFile
         │    ├─ ItemProcessor
         │    └─ @StepScope writer lấy outputFile
         │
         └─ Trả JobExecution
                 ├─ assert BatchStatus
                 ├─ assert readCount/writeCount/skipCount
                 └─ assert file output
```

Mẫu test tích hợp:

```java
@SpringBatchTest
@SpringBootTest(
    classes = BatchApplication.class,
    properties = {
        "spring.batch.job.enabled=false",
        "spring.batch.jdbc.initialize-schema=always"
    }
)
class ImportJobTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @TempDir
    Path tempDir;

    @Test
    void readsAnInputResourceAndWritesTheExpectedOutput()
            throws Exception {

        Path input = tempDir.resolve("input.csv");
        Path output = tempDir.resolve("output.csv");

        Files.writeString(input, "id,amount\n1,10.00\n",
                StandardCharsets.UTF_8);

        JobParameters parameters = new JobParametersBuilder()
                .addString("inputFile", input.toString())
                .addString("outputFile", output.toString())
                .toJobParameters();

        JobExecution execution = jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.COMPLETED, execution.getStatus());
        assertTrue(Files.exists(output));
        // Thêm assert nội dung thật và read/write/skip count.
    }
}
```

Các import cần thiết cho đoạn trên:

```java
import static org.junit.jupiter.api.Assertions.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
```

`BatchApplication` đại diện cho application thật đã cấu hình Job, Step, reader và writer; đoạn test chỉ minh họa cách dùng hạ tầng. Nếu project không có schema metadata hoặc datasource phù hợp, integration test sẽ không chạy chỉ nhờ `@SpringBatchTest`.

**Phân biệt hai tình huống:**

- Test **bean `@StepScope` trực tiếp**: listener là phần thiết yếu để mock/setup scope; không phải chạy job.
- Test **job/step thật** qua launcher: Spring Batch tự thiết lập scope trong khi step thực thi; `@SpringBatchTest` cung cấp test utilities và tích hợp ngữ cảnh kiểm thử.

Không nên dùng kết quả test scoped bean đơn lẻ làm bằng chứng rằng cả job đã xử lý đúng tài nguyên.

## 10. Giao dịch, dữ liệu test và thứ tự cleanup

Hạ tầng test Spring có thể kết hợp các listener khác như `TransactionalTestExecutionListener` và `SqlScriptsTestExecutionListener`. Khi viết kiểm thử batch, đây là nơi dễ phát sinh lỗi nếu giả định rằng mọi dữ liệu đều rollback cùng một transaction.

### Trường hợp điển hình

1. Một test được đánh dấu `@Transactional`; Spring Test mở transaction bao quanh test theo chính sách của `TransactionalTestExecutionListener`.
2. Test gọi `JobLauncherTestUtils.launchJob(...)`.
3. Job/step thực thi bằng transaction manager và ranh giới commit riêng.
4. Test kỳ vọng dữ liệu batch sẽ luôn rollback theo transaction bao ngoài.

Kỳ vọng đó **không luôn đúng**. Job có thể chạy ở luồng/transaction khác; cấu hình `JobRepository` và business database cũng ảnh hưởng cách transaction vận hành. Cần thiết kế fixture và cleanup theo hành vi thực tế của job.

Với integration test batch:

- Dùng database test riêng hoặc schema cô lập; đừng dựa vào rollback của test để dọn mọi thay đổi do job đã commit.
- Khởi tạo trạng thái cần thiết một cách tường minh trước test.
- Dùng tham số định danh phù hợp nếu chạy nhiều `JobInstance`; chạy lại một instance đã `COMPLETED` không tạo một lượt chạy mới giống nhau.
- Nếu dùng `JobRepositoryTestUtils.removeJobExecutions()`, chỉ áp dụng trên repository **dành riêng cho kiểm thử**, vì thao tác này xóa metadata thực thi.
- Tài nguyên tệp nên ở `@TempDir`, không dùng chung đường dẫn cố định giữa các phương thức hoặc luồng test.

### Vòng đời scope và lỗi trong @AfterEach

Một bean step-scoped có thể cần context khi được gọi trong `@AfterEach`. Do `StepScopeTestExecutionListener` thường tháo scope tại `afterTestMethod`, cơ chế listener cho phép các thao tác dọn dẹp trong `@AfterEach` được thực thi khi ngữ cảnh còn phù hợp. Tuy vậy, tránh giữ tham chiếu đến đối tượng target step-scoped để truy cập sau khi test đã hoàn tất hoặc trên một thread không được gắn context.

Trong kiểm thử song song, context scope theo thread không đồng nghĩa an toàn cho dữ liệu chia sẻ: file, tên bảng, static state và repository chung vẫn có thể xung đột.

## 11. Lỗi thường gặp khi cấu hình TestExecutionListener

| Dấu hiệu | Nguyên nhân phổ biến | Hướng xử lý |
|---|---|---|
| `Scope 'step' is not active for the current thread` | Truy cập bean `@StepScope` không có `StepExecution` đang gắn | Bổ sung `StepScopeTestExecutionListener`, dùng `@SpringBatchTest` hoặc `StepScopeTestUtils` |
| `Scope 'job' is not active for the current thread` | Truy cập bean `@JobScope` không có `JobExecution` | Dùng `JobScopeTestExecutionListener`/`@SpringBatchTest` |
| `No Scope registered for scope name 'step'` | Spring context chưa đăng ký `StepScope` | Dùng batch configuration hoặc bean `StepScope` cho context thử nghiệm tối giản |
| Giá trị `@Value` trong scoped bean là `null` | Key không có trong context hoặc sai loại context | Kiểm tra biểu thức `stepExecutionContext`, `jobExecutionContext` và `jobParameters` |
| `@Autowired` không inject bean | Listener mặc định đã bị thay thế khi khai báo thủ công | Bật `MERGE_WITH_DEFAULTS` và giữ hạ tầng Spring Test injection |
| Unit test chạy nhưng job integration test lỗi metadata | Scope mock hoạt động, nhưng JobRepository/DB chưa được cấu hình | Cấu hình database, schema, transaction manager và batch infrastructure riêng cho integration test |
| Test chạy độc lập qua, chạy cả suite thì thất bại | Shared file, job parameters, test DB hoặc context mutable | Sử dụng `@TempDir`, fixture cô lập và quản lý `JobInstance` |
| Sau khi test xong vẫn lỗi truy cập scoped bean | Dùng target sau khi scope đã đóng hoặc qua thread khác | Chỉ truy cập trong vòng đời scope hoặc cấp context phù hợp cho thread |
| Lỗi tạo scoped proxy với class cuối cùng | `@StepScope`/`@JobScope` thường dùng class-based scoped proxy | Dùng bean type có thể proxy hoặc thiết kế interface/proxy phù hợp |
| Listener custom làm mất output lỗi gốc | Listener tự ném exception khi dọn dẹp | Bảo đảm cleanup ổn định, ghi nhận lỗi phụ mà không che khuất lỗi test quan trọng |

### Cách chẩn đoán có hệ thống

Khi gặp lỗi scope, đi theo luồng:

```text
Có @SpringJUnitConfig / @SpringBootTest và SpringExtension?
    │
    ├─ Không -> Spring TestContext chưa được kích hoạt.
    │
    └─ Có
        │
        ▼
Context có đăng ký StepScope / JobScope?
    │
    ├─ Không -> Cấu hình scope.
    │
    └─ Có
        │
        ▼
Có listener / StepScopeTestUtils tương ứng?
    │
    ├─ Không -> Gắn StepExecution / JobExecution.
    │
    └─ Có
        │
        ▼
Context có key mà @Value tham chiếu?
    │
    ├─ Không -> Khởi tạo đúng ExecutionContext / JobParameters.
    │
    └─ Có -> Xét thread, thời điểm truy cập, proxy và context thực tế.
```

Những bước trên giúp phân biệt lỗi hạ tầng test với lỗi nghiệp vụ trong reader/processor/writer.

## 12. Thực hành: kiểm thử listener theo từng mức

### Bài tập 1 — Giá trị từ StepExecutionContext

Tạo bean `@StepScope` đọc `stepExecutionContext['batchSize']`. Viết test sử dụng `StepScopeTestExecutionListener` với `getStepExecution()` để cấp giá trị `batchSize=50` và assert bean nhận đúng số nguyên.

Tiếp theo bỏ factory method và quan sát khác biệt khi default context thiếu key. Giải thích vì sao listener kích hoạt scope nhưng không tự tạo ra dữ liệu nghiệp vụ.

### Bài tập 2 — Giá trị từ JobExecutionContext

Tạo bean `@JobScope` có thuộc tính `tenant` lấy từ `jobExecutionContext['tenant']`. Test hai dữ liệu giả định `"shop-A"` và `"shop-B"` bằng hai `JobExecution` khác nhau hoặc hai phương thức test độc lập. Đảm bảo scoped bean không dùng lại dữ liệu sai giữa các lần.

### Bài tập 3 — Manual scope versus listener

Dùng cùng bean `@StepScope` để viết hai test:

- Test A: đăng ký `StepScopeTestExecutionListener`.
- Test B: chỉ kích hoạt scope cho một callback qua `StepScopeTestUtils.doInStepScope`.

Đối chiếu phạm vi hiệu lực và trường hợp nào dễ đọc hơn.

### Bài tập 4 — Listener chẩn đoán

Viết `BatchFailureDiagnosticsListener` để log tên method và exception khi test thất bại. Chạy một test cố tình sai assertion. Xác nhận test vẫn **FAILED** và thông tin lỗi gốc còn nguyên.

### Bài tập 5 — Tích hợp job thật

Dùng `@SpringBatchTest` kiểm thử một job đọc CSV, cộng phí rồi ghi CSV:

1. Tạo input/output trong `@TempDir`.
2. Truyền đường dẫn qua `JobParameters`.
3. Gọi `JobLauncherTestUtils.launchJob(...)`.
4. Assert `BatchStatus.COMPLETED`, `readCount`, `writeCount` và toàn bộ nội dung output.
5. Tạo input lỗi để quan sát `BatchStatus.FAILED`; giải thích sự khác biệt với lỗi không kích hoạt scope trong unit test.

## 13. Ghi chú về phiên bản và API

Các ví dụ khai báo và import trong bài phù hợp với **Spring Batch 5.x, Spring Framework 6.x và JUnit Jupiter**. Đối với Spring Batch 6.x, hãy dùng tài liệu API tương ứng để cập nhật các class bị thay đổi package hoặc test utility. Cơ chế Spring TestContext `TestExecutionListener` và mục đích của hai listener scope vẫn là nền tảng quan trọng.

Trong Spring Batch 5.x, `JobLauncherTestUtils.launchJob()/launchStep()` thường được dùng khi test batch. Ở Spring Batch 6.x, các API `JobOperatorTestUtils.startJob()/startStep()` là hướng thay thế khi nâng cấp bộ test utility. Khi migrate, kiểm tra dependency và import của toàn bộ project theo cùng một phiên bản Spring Batch.

Không nên chép import của một ví dụ Spring Batch 5.x vào project Spring Batch 6.x rồi chỉ đổi tên test utility; cần đối chiếu tài liệu API của dòng phiên bản đó.

## 14. Tài liệu tham khảo

- [Spring Framework — TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html): kiến trúc kiểm thử dựa trên Spring context, callback và listener.
- [Spring Framework — TestExecutionListener](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tel-config.html): đăng ký, tự phát hiện, thứ tự và kế thừa listener.
- [Spring Batch — Unit Testing](https://docs.spring.io/spring-batch/reference/testing.html): `@SpringBatchTest`, step/job scoped testing và test utilities.
- [Spring Batch — Late Binding of Job and Step Attributes](https://docs.spring.io/spring-batch/reference/step/late-binding.html): `@StepScope`, `@JobScope` và dữ liệu thực thi được bind muộn.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): vòng đời JUnit Jupiter và extension model.

`TestExecutionListener` cung cấp cơ chế nối vòng đời kiểm thử với hạ tầng Spring. Với Spring Batch, hiểu rõ `StepScopeTestExecutionListener`, `JobScopeTestExecutionListener` và `@SpringBatchTest` giúp kiểm thử đúng các bean phụ thuộc ngữ cảnh batch, đồng thời phân biệt rạch ròi việc **thiết lập test context** với việc **chạy một job/step thật và xác minh kết quả dữ liệu**.
