# Thay đổi mức cô lập đúng thời điểm và đúng phạm vi

Mức cô lập (isolation level) quy định một transaction được phép quan sát những thay đổi đồng thời nào và DBMS xử lý xung đột đọc/ghi ra sao. Chọn mức cô lập phù hợp là quan trọng, nhưng còn phải **đặt đúng thời điểm, đúng connection, đúng transaction và đúng phạm vi**. Cấu hình có vẻ hợp lý vẫn có thể không bảo vệ nghiệp vụ nếu được đặt sau khi transaction bắt đầu, đặt trên connection khác, bị transaction manager bỏ qua hoặc chỉ áp dụng cho một statement trong khi nghiệp vụ cần bảo vệ nhiều statement.

## 1. Isolation level là thuộc tính của transaction

Các mức phổ biến:

| Mức | Ý nghĩa khái quát | Điều cần lưu ý |
|---|---|---|
| **READ UNCOMMITTED** | Mức cô lập thấp nhất theo mô hình SQL | Có thể cho dirty read; PostgreSQL xử lý như READ COMMITTED |
| **READ COMMITTED** | Chỉ đọc dữ liệu đã commit theo snapshot/điểm nhìn của statement | Các lần đọc có thể thấy commit mới xen giữa |
| **REPEATABLE READ** | Giữ tính ổn định của các lần đọc theo semantics DBMS | Phantom và xung đột ghi khác nhau giữa DBMS |
| **SERIALIZABLE** | Kết quả tương đương một thứ tự tuần tự hợp lệ | Transaction có thể bị từ chối và cần retry |

Cùng tên mức cô lập không có nghĩa mọi hệ quản trị có implementation giống hệt. PostgreSQL dùng MVCC và triển khai READ UNCOMMITTED như READ COMMITTED. InnoDB phân biệt consistent read và locking read. SQL Server có READ_COMMITTED_SNAPSHOT và SNAPSHOT isolation với cấu hình riêng.

Vì vậy, phải xác định DBMS, phiên bản, engine và yêu cầu nghiệp vụ trước khi chọn mức cô lập.

## 2. Thời điểm đặt isolation

Một transaction đi qua các bước khái quát:

1. Lấy hoặc sử dụng connection.
2. Thiết lập isolation, read-only, timeout và các thuộc tính cần thiết.
3. Bắt đầu transaction.
4. Thực thi các câu SQL.
5. Commit hoặc rollback.
6. Dọn dẹp và trả connection về pool.

Nhiều DBMS yêu cầu isolation được đặt trước statement đầu tiên của transaction; một số không cho đổi khi transaction đã hoạt động. Framework transaction manager cũng cần biết cấu hình trước khi bắt đầu hoặc tham gia transaction.

### 2.1. Đặt trước khi thực thi công việc

Ví dụ JDBC:

```java
import java.sql.Connection;
import java.sql.SQLException;
import javax.sql.DataSource;

public class TransactionRunner {
    private final DataSource dataSource;

    public TransactionRunner(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void execute() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            // Đặt isolation khi connection chưa có transaction nghiệp vụ.
            connection.setTransactionIsolation(
                Connection.TRANSACTION_SERIALIZABLE
            );
            connection.setAutoCommit(false);

            try {
                // Tất cả SQL cần chung transaction dùng connection này.
                // executeBusinessSql(connection);
                connection.commit();
            } catch (SQLException | RuntimeException ex) {
                try {
                    connection.rollback();
                } catch (SQLException rollbackFailure) {
                    ex.addSuppressed(rollbackFailure);
                }
                throw ex;
            }
        }
    }
}
```

Trình tự này đặt isolation trước câu SQL đầu tiên. Trong JDBC, gọi setAutoCommit(false) không nhất thiết gửi lệnh BEGIN ngay tại thời điểm gọi; chi tiết bắt đầu transaction phụ thuộc driver/DBMS và thời điểm thực thi SQL. Điều quan trọng là cấu hình isolation được đặt lúc connection ở trạng thái phù hợp.

