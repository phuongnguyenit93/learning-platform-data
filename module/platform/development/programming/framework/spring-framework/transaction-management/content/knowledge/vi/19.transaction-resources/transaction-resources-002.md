# DataSourceUtils, EntityManagerUtils và các hàm truy cập có nhận biết giao dịch

> **Spring Framework – Transaction Management → Tài nguyên gắn giao dịch.** Transaction do Spring quản lý không làm cho mọi JDBC `Connection` hoặc JPA `EntityManager` trong ứng dụng tự động sử dụng chung một resource. Muốn dữ liệu được commit/rollback cùng nhau, mã truy cập phải lấy **đúng tài nguyên đang gắn với transaction**. Bài này giải thích `DataSourceUtils`, utility JPA tương ứng, `TransactionSynchronizationManager` và các abstraction như `JdbcTemplate`, `@PersistenceContext`, `SharedEntityManagerCreator`. Cuối bài là ví dụ Java 17+ với Spring JDBC và H2.

## 1. Mục tiêu

Học xong, bạn cần làm được các việc sau:

1. Mô tả logical transaction scope, physical transaction, connection/entity manager và resource binding.
2. Giải thích vì sao `DataSourceUtils.getConnection(ds)` tham gia transaction, còn `ds.getConnection()` trên pool thông thường có thể lấy connection khác.
3. Dùng đúng cặp `getConnection`/`releaseConnection` và không vô tình đóng connection mà manager đang giữ.
4. Hiểu `JdbcTemplate` dùng cơ chế transaction-aware sau hậu trường.
5. Phân biệt tên thường gọi “EntityManagerUtils” với API thật của Spring là `EntityManagerFactoryUtils`, cùng `@PersistenceContext` và `SharedEntityManagerCreator`.
6. Chẩn đoán `TransactionSynchronizationManager` mà không tự bind/unbind resource trong business code.
7. Tránh sai transaction manager, datasource, thread, proxy và lifecycle khi trộn JDBC/JPA.
8. Chạy demo có thể kiểm chứng commit, rollback từ exception, explicit rollback-only, cùng đường JDBC được gọi ngoài transaction.

## 2. Chú ý tên lớp EntityManagerUtils

Trong **Spring Framework 6.2**, class tiện ích JPA chính thức thuộc `org.springframework.orm.jpa` có tên **`EntityManagerFactoryUtils`**, không phải `org.springframework.orm.jpa.EntityManagerUtils`. Cụm “EntityManagerUtils” có thể dùng như cách diễn đạt tổng quát cho utilities thao tác EntityManager, nhưng **không phải tên import Spring 6.2**.

```java
// KHÔNG DÙNG: đoạn sau cố tình minh họa một import không hợp lệ.
import org.springframework.orm.jpa.EntityManagerUtils;

// CÁC API THỰC TẾ TRONG SPRING:
import org.springframework.orm.jpa.EntityManagerFactoryUtils;
import org.springframework.orm.jpa.SharedEntityManagerCreator;
import org.springframework.jdbc.datasource.DataSourceUtils;
```

Đây là ví dụ **minh họa lỗi import**, không phải source file biên dịch. Khi viết code ứng dụng JPA bình thường, Spring thường khuyên dùng `@PersistenceContext` hoặc Spring Data JPA repositories thay vì gọi utility class thủ công.

Bảng đúng tên và mục đích:

| Công nghệ | API | Mục đích |
| --- | --- | --- |
| JDBC | `DataSourceUtils.getConnection(DataSource)` | Lấy connection có nhận biết thread-bound transaction resource |
| JDBC | `DataSourceUtils.releaseConnection(Connection,DataSource)` | Trả/đóng connection **chỉ khi phù hợp** với transaction binding |
| JDBC | `JdbcTemplate` | Đường truy cập JDBC cấp cao, tự quản lý connection/statement lifecycle |
| JDBC legacy | `TransactionAwareDataSourceProxy` | Làm plain `DataSource.getConnection()` của mã cũ có nhận biết Spring transactions |
| JPA | `EntityManagerFactoryUtils.getTransactionalEntityManager(emf)` | Lấy EntityManager theo Spring transaction synchronization; có thể trả `null` |
| JPA | `SharedEntityManagerCreator` | Tạo shared EntityManager proxy trỏ đến EntityManager phù hợp với transaction hiện hành |
| JPA thông thường | `@PersistenceContext` | Inject shared transaction-scoped EntityManager reference |
| Spring infrastructure | `TransactionSynchronizationManager` | Lưu resource map và synchronization metadata của imperative transaction context |

## 3. Resource binding giải quyết vấn đề gì?

Giả sử một use case cần ghi hai bảng rồi rollback nếu có lỗi:

```java
@Transactional
public void submitOrder() {
    jdbcTemplate.update("INSERT INTO orders ...");
    customAuditDao.insert(...);
    // Có thể ném lỗi sau hai lệnh INSERT.
}
```

Đây là **fragment nghiệp vụ**: SQL và tham số được rút gọn. Nếu `JdbcTemplate` dùng connection C1 đang nằm trong transaction T1, còn `customAuditDao` mở connection C2 với autocommit, rollback T1 chỉ hoàn tác dữ liệu của C1. Audit trên C2 có thể đã commit. **Một annotation không tự gom hai connection độc lập thành một physical transaction.**

Cơ chế đúng:

```text
                  Spring-managed service
                            |
                  @Transactional / txTemplate
                            |
                            v
                 PlatformTransactionManager
                            |
                       begin T1
                            |
                  ConnectionHolder(C1)
                            |
     TransactionSynchronizationManager.bindResource(ds, holder)
                            |
             +--------------+--------------+
             |                             |
       JdbcTemplate                      Custom DAO
             |                             |
       DataSourceUtils             DataSourceUtils.getConnection(ds)
             |                             |
             +------------- C1 ------------+
                            |
                       commit/rollback
                            |
              cleanup binding + release C1
```

