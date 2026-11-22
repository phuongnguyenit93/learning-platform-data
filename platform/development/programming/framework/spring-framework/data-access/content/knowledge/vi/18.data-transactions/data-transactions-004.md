# Chọn cùng DataSource và bộ quản lý cho các thao tác cần phối hợp

Một nghiệp vụ có thể cần nhiều thao tác dữ liệu cùng thành công: tạo đơn hàng, trừ tồn kho, ghi lịch sử hoặc ghi bản tin outbox. Khi dùng Spring JDBC, **muốn các thao tác ấy cùng commit hoặc cùng rollback trong một giao dịch JDBC cục bộ, chúng phải tham gia đúng cùng tài nguyên giao dịch**: `DataSource` được bộ quản lý transaction điều khiển, cách lấy kết nối có nhận biết transaction và phạm vi gọi thực sự được Spring quản lý.

**Cùng JDBC URL, cùng database hoặc cùng bảng chưa đủ để bảo đảm cùng transaction.** Hai đối tượng `DataSource` được tạo độc lập có thể mở hai `Connection` khác nhau và commit tách biệt. Tương tự, hai repository dùng cùng `DataSource` nhưng chạy ở hai luồng hoặc ở hai transaction riêng vẫn có thể không thuộc cùng một đơn vị commit.

Bài này tập trung vào cách **chọn và nối đúng `DataSource` với transaction manager cho các thao tác cần phối hợp**, cách kiểm chứng hành vi thực tế trong Spring JDBC, các cấu hình dễ làm hỏng tính nguyên tử và ranh giới với JPA, nhiều database và hệ thống ngoài.

## 1. Xác định “phối hợp” nghĩa là gì

Giả sử ứng dụng có ba bước:

1. Ghi `purchase_order` trạng thái `PENDING`.
2. Giảm `inventory.available` sau khi kiểm tra đủ số lượng.
3. Ghi `order_outbox` để sau commit có thể gửi một sự kiện.

Nếu cả ba cùng nằm trong **một transaction trên một cơ sở dữ liệu hỗ trợ giao dịch**, lỗi tại bước 2 hoặc 3 phải khiến dữ liệu của cả ba bước được rollback. Nếu commit thành công, các thay đổi DB trong transaction đó cùng được chấp nhận. Đây là **atomicity của đơn vị thao tác DB**, không phải bảo đảm rằng hệ thống nhận sự kiện hay cổng thanh toán bên ngoài đã xử lý xong.

Khi thiết kế, cần trả lời ba câu hỏi:

- **Ranh giới nghiệp vụ:** Những thay đổi nào bắt buộc commit/rollback cùng nhau? Bước nào chỉ cần retry hoặc đối soát riêng?
- **Ranh giới tài nguyên:** Chúng dùng một database/transactional resource, hay thực tế dùng nhiều database, connection factory, message broker?
- **Ranh giới thực thi:** Chúng có chạy qua cùng Spring-managed transaction, đúng manager, đúng context/luồng hay không?

Trong phạm vi **JDBC cục bộ một tài nguyên**, giải pháp phổ biến là một `DataSource` thống nhất, `JdbcTemplate`/`NamedParameterJdbcTemplate` sử dụng nó, và một `JdbcTransactionManager` hoặc `DataSourceTransactionManager` quản lý **chính `DataSource` đó**.

## 2. Phân biệt ba thành phần và trách nhiệm

| Thành phần | Vai trò | Điều quan trọng |
| --- | --- | --- |
| `DataSource` (`javax.sql.DataSource`) | Nhà máy cung cấp JDBC `Connection` | Là tài nguyên mà transaction manager và JDBC data access phải dùng nhất quán |
| `PlatformTransactionManager` | Bắt đầu, commit, rollback và định nghĩa phạm vi transaction | Phải chọn implementation gắn với loại tài nguyên thực tế |
| `JdbcTemplate` / `NamedParameterJdbcTemplate` | Thực hiện SQL, quản lý statement/result, chuyển lỗi JDBC | Sử dụng `DataSourceUtils` để lấy connection đang gắn với Spring transaction |
| `DataSourceUtils` | Lấy/giải phóng connection có nhận biết transaction của Spring | Không tự mở connection trực tiếp bằng `dataSource.getConnection()` trong DAO muốn tham gia Spring transaction |
| `TransactionSynchronizationManager` | Quản lý resource/synchronization gắn với thread trong imperative transaction | Được framework dùng nội bộ; không nên tự bind/unbind resource thủ công trong ứng dụng thông thường |

