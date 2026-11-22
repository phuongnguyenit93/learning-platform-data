# Đặt ranh giới giao dịch ở thao tác nghiệp vụ phù hợp

> **Mục tiêu:** Xác định nơi mở và kết thúc database transaction theo một thao tác nghiệp vụ (use case), để các thay đổi liên quan thành công hoặc thất bại cùng nhau; giữ transaction đủ ngắn; hiểu chính xác cách `@Transactional` của Spring Framework hoạt động và kiểm chứng rollback, commit, cạnh tranh đồng thời.

## 1. Ranh giới giao dịch là một quyết định thiết kế nghiệp vụ

**Database transaction** là một đơn vị làm việc với cơ sở dữ liệu: khi commit, các thay đổi thuộc transaction được xác nhận; khi rollback, chúng bị hủy theo khả năng giao dịch của database và tài nguyên đang tham gia. Các tính chất ACID gồm atomicity, consistency, isolation và durability. Transaction giải quyết tính nhất quán **trong phạm vi tài nguyên mà transaction manager thực sự quản lý**; nó không tự bao phủ HTTP call, email, message broker hay database độc lập khác.

**Thao tác nghiệp vụ (business operation/use case)** là một hành động có ý nghĩa đối với người dùng và quy tắc nghiệp vụ, ví dụ “chuyển tiền”, “xác nhận đơn hàng”, “hủy đặt chỗ”. Một thao tác có thể đọc/ghi nhiều bảng qua nhiều repository. Ranh giới transaction phù hợp thường bao lấy **những thay đổi cơ sở dữ liệu phải cùng thành công hoặc cùng thất bại để giữ bất biến nghiệp vụ**.

Ví dụ thao tác chuyển 100.000 đồng từ tài khoản A sang B (bỏ qua các yếu tố thanh toán thực tế):

1. Kiểm tra A, B và điều kiện chuyển.
2. Trừ tiền A.
3. Cộng tiền B.
4. Lưu bản ghi chuyển tiền.

Nếu bước 2 commit riêng, sau đó bước 3 lỗi, tiền ở A đã mất nhưng B chưa nhận. Vì vậy **bước 2–4 phải nằm trong cùng một transaction** với kiểm tra số dư/đồng thời phù hợp. Ngược lại, gửi email thông báo có thể diễn ra *sau commit*; để email nằm trong transaction không làm thao tác gửi email có khả năng rollback.

Một số khái niệm không nên đánh đồng:

| Khái niệm | Ý nghĩa | Phạm vi ví dụ |
| --- | --- | --- |
| **Use case** | Hành vi nghiệp vụ và điều kiện thành công | `transferMoney`, `placeOrder` |
| **Transaction boundary** | Nơi bắt đầu, tham gia, commit/rollback database transaction | `@Transactional` trên phương thức service |
| **Repository/DAO method** | Một thao tác truy cập dữ liệu | `debit`, `credit`, `insertLog` |
| **HTTP request** | Vòng đời giao tiếp với client | Nhận input → service → tạo response |
| **Long-running workflow** | Chuỗi bước kéo dài, có thể qua nhiều hệ thống | Thanh toán → kho → giao hàng |

**Không mặc định một HTTP request = một transaction**, cũng không mặc định “mỗi câu SQL/repository method = một transaction”. Chọn ranh giới theo điều kiện nhất quán cần giữ.

## 2. Nguyên tắc thiết kế: một thao tác nghiệp vụ, một điểm điều phối transaction

Trong ứng dụng Spring nhiều tầng, cách tổ chức thường rõ ràng nhất là:

```text
Controller / Job / Message Handler
    | kiểm tra cú pháp request, xác thực, chuyển DTO
    v
Application Service / Use-case Service
    | @Transactional trên phương thức thao tác nghiệp vụ
    | điều phối nhiều DAO/Repository
    +--------------------+-------------------+
    v                    v                   v
  AccountDao         OrderRepository     AuditRepository
    |                    |                   |
    +--------------------+-------------------+
                     |
            Cùng transaction manager
            và tài nguyên DB tham gia
                     |
                 Commit/Rollback
```

- **Controller** nên giữ mỏng, không ôm transaction khi đang đọc request body, serialize response hay gọi network.
- **Application service** biết toàn bộ các bước cần atomic. Đặt `@Transactional` ở *public entry point* của use case, thường tại service này, để mọi lời gọi data access bên trong cùng tham gia transaction.
- **Repository/DAO** chỉ tập trung câu lệnh/mapping dữ liệu. Annotation trên repository riêng lẻ có thể hữu ích, nhưng *không thay thế* transaction bao trùm use case có nhiều repository.
- **Domain object** giữ quy tắc bất biến; không cần biết cách Spring mở/đóng transaction. Domain validation và database constraint bổ trợ nhau.
- Một service có thể có nhiều phương thức use case với chính sách khác nhau (ghi, đọc, hoặc workflow có nhiều giai đoạn); không nên phủ `@Transactional` cho mọi phương thức chỉ vì “dễ”.

