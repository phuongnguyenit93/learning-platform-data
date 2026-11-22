# Phân biệt hàm SQL, hàm thủ tục và stored procedure trong Database SQL

Một ứng dụng quản lý đơn hàng thường phải thực hiện ba loại công việc: **tính giá sau giảm** từ các tham số đầu vào, **phân loại đơn hàng** theo nhiều quy tắc, và **xác nhận đơn** bằng cách thay đổi dữ liệu trong database. Cả ba đều có thể được đóng gói thành một đối tượng được đặt tên trong cơ sở dữ liệu, nhưng không nên gọi tất cả là “stored procedure”.

Ở mức SQL, cần phân biệt ít nhất ba khái niệm:

1. **Hàm SQL** (*SQL-language function*): hàm được định nghĩa bằng các câu SQL, ví dụ PostgreSQL `CREATE FUNCTION ... LANGUAGE SQL`; thường phù hợp để diễn đạt phép tính hoặc truy vấn trả một giá trị hay một tập hàng.
2. **Hàm thủ tục** (*procedural-language function*): vẫn là **function**, nhưng phần thân viết bằng ngôn ngữ thủ tục như **PL/pgSQL**, **PL/SQL**, **T-SQL** hoặc ngôn ngữ thủ tục được DBMS hỗ trợ. Nó có biến cục bộ, `IF`, vòng lặp, xử lý ngoại lệ và thường trả kết quả qua `RETURN`.
3. **Stored procedure** (*thủ tục lưu trữ*): đối tượng thao tác nghiệp vụ được gọi bằng cơ chế như `CALL` hoặc `EXEC`; thường phối hợp nhiều bước, có tham số `IN`/`OUT`/`INOUT` tùy DBMS, có thể sửa dữ liệu, và trong **một số hoàn cảnh** có thể thực hiện điều khiển giao dịch. Một stored procedure **không tự động là một transaction độc lập**, cũng không mặc nhiên tự commit.

**Điểm cốt lõi:** “SQL” và “thủ tục” ở hai nhóm hàm trên mô tả **ngôn ngữ viết phần thân**, còn “function” và “procedure” mô tả **loại đối tượng và hợp đồng gọi/trả kết quả**. Vì vậy, một **hàm viết bằng PL/pgSQL vẫn là stored function**, không trở thành stored procedure chỉ vì có `IF` hoặc `LOOP`.

Bài này thuộc **Database SQL → Thủ tục và hàm**. Các ví dụ chính dùng PostgreSQL, sau đó đối chiếu MySQL/MariaDB, SQL Server, Oracle và SQLite để tránh mang một cú pháp hoặc hạn chế từ DBMS này sang DBMS khác.

## 1. Bản đồ khái niệm: ba thứ dễ bị nhầm

~~~mermaid
flowchart TD
    A["Đóng gói logic ở tầng database"] --> B["Function"]
    A --> C["Stored procedure"]
    B --> D["SQL-language function\nVí dụ: LANGUAGE SQL"]
    B --> E["Procedural-language function\nVí dụ: LANGUAGE plpgsql"]
    D --> F["Được dùng trong biểu thức\nhoặc FROM khi trả bảng"]
    E --> F
    C --> G["Gọi bằng CALL / EXEC\nThực hiện quy trình nhiều bước"]
~~~

Với PostgreSQL:

~~~sql
-- Hàm viết bằng SQL:
CREATE FUNCTION ... RETURNS numeric
LANGUAGE sql AS $$ SELECT ... $$;

-- Hàm viết bằng ngôn ngữ thủ tục PL/pgSQL:
CREATE FUNCTION ... RETURNS text
LANGUAGE plpgsql AS $$
BEGIN
    IF ... THEN
        RETURN ...;
    END IF;
END;
$$;

-- Stored procedure viết bằng PL/pgSQL:
CREATE PROCEDURE ...
LANGUAGE plpgsql AS $$
BEGIN
    UPDATE ...;
END;
$$;
~~~

Mẫu ở trên chỉ thể hiện **hình dạng cú pháp**. Phần thực hành có các câu hoàn chỉnh chạy được.

### 1.1. Bảng phân biệt nhanh

| Tiêu chí | Hàm SQL | Hàm thủ tục | Stored procedure |
| --- | --- | --- | --- |
| Loại đối tượng | **Function** | **Function** | **Procedure** |
| Ngôn ngữ phần thân | SQL | PL/pgSQL, PL/SQL, T-SQL… tùy DBMS | Ngôn ngữ procedure mà DBMS hỗ trợ |
| Mục tiêu phổ biến | Tính toán, đóng gói SELECT, trả scalar hoặc tập hàng | Tính toán nhiều nhánh, xử lý logic có biến, có thể đọc/ghi tùy DBMS | Điều phối quy trình và nhiều thao tác |
| Cách gọi PostgreSQL | `SELECT f(...)`, trong biểu thức hoặc `FROM f(...)` | Tương tự function | `CALL p(...)` |
| Trả kết quả | Kiểu khai báo trong `RETURNS` | Kiểu khai báo trong `RETURNS` | Có thể dùng `OUT`/`INOUT` hoặc cơ chế riêng, tùy DBMS |
| `IF`, `LOOP` nội tại | Không dùng trực tiếp như PL/pgSQL; thường dùng `CASE`, CTE | Có | Có |
| Ghi dữ liệu | **Phụ thuộc DBMS và tính chất hàm**; không đồng nghĩa read-only | **Phụ thuộc DBMS**; PostgreSQL VOLATILE function có thể ghi | Thường dùng cho DML nhiều bước |
| `COMMIT`/`ROLLBACK` bên trong | Không dùng trong PostgreSQL function | Không dùng trong PostgreSQL function | Chỉ trong điều kiện được DBMS cho phép |
| Phù hợp trong `WHERE`/`SELECT` | Có khi là function trả giá trị hợp lệ | Có khi là function trả giá trị hợp lệ | **Không** dùng trực tiếp như biểu thức SQL thông thường |

Bảng này mô tả **định hướng thiết kế**, không phải hạn chế SQL chuẩn cố định trên mọi hệ. Ví dụ SQL Server hạn chế UDF sửa trạng thái database; PostgreSQL cho phép một số function thực hiện DML; Oracle có hạn chế với function được gọi từ câu SQL.

### 1.2. “Stored function” và “hàm thủ tục” không phải hai đối tượng đối lập

Một stored function là hàm **được định nghĩa và lưu trong database catalog**. Nó có thể có phần thân SQL hoặc phần thân procedural. Vì vậy:

~~~text
Stored function
├── PostgreSQL LANGUAGE SQL
├── PostgreSQL LANGUAGE plpgsql
├── Oracle PL/SQL FUNCTION
├── SQL Server scalar/table-valued function
└── MySQL stored FUNCTION
~~~

Những dạng này đều thuộc họ **function** nhưng có khả năng, cú pháp và giới hạn khác nhau. **Stored procedure** là họ đối tượng khác, dù cả hai cùng “stored” trong database.

## 2. Nhìn từ người gọi: hàm tham gia biểu thức, thủ tục là một lời gọi tác vụ

### 2.1. Function trong SELECT

~~~sql
SELECT
    id,
    tong_tien,
    round(tong_tien * 0.9, 2) AS sau_giam_10_phan_tram
FROM don_hang;
~~~

Nếu công thức tính sau giảm được đóng gói trong function:

~~~sql
SELECT
    id,
    tong_tien,
    tinh_gia_sau_giam(tong_tien, 10) AS sau_giam
FROM don_hang;
~~~

Về mặt cú pháp, function xuất hiện **bên trong SELECT**, tương tự một biểu thức trả giá trị. Nó cũng có thể được dùng trong `ORDER BY`, `WHERE` hoặc những vị trí SQL cho phép, tùy kiểu trả về và ràng buộc.

### 2.2. Procedure là lời gọi độc lập

~~~sql
CALL xac_nhan_don(101);
~~~

Ta không thể coi stored procedure PostgreSQL như một hàm scalar:

~~~sql
-- Không hợp lệ nếu xac_nhan_don là PROCEDURE:
-- SELECT xac_nhan_don(101);
-- SELECT * FROM don_hang WHERE id = xac_nhan_don(101);
~~~

Cú pháp `CALL` yêu cầu hệ quản trị thực hiện **thủ tục như một thao tác**. Nếu procedure cần trả dữ liệu, DBMS có cơ chế riêng: tham số OUT/INOUT, tập kết quả, cursor hoặc các đối tượng trung gian, không phải tự động trả một giá trị duy nhất như scalar function.

### 2.3. Function trả bảng có thể xuất hiện ở FROM

Không phải function nào cũng chỉ trả **một ô**. PostgreSQL và các hệ khác có kiểu **table-valued/set-returning function**:

~~~sql
SELECT *
FROM tim_don_theo_trang_thai('MOI');
~~~

Ở đây function tham gia nguồn dữ liệu của `FROM`. Nó vẫn là function, không phải procedure chỉ vì trả nhiều hàng.

## 3. Bộ dữ liệu thực hành PostgreSQL

Để ví dụ tự chứa, tạo một schema riêng trong **database thử nghiệm**. Cần quyền `CREATE` phù hợp. Đừng chạy trên database sản xuất nếu chưa kiểm soát tên đối tượng và quyền.

~~~sql
CREATE SCHEMA bai335;

