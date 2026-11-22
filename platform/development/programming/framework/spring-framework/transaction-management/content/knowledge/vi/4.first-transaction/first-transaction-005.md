# Thực hiện hai thao tác ghi trong một luồng nghiệp vụ

## 1. Bài toán của giao dịch đầu tiên

**Mục tiêu:** hiểu và tự chạy một nghiệp vụ Spring Framework trong đó **hai thao tác ghi dữ liệu phải cùng thành công hoặc cùng bị hủy**. Sau bài này, bạn có thể:

1. Xác định trạng thái dữ liệu trước và sau hai lệnh ghi.
2. Phân biệt **hai lệnh chạy liên tiếp** với **hai lệnh nằm trong cùng một transaction**.
3. Đặt ranh giới `@Transactional` ở tầng service, để hai thao tác của repository dùng cùng transaction JDBC.
4. Tạo lỗi có chủ đích sau thao tác thứ nhất, quan sát rollback, rồi giải thích chính xác vì sao thao tác thứ nhất không được lưu.
5. Kiểm tra kết quả với dữ liệu thật thay vì chỉ khẳng định rằng phương thức đã gắn annotation.

Trong ví dụ xuyên suốt, bảng `wallets` có hai tài khoản:

| Tài khoản | `id` | `balance` ban đầu |
| --- | ---: | ---: |
| A (người gửi) | 1 | 100 |
| B (người nhận) | 2 | 50 |

Nghiệp vụ **chuyển 20 đơn vị từ A sang B** đòi hỏi hai câu lệnh ghi:

```sql
-- Ghi 1: trừ tiền của A, chỉ trừ nếu đủ tiền.
UPDATE wallets
SET balance = balance - 20
WHERE id = 1 AND balance >= 20;

-- Ghi 2: cộng tiền vào B.
UPDATE wallets
SET balance = balance + 20
WHERE id = 2;
```

Nếu cả hai thành công, số dư trở thành **A = 80, B = 70**, tổng vẫn bằng 150. Nếu ghi 1 thành công nhưng ghi 2 lỗi, nghiệp vụ phải để dữ liệu trở lại **A = 100, B = 50**. Tính chất cần đạt là **atomicity**: mọi thay đổi thuộc transaction được commit như một đơn vị hoặc rollback như một đơn vị.

Ở ví dụ này, cả hai ghi thuộc **cùng một cơ sở dữ liệu JDBC**. Không suy rộng rằng Spring tự rollback được email, HTTP request, message đã gửi, hoặc hai database độc lập nếu chúng không cùng tham gia cơ chế transaction tương ứng.

## 2. Vì sao gọi hai lệnh nối tiếp chưa đủ?

Xét một phương thức chưa có transaction boundary:

```java
public void transferWithoutTransaction(int from, int to, int amount) {
    repository.debit(from, amount);  // Ghi thứ nhất.
    repository.credit(to, amount); // Ghi thứ hai.
}
```

Đây là **mã giả lập tầng service**, giả định `repository` cung cấp hai phương thức. Thứ tự lệnh Java không tự tạo transaction. Trong cấu hình JDBC thông dụng, connection không được Spring quản lý trong transaction sẽ chạy với `autoCommit=true`: mỗi câu lệnh có thể được commit riêng. Nếu ghi thứ hai lỗi, ghi thứ nhất đã commit sẽ không tự đảo ngược.

| Thời điểm | Trường hợp không cùng transaction | Trường hợp trong một transaction |
| --- | --- | --- |
| Ban đầu | A=100, B=50 | A=100, B=50 |
| Sau ghi 1 | A bị trừ; có thể đã commit | A bị trừ **bên trong transaction chưa commit** |
| Ghi 2 thất bại | A có thể vẫn bị trừ, B chưa cộng | Exception khiến transaction rollback |
| Kết thúc lỗi | Dữ liệu có thể sai: A=80, B=50 | Khôi phục A=100, B=50 |

Phân biệt **trạng thái tạm bên trong transaction** với **trạng thái đã commit**: lệnh ghi 1 vẫn được database thực thi, nên transaction hiện tại có thể nhìn thấy kết quả tạm; rollback mới hủy nó. Khả năng transaction khác nhìn thấy dữ liệu tạm còn phụ thuộc isolation của database.