### Cách suy ra ranh giới từ yêu cầu

Đặt bốn câu hỏi trước khi annotate:

1. **Bất biến nào cần đúng?** Ví dụ `balance >= 0` và “ghi cả debit/credit/log hoặc không ghi gì”.
2. **Các thay đổi nào phải atomic?** Chỉ những lệnh SQL vào cùng database, hay còn một API bên ngoài? Nếu có API bên ngoài, cần thiết kế thêm cơ chế phối hợp.
3. **Thời gian giữ khóa/connection dự kiến?** Nếu có HTTP call, retry, tính toán lớn hoặc chờ người dùng, hãy tách khỏi transaction ngắn.
4. **Ai là entry point thật sự?** HTTP controller, scheduled job, message listener… phải gọi một **Spring bean qua proxy** để transaction advice có cơ hội chạy.

Bắt đầu bằng `Propagation.REQUIRED` mặc định cho use case đồng bộ trong một datasource. Chỉ tăng độ phức tạp khi có yêu cầu đo được.

## 3. Ranh giới đặt sai và đúng: chuyển tiền

### Sai: ba thao tác được commit độc lập

```java
// Minh họa lỗi thiết kế; không phải chương trình chạy độc lập.
public void transfer(long from, long to, long cents) {
    accountDao.debit(from, cents);    // Có thể đã commit
    accountDao.credit(to, cents);     // Lỗi tại đây thì sao?
    transferDao.save(from, to, cents);
}
```

Nếu không có một transaction bao ngoài, từng thao tác JDBC có thể chạy ở auto-commit hoặc repository có thể khởi tạo transaction riêng. Một bước lỗi không tự hủy những bước đã commit. Gắn `@Transactional` vào từng hàm `debit`, `credit`, `save` **không** tạo ra một transaction cho toàn use case.

### Đúng: transaction bao quanh các bước phải atomic

```java
@Service
public class TransferService {
    private final AccountDao accountDao;
    private final TransferDao transferDao;

    public TransferService(AccountDao accountDao, TransferDao transferDao) {
        this.accountDao = accountDao;
        this.transferDao = transferDao;
    }

    @Transactional
    public void transfer(long from, long to, long cents) {
        // Validate + khóa/đồng bộ dữ liệu thích hợp cho concurrency.
        accountDao.ensureTransferAllowed(from, to, cents);
        accountDao.debit(from, cents);
        accountDao.credit(to, cents);
        transferDao.save(from, to, cents);
    }
}
```

Đoạn trên là **minh họa kiến trúc**, không phải class biên dịch độc lập: các phương thức `ensureTransferAllowed`, `debit`, `credit` và `save` là API giả định của các DAO. Bản chạy được trong mục 5 có đầy đủ SQL, kiểm tra dữ liệu và mô phỏng lỗi rollback.

Khi lời gọi đi qua Spring transactional proxy, `TransactionInterceptor` dùng `PlatformTransactionManager` để mở hoặc tham gia transaction trước khi chạy thân phương thức; sau đó commit khi thành công hoặc rollback theo chính sách exception. Với JDBC và cùng `DataSource`, `JdbcTemplate` lấy connection đang gắn với transaction, nên các DAO dùng cùng một phạm vi làm việc.

**Điểm tinh tế:** transaction mở lúc proxy nhận lời gọi `transfer()` và kết thúc khi lời gọi trả về/throw qua proxy. Thêm annotation vào một private helper hoặc gọi annotated method bằng `this.someMethod()` trong cùng object không đảm bảo tạo transaction như mong đợi.

## 4. Khi nào nên mở, khi nào nên kết thúc?

