# Lần theo điều kiện của `DataSourceAutoConfiguration`

Chủ đề: Spring Boot Auto Configuration  
Ngữ cảnh: Ví dụ JDBC  
Mục tiêu: Theo dõi từ dependency và classpath đến điều kiện cấp lớp, nhánh embedded database, nhánh connection pool, cơ chế back-off và cấu hình JDBC hiệu lực. Sau bài này, có thể đọc Condition Evaluation Report để giải thích vì sao Spring Boot tạo hoặc bỏ qua `DataSource`.

## 1. `DataSourceAutoConfiguration` chịu trách nhiệm gì?

`DataSourceAutoConfiguration` là auto-configuration của Spring Boot cho JDBC `DataSource`. `DataSource` là abstraction chuẩn của Java (`javax.sql.DataSource`) dùng để lấy JDBC `Connection`. Một `DataSource` thường được tạo từ implementation cụ thể như HikariCP, Tomcat JDBC Pool, Apache DBCP2 hoặc embedded database.

Ứng dụng thường chỉ cần thêm starter và khai báo connection settings:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-jdbc</artifactId>
</dependency>
```

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: app_user
    password: ${DB_PASSWORD}
```

Khi auto-configuration được bật qua `@SpringBootApplication` hoặc `@EnableAutoConfiguration`, Spring Boot xem xét `DataSourceAutoConfiguration`. Nếu các điều kiện phù hợp, nó chọn một nhánh cấu hình và đăng ký bean `DataSource`. Các cấu hình JDBC khác như `JdbcTemplate`, transaction manager hoặc SQL initialization có thể dựa trên bean này.

Điểm quan trọng: `DataSourceAutoConfiguration` không phải một phương thức duy nhất luôn tạo pool. Nó là một cấu hình có nhiều lớp điều kiện. Phải lần theo từng tầng để hiểu tại sao một `DataSource` được tạo, hoặc vì sao một nhánh bị bỏ qua.

## 2. Đọc các điều kiện ở cấp lớp trước

Trong Spring Boot 3.3.x, phần khai báo chính của `DataSourceAutoConfiguration` có cấu trúc tương đương:

```java
@AutoConfiguration(before = SqlInitializationAutoConfiguration.class)
@ConditionalOnClass({
        DataSource.class,
        EmbeddedDatabaseType.class
})
@ConditionalOnMissingBean(type = "io.r2dbc.spi.ConnectionFactory")
@EnableConfigurationProperties(DataSourceProperties.class)
@Import({
        DataSourcePoolMetadataProvidersConfiguration.class,
        DataSourceCheckpointRestoreConfiguration.class
})
public class DataSourceAutoConfiguration {
    // Hai nhánh cấu hình embedded và pooled nằm bên trong.
}
```

Mỗi annotation trả lời một câu hỏi riêng:

| Annotation | Câu hỏi | Ý nghĩa |
| --- | --- | --- |
| `@AutoConfiguration(before = SqlInitializationAutoConfiguration.class)` | Cấu hình này cần đứng trước cấu hình nào? | Sắp xếp auto-configuration để JDBC DataSource có thể được đăng ký trước SQL initialization |
| `@ConditionalOnClass(...)` | API cần thiết có trên classpath không? | Phải có `javax.sql.DataSource` và `EmbeddedDatabaseType` của Spring JDBC |
| `@ConditionalOnMissingBean(type = "io.r2dbc.spi.ConnectionFactory")` | Có bean R2DBC `ConnectionFactory` không? | Nếu đã có, JDBC auto-configuration mặc định nhường chỗ |
| `@EnableConfigurationProperties(DataSourceProperties.class)` | Có nhóm property cấu hình JDBC không? | Đăng ký và bind các khóa `spring.datasource` vào `DataSourceProperties` |
| `@Import(...)` | Có cấu hình hỗ trợ nào được nạp kèm? | Nạp metadata providers và checkpoint/restore support; không đồng nghĩa trực tiếp tạo pool |

### 2.1. Điều kiện classpath

`javax.sql.DataSource` thuộc Java SQL API. `EmbeddedDatabaseType` thuộc Spring JDBC. Nếu thiếu Spring JDBC trên runtime classpath, điều kiện class không thỏa và `DataSourceAutoConfiguration` không được áp dụng.

Đó là lý do starter có vai trò quan trọng:

