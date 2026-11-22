# Đồ thị liên kết transaction manager, DataSource hoặc ConnectionFactory và mã truy cập dữ liệu trong Spring

## 1. Vì sao cần đọc đúng đồ thị liên kết?

Khi viết `@Transactional`, điều cần kiểm tra không chỉ là annotation có mặt, mà là **transaction manager nào đang điều khiển giao dịch, manager đó quản lý tài nguyên nào, và đoạn mã truy cập dữ liệu có lấy đúng connection thuộc giao dịch đó hay không**. Ba mắt xích này quyết định một câu SQL có được commit/rollback cùng các câu SQL khác.

Trong Spring Framework, mô hình cần nhìn theo **hai nhánh tách biệt**:

- **Imperative/JDBC:** `PlatformTransactionManager`, `javax.sql.DataSource`, JDBC `Connection`, `JdbcTemplate` hoặc repository dùng JDBC. Transaction context thường gắn với **thread**.
- **Reactive/R2DBC:** `ReactiveTransactionManager`, `io.r2dbc.spi.ConnectionFactory`, R2DBC `Connection`, `DatabaseClient` hoặc reactive repository. Transaction context gắn với **Reactor subscriber Context**, không dựa vào ThreadLocal của JDBC.

Ngoài ra, **JPA** là một nhánh imperative quan trọng: `JpaTransactionManager` quản lý `EntityManagerFactory`/`EntityManager`; bên dưới JPA provider thường vẫn dùng JDBC `DataSource`. JPA không phải R2DBC.

Cần phân biệt:

| Thành phần | Câu hỏi nó trả lời | Chức năng |
| --- | --- | --- |
| Transaction boundary (`@Transactional`, `TransactionTemplate`, `TransactionalOperator`) | Khi nào bắt đầu/kết thúc phạm vi? | Khai báo hoặc lập trình quy tắc transaction |
| Transaction manager | Ai begin/join, commit, rollback và đồng bộ hóa tài nguyên? | Điều phối giao dịch phù hợp với công nghệ lưu trữ |
| `DataSource` / `ConnectionFactory` / `EntityManagerFactory` | Lấy tài nguyên truy cập dữ liệu từ đâu? | Factory/pool hoặc abstraction tạo tài nguyên |
| `JdbcTemplate` / `DatabaseClient` / `EntityManager` / repository | Ai thực thi SQL hoặc thao tác persistence? | Cung cấp API truy cập dữ liệu cho nghiệp vụ |
| JDBC/R2DBC `Connection` | Thay đổi được thực hiện qua kết nối nào? | Tài nguyên vật lý hoặc logical handle được quản lý trong transaction |
| Database | Hệ thống cuối cùng lưu dữ liệu ở đâu? | Nơi thực thi SQL và xác nhận/hủy transaction |

**Quy tắc nền tảng:** transaction manager không tự tìm và gom mọi câu SQL trong ứng dụng. Mã truy cập dữ liệu phải sử dụng **đúng tài nguyên được đồng bộ hóa** với manager. Cùng một URL database hoặc cùng một câu lệnh SQL chưa đủ để chứng minh hai thao tác thuộc cùng giao dịch.

## 2. Đồ thị tổng thể: hai đường đi song song

Hai sơ đồ sau là **đồ thị liên kết bean và luồng thực thi**; mũi tên ghi `begin/commit/rollback` thể hiện quyền điều khiển giao dịch, còn mũi tên `lấy connection` thể hiện đường truy cập tài nguyên. Chúng không hàm ý Spring luôn gửi câu SQL `BEGIN` ở mỗi method.

### 2.1. Nhánh JDBC, chạy đồng bộ

~~~mermaid
flowchart LR
    A["Caller"] --> B["Spring proxy"]
    B --> C["TransactionInterceptor"]
    C -->|"begin / join / commit / rollback"| M["PlatformTransactionManager<br/>JdbcTransactionManager<br/>hoặc DataSourceTransactionManager"]
    C -->|"gọi method"| S["Service @Transactional"]
    S --> D["DAO / Repository"]
    D --> J["JdbcTemplate"]
    J --> U["DataSourceUtils"]
    U --> H["Connection gắn với thread"]
    M -->|"lấy và quản lý"| DS["DataSource"]
    DS --> H
    H --> DB[("Cơ sở dữ liệu")]
~~~

Nhìn đồ thị thành hai nhánh **cùng gặp nhau tại connection**:

- **Nhánh điều khiển:** proxy → `TransactionInterceptor` → transaction manager → `DataSource` → connection. Manager giữ quyền commit hoặc rollback.
- **Nhánh nghiệp vụ:** service → DAO → `JdbcTemplate` → `DataSourceUtils` → connection đã gắn với transaction. DAO thực thi SQL; nó không tự quyết định commit.

`JdbcTransactionManager` kế thừa cơ chế của `DataSourceTransactionManager` và bổ sung dịch lỗi commit/rollback sang hệ phân cấp `DataAccessException` trong các trường hợp phù hợp. Cả hai dùng `DataSource` cho giao dịch JDBC một tài nguyên. Chúng **không** quản lý tất cả các database hoặc tất cả các `DataSource` của ứng dụng theo kiểu tự động.