Ở đây, `TransactionSynchronizationManager` cung cấp cơ chế resource map gắn với execution context của **imperative Spring transaction management**. Transaction manager sử dụng nó để bind/unbind resources và đồng bộ lifecycle. DAO **không** nên tự gọi `bindResource` hoặc tự giữ `ConnectionHolder` trong shared field.

### 3.1. Logical scope khác physical transaction

Nếu outer `@Transactional(REQUIRED)` gọi inner `@Transactional(REQUIRED)` qua proxy, Spring có thể tạo hai logical scopes **tham gia chung T1**, nên cùng connection/resource. Với `REQUIRES_NEW`, inner tạo T2 độc lập: manager có thể tạm treo binding T1, bind connection C2 cho T2, rồi khôi phục C1 khi inner kết thúc.

```text
outer REQUIRED: T1, bound C1
    |
    +-- inner REQUIRES_NEW:
    |       suspend T1
    |       bound C2 for T2
    |       DataSourceUtils.getConnection(ds) -> C2
    |       commit/rollback T2
    |       resume T1
    |
    +-- DataSourceUtils.getConnection(ds) -> C1
    +-- commit/rollback T1
```

**Resource-aware** nghĩa là lấy đúng resource **của scope hiện tại**, không phải “cùng một connection trên mọi phương thức của cùng một thread mãi mãi”.

## 4. DataSourceUtils.getConnection / doGetConnection

Import:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import org.springframework.jdbc.datasource.DataSourceUtils;
```

Gọi:

```java
Connection connection = DataSourceUtils.getConnection(dataSource);
```

Đây là fragment với biến `dataSource` được inject hoặc cấu hình từ Spring. Logic quan trọng:

1. Helper kiểm tra resource holder tương ứng với **key datasource** đang bind với transaction context.
2. Nếu holder có JDBC connection phù hợp, trả về connection bound này để câu SQL kế tiếp tham gia transaction.
3. Nếu chưa có, helper lấy connection từ datasource. Nếu synchronization đang active, Spring có thể đăng ký holder/callback để dùng lại và cleanup đúng khi scope kết thúc.
4. Khi không có Spring transaction/synchronization, helper vẫn có thể lấy connection bình thường cho một JDBC operation.

Hai biến thể:

- `getConnection(ds)`: chuyển các lỗi lấy connection thành Spring unchecked `CannotGetJdbcConnectionException`.
- `doGetConnection(ds)`: giữ lại `SQLException` từ JDBC cho caller xử lý.

Không đồng nhất `DataSourceUtils.getConnection(ds)` với `DriverManager.getConnection(url)`. Lời gọi `DriverManager` không tra resource map do Spring manager quản lý và thường tạo connection/transaction độc lập.

### 4.1. Connection có đang được Spring bound không?

```java
boolean transactional =
    DataSourceUtils.isConnectionTransactional(connection, dataSource);
