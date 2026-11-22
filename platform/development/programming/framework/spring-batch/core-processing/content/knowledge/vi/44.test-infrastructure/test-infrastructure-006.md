# Context cache trong hạ tầng kiểm thử Spring Batch

Một bài kiểm thử tích hợp Spring Batch thường cần khởi tạo nhiều thành phần: `ApplicationContext`, cấu hình `Job` và `Step`, `ItemReader`, `ItemProcessor`, `ItemWriter`, `JobRepository`, transaction manager và kết nối tới cơ sở dữ liệu test. Nếu mỗi phương thức kiểm thử đều dựng lại toàn bộ hệ thống này, bộ test có thể chậm đáng kể dù dữ liệu thử chỉ có vài dòng.

**Context cache** của **Spring TestContext Framework** giải quyết chi phí khởi tạo đó bằng cách lưu và tái sử dụng những `ApplicationContext` đã được tạo với cùng một cấu hình kiểm thử. Trong Spring Batch, hiểu cơ chế này giúp viết integration test nhanh hơn, đồng thời tránh lỗi rất khó nhận ra: test A chạy thành công một mình nhưng test B thất bại khi cả hai chạy cùng nhau vì dữ liệu batch hoặc trạng thái một bean còn sót lại.

Điểm cần phân biệt ngay từ đầu:

> **Context cache tái sử dụng cấu hình và các bean trong `ApplicationContext`; nó không tự dọn dữ liệu nghiệp vụ, lịch sử `JobExecution` hay mọi trạng thái do các bài test tạo ra.**

Bài này giải thích cách cache được xác định, khi nào được dùng lại, mối quan hệ với `@SpringBatchTest`, cách cô lập dữ liệu batch, tình huống cần `@DirtiesContext` và phương pháp đọc log để tìm nguyên nhân khởi tạo context nhiều lần.

## 1. Context cache là gì?

Khi một test sử dụng Spring TestContext, chẳng hạn qua `@SpringBootTest`, `@ContextConfiguration` hoặc các test slice của Spring Boot, framework cần nạp một `ApplicationContext` để chạy test. Việc nạp có thể phải thực hiện:

- Đọc cấu hình và tạo các bean của Spring.
- Áp dụng `@Profile`, properties và các bean thay thế dành cho test.
- Khởi tạo `DataSource`, transaction manager và cơ sở hạ tầng Spring Batch.
- Tạo các định nghĩa `Job`/`Step`; khởi tạo bean singleton đủ điều kiện.
- Thiết lập các thành phần khác theo cấu hình ứng dụng: JPA, security, messaging, web layer, v.v.

Sau khi tạo thành công, Spring TestContext lưu context trong một **cache tĩnh** gắn với tiến trình JVM đang chạy test. Các phương thức hoặc lớp test sau đó có cấu hình tương đương có thể nhận lại context đã khởi tạo thay vì dựng mới.

~~~mermaid
flowchart TD
    A["Test cần ApplicationContext"] --> B["Tính context cache key"]
    B --> C{"Cache có context hợp lệ\nvới key đó?"}
    C -->|Có| D["Tái sử dụng ApplicationContext"]
    C -->|Không| E["Nạp context mới"]
    E --> F["Đưa context vào cache"]
    F --> G["Chạy test"]
    D --> G
    G --> H["Test tiếp theo"]
    H --> B
~~~

Ví dụ: một lớp `ImportJobIntegrationTest` có ba phương thức test dùng cùng `@SpringBootTest` thường được nạp một context cho cả ba phương thức. Nếu lớp `ExportJobIntegrationTest` có **cùng cấu hình context** và cùng JVM, nó cũng có thể tái sử dụng context đó. Cơ chế này không cần người viết test tự tạo singleton cache.

**Context cache không phải cache kết quả kiểm thử.** Mỗi bài test vẫn chạy các assertion, xử lý dữ liệu và job theo yêu cầu. Cache chỉ tránh lặp lại phần khởi tạo ngữ cảnh Spring đủ điều kiện dùng chung.

## 2. Cache được nhận diện bằng khóa nào?

Spring không chỉ dựa vào tên lớp test. Spring TestContext xây dựng một **cache key** từ `MergedContextConfiguration`, gồm những thông tin cấu hình có ảnh hưởng đến cách nạp context.

