# TransactionInterceptor bao quanh lời gọi nghiệp vụ trong Spring

> **Spring Framework — Transaction Management → Cơ chế proxy.** Bài học giải thích chính xác đường đi của một lời gọi `@Transactional` trong Spring: từ đối tượng proxy, qua `TransactionInterceptor` và `TransactionManager`, đến mã nghiệp vụ, rồi quay trở lại để commit hoặc rollback. Mục đích là hiểu *khi nào* giao dịch được tạo, *ai* kết thúc giao dịch và *vì sao* những lời gọi tưởng giống nhau có thể có kết quả rollback khác nhau.

## 1. Bức tranh tổng thể

Khi một Spring bean được cấu hình giao dịch khai báo, Spring thường không chèn `beginTransaction()` và `commit()` vào thân phương thức do lập trình viên viết. Trong **proxy mode** (chế độ mặc định), Spring tạo một **AOP proxy** để chặn các lời gọi đi qua bean đó. Proxy có một chuỗi advice/interceptor; một mắt xích phục vụ giao dịch là `org.springframework.transaction.interceptor.TransactionInterceptor`.

Các thành phần chính:

| Thành phần | Vai trò |
| --- | --- |
| **Caller** | Controller, service khác, scheduled task hoặc mã gọi một Spring bean. |
| **AOP proxy** | Đối tượng bên ngoài thường được injector trả về; nhận lời gọi trước target. |
| **Transaction advisor / pointcut** | Xác định method nào cần áp dụng transaction advice dựa trên metadata. |
| **TransactionAttributeSource** | Cung cấp `TransactionAttribute` của method/class (ví dụ từ `@Transactional`), gồm propagation, isolation, rollback rules, read-only, timeout và manager qualifier. |
| **TransactionInterceptor** | `MethodInterceptor` thực thi transaction advice xung quanh method invocation. |
| **TransactionManager** | Thực hiện việc lấy/tham gia, commit/rollback, giải phóng/tạm treo tài nguyên giao dịch. Imperative: `PlatformTransactionManager`; reactive: `ReactiveTransactionManager`. |
| **Target method** | Phương thức Java do lập trình viên viết; thực hiện nghiệp vụ với JDBC/JPA hoặc tài nguyên thích hợp. |
| **Resource** | JDBC `Connection`, JPA `EntityManager`, R2DBC `Connection`... thực sự tham gia transaction. |

Sơ đồ đường đi (mô tả transaction imperative, lời gọi qua proxy):

```text
Caller
  |
  | 1. gọi Spring bean được inject
  v
AOP PROXY
  |
  | chọn advice tương ứng cho method
  v
TransactionInterceptor
  |
  | 2. đọc TransactionAttribute (từ @Transactional, v.v.)
  | 3. chọn PlatformTransactionManager phù hợp
  | 4. bắt đầu hoặc tham gia transaction
  |    (có thể gắn resource với thread)
  |
  | 5. invocation.proceed()
  v
TARGET METHOD / business logic
  |
  | JDBC / JPA / repository / service khác ...
  |
  +---------------------------+
                              |
             trả về / ném exception
                              |
                              v
TransactionInterceptor
  |
  | 6a. hoàn tất bình thường --> yêu cầu COMMIT
  | 6b. exception           --> quyết định ROLLBACK hay COMMIT
  |     theo rollback rules và trạng thái transaction
  | 7. cleanup / khôi phục context
  v
AOP PROXY --> Caller
        (trả kết quả hoặc ném exception)
```

**Điểm then chốt:** `TransactionInterceptor` chạy *bao quanh lời gọi nghiệp vụ*, thường quản lý transaction **trước khi đi vào target** và **sau khi target trở ra**. Mã trong target không phải tự gọi `commit()` nếu đã giao cho Spring quản lý; transaction manager quyết định commit/rollback.

Đây là mô hình logic, không phải sơ đồ từng dòng trong mã nguồn Spring. Trong thực tế có thể có nhiều advisors (logging, security, retry, metrics...), và thứ tự của chúng có thể ảnh hưởng advice nào chạy bên trong/bên ngoài transaction.

## 2. Điều gì khiến lời gọi được interceptor chặn?

### Cần cả metadata và runtime infrastructure

`@Transactional` tự nó là **metadata**. Để biến annotation thành hành vi runtime, một ứng dụng Spring imperative thường cần:

1. Một Spring bean chứa method được định nghĩa là transactional.
2. Bật transaction management bằng `@EnableTransactionManagement`, XML `<tx:annotation-driven/>` hoặc auto-configuration tương ứng.
3. Một `TransactionManager` phù hợp (ví dụ `JdbcTransactionManager` cho JDBC, `JpaTransactionManager` cho JPA).
4. Một caller gọi **qua Spring proxy** thay vì trực tiếp tạo target bằng `new` hay gọi nội bộ `this.method()`.
5. Các thao tác truy cập dữ liệu thực sự tham gia tài nguyên mà manager quản lý.

Ví dụ cấu hình JDBC (fragment, không chạy độc lập vì chưa khai báo `DataSource`):

```java
@Configuration
@EnableTransactionManagement
public class TxConfig {
    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }
}
```

Cần import `org.springframework.context.annotation.*`, `org.springframework.transaction.PlatformTransactionManager`, `org.springframework.jdbc.support.JdbcTransactionManager` và `javax.sql.DataSource`. `@EnableTransactionManagement` đăng ký infrastructure để tìm transactional metadata, tạo advisor/proxy và áp dụng `TransactionInterceptor` khi method được gọi qua proxy.

