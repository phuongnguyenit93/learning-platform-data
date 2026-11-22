# READ_UNCOMMITTED và giới hạn hỗ trợ thực tế trong Spring Transaction Management

## 1. Mục tiêu bài học

`READ_UNCOMMITTED` là mức cô lập (isolation level) yếu nhất trong bộ bốn mức thông dụng của chuẩn SQL. Về ý nghĩa lý thuyết, nó **cho phép một transaction đọc dữ liệu mà transaction khác chưa commit** — hiện tượng **dirty read**. Spring Framework có thể yêu cầu mức này bằng `@Transactional(isolation = Isolation.READ_UNCOMMITTED)` hoặc `TransactionDefinition.ISOLATION_READ_UNCOMMITTED`.

Nhưng một annotation **không bảo đảm** database sẽ cho phép đọc bẩn. Khả năng áp dụng còn phụ thuộc transaction manager, JDBC driver, DBMS/engine, propagation, transaction đang tồn tại, connection được sử dụng và cả thời điểm phép đọc diễn ra.

Sau bài này, bạn có thể:

1. Hiểu dirty read xảy ra thế nào và vì sao dữ liệu nhìn thấy có thể bị rollback ngay sau đó.
2. Phân biệt `READ_UNCOMMITTED` với `READ_COMMITTED`, `REPEATABLE_READ` và `SERIALIZABLE` theo các hiện tượng dirty read, non-repeatable read và phantom read.
3. Khai báo isolation trong Spring JDBC bằng `@Transactional`, `TransactionTemplate` hoặc XML, và biết khi nào cấu hình được áp dụng.
4. Kiểm tra `DatabaseMetaData.supportsTransactionIsolationLevel(...)` và `Connection.getTransactionIsolation()` nhưng **không nhầm metadata/setting với bằng chứng hành vi**.
5. Hiểu khác biệt thực tế: PostgreSQL coi `READ UNCOMMITTED` như `READ COMMITTED`; Oracle Database không cho dirty read; MySQL InnoDB, H2 và SQL Server có cơ chế hỗ trợ theo tài liệu sản phẩm.
6. Chạy một thử nghiệm Java 17+ có **writer giữ transaction chưa commit** và **hai reader sử dụng hai connection/transaction độc lập**; sau đó writer rollback để chứng minh dữ liệu từng được đọc nhưng không tồn tại ở trạng thái committed.
7. Tránh các anti-pattern: đọc từ cùng connection rồi kết luận dirty read; gọi self-invocation khiến Spring proxy không chạy; gắn isolation cho inner `REQUIRED` trong khi outer đã mở transaction; dùng dirty read cho kiểm tra số dư, thanh toán hoặc dữ liệu nghiệp vụ quyết định.

**Phạm vi:** Bài tập trung vào Spring Framework transaction management **đồng bộ với JDBC**, còn JPA, JTA, reactive và các DBMS khác được đề cập ở phần giới hạn. Không khuyến nghị bật `READ_UNCOMMITTED` để tăng tốc trước khi có yêu cầu nghiệp vụ và đo đạc cụ thể.

## 2. Dirty read là gì?

Giả sử tài khoản/bảng `price_quote` có giá đã commit là 100. Hai transaction độc lập hoạt động đồng thời:

```text
Thời điểm          Transaction A (writer)         Transaction B (reader)
---------          ----------------------         ----------------------
T0                 BEGIN                           BEGIN READ_UNCOMMITTED
T1                 UPDATE price = 900
                   (CHƯA COMMIT)
T2                                                 SELECT price -> 900 (*)
T3                 ROLLBACK
T4                                                 Nếu đọc lại -> có thể là 100
T5                 --                              COMMIT/END
```

`(*)` là **dirty read**: B đọc giá trị 900 do A viết nhưng A chưa commit. A rollback nên 900 **chưa từng trở thành giá trị committed**. Một quyết định nghiệp vụ được đưa ra dựa trên 900 có thể sai.

Một ví dụ khác là `INSERT` bản ghi `id=42` mà chưa commit. Reader ở mức cho phép dirty read có thể thấy bản ghi này; nếu writer rollback, reader sau đó không còn thấy nó.

Điều cần phân biệt:

- **Read your own writes:** Cùng transaction/connection ghi rồi đọc lại thấy thay đổi của chính mình. Đây là hành vi bình thường, **không chứng minh dirty read**.
- **Dirty read:** Transaction/connection **B khác** đọc thay đổi chưa commit của transaction **A**.
- **Non-repeatable read:** B đọc một hàng lần đầu, A **commit** giá trị mới, B đọc lại cùng hàng thấy giá trị khác.
- **Phantom read:** B lặp lại một truy vấn theo điều kiện, có thể thấy tập hàng khác do transaction khác **commit** INSERT/DELETE phù hợp.
- **Dirty write:** Hai transaction ghi đè lên thay đổi chưa commit của nhau; không đồng nghĩa với việc READ_UNCOMMITTED cho phép dirty write. Nhiều engine vẫn có write locks và ngăn kiểu ghi này.

### Ma trận hiện tượng theo mô hình chuẩn

| Isolation theo khái niệm SQL | Dirty read | Non-repeatable read | Phantom read |
| --- | --- | --- | --- |
| `READ_UNCOMMITTED` | Có thể | Có thể | Có thể |
| `READ_COMMITTED` | Không | Có thể | Có thể |
| `REPEATABLE_READ` | Không | Không theo định nghĩa chuẩn | Có thể theo mô hình chuẩn |
| `SERIALIZABLE` | Không | Không | Không |

**"Có thể" không nghĩa là "chắc chắn xuất hiện".** DBMS hiện đại có MVCC, snapshot, predicate locking, các mức bảo đảm bổ sung hoặc ánh xạ mức isolation sang semantics khác. Chẳng hạn PostgreSQL không cho dirty read dù nhận yêu cầu `READ UNCOMMITTED`. Các loại truy vấn `SELECT`, locking read, UPDATE, isolation snapshot, storage engine và cơ chế cấu hình DB cũng có thể thay đổi hành vi. Ma trận mô tả tính cho phép của mô hình, **không phải cam kết mọi backend**.

## 3. Spring biểu diễn READ_UNCOMMITTED như thế nào?

### 3.1. Với annotation

```java
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(isolation = Isolation.READ_UNCOMMITTED, readOnly = true)
public long countRows() {
    return jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM price_quote",
        Long.class);
}
```