| Thành phần của khóa | Ví dụ | Vì sao ảnh hưởng cache |
|---|---|---|
| `locations` và `classes` | `@ContextConfiguration(classes = TestBatchConfig.class)` | Danh sách nguồn cấu hình khác có thể tạo các bean khác. |
| `contextInitializerClasses` | Custom `ApplicationContextInitializer` | Initializer có thể thay đổi context. |
| `contextLoader` | Loader chuẩn hoặc loader riêng | Cách tạo context khác nhau. |
| `activeProfiles` | `@ActiveProfiles("test")`, `@ActiveProfiles("integration")` | Các profile có thể kích hoạt bean hoặc cấu hình khác. |
| `propertySourceDescriptors` | `@TestPropertySource(locations = "...")` | Nguồn property được khai báo khác nhau. |
| `propertySourceProperties` | `@TestPropertySource(properties = "...")` | Giá trị cấu hình inline khác nhau. |
| `contextCustomizers` | `@DynamicPropertySource`, các khai báo mock/override bean | Các tùy chỉnh bổ sung có thể làm context khác. |
| `parent` | `@ContextHierarchy` | Context cha là một phần của cấu hình. |
| `resourceBasePath` | `@WebAppConfiguration` | Áp dụng cho môi trường kiểm thử web. |

Trong Spring Boot, `@SpringBootTest(properties = "...")`, kiểu môi trường web, các test slice, `@Import` và khai báo mock/override bean có thể tạo sự khác biệt thông qua cấu hình hoặc context customizer. **Hai lớp test chỉ cùng dùng `@SpringBootTest` không đủ để kết luận chắc chắn sẽ trúng cùng một cache entry.**

Ví dụ:

~~~java
@SpringBootTest(properties = "spring.batch.job.enabled=false")
@ActiveProfiles("test")
class ImportJobTest {
    // ...
}

@SpringBootTest(properties = "spring.batch.job.enabled=false")
@ActiveProfiles("test")
class ExportJobTest {
    // ...
}
~~~

Hai lớp này **có khả năng** dùng chung context nếu các cấu hình khác cũng tương đương và đang chạy trong cùng tiến trình JVM. Ngược lại:

~~~java
@SpringBootTest(properties = "app.batch.chunk-size=2")
class SmallChunkTest {
    // ...
}

@SpringBootTest(properties = "app.batch.chunk-size=50")
class LargeChunkTest {
    // ...
}
~~~

Các properties khác nhau dẫn đến các cấu hình context khác nhau, nên không nên kỳ vọng chúng chia sẻ cùng cache entry. Những test sử dụng `@MockBean` của Spring Boot (ở các phiên bản còn hỗ trợ), hoặc `@MockitoBean` trong hệ sinh thái Spring Framework mới hơn, cũng có thể thay đổi khóa cache theo các bean được override.

**Tên phương thức test, tên dữ liệu CSV và dữ liệu hiện có trong database không tự động tạo một cache key mới.** Đây là nguồn gốc của nhiều lỗi phụ thuộc thứ tự chạy.

## 3. Context cache tương tác với Spring Batch như thế nào?

Trong Spring Batch, một context được tái sử dụng thường chứa các bean cấu hình của hệ thống:

- `Job` và `Step` mô tả pipeline xử lý.
- `JobLauncher` và `JobRepository` để điều phối và lưu metadata của job.
- `PlatformTransactionManager`, `DataSource` hoặc thành phần persistence.
- Các reader/processor/writer và listener được đăng ký.
- Các bean test utility do `@SpringBatchTest` cung cấp.

Nhưng **tái sử dụng bean** và **tái sử dụng trạng thái thực thi** là hai chuyện khác nhau:

| Thứ được tái sử dụng hoặc còn tồn tại | Context cache có liên quan thế nào? | Cách quản lý khi test |
|---|---|---|
| Cấu hình `Job`/`Step` và singleton beans | Thường được tái sử dụng cùng context. | Để bean không chứa trạng thái thay đổi ngoài ý muốn. |
| `JobRepository` bean | Có thể là cùng bean. | Phải quản lý các bản ghi metadata do nó lưu. |
| Bảng nghiệp vụ do writer cập nhật | Không được dọn chỉ vì cache hit/miss. | Reset database hoặc dùng dữ liệu tách biệt cho từng test. |
| `BATCH_JOB_INSTANCE`, `BATCH_JOB_EXECUTION`, `BATCH_STEP_EXECUTION` và bảng liên quan | Là dữ liệu trong repository, có thể tồn tại qua nhiều test. | Dọn metadata trong database test hoặc dùng chiến lược `JobParameters` rõ ràng. |
| `ExecutionContext` của một job/step execution | Gắn với execution và metadata; không phải cache của TestContext. | Tạo execution riêng hoặc chủ động kiểm tra restart cùng execution phù hợp. |
| `@StepScope` và `@JobScope` | Bean được giải quyết theo ngữ cảnh execution/scope. | Thiết lập scope của test đúng cách; không chia sẻ trạng thái xử lý tùy tiện. |
| H2 in-memory database | Có thể tồn tại cùng kết nối và tùy cấu hình vòng đời DB. | Không mặc định “in-memory” đồng nghĩa với rỗng trước mỗi test. |
| Cơ sở dữ liệu ngoài, Kafka, filesystem, HTTP mock server | Không thuộc vòng đời cache Spring một cách tổng quát. | Dọn hoặc cô lập theo loại tài nguyên. |

