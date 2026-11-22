# `@Transactional` và `TransactionTemplate` trong Spring: ranh giới, commit và rollback

Một nghiệp vụ có thể cần nhiều câu SQL nhưng phải cho ra **một kết quả nhất quán**. Ví dụ chuyển 10 đơn vị từ tài khoản A sang tài khoản B: nếu trừ A thành công rồi cộng B thất bại, hệ thống không được lưu trạng thái chỉ mới trừ A. **Transaction (giao dịch)** gom các thao tác có liên quan vào một đơn vị commit hoặc rollback theo khả năng của database và transaction manager.

Trong Spring Framework Data Access, hai cách điều khiển giao dịch thường gặp là:

- **`@Transactional`**: khai báo quy tắc transaction trên method/class; cơ chế Spring transaction interceptor/proxy lo mở, tham gia, commit hoặc rollback.
- **`TransactionTemplate`**: dùng API Java gọi `execute(...)` hoặc `executeWithoutResult(...)`, đặt ranh giới transaction ngay quanh callback.

Hai cách đều có thể dùng cùng `PlatformTransactionManager` và cùng `DataSource`, nhưng khác nhau về vị trí cấu hình, cách gọi qua proxy và độ linh hoạt khi xử lý từng đoạn công việc.

Bài này tập trung vào **giao dịch imperative** với Spring JDBC và database quan hệ. Giao dịch reactive dùng cơ chế khác, được phân biệt ở cuối.

## 1. Giao dịch là gì và vì sao cần ranh giới rõ ràng?

Hãy xét tài khoản A có số dư 100 và tài khoản B có số dư 100. Một lần chuyển 10 có hai bước:

~~~sql
UPDATE accounts SET balance = balance - 10 WHERE id = 1;
UPDATE accounts SET balance = balance + 10 WHERE id = 2;
~~~

Nếu cùng một transaction và cả hai bước thành công, sau commit kết quả là A=90, B=110. Nếu bước thứ hai gặp lỗi làm transaction rollback, kết quả vẫn là A=100, B=100. Khi không có transaction bao trùm, mỗi SQL có thể được commit riêng theo chế độ auto-commit, dẫn tới khả năng chỉ lưu bước đầu.

Các thuộc tính **ACID** thường dùng để mô tả giao dịch:

| Thuộc tính | Ý nghĩa thực tế |
| --- | --- |
| Atomicity | Các thay đổi trong phạm vi giao dịch được commit cùng nhau hoặc rollback theo khả năng DB; không cho phép “mới hoàn tất nửa nghiệp vụ” sau rollback. |
| Consistency | Giao dịch phải tuân thủ các ràng buộc nhất quán; **quy tắc nghiệp vụ vẫn phải được lập trình và kiểm tra**, annotation không tự tạo chúng. |
| Isolation | Mức độ các transaction đồng thời nhìn thấy/ảnh hưởng lẫn nhau phụ thuộc isolation, khóa và cơ chế của database. |
| Durability | Sau commit thành công, DB có trách nhiệm bảo đảm độ bền theo cơ chế lưu trữ của nó. |

**Transaction không tự bảo đảm một nghiệp vụ chuyển tiền hoàn toàn chính xác:** còn cần kiểm tra số hàng chịu tác động, số dư đủ hay không, chống chuyển trùng, xử lý cạnh tranh và thiết kế mức isolation/locking phù hợp. Ví dụ sau ưu tiên minh họa commit/rollback trên hai câu SQL, không phải một hệ thống ngân hàng hoàn chỉnh.

### Thành phần tham gia trong Spring JDBC

~~~text
Client -> Spring-managed service
             |
             +-- @Transactional qua proxy
             |         hoặc
             +-- TransactionTemplate.execute(...)
                         |
                         v
              PlatformTransactionManager
                         |
                         v
               DataSource / JDBC Connection
                         |
                JdbcTemplate, Repository
                         |
                      Database
~~~

- `PlatformTransactionManager` là hợp đồng quản lý transaction imperative của Spring; implementation cho JDBC có thể là `DataSourceTransactionManager` hoặc `JdbcTransactionManager`.
- `DataSource` cung cấp connection. `JdbcTemplate` lấy connection qua hạ tầng Spring, nhờ vậy tham gia transaction đang gắn với thread hiện tại trên cùng resource.
- `TransactionDefinition` mô tả propagation, isolation, timeout và read-only; `TransactionStatus` cho phép đánh dấu rollback-only và kiểm tra trạng thái trong phạm vi được cấp.
- Khi Spring Boot cấu hình một `DataSource` và transaction manager phù hợp, phần lớn ứng dụng dùng transaction declarative hoặc programmatic mà không cần tự viết `connection.setAutoCommit(false)` và `commit()/rollback()`.

**Điều kiện then chốt:** các thao tác phải thực sự dùng tài nguyên do **cùng transaction manager** quản lý. Một `DriverManager.getConnection(...)` tự mở ngoài `DataSource` của Spring không mặc nhiên tham gia transaction của service.

## 2. `@Transactional`: khai báo ranh giới giao dịch

