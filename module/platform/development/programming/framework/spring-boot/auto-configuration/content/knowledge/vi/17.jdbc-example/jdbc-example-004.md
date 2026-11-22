# Bean DataSource do người dùng cung cấp và hành vi nhường chỗ của Spring Boot

## 1. Bối cảnh: vì sao một bean DataSource có thể làm Boot dừng tạo bean mặc định?

Trong ứng dụng Spring Boot dùng JDBC, `DataSource` là điểm vào chuẩn để lấy kết nối tới database. Thông thường ứng dụng chỉ cần khai báo:

```properties
spring.datasource.url=jdbc:postgresql://localhost:5432/catalog
spring.datasource.username=catalog_app
spring.datasource.password=change-me
```

Spring Boot đọc cấu hình, chọn một connection pool có trên classpath (thường là HikariCP), rồi đăng ký bean `DataSource` để các thành phần JDBC, transaction, SQL initialization hoặc JPA sử dụng.

Khi cần toàn quyền kiểm soát, ứng dụng có thể tự khai báo một bean `DataSource`. Đây là một extension point được Spring Boot hỗ trợ. Auto-configuration sẽ **nhường chỗ (back off)** cho bean do ứng dụng cung cấp nếu bean đó đáp ứng điều kiện kiểu mà auto-configuration kiểm tra.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
class DatabaseConfiguration {

    @Bean
    DataSource customDataSource() {
        // Tạo DataSource do ứng dụng quản lý.
        // Ví dụ cụ thể ở mục 6.
    }
}
```

Khi bean này được nhận diện là một `DataSource` hợp lệ, Spring Boot không tạo thêm bean `DataSource` mặc định của nhánh embedded/pooling. Các cấu hình JDBC tiếp theo vẫn có thể sử dụng bean mà ứng dụng cung cấp.

**Cần phân biệt hai việc:**

- **Back-off của bean DataSource mặc định:** Boot bỏ qua việc tạo pool/embedded datasource mặc định vì ứng dụng đã cung cấp datasource.
- **Các auto-configuration JDBC khác:** những thành phần như `JdbcTemplate`, database initialization hoặc transaction manager vẫn có thể được cấu hình dựa trên datasource hiện có, nếu các điều kiện riêng của chúng thỏa mãn.

Vì vậy, một bean `DataSource` do người dùng cung cấp không đồng nghĩa toàn bộ hệ sinh thái JDBC của Spring Boot bị tắt.

## 2. Cơ chế back-off hoạt động như thế nào?

Spring Boot dùng `@ConditionalOnMissingBean` để cho phép ứng dụng thay thế một bean mặc định. Với datasource, cấu hình embedded và pooled datasource chỉ được áp dụng khi chưa có datasource phù hợp trong context.

Có thể hình dung:

```text
Classpath có JDBC + Spring JDBC
             |
             v
     DataSourceAutoConfiguration
             |
             +--> Đăng ký DataSourceProperties
             |
             v
  Đã có bean DataSource / XADataSource?
          /                 \
        Có                   Chưa
        |                     |
        v                     v
  Bỏ qua nhánh tạo       Kiểm tra URL, embedded DB,
  DataSource mặc định   connection pool và driver
        |                     |
        v                     v
  Dùng bean do user     Tạo DataSource mặc định
  cung cấp                     |
        |                     |
        +----------+----------+
                   |
                   v
     JdbcTemplate / SQL init / transaction
        có thể dùng DataSource phù hợp
