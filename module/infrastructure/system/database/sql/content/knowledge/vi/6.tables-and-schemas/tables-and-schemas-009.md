# Bảng tạm và phạm vi tồn tại theo kết nối hoặc giao dịch

Trong SQL, **bảng tạm (temporary table)** là một bảng dùng cho dữ liệu trung gian trong quá trình xử lý, chẳng hạn lưu danh sách mã cần kiểm tra, chuẩn bị dữ liệu báo cáo hoặc chia một phép biến đổi phức tạp thành nhiều bước. Điểm quan trọng là **bảng tạm tồn tại trong phạm vi nào, dữ liệu bị xóa khi nào và công cụ nào thực sự đang giữ kết nối với cơ sở dữ liệu**.

Cùng một từ “tạm”, các hệ quản trị cơ sở dữ liệu (DBMS) có thể có quy tắc rất khác nhau: bảng tạm của PostgreSQL thường gắn với **phiên kết nối** và có thể cấu hình hành vi khi **COMMIT**; MySQL gắn bảng tạm với phiên; SQL Server phân biệt bảng tạm cục bộ và toàn cục; Oracle có kiểu bảng tạm mà **định nghĩa bảng tồn tại lâu dài nhưng dữ liệu của mỗi phiên là tạm thời**.

Bài học này lấy **PostgreSQL** làm môi trường thực hành chính để giải thích rõ hai lớp phạm vi **kết nối (session)** và **giao dịch (transaction)**, sau đó so sánh với các DBMS khác.

## 1. Bảng tạm là gì và khác bảng thông thường ra sao?

Bảng thông thường lưu dữ liệu để nhiều phiên truy cập theo quyền và quy tắc giao dịch của hệ thống. Ví dụ, bảng `customers` chứa thông tin khách hàng chính thức; khi ứng dụng đóng kết nối, bảng vẫn tồn tại.

Bảng tạm dùng để lưu kết quả hoặc dữ liệu trung gian phục vụ công việc ngắn hạn. Trong PostgreSQL, có thể tạo bằng:

```sql
CREATE TEMPORARY TABLE lesson_numbers (
    number_value INTEGER NOT NULL
);
```

Từ khóa `TEMPORARY` có thể viết ngắn là `TEMP`:

```sql
CREATE TEMP TABLE lesson_numbers_short (
    number_value INTEGER NOT NULL
);
```

Trong PostgreSQL, những bảng vừa tạo là **bảng riêng của phiên hiện tại**. Khi phiên đó kết thúc, hệ thống tự loại bỏ các bảng tạm và dữ liệu của chúng. Đừng hiểu “bảng tạm” đơn giản là “dữ liệu chỉ được giữ trong RAM”: PostgreSQL vẫn có thể dùng bộ nhớ và đĩa để xử lý, lưu trữ và quản lý bảng tạm.

| Thuộc tính | Bảng thông thường trong PostgreSQL | Bảng tạm PostgreSQL |
|---|---|---|
| Câu lệnh tạo | `CREATE TABLE` | `CREATE TEMP TABLE` |
| Định nghĩa bảng | Tồn tại cho đến khi được thay đổi/xóa | Thông thường chỉ trong phiên kết nối tạo bảng |
| Dữ liệu | Lưu lâu dài theo giao dịch, sao lưu và chính sách hệ thống | Dữ liệu trung gian theo phiên, có tùy chọn xử lý khi `COMMIT` |
| Khả năng truy cập từ phiên khác | Có, nếu được cấp quyền và thỏa điều kiện giao dịch | Phiên khác không thể truy cập bảng tạm của phiên tạo |
| Tên bảng | Thuộc schema thông thường | Nằm trong schema tạm riêng của phiên |
| Mục đích tiêu biểu | Dữ liệu nghiệp vụ chính thức | Bước trung gian của tính toán, xử lý dữ liệu |

**Phân biệt “tạm” với “không quan trọng”:** bảng tạm vẫn là đối tượng SQL có cột, kiểu dữ liệu, ràng buộc và có thể có chỉ mục. Nếu dùng sai giao dịch hoặc kết nối, dữ liệu có thể biến mất trước khi tác vụ dùng đến.

## 2. Phiên kết nối, giao dịch và câu lệnh: ba phạm vi khác nhau

Trước khi dùng bảng tạm, cần tách ba khái niệm:

- **Câu lệnh (statement):** một lệnh SQL như `SELECT`, `INSERT` hoặc `CREATE TABLE`.
- **Giao dịch (transaction):** một nhóm thao tác được thực hiện như một đơn vị, kết thúc bằng `COMMIT` hoặc `ROLLBACK`. Với PostgreSQL, có thể bắt đầu bằng `BEGIN`.
- **Phiên/kết nối (session/connection):** một phiên giao tiếp đang hoạt động giữa client và DBMS. Trong bài, “kết nối” là **kết nối vật lý tới DBMS**; ứng dụng dùng connection pool có thể mượn và trả lại kết nối này nhiều lần.

Một phiên có thể thực hiện **nhiều giao dịch liên tiếp**:

```text
Phiên A (kết nối vật lý vẫn mở)
│
├─ Giao dịch T1: BEGIN → SQL → COMMIT
│
├─ Giao dịch T2: BEGIN → SQL → ROLLBACK
│
├─ Giao dịch T3: BEGIN → SQL → COMMIT
│
└─ Đóng kết nối
```

Một bảng tạm **gắn với phiên** có thể còn tồn tại trong T2 và T3 sau khi T1 đã `COMMIT`. Một bảng tạm được cấu hình **xóa dữ liệu khi kết thúc giao dịch** có thể vẫn còn định nghĩa bảng nhưng không còn hàng dữ liệu sau `COMMIT`. Một bảng tạm được cấu hình **xóa cả bảng khi COMMIT** không tồn tại trong giao dịch tiếp theo.

Đây là ba trạng thái cần phân biệt:

1. **Bảng còn tồn tại không?** Có thể chạy `SELECT` từ tên bảng đó hay không?
2. **Dữ liệu trong bảng còn không?** Bảng có thể tồn tại nhưng trả về 0 hàng.
3. **Phiên nào sở hữu bảng?** Một kết nối khác có thể không thấy bảng tạm dù phiên tạo vẫn đang sử dụng bình thường.

## 3. Tạo và dùng bảng tạm trong PostgreSQL

### 3.1. Tạo bảng và thao tác như bảng thông thường

Giả sử bạn muốn chuẩn bị một danh sách mã đơn hàng để kiểm tra trong lúc thực hành:

```sql
CREATE TEMP TABLE lesson_order_stage (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    amount NUMERIC(12, 2) NOT NULL
);

INSERT INTO lesson_order_stage (order_id, customer_id, amount)
VALUES
    (101, 1, 200000.00),
    (102, 1, 150000.00),
    (103, 2, 500000.00);

SELECT *
FROM lesson_order_stage
ORDER BY order_id;
```