```

Fragment. Trạng thái `true` phản ánh connection liên quan holder đang bind cho datasource, **không** chứng minh commit đã thành công hay không có database error. Để chẩn đoán đầy đủ, đối chiếu `TransactionSynchronizationManager.isActualTransactionActive()` và truy vấn dữ liệu sau transaction boundary.

### 4.2. Vì sao datasource identity quan trọng?

Spring transaction manager thường bind resource theo key `DataSource` tương ứng. Hai pools có cùng JDBC URL **không** có nghĩa cùng holder. Hai wrappers/proxies chưa cấu hình nhất quán cũng có thể dẫn đến việc code tìm không đúng resource đang bind.

Với nhiều datasources, phải xác định: `JdbcTemplate` dùng bean nào, `JdbcTransactionManager` được khởi tạo bằng bean nào, và custom DAO nhận bean nào. Chỉ dùng chung tên database không đủ.

## 5. DataSourceUtils.releaseConnection mới là cách trả đúng

Một JDBC DAO tự viết:

```java
Connection con = DataSourceUtils.getConnection(dataSource);
try (PreparedStatement statement =
        con.prepareStatement("INSERT INTO audit_events(id, text) VALUES (?, ?)")) {

    statement.setLong(1, 10L);
    statement.setString(2, "created");
    DataSourceUtils.applyTransactionTimeout(statement, dataSource);
    statement.executeUpdate();

} catch (SQLException ex) {
    throw new IllegalStateException("Insert failed", ex);
} finally {
    DataSourceUtils.releaseConnection(con, dataSource);
}
```

Đây là **fragment**, giả định có imports, datasource và bảng. Nếu connection đang được Spring giữ cho transaction, `releaseConnection` không làm physical connection đóng sai thời điểm; manager release ở phase phù hợp. Nếu chưa có transaction-bound connection, helper có thể close/trả connection về pool.

**Không nên dùng:**

```java
// Anti-pattern với connection do DataSourceUtils trả về:
try (Connection con = DataSourceUtils.getConnection(dataSource)) {
    // ...
}
```

Đây là fragment minh họa sai. Try-with-resources sẽ gọi `Connection.close()` trực tiếp, có thể đóng connection mà transaction manager còn đang sử dụng. Với `DataSourceUtils.getConnection`, hãy dùng `DataSourceUtils.releaseConnection` trong `finally`; statement và resultset vẫn nên dùng try-with-resources.

Tương tự, **không gọi `con.commit()`, `con.rollback()` hoặc `con.setAutoCommit(true)` tùy tiện** trên connection đã được manager bind, vì bạn có thể phá transaction boundary do Spring điều phối.

## 6. DataSourceUtils.applyTransactionTimeout

Custom JDBC code không dùng `JdbcTemplate` nên phải lưu ý transaction timeout khi tạo `Statement`/`PreparedStatement`:

```java
Connection c = DataSourceUtils.getConnection(dataSource);
try (PreparedStatement ps =
        c.prepareStatement("SELECT id FROM jobs WHERE status = ?")) {

    DataSourceUtils.applyTransactionTimeout(ps, dataSource);
    ps.setString(1, "READY");

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Đọc rows.
        }
    }
} finally {
    DataSourceUtils.releaseConnection(c, dataSource);
}
```

**Fragment:** cần catch/`throws SQLException`, imports và schema. Helper có thể áp dụng remaining transaction timeout vào statement khi được resource holder quản lý. `applyTimeout(statement,ds,timeout)` có thể dùng timeout khác, với transaction timeout được áp dụng theo semantics của Spring khi phù hợp.

Đừng nhầm Spring transaction timeout với database lock timeout, network socket timeout hay HTTP timeout: mỗi loại có phạm vi khác nhau. Không có utility nào bảo đảm ngắt mọi công việc chậm trong callback.

## 7. JdbcTemplate đã có transaction awareness

`JdbcTemplate` truy cập JDBC connection thông qua đường Spring-aware, dùng `DataSourceUtils`. Ví dụ:

```java
@Transactional
public void process() {
    jdbcTemplate.update(
            "INSERT INTO orders(id, label) VALUES (?, ?)",
            1, "new");
    jdbcTemplate.update(
            "INSERT INTO audit_events(id, text) VALUES (?, ?)",
            1, "order-created");
}
```

Fragment cần bean thực, schema và Spring AOP proxy. Hai lệnh thường dùng cùng physical transaction nếu manager và JdbcTemplate dùng đúng datasource. Không cần DAO gọi thêm `DataSourceUtils` bao quanh mỗi `jdbcTemplate.update(...)`.

### 7.1. Khi cần raw JDBC, ưu tiên ConnectionCallback

`JdbcTemplate.execute(ConnectionCallback<T>)` trao connection phù hợp cho code và quản lý acquisition/release:

```java
Integer count = jdbcTemplate.execute(connection -> {
    try (PreparedStatement ps =
            connection.prepareStatement("SELECT COUNT(*) FROM orders");
         ResultSet rs = ps.executeQuery()) {
        rs.next();
        return rs.getInt(1);
    }
});
```

Fragment cần imports và bảng orders. Nếu chỉ truy vấn count, `queryForObject` còn đơn giản hơn. Nhưng callback hữu ích khi cần JDBC APIs đặc thù và vẫn muốn Spring quản lý resource lifecycle.

### 7.2. NamedParameterJdbcTemplate

`NamedParameterJdbcTemplate` dùng `JdbcTemplate` phía dưới, nên có cùng nhận biết transaction khi cấu hình đúng datasource/manager:

```java
namedJdbc.update(
    "UPDATE inventory SET available=available-:n WHERE id=:id",
    Map.of("n", 2, "id", 101));
```

Đây là fragment cần biến `namedJdbc`, imports và schema. Dấu `:n`, `:id` là Spring named parameters được convert sang JDBC bind parameters.

## 8. Raw dataSource.getConnection() có luôn sai không?

Với một `DataSource` thông thường/pool, gọi trực tiếp:

```java
try (Connection raw = dataSource.getConnection()) {
    // Plain JDBC call.
}
```

không tự tra `ConnectionHolder` đang bound với Spring. Trong outer transaction T1, raw call có thể mượn connection khác C2 ở autocommit mode; dữ liệu của nó **không rollback** cùng T1.

Tuy nhiên, `dataSource` có thể là **`TransactionAwareDataSourceProxy`**; khi đó `getConnection()` của proxy có behavior nhận biết Spring transaction. Vì vậy khuyến nghị đúng là:

- Code mới: dùng `JdbcTemplate`, `NamedParameterJdbcTemplate`, `ConnectionCallback` hoặc `DataSourceUtils`.
- Legacy library buộc tự gọi `DataSource.getConnection` và `Connection.close`: cân nhắc trao `TransactionAwareDataSourceProxy` bao target datasource.
- Manager: phải điều phối **target/underlying datasource thích hợp**, không tạo một chain proxy ngẫu nhiên rồi kỳ vọng resource key tự khớp.

## 9. TransactionAwareDataSourceProxy khác LazyConnectionDataSourceProxy

| Proxy | Vai trò | Không làm |
| --- | --- | --- |
| `TransactionAwareDataSourceProxy` | Cho plain JDBC legacy code tham gia Spring-managed transaction khi gọi `getConnection`/`close` | Không tạo transaction nếu caller chưa có; không thay `PlatformTransactionManager` |
| `LazyConnectionDataSourceProxy` | Trì hoãn mượn physical JDBC connection cho đến lúc cần statement/metadata thực tế | Không biến một raw JDBC operation thành đúng transaction boundary khi cấu hình manager sai |
| `DataSource`/pool target | Cung cấp physical JDBC connections | Không tự biết Spring transaction map nếu không có bridge/utilities |

Fragment khởi tạo:

```java
DataSource legacyAware = new TransactionAwareDataSourceProxy(targetDataSource);
DataSource lazy = new LazyConnectionDataSourceProxy(targetDataSource);
```

Đây là fragment cần imports. Khi bọc nhiều tầng, tài liệu Spring khuyên đặt `TransactionAwareDataSourceProxy` **ngoài cùng** đối với code legacy. Sử dụng wrappers phải được kiểm tra bằng integration test: manager, application JDBC code và pool cần thống nhất resource identity.

## 10. TransactionSynchronizationManager lưu những gì?

Đây là Spring infrastructure cho imperative transaction context. Các API quan sát:

```java
boolean active =
        TransactionSynchronizationManager.isActualTransactionActive();