- `spring-boot-starter-jdbc` kéo theo Spring JDBC và HikariCP.
- `spring-boot-starter-data-jpa` cũng đưa các thành phần JDBC cần thiết vào dependency graph.
- Chỉ thêm JDBC driver nhưng thiếu thư viện Spring JDBC có thể chưa đủ để bật auto-configuration.

Nếu report cho biết thiếu `EmbeddedDatabaseType`, hãy kiểm tra dependency `spring-jdbc` và dependency graph trước khi sửa `application.yml`.

### 2.2. Vì sao R2DBC `ConnectionFactory` làm JDBC lùi lại?

Điều kiện cấp lớp kiểm tra sự vắng mặt của kiểu bean `io.r2dbc.spi.ConnectionFactory`. Khi một `ConnectionFactory` R2DBC đã được đăng ký, JDBC `DataSourceAutoConfiguration` mặc định không tham gia. Đây là cách Spring Boot tránh tự động đưa JDBC blocking vào cấu hình ứng dụng reactive.

Hai API không giống nhau:

| JDBC | R2DBC |
| --- | --- |
| `javax.sql.DataSource` | `io.r2dbc.spi.ConnectionFactory` |
| `java.sql.Connection` | `io.r2dbc.spi.Connection` |
| API blocking | API reactive/non-blocking |
| Ví dụ `JdbcTemplate` | Ví dụ `DatabaseClient` |

Nếu ứng dụng thực sự cần cả JDBC lẫn R2DBC, có thể chủ động import `DataSourceAutoConfiguration` để bật JDBC. Tuy nhiên, cần cân nhắc việc dùng API blocking trong ứng dụng reactive và quản lý thread phù hợp; không nên import chỉ để ép một condition match mà chưa hiểu tác động.

### 2.3. `DataSourceProperties` được đăng ký ở tầng nào?

Khi điều kiện cấp lớp khớp, `@EnableConfigurationProperties(DataSourceProperties.class)` đăng ký object cấu hình. Các thuộc tính thường gặp gồm:

- `spring.datasource.url`
- `spring.datasource.username`
- `spring.datasource.password`
- `spring.datasource.driver-class-name`
- `spring.datasource.type`
- `spring.datasource.jndi-name`
- Các thiết lập liên quan đến embedded database và XA.

`DataSourceProperties` có trách nhiệm suy luận một số giá trị như URL, driver class, username và password. Ví dụ, Spring Boot có thể suy luận driver từ JDBC URL; nếu không có URL nhưng embedded database có sẵn, nó có thể xác định URL cho embedded database.

Việc `DataSourceProperties` tồn tại chưa chứng minh `DataSource` đã được tạo. Đây mới là phần cấu hình đầu vào. Hai nhánh bên trong mới quyết định có đăng ký bean nguồn dữ liệu hay không.

## 3. Hai nhánh chính: embedded database và pooled DataSource

`DataSourceAutoConfiguration` có hai nested configuration quan trọng:

```java
@Configuration(proxyBeanMethods = false)
@Conditional(EmbeddedDatabaseCondition.class)
@ConditionalOnMissingBean({
        DataSource.class,
        XADataSource.class
})
@Import(EmbeddedDataSourceConfiguration.class)
protected static class EmbeddedDatabaseConfiguration {
}

@Configuration(proxyBeanMethods = false)
@Conditional(PooledDataSourceCondition.class)
@ConditionalOnMissingBean({
        DataSource.class,
        XADataSource.class
})
@Import({
        DataSourceConfiguration.Hikari.class,
        DataSourceConfiguration.Tomcat.class,
        DataSourceConfiguration.Dbcp2.class,
        DataSourceConfiguration.OracleUcp.class
})
protected static class PooledDataSourceConfiguration {
}
```

Mã trên thể hiện cấu trúc và các condition quan trọng của dòng Boot 3.3; danh sách lớp pool có thể thay đổi theo version và classpath. Cần đọc API/source đúng phiên bản đang dùng nếu muốn dựa vào một implementation cụ thể.

Hai nhánh đều kiểm tra rằng ứng dụng chưa có `DataSource` hoặc `XADataSource`. Nhưng điều kiện chọn embedded và pooled khác nhau.

### 3.1. Nhánh embedded database

Spring Boot có thể tự tạo embedded database nếu dependency tương ứng có trên classpath, ví dụ:

- H2.
- HSQLDB.
- Derby (đã bị deprecated trong các tài liệu Spring Boot mới hơn).

Nhánh embedded thường được xem xét khi:

1. `spring.datasource.url` chưa được đặt thành giá trị có nội dung.
2. Không có connection pool được hỗ trợ, hoặc không có cấu hình type pool tường minh khiến nhánh pooled được ưu tiên.
3. `EmbeddedDatabaseType` có trên classpath.
4. Một embedded database được nhận diện từ classpath.

Ví dụ Maven:

```xml
<dependency>
    <groupId>com.h2database</groupId>
    <artifactId>h2</artifactId>
    <scope>runtime</scope>
</dependency>
```

Khi không khai báo `spring.datasource.url`, Spring Boot có thể chọn URL in-memory cho H2 và tạo embedded `DataSource`. Database in-memory phù hợp cho demo/test, nhưng dữ liệu không phải dữ liệu bền vững sau khi JVM kết thúc.

### 3.2. Nhánh pooled DataSource

Nhánh pooled được xem xét khi có implementation pool được hỗ trợ trên classpath hoặc người dùng chỉ định `spring.datasource.type`.

Spring Boot 3.3 ưu tiên các implementation phổ biến theo thứ tự:

1. HikariCP.
2. Tomcat JDBC Pool.
3. Apache Commons DBCP2.
4. Oracle UCP khi các lựa chọn trước không có.

Nếu dùng `spring-boot-starter-jdbc` hoặc `spring-boot-starter-data-jpa`, HikariCP thường đã có sẵn, vì vậy Hikari thường được chọn mặc định.

Có thể chỉ định rõ pool:

```yaml
spring:
  datasource:
    type: com.zaxxer.hikari.HikariDataSource
```

Hoặc dùng implementation khác nếu dependency tương ứng đã có. `spring.datasource.type` là tên lớp `DataSource` thực tế; nó không phải tên ngắn như `hikari`.

### 3.3. Vì sao embedded branch có thể no-match trong khi DataSource vẫn được tạo?

Đây là một trong những điểm quan trọng nhất khi đọc report.

Giả sử H2 và HikariCP đều có trên classpath, nhưng `spring.datasource.url` không được khai báo. Spring Boot có thể:

1. Nhận diện Hikari là pool được hỗ trợ.
2. Chọn nhánh pooled vì pool có sẵn.
3. Đánh giá embedded branch là no-match vì pool được ưu tiên.
4. Dùng `DataSourceProperties` để xác định URL embedded H2.
5. Tạo `HikariDataSource` kết nối tới H2 in-memory.

Vì vậy, report có thể ghi `EmbeddedDatabaseConfiguration` là negative match, còn `PooledDataSourceConfiguration` là positive match. Điều đó hoàn toàn bình thường; không có nghĩa Spring Boot không tạo database.

Không đọc một dòng negative match riêng lẻ rồi kết luận toàn bộ `DataSourceAutoConfiguration` thất bại. Phải kiểm tra cả hai nhánh và bean cuối cùng trong context.

## 4. Điều kiện back-off: khi ứng dụng tự khai báo DataSource

Cả embedded và pooled configuration đều có:

```java
@ConditionalOnMissingBean({
        DataSource.class,
        XADataSource.class
})
```

Nếu ứng dụng đã định nghĩa một bean `DataSource` hoặc `XADataSource` mà condition nhìn thấy, các nhánh tạo nguồn dữ liệu mặc định sẽ nhường chỗ.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
class MyDatabaseConfiguration {

