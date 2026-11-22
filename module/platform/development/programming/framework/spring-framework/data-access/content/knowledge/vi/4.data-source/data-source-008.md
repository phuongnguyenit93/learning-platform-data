# Tiêm đúng DataSource khi ứng dụng có nhiều nguồn

## Mục tiêu và tình huống

Một ứng dụng Spring có thể làm việc với hai cơ sở dữ liệu: **orders** chứa đơn hàng và **audit** chứa nhật ký nghiệp vụ. Cả hai nguồn được biểu diễn bằng interface `javax.sql.DataSource`. Khi trong Spring container có nhiều bean cùng kiểu `DataSource`, việc tiêm phụ thuộc (dependency injection, DI) phải chỉ rõ **bean nào phục vụ đường truy cập dữ liệu nào**.

Sau bài này, bạn có thể:

1. Nhận ra lỗi tiêm nguồn dữ liệu không rõ ràng và lý do chọn nhầm nguồn còn nguy hiểm hơn một lỗi khởi động.
2. Phân biệt tên bean, `@Qualifier` và `@Primary` khi tiêm `DataSource`, `JdbcTemplate` hoặc repository.
3. Cấu hình và chạy một ví dụ Java 17+ có hai H2 database độc lập, kiểm tra dữ liệu đi đúng nơi.
4. Chọn đúng transaction manager cho mỗi nguồn và nhận biết giới hạn giao dịch khi một nghiệp vụ tác động hai database.
5. Vận dụng nguyên tắc tương tự cho Spring Data JPA và Spring Boot mà không nhầm auto-configuration với DI.

Trọng tâm của bài là **lựa chọn nguồn dữ liệu chính xác tại điểm tiêm**. Pool tuning, chi tiết JPA mapping, distributed transaction và routing đa tenant sẽ chỉ được nhắc khi cần để tránh sai sót thực tế.

## 1. Vì sao có nhiều DataSource dễ bị tiêm nhầm?

`DataSource` là interface JDBC cung cấp `Connection`. Nó không mang tên nghiệp vụ “orders” hay “audit” trong hệ thống kiểu Java. Hai bean như sau đều có cùng kiểu:

```java
DataSource ordersDataSource;
DataSource auditDataSource;
```

Nếu một bean khác yêu cầu theo kiểu mà không định danh:

```java
@Bean
JdbcTemplate jdbcTemplate(DataSource dataSource) {
    return new JdbcTemplate(dataSource);
}
```

Spring sẽ có nhiều ứng viên `DataSource`. Khi không có cơ chế chọn được duy nhất, ứng dụng thường lỗi khởi tạo, ví dụ `NoUniqueBeanDefinitionException` hoặc lỗi dependency không thể thỏa mãn. Nhưng nếu có `@Primary` hay cơ chế phân giải khác, Spring có thể chọn một ứng viên **hợp lệ về mặt DI nhưng sai về nghiệp vụ**.

Các tình huống dễ gặp:

- `OrderRepository` ghi dữ liệu đơn hàng vào database audit vì nhận nhầm `DataSource`.
- Hai database đều có bảng `users`, nên câu SQL chạy thành công dù thực chất đọc sai tập người dùng.
- `JdbcTemplate` đang sử dụng nguồn orders, còn `@Transactional` lại quản lý transaction của nguồn audit. Lỗi xảy ra nhưng thao tác orders không rollback như người viết nghĩ.
- Local chỉ có một database, còn staging/production có hai nguồn và cấu hình bean khác nhau.

**Nguyên tắc:** xác định danh tính nguồn từ `DataSource → JdbcTemplate/EntityManagerFactory → Repository → TransactionManager`; kiểm tra đường nối này bằng test và kết nối thực tế.

## 2. Tên bean, @Qualifier và @Primary

### 2.1. Tên bean là danh tính của một nguồn

Khai báo `@Bean("ordersDataSource")` cho bean kết nối orders và `@Bean("auditDataSource")` cho audit. Tên nên phản ánh vai trò ổn định của nguồn, tránh `dataSource1` và `dataSource2`.

Ví dụ đặt tên bean dưới đây chỉ minh họa cú pháp, **không phải code độc lập chạy được**, vì phương thức tạo connection source được lược bỏ:

```java
@Bean("ordersDataSource")
DataSource ordersDataSource() {
    return createOrdersDataSource();
}

@Bean("auditDataSource")
DataSource auditDataSource() {
    return createAuditDataSource();
}
```

