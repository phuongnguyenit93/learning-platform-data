# AnyNestedCondition cho các phương án thay thế

## 1. Khi nào cần điều kiện OR trong auto-configuration?

Một auto-configuration thường chỉ được áp dụng khi nhiều điều kiện cùng đúng. Ví dụ, thư viện cần có SDK trên classpath, feature flag phải bật và ứng dụng chưa cung cấp bean thay thế. Đây là logic AND: tất cả điều kiện đều phải khớp.

Nhưng có những tính năng hỗ trợ nhiều cách cấu hình thay thế. Ví dụ, một ứng dụng có thể kết nối tới Catalog bằng JNDI **hoặc** bằng JDBC URL. Chỉ cần một trong hai phương án được cấu hình thì nhánh auto-configuration đã có đủ cơ sở để tham gia.

Nếu đặt hai `@ConditionalOnProperty` độc lập trên cùng một configuration class, Spring sẽ kết hợp chúng theo AND. Kết quả là ứng dụng phải cấu hình cả JNDI lẫn URL, trái với yêu cầu “một trong hai”.

Spring Boot cung cấp `AnyNestedCondition` để biểu diễn trường hợp này. Đây là một composite condition: **condition tổng khớp khi ít nhất một condition trên các nested class khớp**.

Bài học dùng Java 17+, Spring Boot 3.3.13, Maven và `ApplicationContextRunner`. Sau bài này, bạn có thể:

- Nhận diện đúng logic OR trong auto-configuration.
- Viết một condition kế thừa `AnyNestedCondition`.
- Chọn `ConfigurationPhase` phù hợp.
- Kết hợp OR bên trong với AND ở configuration bên ngoài.
- Kiểm thử từng nhánh, trường hợp không có nhánh nào và trường hợp nhiều nhánh cùng khớp.
- Phân biệt “ít nhất một” với “chính xác một”.

## 2. Hiểu đúng logic AnyNestedCondition

Giả sử có hai phương án:

- `J`: ứng dụng bật kết nối bằng JNDI.
- `U`: ứng dụng bật kết nối bằng URL.

`AnyNestedCondition` dùng logic OR bao hàm:

| J | U | Kết quả |
|---|---|---|
| false | false | Không khớp |
| true | false | Khớp |
| false | true | Khớp |
| true | true | Khớp |

Điểm cuối rất quan trọng: OR của `AnyNestedCondition` **không phải XOR**. Khi cả hai nhánh cùng khớp, condition tổng vẫn khớp. Nó không tự chọn JNDI hay URL, cũng không tự đặt thứ tự ưu tiên.

Nếu yêu cầu nghiệp vụ là “chỉ được cấu hình đúng một phương án”, cần kiểm tra trường hợp cả hai cùng bật ở một tầng khác, chẳng hạn validation trong `@Bean` factory method hoặc một custom condition chuyên kiểm tra tính loại trừ lẫn nhau.

### 2.1. So sánh với AND và NOR

Spring Boot có ba lớp composite condition thường gặp:

| Lớp | Quy tắc | Cách hiểu |
|---|---|---|
| `AnyNestedCondition` | Khớp nếu có ít nhất một nested condition khớp | OR |
| `AllNestedConditions` | Chỉ khớp nếu mọi nested condition đều khớp | AND |
| `NoneNestedConditions` | Khớp nếu không nested condition nào khớp | NOR / NOT OR |

Ví dụ với hai điều kiện J và U:

- `AnyNestedCondition`: J hoặc U hoặc cả hai.
- `AllNestedConditions`: J và U đều phải đúng.
- `NoneNestedConditions`: cả J và U đều sai.

Đây là các lớp trong package `org.springframework.boot.autoconfigure.condition`, cùng dựa trên `AbstractNestedCondition`.

### 2.2. Các condition bên trong một nhánh vẫn kết hợp theo AND

Mỗi nested class có thể mang một hoặc nhiều annotation condition. Các condition gắn trên cùng một nested class phải cùng khớp để nhánh đó khớp.

Ví dụ:

```java
@ConditionalOnClass(name = "com.vendor.jndi.Client")
@ConditionalOnProperty(
        prefix = "acme.catalog",
        name = "jndi-enabled",
        havingValue = "true")
static class JndiBranch {
}
```

Nhánh JNDI này có logic:

`Client có trên classpath AND jndi-enabled=true`

Nếu nested class URL có logic:

`HTTP client có trên classpath AND url-enabled=true`

thì condition tổng sẽ là:

`(JNDI classpath AND JNDI flag) OR (HTTP classpath AND URL flag)`

Có thể tiếp tục đặt các điều kiện chung trên configuration bên ngoài, ví dụ `@ConditionalOnClass` cho API dùng chung hoặc `@ConditionalOnProperty` cho feature flag tổng. Các điều kiện ở tầng ngoài kết hợp với condition tổng bằng AND.

## 3. Vì sao không dùng hai @ConditionalOnProperty trên cùng class?

Giả sử viết:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "acme.catalog",
        name = "jndi-enabled",
        havingValue = "true")
@ConditionalOnProperty(
        prefix = "acme.catalog",
        name = "url-enabled",
        havingValue = "true")
class CatalogConfiguration {
}
```

Cấu hình trên yêu cầu cả hai property cùng bằng `true`. Hai annotation không có nghĩa “chọn một trong hai”.

Một cách khác là truyền nhiều tên vào cùng `@ConditionalOnProperty`:

```java
@ConditionalOnProperty(
        prefix = "acme.catalog",
        name = {"jndi-enabled", "url-enabled"},
        havingValue = "true")
```

Cách này cũng là AND: tất cả tên trong mảng `name` phải thỏa điều kiện.

Nếu cần OR giữa nhiều condition annotation, dùng `AnyNestedCondition` sẽ thể hiện ý định trực tiếp hơn. `@ConditionalOnExpression` có thể viết biểu thức OR, nhưng với các điều kiện cấu hình thông thường, nested condition dễ tách nhánh, đọc và chẩn đoán hơn. Đặc biệt, tránh tham chiếu bean trong SpEL condition vì bean có thể bị khởi tạo rất sớm trong quá trình refresh.

## 4. Cấu trúc và API của AnyNestedCondition

`AnyNestedCondition`:

- Nằm trong package `org.springframework.boot.autoconfigure.condition`.
- Kế thừa `AbstractNestedCondition`.
- Triển khai `Condition` và `ConfigurationCondition`.
- Có constructor nhận `ConfigurationCondition.ConfigurationPhase`.
- Thu thập outcome từ các nested class rồi trả về kết quả tổng.

Một condition tối thiểu:

```java
static class OnJndiOrUrl extends AnyNestedCondition {

    OnJndiOrUrl() {
        super(ConfigurationPhase.PARSE_CONFIGURATION);
    }

    @ConditionalOnProperty(
            prefix = "acme.catalog",
            name = "jndi-enabled",
            havingValue = "true")
    static class OnJndi {
    }

