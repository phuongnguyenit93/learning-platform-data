# Trigger theo hàng và theo câu lệnh trong SQL

> **Module:** Database SQL  
> **Chương:** Trigger  
> **Bài học:** Trigger theo hàng và theo câu lệnh

Một câu UPDATE có thể thay đổi đúng một dòng, một triệu dòng hoặc không dòng nào. Nếu bảng có trigger, trigger sẽ được gọi bao nhiêu lần? Có thể đọc giá trị cũ và mới của từng dòng hay toàn bộ tập dòng cùng lúc không? Một câu UPDATE không khớp dòng nào có tạo nhật ký không? Và tại sao cùng một yêu cầu lại viết khác nhau trên PostgreSQL, Oracle, SQL Server, MySQL và SQLite?

Đó là trọng tâm của hai mô hình **trigger theo hàng (row-level trigger)** và **trigger theo câu lệnh (statement-level trigger)**.

- **Trigger theo hàng:** chạy riêng cho từng hàng bị tác động bởi một sự kiện DML, thường có thể xem các giá trị OLD và NEW tương ứng.
- **Trigger theo câu lệnh:** chạy một lần cho sự kiện câu lệnh, bất kể câu đó liên quan 0, 1 hay nhiều hàng, theo ngữ nghĩa của DBMS hỗ trợ. Muốn xem những hàng cụ thể, phải dùng cơ chế tập chuyển tiếp hoặc kỹ thuật tương ứng.

Lưu ý ngay từ đầu: **BEFORE, AFTER và INSTEAD OF** mô tả **thời điểm hoặc cách thay thế thao tác**; **FOR EACH ROW và FOR EACH STATEMENT** mô tả **phạm vi kích hoạt**. Chúng không phải hai cặp từ đồng nghĩa.

---

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích trigger là gì, do sự kiện nào kích hoạt và khác procedure, constraint, job như thế nào.
2. Phân biệt trigger theo hàng và trigger theo câu lệnh với ví dụ INSERT, UPDATE, DELETE.
3. Đếm đúng số lần kích hoạt khi một DML thay đổi 0, 1, 100 hoặc một triệu hàng.
4. Phân biệt một câu UPDATE nhiều hàng với nhiều câu UPDATE riêng lẻ.
5. Đọc OLD/NEW khi trigger theo hàng, và không áp nhầm chúng cho statement trigger.
6. Hiểu vai trò của transition tables trong PostgreSQL và pseudo-tables inserted/deleted trong SQL Server.
7. Biết Oracle hỗ trợ row/statement triggers và compound trigger, cùng rủi ro mutating table.
8. Biết MySQL và SQLite không có statement-level DML trigger tổng quát như PostgreSQL/Oracle.
9. Thiết kế BEFORE ROW để kiểm tra/chỉnh NEW nếu DBMS cho phép, và AFTER trigger để ghi audit.
10. Thiết kế audit một dòng cho từng thay đổi hoặc một dòng cho toàn câu lệnh.
11. Phân biệt UPDATE đã nhắm hàng với giá trị thực sự đổi.
12. Hiểu tác động tới transaction, rollback, locking, concurrency, recursion và dữ liệu nhạy cảm.
13. Phân tích UPSERT, MERGE, DELETE, TRUNCATE, cascade và trigger trên view.
14. Viết các ví dụ SQL có điều kiện rõ ràng, xử lý 0 hàng và nhiều hàng đúng.
15. Kiểm thử và đo hiệu năng trigger trước khi dùng cho thao tác dữ liệu quy mô lớn.

## 2. Trigger là gì?

**Trigger** là chương trình hoặc khối lệnh được lưu trong cơ sở dữ liệu, tự động thực thi khi một sự kiện nhất định xảy ra trên bảng, view hoặc đối tượng có hỗ trợ.

Ví dụ DML:

~~~sql
INSERT INTO san_pham (...);
UPDATE san_pham SET gia_ban = gia_ban * 1.05 WHERE trang_thai = 'ACTIVE';
DELETE FROM san_pham WHERE ma_san_pham = 'P09';
~~~

Nếu có trigger tương ứng, DBMS thực thi logic trigger theo quy tắc của nó. Trigger có thể:

- Kiểm tra dữ liệu.
- Chuẩn hóa giá trị trước khi lưu.
- Ghi lịch sử thay đổi OLD/NEW.
- Sinh dòng nhật ký hoạt động.
- Duy trì một bảng tổng hợp.
- Ghi outbox event trong cùng giao dịch.
- Từ chối thao tác trái điều kiện.

Trigger **không cần ứng dụng gọi trực tiếp**. Điều này vừa hữu ích, vừa tạo rủi ro: một câu UPDATE tưởng đơn giản có thể thực hiện nhiều thao tác phụ ẩn. Vì thế, trigger cần có tài liệu schema và quy trình kiểm thử.

### 2.1. Trigger khác stored procedure

- **Stored procedure/function:** được gọi trực tiếp hoặc từ một chương trình khác; có tham số và hợp đồng gọi rõ.
- **Trigger:** được kích hoạt bởi sự kiện; dữ liệu ngữ cảnh được DBMS cung cấp.
- **Constraint:** diễn đạt bất biến dữ liệu như NOT NULL, UNIQUE, CHECK, FOREIGN KEY.
- **Scheduled job:** chạy theo lịch hoặc điều kiện điều phối, không phải theo mỗi INSERT/UPDATE/DELETE.
- **Application service:** điều phối workflow, giao dịch, phân quyền và tương tác với hệ thống ngoài.

Một trigger ghi audit có thể phù hợp, nhưng quy tắc tồn kho không âm vẫn nên dùng CHECK nếu đủ khả năng.

## 3. Dữ liệu dùng xuyên suốt bài học

Giả sử bảng sản phẩm:

~~~sql
CREATE TABLE san_pham (
    ma_san_pham VARCHAR(20) PRIMARY KEY,
    ten_san_pham VARCHAR(100) NOT NULL,
    so_luong_ton INTEGER NOT NULL,
    gia_ban DECIMAL(14,2) NOT NULL,
    trang_thai VARCHAR(20) NOT NULL,
    phien_ban INTEGER NOT NULL DEFAULT 1,
    CONSTRAINT ck_stock CHECK (so_luong_ton >= 0),
    CONSTRAINT ck_price CHECK (gia_ban >= 0)
);
~~~

Dữ liệu mẫu:

| Mã | Tên | Tồn kho | Giá bán | Trạng thái |
|---|---|---:|---:|---|
| P01 | Bút bi | 10 | 100000 | ACTIVE |
| P02 | Sổ tay | 5 | 200000 | ACTIVE |
| P03 | Thước | 0 | 50000 | ACTIVE |
| P04 | Hộp bút | 20 | 80000 | STOP |
| P05 | Giấy | 8 | 30000 | ACTIVE |

Trong ví dụ:

~~~sql
UPDATE san_pham
SET gia_ban = gia_ban * 1.10
WHERE trang_thai = 'ACTIVE';
~~~

bốn hàng P01, P02, P03 và P05 thuộc tập được cập nhật.

Nếu có một trigger **FOR EACH ROW**, nó sẽ được thực thi theo từng hàng đó. Nếu có một trigger **FOR EACH STATEMENT**, nó sẽ được thực thi một lần cho sự kiện UPDATE, dù bốn hàng được sửa.

**Quy ước:** Mỗi ví dụ độc lập được hiểu bắt đầu từ dữ liệu mẫu ban đầu, trừ trường hợp nêu rõ chuỗi nhiều câu lệnh. Không chạy các ví dụ thay đổi dữ liệu trực tiếp ở production.

## 4. Ba trục đọc một định nghĩa trigger

Đọc trigger theo thứ tự:

**Thứ nhất — sự kiện:**
- INSERT.
- UPDATE.
- DELETE.
- Các sự kiện khác có thể gồm TRUNCATE, DDL, LOGON, v.v. theo DBMS.

**Thứ hai — timing:**
- BEFORE: trước thao tác được mô tả.
- AFTER: sau bước thao tác theo quy tắc trigger nhưng **không nhất thiết sau COMMIT**.
- INSTEAD OF: thực thi logic thay thế DML mặc định, thường trên view.

**Thứ ba — granularity:**
- ROW: từng hàng.
- STATEMENT: một lần cho mỗi câu lệnh/sự kiện.

Các tổ hợp như BEFORE ROW, AFTER ROW, BEFORE STATEMENT, AFTER STATEMENT có thể tồn tại trong một số hệ, nhưng **không phải DBMS nào cũng hỗ trợ tất cả**.

### 4.1. Ví dụ tên gọi

- AFTER UPDATE FOR EACH ROW: sau khi mỗi hàng được UPDATE theo quy tắc hệ.
- AFTER UPDATE FOR EACH STATEMENT: sau một câu UPDATE, chạy một lần.
- BEFORE INSERT FOR EACH ROW: xử lý giá trị NEW trước khi chèn.
- INSTEAD OF UPDATE ON view: thay thế UPDATE trên view bằng logic định nghĩa, phạm vi row/statement tùy DBMS.

**Không gọi mọi AFTER trigger là statement-level trigger.** Đây là nhầm lẫn phổ biến khi chuyển từ SQL Server sang PostgreSQL.

## 5. Trigger theo hàng: hoạt động theo mỗi hàng được tác động

Hình dung câu lệnh:

~~~sql
UPDATE san_pham
SET so_luong_ton = so_luong_ton + 5
WHERE trang_thai = 'ACTIVE';
~~~

Kết quả logic với mẫu là:

~~~text
P01: OLD.stock=10  NEW.stock=15
P02: OLD.stock=5   NEW.stock=10
P03: OLD.stock=0   NEW.stock=5
P05: OLD.stock=8   NEW.stock=13
~~~

Nếu AFTER UPDATE FOR EACH ROW trigger phù hợp, body được gọi **bốn lần**. Mỗi lần xử lý **một cặp hàng** OLD và NEW.

### 5.1. Điều kiện cần nhớ

Một trigger row-level không tự biết toàn bộ kết quả DML của câu lệnh. Mỗi lần nó thấy một hàng tương ứng, cùng những thông tin hệ quản trị cung cấp.

Muốn đếm cả lô hoặc tính tổng thay đổi của tất cả hàng, cần:
- Một cơ chế statement-level với transition tables.
- Một compound trigger tích lũy trạng thái theo câu lệnh.
- Hoặc xử lý từ stored procedure/service có giao diện batch thích hợp.

### 5.2. Thứ tự các hàng không được mặc định

Không được giả định P01 rồi P02 rồi P03 rồi P05 sẽ luôn là thứ tự chạy row trigger. Thứ tự phụ thuộc kế hoạch thực thi, cơ chế ghi và DBMS; nếu nghiệp vụ cần thứ tự sự kiện, phải thiết kế thêm sequence/timestamp/event identity hoặc xử lý tuần tự có kiểm soát.

### 5.3. Khi nào hợp lý?

Row trigger thường phù hợp:
- Kiểm tra OLD/NEW của từng thực thể.
- Từ chối trạng thái không hợp lệ.
- Chuẩn hóa dữ liệu từng hàng.
- Ghi audit old/new theo product_id.
- Ghi dữ liệu biến đổi nhỏ liên quan tới một hàng.

Nhưng một UPDATE một triệu hàng có thể gọi body một triệu lần, nên phải đo chi phí.

## 6. Trigger theo câu lệnh: một lần cho DML statement

Nếu DBMS hỗ trợ:

~~~sql
CREATE TRIGGER ...
AFTER UPDATE ON san_pham
FOR EACH STATEMENT
...
~~~

thì body chạy **một lần cho câu UPDATE**, không phụ thuộc số hàng được cập nhật.

