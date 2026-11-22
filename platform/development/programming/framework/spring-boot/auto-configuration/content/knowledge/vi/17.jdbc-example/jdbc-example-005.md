# Nhiều DataSource, ứng viên chính và điều kiện của JdbcTemplateAutoConfiguration

## Mục tiêu học tập

Trong một ứng dụng Spring Boot dùng JDBC, chỉ có một `DataSource` thì việc tạo `JdbcTemplate` thường diễn ra tự động. Nhưng khi ứng dụng có nhiều cơ sở dữ liệu — ví dụ database giao dịch và database báo cáo — Spring phải biết **DataSource nào là ứng viên mặc định** để một dependency theo kiểu `DataSource` có thể được inject mà không mơ hồ.

Bài học này truy vết cách `JdbcTemplateAutoConfiguration` quyết định có được áp dụng hay không, tập trung vào `@ConditionalOnSingleCandidate(DataSource.class)`, `@Primary`, các cấu hình được `@Import` và điều kiện back-off khi người dùng đã tự khai báo JDBC bean.

Sau bài học, bạn có thể:

- Giải thích vì sao một `DataSource` thường đủ để auto-configure `JdbcTemplate`.
- Dự đoán kết quả khi có hai `DataSource` không có `@Primary`, có đúng một `@Primary`, hoặc có nhiều bean cùng được đánh dấu `@Primary`.
- Phân biệt `@Primary` với `@Qualifier` và hiểu giới hạn của mỗi annotation.
- Đọc các điều kiện và cấu hình con được import bởi `JdbcTemplateAutoConfiguration`.
- Biết khi nào `JdbcTemplate` mặc định được tạo, khi nào cấu hình mặc định back off và cách tự khai báo template cho từng database.
- Kiểm chứng các nhánh bằng `ApplicationContextRunner` mà không cần kết nối đến database thật.

## 1. Từ DataSource đến JdbcTemplate

`DataSource` là abstraction của JDBC dùng để lấy kết nối đến database. `JdbcTemplate` của Spring JDBC nhận một `DataSource` và cung cấp API thao tác SQL, quản lý vòng đời JDBC resource và chuyển đổi các lỗi JDBC sang hệ thống exception của Spring.

Một ứng dụng đơn giản thường chỉ có một `DataSource`:

~~~java
@Bean
DataSource dataSource() {
    // Cấu hình pool/connection của ứng dụng
}
~~~

Khi các thư viện JDBC cần một `DataSource`, việc inject theo kiểu có một ứng viên duy nhất là rõ ràng. Spring Boot có thể tự cấu hình `JdbcTemplate` dựa trên DataSource đó.

Nhưng với hai database:

- `ordersDataSource`: database giao dịch.
- `reportingDataSource`: database báo cáo.

Một phương thức nhận `DataSource` mà không có qualifier sẽ không biết nên chọn bean nào. Spring Boot không thể tự đoán database nghiệp vụ mà ứng dụng muốn dùng. Đây là lý do có điều kiện **single candidate**.

## 2. JdbcTemplateAutoConfiguration kiểm tra những gì?

Trong Spring Boot 3.3, lớp `org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration` có cấu trúc annotation chính như sau:

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

Đây là **trích đoạn cấu trúc để đọc source**, không phải class người dùng cần tự khai báo. Các lớp cấu hình con được Spring Boot cung cấp trong package auto-configuration.

Có năm điểm cần nhận ra:

1. **`@AutoConfiguration(after = DataSourceAutoConfiguration.class)`:** xử lý sau auto-configuration tạo/cung cấp DataSource mặc định. Condition cần nhìn thấy các bean definitions DataSource đã được xử lý.
2. **`@ConditionalOnClass`:** chỉ xét cấu hình nếu cả `javax.sql.DataSource` và `org.springframework.jdbc.core.JdbcTemplate` có trên classpath.
3. **`@ConditionalOnSingleCandidate(DataSource.class)`:** phải có một ứng viên DataSource duy nhất có thể xác định cho injection theo kiểu. Nếu có nhiều bean, một primary candidate duy nhất có thể làm điều kiện khớp.
4. **`@EnableConfigurationProperties(JdbcProperties.class)`:** đăng ký cấu hình các thuộc tính liên quan đến JDBC template.
5. **`@Import`:** đưa các cấu hình hỗ trợ vào quá trình xử lý, gồm cấu hình `JdbcTemplate`, `NamedParameterJdbcTemplate` và dependency liên quan đến database initialization.