    @ConditionalOnProperty(
            prefix = "acme.catalog",
            name = "url-enabled",
            havingValue = "true")
    static class OnUrl {
    }
}
```

Các nested member class là những lớp tĩnh, mỗi lớp đại diện cho một phương án. Chúng không cần chứa method hoặc bean; annotation trên lớp là đủ để mô tả điều kiện của nhánh.

Sau đó gắn composite condition vào configuration bằng `@Conditional`:

```java
@Configuration(proxyBeanMethods = false)
@Conditional(OnJndiOrUrl.class)
class CatalogConnectionConfiguration {
}
```

`AnyNestedCondition` không tự tạo bean. Nó chỉ quyết định configuration hoặc bean được bảo vệ bởi `@Conditional` có được tiếp tục xử lý hay không. Việc đăng ký bean vẫn do `@Bean`, component hoặc cấu hình khác thực hiện.

### 4.1. ConfigurationPhase là gì?

Constructor yêu cầu chọn một trong hai phase:

| Phase | Thời điểm | Trường hợp phù hợp |
|---|---|---|
| `PARSE_CONFIGURATION` | Khi Spring đang phân tích các lớp `@Configuration` | Các condition dựa trên classpath, property, profile hoặc resource có thể đánh giá sớm |
| `REGISTER_BEAN` | Khi Spring đăng ký bean thông thường; lúc này các configuration class đã được phân tích | Các condition cần quan sát bean definition đã được đăng ký |

Ví dụ trong bài chỉ dùng `@ConditionalOnProperty`, nên `PARSE_CONFIGURATION` là lựa chọn phù hợp: Spring có thể kiểm tra các property trước khi quyết định có đưa nested configuration vào hay không.

Nếu một nested condition dựa trên bean hiện có, chẳng hạn `@ConditionalOnBean`, cần cân nhắc `REGISTER_BEAN` để condition được đánh giá sau khi các configuration class đã được phân tích. Chọn phase theo yêu cầu của các condition thành viên, không chọn tùy ý.

Lưu ý: `REGISTER_BEAN` không có nghĩa condition sẽ ngăn mọi `@Configuration` class được parse. Phase này dành cho việc đánh giá khi đăng ký bean thông thường. Nếu cần loại cả configuration class từ sớm, phase và vị trí áp dụng phải được thiết kế phù hợp.

### 4.2. Một nhánh có thể chứa nhiều condition

Ví dụ mỗi phương án cần đồng thời classpath và property:

```java
static class OnCatalogTransport extends AnyNestedCondition {

    OnCatalogTransport() {
        super(ConfigurationPhase.PARSE_CONFIGURATION);
    }

    @ConditionalOnClass(name = "com.vendor.jndi.JndiCatalogClient")
    @ConditionalOnProperty(
            prefix = "acme.catalog",
            name = "jndi-enabled",
            havingValue = "true")
    static class JndiBranch {
    }

    @ConditionalOnClass(name = "com.vendor.http.HttpCatalogClient")
    @ConditionalOnProperty(
            prefix = "acme.catalog",
            name = "url-enabled",
            havingValue = "true")
    static class HttpBranch {
    }
}
```

Ở đây, `JndiBranch` cần cả hai điều kiện cùng khớp. `HttpBranch` cũng cần cả hai điều kiện cùng khớp. `OnCatalogTransport` chỉ cần một trong hai nhánh khớp.

Nếu muốn thêm yêu cầu chung cho mọi nhánh, đặt condition đó ở configuration được bảo vệ:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(CatalogService.class)
@Conditional(OnCatalogTransport.class)
class CatalogConnectionConfiguration {
}
```

Kết quả tổng lúc này là:

`CatalogService có trên classpath AND (JNDI branch OR HTTP branch)`

## 5. Ví dụ thực tế: chấp nhận JNDI hoặc URL

Ta xây dựng một auto-configuration tạo `CatalogConnectionSettings` nếu người dùng bật một trong hai lựa chọn:

- `acme.catalog.jndi-enabled=true` và cung cấp `acme.catalog.jndi-name`.
- `acme.catalog.url-enabled=true` và cung cấp `acme.catalog.url`.

Nếu không bật lựa chọn nào, cấu hình không được áp dụng và không tạo bean. Nếu bật cả hai, `AnyNestedCondition` vẫn khớp vì đây là OR bao hàm; ví dụ sẽ từ chối cấu hình mơ hồ bằng lỗi rõ ràng.

### 5.1. Cấu trúc dự án

```text
any-nested-condition-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/demo/catalog/
    │       ├── CatalogConnectionSettings.java
    │       └── autoconfigure/
    │           └── CatalogAutoConfiguration.java
    └── test/
        └── java/demo/catalog/autoconfigure/
            └── CatalogAutoConfigurationTests.java
```

### 5.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>any-nested-condition-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

`spring-boot-autoconfigure` cung cấp các annotation và composite condition. `spring-boot-starter-test` cung cấp JUnit 5, AssertJ và `ApplicationContextRunner` cho các bài test.

### 5.3. CatalogConnectionSettings.java

