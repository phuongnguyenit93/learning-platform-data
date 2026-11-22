# Quản lý giao dịch khai báo và quản lý bằng mã trong Spring Framework

## 1. Mục tiêu và bối cảnh

Sau bài này, bạn có thể: xác định ranh giới giao dịch (transaction boundary) cho một use case; triển khai giao dịch khai báo bằng `@Transactional`; triển khai giao dịch bằng mã qua `TransactionTemplate` hoặc `PlatformTransactionManager`; giải thích commit/rollback, propagation, vai trò proxy/AOP; và chọn cách phù hợp dựa vào nhu cầu nghiệp vụ.

Giả sử chuyển 20 đơn vị tiền từ tài khoản A sang B. Hệ thống phải **trừ A và cộng B cùng thành công, hoặc cả hai đều không có hiệu lực**. Nếu bước cộng B lỗi sau khi trừ A, transaction phải rollback. Một transaction đảm bảo tính nguyên tử đối với tài nguyên dữ liệu **thực sự được quản lý trong transaction đó**; gọi HTTP, gửi email, publish message sang hệ thống ngoài không tự được rollback bởi annotation.

Spring hỗ trợ hai cách chỉ định điểm bắt đầu và kết thúc giao dịch:

- **Khai báo (declarative):** mô tả chính sách giao dịch trên phương thức/lớp, thường dùng `@Transactional`. Spring AOP và transaction interceptor áp dụng chính sách khi phương thức được gọi qua proxy.
- **Bằng mã (programmatic):** bao trực tiếp đoạn xử lý trong `TransactionTemplate` hoặc gọi `PlatformTransactionManager` để tự kiểm soát scope. Hữu ích khi giao dịch chỉ bao trùm một đoạn ngắn, ranh giới phụ thuộc nhánh xử lý hoặc cần điều phối tường minh.

Cả hai đều dựa trên transaction manager; khác nhau ở **cách thể hiện ranh giới**, không phải hai cơ chế lưu trữ khác nhau.

## 2. Hạ tầng giao dịch của Spring

| Thành phần | Vai trò |
| --- | --- |
| `PlatformTransactionManager` | Điều phối get transaction/commit/rollback trong luồng xử lý đồng bộ JDBC/JPA. |
| `ReactiveTransactionManager` | Điều phối transaction cho pipeline reactive, gắn context thay vì ThreadLocal. |
| `TransactionDefinition` | Chính sách: propagation, isolation, timeout, read-only. |
| `TransactionStatus` | Trạng thái transaction; có thể đánh dấu `setRollbackOnly()`. |
| `TransactionInterceptor` | AOP advice thực thi transaction policy khai báo quanh method call. |
| `TransactionTemplate` | API callback che giấu mã begin/commit/rollback lặp lại. |

Tùy technology, transaction manager có thể là `JdbcTransactionManager`/`DataSourceTransactionManager` cho JDBC, `JpaTransactionManager` cho JPA hoặc loại khác. Có một bean manager phù hợp và để các thao tác truy cập dữ liệu tham gia đúng tài nguyên transaction là điều kiện thiết yếu. Không nên mặc định hai datasource hoặc một database và một API bên ngoài cùng được bao phủ bởi một local transaction.

Chu trình đồng bộ khi một caller gọi service có transaction:

```text
Caller
  -> Boundary (proxy @Transactional hoặc TransactionTemplate)
     -> Chọn transaction manager
     -> Mở transaction mới hoặc tham gia transaction hiện có
     -> Thao tác dữ liệu A; thao tác dữ liệu B
     -> Thành công: commit nếu boundary sở hữu transaction
     -> Lỗi theo rollback rule / rollback-only: rollback
  -> Trả kết quả hoặc ném ngoại lệ tới caller
```

## 3. Quản lý khai báo với `@Transactional`

### 3.1. Khai báo và cơ chế proxy

