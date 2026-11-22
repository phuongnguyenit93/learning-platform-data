# Đối chiếu suy luận từ mã nguồn với một thí nghiệm context tối thiểu khi đọc Spring Boot Auto Configuration

Khi đọc một lớp auto-configuration, ta thường thấy một vài annotation như `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnMissingBean` và một hoặc nhiều phương thức `@Bean`. Từ mã nguồn, ta có thể **suy luận** bean nào có khả năng được đăng ký. Nhưng suy luận đó còn phụ thuộc classpath, property, bean do ứng dụng cung cấp, thứ tự xử lý, context hierarchy và phiên bản Spring Boot đang chạy.

Cách làm chắc chắn là ghép hai loại bằng chứng:

1. **Đọc mã nguồn để hình thành giả thuyết:** lớp nào được Boot tìm thấy, condition nào cần khớp, phương thức bean nào được phép chạy và bean nào phải back off.
2. **Dựng một context tối thiểu để kiểm chứng:** chỉ nạp auto-configuration đang nghiên cứu, kiểm soát property và user bean, rồi quan sát bean definitions cùng `ConditionEvaluationReport`.

Thí nghiệm không thay thế việc đọc mã nguồn; mã nguồn cũng không thay thế quan sát runtime. Hai cách bổ sung cho nhau: mã nguồn giải thích *vì sao* một nhánh được thiết kế như vậy, còn context test xác nhận *trong điều kiện cụ thể* nhánh đó thật sự diễn ra.

## 1. Bắt đầu bằng đúng phiên bản và đúng artifact

Trước khi đọc class trên GitHub hoặc IDE, xác định **phiên bản Spring Boot thực sự được resolve**. Một ứng dụng có thể khai báo parent hoặc BOM một phiên bản, nhưng dependency transitive, plugin hay module con có thể làm người đọc nhìn nhầm artifact khác.

Với Maven, bắt đầu bằng:

```bash
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-autoconfigure
```

Đọc phiên bản của `spring-boot-autoconfigure` trong output. Đây là artifact chứa phần lớn auto-configuration của Spring Boot. Kiểm tra thêm `spring-boot` và `spring-boot-test` nếu đang xem bootstrap hoặc test runner:

```bash
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot,spring-boot-test,spring-boot-autoconfigure
```

Với Gradle:

```bash
./gradlew dependencyInsight --dependency spring-boot-autoconfigure --configuration runtimeClasspath
```

Sau khi biết phiên bản, mở **source JAR cùng phiên bản**. Maven có thể tải source JAR bằng:

```bash
mvn dependency:sources -DincludeGroupIds=org.springframework.boot
```

Trong IDE, có thể mở `External Libraries` hoặc `Go to Declaration` để nhảy vào source. Nếu chỉ có bytecode, decompiler là phương án đọc tạm thời; cần nhớ bytecode không cung cấp đầy đủ comment, tên tham số hoặc cấu trúc source ban đầu. Không đối chiếu source của nhánh `main` với ứng dụng đang chạy Boot 3.3.x rồi coi mọi chi tiết là giống nhau.

**Quy tắc:** ghi lại version, tọa độ artifact và class đang đọc. Khi thí nghiệm cho kết quả khác dự đoán, bước đầu tiên là xác nhận test và ứng dụng đang dùng **cùng phiên bản**.

## 2. Theo dấu đường nạp auto-configuration trước khi đọc condition

Một class mang tên `*AutoConfiguration` không tự động được nạp chỉ vì nó nằm trong dependency JAR. Với Spring Boot 3.x, ứng viên auto-configuration được công bố trong resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Mỗi dòng liệt kê tên đầy đủ của một class auto-configuration. Khi đọc starter hoặc thư viện, hãy kiểm tra resource này **trong đúng JAR**:

```text
com.example.storage.autoconfigure.StorageAutoConfiguration
com.example.storage.autoconfigure.StorageWebAutoConfiguration
```

Tên ở trên chỉ là ví dụ. Trong JAR thực tế, tìm resource bằng IDE, lệnh `jar tf` hoặc công cụ xem archive. Nếu class không được liệt kê, cần tìm cơ chế đăng ký khác hoặc xác định vì sao class không phải ứng viên.