```java
package demo.catalog;

public record CatalogConnectionSettings(
        String strategy,
        String location) {
}
```

Record này biểu diễn lựa chọn kết nối đã được cấu hình. `strategy` có giá trị `jndi` hoặc `url`; `location` chứa JNDI name hoặc URL tương ứng.

### 5.4. CatalogAutoConfiguration.java

```java
package demo.catalog.autoconfigure;

import demo.catalog.CatalogConnectionSettings;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.AnyNestedCondition;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ConfigurationCondition.ConfigurationPhase;
import org.springframework.core.env.Environment;

@AutoConfiguration
public class CatalogAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @Conditional(OnCatalogConnectionConfigured.class)
    static class CatalogConnectionConfiguration {

        @Bean
        CatalogConnectionSettings catalogConnectionSettings(
                Environment environment) {

            boolean jndiEnabled = environment.getProperty(
                    "acme.catalog.jndi-enabled",
                    Boolean.class,
                    false);

            boolean urlEnabled = environment.getProperty(
                    "acme.catalog.url-enabled",
                    Boolean.class,
                    false);

            if (jndiEnabled == urlEnabled) {
                throw new IllegalStateException(
                        "Enable exactly one of acme.catalog.jndi-enabled "
                                + "or acme.catalog.url-enabled.");
            }

            if (jndiEnabled) {
                String jndiName = requireText(
                        environment.getProperty("acme.catalog.jndi-name"),
                        "acme.catalog.jndi-name");

                return new CatalogConnectionSettings("jndi", jndiName);
            }

            String url = requireText(
                    environment.getProperty("acme.catalog.url"),
                    "acme.catalog.url");

            return new CatalogConnectionSettings("url", url);
        }

        private static String requireText(String value, String propertyName) {
            if (value == null || value.isBlank()) {
                throw new IllegalStateException(
                        "Property " + propertyName + " must have a value.");
            }
            return value;
        }
    }

    static class OnCatalogConnectionConfigured extends AnyNestedCondition {

        OnCatalogConnectionConfigured() {
            super(ConfigurationPhase.PARSE_CONFIGURATION);
        }

        @ConditionalOnProperty(
                prefix = "acme.catalog",
                name = "jndi-enabled",
                havingValue = "true")
        static class JndiEnabled {
        }

        @ConditionalOnProperty(
                prefix = "acme.catalog",
                name = "url-enabled",
                havingValue = "true")
        static class UrlEnabled {
        }
    }
}
```

Đọc cấu hình theo từng phần:

1. `OnCatalogConnectionConfigured` kế thừa `AnyNestedCondition`, nên condition tổng khớp nếu `JndiEnabled` hoặc `UrlEnabled` khớp.
2. Mỗi nested class dùng `@ConditionalOnProperty` với `havingValue="true"`. Vì vậy giá trị thiếu, `false` hoặc chuỗi khác `true` không bật nhánh đó.
3. `CatalogConnectionConfiguration` chỉ được áp dụng khi composite condition khớp.
4. Bean method đọc lại các cờ để biết người dùng chọn nhánh nào, rồi lấy giá trị JNDI name hoặc URL tương ứng.
5. Nếu cả hai cờ cùng true, bean method báo lỗi vì ví dụ yêu cầu đúng một phương án.
6. Nếu bật một cờ nhưng thiếu giá trị location, bean method fail-fast với tên property cần bổ sung.

Condition OR và kiểm tra “chính xác một” là hai trách nhiệm riêng. `AnyNestedCondition` chỉ đảm bảo có ít nhất một nhánh khớp; phần kiểm tra loại trừ lẫn nhau nằm trong factory method.

### 5.5. Đăng ký auto-configuration trong JAR

Khi phát hành thư viện để Spring Boot tự phát hiện, thêm file:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Nội dung:

```text
demo.catalog.autoconfigure.CatalogAutoConfiguration
```

Ví dụ test tiếp theo gọi trực tiếp class bằng `AutoConfigurations.of(...)`, nên không cần đọc file imports. Với một consumer integration test kiểm tra JAR đã đóng gói, cần xác nhận resource imports này có trong artifact.