Nếu phương thức **không có transaction metadata** (trực tiếp hoặc từ class/interface phù hợp) thì transaction advice không tự điều phối nó chỉ vì method dùng SQL. Nếu bean đã được proxy bởi advice khác, sự hiện diện của proxy cũng chưa đủ để chứng minh giao dịch đang hoạt động cho method đang xét.

### `@Transactional` có thể đặt ở đâu?

Thường đặt ở **public service method** là dễ hiểu và nhất quán. Annotation có thể đặt trên class hoặc method; method-level metadata cụ thể được ưu tiên khi resolution diễn ra. Spring cũng hỗ trợ interface-level annotation trong những chế độ proxy phù hợp, nhưng tài liệu Spring khuyên đặt annotation trên concrete class/method để tránh khác biệt giữa proxy và AspectJ weaving.

Trong Spring Framework 6+, class-based proxy có thể intercept một số `protected` hoặc package-visible methods từ lời gọi bên ngoài; interface-based proxy yêu cầu public method thuộc proxied interface. **Private methods không trở thành transactional entry point trong proxy mode.** Không nên suy ra rằng mọi method không public đều được chặn theo cùng quy tắc: điều đó phụ thuộc kiểu proxy và phiên bản/configuration.

## 3. Bên trong `TransactionInterceptor`: luồng xử lý theo từng bước

### Bước 1 — nhận `MethodInvocation`

`TransactionInterceptor` triển khai AOP Alliance `MethodInterceptor`. Khi Spring AOP gọi `invoke(MethodInvocation)`, interceptor có thông tin về method, target class và callback `proceed()` để chuyển tiếp lời gọi sang advice tiếp theo hoặc đến target.

Không nhầm `MethodInvocation` ở đây với một HTTP request. Một request web có thể gọi nhiều service methods; mỗi service method được intercept là một ranh giới AOP riêng, và propagation quyết định chúng dùng một hay nhiều physical transactions.

### Bước 2 — xác định transaction attributes

`TransactionInterceptor` kế thừa logic từ `TransactionAspectSupport`. Infrastructure dùng `TransactionAttributeSource` để tìm metadata của method/class, chẳng hạn:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.READ_COMMITTED,
    readOnly = false,
    rollbackFor = IOException.class
)
public void importFile() throws IOException {
    // Business method.
}
```

Đây là **fragment**: cần các imports và ngữ cảnh Spring. Các attributes nói cho interceptor biết ý định nghiệp vụ. Chúng **không phải** transaction manager và **không tự bảo đảm** tài nguyên đã tham gia transaction.

Nếu một method được proxy nhưng không có transaction attributes tương ứng, gọi nó không đồng nghĩa sẽ bắt đầu transaction chỉ vì nó nằm trên proxy.

### Bước 3 — xác định manager và ranh giới giao dịch

Với imperative code, Spring cần một `PlatformTransactionManager` như `JdbcTransactionManager`, `DataSourceTransactionManager` hoặc `JpaTransactionManager`. Nếu có nhiều managers, qualifier `@Transactional(transactionManager = "ordersTx")` hoặc cấu hình default giúp chọn đúng bean.

Manager được yêu cầu bắt đầu hoặc tham gia transaction dựa theo propagation:

- `REQUIRED` (mặc định): nếu đã có transaction phù hợp thì tham gia; nếu chưa có thì bắt đầu mới.
- `REQUIRES_NEW`: bắt đầu transaction vật lý độc lập, có thể tạm treo transaction ngoài.
- `NESTED`: có thể dùng savepoint tùy manager/tài nguyên.
- `SUPPORTS`: có thể thực thi không có transaction thực nếu chưa có transaction.

**Không phải mỗi lần đi qua interceptor đều đồng nghĩa `BEGIN` vật lý mới.** Nếu inner method dùng `REQUIRED` và đã có transaction tương ứng, manager có thể chỉ mở một **logical scope** tham gia physical transaction đang chạy.

Ví dụ hai method:

```java
@Transactional
public void createInvoice() {
    invoiceRepository.save(...);
    taxService.calculateAndSave(...); // service bean khác, cùng manager
}

