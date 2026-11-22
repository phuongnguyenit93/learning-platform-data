# Đăng ký DataSource thành bean và cấp cấu hình kết nối trong Spring Framework

## 1. Mục tiêu bài học

`DataSource` là điểm bắt đầu của nhiều cơ chế truy cập cơ sở dữ liệu quan hệ trong Java và Spring. Một ứng dụng có thể tạo kết nối JDBC trực tiếp, nhưng với Spring Framework, cách thông dụng là **đăng ký một `DataSource` làm bean, để Spring quản lý vòng đời và cấp bean ấy cho các thành phần cần truy cập dữ liệu**.

Học xong bài này, bạn cần làm được những việc cụ thể:

1. Giải thích `javax.sql.DataSource` khác với `java.sql.Connection` và connection pool như thế nào.
2. Đăng ký `DataSource` bằng `@Configuration` và `@Bean` trong Spring Framework thuần, không phụ thuộc vào Spring Boot.
3. Cấp URL, tài khoản, mật khẩu và thông số pool từ cấu hình bên ngoài mã nguồn; xác định chính xác nguồn cấu hình.
4. Inject cùng `DataSource` vào `JdbcTemplate`, repository và transaction manager, không tự tạo pool ở từng nơi sử dụng.
5. Biết khi nào Spring Boot tự tạo bean và cách tránh tạo hai bean `DataSource` ngoài ý muốn.
6. Xác minh kết nối bằng một chương trình chạy được, hiểu thời điểm mở/đóng tài nguyên, và chẩn đoán những lỗi cấu hình phổ biến.

**Phạm vi:** trọng tâm là khai báo bean, binding thông số và lifecycle của kết nối. Các truy vấn JDBC phức tạp, transaction propagation, JPA và tối ưu SQL thuộc các phần học tiếp theo.

## 2. Phân biệt DataSource, Connection, pool và Spring bean

`javax.sql.DataSource` là một **interface tiêu chuẩn của Java**, có phương thức chủ yếu `getConnection()` để cấp một `java.sql.Connection`. Nó không mặc nhiên có nghĩa là connection pool: một implementation có thể mở kết nối mới mỗi lần gọi, hoặc lấy kết nối từ pool.

| Đối tượng | Chức năng | Ai nên quản lý? |
| --- | --- | --- |
| `DataSource` | Cấu hình và cung cấp JDBC connection | Spring IoC container giữ làm bean |
| `Connection` | Phiên giao tiếp JDBC với database; có transaction state | Mã JDBC hoặc Spring JDBC/transaction infrastructure mượn rồi trả/đóng đúng cách |
| Connection pool | Tái sử dụng kết nối vật lý, giới hạn số kết nối đồng thời | Implementation của `DataSource` như HikariCP |
| `JdbcTemplate` | Thực thi SQL, binding tham số, mapping kết quả và giải phóng tài nguyên | Được tạo làm bean, inject `DataSource` |
| Transaction manager | Phối hợp một hoặc nhiều lời gọi JDBC trong cùng transaction | Spring transaction infrastructure |

Luồng điển hình:

```text
Spring ApplicationContext
  ├── bean "dataSource" ──► HikariDataSource (pool)
  ├── bean "jdbcTemplate" ─► dùng bean DataSource ở trên
  └── bean "transactionManager" ─► dùng bean DataSource ở trên
                                         │ getConnection()
                                         ▼
                                   JDBC Connection
                                         │ driver
                                         ▼
                                   Database server
```

Một `DataSource` singleton **không phải** một `Connection` singleton. Các request có thể sử dụng các connection riêng được pool cấp phát, trong khi cùng tham chiếu đến một bean `DataSource`. Khi ứng dụng trả/đóng connection mượn từ HikariCP, pool thường nhận lại connection để tái sử dụng; khi Spring đóng context, bản thân pool mới được đóng.

Những nguyên tắc này đặc biệt quan trọng:

- Inject `DataSource` hoặc `JdbcTemplate`; không gọi `new HikariDataSource(...)` trong từng controller, service hay repository.
- Không lưu một JDBC `Connection` làm trường dùng chung giữa nhiều request/thread.
- Với Spring JDBC, hãy để `JdbcTemplate` lấy và trả connection. Nếu dùng JDBC thuần ngoài transaction do Spring quản lý, dùng `try-with-resources` cho connection, statement và result set.
- Khi có Spring transaction đang hoạt động, không tự commit/rollback hay tự đóng connection đang do transaction manager quản lý; ưu tiên `JdbcTemplate` hoặc API transaction-aware của Spring.

## 3. Quy trình tạo và đăng ký bean trong Spring Framework thuần

Với ứng dụng **không dùng Spring Boot**, bạn cần tự xác định bean `DataSource` và cơ chế nạp cấu hình. Một cấu hình phổ biến có dạng:

```java
@Configuration
@PropertySource("classpath:db.properties")
class DatabaseConfig {
    @Bean(destroyMethod = "close")
    HikariDataSource dataSource(Environment environment) {
        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(environment.getRequiredProperty("db.url"));
        config.setUsername(environment.getRequiredProperty("db.username"));
        config.setPassword(environment.getRequiredProperty("db.password"));
        config.setMaximumPoolSize(
                environment.getProperty("db.pool.max-size", Integer.class, 5));
        return new HikariDataSource(config);
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }
}
```

**Lưu ý:** Đây là đoạn minh họa nằm trong class cấu hình, chưa có phần import, ứng dụng khởi động và file cấu hình; phần 4 cung cấp một project **đầy đủ, có thể chạy độc lập**.

Giải nghĩa từng bước:

1. `@Configuration` đánh dấu class khai báo các bean cho container. `@Bean` trên method cho biết object trả về được đăng ký làm bean.
2. `@PropertySource("classpath:db.properties")` thêm file `.properties` từ classpath vào `Environment`. Spring Framework thuần **không tự hiểu `application.yml` theo cơ chế cấu hình của Spring Boot**.
3. `Environment` được Spring inject vào factory method. `getRequiredProperty` giúp phát hiện thiếu URL/username/password sớm; `getProperty` có thể cấp default có chủ đích cho thông số không nhạy cảm.
4. `HikariConfig` nhận JDBC URL, credential và các tham số pool. `new HikariDataSource(config)` tạo pool theo cấu hình đó.
5. `@Bean(destroyMethod = "close")` yêu cầu Spring gọi `close()` khi hủy bean, giải phóng kết nối của pool lúc đóng context.
6. `jdbcTemplate(DataSource dataSource)` nhận chính bean hiện có từ container. Spring resolve dependency theo kiểu; method không tự tạo `DataSource` thứ hai.

Đối với bean có thể đóng, Spring đôi khi suy luận được phương thức destroy; ở đây chỉ định `close` tường minh để làm rõ ý định. Việc hủy pool **khác** với thao tác `connection.close()` trên một connection đã mượn.

### Chọn implementation phù hợp

- `DriverManagerDataSource` (Spring JDBC) giúp ví dụ và test đơn giản, nhưng **không pooling**: mỗi `getConnection()` tạo một kết nối mới.
- `HikariDataSource` (HikariCP) là một lựa chọn pool phổ biến trong ứng dụng thật; cần khai báo dependency và cấu hình giới hạn thích hợp.
- `JndiObjectFactoryBean`/JNDI lookup phù hợp khi application server hoặc container cấp `DataSource` sẵn; khi đó đừng tạo thêm pool trùng lặp.
- `DataSource` có thể do framework auto-configuration tạo; nếu đã có bean đúng, hãy inject và sử dụng bean ấy.

## 4. Bài thực hành độc lập: đăng ký DataSource bằng @Bean

Ví dụ dùng **Java 17**, **Spring Framework 6.2.3**, **HikariCP 5.1.0** và **H2 2.3.232**. Phiên bản được cố định để minh họa tái lập được. Đây là ứng dụng Java đơn giản sử dụng Spring container, **không cần Spring Boot, máy chủ HTTP hoặc database cài ngoài**.