Ở mức khái quát, đường đi là:

```text
@SpringBootApplication / @EnableAutoConfiguration
                 |
                 v
      AutoConfigurationImportSelector
                 |
                 v
  Tìm candidate từ AutoConfiguration.imports
                 |
                 v
       Áp dụng exclusions / filters
                 |
                 v
       Sắp thứ tự auto-configuration
                 |
                 v
     Xử lý class và các @Conditional
                 |
                 v
       Đăng ký bean definitions phù hợp
                 |
                 v
       Khởi tạo bean theo dependency
```

`AutoConfigurationImportSelector` là `DeferredImportSelector` chuyên xử lý auto-configuration. Đây là điểm tham chiếu hữu ích khi muốn hiểu cơ chế import ở mức framework. Trong ứng dụng thông thường, **không cần tự gọi selector hoặc dùng API nội bộ của nó**; hãy dùng cơ chế nạp chính thức và test bằng `AutoConfigurations.of`.

Ngoài resource imports, kiểm tra:

- `@SpringBootApplication(exclude = …)` hoặc `excludeName`.
- Property `spring.autoconfigure.exclude`.
- `AutoConfigurationImportFilter` và metadata lọc sớm nếu thư viện có dùng.
- Starter có thật sự nằm trên runtime classpath không.
- Auto-configuration có vô tình bị component scan hoặc `@Import` theo đường khác không.

Một class không xuất hiện trong report condition có thể **chưa từng là candidate**, bị exclude hoặc bị lọc sớm. Không nên kết luận “condition của nó đã pass” chỉ vì không thấy nó trong `negativeMatches`.

## 3. Đọc một auto-configuration theo thứ tự

Khi đã xác nhận class được nạp, đọc theo các lớp thông tin sau. Đừng bắt đầu bằng việc đoán từ tên bean.

### 3.1. Annotation trên class

Ví dụ:

```java
@AutoConfiguration(after = ClientCoreAutoConfiguration.class)
@ConditionalOnClass(ClientApi.class)
@ConditionalOnProperty(
        prefix = "demo.client",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class ClientAutoConfiguration {
    // Các cấu hình con và bean methods...
}
```

Đây là đoạn minh họa; các kiểu `ClientApi` và `ClientCoreAutoConfiguration` cần tồn tại trong dự án thật.

Đọc từng annotation và ghi lại giả thuyết:

- `@AutoConfiguration`: class là cấu hình được thiết kế cho cơ chế auto-configuration.
- `after = …`: Boot cần áp dụng class này sau auto-configuration được nêu. Thứ tự ảnh hưởng **thứ tự định nghĩa bean**, không tự quyết định thứ tự tạo instance.
- `@ConditionalOnClass`: class cần thiết phải có trên classpath.
- `@ConditionalOnProperty`: property phải đạt yêu cầu. Với `havingValue = "true"` và `matchIfMissing = false`, property thiếu hoặc không phải `true` khiến condition không khớp.
- `@Import` hoặc nested configuration: có thể mở thêm nhánh cấu hình, cần tiếp tục lần theo class được import.

Một class có nhiều condition thường chỉ được áp dụng khi **tất cả condition cần thiết** của class đều khớp. Nếu class condition không khớp, các bean method bên trong không được xử lý như thể lớp đã được bật đầy đủ.

### 3.2. Nested configuration và điều kiện theo classpath

Một thư viện có thể chỉ cần một API khi feature cụ thể được cài đặt. Cấu hình thường tách như sau:

```java
@AutoConfiguration
public class StorageAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(StorageClient.class)
    static class StorageClientConfiguration {

        @Bean
        @ConditionalOnMissingBean(StorageClient.class)
        StorageClient storageClient() {
            return new DefaultStorageClient();
        }
    }
}
```

Đây là trích đoạn minh họa. Việc cô lập class có dependency tùy chọn trong nested configuration giúp tránh nạp các kiểu không tồn tại khi optional library vắng mặt. Spring Boot dùng metadata để xử lý annotation condition; với `@Bean` method, JVM có thể cần load kiểu xuất hiện trong chữ ký phương thức trước khi condition method được áp dụng. Vì thế hãy đọc **vị trí condition**, không chỉ đọc tên annotation.

