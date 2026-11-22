# Kiểm chứng thứ tự bằng kết quả bean và báo cáo điều kiện

## Mục tiêu của bài

Trong Spring Boot Auto-configuration, việc thêm `@AutoConfiguration(after = ...)` hoặc `@AutoConfigureBefore` mới chỉ **diễn đạt quan hệ xử lý cấu hình**. Muốn biết quan hệ đó có tạo ra hành vi đúng không, bạn cần kiểm chứng đồng thời:

1. **Kết quả bean:** context thực sự có những bean nào, tên và kiểu là gì, bean nào được chọn, bean mặc định có nhường chỗ cho bean nguồn/người dùng hay không?
2. **Kết quả điều kiện:** `ConditionEvaluationReport` ghi nhận điều kiện nào khớp, điều kiện nào không khớp, vì sao `@ConditionalOnBean` hoặc `@ConditionalOnMissingBean` cho kết quả đó?

Chỉ nhìn danh sách bean sau startup có thể xác nhận trạng thái cuối nhưng chưa giải thích quyết định tại **thời điểm bean definition được xử lý**. Ngược lại, chỉ đọc báo cáo điều kiện chưa chứng minh ứng dụng đã tạo bean như mong đợi. Hai tín hiệu cần được đọc **cùng nhau**.

Bài học dùng Spring Boot 3.3.x, Spring Framework 6.1 và Java 17+. Ví dụ gồm một bộ kiểm thử `ApplicationContextRunner` có thể chạy độc lập, kiểm chứng cả thứ tự đúng, thứ tự ngược và trường hợp bean do người dùng cung cấp.

## 1. Hiểu chính xác “thứ tự” trước khi kiểm thử

Có nhiều trình tự khác nhau trong vòng đời Spring; chỉ một số liên quan trực tiếp đến auto-configuration.

| Lớp thứ tự | Thời điểm | Câu hỏi đúng | Cơ chế phù hợp |
| --- | --- | --- | --- |
| Phát hiện / nhập auto-configuration | Bootstrap và phân tích cấu hình | Những auto-configuration nào là ứng viên? | `AutoConfiguration.imports`, classpath, exclude |
| **Áp dụng auto-configuration và đăng ký bean definition** | Trong xử lý configuration | Bean source có được khai báo trước lúc condition phía sau được đánh giá? | `@AutoConfiguration(before/after)`, `beforeName/afterName`, `@AutoConfigureBefore/After`, `@AutoConfigureOrder` |
| Đánh giá điều kiện | Tại một thời điểm trong quá trình xử lý | Bean cần tìm đã có definition và metadata kiểu phù hợp chưa? | `@ConditionalOnBean`, `@ConditionalOnMissingBean`, `ConditionEvaluationReport` |
| **Tạo instance** và injection | Khi context được refresh, bean cần dùng | Constructor/`@Bean` method nào chạy trước? | Quan hệ dependency, constructor injection, `@DependsOn`, lazy/prototype |
| Sử dụng bean khi có request/job | Runtime | Logic nghiệp vụ chạy theo trình tự nào? | Scheduler, transaction, event, flow ứng dụng |

**Quy tắc quan trọng:** `@AutoConfiguration(after = SourceAutoConfiguration.class)` ảnh hưởng đến thứ tự **đăng ký định nghĩa bean** của các auto-configuration, **không bảo đảm** mọi instance do Source tạo sẽ được khởi tạo trước instance ở cấu hình sau.

Ví dụ, phương thức `@Bean` bên dưới được Spring phân tích và đăng ký như một *definition* ngay cả khi đối tượng `CatalogService` chưa được tạo:

```java
@Bean
CatalogService sourceCatalog() {
    return new CatalogService("source");
}
```

Đoạn mã này là **phần của một class `@Configuration`**, không phải chương trình Java độc lập. Điều kiện `@ConditionalOnBean(CatalogService.class)` trong auto-configuration áp dụng **sau** có thể nhận diện bean qua definition/kiểu trả về đã khai báo. Việc bean thực tế chỉ được tạo khi refresh hoặc khi cần dùng không cản trở logic đó.

Không dùng `@DependsOn` để “sửa” việc điều kiện không nhìn thấy definition: `@DependsOn` nói về thứ tự **khởi tạo**, trong khi lỗi là thứ tự **xử lý cấu hình**.

## 2. Những annotation thực sự quản lý thứ tự auto-configuration

Spring Boot 3.x cho phép mô tả quan hệ trực tiếp:

```java
@AutoConfiguration(after = SourceAutoConfiguration.class)
class DependentAutoConfiguration {
}
```

Tương đương ý nghĩa với việc dùng `@AutoConfigureAfter(SourceAutoConfiguration.class)` trên auto-configuration cần được áp dụng sau. Chiều ngược lại:

```java
@AutoConfiguration(before = OtherAutoConfiguration.class)
class EarlierAutoConfiguration {
}
```

Nếu không muốn phụ thuộc vào class trực tiếp, có thể dùng tên đầy đủ:

```java
@AutoConfiguration(
    afterName = "com.example.library.SourceAutoConfiguration")
class OptionalDependentAutoConfiguration {
}
```

Các mảnh ví dụ này giả sử class liên quan đã tồn tại; chúng minh họa annotation chứ không phải file hoàn chỉnh.

