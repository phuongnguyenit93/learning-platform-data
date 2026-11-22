# DDL, TRUNCATE và khác biệt về implicit commit trong giao dịch SQL

Một lập trình viên có thể tự tin với quy tắc quen thuộc: **`BEGIN` mở giao dịch, `COMMIT` lưu thay đổi, `ROLLBACK` hủy thay đổi**. Quy tắc này đúng cho nhiều thao tác `INSERT`, `UPDATE`, `DELETE` trên bảng có hỗ trợ giao dịch. Nhưng khi xen **DDL** như `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE` hoặc lệnh **`TRUNCATE`**, kết quả có thể khác hoàn toàn tùy hệ quản trị cơ sở dữ liệu.

Ví dụ, hãy tưởng tượng đoạn lệnh:

```sql
BEGIN;
INSERT INTO audit_log (message) VALUES ('Preparing cleanup');
TRUNCATE TABLE staging_data;
ROLLBACK;
```

Người viết có thể nghĩ `ROLLBACK` sẽ hủy cả dòng log mới và thao tác làm rỗng `staging_data`. Tuy nhiên:

- **PostgreSQL:** `TRUNCATE` trong một transaction có thể được rollback, cùng những thay đổi dữ liệu bình thường trong transaction đó.
- **SQL Server Database Engine:** `TRUNCATE TABLE` cũng có thể rollback trong một transaction rõ ràng, với các hạn chế áp dụng cho bảng.
- **MySQL/MariaDB:** `TRUNCATE TABLE` là thao tác DDL gây **implicit commit**, làm kết thúc transaction đang mở; `ROLLBACK` về sau không khôi phục bảng vừa truncate.
- **Oracle Database:** `TRUNCATE TABLE` gây commit ngầm trước và sau thao tác DDL thành công; không thể dùng `ROLLBACK` để lấy lại các hàng đã truncate.
- **SQLite:** không có câu lệnh `TRUNCATE TABLE` trong cú pháp SQL thông dụng; thay bằng `DELETE FROM table`, thao tác có thể rollback nếu nằm trong transaction rõ ràng.

Vì vậy, bài toán cần hiểu không phải “`TRUNCATE` nhanh hơn `DELETE` bao nhiêu”, mà là **thao tác nào thực sự nằm trong transaction nào, lúc nào transaction bị commit ngầm, và liệu schema hoặc dữ liệu có thể rollback hay không**.

Bài học thuộc chương **Giao dịch SQL** của module **Database SQL**, tập trung vào bốn khái niệm: DDL, `TRUNCATE`, implicit commit và khác biệt giữa các DBMS. Các ví dụ được tách theo phương ngữ và thiết kế cho **cơ sở dữ liệu thử nghiệm**; không chạy lệnh `DROP` hay `TRUNCATE` với dữ liệu cần giữ.

## 1. Phân biệt DDL, DML và câu lệnh điều khiển giao dịch

SQL thường được chia thành những nhóm lệnh để học:

| Nhóm | Ví dụ | Vai trò |
|---|---|---|
| **DDL** (*Data Definition Language*) | `CREATE`, `ALTER`, `DROP`, `RENAME` | Tạo, đổi hoặc xóa cấu trúc/đối tượng cơ sở dữ liệu |
| **DML** (*Data Manipulation Language*) | `INSERT`, `UPDATE`, `DELETE` | Thêm, cập nhật, xóa dữ liệu hàng |
| **TCL** (*Transaction Control Language*) | `BEGIN`/`START TRANSACTION`, `COMMIT`, `ROLLBACK`, `SAVEPOINT` | Xác lập hoặc điều khiển ranh giới transaction |
| **DQL** (cách phân loại giảng dạy phổ biến) | `SELECT` | Đọc dữ liệu |
| **DCL** (*Data Control Language*) | `GRANT`, `REVOKE` | Quyền truy cập, với hành vi giao dịch riêng từng DBMS |

Các nhãn trên hữu ích để tổ chức kiến thức, nhưng **không phải hợp đồng về giao dịch**. Đặc biệt, `TRUNCATE` thường được xem là thao tác **DDL hoặc DDL-like**, dù mục đích của nó là làm rỗng dữ liệu.

Không thể suy rằng:

- “DDL chắc chắn không rollback được” — sai với nhiều lệnh DDL trong PostgreSQL và SQL Server.
- “Có `BEGIN` là mọi lệnh ở giữa đều rollback được” — sai với MySQL/Oracle khi gặp DDL gây commit ngầm.
- “`TRUNCATE` đụng dữ liệu nên có ngữ nghĩa transaction như `DELETE`” — sai ở nhiều hệ.
- “`TRUNCATE` là DDL nên mọi hệ đều implicit commit” — cũng sai, vì PostgreSQL và SQL Server có rollback cho thao tác này.

**Phải kiểm tra chính xác DBMS, phiên bản và loại lệnh**, không chỉ nhóm DDL/DML.

## 2. Giao dịch tường minh, autocommit và implicit commit

Ba thuật ngữ dễ bị trộn lẫn:

### 2.1. Giao dịch tường minh (*explicit transaction*)

Người viết chủ động mở và đóng giao dịch:

```sql
BEGIN;

UPDATE accounts
SET balance = balance - 100
WHERE account_id = 1;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 2;

COMMIT;
```

Ví dụ mang tính mô tả; chuyển tiền thật cần thêm điều kiện số dư, khóa, kiểm tra số hàng, chống ghi trùng và mức cô lập phù hợp.

Nếu hệ quản trị hỗ trợ giao dịch với các bảng này, trước `COMMIT` ta có thể `ROLLBACK` để bỏ cả hai cập nhật.

### 2.2. Autocommit

Ở chế độ **autocommit**, mỗi statement thành công thường được thực thi trong một transaction riêng và commit khi statement kết thúc. Ví dụ:

```sql
INSERT INTO logs (message) VALUES ('A');
INSERT INTO logs (message) VALUES ('B');
```

Nếu hai câu được gửi trong chế độ autocommit, câu đầu có thể đã commit trước khi câu thứ hai chạy. Vì thế `ROLLBACK` gửi sau đó không thể quay lại transaction đã hoàn tất.

**Autocommit là chính sách quản lý transaction ở kết nối/driver/session**, không nhất thiết là commit do bản thân câu DDL gây ra.

### 2.3. Implicit commit do một câu lệnh

**Implicit commit** trong bài này là trường hợp hệ quản trị **tự kết thúc giao dịch đang mở**, như thể có câu `COMMIT`, khi chạy một loại lệnh nhất định.

Ví dụ mô hình MySQL/Oracle:

```text
START TRANSACTION
    |
    +-- INSERT A           (chưa commit)
    |
    +-- UPDATE B           (chưa commit)
    |
    +-- DDL / TRUNCATE
          |
          +-- IMPLICIT COMMIT các thay đổi A, B
          |
          +-- Thực hiện DDL theo cơ chế riêng
          |
          +-- DDL được hoàn tất/commit theo quy tắc engine
    |
    +-- ROLLBACK           (không thể hủy A, B đã commit)
```

Điểm nguy hiểm không chỉ là `TRUNCATE` **không rollback được**, mà còn là **những thay đổi DML trước `TRUNCATE` có thể bị commit ngoài ý muốn**.

### 2.4. Autocommit và implicit commit khác nhau ở điểm nào?

| Tình huống | Nguyên nhân commit | Ý nghĩa |
|---|---|---|
| `INSERT` chạy riêng khi autocommit bật | Chế độ kết nối quản lý mỗi statement như một transaction | Không có transaction dài cần giữ |
| `COMMIT` | Người viết yêu cầu tường minh | Lưu transaction hiện tại |
| `ALTER TABLE` trong MySQL khi transaction đã mở | Lệnh DDL buộc commit ngầm | Các DML trước đó có thể được lưu dù chưa gọi COMMIT |
| `TRUNCATE TABLE` trong Oracle | DDL có implicit commit | Không thể hủy truncate bằng ROLLBACK |
| `TRUNCATE` trong PostgreSQL bên trong `BEGIN` | Không tự kết thúc transaction vì tên lệnh | Có thể rollback các thay đổi liên quan |
| `TRUNCATE TABLE` trong SQL Server bên trong `BEGIN TRAN` | Tham gia transaction rõ ràng | Có thể rollback |

Một transaction đã **commit** thì không “rollback ngược thời gian” bằng một lệnh mới. Muốn khôi phục sau commit thường cần backup/PITR, lưu lịch sử hoặc thao tác bù với những giới hạn riêng.

## 3. Transactional DDL khác atomic DDL

Một nhầm lẫn phổ biến là thấy tài liệu ghi **atomic DDL** rồi nghĩ lệnh DDL nằm trong transaction ứng dụng và có thể rollback như `UPDATE`.

Hai khái niệm khác nhau:

**Transactional DDL:** thay đổi schema có thể tham gia vào transaction do người dùng điều khiển; nếu transaction rollback thì bản thân thay đổi schema được hoàn tác. PostgreSQL hỗ trợ nhiều dạng DDL kiểu này. SQL Server Database Engine cũng hỗ trợ giao dịch cho nhiều thao tác DDL, với những ngoại lệ.

**Atomic DDL:** một thao tác DDL được thiết kế **thành công toàn bộ hoặc không để lại trạng thái metadata/storage nửa vời**, kể cả khi server gặp sự cố ở giữa, theo phạm vi mà engine hỗ trợ. Điều đó **không đồng nghĩa** người dùng có thể gói DDL với nhiều DML khác vào một transaction rồi `ROLLBACK` tất cả.