Tên bean giúp người đọc biết database nào được sử dụng tại mỗi nơi cấu hình; nó cũng hỗ trợ tìm đúng bean trong `ApplicationContext` và kiểm thử.

### 2.2. @Qualifier chọn bean ngay tại điểm tiêm

`@Qualifier` giới hạn các ứng viên theo qualifier/tên bean được chỉ định. Ví dụ:

```java
@Bean("auditJdbc")
JdbcTemplate auditJdbc(
        @Qualifier("auditDataSource") DataSource source) {
    return new JdbcTemplate(source);
}
```

Khi ứng dụng có hai bean `DataSource`, phương thức `auditJdbc` này vẫn nhận nguồn `auditDataSource`. Có thể dùng qualifier tương tự trong constructor:

```java
public AuditRepository(
        @Qualifier("auditJdbc") JdbcTemplate jdbc) {
    this.jdbc = jdbc;
}
```

Đoạn constructor giả định class có trường `jdbc`; xem ví dụ chạy được ở chương 4. Nếu class có một constructor duy nhất và được Spring quản lý, thông thường không cần thêm `@Autowired`.

**Qualify cả lớp trung gian.** Đặt tên cho hai `DataSource` rồi xây hai `JdbcTemplate` cùng kiểu chưa đủ: repository còn phải nhận đúng template. `@Qualifier` được dùng ở **điểm tiêm**, không chỉ ở nơi định nghĩa bean.

`@Qualifier` không chuyển kết nối mỗi lần chạy SQL. Nó định tuyến **phụ thuộc tới bean được chọn tại thời điểm khởi tạo**; một `JdbcTemplate` dùng `DataSource` được cấu hình cho nó, trừ khi nguồn đó chủ động triển khai cơ chế routing.

### 2.3. @Primary chỉ một lựa chọn mặc định

`@Primary` đánh dấu bean được ưu tiên khi có nhiều ứng viên cùng kiểu và injection point không có cách chọn cụ thể hơn. Chẳng hạn:

```java
@Bean("ordersDataSource")
@Primary
DataSource ordersDataSource() {
    return createOrdersDataSource();
}
```

Đây cũng chỉ là đoạn minh họa, vì `createOrdersDataSource()` không được định nghĩa tại đây.

Đánh dấu orders là primary có thể phù hợp khi đó là nguồn mặc định được thống nhất cho phần lớn ứng dụng. Tuy nhiên:

- Một điểm tiêm có `@Qualifier("auditDataSource")` vẫn chọn audit, kể cả khi orders là primary.
- `@Primary` trên `DataSource` **không tự biến** `ordersJdbc` thành primary trong số các bean `JdbcTemplate`.
- Tương tự, `@Primary` trên một nguồn kết nối **không tự chọn** transaction manager tương ứng cho mọi `@Transactional`.
- Dùng `@Primary` chỉ để làm lỗi biến mất có thể che giấu một đường truy cập dữ liệu sai.

Khi hai nguồn có vai trò ngang nhau, dùng qualifier explicit ở mỗi điểm cần chọn nguồn thường dễ kiểm tra hơn việc áp đặt một default.

### 2.4. Không dựa vào tên biến hay tên tham số

Spring có thể xét tên tham số/tên bean khi phân giải autowiring theo một số quy tắc, nhưng điều đó phụ thuộc metadata biên dịch và cách đăng ký bean. Một lần đổi tên tham số hoặc điều chỉnh cấu hình biên dịch có thể khiến kết quả khác dự kiến.

Với nguồn quan trọng, hãy chỉ định `@Qualifier("ordersDataSource")` hoặc `@Qualifier("auditDataSource")` ngay tại điểm tiêm. Việc này thể hiện ý nghĩa nghiệp vụ mà không phụ thuộc sự trùng hợp của tên biến.

## 3. Thiết kế luồng bean trước khi code

Hai nguồn dữ liệu cố định có thể tổ chức như sau:

```text
                         Spring ApplicationContext
                                     |
                +--------------------+--------------------+
                |                                         |
                v                                         v
        ordersDataSource                           auditDataSource
                |                                         |
                | @Qualifier("ordersDataSource")          | @Qualifier("auditDataSource")
                v                                         v
            ordersJdbc                                auditJdbc
                |                                         |
                | @Qualifier("ordersJdbc")                | @Qualifier("auditJdbc")
                v                                         v
         OrdersRepository                          AuditRepository
                |                                         |
                +--------------------+--------------------+
                                     |
                                Business Service
                         (quyết định use case phù hợp)
```