## 6. Kiểm thử các nhánh với ApplicationContextRunner

`ApplicationContextRunner` tạo một context nhỏ cho từng tổ hợp property. Đây là cách thuận tiện để xác nhận nhánh nào khớp và bean nào được đăng ký.

### 6.1. CatalogAutoConfigurationTests.java

```java
package demo.catalog.autoconfigure;

import demo.catalog.CatalogConnectionSettings;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    CatalogAutoConfiguration.class));

    @Test
    void noAlternativeDoesNotCreateTheBean() {
        contextRunner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context)
                    .doesNotHaveBean(CatalogConnectionSettings.class);
        });
    }

    @Test
    void jndiAlternativeCreatesTheBean() {
        contextRunner
                .withPropertyValues(
                        "acme.catalog.jndi-enabled=true",
                        "acme.catalog.jndi-name=java:comp/env/jdbc/catalog")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(
                            CatalogConnectionSettings.class);

                    assertThat(context.getBean(
                            CatalogConnectionSettings.class))
                            .isEqualTo(new CatalogConnectionSettings(
                                    "jndi",
                                    "java:comp/env/jdbc/catalog"));
                });
    }

    @Test
    void urlAlternativeCreatesTheBean() {
        contextRunner
                .withPropertyValues(
                        "acme.catalog.url-enabled=true",
                        "acme.catalog.url=https://catalog.example.test")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(
                            CatalogConnectionSettings.class);

                    assertThat(context.getBean(
                            CatalogConnectionSettings.class))
                            .isEqualTo(new CatalogConnectionSettings(
                                    "url",
                                    "https://catalog.example.test"));
                });
    }

    @Test
    void bothAlternativesAreRejectedAsAmbiguous() {
        contextRunner
                .withPropertyValues(
                        "acme.catalog.jndi-enabled=true",
                        "acme.catalog.jndi-name=java:comp/env/jdbc/catalog",
                        "acme.catalog.url-enabled=true",
                        "acme.catalog.url=https://catalog.example.test")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasStackTraceContaining(
                                    "Enable exactly one of acme.catalog.jndi-enabled");
                });
    }

    @Test
    void enabledUrlRequiresANonBlankUrl() {
        contextRunner
                .withPropertyValues(
                        "acme.catalog.url-enabled=true",
                        "acme.catalog.url=")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasStackTraceContaining(
                                    "Property acme.catalog.url must have a value.");
                });
    }
}
```

### 6.2. Chạy kiểm thử

Từ thư mục chứa `pom.xml`, dùng JDK 17+ và Maven:

```bash
mvn test
```

Với năm test trên, kết quả mong đợi là:

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

Đây là kết quả kỳ vọng của ví dụ, không phải log của một lần chạy đã thực thi. Maven Surefire có thể hiển thị thêm tên test và thời gian thực thi.

### 6.3. Ma trận test

| Test | JNDI flag | URL flag | Kết quả |
|---|---:|---:|---|
| `noAlternativeDoesNotCreateTheBean` | false/thiếu | false/thiếu | Context thành công, không có bean |
| `jndiAlternativeCreatesTheBean` | true | false/thiếu | Bean dùng strategy `jndi` |
| `urlAlternativeCreatesTheBean` | false/thiếu | true | Bean dùng strategy `url` |
| `bothAlternativesAreRejectedAsAmbiguous` | true | true | Composite condition khớp; factory method từ chối cấu hình |
| `enabledUrlRequiresANonBlankUrl` | false/thiếu | true | Composite condition khớp; factory method báo thiếu URL |

Hai test thành công riêng biệt chứng minh từng nhánh OR có thể kích hoạt configuration. Test không có lựa chọn chứng minh cả hai nhánh đều không khớp thì configuration không được áp dụng. Test bật cả hai chứng minh `AnyNestedCondition` là OR bao hàm, không phải XOR.

## 7. ConfigurationPhase và điều kiện dựa trên bean