Kết quả `SELECT` trả ba dòng vừa nhập. Có thể dùng `WHERE`, `JOIN`, `GROUP BY` hoặc cập nhật dữ liệu trong bảng tạm như với bảng thông thường:

```sql
SELECT
    customer_id,
    COUNT(*) AS number_of_orders,
    SUM(amount) AS total_amount
FROM lesson_order_stage
GROUP BY customer_id
ORDER BY customer_id;
```

Ví dụ tổng theo khách hàng: khách hàng 1 có hai đơn với tổng 350000; khách hàng 2 có một đơn với tổng 500000.

Khi không cần nữa, bạn có thể chủ động xóa bảng trong **chính phiên đã tạo**:

```sql
DROP TABLE lesson_order_stage;
```

Nếu không `DROP`, PostgreSQL sẽ tự loại bỏ bảng tạm khi phiên tạo kết thúc. Khi chạy lại ví dụ trong cùng phiên, bảng cũ có thể vẫn còn, nên phải chủ động dọn bảng đã tạo hoặc dùng tên riêng cho lượt thực hành. Không chạy `DROP TABLE` với tên không kiểm tra trên database quan trọng, vì nếu bảng tạm không tồn tại, tên đó có thể trỏ tới một bảng thường.

### 3.2. Tạo bảng tạm từ kết quả truy vấn

Nếu cần lưu kết quả trung gian của một truy vấn, PostgreSQL hỗ trợ `CREATE TEMP TABLE ... AS SELECT`:

```sql
CREATE TEMP TABLE lesson_customer_totals AS
SELECT
    customer_id,
    COUNT(*) AS order_count,
    SUM(amount) AS total_amount
FROM (
    VALUES
        (1, 200000.00::NUMERIC),
        (1, 150000.00::NUMERIC),
        (2, 500000.00::NUMERIC)
) AS orders(customer_id, amount)
GROUP BY customer_id;

SELECT *
FROM lesson_customer_totals
ORDER BY customer_id;
```

Đây là ví dụ **tự chứa**, không phụ thuộc bảng nghiệp vụ nào khác: phần `VALUES` tạo ba dòng dữ liệu đầu vào ngay trong câu lệnh. PostgreSQL xác định các cột đầu ra của bảng tạm dựa trên danh sách `SELECT`.

Một khả năng khác là `SELECT ... INTO TEMP TABLE` trong PostgreSQL, nhưng `CREATE TEMP TABLE ... AS SELECT` thường thể hiện mục đích rõ hơn. **Không nhầm** với `SELECT ... INTO` trong ngôn ngữ thủ tục hoặc với cú pháp `SELECT INTO` của SQL Server: cách hiểu khác nhau theo ngữ cảnh và DBMS.

### 3.3. Schema chứa bảng tạm

PostgreSQL tạo một **schema tạm riêng** cho mỗi phiên cần sử dụng bảng tạm, thường có tên nội bộ dạng `pg_temp_N`. Bạn thường chỉ cần truy vấn theo tên bảng:

```sql
SELECT *
FROM lesson_customer_totals;
```

Trong PostgreSQL, bảng tạm có thể **che khuất (shadow)** bảng thường cùng tên khi truy vấn không chỉ rõ schema. Ví dụ, nếu phiên có bảng tạm `reports` và database cũng có bảng thường `public.reports`, thì:

```sql
SELECT * FROM reports;        -- Có thể trỏ vào bảng tạm.
SELECT * FROM public.reports; -- Trỏ rõ bảng thường trong schema public.
```

Hai câu `SELECT` trên có thể đọc hai bảng hoàn toàn khác nhau. Khi viết SQL có cả bảng tạm và bảng nghiệp vụ, nên dùng tên tạm dễ nhận diện như `tmp_report_rows` hoặc `lesson_...` và ghi rõ schema của bảng thường khi cần.

Bảng tạm PostgreSQL có schema nội bộ riêng, **không nên cố tạo bảng tạm ngay trong schema thông thường như `public`**. Khi ứng dụng cần truy cập một bảng thường quan trọng, dùng tên có schema rõ ràng sẽ giảm nguy cơ nhầm đối tượng.

## 4. Bảng tạm theo kết nối: hai phiên không chia sẻ dữ liệu

Mở **hai kết nối PostgreSQL độc lập** tới cùng một database, gọi là phiên A và phiên B. Có thể mở hai terminal `psql` hoặc hai kết nối riêng trong GUI.

### Phiên A

```sql
CREATE TEMP TABLE lesson_session_scope (
    item_id INTEGER NOT NULL,
    note TEXT
);

INSERT INTO lesson_session_scope (item_id, note)
VALUES (1, 'Chỉ thuộc phiên A');

SELECT *
FROM lesson_session_scope;
```

Phiên A thấy dòng vừa nhập.

### Phiên B

```sql
SELECT *
FROM lesson_session_scope;
```

Nếu trong database không có bảng thường cùng tên, phiên B nhận lỗi tương tự:

```text
ERROR: relation "lesson_session_scope" does not exist
```

Lý do: phiên B **không thể truy cập bảng tạm được tạo ở phiên A**. Kể cả phiên A đã `COMMIT`, bảng tạm của A vẫn không trở thành bảng chung.

Phiên B có thể tạo **bảng tạm cùng tên của chính mình**:

```sql
CREATE TEMP TABLE lesson_session_scope (
    item_id INTEGER NOT NULL,
    note TEXT
);

INSERT INTO lesson_session_scope (item_id, note)
VALUES (2, 'Chỉ thuộc phiên B');

SELECT *
FROM lesson_session_scope;
```

Bây giờ hai phiên đều dùng tên `lesson_session_scope` nhưng mỗi phiên thấy **dữ liệu riêng**.

### Đóng một phiên có ảnh hưởng gì?

Giả sử bạn đóng hẳn kết nối A. PostgreSQL tự loại bỏ bảng tạm của A. Kết nối B vẫn giữ bảng tạm và dữ liệu của B, miễn là B còn sống và giao dịch/bảng tạm được cấu hình phù hợp.

**Đóng tab SQL không luôn tương đương đóng kết nối DBMS.** Một công cụ GUI có thể vẫn giữ kết nối; ứng dụng dùng connection pool có thể trả kết nối vào pool mà không đóng. Vì vậy, khi kiểm tra vòng đời bảng tạm, hãy xác nhận đúng **phiên cơ sở dữ liệu**, thay vì chỉ nhìn cửa sổ hay màn hình ứng dụng.

## 5. PostgreSQL: ON COMMIT quyết định điều xảy ra khi kết thúc giao dịch

PostgreSQL hỗ trợ ba chế độ cho bảng tạm:

```sql
CREATE TEMP TABLE table_name (
    -- Các cột ...
)
ON COMMIT PRESERVE ROWS;
```