Một transaction không thay thế kiểm tra nghiệp vụ. Hai câu `UPDATE` đều có thể chạy mà ảnh hưởng **0 hàng** (ví dụ tài khoản nhận không tồn tại). Vì vậy mã cần kiểm tra **số hàng được cập nhật** và coi kết quả không đạt yêu cầu là lỗi, để cả transaction rollback.

## 3. Đặt ranh giới giao dịch ở đâu trong Spring?

Một cách tổ chức dễ đọc là:

```text
Ứng dụng/Controller
    |
    v
WalletService.transfer(...)        <- @Transactional: ranh giới nghiệp vụ
    |
    +--> WalletRepository.debit(...)   <- UPDATE thứ nhất
    |
    +--> WalletRepository.credit(...)  <- UPDATE thứ hai
    |
    v
Commit khi cả hai thành công;
Rollback nếu một bước bắt buộc ném lỗi cần rollback.
```

**Vì sao đặt ở service?** Service quyết định rằng hai thao tác repository tạo thành **một use case**. Repository chỉ thực hiện truy vấn/cập nhật; việc gọi hai repository methods trong cùng một transaction là quyết định ở tầng phối hợp nghiệp vụ.

Với `@Transactional` chạy ở chế độ Spring AOP proxy phổ biến:

1. Caller lấy `WalletService` từ Spring context và gọi `transfer()` **qua proxy**.
2. Transaction interceptor nhờ `PlatformTransactionManager` bắt đầu transaction (hoặc tham gia transaction hiện có theo propagation).
3. Cả `debit()` và `credit()` dùng `JdbcTemplate` và cùng `DataSource`, nên Spring lấy JDBC `Connection` gắn với transaction đang hoạt động.
4. Method kết thúc bình thường: manager commit. Nếu unchecked exception thoát ra: mặc định rollback; caller nhận lại ngoại lệ.

Điều này có hai điều kiện quan trọng: bean phải do Spring quản lý và lời gọi phải đi **qua proxy**; các thao tác JDBC cần dùng tài nguyên tham gia cùng transaction. `JdbcTemplate` lấy connection qua `DataSourceUtils` nên hỗ trợ quy tắc này với `DataSourceTransactionManager`. Tự gọi `this.transfer()` từ một phương thức của chính target class sẽ bỏ qua proxy ở chế độ mặc định.

Trong ví dụ độc lập bên dưới, cấu hình `@EnableTransactionManagement` bật xử lý annotation; `DataSourceTransactionManager` quản lý một H2 `DataSource`.

## 4. Thực hành đầy đủ: Java 17+, Spring Framework, JDBC, H2

Dự án nhỏ dùng **Spring Framework 6.2.8**, **H2 2.3.232** và Maven. Các phiên bản được cố định để ví dụ có dependency xác định. Đây là ứng dụng Java độc lập, không cần Spring Boot, HTTP server hay một database cài sẵn.

### 4.1. Cấu trúc file

```text
two-writes-demo/
├── pom.xml
└── src/main/java/example/
    ├── App.java
    ├── TxConfig.java
    ├── WalletRepository.java
    └── WalletService.java
```

### 4.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>two-writes-demo</artifactId>
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
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
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
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
                <configuration>
                    <mainClass>example.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` chứa ApplicationContext và hạ tầng proxy; `spring-jdbc` chứa `JdbcTemplate` và JDBC transaction manager; `spring-tx` chứa transaction abstraction và `@Transactional`; H2 là database chạy trong bộ nhớ JVM. Ở project production, dependency/phiên bản thường được quản lý tập trung bằng BOM và dùng connection pool phù hợp.

### 4.3. `TxConfig.java` — cấu hình connection và transaction manager

```java
package example;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;

@Configuration
@EnableTransactionManagement
public class TxConfig {

    @Bean
    public DataSource dataSource() {
        JdbcDataSource ds = new JdbcDataSource();
        ds.setURL("jdbc:h2:mem:two_writes;DB_CLOSE_DELAY=-1");
        ds.setUser("sa");
        ds.setPassword("");
        return ds;
    }

    @Bean
    public JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    public PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    public WalletRepository walletRepository(JdbcTemplate jdbcTemplate) {
        return new WalletRepository(jdbcTemplate);
    }