```

Đây là mô hình khái quát. Thực tế, `DataSourceAutoConfiguration` còn có điều kiện classpath, điều kiện liên quan R2DBC, nhánh embedded và nhánh pooled. Mỗi auto-configuration phụ trợ như `JdbcTemplateAutoConfiguration` cũng có điều kiện riêng.

### 2.1. Điều kiện được đánh giá theo bean definition

`@ConditionalOnMissingBean(DataSource.class)` kiểm tra metadata bean mà Spring đã biết tại thời điểm condition được đánh giá. Spring Boot khuyến nghị đặt bean condition như `@ConditionalOnMissingBean` trong **auto-configuration**, vì auto-configuration được xử lý sau các bean definitions do người dùng khai báo.

Do đó, khi tự viết starter:

- Dùng `@ConditionalOnMissingBean(DataSource.class)` trên phương thức `@Bean` tạo datasource mặc định.
- Đặt phương thức trong class `@AutoConfiguration` được đăng ký theo cơ chế của Boot.
- Khai báo kiểu trả về rõ ràng là `DataSource` hoặc implementation cụ thể.
- Không đặt condition quá sớm trong một cấu hình thông thường rồi giả định mọi bean ứng dụng đã được đăng ký.

Kiểu trả về rất quan trọng. Ví dụ `@Bean Object customDataSource()` có thể che giấu thông tin kiểu khỏi quá trình đánh giá condition trước khi method được gọi. Nên khai báo `@Bean DataSource customDataSource()` hoặc `@Bean HikariDataSource customDataSource()`.

### 2.2. Bean cùng tên không phải lúc nào cũng đủ

Cơ chế back-off chủ yếu dựa trên **kiểu bean** mà condition yêu cầu. Chỉ đặt tên bean là `dataSource` nhưng trả về một đối tượng không triển khai `DataSource` không tạo ra datasource thay thế.

Ngược lại, một bean tên `customDataSource` vẫn có thể làm datasource mặc định back off nếu kiểu bean của nó là `DataSource` và nó là ứng viên được condition xét đến.

Không nên bật `spring.main.allow-bean-definition-overriding=true` chỉ để ghi đè bean mặc định bằng cùng tên. Hãy dùng contract back-off theo kiểu và điều kiện được thiết kế cho mục tiêu đó.

## 3. Cấu hình mặc định của Spring Boot khi không có bean thay thế

Nếu ứng dụng không tự cung cấp `DataSource`, Spring Boot có thể tạo datasource từ `spring.datasource.*`.

Ví dụ:

```yaml
spring:
  datasource:
    url: jdbc:h2:mem:catalog;DB_CLOSE_DELAY=-1
    username: sa
    password:
    hikari:
      maximum-pool-size: 10
      connection-timeout: 30000
```

Các giá trị thường gặp:

- `spring.datasource.url`: JDBC URL.
- `spring.datasource.username` và `spring.datasource.password`: thông tin đăng nhập.
- `spring.datasource.driver-class-name`: tên driver nếu Boot không thể suy ra từ URL hoặc cần chỉ định cụ thể.
- `spring.datasource.type`: ép chọn class datasource/pool.
- `spring.datasource.hikari.*`: cấu hình riêng cho HikariCP.
- `spring.datasource.tomcat.*`, `spring.datasource.dbcp2.*` hoặc prefix tương ứng: cấu hình pool implementation khác nếu có dependency.

Spring Boot ưu tiên các connection pool theo thứ tự được tài liệu mô tả: HikariCP, Tomcat JDBC pool, Commons DBCP2 và Oracle UCP. Khi dùng `spring-boot-starter-jdbc` hoặc `spring-boot-starter-data-jpa`, HikariCP thường đã có trên classpath.

Nếu không có URL nhưng có embedded database phù hợp trên classpath, Boot có thể tự cấu hình database nhúng. Nếu cần tắt nhánh embedded, có thể đặt `spring.datasource.embedded-database-connection=none`.

### 3.1. DataSourceProperties vẫn là một phần của auto-configuration

`DataSourceAutoConfiguration` bật `DataSourceProperties` để giữ các cấu hình chuẩn. Khi user cung cấp datasource và nhánh tạo datasource mặc định back off, không nên hiểu rằng mọi property bean hỗ trợ đã biến mất.

Tuy nhiên, **bean datasource tùy chỉnh không tự động nhận mọi `spring.datasource.*`** chỉ vì `DataSourceProperties` tồn tại. Nếu factory của bạn không đọc properties hoặc datasource không được bind bằng `@ConfigurationProperties`, các giá trị đó không tự ghi vào object do bạn tạo.

## 4. Khi người dùng tự định nghĩa một DataSource

### 4.1. Tự tạo bean DataSource

Ví dụ sau dùng `DriverManagerDataSource` của Spring Framework để minh họa một datasource do ứng dụng cung cấp:

```java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

@Configuration(proxyBeanMethods = false)
class CustomDataSourceConfiguration {

