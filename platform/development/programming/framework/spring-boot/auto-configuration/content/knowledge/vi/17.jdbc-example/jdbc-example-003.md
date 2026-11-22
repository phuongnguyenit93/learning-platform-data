# Thuộc tính kết nối và lựa chọn nguồn dữ liệu mặc định

> **Mục tiêu:** Hiểu Spring Boot dùng các thuộc tính `spring.datasource.*` để tạo JDBC `DataSource` như thế nào, cách Boot chọn pool hoặc database nhúng khi không khai báo URL, và khi nào một `DataSource` do ứng dụng cung cấp khiến auto-configuration nhường chỗ. Sau bài này, bạn có thể xác định nguồn dữ liệu mặc định đang được chọn, cấu hình kết nối đúng cho driver/pool, và chủ động chuyển sang một hoặc nhiều `DataSource` tùy chỉnh.

Bài học nằm trong **Spring Boot Auto Configuration → Ví dụ JDBC**, sử dụng Spring Boot 3.3.x và Java 17+. Nội dung tập trung vào JDBC `javax.sql.DataSource`; nó không đồng nhất với kết nối reactive R2DBC (`ConnectionFactory`).

## 1. DataSource là gì và Boot tự cấu hình điều gì?

JDBC cung cấp interface `javax.sql.DataSource` để ứng dụng lấy connection tới database. `DataSource` thường đóng vai trò factory hoặc connection pool, giúp các thành phần như `JdbcTemplate`, Spring Data JDBC và JPA dùng chung cách lấy kết nối.

Trong ứng dụng Spring Boot thông thường, bạn không cần tự viết `@Bean DataSource`. Khi dependency và điều kiện phù hợp, Boot áp dụng `DataSourceAutoConfiguration`, đăng ký một `DataSource` dựa trên cấu hình bên ngoài và các thư viện có trong classpath.

Các phần chính của quá trình:

1. **Classpath:** Có JDBC API, Spring JDBC và driver/pool phù hợp không?
2. **Property binding:** `spring.datasource.*` có cung cấp URL, username, password, driver hoặc JNDI name không?
3. **Lựa chọn implementation:** Pool nào có sẵn? Có bị chỉ định rõ bằng `spring.datasource.type` không?
4. **Back-off:** Ứng dụng đã tự đăng ký `DataSource` chưa? Nếu có, Boot thường nhường phần tạo `DataSource` mặc định.
5. **Sử dụng:** Các bean truy cập dữ liệu nhận `DataSource` qua dependency injection; `JdbcTemplate` và một số thành phần JDBC khác có thể được auto-configure dựa trên bean này.

Một `DataSource` bean đã được tạo không có nghĩa mọi câu lệnh SQL đều chắc chắn thành công. Driver có thể không kết nối được host, tài khoản có thể thiếu quyền, database có thể chưa tồn tại, hoặc schema chưa được khởi tạo. Hãy tách lỗi tạo cấu hình, lỗi mở connection và lỗi thực thi SQL khi chẩn đoán.

## 2. Các thuộc tính kết nối chuẩn: spring.datasource.*

Cấu hình chung nằm dưới prefix `spring.datasource`. Ví dụ PostgreSQL:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: orders_app
    password: ${DB_PASSWORD}
~~~

Các trường quan trọng:

| Property | Ý nghĩa | Lưu ý |
| --- | --- | --- |
| `spring.datasource.url` | JDBC URL của database | Đây là thông tin quan trọng nhất khi kết nối database bên ngoài. |
| `spring.datasource.username` | Tài khoản kết nối | Có thể lấy từ biến môi trường hoặc secret manager. |
| `spring.datasource.password` | Mật khẩu | Không commit giá trị thật vào repository. |
| `spring.datasource.driver-class-name` | Tên đầy đủ của JDBC driver class | Thường có thể suy ra từ URL; nếu khai báo tường minh, class phải có trên runtime classpath. |
| `spring.datasource.type` | Lớp implementation `DataSource` muốn sử dụng | Dùng để chỉ định pool/implementation thay cho lựa chọn tự động. |
| `spring.datasource.jndi-name` | Tên JNDI của DataSource do application server quản lý | Là cách lấy DataSource từ JNDI thay cho tự tạo pool bằng URL/username/password. |
| `spring.datasource.name` | Tên datasource, được dùng trong một số trường hợp như database nhúng | Không phải tên bean thay thế cho `@Qualifier`. |
| `spring.datasource.generate-unique-name` | Yêu cầu tên database nhúng duy nhất | Hữu ích trong test cần context có database riêng. |
| `spring.datasource.embedded-database-connection` | Chọn loại embedded database hoặc `none` | Dùng khi nhiều database nhúng cùng có trên classpath hoặc muốn tắt lựa chọn nhúng. |