Đây là **fragment minh họa**, chưa khai báo `jdbcTemplate` hoặc class chứa method. `Isolation.READ_UNCOMMITTED` nói với Spring: khi tạo transaction mới, hãy yêu cầu transaction manager thiết lập mức cô lập tương ứng. `readOnly=true` là hint tối ưu hóa/định hướng đọc; không quyết định có dirty read hay không, và cũng không phải luôn là biện pháp ngăn ghi dữ liệu.

`Isolation.DEFAULT` (mặc định của `@Transactional`) **không** mang nghĩa `READ_COMMITTED`. Nó mang nghĩa **sử dụng mặc định của underlying database/resource**, vốn có thể khác nhau; ví dụ MySQL InnoDB mặc định `REPEATABLE_READ`, còn PostgreSQL/H2 thường mặc định `READ_COMMITTED`.

### 3.2. Với TransactionTemplate

```java
TransactionTemplate template = new TransactionTemplate(transactionManager);
template.setIsolationLevel(TransactionDefinition.ISOLATION_READ_UNCOMMITTED);
template.setReadOnly(true);

Integer count = template.execute(status ->
    jdbcTemplate.queryForObject(
        "SELECT COUNT(*) FROM price_quote", Integer.class));
```

Đây là **fragment**, cần bean `transactionManager`/`jdbcTemplate` và import `TransactionDefinition`/`TransactionTemplate`. `TransactionTemplate` áp dụng isolation khi nó **thực sự tạo transaction mới**; nếu propagation `REQUIRED` tham gia transaction có sẵn, annotation/setting khác trên inner không tự đổi isolation của outer.

### 3.3. Với XML transaction advice

```xml
<tx:advice id="txAdvice" transaction-manager="transactionManager">
    <tx:attributes>
        <tx:method name="find*" isolation="READ_UNCOMMITTED"
                   read-only="true"/>
        <tx:method name="*"/>
    </tx:attributes>
</tx:advice>
```

Đây cũng là **fragment cấu hình**, cần khai báo namespace `tx`, manager bean và AOP advisor để gắn advice vào pointcut. Isolation vẫn đi qua Spring transaction manager và JDBC connection; XML không thể ép DBMS triển khai tính năng không được hỗ trợ.

### 3.4. Ánh xạ sang JDBC

Spring dùng khái niệm isolation level gần với các hằng của JDBC:

| Spring | JDBC `Connection` | Giá trị số JDBC |
| --- | --- | --- |
| `Isolation.READ_UNCOMMITTED` | `TRANSACTION_READ_UNCOMMITTED` | `1` |
| `Isolation.READ_COMMITTED` | `TRANSACTION_READ_COMMITTED` | `2` |
| `Isolation.REPEATABLE_READ` | `TRANSACTION_REPEATABLE_READ` | `4` |
| `Isolation.SERIALIZABLE` | `TRANSACTION_SERIALIZABLE` | `8` |
| `Isolation.DEFAULT` | Không ép mức riêng; dùng mặc định resource | Không phải một số JDBC level cụ thể |

Với `DataSourceTransactionManager`/`JdbcTransactionManager`, khi **bắt đầu một JDBC transaction mới**, Spring có thể gọi `Connection.setTransactionIsolation(...)` theo metadata. Khi hoàn tất, Spring thường khôi phục các thuộc tính connection đã thay đổi để không "rò" isolation sang lượt dùng connection tiếp theo từ pool.

**Giới hạn:** Việc set level có thể bị driver từ chối, được chuyển/ánh xạ, hoặc được chấp nhận như một cấu hình nhưng DB vẫn thực thi semantics khác. Vì vậy `@Transactional(isolation = Isolation.READ_UNCOMMITTED)` là **yêu cầu** chứ không phải bằng chứng dữ liệu thực sự có thể được dirty-read.

## 4. Khi nào isolation mới có hiệu lực trong propagation?

Mấu chốt là **physical transaction mới**:

```text
Caller không có transaction
    |
    v
@Transactional(isolation = READ_UNCOMMITTED, propagation = REQUIRED)
    |
    +-- Spring mở JDBC transaction mới
    +-- manager yêu cầu READ_UNCOMMITTED
    +-- phép đọc chạy dưới mức DB/driver thực tế áp dụng
    +-- COMMIT/ROLLBACK -> connection được trả về pool
```

Nhưng khi caller đã có transaction:

```text
Outer @Transactional(isolation = READ_COMMITTED)
   |
   +-- physical transaction T ở READ_COMMITTED
   |
   +-- Inner @Transactional(
   |       isolation = READ_UNCOMMITTED,
   |       propagation = REQUIRED)
   |       -> tham gia T
   |       -> không tự đổi T sang READ_UNCOMMITTED
   |
   +-- outer hoàn tất transaction T
```

| Scope | Mức mới được yêu cầu? | Kết luận |
| --- | --- | --- |
| `REQUIRED` không có outer transaction | Có, khi tạo physical transaction | Có thể áp dụng nếu manager/DB hỗ trợ |
| `REQUIRED` có outer transaction | Inner chỉ tham gia transaction hiện tại | Isolation của inner thường bị bỏ qua theo chế độ lenient mặc định |
| `REQUIRES_NEW` có outer transaction | Tạo physical transaction mới, suspend outer | Có thể yêu cầu isolation mới riêng |
| `NESTED` có outer JDBC transaction | Savepoint trên cùng physical transaction | Không phải transaction độc lập để thay isolation |
| Self-invocation bằng `this.method()` | Có thể bỏ qua proxy | Metadata trên inner method không được áp dụng |
| Method chạy trong thread mới | Không tự nhận transaction thread-bound của caller | Phải xác định transaction mới/cơ chế async rõ ràng |

Spring cung cấp tùy chọn `AbstractPlatformTransactionManager.setValidateExistingTransaction(true)`. Khi bật, một inner `REQUIRED` yêu cầu isolation **khác** với transaction hiện tại có thể bị từ chối thay vì âm thầm tham gia. Đây là cơ chế bảo vệ cấu hình, **không phải** cơ chế nâng/hạ isolation của transaction đã tồn tại.

Ví dụ cấu hình để phát hiện mismatch, chỉ dùng nếu ứng dụng thực sự muốn chính sách strict:

```java
@Bean
DataSourceTransactionManager transactionManager(DataSource dataSource) {
    var manager = new DataSourceTransactionManager(dataSource);
    manager.setValidateExistingTransaction(true);
    return manager;
}
```

Đây là fragment, không có trong dự án chạy ở mục 8 vì ví dụ sẽ chủ động quan sát hành vi lenient mặc định. Nếu đã có bean transaction manager, đừng vô tình tạo thêm manager thứ hai hoặc thay đổi cấu hình toàn ứng dụng chỉ để kiểm tra một method.

