# Điều cần kiểm chứng khi DDL hoặc câu lệnh quản trị xuất hiện trong giao dịch

Một giao dịch cơ sở dữ liệu thường được hình dung theo trình tự `BEGIN → đọc/ghi dữ liệu → COMMIT` hoặc `ROLLBACK`. Với các lệnh thao tác dữ liệu thông thường, cách hình dung này hữu ích. Nhưng khi xen vào giữa giao dịch là lệnh thay đổi cấu trúc bảng (DDL) hoặc lệnh quản trị hệ thống, **ranh giới giao dịch có thể thay đổi, lệnh có thể bị từ chối trong transaction hoặc tạo ra tác dụng không thể rollback**.

Không có một quy tắc áp dụng giống nhau cho mọi hệ quản trị cơ sở dữ liệu (DBMS). Chẳng hạn, nhiều lệnh DDL thông thường trong PostgreSQL có thể rollback theo giao dịch; phần lớn DDL trong MySQL và Oracle lại gây **implicit commit**; còn một số lệnh bảo trì hoặc quản trị chỉ được chạy bên ngoài transaction. Vì vậy, câu hỏi đúng khi đọc một đoạn mã giao dịch là: **lệnh cụ thể này, trên DBMS và phiên bản đang dùng, ảnh hưởng đến transaction hiện tại như thế nào?**

Bài học trình bày các hiện tượng cần phân biệt, các trường hợp khác nhau giữa những DBMS phổ biến và phương pháp kiểm chứng bằng thử nghiệm có kiểm soát.

## 1. DDL và lệnh quản trị liên quan gì đến vòng đời giao dịch?

Một giao dịch thông thường gồm các giai đoạn:

```text
Kết nối bắt đầu giao dịch
         |
         v
Đọc / kiểm tra / cập nhật dữ liệu
         |
         v
      COMMIT --------------------> Thay đổi được xác nhận
         |
         +--- hoặc ROLLBACK -----> Hủy các thay đổi có thể rollback
```

Khi thêm lệnh khác vào giữa chuỗi, cần phân loại:

| Nhóm lệnh | Ví dụ | Điều cần xác minh |
|---|---|---|
| **DML** (thao tác dữ liệu) | `INSERT`, `UPDATE`, `DELETE`, `SELECT` | DML đang thuộc giao dịch nào, các khóa và phiên bản dữ liệu tồn tại đến đâu? |
| **DDL** (định nghĩa cấu trúc) | `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`, `CREATE INDEX` | Có tự commit không, có rollback được không, có được chạy trong transaction không? |
| **Lệnh xóa dữ liệu theo cấu trúc** | `TRUNCATE TABLE` | Dù mục đích là xóa hàng, nhiều DBMS xử lý `TRUNCATE` theo ngữ nghĩa DDL; có thể gây commit ngầm. |
| **DCL / bảo mật** | `GRANT`, `REVOKE`, `CREATE USER` | Quyền truy cập thay đổi ở phạm vi nào, có commit ngầm không, có rollback được không? |
| **Điều khiển giao dịch** | `BEGIN`, `START TRANSACTION`, `SAVEPOINT`, `COMMIT`, `ROLLBACK`, `SET TRANSACTION` | Có kết thúc transaction cũ không, thay đổi isolation có hiệu lực khi nào? |
| **Quản trị / bảo trì** | `VACUUM`, `ALTER SYSTEM`, `ANALYZE`, `LOCK TABLES`, thay đổi cấu hình phiên | Có chạy được trong transaction không, có ảnh hưởng ngoài giao dịch hiện tại không? |

Cách xếp nhóm trong sách SQL không đủ để dự đoán hành vi thực tế. Ví dụ, `TRUNCATE` có thể rollback trong PostgreSQL và SQL Server khi thực sự nằm trong một transaction thích hợp, nhưng lại gây implicit commit trong MySQL và Oracle. Ngay trong một DBMS, các biến thể của cùng nhóm lệnh có thể khác nhau.

### Ba kết quả rất khác nhau

Đối với một lệnh xuất hiện bên trong transaction, thường cần phân biệt ít nhất ba trường hợp:

1. **Tham gia transaction:** lệnh được thực thi và có thể rollback cùng các thay đổi khác. Ví dụ, nhiều lệnh `CREATE TABLE` trong PostgreSQL.
2. **Tạo ranh giới giao dịch mới hoặc implicit commit:** những thay đổi trước đó có thể được xác nhận trước khi lệnh chạy; `ROLLBACK` về sau không hủy được chúng. Ví dụ, phần lớn DDL trong MySQL và Oracle.
3. **Bị từ chối trong transaction:** DBMS yêu cầu chạy lệnh độc lập, khiến quy trình hoặc migration bị lỗi. Ví dụ, PostgreSQL `VACUUM` và `CREATE INDEX CONCURRENTLY` không được chạy trong một explicit transaction block.

Ngoài ra còn trường hợp **lệnh không commit transaction nhưng tác dụng của chính nó không rollback được**. MySQL `CREATE TEMPORARY TABLE` là ví dụ quan trọng; xem phần riêng bên dưới.

