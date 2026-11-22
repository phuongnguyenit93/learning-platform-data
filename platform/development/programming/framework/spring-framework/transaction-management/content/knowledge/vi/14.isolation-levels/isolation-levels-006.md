# REPEATABLE_READ và những khác biệt triển khai MVCC trong Spring Transaction Management

## 1. Mục tiêu và câu trả lời ngắn

Trong Spring Framework, bạn có thể yêu cầu mức cô lập **`Isolation.REPEATABLE_READ`** cho một transaction. Ý nghĩa tối thiểu theo mô hình cô lập SQL là: khi một giao dịch đọc lại **cùng hàng đã đọc**, nó không được bất ngờ thấy phiên bản khác do một giao dịch đồng thời đã commit. Nhưng câu lệnh SQL đó chạy trên **PostgreSQL, MySQL/InnoDB, SQL Server, Oracle hay H2** có thể có hành vi khác nhau về snapshot, phantom read, locking read, xung đột ghi và chi phí tài nguyên.

Bài Knowledge này giải thích:

- Dirty read, non-repeatable read, phantom read và serialization anomaly, đặc biệt sự khác nhau giữa **đọc lại cùng hàng** và **đọc lại cùng tập kết quả theo điều kiện**.
- Cơ chế **MVCC — Multi-Version Concurrency Control**: nhiều phiên bản một hàng, transaction snapshot/read view, đọc thay đổi của chính mình, duy trì phiên bản cũ và kiểm tra xung đột khi ghi.
- Những khác biệt thực tế giữa PostgreSQL `REPEATABLE READ`, InnoDB `REPEATABLE READ`, SQL Server `REPEATABLE READ`, Oracle và H2.
- Cấu hình `@Transactional(isolation = Isolation.REPEATABLE_READ)` trong Spring và những điều annotation **không** bảo đảm.
- Một demo Java 17 + Spring JDBC + H2 chạy được để kiểm tra read consistency, kèm hai transaction khác nhau; bài tập/SQL timeline để xác nhận hành vi trên database thực.
- Các sai lầm về write skew, read-modify-write, locking read, JPA first-level cache, transaction dài và chính sách retry.

**Quy tắc cốt lõi:** tên isolation level mô tả **một tập cam kết và API yêu cầu**, không phải một thuật toán concurrency control bắt buộc cho tất cả database. “REPEATABLE_READ” **không đồng nghĩa** “toàn bộ hành vi luôn là snapshot isolation”, **không đồng nghĩa** “không có phantom trong mọi hệ quản trị”, và **không đồng nghĩa** “đảm bảo serializable”.

## 2. Trước hết: transaction và bốn loại anomaly

Một **transaction** là một đơn vị công việc DB được commit hoặc rollback. Mức cô lập (isolation level) định nghĩa mức độ một transaction có thể quan sát/ảnh hưởng các transaction đồng thời. Hãy đặt hai transaction **T1** và **T2** chạy trên hai database connections độc lập.

| Hiện tượng | Minh họa | REPEATABLE_READ tối thiểu theo SQL |
|---|---|---|
| **Dirty read** | T1 đọc giá trị T2 vừa ghi nhưng T2 **chưa commit**, sau đó T2 rollback | Không được xảy ra |
| **Non-repeatable read** | T1 đọc hàng A = 100; T2 sửa A = 120 rồi commit; T1 đọc lại hàng A thấy 120 | **Không được xảy ra** |
| **Phantom read** | T1 `SELECT ... WHERE amount >= 100` có 3 hàng; T2 chèn hàng thỏa điều kiện rồi commit; T1 chạy lại query thấy 4 hàng | **Có thể được phép** trong mức tối thiểu của REPEATABLE READ |
| **Serialization anomaly** | Nhiều transaction cùng commit thành công nhưng tổng kết quả không tương đương bất kỳ thứ tự thực thi tuần tự nào | **Có thể xảy ra** ở REPEATABLE READ |

Ở đây “được phép” **không có nghĩa phải xảy ra**. Một database được quyền cung cấp bảo vệ mạnh hơn mức tối thiểu SQL. Đây là lý do cùng một mức `REPEATABLE_READ` có thể ngăn phantom trong PostgreSQL nhưng không ngăn phantom trong SQL Server/H2.

### 2.1. Non-repeatable read: cùng hàng, giá trị khác

```text
T1 (READ COMMITTED)                T2
---------------------------------  ----------------------------
BEGIN
SELECT balance WHERE id=1 -> 100
                                   BEGIN
                                   UPDATE balance=120 WHERE id=1
                                   COMMIT
SELECT balance WHERE id=1 -> 120
COMMIT
```

T1 chạy hai lần trên cùng hàng, nhưng kết quả khác vì snapshot/visibility của lần đọc sau đã cập nhật. Ở nhiều database, `REPEATABLE_READ` sẽ không cho hiện tượng này: nó có thể đọc phiên bản cũ qua MVCC, hoặc giữ khóa đọc để ngăn T2 cập nhật đến khi T1 hoàn tất.

### 2.2. Phantom read: cùng predicate, tập hàng khác

```text
T1                                   T2
-----------------------------------  ----------------------------
BEGIN
SELECT COUNT(*) FROM orders
WHERE amount >= 100 -> 3
                                     INSERT orders(amount=150)
                                     COMMIT
SELECT COUNT(*) FROM orders
WHERE amount >= 100 -> 4  (phantom)
COMMIT
```

Ví dụ trên là **một lịch có thể xảy ra** ở isolation cho phép phantom, không phải output cố định trên mọi database. Ở PostgreSQL REPEATABLE READ, cùng một consistent snapshot ngăn T1 nhìn thấy hàng T2 mới commit; ở SQL Server REPEATABLE READ thông thường, shared lock trên những hàng đã đọc không nhất thiết khóa toàn bộ **khoảng giá trị** để chặn hàng mới xuất hiện.

### 2.3. Serialization anomaly: kết quả ổn định nhưng business invariant vẫn sai

Giả sử có hai bác sĩ trực; quy tắc nghiệp vụ là **phải còn ít nhất một bác sĩ trực**:

```text
doctors:
(Alice, on_call=true)
(Bob,   on_call=true)

T1                                T2
--------------------------------  --------------------------------
BEGIN REPEATABLE READ             BEGIN REPEATABLE READ
COUNT(on_call=true) -> 2          COUNT(on_call=true) -> 2
UPDATE Alice SET on_call=false    UPDATE Bob SET on_call=false
COMMIT                            COMMIT

Kết quả: không còn ai trực.
```