    @Bean
    DataSource dataSource() {
        return DataSourceBuilder.create()
                .url("jdbc:postgresql://localhost:5432/orders")
                .username("app_user")
                .password("secret")
                .build();
    }
}
```

Đây là cấu hình minh họa; trong ứng dụng thật nên quản lý credential bằng secret/environment thay vì ghi mật khẩu trực tiếp.

Khi user bean được xử lý trước auto-configuration:

- `DataSourceAutoConfiguration` ở cấp lớp vẫn có thể match.
- `DataSourceProperties` vẫn có thể được đăng ký.
- `EmbeddedDatabaseConfiguration` không khớp vì đã có `DataSource`.
- `PooledDataSourceConfiguration` cũng không khớp vì đã có `DataSource`.
- Bean `dataSource` do ứng dụng cung cấp được dùng cho các thành phần JDBC tiếp theo.

Điều này khác với `@Primary`. `@Primary` chỉ giúp chọn ứng viên khi có nhiều bean; `@ConditionalOnMissingBean` mới là điều kiện để bean fallback không được đăng ký.

### 4.1. Tại sao điều kiện theo interface quan trọng?

Nếu starter kiểm tra sự hiện diện của `DataSource.class`, mọi implementation phù hợp đều có thể khiến fallback nhường chỗ. Không cần người dùng phải cung cấp đúng `HikariDataSource`.

Ngược lại, nếu code kiểm tra một implementation cụ thể như `HikariDataSource.class`, một `DriverManagerDataSource` hoặc một pool khác có thể không đáp ứng condition đó. Khi thiết kế auto-configuration riêng, chọn condition theo contract cần thay thế, thường là interface `DataSource`, thay vì khóa vào implementation nếu không có lý do rõ ràng.

Cũng cần bảo đảm method `@Bean` công khai kiểu trả về đủ cụ thể để Spring dự đoán loại bean khi condition được đánh giá. Một chữ ký trả về `Object` có thể che khuất thông tin kiểu cần thiết.

## 5. Lần theo quá trình từ dependency đến bean

Có thể đọc toàn bộ luồng theo thứ tự sau:

```text
@SpringBootApplication / @EnableAutoConfiguration
                   |
                   v
     DataSourceAutoConfiguration candidate?
                   |
          +--------+---------+
          |                  |
       Không match         Match cấp lớp
          |                  |
   Không tạo JDBC DS         v
                 Enable DataSourceProperties
                 Import metadata/checkpoint support
                              |
                              v
                 Có R2DBC ConnectionFactory?
                    (được kiểm tra ở cấp lớp)
                              |
                 nếu không có thì đi tiếp
                              |
               Đã có DataSource/XADataSource?
                    /                    \
                  Có                     Không
                  |                        |
             Back-off              Đánh giá 2 nhánh
                                           |
                          +----------------+----------------+
                          |                                 |
                 EmbeddedDatabaseCondition        PooledDataSourceCondition
                          |                                 |
             Embedded database phù hợp?          Pool/type phù hợp?
                          |                                 |
                 Embedded branch                 Pooled branch
                          |                                 |
                          +----------------+----------------+
                                           |
                              DataSource bean được đăng ký
                                           |
                              Bean được khởi tạo khi cần
                                           |
                              JDBC consumers sử dụng nó
```

Lưu ý sơ đồ là luồng tư duy, không phải toàn bộ thứ tự callback nội bộ của Spring. `@AutoConfiguration(before=...)` sắp xếp việc xử lý auto-configuration; thứ tự khởi tạo bean thực tế còn phụ thuộc dependency graph, `@DependsOn` và lifecycle.

## 6. Những property cần biết khi trace JDBC

| Property | Tác dụng | Câu hỏi khi chẩn đoán |
| --- | --- | --- |
| `spring.datasource.url` | JDBC URL | Có URL thật hay chỉ là placeholder không resolve? |
| `spring.datasource.username` | Tài khoản kết nối | Có bị nguồn cấu hình khác ghi đè không? |
| `spring.datasource.password` | Mật khẩu | Giá trị secret có được inject đúng không? |
| `spring.datasource.driver-class-name` | Driver JDBC cụ thể | Driver class có trên runtime classpath không? |
| `spring.datasource.type` | Chọn implementation DataSource | Class đã được thêm dependency chưa? |
| `spring.datasource.jndi-name` | Lấy DataSource từ JNDI | JNDI context/name có hợp lệ và có cấu hình tương ứng không? |
| `spring.datasource.hikari.*` | Thuộc tính riêng Hikari | Hikari có thật sự được chọn không? |
| `spring.datasource.embedded-database-connection` | Chọn embedded database connection phù hợp | Embedded database nào được chọn hoặc bị tắt? |

### 6.1. URL và driver

Ví dụ PostgreSQL:

```yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: app_user
    password: ${DB_PASSWORD}
```

Spring Boot thường suy luận driver từ JDBC URL nếu driver tương ứng có trên classpath. Có thể khai báo rõ:

```yaml
spring:
  datasource:
    driver-class-name: org.postgresql.Driver