Trong Java, annotation thường được đặt trên service bean chứa một đơn vị nghiệp vụ. Ví dụ này dùng bảng `accounts(id, balance)`, một `JdbcTemplate` và transaction manager đã cấu hình; các khai báo import được ghi đầy đủ:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountService {
    private final JdbcTemplate jdbc;

    public AccountService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(long from, long to, int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }

        int debited = jdbc.update(
            "UPDATE accounts SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, from, amount
        );
        if (debited != 1) {
            throw new IllegalStateException("Insufficient funds");
        }

        int credited = jdbc.update(
            "UPDATE accounts SET balance = balance + ? WHERE id = ?",
            amount, to
        );
        if (credited != 1) {
            throw new IllegalStateException("Destination not found");
        }
    }
}
```

Đây là **lớp minh họa**, chưa phải ứng dụng độc lập; mục 6 có project chạy trọn vẹn. Khi method `transfer` được gọi **qua Spring bean proxy**, `TransactionInterceptor` lựa chọn transaction manager, bắt đầu hoặc tham gia transaction, gọi body và quyết định kết thúc. Nếu câu lệnh cộng B lỗi với `RuntimeException`, phần trừ A được rollback. Nên đặt transaction boundary ở entry point nghiệp vụ (service/use case), không đặt từng thao tác nhỏ thành những transaction rời nhau.

Với Spring Framework thuần, kích hoạt annotation-driven transaction management bằng `@EnableTransactionManagement` trên `@Configuration` hoặc `<tx:annotation-driven/>` trong XML. Spring Boot thường tự cấu hình nếu có manager/dependencies phù hợp. Bản thân annotation chỉ là **metadata**: tự tạo object bằng `new` hoặc thiếu hạ tầng transaction sẽ không khiến annotation có tác dụng.

Giao dịch **khai báo cũng có thể cấu hình bằng XML**, ví dụ `<tx:advice>` kết hợp AOP pointcut đặt quy tắc theo method name. Khi code Java được quyền gắn annotation, `@Transactional` thường dễ đọc hơn; XML hữu ích khi không sửa được mã nguồn hoặc muốn chính sách ngoài lớp.

### 3.2. Các thuộc tính quan trọng

| Thuộc tính | Ý nghĩa/mặc định thông thường |
| --- | --- |
| `propagation` | `REQUIRED`: tham gia transaction hiện tại hoặc mở mới nếu chưa có. |
| `isolation` | `DEFAULT`, do database/manager quyết định. |
| `readOnly` | `false`; `true` thường là **hint tối ưu**, không phải cơ chế bắt buộc cấm ghi. |
| `timeout` | Dùng thời hạn tính theo giây nếu được manager hỗ trợ; mặc định theo transaction system. |
| `rollbackFor`, `noRollbackFor` | Bổ sung ngoại lệ cần/không cần rollback. |
| `transactionManager` | Chọn bean manager khi có nhiều manager. |

Ví dụ cấu hình chính sách có chủ đích, đặt trên một phương thức trong Spring bean:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.READ_COMMITTED,
    timeout = 10,
    rollbackFor = IOException.class
)
public void importOrders() throws IOException {
    // Các câu lệnh JDBC/JPA thuộc một use case.
}
```

Đoạn trên là **phương thức minh họa**, cần import `java.io.IOException` và các kiểu `org.springframework.transaction.annotation.Transactional`, `Propagation`, `Isolation`. Các khai báo isolation/timeout/read-only của inner `REQUIRED` không tự thay đổi transaction đã được outer tạo trước đó; transaction manager và database còn quyết định khả năng hỗ trợ thực tế.

**Rollback mặc định của `@Transactional`:** unchecked `RuntimeException` và `Error` làm rollback; checked `Exception` (ví dụ `IOException`) thường không làm rollback nếu không có rule thêm. Dùng `rollbackFor` để chỉ rõ. Từ Spring Framework 6.2 có tùy chọn chính sách rollback mặc định toàn cục, nên cần kiểm tra cấu hình dự án khi dự đoán hành vi.

Một lỗi phổ biến là nuốt ngoại lệ:

```java
@Transactional
public void wrongPattern() {
    try {
        writeData();
    } catch (RuntimeException ex) {
        logError(ex);
    }
}
```

`writeData` và `logError` ở đây là **hàm minh họa**. Khi exception bị bắt và method trả về bình thường, interceptor có thể commit những gì đã thay đổi nếu transaction chưa bị đánh dấu rollback-only. Hãy để lỗi lan ra boundary, cấu hình `rollbackFor` phù hợp, hoặc khi có lý do nghiệp vụ rõ ràng gọi `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` bên trong một transaction đang hoạt động. Đừng báo thành công khi một thao tác bắt buộc không hoàn tất.

### 3.3. Những hạn chế của proxy cần nhớ

Chế độ mặc định dùng Spring AOP proxy, chỉ intercept **external calls đi qua proxy**. Nếu `this.inner()` gọi method khác trên cùng instance, `@Transactional` của `inner()` không được kích hoạt:

```java
@Service
public class OrderService {
    public void placeOrder() {
        saveOrder(); // self-invocation: bỏ qua @Transactional của saveOrder.
    }

    @Transactional
    public void saveOrder() {
        // Thao tác lưu dữ liệu.
    }
}
```