Khi hai transaction cập nhật **hai hàng khác nhau** dựa trên snapshot chung, một hệ sử dụng snapshot isolation có thể để cả hai commit: **write skew**. Mỗi transaction tự đọc một snapshot hợp lệ, nhưng tổng kết quả vi phạm ràng buộc liên hàng. PostgreSQL REPEATABLE READ **có thể** gặp trường hợp này; `SERIALIZABLE` (với xử lý lỗi/retry) hoặc khóa/constraint phù hợp giúp bảo vệ invariant. Trong database dùng row locking, lịch thực thi và kết quả có thể khác.

**Bài học:** thấy cùng giá trị sau hai lần SELECT **không đủ** để khẳng định toàn bộ logic nhiều thao tác là serializable.

## 3. MVCC hoạt động như thế nào?

**MVCC (Multi-Version Concurrency Control)** cho phép database giữ nhiều phiên bản logic của một hàng để transaction đọc snapshot thích hợp. Các hệ triển khai khác nhau: ví dụ PostgreSQL lưu nhiều tuple version và dùng visibility rules; InnoDB dùng undo information/read view; SQL Server có row-versioning infrastructure và một số isolation options riêng.

```text
Hàng tài khoản id=1:

Phiên bản V1: balance=100  -- đã commit trước snapshot của T1
Phiên bản V2: balance=120  -- T2 vừa commit sau snapshot của T1

T1 đọc qua snapshot cũ  ───────────> thấy V1 (100)
T3 mở snapshot mới      ───────────> có thể thấy V2 (120)
```

Các thuộc tính nên hiểu độc lập:

1. **Read view/snapshot:** DB quyết định transaction/statement nào được nhìn thấy phiên bản nào. Snapshot có thể cố định **mỗi statement** hoặc **mỗi transaction**, tùy engine và isolation.
2. **Read your own writes:** một transaction thường vẫn nhìn thấy các thay đổi chính nó vừa tạo, dù snapshot tham chiếu một thời điểm cũ. Do đó “snapshot cố định” **không có nghĩa** mọi SELECT luôn trả về giá trị bất biến bất chấp chính T1 đã UPDATE.
3. **Visibility khác locking:** plain SELECT dùng consistent snapshot có thể không khóa các hàng được đọc; các câu lệnh `UPDATE`/`DELETE`/`SELECT FOR UPDATE` có logic khóa và chọn phiên bản riêng.
4. **Garbage collection/version retention:** DB không thể dọn bản ghi cũ ngay nếu transaction/snapshot đang mở còn có thể cần đọc. PostgreSQL có VACUUM/old tuples, InnoDB có undo/purge, SQL Server có version store. Transaction đọc quá lâu có thể làm áp lực lưu trữ tăng.
5. **MVCC không loại bỏ write locks:** transaction đồng thời UPDATE cùng một hàng vẫn cần cơ chế khóa/xung đột. Cách chờ, lỗi và retry khác nhau giữa các engine.
6. **Isolation không phải một API cache:** dữ liệu cũ được cung cấp bởi visibility của DB, không nhất thiết là Hibernate cache hay Java object được giữ trong RAM.

### 3.1. Một snapshot được tạo lúc nào?

Câu “snapshot tại lúc BEGIN” chỉ là cách nói rút gọn và **không chính xác với mọi engine**.

- **PostgreSQL REPEATABLE READ:** snapshot được chốt khi transaction thực hiện câu lệnh truy vấn hoặc thay đổi dữ liệu đầu tiên, không nhất thiết ngay tại câu `BEGIN`. Các statement sau đọc cùng snapshot (cộng thay đổi do chính transaction).
- **InnoDB REPEATABLE READ:** với **consistent nonlocking SELECT**, read view được thiết lập ở **lần consistent read đầu tiên** trong transaction, trừ khi sử dụng cú pháp/điều kiện đặc biệt như `START TRANSACTION WITH CONSISTENT SNAPSHOT`. Các consistent read tiếp theo dùng read view đó.
- **READ COMMITTED dựa trên MVCC:** thường chọn snapshot mới cho mỗi statement, vì vậy cùng một câu SELECT có thể trả về dữ liệu T2 vừa commit giữa hai lần gọi.
- **SQL Server REPEATABLE READ thông thường:** hành vi chủ yếu là giữ **shared locks** đến cuối transaction, không phải bắt buộc giữ một transaction-wide MVCC snapshot.

Do vậy, **thời điểm SELECT đầu tiên và loại SELECT** có thể quyết định kết quả thử nghiệm, nhất là khi so sánh PostgreSQL với InnoDB.

## 4. Bảng so sánh: một isolation name, nhiều cách hiện thực

Bảng tổng hợp mô tả hành vi chủ yếu của các cấu hình phổ biến, không thay cho tài liệu/version/engine đang chạy thực tế.

| Database | `REPEATABLE READ` thường thực hiện bằng gì? | Hai plain SELECT có thể thấy update của T2 đã commit? | Phantom trong truy vấn lặp thông thường | Điểm cần nhớ |
|---|---|---|---|---|
| **PostgreSQL** | Transaction snapshot/MVCC; triển khai dạng snapshot isolation | Không, sau khi snapshot đã chốt | **Không** đối với snapshot reads | Vẫn có serialization anomaly/write skew; một số update conflict gây lỗi phải retry |
| **MySQL InnoDB** | Consistent nonlocking reads dùng read view cố định từ lần đọc đầu | Không cho plain consistent SELECT cùng read view | Plain consistent SELECT thường **không thấy phantom mới** | Locking read và DML nhìn trạng thái mới hơn, dùng record/gap/next-key locks; không trộn semantics một cách ngây thơ |
| **SQL Server** | `REPEATABLE READ` dựa trên shared locks giữ đến cuối transaction | Không theo semantics thông thường; T2 có thể phải chờ | **Có thể** vì không bảo vệ key ranges | `SNAPSHOT` là **isolation khác**, `RCSI` là cách thực hiện READ COMMITTED |
| **Oracle Database** | Không hỗ trợ một level độc lập tên `REPEATABLE READ` | Không có level để đối chiếu trực tiếp | Dùng READ COMMITTED/SERIALIZABLE tùy yêu cầu | Oracle dùng MVCC; lựa chọn là READ COMMITTED, SERIALIZABLE, READ ONLY |
| **H2** | Engine MVCC; mức REPEATABLE READ riêng | Không xảy ra non-repeatable read | **Có thể** có phantom | H2 có mức `SNAPSHOT` riêng; test H2 không chứng minh phantom policy của PostgreSQL |

**Không đánh đồng:** PostgreSQL REPEATABLE READ ≈ snapshot isolation về nhiều đặc điểm thực tế, nhưng không có nghĩa PostgreSQL REPEATABLE READ = SQL Server REPEATABLE READ; InnoDB REPEATABLE READ có hai mô hình đọc khác nhau tùy statement; H2 REPEATABLE READ khác H2 SNAPSHOT.

