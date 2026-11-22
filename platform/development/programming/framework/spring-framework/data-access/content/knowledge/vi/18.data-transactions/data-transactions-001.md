# Ranh giới giao dịch bao nhiều thao tác repository trong Spring Framework

## 1. Vì sao một nghiệp vụ phải bao trùm nhiều repository?

Giả sử nghiệp vụ **chuyển 100 đơn vị tiền** từ tài khoản A sang tài khoản B cần thực hiện ba thao tác:

1. `AccountRepository` trừ 100 khỏi A.
2. `AccountRepository` cộng 100 vào B.
3. `AuditRepository` ghi nhận một dòng lịch sử chuyển tiền.

Mỗi repository có trách nhiệm truy cập dữ liệu, nhưng **cả ba thao tác cùng tạo nên một nghiệp vụ duy nhất**. Nếu bước 1 thành công mà bước 2 hoặc 3 thất bại, dữ liệu sẽ không nhất quán. Quy tắc nghiệp vụ là **hoặc cả ba thay đổi cùng được commit, hoặc toàn bộ bị rollback**.

Đây chính là ý nghĩa của **ranh giới giao dịch bao nhiều thao tác repository** (*transaction boundary spanning multiple repository operations*): Spring bắt đầu giao dịch trước khi chạy chuỗi thao tác trong một service, để các repository tham gia cùng giao dịch vật lý, rồi commit khi toàn bộ thành công hoặc rollback khi có lỗi đáp ứng quy tắc rollback.

Sơ đồ ý tưởng:

~~~text
Controller / Job / Message Handler
               |
               v
     TransferService.transfer()  <-- @Transactional, bắt đầu ranh giới
        |         |        |
        v         v        v
   AccountRepo  AccountRepo AuditRepo
   debit(A)     credit(B)   record(...)
        \         |        /
         \        |       /
          +--- cùng transaction ---+
                       |
             hoàn thành?  +-- lỗi theo rollback rule --> ROLLBACK
                 |
               COMMIT
~~~

**Điểm mấu chốt:** transaction thường là ranh giới của **một use case tại service/application layer**, không nhất thiết trùng ranh giới của một repository, một câu SQL, hoặc một HTTP request. Một repository có thể cung cấp nhiều phương thức dữ liệu độc lập; service biết phương thức nào phải hoàn thành cùng nhau.

## 2. Transaction bảo đảm điều gì?

Với một database giao dịch hỗ trợ ACID, phạm vi chung nhằm đạt:

- **Atomicity (nguyên tử):** các thay đổi trong một transaction cùng commit hoặc cùng rollback.
- **Consistency (nhất quán):** các constraint ở DB và các invariant do ứng dụng kiểm tra phải được duy trì; transaction không tự viết quy tắc nghiệp vụ thay cho bạn.
- **Isolation (cô lập):** các giao dịch đồng thời được quan sát theo isolation level của DB; không mặc định là serializable.
- **Durability (bền vững):** DB đảm bảo dữ liệu đã commit theo cơ chế lưu trữ và cấu hình của nó.

Một transaction **không tự** làm cho kiểm tra số dư, tồn kho hay uniqueness đúng trong mọi tình huống đồng thời. Vẫn có thể cần ràng buộc database, update có điều kiện, optimistic/pessimistic locking hoặc isolation phù hợp.

### Trường hợp sai: mỗi repository tự commit riêng

~~~java
// Minh họa thiết kế không có transaction chung ở tầng service.
public void transfer(long from, long to, int amount) {
    accountRepository.debit(from, amount);   // có thể commit trước
    accountRepository.credit(to, amount);    // lỗi tại đây
    auditRepository.record(from, to, amount);
}
~~~

Nếu các lời gọi tự chạy bên ngoài transaction chung với auto-commit (hoặc từng repository tự mở transaction độc lập), bước trừ tiền có thể đã được lưu vĩnh viễn trước khi bước cộng thất bại. Đặt `@Transactional` cho **service method được Spring quản lý** là cách phổ biến để các hoạt động JDBC trong cùng database tham gia một transaction.

### Trường hợp đúng: một use case, một transaction

~~~java
// Minh họa bên trong một service bean được Spring quản lý.
@Transactional
public void transfer(long from, long to, int amount) {
    accountRepository.debit(from, amount);
    accountRepository.credit(to, amount);
    auditRepository.record(from, to, amount);
}
~~~

Trong Spring transaction management dạng imperative, khi lời gọi đi **qua proxy Spring**, một `PlatformTransactionManager` phù hợp mở hoặc tham gia transaction; các repository dùng cùng nguồn tài nguyên sẽ cùng tham gia, kể cả khi chính repository **không đặt `@Transactional`**. Annotation không yêu cầu tất cả các repository đều là con của một lớp hoặc phải gọi chung một phương thức repository.

## 3. Điều kiện để nhiều repository thực sự cùng một transaction

Chỉ thêm một annotation vào mã nguồn **chưa đủ**. Cần kiểm tra đồng thời các điều kiện:

1. **Service là Spring bean** và lời gọi method đi qua transactional proxy (cấu hình `@EnableTransactionManagement`, hoặc Spring Boot cấu hình transaction phù hợp).
2. **Có `PlatformTransactionManager` đúng tài nguyên**, ví dụ `DataSourceTransactionManager`/`JdbcTransactionManager` cho JDBC trên một `DataSource`, hoặc `JpaTransactionManager` cho JPA persistence unit.
3. **Các repository tham gia tài nguyên do transaction manager quản lý**. Với `JdbcTemplate`, chúng nên dùng cùng `DataSource` liên quan đến transaction manager; `JdbcTemplate` lấy connection qua hạ tầng Spring nên tham gia thread-bound transaction.
4. **Các thao tác chạy trong ngữ cảnh transaction tương ứng**, thường cùng thread đối với JDBC/JPA kiểu imperative. Một tác vụ tự chuyển sang thread mới không mặc nhiên thừa hưởng transaction của thread gọi.
5. **Propagation cho phép tham gia**: `REQUIRED` mặc định sẽ tham gia transaction đang có; `REQUIRES_NEW` cố tình mở transaction riêng; `NOT_SUPPORTED` tạm ngưng transaction.

Ví dụ: service đã `@Transactional` và hai repository dùng hai `JdbcTemplate` được tạo từ cùng `DataSource` vẫn có thể chung transaction. Ngược lại, nếu một repository tự gọi `DriverManager.getConnection(...)`, tạo nguồn kết nối tách biệt, hoặc dùng manager khác mà không phối hợp, lời hứa “rollback tất cả” có thể thất bại.

**Một nguồn dữ liệu không đồng nghĩa mọi hệ thống trong use case được giao dịch nguyên tử.** Database, HTTP API, email, file system, Redis và message broker thường có ranh giới commit riêng; phần 11 trình bày cách phối hợp.

## 4. Cách Spring mở, liên kết và kết thúc transaction

Với `@Transactional` và `Propagation.REQUIRED` mặc định:

1. Client gọi **proxy** của `TransferService.transfer(...)`.
2. `TransactionInterceptor` tìm metadata của `@Transactional`.
3. `PlatformTransactionManager` bắt đầu transaction nếu chưa có hoặc tham gia transaction đang chạy.
4. Phần thân method gọi các repository; trong JDBC, `DataSourceTransactionManager` quản lý/bind connection với thread, còn Spring JDBC lấy connection phù hợp qua `DataSourceUtils`.
5. Method trả về bình thường: interceptor yêu cầu commit (nếu sở hữu transaction thực sự).
6. Method ném exception thỏa rollback rule: interceptor rollback hoặc đánh dấu transaction chung là **rollback-only**; exception tiếp tục đi ra cho caller xử lý.

Ví dụ trạng thái thời gian:

~~~text
t0: caller --> transactional proxy
t1: BEGIN TRANSACTION
t2: UPDATE account SET balance = balance - 100 ...
t3: UPDATE account SET balance = balance + 100 ...
t4: INSERT INTO transfer_audit ...
t5: COMMIT   (hoặc ROLLBACK khi lỗi)
t6: trả về caller
~~~

Nhiều repository **không nhất thiết làm nhiều lần BEGIN/COMMIT**. Với cùng tài nguyên và `REQUIRED`, chúng chia sẻ một transaction vật lý, dù có thể có nhiều transaction scope logic khi phương thức ở tầng trong cũng được đánh dấu `@Transactional`.

Một method bình thường gọi ba repository trong một `@Transactional` service chỉ có **một** ranh giới bao bên ngoài. Không cần mở thêm transaction thủ công trong từng repository.

## 5. Ví dụ Java 17+ độc lập: chuyển tiền qua hai repository

Ví dụ thực hành chạy không cần Spring Boot: tạo một database H2 in-memory, đăng ký Spring beans bằng Java configuration, bật transaction, tạo bảng, chuyển tiền thành công, sau đó mô phỏng lỗi **sau khi cả ba repository đã ghi**. Khi lỗi xảy ra, Spring rollback toàn bộ ba thay đổi của lần gọi thứ hai.

Cấu trúc project:

~~~text
spring-multi-repository-transaction/
├── pom.xml
└── src/main/java/demo/TransferDemo.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-multi-repository-transaction</artifactId>
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
                <version>3.14.0</version>
                <artifactId>maven-compiler-plugin</artifactId>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**`src/main/java/demo/TransferDemo.java`**

~~~java
package demo;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;