`DataSourceTransactionManager` điều khiển một JDBC `Connection` thuộc `DataSource` đã chọn. `JdbcTransactionManager` kế thừa cách quản lý đó và bổ sung dịch lỗi JDBC khi commit/rollback sang họ `DataAccessException` khi thích hợp. Cả hai phục vụ trường hợp **JDBC một tài nguyên**; không tự phối hợp commit nguyên tử giữa hai hệ quản trị database độc lập.

Với Spring JDBC, một lời gọi `JdbcTemplate.update(...)` bên trong transaction lấy connection thông qua `DataSourceUtils.getConnection(dataSource)`. Nếu tài nguyên phù hợp đang được Spring gắn với thread, JDBC tham gia đúng connection đó. Khi không có transaction đang quản lý kết nối, thông thường mỗi thao tác sẽ lấy connection và chịu quy tắc auto-commit của connection/driver/pool.

### Cùng DataSource không đồng nghĩa cùng một physical Connection mãi mãi

Một `DataSource` là **nhà máy connection**; bên ngoài transaction nó có thể trả các connection khác nhau theo từng lời gọi. Điều cần thiết là **trong cùng phạm vi transaction**, các thao tác tham gia connection đã được manager gắn với tài nguyên. Spring quản lý việc lấy/trả connection, nên không nên giữ một `Connection` ở field của singleton repository để dùng qua nhiều request.

```text
                 Spring-managed service transaction
                              │
                              ▼
                 JdbcTransactionManager(ds)
                              │
                  thread-bound Connection
                      qua DataSourceUtils
                       ┌──────┴──────┐
                       ▼             ▼
                 JdbcTemplate A   JdbcTemplate B
                     (ds)            (ds)
                       │             │
                       └──────┬──────┘
                              ▼
                     cùng JDBC transaction
                       commit / rollback
```

Nếu `JdbcTemplate B` lại dùng `anotherDataSource`, nó có thể mở connection mới không được manager trên điều khiển, dù cả hai datasource dùng **cùng username, URL và database**.

## 3. Ví dụ Java 17+ độc lập: rollback toàn bộ và lỗi phối hợp

Ví dụ dùng **Spring JDBC + H2 in-memory** để nhìn được kết quả từ kết nối khác sau mỗi transaction. Không cần Spring Boot hoặc annotation `@Transactional` trong demo, vì `TransactionTemplate` làm ranh giới transaction tường minh. Cách hoạt động của JDBC transaction và `DataSource` cũng là nền tảng của `@Transactional` khi dùng đúng manager.

### 3.1. Cấu hình Gradle

Tạo file `settings.gradle`:

```groovy
rootProject.name = 'jdbc-coordinated-transaction-demo'
```

Tạo file `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'CoordinatedTransactionDemo'
}
```

Dùng JDK 17+ và Gradle tương thích. `spring-jdbc` kéo theo các thành phần transaction cần thiết qua dependency tương ứng. H2 chỉ dùng lúc chạy, bởi mã Java không import lớp H2 trực tiếp.

### 3.2. Chương trình chạy đầy đủ

