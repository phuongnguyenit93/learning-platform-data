# Isolation của lời gọi tham gia so với giao dịch mới trong Spring Transaction Management

## 1. Câu hỏi cốt lõi: khai báo SERIALIZABLE ở inner có làm thay đổi outer không?

Giả sử một service Spring đã mở transaction với mức cô lập `READ_COMMITTED`. Trong transaction ấy, service gọi một method của bean khác:

~~~java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.SERIALIZABLE
)
public void processCriticalStep() {
    // Thực thi JDBC/ORM ở đây.
}
~~~

Liệu method bên trong có chạy ở `SERIALIZABLE` vì annotation yêu cầu mức mạnh hơn? **Không nhất thiết — trong kịch bản tham gia transaction hiện hữu, mặc định Spring thường bỏ qua isolation được khai báo riêng ở inner.** `PROPAGATION_REQUIRED` của inner tham gia **cùng physical transaction** đã được outer mở. Một physical transaction đang hoạt động không tự được chuyển mức isolation chỉ vì một logical scope mới bắt đầu.

Ngược lại, nếu chính method đó **mở một physical transaction mới** (vì trước đó chưa có transaction và dùng `REQUIRED`, hoặc chủ động dùng `REQUIRES_NEW`), Spring có cơ hội thiết lập isolation lên connection/resource trước khi thực thi SQL. Khi manager/driver/database hỗ trợ, isolation mới có thể thực sự được áp dụng.

Đây là hai quy tắc khác nhau:

1. **Chọn metadata**: Spring đọc `@Transactional(isolation = ...)` của method theo vị trí annotation có hiệu lực.
2. **Áp dụng isolation lên tài nguyên**: một isolation declaration thường chỉ tác động khi **transaction vật lý mới bắt đầu**, không có quyền viết lại một transaction hiện hữu được scope khác sở hữu.

Nói ngắn gọn, **method inner có annotation riêng không đồng nghĩa method inner có physical transaction riêng**.

Bài này trình bày: isolation là gì, cách Spring xử lý `REQUIRED`/`REQUIRES_NEW`/`NESTED`, khi nào manager từ chối mismatch nhờ `validateExistingTransaction`, cách quan sát isolation **thực tế trên JDBC connection**, và thiết kế test để tránh kết luận sai.

## 2. Isolation thuộc về physical transaction, không thuộc một đoạn Java code độc lập

Một **mức cô lập transaction** định nghĩa cách những thao tác trong một transaction nhìn thấy hoặc tương tác với thao tác từ các transaction khác, theo khả năng của DB/driver. Các mức trong Spring `Isolation` ánh xạ sang hằng JDBC tương ứng:

| Spring `Isolation` | JDBC constant | Ý nghĩa khái quát |
| --- | --- | --- |
| `DEFAULT` | Mặc định của hệ transaction/database | Không ép một mức cụ thể từ annotation |
| `READ_UNCOMMITTED` | `Connection.TRANSACTION_READ_UNCOMMITTED` | Trong hệ hỗ trợ đúng nghĩa, có thể thấy dữ liệu chưa commit của transaction khác |
| `READ_COMMITTED` | `Connection.TRANSACTION_READ_COMMITTED` | Ngăn dirty read; cách xử lý non-repeatable read/phantom tùy hệ |
| `REPEATABLE_READ` | `Connection.TRANSACTION_REPEATABLE_READ` | Nhắm đến độ ổn định khi đọc lại hàng, theo semantics DB |
| `SERIALIZABLE` | `Connection.TRANSACTION_SERIALIZABLE` | Mức cô lập mạnh nhất trong mô hình chuẩn, tương đương hiệu ứng một thứ tự thực thi tuần tự khi hệ thực hiện đúng |

**Các cảnh báo quan trọng về mức cô lập:**

- `Isolation.DEFAULT` **không đồng nghĩa** `READ_COMMITTED` ở mọi database. Đây là lệnh để manager để nguồn tài nguyên chọn giá trị mặc định. H2/PostgreSQL thường khởi đầu với READ_COMMITTED, nhưng phải kiểm tra hệ đang chạy.
- Một driver/database có thể **không hỗ trợ** một isolation level được yêu cầu, hoặc có semantics/kiểu MVCC khác cách mô tả đơn giản trong sách. Không tự suy từ enum Spring rằng mọi hiện tượng concurrency chắc chắn biến mất.
- Isolation không thay thế ràng buộc UNIQUE, khóa đúng cách, retry cho serialization failure hay thiết kế invariants nghiệp vụ.
- Spring `@Transactional` thường dùng `Isolation.DEFAULT`. Chỉ đặt `SERIALIZABLE` khi có lý do về consistency, không xem nó là “cấu hình an toàn nhất cho mọi lời gọi”.

Trong Spring JDBC, transaction manager thường dùng `Connection.setTransactionIsolation(...)` ở giai đoạn bắt đầu transaction mới khi isolation khác `DEFAULT`; nó cũng cố khôi phục trạng thái connection trước khi trả pool sau transaction. Thao tác setting này phải phù hợp contract driver/DB. Transaction được mở qua JPA, JTA hoặc R2DBC có thể quản lý isolation theo cách khác và không phải manager nào cũng hỗ trợ tất cả mức.

## 3. Logical transaction scope và physical transaction: nơi hiểu nhầm bắt đầu

Spring phân biệt:

- **Logical scope**: mỗi lần method đi qua declarative transaction advice có một transaction definition/status cho lời gọi đó (ví dụ outer `@Transactional` và inner `@Transactional` ở hai Spring beans).
- **Physical transaction**: transaction thật ở tài nguyên, ví dụ JDBC connection/DB transaction có begin, commit hoặc rollback.

Với `PROPAGATION_REQUIRED`, nếu chưa có transaction, logical scope tạo một physical transaction mới; nếu đã có, logical scope **join** physical transaction đang tồn tại. Nhiều logical scopes có thể cùng dùng một transaction vật lý.

