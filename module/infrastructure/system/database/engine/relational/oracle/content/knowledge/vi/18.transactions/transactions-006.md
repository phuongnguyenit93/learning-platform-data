# Implicit commit của DDL và tác động đến script triển khai trong Oracle Database

Trong Oracle Database, các lệnh thay đổi cấu trúc như CREATE TABLE, ALTER TABLE, CREATE INDEX, DROP và TRUNCATE có một đặc điểm quan trọng: chúng tạo ra **implicit commit** (COMMIT ngầm). Đặc điểm này ảnh hưởng trực tiếp đến cách thiết kế transaction, viết script triển khai, chạy migration và xử lý lỗi.

Một hiểu lầm thường gặp là đặt nhiều câu lệnh DML và DDL trong cùng một script rồi nghĩ rằng chỉ cần ROLLBACK ở cuối là có thể hoàn tác toàn bộ nếu có lỗi. Trong Oracle, điều đó không đúng. Trước khi thực thi DDL, Oracle commit transaction hiện tại. Khi DDL thành công, thay đổi cấu trúc cũng được commit. Vì vậy, DDL có thể tạo ranh giới transaction giữa các câu DML trong cùng script.

Bài học giải thích quy tắc commit ngầm, phân biệt DDL với DML, minh họa tác động đến SAVEPOINT và ROLLBACK, so sánh DELETE với TRUNCATE, xử lý DDL trong PL/SQL/JDBC, và xây dựng chiến lược triển khai schema an toàn khi migration có cả thay đổi cấu trúc lẫn dữ liệu.

## 1. Transaction trong Oracle và hai nhóm lệnh thường gặp

Transaction là một đơn vị công việc dữ liệu. Với DML thông thường, ứng dụng có thể thực hiện nhiều thao tác rồi quyết định:

- COMMIT: xác nhận thay đổi.
- ROLLBACK: hủy các thay đổi chưa commit.
- ROLLBACK TO SAVEPOINT: quay lại một điểm lưu trong transaction hiện tại.

Ví dụ:

~~~sql
UPDATE accounts
SET balance = balance - 100
WHERE account_id = 10;

UPDATE accounts
SET balance = balance + 100
WHERE account_id = 20;

-- Chỉ khi mọi thao tác hợp lệ:
COMMIT;
~~~

Nếu kiểm tra phát hiện lỗi trước COMMIT, có thể ROLLBACK để hủy cả hai UPDATE.

Tuy nhiên, Oracle phân biệt rõ hai nhóm lệnh:

| Nhóm | Ví dụ | Hành vi transaction thường gặp |
|---|---|---|
| DML (Data Manipulation Language) | INSERT, UPDATE, DELETE, MERGE | Thay đổi dữ liệu trong transaction; có thể COMMIT hoặc ROLLBACK |
| DDL (Data Definition Language) | CREATE, ALTER, DROP, TRUNCATE, RENAME, COMMENT | Oracle thực hiện implicit commit trước khi chạy DDL và commit thay đổi DDL khi lệnh thành công |

SELECT chỉ đọc dữ liệu và không tự commit các thay đổi DML đang chờ trong transaction. Các lệnh điều khiển transaction như COMMIT, ROLLBACK và SAVEPOINT có semantics riêng.

## 2. Quy tắc implicit commit của DDL

### 2.1 Commit trước và sau DDL

Oracle thực hiện commit ngầm quanh một câu lệnh DDL:

1. **Trước khi thực thi DDL:** commit transaction hiện tại của session, bao gồm các thay đổi DML chưa commit.
2. **Thực thi DDL:** Oracle áp dụng thay đổi metadata/cấu trúc theo câu lệnh.
3. **Sau khi DDL thành công:** thay đổi DDL được commit.

Có thể hình dung:

~~~text
Transaction A
    |
    +-- INSERT / UPDATE / DELETE chưa commit
    |
    v
Chạy một câu DDL
    |
    +-- Oracle COMMIT transaction A trước DDL
    |
    +-- Thực thi CREATE / ALTER / DROP / TRUNCATE ...
    |
    +-- Nếu DDL thành công: commit thay đổi DDL
    |
    v
Transaction mới
    |
    +-- DML tiếp theo
    |
    +-- COMMIT hoặc ROLLBACK riêng
~~~

Điểm quan trọng nhất: implicit commit trước DDL có thể commit **mọi DML chưa commit của session**, không chỉ dữ liệu liên quan đến đối tượng mà DDL đang thay đổi.

### 2.2 Ví dụ: DDL commit DML trước đó

Giả sử có bảng lab:

~~~sql
CREATE TABLE ddl_commit_demo (
    id   NUMBER PRIMARY KEY,
    note VARCHAR2(100)
);
~~~

Sau đó chạy:

~~~sql
INSERT INTO ddl_commit_demo (id, note)
VALUES (1, 'DML before DDL');

CREATE TABLE ddl_marker (
    id NUMBER
);

ROLLBACK;
~~~

Kết quả:

~~~sql
SELECT *
FROM ddl_commit_demo
WHERE id = 1;
~~~

Dòng ID=1 vẫn tồn tại. Lý do:

- INSERT tạo thay đổi DML chưa commit.
- CREATE TABLE ddl_marker kích hoạt implicit commit trước khi thực thi.
- INSERT đã được commit tại thời điểm đó.
- ROLLBACK sau CREATE TABLE chỉ tác động đến các thay đổi còn nằm trong transaction hiện tại; nó không thể hoàn tác INSERT đã commit.