Điều kiện quan trọng nhất trong bài này là `@ConditionalOnSingleCandidate(DataSource.class)`. Nếu điều kiện trên **class chính** không khớp, các cấu hình con được import trong class này cũng không được áp dụng qua đường auto-configuration đó.

## 3. @ConditionalOnSingleCandidate có nghĩa gì?

Annotation thuộc package:

~~~java
org.springframework.boot.autoconfigure.condition
~~~

Điều kiện khớp khi:

- Có bean thuộc kiểu đang kiểm tra trong `BeanFactory`.
- Có thể xác định **một ứng viên duy nhất** cho việc autowire một dependency đơn theo kiểu đó.

Trường hợp phổ biến:

- Chỉ có một `DataSource`: điều kiện khớp.
- Có nhiều `DataSource`, nhưng đúng một bean được đánh dấu `@Primary`: điều kiện vẫn khớp.
- Có nhiều `DataSource`, không có primary: không có ứng viên duy nhất, điều kiện không khớp.
- Có nhiều bean cùng được đánh dấu primary: không thể chọn một primary duy nhất, điều kiện không khớp.

### Bảng quyết định

| Các bean DataSource trong context | Có single candidate? | JdbcTemplateAutoConfiguration |
| --- | --- | --- |
| Không có DataSource | Không | Không áp dụng |
| Một DataSource | Có | Có thể áp dụng nếu các điều kiện khác khớp |
| Hai DataSource, không có `@Primary` | Không | Không áp dụng |
| Hai DataSource, đúng một `@Primary` | Có | Có thể áp dụng |
| Ba DataSource, đúng một `@Primary` | Có | Có thể áp dụng |
| Hai DataSource, cả hai đều `@Primary` | Không | Không áp dụng |

Bảng giả định các bean đều là ứng viên autowire phù hợp. Các thuộc tính như `autowireCandidate=false`, bean definition không phải default candidate và context hierarchy có thể ảnh hưởng quá trình tìm ứng viên; chúng là trường hợp nâng cao, không nên dùng để thay thế một thiết kế DataSource rõ ràng.

**Lưu ý:** `@ConditionalOnSingleCandidate` chỉ nhìn thấy những bean definitions đã được xử lý tại thời điểm condition được đánh giá. Vì vậy, nếu một auto-configuration khác tạo DataSource, thứ tự auto-configuration phải cho phép DataSource được đăng ký trước. Đây cũng là lý do `JdbcTemplateAutoConfiguration` khai báo chạy sau `DataSourceAutoConfiguration`.

## 4. @Primary và @Qualifier giải quyết hai vấn đề khác nhau

### 4.1. @Primary: chọn ứng viên mặc định theo kiểu

`@Primary` đánh dấu một bean là lựa chọn ưu tiên khi Spring cần inject **một giá trị đơn** trong số nhiều bean cùng kiểu.

~~~java
@Configuration(proxyBeanMethods = false)
class DataSourceConfiguration {

    @Bean
    @Primary
    DataSource ordersDataSource() {
        return createOrdersDataSource();
    }

    @Bean
    DataSource reportingDataSource() {
        return createReportingDataSource();
    }
}
~~~

Trong ví dụ, khi một phương thức nhận `DataSource` mà không có qualifier, Spring chọn `ordersDataSource`. Đối với `@ConditionalOnSingleCandidate(DataSource.class)`, primary candidate giúp điều kiện xác định được một ứng viên duy nhất dù context có nhiều DataSource.

`@Primary` **không xóa** các bean còn lại. `reportingDataSource` vẫn tồn tại và vẫn có thể được inject bằng qualifier. Khi inject `List<DataSource>` hoặc `Map<String, DataSource>`, Spring vẫn cung cấp các ứng viên phù hợp; `@Primary` không lọc collection xuống còn một bean.

### 4.2. @Qualifier: chọn bean cụ thể tại điểm inject

Khi cần database báo cáo, hãy chỉ định bean bằng tên/qualifier:

~~~java
@Service
class ReportRepository {

    private final JdbcTemplate jdbcTemplate;