~~~mermaid
flowchart TD
    A["Client -> OuterService proxy"] --> B["Outer @Transactional<br/>isolation=READ_COMMITTED"]
    B --> C["Physical transaction T1<br/>JDBC Connection C1<br/>READ_COMMITTED"]
    C --> D{"Inner qua proxy<br/>propagation?"}
    D -->|"REQUIRED: join"| E["Logical scope inner<br/>khai báo SERIALIZABLE"]
    E --> F["Vẫn dùng T1 và C1<br/>isolation thực tế READ_COMMITTED<br/>nếu validate=false"]
    D -->|"REQUIRES_NEW"| G["Suspend T1 và C1"]
    G --> H["Begin physical transaction T2<br/>Connection C2<br/>SERIALIZABLE nếu hỗ trợ"]
    H --> I["Commit/rollback T2<br/>resume T1 trên C1"]
    F --> J["Outer commit/rollback T1"]
    I --> J
~~~

Sơ đồ giả định một `DataSource`/`JdbcTransactionManager`, outer đã sử dụng JDBC connection, và annotation của inner **thực sự được intercept**. Nếu outer có isolation khác, giá trị physical transaction sẽ theo outer khi inner join. Nếu không có outer transaction, `REQUIRED` của inner sẽ tự mở mới và không còn nhánh “join”.

### 3.1. Cùng một method nhưng hai đường gọi khác nhau

~~~java
@Service
class RiskService {
    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.SERIALIZABLE
    )
    public void assess() {
        // ...
    }
}
~~~

Giả định `assess()` được gọi qua Spring proxy:

- **Caller ngoài transaction:** `REQUIRED` tạo T2 mới; khi manager hỗ trợ, nó yêu cầu `SERIALIZABLE` cho T2.
- **Caller đang ở T1 READ_COMMITTED:** `REQUIRED` join T1; isolation của T1 thường vẫn là `READ_COMMITTED`, dù method định nghĩa `SERIALIZABLE`.
- **Caller đang ở T1 SERIALIZABLE:** `REQUIRED` join T1; không cần thay isolation vì đã cùng mức, nhưng đó không phải vì inner đã tạo một physical transaction mới.
- **Caller đang ở T1 với isolation DEFAULT:** phải biết mức thực tế của JDBC connection, và semantics của strict validation có thể phụ thuộc isolation metadata mà Spring lưu cho T1; không đánh đồng giá trị “DEFAULT” với một JDBC constant cụ thể.

Câu hỏi thiết kế không chỉ là “inner ghi isolation nào?”, mà là **“lời gọi ấy join transaction sẵn có hay thực sự tạo transaction mới?”**.

## 4. PROPAGATION_REQUIRED: mặc định join và bỏ qua isolation inner

Đây là tình huống thường gặp trong service layer:

~~~java
@Service
class CheckoutService {
    private final FraudService fraud;

    CheckoutService(FraudService fraud) {
        this.fraud = fraud;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void checkout() {
        // T1 được tạo ở đây khi không có outer transaction.
        fraud.checkAndUpdate();
    }
}

@Service
class FraudService {
    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.SERIALIZABLE
    )
    public void checkAndUpdate() {
        // Tham gia T1 thay vì tự mở T2.
    }
}
~~~

Đây là ví dụ minh họa cấu trúc chưa có database code và imports. Khi caller gọi `checkout()` qua proxy, T1 được tạo với isolation được yêu cầu là `READ_COMMITTED`. `FraudService` là **bean khác** nên `checkAndUpdate()` đi qua proxy và manager nhìn thấy annotation riêng của inner. Tuy nhiên propagation `REQUIRED` quyết định **tham gia T1**. Theo chế độ mặc định (lenient) của các manager dựa trên `AbstractPlatformTransactionManager`, isolation `SERIALIZABLE` của inner **không nâng** T1 từ `READ_COMMITTED` lên mức mới.

Chính tài liệu Spring về transaction propagation lưu ý rằng participating transaction mặc định nhận đặc tính của outer, và **bỏ qua** isolation level, timeout và read-only flag riêng của inner, trừ khi cấu hình kiểm tra không tương thích. Do đó phải tách hai kết luận:

1. **Annotation của inner đã được đọc**: transaction interceptor chọn propagation `REQUIRED`.
2. **Isolation của inner không được thi hành thành một thay đổi connection**: vì không bắt đầu physical transaction mới.

Nếu cần enforce một isolation mạnh cho critical operation, chỉ đặt annotation ở inner khi method được gọi bên trong T1 không đủ. Hoặc đảm bảo **entrypoint sở hữu transaction** có isolation yêu cầu, hoặc thiết kế một physical transaction độc lập với `REQUIRES_NEW` sau khi đánh giá consistency và tài nguyên.

## 5. PROPAGATION_REQUIRES_NEW: bắt đầu physical transaction khác, áp dụng isolation riêng

Cấu hình:

~~~java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.SERIALIZABLE
)
public void checkAndUpdateIndependently() {
    // ...
}
~~~

Khi có outer T1 ở mức `READ_COMMITTED`, method này **không join T1**. Spring suspend T1, mở T2 mới; với JDBC manager và driver hỗ trợ, T2 được cấu hình isolation `SERIALIZABLE` trên connection của nó. Sau khi T2 commit/rollback, Spring trả connection của T2 và resume T1. T1 tiếp tục với `READ_COMMITTED` của chính nó.

| Thời điểm | T1 outer | T2 inner | Isolation SQL đang dùng |
| --- | --- | --- | --- |
| Outer bắt đầu | Active | Chưa có | READ_COMMITTED |
| Inner `REQUIRES_NEW` bắt đầu | Suspend, giữ tài nguyên | Active | SERIALIZABLE |
| Inner return/throw | Vẫn suspend | Commit/rollback | SERIALIZABLE cho T2 đến lúc hoàn tất |
| Outer resume | Active | Đã hoàn tất | READ_COMMITTED |
| Outer hoàn tất | Commit/rollback | Đã hoàn tất | Không còn transaction T1 |

**Đặc biệt quan trọng:** `REQUIRES_NEW` còn đổi **atomicity**. Inner commit thành công **không** bị outer rollback sau đó. Nếu inner đọc dữ liệu outer vừa sửa nhưng **chưa commit**, T2 thường **không nhìn thấy** các thay đổi chưa commit đó trong isolation ngăn dirty read; T2 cũng có thể chờ lock T1 đang giữ, dẫn đến lock dependency. Đừng dùng `REQUIRES_NEW` chỉ để “bắt buộc SERIALIZABLE” nếu nghiệp vụ yêu cầu toàn bộ thao tác của outer và inner cùng commit/rollback.