Đây là ví dụ điển hình cho thấy một DDL không liên quan đến bảng DML vẫn có thể commit dữ liệu DML trước đó.

### 2.3 Nếu DDL thất bại thì sao?

Giả sử:

~~~sql
INSERT INTO ddl_commit_demo (id, note)
VALUES (2, 'DML before failed DDL');

CREATE TABLE ddl_commit_demo (
    id NUMBER
);
~~~

CREATE TABLE thất bại vì đối tượng đã tồn tại, nhưng transaction DML trước đó đã bị commit trước khi Oracle thử thực thi DDL. Lỗi của CREATE TABLE không làm INSERT quay lại trạng thái chưa commit.

Phải phân biệt hai việc:

- **DML trước DDL:** đã được commit bởi bước implicit commit trước khi DDL chạy.
- **DDL bị lỗi:** thay đổi cấu trúc mà câu lệnh lỗi không được hoàn tất; lỗi DDL không khôi phục transaction trước đó.

Vì vậy, không được dựa vào giả định “DDL lỗi thì toàn bộ script rollback”.

### 2.4 DML sau DDL vẫn có thể rollback

Sau khi DDL thành công, một transaction mới có thể bắt đầu:

~~~sql
CREATE TABLE ddl_after_demo (
    id NUMBER PRIMARY KEY,
    note VARCHAR2(100)
);

INSERT INTO ddl_after_demo VALUES (1, 'after DDL');

ROLLBACK;
~~~

INSERT sau CREATE TABLE chưa được commit bởi một DDL khác hoặc COMMIT tường minh, nên ROLLBACK có thể hủy dòng ID=1. Bảng vẫn tồn tại vì CREATE TABLE đã được commit.

Một script có thể vì thế chứa cả thay đổi không thể rollback bằng transaction thông thường và thay đổi DML còn rollback được. Phải biết rõ transaction boundary nằm ở đâu.

## 3. Những lệnh DDL thường gặp có implicit commit

Các lệnh DDL phổ biến trong quá trình phát triển và triển khai schema gồm:

| Lệnh | Ví dụ | Tác động |
|---|---|---|
| CREATE TABLE | Tạo bảng mới | Tạo metadata và cấu trúc bảng |
| ALTER TABLE | Thêm cột, đổi constraint | Thay đổi định nghĩa bảng |
| DROP TABLE | Xóa bảng | Gỡ đối tượng bảng khỏi schema |
| TRUNCATE TABLE | Xóa toàn bộ dòng theo cơ chế truncate | DDL, không rollback như DELETE |
| CREATE INDEX | Tạo index | Thay đổi cấu trúc truy cập |
| DROP INDEX | Xóa index | Gỡ index |
| CREATE SEQUENCE | Tạo sequence | Tạo đối tượng cấp số |
| ALTER SEQUENCE | Thay đổi cấu hình sequence | Thay đổi metadata sequence |
| RENAME | Đổi tên đối tượng | Thay đổi metadata |
| COMMENT ON | Ghi chú đối tượng/cột | Thay đổi metadata |
| CREATE VIEW | Tạo view | Tạo metadata view |
| CREATE OR REPLACE PROCEDURE | Tạo/thay thế procedure | Thay đổi đối tượng PL/SQL |

Không nên chỉ ghi nhớ một danh sách tên lệnh. Khi đưa một lệnh quản trị schema vào script, hãy xác định đó là DDL hay DML và kiểm tra tài liệu SQL Language Reference của phiên bản Oracle đang dùng nếu chưa chắc chắn.

### 3.1 CREATE TABLE AS SELECT (CTAS)

CTAS là DDL:

~~~sql
CREATE TABLE sales_snapshot AS
SELECT *
FROM sales
WHERE sale_date >= DATE '2026-01-01';
~~~

Dù câu lệnh có SELECT, phần CREATE TABLE AS SELECT vẫn là DDL và kích hoạt implicit commit. Không được coi CTAS là một SELECT thuần túy có thể rollback cùng các DML trước đó.

### 3.2 CREATE INDEX cũng là DDL

~~~sql
CREATE INDEX idx_orders_customer
ON orders (customer_id);
~~~

Tạo index có thể commit transaction đang mở trước khi câu lệnh thực thi. Nếu script đã UPDATE dữ liệu nhưng chưa COMMIT, CREATE INDEX tiếp theo có thể commit luôn UPDATE đó.

### 3.3 TRUNCATE là DDL, không phải DELETE

~~~sql
TRUNCATE TABLE staging_orders;
~~~

TRUNCATE xóa dữ liệu theo cơ chế DDL. Nó có implicit commit và không thể được hoàn tác bằng ROLLBACK thông thường. Nếu cần xóa có khả năng rollback, dùng DELETE trong transaction phù hợp:

~~~sql
DELETE FROM staging_orders;

-- Kiểm tra kết quả:
SELECT COUNT(*) FROM staging_orders;

-- Chọn một trong hai:
-- COMMIT;
-- ROLLBACK;
~~~

DELETE có thể ghi undo và rollback; TRUNCATE là thao tác cấu trúc/segment với semantics khác.