| Tình huống | Ranh giới hợp lý | Giải thích |
| --- | --- | --- |
| Tạo đơn và trừ tồn kho trong cùng DB | Use case `placeOrder` bọc các câu ghi phải atomic | Không được có đơn “đã đặt” mà tồn kho chưa cập nhật theo quy tắc |
| Cập nhật hồ sơ ở một bảng | Có thể dùng transaction mức use case; một lệnh SQL đơn lẻ cũng atomic theo DB | Đừng mở transaction rộng hơn nhu cầu |
| Đọc một báo cáo với nhiều truy vấn cần snapshot nhất quán | Transaction chỉ đọc với isolation phù hợp, nếu nghiệp vụ thực sự đòi snapshot | `readOnly` riêng lẻ không tự tạo snapshot mong muốn |
| Lấy dữ liệu DB rồi gọi REST API chậm | Hoàn tất DB transaction trước network call khi có thể | Giữ khóa/connection trong lúc chờ mạng gây contention, timeout |
| Nhận tiền từ cổng thanh toán, sau đó ghi DB | Phân chia bước cục bộ và phối hợp bằng idempotency, trạng thái/saga/outbox | DB rollback không hoàn tác được thanh toán bên ngoài |
| Xử lý một batch 50.000 bản ghi | Chia lô có điểm resume và chiến lược rollback được định nghĩa | Một transaction khổng lồ gây log/lock/memory pressure |
| Gửi notification sau khi đơn commit | Event sau commit; cần bảo đảm giao hàng thì dùng transactional outbox | Email/message không tham gia ACID của database |

**Transaction đủ rộng để giữ bất biến, nhưng đủ ngắn để giảm thời gian giữ lock và connection.** Không tự động kéo transaction qua toàn bộ request hay cả workflow nhiều phút.

## 5. Ví dụ hoàn chỉnh chạy được với Spring JDBC và H2

Ví dụ sử dụng **Java 17+, Maven, Spring Boot 3.5.16, Spring Framework transaction, JdbcTemplate và H2**. Không dùng Spring Data JPA để tập trung vào ranh giới transaction; nguyên tắc đặt `@Transactional` tại use-case service vẫn áp dụng khi dùng JPA.

Cấu trúc thư mục:

```text
transaction-boundary/
├── pom.xml
└── src/main/
    ├── java/com/example/tx/
    │   ├── DemoApplication.java
    │   ├── AccountDao.java
    │   └── TransferService.java
    └── resources/
        ├── application.properties
        ├── schema.sql
        └── data.sql
```

**`pom.xml`** — Starter JDBC cung cấp `JdbcTemplate` và tích hợp transaction; H2 là database nhúng để chạy thử:

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
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>transaction-boundary</artifactId>
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

**`src/main/resources/schema.sql`** — số tiền được biểu diễn bằng đơn vị nhỏ nhất (ở đây là số nguyên cents cho mục đích minh họa), có constraint không âm:

```sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    balance_cents BIGINT NOT NULL CHECK (balance_cents >= 0)
);

CREATE TABLE transfer_log (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    from_id BIGINT NOT NULL,
    to_id BIGINT NOT NULL,
    amount_cents BIGINT NOT NULL CHECK (amount_cents > 0)
);
```

**`src/main/resources/data.sql`**:

```sql
INSERT INTO accounts (id, balance_cents) VALUES (1, 100000);
INSERT INTO accounts (id, balance_cents) VALUES (2, 50000);
```

**`src/main/resources/application.properties`**:

```properties
spring.datasource.url=jdbc:h2:mem:txdemo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
```

Spring Boot nạp `schema.sql`/`data.sql` khi khởi tạo datasource; dữ liệu demo chỉ ở bộ nhớ, được khởi tạo lại khi chạy ứng dụng mới. Dùng migration tool, database thật và thiết kế tài khoản đầy đủ nếu đưa ý tưởng vào production.

**`src/main/java/com/example/tx/AccountDao.java`** — thao tác SQL đơn giản; không tự mở transaction riêng:

```java
package com.example.tx;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class AccountDao {
    private final JdbcTemplate jdbc;

    public AccountDao(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public long lockedBalance(long id) {
        Long balance = jdbc.queryForObject(
                "SELECT balance_cents FROM accounts WHERE id = ? FOR UPDATE",
                Long.class, id);
        if (balance == null) {
            throw new IllegalStateException("Missing account: " + id);
        }
        return balance;
    }

    public void changeBalance(long id, long delta) {
        int updated = jdbc.update(
                "UPDATE accounts SET balance_cents = balance_cents + ? " +
                "WHERE id = ?",
                delta, id);
        if (updated != 1) {
            throw new IllegalStateException("Missing account: " + id);
        }
    }

    public void recordTransfer(long fromId, long toId, long cents) {
        jdbc.update(
                "INSERT INTO transfer_log (from_id, to_id, amount_cents) " +
                "VALUES (?, ?, ?)",
                fromId, toId, cents);
    }

    public long balance(long id) {
        Long value = jdbc.queryForObject(
                "SELECT balance_cents FROM accounts WHERE id = ?",
                Long.class, id);
        if (value == null) {
            throw new IllegalStateException("Missing account: " + id);
        }
        return value;
    }

    public int transferCount() {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM transfer_log", Integer.class);
        return count == null ? 0 : count;
    }
}
```