- `before` / `after` định nghĩa quan hệ tương đối **giữa các auto-configuration**; cần cả hai được chọn làm ứng viên thì quan hệ mới có cơ hội ảnh hưởng.
- `beforeName` / `afterName` dùng tên class đầy đủ; hữu ích khi thư viện không muốn giữ kiểu class ở compile time hoặc class mục tiêu chỉ tồn tại trong một phiên bản khác.
- `@AutoConfigureOrder` cung cấp thứ tự tổng quát cho các auto-configuration không có quan hệ trực tiếp; khi có dependency về thứ tự rõ ràng, nên biểu đạt bằng `before/after` thay vì các con số khó duy trì.
- `@Order` đặt trên bean/handler thường **không thay thế** quan hệ sắp thứ tự auto-configuration; `@DependsOn` cũng không thay thế.
- Thứ tự cấu hình **không phải** thứ tự ghi từng dòng trong file imports và cũng không phải thứ tự bạn truyền các class cho `AutoConfigurations.of(...)` trong test. Spring Boot sắp xếp auto-configuration theo metadata tương tự khi ứng dụng thực chạy.
- Với Spring Boot 3.x, auto-configuration phát hành qua starter được liệt kê trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`, một tên class trên mỗi dòng. Không dựa vào component scan để nạp auto-configuration.

Cũng cần nhớ: nếu một auto-configuration bị `exclude`, không có trên classpath, hoặc điều kiện ở cấp class loại bỏ nó, quan hệ `after` không thể buộc nó cung cấp bean. **Order là điều kiện cần cho một số luồng phụ thuộc, không thay thế việc bảo đảm bean thực sự được đăng ký.**

## 3. Điều kiện bean đánh giá theo “những gì đã xử lý”

Hai điều kiện dễ làm lộ lỗi thứ tự nhất là:

- `@ConditionalOnBean(CatalogService.class)`: chỉ tạo bean phụ thuộc nếu đã nhận diện được bean kiểu `CatalogService` ở thời điểm kiểm tra.
- `@ConditionalOnMissingBean(CatalogService.class)`: tạo fallback nếu **chưa** nhận diện được ứng viên kiểu `CatalogService` tại thời điểm ấy.

Đây không phải các điều kiện “đợi đến khi mọi @Configuration đã xử lý xong rồi đánh giá lại”. Spring Boot khuyên đặt bean conditions chủ yếu trong auto-configuration vì bean người dùng thường được đăng ký trước các auto-configuration. Giữa các auto-configuration với nhau, người viết phải công bố quan hệ áp dụng khi một bên phụ thuộc định nghĩa của bên kia.

### 3.1. Cùng một nguồn bean, đảo order dẫn đến hai kết quả

Giả sử `SourceAutoConfiguration` luôn cung cấp một bean `CatalogService` tên `sourceCatalog`. `FallbackAutoConfiguration` có:

```java
@Bean
@ConditionalOnMissingBean(CatalogService.class)
CatalogService fallbackCatalog() {
    return new CatalogService("fallback");
}
```

Nếu **fallback áp dụng sau source**:

```text
SourceAutoConfiguration        -> định nghĩa sourceCatalog : CatalogService
FallbackAutoConfiguration      -> kiểm tra MissingBean(CatalogService)
                               -> tìm thấy sourceCatalog -> không đăng ký fallback
Context refresh                -> 1 bean CatalogService
```

Nếu **fallback áp dụng trước source**:

```text
FallbackAutoConfiguration      -> chưa thấy CatalogService -> đăng ký fallback
SourceAutoConfiguration        -> đăng ký sourceCatalog (không có điều kiện)
Context refresh                -> 2 bean CatalogService
```

Hai sơ đồ thể hiện các **tình huống đã kiểm soát**, không phải sự bảo đảm thứ tự mặc định nếu không khai báo ràng buộc. Trường hợp hai bean khác tên cùng kiểu thường làm `getBean(CatalogService.class)` trở nên mơ hồ nếu không có `@Primary`, qualifier hoặc tên rõ ràng. Nó **không nhất thiết** gây lỗi ngay khi refresh nếu không bean nào yêu cầu một ứng viên duy nhất, nhưng là tín hiệu cần điều tra.

### 3.2. Điều kiện OnBean có chiều phụ thuộc tương tự

Nếu `DependentAutoConfiguration` cung cấp:

```java
@Bean
@ConditionalOnBean(CatalogService.class)
DiagnosticMarker diagnosticMarker() {
    return new DiagnosticMarker();
}
```

Khi cấu hình phụ thuộc áp dụng **sau** source, điều kiện có cơ sở nhận diện bean. Khi nó áp dụng **trước** source và chưa có bean kiểu đó nào khác, condition có thể không khớp, khiến `diagnosticMarker` vắng mặt sau startup **dù cuối cùng `sourceCatalog` tồn tại**.

Vì vậy “cuối cùng có bean” không đồng nghĩa “condition đã thấy bean lúc được đánh giá”. Một check cuối quá trình chỉ phát hiện symptom; báo cáo điều kiện bổ sung nguyên nhân.

## 4. Hai nguồn chứng cứ cần ghép cặp

### 4.1. Chứng cứ kết quả bean: WHAT

Sau khi `ApplicationContext` tạo thành công, dùng những phép kiểm tra sau để biết kết quả:

```java
assertThat(context).hasSingleBean(CatalogService.class);
assertThat(context).hasBean("sourceCatalog");
assertThat(context).doesNotHaveBean("fallbackCatalog");
assertThat(context.getBean(CatalogService.class).origin())
        .isEqualTo("source");