## 4. DDL làm mất SAVEPOINT và giới hạn ROLLBACK

### 4.1 SAVEPOINT không tồn tại qua ranh giới DDL

Ví dụ:

~~~sql
INSERT INTO ddl_commit_demo (id, note)
VALUES (3, 'before savepoint');

SAVEPOINT before_ddl;

CREATE TABLE ddl_savepoint_demo (
    id NUMBER
);

ROLLBACK TO before_ddl;
~~~

ROLLBACK TO sẽ báo lỗi vì implicit commit trước DDL đã kết thúc transaction chứa SAVEPOINT đó. Các savepoint của transaction cũ không còn hiệu lực.

### 4.2 ROLLBACK không thể đi ngược qua DDL đã commit

Giả sử script:

~~~sql
INSERT INTO deployment_log (message)
VALUES ('start deployment');

ALTER TABLE customers ADD (segment_code VARCHAR2(20));

UPDATE customers
SET segment_code = 'STANDARD'
WHERE segment_code IS NULL;

ROLLBACK;
~~~

Sau khi script chạy đến ROLLBACK:

- INSERT vào DEPLOYMENT_LOG đã được commit trước ALTER TABLE.
- ALTER TABLE đã được commit khi thành công.
- UPDATE sau ALTER TABLE chưa được commit bởi DDL khác, nên ROLLBACK có thể hủy UPDATE.

Kết quả có thể là schema đã có cột SEGMENT_CODE, log bắt đầu triển khai đã được lưu, nhưng phần backfill bị rollback. Đây là trạng thái một phần cần được dự tính trong quy trình triển khai.

### 4.3 DDL không phải một phần của transaction DML có thể rollback

Không thiết kế theo mô hình:

~~~text
BEGIN TRANSACTION
    DML 1
    DDL 1
    DML 2
    DDL 2
    DML 3
ROLLBACK nếu có lỗi
~~~

Mô hình này không tồn tại theo cách một transaction ACID duy nhất bao trùm mọi DDL của Oracle. Mỗi DDL tạo ranh giới commit riêng.

## 5. So sánh DELETE, TRUNCATE và DROP

Ba lệnh có thể đều khiến dữ liệu hoặc bảng biến mất khỏi truy vấn thông thường, nhưng semantics khác nhau:

| Tiêu chí | DELETE | TRUNCATE | DROP TABLE |
|---|---|---|---|
| Nhóm lệnh | DML | DDL | DDL |
| Phạm vi | Có thể xóa một phần theo WHERE | Xóa toàn bộ dòng của bảng | Xóa đối tượng bảng |
| WHERE | Có | Không | Không |
| Có thể ROLLBACK trong transaction thông thường? | Có, trước COMMIT | Không | Không |
| Trigger DELETE | Có thể kích hoạt row/statement DELETE trigger theo định nghĩa | Không chạy DELETE trigger như DELETE | Không phải DELETE từng dòng |
| Cấu trúc bảng sau lệnh | Còn | Còn | Bị xóa |
| Implicit commit | Không tự commit như DDL | Có | Có |

Ví dụ DELETE một nhóm:

~~~sql
DELETE FROM orders
WHERE status = 'CANCELLED';
~~~

Có thể kiểm tra số dòng và rollback nếu chưa commit.

TRUNCATE:

~~~sql
TRUNCATE TABLE orders_stage;
~~~

Không thể lọc theo WHERE và không thể rollback như DELETE.

DROP:

~~~sql
DROP TABLE orders_stage;
~~~

Xóa đối tượng bảng. Cơ chế recycle bin hoặc flashback table có thể cung cấp đường phục hồi trong một số cấu hình, nhưng đó không phải ROLLBACK transaction thông thường và không nên thay thế kế hoạch backup/recovery.

## 6. DDL trong PL/SQL vẫn có implicit commit

### 6.1 DDL động với EXECUTE IMMEDIATE

PL/SQL không cho viết trực tiếp nhiều câu DDL tĩnh trong thân block như câu DML. Có thể chạy DDL động:

~~~sql
BEGIN
    EXECUTE IMMEDIATE
        'CREATE TABLE dynamic_ddl_demo (id NUMBER)';
END;
/
~~~

Việc bọc DDL trong BEGIN...END không biến nó thành DML và không loại bỏ implicit commit. DDL chạy qua EXECUTE IMMEDIATE vẫn có semantics commit của DDL.

### 6.2 Exception handler không thể rollback DML trước DDL

~~~sql
BEGIN
    INSERT INTO deployment_log (message)
    VALUES ('before dynamic DDL');

    EXECUTE IMMEDIATE
        'CREATE TABLE dynamic_table_demo (id NUMBER)';

    RAISE_APPLICATION_ERROR(-20001, 'Simulated failure');
EXCEPTION
    WHEN OTHERS THEN
        ROLLBACK;
        RAISE;
END;
/
~~~

INSERT vào DEPLOYMENT_LOG đã được commit trước khi EXECUTE IMMEDIATE thực thi CREATE TABLE. Nếu sau đó phát sinh lỗi và handler chạy ROLLBACK, INSERT đó vẫn không bị hủy. ROLLBACK chỉ áp dụng cho transaction hiện tại sau ranh giới DDL.

Đây là lý do không nên đặt DDL xen giữa các bước DML rồi dùng một exception handler với ROLLBACK như thể toàn bộ block là nguyên tử.

