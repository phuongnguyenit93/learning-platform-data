# Giới hạn của giao dịch trong một kết nối và hướng học chuyên sâu

Một giao dịch SQL thường được giới thiệu bằng ba lệnh:

```sql
BEGIN;
-- Những câu lệnh SQL liên quan.
COMMIT;
-- Hoặc ROLLBACK khi không thể xác nhận.
```

Nhưng khi một ứng dụng chuyển tiền, tạo đơn hàng hoặc đồng bộ dữ liệu, câu hỏi khó nhất đôi khi không phải **viết BEGIN hay COMMIT ở đâu**, mà là: **câu SQL nào thật sự thuộc cùng giao dịch, kết nối nào thực hiện chúng, và điều gì nằm ngoài khả năng ROLLBACK của database?**

Ví dụ, ứng dụng trừ tiền người gửi bằng kết nối A rồi cộng tiền người nhận bằng kết nối B. Nếu B đã COMMIT nhưng A ROLLBACK, hệ thống có thể cộng tiền mà không trừ tiền. Một `ROLLBACK` trên A **không thể hủy một COMMIT độc lập của B**. Tương tự, nếu ứng dụng gửi email, gọi cổng thanh toán hay ghi file giữa `BEGIN` và `COMMIT`, những tác dụng bên ngoài ấy **không tự tham gia** giao dịch SQL.

Bài học thuộc **Database SQL → Giao dịch SQL**, tập trung vào:

1. Ranh giới một **local transaction** theo kết nối/phiên và transaction manager.
2. Tương tác giữa `BEGIN`, `COMMIT`, `ROLLBACK`, autocommit, isolation và connection pool.
3. Giới hạn khi dùng nhiều kết nối, nhiều database và các dịch vụ bên ngoài.
4. Các mô hình nâng cao: **idempotency, outbox/inbox, XA/two-phase commit, saga, retry, đối soát**.
5. **Lộ trình học chuyên sâu** kèm thực hành PostgreSQL, JDBC và tình huống lỗi thực tế.

Ví dụ chính dùng **PostgreSQL**. Chúng ta sẽ tạo dữ liệu trong một database thực hành riêng để **hai phiên kết nối thật** có thể quan sát cùng bảng. Cú pháp/hành vi ở SQL Server, MySQL, SQLite và Oracle được giải thích riêng khi có khác biệt.

> **Nguyên tắc:** transaction chỉ bao phủ những tài nguyên và thao tác thật sự tham gia phạm vi quản lý của transaction đó. Nó không tự phát hiện mọi lỗi nghiệp vụ, không tự lan qua connection khác và không tự hoàn tác side effect ngoài SQL.

## 1. Bốn khái niệm không được trộn lẫn

| Khái niệm | Ví dụ | Vai trò |
| --- | --- | --- |
| **Statement** | `UPDATE accounts SET ...` | Một câu SQL, có thể chạy độc lập hoặc bên trong một transaction |
| **Connection/session** | Cửa sổ `psql`, đối tượng `Connection` trong JDBC | Ngữ cảnh thực thi và giữ trạng thái local transaction |
| **Transaction manager / DBMS** | PostgreSQL, InnoDB, JTA manager | Điều phối xác nhận/hủy, khóa, cô lập và khôi phục cho những tài nguyên được quản lý |
| **Nghiệp vụ** | Chuyển tiền, đặt hàng, gửi thông báo | Có thể đi qua nhiều statement, connection, database và dịch vụ |

Một HTTP request không tự tương đương với một transaction:

```text
HTTP POST /transfer
        |
        +--- Repository debit ---> Connection A ---> Database
        |
        +--- Repository credit --> Connection B ---> Database
        |
        +--- Payment API -------> HTTP service khác
        |
        +--- Notify ------------> Message broker
```

Nếu thiếu một thiết kế phối hợp tường minh, các bước trên có **những ranh giới xác nhận riêng**.

### 1.1. Một kết nối có thể sửa nhiều bảng

Trong cùng một PostgreSQL database:

```sql
BEGIN;

UPDATE sales.orders
SET status = 'PAID'
WHERE order_id = 42;

INSERT INTO audit.order_events (order_id, event_type)
VALUES (42, 'PAID');

COMMIT;
```

Đoạn trên là **mẫu khái niệm**, giả định hai bảng tồn tại. Hai schema `sales` và `audit` không tự tạo hai transaction. Nếu cùng connection và cùng DBMS quản lý, các thay đổi có thể thuộc **một local transaction**.

### 1.2. Hai kết nối tới cùng database vẫn độc lập

```text
Connection A                      Connection B
------------                      ------------
BEGIN                             BEGIN
UPDATE account A                  UPDATE account B
ROLLBACK                          COMMIT

Thay đổi A bị hủy.                Thay đổi B được lưu.
```

Cùng tên database không đồng nghĩa hai kết nối dùng chung trạng thái transaction.

### 1.3. Một transaction có thể ngắn hơn hoặc dài hơn một statement

Một câu `UPDATE` chạy trong client bật autocommit thường được xử lý và commit như một transaction ngầm. Ngược lại, transaction tường minh có thể chứa nhiều câu `SELECT`, `UPDATE`, `INSERT`, `DELETE` và những DDL được DBMS cho phép.

Trong thực tế, một request có thể vô tình tạo **nhiều local transaction** nếu các repository lấy connection khác nhau hoặc các lời gọi đã tự commit.

## 2. Ôn lại BEGIN, START TRANSACTION, COMMIT, ROLLBACK

Trong PostgreSQL:

```sql
BEGIN;
UPDATE accounts SET ... WHERE ...;
COMMIT;
```

hoặc:

```sql
START TRANSACTION;
UPDATE accounts SET ... WHERE ...;
ROLLBACK;
```

Ý nghĩa:

- **`BEGIN` / `START TRANSACTION`:** bắt đầu một transaction tường minh trong ngữ cảnh SQL của những hệ hỗ trợ.
- **`COMMIT`:** xác nhận và kết thúc transaction nếu thành công.
- **`ROLLBACK`:** hủy những thay đổi chưa commit thuộc transaction và kết thúc nó.
- **`SAVEPOINT` / `ROLLBACK TO SAVEPOINT`:** cho phép hoàn tác một đoạn trong cùng transaction, không tạo một commit độc lập.

### 2.1. Autocommit là một cấu hình quan trọng

Nếu ứng dụng gửi hai câu SQL bằng chế độ autocommit:

```sql
UPDATE accounts SET balance = balance - 100 WHERE account_id = 1;
UPDATE accounts SET balance = balance + 100 WHERE account_id = 2;
```

mỗi câu có thể được commit riêng. Nếu câu thứ hai lỗi, câu thứ nhất **đã commit** không thể được ROLLBACK bằng lệnh gửi sau đó.

Autocommit thuộc cách hoạt động của DBMS/client/driver:

- `psql` thường commit từng statement ngoài transaction block.
- JDBC `Connection` thông thường bắt đầu với `autoCommit = true`.
- MySQL có cấu hình `autocommit` theo session.
- SQL Server có implicit autocommit mode và chế độ `IMPLICIT_TRANSACTIONS`.
- Framework có thể mở transaction qua API, dù mã nguồn không gửi câu SQL `BEGIN` tường minh.

Hãy kiểm tra **transaction boundary thực tế**, không phán đoán từ tên phương thức hoặc vị trí dòng code.

### 2.2. ROLLBACK không quay ngược thời gian qua COMMIT

```text
BEGIN -> UPDATE -> COMMIT -> transaction kết thúc.
BEGIN -> UPDATE -> ROLLBACK -> thay đổi của transaction này bị hủy.
```

Nếu COMMIT đã xác nhận, muốn thay đổi trạng thái sau đó phải có **một transaction mới** với thao tác điều chỉnh/bù trừ phù hợp. Với dữ liệu tài chính, điều đó thường đòi hỏi bút toán mới có audit, không sửa lịch sử tùy tiện.

## 3. Chuẩn bị một database thực hành cho hai kết nối PostgreSQL

