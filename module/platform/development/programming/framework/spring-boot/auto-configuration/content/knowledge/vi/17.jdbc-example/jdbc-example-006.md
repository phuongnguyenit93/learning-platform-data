# Quan hệ thứ tự giữa cấu hình nguồn dữ liệu và tiện ích JDBC trong Spring Boot

## 1. Vấn đề cần giải quyết

Một ứng dụng Spring Boot có thể có nhiều tầng hạ tầng JDBC:

- `DataSource` cung cấp kết nối tới database.
- `JdbcTemplate` lấy connection từ `DataSource` để thực thi SQL.
- `NamedParameterJdbcTemplate`, `JdbcClient` hoặc repository/service riêng có thể phụ thuộc vào `JdbcTemplate` hoặc `DataSource`.

Nếu một thư viện tự cung cấp tiện ích JDBC, nó chỉ nên đăng ký bean sau khi dependency cần thiết đã được cấu hình. Đây là bài toán về **thứ tự áp dụng auto-configuration** và **thời điểm đánh giá điều kiện bean**.

Cần phân biệt hai loại thứ tự:

1. **Thứ tự áp dụng auto-configuration:** thứ tự Spring xử lý các lớp cấu hình và đăng ký bean definitions. Dùng `@AutoConfiguration(after = ...)`, `@AutoConfigureAfter`, `before` hoặc `@AutoConfigureBefore`.
2. **Thứ tự khởi tạo bean:** thứ tự object thực sự được tạo trong ApplicationContext. Spring quyết định dựa trên dependency injection và `@DependsOn`.

`after` giúp condition bean nhìn thấy các bean definitions đã được cấu hình trước đó. Nó **không phải** lệnh tạo object trước object khác.

## 2. Chuỗi cấu hình JDBC trong Spring Boot 3.3

Chuỗi điển hình:

```text
DataSourceAutoConfiguration
          |
          | đăng ký DataSource bean definition
          v
JdbcTemplateAutoConfiguration
          |
          | cần DataSource candidate phù hợp
          | đăng ký JdbcTemplate / NamedParameterJdbcTemplate
          v
CustomJdbcUtilityAutoConfiguration
          |
          | cần JdbcTemplate bean definition
          v
JdbcStatsRepository
```

Spring Boot 3.3 thể hiện quan hệ này trong cấu hình có sẵn:

- `DataSourceAutoConfiguration` được đánh dấu `@AutoConfiguration(before = SqlInitializationAutoConfiguration.class)`. Nó kiểm tra class JDBC cần thiết, sự hiện diện của R2DBC `ConnectionFactory`, đăng ký `DataSourceProperties` và cấu hình nguồn dữ liệu phù hợp.
- `JdbcTemplateAutoConfiguration` được đánh dấu `@AutoConfiguration(after = DataSourceAutoConfiguration.class)`. Nó kiểm tra các class `DataSource`, `JdbcTemplate` trên classpath và dùng `@ConditionalOnSingleCandidate(DataSource.class)` trước khi đăng ký các tiện ích template.

Do đó, nếu tiện ích của thư viện cần `JdbcTemplate`, hãy đặt auto-configuration của nó sau `JdbcTemplateAutoConfiguration`. Nếu nó chỉ cần trực tiếp `DataSource`, có thể đặt sau `DataSourceAutoConfiguration`.

## 3. Khai báo thứ tự bằng `@AutoConfiguration(after = ...)`

Ví dụ tiện ích phụ thuộc `JdbcTemplate`:

```java
package demo;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@AutoConfiguration(after = JdbcTemplateAutoConfiguration.class)
@ConditionalOnClass(JdbcTemplate.class)
@ConditionalOnBean(JdbcTemplate.class)
public class JdbcUtilityAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(JdbcStatsRepository.class)
    JdbcStatsRepository jdbcStatsRepository(JdbcTemplate jdbcTemplate) {
        return new JdbcStatsRepository(jdbcTemplate);
    }
}
```

Ý nghĩa:

- `after = JdbcTemplateAutoConfiguration.class` yêu cầu auto-configuration tiện ích được áp dụng sau cấu hình template của Boot.
- `@ConditionalOnClass(JdbcTemplate.class)` bảo đảm API JDBC template có trên classpath.
- `@ConditionalOnBean(JdbcTemplate.class)` chỉ cho phép cấu hình này áp dụng khi bean template đã được đăng ký.
- `@ConditionalOnMissingBean(JdbcStatsRepository.class)` cho phép ứng dụng cung cấp implementation thay thế.
- Tham số `JdbcTemplate jdbcTemplate` của phương thức `@Bean` tạo dependency thực sự. Khi Spring khởi tạo repository, nó phải resolve template trước.

Nếu tiện ích chỉ dùng trực tiếp `DataSource`, có thể dùng mẫu:

```java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
@ConditionalOnClass(DataSource.class)
@ConditionalOnSingleCandidate(DataSource.class)
public class DirectDataSourceUtilityAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    ConnectionInspector connectionInspector(DataSource dataSource) {
        return new ConnectionInspector(dataSource);
    }
}
```

`ConnectionInspector` là kiểu minh họa phải được định nghĩa riêng. `@ConditionalOnSingleCandidate(DataSource.class)` phù hợp khi tiện ích cần một datasource duy nhất hoặc một datasource được đánh dấu `@Primary`. Nếu có nhiều datasource và không có primary, điều kiện này không match.

| Tiện ích cần | Nên áp dụng sau | Điều kiện bean thường dùng |
|---|---|---|
| `DataSource` | `DataSourceAutoConfiguration` | `@ConditionalOnSingleCandidate(DataSource.class)` hoặc `@ConditionalOnBean(DataSource.class)` |
| `JdbcTemplate` | `JdbcTemplateAutoConfiguration` | `@ConditionalOnBean(JdbcTemplate.class)` |
| `NamedParameterJdbcTemplate` | `JdbcTemplateAutoConfiguration` | `@ConditionalOnBean(NamedParameterJdbcTemplate.class)` |
| Bean do auto-configuration khác cung cấp | Auto-configuration đó | `@ConditionalOnBean(RepositoryType.class)` |

Chỉ khai báo quan hệ thứ tự trực tiếp mà tiện ích thực sự cần.

## 4. `after`, `before`, `afterName` và `@AutoConfigureOrder`

### `after` và `before`

```java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
class MyJdbcAutoConfiguration {
}

@AutoConfiguration(before = SqlInitializationAutoConfiguration.class)
class CustomSqlSetupAutoConfiguration {
}
```

`after` yêu cầu cấu hình của bạn được áp dụng sau class được chỉ định. `before` yêu cầu nó được áp dụng trước class được chỉ định.

### `afterName` và `beforeName`

Khi không muốn tham chiếu class đích bằng class literal, có thể dùng tên đầy đủ:

```java
@AutoConfiguration(
    afterName = "org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration"
)
class MyJdbcAutoConfiguration {
}
```

Cách này hữu ích khi dependency đích là tùy chọn và module hiện tại không muốn tham chiếu trực tiếp tới class đó ở compile time. Tên phải là FQCN chính xác; chuỗi không được compiler kiểm tra.

### `@AutoConfigureAfter` và `@AutoConfigureBefore`

Hai annotation chuyên biệt vẫn có thể diễn tả cùng quan hệ:

```java
@AutoConfigureAfter(DataSourceAutoConfiguration.class)
@Configuration(proxyBeanMethods = false)
class LegacyStyleJdbcConfiguration {
}
```

Trong code Spring Boot 3.x mới, thường ưu tiên `@AutoConfiguration(after = ...)` cho auto-configuration class.

### `@AutoConfigureOrder`

`@AutoConfigureOrder` đặt thứ tự tương đối tổng quát cho auto-configuration, hữu ích khi các cấu hình không có quan hệ trực tiếp hoặc không nên biết tên của nhau. Khi JDBC utility thực sự phụ thuộc vào `DataSourceAutoConfiguration` hay `JdbcTemplateAutoConfiguration`, quan hệ `after` rõ ràng hơn một con số order chung.

`@Order` trên bean thông thường không thay thế thứ tự áp dụng auto-configuration.

