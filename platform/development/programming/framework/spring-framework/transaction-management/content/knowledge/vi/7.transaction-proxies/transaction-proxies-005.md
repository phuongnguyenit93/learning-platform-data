# Self-invocation bỏ qua điểm chặn trong chế độ proxy của Spring Transaction

## 1. Hiện tượng: có @Transactional nhưng phương thức vẫn chạy ngoài transaction

Trong Spring Framework, một phương thức được gắn `@Transactional` **không tự trở thành một khối giao dịch chỉ vì Java gọi nó**. Ở chế độ transaction mặc định (`mode = PROXY`), annotation là metadata được **Spring AOP proxy** và `TransactionInterceptor` sử dụng khi một lời gọi đi **qua proxy** của bean.

**Self-invocation** là lời gọi từ một phương thức của đối tượng đến một phương thức khác **trên cùng đối tượng**, thông qua `this.otherMethod()` hoặc viết ngắn `otherMethod()`. Khi lời gọi đã đi vào **target object**, self-invocation tiếp tục gọi trực tiếp target: nó **không quay lại proxy**, vì vậy transaction advice gắn với phương thức bên trong **không được chạy thêm lần nữa**. Đây là một quy tắc cơ bản của Spring AOP proxy, áp dụng cả với proxy dựa trên JDK interface và proxy dựa trên subclass (CGLIB).

Ví dụ ý tưởng:

~~~java
@Service
public class OrderService {
    public void placeOrder() {
        this.persistOrder(); // Gọi trong cùng instance: bỏ qua advice của persistOrder.
    }

    @Transactional
    public void persistOrder() {
        // Lời gọi tự thân này không tự mở transaction mới.
    }
}
~~~

Đây là đoạn minh họa, chưa có thao tác database hay chương trình chạy độc lập. Nếu `placeOrder()` **không ở trong transaction nào khác**, thì gọi `persistOrder()` theo cách trên không làm `@Transactional` trên `persistOrder()` có hiệu lực. Ngược lại, nếu caller gọi `orderService.persistOrder()` **qua Spring proxy** và các điều kiện giao dịch được cấu hình hợp lệ, advice có cơ hội tạo hoặc tham gia transaction.

**Cần ghi nhớ chính xác:** self-invocation bỏ qua **điểm chặn ở phương thức được gọi**, chứ không có nghĩa mọi lời gọi nội bộ đều không thể chạy trong một transaction. Nếu phương thức bên ngoài đã được proxy mở transaction, code bên trong vẫn có thể dùng transaction ấy. Bài này sẽ chứng minh cả hai tình huống.

## 2. Proxy và target là hai vai trò khác nhau

Một bean được Spring quản lý có thể được trình cho caller qua **proxy**. Proxy giữ trách nhiệm chạy các interceptor liên quan, rồi mới ủy quyền đến method trên target. Với transaction advice, chuỗi thông thường là:

1. Caller giữ tham chiếu bean do Spring inject (`@Autowired`, constructor injection, hoặc `ApplicationContext.getBean`).
2. Caller gọi một method **qua proxy**.
3. `TransactionInterceptor` đọc metadata `@Transactional` trên method phù hợp, chọn transaction manager và bắt đầu/tham gia transaction theo propagation.
4. Proxy ủy quyền method sang **target**.
5. Khi target trả về hoặc ném lỗi, interceptor quyết định commit/rollback theo transaction status và quy tắc rollback.

Khi chính target gọi tiếp `this.inner()`, bước 2–3 **không xảy ra lần thứ hai** cho `inner()`. Một lời gọi Java thông thường không tự “nhìn thấy” annotation và áp dụng AOP.

### 2.1. Sơ đồ hai đường gọi

~~~mermaid
flowchart TD
    A["Caller khác bean"] --> B["Spring AOP proxy"]
    B --> C["TransactionInterceptor<br/>kiểm tra @Transactional"]
    C --> D["Target.outer()"]
    D -->|"this.inner()"| E["Target.inner()"]
    E --> F["Mã truy cập dữ liệu"]
    D -.->|"Lời gọi nội bộ không đi qua"| G["Proxy advice cho inner()"]
    H["Caller khác bean"] -->|"proxy.inner()"| I["Spring AOP proxy"]
    I --> J["TransactionInterceptor<br/>cho inner()"]
    J --> K["Target.inner()"]
~~~

Nhánh trên: `outer()` đã được gọi qua proxy, nhưng `inner()` được gọi trực tiếp trong target. Nhánh dưới: một bean khác gọi `inner()` qua proxy, cho phép Spring xử lý transaction metadata của chính `inner()`.