Ví dụ cụ thể: `JobRepository` được tái sử dụng nhưng database vẫn chứa một `JobInstance` đã **COMPLETED** với tập `JobParameters` xác định. Nếu test khác gọi lại cùng job với cùng identifying parameters, Spring Batch có thể thông báo `JobInstanceAlreadyCompleteException`. Việc này không chứng tỏ cache hỏng: hạ tầng batch đã nhớ kết quả lần chạy trước trong repository, đúng theo thiết kế.

Một ví dụ khác: singleton writer giữ biến `List` để thu thập bản ghi test. Nếu biến không được xóa trước mỗi test, lần sau có thể thấy dữ liệu cũ. Tốt hơn nên dùng collector được reset có chủ đích hoặc thực thi từng lần trong scope phù hợp, thay vì phụ thuộc vào việc Spring khởi tạo lại context.

## 4. Phân biệt context cache, transaction và checkpoint

Ba khái niệm có phạm vi khác nhau:

| Cơ chế | Quản lý gì? | Khi nào có hiệu lực? |
|---|---|---|
| **Spring TestContext cache** | Tái sử dụng `ApplicationContext` giữa các test có cấu hình phù hợp. | Trong tiến trình JVM chạy test. |
| **Transaction của chunk** | Commit hoặc rollback các thay đổi thuộc transaction khi step đọc/xử lý/ghi chunk. | Trong một lần thực thi step. |
| **Spring Batch checkpoint/ExecutionContext** | Lưu tiến độ và trạng thái cần cho restart. | Theo `JobExecution`/`StepExecution` và repository. |

**Context cache hit không đồng nghĩa với job restart.** Muốn kiểm thử restart, phải tạo tình huống một execution thất bại rồi tiếp tục đúng `JobInstance` theo quy tắc Spring Batch. **Context cache miss cũng không có nghĩa là xóa lịch sử job.** Nếu database vẫn giữ các bảng metadata, context mới đọc lại cùng lịch sử đó.

Đặc biệt, một phương thức test gắn `@Transactional` không bảo đảm toàn bộ thao tác của job được rollback khi test kết thúc. Job launcher, step, các chunk và repository có thể quản lý transaction với ranh giới riêng; ở một số cấu hình, gọi `JobLauncher` từ một transaction có sẵn còn gây lỗi do kiểm tra transaction của `JobRepository`. Với integration test chạy job thật, nên xác định rõ ranh giới giao dịch và **dọn dữ liệu qua cơ chế dành cho test**, thay vì trông đợi một annotation cấp test sẽ hoàn tác mọi side effect.

## 5. Sử dụng @SpringBatchTest với SpringBootTest

`@SpringBatchTest` cung cấp hỗ trợ kiểm thử Spring Batch, bao gồm các tiện ích như `JobLauncherTestUtils`, `JobRepositoryTestUtils` và hỗ trợ tạo ngữ cảnh job/step scope cho test. Nó phục vụ việc **điều khiển và kiểm thử batch**, còn cơ chế lưu và tái sử dụng `ApplicationContext` do Spring TestContext Framework quản lý.

Với ứng dụng Spring Boot, một cấu hình thường gặp:

~~~java
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
@ActiveProfiles("test")
class ImportOrdersJobIntegrationTest {
    // Test code
}
~~~

Giải thích:

- `@SpringBootTest` tạo context tích hợp của ứng dụng Boot.
- `@SpringBatchTest` giúp test truy cập các tiện ích chạy job/step và scope thích hợp.
- `@ActiveProfiles("test")` chọn profile chứa database và thiết lập dành riêng cho test.
- `spring.batch.job.enabled=false` ngăn cơ chế tự khởi chạy `Job` của **Spring Boot** khi application context khởi động, giúp test tự quyết định lúc nào gọi job. Property này không vô hiệu hóa khả năng chạy job thủ công.

Nếu dự án dùng cấu hình Spring Batch không thông qua cơ chế auto-run của Spring Boot, phải hiểu rõ cách job được khởi động trong setup thực tế. Annotation không tự chứng minh database test đã được cô lập.

### Ví dụ: chạy job và dọn metadata giữa các test