### 2.2. Đặt quá muộn

```java
connection.setAutoCommit(false);

// Transaction có thể đã bắt đầu.
runFirstQuery(connection);

// Không portable để đổi isolation ở thời điểm này.
connection.setTransactionIsolation(Connection.TRANSACTION_SERIALIZABLE);
```

Driver/DBMS có thể ném SQLException hoặc từ chối thay đổi vì transaction đã hoạt động. Một số DBMS có cú pháp thay đổi transaction characteristics chỉ trước statement đầu tiên, nhưng không nên suy ra rằng JDBC setter luôn hợp lệ giữa transaction.

Ngay cả khi một DBMS cho phép thay đổi ở một mốc nhất định, thay đổi đó không hồi tố snapshot hoặc các quyết định đã thực hiện. Nếu transaction đã đọc dữ liệu theo góc nhìn cũ, việc đổi isolation sau đó không biến các thao tác trước thành serializable.

### 2.3. Thời điểm cấu hình và thời điểm hiệu lực

Phân biệt ba hành động:

- Đặt **default** để transaction tương lai sử dụng.
- Đặt **transaction hiện tại** trước khi nó thực hiện statement cần bảo vệ.
- Đặt isolation qua **framework** để transaction manager áp dụng khi tạo transaction.

Một lệnh thay đổi session default giữa hai transaction không có nghĩa transaction hiện tại tự đổi mức. Một method được gọi khi transaction đã mở cũng không thể mặc nhiên nâng isolation của transaction đó.

## 3. Phạm vi: statement, transaction, session và connection

| Phạm vi | Ý nghĩa | Ví dụ | Rủi ro nếu nhầm |
|---|---|---|---|
| **Statement** | Một câu lệnh có semantics đọc/khóa riêng | SELECT ... FOR UPDATE | Không bảo vệ các statement khác |
| **Transaction** | Các statement trong cùng transaction dùng isolation đã chọn | JDBC transaction | Đặt sau khi transaction hoạt động có thể quá muộn |
| **Session/Connection** | Thuộc tính hiện hành hoặc default của session | SET SESSION TRANSACTION | Có thể ảnh hưởng transaction tiếp theo trên cùng session |
| **Database/Server default** | Mặc định được áp dụng rộng cho session/transaction mới | Cấu hình DBMS | Ảnh hưởng nhiều workload |

Một transaction thường gắn với một connection trong JDBC và các câu lệnh phải tham gia cùng transaction context. Nếu mở connection khác, transaction manager không tự làm cho connection đó tham gia cùng transaction.

### 3.1. Session có vòng đời dài hơn transaction

Connection pool giữ các kết nối vật lý để tái sử dụng. Request A có thể đổi session isolation rồi trả connection về pool. Nếu pool/driver không reset trạng thái đó, request B có thể nhận lại connection với cấu hình A để lại.

Do đó, cần:
- Để pool/transaction manager quản lý và reset connection state.
- Tránh tự thay session default trong code nghiệp vụ nếu không có cơ chế khôi phục.
- Xác minh connection trả về pool không có transaction mở.
- Kiểm tra cấu hình runtime trên đúng connection thực tế.

**COMMIT/ROLLBACK kết thúc transaction; nó không đồng nghĩa session và mọi session setting đều biến mất.**

## 4. PostgreSQL: transaction và session scope

### 4.1. Cấu hình transaction hiện tại

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;

SELECT balance
FROM accounts
WHERE id = 1;

COMMIT;
```

Có thể sử dụng SET TRANSACTION sau BEGIN nhưng phải đặt trước khi statement đầu tiên cần snapshot/transaction semantics được thực hiện:

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

-- Các thao tác của transaction.

COMMIT;
```

Cách viết trực tiếp trong BEGIN giúp ranh giới và mức cô lập dễ quan sát hơn.

