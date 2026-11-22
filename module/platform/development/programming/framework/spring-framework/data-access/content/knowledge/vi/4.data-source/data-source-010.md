# Phân biệt cấu hình Spring Framework với tự động cấu hình Spring Boot cho DataSource

## 1. Cùng dùng Spring JDBC, nhưng ai tạo DataSource?

Trong ứng dụng Java truy cập cơ sở dữ liệu, `DataSource` (thuộc `javax.sql.DataSource` của JDBC) là hợp đồng cung cấp `Connection`. `JdbcTemplate` sử dụng `DataSource` để chạy SQL; transaction manager sử dụng nguồn kết nối tương ứng để phối hợp commit/rollback. Mọi ứng dụng đều phải có một nguồn kết nối được cấu hình đúng, dù cấu hình đó do lập trình viên khai báo trực tiếp hay do Spring Boot tự cấu hình dựa trên classpath và thuộc tính.

**Spring Framework thuần** cung cấp IoC container, dependency injection, các API JDBC/transaction và cách khai báo bean. Nó không mặc nhiên tạo `DataSource` chỉ vì dự án có thư viện `spring-jdbc` hoặc có tệp `application.properties`. Bạn thường phải đăng ký các bean cần thiết, khai báo thuộc tính và chọn implementation bằng code/XML hay cấu hình cụ thể.

**Spring Boot** xây trên Spring Framework, bổ sung cơ chế **auto-configuration**: nếu các điều kiện phù hợp, Boot tạo sẵn những bean thông dụng như `DataSource`, `JdbcTemplate`, `NamedParameterJdbcTemplate` và transaction manager. Các giá trị có thể được suy ra từ các thuộc tính như `spring.datasource.url`, `spring.datasource.username` hoặc driver cơ sở dữ liệu trên classpath. Nếu ứng dụng đã tự cung cấp bean nhất định, cấu hình tự động liên quan thường nhường quyền cho bean đó theo điều kiện của từng auto-configuration.

Nói ngắn gọn:

- **Spring Framework:** “Tôi cung cấp container và API; bạn khai báo thành phần nào cần tồn tại.”
- **Spring Boot:** “Tôi dùng container Spring và thử khai báo cấu hình hợp lý từ dependency, properties và bean hiện có; bạn vẫn được tùy chỉnh.”

Auto-configuration **không phải** một JDBC API mới, **không loại bỏ** `DataSource`, và **không thay** việc hiểu kết nối, pooling, transaction hoặc các ràng buộc của DB.

## 2. Chuỗi phụ thuộc ở runtime

```text
                        Ứng dụng
                           |
                           v
                     Repository/DAO
                           |
                           v
                      JdbcTemplate
                           |
                           v
                    javax.sql.DataSource
                           |
                  lấy / trả Connection
                           |
                           v
                  JDBC driver / database

    Spring-managed transaction (nếu cấu hình)
                    |
                    v
            PlatformTransactionManager
                    |
                    v
                 DataSource
```

Sự khác biệt giữa Framework và Boot nằm chủ yếu ở **quá trình dựng các bean** và **nguồn giá trị cấu hình**, không nằm ở thao tác SQL do `JdbcTemplate` thực hiện. Cùng một `JdbcTemplate` vẫn sử dụng `DataSourceUtils` để tham gia connection được Spring quản lý khi có transaction thích hợp.

### 2.1. Vai trò của từng thành phần

| Thành phần | Spring Framework cung cấp gì? | Spring Boot bổ sung gì? |
| --- | --- | --- |
| `DataSource` | Sử dụng interface JDBC; cho phép đăng ký implementation làm bean | Có thể tự tạo bean từ dependency, thông tin kết nối và điều kiện auto-config |
| `DriverManagerDataSource` | Implementation đơn giản của `spring-jdbc`, tạo connection mới khi được yêu cầu | Không phải pool mặc định của Boot |
| HikariCP | Có thể được khai báo/chọn thủ công khi có thư viện | Thường được Boot chọn làm JDBC pool khi HikariCP có trên classpath và không bị thay bằng lựa chọn khác |
| `JdbcTemplate` | Cung cấp class và API SQL, mapper, callback | Có thể tự tạo bean `JdbcTemplate` nếu đủ điều kiện |
| `NamedParameterJdbcTemplate` | Cung cấp API tham số `:name` | Có thể tự tạo bean tương ứng nếu đủ điều kiện |
| `PlatformTransactionManager` | Cung cấp abstraction và các implementation như `JdbcTransactionManager` | Có thể tự tạo transaction manager JDBC nếu có `DataSource` thích hợp và không bị cấu hình khác thay thế |
| `@Transactional` | Định nghĩa metadata và Spring transaction infrastructure, cần được bật/cấu hình | Auto-config giúp thiết lập nhiều thành phần transaction khi điều kiện thỏa, nhưng proxy/transaction vẫn có quy tắc riêng |
| JDBC driver | Driver nằm trong dependency runtime | Driver vẫn phải nằm trên classpath; Boot có thể suy ra tên driver từ JDBC URL thông dụng |
| URL, user, password | Bạn quyết định cách cung cấp/bind | Boot có binder và các thuộc tính `spring.datasource.*` thông dụng |

