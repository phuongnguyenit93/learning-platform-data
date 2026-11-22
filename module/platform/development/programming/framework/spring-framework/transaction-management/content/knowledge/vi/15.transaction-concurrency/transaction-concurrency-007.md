# Lock timeout, transaction timeout và câu lệnh bị hủy trong Spring Framework

## 1. Bài toán: cùng là "timeout" nhưng tác động khác nhau

Trong ứng dụng Spring Framework có nhiều request cập nhật cùng một bản ghi, transaction A giữ khóa để sửa dữ liệu; transaction B đợi khóa và cuối cùng nhận lỗi timeout. Ở một tình huống khác, transaction không chờ khóa mà chạy logic Java quá lâu; đến khi thực thi JDBC statement tiếp theo, Spring phát hiện **deadline giao dịch** đã hết. Một tình huống thứ ba là một SQL statement bị hủy do `Statement.setQueryTimeout(...)`, timeout phía server hoặc lệnh `Statement.cancel()`.

Ba vấn đề có liên hệ nhưng **không cùng một bộ đếm thời gian, không cùng cơ chế và không bảo đảm cùng hậu quả rollback**.

Bài học thuộc phần **Khóa và đồng thời** của Spring transaction management. Sau bài, bạn có thể:

- Phân biệt **lock wait timeout**, **transaction timeout**, **statement/query timeout**, **statement cancellation**, và **connection-pool acquisition timeout**.
- Hiểu khóa được giữ bởi transaction nào, câu lệnh nào đang chờ, ai tạo và ai thực thi timeout.
- Cấu hình `@Transactional(timeout = ...)`, `TransactionTemplate.setTimeout(...)` và XML `<tx:method timeout="...">` đúng đơn vị và đúng transaction boundary.
- Giải thích cách `DataSourceTransactionManager` truyền deadline còn lại xuống JDBC `Statement` thông qua `JdbcTemplate` / `DataSourceUtils`.
- Nắm giới hạn: timeout transaction **không phải** đồng hồ tự ngắt mọi tác vụ Java, và `Future.cancel(true)` không đồng nghĩa lệnh SQL đã được hủy.
- Phân biệt lỗi SQL statement bị rollback riêng với transaction vật lý bị rollback toàn bộ, kể cả khi exception bị catch.
- Chạy demo Java 17+ với hai JDBC transaction đồng thời trên H2: lock timeout vì bản ghi bị khóa; deadline Spring hết trước SQL tiếp theo; kiểm chứng dữ liệu sau rollback.
- Đọc nguyên nhân gốc (`SQLException`, SQLState/error code), thiết kế retry đúng transaction boundary và tránh giữ lock quá lâu.

**Ví dụ xuyên suốt:** Bảng `locked_account` có `id=1, balance=100`. Transaction W lấy khóa để cập nhật `balance=200` nhưng chưa commit. Transaction C muốn cập nhật `balance=300`, không thể lấy khóa kịp thời và bị hủy câu lệnh. Cuối cùng W rollback, nên giá trị đã commit vẫn là 100. Ở một luồng riêng, transaction có `timeout=1` giây insert một hàng, chờ trong Java rồi dùng `JdbcTemplate` thực thi SQL mới: Spring kiểm tra deadline và ngăn giao dịch tiếp tục.

## 2. Phân loại thời hạn: lớp nào điều khiển?

| Cơ chế | Đo từ đâu? | Chủ thể thiết lập | Đối tượng bị giới hạn | Đơn vị thường dùng |
| --- | --- | --- | --- | --- |
| **Lock wait timeout** | Khoảng chờ lấy lock của một operation | DB/session/engine; cấu hình riêng từng DB | Lệnh đang chờ khóa | H2/PostgreSQL/SQL Server: ms; MySQL InnoDB: giây |
| **Spring transaction timeout** | Thời hạn của transaction mới do Spring quản lý | `@Transactional`, `TransactionTemplate`, manager | Transaction scope/deadline; được chuyển xuống JDBC statement theo hỗ trợ | Giây |
| **JDBC statement/query timeout** | Thời gian execute một SQL statement | `Statement.setQueryTimeout` / `JdbcTemplate.setQueryTimeout` | Statement đang execute | Giây |
| **DB statement timeout** | Thời gian server xử lý statement | Ví dụ PostgreSQL `statement_timeout` | Statement của session/server | Thường ms hoặc chuỗi có đơn vị |
| **Statement cancellation** | Có yêu cầu hủy chủ động | `Statement.cancel()` hoặc server/client | Statement đang chạy, tùy driver/backend | Không nhất thiết có deadline |
| **Pool acquisition timeout** | Thời gian đợi lấy connection từ pool | Ví dụ HikariCP `connectionTimeout` | Chờ connection, **không** phải chờ row lock | Mili giây |
| **Network/socket timeout** | Chờ hoạt động mạng/driver | Driver, network layer, `Connection.setNetworkTimeout` | Giao tiếp kết nối | Thường mili giây |
| **HTTP/request timeout** | Ngân sách request ở application/gateway | API framework/client/gateway | Request HTTP | Tùy hệ thống |

### Ba câu hỏi cần đặt trước khi xử lý lỗi

1. **Đang chờ khóa hay đang chạy SQL chậm?** Lock wait là một loại thời gian bên trong statement; statement/query timeout có thể bao gồm cả thời gian chờ lock tùy DB/driver.
2. **Lỗi đến từ DB, JDBC driver hay Spring transaction manager?** Loại exception Java chỉ là lớp biểu diễn; hãy xem `SQLException` gốc và SQLState/error code.
3. **Transaction nào còn có thể commit?** Một số DB chỉ hủy statement bị lỗi; một số làm toàn transaction bị aborted. Ngoài ra, nếu exception RuntimeException đi ra qua Spring `@Transactional` proxy, **Spring mặc định rollback toàn transaction mà proxy đang sở hữu**, dù backend chỉ hủy một statement.

**Quy tắc:** Không suy luận "câu lệnh bị hủy" = "mọi thay đổi đã rollback"; cũng không suy luận "catch được exception" = "transaction vẫn an toàn để commit".

## 3. Lock wait timeout: một transaction chờ tài nguyên transaction khác giữ

### 3.1. Timeline

```text
Connection W / transaction T1         Connection C / transaction T2
----------------------------------    -----------------------------------
BEGIN
SELECT ... FOR UPDATE (id=1)
UPDATE id=1 SET balance=200
(lock vẫn được giữ)
                                     BEGIN
                                     UPDATE id=1 SET balance=300
                                     -> CHỜ khóa của T1
... tiếp tục giữ khóa ...
                                     quá giới hạn lock wait
                                     -> statement bị báo lỗi
                                     -> interceptor có thể rollback T2
ROLLBACK T1
                                     truy vấn mới -> balance vẫn là 100
```

Ở đây T1 và T2 là **hai transaction trên hai connection vật lý khác nhau**. Một transaction có thể tự đọc/ghi vào hàng đã khóa bởi chính nó, nên nếu bạn làm demo "UPDATE rồi UPDATE" trên **cùng connection**, bạn chưa kiểm chứng contention.

### 3.2. Lock timeout không phải transaction timeout

- Lock wait timeout quan tâm **một lần chờ lock**, không nhất thiết giới hạn toàn bộ công việc ở transaction.
- `@Transactional(timeout = 30)` của Spring không đồng nghĩa DB `lock_timeout=30s`.
- Một SQL có thể bị lock timeout trong khi thời hạn Spring transaction vẫn còn rất nhiều.
- Ngược lại, Spring transaction deadline có thể hết khi code đang tính toán, gọi API khác hoặc chờ thread — không cần chờ database lock.
- Nếu hai giới hạn cùng được thiết lập, lỗi nào đến trước phụ thuộc tình huống thực, driver và cách backend tính timeout.

### 3.3. Khi lock timeout xảy ra, lock của ai được nhả?

Transaction **đang giữ lock** không bị tự động rollback chỉ vì một transaction khác hết thời gian chờ. Transaction W có thể tiếp tục giữ lock cho tới khi W commit/rollback hoặc session kết thúc theo cơ chế DB.

Còn transaction **đang chờ** có thể:

- Chỉ mất statement đang chờ và vẫn có thể tiếp tục transaction, tùy DB/error state.
- Bị database đặt vào trạng thái failed/aborted cho đến khi rollback.
- Bị Spring transaction interceptor rollback toàn bộ nếu exception đi ra khỏi method `@Transactional` và thỏa rollback rules.

Vì vậy phải phân biệt **trạng thái DB** với **rollback policy của Spring**; hai cơ chế có thể cùng dẫn đến rollback nhưng diễn ra ở lớp khác nhau.

## 4. Spring transaction timeout: deadline, không phải máy ngắt thread

### 4.1. @Transactional(timeout = ...)

```java
@Transactional(timeout = 5)
public void processBatch() {
    jdbcTemplate.update(
            "UPDATE locked_account SET balance = ? WHERE id = ?",
            110, 1L);
    // Những JDBC statement tiếp theo chịu budget còn lại
    // của transaction mới do Spring quản lý.
}
```

Đoạn này là fragment, giả định có `jdbcTemplate`. `timeout = 5` có đơn vị **giây**. Ở transaction manager JDBC phù hợp, Spring đặt một deadline khi **khởi tạo transaction vật lý mới** và truyền thời gian còn lại xuống mỗi statement được tạo qua Spring JDBC.

Điểm đặc biệt:

- `@Transactional(timeout = 5)` không phải bộ định thời tự động gọi `Thread.interrupt()` sau 5 giây.
- Nếu method `Thread.sleep(10_000)` rồi **không thực hiện thêm JDBC statement**, chỉ riêng annotation không bảo đảm một lệnh hủy thread hoặc một `TransactionTimedOutException` ngay sau 5 giây. Cần hiểu lifecycle manager/driver.
- Với `JdbcTemplate`, khi tạo statement, Spring sử dụng cơ chế `DataSourceUtils.applyTransactionTimeout(...)` và `Statement.setQueryTimeout(...)`. Nếu deadline đã hết, việc tính thời gian còn lại có thể ném `TransactionTimedOutException` **trước khi statement được execute**.
- Một SQL đang chạy có thể được driver/server hủy khi query timeout được áp dụng; việc hủy có đúng hạn không phụ thuộc driver và database.
- Commit có thể còn mất thời gian, và một timeout mềm không đảm bảo hard end-to-end bound tuyệt đối cho mọi thao tác.

### 4.2. Deadline được áp dụng ở đâu?

```text
@Transactional(timeout = 5) proxy bắt đầu transaction
    |
    +-- t=0s: INSERT A        -> statement budget còn gần 5s
    |
    +-- t=2s: UPDATE B        -> statement budget còn gần 3s
    |
    +-- t=4s: SELECT C        -> statement budget còn gần 1s
    |
    +-- t=6s: UPDATE D        -> deadline đã hết
              |
              +-- JdbcTemplate/DataSourceUtils có thể ném
                  TransactionTimedOutException trước execute
    |
    +-- transaction interceptor rollback nếu exception thoát ra
```

Thời điểm timeout là của **transaction mới bắt đầu**, không phải thời gian 5 giây riêng cho từng query. `Statement#setQueryTimeout` là khả năng phía JDBC mà Spring tận dụng để giới hạn câu lệnh dựa trên **thời gian còn lại**.

Spring JDBC `JdbcTemplate` tự xử lý transaction-bound `Connection` và statement settings. Nếu code tạo raw `Statement` thủ công, nó không tự nhận mọi timeout giống `JdbcTemplate`; khi dùng raw JDBC ở transaction do Spring quản lý, hãy lấy connection qua `DataSourceUtils` và gọi `DataSourceUtils.applyTransactionTimeout(statement, dataSource)` với các statement tự tạo (hoặc dùng proxy connection thích hợp). Không tùy tiện gọi `commit/rollback` trên connection do Spring quản lý.

### 4.3. Propagation quyết định ai đặt deadline

| Propagation | Khi có outer transaction | Deadline mới? |
| --- | --- | --- |
| `REQUIRED` | Tham gia transaction outer | **Không** tự thay đổi deadline của physical transaction hiện có |
| `REQUIRES_NEW` | Suspend outer, mở transaction vật lý mới | Có thể đặt deadline riêng |
| `NESTED` | Dùng savepoint trong physical transaction chung | Không tự mở transaction vật lý có deadline độc lập |
| Không có outer + `REQUIRED` | Mở transaction mới | Áp dụng `timeout` nếu manager hỗ trợ |
| Self-invocation `this.method()` trong cùng bean | Có thể không đi qua proxy method | Timeout metadata của method được gọi có thể không được áp dụng |

Ví dụ:

```java
@Transactional(timeout = 20)
public void outer() {
    otherService.inner(); // bean khác, inner REQUIRED timeout=2
}

// Ở bean otherService:
@Transactional(propagation = Propagation.REQUIRED, timeout = 2)
public void inner() {
    // Tham gia outer physical transaction: không nhận deadline 2s riêng.
}
```

Hai đoạn là fragments minh họa. Không thể dùng inner `@Transactional(timeout=2)` để "rút ngắn" deadline outer `timeout=20` khi inner chỉ tham gia transaction đó. Nếu thật sự cần giới hạn cho một SQL riêng, cần query/statement timeout phù hợp; nếu cần transaction độc lập, cân nhắc `REQUIRES_NEW` với hệ quả riêng về connection và commit.

### 4.4. TransactionTemplate và XML

Programmatic transaction:

```java
TransactionTemplate template = new TransactionTemplate(transactionManager);
template.setTimeout(5);

template.executeWithoutResult(status -> {
    jdbcTemplate.update(
            "UPDATE locked_account SET balance = ? WHERE id = ?",
            120, 1L);
});
```

Đoạn minh họa giả định có `PlatformTransactionManager transactionManager` và `JdbcTemplate jdbcTemplate`. `TransactionTemplate` mặc định dùng `REQUIRED` nên chỉ có deadline riêng khi nó tạo physical transaction mới.

XML transaction advice:

```xml
<tx:advice id="txAdvice" transaction-manager="transactionManager">
    <tx:attributes>
        <tx:method name="update*" propagation="REQUIRED" timeout="5"/>
        <tx:method name="find*" read-only="true"/>
        <tx:method name="*"/>
    </tx:attributes>
</tx:advice>
```

Đây là fragment cấu hình; cần namespace, bean manager và AOP advisor/pointcut. `timeout="5"` là **5 giây**. Đừng nhầm với H2 `LOCK_TIMEOUT=500` là **500 mili giây**.

## 5. Query timeout và statement cancellation: lệnh đang chạy bị hủy

### 5.1. JDBC Statement#setQueryTimeout

`Statement#setQueryTimeout(int seconds)` yêu cầu driver giới hạn số giây một statement được phép thực thi:

```java
JdbcTemplate template = new JdbcTemplate(dataSource);
template.setQueryTimeout(2);

template.queryForObject(
        "SELECT COUNT(*) FROM locked_account", Integer.class);
```

Đây là fragment; cần `DataSource`. `JdbcTemplate.setQueryTimeout(2)` áp dụng timeout cho statement mà template tạo, nếu không bị deadline transaction đang hoạt động override. **Thời gian còn lại của transaction Spring thường được ưu tiên** khi `JdbcTemplate` đang ở trong transaction có timeout.

Lưu ý:

- Driver có thể làm tròn thời gian, dùng cơ chế server-side hoặc client-side cancellation; khả năng thực thi và thời điểm báo lỗi khác nhau.
- `Statement.setQueryTimeout(0)` theo JDBC thường biểu thị không giới hạn query timeout ở mức JDBC, nhưng có thể vẫn bị **server-side timeout** hay **transaction deadline** chặn.
- Statement/query timeout không đồng nghĩa lock timeout: statement bị chặn vì query chạy lâu, bao gồm có thể do chờ lock, nhưng lock timeout chỉ đếm quá trình lấy lock.
- Nếu database ném lỗi làm transaction aborted, không thể chỉ catch rồi tiếp tục query như bình thường.

### 5.2. Statement.cancel() là một yêu cầu hủy

JDBC có API:

```java
// Fragment: controller thread đang nắm một Statement còn chạy.
// Driver và database quyết định cách hỗ trợ cancellation thực tế.
statement.cancel();
```

Đây là fragment **không chạy độc lập**. Ý nghĩa:

- `cancel()` yêu cầu hủy statement đang execute; không có bảo đảm cross-driver rằng lệnh sẽ dừng tức thì.
- Một số driver gửi lệnh cancel tới DB server. Có thể còn độ trễ mạng và thời gian backend dừng xử lý.
- `statement.close()` và `connection.close()` cũng không nên được coi là cơ chế thay thế transaction rollback an toàn nếu chưa kiểm tra driver/pool.
- Sau cancel, có thể cần rollback transaction và loại bỏ connection lỗi; quyết định dựa trên DB error state.

### 5.3. Future.cancel(true) / Thread.interrupt() không chắc hủy JDBC

`Future.cancel(true)` cố ngắt thread đang chạy nếu được phép, nhưng **JDBC driver không có nghĩa vụ tự biến mọi thread interrupt thành SQL cancel**. Thread có thể vẫn chặn tại network read, hoặc DB vẫn đang chạy query. Nếu request HTTP bị client đóng, transaction JDBC cũng không nhất thiết tự dừng.

Khi cần hủy SQL đang chạy, đặt giới hạn nhiều lớp và test với driver thật:

1. DB-side statement/lock timeout phù hợp.
2. JDBC `Statement.setQueryTimeout(...)` trên từng statement.
3. Spring transaction timeout cho toàn scope, khi tạo transaction mới.
4. Connection/socket/network timeout và circuit breaker/request timeout ở lớp riêng.
5. Trong tình huống chủ động cancel, dùng API hỗ trợ và chứng minh backend thực sự kết thúc statement; sau đó cleanup transaction/connection.

**Đừng** tự động nhận diện `CancellationException` của Java Future là bằng chứng SQL đã rollback trên database.

### 5.4. JDBC và Spring exception taxonomy

| Hiện tượng | Exception/diagnostic có thể thấy | Chú ý |
| --- | --- | --- |
| Spring nhận ra deadline transaction đã hết | `TransactionTimedOutException` | Có thể xảy ra **trước** khi SQL mới chạy |
| JDBC statement bị timeout/cancel | `SQLTimeoutException` hoặc `SQLException` | Lỗi từ driver, SQLState/error code khác DB |
| Spring dịch JDBC timeout | `QueryTimeoutException` hoặc subtype `DataAccessException` khác | Không nên assert subtype cố định cho mọi DB/driver |
| Lock không lấy được | `CannotAcquireLockException`, `PessimisticLockingFailureException`, `DataAccessException` khác | Cần xem root `SQLException` để biết lỗi khóa hay lỗi query khác |
| Transaction bị rollback-only ngoài dự kiến | `UnexpectedRollbackException` | Thường xuất hiện ở outer commit, không phải lock timeout gốc |
| Pool không cấp được connection kịp | Exception của pool/driver | Không đồng nghĩa SQL đã chờ row lock |
| Deadlock DB chọn một transaction làm nạn nhân | SQLState/vendor-specific exception | Khác tình huống chỉ đợi khóa quá lâu |

Spring không đảm bảo **một** exception class tương đương **một** mã SQL duy nhất ở tất cả backend. Dùng `SQLException.getSQLState()`, `getErrorCode()`, exception chain và logs để phân loại. Tránh in raw SQL có secret/PII vào log.

## 6. Khác biệt DBMS: nơi hủy statement, nơi abort cả transaction

### 6.1. H2: LOCK_TIMEOUT tính bằng mili giây

H2 cho phép:

```sql
SET LOCK_TIMEOUT 500;
```

Lệnh đặt thời gian chờ khóa tối đa **500 ms** cho **session hiện tại**. Nó không commit transaction và rollback cũng không tự khôi phục thiết lập session. Có thể khai báo trong JDBC URL của ví dụ:

```properties
spring.datasource.url=jdbc:h2:mem:lock_lab;DB_CLOSE_DELAY=-1;LOCK_TIMEOUT=350
```

Như vậy các connection mới của demo được thiết lập giới hạn chờ khóa 350 ms. Khi statement không lấy được lock kịp, H2 thường đưa `SQLException` có mã `50200` (`LOCK_TIMEOUT_1`). Spring có thể dịch sang một subtype `DataAccessException`; không hardcode loại ngoại lệ Spring.

**Cẩn thận:** Đổi session `SET LOCK_TIMEOUT` thủ công trên connection từ pool có thể ảnh hưởng request kế tiếp nếu thiết lập chưa được reset. Trong ví dụ dùng URL để tránh thay đổi tạm thời riêng từng phiên trong method nghiệp vụ.

Tài liệu: https://h2database.com/html/commands.html và https://h2database.com/javadoc/org/h2/api/ErrorCode.html

### 6.2. PostgreSQL: lock_timeout và statement_timeout riêng biệt

PostgreSQL có hai thiết lập server-side quan trọng:

```sql
-- Ví dụ khi đang ở trong một transaction PostgreSQL.
SET LOCAL lock_timeout = '300ms';
SET LOCAL statement_timeout = '2s';
```

- `lock_timeout`: hủy statement nếu **chờ một lần lấy lock** quá lâu; không áp dụng cho thời gian CPU/IO của phần khác trong query.
- `statement_timeout`: giới hạn thời gian xử lý statement trên server, bao gồm cả chờ lock.
- `SET LOCAL` chỉ ảnh hưởng transaction hiện tại; tránh rò session settings khi dùng connection pool.
- Khi cả hai bật, nếu `statement_timeout` nhỏ hơn hoặc bằng `lock_timeout`, statement timeout thường xảy ra trước; cần thiết kế ngưỡng hợp lý.
- Một lỗi SQL trong PostgreSQL thường khiến transaction hiện hành ở trạng thái **failed** cho đến khi rollback, trừ trường hợp đã dùng savepoint và xử lý thích hợp. Catch `DataAccessException` rồi thực thi SQL mới mà không rollback thường tiếp tục lỗi.
- Ví dụ SQLState: `55P03` liên quan `lock_not_available`, `57014` liên quan `query_canceled`. Không cố dùng mã lỗi như định nghĩa chung JDBC cho mọi DB.

PostgreSQL còn có `idle_in_transaction_session_timeout` để chấm dứt session mở transaction nhưng idle quá lâu; các phiên bản hiện đại cũng có `transaction_timeout` phía server. Những setting này **khác** Spring `@Transactional(timeout=...)` và cần xem tài liệu đúng phiên bản deployed.

Tài liệu: https://www.postgresql.org/docs/current/runtime-config-client.html và https://www.postgresql.org/docs/current/errcodes-appendix.html

### 6.3. MySQL InnoDB: lock wait timeout thường chỉ rollback statement

MySQL InnoDB có:

```sql
-- Ví dụ khi dùng đúng MySQL InnoDB:
SET SESSION innodb_lock_wait_timeout = 3;
```

`innodb_lock_wait_timeout` tính bằng **giây** và áp dụng chủ yếu cho chờ row lock của InnoDB; mặc định có thể khác cấu hình ứng dụng. Lỗi điển hình: `ERROR 1205 (HY000)`.

Theo tài liệu MySQL 8.4, khi lock wait timeout:

- **Mặc định**, InnoDB rollback **statement đang chờ**, không nhất thiết rollback **toàn transaction**.
- Nếu cấu hình server `innodb_rollback_on_timeout`, database có thể rollback toàn transaction.
- **Deadlock** khác lock wait timeout: InnoDB thường phát hiện deadlock và rollback transaction được chọn làm nạn nhân.
- Dù InnoDB chỉ hủy statement, nếu exception RuntimeException **thoát ra qua Spring @Transactional proxy**, Spring mặc định sẽ rollback transaction của method. Khi exception được catch **bên trong** transactional method, transaction có thể tiếp tục theo quy tắc InnoDB, nhưng phải đánh giá trạng thái và invariant nghiệp vụ cẩn thận.

Lỗi phổ biến: đọc tài liệu "statement only rollback" rồi kết luận một Spring transactional method sẽ commit mọi INSERT trước lock timeout. Điều đó **không đúng mặc định** nếu lỗi database được Spring dịch thành `DataAccessException` (unchecked) và nó thoát ra qua proxy.