### 3.3. Từng phương thức `@Bean`

Với mỗi phương thức, ghi lại:

- Tên bean mặc định và mọi tên phụ được khai báo.
- Kiểu trả về khai báo, nhất là interface và implementation.
- `@Conditional` đặt ngay trên method.
- Tham số method được inject và chúng là bắt buộc hay tùy chọn.
- Có dùng `ObjectProvider`, `Optional`, `@Lazy` hay factory bean không.
- Method có phụ thuộc vào property hoặc bean khác không.

Ví dụ:

```java
@Bean
@ConditionalOnMissingBean(StorageClient.class)
StorageClient storageClient(StorageProperties properties) {
    return new DefaultStorageClient(properties.endpoint());
}
```

Suy luận ban đầu: khi class configuration được áp dụng, nếu không có bean phù hợp `StorageClient` và các điều kiện khác khớp, method có thể đăng ký default. Nhưng phải kiểm tra kiểu khai báo và bean definition đã được xử lý trước đó. `@ConditionalOnMissingBean` đánh giá những definition mà Spring đã xử lý **tới thời điểm condition chạy**, không phải một ảnh chụp bao gồm mọi bean có thể xuất hiện về sau.

**Chú ý kiểu trả về:** condition theo bean type có thể dựa trên thông tin kiểu mà method signature cung cấp. Đừng chỉ nhìn kiểu thực tế của object được `return`; kiểu trả về khai báo có ý nghĩa đối với quá trình phân tích bean metadata.

### 3.4. Property và default value

Tìm `@ConfigurationProperties`, `@DefaultValue`, constructor binding, field initializer và các property condition liên quan. Cần phân biệt:

- Property dùng để **quyết định cấu hình có được áp dụng** hay không.
- Property dùng để **điều chỉnh hành vi bean sau khi bean đã được tạo**.
- Giá trị mặc định trong Java model với giá trị mặc định của `@ConditionalOnProperty`.

Ví dụ `matchIfMissing = true` có thể bật condition ngay cả khi property không tồn tại; còn `matchIfMissing = false` yêu cầu property có mặt và đạt giá trị được chỉ định. Không thể kết luận chỉ từ việc thấy một key trong file `application.yml`; profile, environment variable, command line và property source có thể ghi đè giá trị đó.

### 3.5. Thứ tự và phụ thuộc

Nếu có `@AutoConfigureBefore`, `@AutoConfigureAfter`, `before/after` trên `@AutoConfiguration` hoặc `@AutoConfigureOrder`, ghi lại quan hệ trước/sau. Sau đó kiểm tra bean method có dùng `@ConditionalOnBean` hoặc `@ConditionalOnMissingBean` không.

Thứ tự auto-configuration ảnh hưởng **lúc bean definition được đăng ký**; thứ tự tạo instance sau đó phụ thuộc constructor injection, dependency graph và `@DependsOn`. Không dùng thứ tự khởi tạo bean để suy ra thứ tự condition được đánh giá, và ngược lại.

## 4. Chuyển suy luận thành giả thuyết có thể kiểm chứng

Một nhận định tốt cần chỉ rõ **điều kiện đầu vào** và **quan sát mong đợi**. Tránh câu mơ hồ như “cấu hình này sẽ chạy”.

Ví dụ với `ClientAutoConfiguration` ở trên:

| Mã nguồn quan sát được | Giả thuyết cần kiểm chứng | Cách tạo tình huống |
| --- | --- | --- |
| `@ConditionalOnClass(ClientApi.class)` | Thiếu `ClientApi` thì nhánh cấu hình không được áp dụng. | Dùng `FilteredClassLoader` để loại class khỏi classpath của runner. |
| `@ConditionalOnProperty(... enabled=true)` | Property `demo.client.enabled=false` sẽ ngăn configuration. | Dùng `withPropertyValues`. |
| `@ConditionalOnMissingBean(Client.class)` | Có bean custom kiểu `Client` thì default method back off. | Dùng `withUserConfiguration` cung cấp custom bean. |
| `@AutoConfiguration(after = Core.class)` | Cấu hình được áp dụng sau Core trong danh sách auto-configuration. | Nạp cả hai bằng `AutoConfigurations.of` và kiểm tra hành vi phụ thuộc condition. |
| `@Bean` trả về `Client` | Nếu các condition khớp, bean có kiểu `Client` được đăng ký. | Kiểm tra bean theo tên và kiểu trong context. |