@Transactional
public void calculateAndSave(...) {
    // REQUIRED mặc định: thường tham gia transaction của createInvoice().
}
```

Các dấu `...` biểu thị dữ liệu và methods của ứng dụng, đây không phải code chạy độc lập. Khi cùng manager và các resource tham gia đúng cách, một commit vật lý ở outer có thể xác nhận cả hai nghiệp vụ.

### Bước 4 — gọi business method

Sau khi thiết lập transaction context, interceptor gọi `invocation.proceed()`. Lời gọi chạy tiếp qua các advice còn lại và cuối cùng vào target method. Business method dùng repository/DAO/JdbcTemplate như bình thường.

Với imperative JDBC, Spring thường gắn resource vào thread qua `TransactionSynchronizationManager`. `JdbcTemplate` nhận JDBC connection tham gia transaction từ cùng `DataSource` nhờ cơ chế `DataSourceUtils`. Vì vậy nhiều `jdbcTemplate.update(...)` có thể dùng cùng transaction mà target method không cần tự quản lý `setAutoCommit(false)`.

**Interceptor không biến mọi SQL từ bất kỳ datasource thành một giao dịch:** connection mở thủ công bằng `DriverManager` hoặc từ datasource khác có thể nằm ngoài transaction được quản lý. Khi dùng JPA phải khớp `EntityManagerFactory`; khi dùng R2DBC phải khớp `ConnectionFactory` và reactive context.

### Bước 5 — nhận kết quả hoặc exception từ target

Có hai nhánh căn bản:

- **Target trở về bình thường:** interceptor yêu cầu manager hoàn tất theo hướng commit. Manager vẫn có thể rollback nếu physical transaction đã bị đánh dấu rollback-only, hoặc commit có thể thất bại vì lỗi DB/driver.
- **Target ném exception:** interceptor so sánh exception với rollback rules, rồi yêu cầu manager rollback hoặc commit theo cấu hình. Exception thường được truyền tiếp đến caller (có thể kèm ngoại lệ khác phát sinh khi hoàn tất transaction).

Với defaults của `@Transactional` trong các cấu hình thông thường, **`RuntimeException` và `Error` kích hoạt rollback; checked exception không mặc nhiên kích hoạt rollback**. Có thể chỉ rõ `rollbackFor` hoặc `noRollbackFor`. Quy tắc này còn chịu tác động của transaction đã rollback-only và các lỗi tài nguyên: không thể bảo đảm “checked exception luôn commit”.

### Bước 6 — cleanup và khôi phục context

Sau commit/rollback hoặc khi xử lý lỗi, infrastructure dọn dẹp transaction status/resource theo trách nhiệm của manager. Nếu method inner tham gia outer, Spring phải khôi phục transaction information của scope gọi trước chứ không được tùy tiện commit hoặc đóng physical transaction của outer. Sau khi proxy trả quyền điều khiển, caller nhìn thấy kết quả hoặc exception theo thực tế hoàn tất transaction.

**Đừng nghĩ “hàm return rồi thì transaction không thể fail”.** `commit()` được thực hiện ở lớp advice sau khi thân method đã tính ra giá trị trả về; nếu commit thất bại hoặc transaction rollback-only, caller có thể nhận exception dù target đã đi đến lệnh `return`.

## 4. Pseudocode để hiểu “bao quanh”, không phải source Spring nguyên bản

Đoạn sau mô phỏng *ý tưởng* của imperative transaction advice. Đây là **pseudocode**, không phải chữ ký phương thức và source thật của `TransactionInterceptor`, không dùng để biên dịch:

```text
attr = transactionAttributeSource.resolve(invokedMethod, targetClass)
manager = resolveTransactionManager(attr)
status = manager.getTransaction(attr)  // create hoặc join tùy propagation

try {
    value = invocation.proceed()       // chạy advice còn lại và business logic
    manager.commit(status)            // có thể rollback nếu rollback-only
    return value
} catch (Throwable error) {
    if (attr.rollbackOn(error)) {
        manager.rollback(status)
    } else {
        manager.commit(status)
    }
    throw error
} finally {
    restoreTransactionContext()
}
```

**Cảnh báo về mức đơn giản hóa:** Spring thật còn xử lý các nhánh không có transaction attributes, transaction synchronization, method identification, nhiều propagation, rollback-only, lỗi commit/rollback, các return types đặc biệt và reactive flow. Vì vậy không thể suy luận chính xác mọi thứ từ pseudocode, đặc biệt thứ tự ném exception khi manager.commit() tự thất bại. Mục tiêu của pseudocode là làm rõ **trình tự bắt đầu → proceed → commit/rollback → cleanup**.

Một cách viết dễ nhớ là:

```text
BEFORE: TransactionInterceptor quyết định ranh giới transaction
AROUND: invocation.proceed() đưa lời gọi vào business method
AFTER : TransactionInterceptor xem kết quả/exception và kết thúc scope
```

Thứ “bao quanh” ở đây là **method invocation qua proxy**, không phải mọi dòng mã chạy trong cùng HTTP request, không phải toàn bộ thread mới sinh ra, cũng không phải mọi lời gọi nội bộ trong object.

## 5. Ví dụ Java 17+ có thể chạy: quan sát proxy, transaction và rollback

Ví dụ dùng Spring Framework 6.2.x, Spring JDBC, H2 in-memory database, Java 17+ và Maven. Hai service beans có `@Transactional`:

- `OrderService.place(...)` ghi một order.
- `AuditService.record(...)` ghi một audit record trong **cùng datasource**.
- Khi cố ý ném `IllegalStateException` sau hai thao tác, interceptor xử lý rollback; cả order và audit record của lần gọi lỗi đều không còn.
- Khi method hoàn tất bình thường, interceptor commit; hai record của lần gọi thành công tồn tại.
- In `AopUtils.isAopProxy(...)` để xác nhận bean nhận được là AOP proxy và `TransactionSynchronizationManager` để kiểm tra transaction đang active bên trong method.

Dự án không cần Spring Boot và không cần database server.

### 5.1. Tạo cấu trúc dự án

```text
transaction-interceptor-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/
                └── learning/
                    └── TransactionInterceptorDemo.java
```

Nội dung `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.learning</groupId>
    <artifactId>transaction-interceptor-demo</artifactId>
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
                    <mainClass>dev.learning.TransactionInterceptorDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.2. Nội dung `TransactionInterceptorDemo.java`