Đoạn code sau giả định ứng dụng có bean `importOrdersJob`, bảng nghiệp vụ `processed_order` và một database test riêng. Ví dụ kiểm tra số lượng output; với ứng dụng thật, nên khẳng định cả giá trị từng bản ghi:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.batch.core.BatchStatus;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.test.JobLauncherTestUtils;
import org.springframework.batch.test.JobRepositoryTestUtils;
import org.springframework.batch.test.context.SpringBatchTest;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
@ActiveProfiles("test")
class ImportOrdersJobIntegrationTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    private JobRepositoryTestUtils jobRepositoryTestUtils;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @Autowired
    @Qualifier("importOrdersJob")
    private Job importOrdersJob;

    @BeforeEach
    void prepare() {
        // Chỉ thực hiện trên database dành riêng cho test.
        jobRepositoryTestUtils.removeJobExecutions();
        jdbcTemplate.update("DELETE FROM processed_order");
        jobLauncherTestUtils.setJob(importOrdersJob);
    }

    @Test
    void importsThreeOrders() throws Exception {
        JobExecution execution = jobLauncherTestUtils.launchJob(
            new JobParametersBuilder()
                .addString("scenario", "three-orders")
                .toJobParameters()
        );

        assertThat(execution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
        Integer count = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM processed_order", Integer.class);
        assertThat(count).isEqualTo(3);
    }
}
~~~

Ở đây, `@BeforeEach` được gọi trước **mỗi phương thức test** dù context là cache hit. Nó dọn lịch sử job và dữ liệu nghiệp vụ trên cơ sở dữ liệu chuyên dụng; cấu hình job và các bean trong context vẫn có thể được tái sử dụng. Không áp dụng `removeJobExecutions()` trên repository dùng chung với môi trường thật hoặc với các test đang chạy song song trên cùng database, vì nó có thể xóa lịch sử của execution khác.

Ví dụ chỉ hợp lệ nếu input test đã được chuẩn bị để tạo đúng ba đơn hàng và writer ghi vào `processed_order`. Với dữ liệu test thực, nên đặt CSV cố định dưới `src/test/resources` và cấu hình reader nhận đường dẫn resource đó một cách rõ ràng.

Nếu cùng context có **nhiều bean `Job`**, `JobLauncherTestUtils` cần được thiết lập đúng job mục tiêu; trong ví dụ, `setJob(importOrdersJob)` loại bỏ sự nhập nhằng.

## 6. Tái sử dụng context giữa nhiều lớp kiểm thử

Thay vì để mỗi test class thay đổi properties nhỏ lẻ, có thể thống nhất cấu hình cho cùng nhóm test:

~~~java
@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
@ActiveProfiles("test")
class ReaderIntegrationTest {
    // ...
}

@SpringBatchTest
@SpringBootTest(properties = "spring.batch.job.enabled=false")
@ActiveProfiles("test")
class WriterIntegrationTest {
    // ...
}
~~~

Nếu các nguồn cấu hình, customizer và context loader thực tế giống nhau, hai lớp có thể chia sẻ cache entry. Trong cả hai, vẫn phải chuẩn bị và dọn trạng thái dữ liệu dành riêng cho test.

Một số nhóm test nên dùng context khác nhau vì thực sự cần hạ tầng khác:

- Unit test processor chỉ cần đối tượng Java và mock đơn giản: **không cần** `@SpringBootTest`.
- Reader test chỉ cần tokenizer/mapper: có thể dựng trực tiếp reader, không cần toàn bộ ứng dụng.
- Test tích hợp `Job` và `Step`: dùng context batch hoặc Boot thích hợp.
- Test chạy với một profile, database engine hoặc cách override bean khác: chấp nhận context riêng khi cấu hình khác có ý nghĩa.

Mục tiêu là **tái sử dụng cấu hình giống nhau một cách có chủ đích**, không phải ép tất cả test dùng một context khổng lồ. Một test đơn vị nhỏ thường nhanh hơn nhiều khi không phải khởi tạo Spring.

## 7. Khi nào @DirtiesContext là lựa chọn phù hợp?

`@DirtiesContext` thông báo cho Spring TestContext rằng `ApplicationContext` đang dùng đã bị thay đổi hoặc không còn nên tái sử dụng. Tùy vị trí và chế độ, framework có thể loại bỏ context khỏi cache và đóng nó để test kế tiếp nạp lại context.

Ví dụ:

~~~java
import org.springframework.test.annotation.DirtiesContext;

@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
@SpringBatchTest
@SpringBootTest
class ChangesSingletonConfigurationTest {
    // Test thay đổi trạng thái cấu hình singleton
    // đến mức không thể phục hồi an toàn trong cleanup.
}
~~~

Các chế độ thường dùng:

| Cách đánh dấu | Ý nghĩa |
|---|---|
| `@DirtiesContext(methodMode = AFTER_METHOD)` tại phương thức | Đánh dấu context là bẩn sau phương thức đó. |
| `@DirtiesContext(methodMode = BEFORE_METHOD)` | Đảm bảo context cũ không được tái sử dụng cho phương thức hiện tại. |
| `@DirtiesContext(classMode = AFTER_CLASS)` tại lớp | Đánh dấu context sau khi toàn bộ lớp chạy xong. |
| `@DirtiesContext(classMode = BEFORE_CLASS)` | Yêu cầu context được làm mới trước khi các test trong lớp chạy. |
| `@DirtiesContext(classMode = AFTER_EACH_TEST_METHOD)` | Đánh dấu sau từng phương thức, dẫn tới việc nạp lại thường xuyên hơn. |

Khi test thay đổi cấu hình bean, môi trường trong context hoặc một singleton mà không có cách reset đúng, việc đánh dấu context là bẩn là hợp lý. Tuy nhiên, `@DirtiesContext` **không phải công cụ dọn toàn bộ dữ liệu bên ngoài Spring context**:

- Nếu writer đã commit vào PostgreSQL test, đóng context không xóa các hàng ấy.
- Nếu batch gửi một thông điệp Kafka hay file đã ghi, context bị đóng không hủy tác động đó.
- Nếu một database in-memory tồn tại ngoài vòng đời connection/context do cấu hình riêng, đóng context có thể không xóa trạng thái như mong đợi.

Vì vậy, khi chỉ có dữ liệu bảng `processed_order` hoặc metadata `BATCH_*` còn sót, cách sửa thường là **reset dữ liệu test**, không phải thêm `@DirtiesContext` vào mọi test. Lạm dụng annotation này làm tăng cache miss và thời gian chạy mà vẫn có thể không giải quyết đúng nguồn nhiễm trạng thái.

## 8. Những tình huống khiến context không được tái sử dụng

### 8.1. Khác nhau ở properties hoặc profile

~~~java
@SpringBootTest(properties = "app.import.strict=true")
class StrictImportTest { }

@SpringBootTest(properties = "app.import.strict=false")
class LenientImportTest { }
~~~

Đây là hai ngữ cảnh có hành vi khác nhau. Nếu cần kiểm tra nhiều biến thể logic mà không nhất thiết đổi cách tạo bean, cân nhắc truyền dữ liệu hoặc tham số xử lý trực tiếp; chỉ thay properties của context khi đó thực sự là đối tượng kiểm thử.

### 8.2. Khai báo mock khác nhau giữa các lớp

Một lớp override bean `PaymentClient`, lớp khác override `NotificationClient`; hai tập customizer khác nhau có thể tạo hai cache key. Khác biệt do mock bean làm context không đồng nhất là điều bình thường.

Nếu trong một nhóm test, tất cả đều cần cùng một tập phụ thuộc giả, có thể chia sẻ cấu hình kiểm thử hoặc mock configuration có chủ đích. Nhưng đừng thêm mock không cần thiết chỉ để cố gắng tối ưu cache.

### 8.3. @DynamicPropertySource và tài nguyên động

`@DynamicPropertySource` thường dùng để đưa cổng, URL hoặc credential của Testcontainers vào Spring Environment:

~~~java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
~~~

Lưu ý rằng method `@DynamicPropertySource` đóng vai trò trong context customizer. Nếu nhiều lớp **kế thừa cùng phương thức** nhưng tài nguyên được cung cấp thực tế khác nhau (chẳng hạn container của lớp trước đã dừng rồi lớp sau dùng một container/port mới), một context được cache có thể giữ `DataSource` gắn với tài nguyên cũ. Khi đó, cần thiết kế vòng đời container phù hợp với việc dùng chung context, hoặc đánh dấu context bẩn khi cấu hình động thực sự thay đổi.

Một container dùng chung ổn định trong toàn bộ nhóm integration test có thể giảm thời gian khởi tạo, nhưng phải tách dữ liệu giữa các test. Không nên để cache context ngầm quyết định vòng đời của tài nguyên ngoài JVM.

### 8.4. Chạy test trong nhiều JVM hoặc nhiều process

Context cache là **cache tĩnh trong một JVM**. Nó không được chia sẻ qua:

- Hai tiến trình test riêng.
- Các worker JVM độc lập do build tool fork.
- Hai lần chạy test khác nhau trong IDE hoặc CI.

Vì vậy, cùng một cấu hình có thể nạp context một lần trong JVM A và một lần khác trong JVM B; đó không phải cache miss bất thường. Khi cấu hình build chia test qua nhiều JVM, cần cân bằng mức song song, bộ nhớ, chi phí khởi tạo context và khả năng cô lập database.