## 2. Các khái niệm dễ bị nhầm

### 2.1. Implicit commit khác với autocommit

- **Autocommit:** chế độ mà một câu lệnh chạy độc lập sẽ được commit khi hoàn tất thành công, trừ khi có transaction tường minh đang điều khiển. Cách vận hành chi tiết phụ thuộc driver, DBMS và ứng dụng.
- **Explicit transaction:** ứng dụng bắt đầu hoặc framework quản lý một transaction gồm nhiều lệnh, nhằm chủ động `COMMIT` hoặc `ROLLBACK` ở cuối.
- **Implicit commit:** **bản thân một lệnh cụ thể** khiến DBMS xác nhận transaction hiện có, dù ứng dụng chưa gọi `COMMIT`.

Vì thế, đặt `autocommit = false` không phải cam kết mọi DDL sẽ có thể rollback. Một DDL có đặc tính implicit commit có thể cắt ngang giao dịch ngay cả khi ứng dụng đang quản lý transaction thủ công.

### 2.2. Commit trước, commit sau và câu lệnh lỗi

Ở một số DBMS, một lệnh DDL gây commit **trước khi** thực thi và một lần nữa **sau khi** thành công. Giả sử:

```text
BEGIN
UPDATE account_balance ...     <- thay đổi A
ALTER TABLE accounts ...       <- DDL
UPDATE another_table ...       <- thay đổi B
ROLLBACK
```

Nếu `ALTER TABLE` implicit commit phần giao dịch trước nó, **A đã được xác nhận**. Câu `ROLLBACK` cuối không thể lấy lại A; tác động của B tùy giao dịch mới/autocommit của phiên kết nối. Nếu DDL bị lỗi, không được mặc định rằng A còn chờ rollback: một số cơ chế vẫn có thể commit A **trước khi phát hiện lỗi DDL**.

Ngược lại, trong DBMS cho phép DDL transactional, cùng một chuỗi có thể rollback cả thay đổi cấu trúc lẫn DML, miễn là từng lệnh hỗ trợ hành vi đó.

### 2.3. "Atomic DDL" không đồng nghĩa "Transactional DDL"

Hai khái niệm sau không thay thế cho nhau:

- **Atomic DDL** nói về việc thực hiện **một thao tác DDL** một cách nhất quán, đặc biệt khi tiến trình hoặc máy chủ gặp sự cố giữa chừng. Một DDL có thể được bảo vệ ở cấp phát biểu bằng log/metadata mà không cho phép ứng dụng rollback nó.
- **Transactional DDL** nói về khả năng DDL **tham gia một transaction của người dùng** và được `COMMIT` hoặc `ROLLBACK` cùng các lệnh khác.

Ví dụ, MySQL 8.x hỗ trợ atomic DDL cho một số thao tác với InnoDB và các thành phần metadata thích hợp, nhưng điều đó **không khiến `CREATE TABLE` trở thành thao tác có thể rollback trong explicit transaction**.

## 3. PostgreSQL: nhiều DDL có thể rollback, nhưng có ngoại lệ

PostgreSQL hỗ trợ thực hiện nhiều thao tác DDL trong transaction, bao gồm các dạng `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE` và `CREATE INDEX` thông thường. Trong các trường hợp được hỗ trợ, DDL được xác nhận hoặc hủy cùng DML của giao dịch.

### 3.1. Thử nghiệm: rollback cả DML và DDL

Giả sử môi trường thử nghiệm đã có bảng:

```sql
CREATE TABLE tx_lab_log (
    id INTEGER PRIMARY KEY,
    message TEXT NOT NULL
);
```

Sau đó chạy:

```sql
BEGIN;

INSERT INTO tx_lab_log (id, message)
VALUES (101, 'temporary change');

CREATE TABLE tx_lab_created (
    id INTEGER PRIMARY KEY
);

ROLLBACK;
```

Sau `ROLLBACK`:

- Hàng `tx_lab_log.id = 101` không tồn tại nếu trước đó chưa có hàng cùng id.
- Bảng `tx_lab_created` không tồn tại vì `CREATE TABLE` cũng đã bị rollback.

Đây là ví dụ về một **DDL transactional**, chứ không phải bằng chứng rằng mọi lệnh quản trị PostgreSQL đều chạy trong transaction.

### 3.2. Những lệnh không được chạy trong transaction block

Một số ví dụ thường gặp trong PostgreSQL:

| Lệnh | Điều cần nhớ |
|---|---|
| `CREATE DATABASE` / `DROP DATABASE` | Không được thực thi bên trong transaction block. |
| `VACUUM` | Không được thực thi bên trong transaction block; `VACUUM` bảo trì dữ liệu theo cơ chế riêng. |
| `CREATE INDEX CONCURRENTLY` | Không được chạy trong explicit transaction block; dùng cơ chế tạo chỉ mục đồng thời riêng. |
| `REINDEX ... CONCURRENTLY` | Có ràng buộc transaction riêng; không chạy trong transaction block. |
| `ALTER SYSTEM` | Không được thực thi bên trong transaction block; thay đổi cấu hình máy chủ. |