```sql
CREATE TEMP TABLE table_name (
    -- Các cột ...
)
ON COMMIT DELETE ROWS;
```

```sql
CREATE TEMP TABLE table_name (
    -- Các cột ...
)
ON COMMIT DROP;
```

| Chế độ | Khi `COMMIT` | Định nghĩa bảng có còn? | Dữ liệu có còn? | Phù hợp khi |
|---|---|---|---|---|
| `ON COMMIT PRESERVE ROWS` | Giữ dữ liệu đã commit | Có, đến hết phiên hoặc đến khi bị `DROP` | Có | Dữ liệu trung gian dùng qua nhiều giao dịch của cùng phiên |
| `ON COMMIT DELETE ROWS` | Xóa toàn bộ hàng trong bảng tạm | Có, đến hết phiên hoặc đến khi bị `DROP` | Không, sau commit | Tái sử dụng cấu trúc bảng trong từng giao dịch |
| `ON COMMIT DROP` | Xóa bảng tạm | Không, sau commit | Không | Chỉ cần bảng trong một giao dịch |

Trong **PostgreSQL**, chế độ mặc định khi bỏ `ON COMMIT` là **`PRESERVE ROWS`**. Không suy ra chế độ mặc định tương tự ở Oracle hoặc DBMS khác.

### 5.1. PRESERVE ROWS: dữ liệu đã commit vẫn ở đó

Chạy trong **một phiên PostgreSQL**, theo đúng thứ tự:

```sql
CREATE TEMP TABLE lesson_preserve (
    item_id INTEGER PRIMARY KEY,
    note TEXT
) ON COMMIT PRESERVE ROWS;

INSERT INTO lesson_preserve (item_id, note)
VALUES (1, 'Được giữ qua COMMIT');

BEGIN;

INSERT INTO lesson_preserve (item_id, note)
VALUES (2, 'Sẽ bị ROLLBACK');

ROLLBACK;

SELECT item_id, note
FROM lesson_preserve
ORDER BY item_id;
```

Kết quả cuối chỉ còn dòng `item_id = 1` nếu các câu ngoài giao dịch `BEGIN ... ROLLBACK` được chạy với auto-commit thông thường.

Giải thích:

1. Lần `INSERT` đầu đã được commit bởi giao dịch tự động của client.
2. Lần `INSERT` thứ hai diễn ra trong giao dịch riêng.
3. `ROLLBACK` hủy lần chèn thứ hai.
4. Bảng vẫn tồn tại trong phiên và vẫn chứa dòng thứ nhất.

**`PRESERVE ROWS` không có nghĩa bỏ qua `ROLLBACK`.** Nó chỉ quy định bảng tạm không tự xóa hàng đã được commit khi giao dịch kết thúc. Các thay đổi chưa commit vẫn chịu quy tắc giao dịch.

### 5.2. DELETE ROWS: bảng còn, hàng bị xóa khi COMMIT

```sql
BEGIN;

CREATE TEMP TABLE lesson_delete_rows (
    item_id INTEGER
) ON COMMIT DELETE ROWS;

INSERT INTO lesson_delete_rows (item_id)
VALUES (1), (2), (3);

SELECT COUNT(*) AS count_before_commit
FROM lesson_delete_rows;
-- Trong giao dịch hiện tại: 3.

COMMIT;

SELECT COUNT(*) AS count_after_commit
FROM lesson_delete_rows;
-- Sau COMMIT: 0.
```

Điểm chính: sau `COMMIT`, **bảng `lesson_delete_rows` vẫn còn** nhưng không còn dòng nào. Bạn có thể bắt đầu giao dịch mới, thêm dòng mới và sử dụng lại cấu trúc cột của bảng:

```sql
BEGIN;

INSERT INTO lesson_delete_rows (item_id)
VALUES (4);

SELECT * FROM lesson_delete_rows;

COMMIT;
-- Sau COMMIT lần này, hàng 4 cũng bị xóa.
```

**Cảnh báo với chế độ auto-commit:** nếu mỗi câu SQL được DBMS/client thực thi trong giao dịch riêng, thì một lệnh `INSERT` có thể lập tức được commit và hàng bị xóa **trước khi câu `SELECT` tiếp theo chạy**. Khi cần xử lý nhiều lệnh trên cùng dữ liệu tạm `ON COMMIT DELETE ROWS`, hãy bao toàn bộ thao tác trong `BEGIN ... COMMIT`.

### 5.3. DROP: kết thúc giao dịch là kết thúc bảng

```sql
BEGIN;

CREATE TEMP TABLE lesson_drop_at_commit (
    item_id INTEGER
) ON COMMIT DROP;

INSERT INTO lesson_drop_at_commit (item_id)
VALUES (10), (20);

SELECT COUNT(*) AS count_during_transaction
FROM lesson_drop_at_commit;
-- Trong giao dịch hiện tại: 2.

COMMIT;
```

Sau `COMMIT`, bảng đã bị loại bỏ; cố chạy:

```sql
SELECT *
FROM lesson_drop_at_commit;
```

sẽ cho lỗi “relation does not exist”, trừ trường hợp có một bảng khác cùng tên đang được nhìn thấy qua `search_path`.

Nếu muốn kiểm tra bằng một biểu thức ít gây lỗi trong PostgreSQL, có thể dùng:

```sql
SELECT to_regclass('pg_temp.lesson_drop_at_commit') AS temp_table_after_commit;
```

Khi không có bảng tạm tương ứng trong phiên, kết quả sẽ là `NULL`.

**Quan trọng:** nếu tạo bảng `ON COMMIT DROP` trong môi trường auto-commit mà không mở `BEGIN`, câu `CREATE TEMP TABLE` có thể tạo và bị drop ngay khi chính câu lệnh đó kết thúc giao dịch. Vì vậy, ví dụ `ON COMMIT DROP` phải được đặt bên trong một giao dịch tường minh nếu cần thêm hoặc đọc dữ liệu ở các câu lệnh tiếp theo.

### 5.4. So sánh thời điểm sống của bảng và dữ liệu

```text
Một phiên PostgreSQL còn kết nối:
        BEGIN                  COMMIT            BEGIN          COMMIT
          |                      |                 |               |
----------+----------------------+-----------------+---------------+----> thời gian

PRESERVE   [ bảng + dữ liệu ]----[ bảng + dữ liệu tiếp tục tồn tại ]---->
DELETE     [ bảng + dữ liệu ]----[ bảng còn, 0 hàng ]--[ thêm hàng ]--[ 0 hàng ]
DROP       [ bảng + dữ liệu ]----[ không còn bảng ]
                                                                |
                                                   Kết thúc phiên:
                                          mọi bảng tạm còn lại bị loại bỏ
```