`DataSource` không nhất thiết là pool. Ví dụ `DriverManagerDataSource` tiện cho bài học/test, nhưng **không có connection pooling**. Trong ứng dụng production, nên cân nhắc pool đã quản lý giới hạn kết nối, timeout, kiểm tra sức khỏe và vòng đời.

## 3. Spring Framework thuần: tự khai báo các bean

### 3.1. Các quyết định phải làm rõ

Với ứng dụng dùng Spring Framework trực tiếp, thường cần:

1. Thêm các dependency `spring-context`, `spring-jdbc` và driver cơ sở dữ liệu.
2. Chọn implementation của `DataSource`; nhập URL, user, password và thông số pool nếu có.
3. Khai báo bean `DataSource` bằng `@Configuration`/`@Bean` (hoặc XML).
4. Khai báo `JdbcTemplate`, truyền vào `DataSource`.
5. Nếu cần transaction khai báo `PlatformTransactionManager` phù hợp, bật transaction infrastructure (ví dụ `@EnableTransactionManagement`), đặt ranh giới `@Transactional` ở nơi thích hợp.
6. Chọn và quản lý cách đọc properties từ file, environment hoặc secret store; Spring Framework không tự hiểu `spring.datasource.url` như quy ước Spring Boot.

Có thể viết `new JdbcTemplate(dataSource)` trực tiếp, nhưng để service/repository dùng dependency injection, quản lý bean thường rõ ràng và dễ kiểm thử hơn.

### 3.2. Chương trình đầy đủ: Spring Framework + H2

Ví dụ dùng **Java 17+**, **Spring Framework 6.2.12** và H2. Chương trình hoạt động mà không cần Spring Boot, không cần cài database server. Lưu ý các version ở đây được **ghim để minh họa**, không có ý nghĩa là phiên bản mới nhất.

Cấu trúc:

```text
framework-datasource-demo/
├── pom.xml
└── src/main/java/example/FrameworkDataSourceDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>framework-datasource-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/example/FrameworkDataSourceDemo.java`:

```java
package example;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

public class FrameworkDataSourceDemo {
    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    static class JdbcConfig {
        @Bean
        DataSource dataSource() {
            DriverManagerDataSource source = new DriverManagerDataSource();
            source.setDriverClassName("org.h2.Driver");
            source.setUrl("jdbc:h2:mem:frameworkdemo;DB_CLOSE_DELAY=-1");
            source.setUsername("sa");
            source.setPassword("");
            return source;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource dataSource) {
            return new JdbcTransactionManager(dataSource);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(JdbcConfig.class)) {
            DataSource dataSource = context.getBean(DataSource.class);
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            PlatformTransactionManager transactionManager =
                    context.getBean(PlatformTransactionManager.class);

            jdbc.execute("CREATE TABLE people (id BIGINT PRIMARY KEY, name VARCHAR(80))");
            jdbc.update("INSERT INTO people (id, name) VALUES (?, ?)", 1L, "Lan");
            String name = jdbc.queryForObject(
                    "SELECT name FROM people WHERE id = ?",
                    String.class, 1L);

            System.out.println("Framework DataSource: "
                    + dataSource.getClass().getSimpleName());
            System.out.println("Framework JdbcTemplate: "
                    + jdbc.getClass().getSimpleName());
            System.out.println("Framework transaction manager: "
                    + transactionManager.getClass().getSimpleName());
            System.out.println("Framework query: " + name);
        }
    }
}
```

Chạy trong thư mục có `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.FrameworkDataSourceDemo
```

Dữ liệu do chương trình in ra (không tính log Maven):

```text
Framework DataSource: DriverManagerDataSource
Framework JdbcTemplate: JdbcTemplate
Framework transaction manager: JdbcTransactionManager
Framework query: Lan
```

**Tại sao ví dụ chạy được?**

- `AnnotationConfigApplicationContext` tải `JdbcConfig` và nhận ra ba phương thức `@Bean`.
- `DataSource` là bean được lập trình viên **tạo tường minh**; Spring không tự chọn H2, URL hay username.
- Container inject đúng cùng `DataSource` vào `JdbcTemplate` và `JdbcTransactionManager`.
- `JdbcTemplate` chạy lệnh tạo bảng, insert và select bằng JDBC; `DB_CLOSE_DELAY=-1` giữ database in-memory sống qua các connection khác nhau trong cùng tiến trình.
- `DriverManagerDataSource` không tái sử dụng connection theo pool; chỉ nên dùng cho minh họa hoặc trường hợp đơn giản, không đem nguyên cấu hình này vào production.

`@EnableTransactionManagement` cho phép Spring áp dụng `@Transactional` vào những bean phù hợp khi có lời gọi qua transaction proxy. Ví dụ không khai báo service transactional vì mỗi thao tác SQL đều đơn giản; khai báo transaction manager ở đây nhằm nhìn thấy trách nhiệm cấu hình của Framework.