    @Bean
    DataSource customDataSource() {
        DriverManagerDataSource dataSource =
                new DriverManagerDataSource();

        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl(
                "jdbc:h2:mem:custom;DB_CLOSE_DELAY=-1"
        );
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        return dataSource;
    }
}
```

`DriverManagerDataSource` không phải connection pool; mỗi lần lấy kết nối, nó tạo kết nối JDBC mới. Đây là implementation đơn giản cho test hoặc demo, không phải lựa chọn mặc định cho tải production.

Khi context có bean này:

- Nhánh tạo datasource mặc định của Boot back off.
- `JdbcTemplate` có thể được auto-configure và sử dụng bean `customDataSource`.
- Các thành phần cần datasource có thể nhận bean này thông qua dependency injection.
- Các cấu hình `spring.datasource.url` không tự ghi đè URL hard-code trong method trên.

### 4.2. Boot vẫn tái sử dụng datasource người dùng

Tài liệu Spring Boot xác nhận datasource do ứng dụng cung cấp được tái sử dụng ở những nơi Boot cần, bao gồm database initialization. Điều này cho phép bạn thay đổi cách tạo kết nối mà vẫn tận dụng các thành phần JDBC khác của Boot.

Ví dụ, nếu ứng dụng dùng `JdbcTemplate`:

```java
@Repository
class ProductRepository {

    private final JdbcTemplate jdbcTemplate;

    ProductRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    Integer countProducts() {
        return jdbcTemplate.queryForObject(
                "select count(*) from products",
                Integer.class
        );
    }
}
```

`JdbcTemplate` nhận datasource phù hợp từ context. Repository không cần biết datasource là Hikari, datasource từ JNDI hay datasource do ứng dụng tự tạo.

Lưu ý: ví dụ repository giả định bảng `products` đã tồn tại; đoạn code chỉ minh họa cách inject và sử dụng `JdbcTemplate`, không tự tạo schema.

### 4.3. Bind cấu hình bên ngoài vào datasource tùy chỉnh

Nếu muốn datasource riêng vẫn được cấu hình từ file YAML, có thể dùng `@ConfigurationProperties` trên bean hoặc dùng `DataSourceProperties` để tạo pool.

Với HikariCP, một cách cấu hình rõ ràng là:

```java
import com.zaxxer.hikari.HikariDataSource;

import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

@Configuration(proxyBeanMethods = false)
class CustomPoolConfiguration {

    @Bean
    @Primary
    @ConfigurationProperties("app.datasource")
    DataSourceProperties dataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @ConfigurationProperties("app.datasource.configuration")
    HikariDataSource customDataSource(
            DataSourceProperties properties) {

        return properties.initializeDataSourceBuilder()
                .type(HikariDataSource.class)
                .build();
    }
}
```

Cấu hình tương ứng:

```yaml
app:
  datasource:
    url: jdbc:postgresql://localhost:5432/catalog
    username: catalog_app
    password: change-me
    configuration:
      maximum-pool-size: 20
      connection-timeout: 30000
```

`DataSourceProperties.initializeDataSourceBuilder()` chuyển các giá trị chuẩn sang builder. Điều này quan trọng vì Hikari dùng thuộc tính `jdbcUrl`, trong khi cấu hình datasource tổng quát dùng `url`. Nếu bind trực tiếp vào `HikariDataSource`, bạn thường phải dùng `jdbc-url` thay cho `url`.

Đây là cấu hình datasource do ứng dụng kiểm soát; vì đã cung cấp bean `DataSource`, Boot không tạo thêm datasource mặc định. `@Primary` trên `DataSourceProperties` ở ví dụ giữ bean properties này làm ứng viên mặc định khi có nhiều bean cùng kiểu.

## 5. Phân biệt một DataSource thay thế và một DataSource bổ sung

Đây là điểm dễ nhầm nhất khi ứng dụng cần nhiều database.

### 5.1. Một datasource do user cung cấp để thay mặc định

Nếu ứng dụng chỉ định nghĩa một bean `DataSource` bình thường, Boot nhận diện datasource đó và nhường chỗ cho bean mặc định.

```java
@Bean
DataSource customDataSource() {
    // ...
}
```

Kết quả: ứng dụng chỉ có datasource do user tạo (cùng các bean phụ trợ khác nếu được cấu hình). Đây là hành vi phù hợp khi bạn muốn thay hoàn toàn datasource mặc định.

### 5.2. Thêm datasource thứ hai nhưng vẫn muốn giữ datasource mặc định

Nếu bạn cần database chính do Boot cấu hình và thêm một database báo cáo, việc khai báo một bean `DataSource` bình thường thứ hai có thể khiến auto-configuration datasource mặc định back off. Để đánh dấu datasource phụ là bean **không phải ứng viên mặc định**, Spring Framework 6.2 cung cấp thuộc tính `defaultCandidate` trên `@Bean`.

Ví dụ theo Spring Boot 3.5:

```java
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.jdbc.DataSourceBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import com.zaxxer.hikari.HikariDataSource;