Sơ đồ biểu diễn hành vi khi **commit thành công**. Nếu giao dịch `ROLLBACK`, kết quả còn phụ thuộc bảng được tạo ở đâu và thao tác nào đã được commit trước đó.

## 6. ROLLBACK, DDL và bảng tạm: khác với ON COMMIT

`COMMIT` có nghĩa xác nhận giao dịch; `ROLLBACK` có nghĩa hủy các thay đổi chưa commit trong giao dịch. Chúng **không phải hai cách viết tương đương để “kết thúc và xóa bảng tạm”**.

Trong PostgreSQL, các câu lệnh tạo và thay đổi cấu trúc bảng tạm có thể tham gia giao dịch. Ví dụ:

```sql
BEGIN;

CREATE TEMP TABLE lesson_created_then_rollback (
    item_id INTEGER
);

INSERT INTO lesson_created_then_rollback (item_id)
VALUES (1);

ROLLBACK;

SELECT to_regclass(
    'pg_temp.lesson_created_then_rollback'
) AS table_after_rollback;
```

Bảng được **tạo trong giao dịch vừa rollback** nên thao tác tạo bảng bị hủy. Kết quả `to_regclass(...)` là `NULL`.

Trường hợp khác: bảng tạm được tạo và đã commit **trước** giao dịch bị rollback:

```sql
CREATE TEMP TABLE lesson_rollback_rows (
    item_id INTEGER PRIMARY KEY
);

INSERT INTO lesson_rollback_rows (item_id)
VALUES (1);

BEGIN;

INSERT INTO lesson_rollback_rows (item_id)
VALUES (2);

ROLLBACK;

SELECT *
FROM lesson_rollback_rows
ORDER BY item_id;
```

Nếu thực thi ngoài `BEGIN ... ROLLBACK` theo chế độ auto-commit, kết quả chỉ còn dòng `1`. **Định nghĩa bảng vẫn tồn tại** vì nó đã được xác nhận trước giao dịch bị rollback.

Với bảng `ON COMMIT DELETE ROWS` hoặc `ON COMMIT DROP`, hành vi được mô tả bởi cụm từ “**ON COMMIT**” — không tự hiểu `ROLLBACK` sẽ kích hoạt cùng thao tác xóa như `COMMIT`. Hãy xác định lúc nào tạo bảng, lúc nào chèn dữ liệu và giao dịch nào đã được xác nhận.

## 7. Giao dịch tự động và phạm vi phiên trong ứng dụng

### 7.1. Auto-commit không tự đóng phiên

Nhiều công cụ SQL mặc định dùng **auto-commit**: từng câu SQL chạy độc lập và commit khi hoàn thành. Điều này không có nghĩa công cụ đóng kết nối ngay sau từng câu.

Với PostgreSQL:

```sql
CREATE TEMP TABLE lesson_autocommit (
    value_number INTEGER
);
```

Nếu không nêu `ON COMMIT`, bảng dùng mặc định `PRESERVE ROWS`, nên thường vẫn tồn tại sau khi câu `CREATE` được auto-commit. Bạn có thể tiếp tục:

```sql
INSERT INTO lesson_autocommit (value_number)
VALUES (5);

SELECT * FROM lesson_autocommit;
```

nếu cả hai câu chạy trên **cùng phiên kết nối**.

### 7.2. Connection pool làm “cùng ứng dụng” khác “cùng kết nối”

Ứng dụng Java, web API hoặc hệ thống xử lý batch thường dùng **connection pool**. Mỗi lần mượn `Connection`, ứng dụng có thể nhận một kết nối vật lý khác, ngay cả khi cùng một request hay cùng một tài khoản database.

```text
Ứng dụng Java / Web API
        |
        v
     Connection Pool
       /       \
      /         \
  Kết nối A   Kết nối B
  temp_data A temp_data B
      \         /
       PostgreSQL
```

Ví dụ:

1. Tác vụ thứ nhất mượn kết nối A và tạo bảng tạm `tmp_import_rows`.
2. Tác vụ trả kết nối A về pool.
3. Tác vụ thứ hai mượn kết nối B rồi `SELECT * FROM tmp_import_rows`.
4. Truy vấn trên B có thể báo không tìm thấy bảng, vì **B không phải phiên đã tạo bảng tạm**.

Tình huống ngược lại cũng xảy ra: pool cấp lại A cho một request khác và bảng tạm của request trước **vẫn còn**, nếu chưa được drop và kết nối vật lý còn sống. Điều này có thể làm sai kết quả hoặc gây lỗi “table already exists”.

**Quy tắc thực hành:** nếu xử lý dựa vào bảng tạm theo phiên, hãy giữ các thao tác tạo, chèn, đọc và dọn bảng trên **cùng một kết nối**. Dọn dữ liệu/đối tượng trước khi trả kết nối về pool theo quy ước dự án; không mặc định rằng `commit()` hay `close()` trên một đối tượng connection do pool quản lý sẽ đóng hẳn phiên ở DBMS.

### 7.3. Minh họa với JDBC trong Java

Mẫu dưới đây dùng PostgreSQL và JDBC. Đây là **mã minh họa cấu trúc thao tác**, giả định ứng dụng đã thiết lập `DataSource`, quyền tạo bảng tạm và cơ chế xử lý lỗi phù hợp.

```java
try (Connection conn = dataSource.getConnection()) {
    conn.setAutoCommit(false);

    try {
        try (Statement statement = conn.createStatement()) {
            statement.execute("""
                CREATE TEMP TABLE tmp_import_ids (
                    item_id INTEGER PRIMARY KEY
                ) ON COMMIT DROP
                """);
        }

        try (PreparedStatement insert = conn.prepareStatement(
                "INSERT INTO tmp_import_ids (item_id) VALUES (?)")) {
            insert.setInt(1, 101);
            insert.executeUpdate();
        }

        try (Statement statement = conn.createStatement();
             ResultSet rows = statement.executeQuery(
                 "SELECT COUNT(*) FROM tmp_import_ids")) {
            if (rows.next()) {
                System.out.println(rows.getLong(1)); // 1
            }
        }

        conn.commit(); // ON COMMIT DROP: bảng tạm bị xóa.
    } catch (SQLException error) {
        conn.rollback();
        throw error;
    } finally {
        conn.setAutoCommit(true);
    }
}
```

Các thao tác đều dùng một biến `conn`, tức **một kết nối trong phạm vi xử lý này**. `setAutoCommit(false)` cho phép `ON COMMIT DROP` tồn tại xuyên qua nhiều câu lệnh, cho đến khi `commit()`. `PreparedStatement` dùng tham số thay vì ghép dữ liệu người dùng vào SQL.

Đoạn mã giả định Java hỗ trợ text block (`"""`, Java 15+) và `DataSource` có sẵn. Trong code sản xuất, cần áp dụng chính sách khôi phục trạng thái connection của pool và xử lý lỗi ở `rollback()/setAutoCommit()` theo framework; không xem ví dụ đơn giản này là một thư viện quản lý transaction hoàn chỉnh.