Một giả thuyết phải có **dấu hiệu bác bỏ**. Ví dụ: “khi property là false, bean không tồn tại” có thể được bác bỏ nếu bean vẫn có mặt. Khi đó, ta cần kiểm tra có bean cùng tên/kiểu từ user configuration, một auto-configuration khác, hay một đường đăng ký khác.

### Bảng đối chiếu ba lớp bằng chứng

| Lớp bằng chứng | Câu hỏi | Nguồn |
| --- | --- | --- |
| Candidate/discovery | Class có được Boot tìm thấy và không bị exclude? | Resource imports, dependency tree, exclusions, import filters. |
| Condition/registration | Class hoặc bean method có condition nào khớp? | Annotation và mã condition; ConditionEvaluationReport. |
| Runtime result | Bean nào thực sự có trong context và có tạo thành công? | `ApplicationContextRunner`, bean names/types, startup failure và dependency graph. |

Đừng gộp ba câu hỏi thành một. Một class có thể là candidate nhưng condition không khớp; condition class có thể khớp nhưng một bean method back off; method có thể được đăng ký nhưng instance tạo thất bại do dependency hoặc lỗi constructor.

## 5. Thí nghiệm tối thiểu với `ApplicationContextRunner`

`ApplicationContextRunner` là công cụ test của Spring Boot để tạo một `ApplicationContext` nhỏ, có thể kiểm soát cấu hình, property và user beans. Mỗi lần gọi `run` dựng một context cho tình huống test rồi đóng context sau callback.

Đây là cách phù hợp để kiểm chứng auto-configuration vì không cần khởi chạy toàn bộ ứng dụng, server HTTP, database hoặc các integration không liên quan. Test chỉ nạp các auto-configuration cần khảo sát.

Các khả năng thường dùng:

- `withConfiguration(AutoConfigurations.of(...))`: nạp các auto-configuration cần kiểm tra.
- `withPropertyValues(...)`: tạo biến thể environment.
- `withUserConfiguration(...)`: thêm cấu hình bean của ứng dụng.
- `withBean(...)`: thêm bean trực tiếp vào context thử nghiệm.
- `withClassLoader(new FilteredClassLoader(...))`: mô phỏng thiếu class/dependency tùy chọn.
- `withInitializer(ConditionEvaluationReportLoggingListener...)`: ghi Condition Evaluation Report ra log.

**Đừng tạo một test context lớn giống hệt ứng dụng ngay từ đầu.** Hãy tạo một context nhỏ nhất có thể tái hiện giả thuyết; sau khi xác nhận được từng condition, mới mở rộng test để thêm dependency hoặc cấu hình thực tế.

## 6. Ví dụ hoàn chỉnh: đọc condition rồi kiểm chứng bằng context

Ta dùng một auto-configuration giả định có hai lớp điều kiện:

1. Cấu hình chỉ bật khi `demo.feature.enabled=true`.
2. Bean default chỉ được đăng ký khi ứng dụng chưa cung cấp `FeatureClient`.

Ba thí nghiệm sẽ kiểm chứng ba trạng thái: property đúng và không có custom bean; property sai; property đúng nhưng user có custom bean.

### 6.1. Cấu trúc dự án

