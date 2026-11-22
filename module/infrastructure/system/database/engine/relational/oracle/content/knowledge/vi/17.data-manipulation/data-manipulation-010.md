# LOG ERRORS và tách dòng lỗi khi nạp dữ liệu

Khi nạp dữ liệu theo batch, một vài hàng lỗi không nhất thiết phải làm hỏng toàn bộ lô dữ liệu. Ví dụ, trong 100.000 sản phẩm từ hệ thống nguồn, có thể chỉ một số hàng vi phạm `NOT NULL`, `CHECK`, độ dài cột hoặc quy tắc dữ liệu. Nếu câu lệnh DML dừng ngay ở lỗi đầu tiên, người vận hành phải tìm và sửa từng hàng rồi chạy lại cả batch.

Oracle Database cung cấp **DML error logging** qua mệnh đề `LOG ERRORS`. Cơ chế này cho phép câu lệnh `INSERT`, `UPDATE`, `DELETE` hoặc `MERGE` ghi các lỗi ở cấp hàng vào một bảng log, trong khi tiếp tục xử lý những hàng khác trong giới hạn được cấu hình.

Hai thành phần thường dùng:

- `DBMS_ERRLOG.CREATE_ERROR_LOG`: tạo bảng ghi lỗi có cấu trúc phù hợp với bảng đích.
- `LOG ERRORS INTO ... REJECT LIMIT ...`: chỉ định bảng ghi lỗi, nhãn nhận diện lần chạy và số lỗi tối đa được chấp nhận.

`LOG ERRORS` giúp tách hàng bị từ chối khỏi các hàng được xử lý thành công. Nó không thay thế việc kiểm tra dữ liệu nguồn, không bắt được mọi lỗi của cả câu SQL và không tự sửa dữ liệu lỗi. Muốn nạp dữ liệu an toàn, cần phân biệt lỗi ở cấp hàng với lỗi khiến toàn bộ statement thất bại, theo dõi batch bằng tag và kiểm tra kết quả trước khi commit.

## 1. DML error logging hoạt động thế nào?

Một câu DML thông thường có thể dừng khi gặp lỗi ở một hàng. Khi thêm `LOG ERRORS`, Oracle có thể ghi thông tin lỗi vào error logging table rồi tiếp tục xử lý các hàng còn lại.

~~~text
                 SOURCE ROWS
                      |
                      v
                DML statement
                      |
          +-----------+-----------+
          |                       |
       Row succeeds            Row error
          |                       |
          v                       v
    Change target row       Write error details
                                  |
                                  v
                          Continue within reject limit
~~~

Ví dụ, khi `INSERT ... SELECT` đưa 1.000 hàng vào bảng đích:

- 990 hàng hợp lệ có thể được chèn.
- 10 hàng vi phạm ràng buộc có thể được ghi vào bảng error log.
- Câu lệnh tiếp tục khi số lỗi không vượt `REJECT LIMIT`.

Kết quả thực tế phụ thuộc loại lỗi và giới hạn của DML error logging. Những lỗi ở cấp statement, lỗi hạ tầng hoặc một số vi phạm unique constraint không được xử lý như lỗi hàng thông thường; chúng vẫn có thể làm câu lệnh thất bại.

## 2. Bảng error log được tạo bằng DBMS_ERRLOG

Oracle không tự tạo bảng log mỗi khi chạy `LOG ERRORS`. Trước tiên, cần tạo bảng bằng package `DBMS_ERRLOG`.

### 2.1. Cú pháp CREATE_ERROR_LOG

~~~sql
BEGIN
    DBMS_ERRLOG.CREATE_ERROR_LOG(
        dml_table_name      => 'TARGET_TABLE',
        err_log_table_name  => 'ERR$_TARGET_TABLE',
        err_log_table_owner => 'APP_SCHEMA',
        err_log_table_space => 'USERS',
        skip_unsupported    => TRUE
    );
END;
/
~~~

Các tham số thường gặp:

| Tham số | Ý nghĩa |
| --- | --- |
| `dml_table_name` | Tên bảng đích có DML cần ghi lỗi |
| `err_log_table_name` | Tên bảng log; nếu bỏ qua, Oracle tạo tên mặc định theo quy ước `ERR$_...` |
| `err_log_table_owner` | Schema sở hữu bảng log; mặc định theo ngữ cảnh gọi package |
| `err_log_table_space` | Tablespace dùng cho bảng log nếu cần chỉ định |
| `skip_unsupported` | Cho phép bỏ qua các cột có kiểu dữ liệu không được hỗ trợ trong error log table |

Tên bảng truyền vào package thường được viết theo tên đối tượng trong data dictionary, tức chữ hoa nếu bảng được tạo không dùng quoted identifier. Nếu bảng được tạo với tên có phân biệt chữ hoa/thường bằng dấu ngoặc kép, cần tuân theo đúng quy tắc định danh đó.

Người thực hiện cần quyền tạo bảng trong schema đích và quyền thực thi `DBMS_ERRLOG`. Trong môi trường được quản trị tập trung, DBA có thể tạo sẵn error log table và cấp quyền cần thiết cho tài khoản chạy batch.

### 2.2. Các cột hệ thống trong error log table

Oracle tạo một số cột kỹ thuật:

| Cột | Ý nghĩa |
| --- | --- |
| `ORA_ERR_NUMBER$` | Mã lỗi Oracle |
| `ORA_ERR_MESG$` | Thông báo lỗi |
| `ORA_ERR_ROWID$` | ROWID của hàng đích liên quan nếu có |
| `ORA_ERR_OPTYP$` | Loại thao tác DML gây lỗi |
| `ORA_ERR_TAG$` | Tag do câu DML cung cấp |

Ngoài các cột hệ thống, bảng log có các cột tương ứng với những cột được hỗ trợ của bảng đích. Nhờ đó, người vận hành có thể xem giá trị hàng gây lỗi cùng thông tin ORA error.

`ORA_ERR_ROWID$` có thể NULL, đặc biệt với lỗi khi INSERT vì hàng chưa được tạo thành hàng đích. Không dùng cột này làm khóa truy vết duy nhất cho mọi loại DML.

### 2.3. Cột có kiểu dữ liệu không hỗ trợ

Một số kiểu dữ liệu của bảng đích không thể được biểu diễn trong error logging table theo cách thông thường, chẳng hạn các kiểu LOB, `LONG`, kiểu đối tượng hoặc collection. Nếu không bỏ qua các cột không hỗ trợ, việc tạo bảng log có thể thất bại.

`skip_unsupported => TRUE` cho phép tạo bảng log mà bỏ qua các cột không hỗ trợ. Khi đó, giá trị của những cột bị bỏ qua không có trong error log table. Nếu cần truy vết các cột đó, phải thiết kế thêm cơ chế lưu dữ liệu nguồn hoặc bảng quarantine phù hợp.

Tạo bảng log **một lần** cho bảng đích và tái sử dụng qua các batch. Không cần gọi `CREATE_ERROR_LOG` mỗi lần nạp.

## 3. Dữ liệu lab: bảng đích và bảng staging

Ta nạp dữ liệu danh mục hàng hóa từ staging vào bảng tồn kho. Dữ liệu staging cho phép lưu giá trị dài hơn và có NULL để mô phỏng dữ liệu chưa được chuẩn hóa. Bảng đích có ràng buộc chặt hơn.

Chạy các lệnh trong schema thực hành do bạn sở hữu, có quyền `CREATE TABLE` và quota tablespace.

### 3.1. Tạo bảng đích

~~~sql
CREATE TABLE lab_inventory (
    item_id       NUMBER PRIMARY KEY,
    item_name     VARCHAR2(40 CHAR) NOT NULL,
    category_code VARCHAR2(10 CHAR) NOT NULL,
    unit_price    NUMBER(9, 2) NOT NULL,
    CONSTRAINT ck_lab_inventory_price
        CHECK (unit_price >= 0)
);
~~~

Các quy tắc của bảng đích:

- `ITEM_ID` phải duy nhất.
- `ITEM_NAME`, `CATEGORY_CODE` và `UNIT_PRICE` không được NULL.
- `UNIT_PRICE` không được âm.
- Tên hàng tối đa 40 ký tự; mã nhóm tối đa 10 ký tự.

### 3.2. Tạo bảng staging

~~~sql
CREATE TABLE lab_inventory_stage (
    stage_row_id  NUMBER PRIMARY KEY,
    batch_id      NUMBER NOT NULL,
    item_id       NUMBER NOT NULL,
    item_name     VARCHAR2(100 CHAR),
    category_code VARCHAR2(20 CHAR),
    unit_price    NUMBER(12, 2)
);
~~~

`STAGE_ROW_ID` là khóa định danh của hàng nhận từ nguồn. Bảng staging rộng và ít ràng buộc hơn để giữ được dữ liệu cần kiểm tra. Bảng đích mới là nơi áp dụng quy tắc dữ liệu chính thức.

### 3.3. Tạo error log table

~~~sql
BEGIN
    DBMS_ERRLOG.CREATE_ERROR_LOG(
        dml_table_name     => 'LAB_INVENTORY',
        err_log_table_name => 'ERR$_LAB_INVENTORY',
        skip_unsupported   => TRUE
    );
END;
/
~~~

Sau khi chạy thành công, schema có bảng `ERR$_LAB_INVENTORY`. Có thể xem cấu trúc:

~~~sql
DESC err$_lab_inventory;
~~~

Không tự tạo bảng log bằng cách đoán danh sách cột hệ thống. Dùng package để Oracle tạo đúng cấu trúc tương ứng với bảng đích.

### 3.4. Nạp dữ liệu nguồn của batch 100

~~~sql
INSERT INTO lab_inventory_stage VALUES
    (1001, 100, 101, 'USB Hub', 'ACCESSORY', 25.00);

INSERT INTO lab_inventory_stage VALUES
    (1002, 100, 102, 'Monitor', 'DISPLAY', 220.00);

INSERT INTO lab_inventory_stage VALUES
    (1003, 100, 103, NULL, 'AUDIO', 30.00);

INSERT INTO lab_inventory_stage VALUES
    (1004, 100, 104, 'Cable', 'ACCESSORY', -2.00);

INSERT INTO lab_inventory_stage VALUES
    (1005, 100, 105, 'Keyboard', NULL, 45.00);

INSERT INTO lab_inventory_stage VALUES
    (1006, 100, 106,
     'This product name is longer than forty characters',
     'ACCESSORY', 10.00);

INSERT INTO lab_inventory_stage VALUES
    (1007, 100, 107, 'Speaker', 'VERY_LONG_CATEGORY', 20.00);

COMMIT;
~~~

Batch có hai hàng hợp lệ và năm hàng vi phạm quy tắc đích:

| STAGE_ROW_ID | ITEM_ID | Vấn đề |
| ---: | ---: | --- |
| 1001 | 101 | Hợp lệ |
| 1002 | 102 | Hợp lệ |
| 1003 | 103 | `ITEM_NAME` NULL |
| 1004 | 104 | `UNIT_PRICE` âm |
| 1005 | 105 | `CATEGORY_CODE` NULL |
| 1006 | 106 | Tên vượt quá 40 ký tự |
| 1007 | 107 | Mã nhóm vượt quá 10 ký tự |

## 4. INSERT ... SELECT với LOG ERRORS

Đây là mẫu thường dùng khi nạp batch từ staging:

~~~sql
INSERT INTO lab_inventory (
    item_id,
    item_name,
    category_code,
    unit_price
)
SELECT
    item_id,
    item_name,
    category_code,
    unit_price
FROM lab_inventory_stage
WHERE batch_id = 100
LOG ERRORS INTO err$_lab_inventory ('LOAD_100')
REJECT LIMIT UNLIMITED;
~~~

Giải thích:

- `INSERT INTO` chỉ rõ các cột của target.
- `SELECT` lấy dữ liệu thuộc batch 100.
- `LOG ERRORS INTO err$_lab_inventory` chỉ định bảng ghi lỗi.
- `'LOAD_100'` là tag để nhận diện lần chạy.
- `REJECT LIMIT UNLIMITED` cho phép tiếp tục ghi nhận mọi lỗi hàng thuộc phạm vi DML error logging hỗ trợ.

Với dữ liệu lab, hai hàng 101 và 102 được chèn; các hàng còn lại được ghi vào error log do vi phạm `NOT NULL`, `CHECK` hoặc giới hạn độ dài cột.

`UNLIMITED` không có nghĩa statement có thể bỏ qua mọi lỗi. Nó chỉ bỏ giới hạn số lỗi hàng được chấp nhận. Lỗi ở cấp statement, lỗi không được DML error logging hỗ trợ hoặc lỗi tài nguyên vẫn có thể làm câu lệnh thất bại.

## 5. Xem các hàng bị từ chối

### 5.1. Đọc lỗi theo tag

~~~sql
SELECT
    ora_err_number$ AS error_number,
    ora_err_mesg$   AS error_message,
    ora_err_optyp$  AS operation_type,
    ora_err_tag$    AS batch_tag,
    ora_err_rowid$  AS target_rowid,
    item_id,
    item_name,
    category_code,
    unit_price
FROM err$_lab_inventory
WHERE ora_err_tag$ = 'LOAD_100'
ORDER BY item_id;
~~~

Các thông tin cần xem:

- **Error number/message** cho biết loại vi phạm và nguyên nhân Oracle báo.
- **Operation type** giúp nhận biết lỗi phát sinh từ INSERT, UPDATE, DELETE hoặc MERGE.
- **Tag** phân biệt các batch/lần chạy.
- Các cột nghiệp vụ giúp nhận diện hàng nguồn đã gây lỗi.

Không nên phụ thuộc vào chuỗi thông báo lỗi để điều khiển logic nghiệp vụ. Thông báo có thể thay đổi theo phiên bản, ngôn ngữ hoặc ngữ cảnh; hãy dùng mã lỗi và quy tắc xử lý đã được định nghĩa, đồng thời giữ lại thông tin cần điều tra.

### 5.2. Đếm số hàng thành công và số hàng lỗi

~~~sql
SELECT COUNT(*) AS rejected_rows
FROM err$_lab_inventory
WHERE ora_err_tag$ = 'LOAD_100';
~~~

Số hàng nguồn thuộc batch:

~~~sql
SELECT COUNT(*) AS source_rows
FROM lab_inventory_stage
WHERE batch_id = 100;
~~~

Số hàng hiện có trong target:

~~~sql
SELECT COUNT(*) AS target_rows
FROM lab_inventory;
~~~

Trong lab ban đầu, target rỗng; sau batch 100 dự kiến có hai hàng hợp lệ và năm lỗi. Trong quy trình thực tế, không lấy `COUNT(*)` của target làm số hàng thành công của riêng batch nếu target đã có dữ liệu từ trước. Cần ghi nhận số hàng nguồn, số hàng lỗi theo tag và số hàng DML xử lý của statement (chẳng hạn `SQL%ROWCOUNT` trong PL/SQL) theo đúng ngữ cảnh.

### 5.3. Truy vết ngược về staging

Error log table được tạo dựa trên **cấu trúc target**, không tự động sao chép mọi cột riêng có trong source. Trong lab, `STAGE_ROW_ID` không phải cột của `LAB_INVENTORY`, nên nó không tự xuất hiện trong `ERR$_LAB_INVENTORY`.

Có thể tìm hàng staging bằng khóa nghiệp vụ nếu khóa đó đủ để xác định một hàng:

~~~sql
SELECT
    s.stage_row_id,
    s.batch_id,
    s.item_id,
    s.item_name,
    s.category_code,
    s.unit_price
FROM lab_inventory_stage s
JOIN err$_lab_inventory e
  ON e.item_id = s.item_id
WHERE s.batch_id = 100
  AND e.ora_err_tag$ = 'LOAD_100'
ORDER BY s.stage_row_id;
~~~

Nếu source có thể chứa nhiều hàng cùng `ITEM_ID`, phép join trên không đủ để xác định chính xác hàng gây lỗi. Khi cần truy vết tuyệt đối, hãy thiết kế khóa tương quan duy nhất được lưu cùng dữ liệu đích/log hoặc duy trì một bảng quarantine/validation chứa `STAGE_ROW_ID`, batch và payload gốc. Đừng giả định DML error log tự giữ mọi cột staging.