```

Đây là **các assertion nằm trong callback của `ApplicationContextRunner`**, với `context` và class `CatalogService` đã được khai báo. Các phép này phân biệt:

1. **Có bao nhiêu bean?** Không có, một hay nhiều ứng viên cùng kiểu?
2. **Tên bean nào tồn tại?** Source, fallback hay user override?
3. **Giá trị/cấu hình quan sát được có đúng không?** Bean có đến từ nguồn đúng và mang thiết lập dự kiến?
4. **Ứng dụng có khởi động thành công không?** Có ngoại lệ `NoSuchBeanDefinitionException`, `NoUniqueBeanDefinitionException` hoặc vòng dependency không?

Lưu ý: `hasSingleBean` chỉ chứng minh số lượng bean phù hợp. Nó **không chứng minh** điều kiện nào đã match. Một bean trùng tên hoặc `@Primary` có thể khiến việc injection thành công, che đi một fallback ngoài ý muốn. Hãy assert cả **tên** và **giá trị nguồn**.

### 4.2. Chứng cứ báo cáo điều kiện: WHY

Spring Boot ghi nhận đánh giá điều kiện trong `ConditionEvaluationReport`. Báo cáo nhóm kết quả theo nguồn đánh giá (configuration class hoặc phương thức `@Bean`). Một nguồn có thể có nhiều condition; chỉ cần một condition không khớp thì cả nguồn không thỏa.

Một cách lấy báo cáo **sau khi context đã refresh**:

```java
ConditionEvaluationReport report =
        ConditionEvaluationReport.get(context.getBeanFactory());
var outcomesBySource = report.getConditionAndOutcomesBySource();
```

Đoạn này nằm trong callback test, có `context` là `AssertableApplicationContext`. Kết quả là map từ khóa `"package.AutoConfiguration#beanMethod"` (hoặc tên class cho condition cấp class) tới tập các `ConditionAndOutcome`. Với nested class, tên JVM chứa ký tự `$` giữa tên class ngoài và class bên trong; vì vậy nên lấy khóa từ `SomeAutoConfiguration.class.getName()` thay vì đoán.

Với một method cụ thể:

```java
String key = FallbackAutoConfiguration.class.getName()
        + "#fallbackCatalog";
var outcomes = report.getConditionAndOutcomesBySource().get(key);
if (outcomes != null) {
    System.out.println("fullMatch=" + outcomes.isFullMatch());
    outcomes.forEach(item -> System.out.println(
            item.getCondition().getClass().getSimpleName()
                    + ": " + item.getOutcome().getMessage()));
}
```

Đây là **mảnh code minh họa**, giả sử `report` và class `FallbackAutoConfiguration` tồn tại. `isFullMatch()` cho biết **mọi condition được ghi cho nguồn đó đều khớp hay không**; từng `getOutcome()` cho kết quả chi tiết và thông điệp. Các thông điệp thường giải thích bean đã tìm thấy/không tìm thấy, kiểu được kiểm tra và search strategy.

Không khẳng định một đoạn thông điệp là stdout cố định: phiên bản Spring Boot, tên bean thực tế, điều kiện kèm theo và logging configuration có thể làm thông điệp khác nhau. Trong test tự động, hãy assert các boolean match và tên bean; khi debug, in message để đọc lý do.

### 4.3. Từ khóa đối chiếu trong báo cáo

| Dấu hiệu từ report | Điều cần đối chiếu với bean cuối | Diễn giải |
| --- | --- | --- |
| `OnBeanCondition` cho `@ConditionalOnMissingBean`: **matched**, không thấy `CatalogService` | Có `fallbackCatalog` | Fallback được phép đăng ký tại thời điểm condition |
| `OnBeanCondition` cho `@ConditionalOnMissingBean`: **not matched**, đã thấy `sourceCatalog` | Không có `fallbackCatalog`, vẫn có `sourceCatalog` | Fallback nhường chỗ đúng |
| `OnBeanCondition` cho `@ConditionalOnBean`: **matched** | Có bean phụ thuộc | Bean cần thiết đã được nhận diện khi condition chạy |
| `OnBeanCondition` cho `@ConditionalOnBean`: **not matched** | Không có bean phụ thuộc, nhưng sau đó có thể có source | Có khả năng source được định nghĩa quá muộn hoặc type metadata không phù hợp |
| `OnClassCondition`: không có thư viện | Bean tích hợp vắng mặt | Vấn đề classpath, không thể quy ngay thành lỗi ordering |
| `OnPropertyCondition`: property tắt | Bean vắng mặt | Vấn đề cấu hình property, không thể chỉ sửa `after` |
| Có source trong `unconditionalClasses` | Context có/không bean phụ thuộc điều kiện | Class đó không mang điều kiện ở cấp auto-configuration; không phải bằng chứng thời điểm bean được tạo |

**Báo cáo điều kiện không phải timeline khởi tạo bean.** Nó không cho bạn thời điểm constructor chạy, thứ tự từng instance được tạo, hoặc lịch sử mọi lần gọi phương thức `@Bean`. Nó là bản ghi điều kiện đã đánh giá trong quá trình cấu hình. Để quan sát khởi tạo, dùng log lifecycle, `BeanPostProcessor` có kiểm soát hoặc application startup tracing theo mục tiêu khác.

## 5. Bài thực hành có thể chạy: chứng minh thứ tự bằng 5 test

Bài thử tạo hai trạng thái đối lập trên cùng module Spring Boot. `SourceAutoConfiguration` luôn định nghĩa `CatalogService`; các auto-configuration “before” và “after” chỉ khác quan hệ thứ tự. Ngoài việc assert bean cuối, test đọc `ConditionEvaluationReport` và assert `isFullMatch()` cho đúng method.

### 5.1. Cấu trúc và dependency

Tạo một thư mục test Gradle độc lập:

```text
auto-configuration-order-lab/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/AutoConfigurationOrderEvidenceTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'auto-configuration-order-lab'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.3.13'
}