@Configuration(proxyBeanMethods = false)
class ReportingDataSourceConfiguration {

    @Bean(defaultCandidate = false)
    @Qualifier("reporting")
    HikariDataSource reportingDataSource() {
        return DataSourceBuilder.create()
                .type(HikariDataSource.class)
                .url("jdbc:h2:mem:reporting;DB_CLOSE_DELAY=-1")
                .username("sa")
                .build();
    }
}
```

Khi đó:

- Datasource mặc định của Boot vẫn có thể được tạo từ `spring.datasource.*`.
- `reportingDataSource` vẫn tồn tại và có thể inject khi chỉ định `@Qualifier("reporting")`.
- Bean phụ không chen vào các injection point chỉ yêu cầu kiểu `DataSource` mặc định.
- Các service cần database báo cáo phải chỉ rõ qualifier.

Ví dụ:

```java
@Repository
class ReportingRepository {

    private final JdbcTemplate jdbcTemplate;

    ReportingRepository(
            @Qualifier("reporting") DataSource reportingDataSource) {
        this.jdbcTemplate = new JdbcTemplate(reportingDataSource);
    }
}
```

`defaultCandidate=false` được hỗ trợ từ Spring Framework 6.2, do đó có trong dòng Spring Boot 3.5. Nó khác `autowireCandidate=false`:

| Thuộc tính | Injection không qualifier | Injection có qualifier |
| --- | --- | --- |
| Mặc định | Có thể được xét | Có thể được xét |
| `defaultCandidate=false` | Không là ứng viên mặc định | Vẫn có thể inject khi qualifier khớp |
| `autowireCandidate=false` | Không được xét | Cũng không được inject theo kiểu |

Đây là lý do không nên dùng `autowireCandidate=false` thay thế một cách máy móc cho datasource phụ: datasource vẫn cần được inject ở nơi có qualifier.

### 5.3. Vai trò của @Primary và @Qualifier

- `@Primary` chọn bean ưu tiên khi có nhiều ứng viên phù hợp cho injection không chỉ rõ qualifier.
- `@Qualifier` chỉ định chính xác bean cần inject.
- `@ConditionalOnMissingBean` quyết định auto-configuration có tạo bean mặc định hay không.
- `defaultCandidate=false` đánh dấu bean bổ sung không tham gia như ứng viên mặc định; trong trường hợp datasource thứ hai, nó giúp datasource mặc định của Boot không bị back off.

`@Primary` **không thay thế** `@ConditionalOnMissingBean`. Nếu bạn khai báo hai datasource bình thường, việc đánh dấu một bean là primary không có nghĩa Boot sẽ bỏ qua datasource thứ hai khi đánh giá condition. Nếu muốn giữ datasource auto-configured và thêm datasource phụ, hãy dùng mẫu `defaultCandidate=false` + `@Qualifier` được tài liệu hướng dẫn.

## 6. Ví dụ chạy được: kiểm tra back-off bằng Java 17 và Spring Boot 3.5

Ví dụ sau kiểm tra ba trường hợp:

1. Không có bean DataSource do người dùng cung cấp: Boot tạo Hikari datasource.
2. Có một bean DataSource do người dùng cung cấp: datasource mặc định của Boot back off, còn JdbcTemplate dùng datasource của user.
3. Có một datasource bổ sung đánh dấu `defaultCandidate=false`: datasource mặc định của Boot vẫn được tạo và datasource phụ có thể inject bằng qualifier.

Ví dụ dùng H2 in-memory để không cần database bên ngoài. Các test thực thi câu SQL `SELECT 1` nhằm xác nhận kết nối thực sự hoạt động.

### Cấu trúc thư mục

```text
datasource-backoff-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── DataSourceBackoffTest.java
```

### Tệp pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>datasource-backoff-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>

        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### Tệp src/test/java/example/DataSourceBackoffTest.java

```java
package example;

import javax.sql.DataSource;

import com.zaxxer.hikari.HikariDataSource;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.autoconfigure.jdbc.JdbcTemplateAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import static org.assertj.core.api.Assertions.assertThat;

class DataSourceBackoffTest {

    @Configuration(proxyBeanMethods = false)
    static class UserDataSourceConfiguration {