```

Nếu URL sai cú pháp, driver không tồn tại, hoặc credentials sai, cần phân biệt lỗi nào xảy ra ở giai đoạn tạo bean và lỗi nào chỉ xuất hiện khi lấy connection. Một pool có thể được khởi tạo nhưng kết nối thực tới database vẫn thất bại sau đó, tùy cấu hình và thời điểm validate connection.

### 6.2. Hikari-specific properties

Khi Hikari được chọn, các thuộc tính pool-specific được bind dưới:

```yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 12
      minimum-idle: 2
      connection-timeout: 30000
```

Các thuộc tính chung ở `spring.datasource` và thuộc tính riêng ở `spring.datasource.hikari` có vai trò khác nhau. Không đặt `maximum-pool-size` ở cấp `spring.datasource` rồi mong Hikari nhận nó; cần đúng prefix.

### 6.3. URL `jdbc:` và thuộc tính `jdbc-url`

Hikari có property `jdbcUrl`, không có property `url` theo cùng cách mà `DataSourceProperties` công bố. Nếu tự viết `@Bean HikariDataSource` rồi bind thẳng bằng `@ConfigurationProperties`, cần chú ý sự khác biệt này.

Khi dùng `DataSourceProperties.initializeDataSourceBuilder()`, Spring Boot chuyển URL chung sang thuộc tính phù hợp của implementation. Đó là một lý do nên dùng `DataSourceProperties` trong cấu hình DataSource tùy chỉnh thay vì tự bind trực tiếp một `HikariDataSource` với `spring.datasource.url`.

## 7. Condition Evaluation Report cho DataSource

Để biết tại sao Spring Boot chọn hoặc bỏ qua nhánh JDBC, bật:

```bash
java -jar app.jar --debug
```

Hoặc cấu hình `debug=true`. Condition Evaluation Report sẽ hiển thị positive/negative matches và message của từng source.

Những source đáng tìm:

- `org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration`
- `DataSourceAutoConfiguration.EmbeddedDatabaseConfiguration`
- `DataSourceAutoConfiguration.PooledDataSourceConfiguration`
- Các nested configuration của `DataSourceConfiguration` như Hikari, Tomcat, DBCP2
- Các auto-configuration tiếp theo sử dụng `DataSource`, chẳng hạn transaction manager, `JdbcTemplate` và SQL initialization.

Một report minh họa theo ý nghĩa:

| Source | Kết quả | Message có thể cho biết |
| --- | --- | --- |
| `DataSourceAutoConfiguration` | Positive | Các class cần thiết có mặt, không có R2DBC ConnectionFactory |
| `EmbeddedDatabaseConfiguration` | Negative | Có URL hoặc pool được hỗ trợ nên nhánh embedded không được chọn |
| `PooledDataSourceConfiguration` | Positive | Pool được hỗ trợ có trên classpath hoặc type được chỉ định |
| `DataSourceConfiguration.Hikari` | Positive | Hikari có trên classpath và chưa có DataSource khác |
| `DataSourceConfiguration.Tomcat` | Negative | Hikari đã được chọn, hoặc Tomcat pool không có/không phải type được chọn |

Bảng là ví dụ minh họa; message chính xác phụ thuộc classpath, property và version. Trong một ứng dụng dùng custom DataSource, nested embedded và pooled branches có thể cùng no-match do back-off, trong khi root `DataSourceAutoConfiguration` vẫn positive.

### 7.1. Đọc report bằng API trong một context test

Spring Boot cung cấp `ConditionEvaluationReport`:

```java
ConditionEvaluationReport report =
        ConditionEvaluationReport.get(context.getBeanFactory());