boolean sync =
        TransactionSynchronizationManager.isSynchronizationActive();

boolean bound =
        TransactionSynchronizationManager.hasResource(dataSource);

Object holder =
        TransactionSynchronizationManager.getResource(dataSource);
```

**Fragment:** cần imports và datasource bean. Một `ConnectionHolder` có thể được bind bằng key datasource; một `EntityManagerHolder` có thể được bind bằng key `EntityManagerFactory`.

**Hai flags không giống nhau:**

- `isActualTransactionActive()`: Spring đang đánh dấu một actual transaction trong execution context.
- `isSynchronizationActive()`: resource synchronization callbacks đang active. Một `SUPPORTS` scope ở cấu hình nhất định có thể có synchronization dù không có actual physical transaction.

Đừng thấy `isSynchronizationActive()==true` rồi kết luận mọi SQL trong method sẽ rollback cùng nhau.

Các đặc tính có thể đọc:

```java
String name =
        TransactionSynchronizationManager.getCurrentTransactionName();

Integer isolation =
        TransactionSynchronizationManager
                .getCurrentTransactionIsolationLevel();

boolean readOnly =
        TransactionSynchronizationManager
                .isCurrentTransactionReadOnly();
```

Những method này dùng cho introspection. `isolation == null` thường nghĩa là chưa có Spring isolation override, không phải JDBC không có isolation. `readOnly` là hint/cấu hình transaction, không phải security policy bảo đảm cấm mọi ghi.

### 10.1. Không tự bindResource trong DAO

`TransactionSynchronizationManager.bindResource(key,value)` và `unbindResource(key)` là API infrastructure. Một DAO bình thường **không nên** tự bind physical connection hoặc EntityManager để “ép transaction”, vì có thể làm hỏng holder lifecycle, gây leak hoặc ghi đè resource đang bound. Cứ để manager và Spring templates xử lý.

### 10.2. Thread context và @Async

Imperative transaction binding thường là **thread-bound**. Chạy `@Async`, `CompletableFuture` hoặc executor thread khác không tự đem JDBC Connection/JPA EntityManager của transaction ngoài theo. Không cache `Connection`/physical `EntityManager` trong singleton rồi share giữa threads.

Reactive/R2DBC dùng reactive transaction context và các abstractions như `ConnectionFactoryUtils`, `TransactionalOperator`; không sử dụng `DataSourceUtils` (JDBC) để quản lý R2DBC transactions.

## 11. EntityManagerFactoryUtils trong Spring JPA

Tên import chính xác:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import org.springframework.orm.jpa.EntityManagerFactoryUtils;
```

Utility method:

```java
EntityManager em =
        EntityManagerFactoryUtils.getTransactionalEntityManager(emf);
```

Đây là **fragment** cần `emf` đã được cấu hình với `JpaTransactionManager`/persistence unit phù hợp. `getTransactionalEntityManager(...)` có thể trả **null** khi không có thread-bound EntityManager/synchronization phù hợp. Vì vậy không dereference vô điều kiện:

```java
EntityManager em =
        EntityManagerFactoryUtils.getTransactionalEntityManager(emf);

if (em == null) {
    throw new IllegalStateException(
            "No transaction-synchronized EntityManager available");
}
em.persist(entity);
```

Đây là fragment: `entity` phải được quản lý bởi đúng persistence unit, và ghi dữ liệu JPA cần actual transaction thích hợp.

Đặc biệt **không `em.close()`** nếu `em` đang được Spring transaction manager bind. Cleanup resource trong trường hợp này thuộc manager/synchronization infrastructure.

### 11.1. Các methods đáng biết

| `EntityManagerFactoryUtils` method | Ý nghĩa |
| --- | --- |
| `getTransactionalEntityManager(emf)` | Lấy EntityManager có nhận biết transaction; nullable |
| `doGetTransactionalEntityManager(...)` | Low-level variant có thể giữ nguyên `PersistenceException` |
| `applyTransactionTimeout(query,emf)` | Áp dụng timeout phù hợp lên JPA `Query` |
| `closeEntityManager(em)` | Helper đóng application-managed EntityManager khi caller thật sự sở hữu |
| `convertJpaAccessExceptionIfPossible(ex)` | Chuyển một số JPA exceptions thành Spring `DataAccessException`; có thể trả null |
| `findEntityManagerFactory(beanFactory,unitName)` | Tìm persistence unit/EMF theo bean factory |

Javadoc mô tả `EntityManagerFactoryUtils` chủ yếu dành cho framework internals/integrations. Với application thường ngày, `@PersistenceContext` và Spring Data JPA repository đơn giản, ít lỗi hơn.

## 12. @PersistenceContext và SharedEntityManagerCreator

Trong Spring JPA, field injected:

```java
@Repository
public class CustomerDao {
    @PersistenceContext
    private EntityManager em;

    public Customer find(long id) {
        return em.find(Customer.class, id);
    }
}
```

Đây là JPA fragment, cần imports và entity `Customer`. Với mặc định `PersistenceContextType.TRANSACTION`, injected reference là **shared transactional EntityManager proxy**; nó delegate đến actual EntityManager phù hợp với transaction hiện tại.

**Không nhầm proxy với physical EntityManager:**