### 8.5. Cache quá nhỏ và bị eviction

Spring TestContext cache có giới hạn dung lượng; giá trị mặc định phổ biến là **32 context** và cơ chế loại bỏ mục ít được sử dụng gần đây (**LRU**) khi vượt giới hạn. Nếu bộ test tạo quá nhiều cấu hình khác nhau, những context cũ có thể bị đóng và phải khởi tạo lại khi được dùng tiếp.

Có thể điều chỉnh tối đa bằng thuộc tính JVM:

~~~text
-Dspring.test.context.cache.maxSize=64
~~~

Tăng cache size không phải luôn tốt hơn: nhiều context sống đồng thời cũng chiếm heap, giữ connection pool và các tài nguyên khác. Trước khi tăng giới hạn, nên xem vì sao test sinh ra quá nhiều cấu hình khác nhau và có thể gom các cấu hình tương đương hay không.

## 9. Cách quan sát cache hit/miss bằng log

Spring TestContext cung cấp thông tin thống kê cache qua logging. Có thể đặt logger sau ở mức `DEBUG` trong cấu hình log test:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Nếu dự án không dùng Spring Boot logging properties, cấu hình level tương đương trong Logback/Log4j hoặc hệ thống logging được chọn. Khi chạy test, tìm các số liệu như:

- `size`: số context đang nằm trong cache.
- `maxSize`: giới hạn mục cache.
- `hitCount`: số lần tra cứu tìm thấy context phù hợp.
- `missCount`: số lần tra cứu chưa có context phù hợp.
- `parentContextCount`: số context cha khi sử dụng context hierarchy.

Một cache miss ở lần đầu nạp cấu hình là bình thường. Điều cần điều tra là số lần miss tăng đều trong một bộ test mà lẽ ra chia sẻ cấu hình, hoặc context liên tục bị loại ra vì `@DirtiesContext` và eviction.

Lưu ý **hitCount không phải số phương thức test thành công**; framework có thể truy cập cache nhiều lần trong vòng đời một bài test, vì vậy không lấy hitCount chia số lượng test để suy ra tỷ lệ chính xác. Hãy dùng thống kê như tín hiệu chẩn đoán kết hợp với việc so sánh context configuration.

### Khi context nạp thất bại

Ở các phiên bản Spring Framework mới, TestContext có cơ chế **context failure threshold** để tránh cố gắng nạp đi nạp lại cùng một context lỗi. Một cấu hình mặc định được sử dụng từ Spring Framework 6.1 là ngưỡng 1 lần thất bại cho một cache key, có thể điều chỉnh bằng:

~~~text
-Dspring.test.context.failure.threshold=2
~~~

Khi thấy lỗi kiểu “`ApplicationContext failure threshold exceeded`”, cần tìm **ngoại lệ nạp context đầu tiên** (ví dụ thiếu property, bean không tạo được, database không kết nối) thay vì chỉ đọc những lỗi bị bỏ qua về sau. Tăng ngưỡng không chữa được cấu hình sai; chỉ hữu ích trong một số tình huống chẩn đoán hoặc tài nguyên lỗi tạm thời.

## 10. Các lỗi cụ thể khi kiểm thử Spring Batch với context cache

### Tình huống A: “JobInstance already complete”

**Biểu hiện:** Test đầu chạy job hoàn tất; test thứ hai dùng cùng tên job và cùng identifying `JobParameters` rồi nhận `JobInstanceAlreadyCompleteException`.

**Nguyên nhân:** `JobRepository` vẫn chứa metadata của một `JobInstance` đã hoàn tất. Cache context có thể khiến các test dễ dùng chung repository, nhưng nguồn thông tin thực tế nằm trong database.

**Hướng xử lý:** Dùng database test độc lập; xóa metadata giữa các test khi mục tiêu là chạy độc lập; hoặc tạo `JobParameters` khác khi test đang kiểm tra một job instance mới. Khi kiểm thử restart, **không xóa metadata giữa hai lần chạy cùng instance**, vì chính metadata đó cần cho hành vi restart.

### Tình huống B: Test writer báo số bản ghi lớn hơn mong đợi

**Biểu hiện:** Chạy một mình có ba hàng; chạy sau lớp test khác có sáu hàng.

**Nguyên nhân có thể:** Bảng nghiệp vụ chưa được reset, writer dùng static collector, hoặc cả hai test dùng cùng khóa dữ liệu.

**Hướng xử lý:** Reset bảng dành riêng cho test hoặc dùng schema/database cách ly; không xóa bừa dữ liệu môi trường chung. Nếu writer giữ state trong singleton, thay đổi thiết kế hoặc reset có chủ đích trước mỗi ca.