Ví dụ một method ở tầng service:

~~~java
@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(int fromId, int toId, int amount) {
        jdbc.update(
            "UPDATE accounts SET balance = balance - ? WHERE id = ?",
            amount, fromId);

        jdbc.update(
            "UPDATE accounts SET balance = balance + ? WHERE id = ?",
            amount, toId);
    }
}
~~~

Đây là **đoạn class Spring minh họa**, cần import `@Service`, `@Transactional`, `JdbcTemplate` và các bean/DataSource phù hợp; ví dụ đầy đủ chạy được xuất hiện ở mục 5. Spring transaction interceptor đặt logic transaction **xung quanh lần gọi method hợp lệ qua proxy**:

1. Một bean khác gọi `transfer(...)` thông qua Spring proxy.
2. Transaction interceptor chọn `PlatformTransactionManager` và mở transaction nếu chưa có, hoặc tham gia transaction hiện tại theo propagation.
3. `JdbcTemplate` chạy hai câu SQL trên connection tham gia transaction đó.
4. Nếu method hoàn thành bình thường và transaction không bị đánh dấu rollback-only, Spring yêu cầu commit tại ranh giới tương ứng.
5. Nếu exception phù hợp quy tắc rollback thoát ra method, Spring yêu cầu rollback hoặc đánh dấu transaction đang tham gia là rollback-only.

**`@Transactional` là metadata; annotation tự nó không tự mở transaction trên đối tượng do `new` tạo thủ công.** Cần bean được Spring quản lý và hạ tầng transaction management được bật (`@EnableTransactionManagement` hoặc auto-configuration thích hợp của Spring Boot), cùng transaction manager tương ứng.

### Quy tắc mặc định quan trọng

Theo mặc định thường dùng trong Spring:

| Thuộc tính | Mặc định |
| --- | --- |
| Propagation | `Propagation.REQUIRED` |
| Isolation | `Isolation.DEFAULT` (theo database/transaction manager) |
| Read-only | `false` |
| Timeout | Mặc định của transaction manager, hoặc không giới hạn nếu hệ thống không hỗ trợ |
| Rollback | Với `RuntimeException` và `Error`; **checked exception** thường không kích hoạt rollback theo mặc định |

Lưu ý: dự án có thể cấu hình quy tắc rollback chung khác mặc định. Không suy diễn hành vi từ annotation nếu đã có cấu hình transaction riêng.

`REQUIRED` có nghĩa: **nếu chưa có transaction phù hợp thì tạo mới; nếu đã có thì tham gia**. Do đó mỗi `@Transactional` không đồng nghĩa với “luôn có transaction vật lý độc lập”.

### Chọn rollback cho checked exception

~~~java
@Transactional(rollbackFor = java.io.IOException.class)
public void importDocument() throws java.io.IOException {
    // Nhiều thao tác database và I/O...
}
~~~

Đây chỉ là **chữ ký/minh họa**, không phải một chương trình chạy độc lập. Với `rollbackFor`, nếu `IOException` thoát khỏi method qua transaction interceptor, Spring cũng chọn rollback. Ngoài ra có `noRollbackFor` để điều chỉnh exception không dẫn đến rollback. Quy tắc rollback ảnh hưởng **cách transaction manager xử lý**, không làm một lỗi I/O trên filesystem hoặc HTTP tự bị hoàn tác.

## 3. `TransactionTemplate`: điều khiển transaction bằng callback

`TransactionTemplate` thuộc `org.springframework.transaction.support`. Nó nhận `PlatformTransactionManager`, tạo/tham gia transaction theo cấu hình rồi gọi một callback do ứng dụng cung cấp.

~~~java
@Service
public class TransferWithTemplate {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate template;

    public TransferWithTemplate(
            JdbcTemplate jdbc,
            PlatformTransactionManager manager) {
        this.jdbc = jdbc;
        this.template = new TransactionTemplate(manager);
    }

    public void transfer(int fromId, int toId, int amount) {
        template.executeWithoutResult(status -> {
            jdbc.update(
                "UPDATE accounts SET balance = balance - ? WHERE id = ?",
                amount, fromId);
            jdbc.update(
                "UPDATE accounts SET balance = balance + ? WHERE id = ?",
                amount, toId);
        });
    }
}
~~~

Đây là class Spring **minh họa**; cần import `Service`, `JdbcTemplate`, `PlatformTransactionManager`, `TransactionTemplate`. Mỗi khi code đi vào `executeWithoutResult`, transaction được điều khiển qua template ngay tại điểm này. Có hai API chính:

- `template.execute(status -> result)` khi muốn trả về giá trị `T`.
- `template.executeWithoutResult(status -> { ... })` khi callback không cần trả kết quả.

Khi callback kết thúc bình thường, template thực hiện logic commit ở ranh giới của nó; khi callback ném unchecked exception hoặc transaction bị đánh dấu rollback-only, hệ thống thực hiện logic rollback phù hợp.

### Rollback chủ động không cần ném exception