## 5. Bean definitions và thứ tự khởi tạo object là hai chuyện khác nhau

Giả sử có phương thức:

```java
@Bean
JdbcStatsRepository jdbcStatsRepository(JdbcTemplate jdbcTemplate) {
    return new JdbcStatsRepository(jdbcTemplate);
}
```

Khi Spring tạo `JdbcStatsRepository`, tham số `JdbcTemplate` là dependency. Spring resolve và tạo template trước khi gọi phương thức bean này nếu nó chưa được tạo. Dependency injection đã thể hiện thứ tự khởi tạo cần thiết.

`@AutoConfiguration(after = JdbcTemplateAutoConfiguration.class)` giải quyết câu hỏi khác: **khi condition của tiện ích được đánh giá, bean definition `JdbcTemplate` đã được đăng ký hay chưa?**

`@ConditionalOnBean(JdbcTemplate.class)` dựa vào bean definitions mà Spring đã xử lý tới thời điểm đánh giá. Nếu tiện ích được xử lý trước cấu hình tạo template, condition có thể không match dù template sẽ được đăng ký sau đó. `after` giải quyết quan hệ thời điểm đánh giá này.

| Cơ chế | Tác động |
|---|---|
| `@AutoConfiguration(after = ...)` | Thứ tự áp dụng cấu hình và đăng ký bean definitions |
| `@ConditionalOnBean(...)` | Quyết định đăng ký dựa trên bean definitions đã biết |
| Tham số trong phương thức `@Bean` | Dependency injection khi khởi tạo bean |
| Constructor injection | Khai báo dependency thực sự giữa các bean |
| `@DependsOn` | Ép một bean khởi tạo trước bean khác khi có side effect không thể biểu diễn bằng injection |

Với `JdbcTemplate` và `DataSource`, ưu tiên constructor hoặc method-parameter injection. Không dùng `@DependsOn` chỉ để thay thế dependency injection đã có sẵn.

## 6. Vì sao `@ConditionalOnBean` cần đúng thứ tự?

`@ConditionalOnBean` và `@ConditionalOnMissingBean` được đánh giá dựa trên các bean definitions đã được xử lý tới thời điểm đó. Spring Boot khuyến nghị dùng các điều kiện bean này trong auto-configuration vì auto-configuration được xử lý sau bean definitions do người dùng khai báo.

Trong ví dụ:

```java
@AutoConfiguration(after = JdbcTemplateAutoConfiguration.class)
@ConditionalOnBean(JdbcTemplate.class)
class JdbcUtilityAutoConfiguration {
    // Các bean phụ thuộc JdbcTemplate
}
```

`after` giúp `JdbcTemplateAutoConfiguration` được áp dụng trước. Nếu cấu hình đó match và đăng ký template, condition bean của tiện ích có thể nhìn thấy bean definition tương ứng.

Đặt condition ở cấp class có tác dụng ngăn đăng ký configuration class nếu condition không match; đặt ở từng `@Bean` method chỉ điều khiển bean method đó.

Không nên dùng `@ConditionalOnBean` trên một configuration thông thường rồi kỳ vọng nó nhìn thấy mọi bean được khai báo ở cấu hình xử lý muộn hơn. Hãy đặt logic vào auto-configuration và khai báo quan hệ thứ tự phù hợp.

## 7. Ví dụ kiểm thử với `ApplicationContextRunner` (Spring Boot 3.3 / Java 17+)

Ví dụ dưới đây dùng JUnit 5 và H2 để kiểm tra ba trường hợp:

1. Có datasource: Boot tạo `JdbcTemplate`, sau đó auto-configuration riêng tạo repository JDBC.
2. Loại trừ datasource auto-configuration: không có `JdbcTemplate`, tiện ích riêng không được tạo.
3. Người dùng cung cấp repository riêng: auto-configuration mặc định back off.

Đặt file `src/test/java/demo/JdbcAutoConfigurationOrderTest.java`:

```java
package demo;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class JdbcAutoConfigurationOrderTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            DataSourceAutoConfiguration.class,
                            JdbcTemplateAutoConfiguration.class,
                            JdbcUtilityAutoConfiguration.class
                    ))
                    .withPropertyValues(
                            "spring.datasource.url=jdbc:h2:mem:jdbc_order_test",
                            "spring.datasource.username=sa",
                            "spring.datasource.password="
                    );

    @Test
    void datasourceIsAvailableBeforeJdbcUtilityIsCreated() {
        runner.run(context -> {
            assertTrue(context.containsBean("dataSource"));
            assertNotNull(context.getBean(DataSource.class));
            assertNotNull(context.getBean(JdbcTemplate.class));

            JdbcStatsRepository repository =
                    context.getBean(JdbcStatsRepository.class);

            assertEquals(1, repository.selectOne());
        });
    }

    @Test
    void withoutDatasourceAutoConfigurationJdbcUtilityDoesNotExist() {
        runner.withPropertyValues(
                        "spring.autoconfigure.exclude="
                                + "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
                )
                .run(context -> {
                    assertFalse(context.containsBean("jdbcTemplate"));
                    assertFalse(context.containsBean("jdbcStatsRepository"));
                    assertTrue(context.getBeansOfType(DataSource.class).isEmpty());
                });
    }

    @Test
    void userRepositoryOverridesTheDefault() {
        runner.withUserConfiguration(UserRepositoryConfiguration.class)
                .run(context -> {
                    assertTrue(context.containsBean("customJdbcStatsRepository"));
                    assertFalse(context.containsBean("jdbcStatsRepository"));

                    assertEquals(
                            1,
                            context.getBean(JdbcStatsRepository.class).selectOne()
                    );
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserRepositoryConfiguration {

        @Bean
        JdbcStatsRepository customJdbcStatsRepository(
                JdbcTemplate jdbcTemplate) {
            return new JdbcStatsRepository(jdbcTemplate);
        }
    }
}

@AutoConfiguration(after = JdbcTemplateAutoConfiguration.class)
@ConditionalOnClass(JdbcTemplate.class)
@ConditionalOnBean(JdbcTemplate.class)
class JdbcUtilityAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(JdbcStatsRepository.class)
    JdbcStatsRepository jdbcStatsRepository(JdbcTemplate jdbcTemplate) {
        return new JdbcStatsRepository(jdbcTemplate);
    }
}

final class JdbcStatsRepository {

    private final JdbcTemplate jdbcTemplate;

    JdbcStatsRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    int selectOne() {
        return jdbcTemplate.queryForObject("SELECT 1", Integer.class);
    }
}
```

### Giải thích test

- `AutoConfigurations.of(...)` đăng ký ba auto-configuration. Spring Boot sắp xếp chúng theo metadata `before`/`after`, không phụ thuộc thứ tự class được liệt kê.
- `DataSourceAutoConfiguration` tạo datasource từ H2 URL.
- `JdbcTemplateAutoConfiguration` được áp dụng sau datasource và chỉ match khi có một `DataSource` candidate phù hợp.
- `JdbcUtilityAutoConfiguration` được áp dụng sau `JdbcTemplateAutoConfiguration`, đồng thời kiểm tra bean `JdbcTemplate` đã tồn tại.
- Phương thức `jdbcStatsRepository(JdbcTemplate jdbcTemplate)` thể hiện dependency thật giữa repository và template.
- Test thứ hai loại trừ datasource auto-configuration bằng property. Khi không có datasource, điều kiện tạo `JdbcTemplate` không đạt, và tiện ích riêng cũng không được đăng ký.
- Test thứ ba xác nhận bean người dùng thay thế bean mặc định nhờ `@ConditionalOnMissingBean`.

### Dependency và lệnh chạy

Trong project Gradle đã quản lý phiên bản bằng Spring Boot 3.3.x:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-jdbc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Chạy trên Linux/macOS:

```bash
./gradlew test --tests demo.JdbcAutoConfigurationOrderTest
```

Trên Windows PowerShell:

```powershell
.\\gradlew.bat test --tests demo.JdbcAutoConfigurationOrderTest
```

