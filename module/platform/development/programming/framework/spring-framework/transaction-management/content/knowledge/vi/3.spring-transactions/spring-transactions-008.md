# Chọn Transaction Manager theo loại tài nguyên, không theo tên `@Transactional`

> **Spring Framework — Transaction Management → Mô hình Spring.** Bài học trả lời câu hỏi: khi một ứng dụng dùng JDBC, JPA, R2DBC, MongoDB, Kafka hoặc nhiều nguồn dữ liệu, phải chọn `TransactionManager` nào, và vì sao tên annotation `@Transactional` không nói lên tài nguyên thực sự được commit/rollback?

## 1. Nguyên tắc cốt lõi

**Chọn transaction manager theo tài nguyên cần tham gia giao dịch và cơ chế truy cập tài nguyên đó.** Tên `@Transactional` chỉ cung cấp metadata về ranh giới giao dịch; nó không tự biến mọi truy cập dữ liệu trong phương thức thành một giao dịch thống nhất.

Ba lớp cần phân biệt:

1. **Annotation và transaction attributes:** `@Transactional` mô tả propagation, isolation, read-only, timeout, rollback rules và có thể nêu rõ tên/qualifier của manager.
2. **Transaction infrastructure:** Spring AOP `TransactionInterceptor` đọc metadata, xác định manager phù hợp và yêu cầu manager bắt đầu/tham gia, commit hoặc rollback giao dịch.
3. **Resource binding:** manager quản lý tài nguyên thực sự — JDBC `Connection` từ một `DataSource`, JPA `EntityManager` từ một `EntityManagerFactory`, R2DBC `Connection` từ một `ConnectionFactory`, MongoDB `ClientSession` hoặc transaction toàn cục do JTA coordinator điều phối.

Luồng tổng quát:

```text
Lời gọi đi qua Spring proxy
          |
          v
@Transactional (metadata: propagation/rollback/transactionManager)
          |
          v
TransactionInterceptor
          |
          +--> chọn TransactionManager bean được cấu hình/qualify
                     |
                     +--> quản lý tài nguyên phù hợp
                     |      JDBC DataSource + Connection
                     |      JPA EntityManagerFactory + EntityManager
                     |      R2DBC ConnectionFactory + Connection
                     |      MongoDatabaseFactory + ClientSession
                     |      JTA coordinator + enlisted resources
                     |
                     +--> gọi nghiệp vụ
                     |
                     +--> commit hoặc rollback
```

**Cùng một `@Transactional`, nhưng cách quản lý transaction thay đổi theo manager.** Ví dụ, `@Transactional` trên service JPA và trên service JDBC có thể trông giống hệt nhau; nếu service JPA sử dụng manager JDBC không tích hợp `EntityManager` của nó thì không thể mặc nhiên kỳ vọng persist/flush/rollback JPA hoạt động đúng.

Ngược lại, thay tên bean từ `ordersTxManager` thành `jpaTxManager` **không** biến một `JdbcTransactionManager` thành `JpaTransactionManager`. Tên chỉ là định danh để tham chiếu bean; hành vi được quyết định bởi **kiểu triển khai manager + đối tượng tài nguyên mà bean đó nhận khi cấu hình**.

## 2. Phân biệt các abstraction trong Spring

- `org.springframework.transaction.TransactionManager`: interface chung.
- `PlatformTransactionManager`: manager cho **imperative transaction**; cung cấp `getTransaction(...)`, `commit(...)` và `rollback(...)`. Thường gắn trạng thái transaction/tài nguyên với thread.
- `ReactiveTransactionManager`: manager cho **reactive transaction**; sử dụng luồng reactive và Reactor `Context`, không dùng mô hình thread-bound của JDBC.
- `@Transactional`: annotation mô tả transaction attributes; **không phải** một manager.
- `TransactionTemplate`: cách lập trình để sử dụng một `PlatformTransactionManager` cụ thể.
- `TransactionalOperator`: cách lập trình để sử dụng một `ReactiveTransactionManager` cụ thể.

Một manager có thể dùng cùng API declarative `@Transactional` nhưng không nhất thiết hỗ trợ mọi thuộc tính giống nhau. Khả năng `NESTED`/savepoint, isolation, timeout và `readOnly` phụ thuộc vào manager, driver và datastore. `readOnly=true` thường là hint/optimization, **không phải cơ chế bảo mật mặc định** ngăn mọi lệnh ghi trên mọi hệ quản trị.

## 3. Bảng chọn manager theo tài nguyên và cơ chế truy cập