Có bốn trách nhiệm cần giữ rõ:

1. **Nguồn kết nối:** mỗi `DataSource` đại diện một nguồn cấu hình JDBC (URL, credentials, driver, pool). Một bean `DataSource` cũng có thể là router nếu chủ đích thiết kế như vậy; ví dụ này không dùng router.
2. **Công cụ truy vấn:** `JdbcTemplate` nhận nguồn qua constructor. Với hai nguồn độc lập, tạo mỗi template riêng giúp nhận diện rõ.
3. **Repository:** mỗi repository gói SQL/ánh xạ của một miền dữ liệu và nhận template thích hợp. Service gọi repository theo nhu cầu nghiệp vụ, không phải chọn bean theo tên tùy tiện.
4. **Giao dịch:** một transaction manager phải khớp với datasource của các thao tác mà nó cần quản lý; đây là mối liên hệ **riêng** so với wiring repository.

Nếu cấu hình phức tạp, hãy lập bảng ánh xạ nguồn kết nối → bean → template → repository → manager và đối chiếu với database URL/schema thực tế.

## 4. Ví dụ chạy được: hai H2 database với Spring Framework

Ví dụ sử dụng **Java 17+**, Spring Framework **6.2.x**, Gradle và H2 in-memory. Nó minh họa cùng lúc hai `DataSource`, hai `JdbcTemplate` và hai repository. Không cần Spring Boot, HTTP server hay cài một database bên ngoài.

Cấu trúc:

```text
multi-data-source-demo/
├── build.gradle
└── src/main/java/example/MultiDataSourceDemo.java
```

Nội dung `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.12'
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'example.MultiDataSourceDemo'
}
```

Nội dung `src/main/java/example/MultiDataSourceDemo.java`:

```java
package example;

import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

@Configuration
public class MultiDataSourceDemo {

    // Cùng kiểu DataSource nhưng hai địa chỉ database khác nhau.
    @Bean("ordersDataSource")
    DataSource ordersDataSource() {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:orders_db;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");
        return ds;
    }

    @Bean("auditDataSource")
    DataSource auditDataSource() {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:audit_db;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");
        return ds;
    }

    // Chọn đích bằng qualifier, không phụ thuộc bean mặc định.
    @Bean("ordersJdbc")
    JdbcTemplate ordersJdbc(
            @Qualifier("ordersDataSource") DataSource source) {
        return new JdbcTemplate(source);
    }

    @Bean("auditJdbc")
    JdbcTemplate auditJdbc(
            @Qualifier("auditDataSource") DataSource source) {
        return new JdbcTemplate(source);
    }

    // Hai JdbcTemplate cũng cùng kiểu: phải chọn đúng template.
    @Bean
    OrdersRepository ordersRepository(
            @Qualifier("ordersJdbc") JdbcTemplate jdbc) {
        return new OrdersRepository(jdbc);
    }

    @Bean
    AuditRepository auditRepository(
            @Qualifier("auditJdbc") JdbcTemplate jdbc) {
        return new AuditRepository(jdbc);
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                MultiDataSourceDemo.class)) {

            OrdersRepository orders =
                    context.getBean(OrdersRepository.class);
            AuditRepository audit =
                    context.getBean(AuditRepository.class);

            orders.createTable();
            audit.createTable();

            orders.save(10L, "PAID");
            audit.append(10L, "order-created");

            System.out.println("orders/10=" + orders.findStatus(10L));
            System.out.println("audit/10=" + audit.findEvent(10L));
        }
    }

    static final class OrdersRepository {
        private final JdbcTemplate jdbc;

        OrdersRepository(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        void createTable() {
            jdbc.execute("""
                    CREATE TABLE orders (
                        id BIGINT PRIMARY KEY,
                        status VARCHAR(30) NOT NULL
                    )
                    """);
        }

        void save(long id, String status) {
            jdbc.update(
                    "INSERT INTO orders (id, status) VALUES (?, ?)",
                    id, status);
        }

        String findStatus(long id) {
            return jdbc.queryForObject(
                    "SELECT status FROM orders WHERE id = ?",
                    String.class, id);
        }
    }

    static final class AuditRepository {
        private final JdbcTemplate jdbc;

        AuditRepository(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        void createTable() {
            jdbc.execute("""
                    CREATE TABLE audit_events (
                        id BIGINT PRIMARY KEY,
                        event_name VARCHAR(100) NOT NULL
                    )
                    """);
        }

        void append(long id, String eventName) {
            jdbc.update(
                    "INSERT INTO audit_events (id, event_name) VALUES (?, ?)",
                    id, eventName);
        }

        String findEvent(long id) {
            return jdbc.queryForObject(
                    "SELECT event_name FROM audit_events WHERE id = ?",
                    String.class, id);
        }
    }
}
```