### 4.2. Cấu hình mặc định cho các transaction tiếp theo

```sql
SET SESSION CHARACTERISTICS AS TRANSACTION
    ISOLATION LEVEL READ COMMITTED;

SHOW transaction_isolation;
```

Lệnh SESSION CHARACTERISTICS đặt mặc định cho transaction tương lai trên session hiện tại; nó không có nghĩa transaction đang chạy tự động thay đổi isolation. Nếu dùng pool, cần bảo đảm session state được reset đúng.

### 4.3. READ UNCOMMITTED trên PostgreSQL

PostgreSQL chấp nhận cú pháp READ UNCOMMITTED nhưng thực hiện giống READ COMMITTED; nó không cho dirty read. Do vậy, đặt JDBC TRANSACTION_READ_UNCOMMITTED để mong đọc thay đổi chưa commit là giả định sai trên PostgreSQL.

## 5. MySQL/InnoDB: global, session và transaction scope

MySQL hỗ trợ thiết lập isolation ở các phạm vi khác nhau. Cú pháp phổ biến:

### 5.1. Session default

```sql
SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED;

START TRANSACTION;
-- Các câu lệnh thuộc transaction.
COMMIT;
```

Thiết lập session tác động đến mặc định của các transaction sau trên session đó.

### 5.2. Transaction kế tiếp

```sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

START TRANSACTION;
-- Transaction kế tiếp sử dụng mức đã đặt.
COMMIT;
```

Phạm vi này khác với session default. Phải tuân theo cú pháp và thứ tự lệnh của phiên bản MySQL đang dùng.

### 5.3. Global default

```sql
SET GLOBAL TRANSACTION ISOLATION LEVEL READ COMMITTED;
```

Thiết lập GLOBAL có ảnh hưởng tới session mới theo quy tắc MySQL; session đang tồn tại có thể tiếp tục giữ giá trị riêng. Đây là thay đổi phạm vi vận hành rộng và cần đánh giá workload, quyền truy cập và khả năng ảnh hưởng ứng dụng.

### 5.4. Không nhầm isolation với autocommit

Autocommit quyết định cách statement được commit tự động khi không có transaction tường minh. Isolation level quyết định quy tắc nhìn thấy dữ liệu và xử lý xung đột. Hai thuộc tính có liên quan nhưng không thay thế nhau.

```sql
SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SET autocommit = 0;

START TRANSACTION;
-- Nhiều statement trong một transaction.
COMMIT;
```

Tránh tắt autocommit rồi để session idle trong transaction; connection có thể giữ snapshot/lock lâu hơn dự kiến.

## 6. SQL Server: session isolation và snapshot options

SQL Server có các điểm riêng:

- SET TRANSACTION ISOLATION LEVEL đặt mức cho session và được dùng cho các transaction tiếp theo trên session.
- READ COMMITTED có thể sử dụng locking read hoặc row versioning nếu database bật READ_COMMITTED_SNAPSHOT.
- SNAPSHOT isolation cần database cho phép bằng ALLOW_SNAPSHOT_ISOLATION.
- SNAPSHOT cần được chọn trước khi transaction truy cập dữ liệu và chỉ hoạt động khi database đã cấu hình hỗ trợ.

Ví dụ:

```sql
SET TRANSACTION ISOLATION LEVEL SNAPSHOT;

BEGIN TRANSACTION;

SELECT balance
FROM dbo.accounts
WHERE id = 1;

COMMIT TRANSACTION;
```

Bật READ_COMMITTED_SNAPSHOT không đồng nghĩa mọi session được chuyển sang SNAPSHOT isolation tường minh. Cần phân biệt database option, session isolation và transaction boundary. Không sao chép nguyên cú pháp PostgreSQL/MySQL sang SQL Server.

## 7. JDBC: setTransactionIsolation

JDBC định nghĩa các hằng số:

| Constant | Mức |
|---|---|
| Connection.TRANSACTION_READ_UNCOMMITTED | READ UNCOMMITTED |
| Connection.TRANSACTION_READ_COMMITTED | READ COMMITTED |
| Connection.TRANSACTION_REPEATABLE_READ | REPEATABLE READ |
| Connection.TRANSACTION_SERIALIZABLE | SERIALIZABLE |

Không phải driver/DBMS hỗ trợ mọi mức. Nếu không hỗ trợ, setter có thể ném SQLException.

```java
try (Connection connection = dataSource.getConnection()) {
    DatabaseMetaData meta = connection.getMetaData();

    if (!meta.supportsTransactionIsolationLevel(
            Connection.TRANSACTION_SERIALIZABLE)) {
        throw new SQLException("SERIALIZABLE không được hỗ trợ");
    }

    connection.setTransactionIsolation(
        Connection.TRANSACTION_SERIALIZABLE
    );
    connection.setAutoCommit(false);

    try {
        // executeBusinessSql(connection);
        connection.commit();
    } catch (SQLException | RuntimeException ex) {
        try {
            connection.rollback();
        } catch (SQLException rollbackFailure) {
            ex.addSuppressed(rollbackFailure);
        }
        throw ex;
    }
}
```

Các điểm cần lưu ý:

1. supportsTransactionIsolationLevel cho biết driver/DBMS tuyên bố hỗ trợ, không bảo đảm semantics giống DBMS khác.
2. Lấy connection từ pool có thể nhận trạng thái được pool reset; không nên giả định giá trị mặc định.
3. Đặt isolation trước khi transaction bắt đầu thực thi.
4. Dùng cùng connection cho tất cả câu lệnh cần chung transaction.
5. Để framework/pool khôi phục trạng thái sau commit/rollback.
6. Không để lỗi rollback che mất lỗi gốc; có thể lưu lỗi rollback dưới dạng suppressed exception.

## 8. Spring @Transactional: đúng method và đúng propagation

Spring cho phép khai báo isolation trên @Transactional:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {
    @Transactional(isolation = Isolation.SERIALIZABLE)
    public void reserveOneProduct(long productId) {
        // Đọc/kiểm tra và cập nhật tồn kho trong cùng transaction.
    }
}
```

Mức isolation được áp dụng khi transaction manager tạo transaction mới, nếu manager/DBMS hỗ trợ. Annotation **không bảo đảm thay đổi isolation của transaction đã tồn tại mà method tham gia**.

### 8.1. REQUIRED: tham gia transaction hiện tại

Propagation mặc định của Spring là REQUIRED. Nếu method ngoài đã mở transaction READ COMMITTED, method con có isolation SERIALIZABLE nhưng dùng REQUIRED vẫn có thể tham gia transaction ngoài. Transaction đã mở quyết định isolation.

```java
@Service
public class CheckoutService {
    @Transactional
    public void checkout() {
        // Transaction ngoài đã bắt đầu.
        inventoryService.reserveOneProduct(101L);
    }
}

@Service
public class InventoryService {
    @Transactional(isolation = Isolation.SERIALIZABLE)
    public void reserveOneProduct(long productId) {
        // Với REQUIRED, có thể tham gia transaction ngoài.
    }
}
```

Spring mặc định có thể bỏ qua khai báo isolation/timeout/read-only cục bộ khi tham gia transaction đang tồn tại. Một số transaction manager có tùy chọn validateExistingTransaction để từ chối mismatch. Vì thế, nếu nghiệp vụ bắt buộc SERIALIZABLE, hãy đặt mức ở điểm bắt đầu transaction thực sự hoặc tổ chức propagation có chủ đích.

### 8.2. REQUIRES_NEW: transaction độc lập

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.SERIALIZABLE
)
public void reserveIndependently(long productId) {
    // Transaction mới, độc lập với transaction ngoài.
}
```