| Tình huống | Transactional DDL | Atomic DDL |
|---|---|---|
| Người dùng `BEGIN` → `ALTER TABLE` → `ROLLBACK` | Có thể đưa schema về trạng thái cũ nếu hỗ trợ | Không tự bảo đảm khả năng rollback theo ý người dùng |
| Server crash giữa `ALTER TABLE` | Cần cơ chế phục hồi tương ứng | Mục tiêu là không để lại nửa thay đổi được công bố |
| DML trước DDL có bị commit ngầm? | Không phải đặc tính bắt buộc | Vẫn có thể bị commit ngầm |
| MySQL 8.x/InnoDB | Nhiều DDL gây implicit commit | Hỗ trợ atomic DDL cho những thao tác phù hợp |
| MariaDB 10.6+ | Nhiều DDL vẫn implicit commit | Có cải tiến atomic/crash-safe DDL theo phiên bản |

**Câu ghi nhớ:** *“Atomic DDL không đồng nghĩa transactional DDL.”* Đừng dùng lời hứa **crash-safe** làm bằng chứng `ROLLBACK` sẽ hủy được `CREATE`, `ALTER` hay `TRUNCATE` trong MySQL/MariaDB.

## 4. DDL nào thường cần kiểm tra?

Ví dụ thay đổi cấu trúc:

```sql
CREATE TABLE demo_items (
    item_id INTEGER PRIMARY KEY,
    item_name VARCHAR(100)
);

ALTER TABLE demo_items
ADD COLUMN category VARCHAR(50);

CREATE INDEX idx_demo_items_name
ON demo_items (item_name);

DROP TABLE demo_items;
```

Những thao tác này có thể ảnh hưởng metadata, chỉ mục, khóa, bảng dữ liệu hoặc khả năng truy cập của phiên khác.

Các nhóm thường cần lưu ý:

- `CREATE TABLE`, `DROP TABLE`.
- `ALTER TABLE`: thêm/xóa cột, đổi kiểu, đổi ràng buộc.
- `CREATE INDEX`, `DROP INDEX`.
- `RENAME TABLE` hoặc đổi tên đối tượng.
- `TRUNCATE TABLE`.
- `CREATE VIEW`, `DROP VIEW` và một số thay đổi quyền/schema khác.

Không phải **mọi** DDL trong một DBMS đều có cùng đặc tính. Ví dụ PostgreSQL cho rollback nhiều thao tác DDL thông thường, nhưng **`CREATE DATABASE`**, `VACUUM` và `CREATE INDEX CONCURRENTLY` không được chạy trong transaction block theo quy tắc tương ứng. SQL Server cũng có những lệnh không được phép bên trong user transaction, như một số thao tác ở cấp database.

**Không suy từ một câu `CREATE TABLE` chạy được trong transaction ra quy tắc cho mọi lệnh DDL.**

## 5. TRUNCATE, DELETE và DROP: giống hoặc khác ở đâu?

Ba câu sau có thể trông đều là “xóa”:

```sql
DELETE FROM demo_items;

TRUNCATE TABLE demo_items;

DROP TABLE demo_items;
```

Nhưng khác về phạm vi và hành vi.

| Tiêu chí | `DELETE FROM t` | `TRUNCATE TABLE t` | `DROP TABLE t` |
|---|---|---|---|
| Mục tiêu | Xóa hàng thỏa điều kiện | Làm rỗng toàn bộ bảng/đối tượng được chỉ định | Xóa định nghĩa bảng và dữ liệu |
| Hỗ trợ `WHERE` | Có | Không | Không |
| Giữ bảng để `INSERT` tiếp | Có | Có | Không |
| Có thể kích hoạt DELETE row triggers | Có, theo DBMS/schema | Thường không | Không theo nghĩa DELETE từng hàng |
| Cơ chế xử lý | Thao tác xóa hàng | Thường giải phóng/đặt lại vùng lưu trữ, không duyệt mỗi hàng | Hủy đối tượng |
| Số hàng trả về | Có thể là số hàng thực sự bị xóa | Có thể không phản ánh số hàng cũ | Không phải số hàng đã DELETE |
| Reset identity/auto-increment | Thường không tự reset | Tùy DBMS và tùy chọn; nhiều hệ reset | Đối tượng bị loại bỏ |
| Rollback | Thông thường có trên bảng transactional | **Rất khác theo DBMS** | **Rất khác theo DBMS** |
| Tác động FK | Kiểm tra/cascade theo từng hàng | Có nhiều hạn chế với bảng được tham chiếu | Có ràng buộc phụ thuộc/giới hạn riêng |

`DELETE FROM t` không có `WHERE` cũng xóa toàn bộ hàng, nhưng **không tự biến thành `TRUNCATE`** về trigger, identity, logging hay transaction. Một số DBMS có tối ưu vật lý riêng; ngữ nghĩa SQL của câu vẫn là `DELETE`.

`TRUNCATE` không hỗ trợ “xóa các dòng trước ngày X”. Nếu cần lọc theo thời gian, trạng thái hoặc tenant, dùng `DELETE ... WHERE ...` hay chính sách partition phù hợp, không viết:

```sql
-- SAI: TRUNCATE thông thường không có WHERE.
TRUNCATE TABLE demo_items WHERE created_at < '2026-01-01';
```

## 6. PostgreSQL: DDL và TRUNCATE có thể rollback

PostgreSQL nổi bật ở chỗ nhiều DDL thông thường **tham gia transaction do người dùng mở**. Trong đó, `TRUNCATE` được tài liệu PostgreSQL xác nhận là **transaction-safe đối với dữ liệu của bảng**.

### 6.1. Tạo dữ liệu thử trước transaction

```sql
-- PostgreSQL: chạy ở phiên thử, giả định autocommit mặc định.
CREATE TEMP TABLE demo_pg_items (
    item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_name TEXT NOT NULL
);

INSERT INTO demo_pg_items (item_name)
VALUES ('A'), ('B'), ('C');

SELECT COUNT(*) AS before_count
FROM demo_pg_items;
-- 3
```

Bảng là `TEMP` để giảm nguy cơ tác động dữ liệu thật. Ba hàng này đã có trước bài thử rollback.

### 6.2. ROLLBACK khôi phục cả dữ liệu lẫn TRUNCATE

```sql
BEGIN;

INSERT INTO demo_pg_items (item_name)
VALUES ('D');

SELECT COUNT(*) AS count_before_truncate
FROM demo_pg_items;
-- 4

TRUNCATE TABLE demo_pg_items;

SELECT COUNT(*) AS count_after_truncate
FROM demo_pg_items;
-- 0 trong transaction hiện tại

ROLLBACK;

SELECT item_id, item_name
FROM demo_pg_items
ORDER BY item_id;
-- Lại có A, B, C. Không có D.
```

Cách đọc:

1. Bên ngoài giao dịch thử, bảng có **3 hàng**.
2. Trong giao dịch, chèn `D` làm số hàng tạm thời thành **4**.
3. `TRUNCATE` làm bảng rỗng trong transaction, nhìn thấy **0 hàng** tại phiên hiện tại.
4. `ROLLBACK` hủy thao tác thêm `D` và hủy `TRUNCATE`.
5. Bảng lại có ba hàng ban đầu.

Vì thế câu “`TRUNCATE` luôn không rollback được” là **sai khi nói về PostgreSQL**.

### 6.3. DDL thông thường cũng có thể rollback

Một ví dụ khác, chạy trên cùng bảng `demo_pg_items`:

```sql
BEGIN;

ALTER TABLE demo_pg_items
ADD COLUMN category TEXT DEFAULT 'general';

UPDATE demo_pg_items
SET category = 'test';

ROLLBACK;

-- Sau rollback:
-- 1) Các dòng A, B, C vẫn còn.
-- 2) Cột category mới thêm không còn thuộc schema.
SELECT item_id, item_name
FROM demo_pg_items
ORDER BY item_id;
```

Trong PostgreSQL, thay đổi DDL được hỗ trợ ở ví dụ này nằm trong transaction, nên rollback hủy cả **ALTER** lẫn **UPDATE**.

Đừng thử `SELECT category` sau rollback như thể cột vẫn có thật; PostgreSQL sẽ báo cột không tồn tại, điều đó là hệ quả dự kiến của rollback schema.

### 6.4. Không phải mọi DDL PostgreSQL đều chạy trong BEGIN

Một số lệnh bị cấm trong transaction block, chẳng hạn:

```sql
-- PostgreSQL: KHÔNG chạy trong một BEGIN ... COMMIT block.
CREATE DATABASE demo_new_database;
```

Các ví dụ khác cần kiểm tra là `CREATE INDEX CONCURRENTLY`, `VACUUM` và `ALTER SYSTEM`. Từng lệnh có lý do riêng. Kết luận đúng là **“nhiều DDL PostgreSQL transactional, không phải mọi DDL PostgreSQL”**.

### 6.5. TRUNCATE mặc định không reset identity trong PostgreSQL

PostgreSQL có các tùy chọn:

```sql
TRUNCATE TABLE demo_pg_items CONTINUE IDENTITY;
```

và:

```sql
TRUNCATE TABLE demo_pg_items RESTART IDENTITY;
```

- `CONTINUE IDENTITY` là **mặc định**: không yêu cầu reset các sequence gắn với cột bảng.
- `RESTART IDENTITY` yêu cầu khởi động lại những sequence **được sở hữu bởi các cột của bảng bị truncate**.
- Với PostgreSQL hiện đại, việc restart sequence do `TRUNCATE ... RESTART IDENTITY` thực hiện **cũng có thể rollback** cùng transaction.

Ví dụ:

```sql
BEGIN;

TRUNCATE TABLE demo_pg_items RESTART IDENTITY;

INSERT INTO demo_pg_items (item_name)
VALUES ('Temp after restart');

-- Trong transaction, sequence có thể đã cấp lại từ đầu.
ROLLBACK;

-- Bảng lại có A, B, C.
-- Thao tác restart sequence do TRUNCATE được hoàn tác.
```