report.getConditionAndOutcomesBySource().forEach((source, outcomes) -> {
    if (source.contains("DataSourceAutoConfiguration")) {
        System.out.println(source + " => "
                + (outcomes.isFullMatch() ? "MATCH" : "NO MATCH"));

        outcomes.forEach(item -> {
            var outcome = item.getOutcome();
            System.out.println("  "
                    + item.getCondition().getClass().getSimpleName()
                    + " | "
                    + (outcome.isMatch() ? "matched" : "did not match")
                    + " | "
                    + outcome.getMessage());
        });
    }
});
```

Đây là snippet đặt bên trong một test hoặc component có `ConfigurableApplicationContext`; không phải chương trình độc lập. Nội dung message do từng condition cung cấp, vì vậy không nên phụ thuộc vào chuỗi log chính xác trong logic sản phẩm.

Nếu có Spring Boot Actuator và đã expose endpoint phù hợp, `/actuator/conditions` cung cấp kết quả positive/negative matches dưới dạng JSON. Chỉ expose endpoint này trong môi trường chẩn đoán và bảo vệ quyền truy cập phù hợp.

## 8. Thực hành chạy được: Spring Boot 3.3.13 + Java 17 + H2

Bài thực hành dùng `ApplicationContextRunner` để kiểm tra ba trường hợp:

1. Không khai báo URL nhưng H2 có trên classpath: Boot tạo DataSource cho embedded database, thường bằng Hikari khi Hikari có sẵn.
2. Ứng dụng tự cung cấp DataSource: auto-configuration back off.
3. Có URL và Hikari-specific property: Boot dùng URL được chỉ định và bind cấu hình pool.

### 8.1. Cấu trúc dự án

```text
datasource-auto-config-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── DataSourceAutoConfigurationTest.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>datasource-auto-config-demo</artifactId>
    <version>1.0.0</version>

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
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

`spring-boot-starter-jdbc` cung cấp Spring JDBC và HikariCP; H2 chỉ cần ở test scope vì ví dụ không kết nối database bên ngoài.

### 8.3. `DataSourceAutoConfigurationTest.java`

```java
package demo;

import java.sql.Connection;
import java.sql.SQLException;

import javax.sql.DataSource;

import com.zaxxer.hikari.HikariDataSource;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

import static org.assertj.core.api.Assertions.assertThat;

class DataSourceAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(DataSourceAutoConfiguration.class));

    @Test
    void embeddedH2IsUsedWhenNoUrlIsProvided() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(DataSource.class);

            DataSource dataSource = context.getBean(DataSource.class);
            assertThat(dataSource).isInstanceOf(HikariDataSource.class);

            try (Connection connection = dataSource.getConnection()) {
                assertThat(connection.getMetaData().getURL())
                        .startsWith("jdbc:h2:mem:");
            }
            catch (SQLException ex) {
                throw new AssertionError("Could not open embedded H2 connection", ex);
            }

            ConditionEvaluationReport report =
                    ConditionEvaluationReport.get(context.getBeanFactory());
            var outcomes = report.getConditionAndOutcomesBySource()
                    .get(DataSourceAutoConfiguration.class.getName());

            assertThat(outcomes).isNotNull();
            assertThat(outcomes.isFullMatch()).isTrue();
        });
    }

    @Test
    void userDefinedDataSourceMakesDefaultConfigurationBackOff() {
        runner.withUserConfiguration(UserDataSourceConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(DataSource.class);
                    assertThat(context).hasBean("userDataSource");
                    assertThat(context).doesNotHaveBean("dataSource");

                    DataSource dataSource = context.getBean(DataSource.class);
                    assertThat(dataSource)
                            .isInstanceOf(DriverManagerDataSource.class);
                });
    }

    @Test
    void explicitUrlAndHikariSettingsAreApplied() {
        runner.withPropertyValues(
                        "spring.datasource.url=jdbc:h2:mem:configured;DB_CLOSE_DELAY=-1",
                        "spring.datasource.username=sa",
                        "spring.datasource.hikari.maximum-pool-size=4")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(DataSource.class);

                    HikariDataSource dataSource =
                            context.getBean(HikariDataSource.class);

                    assertThat(dataSource.getJdbcUrl())
                            .startsWith("jdbc:h2:mem:configured");
                    assertThat(dataSource.getMaximumPoolSize()).isEqualTo(4);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserDataSourceConfiguration {

        @Bean
        DataSource userDataSource() {
            return new DriverManagerDataSource(
                    "jdbc:h2:mem:userdb;DB_CLOSE_DELAY=-1",
                    "sa",
                    "");
        }
    }
}
```

Chạy trong thư mục chứa `pom.xml`:

```bash
mvn test
```