Tạo file `src/main/java/CoordinatedTransactionDemo.java`:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public final class CoordinatedTransactionDemo {
    private static final String URL =
        "jdbc:h2:mem:coord_demo;DB_CLOSE_DELAY=-1";

    private CoordinatedTransactionDemo() {}

    public static void main(String[] args) {
        DriverManagerDataSource sharedDataSource = createDataSource();
        JdbcTemplate primaryJdbc = new JdbcTemplate(sharedDataSource);
        JdbcTemplate auditJdbcShared = new JdbcTemplate(sharedDataSource);

        JdbcTransactionManager manager =
            new JdbcTransactionManager(sharedDataSource);
        TransactionTemplate tx = new TransactionTemplate(manager);

        primaryJdbc.execute(
            "CREATE TABLE booking (" +
            "id INT PRIMARY KEY, note VARCHAR(40) NOT NULL)"
        );
        primaryJdbc.execute(
            "CREATE TABLE booking_audit (" +
            "id INT PRIMARY KEY, note VARCHAR(40) NOT NULL)"
        );

        // Đúng: cả hai JdbcTemplate tham gia cùng DataSource/transaction.
        expectRollback(tx, primaryJdbc, auditJdbcShared, 1);
        System.out.println("Shared rollback: " + counts(primaryJdbc));

        // Sai: cùng JDBC URL nhưng một DataSource khác và connection riêng.
        DriverManagerDataSource anotherDataSource = createDataSource();
        JdbcTemplate auditJdbcOther = new JdbcTemplate(anotherDataSource);

        expectRollback(tx, primaryJdbc, auditJdbcOther, 2);
        System.out.println("Different DataSource rollback: " + counts(primaryJdbc));

        // Đúng: cả hai thao tác thành công trong một transaction.
        tx.executeWithoutResult(status -> {
            primaryJdbc.update(
                "INSERT INTO booking(id, note) VALUES (?, ?)",
                3, "created"
            );
            auditJdbcShared.update(
                "INSERT INTO booking_audit(id, note) VALUES (?, ?)",
                3, "recorded"
            );
        });
        System.out.println("Shared commit: " + counts(primaryJdbc));
    }

    private static DriverManagerDataSource createDataSource() {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl(URL);
        dataSource.setUsername("sa");
        dataSource.setPassword("");
        return dataSource;
    }

    private static void expectRollback(
        TransactionTemplate tx,
        JdbcTemplate primaryJdbc,
        JdbcTemplate auditJdbc,
        int id
    ) {
        try {
            tx.executeWithoutResult(status -> {
                primaryJdbc.update(
                    "INSERT INTO booking(id, note) VALUES (?, ?)",
                    id, "created"
                );
                auditJdbc.update(
                    "INSERT INTO booking_audit(id, note) VALUES (?, ?)",
                    id, "recorded"
                );
                throw new IllegalStateException("SIMULATED_FAILURE");
            });
            throw new AssertionError("Expected transaction failure");
        } catch (IllegalStateException error) {
            if (!"SIMULATED_FAILURE".equals(error.getMessage())) {
                throw error;
            }
        }
    }

    private static String counts(JdbcTemplate jdbc) {
        Integer bookings = jdbc.queryForObject(
            "SELECT COUNT(*) FROM booking", Integer.class
        );
        Integer audits = jdbc.queryForObject(
            "SELECT COUNT(*) FROM booking_audit", Integer.class
        );
        return "bookings=" + bookings + ", audit=" + audits;
    }
}
```

Chạy từ thư mục chứa `build.gradle`:

```bash
gradle run --quiet
```

Nếu đã có Gradle Wrapper phù hợp, trên Linux/macOS dùng `./gradlew run --quiet`; trên Windows dùng `gradlew.bat run --quiet`.

**Stdout dự kiến của chương trình Java** (không tính log Gradle):

```text
Shared rollback: bookings=0, audit=0
Different DataSource rollback: bookings=0, audit=1
Shared commit: bookings=1, audit=2
```

### 3.3. Vì sao ra các con số ấy?

- Lần 1: `primaryJdbc` và `auditJdbcShared` đều tham chiếu **chính đối tượng `sharedDataSource`**. `JdbcTransactionManager(sharedDataSource)` gắn connection với thread; cả hai `INSERT` tham gia transaction. Ngoại lệ runtime khiến transaction rollback; đếm lại sau khi callback kết thúc được `0, 0`.
- Lần 2: `anotherDataSource` được tạo **mới**, nhưng URL kết nối giống hệt. Nó vẫn có thể cấp một `Connection` khác, không nằm dưới transaction đang quản lý `sharedDataSource`. Trong cấu hình demo, statement của `auditJdbcOther` chạy với auto-commit nên bản ghi audit có `id=2` đã commit; còn `booking id=2` do `primaryJdbc` tạo bị rollback. Kết quả `0, 1` là một trạng thái **ghi một phần**, không phải một rollback toàn phần.
- Lần 3: cả hai `JdbcTemplate` dùng chung datasource; callback chạy không lỗi và `TransactionTemplate` commit. Lúc này một `booking id=3` và audit tương ứng được lưu. **Bản ghi audit id=2 từ lần lỗi trước vẫn tồn tại**, nên đếm là `1, 2`, không phải `1, 1`.
- `DB_CLOSE_DELAY=-1` giữ database H2 trong bộ nhớ suốt vòng đời JVM để các connection mới vẫn thấy cùng database. Chính vì hai datasource truy cập **cùng database**, ví dụ làm nổi bật rằng **cùng database khác với cùng transaction**.

**Giới hạn của ví dụ:** H2 cho phép những thao tác đơn giản này, nhưng hành vi khóa, auto-commit và cách phản ứng với DDL có thể khác DBMS thực. Với hệ thống thật, hãy kiểm thử trên database, driver và connection pool đang sử dụng. `DriverManagerDataSource` tạo connection đơn giản để học; production thường dùng pool như HikariCP.

## 4. Kết nối đúng các bean trong một ứng dụng Spring

Thông thường chỉ định nghĩa **một bean `DataSource`** làm nguồn kết nối cho nhóm thao tác cần phối hợp, tạo repository/templates trên bean đó và tạo transaction manager điều khiển bean ấy. Ví dụ cấu trúc Spring (các phương thức DAO chỉ là minh họa, không phải chương trình độc lập):

```java
@Configuration
@EnableTransactionManagement
public class BookingJdbcConfig {
    @Bean("bookingDataSource")
    public DataSource bookingDataSource() {
        // Thực tế cấu hình pool/credentials qua properties và secrets.
        HikariDataSource pool = new HikariDataSource();
        pool.setJdbcUrl("jdbc:postgresql://localhost:5432/booking");
        pool.setUsername("booking_app");
        // Password do hệ thống cấu hình an toàn cung cấp.
        return pool;
    }