test {
    useJUnitPlatform()
}
```

Cần Java 17+ và Gradle tương thích phiên bản Java bạn dùng. `spring-boot-starter-test` mang những thư viện cần cho `ApplicationContextRunner`, JUnit 5, AssertJ và Spring Boot auto-configuration. Bài này không cần database, server, Docker, file `application.properties` hay chạy `SpringApplication` thật.

### 5.2. File test Java 17 hoàn chỉnh

`src/test/java/demo/AutoConfigurationOrderEvidenceTest.java`:

```java
package demo;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcomes;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationOrderEvidenceTest {

    record CatalogService(String origin) {}

    record DiagnosticMarker(String value) {}

    @AutoConfiguration
    static class SourceAutoConfiguration {
        @Bean
        CatalogService sourceCatalog() {
            return new CatalogService("source");
        }
    }

    @AutoConfiguration(after = SourceAutoConfiguration.class)
    static class LateFallbackAutoConfiguration {
        @Bean
        @ConditionalOnMissingBean(CatalogService.class)
        CatalogService lateFallback() {
            return new CatalogService("fallback");
        }
    }

    @AutoConfiguration(before = SourceAutoConfiguration.class)
    static class EarlyFallbackAutoConfiguration {
        @Bean
        @ConditionalOnMissingBean(CatalogService.class)
        CatalogService earlyFallback() {
            return new CatalogService("fallback");
        }
    }

    @AutoConfiguration(after = SourceAutoConfiguration.class)
    static class LateObserverAutoConfiguration {
        @Bean
        @ConditionalOnBean(CatalogService.class)
        DiagnosticMarker lateObserver() {
            return new DiagnosticMarker("seen");
        }
    }

    @AutoConfiguration(before = SourceAutoConfiguration.class)
    static class EarlyObserverAutoConfiguration {
        @Bean
        @ConditionalOnBean(CatalogService.class)
        DiagnosticMarker earlyObserver() {
            return new DiagnosticMarker("seen");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserCatalogConfiguration {
        @Bean
        CatalogService customCatalog() {
            return new CatalogService("user");
        }
    }

    private ApplicationContextRunner runner(Class<?>... configurations) {
        return new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(configurations));
    }

    private boolean conditionMatched(
            AssertableApplicationContext context,
            Class<?> configurationClass,
            String beanMethod) {

        ConditionEvaluationReport report =
                ConditionEvaluationReport.get(context.getBeanFactory());

        Map<String, ConditionAndOutcomes> outcomesBySource =
                report.getConditionAndOutcomesBySource();

        String source = configurationClass.getName() + "#" + beanMethod;
        assertThat(outcomesBySource)
                .as("Condition report should contain " + source)
                .containsKey(source);

        return outcomesBySource.get(source).isFullMatch();
    }

    @Test
    void fallbackAfterSourceIsSkippedAndReportExplainsWhy() {
        // Cố ý truyền LateFallback trước; Boot vẫn áp dụng "after".
        runner(LateFallbackAutoConfiguration.class,
                SourceAutoConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(CatalogService.class);
                    assertThat(context).hasBean("sourceCatalog");
                    assertThat(context).doesNotHaveBean("lateFallback");
                    assertThat(context.getBean(CatalogService.class).origin())
                            .isEqualTo("source");

                    assertThat(conditionMatched(context,
                            LateFallbackAutoConfiguration.class,
                            "lateFallback")).isFalse();
                });
    }

    @Test
    void fallbackBeforeSourceCreatesTwoDefinitions() {
        // Cố ý truyền Source trước; quan hệ "before" vẫn thắng.
        runner(SourceAutoConfiguration.class,
                EarlyFallbackAutoConfiguration.class)
                .run(context -> {
                    assertThat(context).hasBean("earlyFallback");
                    assertThat(context).hasBean("sourceCatalog");
                    assertThat(context.getBeansOfType(CatalogService.class))
                            .containsOnlyKeys("earlyFallback", "sourceCatalog");

                    assertThat(conditionMatched(context,
                            EarlyFallbackAutoConfiguration.class,
                            "earlyFallback")).isTrue();
                });
    }

    @Test
    void observerAfterSourceSeesTheDefinition() {
        runner(LateObserverAutoConfiguration.class,
                SourceAutoConfiguration.class)
                .run(context -> {
                    assertThat(context).hasBean("sourceCatalog");
                    assertThat(context).hasSingleBean(DiagnosticMarker.class);
                    assertThat(context).hasBean("lateObserver");

                    assertThat(conditionMatched(context,
                            LateObserverAutoConfiguration.class,
                            "lateObserver")).isTrue();
                });
    }

    @Test
    void observerBeforeSourceDoesNotSeeTheFutureDefinition() {
        runner(SourceAutoConfiguration.class,
                EarlyObserverAutoConfiguration.class)
                .run(context -> {
                    assertThat(context).hasBean("sourceCatalog");
                    assertThat(context).doesNotHaveBean("earlyObserver");
                    assertThat(context).doesNotHaveBean(DiagnosticMarker.class);

                    assertThat(conditionMatched(context,
                            EarlyObserverAutoConfiguration.class,
                            "earlyObserver")).isFalse();
                });
    }

    @Test
    void userBeanBeatsFallbackWithoutSourceAutoConfiguration() {
        runner(LateFallbackAutoConfiguration.class)
                .withUserConfiguration(UserCatalogConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(CatalogService.class);
                    assertThat(context).hasBean("customCatalog");
                    assertThat(context).doesNotHaveBean("lateFallback");
                    assertThat(context.getBean(CatalogService.class).origin())
                            .isEqualTo("user");

                    assertThat(conditionMatched(context,
                            LateFallbackAutoConfiguration.class,
                            "lateFallback")).isFalse();
                });
    }
}
```

**Lưu ý về test:** Đây là **năm context độc lập**. Hai tình huống early fallback và early observer được kiểm tra ở **hai context riêng**, tránh để fallback đăng ký trước vô tình tạo thành ứng viên cho observer và làm sai phép so sánh. Đây chính là cách kiểm soát biến khi thử order.

### 5.3. Chạy test và quan sát kết quả

Từ thư mục dự án:

```bash
gradle test --tests demo.AutoConfigurationOrderEvidenceTest
```

Nếu repo có wrapper, trên Linux/macOS:

```bash
./gradlew test --tests demo.AutoConfigurationOrderEvidenceTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests demo.AutoConfigurationOrderEvidenceTest
```

**Kết quả kỳ vọng**: task test hoàn thành với **5 test passed** (với các dependency tương thích). Không coi toàn bộ Gradle log hay thứ tự log là stdout cố định. Bài kiểm thử là mẫu để người học tạo project và chạy; nếu chưa chạy test thực tế trong môi trường của bạn, đó là kỳ vọng lý thuyết dựa trên các API đã mô tả.

### 5.4. Ma trận kết quả bắt buộc kiểm chứng

| Test | Bean source | Bean fallback | Bean observer | Match của condition đang kiểm tra |
| --- | --- | --- | --- | --- |
| `fallbackAfterSource...` | `sourceCatalog` có | `lateFallback` không | Không xét | `@ConditionalOnMissingBean` = **false** |
| `fallbackBeforeSource...` | `sourceCatalog` có | `earlyFallback` có | Không xét | `@ConditionalOnMissingBean` = **true** |
| `observerAfterSource...` | `sourceCatalog` có | Không xét | `lateObserver` có | `@ConditionalOnBean` = **true** |
| `observerBeforeSource...` | `sourceCatalog` có **cuối cùng** | Không xét | `earlyObserver` không | `@ConditionalOnBean` = **false** |
| `userBeanBeatsFallback...` | `customCatalog` có | `lateFallback` không | Không xét | `@ConditionalOnMissingBean` = **false** |

Cột “match” ứng với kết quả `ConditionAndOutcomes.isFullMatch()` của method đang xét. Đó **không phải** cờ chứa thứ tự A trước B do report lưu; quan hệ thứ tự được suy ra từ **kết quả khi đổi annotation**, và được khẳng định bằng source/bean/condition trong context đã cô lập.

Hai test đầu và test observer-before chứng minh vì sao chỉ xem bean list cuối không đủ. Ở test `observerBeforeSource...`, bean `sourceCatalog` **đã có sau refresh** nhưng observer vẫn không tồn tại: khi condition được đánh giá, source chưa được xử lý. Report thể hiện `OnBeanCondition` không match cho `earlyObserver`; điều kiện không được “replay” sau đó.

## 6. In lý do từ ConditionEvaluationReport mà không phụ thuộc câu chữ log

Các test trên kiểm tra boolean `isFullMatch()`. Khi cần đọc **thông điệp cụ thể** mà Spring Boot đưa ra, thêm đoạn sau bên trong callback của một test (đây là mảnh minh họa, không phải file riêng):

```java
ConditionEvaluationReport report =
        ConditionEvaluationReport.get(context.getBeanFactory());

