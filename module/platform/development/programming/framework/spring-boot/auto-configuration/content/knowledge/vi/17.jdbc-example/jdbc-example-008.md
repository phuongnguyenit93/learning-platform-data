# Đọc điều kiện cấp class trước khi phân tích từng phương thức @Bean: ví dụ JDBC trong Spring Boot

## 1. Cách đọc auto-configuration từ ngoài vào trong

Một auto-configuration JDBC có thể cung cấp nhiều bean hạ tầng, nhưng chỉ khi context đáp ứng các điều kiện phù hợp. Khi đọc source, không nên bắt đầu ngay ở thân phương thức `@Bean`. Hãy đi theo thứ tự:

1. **Nguồn phát hiện:** class có được Spring Boot import từ `AutoConfiguration.imports` không?
2. **Metadata cấp class:** `@AutoConfiguration(before/after)`, các annotation `@Conditional...`, `@EnableConfigurationProperties` và `@Import` đang nói gì?
3. **Cấu hình được import:** mỗi nested/imported `@Configuration` có điều kiện riêng nào?
4. **Từng bean method:** tên bean, return type, condition riêng, tham số dependency và phần khởi tạo.
5. **Kết quả context:** bean nào được đăng ký, bean nào back off, và lý do.

Cách đọc này hữu ích với JDBC vì `JdbcTemplateAutoConfiguration` là class điều phối: nó khai báo các điều kiện chung và import những cấu hình con chứa phương thức tạo `JdbcTemplate` và `NamedParameterJdbcTemplate`.

**Phạm vi bài thực hành:** chỉ phân tích cơ chế auto-configuration và bean registration. Các ví dụ dùng `DataSource` giả lập; không mở kết nối, không chạy SQL, không tạo bảng, không viết repository hay nghiệp vụ truy vấn dữ liệu.

## 2. Xác nhận auto-configuration được phát hiện

Auto-configuration là một class cấu hình Spring được đánh dấu bằng `@AutoConfiguration`. Để Spring Boot tự phát hiện class trong JAR, tên đầy đủ của class phải được liệt kê trong file:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Ví dụ:

~~~text
com.acme.jdbc.autoconfigure.AcmeJdbcAutoConfiguration
~~~

Mỗi dòng là một class auto-configuration ứng viên. Việc có class trong classpath hoặc có annotation `@AutoConfiguration` trên source **không tự đảm bảo** class được import. Nó vẫn có thể bị exclude hoặc bị condition loại.

Trong Spring Boot 3.3, class public `org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration` được mô tả là auto-configuration cho `JdbcTemplate` và `NamedParameterJdbcTemplate`. Đây là điểm bắt đầu thực tế để luyện cách đọc từ annotation cấp class xuống các cấu hình được import.

## 3. Đọc annotation cấp class của JdbcTemplateAutoConfiguration

Metadata cấp class của Spring Boot 3.3 có thể tóm tắt như sau:

~~~java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
@ConditionalOnClass({
        DataSource.class,
        JdbcTemplate.class
})
@ConditionalOnSingleCandidate(DataSource.class)
@EnableConfigurationProperties(JdbcProperties.class)
@Import({
        DatabaseInitializationDependencyConfigurer.class,
        JdbcTemplateConfiguration.class,
        NamedParameterJdbcTemplateConfiguration.class
})
public class JdbcTemplateAutoConfiguration {
}
~~~

Đây là cách thể hiện phần metadata; các cấu hình được import mới chứa những bean method cụ thể. Đọc từng annotation trước khi mở method:

| Annotation | Câu hỏi cần trả lời | Ý nghĩa trong ví dụ JDBC |
| --- | --- | --- |
| `@AutoConfiguration(after = DataSourceAutoConfiguration.class)` | Cấu hình cần được xử lý sau class nào? | Yêu cầu xử lý sau `DataSourceAutoConfiguration` khi cả hai cùng là ứng viên. Đây là metadata **thứ tự**, không phải condition boolean. |
| `@ConditionalOnClass({DataSource.class, JdbcTemplate.class})` | Những type nào phải có trên classpath? | Cả JDBC `DataSource` và Spring `JdbcTemplate` phải có. Thiếu một type thì auto-configuration không phù hợp. |
| `@ConditionalOnSingleCandidate(DataSource.class)` | Context có thể chọn một `DataSource` candidate không? | Khớp khi có một candidate phù hợp, hoặc có nhiều candidate nhưng một bean được đánh dấu `@Primary`. |
| `@EnableConfigurationProperties(JdbcProperties.class)` | Properties class nào được bật? | Đăng ký bean cấu hình JDBC để template đọc các tùy chọn như fetch size, max rows và query timeout. |
| `@Import(...)` | Những cấu hình hỗ trợ nào được đưa vào? | Import dependency configurer, cấu hình tạo `JdbcTemplate` và cấu hình tạo `NamedParameterJdbcTemplate`. |