~~~java
template.executeWithoutResult(status -> {
    int affected = jdbc.update(
        "UPDATE accounts SET balance = balance - ? WHERE id = ?",
        amount, fromId);

    if (affected != 1) {
        status.setRollbackOnly();
        return;
    }

    jdbc.update(
        "UPDATE accounts SET balance = balance + ? WHERE id = ?",
        amount, toId);
});
~~~

Đoạn trên chỉ chạy trong method có `template`, `jdbc`, `amount`, `fromId`, `toId` đã khai báo. `status.setRollbackOnly()` cho biết transaction **không được commit**. Lệnh `return` ở đây chỉ kết thúc callback `void`; template sẽ xử lý dấu rollback-only. Không có exception tự động thông báo lỗi nghiệp vụ cho tầng gọi: nếu caller cần biết thất bại, hãy trả trạng thái rõ ràng hoặc ném exception phù hợp.

**Không coi `TransactionTemplate` là một connection riêng**: nó cũng dùng transaction manager; trong Spring JDBC, `JdbcTemplate` tham gia transaction đó khi cùng `DataSource`. Nếu chạy trong transaction bên ngoài với propagation `REQUIRED`, rollback-only ở callback có thể ảnh hưởng **cả transaction bên ngoài**.

### Tuỳ biến cấu hình template

~~~java
TransactionTemplate readTemplate = new TransactionTemplate(manager);
readTemplate.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
readTemplate.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);
readTemplate.setTimeout(15);
readTemplate.setReadOnly(true);
~~~

Mảnh mã trên dùng `PlatformTransactionManager manager` và cần import `TransactionDefinition`, `TransactionTemplate`. `TransactionTemplate` có state **cấu hình**, nên nên thiết lập **một lần trước khi dùng chung**; tránh thay timeout, isolation, propagation trên cùng instance đang dùng đồng thời bởi nhiều thread. Có thể dùng các instance khác nhau khi cần chính sách giao dịch khác nhau. `readOnly` là dấu hiệu/hint và không phải cơ chế chặn ghi tuyệt đối trên mọi database.

## 4. So sánh trực tiếp hai API

| Khía cạnh | `@Transactional` | `TransactionTemplate` |
| --- | --- | --- |
| Phong cách | Declarative: khai báo bằng annotation | Programmatic: gọi callback bằng Java |
| Ranh giới transaction | Thường bao quanh method được Spring intercept | Chính xác phạm vi callback `execute` |
| Phụ thuộc proxy | **Có** trong proxy mode mặc định; self-invocation là bẫy | **Không** cần proxy để chính `template.execute` quản lý |
| Quy tắc rollback | Annotation, cấu hình rollback rule, exception thoát khỏi method | Exception và `TransactionStatus.setRollbackOnly()` trong callback |
| Trả kết quả | Method trả giá trị theo chữ ký bình thường | `execute(status -> T)` trả kết quả callback |
| Điều chỉnh cấu hình | Attribute của `@Transactional` | Đặt trên `TransactionTemplate` trước khi gọi |
| Khi nào dễ đọc | Phần lớn service method có một transaction bao trùm | Một đoạn nhỏ cần transaction, nhiều khối có phạm vi khác nhau, rollback chủ động |
| Coupling tới Spring | Annotation trên lớp nghiệp vụ | Tham chiếu trực tiếp `TransactionTemplate` và `TransactionStatus` |
| Chi phí kỹ thuật | Proxy/interceptor, cần hiểu lời gọi qua bean | Callback và code thiết lập template, cần hiểu nested scope |
| JDBC resource | Cùng manager/DataSource khi cấu hình đúng | Cùng manager/DataSource khi cấu hình đúng |

Hai lựa chọn **không loại trừ nhau**: ứng dụng có thể dùng `@Transactional` cho phần lớn service và `TransactionTemplate` tại những đoạn đòi hỏi ranh giới đặc biệt. Tuy nhiên, khi một `TransactionTemplate(REQUIRED)` nằm bên trong method `@Transactional(REQUIRED)`, đó thông thường là **các phạm vi logic cùng tham gia một transaction vật lý**, không phải hai lần commit độc lập.

## 5. Ví dụ Spring Boot + Java 17 chạy được: kiểm chứng hai kiểu transaction

Ví dụ sau chạy độc lập trong một dự án Maven nhỏ, không yêu cầu database server vì sử dụng **H2 in-memory**. Nó minh hoạ:

1. Chuyển 10 thành công bằng `@Transactional`.
2. Gây `IllegalStateException` sau khi trừ tiền bằng `@Transactional`: rollback, số dư không đổi.
3. Chuyển 20 thành công bằng `TransactionTemplate`.
4. Gây lỗi sau khi trừ tiền bằng `TransactionTemplate`: rollback.
5. Gọi `TransactionStatus.setRollbackOnly()` trong template: rollback dù callback kết thúc bình thường.

Điều kiện: **JDK 17+**, Maven 3.9+ và internet hoặc Maven cache có các dependency lần đầu. Bài dùng Spring Boot **3.3.5** làm bản baseline minh họa (dựa trên Spring Framework 6.x); ứng dụng mới nên chọn phiên bản Boot được dự án hỗ trợ và kiểm tra tương thích Java.