### 2.2. Nhánh R2DBC, chạy reactive

~~~mermaid
flowchart LR
    A["Subscriber"] --> B["Publisher từ service"]
    B --> C["Transactional advice<br/>hoặc TransactionalOperator"]
    C -->|"begin / join / commit / rollback"| M["ReactiveTransactionManager<br/>R2dbcTransactionManager"]
    C -->|"subscribe luồng nghiệp vụ"| S["Reactive service"]
    S --> D["Reactive DAO / Repository"]
    D --> J["DatabaseClient"]
    J --> U["ConnectionFactoryUtils"]
    U --> H["Connection gắn với<br/>Reactor subscriber Context"]
    M -->|"lấy và quản lý"| CF["ConnectionFactory"]
    CF --> H
    H --> DB[("Cơ sở dữ liệu")]
~~~

Ở nhánh này, method trả về `Mono`/`Flux` chỉ **mô tả** phép tính. Việc truy cập DB và bắt đầu transaction thường xảy ra **khi Publisher được subscribe**; subscriber context là cơ chế để các thao tác trong pipeline dùng lại connection do `R2dbcTransactionManager` quản lý.

Cả hai nhánh đều có pattern "manager quản lý một factory, data-access code lấy tài nguyên qua tiện ích nhận biết transaction". Sự giống nhau về hình dạng **không có nghĩa** JDBC `DataSource` và R2DBC `ConnectionFactory` dùng chung context, connection hoặc commit với nhau.

## 3. Từng cạnh trong đồ thị JDBC có ý nghĩa gì?

### 3.1. Manager và DataSource

`DataSource` (JDBC) là factory chuẩn để lấy `java.sql.Connection`; implementation thường là connection pool như HikariCP. `DataSourceTransactionManager`/`JdbcTransactionManager` nhận **một `DataSource` cụ thể** qua constructor hoặc setter. Manager dùng connection thuộc nguồn này để thiết lập transaction, phối hợp isolation/read-only/timeout trong giới hạn được hỗ trợ, commit hoặc rollback và trả tài nguyên về pool.

Trong Spring imperative, `TransactionSynchronizationManager` giữ liên kết tài nguyên với **thread hiện hành**. Với JDBC manager, một `ConnectionHolder` được gắn dưới khóa liên quan đến `DataSource` của transaction. DAO dùng đúng `DataSource` sẽ có cơ hội nhận lại connection đã gắn, thay vì mượn một connection độc lập.

Đường đúng:

~~~text
jdbcTxManager ──tham chiếu──> mainDataSource ──cấp──> JDBC Connection
paymentJdbcTemplate ──tham chiếu──> mainDataSource
paymentJdbcTemplate ──DataSourceUtils──> Connection đang gắn với transaction
~~~

Đường đáng nghi:

~~~text
jdbcTxManager ──> mainDataSource
paymentJdbcTemplate ──> auditDataSource
~~~

Nếu `mainDataSource` và `auditDataSource` là hai pool hoặc hai wrapper không được phối hợp đúng, manager thứ nhất không tự điều khiển transaction từ pool thứ hai. Ngay cả hai `DataSource` trỏ cùng một database cũng có thể cấp **hai connection riêng**, với commit/rollback độc lập.

### 3.2. JdbcTemplate và DataSourceUtils

`JdbcTemplate` dùng `DataSourceUtils` nội bộ. `DataSourceUtils.getConnection(dataSource)` ưu tiên connection đã gắn với giao dịch ở thread hiện hành; nếu không có, nó lấy connection phù hợp từ `DataSource`. `DataSourceUtils.releaseConnection(connection, dataSource)` biết khi nào **không** được đóng connection còn thuộc transaction; framework thường tự xử lý.

Với JDBC thuần tự viết, cách lấy/giải phóng tài nguyên đúng khi muốn tham gia giao dịch Spring là:

~~~java
Connection connection = DataSourceUtils.getConnection(dataSource);
try {
    // Tạo PreparedStatement, gán tham số, thực thi SQL.
    // Các lời gọi JDBC cụ thể được lược bỏ trong ví dụ cơ chế này.
} finally {
    DataSourceUtils.releaseConnection(connection, dataSource);
}
~~~

Đây là **trích đoạn minh họa**, chưa phải một chương trình độc lập. Gọi trực tiếp `dataSource.getConnection()` trên một `DataSource` thông thường có thể tạo connection mới ngoài transaction được gắn bởi Spring. Với thư viện legacy bắt buộc dùng `DataSource.getConnection()`, có thể nghiên cứu `TransactionAwareDataSourceProxy`; code Spring mới nên ưu tiên `JdbcTemplate` hoặc `DataSourceUtils`.

### 3.3. Trình tự một transaction JDBC

