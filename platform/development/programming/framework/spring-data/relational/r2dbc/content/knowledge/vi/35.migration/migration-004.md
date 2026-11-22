# Phân tách giao dịch và tài nguyên khi JDBC cùng tồn tại với R2DBC

Một ứng dụng Spring có thể cần dùng JDBC và R2DBC cùng lúc trong giai đoạn chuyển đổi hoặc vì hai loại công việc có đặc điểm khác nhau. Ví dụ, module cũ vẫn dùng JdbcTemplate để đọc và ghi dữ liệu, trong khi module mới dùng Spring Data R2DBC để xử lý API reactive. Flyway hoặc Liquibase cũng thường sử dụng JDBC để chạy migration, ngay cả khi runtime của ứng dụng dùng R2DBC.

Điểm cần hiểu rõ là JDBC và R2DBC quản lý kết nối, transaction và execution context theo hai cơ chế khác nhau. Một DataSource và một ConnectionFactory là hai nguồn tài nguyên riêng. JDBC transaction thường gắn với thread hiện tại; reactive transaction của R2DBC được truyền qua Reactor Context. Việc hai API cùng trỏ tới một database không khiến chúng tự động dùng chung connection hoặc cùng một transaction.

Nếu không tách rõ ranh giới, ứng dụng có thể gặp những lỗi khó chẩn đoán: một phần dữ liệu đã commit trong khi phần còn lại rollback, annotation @Transactional chọn nhầm transaction manager, JDBC blocking call chạy trên event-loop, connection pool bị tính thiếu, hoặc test cho kết quả khác với runtime.

Bài học này giải thích cách Spring quản lý hai loại tài nguyên, cách cấu hình riêng DataSource và ConnectionFactory, chọn PlatformTransactionManager và ReactiveTransactionManager, kết hợp code blocking với reactive an toàn, xử lý consistency giữa hai transaction, dùng migration JDBC trong ứng dụng R2DBC, và kiểm thử các tình huống commit/rollback thực tế.

## 1. Mô hình tài nguyên: JDBC và R2DBC là hai đường kết nối

Một ứng dụng dùng cả hai công nghệ thường có hai stack riêng:

~~~text
Ứng dụng Spring
    |
    +------------------------------+
    |                              |
    v                              v
JDBC / imperative              R2DBC / reactive
    |                              |
    v                              v
DataSource                    ConnectionFactory
    |                              |
    v                              v
JDBC Connection               R2DBC Connection
    |                              |
    v                              v
PlatformTransactionManager    ReactiveTransactionManager
    |                              |
    v                              v
Thread-bound transaction      Reactor Context transaction
    |                              |
    v                              v
JdbcTemplate / JDBC DAO        DatabaseClient / R2DBC Repository
    |                              |
    +--------------+---------------+
                   |
                   v
             Database server
~~~

Hai nhánh có thể kết nối tới cùng một database server, cùng database và thậm chí cùng schema. Nhưng connection vẫn được tạo và quản lý riêng.

| Thành phần | JDBC | R2DBC |
|---|---|---|
| API kết nối | DataSource | ConnectionFactory |
| Connection | java.sql.Connection | io.r2dbc.spi.Connection |
| Truy cập phổ biến | JdbcTemplate, JDBC DAO, Spring Data JDBC/JPA | DatabaseClient, Spring Data R2DBC |
| Transaction manager | PlatformTransactionManager, ví dụ DataSourceTransactionManager | ReactiveTransactionManager, ví dụ R2dbcTransactionManager |
| Transaction context | Thường gắn với thread | Gắn với Reactor Context |
| Pool thường gặp | HikariCP | r2dbc-pool |
| Kiểu thực thi | Blocking | Non-blocking khi driver và pipeline hỗ trợ |

Không chuyển một JDBC Connection sang R2DBC Connection hoặc ngược lại. R2DBC SPI và JDBC API có lifecycle, giao thức và kiểu connection khác nhau.

## 2. Vì sao cùng database vẫn không có transaction chung?

Giả sử một request thực hiện hai thao tác:

1. Dùng JdbcTemplate cập nhật bảng account.
2. Dùng R2DBC Repository tạo một bản ghi audit.

Dù hai thao tác trỏ tới cùng PostgreSQL database, mỗi stack có thể lấy một connection riêng:

~~~text
JDBC transaction
  Connection J1
  UPDATE account ...
  COMMIT

R2DBC transaction
  Connection R1
  INSERT audit ...
  ROLLBACK
~~~

Nếu bước thứ hai thất bại sau khi bước thứ nhất đã commit, cập nhật account vẫn tồn tại. Không có transaction manager nào tự động rollback transaction JDBC chỉ vì transaction R2DBC thất bại.

Một database server có thể quản lý nhiều transaction đồng thời, nhưng database không tự suy ra rằng hai connection từ hai API thuộc cùng một đơn vị nghiệp vụ. Muốn phối hợp hai resource manager cần một cơ chế transaction phân tán được hỗ trợ rõ ràng; chỉ dùng chung URL database là chưa đủ.

### 2.1. Những gì không được chia sẻ

JDBC và R2DBC không tự chia sẻ:

- Connection.
- Transaction status.
- Savepoint.
- Rollback scope.
- Thread/Reactive Context.
- Connection pool.
- Timeout và isolation configuration.
- Các lock/visibility semantics của một transaction chưa commit.

Database vẫn có thể quan sát lock và dữ liệu đã commit theo isolation level. Nhưng transaction đang mở trên JDBC connection không trở thành transaction của R2DBC connection.

### 2.2. Cùng schema không đồng nghĩa cùng transaction

Ví dụ JDBC insert một hàng nhưng chưa commit. Một query R2DBC trên connection khác thường không nhìn thấy hàng chưa commit ở isolation phổ biến như READ COMMITTED. Tùy isolation và database, nó có thể chờ lock hoặc đọc snapshot khác, nhưng không tham gia transaction JDBC.

Nếu JDBC commit trước, R2DBC transaction bắt đầu sau đó có thể đọc dữ liệu đã commit. Đây là quan hệ thứ tự giữa hai transaction độc lập, không phải atomicity chung.