### 6.3 Bind variable và tên đối tượng trong DDL động

Trong dynamic SQL, bind variable có thể thay giá trị dữ liệu trong những vị trí được hỗ trợ, nhưng không thể thay tên bảng/cột như một identifier:

~~~sql
-- Không thể bind tên bảng theo cách này:
EXECUTE IMMEDIATE 'CREATE TABLE :table_name (id NUMBER)'
USING p_table_name;
~~~

Nếu tên đối tượng cần động, phải kiểm soát/whitelist identifier và quote đúng quy tắc Oracle, ví dụ dùng DBMS_ASSERT khi phù hợp. Không nối trực tiếp chuỗi tên bảng do người dùng gửi vào DDL vì có nguy cơ SQL injection và tạo sai đối tượng.

## 7. Tác động đến script triển khai

Một script triển khai thường kết hợp:

- Tạo hoặc sửa bảng, cột, constraint, index.
- Nạp hoặc chuyển đổi dữ liệu.
- Tạo view, procedure, trigger, sequence.
- Kiểm tra dữ liệu và ghi nhận phiên bản triển khai.

Nếu không nhận diện các ranh giới implicit commit, script có thể để lại trạng thái triển khai một phần sau khi lỗi.

### 7.1 Ví dụ script dễ gây hiểu lầm

~~~sql
UPDATE application_config
SET config_value = 'new'
WHERE config_key = 'FEATURE_X';

ALTER TABLE customers
ADD (new_code VARCHAR2(20));

UPDATE customers
SET new_code = 'DEFAULT'
WHERE new_code IS NULL;

-- Người viết nghĩ có thể rollback toàn bộ nếu bước kiểm tra thất bại:
ROLLBACK;
~~~

Thực tế:

1. UPDATE APPLICATION_CONFIG được commit trước ALTER TABLE.
2. ALTER TABLE được commit khi thành công.
3. UPDATE CUSTOMERS là DML sau DDL; nếu chưa có commit tiếp theo, ROLLBACK có thể hủy nó.

Script không thể quay lại trạng thái ban đầu chỉ bằng ROLLBACK.

### 7.2 Tách rõ các phase

Một quy trình triển khai dễ kiểm soát có thể chia thành:

~~~text
Preflight / kiểm tra điều kiện
          |
          v
DDL additive (tạo/thêm cấu trúc tương thích)
          |
          v
Backfill / chuyển đổi dữ liệu bằng DML
          |
          v
Validation / đối soát dữ liệu
          |
          v
Application switch / chuyển ứng dụng
          |
          v
DDL cleanup (xóa cấu trúc cũ khi đã an toàn)
~~~

Mỗi bước cần có điều kiện đầu vào, kết quả mong đợi và cách phục hồi riêng. Không giả định tất cả phase có thể rollback chung.

### 7.3 Thực hiện DDL trước nhóm DML cần rollback

Nếu có thể, hãy hoàn thành các DDL cần thiết trước khi bắt đầu một nhóm DML cần tính nguyên tử:

~~~sql
-- Phase 1: DDL; implicit commit là ranh giới rõ ràng.
ALTER TABLE customers
ADD (segment_code VARCHAR2(20));

-- Phase 2: bắt đầu nhóm DML.
UPDATE customers
SET segment_code = 'STANDARD'
WHERE segment_code IS NULL;

-- Kiểm tra:
SELECT COUNT(*)
FROM customers
WHERE segment_code IS NULL;

-- Chỉ commit khi kiểm tra đạt:
COMMIT;
~~~

Nếu backfill có lỗi trước COMMIT, có thể ROLLBACK nhóm DML. Cột đã thêm vẫn tồn tại và cần được xử lý theo kế hoạch triển khai.

### 7.4 Tránh DDL ở giữa transaction DML

Không nên:

~~~sql
UPDATE inventory
SET reserved_qty = reserved_qty + 5
WHERE product_id = 10;

CREATE INDEX idx_inventory_product
ON inventory(product_id);

UPDATE inventory
SET reserved_qty = reserved_qty + 3
WHERE product_id = 20;
~~~

CREATE INDEX commit UPDATE đầu tiên. Nếu UPDATE thứ hai thất bại và script rollback, UPDATE đầu tiên đã được commit. Nếu hai UPDATE cần cùng thành công hoặc cùng thất bại, hãy tách DDL ra trước hoặc sau transaction DML theo lịch triển khai.

## 8. Thiết kế migration có DDL và backfill

Một migration thay đổi schema thường có cả DDL lẫn DML. Cần thiết kế để ứng dụng hoạt động được trong các trạng thái chuyển tiếp.

### 8.1 Ví dụ: thêm cột mới

Yêu cầu: bảng CUSTOMERS có cột FULL_NAME cũ; ứng dụng mới muốn dùng DISPLAY_NAME.

Một cách triển khai theo nhiều giai đoạn:

**Giai đoạn A — Expand**

~~~sql
ALTER TABLE customers
ADD (display_name VARCHAR2(200));
~~~

Đây là DDL và có implicit commit. Cột mới được tạo; ứng dụng cũ vẫn có thể tiếp tục hoạt động nếu thay đổi tương thích.

**Giai đoạn B — Backfill**

~~~sql
UPDATE customers
SET display_name = full_name
WHERE display_name IS NULL;