## 6. Tag giúp tách các lần nạp

Tag là biểu thức đơn giản truyền vào `LOG ERRORS`. Dùng tag để phân biệt batch, bước ETL hoặc loại thao tác:

~~~sql
LOG ERRORS INTO err$_lab_inventory ('BATCH_2026_001')
REJECT LIMIT UNLIMITED
~~~

Ví dụ quy ước:

| Tag | Ý nghĩa |
| --- | --- |
| `LOAD_100` | Nạp batch 100 |
| `PRICE_UPDATE_100` | Cập nhật giá trong batch 100 |
| `MERGE_200` | Đồng bộ MERGE batch 200 |
| `REPAIR_2026_01` | Chạy sửa dữ liệu có kiểm soát |

Không tái sử dụng tag một cách mơ hồ nếu cần điều tra lịch sử. Tag nên đủ thông tin để liên kết với batch/run ID của hệ thống ETL, nhưng tránh nhét dữ liệu nhạy cảm vào tag.

Truy vấn lỗi có thể lọc theo tag:

~~~sql
SELECT
    ora_err_tag$,
    ora_err_number$,
    COUNT(*) AS error_rows
FROM err$_lab_inventory
GROUP BY ora_err_tag$, ora_err_number$
ORDER BY ora_err_tag$, ora_err_number$;
~~~

Error log table là dữ liệu vận hành lâu dài; cần có chính sách retention, phân quyền truy cập, lưu trữ và dọn dẹp theo batch. Không truncate bảng log ngay sau khi chạy nếu chưa lưu hoặc xử lý các hàng lỗi cần điều tra.

## 7. REJECT LIMIT: giới hạn số lỗi được chấp nhận

Cú pháp:

~~~sql
LOG ERRORS INTO error_table ('tag')
REJECT LIMIT integer
~~~

Hoặc:

~~~sql
LOG ERRORS INTO error_table ('tag')
REJECT LIMIT UNLIMITED
~~~

| Cấu hình | Ý nghĩa |
| --- | --- |
| `REJECT LIMIT 0` | Không chấp nhận lỗi hàng; đây là mức mặc định khi không chỉ định reject limit |
| `REJECT LIMIT 5` | Cho phép tối đa 5 lỗi hàng trước khi statement vượt ngưỡng |
| `REJECT LIMIT 100` | Cho phép tối đa 100 lỗi hàng |
| `REJECT LIMIT UNLIMITED` | Không đặt ngưỡng số lỗi hàng |

Ví dụ:

~~~sql
INSERT INTO lab_inventory (item_id, item_name, category_code, unit_price)
SELECT item_id, item_name, category_code, unit_price
FROM lab_inventory_stage
WHERE batch_id = 100
LOG ERRORS INTO err$_lab_inventory ('LOAD_LIMIT_5')
REJECT LIMIT 5;
~~~

Nếu số lỗi vượt giới hạn, statement kết thúc với lỗi thay vì tiếp tục như khi dùng `UNLIMITED`. Hãy coi trường hợp đó là một lần nạp thất bại cần được điều tra và xử lý transaction theo quy trình. Không giả định rằng statement đã hoàn tất một phần theo cách ứng dụng mong muốn.

Đặt `UNLIMITED` phù hợp với batch cần thu thập mọi lỗi hàng có thể ghi nhận, nhưng không thay thế cảnh báo khi tỷ lệ lỗi cao. Một batch có 90% hàng lỗi vẫn có thể hoàn tất về mặt cú pháp; quy trình ETL cần tự đặt ngưỡng chất lượng dữ liệu và quyết định có chấp nhận kết quả hay không.

## 8. LOG ERRORS với UPDATE

DML error logging không chỉ dành cho INSERT. Có thể dùng với UPDATE khi thao tác cập nhật một số hàng có thể vi phạm ràng buộc.

Ví dụ minh họa: tăng giá 10% nhưng một số giá trị sau cập nhật có thể vi phạm quy tắc đích:

~~~sql
UPDATE lab_inventory
SET unit_price = unit_price * 1.10
WHERE category_code = 'ACCESSORY'
LOG ERRORS INTO err$_lab_inventory ('PRICE_UP_10')
REJECT LIMIT UNLIMITED;
~~~

Trong lab hiện tại, dữ liệu hợp lệ và phép tăng giá này không tạo giá âm, nên ví dụ chủ yếu minh họa cú pháp. Với hệ thống thật, các lỗi có thể phát sinh khi cập nhật cột có ràng buộc, khóa ngoại hoặc giới hạn dữ liệu. Error log ghi hàng lỗi trong phạm vi Oracle hỗ trợ; các vi phạm unique constraint trong UPDATE có những hạn chế riêng và không nên giả định đều được ghi nhận.

Có thể xem lỗi UPDATE theo tag:

~~~sql
SELECT
    ora_err_number$,
    ora_err_mesg$,
    ora_err_optyp$,
    item_id,
    item_name,
    unit_price
FROM err$_lab_inventory
WHERE ora_err_tag$ = 'PRICE_UP_10';
~~~

## 9. LOG ERRORS với MERGE

`MERGE` cũng hỗ trợ error logging. Đây là trường hợp hữu ích khi đồng bộ dữ liệu: một số hàng nguồn có thể cập nhật/chèn thành công, trong khi hàng khác vi phạm ràng buộc target.