Với connection pool như HikariCP, outer có thể vẫn giữ C1 trong khi T2 cần mượn C2. Nhiều request đồng thời có thể gây pool exhaustion. Việc chọn mức cô lập riêng cần đi cùng dự toán connection pool và row locks.

## 6. Isolation.DEFAULT: DB default khác Spring metadata của outer

`@Transactional` có isolation mặc định là `Isolation.DEFAULT`. Trong cách dùng điển hình:

~~~java
@Transactional
public void writeDefault() {
    // Mức isolation physical transaction lấy từ default của DB/pool/driver,
    // không thể suy ra trực tiếp từ annotation này.
}
~~~

Nếu Spring không yêu cầu một isolation cụ thể, JDBC connection có thể đang ở mặc định của pool/database, ví dụ `READ_COMMITTED` trong cấu hình H2 thông dụng. Tuy vậy:

- `TransactionSynchronizationManager.getCurrentTransactionIsolationLevel()` phản ánh **isolation level được Spring khai báo gắn với transaction context**, có thể là `null` nếu transaction dùng `Isolation.DEFAULT`; nó **không nhất thiết** là JDBC isolation thật.
- `Connection.getTransactionIsolation()`, gọi trên **connection đang gắn với transaction**, là phép quan sát isolation JDBC thực tế tại thời điểm kiểm tra.
- Một connection từ pool phải được quản lý/khôi phục đúng; nếu code bên ngoài transaction tự thay isolation mà không reset, hành vi có thể khác dự đoán.

**Ví dụ dễ nhầm:** Outer khai báo `Isolation.DEFAULT` (metadata Spring không nêu mức cụ thể) nhưng connection thực tế đang là `READ_COMMITTED`. Inner `REQUIRED` khai báo `SERIALIZABLE`, lenient mode join nên vẫn dùng connection thực tế `READ_COMMITTED`. Strict validation có thể so sánh yêu cầu inner với metadata isolation hiện tại mà manager biết, thay vì tự so sánh ý định lập trình với driver theo cách bạn tưởng. Khi cần xác minh mismatch một cách không nhập nhằng, đặt outer level **tường minh** và dùng test connection-level.

### DEFAULT có “đủ an toàn” không?

Không có câu trả lời phổ quát. Mỗi DB có default isolation và concurrency semantics riêng. Isolation thích hợp phụ thuộc anomalies phải phòng tránh, workload, lock contention, retry policy và transaction duration. Đừng hardcode assumption “DEFAULT = SERIALIZABLE” hay “DEFAULT = READ_COMMITTED” khi thiết kế trên nhiều database.

## 7. Kiểm tra chặt với validateExistingTransaction

Spring hỗ trợ cấu hình **`setValidateExistingTransaction(true)`** trên các transaction managers kế thừa `AbstractPlatformTransactionManager`, ví dụ `JdbcTransactionManager` và `DataSourceTransactionManager`.

Khi bật:

- Nếu inner muốn tham gia transaction hiện có nhưng yêu cầu một isolation level **khác** mức mà Spring ghi nhận cho transaction ngoài, manager có thể **từ chối** việc join với `IllegalTransactionStateException`, thay vì âm thầm bỏ qua khai báo của inner.
- Cơ chế này còn giúp phát hiện một inner read-write cố tham gia transaction outer read-only, tùy manager và metadata.
- Nó **không biến `REQUIRED` thành `REQUIRES_NEW`**: mismatch bị báo lỗi, không tạo một transaction độc lập thay thế.
- Nếu inner không yêu cầu isolation cụ thể (`Isolation.DEFAULT`), đây không phải yêu cầu “nâng/cố định isolation”, nên không tự gây mismatch chỉ vì physical DB level có một giá trị cụ thể.
- Không phải mọi transaction manager hỗ trợ custom isolation như nhau; khi manager không hỗ trợ, cần xác định khả năng thật của resource.

Bean cấu hình tiêu biểu:

~~~java
@Bean
JdbcTransactionManager transactionManager(DataSource dataSource) {
    JdbcTransactionManager manager = new JdbcTransactionManager(dataSource);
    manager.setValidateExistingTransaction(true);
    return manager;
}
~~~

Đoạn này cần nằm trong lớp `@Configuration`/Spring Boot application có imports phù hợp; `DataSource` phải là nguồn tài nguyên của DAO. Nó là **policy toàn manager**, không chỉ một method. Bật strict validation có thể làm các luồng trước đó “chạy được nhưng silently ignored” chuyển thành **fail fast**; cần kiểm thử toàn bộ các caller đang tham gia transaction.

### Lưu ý tên API

Tên Java setter là **`setValidateExistingTransaction`** (số ít “Transaction”). Tài liệu có chỗ diễn đạt “validate existing transactions” như tiếng Anh mô tả; khi viết mã, dùng đúng tên method và kiểu manager có API này.

### Vì sao strict validation hữu ích?

Giả sử nghiệp vụ thanh toán đòi mọi SQL liên quan quyết định trạng thái cuối cùng chạy ở isolation đã quy định. Nếu một caller mở transaction yếu hơn rồi gọi method critical `@Transactional(isolation=SERIALIZABLE)` với `REQUIRED`, cấu hình mặc định **không nâng** transaction ngoài. Nếu đó là bug consistency, strict mode làm lỗi xuất hiện **ngay tại lúc tham gia**, thay vì để hệ thống tưởng đã chạy ở isolation mong muốn.

Nhưng strict mode không giải quyết yêu cầu “chỉ inner cần isolation khác mà vẫn join cùng physical transaction”; hai mong muốn đó mâu thuẫn về resource semantics. Cần chọn isolation cho T1 từ đầu hoặc tách T2 chủ động.

## 8. Ví dụ Java 17+ chạy được: nhìn isolation thật trên JDBC Connection