## 5. PostgreSQL: snapshot ổn định, không phantom nhưng vẫn có write skew

PostgreSQL mặc định **READ COMMITTED**. Khi chuyển sang `REPEATABLE READ`:

1. Các câu đọc sau snapshot ban đầu nhìn cùng tập thay đổi đã commit trước snapshot, cộng những thay đổi của chính T1.
2. T2 có thể commit UPDATE/INSERT khi T1 đang đọc snapshot cũ; T1 không tự thấy thay đổi đó trong các SELECT sau.
3. PostgreSQL cam kết **không có phantom read** ở REPEATABLE READ — mạnh hơn mức tối thiểu trong bảng chuẩn SQL.
4. Các giao dịch đồng thời có thể vẫn tạo **serialization anomaly**, nhất là write skew trên các hàng khác nhau.
5. Nếu T1 muốn UPDATE/DELETE/lock một hàng đã bị transaction khác sửa sau snapshot của T1, PostgreSQL có thể chờ rồi báo **serialization failure** thay vì dùng phiên bản cũ để cập nhật. Phải rollback và retry **toàn transaction**, không chỉ retry một statement trên transaction đã lỗi.

### 5.1. Ví dụ hai session PostgreSQL

Giả sử bảng đã tồn tại:

```sql
CREATE TABLE accounts (
    id INTEGER PRIMARY KEY,
    balance INTEGER NOT NULL
);
INSERT INTO accounts(id, balance) VALUES (1, 100);
```

Chạy trên hai kết nối độc lập. *Session 1*:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT balance FROM accounts WHERE id=1;  -- 100, chốt snapshot
-- Trong lúc session 1 vẫn mở, chạy session 2:
-- UPDATE accounts SET balance=120 WHERE id=1; COMMIT;
SELECT balance FROM accounts WHERE id=1;  -- vẫn 100
COMMIT;
```

*Session 2*, chạy giữa hai SELECT của session 1:

```sql
BEGIN;
UPDATE accounts SET balance=120 WHERE id=1;
COMMIT;
```

Nếu session 1 chỉ đọc, PostgreSQL trả **100 rồi 100**; một transaction mới sau đó có thể thấy 120. Nếu session 1 cố UPDATE hàng này sau khi session 2 đã commit, nó có thể nhận SQLSTATE **`40001`** với lỗi serialization; ứng dụng phải chạy lại từ boundary transaction.

### 5.2. Phản ví dụ phantom theo predicate

Ở T1 đã chốt snapshot:

```sql
SELECT COUNT(*) FROM accounts WHERE balance >= 100;
```

T2 chèn thêm hàng thỏa điều kiện rồi commit. Khi T1 chạy lại cùng query, nó **không** thấy hàng mới trong snapshot của mình. Đây là “không phantom” theo PostgreSQL REPEATABLE READ, chứ **không** phải lời hứa của mọi database dùng nhãn REPEATABLE READ.

### 5.3. Vì sao cần SERIALIZABLE cho invariant nhiều hàng?

Ở bài toán hai bác sĩ, nếu cả hai transaction dựa trên snapshot cũ rồi UPDATE các hàng *khác nhau*, PostgreSQL REPEATABLE READ có thể cho phép cả hai commit và không còn ai trực. PostgreSQL `SERIALIZABLE` sử dụng Serializable Snapshot Isolation (SSI), phát hiện chuỗi phụ thuộc không thể tuần tự hóa và rollback một transaction bằng lỗi `40001`; application cần retry toàn bộ transaction.

Không tăng isolation lên SERIALIZABLE một cách mù quáng: cần biết invariant, số lần conflict, policy retry/idempotency, chi phí quản lý transaction và tác động đến throughput. Một unique constraint, check logic được khóa đúng hoặc thiết kế lại dữ liệu đôi khi phù hợp hơn.

## 6. MySQL InnoDB: consistent read và locking/current read không giống nhau

InnoDB mặc định **REPEATABLE READ** (trong cấu hình thông thường). Điểm dễ gây bug là **không phải mọi câu lệnh trong cùng transaction đều đọc theo cùng một kiểu**.

### 6.1. Consistent nonlocking SELECT

Một câu `SELECT` thông thường (không `FOR UPDATE`/`FOR SHARE`) thường là **consistent nonlocking read**. Trong REPEATABLE READ:

- Lần consistent read đầu tạo read view của transaction.
- Những consistent read tiếp theo dùng read view đó và nhìn thấy dữ liệu đã commit trước read view, cộng thay đổi của T1.
- Các hàng mới do T2 commit sau read view **không xuất hiện** trong những plain consistent SELECT của T1 — vì vậy phantom kiểu “SELECT lặp lại thấy hàng mới” thường không xuất hiện ở đây.

Trong READ COMMITTED, InnoDB tạo read view mới cho **mỗi consistent read**, nên non-repeatable và phantom reads có thể xảy ra.

**Chi tiết có thể gây ngạc nhiên:** InnoDB cho transaction nhìn thấy những thay đổi **do chính nó** thực hiện. Vì thế sau một `UPDATE` của T1, SELECT có thể kết hợp phiên bản vừa sửa của các hàng T1 với phiên bản cũ của các hàng khác; kết quả có thể không trùng bất kỳ một trạng thái đơn nhất của database bên ngoài.

### 6.2. Locking read, UPDATE và DELETE

```sql
-- Một plain consistent read:
SELECT balance FROM accounts WHERE id = 1;

-- Một locking read:
SELECT balance FROM accounts WHERE id = 1 FOR UPDATE;