### 4.1. Cấu trúc file

```text
datasource-bean-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/demo/DataSourceBeanDemo.java
        └── resources/db.properties
```

`settings.gradle`:

```groovy
rootProject.name = 'datasource-bean-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.3'
    implementation 'org.springframework:spring-jdbc:6.2.3'
    implementation 'com.zaxxer:HikariCP:5.1.0'
    runtimeOnly 'com.h2database:h2:2.3.232'
    runtimeOnly 'org.slf4j:slf4j-simple:2.0.16'
}

application {
    mainClass = 'demo.DataSourceBeanDemo'
}
```

`src/main/resources/db.properties`:

```properties
# H2 trong bộ nhớ: chỉ là cấu hình ví dụ học tập.
db.url=jdbc:h2:mem:bean_demo;DB_CLOSE_DELAY=-1
db.username=sa
db.password=
db.pool.max-size=4
db.pool.connection-timeout-ms=30000
```

`db.password` trống chỉ vì H2 demo cho phép như vậy. **Không** sao chép mô hình lưu mật khẩu ngay trong file của repository cho database production. Trong `.properties`, URL H2 và chuỗi có dấu `;` được hiểu là giá trị văn bản bình thường.

`src/main/java/demo/DataSourceBeanDemo.java`:

```java
package demo;

import javax.sql.DataSource;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.PropertySource;
import org.springframework.core.env.Environment;
import org.springframework.jdbc.core.JdbcTemplate;

public class DataSourceBeanDemo {

    @Configuration
    @PropertySource("classpath:db.properties")
    static class DatabaseConfig {

        @Bean(destroyMethod = "close")
        HikariDataSource dataSource(Environment env) {
            HikariConfig config = new HikariConfig();

            config.setJdbcUrl(env.getRequiredProperty("db.url"));
            config.setUsername(env.getRequiredProperty("db.username"));
            config.setPassword(env.getRequiredProperty("db.password"));

            config.setMaximumPoolSize(
                    env.getProperty("db.pool.max-size", Integer.class, 4));
            config.setConnectionTimeout(
                    env.getProperty("db.pool.connection-timeout-ms",
                            Long.class, 30_000L));

            return new HikariDataSource(config);
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(DatabaseConfig.class)) {

            DataSource dataSource = context.getBean(DataSource.class);
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            jdbc.execute("""
                    CREATE TABLE projects (
                        id BIGINT PRIMARY KEY,
                        name VARCHAR(100) NOT NULL
                    )
                    """);

            int inserted = jdbc.update(
                    "INSERT INTO projects (id, name) VALUES (?, ?)",
                    7L, "DataSource bean");

            Integer count = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM projects", Integer.class);
            String name = jdbc.queryForObject(
                    "SELECT name FROM projects WHERE id = ?",
                    String.class, 7L);

            System.out.println("bean=" +
                    dataSource.getClass().getSimpleName());
            System.out.println("inserted=" + inserted);
            System.out.println("count=" + count);
            System.out.println("name=" + name);
        }
    }
}
```

Tại thư mục `datasource-bean-demo` có Gradle sẵn, chạy:

```bash
gradle run
```

Nếu bạn thêm Gradle Wrapper vào project, dùng `./gradlew run` trên Linux/macOS hoặc `gradlew.bat run` trên Windows. Dưới đây là **bốn dòng được viết bởi `System.out`**; log startup/shutdown của HikariCP hoặc Gradle có thể xuất hiện thêm:

```text
bean=HikariDataSource
inserted=1
count=1
name=DataSource bean
```

**Giải thích cơ chế:**