report.getConditionAndOutcomesBySource()
        .forEach((source, outcomes) -> {
            if (!source.contains("FallbackAutoConfiguration")) {
                return;
            }
            System.out.println(source + " -> match=" + outcomes.isFullMatch());
            outcomes.forEach(item -> System.out.println(
                    "  " + item.getCondition().getClass().getSimpleName()
                    + ": matched=" + item.getOutcome().isMatch()
                    + "; message=" + item.getOutcome().getMessage()));
        });
```

Đoạn này dùng lại các import `ConditionEvaluationReport` đã có trong file test. Nó không in một “dòng chuẩn” cố định vì nội dung thông điệp phụ thuộc tình huống. Cần đọc cả **source key** và **tên condition**: một cấu hình có thể không khớp do `OnClassCondition` hoặc `OnPropertyCondition`, dù thứ tự source/fallback hoàn toàn đúng.

Có thể nhờ Spring Boot tự log report khi chạy test:

```java
new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener
                        .forLogLevel(LogLevel.INFO))
        .withConfiguration(
                AutoConfigurations.of(
                        SourceAutoConfiguration.class,
                        LateFallbackAutoConfiguration.class))
        .run(context -> {
            // Assert bean và condition tại đây.
        });
```

Đoạn ví dụ này dùng thêm các import:

```java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
```

Nội dung trong callback là **minh họa vị trí assertion**, không phải code hoàn chỉnh để copy tách rời. Nếu Gradle hoặc logging backend không hiện stdout/test logging, cấu hình `testLogging.showStandardStreams = true` (nếu cần) hoặc kiểm tra report qua API như ở mục 5. Không vì không thấy log mà kết luận không có report.

Trong ứng dụng Spring Boot thực, có thể bật report bằng tham số khởi động `--debug` hoặc `debug=true`. Khi dùng Spring Boot Actuator và endpoint `conditions` được bật/expose phù hợp, `GET /actuator/conditions` cung cấp bản báo cáo dạng JSON.

### 6.1. Đọc các trường trong Actuator report

Một mẫu **rút gọn theo cấu trúc**, không phải output cố định từ các test ở trên:

```json
{
  "contexts": {
    "application": {
      "positiveMatches": {
        "demo.ExampleAutoConfiguration#fallback": [
          {
            "condition": "OnBeanCondition",
            "message": "explanation produced by Spring Boot"
          }
        ]
      },
      "negativeMatches": {
        "demo.OtherAutoConfiguration#other": {
          "notMatched": [
            {
              "condition": "OnBeanCondition",
              "message": "why the condition failed"
            }
          ],
          "matched": []
        }
      },
      "unconditionalClasses": []
    }
  }
}
```

`positiveMatches` là nhóm các source được điều kiện cho phép; `negativeMatches` ghi các source bị loại cùng danh sách `notMatched` và các điều kiện khác có thể đã `matched`. `unconditionalClasses` liệt kê những auto-configuration không bị ràng buộc bởi condition tương ứng. Source key ở cấp method thường chứa `#methodName`. Với nhiều context (management/parent/child), phải chọn đúng context id.