Ví dụ trước dùng property condition, nên phase `PARSE_CONFIGURATION` là phù hợp. Nhưng khi một nhánh phụ thuộc vào bean definition, cần xem xét phase cẩn thận.

Ví dụ một integration có thể được bật nếu ứng dụng đã đăng ký `DataSource` **hoặc** `ConnectionFactory`:

```java
static class OnDataSourceOrConnectionFactory extends AnyNestedCondition {

    OnDataSourceOrConnectionFactory() {
        super(ConfigurationPhase.REGISTER_BEAN);
    }

    @ConditionalOnBean(DataSource.class)
    static class OnDataSource {
    }

    @ConditionalOnBean(ConnectionFactory.class)
    static class OnConnectionFactory {
    }
}
```

Ở đây các nhánh dựa trên bean condition, nên `REGISTER_BEAN` là phase cần cân nhắc để các configuration class đã được parse trước khi kiểm tra bean definition.

Tuy nhiên, `@ConditionalOnBean` chỉ nhìn thấy bean definition đã được xử lý tới thời điểm condition chạy. Nếu bean phụ thuộc được đăng ký bởi một auto-configuration khác, cần kiểm soát thứ tự auto-configuration bằng `@AutoConfiguration(after=...)` hoặc cơ chế ordering phù hợp. Không nên dựa vào thứ tự ngẫu nhiên.

Với một composite condition chứa cả property/classpath condition và bean condition, hãy xem xét toàn bộ thành viên và phase cần thiết. Không chọn `PARSE_CONFIGURATION` chỉ vì đó là ví dụ phổ biến trong tài liệu.

## 8. Đọc kết quả trong ConditionEvaluationReport

Khi auto-configuration không chạy như mong đợi, bật debug:

```bash
java -jar app.jar --debug
```

Condition Evaluation Report giúp thấy condition nào khớp và condition nào không khớp. Với `AnyNestedCondition`, hãy tìm:

- Condition tổng có khớp hay không.
- Bao nhiêu nested member khớp.
- Nhánh JNDI hoặc URL nào không khớp.
- Condition khác trên configuration bên ngoài có đang chặn cấu hình hay không.

`AnyNestedCondition` tổng hợp outcome của các nested member và thông điệp của từng nhánh. Nếu ít nhất một nhánh khớp, outcome tổng khớp. Nếu không nhánh nào khớp, configuration được bảo vệ sẽ không được áp dụng.

Nếu condition tổng khớp nhưng bean vẫn không xuất hiện, kiểm tra tiếp các điều kiện khác trên `@Bean` method, `@ConditionalOnMissingBean`, lỗi tạo bean hoặc exception trong factory method. Composite condition chỉ quyết định một tầng của quá trình đăng ký bean.

Trong test, có thể thêm listener để in report:

```java
new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(
                        LogLevel.INFO))
        .withConfiguration(
                AutoConfigurations.of(CatalogAutoConfiguration.class))
        .run(context -> {
            // Assertions
        });
```

Cần import:

```java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
```

## 9. Khi nào nên dùng AnyNestedCondition?

Dùng `AnyNestedCondition` khi:

- Có hai hoặc nhiều phương án cấu hình thay thế.
- Mỗi phương án có thể mô tả bằng condition annotation riêng.
- Muốn mỗi nhánh có tên và điều kiện rõ ràng.
- Muốn Spring Boot tổng hợp outcome và đưa vào Condition Evaluation Report.
- Muốn kết hợp các nhánh OR với điều kiện chung ở configuration bên ngoài.

Ví dụ thực tế:

| Phương án | Nhánh điều kiện |
|---|---|
| Kết nối qua JNDI hoặc URL | `@ConditionalOnJndi` OR `@ConditionalOnProperty` |
| Có SDK A hoặc SDK B | `@ConditionalOnClass(A.class)` OR `@ConditionalOnClass(B.class)` |
| Một trong hai loại web server có mặt | Servlet condition OR reactive condition |
| Có file cấu hình A hoặc resource B | Resource condition A OR resource condition B |
| Feature bật bởi property A hoặc profile B | Property condition OR profile condition |

### 9.1. Khi nào nên viết Condition thủ công?