public class TransferDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            jdbc.execute("""
                    CREATE TABLE account (
                        id BIGINT PRIMARY KEY,
                        balance INTEGER NOT NULL
                    )
                    """);
            jdbc.execute("""
                    CREATE TABLE transfer_audit (
                        id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                        from_id BIGINT NOT NULL,
                        to_id BIGINT NOT NULL,
                        amount INTEGER NOT NULL
                    )
                    """);

            jdbc.update("INSERT INTO account(id, balance) VALUES (?, ?)",
                    1L, 500);
            jdbc.update("INSERT INTO account(id, balance) VALUES (?, ?)",
                    2L, 200);

            // Lấy bean từ context để đi qua transactional proxy.
            TransferService service = context.getBean(TransferService.class);

            service.transfer(1L, 2L, 100, false);
            System.out.println("afterSuccess=" + balances(jdbc));
            System.out.println("auditAfterSuccess=" + auditCount(jdbc));

            try {
                service.transfer(1L, 2L, 50, true);
            } catch (IllegalStateException expected) {
                System.out.println("failedOperationRolledBack=true");
            }

            System.out.println("afterRollback=" + balances(jdbc));
            System.out.println("auditAfterRollback=" + auditCount(jdbc));
        }
    }

    private static java.util.List<Integer> balances(JdbcTemplate jdbc) {
        return jdbc.queryForList(
                "SELECT balance FROM account ORDER BY id", Integer.class);
    }

    private static Integer auditCount(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM transfer_audit", Integer.class);
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class AppConfig {
        @Bean
        public DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:transfer_example;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new DataSourceTransactionManager(dataSource);
        }

        @Bean
        public AccountRepository accountRepository(JdbcTemplate jdbc) {
            return new AccountRepository(jdbc);
        }

        @Bean
        public AuditRepository auditRepository(JdbcTemplate jdbc) {
            return new AuditRepository(jdbc);
        }

        @Bean
        public TransferService transferService(
                AccountRepository accounts, AuditRepository audits) {
            return new TransferService(accounts, audits);
        }
    }

    public static class AccountRepository {
        private final JdbcTemplate jdbc;

        public AccountRepository(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        public void debit(long accountId, int amount) {
            int count = jdbc.update("""
                    UPDATE account
                    SET balance = balance - ?
                    WHERE id = ? AND balance >= ?
                    """, amount, accountId, amount);

            if (count != 1) {
                throw new IllegalStateException(
                        "Account does not exist or has insufficient funds");
            }
        }

        public void credit(long accountId, int amount) {
            int count = jdbc.update("""
                    UPDATE account
                    SET balance = balance + ?
                    WHERE id = ?
                    """, amount, accountId);

            if (count != 1) {
                throw new IllegalStateException("Target account not found");
            }
        }
    }

    public static class AuditRepository {
        private final JdbcTemplate jdbc;

        public AuditRepository(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        public void record(long from, long to, int amount) {
            jdbc.update("""
                    INSERT INTO transfer_audit (from_id, to_id, amount)
                    VALUES (?, ?, ?)
                    """, from, to, amount);
        }
    }

    public static class TransferService {
        private final AccountRepository accounts;
        private final AuditRepository audits;

        public TransferService(
                AccountRepository accounts, AuditRepository audits) {
            this.accounts = accounts;
            this.audits = audits;
        }

        @Transactional
        public void transfer(
                long from, long to, int amount, boolean failAfterWriting) {
            if (amount <= 0 || from == to) {
                throw new IllegalArgumentException("Invalid transfer");
            }

            accounts.debit(from, amount);
            accounts.credit(to, amount);
            audits.record(from, to, amount);

            if (failAfterWriting) {
                throw new IllegalStateException("Simulated business failure");
            }
        }
    }
}
~~~

Chạy tại thư mục chứa `pom.xml` với JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java "-Dexec.mainClass=demo.TransferDemo"
~~~

**Đầu ra mong đợi cho H2 in-memory mới:**

~~~text
afterSuccess=[400, 300]
auditAfterSuccess=1
failedOperationRolledBack=true
afterRollback=[400, 300]
auditAfterRollback=1
~~~

### Giải thích kết quả từng lần gọi

**Lần 1, thành công:**

- Tài khoản 1: `500 - 100 = 400`.
- Tài khoản 2: `200 + 100 = 300`.
- Có một dòng audit được insert.
- Service trở về bình thường, transaction manager commit cả ba thay đổi.

**Lần 2, cố ý thất bại:**

- Trong transaction thứ hai, code thử trừ thêm 50, cộng thêm 50 và ghi thêm một audit.
- Sau cùng code ném `IllegalStateException` — một `RuntimeException` đáp ứng rollback mặc định.
- Spring rollback **cả** phần ghi account và audit của lần thứ hai. Vì vậy số dư vẫn `[400, 300]`, số dòng audit vẫn `1`.
- Câu `catch` trong `main` nằm **bên ngoài** service proxy, sau khi Spring đã xử lý rollback. Việc caller bắt exception lúc đó không làm commit lại giao dịch thất bại.

Ví dụ cố ý không dùng `@Transactional` trên hai repository: chúng được đăng ký thành Spring bean và sử dụng cùng `JdbcTemplate` lấy từ cùng `DataSource`, nên tự động sử dụng connection được manager gắn cho transaction hiện hành. Khi gỡ `@Transactional` ở service, các thao tác độc lập có thể auto-commit; khi đó phép thử rollback sẽ không còn cho kết quả bảo toàn như trên.

**Giới hạn của ví dụ:** mô phỏng đơn giản trên H2 chứng minh cách ghép repository và rollback. Trong hệ tiền thật còn phải xử lý số dư vượt phạm vi, isolation/locking, idempotency, retry, audit bất biến và các ràng buộc khác.

## 6. Đặt `@Transactional` ở đâu?

Thông thường chọn **method public của application/service layer** đại diện cho một thao tác nghiệp vụ nhất quán:

~~~java
// Một method nghiệp vụ, các repository là thành phần cộng tác.
@Transactional
public OrderId placeOrder(PlaceOrderCommand command) {
    Order order = orderRepository.create(command);
    inventoryRepository.reserve(command.items());
    paymentRecordRepository.recordPending(order.id());
    return order.id();
}
~~~

Đây là **đoạn phác họa kiến trúc**: các type/method giả định đã có trong ứng dụng, không phải file Java độc lập. Với các ràng buộc dữ liệu phù hợp, transaction bao việc tạo order, giữ hàng và ghi nhận trạng thái thanh toán trong cùng database. **Nó không tự bao một lần thu tiền thực tế ở cổng thanh toán bên ngoài**.

### Ranh giới quá nhỏ

Nếu mỗi repository method tự `@Transactional` và service không có transaction bao ngoài:

~~~text
placeOrder() không có transaction chung
  -> orderRepository.create()      : BEGIN, COMMIT
  -> inventoryRepository.reserve() : BEGIN, ROLLBACK (lỗi)
  -> paymentRecordRepository...    : không chạy
~~~

Kết quả có thể là order đã lưu nhưng inventory chưa được giữ. Một transaction độc lập tại mỗi repository **không thay thế** transaction ở tầng service.

### Ranh giới quá lớn

Không nhất thiết đặt `@Transactional` lên toàn bộ controller hay giữ transaction mở trong suốt:

- Gọi HTTP API mất vài giây.
- Chờ người dùng hoặc đọc file lớn.
- Gửi email hoặc xử lý CPU dài.
- Chờ message broker xác nhận.

Transaction dài giữ connection/lock và làm giảm throughput, tăng nguy cơ deadlock, timeout hoặc cạn connection pool. Nên gom **đúng phần truy cập dữ liệu cần nguyên tử**, chuyển external effects sang cơ chế phù hợp sau commit hoặc outbox.

### Một service gọi nhiều service

Transaction có thể bao nhiều service/repository nếu method service bên ngoài có transaction và các lời gọi đồng bộ đi vào bean Spring cùng transaction manager, `REQUIRED`. Không có luật “một transaction chỉ được qua một lớp service”. Điều quyết định là propagation, tài nguyên và cách gọi proxy.

## 7. Rollback: exception, catch và các tình huống khó

### Quy tắc mặc định

Với `@Transactional` của Spring, mặc định:

- `RuntimeException` và `Error` thoát ra transactional method → rollback.
- **Checked exception** (ví dụ `IOException`) thoát ra → mặc định **không** kích hoạt rollback, trừ khi cấu hình quy tắc phù hợp.
- Khi method trả về bình thường → framework cố commit, trừ khi transaction đã được đánh dấu rollback-only hoặc thất bại ở bước commit.

Dùng quy tắc tường minh cho checked exception của nghiệp vụ:

~~~java
// Minh họa trong một Spring-managed service.
@Transactional(rollbackFor = java.io.IOException.class)
public void importData() throws java.io.IOException {
    repository.savePartOne();
    repository.savePartTwo();
    remoteFileReader.readRequiredData(); // có thể ném IOException
}
~~~

Đoạn này không phải chương trình chạy độc lập; các repository và reader là thành phần giả định. Nên cân nhắc đọc/kiểm tra file **trước** khi bắt đầu transaction để tránh giữ transaction mở trong khi I/O chậm. `rollbackFor` minh họa đúng cơ chế rollback khi exception checked buộc phải nằm trong scope.

### Bắt rồi nuốt exception bên trong transaction

~~~java
@Transactional
public void process() {
    repository.saveA();
    try {
        repository.saveB();
    } catch (IllegalStateException ex) {
        // Nuốt lỗi rồi kết thúc method bình thường:
        // transaction có thể commit A nếu chưa bị mark rollback-only.
    }
}
~~~

Nếu lỗi chỉ là exception nghiệp vụ tự ném và không có inner transaction đánh dấu rollback, Spring nhìn thấy method trả về bình thường và có thể commit `saveA()`. Nếu lỗi đến từ một inner `@Transactional(REQUIRED)` đã đánh dấu transaction chung rollback-only, outer vẫn không thể commit; khi outer yêu cầu commit, Spring có thể ném `UnexpectedRollbackException`.

Cách xử lý an toàn: **để exception thoát ra** khi muốn rollback toàn bộ; hoặc tái ném sau khi xử lý; hoặc nếu có lý do phải trả kết quả mà vẫn rollback, chủ động đánh dấu rollback-only qua transaction infrastructure. Đừng giả định `catch` sẽ khiến DB rollback hay “hủy lỗi” của transaction.

### `setRollbackOnly()` khi thực sự cần

~~~java
// Đoạn minh họa chỉ dùng khi đang có Spring-managed transaction.
org.springframework.transaction.interceptor.TransactionAspectSupport
        .currentTransactionStatus()
        .setRollbackOnly();
~~~

Cách này kết dính logic với Spring; chỉ sử dụng có chủ đích khi không thể để exception đi ra ngoài. Tái thiết kế luồng trả lỗi thường dễ đọc hơn.

### Checked exception và Spring Framework 6.2

Từ Spring 6.2 có thể thay đổi mặc định rollback rộng hơn bằng cấu hình `@EnableTransactionManagement(rollbackOn = ALL_EXCEPTIONS)` khi ứng dụng chọn dùng quy tắc này. Không giả định toàn bộ dự án đều bật. Với ví dụ và kiến thức nền, mặc định vẫn là rollback cho `RuntimeException`/`Error`; dùng `rollbackFor` ở method nếu cần hành vi cụ thể, độc lập với cấu hình toàn cục.

## 8. Propagation quyết định ranh giới thật

Khi một method đã trong transaction gọi một method khác cũng có `@Transactional`, thuộc tính `propagation` quyết định method bên trong tham gia hay tách khỏi transaction:

| Propagation | Hành vi khi đã có transaction ngoài | Ảnh hưởng với use case nhiều repository |
|---|---|---|
| `REQUIRED` (mặc định) | Tham gia cùng **physical transaction**, tạo scope logic riêng | Lựa chọn mặc định cho một nghiệp vụ cần rollback chung |
| `REQUIRES_NEW` | Tạm đình chỉ transaction ngoài, mở **physical transaction mới** | Inner có thể commit độc lập, phá yêu cầu all-or-nothing nếu dùng sai |
| `NESTED` | Dùng savepoint trong **cùng** physical transaction khi manager/driver hỗ trợ | Có thể rollback một đoạn về savepoint rồi cho outer tiếp tục |
| `SUPPORTS` | Có transaction thì tham gia; không có thì chạy không transaction | Dễ thiếu bảo đảm khi caller quên mở transaction |
| `MANDATORY` | Bắt buộc đã có transaction, nếu không báo lỗi | Hữu ích nếu một service chỉ được gọi trong workflow có transaction |
| `NOT_SUPPORTED` | Tạm ngưng transaction đang có, thực thi không transaction | Không phù hợp cho bước ghi bắt buộc phải rollback cùng phần còn lại |
| `NEVER` | Có transaction thì báo lỗi | Dùng cho logic yêu cầu luôn chạy ngoài transaction |

### `REQUIRED`: nhiều scope logic, một transaction vật lý

~~~text
Service.placeOrder()  @Transactional(REQUIRED) --> BEGIN
  RepoA.save()        @Transactional(REQUIRED) --> JOIN
  RepoB.reserve()     @Transactional(REQUIRED) --> JOIN
Service kết thúc bình thường                --> COMMIT 1 lần
~~~

Ngay cả khi `RepoB.reserve()` có annotation riêng, với `REQUIRED` nó thường tham gia transaction hiện hành. Các tham số isolation/timeout/readOnly riêng của method tham gia có thể không đổi được transaction ngoài đang hoạt động; giá trị thực tế do scope tạo transaction quyết định. Có thể cấu hình manager để kiểm tra xung đột thuộc tính.

### `REQUIRES_NEW`: transaction độc lập

Nếu `AuditService.record()` mang `@Transactional(propagation = Propagation.REQUIRES_NEW)` và được gọi **qua proxy của bean khác**, audit có thể commit riêng ngay cả khi transaction chuyển tiền sau đó rollback. Điều này chỉ hợp lý khi nghiệp vụ **thực sự muốn** audit tồn tại độc lập (ví dụ một số loại log lỗi), và không muốn audit là thành phần phải rollback chung.

`REQUIRES_NEW` thường cần connection thứ hai trong khi connection của outer transaction vẫn được giữ. Với connection pool nhỏ hoặc tải cao, lạm dụng có thể gây cạn pool, lock contention hoặc deadlock. Cũng phải hiểu transaction độc lập không nhìn thấy mọi dữ liệu chưa commit từ outer, tùy isolation.

### `NESTED`: savepoint, không phải transaction độc lập

Với JDBC và `DataSourceTransactionManager` hỗ trợ savepoint, `NESTED` có thể rollback một phần về savepoint; transaction vật lý ngoài vẫn quyết định commit cuối cùng. Không giả định nó hoạt động tương đương trong mọi JPA/JTA manager hoặc mọi driver.

**Lựa chọn thực tế:** nếu đề bài là “ba repository phải cùng thành công hoặc cùng thất bại”, hãy bắt đầu bằng một service `@Transactional` mặc định `REQUIRED`, chỉ đổi propagation khi có lý do được kiểm thử.

## 9. Các bẫy proxy làm `@Transactional` không hoạt động như tưởng

### Tự gọi method trong cùng instance (*self-invocation*)

~~~java
// Mô tả một Spring bean; không phải chương trình độc lập.
public void processOrder() {
    this.saveOrder(); // không đi qua transactional proxy
}

@Transactional
public void saveOrder() {
    repository.save();
}
~~~

Với Spring AOP **proxy mode** mặc định, `this.saveOrder()` không đi qua proxy; annotation của `saveOrder()` **không tự mở transaction**. Nếu `processOrder()` đã chạy trong transaction hợp lệ, lệnh bên trong vẫn tham gia transaction đó do context sẵn có; vấn đề là annotation trên method tự gọi không được interceptor áp dụng.

Cách rõ ràng: đặt `@Transactional` tại method entry point được bean khác gọi qua proxy; hoặc chuyển chức năng cần propagation riêng sang bean Spring khác và gọi qua bean đó. Không mặc định dùng `AopContext.currentProxy()` hay tự inject bản thân để sửa một thiết kế sai ranh giới.

### Tự khởi tạo bằng `new` hoặc gọi method không được proxy chặn

`new TransferService(...)` tự tạo ngoài Spring container không có transactional proxy. `@Transactional` là metadata; không phải từ khóa Java tự sinh transaction. Với JDK interface proxy, method cần thuộc interface proxied và public. Với class-based proxy, điều kiện visibility có thể khác theo phiên bản Spring; `private` và `final` không thể được override để interceptor thực hiện như một lời gọi public bình thường.

Không dựa vào `@Transactional` trong constructor hay `@PostConstruct` vì proxy có thể chưa hoạt động. Ưu tiên method public của Spring bean được gọi từ component khác.

### Bất đồng transaction manager / datasource

Ví dụ một repository dùng `DataSource` của DB A, repository kia dùng DB B và `@Transactional` chỉ trỏ manager của DB A. Kết quả không phải tự động distributed transaction. Hãy xác định manager nào quản lý từng tài nguyên; nếu cần phối hợp atomic nhiều tài nguyên, cân nhắc JTA/XA khi hạ tầng thực sự hỗ trợ, hoặc thiết kế consistency theo event/saga.

### Chuyển thread hoặc reactive context

Imperative transaction qua `PlatformTransactionManager` thường gắn vào thread hiện tại. `CompletableFuture.supplyAsync(...)`, `@Async`, thread pool hoặc task scheduler không mặc nhiên mang transaction JDBC từ thread cha qua. Bản thân một `@Transactional` trên method trả async type cũng không biến mọi bước bất đồng bộ thành cùng JDBC transaction.

Với R2DBC/reactive stack, Spring sử dụng `ReactiveTransactionManager` và Reactor context, là mô hình khác. Đừng trộn hai ngữ cảnh rồi giả định mọi repository cùng một giao dịch.

## 10. Isolation, locking và tính đúng khi chạy đồng thời

Ranh giới transaction giải quyết **atomicity**, còn hai request đồng thời có thể tạo race condition tùy isolation và SQL.

Ví dụ sai:

~~~text
T1: SELECT stock = 1
T2: SELECT stock = 1
T1: UPDATE stock = 0, commit
T2: UPDATE stock = 0, commit
Kết quả: cả hai request tưởng đã bán được một món duy nhất.
~~~

Chỉ đặt `@Transactional` quanh cả hai lời gọi chưa chắc loại bỏ lỗi này dưới isolation mặc định. Có thể dùng một UPDATE nguyên tử với điều kiện:

~~~sql
UPDATE inventory
SET available = available - 1
WHERE product_id = ? AND available >= 1;
~~~

Sau đó kiểm tra `updateCount == 1`; nếu 0 thì hết hàng/không có sản phẩm và phải kết thúc nghiệp vụ phù hợp. Với nghiệp vụ đọc–sửa–ghi phức tạp, cân nhắc optimistic locking theo version hoặc pessimistic row lock, và thiết lập `@Transactional(isolation = Isolation.SERIALIZABLE)` khi được DB/driver hỗ trợ và hiệu năng chấp nhận. Không áp dụng isolation cao theo thói quen cho mọi method.

**Read-only:** `@Transactional(readOnly = true)` chủ yếu là một gợi ý tối ưu cho hạ tầng quản lý transaction/persistence; tùy database và manager có thể có giới hạn thực thi. Không coi nó là bảo đảm kiểm soát quyền ghi tuyệt đối.

**Timeout:** `@Transactional(timeout = 10)` yêu cầu timeout 10 giây theo khả năng của manager và các operation được áp dụng; không mặc định rằng mọi HTTP request, thread hoặc I/O chậm sẽ bị cưỡng bức dừng đúng 10 giây. Tránh mở transaction trước công việc không liên quan DB.

**Retry:** deadlock, serialization failure hoặc transient connection error đôi khi cần retry **toàn bộ use case từ ngoài transaction đã thất bại**, thay vì retry từng SQL riêng lẻ bên trong transaction có trạng thái không còn dùng được. Thiết kế idempotency và giới hạn số lần retry để tránh ghi đôi khi một bước đã commit.

## 11. Khi một nghiệp vụ còn gọi hệ thống ngoài database

Một transaction JDBC cho `orderRepository` và `inventoryRepository` **không rollback được email đã gửi hoặc HTTP payment request đã thành công**:

~~~text
@Transactional placeOrder()
  INSERT order                 (DB transaction)
  UPDATE inventory             (DB transaction)
  HTTP charge payment gateway  (hệ thống bên ngoài, commit riêng)
  INSERT payment_record        (DB transaction)
  DB COMMIT / ROLLBACK
~~~

Nếu INSERT cuối thất bại, DB rollback nhưng gateway có thể đã thu tiền. Giữ giao dịch DB mở trong khi gọi gateway còn gây lock/timeout.

Các cách tiếp cận tùy yêu cầu:

- **Transactional outbox:** trong **cùng transaction DB**, cập nhật order và ghi một sự kiện outbox; sau commit, worker riêng xuất bản sự kiện với cơ chế retry và deduplication. Dữ liệu order và “ý định phát sự kiện” commit hoặc rollback cùng nhau.
- **After-commit event:** chạy side effect sau commit thông qua callback/event listener phù hợp; tránh phát sự kiện trước khi biết chắc DB đã commit. Tuy nhiên callback riêng không tự mang lại bảo đảm gửi thành công sau crash; outbox cần thiết khi muốn độ tin cậy cao.
- **Saga/compensating action:** chuỗi nhiều dịch vụ/DB độc lập dùng các bước và nghiệp vụ bù trừ; không giả định một `@Transactional` local bao được tất cả.
- **Idempotency key:** khi retry API/payment/event, nhận diện request lặp để tránh trừ tiền hoặc phát sinh order hai lần.

Cần xác định đúng “nguyên tử” đang nói đến: **các repository cùng database và manager** có thể nằm trong transaction local; nhiều service hoặc hạ tầng ngoài thường cần giao thức/phối hợp khác.

## 12. TransactionTemplate khi cần ranh giới lập trình tường minh

`@Transactional` là cách declarative phổ biến. Khi cần kiểm soát rõ scope trong một luồng hoặc tránh bẫy self-invocation, có thể dùng `TransactionTemplate` từ Spring:

~~~java
// Đoạn minh họa, giả sử template được inject và repositories có sẵn.
transactionTemplate.execute(status -> {
    accountRepository.debit(fromId, amount);
    accountRepository.credit(toId, amount);
    auditRepository.record(fromId, toId, amount);
    return null;
});
~~~

`TransactionTemplate` gọi transaction manager, thực thi callback và commit/rollback theo logic của nó; mặc định nó dùng propagation `REQUIRED`. Callback ném `RuntimeException` thường làm transaction rollback. Có thể `status.setRollbackOnly()` khi chủ động hủy transaction mà không ném exception.

**Không** tự tạo `new TransactionTemplate(new DataSourceTransactionManager(otherDataSource))` mỗi lần khi ứng dụng đã có manager với tài nguyên khác: điều này có thể phá ranh giới transaction dự kiến. Nên inject manager/template được cấu hình đúng và giữ giao dịch trong service.

## 13. Kiểm thử đúng ranh giới, thay vì chỉ kiểm tra từng repository

Một bộ integration test hữu ích phải xác nhận trạng thái database **sau khi transaction của service đã kết thúc**:

1. **Happy path:** debit, credit, audit cùng xuất hiện và số lượng mỗi thao tác hợp lệ.
2. **Lỗi ở repository đầu/giữa/cuối:** cố ý tạo lỗi sau mỗi bước và xác minh **không** tồn tại cập nhật nửa chừng.
3. **Constraint:** trùng khóa, tồn kho âm, tài khoản không tồn tại; exception được propagate hoặc rollback đúng quy tắc.
4. **Checked exception:** kiểm tra rõ mặc định commit/rollback và `rollbackFor` nếu cần.
5. **Inner transaction:** có `REQUIRED` đánh dấu rollback-only, `REQUIRES_NEW` độc lập, `NESTED` savepoint nếu thiết kế dùng.
6. **Concurrency:** chạy hai thao tác tranh chấp trên cùng dữ liệu, kiểm tra lock/isolation và optimistic version.
7. **Đúng cấu hình:** test qua bean lấy từ Spring context, sử dụng đúng manager/DataSource và transaction proxy; test trực tiếp đối tượng tạo bằng `new` không đủ.

**Bẫy kiểm thử:** nếu bản thân test được đánh dấu `@Transactional` và test framework tự rollback cuối test, bạn có thể vô tình khiến nhiều lời gọi service “dính” chung một transaction test. Điều đó không chứng minh service có ranh giới độc lập hay commit đúng trong production. Khi xác minh hành vi commit/rollback thực, hãy chọn kiểm thử không có outer test transaction hoặc chủ động kết thúc/kiểm tra transaction tại đúng thời điểm.

Ví dụ assertion cho `TransferDemo`:

~~~text
Ban đầu:       balance(A)=500, balance(B)=200, audit=0
Sau thành công:balance(A)=400, balance(B)=300, audit=1
Sau lỗi giả lập:balance(A)=400, balance(B)=300, audit=1
~~~

Số dư không đổi sau lỗi lần hai chính là dấu hiệu toàn bộ thao tác trong scope thứ hai đã rollback; **nó không kiểm tra được tất cả các failure mode của driver/DB production**. Phải thử lại trên database thực tế khi quyết định isolation, pooling và XA.

## 14. Những lỗi thường gặp

| Dấu hiệu | Nguyên nhân phổ biến | Cách xác minh và khắc phục |
|---|---|---|
| Repository đầu đã commit, repository sau thất bại | `@Transactional` chỉ có ở từng repo, service không mở transaction chung | Đặt boundary tại service public method; test lỗi ở bước cuối |
| Annotation không có tác dụng | Bean bị tạo bằng `new`, self-invocation, method không được proxy | Lấy bean từ Spring, gọi qua proxy, kiểm thử rollback |
| `UnexpectedRollbackException` lúc kết thúc | Inner `REQUIRED` đã mark rollback-only nhưng outer vẫn cố commit | Xem exception gốc và transaction log; xác định lại cách xử lý lỗi |
| Audit vẫn được lưu khi chuyển tiền rollback | Audit dùng `REQUIRES_NEW` hoặc DB/manager riêng | Dùng `REQUIRED` nếu cần rollback cùng; hoặc công nhận audit độc lập có chủ đích |
| DB A rollback còn DB B vẫn commit | Chỉ dùng transaction manager local của DB A | Dùng phối hợp phù hợp (JTA/XA hoặc saga/outbox) |
| Checked exception nhưng dữ liệu vẫn commit | Rollback rule mặc định không bao checked exception | Dùng `rollbackFor`, hoặc cấu hình default rollback phù hợp |
| Service nuốt exception và commit một phần | `catch` giữ lỗi lại, không đánh dấu rollback | Rethrow hoặc setRollbackOnly khi phù hợp |
| Thao tác async không tham gia transaction | Transaction imperative gắn theo thread | Đặt transaction riêng rõ ràng trong worker/task hoặc thiết kế outbox |
| Transaction kéo dài/cạn connection | Gọi HTTP, xử lý tệp hoặc giữ lock trong scope | Thu hẹp scope; chuyển side effects sang sau commit |
| Dữ liệu bất nhất khi nhiều request | Isolation/locking hoặc SQL không bảo toàn invariant | Conditional update, versioning, locking, unique constraint |
| Integration test “qua” nhưng production sai | Test nằm trong outer transaction hoặc dùng H2 khác DB thực | Test qua proxy và trên DB production với committed state |

## 15. Checklist thiết kế một use case với nhiều repository

Trước khi viết code, trả lời lần lượt:

1. **Nghiệp vụ nào phải all-or-nothing?** Ví dụ chuyển tiền = debit + credit + audit; xác định những thay đổi thực sự phải commit cùng nhau.
2. **Ranh giới ở đâu?** Một method service public, được bean khác gọi qua Spring proxy, thường là điểm bắt đầu tốt.
3. **Tài nguyên nào tham gia?** Cùng database, `DataSource`, `EntityManager` và transaction manager nào? Có external API hoặc broker nằm ngoài phạm vi local không?
4. **Propagation nào?** Mặc định `REQUIRED`; dùng `REQUIRES_NEW` chỉ khi thực sự muốn độc lập; đừng vô tình tách audit/stock ra khỏi use case.
5. **Thất bại nào phải rollback?** Runtime, checked exception, lỗi nghiệp vụ, exception bị bắt; định nghĩa rollback rule và hành vi trả lỗi.
6. **Concurrency được bảo vệ ra sao?** Conditional SQL, khóa unique, lock/version, isolation thích hợp và retry cả use case.
7. **Có việc chậm hoặc side effect ngoài DB không?** Đưa ra ngoài scope hoặc dùng outbox/after-commit để tránh giữ transaction lâu.
8. **Đã test trạng thái commit và rollback chưa?** Kiểm thử qua Spring bean, lỗi ở từng bước, transaction ngoài/nested nếu có và DB production.

## 16. Bài tập tự thực hành

1. Trong `TransferDemo`, bỏ `@Transactional` khỏi `TransferService.transfer`. Dự đoán và xác minh số dư cùng audit sau lần gọi ném exception; giải thích vì sao transaction chung không còn.
2. Đổi thứ tự thao tác để ném lỗi sau `accounts.debit` nhưng trước `accounts.credit`. Viết assertion cho tất cả account/audit để chứng minh rollback đúng.
3. Tạo một `AuditService` khác có `@Transactional(REQUIRES_NEW)`, gọi qua bean proxy, rồi cho outer transaction rollback. So sánh audit còn tồn tại với yêu cầu nghiệp vụ.
4. Thêm một checked exception tự khai báo, thử `@Transactional` mặc định và `@Transactional(rollbackFor = ...)`; đối chiếu DB sau mỗi lần.
5. Cho `transfer` gọi một method `@Transactional` khác bằng `this.method()` và so sánh với lời gọi qua bean Spring riêng; trình bày tác động của self-invocation.
6. Viết integration test có hai request chuyển tiền đồng thời từ cùng account với số dư giới hạn. Đảm bảo tổng tiền không âm và chỉ những giao dịch hợp lệ được commit.

## Tài liệu tham khảo

- Spring Framework Reference — Declarative Transactions, Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework Reference — Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework Reference — Rolling Back a Declarative Transaction: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework Reference — Transaction Management Strategies: https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html
- Spring Framework Reference — Programmatic Transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework Reference — JDBC Transaction Manager: https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html