## 5. Những giới hạn thực tế theo DBMS

### 5.1. PostgreSQL: nhận tên level, nhưng không có dirty read

Tài liệu chính thức PostgreSQL nói rõ **`READ UNCOMMITTED` được xử lý như `READ COMMITTED`**. Điều đó có nghĩa:

- Không nên kỳ vọng đọc thấy thay đổi chưa commit từ transaction khác chỉ nhờ yêu cầu mức này.
- Nếu JDBC driver chấp nhận lệnh đặt isolation, điều đó không chứng minh có dirty read.
- PostgreSQL sử dụng MVCC; với ordinary SELECT ở `READ COMMITTED`, snapshot của câu lệnh chỉ nhìn dữ liệu committed phù hợp, không nhìn thay đổi chưa commit từ transaction khác.
- Nếu bài test được viết với giả định "READ_UNCOMMITTED luôn phải thấy row của writer chưa commit", test **sẽ không hợp lệ khi port sang PostgreSQL**.

Do đó **không lấy kết quả demo H2/MySQL để suy ra PostgreSQL**.

Tham khảo: https://www.postgresql.org/docs/current/transaction-iso.html và https://www.postgresql.org/docs/current/sql-set-transaction.html

### 5.2. MySQL InnoDB: có READ UNCOMMITTED, nhưng phải đúng engine

InnoDB cung cấp bốn mức `READ UNCOMMITTED`, `READ COMMITTED`, `REPEATABLE READ` và `SERIALIZABLE`. Mặc định phổ biến của InnoDB là `REPEATABLE READ`.

Tài liệu InnoDB mô tả ở mức `READ UNCOMMITTED`, ordinary `SELECT` không locking có thể thực hiện **dirty read**, nghĩa là dữ liệu đang quan sát có thể là trạng thái chưa được commit.

Hạn chế khi suy luận:

- Phải xác nhận bảng dùng **InnoDB hoặc engine transactional phù hợp**. Một engine không có rollback/transaction sẽ làm ví dụ "writer rollback" không còn đúng.
- Một `SELECT ... FOR UPDATE`, locking read hoặc update statement không nhất thiết theo đúng kiểu ordinary nonlocking SELECT. Không đồng nhất toàn bộ SQL với khái niệm dirty read đơn giản.
- Có thể bị ảnh hưởng bởi phiên bản DB/driver, connection pool, isolation của session và hình thức truy vấn.
- Không dùng dirty read như bằng chứng dữ liệu "đã tồn tại" để thực hiện nghiệp vụ thanh toán, kiểm tồn kho hoặc phát hành hóa đơn.

Tham khảo: https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html

### 5.3. SQL Server: có READ UNCOMMITTED, không phải NOLOCK là vô hại

Microsoft mô tả `READ UNCOMMITTED` cho phép đọc những hàng mà transaction khác đã sửa nhưng chưa commit. Cơ chế thường được so sánh với table hint `NOLOCK` trong các tình huống đọc dữ liệu.

Tuy nhiên:

- Dirty read làm báo cáo có thể thấy dữ liệu sẽ biến mất nếu writer rollback.
- Không phải mọi truy vấn đều "không có lock", và `NOLOCK` không phải giải pháp mặc định cho mọi vấn đề blocking.
- SQL Server có các lựa chọn khác như `READ_COMMITTED_SNAPSHOT`/`SNAPSHOT` để cân bằng concurrency với tính nhất quán theo cách khác; chúng không tương đương việc mở dirty read.
- Một số bản triển khai/biến thể SQL platform có thêm quy tắc riêng, nên kiểm tra **đúng SQL Server engine/edition và cấu hình**.

Tham khảo: https://learn.microsoft.com/en-us/sql/t-sql/statements/set-transaction-isolation-level-transact-sql

### 5.4. Oracle Database: không cho phép dirty reads

Tài liệu Oracle Database khẳng định **`READ UNCOMMITTED` không phải mức isolation cung cấp dirty read**. Oracle triển khai các mức như `READ COMMITTED`, `SERIALIZABLE` và read-only transaction theo cơ chế của sản phẩm; ordinary query sử dụng consistent reads.

- Không nên suy ra chỉ cần `@Transactional(isolation = READ_UNCOMMITTED)` là Oracle cho đọc uncommitted.
- JDBC driver có thể từ chối hoặc xử lý yêu cầu isolation theo khả năng thực tế; cần kiểm tra behavior và lỗi trả về.
- Không thử "lách" dirty read để tăng tốc: mục tiêu throughput có thể được giải quyết bằng chiến lược transaction/SQL/index phù hợp mà vẫn đọc committed data.

Tham khảo: https://docs.oracle.com/en/database/oracle/oracle-database/21/adfns/sql-processing-for-application-developers.html

### 5.5. H2: môi trường phù hợp để học dirty read

H2 công bố hỗ trợ `READ UNCOMMITTED` và mô tả dirty reads có thể xảy ra ở mức này. Mức mặc định H2 thường là `READ COMMITTED`.

Vì vậy chúng ta dùng **H2 in-memory có tên** để chạy một thử nghiệm có kiểm soát:

- Transaction A INSERT một bản ghi nhưng **chưa commit**.
- Reader B ở `READ_UNCOMMITTED` trên một JDBC transaction/connection **khác** thực hiện SELECT trước khi A kết thúc.
- Reader C ở `READ_COMMITTED` cũng SELECT trong khi A còn mở.
- A rollback.
- C đọc lại sau rollback: không còn bản ghi.

Quan trọng: H2 chỉ làm **demo kỹ thuật**, không phải phép bảo đảm tính tương thích cho PostgreSQL, Oracle, MySQL hoặc SQL Server production.

Tham khảo: https://h2database.com/html/advanced.html và https://h2database.com/html/features.html

### 5.6. Bảng tổng hợp không đánh đồng các DB

| DB / engine | READ_UNCOMMITTED và dirty read | Kỳ vọng nên kiểm chứng |
| --- | --- | --- |
| H2 | Có hỗ trợ theo tài liệu H2 | Với ordinary SELECT và hai transaction khác connection, có thể nhìn uncommitted row |
| MySQL InnoDB | Có hỗ trợ | Thử trên cùng version/engine/driver với truy vấn thật |
| SQL Server | Có hỗ trợ | Thử theo SQL Server edition/options; đánh giá rủi ro `NOLOCK` |
| PostgreSQL | `READ UNCOMMITTED` được đối xử như `READ COMMITTED` | Không mong dirty read |
| Oracle Database | Không cho dirty read | Không mong dirty read; kiểm tra driver báo lỗi/mapping |
| Engine không transactional | Không bảo đảm rollback | Không dùng để kết luận isolation theo chuẩn giao dịch |