    @Bean
    public WalletService walletService(WalletRepository walletRepository) {
        return new WalletService(walletRepository);
    }
}
```

- `@EnableTransactionManagement` cho phép Spring áp dụng `@Transactional` thông qua transaction interceptor/proxy.
- `transactionManager()` quản lý JDBC connection của đúng `dataSource()`. Không tạo hai datasource riêng cho hai thao tác.
- `DB_CLOSE_DELAY=-1` giữ H2 in-memory database tồn tại đến khi JVM kết thúc, ngay cả khi connection tạm đóng.
- `JdbcDataSource` ở đây phục vụ demo; ứng dụng thật thường dùng datasource có connection pool.

### 4.4. `WalletRepository.java` — chính xác hai thao tác ghi

```java
package example;

import org.springframework.jdbc.core.JdbcTemplate;

public class WalletRepository {

    private final JdbcTemplate jdbc;

    public WalletRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int debit(int walletId, int amount) {
        return jdbc.update(
            "UPDATE wallets " +
            "SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, walletId, amount
        );
    }

    public int credit(int walletId, int amount) {
        return jdbc.update(
            "UPDATE wallets " +
            "SET balance = balance + ? " +
            "WHERE id = ?",
            amount, walletId
        );
    }
}
```

`debit` là ghi 1, `credit` là ghi 2. Cả hai trả về `int` — số hàng thực sự được `UPDATE` sửa. Với bài toán mỗi `id` là một tài khoản duy nhất, kết quả hợp lệ cho mỗi bước là **1 hàng**. Kết quả 0 báo tài khoản không tồn tại hoặc nguồn không đủ số dư.

Đặt điều kiện `balance >= ?` ngay trong câu `UPDATE` giúp việc kiểm tra số dư và trừ tiền diễn ra như một thao tác SQL có điều kiện; không nên làm kiểu «SELECT số dư → tự kiểm tra trong Java → UPDATE không điều kiện» mà bỏ qua nguy cơ tranh chấp. Vấn đề khóa, deadlock, retry và isolation khi có tải đồng thời vẫn cần được giải quyết riêng cho môi trường production.

### 4.5. `WalletService.java` — một ranh giới chứa cả hai ghi

```java
package example;

import org.springframework.transaction.annotation.Transactional;

public class WalletService {

    private final WalletRepository repository;

    public WalletService(WalletRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void transfer(
        int fromId,
        int toId,
        int amount,
        boolean failAfterDebit
    ) {
        if (amount <= 0 || fromId == toId) {
            throw new IllegalArgumentException("invalid transfer");
        }

        int debited = repository.debit(fromId, amount);  // GHI 1
        if (debited != 1) {
            throw new IllegalStateException("source missing or insufficient");
        }

        if (failAfterDebit) {
            // Chỉ dùng trong bài lab để cố ý làm hỏng nghiệp vụ.
            throw new IllegalStateException("simulated failure after debit");
        }

        int credited = repository.credit(toId, amount); // GHI 2
        if (credited != 1) {
            throw new IllegalStateException("receiver missing");
        }
    }
}
```

**Điểm quyết định nằm ở `@Transactional` trên `transfer`.** Trong một lời gọi:

- Spring bắt đầu transaction trước khi chạy thân phương thức (nếu chưa có transaction).
- Repository thực thi hai `UPDATE` và dùng cùng JDBC transaction.
- Nếu `debit` hoặc `credit` không đạt 1 hàng, service ném exception thay vì trả thành công giả.
- Nếu lỗi xảy ra giữa hai ghi, `IllegalStateException` là unchecked exception nên Spring rollback theo mặc định.
- Chỉ khi phương thức hoàn thành hợp lệ, transaction boundary mới commit.

Biến `failAfterDebit` là công tắc **chỉ dành cho thí nghiệm**, để chủ động xác minh tình huống «đã ghi 1 nhưng chưa ghi 2». Một use case production sẽ không có tham số này.

### 4.6. `App.java` — khởi tạo dữ liệu, gọi bean và quan sát kết quả

```java
package example;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;

public final class App {

    private App() {
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(TxConfig.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            WalletService service = context.getBean(WalletService.class);

            jdbc.execute(
                "CREATE TABLE wallets (" +
                "id INT PRIMARY KEY, " +
                "balance INT NOT NULL)"
            );
            jdbc.update(
                "INSERT INTO wallets(id, balance) VALUES (?, ?)", 1, 100
            );
            jdbc.update(
                "INSERT INTO wallets(id, balance) VALUES (?, ?)", 2, 50
            );

            showBalances("Before", jdbc);

            service.transfer(1, 2, 20, false);
            showBalances("After commit", jdbc);

            try {
                service.transfer(1, 2, 10, true);
            } catch (IllegalStateException ex) {
                System.out.println("Expected error: " + ex.getMessage());
            }
            showBalances("After rollback", jdbc);

            try {
                service.transfer(1, 999, 5, false);
            } catch (IllegalStateException ex) {
                System.out.println("Expected error: " + ex.getMessage());
            }
            showBalances("After receiver error", jdbc);
        }
    }