-- Một DML statement:
UPDATE accounts SET balance = balance - 10 WHERE id = 1;
```

Những câu này **không mang cùng visibility/locking semantics**. `SELECT ... FOR UPDATE`, `FOR SHARE`, `UPDATE` và `DELETE` dùng cơ chế khóa/current read liên quan đến trạng thái mới hơn và có thể phải chờ giao dịch khác kết thúc. InnoDB dùng **record locks**, **gap locks** và **next-key locks** phụ thuộc predicate và index được truy cập.

- Truy vấn qua unique index với điều kiện unique phù hợp có thể chỉ khóa record.
- Range scan/điều kiện không unique có thể khóa cả những khoảng giá trị để ngăn insert vào khoảng (next-key/gap locking), tùy query plan/index/isolation.
- Không có index phù hợp có thể làm phạm vi khóa rộng và throughput giảm.
- Đừng rút kết luận “plain SELECT ổn định nên UPDATE cũng chỉ đụng những hàng hiện trong snapshot cũ”.

**Ví dụ bất ngờ được tài liệu InnoDB mô tả:** T1 plain SELECT theo predicate không thấy hàng mới do T2 insert sau read view, nhưng T1 thực hiện `UPDATE ... WHERE same_predicate` có thể tác động đến hàng mới đó theo cơ chế current/locking read. Sau UPDATE, plain SELECT tiếp theo thậm chí có thể thấy hàng do chính T1 vừa cập nhật. Điều này khác với cách PostgreSQL REPEATABLE READ xử lý update conflict trên row đã thay đổi sau snapshot.

### 6.3. Phantom “được ngăn” trong trường hợp nào?

Không nên khẳng định **“InnoDB REPEATABLE READ hoàn toàn không có phantom trong mọi tình huống”**. Diễn đạt chính xác hơn:

- Với **plain consistent reads** trên cùng read view, T1 không thấy các insert mới của T2.
- Với **locking reads/range scans**, InnoDB có thể dùng next-key/gap locks nhằm chặn insert vào khoảng đã khóa; tùy index, điều kiện và câu lệnh.
- Nếu trộn consistent SELECT với locking SELECT hoặc DML, hai kiểu đọc có thể nhìn **các phiên bản khác nhau**, khiến suy luận trên cùng “snapshot” bị sai.

Tài liệu MySQL khuyến nghị tránh trộn locking statements với nonlocking SELECT một cách tùy tiện trong REPEATABLE READ; nếu logic thật sự yêu cầu lịch biểu tuần tự hóa, cân nhắc SERIALIZABLE hoặc thiết kế locking rõ ràng.

## 7. SQL Server: REPEATABLE READ giữ shared locks, SNAPSHOT là mức riêng

SQL Server minh họa rõ nhất vì sao không thể đánh đồng **REPEATABLE_READ = MVCC snapshot**.

Trong SQL Server, `REPEATABLE READ` truyền thống giữ **shared read locks** trên các hàng đã đọc cho đến cuối transaction, khiến giao dịch khác không thể sửa chính những hàng đó trong khi T1 còn giữ lock. Nhưng **không khóa mọi khoảng giá trị** của predicate, nên một transaction khác vẫn có thể thêm hàng thỏa điều kiện và gây **phantom**.

```text
T1 REPEATABLE READ:
  SELECT ... WHERE id = 1     -- giữ S lock trên hàng id=1
  ...
T2 UPDATE id=1               -- có thể phải chờ T1 kết thúc

T2 INSERT id=99 thuộc range:
  -- có thể thành công nếu không bị những lock khác chặn

T1 SELECT COUNT(*) WHERE id > 50
  -- có thể gặp phantom
```

SQL Server có cơ chế row versioning nhưng **tên các isolation options khác**:

- **READ_COMMITTED_SNAPSHOT (RCSI)** là tùy chọn **cấp database** khiến `READ COMMITTED` sử dụng snapshot theo **mỗi statement**; nó **không biến REPEATABLE READ thành snapshot isolation**.
- **SNAPSHOT isolation** là **một isolation level riêng** sử dụng row versions để cung cấp transaction-level snapshot. Cần bật `ALLOW_SNAPSHOT_ISOLATION` trên database và chọn SNAPSHOT ở session/transaction đúng cách.
- **SERIALIZABLE** dùng range locks để bảo vệ predicates khỏi phantom theo semantics SQL Server.

Hãy kiểm tra edition/version/tùy chọn optimized locking và transaction isolation được đặt thực tế, thay vì chỉ suy từ annotation Java.

**Giới hạn của Spring enum:** `Isolation.REPEATABLE_READ` ánh xạ đến JDBC `TRANSACTION_REPEATABLE_READ`; nó **không đồng nghĩa** thiết lập SQL Server `SNAPSHOT` (một level riêng của SQL Server). Đừng tự coi việc đổi enum thành REPEATABLE_READ là đủ để nhận transaction-wide row versioning trong SQL Server.

## 8. Oracle và H2: hai lý do khác để không suy rộng

### 8.1. Oracle Database

Oracle dùng multiversion read consistency nhưng **không cung cấp isolation level tên REPEATABLE READ độc lập** trong tập mức hỗ trợ như PostgreSQL/MySQL. Các mode thông dụng gồm:

- **READ COMMITTED (mặc định):** mỗi câu query đọc dữ liệu đã commit tại thời điểm statement bắt đầu.
- **SERIALIZABLE:** transaction-level consistent view với cơ chế kiểm tra xung đột và lỗi khi cần (ví dụ `ORA-08177`); không nên đánh đồng trực tiếp với cơ chế SSI của PostgreSQL.
- **READ ONLY transaction:** hữu ích cho một snapshot nhất quán phục vụ các chuỗi truy vấn đọc.

Vì vậy, `@Transactional(isolation = Isolation.REPEATABLE_READ)` có thể không được driver/manager Oracle chấp nhận. Không làm fallback im lặng sang `SERIALIZABLE` nếu không đánh giá tính đúng đắn, lỗi/retry và chi phí.

### 8.2. H2 in-memory

H2 có các mức `READ_COMMITTED`, `REPEATABLE_READ`, `SNAPSHOT`, `SERIALIZABLE` (và READ_UNCOMMITTED). Theo tài liệu H2:

- `REPEATABLE_READ` ngăn dirty và non-repeatable reads, nhưng **phantom reads vẫn có thể xảy ra**.
- `SNAPSHOT` ngăn cả phantom đối với read view theo semantics H2.
- Mức `SERIALIZABLE` của H2 có ghi chú hạn chế về việc bảo đảm tương đương lịch tuần tự trong những transaction có ghi.

Do đó H2 là môi trường học tốt để quan sát **đọc lại hàng** dưới các isolation levels, nhưng **không phải mô phỏng chính xác PostgreSQL/InnoDB/SQL Server** cho phantom, locking, conflict, DDL hoặc hiệu năng. Phải kiểm thử tích hợp trên database production thực tế.

## 9. Spring Framework chuyển isolation vào database như thế nào?

Với Spring JDBC và transaction manager địa phương:

```java
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.REPEATABLE_READ,
    readOnly = true
)
public Report readReport() {
    // Truy vấn JDBC/repository trong transaction do Spring quản lý.
    // Chỉ là snippet: Report và repository do ứng dụng cung cấp.
    return repository.loadReport();
}
```

Snippet trên **không biên dịch độc lập** vì `Report` và `repository` tượng trưng. Khi method này **bắt đầu physical transaction mới**, Spring transaction manager có thể gọi JDBC `Connection.setTransactionIsolation(Connection.TRANSACTION_REPEATABLE_READ)` trước các lệnh SQL. JDBC driver/database sau đó quyết định semantics thực tế. Spring **không tự cài MVCC trong Java**, không tự lưu snapshot của dữ liệu DB.

### 9.1. Isolation chỉ có hiệu lực khi thật sự mở transaction mới

Đây là lỗi thiết kế Spring rất hay gặp:

```java
@Service
class OuterService {
    private final ReportService reports;