Nếu bỏ phương thức `@Bean JdbcTemplate`, việc `context.getBean(JdbcTemplate.class)` sẽ lỗi vì **Spring Framework thuần không tự tạo JdbcTemplate**. Nếu bỏ `DataSource`, container cũng không có nguồn connection để inject vào bean phụ thuộc.

## 4. Spring Boot: tự cấu hình khi đủ điều kiện

Spring Boot dùng `@SpringBootApplication`, trong đó bao gồm cơ chế bật auto-configuration cùng cấu hình ứng dụng và component scan. Khi thư viện JDBC, pool/embedded DB và các bean thích hợp có mặt, các lớp auto-configuration được kích hoạt có điều kiện.

Với cách dùng JDBC phổ biến, chuỗi khái niệm là:

```text
Dependencies + application.properties/yaml + beans hiện có
                         |
                         v
                  Spring Boot auto-config
                         |
           kiểm tra classpath / conditions
                         |
         +---------------+---------------+
         |                               |
 Có DataSource do ứng dụng tạo?        Chưa có DataSource?
         |                               |
 Dùng bean đã khai báo;             Boot thử tạo bean nếu
 một số auto-config sẽ back off     các điều kiện phù hợp
         |                               |
         +---------------+---------------+
                         |
                         v
                 DataSource candidate
                         |
         +---------------+---------------+
         |                               |
  JdbcTemplate bean?            Transaction manager bean?
  (nếu đủ điều kiện)              (nếu đủ điều kiện)
```

Boot dùng các cấu hình như `DataSourceAutoConfiguration`, `JdbcTemplateAutoConfiguration` và cấu hình liên quan đến transaction. Tên lớp, package và chi tiết điều kiện có thể thay đổi giữa các dòng phiên bản Boot; **mấu chốt là điều kiện theo classpath, properties và bean hiện có**.

Cần hiểu các trường hợp:

- Có `spring-boot-starter-jdbc`, HikariCP (được starter kéo theo) và một JDBC driver phù hợp: Boot thường có thể tạo pooled `DataSource`.
- Có H2/HSQLDB/Derby embedded trên classpath: Boot có thể cấu hình một embedded database nếu không cung cấp URL, tùy ngữ cảnh và phiên bản.
- Chỉ có `spring.datasource.url` trong file nhưng thiếu dependency DataSource/driver cần thiết: không thể đảm bảo kết nối; property không biến thành JDBC driver.
- Có một `@Bean DataSource` do ứng dụng định nghĩa: auto-configuration tạo `DataSource` mặc định thường **back off**; các auto-config khác vẫn có thể tạo template/transaction manager dựa trên bean này.
- Có hai `DataSource` mà không xác định candidate: autowiring theo loại có thể mơ hồ; auto-configuration cho `JdbcTemplate` cần candidate thích hợp.
- Dự án chỉ dùng R2DBC/reactive có một cấu hình kết nối reactive khác: không suy luận rằng JDBC `DataSource` sẽ được tạo. R2DBC không phải JDBC.

### 4.1. Các thuộc tính Spring Boot thường gặp

```properties
# Ví dụ PostgreSQL, cần có dependency JDBC driver PostgreSQL:
spring.datasource.url=jdbc:postgresql://localhost:5432/sales
spring.datasource.username=app_user
spring.datasource.password=change-me

# Boot thường chọn HikariCP khi có Hikari trên classpath:
spring.datasource.hikari.maximum-pool-size=10
spring.datasource.hikari.connection-timeout=30000
```

Đây là **ví dụ cấu hình**, không phải bí mật thật. Thực tế nên đưa password qua environment variable/secret manager thay vì commit vào repository.

| Nhóm cấu hình | Ý nghĩa |
| --- | --- |
| `spring.datasource.url` | JDBC URL kết nối; bỏ qua sẽ cần nguồn suy luận khác như embedded DB |
| `spring.datasource.username` / `password` | Tài khoản kết nối; nên cấp qua cấu hình môi trường an toàn |
| `spring.datasource.driver-class-name` | Driver class; thường có thể suy ra từ URL phổ biến nếu jar driver có sẵn |
| `spring.datasource.type` | Có thể chỉ định implementation DataSource thay vì lựa chọn mặc định |
| `spring.datasource.hikari.*` | Tùy chỉnh pool Hikari khi DataSource thực tế dùng Hikari |
| `spring.sql.init.*` | Cấu hình cơ chế chạy schema/data SQL lúc khởi tạo, là vấn đề riêng với cấu hình kết nối |
| `spring.jpa.*` | Cấu hình JPA/Hibernate nếu ứng dụng dùng JPA; không bắt buộc cho JdbcTemplate |

Mỗi nhóm property được xử lý bởi cơ chế cụ thể. Đặc biệt, **`spring.datasource.hikari.maximum-pool-size` không biến `DriverManagerDataSource` thành connection pool** nếu bạn đã tự đăng ký `DriverManagerDataSource` và Boot không tạo Hikari.

### 4.2. Chương trình đầy đủ: Spring Boot + H2

Ví dụ thứ hai dùng **Java 17+**, **Spring Boot 3.5.7** và starter JDBC. Phiên bản được cố định để người học tái hiện ví dụ, không nhằm khẳng định đây là bản Boot mới nhất.