```java
package dev.learning;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class TransactionInterceptorDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class AppConfig {

        @Bean
        DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:tx_interceptor;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new JdbcTransactionManager(ds);
        }

        @Bean
        AuditService auditService(JdbcTemplate jdbc) {
            return new AuditService(jdbc);
        }

        @Bean
        OrderService orderService(JdbcTemplate jdbc, AuditService audit) {
            return new OrderService(jdbc, audit);
        }
    }

    public static class AuditService {
        private final JdbcTemplate jdbc;

        public AuditService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional
        public void record(int orderId) {
            System.out.println(
                    "audit.txActive="
                    + TransactionSynchronizationManager
                            .isActualTransactionActive());

            jdbc.update(
                    "INSERT INTO audit_events (order_id, description) "
                    + "VALUES (?, ?)",
                    orderId, "order placed");
        }
    }

    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final AuditService audit;

        public OrderService(JdbcTemplate jdbc, AuditService audit) {
            this.jdbc = jdbc;
            this.audit = audit;
        }

        @Transactional
        public void place(int id, boolean failAfterAudit) {
            System.out.println(
                    "order.txActive="
                    + TransactionSynchronizationManager
                            .isActualTransactionActive());

            jdbc.update(
                    "INSERT INTO orders (id, description) VALUES (?, ?)",
                    id, "sample order");

            // Gọi sang một Spring bean khác nên audit proxy được đi qua.
            // Propagation.REQUIRED mặc định => tham gia transaction hiện tại.
            audit.record(id);

            if (failAfterAudit) {
                throw new IllegalStateException("simulated failure");
            }
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            // DDL chạy trước các thao tác nghiệp vụ trong thí nghiệm.
            jdbc.execute("""
                    CREATE TABLE orders (
                        id INT PRIMARY KEY,
                        description VARCHAR(80) NOT NULL
                    )
                    """);
            jdbc.execute("""
                    CREATE TABLE audit_events (
                        order_id INT PRIMARY KEY,
                        description VARCHAR(80) NOT NULL
                    )
                    """);

            OrderService orders = context.getBean(OrderService.class);
            AuditService audit = context.getBean(AuditService.class);

            System.out.println(
                    "orderProxy=" + AopUtils.isAopProxy(orders));
            System.out.println(
                    "auditProxy=" + AopUtils.isAopProxy(audit));

            // Lượt thứ nhất: cả hai INSERT thành công => commit.
            orders.place(1, false);

            // Lượt thứ hai: cả hai INSERT đã chạy rồi ném exception
            // => interceptor rollback transaction của lượt thứ hai.
            try {
                orders.place(2, true);
            } catch (IllegalStateException expected) {
                System.out.println("caught=" + expected.getMessage());
            }

            Integer orderCount = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM orders", Integer.class);
            Integer auditCount = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM audit_events", Integer.class);

            System.out.println("orders=" + orderCount);
            System.out.println("auditEvents=" + auditCount);
        }
    }
}
```

### 5.3. Biên dịch và chạy

Yêu cầu cài JDK 17+ và Maven; khi chạy lần đầu cần Internet để Maven tải dependencies. Trong thư mục `transaction-interceptor-demo` chạy:

```bash
mvn -q clean compile exec:java
```

Những dòng **do chương trình in ra**, không tính log tùy môi trường:

```text
orderProxy=true
auditProxy=true
order.txActive=true
audit.txActive=true
order.txActive=true
audit.txActive=true
caught=simulated failure
orders=1
auditEvents=1
```

Giải thích theo đúng thứ tự:

1. `@EnableTransactionManagement` khiến Spring tạo proxy cho hai service classes có transactional methods. Chúng không khai báo business interface, nên Spring có thể dùng class-based proxies.
2. Khi gọi `orders.place(1, false)`, call đi vào `OrderService` proxy. Interceptor lấy default transaction metadata, yêu cầu `JdbcTransactionManager` bắt đầu JDBC transaction T1. Trong method, `isActualTransactionActive()` là `true`.
3. `audit.record(1)` đi qua proxy của `AuditService`. Do default `REQUIRED` và cùng manager/datasource, inner tham gia T1, không commit vật lý riêng khi `record` kết thúc.
4. `place(1,false)` trở về bình thường, interceptor của outer yêu cầu commit. Hai records của T1 tồn tại.
5. `place(2,true)` mở T2. Hai INSERT xảy ra, nhưng method ném `IllegalStateException`. Interceptor của outer thấy exception theo rollback rules mặc định và yêu cầu rollback T2.
6. `main` bắt exception sau khi nó đi qua proxy. T2 đã được rollback; T1 của lần gọi trước đã commit nên không bị ảnh hưởng.
7. Hai câu `SELECT COUNT(*)` ở cuối dùng connection khác ngoài transaction đã kết thúc, vì thế nhìn thấy chính xác một order và một audit record.

Bài học của ví dụ là **thời điểm giao dịch kết thúc nằm ở lớp interceptor**, còn thân business method chỉ thực hiện thao tác dữ liệu.

> **Giới hạn quan sát:** `AopUtils.isAopProxy(...) == true` xác nhận bean có AOP proxy, nhưng riêng điều này không chứng minh *method đang xét* chắc chắn có transaction advice. Kết hợp việc kiểm tra target method, transaction manager/resource và test rollback mới có bằng chứng đầy đủ.

### 5.4. Thử nghiệm tùy chọn

Sau khi chạy bản gốc, có thể sửa tham số lần gọi thứ hai từ `orders.place(2, true)` thành `orders.place(2, false)` và chạy lại trên một JVM mới. Khi đó cả hai lượt kết thúc bình thường: số đếm `orders` và `auditEvents` đều là 2; dòng `caught=...` không xuất hiện. Việc so sánh nhánh thành công và nhánh lỗi cho thấy quyết định commit/rollback không nằm trong hai câu SQL của business method.

