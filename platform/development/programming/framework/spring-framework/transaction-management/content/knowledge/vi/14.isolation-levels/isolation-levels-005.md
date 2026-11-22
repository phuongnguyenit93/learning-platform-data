# READ_COMMITTED và ảnh chụp dữ liệu theo từng hệ quản trị

> **Học phần:** Spring Framework — Transaction Management. **Chủ đề cha:** Mức cô lập. Bài này tập trung vào cách `READ_COMMITTED` kiểm soát dữ liệu được phép nhìn thấy và sự khác nhau giữa **statement-level MVCC snapshot** với **lock-based reads** ở PostgreSQL, Oracle Database, MySQL/InnoDB, Microsoft SQL Server và H2. Phần Spring trình bày `@Transactional(isolation = Isolation.READ_COMMITTED)`, transaction boundary, datasource/driver và một dự án Java 17 chạy được để kiểm chứng non-repeatable read.

## 1. READ_COMMITTED cam kết điều gì?

**READ_COMMITTED** là một transaction isolation level trong JDBC và SQL. Mục tiêu cơ bản: một lần đọc ở mức này **không lấy dữ liệu đang sửa nhưng chưa commit của transaction khác** (*dirty read*). Tuy nhiên, giữa **hai câu SQL** của cùng một transaction, transaction khác có thể commit thay đổi. Vì vậy, đọc lại cùng một hàng có thể nhận giá trị mới (*non-repeatable read*) và lặp lại truy vấn theo điều kiện có thể gặp hàng mới (*phantom read*).

Đây là điểm cần phân biệt:

- **Isolation level** mô tả các hiện tượng đọc/ghi được phép hoặc được ngăn chặn theo hợp đồng của database.
- **Read view / snapshot** mô tả cách một database cụ thể xác định các phiên bản dữ liệu một câu lệnh nhìn thấy.
- **MVCC** (Multi-Version Concurrency Control) là cách giữ nhiều phiên bản bản ghi để hỗ trợ đọc nhất quán mà không bắt reader luôn đợi writer.
- **Locks** là cơ chế kiểm soát đọc/ghi đồng thời bằng khóa tài nguyên, có thể làm reader chờ writer hoặc ngược lại.

**Không được đồng nhất “READ_COMMITTED” với “cả transaction dùng một ảnh chụp cố định”.** Với PostgreSQL, Oracle và consistent read của MySQL/InnoDB ở READ COMMITTED, các lần đọc khác nhau thường tạo/nhận **ảnh chụp mới theo từng statement/consistent read**. SQL Server còn có **hai cơ chế READ COMMITTED** tùy database option `READ_COMMITTED_SNAPSHOT`.

## 2. Mô hình hai phiên đọc: transaction A và B

Giả sử một bảng đang có số dư:

```sql
CREATE TABLE account_balance (
    id INT PRIMARY KEY,
    balance INT NOT NULL
);

INSERT INTO account_balance (id, balance)
VALUES (1, 100);
```

Một lịch trình được kiểm soát:

```text
Thời điểm       Transaction A (READ COMMITTED)          Transaction B
---------------------------------------------------------------------------
t0              BEGIN
t1              SELECT balance WHERE id=1 -> 100
t2                                                       BEGIN
t3                                                       UPDATE -> 150
t4                                                       chưa COMMIT
t5              Không đọc được giá trị chưa commit 150
                (có thể thấy 100 hoặc phải đợi,
                 tùy DB/kiểu đọc)
t6                                                       COMMIT
t7              SELECT balance WHERE id=1 -> 150
t8              COMMIT
```

Hai lần `SELECT` của A diễn ra **trong cùng một transaction A**, nhưng lần đầu trả về `100` và lần sau trả về `150`. Không có dirty read: giá trị mới được thấy **sau khi B đã commit**.

Sự thay đổi `100 → 150` là **non-repeatable read**. `READ_COMMITTED` cho phép hiện tượng này. Nó không có nghĩa A “đọc dữ liệu sai”: A đang đọc **hai trạng thái đã commit khác nhau** tại hai thời điểm.

### Một lưu ý về thời điểm

Trong một database có statement-level snapshot như PostgreSQL, nếu B commit **sau khi một câu SELECT dài đã bắt đầu**, câu SELECT đó vẫn nhìn trạng thái phù hợp với snapshot của lúc câu lệnh bắt đầu (và các thay đổi do chính A đã thực hiện). **SELECT tiếp theo** sau khi B commit mới có thể thấy phiên bản mới. Không được diễn giải “READ_COMMITTED” thành việc một SELECT đang quét dữ liệu sẽ tự đổi mọi hàng sang phiên bản mới trong lúc chạy.

Với **SQL Server READ COMMITTED dùng shared locks**, không thể khẳng định mọi SELECT luôn có một ảnh chụp nhất quán tại cùng một thời điểm. Chương tương ứng sẽ giải thích chính xác sự khác biệt.

## 3. Dirty read, non-repeatable read và phantom read

| Hiện tượng | Định nghĩa thực hành | READ_COMMITTED |
| --- | --- | --- |
| **Dirty read** | A đọc giá trị B đã ghi nhưng B **chưa commit**; B có thể rollback | **Bị ngăn** trong hoạt động bình thường |
| **Non-repeatable read** | A đọc cùng một hàng hai lần; B commit thay đổi giữa hai lần | **Có thể xảy ra** |
| **Phantom read** | A chạy lại truy vấn với điều kiện; B commit INSERT/DELETE/UPDATE làm tập kết quả đổi | **Có thể xảy ra** |
| **Transaction-wide consistent snapshot** | Tất cả SELECT thường của A nhìn cùng trạng thái tại một mốc thời gian của A | **Không được READ_COMMITTED bảo đảm** |
| **Serialization** | Kết quả như các transaction chạy tuần tự theo một thứ tự hợp lệ | **Không được READ_COMMITTED bảo đảm** |

Phantom read minh họa:

```sql
-- Transaction A, lần 1
SELECT COUNT(*) FROM orders WHERE status = 'NEW';
-- 2

-- Transaction B thêm một đơn NEW rồi COMMIT.

-- Transaction A, lần 2
SELECT COUNT(*) FROM orders WHERE status = 'NEW';
-- 3
```

Các câu lệnh trên là **kịch bản hai session**, không phải script chạy liên tục trong một session. `READ_COMMITTED` cho phép A thấy số đếm thay đổi. Trong thực tế, số liệu còn phụ thuộc query execution, locking hints, trạng thái commit và transaction manager.

### Vì sao điều này đáng quan tâm với Java service?

```java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void processReport() {
    int countBefore = repository.countOpenOrders();
    // Một service khác có thể commit thay đổi vào lúc này.
    int countAfter = repository.countOpenOrders();
}
```

Đây là **trích đoạn** (repository do ứng dụng định nghĩa). `countBefore != countAfter` không phải bug của Spring. Isolation được database thực thi cho các truy vấn; annotation **không biến hai câu SELECT thành một ảnh chụp cố định của toàn method**.

## 4. “Ảnh chụp theo statement” nghĩa là gì?

Một **statement-level snapshot** có thể hiểu là *read view* được xác định cho **một câu SQL**, đối chiếu trạng thái các transaction đã commit trước mốc snapshot đó (cộng các thay đổi phù hợp do chính transaction hiện tại thực hiện). Khi chạy câu SQL khác ở READ COMMITTED, database có thể cấp **snapshot mới**.