## 3. Cấu hình dependency và URL riêng

Một ứng dụng cần dependency cho cả hai stack. Ví dụ Gradle:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-jdbc")
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")

    runtimeOnly("org.postgresql:postgresql")
    runtimeOnly("org.postgresql:r2dbc-postgresql")

    // Nếu dùng migration qua Flyway:
    implementation("org.flywaydb:flyway-core")
}
~~~

Version nên được quản lý bởi Spring Boot dependency management/BOM. Không tự pin Spring Data, Spring Framework hoặc R2DBC SPI riêng nếu chưa xác nhận compatibility.

JDBC driver và R2DBC driver là hai driver khác nhau, dù cùng nhà cung cấp và cùng database engine.

### 3.1. Cấu hình application.yml

Ví dụ hai URL cùng trỏ tới một PostgreSQL database:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: app_user
    password: jdbc-secret-injected
    hikari:
      maximum-pool-size: 12
      connection-timeout: 3000

  r2dbc:
    url: r2dbc:postgresql://localhost:5432/orders
    username: app_user
    password: r2dbc-secret-injected
    pool:
      enabled: true
      initial-size: 2
      max-size: 8
      max-acquire-time: 3s
~~~

Các thuộc tính pool và tên property có thể khác theo Spring Boot version. Kiểm tra metadata cấu hình của release đang dùng. Nếu URL, username hoặc credential khác nhau, xác nhận cả hai stack thực sự kết nối đúng database/schema.

Không đưa password thật vào source control. Có thể dùng secret manager hoặc biến môi trường riêng cho từng kết nối.

### 3.2. Vì sao cần hai driver?

JDBC driver triển khai API java.sql và thường trả connection blocking. R2DBC driver triển khai SPI io.r2dbc.spi với API reactive.

Không thể dùng dependency JDBC để tạo R2DBC ConnectionFactory chỉ bằng cách thay URL prefix. Cũng không thể truyền URL r2dbc:postgresql: vào HikariCP.

### 3.3. Nếu hai stack trỏ tới hai database khác nhau

Cấu hình phải làm rõ database/schema của từng stack. Không dựa vào default schema hoặc search path giống nhau giữa hai connection. Mỗi pool có thể có session setting, timezone, role, search path và isolation khác nhau.

Nếu JDBC và R2DBC trỏ tới hai database khác nhau, vấn đề consistency càng rõ: hai local transaction không thể rollback lẫn nhau.

## 4. Khai báo hai transaction manager tường minh

Khi có nhiều transaction manager, hãy đặt tên rõ ràng để caller chọn đúng manager.

~~~java
@Configuration
public class PersistenceTransactionConfiguration {

    @Bean("jdbcTransactionManager")
    PlatformTransactionManager jdbcTransactionManager(
            DataSource dataSource) {

        return new DataSourceTransactionManager(dataSource);
    }

    @Bean("r2dbcTransactionManager")
    ReactiveTransactionManager r2dbcTransactionManager(
            ConnectionFactory connectionFactory) {

        return new R2dbcTransactionManager(connectionFactory);
    }

    @Bean("r2dbcTransactionalOperator")
    TransactionalOperator r2dbcTransactionalOperator(
            @Qualifier("r2dbcTransactionManager")
            ReactiveTransactionManager transactionManager) {

        return TransactionalOperator.create(transactionManager);
    }
}
~~~

Các import chính:

~~~java
import javax.sql.DataSource;
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.reactive.TransactionalOperator;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
~~~

Package javax.sql.DataSource thuộc Java SE. Các package Spring có thể thay đổi theo generation; dùng dependency Spring Framework/Spring Boot tương thích.

Spring Boot có thể auto-configure một hoặc cả hai transaction manager tùy classpath và bean hiện có. Nếu ứng dụng tự khai báo manager, kiểm tra điều kiện auto-configuration để không tạo hai bean cạnh tranh hoặc vô tình dùng sai DataSource/ConnectionFactory.

### 4.1. Dùng DataSourceTransactionManager cho JDBC

DataSourceTransactionManager quản lý transaction JDBC cho một DataSource. Trong Spring Framework mới hơn có thể có JdbcTransactionManager, cung cấp thêm một số xử lý exception JDBC; lựa chọn cụ thể phụ thuộc version.

Điều quan trọng là manager phải quản lý đúng DataSource mà JdbcTemplate/JDBC DAO đang dùng.

### 4.2. Dùng R2dbcTransactionManager cho R2DBC

R2dbcTransactionManager quản lý transaction cho một ConnectionFactory. Repository và DatabaseClient cần dùng cùng ConnectionFactory được quản lý để tham gia transaction.

Nếu có nhiều ConnectionFactory, cần tạo transaction manager tương ứng cho từng resource và xác định rõ repository nào dùng resource nào.

### 4.3. Tránh dựa vào manager mặc định khi có nhiều manager

Nếu context có nhiều transaction manager, việc phân giải mặc định có thể phụ thuộc bean name, type, qualifier hoặc @Primary. Đừng để hành vi mặc định quyết định transaction cho một thao tác quan trọng.

Đặt tên và qualifier tường minh giúp code review dễ nhận ra resource mà transaction bao phủ.

## 5. Gắn @Transactional đúng với từng stack

### 5.1. Method JDBC dùng JDBC transaction manager

~~~java
@Service
public class LegacyAccountService {

    private final JdbcTemplate jdbcTemplate;

    public LegacyAccountService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(transactionManager = "jdbcTransactionManager")
    public void updateBalance(Long accountId, BigDecimal amount) {
        jdbcTemplate.update(
                """
                UPDATE account
                SET balance = balance + ?
                WHERE id = ?
                """,
                amount,
                accountId);
    }
}
~~~

Transaction được mở bởi JDBC transaction manager. JdbcTemplate lấy connection theo cơ chế Spring và tham gia transaction hiện tại trên thread thực thi.

### 5.2. Method R2DBC trả về Publisher dùng reactive manager

~~~java
@Service
public class AuditService {

    private final AuditRepository repository;

    public AuditService(AuditRepository repository) {
        this.repository = repository;
    }