Trong thực tế, cần thêm integration tests cho các trường hợp lỗi SQL, timeout, rollback-only, và cập nhật nhiều bảng; không chỉ dựa trên `isActualTransactionActive()`.

## 6. Vì sao self-invocation làm lời gọi “thoát” khỏi interceptor?

Đây là lỗi phổ biến nhất khi hiểu sai transaction proxy.

```java
@Service
public class ReportService {

    public void generate() {
        saveReport();  // tương đương this.saveReport()
    }

    @Transactional
    public void saveReport() {
        // Ghi dữ liệu cần giao dịch.
    }
}
```

Đoạn code là **fragment** (cần import `@Service`, `@Transactional` và logic lưu dữ liệu). Giả sử caller gọi `reportService.generate()` từ Spring context:

- Caller đi qua proxy tới `generate()`, nhưng `generate()` không có transaction metadata.
- Bên trong target, lệnh `this.saveReport()` **không quay lại proxy**. Vì vậy interceptor của `saveReport` không được gọi và annotation trên `saveReport` không tự kích hoạt transaction mới.
- Nếu `generate()` lại đã có transaction (ví dụ do annotation ở class/outer method), `saveReport` vẫn có thể sử dụng transaction **đang tồn tại**, nhưng **những thuộc tính riêng của `saveReport`** như `REQUIRES_NEW` hoặc `rollbackFor` sẽ không được interceptor áp dụng cho lời gọi nội bộ.

Đó là lý do chỉ kiểm tra `TransactionSynchronizationManager.isActualTransactionActive()` trong một method có thể chưa đủ để kết luận annotation *của chính method đó* đã được intercept. Transaction có thể đến từ outer method.

### Cách sửa được khuyên dùng: tách ranh giới sang bean khác

```java
@Service
class ReportWriter {
    @Transactional
    public void saveReport() {
        // Thao tác dữ liệu.
    }
}

@Service
class ReportFacade {
    private final ReportWriter writer;

    ReportFacade(ReportWriter writer) {
        this.writer = writer;
    }

    public void generate() {
        writer.saveReport(); // gọi qua proxy bean ReportWriter
    }
}
```

Đoạn này là fragment. `writer` phải là bean do Spring cung cấp; đừng tự `new ReportWriter()`. Ngoài cách tách bean, có thể dùng `TransactionTemplate` để đặt boundary bằng code. Dùng `AopContext.currentProxy()` và bật `exposeProxy` là một giải pháp kỹ thuật đặc thù, gây coupling với AOP và khó bảo trì hơn nên không nên chọn mặc định.

### Khi nào AspectJ mode khác proxy mode?

`@EnableTransactionManagement(mode = AdviceMode.ASPECTJ)` kết hợp cấu hình weaving và `spring-aspects` có thể áp dụng transaction advice ở mức bytecode thay vì dựa vào caller đi qua proxy; vì vậy self-invocation cũng có thể được xử lý. Đây là chế độ riêng, cần compile-time hoặc load-time weaving phù hợp và không tự có chỉ bằng việc thêm annotation vào source.

Bài học này tập trung vào **proxy mode**, là chế độ thông thường.

## 7. JDK proxy, class-based proxy và method visibility

Spring AOP có hai họ proxy thường gặp:

| Kiểu | Khi nào phù hợp | Điều phải lưu ý |
| --- | --- | --- |
| **JDK dynamic proxy** | Bean được proxy qua interface. | Caller thường làm việc qua interface; chỉ các public interface methods được proxy. Không lấy bean bằng cách ép sang implementation nếu proxy không implements class đó. |
| **Class-based proxy (CGLIB)** | Bean không có business interface hoặc cấu hình yêu cầu proxy class. | Proxy là subclass; final class hoặc final method không thể được subclass/override để chặn theo cơ chế này. Visibility còn phụ thuộc version/cấu hình. |

`@EnableTransactionManagement(proxyTargetClass = true)` yêu cầu class-based proxy cho cấu hình proxy mode. Khi `proxyTargetClass=false`, Spring có thể dùng JDK dynamic proxies cho các beans có giao diện và class-based proxies cho beans không có giao diện; giá trị mặc định này không có nghĩa Spring luôn tạo JDK proxy.

Ví dụ interface-based:

```java
public interface PaymentService {
    void pay(long orderId);
}

@Service
public class PaymentServiceImpl implements PaymentService {
    @Override
    @Transactional
    public void pay(long orderId) {
        // ...
    }
}
```

Đây là fragment: khi Spring sử dụng JDK proxy, caller nên inject `PaymentService`. `getBean(PaymentServiceImpl.class)` có thể không tìm thấy bean theo class mong muốn hoặc ép kiểu thất bại vì object proxy chỉ implements interface.

**Chọn method public và đặt `@Transactional` trên concrete service method** là quy ước dễ đọc, ổn định giữa các cấu hình proxy. Đừng dựa vào interception của private/final methods hoặc của lời gọi từ constructor/`@PostConstruct`, vì proxy chưa chắc đã sẵn sàng và các cơ chế đó không đi qua interception bình thường.

## 8. Exception đi qua TransactionInterceptor: hiểu đúng quyết định rollback

### Mặc định rollback cho unchecked exceptions

```java
@Transactional
public void createCustomer() {
    jdbc.update("INSERT INTO customers ...");
    throw new IllegalArgumentException("invalid");
}
```