Các thuộc tính chung này được bind vào `DataSourceProperties`. Ngoài chúng, mỗi pool có namespace riêng, ví dụ `spring.datasource.hikari.*`, `spring.datasource.tomcat.*`, `spring.datasource.dbcp2.*` hoặc `spring.datasource.oracleucp.*`. Không phải mọi thuộc tính pool đều có ý nghĩa với mọi implementation.

### 2.1. JDBC URL và driver

JDBC URL có cấu trúc riêng theo vendor. Ví dụ thường gặp:

| Database | URL mẫu | Driver class thường dùng |
| --- | --- | --- |
| PostgreSQL | `jdbc:postgresql://localhost:5432/orders` | `org.postgresql.Driver` |
| MySQL | `jdbc:mysql://localhost:3306/orders` | `com.mysql.cj.jdbc.Driver` |
| H2 in-memory | `jdbc:h2:mem:orders` | `org.h2.Driver` |

Boot có thể suy ra driver class từ URL đối với phần lớn database. Vì vậy, trong trường hợp bình thường bạn chỉ cần khai báo URL và bảo đảm dependency driver có mặt ở runtime:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

Nếu cần khai báo rõ driver:

~~~properties
spring.datasource.driver-class-name=org.postgresql.Driver
~~~

Tên driver phải tồn tại và load được. Nếu dùng tên class cũ hoặc driver jar không nằm trong runtime classpath, việc tạo pool có thể thất bại trước cả khi truy vấn SQL.

**Không nhầm URL với tên database:** URL thường chứa host, port và database/service name. Sai port, sai tên database hoặc thiếu tham số SSL có thể khiến kết nối bị từ chối hoặc bị database từ chối xác thực dù username/password đúng.

### 2.2. Quản lý credentials

Trong môi trường thật, tránh đặt mật khẩu trực tiếp trong YAML được commit. Có thể dùng biến môi trường:

~~~yaml
spring:
  datasource:
    url: ${SPRING_DATASOURCE_URL}
    username: ${SPRING_DATASOURCE_USERNAME}
    password: ${SPRING_DATASOURCE_PASSWORD}
~~~

Spring Boot cũng hỗ trợ biến môi trường theo tên property thông thường; ví dụ `SPRING_DATASOURCE_URL`, `SPRING_DATASOURCE_USERNAME` và `SPRING_DATASOURCE_PASSWORD`. Khi dùng placeholder, ứng dụng phải thực sự nhận được biến tương ứng từ process/container/IDE. Không in password ra log khi debug.

## 3. Boot chọn DataSource mặc định như thế nào?

Lựa chọn phụ thuộc URL, database nhúng, driver và pool có sẵn. Hãy phân biệt hai quyết định: **database nào được kết nối** và **implementation DataSource/pool nào được dùng**.

### 3.1. Có URL kết nối database bên ngoài

Khi `spring.datasource.url` được cung cấp, Boot sử dụng URL cùng credentials/driver để cấu hình datasource có pool. Pool cần một JDBC driver hợp lệ có thể load được.

Ví dụ:

~~~properties
spring.datasource.url=jdbc:postgresql://db.internal:5432/orders
spring.datasource.username=orders_app
spring.datasource.password=${DB_PASSWORD}
~~~

Nếu driver PostgreSQL có trên classpath và pool phù hợp có sẵn, Boot có thể tạo pooled `DataSource`. URL chỉ định database; classpath và cấu hình pool quyết định implementation.

### 3.2. Không có URL: thử embedded database

Nếu không có `spring.datasource.url`, Boot thử cấu hình database nhúng khi một implementation phù hợp có trên classpath. Các database nhúng được hỗ trợ gồm:

- H2
- HSQL
- Apache Derby

Chúng phù hợp cho demo, test hoặc một số công cụ nội bộ. Database in-memory thường không lưu dữ liệu bền vững sau khi process kết thúc. Đừng vô tình để ứng dụng production dùng H2 nhúng chỉ vì dependency H2 còn nằm trên classpath.

