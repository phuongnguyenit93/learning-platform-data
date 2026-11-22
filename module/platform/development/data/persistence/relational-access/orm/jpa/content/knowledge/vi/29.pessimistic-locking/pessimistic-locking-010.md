# Kiểm chứng hành vi khóa trên hệ quản trị mục tiêu

> **Chủ đề:** Data Persistence Relational Access ORM JPA  
> **Chương:** Khóa bi quan

Khi lập trình Java Persistence API (JPA), ta có thể yêu cầu khóa bi quan bằng `LockModeType.PESSIMISTIC_READ`, `PESSIMISTIC_WRITE` hoặc `PESSIMISTIC_FORCE_INCREMENT`. Những API đó biểu diễn **ý định đồng bộ hóa các giao dịch cạnh tranh**, nhưng không có nghĩa tất cả hệ quản trị cơ sở dữ liệu (DBMS), JDBC drivers và JPA providers sẽ phát cùng một câu SQL, chờ khóa cùng khoảng thời gian, khóa cùng phạm vi, hay ném cùng một exception.

Ví dụ, việc khóa một hàng bằng `SELECT ... FOR UPDATE` trên PostgreSQL khác với thực thi locking hints trên SQL Server. MySQL/InnoDB có thể khóa cả vùng chỉ mục trong một số truy vấn phạm vi; với một database dùng MVCC, một `SELECT` thông thường có thể đọc phiên bản đã commit trong lúc giao dịch khác đang giữ khóa cập nhật mà **không** bị chặn. Trên một provider, `PESSIMISTIC_READ` có thể dùng shared lock; trên provider khác, nó có thể được nâng lên kiểu khóa mạnh hơn khi database không hỗ trợ đúng dạng shared-lock cần thiết.

Do đó, câu hỏi kỹ thuật không nên chỉ là:

> “Trong JPA, `PESSIMISTIC_WRITE` nghĩa là gì?”

Mà còn là:

> “Trên **DBMS, phiên bản, isolation level, JDBC driver, JPA provider và SQL dialect thực sự của ứng dụng**, thao tác nào bị chặn, bao lâu, kết thúc ra sao và làm sao đo được bằng bằng chứng?”

Bài này trình bày một phương pháp kiểm chứng có thể lặp lại: chuẩn bị dữ liệu và giao dịch, tạo cạnh tranh có kiểm soát, quan sát SQL và tiến trình chờ, phân loại kết quả, rồi ghi lại quyết định thiết kế. Ví dụ dùng **Jakarta Persistence** (`jakarta.persistence.*`). Trong dự án JPA cũ dùng `javax.persistence.*`, package/hint prefix khác; cần nhất quán với phiên bản đang triển khai.

---

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt ý nghĩa chuẩn JPA của `PESSIMISTIC_READ`, `PESSIMISTIC_WRITE` và `PESSIMISTIC_FORCE_INCREMENT`.
2. Xác định các yếu tố môi trường quyết định hành vi khóa: DBMS, engine, isolation, driver, provider, dialect, transaction manager, pool và version.
3. Viết giả thuyết kiểm chứng cụ thể thay vì dựa vào tên annotation.
4. Thiết lập **hai giao dịch thật trên hai connection/EntityManager riêng** để tạo contention.
5. Xác định thời điểm bắt đầu, thời điểm lấy khóa thành công, lúc giao dịch commit/rollback và lúc khóa được giải phóng.
6. Phân biệt blocking, lock timeout, statement timeout, connection timeout và deadlock.
7. Quan sát lệnh SQL provider sinh ra và đối chiếu với DBMS.
8. Thực hiện các thí nghiệm `SELECT ... FOR UPDATE`/shared locking bằng phiên SQL thủ công khi thích hợp.
9. Dùng công cụ quan sát PostgreSQL, MySQL/InnoDB, SQL Server và Oracle ở mức phù hợp.
10. Hiểu ảnh hưởng của `READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE` và MVCC.
11. Kiểm tra tác động của transaction boundary: `flush` không giải phóng khóa; `commit`/`rollback` thường kết thúc transaction-held locks.
12. Kiểm tra độ tin cậy của hint `jakarta.persistence.lock.timeout` và phân biệt nó với `jakarta.persistence.query.timeout`.
13. Phân loại `LockTimeoutException`, `PessimisticLockException`, lỗi deadlock và các wrapper của provider/framework.
14. Kiểm chứng `PESSIMISTIC_FORCE_INCREMENT` cùng entity có `@Version`.
15. Nhận ra việc khóa **một hàng hiện có** không tự bảo vệ **mọi tập kết quả theo điều kiện** khỏi phantom inserts.
16. Kiểm tra ảnh hưởng index, phạm vi truy vấn, join, foreign key, provider follow-on locking và lock escalation.
17. Thiết kế bài kiểm thử concurrency bằng hai `EntityManager`, latch và phương thức quan sát DB.
18. Ghi một **biên bản kiểm chứng** đủ thông tin để nhóm phát triển có thể tái lập trên database production-target.

## 2. “Kiểm chứng hành vi khóa” là kiểm chứng điều gì?

Một kiểm chứng khóa không chỉ xác nhận một câu Java chạy thành công.

Cần trả lời ít nhất sáu câu hỏi:

1. **Ai giữ khóa?** Giao dịch/connection nào đã lock row hoặc key?
2. **Ai cạnh tranh?** Giao dịch thứ hai đang `SELECT` thường, `SELECT FOR UPDATE`, `UPDATE`, `DELETE` hay `INSERT`?
3. **Đối tượng nào được bảo vệ?** Một primary-key row, nhiều rows, một range/index gap hay một đối tượng khác?
4. **Có chờ không?** Nếu chờ, lý do nào được DBMS báo và bao lâu?
5. **Kết thúc bằng gì?** Nhận khóa sau khi A commit, timeout, deadlock victim, exception hay truy vấn thành công ngay?
6. **Ứng dụng nhìn thấy gì?** SQL, Java exception, trạng thái transaction, số row bị ảnh hưởng và trạng thái entity.

Một kết quả như “B bị chậm 1,5 giây” **chưa đủ** để kết luận B đã chờ row lock. Chậm có thể đến từ scheduling, pool hết connection, network, GC, query plan, I/O hoặc chính server. Cần đối chiếu với **thông tin blocking session/lock wait ở database**.

### 2.1. Cần kiểm tra theo lớp

```text
Java business service
        |
        v
JPA API / EntityManager
        |
        v
Provider (Hibernate, EclipseLink, ...)
        |
        v
SQL dialect / JDBC driver
        |
        v
Database transaction / isolation
        |
        v
Lock manager / MVCC / index structures
        |
        v
Blocking, timeout, deadlock, commit/rollback
```

Giả sử code Java không đổi. Chỉ thay dialect/provider hoặc isolation vẫn có thể làm SQL và kết quả khác.

### 2.2. “Target DBMS” là một cấu hình cụ thể

Cần ghi rõ:

| Thành phần | Ví dụ thông tin cần ghi |
|---|---|
| Database | PostgreSQL / MySQL / SQL Server / Oracle |
| Database version | Bản major/minor đang thử |
| Storage engine | Ví dụ InnoDB nếu dùng MySQL |
| Isolation level | READ COMMITTED, REPEATABLE READ, ... |
| JDBC driver | Tên và phiên bản |
| JPA provider | Hibernate ORM/EclipseLink + phiên bản |
| SQL dialect | Dialect thực sự được chọn |
| Connection pool | HikariCP hoặc pool tương ứng + size |
| Transaction model | RESOURCE_LOCAL / JTA / Spring-managed |
| Lock mode | PESSIMISTIC_READ / WRITE / FORCE_INCREMENT |
| Lock timeout | JPA hint và cài đặt DB/session |
| Query path | `find`, JPQL `setLockMode`, Criteria hoặc native SQL |
| Cache/enhancement | First-level/second-level cache, bytecode enhancement |
| Schema/index | PK, foreign keys, indexes, điều kiện lọc |
| Test environment | Data size, resource limits, topology |

Không nên viết tài liệu “đã kiểm chứng PostgreSQL” nếu chỉ chạy H2 giả lập PostgreSQL mode. H2 có ích cho test nhẹ, nhưng **không thay thế integration test trên DBMS mục tiêu**.

---

## 3. LockModeType theo chuẩn Jakarta Persistence

Imports:

```java
import jakarta.persistence.LockModeType;
```

Các chế độ liên quan:

| LockModeType | Ý định ở mức JPA | Điểm cần đo trên DBMS |
|---|---|---|
| `PESSIMISTIC_READ` | Dùng khóa bi quan để bảo vệ dữ liệu được đọc, ngăn dirty/non-repeatable read theo contract; có thể dùng shared lock hoặc mạnh hơn | Có chặn writer khác? Có chặn reader locking khác? SQL là gì? |
| `PESSIMISTIC_WRITE` | Yêu cầu khóa bi quan cho cập nhật, ngăn thao tác ghi cạnh tranh phù hợp | UPDATE/DELETE/lock writer khác chờ ra sao? |
| `PESSIMISTIC_FORCE_INCREMENT` | Khóa bi quan và tăng version cho entity có `@Version` theo ngữ nghĩa chuẩn | Có SQL UPDATE version? Version đổi ở giai đoạn nào? |
| `OPTIMISTIC` | Kiểm tra version khi transaction hoàn tất, không giống khóa row ngay lúc đọc | Không dùng như kết luận PESSIMISTIC |
| `OPTIMISTIC_FORCE_INCREMENT` | Optimistic version increment | Phân biệt với pessimistic locking |
| `NONE` | Không yêu cầu lock đặc biệt qua API đó | Database vẫn có transaction/statement locks tùy thao tác |

### 3.1. PESSIMISTIC_READ không luôn có SQL “FOR SHARE”

Nếu DBMS/provider không hỗ trợ loại shared lock tương ứng, provider có thể sử dụng khóa độc quyền/mạnh hơn để đáp ứng ý định chuẩn. Do đó:

- Không khẳng định mọi DBMS cho hai `PESSIMISTIC_READ` đọc đồng thời.
- Không suy ra SQL từ enum.
- Cần thử **read–read**, **read–write** và **write–read locking** trên stack thật.

### 3.2. PESSIMISTIC_WRITE không luôn khóa mọi SELECT thường

Với MVCC, một `SELECT` bình thường thường có thể đọc phiên bản dữ liệu đã commit trong khi transaction khác giữ row lock để sửa. Một `SELECT ... FOR UPDATE` hoặc `UPDATE` cạnh tranh mới là tình huống chờ dễ quan sát.

Không coi “SELECT không bị chặn” là bằng chứng `PESSIMISTIC_WRITE` thất bại. Phải dùng **giao dịch cạnh tranh phù hợp với loại khóa**.

### 3.3. PESSIMISTIC_FORCE_INCREMENT cần @Version

Ví dụ entity có `@Version Long version`. Provider có thể tăng version bằng SQL update trong quá trình giữ lock/flush/transaction; thời điểm chính xác cần quan sát. Dạng khóa này hữu ích khi cần đánh dấu entity đã bị can thiệp và buộc các giao dịch optimistic cũ phải kiểm tra lại.

Đừng thử trên entity không versioned rồi coi hành vi giống nhau ở mọi provider. Kiểm tra mapping và khả năng hỗ trợ theo chuẩn/provider.

---

## 4. Thiết kế một phép thử có thể tái lập

Thay vì bắt đầu bằng business graph lớn, dùng một bảng đơn giản.

### 4.1. Bảng wallets

Ví dụ SQL minh họa; cú pháp tạo khóa sinh tự động tùy DBMS:

```sql
CREATE TABLE wallets (
    id BIGINT PRIMARY KEY,
    owner_name VARCHAR(120) NOT NULL,
    balance DECIMAL(19, 2) NOT NULL,
    version BIGINT NOT NULL
);

INSERT INTO wallets (id, owner_name, balance, version)
VALUES
    (1, 'Alice', 100.00, 0),
    (2, 'Bob',   200.00, 0);
```

Sử dụng ID cố định vì mục tiêu của bài là **khóa**, không phải sinh khóa chính. Bảng phải được tạo trên **database mục tiêu**, không chỉ test với in-memory database.

### 4.2. Entity Jakarta Persistence

```java
package demo.locklab;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

import java.math.BigDecimal;
import java.util.Objects;

@Entity
@Table(name = "wallets")
public class Wallet {

    @Id
    private Long id;

    @Column(name = "owner_name", nullable = false)
    private String ownerName;

    @Column(name = "balance", nullable = false, precision = 19, scale = 2)
    private BigDecimal balance;

    @Version
    @Column(name = "version", nullable = false)
    private Long version;

    protected Wallet() {
        // JPA
    }

    public Long getId() {
        return id;
    }

    public BigDecimal getBalance() {
        return balance;
    }

    public Long getVersion() {
        return version;
    }

    public void credit(BigDecimal amount) {
        Objects.requireNonNull(amount, "amount");
        if (amount.signum() <= 0) {
            throw new IllegalArgumentException(
                "amount must be positive");
        }
        balance = balance.add(amount);
    }
}
```