Fragment minh họa, SQL thiếu thông tin cố ý; đừng chạy nguyên văn. Khi `IllegalArgumentException` thoát khỏi method qua proxy, rollback rules mặc định yêu cầu rollback.

### Checked exceptions cần khai báo khi muốn rollback

```java
@Transactional(rollbackFor = IOException.class)
public void importOrders(Path file) throws IOException {
    // Đọc file và ghi database.
    // IOException thoát khỏi method sẽ yêu cầu rollback.
}
```

Fragment: cần import `java.io.IOException`, `java.nio.file.Path`, và thực thi thực tế. Khi không khai báo `rollbackFor`, checked exception thường **không** nằm trong rollback rules mặc định; interceptor có thể yêu cầu commit dù checked exception được ném. Nhưng nếu tài nguyên hoặc inner scope đã đánh dấu rollback-only, physical transaction vẫn rollback.

### Bắt exception và trả về bình thường

```java
@Transactional
public void process() {
    jdbc.update("INSERT INTO items ...");
    try {
        performNextStep();
    } catch (RuntimeException ignored) {
        // Exception bị nuốt: interceptor chỉ thấy method trả về bình thường.
    }
}
```

Fragment minh họa. Nếu các bước tiếp theo thất bại nhưng exception không thoát khỏi proxy invocation, interceptor không thể dựa vào exception đó để áp dụng rollback rule. Nếu resource chưa tự đánh dấu rollback-only, method trở về bình thường và transaction có thể commit. Cần chọn chiến lược rõ: ném lại exception, định nghĩa rollback rules phù hợp, hoặc đánh dấu rollback-only theo API Spring khi thật sự cần.

### Rollback-only và `UnexpectedRollbackException`

Hai method `REQUIRED` có thể tạo **hai logical scopes** trên một physical transaction. Nếu inner đã đánh dấu rollback-only nhưng outer bắt lỗi rồi cố trả về bình thường, interceptor outer có thể gọi commit nhưng manager buộc rollback và ném `UnexpectedRollbackException`. Lý do: caller không được hiểu nhầm transaction đã commit.

```text
T1 (outer @Transactional)
  |
  +-- inner @Transactional REQUIRED
  |     +-- lỗi => đánh dấu T1 rollback-only
  |
  +-- outer bắt lỗi rồi return
  |
  +-- outer interceptor gọi commit(T1)
  |     +-- T1 bị rollback
  |     +-- báo UnexpectedRollbackException
```

Không nên chữa bằng cách bắt và bỏ qua `UnexpectedRollbackException`. Cần xem lại nghiệp vụ: nếu inner phải rollback độc lập, cân nhắc `REQUIRES_NEW` khi phù hợp (và nhớ rằng kết quả đã commit của inner sẽ không tự rollback cùng outer), hoặc tách ranh giới khác.

## 9. Một số thứ nằm ngoài phạm vi “bao quanh” mặc định

### Lời gọi sang thread khác

Một transaction imperative do `PlatformTransactionManager` quản lý thường gắn với execution thread. Tạo thread mới bằng `new Thread(...)`, `CompletableFuture.supplyAsync(...)` hoặc chạy một tác vụ `@Async` không tự mang theo transaction context.

```java
@Transactional
public void placeOrder() {
    CompletableFuture.runAsync(() -> {
        // Chạy trên thread khác:
        // không tự tham gia transaction imperative của thread gọi.
    });
}
```

Fragment minh họa. Đặc biệt, nếu async task ghi vào database của cùng ứng dụng, nó có thể dùng connection và transaction độc lập. Không suy luận “code nằm trong dấu ngoặc của method `@Transactional` nên luôn rollback chung”.

### Reactive `Publisher`

`TransactionInterceptor` hiện hỗ trợ cả imperative và reactive paths. Với reactive return types như Reactor `Mono`/`Flux` và manager `ReactiveTransactionManager`, transaction gắn với **Reactor Context** của subscription, không phải đơn giản “bắt đầu trước khi thân Java method tạo ra `Mono` rồi commit ngay khi method trả `Mono`”.

Hình dung:

```text
caller gọi proxy method trả Mono
       |
       v
TransactionInterceptor nhận diện reactive return type
       |
       v
xây transaction-aware Publisher
       |
       v
khi subscribe và chạy reactive pipeline:
    begin/join reactive transaction
    -> các thao tác R2DBC trong cùng context
    -> complete/error/cancel theo semantics reactive
    -> commit/rollback/cleanup tương ứng
```

Tài liệu Spring phân biệt rõ `PlatformTransactionManager` cho method imperative (kể cả `void`) và `ReactiveTransactionManager` cho reactive transaction. Đừng chọn `R2dbcTransactionManager` cho một method JDBC imperative chỉ vì method có `@Transactional`. Với reactive cancel signal, cần xem semantics chính xác của phiên bản Spring và nguồn reactive để không mặc định “cancel tương đương return bình thường”.

### External side effects

TransactionInterceptor chỉ điều phối **tài nguyên được manager quản lý**. Nếu method đã gọi HTTP API, gửi email, ghi file hoặc gửi message ra broker không tham gia cùng một transaction coordinator, rollback database **không tự hoàn tác side effect**. Với nhiều tài nguyên cần atomicity hãy xem JTA/XA khi có hạ tầng phù hợp; ngoài ra có thể dùng outbox, saga, idempotency và compensation theo yêu cầu hệ thống.

### Trật tự các AOP advice