    ReportRepository(
            @Qualifier("reportingJdbcTemplate")
            JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }
}
~~~

Qualifier thu hẹp tập ứng viên tại **điểm injection cụ thể**. Nó không tự đánh dấu DataSource làm primary và không thay đổi điều kiện class-level `@ConditionalOnSingleCandidate(DataSource.class)`.

Vì vậy, nếu có hai DataSource không có primary, việc một service khác dùng `@Qualifier("ordersDataSource")` không tự khiến `JdbcTemplateAutoConfiguration` khớp. Condition của auto-configuration đang xét kiểu DataSource trên toàn context; nó không biết qualifier của mọi điểm injection trong ứng dụng.

### 4.3. Dùng cả hai trong ứng dụng nhiều database

Một thiết kế phổ biến:

- Đánh dấu DataSource mặc định bằng `@Primary` để các auto-configuration dùng một ứng viên mặc định.
- Dùng `@Qualifier` cho các service hoặc template gắn với database phụ.
- Nếu cần một `JdbcTemplate` cho từng DataSource, khai báo rõ các template và qualifier tương ứng.

## 5. Cấu hình hai DataSource với một primary

Spring Boot khuyến nghị đánh dấu một DataSource là `@Primary` khi cấu hình nhiều DataSource, vì các auto-configuration phía sau thường cần inject một ứng viên theo kiểu.

Ví dụ production dưới đây dùng `DataSourceProperties` để bind URL, username, password và dùng HikariCP làm connection pool.

**Tệp:** `src/main/java/example/jdbc/DataSourcesConfiguration.java`

~~~java
package example.jdbc;

import com.zaxxer.hikari.HikariDataSource;

import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

@Configuration(proxyBeanMethods = false)
class DataSourcesConfiguration {

    @Bean
    @Primary
    @ConfigurationProperties("app.datasource.orders")
    DataSourceProperties ordersDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @Primary
    @ConfigurationProperties("app.datasource.orders.configuration")
    HikariDataSource ordersDataSource(
            DataSourceProperties ordersDataSourceProperties) {
        return ordersDataSourceProperties.initializeDataSourceBuilder()
                .type(HikariDataSource.class)
                .build();
    }

    @Bean
    @ConfigurationProperties("app.datasource.reporting")
    DataSourceProperties reportingDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @ConfigurationProperties("app.datasource.reporting.configuration")
    HikariDataSource reportingDataSource(
            @Qualifier("reportingDataSourceProperties")
            DataSourceProperties reportingDataSourceProperties) {
        return reportingDataSourceProperties.initializeDataSourceBuilder()
                .type(HikariDataSource.class)
                .build();
    }
}
~~~

Các import không sử dụng có thể bỏ khi đặt code vào dự án; đoạn trên minh họa đầy đủ các kiểu cần thiết. Không cần `@EnableConfigurationProperties` ở đây vì hai `DataSourceProperties` được đăng ký trực tiếp bằng `@Bean`.

Cấu hình YAML tương ứng:

~~~yaml
app:
  datasource:
    orders:
      url: jdbc:postgresql://localhost:5432/orders
      username: app
      password: change-me
      configuration:
        maximum-pool-size: 20

    reporting:
      url: jdbc:postgresql://localhost:5432/reporting
      username: report
      password: change-me
      configuration:
        maximum-pool-size: 5
~~~

Các giá trị kết nối chỉ là ví dụ minh họa; cung cấp credential từ secret/configuration phù hợp trong môi trường thực tế.

`DataSourceProperties.initializeDataSourceBuilder()` giúp xử lý việc chuyển `url` sang thuộc tính phù hợp của connection pool như Hikari `jdbcUrl`. Cách này tránh phải tự viết logic chuyển đổi và giúp hai DataSource có namespace riêng.

### Vì sao DataSourceProperties đầu tiên cũng có @Primary?

Trong ví dụ, cả `ordersDataSourceProperties` và `ordersDataSource` được đánh dấu `@Primary`. DataSource primary giúp các injection theo kiểu `DataSource` xác định được ứng viên; properties primary giúp các thành phần như database initialization chọn đúng bộ properties mặc định khi cần.

### DataSourceAutoConfiguration có còn tạo DataSource mặc định không?