### 7.4. Pooling theo giao dịch và proxy kết nối

Một số hệ thống sử dụng proxy/pool ở tầng database có chế độ **transaction pooling**. Chế độ đó có thể gán một kết nối server khác cho các giao dịch nối tiếp, dù client thấy cùng một kết nối logic. Vì bảng tạm PostgreSQL thuộc **phiên phía server**, không thể giả định dữ liệu tạm sẽ còn và truy cập được ở giao dịch tiếp theo.

- Với `ON COMMIT DROP`, vòng đời ngắn trong **một giao dịch** thường dễ giới hạn phạm vi hơn.
- Với bảng tạm cần tồn tại **qua nhiều transaction**, phải xác định ứng dụng thực sự được giữ cùng server session hay không.
- Nếu hệ thống không đảm bảo kết nối ổn định, cân nhắc CTE, truy vấn con hoặc bảng staging thông thường có khóa theo tác vụ.

Không dựa vào tên biến connection hay ID request để suy ra phiên server, vì các thành phần pool có thể tái sử dụng hoặc thay đổi kết nối thực.

## 8. Bảng tạm và dữ liệu trung gian: các mẫu sử dụng phù hợp

### 8.1. Tập hợp dữ liệu nhiều bước

Khi một phép xử lý lớn cần nhiều bước truy vấn, bảng tạm cho phép **lưu kết quả trung gian** để tái sử dụng:

```sql
CREATE TEMP TABLE lesson_sales_stage AS
SELECT *
FROM (
    VALUES
        (1, 101, 120000::NUMERIC),
        (2, 102, 95000::NUMERIC),
        (3, 101, 150000::NUMERIC),
        (4, 103, 250000::NUMERIC)
) AS sales(sale_id, customer_id, amount);

SELECT customer_id, SUM(amount) AS total
FROM lesson_sales_stage
GROUP BY customer_id
ORDER BY customer_id;

SELECT COUNT(*) AS large_sale_count
FROM lesson_sales_stage
WHERE amount >= 100000;
```

Một lần tạo bảng giúp cả hai phép tổng hợp đọc lại cùng dữ liệu trung gian. Nếu nguồn dữ liệu rất lớn và có nhiều bước xử lý, có thể hữu ích so với lặp đi lặp lại cùng logic truy vấn. Tuy nhiên, bảng tạm cũng tốn chi phí tạo bảng, ghi dữ liệu và quản lý đối tượng.

### 8.2. Chỉ mục trên bảng tạm

Bảng tạm PostgreSQL có thể tạo chỉ mục:

```sql
CREATE INDEX lesson_sales_stage_customer_idx
    ON lesson_sales_stage (customer_id);

ANALYZE lesson_sales_stage;
```

Chỉ mục có thể giúp các truy vấn trên bảng tạm đủ lớn hoặc có nhiều thao tác tìm kiếm/nối, nhưng trên bảng vài dòng như ví dụ, chi phí tạo chỉ mục thường không đáng. `ANALYZE` giúp bộ tối ưu hóa có thống kê về dữ liệu bảng tạm PostgreSQL; cơ chế autovacuum của PostgreSQL không tự phân tích các bảng tạm của phiên như đối với bảng thường.

**Không mặc định bảng tạm luôn nhanh hơn.** Hiệu quả phụ thuộc số hàng, độ phức tạp truy vấn, chỉ mục, cách sử dụng lại dữ liệu và tài nguyên hệ thống. Khi hiệu năng quan trọng, so sánh kế hoạch thực thi `EXPLAIN` trong đúng DBMS.

### 8.3. Chuẩn bị danh sách ID để JOIN

Một tập mã cần lọc hoặc xử lý nhiều lần có thể đặt trong bảng tạm:

```sql
CREATE TEMP TABLE lesson_selected_customers (
    customer_id INTEGER PRIMARY KEY
);

INSERT INTO lesson_selected_customers (customer_id)
VALUES (101), (103), (105);

SELECT *
FROM lesson_selected_customers
ORDER BY customer_id;
```

Trong hệ thống thực tế, bạn có thể nối với bảng khách hàng chính thức:

```sql
-- Giả định đã có bảng public.customers(customer_id, customer_name).
SELECT
    c.customer_id,
    c.customer_name
FROM public.customers AS c
JOIN lesson_selected_customers AS s
    ON s.customer_id = c.customer_id;
```

Ví dụ `JOIN` này minh họa việc dùng dữ liệu tạm để lọc dữ liệu thật. Nó chỉ chạy được nếu database thực hành có bảng `public.customers` với các cột tương ứng. Khi xử lý danh sách chỉ vài ID dùng một lần, một `VALUES` hoặc tham số mảng có thể đơn giản hơn tạo bảng tạm.

## 9. So sánh bảng tạm với CTE, truy vấn con và bảng staging

Không phải mọi kết quả trung gian đều cần một bảng tạm.

| Công cụ | Phạm vi sử dụng | Dữ liệu/định nghĩa có tồn tại sau câu truy vấn? | Khi nào cân nhắc |
|---|---|---|---|
| Truy vấn con (subquery/derived table) | Trong một câu SQL | Không có bảng trung gian đặt tên tồn tại như một đối tượng riêng | Logic ngắn, chỉ dùng tại một chỗ |
| CTE `WITH` | Trong phạm vi một câu SQL | Không như đối tượng tồn tại qua các câu SQL | Chia một truy vấn thành các bước dễ đọc |
| View thông thường | Đối tượng schema tồn tại đến khi bị xóa | Định nghĩa view tồn tại; dữ liệu được truy vấn từ nguồn | Tái sử dụng logic truy vấn trong nhiều phiên |
| Bảng tạm PostgreSQL | Phiên tạo; dữ liệu có thể bị tác động bởi `ON COMMIT` | Có thể qua nhiều câu lệnh/giao dịch cùng phiên | Nhiều bước xử lý cần lưu và tái sử dụng kết quả trung gian |
| Bảng staging thông thường | Đối tượng trong schema, có quyền truy cập giữa các phiên | Có, đến khi ứng dụng chủ động dọn | Xử lý kéo dài nhiều phiên, job độc lập, chia sẻ giữa worker |

Ví dụ cùng một phép tính gói trong **một câu SQL** bằng CTE:

```sql
WITH sales_stage AS (
    SELECT *
    FROM (
        VALUES
            (101, 120000::NUMERIC),
            (102, 95000::NUMERIC),
            (101, 150000::NUMERIC)
    ) AS sales(customer_id, amount)
)
SELECT
    customer_id,
    SUM(amount) AS total_amount
FROM sales_stage
GROUP BY customer_id
ORDER BY customer_id;
```