### 9.1. Nạp batch 200

Thêm hai hàng:

~~~sql
INSERT INTO lab_inventory_stage VALUES
    (2001, 200, 101, 'USB Hub Pro', 'ACCESSORY', -5.00);

INSERT INTO lab_inventory_stage VALUES
    (2002, 200, 103, 'Headset', 'AUDIO', 55.00);

COMMIT;
~~~

ID 101 đã tồn tại sau batch 100. Hàng mới có giá âm, nên vi phạm CHECK khi UPDATE. ID 103 chưa tồn tại và có dữ liệu hợp lệ, nên có thể được INSERT.

### 9.2. MERGE có LOG ERRORS

~~~sql
MERGE INTO lab_inventory t
USING (
    SELECT
        item_id,
        item_name,
        category_code,
        unit_price
    FROM lab_inventory_stage
    WHERE batch_id = 200
) s
ON (t.item_id = s.item_id)
WHEN MATCHED THEN
    UPDATE SET
        t.item_name = s.item_name,
        t.category_code = s.category_code,
        t.unit_price = s.unit_price
WHEN NOT MATCHED THEN
    INSERT (
        item_id,
        item_name,
        category_code,
        unit_price
    )
    VALUES (
        s.item_id,
        s.item_name,
        s.category_code,
        s.unit_price
    )
LOG ERRORS INTO err$_lab_inventory ('MERGE_200')
REJECT LIMIT UNLIMITED;
~~~

Kết quả mong muốn trong lab:

- Hàng 101 đi vào nhánh MATCHED nhưng UPDATE thất bại vì `UNIT_PRICE` âm; lỗi được ghi nếu thuộc nhóm lỗi hàng Oracle hỗ trợ.
- Hàng 103 đi vào nhánh NOT MATCHED và được INSERT.

Kiểm tra:

~~~sql
SELECT
    ora_err_number$,
    ora_err_mesg$,
    ora_err_optyp$,
    ora_err_tag$,
    item_id,
    unit_price
FROM err$_lab_inventory
WHERE ora_err_tag$ = 'MERGE_200';

SELECT item_id, item_name, category_code, unit_price
FROM lab_inventory
ORDER BY item_id;
~~~

`LOG ERRORS` không sửa logic khớp của MERGE. Điều kiện `ON` vẫn quyết định hàng nguồn là MATCHED hay NOT MATCHED; các nhánh UPDATE/INSERT vẫn thực hiện như đã khai báo. Error logging chỉ xử lý những lỗi hàng được hỗ trợ phát sinh trong quá trình DML.

### 9.3. Nguồn trùng khóa vẫn phải xử lý trước

Nếu source có nhiều hàng cùng khớp một hàng target, `MERGE` có thể gặp `ORA-30926`. DML error logging không phải cách deduplicate source và không thay thế việc tạo một tập nguồn xác định.

Kiểm tra trùng:

~~~sql
SELECT item_id, COUNT(*) AS source_rows
FROM lab_inventory_stage
WHERE batch_id = :batch_id
GROUP BY item_id
HAVING COUNT(*) > 1;
~~~

Nếu cần chọn phiên bản mới nhất, dùng `ROW_NUMBER()` với tie-breaker ổn định trong source subquery trước khi MERGE. Nếu nhiều hàng nguồn là các giao dịch cần cộng dồn, aggregate chúng theo khóa đích trước khi MERGE.

## 10. LOG ERRORS với DELETE

DELETE cũng có thể dùng error logging:

~~~sql
DELETE FROM lab_inventory t
WHERE t.category_code = 'OBSOLETE'
LOG ERRORS INTO err$_lab_inventory ('DELETE_OLD')
REJECT LIMIT UNLIMITED;
~~~

Nếu một hàng không thể xóa do ràng buộc tham chiếu hoặc một lỗi hàng được hỗ trợ, Oracle có thể ghi lỗi tương ứng. Tuy nhiên, lỗi do ràng buộc trì hoãn, lỗi statement hoặc các trường hợp nằm ngoài phạm vi DML error logging vẫn có thể làm câu lệnh thất bại.

Không dùng ví dụ DELETE trên bảng nghiệp vụ chỉ để thử error logging. Hãy tạo dữ liệu lab riêng và kiểm tra quan hệ khóa ngoại trước khi thực hành.

## 11. Tách dữ liệu lỗi khỏi luồng nạp chính

Error log table là nơi lưu **thông tin lỗi DML**. Để xử lý vận hành, thường cần phân loại hàng lỗi thành các nhóm:

1. **Có thể sửa tự động:** ví dụ chuẩn hóa khoảng trắng hoặc ánh xạ mã nhóm theo bảng tham chiếu.
2. **Cần người phụ trách nguồn sửa:** ví dụ thiếu mã định danh, thiếu tên bắt buộc hoặc giá trị nghiệp vụ không hợp lệ.
3. **Không thể nạp theo chính sách:** ví dụ bản ghi bị từ chối vĩnh viễn hoặc không còn hợp lệ.

Một quy trình phổ biến:

~~~text
Receive source batch
        |
        v
Load into staging (preserve raw values)
        |
        v
Validate and normalize
        |
        v
INSERT / MERGE ... LOG ERRORS
        |
        +----------------------+
        |                      |
        v                      v
Rows accepted             Rows in ERR$_ table
        |                      |
        v                      v