1. `AnnotationConfigApplicationContext` đọc `DatabaseConfig`, xử lý `@PropertySource`, gọi factory method `dataSource` và đưa object Hikari vào container.
2. Bean `jdbcTemplate` nhận cùng `DataSource`. Không cần truyền URL/username/password vào `JdbcTemplate`, vì nó chỉ cần interface `DataSource`.
3. Khi câu SQL đầu tiên chạy, `JdbcTemplate` yêu cầu connection, thực thi statement và trả connection về pool theo đúng lifecycle.
4. `db.url` chỉ định H2 in-memory; `DB_CLOSE_DELAY=-1` cho phép database trong bộ nhớ tồn tại qua việc đóng connection giữa các câu lệnh trong cùng JVM.
5. `jdbc.update` trả về số dòng bị tác động, nên `inserted=1`; hai truy vấn đọc lại dữ liệu tạo `count=1` và `name=DataSource bean`.
6. Khối `try-with-resources` đóng `ApplicationContext` khi kết thúc, khiến Spring gọi `HikariDataSource.close()`. Pool không bị tạo lại theo từng câu SQL.

**Thử nghiệm có ý nghĩa:**

- Xóa dòng `db.url=...`: `getRequiredProperty("db.url")` không tìm thấy property, bean không thể khởi tạo. Đây là lỗi cấu hình cần xử lý trước khi ứng dụng phục vụ request.
- Sửa H2 URL sang URL của database không tồn tại: có thể gặp lỗi lấy connection hoặc khởi tạo pool. Xem exception gốc và SQLState; không tự suy luận đó là lỗi `@Bean`.
- Đổi `db.pool.max-size` từ 4 sang 2 rồi quan sát cấu hình của pool; đây là giới hạn số connection **trong pool**, không phải số bean `DataSource`.
- Bỏ `@Bean` khỏi method `dataSource`: Spring sẽ không đăng ký object ấy làm bean, nên dependency `DataSource` của `jdbcTemplate` không được resolve (nếu không có bean thay thế).

## 5. Nguồn cấu hình và cách không hard-code thông tin kết nối

Một bean `DataSource` cần tối thiểu các thông tin tùy hệ quản trị:

- **JDBC URL:** loại driver/protocol, host, cổng, database, tham số kết nối; ví dụ PostgreSQL `jdbc:postgresql://db.example.internal:5432/orders`.
- **Username/password** hoặc cơ chế xác thực tương ứng (identity/IAM, wallet, secret provider...).
- **JDBC driver** trên runtime classpath, tương thích database và JDK.
- **Pool configuration:** kích thước tối đa, thời gian chờ lấy connection, timeout/idle/lifetime thích hợp.
- **Tùy chọn an toàn:** TLS và xác minh chứng chỉ, quyền database tối thiểu, timeout để tránh treo kéo dài.

Không đưa giá trị nhạy cảm thực vào mã Java, git repository, ví dụ học tập chia sẻ hoặc log. Tách cấu hình theo môi trường và cấp secret qua environment, secret manager hoặc cấu hình quản lý an toàn.

### Spring Framework thuần: Environment + PropertySource

Trong ví dụ ở phần 4, `@PropertySource("classpath:db.properties")` nạp file từ classpath; `Environment` gom các property source theo thứ tự ưu tiên. System properties hoặc environment variables có thể tham gia tùy môi trường và tên khóa; hãy kiểm tra **tên property được resolve thực tế**, không suy luận quy tắc “relaxed binding” của Spring Boot luôn tồn tại trong Spring Core.

Có thể tự định nghĩa các property source cho môi trường thật mà không thay Java code, chẳng hạn thêm nguồn từ file bên ngoài hoặc cấu hình bean nạp từ secret provider. Phương thức `getRequiredProperty` hữu ích để phát hiện thiếu thông số sớm. Tuy vậy, nó chỉ kiểm tra **sự tồn tại** của property; ứng dụng vẫn nên kiểm tra chuỗi không trống cho các giá trị bắt buộc khác với mật khẩu demo.

Với `@Value("${db.url}")` (nếu chọn cách injection bằng placeholder), cần hiểu cơ chế placeholder resolution đã được kích hoạt trong context. Trong một ứng dụng Spring Framework thuần, `Environment` là lựa chọn minh họa rõ ràng và ít phụ thuộc vào hạ tầng bổ sung hơn.

### Spring Boot: cấu hình khai báo khi có auto-configuration