| Tài nguyên và cách truy cập | Manager thường phù hợp | Tài nguyên mà manager điều phối | Điều kiện cần nhớ |
| --- | --- | --- | --- |
| JDBC, `JdbcTemplate` hoặc SQL qua `DataSource` | `JdbcTransactionManager` hoặc `DataSourceTransactionManager` | JDBC `Connection` của **đúng `DataSource`** | DAO phải dùng connection có nhận biết transaction; `JdbcTemplate`/`DataSourceUtils` làm việc này |
| JPA, `EntityManager`, Spring Data JPA repository | `JpaTransactionManager` | JPA `EntityManager` của **đúng `EntityManagerFactory`** | Repository/`EntityManager` phải gắn với factory do manager điều phối |
| JDBC **cùng một datasource bên dưới JPA** | Có thể dùng `JpaTransactionManager` cho cả JPA và JDBC | `EntityManager`; có thể chia sẻ JDBC connection | Cần cùng `DataSource` và hỗ trợ từ `JpaDialect`; không suy ra từ URL database giống nhau |
| Nhiều tài nguyên có yêu cầu commit nguyên tử toàn cục | `JtaTransactionManager` + transaction coordinator | Các XA resource tham gia transaction JTA | Phải cấu hình driver, pool, provider và coordinator cho XA/JTA; không xảy ra chỉ vì có annotation |
| R2DBC qua `DatabaseClient` / reactive repository | `R2dbcTransactionManager` | R2DBC `Connection` của **đúng `ConnectionFactory`** trong Reactor `Context` | Dùng reactive pipeline; không thay được manager JDBC |
| MongoDB imperative (`MongoTemplate`) | `MongoTransactionManager` (Spring Data MongoDB) | MongoDB `ClientSession` trên đúng `MongoDatabaseFactory` | Mongo deployment phải hỗ trợ transaction, cần cấu hình manager |
| MongoDB reactive (`ReactiveMongoTemplate`) | `ReactiveMongoTransactionManager` (Spring Data MongoDB) | MongoDB `ClientSession` trong reactive context | Không dùng bản imperative cho reactive operations |
| Kafka producer có giao dịch | `KafkaTransactionManager` (Spring Kafka) | Transaction của Kafka producer | Không đảm bảo commit nguyên tử cùng một database khác theo kiểu JDBC local transaction |

Bảng là **bản đồ lựa chọn theo tài nguyên**, không phải luật cứng “mỗi công nghệ chỉ có duy nhất một manager”. Chẳng hạn JTA có thể điều phối JPA/JDBC nếu các tài nguyên đã được tích hợp JTA đúng cách; `JpaTransactionManager` cũng có thể phục vụ truy cập JDBC trên datasource tương ứng. Mỗi khả năng phụ thuộc cấu hình thực tế.

### JDBC: `JdbcTransactionManager` và `DataSourceTransactionManager`

Cả hai phục vụ local transaction trên **một JDBC `DataSource`**:

- `DataSourceTransactionManager` quản lý JDBC connection, commit, rollback, isolation, timeout và savepoint khi được hỗ trợ.
- `JdbcTransactionManager` là biến thể kế thừa `DataSourceTransactionManager`, bổ sung việc chuyển đổi lỗi commit/rollback thành các `DataAccessException` phù hợp hơn với `JdbcTemplate`.
- Trường hợp JDBC thuần thông thường, `JdbcTransactionManager` là lựa chọn tiện lợi; `DataSourceTransactionManager` vẫn đúng khi ứng dụng sử dụng hợp đồng/lỗi phù hợp với nó.

Dù chọn biến thể nào, manager phải nhận **đúng bean `DataSource`** mà `JdbcTemplate`/DAO sử dụng. Có hai datasource A và B thì manager gắn A không tự động tạo transaction cho kết nối lấy từ B.

### JPA: vì sao nên chọn `JpaTransactionManager`?

`JpaTransactionManager` quản lý `EntityManager` gắn với `EntityManagerFactory` cụ thể, giúp persistence context, flush và database transaction có ranh giới thống nhất. Spring Data JPA repository và `@PersistenceContext` cần dùng đúng factory/manager.

Nếu một service thực hiện cả JPA lẫn `JdbcTemplate` **trên cùng database, cùng underlying datasource**, `JpaTransactionManager` có thể cho JDBC tham gia **cùng transaction** khi `JpaDialect`/connection access được cấu hình tương thích. Đây là ngoại lệ quan trọng đối với cách nhớ máy móc “cứ nhìn thấy JDBC thì luôn phải chọn JDBC manager”.

Không tự khởi tạo thêm `JdbcTransactionManager` cho cùng datasource và tùy ý chuyển manager giữa các method nếu mục tiêu là **một** transaction chung cho JPA và JDBC. Hai manager độc lập không tự đồng bộ persistence context của JPA với JDBC transaction do manager kia mở.

### R2DBC: hai chữ “SQL” chưa đủ để chọn manager

JDBC là API chặn luồng và dùng `javax.sql.DataSource`; R2DBC là API reactive và dùng `io.r2dbc.spi.ConnectionFactory`. Chúng có kiểu kết nối và cơ chế gắn transaction khác nhau.

- `JdbcTransactionManager` là một `PlatformTransactionManager`, thường gắn connection theo thread.
- `R2dbcTransactionManager` là một `ReactiveTransactionManager`, gắn connection vào subscriber `Context`.
- `@Transactional` trên phương thức có reactive return type (`Mono`/`Flux`/`Publisher`) được xử lý theo đường reactive; phương thức trả `void`, đối tượng Java thông thường phải gắn với manager imperative phù hợp.

**Không thể bọc JDBC trong `Mono` rồi kỳ vọng tự động có transaction R2DBC**; cũng không thể lấy connection R2DBC và điều phối bằng manager JDBC.

### JTA: chọn khi yêu cầu thật sự là phối hợp tài nguyên

`JtaTransactionManager` đóng vai trò adapter vào JTA coordinator. Muốn database A và database B cùng được commit/rollback nguyên tử theo giao thức XA, cần tài nguyên XA, coordinator và cấu hình enlistment tương thích. Chỉ thêm `@Transactional` hoặc đặt tên bean `globalTransactionManager` **không tạo ra distributed transaction**.

Khi nhiều hệ thống không hỗ trợ cùng một coordinator (ví dụ database và HTTP API), hãy đánh giá transactional outbox, saga và cơ chế bù trừ/idempotency; không giả định một annotation bảo đảm atomicity xuyên hệ thống.

## 4. Cách chọn manager: đi từ công việc thực tế đến bean

Hãy trả lời theo thứ tự:

1. **Dữ liệu nào cần rollback cùng nhau?** Một bảng, nhiều bảng cùng database, hai database độc lập hay database + message broker?
2. **Code sử dụng API truy cập nào?** `JdbcTemplate`, JPA repository/`EntityManager`, `DatabaseClient` R2DBC, Mongo template, Kafka template?
3. **API đó lấy tài nguyên từ factory nào?** `DataSource`, `EntityManagerFactory`, `ConnectionFactory`, `MongoDatabaseFactory`, Kafka `ProducerFactory`?
4. **Manager nào thực sự điều phối factory đó?** Kiểm tra constructor/setter/config bean; không phỏng đoán từ tên.
5. **Toàn bộ operations cần rollback có tham gia manager đã chọn không?** Với một local manager, tài nguyên ở ngoài phạm vi của nó không tự động tham gia.
6. **Đây là imperative hay reactive flow?** Kiểm tra kiểu trả về và cách tài nguyên được gắn với thread hoặc Reactor `Context`.
7. **Có hơn một manager trong ApplicationContext không?** Chỉ rõ mặc định hoặc qualifier để Spring chọn đúng; tránh dựa vào lựa chọn tình cờ.

Cây quyết định rút gọn:

```text
Cần một đơn vị giao dịch
          |
          +-- R2DBC/reactive SQL? ----------> R2dbcTransactionManager
          |
          +-- Mongo imperative/reactive? --> MongoTransactionManager /
          |                                 ReactiveMongoTransactionManager
          |
          +-- JPA/EntityManager? ----------> JpaTransactionManager
          |                                   (có thể phối hợp JDBC cùng datasource)
          |
          +-- JDBC-only? ------------------> JdbcTransactionManager
          |                                   hoặc DataSourceTransactionManager
          |
          +-- Nhiều XA resources cần
          |   atomic commit toàn cục? ----> JtaTransactionManager + XA/JTA
          |
          +-- Kafka producer transaction? -> KafkaTransactionManager
                                            (phạm vi transaction Kafka)
```

**Nếu một service chạm nhiều công nghệ, câu hỏi quan trọng nhất không phải “chọn tên nào nghe hợp lý”, mà là chúng có thể tham gia cùng một cơ chế transaction hay không.**

## 5. Cơ chế chọn manager của `@Transactional`

`@Transactional` không xem vào thân hàm để thấy “method này gọi `JpaRepository` nên tự tìm `JpaTransactionManager`”. Nó hoạt động từ metadata và các bean đã cấu hình.

Trong ứng dụng một manager, thường không cần chỉ rõ:

```java
import org.springframework.transaction.annotation.Transactional;

@Transactional
public void createOrder() {
    // Spring dùng default transaction manager đã cấu hình.
}
```

Đoạn này chỉ minh họa cú pháp trong một Spring bean; không phải chương trình chạy độc lập.

Khi có nhiều manager, nên chỉ rõ định danh tương ứng:

```java
@Transactional(transactionManager = "ordersTxManager")
public void createOrder() {
    // Các thao tác phải tham gia đúng resources của ordersTxManager.
}

@Transactional("billingTxManager") // Alias của transactionManager = "billingTxManager"
public void createInvoice() {
    // Các thao tác phải tham gia resources của billingTxManager.
}
```

Hai dạng trên **đều dùng chính annotation `org.springframework.transaction.annotation.Transactional`**. Giá trị chuỗi là tên bean hoặc qualifier, **không phải tên công nghệ giao dịch**. Tên `ordersTxManager` có thể trỏ đến `JdbcTransactionManager`, `JpaTransactionManager` hoặc một loại khác; phải kiểm tra bean thực tế.

Một ví dụ wiring:

```java
// Đoạn cấu hình minh họa, giả định các datasource đã tồn tại.
@Bean("ordersTxManager")
PlatformTransactionManager ordersTxManager(
        @Qualifier("ordersDataSource") DataSource dataSource) {
    return new JdbcTransactionManager(dataSource);
}
```

Trong ứng dụng có nhiều `TransactionManager`, `@Transactional` không chỉ rõ manager có thể gây lỗi không xác định được default hoặc chọn default ngoài ý định, tùy cấu hình. Sử dụng tên/qualifier rõ ràng là cách dễ kiểm chứng nhất. Có thể cấu hình `@Primary` hoặc `TransactionManagementConfigurer` để đặt default khi hợp lý; điều đó **không thay thế** việc chọn manager riêng cho tài nguyên khác.

Ngoài ra, trong Spring Framework 6.2+, `@Qualifier` ở mức class có thể ảnh hưởng lựa chọn manager cho các `@Transactional` không nêu qualifier; đây là lựa chọn cấu hình bổ sung, vẫn cần bảo đảm resource binding đúng.

**`jakarta.transaction.Transactional` là annotation chuẩn Jakarta Transactions.** Spring hỗ trợ annotation này như một nguồn metadata declarative trong cấu hình phù hợp, nhưng việc import annotation Jakarta **không ép Spring phải sử dụng JTA**. Cơ chế quản lý giao dịch vẫn do manager được cấu hình quyết định. Khi cần những thuộc tính Spring-specific như `transactionManager`, `propagation` và `rollbackFor`, dùng `org.springframework.transaction.annotation.Transactional`.

## 6. Ví dụ Java 17+ chạy được: hai database, hai manager, hai kết quả commit khác nhau

Ví dụ này chứng minh ba điều:

- Cả hai method đều dùng cùng loại annotation `@Transactional`.
- Method xử lý order chọn `ordersTxManager` gắn với database `ordersDb`; method ghi audit chọn `auditTxManager` gắn với database `auditDb`.
- Khi method order thất bại, order được rollback; audit đã commit bằng **một local transaction độc lập**, nên vẫn tồn tại. Điều này không phải lỗi Spring: đó là phạm vi giao dịch được cấu hình.