- `EntityManagerFactory` nhìn chung là thread-safe để dùng chung.
- Physical `EntityManager`/persistence context không thread-safe để chia sẻ giữa concurrent requests.
- Shared proxy mà Spring inject có thể lưu như một field trong singleton bean vì nó chọn actual transactional EntityManager phù hợp với từng execution.

Nếu cần định nghĩa proxy bằng Java config:

```java
@Bean("sharedEntityManager")
static EntityManager sharedEntityManager(EntityManagerFactory emf) {
    return SharedEntityManagerCreator.createSharedEntityManager(emf);
}
```

Đây là fragment, cần import `org.springframework.orm.jpa.SharedEntityManagerCreator`. Trong các services, ưu tiên `@PersistenceContext` khi muốn API JPA thuần.

### 12.1. emf.createEntityManager() là trường hợp khác

```java
EntityManager manual = emf.createEntityManager();
try {
    // Manual/application-managed EntityManager.
} finally {
    manual.close();
}
```

Đây là fragment. `emf.createEntityManager()` tạo EntityManager mà application tự sở hữu lifecycle; **không** tự biến thành cùng transactional EntityManager mà `JpaTransactionManager` đã bound. Khi cần phối hợp, phải thiết kế transaction synchronization/JTA/provider integration đúng, không tự suy từ cùng EMF.

### 12.2. EXTENDED persistence context có rủi ro thread safety

`@PersistenceContext(type = PersistenceContextType.EXTENDED)` có lifecycle vượt một transaction, không phải lựa chọn để “dùng lâu hơn cho mọi singleton service”. Physical extended EntityManager không thread-safe, nên chỉ hợp lý với stateful component có lifecycle/ownership rõ và không có concurrent access không kiểm soát.

## 13. JpaTransactionManager và JDBC có thể kết hợp?

Với cấu hình phù hợp, `JpaTransactionManager` có thể expose JDBC connection từ transactional EntityManager cho `JdbcTemplate`/`DataSourceUtils` sử dụng trên **cùng datasource**. Điều này phụ thuộc JPA provider/`JpaDialect`, `EntityManagerFactory`, datasource và cấu hình transaction manager.

```text
                @Transactional service
                          |
                JpaTransactionManager
                          |
                EntityManagerFactory
                          |
          transaction-bound EntityManager
                          |
                  JPA persistence context
                          |
            JDBC Connection có thể expose
                  /                 \
                 /                   \
      JPA @PersistenceContext       JdbcTemplate
                 \                   /
                  cùng physical transaction
```

Đừng khẳng định mọi provider và mọi datasources đều hỗ trợ một cách tự động. Trong hỗn hợp JDBC/JPA:

- JPA thay đổi entity nhưng chưa flush: JDBC query có thể chưa thấy INSERT/UPDATE vì SQL chưa được gửi xuống database.
- JDBC update trực tiếp: first-level JPA cache có thể giữ managed entity cũ, cần `flush`/`refresh`/`clear` theo use case.
- Bulk/native SQL có thể không tự thực thi optimistic `@Version` updates như entity manager bình thường.
- `em.flush()` không phải `commit()`; physical transaction khác chưa nhất thiết nhìn thấy thay đổi.
- Lỗi JDBC/JPA có thể khiến transaction rollback-only; catch exception không làm transaction trở nên committable.

Với **hai** independent datasources, một local manager không tạo distributed atomicity. Cần thiết kế JTA/XA, saga hoặc transactional outbox theo yêu cầu nghiệp vụ.

## 14. Java 17+ runnable demo: JDBC template + DataSourceUtils trong cùng transaction

Demo dùng Spring Framework **6.2.8**, Java 17+, Maven và H2 in-memory **2.3.232**, không cần Spring Boot. Đây là chương trình **JDBC runnable độc lập**; ví dụ JPA ở trên là các fragments vì muốn chạy JPA phải cấu hình provider và persistence unit riêng.

Bốn kịch bản:

1. Service `@Transactional` ghi một row bằng `JdbcTemplate` và một row qua DAO dùng `DataSourceUtils`: cả hai commit.
2. Hai DAO ghi dữ liệu nhưng service ném `RuntimeException`: cả hai rows rollback.
3. Service gọi `setRollbackOnly()` rồi trả result bình thường: cả hai rows rollback.
4. Gọi DAO dùng `DataSourceUtils` ngoài transaction: helper lấy connection, trả về pool/close đúng lifecycle; với H2 autocommit default, row được lưu.

### 14.1. Cấu trúc

```text
resource-aware-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/
                └── learning/
                    └── ResourceAwareDemo.java
```

### 14.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
            https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>dev.learning</groupId>
    <artifactId>resource-aware-demo</artifactId>
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
                <configuration><release>17</release></configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>dev.learning.ResourceAwareDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 14.3. src/main/java/dev/learning/ResourceAwareDemo.java