Ví dụ CLI sử dụng **Java 17**, **Spring Boot 3.3.5 (Spring Framework 6.1.x)**, `spring-boot-starter-jdbc`, H2 in-memory, Maven và hai Spring services riêng. Không có HTTP server hay external DB.

Chương trình chạy **ba tình huống**:

1. **Lenient + REQUIRED join:** Outer mở transaction `READ_COMMITTED`, inner yêu cầu `SERIALIZABLE` nhưng join cùng physical transaction; inner đọc JDBC connection và thấy `READ_COMMITTED`.
2. **REQUIRES_NEW:** Outer mở `READ_COMMITTED`, inner mở physical transaction độc lập `SERIALIZABLE`; trở ra outer lại thấy `READ_COMMITTED`.
3. **Strict validation:** Manager bật `validateExistingTransaction=true`, inner `REQUIRED` yêu cầu `SERIALIZABLE` nhưng outer đang `READ_COMMITTED`; manager ném `IllegalTransactionStateException` ngay khi inner chuẩn bị tham gia.

Để quan sát chính xác, chương trình gọi `JdbcTemplate.execute(ConnectionCallback<T>)` lấy **connection của transaction hiện tại** và đọc `Connection.getTransactionIsolation()`. Không suy luận mức isolation chỉ bằng việc đọc annotation hoặc log.

### 8.1. Cấu trúc tệp

~~~text
isolation-join-demo/
├── pom.xml
└── src/main/java/example/isolation/
    ├── IsolationDemoApplication.java
    ├── OuterService.java
    └── InnerService.java
~~~

Lớp tiện ích package-private `IsolationProbe` được viết **trong cùng tệp** `IsolationDemoApplication.java`, vì Java cho phép một tệp có một public top-level class cùng package-private top-level class. Vì vậy project chỉ cần đúng **bốn tệp**.

### 8.2. pom.xml

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
    <artifactId>isolation-join-demo</artifactId>
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

### 8.3. src/main/java/example/isolation/IsolationDemoApplication.java

~~~java
package example.isolation;

import java.sql.Connection;
import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.IllegalTransactionStateException;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class IsolationDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(IsolationDemoApplication.class, args);
    }

    @Bean
    JdbcTransactionManager transactionManager(DataSource dataSource) {
        JdbcTransactionManager manager = new JdbcTransactionManager(dataSource);
        manager.setValidateExistingTransaction(false);
        return manager;
    }

    @Bean
    CommandLineRunner demo(OuterService outer, JdbcTransactionManager manager) {
        return args -> {
            System.out.println("LENIENT_MODE");
            outer.joinScenario();
            outer.independentScenario();

            // Chỉ đổi flag trong ứng dụng CLI đơn luồng để minh họa.
            // KHÔNG khuyến nghị đổi transaction manager config lúc production chạy.
            manager.setValidateExistingTransaction(true);
            System.out.println("STRICT_MODE");
            try {
                outer.joinScenario();
            } catch (IllegalTransactionStateException ex) {
                System.out.println(
                    "STRICT_REJECTED=" + ex.getClass().getSimpleName()
                );
            }
        };
    }
}

// Package-private utility class trong cùng file với public class phía trên.
final class IsolationProbe {
    private IsolationProbe() {
    }

    static String actual(JdbcTemplate jdbc) {
        Integer level = jdbc.execute(
            (ConnectionCallback<Integer>) connection ->
                connection.getTransactionIsolation()
        );
        if (level == null) {
            throw new IllegalStateException("No JDBC isolation level");
        }
        return switch (level) {
            case Connection.TRANSACTION_READ_UNCOMMITTED -> "READ_UNCOMMITTED";
            case Connection.TRANSACTION_READ_COMMITTED -> "READ_COMMITTED";
            case Connection.TRANSACTION_REPEATABLE_READ -> "REPEATABLE_READ";
            case Connection.TRANSACTION_SERIALIZABLE -> "SERIALIZABLE";
            default -> "OTHER(" + level + ")";
        };
    }
}
~~~

Lưu ý import `ConnectionCallback` trong `org.springframework.jdbc.core` là loại callback giúp `JdbcTemplate` cung cấp connection gắn với Spring transaction. Không gọi `dataSource.getConnection()` trực tiếp rồi quên đóng: đó có thể là một connection khác, khiến kết quả đo vô nghĩa đối với transaction hiện hành.

### 8.4. src/main/java/example/isolation/OuterService.java