**Không đồng nhất điều này với mọi hoạt động sequence:** các lệnh cấp số kiểu `nextval()` thông thường có đặc tính không rollback theo từng lần dùng; `currval()` ở session cũng có những khác biệt sau rollback. Không xây quy tắc “mọi ID sẽ liên tục trở lại như chưa từng có câu lệnh nào” từ ví dụ trên.

### 6.6. ON TRUNCATE trigger khác ON DELETE trigger

Trong PostgreSQL:

- `TRUNCATE` **không kích hoạt `ON DELETE` triggers**.
- PostgreSQL có thể kích hoạt **`ON TRUNCATE` triggers** nếu được định nghĩa.
- `DELETE FROM t` dùng cơ chế trigger của DELETE theo khai báo.

Nếu audit của bạn chỉ nằm trong `AFTER DELETE` trigger, việc đổi từ `DELETE` sang `TRUNCATE` có thể làm **mất đường audit dự kiến**. Cần hiểu toàn bộ trigger, FK và quyền trước khi tối ưu.

### 6.7. TRUNCATE và FK: cẩn thận với CASCADE

Giả sử bảng `orders` tham chiếu `customers` bằng FK. PostgreSQL có thể từ chối `TRUNCATE customers` nếu bảng khác đang tham chiếu nó và không được truncate cùng.

```sql
-- PostgreSQL: chỉ minh họa cú pháp, không chạy trên dữ liệu thật.
TRUNCATE TABLE customers RESTRICT;
```

`RESTRICT` là mặc định: từ chối nếu có bảng liên quan qua FK cần được xử lý.

```sql
-- CẢNH BÁO: CASCADE có thể làm rỗng thêm toàn bộ bảng phụ thuộc.
TRUNCATE TABLE customers CASCADE;
```

`CASCADE` ở đây không có nghĩa “chỉ xóa đơn của những khách đã xóa”, bởi `TRUNCATE` là thao tác **toàn bảng**. Nó có thể truncate **toàn bộ bảng tham chiếu** và các bảng phụ thuộc liên quan. Hãy xem danh sách phụ thuộc trước khi dùng trong môi trường thật.

### 6.8. Transactional không có nghĩa MVCC-safe

PostgreSQL ghi rõ `TRUNCATE` **không MVCC-safe** theo cùng ý nghĩa với `DELETE` thông thường. Sau khi truncate commit, một transaction đồng thời đang dùng snapshot cũ có thể thấy bảng rỗng trong một số hoàn cảnh dù snapshot được tạo trước lúc truncate. Điều này liên quan tới việc transaction đó đã truy cập/giữ khóa bảng trước khi DDL bắt đầu hay chưa.

Đồng thời `TRUNCATE` giữ khóa bảng `ACCESS EXCLUSIVE`, ngăn nhiều hoạt động đồng thời trên bảng trong lúc thao tác đang diễn ra.

Vì thế:

- `TRUNCATE` có thể **ROLLBACK** trong PostgreSQL.
- Nhưng không thể suy rằng nó có **cùng hành vi concurrency/MVCC và mức khóa** như `DELETE`.
- Transaction dài chứa `TRUNCATE` có thể chặn đọc/ghi khác.

**Rollback được không đồng nghĩa thao tác an toàn khi hệ thống đang có lưu lượng thật.**

## 7. MySQL: DDL gây implicit commit, TRUNCATE không rollback

Với MySQL trên storage engine transactional phổ biến như **InnoDB**, những DML thông thường tham gia giao dịch. Nhưng **nhiều DDL** như `CREATE TABLE`, `ALTER TABLE`, `DROP TABLE` và `TRUNCATE TABLE` gây commit ngầm.

Tài liệu MySQL mô tả: những câu lệnh này thường **commit giao dịch đang mở trước khi chạy**, và phần lớn cũng có commit theo quy tắc sau khi thao tác hoàn tất. Vì vậy, không nên chèn DDL vào một transaction chứa các DML mà muốn bảo đảm all-or-nothing.

### 7.1. Ví dụ nhìn thấy DML bị commit ngoài ý muốn

Để phân biệt ảnh hưởng của `TRUNCATE` với các thay đổi ở bảng khác, dùng **hai bảng độc lập** trong cơ sở dữ liệu thử:

```sql
-- MySQL/InnoDB: chạy ngoài transaction thử.
CREATE TABLE demo_mysql_items (
    item_id INT PRIMARY KEY,
    item_name VARCHAR(50) NOT NULL
) ENGINE = InnoDB;

CREATE TABLE demo_mysql_audit (
    audit_id INT PRIMARY KEY,
    message VARCHAR(100) NOT NULL
) ENGINE = InnoDB;

INSERT INTO demo_mysql_items (item_id, item_name)
VALUES (1, 'baseline');

START TRANSACTION;

INSERT INTO demo_mysql_audit (audit_id, message)
VALUES (1, 'Uncommitted audit');

INSERT INTO demo_mysql_items (item_id, item_name)
VALUES (2, 'pending');

-- DDL: gây implicit commit, làm rỗng bảng items.
TRUNCATE TABLE demo_mysql_items;

-- Không đảo ngược DDL hoặc DML đã commit trước nó.
ROLLBACK;

SELECT COUNT(*) AS audit_rows
FROM demo_mysql_audit;
-- 1

SELECT COUNT(*) AS item_rows
FROM demo_mysql_items;
-- 0
```

Giải thích:

1. `START TRANSACTION` mở transaction.
2. Hai câu `INSERT` tạo thay đổi đang chờ commit.
3. `TRUNCATE TABLE` làm **implicit commit trước**, vì thế hàng audit cũng được lưu.
4. `TRUNCATE` làm rỗng bảng items theo cơ chế DDL của MySQL.
5. `ROLLBACK` sau đó **không thể hủy thao tác đã commit**.
6. Bảng audit còn một hàng; bảng items rỗng.

Đây là ví dụ quan trọng vì nó chỉ ra **implicit commit ảnh hưởng cả những lệnh trước đó**, không chỉ thao tác xóa dữ liệu.

### 7.2. ALTER TABLE cũng có thể commit các INSERT trước đó

```sql
-- MySQL/InnoDB; giả sử bảng demo_mysql_audit đã tạo sẵn.
START TRANSACTION;

INSERT INTO demo_mysql_audit (audit_id, message)
VALUES (2, 'Before ALTER');

ALTER TABLE demo_mysql_items
ADD COLUMN note VARCHAR(100) NULL;

ROLLBACK;

-- Hàng audit_id=2 vẫn được commit bởi ALTER.
-- Cột note đã thêm cũng không bị ROLLBACK bỏ đi.
```

Một kế hoạch “rollback nếu migration thất bại” **không hiệu lực theo cùng cách** như PostgreSQL nếu có DDL gây commit ngầm ở MySQL.

### 7.3. MySQL 8.x atomic DDL không giải quyết vấn đề này

MySQL 8.0/8.4 với InnoDB hỗ trợ cơ chế **atomic DDL** cho các thao tác thích hợp, hướng đến nhất quán metadata/storage/binlog khi có lỗi hoặc crash. Nhưng tài liệu MySQL nêu rõ **atomic DDL không phải transactional DDL theo ý người dùng**.

Không viết:

```sql
START TRANSACTION;
ALTER TABLE demo_mysql_items ADD COLUMN temporary_note VARCHAR(20);
ROLLBACK;
```

rồi giả định schema trở lại trạng thái cũ. `ALTER TABLE` thông thường đã gây commit ngầm.

### 7.4. Ngoại lệ CREATE TEMPORARY TABLE: không commit nhưng không rollback được

MySQL có ngoại lệ quan trọng:

```sql
-- MySQL: CREATE TEMPORARY TABLE không tự gây implicit commit.
START TRANSACTION;

INSERT INTO demo_mysql_audit (audit_id, message)
VALUES (3, 'Will roll back');

CREATE TEMPORARY TABLE demo_mysql_stage (
    id INT PRIMARY KEY
);

ROLLBACK;

-- Hàng audit_id=3 được rollback (giả sử không có commit khác).
-- Bảng tạm demo_mysql_stage vẫn tồn tại trong session.
```

Hai thuộc tính khác nhau:

- `CREATE TEMPORARY TABLE` và `DROP TEMPORARY TABLE` **không gây implicit commit** trong những trường hợp MySQL được tài liệu mô tả.
- Nhưng sự kiện **tạo/xóa đối tượng temporary** đó **không được rollback** như DML thông thường.

Đây là ví dụ cho thấy **“không implicit commit” không tự động đồng nghĩa “DDL transactional”**.

Lưu ý: **`ALTER TABLE` và `CREATE INDEX` trên bảng tạm** vẫn có thể gây implicit commit theo quy tắc MySQL; không mở rộng ngoại lệ của `CREATE TEMPORARY TABLE` ra mọi DDL trên temp table.

### 7.5. TRUNCATE bảng tạm vẫn implicit commit

Không viết:

```sql
START TRANSACTION;
TRUNCATE TABLE demo_mysql_stage;
ROLLBACK;
```

với kỳ vọng vì bảng là `TEMPORARY` thì `TRUNCATE` được rollback. MySQL/MariaDB vẫn xử lý `TRUNCATE TABLE` như một thao tác gây implicit commit, **kể cả đối tượng tạm** theo các quy tắc tài liệu liên quan.

### 7.6. Ràng buộc của TRUNCATE trên MySQL

MySQL/InnoDB có các đặc điểm thường gặp:

- `TRUNCATE TABLE` làm rỗng **toàn bộ** bảng, không có `WHERE`.
- Thường đặt lại bộ đếm `AUTO_INCREMENT`.
- Không thực hiện các row-level `DELETE` triggers như `DELETE`.
- Có hạn chế khi bảng được tham chiếu bởi FK từ bảng khác; self-reference có quy tắc riêng.
- Không xem `TRUNCATE` là lời hứa “không dùng log” hoặc “không khóa”.
- Xử lý transactional khác tùy storage engine; ví dụ MyISAM không có rollback DML như InnoDB.

Khi dữ liệu quan trọng, việc thay `DELETE FROM t` bằng `TRUNCATE t` không chỉ đổi tốc độ: nó đổi **khả năng rollback, implicit commit và hành vi identity/trigger**.

## 8. MariaDB: tương tự về implicit commit, nhưng phải xem phiên bản

MariaDB có nhiều điểm tương đồng với MySQL, nhưng là hệ quản trị phát triển độc lập. Tài liệu MariaDB liệt kê `TRUNCATE TABLE`, nhiều `CREATE`/`ALTER`/`DROP` và các lệnh quản trị khác trong nhóm gây **implicit commit trước khi thực thi**.

Ví dụ mô hình:

```sql
-- MariaDB/InnoDB; giả sử bảng đã tồn tại.
START TRANSACTION;

UPDATE demo_orders
SET status = 'ARCHIVED'
WHERE order_id = 10;

TRUNCATE TABLE demo_import_stage;

ROLLBACK;
```

**Không được giả định** `ROLLBACK` sẽ hủy cập nhật ở `demo_orders` hoặc khôi phục dữ liệu `demo_import_stage`. Nếu `TRUNCATE` đã gây commit ngầm, phần cập nhật trước nó có thể đã được commit.

Đồng thời:

- MariaDB cũng có những ngoại lệ đối với `CREATE TEMPORARY TABLE`/`DROP TEMPORARY TABLE`.
- `TRUNCATE TABLE` vẫn gây implicit commit, kể cả khi đối tượng tạm.
- MariaDB 10.6+ có cải tiến **atomic/crash-safe DDL**, nhưng không có nghĩa mọi DDL trở thành một phần transaction do ứng dụng có thể rollback.
- Cách xử lý với các storage engine và phiên bản có thể khác MySQL; luôn kiểm tra hệ đích.

Một số câu `ANALYZE`, `OPTIMIZE` hay thao tác quyền/khóa cũng có thể tác động đến transaction theo quy tắc engine. Không giới hạn việc kiểm tra implicit commit chỉ ở ba từ `CREATE`, `ALTER`, `DROP`.

## 9. Oracle Database: COMMIT trước và sau DDL

Oracle Database có quy tắc rõ về DDL: **thực hiện implicit commit trước DDL**, sau đó commit khi DDL thành công hoặc rollback phần của chính DDL nếu thất bại ở giai đoạn thực thi phù hợp. **Các DML đã commit trước DDL không được rollback lại**.

### 9.1. Ví dụ TRUNCATE trong Oracle

Chuẩn bị trên **schema thử**, không sử dụng bảng quan trọng:

```sql
-- Oracle Database
CREATE TABLE demo_oracle_items (
    item_id NUMBER PRIMARY KEY,
    item_name VARCHAR2(50) NOT NULL
);

CREATE TABLE demo_oracle_audit (
    audit_id NUMBER PRIMARY KEY,
    message VARCHAR2(100) NOT NULL
);

INSERT INTO demo_oracle_items (item_id, item_name)
VALUES (1, 'baseline');

COMMIT;
```

Thực hiện:

```sql
INSERT INTO demo_oracle_audit (audit_id, message)
VALUES (1, 'Pending DML');

INSERT INTO demo_oracle_items (item_id, item_name)
VALUES (2, 'temporary');

-- Oracle: DDL gây commit ngầm và không rollback được.
TRUNCATE TABLE demo_oracle_items;

ROLLBACK;

SELECT COUNT(*) FROM demo_oracle_audit;
-- 1: dòng audit đã commit trước TRUNCATE.

SELECT COUNT(*) FROM demo_oracle_items;
-- 0: bảng đã bị truncate.
```

Khác biệt so với PostgreSQL là rất lớn: **`ROLLBACK` sau `TRUNCATE` không khôi phục hai hàng**; lệnh `INSERT` ở bảng audit cũng không bị hủy vì đã được commit trước khi Oracle thực thi DDL.

### 9.2. Nếu câu DDL thất bại thì sao?

Ví dụ có một `INSERT` chưa commit, sau đó chạy `ALTER TABLE` nhưng bị lỗi vì tên cột trùng hoặc ràng buộc không hợp lệ.

Trong Oracle, với một câu DDL đã được nhận diện/được thực thi tới giai đoạn liên quan, **implicit commit trước DDL có thể đã xảy ra**. Nếu thao tác DDL thất bại ở giai đoạn thực thi, Oracle rollback **thay đổi của câu DDL đó**, nhưng **không rollback những DML đã được commit ngay trước DDL**.

Không khái quát rằng **mọi chuỗi ký tự SQL sai cú pháp** đều chắc chắn gây commit — lỗi phát hiện lúc parser chưa chấp nhận DDL có thể khác. Bài học thực hành là: **không dùng khả năng DDL sẽ báo lỗi để bảo vệ transaction DML đang mở**.

### 9.3. TRUNCATE của Oracle không thể ROLLBACK hay FLASHBACK TABLE đơn giản

Tài liệu Oracle về `TRUNCATE TABLE` ghi rõ không thể rollback lệnh này; cũng không thể dùng `FLASHBACK TABLE` để đưa bảng về nội dung trước truncate theo cơ chế thường thấy.

Vì vậy, khi cần khôi phục, phải dựa vào chiến lược backup, phục hồi tại thời điểm, bản sao dữ liệu hoặc công cụ phục hồi chuyên biệt được cấu hình **trước** sự cố, không chỉ mở SQL Developer rồi gửi `ROLLBACK`.

### 9.4. Không nhầm DELETE với TRUNCATE

```sql
-- Oracle: DELETE là DML, có thể rollback trước COMMIT.
DELETE FROM demo_oracle_items
WHERE item_id = 1;

ROLLBACK;
```

Nếu `DELETE` nằm trong transaction chưa commit, thao tác có thể được hoàn tác. Trái lại:

```sql
-- Oracle: TRUNCATE là DDL, không rollback được.
TRUNCATE TABLE demo_oracle_items;
ROLLBACK;
```

không đưa dữ liệu về trạng thái trước `TRUNCATE`.

Oracle cũng có hạn chế với bảng cha đang được tham chiếu qua FK, quyền và phụ thuộc. `TRUNCATE` không phải một đường “bỏ qua mọi ràng buộc” hợp lệ.

## 10. SQL Server Database Engine: TRUNCATE có thể rollback

Một điểm gây nhầm lẫn lớn: **SQL Server có thể rollback `TRUNCATE TABLE` khi nó được thực hiện trong transaction**, mặc dù lệnh này không xóa từng hàng như `DELETE`.

### 10.1. Ví dụ dùng BEGIN TRANSACTION

```sql
-- SQL Server Database Engine: chạy trong database thử.
CREATE TABLE dbo.demo_sqlserver_items (
    item_id INT PRIMARY KEY,
    item_name NVARCHAR(50) NOT NULL
);

INSERT INTO dbo.demo_sqlserver_items (item_id, item_name)
VALUES (1, N'A'), (2, N'B');

BEGIN TRANSACTION;

INSERT INTO dbo.demo_sqlserver_items (item_id, item_name)
VALUES (3, N'C');

TRUNCATE TABLE dbo.demo_sqlserver_items;

SELECT COUNT(*) AS during_transaction
FROM dbo.demo_sqlserver_items;
-- 0

ROLLBACK TRANSACTION;

SELECT item_id, item_name
FROM dbo.demo_sqlserver_items
ORDER BY item_id;
-- 1/A và 2/B; không còn hàng 3/C.
```

Trong transaction:

1. Chèn hàng 3.
2. Truncate toàn bộ bảng.
3. `ROLLBACK TRANSACTION` hoàn tác cả thao tác chèn và truncate.

Do đó, **không đúng** khi nói “TRUNCATE trong SQL Server luôn commit ngầm như Oracle”.

### 10.2. Nhiều DDL SQL Server cũng transactional, nhưng có ngoại lệ

SQL Server cho phép thực hiện nhiều DDL thông thường như `CREATE TABLE`/`ALTER TABLE` trong transaction, tùy loại thao tác và môi trường. Nhưng không phải mọi DDL hay sản phẩm thuộc hệ sinh thái Microsoft đều hỗ trợ cùng phạm vi:

- Một số lệnh cấp database hoặc thao tác bảo trì có giới hạn về explicit transaction.
- `TRUNCATE TABLE` bị hạn chế với một số bảng có foreign key, indexed view, replication hoặc temporal table.
- **Azure Synapse Analytics** có quy tắc `TRUNCATE` khác SQL Server Database Engine, trong đó tài liệu nêu không được chạy `TRUNCATE` trong transaction ở môi trường đó.
- Không lấy thành công của một ví dụ trên SQL Server Database Engine để kết luận mọi dịch vụ SQL/cloud có cùng hành vi.

### 10.3. TRUNCATE trong SQL Server không giống DELETE

Các điểm thường gặp trong SQL Server Database Engine:

- `TRUNCATE TABLE` không hỗ trợ `WHERE`.
- Thường dùng logging theo **phân bổ trang/extents**, ít ghi log hơn việc xóa từng hàng; không có nghĩa hoàn toàn không ghi log.
- Không kích hoạt `DELETE` triggers vì không phát sinh các thao tác xóa từng hàng theo cùng cơ chế.
- Thường đặt lại giá trị **IDENTITY** về seed của cột.
- Có thể rollback trong transaction.
- Sử dụng khóa bảng/schema như `SCH-M`, có thể gây chờ/block các phiên truy cập khác.
- Có những hạn chế với FK tham chiếu từ bảng khác, ngoại lệ với FK tự tham chiếu theo tài liệu.

Với bảng lớn, deallocation có thể diễn ra theo giai đoạn, trong đó không phải mọi không gian trống được trả lại tức thì khi câu SQL kết thúc.

### 10.4. Autocommit vẫn có hiệu lực nếu không mở transaction

Nếu chỉ chạy:

```sql
TRUNCATE TABLE dbo.demo_sqlserver_items;
```

ngoài một explicit transaction và với chính sách autocommit thông thường, statement thành công có thể đã commit khi kết thúc. `ROLLBACK` gửi sau đó không quay lại được transaction đã hoàn thành.

Khả năng **TRUNCATE hỗ trợ rollback trong transaction** không có nghĩa mọi `TRUNCATE` đã chạy đều có thể rollback vô thời hạn.

## 11. SQLite: không có lệnh TRUNCATE TABLE

SQLite không hỗ trợ cú pháp `TRUNCATE TABLE table_name` theo kiểu PostgreSQL/MySQL/SQL Server/Oracle. Nếu mục tiêu là làm rỗng bảng, dùng:

```sql
DELETE FROM demo_sqlite_items;
```

Trong transaction SQLite, thao tác xóa này có thể rollback:

```sql
-- SQLite: cơ sở dữ liệu thử.
CREATE TABLE demo_sqlite_items (
    item_id INTEGER PRIMARY KEY,
    item_name TEXT NOT NULL
);

INSERT INTO demo_sqlite_items (item_id, item_name)
VALUES (1, 'A'), (2, 'B');

BEGIN;

DELETE FROM demo_sqlite_items;

SELECT COUNT(*) AS during_transaction
FROM demo_sqlite_items;
-- 0

ROLLBACK;

SELECT item_id, item_name
FROM demo_sqlite_items
ORDER BY item_id;
-- 1/A và 2/B.
```

### 11.1. SQLite DDL có thể nằm trong transaction

SQLite cũng cho phép nhiều thao tác schema trong transaction, với rollback:

```sql
BEGIN;

ALTER TABLE demo_sqlite_items
ADD COLUMN note TEXT;

DELETE FROM demo_sqlite_items;

ROLLBACK;

-- Sau rollback, hai hàng A/B vẫn tồn tại
-- và cột note vừa thêm không còn trong schema.
PRAGMA table_info(demo_sqlite_items);
```

Không suy rằng vì SQLite hỗ trợ rollback DDL trong explicit transaction nên `CREATE` ngoài transaction sẽ chờ mãi tới một `COMMIT` thủ công. SQLite có cơ chế **transaction tự khởi tạo** khi chạy SQL; một statement có thể tự mở và hoàn thành transaction nếu ứng dụng không giữ transaction tường minh.

### 11.2. SQLite có “truncate optimization” nhưng đó vẫn là DELETE

SQLite có một tối ưu nội bộ gọi là **truncate optimization**. Theo tài liệu SQLite, khi một câu `DELETE` không có `WHERE`, không có `RETURNING` và bảng không có trigger, engine có thể xóa nội dung bảng bằng cơ chế tối ưu không cần đi qua từng hàng giống cách xóa thông thường.

```sql
-- SQLite: cú pháp vẫn là DELETE, không phải TRUNCATE TABLE.
DELETE FROM demo_sqlite_items;
```

**Tên tối ưu không đổi ngữ nghĩa giao dịch:** câu lệnh vẫn là `DELETE`, có thể rollback trong transaction, không tự mang quy tắc implicit commit của MySQL/Oracle `TRUNCATE`.

Nếu thêm trigger, `RETURNING` hoặc điều kiện lọc, phạm vi tối ưu có thể thay đổi. Không dựa vào “truncate optimization” để khẳng định mọi lệnh `DELETE FROM t` trong SQLite đều dùng một kế hoạch vật lý duy nhất.

### 11.3. Không tự reset AUTOINCREMENT bằng cách DELETE toàn bảng

SQLite có `INTEGER PRIMARY KEY` và chế độ `AUTOINCREMENT` với cơ chế theo dõi số đã dùng. `DELETE FROM t` không tương đương câu lệnh “reset mọi sequence/identity” của những hệ quản trị khác. Nếu dùng `AUTOINCREMENT`, cần hiểu bảng `sqlite_sequence` và quy tắc cấp rowid trước khi quyết định tái sử dụng ID.

Trong hệ thống thật, tốt hơn là **không yêu cầu ID liên tiếp hay reset về 1** như một phần của việc dọn dữ liệu; khóa chính là danh tính, không phải số thứ tự để hiển thị.

## 12. Bảng đối chiếu các DBMS

| Hệ quản trị | DDL `CREATE/ALTER/DROP` thông thường | `TRUNCATE` | ROLLBACK `TRUNCATE` trong explicit transaction? |
|---|---|---|---|
| **PostgreSQL** | Nhiều thao tác transactional, với ngoại lệ theo lệnh | Có; hỗ trợ `CONTINUE/RESTART IDENTITY`, `CASCADE/RESTRICT` | **Có** |
| **MySQL/InnoDB** | Nhiều DDL gây implicit commit; atomic DDL ≠ rollback do user | Có; DDL, thường reset AUTO_INCREMENT | **Không** |
| **MariaDB/InnoDB** | Nhiều DDL implicit commit; đặc điểm crash-safe tùy phiên bản | Có; gây implicit commit | **Không** |
| **Oracle Database** | Commit ngầm trước và sau DDL theo quy tắc | Có; DDL, không `WHERE` | **Không** |
| **SQL Server Database Engine** | Nhiều DDL tham gia transaction, nhưng có ngoại lệ | Có; logging/khóa riêng, reset IDENTITY | **Có** |
| **SQLite** | DDL có thể rollback trong explicit transaction | **Không có cú pháp TRUNCATE TABLE** | Không áp dụng; `DELETE FROM t` có thể rollback |

Đọc bảng với những giới hạn sau:

1. Không có chuyện “mọi DDL trong PostgreSQL/SQL Server đều transactional”.
2. SQL Server Database Engine không đồng nhất với mọi dịch vụ Azure/Synapse/Fabric.
3. MySQL/MariaDB chịu ảnh hưởng storage engine, phiên bản và tính năng temporary table.
4. Hành vi rollback còn phụ thuộc **statement có thực sự nằm trong transaction chưa commit hay không**.
5. “Có thể rollback” không nói gì về mức khóa, chi phí log, tác động trigger, FK hay an toàn vận hành.

## 13. Các timeline so sánh dễ nhớ

Giả sử đã có một bảng `items` có 2 hàng và bảng `audit` rỗng. Ta chạy ý tưởng:

```sql
BEGIN;
INSERT INTO audit VALUES (...);
TRUNCATE TABLE items;
ROLLBACK;
```

Cùng ý định nhưng kết quả khác nhau theo engine:

| DBMS | Sau ROLLBACK, audit còn dòng mới? | Sau ROLLBACK, items còn 2 hàng cũ? |
|---|---|---|
| PostgreSQL | **Không** | **Có** |
| SQL Server Database Engine | **Không** | **Có** |
| MySQL/InnoDB | **Có** do implicit commit trước TRUNCATE | **Không** |
| MariaDB/InnoDB | **Có** do implicit commit | **Không** |
| Oracle Database | **Có** do implicit commit trước DDL | **Không** |
| SQLite | Dùng `DELETE FROM items` thay cho TRUNCATE → **không** | Với `DELETE` trong transaction → **có** |

**Giả định:** các bảng thử có kiểu/ràng buộc tương ứng, lệnh chạy thành công, không có tác động khác từ trigger, không có giao dịch khác và cơ chế commit bình thường. Không xem bảng này là dự đoán cho mọi lệnh DDL khác ngoài ví dụ.

### 13.1. “BEGIN” trên từng hệ cũng không hoàn toàn giống nhau

| DBMS | Cách mở transaction thường gặp |
|---|---|
| PostgreSQL | `BEGIN;` hoặc `START TRANSACTION;` |
| MySQL/MariaDB | `START TRANSACTION;` hoặc `BEGIN;` theo ngữ cảnh SQL |
| SQL Server | `BEGIN TRANSACTION;`/`BEGIN TRAN;` |
| Oracle | Transaction DML thường bắt đầu ngầm; có `SET TRANSACTION` để đặt thuộc tính, không dùng `BEGIN;` SQL đơn giản theo nghĩa PostgreSQL |
| SQLite | `BEGIN;`, `BEGIN IMMEDIATE;`, `BEGIN EXCLUSIVE;` |

Vì vậy, khi chuyển ví dụ, điều chỉnh **lệnh mở transaction** và chính sách driver, không copy nguyên một script trên mọi hệ.

## 14. SAVEPOINT có giúp cứu lại transaction sau implicit commit không?

`SAVEPOINT` cho phép đánh dấu vị trí trong transaction trên những DBMS hỗ trợ:

```sql
BEGIN;

INSERT INTO demo_items (item_id, item_name)
VALUES (10, 'A');

SAVEPOINT before_change;

UPDATE demo_items
SET item_name = 'B'
WHERE item_id = 10;

ROLLBACK TO SAVEPOINT before_change;

COMMIT;
```

Ở hệ hỗ trợ cú pháp/transaction tương ứng, đoạn này có thể giữ hàng 10 với tên `A` vì chỉ cập nhật sau savepoint bị hủy.