COMMIT;
~~~

Với bảng lớn, backfill có thể chia batch, theo khóa tăng dần hoặc theo partition, ghi nhận checkpoint và commit theo lô. Phải tính đến ứng dụng đang ghi dữ liệu trong thời gian backfill.

**Giai đoạn C — Validate**

~~~sql
SELECT COUNT(*) AS missing_display_names
FROM customers
WHERE display_name IS NULL;
~~~

Kiểm tra số lượng, độ dài, dữ liệu bất thường và tính nhất quán với nguồn.

**Giai đoạn D — Switch**

Triển khai ứng dụng đọc/ghi DISPLAY_NAME theo chiến lược tương thích. Có thể cần dual-write trong một khoảng chuyển tiếp, tùy kiến trúc.

**Giai đoạn E — Contract**

Chỉ sau khi mọi ứng dụng không còn phụ thuộc FULL_NAME mới cân nhắc xóa cột cũ:

~~~sql
ALTER TABLE customers
DROP COLUMN full_name;
~~~

Đây là DDL riêng, có implicit commit và cần kế hoạch phục hồi/forward fix. Không gộp thao tác xóa cột vào cùng một transaction kỳ vọng có thể rollback nếu ứng dụng phát sinh lỗi.

### 8.2 Expand-and-contract giảm rủi ro

Mô hình expand-and-contract:

1. Mở rộng schema bằng thay đổi tương thích ngược (thêm cột/bảng mới).
2. Triển khai ứng dụng có thể đọc/ghi cấu trúc cũ và mới.
3. Backfill dữ liệu theo batch và kiểm tra.
4. Chuyển toàn bộ ứng dụng sang cấu trúc mới.
5. Xác nhận không còn dependency cũ.
6. Xóa cấu trúc cũ trong một migration riêng.

Các bước này tách thay đổi schema không thể rollback giao dịch khỏi thay đổi ứng dụng và dữ liệu. Đây không phải quy tắc bắt buộc cho mọi migration, nhưng hữu ích với hệ thống cần triển khai liên tục hoặc ít downtime.

## 9. Xử lý lỗi và phục hồi sau DDL

### 9.1 Không dùng ROLLBACK như cơ chế undo DDL

Nếu CREATE TABLE, ALTER TABLE hoặc DROP thành công, COMMIT/ROLLBACK sau đó không đưa schema trở lại trạng thái trước DDL.

Muốn đảo một thay đổi cấu trúc, cần một **compensating DDL** (lệnh DDL bù) hoặc phương án phục hồi được thiết kế trước:

- Thêm cột: có thể DROP COLUMN nếu an toàn và không có dependency.
- Đổi tên cột: có thể đổi tên ngược nếu ứng dụng chưa phụ thuộc.
- Tạo index: có thể DROP INDEX.
- Xóa cột hoặc bảng: không phải lúc nào cũng khôi phục được dữ liệu chỉ bằng DDL ngược; cần backup, recycle bin/flashback phù hợp hoặc bản sao dữ liệu.

DDL bù là một thao tác mới, có thể có implicit commit riêng. Nó không phải rollback của DDL trước.

### 9.2 DDL thành công rồi bước sau thất bại

Ví dụ:

~~~sql
ALTER TABLE orders
ADD (source_code VARCHAR2(30));

UPDATE orders
SET source_code = 'WEB'
WHERE channel = 'ONLINE';

-- Một bước kiểm tra sau đó phát hiện lỗi:
RAISE_APPLICATION_ERROR(-20010, 'Validation failed');
~~~

Cột SOURCE_CODE đã được tạo và commit. Nếu UPDATE chưa commit, nó có thể rollback khi xử lý lỗi; schema vẫn còn cột. Khi chạy lại script, CREATE/ALTER có thể lỗi vì cột đã tồn tại.

Vì vậy script migration cần có:

- Precondition rõ ràng.
- Kiểm tra trạng thái đối tượng trước khi thực hiện.
- Các bước có thể chạy lại an toàn khi phù hợp.
- Ghi nhận tiến độ migration.
- Hướng xử lý khi một phần đã thành công.

### 9.3 Idempotency của script

Một migration idempotent có thể chạy lại mà không tạo thêm tác dụng ngoài ý muốn, hoặc phát hiện trạng thái đã áp dụng và dừng an toàn.

Ví dụ, trước khi thêm cột, kiểm tra USER_TAB_COLUMNS theo TABLE_NAME và COLUMN_NAME đã chuẩn hóa:

~~~sql
SELECT COUNT(*)
FROM user_tab_columns
WHERE table_name = 'CUSTOMERS'
  AND column_name = 'SEGMENT_CODE';
~~~

Nếu đã có cột, script cần xác định:

- Cột đã được tạo bởi lần chạy trước và đúng định nghĩa?
- Hay đã tồn tại với kiểu/độ dài khác?
- Có thể tiếp tục backfill không?
- Có cần dừng để người vận hành xử lý drift?

Chỉ kiểm tra tên tồn tại là chưa đủ; cần xác nhận cấu trúc thực tế khớp với kỳ vọng.

### 9.4 Bảng lịch sử migration

Một bảng lịch sử có thể lưu version, thời điểm bắt đầu/kết thúc, checksum, trạng thái và người triển khai. Tuy nhiên, vì DDL có implicit commit, bản ghi migration và DDL không mặc nhiên nằm trong cùng một transaction nguyên tử.