~~~java
package example.isolation;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterService {
    private final JdbcTemplate jdbc;
    private final InnerService inner;

    public OuterService(JdbcTemplate jdbc, InnerService inner) {
        this.jdbc = jdbc;
        this.inner = inner;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void joinScenario() {
        System.out.println(
            "OUTER_JOIN_BEFORE=" + IsolationProbe.actual(jdbc)
        );
        // Bean khác -> đi qua transaction proxy của InnerService.
        inner.joinSerializable();
        System.out.println(
            "OUTER_JOIN_AFTER=" + IsolationProbe.actual(jdbc)
        );
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void independentScenario() {
        System.out.println(
            "OUTER_NEW_BEFORE=" + IsolationProbe.actual(jdbc)
        );
        inner.newSerializable();
        System.out.println(
            "OUTER_NEW_AFTER=" + IsolationProbe.actual(jdbc)
        );
    }
}
~~~

### 8.5. src/main/java/example/isolation/InnerService.java

~~~java
package example.isolation;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InnerService {
    private final JdbcTemplate jdbc;

    public InnerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.SERIALIZABLE
    )
    public void joinSerializable() {
        System.out.println(
            "INNER_REQUIRED_ACTUAL=" + IsolationProbe.actual(jdbc)
        );
    }

    @Transactional(
        propagation = Propagation.REQUIRES_NEW,
        isolation = Isolation.SERIALIZABLE
    )
    public void newSerializable() {
        System.out.println(
            "INNER_NEW_ACTUAL=" + IsolationProbe.actual(jdbc)
        );
    }
}
~~~

### 8.6. Chạy và đối chiếu đầu ra

Từ thư mục chứa `pom.xml` (JDK 17+ và Maven; dependencies có thể được tải ở lần đầu):

~~~bash
mvn -q spring-boot:run
~~~

Các **dòng do chương trình tự in** theo thứ tự, không tính log khởi động Spring Boot/HikariCP:

~~~text
LENIENT_MODE
OUTER_JOIN_BEFORE=READ_COMMITTED
INNER_REQUIRED_ACTUAL=READ_COMMITTED
OUTER_JOIN_AFTER=READ_COMMITTED
OUTER_NEW_BEFORE=READ_COMMITTED
INNER_NEW_ACTUAL=SERIALIZABLE
OUTER_NEW_AFTER=READ_COMMITTED
STRICT_MODE
OUTER_JOIN_BEFORE=READ_COMMITTED
STRICT_REJECTED=IllegalTransactionStateException
~~~

**Giải thích từng bước:**

1. `LENIENT_MODE`: manager đang để `setValidateExistingTransaction(false)`.
2. `OUTER_JOIN_BEFORE=READ_COMMITTED`: outer proxy bắt đầu T1 mới, Spring yêu cầu isolation READ_COMMITTED trên JDBC connection của T1.
3. `INNER_REQUIRED_ACTUAL=READ_COMMITTED`: dù method inner khai báo SERIALIZABLE, nó join T1 qua `REQUIRED`. Với lenient mode, manager bỏ qua isolation yêu cầu riêng của inner; JDBC connection vẫn là READ_COMMITTED.
4. `OUTER_JOIN_AFTER=READ_COMMITTED`: T1 chưa đổi isolation trong lần join. Transaction ngoài hoàn tất ở cuối method.
5. `OUTER_NEW_BEFORE=READ_COMMITTED`: một T1 mới được tạo cho lần gọi thứ hai.
6. `INNER_NEW_ACTUAL=SERIALIZABLE`: `REQUIRES_NEW` suspend T1, mở physical transaction T2 và yêu cầu SERIALIZABLE trên connection của T2. H2 hỗ trợ mức này.
7. `OUTER_NEW_AFTER=READ_COMMITTED`: T2 đã hoàn tất và T1 resume với isolation ban đầu.
8. `STRICT_MODE`: demo bật `setValidateExistingTransaction(true)` **sau khi các method trước đã return**; không làm việc đó giữa một request production có transaction đồng thời.
9. Outer bắt đầu T1 READ_COMMITTED và in `OUTER_JOIN_BEFORE=READ_COMMITTED`.
10. Inner `REQUIRED` yêu cầu SERIALIZABLE; strict validation phát hiện mismatch và **từ chối tham gia trước khi vào body của `joinSerializable()`**. Caller ngoài outer proxy bắt `IllegalTransactionStateException` sau khi outer interceptor xử lý rollback. Vì vậy **không có dòng `INNER_REQUIRED_ACTUAL` thứ hai** trong strict case.

Demo cho thấy không chỉ annotation metadata mà **JDBC isolation hiện tại** được trả từ connection đúng transaction. Nó không phải bài test concurrency anomalies như phantom read; cần test multi-connection đồng thời riêng nếu muốn chứng minh hiện tượng read/write cụ thể.

## 9. Ma trận dự đoán khi caller có hoặc không có transaction ngoài

Giả sử Spring JDBC manager có hỗ trợ isolation level được yêu cầu, lời gọi **đi qua proxy**, không có transaction bao ngoài ngoài những gì mô tả:

| Transaction hiện tại | Annotation inner | Physical transaction | Isolation inner dự kiến khi lenient | Khi strict validation |
| --- | --- | --- | --- | --- |
| Không có | `REQUIRED, SERIALIZABLE` | Inner tạo T mới | SERIALIZABLE | Cùng kết quả nếu driver hỗ trợ |
| Có T1 READ_COMMITTED | `REQUIRED, SERIALIZABLE` | Join T1 | READ_COMMITTED (theo T1) | Từ chối mismatch |
| Có T1 SERIALIZABLE | `REQUIRED, SERIALIZABLE` | Join T1 | SERIALIZABLE | Cho join nếu metadata tương thích |
| Có T1 READ_COMMITTED | `REQUIRED, DEFAULT` | Join T1 | READ_COMMITTED | Không đòi isolation mới |
| Có T1 READ_COMMITTED | `REQUIRES_NEW, SERIALIZABLE` | Suspend T1, tạo T2 | SERIALIZABLE trên T2 | Tạo T2, không kiểm tra như join T1 |
| Không có | `REQUIRES_NEW, SERIALIZABLE` | Tạo T2 mới | SERIALIZABLE | Cùng kết quả nếu hỗ trợ |
| Có T1 READ_COMMITTED | `NESTED, SERIALIZABLE` | Có thể tạo JDBC savepoint trong T1 | Không tự nâng T1 thành SERIALIZABLE | Không xem là cách tạo isolation mới |
| Có T1 READ_COMMITTED | `SUPPORTS, SERIALIZABLE` | Tham gia nếu có | T1 vẫn READ_COMMITTED | Không sử dụng SUPPORTS để yêu cầu isolation mới |

**Lưu ý `NESTED`:** hành vi còn phụ thuộc support của manager/driver; savepoint không tạo physical transaction mới. `SUPPORTS` với isolation riêng không phải mô hình được thiết kế để ép isolation của một physical transaction mới. Theo Javadoc của `@Transactional`, isolation và timeout chủ yếu chỉ áp dụng khi một transaction mới được mở với `REQUIRED` hoặc `REQUIRES_NEW`.

## 10. Isolation của annotation, isolation của Spring context, isolation của connection

Có ba lớp thông tin khác nhau:

1. **Definition yêu cầu:** `@Transactional(isolation = Isolation.SERIALIZABLE)` — điều người viết muốn tại transaction boundary.
2. **Spring transaction context:** `TransactionSynchronizationManager.getCurrentTransactionIsolationLevel()` — thông tin mức cô lập **được khai báo** mà Spring gắn với context của transaction hiện hành; có thể `null` với `DEFAULT`.
3. **JDBC connection thực tế:** `Connection.getTransactionIsolation()` từ connection transaction-aware mà `JdbcTemplate` sử dụng — mức isolation driver báo đang có.

Trong ví dụ lenient, definition của inner yêu cầu SERIALIZABLE nhưng physical connection trong inner trả READ_COMMITTED. Đọc code annotation mà không quan sát context/connection có thể làm kết luận sai.

~~~java
// Trích đoạn trong method imperative đã được Spring transaction advice áp dụng:
Integer springDeclared =
    TransactionSynchronizationManager.getCurrentTransactionIsolationLevel();

// Nhận đúng connection đang gắn với transaction qua JdbcTemplate.
Integer jdbcActual = jdbc.execute(
    (ConnectionCallback<Integer>) c -> c.getTransactionIsolation()
);
~~~

Các import cần thiết trong trích đoạn: `org.springframework.transaction.support.TransactionSynchronizationManager`, `org.springframework.jdbc.core.ConnectionCallback`, `org.springframework.jdbc.core.JdbcTemplate`. Đây là **đoạn minh họa**, không phải một lớp chạy độc lập. Đừng dùng `new JdbcTemplate(new HikariDataSource(...))` để thử một source hoàn toàn khác; phải dùng đúng bean `DataSource` mà manager quản lý.

**Một bẫy:** Nếu dùng `DataSource.getConnection()` trực tiếp, bạn có thể borrow connection khác pool (không gắn với transaction) và thấy default isolation của nó. Khi đó log “inner is READ_COMMITTED” không chứng minh inner SQL trên `JdbcTemplate` cũng chạy mức ấy. Để đo đúng, thao tác qua Spring transaction-aware API; `JdbcTemplate` dùng `DataSourceUtils` dưới hood.

## 11. Điều gì sẽ xảy ra nếu isolation level không được database hỗ trợ?

Mức được khai báo không phải magic. Có thể gặp:

- Driver/database **không hỗ trợ** một JDBC isolation level: `Connection.setTransactionIsolation(...)` có thể từ chối, hoặc DB sẽ có behavior riêng theo driver.
- Transaction manager không hỗ trợ custom isolation: có thể ném `InvalidIsolationLevelException` hoặc ngoại lệ tương ứng.
- Một database dùng snapshot isolation/MVCC có semantics khác bảng ANSI SQL giản lược; cùng tên `REPEATABLE_READ` hoặc `SERIALIZABLE` không bảo đảm chiến lược locking giống nhau.
- Có serialization failure/lock timeout khi DB thực thi ở isolation mạnh; ứng dụng phải định nghĩa retry chính xác, **không** coi isolation mạnh là không bao giờ thất bại.
- Transaction timeout, read-only, isolation đều là thuộc tính transaction nhưng có hỗ trợ và hiệu lực riêng. Việc một thuộc tính được manager chấp nhận không chứng minh những thuộc tính khác đều thi hành y hệt.

Khi thiết kế đa cơ sở dữ liệu, cần test trên DB thực (PostgreSQL, MySQL/InnoDB, SQL Server, Oracle...) thay vì chỉ dựa vào H2. Demo H2 ở trên chỉ chứng minh **Spring chọn mức isolation của connection** trong ba kịch bản, không phải chứng minh toàn bộ anomaly matrix sản xuất.

## 12. Cẩn trọng với REQUIRES_NEW và độ nhất quán nghiệp vụ

Giả sử outer T1 đọc thông tin khách hàng và ghi `account.balance`, rồi inner `REQUIRES_NEW` SERIALIZABLE kiểm tra hạn mức. T2 là physical transaction khác, nên **không kế thừa uncommitted writes của T1** và có thể nhìn snapshot/state của DB khác. Nếu T2 cần kiểm tra giá trị mà outer chưa commit, kết quả không nhất thiết như người viết tưởng. T2 cũng có thể bị block bởi khóa do T1 giữ trong khi T1 đang chờ T2 — một vòng phụ thuộc dù pool đủ connection.

Đây là lý do **không tự động dùng REQUIRES_NEW chỉ để lấy mức isolation khác**. Hỏi theo thứ tự:

1. Invariant nghiệp vụ có cần tất cả bước cùng atomic không?
2. Mức isolation mạnh có thể được đặt ở **outer transaction owner** ngay từ đầu không?
3. Việc tách inner thành transaction độc lập có làm xuất hiện partial commits ngoài ý muốn không?
4. Có uncommitted data của outer mà inner cần thấy không?
5. Có cross-transaction lock dependency hoặc connection pool contention không?
6. Có thể thiết kế một command/entrypoint mới mở với `SERIALIZABLE` thay vì gọi trong T1 hiện tại không?

Nếu muốn toàn workflow cùng atomic và có yêu cầu isolation mạnh, chọn **một physical transaction sở hữu tất cả thao tác** với isolation phù hợp từ đầu, thay vì ghép hai transaction độc lập mà không muốn hậu quả về consistency.

## 13. Vai trò của proxy và lời gọi nội bộ

Trong `@EnableTransactionManagement` proxy mode mặc định, `@Transactional` chỉ được advice khi lời gọi đi **qua proxy** của Spring. Lời gọi `this.inner()` trong cùng target object không tạo một transaction interceptor mới cho inner.

~~~java
@Service
class OneBean {
    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void outer() {
        this.inner(); // Không đi qua proxy inner.
    }

    @Transactional(
        propagation = Propagation.REQUIRES_NEW,
        isolation = Isolation.SERIALIZABLE
    )
    public void inner() {
        // Annotation của inner không tự mở T2 khi gọi bằng this.inner().
    }
}
~~~

Đây là **mã minh họa**. Nếu caller đi qua proxy của `outer()`, inner vẫn có thể chạy trong T1 READ_COMMITTED của outer, nhưng không phải vì `REQUIRES_NEW` của inner đã chạy. **Đừng xem “isolation không đổi” là bằng chứng duy nhất của REQUIRED join**; nó cũng có thể xảy ra vì self-invocation bỏ qua transaction advice.

Để có transaction boundary đúng, tách inner sang bean khác gọi qua Spring proxy, hoặc dùng `TransactionTemplate`/programmatic transaction khi phù hợp. Kiểm chứng bằng integration test với dữ liệu commit/rollback và connection isolation, không chỉ kiểm tra annotation trên source code.

## 14. TransactionTemplate cũng tuân theo quy tắc isolation của physical transaction

Nếu dùng Spring programmatic API, quy tắc tương tự. Trích đoạn minh họa:

~~~java
TransactionTemplate template = new TransactionTemplate(manager);
template.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRED
);
template.setIsolationLevel(
    TransactionDefinition.ISOLATION_SERIALIZABLE
);
template.executeWithoutResult(status -> {
    // Khi manager tham gia T1 hiện hữu,
    // SERIALIZABLE ở definition này không tự nâng T1.
});
~~~