Ví dụ:

```sql
BEGIN;

CREATE INDEX CONCURRENTLY idx_tx_lab_log_message
ON tx_lab_log (message);
-- PostgreSQL từ chối vì CREATE INDEX CONCURRENTLY
-- không được thực thi trong transaction block.

ROLLBACK;
```

Trong PostgreSQL, một lỗi SQL trong transaction có thể đưa transaction về trạng thái **aborted**; các lệnh tiếp theo sẽ không hoạt động bình thường cho đến khi `ROLLBACK` (hoặc xử lý qua savepoint nếu thích hợp). Nếu hệ thống migration mặc định bọc nhiều bước vào một transaction, phải tách bước `CREATE INDEX CONCURRENTLY` theo hỗ trợ cụ thể của công cụ.

### 3.3. Rollback được không đồng nghĩa ít khóa

DDL có thể cần **metadata/schema lock** hoặc khóa mạnh trên bảng. Ví dụ, nhiều biến thể `ALTER TABLE` dùng khóa ngăn đọc/ghi đồng thời trong một khoảng thời gian. Nếu transaction tạo DDL thành công rồi giữ mở rất lâu, các khóa liên quan có thể tiếp tục tồn tại đến `COMMIT`/`ROLLBACK`, gây chờ dây chuyền.

Với PostgreSQL, trước một thay đổi schema lớn nên cân nhắc:

- Phạm vi và cấp độ khóa mà **biến thể `ALTER TABLE` cụ thể** yêu cầu.
- Kích thước bảng, thời gian rewrite/scan, ảnh hưởng đến các truy vấn đang chạy.
- `lock_timeout` và `statement_timeout` phù hợp cho phiên migration, cùng kế hoạch thử lại.
- Tác động tới replication, migration song song, và các ứng dụng vẫn dùng schema cũ.

Không nên vì PostgreSQL hỗ trợ rollback DDL mà tự động gộp mọi thay đổi schema lớn vào một transaction dài.

## 4. MySQL/InnoDB: nhiều DDL implicit commit, kể cả khi đã START TRANSACTION

Với MySQL, phần lớn lệnh thay đổi cấu trúc như `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE`, `TRUNCATE TABLE`, `RENAME TABLE` và các lệnh chỉ mục liên quan sẽ gây **implicit commit**. Điều này xảy ra dù ứng dụng đã bắt đầu transaction tường minh.

### 4.1. Ví dụ: ROLLBACK không hủy dữ liệu đã commit trước DDL

Chuẩn bị trong **môi trường thử nghiệm**:

```sql
CREATE TABLE tx_lab_events (
    id INT PRIMARY KEY,
    note VARCHAR(100)
) ENGINE = InnoDB;
```

Thực hiện:

```sql
START TRANSACTION;

INSERT INTO tx_lab_events(id, note)
VALUES (1, 'before DDL');

CREATE TABLE tx_lab_other (
    id INT PRIMARY KEY
) ENGINE = InnoDB;

ROLLBACK;
```

Kết quả điển hình trên MySQL/InnoDB:

- `tx_lab_events` **vẫn chứa** hàng `id = 1` vì transaction đã bị commit ngầm khi DDL được thực thi.
- Bảng `tx_lab_other` **vẫn tồn tại**; `ROLLBACK` không hủy được DDL vừa thực hiện.
- Transaction ban đầu đã kết thúc; không nên tiếp tục giả định rằng kết nối vẫn giữ nguyên giao dịch lúc bắt đầu.

Điều cần kiểm tra không phải liệu câu `ROLLBACK` có trả về thành công hay không, mà là **dữ liệu quan sát được từ kết nối khác** sau chuỗi lệnh.

### 4.2. Ngoại lệ khó nhận biết: temporary table

Trong MySQL, `CREATE TEMPORARY TABLE` và `DROP TEMPORARY TABLE` không gây implicit commit theo cách của `CREATE TABLE` thông thường. Tuy nhiên, tác động tạo/xóa bảng tạm **không được rollback cùng transaction**.

Ví dụ:

```sql
START TRANSACTION;

CREATE TEMPORARY TABLE tx_lab_temporary (
    id INT PRIMARY KEY
);

ROLLBACK;

-- Bảng temporary vẫn có thể còn tồn tại trong session hiện tại.
-- Nó không phải bảng chia sẻ với các connection khác.
```

Đây là tình huống quan trọng: **không implicit commit** vẫn chưa đủ để suy ra **tính nguyên tử của mọi tác dụng**. Bảng tạm có vòng đời gắn với session, không giống bảng dữ liệu nghiệp vụ thông thường.

Ngoài DDL, các nhóm lệnh quản trị tài khoản/quyền, một số lệnh khóa bảng và điều khiển transaction của MySQL cũng có quy tắc implicit commit. Chẳng hạn, thay `autocommit` từ `0` sang `1` có thể commit transaction hiện hành; `START TRANSACTION` mới trong khi đang có transaction cũ cũng có thể xác nhận transaction cũ theo quy tắc MySQL. Vì vậy không nên sử dụng một lệnh cấu hình session ở giữa nghiệp vụ mà chưa đọc rõ semantics.