Đừng diễn giải sơ đồ là “một proxy mới được tạo cho mỗi lần gọi”. Thông thường bean proxy tồn tại sẵn; sự khác biệt nằm ở **đường đi của lời gọi**.

### 2.2. CGLIB không tự sửa được self-invocation

Có hai hình thức proxy thường gặp:

| Proxy | Khi nào phổ biến | Self-invocation |
| --- | --- | --- |
| JDK dynamic proxy | Bean được proxy qua interface phù hợp | `this.inner()` từ target vẫn bỏ qua advice |
| Class-based proxy (thường CGLIB) | Bean được proxy qua subclass, ví dụ service không có interface | `this.inner()` từ target vẫn bỏ qua advice |

Đổi `proxyTargetClass = true` **không biến lời gọi nội bộ thành lời gọi qua proxy**. Class-based proxy có thêm hạn chế về những method không thể override, chẳng hạn `final` hoặc `private`; đó là một vấn đề khác, không phải nguyên nhân gốc của self-invocation.

## 3. @Transactional thực sự làm gì khi đi qua proxy?

`@Transactional` thông thường có propagation mặc định là `REQUIRED`: nếu chưa có transaction phù hợp thì manager mở một transaction mới; nếu đã có thì method tham gia transaction hiện tại. Khi method kết thúc, interceptor quyết định commit hoặc rollback theo tình trạng transaction và rollback rules. Theo mặc định thông dụng của Spring Framework, `RuntimeException` và `Error` gây rollback, còn checked exception không tự gây rollback nếu chưa có rule khác.

Những hành vi đó được kích hoạt **tại transaction boundary có advice**. Không có nghĩa annotation sẽ được kiểm tra một lần nữa cho mọi method call bên trong target. Vì vậy một self-call có thể làm mất hiệu lực riêng của các khai báo:

- `propagation = REQUIRES_NEW`: không mở transaction vật lý độc lập cho inner.
- `propagation = MANDATORY`: không thực hiện kiểm tra bắt buộc “phải có transaction” ở ranh giới inner.
- `propagation = NEVER`: không thực hiện kiểm tra “không được có transaction” riêng cho inner.
- `rollbackFor` / `noRollbackFor`: không xử lý rollback rules của inner tại điểm self-call.
- `readOnly`, `isolation`, `timeout`, `transactionManager`: không áp dụng các thuộc tính transaction **riêng của inner** chỉ vì inner có annotation.
- `NESTED`: không tự thiết lập nested scope/savepoint theo annotation inner.

Nếu caller đã mở transaction, các câu SQL trong inner **có thể vẫn tham gia transaction đang có**, miễn là chúng dùng đúng tài nguyên/transaction manager. Nhưng điều đó không chứng minh `@Transactional` của inner đã được thực thi.

## 4. Ba trường hợp dễ nhầm: không có transaction, có transaction ngoài, và transaction mới độc lập

### 4.1. Outer không có transaction; inner mới có @Transactional

~~~java
@Service
class RegistrationService {
    public void register() {
        saveRegistration();
    }

    @Transactional
    public void saveRegistration() {
        // Ghi database
    }
}
~~~

Nếu một caller bên ngoài gọi `register()` qua bean Spring, `register()` không có transaction metadata riêng, còn `saveRegistration()` được gọi **trực tiếp trên target**. Trường hợp phổ biến với JDBC auto-commit là lệnh ghi có thể được commit theo từng statement, thay vì được gom vào transaction mà người viết kỳ vọng ở `saveRegistration()`.

Kết luận ở đây có điều kiện: **không có transaction bao ngoài từ nguồn khác**. Một transaction test, transaction do caller mở, hoặc callback từ `TransactionTemplate` có thể thay đổi tình huống. Đừng khẳng định “self-invocation luôn làm transactionActive=false”.

### 4.2. Outer đã có transaction; inner dùng @Transactional(REQUIRED)