### Tình huống C: Đóng context làm bộ test chậm

**Biểu hiện:** Nhiều log khởi tạo database/bean, thời gian chạy tăng dần theo số lớp.

**Nguyên nhân có thể:** Gắn `@DirtiesContext` ở lớp cơ sở, mỗi lớp thay một inline property, khai báo mock khác nhau hoặc cache bị eviction.

**Hướng xử lý:** Bật logger cache ở DEBUG, đọc số liệu hit/miss, so sánh annotation giữa các lớp, chỉ giữ `@DirtiesContext` tại nơi thực sự làm context không thể dùng lại.

### Tình huống D: Test với Testcontainers chạy được riêng lẻ nhưng lỗi trong suite

**Biểu hiện:** `DataSource` kết nối tới port/container đã ngừng khi lớp trước kết thúc.

**Nguyên nhân có thể:** Vòng đời container ngắn hơn context đã cache; cấu hình động từ `@DynamicPropertySource` được tái sử dụng với tài nguyên đã đổi.

**Hướng xử lý:** Thiết kế container sống đủ lâu nếu muốn dùng chung context, hoặc không dùng chung context khi endpoint thay đổi. Đồng thời cô lập dữ liệu do các test tạo ra trên cùng container.

### Tình huống E: Test step-scoped bean không có StepExecution

**Biểu hiện:** Reader có `@StepScope` truy cập job parameters hoặc execution context nhưng test trực tiếp gọi bean khi chưa có step context.

**Nguyên nhân:** Bean phụ thuộc scope runtime, không phải do context cache mất dữ liệu.

**Hướng xử lý:** Dùng hỗ trợ scope của `@SpringBatchTest`, các test execution listener liên quan hoặc `StepScopeTestUtils` để thiết lập `StepExecution` phù hợp. Mỗi test phải có scope và parameters mong đợi; tái sử dụng `ApplicationContext` không có nghĩa tái sử dụng `StepExecution` của test trước.

## 11. Test song song: cache vẫn dùng được, dữ liệu phải được cô lập

Khi chạy song song, hai test có thể cùng dùng một `ApplicationContext` được cache. Điều đó **không làm cho ứng dụng hoặc test fixture tự nhiên trở nên thread-safe**:

- Nếu hai job cùng viết vào một bảng bằng những ID giống nhau, chúng có thể tranh chấp hoặc gây kết quả đan xen.
- Nếu cả hai test đều gọi `JobRepositoryTestUtils.removeJobExecutions()` trên cùng database, một test có thể xóa metadata của job do test kia đang chạy.
- Nếu một singleton mutable giữ bộ đếm hoặc danh sách tạm, các test có thể can thiệp trạng thái của nhau.
- Nếu mỗi test thay đổi property hệ thống (system property) toàn cục, thay đổi có thể ảnh hưởng đến test đang chạy ở thread khác.

Các chiến lược hợp lý gồm: dùng schema/database tách biệt, đặt khóa dữ liệu riêng theo ca test, chia nhóm test cần tuần tự, hoặc thiết kế lại bean tránh mutable shared state. Chọn chiến lược theo yêu cầu thực tế; tắt cache chỉ để tránh vấn đề đồng thời thường không đủ vì database ngoài context vẫn là tài nguyên chung.

Đặc biệt với `JobRepositoryTestUtils.removeJobExecutions()`, thao tác này phù hợp nhất khi mỗi bộ test sử dụng repository **chuyên dụng và không có job song song**. Nếu chạy nhiều job trên cùng repository, hãy thiết kế cách xóa metadata có phạm vi và vòng đời phù hợp, hoặc cấp repository riêng cho mỗi test.

## 12. Hướng tiếp cận để bộ test vừa nhanh vừa đáng tin cậy

Một cách tổ chức thực tế:

1. **Chia theo mức độ phụ thuộc Spring.** Processor thuần Java test không cần context; reader mapping có thể test trực tiếp; job integration mới dùng `@SpringBatchTest`/`@SpringBootTest`.
2. **Giữ cấu hình integration test ổn định.** Dùng cùng profile `test`, cùng nguồn configuration và properties khi các bài test cần môi trường giống nhau.
3. **Đặt fixture và expected output tường minh.** Dữ liệu nhỏ với ID cố định làm kết quả dễ so sánh sau khi job chạy.
4. **Tách vòng đời context khỏi vòng đời dữ liệu.** Để Spring cache context; dọn metadata job, bảng nghiệp vụ và tài nguyên test theo nhu cầu của từng ca.
5. **Không thay `JobParameters` một cách ngẫu nhiên để che lỗi.** Chọn identifying parameters rõ nghĩa; dùng giá trị khác cho job instance mới, dùng lại đúng instance khi kiểm thử restart.
6. **Chỉ dùng `@DirtiesContext` khi context thực sự không còn an toàn.** Dọn dữ liệu riêng không đòi hỏi làm bẩn context.
7. **Đo vấn đề trước khi tối ưu.** Xem log cache, số lần context được nạp, bộ nhớ, database connections và cấu hình fork/parallel của build tool.