Đây là **lớp minh họa**, không có persistence implementation. Sửa bằng cách đặt boundary trên `placeOrder()`, hoặc chuyển `saveOrder()` sang một Spring service bean khác rồi gọi qua bean ấy. AspectJ weaving có thể xử lý self-invocation nhưng cần cấu hình riêng.

Ngoài ra:

- Ưu tiên method `public` trên concrete Spring-managed bean, được gọi qua proxy. Khả năng intercept `private`/`final` hoặc method không public phụ thuộc loại proxy và phiên bản Spring; đừng giả định chúng hoạt động như public method.
- Annotation trên class đặt default cho các method phù hợp; annotation chi tiết trên method có mức ưu tiên cao hơn.
- Transaction imperative thường gắn với **thread hiện tại**. `@Async`, thread mới hay `CompletableFuture` không tự kế thừa transaction từ caller.
- Không dựa vào `@Transactional` trong `@PostConstruct` khi proxy chưa hoàn tất khởi tạo.
- Transaction không tự động hoàn tác lời gọi HTTP, gửi email, hay side effect từ hệ thống bên ngoài. Với những tác vụ đó, cân nhắc transactional outbox/saga/compensation.

## 4. Quản lý transaction bằng mã

### 4.1. `TransactionTemplate`: lựa chọn ưu tiên cho imperative

`TransactionTemplate` lấy một `PlatformTransactionManager` và nhận callback. Template tự tổ chức begin, commit/rollback, dọn dẹp resource; business code chỉ nêu thao tác cần nằm trong transaction:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public class InventoryWriter {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate template;

    public InventoryWriter(JdbcTemplate jdbc, PlatformTransactionManager manager) {
        this.jdbc = jdbc;
        this.template = new TransactionTemplate(manager);
    }

    public void reserve(long productId, int quantity) {
        template.executeWithoutResult(status -> {
            int updated = jdbc.update(
                "UPDATE inventory SET available = available - ? " +
                "WHERE id = ? AND available >= ?",
                quantity, productId, quantity
            );
            if (updated != 1) {
                status.setRollbackOnly();
            }
        });
    }
}
```

Đây là **lớp minh họa**, cần bảng `inventory` và bean manager/JDBC. `status.setRollbackOnly()` yêu cầu rollback ngay cả khi callback trả về bình thường. Nghiệp vụ thật nên trả kết quả hoặc ném ngoại lệ để caller biết đặt hàng thất bại; không được hiểu việc callback hoàn thành là tác vụ chắc chắn đã commit.

Dùng `template.execute(status -> { ...; return result; })` nếu muốn trả giá trị. Khi callback ném unchecked exception, template rollback rồi truyền ngoại lệ ra ngoài (trừ vấn đề rollback/cleanup khác). Khi cần xử lý checked exception, phải chuyển thành lỗi có chủ đích, xử lý trong callback hoặc đánh dấu rollback-only; đừng giả định callback cho phép `throws IOException` tùy ý.

Có thể cấu hình template trước khi dùng bằng `setPropagationBehavior(Propagation.REQUIRES_NEW.value())`, `setIsolationLevel(...)`, `setReadOnly(true)` và `setTimeout(...)`. Nếu nhiều lời gọi đồng thời dùng chung instance, cố định cấu hình ngay từ khởi tạo, không thay đổi giữa các callback.

### 4.2. Gọi thẳng `PlatformTransactionManager`

Cách thấp hơn cho phép tự điều khiển transaction lifecycle. Đoạn Java 17+ này dùng Spring transaction dependency, và `Runnable` do caller truyền vào chứa việc cần thực hiện:

```java
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.DefaultTransactionDefinition;

public class ManualUnitOfWork {
    private final PlatformTransactionManager manager;

    public ManualUnitOfWork(PlatformTransactionManager manager) {
        this.manager = manager;
    }