Nếu logic chỉ là OR của các annotation condition tiêu chuẩn, `AnyNestedCondition` thường dễ đọc hơn một class tự triển khai `Condition`.

Một custom `Condition` thủ công phù hợp khi cần:

- So sánh nhiều giá trị property theo quy tắc riêng.
- Kiểm tra quan hệ giữa các property, ví dụ hai giá trị phải cùng xuất hiện hoặc loại trừ nhau.
- Đọc một resource theo nội dung, không chỉ kiểm tra tồn tại.
- Tính toán điều kiện từ nhiều nguồn mà annotation có sẵn không biểu diễn được.

Khi tự viết `Condition`, cần triển khai `matches(ConditionContext, AnnotatedTypeMetadata)` và tự bảo đảm thông điệp chẩn đoán đủ rõ. Nếu muốn kiểm soát phase, triển khai thêm `ConfigurationCondition`.

### 9.2. Khi nào không nên dùng?

Không cần `AnyNestedCondition` nếu:

- Chỉ có một condition.
- Tất cả điều kiện phải cùng đúng: dùng các condition AND thông thường hoặc `AllNestedConditions`.
- Cấu hình phải không có bất kỳ lựa chọn nào: cân nhắc `NoneNestedConditions`.
- Logic OR quá nhỏ và một custom condition đơn giản, rõ ràng hơn.
- Các nhánh cần tạo bean implementation hoàn toàn khác nhau và không chia sẻ configuration: đôi khi tách thành hai auto-configuration riêng dễ quản lý hơn.

Đừng tạo một composite condition chỉ để bọc một `@ConditionalOnProperty` duy nhất.

## 10. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Phải bật cả JNDI và URL mới chạy | Dùng hai annotation condition độc lập trên cùng class, tạo logic AND | Dùng `AnyNestedCondition` với một nested class cho mỗi lựa chọn |
| Một trong hai nhánh đúng nhưng condition tổng vẫn false | Nested class có thêm condition AND không thỏa | Kiểm tra toàn bộ annotation trên từng nested class |
| Cả hai nhánh đúng nhưng ứng dụng vẫn lỗi | `AnyNestedCondition` là OR bao hàm; factory method chưa xử lý trường hợp cả hai cùng bật | Đặt quy tắc ưu tiên hoặc validation loại trừ lẫn nhau |
| Nghĩ `AnyNestedCondition` tự chọn implementation | Composite condition chỉ trả về kết quả tổng | Dùng factory method hoặc tách bean theo từng nhánh để chọn implementation |
| Property có mặt nhưng không khớp | `havingValue` không đúng hoặc giá trị là `false` | Kiểm tra giá trị cuối trong Environment và khai báo `havingValue` rõ ràng |
| Dùng mảng `name` trong `@ConditionalOnProperty` để tạo OR | Nhiều tên trong cùng annotation phải cùng khớp | Tạo các nested class riêng trong `AnyNestedCondition` |
| Condition dựa trên bean không thấy bean vừa khai báo | Chọn phase quá sớm hoặc thứ tự auto-configuration chưa đúng | Cân nhắc `REGISTER_BEAN` và ordering |
| Condition khớp nhưng bean không tồn tại | `@ConditionalOnMissingBean`, condition khác hoặc factory method lỗi | Đọc toàn bộ Condition Evaluation Report và startup exception |
| `@ConditionalOnExpression` khó debug | Biểu thức SpEL dài hoặc tham chiếu bean quá sớm | Dùng nested condition nếu logic là OR giữa các annotation có sẵn |
| Tên nested class không phản ánh mục đích | Nhánh condition khó đọc trong code/report | Đặt tên như `JndiEnabled`, `UrlEnabled`, `OnVendorSdk` |

## 11. Quy trình thiết kế và kiểm thử

Khi cần một auto-configuration có nhiều lựa chọn thay thế:

1. Viết logic bằng lời trước: nhánh A hoặc B, và có điều kiện chung nào không?
2. Tách mỗi phương án thành một nested static class.
3. Gắn condition cụ thể lên từng nested class.
4. Kế thừa `AnyNestedCondition` và chọn `ConfigurationPhase` phù hợp.
5. Gắn composite condition bằng `@Conditional` lên configuration cần bảo vệ.
6. Nếu có điều kiện chung, đặt chúng trên configuration bên ngoài để tạo AND với OR tổng.
7. Quyết định rõ trường hợp nhiều nhánh cùng khớp: chấp nhận, chọn ưu tiên hay báo lỗi.
8. Dùng `ApplicationContextRunner` kiểm tra không nhánh nào, từng nhánh riêng và nhiều nhánh cùng khớp.
9. Khi test fail, đọc Condition Evaluation Report để xác định nested member nào không khớp.
10. Kiểm tra bean cuối cùng và lỗi khởi tạo riêng; condition match không bảo đảm factory method tạo bean thành công.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** `AnyNestedCondition` khớp khi nào?

**Đáp án:** Khi ít nhất một nested class condition khớp.

**Câu 2.** Nếu hai nested condition đều khớp, condition tổng có khớp không?

**Đáp án:** Có. Đây là OR bao hàm, không phải XOR.

**Câu 3.** Hai `@ConditionalOnProperty` đặt trên cùng configuration class có tạo OR không?

**Đáp án:** Không. Các condition trên cùng class được kết hợp theo AND.

**Câu 4.** Muốn condition tổng khớp khi mọi nested condition đều đúng, dùng lớp nào?

**Đáp án:** `AllNestedConditions`.

**Câu 5.** Muốn condition tổng khớp khi không nested condition nào đúng, dùng lớp nào?

**Đáp án:** `NoneNestedConditions`.

**Câu 6.** Vì sao ví dụ JNDI/URL vẫn cần kiểm tra khi cả hai flag đều true?

**Đáp án:** `AnyNestedCondition` chỉ kiểm tra có ít nhất một nhánh đúng. Nếu yêu cầu chính xác một nhánh, phải thêm validation hoặc logic loại trừ lẫn nhau.

**Câu 7.** Khi các nested condition dựa trên property và classpath, phase nào thường phù hợp?

**Đáp án:** `PARSE_CONFIGURATION`, vì các condition có thể được đánh giá khi Spring phân tích configuration class.

**Câu 8.** Khi các nested condition cần quan sát bean definition, nên cân nhắc phase nào?

**Đáp án:** `REGISTER_BEAN`, vì lúc này các configuration class đã được phân tích.

## 13. Ghi nhớ

- `AnyNestedCondition` là composite condition của Spring Boot, khớp khi **ít nhất một** nested class condition khớp.
- OR là bao hàm: nhiều nhánh cùng khớp vẫn cho kết quả true.
- Các condition trên cùng một nested class kết hợp theo AND; các nested class được `AnyNestedCondition` kết hợp theo OR.
- Dùng `@Conditional(OnYourCondition.class)` để gắn composite condition vào configuration hoặc bean.
- Chọn `PARSE_CONFIGURATION` cho các condition có thể đánh giá sớm như property/classpath; cân nhắc `REGISTER_BEAN` khi phụ thuộc bean definition.
- `AnyNestedCondition` không tự chọn nhánh hoặc tạo bean; factory method vẫn phải xử lý lựa chọn thực tế.
- Kiểm thử đủ trường hợp không nhánh nào khớp, từng nhánh riêng và nhiều nhánh cùng khớp.
- Dùng Condition Evaluation Report để tìm nhánh cụ thể đang khớp hoặc không khớp.

### Tài liệu chính thức

- [Spring Boot 3.3.13 API — AnyNestedCondition](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/AnyNestedCondition.html)
- [Spring Boot 3.3.13 API — AllNestedConditions](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/AllNestedConditions.html)
- [Spring Boot 3.3.13 API — NoneNestedConditions](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/NoneNestedConditions.html)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Framework 6.1 — ConfigurationCondition.ConfigurationPhase](https://docs.spring.io/spring-framework/docs/6.1.19/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.ConfigurationPhase.html)