Nếu có thêm `@Around` logging, security, retry hoặc caching, thứ tự advisor quyết định đoạn logic nào được bao bởi transaction. Ví dụ, một advice logging ở **ngoài** transaction advice có thể đo cả thời gian commit; nếu ở **trong**, nó có thể dừng đo khi business method trả về trước khi transaction manager commit.

Có thể cấu hình order cho transaction advice qua `@EnableTransactionManagement(order = ...)` và dùng `@Order` cho aspects khác. **Không đoán** thứ tự chỉ từ thứ tự annotation viết trên method. Khi debugging lỗi commit hoặc retry, hãy kiểm tra thứ tự thực tế, vì retry ngoài transaction thường có semantics khác retry xảy ra bên trong một transaction đã đánh dấu rollback-only.

## 10. Cách quan sát và debug TransactionInterceptor

### Bật logging đúng namespace

Trong ứng dụng Spring Boot, có thể thử các cấu hình sau trong `application.properties`:

```properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.transaction.support=DEBUG
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Log thực tế và định dạng khác nhau theo phiên bản Spring, manager và logging backend. Không nên viết test phụ thuộc vào *chính xác* một câu log. Ví dụ Spring thuần ở mục 5 không tự đọc `application.properties` theo cách Spring Boot làm.

### Chẩn đoán từ bên ngoài proxy

Trong integration test hoặc đoạn code có ApplicationContext:

```java
Object bean = applicationContext.getBean(OrderService.class);
System.out.println(AopUtils.isAopProxy(bean));
```

Đây là **fragment**: cần biến `applicationContext` và class `OrderService` đã tồn tại. Nếu proxy là JDK proxy, dùng interface type khi lấy bean; nếu class-based proxy có thể dùng concrete class.

Khi cần xem advisors trên một Spring AOP proxy, có thể dùng:

```java
if (bean instanceof org.springframework.aop.framework.Advised advised) {
    for (var advisor : advised.getAdvisors()) {
        System.out.println(advisor.getAdvice().getClass().getName());
    }
}
```

Fragment này có thể giúp thấy `TransactionInterceptor` là advice nào, nhưng một bean có advisor không có nghĩa tất cả methods đều được advice match; phải xác nhận method/pointcut metadata. Spring có thể tạo các proxies không cho phép inspection theo cách này trong một số cấu hình.

### Quan sát trạng thái trong method imperative

```java
boolean txActive =
        TransactionSynchronizationManager.isActualTransactionActive();
boolean readOnly =
        TransactionSynchronizationManager.isCurrentTransactionReadOnly();
Integer isolation =
        TransactionSynchronizationManager
                .getCurrentTransactionIsolationLevel();