1. Caller gọi method từ **Spring bean proxy**; self-invocation qua `this.method()` trong cùng bean không qua advice ở proxy mode.
2. `TransactionInterceptor` chọn `PlatformTransactionManager` và quy tắc `@Transactional`. Với `REQUIRED`, nếu chưa có transaction hiện hành thì tạo mới; nếu có thì tham gia.
3. Manager lấy JDBC connection của `DataSource` tương ứng, chuẩn bị đặc tính giao dịch phù hợp (ví dụ auto-commit) và gắn connection vào transaction context của thread.
4. Service gọi DAO; `JdbcTemplate` lấy connection qua `DataSourceUtils` và thực thi SQL trên connection đó.
5. Nếu method kết thúc thành công và không có rollback-only, manager của **giao dịch vật lý ngoài cùng** yêu cầu commit; nếu vi phạm rollback rule hoặc đã đánh dấu rollback-only thì rollback.
6. Manager thực hiện cleanup: đồng bộ hóa callback cần thiết, gỡ liên kết tài nguyên, phục hồi trạng thái connection và trả lại nguồn cấp. Scope `REQUIRED` bên trong chỉ tham gia transaction nên không tự commit vật lý riêng.

Đừng nhầm **bean singleton** như `JdbcTemplate` với **connection duy nhất**: template được dùng chung giữa nhiều request/thread; mỗi transaction có resource context của riêng nó. Ngược lại, trong một scope giao dịch, nhiều lệnh `JdbcTemplate` có thể dùng **cùng connection hiện hành**.

## 4. Từng cạnh trong đồ thị R2DBC có ý nghĩa gì?

### 4.1. ReactiveTransactionManager và ConnectionFactory

`ConnectionFactory` là giao diện của **R2DBC**, cung cấp publisher tạo `io.r2dbc.spi.Connection`. `R2dbcTransactionManager` quản lý một `ConnectionFactory` và gắn connection vào **subscriber Context**. Nó có thể begin/commit/rollback trên R2DBC connection và giải phóng tài nguyên qua lifecycle reactive.

`DatabaseClient` của Spring Framework là API chạy SQL non-blocking; các thao tác từ client lấy connection bằng cơ chế nhận biết transaction, thông qua `ConnectionFactoryUtils`. Đây là cặp tương ứng với `JdbcTemplate` + `DataSourceUtils` ở nhánh JDBC:

| JDBC imperative | R2DBC reactive |
| --- | --- |
| `PlatformTransactionManager` | `ReactiveTransactionManager` |
| `JdbcTransactionManager`/`DataSourceTransactionManager` | `R2dbcTransactionManager` |
| `javax.sql.DataSource` | `io.r2dbc.spi.ConnectionFactory` |
| `java.sql.Connection` | `io.r2dbc.spi.Connection` |
| `JdbcTemplate` | `org.springframework.r2dbc.core.DatabaseClient` |
| `DataSourceUtils` | `ConnectionFactoryUtils` |
| Thread-bound resource | Reactor subscriber Context-bound resource |
| Logic thực thi ngay trong lời gọi method | Publisher thường được thực thi khi subscribe |

Dùng `connectionFactory.create()` trực tiếp trong DAO không mặc nhiên lấy lại connection đang được Spring quản lý. Khi cần thao tác R2DBC ở tầng thấp, dùng `ConnectionFactoryUtils.getConnection(factory)` và cơ chế release tương ứng, hoặc ưu tiên `DatabaseClient`. Với client R2DBC bên thứ ba không tích hợp Spring, có `TransactionAwareConnectionFactoryProxy` trong những trường hợp phù hợp; proxy này không biến một JDBC `DataSource` thành R2DBC.

### 4.2. Reactive context không phải ThreadLocal

Một pipeline có thể đổi thread trong lúc thực thi mà vẫn giữ transaction context của subscriber. Điều kiện then chốt là các thao tác **tiếp tục trong cùng reactive pipeline/context**, sử dụng đúng `ConnectionFactory`. Không có quy tắc "cùng thread nghĩa là cùng transaction" cho R2DBC; chiều ngược lại, một thread khác trong JDBC imperative cũng không tự nhận transaction chỉ vì nó được tạo từ method `@Transactional`.

Một method reactive được advice bởi `ReactiveTransactionManager` phải trả về kiểu reactive phù hợp, ví dụ `Mono<Void>` hoặc `Flux<T>`. Không tự gọi `subscribe()` bên trong service để chạy một nhánh độc lập rồi trả về: nhánh đó có thể chạy ngoài transaction mà caller dự kiến. Nếu không ai subscribe vào publisher trả về, công việc reactive và transaction cũng thường **không chạy**.

### 4.3. Đồ thị R2DBC với bean wiring và một pipeline

Đoạn dưới là **cấu hình và service minh họa trong một ứng dụng Spring đã có một `ConnectionFactory` bean, driver R2DBC và bảng `wallet`**. Nó không phải ứng dụng chạy độc lập vì chưa có bootstrap và cấu hình database:

~~~java
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Service;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Configuration
@EnableTransactionManagement
class ReactiveWiring {
    @Bean
    ReactiveTransactionManager r2dbcTx(ConnectionFactory factory) {
        return new R2dbcTransactionManager(factory);
    }

    @Bean
    DatabaseClient databaseClient(ConnectionFactory factory) {
        return DatabaseClient.create(factory);
    }
}