    @Transactional(transactionManager = "r2dbcTransactionManager")
    public Mono<AuditEntry> record(AuditEntry entry) {
        return repository.save(entry);
    }
}
~~~

Reactive transaction được gắn với lifecycle của publisher và được truyền qua Reactor Context. Method phải trả publisher để transaction manager bao trùm quá trình subscribe và terminal signal.

### 5.3. Không dùng nhầm JDBC manager cho method reactive

Một method trả Mono không nên được cấu hình với JDBC PlatformTransactionManager với kỳ vọng nó quản lý R2DBC query. JDBC manager không điều khiển R2DBC ConnectionFactory.

Tương tự, R2DBC transaction manager không tự quản lý JdbcTemplate. Hãy ghép kiểu return và transaction manager đúng loại.

### 5.4. Tách service theo resource

Một cách thiết kế dễ hiểu:

- LegacyAccountService: JDBC và jdbcTransactionManager.
- ReactiveAuditService: R2DBC và r2dbcTransactionManager.
- AccountWorkflowService: điều phối các bước, nhưng không giả định hai transaction local là atomic.

Tách service giúp transaction boundary rõ ràng và giảm nguy cơ một annotation ở cấp class vô tình áp dụng sai manager cho method thuộc stack khác.

### 5.5. Self-invocation và proxy

Spring thường áp dụng @Transactional qua proxy. Nếu một method trong cùng class gọi trực tiếp method transactional khác của chính instance, lời gọi nội bộ có thể không đi qua proxy nên transaction advice không được áp dụng như mong đợi.

Tách transaction boundary sang bean riêng hoặc dùng TransactionTemplate/TransactionalOperator tường minh khi cần điều khiển.

## 6. Thread-bound JDBC transaction và Reactor Context của R2DBC

Đây là khác biệt cốt lõi khi hai công nghệ cùng tồn tại.

### 6.1. JDBC transaction gắn với thread

JDBC transaction trong Spring thường dùng thread-bound resource. DataSourceTransactionManager gắn JDBC Connection với thread hiện tại. JdbcTemplate sử dụng cơ chế Spring để tìm connection đó.

Vì vậy:

- Các JDBC call trong cùng transaction cần chạy trong execution thread/context phù hợp.
- Tự chuyển JDBC work sang một thread khác có thể làm mất sự tham gia transaction.
- Không giữ JDBC Connection rồi sử dụng tùy tiện từ nhiều thread.
- Một transaction imperative không tự lan qua Reactor Context.

### 6.2. R2DBC transaction gắn với Reactor Context

Reactive transaction manager dùng Reactor Context để truyền transaction resource xuyên qua publisher chain.

Các repository/DatabaseClient tích hợp Spring có thể lấy connection đang thuộc transaction context. Việc chuyển scheduler trong Reactor chain không có cùng semantics với ThreadLocal JDBC transaction.

Không tự gọi subscribe() độc lập ở giữa pipeline vì subscription mới có thể không giữ context và transaction của chain ban đầu.

### 6.3. Hai context không tự bridge cho nhau

Micrometer Context Propagation hoặc Reactor context bridge không biến hai protocol thành cùng một transaction manager.

Context propagation có thể truyền metadata, trace hoặc một số ThreadLocal; nó không hợp nhất hai connection hoặc mở rộng transaction manager sang resource không được enlist.

## 7. JDBC blocking call trong ứng dụng WebFlux

Nếu một WebFlux request phải gọi JDBC trong giai đoạn chuyển tiếp, JDBC call cần được cô lập khỏi event-loop thread.

Ví dụ đọc bằng JdbcTemplate:

~~~java
public Mono<LegacyAccount> findLegacyAccount(Long id) {
    return Mono.fromCallable(() ->
                    jdbcTemplate.queryForObject(
                            """
                            SELECT id, account_name, balance
                            FROM account
                            WHERE id = ?
                            """,
                            accountRowMapper,
                            id))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

boundedElastic dành cho một số tác vụ blocking. Đây là adapter chuyển tiếp, không biến JDBC thành non-blocking.

Cần lưu ý:

- Giới hạn concurrency của các blocking call.
- Đặt query timeout và connection timeout.
- Theo dõi hàng đợi scheduler.
- Không gọi block() từ event-loop.
- Không dùng JDBC connection trên nhiều thread.
- Lập kế hoạch thay thế bằng R2DBC hoặc giữ riêng module imperative nếu phù hợp.

### 7.1. Transaction JDBC phải bao trọn phần blocking trên cùng thread

Nếu cần nhiều JDBC statement trong một transaction, dùng TransactionTemplate bên trong một blocking callable:

~~~java
public Mono<LegacyAccount> updateLegacyAccount(
        Long accountId,
        BigDecimal amount) {

    return Mono.fromCallable(() ->
                    jdbcTransactionTemplate.execute(status -> {
                        jdbcTemplate.update(
                                "UPDATE account SET balance = balance + ? WHERE id = ?",
                                amount,
                                accountId);

                        return jdbcTemplate.queryForObject(
                                "SELECT id, account_name, balance FROM account WHERE id = ?",
                                accountRowMapper,
                                accountId);
                    }))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

TransactionTemplate.execute mở, commit hoặc rollback transaction JDBC trước khi trả kết quả. Các JDBC call trong callback cùng tham gia transaction vì chúng chạy trong cùng callback/thread.

Không tạo Mono trong callback rồi trả ra để JDBC transaction kết thúc trước khi publisher thực thi. TransactionTemplate là imperative: callback phải hoàn tất công việc JDBC đồng bộ trong transaction scope.

### 7.2. Không bọc JDBC bằng fromCallable rồi cho rằng đã có transaction

Đoạn này chỉ offload blocking call:

~~~java
Mono.fromCallable(() -> jdbcTemplate.update(...))
        .subscribeOn(Schedulers.boundedElastic());
~~~

Nó không tự tạo transaction nếu không có transaction boundary. Nếu cần atomicity cho nhiều JDBC statement, dùng @Transactional trên một method imperative được gọi qua proxy, hoặc TransactionTemplate bên trong callable.

## 8. Kết hợp JDBC và R2DBC trong cùng workflow

Có thể cần điều phối hai bước trong một reactive service. Ví dụ cập nhật dữ liệu legacy qua JDBC rồi ghi dữ liệu mới qua R2DBC.

~~~java
public Mono<WorkflowResult> execute(Command command) {
    return Mono.fromCallable(() ->
                    jdbcTransactionTemplate.execute(status ->
                            legacyDao.update(command)))
            .subscribeOn(Schedulers.boundedElastic())
            .flatMap(jdbcResult ->
                    r2dbcTransactionalOperator.transactional(
                            reactiveRepository.save(
                                    toReactiveEntity(command, jdbcResult)))
                            .map(audit ->
                                    new WorkflowResult(
                                            jdbcResult.id(),
                                            audit.getId())));
}
~~~

Về transaction semantics:

1. JDBC transaction chạy trong boundedElastic thread.
2. TransactionTemplate.execute commit hoặc rollback trước khi phát kết quả JDBC.
3. Sau đó R2DBC transaction được mở cho publisher save.
4. Nếu R2DBC thất bại, JDBC transaction đã commit không tự rollback.

Đây là hai transaction độc lập được điều phối tuần tự.

### 8.1. Lỗi sau khi bước đầu đã commit

~~~text
JDBC transaction:
  UPDATE legacy_account
  COMMIT
            |
            v
R2DBC transaction:
  INSERT new_audit
  ERROR
  ROLLBACK
~~~

Trạng thái cuối cùng là account đã cập nhật nhưng audit chưa được ghi. Đây là partial completion cần được thiết kế và xử lý như một trường hợp nghiệp vụ thực tế.

Không mô tả workflow này là atomic chỉ vì hai bước nằm trong cùng một method Java hoặc cùng một reactive chain.

### 8.2. Không giữ R2DBC transaction mở trong lúc chờ JDBC lâu

Có thể viết một publisher bọc toàn bộ workflow trong R2DBC TransactionalOperator rồi gọi JDBC ở giữa. Khi đó R2DBC connection/transaction có thể bị giữ trong khi blocking JDBC call chạy, nhưng JDBC vẫn không tham gia transaction đó.

Điều này làm transaction R2DBC dài hơn, tăng thời gian giữ connection và không tạo atomicity. Chỉ bao phần R2DBC cần transaction bằng reactive manager; bao phần JDBC bằng JDBC manager.

### 8.3. Nếu thứ tự cần đảo lại

Nếu R2DBC commit trước rồi JDBC thất bại, trạng thái ngược lại xảy ra: dữ liệu reactive đã commit, dữ liệu legacy chưa cập nhật.

Đổi thứ tự không giải quyết bài toán consistency. Cần idempotency, outbox, retry/reconciliation hoặc compensation.

## 9. Có thể dùng một @Transactional cho cả JDBC và R2DBC không?

Không thể đạt atomic transaction giữa hai resource chỉ bằng một annotation @Transactional.

Một transaction manager quản lý một loại resource mà nó biết cách điều khiển. DataSourceTransactionManager quản lý JDBC DataSource; R2dbcTransactionManager quản lý R2DBC ConnectionFactory.

Ví dụ sau không tạo một transaction chung:

~~~java
@Transactional(transactionManager = "jdbcTransactionManager")
public Mono<Result> doBoth() {
    // JDBC operation
    // R2DBC repository operation
    return reactiveRepository.save(...).map(...);
}
~~~

JDBC manager không điều khiển reactive connection. Tùy cách interception và return type, cấu hình manager không tương thích có thể không hoạt động hoặc transaction scope không bao trùm reactive subscription. Không dùng kiểu kết hợp này.

Cũng không nên đặt một @Transactional cấp class rồi mong Spring tự chọn manager khác nhau cho từng statement bên trong method. Hãy xác định manager theo method/service và chia ranh giới.

## 10. Multiple transaction managers và @Primary

Khi có nhiều bean manager, Spring cần phân giải manager cho annotation hoặc API transaction.

Một số nguyên tắc:

- Đặt bean name có ý nghĩa như jdbcTransactionManager và r2dbcTransactionManager.
- Dùng @Transactional(transactionManager = "...") cho method cần transaction declarative.
- Dùng @Qualifier khi inject manager hoặc operator.
- Chỉ dùng @Primary nếu thật sự có một manager mặc định phù hợp cho đa số imperative/reactive call site.
- Không xem @Primary là cơ chế tự phân biệt JDBC và R2DBC theo từng câu query.
- Kiểm tra bean manager thực tế trong application context.

Nếu một class có cả JDBC và R2DBC method, tách thành hai service thường rõ ràng hơn annotation mặc định ở class level.

### 10.1. Dùng TransactionTemplate cho JDBC

~~~java
@Bean
TransactionTemplate jdbcTransactionTemplate(
        @Qualifier("jdbcTransactionManager")
        PlatformTransactionManager transactionManager) {

    return new TransactionTemplate(transactionManager);
}
~~~

TransactionTemplate giúp thể hiện transaction boundary imperative ngay tại nơi gọi, đặc biệt hữu ích khi bọc blocking work trong Mono.fromCallable.

### 10.2. Dùng TransactionalOperator cho R2DBC

~~~java
@Bean
TransactionalOperator r2dbcTransactionalOperator(
        @Qualifier("r2dbcTransactionManager")
        ReactiveTransactionManager transactionManager) {

    return TransactionalOperator.create(transactionManager);
}
~~~

TransactionalOperator bọc publisher. Khi publisher hoàn tất thành công, transaction commit; khi lỗi hoặc cancellation được xử lý theo transaction semantics, transaction manager thực hiện cleanup/rollback phù hợp.

## 11. Propagation và isolation không đi xuyên resource manager

Các thuộc tính như REQUIRED, REQUIRES_NEW, SUPPORTS, MANDATORY, isolation và timeout được áp dụng trong phạm vi transaction manager/resource tương ứng.

Ví dụ:

- REQUIRES_NEW trên JDBC manager tạo transaction JDBC mới.
- REQUIRES_NEW trên R2DBC manager tạo transaction R2DBC mới.
- Một JDBC REQUIRES_NEW không tạm dừng hoặc enlist R2DBC transaction như cùng một resource.
- Isolation của JDBC transaction không tự đặt isolation cho R2DBC connection.

Nếu cần cùng một business operation qua hai resource, phải thiết kế orchestration/consistency riêng.

### 11.1. Isolation khác nhau giữa hai connection

Có thể JDBC transaction dùng READ COMMITTED, còn R2DBC transaction dùng REPEATABLE READ. Kết quả đọc có thể khác nhau theo thời điểm và snapshot.

Đặt isolation rõ ràng cho từng transaction manager khi nghiệp vụ cần. Kiểm tra database hỗ trợ isolation nào và semantics thực tế của driver.

### 11.2. Không giữ transaction lâu khi gọi hệ thống ngoài

Một transaction JDBC hoặc R2DBC không nên mở trong lúc chờ HTTP service, message broker hoặc thao tác file lâu. Điều này giữ connection và lock trong thời gian không cần thiết.

Hãy chia thành các bước transaction ngắn và dùng outbox/saga khi cần phối hợp.

## 12. Vì sao không dùng ChainedTransactionManager để có atomicity?

Trong một số codebase Spring Data cũ có thể gặp ChainedTransactionManager, vốn phối hợp nhiều transaction manager theo kiểu best-effort. Nó không tương đương một distributed transaction coordinator có prepare/commit hai pha.

Nếu một manager commit thành công rồi manager tiếp theo thất bại, hệ thống có thể ở trạng thái partial commit. Rollback bù không thể đảm bảo đảo ngược một commit đã xảy ra trong mọi tình huống.

ChainedTransactionManager đã bị deprecated trong các generation Spring Data liên quan và không nên là nền tảng cho thiết kế atomic cross-resource mới.

Không đặt tên một chuỗi transaction manager là global transaction rồi cho rằng hai database resource được commit nguyên tử.

## 13. XA và distributed transaction

JDBC có thể hỗ trợ XA thông qua XADataSource và resource manager phù hợp. Spring có thể tích hợp JTA transaction manager với các resource XA-capable.

Tuy nhiên, R2DBC SPI tiêu chuẩn không cung cấp một cơ chế XA tương đương phổ quát để enlist R2DBC ConnectionFactory vào một distributed two-phase commit transaction. Khả năng cụ thể phải được xác minh với driver và transaction coordinator, không suy luận từ việc database có hỗ trợ XA ở JDBC.

Nếu cả hai resource thực sự hỗ trợ XA và hạ tầng vận hành có transaction coordinator, 2PC có thể là một lựa chọn nhưng đi kèm chi phí, lock, recovery log và vận hành phức tạp.

Với JDBC + R2DBC thông thường, hãy mặc định chúng là hai local transaction độc lập cho tới khi có bằng chứng triển khai cụ thể chứng minh khả năng enlist chung.

## 14. Transactional Outbox để đồng bộ hai đường persistence

Nếu một nghiệp vụ cần cập nhật database chính và thông báo cho một hệ thống/đường persistence khác, Transactional Outbox thường phù hợp hơn việc cố tạo transaction chung.

Ví dụ database chính được cập nhật bằng R2DBC:

~~~text
R2DBC transaction
  UPDATE business_record
  INSERT outbox_event
  COMMIT
        |
        v
Outbox relay / CDC
        |
        v
Event broker
        |
        v
JDBC consumer
  BEGIN JDBC transaction
  UPDATE legacy_store
  INSERT processed_event_id
  COMMIT
~~~

Business record và outbox event nằm trong cùng một R2DBC transaction. Nếu transaction rollback, cả hai rollback. Nếu commit, relay có thể gửi event sau đó.

Consumer JDBC xử lý event trong transaction JDBC của nó. Ghi processed event ID cùng business update giúp consumer idempotent.

Nếu dữ liệu chính được ghi bằng JDBC, có thể ghi outbox trong cùng JDBC transaction rồi relay bằng một worker khác.

### 14.1. Outbox không phải exactly-once tự động

Relay có thể gửi lại event nếu process crash sau khi publish nhưng trước khi đánh dấu sent. Consumer cần idempotency/deduplication.

Thiết kế cần có:

- Event ID ổn định.
- Unique constraint cho processed event.
- Retry có giới hạn và dead-letter policy.
- Thứ tự event nếu aggregate yêu cầu.
- Cleanup/retention cho outbox.
- Metrics cho backlog và publish failures.

Outbox cung cấp atomicity giữa business write và outbox record trong một resource transaction. Việc truyền sang resource khác là eventual consistency.

## 15. Saga và compensation

Nếu workflow có nhiều bước trên nhiều resource, có thể mô hình hóa thành saga:

~~~text
Bước 1: JDBC reserve legacy resource
       |
       v
Bước 2: R2DBC create new record
       |
       v
Bước 3: Publish confirmation
       |
       +---- lỗi?
               |
               v
       Compensation cho bước đã hoàn tất
~~~

Compensation là một thao tác nghiệp vụ mới để đảo/điều chỉnh trạng thái đã commit, không phải rollback transaction cũ.

Ví dụ:

- JDBC đã reserve inventory.
- R2DBC tạo order thất bại.
- Saga gọi JDBC release reservation.
- Nếu compensation cũng thất bại, lưu trạng thái cần retry/reconciliation.

Không phải thao tác nào cũng có compensation hoàn hảo. Gửi email hoặc phát thông báo đã được người dùng nhận không thể undo như rollback SQL.

Saga cần state machine bền vững, idempotency, retry, timeout, audit và cách xử lý compensation thất bại.

## 16. Chọn một công nghệ làm transaction owner cho mỗi use case

Một cách đơn giản hóa kiến trúc là chọn một persistence technology làm owner của transaction cho từng use case.

| Use case | Transaction owner | Resource |
|---|---|---|
| API tạo order reactive | R2DBC | ConnectionFactory |
| Batch legacy cập nhật account | JDBC | DataSource |
| Flyway migration | JDBC | DataSource |
| Ghi outbox cùng order | R2DBC nếu order dùng R2DBC | Cùng R2DBC transaction |
| Đồng bộ legacy store | JDBC consumer transaction | DataSource |

Nếu một use case cần cập nhật hai resource, hãy coi đó là workflow nhiều bước với consistency policy riêng, thay vì cố nhồi vào một transaction local.

Trong một số hệ thống, chuyển toàn bộ use case sang JDBC hoặc toàn bộ sang R2DBC sẽ giảm đáng kể độ phức tạp. Giữ hai công nghệ là quyết định có chi phí vận hành và cần lý do cụ thể.

## 17. Flyway/Liquibase dùng JDBC trong ứng dụng R2DBC

Một trường hợp coexistence phổ biến là runtime dùng R2DBC nhưng schema migration dùng JDBC.

Lý do: Flyway/Liquibase có tích hợp JDBC phổ biến và migration thường chạy lúc khởi động/deploy, không nằm trong request reactive path.

Ví dụ cấu hình datasource JDBC cho migration và R2DBC cho runtime:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: migration_user
    password: migration-secret-injected

  r2dbc:
    url: r2dbc:postgresql://localhost:5432/orders
    username: app_user
    password: r2dbc-secret-injected
~~~

Có thể dùng credential migration có quyền DDL cao hơn và credential runtime chỉ có quyền DML cần thiết. Không dùng tài khoản migration quyền cao cho request path nếu không cần.

### 17.1. Migration là transaction JDBC riêng

Flyway/Liquibase chạy migration qua DataSource/connection do chúng quản lý. Sau migration, R2DBC application kết nối vào schema đã được cập nhật.

Migration không tự tham gia reactive transaction của R2DBC. Thông thường đây là điều mong muốn: schema change hoàn tất trước khi ứng dụng nhận traffic.

### 17.2. Nếu chỉ cấu hình spring.r2dbc.url

Một số công cụ migration cần JDBC URL và JDBC driver. Nếu chỉ có R2DBC URL, migration tool có thể không biết cách kết nối.

Cấu hình JDBC riêng hoặc cấu hình Flyway/Liquibase tường minh theo version của Spring Boot và migration tool. Kiểm tra startup logs để xác nhận migration chạy đúng database/schema.

### 17.3. Thứ tự deploy và schema compatibility

Khi rolling deploy có nhiều version ứng dụng, migration nên tuân theo chiến lược expand-and-contract:

1. Thêm column/table tương thích với code cũ.
2. Deploy code mới có thể đọc cả schema cũ/mới nếu cần.
3. Backfill dữ liệu.
4. Chuyển traffic/behavior.
5. Xóa schema cũ ở release sau khi không còn consumer.

Không chạy migration destructive trước khi tất cả instance và worker cũ đã ngừng sử dụng column/table đó.

## 18. Quản lý vòng đời connection riêng

### 18.1. JDBC với JdbcTemplate

JdbcTemplate quản lý việc lấy và giải phóng connection theo transaction context. Ưu tiên dùng JdbcTemplate thay vì tự gọi dataSource.getConnection().

Nếu cần JDBC API thấp hơn, dùng DataSourceUtils hoặc cơ chế Spring transaction-aware phù hợp. Không đóng connection đang thuộc transaction bằng tay.

### 18.2. R2DBC với Repository/DatabaseClient

Spring Data R2DBC Repository và DatabaseClient tích hợp với connection management của Spring. Nếu dùng raw R2DBC SPI, cần quản lý connection lifecycle bằng cơ chế reactive như usingWhen và đảm bảo release cả success/error/cancel.

Không gọi ConnectionFactory.create() rồi quên close/release. Connection leak ở R2DBC có thể làm pool pending tăng dần.

### 18.3. Không chia sẻ connection giữa request

JDBC Connection và R2DBC Connection không phải object thread-safe dùng chung cho nhiều request. Connection pool cấp connection theo lifecycle transaction/operation.

Không lưu connection trong singleton field hoặc cache. Không truyền connection qua message hoặc scheduler khác.

## 19. Tính ngân sách connection cho cả hai pool

Khi dùng hai stack, tổng connection có thể lớn gần gấp đôi so với chỉ một pool.

Ví dụ:

- Mỗi instance JDBC Hikari max 12.
- Mỗi instance R2DBC pool max 8.
- Có 3 instance.

Tổng khả năng cấp connection:

\[
3 \times (12 + 8) = 60
\]

Chưa tính migration, admin console, monitoring, batch worker khác và connection của ứng dụng khác.

Một ngân sách tổng thể:

\[
C_{\text{total}}
=
N_{\text{replicas}}
\times
(C_{\text{JDBC}} + C_{\text{R2DBC}})
+
C_{\text{other}}
\]

So sánh với giới hạn session của database. Nếu cả hai pool cùng dùng một database server, chúng cùng tiêu thụ ngân sách connection đó.

### 19.1. Timeout riêng

JDBC có connection timeout, validation timeout, query timeout và socket timeout tùy pool/driver. R2DBC pool có acquire/create/idle lifetime và driver-specific timeout.

Không giả định timeout của một pool tự áp dụng cho pool kia. Cấu hình và theo dõi riêng.

### 19.2. Pool exhaustion có thể xảy ra độc lập

Có thể JDBC pool còn connection trong khi R2DBC pool pending, hoặc ngược lại. Một request có thể thành công ở một stack nhưng timeout ở stack còn lại.

Dashboard cần tách metrics theo pool/resource, không gộp tất cả thành một con số database connections không phân biệt.

## 20. Không tạo deadlock bằng cách chờ chéo hai pool

Một workflow có thể giữ JDBC connection rồi chờ R2DBC operation, trong khi workflow khác giữ R2DBC connection rồi chờ JDBC operation. Nếu cả hai pool nhỏ và transaction giữ connection lâu, có thể tạo tình trạng chờ dây chuyền hoặc deadlock ở cấp ứng dụng.

Giảm rủi ro:

- Tránh giữ transaction mở trong khi gọi resource khác.
- Chọn thứ tự truy cập thống nhất nếu workflow buộc phải gọi hai resource.
- Không chạy JDBC blocking trên event-loop.
- Đặt timeout cho acquire/query.
- Giữ transaction scope ngắn.
- Giới hạn concurrency.
- Dùng outbox/saga để tách bước khi phù hợp.

Một transaction local nên chỉ giữ resource cần thiết cho phần công việc của nó.

## 21. Read-after-write và visibility giữa hai stack

Nếu JDBC commit xong rồi R2DBC query cùng bảng, R2DBC thường nhìn thấy dữ liệu đã commit theo isolation level của transaction mới.

Nhưng các trường hợp sau cần cẩn trọng:

- JDBC write chưa commit.
- R2DBC transaction đã mở snapshot trước khi JDBC commit.
- Hai transaction dùng isolation khác nhau.
- Read replica có replication lag.
- Hai URL trỏ tới database/schema khác nhau.
- Connection session có search path/timezone/role khác nhau.

Không dùng việc cùng database làm bằng chứng consistency tức thời. Xác định rõ commit order, isolation, primary/replica routing và retry behavior.

## 22. Kiểm thử hai transaction manager

Unit test mock JdbcTemplate và repository không chứng minh hai transaction thực sự tách biệt hoặc rollback đúng. Cần integration test với database engine mục tiêu.

Có thể dùng Testcontainers PostgreSQL và tạo cả JDBC DataSource lẫn R2DBC ConnectionFactory trỏ tới cùng container.

### 22.1. Test JDBC rollback

Thực hiện hai JDBC statement trong TransactionTemplate, cố tình ném exception giữa chừng, sau đó đọc bằng JDBC hoặc R2DBC connection mới để xác nhận không có thay đổi được commit.

### 22.2. Test R2DBC rollback

Bọc hai thao tác R2DBC trong TransactionalOperator, làm thao tác thứ hai lỗi, sau đó đọc bằng connection mới để xác nhận thao tác đầu cũng rollback.

### 22.3. Test partial commit giữa hai stack

Kịch bản:

1. JDBC transaction cập nhật bảng legacy và commit.
2. R2DBC transaction insert audit rồi phát lỗi.
3. Đọc bằng cả hai API.
4. Xác nhận JDBC update vẫn tồn tại, audit không tồn tại.

Test này chứng minh hai local transaction không atomic với nhau.

### 22.4. Test blocking call trong WebFlux

Dùng integration test có request thật hoặc instrumentation để xác nhận JDBC call được offload khỏi event-loop. Kiểm tra concurrency và timeout khi JDBC pool bão hòa.

Không chỉ kiểm tra response 200; cần xác nhận thread/execution boundary và transaction behavior.

### 22.5. Tránh test @Transactional gây hiểu nhầm

Một test JUnit được bọc trong JDBC @Transactional không tự động bao trùm request HTTP chạy trên server thread khác hoặc publisher được subscribe ở context khác.

Tương tự, test reactive transaction cần subscribe publisher và xác nhận kết quả sau terminal signal. Không giả định transaction của test thread bao phủ mọi reactive operation.

## 23. Ma trận chọn công cụ

| Tình huống | Cách làm |
|---|---|
| Toàn bộ use case dùng JDBC | @Transactional với JDBC manager hoặc TransactionTemplate |
| Toàn bộ use case dùng R2DBC | @Transactional reactive hoặc TransactionalOperator |
| WebFlux gọi JDBC legacy | Cô lập blocking call trên boundedElastic, transaction JDBC nằm trong callback/thread đó |
| JDBC rồi R2DBC trong một workflow | Hai transaction riêng, có consistency policy |
| Cần business write và event cùng atomicity | Outbox trong cùng một transaction manager/resource |
| Cần cập nhật hai database độc lập | Saga, outbox, idempotency và reconciliation |
| Migration cho ứng dụng R2DBC | Flyway/Liquibase qua JDBC DataSource nếu tool dùng JDBC |
| Muốn rollback JDBC khi R2DBC lỗi | Không thể bằng local transaction manager thông thường; cần distributed transaction được hỗ trợ hoặc thiết kế compensation |

## 24. Những lỗi thường gặp khi JDBC và R2DBC cùng tồn tại

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ cùng database nghĩa là cùng transaction | Một stack commit trong khi stack kia rollback | Xem mỗi connection/resource là transaction riêng |
| Dùng JDBC manager cho R2DBC repository | R2DBC operation không được JDBC manager quản lý | Dùng R2dbcTransactionManager |
| Dùng R2DBC manager cho JdbcTemplate | JDBC call không tham gia reactive transaction | Dùng PlatformTransactionManager cho DataSource |
| Dựa vào @Transactional mặc định khi có nhiều manager | Method có thể chọn sai manager | Chỉ định transactionManager/qualifier |
| Đặt @Transactional cấp class cho hai loại method | Boundary không rõ và dễ cấu hình sai | Tách service theo resource |
| Gọi JDBC trên event-loop | Chặn request và làm giảm throughput | Offload boundedElastic hoặc giữ imperative boundary |
| Bọc JDBC trong fromCallable mà không có tx | Nhiều statement có thể commit riêng | Dùng TransactionTemplate/manager JDBC |
| Để JDBC transaction mở qua scheduler hop | Thread-bound connection không còn đúng context | Giữ toàn bộ JDBC callback trong một thread |
| Giữ R2DBC transaction khi chờ JDBC lâu | Giữ connection nhưng không có atomicity | Tách transaction scope |
| Gọi subscribe() độc lập | Mất lifecycle, lỗi và Reactor Context | Nối publisher và để framework quản lý |
| Dùng một pool size cho cả hai stack | Tổng connection vượt giới hạn DB | Tính riêng từng pool và tổng replica |
| Dùng ChainedTransactionManager như 2PC | Có thể partial commit | Outbox/saga hoặc XA thật sự được hỗ trợ |
| Nghĩ Flyway tự dùng R2DBC URL | Migration không kết nối được | Cấu hình JDBC DataSource/driver |
| Test chỉ bằng H2 hoặc mock | Bỏ sót khác biệt transaction/driver | Test với database engine mục tiêu |
| Nghĩ rollback test thread bao trùm HTTP request | Dữ liệu test bị commit ngoài dự kiến | Test transaction theo đúng execution context |
| Dùng hai credential/session config không đồng nhất | Khác schema, role hoặc timezone | Kiểm tra config của cả hai pool |

## 25. Quy trình chuyển đổi an toàn khi giữ cả JDBC và R2DBC

Một lộ trình thực tế:

1. Liệt kê các module và call site đang dùng JDBC.
2. Liệt kê repository, DatabaseClient và ConnectionFactory dùng R2DBC.
3. Xác định database/schema và credential của từng resource.
4. Cấu hình DataSource/JDBC driver và ConnectionFactory/R2DBC driver riêng.
5. Khai báo transaction manager riêng, có tên/qualifier rõ ràng.
6. Gắn từng service method với đúng transaction manager.
7. Giữ JDBC blocking call ngoài event-loop và bao transaction trong cùng callback/thread.
8. Không giả định một method orchestration tạo atomicity giữa hai manager.
9. Chọn outbox, saga, idempotency hoặc compensation cho consistency liên resource.
10. Chạy migration qua JDBC nếu công cụ yêu cầu, trước khi runtime nhận traffic.
11. Tính tổng connection budget của hai pool trên tất cả replica.
12. Thêm metrics/health cho từng pool và transaction path.
13. Test rollback JDBC, rollback R2DBC và partial commit giữa hai stack.
14. Chuyển từng use case sang một transaction owner rõ ràng khi có thể.
15. Xóa adapter blocking khi không còn caller legacy và xác nhận không còn block()/JDBC trên reactive path.

## 26. Ví dụ tổng hợp: workflow điều phối hai resource

Giả sử một ứng dụng có:

- Legacy account store dùng JDBC.
- Audit store mới dùng R2DBC.
- Mỗi bước có transaction local.
- Nếu audit thất bại, job cần retry hoặc reconciliation.

Một orchestration đơn giản:

~~~java
@Service
public class AccountWorkflowService {

    private final TransactionTemplate jdbcTransactionTemplate;
    private final LegacyAccountDao legacyDao;
    private final AuditRepository auditRepository;
    private final TransactionalOperator r2dbcTx;

    public AccountWorkflowService(
            TransactionTemplate jdbcTransactionTemplate,
            LegacyAccountDao legacyDao,
            AuditRepository auditRepository,
            TransactionalOperator r2dbcTx) {
        this.jdbcTransactionTemplate = jdbcTransactionTemplate;
        this.legacyDao = legacyDao;
        this.auditRepository = auditRepository;
        this.r2dbcTx = r2dbcTx;
    }

    public Mono<WorkflowResult> updateAccount(
            UpdateAccountCommand command) {

        return Mono.fromCallable(() ->
                        jdbcTransactionTemplate.execute(status ->
                                legacyDao.update(command)))
                .subscribeOn(Schedulers.boundedElastic())
                .flatMap(legacyResult ->
                        r2dbcTx.transactional(
                                auditRepository.save(
                                        AuditEntry.from(
                                                command,
                                                legacyResult)))
                        .map(audit ->
                                WorkflowResult.completed(
                                        legacyResult.id(),
                                        audit.getId())));
    }
}
~~~

Đoạn trên minh họa thứ tự commit: JDBC transaction hoàn tất trước, sau đó R2DBC transaction mới chạy. Nếu audit lỗi, account update đã commit.

Để đạt consistency tốt hơn, có thể thay bước ghi audit R2DBC trực tiếp bằng outbox trong cùng JDBC transaction với account update. Một relay sẽ phát event, và consumer R2DBC ghi audit idempotently. Khi đó account update và outbox event atomic trong JDBC; audit được cập nhật eventual sau khi event được xử lý.

~~~text
JDBC transaction
  UPDATE legacy_account
  INSERT outbox_event
  COMMIT
        |
        v
Outbox relay
        |
        v
Event
        |
        v
R2DBC transaction
  INSERT audit
  INSERT processed_event
  COMMIT
~~~

Consumer cần unique key trên event ID để xử lý event gửi lại. Nếu R2DBC ghi audit thành công nhưng acknowledgment bị mất, event có thể được phát lại; unique constraint/deduplication bảo vệ khỏi duplicate.

## 27. Nguyên tắc thiết kế cần nhớ

- DataSource/JDBC và ConnectionFactory/R2DBC là hai resource riêng.
- JDBC Connection và R2DBC Connection không thể thay thế hoặc dùng chung.
- JDBC transaction thường thread-bound; R2DBC transaction đi qua Reactor Context.
- PlatformTransactionManager quản lý JDBC; ReactiveTransactionManager quản lý R2DBC.
- Dùng DataSourceTransactionManager/JdbcTransactionManager và R2dbcTransactionManager đúng resource.
- Đặt tên transaction manager và chỉ định qualifier rõ ràng khi có nhiều manager.
- TransactionTemplate dành cho transaction imperative; TransactionalOperator dành cho publisher reactive.
- Không gọi JDBC blocking trên WebFlux event-loop; cô lập trên scheduler phù hợp trong giai đoạn chuyển tiếp.
- Bọc toàn bộ JDBC work trong cùng transaction callback/thread.
- Một workflow Java gọi hai stack không có nghĩa hai transaction atomic.
- Nếu một transaction đã commit, lỗi ở transaction còn lại không rollback commit trước.
- REQUIRES_NEW, isolation và savepoint chỉ có hiệu lực trong resource manager tương ứng.
- Không dựa vào ChainedTransactionManager như một distributed two-phase commit.
- XA chỉ khả thi khi mọi resource thực sự hỗ trợ enlistment và có transaction coordinator; R2DBC SPI tiêu chuẩn không cung cấp XA phổ quát.
- Dùng outbox, saga, idempotency và reconciliation cho consistency giữa resource.
- Flyway/Liquibase có thể dùng JDBC DataSource trong ứng dụng runtime R2DBC.
- Tính tổng connection của HikariCP và r2dbc-pool qua tất cả replica.
- Kiểm thử rollback và partial commit bằng đúng database engine/driver.
- Chuyển từng use case sang một transaction owner rõ ràng để giảm độ phức tạp.