Version giúp kiểm chứng `PESSIMISTIC_FORCE_INCREMENT` hoặc việc optimistic version conflict, nhưng không cần version để minh họa mọi tình huống `PESSIMISTIC_WRITE`.

### 4.3. Dữ liệu thử phải được reset

Mỗi scenario nên bắt đầu với:

```text
wallet#1: balance=100.00, version=0
wallet#2: balance=200.00, version=0
```

Nếu các scenario liên tục ghi balance/version mà không reset, kết luận cuối có thể lệch. Reset bằng transaction riêng trước test, **không reset khi còn giao dịch đang khóa**, và ghi rõ expected state sau commit/rollback.

### 4.4. Không thử blocking dài trên production

Các ví dụ giữ transaction mở có chủ ý. Chạy trên database test/staging được phép, dùng một bảng chuyên biệt và timeout an toàn. Trên production, giữ khóa hoặc tạo deadlock có thể làm ảnh hưởng người dùng khác; nếu cần khảo sát production, dùng công cụ đọc metrics, phân tích log và kế hoạch quan sát được phê duyệt.

---

## 5. Ma trận thí nghiệm cần chuẩn bị

Một kiểm chứng tốt gồm nhiều cặp hành động A/B, không chỉ một lần thử:

| Tình huống | Transaction A | Transaction B | Điều cần quan sát |
|---|---|---|---|
| W/W | Lock wallet#1 kiểu WRITE, giữ transaction | Lock wallet#1 kiểu WRITE | B có chờ, timeout hoặc fail không? |
| W/UPDATE | WRITE wallet#1 | `UPDATE wallets SET ... WHERE id=1` | UPDATE B có chờ A không? |
| W/SELECT thường | WRITE wallet#1 rồi update chưa commit | `SELECT` không khóa | Có đọc dữ liệu đã commit không? Có bị chặn không? |
| R/R | READ wallet#1 | READ wallet#1 | Shared locks có cùng tồn tại không? |
| R/W | READ wallet#1 | WRITE wallet#1 | Writer có chờ reader không? |
| W/R | WRITE wallet#1 | READ wallet#1 | Reader-locking có chờ không? |
| W/khác row | WRITE wallet#1 | WRITE wallet#2 | Có cạnh tranh không mong đợi không? |
| Rollback | WRITE + UPDATE wallet#1 | Đợi WRITE wallet#1 | Sau rollback B thấy gì? |
| Force version | FORCE_INCREMENT wallet#1 | Đọc version sau commit | Version có tăng? |
| Deadlock | Lock #1 rồi #2 | Lock #2 rồi #1 | DB phát hiện và xử lý ra sao? |
| Range | Lock những wallet thỏa điều kiện | INSERT một wallet mới phù hợp | Có gap/range/phantom behavior? |
| No-wait | WRITE wallet#1 giữ lâu | Lock với wait=0/nowait | Thất bại nhanh hay hint bị bỏ qua? |

**Không coi tất cả expected outcomes của bảng là cố định theo mọi DBMS.** Kết quả thực tế phải được ghi theo môi trường mục tiêu.

---

## 6. Giao thức thử nghiệm: hai phiên, hai transaction

Thí nghiệm thủ công dễ kiểm tra nhất gồm:

```text
Phiên SQL A / Connection A           Phiên SQL B / Connection B
-----------------------------        ----------------------------
BEGIN                                BEGIN
SELECT ... FOR UPDATE wallet#1        SELECT ... FOR UPDATE wallet#1
(giữ giao dịch mở)                   (chờ hoặc timeout)
       |
       +-- [Observer thứ ba đọc trạng thái khóa]
       |
COMMIT / ROLLBACK                    B tiếp tục hoặc exception
                                     COMMIT / ROLLBACK
```

### 6.1. Vì sao phải là hai connection thật?

Nếu dùng **cùng một EntityManager** cho hai thao tác tuần tự, bạn đang chạy trong cùng persistence context/transaction theo cách có thể không tạo cạnh tranh mong muốn. Nếu dùng connection pool chỉ có một connection và request B không lấy được connection, B có thể chờ **pool**, không phải row lock.

Để xác thực row lock contention, cần:

- Hai transactions độc lập.
- Hai physical database connections đồng thời (hoặc hai DB sessions).
- Observer riêng nếu muốn truy vấn trạng thái blocker trong lúc B đang đợi.
- Không dùng EntityManager từ nhiều threads đồng thời vì EntityManager không thread-safe.

### 6.2. Tại sao A phải giữ transaction mở?

Nhiều transaction-level locks được giữ đến `COMMIT` hoặc `ROLLBACK`. Nếu A commit ngay sau `SELECT FOR UPDATE` trước khi B bắt đầu, B có thể nhận khóa tức thì và test không tái hiện contention.

Trong test, A cần dừng ở một **barrier/latch** sau khi lock thành công và trước khi commit, chờ observer/B thử khóa.

### 6.3. Các mốc thời gian

Ghi ít nhất:

```text
T0: A begins transaction
T1: A reports lock acquired
T2: B begins transaction
T3: B attempts competing operation
T4: DB observer confirms waiting/blocker
T5: A commits or rolls back
T6: B acquires lock or throws exception
T7: B commits or rolls back
```

Không đánh đồng **B thread đã bắt đầu** với **B đã tới database và chờ row lock**. Cần bằng chứng từ DB/session để khẳng định T4.

---

## 7. Kiểm chứng thủ công trên PostgreSQL

PostgreSQL cung cấp `SELECT ... FOR UPDATE` để lấy row-level locking khi transaction còn mở. Ví dụ dưới đây giả định bảng `wallets` đã được tạo.

### 7.1. Phiên A giữ WRITE lock

Mở cửa sổ SQL A:

```sql
BEGIN;

SELECT id, balance, version
FROM wallets
WHERE id = 1
FOR UPDATE;

UPDATE wallets
SET balance = balance + 10,
    version = version + 1
WHERE id = 1;

-- Giữ transaction mở: chưa COMMIT/ROLLBACK.
```

Bảng hàng #1 đã được transaction A lock để cập nhật. Balance mới chưa commit không phải dữ liệu mà mọi session khác sẽ nhìn thấy.

### 7.2. Phiên B thử WRITE lock

Mở cửa sổ SQL B riêng:

```sql
BEGIN;

SELECT id, balance, version
FROM wallets
WHERE id = 1
FOR UPDATE;

-- Quan sát: câu lệnh có thể chờ A giải phóng khóa.
```

Trước khi A commit/rollback, B có thể đứng ở trạng thái đợi.

### 7.3. Đưa B đi tiếp

Quay lại phiên A:

```sql
COMMIT;
```

B có thể nhận khóa sau khi A commit và, trong cấu hình isolation phù hợp (ví dụ READ COMMITTED), quan sát bản ghi sau cập nhật. Sau đó kết thúc B:

```sql
COMMIT;
```

Không để B giữ khóa vô tình sau khi đã nhận.

### 7.4. Thử rollback

Reset dữ liệu trên DB test. Thực hiện lại A lock và UPDATE nhưng thay `COMMIT` bằng:

```sql
ROLLBACK;
```

Lúc này thao tác ghi chưa commit của A bị hủy; B có thể tiếp tục theo visibility/isolation hiện hành. Ghi balance/version cuối bằng một session mới.

### 7.5. Không kết luận SELECT thường nhất thiết bị chặn

Trong một session C:

```sql
SELECT id, balance, version
FROM wallets
WHERE id = 1;
```

Ở môi trường MVCC thông dụng, câu SELECT thường có thể đọc dữ liệu committed trước đó, không chờ FOR UPDATE theo kiểu locking read. Nếu nó không chờ, đó **không phải bằng chứng A chưa lock**. Thử một lệnh khóa cạnh tranh hoặc UPDATE mới là đối chứng phù hợp.

---

## 8. Quan sát phiên chờ trên PostgreSQL

Có thể dùng `pg_stat_activity` và `pg_blocking_pids` (cần quyền xem thông tin phù hợp):

```sql
SELECT
    a.pid,
    a.usename,
    a.state,
    a.wait_event_type,
    a.wait_event,
    pg_blocking_pids(a.pid) AS blocking_pids,
    left(a.query, 160) AS query_preview
FROM pg_stat_activity AS a
WHERE a.datname = current_database()
ORDER BY a.pid;
```

Mục tiêu:

- Xác định PID của phiên B đang đợi.
- Xác định PID blocker A qua `pg_blocking_pids`.
- Quan sát `wait_event_type`, `wait_event` phù hợp.
- Đối chiếu với truy vấn đang thực thi.

### 8.1. pg_locks là công cụ bổ trợ, không phải bản đồ đơn giản mọi row

```sql
SELECT
    pid,
    locktype,
    mode,
    granted,
    relation::regclass AS relation_name,
    transactionid
FROM pg_locks
WHERE pid IN (:pid_a, :pid_b)
ORDER BY pid, granted, locktype, mode;
```

Thay `:pid_a`/`:pid_b` bằng PIDs thật hoặc dùng tham số trong client phù hợp. Trong PostgreSQL, một phiên chờ row-level contention có thể thể hiện qua việc đợi transaction ID và các lock records khác, chứ **không phải mọi row lock đều luôn hiển thị trực tiếp thành một dòng dễ đọc trong `pg_locks`**.

Vì vậy hãy kết hợp `pg_blocking_pids`, `pg_stat_activity`, `pg_locks` và SQL thực tế. Không suy kết luận chỉ từ việc không thấy một dòng “tuple lock”.

### 8.2. Timeout do PostgreSQL session định nghĩa

Trong phiên B thử:

```sql
BEGIN;
SET LOCAL lock_timeout = '2s';

SELECT *
FROM wallets
WHERE id = 1
FOR UPDATE;

-- Nếu A giữ lock lâu hơn giới hạn, nhận lock timeout.
```

Sau một statement error trong transaction PostgreSQL, transaction có thể ở trạng thái aborted và thường cần:

```sql
ROLLBACK;
```

Đây là timeout **tại database** bằng lệnh PostgreSQL, không có nghĩa JPA hint lock timeout sẽ được mọi provider dịch thành `SET LOCAL lock_timeout`.

### 8.3. NOWAIT và SKIP LOCKED

PostgreSQL có cú pháp vendor SQL:

```sql
SELECT *
FROM wallets
WHERE id = 1
FOR UPDATE NOWAIT;
```

hoặc:

```sql
SELECT *
FROM wallets
WHERE id = 1
FOR UPDATE SKIP LOCKED;
```

Ý nghĩa khác nhau:

- `NOWAIT`: không chờ khóa không tương thích, có thể phát lỗi ngay.
- `SKIP LOCKED`: bỏ qua những rows bị khóa không lấy được ngay; hữu ích cho một số queue-consumer patterns, nhưng không đại diện một snapshot đầy đủ của tất cả rows phù hợp.

Đây là SQL feature trên DBMS hỗ trợ, **không phải cú pháp JPQL chuẩn áp dụng giống nhau cho mọi provider**.

---

## 9. PESSIMISTIC_READ trên PostgreSQL

Một thử nghiệm bổ sung dùng `FOR SHARE`:

Phiên A:

```sql
BEGIN;

SELECT *
FROM wallets
WHERE id = 1
FOR SHARE;

-- Giữ transaction.
```

Phiên B:

```sql
BEGIN;

SELECT *
FROM wallets
WHERE id = 1
FOR SHARE;
```

Nhiều shared row locks có thể tương thích với nhau. Nhưng nếu B dùng `FOR UPDATE` hoặc `UPDATE` cùng row, nó có thể phải chờ.

### 9.1. JPA READ có nhất thiết sinh FOR SHARE?

Không. Cần bật SQL log rồi dùng:

```java
em.find(
    Wallet.class,
    1L,
    LockModeType.PESSIMISTIC_READ
);
```

để xem provider/dialect thực sự sinh `FOR SHARE` hay một cơ chế khác. Ví dụ SQL thủ công chỉ dùng để xác lập **đặc tính database**, không tự chứng minh cách một JPA provider map enum.

### 9.2. PostgreSQL có thêm các row-lock strengths

PostgreSQL cũng có các mức `FOR NO KEY UPDATE` và `FOR KEY SHARE` trong ngữ cảnh nhất định. Chúng không tương đương một-một với toàn bộ `LockModeType` của JPA. Đặc biệt những UPDATE không sửa key columns có thể dùng các lock strengths khác nhau ở mức DB. Khi kiểm chứng chi tiết về foreign key và khóa key/non-key update, phải đọc SQL thực tế và hiểu ma trận tương thích của PostgreSQL version mục tiêu.

---

## 10. MySQL/InnoDB: thử locking read trong transaction thật

Với MySQL dùng InnoDB, khóa hàng gắn với giao dịch. **Autocommit** đặc biệt quan trọng: nếu mỗi statement chạy ở transaction riêng và tự commit ngay, khóa có thể được giải phóng quá sớm để quan sát cạnh tranh.