@Service
class ReactiveTransferService {
    private final DatabaseClient db;

    ReactiveTransferService(DatabaseClient db) {
        this.db = db;
    }

    @Transactional(transactionManager = "r2dbcTx")
    public Mono<Void> transfer(int from, int to, long amount) {
        Mono<Void> debit = db.sql(
                "UPDATE wallet SET balance = balance - :amount WHERE id = :id")
            .bind("amount", amount)
            .bind("id", from)
            .fetch()
            .rowsUpdated()
            .flatMap(n -> n == 1
                ? Mono.<Void>empty()
                : Mono.error(new IllegalStateException("debit must update one row")));

        Mono<Void> credit = db.sql(
                "UPDATE wallet SET balance = balance + :amount WHERE id = :id")
            .bind("amount", amount)
            .bind("id", to)
            .fetch()
            .rowsUpdated()
            .flatMap(n -> n == 1
                ? Mono.<Void>empty()
                : Mono.error(new IllegalStateException("credit must update one row")));

        return debit.then(credit);
    }
}
~~~

Ở đây `r2dbcTx` và `DatabaseClient` nhận **chính bean `ConnectionFactory` đã được Spring inject**. Cả hai `UPDATE` được ghép tuần tự bằng `then`; khi publisher được subscribe qua Spring proxy, chúng được thực thi trong transaction reactive. Nếu debit hoặc credit phát lỗi, rollback rule mặc định với `RuntimeException` sẽ yêu cầu rollback. Ví dụ giả định driver hỗ trợ các thao tác và bảng `wallet` có cột `id`, `balance` thích hợp. Trong ứng dụng Spring Boot, nếu `DatabaseClient`/manager đã được autoconfigure thì tái sử dụng bean có sẵn, tránh tự đăng ký bản trùng không cần thiết.

## 5. Đồ thị JPA: manager liên kết tới EntityManagerFactory

Với JPA, đích trực tiếp của `JpaTransactionManager` là `EntityManagerFactory`; thao tác thường đi qua `EntityManager` hoặc Spring Data JPA repository, không đi trực tiếp qua `JdbcTemplate`:

~~~mermaid
flowchart LR
    A["Caller"] --> P["Transactional proxy"]
    P --> T["JpaTransactionManager"]
    P --> S["Service"]
    S --> R["JPA Repository"]
    R --> E["EntityManager<br/>gắn với transaction"]
    T --> F["EntityManagerFactory"]
    F --> E
    F --> DS["DataSource của JPA provider"]
    DS --> C["JDBC Connection"]
    E --> C
    C --> DB[("Cơ sở dữ liệu")]
~~~

`EntityManagerFactory` là factory thường được dùng chung; `EntityManager` là persistence context có vòng đời và phạm vi phù hợp với transaction, **không phải một singleton `EntityManager` dùng chung mọi thread**. Với Spring Data JPA, repository thường hoạt động qua `EntityManager` được Spring quản lý/synchronize.

Có những trường hợp **trộn JPA và JDBC** trên **cùng `DataSource`** trong một transaction do `JpaTransactionManager` quản lý: Spring có thể cho phép JDBC code truy cập connection tương ứng qua `DataSourceUtils` nếu `JpaDialect`/JPA provider và cấu hình hỗ trợ. Không được suy ra điều đó chỉ từ việc hai bean có cùng URL. Khi ứng dụng tự khai báo **cả `JpaTransactionManager` lẫn `JdbcTransactionManager` cho cùng DB**, chọn nhầm manager có thể khiến hai phần chạy trên những transaction riêng; cần thiết kế và kiểm chứng rõ manager mà entrypoint sử dụng.

JPA `flush()` chỉ đồng bộ thay đổi của persistence context xuống DB; **không tương đương commit**. Mục đích của đồ thị JPA là chỉ đúng chủ sở hữu transaction (`JpaTransactionManager` → `EntityManagerFactory`) và con đường mã nghiệp vụ truy cập dữ liệu (repository → `EntityManager`).

## 6. Cách ghép đúng các bean trong một ứng dụng

Một cách đọc cấu hình hiệu quả là tìm từ **đường vào service** đến **manager**, rồi từ manager và DAO tìm về **factory**.

| Nhu cầu | Transaction manager thường phù hợp | Factory phải khớp | API truy cập thường dùng |
| --- | --- | --- | --- |
| JDBC thuần, một DB | `JdbcTransactionManager` hoặc `DataSourceTransactionManager` | `DataSource` | `JdbcTemplate`, Spring JDBC repository |
| JPA (Hibernate hoặc JPA provider khác) | `JpaTransactionManager` | `EntityManagerFactory`, với `DataSource` dưới JPA provider | `EntityManager`, Spring Data JPA |
| R2DBC reactive, một DB | `R2dbcTransactionManager` | `ConnectionFactory` | `DatabaseClient`, Spring Data R2DBC repository |
| JTA/XA khi có hạ tầng phối hợp phù hợp | `JtaTransactionManager` | Transaction coordinator và các tài nguyên đã enlist | JDBC/JPA được cấu hình tham gia JTA |