Nếu có nhiều embedded database cùng tồn tại, có thể chọn rõ bằng `spring.datasource.embedded-database-connection`. Giá trị `none` tắt lựa chọn embedded database. Trong test, `spring.datasource.generate-unique-name=true` giúp các application context không vô tình dùng chung một database nhúng có tên mặc định.

Ví dụ dependency H2 cho test:

~~~groovy
dependencies {
    testRuntimeOnly 'com.h2database:h2'
}
~~~

Ví dụ cấu hình test:

~~~properties
spring.datasource.generate-unique-name=true
~~~

### 3.3. Pool nào được chọn?

Trong Spring Boot 3.3, khi Boot tự chọn pool theo classpath, thứ tự ưu tiên là:

1. **HikariCP** nếu có.
2. Tomcat JDBC connection pool nếu HikariCP không có.
3. Commons DBCP2 nếu hai lựa chọn trên không có.
4. Oracle UCP nếu các pool trước không có và UCP có sẵn.

`spring-boot-starter-jdbc` và `spring-boot-starter-data-jpa` mặc định kéo theo HikariCP. Vì vậy nhiều ứng dụng thấy Hikari ngay cả khi không tự khai báo dependency Hikari riêng.

Bạn có thể chỉ định pool bằng property:

~~~properties
spring.datasource.type=com.zaxxer.hikari.HikariDataSource
~~~

Giá trị phải là tên đầy đủ của lớp `DataSource` có trên classpath. Khi chỉ định `spring.datasource.type`, bạn đã quyết định implementation thay cho thuật toán lựa chọn tự động.

**Tóm tắt các trường hợp thường gặp:**

| URL | Embedded DB trên classpath | Pool/driver | Kết quả dự kiến |
| --- | --- | --- | --- |
| Có URL ngoài | Không cần embedded DB | Driver hợp lệ và pool có sẵn | Pooled DataSource kết nối URL đã khai báo |
| Không có URL | Có H2/HSQL/Derby và `spring-jdbc` | Embedded database có thể tạo | Boot có thể dùng database nhúng |
| Không có URL | Không có embedded DB phù hợp | Không có nguồn kết nối thay thế | Không thể xác định datasource mặc định; ứng dụng có thể báo lỗi khi cần DataSource |
| Có user `DataSource` bean | Không quan trọng cho nhánh auto-config mặc định | Ứng dụng tự chọn implementation | DataSource auto-configuration nhường chỗ |

Bảng này mô tả các nhánh phổ biến. Điều kiện classpath và các bean khác trong context vẫn có thể ảnh hưởng kết quả thực tế.

## 4. Thuộc tính riêng của connection pool

Các thuộc tính chuẩn `spring.datasource.url`, `username`, `password` dùng chung cho nhiều implementation. Những tham số riêng như giới hạn pool và timeout phải đặt trong namespace của pool đang sử dụng.

Ví dụ HikariCP:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: orders_app
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 12
      minimum-idle: 2
      connection-timeout: 30000
      idle-timeout: 600000
      max-lifetime: 1800000
~~~

Các property thường gặp:

- `maximum-pool-size`: số connection tối đa pool được phép giữ.
- `minimum-idle`: số connection nhàn rỗi tối thiểu mà pool cố duy trì.
- `connection-timeout`: thời gian tối đa chờ lấy connection từ pool trước khi báo lỗi.
- `idle-timeout`: thời gian một connection nhàn rỗi có thể ở lại pool trước khi được xem xét loại bỏ.
- `max-lifetime`: tuổi thọ tối đa của connection trong pool.

Các con số ở ví dụ chỉ để minh họa cách cấu hình, không phải khuyến nghị dùng cho mọi hệ thống. Pool size cần dựa trên số instance ứng dụng, số luồng đồng thời, thời gian truy vấn và giới hạn connection của database. Nếu mỗi instance mở pool 12 connection và chạy 10 instance, tổng khả năng mở connection có thể lên đến 120, chưa tính công cụ quản trị hoặc service khác.

### 4.1. Đừng nhầm spring.datasource.url với Hikari jdbc-url