    OuterService(ReportService reports) {
        this.reports = reports;
    }

    @Transactional(isolation = Isolation.READ_COMMITTED)
    public void outer() {
        reports.readRepeatably();
    }
}

@Service
class ReportService {
    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.REPEATABLE_READ
    )
    public void readRepeatably() {
        // Tham gia transaction READ_COMMITTED của outer.
        // REPEATABLE_READ ở inner không tự thay đổi physical transaction!
    }
}
```

Đây là **hai class minh họa** chưa bao gồm imports/runner. Với `REQUIRED`, nếu outer đã có transaction, inner **tham gia transaction ngoài**; cấu hình isolation của inner thông thường **không thay thế** isolation của physical transaction đang mở. `AbstractPlatformTransactionManager.validateExistingTransaction` mặc định **false** (tương đối lenient). Nếu bật `true`, Spring có thể phát hiện yêu cầu isolation/read-only không tương thích khi tham gia và từ chối thay vì bỏ qua.

Nếu thật sự muốn một transaction đọc với isolation riêng, cân nhắc **tách service và dùng `REQUIRES_NEW`** với những đánh đổi: outer bị suspend, inner lấy connection/transaction khác, giữ locks/tài nguyên của outer và có thể xảy ra bất nhất về commit/rollback. Không dùng `REQUIRES_NEW` chỉ để “né” sự cần thiết thiết kế transaction boundary đúng.

### 9.2. Proxy và self-invocation

```java
@Service
class WrongService {
    public void report() {
        this.loadStableSnapshot();
    }

    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public void loadStableSnapshot() {
        // Gọi this.loadStableSnapshot() không đi qua proxy.
    }
}
```

Đây là snippet minh họa: trong Spring proxy mode, lời gọi cùng instance bằng `this` bypass transaction interceptor. `@Transactional` có thể **không tạo transaction**, nên mức isolation không được đặt. Khuyến nghị gọi một method service khác qua Spring-managed proxy hoặc dùng `TransactionTemplate` để chủ động khai báo boundary.

### 9.3. `Isolation.DEFAULT` không phải READ_COMMITTED

`Isolation.DEFAULT` có nghĩa dùng **mức mặc định của database/connection**, không phải mặc định READ_COMMITTED của Spring. Các hệ khác nhau: PostgreSQL mặc định READ COMMITTED, InnoDB mặc định REPEATABLE READ, Oracle mặc định READ COMMITTED, H2 mặc định READ COMMITTED; SQL Server còn có các lựa chọn database như RCSI. Không dựa vào tên enum để suy ra DBA đã cấu hình gì.

### 9.4. Read-only không tự tăng isolation

`@Transactional(readOnly = true)` có thể là hint/tối ưu hóa hoặc thiết lập read-only trên connection/session tùy manager/driver. Nó **không tự tạo snapshot ổn định, không tự biến READ_COMMITTED thành REPEATABLE_READ và không thay SERIALIZABLE**. Tương tự, các entity được Hibernate giữ trong first-level cache không chứng minh database đang lặp lại query theo REPEATABLE_READ; cần kiểm tra SQL thực sự.

## 10. Demo Java 17 chạy được: READ_COMMITTED thấy update, REPEATABLE_READ không thấy

Thực nghiệm dùng **Spring JDBC**, **TransactionTemplate**, **H2**. Để tạo hai physical transactions độc lập một cách có thứ tự mà không phụ thuộc timing thread, code mở T1 rồi dùng `PROPAGATION_REQUIRES_NEW` để chạy T2 trên connection khác:

1. T1 đọc `balance=100`.
2. T2 cập nhật cùng hàng thành 125 và commit.
3. T1 đọc lại cùng hàng, trước khi chính T1 commit.
4. So sánh T1 dùng READ_COMMITTED với T1 dùng REPEATABLE_READ.

T1 **chỉ đọc**, do đó thí nghiệm tránh việc nó đang giữ write lock trên hàng khiến T2 không update được. H2 cho phép non-repeatable reads ở READ_COMMITTED và ngăn chúng ở REPEATABLE_READ, phù hợp mục tiêu quan sát. Demo **không tuyên bố** tất cả DB tạo phantom giống H2.

### 10.1. Cấu trúc dự án

```text
spring-repeatable-read-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── isolation/
                        └── Main.java
```

### 10.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>spring-repeatable-read-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
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
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-jdbc` kéo theo Spring transaction infrastructure, `h2` là database in-memory. Spring 6.2.19 phù hợp Java 17+, dùng bản đã pin để dễ tái hiện; dự án production nên quản lý dependencies bằng BOM/phiên bản được duy trì và kiểm thử.

### 10.3. `src/main/java/com/example/isolation/Main.java`

```java
package com.example.isolation;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

public class Main {

    private static int readBalance(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
            "SELECT balance FROM accounts WHERE id = 1",
            Integer.class
        );
    }

    private static void runCase(
            String name,
            int isolation,
            JdbcTemplate jdbc,
            JdbcTransactionManager manager) {

        // Reset giữa hai kịch bản, ngoài transaction đang được demo.
        jdbc.update("UPDATE accounts SET balance = 100 WHERE id = 1");

        // T1 có physical transaction và isolation được chọn.
        TransactionTemplate outer = new TransactionTemplate(manager);
        outer.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
        outer.setIsolationLevel(isolation);

        // T2 có transaction/connection độc lập, suspend T1 khi chạy.
        TransactionTemplate writer = new TransactionTemplate(manager);
        writer.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRES_NEW
        );

        System.out.println("=== " + name + " ===");

        outer.executeWithoutResult(t1 -> {
            int first = readBalance(jdbc);
            System.out.println("T1 first=" + first);

            writer.executeWithoutResult(t2 -> {
                jdbc.update(
                    "UPDATE accounts SET balance = 125 WHERE id = 1"
                );
                System.out.println("T2 updated=125");
            }); // T2 commit, T1 được resume.

            int second = readBalance(jdbc);
            System.out.println("T1 second=" + second);
        }); // T1 commit.

        System.out.println("after completion=" + readBalance(jdbc));
    }

    public static void main(String[] args) {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl(
            "jdbc:h2:mem:repeatable_demo;DB_CLOSE_DELAY=-1"
        );
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute(
            "CREATE TABLE accounts (" +
            "id INT PRIMARY KEY, " +
            "balance INT NOT NULL)"
        );
        jdbc.update(
            "INSERT INTO accounts(id, balance) VALUES (1, 100)"
        );

        JdbcTransactionManager manager =
            new JdbcTransactionManager(dataSource);

        runCase(
            "READ_COMMITTED",
            TransactionDefinition.ISOLATION_READ_COMMITTED,
            jdbc,
            manager
        );

        runCase(
            "REPEATABLE_READ",
            TransactionDefinition.ISOLATION_REPEATABLE_READ,
            jdbc,
            manager
        );
    }
}
```