CTE cho phép đặt tên bước trung gian nhưng **không tạo bảng tạm để câu SQL sau đọc lại**. Tùy DBMS, phiên bản và kế hoạch thực thi, CTE có thể được nội tuyến hoặc vật hóa; tránh khẳng định CTE luôn chạy nhanh hơn hoặc chậm hơn bảng tạm.

Bảng staging **thông thường** có thể được thiết kế với cột `job_id`, `created_at` và cơ chế dọn dữ liệu, phù hợp khi nhiều kết nối hoặc nhiều worker cần dùng chung kết quả. Đổi lại, ứng dụng phải quản lý quyền truy cập, cô lập dữ liệu theo tác vụ, dọn dữ liệu cũ và tài nguyên lưu trữ.

## 10. Khác biệt giữa các hệ quản trị cơ sở dữ liệu

Cú pháp và vòng đời bảng tạm **không hoàn toàn theo một chuẩn chung**. Khi đọc tài liệu hoặc chuyển hệ thống, hãy kiểm tra cả **định nghĩa bảng** lẫn **phạm vi hàng dữ liệu**.

| DBMS | Cú pháp/khái niệm | Phạm vi truy cập và tồn tại | Vai trò của giao dịch |
|---|---|---|---|
| **PostgreSQL** | `CREATE TEMP TABLE` | Bảng riêng của phiên, tự bị xóa khi phiên kết thúc | `ON COMMIT PRESERVE ROWS`, `DELETE ROWS` hoặc `DROP` |
| **MySQL** | `CREATE TEMPORARY TABLE` | Bảng tạm thuộc phiên tạo, tự bị xóa khi kết nối đóng | Không có cùng ba chế độ `ON COMMIT` như PostgreSQL; quy tắc DDL/rollback khác |
| **SQL Server** | `#local_temp` và `##global_temp` | `#` chủ yếu trong phiên/phạm vi tạo; `##` có thể được nhiều phiên nhìn thấy | Không dùng cú pháp PostgreSQL `ON COMMIT`; chịu quy tắc giao dịch T-SQL |
| **Oracle** | `GLOBAL TEMPORARY TABLE` | Định nghĩa bảng là đối tượng database tồn tại lâu dài; mỗi phiên chỉ thấy dữ liệu của mình | `ON COMMIT DELETE ROWS` hoặc `PRESERVE ROWS` quyết định phạm vi dữ liệu |
| **SQLite** | `CREATE TEMP TABLE` | Bảng nằm trong schema `temp` của một kết nối | Tuân thủ giao dịch SQLite, nhưng không có `ON COMMIT DROP/DELETE ROWS` như PostgreSQL |

### 10.1. MySQL: bảng tạm theo phiên

Ví dụ trong MySQL:

```sql
CREATE TEMPORARY TABLE tmp_customer_ids (
    customer_id INT PRIMARY KEY
);

INSERT INTO tmp_customer_ids (customer_id)
VALUES (1), (2), (3);

SELECT *
FROM tmp_customer_ids;
```

Bảng chỉ dùng được trong **phiên tạo**, và được tự dọn khi phiên kết thúc. Một phiên khác có thể tạo bảng tạm trùng tên mà không dùng chung dữ liệu.

Một điểm cần chú ý trong MySQL: `CREATE TEMPORARY TABLE` và `DROP TEMPORARY TABLE` không gây implicit commit như nhiều thao tác DDL khác, nhưng **bản thân thao tác tạo/drop bảng tạm không được rollback để khôi phục trạng thái như DDL giao dịch của PostgreSQL**. Với bảng tạm dùng engine giao dịch như InnoDB, thay đổi dữ liệu `INSERT/UPDATE/DELETE` có thể chịu tác động của giao dịch.

MySQL cũng có cơ chế bảng tạm cùng tên **che khuất** bảng thường trong một phiên. Vì vậy, không nên dựa vào tên bảng không chỉ rõ ngữ cảnh khi thao tác dữ liệu quan trọng.

### 10.2. SQL Server: bảng tạm cục bộ và toàn cục

SQL Server thường đặt bảng tạm trong `tempdb` và dùng tiền tố tên:

```sql
CREATE TABLE #local_stage (
    item_id INT PRIMARY KEY,
    note NVARCHAR(100)
);

INSERT INTO #local_stage (item_id, note)
VALUES (1, N'Chỉ dùng theo phạm vi local');

SELECT *
FROM #local_stage;
```

`#local_stage` là bảng tạm **cục bộ**; phạm vi nhìn thấy còn phụ thuộc vị trí tạo, ví dụ tạo trong stored procedure có thể làm bảng bị loại bỏ khi stored procedure kết thúc. Nếu tạo tại phiên tương tác thông thường, bảng thường tồn tại đến khi phiên đóng hoặc được drop.

Bảng tạm **toàn cục** dùng `##`:

```sql
CREATE TABLE ##global_stage (
    item_id INT PRIMARY KEY
);
```

Bảng `##global_stage` có thể được phiên khác truy cập khi còn tồn tại, nên không phù hợp để giả định mỗi phiên có dữ liệu riêng. Theo mặc định trên nhiều cấu hình SQL Server, bảng tạm toàn cục được dọn khi phiên tạo kết thúc và không còn câu lệnh đang dùng nó; một số phiên bản/cấu hình có thể thay đổi việc tự dọn. Trong hệ thống nhiều người dùng, phải chú ý tên bảng, xung đột và quyền truy cập.

**Không dùng `ON COMMIT DROP` của PostgreSQL trong T-SQL.** Khi chuyển script sang SQL Server, thiết kế lại vòng đời bảng theo phạm vi `#`/`##`, stored procedure và transaction của T-SQL.

### 10.3. Oracle: định nghĩa tồn tại lâu dài, dữ liệu theo giao dịch hoặc phiên

Oracle có **global temporary table (GTT)**. Khác với PostgreSQL, từ **GLOBAL** ở đây không có nghĩa là các phiên chia sẻ các hàng trong bảng: nhiều phiên có thể dùng cùng **định nghĩa bảng**, nhưng dữ liệu của từng phiên được giữ riêng.

Ví dụ dạng dữ liệu **theo giao dịch** trong Oracle:

```sql
CREATE GLOBAL TEMPORARY TABLE work_items_tx (
    item_id NUMBER
) ON COMMIT DELETE ROWS;
```

Hoặc dữ liệu **theo phiên**:

```sql
CREATE GLOBAL TEMPORARY TABLE work_items_session (
    item_id NUMBER
) ON COMMIT PRESERVE ROWS;
```

Với `DELETE ROWS`, Oracle xóa dữ liệu tạm của giao dịch khi commit; với `PRESERVE ROWS`, dữ liệu có thể được giữ trong phiên qua các giao dịch. Tuy nhiên, **định nghĩa GTT vẫn tồn tại** trong database cho đến khi bị xóa theo cách quản trị đối tượng. Lệnh `CREATE GLOBAL TEMPORARY TABLE` không phải thứ bạn thường cần chạy lại mỗi khi ứng dụng mở một connection.

