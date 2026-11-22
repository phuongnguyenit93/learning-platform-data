# @ConditionalOnSingleCandidate khi một type có nhiều bean

Trong Spring Boot, một ứng dụng có thể đăng ký nhiều Bean cùng triển khai một interface. Điều này bình thường: ứng dụng có thể có nhiều cách gửi thông báo, nhiều loại cache, nhiều implementation lưu trữ hoặc nhiều datasource. Vấn đề xuất hiện khi một cấu hình tự động cần **một Bean duy nhất** của một kiểu để tạo thành phần tiếp theo.

Ví dụ, một auto-configuration muốn tạo `ReportPublisher` và factory method của nó cần một `ReportStore`. Nếu container chỉ có một Bean `ReportStore`, Spring có thể inject trực tiếp. Nếu có hai Bean cùng kiểu, việc chọn một Bean có thể trở nên mơ hồ. Một Bean được đánh dấu `@Primary` có thể giải quyết lựa chọn mặc định.

`@ConditionalOnSingleCandidate` là điều kiện của Spring Boot dành cho tình huống này. Nó chỉ khớp khi BeanFactory có **một ứng viên duy nhất** có thể được autowire theo kiểu yêu cầu, hoặc khi có nhiều ứng viên nhưng xác định được một **primary candidate**. Nếu có nhiều Bean cùng kiểu mà không có ứng viên primary duy nhất, điều kiện không khớp.

Điều kiện này đặc biệt hữu ích trong auto-configuration: chỉ tạo Bean phụ thuộc vào một collaborator khi container có thể cung cấp collaborator đó một cách không mơ hồ.

## 1. Vấn đề: một type có nhiều Bean

Giả sử ứng dụng có interface:

```java
public interface ReportStore {
    void save(String report);
}
```

Và hai implementation:

```java
@Component("databaseReportStore")
public class DatabaseReportStore implements ReportStore {
    @Override
    public void save(String report) {
        // Lưu báo cáo vào database.
    }
}
```

```java
@Component("fileReportStore")
public class FileReportStore implements ReportStore {
    @Override
    public void save(String report) {
        // Lưu báo cáo vào file.
    }
}
```

Container lúc này có hai Bean cùng có thể gán cho kiểu `ReportStore`:

| Bean name | Implementation | Kiểu có thể inject |
|---|---|---|
| `databaseReportStore` | `DatabaseReportStore` | `ReportStore` |
| `fileReportStore` | `FileReportStore` | `ReportStore` |

Một service yêu cầu một `ReportStore`:

```java
@Service
public class ReportPublisher {
    private final ReportStore store;

    public ReportPublisher(ReportStore store) {
        this.store = store;
    }
}
```

Nếu không có metadata giúp Spring lựa chọn một ứng viên, constructor injection trở nên mơ hồ. Context có thể thất bại với lỗi như `NoUniqueBeanDefinitionException` hoặc một lỗi tạo Bean bao ngoài có nguyên nhân gốc là nhiều ứng viên phù hợp.

Điều này không có nghĩa nhiều Bean cùng interface là sai. Có nhiều implementation là một cách thiết kế hợp lệ; chỉ có điểm **cần đúng một implementation mặc định** mới phải có quy tắc lựa chọn.

## 2. @ConditionalOnSingleCandidate là gì?

`@ConditionalOnSingleCandidate` thuộc package:

```java
org.springframework.boot.autoconfigure.condition
```

Nó là một conditional annotation của Spring Boot. Spring đánh giá điều kiện khi xử lý cấu hình; cấu hình hoặc Bean được đánh dấu chỉ được đăng ký khi có một ứng viên phù hợp duy nhất theo kiểu yêu cầu.

Cách dùng cơ bản:

```java
@Bean
@ConditionalOnSingleCandidate(ReportStore.class)
ReportPublisher reportPublisher(ReportStore store) {
    return new ReportPublisher(store);
}
```

Đọc đoạn này như sau:

1. Spring Boot xem trong BeanFactory có Bean nào phù hợp với kiểu `ReportStore`.
2. Nếu chỉ có một ứng viên, điều kiện khớp.
3. Nếu có nhiều ứng viên nhưng có một primary candidate, điều kiện cũng có thể khớp.
4. Nếu có nhiều ứng viên mà không xác định được một primary candidate duy nhất, điều kiện không khớp.
5. Chỉ khi điều kiện khớp, Bean `reportPublisher` mới được đăng ký từ method trên.