Trong ứng dụng Spring Boot có `spring-boot-starter-jdbc` và JDBC driver phù hợp, **nếu các điều kiện auto-configuration thỏa mãn**, Boot thường tự tạo bean `DataSource` và dùng HikariCP khi có trên classpath. Khi đó có thể chỉ cần file `application.yml`:

```yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 10
      connection-timeout: 30000
```

Ví dụ giá trị `DB_URL` ở môi trường production có thể là `jdbc:postgresql://db.internal:5432/app`; phải bổ sung driver PostgreSQL tương ứng. Các giá trị `${...}` là placeholder của Spring Boot, yêu cầu biến môi trường hoặc property phù hợp thực sự có mặt.

**Không nên định nghĩa thêm một `@Bean DataSource` chỉ vì đã dùng Spring Boot.** Nếu tự cung cấp bean `DataSource`, cơ chế tự cấu hình `DataSource` mặc định thường lùi lại theo điều kiện của Boot; lúc ấy bạn chịu trách nhiệm về cấu hình, pooling, lifecycle và quan hệ với transaction manager. Kiểm tra bản Boot thực tế và report auto-configuration nếu hành vi khác mong đợi.

### Khi cần bean tùy biến trong Boot

Nếu có yêu cầu đặc biệt (nhiều database, tùy biến driver/pool, cơ chế xác thực), nên dùng cơ chế binding kiểu mạnh của Boot. Một mẫu giản lược với `DataSourceProperties` và HikariCP:

```java
// Đoạn minh họa riêng cho ứng dụng Spring Boot.
// Cần import DataSourceProperties, ConfigurationProperties,
// HikariDataSource và các annotation Spring liên quan.
@Bean
@ConfigurationProperties("app.datasource")
DataSourceProperties appDataSourceProperties() {
    return new DataSourceProperties();
}

@Bean(destroyMethod = "close")
@ConfigurationProperties("app.datasource.hikari")
HikariDataSource appDataSource(DataSourceProperties appDataSourceProperties) {
    return appDataSourceProperties.initializeDataSourceBuilder()
            .type(HikariDataSource.class)
            .build();
}
```

Với ví dụ này, `app.datasource.url/username/password` được bind vào `DataSourceProperties`; cấu hình `app.datasource.hikari.*` tùy biến pool. Đây là **đoạn minh họa**, không phải toàn bộ class chạy độc lập; trong ứng dụng nhiều nguồn dữ liệu cần đặt tên bean/`@Qualifier` rõ ràng và tránh injection mơ hồ. Với một database thông thường, ưu tiên cấu hình Boot chuẩn trước khi tự viết factory method.

## 6. Cấp bean cho repository, JdbcTemplate và transaction manager

Đăng ký bean chỉ là bước đầu; điều quan trọng là **mọi thành phần cùng một database phải sử dụng đúng `DataSource` dự kiến**.

Một cấu hình Spring JDBC thuần có thể thêm transaction manager như sau:

```java
// Bổ sung vào class @Configuration đã có bean DataSource.
// Đoạn minh họa; cần imports tương ứng.
@Bean
JdbcTemplate jdbcTemplate(DataSource dataSource) {
    return new JdbcTemplate(dataSource);
}

@Bean
JdbcTransactionManager transactionManager(DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}
```

`JdbcTransactionManager` triển khai `PlatformTransactionManager` cho JDBC trên cùng `DataSource`. Để sử dụng `@Transactional` trong Spring Framework thuần theo proxy mode, cần bật quản lý transaction (ví dụ `@EnableTransactionManagement`), gọi service qua Spring-managed bean và hiểu giới hạn self-invocation. Chi tiết về propagation và rollback thuộc bài transaction; ở đây điểm mấu chốt là **DataSource phải khớp**.

Một repository có thể được inject:

```java
@Repository
public class ProjectRepository {
    private final JdbcTemplate jdbcTemplate;

    public ProjectRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public int countProjects() {
        Integer count = jdbcTemplate.queryForObject(
                "SELECT COUNT(*) FROM projects", Integer.class);
        return count == null ? 0 : count;
    }
}
```