Khi chỉ có một manager, `@Transactional` thường tìm được manager mặc định qua cấu hình Spring/Boot. Khi có nhiều manager, chọn bằng bean name hoặc qualifier:

~~~java
@Transactional(transactionManager = "ordersJdbcTx")
public void saveOrder() { /* Trích đoạn nghiệp vụ JDBC */ }

@Transactional(transactionManager = "catalogJpaTx")
public void updateCatalog() { /* Trích đoạn nghiệp vụ JPA */ }

@Transactional(transactionManager = "reportR2dbcTx")
public Mono<Void> refreshReport() {
    return Mono.empty(); // Chỉ minh họa kiểu trả về reactive.
}
~~~

Ba method là **chữ ký minh họa**, không phải chương trình chạy độc lập. `@Transactional("ordersJdbcTx")` chọn **một** manager; nó không tự phối hợp ba manager thành một transaction phân tán. Với nhiều `DataSource`, mỗi manager phải được nối đúng với `JdbcTemplate`/repository mong muốn; với nhiều `ConnectionFactory` cũng tương tự.

### Ví dụ cấu hình JDBC tối thiểu, chỉ biểu diễn các cạnh bean

~~~java
@Configuration
@EnableTransactionManagement
class JdbcWiring {
    @Bean
    PlatformTransactionManager ordersJdbcTx(
            @Qualifier("ordersDataSource") DataSource ds) {
        return new JdbcTransactionManager(ds);
    }

    @Bean
    JdbcTemplate ordersJdbc(
            @Qualifier("ordersDataSource") DataSource ds) {
        return new JdbcTemplate(ds);
    }
}
~~~

Đây là **trích đoạn**: giả định đã có bean `ordersDataSource` và imports `@Configuration`, `@Bean`, `@Qualifier`, `DataSource`, `PlatformTransactionManager`, `JdbcTransactionManager`, `JdbcTemplate`. Nó nói rõ quan hệ:

~~~text
ordersJdbcTx ─────┐
                  ├──> ordersDataSource
ordersJdbc ───────┘
~~~

**Một bean manager và một bean template cùng tham chiếu một bean nguồn kết nối** là dấu hiệu đúng về mặt wiring. Tuy nhiên cần xác minh lời gọi đi qua proxy, transaction được kích hoạt và DAO thật sự dùng đúng template; chỉ có dependency injection đúng chưa đủ để kết luận hành vi runtime.

## 7. Ví dụ chạy được: kiểm tra cùng connection và rollback bằng Spring JDBC

Ví dụ này dùng Java 17+, Spring Boot 3.3.5 (Spring Framework 6.x), Maven và H2 in-memory. Mục tiêu là kiểm chứng **đồ thị JDBC bằng dữ liệu thực tế**, không dựa vào việc đọc annotation rồi suy đoán. Có đúng ba tệp; không cần tạo web server, không cần JPA hay R2DBC trong ví dụ chạy này.

Cấu trúc:

~~~text
tx-graph-demo/
├── pom.xml
└── src/main/java/example/txgraph/
    ├── TxGraphApplication.java
    └── TransferService.java
~~~

**Tệp `pom.xml`:**

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
    <artifactId>tx-graph-demo</artifactId>
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

**Tệp `src/main/java/example/txgraph/TxGraphApplication.java`:**

~~~java
package example.txgraph;

import java.util.LinkedHashMap;
import java.util.Map;
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
public class TxGraphApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxGraphApplication.class, args);
    }

    // Manager và JdbcTemplate nhận cùng DataSource bean của Spring Boot.
    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc, TransferService transfer) {
        return args -> {
            jdbc.execute("CREATE TABLE wallet (id INT PRIMARY KEY, balance INT NOT NULL)");
            jdbc.update("INSERT INTO wallet (id, balance) VALUES (?, ?)", 1, 100);
            jdbc.update("INSERT INTO wallet (id, balance) VALUES (?, ?)", 2, 50);

            System.out.println("Trước: " + balances(jdbc));

            try {
                transfer.move(1, 2, 20, true);
            } catch (IllegalStateException ex) {
                System.out.println("Rollback vì: " + ex.getMessage());
            }
            System.out.println("Sau rollback: " + balances(jdbc));

            transfer.move(1, 2, 20, false);
            System.out.println("Sau commit: " + balances(jdbc));
        };
    }

    private static Map<Integer, Integer> balances(JdbcTemplate jdbc) {
        return jdbc.query("SELECT id, balance FROM wallet ORDER BY id", rs -> {
            Map<Integer, Integer> rows = new LinkedHashMap<>();
            while (rs.next()) {
                rows.put(rs.getInt("id"), rs.getInt("balance"));
            }
            return rows;
        });
    }
}
~~~

**Tệp `src/main/java/example/txgraph/TransferService.java`:**

~~~java
package example.txgraph;