Annotation này giúp auto-configuration **rút lui an toàn** khi không thể chọn một dependency duy nhất. Khi điều kiện không khớp, Spring không tạo `ReportPublisher` theo method đó; các Bean khác trong ứng dụng vẫn có thể được tạo bình thường.

### Cú pháp

Ví dụ phổ biến:

```java
@ConditionalOnSingleCandidate(ReportStore.class)
```

Annotation cũng hỗ trợ chỉ định kiểu qua tên class:

```java
@ConditionalOnSingleCandidate(type = "com.example.reporting.ReportStore")
```

Khai báo theo `value` thường dễ refactor và kiểm tra kiểu ở compile time hơn. Dùng `type` khi cần tham chiếu kiểu dưới dạng tên chuỗi, chẳng hạn trong một cấu hình tùy chọn không muốn có compile-time dependency trực tiếp tới class đó.

Không cần tự viết `@Conditional` hoặc truy cập `ApplicationContext` để đếm Bean trong những trường hợp thông thường; annotation này đã diễn đạt sẵn ý nghĩa “một candidate theo type”.

## 3. Quy tắc quyết định: một ứng viên, nhiều ứng viên và @Primary

Hãy xét bốn tình huống:

| Số Bean phù hợp với type | Primary candidate | `@ConditionalOnSingleCandidate` |
|---:|---|---|
| 0 | Không có | Không khớp |
| 1 | Không cần | Khớp |
| 2 hoặc nhiều | Không có | Không khớp |
| 2 hoặc nhiều | Có một primary candidate duy nhất | Khớp |

Điểm cốt lõi là điều kiện không yêu cầu toàn container chỉ có một Bean. Nó yêu cầu container có thể xác định **một ứng viên duy nhất để autowire theo kiểu đó**.

### Trường hợp chỉ có một Bean

```java
@Configuration(proxyBeanMethods = false)
class ReportStoreConfiguration {
    @Bean
    ReportStore reportStore() {
        return new DatabaseReportStore();
    }
}
```

Nếu không có Bean `ReportStore` nào khác trong phạm vi tìm kiếm của điều kiện, `@ConditionalOnSingleCandidate(ReportStore.class)` khớp. Không cần đánh dấu `@Primary` vì đã chỉ có một ứng viên.

### Trường hợp có nhiều Bean và không có primary

```java
@Configuration(proxyBeanMethods = false)
class ReportStoreConfiguration {
    @Bean
    ReportStore databaseReportStore() {
        return new DatabaseReportStore();
    }

    @Bean
    ReportStore fileReportStore() {
        return new FileReportStore();
    }
}
```

Có hai ứng viên. Không có Bean nào được đánh dấu primary, vì vậy điều kiện không khớp. Một auto-configured Bean cần duy nhất `ReportStore` sẽ không được đăng ký từ method có điều kiện đó.

### Trường hợp có một primary

```java
@Configuration(proxyBeanMethods = false)
class ReportStoreConfiguration {
    @Bean
    @Primary
    ReportStore databaseReportStore() {
        return new DatabaseReportStore();
    }

    @Bean
    ReportStore fileReportStore() {
        return new FileReportStore();
    }
}
```

Giờ đây `databaseReportStore` là ứng viên primary. Điều kiện có thể khớp và khi factory method nhận tham số `ReportStore`, Spring có thể inject primary Bean đó.

`@Primary` không xóa `fileReportStore` khỏi container. Bean thứ hai vẫn có thể được lấy theo tên hoặc được inject khi một điểm injection chỉ định qualifier phù hợp.

### Có nhiều primary candidate thì sao?

`@Primary` được dùng để xác định một ứng viên ưu tiên. Nếu có nhiều Bean cùng kiểu và metadata primary không tạo ra một lựa chọn duy nhất, không nên kỳ vọng `@ConditionalOnSingleCandidate` sẽ chọn tùy ý. Điều kiện được thiết kế để tránh tình huống mơ hồ, không phải để dự đoán Bean nào được tạo trước.

## 4. Ví dụ auto-configuration hoàn chỉnh

Ta xây một auto-configuration cung cấp `ReportPublisher` nếu ứng dụng có một `ReportStore` có thể lựa chọn duy nhất.

### Contract và Bean do ứng dụng cung cấp