Nếu đổi propagation thành `PROPAGATION_REQUIRES_NEW`, callback có thể mở physical transaction mới và áp dụng isolation yêu cầu, trong giới hạn manager/DB. Cách viết chương trình **không** thay đổi quy luật join versus new. Nó chỉ loại bỏ việc phải có lời gọi qua proxy cho callback.

`TransactionTemplate` phù hợp khi cần boundary rõ trong cùng component, nhưng phải cân nhắc transaction manager, exception, retry và tài nguyên pool. Nó không là công cụ “ép mức isolation cho transaction đang chạy”.

## 15. Những lỗi cấu hình thường gặp

| Ngộ nhận hoặc lỗi | Thực tế |
| --- | --- |
| “Inner `REQUIRED` khai báo SERIALIZABLE thì toàn T1 tự nâng lên SERIALIZABLE.” | Default lenient manager thường bỏ qua isolation inner khi join T1. |
| “Có annotation ở method là physical transaction mới.” | `REQUIRED` join physical transaction hiện hữu. |
| “`Isolation.DEFAULT` luôn là READ_COMMITTED.” | Lấy theo DB/connection/manager default, khác theo môi trường. |
| “`REQUIRES_NEW` chỉ đổi isolation mà vẫn cùng commit với outer.” | Nó tạo physical transaction độc lập và đổi atomicity. |
| “Bật `validateExistingTransaction=true` sẽ tự tạo transaction mới khi mismatch.” | Không. Nó thường từ chối join bằng exception. |
| “Strict validation kiểm tra mức isolation thực trên mọi JDBC connection trong mọi manager.” | Nó dựa vào transaction metadata/manager rules; đừng coi là JDBC diagnostic toàn diện. |
| “Inner `NESTED` có thể đặt SERIALIZABLE độc lập với outer.” | JDBC savepoint nằm trong cùng physical transaction, không phải T2 riêng. |
| “Thay isolation bằng cách gọi `Connection.setTransactionIsolation` giữa transaction là an toàn.” | Có thể phá consistency/driver contract và trạng thái pool; không thay đổi tùy tiện giữa transaction. |
| “H2 hỗ trợ SERIALIZABLE nghĩa là PostgreSQL/MySQL có cùng anomaly behavior.” | Driver/DB có semantics riêng; phải test trên hệ đích. |
| “`TransactionSynchronizationManager` báo null thì JDBC connection không có isolation.” | `null` thường biểu thị không có isolation level explicit trong Spring metadata, không phải connection không có JDBC isolation. |
| “Self-call vẫn được @Transactional advice của inner xử lý.” | Proxy mode thường bỏ qua advice ở lời gọi `this.inner()`. |
| “Tăng isolation là giải pháp chung cho mọi race condition.” | Cần transaction scope đúng, constraints, locking/retry và test concurrent execution. |