        @Bean
        DataSource customDataSource() {
            DriverManagerDataSource dataSource =
                    new DriverManagerDataSource();

            dataSource.setDriverClassName("org.h2.Driver");
            dataSource.setUrl(
                    "jdbc:h2:mem:userdb;DB_CLOSE_DELAY=-1"
            );
            dataSource.setUsername("sa");
            dataSource.setPassword("");

            return dataSource;
        }
    }

    record ReportingProbe(JdbcTemplate jdbcTemplate) {}

    @Configuration(proxyBeanMethods = false)
    static class AdditionalDataSourceConfiguration {

        @Bean(defaultCandidate = false)
        @Qualifier("reporting")
        DataSource reportingDataSource() {
            DriverManagerDataSource dataSource =
                    new DriverManagerDataSource();

            dataSource.setDriverClassName("org.h2.Driver");
            dataSource.setUrl(
                    "jdbc:h2:mem:reporting;DB_CLOSE_DELAY=-1"
            );
            dataSource.setUsername("sa");
            dataSource.setPassword("");

            return dataSource;
        }

        @Bean
        ReportingProbe reportingProbe(
                @Qualifier("reporting") DataSource dataSource) {
            return new ReportingProbe(new JdbcTemplate(dataSource));
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    DataSourceAutoConfiguration.class,
                                    JdbcTemplateAutoConfiguration.class
                            )
                    );

    @Test
    void bootCreatesDefaultPooledDataSourceWhenNoUserBeanExists() {
        runner.withPropertyValues(
                        "spring.datasource.url=jdbc:h2:mem:bootdb;DB_CLOSE_DELAY=-1",
                        "spring.datasource.username=sa",
                        "spring.datasource.password="
                )
                .run(context -> {
                    assertThat(context).hasSingleBean(DataSource.class);
                    assertThat(context.getBean(DataSource.class))
                            .isInstanceOf(HikariDataSource.class);

                    assertThat(context).hasSingleBean(JdbcTemplate.class);
                    Integer result = context.getBean(JdbcTemplate.class)
                            .queryForObject("SELECT 1", Integer.class);

                    assertThat(result).isEqualTo(1);
                });
    }

    @Test
    void userDataSourceMakesBootDefaultBackOff() {
        runner.withUserConfiguration(UserDataSourceConfiguration.class)
                .withPropertyValues(
                        "spring.datasource.url=jdbc:h2:mem:ignored;DB_CLOSE_DELAY=-1",
                        "spring.datasource.username=sa",
                        "spring.datasource.password="
                )
                .run(context -> {
                    assertThat(context).hasSingleBean(DataSource.class);
                    assertThat(context).hasBean("customDataSource");
                    assertThat(context).doesNotHaveBean("dataSource");

                    assertThat(context.getBean(DataSource.class))
                            .isInstanceOf(DriverManagerDataSource.class);

                    // Properties bean vẫn được đăng ký.
                    assertThat(context)
                            .hasSingleBean(DataSourceProperties.class);

                    // JdbcTemplate sử dụng DataSource do user cung cấp.
                    Integer result = context.getBean(JdbcTemplate.class)
                            .queryForObject("SELECT 1", Integer.class);

                    assertThat(result).isEqualTo(1);
                });
    }