```java
public interface ReportStore {
    void save(String report);
}
```

```java
public class ReportPublisher {
    private final ReportStore store;

    public ReportPublisher(ReportStore store) {
        this.store = store;
    }

    public void publish(String report) {
        store.save(report);
    }
}
```

`ReportPublisher` không tự tạo `ReportStore`. Nó chỉ yêu cầu dependency qua constructor.

### Auto-configuration

```java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnSingleCandidate;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class ReportPublisherAutoConfiguration {

    @Bean
    @ConditionalOnSingleCandidate(ReportStore.class)
    ReportPublisher reportPublisher(ReportStore store) {
        return new ReportPublisher(store);
    }
}
```

Ở đây:

- `@AutoConfiguration` đánh dấu cấu hình tự động của Spring Boot.
- `@Bean` khai báo factory method tạo `ReportPublisher`.
- `@ConditionalOnSingleCandidate` kiểm tra có thể phân giải duy nhất `ReportStore` hay không.
- Tham số method `ReportStore store` yêu cầu container inject ứng viên đã được chọn.

Trong một thư viện auto-configuration được đóng gói riêng, class cấu hình cần được đăng ký theo cơ chế import auto-configuration của Spring Boot, thường thông qua file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

với tên class cấu hình đầy đủ, ví dụ:

```text
com.example.reporting.ReportPublisherAutoConfiguration
```

Đây là bước dành cho tác giả thư viện auto-configuration. Ứng dụng thông thường không cần tự tạo file này chỉ để dùng một Bean `@Configuration` do mình khai báo.

### Hành vi trong ba cấu hình ứng dụng

**Cấu hình A — chỉ có một ReportStore:**

```java
@Configuration(proxyBeanMethods = false)
class ApplicationStoreConfiguration {
    @Bean
    ReportStore reportStore() {
        return new DatabaseReportStore();
    }
}
```

Kết quả: condition khớp; `ReportPublisher` được đăng ký và nhận `reportStore`.

**Cấu hình B — có hai ReportStore nhưng không có primary:**

```java
@Configuration(proxyBeanMethods = false)
class ApplicationStoreConfiguration {
    @Bean
    ReportStore databaseReportStore() {
        return new DatabaseReportStore();
    }

    @Bean
    ReportStore fileReportStore() {
        return new FileReportStore();
    }
}
```

Kết quả: condition không khớp; method `reportPublisher(...)` không cung cấp Bean. Auto-configuration tránh tạo một Bean mà dependency của nó không có lựa chọn duy nhất.

**Cấu hình C — hai ReportStore, một primary:**

```java
@Configuration(proxyBeanMethods = false)
class ApplicationStoreConfiguration {
    @Bean
    @Primary
    ReportStore databaseReportStore() {
        return new DatabaseReportStore();
    }

    @Bean
    ReportStore fileReportStore() {
        return new FileReportStore();
    }
}
```

Kết quả: condition khớp; `ReportPublisher` được đăng ký và tham số `ReportStore` nhận `databaseReportStore`.

## 5. @ConditionalOnSingleCandidate khác @ConditionalOnBean thế nào?

Hai annotation đều là điều kiện dựa trên Bean hiện có, nhưng trả lời câu hỏi khác nhau.

| Annotation | Câu hỏi | Nhiều Bean cùng type |
|---|---|---|
| `@ConditionalOnBean(ReportStore.class)` | Có ít nhất một Bean phù hợp không? | Thường vẫn khớp |
| `@ConditionalOnSingleCandidate(ReportStore.class)` | Có một ứng viên duy nhất có thể autowire không? | Chỉ khớp nếu có primary candidate duy nhất |
| `@ConditionalOnMissingBean(ReportStore.class)` | Chưa có Bean phù hợp để cấu hình mặc định không? | Không khớp nếu đã có Bean phù hợp |

### Khi nào dùng @ConditionalOnBean?

Nếu Bean chỉ cần biết rằng một integration đã được đăng ký, bất kể có một hay nhiều implementation, `@ConditionalOnBean` có thể phù hợp.

Ví dụ, một registry có thể hoạt động khi có ít nhất một `ReportStore` và nhận tất cả implementation qua collection:

```java
@Bean
@ConditionalOnBean(ReportStore.class)
ReportStoreRegistry reportStoreRegistry(List<ReportStore> stores) {
    return new ReportStoreRegistry(stores);
}
```