**Đặc biệt:** thứ tự các mục trong report, thứ tự key JSON hoặc thứ tự log **không phải bằng chứng** thứ tự bean được tạo. Dùng bean assertions và lý do match để xác nhận trạng thái; dùng ràng buộc metadata và test đảo ngược để xác minh nguyên nhân.

### 6.2. Report không thay thế failure analysis

Khi ứng dụng không khởi động, có thể xem log thất bại và condition report (nếu thu được) để biết vì sao bean bị loại hoặc trùng. Tuy nhiên, một `NoUniqueBeanDefinitionException` có thể xuất hiện **sau** khi cả hai bean definition đều đăng ký. Report có thể cho biết vì sao fallback từng được phép tạo, nhưng không giải thích toàn bộ lỗi injection; cần đối chiếu stack trace và bean graph.

Khi dùng `ApplicationContextRunner` và cố tình kiểm tra trường hợp context fail, có thể assert:

```java
runner.run(context -> {
    assertThat(context).hasFailed();
    assertThat(context.getStartupFailure())
            .hasRootCauseInstanceOf(
                    org.springframework.beans.factory.NoUniqueBeanDefinitionException.class);
});
```

Đây chỉ là **mẫu test cho tình huống được thiết kế để fail** với helper `runner` đã có trong context khác. **Không thêm assertion này vào 5 test chính**, vì chúng không tạo dependency đòi hỏi một ứng viên duy nhất. Cách kiểm tra exception cụ thể cần thích ứng với chuỗi exception của trường hợp thực tế.

## 7. Quy trình điều tra khi nghi ngờ lỗi thứ tự ở một module

Áp dụng quy trình bảy bước dưới đây để tránh sửa nhầm:

1. **Chụp lại kết quả mong muốn.** Định nghĩa rõ “nếu user đã cung cấp `CatalogService`, fallback phải vắng mặt; nếu source có thì observer phải có”. Ghi tên bean và kiểu như hợp đồng test.
2. **Xác định ai cung cấp bean nguồn.** Bean user config, component scan, bean của auto-config khác, registrar hay factory? `@ConditionalOnBean` kiểm tra các definition đã được xử lý, nên không thể chỉ nhìn bean hiện diện cuối cùng. Đảm bảo kiểu trả về của `@Bean` đủ chính xác.
3. **Ghi quan hệ thứ tự thực sự.** Ai cần `after` ai? Có `afterName` trỏ đúng tên class Java đầy đủ không? Class mục tiêu có được chọn làm auto-config không? Đã vô tình loại trừ hoặc tắt class bằng điều kiện khác chưa?
4. **Kiểm tra bean kết quả.** Dùng `ApplicationContextRunner` để assert `hasBean`/`doesNotHaveBean`, `hasSingleBean` hoặc `getBeansOfType`. Ghi lại bean names và nguồn tạo.
5. **Lấy report đúng context.** Dùng `ConditionEvaluationReport.get(context.getBeanFactory())`; đối chiếu source key `AutoConfiguration#beanMethod` và `OnBeanCondition`, đọc positive/negative matches. Nếu condition chưa từng được đánh giá vì cấu hình cấp class bị loại trước, hãy kiểm tra **class-level source** tương ứng.
6. **Đổi đúng một biến.** Thử ràng buộc `before` so với `after` với cùng classpath/properties; thử có và không có user bean. Đừng đổi order, property, mock và dependency cùng lúc.
7. **Chốt bằng test hành vi.** Assertion bean phải bảo vệ contract; assertion report bảo vệ lời giải thích. Giữ những test đó khi refactor starter/auto-configuration hoặc nâng Spring Boot.