```text
Transaction A:  BEGIN ------------------------------------------------ COMMIT
                  | SELECT #1 |                | SELECT #2 |
Snapshot A1:       ^ dữ liệu tại S1              ^
Transaction B:              UPDATE ---- COMMIT
Snapshot A2:                                  ^ dữ liệu tại S2

S1: id=1 -> 100
S2: id=1 -> 150
```

Với cách triển khai MVCC, database lưu đủ thông tin phiên bản để **tái dựng** dữ liệu của snapshot. Một câu SQL đang chạy có thể tránh việc đọc “nửa trước/nửa sau” của nhiều commit khác nhau. Đây là **statement-level read consistency**, yếu hơn transaction-level snapshot.

Nhưng cần nhớ ba ngoại lệ/giới hạn khi nói chung về hệ quản trị:

1. **Locking reads và DML** (`SELECT ... FOR UPDATE`, `UPDATE`, `DELETE`) không nhất thiết dùng cùng quy tắc phiên bản như plain consistent `SELECT`. Chúng phải xử lý xung đột cập nhật trên trạng thái hàng thực tế.
2. **Tự thấy thay đổi của mình** (*read your own writes*): một transaction thường thấy row chính nó vừa INSERT/UPDATE ngay cả khi chưa commit, dù snapshot của statement chỉ cho thấy dữ liệu đã commit từ transaction khác.
3. **READ COMMITTED lock-based** của SQL Server không đồng nghĩa snapshot theo statement; ngăn dirty read bằng shared locks nhưng có thể quan sát biến động trong một lần quét.

Vì vậy câu “READ_COMMITTED luôn snapshot từng statement” chỉ đúng nếu **đã nêu rõ engine và kiểu đọc** tương ứng.

## 5. PostgreSQL: snapshot mới ở đầu mỗi câu lệnh

Trong PostgreSQL, `READ COMMITTED` là mức cô lập mặc định cho transaction thông thường. Tài liệu PostgreSQL 18 mô tả plain `SELECT` ở mức này chỉ nhìn dữ liệu từ transaction khác đã commit **trước khi SELECT bắt đầu**. Mỗi câu lệnh mới có thể nhận snapshot mới.

Ví dụ hai cửa sổ `psql`.

### 5.1. Khởi tạo một lần

```sql
DROP TABLE IF EXISTS account_balance;
CREATE TABLE account_balance (
    id INT PRIMARY KEY,
    balance INT NOT NULL
);
INSERT INTO account_balance(id, balance) VALUES (1, 100);
```

Đây là ví dụ học tập trên database riêng. Không chạy `DROP TABLE` trên schema có dữ liệu thật.

### 5.2. Session A

```sql
BEGIN ISOLATION LEVEL READ COMMITTED;

SELECT balance
FROM account_balance
WHERE id = 1;
-- 100

-- Tại đây dừng, sang session B để UPDATE và COMMIT.

SELECT balance
FROM account_balance
WHERE id = 1;
-- 150

COMMIT;
```

### 5.3. Session B

Sau khi A hoàn thành SELECT đầu tiên:

```sql
BEGIN;
UPDATE account_balance
SET balance = 150
WHERE id = 1;
COMMIT;
```

**Điểm chính:** transaction A chưa kết thúc, nhưng SELECT thứ hai của A nhận snapshot của câu lệnh mới và thấy commit từ B.

### 5.4. Tác động lên UPDATE và SELECT FOR UPDATE

PostgreSQL có **quy tắc xử lý concurrent updates tinh tế hơn** plain SELECT. Một `UPDATE`/`DELETE`/`SELECT FOR UPDATE` có thể đợi transaction đã sửa hàng kết thúc, rồi **đánh giá lại điều kiện** trên phiên bản hàng mới nếu transaction kia commit. Vì thế không thể lấy “snapshot tại đầu statement” của `SELECT` thường rồi suy ra mọi DML chỉ tác động đúng dữ liệu nhìn thấy ở snapshot ban đầu.

Ví dụ:

```sql
UPDATE account_balance
SET balance = balance + 10
WHERE id = 1;
```

Khi có concurrent update cùng hàng, PostgreSQL cần đồng bộ row lock và tái xử lý cho nhất quán. Một phép cộng dạng SQL trên giá trị hiện hành thường khác về tính an toàn so với mẫu “đọc giá trị vào Java rồi ghi đè balance bằng một constant” ở transaction cạnh tranh.