Chạy ở thư mục dự án:

```bash
gradle run
```

Nếu có Gradle Wrapper, bạn có thể chạy `./gradlew run` trên Linux/macOS hoặc `gradlew.bat run` trên Windows. Gradle sẽ có log riêng; **stdout do chương trình Java in** là hai dòng:

```text
orders/10=PAID
audit/10=order-created
```

Tại sao ví dụ đúng nguồn:

- `ordersDataSource` kết nối với `jdbc:h2:mem:orders_db;DB_CLOSE_DELAY=-1`, `auditDataSource` với `jdbc:h2:mem:audit_db;DB_CLOSE_DELAY=-1`. Đây là hai H2 database riêng trong cùng JVM.
- `ordersJdbc` được tiêm source orders, `auditJdbc` được tiêm source audit. `OrdersRepository` chỉ nhận `ordersJdbc`, `AuditRepository` chỉ nhận `auditJdbc`.
- Các repository được tạo qua `@Bean`. Không cần `@Repository` hoặc component scanning trong chương trình này.
- Không có `@Primary`: nếu một thành phần mới yêu cầu `DataSource` không qualifier, lỗi không có ứng viên duy nhất sẽ giúp phát hiện rằng nó chưa chọn nguồn.
- `DriverManagerDataSource` mở connection theo yêu cầu, phù hợp ví dụ nhỏ nhưng **không phải pool dành cho production**.
- Với H2 URL `DB_CLOSE_DELAY=-1`, memory database vẫn tồn tại giữa những lần đóng connection trong cùng JVM; dữ liệu mất sau khi JVM kết thúc.

### 4.1. Kiểm tra URL thật mà template dùng

Tên bean có thể bị đặt sai. Để xác minh chính source thực tế, có thể dùng JDBC metadata qua `JdbcTemplate`:

```java
import org.springframework.jdbc.core.ConnectionCallback;

// Ví dụ là đoạn trích ở nơi đã có biến ordersJdbc, auditJdbc.
String ordersUrl = ordersJdbc.execute(
        (ConnectionCallback<String>) connection ->
                connection.getMetaData().getURL());

String auditUrl = auditJdbc.execute(
        (ConnectionCallback<String>) connection ->
                connection.getMetaData().getURL());
```

Đây là **đoạn minh họa**, không phải file Java độc lập. Hai URL phải trỏ đến nguồn dự định; kiểm tra cả catalog/schema hiện hành và dữ liệu seed nếu nhiều database có bảng giống nhau. Không in connection URL hoặc secrets nhạy cảm trong log production.

## 5. Constructor injection và vai trò của repository

Khi repository nhận dependency trong constructor, nguồn bắt buộc được xác định khi Spring tạo bean. Điều này hỗ trợ bất biến trường `final`, unit test và đọc đường phụ thuộc dễ hơn field injection.

Ví dụ **trích đoạn** cho project dùng component scanning:

```java
@Repository
public class AuditRepository {
    private final JdbcTemplate jdbc;

    public AuditRepository(
            @Qualifier("auditJdbc") JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    // Các thao tác dữ liệu audit sử dụng cùng jdbc này.
}
```

Cần import `Repository`, `Qualifier` và `JdbcTemplate` tương ứng. `@Repository` giúp Spring nhận diện thành phần khi scan package; nó **không tự biết database nào đúng**, và không thay `@Qualifier`. Ở chương 4 đã đăng ký repository bằng `@Bean`, nên không kết hợp thêm component scanning cho cùng repository.

Nếu nhiều tầng truy vấn được sử dụng, chọn nguồn tại nơi xây adapter/repository rồi tiêm **repository theo ý nghĩa nghiệp vụ** vào service. Không nên để controller hoặc mỗi câu SQL tự tìm `ApplicationContext.getBean("...")`, vì cách đó giấu dependency và khó test.