import java.sql.Connection;
import javax.sql.DataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    private final DataSource dataSource;
    private final JdbcTemplate jdbc;

    public TransferService(DataSource dataSource, JdbcTemplate jdbc) {
        this.dataSource = dataSource;
        this.jdbc = jdbc;
    }

    @Transactional
    public void move(int from, int to, int amount, boolean failAfterDebit) {
        Connection first = DataSourceUtils.getConnection(dataSource);
        try {
            Connection second = DataSourceUtils.getConnection(dataSource);
            try {
                System.out.println("Cùng connection: " + (first == second));
            } finally {
                DataSourceUtils.releaseConnection(second, dataSource);
            }

            int updated = jdbc.update(
                "UPDATE wallet SET balance = balance - ? WHERE id = ? AND balance >= ?",
                amount, from, amount
            );
            if (updated != 1) {
                throw new IllegalStateException("insufficient balance");
            }
            if (failAfterDebit) {
                throw new IllegalStateException("simulated failure");
            }
            updated = jdbc.update(
                "UPDATE wallet SET balance = balance + ? WHERE id = ?",
                amount, to
            );
            if (updated != 1) {
                throw new IllegalStateException("destination absent");
            }
        } finally {
            DataSourceUtils.releaseConnection(first, dataSource);
        }
    }
}
~~~

Chạy trong thư mục `tx-graph-demo` (cần JDK 17+ và Maven, Maven tự tải dependency nếu chưa có):

~~~bash
mvn spring-boot:run
~~~

Các dòng do chương trình in ra, **bỏ qua log khởi động Spring/Hikari**:

~~~text
Trước: {1=100, 2=50}
Cùng connection: true
Rollback vì: simulated failure
Sau rollback: {1=100, 2=50}
Cùng connection: true
Sau commit: {1=80, 2=70}
~~~

Giải thích dựa trên đồ thị:

1. `@SpringBootApplication` tạo Spring context; Boot cung cấp một `DataSource` H2 và `JdbcTemplate` dùng chính nguồn đó. Bean `transactionManager` được cấu hình rõ là `JdbcTransactionManager(dataSource)`.
2. `CommandLineRunner` gọi `transfer.move(...)` qua **bean do Spring inject**, nên transaction advice được áp dụng. Nếu thay bằng gọi trực tiếp qua `new TransferService(...)`, kết quả không còn chứng minh proxy transaction.
3. Hai lần `DataSourceUtils.getConnection(dataSource)` bên trong cùng transaction trả về cùng connection đã gắn với thread. Hai reference được release đúng cách; Spring không đóng sớm connection còn thuộc transaction.
4. `jdbc.update(...)` đi qua `JdbcTemplate` và `DataSourceUtils`, nên các UPDATE tham gia chính connection được manager điều khiển.
5. Lần đầu, lệnh trừ tiền thành công nhưng `IllegalStateException` thoát ra khỏi transactional method. Spring rollback, giữ nguyên hai số dư. `catch` nằm **ngoài service proxy**, không nuốt exception trước khi advice nhìn thấy.
6. Lần sau, hai UPDATE thành công và method trả về bình thường, manager commit. Cả hai số dư đổi đúng 20 đơn vị.

`first == second` là bằng chứng rõ cho connection mà **`DataSourceUtils` trả về trong giao dịch này**, không phải phép thử toàn diện cho mọi cấu hình pool/proxy; thêm một kiểm chứng quan trọng là thay đổi dữ liệu đã rollback/commit như dự kiến. Thử xóa `@Transactional` (chỉ trong project demo tạm) sẽ cho thấy tại sao không thể xem việc dùng cùng `DataSource` như bảo đảm tự động có transaction.

## 8. Ba đồ thị dễ bị nối nhầm

### Trường hợp A — manager và DAO dùng hai DataSource khác nhau

~~~text
Service @Transactional -> jdbcTxManager -> dataSourceMain -> connection #1
                  DAO -> jdbcTemplateAudit -> dataSourceAudit -> connection #2
~~~

Một transaction của `jdbcTxManager` chỉ quản lý connection mà manager đó phụ trách. Connection #2 không tự gia nhập transaction #1. Nếu lệnh qua #1 rollback nhưng #2 đã auto-commit, hệ thống có thể lưu nửa nghiệp vụ.

**Cách sửa:** quyết định rõ dữ liệu nào cần thuộc một transaction, inject đúng nguồn vào manager và mọi DAO tham gia. Nếu thật sự cần atomicity qua nhiều tài nguyên độc lập, thiết kế transaction coordinator tương ứng (ví dụ JTA/XA khi có hỗ trợ), hoặc dùng outbox/saga theo yêu cầu nghiệp vụ. Không giải quyết bằng cách đặt thêm `@Transactional` ở mọi method.

### Trường hợp B — R2DBC và JDBC cùng trỏ một database

~~~text
@Transactional với R2dbcTransactionManager
    -> ConnectionFactory -> R2DBC Connection

JdbcTemplate
    -> DataSource -> JDBC Connection
~~~

Hai connection thuộc **hai driver/API và hai transaction context khác nhau**. `R2dbcTransactionManager` không điều khiển JDBC `Connection`, và `JdbcTransactionManager` không điều khiển R2DBC `Connection`. Cùng database host/schema không làm chúng chia sẻ transaction. Kết hợp kiểu blocking và reactive cũng có rủi ro về scheduling/luồng thực thi.