### 10.1. Phiên A

```sql
START TRANSACTION;

SELECT id, balance, version
FROM wallets
WHERE id = 1
FOR UPDATE;

UPDATE wallets
SET balance = balance + 10,
    version = version + 1
WHERE id = 1;

-- Chưa COMMIT.
```

### 10.2. Phiên B

```sql
START TRANSACTION;

SELECT id, balance, version
FROM wallets
WHERE id = 1
FOR UPDATE;

-- Theo dõi trạng thái lock wait.
```

Kết thúc A bằng `COMMIT` hoặc `ROLLBACK` để B tiếp tục/thất bại theo session settings.

### 10.3. Lock wait timeout

Một session test có thể dùng:

```sql
SET SESSION innodb_lock_wait_timeout = 3;

START TRANSACTION;

SELECT *
FROM wallets
WHERE id = 1
FOR UPDATE;
```

Nếu timeout, InnoDB thường báo lỗi lock wait timeout (ví dụ mã lỗi cụ thể của engine/driver). Không kết luận toàn bộ transaction đã tự rollback trong mọi cấu hình: **statement timeout và transaction rollback không phải đồng nghĩa**. Để cleanup chắc chắn trong test:

```sql
ROLLBACK;
```

### 10.4. PESSIMISTIC_READ trên MySQL

MySQL/InnoDB có cơ chế shared locking read, ví dụ cú pháp `FOR SHARE` ở những phiên bản hỗ trợ (các bản cũ có thể dùng cú pháp khác). Provider có thể chọn SQL tương ứng hoặc khóa mạnh hơn; phải kiểm chứng SQL đã phát.

### 10.5. REPEATABLE READ và gap/next-key locking

Ở MySQL/InnoDB, dưới một số isolation levels, điều kiện tìm kiếm theo **range/index** có thể tạo **next-key/gap locks**, chặn không chỉ UPDATE row hiện có mà còn INSERT vào khoảng chỉ mục.

Ví dụ ý tưởng:

```sql
START TRANSACTION;

SELECT *
FROM wallets
WHERE id BETWEEN 10 AND 20
FOR UPDATE;
```

Một transaction B thử INSERT ID trong vùng có thể bị ảnh hưởng tùy:

- Isolation level.
- Index được sử dụng.
- Query plan.
- Range predicate.
- Khóa thực tế InnoDB lấy.
- Trường hợp unique lookup một row cụ thể.

Đừng lấy behavior của `WHERE id = 1` rồi suy ra behavior của `WHERE id BETWEEN 10 AND 20`. Đây là **một scenario khác** cần đo độc lập.

---

## 11. Quan sát khóa trên MySQL/InnoDB

Trên các phiên bản MySQL 8 thích hợp, các bảng Performance Schema hữu ích:

```sql
SELECT *
FROM performance_schema.data_lock_waits;
```

```sql
SELECT
    ENGINE,
    ENGINE_LOCK_ID,
    ENGINE_TRANSACTION_ID,
    OBJECT_SCHEMA,
    OBJECT_NAME,
    INDEX_NAME,
    LOCK_TYPE,
    LOCK_MODE,
    LOCK_STATUS,
    LOCK_DATA
FROM performance_schema.data_locks
WHERE OBJECT_NAME = 'wallets';
```

Có thể đối chiếu requesting/blocking lock IDs trong `data_lock_waits` với `data_locks`. Một số hệ quản trị tương thích MySQL có hệ thống quan sát hoặc schema khác; không mặc nhiên các truy vấn trên hoạt động trong mọi phiên bản MariaDB.

### 11.1. Kiểm tra giao dịch InnoDB

Có thể dùng các view/trạng thái hỗ trợ của InnoDB và `SHOW ENGINE INNODB STATUS` để phân tích lock waits/deadlocks:

```sql
SHOW ENGINE INNODB STATUS;
```

Output lớn và quyền truy cập có thể bị giới hạn. Với deadlock, InnoDB thường lưu thông tin một deadlock gần đây; không xem nó là log đầy đủ vô hạn của mọi deadlock.

### 11.2. Không đổ lỗi cho JPA khi pool thiếu connection

Nếu thread B chưa có JDBC connection vì connection pool size = 1, MySQL sẽ **không** thấy B như một DB session chờ row lock. Hãy kiểm tra metrics pool active/pending/timeout trước khi kết luận lock contention.

### 11.3. Isolation level phải được đo

Một default phổ biến của InnoDB là REPEATABLE READ, nhưng không áp đặt điều đó cho mọi môi trường. Ghi giá trị session hiện tại và xác nhận code/framework có override isolation hay không. Thay isolation có thể thay phạm vi locks và behavior của range scans.

---

## 12. SQL Server: không suy diễn cú pháp FOR UPDATE

SQL Server dùng mô hình locking và các table hints khác PostgreSQL/MySQL. Không sao chép:

```sql
SELECT ... FOR UPDATE;
```

sang SQL Server như một cú pháp chung.

Trong một bài thử có thể dùng SQL Server table hints phù hợp, ví dụ:

Phiên A:

```sql
BEGIN TRANSACTION;

SELECT id, balance, version
FROM dbo.wallets WITH (UPDLOCK, ROWLOCK)
WHERE id = 1;

-- Giữ transaction mở.
```

Phiên B:

```sql
BEGIN TRANSACTION;

SELECT id, balance, version
FROM dbo.wallets WITH (UPDLOCK, ROWLOCK)
WHERE id = 1;

-- Quan sát blocking/wait.
```

Sau khi kết thúc, nhớ:

```sql
COMMIT TRANSACTION;
```

hoặc:

```sql
ROLLBACK TRANSACTION;
```

### 12.1. Hints không phải bảo đảm một row lock duy nhất

`ROWLOCK` là hint, không phải lời hứa database sẽ chỉ khóa đúng một row trong mọi tình huống. SQL Server có thể áp dụng khóa key/page/table tùy plan, index, memory, escalation, isolation và các constraints. `UPDLOCK` mang semantics khóa phục vụ cập nhật; không phải “dịch 1:1” cho mọi yêu cầu JPA PESSIMISTIC_WRITE.

### 12.2. READ_COMMITTED_SNAPSHOT ảnh hưởng SELECT thường

Khi SQL Server bật row-versioning options như `READ_COMMITTED_SNAPSHOT`, một SELECT thông thường dưới READ COMMITTED có thể đọc phiên bản thay vì chờ exclusive row locks như trong một cấu hình locking READ COMMITTED cổ điển. Điều này ảnh hưởng kết luận từ test W/SELECT thường.

### 12.3. Quan sát sessions chờ

Ví dụ diagnostic:

```sql
SELECT
    session_id,
    blocking_session_id,
    wait_type,
    wait_time,
    wait_resource
FROM sys.dm_exec_requests
WHERE blocking_session_id <> 0;
```

```sql
SELECT
    request_session_id,
    resource_type,
    request_mode,
    request_status,
    resource_associated_entity_id
FROM sys.dm_tran_locks
ORDER BY request_session_id;
```

Các DMV có yêu cầu quyền và đôi khi hiển thị nhiều hoạt động không liên quan. Lọc thêm theo session IDs hoặc database để tránh nhầm blocker.

### 12.4. SQL Server deadlock/timeout

SQL Server có cơ chế phát hiện deadlock và chọn victim; exception phía JDBC/JPA có thể bị wrap. Lock timeout còn có thể được cấu hình ở session bằng lệnh vendor-specific, khác với query/connection timeout. Ghi mã lỗi SQL Server/JDBC thực tế thay vì đoán exception JPA từ tên error.

---

## 13. Oracle Database: FOR UPDATE, WAIT và NOWAIT

Oracle hỗ trợ locking clauses với biến thể riêng.

Phiên A:

```sql
-- Transaction bắt đầu theo cơ chế của Oracle session.
SELECT id, balance, version
FROM wallets
WHERE id = 1
FOR UPDATE;

UPDATE wallets
SET balance = balance + 10,
    version = version + 1
WHERE id = 1;

-- Giữ transaction tới khi COMMIT/ROLLBACK.
```

Phiên B:

```sql
SELECT id, balance, version
FROM wallets
WHERE id = 1
FOR UPDATE WAIT 3;
```

Hoặc để không chờ:

```sql
SELECT id, balance, version
FROM wallets
WHERE id = 1
FOR UPDATE NOWAIT;
```

Sau test, commit/rollback từng session.

### 13.1. Kiểm tra wait/blocking trong Oracle

Tùy quyền:

```sql
SELECT
    sid,
    serial#,
    username,
    blocking_session,
    event,
    seconds_in_wait
FROM v$session
WHERE blocking_session IS NOT NULL;
```

Các views như `v$locked_object` có thể hỗ trợ phân tích đối tượng bị lock, nhưng không nên coi một view là danh sách đầy đủ các row locks với primary keys cụ thể.

### 13.2. Đừng nhầm SQL và JPA mapping

Oracle có nhiều biến thể cú pháp `FOR UPDATE`, `WAIT`, `NOWAIT`, `SKIP LOCKED`. JPA provider/dialect phải quyết định cách phát SQL tương ứng khi ứng dụng dùng `PESSIMISTIC_WRITE` và hints. Việc native SQL chạy thành công **chưa đủ** để khẳng định `EntityManager.find(..., PESSIMISTIC_WRITE)` dùng đúng cùng clause.

### 13.3. Phân loại Oracle error

Các lỗi lock busy, timeout, deadlock có mã Oracle khác nhau và có thể được Hibernate/framework map thành exception khác. Ghi ít nhất DB error code, SQLState nếu có, root cause và transaction disposition.

---

## 14. Ma trận khác biệt theo DBMS: nên kết luận ở mức nào?

| Khía cạnh | PostgreSQL | MySQL/InnoDB | SQL Server | Oracle |
|---|---|---|---|---|
| Ví dụ locking write SQL | `FOR UPDATE` | `FOR UPDATE` | Hints như `UPDLOCK` | `FOR UPDATE` |
| Ví dụ read/shared locking | `FOR SHARE` | `FOR SHARE` ở phiên bản phù hợp | Hints/lock modes riêng | Cơ chế riêng, không suy 1:1 |
| MVCC/row version | Có | Có | Tùy isolation/RCSI | Có cơ chế consistent reads |
| Range/gap effects | Cần xem isolation/predicate | Next-key/gap tùy isolation/index | Key-range tùy isolation/hints | Phụ thuộc isolation/SQL |
| Diagnostic phổ biến | `pg_stat_activity`, `pg_locks` | Performance Schema | DMVs | `v$session`/views |
| Statement lock timeout | Setting riêng | Setting InnoDB riêng | Setting session riêng | Clauses WAIT/NOWAIT riêng |
| SQL generated by JPA | Phải quan sát | Phải quan sát | Phải quan sát | Phải quan sát |

Bảng này chỉ là **bản đồ nơi cần thử**. Không dùng nó để khẳng định tất cả phiên bản có cùng behavior. Ví dụ “đã chạy với PostgreSQL 16, READ COMMITTED, Hibernate 6.x, JDBC driver Y” là kết luận có phạm vi cụ thể; đổi một thành phần cần đánh giá lại.

---

## 15. JPA: lấy khóa từ EntityManager.find

Ví dụ sử dụng `RESOURCE_LOCAL` với transaction do ứng dụng điều khiển:

```java
EntityManager em = emf.createEntityManager();

try {
    EntityTransaction tx = em.getTransaction();
    tx.begin();

    try {
        Wallet wallet = em.find(
            Wallet.class,
            1L,
            LockModeType.PESSIMISTIC_WRITE
        );

        if (wallet == null) {
            throw new IllegalStateException("Wallet not found");
        }

        wallet.credit(new BigDecimal("10.00"));

        // Có thể flush để quan sát SQL UPDATE;
        // vẫn chưa phải COMMIT.
        em.flush();

        tx.commit();
    } catch (RuntimeException failure) {
        if (tx.isActive()) {
            tx.rollback();
        }
        throw failure;
    }
} finally {
    em.close();
}
```