Kết quả mong đợi: ba test đều thành công; Maven Surefire thường hiển thị:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
```

Không có stdout tùy biến. Test đầu mở một connection thật tới H2 in-memory và kiểm tra JDBC URL; test thứ hai xác minh back-off bằng custom bean; test thứ ba xác minh URL và Hikari maximum pool size.

`ApplicationContextRunner` không khởi chạy một ứng dụng production hoàn chỉnh. Nó tạo context nhỏ có classpath, property và user configuration xác định, phù hợp để cô lập điều kiện auto-configuration.

## 9. Các tình huống report dễ gây hiểu nhầm

### 9.1. `DataSourceAutoConfiguration` không xuất hiện

Nếu không thấy source trong report, kiểm tra:

- `spring-boot-starter-jdbc` hoặc starter tương đương có trong runtime dependency graph không.
- `spring-jdbc` có thực sự có mặt không.
- `DataSourceAutoConfiguration` có bị exclude qua `@SpringBootApplication(exclude=...)` hoặc `spring.autoconfigure.exclude` không.
- Dependency version có bị lệch khiến artifact chứa class khác version mong muốn không.
- Ứng dụng có bật `@EnableAutoConfiguration` hoặc `@SpringBootApplication` không.

Không thấy source không đồng nghĩa với một negative match; auto-configuration có thể chưa phải candidate hoặc đã bị loại khỏi danh sách.

### 9.2. Embedded no-match, pooled positive

Thường là tình huống pool được ưu tiên. Kiểm tra `PooledDataSourceConfiguration` và loại bean cuối cùng. Nếu `DataSource` thực tế là `HikariDataSource`, việc embedded branch no-match là hợp lý.

### 9.3. Cả embedded và pooled đều no-match

Một số khả năng:

- Có `DataSource` hoặc `XADataSource` do ứng dụng cung cấp, khiến cả hai nhánh back off.
- Không có embedded database phù hợp và cũng không có pool được hỗ trợ.
- `spring.datasource.url` được khai báo nhưng không có pool/type thích hợp trên classpath.
- Có lỗi ở tầng classpath hoặc một điều kiện khác loại nhánh cấu hình.

Đọc message cụ thể của mỗi nested configuration trước khi sửa property.

### 9.4. Bean DataSource có mặt nhưng lấy connection thất bại

Điều này khác với condition no-match. Bean có thể đã được đăng ký và khởi tạo, nhưng kết nối không mở được do:

- Driver không có hoặc không tương thích.
- URL/port/hostname sai.
- Database chưa sẵn sàng.
- Username/password không đúng.
- TLS, network policy hoặc firewall.
- Pool cạn connection hoặc timeout.

Lúc này kiểm tra exception của `getConnection()`, pool logs và network/database; không tiếp tục sửa condition nếu report cho thấy DataSource đã match.

### 9.5. Có R2DBC nhưng cần JDBC

Nếu report cho biết JDBC configuration back off vì `ConnectionFactory`, xác định ứng dụng có thực sự cần hai stack không. Có thể chủ động import `DataSourceAutoConfiguration` để giữ JDBC, nhưng hãy xem xét blocking API và cấu hình transaction riêng. Không xóa bean R2DBC chỉ để làm JDBC condition match nếu ứng dụng vẫn cần reactive database access.

## 10. Tắt hoặc thay thế DataSource auto-configuration khi nào?

Nếu ứng dụng tự quản lý DataSource hoàn toàn, chỉ cần khai báo bean phù hợp thì nhánh mặc định có thể tự back off. Không phải lúc nào cũng cần exclude cả `DataSourceAutoConfiguration`.

Khi muốn tắt toàn bộ auto-configuration này, có thể dùng:

```java
@SpringBootApplication(
        exclude = DataSourceAutoConfiguration.class
)
public class Application {
}
```

Hoặc cấu hình:

```properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

Chỉ exclude khi đã hiểu các auto-configuration phụ thuộc vào `DataSource` sẽ bị ảnh hưởng. Ví dụ `JdbcTemplate`, JDBC transaction manager và SQL initialization có thể không còn được tạo theo cách mặc định. Exclude không tự cung cấp DataSource thay thế.

## 11. Quy trình chẩn đoán ngắn gọn

Khi `DataSource` không xuất hiện như mong đợi:

1. Kiểm tra candidate: `DataSourceAutoConfiguration` có được nạp không? Có bị exclude không?
2. Kiểm tra class condition: `DataSource` và `EmbeddedDatabaseType` có trên classpath không?
3. Kiểm tra R2DBC: có bean `ConnectionFactory` khiến JDBC auto-configuration back off không?
4. Kiểm tra user bean: đã có `DataSource`/`XADataSource` nào khiến nested branches nhường chỗ không?
5. Kiểm tra embedded/pool branch: URL có được đặt không, embedded DB có trên classpath không, pool nào được hỗ trợ, `spring.datasource.type` có hợp lệ không?
6. Kiểm tra driver và URL: driver có trên runtime classpath không, URL có đúng không, credential có hợp lệ không?
7. Kiểm tra pool-specific settings: prefix `spring.datasource.hikari` có đúng với pool được chọn không?
8. Nếu bean có nhưng connection lỗi: chuyển sang chẩn đoán database/network/credential/pool thay vì condition.

