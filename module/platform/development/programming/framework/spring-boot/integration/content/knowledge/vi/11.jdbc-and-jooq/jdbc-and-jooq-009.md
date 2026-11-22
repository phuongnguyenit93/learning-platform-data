# Tích hợp truy vấn với transaction manager phù hợp trong Spring Boot: JDBC và jOOQ

Khi viết luồng tích hợp bằng Spring Boot, một service thường cần kết hợp **JDBC** để thực hiện thao tác đơn giản và **jOOQ** để xây dựng SQL có kiểm tra kiểu ở thời điểm biên dịch. Chẳng hạn consumer nhận sự kiện `PaymentCaptured`, ghi một `eventId` vào bảng chống trùng bằng `JdbcTemplate`, cập nhật hạn mức bằng jOOQ, rồi ghi bút toán vào SQL. Nếu bước cuối thất bại, cả ba thay đổi phải **rollback trong cùng giao dịch**. Gọi `@Transactional` chưa đủ nếu các truy vấn sử dụng kết nối khác nhau hoặc được điều phối bởi transaction manager không đúng.

Bài thuộc chương **JDBC và jOOQ** của module **SPRING_BOOT_INTEGRATION**. Module nghiên cứu tích hợp Spring Boot với HTTP client, cơ sở dữ liệu, cache, broker thông điệp và các adapter Spring Integration, với trọng tâm cấu hình, hợp đồng dữ liệu, giao dịch, lỗi, chống xử lý trùng, kiểm thử và quan sát hệ thống. Ở đây ta tập trung vào **chọn `PlatformTransactionManager` đúng với tài nguyên**, cách `JdbcTemplate` và `DSLContext` cùng tham gia transaction, và ranh giới khi luồng tích hợp đi qua database, thread hoặc broker khác.

> Các ví dụ minh họa Spring Boot 3.x, Spring Framework 6.x, JDBC, jOOQ và PostgreSQL. Cú pháp SQL `ON CONFLICT` là của PostgreSQL. Khi dùng phiên bản Boot khác, nhiều datasource hoặc thay thế transaction manager mặc định, cần kiểm tra bean thật trong `ApplicationContext` và thử rollback trên database thật. Các class jOOQ như `WALLET` được giả định đã sinh từ schema bằng jOOQ code generation.

## 1. Vì sao truy vấn thành công riêng lẻ vẫn có thể tạo dữ liệu sai?

Xét luồng ghi một khoản trừ tiền sau khi nhận sự kiện thanh toán:

~~~mermaid
sequenceDiagram
    participant L as @RabbitListener
    participant S as LedgerService
    participant J as JdbcTemplate
    participant Q as jOOQ DSLContext
    participant DB as PostgreSQL

    L->>S: apply(PaymentCaptured)
    Note over S,DB: Một transaction Spring
    S->>J: INSERT processed_events(eventId)
    J->>DB: INSERT
    S->>Q: UPDATE wallet SET balance...
    Q->>DB: UPDATE
    S->>J: INSERT wallet_ledger
    J->>DB: INSERT
    alt Tất cả bước thành công
        S->>DB: COMMIT
        S-->>L: Thành công, listener có thể ACK
    else Một bước ném lỗi cần rollback
        S->>DB: ROLLBACK
        S--xL: Exception để listener xử lý
    end
~~~

Nếu `JdbcTemplate` nhận connection A thuộc transaction nhưng `DSLContext` tự mở connection B ở chế độ auto-commit, lệnh cập nhật bằng jOOQ có thể **được commit ngay**, trong khi lệnh JDBC còn lại rollback. Khi consumer retry, trạng thái tài khoản có thể bị thay đổi hai lần.

Để transaction thực sự bao trùm truy vấn JDBC và jOOQ, phải đồng thời thỏa các điều kiện:

1. Các thao tác cùng thuộc một **database resource** mong muốn, thường là cùng `DataSource` trỏ đến database đích.
2. Transaction manager được chọn quản lý **chính DataSource đó**.
3. Cả `JdbcTemplate` lẫn `DSLContext` lấy connection theo **cơ chế nhận biết Spring transaction**.
4. Mọi thao tác cần atomic được thực hiện trong **ranh giới transaction đang hoạt động**, không bị chuyển sang thread/connection khác ngoài ý muốn.
5. Exception/rollback rule phản ánh đúng trường hợp phải hủy giao dịch.

**Một @Transactional trên method chỉ là điểm khai báo.** Muốn biết hiệu lực thực tế phải xem manager, connection provider, việc gọi qua proxy và kết quả kiểm thử commit/rollback.

## 2. Phân biệt transaction manager, DataSource và connection

Ba thành phần liên quan nhưng không đồng nghĩa:

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `DataSource` | Cấp connection tới cơ sở dữ liệu; thường chứa pool | `HikariDataSource` |
| `PlatformTransactionManager` | Bắt đầu, commit, rollback, suspend hoặc tạo savepoint theo transaction definition | `JdbcTransactionManager`, `JpaTransactionManager`, `JtaTransactionManager` |
| `Connection` | Phiên JDBC vật lý/logic chạy SQL với auto-commit, isolation và state | `java.sql.Connection` |

Trong giao dịch JDBC khai báo bằng Spring, transaction manager thường lấy connection từ `DataSource`, cấu hình auto-commit/isolation/read-only và **gắn `ConnectionHolder` với thread hiện tại** thông qua `TransactionSynchronizationManager`. Các truy vấn Spring JDBC dùng `DataSourceUtils` để lấy connection đã được gắn, vì vậy có thể cùng nhìn thấy thao tác chưa commit và cùng rollback.

~~~mermaid
flowchart TD
    TX["@Transactional qua Spring proxy"] --> TM["JdbcTransactionManager"]
    TM --> DS[("DataSource / Hikari pool")]
    TM --> HOLDER["ConnectionHolder trên thread"]
    JDBC["JdbcTemplate / NamedParameterJdbcTemplate"] --> DSU["DataSourceUtils"]
    JOOQ["jOOQ DSLContext"] --> TAP["TransactionAwareDataSourceProxy hoặc provider tích hợp Spring"]
    DSU --> HOLDER
    TAP --> HOLDER
    HOLDER --> DB[("Cùng JDBC Connection")]
    DB --> SQL["INSERT / UPDATE / SELECT trong một transaction"]
~~~

Sơ đồ mô tả mô hình JDBC **imperative**. `ThreadLocal` transaction context không tự truyền sang thread của `@Async`, `CompletableFuture`, `parallelStream` hoặc Reactor scheduler khác. Với R2DBC/reactive transaction, cơ chế tài nguyên và context khác; không dùng sơ đồ trên như bằng chứng rằng `R2dbcTransactionManager` quản lý được JDBC.

### Những manager thường gặp