```text
source-context-lab/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── SourceVsContextTest.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>source-context-lab</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 6.2. File test hoàn chỉnh

Tạo `src/test/java/demo/SourceVsContextTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class SourceVsContextTest {

    record FeatureClient(String source) {
    }

    @AutoConfiguration
    @ConditionalOnProperty(
            prefix = "demo.feature",
            name = "enabled",
            havingValue = "true"
    )
    static class FeatureAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(FeatureClient.class)
        FeatureClient featureClient() {
            return new FeatureClient("default");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserConfiguration {

        @Bean
        FeatureClient customFeatureClient() {
            return new FeatureClient("custom");
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            FeatureAutoConfiguration.class
                    ));

    private static ConditionEvaluationReport.ConditionAndOutcomes outcomesFor(
            AssertableApplicationContext context, String sourceSuffix) {

        return ConditionEvaluationReport.get(context.getBeanFactory())
                .getConditionAndOutcomesBySource()
                .entrySet()
                .stream()
                .filter(entry -> entry.getKey().endsWith(sourceSuffix))
                .map(entry -> entry.getValue())
                .findFirst()
                .orElseThrow(() -> new AssertionError(
                        "No condition report entry ending with " + sourceSuffix
                ));
    }

    @Test
    void matchingPropertyRegistersDefaultBean() {
        runner.withPropertyValues("demo.feature.enabled=true")
                .run(context -> {
                    assertThat(context.getBeansOfType(FeatureClient.class))
                            .containsOnlyKeys("featureClient");

                    assertThat(context.getBean(FeatureClient.class).source())
                            .isEqualTo("default");

                    assertThat(outcomesFor(
                            context,
                            FeatureAutoConfiguration.class.getName()
                    ).isFullMatch()).isTrue();

                    assertThat(outcomesFor(
                            context,
                            FeatureAutoConfiguration.class.getName()
                                    + "#featureClient"
                    ).isFullMatch()).isTrue();
                });
    }

    @Test
    void propertyMismatchPreventsConfiguration() {
        runner.withPropertyValues("demo.feature.enabled=false")
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(FeatureClient.class);

                    assertThat(outcomesFor(
                            context,
                            FeatureAutoConfiguration.class.getName()
                    ).isFullMatch()).isFalse();
                });
    }

    @Test
    void userBeanMakesDefaultMethodBackOff() {
        runner.withPropertyValues("demo.feature.enabled=true")
                .withUserConfiguration(UserConfiguration.class)
                .run(context -> {
                    assertThat(context.getBeansOfType(FeatureClient.class))
                            .containsOnlyKeys("customFeatureClient");

                    assertThat(context.getBean(FeatureClient.class).source())
                            .isEqualTo("custom");

                    assertThat(outcomesFor(
                            context,
                            FeatureAutoConfiguration.class.getName()
                    ).isFullMatch()).isTrue();

                    assertThat(outcomesFor(
                            context,
                            FeatureAutoConfiguration.class.getName()
                                    + "#featureClient"
                    ).isFullMatch()).isFalse();
                });
    }
}
```

Chạy từ thư mục `source-context-lab` bằng JDK 17+ và Maven:

```bash
mvn test
```

**Kết quả mong đợi:** ba test thành công; Surefire thường báo tổng hợp `Tests run: 3, Failures: 0, Errors: 0, Skipped: 0`. Mã test không gọi `System.out.println` nên không có stdout nghiệp vụ cố định.

### 6.3. Đối chiếu kết quả với suy luận từ source

Trước khi chạy, ta đã đọc:

```java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.feature",
        name = "enabled",
        havingValue = "true"
)
static class FeatureAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(FeatureClient.class)
    FeatureClient featureClient() {
        return new FeatureClient("default");
    }
}
```

Từ mã nguồn, lập ba dự đoán:

| Thí nghiệm | Dự đoán từ source | Quan sát cần kiểm tra |
| --- | --- | --- |
| `enabled=true`, không user bean | Class condition khớp; method condition khớp; default được đăng ký. | Chỉ có `featureClient`, source `default`; hai report source full match. |
| `enabled=false` | Class condition không khớp; method không tạo default. | Không có `FeatureClient`; report class không full match. |
| `enabled=true`, có user bean | Class condition khớp; method condition thiếu bean không khớp. | Chỉ có `customFeatureClient`; report class full match nhưng method không full match. |

Đây là bằng chứng trực tiếp cho sự khác biệt giữa **condition trên class** và **condition trên bean method**. Trong trường hợp thứ ba, không phải toàn bộ auto-configuration bị loại; class-level property condition vẫn khớp, nhưng method `featureClient` back off vì user đã đăng ký bean cùng kiểu.

Helper `outcomesFor` đọc `ConditionEvaluationReport` từ đúng BeanFactory của test context. Report nhóm condition theo source; source có thể là tên configuration class hoặc `ClassName#methodName`. `isFullMatch()` cho biết mọi outcome được ghi cho source đó có khớp hay không. Nếu muốn đọc message chi tiết, có thể duyệt từng `ConditionAndOutcome` trong collection và xem condition/outcome tương ứng.