## 16. Debug: một method yêu cầu SERIALIZABLE nhưng SQL vẫn chạy READ_COMMITTED

Hãy kiểm tra theo thứ tự:

1. **Caller thực tế là ai?** Có outer `@Transactional` hoặc test transaction đang mở không? Nếu có, isolation của physical transaction đó là gì?
2. **Propagation tại inner là gì?** `REQUIRED` join, `REQUIRES_NEW` tạo transaction độc lập, `NESTED` dùng savepoint khi hỗ trợ.
3. **Lời gọi có qua proxy không?** Bean khác được Spring inject hay self-invocation qua `this`? Mã tạo bằng `new` không được transaction advice xử lý.
4. **Manager nào được chọn?** Có nhiều `PlatformTransactionManager`/`DataSource` không? `@Transactional(transactionManager="...")` cần chỉ đúng manager của SQL đang chạy.
5. **Metadata nào có hiệu lực?** Method annotation có ưu tiên hơn class annotation; đừng giả định các thuộc tính class được merge từng phần vào method.
6. **Có strict validation chưa?** Nếu bật `setValidateExistingTransaction(true)` và có mismatch, phải thấy lỗi ở bước tham gia; nếu không, kiểm tra lại manager/proxy.
7. **Đo isolation ở connection thật.** Dùng `JdbcTemplate.execute(ConnectionCallback)` hoặc API tương đương có transaction awareness; không borrow một connection khác để kiểm tra.
8. **Kết quả có phụ thuộc driver không?** DB có hỗ trợ isolation yêu cầu, có nâng cấp/downgrade, có MVCC, có lock/serialization failure không?
9. **Test có transaction bao ngoài không?** Một test method `@Transactional` do Spring TestContext tạo có thể biến service method `REQUIRED` thành participating scope ngoài dự đoán.
10. **Có inner resource khác không?** Một repository dùng datasource/manager khác có thể thực sự chạy trong physical transaction khác, không được suy ra từ cùng tên database.

Log thử nghiệm có thể bật:

~~~properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
~~~

Dùng logging để xác nhận begin/join/suspend và manager, nhưng không xem log “participating in existing transaction” là phép đo thay cho `getTransactionIsolation()` của đúng JDBC connection. Trong production, kiểm soát mức log để tránh overhead và thông tin nhạy cảm.

## 17. Bài tập tình huống và đáp án

### Bài 1. Inner REQUIRED nâng isolation?

Outer mới mở T1 `READ_COMMITTED`. Inner bean khác có `@Transactional(propagation=REQUIRED, isolation=SERIALIZABLE)`. Manager lenient mặc định. Inner đọc JDBC connection. Isolation dự kiến?

**Đáp án:** `READ_COMMITTED` theo T1, vì inner join cùng physical transaction. Inner metadata `SERIALIZABLE` không áp dụng lại lên T1.