Hikari có thuộc tính Java tên `jdbcUrl`, trong khi `DataSourceProperties` dùng tên chung `url`. Khi dùng cấu hình Boot chuẩn `spring.datasource.*`, Boot xử lý việc ánh xạ URL sang implementation pool.

Nhưng nếu tự tạo `HikariDataSource` và bind trực tiếp:

~~~java
@Bean
@ConfigurationProperties("app.datasource")
HikariDataSource customDataSource() {
    return DataSourceBuilder.create()
            .type(HikariDataSource.class)
            .build();
}
~~~

thì Hikari không có property `url`; property trực tiếp của nó là `jdbc-url`. Cấu hình dưới prefix `app.datasource` khi đó cần dùng `app.datasource.jdbc-url`.

Cách linh hoạt hơn là dùng `DataSourceProperties` và `initializeDataSourceBuilder()`; nó giữ hợp đồng property chung là `url` và chuyển sang `jdbcUrl` phù hợp cho Hikari. Phần 7 có ví dụ đầy đủ.

## 5. Khi nào auto-configuration nhường chỗ?

Nếu ứng dụng khai báo một bean kiểu `DataSource`, Spring Boot thường không tạo thêm datasource mặc định. Đây là cơ chế back-off để người dùng kiểm soát cách kết nối.

Ví dụ một datasource do ứng dụng tạo:

~~~java
@Configuration(proxyBeanMethods = false)
class CustomDatabaseConfiguration {

    @Bean
    DataSource customDataSource() {
        return DataSourceBuilder.create()
                .url("jdbc:h2:mem:custom")
                .username("sa")
                .build();
    }
}
~~~

Đây là ví dụ minh họa ngắn; dự án thực tế cần dependency driver H2 và nên externalize các giá trị thay vì hardcode. Khi bean `DataSource` này hiện diện trước lúc auto-configuration đánh giá điều kiện, Boot không thêm datasource mặc định.

Điều đó có một hệ quả quan trọng: nếu bạn chỉ thêm một `DataSource` phụ vào ứng dụng và mong Boot tiếp tục tạo datasource mặc định cho database chính, việc khai báo bean tùy chỉnh có thể làm auto-configuration lùi lại. Khi cần nhiều nguồn dữ liệu, hãy định nghĩa và cấu hình rõ **cả hai** datasource, rồi đánh dấu nguồn mặc định bằng `@Primary`.

Không dùng `@Primary` để thay thế back-off. `@Primary` chỉ giúp Spring chọn bean ưu tiên khi có nhiều candidate cùng kiểu; nó không ngăn Boot tạo bean mặc định. Back-off và chọn candidate là hai cơ chế riêng.

### 5.1. Khi nào dùng JNDI?

Trong application server có khả năng quản lý connection pool, ứng dụng có thể lấy datasource bằng JNDI:

~~~properties
spring.datasource.jndi-name=java:jboss/datasources/orders
~~~

Khi đó ứng dụng tham chiếu DataSource do server đăng ký tại JNDI name. Đây là lựa chọn thay thế cho việc khai báo `spring.datasource.url`, `username` và `password` để tự cấu hình datasource. Tên JNDI phải tồn tại trong runtime container; chạy cùng cấu hình trên một môi trường không có resource đó sẽ thất bại.

## 6. Ví dụ JDBC tối giản với Spring Boot

Để hình dung cấu hình chuẩn, một ứng dụng Maven có thể dùng:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

File `src/main/resources/application.yml`:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: orders_app
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 12
      connection-timeout: 30000
~~~

Một bean có thể nhận `JdbcTemplate` mà không cần tự tạo datasource:

~~~java
package example.jdbc;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class HealthRepository {

    private final JdbcTemplate jdbcTemplate;

    public HealthRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public Integer databaseVersion() {
        return jdbcTemplate.queryForObject(
                "select 1",
                Integer.class);
    }
}
~~~

`JdbcTemplate` được Boot auto-configure khi có `DataSource` phù hợp và các điều kiện liên quan. Repository trên dùng câu SQL `select 1` để xác nhận một truy vấn đơn giản; câu SQL kiểm tra cụ thể có thể khác giữa các database. Ví dụ không yêu cầu tạo bean `JdbcTemplate` thủ công.

## 7. Tự cấu hình một DataSource bằng DataSourceProperties

Khi cần tự chọn Hikari hoặc pool khác, `DataSourceProperties` giúp tái sử dụng các thuộc tính kết nối chung:

**Tệp:** `src/main/java/example/jdbc/CustomDataSourceConfiguration.java`

~~~java
package example.jdbc;

import com.zaxxer.hikari.HikariDataSource;
import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CustomDataSourceConfiguration {

    @Bean
    @ConfigurationProperties("app.datasource")
    public DataSourceProperties appDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @ConfigurationProperties("app.datasource.configuration")
    public HikariDataSource appDataSource(
            DataSourceProperties appDataSourceProperties) {

        return appDataSourceProperties
                .initializeDataSourceBuilder()
                .type(HikariDataSource.class)
                .build();
    }
}
~~~

Cấu hình:

~~~yaml
app:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: orders_app
    password: ${DB_PASSWORD}
    configuration:
      maximum-pool-size: 12
      connection-timeout: 30000
~~~

`DataSourceProperties.initializeDataSourceBuilder()` tạo builder từ URL, username, password, driver và type đã bind. `.type(HikariDataSource.class)` chọn Hikari rõ ràng; namespace `.configuration` bind các property riêng của Hikari sau khi builder tạo object.

Vì đây là datasource tùy chỉnh, Boot không còn tạo datasource mặc định theo nhánh auto-configuration. Trong một ứng dụng hoàn chỉnh, các bean truy cập JDBC sẽ dùng datasource này nếu chỉ có một candidate phù hợp.

Nếu đặt tên bean là `appDataSource` thay vì `dataSource`, việc tiêm theo type vẫn có thể hoạt động khi chỉ có một bean; nếu có nhiều candidate, hãy dùng `@Primary` và `@Qualifier` như phần kế tiếp.

## 8. Nhiều DataSource: Primary và Qualifier

Một ứng dụng có thể kết nối database nghiệp vụ và database báo cáo. Mỗi datasource cần prefix riêng, `DataSourceProperties` riêng và pool configuration riêng.

**Tệp:** `src/main/java/example/jdbc/MultiDataSourceConfiguration.java`

~~~java
package example.jdbc;

import com.zaxxer.hikari.HikariDataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.autoconfigure.jdbc.DataSourceProperties;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

@Configuration(proxyBeanMethods = false)
public class MultiDataSourceConfiguration {

    @Bean
    @Primary
    @ConfigurationProperties("app.datasource.primary")
    DataSourceProperties primaryDataSourceProperties() {
        return new DataSourceProperties();
    }

    @Bean
    @Primary
    @ConfigurationProperties("app.datasource.primary.configuration")
    HikariDataSource primaryDataSource(
            @Qualifier("primaryDataSourceProperties")
            DataSourceProperties properties) {

        return properties.initializeDataSourceBuilder()
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
            DataSourceProperties properties) {

        return properties.initializeDataSourceBuilder()
                .type(HikariDataSource.class)
                .build();
    }
}
~~~

Ví dụ cấu hình YAML:

~~~yaml
app:
  datasource:
    primary:
      url: jdbc:postgresql://localhost:5432/orders
      username: orders_app
      password: ${ORDERS_DB_PASSWORD}
      configuration:
        maximum-pool-size: 16

    reporting:
      url: jdbc:postgresql://localhost:5432/reports
      username: reports_app
      password: ${REPORTS_DB_PASSWORD}
      configuration:
        maximum-pool-size: 6
~~~

Cách hoạt động:

- `primaryDataSourceProperties` và `primaryDataSource` đều là `@Primary`, nên các auto-configuration khác cần một datasource mặc định theo type có candidate ưu tiên.
- `reportingDataSourceProperties` và `reportingDataSource` được lấy riêng bằng `@Qualifier`.
- Vì ứng dụng tự khai báo DataSource, auto-configuration datasource mặc định của Boot nhường chỗ.
- Các DAO/service cần database báo cáo phải inject rõ `@Qualifier("reportingDataSource")`.

Ví dụ injection:

~~~java
package example.jdbc;

import javax.sql.DataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ReportingRepository {

    private final JdbcTemplate jdbcTemplate;

    public ReportingRepository(
            @Qualifier("reportingDataSource") DataSource dataSource) {
        this.jdbcTemplate = new JdbcTemplate(dataSource);
    }
}
~~~