Thiết kế runner phải tính đến tình huống:

1. DDL đã thành công và commit.
2. Tiến trình dừng trước khi ghi nhận migration hoàn tất.
3. Lần chạy tiếp theo phát hiện schema đã thay đổi nhưng history chưa đánh dấu.

Cần có quy tắc reconcile/repair rõ, thay vì tự động chạy lại toàn bộ DDL và giả định trạng thái ban đầu.

## 10. DDL và công cụ chạy script

### 10.1 SQL*Plus và SQLcl

SQL*Plus/SQLcl có các lệnh điều khiển script như:

~~~sql
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK
~~~

Lệnh này yêu cầu client thoát khi gặp SQL error và thực hiện hành vi ROLLBACK được chỉ định cho transaction hiện tại. Nó không thể hoàn tác DML đã được implicit commit trước một DDL.

Ví dụ:

~~~sql
WHENEVER SQLERROR EXIT SQL.SQLCODE ROLLBACK

UPDATE application_config
SET config_value = 'new'
WHERE config_key = 'FEATURE_X';

ALTER TABLE customers
ADD (segment_code VARCHAR2(20));

-- Nếu có lỗi ở đây, rollback không thể hủy UPDATE đã commit trước ALTER.
~~~

WHENEVER SQLERROR hữu ích để dừng script và trả mã lỗi, nhưng không biến DDL thành transactional DML.

### 10.2 SQL Developer và chế độ chạy script

SQL Developer có các cách thực thi câu lệnh và script khác nhau, cùng tùy chọn commit/autocommit tùy cấu hình. Dù client đang để chế độ manual commit, implicit commit của Oracle DDL vẫn được thực hiện ở server.

Không được dựa vào nút Rollback của client để hoàn tác DDL đã thành công. Nút đó chỉ có thể rollback transaction hiện tại còn chưa commit.

### 10.3 JDBC auto-commit

Ứng dụng Java có thể cấu hình:

~~~java
connection.setAutoCommit(false);
~~~

Điều này cho phép ứng dụng quản lý transaction DML bằng commit/rollback. Nhưng nó **không ngăn Oracle implicit commit khi chạy DDL**.

Ví dụ:

~~~java
connection.setAutoCommit(false);

try (Statement statement = connection.createStatement()) {
    statement.executeUpdate(
        "UPDATE application_config " +
        "SET config_value = 'new' " +
        "WHERE config_key = 'FEATURE_X'"
    );

    statement.execute(
        "ALTER TABLE customers ADD (segment_code VARCHAR2(20))"
    );

    connection.rollback();
}
~~~

UPDATE có thể đã được commit khi Oracle thực thi ALTER TABLE. Lệnh rollback sau đó không thể hoàn tác UPDATE đó. JDBC auto-commit false không thay đổi quy tắc transaction phía database.

Nếu autoCommit=true, driver thường commit DML theo quy tắc JDBC sau mỗi statement thành công, tạo thêm các ranh giới commit ở phía client. Đây là một hành vi khác với implicit commit do DDL. Khi viết migration, cần hiểu cả cấu hình driver lẫn semantics của Oracle.

### 10.4 Flyway, Liquibase và migration runner

Các công cụ migration có thể tổ chức migration theo transaction, ghi lịch sử và dừng khi lỗi. Nhưng không công cụ nào có thể biến một DDL Oracle có implicit commit thành câu lệnh có thể rollback như DML thông thường.

Khi dùng công cụ:

- Kiểm tra tài liệu về transaction handling của phiên bản công cụ và Oracle driver.
- Xác định migration nào chứa DDL và migration nào chỉ có DML.
- Không đặt kỳ vọng một migration chứa nhiều DDL/DML sẽ được rollback nguyên khối khi một bước giữa chừng thất bại.
- Thiết kế migration có thể kiểm tra và phục hồi từ trạng thái đã áp dụng một phần.
- Kiểm tra bảng history nếu script lỗi sau khi DDL đã commit.

Một số công cụ có cơ chế phát hiện DDL hoặc cấu hình migration không transactional; cách xử lý cụ thể phụ thuộc phiên bản và cấu hình, nên phải xác nhận theo tài liệu công cụ đang dùng.

## 11. Tác động đến khóa và session khác

### 11.1 Commit trước DDL giải phóng khóa transaction

DML chưa commit có thể đang giữ row lock. Khi Oracle thực hiện implicit commit trước DDL, các khóa transaction được giải phóng theo quy tắc commit.

Điều này có thể làm thay đổi thời điểm các session khác nhìn thấy dữ liệu đã commit hoặc tiếp tục cập nhật dòng.

### 11.2 DDL vẫn có thể cần khóa metadata

Sau implicit commit, DDL có thể cần khóa đối tượng hoặc metadata. Nếu session khác đang sử dụng đối tượng theo cách xung đột, DDL có thể phải chờ hoặc thất bại do lock timeout/điều kiện khóa.

Implicit commit không có nghĩa DDL luôn chạy ngay lập tức; nó chỉ xác định ranh giới transaction của session thực thi.

### 11.3 Không dùng DDL làm cách giải phóng khóa tùy tiện