    public void run(Runnable work) {
        TransactionStatus status =
            manager.getTransaction(new DefaultTransactionDefinition());

        try {
            work.run();
            manager.commit(status);
        } catch (RuntimeException | Error ex) {
            if (!status.isCompleted()) {
                manager.rollback(status);
            }
            throw ex;
        }
    }
}
```

`getTransaction` có thể tham gia transaction hiện có theo propagation, vì vậy `commit(status)` không có nghĩa luôn commit vật lý ngay. Trong đường lỗi, phải tránh rollback một status đã hoàn tất và phải truyền lỗi để caller xử lý. Dùng `TransactionTemplate` cho phần lớn trường hợp vì giảm boilerplate và ít đường đi sai.

### 4.3. Reactive: `TransactionalOperator`

Với R2DBC hoặc reactive pipelines, dùng `ReactiveTransactionManager`/`TransactionalOperator`; đừng dùng `TransactionTemplate` để bao một `Mono` rồi chờ SQL reactive hoàn tất ngoài callback:

```java
// Minh họa trong reactive service đã có ReactiveTransactionManager:
TransactionalOperator operator = TransactionalOperator.create(reactiveManager);
Mono<Void> move = debit(accountA, amount).then(credit(accountB, amount));
return operator.transactional(move);
```

`debit`, `credit` và `reactiveManager` là các biến/hàm **minh họa**; cần import `reactor.core.publisher.Mono` và `org.springframework.transaction.reactive.TransactionalOperator`. Transaction reactive sử dụng **Reactor Context**, đòi hỏi các thao tác tham gia cùng một reactive pipeline.

## 5. Propagation, isolation và rollback-only

| Propagation | Khi caller đã có transaction |
| --- | --- |
| `REQUIRED` (mặc định) | Tham gia cùng physical transaction; inner rollback-only ảnh hưởng outer. |
| `REQUIRES_NEW` | Tạm giữ outer và bắt đầu physical transaction **độc lập**. |
| `NESTED` | Thường tạo savepoint trong cùng JDBC transaction, phụ thuộc manager/resource. |
| `SUPPORTS` | Tham gia nếu có; không thì chạy không transaction. |
| `MANDATORY` | Yêu cầu có transaction trước; nếu không sẽ lỗi. |
| `NOT_SUPPORTED` | Tạm giữ transaction để chạy không transaction. |
| `NEVER` | Gây lỗi nếu đang có transaction. |

**Logical versus physical transaction:** Với hai scope `REQUIRED` gọi qua proxy, mỗi scope có thể quyết định rollback-only riêng nhưng dùng cùng physical transaction. Nếu inner đánh dấu rollback-only và outer vẫn cố commit, Spring có thể ném `UnexpectedRollbackException` để caller không hiểu nhầm rằng transaction đã commit thành công. `REQUIRES_NEW` độc lập, nhưng thường cần thêm connection khi outer vẫn giữ connection: đặt pool quá nhỏ có thể gây chờ/hết connection. `NESTED` không tương đương `REQUIRES_NEW` vì thường dựa vào savepoint trên cùng connection.

Isolation (`READ_COMMITTED`, `REPEATABLE_READ`, `SERIALIZABLE`, ...) điều khiển cách transaction quan sát những thay đổi đồng thời theo cơ chế DB, không thay thế thiết kế khóa/optimistic locking. `readOnly=true` là hint tối ưu của provider, không bảo đảm không thể ghi. Timeout chỉ có tác dụng theo manager và tài nguyên hỗ trợ.

## 6. Demo độc lập với Java 17+, Maven, Spring Boot và H2

Ví dụ sau dùng **Spring Boot 3.5.16**, `spring-boot-starter-jdbc` và H2 in-memory. Chương trình tạo 2 tài khoản, thử thành công và thất bại ở cả hai cách transaction; H2 giúp thấy số dư sau rollback mà không cần cài database.

Tạo các file:

```text
transaction-demo/
  pom.xml
  src/main/java/example/TxDemoApplication.java
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>transaction-demo</artifactId>
    <version>1.0.0</version>
    <properties><java.version>17</java.version></properties>
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

`src/main/java/example/TxDemoApplication.java`:

```java
package example;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootApplication
public class TxDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc, TransferService transfer) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE accounts (id INT PRIMARY KEY, balance INT NOT NULL)"
            );
            jdbc.update("INSERT INTO accounts (id, balance) VALUES (?, ?)", 1, 100);
            jdbc.update("INSERT INTO accounts (id, balance) VALUES (?, ?)", 2, 100);

            System.out.println("Bat dau: " + balances(jdbc));

            try {
                transfer.declarative(1, 2, 20, true);
            } catch (IllegalStateException expected) {
                // Tiếp tục demo sau lỗi có chủ đích.
            }
            System.out.println("Khai bao loi: " + balances(jdbc));

            transfer.declarative(1, 2, 20, false);
            System.out.println("Khai bao thanh cong: " + balances(jdbc));

            try {
                transfer.programmatic(1, 2, 10, true);
            } catch (IllegalStateException expected) {
                // Tiếp tục demo sau lỗi có chủ đích.
            }
            System.out.println("Bang ma loi: " + balances(jdbc));

            transfer.programmatic(1, 2, 10, false);
            System.out.println("Bang ma thanh cong: " + balances(jdbc));
        };
    }

    private static String balances(JdbcTemplate jdbc) {
        Integer a = jdbc.queryForObject(
            "SELECT balance FROM accounts WHERE id = ?", Integer.class, 1
        );
        Integer b = jdbc.queryForObject(
            "SELECT balance FROM accounts WHERE id = ?", Integer.class, 2
        );
        return a + " / " + b;
    }
}

@Service
class TransferService {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate template;

    TransferService(JdbcTemplate jdbc, PlatformTransactionManager manager) {
        this.jdbc = jdbc;
        this.template = new TransactionTemplate(manager);
    }

    @Transactional
    public void declarative(int from, int to, int amount, boolean fail) {
        transferSteps(from, to, amount, fail);
    }

    public void programmatic(int from, int to, int amount, boolean fail) {
        template.executeWithoutResult(
            status -> transferSteps(from, to, amount, fail)
        );
    }

    private void transferSteps(int from, int to, int amount, boolean fail) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }

        int debited = jdbc.update(
            "UPDATE accounts SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, from, amount
        );
        if (debited != 1) {
            throw new IllegalStateException("Cannot debit source");
        }

        if (fail) {
            throw new IllegalStateException("Simulated failure after debit");
        }

        int credited = jdbc.update(
            "UPDATE accounts SET balance = balance + ? WHERE id = ?",
            amount, to
        );
        if (credited != 1) {
            throw new IllegalStateException("Cannot credit destination");
        }
    }
}
```

Tại thư mục `transaction-demo`, dùng JDK 17 trở lên và Maven 3.9+:

```bash
java -version
mvn -version
mvn -q spring-boot:run
```

Các dòng do `CommandLineRunner` in ra, ngoài log Spring, là:

```text
Bat dau: 100 / 100
Khai bao loi: 100 / 100
Khai bao thanh cong: 80 / 120
Bang ma loi: 80 / 120
Bang ma thanh cong: 70 / 130
```

Hai lần cố ý ném lỗi ngay sau bước trừ tiền đều rollback, số dư không đổi. Hai lần thành công lần lượt chuyển 20 và 10; tổng luôn là 200. `@Transactional` hoạt động vì runner gọi `TransferService` bean được inject qua Spring proxy; `TransactionTemplate` tự quản lý scope của callback. Trong sản phẩm thật cần bổ sung concurrency controls, idempotency và kiểm thử với database đang dùng; H2 chỉ minh họa transaction boundary.

## 7. Chọn cách triển khai và kiểm tra kết quả

| Bài toán | Cách thường phù hợp |
| --- | --- |
| Use case service có transaction bao toàn phương thức | `@Transactional`: thể hiện chính sách rõ, ít boilerplate. |
| Chỉ một đoạn nhỏ cần transaction hoặc có nhánh đặc biệt | `TransactionTemplate`: ranh giới ngay tại vị trí callback. |
| Cần transaction độc lập lồng trong quy trình | `REQUIRES_NEW` qua service proxy khác hoặc template cấu hình propagation; cân nhắc connection pool. |
| Cần tự quyết định begin/commit/rollback trong thuật toán đặc biệt | `PlatformTransactionManager` trực tiếp, nhưng phải xử lý đường lỗi đầy đủ. |
| Pipeline R2DBC/Reactive | `TransactionalOperator` hoặc `@Transactional` với `ReactiveTransactionManager`. |

Checklist QA thực tế: gọi service **qua bean**; kiểm tra đúng manager và datasource; chủ động thử lỗi ở **bước thứ hai** và xác nhận bước thứ nhất rollback; thử checked exception; thử inner `REQUIRED` rollback-only; kiểm tra self-invocation; tránh gọi mạng trong transaction dài; kiểm thử bằng integration test trên database phù hợp. Nếu test dùng `@Transactional` ở chính test method, cần nhớ Spring Test thường rollback test transaction, điều này khác với việc kiểm chứng boundary thực tế của service.

**Tự kiểm tra:** Điều gì xảy ra nếu bỏ `@Transactional` và `TransactionTemplate` khỏi demo? Tại sao `this.save()` không chạy interceptor của `save`? Vì sao inner `REQUIRED` đánh dấu rollback-only có thể làm outer ném `UnexpectedRollbackException`? Khi nào thật sự nên dùng `REQUIRES_NEW` thay vì `NESTED`?

## 8. Tài liệu Spring chính thức

- [Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