    private static void showBalances(String label, JdbcTemplate jdbc) {
        Integer a = jdbc.queryForObject(
            "SELECT balance FROM wallets WHERE id = ?", Integer.class, 1
        );
        Integer b = jdbc.queryForObject(
            "SELECT balance FROM wallets WHERE id = ?", Integer.class, 2
        );
        System.out.println(label + ": A=" + a + ", B=" + b);
    }
}
```

Lệnh `context.getBean(WalletService.class)` quan trọng: `service` là bean lấy từ Spring và được gọi **từ bên ngoài**, nên `@Transactional` được interceptor áp dụng. Nếu thay bằng `new WalletService(...)` hoặc cho một method trong `WalletService` gọi `this.transfer(...)`, hành vi proxy sẽ khác.

Dữ liệu đầu được tạo trước khi chạy các transaction thử nghiệm. Sau mỗi lời gọi service, `showBalances` truy vấn lại bảng và cho thấy dữ liệu đã commit (hoặc đã được rollback) từ góc nhìn lời gọi độc lập sau khi transaction kết thúc.

### 4.7. Biên dịch và chạy

Mở terminal ở thư mục chứa `pom.xml`. Cần JDK 17+ và Maven 3.9+ (có kết nối Maven Central cho lần tải dependencies đầu tiên):

```bash
java -version
mvn -version
mvn -q compile exec:java
```

Các dòng do chương trình in ra phải là (ngoài log của Maven/Spring nếu môi trường hiển thị thêm):

```text
Before: A=100, B=50
After commit: A=80, B=70
Expected error: simulated failure after debit
After rollback: A=80, B=70
Expected error: receiver missing
After receiver error: A=80, B=70
```

**Đọc kết quả theo từng transaction:**

1. **Lời gọi thành công:** Ghi 1 trừ A 20, ghi 2 cộng B 20, rồi commit. Từ `(100, 50)` thành `(80, 70)`.
2. **Lỗi ở giữa:** Lời gọi tiếp theo thử trừ A 10 nhưng ném `simulated failure after debit` trước khi cộng B. Vì exception thoát ra khỏi `transfer`, Spring rollback cả transaction. Kết quả vẫn là `(80, 70)`.
3. **Tài khoản nhận không tồn tại:** Ghi 1 tạm trừ A 5; ghi 2 có `id = 999` nên cập nhật 0 hàng, service ném `receiver missing`. Transaction rollback, A/B vẫn `(80, 70)`. Đây là lý do phải kiểm tra `update count`, không chỉ đợi exception từ JDBC driver.

Số tiền được chuyển trong lần thành công vẫn có tổng 150. Việc hai lần lỗi không làm thay đổi số dư mới là bằng chứng trực tiếp cho rollback của **cả luồng nghiệp vụ**.

## 5. Điều gì sẽ xảy ra nếu bỏ ranh giới transaction?

Bạn có thể làm thí nghiệm **trên bản sao lab H2**, không chạy trên dữ liệu thật:

- Bỏ annotation `@Transactional` ở `WalletService.transfer` và chạy lại chương trình từ đầu bằng một JVM mới.
- Lời gọi thành công vẫn có thể cho `(80, 70)` vì từng `UPDATE` đều hoàn tất.
- Ở lời gọi bị lỗi giữa hai ghi, `debit` có thể đã autocommit trên connection độc lập; kết quả sau lỗi trở thành **A=70, B=70**, tổng chỉ còn 140.
- Lỗi tài khoản nhận không tồn tại có thể tiếp tục làm A giảm, vì thao tác ghi 1 đã commit còn thao tác ghi 2 sửa 0 hàng.

Sự cố không nằm ở cú pháp SQL: cùng hai câu SQL, cùng thứ tự Java, nhưng **thiếu chung một transaction boundary** nên ứng dụng không còn đảm bảo atomicity.

Nếu bạn đặt `@Transactional` riêng trên `WalletRepository.debit()` và `WalletRepository.credit()` rồi gọi chúng từ service không có transaction, mỗi phương thức repository có thể tạo **transaction riêng**, vẫn chưa đạt yêu cầu «hoặc cả hai, hoặc không thao tác nào». Ranh giới cần bao trọn **hai ghi của một use case**.

## 6. Hiểu commit, rollback, propagation qua bài lab

Mặc định `@Transactional` dùng `Propagation.REQUIRED`. Trong `App.main` không có transaction bao quanh `service.transfer()`, nên khi gọi qua proxy, Spring tạo transaction mới. Nếu một service khác đã mở transaction và gọi `transfer()` qua proxy với `REQUIRED`, cả hai có thể **tham gia một physical transaction hiện có**. Khi đó kết quả cuối cùng phải xét transaction của caller ngoài cùng; `transfer()` trả về không nhất thiết nghĩa là đã commit vật lý.

Đối với JDBC transaction này:

- **Begin:** Transaction manager lấy connection, đặt transaction mode phù hợp và gắn tài nguyên vào luồng hiện tại.
- **Ghi 1 và ghi 2:** `JdbcTemplate` gọi qua `DataSourceUtils` nên tái sử dụng connection đã được Spring gắn với transaction.
- **Commit:** Khi proxy nhận kết quả bình thường, boundary sở hữu transaction yêu cầu commit; database lưu cả hai cập nhật.
- **Rollback:** Khi exception thỏa quy tắc rollback thoát khỏi method, boundary yêu cầu rollback; database hoàn tác các thay đổi chưa commit, bao gồm ghi 1 đã chạy.

Mặc định trong giao dịch khai báo kiểu imperative, `RuntimeException` hoặc `Error` dẫn đến rollback; checked exception như `IOException` **không tự kích hoạt rollback** nếu không có rollback rule phù hợp. Nếu use case có checked exception mà phải hủy hai ghi, có thể khai báo `@Transactional(rollbackFor = IOException.class)`. Chính sách toàn cục/manager có thể được tùy chỉnh; hãy kiểm tra cấu hình hệ thống khi dự đoán ngoại lệ.

**Không bắt lỗi rồi âm thầm trả thành công** trong phương thức giao dịch. Ví dụ sau là **minh họa lỗi thiết kế**, không phải đoạn chạy độc lập:

```java
@Transactional
public void transferWrongly() {
    repository.debit(1, 20);
    try {
        repository.credit(999, 20);
    } catch (RuntimeException ex) {
        // Nuốt exception: interceptor có thể nghĩ nghiệp vụ thành công.
    }
}
```

Ngoài việc không kiểm tra update count, đoạn trên còn có khả năng nuốt lỗi. Nếu exception đã bị bắt và không có rollback-only, Spring có thể commit thao tác trừ tiền. Cách đúng trong lab là kiểm tra từng kết quả và để exception thoát ra khỏi `transfer`; với các tình huống xử lý đặc biệt, có thể đánh dấu rollback-only một cách chủ động.

**Transaction scope và thread:** Mô hình JDBC này dùng transaction gắn với thread của lời gọi. Không tách `debit` và `credit` sang các thread tùy ý bằng `@Async`/`CompletableFuture` và giả định transaction tự lan sang thread khác. Reactive R2DBC có hạ tầng transaction khác, dùng Reactor Context và `ReactiveTransactionManager`.

## 7. Biến thể: cùng hai ghi qua `TransactionTemplate`

Một transaction boundary cũng có thể viết bằng mã. Đoạn minh họa sau giả định `repository` là `WalletRepository` từ demo và `manager` là `PlatformTransactionManager` đang quản lý đúng datasource:

```java
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public class TemplateTransferService {
    private final WalletRepository repository;
    private final TransactionTemplate template;

    public TemplateTransferService(
        WalletRepository repository,
        PlatformTransactionManager manager
    ) {
        this.repository = repository;
        this.template = new TransactionTemplate(manager);
    }

    public void transfer(int fromId, int toId, int amount) {
        if (amount <= 0 || fromId == toId) {
            throw new IllegalArgumentException("invalid transfer");
        }

        template.executeWithoutResult(status -> {
            if (repository.debit(fromId, amount) != 1) {
                throw new IllegalStateException("cannot debit");
            }
            if (repository.credit(toId, amount) != 1) {
                throw new IllegalStateException("cannot credit");
            }
        });
    }
}
```

Đây là **lớp minh họa có thể biên dịch khi thêm vào project**, chưa được `TxConfig` đăng ký làm bean. `TransactionTemplate` tự bắt đầu/điều phối kết thúc scope callback, nên hai câu ghi vẫn được bọc làm một transaction. Cách dùng `@Transactional` thuận tiện nếu ranh giới trùng toàn bộ service method; template hữu ích khi chỉ một đoạn của luồng dài cần transaction hoặc khi phải đặt ranh giới theo nhánh xử lý.

## 8. Kiểm thử đủ mạnh cho hai thao tác ghi

Một phép thử tốt cần nhìn thấy **trạng thái database sau khi transaction kết thúc**. Có thể lập bảng test cases cho cùng method `transfer`:

| Trường hợp | Ghi 1 | Ghi 2 | Kỳ vọng |
| --- | --- | --- | --- |
| Nguồn đủ tiền, đích tồn tại | 1 hàng | 1 hàng | Commit cả hai; tổng số dư không đổi |
| Cố ý ném lỗi giữa hai bước | 1 hàng tạm | Chưa chạy | Rollback; cả hai số dư giữ nguyên |
| Tài khoản nhận không tồn tại | 1 hàng tạm | 0 hàng | Ném lỗi và rollback ghi 1 |
| Nguồn không đủ tiền | 0 hàng | Không chạy | Ném lỗi; không đổi số dư |
| `amount <= 0` hoặc cùng tài khoản | Không chạy | Không chạy | Từ chối dữ liệu đầu vào |

**Cách kiểm tra:** tạo dữ liệu đầu; gọi service **qua Spring bean**; bắt exception ở phía caller khi muốn tiếp tục kiểm tra; đọc lại bằng truy vấn sau khi service call đã kết thúc; so sánh số dư từng tài khoản, không chỉ tổng. Tổng số dư vẫn đúng chưa chắc mọi chuyển khoản hợp lệ; ngược lại, mỗi bước ảnh hưởng 1 hàng cũng chưa đủ nếu thiếu ranh giới transaction.

Khi dùng Spring Test, một test method tự gắn `@Transactional` có thể chạy trong transaction của test và được framework rollback sau test. Nếu muốn kiểm tra commit/rollback thực tế ở boundary service, hãy tổ chức integration test để phân biệt transaction của **test harness** với transaction ứng dụng (ví dụ gọi service không nằm trong một test-managed transaction).

Trong sản phẩm thật, còn phải xử lý idempotency của request, quyền chuyển tiền, validation, concurrency/lock ordering, isolation, connection-pool sizing, giám sát thời gian giữ connection và retry có kiểm soát. Đặc biệt, **không gọi HTTP/email rồi cho rằng rollback JDBC sẽ hoàn tác side effect bên ngoài**; có thể cần outbox, saga hoặc compensation tùy bài toán.

## 9. Tóm tắt kiến thức cần giữ

Hai thao tác ghi trong một luồng nghiệp vụ chỉ có ý nghĩa nguyên tử khi chúng **cùng tham gia một transaction được quản lý**. Trong ứng dụng Spring JDBC, cách đầu tiên nên thực hành là đặt `@Transactional` trên phương thức service bao trọn hai thao tác repository; bảo đảm lời gọi đi qua Spring proxy, các repository dùng cùng datasource/manager, và lỗi của một bước khiến transaction rollback.

Điểm quan trọng nhất của bài lab không phải chạy thành công hai câu `UPDATE`. Đó là **cố tình làm hỏng thao tác thứ hai hoặc hỏng ngay sau thao tác thứ nhất, rồi xác nhận không có cập nhật dở dang được commit**.

Tự trả lời trước khi chuyển bài:

1. Vì sao hai lệnh `UPDATE` chạy liên tiếp không mặc định là một transaction?
2. Nếu `credit()` cập nhật 0 hàng nhưng không ném lỗi, `@Transactional` có tự biết nghiệp vụ thất bại không?
3. Vì sao `App` lấy `WalletService` từ Spring context thay vì gọi `new`?
4. Vì sao cần đọc lại trạng thái **sau** khi phương thức transaction kết thúc?
5. Hệ quả của việc chuyển `debit` và `credit` sang hai datasource không tham gia cùng transaction là gì?

## 10. Tài liệu tham khảo

- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Controlling Database Connections (`DataSourceUtils`)](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