**Không dùng TEMP TABLE cho thí nghiệm hai session.** Bảng tạm PostgreSQL thuộc session tạo nó và không hiện ra như bảng chung cho session khác. Để quan sát hai kết nối đồng thời, dùng bảng thật trong **một database học tập riêng**, không sử dụng database production.

Chạy trong một phiên có quyền tạo schema:

```sql
CREATE SCHEMA tx_scope_lab;

CREATE TABLE tx_scope_lab.accounts (
    tenant_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    owner_name TEXT NOT NULL,
    balance NUMERIC(14, 2) NOT NULL CHECK (balance >= 0),
    PRIMARY KEY (tenant_id, account_id)
);

CREATE TABLE tx_scope_lab.transfers (
    transfer_ref TEXT PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    from_account_id INTEGER NOT NULL,
    to_account_id INTEGER NOT NULL,
    amount NUMERIC(14, 2) NOT NULL CHECK (amount > 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (from_account_id <> to_account_id),
    FOREIGN KEY (tenant_id, from_account_id)
        REFERENCES tx_scope_lab.accounts (tenant_id, account_id),
    FOREIGN KEY (tenant_id, to_account_id)
        REFERENCES tx_scope_lab.accounts (tenant_id, account_id)
);

CREATE TABLE tx_scope_lab.outbox (
    outbox_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_key TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    sent_at TIMESTAMPTZ
);

INSERT INTO tx_scope_lab.accounts (
    tenant_id, account_id, owner_name, balance
) VALUES
    (10, 101, 'An',   1000.00),
    (10, 102, 'Bình',  500.00),
    (10, 103, 'Chi',   200.00),
    (20, 101, 'An thuộc tenant 20', 900.00);
```

Kiểm tra:

```sql
SELECT tenant_id, account_id, owner_name, balance
FROM tx_scope_lab.accounts
ORDER BY tenant_id, account_id;
```

| Tenant | Tài khoản | Chủ | Số dư |
| ---: | ---: | --- | ---: |
| 10 | 101 | An | 1000.00 |
| 10 | 102 | Bình | 500.00 |
| 10 | 103 | Chi | 200.00 |
| 20 | 101 | An thuộc tenant 20 | 900.00 |

Tổng số dư tenant 10 là **1700.00**. Hai tenant cùng có account_id 101: một transaction không tự bảo vệ nghiệp vụ nếu câu UPDATE quên `tenant_id`.

**Lưu ý:** nếu schema `tx_scope_lab` đã tồn tại, không tự thay hay xóa schema ấy; sử dụng một database/schema thực hành riêng. Những thí nghiệm có COMMIT sẽ thay đổi dữ liệu lab; cần đặt lại dữ liệu giữa các thí nghiệm khi muốn so sánh từ cùng mốc.

## 4. Thí nghiệm một connection chưa COMMIT, connection kia đọc gì?

Mở **Session A** và **Session B** trong hai cửa sổ `psql` độc lập, kết nối cùng PostgreSQL database. Dùng READ COMMITTED cho ví dụ.

**Session A:**

```sql
BEGIN;

UPDATE tx_scope_lab.accounts
SET balance = balance - 100
WHERE tenant_id = 10 AND account_id = 101;

SELECT balance
FROM tx_scope_lab.accounts
WHERE tenant_id = 10 AND account_id = 101;
-- Session A thấy 900.00.
```

Giữ transaction A đang mở. **Session B**:

```sql
SELECT balance
FROM tx_scope_lab.accounts
WHERE tenant_id = 10 AND account_id = 101;
-- Session B thấy 1000.00.
```

PostgreSQL không cho B đọc thay đổi chưa commit của A trong READ COMMITTED. A lại đọc được **chính những thay đổi chưa commit của mình**.

Trở lại A:

```sql
ROLLBACK;
```

B đọc lại và vẫn thấy 1000. Nếu A `COMMIT` thay vì ROLLBACK, một SELECT **mới** của B ở READ COMMITTED sau commit có thể thấy 900. Trong một transaction REPEATABLE READ ở B với snapshot trước đó, B có thể tiếp tục thấy snapshot cũ cho tới khi transaction B kết thúc.

### 4.1. Vì sao cần hai session thật?

Không thể chứng minh ranh giới giữa hai connection bằng cách dùng hai tab editor nhưng chúng thực chất chia sẻ cùng một backend connection. Trong PostgreSQL có thể quan sát:

```sql
SELECT pg_backend_pid() AS backend_pid;
```

Hai kết nối độc lập thường có PID backend khác nhau. Tuy nhiên, PID **không phải transaction ID nghiệp vụ**; một pool có thể tái sử dụng cùng backend cho nhiều transaction ở các thời điểm khác nhau.

## 5. Thí nghiệm hai connection: ROLLBACK A không hủy COMMIT B

Giả sử account 101 = 1000 và account 102 = 500 trước thí nghiệm.

**Session A**:

```sql
BEGIN;

UPDATE tx_scope_lab.accounts
SET balance = balance - 20
WHERE tenant_id = 10 AND account_id = 101;

-- Chưa commit.
```

**Session B**:

```sql
BEGIN;

UPDATE tx_scope_lab.accounts
SET balance = balance + 20
WHERE tenant_id = 10 AND account_id = 102;

COMMIT;
```

Sau đó **Session A**:

```sql
ROLLBACK;
```

Kết quả:

| Tài khoản | Ban đầu | Sau B COMMIT và A ROLLBACK |
| --- | ---: | ---: |
| 101 | 1000 | **1000** |
| 102 | 500 | **520** |
| Tổng hai tài khoản | 1500 | **1520** |

Đây là một giao dịch chuyển tiền **sai nghiệp vụ** dù hai local transactions đã tuân theo quy tắc COMMIT/ROLLBACK của chúng. A không thể hủy thay đổi B đã commit, bởi B là một transaction khác.

Nếu thực hành, có thể đặt lại account 102 về 500 **trong database lab** bằng một transaction mới:

```sql
BEGIN;
UPDATE tx_scope_lab.accounts
SET balance = 500
WHERE tenant_id = 10 AND account_id = 102;
COMMIT;
```

Đây là reset dữ liệu mẫu, **không** phải hướng dẫn “undo” giao dịch tài chính production.

### 5.1. Nếu cả hai cùng UPDATE một hàng?

Session B có thể phải chờ khóa ghi mà A đang giữ. Đó là **kiểm soát concurrency**, không có nghĩa các connection đã hợp thành cùng transaction. Một connection có thể bị block khi UPDATE, nhưng ROLLBACK của connection khác vẫn chỉ hủy transaction của connection ấy.

## 6. Tính nguyên tử không tự bảo đảm nghiệp vụ đúng

Một transaction chuyển tiền cần làm nhiều hơn:

```sql
BEGIN;

UPDATE tx_scope_lab.accounts
SET balance = balance - 150
WHERE tenant_id = 10
  AND account_id = 101
  AND balance >= 150;

UPDATE tx_scope_lab.accounts
SET balance = balance + 150
WHERE tenant_id = 10 AND account_id = 102;

COMMIT;
```

Nếu UPDATE đầu tác động **0 hàng** vì không đủ tiền hoặc account không tồn tại, SQL không nhất thiết báo exception. Nếu ứng dụng vẫn chạy UPDATE hai rồi COMMIT, tiền có thể được cộng mà không bị trừ.

### 6.1. Phải kiểm tra affected rows

Một thao tác chuyển tiền có thể yêu cầu:

- Account nguồn và đích tồn tại, đúng tenant và loại tiền.
- Amount dương và trong giới hạn.
- Debit tác động **đúng một hàng**.
- Credit tác động **đúng một hàng**.
- Ledger được ghi cùng transaction.
- Mã giao dịch chống replay không trùng hoặc được xử lý theo quy tắc rõ.

Trong PostgreSQL PL/pgSQL, có thể dùng `GET DIAGNOSTICS ... ROW_COUNT`. Ứng dụng Java/JDBC có `executeUpdate()` trả số hàng.

### 6.2. Ví dụ PostgreSQL có kiểm tra và rollback ở cuối