Oracle còn hỗ trợ **private temporary table** ở các phiên bản phù hợp, với quy tắc vòng đời **định nghĩa** riêng. Đừng đánh đồng private temporary table, global temporary table và bảng tạm PostgreSQL chỉ vì tất cả đều có chữ “temporary”.

### 10.4. SQLite: bảng tạm theo kết nối

SQLite có thể tạo bảng trong schema `temp`:

```sql
CREATE TEMP TABLE temp_values (
    value_number INTEGER
);

INSERT INTO temp_values (value_number)
VALUES (10), (20);

SELECT SUM(value_number)
FROM temp_values;
```

Bảng tạm này thuộc **kết nối SQLite hiện tại** và mất khi kết nối đóng. Một kết nối SQLite khác, kể cả cùng mở một file database, không dùng chung bảng `temp_values` của kết nối đầu. SQLite không hỗ trợ tùy chọn `ON COMMIT DELETE ROWS` hoặc `ON COMMIT DROP` theo cú pháp PostgreSQL; commit các thao tác dữ liệu không tự động dọn bảng tạm của kết nối.

## 11. Những giới hạn và rủi ro thực tế

### 11.1. Bảng tạm không tự bảo đảm “nhẹ” hoặc “nằm trong RAM”

Bảng tạm vẫn tiêu thụ tài nguyên xử lý. Tùy DBMS và khối lượng công việc, có thể dùng bộ nhớ, tệp tạm, vùng lưu trữ hệ thống hoặc log nhất định. Tạo quá nhiều bảng tạm hoặc giữ dữ liệu lớn trong những phiên lâu sống có thể gây áp lực lên hệ thống.

Nếu chỉ cần một kết quả trung gian một lần, thử truy vấn con hoặc CTE trước; nếu cần dùng lại nhiều lần, cân nhắc bảng tạm dựa trên chi phí thực tế.

### 11.2. Tạo quá nhiều bảng tạm là một chi phí vận hành

Mỗi `CREATE TEMP TABLE` có chi phí tạo đối tượng và quản lý metadata. Một ứng dụng có hàng nghìn request/giây, mỗi request tự tạo nhiều bảng tạm nhỏ, có thể tạo thêm tải không cần thiết. Ngược lại, việc dùng một bảng tạm lớn, được lập chỉ mục hợp lý cho job nặng đôi khi hữu ích hơn một truy vấn cực lớn. Cách chọn phụ thuộc đặc điểm workload.

### 11.3. Bảng tạm không phải cơ chế chia sẻ công việc nhiều phiên

Nếu hai tiến trình cần **chung dữ liệu trung gian**, bảng tạm theo phiên của PostgreSQL/MySQL/SQLite không đáp ứng trực tiếp. Sử dụng một bảng staging thông thường, có khóa tác vụ (`job_id`), quyền truy cập phù hợp và dọn dữ liệu có kiểm soát khi cần chia sẻ giữa các kết nối.

### 11.4. Quyền tạo bảng và dữ liệu nhạy cảm

Tài khoản cần quyền phù hợp để tạo bảng tạm. Ví dụ PostgreSQL quản lý quyền `TEMPORARY` trên database. Dữ liệu trong bảng tạm vẫn có thể chứa thông tin nhạy cảm và vẫn phải tuân thủ quy định về bảo mật, nhật ký, truy cập và tài nguyên. Không coi chữ “temporary” là bảo đảm riêng tư hoặc an toàn mặc định.

### 11.5. Tên bảng và việc dọn dữ liệu

Nếu tạo bảng tạm rồi kết nối bị tái sử dụng, bảng có thể còn với cùng tên và dữ liệu cũ. Trong PostgreSQL, chọn một chiến lược:

- Dùng `ON COMMIT DROP` nếu tác vụ gói gọn trong một transaction.
- Gọi `DROP TABLE` ở cuối phạm vi phiên đã tạo, kiểm soát lỗi và giao dịch theo kiến trúc ứng dụng.
- Đặt tên rõ ràng, tránh trùng với bảng nghiệp vụ và tránh giả định trả connection về pool đã xóa dữ liệu.
- Kiểm tra nơi tên bảng được phân giải khi có cả bảng tạm và bảng thường cùng tên.

Không dọn bảng “theo tên” một cách tùy tiện nếu chưa xác định rõ đó chính là đối tượng tạm của tác vụ hiện tại.

## 12. Cách chọn vòng đời phù hợp

Có thể ra quyết định theo thứ tự:

1. **Dữ liệu chỉ dùng trong một câu SQL?** Dùng truy vấn con hoặc CTE nếu biểu thức và mục đích cho phép.
2. **Cần lưu dữ liệu qua nhiều câu SQL trong cùng một giao dịch?** Bảng tạm `ON COMMIT DROP` thường phù hợp trong PostgreSQL khi muốn tự dọn ở `COMMIT`.
3. **Cần tái sử dụng cấu trúc bảng ở từng giao dịch, nhưng không giữ hàng qua commit?** Cân nhắc `ON COMMIT DELETE ROWS` trong PostgreSQL.
4. **Cần giữ kết quả qua nhiều giao dịch của cùng phiên vật lý?** Dùng `ON COMMIT PRESERVE ROWS` và quản lý dọn bảng rõ ràng; xác nhận pool/proxy không đổi server session.
5. **Cần chia sẻ giữa nhiều phiên hoặc phục hồi sau khi mất kết nối?** Cân nhắc bảng staging thường có quản lý vòng đời, thay vì bảng tạm gắn phiên.

Mỗi lựa chọn đều phụ thuộc DBMS. Câu hỏi **“bảng tồn tại tới khi nào?”** và câu hỏi **“dữ liệu tồn tại tới khi nào?”** có thể có câu trả lời khác nhau.

## 13. Bài tập thực hành

Các bài dưới đây dựa trên PostgreSQL, yêu cầu kết nối tới một database thực hành. Hãy tạo bảng trong đúng phiên được nêu. Dùng tên riêng hoặc xóa những bảng đã tạo nếu muốn chạy lại toàn bộ bài.

### Bài 1. Dự đoán dữ liệu sau COMMIT

Chạy trong cùng một phiên:

```sql
CREATE TEMP TABLE lesson_task_preserve (
    id INTEGER
) ON COMMIT PRESERVE ROWS;

BEGIN;
INSERT INTO lesson_task_preserve (id) VALUES (1), (2);
COMMIT;

SELECT COUNT(*) AS count_after_commit
FROM lesson_task_preserve;
```

**Câu hỏi:** Kết quả là bao nhiêu? **Đáp án:** `2`. Hàng đã được commit và chế độ `PRESERVE ROWS` giữ chúng trong phiên.