Để tránh “test xanh giả”, đừng chỉ assert `context.containsBean("sourceCatalog")`. Với bug fallback vẫn tồn tại, source có thể vẫn hiện diện và phép test sẽ xanh. Phải assert **fallback vắng mặt**, **số lượng bean**, **giá trị nguồn** và ít nhất một **condition outcome** liên quan.

## 8. Những nguyên nhân có biểu hiện giống sai thứ tự

Không phải mỗi `@ConditionalOnBean` không khớp đều do `after` thiếu.

| Hiện tượng | Nguyên nhân khác cần xét | Dấu hiệu phân biệt |
| --- | --- | --- |
| Bean xuất hiện cuối cùng nhưng `@ConditionalOnBean` đã không khớp | Definition được đăng ký muộn; hoặc metadata type không nhận diện được | Report ghi không tìm thấy ứng viên; kiểm tra type khai báo và thứ tự xử lý |
| `after` đúng mà fallback vẫn bật | Source bị condition ở cấp class/method loại, không có definition | Report source có `OnClassCondition`, `OnPropertyCondition`, `OnBeanCondition` âm |
| Bean nguồn có nhưng fallback không tắt | `@Bean Object service()` hoặc kiểu factory quá rộng | Condition theo `CatalogService` không thấy type như mong đợi; sửa metadata/return type |
| Bean user tồn tại nhưng cả fallback cũng có | Definition user được tạo ở nhánh/config timing không đúng, hoặc condition theo type khác | Test `withUserConfiguration` và đối chiếu chính xác type/name |
| Có 2 bean nhưng app vẫn chạy | Chưa injection một bean đơn, có qualifier/primary hoặc không ai tiêu thụ | Assert `getBeansOfType` và giá trị source, không chỉ startup |
| App fail khi inject một bean | Trùng ứng viên do fallback và source, hoặc phụ thuộc khác | Stack trace xác định lỗi; report chỉ giải thích các condition |
| Lý do âm không nói đến bean | Classpath/property/web condition không khớp | Xem tên condition, sửa tầng nguyên nhân |
| Thay `@Order` nhưng không đổi kết quả | `@Order` không sắp auto-config theo quan hệ bean definition mong muốn | Dùng `@AutoConfiguration(before/after)`, test lại |
| Thêm `@DependsOn` không thay condition | `@DependsOn` điều khiển initialization | Sửa thứ tự processing definition |
| Test phụ thuộc vào thứ tự truyền `AutoConfigurations.of` | Chưa hiểu boot sorter; test có coupling không đáng tin | Dùng metadata quan hệ, đảo thứ tự tham số như ví dụ test |
| Condition kết quả khác giữa app và runner | Runner thiếu user configuration, environment, classpath, parent context hoặc auto-config | Xây dựng context test đại diện cho tình huống thật |

### 8.1. Đừng dùng type yếu làm “bằng chứng” sai order

Nếu source bean được khai báo như sau:

```java
@Bean
Object catalogService() {
    return new CatalogService("source");
}
```

thì condition `@ConditionalOnBean(CatalogService.class)` **không được bảo đảm** nhận diện đúng implementation trước khi bean được tạo. Việc đổi `before/after` có thể không giải quyết vì source đã đăng ký nhưng **metadata type không đủ**. Cách khắc phục là khai báo kiểu trả về phù hợp:

```java
@Bean
CatalogService catalogService() {
    return new CatalogService("source");
}
```

Các đoạn minh họa này giả định `CatalogService` có constructor như record trong bài test. Nếu source là `FactoryBean`, cần xem kiểu sản phẩm được công bố qua `getObjectType()` hoặc metadata tương ứng; factory tồn tại chưa chắc cho condition biết type sản phẩm. Đây là bước kiểm tra bổ sung khi report và kết quả bean bất nhất.

### 8.2. Không dựa vào thứ tự của các `@Bean` trong cùng một config

Hai phương thức `@Bean` có điều kiện liên hệ nhau đặt trong cùng `@Configuration` có thể tạo dependency về thứ tự xử lý không rõ ràng. Để kiểm chứng quan hệ auto-config một cách ổn định, đưa nguồn và phần phụ thuộc vào **các auto-configuration riêng** và khai báo `after` rõ ràng như bộ test ở mục 5. Khi mục tiêu là user override, dùng `withUserConfiguration(...)` của runner để mô hình hóa việc user configuration được xử lý trước auto-configuration.

Nếu nhiều auto-configuration cùng cung cấp fallback cho một interface, chúng có thể tác động lẫn nhau qua `@ConditionalOnMissingBean`. Test cần kể cả trường hợp nhiều nguồn cùng được import, nhưng vẫn giữ từng tình huống cô lập và có assert số lượng, tên và source của bean.

## 9. Không nhầm order metadata với order khởi tạo bean