**Đừng chỉ assert context khởi động thành công.** Một context có thể khởi động dù auto-configuration không được áp dụng. Hãy kiểm tra cả bean name/type và condition report để chứng minh kết luận.

## 7. Bổ sung đúng một biến khi giả thuyết cần classpath hoặc web context

Sau khi test property và user bean đã rõ, mở rộng từng yếu tố riêng.

### 7.1. Giả lập class tùy chọn không có trên classpath

Spring Boot cung cấp `FilteredClassLoader`:

```java
runner.withClassLoader(new FilteredClassLoader(OptionalClientApi.class))
        .run(context -> {
            assertThat(context).doesNotHaveBean(OptionalClient.class);
        });
```

Đây là **đoạn minh họa** cần thêm class condition tương ứng vào auto-configuration. Nếu class optional được tham chiếu trong method signature, nên cô lập method đó trong nested configuration có `@ConditionalOnClass` để tránh nạp kiểu không có trên classpath. Thí nghiệm này mô phỏng một dependency vắng mặt; nó không thay thế kiểm tra runtime classpath thực tế của ứng dụng.

### 7.2. Condition chỉ dành cho web application

Nếu source có `@ConditionalOnWebApplication`, runner non-web mặc định có thể không đại diện đúng ứng dụng. Dùng `WebApplicationContextRunner` cho Servlet hoặc `ReactiveWebApplicationContextRunner` cho Reactive:

```java
new WebApplicationContextRunner()
        .withConfiguration(AutoConfigurations.of(WebFeatureAutoConfiguration.class))
        .run(context -> {
            assertThat(context).hasSingleBean(WebFeature.class);
        });
```

Đây là trích đoạn; `WebFeatureAutoConfiguration` cần có condition Servlet phù hợp. Không thêm web starter chỉ để ép một test thường thành web context nếu không cần.

### 7.3. Bật report logging trong runner

Có thể để Spring Boot ghi report khi test chạy:

```java
new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(
                        LogLevel.INFO
                )
        )
        .withConfiguration(
                AutoConfigurations.of(FeatureAutoConfiguration.class)
        )
        .run(context -> {
            // Assertions về bean và condition ở đây.
        });
```

Cần import `org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener` và `org.springframework.boot.logging.LogLevel`. Đây là trích đoạn bổ sung cho test; không phải cách duy nhất để xem report. Với test tự động, đọc `ConditionEvaluationReport` trực tiếp thường thuận tiện hơn so với so khớp chuỗi log.

## 8. Khi source và experiment không khớp, kiểm tra theo thứ tự

Nếu dự đoán không giống kết quả, không vội kết luận framework có bug. Đi theo các điểm sau:

1. **Version:** source JAR và dependency runtime có đúng cùng version không?
2. **Discovery:** class có nằm trong `AutoConfiguration.imports` của JAR thực sự được resolve không?
3. **Exclusion/filter:** class có bị `exclude`, `spring.autoconfigure.exclude` hoặc import filter loại không?
4. **Classloader:** class optional có thực sự nhìn thấy từ classloader mà context dùng không? Có nhiều version của dependency không?
5. **Environment:** property có bị profile, environment variable, command line hoặc test property override không? Kiểm tra cả `matchIfMissing` và `havingValue`.
6. **User bean:** bean đã được đăng ký trước condition chưa? Kiểu trả về khai báo có đủ thông tin không? Condition đang tìm theo type, name hay annotation?
7. **Order:** có auto-configuration khác đăng ký bean trước hoặc đặt `before/after` không?
8. **Context:** test có dùng đúng context loại Servlet/Reactive/non-web và đúng parent/child hierarchy không?
9. **Method-level condition:** class có thể match nhưng một method vẫn back off; tìm cả key `ClassName#methodName`.
10. **Instance creation:** condition đã match và definition đã đăng ký nhưng instance có thể lỗi do constructor, dependency, post-processor hoặc kết nối ngoài. Đọc startup exception và dependency graph.