```sql
BEGIN;

DO $$
DECLARE
    v_rows INTEGER;
BEGIN
    UPDATE tx_scope_lab.accounts
    SET balance = balance - 25
    WHERE tenant_id = 10
      AND account_id = 101
      AND balance >= 25;

    GET DIAGNOSTICS v_rows = ROW_COUNT;
    IF v_rows <> 1 THEN
        RAISE EXCEPTION 'Debit: expected exactly one row';
    END IF;

    UPDATE tx_scope_lab.accounts
    SET balance = balance + 25
    WHERE tenant_id = 10
      AND account_id = 102;

    GET DIAGNOSTICS v_rows = ROW_COUNT;
    IF v_rows <> 1 THEN
        RAISE EXCEPTION 'Credit: expected exactly one row';
    END IF;

    INSERT INTO tx_scope_lab.transfers (
        transfer_ref, tenant_id, from_account_id, to_account_id, amount
    )
    VALUES ('demo-sandbox-001', 10, 101, 102, 25.00);
END;
$$;

-- Có thể SELECT quan sát thay đổi trong transaction.
ROLLBACK;
```

Ở đây ROLLBACK cuối cùng giữ nguyên dữ liệu demo khi thành công. Nếu câu DO báo lỗi, PostgreSQL có thể chuyển transaction sang trạng thái aborted; cần `ROLLBACK` trước khi tiếp tục các lệnh khác. Đây vẫn là ví dụ giảng dạy: chuyển tiền thật còn cần idempotency/ledger toàn diện, permission, concurrency và các kiểm tra khác.

## 7. Cùng connection không phải lúc nào cũng cùng một transaction

Connection pool có thể tái sử dụng một backend:

```text
Request 1 -> mượn Connection X -> BEGIN ... COMMIT -> trả pool
Request 2 -> mượn Connection X -> BEGIN ... ROLLBACK -> trả pool
```

Cùng một physical connection **ở hai thời điểm khác nhau** không đồng nghĩa chúng có chung một transaction. Local transaction có điểm **bắt đầu và kết thúc**, độc lập với tuổi thọ của TCP connection.

### 7.1. Connection handle logic và connection vật lý

Trong pool, lời gọi `getConnection()` có thể trả handle logic; `close()` thường trả handle đó về pool. Connection vật lý có thể tiếp tục tồn tại. Điều ứng dụng cần bảo đảm là **mọi câu SQL cần commit cùng nhau phải tham gia cùng transaction context**.

### 7.2. Không trả connection còn transaction mở

Nếu một hàm mở transaction rồi bị exception, không ROLLBACK trước khi trả connection, hệ thống có thể giữ lock/snapshot/trạng thái lỗi. Một số pool có bước rollback/reset khi trả connection, nhưng không được phụ thuộc mù quáng vào đó thay cho cleanup đúng.

### 7.3. Không tự ghép transaction bằng mã request

Việc hai statement có cùng `request_id` trong log không biến chúng thành cùng transaction. Request ID phục vụ **quan sát và truy vết**; transaction boundary phải do DBMS/driver/manager thực hiện.

## 8. Java/JDBC: transaction thực sự gắn với Connection

Một ví dụ giao dịch qua JDBC:

```java
try (Connection conn = dataSource.getConnection()) {
    boolean oldAutoCommit = conn.getAutoCommit();
    try {
        conn.setAutoCommit(false);

        try (PreparedStatement debit = conn.prepareStatement(
                 "UPDATE accounts SET balance = balance - ? " +
                 "WHERE tenant_id = ? AND account_id = ? AND balance >= ?");
             PreparedStatement credit = conn.prepareStatement(
                 "UPDATE accounts SET balance = balance + ? " +
                 "WHERE tenant_id = ? AND account_id = ?")) {

            BigDecimal amount = new BigDecimal("100.00");

            debit.setBigDecimal(1, amount);
            debit.setInt(2, 10);
            debit.setInt(3, 101);
            debit.setBigDecimal(4, amount);
            if (debit.executeUpdate() != 1) {
                throw new SQLException("Debit failed");
            }

            credit.setBigDecimal(1, amount);
            credit.setInt(2, 10);
            credit.setInt(3, 102);
            if (credit.executeUpdate() != 1) {
                throw new SQLException("Credit failed");
            }
        }

        // Còn phải ghi ledger/idempotency/outbox cùng conn
        // trong hệ thống thật, rồi mới commit.
        conn.commit();
    } catch (Exception ex) {
        try {
            conn.rollback();
        } catch (SQLException rollbackError) {
            ex.addSuppressed(rollbackError);
        }
        throw ex;
    } finally {
        conn.setAutoCommit(oldAutoCommit);
    }
}
```

Đây là mã minh họa kiến trúc, giả định có bảng `accounts` tương ứng trong ứng dụng. Nó cho thấy:

1. Debit và credit dùng **cùng conn**.
2. Autocommit được tắt trước các UPDATE.
3. Các giá trị được gửi qua `PreparedStatement`.
4. Mỗi bước kiểm tra **số hàng ảnh hưởng**.
5. Chỉ COMMIT khi mọi bước bắt buộc thành công.
6. Khi lỗi, ROLLBACK trên chính conn và cleanup connection.

**Lưu ý:** đổi `autoCommit` từ false trở về true khi transaction còn hoạt động có thể kích hoạt COMMIT theo hợp đồng JDBC. Vì vậy phải bảo đảm giao dịch được kết thúc đúng trước bước khôi phục trạng thái; nếu conn bị lỗi nặng/không chắc kết quả commit, không cố đưa lại vào pool như bình thường.

### 8.1. Một lỗi JDBC dễ mắc

```java
Connection a = dataSource.getConnection();
Connection b = dataSource.getConnection();

a.setAutoCommit(false);
b.setAutoCommit(false);

// Debit dùng a.
// Credit dùng b.
// b.commit();
// a.rollback();
```

COMMIT của b vẫn tồn tại sau ROLLBACK của a. Cùng `DataSource` không đồng nghĩa cùng transaction.

### 8.2. Kết quả COMMIT khi mất kết nối

Nếu client gửi `conn.commit()` rồi mất mạng trước khi nhận ACK, database **có thể đã commit thành công**. Không thể luôn coi exception là “đã rollback”. Nghiệp vụ quan trọng cần idempotency key và bước xác minh kết quả sau khi kết nối phục hồi.

## 9. Framework: `@Transactional` không tự biến mọi resource thành atomic

Với framework như Spring:

```java
@Transactional
public void transfer(...) {
    accountRepository.debit(...);
    accountRepository.credit(...);
    transferRepository.save(...);
}
```

Khi được gọi qua transaction proxy đúng, dùng đúng transaction manager và mọi repository tham gia cùng nguồn/transaction, các thao tác DB có thể thuộc một local transaction.

Nhưng hãy kiểm tra:

| Tình huống | Rủi ro |
| --- | --- |
| Repository A và B dùng hai DataSource khác nhau | Local transaction manager có thể chỉ quản lý một nguồn |
| Self-invocation qua phương thức cùng class | Với proxy-based transaction, lời gọi có thể bỏ qua proxy |
| `@Async` hoặc tạo thread mới | Transaction context có thể không được truyền |
| Propagation `REQUIRES_NEW` | Có thể mở một transaction độc lập, suspend transaction ngoài |
| `NESTED` | Có thể dùng savepoint, không nhất thiết là transaction độc lập |
| Exception bị bắt và nuốt | Framework có thể tiếp tục COMMIT nếu không đánh dấu rollback |
| Quy tắc checked exception | Rollback rules phụ thuộc framework/cấu hình |
| Raw JDBC/JPA lấy connection không đồng bộ với manager | Một câu SQL có thể chạy ngoài scope dự kiến |
| Gọi HTTP/broker trong phương thức transactional | Resource ngoài SQL không tự tham gia |

### 9.1. REQUIRES_NEW có nghĩa gì?

```text
Outer transaction:
  UPDATE đơn hàng
  Inner REQUIRES_NEW:
      INSERT log -> COMMIT độc lập
  Outer -> ROLLBACK
```