Đây là snippet riêng, không phải class nằm trong chương trình demo ở phần 4; cần đặt đúng package/import và kích hoạt component scanning hoặc đăng ký repository bean. Ứng dụng nên inject dependency qua constructor để rõ ràng và dễ kiểm thử.

**Tại sao cùng DataSource quan trọng?** Khi Spring quản lý một JDBC transaction, tài nguyên kết nối được gắn với transaction hiện tại. `JdbcTemplate` có thể tham gia connection/transaction đó qua hạ tầng Spring; tự tạo pool khác hoặc tự `DriverManager.getConnection(...)` trong DAO có thể đưa thao tác ra ngoài transaction dự kiến.

Nếu ứng dụng có **hai `DataSource`** (ví dụ `ordersDataSource` và `reportingDataSource`), hãy đặt tên rõ, dùng `@Qualifier` để chọn đúng bean khi inject `JdbcTemplate` và transaction manager; hoặc thiết lập bean `@Primary` có chủ đích. Một JDBC transaction manager thông thường gắn với một `DataSource`: đừng mặc định rằng transaction trên database A tự rollback thao tác ở database B.

## 7. Vòng đời pool và các giá trị cấu hình cần hiểu

**`maximumPoolSize`:** số connection vật lý tối đa pool có thể quản lý cùng lúc. Nếu đã hết connection rảnh, caller phải chờ đến khi có connection được trả hoặc `connectionTimeout` hết hạn; lúc ấy HikariCP có thể ném `SQLException`. Giới hạn 10 là **mỗi instance/pool**, không phải toàn cụm deployment.

**`connectionTimeout`:** thời gian tối đa chờ mượn connection từ pool, tính bằng millisecond đối với setter Hikari. Nó **không đồng nhất** với timeout thực thi một câu SQL hoặc socket/network timeout của JDBC driver.

**`maxLifetime` / `idleTimeout` / `keepaliveTime`:** liên quan vòng đời kết nối và việc pool chủ động duy trì kết nối; chọn theo giới hạn timeout của database/proxy/network. Không đặt giá trị tùy tiện thấp đến mức gây đóng/mở liên tục.

**`minimumIdle`:** số connection nhàn rỗi pool cố gắng duy trì. Nếu không có nhu cầu đặc biệt, có thể bắt đầu với mặc định của pool và đo tải thực tế trước khi tinh chỉnh.

**Lifecycle:** trong một Spring context thông thường, bean `DataSource` nên là singleton và sống xuyên suốt ứng dụng. Spring đóng pool khi shutdown. Connection được mượn từ pool cần được trả sớm; không giữ connection khi chờ network API hay chạy tác vụ tính toán dài không cần database.

Ví dụ năng lực kết nối: nếu có 6 instance, mỗi instance cấu hình `maximumPoolSize=10` thì tổng nhu cầu cực đại từ sáu pool có thể đạt **60 connection** (chưa tính admin, migration, monitoring và dịch vụ khác). Phải cân bằng giới hạn kết nối database với số instance/pool, độ dài transaction và concurrency; “pool càng lớn càng nhanh” thường sai.

**Pool không giải quyết mọi vấn đề:** transaction kéo dài, query chậm, deadlock, khóa bị tranh chấp, thiếu index hoặc connection leak vẫn làm ứng dụng nghẽn. Quan sát số connection active/idle/pending, latency mượn connection, thời gian truy vấn và timeout; chỉ chỉnh pool sau khi xác định nguyên nhân.

## 8. Phân biệt các hình thức cấu hình theo môi trường