Nếu cần thêm report vào log của ứng dụng thật, khởi chạy với `--debug`. Nếu Actuator được cấu hình, endpoint `/actuator/conditions` có thể cung cấp JSON condition report. Hãy xem đúng context và bảo vệ endpoint vận hành; không nên expose report nội bộ công khai chỉ để debug tạm thời.

## 9. Điều thí nghiệm tối thiểu chứng minh — và điều nó không chứng minh

| Thí nghiệm có thể chứng minh | Không tự động chứng minh |
| --- | --- |
| Với đúng classpath, property và user config của test, bean có/không có như assertion. | Ứng dụng production có cùng classpath, profile và property source. |
| Một condition source cụ thể full match hoặc không full match trong test context. | Mọi context trong JVM có cùng report hoặc cùng kết quả. |
| Một user bean khiến method-level `@ConditionalOnMissingBean` back off trong test. | Không có auto-configuration khác trong ứng dụng cũng tạo một bean tương tự. |
| Một optional class bị FilteredClassLoader che đi khiến nhánh tương ứng không khớp. | Dependency ngoài đời thực hoàn toàn không có ở mọi classloader. |
| Một Servlet/Reactive runner mô phỏng được loại context tương ứng. | Embedded server, security, network hoặc lifecycle của ứng dụng production hoạt động đầy đủ. |

Thí nghiệm context tối thiểu có giá trị vì nó **cô lập biến**. Khi test đã xác nhận một giả thuyết, hãy thêm dependency thật, property thật hoặc integration thật từng bước. Nếu chỉ chạy một `@SpringBootTest` lớn rồi thấy bean xuất hiện, ta biết kết quả tổng thể nhưng có thể khó biết chính xác condition nào đã quyết định.

## 10. Checklist thực hành khi đọc một auto-configuration

- [ ] Xác nhận version Spring Boot và artifact đang chạy.
- [ ] Tìm class trong `AutoConfiguration.imports` của JAR phù hợp.
- [ ] Kiểm tra exclusions, import filters và metadata liên quan.
- [ ] Đọc class-level condition trước nested configuration.
- [ ] Lần theo `@Import`, nested config và `before/after/order`.
- [ ] Đọc từng bean method, return type, bean name và method-level condition.
- [ ] Kiểm tra property source, defaults và optional dependencies.
- [ ] Viết giả thuyết có input và expected bean/report rõ ràng.
- [ ] Tạo `ApplicationContextRunner` nhỏ, một test case cho mỗi biến.
- [ ] Assert bean theo **tên và kiểu**, không chỉ assert context startup.
- [ ] Đọc `ConditionEvaluationReport` để đối chiếu source class/method.
- [ ] Khi cần, mở rộng bằng `FilteredClassLoader` hoặc web-specific runner.
- [ ] Nếu kết quả lệch, kiểm tra version, discovery, exclusions, classpath, property, user bean, order và context trước.

**Kết luận:** đọc mã nguồn cho ta giả thuyết về đường đi của auto-configuration; một context test nhỏ biến giả thuyết đó thành bằng chứng có thể lặp lại. Hãy kiểm tra đúng phiên bản, đúng resource imports, từng condition ở class và method, rồi tạo một `ApplicationContextRunner` kiểm soát property và user bean. Đối chiếu cả bean thực tế lẫn `ConditionEvaluationReport` sẽ giúp phân biệt **class không được nạp**, **condition không khớp**, **bean method back off** và **bean instance tạo thất bại**.

### Tài liệu tham khảo chính thức

- Spring Boot 3.3 — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 API — `AutoConfigurationImportSelector`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html
- Spring Boot 3.3 API — `@AutoConfiguration`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
- Spring Boot 3.3 API — `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
- Spring Boot 3.3 API — `ConditionEvaluationReport`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html
- Spring Boot 3.3 API — `ConditionEvaluationReport.ConditionAndOutcomes`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.ConditionAndOutcomes.html