### Thứ tự không đồng nghĩa điều kiện tồn tại

`after = DataSourceAutoConfiguration.class` **không** có nghĩa `DataSourceAutoConfiguration` bắt buộc phải tạo được bean. Nó chỉ quy định thứ tự tương đối khi cả hai auto-configuration cùng tham gia.

Nếu ứng dụng tự khai báo `DataSource` và cấu hình tạo datasource mặc định back off, `JdbcTemplateAutoConfiguration` vẫn có thể tìm thấy bean do người dùng cung cấp, miễn các điều kiện khác khớp.

### Classpath không đồng nghĩa BeanFactory

`@ConditionalOnClass(DataSource.class)` kiểm tra type có trên classpath. Nó không chứng minh đã có bean `DataSource`.

`@ConditionalOnSingleCandidate(DataSource.class)` kiểm tra bean candidate trong context. Có thư viện JDBC trên classpath nhưng chưa có bean `DataSource` thì điều kiện candidate không khớp.

Đây là hai câu hỏi khác nhau, dù cùng nằm ở cấp class.

## 4. Đọc các cấu hình được import

Sau khi hiểu class điều phối, mở từng cấu hình trong `@Import`. Với JDBC, hai cấu hình quan trọng là `JdbcTemplateConfiguration` và `NamedParameterJdbcTemplateConfiguration`.

### 4.1. Cấu hình tạo JdbcTemplate

Trong Spring Boot 3.3, `JdbcTemplateConfiguration` là cấu hình con được import. Phần cốt lõi có dạng:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnMissingBean(JdbcOperations.class)
class JdbcTemplateConfiguration {

    @Bean
    @Primary
    JdbcTemplate jdbcTemplate(
            DataSource dataSource,
            JdbcProperties properties) {

        // Cấu hình fetch size, max rows, query timeout từ properties.
        // Lược giản phần thân để tập trung vào đăng ký bean.
        return new JdbcTemplate(dataSource);
    }
}
~~~

Điều kiện `@ConditionalOnMissingBean(JdbcOperations.class)` nằm trên **class cấu hình con**. Nếu context đã có bean triển khai `JdbcOperations`, cấu hình mặc định này back off. Khi cấu hình con được áp dụng, method `jdbcTemplate(...)` cung cấp bean `JdbcTemplate`.

Đọc method sau khi đã hiểu condition:
- Return type là `JdbcTemplate`, một kiểu cụ thể triển khai `JdbcOperations`.
- Tham số `DataSource` phải được giải quyết từ context.
- Tham số `JdbcProperties` cung cấp các tùy chọn cấu hình.
- `@Primary` đánh dấu bean này là candidate ưu tiên nếu có nhiều bean cùng type.
- Thân method chỉ tạo/cấu hình đối tượng template; ví dụ không gọi `query()` hoặc `update()`.

### 4.2. Cấu hình tạo NamedParameterJdbcTemplate

Cấu hình con thứ hai có thể tóm tắt:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnSingleCandidate(JdbcTemplate.class)
@ConditionalOnMissingBean(NamedParameterJdbcOperations.class)
class NamedParameterJdbcTemplateConfiguration {

    @Bean
    @Primary
    NamedParameterJdbcTemplate namedParameterJdbcTemplate(
            JdbcTemplate jdbcTemplate) {

        return new NamedParameterJdbcTemplate(jdbcTemplate);
    }
}
~~~

Có hai condition ở cấp **cấu hình con**:
- `@ConditionalOnSingleCandidate(JdbcTemplate.class)`: phải chọn được một `JdbcTemplate` candidate.
- `@ConditionalOnMissingBean(NamedParameterJdbcOperations.class)`: chưa có implementation phù hợp do ứng dụng cung cấp.