Ví dụ nhóm test phù hợp:

| Nhóm test | Có cần Spring context? | Cần dọn gì? | Cache mong đợi |
|---|---|---|---|
| Processor thuần Java | Không | Đối tượng test cục bộ. | Không áp dụng. |
| Flat file parser độc lập | Có thể không | Đóng reader, reset execution context test. | Không bắt buộc. |
| Batch job integration trên DB test | Có | Bảng nghiệp vụ, `BATCH_*`, resource đầu vào/đầu ra. | Dùng lại khi cấu hình tương đương. |
| Step-scoped reader integration | Có | `StepExecution` và state của test. | Context có thể dùng lại, step scope phải đúng từng test. |
| Thay đổi cấu hình singleton không phục hồi | Có | Tài nguyên ngoài context nếu có. | Đánh dấu dirty theo phạm vi cần thiết. |
| Test batch với nhiều container khác endpoint | Có | Vòng đời container và dữ liệu. | Cache chỉ an toàn khi endpoint/cấu hình tương ứng. |

## 13. Câu hỏi thường gặp

**Có nên gắn `@DirtiesContext` vào mọi lớp test Spring Batch không?**

Không. Làm vậy khiến các lớp liên tục khởi tạo lại context, trong khi các bản ghi đã commit trong database vẫn có thể tồn tại. Hãy dọn dữ liệu đúng nơi lưu và dùng `@DirtiesContext` khi context bị thay đổi đến mức không còn dùng lại an toàn.

**Hai test cùng `@SpringBootTest` có chắc dùng chung context không?**

Không chắc. Key còn phụ thuộc profile, properties, configuration classes, initializers, context customizers (gồm khai báo mock/override) và các thành phần khác. Ngoài ra, cache chỉ chia sẻ trong cùng JVM.

**Cache có làm JobRepository ghi thiếu hoặc trùng metadata không?**

Bản thân context cache không quyết định nghiệp vụ lưu metadata. `JobRepository` ghi nhận job instance/execution theo cơ chế Spring Batch và cấu hình persistence. Những lỗi trùng lần chạy thường liên quan `JobParameters`, dữ liệu repository còn tồn tại hoặc chiến lược test không cô lập.

**Nếu làm mới context thì database test có rỗng không?**

Không có bảo đảm chung. Điều đó phụ thuộc cơ chế khởi tạo schema, loại database, vòng đời connection, container và cách cấp resource. Với PostgreSQL hay một database nằm ngoài context, dữ liệu vẫn tồn tại cho đến khi được dọn hoặc thay bằng database khác.

**Bật cache có làm test phụ thuộc thứ tự không?**

Việc tái sử dụng context có thể **làm lộ** trạng thái mutable hoặc dữ liệu không được dọn giữa các test. Giải pháp là kiểm soát trạng thái đầu vào/đầu ra và isolation, đồng thời giữ các singleton an toàn cho việc tái sử dụng.

**Muốn biết vì sao test chậm thì nên bắt đầu ở đâu?**

Bật `DEBUG` cho `org.springframework.test.context.cache`, quan sát miss/hit và các lần context bị đóng. Sau đó so sánh cấu hình các lớp, số lần fork JVM và thời gian khởi tạo tài nguyên như database hoặc container; tránh tối ưu dựa vào cảm giác.

## Kết luận

Trong hạ tầng kiểm thử Spring Batch, **context cache** là cơ chế của Spring TestContext giúp tái sử dụng `ApplicationContext` khi cấu hình kiểm thử tương đương. Nó mang lại tốc độ, nhưng đòi hỏi phân biệt rõ **cấu hình Spring** với **trạng thái thực thi batch**.

Hãy để context được cache khi phù hợp, sử dụng `@SpringBatchTest` để điều khiển job/step, chủ động dọn metadata `JobRepository` và dữ liệu writer, quản lý vòng đời container/fixture, và chỉ dùng `@DirtiesContext` khi context không còn an toàn để tái sử dụng. Khi những ranh giới này được thiết kế rõ ràng, bộ integration test vừa nhanh, vừa ổn định khi chạy độc lập, chạy toàn bộ suite hoặc chạy trong CI.