Log từ inner có thể vẫn còn. Đôi khi cần log **nỗ lực thất bại** độc lập, nhưng nếu log có nghĩa “đơn đã thành công”, đây có thể là lỗi. Phải phân biệt **audit của nỗ lực** với **audit của trạng thái đã commit**.

### 9.2. Reactive và async

Trong reactive stack như R2DBC, transaction context có thể được truyền qua cơ chế reactive, không phải đơn thuần ThreadLocal. Một operation được subscribe/chạy ngoài scope có thể dùng connection khác. Nguyên tắc vẫn là **xác minh câu SQL tham gia đúng transaction context**, không đoán theo thread, coroutine hay tên annotation.

## 10. ACID và những điều ACID không hứa

| Chữ | Ý nghĩa | Giới hạn cần nhớ |
| --- | --- | --- |
| **A — Atomicity** | Các thay đổi trong transaction được xác nhận/hủy như một đơn vị | Không bao phủ connection hay side effect không tham gia |
| **C — Consistency** | Duy trì những bất biến được ràng buộc/kiểm tra | DB không tự hiểu tất cả quy tắc nghiệp vụ |
| **I — Isolation** | Điều phối transaction đồng thời theo mức cô lập | Không phải mức nào cũng ngăn mọi anomaly |
| **D — Durability** | Commit thành công được duy trì theo bảo đảm của DBMS/cấu hình | Phụ thuộc cơ chế ghi log, replication và khả năng khôi phục |

Nếu debit 100 và credit 120 **trong cùng transaction**, SQL vẫn có thể COMMIT nếu không có quy tắc bảo vệ bất biến tổng tiền. Atomicity không chứng minh phép tính đúng.

### 10.1. Isolation và concurrency

Những vấn đề cần học:

- **Dirty read:** đọc dữ liệu chưa commit của transaction khác.
- **Non-repeatable read:** đọc lại một hàng trong cùng transaction nhận giá trị mới do transaction khác commit.
- **Phantom:** tập hàng thỏa điều kiện thay đổi giữa các lần đọc.
- **Lost update:** cập nhật dựa trên trạng thái cũ làm mất cập nhật đồng thời.
- **Write skew:** hai transaction sửa các hàng khác nhau nhưng làm sai bất biến chung.
- **Deadlock:** hai hoặc nhiều transaction chờ khóa theo vòng.

PostgreSQL dùng MVCC, có `READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE` và những quy tắc cụ thể. MySQL/InnoDB, SQL Server và Oracle có cơ chế/giao thức cô lập khác nhau dù tên mức isolation tương tự.

### 10.2. SERIALIZABLE không có nghĩa sẽ không gặp lỗi

Ở PostgreSQL, transaction SERIALIZABLE có thể bị từ chối với SQLSTATE `40001` (*serialization failure*) để tránh một lịch thực thi không thể coi là tuần tự. Ứng dụng phải **rollback và retry toàn bộ logic nghiệp vụ** nếu an toàn, không chỉ chạy lại câu cuối.

### 10.3. Deadlock và retry

PostgreSQL có mã lỗi `40P01` cho deadlock. Một số biện pháp:

- Giữ transaction ngắn.
- Lấy khóa cùng thứ tự giữa các luồng.
- Dùng index và điều kiện WHERE phù hợp.
- Không chờ người dùng/HTTP khi đang giữ khóa dài.
- Retry có giới hạn, backoff và idempotency.

Không retry mù mọi lỗi: thiếu tiền, sai tenant, FK/unique conflict có thể là từ chối nghiệp vụ, không phải lỗi transient.

## 11. SAVEPOINT và transaction “lồng nhau”

Ví dụ PostgreSQL:

```sql
BEGIN;

UPDATE tx_scope_lab.accounts
SET balance = balance - 10
WHERE tenant_id = 10 AND account_id = 101;

SAVEPOINT before_optional;

UPDATE tx_scope_lab.accounts
SET balance = balance + 20
WHERE tenant_id = 10 AND account_id = 102;

ROLLBACK TO SAVEPOINT before_optional;

UPDATE tx_scope_lab.accounts
SET balance = balance + 10
WHERE tenant_id = 10 AND account_id = 102;

RELEASE SAVEPOINT before_optional;

ROLLBACK;
```

Sau `ROLLBACK TO`, phần cộng nhầm 20 bị hủy, còn phần trừ 10 trước savepoint vẫn chưa commit trong transaction. `RELEASE SAVEPOINT` bỏ mốc rollback một phần, **không tự COMMIT**. ROLLBACK cuối cùng hủy cả trừ 10 và cộng 10.

Trong SQL Server có `SAVE TRANSACTION` và quy tắc nested transaction/`@@TRANCOUNT` riêng. Không sao chép mô hình “transaction con commit độc lập” khi framework thực tế chỉ dùng savepoint.

## 12. Một transaction SQL không rollback được side effect ngoài database

```text
BEGIN trên PostgreSQL
  UPDATE order -> PAID
  HTTP POST sang Payment API
  Gửi email "Thanh toán thành công"
  INSERT ledger ... -> lỗi
ROLLBACK PostgreSQL
```

Kết quả có thể là:

- Thay đổi order trong PostgreSQL bị rollback.
- Payment API **đã ghi nhận một giao dịch riêng**.
- Email đã gửi **không bị thu hồi**.

Những thứ sau thường không nằm trong local SQL transaction nếu không có cơ chế phối hợp riêng:

- HTTP/gRPC API của dịch vụ khác.
- Email, SMS, push notification.
- Message broker/queue.
- File, object storage, cache, search index.
- Database khác trên connection khác.
- Cổng thanh toán/ERP có cơ chế commit riêng.

### 12.1. Gửi sau COMMIT vẫn có rủi ro

```text
COMMIT DB thành công
Ứng dụng crash
Email/event chưa được gửi
```

Gửi trước commit có thể tạo thông báo cho giao dịch bị rollback; gửi ngay sau commit có thể mất thông báo khi process crash. Đây là khoảng trống mà **transactional outbox** thường giải quyết.

### 12.2. ROLLBACK không đảo các giá trị sequence

Trong PostgreSQL, các giá trị cấp bởi `nextval()` không nhất thiết được lấy lại sau rollback. Log hệ thống cũng có thể ghi rằng câu lệnh đã chạy. Không nhầm “dữ liệu nghiệp vụ rollback” với “toàn bộ dấu vết và side effect đều biến mất”.

## 13. Transactional outbox: ghi ý định phát sự kiện trong cùng COMMIT

Một mô hình:

```text
BEGIN local transaction trên PostgreSQL
    UPDATE accounts
    INSERT transfers
    INSERT outbox(event_key, type, payload)
COMMIT

Publisher worker:
    đọc outbox đã commit
    publish event tới broker
    cập nhật sent_at / retry theo quy trình
```

Nếu transaction ROLLBACK, cả transfer và outbox đều bị hủy. Nếu COMMIT, hàng outbox đã tồn tại để worker gửi sau khi ứng dụng khởi động lại.

### 13.1. Ví dụ outbox trong schema thực hành

```sql
BEGIN;

UPDATE tx_scope_lab.accounts
SET balance = balance - 25
WHERE tenant_id = 10
  AND account_id = 101
  AND balance >= 25;

UPDATE tx_scope_lab.accounts
SET balance = balance + 25
WHERE tenant_id = 10 AND account_id = 102;

INSERT INTO tx_scope_lab.transfers (
    transfer_ref, tenant_id, from_account_id, to_account_id, amount
)
VALUES ('demo-outbox-001', 10, 101, 102, 25.00);

INSERT INTO tx_scope_lab.outbox (
    event_key, event_type, payload
)
VALUES (
    'demo-outbox-001',
    'TransferCompleted',
    jsonb_build_object('transfer_ref', 'demo-outbox-001', 'amount', 25.00)
);

SELECT event_key, event_type, sent_at
FROM tx_scope_lab.outbox
WHERE event_key = 'demo-outbox-001';

ROLLBACK;
```