Cấu trúc:

```text
boot-datasource-demo/
├── pom.xml
└── src/main/
    ├── java/example/BootDataSourceDemo.java
    └── resources/application.properties
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>boot-datasource-demo</artifactId>
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
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/resources/application.properties`:

```properties
spring.main.banner-mode=off
logging.level.root=ERROR

spring.datasource.url=jdbc:h2:mem:bootdemo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=5
```

`src/main/java/example/BootDataSourceDemo.java`:

```java
package example;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class BootDataSourceDemo {
    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                     SpringApplication.run(BootDataSourceDemo.class, args)) {
            // CommandLineRunner chạy khi context đã sẵn sàng.
        }
    }

    @Bean
    CommandLineRunner inspectDataSource(
            DataSource dataSource, JdbcTemplate jdbc) {
        return args -> {
            jdbc.execute("CREATE TABLE people (id BIGINT PRIMARY KEY, name VARCHAR(80))");
            jdbc.update(
                    "INSERT INTO people (id, name) VALUES (?, ?)", 1L, "Lan");
            String name = jdbc.queryForObject(
                    "SELECT name FROM people WHERE id = ?", String.class, 1L);

            System.out.println("Boot DataSource: "
                    + dataSource.getClass().getSimpleName());
            System.out.println("Boot JdbcTemplate: "
                    + jdbc.getClass().getSimpleName());
            System.out.println("Boot query: " + name);
        };
    }
}
```

Chạy trong thư mục `boot-datasource-demo`:

```bash
mvn -q spring-boot:run
```

Với classpath/starter và cấu hình trên, các dòng chương trình in ra:

```text
Boot DataSource: HikariDataSource
Boot JdbcTemplate: JdbcTemplate
Boot query: Lan
```

**Điều gì khác ví dụ Framework thuần?**

- Code không tự khai báo `@Bean DataSource`, `@Bean JdbcTemplate` hay transaction manager. Đây là phần Boot có thể tự cấu hình do starter, H2, properties và không có bean cạnh tranh.
- `spring-boot-starter-jdbc` cung cấp Spring JDBC cùng các thành phần liên quan, trong đó thường có HikariCP; H2 driver được khai báo riêng.
- URL/user/password từ `application.properties` được Boot đưa vào cơ chế tạo `DataSource`; pool Hikari nhận `maximum-pool-size=5`.
- `CommandLineRunner` được tạo như một bean ứng dụng; Boot inject các bean auto-config vào tham số phương thức.
- Phần repository/SQL có thể hoàn toàn giống Framework thuần: `JdbcTemplate` tiếp tục chạy SQL và mapping JDBC thông thường.

Log startup, phiên bản driver và cách trình bày thông báo của Maven có thể thay đổi theo môi trường. Kết quả trên là **các dòng `System.out.println`**, không phải bản chụp toàn bộ console.

### 4.3. Vì sao không nên coi Boot là phép màu?

Trong ví dụ Boot, những điều kiện đã được chuẩn bị sẵn:

1. Có starter để bật các auto-configuration phù hợp.
2. Có H2 driver trong runtime classpath.
3. Có JDBC URL hợp lệ.
4. Không đăng ký bean `DataSource` riêng khiến cấu hình mặc định phải nhường chỗ.
5. Có một `DataSource` đủ rõ để auto-config tạo `JdbcTemplate`.

Nếu thiếu một điều kiện, startup có thể lỗi, bean không tồn tại hoặc triển khai có hành vi khác. Ví dụ chỉ thêm `spring.datasource.url=jdbc:postgresql:...` mà không khai báo PostgreSQL JDBC driver thì Boot không thể tạo kết nối PostgreSQL thành công.

## 5. So sánh trực tiếp theo trách nhiệm

| Câu hỏi | Spring Framework thuần | Spring Boot |
| --- | --- | --- |
| Ai quyết định tạo `DataSource`? | Lập trình viên/cấu hình do dự án cung cấp | Auto-config nếu thỏa điều kiện, hoặc bean người dùng |
| Ai cung cấp URL và credentials? | Từ Java config/XML/property binding do dự án tự thiết kế | Từ `spring.datasource.*` và cơ chế Externalized Configuration nếu auto-config được áp dụng |
| Có tạo `JdbcTemplate` sẵn không? | Không tự động chỉ vì có jar | Có thể được tạo có điều kiện khi có DataSource phù hợp |
| Có pool mặc định không? | Không có chính sách pool mặc định; bạn chọn | HikariCP thường là lựa chọn ưu tiên nếu classpath phù hợp |
| Ai quản lý transaction? | Bạn đăng ký manager và bật infrastructure khi cần | Boot có thể auto-config manager phù hợp; bạn vẫn quyết định ranh giới `@Transactional` |
| Có cần SQL và mapping không? | Có | Có |
| Có thể dùng cùng thư viện Spring JDBC? | Có | Có; Boot dùng các thư viện Framework bên dưới |
| Bean tự định nghĩa có ưu tiên không? | Chính bạn định nghĩa bean | Auto-config liên quan thường back off khi có bean người dùng thích hợp |
| Dễ hiểu trực tiếp bean nào tồn tại? | Phần lớn được khai báo minh bạch trong config | Cần hiểu condition report và danh sách bean runtime |
| Dùng production được không? | Có, nếu tự cấu hình đủ pooling, timeout, transaction, secrets và observability | Có, nếu kiểm soát autoconfig/properties, pool, timeout, transaction, secrets và observability |