**Đọc code:**

- `runCase` dùng một `JdbcTransactionManager` và một datasource duy nhất; `JdbcTemplate` lấy đúng connection hiện đang ràng buộc với transaction của từng đoạn.
- `TransactionTemplate` cho phép đặt isolation của **physical transaction mới** mà không cần AOP proxy. T1 là transaction ngoài; T2 có `PROPAGATION_REQUIRES_NEW` nên sử dụng một physical transaction mới và sau đó resume T1.
- `DriverManagerDataSource` tạo connection theo yêu cầu và **không phải pool**; dùng cho demo, production nên dùng pool phù hợp. Vì T1 chưa ghi/khóa hàng này, T2 có thể cập nhật độc lập để quan sát read consistency.
- Mỗi kịch bản reset balance về 100 **sau transaction trước hoàn tất**. Không dùng các con số từ lần chạy trước để kết luận về transaction mới.
- `readBalance` dùng JDBC SQL trực tiếp qua template, tránh nhầm với Hibernate first-level cache.

### 10.4. Chạy và output kỳ vọng

Cài JDK 17+ và Maven. Tại thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.isolation.Main
```

Những dòng do chính chương trình in ra trên H2 cho ví dụ này:

```text
=== READ_COMMITTED ===
T1 first=100
T2 updated=125
T1 second=125
after completion=125
=== REPEATABLE_READ ===
T1 first=100
T2 updated=125
T1 second=100
after completion=125
```

**Giải thích sự khác biệt:**

- Với `READ_COMMITTED`, hai SELECT của T1 có thể nhìn snapshot khác nhau. T2 đã commit trước SELECT thứ hai nên T1 thấy 125.
- Với `REPEATABLE_READ`, T1 không bị non-repeatable read trên cùng hàng: hai lần T1 đọc đều là 100. T2 **vẫn đã commit thành công**; sau khi T1 đóng, một transaction mới nhìn thấy 125.
- Việc T1 vẫn thấy 100 **không có nghĩa T2 không commit** hoặc database đã rollback T2. Đó là **visibility của T1**.
- Kết quả này **chỉ minh họa non-repeatable read**, không chứng minh phantom hay write skew bị ngăn ở H2 hoặc các DB khác.

Đây là code demo có thể biên dịch với dependencies đã khai báo; nội dung này mô tả hành vi được kỳ vọng theo semantics H2, còn việc chạy thật cần JDK/Maven và thư viện đã tải. Nếu dùng một database khác, có thể gặp tình trạng blocking, update conflict, khác biệt SQL dialect hoặc cách snapshot được chốt: khi đó cần test thực tế và không sửa kỳ vọng bằng cách bỏ qua exception.

## 11. Hai phiên bản SQL để kiểm chứng phantom và kiểu đọc trên engine thật

### 11.1. PostgreSQL: hai lần count theo predicate trên cùng snapshot

Chuẩn bị dữ liệu **trước** khi mở T1:

```sql
CREATE TABLE invoices (
    id INTEGER PRIMARY KEY,
    amount INTEGER NOT NULL
);
INSERT INTO invoices(id, amount)
VALUES (1, 120), (2, 90);
```

Kết nối T1:

```sql
BEGIN ISOLATION LEVEL REPEATABLE READ;
SELECT COUNT(*) FROM invoices WHERE amount >= 100; -- 1
-- Dừng ở đây để kết nối T2 chèn và COMMIT.
SELECT COUNT(*) FROM invoices WHERE amount >= 100; -- vẫn 1
COMMIT;
```

Kết nối T2, chạy giữa hai query của T1:

```sql
BEGIN;
INSERT INTO invoices(id, amount) VALUES (3, 150);
COMMIT;
```

Nếu không có thao tác thay đổi dữ liệu khác và đúng lịch trên, T1 ở PostgreSQL RR vẫn đếm **1**. Khi T1 commit và transaction kế tiếp đọc, kết quả đếm là **2**. Nhìn snapshot ổn định không có nghĩa có ràng buộc ngăn T2 insert, chỉ là T1 không nhìn phiên bản mới.

### 11.2. InnoDB: phân biệt SELECT thường và SELECT FOR UPDATE

Tại một InnoDB transaction ở `REPEATABLE READ`:

```sql
START TRANSACTION;
SELECT balance FROM accounts WHERE id = 1;
-- T2 cập nhật cùng id=1 rồi COMMIT.
SELECT balance FROM accounts WHERE id = 1;
-- Plain consistent SELECT thường vẫn thấy phiên bản snapshot cũ.