| Tình huống | Nên đăng ký DataSource thế nào? | Nguồn cấu hình |
| --- | --- | --- |
| Console app / Spring Framework thuần | `@Configuration` + `@Bean` hoặc hạ tầng sẵn có | `Environment`, `@PropertySource`, nguồn ngoài |
| Spring Boot với một database | Để `DataSourceAutoConfiguration` tạo bean khi phù hợp | `spring.datasource.*` và environment/secret manager |
| Spring Boot có nhiều database | Bean được đặt tên tường minh, binding và qualifier rõ | Prefix riêng cho từng database |
| Chạy trong application server có JNDI | Lấy `DataSource` mà server đã quản lý | JNDI name và cấu hình server |
| Integration test | Test `DataSource` H2 hoặc container database thật | Profile test, test properties, ephemeral database |
| Production | Pool giới hạn có kiểm soát và credential an toàn | Secret manager/environment, URL/TLS/driver theo môi trường |

**Không nên dùng `DriverManagerDataSource` cho workload cần pooling.** Hãy để một implementation pool ổn định làm bean, tránh pool mới ở mỗi request.

## 9. Quy trình kiểm tra một DataSource bean hoạt động

Kiểm tra theo thứ tự để phân biệt lỗi DI, cấu hình, driver và database:

1. **Bean có tồn tại?** `ApplicationContext.getBean(DataSource.class)` hoặc kiểm tra tên bean. Nếu báo không tìm thấy, xác nhận `@Configuration` được import/scan, `@Bean` được xử lý và Boot auto-configuration có thực sự kích hoạt.
2. **Có nhiều bean cùng kiểu?** Khi inject theo `DataSource.class` mà có hai ứng viên, Spring có thể báo `NoUniqueBeanDefinitionException`. Đặt tên, `@Qualifier` hoặc `@Primary` có chủ đích.
3. **Thông số có được resolve?** Kiểm tra tên property và profile, bảo đảm URL, username và secret có mặt. Có thể log host/database ID đã che thông tin nhạy cảm; **không log password, full connection string chứa secret hoặc token**.
4. **Driver hiện diện?** Thiếu JDBC driver trên runtime classpath có thể khiến Hikari/DriverManager không khởi tạo connection. Cài đúng driver cho JDBC URL và phiên bản JDK/database.
5. **Database có truy cập được?** Kiểm tra DNS, firewall, cổng, TLS, database name và tài khoản/quyền truy cập; không quy mọi `SQLException` thành lỗi Spring.
6. **Pool có cấp connection?** Nếu startup thành công mà request timeout, xem connection leak, transaction kéo dài, pool active/pending và giới hạn database.
7. **JdbcTemplate và transaction manager trỏ vào đâu?** Cả hai phải dùng đúng bean tương ứng. Đặc biệt khi có nhiều pool, assert rõ dependency thay vì dựa vào tên biến.
8. **Test được luồng thực?** Chạy ít nhất một SQL đơn giản và giải phóng context; với database thật nên kiểm chứng quyền query/write cần thiết và TLS.

### Những lỗi thường gặp

| Dấu hiệu | Lỗi phổ biến | Cách xử lý |
| --- | --- | --- |
| `NoSuchBeanDefinitionException: DataSource` | Config không được đăng ký hoặc auto-configuration không áp dụng | Import/scan `@Configuration`; kiểm tra condition report của Boot |
| `NoUniqueBeanDefinitionException` | Có nhiều `DataSource` nhưng inject không rõ | Dùng qualifier/primary và đặt tên giao dịch |
| Không tìm thấy `db.url` | Thiếu `@PropertySource`, sai classpath, sai tên property | Xác minh file resource và nguồn `Environment` |
| “No suitable driver” / driver class not found | Chưa có driver trong runtime dependency | Thêm JDBC driver thích hợp và kiểm tra URL |
| Login failed / authentication error | Sai credential, quyền hoặc xác thực | Sửa secret, tài khoản và quyền; không in secret |
| Connection refused / timed out | Host, port, network, TLS, DB chưa sẵn sàng | Kiểm tra mạng, service/database, chứng chỉ |
| Connection is not available / timeout from pool | Pool cạn hoặc connection bị giữ quá lâu | Đo active/pending, transaction duration, leak |
| Thao tác rollback không đúng | Dùng nhầm `DataSource`/transaction manager hoặc ra ngoài proxy | Kiểm tra bean wiring và test rollback |
| H2 test chạy nhưng production thất bại | Dialect, type, privilege, TLS và behavior khác | Integration test trên DB tương thích production |