### 4.3. Atomic DDL của MySQL không thay thế kiểm tra ranh giới

Khi tài liệu MySQL mô tả “atomic DDL”, hãy hỏi chính xác nó bảo vệ điều gì khi có crash và metadata/data dictionary xử lý ra sao. Không được suy ra rằng:

```text
START TRANSACTION;
UPDATE business_table ...;
ALTER TABLE business_table ...;
ROLLBACK;
```

sẽ tự trả mọi thứ về trạng thái ban đầu. Trong phần lớn trường hợp DDL MySQL thường gặp, `UPDATE` phía trước đã bị commit ngầm trước `ALTER TABLE`.

## 5. Oracle Database: DDL thường kết thúc transaction hiện tại

Trong Oracle, DDL như `CREATE`, `ALTER`, `DROP`, `TRUNCATE` thường gắn với **implicit commit**. Oracle thực hiện commit transaction hiện có **trước khi thử thực thi DDL**, rồi commit thay đổi DDL sau khi thành công. Vì vậy, **DDL thất bại cũng có thể khiến DML trước đó đã được commit** do ranh giới commit trước lệnh.

Ví dụ minh họa (giả sử bảng `tx_lab_events` đã có):

```sql
INSERT INTO tx_lab_events(id, note)
VALUES (1, 'pending business change');

ALTER TABLE tx_lab_events
ADD (created_at TIMESTAMP);

ROLLBACK;
```

Một transaction DML trước DDL có thể đã được commit ngay trước `ALTER TABLE`, và thay đổi schema nếu thành công cũng không bị hủy bởi `ROLLBACK` sau đó.

Cần đặc biệt chú ý `TRUNCATE TABLE`: dù nhìn giống thao tác xóa dữ liệu, trong Oracle đây là DDL và không thể xem như `DELETE` có thể rollback theo cách thông thường. Nếu ứng dụng yêu cầu thao tác xóa có thể rollback, lựa chọn giữa `DELETE` và `TRUNCATE` phải được xác định bằng semantics và yêu cầu vận hành cụ thể, không chỉ bằng hiệu năng.

## 6. SQL Server và SQLite: các trường hợp khác cần nhớ

### 6.1. SQL Server

SQL Server cho phép **nhiều DDL thường gặp** tham gia transaction tường minh, nên một số thao tác như `CREATE TABLE` hoặc `ALTER TABLE` có thể được rollback khi đúng điều kiện. Chẳng hạn, `TRUNCATE TABLE` trong transaction SQL Server có thể rollback. Tuy nhiên, **không phải mọi lệnh quản trị hay mọi biến thể DDL đều được phép** trong transaction do người dùng khởi tạo; `CREATE DATABASE` là ví dụ về lệnh không được đặt trong explicit/user transaction theo quy tắc của SQL Server.

SQL Server còn có các chế độ giao dịch, câu lệnh quản lý session và các hạn chế riêng với thao tác quản trị, nên cần kiểm tra đúng câu lệnh đang dùng. Đừng áp dụng máy móc giả định implicit commit của MySQL hay giả định rollback mọi DDL của PostgreSQL sang SQL Server.

### 6.2. SQLite

SQLite hỗ trợ rollback nhiều thay đổi schema khi những lệnh như `CREATE TABLE`/`DROP TABLE` nằm trong **explicit transaction**. Nếu không có explicit transaction, SQLite có thể tự mở và kết thúc transaction cho từng câu lệnh.

Một số lệnh bảo trì và thiết lập đặc biệt có hạn chế khác: `VACUUM` không được chạy khi đang có transaction mở; `PRAGMA foreign_keys` không được đổi hiệu lực theo cách thông thường ở giữa một transaction. Các `PRAGMA` không có một quy tắc giao dịch chung cho mọi cấu hình.

Khi sử dụng SQLite qua ORM hoặc thư viện kết nối, nên xác minh transaction thực sự đã mở ở thời điểm DDL chạy và lệnh cấu hình nào áp dụng cho cả connection/session.

## 7. Bảng so sánh nhanh hành vi cần kiểm chứng

Bảng dưới là **định hướng cho những trường hợp phổ biến**, không phải lời bảo đảm cho mọi phiên bản, storage engine hoặc mọi dạng lệnh:

| DBMS | `CREATE/ALTER TABLE` thông thường trong explicit transaction | `TRUNCATE TABLE` | Ví dụ ngoại lệ / giới hạn |
|---|---|---|---|
| **PostgreSQL** | Phần lớn hỗ trợ rollback trong transaction | Có thể rollback khi thực hiện trong transaction | `CREATE INDEX CONCURRENTLY`, `VACUUM`, `CREATE DATABASE` không chạy trong transaction block. |
| **MySQL (InnoDB)** | Phần lớn DDL gây implicit commit; không rollback bằng transaction người dùng | Thường implicit commit, không rollback như `DELETE` | `CREATE TEMPORARY TABLE` không commit ngầm nhưng chính việc tạo bảng tạm không rollback được. |
| **Oracle Database** | DDL thường implicit commit trước và sau lệnh thành công | DDL, không rollback | DDL lỗi vẫn có thể commit DML trước đó bởi commit xảy ra trước khi thử lệnh. |
| **SQL Server** | Nhiều DDL có thể tham gia explicit transaction và rollback | Có thể rollback trong explicit transaction | `CREATE DATABASE` và một số thao tác quản trị không được chạy trong user transaction. |
| **SQLite** | Nhiều DDL hỗ trợ rollback khi có explicit transaction | Không có cú pháp `TRUNCATE TABLE` chuẩn như các DBMS trên | `VACUUM` và một số `PRAGMA` có quy tắc riêng. |

**Cùng một từ khóa không có nghĩa cùng một hợp đồng giao dịch.** Hãy tra cứu theo **tên câu lệnh đầy đủ + DBMS + phiên bản + engine/chế độ liên quan**, nhất là khi có `CONCURRENTLY`, `ONLINE`, `TEMPORARY`, `IF EXISTS` hoặc tùy chọn quản trị khác.

## 8. Câu lệnh quản trị có thể thay đổi session, khóa hoặc trạng thái hệ thống

Không phải mọi rủi ro đều đến từ schema DDL. Một số câu lệnh quản trị làm thay đổi **cách xử lý những câu lệnh tiếp theo** hoặc gây tác dụng ngoài transaction đang xét.

### 8.1. SET, autocommit và mức cô lập

Ví dụ những ý định cấu hình khác nhau:

- Thay đổi isolation level mặc định của một session.
- Thay đổi isolation chỉ cho transaction kế tiếp hoặc hiện tại, nếu DBMS cho phép.
- Bật/tắt autocommit.
- Thay đổi session SQL mode, search path, schema mặc định, timezone hoặc tham số timeout.

Cần xác định **thời điểm cấu hình bắt đầu có hiệu lực**. Ví dụ, một số DBMS yêu cầu đặt isolation level **trước khi transaction bắt đầu**; lệnh thay đổi giữa transaction có thể bị từ chối hoặc chỉ ảnh hưởng transaction sau. Một lệnh `SET` không nhất thiết commit, nhưng cũng không thể mặc định rằng mọi dạng `SET` chỉ có hiệu lực trong transaction hiện tại.

Với ứng dụng dùng **connection pool**, thay đổi session-level có thể ảnh hưởng request sau nếu trạng thái không được reset đúng. Ngược lại, cấu hình transaction-local thường kết thúc ở commit/rollback theo cơ chế của DBMS. Đọc tài liệu của cả DBMS lẫn pool/driver trước khi thay đổi session từ mã nghiệp vụ.

### 8.2. LOCK, metadata lock và thời gian chờ

DDL có thể yêu cầu khóa ở cấp schema/metadata hoặc khóa mạnh hơn DML thông thường. Những câu lệnh quản trị khóa bảng có semantics riêng, ví dụ `LOCK TABLES` trong MySQL có tương tác với transaction và implicit commit; không thể đồng nhất với `SELECT ... FOR UPDATE`.

Khi migration chạy trên bảng có lượng truy cập lớn:

```text
Request A: Transaction dài, đang đọc/ghi bảng orders
                      |
                      v
Migration B: ALTER TABLE orders ... chờ metadata/schema lock
                      |
                      v
Request C, D, E ...: có thể phải xếp hàng chờ
```

Ngay cả một DDL hỗ trợ rollback cũng có thể làm tăng độ trễ nghiêm trọng trước khi bị rollback. Cần xem cả **khả năng đảo ngược thay đổi** lẫn **tác dụng lên lưu lượng đang chạy**.

### 8.3. GRANT, REVOKE và các tác vụ cấp quyền

Thay đổi quyền, vai trò hoặc người dùng là thao tác quản trị có tác dụng đến truy cập của session khác. Hành vi commit và rollback phụ thuộc DBMS: không nên mặc định `GRANT` là DDL có implicit commit ở mọi hệ, hoặc là DML sẽ rollback được ở mọi hệ. Với migration, hãy kiểm tra thứ tự tạo đối tượng và cấp quyền, phạm vi thay đổi, session đang mở và cách xử lý nếu quá trình thất bại giữa chừng.

### 8.4. VACUUM, INDEX và bảo trì nền

Một số tác vụ bảo trì yêu cầu chạy độc lập, trong khi các tác vụ khác chấp nhận transaction nhưng tạo khóa hoặc chi phí I/O lớn. Ví dụ trong PostgreSQL:

- `VACUUM` không chạy trong transaction block.
- `CREATE INDEX` thông thường có thể transactional nhưng có thể gây chặn truy cập ở mức nhất định.
- `CREATE INDEX CONCURRENTLY` thiết kế để giảm chặn ghi trên bảng, nhưng phải chạy ngoài explicit transaction block và có những trạng thái thất bại cần xử lý riêng.