Chạy một câu DDL để ép commit transaction có thể vô tình commit dữ liệu nghiệp vụ chưa được kiểm tra. Nếu cần giải phóng khóa, hãy quản lý transaction và COMMIT/ROLLBACK theo nghiệp vụ, không dùng DDL như một lệnh commit trá hình.

## 12. Các mẫu script triển khai nên tránh và nên dùng

### 12.1 Mẫu cần tránh: trộn DML chưa xác nhận với DDL

~~~sql
UPDATE invoices
SET status = 'READY'
WHERE invoice_date < DATE '2026-01-01';

CREATE INDEX idx_invoices_status
ON invoices(status);

-- Người vận hành thấy lỗi ở bước tiếp theo và chạy ROLLBACK:
ROLLBACK;
~~~

UPDATE đầu tiên đã bị commit trước CREATE INDEX. Nếu điều kiện UPDATE sai, rollback ở cuối không sửa được dữ liệu đã commit.

### 12.2 Mẫu rõ ràng hơn: tách DDL và DML

~~~sql
-- Phase A: thay đổi cấu trúc.
CREATE INDEX idx_invoices_status
ON invoices(status);

-- Phase B: thay đổi dữ liệu.
UPDATE invoices
SET status = 'READY'
WHERE invoice_date < DATE '2026-01-01';

-- Kiểm tra trước khi xác nhận dữ liệu:
SELECT COUNT(*)
FROM invoices
WHERE invoice_date < DATE '2026-01-01'
  AND status <> 'READY';

-- COMMIT khi đạt yêu cầu; ROLLBACK nếu chưa đạt.
~~~

DDL đã được commit trước khi bắt đầu nhóm DML. Nhóm DML có thể được rollback riêng nếu kiểm tra không đạt.

### 12.3 Mẫu triển khai theo checkpoint

~~~sql
-- 1. Preflight: kiểm tra object/column/index và dữ liệu hiện có.

-- 2. DDL additive: chạy riêng, kiểm tra thành công.
ALTER TABLE customers
ADD (segment_code VARCHAR2(20));

-- 3. Backfill: một transaction hoặc nhiều batch được kiểm soát.
UPDATE customers
SET segment_code = 'STANDARD'
WHERE segment_code IS NULL;

-- 4. Validate.
SELECT COUNT(*) AS rows_missing_segment
FROM customers
WHERE segment_code IS NULL;

-- 5. Chỉ COMMIT dữ liệu khi validation đạt.
COMMIT;

-- 6. DDL cleanup ở migration/release riêng sau khi không còn dependency.
~~~

Mỗi checkpoint cần được ghi nhận để người vận hành biết bước nào đã hoàn tất và bước nào cần tiếp tục hoặc phục hồi.

## 13. Thiết kế script có khả năng chạy lại

### 13.1 Kiểm tra trước khi CREATE

Trước khi tạo đối tượng, có thể kiểm tra dictionary view:

~~~sql
SELECT table_name
FROM user_tables
WHERE table_name = 'DEPLOYMENT_STAGE';
~~~

Nếu đối tượng đã tồn tại, không tự động bỏ qua mà không kiểm tra định nghĩa. Bảng cùng tên nhưng khác cột hoặc constraint có thể là schema drift.

### 13.2 Kiểm tra cột trước ALTER

~~~sql
SELECT column_name,
       data_type,
       data_length,
       nullable
FROM user_tab_columns
WHERE table_name = 'CUSTOMERS'
  AND column_name = 'SEGMENT_CODE';
~~~

Kiểm tra kiểu dữ liệu, độ dài và nullable để xác nhận trạng thái thực tế. Nếu đã tồn tại đúng cấu trúc, script có thể chuyển sang bước tiếp theo theo chính sách migration; nếu khác, dừng và yêu cầu xử lý drift.

### 13.3 Xử lý lỗi đối tượng đã tồn tại có kiểm soát

Có thể viết PL/SQL kiểm tra dictionary trước khi DDL hoặc bắt đúng mã lỗi theo đối tượng. Không nên dùng:

~~~sql
WHEN OTHERS THEN NULL;
~~~

để nuốt mọi lỗi. Nó có thể che giấu lỗi quyền, tablespace, cú pháp, khóa hoặc dependency. Nếu bắt ngoại lệ, chỉ xử lý đúng tình huống dự kiến và RAISE lại các lỗi khác.

Lưu ý: ngay cả khi DDL nằm trong EXECUTE IMMEDIATE và được bọc trong exception handler, implicit commit trước DDL vẫn có hiệu lực.

## 14. Bài lab: quan sát implicit commit

Phần lab nên chạy trong schema thực hành riêng có quyền tạo bảng. Không dùng bảng nghiệp vụ hoặc schema production. DDL trong lab vẫn commit transaction hiện tại, vì vậy hãy dùng dữ liệu thử nghiệm.

### 14.1 Tạo bảng

~~~sql
CREATE TABLE lab_ddl_txn (
    id   NUMBER PRIMARY KEY,
    note VARCHAR2(100)
);
~~~

### 14.2 Chèn DML nhưng chưa commit

~~~sql
INSERT INTO lab_ddl_txn (id, note)
VALUES (1, 'insert before create table');
~~~

Trong cùng session, có thể SELECT để thấy dòng ID=1. Session khác theo isolation mặc định chưa nhìn thấy thay đổi chưa commit.

### 14.3 Chạy DDL không liên quan