**`src/main/java/com/example/tx/TransferService.java`** — một transaction cho cả debit, credit, và log; thứ tự khóa ổn định giảm khả năng deadlock khi hai transaction chuyển ngược chiều:

```java
package com.example.tx;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    private final AccountDao accounts;

    public TransferService(AccountDao accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public void transfer(long fromId, long toId,
                         long amountCents, boolean simulateFailure) {
        if (fromId == toId || amountCents <= 0) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        // Lock theo thứ tự ID tăng dần để tránh đảo thứ tự khóa.
        long firstId = Math.min(fromId, toId);
        long secondId = Math.max(fromId, toId);
        long firstBalance = accounts.lockedBalance(firstId);
        long secondBalance = accounts.lockedBalance(secondId);

        long fromBalance = fromId == firstId
                ? firstBalance : secondBalance;
        if (fromBalance < amountCents) {
            throw new IllegalArgumentException("Insufficient balance");
        }

        accounts.changeBalance(fromId, -amountCents);

        // Cờ mô phỏng lỗi chỉ có trong bài thực hành.
        if (simulateFailure) {
            throw new IllegalStateException("Simulated failure");
        }

        accounts.changeBalance(toId, amountCents);
        accounts.recordTransfer(fromId, toId, amountCents);
    }
}
```

`SELECT ... FOR UPDATE` khóa các hàng tài khoản trong transaction đang chạy. Kiểm tra số dư và ghi sau khi đã khóa giúp tránh hai lệnh chuyển đồng thời cùng tiêu số dư đã cũ. Với database thực tế phải xác minh mức isolation, cú pháp locking, tính công bằng và chiến lược retry deadlock. Thứ tự khóa nhất quán **giảm nguy cơ**, không bảo đảm tuyệt đối không deadlock.

**`src/main/java/com/example/tx/DemoApplication.java`** — gọi service bean từ một bean khác để đi qua transaction proxy; đọc trạng thái sau khi lời gọi kết thúc:

```java
package com.example.tx;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(TransferService service, AccountDao accounts) {
        return args -> {
            try {
                service.transfer(1L, 2L, 10000L, true);
            } catch (IllegalStateException expected) {
                System.out.println(
                        "rollback: " + accounts.balance(1L) + "," +
                        accounts.balance(2L) + "; log=" +
                        accounts.transferCount());
            }

            service.transfer(1L, 2L, 10000L, false);
            System.out.println(
                    "committed: " + accounts.balance(1L) + "," +
                    accounts.balance(2L) + "; log=" +
                    accounts.transferCount());
        };
    }
}
```

Chạy từ thư mục dự án có `pom.xml`, với JDK 17+ và Maven đã cài:

```bash
mvn spring-boot:run
```

Trong log có **hai dòng do ứng dụng in**, không tính các dòng khởi động của Spring:

```text
rollback: 100000,50000; log=0
committed: 90000,60000; log=1
```

**Giải thích từng bước:**

1. Lượt đầu khởi tạo transaction, khóa hai hàng, trừ A rồi cố tình ném `IllegalStateException`. Exception unchecked đi ra khỏi phương thức service, proxy rollback; A/B/log giữ nguyên.
2. Lượt thứ hai thực hiện cả ba lệnh SQL, trở về bình thường; proxy commit một lần cho cả thao tác. A giảm 10.000, B tăng 10.000, log tăng một bản ghi.
3. Nếu bỏ `@Transactional` trên `transfer()`, một lệnh UPDATE JDBC có thể auto-commit trước khi lỗi mô phỏng; đó chính là thiết kế sai mà bài này cần tránh.

Ví dụ này đã kiểm tra đường đi của transaction **trong cùng H2 datasource**. Nó không phải thiết kế ngân hàng production: thiếu khóa idempotency nghiệp vụ, xác thực quyền, chống trùng yêu cầu, ledger hai bút toán chuẩn, truy vết, xử lý số tiền rất lớn, retry an toàn và kiểm chứng với database thật.

## 6. Spring thực sự mở và đóng transaction như thế nào?

`@Transactional` là **metadata** cho Spring AOP. Trong mô hình imperative, interceptor dùng `PlatformTransactionManager` (ví dụ `JdbcTransactionManager`/`DataSourceTransactionManager` với JDBC hoặc `JpaTransactionManager` với JPA) để quản lý tài nguyên. Mặc định cho annotation:

| Thuộc tính | Mặc định | Ý nghĩa thực tế |
| --- | --- | --- |
| `propagation` | `REQUIRED` | Không có transaction thì mở; nếu đã có transaction phù hợp thì tham gia |
| `isolation` | `DEFAULT` | Theo mức mặc định của database/manager |
| `readOnly` | `false` | Giao dịch đọc/ghi |
| `timeout` | Theo transaction manager | Không phải lúc nào cũng có timeout hiệu lực |
| Rollback | `RuntimeException` và `Error` | Checked exception mặc định không yêu cầu rollback |

Diễn tiến điển hình:

```text
Caller --> Spring proxy --> TransactionInterceptor
                                 |
                            begin / join
                                 |
                            service body
                                 |
                       +---------+----------+
                       |                    |
                    return            throw exception
                       |                    |
                   commit             rollback rules
                       |                    |
                       +---------+----------+
                                 |
                           Caller nhận kết quả
```

**Điều kiện quan trọng:** Spring phải quản lý object dưới dạng bean, transaction management phải được bật và phải có transaction manager phù hợp. Với Spring Boot JDBC/JPA được cấu hình đúng và một datasource, phần hạ tầng thường được auto-configure; ngoài Boot có thể cần `@EnableTransactionManagement` cùng transaction manager bean.

### Vì sao không đặt annotation tùy tiện?

- **Self-invocation:** `this.transfer()` hoặc một phương thức trong cùng bean gọi một annotated method khác không đi qua proxy ở cấu hình proxy mặc định. Cách rõ ràng là để bean A gọi public method annotated của bean B.
- **Tự tạo object:** `new TransferService(…)` không đi qua Spring container, nên annotation không được Spring interceptor xử lý.
- **Private/final method:** khả năng interception phụ thuộc proxy; để an toàn, chọn **public method trên Spring-managed service** và gọi từ bean khác. Tránh đánh dấu private helper rồi tưởng đã có transaction.
- **Khởi tạo bean:** không dựa vào `@Transactional` cho lời gọi trong constructor hoặc `@PostConstruct`; proxy chưa sẵn sàng cho những đường gọi này.
- **Thread khác:** transaction JDBC/JPA thông thường gắn với thread hiện tại; `new Thread`, `@Async`, executor không tự kế thừa transaction. Reactive transaction lại được truyền trong Reactor context, cần thiết kế khác.
- **Trên Controller:** dễ giữ transaction quá lâu qua xử lý web, remote call, serialization. Service-level use case thường là điểm vào ổn định hơn cho HTTP, job và message listener.

## 7. Propagation quyết định transaction được chia sẻ hay tách riêng

Một method A có `@Transactional` gọi method B của **Spring bean khác** có annotation:

| Propagation của B | B làm gì khi A đã có transaction? | Khi nào cân nhắc |
| --- | --- | --- |
| `REQUIRED` (mặc định) | B cùng tham gia **physical transaction** của A; mọi bước atomic với A | Các repository/service con cùng một use case |
| `REQUIRES_NEW` | Tạm treo transaction A, bắt đầu **physical transaction độc lập** cho B | Trường hợp hiếm cần commit/rollback một bước độc lập có chủ đích |
| `NESTED` | Dùng savepoint trong cùng physical transaction khi manager/driver hỗ trợ | Rollback một phần với JDBC savepoint và đặc tả rõ |
| `MANDATORY` | Bắt buộc caller đã có transaction, nếu không báo lỗi | Bảo vệ một API nội bộ chỉ được gọi trong transaction |
| `SUPPORTS` | Có transaction thì tham gia, không có thì chạy ngoài transaction | Đọc tùy ngữ cảnh; thường không làm ranh giới chính |

**Không chọn `REQUIRES_NEW` chỉ để “chắc chắn có transaction”.** Nó có thể commit dữ liệu B dù A rollback; ngoài ra transaction ngoài vẫn giữ connection/tài nguyên, còn transaction trong cần connection mới, dẫn tới cạn pool. `NESTED` không đồng nghĩa một commit độc lập: savepoint rollback một phần vẫn nằm trong transaction ngoài.

Một bẫy khác: method B dùng `REQUIRED` cùng transaction A, rồi B đánh dấu **rollback-only**. Dù A bắt exception và cố commit, Spring có thể ném `UnexpectedRollbackException` vì transaction thực tế đã rollback. Đây là tín hiệu đúng để caller không tưởng nhầm dữ liệu đã được commit.

## 8. Exception và rollback phải phản ánh quy tắc nghiệp vụ