REQUIRES_NEW tạm đình chỉ transaction ngoài và tạo transaction mới. Mức SERIALIZABLE có thể áp dụng cho transaction mới nếu được hỗ trợ.

Đây là thay đổi semantics nghiệp vụ, không chỉ là cách bật isolation. Transaction con có thể commit dù transaction ngoài rollback. Transaction ngoài cũng có thể vẫn giữ connection và lock trong lúc bị đình chỉ; REQUIRES_NEW có thể cần thêm connection, gây áp lực pool.

### 8.3. Self-invocation và proxy

Trong proxy mode mặc định, gọi method transactional từ một method khác cùng bean bằng this.method() thường không đi qua proxy; annotation trên method được gọi có thể không có hiệu lực. Hãy gọi qua bean/proxy được Spring quản lý hoặc dùng cơ chế quản lý transaction phù hợp.

Ngay cả khi proxy hoạt động, REQUIRED vẫn tham gia transaction đang tồn tại. Cần xem đồng thời cả proxy và propagation, không chỉ nhìn annotation.

## 9. Thay đổi isolation khi transaction đã tồn tại

Không nên tùy tiện đổi isolation giữa transaction:

- Một hoặc nhiều statement có thể đã xác lập snapshot.
- DBMS có thể cấm thay đổi trong transaction đang hoạt động.
- Một số cú pháp chỉ cho phép đặt trước statement đầu tiên.
- Framework đã bind connection và transaction metadata.
- Thay đổi muộn không sửa các quyết định dựa trên snapshot cũ.

Nếu nghiệp vụ cần semantics khác, kết thúc transaction hiện tại theo đúng quy tắc và bắt đầu transaction mới với isolation phù hợp.

### 9.1. Savepoint không tạo transaction mới

Spring propagation NESTED thường dùng savepoint trong transaction vật lý hiện có nếu manager hỗ trợ. Savepoint không phải transaction độc lập có isolation riêng. Rollback về savepoint chỉ hoàn tác một phần thay đổi; transaction ngoài vẫn tồn tại.

### 9.2. Không dùng isolation mới để chữa quyết định cũ

Nếu transaction đã đọc snapshot cũ rồi tính toán, đặt mức isolation mạnh hơn sau đó không tự cập nhật phép tính. Cần đọc lại, kiểm tra version/điều kiện hoặc chạy lại toàn transaction.

## 10. Chọn phạm vi isolation theo workload

| Nhu cầu | Cách cân nhắc |
|---|---|
| Đọc đơn giản, không cần snapshot xuyên nhiều statement | READ COMMITTED nếu phù hợp DBMS |
| Nhiều lần đọc cần cùng snapshot | REPEATABLE READ hoặc snapshot phù hợp |
| Invariant phụ thuộc nhiều hàng, có nguy cơ write skew | SERIALIZABLE, guard row, explicit locking hoặc constraint |
| Cập nhật một entity theo version | Optimistic locking/version predicate |
| Trừ hàng tồn có điều kiện | Conditional UPDATE và kiểm tra row count |
| Báo cáo dài, cần nhất quán tại một thời điểm | Snapshot/reporting design; tránh transaction mở quá lâu |
| Workflow cần khóa cụ thể | Khóa đúng hàng/phạm vi, transaction ngắn |

Không nên nâng toàn hệ thống lên SERIALIZABLE chỉ để sửa một race condition, cũng không nên hạ toàn hệ thống xuống READ UNCOMMITTED để giảm chờ khóa. Mức cao hơn có thể tăng lock contention hoặc serialization retry tùy DBMS. Đo trên workload và chuẩn bị retry trước khi triển khai.

## 11. Isolation không thay thế constraint và locking

### 11.1. Constraint bảo vệ bất biến

Dùng CHECK cho số dư không âm, UNIQUE cho mã yêu cầu, FOREIGN KEY cho tham chiếu. Constraint được DBMS bảo vệ trên nhiều đường ghi, không chỉ một service.