Tạo cây thư mục:

~~~text
transaction-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── tx/
                    ├── TxDemoApplication.java
                    └── TransferService.java
~~~

**File `pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
          https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>transaction-demo</artifactId>
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
~~~

**File `src/main/java/demo/tx/TransferService.java`:**

~~~java
package demo.tx;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class TransferService {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate template;

    public TransferService(
            JdbcTemplate jdbc,
            PlatformTransactionManager transactionManager) {
        this.jdbc = jdbc;
        this.template = new TransactionTemplate(transactionManager);
    }

    // Method public được gọi từ bean khác qua Spring proxy.
    @Transactional
    public void annotatedTransfer(int amount, boolean failAfterDebit) {
        transferSteps(amount, failAfterDebit);
    }

    // TransactionTemplate bắt đầu/tham gia transaction ở execute().
    public void templateTransfer(int amount, boolean failAfterDebit) {
        template.executeWithoutResult(status ->
                transferSteps(amount, failAfterDebit));
    }

    // Rollback chủ động, không cần ném exception.
    public void templateRollbackOnly(int amount) {
        template.executeWithoutResult(status -> {
            debit(amount);
            status.setRollbackOnly();
        });
    }

    // Helper private chạy BÊN TRONG transaction của method phía trên.
    private void transferSteps(int amount, boolean failAfterDebit) {
        debit(amount);

        if (failAfterDebit) {
            throw new IllegalStateException("simulated failure");
        }

        int credited = jdbc.update(
                "UPDATE accounts SET balance = balance + ? WHERE id = ?",
                amount, 2);
        if (credited != 1) {
            throw new IllegalStateException("credit did not update one row");
        }
    }

    private void debit(int amount) {
        int debited = jdbc.update(
                "UPDATE accounts SET balance = balance - ? WHERE id = ?",
                amount, 1);
        if (debited != 1) {
            throw new IllegalStateException("debit did not update one row");
        }
    }
}
~~~

**File `src/main/java/demo/tx/TxDemoApplication.java`:**

~~~java
package demo.tx;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class TxDemoApplication implements CommandLineRunner {
    private final JdbcTemplate jdbc;
    private final TransferService transferService;

    public TxDemoApplication(
            JdbcTemplate jdbc,
            TransferService transferService) {
        this.jdbc = jdbc;
        this.transferService = transferService;
    }

    public static void main(String[] args) {
        SpringApplication.run(TxDemoApplication.class, args);
    }

    @Override
    public void run(String... args) {
        // Bảng/dữ liệu mới trên H2 in-memory.
        jdbc.execute("""
            CREATE TABLE accounts (
                id INT PRIMARY KEY,
                balance INT NOT NULL
            )
            """);
        jdbc.update("INSERT INTO accounts(id, balance) VALUES(?, ?)", 1, 100);
        jdbc.update("INSERT INTO accounts(id, balance) VALUES(?, ?)", 2, 100);
        System.out.println("start=" + balances());

        transferService.annotatedTransfer(10, false);
        System.out.println("annotated_success=" + balances());

        try {
            transferService.annotatedTransfer(5, true);
        } catch (IllegalStateException ex) {
            System.out.println("annotated_error=" + ex.getMessage());
        }
        System.out.println("annotated_rollback=" + balances());

        transferService.templateTransfer(20, false);
        System.out.println("template_success=" + balances());

        try {
            transferService.templateTransfer(7, true);
        } catch (IllegalStateException ex) {
            System.out.println("template_error=" + ex.getMessage());
        }
        System.out.println("template_rollback=" + balances());

        transferService.templateRollbackOnly(4);
        System.out.println("rollback_only=" + balances());
    }

    private String balances() {
        Integer a = jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = ?",
                Integer.class, 1);
        Integer b = jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = ?",
                Integer.class, 2);
        return a + "," + b;
    }
}
~~~

**Chạy tại thư mục `transaction-demo/`:**

~~~bash
mvn -q spring-boot:run
~~~

Các **dòng do chương trình tự in** (ngoài các log khởi động/thông báo của Spring Boot và Maven):

~~~text
start=100,100
annotated_success=90,110
annotated_error=simulated failure
annotated_rollback=90,110
template_success=70,130
template_error=simulated failure
template_rollback=70,130
rollback_only=70,130
~~~

### Phân tích chính xác kết quả

- Ban đầu A=100, B=100.
- `annotatedTransfer(10, false)` trừ 10 rồi cộng 10; method trả bình thường, transaction commit, thành 90,110.
- `annotatedTransfer(5, true)` trừ A rồi ném `IllegalStateException` **trước** bước cộng B. Vì exception unchecked thoát khỏi method qua proxy, transaction rollback; cả hai số dư vẫn 90,110.
- `templateTransfer(20, false)` tạo transaction theo `TransactionTemplate` và commit hai update; số dư thành 70,130.
- `templateTransfer(7, true)` ném lỗi trong callback; template rollback, số dư vẫn 70,130.
- `templateRollbackOnly(4)` chạy một `UPDATE` nhưng đặt `status.setRollbackOnly()` trước khi callback kết thúc. Không có exception, song vẫn rollback, nên số dư tiếp tục 70,130.

**Vì sao ví dụ gọi method từ `TxDemoApplication` sang `TransferService`?** Hai lớp là hai Spring bean khác nhau: lời gọi đến `annotatedTransfer` đi qua transactional proxy. Nếu cùng `TransferService` tự gọi `this.annotatedTransfer(...)`, quy tắc proxy có thể bị bỏ qua. Phương thức `transferSteps` là helper private không cần annotation vì nó đã chạy trong transaction đang được thiết lập bởi public method.

**Vì sao H2 tự có transaction manager?** Spring Boot với `spring-boot-starter-jdbc` và H2 trên classpath có thể auto-configure `DataSource`, `JdbcTemplate` và một `PlatformTransactionManager` cho JDBC. `@EnableTransactionManagement` được viết rõ để minh họa cơ chế bật declarative transaction. Trong ứng dụng Boot có auto-configuration thích hợp, thường không cần thêm annotation này thủ công.

**Giới hạn nghiệp vụ ví dụ:** tiền là số nguyên tượng trưng, không kiểm tra số dư đủ, không khóa cạnh tranh, không có idempotency. Với tiền thật, dùng `BigDecimal`/kiểu decimal và thêm các ràng buộc nghiệp vụ, kiểm soát đồng thời phù hợp.

## 6. Exception, commit và rollback: hiểu đúng từng trường hợp

### 6.1. `@Transactional` không rollback mặc định cho mọi `Exception`

Với cấu hình mặc định:

| Điều xảy ra trong method | Kết quả phổ biến khi transaction được Spring quản lý |
| --- | --- |
| Method hoàn thành bình thường, không rollback-only | Commit ở phạm vi chịu trách nhiệm commit |
| `RuntimeException` thoát khỏi method | Rollback/đánh dấu rollback-only |
| `Error` thoát khỏi method | Rollback/đánh dấu rollback-only |
| Checked exception như `IOException` thoát khỏi method | Mặc định **không** yêu cầu rollback, trừ khi có `rollbackFor` hoặc quy tắc chung |
| Method **bắt và nuốt** exception rồi return | Interceptor có thể xem method là thành công; không tự biết lỗi đã được bắt |
| Code tự đánh dấu transaction rollback-only | Transaction không được commit, kể cả khi method return bình thường |

Một lỗi rất thường gặp:

~~~java
@Transactional
public void saveBoth() {
    jdbc.update("INSERT INTO first_table ...");
    try {
        jdbc.update("INSERT INTO second_table ...");
    } catch (RuntimeException ex) {
        logger.warn("Second insert failed", ex);
        // Không rethrow, không đánh dấu rollback-only.
    }
}
~~~

Đây là **mã minh họa không runnable độc lập**: SQL được rút gọn, biến `jdbc`/`logger` chưa khai báo. Nếu lỗi đã được bắt và không làm transaction bị marked rollback-only ở tầng sâu hơn, Spring có thể cố commit phần đầu. Với lỗi JDBC, tài nguyên/transaction có thể cũng đã bị database đưa vào trạng thái không thể commit; không dựa vào việc bắt exception để bảo đảm có thể tiếp tục. Nghiệp vụ cần quyết định cụ thể **ném lại lỗi**, chọn `rollbackFor`, hoặc đánh dấu rollback-only khi thích hợp.

Nếu cần quyết định rollback thủ công trong method `@Transactional`, có thể dùng:

~~~java
TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
~~~

Đây là **API gắn với transaction do proxy/interceptor đang quản lý**; nếu không có transaction aspect phù hợp trong call stack, `currentTransactionStatus()` không phải lựa chọn an toàn. Thông thường nên để exception đúng loại thoát ra hoặc dùng `TransactionTemplate` nếu cần code xử lý rollback rõ ràng.

### 6.2. `TransactionTemplate` với exception và rollback-only

~~~java
String result = template.execute(status -> {
    boolean ok = validateInput();
    if (!ok) {
        status.setRollbackOnly();
        return "REJECTED";
    }

    updateDatabase();
    return "DONE";
});
~~~

Đây là mảnh mã trong class đã có `template` và các method `validateInput()`/`updateDatabase()`; không phải chương trình độc lập. `"REJECTED"` có thể được trả về **trong khi transaction rollback**. Do đó không suy luận “callback trả về giá trị” đồng nghĩa “đã commit”.

Nếu callback ném `RuntimeException`, template sẽ rollback theo đường lỗi. Nếu callback cần gọi API ném checked exception, giao diện callback không khai báo checked exception tùy ý; ứng dụng có thể bọc exception thành unchecked hoặc xử lý và gọi `setRollbackOnly()` theo hợp đồng rõ ràng. Đừng âm thầm bỏ lỗi mà caller cần biết.

### 6.3. Rollback-only từ phạm vi con và `UnexpectedRollbackException`

Giả sử method ngoài có `@Transactional(REQUIRED)` và gọi method con cũng `REQUIRED`. Nếu method con đánh dấu transaction rollback-only, **hai logical scopes có thể cùng dùng một physical transaction**. Method ngoài bắt lỗi rồi cố return bình thường không có nghĩa transaction có thể commit. Khi outer scope cố commit, Spring có thể ném `UnexpectedRollbackException` để báo việc rollback đã xảy ra thay cho commit kỳ vọng.

Đây là hành vi thiết kế nhằm không báo thành công giả cho caller. Muốn phần con commit hoặc rollback **độc lập**, cần cân nhắc `REQUIRES_NEW` với resource/connection riêng, hoặc tổ chức workflow khác; không chỉ bắt exception rồi cho rằng phần ngoài có thể commit.

## 7. Propagation: phạm vi nào thực sự tạo transaction?

**Propagation** định nghĩa cách một scope xử lý transaction hiện tại.

| Chế độ | Khi chưa có transaction | Khi đang có transaction | Điểm cần hiểu |
| --- | --- | --- | --- |
| `REQUIRED` | Tạo mới | Tham gia transaction hiện tại | Mặc định và phù hợp phần lớn service |
| `REQUIRES_NEW` | Tạo mới | Tạm gác phạm vi ngoài, dùng transaction vật lý độc lập | Inner có thể commit/rollback độc lập; có thể cần thêm connection |
| `NESTED` | Thường tạo transaction như `REQUIRED` | Dùng savepoint trong cùng physical transaction nếu transaction manager/DB hỗ trợ | Có thể rollback phạm vi con về savepoint |
| `SUPPORTS` | Chạy không có transaction | Tham gia transaction hiện tại | Không bảo đảm atomicity khi gọi độc lập |
| `MANDATORY` | Báo lỗi | Tham gia transaction hiện tại | Dùng khi hợp đồng yêu cầu caller đã có transaction |
| `NOT_SUPPORTED` | Chạy không có transaction | Tạm ngưng transaction hiện tại | Phù hợp một số công việc không cần transaction |
| `NEVER` | Chạy không có transaction | Báo lỗi | Thể hiện ràng buộc không được có transaction |

Ví dụ declarative:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordAudit() {
    // Công việc JDBC muốn commit/rollback độc lập.
}
~~~

Mảnh mã này cần import `Propagation` và được gọi **qua Spring proxy**, ví dụ từ một bean khác. `REQUIRES_NEW` không nên dùng máy móc để ghi audit cho mọi nghiệp vụ: inner transaction có thể commit ngay cả khi outer rollback, và nó thường cần thêm connection trong khi outer transaction vẫn giữ connection. Thiết kế connection pool phải tính đến tình huống đó.

Cùng ý tưởng với programmatic API:

~~~java
TransactionTemplate auditTemplate = new TransactionTemplate(manager);
auditTemplate.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);

auditTemplate.executeWithoutResult(status -> {
    // Một đoạn độc lập theo cấu hình và khả năng manager.
});
~~~

`NESTED` thường dựa trên JDBC savepoint, không phải cơ chế phổ quát trên mọi transaction manager hoặc DB; trong Spring JDBC, cần kiểm tra `DataSourceTransactionManager`/`JdbcTransactionManager` và khả năng savepoint của driver. Nếu manager không hỗ trợ, có thể ném exception thay vì âm thầm tạo kiểu transaction như kỳ vọng.

**Isolation, timeout và read-only của phạm vi con `REQUIRED` tham gia transaction ngoài thường không thể ghi đè thực chất các đặc tính của transaction vật lý đã tồn tại.** Khi cần quy tắc khác, phải hiểu cách transaction manager xử lý hoặc từ chối sự khác biệt.

## 8. Isolation, read-only và timeout áp dụng ở đâu?

Một annotation rõ ràng hơn:

~~~java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.READ_COMMITTED,
    readOnly = true,
    timeout = 20)
public CustomerReport loadReport() {
    // Truy vấn dữ liệu, trả DTO đã materialize.
}
~~~

Đây là chữ ký minh họa; cần import `Propagation`, `Isolation`, `Transactional` và định nghĩa `CustomerReport`. Những thuộc tính chính:

- **`isolation`**: yêu cầu mức cô lập khi transaction vật lý được tạo; ý nghĩa dirty read, non-repeatable read, phantom read còn phụ thuộc database và cơ chế MVCC/locking. Một isolation level được đặt ở method con tham gia transaction có sẵn không tự nâng isolation của transaction ngoài.
- **`readOnly`**: là hướng dẫn tối ưu/ý định truy cập chỉ đọc; driver, ORM, DB và manager có thể xử lý khác nhau. Không phải tường lửa ngăn mọi câu `UPDATE`.
- **`timeout`**: thời gian giao dịch tối đa theo cách transaction manager hỗ trợ. Timeout không đồng nghĩa hủy ngay mọi truy vấn I/O hoặc lời gọi HTTP đang chặn; cần bổ sung query/network timeout thích hợp.
- **`rollbackFor`, `noRollbackFor`**: tùy biến điều kiện exception làm rollback.

Nên đặt annotation tại **service method** bao quanh một nghiệp vụ hoàn chỉnh; các repository SQL bên dưới tham gia transaction thông qua Spring. Một transaction cực dài bao cả upload file, gọi API bên ngoài, chờ người dùng xác nhận thường làm tăng lock time và giữ connection lâu. Nếu quy trình cần nhiều bước không thể nằm trong một DB transaction ngắn, hãy thiết kế state machine, outbox, retry/idempotency hay saga phù hợp.

## 9. Bẫy của proxy và cách tổ chức mã

### 9.1. Self-invocation: gọi method `@Transactional` từ chính object

~~~java
@Service
public class InvoiceService {
    public void runJob() {
        this.saveInvoice(); // Không đi qua proxy của saveInvoice().
    }

    @Transactional
    public void saveInvoice() {
        // JDBC inserts
    }
}
~~~

Đây là class minh họa. Trong **proxy mode mặc định**, chỉ những lời gọi **đi vào bean thông qua proxy** được interceptor bắt. `this.saveInvoice()` là lời gọi nội bộ nên annotation trên `saveInvoice()` **không tự tạo transaction** ở điểm đó. Nếu `runJob()` đã được gọi trong transaction được tạo ở một tầng khác, JDBC vẫn có thể đang tham gia transaction sẵn có; bẫy là **annotation của method nội bộ không được áp dụng thêm**.

Cách thiết kế thường rõ nhất là tách method có transaction sang một `@Service` khác và gọi qua Spring injection; hoặc đặt `@Transactional` ngay trên entry point phù hợp. Với đoạn logic cần ranh giới chính xác bên trong một method, `TransactionTemplate` cũng là lựa chọn tốt. Không tự gọi qua `AopContext.currentProxy()` nếu có thể tổ chức code rõ hơn.

### 9.2. Method không được proxy intercept

- Đối tượng được tạo bằng `new` thay vì là Spring bean: annotation có thể không được xử lý.
- `private` method không trở thành entry point transaction trong proxy mode; các ràng buộc visibility và proxy style cần được kiểm tra.
- Method `final` hoặc class `final` có thể ngăn class-based proxy override/intercept; interface-based proxy có ràng buộc riêng.
- Gọi method có annotation ngay trong giai đoạn khởi tạo, chẳng hạn `@PostConstruct`, không phải thời điểm đáng tin cậy để đòi transaction proxy đã được áp dụng.
- `@Transactional` trên method `@Async` hay thread mới không tự truyền thread-bound transaction từ caller sang executor.
- Trong môi trường có nhiều transaction manager, cần chọn đúng manager qua qualifier/annotation và bảo đảm các repository dùng đúng resource.

### 9.3. Tại sao `TransactionTemplate` không gặp bẫy self-invocation ở điểm này?

Bởi vì việc mở transaction nằm trong lời gọi Java rõ ràng:

~~~java
public void doWork() {
    template.executeWithoutResult(status -> updateRows());
}
~~~

Dù `doWork()` được gọi từ cùng object, lệnh `template.executeWithoutResult(...)` vẫn chạy. Điều đó **không** có nghĩa nó tự khắc phục việc quản lý sai `DataSource` hay tạo transaction mới độc lập; propagation và manager vẫn quyết định điều đó.

## 10. Transaction chỉ bao phủ những tài nguyên có quản lý phù hợp

Một DB transaction không tự rollback:

- Email đã gửi qua SMTP, HTTP request đã được bên ngoài xử lý.
- File đã ghi/đổi tên trên filesystem.
- Thông báo đã publish sang hệ thống message mà không tham gia cùng cơ chế transaction.
- Một database khác nếu chỉ có hai `DataSourceTransactionManager` độc lập.
- Công việc bất đồng bộ thực thi ở thread khác mà không có transaction riêng đúng cách.

Nếu muốn ghi database và phát sự kiện đáng tin, có thể dùng **transactional outbox**: ghi dữ liệu nghiệp vụ và bản ghi outbox trong cùng DB transaction, sau đó một thành phần khác publish và retry có idempotency. Với distributed transaction thật sự, phải cấu hình cơ chế điều phối phù hợp (ví dụ JTA khi hạ tầng hỗ trợ); `@Transactional` trên một service không tự biến nhiều nguồn thành một transaction phân tán.

### Reactive khác imperative

`@Transactional` có thể được sử dụng trong code reactive **khi dùng `ReactiveTransactionManager` và method trả kiểu reactive thích hợp**. Khi đó context giao dịch được gắn với **Reactor context** chứ không phải ThreadLocal của `PlatformTransactionManager`. Spring khuyến nghị `TransactionalOperator` cho giao dịch reactive programmatic.

Với `JdbcTemplate`, JDBC blocking và `PlatformTransactionManager`, `TransactionTemplate` là công cụ programmatic thích hợp. Không trộn `Mono/Flux` async tùy ý vào callback JDBC rồi giả định transaction tiếp tục ở những thread khác.

## 11. Nên chọn API nào?

Chọn **`@Transactional`** khi:

- Service method thể hiện rõ một nghiệp vụ cần commit/rollback cùng nhau.
- Caller gọi bean qua Spring và quy tắc rollback/propagation có thể khai báo gọn bằng annotation.
- Muốn giữ business code ít phụ thuộc vào `TransactionStatus` và hạ tầng transaction.

Chọn **`TransactionTemplate`** khi:

- Muốn transaction chỉ bao quanh **một đoạn nhỏ** giữa các phần xử lý khác.
- Cần `status.setRollbackOnly()` theo quyết định nghiệp vụ bên trong callback.
- Một method cần nhiều transaction tách biệt hoặc cấu hình khác nhau mà việc phân tách bean/annotation sẽ kém rõ.
- Cần điều khiển ranh giới ngay trong mã Java, không phụ thuộc self-invocation proxy tại điểm gọi.

Dù chọn API nào, quy tắc thiết kế chung là **transaction ngắn, rõ ranh giới, mọi SQL quan trọng cùng resource/manager, kiểm tra số hàng và lỗi rõ ràng, và có integration test chứng minh rollback thật**.

## 12. Kiểm thử những trường hợp dễ sai

| Ca kiểm thử | Kỳ vọng |
| --- | --- |
| Hai SQL thành công trong `@Transactional` | Cả hai được commit |
| SQL thứ hai ném `RuntimeException` | SQL trước rollback, dữ liệu ban đầu không đổi |
| Method ném checked exception không có `rollbackFor` | Xác nhận policy mặc định/cấu hình thực tế; có thể vẫn commit nếu transaction còn hợp lệ |
| Method có `rollbackFor` và exception thoát ra | Rollback khi match rule |
| Exception bị bắt rồi return bình thường | Kiểm tra có rollback-only hay không; tránh giả định luôn rollback |
| Callback `TransactionTemplate` ném unchecked exception | Rollback và exception lan ra caller |
| Callback gọi `setRollbackOnly()` rồi return | Rollback dù không ném lỗi |
| Inner `REQUIRED` đánh dấu rollback-only | Outer không được báo commit thành công; có thể nhận `UnexpectedRollbackException` |
| Inner `REQUIRES_NEW` | Inner tách transaction; quan sát commit/rollback và tác động connection pool |
| `this.methodAnnotated()` | Annotation method nội bộ không tự được proxy intercept |
| Hai `DataSource` khác nhau | Chứng minh resource nào thật sự tham gia manager |
| Thread async/reactive | Kiểm tra propagation transaction theo đúng mô hình, không trông chờ ThreadLocal truyền tự động |

Với integration test, **không vô tình bao toàn bộ test trong `@Transactional` và rollback ở cuối test** nếu mục tiêu là kiểm tra service đã commit/rollback độc lập thế nào: transaction của test có thể khiến SQL cùng tham gia một transaction do test quản lý, che khuất hành vi thực của service. Hãy chọn cấu hình test phù hợp hoặc chạy các lời gọi từ phạm vi bên ngoài transaction test, rồi truy vấn trạng thái database để đối chiếu.

Trong production, theo dõi số connection đang dùng, thời gian chờ pool, thời gian transaction, deadlock, lock timeout, retry rate và lỗi `UnexpectedRollbackException`. Tránh retry toàn bộ nghiệp vụ sau lỗi khi chưa có idempotency phù hợp.

## 13. Câu hỏi tự kiểm tra

1. **Một method `@Transactional` gọi hai câu SQL, sau câu đầu ném `IllegalStateException`. Kết quả?** Nếu đi qua proxy, dùng đúng transaction manager và mặc định rollback, cả hai thay đổi trong transaction được rollback; không commit riêng câu đầu.
2. **`@Transactional` ở method `private` nhưng được gọi từ public method của cùng bean có tạo transaction?** Không thể dựa vào annotation đó trong proxy mode. Hãy đặt ranh giới trên public entry point hoặc cấu trúc bean khác.
3. **`TransactionTemplate.executeWithoutResult` gọi `status.setRollbackOnly()` nhưng không ném exception; callback return. Có commit không?** Không, transaction được đánh dấu rollback-only.
4. **Inner `@Transactional(REQUIRED)` có phải transaction vật lý khác outer `REQUIRED` không?** Thường không; cả hai tham gia cùng transaction vật lý.
5. **Vì sao `REQUIRES_NEW` có thể gây cạn connection pool?** Outer giữ tài nguyên/connection trong lúc inner cần một transaction/connection mới.
6. **Một service gửi email rồi sau đó rollback database. Email có tự rút lại không?** Không; email là side effect ngoài transaction database.
7. **Khi nào chọn `TransactionalOperator`?** Khi dùng transaction reactive, `ReactiveTransactionManager` và reactive pipeline, thay vì callback JDBC blocking.

## 14. Tài liệu chính thức

- Spring Framework, *Using @Transactional*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework, *Programmatic Transaction Management* và `TransactionTemplate`: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework, *Transaction Propagation*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework, *Understanding the Declarative Transaction Implementation*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework, *Rolling Back a Declarative Transaction*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- JavaDoc, `TransactionTemplate`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html