## 10. Kiểm thử cấu hình đúng bằng hành vi, không chỉ bằng việc khởi động

Bài demo đã chứng minh ba việc: Spring trả về một `DataSource` bean, `JdbcTemplate` dùng được nó, và H2 thực thi được thao tác ghi/đọc. Trong dự án thật, nên kiểm tra thêm:

- **DI:** repository nhận đúng bean `JdbcTemplate`/`DataSource`, đặc biệt nếu có nhiều connection pool.
- **Lifecycle:** Spring context đóng pool; không tự tạo pool thủ công mỗi lần gọi repository.
- **Connection validation:** test truy vấn `SELECT 1` hoặc thao tác thật với database test.
- **Configuration failure:** khi thiếu property bắt buộc, ứng dụng báo lỗi rõ ngay trong startup thay vì chạy với kết nối mặc định nguy hiểm.
- **Transaction consistency:** các repository thuộc cùng nghiệp vụ tham gia cùng transaction manager, kiểm chứng rollback bằng integration test riêng.
- **Production parity:** test truy cập với loại database/driver gần production, vì H2 không mô phỏng đầy đủ dialect, isolation, permission hoặc TLS.

**Đề bài thực hành mở rộng:** thay H2 demo bằng PostgreSQL test. Đưa URL và credential ra môi trường, thêm PostgreSQL JDBC driver, giữ nguyên `JdbcTemplate` và logic insert/query. Nếu ứng dụng phải thay đổi lớp repository chỉ vì host hoặc credential thay đổi, phần tách cấu hình và dependency injection chưa tốt.

## 11. Câu hỏi tự đánh giá

1. Có phải `DataSource` luôn là connection pool? Hãy đưa ví dụ một implementation không pooling.
2. Tại sao `@Bean` thường nằm trong `@Configuration`, và vì sao nên inject `DataSource` thay vì `new` ở repository?
3. Khi gọi `getBean(DataSource.class)`, điều gì xảy ra nếu không có bean hoặc có hai bean cùng kiểu?
4. `@PropertySource` và `Environment` phối hợp thế nào trong Spring Framework thuần? `application.yml` có tự được nạp như trong Boot không?
5. Vì sao `@Bean(destroyMethod="close")` có ý nghĩa với `HikariDataSource` nhưng không có nghĩa là đóng pool sau mỗi query?
6. `maximumPoolSize=10` với tám application instance có thể tạo áp lực tối đa bao nhiêu connection từ tám pool đó?
7. Một application có hai database và hai transaction manager: dùng cách nào để tránh repository A nhận nhầm `DataSource` B?
8. Tại sao ứng dụng chạy được với H2 trong memory vẫn cần test kết nối/driver/query trên database thật?
9. Khi pool timeout, cần quan sát gì trước khi quyết định tăng `maximumPoolSize`?
10. Trong Spring Boot, khi nào bạn cần khai báo `@Bean DataSource`, và khi nào chỉ cần cấu hình `spring.datasource.*`?

**Tiêu chí hoàn thành:** tự tạo và chạy project ở phần 4, đổi được cấu hình kết nối mà không sửa mã repository, giải thích đúng lifecycle của `DataSource`/`Connection`/pool, và xác định được lý do một bean truy cập dữ liệu không inject được hoặc không kết nối được.

## 12. Nguồn đọc sâu

- Java SE 17 `DataSource`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/javax/sql/DataSource.html
- Spring Framework JDBC Package và DataSource: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- Spring Framework Java-based container configuration: https://docs.spring.io/spring-framework/reference/core/beans/java.html
- Spring Boot Data SQL / DataSource Configuration: https://docs.spring.io/spring-boot/reference/data/sql.html
- HikariCP configuration: https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby

Khi tham khảo API và ví dụ, hãy đối chiếu đúng nhánh phiên bản Spring, Boot, driver và database của dự án đang làm việc.