    @Bean("bookingJdbc")
    public JdbcTemplate bookingJdbc(
        @Qualifier("bookingDataSource") DataSource dataSource
    ) {
        return new JdbcTemplate(dataSource);
    }

    @Bean("bookingTransactionManager")
    public PlatformTransactionManager bookingTransactionManager(
        @Qualifier("bookingDataSource") DataSource dataSource
    ) {
        return new JdbcTransactionManager(dataSource);
    }
}
```

Đoạn trên cần các import Spring Configuration/Bean/Qualifier, `DataSource`, `HikariDataSource`, `JdbcTemplate`, `PlatformTransactionManager`, `JdbcTransactionManager`; cần dependency HikariCP/driver và cấu hình credentials thật. Nó **minh họa wiring** nên chưa có mã khởi động độc lập và không nên dùng giá trị cấu hình database mẫu ở production.

Một service có thể phối hợp hai repository cùng dùng `bookingJdbc`:

```java
@Service
public class BookingService {
    private final BookingRepository bookings;
    private final InventoryRepository inventory;

    public BookingService(
        BookingRepository bookings,
        InventoryRepository inventory
    ) {
        this.bookings = bookings;
        this.inventory = inventory;
    }

    @Transactional(transactionManager = "bookingTransactionManager")
    public long reserve(ReserveCommand command) {
        long bookingId = bookings.insertPending(command);

        int changed = inventory.tryReserve(
            command.sku(), command.quantity()
        );
        if (changed != 1) {
            throw new IllegalStateException("OUT_OF_STOCK");
        }

        bookings.markReserved(bookingId);
        return bookingId;
    }
}
```

`BookingRepository`, `InventoryRepository` và `ReserveCommand` là kiểu nghiệp vụ cần định nghĩa trong dự án; đoạn này chỉ minh họa ranh giới service. Nếu cả hai repository cùng dùng `bookingJdbc`, manager đã đặt trên datasource đó, và `@Transactional` thực sự được proxy áp dụng, các lệnh JDBC sẽ tham gia transaction theo propagation hiện hành.

**Đặc biệt quan trọng:** nếu có **nhiều transaction manager** trong Spring context, dùng `@Transactional("bookingTransactionManager")` hoặc `@Transactional(transactionManager = "bookingTransactionManager")` để chỉ rõ manager cho service. Không giả định Spring sẽ luôn chọn manager của datasource mà repository tình cờ sử dụng.

Trong Spring Boot, autoconfiguration thường tạo datasource/transaction manager theo dependencies và properties khi đủ điều kiện. Tuy nhiên khi ứng dụng định nghĩa nhiều bean, cấu hình tự động có thể thay đổi. Hãy xác minh **bean thực sự được inject**, đừng chỉ xem tên trong file YAML rồi kết luận đã đồng bộ.

## 5. Ranh giới transaction của `@Transactional`

Dù chọn đúng datasource và manager, cần thỏa các điều kiện sau:

### 5.1. Phải đi qua Spring proxy

`@Transactional` ở chế độ proxy mặc định chỉ phát huy khi có lời gọi đi **qua Spring-managed proxy**. Ví dụ:

```java
@Service
public class TransferService {
    public void process() {
        reserve(); // this.reserve(): lời gọi nội bộ, bỏ qua proxy.
    }