Nếu dùng JPA với nhiều datasource, việc tạo hai `DataSource` mới chỉ là bước đầu. Thông thường còn cần `EntityManagerFactory`, transaction manager và cấu hình repository tương ứng cho mỗi database. Không giả định Boot sẽ tự suy ra toàn bộ mapping JPA cho mọi datasource chỉ vì có nhiều bean.

## 9. Kiểm thử lựa chọn DataSource bằng ApplicationContextRunner

`ApplicationContextRunner` cho phép dựng context nhỏ, nạp `DataSourceAutoConfiguration` và thay đổi property/bean để kiểm tra các nhánh auto-configuration mà không cần khởi chạy cả web server.

Ví dụ dưới đây là một tệp test Java hoàn chỉnh cho Java 17+, Spring Boot 3.3.x, JUnit Jupiter, AssertJ, `spring-boot-starter-jdbc` và H2 trong test runtime.

**Tệp:** `src/test/java/example/jdbc/DataSourceAutoConfigurationTest.java`

~~~java
package example.jdbc;

import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabase;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseBuilder;
import org.springframework.jdbc.datasource.embedded.EmbeddedDatabaseType;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import com.zaxxer.hikari.HikariDataSource;

import static org.assertj.core.api.Assertions.assertThat;

class DataSourceAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(DataSourceAutoConfiguration.class));

    @Test
    void jdbcUrlCreatesHikariDataSourceAndInfersDriver() {
        runner.withPropertyValues(
                "spring.datasource.url=jdbc:h2:mem:orders;DB_CLOSE_DELAY=-1",
                "spring.datasource.username=sa",
                "spring.datasource.password=",
                "spring.datasource.hikari.maximum-pool-size=4")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(DataSource.class);

                    DataSource dataSource = context.getBean(DataSource.class);
                    assertThat(dataSource).isInstanceOf(HikariDataSource.class);
                    assertThat(((HikariDataSource) dataSource)
                            .getMaximumPoolSize()).isEqualTo(4);

                    try (var connection = dataSource.getConnection()) {
                        assertThat(connection.isValid(1)).isTrue();
                    }
                });
    }

    @Test
    void missingUrlUsesEmbeddedH2WhenAvailable() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(DataSource.class);
            assertThat(context.getBean(DataSource.class))
                    .isInstanceOf(EmbeddedDatabase.class);
        });
    }

    @Test
    void userDataSourceMakesDefaultAutoConfigurationBackOff() {
        runner.withUserConfiguration(UserDataSourceConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(DataSource.class);
                    assertThat(context).hasBean("customDataSource");
                    assertThat(context.getBean(DataSource.class))
                            .isInstanceOf(EmbeddedDatabase.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserDataSourceConfiguration {

        @Bean
        DataSource customDataSource() {
            return new EmbeddedDatabaseBuilder()
                    .setType(EmbeddedDatabaseType.H2)
                    .generateUniqueName(true)
                    .build();
        }
    }
}
~~~

**Dependency test cần có:**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
}
~~~

Chạy:

~~~bash
mvn -Dtest=DataSourceAutoConfigurationTest test
# Hoặc Gradle wrapper trên Linux/macOS:
./gradlew test --tests example.jdbc.DataSourceAutoConfigurationTest
~~~

**Kết quả mong đợi:** 3 test PASS khi các dependency ở trên đã được cấu hình đúng:

1. Có JDBC URL H2: Boot tạo HikariDataSource, driver được suy từ URL và pool nhận `maximum-pool-size=4`; phép kiểm tra connection trả về `true`.
2. Không có URL: H2 có mặt trong test runtime nên Boot có thể chọn embedded database.
3. Có bean `customDataSource`: auto-configuration không tạo thêm datasource mặc định.

Không có stdout cố định vì các test dùng assertion. Test thứ nhất thực sự mở connection tới H2 in-memory; hai test còn lại kiểm tra loại bean và back-off. Nếu muốn test PostgreSQL/MySQL thật, dùng Testcontainers hoặc môi trường database kiểm thử riêng thay cho giả định H2 mô phỏng đầy đủ hành vi của production server.

## 10. Chẩn đoán lỗi kết nối thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| `Failed to determine a suitable driver class` | Không có URL/embedded database phù hợp hoặc driver không được load | Xác nhận `spring.datasource.url`, dependency driver runtime và `spring.datasource.driver-class-name` |
| `No suitable driver` | JDBC URL sai format hoặc driver không có trên classpath | Đối chiếu URL theo vendor và runtime dependency tree |
| `Connection refused` | Host/port sai, database chưa chạy, firewall hoặc network policy | Kiểm tra DNS, TCP port, container/service và network route |
| `Unknown database` hoặc database not found | Tên database/service trong URL không tồn tại hoặc không được phép truy cập | Kiểm tra database name và cấu hình server |
| `Access denied` / authentication failure | Username/password sai hoặc user thiếu quyền | Kiểm tra secret đang được inject vào process và quyền database |
| Timeout khi lấy connection | Pool cạn connection, query giữ connection quá lâu, database chậm hoặc không truy cập được | Phân biệt pool acquisition timeout với network/connect timeout; xem metrics và log pool |
| Hikari không nhận URL khi custom binding | Bind `url` trực tiếp vào `HikariDataSource` | Dùng `jdbc-url` hoặc `DataSourceProperties.initializeDataSourceBuilder()` |
| `NoUniqueBeanDefinitionException` | Nhiều `DataSource` cùng type mà không có candidate rõ ràng | Đánh dấu một bean `@Primary` và dùng `@Qualifier` ở nơi cần datasource phụ |

### 10.1. Kiểm tra theo thứ tự

1. **Property có thực sự được nạp?** Xác định active profile, config import, biến môi trường và command line; nguồn ưu tiên cao hơn có thể ghi đè `application.yml`.
2. **URL có đúng vendor/host/port/database?** Thử kiểm tra kết nối từ cùng môi trường/container nơi ứng dụng chạy.
3. **Driver có trên runtime classpath?** Dependency chỉ nằm ở compile/test scope có thể không có trong executable artifact.
4. **Implementation pool nào được chọn?** Xem `spring.datasource.type` và thư viện pool hiện diện; không đoán từ IDE nếu runtime artifact khác.
5. **Có user DataSource bean nào làm auto-config back off không?** Kiểm tra `@Configuration`, `@Bean`, profile và điều kiện của cấu hình tùy chỉnh.
6. **Lỗi ở bước lấy connection hay thực thi SQL?** Mở connection tối giản trước, rồi mới kiểm tra query, schema và quyền.

Actuator có thể hỗ trợ quan sát cấu hình và health khi được cấu hình phù hợp, nhưng không nên expose thông tin nhạy cảm hoặc chi tiết connection ra môi trường công khai. Không log password hoặc URL chứa credential.

## 11. Phân biệt JDBC DataSource và R2DBC ConnectionFactory

`DataSource` thuộc JDBC và dùng mô hình truy cập database blocking. R2DBC dùng `io.r2dbc.spi.ConnectionFactory` cho truy cập reactive. Hai loại không thể thay thế trực tiếp cho nhau:

| Thành phần | JDBC | R2DBC |
| --- | --- | --- |
| API kết nối | `javax.sql.DataSource` | `io.r2dbc.spi.ConnectionFactory` |
| Property prefix phổ biến | `spring.datasource.*` | `spring.r2dbc.*` |
| Kiểu truy cập | Blocking | Reactive |
| Template thường dùng | `JdbcTemplate` / `JdbcClient` | `DatabaseClient` |
| Driver | JDBC driver | R2DBC driver |

Nếu ứng dụng dùng R2DBC, đừng cấu hình `spring.datasource.url` rồi kỳ vọng nó tạo reactive connection. Tương tự, thêm JDBC starter không tự biến JDBC code thành non-blocking. Chọn stack dựa trên yêu cầu concurrency, transaction, driver và thư viện data access thực tế.

## 12. Các lỗi thiết kế cần tránh

- **Để H2 trên runtime production classpath mà không khai báo URL:** Boot có thể chọn database nhúng thay vì database mong muốn.
- **Khai báo `driver-class-name` cũ:** URL có thể đúng nhưng class driver không còn trong phiên bản dependency đang dùng.
- **Dùng `spring.datasource.hikari.*` khi pool không phải Hikari:** các property đó không cấu hình pool khác.
- **Bind trực tiếp `url` vào HikariDataSource:** Hikari có `jdbc-url`; dùng `DataSourceProperties` để giữ tên property chung.
- **Thêm DataSource thứ hai và mong Boot giữ default DataSource:** user DataSource làm auto-configuration nhường chỗ; hãy định nghĩa cả hai datasource rõ ràng.
- **Quên `@Primary`:** nhiều auto-configuration phía sau cần một datasource candidate theo type và có thể thất bại nếu không xác định được candidate ưu tiên.
- **Dùng `@Primary` thay cho `@Qualifier`:** `@Primary` chỉ chọn mặc định; code truy cập database phụ nên chỉ rõ qualifier để tránh dùng nhầm database.
- **Tối ưu pool bằng cách tăng số connection tùy tiện:** tổng số connection trên mọi instance có thể vượt giới hạn của database.
- **Để credential trong Git:** dùng secret manager, environment hoặc hệ thống quản lý secret phù hợp.
- **Dùng `DataSource` JDBC cho code reactive với kỳ vọng non-blocking:** JDBC vẫn blocking, dù được gọi từ một ứng dụng WebFlux.

## 13. Tự kiểm tra kiến thức

1. `spring.datasource.url` không được khai báo nhưng H2 có trên classpath. Boot có thể làm gì?  
   **Đáp án:** Thử auto-configure embedded H2; điều kiện classpath và embedded database selection quyết định nhánh cụ thể.

2. `spring-boot-starter-jdbc` có mặt và HikariCP nằm trên classpath. Pool mặc định thường là gì?  
   **Đáp án:** HikariCP, vì Boot ưu tiên Hikari trong thuật toán lựa chọn pool.

3. Có thể luôn bỏ `spring.datasource.driver-class-name` không?  
   **Đáp án:** Thường có thể khi driver suy ra được từ JDBC URL và driver jar có mặt. Nếu suy luận không được hoặc cần class cụ thể, khai báo tường minh.

4. Tại sao `DataSourceProperties` hữu ích khi tự tạo HikariDataSource?  
   **Đáp án:** Nó xử lý thuộc tính chung như `url` và chuyển đổi phù hợp sang `jdbcUrl` của Hikari thông qua `initializeDataSourceBuilder()`.

5. Ứng dụng khai báo một bean `DataSource` riêng. Điều gì xảy ra với datasource mặc định?  
   **Đáp án:** DataSource auto-configuration nhường chỗ; bean do ứng dụng khai báo được sử dụng.

6. Khi có hai DataSource, `@Primary` và `@Qualifier` khác nhau thế nào?  
   **Đáp án:** `@Primary` xác định candidate mặc định theo type; `@Qualifier` chọn chính xác bean cần dùng tại injection point.

7. Vì sao kiểm tra `DataSource` bean chưa đủ để chứng minh database production dùng được?  
   **Đáp án:** Cần mở connection và xác nhận network, credentials, database, quyền và query/schema thực tế.

## Tài liệu chính thức

- [Spring Boot 3.3 — SQL Databases](https://docs.spring.io/spring-boot/3.3/reference/data/sql.html): embedded database, `spring.datasource.*`, driver inference, pool priority, `spring.datasource.type`, JNDI và JDBC templates.
- [Spring Boot 3.3 — Configure a Custom DataSource](https://docs.spring.io/spring-boot/3.3/how-to/data-access.html#howto.data-access.configure-custom-datasource): `DataSourceBuilder`, Hikari `jdbc-url`, `DataSourceProperties` và `initializeDataSourceBuilder()`.
- [Spring Boot 3.3 — Configure Two DataSources](https://docs.spring.io/spring-boot/3.3/how-to/data-access.html#howto.data-access.configure-two-datasources): `@Primary`, `@Qualifier`, hai bộ `DataSourceProperties` và pool configuration.
- [Spring Boot 3.3 API — DataSourceProperties](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceProperties.html): thuộc tính kết nối chuẩn và builder initialization.
- [Spring Boot 3.3 API — DataSourceAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceAutoConfiguration.html): điều kiện và cấu trúc auto-configuration datasource.

**Ghi nhớ:** Hãy tách ba quyết định: **database/URL nào được kết nối**, **pool implementation nào được chọn**, và **bean DataSource nào là candidate mặc định**. `spring.datasource.*` mô tả kết nối, classpath/`spring.datasource.type` ảnh hưởng pool, còn bean do ứng dụng khai báo có thể làm Boot back off; khi có nhiều nguồn, dùng `@Primary` cho mặc định và `@Qualifier` cho từng nguồn cụ thể.