```java
package dev.learning;

import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceUtils;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public final class ResourceAwareDemo {

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {
        @Bean
        DataSource dataSource() {
            JdbcDataSource ds = new JdbcDataSource();
            ds.setURL("jdbc:h2:mem:resource_aware;DB_CLOSE_DELAY=-1");
            ds.setUser("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        PlatformTransactionManager transactionManager(DataSource ds) {
            return new JdbcTransactionManager(ds);
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        RawJdbcDao rawJdbcDao(DataSource ds) {
            return new RawJdbcDao(ds);
        }

        @Bean
        BusinessService businessService(
                JdbcTemplate jdbc, RawJdbcDao dao, DataSource ds) {
            return new BusinessService(jdbc, dao, ds);
        }
    }

    // Custom JDBC code: đúng pattern get + release.
    public static class RawJdbcDao {
        private final DataSource dataSource;

        public RawJdbcDao(DataSource dataSource) {
            this.dataSource = dataSource;
        }

        public boolean insert(int id, String label) {
            Connection con =
                    DataSourceUtils.getConnection(dataSource);

            try (PreparedStatement ps = con.prepareStatement(
                    "INSERT INTO records(id, label) VALUES(?, ?)")) {
                DataSourceUtils.applyTransactionTimeout(
                        ps, dataSource);

                ps.setInt(1, id);
                ps.setString(2, label);
                ps.executeUpdate();

                return DataSourceUtils.isConnectionTransactional(
                        con, dataSource);
            } catch (SQLException e) {
                throw new IllegalStateException(
                        "Insert failed for id=" + id, e);
            } finally {
                DataSourceUtils.releaseConnection(con, dataSource);
            }
        }
    }

    public static class BusinessService {
        private final JdbcTemplate jdbc;
        private final RawJdbcDao dao;
        private final DataSource dataSource;

        public BusinessService(
                JdbcTemplate jdbc, RawJdbcDao dao, DataSource ds) {
            this.jdbc = jdbc;
            this.dao = dao;
            this.dataSource = ds;
        }

        @Transactional
        public void succeed() {
            System.out.println(
                    "inside.active="
                    + TransactionSynchronizationManager
                            .isActualTransactionActive());
            System.out.println(
                    "inside.datasourceBound="
                    + TransactionSynchronizationManager
                            .hasResource(dataSource));

            jdbc.update(
                    "INSERT INTO records(id, label) VALUES(?, ?)",
                    1, "jdbc");

            boolean bound = dao.insert(2, "datasource-utils");
            System.out.println(
                    "inside.customConnectionTransactional=" + bound);
        }

        @Transactional
        public void fail() {
            jdbc.update(
                    "INSERT INTO records(id, label) VALUES(?, ?)",
                    3, "will rollback jdbc");
            dao.insert(4, "will rollback custom");
            throw new IllegalStateException("simulated failure");
        }

        @Transactional
        public String reject() {
            jdbc.update(
                    "INSERT INTO records(id, label) VALUES(?, ?)",
                    5, "rollback-only jdbc");
            dao.insert(6, "rollback-only custom");

            TransactionAspectSupport.currentTransactionStatus()
                    .setRollbackOnly();
            return "rejected";
        }
    }

    private static int count(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM records", Integer.class);
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             Config.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute("""
                    CREATE TABLE records (
                        id INT PRIMARY KEY,
                        label VARCHAR(80) NOT NULL
                    )
                    """);

            BusinessService service =
                    context.getBean(BusinessService.class);

            service.succeed();
            System.out.println("afterSuccess.rows=" + count(jdbc));

            try {
                service.fail();
            } catch (IllegalStateException ex) {
                System.out.println(
                        "failure.caught=" + ex.getMessage());
            }
            System.out.println("afterFailure.rows=" + count(jdbc));

            System.out.println(
                    "rollbackOnly.result=" + service.reject());
            System.out.println(
                    "afterRollbackOnly.rows=" + count(jdbc));

            RawJdbcDao dao = context.getBean(RawJdbcDao.class);
            System.out.println(
                    "outside.customConnectionTransactional="
                    + dao.insert(7, "outside"));

            System.out.println("afterOutside.rows=" + count(jdbc));
            System.out.println(
                    "outside.active="
                    + TransactionSynchronizationManager
                            .isActualTransactionActive());
            System.out.println(
                    "outside.datasourceBound="
                    + TransactionSynchronizationManager
                            .hasResource(context.getBean(DataSource.class)));
        }
    }
}
```

### 14.4. Lệnh chạy và stdout kỳ vọng

Trong thư mục `resource-aware-demo`, cần JDK 17+, Maven 3.x và Internet khi tải Maven dependencies lần đầu:

```bash
mvn -q clean compile exec:java
```

Các dòng do **chính chương trình** in ra (log Maven/Spring có thể khác tùy môi trường):

```text
inside.active=true
inside.datasourceBound=true
inside.customConnectionTransactional=true
afterSuccess.rows=2
failure.caught=simulated failure
afterFailure.rows=2
rollbackOnly.result=rejected
afterRollbackOnly.rows=2
outside.customConnectionTransactional=false
afterOutside.rows=3
outside.active=false
outside.datasourceBound=false
```

### 14.5. Giải thích kết quả

**Commit thành công:** Spring `JdbcTransactionManager` bắt đầu transaction, bind `ConnectionHolder` cho cùng `DataSource`. `JdbcTemplate` insert ID=1, rồi DAO `DataSourceUtils` insert ID=2. Connection trong custom DAO được nhận diện là đang transactional; khi service return, T1 commit, có 2 rows.

**Unchecked exception:** Service ghi ID=3 qua JdbcTemplate và ID=4 qua custom DAO, rồi ném `IllegalStateException`. Interceptor yêu cầu rollback T2. Hai rows đều mất; count vẫn 2. Điều này kiểm chứng custom DAO đã dùng **đúng transaction resource**.

**Explicit rollback-only:** Service ghi IDs 5 và 6 rồi đánh dấu rollback-only; method trả `"rejected"` bình thường. Transaction manager rollback vì root scope yêu cầu, nên count vẫn 2. Không được hiểu một return bình thường là dữ liệu đã commit.

**Ngoài transaction:** DAO tự lấy connection, thao tác chạy với H2 autocommit mặc định; helper release sau statement. `isConnectionTransactional` là false và count tăng thành 3. Đây không phải “Spring tự mở một transaction lớn” cho external caller; chỉ là JDBC operation ngoài transaction-scope của service.