Sau ROLLBACK, không còn transfer/outbox mới của `demo-outbox-001`. Đây chỉ là ví dụ ranh giới atomicity: muốn COMMIT một chuyển tiền thật, **phải kiểm tra số hàng debit và credit, quyền, tiền tệ, idempotency và concurrency** trước khi xác nhận.

### 13.2. Vì sao outbox vẫn có thể gửi lặp?

Worker có thể:

```text
1. Đọc outbox PENDING.
2. Publish thành công tới broker.
3. Crash trước khi cập nhật sent_at.
4. Restart: thấy outbox vẫn PENDING.
5. Publish cùng event lần hai.
```

Outbox giúp **không mất ý định gửi** sau commit, nhưng không tự bảo đảm broker nhận đúng một bản. Vì thế consumer cần xử lý **idempotent**, và publisher cần retry/reconciliation.

## 14. Inbox: consumer xử lý thông điệp lặp an toàn

Một consumer có thể nhận cùng `event_id` nhiều lần. Một phương án:

```text
BEGIN transaction consumer DB
    INSERT inbox(event_id) với UNIQUE constraint
    nếu event đã có -> không thực hiện lại business action
    nếu mới -> UPDATE dữ liệu business
COMMIT consumer DB
```

Bảng ý tưởng:

```sql
CREATE TABLE consumer_inbox (
    event_id TEXT PRIMARY KEY,
    received_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

Đây là mẫu cho **database của consumer**, không phải schema lab đã tạo. Ghi inbox và thay đổi business cần được thực hiện **trong cùng local transaction của consumer**, không commit inbox trước rồi mới làm nghiệp vụ. Nếu làm sai thứ tự, event có thể bị coi là đã xử lý dù cập nhật business chưa từng commit.

### 14.1. Exactly-once phải nêu rõ phạm vi

Một broker có thể quảng bá một loại “exactly-once processing” trong phạm vi giao thức broker; điều đó không tự đồng nghĩa một UPDATE SQL ở database khác hoặc một HTTP call được thực hiện đúng một lần. Phải xác định **đúng một lần cho thao tác nào** và cơ chế dedup/transaction ở điểm đó.

## 15. COMMIT không rõ kết quả khi mất kết nối

```text
Application                       Database
-----------                       --------
COMMIT -------------------------> Ghi nhận thành công
          X mạng đứt
Không nhận ACK
```

Application có thể không biết database **đã COMMIT hay chưa**. Nếu retry một chuyển tiền bằng một mã giao dịch mới, có nguy cơ chuyển **hai lần**.

### 15.1. Idempotency key ổn định

Mỗi nghiệp vụ quan trọng nên có mã định danh:

```text
transfer_ref = T-2026-00042
Lần gửi 1 -> timeout
Lần gửi 2 -> giữ nguyên transfer_ref
```

Database cần unique constraint hoặc cơ chế claim có tính nguyên tử theo mã này. Một request trùng mã nhưng **payload khác** (amount, account, tenant) phải được phân biệt; không coi là cùng một yêu cầu hợp lệ chỉ vì chuỗi key trùng.

### 15.2. Quy trình khi outcome unknown

1. Phục hồi kết nối hoặc sử dụng kênh đọc tin cậy.
2. Tra cứu ledger/trạng thái theo idempotency key.
3. Nếu đã ghi nhận, trả kết quả đã xác nhận.
4. Nếu chưa thấy và có cơ chế retry an toàn, thử lại **cùng key**.
5. Nếu còn bất định, giữ trạng thái PENDING/UNKNOWN và đối soát; không tự kết luận “không nhận OK nghĩa là chưa commit”.

### 15.3. SELECT trước rồi INSERT chưa đủ

Hai request đồng thời có thể đều SELECT thấy chưa có `transfer_ref` và cùng bắt đầu xử lý. Cần **unique claim trong transaction**, khóa/constraint và quy tắc xử lý conflict. Idempotency không chỉ là một câu SELECT tại đầu hàm.

## 16. Khi nhiều database cần phối hợp

Một nghiệp vụ đặt hàng có thể đi qua:

```text
Order DB     -> tạo đơn PENDING
Inventory DB -> giữ tồn kho
Payment DB   -> authorize thanh toán
Email        -> thông báo
```

Mỗi database/dịch vụ có thể có local transaction riêng. Nếu tồn kho đã commit nhưng thanh toán thất bại, **ROLLBACK của Order DB không tự giải phóng tồn kho**.

### 16.1. Trường hợp cùng một DBMS nhưng khác schema

Hai bảng trong hai schema cùng một PostgreSQL database có thể được một connection sửa trong cùng transaction. Trong MySQL/InnoDB, những bảng transactional ở nhiều schema cùng server có thể cùng tham gia transaction thích hợp. SQL Server có khả năng cross-database transaction trong một số cấu hình cùng instance, nhưng remote servers và những topology đặc biệt có giới hạn riêng.

Không nên nói “hễ khác schema thì phải 2PC”. Ranh giới thực là **transaction manager, engine, connection và tài nguyên được hỗ trợ**.

### 16.2. Foreign data wrapper và linked server

Một câu SQL sử dụng FDW/dblink/linked server có thể chạm nguồn từ xa. Không mặc định vì nó xuất hiện trong **một statement** mà rollback của database nguồn bao phủ mọi side effect ở xa trong mọi lỗi/cấu hình. Cần kiểm tra khả năng transaction của provider, driver, phiên bản và giao thức đang dùng.

## 17. Two-phase commit (2PC) và XA

**Two-phase commit** là mô hình điều phối một quyết định xác nhận giữa nhiều resource manager hỗ trợ giao thức.

```text
             COORDINATOR
                  |
      +-----------+-----------+
      |                       |
   Database A               Database B
      |                       |
  PHASE 1: PREPARE        PHASE 1: PREPARE
  "Có thể commit?"        "Có thể commit?"
      |                       |
      +-----------+-----------+
                  |
     Nếu mọi bên sẵn sàng:
          PHASE 2: COMMIT
     Nếu không:
          PHASE 2: ABORT
```

### 17.1. Ưu điểm

Trong cấu hình được hỗ trợ, coordinator có thể phối hợp participant để đưa ra **một quyết định commit/abort toàn cục**, thay vì từng phía tự commit trước khi biết tình trạng các bên còn lại.

### 17.2. Chi phí và giới hạn

- Participant có thể giữ lock/tài nguyên sau PREPARE.
- Nếu coordinator/mạng gặp lỗi, giao dịch **in-doubt** có thể cần recovery.
- Log quyết định cần bền vững và có cơ chế theo dõi.
- Không phải mọi DB, HTTP API, broker hoặc cloud service đều hỗ trợ XA/2PC.
- Độ trễ và khả năng sẵn sàng của toàn luồng phụ thuộc nhiều bên.

**2PC không phải giải pháp “cứ thêm BEGIN ở hai DB là xong”.**

### 17.3. PostgreSQL prepared transactions

PostgreSQL có cú pháp nâng cao:

```sql
BEGIN;
-- Thay đổi trong transaction.
PREPARE TRANSACTION 'global-operation-001';