Imports:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import jakarta.persistence.LockModeType;
import java.math.BigDecimal;
```

### 15.1. Lock phải được yêu cầu khi có transaction hợp lệ

`PESSIMISTIC_WRITE` thường cần transaction đang active. Nếu gọi bên ngoài transaction context phù hợp, provider có thể ném `TransactionRequiredException` hoặc loại exception theo contract của API.

Đừng viết test bỏ transaction rồi xem kết quả là hành vi DB row lock có ý nghĩa.

### 15.2. find có thể phát SELECT + lock, hoặc chiến lược khác

Provider có thể sinh SQL dạng:

```sql
SELECT ...
FROM wallets
WHERE id = ?
FOR UPDATE;
```

nhưng cách sinh cụ thể phụ thuộc provider/dialect và database. Hãy bật logging để biết có `FOR UPDATE`, locking hint, follow-on lock SQL hay điều chỉnh nào khác.

### 15.3. Không tin trạng thái entity hiện có trong cache

Nếu Wallet#1 đã nằm trong persistence context trước khi gọi `find` có lock mode, provider có thể không cần SELECT thông thường giống như truy xuất entity lần đầu, nhưng vẫn phải áp dụng yêu cầu lock theo semantics. Với phép thử SQL rõ ràng, nên dùng **EntityManager mới cho từng transaction**, tránh first-level cache làm khó việc quan sát.

### 15.4. flush không giải phóng row locks

`em.flush()` đồng bộ pending changes vào DB trong transaction. Nó **không phải commit** và không tự giải phóng những transaction-held locks. Để kiểm chứng, giữ A mở sau flush rồi cho B lock/UPDATE cùng row.

---

## 16. JPQL query.setLockMode

Không chỉ `find`, bạn có thể gắn lock mode cho query:

```java
List<Wallet> wallets = em.createQuery(
    """
    SELECT w
    FROM Wallet w
    WHERE w.id IN :ids
    ORDER BY w.id
    """,
    Wallet.class)
    .setParameter("ids", List.of(1L, 2L))
    .setLockMode(LockModeType.PESSIMISTIC_WRITE)
    .getResultList();
```

### 16.1. SQL có thể khác khi query JOIN, DISTINCT hoặc pagination

Nếu JPQL query phức tạp có `DISTINCT`, `JOIN FETCH`, `GROUP BY` hoặc pagination, một số providers/dialects có thể dùng **follow-on locking**: query root trước rồi phát SQL lock riêng. Có database không cho phép áp `FOR UPDATE` trực tiếp lên một số query shape.

Phải quan sát **toàn bộ SQL statements**, không chỉ câu đầu. Đừng suy “query đầu không có FOR UPDATE, vậy không có lock” khi provider đã dùng bước khóa tiếp theo.

### 16.2. Query lock không phải khóa tất cả dữ liệu liên quan vô hạn

Ví dụ khóa Wallet entities trong query không tự khóa toàn bộ object graph tùy ý của các entity quan hệ. Phạm vi lock cần được xét theo khóa root, mapping, provider/dialect, lock scope hints và SQL thực tế.

### 16.3. Không gắn PESSIMISTIC_WRITE cho scalar count để “khóa cả bảng”

`SELECT COUNT(w)` trả scalar; lock mode của query chủ yếu có semantics với entities được chọn. Việc đòi row locks khi query chỉ trả aggregate có thể không hợp lệ hoặc phụ thuộc provider. Nếu nghiệp vụ cần serialize một tập bản ghi, phải xác định **rows cụ thể** cần khóa và transaction strategy tương ứng.

---

## 17. Kiểm chứng hai EntityManager và hai threads

Một test JPA có ý nghĩa phải dùng hai `EntityManager` độc lập, lý tưởng là hai JDBC connections đang hoạt động. Ví dụ sau là **harness minh họa có kiểm soát** cho `RESOURCE_LOCAL`. Nó không đồng thời sửa cùng `EntityManager` từ nhiều threads.

```java
package demo.locklab;

import jakarta.persistence.EntityManager;
import jakarta.persistence.EntityManagerFactory;
import jakarta.persistence.EntityTransaction;
import jakarta.persistence.LockModeType;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public final class PessimisticLockProbe {

    private final EntityManagerFactory emf;

    public PessimisticLockProbe(EntityManagerFactory emf) {
        this.emf = emf;
    }

    public void run(long walletId) throws Exception {
        CountDownLatch aLocked = new CountDownLatch(1);
        CountDownLatch releaseA = new CountDownLatch(1);
        CountDownLatch bAboutToLock = new CountDownLatch(1);

        ExecutorService pool = Executors.newFixedThreadPool(2);

        try {
            Future<?> a = pool.submit(() -> {
                EntityManager em = emf.createEntityManager();
                EntityTransaction tx = em.getTransaction();

                try {
                    tx.begin();

                    Wallet w = em.find(
                        Wallet.class, walletId,
                        LockModeType.PESSIMISTIC_WRITE
                    );
                    if (w == null) {
                        throw new IllegalStateException("No wallet");
                    }

                    System.out.println("A acquired lock");
                    aLocked.countDown();

                    if (!releaseA.await(30, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                            "A release not signaled");
                    }

                    tx.commit();
                    System.out.println("A committed");
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new RuntimeException(e);
                } finally {
                    if (tx.isActive()) {
                        tx.rollback();
                    }
                    em.close();
                }
            });

            Future<Long> b = pool.submit(() -> {
                if (!aLocked.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                        "A did not acquire lock");
                }

                EntityManager em = emf.createEntityManager();
                EntityTransaction tx = em.getTransaction();

                try {
                    tx.begin();

                    bAboutToLock.countDown();

                    long started = System.nanoTime();

                    Wallet w = em.find(
                        Wallet.class, walletId,
                        LockModeType.PESSIMISTIC_WRITE
                    );
                    if (w == null) {
                        throw new IllegalStateException("No wallet");
                    }

                    long elapsedNanos =
                        System.nanoTime() - started;

                    tx.commit();

                    return TimeUnit.NANOSECONDS
                        .toMillis(elapsedNanos);
                } finally {
                    if (tx.isActive()) {
                        tx.rollback();
                    }
                    em.close();
                }
            });

            try {
                if (!aLocked.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                        "A failed to obtain lock");
                }

                if (!bAboutToLock.await(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                        "B did not start attempt");
                }

                // B đã tới sát lời gọi find(..., WRITE).
                // Chưa chứng minh B thực sự đang chờ DB row lock.
                try {
                    Long millis = b.get(300, TimeUnit.MILLISECONDS);
                    System.out.println(
                        "B completed before release: " + millis);
                } catch (TimeoutException expected) {
                    System.out.println(
                        "B still running; inspect DB wait view now");
                }

                // Có thể tạm đặt breakpoint tại đây để
                // dùng connection thứ ba xem blocking sessions.
            } finally {
                // Dù observer có exception, không bỏ quên A.
                releaseA.countDown();
            }

            // Thu thập cả exception của A/B nếu có.
            a.get(30, TimeUnit.SECONDS);
            Long bMillis = b.get(30, TimeUnit.SECONDS);

            System.out.println("B lock elapsed ms: " + bMillis);
        } finally {
            releaseA.countDown();
            pool.shutdownNow();
        }
    }
}
```

### 17.1. Giới hạn của harness

Code cố tình dùng timeout để **không giữ A vô hạn**. Nhưng việc `b.get(300 ms)` bị timeout chỉ chứng minh B chưa hoàn tất trong khoảng quan sát, **không chứng minh nguyên nhân là row lock**. B có thể đang chờ connection, thread scheduling hoặc câu SQL khác.

Để ghi nhận chính xác, tại thời điểm B chưa xong hãy quan sát DB:

- PostgreSQL: `pg_blocking_pids`/`pg_stat_activity`.
- MySQL/InnoDB: `performance_schema.data_lock_waits`.
- SQL Server: `sys.dm_exec_requests`.
- Oracle: `v$session`.

### 17.2. Bảo đảm pool đủ connections

Nếu pool chỉ có một connection, A giữ connection và B chờ pool. Trước khi chạy harness, bảo đảm pool cho phép ít nhất **hai connections đồng thời**, và nếu cần observer trong cùng pool thì phải có connection thứ ba hoặc dùng SQL client khác.

### 17.3. Timeouts của harness không phải lock timeout

`b.get(300, MILLISECONDS)` chỉ timeout **thread Future wait** ở Java caller. Nó không tự hủy SQL statement, không cấu hình DB lock wait và không rollback B. Đừng nhầm nó với `jakarta.persistence.lock.timeout` hoặc DB `lock_timeout`.

### 17.4. Khả năng cleanup

Trong một harness production-grade, nên lưu log lifecycle, dùng finally, bounded waits, transaction rollback, cancel tasks khi test thất bại, close EntityManagers và loại bỏ session bị kẹt. Nếu thread bị block trong JDBC driver lâu hơn các timeouts Java, shutdownNow có thể không ngắt ngay driver call. Cần DB-side timeout và khả năng kill session trong môi trường test.

---

## 18. Dùng latch để điều phối, không chỉ dùng Thread.sleep

Một cách thử thiếu chắc chắn:

```java
Thread.sleep(1000);
startTransactionB();
```

không cam kết A đã lấy khóa: A có thể bị chậm vì scheduler, network hoặc pool.

Thay bằng:

```text
A:
  begin
  lock row
  signal aLocked
  wait releaseA
  commit

B:
  wait aLocked
  begin
  attempt lock same row
  finish/throw

Observer:
  wait aLocked
  let B attempt
  inspect database
  releaseA
```

`CountDownLatch` giúp đảm bảo thứ tự các **mốc do ứng dụng kiểm soát**. Nhưng một latch “B sắp gọi find” vẫn không chứng minh driver đã gửi SQL; cần DB monitoring để phân biệt trạng thái blocked thật sự.

### 18.1. Không chia sẻ EntityManager

Sai:

```java
EntityManager em = emf.createEntityManager();

executor.submit(() -> em.find(Wallet.class, 1L));
executor.submit(() -> em.find(Wallet.class, 1L));
```

EntityManager không được dùng đồng thời tùy tiện như một thread-safe service. Test kiểu này có thể tạo lỗi persistence context thay vì kiểm chứng transaction locks.

### 18.2. Không dùng cùng transaction để mô phỏng hai người dùng

Hai thao tác trong cùng transaction có thể đọc/ghi những dữ liệu transaction đã khóa mà không tạo contention như hai transaction độc lập. Cần hai transactions thật.

---

## 19. Kiểm chứng timeout qua Jakarta Persistence hint

Có thể truyền map hints khi `find`:

```java
Map<String, Object> hints = new HashMap<>();

hints.put("jakarta.persistence.lock.timeout", 2_000);

Wallet wallet = em.find(
    Wallet.class,
    1L,
    LockModeType.PESSIMISTIC_WRITE,
    hints
);
```

Hoặc trên query:

```java
TypedQuery<Wallet> query = em.createQuery(
    "SELECT w FROM Wallet w WHERE w.id = :id",
    Wallet.class
);

query.setParameter("id", 1L);
query.setLockMode(LockModeType.PESSIMISTIC_WRITE);
query.setHint("jakarta.persistence.lock.timeout", 2_000);

Wallet wallet = query.getSingleResult();
```

### 19.1. Đơn vị và ý định

Hint lock timeout trong Jakarta Persistence có ý định thể hiện **thời gian chờ lấy khóa**, thường tính bằng mili-giây, với giá trị không chờ được biểu diễn theo semantics API/hint. Nhưng **việc hint được provider/dialect/DBMS hỗ trợ như thế nào có thể khác nhau**; những unsupported hints có thể bị bỏ qua.

### 19.2. Hãy thử ba tình huống

1. Không truyền hint: quan sát wait theo DB default.
2. Hint `0`: kiểm tra có nonblocking acquisition/fail nhanh trên stack không.
3. Hint `2_000`: kiểm tra thời gian thất bại thực tế và root cause.

**Không dùng kết quả của Hibernate trên một database để suy ra mọi provider đều hỗ trợ đúng 2 giây.**

### 19.3. Lock timeout khác query timeout

`jakarta.persistence.query.timeout` có mục tiêu **timeout thực thi query** rộng hơn; `jakarta.persistence.lock.timeout` nhắm tới **đợi khóa**. JDBC driver/network/socket timeout và transaction timeout của framework là những lớp khác nữa.

Nếu ứng dụng báo timeout, hãy ghi chính xác **cơ chế nào kích hoạt trước**:

```text
B wait:
  DB lock timeout?
  JPA lock timeout hint?
  JDBC query timeout?
  Spring transaction timeout?
  Pool connection acquisition timeout?
  Network/socket timeout?
  Future.get(...) timeout của test?
```

Không gộp tất cả vào một kết luận “đã cấu hình lock timeout”.

### 19.4. Session-level settings có thể còn hiệu lực

Nếu test đổi lock timeout ở database session, hãy reset khi trả connection về pool nếu driver/pool không reset giúp. Một connection mang session setting cũ sang request khác có thể làm test sau sai hoặc ảnh hưởng production.

---

## 20. Phân loại exception: statement vs transaction

Các exception thường cần phân biệt:

| Loại | Ngữ nghĩa cần chú ý |
|---|---|
| `LockTimeoutException` | Không lấy được lock trong thời gian cho phép; theo semantics JPA, tình huống thất bại ở mức statement không nhất thiết đánh dấu toàn transaction rollback |
| `PessimisticLockException` | Lỗi locking có rollback cấp transaction theo semantics JPA |
| `TransactionRequiredException` | Yêu cầu transaction nhưng không có transaction hợp lệ |
| `OptimisticLockException` | Version check/conflict; có thể xuất hiện ở những luồng kết hợp versioning, không nên mặc định là deadlock |
| `PersistenceException` hoặc provider wrapper | Cần kiểm tra root cause và SQLState/vendor code |
| Spring DataAccessException | Framework có thể translate exception JPA/JDBC thành loại riêng |

### 20.1. Không đoán rollback chỉ từ class name

DBMS có thể đánh dấu transaction aborted sau statement error, hoặc chỉ rollback statement rồi giữ transaction active tùy engine/configuration. Provider/framework cũng có thể mark rollback-only.

Ngay cả khi JPA exception semantics phân biệt statement-level và transaction-level, **cách database thực tế xử lý một lỗi cụ thể phải được quan sát**.

### 20.2. Mẫu RESOURCE_LOCAL cleanup an toàn

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Wallet wallet = em.find(
        Wallet.class,
        1L,
        LockModeType.PESSIMISTIC_WRITE
    );

    if (wallet == null) {
        throw new IllegalStateException("Missing wallet");
    }

    wallet.credit(new BigDecimal("5.00"));
    tx.commit();
} catch (RuntimeException failure) {
    if (tx.isActive()) {
        try {
            tx.rollback();
        } catch (RuntimeException rollbackFailure) {
            failure.addSuppressed(rollbackFailure);
        }
    }
    throw failure;
} finally {
    em.close();
}
```