Đây là **hành vi tài liệu hóa**, không phải lời hứa rằng mọi query/driver/version đều tái hiện một output giống H2. Khi triển khai thật, verify phiên bản, engine, schema, transaction mode và workload.

## 6. Vì sao metadata JDBC chưa chứng minh dirty read?

JDBC cung cấp hai phép kiểm tra hữu ích:

```java
try (Connection c = dataSource.getConnection()) {
    boolean advertised = c.getMetaData()
            .supportsTransactionIsolationLevel(
                    Connection.TRANSACTION_READ_UNCOMMITTED);
    int current = c.getTransactionIsolation();
    System.out.println("driver reports support: " + advertised);
    System.out.println("current JDBC level: " + current);
}
```

Đây là fragment Java; `DataSource` và imports phải được cung cấp.

Ý nghĩa đúng:

- `DatabaseMetaData.supportsTransactionIsolationLevel(int)` trả về **khả năng driver báo cáo** với mức cô lập.
- `Connection.getTransactionIsolation()` phản ánh trạng thái isolation của JDBC connection; giá trị `1` tương ứng `TRANSACTION_READ_UNCOMMITTED`.
- `Connection.setTransactionIsolation(int)` yêu cầu đổi mức cô lập khi transaction mới được chuẩn bị, tùy manager/driver/backend.

Các câu hỏi metadata **không trả lời được**:

- Câu SELECT có thấy uncommitted row do connection khác vừa ghi không?
- Backend có ánh xạ READ_UNCOMMITTED thành READ_COMMITTED không?
- Transaction hiện tại là outer transaction đã mở trước khi inner annotation yêu cầu level mới không?
- SQL được chạy trên cùng connection/DB/schema/tenant đang được kiểm tra không?
- Reader đã đọc trong lúc writer thực sự **chưa commit**, hay writer đã rollback/commit trước đó?

**Vì vậy cần kiểm chứng hành vi cạnh tranh (concurrency test).** Cách đáng tin là dùng hai physical connection đồng thời, giữ writer open bằng cơ chế đồng bộ, thực hiện SELECT trong lúc writer chưa kết thúc, sau đó rollback writer và đối chiếu committed state.

## 7. Thiết kế thử nghiệm đúng và các điều kiện kiểm soát

### 7.1. Sơ đồ hai phiên làm việc

```text
Thread W / Connection W                     Thread Main / Connection R
-------------------------------------       -----------------------------------
@Transactional REQUIRED begin
INSERT id=101, amount=900 (uncommitted)
signal "inserted"
wait("release")

                                            @Transactional READ_UNCOMMITTED:
                                              SELECT COUNT(*) WHERE id=101
                                              H2 demo: 1 (dirty read)

                                            @Transactional READ_COMMITTED:
                                              SELECT COUNT(*) WHERE id=101
                                              H2 demo: 0

release writer
throw IllegalStateException
Spring ROLLBACK
                                            @Transactional READ_COMMITTED:
                                              SELECT COUNT(*) WHERE id=101
                                              0 (không có row committed)
```

### 7.2. Điều kiện để kết luận đúng

1. Writer dùng `@Transactional` và gọi từ Spring proxy, không phải tự `new` service.
2. Writer **giữ transaction chưa hoàn tất** ở thời điểm reader chạy. `CountDownLatch` đồng bộ thứ tự; không dựa vào `Thread.sleep(100)` hay may rủi scheduling.
3. Reader được gọi từ caller không có transaction ngoài, để `@Transactional(isolation=...)` mở transaction riêng và thực sự áp dụng isolation.
4. Writer và reader dùng **cùng DB nhưng hai connection**. Connection pool phải có đủ connection cho việc ghi và đọc đồng thời; không dùng pool size 1.
5. Bảng được tạo trước khi bắt đầu thử nghiệm; tránh DDL implicit commit khi writer đang giữ transaction.
6. Dùng ordinary `SELECT COUNT(*)`, không dùng locking read, không đọc từ JPA first-level cache.
7. Dùng một ID chỉ dành cho mỗi test, tránh dữ liệu cũ làm sai kết luận.
8. **Đọc lại sau writer rollback** để phân biệt dirty read với dữ liệu committed.
9. Có timeout và `finally` để giải phóng writer/ExecutorService, tránh treo vĩnh viễn nếu reader bị blocked hoặc test thất bại.
10. Với DB khác H2, **không hardcode** assert "dirty read = 1" nếu vendor cố tình không hỗ trợ level đó; thay bằng expected behavior phù hợp tài liệu của vendor.

## 8. Dự án Spring Boot Java 17+ chạy được

Ví dụ dùng Spring Boot **3.5.6**, Spring JDBC, H2, Maven và JUnit 5. Các file đủ để bạn tạo thư mục và chạy; Spring Boot tự tạo `DataSource` connection pool cùng `PlatformTransactionManager` cho JDBC. Không cần cấu hình JPA.

### 8.1. Cấu trúc thư mục

```text
read-uncommitted-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── IsolationApplication.java
    │   │   ├── PendingWriteService.java
    │   │   ├── IsolationReadService.java
    │   │   └── OuterIsolationService.java
    │   └── resources/application.properties
    └── test/java/demo/
        └── IsolationIntegrationTest.java
```

### 8.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>read-uncommitted-lab</artifactId>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

`spring-boot-starter-jdbc` cung cấp `JdbcTemplate` và JDBC transaction infrastructure; H2 là database in-memory; `spring-boot-starter-test` có Spring Test/JUnit 5.

### 8.3. application.properties

**`src/main/resources/application.properties`**

```properties
spring.datasource.url=jdbc:h2:mem:dirty_read_lab;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=5
spring.main.banner-mode=off
```

**Vì sao cần pool lớn hơn 1?** Writer giữ một connection trong transaction trong khi main thread cần connection khác cho reader. Pool size `5` giúp tránh deadlock do chờ connection và cho phép thử nghiệm concurrent reads. URL H2 **có tên** `dirty_read_lab` để các connection của cùng JVM truy cập một database, và `DB_CLOSE_DELAY=-1` giữ database sống trong JVM.

### 8.4. PendingWriteService.java: giữ transaction chưa commit