CREATE TABLE bai335.don_hang (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ten_khach TEXT NOT NULL,
    tong_tien NUMERIC(12,2) NOT NULL CHECK (tong_tien >= 0),
    trang_thai TEXT NOT NULL DEFAULT 'MOI'
        CHECK (trang_thai IN ('MOI', 'DA_XAC_NHAN', 'DA_HUY')),
    tao_luc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO bai335.don_hang (ten_khach, tong_tien, trang_thai)
VALUES
    ('An',   250000, 'MOI'),
    ('Bình', 780000, 'MOI'),
    ('Chi', 1450000, 'DA_XAC_NHAN'),
    ('Dung', 90000, 'MOI');

SELECT id, ten_khach, tong_tien, trang_thai
FROM bai335.don_hang
ORDER BY id;
~~~

Các ID do database sinh ra; **không giả định thứ tự bắt đầu bằng 1** khi chạy trên một database đã có lịch sử hoặc dùng sequence khác. Nếu chạy từ schema mới và identity mặc định, chúng thường là 1–4.

| Cột | Vai trò |
| --- | --- |
| `id` | Khóa chính do database sinh |
| `ten_khach` | Dữ liệu đầu vào |
| `tong_tien` | Giá trị được tính/kiểm tra bằng hàm |
| `trang_thai` | Giá trị procedure có thể cập nhật |
| `tao_luc` | Thời điểm do default database gán |

Phần thực hành sử dụng tên đầy đủ `bai335.don_hang` để không phụ thuộc `search_path`.

**Dọn sau bài học:** trên database thử nghiệm và sau khi đã xác nhận schema này chỉ chứa dữ liệu demo, có thể dùng `DROP SCHEMA bai335 CASCADE;` để xóa toàn bộ đối tượng bài học. Lệnh ấy **xóa dữ liệu**; không dùng trên schema không thuộc bài thực hành.

## 4. Hàm SQL: đóng gói biểu thức bằng LANGUAGE SQL

Hàm đầu tiên tính giá sau giảm với tỷ lệ phần trăm.

~~~sql
CREATE FUNCTION bai335.tinh_gia_sau_giam(
    p_gia NUMERIC,
    p_ty_le NUMERIC
)
RETURNS NUMERIC
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT round(p_gia * (1 - p_ty_le / 100), 2);
$$;
~~~

Gọi thử:

~~~sql
SELECT bai335.tinh_gia_sau_giam(500000, 10) AS gia_moi;

SELECT
    id,
    ten_khach,
    tong_tien,
    bai335.tinh_gia_sau_giam(tong_tien, 15) AS gia_sau_giam_15
FROM bai335.don_hang
ORDER BY id;
~~~

Kết quả phép tính đầu là **450000.00**; kết quả các dòng tùy `tong_tien` của từng đơn.

### 4.1. Giải thích từng phần

- `CREATE FUNCTION bai335.tinh_gia_sau_giam(...)` tạo một function trong schema `bai335`.
- `p_gia NUMERIC, p_ty_le NUMERIC` là hai tham số đầu vào.
- `RETURNS NUMERIC` khai báo kiểu kết quả.
- `LANGUAGE sql` chỉ định **phần thân dùng ngôn ngữ SQL**.
- `AS $$ ... $$` bao bọc phần thân bằng dollar-quoted string, tránh phải escape nhiều dấu nháy đơn.
- `IMMUTABLE` là lời khai với planner rằng cùng đầu vào cho cùng kết quả, không phụ thuộc dữ liệu/biến động bên ngoài.
- `STRICT` trong PostgreSQL làm function **không thực thi thân hàm khi đối số có NULL**; kết quả là NULL.

Hàm này **không tự kiểm tra tỷ lệ 0–100**. Nó chỉ thực hiện công thức. Nếu ứng dụng cần từ chối giá âm hoặc tỷ lệ không hợp lệ, phải bổ sung quy tắc, ví dụ dùng procedural function với `RAISE EXCEPTION`.

### 4.2. Một function không cần biến/IF nếu biểu thức đã đủ

Với bài toán tính giá có một công thức đơn giản, viết `LANGUAGE sql` thường ngắn gọn và gần với SQL thông thường:

~~~sql
SELECT round(500000 * (1 - 10 / 100.0), 2);
~~~

Hàm giúp **tái sử dụng, đặt tên quy tắc và cấp quyền phù hợp**. Tuy nhiên, một function có nghĩa vụ bảo trì: đổi công thức cần quản lý phiên bản và kiểm tra mọi chỗ gọi.

### 4.3. IMMUTABLE, STABLE, VOLATILE là các cam kết với planner PostgreSQL

| Phân loại | Ý nghĩa khái quát | Ví dụ |
| --- | --- | --- |
| `IMMUTABLE` | Cùng tham số luôn cho cùng kết quả, không phụ thuộc thay đổi bên ngoài | Phép toán số học thuần |
| `STABLE` | Kết quả có thể dựa vào trạng thái database nhưng ổn định theo phạm vi snapshot của statement phù hợp | Đọc bảng tham chiếu trong function |
| `VOLATILE` | Kết quả/hiệu ứng có thể thay đổi theo mỗi lần gọi; cần đánh giá thận trọng | Hàm sinh số ngẫu nhiên, DML, gọi sequence |

**Không khai báo IMMUTABLE chỉ để ép tối ưu.** Nếu function thật ra đọc bảng giá có thể đổi theo thời gian, khai báo sai có thể khiến planner cache/fold kết quả theo cách không còn đúng nghiệp vụ.

### 4.4. SQL-language function không đồng nghĩa mọi function luôn read-only

Trong PostgreSQL, `LANGUAGE SQL` function có thể gồm nhiều câu SQL trong những hoàn cảnh hợp lệ, và function được khai báo `VOLATILE` có thể thực hiện thao tác ghi trong giới hạn của DBMS. Nhãn **SQL-language** chỉ cho biết **cách viết thân**, không phải “bắt buộc thuần và không có side effect”.

Ngược lại, một hàm viết bằng `plpgsql` cũng có thể **hoàn toàn thuần**, chỉ tính số và trả kết quả. Không đánh đồng **ngôn ngữ** với **mức độ thay đổi trạng thái**.

## 5. Hàm SQL trả một tập hàng: RETURNS TABLE

PostgreSQL hỗ trợ `RETURNS TABLE(...)`, phù hợp để đóng gói truy vấn trả nhiều dòng.

~~~sql
CREATE FUNCTION bai335.tim_don_theo_trang_thai(
    p_trang_thai TEXT
)
RETURNS TABLE (
    id BIGINT,
    ten_khach TEXT,
    tong_tien NUMERIC,
    tao_luc TIMESTAMPTZ
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        d.id,
        d.ten_khach,
        d.tong_tien,
        d.tao_luc
    FROM bai335.don_hang AS d
    WHERE d.trang_thai = p_trang_thai;
$$;
~~~

Cách gọi:

~~~sql
SELECT *
FROM bai335.tim_don_theo_trang_thai('MOI')
ORDER BY id;
~~~

Kết quả ban đầu gồm những đơn trạng thái MOI (An, Bình, Dung); thứ tự được xác định bởi **ORDER BY bên ngoài**.

### 5.1. Vì sao dùng FROM?

Function trả **nhiều hàng, nhiều cột**. `FROM bai335.tim_don_theo_trang_thai('MOI')` cho phép hệ quản trị xem đầu ra function như một nguồn hàng:

~~~sql
SELECT ten_khach, tong_tien
FROM bai335.tim_don_theo_trang_thai('MOI')
WHERE tong_tien >= 200000
ORDER BY tong_tien DESC;
~~~

Một số SQL-language functions có thể được planner **inline** vào truy vấn gọi khi thỏa điều kiện, giúp tối ưu hóa xuyên qua ranh giới function. Nhưng **không bảo đảm mọi function được inline**, nhất là khi có thuộc tính, cấu trúc hoặc hành vi không đủ điều kiện. Phải đọc execution plan thực tế.

### 5.2. Function trả bảng không đồng nghĩa view

Một `VIEW` thường cố định cấu trúc truy vấn và được gọi như bảng:

~~~sql
SELECT * FROM bai335.view_don_moi;
~~~

Một table-valued function có thể **nhận tham số**:

~~~sql
SELECT * FROM bai335.tim_don_theo_trang_thai('MOI');
SELECT * FROM bai335.tim_don_theo_trang_thai('DA_XAC_NHAN');
~~~

Nó gần với “truy vấn có tham số”. Nếu không cần logic tái sử dụng hoặc tham số, view hoặc SQL trực tiếp có thể đơn giản hơn.

## 6. Hàm thủ tục: function viết bằng PL/pgSQL

Giả sử cần xếp loại đơn theo số tiền:

- Dưới 200.000: `THUONG`.
- Từ 200.000 đến dưới 1.000.000: `TIEU_CHUAN`.
- Từ 1.000.000 trở lên: `VIP`.
- Nếu tham số là NULL: trả NULL.
- Không nhận giá âm.

PL/pgSQL diễn đạt điều kiện bằng biến, `IF`, `ELSIF` và `RAISE EXCEPTION`:

~~~sql
CREATE FUNCTION bai335.xep_hang_don(
    p_tong_tien NUMERIC
)
RETURNS TEXT
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    IF p_tong_tien IS NULL THEN
        RETURN NULL;
    ELSIF p_tong_tien < 0 THEN
        RAISE EXCEPTION 'Tong tien khong duoc am: %', p_tong_tien;
    ELSIF p_tong_tien >= 1000000 THEN
        RETURN 'VIP';
    ELSIF p_tong_tien >= 200000 THEN
        RETURN 'TIEU_CHUAN';
    ELSE
        RETURN 'THUONG';
    END IF;
END;
$$;
~~~

Gọi:

~~~sql
SELECT bai335.xep_hang_don(1500000) AS xep_hang;

SELECT
    id,
    ten_khach,
    tong_tien,
    bai335.xep_hang_don(tong_tien) AS nhom_don
FROM bai335.don_hang
ORDER BY id;
~~~

### 6.1. Tại sao đây vẫn là function?

Đối tượng được tạo bằng `CREATE FUNCTION`, có `RETURNS TEXT` và được gọi trong `SELECT`. Nó **không trở thành stored procedure** vì chứa `BEGIN ... END` hoặc `IF`.

Cặp sau thể hiện ranh giới:

~~~sql
SELECT bai335.xep_hang_don(500000); -- Function.
-- CALL bai335.xep_hang_don(500000); -- Sai loại đối tượng.
~~~

### 6.2. Biến cục bộ với DECLARE

Ví dụ tính chiết khấu theo loại khách hàng:

~~~sql
CREATE FUNCTION bai335.tinh_thanh_tien(
    p_gia NUMERIC,
    p_loai_khach TEXT
)
RETURNS NUMERIC
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v_ty_le NUMERIC := 0;
    v_ket_qua NUMERIC;
BEGIN
    IF p_gia IS NULL THEN
        RETURN NULL;
    END IF;

    IF p_gia < 0 THEN
        RAISE EXCEPTION 'Gia phai >= 0';
    END IF;

    IF p_loai_khach = 'VIP' THEN
        v_ty_le := 15;
    ELSIF p_loai_khach = 'THAN_THIET' THEN
        v_ty_le := 5;
    ELSE
        v_ty_le := 0;
    END IF;

    v_ket_qua := round(p_gia * (1 - v_ty_le / 100), 2);
    RETURN v_ket_qua;
END;
$$;
~~~

Ví dụ:

~~~sql
SELECT bai335.tinh_thanh_tien(800000, 'VIP');        -- 680000.00
SELECT bai335.tinh_thanh_tien(800000, 'THAN_THIET'); -- 760000.00
SELECT bai335.tinh_thanh_tien(800000, 'KHAC');      -- 800000.00
~~~

**Từ khóa quan trọng:** `DECLARE` khai báo biến; `:=` gán giá trị; `IF/ELSIF/ELSE` điều kiện; `RETURN` kết thúc và trả giá trị của function.

### 6.3. Có thể viết bằng CASE trong SQL không?

Nhiều quy tắc nhánh đơn giản cũng viết được trong một function LANGUAGE SQL bằng `CASE`:

~~~sql
CREATE FUNCTION bai335.xep_hang_don_sql(
    p_tong_tien NUMERIC
)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE
        WHEN p_tong_tien IS NULL THEN NULL
        WHEN p_tong_tien >= 1000000 THEN 'VIP'
        WHEN p_tong_tien >= 200000 THEN 'TIEU_CHUAN'
        ELSE 'THUONG'
    END;
$$;
~~~

Ví dụ này **không ném lỗi khi giá âm**, khác function PL/pgSQL phía trên. Hai hàm có thể có cùng dạng đầu ra nhưng **khác hợp đồng nghiệp vụ**. Hãy chọn LANGUAGE SQL nếu biểu thức SQL diễn đạt rõ; dùng PL/pgSQL khi cần kiểm soát lỗi, biến, vòng lặp hoặc nhiều bước.

## 7. Hàm PL/pgSQL đọc bảng: SELECT ... INTO

Một function có thể đọc dữ liệu database rồi trả kết quả:

~~~sql
CREATE FUNCTION bai335.lay_tong_don(
    p_don_id BIGINT
)
RETURNS NUMERIC
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_tong NUMERIC;
BEGIN
    SELECT d.tong_tien
      INTO v_tong
    FROM bai335.don_hang AS d
    WHERE d.id = p_don_id;

    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    RETURN v_tong;
END;
$$;
~~~

Gọi:

~~~sql
SELECT bai335.lay_tong_don(1);
~~~

Với ID không tồn tại, ví dụ trả NULL. Nhưng cần hiểu rõ:

- Trong PL/pgSQL, `SELECT ... INTO v_tong` là **gán kết quả SELECT vào biến**, không phải cú pháp tạo bảng `SELECT INTO` ở những ngữ cảnh SQL khác.
- `FOUND` phản ánh tình trạng của thao tác SQL gần nhất theo quy tắc PL/pgSQL.
- `STABLE` phù hợp khi function chỉ đọc dữ liệu theo snapshot của statement và không ghi; **không** có nghĩa bảng sẽ không thay đổi giữa các transaction.
- Truy vấn bảng theo từng ID qua function trong hàng triệu dòng có thể phát sinh chi phí lặp lại; với báo cáo tập hợp, JOIN trực tiếp thường rõ ràng và dễ tối ưu hơn.

### 7.1. SELECT INTO và xử lý nhiều hàng

Nếu câu SELECT có thể trả nhiều hàng, một function scalar cần quy tắc chọn hàng rõ ràng: `ORDER BY ... LIMIT 1`, ràng buộc UNIQUE hoặc `SELECT ... INTO STRICT` để yêu cầu đúng một hàng khi phù hợp. Không để ngẫu nhiên lấy một hàng rồi gọi đó là kết quả nghiệp vụ.

## 8. Hàm thủ tục với vòng lặp và RETURN NEXT

PL/pgSQL hỗ trợ vòng lặp và trả nhiều hàng:

~~~sql
CREATE FUNCTION bai335.tao_day_so(
    p_tu INTEGER,
    p_den INTEGER
)
RETURNS SETOF INTEGER
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
    v_i INTEGER;
BEGIN
    IF p_tu IS NULL OR p_den IS NULL THEN
        RETURN;
    END IF;

    IF p_den - p_tu > 100 THEN
        RAISE EXCEPTION 'Khoang qua lon';
    END IF;

    FOR v_i IN p_tu..p_den LOOP
        RETURN NEXT v_i;
    END LOOP;

    RETURN;
END;
$$;
~~~

Gọi:

~~~sql
SELECT *
FROM bai335.tao_day_so(3, 6);
~~~

Kết quả: **3, 4, 5, 6** theo quy tắc ví dụ. `RETURN NEXT` bổ sung hàng cho tập kết quả; `RETURN` kết thúc function.

**Lưu ý về thiết kế:** ví dụ này chỉ dạy cú pháp procedural function. Nếu chỉ cần tạo chuỗi số, PostgreSQL có `generate_series(3,6)` hiệu quả và rõ hơn. Không chuyển một phép toán tập hợp vốn có sẵn trong SQL sang vòng lặp thủ công nếu không có lý do.

## 9. Stored procedure: đóng gói quy trình nhiều bước

Ta định nghĩa procedure xác nhận đơn từ `MOI` sang `DA_XAC_NHAN`. Quy trình chỉ hợp lệ khi đúng một đơn đang ở trạng thái MOI.

~~~sql
CREATE PROCEDURE bai335.xac_nhan_don(
    IN p_don_id BIGINT
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_so_hang BIGINT;
BEGIN
    UPDATE bai335.don_hang
    SET trang_thai = 'DA_XAC_NHAN'
    WHERE id = p_don_id
      AND trang_thai = 'MOI';

    GET DIAGNOSTICS v_so_hang = ROW_COUNT;

    IF v_so_hang <> 1 THEN
        RAISE EXCEPTION
            'Don % khong ton tai hoac khong o trang thai MOI',
            p_don_id;
    END IF;
END;
$$;
~~~

Gọi trong PostgreSQL:

~~~sql
CALL bai335.xac_nhan_don(1);

SELECT id, trang_thai
FROM bai335.don_hang
WHERE id = 1;
~~~

Nếu ID 1 là đơn MOI, câu CALL chuyển trạng thái sang DA_XAC_NHAN. Nếu gọi lại với cùng ID, `WHERE ... trang_thai='MOI'` không còn khớp nên procedure ném lỗi.

### 9.1. Vì sao dùng CREATE PROCEDURE?

Hợp đồng của thao tác là **thực hiện chuyển trạng thái nghiệp vụ**, không phải “tính một giá trị có thể lồng vào SELECT”. Người gọi yêu cầu một tác vụ:

~~~sql
CALL bai335.xac_nhan_don(1);
~~~

Thay vì:

~~~sql
SELECT bai335.xac_nhan_don(1); -- Sai: đối tượng là PROCEDURE.
~~~

Procedure có thể đọc, kiểm tra, ghi nhiều bảng, ghi audit, hoặc gọi các routine khác. Tuy nhiên, function PL/pgSQL ở PostgreSQL cũng **có thể** thực hiện DML; sự khác biệt chính là **hợp đồng loại đối tượng/cách gọi và khả năng điều khiển giao dịch trong điều kiện được cho phép**, không phải “function tuyệt đối không ghi, procedure tuyệt đối ghi”.

### 9.2. Tính nguyên tử không tự động đến từ tên PROCEDURE

Procedure trên **không chứa COMMIT**. Nếu ứng dụng chạy:

~~~sql
BEGIN;

CALL bai335.xac_nhan_don(2);

-- Có thể kiểm tra thêm những việc khác.
ROLLBACK;
~~~

thì việc xác nhận đơn 2 bị **hủy**. Nếu thay ROLLBACK bằng COMMIT, thao tác được xác nhận.

**CALL không mặc nhiên COMMIT khi nó nằm trong transaction tường minh của caller.** Trong chế độ autocommit, việc statement CALL kết thúc thành công có thể dẫn đến commit theo quản lý transaction của client/server. Ranh giới thực sự phụ thuộc ngữ cảnh gọi và DBMS.

### 9.3. GET DIAGNOSTICS và số hàng ảnh hưởng

`GET DIAGNOSTICS v_so_hang = ROW_COUNT` trong PL/pgSQL lấy số hàng bị ảnh hưởng bởi câu SQL trước đó theo ngữ nghĩa PostgreSQL. Nó giúp phát hiện trường hợp gọi sai ID hoặc trạng thái.

Không kiểm tra số hàng có thể khiến procedure trả “thành công” dù UPDATE không sửa dòng nào. Trong quy trình nghiệp vụ, **0 hàng bị thay đổi** cần được định nghĩa: lỗi, không có gì để làm, hoặc idempotent success.

## 10. Trả ID từ procedure bằng INOUT trong PostgreSQL

Không phải procedure “không bao giờ trả dữ liệu”. PostgreSQL hỗ trợ các chế độ tham số, trong đó có `INOUT`.

~~~sql
CREATE PROCEDURE bai335.them_don(
    IN p_ten_khach TEXT,
    IN p_tong_tien NUMERIC,
    INOUT p_id BIGINT
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_tong_tien IS NULL OR p_tong_tien < 0 THEN
        RAISE EXCEPTION 'Tong tien khong hop le';
    END IF;

    INSERT INTO bai335.don_hang (ten_khach, tong_tien)
    VALUES (p_ten_khach, p_tong_tien)
    RETURNING id INTO p_id;
END;
$$;
~~~

Gọi trong phiên PostgreSQL hỗ trợ cú pháp này:

~~~sql
CALL bai335.them_don('Hà', 350000, NULL);
~~~

Câu CALL có thể trả một hàng chứa `p_id` thực tế được sinh. `INOUT` là tham số vừa nhận giá trị đầu vào vừa có thể được gán giá trị đầu ra; ở đây đầu vào ban đầu là NULL và sẽ được thay bằng ID mới.

**Phân biệt:**

- Function scalar có `RETURNS BIGINT`; thường gọi từ `SELECT f(...)`.
- Procedure dùng `INOUT p_id` (hoặc `OUT` theo phiên bản/cơ chế thích hợp), được gọi bằng `CALL`.
- SQL Server, Oracle và MySQL có cách bind tham số OUTPUT/OUT khác nhau.

Nếu muốn một API “thêm đơn và nhận ID”, ở PostgreSQL nhiều trường hợp có thể **không cần routine nào cả**:

~~~sql
INSERT INTO bai335.don_hang (ten_khach, tong_tien)
VALUES ('Khanh', 350000)
RETURNING id;
~~~

Đây thường là giải pháp đơn giản khi nghiệp vụ chỉ có một INSERT và cần nhận khóa tự sinh.

## 11. Function cũng có thể ghi dữ liệu trong PostgreSQL

Một lối hiểu cứng nhắc là “function = chỉ SELECT, procedure = có UPDATE”. Điều đó **không đúng cho mọi DBMS**.

Ví dụ PostgreSQL cho phép một `VOLATILE` PL/pgSQL function chèn đơn và trả ID:

~~~sql
CREATE FUNCTION bai335.them_don_function(
    p_ten TEXT,
    p_tong NUMERIC
)
RETURNS BIGINT
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
    v_id BIGINT;
BEGIN
    INSERT INTO bai335.don_hang (ten_khach, tong_tien)
    VALUES (p_ten, p_tong)
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$;
~~~

Gọi:

~~~sql
SELECT bai335.them_don_function('Lan', 410000) AS id_moi;
~~~

Đây vẫn là **function** dù có DML. Nhưng có những hệ quả quan trọng:

1. Việc gọi từ SELECT **có side effect**; một số người đọc câu SQL có thể không ngờ nó chèn hàng.
2. Gọi trên mỗi hàng của một SELECT lớn có thể thực hiện nhiều thao tác ghi.
3. Không được đánh dấu function như `IMMUTABLE` hoặc `STABLE` khi thực hiện DML.
4. Việc phát sinh lỗi phải được xử lý theo transaction caller; function không tự COMMIT độc lập.
5. SQL Server UDF lại có hạn chế khác về thao tác thay đổi trạng thái database; không mang ví dụ PostgreSQL này sang T-SQL.

**Khuyến nghị thiết kế:** nếu hành vi chủ đạo là **ra lệnh sửa trạng thái**, procedure hoặc câu DML tường minh thường dễ hiểu hơn. Việc PostgreSQL *cho phép* function ghi dữ liệu không có nghĩa *nên* viết mọi nghiệp vụ thay đổi trạng thái dưới dạng SELECT function.

## 12. RETURN trong function khác kết quả của procedure

### 12.1. Scalar function

~~~sql
SELECT bai335.xep_hang_don(1500000);
~~~

Function được khai báo `RETURNS TEXT` nên một lần đánh giá hợp lệ trả một giá trị TEXT (hoặc NULL).

### 12.2. Set-returning/table-valued function

~~~sql
SELECT *
FROM bai335.tim_don_theo_trang_thai('MOI');
~~~

Function trả một quan hệ có **nhiều hàng, nhiều cột**. Kết quả này vẫn thuộc loại function.

### 12.3. Procedure có OUT/INOUT parameter

~~~sql
CALL bai335.them_don('Hải', 225000, NULL);
~~~

Đầu ra có thể nằm ở tham số khai báo, được client nhận theo cơ chế CALL/driver. Procedure cũng có thể chỉ hoàn thành tác vụ mà không trả hàng.

### 12.4. “Không có RETURNS” không có nghĩa không có output

SQL Server procedure có thể trả nhiều result sets bằng các câu SELECT trong thân và cung cấp tham số OUTPUT hoặc return status. Oracle procedure có OUT parameters/cursor. PostgreSQL procedure không trả result sets tùy ý bằng SELECT trần theo cách SQL Server; nó sử dụng OUT/INOUT và các phương án như cursor theo quy tắc riêng.

Không dựa vào từ khóa `RETURN` đơn lẻ để kết luận một routine thuộc function hay procedure. Hãy xem **định nghĩa đối tượng** (`CREATE FUNCTION` hay `CREATE PROCEDURE`), **kiểu kết quả** và **cơ chế gọi**.

## 13. Quy trình nhiều thao tác: function thủ tục hay stored procedure?

Hãy tưởng tượng nghiệp vụ **tạo đơn và ghi nhật ký**. Cần:

1. Kiểm tra số tiền không âm.
2. Chèn đơn hàng.
3. Ghi nhật ký tạo đơn.
4. Trả ID đơn vừa tạo.
5. Nếu một bước bắt buộc lỗi, không để dữ liệu lưu dở dang.

Có thể dùng một PostgreSQL procedure:

~~~sql
CREATE TABLE bai335.nhat_ky_don (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    don_hang_id BIGINT NOT NULL REFERENCES bai335.don_hang(id),
    hanh_dong TEXT NOT NULL,
    tao_luc TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE PROCEDURE bai335.tao_don_co_nhat_ky(
    IN p_ten TEXT,
    IN p_tong NUMERIC,
    INOUT p_id BIGINT
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_ten IS NULL OR btrim(p_ten) = ''
       OR p_tong IS NULL OR p_tong < 0 THEN
        RAISE EXCEPTION 'Du lieu don hang khong hop le';
    END IF;

    INSERT INTO bai335.don_hang (ten_khach, tong_tien)
    VALUES (p_ten, p_tong)
    RETURNING id INTO p_id;

    INSERT INTO bai335.nhat_ky_don (don_hang_id, hanh_dong)
    VALUES (p_id, 'TAO_DON');
END;
$$;
~~~

Chạy trong transaction:

~~~sql
BEGIN;
CALL bai335.tao_don_co_nhat_ky('Mai', 620000, NULL);

-- Quan sát các thay đổi trong transaction này.
SELECT id, ten_khach, tong_tien
FROM bai335.don_hang
WHERE ten_khach = 'Mai';

SELECT n.id, n.don_hang_id, n.hanh_dong
FROM bai335.nhat_ky_don AS n
JOIN bai335.don_hang AS d ON d.id = n.don_hang_id
WHERE d.ten_khach = 'Mai';

ROLLBACK;
~~~

Vì không COMMIT, các INSERT do procedure thực hiện đều bị rollback. Nếu thay bằng COMMIT sau khi kiểm tra, cả đơn và log được xác nhận trong một transaction.

### 13.1. Tại sao không viết một function scalar để làm tất cả?

PostgreSQL có thể viết một `VOLATILE` function tương tự và `SELECT` ra ID. Nhưng dùng procedure cho một quy trình thay đổi nhiều bảng thường làm **ý định thao tác** rõ ràng. Khi chức năng này cần dùng trong biểu thức SELECT của nhiều hàng, side effect của function có thể tạo sự ngạc nhiên hoặc được thực thi nhiều lần không như kỳ vọng.

Tuy nhiên, đây là **khuyến nghị phong cách/kiến trúc**, không phải quy tắc cấm function PL/pgSQL ghi dữ liệu trong PostgreSQL.

### 13.2. Procedure có tự tạo atomicity giữa hai INSERT không?

Hai câu INSERT nằm trong **cùng transaction** của CALL; nếu một lỗi không được xử lý làm statement/transaction thất bại, không nên có một “nửa thành công” được commit mà không kiểm tra. Nhưng stored procedure **không tự đảm bảo an toàn ở mọi DBMS** nếu bên trong có xử lý exception, explicit COMMIT, autonomous transaction hoặc thao tác ngoài database. Phải đọc định nghĩa transaction và cách xử lý lỗi cụ thể.

## 14. Transaction control: khác biệt then chốt nhưng có điều kiện

Không có phát biểu đúng chung cho mọi DBMS kiểu “procedure luôn COMMIT được” hoặc “function luôn mở transaction mới”. Cần xem từng hệ.

### 14.1. PostgreSQL function không dùng COMMIT/ROLLBACK bên trong

Một PostgreSQL `LANGUAGE plpgsql` function bình thường **không thể tự ý kết thúc transaction caller** bằng `COMMIT` hoặc `ROLLBACK`. Function thực thi trong transaction chứa câu SQL gọi nó.

Vì vậy:

~~~sql
BEGIN;
SELECT bai335.them_don_function('Nhã', 500000);
ROLLBACK;
~~~

không lưu hàng mới vĩnh viễn: việc INSERT bên trong function bị rollback cùng transaction.

### 14.2. PostgreSQL procedure có thể điều khiển transaction trong hoàn cảnh thích hợp

PostgreSQL hỗ trợ transaction control trong procedure được gọi bằng `CALL` (và trong DO block) **chỉ khi đáp ứng các ràng buộc** về ngữ cảnh gọi. Điển hình, phải là **CALL cấp trên được phép điều khiển transaction**, không nằm trong một transaction block tường minh do client bắt đầu; chuỗi gọi nested CALL/DO cũng phải đáp ứng các hạn chế. Procedure có thuộc tính `SECURITY DEFINER` hoặc mệnh đề `SET` gắn với định nghĩa procedure có các giới hạn về transaction control; không được kết thúc transaction bên trong khối còn subtransaction từ `EXCEPTION`.

Ví dụ **minh họa hành vi**, không chạy cùng lúc với các ví dụ transaction bên trên:

~~~sql
-- Chỉ chạy khi được phép CALL ở ngữ cảnh top-level và DBMS cho phép:
CREATE PROCEDURE bai335.moc_giao_dich_demo()
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO bai335.don_hang (ten_khach, tong_tien)
    VALUES ('GiaoDichTuThuTuc', 100000);

    COMMIT;
END;
$$;

-- Gọi ở top-level, KHÔNG ở giữa BEGIN ... COMMIT tường minh:
-- CALL bai335.moc_giao_dich_demo();
~~~

**Không chạy CALL minh họa này trong một transaction đang mở** nếu muốn COMMIT bên trong hoạt động. Và không nên thiết kế procedure tự COMMIT khi caller cần một chuỗi cập nhật nhiều bước phải nguyên tử; procedure lúc ấy sẽ phá vỡ quyền kiểm soát transaction của caller.

### 14.3. MySQL procedure và SQL Server procedure

MySQL stored procedures có thể dùng các câu điều khiển giao dịch phù hợp trong những ngữ cảnh được hỗ trợ; MySQL **stored functions** bị hạn chế đối với transaction control và nhiều thao tác khác.

SQL Server stored procedures thường thực thi trong transaction của caller hoặc quản lý BEGIN TRANSACTION/COMMIT/ROLLBACK nếu thiết kế như vậy. Khi một stored procedure gọi trong transaction của caller, việc tự COMMIT/ROLLBACK phải xét `@@TRANCOUNT`, `XACT_STATE()` và hợp đồng sở hữu transaction. Không mặc định procedure nào cũng tự COMMIT.

### 14.4. Oracle

Oracle PL/SQL procedure và function có cú pháp/khả năng transaction riêng. Một function được gọi từ một SQL query chịu những hạn chế quan trọng về DML/transaction side effects. Oracle còn có **autonomous transaction** nhưng đó là cơ chế đặc biệt, không phải hành vi mặc định của function hoặc procedure.

### 14.5. Ghi nhớ bằng bảng

| Câu hỏi | Cách trả lời đúng |
| --- | --- |
| Function PostgreSQL có thể COMMIT độc lập? | Không qua COMMIT/ROLLBACK thông thường trong thân function. |
| Procedure PostgreSQL luôn COMMIT được? | **Không**; phụ thuộc ngữ cảnh CALL và giới hạn định nghĩa. |
| CALL procedure trong BEGIN rồi ROLLBACK có thể hủy dữ liệu? | **Có** nếu procedure không và không được kết thúc transaction độc lập. |
| Procedure tự động tạo transaction mới? | **Không phải quy tắc chung**. |
| OUT parameter có làm dữ liệu durable? | Không; đó chỉ là cơ chế trả kết quả. |
| Stored function MySQL có thể dùng transaction control như procedure? | Không; bị hạn chế theo quy tắc stored function MySQL. |

## 15. Xử lý lỗi: IF, EXCEPTION và trạng thái giao dịch

Một lợi thế của procedural language là xử lý nhánh/lỗi:

~~~sql
CREATE FUNCTION bai335.chia_an_toan(
    p_tu_so NUMERIC,
    p_mau_so NUMERIC
)
RETURNS NUMERIC
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    IF p_mau_so IS NULL OR p_mau_so = 0 THEN
        RAISE EXCEPTION 'Mau so phai khac 0';
    END IF;

    RETURN p_tu_so / p_mau_so;
END;
$$;
~~~

Function này cho phép quy tắc lỗi rõ ràng, nhưng việc gọi trong SELECT trên nhiều hàng có thể làm **toàn statement thất bại** nếu một hàng kích hoạt exception. Đó là một phần của hợp đồng function.

### 15.1. EXCEPTION block và subtransaction PostgreSQL

Trong PL/pgSQL, một khối có `EXCEPTION` dùng cơ chế subtransaction để hoàn nguyên thay đổi bên trong khối khi lỗi được bắt. Ví dụ cách minh họa:

~~~sql
CREATE PROCEDURE bai335.thu_ghi_nhat_ky(
    IN p_don_id BIGINT
)
LANGUAGE plpgsql
AS $$
BEGIN
    BEGIN
        INSERT INTO bai335.nhat_ky_don (don_hang_id, hanh_dong)
        VALUES (p_don_id, 'THU_NHAT_KY');
    EXCEPTION WHEN foreign_key_violation THEN
        RAISE NOTICE 'Khong ghi duoc nhat ky: don khong ton tai';
    END;
END;
$$;
~~~

Nếu `p_don_id` không tồn tại, INSERT vi phạm FK, khối con bị hoàn nguyên và NOTICE được phát; transaction bên ngoài có thể tiếp tục. Nhưng **bắt rồi bỏ lỗi** chỉ đúng nếu nghiệp vụ thật sự cho phép bỏ bước log. Nếu log là bắt buộc, nên để lỗi lan lên để caller rollback transaction.

### 15.2. Không dùng EXCEPTION như try/catch mọi thứ vô điều kiện

- Không nuốt mất lỗi mất kết nối, timeout nghiêm trọng hoặc trạng thái giao dịch không còn hợp lệ.
- Không trả giá trị thành công giả khi DML chưa thực sự thành công.
- Không dùng exception để điều khiển nhánh bình thường nếu một điều kiện `IF` đơn giản đã đủ.
- Nếu cần retry, phải xét tính idempotent và transaction isolation.
- Với PostgreSQL, mỗi khối EXCEPTION có overhead; không tạo hàng triệu subtransactions nếu workload có thể xử lý set-based.

## 16. Hàm trong WHERE và ORDER BY: tính đúng trước, tối ưu sau

Có thể dùng function trong điều kiện:

~~~sql
SELECT id, tong_tien
FROM bai335.don_hang
WHERE bai335.xep_hang_don(tong_tien) = 'VIP';
~~~

Nhưng cột `tong_tien` bị đưa vào một **biểu thức hàm**. Một index B-tree thông thường trên `tong_tien` không nhất thiết được khai thác như khi viết:

~~~sql
SELECT id, tong_tien
FROM bai335.don_hang
WHERE tong_tien >= 1000000;
~~~

Nếu yêu cầu VIP luôn đúng theo quy tắc đó, điều kiện trực tiếp rõ ràng và có thể tận dụng index trên `tong_tien`.

### 16.1. Expression index có thể phù hợp

PostgreSQL có expression indexes:

~~~sql
CREATE INDEX idx_don_hang_xep_hang
ON bai335.don_hang (
    bai335.xep_hang_don(tong_tien)
);
~~~

Vì function `xep_hang_don` đã khai báo `IMMUTABLE` và thực sự chỉ tính từ đầu vào, việc tạo expression index có thể phù hợp. Nhưng index có chi phí ghi; nhiều khi câu `WHERE tong_tien >= 1000000` cộng index B-tree thường đã đơn giản hơn.

Nếu function **đọc bảng khác**, thay đổi theo thời gian hoặc có side effect, **không được khai báo IMMUTABLE giả** chỉ để dùng trong index.

### 16.2. Function có thể được gọi nhiều lần

Một function scalar trong SELECT có thể được đánh giá cho nhiều hàng. Không suy rằng engine chỉ gọi nó **một lần** vì câu SQL viết tên function một lần. Planner có thể inline, fold, bỏ qua hoặc thay đổi thời điểm đánh giá các biểu thức hợp lệ theo semantics.

Với function có side effect, không nên dựa vào số lần gọi hoặc thứ tự gọi chỉ từ cách viết SQL:

~~~sql
SELECT bai335.them_don_function('Một lời gọi', 100000)
FROM bai335.don_hang;
~~~

Nếu query nguồn có nhiều hàng, ví dụ này có nguy cơ chèn nhiều đơn. Đó là một lý do quan trọng để **đưa thao tác ghi vào DML/procedure rõ ràng** thay vì function gọi rải rác trong SELECT.

## 17. Bảo mật: quyền EXECUTE và SECURITY DEFINER

Routine có thể trở thành ranh giới cấp quyền: ứng dụng được phép **gọi một chức năng cụ thể** thay vì được phép cập nhật mọi bảng.

### 17.1. PostgreSQL EXECUTE privilege

Ví dụ:

~~~sql
-- Minh họa trên vai trò giả định app_role, chưa được tạo trong bài.
GRANT EXECUTE ON FUNCTION bai335.xep_hang_don(NUMERIC)
TO app_role;

GRANT EXECUTE ON PROCEDURE bai335.xac_nhan_don(BIGINT)
TO app_role;
~~~

Cú pháp cấp quyền cần khớp loại routine và signature. Quyền `EXECUTE` **không tự động** bảo đảm caller có quyền truy cập bảng bên trong nếu routine chạy dưới quyền invoker; cũng không tự động có quyền vượt mọi cơ chế row-level security.

### 17.2. SECURITY INVOKER và SECURITY DEFINER

PostgreSQL functions/procedures có thuộc tính quyền thực thi như `SECURITY INVOKER` (mặc định phù hợp) và `SECURITY DEFINER`. Khi dùng definer, code có thể chạy với quyền của người sở hữu routine, rất nhạy cảm nếu dùng để truy cập dữ liệu nhiều tổ chức.

Nguy cơ thường gặp:

- Dùng tên bảng không có schema cố định rồi bị `search_path` dẫn sang đối tượng không mong muốn.
- Dynamic SQL nối dữ liệu đầu vào không được quote/bind an toàn.
- Procedure không kiểm tra `to_chuc_id` hoặc người sở hữu bản ghi.
- Cấp EXECUTE quá rộng cho routine có quyền ghi dữ liệu nhạy cảm.

Với SECURITY DEFINER trong PostgreSQL, phải khóa `search_path` theo thực hành bảo mật, kiểm soát schema có thể ghi bởi người dùng, dùng tên đối tượng schema-qualified và tránh nhét input vào SQL dưới dạng chuỗi.

### 17.3. Dynamic SQL và SQL injection

Trong PL/pgSQL, khi thật sự cần câu SQL động:

~~~sql
-- Ví dụ ý tưởng trong PL/pgSQL, không phải function hoàn chỉnh:
EXECUTE format(
    'SELECT count(*) FROM %I.%I',
    p_schema,
    p_table
)
INTO v_count;
~~~

`format('%I', ...)` quote định danh. Còn **giá trị dữ liệu** nên đi qua tham số bằng `USING` khi có thể, thay vì nối chuỗi SQL:

~~~sql
EXECUTE format('SELECT count(*) FROM %I.%I WHERE id = $1',
               p_schema, p_table)
INTO v_count
USING p_id;
~~~

Cần kiểm tra **quyền đối với bảng được chọn**, không chỉ quote định danh. SQL injection được ngăn bằng ràng buộc giao diện đầu vào, quote/bind đúng loại và nguyên tắc least privilege, không phải bằng việc đưa tất cả SQL vào stored procedure.

### 17.4. Các DBMS khác

- MySQL có `SQL SECURITY DEFINER`/`INVOKER` cho routine.
- SQL Server hỗ trợ quyền EXECUTE, ownership chaining và `EXECUTE AS` theo ngữ cảnh.
- Oracle có definer/invoker rights với `AUTHID DEFINER`/`CURRENT_USER`.
- SQLite UDF thường được đăng ký bởi ứng dụng, chịu mô hình quyền của ứng dụng/kết nối thay vì stored routine SQL như PostgreSQL.

## 18. Stored routine không thay thế validation và transaction ở ứng dụng

Việc đóng gói logic ở DB **không khiến ứng dụng khỏi trách nhiệm**:

- Xác thực người dùng và phạm vi tổ chức;
- Xác thực input trước khi gửi;
- Bind tham số thay vì nối chuỗi;
- Xử lý lỗi và transaction/connection;
- Ghi log nghiệp vụ phù hợp;
- Chống gọi lại gây side effect trùng;
- Kiểm tra dữ liệu được trả và số hàng tác động.

Ví dụ procedure `xac_nhan_don` chỉ kiểm tra trạng thái, chưa kiểm tra **người gọi có được phép xác nhận đơn của tổ chức đó không**. Một hệ nhiều tenant cần kiểm soát quyền ở tầng DB hoặc kiểm tra context được xác thực, không chỉ tin vào ID do client truyền.

### 18.1. Idempotency khi thao tác ghi

Nếu cùng yêu cầu tạo đơn được gửi lại do timeout, một routine chỉ có INSERT có thể tạo **hai đơn**:

~~~sql
CALL bai335.them_don('Hà', 350000, NULL);
CALL bai335.them_don('Hà', 350000, NULL);
~~~

Đó là hai lời gọi tạo dữ liệu mới, không phải tự động retry an toàn. Cần khóa idempotency/business key duy nhất và chính sách xử lý khi request trùng, bất kể logic được viết ở procedure hay ứng dụng.

## 19. Hiệu năng: set-based SQL và procedural row-by-row

Một nguyên tắc trong database quan hệ là **ưu tiên xử lý theo tập** khi bài toán cho phép.

### 19.1. Một câu UPDATE theo tập

~~~sql
UPDATE bai335.don_hang
SET trang_thai = 'DA_XAC_NHAN'
WHERE trang_thai = 'MOI'
  AND tong_tien >= 500000;
~~~

Câu SQL biểu diễn một tập hàng cần cập nhật. Planner có thể chọn index/scan và tối ưu theo tập.

### 19.2. Vòng lặp cập nhật từng hàng

~~~sql
-- Mẫu PL/pgSQL minh họa, không phải lựa chọn mặc định:
FOR v_id IN
    SELECT id
    FROM bai335.don_hang
    WHERE trang_thai = 'MOI'
      AND tong_tien >= 500000
LOOP
    UPDATE bai335.don_hang
    SET trang_thai = 'DA_XAC_NHAN'
    WHERE id = v_id;
END LOOP;
~~~

Ví dụ này phải nằm trong thân PL/pgSQL routine. Nó có thể phát sinh **nhiều statement DML** và overhead mỗi vòng, trong khi bài toán có thể giải bằng một UPDATE.

**Không phải mọi vòng lặp đều xấu:** có những quy trình thực sự cần quyết định theo từng bước, gọi logic phức tạp hoặc dừng/phục hồi theo đơn vị. Nhưng khi chỉ chuyển trạng thái theo điều kiện, câu SQL set-based thường dễ hiểu và có tiềm năng hiệu năng tốt hơn.

### 19.3. Function SQL có thể inline; procedural function có thể khó tối ưu xuyên lớp

PostgreSQL có khả năng inline một số SQL-language functions khi đáp ứng ràng buộc; việc đó có thể mở ra cơ hội pushdown predicate và tối ưu join. Một function PL/pgSQL phức tạp thường được gọi như một routine riêng và planner của query bên ngoài không nhìn vào toàn bộ điều kiện bên trong theo cùng cách.

Tuy nhiên, **không phải mọi SQL function đều inline**, và procedural function vẫn có những cơ chế cache plan/optimization riêng. Kết luận phải dựa trên `EXPLAIN (ANALYZE, BUFFERS)` và workload đại diện.

### 19.4. N+1 routine calls

Nếu code ứng dụng gọi một function truy vấn bảng cho từng ID trong danh sách 100.000 ID, chi phí network hoặc các câu SQL bên trong function có thể lớn. Một truy vấn JOIN với bảng đầu vào/staging thường rẻ hơn 100.000 lời gọi riêng.

**Đếm các lần gọi và khối lượng dữ liệu**, đừng chỉ nhìn query của một lời gọi function chạy nhanh.

## 20. MySQL/MariaDB: STORED FUNCTION và STORED PROCEDURE

MySQL phân biệt `CREATE FUNCTION` và `CREATE PROCEDURE`; cả hai có thể dùng ngôn ngữ stored program theo cú pháp MySQL. Nó **không có ngữ nghĩa PostgreSQL LANGUAGE SQL vs LANGUAGE plpgsql** giống hệt.

### 20.1. Stored function MySQL

Ví dụ:

~~~sql
CREATE FUNCTION tinh_gia_sau_giam(
    p_gia DECIMAL(12,2),
    p_ty_le DECIMAL(5,2)
)
RETURNS DECIMAL(12,2)
DETERMINISTIC
NO SQL
RETURN ROUND(p_gia * (1 - p_ty_le / 100), 2);
~~~

Gọi:

~~~sql
SELECT tinh_gia_sau_giam(500000, 10);
~~~

`DETERMINISTIC` mô tả tính nhất quán kết quả với cùng input; `NO SQL` khai báo đặc tính truy cập SQL của function này. Đây là đặc tính người viết khai báo với MySQL, không phải phép kiểm thử tự động chứng minh mọi function được đánh dấu deterministic đều thực sự thuần.

MySQL stored functions có những hạn chế cụ thể về điều khiển transaction, dynamic SQL, sử dụng result set và việc sửa bảng đã được câu gọi sử dụng; không chép function DML PostgreSQL vào MySQL rồi kỳ vọng hoạt động.

### 20.2. Stored procedure MySQL

Trong công cụ như MySQL command-line client, `DELIMITER` là **lệnh của client** để cho phép nhập một routine nhiều statement; nó không phải từ khóa SQL server.

~~~sql
DELIMITER $$

CREATE PROCEDURE xac_nhan_don(IN p_id BIGINT)
BEGIN
    UPDATE don_hang
    SET trang_thai = 'DA_XAC_NHAN'
    WHERE id = p_id
      AND trang_thai = 'MOI';

    IF ROW_COUNT() <> 1 THEN
        SIGNAL SQLSTATE '45000'
            SET MESSAGE_TEXT = 'Don khong hop le';
    END IF;
END$$

DELIMITER ;

CALL xac_nhan_don(101);
~~~

Khác với PostgreSQL:

- MySQL không viết `LANGUAGE plpgsql`.
- Procedure dùng `CALL`.
- Function thường được gọi trong `SELECT`.
- Stored procedure có `IN`/`OUT`/`INOUT`.
- Transaction semantics và các hạn chế stored function/procedure cần xét theo phiên bản/storage engine.
- `DELIMITER` là yêu cầu nhập lệnh của **client**; driver API thường gửi định nghĩa routine như một statement mà không cần cú pháp DELIMITER.

### 20.3. Trả tham số OUT ở MySQL

~~~sql
DELIMITER $$

CREATE PROCEDURE dem_don_theo_trang_thai(
    IN p_trang_thai VARCHAR(30),
    OUT p_so_don INT
)
BEGIN
    SELECT COUNT(*)
      INTO p_so_don
    FROM don_hang
    WHERE trang_thai = p_trang_thai;
END$$

DELIMITER ;

CALL dem_don_theo_trang_thai('MOI', @so_don);
SELECT @so_don AS so_don;
~~~

Đây là mẫu **MySQL**. Biến người dùng `@so_don` thuộc session; trong ứng dụng nên dùng cơ chế bind OUT parameter của driver tương ứng. Không dùng tham số OUT MySQL như một scalar function để viết `WHERE id = dem_don_theo_trang_thai(...)`.

## 21. SQL Server: scalar UDF, table-valued UDF và stored procedure

SQL Server dùng **T-SQL**. Các hàm do người dùng định nghĩa thường được chia thành **scalar user-defined function** và **table-valued function**; procedure được gọi bằng `EXEC` hoặc `EXECUTE`.

### 21.1. Scalar T-SQL function

~~~sql
CREATE OR ALTER FUNCTION dbo.XepHangDon(
    @TongTien DECIMAL(18,2)
)
RETURNS NVARCHAR(20)
AS
BEGIN
    DECLARE @KetQua NVARCHAR(20);

    SET @KetQua = CASE
        WHEN @TongTien IS NULL THEN NULL
        WHEN @TongTien >= 1000000 THEN N'VIP'
        WHEN @TongTien >= 200000 THEN N'TIEU_CHUAN'
        ELSE N'THUONG'
    END;

    RETURN @KetQua;
END;
~~~

Gọi:

~~~sql
SELECT dbo.XepHangDon(1500000) AS XepHang;
~~~

Cú pháp này là SQL Server, không chạy nguyên văn trên PostgreSQL.

### 21.2. Inline table-valued function

~~~sql
CREATE OR ALTER FUNCTION dbo.TimDonTheoTrangThai(
    @TrangThai NVARCHAR(30)
)
RETURNS TABLE
AS
RETURN
(
    SELECT Id, TenKhach, TongTien
    FROM dbo.DonHang
    WHERE TrangThai = @TrangThai
);
~~~

Gọi:

~~~sql
SELECT *
FROM dbo.TimDonTheoTrangThai(N'MOI');
~~~

Inline TVF có thể được optimizer tích hợp thuận lợi vào query plan; multi-statement TVF lại có thể có đặc tính ước lượng/thực thi khác, tùy phiên bản. Không mặc định mọi table-valued function sẽ nhanh như một câu SELECT trực tiếp.

### 21.3. Stored procedure SQL Server

~~~sql
CREATE OR ALTER PROCEDURE dbo.XacNhanDon
    @Id BIGINT,
    @SoDong INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.DonHang
    SET TrangThai = N'DA_XAC_NHAN'
    WHERE Id = @Id
      AND TrangThai = N'MOI';

    SET @SoDong = @@ROWCOUNT;
END;
~~~

Gọi:

~~~sql
DECLARE @DaDoi INT;

EXEC dbo.XacNhanDon
    @Id = 101,
    @SoDong = @DaDoi OUTPUT;

SELECT @DaDoi AS SoDongDaCapNhat;
~~~

T-SQL procedure có thể trả **result sets** từ SELECT, dùng OUTPUT parameters và trả status bằng RETURN. Tất cả không đồng nghĩa nó là một function có thể đưa vào biểu thức SELECT.

### 21.4. SQL Server UDF bị hạn chế side effects

Không thể tự ý UPDATE bảng dữ liệu thường xuyên bên trong T-SQL UDF như trong PostgreSQL VOLATILE function. SQL Server UDF có hạn chế đối với sửa trạng thái database, dynamic SQL và một số cơ chế điều khiển lỗi/transaction. Procedure phù hợp hơn cho những quy trình DML.

Có tính năng **scalar UDF inlining** trong SQL Server ở những phiên bản và điều kiện phù hợp, giúp tối ưu một số scalar functions. Không kết luận “scalar UDF luôn chậm” hay “luôn được inline”; cần kiểm tra plan thực tế.

## 22. Oracle: FUNCTION và PROCEDURE trong PL/SQL

Oracle thường định nghĩa routine bằng **PL/SQL**. Cả FUNCTION và PROCEDURE đều có thể dùng biến, `IF`, vòng lặp và xử lý ngoại lệ.

### 22.1. Oracle FUNCTION

~~~sql
CREATE OR REPLACE FUNCTION xep_hang_don(
    p_tong_tien IN NUMBER
)
RETURN VARCHAR2
IS
BEGIN
    IF p_tong_tien IS NULL THEN
        RETURN NULL;
    ELSIF p_tong_tien >= 1000000 THEN
        RETURN 'VIP';
    ELSIF p_tong_tien >= 200000 THEN
        RETURN 'TIEU_CHUAN';
    ELSE
        RETURN 'THUONG';
    END IF;
END;
/
~~~

Gọi khi function hợp lệ để dùng trong SQL:

~~~sql
SELECT xep_hang_don(1500000) AS xep_hang
FROM dual;
~~~

Dấu `/` là cú pháp thực thi khối của những client Oracle như SQL*Plus/SQLcl, không phải từ khóa SQL chuẩn của chính định nghĩa FUNCTION.

### 22.2. Oracle PROCEDURE với OUT

~~~sql
CREATE OR REPLACE PROCEDURE dem_don(
    p_trang_thai IN VARCHAR2,
    p_so_don OUT NUMBER
)
IS
BEGIN
    SELECT COUNT(*)
      INTO p_so_don
    FROM don_hang
    WHERE trang_thai = p_trang_thai;
END;
/
~~~

Trong PL/SQL block:

~~~sql
DECLARE
    v_so_don NUMBER;
BEGIN
    dem_don('MOI', v_so_don);
    DBMS_OUTPUT.PUT_LINE(v_so_don);
END;
/
~~~

Oracle procedure thường được gọi bằng lời gọi PL/SQL hoặc cơ chế CALL/OUT bind của driver, không phải function dùng trực tiếp trong WHERE. Oracle còn có **package** để nhóm các routine và quản lý interface/implementation.

### 22.3. Function Oracle và side effects trong SELECT

Một Oracle PL/SQL function có thể có DML ở một số ngữ cảnh, nhưng khi **được gọi từ một câu SQL query**, các quy tắc về side effects/transaction áp dụng; ví dụ có thể gặp `ORA-14551: cannot perform a DML operation inside a query`. Không sao chép ví dụ PostgreSQL “SELECT function mà function INSERT” sang Oracle.

Oracle hỗ trợ `DETERMINISTIC` cho function trong một số mục đích tối ưu, nhưng đó cũng là cam kết người lập trình phải giữ đúng. Autonomous transaction là cơ chế riêng, **không phải lời khuyên mặc định** để lách hạn chế DML từ function gọi trong SELECT.

## 23. SQLite: SQL functions không nhất thiết là stored functions

SQLite có nhiều built-in functions như `lower()`, `substr()`, `round()`, `coalesce()`. Ứng dụng cũng có thể **đăng ký user-defined functions** trên connection thông qua API (ví dụ sqlite3_create_function trong C hoặc giao diện tương đương trong ngôn ngữ khác).

Nhưng SQLite không cung cấp bộ câu lệnh **CREATE PROCEDURE/CREATE FUNCTION trong SQL schema** tương đương PostgreSQL hoặc MySQL. Vì thế:

~~~sql
-- Không phải cú pháp stored procedure SQLite thông thường:
-- CREATE PROCEDURE xac_nhan_don(...)
-- BEGIN ... END;
~~~

Với SQLite, logic nhiều bước có thể được triển khai ở:

- SQL trực tiếp và **transaction** do ứng dụng điều phối;
- **TRIGGER** cho các phản ứng gắn với DML trong phạm vi hỗ trợ;
- **User-defined functions** do ứng dụng đăng ký;
- Các lớp service hoặc code ứng dụng.

Trigger **không đồng nghĩa procedure**: trigger được gọi tự động bởi sự kiện dữ liệu, còn procedure thường được gọi có chủ đích qua CALL/EXEC. Tránh phát biểu “mọi DBMS đều có stored procedure”.

## 24. So sánh phương ngữ một cách có hệ thống

| Đặc tính | PostgreSQL | MySQL/MariaDB | SQL Server | Oracle | SQLite |
| --- | --- | --- | --- | --- | --- |
| Hàm do người dùng định nghĩa trong database | `CREATE FUNCTION` | `CREATE FUNCTION` | `CREATE FUNCTION` | `CREATE FUNCTION` | Thường đăng ký UDF từ ứng dụng |
| Ngôn ngữ phần thân thường gặp | SQL, PL/pgSQL và ngôn ngữ hỗ trợ khác | Stored program SQL | T-SQL | PL/SQL | Callback ứng dụng |
| Stored procedure | `CREATE PROCEDURE` | `CREATE PROCEDURE` | `CREATE PROCEDURE` | `CREATE PROCEDURE` | Không có cú pháp built-in tương ứng |
| Gọi procedure | `CALL` | `CALL` | `EXEC`/`EXECUTE` | PL/SQL invocation/CALL theo ngữ cảnh | Ứng dụng thực thi các câu SQL |
| Function scalar trong SELECT | Có | Có | Có | Có khi hợp lệ | Built-in/UDF |
| Table-valued function | `RETURNS TABLE`/SETOF | Không đồng dạng tổng quát như PostgreSQL | Inline/multi-statement TVF | Table/pipelined function theo cú pháp Oracle | Table-valued extensions/virtual tables tùy API |
| Function có thể ghi bảng thông thường? | Có trong trường hợp VOLATILE hợp lệ | Có hạn chế đáng kể; không tương đương PG | UDF không được sửa trạng thái DB như procedure | Bị hạn chế mạnh khi gọi từ SELECT | UDF ứng dụng có quy tắc/reentrancy riêng |
| Procedure tự COMMIT? | Chỉ trong ngữ cảnh CALL cho phép | Theo điều khiển giao dịch/ngữ cảnh | Theo BEGIN/COMMIT và transaction owner | Theo logic và ngữ cảnh transaction | Không có procedure |
| OUT/INOUT | Routine parameters theo version/cú pháp | IN/OUT/INOUT | OUTPUT parameters | IN/OUT/IN OUT | API ứng dụng |

**Đọc đúng DBMS và phiên bản** trước khi áp dụng syntax từ bảng. Cùng chữ `FUNCTION` không đồng nghĩa điều kiện gọi, side effects và kiểu result set như nhau.

## 25. Chọn function hay procedure theo nhu cầu

| Nhu cầu | Lựa chọn thường hợp lý | Lý do |
| --- | --- | --- |
| Tính giá sau giảm từ hai số | SQL-language function hoặc SQL biểu thức | Gọn, có thể dùng trong SELECT |
| Xếp loại bằng điều kiện/kiểm tra lỗi | Procedural function hoặc SQL CASE | Trả một giá trị, cần nhánh |
| Trả danh sách đơn theo trạng thái | SQL table-valued function hoặc SQL trực tiếp | Đầu ra là quan hệ |
| Kiểm tra/chuẩn hóa chuỗi dùng lặp lại | Function có ngữ nghĩa rõ | Dùng trong SELECT, kiểm thử độc lập |
| Xác nhận đơn với kiểm tra trạng thái | Stored procedure hoặc UPDATE có điều kiện | Hợp đồng là thao tác thay đổi |
| Chèn đơn và ghi nhật ký bắt buộc | Transaction gồm DML; procedure khi cần đóng gói | Nhiều bước có tính nguyên tử |
| Chuyển tiền giữa hai tài khoản | Transaction thiết kế chặt, procedure/service tùy kiến trúc | Bất biến nghiệp vụ và concurrency |
| Báo cáo tổng hợp hàng triệu đơn | Set-based SELECT/view/TVF khi phù hợp | Hạn chế vòng lặp theo hàng |
| Tác vụ chạy độc lập nhiều phút | Worker/job orchestration; procedure chỉ khi phù hợp | Long transaction/side effects là rủi ro |
| Tương thích SQLite và PostgreSQL | Cân nhắc logic ứng dụng hoặc lớp abstraction | SQLite không có stored procedure cùng dạng |

### 25.1. Khi KHÔNG cần routine

Không nên tạo stored routine chỉ để che một câu SQL cực đơn giản, nếu không có nhu cầu tái sử dụng, quyền, encapsulation hoặc hợp đồng dữ liệu rõ ràng. Ví dụ:

~~~sql
UPDATE bai335.don_hang
SET trang_thai = 'DA_XAC_NHAN'
WHERE id = 101 AND trang_thai = 'MOI'
RETURNING id, trang_thai;
~~~

Câu DML trực tiếp có thể đủ. Nếu nghiệp vụ nhiều bước, cần bảo vệ tính nhất quán giữa bảng hoặc được nhiều ứng dụng gọi, đóng gói procedure có thể đáng giá.

### 25.2. Khi KHÔNG nên dùng function trong SELECT

Đừng viết function DML có side effect rồi gọi nó từ truy vấn tổng hợp chỉ để “tiện”. Các vấn đề có thể phát sinh: số lần đánh giá, truy vấn được tối ưu lại, lỗi giữa chừng, khóa, chi phí và kỳ vọng của người đọc SELECT.

## 26. Quy trình kiểm thử một routine

Một routine tốt cần kiểm thử **hợp đồng**, không chỉ chạy thành công với một bộ tham số.

### 26.1. Function tính toán

Cho `tinh_gia_sau_giam`:

~~~sql
SELECT bai335.tinh_gia_sau_giam(100000, 0);   -- 100000.00
SELECT bai335.tinh_gia_sau_giam(100000, 10);  --  90000.00
SELECT bai335.tinh_gia_sau_giam(NULL, 10);    -- NULL vì STRICT
~~~

Cần quyết định rõ tỷ lệ âm, tỷ lệ trên 100, giá tiền âm, làm tròn và kiểu số. **Hàm SQL mẫu không chủ động từ chối các tỷ lệ ấy**.

### 26.2. Function procedural

~~~sql
SELECT bai335.xep_hang_don(100000);   -- THUONG
SELECT bai335.xep_hang_don(300000);   -- TIEU_CHUAN
SELECT bai335.xep_hang_don(1500000);  -- VIP
SELECT bai335.xep_hang_don(NULL);     -- NULL
~~~

Thử giá âm sẽ kích hoạt `RAISE EXCEPTION`. Cần chạy trong ngữ cảnh transaction phù hợp để không làm hỏng một bài thực hành khác ở PostgreSQL khi cố tình gây lỗi.

### 26.3. Procedure DML

~~~sql
BEGIN;

CALL bai335.xac_nhan_don(4);

SELECT id, trang_thai
FROM bai335.don_hang
WHERE id = 4;

ROLLBACK;
~~~

Nếu đơn 4 còn MOI trước bài, bên trong transaction nó thành DA_XAC_NHAN; sau ROLLBACK nó trở về trạng thái trước đó. Nếu ID 4 đã đổi trạng thái từ bài khác, phải đặt lại dữ liệu thử.

### 26.4. Kiểm tra đầu vào xấu

Các tình huống cần quyết định:

- ID không tồn tại;
- Trạng thái không cho phép chuyển;
- Tiền âm, NULL, vượt giới hạn;
- Function được gọi với kiểu tham số khác/ép kiểu;
- Quyền EXECUTE không đủ;
- Deadlock/serialization failure;
- Gọi lại cùng request;
- Lỗi ghi nhật ký phụ sau khi thay đổi chính.

Không gắn nhãn routine “đã an toàn” chỉ vì một lần CALL trả thành công.

## 27. Bài tập có lời giải

Các bài dưới đây chủ yếu sử dụng schema `bai335` của PostgreSQL; các bài phương ngữ khác ghi rõ. Bài tập có DML nên thực hành trên **database thử nghiệm** và dùng transaction/ROLLBACK khi cần khôi phục dữ liệu.

### Bài 1. Phân loại đối tượng

**Câu hỏi:** `CREATE FUNCTION ... LANGUAGE sql` là function hay procedure?

**Đáp án:** Là **function**. `LANGUAGE sql` chỉ xác định ngôn ngữ phần thân.

### Bài 2. PL/pgSQL có làm đối tượng thành procedure không?

**Câu hỏi:** hàm có `CREATE FUNCTION ... RETURNS TEXT LANGUAGE plpgsql` và `IF ... RETURN` được gọi bằng gì?

**Đáp án:** Vẫn là **function**, thường gọi `SELECT ten_ham(...)` hoặc trong biểu thức SQL tương thích.

### Bài 3. Chọn routine cho phép toán thuần

**Yêu cầu:** tính 15% chiết khấu từ 800000, viết lời gọi function.

~~~sql
SELECT bai335.tinh_gia_sau_giam(800000, 15);
~~~

**Đáp án:** **680000.00**. Với công thức đơn giản, SQL-language function phù hợp.

### Bài 4. Phân loại đơn VIP

**Yêu cầu:** lấy ID, tổng tiền, xếp loại từ function procedural.

~~~sql
SELECT
    id,
    tong_tien,
    bai335.xep_hang_don(tong_tien) AS xep_hang
FROM bai335.don_hang
ORDER BY id;
~~~

**Lời giải:** Function PL/pgSQL được dùng trong SELECT vì nó có `RETURNS TEXT`. Các đơn giá từ 1.000.000 trở lên trả VIP.

### Bài 5. Function trả bảng

**Câu hỏi:** dùng câu nào để lấy hàng từ `tim_don_theo_trang_thai('MOI')`?

~~~sql
SELECT *
FROM bai335.tim_don_theo_trang_thai('MOI')
ORDER BY id;
~~~

**Đáp án:** Đưa function vào `FROM` vì nó trả quan hệ nhiều hàng, nhiều cột.

### Bài 6. Function có biến

**Yêu cầu:** nêu hai cấu trúc PL/pgSQL không trực tiếp có trong phần thân SQL đơn giản.

**Đáp án:** `DECLARE` cho biến cục bộ, `IF/ELSIF/ELSE` hoặc `FOR LOOP` và xử lý `EXCEPTION`. Nhiều nhánh đơn giản vẫn có thể thay bằng SQL `CASE`.

### Bài 7. Procedure được gọi thế nào?

**Yêu cầu:** xác nhận đơn ID 2 trong PostgreSQL và rollback để thử nghiệm.

~~~sql
BEGIN;
CALL bai335.xac_nhan_don(2);
ROLLBACK;
~~~

**Đáp án:** Dùng `CALL`, không dùng `SELECT bai335.xac_nhan_don(2)` vì đây là procedure.

### Bài 8. Procedure có tự commit không?

**Câu hỏi:** trong `BEGIN; CALL xac_nhan_don(2); ROLLBACK;`, xác nhận có được giữ không?

**Đáp án:** **Không**, giả sử procedure không có transaction control riêng. CALL thực hiện DML trong transaction caller, ROLLBACK toàn bộ hoàn nguyên nó.

### Bài 9. Procedure nhận và trả ID

**Yêu cầu:** thêm đơn và nhận ID bằng INOUT parameter.

~~~sql
CALL bai335.them_don('Thảo', 275000, NULL);
~~~

**Đáp án:** Đây là `CALL` procedure có `INOUT p_id`; giá trị đầu ra được gán từ `INSERT ... RETURNING id INTO p_id`. Đầu ra không khiến DML tự động durable trước commit.

### Bài 10. DML không nhất thiết cần routine

**Yêu cầu:** thêm đơn và nhận ID mà không tạo procedure/function mới.

~~~sql
INSERT INTO bai335.don_hang (ten_khach, tong_tien)
VALUES ('Thủy', 200000)
RETURNING id;
~~~

**Đáp án:** PostgreSQL `INSERT ... RETURNING` đáp ứng yêu cầu đơn giản, rõ ràng.

### Bài 11. Function ghi dữ liệu

**Câu hỏi:** tại sao `them_don_function` là function dù INSERT vào bảng?

**Đáp án:** Nó được tạo bằng `CREATE FUNCTION ... RETURNS BIGINT LANGUAGE plpgsql VOLATILE` và được gọi trong SELECT. PostgreSQL cho phép hành vi ghi trong các function phù hợp, nhưng SQL Server UDF và Oracle function gọi từ query có hạn chế khác.

### Bài 12. Giới hạn IMMUTABLE

**Câu hỏi:** một function đọc bảng giá hiện hành rồi trả giá theo ngày có nên khai báo IMMUTABLE chỉ để tạo expression index không?

**Đáp án:** Không. Kết quả phụ thuộc dữ liệu bên ngoài tham số. Phải khai báo volatility đúng và thiết kế index/tra cứu phù hợp; dùng IMMUTABLE giả có thể làm sai kết quả.

### Bài 13. Function trong WHERE

**Yêu cầu:** viết hai cách tìm đơn VIP theo ngưỡng 1.000.000.

~~~sql
SELECT id
FROM bai335.don_hang
WHERE bai335.xep_hang_don(tong_tien) = 'VIP';

SELECT id
FROM bai335.don_hang
WHERE tong_tien >= 1000000;
~~~

**Đáp án:** Với quy tắc hiện tại, truy vấn thứ hai có thể tận dụng B-tree `tong_tien` tự nhiên hơn. Nếu logic xếp hạng thay đổi, cần bảo đảm hai câu vẫn tương đương.

### Bài 14. Một function gọi nhiều lần

**Câu hỏi:** viết `SELECT ham_ghi_du_lieu(...) FROM bang_1000_hang` có luôn ghi đúng một lần không?

**Đáp án:** Không. Function có thể được đánh giá theo số hàng và kế hoạch. Không dùng SELECT với side effect nếu cần hợp đồng “thực hiện một thao tác duy nhất”.

### Bài 15. MySQL function

**Câu hỏi:** trong MySQL, function trả DECIMAL thường được gọi bằng `CALL` hay `SELECT`?

**Đáp án:** Thường dùng `SELECT ten_ham(...)`. `CALL` dành cho stored procedure.

### Bài 16. DELIMITER là gì?

**Câu hỏi:** `DELIMITER $$` trong ví dụ MySQL là lệnh SQL gửi cho server hay lệnh của client nhập script?

**Đáp án:** Là **lệnh của nhiều MySQL client** giúp nhập một định nghĩa nhiều statement; không phải cú pháp stored procedure server dùng ở mọi driver.

### Bài 17. SQL Server scalar UDF ghi bảng?

**Câu hỏi:** có thể chép một PostgreSQL VOLATILE function có INSERT sang SQL Server CREATE FUNCTION để sửa bảng thường không?

**Đáp án:** Không. SQL Server UDF có hạn chế về thay đổi trạng thái database; nên dùng stored procedure hoặc DML trực tiếp.

### Bài 18. SQL Server OUTPUT parameter

**Yêu cầu:** nhận số hàng được cập nhật từ procedure T-SQL.

~~~sql
DECLARE @n INT;
EXEC dbo.XacNhanDon @Id = 101, @SoDong = @n OUTPUT;
SELECT @n AS SoDong;
~~~

**Đáp án:** Procedure sử dụng `@SoDong OUTPUT`, không phải `RETURNS INT` scalar UDF.

### Bài 19. Oracle function trong SELECT

**Câu hỏi:** có nên dùng một PL/SQL function INSERT dữ liệu từ Oracle SELECT mà kỳ vọng hoạt động như PostgreSQL VOLATILE function không?

**Đáp án:** Không. Oracle hạn chế DML/side effects trong function được gọi từ SQL query; có thể gặp `ORA-14551`. Cần thiết kế phù hợp ngữ nghĩa Oracle.

### Bài 20. SQLite

**Câu hỏi:** SQLite có stored procedure định nghĩa bằng `CREATE PROCEDURE` như PostgreSQL không?

**Đáp án:** Không có cú pháp built-in tương đương. Logic thường nằm ở SQL/transaction của ứng dụng, trigger hoặc user-defined function đăng ký từ code.

### Bài 21. Bảo mật stored procedure

**Câu hỏi:** procedure có `SECURITY DEFINER` và nhận `p_to_chuc_id` từ client. Có thể tin client tự truyền đúng tổ chức không?

**Đáp án:** Không. Phải xác thực context, kiểm tra quyền/tenant, hạn chế `search_path`/dynamic SQL và cấp quyền EXECUTE theo least privilege. Stored procedure không tự triệt tiêu lỗi phân quyền.

### Bài 22. Set-based so với LOOP

**Yêu cầu:** xác nhận các đơn MOI có tổng tiền từ 500.000 trở lên.

~~~sql
UPDATE bai335.don_hang
SET trang_thai = 'DA_XAC_NHAN'
WHERE trang_thai = 'MOI'
  AND tong_tien >= 500000;
~~~

**Đáp án:** Một câu UPDATE theo tập thường rõ hơn vòng FOR thực hiện hàng loạt UPDATE theo ID, trừ khi có nghiệp vụ riêng ở từng hàng.

### Bài 23. Chọn kiến trúc cho báo cáo

**Tình huống:** cần trả danh sách đơn theo trạng thái và ngày, được nhiều dashboard dùng, không sửa dữ liệu.

**Gợi ý:** cân nhắc SQL trực tiếp, VIEW hoặc SQL-language table-valued function có tham số. Không tự động chọn stored procedure chỉ vì logic “nằm trong database”. Đo execution plan và đảm bảo index phù hợp.

### Bài 24. Tạo đơn và log

**Tình huống:** tạo đơn và log là hai bước bắt buộc. Nếu log thất bại thì phải làm gì?

**Đáp án:** Không commit nửa giao dịch. Trong transaction bình thường, lỗi chưa được xử lý cần dẫn tới rollback thích hợp. Nếu logic bắt và bỏ lỗi log, đó là **thay đổi hợp đồng nghiệp vụ**, phải được quyết định trước, không phải hiệu ứng mặc định của procedure.

### Bài 25. Phân biệt kết quả và tính bền vững

**Câu hỏi:** CALL procedure trả p_id thành công, nhưng transaction sau đó ROLLBACK. Đơn có chắc tồn tại không?

**Đáp án:** Không. OUT/INOUT là kết quả thực thi tại thời điểm CALL, không xác nhận dữ liệu đã commit. Giá trị sequence cấp có thể vẫn bị tiêu thụ dù rollback.

## 28. Những lỗi phổ biến cần tránh

| Sai lầm | Vì sao sai | Cách hiểu/thiết kế đúng |
| --- | --- | --- |
| “Hàm thủ tục là stored procedure.” | PL/pgSQL function vẫn là function. | Xem CREATE FUNCTION hay CREATE PROCEDURE. |
| “LANGUAGE SQL nghĩa là function không bao giờ ghi.” | PostgreSQL SQL functions có thể có hành vi DML trong điều kiện hợp lệ. | Phân biệt ngôn ngữ với volatility/side effects. |
| “Có IF/LOOP nên phải dùng procedure.” | Procedural function cũng có điều kiện và vòng lặp. | Chọn theo hợp đồng gọi và trả kết quả. |
| “Procedure không thể trả kết quả.” | OUT/INOUT, result sets và cursor có thể được hỗ trợ. | Xem cơ chế DBMS. |
| “Function luôn trả một ô.” | Table-valued/set-returning functions trả nhiều hàng/cột. | Xem RETURNS/RETURNS TABLE. |
| “SELECT function ghi dữ liệu luôn được trên mọi hệ.” | SQL Server UDF/Oracle có hạn chế khác PostgreSQL. | Đọc quy tắc DBMS. |
| “CALL tự COMMIT.” | Thường thuộc transaction caller; transaction control có điều kiện. | Quản lý COMMIT/ROLLBACK rõ ràng. |
| “PostgreSQL procedure COMMIT ở bất cứ đâu.” | Có hạn chế ngữ cảnh CALL, transaction block, SECURITY DEFINER/SET, EXCEPTION. | Chỉ dùng trong điều kiện được phép. |
| “OUT parameter đồng nghĩa COMMIT.” | Chỉ là kênh trả giá trị. | Chờ transaction thành công. |
| “IMMUTABLE giúp tối ưu nên cứ khai báo.” | Khai báo sai có thể gây kết quả không đúng. | Khai volatility trung thực. |
| “Function trong WHERE luôn dùng index trên cột.” | Hàm/cast có thể thay biểu thức truy cập. | Xem EXPLAIN và expression index khi phù hợp. |
| “Càng nhiều LOOP thì càng nhanh.” | Row-by-row DML có overhead. | Ưu tiên set-based khi có thể. |
| “Procedure đảm bảo không bị SQL injection.” | Dynamic SQL vẫn có thể nối input nguy hiểm. | Bind tham số, quote định danh, least privilege. |
| “Chỉ cần quyền EXECUTE là đủ an toàn.” | Routine có thể truy cập dữ liệu ngoài phạm vi caller. | Kiểm tra quyền, RLS/tenant, SECURITY DEFINER. |
| “Một lần gọi routine luôn tương đương một lần gọi function thân.” | Query optimizer có thể đánh giá biểu thức theo kế hoạch. | Tránh dựa vào số lần gọi với side effects. |
| “Function đơn giản nào cũng cần stored routine.” | Làm tăng chi phí triển khai và bảo trì. | Cân nhắc SQL trực tiếp/view. |
| “SQLite có CREATE PROCEDURE giống PostgreSQL.” | SQLite không có SQL stored procedure built-in tương đương. | Dùng API UDF/transaction/trigger khi phù hợp. |
| “Một stored procedure thay thế được transaction của ứng dụng.” | Workflow có thể gồm nhiều thao tác và side effects ngoài DB. | Xác định transaction owner và idempotency. |

## 29. Checklist trước khi tạo routine trong dự án

1. **Mục tiêu là tính giá trị hay thực thi tác vụ?** Nếu chỉ tính hoặc trả tập hàng, cân nhắc function; nếu điều phối DML, cân nhắc procedure/SQL trực tiếp.
2. **Nguồn của logic là SQL expression hay điều khiển luồng?** Một CASE/SELECT có đủ chưa?
3. **DBMS và phiên bản nào?** PostgreSQL, MySQL, SQL Server, Oracle và SQLite khác nhau.
4. **Đầu vào và đầu ra rõ chưa?** Kiểu, NULL, OUT/INOUT, bảng kết quả, nhiều hàng hay một hàng?
5. **Routine có side effect không?** Nếu có, việc gọi từ SELECT có gây bất ngờ hoặc thực hiện nhiều lần không?
6. **Transaction owner là ai?** Caller hay routine? Có được COMMIT bên trong không?
7. **Khi một câu DML ảnh hưởng 0 hàng phải xử lý thế nào?**
8. **Khi lỗi giữa quy trình, các thay đổi trước đó có bị rollback đúng không?**
9. **Volatility/determinism có được khai báo trung thực không?**
10. **Quyền EXECUTE, SECURITY DEFINER/INVOKER, search_path và tenant scope đã chặt chẽ chưa?**
11. **SQL động có bind/quote đúng không?**
12. **Bài toán có thể xử lý set-based thay vì LOOP không?**
13. **Routine có khiến optimizer mất khả năng pushdown/index usage không?**
14. **Có tránh các lời gọi N+1 và log/side effects không thể rollback không?**
15. **Có test input hợp lệ, NULL, lỗi constraint, concurrency, retry và quyền không?**
16. **Có kế hoạch triển khai phiên bản/thay đổi signature và rollback migration không?**
17. **Có tài liệu hóa hợp đồng để ứng dụng khác không nhầm function với procedure không?**

## 30. Tài liệu tham khảo chính thức

Đặc điểm và cú pháp có thể thay đổi giữa phiên bản. Khi triển khai, nên kiểm tra tài liệu của máy chủ/driver đang dùng:

- **PostgreSQL:** [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html), [CREATE PROCEDURE](https://www.postgresql.org/docs/current/sql-createprocedure.html), [CALL](https://www.postgresql.org/docs/current/sql-call.html), [PL/pgSQL](https://www.postgresql.org/docs/current/plpgsql.html), [Volatility Categories](https://www.postgresql.org/docs/current/xfunc-volatility.html), [Transaction Management in PL/pgSQL](https://www.postgresql.org/docs/current/plpgsql-transactions.html).
- **MySQL:** [CREATE PROCEDURE and CREATE FUNCTION](https://dev.mysql.com/doc/refman/8.4/en/create-procedure.html), [Stored Program Restrictions](https://dev.mysql.com/doc/refman/8.4/en/stored-program-restrictions.html).
- **SQL Server:** [CREATE FUNCTION](https://learn.microsoft.com/en-us/sql/t-sql/statements/create-function-transact-sql), [CREATE PROCEDURE](https://learn.microsoft.com/en-us/sql/t-sql/statements/create-procedure-transact-sql), [Scalar UDF Inlining](https://learn.microsoft.com/en-us/sql/relational-databases/user-defined-functions/scalar-udf-inlining).
- **Oracle:** [PL/SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/index.html), [CREATE FUNCTION](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-FUNCTION.html), [CREATE PROCEDURE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-PROCEDURE.html).
- **SQLite:** [Application-Defined SQL Functions](https://www.sqlite.org/appfunc.html), [SQL CREATE TRIGGER](https://www.sqlite.org/lang_createtrigger.html).

## 31. Kết luận

Để phân biệt **hàm SQL, hàm thủ tục và stored procedure**, hãy đặt đúng hai câu hỏi:

**(1) Đối tượng này là FUNCTION hay PROCEDURE?** Function có hợp đồng trả giá trị hoặc tập hàng và thường được dùng trong biểu thức/SELECT/FROM. Procedure có hợp đồng gọi tác vụ bằng CALL/EXEC, có thể trả tham số OUT/INOUT hoặc result set theo DBMS.

**(2) Nếu là FUNCTION thì thân được viết bằng ngôn ngữ nào?** PostgreSQL `LANGUAGE SQL` phù hợp với biểu thức/truy vấn đóng gói; `LANGUAGE plpgsql` thích hợp với biến, điều kiện, vòng lặp và xử lý lỗi. **Cả hai đều là function**.

Những nguyên tắc áp dụng thực tế:

- Không đánh đồng “hàm SQL” với “luôn read-only”, hoặc “hàm thủ tục” với “stored procedure”.
- Không khẳng định mọi procedure tự COMMIT; transaction semantics phụ thuộc DBMS và caller.
- Ưu tiên **SQL theo tập** cho thao tác dữ liệu có thể diễn đạt set-based; chỉ dùng procedural loop khi có lý do.
- Khai đúng **volatility/determinism**, không đưa side effect bất ngờ vào function gọi trong SELECT.
- Giữ ranh giới **quyền, validation, transaction, idempotency và bảo mật** rõ ràng.
- Khi chuyển DBMS, cần chuyển cả **semantics** chứ không chỉ thay `CALL` thành `EXEC`.

**Ghi nhớ:** hàm SQL và hàm thủ tục là hai cách viết **function**; stored procedure là một **loại routine khác**. Chọn đúng công cụ bằng cách nhìn vào **đầu ra mong muốn, hành vi thay đổi dữ liệu, ngữ cảnh gọi và quyền kiểm soát transaction**.