Dùng Spring Framework **6.2.8**, H2 **2.3.232**, Maven và Java 17+. Ví dụ chạy độc lập, không cần Spring Boot hay database server.

### 6.1. Cấu trúc dự án

```text
tx-manager-resource-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/
                └── learning/
                    └── TxManagerResourceDemo.java
```

Tạo `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.learning</groupId>
    <artifactId>tx-manager-resource-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
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
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>dev.learning.TxManagerResourceDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 6.2. Tạo `src/main/java/dev/learning/TxManagerResourceDemo.java`

```java
package dev.learning;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;

public class TxManagerResourceDemo {

    @Configuration
    @EnableTransactionManagement
    public static class AppConfig {

        private static DataSource h2(String databaseName) {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:" + databaseName + ";DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean("ordersDataSource")
        public DataSource ordersDataSource() {
            return h2("ordersDb");
        }

        @Bean("auditDataSource")
        public DataSource auditDataSource() {
            return h2("auditDb");
        }

        @Bean("ordersJdbc")
        public JdbcTemplate ordersJdbc(
                @Qualifier("ordersDataSource") DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean("auditJdbc")
        public JdbcTemplate auditJdbc(
                @Qualifier("auditDataSource") DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean("ordersTxManager")
        public PlatformTransactionManager ordersTxManager(
                @Qualifier("ordersDataSource") DataSource ds) {
            return new JdbcTransactionManager(ds);
        }

        @Bean("auditTxManager")
        public PlatformTransactionManager auditTxManager(
                @Qualifier("auditDataSource") DataSource ds) {
            return new JdbcTransactionManager(ds);
        }

        @Bean
        public AuditService auditService(
                @Qualifier("auditJdbc") JdbcTemplate jdbc) {
            return new AuditService(jdbc);
        }

        @Bean
        public OrderService orderService(
                @Qualifier("ordersJdbc") JdbcTemplate jdbc,
                AuditService auditService) {
            return new OrderService(jdbc, auditService);
        }
    }

    public static class AuditService {
        private final JdbcTemplate jdbc;

        public AuditService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(transactionManager = "auditTxManager")
        public void record(long id) {
            jdbc.update(
                    "INSERT INTO audit_events (id, message) VALUES (?, ?)",
                    id, "order attempted");
        }
    }

    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final AuditService auditService;

        public OrderService(JdbcTemplate jdbc, AuditService auditService) {
            this.jdbc = jdbc;
            this.auditService = auditService;
        }

        @Transactional(transactionManager = "ordersTxManager")
        public void createThenFail() {
            jdbc.update(
                    "INSERT INTO order_records (id, description) "
                            + "VALUES (?, ?)",
                    1L, "sample order");

            // Lời gọi qua một Spring bean khác -> đi qua audit proxy.
            // Audit có manager và datasource riêng.
            auditService.record(1L);

            throw new IllegalStateException("simulated");
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             AppConfig.class)) {

            JdbcTemplate orders =
                    context.getBean("ordersJdbc", JdbcTemplate.class);
            JdbcTemplate audit =
                    context.getBean("auditJdbc", JdbcTemplate.class);

            // DDL chỉ khởi tạo schema, nằm ngoài thử nghiệm rollback.
            orders.execute(
                    "CREATE TABLE order_records "
                            + "(id BIGINT PRIMARY KEY, "
                            + "description VARCHAR(80))");
            audit.execute(
                    "CREATE TABLE audit_events "
                            + "(id BIGINT PRIMARY KEY, "
                            + "message VARCHAR(80))");

            try {
                // Lấy bean đã được Spring proxy, không tự new OrderService.
                context.getBean(OrderService.class).createThenFail();
            } catch (IllegalStateException expected) {
                System.out.println(
                        "Exception: " + expected.getMessage());
            }

            Integer orderCount = orders.queryForObject(
                    "SELECT COUNT(*) FROM order_records", Integer.class);
            Integer auditCount = audit.queryForObject(
                    "SELECT COUNT(*) FROM audit_events", Integer.class);

            System.out.println("order_records=" + orderCount);
            System.out.println("audit_events=" + auditCount);
        }
    }
}
```

### 6.3. Biên dịch và chạy

Tại thư mục `tx-manager-resource-demo`, cần JDK 17+ và Maven; lần chạy đầu cần Internet để tải dependencies:

```bash
mvn -q clean compile exec:java
```

Các dòng kết quả do chương trình in ra (không tính thông báo của Maven hoặc thư viện logging nếu môi trường bật log):

```text
Exception: simulated
order_records=0
audit_events=1
```

**Giải thích:**

1. `AppConfig` tạo hai `DataSource` khác nhau: `ordersDataSource` đi đến `jdbc:h2:mem:ordersDb`, `auditDataSource` đi đến `jdbc:h2:mem:auditDb`.
2. Mỗi `JdbcTransactionManager` được tạo với **đúng datasource riêng của nó**. Hai `JdbcTemplate` cũng được cấu hình khớp với hai datasource đó.
3. Spring intercept `OrderService.createThenFail()` và mở transaction orders. Dòng order mới chưa commit.
4. `OrderService` gọi bean proxy `AuditService`. Spring chọn `auditTxManager` và transaction audit riêng; `record()` kết thúc bình thường nên audit commit.
5. `createThenFail()` ném `IllegalStateException`. Spring rollback transaction orders vì đây là unchecked exception. Kết quả: không có order mới nhưng có audit event.

**Điều chứng minh:** hai manager quản lý hai database riêng, không có một atomic transaction bao cả hai. Không có ý nghĩa “một `@Transactional` tự rollback mọi nguồn dữ liệu”. Ví dụ cố ý để audit commit nhằm làm rõ ranh giới; thiết kế nghiệp vụ thực tế cần quyết định liệu audit độc lập như vậy có đúng yêu cầu hay không.

### 6.4. Muốn rollback cả hai bảng cùng một database thì sao?

Nếu `order_records` và `audit_events` nằm trên **cùng datasource**, hãy cho cả hai DAO sử dụng datasource/connection được cùng manager quản lý, đặt transaction boundary ở service gọi hai thao tác. Khi cả hai operations thực sự tham gia cùng một JDBC transaction, exception sẽ rollback cả hai.

Nếu dữ liệu nằm ở **hai database độc lập**, đổi tên `@Transactional`, trỏ hai manager đến nhau hoặc thêm `@Primary` **không** cung cấp atomicity. Cần cơ chế phối hợp như JTA/XA khi khả thi hoặc một thiết kế nhất quán cuối cùng (outbox/saga) theo yêu cầu nghiệp vụ.

## 7. Cấu hình cho JPA, JDBC và R2DBC trong các tình huống thường gặp

### 7.1. Một JPA persistence unit

Khi repository dùng một `EntityManagerFactory`, dùng `JpaTransactionManager` cho persistence unit đó:

```java
// Trong class @Configuration của ứng dụng có EntityManagerFactory bean.
@Bean("ordersJpaTx")
PlatformTransactionManager ordersJpaTx(
        @Qualifier("ordersEntityManagerFactory")
        jakarta.persistence.EntityManagerFactory emf) {
    return new org.springframework.orm.jpa.JpaTransactionManager(emf);
}
```

Đoạn code trên là **fragment cấu hình**, cần `ordersEntityManagerFactory` đã được khai báo và Spring ORM/JPA dependencies. Service sử dụng:

```java
@Transactional(transactionManager = "ordersJpaTx")
public void persistOrder() {
    // Gọi JPA repository / EntityManager thuộc ordersEntityManagerFactory.
}
```

Nếu dùng Spring Data JPA với nhiều `EntityManagerFactory`, định tuyến repository về factory và manager phù hợp thông qua `@EnableJpaRepositories`:

```java
@EnableJpaRepositories(
    basePackages = "dev.learning.orders.repository",
    entityManagerFactoryRef = "ordersEntityManagerFactory",
    transactionManagerRef = "ordersJpaTx"
)
```

Đây là fragment annotation, không phải class Java độc lập. `entityManagerFactoryRef` định tuyến factory, còn `transactionManagerRef` định tuyến transaction manager; thiếu một trong hai khi có nhiều persistence units có thể khiến repository dùng cấu hình không mong muốn. Đừng quên rằng cấu hình tên bean, default manager ở service và transaction manager của Spring Data repository là các điểm cần kiểm tra riêng.

### 7.2. Một datasource dùng cả JPA và `JdbcTemplate`

Khi JPA và JDBC cần nằm **trong một transaction**, phương án thường dùng là `JpaTransactionManager` điều phối `EntityManagerFactory` và cho `JdbcTemplate` trên datasource tương ứng cùng tham gia. Điều kiện là:

- `EntityManagerFactory` gắn với datasource đó; `JpaTransactionManager` biết datasource tương ứng.
- `JpaDialect` hỗ trợ lấy JDBC connection bên dưới cho phép tham gia transaction.
- JDBC access dùng `JdbcTemplate`/`DataSourceUtils` để lấy connection nhận biết transaction.
- Thứ tự thao tác/flush của JPA được cân nhắc khi JDBC đọc dữ liệu vừa thay đổi trong persistence context: khi cần, `EntityManager.flush()` có thể phải chạy trước câu truy vấn JDBC.

Nếu một trong các điều kiện không thỏa mãn, đừng khẳng định mọi code chạm cùng URL database sẽ tự chia sẻ một physical transaction.

### 7.3. Một reactive SQL pipeline

Đối với R2DBC, manager nên gắn với `ConnectionFactory` mà `DatabaseClient` hoặc repository R2DBC dùng:

```java
// Fragment cấu hình khi đã có R2DBC ConnectionFactory.
@Bean("r2dbcTx")
org.springframework.transaction.ReactiveTransactionManager r2dbcTx(
        io.r2dbc.spi.ConnectionFactory connectionFactory) {
    return new org.springframework.r2dbc.connection
            .R2dbcTransactionManager(connectionFactory);
}
```

Đoạn trên minh họa class, package và constructor; chưa phải một project chạy độc lập. Ví dụ service với `DatabaseClient` đã được inject:

```java
@Transactional(transactionManager = "r2dbcTx")
public reactor.core.publisher.Mono<Void> saveAudit(long id) {
    return databaseClient.sql(
                    "INSERT INTO audit_events (id) VALUES (:id)")
            .bind("id", id)
            .fetch()
            .rowsUpdated()
            .then();
}
```

Transaction R2DBC chạy cùng **reactive subscription/context**, không được tạo chỉ bởi thời điểm gọi phương thức trả `Mono`. Trả pipeline, giữ tất cả bước tham gia cùng reactive chain, không tự tách `subscribe()` hoặc chuyển sang JDBC không được phối hợp.

### 7.4. MongoDB và Kafka

Với MongoDB, `MongoTransactionManager` và `ReactiveMongoTransactionManager` thuộc **Spring Data MongoDB**, không phải Spring JDBC. Mongo template phải cùng `MongoDatabaseFactory` với manager; MongoDB deployment phải hỗ trợ transaction. Với Kafka, `KafkaTransactionManager` thuộc Spring Kafka quản lý transaction của producer Kafka, không mặc nhiên quản lý `DataSource`.

Cùng cú pháp `@Transactional` có thể xuất hiện trong cả hai module. **Tên giống nhau không có nghĩa tài nguyên và rollback semantics giống nhau.**

## 8. Nhiều manager: xác định default rõ ràng, explicit ở đúng boundary

Giả sử một ứng dụng có `ordersJpaTx` và `reportJdbcTx`. Nếu mọi service method đều có `@Transactional` không qualifier thì sẽ khó bảo đảm dùng đúng manager. Hãy chọn một quy ước:

- **Một manager:** cấu hình một bean và dùng `@Transactional` khi không có ambiguity.
- **Nhiều manager nhưng có default thực sự rõ:** cấu hình default qua bean resolution (`@Primary`) hoặc `TransactionManagementConfigurer` theo version/cấu hình; những service dùng tài nguyên không thuộc default vẫn chỉ rõ `transactionManager`.
- **Nhiều manager ngang vai:** luôn khai báo `@Transactional(transactionManager = "...")` tại service boundary để người đọc và hệ thống chọn đúng manager.

Ví dụ đặt default bằng `TransactionManagementConfigurer` (fragment minh họa trong một class `@Configuration` có `@EnableTransactionManagement`, manager bean đã được tạo):

```java
@Override
public org.springframework.transaction.TransactionManager
annotationDrivenTransactionManager() {
    return ordersJpaTxManager;
}
```

Class chứa phương thức này phải `implements TransactionManagementConfigurer`. Việc chọn default như vậy có thể hợp lý khi hầu hết thao tác dùng JPA; nhưng service R2DBC, Mongo hoặc JDBC datasource khác vẫn cần manager riêng.

**Đừng nhầm `@Primary` trên `DataSource` với chọn đúng transaction manager cho mọi repository.** `@Primary` chỉ giúp giải quyết injection/default candidate tại những điểm cụ thể; không hợp nhất các resource hoặc làm các transaction khác tự tham gia.

## 9. Những tình huống dễ chọn nhầm

### 9.1. Chọn theo tên annotation thay vì theo resource

```java
@Transactional
public void write() {
    // JPA repository...
}
```

Không có cơ sở suy luận manager là `JpaTransactionManager` chỉ từ annotation. Phải biết cấu hình bean. Nếu project có manager JDBC là default nhưng method dùng JPA persistence unit khác, trạng thái flush/transaction có thể không được điều phối như dự kiến; tùy provider và thao tác, có thể báo lỗi hoặc không rollback đúng.

### 9.2. Đặt tên bean là “jpaTransactionManager” nhưng khởi tạo bằng manager JDBC

```java
@Bean("jpaTransactionManager")
PlatformTransactionManager wrongName(DataSource ds) {
    return new JdbcTransactionManager(ds);
}
```

Tên bean là `jpaTransactionManager`, nhưng **kiểu thật** vẫn là `JdbcTransactionManager` và nó quản lý JDBC datasource. Đổi tên không biến nó thành manager JPA.

### 9.3. Manager gắn datasource A, repository gắn datasource B

```java
@Bean("ordersTx")
PlatformTransactionManager ordersTx(
        @Qualifier("ordersDataSource") DataSource ds) {
    return new JdbcTransactionManager(ds);
}
```

Nếu `JdbcTemplate` trong method thực tế dùng `reportsDataSource`, operation đó không tự gia nhập local transaction của `ordersDataSource`. Hai cấu hình phải được đối chiếu theo **bean dependency wiring**, không chỉ theo tên bảng hoặc connection string.

### 9.4. Trộn JPA với JDBC mà dùng hai local managers trên cùng DB

JPA repository được `JpaTransactionManager` quản lý, nhưng một helper lại khai báo `@Transactional("jdbcTx")` và thực hiện JDBC trên cùng database. Việc dùng hai managers có thể tạo hai transaction boundaries hoặc sử dụng tài nguyên khác nhau. Không kỳ vọng `PROPAGATION_REQUIRED` của manager B tự động “join” transaction do manager A điều phối. Cần thiết kế **một transaction owner** và bảo đảm các data access APIs thực sự tham gia.

### 9.5. Hai datasources độc lập, tưởng rằng một annotation là distributed transaction

```text
@Transactional("ordersTx")
  ├── ghi DB orders   [local transaction do ordersTx quản lý]
  └── ghi DB billing  [ngoài phạm vi manager đó nếu dùng datasource khác]
```

Muốn hai DB được commit toàn cục bằng JTA thì cả hai phải được cấu hình cho XA/JTA coordinator. Nếu không, chọn mô hình outbox/saga hoặc cơ chế bù trừ phù hợp. Transaction synchronization tuần tự (commit DB rồi Kafka) có thể giảm lỗi thông thường nhưng **không bảo đảm atomic commit** nếu một bên commit được còn bên kia thất bại.

### 9.6. Chọn R2DBC manager cho method imperative

```java
@Transactional(transactionManager = "r2dbcTx")
public void saveUsingJdbc() {
    // JdbcTemplate.update(...);
}
```

`r2dbcTx` là `ReactiveTransactionManager`, method `void` là imperative. Đây là mismatch về programming model; không tạo được transaction JDBC đúng nghĩa. Cần imperative `PlatformTransactionManager` đi với JDBC hoặc viết lại operation như một R2DBC pipeline thực sự.

### 9.7. Gọi phương thức `@Transactional` nội bộ

```java
public void outer() {
    inner(); // self-invocation: không đi qua Spring proxy.
}

@Transactional(transactionManager = "ordersTx")
public void inner() {
    // ...
}
```

Trong chế độ Spring proxy mặc định, gọi `this.inner()` không tự áp dụng advice của `inner()`. Một cách sửa thông thường là tách boundary sang bean khác và gọi qua injected Spring bean; hoặc dùng `TransactionTemplate` ở nơi thích hợp.

### 9.8. Nhầm chính sách rollback với sai manager

Đúng manager chưa đủ nếu exception bị nuốt. Mặc định Spring rollback cho `RuntimeException` và `Error`; checked `Exception` không mặc nhiên kích hoạt rollback. Có thể dùng:

```java
@Transactional(
    transactionManager = "ordersTx",
    rollbackFor = Exception.class
)
public void importOrders() throws Exception {
    // ...
}
```

Phương thức cần thực sự ném exception ra khỏi boundary, hoặc đánh dấu rollback-only theo API phù hợp. Trả về bình thường sau khi bắt lỗi có thể khiến Spring commit.

## 10. Các khía cạnh nâng cao cần hiểu đúng

### `PROPAGATION_REQUIRED` và `REQUIRES_NEW`

`REQUIRED` là mặc định. Trong **cùng manager/tài nguyên** và call qua proxy phù hợp, method bên trong thường tham gia transaction đang hoạt động. `REQUIRES_NEW` yêu cầu transaction mới, khiến phần đã commit ở transaction trong có thể còn tồn tại dù transaction ngoài rollback. Tuy nhiên, hai manager local khác nhau vẫn có hai vùng quản lý tài nguyên, kể cả khi đều dùng `REQUIRED`.

Khi cần transaction mới, connection pool phải có khả năng cấp connection bổ sung; nếu không, các luồng có thể chờ nhau và hết kết nối.

### `NESTED`, savepoint và khả năng của manager

`DataSourceTransactionManager`/`JdbcTransactionManager` hỗ trợ nested transactions dựa trên JDBC savepoints khi driver cho phép. `JpaTransactionManager` không tự biến mọi thao tác JPA trong persistence context thành savepoint độc lập; hỗ trợ nested JDBC nếu cấu hình cho phép vẫn có giới hạn. Không nên mặc định `NESTED` sẽ hành xử giống nhau trên JPA, Mongo, R2DBC hay JTA.

### Isolation và `readOnly`

Chọn manager đúng không tự bảo đảm các yêu cầu isolation. `Isolation.SERIALIZABLE` hay `READ_COMMITTED` phải được datastore/driver hỗ trợ và áp dụng theo transaction thực tế. `readOnly=true` có thể được manager/provider tối ưu hoặc từ chối ghi tùy cấu hình; đừng dùng nó thay kiểm soát quyền ghi.

### Blocking và reactive context

Imperative transactions của `PlatformTransactionManager` thường dựa vào `ThreadLocal`. Tạo thread mới, dùng `CompletableFuture` hoặc chạy database operations trên thread ngoài không tự kế thừa transaction. Reactive transactions của `ReactiveTransactionManager` dùng Reactor `Context`; tách dòng xử lý hoặc tự `subscribe()` ngoài chuỗi có thể làm operation mất bối cảnh transaction.

### Manager local và trạng thái ngoài database

Nếu phương thức cập nhật database rồi gọi HTTP API, gửi email hoặc đẩy message, local transaction không thể tự rollback side effect đã xảy ra. Cân nhắc transactional outbox (cùng DB transaction lưu cả nghiệp vụ và bản ghi event), publisher có retry và idempotent consumer khi cần độ tin cậy xuyên hệ thống.

## 11. Kiểm chứng manager nào đang được chọn

Khi debug một vấn đề rollback không như mong đợi, kiểm tra từ wiring đến hành vi thực tế.

**Bước 1 — liệt kê manager beans trong ApplicationContext.** Fragment chạy trong ứng dụng Spring khi đã có biến `applicationContext`:

```java
applicationContext
        .getBeansOfType(
                org.springframework.transaction.TransactionManager.class)
        .forEach((name, manager) ->
                System.out.println(name + " -> "
                        + manager.getClass().getName()));
```

Tên bean, kiểu thực và đối tượng `DataSource`/`EntityManagerFactory`/`ConnectionFactory` nhận trong constructor là ba thông tin cần đối chiếu. Nếu là proxy, tên class runtime có thể chứa lớp proxy; đọc bean definition hoặc cấu hình ban đầu khi cần.

**Bước 2 — theo dấu phương thức.** Xác nhận service method được gọi qua Spring proxy; trên method hoặc class có qualifier/`transactionManager` nào; default được cấu hình ở đâu; `@EnableTransactionManagement`/auto-configuration đã thực sự bật hay chưa.

**Bước 3 — theo dấu repository/client.** Với JDBC, đối chiếu đúng `JdbcTemplate` và `DataSource`. Với JPA, đối chiếu `EntityManagerFactory` và repository `transactionManagerRef`. Với R2DBC, đối chiếu `ConnectionFactory` và reactive pipeline; với Mongo, đối chiếu `MongoDatabaseFactory`.

**Bước 4 — log transaction.** Trong Spring Boot, có thể bật log chẩn đoán khi cần:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
logging.level.org.springframework.orm.jpa=DEBUG
```

Những dòng log cụ thể khác nhau theo Spring version, manager và backend. Cấu hình này là ví dụ cho `application.properties` của ứng dụng Spring Boot; ví dụ chạy Maven thuần ở mục 6 không tự đọc file Spring Boot này.

**Bước 5 — thử rollback có chủ đích.** Insert vào đúng tài nguyên, ném một `RuntimeException` sau khi insert, đọc lại từ transaction/connection độc lập sau khi method kết thúc. Với hai datasources, kiểm tra kết quả của **từng database**, không chỉ một bảng.

### Bảng test cần có

| Test | Kỳ vọng |
| --- | --- |
| JDBC service dùng đúng manager, exception sau 2 inserts cùng datasource | Cả hai inserts rollback |
| JPA service dùng đúng `JpaTransactionManager`, lỗi sau `save`/`flush` | Thay đổi của cùng JPA transaction rollback |
| Hai datasource độc lập, hai local managers | Giao dịch bên đã commit không bị rollback bởi manager của bên kia |
| Manager gắn A nhưng DAO dùng B | Phát hiện mismatch; không khẳng định B được rollback bởi manager A |
| Reactive R2DBC method trả `Mono` và tham gia đúng `ConnectionFactory` | Operations trong reactive transaction rollback khi pipeline báo lỗi |
| `@Transactional` self-invocation | Kiểm tra advice có được kích hoạt hay bị bỏ qua |
| Checked exception thoát method | Xác nhận cấu hình `rollbackFor` phản ánh yêu cầu nghiệp vụ |
| Spring Data JPA nhiều persistence units | Repository được gắn đúng factory và `transactionManagerRef` |

Đừng chỉ test happy path: một transaction chỉ được kiểm chứng rõ khi gây lỗi giữa chừng và quan sát kết quả commit/rollback trên tài nguyên đúng.

## 12. Checklist lựa chọn thực tế

- [ ] Đã xác định toàn bộ dữ liệu cần cùng commit/rollback.
- [ ] Đã nhận diện API và factory thật: JDBC `DataSource`, JPA `EntityManagerFactory`, R2DBC `ConnectionFactory`, MongoDB `MongoDatabaseFactory`, Kafka `ProducerFactory`.
- [ ] Manager thực tế có kiểu phù hợp và được nối vào đúng factory.
- [ ] DAO/template/repository tham gia tài nguyên do manager quản lý.
- [ ] `@Transactional` chọn đúng bean bằng default được xác định rõ hoặc `transactionManager`/qualifier.
- [ ] Phân biệt imperative `PlatformTransactionManager` và reactive `ReactiveTransactionManager`.
- [ ] Hiểu rõ propagation, rollback rules, proxy/self-invocation và exception handling.
- [ ] Nếu cần atomic commit nhiều tài nguyên, đã thiết kế XA/JTA hoặc giải pháp nhất quán phù hợp; không dựa vào annotation.
- [ ] Có integration test chứng minh rollback khi xảy ra lỗi giữa nhiều thao tác.
- [ ] Khi cần JPA + JDBC cùng database, đã xác nhận điều kiện JDBC participation của `JpaTransactionManager`.

## 13. Ghi nhớ và câu hỏi tự kiểm tra

**Một câu nên thuộc:** *`@Transactional` mô tả ý định giao dịch; `TransactionManager` thực thi ý định đó trên một loại tài nguyên cụ thể; chỉ những thao tác tham gia tài nguyên mà manager thực sự quản lý mới được hưởng ranh giới commit/rollback của nó.*

Tự kiểm tra:

1. Có một method `@Transactional` dùng `JpaRepository`, nhưng bean `transactionManager` thực tế là `JdbcTransactionManager`. Nên kiểm tra những cấu hình nào trước khi tin vào rollback?
2. Hai method cùng dùng `@Transactional("orders")`, nhưng bean `orders` là `R2dbcTransactionManager`. Một method trả `Mono<Void>`, method kia trả `void`. Method nào phù hợp manager hơn, vì sao?
3. Một method ghi database A và B. Khi A và B dùng hai local transaction managers, lỗi sau khi B commit có rollback B được không?
4. Một service gọi JPA repository và `JdbcTemplate` trên cùng datasource. Khi nào `JpaTransactionManager` có thể quản lý được cả hai?
5. Vì sao đổi tên `@Transactional("jpa")` thành `@Transactional("jdbc")` không giải quyết được sai cấu hình tài nguyên?

Đáp án trọng tâm: kiểm tra **manager bean thực tế → factory/resource của manager → factory/resource của DAO → mô hình imperative/reactive → ranh giới và rollback rules**. Tên annotation hoặc tên bean đơn lẻ không đủ để chứng minh điều gì đã được commit/rollback.

## Tài liệu tham khảo chính thức

- [Spring Framework — Transaction Abstraction](https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html): phân biệt `PlatformTransactionManager` và `ReactiveTransactionManager`.
- [Spring Framework — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): proxy, `TransactionInterceptor`, imperative vs reactive.
- [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): qualifier/`transactionManager`, nhiều managers, propagation và rollback.
- [Spring Framework — Controlling JDBC Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `JdbcTransactionManager`, `DataSourceTransactionManager`, `DataSourceUtils`.
- [Spring Framework — `JpaTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/orm/jpa/JpaTransactionManager.html): EntityManagerFactory, điều kiện tham gia JDBC cùng datasource.
- [Spring Framework — R2DBC](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html): `R2dbcTransactionManager` và connection trong Reactor Context.
- [Spring Data MongoDB — Sessions and Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): `MongoTransactionManager`, `ReactiveMongoTransactionManager`.
- [Spring Kafka — Transactions](https://docs.spring.io/spring-kafka/reference/kafka/transactions.html): `KafkaTransactionManager` và ranh giới kết hợp database/Kafka.