**`src/main/java/demo/PendingWriteService.java`**

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PendingWriteService {
    private final JdbcTemplate jdbc;

    public PendingWriteService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void insertThenRollback(
            long id,
            CountDownLatch inserted,
            CountDownLatch release) {

        jdbc.update(
                "INSERT INTO isolation_probe(id, amount) VALUES (?, ?)",
                id, 900);

        // Báo cho reader rằng INSERT đã chạy trong transaction W.
        inserted.countDown();

        try {
            // Giữ transaction W đang mở cho đến khi reader đọc xong.
            if (!release.await(30, TimeUnit.SECONDS)) {
                throw new IllegalStateException("writer timed out");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("writer interrupted", ex);
        }

        // Unchecked exception đi qua transaction interceptor => rollback.
        throw new IllegalStateException("forced rollback");
    }
}
```

`insertThenRollback` được gọi **trên Spring bean proxy** từ một executor thread. Spring transaction đồng bộ được mở trong thread của writer, không phải từ main thread. Sau `INSERT`, writer chỉ phát tín hiệu rồi chờ; chưa return khỏi method, vì vậy chưa có commit/rollback. Khi main thread ra hiệu `release`, method ném unchecked exception; Spring interceptor rollback.

Trong production, không giữ transaction mở để chờ network/UI như cách trình diễn này; đây chỉ là phép **đồng bộ kiểm thử** có timeout để dễ tái hiện dirty read.

### 8.5. IsolationReadService.java: tách READ_UNCOMMITTED và READ_COMMITTED

**`src/main/java/demo/IsolationReadService.java`**

```java
package demo;

import java.sql.Connection;
import java.util.Objects;

import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class IsolationReadService {
    private final JdbcTemplate jdbc;

    public IsolationReadService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public record Observation(int effectiveJdbcLevel, int rows) {}

    @Transactional(
            isolation = Isolation.READ_UNCOMMITTED,
            readOnly = true)
    public Observation readUncommitted(long id) {
        return observe(id);
    }

    @Transactional(
            isolation = Isolation.READ_COMMITTED,
            readOnly = true)
    public Observation readCommitted(long id) {
        return observe(id);
    }

    private Observation observe(long id) {
        Integer jdbcLevel = jdbc.execute(
                (ConnectionCallback<Integer>)
                        Connection::getTransactionIsolation);

        Integer rows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM isolation_probe WHERE id = ?",
                Integer.class, id);

        return new Observation(
                Objects.requireNonNull(jdbcLevel),
                Objects.requireNonNull(rows));
    }
}
```

Hai public methods được gọi qua Spring proxy. Khi caller không có outer transaction, mỗi method tạo transaction mới theo `REQUIRED` mặc định và yêu cầu JDBC isolation tương ứng. `JdbcTemplate` lấy transaction-bound connection; câu `getTransactionIsolation()` và phép SELECT chạy trong cùng method/transaction. `Observation` lưu cả **mức JDBC connection báo cáo** và **số dòng truy vấn quan sát**.

`Objects.requireNonNull(...)` giúp kết quả demo không âm thầm chuyển một giá trị `null` thành dữ liệu giả. `Connection.getTransactionIsolation()` không tự chứng minh semantics vendor; chính phép đọc đồng thời mới là test hành vi.

### 8.6. OuterIsolationService.java: chứng minh inner REQUIRED không tự đổi level

**`src/main/java/demo/OuterIsolationService.java`**

```java
package demo;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterIsolationService {
    private final IsolationReadService reader;

    public OuterIsolationService(IsolationReadService reader) {
        this.reader = reader;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public IsolationReadService.Observation readViaInnerRequired(long id) {
        // Inner yêu cầu READ_UNCOMMITTED, nhưng cùng physical transaction.
        return reader.readUncommitted(id);
    }
}
```

`OuterIsolationService` và `IsolationReadService` là **hai bean** để lời gọi inner đi qua proxy. Với manager ở chế độ lenient mặc định, outer tạo transaction `READ_COMMITTED`, inner `REQUIRED` tham gia transaction đó. Mức JDBC actual vẫn là `READ_COMMITTED`, dù annotation của inner ghi `READ_UNCOMMITTED`.

Khi bật `validateExistingTransaction=true`, kiểu mismatch này có thể bị từ chối; bài dùng default để kiểm chứng việc **inner không tự điều khiển isolation của outer**.

### 8.7. IsolationApplication.java: đồng bộ hai kết nối và in kết quả

**`src/main/java/demo/IsolationApplication.java`**

```java
package demo;

import java.sql.Connection;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class IsolationApplication {
    public static void main(String[] args) {
        SpringApplication.run(IsolationApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(
            DataSource dataSource,
            JdbcTemplate jdbc,
            PendingWriteService writer,
            IsolationReadService reader,
            OuterIsolationService outer) {

        return args -> {
            // DDL chạy trước transaction concurrency demo.
            jdbc.execute("""
                    CREATE TABLE IF NOT EXISTS isolation_probe (
                        id BIGINT PRIMARY KEY,
                        amount INT NOT NULL
                    )
                    """);

            try (Connection connection = dataSource.getConnection()) {
                boolean supported = connection.getMetaData()
                        .supportsTransactionIsolationLevel(
                                Connection.TRANSACTION_READ_UNCOMMITTED);
                System.out.println(
                        "driver reports READ_UNCOMMITTED supported: "
                                + supported);
            }

            CountDownLatch inserted = new CountDownLatch(1);
            CountDownLatch release = new CountDownLatch(1);
            ExecutorService pool = Executors.newSingleThreadExecutor();

            try {
                Future<?> task = pool.submit(() ->
                        writer.insertThenRollback(101L, inserted, release));

                try {
                    if (!inserted.await(10, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                                "writer did not insert");
                    }

                    var dirty = reader.readUncommitted(101L);
                    var clean = reader.readCommitted(101L);

                    System.out.println(
                            "RU effective JDBC level: "
                                    + dirty.effectiveJdbcLevel());
                    System.out.println(
                            "RU while writer open: " + dirty.rows());
                    System.out.println(
                            "RC effective JDBC level: "
                                    + clean.effectiveJdbcLevel());
                    System.out.println(
                            "RC while writer open: " + clean.rows());
                } finally {
                    // Kể cả lúc đọc có lỗi, không để writer chờ mãi.
                    release.countDown();
                }

                boolean rolledBack = false;
                try {
                    task.get(10, TimeUnit.SECONDS);
                } catch (ExecutionException ex) {
                    Throwable failure = ex.getCause();
                    if (!(failure instanceof IllegalStateException)
                            || !"forced rollback".equals(
                                    failure.getMessage())) {
                        throw ex;
                    }
                    rolledBack = true;
                }

                System.out.println(
                        "writer rollback observed: " + rolledBack);

                System.out.println(
                        "RC after writer rollback: "
                                + reader.readCommitted(101L).rows());

                System.out.println(
                        "joined REQUIRED actual JDBC level: "
                                + outer.readViaInnerRequired(101L)
                                       .effectiveJdbcLevel());
            } finally {
                release.countDown();
                pool.shutdownNow();
            }
        };
    }
}
```

Đây là file `@SpringBootApplication` chạy được với các file còn lại. Một số chi tiết quan trọng:

- `ExecutorService` chỉ có một worker thread cho writer; main thread thực hiện các lời gọi reader.
- `inserted.await` chờ đến khi writer đã chạy `INSERT`, không dựa trên thời gian ngủ tùy ý.
- Writer vẫn đang giữ physical transaction ở lúc các reader chạy.
- `READ_UNCOMMITTED` và `READ_COMMITTED` được gọi **tuần tự trong main thread**, nhưng cả hai đều có connection/transaction riêng, khác connection writer đang bận.
- `release.countDown()` trong `finally` giải phóng writer ngay cả khi reader lỗi.
- `Future.get` đợi writer kết thúc; exception từ `insertThenRollback` là **được dự kiến** để Spring rollback. Chỉ chấp nhận `IllegalStateException("forced rollback")`; lỗi khác được phát lại để không có false positive.
- Sau khi writer rollback, `readCommitted` kiểm tra trạng thái **committed**. Nếu dirty read trước đó thấy một hàng nhưng sau rollback không còn, đó là bằng chứng row được đọc khi chưa committed.
- Cuối cùng, outer method yêu cầu `READ_COMMITTED` và gọi inner method muốn `READ_UNCOMMITTED`, để xác minh isolation inner `REQUIRED` không thay đổi level của outer.
- Mọi case dùng ID 101 trong demo, nhưng table mới và chỉ một writer cho ID này.

### 8.8. Lệnh chạy và stdout dự kiến trên H2

Cần Java 17+ và Maven; trong thư mục có `pom.xml`:

```bash
mvn spring-boot:run
```

Các dòng do **chính chương trình** in (bỏ qua log khởi động Spring/Maven):

```text
driver reports READ_UNCOMMITTED supported: true
RU effective JDBC level: 1
RU while writer open: 1
RC effective JDBC level: 2
RC while writer open: 0
writer rollback observed: true
RC after writer rollback: 0
joined REQUIRED actual JDBC level: 2
```

Kết quả đặc biệt:

| Quan sát | Giải thích |
| --- | --- |
| `RU while writer open: 1` | Reader H2 ở `READ_UNCOMMITTED` nhìn thấy INSERT chưa commit của transaction writer |
| `RC while writer open: 0` | Reader `READ_COMMITTED` không nhìn thấy INSERT chưa commit |
| `writer rollback observed: true` | Writer đã ném exception mong đợi, Spring rollback transaction |
| `RC after writer rollback: 0` | Bản ghi chưa từng được commit; dữ liệu dirty-read là trạng thái tạm |
| `joined REQUIRED actual JDBC level: 2` | Reader inner yêu cầu RU nhưng tham gia outer RC, không đổi isolation của outer |

**Giới hạn của stdout:** Đây là output **dự kiến cho H2 và phiên bản/thành phần cấu hình như đã nêu**. Nếu chạy trên PostgreSQL, không nên mong dòng `RU while writer open: 1`. Với database khác, có thể có lỗi driver không hỗ trợ isolation hoặc behavior khác. Kiểm tra phải dựa trên kết quả thực chạy trong môi trường, không cố "sửa" code để ép mọi vendor cho dirty read.

## 9. Integration test kiểm chứng cả metadata và semantics

Tạo file **`src/test/java/demo/IsolationIntegrationTest.java`**:

```java
package demo;

import java.sql.Connection;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class IsolationIntegrationTest {
    @Autowired
    private DataSource dataSource;

    @Autowired
    private PendingWriteService writer;

    @Autowired
    private IsolationReadService reader;

    @Autowired
    private OuterIsolationService outer;

    @Autowired
    private JdbcTemplate jdbc;

    @Test
    void driverAdvertisesReadUncommitted() throws Exception {
        try (Connection connection = dataSource.getConnection()) {
            assertTrue(connection.getMetaData()
                    .supportsTransactionIsolationLevel(
                            Connection.TRANSACTION_READ_UNCOMMITTED));
        }
    }

    @Test
    void readUncommittedCanSeeRowThatLaterRollsBack() throws Exception {
        long id = 1001L;
        CountDownLatch inserted = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        ExecutorService pool = Executors.newSingleThreadExecutor();

        try {
            Future<?> task = pool.submit(() ->
                    writer.insertThenRollback(id, inserted, release));

            try {
                assertTrue(inserted.await(10, TimeUnit.SECONDS));

                var dirty = reader.readUncommitted(id);
                var clean = reader.readCommitted(id);

                assertEquals(
                        Connection.TRANSACTION_READ_UNCOMMITTED,
                        dirty.effectiveJdbcLevel());
                assertEquals(
                        Connection.TRANSACTION_READ_COMMITTED,
                        clean.effectiveJdbcLevel());

                assertEquals(1, dirty.rows()); // Đúng với H2 lab.
                assertEquals(0, clean.rows());
            } finally {
                release.countDown();
            }

            ExecutionException thrown = assertThrows(
                    ExecutionException.class,
                    () -> task.get(10, TimeUnit.SECONDS));
            assertInstanceOf(
                    IllegalStateException.class, thrown.getCause());
            assertEquals(
                    "forced rollback", thrown.getCause().getMessage());

            assertEquals(0, reader.readCommitted(id).rows());
        } finally {
            release.countDown();
            pool.shutdownNow();
        }
    }

    @Test
    void innerRequiredCannotChangeIsolationOfExistingOuter() {
        var result = outer.readViaInnerRequired(9999L);
        assertEquals(
                Connection.TRANSACTION_READ_COMMITTED,
                result.effectiveJdbcLevel());
        assertEquals(0, result.rows());
    }
}
```

Chạy:

```bash
mvn test
```

**Kỳ vọng:** ba test pass trên H2 với Spring Boot/JDBC được cấu hình như project. `@SpringBootTest` tạo application context và chạy `CommandLineRunner`, đã tạo bảng/hoàn tất demo với ID 101; test dùng ID 1001 và 9999 để không trùng.

Test không dùng `@Transactional` ở class/method. Nếu thêm, Spring TestContext có thể mở outer test transaction và các method reader `REQUIRED` tham gia transaction đó, làm mất điều kiện "hai transaction reader được mở mới với isolation riêng" — test isolation sẽ không còn đo thứ bạn tưởng.

### 9.1. Vì sao test phải dùng concurrency thực?

Một test chỉ gọi:

```java
jdbc.update("INSERT INTO isolation_probe(id, amount) VALUES (?, ?)",
        55L, 900);

int count = jdbc.queryForObject(
        "SELECT COUNT(*) FROM isolation_probe WHERE id = ?",
        Integer.class, 55L);
```

**Không chứng minh dirty read.** Các câu lệnh có thể đang ở cùng transaction/connection, hoặc INSERT đã auto-commit trước SELECT. Phải giữ **writer transaction chưa commit** ở một connection và đọc từ **connection thứ hai** ngay trong khoảng đó.

### 9.2. Điều gì khiến test nhìn thấy 0 dù đã yêu cầu READ_UNCOMMITTED?

- Backend cố ý không cho dirty read, như PostgreSQL/Oracle.
- Reader không thật sự mở transaction mới, vì đang join outer `REQUIRED`.
- Driver không áp dụng level như kỳ vọng hoặc manager đã chọn sai.
- Writer đã rollback/commit trước phép đọc (lỗi đồng bộ).
- Hai DataSource trỏ sang database/schema khác.
- Query đi qua cache JPA hoặc read replica thay vì primary database.
- Loại SQL/engine có locking/snapshot semantics khác với giả định.

Không đổi expected từ 1 sang 0 một cách máy móc. Trước tiên cần xác định **vì sao** bằng metadata, JDBC isolation level và test thực tế.

## 10. Các trường hợp cấu hình sai trong ứng dụng Spring

### 10.1. Chỉ nhìn @Transactional rồi kết luận đã bật dirty read

`@Transactional(isolation=READ_UNCOMMITTED)` là một cấu hình request. Transaction manager phải thật sự mở physical transaction mới, JDBC driver nhận lệnh, DB hỗ trợ semantics tương ứng và SQL phải đọc trong khoảng writer đang uncommitted.

### 10.2. Method được gọi bằng this, không qua proxy

`this.someTransactionalMethod()` trong cùng bean ở mode proxy thông thường không kích hoạt transaction advice riêng của inner method. Isolation annotation có thể bị bỏ qua. Cần inject một Spring bean khác/gọi qua proxy như demo.

### 10.3. Inner REQUIRED muốn RU nhưng outer đã RC

Inner `REQUIRED` tham gia outer transaction. Spring không thay level của transaction đã bắt đầu. Nếu quan trọng phải tách physical transaction, cân nhắc `REQUIRES_NEW`; nhưng điều đó đổi semantics transaction và cần thêm JDBC connection. Không nên dùng `REQUIRES_NEW` chỉ để "làm cho annotation có tác dụng" mà không xem nghiệp vụ.

### 10.4. Driver metadata true được hiểu là bảo đảm dirty read

`supportsTransactionIsolationLevel(...)` chỉ là một nguồn thông tin. Cần kiểm tra isolation thực tế của connection và behavior giữa **hai** transaction đồng thời. PostgreSQL là ví dụ quan trọng cho việc một level được chấp nhận/ánh xạ nhưng semantics dirty read không có.

### 10.5. Read-only bị hiểu là một isolation level

`readOnly=true` là gợi ý tối ưu cho transaction/driver, không bảo đảm chống dirty read, không tự biến READ_UNCOMMITTED thành READ_COMMITTED, và không phải hàng rào chặn mọi lệnh SQL ghi trên mọi DB. Isolation và read-only là hai thuộc tính khác nhau.

### 10.6. Dùng READ_UNCOMMITTED như giải pháp mặc định chống lock contention

Đọc bẩn có thể phá invariants nghiệp vụ. Với dashboard quan sát tạm thời, cũng phải gắn nhãn "chưa chắc đã commit". Trước khi hạ isolation, nên thử index/SQL optimization, giảm thời gian giữ transaction, connection pool phù hợp hoặc snapshot/MVCC-based read committed theo DB.

### 10.7. Giả định mọi truy vấn ở RU đều không bị block

DBMS còn dùng schema locks, metadata locks, row/write locks, khóa khi join/ordering/DDL và các cơ chế khác. SQL Server `NOLOCK` không có nghĩa "không bao giờ khóa" và không phải thuốc chữa cho mọi tình huống blocking.

### 10.8. Tự set isolation trên pooled connection và quên restore

Khi dùng Spring-managed transaction, để manager thiết lập/khôi phục isolation. Tự gọi `connection.setTransactionIsolation(...)` trên connection do pool cấp mà không restore có thể làm trạng thái rò sang request sau. Với test JDBC thuần, luôn dùng connection riêng, lưu cấu hình cũ và khôi phục trước khi trả về pool.

### 10.9. Kết luận từ một database giả lập sang production

H2 tiện chạy unit/integration demo, nhưng MySQL/PostgreSQL/Oracle/SQL Server có semantics, SQL dialect và locking khác nhau. Hãy chạy integration test trên đúng DB/driver production, có thể qua Testcontainers, trước khi bật isolation mới.

### 10.10. Dựa trên dữ liệu chưa commit cho hành động không thể hoàn tác

Một dirty read có thể tạo email, thanh toán, thông báo hoặc thay đổi ở hệ thống ngoài. Khi writer rollback, những side effect này không tự rollback. Vì vậy không nên xây quyết định tiền bạc, phân quyền, inventory hoặc public-facing state dựa trên dữ liệu chưa commit.

### 10.11. Bật isolation ở tầng JPA mà giả định tương đương JDBC

Với `JpaTransactionManager`, JPA provider và dialect có thể hỗ trợ hoặc hạn chế custom isolation. Persistence context có first-level cache và flush semantics. Đừng xem kết quả `EntityManager.find` như SELECT trực tiếp trong một JDBC transaction mới. Thử riêng theo provider, JDBC access và manager thực.

### 10.12. Không quan sát outermost boundary

Nếu reader tham gia outer transaction, phép query bên trong chưa đủ chứng minh committed state và isolation đã đổi. Nếu writer đang rollback-only hoặc commit/rollback chưa hoàn tất, cần chờ outermost transaction kết thúc mới kết luận dữ liệu cuối cùng.

## 11. Checklist xác minh hỗ trợ thực tế trước khi deploy

- [ ] Xác định đúng DBMS, version, storage engine, driver version và transaction manager implementation.
- [ ] Xác định `@Transactional` hoạt động qua proxy; không có self-invocation làm metadata bị bỏ qua.
- [ ] Xác định transaction mới thực sự được tạo ở phương thức reader; không phải tham gia một outer `REQUIRED`.
- [ ] Kiểm tra `DatabaseMetaData.supportsTransactionIsolationLevel(Connection.TRANSACTION_READ_UNCOMMITTED)`.
- [ ] Đọc `Connection.getTransactionIsolation()` trong **connection đang tham gia transaction reader**, không chỉ connection bất kỳ từ pool.
- [ ] Kiểm tra server/driver có mapping RU thành RC hay không (đặc biệt PostgreSQL).
- [ ] Dùng đúng JDBC DataSource, database/schema/tenant/primary; tránh read replica và JPA cache.
- [ ] Tạo writer transaction chưa commit, giữ mở bằng latch; chạy reader ở một connection khác.
- [ ] Ghi lại behavior trước writer rollback và so sánh dữ liệu sau writer rollback.
- [ ] Không dùng hardcoded expectation của H2 cho vendor khác.
- [ ] Đánh giá correctness/security/side effects nếu dirty read thực sự xảy ra.
- [ ] Chọn mức isolation phù hợp và bổ sung regression tests chạy trên backend production.

## 12. Câu hỏi và bài tập

**Bài 1.** Transaction A INSERT một hàng rồi chưa commit. B cùng connection A SELECT thấy hàng. Đó có phải dirty read không?

**Đáp án:** Không. Đó là read-your-own-writes trong cùng transaction/connection. Muốn chứng minh dirty read, B phải là một transaction/connection khác.

**Bài 2.** Chạy `@Transactional(isolation = READ_UNCOMMITTED)` trên PostgreSQL. Reader có chắc sẽ thấy dữ liệu chưa commit không?

**Đáp án:** Không. PostgreSQL xử lý `READ UNCOMMITTED` như `READ COMMITTED` và không cho dirty read.

**Bài 3.** Trên H2, reader RU thấy hàng tạm, sau đó writer rollback và RC đọc không còn hàng. Bài test chứng minh điều gì?

**Đáp án:** Reader đã đọc trạng thái chưa committed. Việc dữ liệu mất sau rollback chứng minh dữ liệu tạm không thể xem là thông tin committed.

**Bài 4.** Outer transaction bắt đầu ở READ_COMMITTED, inner `REQUIRED` khai báo READ_UNCOMMITTED. Có chắc inner thực thi RU không?

**Đáp án:** Không. Inner tham gia physical transaction đã mở và thường dùng isolation của outer. Chế độ strict `validateExistingTransaction=true` còn có thể từ chối mismatch.

**Bài 5.** `supportsTransactionIsolationLevel(...)` trả true. Có thể bỏ thử nghiệm hai connection không?

**Đáp án:** Không. Metadata báo khả năng của driver, không chứng minh một SELECT cụ thể có thực hiện dirty read theo semantics DB/engine.

**Bài 6.** MySQL InnoDB mặc định READ_UNCOMMITTED phải không?

**Đáp án:** Không. InnoDB thường mặc định `REPEATABLE_READ`; muốn test RU phải cấu hình một transaction/session riêng và kiểm chứng driver/engine thực tế.

**Bài 7.** Oracle Database có cho phép dirty read nếu Spring annotation là RU không?

**Đáp án:** Không. Oracle Database không cung cấp dirty-read semantics; annotation không thể ép engine vượt quá hỗ trợ.

**Bài 8.** Vì sao demo đặt `spring.datasource.hikari.maximum-pool-size=5`?

**Đáp án:** Writer giữ một connection đang mở. Reader cần connection khác đồng thời; pool size 1 có thể khiến reader chỉ đứng chờ thay vì kiểm chứng concurrency.

**Bài 9.** Vì sao phải tạo bảng trước khi mở transaction writer?

**Đáp án:** DDL trên nhiều DB có implicit commit và có thể làm thay đổi transaction boundary. Test isolation cần cô lập DML khỏi hành vi DDL.

**Bài 10.** Có nên bật RU để tránh mọi lock contention cho nghiệp vụ chuyển khoản?

**Đáp án:** Không. Nó có thể cho phép đọc dữ liệu sẽ rollback và gây quyết định sai. Chọn cách giảm contention giữ được tính nhất quán, ví dụ tối ưu SQL/index/transaction duration hoặc các cơ chế snapshot/MVCC phù hợp.

## 13. Tài liệu chính thức

- Spring Framework — `@Transactional` settings, isolation/propagation và quy tắc proxy: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — Transaction propagation, `REQUIRED` và `validateExistingTransaction`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — `TransactionDefinition` Javadoc (ISOLATION_READ_UNCOMMITTED): https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionDefinition.html
- Spring Framework — JDBC connections và transaction manager: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- PostgreSQL — `SET TRANSACTION`, READ UNCOMMITTED treated as READ COMMITTED: https://www.postgresql.org/docs/current/sql-set-transaction.html
- MySQL 8.4 InnoDB — Transaction Isolation Levels: https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html
- Microsoft SQL Server — `SET TRANSACTION ISOLATION LEVEL`: https://learn.microsoft.com/en-us/sql/t-sql/statements/set-transaction-isolation-level-transact-sql
- Oracle Database — SQL Processing for Application Developers, isolation supported: https://docs.oracle.com/en/database/oracle/oracle-database/21/adfns/sql-processing-for-application-developers.html
- H2 Database — Transaction Isolation: https://h2database.com/html/advanced.html
- JDBC API — `Connection`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html
- JDBC API — `DatabaseMetaData`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/DatabaseMetaData.html

**Kết luận:** `READ_UNCOMMITTED` là **yêu cầu mức cô lập**, không phải bảo đảm nhìn thấy uncommitted data trên mọi database. Hãy xác minh transaction boundary, connection thực tế, metadata driver và behavior DBMS. Đối với Spring, chỉ một physical transaction mới mới có thể nhận isolation mới; inner `REQUIRED` không tự đổi mức của outer. Trước khi dùng trong hệ thống thật, phải kiểm tra concurrency bằng **hai connection**, chờ writer rollback và chứng minh kết quả đọc sau transaction kết thúc — đồng thời cân nhắc nghiêm túc rủi ro dirty read đối với quyết định nghiệp vụ.