SELECT balance FROM accounts WHERE id = 1 FOR UPDATE;
-- Locking/current read; không thể suy ra kết quả chỉ từ read view
-- của plain SELECT. Còn phụ thuộc khóa và thay đổi đồng thời.
COMMIT;
```

Đây là **timeline minh họa cần chạy trên MySQL/InnoDB có bảng accounts thật**, không phải chương trình độc lập có output cứng cho `FOR UPDATE`. Thay vì khẳng định locking read “luôn thấy 125”, cần xét transaction nào đang giữ khóa, thời điểm commit, điều kiện/index và liệu câu lệnh đang chờ hoặc gặp deadlock/timeout.

**Đừng dùng kết quả từ H2 rồi mặc định đó là chính sách phantom của PostgreSQL hoặc InnoDB.**

## 12. Những giới hạn mà REPEATABLE_READ không tự giải quyết

### 12.1. Write skew và invariant nhiều hàng

Để tránh hai bác sĩ cùng rút khỏi ca trực, hãy đặt business invariant vào một transaction với khả năng chống serialization anomalies, hoặc dùng constraint/khóa thích hợp. Ví dụ PostgreSQL `SERIALIZABLE` có thể abort một transaction do phụ thuộc read/write bất hợp lệ; application phải retry toàn transaction theo chính sách có giới hạn.

Không chỉ đọc COUNT rồi tin rằng RR làm câu quyết định “không ai khác thay đổi”: count ổn định với snapshot **không đồng nghĩa** các transaction khác không thể cùng đưa ra quyết định dựa trên snapshot tương tự.

### 12.2. Lost update và optimistic locking

Một pattern có vấn đề:

```text
T1 đọc balance=100
T2 đọc balance=100
T1 tính 100+10 rồi UPDATE balance=110
T2 tính 100+20 rồi UPDATE balance=120
```

Kết quả cuối có thể đánh mất một cập nhật, nhưng **có xảy ra hay không** phụ thuộc engine/isolation và cách UPDATE được viết. PostgreSQL RR có thể báo serialization failure khi hai transaction tranh cùng hàng; SQL Server locking có thể block/deadlock; InnoDB có semantics locking/current read riêng. Không khẳng định một kết quả cứng cho mọi DB.

Các giải pháp thường cân nhắc:

- Cập nhật nguyên tử bằng SQL `UPDATE accounts SET balance=balance+10 WHERE id=?` thay vì read-compute-write không kiểm soát.
- Dùng `@Version` của JPA/Hibernate để optimistic locking khi phù hợp.
- Dùng `SELECT ... FOR UPDATE` / pessimistic locking với chỉ số và transaction boundary phù hợp.
- Với lỗi serialization/deadlock/optimistic conflict, retry lại **toàn bộ đơn vị nghiệp vụ** có khả năng idempotent, không lặp lại side effect không thể đảo ngược.

### 12.3. Long-running transactions và giữ phiên bản dữ liệu

Một báo cáo đọc chạy hàng phút ở snapshot cũ có thể cản DB dọn phiên bản hàng không còn dùng, làm tăng undo/version storage, WAL/retention/cleanup pressure tùy engine. Transaction chạy lâu còn giữ connection và có thể giữ lock khi thực hiện writes/locking reads.

Giảm kích thước transaction, phân trang theo chiến lược đúng dữ liệu, theo dõi tuổi transaction/snapshot, timeout và pool. Nếu chỉ cần một báo cáo nhất quán, cân nhắc database snapshot/export/analytics phù hợp thay vì mở transaction OLTP quá lâu.

### 12.4. Cache ứng dụng dễ làm sai phép đo

JPA `EntityManager.find(...)` lần hai có thể trả **cùng đối tượng Java** trong first-level cache mà không phát SQL lần nữa. Khi đó đọc “100, 100” **chưa chứng minh** database isolation là REPEATABLE_READ. Ngược lại, query JPQL có thể làm flush/hit database hoặc trả dữ liệu khác cách mong đợi.

Để kiểm chứng isolation thực, dùng JDBC query hoặc thiết kế test JPA rõ ràng với flush/clear/refresh có chủ đích, kiểm tra SQL logging, connection và transaction boundary. Không gọi `clear()` một cách vô tội vạ trong production chỉ để “ép tính đúng đắn”.

### 12.5. Nhiều datasource hoặc thread khác

Transaction JDBC local gắn connection của một datasource vào **thread** hiện tại. Nếu bạn gọi async task hoặc dùng datasource khác/transaction manager khác, những SQL đó có thể **không cùng transaction/snapshot**. `@Transactional` trên service A không tự mở một transaction phân tán xuyên nhiều database.

Tương tự, transaction reactive dùng Reactor context và manager riêng. Không dùng `ThreadLocal` hay `TransactionSynchronizationManager.isActualTransactionActive()` của imperative code để kết luận trực tiếp về reactive transaction.

## 13. Chẩn đoán: vì sao REPEATABLE_READ có vẻ không hiệu lực?

| Quan sát | Nguyên nhân có thể có | Cách kiểm tra |
|---|---|---|
| Method có `@Transactional(REPEATABLE_READ)` nhưng query vẫn đọc giá trị mới | Self-invocation, method không qua proxy; transaction chưa được mở | Kiểm tra lời gọi qua Spring bean/proxy, log transaction manager |
| Inner khai báo RR nhưng outer đang READ_COMMITTED | `REQUIRED` đã tham gia physical transaction ngoài | Đọc propagation/boundary; kiểm tra isolation thực tế; dùng strict validation nếu thích hợp |
| Hai lần JPA `find()` đều giống nhau | First-level cache, không phát hai SELECT thật | Bật SQL logging hoặc dùng JDBC test |
| Plain SELECT ổn định nhưng UPDATE/locking SELECT thấy kết quả mới | InnoDB phân biệt consistent read với current/locking read | Kiểm tra dạng SQL, index, read view và locking |
| Query phạm vi xuất hiện phantom ở RR | Có thể đúng với SQL Server/H2, vì chuẩn cho phép | Kiểm tra engine/isolation chứ không đoán theo PostgreSQL |
| RR bị blocking nhiều | Lock-based implementation hoặc query có locking read | Xem wait events, locks, transaction duration và query plan |
| RR ném serialization failure | PostgreSQL/engine phát hiện update conflict | Rollback và retry transaction từ đầu (có backoff/idempotency) |
| Spring báo isolation unsupported | Database/driver không có isolation yêu cầu (ví dụ Oracle RR) | Kiểm tra capability JDBC/transaction manager; chọn chiến lược phù hợp |
| READ_COMMITTED nhưng query vẫn ổn định qua nhiều lần đọc | T2 chưa commit; trúng cache; không có dữ liệu thay đổi; test không đồng bộ đúng | Dùng hai physical transactions và barrier/timeline rõ ràng |
| `Isolation.DEFAULT` tưởng bằng READ_COMMITTED | Mặc định DB khác nhau và có thể bị quản trị viên cấu hình | Kiểm tra `Connection.getTransactionIsolation()` và thông tin server/session |

### 13.1. Kiểm tra isolation JDBC ngay trong transaction

Với JDBC, dùng một connection được lấy qua **Spring-aware API** để không vô tình kiểm tra một connection mới ngoài transaction:

```java
import javax.sql.DataSource;
import org.springframework.jdbc.datasource.DataSourceUtils;
import java.sql.Connection;

public static int currentJdbcIsolation(DataSource ds) {
    Connection conn = DataSourceUtils.getConnection(ds);
    try {
        return conn.getTransactionIsolation();
    } catch (java.sql.SQLException ex) {
        throw new IllegalStateException("Cannot inspect isolation", ex);
    } finally {
        DataSourceUtils.releaseConnection(conn, ds);
    }
}
```

Đây là **phương thức utility minh họa**, cần `DataSource` phù hợp và gọi trong transaction đang hoạt động. `Connection.getTransactionIsolation()` cho biết **level JDBC hiện tại**, không thể tự chứng minh engine đang dùng PostgreSQL-like snapshot hay SQL Server locking. `DataSourceUtils.releaseConnection()` sẽ không đóng connection đang thuộc transaction Spring được bind đúng cách.

SQL kiểm tra bổ sung (khác dialect):

```sql
-- PostgreSQL
SHOW transaction_isolation;