Mặc định Spring rollback với `RuntimeException` hoặc `Error`; checked exception như `IOException` thường **không** kích hoạt rollback trong cấu hình mặc định. Ví dụ exception checked phải hủy mọi thay đổi:

```java
// Minh họa trong một Spring-managed service; không phải file độc lập.
@Transactional(rollbackFor = IOException.class)
public void importAndSave(Path path) throws IOException {
    // Đọc file; nếu việc đọc thất bại sau khi đã ghi database,
    // IOException thoát ra sẽ yêu cầu rollback.
}
```

Nếu quy tắc nghiệp vụ định nghĩa *không* rollback với một lỗi đặc biệt, có thể dùng `noRollbackFor` một cách có chủ đích. Đừng lạm dụng `rollbackFor = Exception.class` hoặc `noRollbackFor` để che thiết kế thao tác nghiệp vụ.

**Bẫy nuốt exception:**

```java
@Transactional
public void placeOrder() {
    stockDao.reserve();
    try {
        orderDao.save();
    } catch (Exception ex) {
        log.warn("Cannot save order", ex); // Nếu chỉ log rồi return,
                                           // transaction có thể commit!
    }
}
```

Đây là mã **minh họa sai**: nếu không có cơ chế khác đánh dấu rollback-only, proxy thấy method trả về bình thường và có thể commit phần `reserve()`. Khi thất bại phải rollback toàn bộ, hãy để exception thích hợp thoát ra; trường hợp buộc phải xử lý tại chỗ thì cần cơ chế rollback-only có chủ đích và hiểu hậu quả.

Ngoài ra:

- Exception được ném **sau commit** không thể hoàn tác transaction đã kết thúc.
- Catch ở **controller, bên ngoài lời gọi service transactional** vẫn cho phép proxy xử lý rollback trước khi controller bắt exception.
- `@Transactional(readOnly = true)` là **hint**, không phải quyền database bảo đảm cấm ghi. Dùng nó cho các thao tác đọc phù hợp, nhưng vẫn cần quyền DB và ràng buộc nếu muốn ngăn ghi.
- Với Spring Framework 6.2+, có thể cấu hình mặc định rollback cho mọi exception bằng `@EnableTransactionManagement(rollbackOn = ALL_EXCEPTIONS)`. Nếu áp dụng quy tắc khác mặc định, phải thống nhất toàn dự án và kiểm thử tác động.

## 9. Transaction không tự giải quyết cạnh tranh đồng thời

Atomicity không thay thế isolation. Hai giao dịch cùng nhìn thấy số dư/tồn kho trước khi một transaction hoàn tất có thể gây lost update, overdraft hoặc oversell nếu thiếu cơ chế phù hợp.

**Ba công cụ thường gặp:**

1. **Database constraint:** `CHECK (balance_cents >= 0)`, `UNIQUE` cho idempotency key, foreign key cho tính toàn vẹn. Đây là lớp bảo vệ cuối cùng, vẫn cần logic ứng dụng xử lý lỗi.
2. **Pessimistic locking:** `SELECT ... FOR UPDATE` hoặc `@Lock(PESSIMISTIC_WRITE)` khi dùng JPA; khóa hàng trong transaction và kiểm tra lại điều kiện trước khi sửa. Giữ transaction ngắn, khóa theo thứ tự nhất quán.
3. **Optimistic locking:** `@Version` trên JPA entity, hay conditional update kiểu `UPDATE ... WHERE version = ?`; nếu xung đột, báo lỗi hoặc retry *toàn bộ thao tác* khi bảo đảm an toàn/idempotent.

Ví dụ bán sản phẩm không nên chỉ thực hiện “SELECT stock” rồi sau đó “UPDATE stock” trong hai transaction tách rời. Một cách kiểm soát cạnh tranh bằng SQL:

```sql
UPDATE products
SET stock = stock - :quantity
WHERE id = :productId
  AND stock >= :quantity;
```

Sau lệnh UPDATE phải kiểm tra số hàng bị ảnh hưởng: `1` là giữ hàng thành công, `0` là hết hàng/không có sản phẩm hoặc điều kiện không thỏa. Đây là ví dụ SQL **dạng named parameters** cho `NamedParameterJdbcTemplate`; không phải statement copy nguyên xi vào JDBC positional parameters. Nếu use case còn ghi order và reservation log, vẫn cần transaction bao quanh tất cả các thay đổi này.

**Isolation** như READ COMMITTED, REPEATABLE READ hoặc SERIALIZABLE có tác dụng khác nhau theo database. Không tăng isolation lên cao nhất theo thói quen; hãy chứng minh anomaly cần ngăn và đo chi phí lock, retry, throughput. Các thuộc tính isolation/timeout của inner `REQUIRED` thường không thay thế được thiết lập của outer transaction đã tồn tại.