Nhưng nếu một câu DDL ở MySQL/Oracle đã **implicit commit**, transaction và các savepoint của transaction trước đó đã kết thúc. Khi ấy, `ROLLBACK TO SAVEPOINT ...` không phải cơ chế quay về trước DDL.

**Điều kiện để savepoint có tác dụng là nó vẫn thuộc một transaction đang tồn tại và phần thay đổi muốn hoàn tác là transactional.** Không thể sử dụng savepoint để lách quy tắc commit ngầm của DDL.

### 14.1. PostgreSQL: savepoint với DDL thông thường

Trong PostgreSQL, một số DDL transactional có thể được hoàn tác về savepoint:

```sql
-- PostgreSQL; giả sử demo_pg_items tồn tại.
BEGIN;

SAVEPOINT before_alter;

ALTER TABLE demo_pg_items
ADD COLUMN note TEXT;

ROLLBACK TO SAVEPOINT before_alter;

-- Cột note đã được hủy ở transaction hiện tại.
COMMIT;
```

Đây là ví dụ về rollback schema trong một transaction hỗ trợ, không phải chỉ rollback DML.

### 14.2. MySQL: implicit commit xóa ranh giới savepoint trước đó

```sql
-- MySQL: KHÔNG kỳ vọng rollback về savepoint sau DDL.
START TRANSACTION;

SAVEPOINT before_ddl;

ALTER TABLE demo_mysql_items
ADD COLUMN extra_note VARCHAR(40);

-- Transaction trước ALTER đã bị kết thúc bởi implicit commit.
-- ROLLBACK TO SAVEPOINT before_ddl sẽ không cứu thay đổi đó.
```

Không dùng cùng một chiến thuật rollback schema cho hai DBMS này.

## 15. Cảnh báo đặc biệt: DDL thất bại vẫn có thể commit DML trước đó

Đây là tình huống gây mất an toàn về mặt nghiệp vụ:

```text
Ứng dụng:
1) UPDATE 100 đơn hàng ở trạng thái PENDING.
2) ALTER TABLE thêm cột.
3) ALTER TABLE lỗi do cột đã tồn tại.
4) ROLLBACK rồi báo "đã hủy hết".
```

Trong **MySQL/MariaDB/Oracle**, bước 2 có thể đã **commit DML ở bước 1 trước khi phát hiện lỗi thực thi của DDL**. `ROLLBACK` ở bước 4 sẽ không hủy được 100 cập nhật.

Không nên giải quyết chỉ bằng `TRY/CATCH`/`catch(SQLException)`:

- Code bắt lỗi biết statement thất bại, **không chứng minh transaction trước nó chưa commit**.
- Một script migration cần hiểu **ranh giới commit của từng câu**.
- Một công cụ migration có tùy chọn “run in transaction” cũng không thể ép server cho rollback DDL nếu engine không hỗ trợ.
- Cần kế hoạch khôi phục độc lập nếu thao tác DDL/`TRUNCATE` không rollback được.

Đồng thời, **lỗi cú pháp bị chặn ngay từ parser** không nhất thiết có cùng thời điểm commit như lỗi DDL trong giai đoạn thực thi. Tránh suy ngược từ một ví dụ thất bại duy nhất thành quy tắc cho mọi lỗi.

## 16. JDBC và ứng dụng Java: setAutoCommit(false) không thắng implicit commit

Giả sử Java dùng JDBC:

```java
Connection connection = dataSource.getConnection();
connection.setAutoCommit(false);

try {
    // DML thay đổi dữ liệu.
    try (PreparedStatement update = connection.prepareStatement(
            "UPDATE orders SET status = 'ARCHIVED' WHERE created_at < ?")) {
        update.setDate(1, java.sql.Date.valueOf("2026-01-01"));
        update.executeUpdate();
    }

    // Thao tác schema/cleanup.
    try (Statement ddl = connection.createStatement()) {
        ddl.executeUpdate("TRUNCATE TABLE import_stage");
    }

    // Nếu xảy ra lỗi sau đó:
    connection.rollback();
} finally {
    connection.close();
}
```

Đây là **đoạn mã minh họa nguy cơ**, không phải mẫu an toàn để dùng nguyên trong sản xuất. Đoạn code chưa có cấu trúc catch/rollback đầy đủ cho mọi nhánh ngoại lệ và giả định các bảng tồn tại.

- Với **PostgreSQL** hoặc **SQL Server Database Engine** (qua driver và câu transaction phù hợp), `TRUNCATE` có thể tham gia transaction do ứng dụng mở và rollback.
- Với **MySQL/MariaDB** hoặc **Oracle**, chính server có thể thực hiện **implicit commit** khi gặp `TRUNCATE`; `setAutoCommit(false)` không biến DDL thành rollbackable.
- Với **SQLite**, câu `TRUNCATE TABLE` không hợp lệ; phải dùng `DELETE FROM import_stage` và kiểm soát transaction tương ứng.

**Không coi API `rollback()` đã được gọi thành công là bằng chứng mọi thay đổi trước đó đã được hủy.** Server có thể đã hoàn tất một transaction trước khi driver gửi `rollback()`.

### 16.1. Vì sao dùng migration tool vẫn cần hiểu DBMS?

Các công cụ như Flyway hoặc Liquibase có thể tổ chức migration, lưu lịch sử schema và quản lý giao dịch khi DBMS cho phép. Nhưng công cụ **không thay đổi luật commit của MySQL/Oracle**.

Một migration nhiều bước:

```text
1. UPDATE data ...
2. ALTER TABLE ...
3. INSERT metadata ...
```

có thể là một đơn vị rollback tương đối thuận lợi trong PostgreSQL nếu mọi statement được hỗ trợ trong transaction. Trên MySQL/Oracle, bước `ALTER TABLE` có thể commit bước trước; nếu bước 3 lỗi, rollback không tự khôi phục bước 1 hoặc 2.

Trong hệ không hỗ trợ transactional DDL theo nhu cầu, cần migration có khả năng **chạy lại an toàn**, backup, bản phục hồi hoặc **compensating migration** được thiết kế và kiểm thử riêng. Không coi “reverse SQL” luôn khôi phục được dữ liệu đã truncate.

### 16.2. Tách giao dịch nghiệp vụ khỏi thay đổi schema

Một thiết kế an toàn hơn là:

- Hoàn tất hoặc rollback **transaction nghiệp vụ** trước khi chạy migration schema.
- Chạy DDL như một giai đoạn triển khai riêng, có phê duyệt và kế hoạch phục hồi.
- Không trộn `TRUNCATE` staging với những DML quan trọng chưa commit nếu hệ có implicit commit.
- Nếu cần làm rỗng dữ liệu nhưng phải rollback được, cân nhắc **`DELETE` trong bảng transactional** và đo chi phí, hoặc dùng bảng/partition thay thế theo cơ chế DBMS.
- Dùng migration có các giai đoạn **expand → migrate data → contract**, tránh drop cột ngay khi ứng dụng vẫn đang dùng.

## 17. TRUNCATE có thể làm mất dữ liệu theo cách nào ngoài implicit commit?

Hiểu quy tắc commit mới chỉ là một phần. `TRUNCATE` còn nhiều rủi ro khác.

### 17.1. Không hỗ trợ WHERE

Không thể giới hạn từng hàng theo ngày, trạng thái hoặc tenant như `DELETE`. Trong hệ multi-tenant có nhiều tenant chung bảng, `TRUNCATE TABLE orders` có thể xóa **mọi tenant**.

Nếu muốn dọn tenant 42:

```sql
-- Mẫu DML phù hợp hơn cho thao tác có bộ lọc.
DELETE FROM orders
WHERE tenant_id = 42
  AND created_at < DATE '2026-01-01';
```

Ví dụ literal ngày theo PostgreSQL/DBMS hỗ trợ cú pháp tương ứng; MySQL/SQL Server/SQLite có thể cần điều chỉnh. Việc có `WHERE` không bảo đảm xóa an toàn nếu tenant_id được lấy từ client không tin cậy; cần ràng buộc quyền.

### 17.2. Hành vi trigger khác DELETE

Một hệ thống audit dựa trên `AFTER DELETE FOR EACH ROW` có thể **không ghi log từng hàng** khi dùng `TRUNCATE`. Trong PostgreSQL có `ON TRUNCATE` trigger riêng. SQL Server và MySQL cũng phân biệt thao tác này với row-level DELETE triggers. Oracle `TRUNCATE` không phải quy trình xóa từng hàng để kích hoạt DELETE trigger như DML.

Nếu audit/legal retention phụ thuộc trigger, không được thay DELETE bằng TRUNCATE chỉ vì tiết kiệm thời gian.

### 17.3. Reset ID có thể ảnh hưởng quan hệ bên ngoài

MySQL, MariaDB và SQL Server thường reset giá trị auto increment/identity theo quy tắc TRUNCATE; PostgreSQL cho chọn `CONTINUE IDENTITY` hoặc `RESTART IDENTITY`. Một hệ ngoài có thể vẫn giữ ID cũ và xem ID tái sử dụng là cùng thực thể, gây nhầm lẫn.

Khóa chính là định danh; không dùng `TRUNCATE` như cách “dọn bộ đếm ID cho đẹp” khi có dữ liệu liên quan ở ngoài bảng.

### 17.4. Foreign key và phụ thuộc

Các DBMS có thể từ chối truncate bảng đang được bảng khác tham chiếu. PostgreSQL có `CASCADE` với phạm vi rất rộng. SQL Server, Oracle, MySQL có các quy tắc khác nhau; không mặc định chỉ cần tắt FK là có thể khôi phục an toàn.

### 17.5. Khóa và chặn hoạt động đồng thời