**Cách sửa:** giữ phần việc cần atomicity trong cùng công nghệ/tài nguyên được manager hỗ trợ, hoặc thiết kế cơ chế phối hợp rõ ràng giữa hai hệ thống; không giả định một annotation bảo đảm atomicity xuyên cả hai.

### Trường hợp C — hai manager cùng loại, nhưng chọn nhầm

~~~text
@Transactional("ordersTx") -> ordersTx -> ordersDataSource
orderJdbcTemplate ----------> ordersDataSource

@Transactional("auditTx")  -> auditTx  -> auditDataSource
auditJdbcTemplate ----------> auditDataSource
~~~

Đây là cấu hình hoàn toàn hợp lệ nếu nghiệp vụ chấp nhận **hai giao dịch độc lập**. Nhưng khi service gọi cả hai DAO trong một method annotated `@Transactional("ordersTx")`, chỉ một annotation đó **không** khiến `auditDataSource` tham gia cùng commit. Thậm chí nếu cả hai manager dùng cùng một server DB, vẫn phải xem chúng đang quản lý connection/resource nào.

Khi có nhiều transaction manager, hãy đọc `@Transactional(transactionManager = "...")`, bean name/qualifier, cấu hình `TransactionManagementConfigurer` (nếu có), và bean factory được inject thực tế. Một trường hợp nguy hiểm là ứng dụng khởi động bình thường và test đường "happy path" qua hết, nhưng chỉ phát hiện không đồng bộ khi tạo lỗi giữa các UPDATE.

## 9. Cách vẽ/đọc đồ thị của một module thực tế

Với từng entrypoint service cần transaction, đi theo thứ tự sau:

1. **Tìm ranh giới:** method nào có `@Transactional`, `TransactionTemplate` hoặc `TransactionalOperator`? Có được gọi qua proxy/sử dụng operator đúng cách không?
2. **Xác định loại thực thi:** method trả giá trị đồng bộ/`void` hay trả `Mono`/`Flux`? Một `PlatformTransactionManager` phục vụ imperative; một `ReactiveTransactionManager` phục vụ reactive.
3. **Tìm manager thật:** bean name nào được chọn? Nếu nhiều manager, annotation/qualifier/primary/default resolver quyết định thế nào?
4. **Tìm factory:** manager tham chiếu đến `DataSource`, `ConnectionFactory` hay `EntityManagerFactory` nào? Có wrapper/proxy/routing factory không?
5. **Tìm mã truy cập:** repository/template/client của từng lệnh SQL sử dụng factory nào? Mã JDBC thuần dùng `DataSourceUtils` hay lại lấy connection trực tiếp?
6. **Xác định context đồng bộ hóa:** trong JDBC, nguồn và thread đã gắn đúng resource chưa? Trong R2DBC, pipeline có giữ subscriber context và không tự mở subscription rời không?
7. **Xác minh bằng failure test:** cố tình làm thất bại sau câu ghi đầu tiên; sau khi transaction đã kết thúc, đọc dữ liệu từ session khác để xác định cả hai thay đổi cùng commit hoặc cùng rollback.

Ví dụ bảng kiểm tra một service có hai DAO:

| Cạnh phải đối chiếu | Điều mong đợi | Dấu hiệu cần điều tra |
| --- | --- | --- |
| `Service -> transactionManager` | Manager đã chọn đúng công nghệ và nguồn | Mơ hồ khi nhiều manager; qualifier sai |
| `Manager -> factory` | Đúng bean nguồn tài nguyên | Trùng tên gần giống, nhiều pool cùng URL |
| `DAO -> template/client -> factory` | Cùng nguồn với manager nếu cần chung giao dịch | DAO dùng pool hoặc client khác |
| `Factory -> connection -> context` | Connection được Spring đồng bộ hóa | Raw `getConnection()` hoặc `create()` bỏ qua helper |
| `Scope -> completion` | Kết quả commit/rollback phù hợp yêu cầu | Exception bị nuốt, publisher không subscribe |
| `Cross-resource boundary` | Có thiết kế phối hợp nếu cần atomicity nhiều tài nguyên | Chỉ dùng một `@Transactional` cho nhiều pool |

### Quan sát runtime mà không sửa logic nghiệp vụ

Với JDBC imperative, có thể bật log của `org.springframework.transaction` và `org.springframework.jdbc.datasource` ở mức DEBUG cho môi trường thử nghiệm. Log thường cho biết việc tạo/tham gia giao dịch, acquire/release connection và commit/rollback, nhưng tùy implementation/version. Khi debug thủ công, `TransactionSynchronizationManager.isActualTransactionActive()` là một dấu hiệu có context giao dịch đang hoạt động trên thread; nó **không** chứng minh DAO dùng đúng `DataSource`. Khi cần, inspect `TransactionSynchronizationManager.getResource(dataSource)` trong công cụ debug để xem liên kết nguồn cụ thể; không nên đưa kiểm tra nội bộ này thành logic nghiệp vụ.