Reconcile counts          Classify by error
        |                      |
        v                      v
Commit/release batch      Repair, quarantine, or reject
~~~

Không nên xóa hàng lỗi khỏi staging ngay sau khi ghi vào error log nếu chưa có bản lưu đủ để sửa và nạp lại. Error log có thể không chứa mọi cột riêng của source, nên staging thường là nguồn truy vết quan trọng.

### 11.1. Tạo danh sách lỗi theo loại

~~~sql
SELECT
    ora_err_number$ AS error_number,
    COUNT(*) AS error_count
FROM err$_lab_inventory
WHERE ora_err_tag$ = 'LOAD_100'
GROUP BY ora_err_number$
ORDER BY error_count DESC, error_number;
~~~

Có thể phân loại theo mã lỗi, nhưng ánh xạ mã sang hành động cần được quản lý trong ứng dụng/ETL. Không phân loại chỉ bằng cách tìm một từ khóa trong thông báo lỗi.

### 11.2. Bảng quarantine riêng

Nếu cần giữ nguyên payload nguồn và trạng thái xử lý, có thể thiết kế bảng quarantine:

~~~sql
CREATE TABLE lab_inventory_quarantine (
    stage_row_id      NUMBER PRIMARY KEY,
    batch_id          NUMBER NOT NULL,
    error_code        NUMBER,
    error_message     VARCHAR2(2000),
    received_at       TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    resolved_at       TIMESTAMP,
    resolution_status VARCHAR2(20) DEFAULT 'PENDING' NOT NULL
);
~~~

Bảng quarantine có thể tham chiếu staging bằng `STAGE_ROW_ID`, giúp quy trình sửa dữ liệu không phụ thuộc vào việc error log table có giữ tất cả cột nguồn hay không. Khi tạo quy trình thật, cần định nghĩa khóa ngoại, chính sách retention và quyền truy cập phù hợp.

## 12. Lỗi nào được ghi và lỗi nào có thể làm cả statement thất bại?

`LOG ERRORS` được thiết kế để xử lý **row errors** trong DML. Không phải mọi lỗi Oracle đều có thể được chuyển thành một dòng trong error log.

### 12.1. Ví dụ lỗi ở cấp hàng

Các lỗi do giá trị của một hàng vi phạm quy tắc target có thể được ghi, tùy loại thao tác và các hạn chế Oracle:

- Vi phạm `NOT NULL`.
- Vi phạm `CHECK` constraint.
- Giá trị chuỗi vượt độ dài cột (`ORA-12899`).
- Một số lỗi chuyển đổi/giá trị cột phát sinh trong quá trình áp dụng DML.
- Một số vi phạm khóa hoặc ràng buộc khác thuộc nhóm Oracle hỗ trợ.

Ví dụ:

~~~sql
INSERT INTO lab_inventory (item_id, item_name, category_code, unit_price)
VALUES (999, NULL, 'MISC', 10)
LOG ERRORS INTO err$_lab_inventory ('ONE_ROW_TEST')
REJECT LIMIT UNLIMITED;
~~~

Hàng này vi phạm `ITEM_NAME NOT NULL`; nếu lỗi được xử lý bởi DML error logging, nó được ghi vào error table thay vì làm dừng toàn bộ batch.

### 12.2. Ví dụ lỗi ở cấp statement hoặc ngoài phạm vi

Các lỗi sau không nên được kỳ vọng là sẽ ghi thành một hàng error log:

- Lỗi cú pháp SQL hoặc tên bảng/cột không tồn tại.
- Thiếu quyền truy cập đối tượng.
- Source query không thể thực thi, chẳng hạn tham chiếu bảng không tồn tại hoặc subquery trả kết quả không hợp lệ.
- Lỗi tài nguyên như hết tablespace hoặc lỗi hệ thống.
- Vi phạm constraint được khai báo `DEFERRABLE` và chỉ được kiểm tra ở thời điểm commit.
- Một số lỗi vi phạm unique constraint/index trong UPDATE/MERGE hoặc direct-path INSERT/MERGE theo các hạn chế của Oracle.
- Lỗi khiến toàn bộ DML không thể tiếp tục theo quy tắc engine.

Đặc biệt, đừng dựa vào `LOG ERRORS` để thay thế xử lý `ORA-00001` trong mọi tình huống. Oracle có những trường hợp unique constraint/index violation không được ghi theo cơ chế này; hãy kiểm tra đúng loại DML và đường thực thi của phiên bản đang dùng.

### 12.3. Lỗi trong biểu thức của source query

Phân biệt lỗi khi áp dụng một hàng vào target với lỗi xảy ra khi Oracle phải tính source query. Ví dụ, nếu source query gọi `TO_NUMBER(raw_price)` và một giá trị không thể chuyển thành số làm biểu thức phát sinh lỗi, statement có thể thất bại trước khi hàng đi đến bước ghi target/error log.

Với dữ liệu nguồn thô, hãy kiểm tra trước:

~~~sql
SELECT stage_row_id, raw_price
FROM lab_inventory_raw_stage
WHERE raw_price IS NOT NULL
  AND VALIDATE_CONVERSION(raw_price AS NUMBER) = 0;
~~~

`VALIDATE_CONVERSION` có từ Oracle 12.2. Nó giúp phát hiện giá trị không chuyển được sang kiểu đích trước khi chạy DML. Với release cũ hơn, có thể dùng quy tắc kiểm tra phù hợp hoặc PL/SQL xử lý từng hàng; đừng giả định hàm này có sẵn trên mọi phiên bản.