    @Test
    void additionalNonDefaultCandidateKeepsBootDataSource() {
        runner.withUserConfiguration(AdditionalDataSourceConfiguration.class)
                .withPropertyValues(
                        "spring.datasource.url=jdbc:h2:mem:primarydb;DB_CLOSE_DELAY=-1",
                        "spring.datasource.username=sa",
                        "spring.datasource.password="
                )
                .run(context -> {
                    assertThat(context).hasBean("dataSource");
                    assertThat(context).hasBean("reportingDataSource");
                    assertThat(context.getBeansOfType(DataSource.class))
                            .hasSize(2);

                    // DataSource mặc định của Boot vẫn là ứng viên mặc định.
                    assertThat(context.getBean(DataSource.class))
                            .isInstanceOf(HikariDataSource.class);

                    Integer primaryResult =
                            context.getBean(JdbcTemplate.class)
                                    .queryForObject("SELECT 1", Integer.class);

                    Integer reportingResult =
                            context.getBean(ReportingProbe.class)
                                    .jdbcTemplate()
                                    .queryForObject("SELECT 1", Integer.class);

                    assertThat(primaryResult).isEqualTo(1);
                    assertThat(reportingResult).isEqualTo(1);
                });
    }
}
```

### Chạy chương trình

Trong thư mục có `pom.xml`, dùng JDK 17+ và Maven:

```bash
java -version
mvn -version
mvn test
```

**Kết quả mong đợi:** ba bài kiểm thử JUnit pass, Maven kết thúc với `BUILD SUCCESS` nếu dependency tải thành công. Không có stdout nghiệp vụ cố định vì test dùng assertions và không gọi `System.out.println`. Báo cáo Surefire nằm trong `target/surefire-reports`.

Giải thích từng test:

- **`bootCreatesDefaultPooledDataSourceWhenNoUserBeanExists`:** không có bean user, Boot tạo Hikari datasource từ `spring.datasource.url`; `JdbcTemplate` thực hiện query thành công.
- **`userDataSourceMakesBootDefaultBackOff`:** có `customDataSource`, Boot không tạo bean tên `dataSource` mặc định. `DataSourceProperties` vẫn tồn tại; `JdbcTemplate` dùng datasource user đã cung cấp. Property URL của Boot bị bỏ qua đối với bean custom vì factory không bind nó.
- **`additionalNonDefaultCandidateKeepsBootDataSource`:** datasource báo cáo được đánh dấu `defaultCandidate=false` và qualifier `reporting`. Boot vẫn tạo datasource mặc định; bean phụ được dùng qua `@Qualifier("reporting")`.

Ví dụ thứ ba cần Spring Framework 6.2 trở lên; Spring Boot 3.5 quản lý phiên bản Framework tương thích. Nếu dự án đang ở Boot 3.3 hoặc Framework cũ hơn, không copy thuộc tính `defaultCandidate` mà chưa kiểm tra API có tồn tại; cần nâng phiên bản hoặc thiết kế multi-datasource theo cơ chế phù hợp với version đó.

## 7. Các ảnh hưởng đến JDBC, transaction và database initialization

### 7.1. JdbcTemplate

`JdbcTemplateAutoConfiguration` có thể tạo `JdbcTemplate` dựa trên datasource phù hợp trong context. Khi chỉ có một datasource, việc thay thế bean thường không yêu cầu thay code repository.

Khi có nhiều datasource, một injection point chỉ khai báo `DataSource` có thể trở nên mơ hồ. Dùng `@Primary` cho datasource chính hoặc `@Qualifier` tại injection point để chọn rõ nguồn dữ liệu. Với datasource bổ sung không muốn làm thay đổi lựa chọn mặc định, cân nhắc `defaultCandidate=false`.

### 7.2. SQL initialization

Các script như `schema.sql` và `data.sql` có thể được Boot dùng để khởi tạo database theo chính sách `spring.sql.init.*`. Boot tái sử dụng datasource do ứng dụng cung cấp cho database initialization khi các điều kiện SQL initialization phù hợp.

Nếu custom datasource trỏ tới database khác với datasource bạn dự định, script có thể chạy nhầm nơi. Kiểm tra URL thực tế, profile và thứ tự datasource trước khi bật initialization trên môi trường có dữ liệu.

### 7.3. Transaction manager

Các auto-configuration transaction có thể tạo transaction manager dựa trên datasource hiện có nếu điều kiện của chúng thỏa. Khi ứng dụng có nhiều datasource, cần quyết định transaction manager nào phục vụ repository/service nào và chỉ định qualifier phù hợp nếu có nhiều manager.

Một datasource đơn lẻ không tự giải quyết giao dịch phân tán giữa nhiều database. Nếu một use case cần ghi nhiều nguồn dữ liệu trong cùng một transaction, phải chọn kiến trúc transaction phù hợp (ví dụ XA/JTA khi thực sự cần) thay vì giả định một `@Transactional` mặc định bao phủ tất cả.

### 7.4. JPA và các tích hợp khác

Auto-configuration JPA thường cần một datasource candidate phù hợp để tạo `EntityManagerFactory`. Khi có nhiều datasource, ứng dụng có thể cần cấu hình rõ `EntityManagerFactory`, transaction manager và repository packages cho từng persistence unit. Đừng chỉ tạo thêm bean `DataSource` rồi mong mọi repository tự chọn đúng database.

## 8. Lựa chọn khi nào nên tự cung cấp DataSource?

| Nhu cầu | Lựa chọn |
| --- | --- |
| Chỉ đổi URL, username, password, pool size của datasource chuẩn | Dùng `spring.datasource.*` |
| Chọn Hikari/Tomcat/DBCP2 có hỗ trợ | Dùng `spring.datasource.type` và các property tương ứng |
| Lấy datasource từ JNDI hoặc application server | Dùng `spring.datasource.jndi-name` hoặc bean JNDI phù hợp |
| Dùng implementation tùy biến, wrapper hoặc datasource proxy | Tự đăng ký bean `DataSource` |
| Cần cấu hình một Hikari pool riêng bằng prefix khác | `DataSourceProperties` + `initializeDataSourceBuilder()` |
| Cần database thứ hai trong khi vẫn giữ datasource Boot | `@Bean(defaultCandidate=false)` + `@Qualifier` |
| Muốn thay datasource mặc định hoàn toàn | Bean `DataSource` thông thường; để auto-configuration back off |

Ưu tiên property chuẩn khi chỉ cần thay giá trị. Tự cung cấp bean khi cần kiểm soát implementation, lifecycle, routing hoặc cách lấy connection.

## 9. Những lỗi thường gặp

1. **Khai báo bean trùng tên nhưng sai kiểu.** Condition kiểm tra kiểu `DataSource`, vì thế chỉ đặt tên `dataSource` không đủ để thay datasource mặc định.
2. **Khai báo return type quá rộng.** `@Bean Object customDataSource()` làm condition khó nhận diện kiểu trước khi khởi tạo. Hãy trả về `DataSource` hoặc implementation cụ thể.
3. **Nghĩ rằng spring.datasource.* tự cấu hình bean tùy biến.** Nếu factory tự hard-code URL hoặc không bind properties, Boot không tự ghi cấu hình chuẩn lên object đó.
4. **Tạo hai datasource bình thường và quên back-off.** Một bean bổ sung có thể khiến datasource mặc định của Boot không được tạo. Nếu cần datasource thứ hai, dùng mẫu `defaultCandidate=false`.
5. **Dùng @Primary để ngăn auto-configuration.** `@Primary` chỉ chọn ứng viên injection; nó không phải điều kiện back-off.
6. **Dùng autowireCandidate=false thay defaultCandidate=false.** Cờ này loại bean khỏi cả injection theo qualifier; không phù hợp nếu datasource phụ vẫn cần được inject ở một số nơi.
7. **Inject DataSource không qualifier khi có nhiều candidate.** Có thể gặp lỗi không xác định được bean; chỉ định `@Primary` hoặc `@Qualifier` theo thiết kế.
8. **Dùng DriverManagerDataSource cho production load cao.** Nó không pool connection; chọn pool phù hợp hoặc datasource do hạ tầng quản lý.
9. **Không quản lý pool/lifecycle.** Khi tự tạo Hikari hoặc pool khác, phải cấu hình giới hạn, timeout, validation, shutdown và quan sát pool theo nhu cầu vận hành.
10. **Bỏ qua SQL initialization.** Bean custom có thể khiến `schema.sql` hoặc `data.sql` chạy trên database khác dự kiến. Xác minh datasource được dùng.
11. **Nhầm một bean custom làm tắt mọi JDBC auto-configuration.** DataSource mặc định back off, nhưng JdbcTemplate, transaction hoặc database initialization vẫn có thể hoạt động dựa trên datasource hiện có.
12. **Dùng điều kiện bean quá sớm.** `@ConditionalOnMissingBean` chỉ thấy các bean definitions đã được xử lý. Đặt điều kiện thay thế trong auto-configuration theo khuyến nghị của Spring Boot.

## 10. Cách chẩn đoán khi datasource không như mong đợi

1. Xác nhận dependency: có `spring-jdbc`, driver database và pool implementation cần dùng không?
2. Kiểm tra bean thực tế: tên bean, kiểu class và số lượng datasource.
3. Kiểm tra điều kiện auto-configuration bằng `--debug` hoặc Actuator `/actuator/conditions` nếu endpoint đã được bật.
4. Kiểm tra property nguồn cuối cùng: `spring.datasource.url`, profile, environment variable và CLI args.
5. Kiểm tra driver và JDBC URL bằng một kết nối thử.
6. Với nhiều datasource, xem bean nào là default candidate, bean nào có qualifier và bean nào được đánh dấu primary.
7. Kiểm tra `JdbcTemplate`/transaction manager đang dùng datasource nào; không suy luận chỉ từ tên property.
8. Kiểm tra logs khởi tạo pool và SQL initialization để xác nhận datasource đích.

Lệnh chạy condition report:

```bash
java -jar app.jar --debug
```

Với Actuator, endpoint conditions phải được expose theo cấu hình phù hợp. Không expose endpoint chẩn đoán nhạy cảm ra Internet công khai.

## 11. Checklist trước khi thay datasource mặc định

- [ ] Bean method trả về kiểu `DataSource` hoặc implementation cụ thể.
- [ ] Hiểu rõ auto-configuration nào sẽ back off.
- [ ] Có property binding rõ ràng nếu không muốn hard-code connection info.
- [ ] Chọn implementation phù hợp (pool hay datasource đơn giản).
- [ ] Có giới hạn pool, timeout, validation và shutdown phù hợp.
- [ ] `JdbcTemplate` và transaction manager nhận đúng datasource.
- [ ] Nếu có nhiều datasource, dùng `@Primary`/`@Qualifier` rõ ràng.
- [ ] Nếu chỉ thêm datasource phụ mà muốn giữ datasource Boot, dùng `defaultCandidate=false` và qualifier theo Spring Framework 6.2+.
- [ ] SQL initialization chạy đúng database.
- [ ] Test nhánh mặc định, user replacement và additional datasource.
- [ ] Kiểm tra condition report khi auto-configuration không khớp.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Ứng dụng có một bean `DataSource customDataSource()`. Spring Boot có tạo thêm Hikari datasource mặc định không?  
**Đáp án:** Không, nhánh tạo datasource mặc định back off khi bean user được nhận diện là `DataSource` hợp lệ.

**Câu 2.** Bean custom tên `myDatabase` có thể làm datasource mặc định back off không?  
**Đáp án:** Có. Condition xét kiểu `DataSource`, không bắt buộc tên bean phải là `dataSource`.

**Câu 3.** Khi datasource custom tồn tại, `JdbcTemplate` có còn được auto-configure không?  
**Đáp án:** Có thể. `JdbcTemplateAutoConfiguration` có điều kiện riêng và có thể dùng datasource user cung cấp khi có một candidate phù hợp.

**Câu 4.** `@Primary` có ngăn Boot tạo datasource mặc định không?  
**Đáp án:** Không. Nó giải quyết lựa chọn injection khi có nhiều bean; back-off do `@ConditionalOnMissingBean`.

**Câu 5.** Muốn thêm datasource báo cáo nhưng giữ datasource chính của Boot, nên dùng gì?  
**Đáp án:** Trên Spring Framework 6.2+/Boot 3.5, đánh dấu bean phụ `@Bean(defaultCandidate=false)` và inject nó bằng `@Qualifier`.

**Câu 6.** Vì sao Hikari cần `jdbc-url` nếu bind trực tiếp, nhưng ví dụ `DataSourceProperties` lại cho phép dùng `url`?  
**Đáp án:** Hikari exposes property `jdbcUrl`; `DataSourceProperties.initializeDataSourceBuilder()` xử lý chuyển đổi từ thuộc tính URL chuẩn sang builder của implementation.

**Câu 7.** Tự tạo `DriverManagerDataSource` có phù hợp làm pool production không?  
**Đáp án:** Không. Nó không quản lý pool kết nối; nên dùng connection pool hoặc datasource do hạ tầng cung cấp.

## Tài liệu tham khảo chính thức

- Spring Boot 3.5 Reference — SQL Databases, cấu hình datasource, connection pool và JDBC templates: https://docs.spring.io/spring-boot/3.5/reference/data/sql.html
- Spring Boot 3.5 How-to — Configure a Custom DataSource, DataSourceProperties, Hikari và nhiều datasource: https://docs.spring.io/spring-boot/3.5/how-to/data-access.html
- Spring Boot 3.5 API — `DataSourceAutoConfiguration`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceAutoConfiguration.html
- Spring Boot 3.5 API — `DataSourceProperties`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceProperties.html
- Spring Boot Reference — Creating Your Own Auto-configuration, điều kiện bean và `@ConditionalOnMissingBean`: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Framework 6.2 Reference — Autowiring Collaborators, `defaultCandidate` và `autowireCandidate`: https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-autowire.html

**Ghi nhớ:** Một bean `DataSource` do ứng dụng cung cấp cho Spring Boot biết rằng ứng dụng đã tự quản lý kết nối database, vì thế datasource mặc định sẽ nhường chỗ. Boot vẫn có thể dùng datasource ấy cho JDBC và database initialization. Nếu cần datasource thứ hai mà vẫn muốn giữ datasource mặc định, hãy phân biệt rõ `@Primary`, `@Qualifier` và `@Bean(defaultCandidate=false)`.