Không nên hiểu “Framework thuần = cũ” và “Boot = mới”. Boot sử dụng chính Spring Framework, và ứng dụng Boot vẫn có thể chứa hàng loạt lớp `@Configuration` tự viết. **Sự lựa chọn là mức độ cấu hình mặc định và cơ chế wiring**, không phải hai công nghệ truy cập DB khác nhau.

## 6. Trường hợp tự khai báo DataSource trong ứng dụng Spring Boot

### 6.1. Boot back off, nhưng chỉ ở những phần liên quan

Giả sử ứng dụng Boot có bean:

```java
// Đoạn minh họa trong một ứng dụng Spring Boot đã có dependency spring-jdbc.
@Configuration(proxyBeanMethods = false)
class CustomJdbcConfiguration {
    @Bean
    DataSource dataSource() {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:custom;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");
        return ds;
    }
}
```

Đoạn này cần import `@Configuration`, `@Bean`, `DataSource`, `DriverManagerDataSource` và driver H2 như các ví dụ đã nêu. Đây là **đoạn minh họa**, không phải file chạy độc lập.

Khi bean `DataSource` này đã hiện diện, phần Boot định tạo một `DataSource` mặc định thường không thực hiện nữa. Nhưng auto-config cho `JdbcTemplate` vẫn có thể dùng bean đó; không có nghĩa “tự khai báo một bean thì Boot tắt tất cả auto-config”.

Đặc biệt:

- `spring.datasource.url` trong `application.properties` không nhất thiết được áp dụng cho `DriverManagerDataSource` do bạn tự `new` theo code trên. Bean tự tạo dùng các giá trị bạn set trong phương thức.
- `spring.datasource.hikari.maximum-pool-size` không tác dụng với bean `DriverManagerDataSource`; nó không phải Hikari.
- Nếu bean tự tạo là pooled `HikariDataSource`, việc properties nào được bind phụ thuộc vào cách khai báo `@ConfigurationProperties` hoặc sử dụng `DataSourceProperties`/builder, không có quy tắc “mọi bean tự viết đều tự nhận tất cả `spring.datasource.*`”.
- Có thể ghi đè bean `JdbcTemplate` theo yêu cầu riêng; khi đó Spring Boot chỉ tạo bản mặc định nếu điều kiện về bean vắng mặt thỏa mãn. Không nên định nghĩa hai bean cùng tên mà không kiểm soát cơ chế conflict.

### 6.2. Dùng Spring Boot mà vẫn muốn khai báo tường minh

Một thiết kế hợp lệ là để Boot quản lý startup, configuration/environment và DI, nhưng tự tạo các `DataSource` cần thiết. Khi số nguồn dữ liệu nhiều, người viết nên đăng ký rõ từng `DataSource`, `JdbcTemplate` và transaction manager, dùng `@Qualifier` và đôi khi `@Primary` để xác định candidate.

Ví dụ khái niệm (không phải Java file hoàn chỉnh):

```java
@Bean
JdbcTemplate billingJdbc(
        @Qualifier("billingDataSource") DataSource dataSource) {
    return new JdbcTemplate(dataSource);
}

@Bean
JdbcTemplate reportingJdbc(
        @Qualifier("reportingDataSource") DataSource dataSource) {
    return new JdbcTemplate(dataSource);
}
```

Nếu có hai bean `JdbcTemplate`, injection `JdbcTemplate` đơn thuần cũng trở nên mơ hồ; đặt tên, `@Qualifier` hoặc `@Primary` cho đúng consumer. Khi nghiệp vụ cần transaction, transaction manager phải gắn với nguồn dữ liệu đúng, không chỉ chọn bean có tên bất kỳ.

Với nhiều DataSource, Boot không thể tự suy đoán nghiệp vụ nào dùng DB nào, SQL nào phải commit cùng nhau, hay có yêu cầu transaction phân tán hay không.

## 7. Properties: khác biệt thường bị hiểu sai

### 7.1. Spring Framework không tự bind `spring.datasource.*`

Trong Framework thuần, thêm file:

```properties
spring.datasource.url=jdbc:h2:mem:demo
spring.datasource.username=sa
spring.datasource.password=
```

**không đủ** để tạo bean `DataSource`. Bạn cần nạp giá trị và tạo bean, ví dụ `@PropertySource`/`Environment`, `@Value` hoặc binder bạn chủ động dùng. Tên khóa có prefix `spring.datasource` chỉ mang ý nghĩa đặc biệt trong các auto-configuration/binder tương ứng của Boot.

Một ví dụ minh họa trong Framework thuần:

```java
@Configuration
@PropertySource("classpath:jdbc.properties")
class DataSourceConfiguration {
    @Bean
    DataSource dataSource(Environment env) {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl(env.getRequiredProperty("db.url"));
        ds.setUsername(env.getRequiredProperty("db.user"));
        ds.setPassword(env.getRequiredProperty("db.password"));
        return ds;
    }
}
```

Đoạn cần các import Spring và bean context tương ứng; file `src/main/resources/jdbc.properties` phải có `db.url`, `db.user`, `db.password`. Đây là đoạn minh họa về **cơ chế lấy properties**, không phải cấu hình phải dùng trong mọi dự án Framework. Khi dùng môi trường production, tránh lưu password thật trong source.

### 7.2. Boot Externalized Configuration không thay thế việc chọn database

Boot hỗ trợ `application.properties`, `application.yml`, môi trường runtime, command-line arguments, profile và các nguồn properties khác. Điều này tiện cho deployment nhưng không tự tạo driver hay database.

Ví dụ cấu hình tách profile:

```properties
# application-dev.properties
spring.datasource.url=jdbc:h2:mem:devdb
spring.datasource.username=sa
spring.datasource.password=
```

```properties
# application-prod.properties
spring.datasource.url=jdbc:postgresql://db.internal:5432/appdb
spring.datasource.username=app_user
spring.datasource.password=use-runtime-secret
```

Trong thực tế, password production nên là secret inject lúc chạy, không được commit giá trị thực. Chọn profile qua môi trường/CLI, ví dụ `--spring.profiles.active=dev`. Không trộn lẫn profile `dev` và `prod` khiến hai URL cạnh tranh thiếu chủ đích.

**Lưu ý:** chế độ test dùng H2 có thể bỏ qua khác biệt dialect, constraint, isolation và indexing của DB production. Auto-configuration không đảm bảo các database thay thế có behavior giống nhau.

## 8. Schema initialization và JPA: những “tự động” khác dễ lẫn

Có `DataSource` chỉ nghĩa là có thể lấy connection. Nó **không đồng nghĩa** bảng đã tồn tại.

Trong Spring Framework thuần, bạn tự quyết định chạy DDL từ Flyway/Liquibase, SQL script bằng `ResourceDatabasePopulator`, hoặc một công cụ migration khác. Trong Boot, cơ chế SQL initialization có thể đọc `schema.sql` và `data.sql` theo cấu hình. Với nhiều phiên bản Boot, mặc định SQL init thường hướng đến embedded databases; với database ngoài có thể cần `spring.sql.init.mode=always` nếu thực sự muốn chạy script, nhưng production thường nên ưu tiên migration được kiểm soát.

Đừng đánh đồng ba việc:

1. **DataSource auto-configuration:** tạo bean connection factory JDBC.
2. **SQL initialization:** tùy chọn chạy các script schema/dữ liệu.
3. **JPA/Hibernate DDL:** hành vi riêng khi dùng JPA và các property `spring.jpa.hibernate.ddl-auto`, không phải bản thân `JdbcTemplate`.

Ví dụ Boot JDBC dùng `JdbcTemplate` nhưng không có JPA sẽ **không cần entity, Hibernate hay repository JPA**. Thêm starter JPA có thể thêm các auto-config và transaction policy khác; cần xem bean thực tế thay vì mặc định nghĩ mọi ứng dụng Boot JDBC đều chạy Hibernate.

Trong ví dụ chương trình ở trên, câu lệnh `CREATE TABLE` được gọi tường minh để tránh phụ thuộc vào cơ chế schema init.

## 9. Transaction: không phải chỉ cần annotation

`@Transactional` là annotation của Spring Framework, không phải riêng Spring Boot. Với Framework thuần, bạn thường cấu hình `PlatformTransactionManager` và bật transaction management; Boot có thể tạo bean tương ứng khi đủ điều kiện. **Cả hai cách đều cần một transaction manager phù hợp với DataSource mà repository đang sử dụng.**

Ví dụ service minh họa:

```java
@Service
public class PaymentService {
    private final JdbcTemplate jdbc;

    public PaymentService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(long fromId, long toId, long amount) {
        int deducted = jdbc.update(
                "UPDATE account SET balance = balance - ? " +
                "WHERE id = ? AND balance >= ?",
                amount, fromId, amount);
        if (deducted != 1) {
            throw new IllegalStateException("Insufficient funds");
        }

        int added = jdbc.update(
                "UPDATE account SET balance = balance + ? WHERE id = ?",
                amount, toId);
        if (added != 1) {
            throw new IllegalStateException("Destination not found");
        }
    }
}
```

Đây là **đoạn minh họa**, chưa phải chương trình chạy độc lập: cần các import của `JdbcTemplate`, `@Service`, `@Transactional`, bảng `account`, cấu hình bean và transaction manager. Production cần kiểm tra amount dương, không chuyển cùng account, numeric type, đồng thời và isolation phù hợp.

Tại sao transaction liên quan đến DataSource?