Vì registry cần một danh sách, nhiều ứng viên không phải vấn đề. `@ConditionalOnSingleCandidate` ở đây sẽ quá chặt và có thể ngăn Bean được tạo dù danh sách nhiều implementation hoàn toàn hợp lệ.

### Khi nào dùng @ConditionalOnSingleCandidate?

Nếu factory method chỉ nhận một `ReportStore` và cần một lựa chọn mặc định:

```java
@Bean
@ConditionalOnSingleCandidate(ReportStore.class)
ReportPublisher reportPublisher(ReportStore store) {
    return new ReportPublisher(store);
}
```

Đây chính là trường hợp annotation này được thiết kế để giải quyết.

### Khi nào dùng @ConditionalOnMissingBean?

Auto-configuration thường cung cấp một Bean mặc định nếu ứng dụng chưa tự khai báo Bean phù hợp:

```java
@Bean
@ConditionalOnMissingBean(ReportStore.class)
ReportStore defaultReportStore() {
    return new InMemoryReportStore();
}
```

Nếu ứng dụng đã đăng ký một hoặc nhiều `ReportStore`, Bean mặc định có thể không được tạo. Điều kiện này hỗ trợ triết lý “back off” của Spring Boot: cấu hình mặc định nhường chỗ cho cấu hình do ứng dụng cung cấp.

Không thay thế lẫn nhau các annotation chỉ vì chúng cùng kiểm tra BeanFactory. Hãy chọn theo đúng hợp đồng mà Bean đang cần: **có ít nhất một**, **chưa có**, hay **có một ứng viên duy nhất**.

## 6. @Primary và @Qualifier có vai trò khác nhau

`@Primary` và `@Qualifier` đều tham gia giải quyết dependency injection, nhưng không cùng mục đích.

### @Primary: lựa chọn mặc định theo type

```java
@Primary
@Component
public class DatabaseReportStore implements ReportStore {
    // ...
}
```

Khi có nhiều Bean `ReportStore`, một Bean primary có thể được chọn cho điểm injection chỉ yêu cầu kiểu `ReportStore` mà không chỉ rõ qualifier.

Đây là metadata phù hợp với ý nghĩa của `@ConditionalOnSingleCandidate`: khi nhiều ứng viên tồn tại, một primary candidate cho phép condition nhận diện một lựa chọn duy nhất.

### @Qualifier: chọn ở điểm injection cụ thể

```java
@Service
public class ArchiveService {
    private final ReportStore store;

    public ArchiveService(
            @Qualifier("fileReportStore") ReportStore store) {
        this.store = store;
    }
}
```

Qualifier cho biết consumer này cần Bean cụ thể. Nó có thể giúp một constructor phân giải thành công dù container có nhiều implementation.

Tuy nhiên, `@ConditionalOnSingleCandidate(ReportStore.class)` không nhận một qualifier tại điểm injection như tham số của nó. Đừng giả định rằng việc một service khác sử dụng `@Qualifier` sẽ làm condition theo type tự động xem các Bean còn lại như không tồn tại. Condition này được dùng để kiểm tra khả năng chọn một candidate theo kiểu và primary candidate; annotation này không phải một annotation chọn Bean theo qualifier tùy ý.

Nếu auto-configuration cần một loại store cụ thể theo tên/qualifier, hãy thiết kế điều kiện và factory method phù hợp với hợp đồng đó; không dùng `@ConditionalOnSingleCandidate` như một annotation chọn qualifier.

## 7. @ConditionalOnSingleCandidate không phải là “đếm class”

Condition đánh giá Bean phù hợp trong BeanFactory, không đơn giản đếm số file Java hoặc số class implement interface.

Ví dụ:

- Một class implementation có mặt trên classpath nhưng không được đăng ký thành Bean thì không tự tạo thêm candidate.
- Một Bean có thể được tạo từ factory method và có kiểu trả về interface.
- Một Bean có thể đến từ auto-configuration khác.
- Một Bean có thể nằm trong parent context, tùy chiến lược tìm kiếm được sử dụng.
- Các Bean không phải autowire candidate hoặc bị bỏ qua theo metadata/điều kiện tương ứng không nhất thiết được xem giống một ứng viên thông thường.

Vì thế, khi condition không khớp, câu hỏi nên là “BeanFactory nhìn thấy những candidate nào ở thời điểm đánh giá?” thay vì “Trong source code có bao nhiêu class implement interface?”.