~~~sql
CREATE TABLE lab_ddl_marker (
    id NUMBER
);
~~~

Lệnh CREATE TABLE kích hoạt implicit commit. DML chèn ID=1 đã được commit.

### 14.4 Thử ROLLBACK

~~~sql
ROLLBACK;

SELECT *
FROM lab_ddl_txn
WHERE id = 1;
~~~

Dòng ID=1 vẫn tồn tại vì đã commit trước CREATE TABLE.

### 14.5 Thử DML sau DDL

~~~sql
INSERT INTO lab_ddl_txn (id, note)
VALUES (2, 'insert after create table');

ROLLBACK;

SELECT *
FROM lab_ddl_txn
ORDER BY id;
~~~

Dòng ID=2 bị rollback; dòng ID=1 vẫn tồn tại. Đây là minh họa cho transaction mới sau ranh giới DDL.

### 14.6 Thử SAVEPOINT

~~~sql
INSERT INTO lab_ddl_txn (id, note)
VALUES (3, 'before savepoint');

SAVEPOINT sp_before_ddl;

CREATE TABLE lab_ddl_savepoint_marker (
    id NUMBER
);

ROLLBACK TO sp_before_ddl;
~~~

ROLLBACK TO không thể quay về savepoint trước DDL vì transaction đã bị commit.

### 14.7 So sánh DELETE và TRUNCATE

Tạo lại dữ liệu nếu cần, sau đó:

~~~sql
DELETE FROM lab_ddl_txn
WHERE id = 1;

ROLLBACK;
~~~

Dòng ID=1 được khôi phục vì DELETE là DML và chưa commit.

Trong một bảng lab khác:

~~~sql
TRUNCATE TABLE lab_ddl_txn;

ROLLBACK;
~~~

TRUNCATE không thể được hoàn tác bằng ROLLBACK thông thường.

### 14.8 Dọn bảng lab

Chỉ xóa các bảng do bạn tạo trong schema lab sau khi đã xác nhận không còn cần dữ liệu:

~~~sql
DROP TABLE lab_ddl_savepoint_marker;
DROP TABLE lab_ddl_marker;
DROP TABLE lab_ddl_txn;
~~~

DROP TABLE cũng là DDL và có implicit commit. Không chạy các lệnh dọn này trên bảng không thuộc lab của bạn.

## 15. Checklist trước khi chạy script triển khai

Trước khi chạy script có DDL, hãy xác định:

1. Lệnh nào là DDL và lệnh nào là DML?
2. Có DML chưa commit nào đứng trước DDL không?
3. Nếu DDL lỗi, DML trước đó đã bị commit chưa?
4. SAVEPOINT nào sẽ bị mất khi DDL chạy?
5. Có đang trông chờ ROLLBACK hoàn tác CREATE, ALTER, DROP hoặc TRUNCATE không?
6. Script có tách phase schema change và data migration không?
7. Mỗi DDL có precondition, postcondition và cách phục hồi không?
8. Nếu script dừng giữa chừng, có thể xác định trạng thái đối tượng hiện tại không?
9. Có kiểm tra dictionary để phát hiện object đã tồn tại hoặc schema drift không?
10. DML backfill có thể chạy lại an toàn không? Có checkpoint/batch khi dữ liệu lớn không?
11. Migration history có xử lý trường hợp DDL đã commit nhưng bước ghi history chưa hoàn tất không?
12. Client/driver có auto-commit riêng không?
13. Exception handler hoặc lệnh WHENEVER SQLERROR có đang bị hiểu nhầm là rollback toàn bộ DDL không?
14. Các thao tác DROP/TRUNCATE có backup, xác nhận phạm vi và phương án phục hồi phù hợp không?
15. DDL có thể chờ khóa hoặc ảnh hưởng session đang dùng đối tượng không?

## 16. Tổng kết

Trong Oracle Database, DDL tạo ranh giới transaction bằng implicit commit:

- Oracle commit transaction hiện tại trước khi thực thi DDL.
- Khi DDL thành công, thay đổi cấu trúc cũng được commit.
- DML chưa commit trước DDL không thể được khôi phục bằng ROLLBACK sau đó, kể cả khi DDL thất bại.
- SAVEPOINT của transaction trước DDL không còn hiệu lực.
- DML sau DDL vẫn có thể COMMIT/ROLLBACK theo transaction mới cho đến khi gặp một ranh giới commit khác.
- TRUNCATE và DROP là DDL; DELETE là DML và có thể rollback trước COMMIT.
- DDL trong EXECUTE IMMEDIATE, stored procedure hoặc script client vẫn chịu semantics commit của Oracle.
- JDBC autoCommit=false, SQL Developer manual commit hoặc WHENEVER SQLERROR ROLLBACK không thể ngăn implicit commit phía database.

Khi triển khai, hãy tách thay đổi cấu trúc khỏi nhóm DML cần rollback, dùng checkpoint rõ ràng, kiểm tra trạng thái schema trước khi chạy lại, chuẩn bị forward-fix/compensating DDL và không coi toàn bộ migration chứa DDL là một transaction có thể rollback nguyên khối. Hiểu đúng implicit commit giúp tránh commit dữ liệu nghiệp vụ ngoài dự kiến và xây dựng quy trình triển khai có thể phục hồi khi lỗi xảy ra giữa chừng.