## 6. Bảng đối chiếu khi có nhiều nguồn

| Orders | Audit | Vai trò |
| --- | --- | --- |
| `ordersDataSource` | `auditDataSource` | Nguồn JDBC, URL/credentials/driver/pool |
| `ordersJdbc` | `auditJdbc` | `JdbcTemplate` sử dụng từng nguồn |
| `OrdersRepository` | `AuditRepository` | Truy vấn/ghi dữ liệu cho miền tương ứng |
| `ordersTransactionManager` | `auditTransactionManager` | Transaction manager gắn với nguồn |
| `app.datasource.orders.*` | `app.datasource.audit.*` | Ví dụ prefix thuộc tính khi cấu hình ngoài mã |

Để phát hiện wiring sai, đối chiếu **cả chuỗi**, không chỉ nhìn `@Bean` của hai DataSource.

### 6.1. Cấu hình ngoài mã nguồn và connection pool

Trong hệ thống thật, URL, username, password và kích thước pool cần lấy từ cấu hình/environment variables hoặc secret manager. Ví dụ YAML bên dưới chỉ minh họa hai prefix thuộc tính; **Spring Framework không tự động tạo hai DataSource chỉ vì có YAML**:

```yaml
app:
  datasource:
    orders:
      url: jdbc:postgresql://orders-db:5432/orders
      username: orders_app
      password: ${ORDERS_DB_PASSWORD}
    audit:
      url: jdbc:postgresql://audit-db:5432/audit
      username: audit_app
      password: ${AUDIT_DB_PASSWORD}
```

Với Spring Boot, bạn cần bean/configuration binding tương ứng, ví dụ `@ConfigurationProperties` kết hợp `DataSourceProperties` hoặc xây pool từ thuộc tính. Khi dùng HikariCP trực tiếp, nó có thuộc tính `jdbcUrl`/`jdbc-url` chứ không phải JavaBean property `url` thông thường; `DataSourceProperties` giúp xử lý ánh xạ này trong kiểu cấu hình phù hợp. Cần đọc tài liệu của đúng phiên bản Spring Boot.

Production nên dùng connection pool thích hợp (ví dụ HikariCP) **cho từng nguồn**, đặt pool size, timeout, health check, metrics và quyền truy cập riêng. Không copy cấu hình pool từ database lớn sang database nhỏ một cách máy móc.

## 7. Chọn đúng transaction manager theo từng nguồn

Đây là lỗi thường bị bỏ qua: **tiêm đúng `JdbcTemplate` không tự bảo đảm `@Transactional` điều phối đúng database**.

Một cấu hình Spring JDBC có thể khai báo manager riêng cho orders và audit. Đoạn dưới đây là **cấu hình bổ sung** trong dự án đã có `ordersDataSource` và `auditDataSource`, không phải file biên dịch độc lập:

```java
@Configuration
@EnableTransactionManagement
public class TransactionConfiguration {

    @Bean("ordersTransactionManager")
    PlatformTransactionManager ordersTransactionManager(
            @Qualifier("ordersDataSource") DataSource ds) {
        return new JdbcTransactionManager(ds);
    }

    @Bean("auditTransactionManager")
    PlatformTransactionManager auditTransactionManager(
            @Qualifier("auditDataSource") DataSource ds) {
        return new JdbcTransactionManager(ds);
    }
}
```

Các import của đoạn trên:

```java
import javax.sql.DataSource;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
```

`JdbcTransactionManager` là một transaction manager JDBC cho một `DataSource`. `DataSourceTransactionManager` cũng là lựa chọn phổ biến; `JdbcTransactionManager` bổ sung khả năng chuyển dịch một số ngoại lệ commit/rollback theo mô hình Spring JDBC.

Một method service chọn manager bằng `@Transactional`:

```java
@Transactional(transactionManager = "ordersTransactionManager")
public void markOrderPaid(long orderId) {
    ordersRepository.updateStatus(orderId, "PAID");
}
```

Phương thức trên chỉ là **minh họa**, giả định `ordersRepository` hợp lệ và code nằm trong Spring-managed service. Cơ chế giao dịch mặc định dựa trên proxy nên lời gọi từ bên ngoài qua Spring bean proxy mới được chặn để áp dụng transaction; self-invocation (`this.markOrderPaid(...)`) thường bỏ qua advice.

Những điều cần nắm:

1. Manager orders phải dùng **chính DataSource** mà `ordersJdbc` đang sử dụng; manager audit phải khớp với `auditJdbc`.
2. Một manager JDBC local chỉ quản lý giao dịch của nguồn tương ứng, không tự bao trùm connection khác.
3. Khi có nhiều transaction manager, sử dụng `@Transactional(transactionManager = "...")` ở nghiệp vụ cần chọn rõ nguồn thay vì đoán nguồn mặc định.
4. `@Transactional(readOnly = true)` không tự chọn replica hoặc tự chuyển một template từ orders sang audit. Đây là thuộc tính transaction; muốn routing đọc/ghi phải có cấu hình routing và kiểm tra replica lag.
5. Dùng `JdbcTemplate`/`DataSourceUtils` đúng cách để tham gia Spring-managed transaction. Tự lấy connection bằng `dataSource.getConnection()` mà không theo cơ chế đồng bộ của Spring có thể không tham gia transaction như dự kiến.

### 7.1. Ghi cả hai database không phải một transaction chung

Giả sử service ghi trạng thái đơn hàng vào orders database rồi thêm một sự kiện ở audit database. Orders có thể commit trong khi audit thất bại nếu hai nguồn dùng các local transaction độc lập. Việc tạo hai bean `PlatformTransactionManager`, đặt `@Transactional` hoặc khai báo nguồn primary **không tự tạo atomic commit cho hai database**.

Nếu nghiệp vụ cần nhất quán liên nguồn, phải chọn một chiến lược khác tùy yêu cầu: transactional outbox và xử lý sự kiện có retry/idempotency, saga/compensation, đối soát bất đồng bộ, hoặc transaction phân tán XA/JTA khi hạ tầng và trade-off phù hợp. Đây là bài toán thiết kế transaction và độ tin cậy, không chỉ là lỗi lựa chọn bean.

### 7.2. Không nhầm transaction manager của JDBC với JPA

Ở ví dụ JDBC, `JdbcTransactionManager` quản lý `DataSource`. Với **JPA**, thông thường mỗi `EntityManagerFactory` cần `JpaTransactionManager` phù hợp. Dùng một manager JDBC và kỳ vọng nó bao trùm mọi persistence context JPA hoặc dùng một JPA manager cho hai entity manager factory là giả định không đúng.

```text
Spring JDBC:  DataSource -> JdbcTemplate -> Repository
                   ^
                   |
             JDBC TransactionManager

Spring JPA:   DataSource -> EntityManagerFactory -> JPA Repository
                               ^
                               |
                          JpaTransactionManager
```

Transaction manager là thành phần cần gắn đúng trong sơ đồ, không chỉ là annotation đặt trên service.

## 8. Với Spring Data JPA, qualifier trên DataSource chưa đủ

Một hệ thống có hai nhóm JPA repository cần cấu hình riêng:

- `DataSource` cho mỗi nhóm.
- `EntityManagerFactory` gắn với nguồn tương ứng, có entity packages và cấu hình persistence thích hợp.
- `JpaTransactionManager` cho từng factory.
- `@EnableJpaRepositories` với `basePackages`, `entityManagerFactoryRef` và `transactionManagerRef` khớp nhau.

Ví dụ **đoạn annotation minh họa** cho vùng orders, không phải class đầy đủ:

```java
@EnableJpaRepositories(
    basePackages = "example.orders.repository",
    entityManagerFactoryRef = "ordersEntityManagerFactory",
    transactionManagerRef = "ordersTransactionManager")
```

Một cấu hình tương tự cần áp dụng cho audit, trỏ đến `auditEntityManagerFactory` và `auditTransactionManager`. Đừng để hai cấu hình scan đè cùng repository package hoặc mặc định dùng sai persistence unit. Việc đặt `@Primary` trên `DataSource` không bảo đảm repository JPA tự nối đúng.

Schema migration (Flyway/Liquibase hoặc quy trình tương đương) cũng cần chỉ đến đúng database; tránh cấu hình khiến migration của orders chạy trên audit.

## 9. Spring Boot auto-configuration cần được xác minh

Spring Boot có auto-configuration cho `DataSource`, pool, `JdbcTemplate` và JPA, nhưng **không tự hiểu mọi prefix cấu hình tự đặt** như `app.datasource.orders.*` và `app.datasource.audit.*`. Khi thêm nguồn thứ hai, nên trả lời ba câu hỏi:

1. **Boot tạo bean nào?** Khi ứng dụng tự khai báo `DataSource`, điều kiện auto-configuration có thể thay đổi tùy phiên bản. Đọc tài liệu đúng phiên bản, không mặc định Boot vẫn tạo source mặc định còn thiếu.
2. **Đâu là default?** Một số cấu hình tự động cần một nguồn mặc định, thường được phân biệt bằng `@Primary`. Trong các phiên bản Boot mới, cơ chế bean `defaultCandidate` cũng có thể ảnh hưởng tương tác với auto-configuration. Phần code dùng trực tiếp Spring Framework ở chương 4 không phụ thuộc hành vi Boot đó.
3. **Ai tạo những bean phía trên?** Việc có hai `DataSource` không đảm bảo Boot tự tạo đủ hai `JdbcTemplate`, hai transaction manager và hai `EntityManagerFactory`. Cần kiểm tra cấu hình từng tầng.

Kiểm tra danh sách bean hiện có từ `ApplicationContext` hoặc công cụ quan sát của Boot nếu được bật, cùng binding property, connection URL và integration test dùng từng repository. Không kết luận chỉ từ việc file `application.yml` chứa hai endpoint.

## 10. Kiểm thử để phát hiện đi sai nguồn

### 10.1. Integration test với dữ liệu phân biệt được

Tạo hai database hoặc schemas test độc lập; seed dữ liệu đặc trưng:

- Orders chứa `order id=10`, `status=PAID`.
- Audit chứa sự kiện `id=10`, `event_name=order-created`.
- Đọc qua đúng repository và đối chiếu kết quả.
- Khi hai database có bảng cùng tên, cố ý seed dữ liệu **khác nhau** để việc đọc nhầm vẫn bị phát hiện.
- Với thao tác ghi, xác minh bản ghi xuất hiện ở nguồn đúng và không xuất hiện ở nguồn sai.

Ví dụ chương 4 cho thấy hai database H2 riêng. Với sản phẩm chạy trên PostgreSQL/MySQL, nên có integration test với DBMS tương ứng hoặc database container để phát hiện khác biệt schema, driver và transaction.

### 10.2. Kiểm tra bean được gắn chính xác

Trong ứng dụng sử dụng `JdbcTemplate` trực tiếp như ví dụ, có thể dùng `JdbcTemplate#getDataSource()` để đối chiếu với bean mong đợi. Mẫu **đoạn test**, không phải một lớp JUnit hoàn chỉnh:

```java
assertSame(
    context.getBean("ordersDataSource", DataSource.class),
    context.getBean("ordersJdbc", JdbcTemplate.class).getDataSource()
);

assertSame(
    context.getBean("auditDataSource", DataSource.class),
    context.getBean("auditJdbc", JdbcTemplate.class).getDataSource()
);
```

`assertSame` đến từ `org.junit.jupiter.api.Assertions`; đoạn trích giả định biến `context` và các bean của chương 4. Với proxy/wrapper hoặc routing datasource, so sánh identity không luôn đủ; cần xác minh thêm connection URL, schema/catalog và dữ liệu thực.

### 10.3. Thử các trường hợp lỗi

- Tạm bỏ qualifier trong test khi có hai ứng viên và không có default: xác nhận container thất bại rõ thay vì chọn ngẫu nhiên.
- Hoán đổi qualifier của `ordersJdbc`/`auditJdbc` trong môi trường thử nghiệm: integration test phải phát hiện bằng bảng hoặc nội dung sai.
- Thử rollback một transaction orders, kiểm tra chỉ dữ liệu orders đã nằm trong phạm vi transaction đó được hoàn tác.
- Mô phỏng nguồn audit mất kết nối, đánh giá nghiệp vụ có retry/outbox hoặc xử lý trạng thái không nhất quán như thiết kế.
- Dùng tài khoản DB có quyền tối thiểu riêng, để kết nối nhầm khó ghi sai bảng hơn.
- Kiểm tra mỗi profile local/test/staging/production đã bind URL/secret đúng, không dựa vào việc tên bean trông hợp lý.

Không nên log passwords, URL kèm secret hoặc dữ liệu nhạy cảm để “debug nhanh”.