### 11.2. Optimistic locking

```sql
UPDATE products
SET price = 120.00,
    version = version + 1
WHERE id = 10
  AND version = 7;
```

Nếu row count bằng 0, dữ liệu đã thay đổi kể từ khi ứng dụng đọc. Cần tải lại và giải quyết xung đột hoặc báo người dùng. JPA có thể dùng @Version theo mẫu tương tự.

### 11.3. Pessimistic locking

```sql
BEGIN;

SELECT quantity
FROM inventory
WHERE product_id = 101
FOR UPDATE;

-- Kiểm tra và cập nhật trong cùng transaction.

COMMIT;
```

Khóa cần được lấy đúng hàng/điều kiện và giữ tới cuối transaction. Isolation level cao hơn không tự thay thế mọi yêu cầu khóa nghiệp vụ.

### 11.4. Retry và idempotency

SERIALIZABLE có thể trả serialization failure; deadlock cũng có thể khiến transaction rollback. Khi retry, chạy lại toàn bộ transaction vì kết quả phụ thuộc dữ liệu đã đọc trước đó. Dùng giới hạn retry, backoff và mã yêu cầu duy nhất để chống thực hiện trùng.

Nếu kết quả COMMIT không rõ do mất kết nối, cần đối soát theo mã nghiệp vụ thay vì tự động gửi một yêu cầu mới.

## 12. Kiểm tra isolation runtime

### PostgreSQL

```sql
SHOW transaction_isolation;
SHOW transaction_read_only;

BEGIN ISOLATION LEVEL REPEATABLE READ;
SHOW transaction_isolation;
COMMIT;
```

### MySQL

```sql
SELECT
    @@global.transaction_isolation,
    @@session.transaction_isolation;
```

Tên system variable có thể khác ở phiên bản cũ; xác định phiên bản thực tế.

### JDBC

```java
try (Connection connection = dataSource.getConnection()) {
    int level = connection.getTransactionIsolation();
    boolean autoCommit = connection.getAutoCommit();

    System.out.println("Isolation=" + level);
    System.out.println("AutoCommit=" + autoCommit);
}
```

Giá trị trên một connection đọc từ pool không tự chứng minh transaction nghiệp vụ đang dùng đúng connection đó. Phải quan sát connection mà transaction manager thật sự quản lý.

Trong Spring, có thể bật log transaction manager phù hợp ở môi trường phát triển để quan sát transaction bắt đầu, tham gia, commit/rollback. Không bật log quá chi tiết tùy tiện trong production nếu có nguy cơ lộ dữ liệu hoặc tạo tải.

## 13. Quy trình quyết định thay đổi isolation

1. **Xác định anomaly cần ngăn:** dirty read, non-repeatable read, phantom, lost update hay write skew? Viết ra lịch transaction gây lỗi.
2. **Xác định invariant:** điều kiện nào phải luôn đúng, điều kiện nào phải được kiểm tra cùng thao tác ghi?
3. **Xác định DBMS và cấu hình:** hệ quản trị, engine, phiên bản, driver và isolation mặc định.
4. **Chọn phạm vi nhỏ nhất phù hợp:** transaction nghiệp vụ, session default hay global default; chỉ thay đổi rộng khi đã đánh giá workload.
5. **Đặt trước khi thực thi:** cấu hình trước statement đầu tiên cần bảo vệ; nếu tham gia transaction ngoài, kiểm tra propagation.
6. **Xác minh runtime:** đọc isolation ở đúng connection/transaction và quan sát transaction manager.
7. **Xử lý kết cục:** commit/rollback đúng nhánh; retry toàn bộ transaction khi lỗi cho phép.
8. **Đo tác động:** lock wait, latency, throughput, retry rate, connection pool và transaction age.

## 14. Những tình huống dễ cấu hình sai