Do đó không thể nói chung “mọi lệnh CREATE đều giống nhau” hoặc “mọi lệnh bảo trì đều implicit commit”.

## 9. Vì sao annotation @Transactional hoặc BEGIN không đủ chứng minh an toàn?

Một ứng dụng Java/Spring có thể dùng `@Transactional` để khai báo ranh giới giao dịch:

```java
@Transactional
public void changeBusinessDataAndSchema() {
    jdbcTemplate.update(
        "UPDATE application_config SET flag = ? WHERE id = ?",
        true, 1
    );
    jdbcTemplate.execute(
        "ALTER TABLE application_config ADD COLUMN extra_info VARCHAR(50)"
    );
    throw new IllegalStateException("Something failed");
}
```

Ý định của lập trình viên có thể là: “method ném exception thì Spring rollback tất cả”. Thực tế phải kiểm chứng:

1. Spring có thực sự mở transaction cho lời gọi này hay không, và các lệnh có dùng **cùng connection/DataSource** hay không?
2. Với DBMS đang dùng, `ALTER TABLE` có **implicit commit** hay tham gia transaction?
3. Exception có khiến transaction manager cố rollback không; tại thời điểm đó có những thay đổi nào **đã commit** vì DBMS?
4. Nếu có thao tác ở connection khác, executor migration khác hoặc tác vụ bất đồng bộ, chúng thuộc transaction nào?

Chẳng hạn, khi chạy trên MySQL, khả năng `ALTER TABLE` implicit commit có thể khiến cập nhật phía trước đã được xác nhận trước khi exception xảy ra; việc Spring gọi rollback về sau **không thể đảo ngược thay đổi đã commit**. Trên PostgreSQL, nhiều DDL thông thường có thể rollback cùng transaction nếu đúng bối cảnh.

`@Transactional` là cơ chế quản lý transaction ở tầng ứng dụng; nó **không thay đổi semantics của lệnh SQL do DBMS quyết định**. Việc hàm có chạy qua transaction proxy, propagation được chọn ra sao và driver có đưa mọi câu lệnh vào đúng transaction hay không vẫn là điều phải kiểm chứng.

## 10. Quy trình kiểm chứng trước khi đưa DDL hoặc lệnh quản trị vào luồng giao dịch

### Bước 1: Liệt kê chính xác từng lệnh và mục đích

Không ghi chung chung “có thay đổi schema”. Hãy xác định:

- Câu SQL đầy đủ và loại biến thể, ví dụ `CREATE INDEX` so với `CREATE INDEX CONCURRENTLY`.
- DBMS, phiên bản, storage engine và cấu hình liên quan.
- Lệnh được thực thi bởi ứng dụng, SQL script, migration tool, job quản trị hay DBA.
- Kết quả mong muốn nếu lệnh **thành công**, **thất bại**, **timeout** hoặc connection đứt giữa chừng.

### Bước 2: Vẽ ranh giới transaction thực tế

Đánh dấu lần bắt đầu, các điểm commit có thể xảy ra, câu lệnh chạy trên connection nào và bước nào có tác dụng ngoài DB:

```text
Connection 1:
  BEGIN
  UPDATE ...          [A: dự kiến chưa commit]
  DDL / ADMIN ...     [B: có commit ngầm? bị từ chối? rollback được?]
  INSERT ...          [C: thuộc transaction nào?]
  ROLLBACK            [D: thực sự hủy được A, B, C đến đâu?]

Connection 2:
  SELECT ...          [Quan sát được A ở thời điểm nào?]
```

Không chỉ dựa vào lời gọi `BEGIN` ở đầu đoạn mã hoặc câu `ROLLBACK` ở cuối. Nếu DDL đã gây implicit commit, “transaction gốc” có thể không còn tồn tại ở thời điểm đó.

### Bước 3: Tra cứu tài liệu theo đúng sản phẩm

Cần tìm trong tài liệu chính thức của DBMS các mục như **implicit commit statements**, **transactional DDL**, **statements disallowed in transaction blocks**, **autocommit**, **lock behavior** và **DDL recovery**.

Những câu hỏi cụ thể gồm:

| Điều cần hỏi | Vì sao quan trọng? |
|---|---|
| Lệnh này có implicit commit **trước** khi chạy không? | DML đã thực hiện trước đó có thể mất khả năng rollback. |
| Lệnh có implicit commit **sau** khi chạy không? | DDL có thể được xác nhận thành một đơn vị riêng. |
| Nếu lệnh thất bại, DML phía trước có bị commit không? | Không thể chỉ suy luận bằng nhánh bắt exception. |
| Nếu chạy trong transaction, DBMS từ chối hay cho phép? | Migration có thể lỗi ngay ở bước triển khai. |
| Bản thân tác dụng DDL có rollback được không? | Không implicit commit vẫn có thể có tác dụng ngoài rollback. |
| Lệnh giữ những khóa nào, trong bao lâu? | Có thể làm nghẽn truy cập dù thay đổi cuối cùng bị rollback. |
| Thao tác ảnh hưởng session hiện tại hay toàn hệ thống? | Thay đổi có thể sống lâu hơn transaction hoặc ảnh hưởng connection pool. |
| Tác dụng sau crash, restart hoặc failover ra sao? | Khả năng phục hồi DDL khác với rollback ở tầng ứng dụng. |