### Kiểu trả về của @Bean có ý nghĩa

```java
@Bean
ReportStore reportStore() {
    return new DatabaseReportStore();
}
```

Khai báo kiểu trả về `ReportStore` giúp container có thông tin type rõ ràng để xử lý điều kiện và dependency resolution. Nếu factory method trả về `Object` dù thực tế tạo `DatabaseReportStore`, Spring có thể không suy luận được kiểu cụ thể ở một số thời điểm xử lý metadata.

Với auto-configuration, hãy khai báo kiểu trả về Bean cụ thể/abstraction phù hợp thay vì dùng `Object` một cách không cần thiết. Điều này giúp điều kiện theo kiểu có đủ thông tin để đánh giá.

### FactoryBean và kiểu chưa xác định sớm

Nếu Bean được cung cấp bởi `FactoryBean`, việc xác định kiểu sản phẩm có thể phụ thuộc vào metadata mà factory cung cấp. Spring có thể cần hỏi kiểu sản phẩm của factory; nếu kiểu không thể xác định sớm, một số điều kiện theo type có thể không có đủ thông tin tại thời điểm đánh giá.

Khi viết auto-configuration, hãy công bố type metadata rõ ràng và tránh buộc condition phải khởi tạo infrastructure chỉ để đoán kiểu. Nếu đang dùng thư viện có `FactoryBean`, hãy kiểm tra cách nó khai báo product type và condition report khi kết quả không như dự kiến.

## 8. Thời điểm đánh giá condition và thứ tự auto-configuration

Điều kiện của Spring Boot được đánh giá trong quá trình xử lý cấu hình, dựa trên những BeanDefinition đã được đăng ký và có thể nhìn thấy tại thời điểm đó. Vì vậy **thứ tự xử lý cấu hình có thể ảnh hưởng kết quả**.

Ví dụ, auto-configuration A muốn kiểm tra một Bean do auto-configuration B cung cấp. Nếu A được đánh giá trước khi B đóng góp BeanDefinition, A có thể không nhìn thấy candidate mà bạn kỳ vọng.

Khi auto-configuration phụ thuộc vào Bean/configuration từ một auto-configuration khác, hãy khai báo thứ tự rõ ràng:

```java
@AutoConfiguration(after = ReportStoreAutoConfiguration.class)
public class ReportPublisherAutoConfiguration {
    // ...
}
```

Hoặc sử dụng annotation ordering tương ứng như `@AutoConfigureAfter` trong các cấu hình phù hợp.

Không dùng thứ tự để che một dependency thiếu trong thiết kế. Ordering chỉ giải quyết quan hệ giữa các nguồn cấu hình; nó không làm một Bean chưa được khai báo trở thành candidate.

### User-defined Bean và auto-configuration

Spring Boot thường xử lý auto-configuration sau cấu hình ứng dụng để Bean do người dùng khai báo có thể được nhìn thấy khi các điều kiện được đánh giá. Đây là nền tảng cho cơ chế mặc định có thể thay thế.

Tuy nhiên, nếu bạn tự xây nhiều module cấu hình và import theo thứ tự tùy chỉnh, vẫn cần hiểu thứ tự đăng ký definition. Khi condition bất ngờ không khớp, hãy đọc condition evaluation report thay vì đoán thứ tự.

## 9. Ví dụ kiểm tra ba trạng thái bằng ApplicationContextRunner

Spring Boot cung cấp `ApplicationContextRunner` để kiểm tra auto-configuration trong một context nhỏ, cô lập. Nó đặc biệt phù hợp để xác nhận condition mà không cần khởi động toàn bộ ứng dụng.

Giả sử auto-configuration:

```java
@AutoConfiguration
public class ReportPublisherAutoConfiguration {

    @Bean
    @ConditionalOnSingleCandidate(ReportStore.class)
    ReportPublisher reportPublisher(ReportStore store) {
        return new ReportPublisher(store);
    }
}
```

Test có thể cấu hình các Bean đầu vào:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

import static org.assertj.core.api.Assertions.assertThat;

class ReportPublisherAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            ReportPublisherAutoConfiguration.class));

    @Test
    void matchesWhenThereIsOneCandidate() {
        runner.withUserConfiguration(OneStoreConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportPublisher.class);
                });
    }

    @Test
    void doesNotMatchWhenThereAreMultipleCandidatesWithoutPrimary() {
        runner.withUserConfiguration(TwoStoresConfiguration.class)
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ReportPublisher.class);
                });
    }

    @Test
    void matchesWhenOneOfSeveralCandidatesIsPrimary() {
        runner.withUserConfiguration(PrimaryStoreConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportPublisher.class);
                    assertThat(context.getBean(ReportPublisher.class))
                            .isNotNull();
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class OneStoreConfiguration {
        @Bean
        ReportStore reportStore() {
            return new DatabaseReportStore();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TwoStoresConfiguration {
        @Bean
        ReportStore databaseReportStore() {
            return new DatabaseReportStore();
        }

        @Bean
        ReportStore fileReportStore() {
            return new FileReportStore();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class PrimaryStoreConfiguration {
        @Bean
        @Primary
        ReportStore databaseReportStore() {
            return new DatabaseReportStore();
        }

        @Bean
        ReportStore fileReportStore() {
            return new FileReportStore();
        }
    }
}
```

Ví dụ minh họa cần có các class `ReportStore`, `ReportPublisher`, `DatabaseReportStore` và `FileReportStore` như đã định nghĩa trước đó. Test dùng AssertJ/JUnit thông qua dependency test của Spring Boot. Nó kiểm tra ba nhánh quan trọng:

1. Một candidate: condition khớp.
2. Nhiều candidate không primary: condition không khớp.
3. Nhiều candidate với một primary: condition khớp.

`ApplicationContextRunner` giúp xác minh hành vi của auto-configuration theo từng tập Bean đầu vào. Đây là cách tốt để tác giả starter đảm bảo cấu hình mặc định không phá ứng dụng có nhiều implementation.

## 10. Quan sát lý do condition khớp hoặc không khớp

Khi ứng dụng khởi động với debug mode, Spring Boot có thể in **Condition Evaluation Report**:

```bash
java -jar app.jar --debug
```

Hoặc bật property:

```properties
debug=true
```

Trong báo cáo, tìm tên auto-configuration hoặc method liên quan. Bạn có thể thấy điều kiện đã khớp hay không khớp và thông tin mô tả lý do.

Nếu ứng dụng có Actuator và endpoint `conditions` được bật, endpoint này cũng có thể giúp quan sát các condition. Việc expose endpoint cần được giới hạn theo cấu hình bảo mật/vận hành phù hợp; không công khai thông tin chẩn đoán nội bộ một cách tùy tiện.

Một số câu hỏi khi đọc report:

- Bean type condition đang kiểm tra là kiểu nào?
- BeanDefinition tương ứng đã được đăng ký trước khi condition đánh giá chưa?
- Có bao nhiêu candidate phù hợp?
- Candidate nào được đánh dấu primary?
- Có một auto-configuration khác chưa chạy hoặc bị exclude không?
- Kiểu trả về của factory method có đủ rõ để Spring suy luận không?

Đừng chỉ nhìn dòng “did not match”; hãy đọc phần message/condition detail để biết lý do cụ thể.

## 11. Những nhầm lẫn thường gặp

**“Có nhiều Bean cùng kiểu thì `@ConditionalOnSingleCandidate` luôn false.”** Không đúng. Nếu có một primary candidate duy nhất, điều kiện vẫn có thể khớp.

**“Có `@Primary` thì các Bean còn lại bị loại.”** Không. `@Primary` chỉ ảnh hưởng lựa chọn mặc định cho điểm injection phù hợp; các Bean khác vẫn được đăng ký và có thể được chọn theo qualifier/tên hoặc inject thành collection.

**“`@ConditionalOnSingleCandidate` giống `@ConditionalOnBean`.”** Không. `@ConditionalOnBean` kiểm tra sự hiện diện của Bean phù hợp; nó không yêu cầu một candidate duy nhất để inject một tham số đơn.

**“`@Qualifier` ở một service làm condition theo type chỉ thấy một Bean.”** Không nên suy luận như vậy. Qualifier là metadata dùng tại điểm injection cụ thể. `@ConditionalOnSingleCandidate` kiểm tra khả năng chọn một candidate theo kiểu và primary candidate; annotation này không nhận qualifier tùy ý như một tham số chọn Bean.

**“Condition không khớp nghĩa là ứng dụng lỗi.”** Không. Khi điều kiện không khớp, Bean được bảo vệ bởi điều kiện đơn giản là không được đăng ký. Đây thường là hành vi mong muốn của auto-configuration; ứng dụng có thể tự cung cấp một cấu hình khác.

**“Condition kiểm tra class implement interface trên classpath.”** Không. Nó kiểm tra các Bean candidate mà BeanFactory có thể nhận diện tại thời điểm đánh giá.

**“Đánh dấu `@Primary` là cách sửa mọi trường hợp mơ hồ.”** Không phải lúc nào cũng đúng. Nếu mỗi consumer cần implementation khác nhau, qualifier hoặc collection injection thể hiện ý định tốt hơn. `@Primary` chỉ phù hợp khi có một mặc định toàn cục hợp lý.

## 12. Khi nào nên dùng @ConditionalOnSingleCandidate?

Nên cân nhắc annotation này khi viết auto-configuration hoặc cấu hình có điều kiện mà Bean tạo ra cần một dependency theo kiểu đơn:

- Tạo một integration adapter dựa trên một `DataSource` được chọn.
- Tạo một client wrapper dựa trên một `ObjectMapper` mặc định có thể autowire.
- Tạo một publisher dựa trên một store/service interface.
- Kích hoạt một tính năng chỉ khi ứng dụng có một implementation mặc định không mơ hồ.

Không nên dùng khi:

- Bean cần tất cả implementation; hãy inject `List<T>` hoặc `Map<String, T>`.
- Chỉ cần biết ít nhất một Bean tồn tại; `@ConditionalOnBean` có thể đúng hơn.
- Muốn cung cấp Bean mặc định khi người dùng chưa cấu hình; xem `@ConditionalOnMissingBean`.
- Consumer luôn cần một implementation cụ thể theo tên; hãy xem `@Qualifier` và điều kiện phù hợp với hợp đồng đó.
- Điều kiện được đặt ở một thời điểm cấu hình mà Bean cần kiểm tra chưa được đăng ký; cần xem lại ordering.

## 13. Quy trình suy luận khi condition không như mong đợi

Khi `@ConditionalOnSingleCandidate` không khớp, hãy phân tích theo thứ tự:

1. **Xác nhận type:** annotation đang kiểm tra đúng interface/class mà factory method cần chưa?
2. **Xác nhận Bean registration:** implementation đã được đăng ký thành BeanDefinition chưa, hay chỉ là class có mặt trên classpath?
3. **Đếm candidate:** có 0, 1 hay nhiều Bean phù hợp trong phạm vi tìm kiếm?
4. **Kiểm tra primary:** nếu nhiều Bean, có đúng một primary candidate không?
5. **Kiểm tra thời điểm:** các BeanDefinition cần thiết đã được xử lý trước khi condition đánh giá chưa?
6. **Kiểm tra type metadata:** factory method/FactoryBean có cung cấp kiểu đủ rõ không?
7. **Đọc condition report:** xác nhận lý do thực tế từ Spring Boot.

Quy trình này giúp phân biệt ba loại vấn đề: thiếu Bean, mơ hồ do nhiều Bean, và condition được đánh giá trước khi thông tin cần thiết xuất hiện.

## 14. Mô hình ghi nhớ

```text
@ConditionalOnSingleCandidate(SomeType.class)
                 |
                 v
      BeanFactory tìm candidate theo type
                 |
        +--------+---------+
        |                  |
     0 candidate       1 candidate
        |                  |
      NO MATCH            MATCH
                           |
        +------------------+
        |
   Nhiều candidate
        |
   Có một primary?
      /       \
    Có         Không
    |            |
  MATCH        NO MATCH
```

`@ConditionalOnSingleCandidate` giúp Spring Boot chỉ đăng ký một cấu hình khi container có thể cung cấp một dependency đơn theo kiểu yêu cầu. Khi có một Bean, điều kiện khớp; khi có nhiều Bean, một primary candidate duy nhất có thể làm rõ lựa chọn; nếu không, auto-configuration rút lui để tránh tạo Bean với dependency mơ hồ.

Hãy chọn annotation theo đúng nhu cầu của factory method: cần **ít nhất một Bean**, cần **không có Bean**, hay cần **một candidate duy nhất**. Khi hiểu rõ khác biệt đó, bạn có thể viết auto-configuration linh hoạt với nhiều implementation mà vẫn giữ được quy tắc dependency injection rõ ràng.