-- Sau đó, theo quyết định của coordinator:
COMMIT PREPARED 'global-operation-001';
-- hoặc ROLLBACK PREPARED 'global-operation-001';
```

Đây là **minh họa cú pháp, không phải bài thực hành nên tự chạy**. Cần cấu hình như `max_prepared_transactions` và coordinator/recovery phù hợp. Prepared transaction bỏ quên có thể giữ khóa/tài nguyên, gây sự cố vận hành.

Trong Java enterprise, có thể gặp JTA/XA transaction manager và `XADataSource`. Một `@Transactional` thông thường **không tự bảo đảm** đã có global XA transaction; cần kiểm tra resource enlistment và recovery.

## 18. Saga: nhiều local transactions và hành động bù trừ

Khi các service độc lập không hỗ trợ 2PC, hoặc workflow kéo dài, có thể dùng **saga**.

```text
1. Order:     tạo đơn PENDING       -> COMMIT local
2. Inventory: giữ tồn kho           -> COMMIT local
3. Payment:   authorize thanh toán  -> COMMIT local
4. Order:     xác nhận đơn          -> COMMIT local
```

Nếu bước 3 thất bại:

```text
Inventory: giải phóng tồn đã giữ  -> transaction bù
Order: chuyển trạng thái CANCELED -> transaction bù
```

**Compensation không phải SQL ROLLBACK qua các DB.** Những bước trước đã commit; bù trừ là **một nghiệp vụ mới** có thể cần audit, retry và xử lý lỗi riêng.

### 18.1. Bù trừ không phải lúc nào cũng nghịch đảo hoàn hảo

- Giữ tồn có thể được giải phóng.
- Thanh toán đã authorize có thể được void theo hợp đồng.
- Tiền đã capture có thể cần refund, không phải rollback.
- Email đã gửi không có phép “undo” bảo đảm.
- Hàng đã giao có thể cần quy trình trả hàng.

Trạng thái PENDING, timeout, chính sách bù trừ và cách xử lý thủ công phải được thiết kế trước, không chờ đến khi lỗi xảy ra.

### 18.2. Orchestration và choreography

| Cách | Mô tả | Lưu ý |
| --- | --- | --- |
| **Orchestration** | Một coordinator quyết định bước tiếp theo và compensation | Dễ theo dõi luồng dài, nhưng coordinator cần bền vững/recovery |
| **Choreography** | Các service phản ứng với event và tự phát event tiếp | Giảm điều phối trung tâm nhưng khó quan sát khi nhiều nhánh |

### 18.3. Eventual consistency là một hợp đồng

Sau khi Inventory commit, Order có thể vẫn PENDING. Đây có thể là trạng thái trung gian hợp lệ nếu có SLA và cách xử lý. Hệ thống cần biết **bao lâu được phép chờ**, khi nào retry, khi nào bù, và khi nào phải can thiệp thủ công.

## 19. So sánh các cơ chế

| Cơ chế | Mục tiêu | Giới hạn |
| --- | --- | --- |
| **Local transaction** | Atomic commit/rollback cho thao tác DB cùng scope | Không bao phủ side effect không tham gia |
| **XA/2PC** | Quyết định commit cho nhiều participant hỗ trợ giao thức | Chi phí locking/recovery; không hỗ trợ mọi nguồn |
| **Saga** | Phối hợp chuỗi local commits và compensation | Không có rollback nguyên tử toàn chuỗi; cần trạng thái trung gian |
| **Transactional outbox** | Giữ ý định gửi event cùng COMMIT business | Có thể publish lặp; cần worker và dedup |
| **Transactional inbox** | Tránh tác động lặp khi consumer nhận lại event | Chỉ bảo vệ business effect thuộc transaction consumer |
| **Idempotency key** | Retry request mà không tạo nghiệp vụ lặp | Phải lưu/claim atomically, đối chiếu payload |
| **Reconciliation** | Phát hiện và sửa sai lệch giữa các nguồn | Không ngăn mọi lỗi ban đầu |

Một kiến trúc đáng tin có thể dùng **local transaction + outbox + inbox + saga + đối soát**, chứ không chọn một cơ chế thay tất cả.

## 20. Không giữ transaction mở trong lúc gọi dịch vụ chậm

Một anti-pattern:

```text
BEGIN DB
SELECT account FOR UPDATE
CALL payment provider (chờ 15 giây)
UPDATE account
COMMIT DB
```

Trong khi chờ HTTP, transaction giữ khóa và có thể gây:

- Transaction khác bị block.
- Deadlock, lock timeout và giảm throughput.
- Snapshot/MVCC cũ kéo dài.
- Connection pool bị chiếm hết vì mỗi request giữ một connection.

Trong nhiều trường hợp, nên thiết kế **reservation/state machine/outbox/saga** để không giữ một transaction ghi suốt lời gọi dịch vụ ngoài. Transaction local cần **ngắn**, chứa các bước SQL cần atomic và kết thúc sớm.

### 20.1. Lock không thay thế unique constraint

`SELECT ... FOR UPDATE` khóa những hàng **đang tồn tại và được chọn**. Nó không tự khóa một hàng chưa có. Nếu cần “không được đặt cùng ghế hai lần”, thường cần unique/filtered constraint hoặc isolation phù hợp với tập điều kiện đó.

### 20.2. Isolation không thay authorization

Một transaction SERIALIZABLE vẫn có thể sửa nhầm tenant nếu `WHERE account_id = 101` mà thiếu `tenant_id`. Isolation bảo vệ tính tương tác đồng thời, không tự biết ai được quyền sửa dữ liệu nào.

## 21. Observability và điều tra sự cố

Khi gặp lỗi “DB đã ROLLBACK nhưng trạng thái nghiệp vụ vẫn thay đổi”, cần dựng **timeline theo tài nguyên**:

```text
request_id / transfer_ref
connection/session A
connection/session B
BEGIN/COMMIT/ROLLBACK thực tế
SQL row counts và SQLSTATE
HTTP/broker call cùng response
outbox event id, consumer inbox id
thời điểm commit/timeout
```

### 21.1. PostgreSQL: quan sát transaction đang mở

Với quyền giám sát phù hợp:

```sql
SELECT
    pid,
    state,
    xact_start,
    wait_event_type,
    wait_event
FROM pg_stat_activity
WHERE datname = current_database()
  AND xact_start IS NOT NULL