Luôn xác nhận kết quả cuối cùng bằng cách liệt kê bean `DataSource`, xem implementation cụ thể, mở connection trong môi trường test phù hợp và đọc condition report.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `DataSourceAutoConfiguration` có `@ConditionalOnClass(EmbeddedDatabaseType.class)`?  
**Đáp án:** Spring Boot cần Spring JDBC embedded database API trong classpath để nhánh cấu hình này có thể hoạt động. Thiếu class cần thiết, root configuration không match.

**Câu 2.** Có H2 và Hikari trên classpath, không khai báo URL. Vì sao report embedded branch có thể no-match?  
**Đáp án:** Boot ưu tiên pool được hỗ trợ; Hikari được tạo và có thể dùng URL embedded H2 được suy luận từ `DataSourceProperties`.

**Câu 3.** Ứng dụng đã có `@Bean DataSource`. Root `DataSourceAutoConfiguration` có nhất thiết no-match không?  
**Đáp án:** Không. Root class-level condition kiểm tra classpath và R2DBC `ConnectionFactory`; các nested DataSource-producing configurations mới kiểm tra missing `DataSource`/`XADataSource` và back off.

**Câu 4.** Khi đã có R2DBC `ConnectionFactory`, JDBC auto-configuration mặc định thế nào?  
**Đáp án:** Back off ở điều kiện cấp lớp. Nếu chủ đích cần cả hai, có thể import JDBC auto-configuration một cách tường minh và đánh giá tác động của blocking JDBC.

**Câu 5.** Bean Hikari xuất hiện nhưng `getConnection()` lỗi. Có thể kết luận `DataSourceAutoConfiguration` no-match không?  
**Đáp án:** Không. Bean đã được đăng ký; lỗi có thể nằm ở driver, URL, database, credential, mạng hoặc pool.

**Câu 6.** Muốn kiểm tra lý do Hikari được chọn thay embedded configuration, nên xem gì?  
**Đáp án:** Condition Evaluation Report của `EmbeddedDatabaseConfiguration`, `PooledDataSourceConfiguration` và nested `DataSourceConfiguration.Hikari`, sau đó xác minh bean thực tế.

## 13. Những điều cần ghi nhớ

- `DataSourceAutoConfiguration` có điều kiện cấp lớp và hai nhánh chính embedded/pooled.
- `@ConditionalOnClass` kiểm tra API cần thiết; `@ConditionalOnMissingBean(type=ConnectionFactory)` khiến JDBC mặc định nhường chỗ khi có R2DBC.
- `DataSourceProperties` cung cấp cấu hình đầu vào; nó không tự chứng minh bean DataSource đã được tạo.
- Embedded branch có thể no-match trong khi pooled branch match; một negative match đơn lẻ không nói lên toàn bộ kết quả.
- Pool selection phụ thuộc `spring.datasource.type` và các pool có trên classpath; Hikari thường được ưu tiên khi có sẵn.
- User `DataSource` hoặc `XADataSource` khiến nhánh mặc định back off.
- Bean tồn tại nhưng không kết nối được là vấn đề runtime/driver/network/credential, khác với condition không match.
- Dùng `--debug`, `/actuator/conditions` và `ApplicationContextRunner` để xác minh từng nhánh thay vì đoán từ một dòng log.

### Tài liệu tham khảo chính thức

- [Spring Boot 3.3 API — `DataSourceAutoConfiguration`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceAutoConfiguration.html)
- [Spring Boot 3.3 — SQL Databases và DataSource Configuration](https://docs.spring.io/spring-boot/3.3/reference/data/sql.html)
- [Spring Boot 3.3 — Data Access How-to](https://docs.spring.io/spring-boot/3.3/how-to/data-access.html)
- [Spring Boot 3.3 API — `DataSourceBuilder`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/jdbc/DataSourceBuilder.html)
- [Spring Boot 3.3 API — `DataSourceProperties`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/DataSourceProperties.html)
- [Spring Boot 3.3 API — `ConditionEvaluationReport`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html)