Khi cấu hình con được áp dụng, method `namedParameterJdbcTemplate(...)` nhận `JdbcTemplate` làm dependency và tạo wrapper `NamedParameterJdbcTemplate`. Ví dụ không thực hiện câu lệnh SQL nào.

### 4.3. Luồng điều kiện tổng quát

~~~mermaid
flowchart TD
    A["JdbcTemplateAutoConfiguration"] --> B{"Có DataSource và JdbcTemplate trên classpath?"}
    B -->|"Không"| X["Auto-configuration không phù hợp"]
    B -->|"Có"| C{"Có một DataSource candidate?"}
    C -->|"Không"| X
    C -->|"Có"| D["Import các cấu hình con"]
    D --> E{"Thiếu JdbcOperations?"}
    E -->|"Có"| F["Đăng ký JdbcTemplate"]
    E -->|"Không"| G["Dùng bean JdbcOperations hiện có"]
    F --> H{"Có một JdbcTemplate và thiếu NamedParameterJdbcOperations?"}
    G --> H
    H -->|"Có"| I["Đăng ký NamedParameterJdbcTemplate"]
    H -->|"Không"| J["Không tạo NamedParameterJdbcTemplate mặc định"]
~~~

Sơ đồ diễn giải các cổng điều kiện chính. Cấu hình thực tế còn import dependency configurer và có metadata khác; sơ đồ không thay thế việc đọc source của từng cấu hình.

## 5. Phân biệt class-level và method-level condition

Một condition có thể xuất hiện trên class cấu hình hoặc trên một method `@Bean`. Trước khi kết luận bean nào bị ảnh hưởng, hãy xác định annotation đang gắn vào phần tử nào.

| Vị trí | Phạm vi cần xem xét | Ví dụ |
| --- | --- | --- |
| `@AutoConfiguration` | Auto-configuration class | `@ConditionalOnClass`, `@ConditionalOnSingleCandidate(DataSource.class)` |
| Imported `@Configuration` | Một nhóm bean trong cấu hình con | `@ConditionalOnMissingBean(JdbcOperations.class)` |
| `@Bean` method | Bean definition do method cung cấp | `@ConditionalOnProperty` hoặc `@ConditionalOnMissingBean` gắn trực tiếp vào method |
| Tham số method | Dependency cần để tạo bean | `DataSource`, `JdbcProperties`, `JdbcTemplate` |

**Không gộp mọi condition thành cùng một loại.** `@ConditionalOnClass` là classpath condition. `@ConditionalOnProperty` kiểm tra `Environment`. `@ConditionalOnBean` và `@ConditionalOnMissingBean` kiểm tra bean đã được xử lý trong context. Chúng có semantics và phase đánh giá khác nhau.

Spring Boot lưu ý `@ConditionalOnBean` và `@ConditionalOnMissingBean` không đơn giản ngăn configuration class được tạo. Khi đặt ở cấp class, điều kiện ảnh hưởng tới việc đăng ký chính configuration class như một bean; khi đặt ở method, điều kiện gắn trực tiếp vào bean method. Vì vậy phải đọc đúng JavaDoc của annotation, vị trí gắn và kết quả thực tế trong context.

Với auto-configuration thư viện:
- Nếu chỉ một bean mặc định cần back off, đặt `@ConditionalOnMissingBean` trên method tương ứng thường thể hiện ý định rõ.
- Nếu một nhóm cấu hình con chỉ có ý nghĩa khi prerequisite có mặt, có thể tổ chức thành nested configuration và đặt condition có chủ đích.
- Nếu muốn bảo vệ optional library trên classpath, dùng classpath condition ở cấu hình bao quanh phù hợp; đừng chỉ dựa vào method condition có signature tham chiếu type tùy chọn.

## 6. Cách đọc từng phương thức @Bean

Sau khi hiểu class-level metadata và các cấu hình con, đọc từng method theo năm mục:

1. **Tên bean:** method name mặc định là bean name nếu không đặt tên khác.
2. **Return type:** Spring dùng type metadata này để nhận diện bean và đánh giá một số bean conditions.
3. **Method annotations:** condition nào gắn trực tiếp vào method? Có `@Primary`, `@Qualifier` hoặc scope không?
4. **Tham số:** method yêu cầu dependency nào? Các dependency này có được cung cấp bởi cấu hình đã qua điều kiện không?
5. **Thân method:** method chỉ lắp ráp object hay tạo side effect như mở kết nối, đọc file, gọi network?