TRUNCATE thường phải lấy khóa mạnh trên bảng hoặc metadata. Một thao tác rất nhanh về CPU có thể vẫn chặn nhiều truy vấn đang chạy hoặc làm queue ghi kéo dài.

Ví dụ PostgreSQL giữ `ACCESS EXCLUSIVE`; SQL Server dùng các khóa bảng/schema. Với MySQL/MariaDB còn có metadata lock và cơ chế engine. Cần theo dõi lock waits và đặt khung thời gian chạy khi dọn dữ liệu lớn.

### 17.6. “Ít logging” không phải “không logging”

`TRUNCATE` thường hiệu quả vì không xóa và log từng hàng như `DELETE`, nhưng engine vẫn cần metadata/log phục hồi phù hợp. Nói `TRUNCATE` “không tạo log” là quá đơn giản và có thể sai.

## 18. Quy trình dọn bảng an toàn khi chưa biết DBMS

Một kịch bản triển khai thực tế có thể làm theo những bước sau.

### Bước 1: Xác định đúng sản phẩm và phiên bản

Ví dụ câu hỏi:

- PostgreSQL 14/15/16/17/18 hay một dịch vụ tương thích?
- MySQL 8.x/InnoDB hay storage engine khác?
- MariaDB phiên bản nào?
- SQL Server Database Engine, Azure SQL Database hay Synapse?
- Oracle Database bản nào?
- SQLite phiên bản nào và hoạt động qua driver gì?

Không chỉ nhìn phần mở rộng file `.sql` rồi suy ra transaction semantics.

### Bước 2: Xác định chính xác lệnh nào sẽ chạy

Phân loại rõ:

```sql
DELETE FROM t WHERE condition;
DELETE FROM t;
TRUNCATE TABLE t;
ALTER TABLE t ...;
DROP TABLE t;
```

Chúng **không cùng phạm vi tác động**, dù đều có thể nằm trong một script “cleanup”.

### Bước 3: Đọc phụ thuộc và chính sách dữ liệu

Xem:

- FK vào và ra khỏi bảng.
- Trigger và audit.
- Khóa/identity/sequence.
- Dữ liệu tenant khác.
- Ứng dụng hoặc job đang dùng bảng.
- Chính sách backup, phục hồi và lưu trữ.

### Bước 4: Xác định khả năng rollback thực tế

Không chỉ hỏi “có `BEGIN` không?”, mà hỏi:

- DDL có gây **implicit commit** không?
- Có **ngoại lệ DDL** bị cấm trong transaction không?
- Thao tác `TRUNCATE` có rollback được không?
- `CREATE TEMPORARY TABLE` có tham gia rollback không?
- Có DML trước DDL có thể bị commit ngoài ý muốn không?
- Nếu statement thất bại, transaction/savepoint có còn tồn tại không?

### Bước 5: Dùng môi trường thử và dữ liệu nhận diện được

Thay vì làm việc trực tiếp trên bảng thật, tạo bảng thử có ba hàng:

```sql
-- Dùng cú pháp CREATE TABLE theo DBMS tương ứng.
CREATE TABLE demo_cleanup (
    id INTEGER PRIMARY KEY,
    note VARCHAR(50)
);
```

Chèn vài dòng kiểm chứng, ghi nhận số hàng trước/sau và thử rollback. **Không làm phép thử TRUNCATE trên bảng chứa dữ liệu thực tế chỉ để xác nhận lý thuyết.**

### Bước 6: Chỉ dùng ROLLBACK như kế hoạch khôi phục nếu DBMS bảo đảm

Nếu đang ở PostgreSQL/SQL Server trong transaction được hỗ trợ, rollback có thể là một lớp bảo vệ. Nhưng vẫn cần kiểm tra khóa, trigger và thao tác phụ.

Nếu MySQL/MariaDB/Oracle gây implicit commit, chuẩn bị backup, staging/reload, snapshot hoặc một phương án khôi phục khác **trước** khi thực thi.

### Bước 7: Đối soát sau thao tác

Đối soát số hàng, số đối tượng phụ thuộc, trạng thái identity khi cần, thời gian khóa và thông tin audit. Nếu cần đảm bảo “dọn đúng partition” hoặc “chỉ xóa dữ liệu hết hạn”, kiểm tra đúng điều kiện và phạm vi thay vì dựa vào con số affected rows chung chung của TRUNCATE.

## 19. Sai lầm thường gặp

| Sai lầm | Hậu quả có thể xảy ra | Hiểu/sửa thế nào |
|---|---|---|
| “Có BEGIN thì ROLLBACK hủy mọi thứ” | DML trước DDL bị commit ngầm trong MySQL/Oracle | Kiểm tra implicit commit theo DBMS |
| “DDL luôn không rollback được” | Hiểu sai PostgreSQL/SQL Server | Nhiều DDL có thể transactional |
| “TRUNCATE luôn không rollback được” | Sai với PostgreSQL, SQL Server | Phân biệt engine |
| “TRUNCATE luôn transactional vì là xóa dữ liệu” | Sai với MySQL/MariaDB/Oracle | TRUNCATE thường có tính DDL |
| “Atomic DDL của MySQL nghĩa là ROLLBACK được ALTER” | Không thể hoàn tác theo user transaction | Tách crash safety và transactional DDL |
| “CREATE TEMPORARY TABLE MySQL không commit nên rollback sẽ xóa bảng” | Bảng tạm vẫn tồn tại trong session | Không commit ≠ rollbackable |
| “TRUNCATE temp table MySQL không commit” | Có thể commit DML trước đó | TRUNCATE vẫn implicit commit |
| “DDL lỗi thì INSERT trước đó chưa commit” | DDL lỗi sau precommit nhưng DML vẫn tồn tại | Không dựa vào DDL failure làm rollback |
| “TRUNCATE và DELETE không WHERE giống hệt” | Sai trigger, identity, FK, logging và transaction | Chọn theo ngữ nghĩa |
| “TRUNCATE sẽ chạy DELETE trigger để ghi audit” | Thiếu audit từng hàng | Xem cơ chế trigger riêng |
| “CASCADE chỉ xóa những hàng liên quan” | PostgreSQL có thể truncate toàn bộ bảng phụ thuộc | Kiểm tra dependency trước |
| “TRUNCATE không có log/không khóa” | Có thể chặn production và dùng WAL/redo/metadata log | Đọc execution/lock behavior |
| “SQLite có TRUNCATE TABLE” | Lỗi cú pháp | Dùng DELETE FROM |
| “SQLite truncate optimization là implicit commit” | Nhầm tên tối ưu với lệnh DDL | SQLite vẫn thực thi DELETE |
| “ROLLBACK sau COMMIT vẫn có thể khôi phục” | Giao dịch đã hoàn tất | Dùng backup/PITR hoặc bù có kiểm soát |
| “TRUNCATE trên SQL Server luôn trong transaction” | Có thể autocommit ngay nếu không có explicit transaction | Mở/kiểm tra transaction rõ |
| “Mọi môi trường SQL Server giống nhau” | Synapse và sản phẩm khác có giới hạn | Kiểm tra đúng sản phẩm |
| “Migration tool bảo đảm rollback trên mọi DB” | Công cụ không thể thay luật server | Thiết kế migration theo dialect |
| “ID reset về 1 là an toàn” | Liên hệ bên ngoài có thể nhầm danh tính | Không dùng ID làm số thứ tự nghiệp vụ |

## 20. Bài tập thực hành kèm đáp án

### Bài 1. Dự đoán kết quả PostgreSQL

Giả sử bảng `t` có hai hàng được commit:

```sql
BEGIN;
INSERT INTO t VALUES (3);
TRUNCATE TABLE t;
ROLLBACK;
```

**Hỏi:** sau rollback còn gì?

**Đáp án:** nếu các câu được hỗ trợ và chạy thành công, bảng lại có **hai hàng cũ**, còn hàng 3 bị rollback. `TRUNCATE` trong PostgreSQL có thể rollback cùng transaction.

### Bài 2. Dự đoán kết quả MySQL/InnoDB

Giả sử bảng `items` có hai hàng và bảng `audit` rỗng:

```sql
START TRANSACTION;
INSERT INTO audit VALUES (1);
TRUNCATE TABLE items;
ROLLBACK;
```

**Đáp án:** `audit` có thể còn hàng 1 vì `TRUNCATE` đã implicit commit DML trước nó; `items` bị làm rỗng và không được khôi phục bởi `ROLLBACK`.

### Bài 3. Dự đoán kết quả Oracle

```sql
INSERT INTO audit_log (id) VALUES (10);
ALTER TABLE products ADD extra_note VARCHAR2(30);
ROLLBACK;
```

**Hỏi:** nếu `ALTER TABLE` thành công thì INSERT có bị rollback không?

**Đáp án:** **không**. Oracle commit ngầm trước khi thực hiện DDL. `ROLLBACK` sau đó không hoàn tác INSERT đã được commit hoặc cột đã thêm.

### Bài 4. SQL Server có rollback TRUNCATE không?

```sql
BEGIN TRANSACTION;
TRUNCATE TABLE dbo.test_items;
ROLLBACK TRANSACTION;
```

**Đáp án:** trên **SQL Server Database Engine** và bảng thỏa các điều kiện sử dụng TRUNCATE, thao tác có thể được rollback. Không suy rằng cùng câu sẽ chạy trong mọi dịch vụ SQL Server/Azure Synapse.

### Bài 5. DELETE hay TRUNCATE nếu cần lọc theo ngày?

**Yêu cầu:** xóa hàng của tenant 10 đã cũ hơn một mốc, giữ tenant khác.

**Đáp án:** chọn `DELETE ... WHERE tenant_id = 10 AND created_at < ...`, không dùng `TRUNCATE` vì `TRUNCATE` không có `WHERE` theo hàng.