    @Transactional(transactionManager = "bookingTransactionManager")
    public void reserve() {
        // JDBC write ...
    }
}
```

Gọi `process()` từ bên ngoài không khiến lời gọi nội bộ `reserve()` tự động có transaction theo annotation của `reserve`. Đặt boundary `@Transactional` ở phương thức service được gọi qua proxy, chuyển sang bean khác hoặc dùng `TransactionTemplate` nếu cần ranh giới tường minh. Đừng xác định transaction đã hoạt động chỉ vì thấy annotation trong source.

### 5.2. Propagation có thể đổi đơn vị commit

- `REQUIRED` (mặc định): tham gia transaction hiện hữu nếu phù hợp; nếu chưa có thì mở transaction mới. Nếu đang tham gia outer transaction, **method return chưa đồng nghĩa outer transaction đã commit**.
- `REQUIRES_NEW`: tạo transaction độc lập, tạm ngưng transaction hiện tại; phần đã commit trong inner transaction không tự rollback theo outer transaction sau đó. Một event/audit trong `REQUIRES_NEW` có thể còn tồn tại khi nghiệp vụ chính bị rollback.
- `NESTED`: với JDBC manager và database/driver hỗ trợ savepoint, có thể rollback một phần theo savepoint. `NESTED` không đồng nghĩa `REQUIRES_NEW`, và không có ở mọi transaction manager/provider.
- `SUPPORTS`, `NOT_SUPPORTED`, `NEVER` hoặc `MANDATORY` ảnh hưởng việc thực sự có transaction. Đọc propagation tại từng entry point khi kết luận các thao tác “cùng nhóm”.

Hai phương thức cùng dùng một datasource **không bảo đảm** cùng transaction nếu một phương thức chủ động mở transaction khác.

### 5.3. Lỗi phải đi tới ranh giới rollback

Theo mặc định của Spring, ngoại lệ `RuntimeException` hoặc `Error` làm rollback transaction khai báo, trong khi checked exception thường không tự kích hoạt rollback nếu không có `rollbackFor`/quy tắc riêng.

```java
@Transactional(
    transactionManager = "bookingTransactionManager",
    rollbackFor = IOException.class
)
public void importOrders() throws IOException {
    // Ghi DB và đọc nguồn có thể phát sinh IOException.
}
```

Đây là đoạn khai báo minh họa, cần imports/type và logic thực tế. Nếu code bắt lỗi rồi trả “success” mà không ném lại hoặc đánh dấu rollback-only, manager có thể commit những dữ liệu đã ghi. Dùng ngoại lệ domain và quy tắc rollback phù hợp; nếu cần tiếp tục sau lỗi, thiết kế trạng thái nhất quán thay vì nuốt lỗi không kiểm soát.

### 5.4. Transaction imperative gắn với thread

JDBC `PlatformTransactionManager` dùng trạng thái tài nguyên gắn với thread. Một công việc được gửi qua `@Async`, `new Thread(...)`, `CompletableFuture.supplyAsync(...)` hoặc một executor **không tự thừa kế JDBC transaction** của thread gọi. Một `JdbcTemplate` được gọi trong worker thread có thể mở connection riêng dù sử dụng cùng datasource.

Với reactive `R2dbcTransactionManager`, transaction sử dụng **Reactor Context** và R2DBC `ConnectionFactory`; không ghép tùy ý với JDBC `DataSource` rồi hy vọng chúng cùng commit. Nếu kiến trúc thực sự cần phối hợp qua ranh giới bất đồng bộ, hãy dùng quy trình có trạng thái, outbox, retry hoặc hạ tầng transaction phù hợp.

## 6. Những cách chọn sai DataSource/manager thường gặp

| Tình huống | Điều có thể xảy ra | Cách sửa hoặc xác minh |
| --- | --- | --- |
| Hai datasource tạo bằng `new ...DataSource()` với cùng JDBC URL | Hai connection/transaction độc lập | Inject và tái sử dụng cùng datasource bean hoặc proxy được thiết kế tương thích |
| Manager cho `ordersDataSource`, DAO lại dùng `reportingDataSource` | DAO không tham gia transaction đúng tài nguyên | Kiểm tra `@Qualifier`, `JdbcTemplate.getDataSource()`, bean wiring |
| Dùng `dataSource.getConnection()` trực tiếp trong code thủ công | Bỏ qua transaction-aware connection lookup | Dùng `JdbcTemplate` hoặc `DataSourceUtils.getConnection/releaseConnection` |
| Tạo `JdbcTemplate(new DriverManagerDataSource(...))` ngay trong repository | Có datasource riêng ngoài cấu hình chung, dễ auto-commit | Constructor injection từ bean `DataSource` đã chọn |
| Hai `PlatformTransactionManager` độc lập cho cùng chuỗi thao tác | Có thể commit hoặc rollback riêng, hành vi khó đoán | Chọn đúng một owner cho một đơn vị công việc; không chồng manager tùy ý |
| `@Transactional` nội bộ qua `this.method()` | Advice không chạy ở proxy mode | Đặt transaction ở public entry point qua Spring bean proxy |
| Inner `REQUIRES_NEW` hoặc `@Async` | Không cùng physical transaction | Chỉ dùng khi cần chủ động tách transaction; test rollback |
| Trộn JPA và JDBC với manager không tương thích | JDBC và EntityManager có thể không chung boundary | Cấu hình `JpaTransactionManager` đúng `EntityManagerFactory`/`DataSource`, kiểm thử tích hợp |
| Hai database, hai pool, hai service | Một local JDBC manager không thể bảo đảm atomicity trên cả hai | Cân nhắc JTA/XA nếu thực sự cần giao dịch phân tán, hoặc outbox/saga |
| Gọi stored routine có implicit commit/DDL | Transaction có thể kết thúc ngoài ý định | Xem DBMS/DDL/routine, kiểm thử hành vi rollback cụ thể |

### TransactionAwareDataSourceProxy và LazyConnectionDataSourceProxy

Không nên kết luận “tên bean/instance phải giống hệt trong mọi trường hợp” mà bỏ qua **proxy chuyên dụng** của Spring:

- `TransactionAwareDataSourceProxy` giúp **code JDBC cũ dùng `DataSource.getConnection()`** nhận kết nối có nhận biết transaction và xử lý close theo Spring. Khi dùng với `DataSourceTransactionManager`, manager thường phải nhận **target `DataSource`**, không cần tự bọc lặp lại.
- `LazyConnectionDataSourceProxy` trì hoãn lấy physical connection; có thể hỗ trợ transaction không thực sự cần kết nối DB và phối hợp routing theo transaction. Khi dùng, manager và data-access phải được cấu hình theo đúng cùng chuỗi wrapper/target mà tài liệu Spring quy định.
- Với `AbstractRoutingDataSource`, lựa chọn tenant/primary/replica phụ thuộc context routing. Nếu thay routing key giữa transaction, connection đã lấy có thể vẫn hướng về nguồn ban đầu. Phải xác định route trước khi bắt đầu transaction và kiểm thử nhất quán.

Thông điệp thực dụng: **tái sử dụng chính datasource bean hoặc một cấu hình wrapper được Spring hỗ trợ có chủ đích**, không tự tạo các connection factory khác nhau chỉ vì URL giống nhau.

## 7. Trộn nhiều công nghệ: JDBC, JPA, nhiều DB

### 7.1. JDBC + JPA trong cùng database

Nếu cùng nghiệp vụ vừa gọi JPA repository vừa gọi `JdbcTemplate`, không tự thay `JpaTransactionManager` bằng `JdbcTransactionManager` và giả định EntityManager vẫn tham gia như cũ.

`JpaTransactionManager` có thể hỗ trợ JDBC tham gia cùng transaction JPA khi cấu hình đúng `EntityManagerFactory`, `DataSource` và cơ chế truy cập connection của JPA provider. Spring nêu rõ `DataSourceUtils` hỗ trợ kết nối được bind với `JpaTransactionManager` trong các điều kiện phù hợp. **Cần kiểm thử thực tế** với provider, phiên bản driver và cấu hình datasource: `flush` JPA, thời điểm SQL của ORM được gửi xuống DB và transaction isolation có thể ảnh hưởng quan sát.

Khi một service chủ yếu thao tác JPA, chọn manager phù hợp cho JPA rồi cấu hình phần JDBC tham gia đúng tài nguyên; khi toàn bộ là JDBC một database, `JdbcTransactionManager` thường đơn giản hơn. Không chọn dựa trên tên “transactionManager” một cách mơ hồ.

### 7.2. Hai datasource thật sự độc lập

Một local `DataSourceTransactionManager` chỉ quản lý connection của **một datasource**. Nếu nghiệp vụ phải ghi vào database A và database B, dù mỗi manager đều hoạt động đúng, commit của A có thể thành công còn B thất bại.

Có hai loại giải pháp, chọn theo yêu cầu tính nhất quán:

1. **Giao dịch phân tán thực sự:** dùng transaction coordinator JTA/XA và tài nguyên/driver XA phù hợp nếu sản phẩm và hạ tầng hỗ trợ. Hai-phase commit có chi phí, giới hạn về failover và vận hành; không tự nhiên xuất hiện chỉ vì khai báo hai `@Transactional`.
2. **Nhất quán cuối cùng có kiểm soát:** dùng transactional outbox, event relay, idempotency, retry/đối soát, saga/compensation để xử lý các hệ thống tách biệt. Thiết kế trạng thái trung gian và trường hợp bị trùng/lỗi.

Một loạt local transaction được gọi tuần tự hoặc được “chain” **không trở thành atomic distributed transaction** vì không có phối hợp commit kiểu XA.

### 7.3. Email, HTTP, payment và message broker

Ngay cả khi mọi câu SQL thuộc cùng datasource, thao tác gọi API ngoài **không tự rollback** theo database. Không giữ DB transaction mở quá lâu để chờ một HTTP API chậm và tự xem đó là atomicity. Có thể ghi outbox trong transaction dữ liệu rồi publish độc lập; consumer cần idempotency. Một event listener `AFTER_COMMIT` tránh hành động trước commit, nhưng **không thay thế** bảo đảm gửi bền vững nếu process chết sau commit.

## 8. Cách quan sát đúng transaction đang hoạt động

Khi nghi ngờ một DAO không nằm trong transaction, có thể log tạm trạng thái do Spring cung cấp:

```java
// Đoạn chẩn đoán đặt bên trong lời gọi JDBC/service.
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();