Tài liệu: https://dev.mysql.com/doc/refman/8.4/en/innodb-parameters.html và https://dev.mysql.com/doc/refman/8.4/en/innodb-error-handling.html

### 6.4. SQL Server: SET LOCK_TIMEOUT trong session

SQL Server hỗ trợ:

```sql
SET LOCK_TIMEOUT 500; -- 500 milliseconds
```

- `500` nghĩa là đợi lock tối đa 500 **ms**.
- `0` nghĩa là không đợi; `-1` thường là mặc định đợi vô thời hạn.
- Setting là **session-scoped**, có thể tồn tại tới khi session kết thúc/đổi setting; khi dùng pool cần xử lý việc reset.
- Lỗi lock timeout thường có mã `1222`; kiểm tra SQL Server docs/driver cho loại exception cụ thể.
- Trạng thái transaction sau lỗi cần kiểm tra phù hợp với `XACT_STATE()`, `XACT_ABORT` và ngữ cảnh code; đừng mặc định có thể tiếp tục và commit.

Tài liệu: https://learn.microsoft.com/en-us/sql/t-sql/statements/set-lock-timeout-transact-sql

### 6.5. Bảng so sánh thực dụng

| Backend/cơ chế | Ví dụ cấu hình | Đơn vị | Điều nên kiểm chứng |
| --- | --- | --- | --- |
| H2 session lock wait | `SET LOCK_TIMEOUT 350` | ms | Lỗi `50200`, transaction/connection giữ lock có còn mở? |
| PostgreSQL | `SET LOCAL lock_timeout='350ms'` | ms | Transaction có vào trạng thái failed? SQLState nào? |
| PostgreSQL statement | `SET LOCAL statement_timeout='2s'` | s/ms | Câu lệnh bị cancel dù không chờ lock? |
| MySQL InnoDB | `innodb_lock_wait_timeout=3` | giây | Statement-only rollback mặc định và ảnh hưởng của Spring interceptor |
| SQL Server | `SET LOCK_TIMEOUT 350` | ms | Session setting, transaction state, error 1222 |
| Spring `@Transactional(timeout=3)` | Annotation/manager | giây | Có tạo transaction mới không? JDBC statement nhận deadline? |
| Spring `JdbcTemplate.setQueryTimeout(3)` | JDBC statement | giây | Driver có tuân thủ? Deadline transaction có override không? |

Không dùng bảng này làm bảng cấu hình copy/paste cho toàn DBMS. Cùng một timeout numeric value nhưng **đơn vị và hành vi có thể khác**; phải đối chiếu tài liệu vendor/version trước khi chạy trên production.

## 7. Dự án Java 17+ chạy được: H2 lock timeout và Spring transaction timeout

Bài thực hành sử dụng Spring Boot **3.5.6**, Java 17+, Spring JDBC, HikariCP và H2 in-memory có tên. Phép thử dùng **hai connection/transaction đồng thời** chứ không mô phỏng bằng cùng một JDBC connection.

**Các kết quả cần chứng minh:**

1. Writer lấy khóa hàng và chưa commit; contender đợi lock quá 350 ms và bị lỗi H2 mã `50200`.
2. Writer rollback; UPDATE của contender đã bị hủy và số dư committed vẫn là `100`.
3. Một transaction riêng có `@Transactional(timeout=1)` INSERT một bản ghi rồi chờ hơn một giây trong Java. Khi gọi `JdbcTemplate` lần kế tiếp, Spring nhận biết deadline đã hết và ném `TransactionTimedOutException`; INSERT trước đó rollback.
4. Không cần đo exact timing của OS hay assert một subtype `DataAccessException` cố định; kiểm tra **mã SQL gốc của H2**, kết quả transaction và dữ liệu cuối.

### 7.1. Cấu trúc dự án

```text
lock-timeout-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── TimeoutApplication.java
    │   │   ├── LockOwnerService.java
    │   │   ├── LockContenderService.java
    │   │   ├── LockExperiment.java
    │   │   └── DeadlineService.java
    │   └── resources/
    │       ├── application.properties
    │       ├── schema.sql
    │       └── data.sql
    └── test/
        └── java/demo/
            └── TimeoutIntegrationTest.java
```

### 7.2. pom.xml

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
    <artifactId>lock-timeout-lab</artifactId>
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

Spring Boot quản lý các dependency phù hợp và tự cấu hình `DataSource`, `JdbcTemplate` và JDBC transaction manager. `spring-boot-starter-test` cho phép chạy JUnit 5/Spring Boot Test.

### 7.3. application.properties và schema/data

**`src/main/resources/application.properties`**

```properties
spring.datasource.url=jdbc:h2:mem:lock_lab;DB_CLOSE_DELAY=-1;LOCK_TIMEOUT=350
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.hikari.maximum-pool-size=5
spring.main.banner-mode=off
app.demo.enabled=true
```

`LOCK_TIMEOUT=350` là **350 ms** của H2, không phải transaction deadline Spring. Pool tối đa 5 connection vì writer giữ một connection đang khóa hàng, contender cần connection thứ hai để thực sự bị lock contention. URL H2 có tên giúp nhiều connection cùng truy cập **một** in-memory database.

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE IF NOT EXISTS locked_account (
    id BIGINT PRIMARY KEY,
    balance INT NOT NULL
);
```

**`src/main/resources/data.sql`**

```sql
INSERT INTO locked_account (id, balance) VALUES (1, 100);
```

Spring Boot khởi tạo schema/data trong embedded H2 trước khi `CommandLineRunner` chạy. Ở ví dụ này chỉ có một dữ liệu gốc `id=1`. Transaction timeout case sử dụng `id=2` nhưng sẽ rollback, vì vậy không tạo dữ liệu mới vĩnh viễn.

### 7.4. LockOwnerService.java — giữ khóa rồi rollback

**`src/main/java/demo/LockOwnerService.java`**

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LockOwnerService {
    private final JdbcTemplate jdbc;

    public LockOwnerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void holdAndRollback(
            CountDownLatch locked,
            CountDownLatch release) {

        // FOR UPDATE lấy lock trước khi thông báo cho contender.
        jdbc.queryForObject(
                "SELECT balance FROM locked_account WHERE id = 1 FOR UPDATE",
                Integer.class);

        jdbc.update(
                "UPDATE locked_account SET balance = 200 WHERE id = 1");

        // Transaction vẫn đang mở, chưa commit/rollback.
        locked.countDown();

        try {
            if (!release.await(15, TimeUnit.SECONDS)) {
                throw new IllegalStateException("owner wait expired");
            }
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("owner interrupted", ex);
        }

        // Phát sinh exception đi qua proxy => rollback update 200.
        throw new IllegalStateException("owner rollback");
    }
}
```

Lời gọi `holdAndRollback` sẽ chạy trong **worker thread**, nhưng vẫn đi qua Spring proxy vì `LockOwnerService` được inject từ Spring container. Transaction được tạo trong worker thread, rồi giữ connection và row lock cho tới khi `release` được mở.

`CountDownLatch` bảo đảm contender chỉ bắt đầu **sau khi writer đã lấy khóa**. Nếu dùng `Thread.sleep(...)` không đồng bộ, test có thể chạy lúc writer chưa khóa hàng và kết quả không ổn định.

### 7.5. LockContenderService.java — cố cập nhật hàng đang bị khóa

**`src/main/java/demo/LockContenderService.java`**

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class LockContenderService {
    private final JdbcTemplate jdbc;

    public LockContenderService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void updateLockedRow() {
        // Trên connection khác, row id=1 vẫn bị transaction owner giữ khóa.
        jdbc.update(
                "UPDATE locked_account SET balance = 300 WHERE id = 1");
    }
}
```

Contender được gọi từ main thread, không có outer transaction. Nó mở transaction/connection riêng. Khi H2 không thể lấy lock trong khoảng 350 ms, JDBC ném lỗi. `JdbcTemplate` chuyển SQLException sang `DataAccessException`; vì đây là unchecked exception và thoát qua transactional interceptor, Spring rollback transaction contender.

Lưu ý: phần xác minh trong `LockExperiment` sẽ tìm **mã lỗi H2 50200 ở chuỗi nguyên nhân SQLException**, không cố định một subtype Spring exception vì translator có thể thay đổi theo driver hoặc phiên bản.

### 7.6. LockExperiment.java — điều phối hai transaction độc lập

**`src/main/java/demo/LockExperiment.java`**

```java
package demo;