**Kết quả kỳ vọng:** cả 3 test pass. Test đầu thực thi `SELECT 1` trên H2 in-memory; test thứ hai không tạo datasource/template/repository; test thứ ba dùng repository do người dùng cung cấp. Đây là kết quả dự kiến theo code và cấu hình dependency, chưa phải log của một lần chạy thực tế.

Khi đưa `JdbcUtilityAutoConfiguration` vào thư viện riêng, thêm tên lớp vào file `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

```text
demo.JdbcUtilityAutoConfiguration
```

Không dựa vào component scan để tìm auto-configuration. Test trên đăng ký class trực tiếp qua `AutoConfigurations.of(...)`, vì vậy không cần file imports trong test.

## 8. Khi chỉ cần DataSource, không cần JdbcTemplate

Không phải tiện ích JDBC nào cũng cần `JdbcTemplate`. Một thư viện có thể cần trực tiếp `DataSource` để mở connection, lấy metadata hoặc tạo thành phần tích hợp khác.

Ví dụ:

```java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
@ConditionalOnClass(DataSource.class)
@ConditionalOnSingleCandidate(DataSource.class)
class ConnectionMetadataAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    ConnectionMetadataReader connectionMetadataReader(
            DataSource dataSource) {
        return new ConnectionMetadataReader(dataSource);
    }
}
```

`ConnectionMetadataReader` là class minh họa phải được định nghĩa trong ứng dụng. Không cần `after = JdbcTemplateAutoConfiguration.class` vì cấu hình không phụ thuộc template. `@ConditionalOnSingleCandidate(DataSource.class)` phù hợp nếu tiện ích chỉ hỗ trợ một datasource candidate rõ ràng.

Nếu ứng dụng có nhiều datasource:

- Có một datasource được đánh dấu `@Primary`, Spring có thể xác định single candidate.
- Có nhiều datasource nhưng không có primary, `@ConditionalOnSingleCandidate` không match.
- Nếu tiện ích cần datasource cụ thể, dùng `@Qualifier` để injection đúng bean; condition cũng phải diễn tả đúng yêu cầu đó.

## 9. Các lỗi thứ tự thường gặp

1. **Đặt tiện ích trước cấu hình tạo dependency.** Auto-configuration dùng `@ConditionalOnBean(JdbcTemplate.class)` nhưng được xử lý trước `JdbcTemplateAutoConfiguration` có thể không match. Khai báo `after` nếu có quan hệ trực tiếp.
2. **Dùng `@Order` thay cho `after`.** `@Order` không biểu diễn dependency giữa các auto-configuration.
3. **Tưởng `after` buộc object được khởi tạo trước.** Nó điều khiển thứ tự áp dụng cấu hình và đăng ký bean definitions. Muốn thể hiện dependency lúc khởi tạo, truyền bean qua constructor hoặc tham số `@Bean`.
4. **Dùng `@DependsOn` để chữa condition không match.** `@DependsOn` điều khiển khởi tạo bean, không khiến `@ConditionalOnBean` được đánh giá lại.
5. **Quên `@ConditionalOnBean`.** Nếu tiện ích cần `JdbcTemplate` nhưng vẫn đăng ký bean method khi template vắng mặt, ứng dụng có thể fail khi khởi tạo.
6. **Kiểm tra sai abstraction.** Kiểm tra `DataSource.class` chỉ chứng minh datasource có mặt, không chứng minh `JdbcTemplate` đã được đăng ký.
7. **Trả về interface quá chung từ `@Bean`.** Condition bean cần metadata kiểu đủ rõ; hãy cung cấp kiểu trả về cụ thể.
8. **Tưởng danh sách class trong `AutoConfigurations.of` quyết định thứ tự.** Spring Boot dùng ordering metadata để sắp xếp auto-configuration.
9. **Tạo vòng phụ thuộc thứ tự.** Nếu A khai báo `after = B` và B khai báo `after = A`, hãy thiết kế lại dependency một chiều.
10. **Quên dependency JDBC là tùy chọn.** Cô lập cấu hình trong class có `@ConditionalOnClass` và tránh nạp kiểu JDBC khi dependency vắng mặt.

## 10. Thứ tự giữa auto-configuration không thay thế thiết kế dependency

Một ứng dụng có thể có nhiều tầng cấu hình: datasource, transaction manager, JDBC template, SQL initialization và thư viện truy vấn riêng. Mỗi tầng nên khai báo đúng dependency:

- `DataSourceAutoConfiguration` chịu trách nhiệm cấu hình nguồn dữ liệu.
- `JdbcTemplateAutoConfiguration` áp dụng sau datasource và kiểm tra một datasource candidate.
- Tiện ích chỉ dùng `JdbcTemplate` nên áp dụng sau template và nhận template qua injection.
- Tiện ích dùng trực tiếp `DataSource` nên phụ thuộc datasource, không phụ thuộc template nếu không cần.
- Bean tùy biến của người dùng nên được tôn trọng bằng `@ConditionalOnMissingBean`.

Không dùng một chuỗi `after` dài chỉ để ép mọi thứ chạy theo thứ tự tưởng tượng. Đặt condition đúng kiểu bean, khai báo dependency bằng injection, và chỉ thêm ordering khi condition cần thấy bean definition từ auto-configuration khác.

## 11. Chẩn đoán khi tiện ích JDBC không được tạo

1. **Kiểm tra classpath:** `spring-jdbc`, driver database và pool implementation cần thiết có ở runtime không?
2. **Kiểm tra datasource:** có bean `DataSource` không? Có nhiều datasource mà thiếu `@Primary` hoặc `@Qualifier` không?
3. **Kiểm tra template:** có bean `JdbcTemplate` hoặc `NamedParameterJdbcTemplate` đúng loại mà tiện ích yêu cầu không?
4. **Kiểm tra ordering:** auto-configuration tiện ích có `after` đúng class không? Class đó có thật sự được import trong ứng dụng không?
5. **Kiểm tra condition:** bật `--debug` hoặc xem Actuator `/actuator/conditions` nếu đã cấu hình để biết `@ConditionalOnBean`, `@ConditionalOnClass` hay `@ConditionalOnSingleCandidate` không match.
6. **Kiểm tra back-off:** ứng dụng đã có bean repository/service thay thế khiến `@ConditionalOnMissingBean` không tạo bean mặc định không?
7. **Kiểm tra khởi tạo:** bean definition có tồn tại nhưng constructor hoặc kết nối JDBC thất bại không? Đây là lỗi khởi tạo, không phải lỗi ordering.
8. **Kiểm thử riêng:** dùng `ApplicationContextRunner` với từng tổ hợp classpath, property, user bean và auto-configuration để tái hiện.

## 12. Ghi nhớ

- `DataSourceAutoConfiguration` là tầng cấu hình nguồn dữ liệu.
- Trong Spring Boot 3.3, `JdbcTemplateAutoConfiguration` được áp dụng **sau** `DataSourceAutoConfiguration`.
- Tiện ích cần `JdbcTemplate` nên khai báo `after = JdbcTemplateAutoConfiguration.class`, kiểm tra `@ConditionalOnBean(JdbcTemplate.class)` và nhận `JdbcTemplate` qua injection.
- Tiện ích chỉ cần `DataSource` có thể khai báo `after = DataSourceAutoConfiguration.class` và kiểm tra datasource phù hợp.
- `after` điều khiển **bean definition registration order**; constructor/method injection điều khiển dependency lúc khởi tạo.
- `@DependsOn` chỉ dành cho quan hệ khởi tạo phụ thuộc side-effect không thể biểu diễn bằng injection.
- Test cả trường hợp có datasource, thiếu datasource và user override để xác nhận auto-configuration không kích hoạt ngoài ý muốn.

### Tài liệu chính thức

- Spring Boot 3.3 Javadoc — `DataSourceAutoConfiguration`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceAutoConfiguration.html
- Spring Boot 3.3 Javadoc — `JdbcTemplateAutoConfiguration`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/JdbcTemplateAutoConfiguration.html
- Spring Boot 3.3 Javadoc — `AutoConfiguration`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
- Spring Boot 3.3 Reference — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 Reference — Testing Applications / JDBC tests: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