Một phương án là tách hàng hợp lệ và không hợp lệ ngay ở staging:

~~~sql
-- Hàng có thể chuyển đổi.
SELECT stage_row_id, TO_NUMBER(raw_price) AS unit_price
FROM lab_inventory_raw_stage
WHERE raw_price IS NOT NULL
  AND VALIDATE_CONVERSION(raw_price AS NUMBER) = 1;

-- Hàng cần kiểm tra/sửa.
SELECT stage_row_id, raw_price
FROM lab_inventory_raw_stage
WHERE raw_price IS NOT NULL
  AND VALIDATE_CONVERSION(raw_price AS NUMBER) = 0;
~~~

Hãy giữ giá trị gốc trong staging để có thể giải thích và sửa dữ liệu, thay vì ghi đè giá trị nguồn bằng một giá trị mặc định mà không lưu dấu vết.

## 13. REJECT LIMIT và transaction

DML error logging không phải cơ chế commit từng hàng độc lập. Target changes vẫn thuộc transaction của câu lệnh và transaction do ứng dụng/session quản lý.

Quy trình nên:

1. Chạy DML với tag duy nhất cho batch.
2. Lấy số hàng bị lỗi theo tag và số hàng nguồn.
3. Kiểm tra trạng thái target và error log.
4. Quyết định commit hay rollback theo tiêu chí chất lượng dữ liệu.
5. Lưu batch/run status và chỉ đánh dấu hoàn tất sau khi transaction được xử lý.

Nếu statement vượt `REJECT LIMIT`, statement kết thúc với lỗi. Khi đó không được coi kết quả là một batch hoàn tất thành công. Hãy xử lý lỗi statement và transaction theo đúng quy trình; không dựa vào giả định rằng chỉ các hàng thành công trước thời điểm vượt ngưỡng sẽ được commit.

Trong quy trình nhiều bước, tránh commit quá sớm giữa bước nạp target và bước lưu trạng thái batch. Nếu commit target trước nhưng chưa ghi nhận batch đã hoàn thành, lần chạy lại có thể khó xác định phần việc nào đã được xử lý.

## 14. Quản lý error log table

Error log table có thể tích lũy dữ liệu qua nhiều batch. Cần quản lý nó như một bảng vận hành:

- Đặt tag có quy ước và liên kết được với run/batch ID.
- Chỉ cấp quyền đọc cho vai trò cần điều tra lỗi; dữ liệu log có thể chứa thông tin cá nhân hoặc dữ liệu nhạy cảm.
- Xác định thời gian lưu giữ theo yêu cầu audit và vận hành.
- Lưu/archive các lỗi cần xử lý trước khi dọn.
- Theo dõi dung lượng và index nếu bảng log lớn.
- Không tạo lại bảng log mỗi lần chạy; việc tạo lại có thể làm mất lịch sử.

Ví dụ dọn dữ liệu cũ sau khi đã archive và được phép xóa:

~~~sql
DELETE FROM err$_lab_inventory
WHERE ora_err_tag$ = 'LOAD_100';
~~~

Chỉ chạy lệnh dọn theo chính sách retention. Trong hệ thống thật, nên xóa theo thời gian hoặc batch đã hoàn tất xử lý thay vì xóa theo một tag dùng chung.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `LOG ERRORS` báo không tìm thấy error table | Chưa tạo bảng hoặc sai schema/tên | Dùng `DBMS_ERRLOG.CREATE_ERROR_LOG` và kiểm tra owner |
| Không thấy hàng lỗi sau DML | Tag truy vấn không khớp, DML không có lỗi hàng, hoặc statement đã thất bại theo trường hợp không hỗ trợ | Kiểm tra tag, mã lỗi và trạng thái statement |
| `CREATE_ERROR_LOG` thất bại với kiểu cột | Bảng đích có kiểu không hỗ trợ trong error table | Dùng `skip_unsupported => TRUE` và lưu riêng dữ liệu cần truy vết |
| Batch dừng ở lỗi đầu tiên | Không khai báo LOG ERRORS hoặc reject limit mặc định bằng 0 | Thêm error logging và đặt reject limit phù hợp |
| Dùng `UNLIMITED` nhưng statement vẫn thất bại | Lỗi không thuộc phạm vi row-level logging hoặc lỗi tài nguyên/statement | Xử lý nguyên nhân gốc; không coi UNLIMITED là bỏ qua mọi lỗi |
| Không truy ra `STAGE_ROW_ID` | Error table dựa trên cột target, không tự giữ mọi cột source | Dùng khóa tương quan duy nhất hoặc quarantine table |
| Source có lỗi chuyển đổi nhưng không vào error log | Lỗi xảy ra trong source expression trước DML | Validate/chuẩn hóa dữ liệu staging trước |
| `ORA-30926` khi MERGE | Source có nhiều hàng tác động cùng một target row | Deduplicate hoặc aggregate source trước MERGE |
| Vi phạm unique không được ghi như mong đợi | Một số unique constraint/index violation nằm ngoài hỗ trợ của DML error logging | Thiết kế khóa, kiểm tra trùng và xử lý riêng; tham khảo restriction theo release |
| Error log table tăng không giới hạn | Không có retention/archive | Quản lý theo batch và thời hạn lưu |
| Dữ liệu target đã đổi nhưng batch chưa đánh dấu xong | Commit và cập nhật trạng thái batch không được phối hợp | Thiết kế transaction và checkpoint nhất quán |