import java.sql.SQLException;
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import org.springframework.dao.DataAccessException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

@Component
public class LockExperiment {
    private final LockOwnerService owner;
    private final LockContenderService contender;
    private final JdbcTemplate jdbc;

    public LockExperiment(
            LockOwnerService owner,
            LockContenderService contender,
            JdbcTemplate jdbc) {
        this.owner = owner;
        this.contender = contender;
        this.jdbc = jdbc;
    }

    public record Result(boolean lockTimedOut, int committedBalance) {}

    public Result run() throws Exception {
        CountDownLatch locked = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            Future<?> ownerTask = executor.submit(
                    () -> owner.holdAndRollback(locked, release));

            if (!locked.await(6, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "owner did not acquire lock");
            }

            boolean timedOut = false;

            try {
                contender.updateLockedRow();
            } catch (DataAccessException ex) {
                // H2 LOCK_TIMEOUT_1: error code 50200.
                // Đừng nuốt lỗi SQL không liên quan.
                if (!hasH2LockTimeoutCode(ex)) {
                    throw ex;
                }
                timedOut = true;
            } finally {
                // Nhả owner dù contender lỗi để tránh treo worker.
                release.countDown();
            }

            try {
                ownerTask.get(8, TimeUnit.SECONDS);
                throw new IllegalStateException(
                        "owner completed without rollback");
            } catch (ExecutionException ex) {
                Throwable cause = ex.getCause();
                if (!(cause instanceof IllegalStateException)
                        || !"owner rollback".equals(cause.getMessage())) {
                    throw ex;
                }
            }

            Integer balance = jdbc.queryForObject(
                    "SELECT balance FROM locked_account WHERE id = 1",
                    Integer.class);

            return new Result(
                    timedOut,
                    Objects.requireNonNull(balance));
        } finally {
            release.countDown();
            executor.shutdownNow();
        }
    }

    private static boolean hasH2LockTimeoutCode(Throwable error) {
        for (Throwable current = error;
                current != null;
                current = current.getCause()) {
            if (current instanceof SQLException sql
                    && sql.getErrorCode() == 50200) {
                return true;
            }
        }
        return false;
    }
}
```

Chú giải logic:

1. `executor` mở thread W. Bean `owner` chạy trong transaction W và khóa `id=1`.
2. `locked.await(...)` chờ đến khi khóa đã được lấy; tránh race condition giữa writer và contender.
3. Main thread gọi `contender.updateLockedRow()`, nên `JdbcTemplate` của contender phải lấy connection khác từ Hikari pool.
4. Khi chờ quá 350 ms, H2 ném `SQLException` lỗi `50200`, Spring dịch sang `DataAccessException`.
5. `catch` kiểm tra nguyên nhân thật; nếu là lỗi SQL khác, nó **được ném tiếp** và demo thất bại thay vì báo thành công giả.
6. `release.countDown()` luôn chạy, để owner tiếp tục và ném exception có chủ đích. `Future.get` xác nhận đúng exception `owner rollback`, nghĩa là transaction owner đã kết thúc qua proxy.
7. Chỉ **sau khi cả hai transaction đã xong** mới query `balance`. Lúc này owner đã rollback giá trị 200, contender không ghi được 300, nên giá trị committed là 100.
8. `shutdownNow()` trong `finally` giải phóng executor. Hai latch và timeout ngăn bài lab kẹt vô hạn nếu có sự cố.

**Giới hạn thực nghiệm:** Không nên dùng việc giữ database transaction bằng latch để làm việc nghiệp vụ thật; đó là kỹ thuật **kiểm chứng concurrency**, cố ý khiến transaction giữ lock đủ lâu cho contender chờ.

### 7.7. DeadlineService.java — Spring transaction timeout trước SQL tiếp theo

**`src/main/java/demo/DeadlineService.java`**

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DeadlineService {
    private final JdbcTemplate jdbc;

    public DeadlineService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(timeout = 1)
    public void expireBeforeNextStatement(long id) {
        jdbc.update(
                "INSERT INTO locked_account (id, balance) VALUES (?, ?)",
                id, 800);

        try {
            // Demo giữ code Java lâu hơn transaction deadline 1 giây.
            // Spring không tự ngắt Thread.sleep chỉ vì annotation.
            Thread.sleep(1800);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("deadline demo interrupted", ex);
        }

        // JdbcTemplate tạo statement mới và kiểm tra deadline còn lại.
        // Deadline đã hết -> thường TransactionTimedOutException.
        jdbc.update(
                "UPDATE locked_account SET balance = ? WHERE id = ?",
                801, id);
    }
}
```

Trong method này:

- Spring `@Transactional(timeout=1)` tạo transaction mới vì caller không có outer transaction.
- `INSERT` đầu tiên chạy trước deadline, nhưng **chưa commit**.
- `Thread.sleep(1800)` không phải câu SQL; nó chỉ làm thời gian thực trôi qua. Không có "daemon timeout" nào buộc thread thức dậy đúng giây thứ 1.
- Khi `JdbcTemplate` tạo statement UPDATE tiếp theo, `DataSourceUtils` nhận ra deadline đã quá hạn và phát `TransactionTimedOutException`.
- Exception đi qua transaction interceptor khiến transaction rollback, nên `INSERT id=2` **không còn** trong database.

Demo này cố tình gây timeout **trước khi execute statement mới** để phân biệt Spring transaction deadline với database lock wait timeout. Nó không chứng minh driver có khả năng ngắt mọi SQL đang chạy đúng hạn.

### 7.8. TimeoutApplication.java — chạy và đọc lại kết quả đã commit

**`src/main/java/demo/TimeoutApplication.java`**

```java
package demo;

import java.util.Objects;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.TransactionTimedOutException;

@SpringBootApplication
public class TimeoutApplication {
    public static void main(String[] args) {
        SpringApplication.run(TimeoutApplication.class, args);
    }

    @Bean
    @ConditionalOnProperty(
            name = "app.demo.enabled",
            havingValue = "true",
            matchIfMissing = true)
    CommandLineRunner demo(
            LockExperiment experiment,
            DeadlineService deadlines,
            JdbcTemplate jdbc) {

        return args -> {
            LockExperiment.Result result = experiment.run();

            System.out.println(
                    "H2 lock timeout observed: " + result.lockTimedOut());
            System.out.println(
                    "balance after owner rollback: "
                            + result.committedBalance());

            boolean transactionTimedOut = false;

            try {
                deadlines.expireBeforeNextStatement(2L);
            } catch (TransactionTimedOutException ex) {
                transactionTimedOut = true;
            }

            System.out.println(
                    "Spring tx timeout observed: " + transactionTimedOut);

            Integer count = jdbc.queryForObject(
                    "SELECT COUNT(*) FROM locked_account WHERE id = 2",
                    Integer.class);

            System.out.println(
                    "row 2 after timeout: "
                            + (Objects.requireNonNull(count) == 0
                                    ? "absent" : "present"));
        };
    }
}
```

Trong demo, `CommandLineRunner` không có `@Transactional`. Vì thế:

- `LockOwnerService` và `LockContenderService` sở hữu transaction riêng trong hai thread.
- `DeadlineService.expireBeforeNextStatement` sở hữu transaction với deadline 1 giây.
- Các truy vấn SELECT ở `LockExperiment`/`TimeoutApplication` thực hiện **sau khi transaction đã kết thúc**, không đánh giá dữ liệu chưa commit trong cùng connection.

`@ConditionalOnProperty` giúp tắt runner lúc chạy integration test để test không tự kích hoạt những cuộc thử nghiệm concurrency khi application context vừa khởi động.

### 7.9. Lệnh chạy và stdout dự kiến

Yêu cầu JDK 17+, Maven 3.6.3+ và dependency có sẵn hoặc có thể tải về. Tại thư mục chứa `pom.xml`:

```bash
mvn spring-boot:run
```

Các dòng do chính ứng dụng in, không tính Spring/Maven logs:

```text
H2 lock timeout observed: true
balance after owner rollback: 100
Spring tx timeout observed: true
row 2 after timeout: absent
```

Bảng đối chiếu:

| Quan sát | Vì sao? |
| --- | --- |
| `H2 lock timeout observed: true` | Contender không thể lấy row lock trong 350 ms; SQL gốc có H2 code `50200` |
| `balance after owner rollback: 100` | Owner rollback giá trị tạm 200; contender không thực hiện thành công UPDATE 300 |
| `Spring tx timeout observed: true` | Transaction deadline 1 giây đã hết trước JDBC UPDATE tiếp theo; Spring phát `TransactionTimedOutException` |
| `row 2 after timeout: absent` | INSERT id=2 thuộc transaction đã rollback |

**Giới hạn:** Đầu ra trên là **kỳ vọng thiết kế với H2/Spring/JDK đã nêu**, không phải bản ghi stdout đã chạy thực tế tại thời điểm viết. Khác biệt OS scheduling, CPU quá tải, phiên bản driver và pool có thể cần tăng khoảng đợi latch/giảm tải môi trường test. Tuy nhiên, demo không dựa vào việc contender "vừa kịp" tranh lock: latch bảo đảm transaction owner đã khóa hàng trước khi contender bắt đầu.

## 8. Integration test xác minh transaction và SQL error

**`src/test/java/demo/TimeoutIntegrationTest.java`**

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.TransactionTimedOutException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(properties = "app.demo.enabled=false")
class TimeoutIntegrationTest {
    @Autowired
    private LockExperiment experiment;

    @Autowired
    private DeadlineService deadlines;

    @Autowired
    private JdbcTemplate jdbc;

    @Test
    void lockWaitTimesOutAndBothTransactionsLeaveOriginalValue()
            throws Exception {

        LockExperiment.Result result = experiment.run();

        assertTrue(result.lockTimedOut());
        assertEquals(100, result.committedBalance());
    }

    @Test
    void springTransactionDeadlineRollsBackPreviousInsert() {
        assertThrows(
                TransactionTimedOutException.class,
                () -> deadlines.expireBeforeNextStatement(20L));

        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM locked_account WHERE id = 20",
                Integer.class);
        assertEquals(0, count);
    }
}
```

Chạy:

```bash
mvn test
```

**Kỳ vọng:** hai test pass trên H2 với cấu hình này. Test dùng ID=20 để không trùng với ID=2 của runner (dù runner đã được tắt bởi property `app.demo.enabled=false`).

**Vì sao không đặt `@Transactional` trên test class?** Nếu Spring TestContext tự mở test-managed transaction, các service `REQUIRED` có thể **tham gia transaction test**, làm thay đổi deadline và ranh giới rollback. Còn test lock contention thậm chí có thể dùng nhầm transaction/connection đang giữ khóa. Vì vậy test được thực hiện từ caller **không có outer transaction**, đúng với thiết kế demo.

### Kiểm chứng lỗi khóa không bị nhầm với lỗi SQL khác

Thay vì chỉ:

```java
assertThrows(DataAccessException.class, () -> contender.updateLockedRow());
```

bài sử dụng `hasH2LockTimeoutCode` để tìm `SQLException.getErrorCode()==50200` trong chuỗi cause. Vì `DataAccessException` có thể đại diện cho nhiều lỗi SQL (câu lệnh sai, constraint, connection), assert subtype rộng đơn thuần sẽ tạo **false positive**.

Điều này cũng không có nghĩa code production phải hardcode mã H2. Trong hệ thống thật, hãy kiểm tra vendor error codes/SQLState, xây chiến lược phân loại phù hợp backend và log nguyên nhân gốc an toàn.

### Test sau rollback quan trọng hơn chỉ assert timeout

Nếu method ném `TransactionTimedOutException` nhưng bạn không SELECT lại, test mới chứng minh có exception, chưa chứng minh được thay đổi trước đó bị rollback. Ở đây assert dữ liệu id=20 **không còn** sau proxy invocation để chứng minh transaction đã hoàn tất theo chính sách rollback.

## 9. Retry: thử lại ở transaction mới, không che lỗi đã có

Khi lock wait timeout hoặc deadlock xảy ra, một số tác vụ idempotent có thể retry. Tuy nhiên, retry **không** nên đặt tùy tiện bên trong transaction đang lỗi hoặc đã bị đánh dấu rollback-only.

### 9.1. Luồng retry hợp lý

```text
Request
   |
   +-- Attempt 1: tạo transaction mới
   |      UPDATE ... -> lock timeout
   |      rollback transaction
   |
   +-- backoff ngắn + jitter
   |
   +-- Attempt 2: tạo transaction mới
   |      UPDATE ... -> thành công
   |      commit
   |
   +-- trả kết quả
```

Điều kiện:

- Mỗi lần thử nên đi qua **transaction proxy riêng**, hoặc dùng `TransactionTemplate` tạo transaction mới cho từng attempt.
- Với DB đã abort transaction (ví dụ PostgreSQL sau một lỗi SQL), **không retry SQL trong cùng transaction bị abort**.
- Chỉ retry loại lỗi được xác định là transient (lock timeout/deadlock phù hợp), không retry syntax error hay lỗi nghiệp vụ không thể khắc phục bằng chờ.
- Đặt **số lần thử tối đa**, backoff/jitter, tổng ngân sách request; không retry vô hạn.
- Cần **idempotency**: không gửi email/chuyển tiền/phát sự kiện trùng nếu attempt trước đã có side effect ngoài DB.
- Trường hợp transaction commit đã xảy ra nhưng response bị mất, không được mặc định retry từ đầu mà không kiểm tra idempotency key.

### 9.2. Ví dụ pseudocode đúng boundary

```java
// Pseudocode: không phải class Java độc lập.
for (int attempt = 1; attempt <= maxAttempts; attempt++) {
    try {
        // worker là một Spring bean khác, method @Transactional.
        worker.performOneTransaction();
        break;
    } catch (TransientDataAccessException ex) {
        if (attempt == maxAttempts) {
            throw ex;
        }
        backoffWithJitter(attempt);
    }
}
```

Đoạn này minh họa vị trí retry **ở ngoài transactional method**. `TransientDataAccessException` là một họ lỗi Spring hữu ích để xem xét, nhưng **không phải mọi** exception subtype đều retry được, và vendor translator không luôn phân loại thống nhất. `maxAttempts`, `backoffWithJitter` và `worker` là phần cần triển khai theo ứng dụng.

Nếu dùng `@Retryable`, phải cài/khởi tạo Spring Retry và đảm bảo AOP advice ordering để mỗi retry attempt thực sự có transaction mới. Bài lab không dùng dependency Spring Retry nên không giả định annotation đó sẽ hoạt động chỉ bằng copy code.

## 10. Chiến lược timeout nhiều lớp trong thực tế

Một bộ cấu hình nên thể hiện rõ **ngân sách thời gian và quan hệ giữa chúng**. Ví dụ API chỉ có khoảng 5 giây xử lý:

| Lớp | Ví dụ ngân sách | Ý nghĩa |
| --- | --- | --- |
| Pool acquisition | 0,5 giây | Không đợi connection quá lâu |
| DB lock wait | 0,7 giây | Thoát sớm nếu row bị khóa lâu |
| DB/JDBC statement | 2 giây | Giới hạn statement chậm nói chung |
| Spring transaction | 4 giây | Deadline tổng cho transaction mới |
| HTTP request | 5 giây | Ngân sách caller/client |

Đây chỉ là **ví dụ thiết kế**, không phải thông số chuẩn. Điều quan trọng là các timeout nên nhất quán và hiểu **cách đo thời gian**: DB-side deadline có thể kiểm soát việc thực thi thực tế tốt hơn một timeout chỉ được kiểm tra khi Java tạo statement mới; còn network timeout liên quan socket, không phải quy tắc rollback.

Không cộng đơn giản các mốc thành một hard SLA nếu driver không hỗ trợ hủy đúng hạn. Hãy đo p95/p99 latency, blocked time, lock graph, pool wait và commit latency trong môi trường thực.

### Nguyên tắc giảm lock contention trước khi tăng timeout

1. Giữ transaction **ngắn**; không chờ HTTP/network/user input khi đang giữ row lock.
2. Bảo đảm UPDATE/SELECT FOR UPDATE dùng index thích hợp; query quét nhiều hàng có thể giữ khóa nhiều hơn dự kiến.
3. Giữ thứ tự khóa nhất quán giữa các luồng để giảm deadlock.
4. Với tác vụ dài, chia batch hợp lý và công khai quy tắc atomicity.
5. Dùng isolation phù hợp; đừng hạ xuống mức yếu chỉ để giảm blocking mà chưa xét correctness.
6. Dùng optimistic locking/version khi mô hình nghiệp vụ cho phép, thay vì luôn giữ pessimistic lock.
7. Với queue workers, cân nhắc `SKIP LOCKED`/`NOWAIT` nếu vendor hỗ trợ và semantics bỏ qua công việc phù hợp.
8. Theo dõi slow-query log, deadlock log, lock wait metrics và thời gian giữ transaction.

## 11. Các tình huống lỗi phổ biến

### 11.1. @Transactional(timeout=1) không tự ngắt Thread.sleep(10s)

**Nguyên nhân:** Spring transaction timeout là deadline/resource timeout, không phải Java watchdog tự interrupt code. `JdbcTemplate` có thể phát hiện hết hạn ở statement tiếp theo. Nếu method chỉ sleep rồi return, không được suy ra hard timeout đã tự hủy.

**Cách kiểm chứng:** Trong test, gọi JDBC statement sau khi deadline đã hết; đối chiếu exception và database rollback, như `DeadlineService`.

### 11.2. Query timeout được cấu hình nhưng SQL vẫn chạy lâu

**Nguyên nhân có thể:** Driver/backend không hỗ trợ cancellation đúng cách, câu lệnh đang chờ mạng, đang commit, hoặc logic ứng dụng nằm ngoài SQL. Một số timeout được làm tròn theo giây.

**Cách xử lý:** Kiểm tra driver/server logs, JDBC `Statement#setQueryTimeout`, DB-side `statement_timeout`, network timeout và thử tình huống thật. Không hứa SQL luôn dừng chính xác tại mốc timer.