- `JdbcTransactionManager`/`DataSourceTransactionManager` gắn transaction với connection lấy từ một `DataSource`.
- `JdbcTemplate` lấy connection theo cách hợp tác với Spring để các lệnh trong một transaction có thể dùng connection đang được ràng buộc với transaction.
- Nếu adapter chủ động mở connection ngoài cơ chế Spring transaction, câu lệnh có thể không tham gia transaction dù được gọi từ service annotated.
- Dùng nhiều DataSource khác nhau không tạo transaction phân tán tự động. Một local JDBC transaction manager quản lý tài nguyên của nó, không điều phối commit nguyên tử qua hai database độc lập.
- Với Spring proxy mặc định, tự gọi `this.transfer(...)` từ cùng class bỏ qua advice; cần lời gọi qua proxy thích hợp.
- Mặc định rollback cho `RuntimeException` và `Error`, không tự rollback checked exceptions trừ khi cấu hình. Bắt lỗi rồi “nuốt” có thể khiến Spring xem phương thức là thành công.

Vì vậy, không nên xem `@Transactional` là bằng chứng đủ để khẳng định “mọi câu SQL của ứng dụng cùng một transaction”. Trong Framework và Boot đều phải kiểm chứng bằng integration test đường rollback.

## 10. Cách phát hiện Boot đã tạo bean gì

Auto-configuration chạy theo điều kiện nên cần **xác minh hành vi thật** thay vì đoán.

### 10.1. Điều tra bằng runtime

Có thể tạm in type của bean:

```java
@Bean
CommandLineRunner inspect(
        DataSource source, JdbcTemplate jdbc) {
    return args -> {
        System.out.println(source.getClass().getName());
        System.out.println(jdbc.getClass().getName());
    };
}
```

Đoạn minh họa cần import `@Bean`, `CommandLineRunner`, `DataSource`, `JdbcTemplate` và ứng dụng Boot. Nếu injection thất bại vì bean thiếu hoặc mơ hồ, lỗi startup chính là thông tin cần điều tra.

Boot hỗ trợ bật condition evaluation report bằng `--debug` hoặc `debug=true` cho các ứng dụng phù hợp, cho thấy tại sao một auto-configuration được áp dụng hoặc không. Nếu đã cài Spring Boot Actuator và mở endpoint phù hợp, `/actuator/conditions` cũng giúp xem điều kiện; endpoint cần được cấu hình expose và bảo vệ cẩn thận, không tự public trong production.

Kiểm tra những câu hỏi sau:

1. Có những dependency nào ở runtime (Spring JDBC, pool, driver, JPA/R2DBC)?
2. Bean `DataSource` nào thực sự tồn tại, type là gì? Có nhiều bean không?
3. Properties nào được nạp từ profile/env/CLI? URL cuối cùng thực tế là gì?
4. Boot đã skip `DataSourceAutoConfiguration` hoặc `JdbcTemplateAutoConfiguration` do điều kiện nào?
5. Transaction manager nào đang tồn tại và nó quản lý DataSource nào?
6. Trong pool có giới hạn connection, timeout và leak detection phù hợp không?

Không in password, token hoặc JDBC URL có credentials nhúng vào log. Việc bật debug ở production cần cân nhắc thông tin cấu hình bị lộ.

### 10.2. Những tình huống lỗi điển hình

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra/sửa |
| --- | --- | --- |
| Framework thuần báo không tìm thấy bean `DataSource` | Chưa đăng ký `@Bean` / scan sai cấu hình | Kiểm tra `@Configuration` được nạp; tạo bean phù hợp |
| Framework thuần thiếu `JdbcTemplate` | Có DataSource nhưng chưa tạo template bean | Khai báo `new JdbcTemplate(dataSource)` dưới `@Bean` |
| Boot báo không xác định được DataSource | Thiếu JDBC URL, không có embedded DB, driver hoặc starter cần thiết | Kiểm tra dependency, properties, database thật |
| Có `spring.datasource.url` nhưng vẫn dùng URL khác | Có DataSource tự tạo bằng code hoặc cấu hình/profile khác ghi đè | Kiểm tra bean thực tế và nguồn property được sử dụng |
| `spring.datasource.hikari.*` không có hiệu quả | Bean thực tế không phải Hikari hoặc không được bind | Kiểm tra `dataSource.getClass()` và cơ chế binding |
| Injection `DataSource` báo nhiều candidate | Nhiều bean cùng interface | Dùng `@Primary`, `@Qualifier` hoặc thiết kế lại bean wiring |
| Boot có DataSource nhưng thiếu template auto-config | Không có Spring JDBC, nhiều candidate hoặc có bean khác phù hợp | Xem condition report và khai báo bean thủ công nếu cần |
| Có template nhưng SQL lỗi “table not found” | Tạo kết nối rồi nhưng schema chưa được khởi tạo | Dùng migration/SQL initialization phù hợp |
| `@Transactional` không rollback | Chưa có proxy/manager đúng, self-invocation, sai DataSource hoặc nuốt exception | Kiểm tra context, bean manager, đường gọi và integration test |
| Nhiều request gây hết connection | Pool limit, connection leak, query/transaction chậm | Đo pool metrics, query latency, timeout và transaction length |