## 11. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| `NoUniqueBeanDefinitionException` cho `DataSource` | Có hai bean cùng kiểu mà injection point chưa chọn. | Đặt qualifier hoặc xác định một primary có ý nghĩa nghiệp vụ. |
| Không lỗi DI nhưng truy vấn đi sai database | Sai qualifier, primary hoặc tên bean ở một tầng. | So sánh đầy đủ chuỗi DataSource → template/factory → repository và URL/schema thực. |
| `NoUniqueBeanDefinitionException` cho `JdbcTemplate` | Đã tách datasource nhưng hai template chưa được phân biệt khi tiêm. | Qualify `ordersJdbc` và `auditJdbc` ở repository. |
| `@Repository` vẫn dùng nhầm nguồn | Annotation stereotype không chọn DataSource. | Qualify template/EntityManagerFactory, kiểm tra repository scanning. |
| `@Transactional` không rollback như mong muốn | Sai transaction manager hoặc gọi bỏ qua proxy. | Kiểm tra manager gắn cùng source và lời gọi qua bean Spring. |
| Orders commit nhưng audit thất bại | Hai local transactions không tạo atomic commit chung. | Chọn mô hình nhất quán liên nguồn và test failure/retry. |
| Dùng `@Primary` rồi thấy mọi truy vấn đi orders | Default che khuất nhu cầu chọn nguồn của audit. | Đặt qualifier rõ ở các consumer audit, tránh default tùy tiện. |
| Local đúng nhưng production sai | Khác profile, property prefix, secret, pool hoặc schema. | Kiểm tra bean/properties thực tế từng môi trường. |
| Spring Data JPA query nhầm persistence unit | Scan repository hoặc ref EntityManagerFactory/manager sai. | Chia package và cấu hình `entityManagerFactoryRef`/`transactionManagerRef`. |
| `readOnly=true` không tự dùng replica | Nhầm transaction read-only với cơ chế routing. | Thiết kế routing/replica riêng, đo độ trễ replication. |

## 12. Checklist khi thêm nguồn mới

1. Đặt tên và mô tả nhiệm vụ của mỗi `DataSource`; ghi nhận URL, schema, driver, credentials, quyền và pool.
2. Cấu hình source thực tế phù hợp Spring Framework hoặc phiên bản Spring Boot của dự án.
3. Xác định template hoặc EntityManagerFactory tương ứng; dùng `@Qualifier` tại mỗi điểm tiêm có nhiều ứng viên.
4. Giữ repository gắn với nguồn rõ ràng; chỉ đưa repository cần thiết cho service.
5. Cấu hình transaction manager khớp nguồn; không coi hai local managers là một transaction phân tán.
6. Test từng đường đọc/ghi và rollback bằng dữ liệu khác biệt giữa hai nguồn.
7. Theo dõi health, pool metrics, query timeout, migration và permission riêng; đưa các lỗi sai nguồn vào kiểm tra trước khi triển khai.

## 13. Câu hỏi tự kiểm tra

1. Vì sao Spring không thể tự suy ra `OrderRepository` cần `ordersDataSource` chỉ từ interface `DataSource`?
2. `@Qualifier("auditJdbc")` trên constructor khác gì với `@Primary` trên `ordersDataSource`?
3. Nếu đã tạo hai `DataSource` rõ ràng, tại sao vẫn cần phân biệt hai `JdbcTemplate`?
4. Trong chương trình H2, bean nào quyết định lệnh `orders.save(...)` đi vào `orders_db`?
5. Vì sao `ordersTransactionManager` không tự rollback một lệnh chạy bởi `auditJdbc`?
6. Với JPA hai nguồn, cần cấu hình thêm những thành phần gì?
7. Test nào phát hiện lỗi chọn sai nguồn khi cả hai database có bảng cùng tên?

**Ghi nhớ:** `@Qualifier` làm rõ **DataSource hoặc template được tiêm** tại từng phụ thuộc; `@Primary` chỉ là lựa chọn mặc định khi thật sự có một nguồn chính. Sau khi lựa chọn chính xác JDBC/JPA repository, phải chọn **transaction manager** phù hợp và kiểm chứng bằng integration test trên hai nguồn độc lập.

### Tham khảo chính thức

- [Spring Framework — Using @Autowired](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired.html).
- [Spring Framework — Using @Qualifier](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-qualifiers.html).
- [Spring Framework — Fine-tuning with @Primary](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/autowired-primary.html).
- [Spring Framework — Using @Transactional và Multiple Transaction Managers](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html).
- [Spring Boot — Data Access / Configure Two DataSources](https://docs.spring.io/spring-boot/how-to/data-access.html); chọn đúng phiên bản Boot mà dự án sử dụng.