| Tình huống | Vì sao sai | Cách xử lý |
|---|---|---|
| JDBC setter sau query đầu tiên | Transaction có thể đã hoạt động; DBMS từ chối | Đặt trước transaction |
| Method con khai SERIALIZABLE nhưng REQUIRED | Transaction ngoài quyết định isolation | Đặt ở method mở transaction hoặc tách transaction có chủ đích |
| Đổi session isolation rồi trả connection về pool | Request sau có thể kế thừa | Reset connection state |
| Chỉ cấu hình một truy vấn | Statement sau có thể thuộc transaction khác | Xác định transaction boundary |
| Đổi GLOBAL để sửa một race condition | Ảnh hưởng rộng workload mới | Thay đổi tại transaction phù hợp |
| SERIALIZABLE nhưng không retry | DBMS có thể từ chối transaction | Retry toàn bộ với giới hạn |
| REQUIRES_NEW chỉ để đổi isolation | Tạo commit độc lập ngoài dự kiến | Chỉ dùng khi đúng semantics nghiệp vụ |
| Cho rằng DBMS cùng tên level có cùng hành vi | Implementation khác nhau | Đọc tài liệu đúng phiên bản |

## 15. Bài tập tình huống

### A. Đặt isolation muộn

Ứng dụng mở transaction READ COMMITTED, đọc số dư 1.000, rồi gọi JDBC setTransactionIsolation(SERIALIZABLE).

**Trả lời:** Không thể coi transaction đã được nâng lên SERIALIZABLE từ đầu. Setter có thể bị từ chối khi transaction hoạt động; thay đổi muộn không hồi tố snapshot và quyết định đã diễn ra. Đặt isolation trước khi công việc transaction bắt đầu.

### B. Spring REQUIRED

outer() mở transaction READ COMMITTED và gọi bean khác có @Transactional(isolation = SERIALIZABLE) với propagation REQUIRED.

**Trả lời:** Method con tham gia transaction hiện có; nó không tự nâng isolation của transaction ngoài. Đặt isolation ở điểm bắt đầu transaction hoặc tạo transaction độc lập nếu đúng nghiệp vụ.

### C. Spring REQUIRES_NEW

Transaction ngoài tạo đơn hàng, gọi method REQUIRES_NEW để ghi audit, rồi transaction ngoài rollback.

**Trả lời:** Bản ghi audit có thể đã commit độc lập. Điều này có thể phù hợp với audit, nhưng cần thiết kế rõ ý nghĩa của log so với trạng thái đơn hàng.

### D. Connection pool

Request A đặt session isolation thành SERIALIZABLE rồi kết thúc. Request B nhận lại connection vật lý.

**Trả lời:** Không thể mặc định B dùng default database. Phải xác minh pool/driver reset session state.

### E. READ UNCOMMITTED trên PostgreSQL

Ứng dụng đặt JDBC TRANSACTION_READ_UNCOMMITTED và mong đọc dữ liệu chưa commit.

**Trả lời:** PostgreSQL triển khai mức này như READ COMMITTED, nên dirty read không xảy ra.

## Kết luận

Thay đổi isolation chỉ có tác dụng khi **được áp dụng đúng thời điểm, đúng connection, đúng transaction và đúng phạm vi sở hữu**. Cần phân biệt session default, transaction hiện tại, transaction mới và method tham gia transaction có sẵn. JDBC, PostgreSQL, MySQL, SQL Server và Spring có API/cú pháp khác nhau; đặc biệt REQUIRED không nâng isolation của transaction ngoài, còn REQUIRES_NEW tạo ranh giới commit độc lập.

Hãy bắt đầu từ anomaly và bất biến nghiệp vụ, chọn semantics phù hợp DBMS, thiết lập isolation trước khi transaction thực thi, xác minh runtime và chuẩn bị retry/rollback theo đúng kết cục. Đó là cách tránh cấu hình chỉ đúng trên source nhưng không bảo vệ được giao dịch thực tế.