Một số lỗi có thể xảy ra trong cả hai mô hình vì chúng nằm ở DB/driver, không phải ở auto-configuration: sai credentials, mạng mất kết nối, deadlock, query chậm, bảng sai schema hoặc quyền người dùng DB không đủ.

## 11. Kiểm thử cấu hình và lựa chọn production

**Framework thuần:** viết kiểm thử tạo `ApplicationContext`, assert có đúng `DataSource`, `JdbcTemplate`, transaction manager và thử một thao tác thật; kiểm tra dọn dẹp context/pool khi đóng.

**Spring Boot:** dùng `@SpringBootTest` khi muốn kiểm tra wiring đầy đủ, hoặc `@JdbcTest` cho JDBC-focused test slice khi phù hợp. Test slice có thể thay DataSource bằng embedded test database tùy cấu hình. Nếu mục tiêu là kiểm tra chính xác connection tới PostgreSQL/MySQL và migration, hãy xác định behavior thay thế DB và dùng database thật hoặc Testcontainers.

Các kiểm thử hữu ích bất kể dùng cách nào:

- Thực hiện SELECT/INSERT đơn giản sau startup với test schema rõ ràng.
- Xác nhận duplicate key và exception translation.
- Xác nhận hai câu lệnh trong transaction rollback cùng nhau khi lệnh sau thất bại.
- Kiểm tra profile `dev`/`test`/`prod` dùng đúng URL/driver, không sử dụng nhầm H2 khi deployment.
- Kiểm tra connection pool có maximum size, connection timeout và close lifecycle hợp lý.
- Với nhiều DataSource, xác nhận từng `JdbcTemplate` và transaction manager trỏ đúng nguồn và bean selection không mơ hồ.

**Khuyến nghị production:** có connection pool phù hợp, secret từ runtime, giới hạn kết nối dựa trên sức chứa DB, timeout, metrics, migration có version, test rollback và xử lý lỗi. Boot giúp giảm phần wiring thường gặp nhưng **không tự chọn thông số đúng cho mọi tải và mọi database**.

## 12. Chọn cách nào khi xây ứng dụng?

Có thể quyết định dựa trên hoàn cảnh:

- **Ứng dụng Spring Boot thông thường, một JDBC database:** bắt đầu bằng `spring-boot-starter-jdbc`, driver và `spring.datasource.*`; tận dụng auto-configuration. Chỉ khai báo bean riêng khi có nhu cầu rõ.
- **Ứng dụng Spring Framework không dùng Boot:** đăng ký `DataSource`, template, transaction manager và property loading tường minh; chọn pool phù hợp môi trường.
- **Ứng dụng Boot có nhiều DB, datasource routing, custom pool, JNDI hoặc XA:** dùng cấu hình tường minh cho từng nguồn, xem chính xác điều kiện auto-config và transaction semantics.
- **Môi trường đặc biệt với chính sách hạ tầng:** có thể giữ Boot để dùng DI/observability, đồng thời tự quản một phần hoặc toàn bộ datasource wiring.

Đừng chọn theo số dòng Java config. Hãy cân nhắc **khả năng vận hành**, tính minh bạch, nhiều nguồn dữ liệu, cơ chế quản lý secrets, yêu cầu transaction và nhu cầu test.

### Câu hỏi tự kiểm tra

1. Vì sao chỉ có `spring-jdbc` trong Spring Framework thuần không khiến bean `DataSource` xuất hiện?
2. Spring Boot có thể tạo `JdbcTemplate` từ một bean `DataSource` do người dùng tự khai báo không? Những điều kiện nào liên quan?
3. Với bean `DriverManagerDataSource` tự tạo, thuộc tính `spring.datasource.hikari.maximum-pool-size` có tác dụng không?
4. Vì sao Spring Boot cần JDBC driver ở runtime dù đã có `spring.datasource.url`?
5. Nếu có hai DataSource, vì sao cần chọn `JdbcTemplate` và transaction manager theo từng nguồn?
6. Nếu có DataSource và chạy SELECT thành công, đã đủ để chứng minh transaction rollback đúng chưa?
7. `DataSourceAutoConfiguration` khác SQL schema initialization và JPA DDL ở điểm nào?
8. Khi một Boot app không auto-config DataSource, sẽ kiểm tra classpath, properties, bean hiện tại và condition report theo thứ tự nào?

**Ghi nhớ:** Spring Framework và Spring Boot sử dụng cùng các abstraction JDBC; điểm khác là **ai khai báo, chọn và bind các bean hạ tầng**. Spring Framework thuần yêu cầu wiring tường minh. Spring Boot áp dụng các default có điều kiện, tự lùi khi ứng dụng đã định nghĩa bean phù hợp, và cho phép cấu hình lại. Cả hai vẫn cần quản lý đúng JDBC driver, DataSource, pool, SQL schema và transaction.

### Tài liệu tham khảo chính thức

- Spring Framework — Data Access / JDBC: https://docs.spring.io/spring-framework/reference/data-access/jdbc.html
- Spring Framework — Data Access / Transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Boot — Working with SQL Databases: https://docs.spring.io/spring-boot/reference/data/sql.html
- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot — Auto-configuration: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