## 10. Đừng giữ database transaction qua bước bên ngoài database

**Không nên làm:**

```java
@Transactional
public void checkout() {
    orderDao.createPendingOrder();
    paymentGateway.chargeCard();    // Network có thể mất nhiều giây.
    orderDao.markPaid();
    emailClient.sendReceipt();       // Email không rollback cùng DB.
}
```

Mã trên là **minh họa một thiết kế rủi ro**, với DAO/client giả định. Khi payment đã thành công ở hệ thống ngoài nhưng `markPaid()` hoặc commit DB thất bại, rollback không hoàn lại thanh toán. Đồng thời transaction giữ connection/lock khi chờ cổng thanh toán/email.

Tách *local transaction* khỏi *distributed workflow* bằng các bước có trạng thái:

1. Ghi đơn `PENDING` và mã yêu cầu/idempotency key vào DB trong một local transaction ngắn.
2. Gọi payment gateway ngoài transaction hoặc thông qua worker; sử dụng idempotency key để retry an toàn theo API gateway.
3. Nhận kết quả/webhook, mở **transaction mới** để chuyển trạng thái đơn bằng điều kiện hợp lệ và ghi sự kiện/outbox.
4. Phát thông báo từ outbox bằng worker sau commit, với retry và deduplication.

**Transactional outbox** lưu event record cùng transaction với trạng thái nghiệp vụ trong *cùng DB*, nên hoặc cả state lẫn event tồn tại, hoặc cả hai rollback. Worker xuất event sau đó; consumer cần idempotent vì phát có thể lặp. `@TransactionalEventListener(phase = AFTER_COMMIT)` phù hợp cho side effect không cần bảo đảm giao hàng mạnh, nhưng **không** tự tạo hàng đợi bền vững: process crash sau commit vẫn có thể làm mất notification.

Với nhiều database, message broker hoặc microservice, một annotation `@Transactional` thông thường **không tạo giao dịch ACID xuyên hệ thống**. Thiết kế saga, compensation, outbox/inbox hoặc distributed transaction khi thật sự có hạ tầng và yêu cầu tương ứng.

## 11. Những lỗi phổ biến khi chọn ranh giới

1. **Chỉ annotate từng repository:** mỗi lời gọi riêng an toàn nhưng toàn use case có thể commit một phần.
2. **Annotate toàn controller/request:** transaction dài, giữ connection/lock khi chờ mạng hoặc render response.
3. **Annotate private method/self-call:** proxy không chạy transaction advice như kỳ vọng.
4. **Catch exception và return thành công:** phần dữ liệu đã ghi có thể commit; caller tưởng use case thành công.
5. **Cho rằng checked exception mặc định rollback:** phải cấu hình rollback rule hoặc chính sách mặc định dự án.
6. **Dùng `REQUIRES_NEW` vô điều kiện:** vô tình tạo commit độc lập và làm cạn connection pool.
7. **Dùng `readOnly` như biện pháp bảo mật:** nó chỉ là hint, không thay thế phân quyền DB.
8. **Đọc rồi ghi không khóa/phiên bản:** có thể race dù đã có transaction; cần constraint, locking hay optimistic concurrency.
9. **Thao tác DB rồi gửi HTTP/email trong transaction:** độ trễ cao, side effect không rollback được.
10. **Cho rằng một database transaction bao hết nhiều datasource:** transaction manager phải thực sự quản lý các tài nguyên liên quan; local manager không đồng bộ nhiều hệ thống.
11. **Bài test tự annotate `@Transactional` rồi tưởng đã kiểm tra commit:** transaction của test thường rollback khi test kết thúc, có thể che lỗi ranh giới thật ở production.
12. **Đặt một transaction cho batch khổng lồ:** khó retry, giữ khóa lâu; thiết kế checkpoint/idempotency và transaction theo lô khi hợp lý.

## 12. Kiểm chứng bằng test và quan sát production

Một thiết kế đúng cần xác nhận bằng lỗi có chủ đích và dữ liệu thật, không chỉ nhìn annotation:

- **Happy path:** toàn bộ thay đổi use case được commit, kết quả phù hợp số dư, tồn kho hoặc trạng thái đơn.
- **Failure giữa chừng:** sau thao tác thứ nhất, chủ động ném unchecked exception; xác nhận *tất cả* bảng liên quan vẫn như trước và bản ghi audit/outbox dự kiến cũng rollback.
- **Checked exception:** test rõ chính sách rollback/commit đã chọn, đặc biệt nếu có `rollbackFor`.
- **Concurrency:** dùng nhiều transaction độc lập thực sự, gây xung đột cùng tài nguyên; xác nhận constraint/locking hoặc retry cho kết quả hợp lệ.
- **Không có transaction:** nếu code cần transaction bắt buộc, kiểm tra nơi gọi qua proxy; test trực tiếp service thật qua Spring container.
- **Remote side effect:** mô phỏng timeout/payment success nhưng DB commit fail; xác nhận idempotency, reconciliation và compensation.
- **Quan sát:** log SQL và transaction ở môi trường test; đo thời gian giao dịch, connection pool wait, deadlock, lock timeout; phân biệt lỗi DB với lỗi remote.

Khi integration test dùng `@SpringBootTest`, tránh để `@Transactional` trên chính test vô tình bọc các lời gọi vào một transaction ngoài và che hành vi commit của service. Có thể dùng test không annotate transaction, reset dữ liệu có chủ đích trước từng test và kiểm tra trạng thái database **sau khi service method kết thúc**. Với các bug isolation, dùng database engine gần production; H2 chỉ phù hợp demo nền tảng.

## 13. Checklist ngắn trước khi đặt `@Transactional`

- [ ] Tôi định nghĩa được **bất biến nghiệp vụ** và bước nào phải all-or-nothing.
- [ ] Ranh giới nằm ở **entry point của use case** do Spring quản lý và được gọi qua proxy.
- [ ] Các thao tác JDBC/JPA liên quan dùng transaction manager và datasource phù hợp.
- [ ] Transaction không ôm I/O mạng, chờ người dùng hoặc xử lý CPU dài không cần thiết.
- [ ] Rollback rule cho checked/unchecked exception khớp quy tắc nghiệp vụ; không nuốt lỗi.
- [ ] Có cơ chế bảo vệ race condition (constraint/lock/version/idempotency) theo yêu cầu.
- [ ] Tôi hiểu hậu quả của propagation; đặc biệt `REQUIRES_NEW` khác `REQUIRED`.
- [ ] Side effect ngoài DB được xử lý sau commit/outbox/saga phù hợp.
- [ ] Có test rollback giữa chừng, commit thành công và cạnh tranh đồng thời.

## 14. Tự kiểm tra

**Câu 1:** Một use case tạo `Order`, giảm `Stock` và ghi `OrderEvent` vào cùng DB. Annotation nên ở đâu?  
**Đáp án:** thường tại public service method điều phối cả ba bước; event nếu dùng outbox phải ghi trong cùng transaction.

**Câu 2:** Service `@Transactional` gọi API gửi email rồi ném `RuntimeException`. Email có bị rollback không?  
**Đáp án:** không; database transaction không hoàn tác giao thức email. Cần xử lý event/notification sau commit, hoặc outbox nếu cần bền vững.

**Câu 3:** A.`method1()` gọi `this.method2()`; `method2` được annotate `@Transactional`. Có chắc transaction mở không?  
**Đáp án:** không ở proxy mode mặc định; lời gọi nội bộ bỏ qua proxy. Đặt annotation ở public entry point thực, hoặc chuyển method giao dịch sang bean khác.

**Câu 4:** A và B dùng `REQUIRED`. B đánh dấu rollback-only, A bắt lỗi rồi trả thành công. Có chắc commit không?  
**Đáp án:** không; cùng physical transaction đã bị đánh dấu rollback-only, và Spring có thể báo `UnexpectedRollbackException` ở outer boundary.

**Câu 5:** Hai request đồng thời trừ tồn kho bằng cách SELECT trước rồi UPDATE sau. Chỉ thêm `@Transactional` có hết oversell?  
**Đáp án:** chưa chắc; phải kiểm soát concurrency bằng locking/conditional UPDATE, version hoặc mức isolation phù hợp và constraint.

## Tài liệu tham khảo chính thức

- Spring Framework — Declarative Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html
- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — Rolling Back a Declarative Transaction: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Boot — Database Initialization: https://docs.spring.io/spring-boot/how-to/data-initialization.html
- Spring Boot 3.5 — SQL Databases: https://docs.spring.io/spring-boot/3.5/reference/data/sql.html

**Ghi nhớ:** “Một use case cần nhất quán” thường có **một transaction cục bộ bao các thay đổi DB phải atomic**, mở tại **application service**, đóng sớm khi xong công việc dữ liệu. Đồng thời phải thiết kế **concurrency, rollback rule, propagation và side effect ngoài DB**; `@Transactional` một mình không giải quyết các yếu tố đó.