Khi ứng dụng tự khai báo DataSource, DataSource auto-configuration sẽ back off theo điều kiện của nó. Ở đây hai DataSource đã do ứng dụng quản lý, nên không nên kỳ vọng Boot tạo thêm một DataSource thứ ba từ `spring.datasource.*`.

Tuy nhiên, điều đó **không đồng nghĩa** `JdbcTemplateAutoConfiguration` cũng phải back off. Nếu context có nhiều DataSource nhưng đúng một primary candidate, điều kiện `@ConditionalOnSingleCandidate(DataSource.class)` vẫn có thể khớp và Boot có thể tạo `JdbcTemplate` mặc định cho DataSource primary.

## 6. JdbcTemplateConfiguration: khi nào template mặc định được tạo?

`JdbcTemplateAutoConfiguration` import cấu hình con `JdbcTemplateConfiguration`. Trong Spring Boot 3.3, cấu hình này sử dụng điều kiện thiếu bean `JdbcOperations`:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnMissingBean(JdbcOperations.class)
static class JdbcTemplateConfiguration {

    @Bean
    @Primary
    JdbcTemplate jdbcTemplate(
            DataSource dataSource,
            JdbcProperties properties) {

        JdbcTemplate template = new JdbcTemplate(dataSource);

        JdbcProperties.Template settings = properties.getTemplate();
        template.setFetchSize(settings.getFetchSize());
        template.setMaxRows(settings.getMaxRows());

        if (settings.getQueryTimeout() != null) {
            template.setQueryTimeout(
                    (int) settings.getQueryTimeout().getSeconds());
        }

        return template;
    }
}
~~~

Đây là **đoạn source rút gọn để giải thích cơ chế**. Class/package access modifier trong source thực tế có thể không cho ứng dụng bên ngoài gọi trực tiếp.

Các điểm quan trọng:

- Điều kiện được kiểm tra theo **interface `JdbcOperations`**, mà `JdbcTemplate` triển khai.
- Nếu context đã có bean `JdbcOperations` phù hợp, cấu hình mặc định này back off.
- Nếu không có bean như vậy, phương thức `jdbcTemplate` tạo một `JdbcTemplate`.
- Bean mặc định được đánh dấu `@Primary`.
- Tham số `DataSource` được inject theo kiểu; khi có nhiều DataSource và một primary, template mặc định dùng DataSource primary.

**Điều kiện missing bean không chỉ đếm bean có tên `jdbcTemplate`.** Một implementation khác của `JdbcOperations` cũng có thể khiến cấu hình mặc định không được áp dụng. Mục tiêu là tôn trọng một JDBC operations implementation mà ứng dụng đã cung cấp.

### Trường hợp người dùng tự tạo JdbcTemplate

~~~java
@Bean
JdbcTemplate customJdbcTemplate(
        @Qualifier("ordersDataSource") DataSource dataSource) {
    return new JdbcTemplate(dataSource);
}
~~~

Vì `JdbcTemplate` triển khai `JdbcOperations`, bean này làm điều kiện `@ConditionalOnMissingBean(JdbcOperations.class)` không khớp. Boot sẽ không tạo thêm `JdbcTemplate` mặc định.

Nếu ứng dụng có hai DataSource và chỉ tạo một custom template cho database phụ, đừng kỳ vọng Boot vẫn tự tạo một template thứ hai cho primary. Điều kiện missing bean được áp dụng cho cấu hình mặc định nói chung, không phải riêng từng DataSource. Nếu muốn cả hai template, hãy khai báo rõ cả hai.

## 7. NamedParameterJdbcTemplate có điều kiện riêng

`JdbcTemplateAutoConfiguration` cũng import `NamedParameterJdbcTemplateConfiguration`. Cấu hình này tạo `NamedParameterJdbcTemplate` khi:

- Có một ứng viên `JdbcTemplate` duy nhất (hoặc nhiều bean nhưng xác định được một primary candidate).
- Chưa có bean `NamedParameterJdbcOperations` phù hợp.

Nó thường tạo một bean `NamedParameterJdbcTemplate` dùng `JdbcTemplate` ứng viên chính và đánh dấu bean mặc định là `@Primary`.

Điều đó có nghĩa:

1. Hai DataSource không có primary khiến auto-configuration chính không khớp; các cấu hình template được import qua nó cũng không chạy.
2. Một DataSource hoặc nhiều DataSource có một primary cho phép cấu hình chính chạy.
3. Nếu người dùng cung cấp một `JdbcTemplate`, cấu hình tạo `JdbcTemplate` mặc định back off.
4. Nếu có đúng một `JdbcTemplate` candidate và chưa có `NamedParameterJdbcOperations`, Boot vẫn có thể tạo `NamedParameterJdbcTemplate`.
5. Nếu người dùng tự cung cấp `NamedParameterJdbcOperations`, cấu hình NamedParameter mặc định cũng back off.

Hai điều kiện missing bean khác nhau bảo vệ hai abstraction khác nhau: `JdbcOperations` và `NamedParameterJdbcOperations`.

## 8. Khi cần một JdbcTemplate cho từng DataSource

Nếu ứng dụng cần truy vấn cả database orders và reporting, hãy tạo hai template có qualifier riêng:

~~~java
@Configuration(proxyBeanMethods = false)
class JdbcTemplatesConfiguration {

    @Bean
    @Primary
    JdbcTemplate ordersJdbcTemplate(
            @Qualifier("ordersDataSource") DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    JdbcTemplate reportingJdbcTemplate(
            @Qualifier("reportingDataSource") DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }
}
~~~

Sau khi có hai `JdbcTemplate`, injection theo kiểu `JdbcTemplate` cũng cần một ứng viên primary hoặc qualifier rõ ràng. Trong ví dụ, `ordersJdbcTemplate` là primary cho injection không qualifier.

Sử dụng:

~~~java
@Repository
class OrdersRepository {

    private final JdbcTemplate jdbcTemplate;

    OrdersRepository(
            @Qualifier("ordersJdbcTemplate")
            JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }
}

@Repository
class ReportingRepository {

    private final JdbcTemplate jdbcTemplate;