boolean boundToExpectedDataSource =
    TransactionSynchronizationManager.hasResource(expectedDataSource);
```

Cần import `org.springframework.transaction.support.TransactionSynchronizationManager` và có `DataSource expectedDataSource` phù hợp. Hai thông tin này hữu ích để khoanh vùng vấn đề, **không phải bằng chứng cuối cùng rằng mọi lệnh đã commit hoặc mọi DAO cùng connection**. Phải xem kết quả rollback/commit thực tế, propagation, routing và loại transaction manager.

Checklist khi điều tra:

1. Xác định public entry point được gọi qua Spring proxy hay code thuần; annotation nằm trên method nào?
2. Xác định **tên manager thật sự được chọn** (có qualifier `@Transactional(transactionManager="...")` không?).
3. Truy các đối tượng `JdbcTemplate`, `NamedParameterJdbcTemplate`, repository tới bean `DataSource` thật và wrapper của nó.
4. Xác nhận hoạt động trên cùng thread/context, không nhảy `@Async`, và không dùng propagation tách transaction ngoài dự kiến.
5. Bật logging transaction **trong môi trường phát triển**, ví dụ logger `org.springframework.transaction` và `org.springframework.jdbc.datasource` ở mức DEBUG phù hợp; tránh log SQL parameters nhạy cảm hoặc credentials.
6. Tạo phép thử chủ động gây lỗi sau khi đã ghi hai nơi, rồi đọc lại **sau khi transaction kết thúc** từ kết nối độc lập. Chỉ test này mới cho bằng chứng mạnh về rollback end-to-end của nhóm thao tác.

Có thể xem `DataSourceUtils` là cách Spring tiếp cận connection đúng scope; đừng gọi `getConnection()`, `commit()`, `rollback()` thủ công bên trong code đã được manager kiểm soát vì việc đó dễ phá quy tắc ownership và thời điểm kết thúc transaction.

## 9. Thiết kế kiểm thử tích hợp có giá trị

Một bộ integration test cho thao tác phối hợp nên kiểm chứng các tình huống sau:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Tất cả câu lệnh thành công | Cả bản ghi chính và bản ghi phụ cùng xuất hiện sau commit |
| Lỗi trong bước thứ hai | Bản ghi bước đầu tiên không còn sau rollback; không có dữ liệu phụ |
| Lỗi trong bước cuối | Các bước trước cùng rollback; không còn trạng thái nửa vời |
| Repository bị trỏ nhầm datasource | Test bắt được tình trạng một bản ghi phụ đã commit dù nghiệp vụ chính rollback |
| `@Transactional` bị self-invocation | Test cho thấy rollback không được áp dụng như mong đợi; sửa entry point rồi test lại |
| `REQUIRES_NEW` được dùng có chủ ý | Kiểm chứng phần inner commit được giữ dù outer rollback; trạng thái này phải đúng hợp đồng |
| Ngoại lệ checked | Xác minh `rollbackFor`/quy tắc rollback, không chỉ tên annotation |
| Multi-DB hoặc external system | Kiểm chứng cơ chế bù trừ/retry/outbox và xử lý lỗi giữa các bước, không đòi local manager bao trùm tất cả |

Với Spring Test, lưu ý test method gắn `@Transactional` có thể tự rollback cuối test. Điều đó tiện cô lập dữ liệu nhưng có thể **che mất lỗi ở ranh giới commit thực tế** của service. Khi cần chứng minh trạng thái sau commit, tổ chức test ngoài transaction mặc định của test hoặc dùng công cụ Spring Test (ví dụ `TestTransaction`) để kết thúc transaction rồi đọc lại. Với nhiều pool hoặc database, test phải chạy trên cùng loại hạ tầng và cấu hình proxy/routing như production.

Các phép kiểm tra chỉ dựa vào `TransactionSynchronizationManager.isActualTransactionActive()` hay `id != null` chưa đủ: transaction có thể active ở datasource A, trong khi DAO B vẫn ghi auto-commit qua datasource khác.

## 10. Quy trình chọn cấu hình trong dự án thực tế

Áp dụng theo thứ tự:

1. **Liệt kê các thao tác phải commit/rollback cùng nhau.** Nếu tất cả dùng một DB hỗ trợ transaction, ưu tiên một local JDBC transaction bao quanh chúng.
2. **Chọn một `DataSource` được quản lý duy nhất cho nhóm JDBC đó.** Cấu hình pool, routing và credentials ở một nơi; inject bean đã chọn vào mọi `JdbcTemplate` liên quan.
3. **Tạo/định vị manager đúng tài nguyên.** Thuần JDBC có thể dùng `JdbcTransactionManager(ds)` hoặc `DataSourceTransactionManager(ds)`; khi có JPA, cân nhắc `JpaTransactionManager` đúng provider/source.
4. **Đặt ranh giới ở service có ý nghĩa nghiệp vụ.** Dùng `@Transactional(transactionManager="...")` qua proxy hoặc `TransactionTemplate`, phân biệt propagation của lời gọi bên trong.
5. **Giữ truy cập connection tương thích Spring.** Dùng templates hoặc `DataSourceUtils`; tránh kết nối thủ công, manager phụ và thay thread bất ngờ.
6. **Xác định tín hiệu thất bại.** Kiểm tra row count, điều kiện nghiệp vụ và ngoại lệ; để rollback đúng cách. Không suy luận hoàn tất nghiệp vụ từ một ID vừa tạo.
7. **Kiểm chứng commit/rollback bằng integration test.** Chủ động gây lỗi giữa các lệnh và đọc trạng thái sau transaction từ một kết nối riêng.
8. **Chọn chiến lược cho phần ngoài một DB.** JTA/XA khi thực sự có yêu cầu distributed atomicity; outbox/saga/idempotency/retry khi triển khai theo quy trình phân tán.

**Ghi nhớ:** Muốn các thao tác Spring JDBC cùng chịu một giao dịch cục bộ, hãy phối hợp **đúng `DataSource`/connection được Spring quản lý, đúng transaction manager và đúng phạm vi thực thi**. Chỉ giống JDBC URL, cùng tên database hoặc cùng annotation `@Transactional` không chứng minh chúng có chung kết quả commit/rollback.

### Tài liệu tham khảo

- [Spring Framework 6.2 — JDBC connections và DataSourceUtils](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/connections.html)
- [Spring Framework — Transaction abstraction](https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html)
- [Spring Framework — Synchronizing resources with transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html)
- [Spring Framework 6.2 — Using @Transactional và lựa chọn nhiều managers](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Understanding transaction proxy](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — DataSourceTransactionManager API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html)
- [Spring Framework — JdbcTransactionManager API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/support/JdbcTransactionManager.html)