### Bước 4: Thử trên môi trường tách biệt bằng hai connection

Nên dựng một schema/bảng **chỉ dành cho thử nghiệm**, không dùng bảng nghiệp vụ đang có dữ liệu quan trọng. Một thí nghiệm minh bạch gồm:

1. Trên **connection A**, tạo dữ liệu ban đầu để có điểm so sánh.
2. Bắt đầu transaction mới trên A, ghi một **hàng đánh dấu** chưa commit.
3. Chạy đúng DDL hoặc lệnh quản trị cần kiểm chứng.
4. Trên **connection B**, đọc hàng đánh dấu theo isolation thích hợp để xem nó đã **được commit** chưa.
5. Trên A, chạy `ROLLBACK` hoặc kích hoạt lỗi có kiểm soát.
6. Trên B, đọc lại hàng đánh dấu và kiểm tra schema; ghi nhận kết quả có phụ thuộc kiểu lỗi hay không.
7. Nếu lệnh là DDL có khóa, thêm một transaction thử nghiệm khác để quan sát **chờ khóa/timeout** mà không ảnh hưởng dịch vụ thật.

Cần **đọc từ connection khác** vì giao dịch có thể nhìn thấy thay đổi chưa commit của chính nó. Nếu chỉ đọc lại trên A trước khi rollback, kết quả chưa chứng minh đã có implicit commit.

Ví dụ mẫu nhận định:

```text
A: BEGIN
A: INSERT marker(42)
A: <câu lệnh cần kiểm chứng>
B: SELECT marker(42)  -> thấy / không thấy?
A: ROLLBACK
B: SELECT marker(42)  -> còn / không còn?
B: kiểm tra đối tượng DDL -> tồn tại / không tồn tại?
```

Kết quả thí nghiệm chỉ có giá trị cho **DBMS, phiên bản, cách kết nối, lệnh và cấu hình đã thử**. Khi nâng cấp hệ quản trị hoặc đổi migration tool, cần xem lại những giả định có thể bị ảnh hưởng.

### Bước 5: Kiểm tra đường chạy của migration framework

Các công cụ migration như Flyway hoặc Liquibase có thể nhóm nhiều câu lệnh vào một transaction **khi DBMS và thao tác cho phép**, đồng thời có tùy chọn chạy non-transactional riêng. Hành vi phụ thuộc version, database support, nội dung migration và cấu hình.

Vì vậy cần xác nhận:

- Công cụ có mặc định bọc toàn bộ migration vào transaction không?
- DDL chứa trong migration có implicit commit không?
- Migration có pha lẫn lệnh transactional với non-transactional không; công cụ có cho phép không?
- Nếu lỗi ở giữa, bảng ghi lịch sử migration báo gì và **schema/data thực tế** đang ở trạng thái nào?
- Cách sửa một migration đã chạy một phần: khôi phục, tiếp tục có kiểm soát hay tạo migration bổ sung?

Một dòng lịch sử báo “migration failed” không đủ để suy ra toàn bộ thao tác trước đó đã rollback.

### Bước 6: Thiết kế khả năng phục hồi

Trước khi chạy DDL/lệnh quản trị có thể commit độc lập, cần chuẩn bị:

- Kế hoạch **backup và restore** thích hợp với mức độ rủi ro; rollback ở ứng dụng không thay thế phục hồi dữ liệu.
- Thứ tự triển khai có thể chịu được ứng dụng cũ và mới cùng tồn tại khi schema chuyển tiếp.
- Những bước DML cần chạy lại idempotent hoặc có marker để biết đã thực thi đến đâu.
- Cơ chế xử lý khi thao tác chỉ thành công một phần, bị timeout hoặc client mất kết nối trước khi nhận kết quả.
- Quan sát lock wait, deadlock, timeout, thời gian migration, log lỗi và trạng thái đối tượng DB.

Không nên chạy thử các lệnh phá hủy bảng, cấu hình máy chủ hoặc cấp quyền bằng tài khoản production chỉ để “xem có rollback không”.

## 11. Tình huống tổng hợp: vừa sửa dữ liệu vừa thay đổi schema

Giả sử nhóm triển khai tính năng mới với hai bước:

1. Chỉnh các hàng dữ liệu cũ để thêm trạng thái mặc định.
2. Thêm cột `status` vào bảng.

Một script có thể được viết như sau:

```sql
BEGIN;

UPDATE orders
SET note = 'migration-started'
WHERE note IS NULL;

ALTER TABLE orders
ADD COLUMN status VARCHAR(20);

ROLLBACK;
```

Có thể người viết dự kiến dùng `ROLLBACK` như công tắc “hủy toàn bộ migration khi không hài lòng”. Nhưng kết quả giữa các hệ thống khác nhau:

- **PostgreSQL:** với DDL bình thường được hỗ trợ, cả cập nhật `note` và thêm `status` có thể rollback cùng giao dịch.
- **MySQL:** `ALTER TABLE` thường gây implicit commit; cập nhật `note` phía trước có thể đã được xác nhận và thay đổi schema không bị hủy bởi `ROLLBACK`.
- **Oracle:** DDL thường implicit commit trước khi thực thi; kể cả DDL lỗi, thay đổi DML trước đó có thể đã được commit.
- **SQL Server:** nhiều DDL được phép trong explicit transaction và rollback được, nhưng cần kiểm tra đúng lệnh và điều kiện cụ thể.

Đây là lý do **một SQL script không thể được xem là có cùng “bảo đảm rollback” trên mọi database**.

Một hướng tổ chức triển khai an toàn hơn thường là **tách thay đổi schema khỏi các giao dịch nghiệp vụ đang xử lý request**, với các pha rõ ràng:

1. **Expand:** thêm schema theo cách tương thích ngược, hạn chế chặn dịch vụ.
2. **Backfill:** cập nhật dữ liệu theo lô có kiểm soát, mỗi lô có thể chạy lại khi thất bại.
3. **Switch:** chuyển ứng dụng sang sử dụng schema mới khi dữ liệu đã đủ điều kiện.
4. **Contract:** chỉ xóa cột/ràng buộc cũ sau khi chắc chắn không còn consumer phụ thuộc.

Cách tổ chức này không làm DDL trở nên transactional. Nó giúp giảm thời gian khóa, làm rõ ranh giới commit và xây dựng kế hoạch phục hồi khi các bước phải commit riêng.

## 12. Các ngộ nhận cần tránh

| Ngộ nhận | Cách hiểu chính xác |
|---|---|
| “Đã có `BEGIN` nên mọi SQL ở giữa đều rollback được.” | Phải xác minh từng lệnh có implicit commit, hỗ trợ transaction hoặc tạo tác dụng ngoài rollback không. |
| “DDL thì lúc nào cũng implicit commit.” | PostgreSQL, SQL Server và SQLite hỗ trợ nhiều dạng DDL transactional; vẫn có ngoại lệ. |
| “DDL của PostgreSQL đều chạy được trong transaction.” | `VACUUM`, `CREATE INDEX CONCURRENTLY`, `CREATE DATABASE` và một số lệnh khác có giới hạn. |
| “MySQL 8 có atomic DDL nên `ROLLBACK` sẽ hủy `ALTER TABLE`.” | Atomic DDL ở cấp phát biểu/khả năng phục hồi không đồng nghĩa transactional DDL trong transaction người dùng. |
| “DDL báo lỗi thì DML trước đó chắc chắn rollback được.” | DBMS có thể đã implicit commit **trước khi thử chạy DDL**. |
| “Không có implicit commit nghĩa là rollback mọi thứ.” | `CREATE TEMPORARY TABLE` trong MySQL là phản ví dụ. |
| “`TRUNCATE` giống `DELETE` nhưng nhanh hơn.” | Ngữ nghĩa giao dịch, trigger, khóa, cấp phát lưu trữ và nhiều tác dụng khác khác nhau tùy DBMS. |
| “`@Transactional` của Spring bảo đảm rollback cả SQL và lệnh quản trị.” | Framework quản lý transaction trong phạm vi hỗ trợ; semantics của DBMS và kết nối vẫn quyết định kết quả. |
| “Lệnh chạy nhanh nên không ảnh hưởng các giao dịch khác.” | DDL có thể chờ hoặc giữ khóa schema/metadata, gây xếp hàng truy vấn. |
| “Migration failed nghĩa là database vẫn nguyên vẹn.” | Phải kiểm tra cả dữ liệu, schema, trạng thái transaction và lịch sử migration thực tế. |

## 13. Ghi nhớ để áp dụng

Khi DDL hoặc lệnh quản trị xuất hiện giữa vòng đời giao dịch, cần xác định ba ranh giới:

**Ranh giới commit:** có lệnh nào tự xác nhận transaction đang mở hay không, và nếu lỗi thì DML trước lệnh đã ở trạng thái nào?

**Ranh giới rollback:** thay đổi cấu trúc, dữ liệu, quyền, cấu hình session hoặc thao tác quản trị nào thực sự có thể được hủy cùng transaction?

**Ranh giới tác động:** câu lệnh chỉ ảnh hưởng dữ liệu trong giao dịch, hay còn ảnh hưởng khóa bảng, metadata, session khác, replication, cấu hình máy chủ hoặc hệ thống bên ngoài?

**Nguyên tắc thực hành:** tra cứu semantics của **câu lệnh chính xác trên DBMS/phiên bản chính xác**, thử với hai kết nối trong môi trường riêng và ghi lại điểm commit/rollback thực tế. Chỉ khi đó mới có thể quyết định nên đặt DDL trong transaction, chạy migration độc lập, hay tách quy trình thành những bước có thể phục hồi an toàn.