| Transaction manager | Tài nguyên chính | Dùng khi nào? | Lưu ý |
| --- | --- | --- | --- |
| `JdbcTransactionManager` | JDBC `DataSource` | `JdbcTemplate`, `NamedParameterJdbcTemplate`, jOOQ dùng JDBC cùng nguồn | Là lựa chọn thích hợp cho local JDBC transaction, có khả năng dịch SQL exception trong commit/rollback |
| `DataSourceTransactionManager` | JDBC `DataSource` | Cùng mô hình JDBC, nền tảng cho `JdbcTransactionManager` | Không tự phối hợp đa database |
| `JpaTransactionManager` | JPA `EntityManagerFactory`, có thể hỗ trợ JDBC trên cùng DataSource khi cấu hình phù hợp | Luồng có JPA và JDBC trong một DB | Không thể suy ra hỗ trợ mọi jOOQ/JDBC query nếu dùng connection/provider khác |
| `JtaTransactionManager` | Transaction coordinator/XA | Cần điều phối nhiều resource XA được hỗ trợ, có hạ tầng phù hợp | Tăng chi phí/độ phức tạp; object storage, HTTP client và nhiều broker không đương nhiên là XA resource |
| `R2dbcTransactionManager` | R2DBC `ConnectionFactory` | Truy vấn database reactive qua R2DBC | Không điều phối JDBC `DataSource` hoặc `JdbcTemplate` |
| Transaction provider riêng của jOOQ | jOOQ `Configuration`/`ConnectionProvider` | Khi sử dụng `DSLContext.transaction(...)` | Phải tích hợp đúng với Spring manager nếu muốn chia sẻ boundary |

Với **một database JDBC** và không có ORM yêu cầu manager khác, `JdbcTransactionManager` thường là lựa chọn trực tiếp. Không chọn manager dựa trên chữ “transaction” trong tên bean; phải đối chiếu với **DataSource được truy vấn thực tế**.

## 3. Auto-configuration của Spring Boot: điểm bắt đầu an toàn

### Dependency

Một project Maven dùng PostgreSQL và Spring Boot thường có:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jooq</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Spring Boot dependency management thường quản lý phiên bản Spring JDBC, jOOQ và driver tương thích với phiên bản Boot. **jOOQ code generation** là một bước build riêng: cần cấu hình plugin/nguồn schema khi muốn dùng các table class được sinh; chỉ thêm starter không tự sinh `WALLET` từ database trong mọi project.

`application.yml` cho một DataSource:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/payments
    username: ${DB_USER}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 12
  jooq:
    sql-dialect: POSTGRES
~~~

Không đưa mật khẩu thật vào file commit. Pool 12 connection chỉ là một ví dụ cần điều chỉnh theo số instance, mức đồng thời, thời gian giữ transaction và giới hạn connection của PostgreSQL.

Với một `DataSource` và cấu hình Boot JDBC thông thường, Boot có thể tạo `JdbcTemplate`, `NamedParameterJdbcTemplate`, transaction manager JDBC và `DSLContext` của jOOQ. Tùy version/starter hiện diện, **transaction manager cuối cùng có thể khác**: nếu ứng dụng đã đăng ký manager riêng, có JPA, JTA hoặc nhiều `DataSource`, các điều kiện auto-configuration thay đổi. Cần kiểm tra bean thật thay vì ngầm giả định Boot luôn chọn cùng một manager.

Trong cấu hình jOOQ được Boot hỗ trợ, `DSLContext` có thể sử dụng `TransactionAwareDataSourceProxy`/`ConnectionProvider` và transaction provider tích hợp Spring. Điều đó cho phép các query jOOQ join với transaction JDBC hiện hành. Khi tự tạo `DSLContext` không qua Boot, trách nhiệm cấu hình chuyển về ứng dụng.

### Xem manager được thực sự inject

Trong môi trường chẩn đoán, có thể liệt kê bean transaction manager một lần khi startup:

~~~java
import java.util.Map;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class TransactionDiagnostics {

    @Bean
    ApplicationRunner logTransactionManagers(
            Map<String, PlatformTransactionManager> managers) {
        return args -> managers.forEach(
                (name, manager) ->
                        System.out.println(
                                name + ": " + manager.getClass().getName()));
    }
}
~~~

Đoạn này là **diagnostic tạm thời**; trong sản phẩm thật dùng logger và không ghi thông tin kết nối/credentials. Với nhiều manager, thêm cả ánh xạ manager → DataSource qua cấu hình bean, metrics hoặc test để bảo đảm một service không vô tình dùng nhầm manager khác.

Spring `@Transactional` có thể chọn manager theo bean mặc định/`@Primary` hoặc qualifier đã cấu hình. Khi nhiều manager, hãy chỉ định `transactionManager = "..."` rõ ràng ở ranh giới quan trọng.

## 4. Thiết kế một giao dịch dùng cả JdbcTemplate và jOOQ

Ví dụ consumer nhận thông điệp `DebitAuthorized` và cần ba bước atomic:

- Ghi nhận `eventId` để chống việc broker giao lại.
- Trừ số dư tài khoản nếu đủ tiền.
- Ghi bút toán sổ cái.

Schema PostgreSQL minh họa:

~~~sql
CREATE TABLE wallet (
    account_id     BIGINT PRIMARY KEY,
    balance_cents  BIGINT NOT NULL CHECK (balance_cents >= 0)
);