Với một read-only lock attempt, ứng dụng có thể muốn xử lý `LockTimeoutException` và thử một operation khác trong transaction nếu stack cho phép. **Không mặc định** transaction vẫn an toàn để sử dụng tiếp sau lỗi lock: cần kiểm tra DB state và rollback policy. Trong một service nghiệp vụ đơn giản, rollback và retry unit of work mới thường dễ reasoning hơn.

### 20.3. JTA/Spring-managed transaction khác RESOURCE_LOCAL

Nếu `EntityManager` do JTA hoặc Spring transaction manager quản lý, không tự gọi `em.getTransaction().begin()` theo mẫu RESOURCE_LOCAL. Dùng `@Transactional`/transaction manager phù hợp; exception handling và rollback policy do framework xử lý theo cấu hình.

---

## 21. Kiểm chứng PESSIMISTIC_FORCE_INCREMENT

`PESSIMISTIC_FORCE_INCREMENT` là một tình huống riêng cần thử với `Wallet.version`:

```java
EntityManager em = emf.createEntityManager();
EntityTransaction tx = em.getTransaction();

try {
    tx.begin();

    Wallet wallet = em.find(
        Wallet.class,
        1L,
        LockModeType.PESSIMISTIC_FORCE_INCREMENT
    );

    Long versionObserved = wallet.getVersion();

    // Không nhất thiết sửa balance.
    tx.commit();

    System.out.println("Version at access: " + versionObserved);
} catch (RuntimeException e) {
    if (tx.isActive()) tx.rollback();
    throw e;
} finally {
    em.close();
}
```

Sau khi commit, dùng **EntityManager mới** truy vấn database để kiểm tra version đã tăng theo expected semantics của force increment.

### 21.1. Thời điểm version tăng là chi tiết cần quan sát

Provider có thể sử dụng SQL update/version increment ở một giai đoạn cụ thể, không nhất thiết `wallet.getVersion()` ngay sau `find` đã phản ánh giá trị cuối. Bài thử đúng cần:

1. Ghi version trước transaction.
2. Thực hiện force increment.
3. Quan sát SQL.
4. Commit.
5. Mở context mới và đọc version persisted.
6. Thử rollback và xác định version persisted không bị tăng sau rollback trong transaction thông thường.

### 21.2. Không trộn với optimistic update

Một entity có `@Version` khi được sửa và flush/commit thường dùng optimistic version checking. `PESSIMISTIC_FORCE_INCREMENT` tạo yêu cầu tăng version ngay cả khi không sửa domain fields, theo semantics của lock mode.

### 21.3. Có thể phát sinh SQL riêng

Nếu thấy `UPDATE wallets SET version=...` bên cạnh SQL lock, không vội coi đó là “write ngoài ý muốn”. Nó có thể là phần đúng của force increment. Nhưng cần đảm bảo không có trigger/logic khác gây tác động không dự định.

---

## 22. PESSIMISTIC_READ, PESSIMISTIC_WRITE và các phép đo phải tương ứng

Không phải mọi phép thử đều dùng cùng loại truy vấn B.

### 22.1. Read/read

A và B cùng yêu cầu `PESSIMISTIC_READ`. Quan sát liệu B lấy được lock ngay hay chờ. Shared locks có thể tương thích, nhưng không bảo đảm mọi DBMS/provider map READ thành dạng shared cụ thể.

### 22.2. Read/write

A đọc có khóa READ, B yêu cầu WRITE hoặc UPDATE. Kết quả cho biết READ có ngăn writer cùng row theo cách engine triển khai không.

### 22.3. Write/read thường

A WRITE, B `SELECT` thường. Với MVCC, B có thể đọc committed version và không chờ. Đây là một behavior hợp lệ cần ghi nhận.

### 22.4. Write/read có khóa

A WRITE, B `PESSIMISTIC_READ` hoặc shared locking read. Khác `SELECT` thường, đây là một locking operation có thể chờ.

### 22.5. Write/write

A WRITE, B WRITE trên cùng row. Đây là phép thử nền tảng dễ quan sát contention và giải phóng khóa sau commit/rollback.

### 22.6. Write/khác row

A WRITE wallet#1, B WRITE wallet#2. Nếu B vẫn chờ, cần tìm lý do: index/gap locking, table lock escalation, uncommitted DDL, pool, triggers, foreign keys hoặc lock manager scope. Đừng mặc định mọi hàng khác nhau chắc chắn không có tương tác trên mọi DBMS/workload.

---

## 23. Lock scope và association graph

JPA có khái niệm phạm vi khóa bi quan, ví dụ hint:

```java
Map<String, Object> hints = new HashMap<>();

hints.put(
    "jakarta.persistence.lock.scope",
    PessimisticLockScope.EXTENDED
);

Wallet wallet = em.find(
    Wallet.class,
    1L,
    LockModeType.PESSIMISTIC_WRITE,
    hints
);
```

Import:

```java
import jakarta.persistence.PessimisticLockScope;
```

### 23.1. NORMAL và EXTENDED không có nghĩa “khóa mọi entity con”

Phạm vi khóa bi quan trong JPA liên quan đến row của entity và một số mapping/join-table/collection-table theo semantics NORMAL/EXTENDED. Nó **không phải** công cụ tự động khóa toàn bộ object graph vô hạn của các associations `@ManyToOne`/`@OneToMany` bất kể ownership.

### 23.2. Provider/DBMS có thể không triển khai giống kỳ vọng

Hint có thể bị bỏ qua nếu không hỗ trợ, hoặc SQL được triển khai theo chiến lược khác nhau. Khi nghiệp vụ cần bảo vệ quan hệ trong join table, phải dựng test riêng:

- A lock owner entity với NORMAL.
- B sửa join-table association liên quan.
- A lock với EXTENDED.
- B lặp thao tác.
- So sánh SQL, wait states và DB effects.

### 23.3. Đừng dùng lock scope để giải quyết phantom tổng quát

Khóa những rows hiện có không tự ngăn transaction khác INSERT row mới thỏa cùng predicate, trừ khi isolation/predicate locking/range-lock behavior cụ thể bảo vệ điều đó. Đây là bài toán isolation/serialization, không chỉ thêm EXTENDED.

---

## 24. Lock theo primary key và lock theo range có thể khác

Ví dụ tìm đúng một Wallet:

```jpql
SELECT w
FROM Wallet w
WHERE w.id = :id
```

và tìm theo phạm vi:

```jpql
SELECT w
FROM Wallet w
WHERE w.balance >= :minBalance
```

Nếu cùng dùng `PESSIMISTIC_WRITE`, phạm vi SQL/index được DB truy cập có thể rất khác:

- Unique-key lookup có thể nhắm tới một record cụ thể.
- Range scan có thể truy cập nhiều records/index entries.
- MySQL/InnoDB ở một số isolation có thể dùng next-key/gap locks.
- SQL Server với isolation/hints nhất định có thể sử dụng key-range locks.
- PostgreSQL row-level `FOR UPDATE` không tự bảo đảm chặn INSERT mới thỏa mọi predicate ở READ COMMITTED.

### 24.1. Phantoms khác lost update

**Lost update**: hai giao dịch đọc/sửa cùng một entity/hàng rồi ghi đè nhau.

**Phantom**: một giao dịch lặp lại truy vấn theo predicate và tập rows thay đổi do INSERT/DELETE/UPDATE của transaction khác.

Khóa một số rows đang tồn tại có thể ngăn writer trên những rows đó, nhưng **không nhất thiết ngăn xuất hiện rows mới** trong tập được truy vấn.

### 24.2. Test phantom riêng

A:

```text
BEGIN
SELECT wallets WHERE balance >= 100 FOR UPDATE
giữ transaction
```

B:

```text
BEGIN
INSERT wallet mới có balance=150
thử COMMIT
```

Quan sát B có chờ hay không, A có thấy phantom ở lần SELECT sau hay không và điều này thay đổi theo isolation/index. Đừng đưa một expected result cố định trước khi biết target DBMS.

---

## 25. Lock ordering và deadlock

Deadlock không đơn thuần là “B chờ A”. Deadlock xuất hiện khi có **chu trình phụ thuộc**.

```text
Transaction A: giữ lock wallet#1
               cần thêm lock wallet#2

Transaction B: giữ lock wallet#2
               cần thêm lock wallet#1

A chờ B, B chờ A -> deadlock cycle
```

### 25.1. Dựng test trên môi trường chuyên biệt

Phiên A:

```text
BEGIN
lock wallet#1
[barrier]
attempt lock wallet#2
```

Phiên B:

```text
BEGIN
lock wallet#2
[barrier]
attempt lock wallet#1
```

Database deadlock detector có thể chọn một transaction làm victim. Ghi:

- DB error code/SQLState.
- Transaction bị hủy hay statement thất bại.
- Thời gian deadlock detection.
- Ảnh hưởng tới state persisted.
- Exception phía JPA/Spring.
- Cleanup của cả hai transactions.

### 25.2. Deadlock khác lock timeout

| Đặc điểm | Lock wait thông thường | Lock timeout | Deadlock |
|---|---|---|---|
| Có chu trình chờ? | Không bắt buộc | Không bắt buộc | Có |
| Có thể hết khi A commit? | Có | Có nếu trước hạn | Hệ quản trị cần phá vòng chờ |
| Kết quả | B được lock sau wait | Một thao tác thất bại theo deadline | Một/vài transaction bị chọn xử lý |
| Hướng xử lý | Giảm thời gian giữ lock | Backoff/retry có kiểm soát | Thứ tự lock nhất quán, retry cả unit |

### 25.3. Phòng ngừa bằng thứ tự khóa

Nếu một workflow phải khóa nhiều Wallets, cố gắng lấy theo **thứ tự cố định**, ví dụ ID tăng dần:

```text
A: lock #1, sau đó #2
B: lock #1, sau đó #2
```

Cách này giảm nguy cơ deadlock do đảo thứ tự. Nhưng deadlocks vẫn có thể phát sinh qua SQL khác, indexes, foreign keys, triggers hoặc một workflow thứ ba. Cần retry policy và observability.

### 25.4. Retry phải làm lại transaction

Một deadlock victim thường không thể đơn giản “tiếp tục câu lệnh tiếp theo” như không có lỗi. Retry nên tạo **unit of work/transaction mới**, giới hạn số lần, có backoff/jitter và idempotency cho nghiệp vụ có side effects.

---

## 26. Khóa bi quan và thao tác đọc ngoài transaction

Một số tình huống phát hiện từ test:

```java
Wallet w = em.find(
    Wallet.class,
    1L,
    LockModeType.PESSIMISTIC_WRITE
);
```

nhưng không có transaction thích hợp có thể lỗi. Vì vậy trước khi test, cần biết:

- EntityManager được tạo bằng `RESOURCE_LOCAL` hay container/JTA?
- Spring `@Transactional` có được áp dụng thật (proxy invocation) không?
- Có self-invocation khiến annotation không tạo transaction không?
- Transaction có cùng connection trong toàn method không?
- Isolation mặc định là gì?
- Gọi qua repository method có mở transaction readonly chỉ cho query không?
- Tài nguyên connection có được giữ đến commit không?

### 26.1. Spring self-invocation không phải thí nghiệm DB lock

Ví dụ một method trong cùng bean gọi trực tiếp method `@Transactional` của chính nó, trong cấu hình Spring proxy thông dụng có thể không đi qua proxy, khiến transaction không được thiết lập như kỳ vọng. Test cần xác minh transaction thực tế trước khi quy kết DB lock không hoạt động.

### 26.2. RESOURCE_LOCAL và JTA cần phân biệt

`RESOURCE_LOCAL`:

```java
EntityTransaction tx = em.getTransaction();
tx.begin();
// ...
tx.commit();
```

JTA/Spring-managed:

```java
@Transactional
public void updateWallet(...) {
    // ...
}
```

Không pha hai cơ chế điều khiển transaction trên cùng EntityManager một cách tùy tiện.

---

## 27. Query timeout, lock timeout, transaction timeout và pool timeout