-- MySQL/InnoDB
SELECT @@transaction_isolation;

-- SQL Server: mức hiện tại có thể kiểm tra bằng DBCC USEROPTIONS
DBCC USEROPTIONS;
```

Các câu trên chỉ dành cho hệ quản trị tương ứng; không copy sang H2/Oracle mà không chỉnh dialect. Kiểm tra trạng thái bên **trong** method đang được Spring intercept, không chỉ ở startup của ứng dụng.

### 13.2. Kiểm thử concurrent transaction đúng cách

Một test tốt dùng **hai physical transactions/connections**, có điểm đồng bộ để đảm bảo lịch:

1. T1 mở với isolation cần thử.
2. T1 thực thi **SELECT đầu tiên**, xác lập snapshot nếu engine làm vậy.
3. T2 mở, UPDATE hoặc INSERT hàng độc lập, **COMMIT trước** khi T1 đọc lần hai.
4. T1 lặp lại **cùng SELECT** hoặc **cùng predicate** rồi ghi nhận kết quả.
5. T1 hoàn tất; mở T3 mới để kiểm tra dữ liệu đã commit thật trong DB.
6. Thử thêm locking read, UPDATE conflict, write skew, rollback/retry và các chỉ số lock/wait trên **DB production tương thích**.

Không dùng `Thread.sleep(...)` như cơ chế đảm bảo thứ tự; nếu thực sự dùng nhiều thread, hãy đồng bộ bằng `CountDownLatch`/barrier, giới hạn timeout và đảm bảo finally cleanup. Demo ở mục 10 dùng `REQUIRES_NEW` để tạo T2 đồng bộ nhưng khác physical transaction, giúp tránh timing không ổn định; với DB lock-based, chính lịch T1-read → T2-update có thể block, và đó là kết quả đáng quan sát thay vì ép output giống H2.

## 14. Cách chọn mức cô lập cho nghiệp vụ

**Khi cần một chuỗi báo cáo đọc ổn định:** REPEATABLE_READ trên hệ MVCC hỗ trợ transaction snapshot có thể hữu ích. Nhưng đối với báo cáo nhiều bảng và nhiều predicates, phải hiểu mức cam kết của engine và cân nhắc transaction READ ONLY/SNAPSHOT/analytics.

**Khi phải bảo đảm invariant qua nhiều hàng:** snapshot ổn định có thể chưa đủ (write skew). Dùng SERIALIZABLE với retry, hoặc ràng buộc/locking thích hợp, kết hợp test concurrent.

**Khi chạy workload đọc-ghi có độ cạnh tranh cao:** REPEATABLE_READ không mặc nhiên nhanh hơn READ_COMMITTED. Snapshot/version retention, row/gap locks, update conflicts và retry có thể làm throughput giảm. Hãy đo thực tế trên truy vấn/index/tải đại diện.

**Khi code chạy trên nhiều database khác nhau:** đừng đặt tên enum rồi tin semantics đồng nhất. Đưa isolation assumptions vào integration tests theo database. Khi migrate PostgreSQL ↔ MySQL ↔ SQL Server ↔ Oracle, xem lại toàn bộ chỗ dựa vào phantom, locking read, retry và thời điểm snapshot.

## 15. Câu hỏi tự kiểm tra

1. **REPEATABLE_READ có bảo đảm không có phantom trên mọi DB không?** — Không. SQL cho phép phantom ở mức tối thiểu; PostgreSQL ngăn phantom, SQL Server/H2 có thể cho phép.
2. **PostgreSQL REPEATABLE READ có tương đương SERIALIZABLE không?** — Không. Vẫn có thể gặp write skew/serialization anomaly.
3. **Hai plain SELECT trong cùng transaction InnoDB RR dùng snapshot ở đâu?** — Thường theo read view của lần consistent read đầu tiên.
4. **`SELECT ... FOR UPDATE` trong InnoDB có cùng visibility với plain SELECT không?** — Không nhất thiết; nó là locking/current read với cơ chế khóa riêng.
5. **SQL Server REPEATABLE READ có tự bật SNAPSHOT isolation không?** — Không. SNAPSHOT là isolation riêng, RCSI là option của READ COMMITTED.
6. **`@Transactional(isolation = REPEATABLE_READ)` trên method inner REQUIRED có nâng outer READ_COMMITTED không?** — Thông thường không, vì inner chỉ tham gia physical transaction ngoài.
7. **Vì sao hai lần `EntityManager.find()` trả giống nhau không chứng minh RR?** — Có thể cả hai lần đọc từ first-level cache.
8. **Nếu transaction PostgreSQL RR nhận SQLSTATE 40001, nên retry gì?** — Rollback và retry **toàn transaction**, với giới hạn/idempotency, không retry riêng câu SQL trên transaction đã lỗi.
9. **Tại sao transaction snapshot mở quá lâu có thể tốn tài nguyên?** — Database phải giữ nhiều row versions/undo/history và connection/lock liên quan cho các reader cũ.
10. **`Isolation.DEFAULT` trong Spring có mặc định là READ_COMMITTED không?** — Không; dùng default của database/connection, khác nhau giữa các engine.

## Tài liệu tham khảo chính thức

- PostgreSQL — Transaction Isolation (REPEATABLE READ và snapshot isolation, phantom, serialization anomaly): https://www.postgresql.org/docs/current/transaction-iso.html
- PostgreSQL — `SET TRANSACTION` và thời điểm thiết lập isolation: https://www.postgresql.org/docs/current/sql-set-transaction.html
- MySQL 8.4 — InnoDB Transaction Isolation Levels: https://dev.mysql.com/doc/refman/8.4/en/innodb-transaction-isolation-levels.html
- MySQL 8.4 — Consistent Nonlocking Reads: https://dev.mysql.com/doc/refman/8.4/en/innodb-consistent-read.html
- MySQL 8.4 — Locking Reads: https://dev.mysql.com/doc/refman/8.4/en/innodb-locking-reads.html
- SQL Server — Transaction Locking and Row Versioning Guide: https://learn.microsoft.com/en-us/sql/relational-databases/sql-server-transaction-locking-and-row-versioning-guide
- Oracle Database — Data Concurrency and Consistency: https://docs.oracle.com/en/database/oracle/oracle-database/18/cncpt/data-concurrency-and-consistency.html
- H2 Database — Transaction Isolation and MVCC: https://h2database.github.io/html/advanced.html#transaction_isolation
- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — `AbstractPlatformTransactionManager` và `validateExistingTransaction`: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html
- Spring Framework — `JdbcTransactionManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jdbc/support/JdbcTransactionManager.html