    ReportingRepository(
            @Qualifier("reportingJdbcTemplate")
            JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }
}
~~~

Vì đã tự khai báo `JdbcTemplate`, cấu hình mặc định của Boot back off. Đây là hành vi mong muốn: ứng dụng kiểm soát rõ mỗi template dùng database nào.

Nếu cần named-parameter template cho cả hai database, hãy khai báo rõ từng bean:

~~~java
@Bean
@Primary
NamedParameterJdbcTemplate ordersNamedParameterJdbcTemplate(
        @Qualifier("ordersJdbcTemplate") JdbcTemplate jdbcTemplate) {
    return new NamedParameterJdbcTemplate(jdbcTemplate);
}

@Bean
NamedParameterJdbcTemplate reportingNamedParameterJdbcTemplate(
        @Qualifier("reportingJdbcTemplate") JdbcTemplate jdbcTemplate) {
    return new NamedParameterJdbcTemplate(jdbcTemplate);
}
~~~

Không dựa vào một bean `NamedParameterJdbcTemplate` mặc định để tự sinh một template cho mỗi DataSource; auto-configuration cung cấp một bean mặc định theo single-candidate rule.

## 9. Ví dụ kiểm chứng bằng ApplicationContextRunner

Ta có thể xác minh các điều kiện mà không cần kết nối database thật. `DriverManagerDataSource` chỉ giữ thông tin URL; các test dưới đây không gọi query hay mở connection.

**Tệp:** `src/test/java/example/jdbc/JdbcTemplateAutoConfigurationConditionsTest.java`

~~~java
package example.jdbc;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import static org.assertj.core.api.Assertions.assertThat;

class JdbcTemplateAutoConfigurationConditionsTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    JdbcTemplateAutoConfiguration.class));

    @Test
    void oneDataSourceCreatesDefaultJdbcTemplate() {
        runner.withUserConfiguration(SingleDataSourceConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(JdbcTemplate.class);
                    assertThat(context.getBean(JdbcTemplate.class).getDataSource())
                            .isSameAs(context.getBean("mainDataSource"));
                });
    }

    @Test
    void twoDataSourcesWithoutPrimaryDoNotMatch() {
        runner.withUserConfiguration(TwoDataSourcesWithoutPrimary.class)
                .run(context -> {
                    assertThat(context).hasBean("ordersDataSource");
                    assertThat(context).hasBean("reportingDataSource");
                    assertThat(context).doesNotHaveBean(JdbcTemplate.class);
                });
    }

    @Test
    void twoDataSourcesWithOnePrimaryUseThePrimaryDataSource() {
        runner.withUserConfiguration(TwoDataSourcesWithPrimary.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(JdbcTemplate.class);
                    assertThat(context.getBean(JdbcTemplate.class).getDataSource())
                            .isSameAs(context.getBean("ordersDataSource"));
                });
    }

    @Test
    void twoPrimaryDataSourcesAreStillAmbiguous() {
        runner.withUserConfiguration(TwoPrimaryDataSources.class)
                .run(context ->
                        assertThat(context).doesNotHaveBean(JdbcTemplate.class));
    }

    @Test
    void userJdbcTemplateMakesDefaultJdbcTemplateBackOff() {
        runner.withUserConfiguration(CustomJdbcTemplateConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(JdbcTemplate.class);
                    assertThat(context.containsBean("customJdbcTemplate")).isTrue();
                    assertThat(context.containsBean("jdbcTemplate")).isFalse();
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class SingleDataSourceConfiguration {

        @Bean
        DataSource mainDataSource() {
            return dataSource("jdbc:example:main");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TwoDataSourcesWithoutPrimary {

        @Bean
        DataSource ordersDataSource() {
            return dataSource("jdbc:example:orders");
        }

        @Bean
        DataSource reportingDataSource() {
            return dataSource("jdbc:example:reporting");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TwoDataSourcesWithPrimary {

        @Bean
        @Primary
        DataSource ordersDataSource() {
            return dataSource("jdbc:example:orders");
        }

        @Bean
        DataSource reportingDataSource() {
            return dataSource("jdbc:example:reporting");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TwoPrimaryDataSources {

        @Bean
        @Primary
        DataSource ordersDataSource() {
            return dataSource("jdbc:example:orders");
        }

        @Bean
        @Primary
        DataSource reportingDataSource() {
            return dataSource("jdbc:example:reporting");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomJdbcTemplateConfiguration {

        @Bean
        @Primary
        DataSource mainDataSource() {
            return dataSource("jdbc:example:main");
        }

        @Bean
        JdbcTemplate customJdbcTemplate(
                @Qualifier("mainDataSource") DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }
    }

    private static DataSource dataSource(String url) {
        return new DriverManagerDataSource(url);
    }
}
~~~

### Ý nghĩa năm test

| Test | Kết quả mong đợi | Điều được kiểm tra |
| --- | --- | --- |
| `oneDataSourceCreatesDefaultJdbcTemplate` | Có một JdbcTemplate dùng main DataSource | Một ứng viên DataSource đủ điều kiện |
| `twoDataSourcesWithoutPrimaryDoNotMatch` | Không có JdbcTemplate mặc định | Hai DataSource không có primary là mơ hồ |
| `twoDataSourcesWithOnePrimaryUseThePrimaryDataSource` | JdbcTemplate dùng orders DataSource | Một primary giúp xác định ứng viên duy nhất |
| `twoPrimaryDataSourcesAreStillAmbiguous` | Không có JdbcTemplate mặc định | Có nhiều primary không tạo ra một ứng viên duy nhất |
| `userJdbcTemplateMakesDefaultJdbcTemplateBackOff` | Chỉ customJdbcTemplate tồn tại | Cấu hình mặc định back off khi đã có JdbcOperations |

`DriverManagerDataSource` không kết nối database chỉ vì được khởi tạo; test chỉ xác minh cấu hình và bean wiring. Nếu gọi query, cần driver và database thực sự tương ứng.

### Dependency và lệnh chạy

Dự án cần Java 17+ và Spring Boot 3.3.x. Với Gradle Groovy DSL, giả sử plugin hoặc BOM Spring Boot đã quản lý version:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Chạy tại module chứa test:

~~~bash
# Linux/macOS
./gradlew test --tests "example.jdbc.JdbcTemplateAutoConfigurationConditionsTest"

# Windows
gradlew.bat test --tests "example.jdbc.JdbcTemplateAutoConfigurationConditionsTest"
~~~

**Kết quả kỳ vọng:** năm test PASS. Test sử dụng AssertJ, không có `System.out.println`, nên không có stdout nội dung cố định của ứng dụng; kết quả console phụ thuộc cấu hình Gradle/JUnit. Đây là kết quả mong đợi theo code, chưa phải log của một lần chạy thực tế.

## 10. Đọc Condition Evaluation Report khi template không xuất hiện

Khi chạy ứng dụng, bật debug:

~~~bash
java -jar app.jar --debug
~~~

Trong Condition Evaluation Report, tìm `JdbcTemplateAutoConfiguration` và các condition liên quan.

Các thông điệp có thể giúp định hướng:

- `@ConditionalOnClass`: thiếu `DataSource` hoặc `JdbcTemplate` trên classpath.
- `@ConditionalOnSingleCandidate(DataSource.class)`: không có DataSource phù hợp hoặc không xác định được primary candidate duy nhất.
- `@ConditionalOnMissingBean(JdbcOperations.class)`: đã có một bean JdbcOperations, nên template mặc định không được tạo.
- `@ConditionalOnSingleCandidate(JdbcTemplate.class)`: chưa có một JdbcTemplate candidate duy nhất để tạo NamedParameter template.
- `@ConditionalOnMissingBean(NamedParameterJdbcOperations.class)`: ứng dụng đã có named-parameter operations riêng.

Phân biệt condition của **auto-configuration class** với condition của **configuration con**:
- Nếu class chính không khớp `@ConditionalOnSingleCandidate(DataSource.class)`, các cấu hình template được import qua nó không được áp dụng.
- Nếu class chính khớp nhưng `JdbcTemplateConfiguration` back off vì có `JdbcOperations`, `NamedParameterJdbcTemplateConfiguration` vẫn có thể được đánh giá độc lập theo điều kiện của nó.

Không kết luận chỉ dựa trên việc thấy bean DataSource trong tab Beans. Hãy đọc đúng condition và tên bean/type mà report ghi nhận.

## 11. Các lỗi thường gặp

1. **Có hai DataSource nhưng không có primary.** `JdbcTemplateAutoConfiguration` không thể xác định một ứng viên theo kiểu; đánh dấu đúng một DataSource là `@Primary` nếu muốn nó làm mặc định.
2. **Đánh dấu cả hai DataSource là primary.** Điều này vẫn mơ hồ; chỉ có một primary candidate mới giải quyết được single-candidate condition.
3. **Nghĩ rằng @Qualifier thay thế được @Primary cho auto-configuration.** Qualifier giải quyết một điểm injection cụ thể; class-level condition không biết qualifier của service.
4. **Nghĩ @Primary làm DataSource phụ biến mất.** Bean phụ vẫn tồn tại; dùng qualifier để truy cập nó.
5. **Chỉ tạo một custom JdbcTemplate cho DataSource phụ và chờ Boot tạo thêm default cho DataSource chính.** Bean custom triển khai `JdbcOperations`, khiến cấu hình mặc định back off; hãy khai báo rõ cả các template cần dùng.
6. **Tạo hai JdbcTemplate nhưng không chọn primary hoặc qualifier.** Injection đơn theo kiểu JdbcTemplate sẽ mơ hồ; đánh dấu một template mặc định và qualifier các template còn lại.
7. **Nhầm JdbcTemplate với NamedParameterJdbcTemplate.** Chúng triển khai hai interface operations khác nhau và có điều kiện back-off riêng.
8. **Cho rằng có một DataSource là mọi điều kiện đều đủ.** Classpath phải có JDBC classes, cấu hình DataSource phải được đăng ký và các condition khác vẫn phải khớp.
9. **Không khai báo thứ tự auto-configuration.** Condition của JdbcTemplate phải được đánh giá sau DataSource configuration; Spring Boot đã đặt `after = DataSourceAutoConfiguration.class` cho mục đích này.
10. **Dùng URL không đúng với connection pool.** Khi tự bind trực tiếp HikariDataSource, property là `jdbc-url`; dùng `DataSourceProperties.initializeDataSourceBuilder()` để xử lý chuyển đổi `url` nhất quán.
11. **Cho rằng DataSource auto-configuration và JdbcTemplate auto-configuration cùng back off.** Chúng là các lớp/điều kiện khác nhau. Tự khai báo DataSource có thể khiến DataSource auto-config back off, nhưng JdbcTemplate auto-config vẫn có thể áp dụng nếu có single candidate.
12. **Chỉ kiểm tra khi có một DataSource.** Cần test cả hai DataSource không primary, một primary, nhiều primary và custom JdbcOperations.

## 12. Checklist khi thiết kế nhiều database

Trước khi phát hành cấu hình:

- Mỗi DataSource có bean name rõ nghĩa, chẳng hạn `ordersDataSource` và `reportingDataSource`.
- Chỉ một DataSource được chọn làm primary mặc định khi cần các auto-configuration theo kiểu.
- Mọi repository/service truy cập database phụ đều dùng `@Qualifier` cụ thể.
- Mỗi JdbcTemplate thủ công được gắn đúng DataSource qua qualifier.
- Nếu có nhiều JdbcTemplate, một template mặc định được đánh dấu primary hoặc tất cả injection đều dùng qualifier.
- Hiểu rõ custom `JdbcOperations` khiến JdbcTemplate auto-configuration back off.
- Kiểm tra cả `NamedParameterJdbcOperations` nếu ứng dụng tự cấu hình named-parameter template.
- Có test cho số lượng DataSource, primary candidate và custom template.
- Đọc Condition Evaluation Report khi một nhánh không được đăng ký.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Ứng dụng có hai DataSource và không có `@Primary`. `@ConditionalOnSingleCandidate(DataSource.class)` có khớp không?

**Đáp án:** Không. Không thể xác định một ứng viên duy nhất cho dependency theo kiểu DataSource.

**Câu 2.** Ứng dụng có ba DataSource, đúng một bean là `@Primary`. Điều kiện có thể khớp không?

**Đáp án:** Có. Một primary candidate giúp Spring xác định bean đơn khi autowire theo kiểu.

**Câu 3.** Một service dùng `@Qualifier("ordersDataSource")`. Điều đó có làm JdbcTemplateAutoConfiguration khớp khi có hai DataSource không primary không?

**Đáp án:** Không. Qualifier chỉ chọn bean tại injection point; điều kiện class-level vẫn không xác định được một primary candidate.

**Câu 4.** Người dùng tạo một bean custom `JdbcTemplate`. Vì sao Boot không tạo thêm một template mặc định?

**Đáp án:** `JdbcTemplate` triển khai `JdbcOperations`; điều kiện `@ConditionalOnMissingBean(JdbcOperations.class)` của cấu hình template mặc định không còn khớp.

**Câu 5.** Có một custom JdbcTemplate nhưng chưa có NamedParameterJdbcTemplate. Boot có thể tạo NamedParameter template không?

**Đáp án:** Có, nếu có một JdbcTemplate candidate duy nhất và chưa có `NamedParameterJdbcOperations` phù hợp. Hai cấu hình con có điều kiện riêng.

## 14. Ghi nhớ khi đọc JdbcTemplateAutoConfiguration

`JdbcTemplateAutoConfiguration` không chỉ kiểm tra xem có một DataSource hay không. Nó cần **một DataSource candidate có thể xác định duy nhất**. Một bean duy nhất đáp ứng điều kiện; nhiều DataSource vẫn có thể đáp ứng nếu có đúng một `@Primary`. Sau đó, cấu hình con tạo `JdbcTemplate` nếu chưa có `JdbcOperations`, và tạo `NamedParameterJdbcTemplate` nếu có một JdbcTemplate candidate và chưa có named-parameter operations.

Với ứng dụng nhiều database:
- `@Primary` xác định DataSource/template mặc định.
- `@Qualifier` chọn đúng database ở từng nơi sử dụng.
- Tự khai báo `JdbcOperations` hoặc `NamedParameterJdbcOperations` sẽ khiến cấu hình mặc định tương ứng back off.
- Muốn có template cho từng database, hãy khai báo từng bean và nối đúng DataSource bằng qualifier.

### Tài liệu Spring Boot và Spring Framework chính thức

- [Spring Boot 3.3 — JdbcTemplateAutoConfiguration Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/JdbcTemplateAutoConfiguration.html)
- [Spring Boot 3.3 — ConditionalOnSingleCandidate Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnSingleCandidate.html)
- [Spring Boot 3.3 — Data Access: Configure Two DataSources](https://docs.spring.io/spring-boot/3.3/how-to/data-access.html)
- [Spring Framework 6.1 — @Primary Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Primary.html)
- [Spring Framework 6.1 — @Qualifier Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/annotation/Qualifier.html)