~~~java
@Service
class OrderService {
    @Transactional
    public void outer() {
        inner();
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void inner() {
        // Mã ở đây chạy bên trong transaction do outer mở,
        // nhưng annotation của inner không có lần advice riêng.
    }
}
~~~

Khi caller đi qua proxy ở `outer()`, manager mở/tham gia transaction. `inner()` là self-call nên **không được intercept riêng**. Các thao tác database của nó vẫn có thể dùng connection của outer; commit/rollback được quyết định ở ranh giới outer.

Trường hợp này dễ bị đánh giá sai vì kiểm tra `TransactionSynchronizationManager.isActualTransactionActive()` trong inner thường trả `true`. Cờ đó chỉ cho biết **context transaction hiện hành đang active**, không chứng minh interception đã xảy ra cho inner.

Nếu inner chỉ là hàm trợ giúp, và bạn thật sự muốn nó nằm cùng transaction với outer, đây có thể là thiết kế hoàn toàn hợp lệ. Không cần thêm `@Transactional` ở helper nếu không cần boundary riêng.

### 4.3. Outer có transaction; inner yêu cầu REQUIRES_NEW

~~~java
@Service
class BillingService {
    @Transactional
    public void outer() {
        this.writeAuditIndependently();
        throw new IllegalStateException("outer failed");
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeAuditIndependently() {
        // Người viết mong audit commit riêng.
    }
}
~~~

Mặc dù inner ghi `REQUIRES_NEW`, self-invocation bỏ qua advice của inner. Vì vậy mã ghi audit vẫn chạy trong transaction của outer nếu dùng cùng resource. Khi outer ném `RuntimeException` và rollback, audit có thể bị rollback theo outer; **không có giao dịch độc lập nào được tạo bởi annotation inner**.

Muốn `REQUIRES_NEW` đúng nghĩa, lời gọi phải qua **proxy transaction hợp lệ** (chẳng hạn một bean dịch vụ khác), hoặc dùng cơ chế transaction chương trình như `TransactionTemplate`.

## 5. Bẫy đặc biệt: bắt exception bên trong outer

Xem một tình huống khác:

~~~java
@Service
class InventoryService {
    @Transactional
    public void outer() {
        try {
            inner();
        } catch (IllegalArgumentException ex) {
            // Quyết định tiếp tục, không rethrow.
        }
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void inner() {
        throw new IllegalArgumentException("rejected");
    }
}
~~~

Nếu lời gọi `inner()` là self-call, không có `TransactionInterceptor` riêng cho inner. Exception bị bắt trong `outer()`, rồi outer trả về bình thường; **nếu không có nguyên nhân rollback-only nào khác**, transaction của outer có thể commit. Đừng suy ra “inner có @Transactional và ném RuntimeException thì outer chắc chắn rollback”.

Nếu refactor inner sang **bean khác**, gọi qua proxy với `REQUIRED` và cùng physical transaction, interceptor của inner có thể đánh dấu transaction chung **rollback-only** khi exception đi qua boundary của inner. Outer bắt exception rồi vẫn cố commit có thể nhận `UnexpectedRollbackException`. Việc bắt exception ở outer không xóa rollback-only marker đã có.

Sự khác nhau này là một trong những lý do cần kiểm thử **kết quả DB sau khi transaction hoàn tất**, không chỉ kiểm tra exception có bị bắt hoặc log có in “active=true” hay không.

## 6. Ví dụ Java 17+ chạy được: so sánh self-call, proxy-call và REQUIRES_NEW

Ví dụ dưới đây sử dụng Spring Boot 3.3.5, Spring JDBC, H2 in-memory và Java 17+. Có bốn tệp; chạy như một ứng dụng dòng lệnh, không cần web server. Một bảng `account` chứa một dòng số dư ban đầu 100. Chương trình chứng minh:

1. Self-call đến method `@Transactional` khi outer không có transaction: lần UPDATE đầu có thể auto-commit; exception không khiến nó rollback.
2. Gọi chính method ấy qua Spring proxy: transaction được tạo, exception gây rollback.
3. Self-call vào method `REQUIRES_NEW` từ outer có transaction: inner không tạo transaction độc lập; outer rollback làm mất thay đổi.
4. Gọi method `REQUIRES_NEW` trên **bean khác** từ outer: inner commit độc lập; outer rollback không hủy commit đã xảy ra ở inner.

### 6.1. Cấu trúc tệp

~~~text
self-invocation-demo/
├── pom.xml
└── src/main/java/example/selfinvoke/
    ├── SelfInvocationApplication.java
    ├── AccountService.java
    └── IndependentWriter.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>self-invocation-demo</artifactId>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
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

### 6.3. SelfInvocationApplication.java

~~~java
package example.selfinvoke;

import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class SelfInvocationApplication {

    public static void main(String[] args) {
        SpringApplication.run(SelfInvocationApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource source) {
        return new JdbcTransactionManager(source);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc, AccountService account) {
        return args -> {
            jdbc.execute("CREATE TABLE account (id INT PRIMARY KEY, amount INT NOT NULL)");
            jdbc.update("INSERT INTO account (id, amount) VALUES (?, ?)", 1, 100);
            System.out.println("START=" + amount(jdbc));

            account.callSelf();
            System.out.println("AFTER_SELF=" + amount(jdbc));

            try {
                account.incrementThenFail(10); // Caller -> proxy -> target
            } catch (IllegalStateException ex) {
                System.out.println("PROXY_CAUGHT=" + ex.getMessage());
            }
            System.out.println("AFTER_PROXY=" + amount(jdbc));

            try {
                account.outerSelfNew();
            } catch (IllegalStateException ex) {
                System.out.println("SELF_NEW_CAUGHT=" + ex.getMessage());
            }
            System.out.println("AFTER_SELF_REQUIRES_NEW=" + amount(jdbc));

            try {
                account.outerOtherBean();
            } catch (IllegalStateException ex) {
                System.out.println("BEAN_NEW_CAUGHT=" + ex.getMessage());
            }
            System.out.println("AFTER_SEPARATE_REQUIRES_NEW=" + amount(jdbc));
        };
    }

    private static Integer amount(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
            "SELECT amount FROM account WHERE id = ?", Integer.class, 1
        );
    }
}
~~~

### 6.4. AccountService.java

~~~java
package example.selfinvoke;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class AccountService {

    private final JdbcTemplate jdbc;
    private final IndependentWriter writer;

    public AccountService(JdbcTemplate jdbc, IndependentWriter writer) {
        this.jdbc = jdbc;
        this.writer = writer;
    }

    // Method này không khai báo transaction.
    public void callSelf() {
        try {
            this.incrementThenFail(10); // Bỏ qua TransactionInterceptor của inner.
        } catch (IllegalStateException ex) {
            System.out.println("SELF_CAUGHT=" + ex.getMessage());
        }
    }

    @Transactional
    public void incrementThenFail(int delta) {
        System.out.println(
            "INNER_TX_ACTIVE="
                + TransactionSynchronizationManager.isActualTransactionActive()
        );
        jdbc.update(
            "UPDATE account SET amount = amount + ? WHERE id = ?", delta, 1
        );
        throw new IllegalStateException("boom");
    }

    @Transactional
    public void outerSelfNew() {
        this.incrementRequiresNew(20); // Inner annotation bị bỏ qua.
        throw new IllegalStateException("outer-fail");
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void incrementRequiresNew(int delta) {
        System.out.println(
            "SELF_NEW_TX_ACTIVE="
                + TransactionSynchronizationManager.isActualTransactionActive()
        );
        jdbc.update(
            "UPDATE account SET amount = amount + ? WHERE id = ?", delta, 1
        );
    }

    @Transactional
    public void outerOtherBean() {
        writer.incrementIndependently(20); // Đi qua proxy của bean khác.
        throw new IllegalStateException("outer-fail");
    }
}
~~~

### 6.5. IndependentWriter.java

~~~java
package example.selfinvoke;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IndependentWriter {

    private final JdbcTemplate jdbc;

    public IndependentWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void incrementIndependently(int delta) {
        jdbc.update(
            "UPDATE account SET amount = amount + ? WHERE id = ?", delta, 1
        );
    }
}
~~~

Chạy ở thư mục chứa `pom.xml`:

~~~bash
mvn -q spring-boot:run
~~~

Ứng dụng tự in các dòng sau theo thứ tự. Spring Boot/Hikari có thể thêm log khởi động khác:

~~~text
START=100
INNER_TX_ACTIVE=false
SELF_CAUGHT=boom
AFTER_SELF=110
INNER_TX_ACTIVE=true
PROXY_CAUGHT=boom
AFTER_PROXY=110
SELF_NEW_TX_ACTIVE=true
SELF_NEW_CAUGHT=outer-fail
AFTER_SELF_REQUIRES_NEW=110
BEAN_NEW_CAUGHT=outer-fail
AFTER_SEPARATE_REQUIRES_NEW=130
~~~

**Giải thích từng kết quả:**

- **START=100:** dữ liệu khởi tạo bên ngoài service transaction.
- **INNER_TX_ACTIVE=false:** `callSelf()` không có transaction, còn lời gọi `this.incrementThenFail(...)` không qua advice. `JdbcTemplate` chạy UPDATE trên connection bình thường; với H2 và thiết lập JDBC mặc định trong ví dụ, statement được auto-commit.
- **AFTER_SELF=110:** mặc dù method annotated ném `IllegalStateException`, transaction advice không chạy cho lần self-call này nên không có rollback của method đó; update +10 được giữ.
- **INNER_TX_ACTIVE=true** ở lần gọi thứ hai: caller gọi `account.incrementThenFail(...)` qua Spring bean proxy. Spring mở transaction, UPDATE +10 diễn ra trong transaction và exception kích hoạt rollback.
- **AFTER_PROXY=110:** kết quả rollback giữ nguyên số dư sau lần self-call.
- **SELF_NEW_TX_ACTIVE=true:** `outerSelfNew()` được proxy mở transaction. Self-call bên trong không tạo transaction khác nhưng vẫn nhìn thấy transaction outer, nên cờ active là true.
- **AFTER_SELF_REQUIRES_NEW=110:** method inner annotated `REQUIRES_NEW` chạy trực tiếp trên target; update +20 bị rollback cùng transaction outer.
- **AFTER_SEPARATE_REQUIRES_NEW=130:** `IndependentWriter` là bean khác. Lời gọi từ `AccountService` đi qua proxy của writer, `REQUIRES_NEW` mở transaction độc lập rồi commit +20. Exception ở outer sau đó rollback transaction ngoài, không hủy được +20 đã commit.

Với `REQUIRES_NEW` thực sự, transaction manager thường cần **một connection khác** trong khi outer đang giữ connection. Ví dụ dùng pool Hikari mặc định của Boot, đủ cho luồng đơn; ở hệ thống có concurrency cao phải tính kích thước pool phù hợp, tránh giữ nhiều connection chờ nhau.

**Điểm quan sát quyết định** là số dư sau khi transaction hoàn tất. Chỉ nhìn `INNER_TX_ACTIVE=true` hoặc `SELF_NEW_TX_ACTIVE=true` chưa đủ để kết luận inner annotation đã được intercept.

## 7. Cách sửa được khuyến nghị: tách ranh giới transaction thành bean riêng

Khi một helper cần có propagation hoặc rollback policy **khác** method caller, hãy thiết kế nó thành một service/bean có ranh giới rõ ràng:

~~~mermaid
flowchart LR
    A["Client"] --> B["OrderService proxy"]
    B --> C["OrderService.outer()"]
    C --> D["AuditService proxy"]
    D --> E["TransactionInterceptor<br/>REQUIRES_NEW"]
    E --> F["AuditService.writeAudit()"]
    F --> G[("Database")]
~~~

Ví dụ minh họa độc lập về cấu trúc (các kiểu `Order`/`Audit` và repository giả định):

~~~java
@Service
class OrderService {
    private final AuditService audit;

    OrderService(AuditService audit) {
        this.audit = audit;
    }

    @Transactional
    public void submit(Order order) {
        // Lưu đơn hàng trong transaction ngoài.
        audit.writeAudit(order.id());
    }
}

@Service
class AuditService {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeAudit(long orderId) {
        // Lưu audit theo transaction vật lý độc lập.
    }
}
~~~

Mỗi service nhận dependency qua constructor. Spring quản lý hai bean, và `OrderService` gọi **bean proxy của `AuditService`** thay vì `this.writeAudit()`. Ranh giới transaction trở nên rõ để đọc, kiểm thử và kiểm soát resource.

Tuy nhiên không nên dùng `REQUIRES_NEW` chỉ để “sửa self-call” nếu nghiệp vụ thực sự cần atomicity của cả đơn hàng và audit. Khi inner commit độc lập, outer rollback **không hoàn tác** inner nữa; một audit record có thể tồn tại trong khi order không được commit. Chọn propagation theo yêu cầu nghiệp vụ trước, rồi mới chọn kiến trúc gọi bean.

## 8. Cách sửa khi không cần một transaction riêng

Không phải mọi self-call đều là bug. Nếu yêu cầu đơn giản là mọi công đoạn dùng **cùng một transaction**, đặt `@Transactional` ở **method public là entrypoint từ bean khác**, rồi để helper bên trong thực hiện công việc:

~~~java
@Service
class CheckoutService {
    @Transactional
    public void checkout() {
        reserveStock();
        chargeAccount();
        saveInvoice();
    }

    private void reserveStock() { /* Cùng transaction của checkout */ }
    private void chargeAccount() { /* Cùng transaction của checkout */ }
    private void saveInvoice() { /* Cùng transaction của checkout */ }
}
~~~

Đây là pseudo-code về cấu trúc (không chứa mã dữ liệu), không phải ứng dụng chạy độc lập. Điều kiện: `checkout()` được gọi **qua Spring proxy** và các repository dùng tài nguyên đúng với manager. Những helper private **không cần annotation riêng** khi chúng chỉ là các bước trong cùng transaction.

Lợi ích: người đọc thấy rõ một transaction boundary duy nhất. Nếu sau này yêu cầu một helper có `REQUIRES_NEW`, `NESTED`, timeout hay rollback rule riêng, hãy tách boundary đó ra đúng cách, tránh chỉ gắn annotation vào helper hiện tại.

## 9. Các giải pháp khác và giới hạn

### 9.1. TransactionTemplate: chủ động tạo scope ngay trong cùng bean

`TransactionTemplate` dùng trực tiếp transaction manager qua callback; nó không cần một cuộc gọi đi qua Spring AOP proxy để kích hoạt transaction. Vì vậy đây là lựa chọn phù hợp nếu code muốn giữ một bean nhưng cần boundary tường minh ở một đoạn xử lý.

~~~java
// Trích đoạn trong một Spring bean đã có JdbcTemplate jdbc
// và PlatformTransactionManager transactionManager.
TransactionTemplate tx = new TransactionTemplate(transactionManager);
tx.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);

tx.executeWithoutResult(status -> {
    jdbc.update(
        "UPDATE account SET amount = amount + ? WHERE id = ?", 20, 1
    );
});
~~~

Imports cho trích đoạn: `org.springframework.transaction.support.TransactionTemplate` và `org.springframework.transaction.TransactionDefinition`. Trong một method `@Transactional` của outer, callback này có thể tạo transaction độc lập phù hợp `REQUIRES_NEW`; transaction manager phải hỗ trợ suspend/resume. Chỉ lưu ý rằng template là **programmatic transaction boundary** và code biết trực tiếp đến transaction API; nhiều ứng dụng service declarative thường sẽ dễ đọc hơn khi tách bean.

### 9.2. Self injection: gọi qua một tham chiếu proxy của chính bean

Spring AOP có thể hỗ trợ gọi tới proxy qua một tham chiếu tới chính bean, ví dụ một tham chiếu được inject có lazy resolution, rồi gọi `self.inner()`. Nhưng phải bảo đảm `self` thật sự là **proxy**, không phải raw target, tránh vòng phụ thuộc và làm thiết kế khó hiểu. Spring cũng xem self injection là giải pháp thay thế khi không refactor được; nó không phải mặc định đầu tiên cho kiến trúc nghiệp vụ.

Trong môi trường nhiều transaction manager hoặc JDK proxy theo interface, tên kiểu của tham chiếu có thể quan trọng: method muốn gọi phải được expose qua kiểu proxy thích hợp. Đừng tùy tiện inject chính class của mình nếu proxy chỉ cung cấp interface.

### 9.3. AopContext.currentProxy(): giải pháp cuối cùng

Có thể gọi qua `AopContext.currentProxy()` khi Spring AOP được cấu hình **exposeProxy=true**, rồi ép kiểu đúng interface/class proxy. Nhưng cách này ràng buộc code nghiệp vụ trực tiếp với Spring AOP, có thể ném exception nếu không đang ở đúng invocation context hoặc chưa bật exposeProxy. Tài liệu Spring khuyến nghị tránh giải pháp này khi có thể refactor.

Không đồng nhất `AopContext.currentProxy()` với `this`. Chỉ thao tác đầu tiên có khả năng đi qua proxy, và nó phụ thuộc hạ tầng/proxy context được cấu hình đúng.

### 9.4. AspectJ mode: weaving thay vì proxy

`@EnableTransactionManagement(mode = AdviceMode.ASPECTJ)` có thể dùng **bytecode weaving** để áp dụng transaction advice mà không cần lời gọi đi qua một Spring AOP proxy; khi cấu hình đúng, self-invocation không gặp giới hạn proxy này. Tuy nhiên cần `spring-aspects` và thiết lập compile-time hoặc load-time weaving tương ứng, cùng những cân nhắc về build và vận hành.

Đây là **cơ chế khác**, không phải hiệu quả tự động khi thêm một annotation `@EnableTransactionManagement`. Annotation trên interface cũng có hạn chế trong AspectJ mode; nên gắn `@Transactional` trên concrete class/method. Không bật AspectJ chỉ vì một helper nhỏ có self-call nếu tách bean hoặc đặt boundary ở entrypoint đã giải quyết rõ yêu cầu.

## 10. Cách phát hiện self-invocation trong một dự án thật

Hãy xem **call graph** thay vì chỉ tìm chỗ xuất hiện `@Transactional`:

1. Xác định **entrypoint**: controller, scheduler, listener, job, caller bean nào gọi service?
2. Xác định object reference tại mỗi cạnh: field do Spring inject, method call trên bean khác, hay `this.` / lời gọi không có qualifier trong cùng class?
3. Xác nhận transaction được kích hoạt trong application context phù hợp. Spring Boot thường hỗ trợ transaction auto configuration khi có transaction manager, nhưng annotation trên một object tự khởi tạo bằng `new` không tự có advice.
4. Ghi lại propagation cần thiết ở **từng boundary**: một transaction chung hay một transaction mới?
5. Xem nơi exception đi qua ranh giới nào và nơi nào bị catch. Với default rollback rules, `RuntimeException` phải đi qua boundary được intercept để rule đó có tác dụng.
6. Nếu nghi ngờ, viết integration test gây lỗi sau một lệnh ghi và đọc dữ liệu **sau khi method hoàn tất**, từ một caller không bị bọc transaction test.
7. Chỉ khi đã chứng minh kết quả, mới chọn refactor sang bean khác hoặc bỏ annotation thừa trên helper.

Có thể bật log thử nghiệm:

~~~properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
~~~

Log có thể hiển thị việc advice tạo hoặc hoàn tất transaction ở mỗi proxy boundary, nhưng thông điệp phụ thuộc manager/version. Không thấy log ở `inner()` không đồng nghĩa “mọi thao tác trong inner đều nằm ngoài transaction”; hãy đối chiếu với transaction hiện có của outer và trạng thái database.

### 10.1. Dùng TransactionSynchronizationManager đúng mức

Trong ứng dụng imperative có transaction đồng bộ với thread:

~~~java
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();

boolean readOnly =
    TransactionSynchronizationManager.isCurrentTransactionReadOnly();
~~~

Đây là **trích đoạn minh họa**, không phải chương trình độc lập. Nó kiểm tra context transaction hiện hành, **không** cung cấp cờ “@Transactional của method này đã chạy advice hay chưa”. Trong self-call từ outer có transaction, `active` vẫn true dù inner không mở boundary mới.

Với reactive transaction dùng `ReactiveTransactionManager`, transaction context có thể nằm trong **Reactor subscriber Context**, nên không áp dụng nguyên cách đọc `ThreadLocal` của imperative. Dù ở chế độ reactive, nếu dựa trên Spring AOP proxy thì self-invocation vẫn là vấn đề đường đi lời gọi; cần giữ publisher trong đúng pipeline và proxy boundary.

### 10.2. Kiểm thử rollback chính xác

Trong test Spring, `@Transactional` ở test method có thể làm service `REQUIRED` tham gia transaction test và sau đó rollback theo quy tắc TestContext, khiến kết quả bị hiểu sai. Để thử self-invocation:

- Dùng một test caller **không** tự có `@Transactional`, inject service từ Spring context và gọi public method qua bean.
- Dùng database cô lập cho mỗi test hoặc reset dữ liệu trước mỗi case.
- Sau khi service return/throw, đọc số dư từ một lời gọi khác bên ngoài transaction đang thử.
- Kiểm tra **cả dữ liệu và exception**: self-call ném lỗi nhưng cập nhật vẫn có thể đã commit; proxy-call ném lỗi và cập nhật rollback.
- Với `REQUIRES_NEW`, xác nhận inner đã commit độc lập bằng kết quả tồn tại sau khi outer rollback.

Khi transaction có nhiều tài nguyên, việc một DAO dùng connection sai manager có thể tạo kết quả giống lỗi self-invocation. Vì vậy kiểm tra thêm transaction manager, `DataSource` hoặc `ConnectionFactory` được inject. Nếu ứng dụng chạy trên multi-tenant/routing datasource, xác nhận resource key thực tế nữa.

## 11. Các hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Đã có `@Transactional` ở inner thì luôn mở transaction.” | Chỉ khi invocation được advice áp dụng hoặc boundary khác chủ động tạo transaction. |
| “`this.inner()` khác `inner()`.” | Cả hai đều self-invocation trên cùng target. |
| “Chuyển sang CGLIB sẽ bắt được self-call.” | Class-based proxy không đổi đường gọi trực tiếp trên target. |
| “Inner nhìn thấy `active=true` nên `REQUIRES_NEW` đã chạy.” | Cờ active có thể do outer mở; cần kiểm tra transaction vật lý và kết quả commit. |
| “Self-call luôn không có transaction.” | Sai khi outer/caller đã mở transaction phù hợp. |
| “Inner ném RuntimeException thì outer chắc chắn rollback.” | Nếu self-call bỏ qua inner advice và outer catch exception rồi return, có thể commit. |
| “Inner `rollbackFor` vẫn được áp dụng dù gọi nội bộ.” | Annotation của inner không được xử lý riêng tại điểm self-call. |
| “`@Transactional` trên private/final helper là cách sửa.” | Proxy mode không thể advice nhiều dạng method không intercept được; thay đổi visibility không sửa self-call. |
| “Spring bean ở đâu cũng có proxy.” | Phải có transaction infrastructure, method/bean được proxy nhận diện; object tạo bằng `new` không phải bean proxy. |
| “Dùng `@PostConstruct` gọi transactional method sẽ mở transaction.” | Proxy có thể chưa hoàn tất khởi tạo; không dựa vào proxy transaction ở init callback. |
| “Dùng `REQUIRES_NEW` bên ngoài luôn an toàn.” | Nó commit độc lập; có thể phá atomicity và cần thêm connection. |
| “AspectJ mode chỉ là một flag không cần cấu hình khác.” | Cần weaving và dependency phù hợp; không tự kích hoạt khi chưa chuẩn bị hạ tầng. |

## 12. Bài tập dự đoán đường gọi và kết quả

**Tình huống A:** Controller gọi `service.outer()` qua proxy; `outer()` không annotate và gọi `this.inner()`; `inner()` có `@Transactional(rollbackFor=Exception.class)`, update DB rồi ném checked exception. Không có transaction ngoài, driver JDBC mặc định auto-commit. Dự đoán: annotation inner bị bỏ qua; UPDATE có thể đã commit theo từng statement. Khi exception thoát ra, không có Spring transaction của inner để rollback.

**Tình huống B:** `outer()` có `@Transactional`; inner có `@Transactional(REQUIRES_NEW)` và dùng cùng JDBC template. Outer gọi `this.inner()` rồi ném RuntimeException. Dự đoán: inner không có transaction mới; thay đổi thuộc outer và bị rollback nếu chưa có side effect ngoài transaction.

**Tình huống C:** Giữ B, nhưng chuyển inner thành method public trên một bean Spring khác, được inject và gọi qua proxy. Dự đoán: transaction inner `REQUIRES_NEW` có thể commit riêng, sau đó outer rollback không hủy commit inner. Nghiệp vụ cần chấp nhận trạng thái đó.

**Tình huống D:** Outer `@Transactional` gọi `this.inner()`, inner ném `IllegalStateException` nhưng outer catch và trả về bình thường. Dự đoán: nếu chỉ có lỗi Java này, không có rollback-only marker khác, outer có thể commit. Nếu inner nằm ở bean khác và dùng `REQUIRED`, advice của inner có thể đánh dấu rollback-only khiến outer commit thất bại với `UnexpectedRollbackException`.

**Tình huống E:** Một component gọi `this.inner()` trong `@PostConstruct`. Dự đoán: không dựa vào transaction advice vì proxy có thể chưa được thiết lập; chuyển khởi tạo cần transaction sang một cơ chế lifecycle sau khi context/proxy hoàn chỉnh, hoặc điều phối bằng service/template rõ ràng.

## 13. Checklist quyết định thiết kế

Khi thấy code `outer() -> inner()` trong cùng class, hãy trả lời:

1. Outer đã được Spring quản lý và **được gọi qua proxy** chưa?
2. Inner cần **cùng transaction** hay **boundary độc lập** (chẳng hạn `REQUIRES_NEW`)?
3. Nếu cùng transaction, có thể đặt annotation ở outer và giữ inner là helper đơn giản?
4. Nếu độc lập, có thể tách inner thành bean khác và gọi qua proxy?
5. Exception ở inner có được advice thấy không, hay bị outer catch trước boundary?
6. Có ambient transaction từ caller/test/`TransactionTemplate` khiến kết quả quan sát bị lệch không?
7. Manager và connection có đúng resource không, và transaction đã **commit/rollback** thật sau khi scope kết thúc chưa?

**Kết luận kỹ thuật:** self-invocation là **vấn đề đường đi lời gọi qua AOP proxy**. Annotation ở method nội bộ vẫn tồn tại trong mã nguồn, nhưng trong proxy mode nó không tạo thêm transaction advice khi code gọi `this.method()`. Thiết kế boundary ở entrypoint phù hợp, tách bean cho những scope cần chính sách riêng, hoặc dùng transaction API tường minh sẽ giúp hành vi commit/rollback khớp với nghiệp vụ.

## Tài liệu tham khảo chính thức

- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxy mode, giới hạn self-invocation, mặc định và AspectJ mode.
- [Spring Framework — AOP Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): phân biệt proxy/target, self-call và các cách khắc phục.
- [Spring Framework — Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): vai trò transaction advice/interceptor.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED`, `REQUIRES_NEW` và rollback-only khi tham gia transaction.
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionTemplate` và `PlatformTransactionManager`.