## 16. Bài tập thực hành

Sử dụng `LAB_INVENTORY`, `LAB_INVENTORY_STAGE` và `ERR$_LAB_INVENTORY` trong mục 3.

### Bài 1 — Tạo error log table

Gọi `DBMS_ERRLOG.CREATE_ERROR_LOG` cho `LAB_INVENTORY`. Dùng `DESC` để nhận diện năm cột hệ thống và các cột dữ liệu target.

### Bài 2 — Nạp batch có hàng lỗi

Chạy `INSERT ... SELECT ... LOG ERRORS` cho batch 100. Ghi lại:

- Tổng số hàng nguồn.
- Số hàng có trong target sau nạp.
- Số hàng lỗi theo tag `LOAD_100`.
- Mã lỗi và thông báo của từng hàng bị từ chối.

### Bài 3 — Phân loại lỗi

Phân loại năm hàng lỗi theo NOT NULL, CHECK và độ dài cột. Viết truy vấn tổng hợp số lỗi theo `ORA_ERR_NUMBER$`.

### Bài 4 — Truy vết về staging

Join error log với staging theo `ITEM_ID`. Sau đó tạo hai hàng staging cùng `ITEM_ID` và giải thích vì sao khóa đó không còn đủ để truy vết một hàng duy nhất. Đề xuất cách dùng `STAGE_ROW_ID` trong quarantine.

### Bài 5 — Reject limit

Chạy một bản sao dữ liệu lab với `REJECT LIMIT 1`, sau đó với `UNLIMITED`. Quan sát hành vi khi số lỗi vượt ngưỡng. Kiểm tra trạng thái target và error log trong transaction của bạn trước khi commit.

### Bài 6 — MERGE có error logging

Chạy batch 200 ở mục 9. Xác định hàng nào đi vào MATCHED, hàng nào đi vào NOT MATCHED, và lỗi nào được ghi theo tag `MERGE_200`.

### Bài 7 — Lỗi source conversion

Tạo bảng staging thô có `RAW_PRICE VARCHAR2`. Chèn một giá trị số hợp lệ và một chuỗi không chuyển được. Dùng `VALIDATE_CONVERSION` để tách hai nhóm trước khi INSERT vào target.

### Bài 8 — Quy trình batch hoàn chỉnh

Thiết kế các bước nhận batch, validate, DML với LOG ERRORS, kiểm tra tỷ lệ lỗi, quarantine, commit/rollback và đánh dấu batch. Nêu rõ trường hợp nào cần dừng toàn bộ batch dù `REJECT LIMIT UNLIMITED`.

## 17. Dọn dữ liệu lab

Chỉ chạy trong schema thực hành do bạn tạo, sau khi đã lưu kết quả cần thiết:

~~~sql
DROP TABLE err$_lab_inventory PURGE;
DROP TABLE lab_inventory_stage PURGE;
DROP TABLE lab_inventory PURGE;
~~~

Error log table không có nghĩa vụ khóa ngoại tới target, nhưng nên xóa nó trước để giữ thứ tự dọn dẹp dễ hiểu. `PURGE` bỏ qua recycle bin; không dùng với bảng nghiệp vụ hoặc dữ liệu cần khôi phục.

## Tổng kết

`DBMS_ERRLOG.CREATE_ERROR_LOG` tạo bảng nhận thông tin lỗi cho một bảng đích; `LOG ERRORS INTO ... ('tag') REJECT LIMIT ...` gắn bảng đó vào câu DML và định danh lần chạy. Khi một lỗi thuộc phạm vi row-level logging xảy ra, Oracle ghi mã lỗi, thông báo, loại thao tác, tag và các cột target được hỗ trợ, rồi tiếp tục xử lý trong giới hạn reject limit.

Hãy phân biệt lỗi hàng với lỗi khiến cả statement thất bại. `REJECT LIMIT UNLIMITED` không bỏ qua lỗi cú pháp, lỗi source query, lỗi tài nguyên, constraint trì hoãn hay mọi vi phạm unique. Với dữ liệu staging, validate các biểu thức chuyển đổi trước DML; chuẩn hóa nguồn trước MERGE; lưu khóa tương quan để truy vết; và giữ error log theo batch để sửa hoặc quarantine hàng lỗi. Chỉ commit khi số liệu target, số lỗi và trạng thái batch đã được đối soát theo chính sách nạp dữ liệu.

## Tài liệu Oracle tham khảo

- [Oracle Database SQL Language Reference — INSERT (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/INSERT.html) — cú pháp DML error logging clause và reject limit.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_ERRLOG (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_ERRLOG.html) — `CREATE_ERROR_LOG` và cấu trúc bảng lỗi.
- [Oracle Database SQL Language Reference — MERGE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/MERGE.html) — dùng error logging trong MERGE.
- [Oracle Database SQL Language Reference — UPDATE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/UPDATE.html) — error logging trong UPDATE.
- [Oracle Database SQL Language Reference — DELETE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/DELETE.html) — error logging trong DELETE.
- [Oracle Database SQL Language Reference — VALIDATE_CONVERSION (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/VALIDATE_CONVERSION.html) — kiểm tra khả năng chuyển đổi trước khi nạp.

Khi triển khai trên Oracle release khác 19c, hãy đối chiếu SQL Language Reference và PL/SQL Packages Reference đúng phiên bản, nhất là các hạn chế về kiểu dữ liệu, unique constraint, direct-path DML và reject limit.