ORDER BY xact_start;
```

Các trạng thái như `idle in transaction` và `idle in transaction (aborted)` giúp nhận diện connection giữ transaction mở nhưng không thực hiện công việc. Thông tin phiên khác có thể bị giới hạn theo quyền; không cấp superuser cho application chỉ để quan sát.

### 21.2. Những chỉ số cần theo dõi

- Thời gian transaction và tuổi transaction đang mở.
- Lock wait, deadlock, serialization failure, timeout.
- Rollback rate, tỷ lệ retry và số lần retry vượt ngưỡng.
- Outbox backlog, event pending quá hạn, consumer lag.
- Saga pending/compensating quá hạn.
- Operation có kết quả COMMIT chưa rõ.
- Sai lệch khi đối soát ledger và trạng thái tổng hợp.

### 21.3. Bảo vệ dữ liệu trong log

Log nên ghi request ID, SQLSTATE, số hàng, connection ID và event key; hạn chế ghi PII, thông tin thanh toán, token hoặc toàn bộ payload khi không cần. Observability không phải lý do mở rộng quyền truy cập dữ liệu nhạy cảm.

## 22. Các lỗi tư duy phổ biến

| Ngộ nhận | Vì sao sai? | Cách nghĩ đúng |
| --- | --- | --- |
| Cùng một HTTP request là một transaction | Request có thể dùng nhiều connection | Xem transaction context thực tế |
| Cùng PostgreSQL database thì rollback một connection hủy mọi update | Mỗi connection có transaction riêng | Chỉ các statement tham gia cùng scope mới được rollback cùng |
| Cùng DataSource thì chắc cùng connection | Pool cấp kết nối tùy thời điểm | Dùng transaction manager/cùng conn |
| Cùng thread thì chắc cùng transaction | Proxy, async, reactive context có thể khác | Kiểm tra framework và propagation |
| `@Transactional` rollback được email/HTTP | Những resource ngoài không tự tham gia | Outbox/saga/idempotency |
| Gửi email sau COMMIT là chắc chắn không mất | Process có thể crash trước send | Outbox |
| `ROLLBACK` sau `COMMIT` sẽ undo | COMMIT đã kết thúc transaction | Transaction bù có audit |
| `SAVEPOINT` là transaction con commit riêng | Savepoint chỉ là mốc trong transaction ngoài | RELEASE không đồng nghĩa COMMIT |
| Không có exception nghĩa UPDATE thành công | UPDATE 0 hàng vẫn là statement hợp lệ | Kiểm tra row count và invariant |
| Dùng SERIALIZABLE là không có lỗi | DB có thể abort với `40001` | Retry toàn transaction có giới hạn |
| Retry mọi exception đều an toàn | Business conflict không hết khi retry | Phân loại lỗi và idempotency |
| Timeout sau COMMIT nghĩa chắc rollback | Server có thể đã commit | Key ổn định và đối soát |
| Outbox đồng nghĩa publish đúng một lần | Worker có thể crash sau publish | Inbox/dedup |
| Broker exactly-once bao phủ DB consumer | Hợp đồng exactly-once có phạm vi | Transactional inbox và unique event ID |
| 2PC chạy được với HTTP bất kỳ | Participant phải hỗ trợ giao thức | Saga/compensation khi độc lập |
| Saga là rollback toàn chuỗi | Mỗi bước đã local commit | Compensation là nghiệp vụ mới |
| FDW/linked server tự có atomicity xuyên mọi nguồn | Phụ thuộc engine/provider/protocol | Kiểm tra tài liệu và failure modes |
| Khác schema bắt buộc phải 2PC | Cùng database/connection vẫn có thể local transaction | Phân biệt schema với resource manager |
| Ghi log chung request ID là transaction chung | Request ID chỉ là metadata | Phải chứng minh bằng connection/manager |
| Giữ transaction mở càng lâu càng an toàn | Giữ lock/snapshot, làm tắc hệ thống | Transaction ngắn và state machine |

## 23. Hướng học chuyên sâu: tám chặng từ SQL tới hệ thống đáng tin

### Chặng 1 — Local transaction và autocommit

**Nắm:** BEGIN/START TRANSACTION, COMMIT, ROLLBACK, SAVEPOINT, trạng thái transaction lỗi, JDBC autoCommit.

**Thực hành:** chạy thí nghiệm hai session ở mục 4–5; ghi giá trị đọc được trước và sau COMMIT/ROLLBACK.

**Đạt yêu cầu khi:** giải thích được vì sao một COMMIT độc lập không bị hủy bởi ROLLBACK khác.

### Chặng 2 — MVCC, isolation và locking

**Nắm:** snapshot, read-your-own-writes, row lock, `READ COMMITTED`, `REPEATABLE READ`, `SERIALIZABLE`, lost update, write skew.

**Thực hành:** Session A giữ `SELECT ... FOR UPDATE`, Session B cố UPDATE cùng hàng; quan sát lock wait rồi thử deadlock trong database lab.

**Đạt yêu cầu khi:** phân biệt được deadlock, lock timeout và serialization failure; biết khi nào retry toàn transaction.

### Chặng 3 — Connection pooling và framework

**Nắm:** cùng một JDBC Connection, transaction manager, rollback rules, propagation, self-invocation, multi-DataSource, async/reactive context.

**Thực hành:** viết test debit/credit trên một connection phải rollback cùng nhau; cố ý tách hai connection và chỉ ra failure.

**Đạt yêu cầu khi:** đọc một service nhiều repository và xác định câu SQL nào nằm trong transaction.

### Chặng 4 — Retry và idempotency

**Nắm:** unique operation key, claim atomic, kiểm tra payload, tình huống timeout/COMMIT không rõ, phân loại lỗi.

**Thực hành:** gửi một request chuyển tiền hai lần với cùng mã; test timeout sau khi DB đã commit.

**Đạt yêu cầu khi:** không kết luận “mất ACK tức rollback” và không tạo nghiệp vụ lặp khi retry.

### Chặng 5 — Outbox/inbox và event delivery

**Nắm:** business+outbox trong một local transaction, publisher at-least-once, idempotent consumer, inbox unique, DLQ và replay.

**Thực hành:** mô phỏng crash sau publish trước khi đánh dấu sent, rồi xác minh consumer không cập nhật dữ liệu hai lần.

**Đạt yêu cầu khi:** mô tả chính xác phạm vi bảo đảm của outbox, inbox và broker.

### Chặng 6 — Distributed transaction và 2PC

**Nắm:** coordinator, PREPARE/COMMIT, in-doubt, recovery, XA/JTA, prepared transaction monitoring.

**Thực hành:** vẽ state machine của coordinator và hai participant trong các kịch bản mất mạng. Không tạo prepared transaction tồn đọng trên server dùng chung.

**Đạt yêu cầu khi:** giải thích được chi phí blocking/recovery và điều kiện participant phải hỗ trợ giao thức.

### Chặng 7 — Saga và bù trừ nghiệp vụ

**Nắm:** orchestration, choreography, PENDING/CONFIRMED/CANCELED, compensation, timeout, retry và manual intervention.

**Thực hành:** mô phỏng Order → Inventory → Payment; cố ý làm payment fail rồi thiết kế bước giải phóng tồn và hủy đơn.

**Đạt yêu cầu khi:** không gọi compensation là ROLLBACK SQL và xác định được trường hợp tác động không thể đảo hoàn toàn.

### Chặng 8 — Vận hành và đối soát

**Nắm:** tracing, monitoring lock/transaction age, outbox lag, unknown commit, reconciliation, runbook.

**Thực hành:** giả lập event lặp/đến trễ, kiểm tra backlog và thiết kế quy trình sửa dữ liệu sai mà vẫn giữ audit.

**Đạt yêu cầu khi:** có thể trả lời “khi một bước mất phản hồi, làm sao biết trạng thái thật và khôi phục an toàn?”.

## 24. Bộ bài tập thực hành

Các bài yêu cầu suy luận phạm vi transaction trước khi chạy. Chỉ thử UPDATE/DELETE trong database lab. Với bài có COMMIT, ghi nhận số dư sau chạy và khôi phục môi trường thực hành nếu muốn lặp lại.

### Bài 1 — Hai backend

Mở hai cửa sổ psql, chạy `SELECT pg_backend_pid()`. Nếu PID khác nhau, transaction của hai cửa sổ có phải một không? Một backend PID có thể phục vụ nhiều transaction nối tiếp nhau qua pool không?

### Bài 2 — Read-your-own-writes

Session A BEGIN trừ 100 ở account 101, chưa commit. Tại sao A SELECT thấy 900 còn B ở READ COMMITTED thấy 1000? Sau A ROLLBACK, B thấy bao nhiêu?

### Bài 3 — COMMIT và snapshot

Làm lại bài 2 nhưng A COMMIT. B ở READ COMMITTED đọc lại có thể thấy gì? Nếu B đang giữ snapshot REPEATABLE READ cũ, hành vi khác thế nào?

### Bài 4 — Rollback khác connection

Session A trừ 20 ở account 101, B cộng 20 ở account 102 và COMMIT, A ROLLBACK. Từ trạng thái 1000/500, tổng mới của hai account là bao nhiêu? Vì sao đây là lỗi nghiệp vụ, không phải DBMS rollback sai?

### Bài 5 — Bảng TEMP

Tại Session A tạo `CREATE TEMP TABLE t(x INT)`; B thử đọc t. Vì sao B không thấy? Dùng bảng nào trong lab để hai session cùng quan sát?

### Bài 6 — JDBC transaction

Viết service dùng `setAutoCommit(false)`, PreparedStatement và `executeUpdate()==1`. Đặt exception sau debit để chứng minh credit và debit chỉ được commit cùng nhau.

### Bài 7 — Lỗi lấy hai connection

Chuyển credit sang connection B với autocommit bật. Sau credit, cố ý gây exception và rollback A. Những hàng nào còn thay đổi? Làm sao sửa thiết kế?

### Bài 8 — Framework propagation

Một phương thức trong dùng `REQUIRES_NEW` ghi audit rồi commit; phương thức ngoài rollback. Audit còn không? Khi nào ghi audit nỗ lực độc lập là hợp lý?

### Bài 9 — Transaction với async

Một phương thức transactional spawn thread mới ghi DB. Có thể khẳng định thread mới tham gia transaction không? Cần kiểm tra context/connection manager thế nào?

### Bài 10 — Zero-row UPDATE

Debit amount lớn hơn số dư, SQL UPDATE 0 hàng, credit vẫn chạy. Hãy mô tả cách phát hiện từ row count và rollback toàn nghiệp vụ.

### Bài 11 — Outbox rollback

Chạy ví dụ ở mục 13 kết thúc bằng ROLLBACK. Kiểm tra `tx_scope_lab.transfers` và `tx_scope_lab.outbox` không có event mới. Vì sao rollback email gửi trực tiếp không tương tự?

### Bài 12 — Outbox publish lặp

Publisher gửi event rồi crash trước `sent_at`. Tại sao event có thể được gửi lần hai? Thiết kế inbox/unique event ID để ngăn duplicate business action.

### Bài 13 — Commit outcome unknown

DB commit xong nhưng client timeout trước ACK. Nếu client retry với transfer_ref khác, điều gì có thể xảy ra? Tại sao cần key ổn định và bước đối soát?

### Bài 14 — Serialization retry

PostgreSQL trả SQLSTATE `40001`. Nên retry câu cuối hay toàn bộ transaction? Khi có HTTP side effect, cần bảo vệ gì trước retry?

### Bài 15 — Deadlock

Session A khóa 101 rồi muốn 102; B khóa 102 rồi muốn 101. Vẽ wait-for graph; đề xuất thứ tự khóa, transaction ngắn và retry có giới hạn.

### Bài 16 — Nhiều schema

Một connection PostgreSQL cập nhật bảng ở schema sales và audit của cùng database. Có phải dùng XA không? Phân biệt với hai PostgreSQL databases qua hai connections.

### Bài 17 — 2PC

Vẽ pha PREPARE và COMMIT. Nếu coordinator crash khi cả hai participant đã PREPARED, cần cơ chế recovery nào? Vì sao phải giám sát prepared transactions tồn đọng?

### Bài 18 — Saga

Thiết kế Order/Inventory/Payment với trạng thái PENDING, RESERVED, CONFIRMED, CANCELED. Nếu payment thất bại sau khi inventory đã commit, compensation nào cần thực hiện?

### Bài 19 — Email không rollback

Một email xác nhận được gửi trước COMMIT, rồi INSERT cuối bị lỗi. ROLLBACK có thu hồi email không? Đề xuất outbox và consumer dedup.

### Bài 20 — CDC và warehouse

DB nguồn COMMIT nhưng warehouse chưa có hàng mới. Có phải local COMMIT đã thất bại không? Cần đo CDC lag, snapshot và watermark như thế nào?

### Bài 21 — Bảo vệ dữ liệu theo tenant

Trong lab, tenant 10 và 20 đều có account 101. Nếu một UPDATE chỉ có `WHERE account_id=101` thì điều gì có thể xảy ra? SERIALIZABLE có thay thế điều kiện tenant không?

### Bài 22 — Connection pool leak

Ứng dụng để connection ở trạng thái `idle in transaction` nhiều phút. Những tác động tới lock, MVCC, vacuum và pool là gì? Đề xuất timeout/cleanup.

### Bài 23 — Sự cố sản xuất giả định

Log báo “ROLLBACK transaction” nhưng số dư người nhận đã tăng 300. Hãy dựng timeline theo connection A/B, autocommit, thời điểm COMMIT và các event. Chỉ rõ bằng chứng cần tìm trong code và log.

### Bài 24 — Chọn kiến trúc

Chọn local transaction, XA/2PC, saga, outbox hoặc inbox cho:

1. Ghi order và order_items trong cùng PostgreSQL database.
2. Ghi đơn rồi gửi email.
3. Hai XA resources cần một global commit.
4. Thanh toán qua một HTTP API không hỗ trợ XA.
5. Consumer nhận message có thể lặp rồi ghi database.

### Bài 25 — Thiết kế dịch vụ hoàn chỉnh

Phác thảo API chuyển tiền có `transfer_ref` ổn định; tenant/currency validation; debit/credit/ledger/outbox trong cùng transaction; row-count checks; rollback/retry; xử lý commit uncertainty; inbox consumer; quan sát transaction và đối soát ledger. Ghi rõ phần nào được database bảo đảm **atomic**, phần nào chỉ **eventually consistent**.

## 25. Checklist khi thiết kế transaction qua nhiều thành phần

### Phạm vi

- [ ] Những statement bắt buộc cùng COMMIT có chạy trên **cùng transaction context** không?
- [ ] Repository/ORM/JDBC có vô tình lấy connection khác không?
- [ ] Autocommit và propagation có được kiểm tra không?
- [ ] Có async/reactive operation nằm ngoài scope không?
- [ ] Có gọi database khác, HTTP, queue, email, object storage không?

### Tính đúng

- [ ] `WHERE` có tenant/khóa/điều kiện trạng thái phù hợp?
- [ ] Có kiểm tra affected rows và business invariant?
- [ ] Unique/constraint/locking phù hợp để chống race condition?
- [ ] Request/event có idempotency key và payload comparison?
- [ ] Side effect quan trọng có outbox/inbox hoặc cơ chế phối hợp tin cậy?

### Lỗi và phục hồi

- [ ] Exception có rollback đúng connection, kể cả lỗi giữa các bước?
- [ ] Deadlock/serialization được phân loại và retry có giới hạn?
- [ ] Khi mất ACK COMMIT có cách tra cứu kết quả thật?
- [ ] Saga có compensation và trạng thái pending/timeout?
- [ ] Có runbook đối soát khi dữ liệu lệch hoặc event backlog?

### Vận hành

- [ ] Transaction ngắn, không giữ lock trong lúc chờ UI/API dài?
- [ ] Có metric transaction age, lock waits, rollbacks, retries, outbox lag?
- [ ] Log có request ID/operation key nhưng không lộ dữ liệu nhạy cảm?
- [ ] Đã xác minh cú pháp và khả năng hỗ trợ của DBMS/version thật?

## 26. Sơ đồ quyết định tổng hợp

```text
                 YÊU CẦU NGHIỆP VỤ
                         |
                         v
             Các thao tác thuộc đâu?
                         |
             +-----------+-----------+
             |                       |
             v                       v
    Một local DB transaction?     Nhiều nguồn/side effect?
             |                       |
             v                       v
      BEGIN trên connection       Chọn consistency model
      UPDATE/INSERT/DELETE              |
      CHECK affected rows       +-------+---------+
      COMMIT hoặc ROLLBACK      |                 |
             |                  v                 v
             v                XA/2PC            Saga
        ACID cục bộ        Coordinator +      Local commits +
                          recovery            compensation
                                                |
                           +--------------------+
                           |
                           v
                  Outbox / inbox / idempotency
                           |
                           v
                    Retry + monitoring +
                    reconciliation + runbook