```

Đây là API chẩn đoán cho transaction imperative. `isolation == null` có thể đơn giản nghĩa Spring không đặt isolation riêng; **không có nghĩa database không có isolation**. Muốn biết JDBC isolation thật, hỏi `Connection.getTransactionIsolation()` trên connection tham gia transaction.

Trong service JDBC, đối chiếu thêm bean `DataSource` của `JdbcTemplate` và manager; với JPA đối chiếu `EntityManagerFactory`. `txActive=true` có thể xuất phát từ transaction outer, nên chỉ một flag không chứng minh lời gọi đang xét đã đi qua interceptor.

### Kiểm tra lỗi theo thứ tự

1. **Caller lấy bean từ Spring?** Nếu dùng `new MyService()`, không đi qua Spring AOP proxy.
2. **Gọi qua proxy hay self-invocation?** `this.inner()` không áp dụng transaction advice của inner.
3. **Infrastructure được bật trong đúng context chưa?** `@EnableTransactionManagement`/auto-configuration phải thấy service beans.
4. **Method có transaction metadata và được proxy intercept được không?** Kiểm tra visibility, final methods/classes, interface/class-based proxies.
5. **TransactionManager có đúng không?** Một bean `@Transactional` dùng datasource A nhưng manager cho B sẽ không tự rollback A.
6. **Trong call chain có những advisors nào?** Logging, retry, async advice có thể ảnh hưởng ranh giới.
7. **Phương thức có ném exception qua proxy không?** Nếu catch trong target, interceptor có thể thấy return bình thường.
8. **Rollback rules có đúng không?** Checked/unchecked exceptions, `rollbackFor`, `noRollbackFor`.
9. **Inner có tham gia outer hay mở riêng?** `REQUIRED`, `REQUIRES_NEW` và `NESTED` khác nhau.
10. **Đã thực hiện test rollback thực tế chưa?** Thao tác ghi vào hai bảng, cố ý gây lỗi ở bước sau và đọc dữ liệu sau transaction.

## 11. Bảng so sánh những lời gọi dễ bị nhầm

| Lời gọi | Có đi qua proxy advice cho method đó? | Hệ quả giao dịch |
| --- | --- | --- |
| Bean A gọi public `@Transactional` trên bean B được Spring inject | Thông thường **có** | Interceptor áp dụng attributes của B, manager begin/join và commit/rollback scope. |
| Caller gọi `@Transactional` method trực tiếp trên proxy của bean B | **Có** khi pointcut/visibility match | Transaction advice áp dụng cho method đó. |
| Trong target B gọi `this.otherTransactionalMethod()` | **Không** cho inner method trong proxy mode | Không có boundary mới theo annotation của inner; có thể vẫn chạy trong outer transaction. |
| `new B().save()` thay cho Spring bean | **Không** | Không có Spring transaction advice. |
| Gọi method `private` có `@Transactional` | **Không** trong Spring proxy mode | Annotation riêng của method không tự tạo transaction. |
| `@Transactional` ở một `final` class với class-based proxy | Không thể dùng subclass proxy để chặn | Cần thiết kế lại interface/proxy hoặc cấu hình phù hợp. |
| Method đã bị proxy nhưng DAO mở JDBC connection khác ngoài manager | Có thể **có proxy**, nhưng DAO không tham gia resource | SQL đó không tự động nằm trong transaction của manager. |
| Inner `REQUIRED` được intercept trong outer transaction | **Có** | Có logical scope của inner nhưng thường cùng physical transaction. |
| Inner `REQUIRES_NEW` được intercept qua Spring proxy | **Có** | Tạm treo outer và bắt đầu transaction mới nếu manager hỗ trợ. |
| Method reactive trả `Mono` dùng reactive manager | **Có**, đường reactive | Transaction gắn với subscription/reactive context, không áp dụng mô hình thread-bound JDBC. |

Các cụm “thông thường”, “có thể” giữ lại những điều kiện thật sự quan trọng: Spring mode, runtime configuration, resource participation và loại manager. Không thể kết luận mọi trường hợp chỉ từ tên annotation.

## 12. Tự kiểm tra

**Câu 1.** Vì sao method `@Transactional` không cần gọi `connection.commit()`?

Vì proxy/`TransactionInterceptor` yêu cầu `TransactionManager` điều phối transaction trước và sau method invocation. Mã nghiệp vụ thực hiện thao tác dữ liệu qua tài nguyên do manager quản lý; manager chịu trách nhiệm commit/rollback.

**Câu 2.** `@Transactional` trên inner method luôn tạo transaction mới?

Không. `REQUIRED` mặc định tham gia transaction hiện có. Nếu cả outer và inner qua proxy, inner thường là logical scope bên trong cùng physical transaction; commit cuối nằm ở outer.

**Câu 3.** Outer bắt `RuntimeException` của inner rồi trả về bình thường, có luôn commit được không?

Không. Inner có thể đã đánh dấu transaction chung rollback-only; outer interceptor có thể nhận `UnexpectedRollbackException` khi cố commit.

**Câu 4.** `this.save()` có khác lời gọi `writer.save()` qua injected Spring bean?

Có. Trong proxy mode, `this.save()` bypass proxy của inner method. `writer.save()` đi vào proxy của bean `writer` nếu được Spring inject và phương thức phù hợp.

**Câu 5.** `AopUtils.isAopProxy(bean) == true` chứng minh toàn bộ methods đều transactional?

Không. Bean có AOP proxy là một bước quan sát. Phải biết advisor/pointcut match method nào và tài nguyên có tham gia transaction hay không.

**Câu 6.** Vì sao một method có `return` vẫn có thể khiến caller nhận lỗi transaction?

Vì transaction advice thực hiện commit sau khi thân method trở về. Commit có thể thất bại hoặc manager có thể rollback do rollback-only.

**Câu 7.** Vì sao `@Transactional` không bao phủ một `CompletableFuture.runAsync(...)` chỉ vì nó được tạo bên trong method?

Vì imperative transaction context dựa trên thread; không tự truyền sang thread mới. Muốn transaction ở task khác cần thiết kế boundary riêng và tránh suy luận rollback chung.

**Câu 8.** Một method trả `Mono` có được commit ngay sau khi tạo object `Mono`?

Không nên hiểu như vậy. Với reactive manager, transaction liên quan đến subscription và execution của reactive pipeline trong Reactor Context.

## 13. Checklist dùng khi code review

- [ ] Method nghiệp vụ là một Spring bean, được gọi qua proxy.
- [ ] `@EnableTransactionManagement` hoặc Spring Boot transaction auto-configuration đã kích hoạt infrastructure.
- [ ] Method/class có transaction attributes được resolution đúng.
- [ ] Proxy type và method visibility/final modifiers cho phép interception.
- [ ] `TransactionManager` phù hợp và đồng bộ với `DataSource`/`EntityManagerFactory`/`ConnectionFactory`.
- [ ] Không có self-invocation vô tình bỏ qua annotation của inner method.
- [ ] Propagation đúng ý định: join existing, new transaction hay nested savepoint.
- [ ] Exceptions cần rollback thực sự thoát qua boundary hoặc được đánh dấu rollback-only.
- [ ] Đã hiểu thứ tự advice với logging/retry/async nếu chúng cùng tồn tại.
- [ ] Reactive methods và imperative methods dùng đúng transaction infrastructure.
- [ ] Đã có integration test chứng minh cả commit và rollback trên dữ liệu thực tế.

## Tài liệu tham khảo chính thức

1. [Spring Framework — Understanding the Spring Framework's Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): proxy, advisor, `TransactionInterceptor` và vòng đời lời gọi.
2. [Spring Framework — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): bật annotation-driven transaction, proxy vs AspectJ, visibility và self-invocation.
3. [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, `REQUIRES_NEW`, `NESTED` và rollback-only.
4. [Spring Framework — `TransactionInterceptor` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/interceptor/TransactionInterceptor.html): `MethodInterceptor`/`invoke` và transaction advice.
5. [Spring Framework — `TransactionAspectSupport` Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/interceptor/TransactionAspectSupport.html): xử lý transaction quanh method và cleanup.
6. [Spring Framework — Controlling JDBC Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `JdbcTransactionManager` và cách JDBC tham gia Spring transaction.
7. [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionTemplate` và `TransactionalOperator` khi cần boundary trực tiếp bằng code.