Với reactive, trace pipeline và điều kiện subscription, bật logging transaction/R2DBC ở môi trường test. Đừng áp dụng cùng cách dò `ThreadLocal` của JDBC để kết luận R2DBC không có transaction. Hãy ưu tiên **integration test gây lỗi sau bước ghi thứ nhất** và xác minh DB state; đó là kiểm chứng khách quan hơn việc chỉ nhìn log.

### Những ngộ nhận cần tránh

- `@Transactional` là metadata: nếu không có advice/manager hợp lệ hoặc self-invocation bỏ qua proxy, hành vi có thể khác mong đợi.
- `DataSource` và `ConnectionFactory` đều tạo "connection" nhưng thuộc hai SPI khác nhau; không inject thay thế cho nhau.
- `JdbcTemplate` và `DatabaseClient` là đối tượng có thể reuse, không có nghĩa một template/client giữ một connection cố định cho mọi request.
- `DataSourceTransactionManager` không tự nhìn thấy mọi pool trong `ApplicationContext`.
- `EntityManagerFactory` khác `EntityManager`: transaction JPA theo persistence context phù hợp, không đơn giản là "JpaTransactionManager trỏ thẳng JdbcTemplate".
- `flush` của JPA hoặc `rowsUpdated()`/`update()` chạy thành công không phải bằng chứng đã commit transaction ngoài cùng.
- `@Transactional(readOnly = true)` là chỉ dẫn/hint; mức độ enforce tùy manager, driver và database. Không dùng nó thay cho quyền truy cập read-only của DB.
- `REQUIRES_NEW` có thể dùng connection độc lập trong khi giao dịch ngoài bị suspend; không giả định hai scope này luôn là một connection.
- Thay đổi trong database transaction không tự hoàn tác email, HTTP call hay message gửi ngoài nguồn giao dịch; cần mô hình tích hợp như outbox nếu yêu cầu nhất quán.

## 10. Bài tập đọc đồ thị và dự đoán kết quả

**Bài tập 1 — cùng DataSource:** Một service `@Transactional("mainTx")` gọi hai DAO. `mainTx` và cả hai `JdbcTemplate` dùng cùng bean `mainDataSource`; method được gọi qua proxy. DAO thứ nhất cập nhật A, DAO thứ hai ném `IllegalStateException` ra ngoài service. Dự đoán kết quả: với propagation mặc định `REQUIRED`, hai DAO cùng tham gia một transaction, nên cả hai thay đổi còn nằm trong transaction được rollback. Xác nhận bằng integration test.

**Bài tập 2 — khác DataSource:** Giữ service như trên nhưng DAO thứ hai dùng `auditDataSource` và tự auto-commit. Dự đoán kết quả: rollback của `mainTx` không phải bảo đảm đảo ngược thay đổi qua `auditDataSource`. Vẽ lại đồ thị bằng cách thêm connection thứ hai để thấy chỗ giao dịch bị tách.

**Bài tập 3 — Publisher không subscribe:** Một reactive service trả về `Mono<Void>` được gắn `@Transactional("r2dbcTx")`, nhưng caller bỏ qua đối tượng trả về mà không subscribe. Dự đoán: pipeline không được thực thi, nên thao tác DB và transaction reactive thông thường không bắt đầu.

**Bài tập 4 — JPA và JDBC:** Một JPA repository và một `JdbcTemplate` cùng nhìn thấy một URL DB. Có thể kết luận cả hai chung transaction do `JpaTransactionManager` quản lý không? **Không**. Cần kiểm tra provider, `JpaDialect`, `EntityManagerFactory`, `DataSource`, cách lấy connection và hoạt động thực tế khi rollback.

## 11. Ghi nhớ mô hình

**Mô hình JDBC:** `@Transactional` → `TransactionInterceptor` → `JdbcTransactionManager`/`DataSourceTransactionManager` → **`DataSource`** ↔ `DataSourceUtils` ← `JdbcTemplate` ← DAO.

**Mô hình R2DBC:** `@Transactional` hoặc `TransactionalOperator` → **`R2dbcTransactionManager` → `ConnectionFactory`** ↔ `ConnectionFactoryUtils` ← `DatabaseClient` ← reactive DAO; gắn với **Reactor subscriber Context**.

**Mô hình JPA:** `@Transactional` → **`JpaTransactionManager` → `EntityManagerFactory`** ↔ `EntityManager` ← JPA repository; JPA provider dùng JDBC `DataSource` bên dưới.

Một đồ thị transaction đúng cần trả lời được cả ba câu: **manager quản lý factory nào; mã truy cập dữ liệu dùng factory nào; và connection nào thực sự chịu commit/rollback?** Chỉ khi ba câu trả lời khớp trong giới hạn transaction manager được hỗ trợ mới có cơ sở tin rằng thao tác dữ liệu sẽ cùng commit hoặc rollback.

## Tài liệu tham khảo chính thức

- Spring Framework — [Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html).
- Spring Framework — [Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html).
- Spring Framework — [Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html).
- Spring Framework — [Controlling JDBC Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html).
- Spring Framework — [Synchronizing Resources with Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html).
- Spring Framework — [Data Access with R2DBC](https://docs.spring.io/spring-framework/reference/data-access/r2dbc.html).
- Spring Framework — [Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html).