CREATE TABLE processed_events (
    consumer_name  VARCHAR(100) NOT NULL,
    event_id       VARCHAR(120) NOT NULL,
    processed_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE wallet_ledger (
    ledger_id      BIGSERIAL PRIMARY KEY,
    event_id       VARCHAR(120) NOT NULL UNIQUE,
    account_id     BIGINT NOT NULL REFERENCES wallet(account_id),
    amount_cents   BIGINT NOT NULL CHECK (amount_cents > 0),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Giả sử jOOQ code generation đã tạo `com.example.jooq.tables.Wallet.WALLET`. DTO:

~~~java
public record DebitAuthorized(
        String eventId,
        long accountId,
        long amountCents
) {
}
~~~

Service Spring quản lý transaction:

~~~java
import static com.example.jooq.tables.Wallet.WALLET;

import org.jooq.DSLContext;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WalletDebitService {

    private static final String CONSUMER = "wallet-debit-v1";

    private final JdbcTemplate jdbc;
    private final DSLContext dsl;

    public WalletDebitService(JdbcTemplate jdbc, DSLContext dsl) {
        this.jdbc = jdbc;
        this.dsl = dsl;
    }

    @Transactional
    public void apply(DebitAuthorized event) {
        if (event.eventId() == null || event.eventId().isBlank()
                || event.accountId() <= 0 || event.amountCents() <= 0) {
            throw new IllegalArgumentException("Sự kiện không hợp lệ");
        }

        // PostgreSQL: INSERT đầu tiên thắng; delivery trùng trả 0 row.
        int inserted = jdbc.update("""
            INSERT INTO processed_events (consumer_name, event_id)
            VALUES (?, ?)
            ON CONFLICT (consumer_name, event_id) DO NOTHING
            """, CONSUMER, event.eventId());

        if (inserted == 0) {
            return; // Đã xử lý cùng eventId trong consumer này.
        }

        // jOOQ và JdbcTemplate phải dùng cùng transaction-aware DataSource.
        int updated = dsl.update(WALLET)
                .set(WALLET.BALANCE_CENTS,
                        WALLET.BALANCE_CENTS.minus(event.amountCents()))
                .where(WALLET.ACCOUNT_ID.eq(event.accountId()))
                .and(WALLET.BALANCE_CENTS.ge(event.amountCents()))
                .execute();

        if (updated != 1) {
            throw new InsufficientBalanceException(
                    "Tài khoản không tồn tại hoặc không đủ số dư");
        }

        jdbc.update("""
            INSERT INTO wallet_ledger (event_id, account_id, amount_cents)
            VALUES (?, ?, ?)
            """, event.eventId(), event.accountId(), event.amountCents());
    }
}
~~~

`InsufficientBalanceException` là một **RuntimeException nghiệp vụ do ứng dụng định nghĩa**. Với rollback mặc định của Spring, nếu `updated != 1` hoặc INSERT ledger ném unchecked exception, cả INSERT inbox lẫn UPDATE wallet đều rollback. Nếu handler ném một *checked exception*, quy tắc rollback cần được cấu hình riêng; xem mục 7.

Phép UPDATE có điều kiện `balance_cents >= amount` thực hiện **kiểm tra và cập nhật nguyên tử** trong SQL; nó an toàn hơn đọc số dư rồi trừ ở Java mà không giữ khóa. Unique key trên `processed_events` giải quyết race giữa hai consumer cùng nhận một `eventId`: khi cùng cố INSERT, database điều phối ràng buộc khóa thay vì phụ thuộc vào kiểm tra trước bằng SELECT.

Có vài ranh giới cần nói rõ:

- Nếu `JdbcTemplate` và `DSLContext` cùng lấy connection thuộc transaction hiện hành, method thành công sẽ commit ba thay đổi một lần.
- Không được gọi `jdbc.update(...)` bằng một DataSource nhưng cấu hình `dsl` cho database khác rồi kỳ vọng chung transaction.
- `@Transactional` ở đây phải chạy qua **Spring proxy**, ví dụ controller/listener inject bean `WalletDebitService` và gọi `apply`.
- Nếu event có số dư thiếu, exception sẽ khiến message được listener/broker xử lý theo chính sách lỗi; cần phân loại đây là lỗi nghiệp vụ để tránh requeue vô hạn.
- Inbox chỉ chống trùng trong phạm vi business side effect cùng database transaction. Nếu sau đó gọi HTTP hoặc publish broker, cần idempotency/outbox tương ứng.

### Listener RabbitMQ gọi đúng service transaction

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class WalletEventConsumer {

    private final WalletDebitService walletDebitService;

    public WalletEventConsumer(WalletDebitService walletDebitService) {
        this.walletDebitService = walletDebitService;
    }

    @RabbitListener(queues = "wallet.debit.events")
    public void onMessage(DebitAuthorized event) {
        walletDebitService.apply(event);
    }
}
~~~

Đoạn listener giả định converter và payload type `DebitAuthorized` đã được cấu hình. Trong chế độ Spring AMQP AUTO ack thông thường, listener trả về thành công sau transaction commit thì container có thể ACK delivery. Nếu SQL commit rồi connection broker mất trước ACK, message có thể được giao lại; inbox ngăn thao tác debit hai lần. Phải cấu hình retry/reject/DLQ theo kiểu lỗi, **không** để lỗi dữ liệu hay nghiệp vụ không phục hồi được quay vòng vô hạn.

## 5. Vì sao jOOQ có thể vô tình đứng ngoài transaction Spring?

`JdbcTemplate` sử dụng hạ tầng `DataSourceUtils` nhận biết connection gắn với Spring transaction. Nhưng jOOQ không tự biết về mọi `PlatformTransactionManager` của ứng dụng nếu nó chỉ được tạo bằng một DataSource thô, một JDBC URL hoặc `Connection` tự mở:

~~~java
// Cấu hình tùy tiện như thế này cần kiểm tra lại transaction boundary.
DSLContext dsl = DSL.using(dataSource, SQLDialect.POSTGRES);
~~~

Một `DataSource` do pool cấp connection thông thường có thể trả về connection mới khi jOOQ gọi `getConnection()`; connection đó không nhất thiết là connection đang được Spring transaction manager giữ cho `JdbcTemplate`. Vì vậy một bước SQL bằng jOOQ có thể auto-commit ngoài transaction mong muốn.

### TransactionAwareDataSourceProxy

Spring cung cấp `TransactionAwareDataSourceProxy` cho thành phần dùng API `DataSource.getConnection()` nhưng chưa tự gọi `DataSourceUtils`. Proxy này có thể trả connection nhận biết Spring transaction, **miễn là transaction manager quản lý cùng DataSource gốc**.

Một cấu hình minh họa khi **tự tạo DSLContext**:

~~~java
import javax.sql.DataSource;
import org.jooq.DSLContext;
import org.jooq.SQLDialect;
import org.jooq.impl.DSL;
import org.jooq.impl.DataSourceConnectionProvider;
import org.jooq.impl.DefaultConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.TransactionAwareDataSourceProxy;

@Configuration(proxyBeanMethods = false)
public class JooqDataSourceConfiguration {

    @Bean
    DSLContext customDslContext(DataSource dataSource) {
        var config = new DefaultConfiguration();

        config.set(SQLDialect.POSTGRES);
        config.set(new DataSourceConnectionProvider(
                new TransactionAwareDataSourceProxy(dataSource)));

        return DSL.using(config);
    }
}
~~~

Đây là ví dụ cho **một DataSource** và một ranh giới transaction do Spring `@Transactional` điều phối. Nếu Boot đã tự tạo `DSLContext` đúng và bạn chỉ cần một datasource, thường nên **inject bean có sẵn** thay vì khai báo thêm một bean trùng vai trò. Khi cần cấu hình riêng, cân nhắc customizer và hạ tầng Boot trước khi thay toàn bộ bean.

**Phân biệt hai SPI của jOOQ:**

1. `ConnectionProvider` quyết định jOOQ lấy và trả JDBC connection thế nào. Nó cần biết cách tham gia Spring-managed connection.
2. `TransactionProvider` điều phối khi code trực tiếp gọi `dsl.transaction(...)` hoặc `dsl.transactionResult(...)`. Nếu muốn các transaction do jOOQ mở **cũng** dùng Spring manager và cùng propagation, phải cấu hình/giữ provider tích hợp Spring phù hợp.

Cấu hình `TransactionAwareDataSourceProxy` ở trên giúp query **tham gia @Transactional hiện hành**. Nó **không tự khẳng định** rằng `dsl.transaction(...)` dùng đúng cùng `PlatformTransactionManager` trong mọi trường hợp. Với dự án chủ yếu dùng Spring `@Transactional`, đặt transaction boundary ở Spring service là lựa chọn dễ theo dõi; nếu sử dụng DSL transaction API, hãy kiểm tra provider đã được Boot/starter cấu hình và test rollback/nesting với chính phiên bản jOOQ của dự án.

### Tránh tạo connection thủ công trong service

Đoạn này phá vỡ giả định transaction-aware:

~~~java
@Transactional
public void broken() throws Exception {
    try (var connection = DriverManager.getConnection(url, user, password)) {
        connection.createStatement()
                .executeUpdate("UPDATE wallet SET balance_cents = 0");
    }
}
~~~

`DriverManager` mở connection độc lập với `DataSource` do transaction manager quản lý. Khi transaction ngoài rollback, UPDATE trên connection thủ công có thể đã commit. `try-with-resources` đóng tài nguyên nhưng không làm connection tham gia transaction Spring.

Nếu bắt buộc dùng JDBC API trực tiếp, nên lấy connection qua `DataSourceUtils.getConnection(dataSource)` và trả bằng `DataSourceUtils.releaseConnection(...)`; hoặc sử dụng callback của `JdbcTemplate` để nó xử lý nhận/trả connection đúng. Không tự `commit()`, `rollback()`, bật `autoCommit` hoặc đóng connection đang được Spring quản lý trong nghiệp vụ.

## 6. Chọn transaction manager trong ứng dụng nhiều DataSource

Ứng dụng có thể kết nối một database nghiệp vụ `paymentsDb` và một database báo cáo `reportingDb`. Không có một `JdbcTransactionManager` local nào tự bao trùm cả hai connection pool.

~~~mermaid
flowchart TD
    SERVICE["ReportingService"] --> PDB["payments DataSource"]
    SERVICE --> RDB["reporting DataSource"]
    PDB --> PTX["paymentsTransactionManager"]
    RDB --> RTX["reportingTransactionManager"]
    PTX --> PCONN["PostgreSQL payments connection"]
    RTX --> RCONN["PostgreSQL reporting connection"]
    WARN["Không tự có atomic commit giữa hai DB"] -.-> PCONN
    WARN -.-> RCONN
~~~

Mỗi `DataSource` cần các bean truy vấn và transaction manager tương ứng. Ví dụ giả định project đã tạo và đặt tên bean `reportingDataSource`:

~~~java
import javax.sql.DataSource;
import org.jooq.DSLContext;
import org.jooq.SQLDialect;
import org.jooq.impl.DSL;
import org.jooq.impl.DataSourceConnectionProvider;
import org.jooq.impl.DefaultConfiguration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.JdbcTransactionManager;
import org.springframework.jdbc.datasource.TransactionAwareDataSourceProxy;

@Configuration(proxyBeanMethods = false)
public class ReportingJdbcConfiguration {

    @Bean("reportingTransactionManager")
    JdbcTransactionManager reportingTransactionManager(
            @Qualifier("reportingDataSource") DataSource reportingDataSource) {
        return new JdbcTransactionManager(reportingDataSource);
    }

    @Bean("reportingJdbcTemplate")
    JdbcTemplate reportingJdbcTemplate(
            @Qualifier("reportingDataSource") DataSource reportingDataSource) {
        return new JdbcTemplate(reportingDataSource);
    }

    @Bean("reportingDsl")
    DSLContext reportingDsl(
            @Qualifier("reportingDataSource") DataSource reportingDataSource) {

        var config = new DefaultConfiguration();
        config.set(SQLDialect.POSTGRES);
        config.set(new DataSourceConnectionProvider(
                new TransactionAwareDataSourceProxy(reportingDataSource)));
        return DSL.using(config);
    }
}
~~~

Service dùng explicit qualifier:

~~~java
import org.jooq.DSLContext;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReportingImportService {

    private final JdbcTemplate reportingJdbc;
    private final DSLContext reportingDsl;

    public ReportingImportService(
            @Qualifier("reportingJdbcTemplate") JdbcTemplate reportingJdbc,
            @Qualifier("reportingDsl") DSLContext reportingDsl) {
        this.reportingJdbc = reportingJdbc;
        this.reportingDsl = reportingDsl;
    }

    @Transactional(transactionManager = "reportingTransactionManager")
    public void updateReport(long reportId) {
        reportingJdbc.update(
                "UPDATE reporting_job SET state = ? WHERE id = ?",
                "PROCESSING", reportId);

        reportingDsl.execute(
                "UPDATE reporting_audit SET last_run_at = CURRENT_TIMESTAMP " +
                "WHERE job_id = ?", reportId);
    }
}
~~~

Đoạn code chứng minh rõ **kết nối truy vấn** được tạo từ `reportingDataSource` và manager được chỉ định là `reportingTransactionManager`. Nó không chứng minh commit giữa reporting DB và payments DB là atomic; đó là hai tài nguyên độc lập.

Nếu toàn ứng dụng có cả auto-configured primary DataSource/DSLContext và reporting DataSource/DSLContext, hãy dùng tên bean, `@Qualifier`, `@Primary` và các điều kiện auto-configuration một cách minh bạch. Tránh dùng một `DSLContext` thiếu qualifier khi có nhiều bean cùng type.

### Ghi hai database trong một nghiệp vụ thì sao?

Ví dụ ghi order vào payments DB rồi ghi audit vào reporting DB:

- Nếu chỉ dùng `paymentsTransactionManager`, thao tác trên reporting DB không tự rollback theo payments.
- Nếu mở hai local transaction tuần tự, vẫn có thời điểm một database commit thành công, database kia lỗi.
- `@Transactional` với một manager không tạo XA/2PC.
- `ChainedTransactionManager`/commit tuần tự không cung cấp atomic transaction thật sự khi một commit đã hoàn tất rồi commit sau thất bại.
- Nếu cần tính nhất quán xuyên hệ thống, ưu tiên **outbox + event consumer idempotent + trạng thái eventual consistency** hoặc kiến trúc giao dịch phân tán được hạ tầng hỗ trợ và chấp nhận chi phí rõ ràng.

Đối với hệ thống tích hợp với HTTP, broker, cache và object store, **đừng mặc định mọi thứ đều tham gia một transaction ACID**. Local JDBC transaction chỉ có hiệu lực trong tài nguyên database được quản lý.

## 7. Ranh giới @Transactional, exception và self-invocation

### Proxy invocation là điều kiện quan trọng

Spring `@Transactional` trong cấu hình proxy thông thường chỉ áp dụng khi method được gọi **qua proxy Spring**. Lỗi phổ biến:

~~~java
@Service
public class OrderService {

    public void entryPoint(long orderId) {
        // Gọi method cùng class: self-invocation, không qua proxy.
        this.updateInTransaction(orderId);
    }

    @Transactional
    public void updateInTransaction(long orderId) {
        // Có thể không có transaction nếu chỉ được gọi qua this.
    }
}
~~~

Giải pháp có thể là tách transaction method sang một Spring service khác và inject service đó, hoặc thiết kế orchestration khác; không dùng lời gọi `this.` để “bật” annotation. Tương tự, tạo object bằng `new SomeService()` thay vì Spring bean, method private/final hoặc cấu hình proxy đặc biệt có thể làm lời gọi không được intercept như dự kiến. Nên đặt transaction ở **public service method** và test ranh giới qua bean thật.

### Checked exception không rollback theo mặc định

Theo quy tắc mặc định của Spring `@Transactional`, **`RuntimeException` và `Error`** khiến transaction rollback; checked exception không mặc định rollback trừ khi cấu hình. Ví dụ:

~~~java
@Transactional(rollbackFor = IOException.class)
public void importDocument(InputStream input) throws IOException {
    // JDBC/jOOQ writes...
    // IOException phải được khai báo rollbackFor nếu muốn rollback SQL.
}
~~~

Tránh dùng `rollbackFor = Exception.class` như phương án máy móc nếu hệ thống có checked exception được coi là kết quả nghiệp vụ chấp nhận commit. Hãy định nghĩa ngoại lệ nào báo thất bại transaction. Nếu method bắt exception rồi chỉ log và trả về bình thường, Spring có thể **commit**, dù nghiệp vụ đã lỗi. Muốn rollback khi xử lý lỗi nội bộ, thường tốt nhất ném exception phù hợp; trong các trường hợp đặc biệt có thể đánh dấu rollback-only thông qua TransactionAspectSupport, nhưng điều đó cần lý do và test rõ.

### Rollback-only và UnexpectedRollbackException

Giả sử method ngoài mở transaction, method trong dùng `PROPAGATION_REQUIRED` tham gia cùng transaction và gặp RuntimeException. Method ngoài bắt lỗi rồi cố commit bình thường. Nếu transaction đã bị đánh dấu rollback-only, Spring sẽ rollback và có thể ném `UnexpectedRollbackException`. Đừng xử lý ngoại lệ này bằng cách retry mù hoặc bỏ qua: phải xem tầng nào đã đánh dấu transaction không thể commit.

### `@Transactional(readOnly = true)` là hint/chính sách, không là quyền

~~~java
@Transactional(readOnly = true)
public WalletSnapshot getSnapshot(long accountId) {
    return dsl.selectFrom(WALLET)
            .where(WALLET.ACCOUNT_ID.eq(accountId))
            .fetchOneInto(WalletSnapshot.class);
}
~~~

`readOnly=true` có thể giúp framework/driver/ORM tối ưu hoặc yêu cầu database read-only mode theo cấu hình, nhưng **không phải cơ chế phân quyền bảo mật** và không luôn cấm mọi kiểu ghi trên mọi database/driver. Quyền database vẫn cần được cấp tối thiểu và thử trên môi trường thật.

## 8. Propagation, isolation và savepoint ảnh hưởng gì đến truy vấn?

| Propagation | Hành vi cốt lõi | Rủi ro khi dùng tùy tiện |
| --- | --- | --- |
| `REQUIRED` (mặc định) | Tham gia transaction đang có hoặc tạo mới | Method trong đánh dấu rollback-only làm transaction ngoài không thể commit |
| `REQUIRES_NEW` | Tạm gác transaction hiện tại và mở transaction vật lý mới | Cần thêm connection, có thể commit độc lập, cạn pool khi lồng nhiều tầng |
| `NESTED` | Tham gia bằng savepoint trong transaction ngoài khi manager/driver hỗ trợ | Không giống transaction vật lý độc lập; hỗ trợ phụ thuộc DB/JDBC |
| `MANDATORY` | Phải có transaction hiện hữu | Lỗi khi caller quên mở boundary |
| `SUPPORTS` | Có thì tham gia, không có thì chạy không có transaction | Những thao tác ghi có thể auto-commit khi caller không mở transaction |
| `NOT_SUPPORTED` | Chạy ngoài transaction, suspend transaction hiện có | Query không còn atomic với thao tác ngoài |
| `NEVER` | Báo lỗi nếu đang có transaction | Chỉ thích hợp cho những API đòi hỏi không có transaction |

`REQUIRES_NEW` hữu ích khi thực sự muốn audit độc lập, nhưng một transaction ngoài đang giữ connection rồi mở transaction trong có thể khiến pool cần **nhiều hơn một connection cho cùng thread**. Nếu 10 request giữ 10 connection và cùng chờ một REQUIRES_NEW trong pool kích thước 10, có nguy cơ deadlock vì không còn connection để mở transaction mới. Điều chỉnh kiến trúc trước khi chỉ tăng pool vô hạn.

`NESTED` trên JDBC thường dựa vào savepoint. Kiểm tra database, driver và manager có hỗ trợ savepoint; với jOOQ `dsl.transaction(...)`, không suy ra mọi nested block mang cùng semantics với Spring propagation `NESTED` nếu transaction provider khác.

### Isolation và điều kiện tranh chấp

`@Transactional(isolation = Isolation.READ_COMMITTED)` chỉ đặt isolation khi **mở transaction mới** theo cơ chế có hiệu lực; nếu method tham gia transaction đang có, nó thường kế thừa isolation của transaction hiện hữu. Các mức như READ_COMMITTED, REPEATABLE_READ, SERIALIZABLE có hành vi cụ thể tùy DB. Không kỳ vọng mọi hệ quản trị hỗ trợ giống nhau hoặc mỗi isolation loại bỏ mọi business race.

Với thao tác số dư ví dụ, query:

~~~sql
UPDATE wallet
SET balance_cents = balance_cents - :amount
WHERE account_id = :accountId
  AND balance_cents >= :amount;
~~~

cùng kiểm tra affected row thường chắc chắn hơn kiểu `SELECT balance; if đủ thì UPDATE` không có locking. Nếu cần đọc một tập bản ghi rồi update theo điều kiện tổng, cân nhắc `SELECT ... FOR UPDATE`, optimistic version column, constraint hoặc isolation cao hơn; cần thiết kế với đặc điểm concurrency cụ thể và kiểm thử hai transaction chạy đồng thời.

## 9. Timeout có nhiều nghĩa: query, transaction, pool và downstream

Một transaction quá dài không chỉ làm API chậm: nó giữ connection, lock và tăng nguy cơ deadlock/thắt cổ chai. Cần phân biệt bốn loại timeout:

| Loại | Ví dụ cấu hình | Điều giới hạn |
| --- | --- | --- |
| Connection acquisition timeout | Hikari `connectionTimeout` | Thời gian chờ lấy một connection rảnh từ pool |
| JDBC statement/query timeout | `JdbcTemplate.setQueryTimeout(...)`, statement-level timeout, DB `statement_timeout` | Thời gian thực thi SQL hoặc chờ kết quả theo driver/DB |
| Spring transaction timeout | `@Transactional(timeout = 5)` | Deadline của transaction do manager quản lý; enforcement phụ thuộc hạ tầng SQL |
| HTTP/RPC/broker timeout | Client HTTP timeout, RSocket/gRPC deadline, consumer timeout | Tài nguyên ngoài DB, không tự nằm trong JDBC transaction |

Ví dụ:

~~~java
@Transactional(timeout = 5)
public void reserve(long walletId, long amount) {
    // Các truy vấn tham gia transaction; không nên có HTTP 30 giây ở đây.
}
~~~

`timeout = 5` là **giây**. Đừng hiểu nó là cơ chế một thread chắc chắn bị ngắt đúng tại giây thứ năm và toàn bộ side effect ngoài database được rollback. Spring JDBC có thể truyền thời gian transaction còn lại vào statement khi sử dụng `DataSourceUtils`/`JdbcTemplate`; jOOQ/driver cần được kiểm tra cách áp dụng query timeout thật sự. Một JDBC statement chạy lâu còn chịu policy của database và socket read timeout.

Khi luồng nghiệp vụ cần gọi API bên ngoài rồi cập nhật SQL, thường nên tách phase: gọi HTTP với deadline hợp lý **ngoài một transaction giữ lock dài**, sau đó mở transaction ngắn để ghi kết quả và trạng thái/phiên bản, hoặc áp dụng orchestration/outbox phù hợp.

## 10. Retry, deadlock và idempotency

Mỗi lần retry một **giao dịch thất bại** phải được coi là một lần thực hiện mới có thể bao gồm nhiều SQL statement. Không retry chỉ statement cuối một cách mù quáng sau deadlock hoặc serialization failure: database thường đã đánh dấu transaction phải rollback.

Ví dụ một tầng orchestration retry toàn bộ service method:

~~~java
@Service
public class DebitOrchestrator {

    private final WalletDebitService walletDebitService;

    public DebitOrchestrator(WalletDebitService walletDebitService) {
        this.walletDebitService = walletDebitService;
    }

    public void applyWithRetry(DebitAuthorized event) {
        // RetryTemplate/Resilience4j hoặc policy ngoài theo exception.
        // Mỗi attempt gọi qua Spring proxy để mở transaction mới.
        walletDebitService.apply(event);
    }
}
~~~

Đây là phác thảo vị trí retry; nếu dùng `@Retryable` và `@Transactional` trên **cùng method**, thứ tự advice quyết định retry chạy **ngoài** hay **bên trong** transaction. Hãy kiểm tra cấu hình advice và viết integration test để bảo đảm mỗi attempt thật sự mở một transaction mới. Một giải pháp dễ suy luận là tách orchestrator retry và service transaction thành các bean khác như trên.

Phân loại lỗi:

- **Transient**: một số deadlock, lock timeout, serialization failure, gián đoạn mạng ngắn. Retry có điều kiện, giới hạn attempts/backoff/jitter, trong ngân sách toàn request.
- **Permanent**: lỗi schema, SQL sai, vi phạm khóa ngoại do hợp đồng sai, dữ liệu không hợp lệ. Không retry vô hạn.
- **Unknown outcome**: DB commit có thể thành công nhưng ACK/response mất; cần **idempotency key** và khả năng kiểm tra lại kết quả.

Spring `DataAccessException` có các nhánh biểu thị transient/non-transient ở mức framework; jOOQ exception có thể được Boot dịch sang Spring exception trong một số cấu hình. Nếu code tự tạo `DSLContext`, hãy xác định ngoại lệ đầu ra thực tế và exception translator phù hợp; đừng phân loại retry chỉ theo một tên exception chung.

Một thiết kế với message broker nên giữ `eventId` bất biến trong mọi lần retry; đừng sinh UUID mới mỗi attempt. Bảng `processed_events` có khóa unique trong cùng transaction tạo hiệu ứng nghiệp vụ một lần đối với những thay đổi SQL đã bảo vệ, dù message có thể được broker giao lại.

## 11. Khác biệt giữa Spring @Transactional và jOOQ DSL transaction API

jOOQ cung cấp API:

~~~java
dsl.transaction(configuration -> {
    DSLContext transactionalDsl = DSL.using(configuration);
    // Chạy các jOOQ query thuộc transaction provider được cấu hình.
});
~~~

Trong code trên, `configuration` là jOOQ `Configuration` được cấp cho transaction callback. Khi dùng trực tiếp `dsl.transaction(...)`, hành vi bắt đầu/commit/rollback do **jOOQ TransactionProvider** điều phối. Với Spring Boot auto-configured jOOQ, provider thường được tích hợp với Spring `PlatformTransactionManager` theo cấu hình hiện hành. Nếu tự dựng `DSLContext`, hãy cấu hình provider phù hợp nếu muốn dùng cả jOOQ transaction API.

Các câu hỏi phải xác minh trước khi trộn hai hình thức:

1. `dsl.transaction(...)` đang gọi Spring provider hay jOOQ provider mặc định?
2. Nếu chạy trong `@Transactional`, transaction bên trong join, tạo savepoint hay dùng manager khác?
3. JDBC code trong callback nhận đúng connection không?
4. Khi exception được catch, transaction nào rollback và transaction nào còn active?
5. Có nhiều DataSource/manager không và provider chọn resource nào?

Hướng thực hành đơn giản cho service dùng JDBC + jOOQ cùng một SQL database: **đặt một transaction boundary ở Spring service** rồi gọi `JdbcTemplate` và `DSLContext` đã inject. Dùng `dsl.transaction(...)` khi thực sự cần transaction API của jOOQ và đã test toàn bộ đường đi cùng manager.

## 12. Giao dịch DB với message broker, HTTP và cache: điểm dừng của ACID

Trong module tích hợp, một luồng có thể ghi PostgreSQL, gửi Kafka/RabbitMQ, gọi REST, cập nhật Redis và upload file. Một `JdbcTransactionManager` **chỉ quản lý local JDBC resource**. Nó không tự rollback Kafka message, HTTP side effect hoặc Redis update sau khi SQL rollback.

### Vấn đề “dual write”

Ví dụ:

~~~java
@Transactional
public void createOrder(Order order) {
    orderRepository.insert(order);      // Transaction SQL
    rabbitTemplate.convertAndSend(
            "orders.exchange", "order.created", order);
    // Publish RabbitMQ không tự atomic với SQL commit.
}
~~~

Hai rủi ro:

- Broker nhận event nhưng SQL commit sau đó thất bại → downstream nhìn thấy một đơn hàng không tồn tại.
- SQL commit thành công nhưng ứng dụng chết trước publish → đơn hàng có trong DB, event bị thiếu.

Một cách xử lý thực dụng là **transactional outbox**:

~~~mermaid
sequenceDiagram
    participant API as order-service
    participant DB as PostgreSQL
    participant RELAY as Outbox relay
    participant MQ as RabbitMQ/Kafka
    participant C as Consumer

    API->>DB: BEGIN
    API->>DB: INSERT orders
    API->>DB: INSERT outbox_events (eventId, payload)
    API->>DB: COMMIT
    RELAY->>DB: Đọc outbox chưa phát
    RELAY->>MQ: Publish event
    MQ-->>RELAY: Publish confirmation
    RELAY->>DB: Đánh dấu đã phát / lưu offset
    MQ->>C: Deliver
    C->>DB: Inbox idempotency + business transaction
~~~

Outbox commit cùng business data trong một SQL transaction. Relay có thể publish trùng nếu broker đã nhận nhưng relay chưa ghi trạng thái đã phát; consumer cần idempotency. Chỉ đánh dấu outbox đã publish khi có xác nhận đủ theo SLA và xử lý trường hợp publish unroutable/failure. Như vậy outbox giảm rủi ro mất event tại ranh giới SQL–broker, nhưng không tự tạo exactly-once trên mọi hệ thống.

### @TransactionalEventListener(AFTER_COMMIT) có đủ không?

Một event listener chạy `AFTER_COMMIT` có thể tránh publish trước khi SQL commit, nhưng **nếu process chết sau commit và trước publish**, event vẫn có thể mất. Nó phù hợp side effect best-effort; nếu yêu cầu chuyển giao bền vững, cần outbox hoặc cơ chế đảm bảo khác. Đặc biệt lưu ý khi `AFTER_COMMIT` chạy, nguồn transaction SQL đã commit; các thao tác DB mới phải có boundary độc lập nếu cần ghi bền vững.

### Cache invalidation

Cập nhật Redis/cache trong transaction SQL rồi SQL rollback có thể để cache lệch với DB. Thường cần invalidation/update **sau khi commit** hoặc phát event qua outbox và chọn mô hình eventual consistency. Đừng mở rộng phạm vi một JDBC manager để hứa hẹn rollback cache từ xa.

## 13. Xử lý truy vấn trong Spring Integration flow và thread khác

Một `@ServiceActivator`, `@JmsListener`, `@RabbitListener` hoặc HTTP controller đều có thể gọi Spring service `@Transactional` nếu bean được inject đúng. Tuy nhiên, khi flow chuyển qua asynchronous channel, executor, scheduled task, virtual thread mới hoặc Reactor scheduler khác, **ThreadLocal transaction context không được tự truyền theo**.

~~~mermaid
flowchart LR
    IN["HTTP / RabbitMQ / Integration channel"] --> SVC["Spring @Transactional Service"]
    SVC --> DB[("DB transaction trên thread hiện tại")]
    SVC --> ASYNC["Async executor / khác thread"]
    ASYNC --> NEWTX["Cần boundary transaction mới nếu ghi SQL"]
~~~

Một số ví dụ thực tế:

- `ExecutorChannel` của Spring Integration có thể chuyển message sang thread khác; transaction bắt đầu ở thread trước đó không “đi theo” message.
- `@Async` chạy bằng executor, phải tự có transaction boundary trên service được gọi trong thread mới.
- `CompletableFuture.supplyAsync(...)` hoặc `parallelStream()` không được giả định chia sẻ JDBC connection của transaction ngoài.
- Trong WebFlux, `@Transactional` với JDBC imperative manager không biến blocking JDBC thành reactive; nếu dùng JDBC trong pipeline reactive, cần lập kế hoạch scheduler/thread hoặc chuyển sang R2DBC với `R2dbcTransactionManager`.
- Khi một message listener nhận và gọi transactional service, **acknowledgement của broker** thường ở ranh giới khác với SQL commit. Kiểm soát lỗi, redelivery và inbox theo thiết kế tích hợp.

Nếu có luồng qua các thread, hãy vẽ rõ **transaction boundary tại mỗi đoạn** và gửi dữ liệu/ID qua message, thay vì gửi `Connection`, `DSLContext` gắn transaction state hoặc entity không an toàn giữa thread.

## 14. Đo lường connection, transaction và SQL để tìm lỗi

Một service có thể “chạy ổn” ở mức API nhưng liên tục giữ transaction quá lâu hoặc tạo connection ngoài pool. Cần quan sát:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| Hikari active/idle/pending connections | Pool có cạn do giữ transaction, leak hoặc thiếu capacity không |
| Connection acquisition latency | Có nhiều request chờ connection hay không |
| Transaction duration, rollback/commit rate | Transaction quá dài hoặc rollback tăng đột biến |
| SQL latency, statement timeout, lock wait | Phân biệt truy vấn chậm với chờ lock |
| Deadlock/serialization failures | Áp lực cạnh tranh và nhu cầu retry có kiểm soát |
| jOOQ query execution events | Bắt SQL chậm theo loại truy vấn mà không lộ dữ liệu bind |
| Spring JDBC exception categories | Xem transient/non-transient failure theo đường truy vấn |
| Duplicate event/inbox hits | Đo redelivery và mức chống trùng nghiệp vụ |
| Outbox backlog/age và publish failures | Phát hiện DB đã commit nhưng event chưa được phát |
| Database session count theo service instance | Kiểm tra tổng pool qua nhiều pod vượt giới hạn server không |

Spring Boot Actuator/Micrometer có thể xuất một số metric DataSource/Hikari nếu dependency và registry phù hợp; jOOQ `ExecuteListener` hoặc instrumentation riêng có thể theo dõi SQL và thời gian execution. Không bật log đầy đủ giá trị bind chứa thông tin thanh toán, cá nhân hoặc credential trong production. Nên log requestId, eventId, correlationId, operation, số row bị ảnh hưởng và timing đã làm sạch.

### Phân biệt connection leak với transaction giữ lock lâu

- **Leak**: application không release connection/stream hoặc tự mở connection mà không đóng; active connections tăng kéo dài.
- **Long transaction**: connection được Spring giữ hợp lệ nhưng quá lâu do HTTP call, sleep, query chậm hoặc lock wait; pool vẫn có thể cạn.
- **Pool exhaustion do REQUIRES_NEW**: một logical request có thể cần nhiều physical connection cùng lúc.
- **Connection churn**: ứng dụng tạo DataSource/DSLContext/client mới liên tục thay vì bean singleton.

Cách xử lý khác nhau: tăng pool chỉ giảm triệu chứng nếu transaction thiết kế sai. Đo `transaction duration` cùng `SQL time` sẽ cho biết chậm ở DB hay do code giữ connection rồi chờ downstream.

## 15. Kiểm thử transaction tích hợp trên database thật

Unit test mock `JdbcTemplate` và `DSLContext` có thể xác minh lời gọi, nhưng **không chứng minh chúng thực sự dùng cùng connection hoặc rollback cùng nhau**. Cần integration test với database đúng loại, tốt nhất PostgreSQL chạy qua Testcontainers/CI và schema migration gần giống production.

### Các trường hợp tối thiểu

| Kịch bản | Thiết lập | Kỳ vọng |
| --- | --- | --- |
| Mọi thao tác thành công | INSERT inbox + jOOQ UPDATE + INSERT ledger | Cả ba thay đổi commit |
| Query JDBC cuối ném lỗi | Cố tình vi phạm constraint tại bước ledger | jOOQ UPDATE và INSERT inbox cùng rollback |
| jOOQ UPDATE không cập nhật row | Số dư thấp, service ném RuntimeException | Inbox rollback, số dư và ledger không đổi |
| Broker redelivery cùng eventId | Gọi hai lần cùng event ID sau commit | Lần hai không trừ thêm số dư |
| Hai consumer chạy đồng thời cùng eventId | Gửi hai delivery song song | Unique inbox bảo vệ; kết quả cuối chỉ có một debit |
| Transaction manager sai DataSource | Cố tình tạo cấu hình miswired trong môi trường test | Test rollback thất bại, phát hiện wiring |
| Self-invocation | Gọi method annotated qua `this` thay vì proxy | Test cho thấy không có boundary như kỳ vọng |
| Checked exception | Ném IOException, so sánh có/không rollbackFor | Hành vi đúng với rule đã khai báo |
| REQUIRES_NEW | Transaction ngoài rollback sau khi transaction trong commit | Thấy rõ sự độc lập và chi phí connection |
| NESTED/savepoint | Nested block lỗi | Chỉ phần sau savepoint rollback nếu DB/driver hỗ trợ |
| Deadlock/serialization failure | Hai transaction cạnh tranh | Rollback toàn transaction và retry đúng ngân sách |
| Message retry sau SQL commit trước ACK | Inject lỗi ở broker channel | Inbox idempotency chặn side effect trùng |
| Outbox relay crash | Publish trước khi ghi trạng thái outbox | Có thể publish trùng, consumer xử lý an toàn |

### Ví dụ kiểm tra rollback của cả JDBC và jOOQ

Một integration test đơn giản có thể gọi service qua Spring proxy rồi kiểm tra trạng thái bên ngoài transaction test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class WalletTransactionIntegrationTest {

    @Autowired WalletDebitService walletDebitService;
    @Autowired JdbcTemplate jdbc;

    @Test
    void rollsBackInboxAndWalletWhenLedgerInsertFails() {
        // Fixture từ migration/test setup:
        // wallet(42, 10000) tồn tại;
        // ledger đã có event_id = EVT-DUPLICATE,
        // nhưng processed_events chưa có event này.

        var event = new DebitAuthorized(
                "EVT-DUPLICATE", 42L, 1_500L);

        assertThatThrownBy(() -> walletDebitService.apply(event))
                .isInstanceOf(RuntimeException.class);

        Long balance = jdbc.queryForObject(
                "SELECT balance_cents FROM wallet WHERE account_id = ?",
                Long.class, 42L);
        Integer inboxRows = jdbc.queryForObject(
                """
                SELECT COUNT(*) FROM processed_events
                WHERE consumer_name = ? AND event_id = ?
                """,
                Integer.class, "wallet-debit-v1", "EVT-DUPLICATE");

        assertThat(balance).isEqualTo(10_000L);
        assertThat(inboxRows).isZero();
    }
}
~~~

Đây là **mẫu test** giả định fixtures được thiết lập trước và có code generation cho jOOQ. Nếu ledger đã có cùng event ID, INSERT cuối phải vi phạm unique constraint, phát sinh RuntimeException; khi transaction được cấu hình đúng, UPDATE wallet và INSERT inbox cùng rollback. Cần cách ly/cleanup fixtures để test độc lập, và quan trọng là **không đánh dấu chính test method bằng `@Transactional`** rồi để Spring test framework rollback toàn test, vì điều đó có thể che việc service không commit/rollback đúng ở boundary riêng.

Bổ sung một integration test đọc qua cả `JdbcTemplate` và jOOQ trong cùng service khi có uncommitted write để phát hiện lỗi provider dùng connection khác. Test với hai kết nối/transaction song song giúp phát hiện anomaly/isolation hơn unit test.

## 16. Các lỗi cấu hình thường gặp và cách sửa

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra/sửa |
| --- | --- | --- |
| `@Transactional` có nhưng jOOQ UPDATE vẫn commit khi JDBC lỗi | jOOQ tự mở connection ngoài Spring transaction | Inject Boot `DSLContext` hoặc dùng `TransactionAwareDataSourceProxy` đúng DataSource |
| Không thấy transaction khi gọi method cùng class | Self-invocation bỏ qua Spring proxy | Tách transactional service hoặc thay kiến trúc gọi |
| Có nhiều transaction manager, commit sai database | Manager được chọn không tương ứng với DataSource của query | Dùng qualifier rõ và kiểm thử mapping |
| Có `JpaTransactionManager` nhưng dùng JDBC/jOOQ | Chưa xác nhận cùng DataSource/connection và khả năng participation | Kiểm tra JPA/JDBC setup; chọn manager thống nhất cho resource |
| Service xử lý checked exception nhưng dữ liệu vẫn commit | Mặc định không rollback checked exception | Khai báo rollbackFor phù hợp với hợp đồng |
| Catch exception xong method return bình thường | Spring hiểu thành công và commit | Ném exception phù hợp hoặc đánh dấu rollback-only có chủ đích |
| `UnexpectedRollbackException` ở method ngoài | Inner REQUIRED đánh dấu rollback-only | Tìm lỗi gốc, điều chỉnh boundary/propagation |
| Pool hết connection khi gọi transaction lồng nhau | REQUIRES_NEW giữ thêm physical connection | Giảm lồng, điều chỉnh orchestration/pool dựa trên tải |
| Transaction rất dài dù SQL nhanh | Giữ transaction qua HTTP/broker call hoặc sleep | Tách phần remote I/O ra khỏi transaction ngắn |
| Query chạy ngoài transaction trong @Async | ThreadLocal không tự lan sang thread khác | Mở boundary mới trong bean/service chạy async |
| jOOQ `dsl.transaction` không cùng semantics Spring | TransactionProvider không được nối với manager | Cấu hình provider hoặc thống nhất dùng @Transactional |
| RabbitMQ redelivery làm trừ tiền hai lần | SQL commit trước ACK, không có inbox unique | Giữ eventId, transaction và unique constraint |
| DB đã có order nhưng Kafka/Rabbit không có event | Dual write không atomic | Transactional outbox, relay, idempotent consumer |
| Read-only không ngăn được UPDATE | Read-only hint bị driver/DB bỏ qua | DB grants và kiểm thử chính sách thực tế |
| Test pass nhưng production rollback sai | Unit mock hoặc test-level rollback che lỗi | Integration test DB thật, transaction boundary ngoài test |

## 17. Checklist áp dụng cho dự án Spring Boot

1. Xác định **resource** được thao tác: một JDBC DataSource, JPA, R2DBC hay nhiều database; chọn manager tương ứng.
2. Với JDBC/jOOQ imperative trong một database, ưu tiên cấu hình `JdbcTransactionManager` hoặc manager đã được Boot thiết lập đúng; xác minh class bean ở runtime.
3. Inject `JdbcTemplate`/`DSLContext` từ đúng DataSource; nếu tạo jOOQ thủ công, dùng connection provider tham gia Spring transaction.
4. Khi có nhiều DataSource/manager, đặt tên bean, qualifier và `@Transactional(transactionManager = "...")` minh bạch; kiểm thử từng luồng.
5. Đặt transaction boundary ở Spring service method gọi qua proxy; tránh self-invocation và thao tác async ngoài boundary.
6. Phân loại exception và rollback rule, hiểu `REQUIRED`, `REQUIRES_NEW`, `NESTED`, isolation và rollback-only.
7. Giữ transaction ngắn, đặt query/transaction timeout phù hợp và đo lock/pool/SQL latency.
8. Với retry, thử lại **toàn bộ transaction** theo chính sách, giữ idempotency key ổn định và giới hạn attempts.
9. Khi tương tác broker/HTTP/cache/object storage, xác định rõ điểm hết ACID; dùng inbox/outbox, trạng thái và bù trừ nếu cần.
10. Test trên database thật các tình huống rollback cả JDBC–jOOQ, concurrent duplicate, nested transaction, deadlock, ACK mất và outbox replay.
11. Quan sát transaction duration, rollback, pool, SQL, idempotency hits và outbox lag; tránh log bind values nhạy cảm.

### Tài liệu tham khảo để đối chiếu API theo phiên bản

- [Spring Framework – Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): declarative transaction, propagation, rollback và resource binding.
- [Spring Framework – JDBC Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `DataSourceUtils`, `TransactionAwareDataSourceProxy` và quản lý connection.
- [Spring Boot – SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): DataSource, transaction manager, JDBC, jOOQ auto-configuration.
- [jOOQ – Transactions](https://www.jooq.org/doc/latest/manual/sql-execution/transaction-management/): `DSLContext.transaction`, TransactionProvider và transaction nesting.
- [Spring Framework – Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionTemplate` cho các boundary rõ ràng khi annotation không phù hợp.

**Ghi nhớ:** `@Transactional` định nghĩa ý định, còn **transaction manager đúng resource cùng connection provider đúng** mới quyết định JDBC và jOOQ commit/rollback chung. Kiểm chứng trên database thật, chống xử lý trùng bằng khóa nghiệp vụ và tôn trọng ranh giới của broker/HTTP/cache giúp các luồng tích hợp Spring Boot giữ nhất quán khi xảy ra lỗi, retry và mất kết nối.