Một thử nghiệm nhỏ ngoài `ConditionEvaluationReport` giúp làm rõ giới hạn:

```java
@AutoConfiguration(after = SourceAutoConfiguration.class)
class ConsumerAutoConfiguration {
    @Bean
    Consumer consumer(CatalogService catalogService) {
        return new Consumer(catalogService);
    }
}
```

Đây là **đoạn minh họa** giả sử `SourceAutoConfiguration`, `CatalogService` và `Consumer` tồn tại. Việc `Consumer` nhận `CatalogService` qua tham số nói cho container biết quan hệ dependency khi tạo instance. `after` cho Spring Boot biết thứ tự áp dụng auto-configuration. Hai cơ chế bổ trợ nhưng không đồng nhất.

Nếu có một bean cần khởi tạo trước bean khác **mà không có injection**, `@DependsOn` có thể diễn đạt quan hệ lifecycle; nó **không thể khiến `@ConditionalOnBean` đánh giá lại**. Đối với startup benchmark, timestamp constructor không chứng minh thứ tự condition: bean có thể được lazy-create rất lâu sau khi report đã ghi.

## 10. Tiêu chí QA cho một thay đổi ordering

Khi một PR sửa `@AutoConfiguration(after=...)`, nên ghi nhận bốn bằng chứng có thể review:

**(A) Đầu vào kiểm soát được.** Danh sách auto-config, source bean, user config, classpath/properties và hướng thứ tự cần kiểm tra.

**(B) Bean assertions.** Có/không có bean theo tên, số bean theo type, bean thực sự được dùng. Với fallback: khi source tồn tại, fallback phải vắng; khi source vắng, fallback phải tồn tại (nếu không bị các condition khác chặn).

**(C) Condition outcomes.** Source key của method/cấu hình, `isFullMatch()` và điều kiện giải thích được kết quả. Với incident thật, ghi message đọc từ report để đối chiếu lý do, nhưng không cố định nguyên văn message thành test mong manh.

**(D) Trường hợp đối chứng.** Có user bean, không có user bean, source chạy sớm/chạy muộn hoặc disable source, và ít nhất một case dùng bean phụ thuộc nếu tính năng cần `@ConditionalOnBean`.

Ví dụ một bằng chứng thay đổi hợp lệ để reviewer đọc:

```text
Expected:
  Source enabled -> exactly one CatalogService named sourceCatalog.
  Fallback absent.
  OnBeanCondition for lateFallback -> not matched (source found).

Controlled inverse:
  Early fallback -> earlyFallback + sourceCatalog both registered.
  OnBeanCondition for earlyFallback -> matched (source not yet seen).

Reason:
  Auto-configuration ordering affects definition visibility
  when @ConditionalOnMissingBean evaluates.
```

Đây là **minh họa kết quả quan sát dự kiến**, không phải nhật ký thực đã chạy trong một môi trường khác.

Kết quả `condition full match=false` không phải lỗi test nếu ta **cố ý** kiểm chứng một fallback đã bị tắt. Đó mới là hành vi đúng. Điều quan trọng là ghép cặp ý nghĩa của điều kiện với sự có/vắng bean phù hợp.

## 11. Checklist cuối trước khi kết luận “đã sửa order”

- [ ] Có mô tả cụ thể bean nào phải xuất hiện, bean nào phải vắng và khi nào?
- [ ] Có phân biệt thứ tự áp dụng **auto-configuration** với thứ tự **khởi tạo bean instance**?
- [ ] Đã khai báo `before/after` hoặc `beforeName/afterName` dựa trên quan hệ thực?
- [ ] Source có thật sự được chọn, xử lý và cung cấp **bean definition** kiểu phù hợp?
- [ ] Có assert tên + số lượng + giá trị bean, thay vì chỉ test startup success?
- [ ] Có đọc `ConditionEvaluationReport` của đúng context, đúng class hoặc method?
- [ ] Có kiểm tra cả match và không match (đặc biệt `@ConditionalOnMissingBean`)?
- [ ] Có thử context với user bean và không có user bean?
- [ ] Có tránh nhầm `@DependsOn`/`@Order` với order auto-config?
- [ ] Có kiểm tra lỗi classpath, property và type metadata trước khi quy mọi triệu chứng cho order?

**Ghi nhớ:** **Bean list trả lời “đã có gì?”; Condition Evaluation Report trả lời “vì sao điều kiện cho phép hoặc từ chối?”**. Ghép chúng trong test cô lập, giữ đầu vào ổn định và đổi duy nhất quan hệ `before/after` là cách chắc chắn để kiểm chứng hiệu ứng thứ tự trong Spring Boot Auto-configuration.

## Tài liệu chính thức để đối chiếu

- Spring Boot 3.3 — Creating Your Own Auto-configuration: quy tắc ordering, bean conditions và `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 API — `@AutoConfiguration` và `before/after/afterName`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
- Spring Boot 3.3 API — `@AutoConfigureAfter`, giải thích chỉ ảnh hưởng definition order: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureAfter.html
- Spring Boot 3.3 API — `ConditionEvaluationReport`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html
- Spring Boot 3.3 API — `ConditionEvaluationReportLoggingListener`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/logging/ConditionEvaluationReportLoggingListener.html
- Spring Boot 3.3 Actuator API — Conditions Evaluation Report: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html