Ví dụ minh họa:

~~~java
@Bean
@ConditionalOnMissingBean(ReportFormatter.class)
DefaultReportFormatter reportFormatter(JdbcProperties properties) {
    return new DefaultReportFormatter(properties.getTemplate());
}
~~~

Đây là ví dụ độc lập, không phải method gốc của Spring Boot. Condition ở method yêu cầu chưa có bean `ReportFormatter`. Return type cụ thể `DefaultReportFormatter` cung cấp type metadata rõ ràng; tham số `JdbcProperties` phải được đăng ký trước.

Tránh viết:

~~~java
@Bean
@ConditionalOnMissingBean
Object reportFormatter(JdbcProperties properties) {
    return new DefaultReportFormatter(properties.getTemplate());
}
~~~

Ở dạng này, method chỉ bộc lộ return type `Object`. Khi condition mặc định suy luận target type từ method, metadata quá chung có thể khiến điều kiện không nhận ra contract thực. Hãy khai báo return type cụ thể nhất phù hợp.

## 7. Ma trận kết quả cho ví dụ JDBC

Giả sử `DataSource` và `JdbcTemplate` đều có trên classpath, và chưa có bean `NamedParameterJdbcOperations` do người dùng khai báo:

| Bean DataSource trong context | Class condition `@ConditionalOnSingleCandidate(DataSource.class)` | Kết quả với JdbcTemplate mặc định |
| --- | --- | --- |
| Không có `DataSource` | Không khớp | Không có `JdbcTemplate` do cấu hình này tạo |
| Một `DataSource` | Khớp | Có thể tạo `JdbcTemplate` nếu chưa có `JdbcOperations` từ người dùng |
| Hai `DataSource`, không có `@Primary` | Không khớp | Không tự chọn datasource tùy ý; không tạo template qua nhánh này |
| Hai `DataSource`, đúng một bean `@Primary` | Khớp | Có thể tạo template dùng candidate primary |

Sau khi class-level condition khớp, điều kiện của cấu hình con tiếp tục quyết định:
- Đã có `JdbcOperations` thì cấu hình tạo template mặc định back off.
- Có một `JdbcTemplate` candidate và chưa có `NamedParameterJdbcOperations` thì cấu hình named-parameter có thể đăng ký bean.
- Nếu người dùng cung cấp sẵn `NamedParameterJdbcOperations`, bean mặc định tương ứng back off.
- Class JDBC có trên classpath không thay thế cho `DataSource` bean; `DataSource` bean không bảo đảm template mặc định được tạo nếu có bean tùy chỉnh làm condition back off.

## 8. Test Spring Boot 3.3: kiểm tra đăng ký bean, không chạy truy vấn

Dùng `ApplicationContextRunner` để kiểm tra các nhánh cấu hình. `Mockito.mock(DataSource.class)` tạo datasource giả; các test chỉ kiểm tra bean registration và dependency injection. Chúng không gọi phương thức truy vấn, không mở connection và không cần database thật.

Tạo file `src/test/java/com/example/demo/JdbcAutoConfigurationConditionsTest.java`. Project cần Java 17+, Spring Boot 3.3, `spring-boot-starter-jdbc` và `spring-boot-starter-test`:

~~~java
package com.example.demo;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

class JdbcAutoConfigurationConditionsTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    JdbcTemplateAutoConfiguration.class));

    @Test
    void noDataSourceMeansJdbcTemplateAutoConfigurationDoesNotMatch() {
        runner.run(context -> {
            assertThat(context).doesNotHaveBean(JdbcTemplate.class);
            assertThat(context).doesNotHaveBean(
                    NamedParameterJdbcTemplate.class);
        });
    }

    @Test
    void oneDataSourceAllowsBothTemplateBeans() {
        runner.withUserConfiguration(OneDataSourceConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(DataSource.class);
                    assertThat(context).hasSingleBean(JdbcTemplate.class);
                    assertThat(context).hasSingleBean(
                            NamedParameterJdbcTemplate.class);
                });
    }

    @Test
    void multipleDataSourcesWithoutPrimaryDoNotSelectOneAutomatically() {
        runner.withUserConfiguration(TwoDataSourcesConfiguration.class)
                .run(context -> {
                    assertThat(context).hasBean("firstDataSource");
                    assertThat(context).hasBean("secondDataSource");
                    assertThat(context).doesNotHaveBean(JdbcTemplate.class);
                    assertThat(context).doesNotHaveBean(
                            NamedParameterJdbcTemplate.class);
                });
    }

    @Test
    void primaryDataSourceResolvesTheSingleCandidateCondition() {
        runner.withUserConfiguration(
                TwoDataSourcesWithPrimaryConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(JdbcTemplate.class);
                    assertThat(context).hasSingleBean(
                            NamedParameterJdbcTemplate.class);
                    assertThat(context.getBean(DataSource.class))
                            .isSameAs(context.getBean("primaryDataSource"));
                });
    }

    @Test
    void userJdbcTemplateMakesDefaultJdbcOperationsBackOff() {
        runner.withUserConfiguration(UserJdbcTemplateConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(JdbcTemplate.class);
                    assertThat(context.getBean(JdbcTemplate.class))
                            .isSameAs(context.getBean("customJdbcTemplate"));
                    assertThat(context).hasSingleBean(
                            NamedParameterJdbcTemplate.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class OneDataSourceConfiguration {

        @Bean
        DataSource dataSource() {
            return Mockito.mock(DataSource.class);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TwoDataSourcesConfiguration {

        @Bean
        DataSource firstDataSource() {
            return Mockito.mock(DataSource.class);
        }

        @Bean
        DataSource secondDataSource() {
            return Mockito.mock(DataSource.class);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TwoDataSourcesWithPrimaryConfiguration {

        @Bean
        @Primary
        DataSource primaryDataSource() {
            return Mockito.mock(DataSource.class);
        }

        @Bean
        DataSource secondaryDataSource() {
            return Mockito.mock(DataSource.class);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserJdbcTemplateConfiguration {

        @Bean
        DataSource dataSource() {
            return Mockito.mock(DataSource.class);
        }

        @Bean
        JdbcTemplate customJdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }
    }
}
~~~

Chạy trong project Gradle đã cấu hình dependency:

~~~bash
./gradlew test --tests "com.example.demo.JdbcAutoConfigurationConditionsTest"
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test --tests "com.example.demo.JdbcAutoConfigurationConditionsTest"
~~~

**Kết quả kỳ vọng:** 5 test PASS:
- Test 1: thiếu `DataSource` nên class-level candidate condition không khớp.
- Test 2: một `DataSource` đáp ứng điều kiện; hai template bean được đăng ký.
- Test 3: hai datasource không có primary; không có candidate duy nhất.
- Test 4: hai datasource nhưng một bean primary; điều kiện candidate khớp.
- Test 5: ứng dụng cung cấp `JdbcTemplate`; cấu hình mặc định không tạo thêm template, còn named-parameter configuration vẫn có thể dùng candidate hiện có.

Đây là ví dụ test được thiết kế để chạy khi dependency đúng; các test chưa được thực thi trong project cụ thể ở lượt này.

## 9. Chẩn đoán bằng Condition Evaluation Report

Khi context không có bean như mong đợi, bật `--debug` khi chạy ứng dụng hoặc `debug=true` để xem Condition Evaluation Report.

Một báo cáo JDBC có thể có cấu trúc như sau:

~~~text
JdbcTemplateAutoConfiguration:
  @ConditionalOnClass found required classes
  @ConditionalOnSingleCandidate found a single bean 'dataSource'

JdbcTemplateConfiguration:
  @ConditionalOnMissingBean found no beans of type JdbcOperations

NamedParameterJdbcTemplateConfiguration:
  @ConditionalOnSingleCandidate found a single bean 'jdbcTemplate'
  @ConditionalOnMissingBean found no beans of type NamedParameterJdbcOperations
~~~

Đây là **ví dụ minh họa cấu trúc báo cáo**, không phải stdout cố định. Tên bean và thông điệp match/no-match thay đổi theo context.

Trong test có thể thêm listener:

~~~java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;

new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(
                        LogLevel.INFO))
        .run(context -> {
            // assertions về bean cần kiểm tra
        });
~~~

Khi đọc report, kiểm tra theo thứ tự:
1. `JdbcTemplateAutoConfiguration` có được import không?
2. `@ConditionalOnClass` có tìm thấy cả `DataSource` và `JdbcTemplate`?
3. `@ConditionalOnSingleCandidate(DataSource.class)` tìm thấy bao nhiêu candidate? Có primary không?
4. Cấu hình con `JdbcTemplateConfiguration` có back off vì đã có `JdbcOperations`?
5. `NamedParameterJdbcTemplateConfiguration` có một `JdbcTemplate` candidate không?
6. Đã có `NamedParameterJdbcOperations` do ứng dụng cung cấp chưa?

Đừng kết luận lỗi nằm trong thân method trước khi biết method có được đăng ký hay không.

## 10. Nhầm lẫn thường gặp khi đọc auto-configuration JDBC

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| Có dependency Spring JDBC là có bean `JdbcTemplate` | Classpath condition mới chỉ là một cổng; còn cần candidate `DataSource` và các condition của cấu hình con. |
| `after = DataSourceAutoConfiguration.class` đồng nghĩa phải dùng datasource do Boot tạo | Đây là ordering metadata; datasource do người dùng cung cấp vẫn có thể thỏa bean condition. |
| Nhiều `DataSource` thì Spring tự chọn một bean bất kỳ | `@ConditionalOnSingleCandidate` cần một candidate duy nhất hoặc một primary rõ ràng. |
| `@ConditionalOnMissingBean(JdbcOperations.class)` kiểm tra classpath | Nó kiểm tra bean trong context theo type được chỉ định. |
| Class-level condition và method-level condition luôn có cùng semantics | Phạm vi và thời điểm đánh giá tùy loại condition; đọc annotation cụ thể và đúng phần tử được gắn. |
| Tạo `JdbcTemplate` nghĩa là đã kết nối database | Đăng ký bean không đồng nghĩa đã mở connection hay chạy truy vấn. |
| Có bean `JdbcTemplate` là chắc chắn có `NamedParameterJdbcTemplate` | Còn phải thỏa candidate condition và missing-bean condition của cấu hình named-parameter. |
| Method có tham số `DataSource` nên tự tạo datasource | Tham số là dependency cần resolve; nó không tự đăng ký bean. |
| Thứ tự tạo bean luôn trùng thứ tự auto-configuration | Ordering điều khiển thứ tự định nghĩa bean; instance được tạo theo dependency và lifecycle. |
| Context khởi động thành công chứng minh mọi bean đã được đăng ký | Bean có thể bị condition bỏ qua mà context vẫn khởi động; test phải assert bean có/không. |

## 11. Checklist review một auto-configuration class

1. **Nguồn import:** xác nhận class có trong `AutoConfiguration.imports` hoặc được import tường minh trong test.
2. **Ordering:** `before`/`after` ảnh hưởng thứ tự xử lý, không phải điều kiện tồn tại bean.
3. **Classpath conditions:** type tùy chọn nào phải có? Có method signature tham chiếu type không luôn có trên runtime classpath không?
4. **Bean conditions cấp class:** điều kiện kiểm tra bean type/name nào, và semantics cấp class của annotation là gì?
5. **Property/web/resource conditions:** toàn bộ cấu hình hay chỉ một phần phụ thuộc môi trường?
6. **Nested/imported configuration:** mở từng class con, lặp lại bước 2–5.
7. **Mỗi `@Bean`:** ghi tên, return type, method conditions, tham số và phần thân.
8. **Back-off:** bean do người dùng cung cấp có ngăn bean mặc định được tạo không?
9. **Test matrix:** classpath có/không, prerequisite bean có/không, một/nhiều candidate, primary và user override.
10. **Condition report:** xác nhận lý do match/no-match thay vì suy đoán từ source.

## Tài liệu tham khảo chính thức

- [Spring Boot 3.3.13 — `JdbcTemplateAutoConfiguration` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/JdbcTemplateAutoConfiguration.html): annotation cấp class, classpath, candidate `DataSource`, properties và các cấu hình được import.
- [Spring Boot 3.3.13 — `DataSourceAutoConfiguration` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceAutoConfiguration.html): các điều kiện cấp class của datasource auto-configuration.
- [Spring Boot 3.3.13 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): class conditions, bean conditions, semantics class/method, `ApplicationContextRunner` và Condition Evaluation Report.
- [Spring Boot 3.3.13 — `@ConditionalOnSingleCandidate` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnSingleCandidate.html): điều kiện một candidate hoặc một primary candidate.
- [Spring Boot 3.3.13 — `@ConditionalOnMissingBean` JavaDoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): đăng ký mặc định theo bean absence.