```

## 27. Kết luận

**Giới hạn của giao dịch trong một kết nối** không phải là giới hạn của số câu SQL hay số bảng, mà là **phạm vi những thao tác thực sự được một transaction manager quản lý và commit/rollback cùng nhau**. Hai connection khác nhau có thể đang thực hiện hai transaction độc lập dù cùng database; cùng một connection có thể thao tác nhiều bảng/schema thuộc phạm vi hỗ trợ. Một local ROLLBACK không hủy COMMIT độc lập ở connection khác và không hoàn tác email, HTTP hay message đã gửi.

Khi xây ứng dụng, cần xác minh **connection, autocommit, framework propagation, concurrency, isolation, affected rows và trạng thái COMMIT chưa rõ**. Với nhiều dịch vụ, local transaction vẫn bảo vệ từng bước, còn **XA/2PC, saga, outbox/inbox, idempotency và đối soát** giải quyết các dạng phối hợp khác nhau; không có một cơ chế đơn lẻ thay thế tất cả.

Con đường học chuyên sâu tốt nhất là **tái hiện lỗi bằng hai phiên PostgreSQL**, sau đó thử với JDBC/connection pool, tiêm lỗi mạng và concurrency, triển khai outbox/inbox, mô hình hóa saga và học vận hành/recovery. Khi có thể trả lời chính xác **“thao tác nào nằm trong giao dịch nào, ai đã COMMIT, ROLLBACK còn hủy được gì và khi mất kết nối phải khôi phục ra sao?”**, bạn đã có nền tảng vững để thiết kế một hệ thống dữ liệu đáng tin cậy.