### 11.3. Lock timeout bị bắt bên trong transactional method rồi vẫn commit

**Nguyên nhân:** InnoDB mặc định có thể chỉ rollback statement bị timeout. Nếu exception bị catch trước khi tới transaction interceptor và backend vẫn cho phép tiếp tục, Spring chỉ thấy method return bình thường nên có thể commit phần việc trước đó.

**Cách xử lý:** Đối với lỗi khóa trên đường ghi dữ liệu nguyên tử, thường để exception thoát qua boundary hoặc chủ động đánh dấu rollback-only rồi xử lý ở caller. Riêng PostgreSQL có failed transaction state sau error, không được tiếp tục mà không rollback/savepoint thích hợp.

### 11.4. Inner REQUIRED có timeout ngắn nhưng không phát huy

**Nguyên nhân:** Inner tham gia physical transaction do outer đã mở. Timeout của inner không tự thay thời hạn outer.

**Cách xử lý:** Đặt timeout tại boundary sở hữu transaction, hoặc đặt query timeout cho operation, cân nhắc transaction mới chỉ khi nghiệp vụ thực sự cho phép.

### 11.5. Hai thử nghiệm không thật sự dùng hai connection

Nếu reader/contender chạy trong cùng transaction hoặc cùng JDBC connection với writer, chúng có thể không chờ lock của chính mình. Dùng hai thread, hai Spring proxy invocations và pool tối thiểu hai connection, như demo; xác nhận transaction boundary và dữ liệu.

### 11.6. Cấu hình số đúng nhưng đơn vị sai

`@Transactional(timeout=3)` là **3 giây**; H2 `SET LOCK_TIMEOUT 300` là **300 ms**; MySQL `innodb_lock_wait_timeout=3` là **3 giây**; SQL Server `SET LOCK_TIMEOUT 300` là **300 ms**. Sai đơn vị khiến request chờ quá lâu hoặc thất bại quá sớm.

### 11.7. Catch tất cả DataAccessException và retry mọi lỗi

Lỗi syntax, constraint, permission và schema không được giải quyết bằng chờ. Phân loại theo SQLState/vendor code và đánh giá retryable; retry tại transaction mới, có giới hạn và idempotency.

### 11.8. Nghi ngờ deadlock nhưng chỉ có lock wait timeout

Deadlock cần chu trình chờ giữa các transaction; lock wait timeout có thể chỉ là transaction A giữ khóa lâu trong khi B đợi một chiều. Tìm đồ thị lock/deadlock log và root SQL error code; đừng thay thuật toán chỉ vì message có chữ "lock".

### 11.9. Chỉ xem exception mà không nhìn data cuối

Một statement timeout có thể chỉ hủy statement phía DB; một transaction mới có thể bị Spring rollback nếu unchecked exception thoát ra; hoặc một transaction đã lỗi bị đánh dấu rollback-only. Phải đợi outermost transaction kết thúc và SELECT từ connection/transaction mới.

### 11.10. Canceled future được hiểu nhầm đã rollback

`Future.cancel(true)` hoặc client disconnect không bảo đảm SQL/cơ sở dữ liệu đã ngừng xử lý. Cần có cancellation/timeout ở JDBC/DB thực, theo dõi completion và rollback boundary.

### 11.11. Mọi timeout đều được ghi log là QueryTimeoutException

Spring JDBC exception translator phụ thuộc driver/SQLState/errorCode; H2 lock timeout có thể được dịch theo cách khác PostgreSQL hoặc MySQL. Log root cause và thời hạn nào đang được áp dụng. `TransactionTimedOutException` cũng **không phải** `DataAccessException` chung của JDBC query errors.

### 11.12. Thay đổi session timeout trên connection pool mà không reset

PostgreSQL `SET`, SQL Server `SET LOCK_TIMEOUT`, H2 `SET LOCK_TIMEOUT` có thể bám theo session/connection. Nếu tiếp tục dùng pooled connection, request khác có thể kế thừa setting cũ. Dùng `SET LOCAL` trong transaction khi vendor hỗ trợ hoặc cơ chế initialization/reset của pool.

### 11.13. Dùng test @Transactional tạo outer transaction ngoài ý muốn

Spring TestContext có thể mở test-managed transaction khi gắn `@Transactional` trên test. `REQUIRED` của service sẽ tham gia transaction test và timeout/commit có thể ở boundary khác. Demo và tests ở đây **không** đánh dấu test class `@Transactional`.

### 11.14. Giữ lock sau khi timeout của contender

Lock của transaction **owner** có thể vẫn tồn tại dù contender đã timeout. Nếu owner không commit/rollback, các request khác tiếp tục bị blocked. Quan sát và xử lý **transaction đang giữ lock**, không chỉ các transaction đang chờ.

## 12. Quy trình chẩn đoán production

Khi nhận một exception liên quan timeout/cancel:

1. **Ghi thời điểm và request correlation ID.** Không log credential, thông tin nhạy cảm hoặc đầy đủ bind parameters nếu không cần.
2. **Phân loại lớp:** không lấy được pool connection, lock wait timeout, statement/query timeout, Spring transaction deadline, network failure hay deadlock?
3. **Lấy root SQLException:** `getSQLState()`, `getErrorCode()`, message gốc; đối chiếu SQLState/vendor error mapping.
4. **Quan sát transaction manager thực tế:** `DataSourceTransactionManager`/`JpaTransactionManager`/JTA? Có bao nhiêu DataSource và manager?
5. **Xác nhận proxy boundary/propagation:** method `@Transactional` thật sự được gọi qua proxy? Inner `REQUIRED` có tham gia outer? Timeout được đặt ở scope sở hữu transaction không?
6. **Kiểm tra server/session settings:** PostgreSQL lock_timeout/statement_timeout, MySQL InnoDB timeout, SQL Server session LOCK_TIMEOUT, H2 LOCK_TIMEOUT.
7. **Đối chiếu statement settings:** `JdbcTemplate.setQueryTimeout`, JDBC `Statement.setQueryTimeout` và thời gian còn lại do Spring áp xuống.
8. **Kiểm tra thời gian giữ khóa:** transaction nào giữ lock, statement nào đang wait, query plan/index và transaction idle.
9. **Xác định trạng thái sau lỗi:** DB transaction failed/aborted? Spring transaction rollback-only? Có thể retry một statement hay phải rollback transaction toàn bộ?
10. **Đọc committed state sau boundary:** database/tenant/schema chính xác, không dựa vào JPA cache hoặc read replica chậm.
11. **Thiết kế phục hồi:** retry có giới hạn trong transaction mới, backoff, idempotency, hoặc trả lỗi nghiệp vụ thích hợp.
12. **Bổ sung regression test** trên đúng DB/driver phiên bản production, không chỉ H2.