### Bài 2. Dự đoán dữ liệu sau DELETE ROWS

```sql
BEGIN;

CREATE TEMP TABLE lesson_task_delete (
    id INTEGER
) ON COMMIT DELETE ROWS;

INSERT INTO lesson_task_delete (id)
VALUES (1), (2), (3);

COMMIT;

SELECT COUNT(*) AS count_after_commit
FROM lesson_task_delete;
```

**Đáp án:** `0`. Bảng còn tồn tại nhưng các hàng bị xóa khi commit.

### Bài 3. Dự đoán điều xảy ra khi DROP

```sql
BEGIN;

CREATE TEMP TABLE lesson_task_drop (
    id INTEGER
) ON COMMIT DROP;

INSERT INTO lesson_task_drop (id)
VALUES (1);

COMMIT;
```

**Câu hỏi:** Sau đó chạy `SELECT * FROM lesson_task_drop;` sẽ thế nào? **Đáp án:** bảng tạm đã bị drop khi commit, nên câu lệnh không tìm thấy bảng tạm; nếu có bảng khác cùng tên trong đường dẫn schema, việc phân giải tên có thể chuyển sang bảng khác. Để nhận biết bảng tạm của phiên, kiểm tra `to_regclass('pg_temp.lesson_task_drop')`.

### Bài 4. Hai kết nối độc lập

Trong phiên A:

```sql
CREATE TEMP TABLE lesson_task_connection (
    id INTEGER
);

INSERT INTO lesson_task_connection (id)
VALUES (10);
```

Mở phiên B kết nối cùng database rồi chạy:

```sql
SELECT * FROM lesson_task_connection;
```

**Đáp án:** B không truy cập được bảng tạm do A tạo. Nếu B không có bảng thường hoặc bảng tạm riêng cùng tên, hệ thống báo không tìm thấy quan hệ. B có thể tạo một bảng tạm **cùng tên** với dữ liệu riêng.

### Bài 5. Tại sao SELECT không còn thấy dữ liệu sau auto-commit?

Một học viên thực hiện:

```sql
CREATE TEMP TABLE lesson_task_autocommit (
    id INTEGER
) ON COMMIT DELETE ROWS;

INSERT INTO lesson_task_autocommit (id)
VALUES (5);

SELECT *
FROM lesson_task_autocommit;
```

Mỗi câu SQL được auto-commit riêng. **Hỏi:** Vì sao `SELECT` không thấy hàng `5`? **Đáp án:** `INSERT` đã commit trước khi chạy `SELECT`, và chế độ `ON COMMIT DELETE ROWS` tự xóa hàng ở thời điểm đó.

**Cách sửa khi cần dùng hàng trong nhiều câu của cùng công việc:**

```sql
BEGIN;

INSERT INTO lesson_task_autocommit (id)
VALUES (5);

SELECT *
FROM lesson_task_autocommit;
-- Thấy hàng 5 khi giao dịch chưa commit.

COMMIT;
-- Sau đây bảng vẫn tồn tại nhưng không còn hàng.
```

### Bài 6. Lựa chọn công cụ

Xét ba tình huống:

1. Một truy vấn báo cáo cần tính doanh thu theo khách hàng một lần và không cần đọc lại kết quả trung gian.
2. Một job cần tạo danh sách ID, cập nhật/kiểm tra qua năm câu SQL, sau đó tự hủy dữ liệu khi commit.
3. Hai worker trên hai kết nối khác nhau cùng cần xem tiến độ và dữ liệu trung gian trong nhiều giờ.

**Gợi ý đáp án:**

1. Dùng CTE hoặc truy vấn con.
2. Trong PostgreSQL, dùng bảng tạm `ON COMMIT DROP` và giữ cùng kết nối, một transaction trong suốt năm câu.
3. Dùng bảng staging thông thường có `job_id`, chính sách phân quyền và dọn dữ liệu; bảng tạm theo phiên không phải cách chia sẻ dữ liệu giữa worker.

### Bài 7. Bảng tạm và ROLLBACK

Trong PostgreSQL:

```sql
BEGIN;

CREATE TEMP TABLE lesson_task_rollback (
    id INTEGER
);

INSERT INTO lesson_task_rollback (id)
VALUES (7);

ROLLBACK;
```

**Câu hỏi:** Bảng `lesson_task_rollback` còn không? **Đáp án:** Không, thao tác `CREATE TEMP TABLE` được thực hiện trong giao dịch vừa rollback nên việc tạo đối tượng cũng bị hủy. Tình huống khác với việc tạo bảng và commit trước, sau đó rollback một lần insert mới.

## 14. Những điểm cần ghi nhớ

- **Bảng tạm phục vụ dữ liệu trung gian**, nhưng vẫn là bảng SQL với cấu trúc, ràng buộc và chi phí quản lý.
- Trong **PostgreSQL**, bảng tạm chủ yếu gắn với **phiên kết nối tạo bảng**. Phiên khác không truy cập bảng tạm của phiên đó, ngay cả khi chung database và người dùng.
- **`ON COMMIT PRESERVE ROWS`** giữ những hàng đã commit; **`ON COMMIT DELETE ROWS`** xóa hàng nhưng giữ bảng; **`ON COMMIT DROP`** xóa cả bảng khi commit.
- **`ROLLBACK` khác `COMMIT`**: thay đổi chưa commit bị hủy; việc tạo bảng tạm trong một transaction của PostgreSQL cũng có thể bị rollback.
- **Auto-commit là kết thúc giao dịch, không phải kết thúc phiên.** Bảng `ON COMMIT DELETE ROWS` có thể mất hàng giữa hai câu SQL nếu không dùng giao dịch tường minh.
- **Connection pool có thể đổi kết nối vật lý** giữa các bước xử lý. Nếu dựa vào bảng tạm theo phiên, phải quản lý phạm vi kết nối và dọn bảng cẩn thận.
- **Các DBMS không thống nhất về bảng tạm:** MySQL dùng bảng tạm theo phiên; SQL Server có `#` và `##`; Oracle GTT có định nghĩa lâu dài nhưng dữ liệu riêng theo phiên/giao dịch; SQLite dùng schema `temp` theo kết nối.
- Khi chỉ cần kết quả trong một câu SQL, **CTE/truy vấn con** thường đơn giản hơn. Khi cần chia sẻ giữa nhiều phiên, **bảng staging thông thường** phù hợp hơn.

Khi thiết kế một quy trình với bảng tạm, hãy xác định thật rõ ba điều: **ai sở hữu kết nối**, **điểm nào sẽ `COMMIT` hoặc `ROLLBACK`**, và **khi nào định nghĩa bảng cùng dữ liệu phải được dọn**. Đó là cơ sở để tránh lỗi “không tìm thấy bảng”, “mất dữ liệu sau commit” hoặc vô tình dùng lại dữ liệu tạm của tác vụ cũ.