Trong thực tế, các lớp deadline có thể chồng lên nhau:

```text
HTTP timeout                 5s
    |
Service transaction timeout  4s
    |
JPA query timeout            3s
    |
JPA lock timeout hint        2s
    |
DB lock wait timeout         10s
    |
JDBC socket timeout          30s
```

Con số chỉ minh họa, không phải đề xuất mặc định. Cơ chế nào tác động trước phụ thuộc provider, DBMS và thời điểm thực thi.

### 27.1. Kiểm chứng có ý nghĩa phải cô lập biến

Thử **từng loại timeout**, giữ các lớp khác đủ lớn trong môi trường test để quan sát timeout cần đo. Nếu app request timeout 1 giây nhưng lock timeout muốn thử 5 giây, bạn sẽ chỉ thấy HTTP/request timeout trước.

### 27.2. Connection pool timeout không phải lock timeout

Nếu có pool size 1:

```text
A giữ connection.
B chưa lấy được connection.
B báo acquisition timeout.
```

DB không hề có phiên B chờ row lock. Ghi pool pending connections và DB active sessions để phân biệt.

### 27.3. Timeout không luôn hủy câu SQL đang chạy

Một timeout ở tầng client có thể làm caller ngừng chờ nhưng database statement/transaction chưa được hủy ngay theo driver. Cần cleanup rõ ràng, cancellation support và DB-side safeguards để không để lock kéo dài.

---

## 28. Kiểm tra transaction kết thúc và khóa được giải phóng

Một thí nghiệm đáng tin phải xác nhận không còn session khóa sau khi kết thúc.

### 28.1. Commit path

A:

```text
begin
lock wallet#1
update wallet#1
commit
```

B đang chờ nếu lock tương tranh. Sau A commit, B phải được giải quyết theo semantics của isolation/DBMS: thường có thể nhận khóa hoặc có lỗi cụ thể.

### 28.2. Rollback path

A:

```text
begin
lock wallet#1
update wallet#1
rollback
```

Sau rollback, dữ liệu A ghi chưa commit không còn và transaction-held locks được giải phóng theo DBMS. B có thể đi tiếp.

### 28.3. Close EntityManager không nên là “cách commit”

`em.close()` không phải thao tác commit. Trên application-managed RESOURCE_LOCAL, phải commit/rollback theo transaction contract trước khi close. Không xây test “A close EM = commit” — nó nhầm transaction boundary với lifecycle của persistence context.

### 28.4. Test phải xác nhận final state

Sau các giao dịch, dùng EntityManager/session mới đọc:

```sql
SELECT id, balance, version
FROM wallets
ORDER BY id;
```

So sánh với expected state; đây là một phần của **kiểm chứng hành vi khóa ở mức nghiệp vụ**, không chỉ log chờ.

---

## 29. Dirty reads, non-repeatable reads và locks

Các hiện tượng isolation cần được tách khỏi “thấy lock”.

### 29.1. Dirty read

Một transaction đọc dữ liệu mà transaction khác chưa commit. Nhiều DBMS/isolation phổ biến ngăn dirty reads, ngay cả khi không dùng `PESSIMISTIC_READ`. Vì thế, việc B không đọc được giá trị chưa commit không chứng minh READ lock đã được áp dụng đúng.

### 29.2. Non-repeatable read

Một transaction đọc cùng row hai lần và thấy giá trị khác sau transaction khác commit ở giữa. Locking read có thể giúp ngăn writer sửa row đang được bảo vệ, nhưng behavior còn phụ thuộc isolation và cách provider lấy lock.

### 29.3. Phantom read

Truy vấn theo predicate hai lần thấy thêm/bớt rows. Row-level lock trên các rows hiện tại có thể không ngăn insert mới thỏa predicate.

### 29.4. Lost update

Hai transactions đọc cùng balance, tự tính kết quả rồi cùng UPDATE khiến kết quả của một transaction bị ghi đè. Pessimistic locking, optimistic versioning hoặc atomic SQL update đều có thể là công cụ phù hợp theo ngữ cảnh, nhưng phải kiểm chứng end-to-end logic.

### 29.5. Tạo test theo đúng hiện tượng

Đừng dùng cùng một scenario để kết luận cả dirty read, phantom, deadlock và lost update. Mỗi hiện tượng cần một trình tự SQL/giao dịch và expected observation riêng.

---

## 30. Lost update: test đúng nghiệp vụ

Giả sử wallet#1 có balance=100.

Hai giao dịch cùng thực hiện:

```text
Read 100
Compute 100 + 10 = 110
Write 110
```

Nếu không có cơ chế đồng bộ phù hợp, có nguy cơ kết quả cuối là 110 thay vì 120 (tùy mapping/version/isolation/UPDATE semantics).

### 30.1. Với @Version

Entity `Wallet` có `@Version`. Optimistic version check có thể phát hiện conflicting update và ném exception thay vì âm thầm lost update. Nếu mục tiêu là đo **pessimistic lock**, phải phân biệt lỗi version check với row-lock contention.

### 30.2. Với PESSIMISTIC_WRITE

A lock và đọc balance, B muốn lock cùng row thì chờ. Sau khi A commit, B nhận khóa và đọc state theo semantics của transaction/isolation. Trong một flow đúng, B tính toán từ giá trị cập nhật, không từ snapshot stale đã đọc trước lock.

### 30.3. Không đọc rồi mới khóa quá muộn

Sai pattern:

```java
Wallet w = em.find(Wallet.class, 1L);
// Application đọc w.balance và tính xong.
em.lock(w, LockModeType.PESSIMISTIC_WRITE);
// Ghi lại một giá trị dựa trên state có thể stale.
```

Nếu business computation đã dựa trên state trước lock, khóa sau đó có thể **quá muộn** để bảo đảm tính đúng mà không refresh/re-read. Nên lấy khóa trước khi đọc/tính trạng thái cần bảo vệ, hoặc thiết kế optimistic retry đúng.

---

## 31. em.lock, em.refresh và state đang managed

Ngoài `find(..., lockMode)` còn có:

```java
Wallet w = em.find(Wallet.class, 1L);

em.lock(w, LockModeType.PESSIMISTIC_WRITE);
```

và:

```java
em.refresh(w, LockModeType.PESSIMISTIC_WRITE);
```

### 31.1. em.lock không tự đồng nghĩa làm mới mọi field

`em.lock` yêu cầu lock trên managed entity; không nên dựa vào nó như một phép “SELECT lại toàn bộ state và ghi đè mọi field” trong tất cả provider. Nếu entity có state stale và nghiệp vụ cần dữ liệu mới từ DB, `refresh` có semantics khác và cần được cân nhắc.

### 31.2. Thứ tự có ý nghĩa

- `find` với lock từ đầu: tải và yêu cầu lock trong một flow.
- `lock` sau khi đã tải: lock managed entity hiện có.
- `refresh` với lock: làm mới state theo database và yêu cầu lock thích hợp.

Mỗi API có thể tạo SQL khác. Phải đo trên target DBMS, nhất là khi first-level cache chứa entity từ trước.

### 31.3. Không refresh vô ý mất pending changes

`refresh` có thể ghi đè trạng thái managed entity chưa flush bằng state từ DB. Nếu đã sửa wallet rồi refresh trước commit, có thể mất thay đổi mong muốn. Cần thiết kế unit of work rõ, không dùng refresh như “cách chữa stale” mọi trường hợp.

---

## 32. Flush ordering và những thay đổi trước lock

Khi transaction đã có pending writes rồi mới thực hiện khóa:

```java
em.getTransaction().begin();

Wallet other = em.find(Wallet.class, 2L);
other.credit(new BigDecimal("5.00"));

Wallet target = em.find(
    Wallet.class,
    1L,
    LockModeType.PESSIMISTIC_WRITE
);

em.getTransaction().commit();
```

Provider có thể flush pending changes theo quy tắc flush mode và query operations. Điều này ảnh hưởng:

- Thứ tự SQL UPDATE so với SELECT lock.
- Những locks được lấy trước/giữ lâu hơn.
- Nguy cơ deadlock khi hai workflows có thứ tự thao tác khác nhau.

### 32.1. Muốn test chỉ một khóa thì tách unit

Bài thử nền nên bắt đầu với transaction sạch, chỉ lock wallet#1. Sau khi đã xác nhận cơ chế cơ bản, mới thêm các pending writes/flush để phân tích deadlock và SQL ordering.

### 32.2. Bật SQL logging theo từng connection/transaction

Nếu chỉ bật log SQL nhưng không có connection/session ID hoặc thread correlation, khó biết câu nào thuộc A hay B. Nên thêm request/test IDs và, nếu có thể, DB session IDs, timestamp và transaction labels (không tiết lộ dữ liệu nhạy cảm).

---

## 33. Bảo vệ invariant nhiều hàng: khóa một row chưa đủ

Ví dụ chuyển tiền giữa hai Wallets:

```text
Wallet#1 -= 50
Wallet#2 += 50
```

Cần transaction atomic và quy tắc lock ordering. Chỉ khóa Wallet#1 chưa chắc bảo vệ Wallet#2 khỏi writer khác.

### 33.1. Khóa các rows cần thiết theo cùng thứ tự

Nếu chuyển từ A tới B, có thể xác định:

```text
firstId  = min(fromId, toId)
secondId = max(fromId, toId)
```

rồi lock first, lock second. Điều này giảm deadlock do thứ tự khóa đảo nhau.

### 33.2. SQL lock query nhiều IDs

Một truy vấn:

```jpql
SELECT w
FROM Wallet w
WHERE w.id IN :ids
ORDER BY w.id
```

với `setLockMode(PESSIMISTIC_WRITE)` thể hiện ý định sắp thứ tự, nhưng DB optimizer có thể lấy row locks theo access plan không trùng hoàn toàn ORDER BY presentation order. Nếu cần **kiểm soát lock acquisition order chặt chẽ**, thử lock từng ID theo thứ tự ở application hoặc đánh giá SQL/dialect cụ thể.

### 33.3. Invariant theo tổng nhóm có thể cần serialization mạnh hơn

Nếu nghiệp vụ “tổng balance của một nhóm không vượt ngưỡng” và có thể insert thêm Wallet vào nhóm, khóa các Wallet rows hiện tại có thể không chặn phantom. Cần transaction isolation/constraint/locking strategy phù hợp với invariant, không chỉ PESSIMISTIC_WRITE trên các entity đã query.

---

## 34. SKIP LOCKED và queue consumers

Một use case phổ biến:

```text
Nhiều workers lấy job PENDING chưa bị worker khác lấy.
```

Trên một số DBMS có `SKIP LOCKED`, mỗi worker có thể bỏ qua jobs đang bị khóa để tìm job khác.

### 34.1. Nó không phải “PESSIMISTIC_WRITE bình thường”

`SKIP LOCKED` có semantics cố ý bỏ qua những rows chưa thể lock ngay. Nếu API cần danh sách đầy đủ hoặc pagination đúng thứ tự toàn tập, skipping locked rows có thể khiến kết quả **không ổn định** và không đầy đủ.

### 34.2. Provider-specific extensions

Một số providers có hints/modes mở rộng hỗ trợ NOWAIT/SKIP LOCKED. Cần tra cứu phiên bản provider/dialect đang dùng, không khẳng định một cấu hình duy nhất portable qua mọi DBMS.

### 34.3. Queue cần state transition atomic

Ngay cả khi SKIP LOCKED chọn job, worker còn phải thay trạng thái claim/lease và commit transaction phù hợp. Không coi SELECT alone là “đã sở hữu job mãi mãi”.

### 34.4. Test contention nhiều workers

Test ba consumers đồng thời với cùng `PENDING` rows, quan sát:

- Có job nào bị nhận bởi hai consumers không?
- Rows bị khóa có được skip theo DB semantics không?
- Trạng thái job sau rollback?
- Worker crash có làm job không bao giờ được xử lý lại?
- Fairness/starvation?
- Số SQL và latency?

Đây là bài mở rộng; không nên dùng SKIP LOCKED để “làm biến mất” mọi lock contention trong transactional CRUD.

---

## 35. Giám sát database và bảo mật

Các views quan sát như `pg_stat_activity`, Performance Schema, SQL Server DMVs, Oracle `v$session` có thể hiển thị SQL text, usernames, session metadata và thông tin nhạy cảm.

### 35.1. Quyền truy cập

Dùng tài khoản test/DBA được cấp quyền phù hợp. Không mở rộng quyền production application user chỉ để cho phép một bài thực hành quan sát locks.

### 35.2. Không log giá trị nhạy cảm

Nếu dùng Hibernate bind-parameter logging, dữ liệu tài chính/token/PII có thể xuất hiện trong logs. Với bài lab, sử dụng dữ liệu giả và cấu hình log trong môi trường cô lập.

### 35.3. Tự động cleanup

Bài thử tạo deadlock hoặc giữ transaction phải có:

- Transaction timeout/DB lock timeout.
- Bounded thread wait.
- `finally` rollback/close.
- Connection pool shutdown.
- Không chạy trên bảng nghiệp vụ production.
- Người chịu trách nhiệm có thể hủy sessions còn kẹt.