**Điều kiện quan trọng:** `BusinessService` phải là Spring bean và method được gọi qua proxy; `DataSource` được inject cho manager, JdbcTemplate và DAO là **cùng bean**. Ví dụ chạy tuần tự, không kiểm thử concurrency. Output được suy ra từ semantics API/DB; cần chạy Maven để xác nhận thực nghiệm.

## 15. Thí nghiệm có chủ đích

**Thử A — Thay DAO DataSourceUtils bằng raw ds.getConnection().** Sử dụng connection mới với `try-with-resources` (và cleanup statements đầy đủ). Khi service fail, custom JDBC insert có thể tự commit khác transaction của JdbcTemplate. Đây là một test **cố ý mô phỏng lỗi**, không dùng production code.

**Thử B — Dùng TransactionAwareDataSourceProxy cho legacy DAO.** Legacy code chỉ biết plain `getConnection()/close()` có thể tham gia Spring transaction, nếu proxy wrapping/manager target được cấu hình đúng. So sánh rows sau failure.

**Thử C — Đặt `RawJdbcDao` dùng datasource khác.** Spring manager vẫn điều phối dsA nhưng custom insert trên dsB có thể không rollback. Nếu hai H2 databases khác nhau, phải tạo schema ở mỗi bên trước khi test.

**Thử D — Bỏ `setRollbackOnly()` trong `reject()`.** IDs 5 và 6 sẽ commit nếu không có exception/resource failure. Kết quả `"rejected"` vẫn có thể được trả ra, nhưng data state khác; business semantics phải được kiểm soát.

**Thử E — Dùng REQUIRES_NEW cho một method riêng.** Quan sát manager tạm suspend outer connection, inner mượn connection độc lập và có thể commit dù outer rollback; nhớ kiểm tra pool sizing và lock waits.

**Thử F — In `TransactionSynchronizationManager.isSynchronizationActive()`.** So sánh với `isActualTransactionActive()` trong scopes khác nhau như `SUPPORTS`; đừng đánh đồng hai flags.

## 16. Các lỗi hay gặp khi triển khai

| Lỗi | Hậu quả | Sửa đúng |
| --- | --- | --- |
| Import `EntityManagerUtils` từ Spring ORM | Không tồn tại class này trong Spring 6.2 | Dùng `EntityManagerFactoryUtils` hoặc `@PersistenceContext` |
| Gọi plain `dataSource.getConnection()` từ normal pool trong transaction | Có thể autocommit ngoài T1 | JdbcTemplate/DataSourceUtils/transaction-aware proxy đúng cấu hình |
| Gọi `Connection.close()` trên connection từ `DataSourceUtils` | Có thể đóng resource đang bị manager giữ | `DataSourceUtils.releaseConnection` |
| Không release sau `getConnection` | Leak/reference count/cleanup sai | `finally` release đúng một lần cho mỗi acquisition |
| Manager dsA, DAO dsB | Rollback không bảo vệ statements của dsB | Đồng nhất datasource/manager, dùng qualifiers |
| Tự bind/unbind `ConnectionHolder` trong business code | Xung đột lifecycle/resource map | Để manager và Spring framework quản lý |
| Xem `isSynchronizationActive` là active physical transaction | Suy luận sai về atomicity | Kết hợp `isActualTransactionActive` và DB assertions |
| Cầm physical `EntityManager` trong singleton | Không thread-safe, stale persistence context | Dùng shared proxy / @PersistenceContext |
| Tự close injected shared EntityManager | Hỏng lifecycle hoặc proxy behavior | Không close; manager cleanup |
| Dùng `emf.createEntityManager()` rồi tưởng đã join transaction | Có thể dùng context riêng, transaction khác hoặc ngoài transaction | Shared proxy/đúng JPA integration |
| Trộn JPA và JDBC mà không flush/refresh | JDBC/managed entities có thể nhìn khác trạng thái | Đồng bộ thứ tự flush, cache và resource manager |
| Chuyển JDBC connection qua `@Async` | Không còn đúng thread-bound transaction context | Tạo transaction mới trong worker |
| Dùng REQUIRES_NEW để sửa mọi rollback | Independent commit ngoài ý muốn, thêm connection/locks | Chọn propagation theo business invariant |
| Chỉ kiểm tra log thay vì dữ liệu sau transaction | Kết luận commit/rollback sai | Integration test với query độc lập sau boundary |

## 17. Checklist kiểm thử tích hợp

- [ ] Ghi qua `JdbcTemplate` và custom `DataSourceUtils` cùng một transaction: cả hai commit.
- [ ] Gây `RuntimeException` sau hai writes: cả hai rollback.
- [ ] Gọi `setRollbackOnly()`: method có thể return bình thường nhưng DB vẫn rollback.
- [ ] Custom DAO ngoài transaction: resource được release, không leak.
- [ ] Khi dùng legacy code, `TransactionAwareDataSourceProxy` cho phép tham gia transaction nếu đúng wrappers/target.
- [ ] Dùng datasource khác: test phải phát hiện SQL nằm ngoài manager resource.
- [ ] `JpaTransactionManager` và `JdbcTemplate` trên cùng datasource: xác minh provider/dialect/flush behavior.
- [ ] `@PersistenceContext` dùng shared proxy; physical `EntityManager` không bị share giữa threads.
- [ ] `REQUIRES_NEW` suspend/resume binding đúng, pool không cạn, inner không tranh row lock do outer giữ.
- [ ] Các kiểm tra thực hiện **sau** commit/rollback và ngoài test-managed transaction có thể rollback thêm.

**Lưu ý Spring TestContext:** Một test method tự gắn `@Transactional` có thể được framework rollback cuối test, làm che khả năng commit thực tế của service. Để chứng minh commit, thiết kế transaction boundary và phép đọc data độc lập cho phù hợp, hoặc dùng `TestTransaction` có chủ đích.