**Nguồn:** [PostgreSQL 18 — Transaction Isolation](https://www.postgresql.org/docs/18/transaction-iso.html) và [SET TRANSACTION](https://www.postgresql.org/docs/18/sql-set-transaction.html).

## 6. Oracle Database: statement-level read consistency dựa trên SCN/undo

Oracle Database dùng cơ chế **multiversion read consistency**. Ở `READ COMMITTED`, Oracle xác định một mốc nhất quán, liên hệ tới **SCN** (*System Change Number*), tại thời điểm câu SQL được mở/bắt đầu. Nếu database đã có các thay đổi mới hơn mốc đó, Oracle có thể dùng **undo** để tái dựng phiên bản phù hợp cho câu SELECT.

```text
SELECT A mở ở SCN=1000
  -> đọc trạng thái được commit tính tới SCN 1000
Một transaction khác commit ở SCN=1001
  -> SELECT A đã mở không tự “nhảy” sang 1001
SELECT B mở sau đó ở SCN=1002
  -> có thể thấy thay đổi đã commit ở 1001
```

Vì mỗi SQL thường có mốc riêng ở READ COMMITTED:

- **Dirty read không xảy ra** trong truy vấn thông thường: A không thấy thay đổi chưa commit của B.
- **Non-repeatable read có thể xảy ra** giữa hai câu SELECT.
- **Phantom có thể xảy ra** giữa hai lần chạy truy vấn theo điều kiện.
- Một câu SELECT lâu có thể cần undo cũ để giữ read consistency; các lỗi liên quan tài nguyên undo có thể xuất hiện khi phiên bản cần thiết không còn khả dụng.

### Oracle không đồng nhất SERIALIZABLE với READ COMMITTED

Ở chế độ `SERIALIZABLE` hoặc một read-only transaction phù hợp, Oracle sử dụng snapshot mang tính **transaction-level** thay vì cấp một read view mới ở mỗi SELECT như READ COMMITTED. Không được so sánh chỉ bằng tên isolation level mà bỏ qua đặc điểm triển khai của từng engine.

### Gợi ý sử dụng trên Oracle

- Khi màn hình/report có nhiều SELECT phải phản ánh cùng một mốc, đừng mặc định READ COMMITTED đáp ứng chỉ vì mỗi SELECT riêng lẻ nhất quán.
- Nếu cần điểm nhìn ổn định cho một báo cáo, cân nhắc transaction mode thích hợp, read-only transaction, Flashback Query/SCN, hoặc tổ chức thành một câu SQL nếu nghiệp vụ cho phép; kiểm chứng tính phù hợp với Oracle version và tài nguyên undo.
- Tránh tự dùng transaction dài cho một quy trình có HTTP/queue wait, vì chi phí snapshot/lock và database resources có thể tăng.

**Nguồn:** [Oracle Database 19c — Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html).

## 7. MySQL/InnoDB: mỗi consistent read có read view mới ở READ COMMITTED

MySQL **InnoDB** sử dụng MVCC cho **consistent nonlocking reads**: một câu `SELECT` thường không khóa hàng mà đọc phiên bản dữ liệu phù hợp.

Điểm phân biệt cốt lõi:

- **`READ COMMITTED`:** mỗi consistent read tạo/dùng **fresh snapshot** riêng, kể cả khi chạy trong cùng một transaction.
- **`REPEATABLE READ`:** đây là isolation mặc định của **InnoDB** trong các cấu hình MySQL thông dụng; các consistent reads của một transaction chia sẻ snapshot thiết lập bởi **consistent read đầu tiên** của transaction.
- **Locking read** (`SELECT ... FOR UPDATE` hoặc `FOR SHARE`) và DML (`UPDATE`/`DELETE`) có xử lý lock/visibility khác plain consistent `SELECT`. Không dùng công thức “snapshot của SELECT” để kết luận cách DML hoạt động.
- InnoDB cho transaction thấy các thay đổi chính nó đã thực hiện, dù chúng chưa commit.

### 7.1. Khác biệt READ COMMITTED và REPEATABLE READ

```text
MySQL InnoDB, READ COMMITTED

T1: BEGIN
T1: SELECT row 7 -> 100        snapshot R1
T2: UPDATE row 7 -> 150; COMMIT
T1: SELECT row 7 -> 150        snapshot R2 (mới)
T1: COMMIT

MySQL InnoDB, REPEATABLE READ (consistent nonlocking SELECT)

T1: BEGIN
T1: SELECT row 7 -> 100        snapshot R1 được thiết lập
T2: UPDATE row 7 -> 150; COMMIT
T1: SELECT row 7 -> 100        vẫn dùng read view R1
T1: COMMIT
```

Đây là hai **kịch bản lý tưởng hóa** cho plain `SELECT`, không phải mô tả chung cho locking reads hoặc các transaction có cập nhật của chính mình.

### 7.2. Cú pháp quan sát

```sql
-- Có thể kiểm tra session MySQL đang dùng isolation nào:
SELECT @@transaction_isolation;

-- Thiết lập cho transaction tiếp theo trong session:
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

START TRANSACTION;
SELECT balance FROM account_balance WHERE id = 1;
-- Cho session khác UPDATE+COMMIT.
SELECT balance FROM account_balance WHERE id = 1;
COMMIT;
```

Tùy version/permission, lệnh `SET TRANSACTION` phải được gọi **trước khi transaction bắt đầu**. Kiểm tra cấu hình thực tế; không cho rằng database mặc định là READ COMMITTED — **MySQL InnoDB thường mặc định REPEATABLE READ**.

### 7.3. Tại sao SELECT FOR UPDATE không tương đương SELECT thường?

`SELECT ... FOR UPDATE` lấy lock đối với hàng đủ điều kiện, có thể chờ transaction khác và truy cập trạng thái hiện hành để phục vụ cập nhật. Nó **không được mô tả chính xác** bằng quy tắc “mỗi plain SELECT một snapshot” ở trên. Trên InnoDB, cách dùng index, range predicate, gap/next-key locking và isolation level ảnh hưởng lock behavior; ở READ COMMITTED, gap locking cho search/index scan thường được giảm bớt, trừ một số trường hợp như foreign-key/duplicate-key checks.

```sql
START TRANSACTION;

SELECT balance
FROM account_balance
WHERE id = 1
FOR UPDATE;

UPDATE account_balance
SET balance = balance - 10
WHERE id = 1;

COMMIT;
```

Đây là mẫu **đọc-để-ghi có lock**, khác với truy vấn báo cáo plain `SELECT`. Không dùng `FOR UPDATE` trên mọi query “để an toàn hơn”: nó có thể tăng contention/deadlock và ảnh hưởng throughput.

**Nguồn:** [MySQL 8.4 — InnoDB Consistent Nonlocking Reads](https://dev.mysql.com/doc/refman/8.4/en/innodb-consistent-read.html) và [Transaction Isolation Levels](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html).

## 8. SQL Server: READ COMMITTED có thể dựa trên locks hoặc row versions

Microsoft SQL Server phân biệt rõ hai **cách thực thi** của `READ COMMITTED` tùy cấu hình database `READ_COMMITTED_SNAPSHOT` (gọi tắt **RCSI**).

### 8.1. RCSI OFF: lock-based READ COMMITTED

Khi `READ_COMMITTED_SNAPSHOT = OFF` (mặc định ở nhiều bản SQL Server on-premises), READ COMMITTED sử dụng **shared locks** để tránh đọc hàng mà writer khác chưa commit. Shared lock ở mức row/page có thể được thả trong khi câu lệnh đang quét; vì vậy **không có bảo đảm một point-in-time snapshot nhất quán của toàn statement theo kiểu MVCC**.

Hệ quả có thể gồm:

- Reader phải **chờ** writer commit/rollback rồi mới đọc hàng mà writer đang khóa.
- Reader/writer có thể chặn nhau tùy lock granularity và query execution.
- Một lần scan có thể bị ảnh hưởng bởi thay đổi concurrent giữa quá trình duyệt, như hiện tượng missing/double reads trong một số tình huống scan.
- Hai câu SELECT riêng biệt đương nhiên có thể nhìn giá trị đã commit khác nhau.

`READ COMMITTED` vẫn ngăn **dirty reads**; tuy nhiên không nên diễn giải “ngăn dirty read” thành “một SELECT luôn là snapshot tại đầu câu lệnh”.

### 8.2. RCSI ON: statement-level row-versioned snapshot

Khi `READ_COMMITTED_SNAPSHOT = ON`, SQL Server dùng **row versions** để cung cấp **statement-level read consistency** cho READ COMMITTED. Một câu SELECT thường nhìn dữ liệu đã commit tại thời điểm statement bắt đầu, đồng thời vẫn có thể thấy kết quả write phù hợp của transaction mình.

```text
RCSI ON:
  SELECT #1 bắt đầu -> read snapshot S1
  Writer COMMIT
  SELECT #2 bắt đầu -> read snapshot S2

Hai SELECT trong cùng transaction vẫn có thể khác nhau.
```

**RCSI không đồng nghĩa isolation level SNAPSHOT.** SQL Server có một isolation level riêng tên `SNAPSHOT`, dùng transaction-level snapshot khi option `ALLOW_SNAPSHOT_ISOLATION` được bật và session yêu cầu level đó. Một database bật RCSI vẫn có thể có các transactions READ COMMITTED thấy snapshot **mới cho mỗi statement**.

### 8.3. Kiểm tra cấu hình thật

```sql
SELECT name, is_read_committed_snapshot_on,
       snapshot_isolation_state_desc
FROM sys.databases
WHERE name = DB_NAME();
```

Kết quả `is_read_committed_snapshot_on = 1` nghĩa là RCSI đang ON cho database hiện tại. `snapshot_isolation_state_desc` liên quan tính sẵn có của isolation `SNAPSHOT`, **không phải** cột thay thế cho RCSI.

Quản trị viên có thể bật RCSI theo quy trình thay đổi cấu hình database, ví dụ:

```sql
-- Lệnh quản trị minh họa: kiểm tra tác động hệ thống trước khi dùng.
ALTER DATABASE YourDatabase SET READ_COMMITTED_SNAPSHOT ON;
```

**Không chạy trên production chỉ để thử bài học**: thay đổi này ảnh hưởng hành vi đọc/locking và tài nguyên row version store, có thể đòi điều kiện kết nối và quyền quản trị. Trên Azure SQL Database, RCSI thường **ON mặc định**; trên SQL Server và Azure SQL Managed Instance, mặc định phổ biến là **OFF**. Luôn xem `sys.databases` thay vì suy đoán từ môi trường.

### 8.4. RCSI không phải “mọi lock biến mất”

Dù RCSI giúp plain reads không cần row/page shared locks cho dữ liệu đang đọc, vẫn có:

- Schema stability locks và các khóa cần thiết cho metadata/DDL.
- Locks cho writes, DML, constraints, locking hints như `UPDLOCK`/`HOLDLOCK`.
- Khả năng cập nhật xung đột, deadlock, lock wait trong những tình huống nhất định.
- Chi phí lưu/duy trì row versions và tempdb/persistent version store tùy cấu hình/phiên bản.

Không khuyên dùng `WITH (NOLOCK)` để “tạo snapshot”: `NOLOCK` tương ứng read-uncommitted-style hints, có thể gây **dirty read** và các bất thường nghiêm trọng. Nếu mục tiêu là giảm reader/writer blocking nhưng vẫn không đọc uncommitted, cần đánh giá RCSI, index/query patterns và phiên bản SQL Server.

**Nguồn:** [Microsoft Learn — Transaction Locking and Row Versioning Guide](https://learn.microsoft.com/en-us/sql/relational-databases/sql-server-transaction-locking-and-row-versioning-guide) và [SET TRANSACTION ISOLATION LEVEL](https://learn.microsoft.com/en-us/sql/t-sql/statements/set-transaction-isolation-level-transact-sql).

## 9. H2: dùng làm bài thực hành có kiểm soát, không thay thế mọi database

H2 hỗ trợ `READ COMMITTED` và mô tả đây là isolation mặc định, **không dirty read** nhưng có thể có **non-repeatable read/phantom read**. H2 dùng MVCC cho nhiều thao tác; khi connection A đọc và connection B chưa commit thay đổi, A nhìn phiên bản đã commit phù hợp và các thay đổi của chính mình.

Ví dụ ở phần 12 dùng H2 để kiểm chứng **hai câu SELECT trong cùng transaction nhận hai giá trị khác nhau** sau khi writer khác commit. Đây là hiện tượng được READ COMMITTED cho phép và H2 có thể tái hiện; không coi đó là bằng chứng H2 giống hoàn toàn PostgreSQL/Oracle/InnoDB/SQL Server về locking, undo, gap locks hay snapshot strategy.

Điều đáng chú ý:

- H2 DDL có thể tự commit transaction. Hãy **tạo bảng và seed dữ liệu trước** khi bắt đầu test transaction, thay vì tạo bảng giữa demo để phán đoán rollback.
- H2 cũng hỗ trợ các isolation levels khác, nhưng ý nghĩa và độ mạnh thực tế không nhất thiết trùng PostgreSQL hay Oracle. Tài liệu H2 có các cảnh báo triển khai đối với `SERIALIZABLE`.
- Connection pool, JDBC version và test harness vẫn ảnh hưởng hành vi; dùng H2 để **học**, rồi chạy integration test bằng database/driver production để xác nhận chất lượng nghiệp vụ.

**Nguồn:** [H2 — Advanced: Transaction Isolation](https://h2database.com/html/advanced.html).

## 10. Bảng tổng hợp “READ_COMMITTED nhìn ảnh chụp nào?”

| Database / chế độ | READ COMMITTED dùng gì cho plain SELECT? | Thời điểm snapshot/read view | Điều bắt buộc nhớ |
| --- | --- | --- | --- |
| **PostgreSQL** | MVCC | Snapshot mới tại lúc **mỗi command bắt đầu** | SELECT kế tiếp có thể thấy commit mới; UPDATE/SELECT FOR UPDATE có recheck/lock semantics. |
| **Oracle Database** | MVCC/read consistency với undo/SCN | Mốc **statement** ở READ COMMITTED | Một statement nhất quán; statement kế tiếp có mốc mới. |
| **MySQL InnoDB** | MVCC consistent nonlocking read | Read view mới ở **mỗi consistent read** khi READ COMMITTED | Default InnoDB thường REPEATABLE READ; locking reads và DML có quy tắc khác. |
| **SQL Server RCSI ON** | Row versioning | Snapshot **đầu mỗi statement** | `READ_COMMITTED_SNAPSHOT=ON` khác isolation `SNAPSHOT`. |
| **SQL Server RCSI OFF** | Shared locks | **Không có point-in-time statement MVCC snapshot được bảo đảm** | Ngăn dirty read nhưng reader/writer có thể block, scan có thể không nhất quán tại một mốc. |
| **H2** | MVCC theo engine H2 | Hành vi RC cho phép đọc committed mới giữa hai statement | Dùng demo RC; không đồng nhất mọi chi tiết engine với production. |

Bảng này mô tả **plain read** trên transaction có READ COMMITTED. Khi thêm locking read, stored procedure, DDL, UDF, database hints, mixed DML hoặc các driver/connection-specific configurations, quy tắc chính xác có thể khác.

### Hai tầng câu hỏi cần đặt khi đọc code

1. **“Transaction của tôi đang có isolation gì?”** Trong Spring/JDBC, kiểm tra annotation, transaction manager, JDBC connection và database default thực tế.
2. **“Database engine thực thi level đó bằng cách nào?”** Kiểm tra PostgreSQL/Oracle/InnoDB/SQL Server RCSI và loại câu SQL.

Chỉ trả lời câu 1 mà bỏ qua câu 2 dẫn đến nhận định sai về blocking và statement consistency.

## 11. Spring Framework: `@Transactional(isolation = READ_COMMITTED)`

Trong Spring, dùng:

```java
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(isolation = Isolation.READ_COMMITTED)
public void calculateAccountStatus() {
    // Các câu SQL qua JdbcTemplate/repository.
}
```

`Isolation.READ_COMMITTED` ánh xạ tới transaction isolation tương ứng của transaction resource/manager (với JDBC là `Connection.TRANSACTION_READ_COMMITTED`). Tuy nhiên:

1. Spring **không tự xây dựng MVCC snapshot**. Database engine quyết định statement visibility và lock strategy.
2. Annotation phải được transaction interceptor thực sự áp dụng — ví dụ caller gọi **Spring-managed bean qua proxy** trong proxy mode, không `new Service()` hay `this.method()`.
3. Isolation được thiết lập cho **transaction mới** do method bắt đầu (`REQUIRED` khi chưa có transaction, hoặc `REQUIRES_NEW`). Khi method chỉ **tham gia** transaction đã có, khai báo isolation ở inner method **không tự thay đổi** isolation của physical transaction ngoài.
4. `Isolation.DEFAULT` là mặc định annotation: dùng mức isolation mặc định của underlying data source/database. PostgreSQL thường default READ COMMITTED, MySQL InnoDB thường default REPEATABLE READ, SQL Server default READ COMMITTED nhưng RCSI có thể ON/OFF.
5. Transaction manager, driver hoặc database có thể **không hỗ trợ** một isolation level cụ thể, hoặc có ngoại lệ khi thiết lập. Đừng coi tên enum là bảo đảm cùng consistency semantics ở mọi engine.
6. Với nhiều datasource/transaction managers, phải xác định annotation thuộc manager/resource nào; một annotation đơn lẻ không thiết lập cùng một snapshot cho mọi database.

### 11.1. `REQUIRED` tham gia giao dịch hiện có

```java
@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public void outer() {
        inner.readCommittedMethod();
    }
}

@Service
class InnerService {
    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void readCommittedMethod() {
        // REQUIRED mặc định, tham gia transaction outer có sẵn.
    }
}
```

Đây là **trích đoạn**, cần import `@Service`, `@Transactional` và `Isolation`. Với cùng transaction manager/resource, inner `REQUIRED` **tham gia physical transaction của outer**; thông thường không hạ isolation T1 từ REPEATABLE_READ xuống READ_COMMITTED. Một số manager cho phép `setValidateExistingTransaction(true)` để **từ chối** isolation mismatch, thay vì âm thầm sử dụng isolation hiện tại.

Nếu cần một transaction độc lập với isolation READ_COMMITTED riêng:

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.READ_COMMITTED
)
public void independentRead() {
    // Transaction mới, isolation mới theo manager và DB.
}
```

Cần import `Propagation`. `REQUIRES_NEW` tạo physical transaction riêng, có thể sử dụng connection riêng và commit/rollback độc lập, nên **không nên dùng chỉ để "ép isolation"** nếu nghiệp vụ phải atomic cùng outer.

### 11.2. JDBC và DataSource

Với `JdbcTransactionManager`/`DataSourceTransactionManager`, Spring chuẩn bị một connection từ `DataSource`, áp dụng isolation được yêu cầu khi bắt đầu transaction phù hợp, và cố khôi phục trạng thái connection khi kết thúc transaction.

```text
Caller -> Spring proxy -> transaction manager
                           |
                           +--> DataSource/Connection
                                setTransactionIsolation(READ_COMMITTED)
                                BEGIN/autoCommit=false
                           |
                           +--> JdbcTemplate sử dụng connection đã bind
                           |
                           +--> COMMIT hoặc ROLLBACK
                           |
                           +--> reset connection state/trả về pool
```

Đây là sơ đồ khái quát, không phải thứ tự mọi JDBC driver ghi log chính xác. Nếu code tự mở `dataSource.getConnection()` không qua transaction-aware mechanism rồi chạy SQL, câu query đó có thể dùng **connection khác**, không tham gia Spring transaction đang bind vào thread. Ưu tiên `JdbcTemplate`, repository/framework tích hợp hoặc `DataSourceUtils` khi làm JDBC mức thấp.

### 11.3. `readOnly=true` không tạo transaction-level snapshot

```java
@Transactional(
    isolation = Isolation.READ_COMMITTED,
    readOnly = true
)
public Report readReport() {
    // ...
}
```

Đây là signature minh họa; `Report` là kiểu ứng dụng. `readOnly=true` là metadata/hint có thể tác động tối ưu hóa và connection/resource, nhưng **không tự nâng isolation** hay “đóng băng” một snapshot cho toàn transaction. Hai SELECT của report vẫn có thể thấy committed data khác nhau ở READ COMMITTED.

Muốn báo cáo nhiều truy vấn nhất quán theo cùng một mốc cần xác định tính nhất quán yêu cầu, đặc điểm database và isolation thích hợp. Không chỉ thêm `readOnly=true` rồi kỳ vọng snapshot cố định.

### 11.4. Self-invocation và test infrastructure

```java
@Transactional(isolation = Isolation.READ_COMMITTED)
public void readInIsolation() { }

public void callLocal() {
    readInIsolation(); // self-invocation, bỏ qua Spring proxy mode.
}
```

Đây là trích đoạn. Nếu `callLocal()` không được intercept và không có transaction bên ngoài, annotation `READ_COMMITTED` của `readInIsolation()` **không có tác dụng** qua lời gọi này. Nếu test method có `@Transactional` do Spring TestContext mở, service có thể đang tham gia **test-managed transaction**, khiến phép thử isolation không đo đúng boundary mong muốn.

## 12. Dự án Java 17 runnable: hai transaction và hai snapshot

**Mục đích:** chứng minh một method Spring `@Transactional(isolation = READ_COMMITTED)` có thể gọi **hai SELECT** cùng hàng và nhận **hai giá trị khác nhau**, vì một transaction khác đã commit giữa hai câu SELECT.

Để kết quả có ý nghĩa, code **không dùng `Thread.sleep` để đoán thời điểm**. Nó dùng `CountDownLatch` và hai executor threads, buộc lịch trình:

1. Reader transaction T1 bắt đầu, đọc `balance = 100`, phát tín hiệu đã đọc.
2. Writer transaction T2 chờ tín hiệu, cập nhật balance thành 150, commit, sau đó báo commit hoàn tất.
3. Reader T1 **vẫn đang mở** và sau khi biết T2 commit, đọc lại: `balance = 150`.
4. Runner đợi cả hai hoàn thành và đọc lại DB: `final = 150`.

**Đây là hai transactions độc lập trên hai threads**, không dùng thread khác để “chia sẻ” T1. Spring imperative transaction gắn với context của thread; mỗi bean method được gọi qua proxy ở thread của chính nó.

### 12.1. Project tree

```text
read-committed-snapshot-demo/
├── pom.xml
└── src/main/
    ├── java/vn/example/isolation/
    │   ├── IsolationApplication.java
    │   ├── ReaderService.java
    │   └── WriterService.java
    └── resources/
        └── application.properties
```

JDK yêu cầu **Java 17 trở lên**; Maven 3.9+ là lựa chọn phù hợp. Không cần cài H2 server.

### 12.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>vn.example</groupId>
    <artifactId>read-committed-snapshot-demo</artifactId>
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

Spring JDBC starter mang `JdbcTemplate`, HikariCP và Spring transaction infrastructure. Bean transaction manager được định nghĩa tường minh trong main application, để không phải suy đoán từ auto-configuration.

### 12.3. `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:read_committed_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

# Reader T1 và writer T2 cần hai physical connections đồng thời.
spring.datasource.hikari.maximum-pool-size=3
```

`DB_CLOSE_DELAY=-1` cho phép H2 in-memory tồn tại trong JVM khi các connections từ pool được trả về. Pool có 3 connections giúp hai threads có connection độc lập mà không tranh chấp việc *lấy* connection. Đây là setting demo, không phải sizing rule production.

### 12.4. `src/main/java/vn/example/isolation/ReaderService.java`

```java
package vn.example.isolation;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReaderService {

    private final JdbcTemplate jdbc;

    public ReaderService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(
        isolation = Isolation.READ_COMMITTED,
        readOnly = true
    )
    public String readTwice(
            CountDownLatch firstReadDone,
            CountDownLatch writerCommitted
    ) throws InterruptedException {

        int first = jdbc.queryForObject(
            "SELECT balance FROM account_balance WHERE id = 1",
            Integer.class
        );

        firstReadDone.countDown();

        if (!writerCommitted.await(10, TimeUnit.SECONDS)) {
            throw new IllegalStateException(
                "Writer did not commit within 10 seconds"
            );
        }

        int second = jdbc.queryForObject(
            "SELECT balance FROM account_balance WHERE id = 1",
            Integer.class
        );

        return "reader.first=" + first
            + "\nreader.second=" + second;
    }
}
```

**Giải thích:**

- `@Transactional` trên public method Spring-managed bean, được caller gọi qua proxy, bắt đầu **một T1** cho cả hai `SELECT`.
- `Isolation.READ_COMMITTED` yêu cầu JDBC transaction READ COMMITTED.
- `readOnly=true` thể hiện T1 chỉ đọc; **nó không biến T1 thành transaction snapshot cố định**.
- `firstReadDone.countDown()` cho biết T1 đã lấy giá trị đầu tiên.
- `writerCommitted.await(...)` chờ writer **hoàn thành commit** trước khi T1 chạy `SELECT` lần hai. Thời hạn 10 giây chỉ là timeout của **test coordination**, không phải transaction timeout.
- Hai `SELECT` cùng chạy trong method/T1, nên khác biệt giá trị là do isolation/commit visibility, không phải vì reader khởi tạo T1 mới.

Method có checked `InterruptedException` để ví dụ Java compile; trong chạy bình thường không có interrupt. Nếu ứng dụng bị interrupt trong test coordination, phải xử lý lỗi theo chính sách rollback/cleanup phù hợp; ở đây không có DML của reader nên phần minh họa không phụ thuộc checked-exception rollback rules.

### 12.5. `src/main/java/vn/example/isolation/WriterService.java`

```java
package vn.example.isolation;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WriterService {

    private final JdbcTemplate jdbc;

    public WriterService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void addFifty() {
        jdbc.update(
            "UPDATE account_balance SET balance = balance + 50 " +
            "WHERE id = 1"
        );
    }
}
```

Writer chạy trong **T2 trên thread khác**, được Spring proxy intercept và commit khi `addFifty()` trả về bình thường. `UPDATE balance = balance + 50` là phép cập nhật ngay trong SQL, tránh bài toán ghi đè một giá trị stale được tính trước ở Java.

### 12.6. `src/main/java/vn/example/isolation/IsolationApplication.java`

```java
package vn.example.isolation;

import java.util.concurrent.CountDownLatch;
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
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement(proxyTargetClass = true)
public class IsolationApplication {

    public static void main(String[] args) {
        SpringApplication.run(IsolationApplication.class, args);
    }

    @Bean
    JdbcTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner demo(
            JdbcTemplate jdbc,
            ReaderService readerService,
            WriterService writerService
    ) {
        return args -> {
            // DDL và dữ liệu mẫu được tạo TRƯỚC hai transactions.
            jdbc.execute(
                "CREATE TABLE account_balance (" +
                "id INT PRIMARY KEY, balance INT NOT NULL)"
            );
            jdbc.update(
                "INSERT INTO account_balance(id, balance) VALUES (1, 100)"
            );

            CountDownLatch firstReadDone = new CountDownLatch(1);
            CountDownLatch writerCommitted = new CountDownLatch(1);
            ExecutorService pool = Executors.newFixedThreadPool(2);

            try {
                Future<String> reader = pool.submit(
                    () -> readerService.readTwice(
                        firstReadDone, writerCommitted
                    )
                );

                Future<?> writer = pool.submit(() -> {
                    if (!firstReadDone.await(10, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                            "Reader did not read within 10 seconds"
                        );
                    }

                    // Trả về từ proxy method nghĩa là commit T2 đã xong.
                    writerService.addFifty();
                    writerCommitted.countDown();
                    return null;
                });

                writer.get(15, TimeUnit.SECONDS);
                System.out.println(reader.get(15, TimeUnit.SECONDS));

                int committed = jdbc.queryForObject(
                    "SELECT balance FROM account_balance WHERE id = 1",
                    Integer.class
                );
                System.out.println("final=" + committed);
            } finally {
                // Nếu writer gặp lỗi, không để reader chờ vô hạn.
                writerCommitted.countDown();
                pool.shutdownNow();
            }
        };
    }
}
```

**Vì sao mã này kiểm chứng đúng?**

1. `CommandLineRunner` không có transaction bọc toàn bộ; service methods mới là các transaction boundaries.
2. `@EnableTransactionManagement(proxyTargetClass=true)` và constructor injection bảo đảm các Spring-managed service methods có thể được gọi qua proxy.
3. T1 và T2 ở **hai threads khác nhau**, mỗi thread có transaction context JDBC riêng.
4. `writerService.addFifty()` chỉ trả về sau khi Spring transaction interceptor hoàn tất commit T2, rồi mới `writerCommitted.countDown()`. Vì vậy reader thứ hai không chạy sớm hơn commit của writer trong lịch trình bình thường.
5. `reader.readTwice(...)` là **một lời gọi method**, tức một T1 xuyên suốt cả hai SELECT; không phải hai transaction khác nhau.
6. H2 READ COMMITTED có thể thấy committed version mới ở lần đọc sau, phù hợp với đặc tả và tài liệu H2.
7. Kết quả được in **theo thứ tự cố định** sau khi main thread chờ `Future`, không phụ thuộc thứ tự log của hai threads.

Nếu thread nào lỗi, `Future.get` sẽ báo exception; code không in kết quả “thành công” giả. Latch có timeout để giảm nguy cơ bài thử bị treo vô hạn; đây không phải phương án tối ưu cho production nhưng là phép thử concurrency dễ đọc.

### 12.7. Build và chạy

```bash
java -version
mvn -version
mvn -q package
java -jar target/read-committed-snapshot-demo-1.0.0.jar
```

**Các dòng do chính code ví dụ chủ động in** khi chạy đúng trên Java 17, Spring Boot 3.5.7, H2 và cấu hình trên:

```text
reader.first=100
reader.second=150
final=150
```

Spring Boot và HikariCP có thể in thêm log khởi động/shutdown. Ba dòng trên mô tả kết quả nghiệp vụ dự kiến của chương trình, không bao gồm log framework.

### 12.8. Tại sao giá trị thứ hai là 150?

- Reader T1 bắt đầu trước, `SELECT #1` lấy `100`.
- Writer T2 chỉ chạy update khi đã nhận latch xác nhận lần đọc thứ nhất.
- Writer thay giá trị thành `150` rồi **commit** trước khi báo latch cho reader.
- Reader T1 vẫn mở ở READ_COMMITTED nên `SELECT #2` đọc committed data mới và có thể thấy `150`.
- Không có dirty read, vì `150` chỉ được reader nhìn **sau commit T2**.
- Hành vi này là một **non-repeatable read được READ_COMMITTED cho phép**, không phải Spring tạo snapshot mới bằng Java; H2/JDBC thực thi quyết định read view.

### 12.9. Đổi REPEATABLE_READ thì sao?

Nếu thay annotation của ReaderService thành:

```java
@Transactional(
    isolation = Isolation.REPEATABLE_READ,
    readOnly = true
)
public String readTwice(...) {
    // Chỉ là chữ ký minh họa; giữ thân method cũ.
}
```

Đây là **trích đoạn signature**, dấu `...` không phải mã Java độc lập. Không tự khẳng định kết quả của mọi database: PostgreSQL, InnoDB, H2 và SQL Server có triển khai/giới hạn mức cô lập khác nhau. Muốn so sánh, cần build chạy lại với database cụ thể, cố định lịch trình và xác nhận khả năng JDBC driver hỗ trợ.

Trong PostgreSQL và plain consistent reads của InnoDB ở REPEATABLE READ, hai SELECT thông thường có xu hướng dùng snapshot nhất quán của transaction; với SQL Server `REPEATABLE READ` có thể dùng locks khác kiểu transaction-level MVCC snapshot. **Tên level không đủ kết luận cơ chế**.

## 13. READ_COMMITTED và bài toán mất cập nhật

Một lỗi phổ biến là nhìn thấy READ_COMMITTED không dirty read rồi kết luận “mọi cập nhật đều an toàn”.

Giả sử hai request cùng đọc `balance=100`:

```text
T1 SELECT balance -> 100
T2 SELECT balance -> 100
T1 tự tính 100 + 10 = 110
T2 tự tính 100 + 20 = 120
T1 UPDATE balance = 110; COMMIT
T2 UPDATE balance = 120; COMMIT
Kết quả 120, thay vì 130 nếu hai phép cộng phải được tích lũy.
```

Đây là kịch bản **read-modify-write với giá trị tính trong ứng dụng**. Database có thể khóa hàng/đợi và có các khác biệt conflict handling, nhưng mẫu ghi đè stale value có nguy cơ **lost update** nếu không có cơ chế bổ sung.

Các cách phòng ngừa tùy yêu cầu:

- Gộp phép toán vào một DML nguyên tử: `UPDATE account_balance SET balance = balance + 10 WHERE id = 1`. DB thực thi row-update locking/concurrency phù hợp.
- **Optimistic locking** với cột version: `UPDATE ... SET balance=?, version=version+1 WHERE id=? AND version=?`, kiểm tra affected row count; nếu 0 thì retry có giới hạn hoặc báo conflict.
- **Pessimistic locking** với `SELECT ... FOR UPDATE` ở những engine hỗ trợ và khi cần serialize critical section.
- Chọn isolation mạnh hơn như transaction-level snapshot hoặc SERIALIZABLE **khi đúng tính chất nghiệp vụ** và đã thử xung đột/retry thực tế. Lưu ý mỗi engine định nghĩa/triển khai hơi khác.

`READ_COMMITTED` không thay thế database constraints, unique keys, optimistic versions hay quản lý race conditions.

## 14. Nhiều query trong cùng một service có thể cho dữ liệu không nhất quán về nghiệp vụ

Đặt ví dụ doanh thu:

```text
T1, READ_COMMITTED:
  SELECT SUM(amount) FROM invoices WHERE status='PAID'   -> 1,000
T2:
  cập nhật/inserts invoice rồi COMMIT
T1:
  SELECT COUNT(*) FROM invoices WHERE status='PAID'      -> 12
```

Cả hai số có thể đúng tại **hai mốc** khác nhau. Nếu kết hợp thành một tỷ lệ trung bình, báo cáo có thể tạo ra một “ảnh tổng hợp” không tồn tại nguyên vẹn ở một thời điểm.

Giải pháp tùy nghiệp vụ:

1. **Một câu SQL:** khi tính SUM/COUNT trên cùng tập dữ liệu trong **cùng statement** ở engine có statement snapshot, hai aggregate cùng nhìn một mốc hợp lý. Ví dụ:
   `SELECT COUNT(*), SUM(amount) FROM invoices WHERE status='PAID'`.
2. **Transaction-level stable read:** chọn cơ chế phù hợp của DB để các queries đọc chung một snapshot khi cần.
3. **Materialized/read model:** duy trì bảng/bản tổng hợp với chính sách cập nhật nhất quán.
4. **Định nghĩa eventual consistency:** nếu dashboard chấp nhận sai lệch nhỏ, quy định rõ SLA/độ trễ thay vì đòi mọi báo cáo có global snapshot.

Đặc biệt, trong **SQL Server RCSI OFF**, gom vào một SQL chưa bảo đảm point-in-time snapshot theo MVCC; phải xác nhận consistency requirements và thiết kế query/isolation tương ứng.

## 15. Kịch bản kiểm thử hai session cho production database

Trước khi thay đổi isolation trên hệ thống thật, hãy thử trong database riêng/staging với ít dữ liệu và hai connections có ID rõ ràng.

### Test A — không dirty read

1. T1 ở READ_COMMITTED đọc `value=100`.
2. T2 UPDATE thành `150` nhưng **chưa commit**.
3. T1 chạy SELECT trong lúc T2 chưa commit:
   - Với MVCC plain reads, T1 có thể thấy `100`.
   - Với SQL Server locking READ COMMITTED, T1 có thể **block** chờ T2.
4. T2 ROLLBACK; T1 phải không nhận một “giá trị đã commit” là `150` từ T2.

**Không khẳng định mọi engine trả về ngay khi writer chưa commit**: mục tiêu là ngăn dirty read, không phải bắt buộc nonblocking.

### Test B — non-repeatable read

1. T1 READ_COMMITTED SELECT id=1, ghi kết quả `100`.
2. T2 UPDATE id=1 thành `150` và COMMIT.
3. T1 SELECT lại id=1, ghi `150` nếu engine/kiểu đọc hỗ trợ hành vi đó.
4. Xác nhận lần thứ hai bắt đầu **sau** COMMIT của T2.
5. T1 COMMIT; kiểm tra isolation và transaction boundary thực sự, không chỉ SQL string.

### Test C — phantom read

1. T1 SELECT COUNT trên điều kiện cố định.
2. T2 INSERT một hàng phù hợp và COMMIT.
3. T1 SELECT COUNT lại; nếu kết quả tăng, đó là phantom.
4. Kiểm tra index, locking hints hoặc isolation thực tế nếu kết quả bị chặn/không giống kỳ vọng.

### Test D — consistency của một SELECT dài

1. Tạo tập dữ liệu đủ lớn cho một SQL truy vấn có kiểm soát.
2. Bắt đầu query T1; để T2 commit thay đổi giữa lúc T1 đang đọc.
3. So sánh kết quả giữa PostgreSQL/Oracle/InnoDB consistent reads, SQL Server RCSI ON và OFF.
4. Tránh suy ra consistency từ một lần chạy đơn lẻ — query plan, index scan, locks và thời điểm commit làm kết quả khác nhau.
5. Với SQL Server RCSI OFF, kiểm tra **không có snapshot statement MVCC**, nên cần mô hình test cụ thể để quan sát possible missing/double reads, không hứa hiện tượng luôn tái hiện.

### Test E — Spring test boundary

Đặt transaction boundary trên public service bean. Gọi qua Spring proxy; tránh test method đã có `@Transactional` bên ngoài làm service join transaction khác. Đọc/ghi qua cùng transaction manager/DataSource. Sử dụng two-thread latch/real database như demo để kiểm soát lịch trình, không chỉ chèn `Thread.sleep` rồi hi vọng race đúng lúc.

## 16. Checklist cấu hình và vận hành READ_COMMITTED

- [ ] Đã xác minh **isolation level thực tế của JDBC connection**, không suy ra từ tên framework.
- [ ] Đã phân biệt `Isolation.DEFAULT` và `Isolation.READ_COMMITTED`.
- [ ] Với Spring, `@Transactional` có hiệu lực qua proxy và **bắt đầu transaction mới** nếu cần đặt isolation.
- [ ] Inner `REQUIRED` không mặc nhiên đổi isolation của outer transaction đang có.
- [ ] Đã xác định DB engine/version: PostgreSQL, Oracle, MySQL/InnoDB, SQL Server hay H2.
- [ ] Với SQL Server, kiểm tra `sys.databases.is_read_committed_snapshot_on`; RCSI ON/OFF thay đổi read behavior.
- [ ] Với MySQL, phân biệt consistent `SELECT` với locking reads và xác minh session default thường REPEATABLE READ.
- [ ] Với PostgreSQL, phân biệt plain SELECT snapshot và concurrent-update recheck của UPDATE/DELETE/FOR UPDATE.
- [ ] Với Oracle, hiểu SCN/undo statement consistency và tài nguyên undo cho query dài.
- [ ] Không nhầm **statement-level snapshot** với snapshot cố định của **cả transaction**.
- [ ] Đã đánh giá non-repeatable read và phantom read có làm sai nghiệp vụ hoặc báo cáo nhiều-query không.
- [ ] Dùng constraints/optimistic locking/row locking/atomic DML để ngăn stale write khi cần.
- [ ] Không dùng `NOLOCK` như biện pháp tạo snapshot nhất quán.
- [ ] Database/query/driver được kiểm thử trong môi trường phù hợp, không mặc định H2 đại diện mọi engine.
- [ ] Có retry có giới hạn khi transaction gặp deadlock, serialization failure, update conflict ở mức isolation/DB đã chọn.
- [ ] Chú ý connection pool, long-running transactions, version/undo store và transaction timeouts.

## 17. Câu hỏi tự kiểm tra

**Câu 1.** Hai SELECT trong một transaction Spring có `@Transactional(isolation=READ_COMMITTED)` lần lượt thấy `100` và `150` sau khi transaction khác commit. Có sai isolation không?

**Đáp án:** Không. `READ_COMMITTED` cho phép non-repeatable read. Với database dùng fresh statement snapshot/consistent read, đây là hành vi bình thường.

**Câu 2.** `READ_COMMITTED` có bảo đảm cả transaction nhìn cùng một ảnh chụp không?

**Đáp án:** Không. Nó ngăn dirty reads nhưng không bảo đảm transaction-level snapshot.

**Câu 3.** PostgreSQL READ COMMITTED và SQL Server RCSI OFF có phải cùng một cách thực thi?

**Đáp án:** Không. PostgreSQL plain SELECT dùng MVCC snapshot theo statement; SQL Server RCSI OFF dùng shared locks và **không hứa point-in-time MVCC statement snapshot**.

**Câu 4.** SQL Server RCSI ON khác SNAPSHOT isolation như thế nào?

**Đáp án:** RCSI ON ở READ COMMITTED cung cấp row-versioned **statement-level** snapshot; isolation `SNAPSHOT` riêng hướng tới **transaction-level** snapshot và cần option/config tương ứng.

**Câu 5.** MySQL InnoDB plain SELECT ở REPEATABLE READ và READ COMMITTED khác nhau ra sao?

**Đáp án:** READ COMMITTED có fresh read view cho từng consistent read; REPEATABLE READ dùng read view thiết lập bởi consistent read đầu tiên của transaction cho các consistent reads tiếp theo, với các ngoại lệ cho locking reads và chính transaction writes.

**Câu 6.** Trong Spring, inner `@Transactional(isolation=READ_COMMITTED)` có tự chuyển outer T1 đang REPEATABLE_READ sang READ_COMMITTED không?

**Đáp án:** Không nếu inner chỉ tham gia T1 do default `REQUIRED`. Isolation là thuộc tính của physical transaction khi nó được bắt đầu.

**Câu 7.** Dùng `readOnly=true` ở READ_COMMITTED có giúp các SELECT trong cùng transaction nhìn một snapshot duy nhất không?

**Đáp án:** Không phải bảo đảm của Spring. Cần isolation/database transaction mode phù hợp nếu nghiệp vụ thật sự cần transaction-level consistency.

**Câu 8.** Đang dùng SQL Server, query bị block ở READ COMMITTED. Có nên thêm `NOLOCK` vào mọi query không?

**Đáp án:** Không. `NOLOCK` có thể đọc uncommitted và gây bất thường. Trước hết kiểm tra RCSI, index/query plan, lock contention và yêu cầu consistency.

**Câu 9.** Một report đọc số tiền tổng và số lượng đơn trong hai SELECT, dữ liệu thay đổi giữa hai câu. Có nên mong hai kết quả cùng mốc không?

**Đáp án:** Không khi chỉ dùng READ COMMITTED. Với engine có statement snapshot, có thể gom vào một SQL hoặc dùng transaction-level consistent read theo nhu cầu.

## Tài liệu chính thức để kiểm chứng

1. **PostgreSQL 18** — [Transaction Isolation](https://www.postgresql.org/docs/18/transaction-iso.html), [SET TRANSACTION](https://www.postgresql.org/docs/18/sql-set-transaction.html): snapshot tại mỗi statement ở READ COMMITTED, non-repeatable reads, UPDATE recheck.
2. **Oracle Database** — [Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html): SCN, undo, statement-level read consistency.
3. **MySQL InnoDB 8.4** — [Consistent Nonlocking Reads](https://dev.mysql.com/doc/refman/8.4/en/innodb-consistent-read.html), [Transaction Isolation Levels](https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html): fresh read view ở READ COMMITTED, REPEATABLE READ mặc định và locking reads.
4. **Microsoft SQL Server** — [Transaction Locking and Row Versioning Guide](https://learn.microsoft.com/en-us/sql/relational-databases/sql-server-transaction-locking-and-row-versioning-guide), [SET TRANSACTION ISOLATION LEVEL](https://learn.microsoft.com/en-us/sql/t-sql/statements/set-transaction-isolation-level-transact-sql): RCSI ON/OFF, shared locks, statement vs transaction snapshots.
5. **H2 Database** — [Advanced: Transaction Isolation](https://h2database.com/html/advanced.html): READ COMMITTED và MVCC dùng trong bài thực hành.
6. **Spring Framework** — [Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html), [Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): isolation metadata, transaction proxy, REQUIRED vs REQUIRES_NEW.

**Kết luận:** `READ_COMMITTED` ngăn **dirty reads** nhưng thường vẫn cho phép dữ liệu giữa các statement của **cùng transaction** thay đổi khi transaction khác commit. “Ảnh chụp mới theo statement” mô tả PostgreSQL, Oracle, consistent reads của InnoDB ở READ COMMITTED và SQL Server khi **RCSI ON**; SQL Server khi **RCSI OFF** ngăn dirty reads chủ yếu bằng locks, không phải ảnh chụp MVCC theo statement. Trong Spring, `Isolation.READ_COMMITTED` là yêu cầu gửi đến **transaction manager và database** khi bắt đầu transaction thích hợp, không phải thuật toán snapshot chạy trong Java.