### 35.4. Quan sát không được làm thay đổi dữ liệu ngoài bài thử

Observer nên chỉ chạy diagnostic SELECTs, tránh chạy DDL hoặc UPDATE trên bảng test trong lúc đo trừ khi đó là một scenario đã được thiết kế.

---

## 36. Trước khi ghi “khóa hoạt động đúng”: bằng chứng tối thiểu

Một test ghi “passed” cần các loại bằng chứng:

1. **Environment fingerprint:** DBMS/version, isolation, provider/driver, dialect.
2. **Setup:** schema, rows, indexes, initial values/version.
3. **Lệnh A và B:** SQL hoặc JPA code chính xác.
4. **Transaction/session IDs:** cho phép đối chiếu hai phía.
5. **Timeline:** A lock acquired, B attempt, B waiting, A commit/rollback, B result.
6. **DB-side observation:** blocker/wait state hoặc lock graph.
7. **Provider-side observation:** SQL phát ra, root exception nếu có.
8. **Final state:** balance/version đã commit hay bị rollback.
9. **Result classification:** success after wait, nowait failure, timeout, deadlock, no contention.
10. **Điều kiện loại trừ:** không phải pool starvation, network stall, first-level cache hay tự động commit quá sớm.

Một dòng `"B took 1200 ms"` không đủ làm báo cáo cho quyết định concurrency production.

---

## 37. Mẫu biên bản kiểm chứng

Dùng mẫu sau cho từng scenario:

```text
SCENARIO:
  W/W same primary key row

ENVIRONMENT:
  DBMS/version:
  Storage engine:
  JDBC driver/version:
  JPA provider/version:
  Dialect:
  Transaction model:
  Isolation:
  Connection pool size:
  Lock timeout settings:
  Schema/index:

INITIAL DATA:
  wallet#1 balance=100.00 version=0

TRANSACTION A:
  SQL/JPA action:
  Session/connection ID:
  Lock acquired at:
  Commit or rollback at:

TRANSACTION B:
  SQL/JPA action:
  Session/connection ID:
  Attempt started at:
  Wait confirmed at:
  Lock acquired or failed at:

DATABASE OBSERVATION:
  Blocking session:
  Waiting resource:
  Lock modes:
  Error code / SQLState (if any):

APPLICATION OBSERVATION:
  Provider SQL:
  Java exception:
  Transaction rollback-only/aborted:
  Connection-pool metrics:

FINAL DATA:
  wallet#1 balance:
  wallet#1 version:

RESULT:
  MATCHES EXPECTATION / DIFFERS / INCONCLUSIVE

NOTES:
  Reproduction steps:
  Confidence limitations:
  Follow-up:
```

### 37.1. “Inconclusive” là một kết quả hợp lệ

Nếu B timeout ở Java `Future.get` nhưng DB không báo wait và chưa biết B có lấy được connection hay chưa, kết luận phải là **chưa đủ bằng chứng**, không ép thành “DB khóa đúng” hoặc “DB khóa sai”.

---

## 38. Các trường hợp biên phải thử

### 38.1. Row không tồn tại

```java
Wallet missing = em.find(
    Wallet.class,
    9999L,
    LockModeType.PESSIMISTIC_WRITE
);
```

Nếu entity không tồn tại, `find` trả null theo semantics thông thường, nhưng DB query/locking behavior có thể khác, đặc biệt với range/gap locks trên một số DBMS. Không suy “đã khóa ID 9999” để ngăn mọi transaction khác INSERT ID đó chỉ vì bạn tìm không thấy row.

### 38.2. Same row, two concurrent writers

Đây là trường hợp nền để xác định blocking và lock release.

### 38.3. Two different rows

Dùng #1 và #2 để kiểm tra tính cục bộ của lock trong điều kiện query/index cụ thể.

### 38.4. Read-only SQL khi row đang bị khóa

Kiểm tra MVCC/row-version semantics riêng, không dùng nó làm negative test duy nhất.

### 38.5. Long-running transaction

Quan sát thời gian giữ khóa và tác động lên queue length/latency khi A bị trì hoãn lâu hơn bình thường.

### 38.6. Lock upgrade

A và B cùng READ lock, sau đó cùng muốn WRITE. Đây có thể tạo blocking/deadlock tùy lock manager; thiết kế scenario có barriers và timeout riêng.

### 38.7. Index thiếu hoặc query không sargable

Một query theo predicate không dùng index có thể quét/khóa phạm vi rộng hơn. So sánh có/không index trên DB test để hiểu chi phí/thời gian/lock footprint.

### 38.8. Fetch query có JOIN

Provider có thể lock root và/hoặc chọn SQL khác khi JOIN/FETCH; không áp giả thuyết “chỉ PK row” một cách máy móc.

### 38.9. Version conflict ngoài ORM

Một native SQL UPDATE không tăng `version` có thể làm sai cơ chế optimistic versioning của JPA. Đừng coi `@Version` là bảo đảm toàn bộ ứng dụng và external writers tự động tuân thủ contract.

### 38.10. Transaction thất bại khi commit

Lỗi tại `commit()` cũng cần ghi; successful lock acquisition và flush không đảm bảo transaction commit thành công.

---

## 39. Bài thực hành A — Chứng minh giao dịch B chờ khóa

1. Tạo bảng wallets và hai rows giả.
2. Dùng hai SQL clients hoặc hai JDBC connections độc lập.
3. A: BEGIN + lock wallet#1 bằng khóa write phù hợp DBMS.
4. B: BEGIN + thử lock wallet#1.
5. Trong lúc B chưa xong, dùng observer truy vấn wait/blocking sessions.
6. Ghi session IDs và blocker relationship.
7. A COMMIT.
8. Xác nhận B được giải quyết và kết thúc B bằng COMMIT/ROLLBACK.
9. Reset dữ liệu.
10. Lặp lại nhưng A ROLLBACK.
11. Đối chiếu final balance/version.

## 40. Bài thực hành B — Thử READ/READ và READ/WRITE

1. A dùng `PESSIMISTIC_READ`.
2. B dùng `PESSIMISTIC_READ`.
3. Ghi SQL, wait state và thời gian.
4. Reset.
5. A READ; B WRITE.
6. Ghi blocking relation.
7. Reset.
8. A WRITE; B READ.
9. So sánh với B SELECT thường không có locking clause.
10. Giải thích kết quả bằng DBMS/provider mapping thực tế.

## 41. Bài thực hành C — Đối chiếu JPA và native SQL

1. Thực hiện raw SQL `SELECT FOR UPDATE` (hoặc table hints của DBMS).
2. Ghi SQL và transaction timeline.
3. Chạy `em.find(Wallet.class,id,PESSIMISTIC_WRITE)`.
4. Bật provider SQL logging.
5. So sánh SQL/hints/lệnh phụ được phát.
6. Thử `em.lock` trên entity đã managed.
7. Thử `em.refresh` với lock mode trong transaction riêng.
8. Ghi sự khác biệt về state và SQL.
9. Không kết luận provider mapping chỉ từ một native SQL query.

## 42. Bài thực hành D — Lock timeout

1. A giữ WRITE lock wallet#1.
2. B dùng JPA hint `jakarta.persistence.lock.timeout=0`.
3. Ghi thời gian, exception và DB error code.
4. Lặp với hint 2_000.
5. Lặp với database session-level lock timeout.
6. Ghi cái nào được hỗ trợ và cái nào bị bỏ qua.
7. Tách `query.timeout`/connection pool timeout khỏi lock timeout.
8. Kiểm tra transaction state sau lỗi.
9. Rollback/close B.
10. Commit/rollback A và kiểm tra locks đã được giải phóng.

## 43. Bài thực hành E — Deadlock

1. A lock wallet#1.
2. B lock wallet#2.
3. Dùng barrier để cả hai sẵn sàng.
4. A cố lock #2; B cố lock #1.
5. Quan sát deadlock detector.
6. Ghi victim transaction và error SQLState/vendor code.
7. Xác nhận rollback cleanup.
8. Đổi hai workflows đều lock ID nhỏ trước.
9. So sánh số deadlocks qua nhiều lần chạy.
10. Không tạo deadlocks trên bảng production.

## 44. Bài thực hành F — PESSIMISTIC_FORCE_INCREMENT

1. Đặt wallet#1 version=0.
2. Mở EntityManager mới.
3. Begin transaction.
4. Gọi `find(...,PESSIMISTIC_FORCE_INCREMENT)`.
5. Không sửa balance.
6. Ghi SQL update/version behavior.
7. Commit.
8. Mở context mới, kiểm tra persisted version.
9. Reset.
10. Lặp và rollback.
11. Kiểm tra persisted version không đổi sau rollback của transaction.
12. So sánh với PESSIMISTIC_WRITE bình thường.

## 45. Bài thực hành G — Isolation và phantom

1. Truy vấn khóa wallet rows theo `balance >= 100`.
2. B thử INSERT wallet mới có balance 150.
3. Ghi behavior ở isolation mặc định.
4. Chuyển sang READ COMMITTED nếu DBMS hỗ trợ, lặp lại.
5. Thử REPEATABLE READ/SERIALIZABLE theo DBMS.
6. Theo dõi index/range locks.
7. Phân biệt row lock với range/next-key behavior.
8. Giải thích vì sao khóa rows hiện hữu không tự giải quyết mọi phantom.
9. Không đánh đồng “SQL không chặn INSERT” với “PESSIMISTIC_WRITE hoàn toàn không có tác dụng”.

## 46. Bài thực hành H — Connection pool

1. Chạy thử với pool size đủ hai connections.
2. Ghi DB sessions A/B và wait state.
3. Trong môi trường lab, thay pool size thành 1.
4. B thử bắt đầu transaction khi A đang giữ connection.
5. Quan sát B chờ **pool** thay vì row lock ở database.
6. Ghi connection acquisition timeout.
7. Trả pool về cấu hình cũ.
8. Giải thích tại sao đo thời gian ở application thôi không đủ.

## 47. Bài thực hành I — N+1 và fetch plan trong lock query

1. Tạo entity có association Customer và Lines.
2. Query root có PESSIMISTIC_WRITE và JOIN to-one.
3. Ghi SQL.
4. Thêm collection fetch join trên dataset test.
5. Xem SQL/follow-on locking hoặc provider warnings.
6. Tránh pagination trực tiếp trên collection fetch join.
7. So sánh lock footprint và số SQL statements.
8. Dùng query IDs rồi lock/fetch roots theo strategy phù hợp.
9. Không khẳng định mọi association được khóa chỉ vì fetch join.

## 48. Bài thực hành J — Hai phiên ghi vào cùng Wallet

1. Wallet balance=100.
2. Thực hiện hai flow tăng 10 không locking ở test riêng.
3. Quan sát version checking nếu entity có @Version.
4. Thử flow có `PESSIMISTIC_WRITE` trước khi đọc balance.
5. Dùng latch bảo đảm A lock trước B.
6. Cho A commit.
7. B tiếp tục và tăng từ trạng thái đã thấy sau lock.
8. Kiểm tra balance=120 nếu cả hai unit of work commit đúng.
9. Ghi các trường hợp version conflict/rollback và xử lý retry.
10. Không dựa vào việc “không xảy ra mất dữ liệu” một lần chạy để kết luận bảo đảm correctness.

## 49. Bài thực hành K — Đo hiệu năng và tài nguyên

1. Tạo dữ liệu nhiều wallets và indexes.
2. Chạy 10, 100 và 1.000 tasks cạnh tranh trên một nhóm row IDs cố định.
3. Giới hạn concurrency phù hợp để không gây outage.
4. Thu wait time, throughput, deadlocks và timeouts.
5. Thu connection-pool pending/active metrics.
6. Theo dõi DB wait events và CPU/I/O.
7. Thử giảm transaction duration.
8. Thử thứ tự khóa nhất quán.
9. So sánh isolation/index nếu phù hợp.
10. Ghi trade-off giữa correctness và throughput.

---

## 50. Checklist báo cáo cuối cho DBMS mục tiêu