## 18. Câu hỏi tự kiểm tra

**1. `DataSourceUtils.getConnection(ds)` có luôn mở physical connection mới không?**  
Không. Nếu Spring có transaction-bound connection cho datasource đó, helper có thể trả connection đang bind. Nếu không, nó yêu cầu connection từ datasource.

**2. Vì sao `JdbcTemplate` không cần custom code gọi `DataSourceUtils`?**  
Vì JdbcTemplate thực hiện acquisition/release transaction-aware phía sau; application code nên dùng abstraction thay vì tự quản lý lifecycle.

**3. `DataSourceUtils.releaseConnection` có luôn đóng connection không?**  
Không. Nó không đóng ngay connection thuộc transaction được Spring quản lý; cleanup do manager thực hiện đúng thời điểm.

**4. Khi nào nên dùng `TransactionAwareDataSourceProxy`?**  
Khi code/library cũ chỉ nhận `DataSource` chuẩn và tự gọi `getConnection()/close()`; đây là bridge cho legacy JDBC.

**5. `LazyConnectionDataSourceProxy` có chức năng giống proxy trên không?**  
Không. Lazy proxy trì hoãn physical connection acquisition; transaction-aware proxy cho plain JDBC code tham gia transaction.

**6. `EntityManagerUtils` có phải Spring ORM class name đúng?**  
Không trong Spring 6.2. Class utility tương ứng là `EntityManagerFactoryUtils`; application thường dùng `@PersistenceContext` hoặc Spring Data JPA.

**7. `getTransactionalEntityManager(emf)` luôn trả EntityManager không null?**  
Không. Method có thể trả null nếu thiếu transaction/synchronization context thích hợp. Write JPA cần actual transaction phù hợp.

**8. Vì sao injected `@PersistenceContext EntityManager` có thể được dùng trong singleton nhưng physical EntityManager không thread-safe?**  
Vì injected reference thường là shared proxy delegate đến actual EntityManager của execution context hiện tại; đó không phải một physical EntityManager cố định share giữa mọi threads.

**9. Nếu manager mở T1, inner REQUIRES_NEW thì DataSourceUtils trả C1 hay C2?**  
Nó dùng binding của inner T2 (thường C2) trong khi T1 được suspend; khi inner kết thúc, resource T1 được resume.

**10. `isConnectionTransactional==true` có chứng minh đã commit?**  
Không. Nó phản ánh resource binding, không phải outcome; DB commit/rollback phải được kiểm tra sau transaction boundary.

**11. Nếu JDBC URL giống nhau nhưng DAO dùng một pool khác, có tự tham gia cùng transaction không?**  
Không được giả định. Cần resource key/manager/datasource thống nhất; hai pools khác nhau có thể tạo các connections khác nhau và transactions khác nhau.

**12. Có thể dùng `DataSourceUtils` để quản lý R2DBC?**  
Không. DataSourceUtils là JDBC imperative utility; reactive stack có `ConnectionFactoryUtils`/`TransactionalOperator` và reactive context.

## 19. Kết luận

**Đúng transaction không chỉ là đúng annotation**. Code cũng phải **lấy và trả đúng JDBC/JPA resource**:

- `DataSourceUtils` hỗ trợ custom JDBC code tra transaction-bound connection và release an toàn.
- `JdbcTemplate` đã có transaction awareness; ưu tiên dùng nó cho code mới.
- `TransactionAwareDataSourceProxy` là bridge cho plain JDBC legacy code; `LazyConnectionDataSourceProxy` giải quyết vấn đề khác.
- JPA trong Spring dùng `EntityManagerFactoryUtils` (không phải một import `EntityManagerUtils` giả định), với `@PersistenceContext`/`SharedEntityManagerCreator` là đường truy cập khuyến nghị.
- `TransactionSynchronizationManager` quản lý resource map theo execution context; application DAO không nên tự bind/unbind.
- Transaction manager và data access phải dùng đúng datasource/persistence unit; `REQUIRES_NEW` có thể đổi resource binding và atomicity.
- Integration test phải kiểm tra **dữ liệu thực sự còn sau commit/rollback**, không chỉ flag, annotation hoặc connection object identity.

## 20. Tài liệu tham khảo

1. [Spring Framework 6.2 – JDBC Connections](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/connections.html) — `DataSourceUtils`, `TransactionAwareDataSourceProxy`, `LazyConnectionDataSourceProxy`.
2. [Spring Framework – Synchronizing Resources with Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html) — cách bind/reuse JDBC resources.
3. [Spring 6.2 – DataSourceUtils API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html) — `getConnection`, `releaseConnection`, `applyTransactionTimeout`.
4. [Spring 6.2 – TransactionSynchronizationManager API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html) — resource map, synchronization và transaction characteristics.
5. [Spring Framework 6.2 – JPA integration](https://docs.spring.io/spring-framework/reference/6.2/data-access/orm/jpa.html) — `@PersistenceContext`, shared EntityManager và transaction lifecycle.
6. [Spring 6.2 – EntityManagerFactoryUtils API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/orm/jpa/EntityManagerFactoryUtils.html) — JPA transactional utility và exception translation.
7. [Spring 6.2 – SharedEntityManagerCreator API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/orm/jpa/SharedEntityManagerCreator.html) — shared JPA proxy.
8. [Spring 6.2 – JpaTransactionManager API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/orm/jpa/JpaTransactionManager.html) — JPA manager và JDBC exposure.
9. [Spring 6.2 – TransactionAwareDataSourceProxy API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/datasource/TransactionAwareDataSourceProxy.html) — legacy JDBC adapter.