### Bài 6. MySQL CREATE TEMPORARY TABLE

```sql
START TRANSACTION;
CREATE TEMPORARY TABLE tmp_demo (id INT);
ROLLBACK;
```

**Hỏi:** có thể kết luận bảng tạm đã bị xóa không?

**Đáp án:** **không**. `CREATE TEMPORARY TABLE` thường không gây implicit commit ở MySQL, nhưng bản thân việc tạo bảng tạm không rollbackable. Bảng tạm vẫn có thể tồn tại trong session sau rollback.

### Bài 7. MySQL TRUNCATE TEMPORARY

```sql
START TRANSACTION;
INSERT INTO audit_log VALUES (20);
TRUNCATE TABLE tmp_demo;
ROLLBACK;
```

**Đáp án:** đừng kỳ vọng `ROLLBACK` hủy `INSERT` vào `audit_log`. `TRUNCATE` có thể gây implicit commit kể cả với bảng tạm trong MySQL/MariaDB.

### Bài 8. Atomic DDL và transaction khác gì?

**Câu hỏi:** MySQL ghi “atomic DDL”. Một `ALTER TABLE` đã hoàn tất có thể được user `ROLLBACK` như `UPDATE` không?

**Đáp án:** thông thường **không**. Atomic DDL bảo vệ tính toàn vẹn của riêng thay đổi DDL khi crash/lỗi theo phạm vi engine; nó không biến DDL thành thao tác nằm trong user transaction cần rollback.

### Bài 9. PostgreSQL RESTART IDENTITY

```sql
BEGIN;
TRUNCATE TABLE demo_pg_items RESTART IDENTITY;
ROLLBACK;
```

**Hỏi:** có rollback được thao tác restart sequence do TRUNCATE yêu cầu không?

**Đáp án:** với PostgreSQL hiện đại, **có** đối với các sequence thuộc phạm vi `RESTART IDENTITY`. Nhưng không suy mọi lần gọi sequence đều rollback được hoặc `currval()` ở session sẽ luôn phản ánh trạng thái giống hệt trước transaction.

### Bài 10. PostgreSQL TRUNCATE CASCADE

**Tình huống:** `orders` tham chiếu `customers` bằng FK. Muốn làm rỗng customers và viết:

```sql
TRUNCATE TABLE customers CASCADE;
```

**Hỏi:** có thể chỉ mất các hàng của customers không?

**Đáp án:** không nên giả định. PostgreSQL có thể **truncate toàn bộ các bảng tham chiếu** trong chuỗi phụ thuộc; cần xem schema và kế hoạch trước khi chạy, nhất là khi đơn hàng cần được giữ.

### Bài 11. SQLite có TRUNCATE không?

**Đáp án:** không có cú pháp `TRUNCATE TABLE` thông dụng. Để xóa toàn bộ hàng, dùng `DELETE FROM table_name`. Nếu nằm trong transaction tường minh, `ROLLBACK` có thể khôi phục hàng. SQLite có “truncate optimization” nội bộ cho một số `DELETE` không có `WHERE`, nhưng đó vẫn là `DELETE`.

### Bài 12. SAVEPOINT có cứu DDL MySQL không?

**Tình huống:** tạo `SAVEPOINT before_alter`, sau đó `ALTER TABLE` gây implicit commit, rồi `ROLLBACK TO SAVEPOINT before_alter`.

**Đáp án:** không. Transaction chứa savepoint đã bị kết thúc do implicit commit; không thể quay lại ranh giới đó bằng savepoint cũ.

### Bài 13. DDL thất bại và commit

**Tình huống:** MySQL có DML chưa commit; một câu `ALTER TABLE` được chấp nhận về cú pháp nhưng thất bại khi thực thi.

**Hỏi:** có thể chắc chắn DML trước đó vẫn chưa commit không?

**Đáp án:** **không**. Theo quy tắc implicit commit, DML trước DDL có thể đã commit trước khi ALTER chạy. Cần hiểu loại lỗi/cấp phân tích SQL cụ thể; đừng xem việc ALTER thất bại là rollback tự động toàn transaction.

### Bài 14. Lỗi tư duy trong JDBC

**Tình huống:** chương trình gọi `connection.setAutoCommit(false)`, chạy `UPDATE`, rồi `TRUNCATE` trên MySQL, sau đó `connection.rollback()`.

**Đáp án:** `setAutoCommit(false)` không vô hiệu hóa implicit commit do server. `UPDATE` có thể đã commit, còn TRUNCATE không rollback được; cần tách DDL ra khỏi transaction nghiệp vụ và thiết kế khôi phục riêng.

### Bài 15. Chọn chiến lược dọn staging

**Yêu cầu:** hệ thống MySQL muốn xóa toàn bộ staging sau khi hoàn tất nhập liệu; nhưng transaction nhập ở bảng đích chưa được commit. Nên đặt `TRUNCATE staging` vào giữa transaction để “cùng rollback” không?

**Đáp án:** **không**. TRUNCATE gây implicit commit, có thể lưu phần nhập ở bảng đích trước khi ứng dụng quyết định commit. Một hướng an toàn hơn là hoàn tất transaction nhập trước, rồi dọn staging trong giai đoạn riêng có kiểm soát; hoặc dùng `DELETE` trong transaction theo thiết kế, chú ý log và hiệu năng.

### Bài 16. So sánh TRUNCATE và DELETE về trigger

**Hỏi:** tại sao không thể dùng `TRUNCATE` thay `DELETE` nếu audit phụ thuộc `AFTER DELETE` row trigger?

**Đáp án:** `TRUNCATE` không thực thi thao tác xóa từng hàng theo cùng ngữ nghĩa trigger; PostgreSQL có `ON TRUNCATE` riêng, các hệ khác cũng không nên được giả định sẽ kích hoạt row-level DELETE trigger. Có thể mất dữ liệu audit nếu thay thế mà không đổi thiết kế.

## 21. Tham khảo tài liệu chính thức theo hệ quản trị

Để đối chiếu các chi tiết có thể khác theo phiên bản, xem tài liệu chính thức của hệ đang dùng:

- **PostgreSQL — TRUNCATE:** https://www.postgresql.org/docs/current/sql-truncate.html — có `RESTART IDENTITY`, `CASCADE`, khóa, MVCC và ghi nhận rollback.
- **MySQL — Statements That Cause an Implicit Commit:** https://dev.mysql.com/doc/refman/8.4/en/implicit-commit.html — liệt kê DDL, ngoại lệ temporary table và `TRUNCATE`.
- **MySQL — Atomic DDL:** https://dev.mysql.com/doc/refman/8.4/en/atomic-ddl.html — giải thích atomic DDL không phải transactional DDL.
- **MariaDB — Implicit Commit:** https://mariadb.com/docs/server/reference/sql-statements/transactions/sql-statements-that-cause-an-implicit-commit — hành vi và ngoại lệ.
- **MariaDB — Atomic DDL:** https://mariadb.com/docs/server/reference/sql-statements/data-definition/atomic-ddl — đặc điểm crash-safe/atomic theo phiên bản.
- **Oracle Database — Transactions:** https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/transactions.html — implicit commit trước/sau DDL.
- **Oracle Database — TRUNCATE TABLE:** https://docs.oracle.com/en/database/oracle/oracle-database/23/sqlrf/TRUNCATE-TABLE.html — hạn chế rollback và flashback.
- **Microsoft SQL Server — TRUNCATE TABLE:** https://learn.microsoft.com/en-us/sql/t-sql/statements/truncate-table-transact-sql — có ví dụ rollback, identity và giới hạn.
- **SQLite — Transactions:** https://www.sqlite.org/lang_transaction.html — giao dịch tường minh và tự khởi tạo.
- **SQLite — DELETE:** https://www.sqlite.org/lang_delete.html — “truncate optimization” của `DELETE`.

Đọc đúng phiên bản tài liệu với server thực tế; không suy hành vi từ một tài liệu nhiều năm cũ hoặc từ DBMS mang tên gần giống.

## Kết luận

**DDL không có một quy tắc commit chung cho mọi DBMS.** Một số hệ, điển hình là **PostgreSQL và SQL Server Database Engine**, cho phép nhiều DDL thông thường và `TRUNCATE` tham gia transaction có thể rollback. Ngược lại, **MySQL/MariaDB và Oracle** có quy tắc **implicit commit** đối với nhiều DDL, trong đó có `TRUNCATE`: thao tác đó có thể commit các DML trước nó và không thể hoàn tác chỉ bằng `ROLLBACK`. **SQLite** không có `TRUNCATE TABLE` riêng; `DELETE FROM t` hoạt động trong cơ chế giao dịch SQLite, kể cả các tối ưu nội bộ khi xóa toàn bảng.

Để tránh sự cố, luôn tách biệt bốn câu hỏi:

1. **Statement có thực sự nằm trong một transaction chưa commit không?**
2. **Statement có gây implicit commit không?**
3. **Nếu không gây implicit commit, bản thân thay đổi DDL/TRUNCATE có rollback được không?**
4. **Nếu rollback được, thao tác có an toàn về FK, trigger, identity, khóa và đồng thời không?**

Đặc biệt, **atomic DDL không đồng nghĩa transactional DDL**, **không implicit commit cũng chưa chắc rollbackable**, và **rollback được không đồng nghĩa không có tác động phụ hoặc khóa mạnh**. Chọn `DELETE`, `TRUNCATE` hay DDL phải dựa trên **ngữ nghĩa nghiệp vụ, khả năng khôi phục và tài liệu của đúng hệ quản trị**, không chỉ dựa vào tốc độ hay một lời hứa chung rằng “đã có BEGIN rồi”.