Đối với Spring Boot, có thể bật log chẩn đoán trong môi trường thử nghiệm:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
logging.level.org.springframework.jdbc.core=DEBUG
```

Log Spring hỗ trợ xác định scope và SQL execution, nhưng lock wait thực sự thường phải xem thêm **DB-side lock views / slow query log / deadlock diagnostics**. Không bật DEBUG/TRACE vô thời hạn trên production nếu chứa SQL/bind values hoặc làm tăng chi phí.

## 13. Câu hỏi và bài tập

**Bài 1 — Timeout nào?** A giữ `SELECT ... FOR UPDATE` trên id=1 trong 10 giây. B cố UPDATE id=1, DB đặt lock timeout 500 ms. B bị lỗi sau khoảng nửa giây. Có phải Spring `@Transactional(timeout=...)` đã hết?

**Đáp án:** Không thể kết luận. Đây là **lock wait timeout** của DB; Spring transaction timeout có thể đang lớn hơn hoặc không cấu hình.

**Bài 2 — Hủy statement có rollback toàn transaction không?** MySQL InnoDB timeout chờ row lock; exception bị catch bên trong `@Transactional` và method return bình thường.

**Đáp án:** InnoDB mặc định chỉ rollback statement timeout; nếu transaction vẫn có thể tiếp tục và Spring interceptor chỉ thấy return bình thường, phần SQL đã thành công trước đó có thể commit. Phải xem cấu hình `innodb_rollback_on_timeout`, trạng thái transaction và quyết định nghiệp vụ.

**Bài 3 — Exception thoát qua proxy:** Cùng lỗi InnoDB được Spring dịch thành `DataAccessException` và đi ra khỏi transactional method không bị bắt. Thường Spring làm gì?

**Đáp án:** Theo default rollback rule cho unchecked exceptions, Spring rollback transaction của method khi nó sở hữu transaction. Hành vi Spring không bị giới hạn ở statement-only rollback của DB.

**Bài 4 — Sleep lâu:** Method `@Transactional(timeout=1)` chỉ `Thread.sleep(5000)` rồi return, không thực hiện JDBC statement nào. Có chắc Spring interrupt thread vào giây thứ nhất không?

**Đáp án:** Không. `@Transactional(timeout)` không phải Java thread watchdog; deadline thường được kiểm tra/áp dụng khi resource operation được thực hiện.

**Bài 5 — JDBC query timeout:** `JdbcTemplate.setQueryTimeout(2)` có cùng ý nghĩa `@Transactional(timeout=2)` không?

**Đáp án:** Không. Query timeout giới hạn từng SQL statement theo JDBC driver; transaction timeout là deadline của scope mới và có thể được truyền thành query timeout **theo thời gian còn lại**.

**Bài 6 — Statement.cancel():** Có bảo đảm rằng `Future.cancel(true)` sẽ làm database rollback SQL đang chạy không?

**Đáp án:** Không. Interrupt của Java và yêu cầu cancel của JDBC/backend khác nhau. Cần hủy SQL được hỗ trợ và quản lý rollback/cleanup.

**Bài 7 — REQUIRED:** Outer transaction deadline 20 giây, inner `REQUIRED` khai báo `timeout=2`. Inner có tự áp 2 giây không?

**Đáp án:** Không khi inner chỉ tham gia physical transaction outer. Timeout metadata chủ yếu có hiệu lực tại transaction mới.

**Bài 8 — H2 50200:** Trong lab, catch `DataAccessException` và xác nhận root `SQLException.getErrorCode()==50200` giúp tránh lỗi nào?

**Đáp án:** Tránh nhầm lỗi SQL bất kỳ (syntax, constraint, connection) với lock timeout. Nhưng khi triển khai DB khác phải dùng mapping riêng, không hardcode H2 code chung.

**Bài 9 — Deadlock:** T1 giữ row A chờ B, T2 giữ B chờ A. Đây chỉ là lock wait một chiều?

**Đáp án:** Không, đây là chu trình deadlock. Engine thường chọn một transaction làm nạn nhân; cần deadlock retry strategy riêng, không suy luận từ thời gian chờ.

**Bài 10 — Client request kết thúc:** HTTP client đóng kết nối ở giây 2, JDBC statement vẫn đang chạy. Lệnh SQL có chắc bị cancel?

**Đáp án:** Không. Request timeout/disconnect không bảo đảm hủy SQL. Cần ranh giới timeout/cancel rõ ở JDBC/DB và cleanup transaction.

**Bài 11 — Session setting:** Vì sao `SET LOCK_TIMEOUT 500` trên SQL Server/H2 cần thận trọng trong connection pool?

**Đáp án:** Đây là session-scoped setting, có thể ảnh hưởng lần dùng kế tiếp của connection nếu không reset. Nên dùng cấu hình phù hợp pool hoặc cơ chế scoped của DB khi hỗ trợ.

**Bài 12 — Bằng chứng rollback:** Vì sao case trong demo phải SELECT sau `ownerTask.get(...)` thay vì SELECT trong lúc owner còn giữ transaction?

**Đáp án:** Chỉ sau khi proxy của owner hoàn tất rollback mới biết trạng thái committed. Đọc trong transaction còn mở hoặc dùng cùng connection có thể thấy thay đổi tạm chưa commit.

## 14. Tài liệu chính thức

- Spring Framework — **Using @Transactional**, `timeout` và propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — **Controlling Database Connections**, transaction timeout áp xuống JDBC statement: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- Spring Framework — `DataSourceUtils` Javadoc, `applyTransactionTimeout` và `applyTimeout`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html
- Spring Framework — `TransactionTimedOutException` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionTimedOutException.html
- Spring Framework — `JdbcTemplate` Javadoc (`setQueryTimeout`): https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Java 17 JDBC — `Statement` (`setQueryTimeout`, `cancel`): https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html
- H2 — SQL `SET LOCK_TIMEOUT` và scope mili giây: https://h2database.com/html/commands.html
- H2 — `ErrorCode.LOCK_TIMEOUT_1` (50200): https://h2database.com/javadoc/org/h2/api/ErrorCode.html
- PostgreSQL — runtime `lock_timeout` và `statement_timeout`: https://www.postgresql.org/docs/current/runtime-config-client.html
- PostgreSQL — SQLSTATE error codes: https://www.postgresql.org/docs/current/errcodes-appendix.html
- MySQL 8.4 — InnoDB error handling: https://dev.mysql.com/doc/refman/8.4/en/innodb-error-handling.html
- MySQL 8.4 — `innodb_lock_wait_timeout` / `innodb_rollback_on_timeout`: https://dev.mysql.com/doc/refman/8.4/en/innodb-parameters.html
- Microsoft SQL Server — `SET LOCK_TIMEOUT`: https://learn.microsoft.com/en-us/sql/t-sql/statements/set-lock-timeout-transact-sql

**Ghi nhớ:** **Lock timeout** là giới hạn chờ khóa do database áp dụng; **Spring transaction timeout** là deadline khi Spring tạo transaction mới và được tích hợp xuống JDBC statements theo cơ chế được hỗ trợ; **statement timeout/cancel** cố dừng một SQL statement nhưng không tự bảo đảm mọi phần của transaction đã rollback. Luôn kiểm tra **transaction boundary**, **root cause**, **trạng thái DB sau lỗi** và **dữ liệu committed sau khi các transaction đã kết thúc**.