### Bài 2. Không có outer transaction thì sao?

Cùng method inner `REQUIRED`/`SERIALIZABLE` nhưng caller không có transaction. Isolation dự kiến?

**Đáp án:** Inner tạo physical transaction mới; nếu manager/driver hỗ trợ, nó thiết lập `SERIALIZABLE` cho transaction đó.

### Bài 3. Bật validateExistingTransaction?

Giữ bài 1, bật strict validation trên `JdbcTransactionManager`. Điều gì khác?

**Đáp án:** Manager phát hiện inner yêu cầu SERIALIZABLE trong T1 được Spring ghi nhận là READ_COMMITTED và từ chối tham gia bằng `IllegalTransactionStateException`; không tự tạo T2.

### Bài 4. Đổi inner sang REQUIRES_NEW?

Outer T1 `READ_COMMITTED` gọi inner `REQUIRES_NEW`/`SERIALIZABLE`. Isolation khi inner chạy, sau khi trở lại outer?

**Đáp án:** Khi inner T2 chạy là `SERIALIZABLE` nếu được hỗ trợ; khi T2 hoàn tất và T1 resume, outer tiếp tục `READ_COMMITTED`. Inner commit/rollback độc lập.

### Bài 5. Inner cùng bean gọi bằng this.inner()?

Outer `@Transactional(READ_COMMITTED)` gọi `this.inner()`; inner annotated `REQUIRES_NEW`/`SERIALIZABLE`. Có T2 không?

**Đáp án:** Trong proxy mode mặc định, **không** tạo T2 bởi annotation inner. Lời gọi bỏ qua advice inner; phần thân có thể chạy trong T1 của outer.

### Bài 6. DEFAULT và metadata null?

Outer `@Transactional` không ghi isolation cụ thể, dùng JDBC connection hiện có `READ_COMMITTED`. `TransactionSynchronizationManager.getCurrentTransactionIsolationLevel()` có thể trả gì?

**Đáp án:** Có thể `null` vì Spring metadata là `Isolation.DEFAULT`, trong khi `Connection.getTransactionIsolation()` trên connection của T1 trả `READ_COMMITTED`. Đừng nhầm declared isolation với effective isolation.

### Bài 7. Isolation mạnh có ngăn mọi lost update?

Hai transaction đọc cùng giá trị, tính giá trị mới rồi cập nhật. Gắn `SERIALIZABLE` vào một helper `REQUIRED` nằm trong outer READ_COMMITTED có đủ không?

**Đáp án:** Không; helper join outer nên không tự nâng mức cô lập. Ngay cả khi physical transaction chạy SERIALIZABLE, hệ thống còn cần xử lý serialization failure/retry và dùng constraints/SQL phù hợp. Kiểm thử concurrency trên DB thật.

### Bài 8. Bài toán consistency khi dùng REQUIRES_NEW?

Outer T1 sửa một hàng nhưng chưa commit, inner T2 SERIALIZABLE cần đọc chính hàng ấy để ra quyết định. Có chắc inner thấy thay đổi chưa commit của outer không?

**Đáp án:** Không. T2 là transaction độc lập; ở các isolation ngăn dirty read, nó không thấy uncommitted write ấy và có thể bị block bởi lock của T1. Chọn propagation theo invariant, không chỉ mức cô lập mong muốn.

## 18. Checklist trước khi triển khai

- [ ] Biết rõ **physical transaction owner** và propagation của mỗi logical scope.
- [ ] Nếu method yêu cầu isolation riêng, xác định nó **mở transaction mới** hay **join**.
- [ ] Không giả định annotation inner tự nâng mức isolation của outer.
- [ ] Kiểm chứng `Isolation.DEFAULT` bằng database/driver thực tế, không hardcode.
- [ ] Chọn `validateExistingTransaction(true)` nếu muốn phát hiện mismatch, và test ảnh hưởng trên các luồng hiện hữu.
- [ ] Đảm bảo lời gọi đến inner qua đúng Spring proxy, không bị self-invocation.
- [ ] Với `REQUIRES_NEW`, đánh giá độc lập commit/rollback, JDBC connection pool và row lock.
- [ ] Đo `Connection.getTransactionIsolation()` trên đúng connection transaction-aware.
- [ ] Test trên DB production-like với concurrent workloads và chiến lược retry.
- [ ] Không đọc kết quả từ một Spring TestContext outer transaction ngoài ý muốn.

## 19. Kết luận

**Isolation là thuộc tính của physical transaction.** `@Transactional(isolation=SERIALIZABLE)` trên một method `REQUIRED` chỉ là **yêu cầu metadata**. Nếu method đang **tham gia** physical transaction `READ_COMMITTED` của outer, Spring mặc định không đổi connection/transaction đó sang SERIALIZABLE. Có thể bật `setValidateExistingTransaction(true)` để **từ chối mismatch** thay vì im lặng bỏ qua.

Muốn isolation riêng có hiệu lực, method phải **sở hữu một physical transaction mới**: `REQUIRED` khi chưa có transaction hiện tại, hoặc `REQUIRES_NEW` khi cần tách ra khỏi outer. Nhưng transaction độc lập cũng đổi atomicity, visibility, resource locks và connection pool demand. Do đó chọn isolation và propagation cùng lúc theo yêu cầu consistency, kiểm chứng trên JDBC connection thật và trong môi trường database đích.

## Tài liệu tham khảo chính thức

- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): physical/logical transactions, `REQUIRED` tham gia và bỏ qua isolation nội bộ, strict `validateExistingTransaction`, `REQUIRES_NEW` có physical transaction độc lập.
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): default `Isolation.DEFAULT` và propagation.
- [Spring Framework 6.1 — Transactional Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html): isolation chủ yếu cho newly started `REQUIRED`/`REQUIRES_NEW` transactions.
- [Spring Framework — AbstractPlatformTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html): `setValidateExistingTransaction` và kiểm tra participating scope.
- [Spring Framework — JDBC Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `DataSourceUtils`, transaction-aware JDBC connection usage.
- [Java SE 17 — java.sql.Connection](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html): `getTransactionIsolation()`, JDBC transaction isolation constants.