Ví dụ:

~~~sql
UPDATE san_pham
SET so_luong_ton = so_luong_ton + 5
WHERE trang_thai = 'ACTIVE';
~~~

sinh một statement event dù bốn hàng bị sửa.

Nhưng:

~~~sql
UPDATE san_pham SET so_luong_ton = so_luong_ton + 5 WHERE ma_san_pham = 'P01';
UPDATE san_pham SET so_luong_ton = so_luong_ton + 5 WHERE ma_san_pham = 'P02';
UPDATE san_pham SET so_luong_ton = so_luong_ton + 5 WHERE ma_san_pham = 'P03';
UPDATE san_pham SET so_luong_ton = so_luong_ton + 5 WHERE ma_san_pham = 'P05';
~~~

là **bốn câu UPDATE**, nên có thể kích hoạt statement trigger **bốn lần**.

### 6.1. Statement khác transaction

Một transaction có thể bao gồm 20 câu UPDATE. Statement trigger có thể chạy 20 lần, chứ không tự gom thành một lần cho transaction. Nếu nghiệp vụ cần **một bản ghi cho cả request hoặc transaction**, hãy dùng request_id, batch_id và cơ chế ghi nhận tương ứng.

### 6.2. Không có một OLD/NEW scalar đại diện cả statement

Nếu một UPDATE chạm 100 hàng, không có một OLD và một NEW duy nhất đại diện được cả tập. Các DBMS hỗ trợ truy cập tập thay đổi theo những cơ chế khác nhau:
- PostgreSQL: transition tables khi cấu hình được hỗ trợ.
- SQL Server: inserted/deleted pseudo-tables.
- Oracle: compound trigger hoặc cách thu thập trạng thái phù hợp.
- MySQL/SQLite: không có statement DML trigger tổng quát tương đương.

## 7. Trường hợp 0 hàng

Xét:

~~~sql
UPDATE san_pham
SET gia_ban = 99999
WHERE ma_san_pham = 'P99';
~~~

Nếu P99 không tồn tại thì **0 hàng bị tác động**.

- Row trigger: **0 lần**, không có hàng để chạy.
- Statement trigger PostgreSQL/Oracle: thông thường **1 lần** cho câu DML dù không có hàng nào.
- SQL Server DML trigger: được kích hoạt theo statement, có thể chạy với tập inserted/deleted rỗng.
- MySQL/SQLite: chỉ có trigger DML theo hàng trong mô hình thông thường, nên **không có trigger row nào chạy**.

Đây là ca kiểm thử cực quan trọng. Một hệ thống audit muốn log cả yêu cầu UPDATE thất bại do không khớp hàng có thể cần statement-level audit. Một hệ thống chỉ muốn log **giá trị thực sự thay đổi** phải tránh ghi một sự kiện thay đổi giả cho câu UPDATE 0 hàng.

### 7.1. Bảng đếm số lần

| Thao tác | Số hàng | Row trigger | Statement trigger |
|---|---:|---:|---:|
| UPDATE một mã tồn tại | 1 | 1 | 1 |
| UPDATE bốn hàng ACTIVE | 4 | 4 | 1 |
| UPDATE P99 không tồn tại | 0 | 0 | 1, nếu hệ hỗ trợ ngữ nghĩa này |
| INSERT một lần thêm 100 dòng | 100 | 100 | 1 |
| DELETE một lần xóa 20 dòng | 20 | 20 | 1 |
| 10 UPDATE riêng, mỗi lần một hàng | 10 tổng | 10 tổng | 10 tổng |

Với UPSERT, MERGE, partition, cascade, trigger khác và thao tác đặc biệt, quy tắc có ngoại lệ; bảng trên mô tả các DML cơ bản.

## 8. OLD và NEW: dữ liệu nào có sẵn?

Các pseudo-record row-level thường có:

| Thao tác | OLD | NEW |
|---|---|---|
| INSERT | Không có hàng cũ | Hàng mới |
| UPDATE | Hàng trước cập nhật | Hàng sau/đề xuất cập nhật |
| DELETE | Hàng bị xóa | Không có hàng mới |

Cách viết khác nhau:

| DBMS | Đọc giá trị cũ | Đọc giá trị mới |
|---|---|---|
| PostgreSQL | OLD.col | NEW.col |
| Oracle | :OLD.col | :NEW.col |
| MySQL | OLD.col | NEW.col |
| SQLite | OLD.col | NEW.col |
| SQL Server | deleted (tập hàng) | inserted (tập hàng) |

### 8.1. Không truy cập NEW trong DELETE hay OLD trong INSERT

Nếu trigger xử lý nhiều loại DML, phải kiểm tra loại sự kiện trước khi dùng bản ghi tương ứng. Đừng tự suy luận pseudo-record không hợp lệ là một hàng có toàn NULL.

### 8.2. UPDATE có giá trị bằng nhau

~~~sql
UPDATE san_pham
SET gia_ban = gia_ban
WHERE ma_san_pham = 'P01';
~~~

Hàng vẫn có thể nằm trong tập UPDATE và kích hoạt row trigger, dù giá cuối không đổi. Nếu audit muốn ghi **chỉ khi giá thực đổi**, phải so OLD.gia_ban với NEW.gia_ban theo ngữ nghĩa NULL chính xác.

### 8.3. UPDATE OF cột không đồng nghĩa cột đổi giá trị

Một số DBMS cho phép trigger UPDATE OF gia_ban hoặc hàm UPDATE(gia_ban). Điều này thường liên quan cột xuất hiện ở danh sách SET/sự kiện, không tự so giá trị OLD/NEW.

## 9. BEFORE ROW và AFTER ROW

**BEFORE ROW** có thể thích hợp khi cần:
- Kiểm tra dữ liệu mới.
- Chuẩn hóa tên.
- Điền metadata mặc định.
- Từ chối một chuyển trạng thái.

**AFTER ROW** thường thích hợp khi:
- Ghi log OLD/NEW.
- Tạo một bản ghi audit tương ứng với hàng đã trải qua xử lý.
- Thực hiện logic phụ thuộc thao tác DML vừa xảy ra trong cùng transaction.

### 9.1. BEFORE không có nghĩa không có transaction

BEFORE trigger được thực thi trong quá trình DML. Nó có thể đọc/ghi đối tượng khác theo quy tắc hệ, phát lỗi, giữ khóa và chịu transaction semantics.

### 9.2. AFTER không đồng nghĩa dữ liệu đã commit

AFTER trigger thường chạy **trước COMMIT** của transaction. Một ROLLBACK sau đó có thể hoàn tác cả UPDATE và những dòng audit do trigger ghi trong cùng transaction.

### 9.3. BEFORE ROW sửa NEW không phổ quát

- PostgreSQL PL/pgSQL: có thể chỉnh NEW và RETURN NEW trong BEFORE ROW.
- MySQL: có thể SET NEW.col trong BEFORE INSERT/UPDATE theo quy tắc.
- Oracle: có thể thay :NEW trong BEFORE ROW trong phạm vi được phép.
- SQLite: không có mô hình SET NEW.col tự do giống MySQL.
- SQL Server: không có BEFORE ROW trigger theo mô hình trên.

Vì vậy không sao chép nguyên văn một đoạn trigger giữa các hệ quản trị.

## 10. INSTEAD OF khác ROW/STATEMENT

INSTEAD OF là timing/cơ chế **thay thế hành động mặc định**, thường dùng khi UPDATE qua view JOIN không có đường ánh xạ tự động.

Ví dụ:

~~~sql
CREATE VIEW v_nhan_vien_phong AS
SELECT n.ma_nv, n.ten_nv, n.luong, p.ten_phong
FROM nhan_vien n
JOIN phong_ban p ON p.ma_phong = n.ma_phong;
~~~

Muốn chỉ sửa luong qua view có thể cần INSTEAD OF trigger đưa UPDATE về nhan_vien.

Phạm vi tùy hệ:
- PostgreSQL, Oracle, SQLite: INSTEAD OF trigger trên view thường theo **hàng**.
- SQL Server: INSTEAD OF DML trigger xử lý theo **câu lệnh**, từ inserted/deleted.
- MySQL: không có INSTEAD OF trigger view tương đương.

Không kết luận cứ INSTEAD OF thì là statement-level trigger.

## 11. PostgreSQL: FOR EACH ROW

PostgreSQL hỗ trợ trigger function trả về kiểu trigger, gắn vào bảng bằng CREATE TRIGGER.

Ví dụ bảng nhật ký:

~~~sql
CREATE TABLE log_ton_pg (
    log_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ma_san_pham VARCHAR(20) NOT NULL,
    old_stock INTEGER,
    new_stock INTEGER,
    recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Hàm trigger:

~~~sql
CREATE OR REPLACE FUNCTION fn_log_ton_pg()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.so_luong_ton IS DISTINCT FROM NEW.so_luong_ton THEN
        INSERT INTO log_ton_pg (
            ma_san_pham, old_stock, new_stock
        )
        VALUES (
            NEW.ma_san_pham,
            OLD.so_luong_ton,
            NEW.so_luong_ton
        );
    END IF;

    RETURN NEW;
END;
$$;
~~~

Định nghĩa trigger:

~~~sql
CREATE TRIGGER trg_log_ton_pg
AFTER UPDATE OF so_luong_ton ON san_pham
FOR EACH ROW
EXECUTE FUNCTION fn_log_ton_pg();
~~~

Nếu UPDATE làm tồn thay đổi ở bốn sản phẩm, sẽ có bốn lần gọi và bốn log tương ứng.

### 11.1. IS DISTINCT FROM

PostgreSQL hỗ trợ IS DISTINCT FROM để so hai giá trị theo ngữ nghĩa có xử lý NULL. Với x=NULL và y=NULL, x IS DISTINCT FROM y là FALSE; với một bên NULL, một bên không NULL là TRUE.

Nếu dùng OLD.col <> NEW.col khi có NULL, biểu thức có thể là UNKNOWN, làm điều kiện IF không chạy. Dù so_luong_ton mẫu NOT NULL, chọn IS DISTINCT FROM giúp minh họa cách kiểm tra giá trị đổi một cách tổng quát.

### 11.2. UPDATE OF so_luong_ton

Trigger khai báo UPDATE OF so_luong_ton theo quy tắc liên quan cột được nhắc đến ở UPDATE. Nó không tự đảm bảo OLD.stock khác NEW.stock. Phần IF trong function kiểm tra **thực sự khác giá trị**.

### 11.3. RETURN NEW trong AFTER trigger

Với AFTER ROW trigger, giá trị trả về thường không được dùng để thay đổi hàng đã cập nhật. RETURN NEW là cách biểu đạt thông dụng. Không nhầm với BEFORE ROW, nơi giá trị RETURN có tác động đến hàng được ghi.

## 12. PostgreSQL: BEFORE ROW chỉnh NEW

~~~sql
CREATE OR REPLACE FUNCTION fn_trim_ten_pg()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.ten_san_pham := TRIM(NEW.ten_san_pham);
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_trim_ten_pg
BEFORE INSERT OR UPDATE OF ten_san_pham ON san_pham
FOR EACH ROW
EXECUTE FUNCTION fn_trim_ten_pg();
~~~

Ở đây mỗi hàng mới/sửa tên được chuẩn hóa trước ghi.

### 12.1. RETURN NULL trong BEFORE ROW nguy hiểm thế nào?

Trong PostgreSQL, BEFORE ROW trigger trả NULL có thể làm DBMS **bỏ qua thao tác đối với hàng đó**. Một ứng dụng có thể nghĩ UPDATE đã xử lý mọi hàng, nhưng trigger âm thầm bỏ vài hàng. Chỉ dùng khi đúng chính sách và đã kiểm soát row count/audit.

### 12.2. Không đổi NEW từ AFTER rồi mong ảnh hưởng bảng

AFTER trigger thường để quan sát/log, không phải chỗ chỉnh NEW trước khi lưu. Nếu muốn dữ liệu đầu vào được trim, dùng BEFORE trigger hoặc logic ứng dụng/constraint phù hợp.

## 13. PostgreSQL: FOR EACH STATEMENT

Tạo bảng audit mức câu lệnh:

~~~sql
CREATE TABLE log_statement_pg (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    action VARCHAR(10) NOT NULL,
    table_name VARCHAR(100) NOT NULL,
    recorded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Hàm:

~~~sql
CREATE OR REPLACE FUNCTION fn_log_statement_pg()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO log_statement_pg (action, table_name)
    VALUES (TG_OP, TG_TABLE_NAME);

    RETURN NULL;
END;
$$;
~~~

Trigger:

~~~sql
CREATE TRIGGER trg_log_statement_pg
AFTER UPDATE ON san_pham
FOR EACH STATEMENT
EXECUTE FUNCTION fn_log_statement_pg();
~~~

Một UPDATE dù chọn 0 hay 4 hàng đều có thể ghi một log “UPDATE lên san_pham”. Đây là **statement audit**, không phải khẳng định bốn hàng thực sự đổi.

### 13.1. Không có OLD/NEW scalar

Statement trigger không có OLD và NEW của một hàng cụ thể, bởi một câu UPDATE có thể sửa hàng nghìn hàng. Muốn đọc tập thay đổi cần transition tables khi PostgreSQL hỗ trợ.

### 13.2. RETURN NULL phù hợp ở statement trigger

Giá trị trả về trong statement-level trigger PostgreSQL thường không được dùng. RETURN NULL ở đây không có nghĩa bỏ qua cả câu UPDATE như trường hợp BEFORE ROW RETURN NULL.

## 14. PostgreSQL: transition tables

PostgreSQL cho phép một số AFTER trigger tham chiếu tập hàng cũ/mới bằng **REFERENCING OLD TABLE AS ... NEW TABLE AS ...**.

Ví dụ bảng thống kê:

~~~sql
CREATE TABLE log_batch_pg (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    affected_rows BIGINT NOT NULL,
    total_old_stock BIGINT NOT NULL,
    total_new_stock BIGINT NOT NULL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
~~~

Hàm:

~~~sql
CREATE OR REPLACE FUNCTION fn_log_batch_pg()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    n BIGINT;
    sum_old BIGINT;
    sum_new BIGINT;
BEGIN
    SELECT COUNT(*), COALESCE(SUM(so_luong_ton), 0)
      INTO n, sum_new
      FROM new_rows;

    SELECT COALESCE(SUM(so_luong_ton), 0)
      INTO sum_old
      FROM old_rows;

    INSERT INTO log_batch_pg (
        affected_rows, total_old_stock, total_new_stock
    )
    VALUES (n, sum_old, sum_new);

    RETURN NULL;
END;
$$;
~~~

Trigger:

~~~sql
CREATE TRIGGER trg_log_batch_pg
AFTER UPDATE ON san_pham
REFERENCING OLD TABLE AS old_rows
            NEW TABLE AS new_rows
FOR EACH STATEMENT
EXECUTE FUNCTION fn_log_batch_pg();
~~~

Nếu UPDATE bốn hàng, transition tables chứa tập dữ liệu tương ứng; COUNT(*)=4. Nếu UPDATE không chạm hàng nào, COUNT(*)=0 và SUM trên tập rỗng được COALESCE về 0.

### 14.1. Transition table không phải bảng lưu trữ lâu dài

Các tên old_rows và new_rows chỉ hợp lệ trong ngữ cảnh trigger; không cần CREATE TABLE riêng và không được dùng như staging table bền vững sau khi sự kiện kết thúc.

### 14.2. Hạn chế cú pháp

PostgreSQL có quy tắc về kiểu trigger, sự kiện, timing và việc dùng REFERENCING. Với UPDATE có transition table, không được mặc định kết hợp tùy ý với trigger **UPDATE OF danh_sach_cot**. Hãy đọc đúng cú pháp phiên bản và phân biệt trigger cần đọc tập thay đổi với trigger chỉ theo cột.

### 14.3. Không JOIN old/new bằng khóa có thể thay đổi

Nếu UPDATE thay ma_san_pham, JOIN old_rows với new_rows theo chính mã đó có thể không match. Ví dụ trên chỉ tính tổng riêng, không ghép từng cặp. Khi cần đối chiếu old/new từng hàng, cần định danh bất biến hoặc một cách khác được bảo đảm.

### 14.4. Vì sao transition tables hữu ích?

Thay vì trigger theo hàng phát 100.000 câu INSERT audit, một AFTER STATEMENT trigger có thể dùng **INSERT ... SELECT** trên new_rows/old_rows, tận dụng xử lý theo tập. Hiệu năng vẫn phụ thuộc dữ liệu, kế hoạch và transaction log; không mặc định mọi statement trigger nhanh hơn.

## 15. Oracle: FOR EACH ROW và statement trigger

Oracle có cú pháp PL/SQL:

Theo hàng:

~~~sql
CREATE OR REPLACE TRIGGER trg_oracle_row
AFTER UPDATE ON san_pham
FOR EACH ROW
BEGIN
    NULL;
END;
/
~~~

Theo câu lệnh:

~~~sql
CREATE OR REPLACE TRIGGER trg_oracle_statement
AFTER UPDATE ON san_pham
BEGIN
    NULL;
END;
/
~~~

Trong trigger DML thông thường, **không ghi FOR EACH ROW** là statement-level trigger. Dấu **/** được nhiều client Oracle dùng để hoàn tất thực thi khối PL/SQL, không phải nội dung của biểu thức SQL.

### 15.1. Oracle dùng :OLD và :NEW

~~~text
:OLD.so_luong_ton
:NEW.so_luong_ton
~~~

là cú pháp trong row trigger. Statement trigger không có một cặp :OLD/:NEW duy nhất vì không đại diện cho một hàng.

### 15.2. BEFORE ROW kiểm tra giá trị

~~~sql
CREATE OR REPLACE TRIGGER trg_oracle_check_ton
BEFORE INSERT OR UPDATE OF so_luong_ton ON san_pham
FOR EACH ROW
BEGIN
    IF :NEW.so_luong_ton < 0 THEN
        RAISE_APPLICATION_ERROR(
            -20001, 'Ton kho khong duoc am'
        );
    END IF;
END;
/
~~~

Ví dụ minh họa cách truy cập :NEW và phát lỗi. Nếu chỉ kiểm tra >=0, CHECK constraint ở bảng gốc thường đơn giản hơn trigger và nên là lớp bảo vệ ưu tiên.

## 16. Oracle: compound trigger

Oracle hỗ trợ **compound trigger** cho phép ghép các phần timing theo câu lệnh và theo hàng, có trạng thái được chia sẻ trong một lần thực thi statement.

Tạo log:

~~~sql
CREATE TABLE log_batch_oracle (
    id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    so_hang NUMBER NOT NULL,
    ghi_luc TIMESTAMP DEFAULT SYSTIMESTAMP
);
~~~

Trigger:

~~~sql
CREATE OR REPLACE TRIGGER trg_dem_batch_oracle
FOR UPDATE ON san_pham
COMPOUND TRIGGER

    g_so_hang PLS_INTEGER := 0;

    BEFORE STATEMENT IS
    BEGIN
        g_so_hang := 0;
    END BEFORE STATEMENT;

    AFTER EACH ROW IS
    BEGIN
        g_so_hang := g_so_hang + 1;
    END AFTER EACH ROW;

    AFTER STATEMENT IS
    BEGIN
        INSERT INTO log_batch_oracle (so_hang)
        VALUES (g_so_hang);
    END AFTER STATEMENT;

END trg_dem_batch_oracle;
/
~~~

Nếu UPDATE bốn hàng, phần AFTER EACH ROW tăng biến g_so_hang bốn lần; AFTER STATEMENT ghi một log so_hang=4. Nếu UPDATE 0 hàng, phần row không chạy và phần statement có thể ghi số 0.

### 16.1. Trạng thái của compound trigger không phải biến toàn cục mãi mãi

Biến g_so_hang được dùng với ngữ nghĩa trạng thái trong lần thực thi trigger tương ứng. Không thay bằng biến package global thiếu bảo vệ mà nghĩ nó tự reset cho mọi session và statement.

### 16.2. Lợi ích

Compound trigger hữu ích khi:
- Cần thu thập ID/dữ liệu từng hàng rồi xử lý sau cả câu lệnh.
- Cần gom log theo batch.
- Muốn giảm một số vấn đề của row trigger đọc bảng đang biến đổi.
- Muốn kết hợp validation từng hàng và xử lý tổng hợp.

Nó không tự giải quyết race giữa hai transaction hoặc bảo đảm mọi phép tổng hợp trên bảng đều an toàn.

## 17. Oracle: mutating table và ORA-04091

Một row trigger Oracle cố SELECT lại **cùng bảng đang được UPDATE** có thể gây lỗi **ORA-04091: table is mutating**, tùy trường hợp.

Ví dụ ý tưởng có rủi ro:

~~~sql
CREATE OR REPLACE TRIGGER trg_oracle_mutating
AFTER UPDATE ON san_pham
FOR EACH ROW
DECLARE
    n NUMBER;
BEGIN
    SELECT COUNT(*) INTO n
    FROM san_pham
    WHERE trang_thai = 'ACTIVE';
END;
/
~~~

Khi xử lý từng hàng, Oracle có thể không cho trigger nhìn lại bảng đang được câu lệnh thay đổi theo cách này.

### 17.1. Các hướng xử lý

- Dùng :OLD/:NEW khi chỉ cần dữ liệu của hàng đang sửa.
- Dùng CHECK, UNIQUE, FK khi nghiệp vụ có thể diễn đạt bằng constraint.
- Dùng compound trigger để thu thập theo hàng, xử lý ở AFTER STATEMENT theo quy tắc Oracle.
- Khi kiểm tra điều kiện liên quan nhiều transaction, vẫn cần locking/isolation và thiết kế ràng buộc; chuyển SELECT sang AFTER STATEMENT không tự chống race.

Không dùng mutating-table workaround một cách máy móc nếu logic nghiệp vụ vẫn sai.

## 18. SQL Server: DML trigger theo câu lệnh

SQL Server không có cú pháp DML **FOR EACH ROW** như PostgreSQL hay Oracle. Trigger DML chạy theo sự kiện câu lệnh và cung cấp **hai pseudo-tables tập hợp**:

- **inserted**: giá trị hàng mới sau INSERT/UPDATE.
- **deleted**: giá trị hàng cũ trước UPDATE/DELETE.

Nếu UPDATE bốn hàng, inserted có bốn hàng mới, deleted có bốn hàng cũ tương ứng trong phạm vi sự kiện.

### 18.1. Audit nhiều hàng đúng cách

Giả sử bảng log SQL Server:

~~~sql
CREATE TABLE dbo.log_ton_sqlserver (
    log_id BIGINT IDENTITY(1,1) PRIMARY KEY,
    ma_san_pham VARCHAR(20) NOT NULL,
    old_stock INT,
    new_stock INT,
    logged_at DATETIME2 DEFAULT SYSUTCDATETIME()
);
~~~

Trigger:

~~~sql
CREATE TRIGGER dbo.trg_log_ton_sqlserver
ON dbo.san_pham
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO dbo.log_ton_sqlserver (
        ma_san_pham, old_stock, new_stock
    )
    SELECT
        d.ma_san_pham,
        d.so_luong_ton,
        i.so_luong_ton
    FROM inserted AS i
    INNER JOIN deleted AS d
        ON d.ma_san_pham = i.ma_san_pham
    WHERE d.so_luong_ton <> i.so_luong_ton;
END;
~~~

**Điều kiện quan trọng:** ví dụ giả định ma_san_pham không thay đổi trong câu UPDATE. Nếu khóa có thể bị đổi, việc JOIN hai tập theo khóa đó có thể thất bại. Cần định danh bất biến hoặc cơ chế audit khác.

### 18.2. Không dùng scalar để giả định inserted có một hàng

Sai ý tưởng:

~~~sql
DECLARE @id VARCHAR(20);
SELECT @id = ma_san_pham FROM inserted;
-- Chi log hoac UPDATE theo mot @id.
~~~

Nếu inserted có 100 hàng, việc gán một giá trị scalar không đại diện cho 100 hàng và có thể bỏ sót dữ liệu. Hãy viết set-based với INSERT ... SELECT, JOIN, UPDATE ... FROM khi cần.

### 18.3. SET NOCOUNT ON

SET NOCOUNT ON làm giảm các thông báo số dòng bị ảnh hưởng phụ do các câu lệnh trong trigger, giúp tránh làm nhiễu client. Nó không biến trigger thành row-level và không tự xử lý logic audit.

### 18.4. SQL Server không có scalar OLD/NEW row

Không viết NEW.gia_ban hoặc OLD.gia_ban trong T-SQL trigger theo cách PostgreSQL/SQLite/MySQL. Mọi giả định về tập thay đổi phải dùng inserted/deleted.

## 19. SQL Server và UPDATE 0 hàng

Với câu:

~~~sql
UPDATE dbo.san_pham
SET gia_ban = gia_ban * 1.10
WHERE ma_san_pham = 'P99';
~~~

AFTER UPDATE trigger có thể được gọi dù không hàng nào thỏa. inserted và deleted rỗng.

Nếu chỉ xử lý khi có hàng:

~~~sql
IF NOT EXISTS (SELECT 1 FROM inserted)
    RETURN;
~~~

Nếu muốn log **một lần cho mọi câu UPDATE**, kể cả 0 hàng, không RETURN; có thể ghi COUNT_BIG(*) từ inserted để nhận 0.

### 19.1. Ví dụ đếm một lần

~~~sql
CREATE TRIGGER dbo.trg_dem_update_sqlserver
ON dbo.san_pham
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    INSERT INTO dbo.log_batch_sqlserver (
        table_name, affected_rows
    )
    SELECT
        'san_pham',
        COUNT_BIG(*)
    FROM inserted;
END;
~~~

Ví dụ giả định bảng log_batch_sqlserver đã được tạo. COUNT_BIG(*) từ inserted phù hợp với số hàng hiện diện trong tập mới của UPDATE. Không suy đoán giá trị @@ROWCOUNT sau khi body trigger đã thực hiện nhiều SQL khác vẫn là số hàng của lệnh gốc.

### 19.2. Hàm UPDATE(column)

~~~sql
IF UPDATE(so_luong_ton)
BEGIN
    -- Xu ly theo chinh sach cot
END;
~~~

cho biết cột được đề cập trong thao tác theo ngữ nghĩa SQL Server, **không khẳng định giá trị cột thực sự thay đổi**. Muốn audit thay đổi thật, so deleted và inserted.

### 19.3. AFTER và INSTEAD OF

SQL Server có AFTER trigger trên bảng theo quy tắc và INSTEAD OF trigger trên bảng/view trong ngữ cảnh được hỗ trợ. Chúng đều nhìn tập inserted/deleted, không trở thành FOR EACH ROW khi chỉ có một dòng.

## 20. MySQL: chỉ có trigger DML theo hàng

MySQL hỗ trợ:

~~~sql
CREATE TRIGGER ...
BEFORE INSERT ON ... FOR EACH ROW ...
~~~

hoặc:

~~~sql
CREATE TRIGGER ...
AFTER UPDATE ON ... FOR EACH ROW ...
~~~

MySQL **không hỗ trợ statement-level DML trigger tổng quát** như FOR EACH STATEMENT trong PostgreSQL/Oracle.

### 20.1. Audit tồn kho bằng AFTER ROW

~~~sql
DELIMITER //

CREATE TRIGGER trg_mysql_log_ton
AFTER UPDATE ON san_pham
FOR EACH ROW
BEGIN
    IF OLD.so_luong_ton <> NEW.so_luong_ton THEN
        INSERT INTO log_ton_mysql (
            ma_san_pham, old_stock, new_stock
        )
        VALUES (
            NEW.ma_san_pham,
            OLD.so_luong_ton,
            NEW.so_luong_ton
        );
    END IF;
END//

DELIMITER ;
~~~

**DELIMITER** là lệnh của client MySQL phổ biến để nhập body có nhiều dấu chấm phẩy, không phải một phần SQL chuẩn xử lý trên server theo cùng cách.

### 20.2. BEFORE ROW sửa NEW

~~~sql
DELIMITER //

CREATE TRIGGER trg_mysql_trim_ten
BEFORE INSERT ON san_pham
FOR EACH ROW
BEGIN
    SET NEW.ten_san_pham = TRIM(NEW.ten_san_pham);
END//

DELIMITER ;
~~~

Cơ chế SET NEW có thể dùng ở BEFORE trigger theo quy tắc MySQL; AFTER trigger không dùng SET NEW để sửa hàng đã ghi.

### 20.3. Trigger cấm tồn âm

~~~sql
DELIMITER //

CREATE TRIGGER trg_mysql_check_ton
BEFORE UPDATE ON san_pham
FOR EACH ROW
BEGIN
    IF NEW.so_luong_ton < 0 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Ton kho khong duoc am';
    END IF;
END//

DELIMITER ;
~~~

Nếu chỉ cần ngăn stock âm, ưu tiên CHECK constraint trên phiên bản/engine thực thi đúng yêu cầu. Trigger ở đây minh họa SIGNAL.

### 20.4. Tự UPDATE bảng kích hoạt

MySQL có hạn chế với việc trigger/stored function sửa lại bảng đang được câu lệnh gọi trigger sử dụng. Một trigger trên san_pham cố UPDATE san_pham có thể gặp lỗi như **ERROR 1442**. Nếu cần chuẩn hóa giá trị của hàng mới, sử dụng SET NEW trong BEFORE trigger khi phù hợp hoặc sửa chính câu UPDATE gốc.

### 20.5. Muốn log một lần cho câu lệnh?

Không thể giả định có FOR EACH STATEMENT trong MySQL. Hãy dùng stored procedure/service, transaction và bảng log batch với request_id; hoặc gom row audit bằng batch_id rồi xử lý hậu kỳ. **Số row triggers không phải số business requests.**

## 21. SQLite: row trigger và INSTEAD OF trên view

SQLite chỉ hỗ trợ row-level DML triggers theo mô hình thông thường, không có FOR EACH STATEMENT tổng quát.

Ví dụ:

~~~sql
CREATE TABLE log_ton_sqlite (
    log_id INTEGER PRIMARY KEY,
    ma_san_pham TEXT,
    old_stock INTEGER,
    new_stock INTEGER
);
~~~

~~~sql
CREATE TRIGGER trg_sqlite_log_ton
AFTER UPDATE OF so_luong_ton ON san_pham
FOR EACH ROW
WHEN OLD.so_luong_ton IS NOT NEW.so_luong_ton
BEGIN
    INSERT INTO log_ton_sqlite (
        ma_san_pham, old_stock, new_stock
    )
    VALUES (
        NEW.ma_san_pham,
        OLD.so_luong_ton,
        NEW.so_luong_ton
    );
END;
~~~

### 21.1. WHEN kiểm tra giá trị khác

SQLite hỗ trợ WHEN và các toán tử IS/IS NOT theo NULL semantics thích hợp. Với cột NOT NULL như so_luong_ton, <> cũng có thể dùng. UPDATE chọn 4 hàng thì trigger được xét cho 4 hàng, nhưng WHEN có thể làm body không chạy nếu OLD=NEW.

### 21.2. RAISE báo lỗi

~~~sql
CREATE TRIGGER trg_sqlite_check_ton
BEFORE UPDATE OF so_luong_ton ON san_pham
FOR EACH ROW
WHEN NEW.so_luong_ton < 0
BEGIN
    SELECT RAISE(ABORT, 'Ton kho khong duoc am');
END;
~~~

SQLite có các hình thức RAISE khác nhau với hệ quả rollback/conflict riêng; ở đây RAISE(ABORT, ...) minh họa từ chối thao tác.

### 21.3. View SQLite mặc định read-only

Muốn INSERT/UPDATE/DELETE thông qua view SQLite thường phải có **INSTEAD OF trigger**. Trigger này vẫn xử lý hàng theo logic view, không phải statement trigger.

### 21.4. Row count trên view

SQLite có đặc điểm API báo số thay đổi đối với DML qua INSTEAD OF trigger trên view. Không mặc định sqlite3_changes() phản ánh mọi UPDATE bên trong trigger như khi cập nhật trực tiếp bảng gốc; cần quan sát dữ liệu nền hoặc audit được thiết kế rõ khi kết quả quan trọng.

## 22. So sánh phạm vi năm DBMS

| Khía cạnh | PostgreSQL | Oracle | SQL Server | MySQL | SQLite |
|---|---|---|---|---|---|
| Trigger DML theo hàng | Có | Có | Không có cú pháp tương đương | Có | Có |
| Trigger DML theo câu lệnh | Có | Có | Có, DML trigger mặc định theo statement | Không | Không |
| BEFORE ROW | Có | Có | Không theo mô hình này | Có | Có |
| AFTER ROW | Có | Có | Không theo mô hình này | Có | Có |
| AFTER STATEMENT | Có | Có | AFTER trigger xử lý tập theo câu lệnh | Không | Không |
| Giá trị từng hàng | OLD/NEW | :OLD/:NEW | inserted/deleted dạng tập | OLD/NEW | OLD/NEW |
| Tập hàng thay đổi | Transition tables theo điều kiện | Compound trigger/thu thập | inserted/deleted | Không có statement transition tables | Không có statement transition tables |
| INSTEAD OF view | Có, theo hàng | Có, theo hàng | Có, theo câu lệnh | Không tương đương | Có, theo hàng |
| Câu DML 0 hàng | Statement trigger có thể chạy | Statement trigger có thể chạy | Trigger có thể chạy với tập rỗng | Row trigger không chạy | Row trigger không chạy |
| Rủi ro đặc thù | RETURN/transition restrictions | Mutating table | Bỏ sót tập inserted | Tự sửa bảng trigger | View read-only/row trigger |

Bảng là tổng quan. Những tình huống như MERGE, ON CONFLICT, partition, foreign table, cascading actions, trigger bị tắt và version khác nhau có thể có chi tiết riêng.

## 23. Khi nào nên dùng row trigger?

Dùng khi hành động là **thuộc tính của từng thực thể**:

1. Chỉ ghi audit khi old_price khác new_price.
2. Kiểm tra trạng thái không được chuyển từ CANCELLED sang ACTIVE.
3. Chuẩn hóa tên sản phẩm trước lưu.
4. Điền một metadata field của chính hàng.
5. Ghi một log mỗi thay đổi bản ghi khách hàng.
6. Kiểm tra điều kiện dựa vào cặp OLD/NEW.

### 23.1. Row trigger không tự giải một quy tắc trên nhiều hàng

Nếu nghiệp vụ yêu cầu “tổng hạn mức của tất cả giao dịch cùng khách không vượt 100 triệu”, trigger row đọc lại tổng có thể gặp concurrency race hoặc mutating-table restrictions. Cần transaction/locking/constraint hoặc mô hình counter đúng, không chỉ thay trigger vào WHERE.

## 24. Khi nào nên dùng statement trigger?

Dùng khi hành động gắn với **toàn bộ câu lệnh**:

1. Ghi một event audit “đã chạy UPDATE”.
2. Tổng hợp số hàng của một batch update.
3. Ghi tổng stock delta từ transition set.
4. Thực hiện một INSERT ... SELECT từ changed rows.
5. Ghi một outbox event theo batch nếu batch là một câu SQL.
6. Chạy logic hậu xử lý chỉ một lần sau thay đổi nhiều hàng.

### 24.1. Statement trigger không đương nhiên hiệu quả hơn

Nếu body thực hiện JOIN rất lớn hoặc SELECT COUNT(*) toàn bảng, thời gian có thể lâu hơn nhiều row triggers đơn giản. Một lần gọi không bằng chi phí không đáng kể.

### 24.2. Statement trigger không đồng nghĩa một lần cho nghiệp vụ

Nếu service chia batch 10.000 dòng thành 100 câu UPDATE, statement trigger có thể chạy 100 lần. Muốn **một event cho toàn business request**, cần request_id/batch table/service orchestration.

## 25. Audit từng hàng so với audit câu lệnh

Giả sử tăng tồn 5 cho bốn sản phẩm ACTIVE.

**Audit từng hàng:**

| Mã | Tồn cũ | Tồn mới |
|---|---:|---:|
| P01 | 10 | 15 |
| P02 | 5 | 10 |
| P03 | 0 | 5 |
| P05 | 8 | 13 |

**Audit cả câu lệnh:**

~~~text
action = UPDATE_STOCK
affected_rows = 4
sum_old_stock = 23
sum_new_stock = 43
delta = +20
~~~

Hai dạng ghi nhận trả lời **hai câu hỏi khác nhau**. Row audit cho biết từng thực thể; statement audit cho biết tổng hoạt động.

### 25.1. Một UPDATE gán cùng giá trị

Nếu 100 hàng được nhắm tới nhưng chỉ 40 giá trị thật đổi:
- “Rows targeted/affected” có thể là 100 theo một số báo cáo.
- “Changed values” là 40 theo điều kiện OLD/NEW đã định.
- Cần phân biệt matched rows, changed rows và row count theo DBMS/driver.

### 25.2. Audit cả hai mức

PostgreSQL có thể dùng một row trigger cho chi tiết và một statement trigger cho tổng, hoặc một statement trigger dựa trên transition tables để ghi cả hai loại log. SQL Server có thể dùng một trigger set-based cho cả log chi tiết và log tổng. Oracle có thể dùng compound trigger. MySQL/SQLite có thể cần API/batch log ngoài row trigger.

## 26. Trigger và transaction

DML, trigger và các INSERT/UPDATE do trigger thực hiện thường thuộc cùng transaction theo ngữ nghĩa DBMS, trừ cơ chế đặc biệt.

Ví dụ:

~~~text
BEGIN TRANSACTION
   UPDATE san_pham
      -> trigger ghi audit
   INSERT don_hang
   COMMIT nếu mọi bước thành công
   ROLLBACK nếu có lỗi
~~~

Nếu transaction rollback, những dòng audit transactional cũng rollback. **AFTER không có nghĩa sau COMMIT.**

### 26.1. Lỗi trigger có thể hủy thao tác

Các DBMS báo lỗi bằng cơ chế khác nhau:
- PostgreSQL: RAISE EXCEPTION.
- Oracle: RAISE_APPLICATION_ERROR.
- SQL Server: THROW hoặc cơ chế lỗi phù hợp.
- MySQL: SIGNAL.
- SQLite: RAISE(ABORT,...).

Khi trigger lỗi, phạm vi rollback và transaction state phụ thuộc DBMS, cấu hình và hình thức lỗi. Ứng dụng cần xử lý exception và tình trạng transaction; không giả định luôn chỉ bỏ qua một hàng.

### 26.2. Trigger không nên trực tiếp gửi HTTP/email/payment

Nếu trigger gửi email rồi câu INSERT/UPDATE khác thất bại và rollback, email **không tự được thu hồi**. Khi cần tích hợp ngoài:

1. Ghi outbox row trong cùng transaction nghiệp vụ.
2. Commit dữ liệu và outbox.
3. Worker bên ngoài gửi thông điệp.
4. Dùng idempotency key, retry và consumer dedupe.

Như vậy tín hiệu bên ngoài đi sau dữ liệu bền vững, dù hệ thống vẫn phải xử lý trường hợp worker gửi thành công nhưng mất phản hồi.

## 27. Concurrency và khóa

Trigger không tự giải quyết mọi vấn đề concurrent updates. Hai giao dịch có thể đọc cùng tồn kho 10, tính kết quả tuyệt đối 8 và 7 rồi ghi đè nhau.

Nên dùng phép UPDATE tại DB với điều kiện:

~~~sql
UPDATE san_pham
SET so_luong_ton = so_luong_ton - :qty,
    phien_ban = phien_ban + 1
WHERE ma_san_pham = :id
  AND so_luong_ton >= :qty
  AND phien_ban = :expected_version;
~~~

Trong ứng dụng:
- Validate qty > 0.
- Kiểm tra affected rows.
- Ràng buộc CHECK stock>=0.
- Transaction và retry phù hợp khi có deadlock/serialization failure.
- Ghi audit bằng trigger nếu cần.

### 27.1. Trigger đọc nhiều hàng không tự tạo bất biến toàn cục

Nếu trigger lấy SUM của các đơn chưa thanh toán để quyết định hạn mức, hai transaction có thể cùng nhìn tổng trước khi bên kia commit và vượt hạn mức. Cần isolation/locks hoặc schema/counter design bảo đảm bất biến.

### 27.2. Trigger làm tăng thời gian giữ khóa

Nếu mỗi UPDATE gọi trigger ghi nhiều log hoặc truy vấn bảng khác, transaction có thể dài hơn, gia tăng contention và deadlock. Với workload quan trọng phải đo trong điều kiện concurrency thực tế.

## 28. Recursion và trigger lồng nhau

Một AFTER UPDATE trigger trên san_pham tự UPDATE lại san_pham có thể gây vòng:

~~~text
UPDATE san_pham
 -> AFTER UPDATE trigger
    -> UPDATE san_pham
       -> AFTER UPDATE trigger
          -> ...
~~~

Các DBMS có chính sách khác nhau: một số hạn chế recursion/nesting, MySQL hạn chế cập nhật bảng đang kích hoạt, Oracle có mutating-table rules, PostgreSQL có thể cần guard/tầng logic phù hợp.

### 28.1. Hướng thiết kế tốt hơn

- Nếu chỉ cần chỉnh NEW.ten_san_pham, dùng BEFORE ROW khi DBMS hỗ trợ.
- Nếu cần tăng phien_ban, đưa vào UPDATE nghiệp vụ hoặc cơ chế quản lý version đáng tin.
- Nếu cần audit, ghi vào **bảng audit riêng**, tránh trigger audit lại quay về sửa bảng nguồn.
- Nếu thật sự cần trigger lồng nhau, dùng guard rõ, test recursion depth và rollback.

## 29. Constraint trước, trigger sau

Nhiều bài toán dễ được giải trực tiếp bằng constraint:

| Nhu cầu | Giải pháp thường ưu tiên |
|---|---|
| Tồn kho không âm | CHECK |
| Giá không âm | CHECK |
| Mã sản phẩm duy nhất | PRIMARY KEY/UNIQUE |
| Mã khách tồn tại | FOREIGN KEY |
| Trường bắt buộc | NOT NULL |
| Giá trị tính từ cột khác | Generated/computed column khi phù hợp |
| Ghi lịch sử thay đổi từng hàng | Row trigger hoặc statement trigger có changed set |
| Ghi một event mỗi câu DML | Statement trigger/API |
| Gửi sự kiện tới hệ ngoài | Outbox + worker |
| Workflow duyệt nhiều bước | Service/procedure |
| Tenant authorization | GRANT/RLS/server identity |

Trigger có thể bổ sung hành vi mà constraint không thể làm, nhưng không nên thay thế ràng buộc đơn giản bằng logic tự viết dễ lỗi concurrency.

### 29.1. UNIQUE không thể thay bằng SELECT trong trigger

Hai transaction có thể cùng SELECT “chưa có mã P01” rồi cùng INSERT. Một trigger kiểm tra EXISTS vẫn có thể mắc race nếu không có bảo vệ. Unique constraint là lớp đúng để ngăn hai khóa trùng.

## 30. Trigger trên view

Khi view JOIN nhiều bảng, một UPDATE qua view có thể không tự ánh xạ về bảng gốc. INSTEAD OF trigger có thể nhận thao tác và cập nhật bảng nền.

Nhưng một hàng view JOIN không luôn bằng một hàng bảng nền. Nếu một nhân viên JOIN với nhiều bản ghi chi tiết, cùng nhân viên xuất hiện nhiều lần. INSTEAD OF ROW trigger có thể được kích hoạt nhiều lần tương ứng với hàng view; nếu update cùng nhân viên lặp, logic sẽ sai.

Với SQL Server, inserted/deleted chứa **tập hàng view** được tác động; phải dùng JOIN/khóa đúng và xử lý duplicates có chủ đích.

### 30.1. Không âm thầm bỏ qua cột không hỗ trợ

Nếu trigger view chỉ cho sửa luong nhưng client SET ten_phong, trigger phải **từ chối rõ** hoặc triển khai cập nhật hợp lệ, không coi một lần chạy thành công nhưng bỏ thay đổi là hành vi ổn.

## 31. INSERT nhiều hàng và DELETE nhiều hàng

Một INSERT ... SELECT tạo 100 dòng trong một câu SQL:
- Row INSERT trigger có thể chạy 100 lần.
- Statement INSERT trigger có thể chạy một lần.
- SQL Server inserted có 100 dòng.

DELETE xóa 20 dòng:
- Row DELETE trigger có OLD của từng dòng.
- Statement DELETE trigger có thể truy cập tập OLD/deleted theo cơ chế DBMS.

### 31.1. Trạng thái 0 hàng phải được kiểm thử cho INSERT/DELETE

INSERT ... SELECT trả 0 dòng hoặc DELETE WHERE không khớp có thể kích hoạt statement trigger trên hệ hỗ trợ. Row trigger không có hàng tương ứng. Với yêu cầu log từng hàng, không nên tạo audit thay đổi dữ liệu cho empty set.

### 31.2. TRUNCATE không phải DELETE

TRUNCATE có semantics riêng và thường không kích hoạt DELETE row triggers như DELETE từng hàng. PostgreSQL có trigger cho sự kiện TRUNCATE ở phạm vi statement; SQL Server và MySQL TRUNCATE không kích hoạt DELETE triggers theo cách DELETE thông thường. Nếu audit xóa dữ liệu là bắt buộc, cần quyền và quy trình TRUNCATE riêng.

### 31.3. Cascade

FOREIGN KEY ON DELETE/UPDATE CASCADE có thể tạo thay đổi ở bảng con. Trigger ở bảng cha/con có thể bị kích hoạt theo quy tắc DBMS; không giả định một DELETE ở bảng cha chỉ sinh một loại trigger trên chính bảng cha.

## 32. MERGE/UPSERT và số lần kích hoạt

Một câu UPSERT có thể đi qua đường **INSERT đề xuất** rồi phát hiện conflict và chuyển sang **UPDATE**. MERGE có thể chứa nhiều nhánh INSERT/UPDATE/DELETE. Vì vậy số lần trigger không được suy ra chỉ từ số lệnh SQL hiển thị.

### 32.1. PostgreSQL ON CONFLICT DO UPDATE

PostgreSQL có quy tắc firing riêng cho row/statement triggers khi INSERT ... ON CONFLICT DO UPDATE. Một số loại INSERT/UPDATE trigger có thể liên quan trong cùng statement, kể cả khi một nhánh thực tế không có hàng được sửa. Phải kiểm thử đường conflict và RETURNING/audit theo đúng phiên bản.

### 32.2. MySQL ON DUPLICATE KEY UPDATE

MySQL có sự kết hợp các trigger INSERT và UPDATE phù hợp khi một dòng đề xuất chèn gặp unique conflict. Không được mặc định “một input row → chỉ một trigger event loại UPDATE” mà không kiểm chứng.

### 32.3. SQL Server MERGE

MERGE có thể kích hoạt AFTER triggers tương ứng với action INSERT/UPDATE/DELETE; không dựa vào thứ tự firing của các action để điều phối nghiệp vụ có tính thứ tự.

### 32.4. Oracle MERGE

Oracle MERGE kết hợp INSERT và UPDATE theo điều kiện, các trigger liên quan được kích hoạt theo quy tắc Oracle và dữ liệu, có thể gặp lỗi nguồn không ổn định khi nhiều dòng match một target. Test số lần và loại event trên môi trường thật.

### 32.5. Bộ test UPSERT tối thiểu

- Insert khóa mới.
- Conflict dẫn tới UPDATE.
- Conflict nhưng giá trị không đổi.
- Source trùng khóa.
- Câu lệnh không làm đổi hàng.
- Retry cùng request.
- Rollback.
- Các trigger khác trên bảng cùng sự kiện.

## 33. Trigger trên partitioned table

Nếu bảng được partition, trigger khai báo trên bảng cha hay các partition con có thể có hành vi khác. Một UPDATE chuyển hàng từ partition này sang partition khác cũng có thể được hệ triển khai bằng các thao tác nội bộ có quy tắc trigger riêng.

Không suy ra từ bảng thường rằng:
- Mọi statement trigger trên partition con đều chạy khi DML nhắm bảng cha.
- Một hàng di chuyển partition chỉ sinh một event UPDATE.
- Trigger attached to view/partition có cùng OLD/NEW semantics với bảng thường.

Hãy kiểm tra:
1. Đối tượng nhận DML.
2. Trigger khai báo ở cha/con/view.
3. DML tác động bảng nào trong thực tế.
4. Loại event phát sinh khi di chuyển.
5. Phiên bản và chính sách partition của DBMS.

## 34. Thứ tự của nhiều triggers

Một bảng có thể có nhiều BEFORE UPDATE triggers và nhiều AFTER UPDATE triggers. Quy tắc thứ tự khác giữa DBMS; có hệ dựa vào tên hoặc cơ chế cấu hình, có hệ có tùy chọn explicit ordering.

Ví dụ:
- Trigger A chuẩn hóa email.
- Trigger B ghi audit email.

Nếu cả hai ở cùng timing, audit có quan sát trước hay sau chuẩn hóa? Không đoán nếu chưa biết thứ tự/semantics.

### 34.1. Giảm phụ thuộc thứ tự

- Chỉnh NEW ở BEFORE ROW, audit OLD/NEW đã có hiệu lực ở AFTER.
- Nếu hai bước buộc theo thứ tự, cân nhắc gộp trong một trigger/procedure.
- Dùng constraint thay vì trigger phụ thuộc vòng.
- Thử với nhiều triggers cùng event.
- Không dựa vào thứ tự xử lý **các hàng** trong một câu UPDATE.

## 35. Hiệu năng khi trigger chạy trên batch lớn

Giả sử:

~~~sql
UPDATE san_pham
SET gia_ban = gia_ban * 1.02
WHERE trang_thai = 'ACTIVE';
~~~

và câu này ảnh hưởng 500.000 hàng.

### 35.1. Chi phí per-row

Nếu trigger mỗi hàng:
- Đọc OLD/NEW.
- SELECT thêm bảng khác.
- INSERT một audit row.
- Gọi hàm tính toán.
- Giữ khóa và ghi transaction log.

thì tổng số thao tác phụ rất lớn. Có thể xảy ra vấn đề tương tự N+1 queries, ngay bên trong database.

### 35.2. Set-based audit

PostgreSQL AFTER STATEMENT với transition tables hoặc SQL Server với inserted/deleted có thể áp:

~~~sql
INSERT INTO audit_table (...)
SELECT ...
FROM changed_rows
WHERE old_value <> new_value;
~~~

Đây là mô tả mẫu, không phải câu SQL copy-paste cho mọi DBMS. Lợi ích có thể là giảm chi phí gọi body nhiều lần và tận dụng phép xử lý tập, nhưng vẫn có chi phí IO/logging.

### 35.3. Statement trigger không miễn phí

Một trigger statement-level thực hiện SELECT COUNT(*) toàn bảng hay JOIN không có index trên triệu hàng vẫn có thể rất đắt. Số lần gọi body là một yếu tố, **không phải toàn bộ chi phí**.

### 35.4. Tối ưu đúng hướng

- Chỉ audit các cột cần thiết.
- Lọc OLD/NEW khi giá trị thực thay đổi.
- Tránh query thừa trong mỗi row.
- Tránh payload JSON quá lớn và dữ liệu nhạy cảm.
- Dùng index hợp lý trên audit table.
- Đo actual runtime, CPU, IO, WAL/redo và contention.
- Nếu chuyển sang statement trigger, xác nhận logic vẫn xử lý đủ mọi hàng.

## 36. Audit cần những trường gì?

Một bản ghi audit hợp lý có thể gồm:

~~~text
audit_id
event_type
table_name
business_key
old_value
new_value
actor_or_service
request_id
transaction_or_batch_id
recorded_at
schema_version
~~~

Không phải mọi audit cần lưu toàn bộ OLD/NEW JSON. Cần cân bằng:
- Khả năng điều tra và hoàn nguyên.
- Dung lượng lưu.
- Chi phí ghi.
- Dữ liệu nhạy cảm và chính sách retention.
- Quyền truy cập bảng audit.
- Mức độ nhất quán với dữ liệu đã commit.

### 36.1. Actor identity

Trong hệ ứng dụng dùng một DB account chung, CURRENT_USER ở trigger có thể chỉ là tài khoản service chứ không phải người thao tác cuối. Nếu cần actor nghiệp vụ, phải truyền context đáng tin qua ứng dụng/session hoặc dùng một cơ chế audit khác, tránh cho client tự giả mạo.

### 36.2. Audit trong transaction

Nếu audit được INSERT bằng trigger trong cùng transaction, rollback thường hoàn tác audit. Điều đó tốt để log **những thay đổi đã commit** nhưng không phù hợp nếu mục tiêu là log mọi lần cố cập nhật bị từ chối; cần một nguồn bảo mật/audit khác cho unsuccessful attempts.

## 37. Java/JDBC và trigger

Ứng dụng Java thực thi câu lệnh:

~~~java
String sql = """
    UPDATE san_pham
    SET so_luong_ton = so_luong_ton - ?,
        phien_ban = phien_ban + 1
    WHERE ma_san_pham = ?
      AND so_luong_ton >= ?
      AND phien_ban = ?
    """;

int qty = 2;
String productId = "P01";
int expectedVersion = 3;

if (qty <= 0) {
    throw new IllegalArgumentException("So luong phai duong");
}

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setInt(1, qty);
    ps.setString(2, productId);
    ps.setInt(3, qty);
    ps.setInt(4, expectedVersion);

    int count = ps.executeUpdate();
    if (count != 1) {
        throw new IllegalStateException(
            "Khong du ton, khong tim thay hoac sai phien ban"
        );
    }
}
~~~

Trigger trên san_pham nếu có được DBMS tự thực thi; Java không cần gọi nó.

### 37.1. Đừng bỏ qua row count

Một câu UPDATE có thể chọn 0 hàng do không đủ tồn, version sai hoặc ID không tồn tại. Không có lỗi SQL không có nghĩa nghiệp vụ thành công.

Số hàng báo về có thể mang semantics matched/changed khác nhau theo DBMS/driver, và trigger/view có thể làm phản hồi phức tạp hơn. Đặt kỳ vọng row count theo chính câu lệnh và môi trường đang chạy.

### 37.2. Giao dịch nhiều bước

Nếu trừ kho phải đi với INSERT đơn hàng, hai thao tác nên trong cùng transaction DB khi dùng cùng nguồn dữ liệu. Trigger audit không thể thay thế transaction.

### 37.3. JDBC batch

Một executeBatch() ở Java có thể được driver triển khai thành nhiều câu SQL hoặc gộp câu, tùy driver/cấu hình. Statement-level trigger chạy theo những câu DML thật được DBMS thực thi, không phải luôn chính xác một lần cho một lời gọi Java.

## 38. Trigger và dữ liệu nhiều tenant

Giả sử hai tenant cùng có mã P01. Một audit trigger phải lưu đủ khóa:

~~~text
tenant_id
ma_san_pham
old_stock
new_stock
~~~

Nếu chỉ ghi ma_san_pham, audit có thể gộp nhầm thay đổi của T1/P01 và T2/P01.

Tương tự, trigger xử lý dữ liệu liên quan phải dùng **full business key**, không chỉ product code. Phân quyền và tenant scope từ server/RLS phải được kiểm soát; trigger không tự giải quyết nguy cơ client sửa tenant khác.

### 38.1. SECURITY DEFINER/INVOKER và quyền

Các DBMS có mô hình owner/definer/invoker khác nhau; quyền thực thi trigger/function và quyền truy cập bảng audit có thể không giống người gửi câu UPDATE. Cần kiểm tra quyền tối thiểu, search_path/schema resolution và nguy cơ privilege escalation.

## 39. Bộ kiểm thử bắt buộc

| Trường hợp | Kiểm tra |
|---|---|
| UPDATE một hàng | Row=1, statement=1 |
| UPDATE bốn hàng | Row=4, statement=1 |
| UPDATE không khớp | Row=0, statement-level xử lý tập rỗng |
| Bốn câu UPDATE một hàng | Statement trigger bốn lần |
| INSERT 100 hàng | Row=100, statement=1 |
| DELETE nhiều hàng | OLD/deleted đúng |
| UPDATE gán giá cũ | Có trigger nhưng có cần audit không |
| UPDATE OF cột | Không đồng nhất với value changed |
| BEFORE ROW chỉnh NEW | Hàng được ghi đúng |
| AFTER ROW audit | OLD/NEW chính xác |
| PostgreSQL transition tables | Số hàng/tổng đúng |
| Oracle compound trigger | Biến đếm 0/1/n |
| Oracle mutating-table | Không SELECT cùng bảng sai ngữ cảnh |
| SQL Server inserted nhiều hàng | Không dùng scalar lấy một hàng |
| SQL Server 0 rows | IF RETURN hoặc log zero theo policy |
| MySQL không FOR EACH STATEMENT | Dùng API/batch nếu cần |
| MySQL cùng bảng trong trigger | Không gặp recursion/ERROR 1442 |
| SQLite WHEN | Không ghi log khi không đổi |
| SQLite view INSTEAD OF | Bảng nền thực đổi |
| Trigger lỗi | Rollback/transaction state đúng |
| Trigger lồng nhau | Không vòng vô hạn |
| Hai transaction cập nhật | Không mất cập nhật |
| Retry request | Không nhân side effect |
| MERGE/UPSERT | Đúng nhánh trigger |
| TRUNCATE | Không mất audit không chủ đích |
| FK cascade | Các trigger liên quan đúng |
| Multi-tenant | Không trộn khóa |
| Dữ liệu nhạy cảm | Audit không lộ ngoài policy |
| Batch 100k hàng | Đo CPU/IO/log/lock |
| Tắt/bật trigger | Có kiểm soát vận hành |
| Đổi schema | Trigger vẫn hợp lệ |

## 40. Những sai lầm phổ biến

| Sai lầm | Hậu quả | Giải pháp |
|---|---|---|
| Nghĩ một UPDATE luôn sửa một hàng | Đếm trigger sai | Hiểu SQL theo tập |
| Nghĩ AFTER tức statement-level | Trộn timing và phạm vi | Tách hai trục |
| Nghĩ statement trigger chạy n lần | Audit lặp | Một lần/câu |
| Quên trường hợp 0 hàng | Ghi/đếm thiếu | Test tập rỗng |
| Giả định MySQL có statement trigger | SQL không hỗ trợ | Row trigger hoặc API |
| Dùng OLD/NEW scalar trên SQL Server | Bỏ qua tập inserted/deleted | Viết set-based |
| SELECT một scalar từ inserted | Bỏ sót nhiều hàng | INSERT SELECT/JOIN |
| Dùng COUNT sau nhiều SQL trong trigger | Row count sai | Đếm pseudo-table phù hợp |
| Truy cập OLD trong INSERT | Không có hàng cũ | Dùng NEW |
| Truy cập NEW trong DELETE | Không có hàng mới | Dùng OLD |
| Không so OLD/NEW khi audit | Log cả giá trị không đổi | Null-safe comparison |
| Nghĩ UPDATE OF tức giá trị khác | Log nhầm | So cũ/mới |
| PostgreSQL BEFORE RETURN NULL tùy ý | Bỏ qua hàng | RETURN NEW khi cần ghi |
| Oracle row trigger SELECT bảng đang sửa | ORA-04091 | Compound/constraint |
| MySQL trigger UPDATE lại bảng kích hoạt | ERROR 1442/thiết kế sai | SET NEW hoặc DML gốc |
| Trigger tự gọi lặp | Recursion/deadlock | Guard/tránh vòng |
| Dựa vào thứ tự xử lý hàng | Bất định | Sequence/logic tập hợp |
| Dùng trigger gửi HTTP | Side effect không rollback | Outbox |
| Audit mọi trường nhạy cảm | Lộ dữ liệu | Whitelist/retention |
| Trigger thay UNIQUE | Race condition | UNIQUE constraint |
| Trigger thay optimistic locking | Lost update | Version predicate |
| Statement trigger đếm 0 như 1 thay đổi | Audit sai nghĩa | COUNT changed set |
| Nhầm statement với transaction | Đếm business event sai | Request/batch id |
| TRUNCATE như DELETE | Không chạy DELETE trigger | Quy trình riêng |
| Không test MERGE | Kích hoạt loại trigger ngoài dự đoán | Test từng nhánh |
| Không đo với batch lớn | Transaction dài | Set-based/tối ưu |
| Trigger trên view bỏ qua cột | Client tưởng thành công | Reject rõ |
| Không tài liệu hóa | Side effects ẩn | Sơ đồ/công bố policy |

## 41. Bài tập thực hành có đáp án

Mỗi bài độc lập từ dữ liệu và mô hình ban đầu, trừ khi ghi khác. Lệnh DML chỉ dùng trong môi trường thử nghiệm.

### Bài 1 — Một hàng

UPDATE đúng P01. Row và statement trigger chạy bao nhiêu lần?

<details>
<summary>Đáp án</summary>

Row=**1**, statement=**1** ở DBMS có hai loại.

</details>

### Bài 2 — Bốn hàng

Một UPDATE chọn bốn sản phẩm ACTIVE. Row và statement trigger chạy bao nhiêu lần?

<details>
<summary>Đáp án</summary>

Row=**4**; statement=**1**.

</details>

### Bài 3 — Không có hàng

UPDATE WHERE ma_san_pham='P99' không có dữ liệu. So trigger theo hàng/câu lệnh.

<details>
<summary>Đáp án</summary>

Row=**0**; statement-level trigger có thể chạy **1** trên PostgreSQL/Oracle/SQL Server, dù tập thay đổi rỗng.

</details>

### Bài 4 — Bốn câu UPDATE

Bốn câu UPDATE riêng, mỗi câu một hàng. Statement trigger chạy một hay bốn lần?

<details>
<summary>Đáp án</summary>

**Bốn lần**, mỗi câu DML một lần.

</details>

### Bài 5 — BEFORE khác ROW

BEFORE là chỉ dấu số lần kích hoạt hay thời điểm?

<details>
<summary>Đáp án</summary>

**Thời điểm.** FOR EACH ROW/FOR EACH STATEMENT mới là phạm vi.

</details>

### Bài 6 — UPDATE OLD/NEW

P01 tồn 10, UPDATE xuống 8. Trigger hàng thấy OLD/NEW là gì?

<details>
<summary>Đáp án</summary>

OLD.stock=10, NEW.stock=8 (cú pháp cụ thể theo DBMS).

</details>

### Bài 7 — INSERT OLD

Trong row INSERT trigger, có OLD của hàng chưa tồn tại không?

<details>
<summary>Đáp án</summary>

**Không.** Có NEW cho bản ghi được chèn.

</details>

### Bài 8 — DELETE NEW

Trong row DELETE trigger, có NEW của hàng bị xóa không?

<details>
<summary>Đáp án</summary>

**Không.** Dùng OLD.

</details>

### Bài 9 — Set cùng giá

UPDATE SET gia_ban=gia_ban có thể kích hoạt row UPDATE trigger không?

<details>
<summary>Đáp án</summary>

**Có** nếu hàng nằm trong tập UPDATE. Nếu chỉ muốn log đổi thực, so OLD.gia_ban và NEW.gia_ban.

</details>

### Bài 10 — PostgreSQL trigger row

Viết khung CREATE TRIGGER AFTER UPDATE theo hàng.

<details>
<summary>Đáp án</summary>

~~~sql
CREATE TRIGGER trg_example
AFTER UPDATE ON san_pham
FOR EACH ROW
EXECUTE FUNCTION fn_example();
~~~

fn_example phải là một trigger function hợp lệ.

</details>

### Bài 11 — PostgreSQL trigger statement

Viết khung AFTER UPDATE statement-level.

<details>
<summary>Đáp án</summary>

~~~sql
CREATE TRIGGER trg_example_stmt
AFTER UPDATE ON san_pham
FOR EACH STATEMENT
EXECUTE FUNCTION fn_example_stmt();
~~~

</details>

### Bài 12 — PostgreSQL RETURN NULL

BEFORE ROW trigger trả NULL có thể gây tác động gì?

<details>
<summary>Đáp án</summary>

Có thể **bỏ qua thao tác đối với hàng đó**. RETURN NEW nếu muốn tiếp tục ghi hàng mới đã kiểm tra/chỉnh sửa.

</details>

### Bài 13 — PostgreSQL transition tables

Cú pháp nào cho statement trigger xem toàn bộ OLD/NEW rows của UPDATE?

<details>
<summary>Đáp án</summary>

~~~sql
REFERENCING OLD TABLE AS old_rows
            NEW TABLE AS new_rows
FOR EACH STATEMENT
~~~

trong AFTER UPDATE trigger hợp lệ theo quy tắc PostgreSQL.

</details>

### Bài 14 — Transition rỗng

UPDATE không khớp hàng, COUNT(*) FROM new_rows trả gì?

<details>
<summary>Đáp án</summary>

**0**, dù statement trigger vẫn được gọi.

</details>

### Bài 15 — Oracle OLD/NEW

Oracle dùng dấu gì trước OLD/NEW trong row trigger?

<details>
<summary>Đáp án</summary>

Dùng **:OLD.col** và **:NEW.col**.

</details>

### Bài 16 — Oracle statement

Trong Oracle, DML trigger không có FOR EACH ROW thường là loại nào?

<details>
<summary>Đáp án</summary>

**Statement-level trigger**, theo mô hình DML thông thường.

</details>

### Bài 17 — Compound trigger

Muốn đếm 4 hàng ở AFTER EACH ROW rồi log một lần ở AFTER STATEMENT, dùng cơ chế gì trong Oracle?

<details>
<summary>Đáp án</summary>

**Compound trigger** với biến đếm chia sẻ trong một câu DML.

</details>

### Bài 18 — Mutating table

Oracle row trigger SELECT lại san_pham đang UPDATE có thể gặp lỗi nào?

<details>
<summary>Đáp án</summary>

**ORA-04091 (mutating table)**; dùng :OLD/:NEW, constraint hoặc compound trigger phù hợp.

</details>

### Bài 19 — SQL Server pseudo-table

SQL Server dùng tên nào cho tập giá trị cũ và mới?

<details>
<summary>Đáp án</summary>

**deleted** cho giá trị cũ, **inserted** cho giá trị mới.

</details>

### Bài 20 — SQL Server nhiều hàng

Vì sao SELECT @id=ma_san_pham FROM inserted rồi chỉ log @id là sai?

<details>
<summary>Đáp án</summary>

Vì inserted có thể có nhiều hàng. Biến scalar chỉ giữ một giá trị, có thể bỏ sót các hàng. Dùng INSERT ... SELECT/JOIN set-based.

</details>

### Bài 21 — SQL Server 0 hàng

Muốn không ghi log khi inserted rỗng, viết gì?

<details>
<summary>Đáp án</summary>

~~~sql
IF NOT EXISTS (SELECT 1 FROM inserted)
    RETURN;
~~~

Chỉ sử dụng nếu không cần audit câu lệnh 0 hàng.

</details>

### Bài 22 — SQL Server UPDATE(column)

IF UPDATE(so_luong_ton) có bảo đảm stock thực đổi không?

<details>
<summary>Đáp án</summary>

**Không.** Nó phản ánh cột được cập nhật theo ngữ nghĩa câu lệnh, không so giá trị cũ/mới. Phải so inserted với deleted.

</details>

### Bài 23 — MySQL statement trigger

MySQL có FOR EACH STATEMENT DML tổng quát không?

<details>
<summary>Đáp án</summary>

**Không.** MySQL có trigger DML FOR EACH ROW; dùng procedure/service/batch log nếu cần một event mỗi statement.

</details>

### Bài 24 — MySQL SET NEW

Ở BEFORE INSERT MySQL, viết câu chuẩn hóa tên thế nào?

<details>
<summary>Đáp án</summary>

~~~sql
SET NEW.ten_san_pham = TRIM(NEW.ten_san_pham);
~~~

</details>

### Bài 25 — MySQL cùng bảng

Trigger trên san_pham tự UPDATE san_pham có rủi ro gì?

<details>
<summary>Đáp án</summary>

Có thể bị hạn chế bởi MySQL và gặp **ERROR 1442**; nên xử lý NEW ở BEFORE hoặc cập nhật từ câu lệnh gốc.

</details>

### Bài 26 — SQLite

SQLite có FOR EACH STATEMENT DML trigger không?

<details>
<summary>Đáp án</summary>

**Không**, cơ chế DML trigger thông thường theo hàng. Cần service/procedure ứng dụng cho audit cấp câu lệnh.

</details>

### Bài 27 — SQLite WHEN

Muốn ghi log chỉ khi tồn kho khác, dùng điều kiện nào?

<details>
<summary>Đáp án</summary>

~~~sql
WHEN OLD.so_luong_ton IS NOT NEW.so_luong_ton
~~~

theo null-safe syntax SQLite.

</details>

### Bài 28 — INSTEAD OF

INSTEAD OF trigger luôn chạy một lần mỗi câu SQL không?

<details>
<summary>Đáp án</summary>

**Không.** PostgreSQL/Oracle/SQLite có INSTEAD OF view triggers theo hàng; SQL Server xử lý theo câu lệnh.

</details>

### Bài 29 — AFTER và COMMIT

AFTER trigger chạy xong là dữ liệu đã COMMIT chưa?

<details>
<summary>Đáp án</summary>

**Chưa chắc.** Trigger thường thuộc transaction trước commit; rollback có thể hoàn tác audit và DML trong cùng giao dịch.

</details>

### Bài 30 — Trigger gửi email

Vì sao không nên gửi email trực tiếp từ AFTER trigger?

<details>
<summary>Đáp án</summary>

Vì ROLLBACK không thu hồi email đã gửi. Nên dùng transactional outbox và worker gửi sau commit, hỗ trợ retry/idempotency.

</details>

### Bài 31 — Constraint hay trigger?

Để kiểm tra stock>=0, chọn CHECK hay trigger?

<details>
<summary>Đáp án</summary>

Ưu tiên **CHECK(stock>=0)** khi DBMS/phiên bản thực thi phù hợp; trigger có thể bổ sung nghiệp vụ khác nhưng không cần cho bất biến đơn giản.

</details>

### Bài 32 — Lost update

Trigger audit OLD/NEW có tự ngăn hai transaction ghi đè kho không?

<details>
<summary>Đáp án</summary>

**Không.** Cần UPDATE tương đối, WHERE stock>=qty/version, transaction/isolation và xử lý xung đột.

</details>

### Bài 33 — Transaction nhiều câu

Một transaction có ba UPDATE. Statement trigger log bao nhiêu lần?

<details>
<summary>Đáp án</summary>

Thông thường **ba lần** theo ba câu UPDATE, không phải một lần cho transaction.

</details>

### Bài 34 — TRUNCATE

Có nên TRUNCATE bảng khi audit dựa vào DELETE ROW trigger không?

<details>
<summary>Đáp án</summary>

**Không** nếu không có cơ chế audit khác; TRUNCATE thường không kích hoạt DELETE row triggers như DELETE thông thường.

</details>

### Bài 35 — UPSERT

Vì sao một UPSERT có thể kích hoạt nhiều loại trigger INSERT/UPDATE?

<details>
<summary>Đáp án</summary>

Vì có nhánh insert đề xuất và conflict update theo cơ chế DBMS. Trigger firing phụ thuộc đường thực thi, timing và loại trigger; phải test trên phiên bản thật.

</details>

### Bài 36 — Hiệu năng

UPDATE một triệu hàng và row trigger mỗi hàng SELECT thêm một bảng. Rủi ro gì?

<details>
<summary>Đáp án</summary>

Có thể tốn nhiều CPU/IO, lock, transaction log và thời gian. Cân nhắc set-based processing, indexes, giảm SQL per-row và đo actual workload.

</details>

### Bài 37 — Recursion

AFTER UPDATE san_pham tự UPDATE san_pham có vấn đề gì?

<details>
<summary>Đáp án</summary>

Có thể tạo recursion, deadlock hoặc lỗi DBMS. Dùng BEFORE chỉnh NEW khi phù hợp, hoặc đặt version/công thức vào DML gốc.

</details>

### Bài 38 — Bảo mật audit

Vì sao không ghi mọi OLD/NEW cột không chọn lọc?

<details>
<summary>Đáp án</summary>

Vì có thể lộ PII/secret, tốn dung lượng và khó quản lý retention. Audit theo whitelist cột cần thiết, quyền tối thiểu và chính sách bảo vệ.

</details>

### Bài 39 — Trigger gắn view

INSTEAD OF trigger trên view JOIN có thể cập nhật cùng hàng gốc nhiều lần vì sao?

<details>
<summary>Đáp án</summary>

Vì một hàng gốc có thể xuất hiện nhiều dòng trong kết quả JOIN. Cần khóa duy nhất, tránh duplicate effects và xử lý tập đúng theo DBMS.

</details>

### Bài 40 — Chọn kiến trúc theo DBMS

Cần log mỗi old/new stock và một log tổng với số hàng mỗi UPDATE. Nên làm gì trên PostgreSQL và SQL Server?

<details>
<summary>Đáp án</summary>

**PostgreSQL:** row trigger cho log chi tiết, statement trigger với transition tables cho tổng; hoặc xử lý cả hai từ changed set trong statement trigger phù hợp.

**SQL Server:** một AFTER UPDATE trigger dùng inserted/deleted để INSERT SELECT log chi tiết và COUNT_BIG(*) cho log tổng. Xử lý set rỗng và giá trị không đổi theo policy.

</details>

### Bài 41 — Test bắt buộc

Ba số lượng hàng nên thử tối thiểu khi kiểm chứng trigger là gì?

<details>
<summary>Đáp án</summary>

**0, 1 và nhiều hàng**. Kèm INSERT/UPDATE/DELETE, giá trị không đổi, lỗi, rollback, UPSERT, concurrent transactions và retry.

</details>

### Bài 42 — Bài toán tổng hợp

Một batch cập nhật 100 sản phẩm, không được tồn âm, cần audit old/new, sau commit gửi một thông điệp tổng batch_id và client có thể retry. Thiết kế?

<details>
<summary>Đáp án</summary>

1. CHECK(stock>=0), validate qty>0.
2. UPDATE đúng điều kiện stock/version với transaction.
3. Audit từng hàng bằng row trigger hoặc set-based statement trigger tùy DBMS.
4. Ghi một outbox event theo batch_id trong cùng transaction.
5. Dùng UNIQUE idempotency key ngăn xử lý lại.
6. Commit dữ liệu + audit + outbox; worker gửi sau commit.
7. Test rollback, failure giữa batch, retry, 0/1/100 hàng, cạnh tranh đồng thời và duplicate delivery.

</details>

## 42. Quy trình thiết kế trigger có kiểm soát

**Bước 1 — Viết nghĩa của sự kiện.** “Có câu UPDATE” khác “có hàng được nhắm”, “có giá trị thay đổi” và “business request đã commit”.

**Bước 2 — Chọn granularity.** Theo hàng nếu cần OLD/NEW riêng; theo câu lệnh nếu cần tổng; theo request nếu cần business event. Không ghép lẫn những phạm vi này.

**Bước 3 — Chọn timing.** BEFORE để validate/chỉnh NEW nếu hỗ trợ; AFTER để audit; INSTEAD OF cho view phức tạp.

**Bước 4 — Xác định DBMS.** PostgreSQL/Oracle có row và statement, SQL Server statement-level DML triggers với inserted/deleted, MySQL/SQLite chủ yếu row-level.

**Bước 5 — Dùng constraint/transaction cho bất biến.** Trigger audit không thay CHECK/UNIQUE/FOREIGN KEY/optimistic locking.

**Bước 6 — Thiết kế set-based.** Nếu dùng statement trigger, xử lý tập thay đổi đầy đủ, không lấy một scalar rồi bỏ các hàng khác.

**Bước 7 — Kiểm soát side effects.** Không tự sửa bảng vô hạn, không gọi HTTP trực tiếp, không log secrets.

**Bước 8 — Thử các trường hợp biên.** 0/1/n hàng, NULL, giá trị không đổi, MERGE/UPSERT, TRUNCATE, FK cascade, rollback và lỗi.

**Bước 9 — Đo dưới tải.** CPU, logical reads, log growth, thời gian transaction, locks và deadlocks.

**Bước 10 — Ghi tài liệu vận hành.** Trigger nào gắn bảng/view nào, firing semantics, changed-column policy, log table, quyền, error behavior và cách tắt/bật được phép.

## 43. Kết luận cần ghi nhớ

1. **Row-level trigger** được kích hoạt theo từng hàng bị tác động, không theo số câu UPDATE.
2. **Statement-level trigger** được kích hoạt một lần cho câu lệnh, có thể ngay cả khi không có hàng nào bị tác động trên DBMS hỗ trợ.
3. **Một UPDATE sửa nhiều hàng** khác **nhiều UPDATE riêng lẻ** về số lần statement trigger.
4. **BEFORE/AFTER/INSTEAD OF** là thời điểm/thay thế hành động; **ROW/STATEMENT** là phạm vi.
5. **OLD/NEW** thuộc ngữ cảnh từng hàng trên PostgreSQL, Oracle, MySQL và SQLite; SQL Server dùng **deleted/inserted** dạng tập.
6. **PostgreSQL** có FOR EACH ROW/STATEMENT, trigger functions, RETURN và transition tables.
7. **Oracle** có :OLD/:NEW, statement triggers và compound triggers; cần tránh mutating table/ORA-04091.
8. **SQL Server** DML triggers hoạt động theo statement; phải xử lý inserted/deleted set-based, không giả định một dòng.
9. **MySQL** có DML triggers theo hàng, không có statement trigger phổ thông; hạn chế tự sửa bảng kích hoạt.
10. **SQLite** có row triggers và INSTEAD OF triggers trên view; không có statement-level DML trigger tổng quát.
11. **UPDATE gán lại cùng giá trị** vẫn có thể kích hoạt UPDATE trigger. Muốn audit thay đổi thực, so OLD và NEW.
12. **AFTER không đồng nghĩa COMMIT**; trigger thường nằm trong transaction, có thể bị rollback.
13. **Trigger không thay constraint, version predicate, locking, idempotency hoặc quyền bảo mật**.
14. **Một business request** có thể gồm nhiều statements; statement trigger không tự là event theo request.
15. **Trigger có thể làm DML chậm và giữ khóa lâu hơn**; đặc biệt lưu ý row triggers trên batch lớn.
16. **Không tạo side effect ngoài DB trực tiếp trong trigger** khi cần nhất quán; dùng transactional outbox.
17. **UPSERT, MERGE, TRUNCATE, FK cascade, partition và view** có các quy tắc firing riêng phải kiểm tra theo DBMS/phiên bản.
18. Khi thiết kế, luôn trả lời: **“Trigger chạy bao nhiêu lần, nó nhìn những hàng nào, thay đổi gì, và rollback/retry sẽ để lại điều gì?”**

### Tài liệu chính thức theo DBMS

Khi triển khai thực tế nên tham khảo tài liệu **đúng phiên bản**:

- **PostgreSQL Documentation:** CREATE TRIGGER, Trigger Procedures, PL/pgSQL Trigger Functions, Transition Tables, Trigger Behavior, Partitioned Tables.
- **Oracle Database SQL Language Reference / PL/SQL Language Reference:** CREATE TRIGGER, DML Triggers, Compound Triggers, Mutating-Table Restrictions.
- **Microsoft Learn — SQL Server:** CREATE TRIGGER, DML Triggers, Use the inserted and deleted Tables, Trigger Nesting/Recursion, MERGE Trigger Behavior.
- **MySQL Reference Manual:** CREATE TRIGGER, Trigger Syntax, Stored Program Restrictions, SIGNAL, ON DUPLICATE KEY UPDATE.
- **SQLite Documentation:** CREATE TRIGGER, INSTEAD OF Triggers, RAISE(), Recursive Triggers, Transactions.
- **Java JDBC:** PreparedStatement, executeUpdate, batch execution, transaction management and row count.

**Thông điệp cuối cùng:** Đừng chọn trigger chỉ vì thấy câu lệnh có INSERT, UPDATE hay DELETE. Hãy chọn dựa trên **phạm vi cần quan sát — một hàng, cả câu lệnh hay toàn bộ nghiệp vụ**, dùng đúng cơ chế DBMS và kiểm thử tập thay đổi 0, 1 và nhiều hàng. Đó là nền tảng để trigger chính xác, dễ kiểm soát và an toàn khi dữ liệu tăng quy mô.