| Câu hỏi | Bằng chứng cần có |
|---|---|
| Đúng DBMS/engine/version chưa? | Environment fingerprint |
| Đúng JPA provider/dialect chưa? | Startup config và SQL log |
| Hai EM có connections riêng không? | Session IDs/pool metrics |
| Có active transaction không? | Transaction boundaries/log |
| Lock SQL là gì? | Provider SQL capture |
| B thật sự chờ row lock? | DB blocking session/wait state |
| READ/READ có tương thích? | Thí nghiệm độc lập |
| READ/WRITE có chặn? | Thí nghiệm độc lập |
| WRITE/WRITE có chặn? | Thí nghiệm độc lập |
| SELECT thường có bị chặn? | MVCC/isolation observation |
| Lock timeout hint được hỗ trợ? | Đo thời gian + exception/SQL |
| Database timeout config là gì? | Session settings |
| Khi rollback có release? | DB wait state + final data |
| Khi commit có release? | DB wait state + final data |
| FORCE_INCREMENT có đổi version? | SQL + persisted version |
| Có lock scope EXTENDED? | Association/join-table scenario |
| Range query khóa vùng nào? | Index plan + data locks |
| Có deadlocks không? | DB deadlock report/vendor code |
| Có bị pool starvation không? | Pool active/pending |
| Có first-level cache ảnh hưởng? | Fresh EntityManager per test |
| Có second-level cache/replica? | Configuration/topology |
| Có flush trước lock ngoài ý muốn? | SQL ordering |
| Có JOIN/follow-on locking không? | Full provider SQL log |
| Có indexes phù hợp không? | EXPLAIN và lock footprint |
| Timeout có được cleanup không? | Rollback/close/session check |
| Có retry/idempotency policy không? | Service-level contract |
| Có thể tái lập kết quả không? | Steps + data + logs |
| Kết luận có nêu giới hạn phạm vi? | DBMS/version/isolation |

---

## 51. Những hiểu lầm phổ biến

### 51.1. “PESSIMISTIC_WRITE luôn sinh SELECT FOR UPDATE”

Không trên mọi DBMS. SQL Server có locking hints; provider có thể dùng follow-on locking hoặc chiến lược vendor-specific. Cần đọc SQL thật.

### 51.2. “SELECT thường không bị block nghĩa là không có row lock”

Không đúng với nhiều hệ quản trị MVCC. SELECT thường có thể đọc committed version trong khi locking writer khác đang giữ khóa.

### 51.3. “Khóa hàng trong PostgreSQL thì pg_locks luôn hiển thị primary key hàng đó”

Không. Waits có thể biểu hiện qua transaction ID và các lock entries khác; cần dùng nhiều diagnostic views.

### 51.4. “Lock timeout ở JPA hint luôn chính xác 2 giây”

Không portable. Provider/dialect/DBMS có thể hỗ trợ khác nhau hoặc bỏ qua hint; đo trên stack thực.

### 51.5. “Thread Future timeout là database lock timeout”

Không. `Future.get(timeout)` chỉ giới hạn thời gian Java caller chờ result. Nó không chứng minh hay cấu hình row lock wait ở DB.

### 51.6. “Khóa READ luôn cho phép READ khác cùng lấy khóa”

Shared-lock strategy là một khả năng, không phải hình thức SQL được mọi provider/DBMS bắt buộc sử dụng.

### 51.7. “PESSIMISTIC_WRITE khóa toàn bộ graph của entity”

Không. Phạm vi phụ thuộc root, mapping, hints, provider/dialect và SQL thật.

### 51.8. “FOR UPDATE theo primary key chặn mọi INSERT vào bảng”

Không. Đó không phải mục tiêu thông thường của row lock; một range/gap/serialization scenario có thể khác.

### 51.9. “Đã flush thì khóa được giải phóng”

Không. Flush chưa commit; transaction-held locks thường vẫn còn đến transaction end.

### 51.10. “Close EntityManager là commit”

Không. Commit/rollback và lifecycle EntityManager là các khái niệm khác.

### 51.11. “Deadlock và lock timeout cùng một lỗi”

Không. Deadlock có chu trình chờ; timeout có thể là một chiều chờ quá hạn. Root cause và retry policy khác nhau.

### 51.12. “PESSIMISTIC_FORCE_INCREMENT chỉ khóa, không sửa gì”

Với versioned entity, force increment yêu cầu tăng version theo semantics của lock mode; phải kiểm tra persisted version.

### 51.13. “Một thử nghiệm với H2 đủ thay PostgreSQL/MySQL production”

Không. H2 có locking và isolation behavior khác; test concurrency phải chạy trên DBMS mục tiêu.

### 51.14. “Hai EntityManagers luôn tương ứng hai connections đồng thời”

Không nhất thiết nếu pool chỉ cho một connection hoặc transaction chưa lấy connection. Phải xác nhận sessions thực tế.

### 51.15. “Thread.sleep đủ chứng minh lock wait”

Không. Sleep không đồng bộ mốc lấy lock và không xác định wait nguyên nhân từ đâu. Dùng latches/barriers và DB observation.

### 51.16. “Index chỉ ảnh hưởng performance, không ảnh hưởng locks”

Với những DBMS/isolations có index-range/next-key locking hoặc lock escalation, index/query plan còn có thể ảnh hưởng phạm vi khóa quan sát được.

### 51.17. “Rollback của A sẽ luôn giúp B nhận khóa và mọi thứ thành công”

B có thể đã timeout, transaction đã aborted, hoặc gặp lỗi khác. Phải xử lý từng outcome và transaction state.

### 51.18. “Có @Version thì khỏi cần kiểm chứng transaction locks”

`@Version` cung cấp optimistic conflict detection; không tự biến một flow thành row-level pessimistic locking. Hai chiến lược giải quyết các tình huống khác nhau và có thể kết hợp.

### 51.19. “Nhận được lock là bảo đảm commit thành công”

Không. Commit có thể lỗi do constraint, deadlock, network/DB failure hoặc transaction khác. Chỉ ghi thành công nghiệp vụ sau khi transaction outcome được xác nhận phù hợp.

### 51.20. “Một lần chạy không deadlock là thiết kế đã hết deadlock”

Deadlock có thể phụ thuộc interleaving, dữ liệu, indexes, load và nhiều SQL statements. Cần nhiều scenario, monitoring và retry policy.

---

## 52. Câu hỏi ôn tập

1. Vì sao không nên kết luận JPA PESSIMISTIC_WRITE sinh cùng SQL trên mọi DBMS?
2. Những thông tin môi trường nào phải được ghi lại trước test?
3. Vì sao cần hai EntityManager/transactions độc lập?
4. Connection pool size 1 có thể làm sai phép thử như thế nào?
5. Làm thế nào xác minh B thực sự chờ row lock trong database?
6. Vì sao SELECT thường có thể không chờ FOR UPDATE trên MVCC DB?
7. PESSIMISTIC_READ và PESSIMISTIC_WRITE khác nhau ở ý định chuẩn nào?
8. Provider có được dùng khóa mạnh hơn cho PESSIMISTIC_READ không?
9. PESSIMISTIC_FORCE_INCREMENT khác PESSIMISTIC_WRITE như thế nào?
10. Entity cần mapping nào để kiểm chứng force increment?
11. Có phải `wallet.getVersion()` ngay sau find đã luôn là version cuối sau commit?
12. Vì sao nên dùng EntityManager mới khi xác nhận persisted version?
13. Với PostgreSQL, `pg_blocking_pids` cho biết gì?
14. Vì sao `pg_locks` không tự là danh sách toàn bộ row primary keys bị khóa?
15. Với MySQL 8, `data_lock_waits` hỗ trợ điều tra gì?
16. Vì sao InnoDB autocommit ảnh hưởng giữ row lock?
17. Next-key/gap locks có thể phát sinh ở loại truy vấn nào?
18. Với SQL Server, vì sao cần xem table hints thay vì `FOR UPDATE`?
19. `READ_COMMITTED_SNAPSHOT` có thể ảnh hưởng một SELECT thường ra sao?
20. Oracle `FOR UPDATE NOWAIT` khác `WAIT n` ở ý nghĩa nào?
21. Vì sao raw SQL native test không tự chứng minh mapping của JPA provider?
22. Khi query có JOIN/DISTINCT, provider có thể phát thêm SQL lock như thế nào?
23. `jakarta.persistence.lock.timeout` có phải luôn được hỗ trợ chính xác không?
24. Lock timeout khác query timeout và pool timeout ở đâu?
25. `LockTimeoutException` khác `PessimisticLockException` về transaction semantics thế nào?
26. Sau PostgreSQL statement error trong transaction, cần lưu ý gì trước câu SQL tiếp?
27. Vì sao `Future.get(300ms)` bị timeout không phải bằng chứng row lock?
28. Vì sao không thể dùng cùng EntityManager ở hai threads?
29. Commit và rollback ảnh hưởng transaction-held locks ra sao?
30. Flush có phải commit không?
31. em.lock và em.refresh khác nhau thế nào khi entity đã managed?
32. Vì sao khóa sau khi tính giá trị từ state cũ có thể quá muộn?
33. Deadlock cycle với hai Wallets được tạo ra như thế nào?
34. Thứ tự khóa nhất quán giúp giảm deadlock ra sao?
35. Vì sao deadlock retry nên bắt đầu transaction mới?
36. Khóa một số rows thỏa predicate có tự ngăn phantom INSERT không?
37. Isolation level và indexes ảnh hưởng phạm vi khóa theo cách nào?
38. `PessimisticLockScope.EXTENDED` có khóa toàn bộ graph vô hạn không?
39. SKIP LOCKED có thích hợp để trả một danh sách đầy đủ cho người dùng không?
40. Vì sao không chạy thử nghiệm giữ locks lâu trên production?
41. Những thành phần nào cần log trong biên bản kiểm chứng?
42. Khi nào kết luận test nên là INCONCLUSIVE?
43. Một lần chạy thành công có đủ để xác nhận concurrency safety không?
44. Vì sao một index sai có thể làm lock wait tăng?
45. Những số liệu gì giúp đánh giá chi phí của khóa bi quan?
46. Vì sao final balance/version cần được kiểm tra sau cả A/B commits?
47. Nếu B nhìn thấy dữ liệu cũ sau khi A commit, cần kiểm tra những gì?
48. Khi nào @Version có thể che một tình huống lost update khỏi thí nghiệm lock?
49. Vì sao hai transaction cùng truy vấn row khác nhau vẫn có thể cạnh tranh ở một số DBMS/workloads?
50. Kết luận “đã kiểm chứng” nên được giới hạn bằng cấu hình môi trường nào?

---

## 53. Bảng ghi nhớ cuối bài

| Cần chứng minh | Thử nghiệm và quan sát |
|---|---|
| PESSIMISTIC_WRITE thật sự lock row | A giữ WRITE; B WRITE/UPDATE cùng row; DB xác nhận blocker |
| PESSIMISTIC_READ tương thích ra sao | A READ; B READ/WRITE; đo wait |
| SQL provider phát | SQL log gắn với transaction/session ID |
| Timeout JPA có hiệu lực không | Hint 0/giá trị dương + DB/session observation |
| Deadlock được phát hiện | A #1→#2, B #2→#1; DB error/trace |
| Force increment hoạt động | Entity @Version; commit; đọc persisted version mới |
| Rollback giải phóng khóa | A rollback; B tiếp tục; final data đúng |
| Flush chưa commit | A flush rồi giữ transaction; B vẫn chờ |
| Range lock có lan rộng không | Query theo predicate/index + insert cạnh tranh |
| SELECT thường có bị chặn không | A WRITE; B nonlocking SELECT; giải thích MVCC |
| Lock scope có ảnh hưởng không | NORMAL/EXTENDED với join/collection tables |
| Có phải pool contention không | Pool metrics + DB session IDs |
| Có N+1/follow-on locking không | Ghi toàn bộ SQL statements |
| Có cần retry không | Timeout/deadlock classification + idempotency |
| Có thể dùng kết quả ở production không | Cùng DBMS/version/driver/provider/isolation/index |
| Chất lượng bằng chứng | Timeline + DB wait graph + SQL + exceptions + final state |

### Sơ đồ kết luận

```text
     BẮT ĐẦU: JPA PESSIMISTIC LOCK
                     |
                     v
      Chọn DBMS + provider + isolation
                     |
                     v
         Dữ liệu + index kiểm soát
                     |
                     v
        A: BEGIN + ACQUIRE LOCK
                     |
                     v
         Giữ A mở bằng barrier
                     |
                     +-------------------+
                     |                   |
                     v                   v
          B: COMPETING OPERATION    OBSERVER:
                     |              DB wait / blockers
                     v                   |
          wait / success / error         |
                     +-------------------+
                     |
                     v
          A COMMIT hoặc ROLLBACK
                     |
                     v
          B tiếp tục / thất bại
                     |
                     v
           Đọc final persisted state
                     |
                     v
          Ghi SQL, error, timeline
                     |
                     v
        KẾT LUẬN TRONG PHẠM VI STACK
```

**Nguyên tắc cuối bài:** khóa bi quan trong JPA phải được hiểu ở cả hai tầng. `LockModeType` nói lên **yêu cầu của ứng dụng đối với persistence provider**, còn **DBMS + SQL dialect + isolation + indexes + transaction lifecycle** quyết định cách khóa thực sự được thực thi. Một phép thử có giá trị phải dùng hai giao dịch/connection độc lập, giữ khóa đủ lâu để quan sát, dùng công cụ database xác định blocker/waiter, phân biệt timeout với deadlock và pool starvation, rồi kiểm tra trạng thái dữ liệu sau commit/rollback. Chỉ khi đó mới có cơ sở lựa chọn lock mode, timeout, thứ tự khóa và retry policy cho **hệ quản trị mục tiêu** thay vì dựa trên phỏng đoán hoặc một hành vi tình cờ của môi trường khác.

