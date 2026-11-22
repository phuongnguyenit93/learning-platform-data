# IF, CASE, vòng lặp và điều kiện kết thúc

## 1. Vì sao thủ tục và hàm SQL cần điều khiển luồng?

SQL thường được học qua các câu truy vấn mang tính **khai báo**: người viết yêu cầu *kết quả cần lấy hoặc dữ liệu cần thay đổi*, còn cơ sở dữ liệu quyết định cách thực thi.

~~~sql
SELECT order_id, total_amount
FROM sales_orders
WHERE total_amount >= 500;
~~~

Nhưng khi viết **hàm (function)**, **thủ tục (procedure)** hoặc một khối lệnh SQL có tính thủ tục, ta có thể cần nhiều bước phụ thuộc điều kiện:

- Nếu đơn hàng đã thanh toán thì từ chối xử lý lần hai; nếu còn mới thì tiếp tục.
- Nếu số tiền lớn thì đưa vào hàng kiểm tra; ngược lại đưa vào hàng xử lý thông thường.
- Lặp qua một số lần thử, nhưng dừng khi đã đạt mục tiêu hoặc vượt giới hạn.
- Duyệt một tập bản ghi để thực hiện tác động đặc thù với từng bản ghi.
- Thoát khỏi vòng lặp, bỏ qua lần lặp hiện tại hoặc kết thúc cả hàm.

Những yêu cầu đó cần **cấu trúc điều khiển luồng**.

Trong bài này, ta phân biệt các khái niệm:

| Cấu trúc | Trả lời câu hỏi | Phạm vi thường gặp |
| --- | --- | --- |
| `IF ... THEN ... ELSIF ... ELSE ... END IF` | Có thực hiện nhánh lệnh này không? | PL/pgSQL và ngôn ngữ thủ tục |
| `CASE ... WHEN ... THEN ... END CASE` | Thực hiện nhóm lệnh nào trong nhiều trường hợp? | Câu lệnh `CASE` của thủ tục |
| `CASE ... WHEN ... THEN ... END` | Biểu thức này trả **giá trị** gì? | SQL `SELECT`, `UPDATE`, `ORDER BY`... |
| `LOOP ... END LOOP` | Lặp vô điều kiện, chờ lệnh thoát bên trong | Ngôn ngữ thủ tục |
| `WHILE ... LOOP` | Lặp khi điều kiện còn đúng | Ngôn ngữ thủ tục |
| `FOR ... LOOP` | Duyệt khoảng số hoặc kết quả truy vấn | Ngôn ngữ thủ tục |
| `FOREACH ... IN ARRAY` | Duyệt phần tử của mảng | PL/pgSQL |
| `EXIT [label] [WHEN ...]` | Rời vòng lặp hoặc khối có nhãn | PL/pgSQL |
| `CONTINUE [label] [WHEN ...]` | Bỏ phần còn lại của một lượt, sang lượt kế tiếp | PL/pgSQL |
| `RETURN` | Kết thúc hàm/thủ tục hoặc trả kết quả | Function/procedure |
| `RAISE EXCEPTION` | Từ chối xử lý bằng lỗi | PL/pgSQL |

**Mục tiêu:** hiểu ngữ nghĩa, viết ví dụ chạy được, kiểm soát điều kiện kết thúc và không lạm dụng vòng lặp để thay thế thao tác SQL theo tập.

Bài thuộc **Database SQL → Thủ tục và hàm**. Nội dung chính lấy **PostgreSQL PL/pgSQL** làm hệ quy chiếu, rồi so sánh với MySQL stored routines, SQL Server T-SQL, Oracle PL/SQL và SQLite.

## 2. Phân biệt SQL khai báo với PL/pgSQL thủ tục

### 2.1. Một câu SELECT có thể chứa CASE mà không cần thủ tục

~~~sql
SELECT
    order_id,
    total_amount,
    CASE
        WHEN total_amount >= 500 THEN 'HIGH'
        WHEN total_amount > 0 THEN 'NORMAL'
        ELSE 'ZERO'
    END AS amount_band
FROM sales_orders;
~~~

`CASE ... END` trong ví dụ là **biểu thức SQL**: nó trả một **giá trị** cho cột `amount_band` của từng hàng.

Không có `IF ... END IF`, không có vòng lặp do người viết điều khiển, và không phải tạo function/procedure.

### 2.2. IF và vòng lặp là câu lệnh của ngôn ngữ thủ tục

PostgreSQL hỗ trợ ngôn ngữ **PL/pgSQL** với các khối:

~~~sql
DO $$
DECLARE
    v_amount NUMERIC(12, 2) := 120.00;
    v_band   TEXT;
BEGIN
    IF v_amount >= 500 THEN
        v_band := 'HIGH';
    ELSIF v_amount > 0 THEN
        v_band := 'NORMAL';
    ELSE
        v_band := 'ZERO';
    END IF;

    RAISE NOTICE 'Amount band: %', v_band;
END;
$$ LANGUAGE plpgsql;
~~~

Kết quả ở mức thông báo là `Amount band: NORMAL`.

Khối này **thực thi các câu lệnh** tùy điều kiện. Nó có biến `v_amount`, phép gán `:=`, `IF` và `RAISE NOTICE`; các cấu trúc này không nằm trong cú pháp một `SELECT` SQL thông thường.

### 2.3. DO, FUNCTION và PROCEDURE khác nhau

| Loại | Cách khai báo | Cách gọi | Khi dùng |
| --- | --- | --- | --- |
| Khối vô danh | `DO $$ ... $$ LANGUAGE plpgsql;` | Chạy trực tiếp | Thử nghiệm hoặc tác vụ một lần |
| Hàm | `CREATE FUNCTION ... RETURNS ... LANGUAGE plpgsql AS $$...$$` | `SELECT function_name(...)` hoặc trong SQL phù hợp | Tính toán, trả giá trị hoặc tập hàng |
| Thủ tục | `CREATE PROCEDURE ... LANGUAGE plpgsql AS $$...$$` | `CALL procedure_name(...)` | Một quy trình thao tác nhiều bước, thay đổi dữ liệu hoặc side effects |
| SQL thông thường | `SELECT`, `UPDATE`, `INSERT`... | Gửi câu SQL | Thao tác tập dữ liệu, thường là ưu tiên đầu tiên |

Không phải mọi DBMS đều có `DO` hoặc cùng cách phân biệt function/procedure. Cú pháp `CALL`, quyền điều khiển giao dịch và khả năng trả tập hàng sẽ thay đổi theo hệ.

### 2.4. BEGIN...END trong PL/pgSQL không tự là BEGIN TRANSACTION

~~~sql
DO $$
BEGIN
    RAISE NOTICE 'Inside procedural block';
END;
$$;
~~~

`BEGIN` và `END` ở đây **đánh dấu khối lệnh thủ tục**. Chúng **không tự mở/commit một transaction** theo cùng nghĩa với:

~~~sql
BEGIN;        -- Mở transaction SQL
UPDATE ...;   -- Thao tác thuộc transaction
COMMIT;       -- Kết thúc transaction
~~~

Cần tách **cấu trúc chương trình** khỏi **ranh giới transaction**. Trong PostgreSQL, function không thể tùy ý điều khiển transaction bằng `COMMIT`/`ROLLBACK`; procedure/DO chỉ có một số ngữ cảnh cho phép transaction control với điều kiện cụ thể, ví dụ việc gọi top-level và không có hạn chế khác. Bài này không thực hiện `COMMIT` bên trong function/procedure.

### 2.5. Dấu chấm phẩy, dollar quoting và tên biến

Các thành phần thường thấy:

~~~sql
DO $body$
DECLARE
    v_count INTEGER := 0;
BEGIN
    v_count := v_count + 1;
    RAISE NOTICE 'v_count=%', v_count;
END;
$body$ LANGUAGE plpgsql;
~~~

- `$body$ ... $body$` (hoặc `$$ ... $$`) là **chuỗi chứa thân khối**; giúp tránh phải escape nhiều dấu nháy đơn.
- `DECLARE` khai báo biến trong khối.
- `:=` gán giá trị cho biến PL/pgSQL.
- Dấu `;` kết thúc các câu lệnh bên trong khối.
- `END;` kết thúc khối. Dấu `;` sau chuỗi body kết thúc câu lệnh `DO`/`CREATE FUNCTION` ở SQL ngoài.

Tên biến có tiền tố `v_` và tham số có tiền tố `p_` là **quy ước dễ đọc**, không bắt buộc về cú pháp. Quy ước giúp giảm nhập nhằng giữa biến PL/pgSQL và tên cột SQL.

## 3. Dữ liệu mẫu xuyên suốt

Tạo bảng đơn hàng dùng cho các ví dụ quản lý trạng thái và vòng lặp. SQL sau dùng PostgreSQL.

### 3.1. Tạo bảng

~~~sql
CREATE TABLE sales_orders (
    order_id      INTEGER PRIMARY KEY,
    customer_id   INTEGER NOT NULL,
    total_amount  NUMERIC(12, 2) NOT NULL,
    order_status  VARCHAR(20) NOT NULL DEFAULT 'NEW',
    attempts      INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed_at  TIMESTAMPTZ,

    CONSTRAINT chk_sales_amount
        CHECK (total_amount >= 0),
    CONSTRAINT chk_sales_attempts
        CHECK (attempts >= 0),
    CONSTRAINT chk_sales_status
        CHECK (
            order_status IN (
                'NEW', 'PROCESSING', 'REVIEW',
                'PAID', 'CANCELLED'
            )
        )
);
~~~

Định nghĩa trạng thái **cho ví dụ**, không phải quy trình thanh toán production:

- `NEW`: đơn mới, chưa được phân loại xử lý.
- `PROCESSING`: đã được nhận để xử lý tiếp, **chưa đồng nghĩa đã thu tiền**.
- `REVIEW`: cần kiểm tra thủ công.
- `PAID`: ghi nhận hoàn tất thanh toán theo hệ thống có thẩm quyền.
- `CANCELLED`: đơn bị hủy.

`attempts` dùng minh họa bộ đếm lần xử lý. Trong hệ thống thực, cần làm rõ idempotency, retry, audit và vai trò của các trạng thái.

### 3.2. Nạp tám đơn hàng

~~~sql
INSERT INTO sales_orders (
    order_id, customer_id, total_amount, order_status, attempts
)
VALUES
    (101, 10, 120.00, 'NEW',       0),
    (102, 10, 800.00, 'NEW',       0),
    (103, 20,   0.00, 'NEW',       0),
    (104, 20, 250.00, 'PAID',      1),
    (105, 30,  75.00, 'CANCELLED', 0),
    (106, 30, 600.00, 'NEW',       1),
    (107, 40, 300.00, 'REVIEW',    2),
    (108, 40,  50.00, 'NEW',       0);
~~~

| order_id | total_amount | order_status | attempts |
| ---: | ---: | --- | ---: |
| 101 | 120.00 | NEW | 0 |
| 102 | 800.00 | NEW | 0 |
| 103 | 0.00 | NEW | 0 |
| 104 | 250.00 | PAID | 1 |
| 105 | 75.00 | CANCELLED | 0 |
| 106 | 600.00 | NEW | 1 |
| 107 | 300.00 | REVIEW | 2 |
| 108 | 50.00 | NEW | 0 |

Bài sẽ dùng bộ dữ liệu này để:

- Phân loại tiền bằng `IF` và `CASE`;
- Cập nhật trạng thái hợp lệ;
- Duyệt các đơn `NEW`;
- Kiểm soát điều kiện lặp và thoát;
- So sánh vòng lặp với một câu `UPDATE` theo tập.

### 3.3. Thực hành trên transaction thử nghiệm

Với ví dụ thay đổi dữ liệu, có thể dùng:

~~~sql
BEGIN;

-- Gọi procedure hoặc chạy DO/UPDATE trên bảng mẫu.

SELECT order_id, order_status, attempts
FROM sales_orders
ORDER BY order_id;

ROLLBACK;
~~~

Trong PostgreSQL, `ROLLBACK` hoàn tác các thay đổi dữ liệu transactional của ví dụ. Nếu một câu lệnh gây lỗi và transaction chuyển sang trạng thái failed, cần `ROLLBACK` (hoặc savepoint phù hợp) trước khi tiếp tục.

**Không chạy tùy tiện những khối cập nhật hàng loạt trên production.** Các ví dụ được giải thích từ dữ liệu ban đầu, nên thực hành từng đoạn và rollback/reset dữ liệu giữa các lần chạy để kết quả dễ đối chiếu.

## 4. IF ... THEN ... ELSIF ... ELSE ... END IF

### 4.1. IF đơn giản

Cú pháp PostgreSQL PL/pgSQL:

~~~sql
IF condition THEN
    statements;
END IF;
~~~

Ví dụ:

~~~sql
DO $$
DECLARE
    v_amount NUMERIC(12, 2) := 800.00;
BEGIN
    IF v_amount >= 500 THEN
        RAISE NOTICE 'Can kiem tra thu cong';
    END IF;
END;
$$ LANGUAGE plpgsql;
~~~

Vì `v_amount >= 500` là `TRUE`, thông báo được phát ra.

`IF` quyết định **chạy hoặc bỏ qua một nhóm câu lệnh**, chứ không trực tiếp trả giá trị như biểu thức `CASE` của SQL.

### 4.2. IF...ELSE: đúng một trong hai nhánh

~~~sql
DO $$
DECLARE
    v_stock INTEGER := 0;
BEGIN
    IF v_stock > 0 THEN
        RAISE NOTICE 'Con hang';
    ELSE
        RAISE NOTICE 'Khong con hang';
    END IF;
END;
$$;
~~~

Kết quả: `Khong con hang`.

`ELSE` xử lý mọi trường hợp **không đi vào nhánh IF**. Với các điều kiện có thể nhận `NULL`, hãy chú ý logic ba giá trị ở mục 5.

### 4.3. IF...ELSIF...ELSE: nhiều điều kiện có thứ tự ưu tiên

~~~sql
DO $$
DECLARE
    v_amount NUMERIC := 120.00;
    v_band TEXT;
BEGIN
    IF v_amount >= 500 THEN
        v_band := 'HIGH';
    ELSIF v_amount >= 100 THEN
        v_band := 'MEDIUM';
    ELSIF v_amount > 0 THEN
        v_band := 'LOW';
    ELSE
        v_band := 'ZERO_OR_UNKNOWN';
    END IF;

    RAISE NOTICE 'Band=%', v_band;
END;
$$;
~~~

Kết quả: `Band=MEDIUM`.

Các điều kiện được xét **theo thứ tự** và nhánh đầu tiên có điều kiện đúng sẽ chạy. Nếu `v_amount = 600`, nhánh HIGH chạy, các nhánh sau không được chọn.

Trong **PostgreSQL PL/pgSQL**, từ khóa là **`ELSIF`**. Một số ngôn ngữ/DBMS khác dùng `ELSEIF`; không chép nguyên cú pháp giữa các hệ.

### 4.4. Lỗi phổ biến: sắp nhánh từ rộng đến hẹp

~~~sql
-- Ví dụ logic sai.
IF v_amount > 0 THEN
    v_band := 'POSITIVE';
ELSIF v_amount >= 500 THEN
    v_band := 'HIGH';
ELSE
    v_band := 'ZERO';
END IF;
~~~

Với `v_amount=800`, nhánh `v_amount > 0` đã đúng, nên nhánh HIGH **không bao giờ được chọn**. Đây là lỗi logic chứ không phải lỗi cú pháp.

Khi các điều kiện chồng lấn, hãy đặt các trường hợp **cụ thể/ưu tiên cao trước** và giải thích chính sách chọn nhánh.

### 4.5. IF lồng nhau

~~~sql
DO $$
DECLARE
    v_status TEXT := 'NEW';
    v_amount NUMERIC := 600.00;
BEGIN
    IF v_status = 'NEW' THEN
        IF v_amount >= 500 THEN
            RAISE NOTICE 'Don moi can review';
        ELSE
            RAISE NOTICE 'Don moi xu ly thong thuong';
        END IF;
    ELSE
        RAISE NOTICE 'Don khong o trang thai NEW';
    END IF;
END;
$$;
~~~

Lồng nhau phù hợp khi điều kiện thứ hai chỉ có ý nghĩa **sau khi điều kiện đầu đúng**. Nhưng quá nhiều tầng IF có thể khó đọc; khi mỗi nhánh chỉ trả một giá trị, cân nhắc `CASE`, bảng cấu hình hoặc tách function nhỏ.

## 5. NULL và logic ba giá trị trong IF

### 5.1. TRUE, FALSE và UNKNOWN

Trong SQL, phép so sánh liên quan `NULL` thường cho kết quả **UNKNOWN/NULL** chứ không phải `TRUE` hay `FALSE`.

~~~sql
SELECT
    NULL = 0      AS null_equals_zero,
    NULL <> 0     AS null_not_equal_zero,
    NULL IS NULL  AS null_is_missing;
~~~

Hai biểu thức so sánh đầu có giá trị `NULL`, còn `NULL IS NULL` là `TRUE`.

### 5.2. IF chỉ đi vào nhánh THEN khi điều kiện TRUE

Trong PL/pgSQL:

~~~sql
DO $$
DECLARE
    v_amount NUMERIC := NULL;
BEGIN
    IF v_amount >= 500 THEN
        RAISE NOTICE 'HIGH';
    ELSE
        RAISE NOTICE 'Khong thoa dieu kien HIGH';
    END IF;
END;
$$;
~~~

Nhánh ELSE chạy, vì `v_amount >= 500` nhận `NULL` chứ không phải TRUE.

**Nhưng nhánh ELSE không chứng minh giá trị chắc chắn nhỏ hơn 500!** Nó còn bao gồm trường hợp **chưa biết**. Nếu nghiệp vụ cần phân biệt thiếu dữ liệu, kiểm tra `IS NULL` trước.

~~~sql
DO $$
DECLARE
    v_amount NUMERIC := NULL;
BEGIN
    IF v_amount IS NULL THEN
        RAISE NOTICE 'Thieu so tien';
    ELSIF v_amount >= 500 THEN
        RAISE NOTICE 'HIGH';
    ELSE
        RAISE NOTICE 'BELOW_HIGH';
    END IF;
END;
$$;
~~~

### 5.3. Không dùng = NULL

~~~sql
-- Sai mục đích:
IF v_amount = NULL THEN
    RAISE NOTICE 'Missing';
END IF;
~~~

Dùng:

~~~sql
IF v_amount IS NULL THEN
    RAISE NOTICE 'Missing';
END IF;
~~~

Nếu cần so sánh an toàn giữa hai giá trị có thể NULL trong PostgreSQL:

~~~sql
IF v_old_value IS DISTINCT FROM v_new_value THEN
    RAISE NOTICE 'Gia tri da thay doi';
END IF;
~~~

`IS DISTINCT FROM` trả TRUE/FALSE ngay cả khi có NULL, giúp phát hiện việc thay đổi từ NULL sang giá trị cụ thể hoặc ngược lại.

### 5.4. AND và OR không thay kiểm soát dữ liệu đầu vào

Một biểu thức:

~~~sql
IF p_amount IS NOT NULL AND p_amount > 0 THEN
    ...
END IF;
~~~

có ý nghĩa “có số tiền và số tiền dương”. Nhưng với các hàm gây side effect hay phép tính có thể gây lỗi, không nên giả định **mọi phép toán trong SQL/PL/pgSQL luôn được đánh giá theo thứ tự viết**. Bộ tối ưu SQL và cơ chế biểu thức có thể có quy tắc riêng.

Khi cần bảo vệ trước phép chia hoặc ép kiểu nguy hiểm, hãy dùng nhánh kiểm tra tường minh hay biểu thức an toàn thích hợp:

~~~sql
IF p_denominator IS NULL OR p_denominator = 0 THEN
    RAISE EXCEPTION 'Mau so phai khac 0 va khong NULL';
END IF;

v_result := p_numerator / p_denominator;
~~~

Đoạn này nằm trong function/procedure giả định có các biến `p_denominator`, `p_numerator` và `v_result` đã khai báo.

## 6. Viết function sử dụng IF

### 6.1. Function trả nhãn mức tiền

~~~sql
CREATE OR REPLACE FUNCTION classify_amount(
    p_amount NUMERIC
)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_amount IS NULL THEN
        RETURN 'UNKNOWN';
    ELSIF p_amount < 0 THEN
        RAISE EXCEPTION 'So tien am: %', p_amount;
    ELSIF p_amount >= 500 THEN
        RETURN 'HIGH';
    ELSIF p_amount >= 100 THEN
        RETURN 'MEDIUM';
    ELSIF p_amount > 0 THEN
        RETURN 'LOW';
    ELSE
        RETURN 'ZERO';
    END IF;
END;
$$;
~~~

Dùng:

~~~sql
SELECT
    classify_amount(NULL)   AS missing_band,
    classify_amount(0)      AS zero_band,
    classify_amount(50)     AS low_band,
    classify_amount(120)    AS medium_band,
    classify_amount(800)    AS high_band;
~~~

| missing_band | zero_band | low_band | medium_band | high_band |
| --- | --- | --- | --- | --- |
| UNKNOWN | ZERO | LOW | MEDIUM | HIGH |

Gọi `classify_amount(-5)` làm function phát sinh exception theo chính sách ví dụ. Dữ liệu gốc `sales_orders.total_amount` đã có constraint không âm, nhưng function còn được gọi độc lập từ ứng dụng hoặc giá trị khác nên vẫn có thể kiểm tra tham số.

### 6.2. RETURN kết thúc ngay function

Khi chạy:

~~~sql
IF p_amount >= 500 THEN
    RETURN 'HIGH';
END IF;
~~~

một lệnh `RETURN` thành công làm **kết thúc function tại điểm đó**, không chạy tiếp các câu lệnh thông thường phía sau trong cùng nhánh.

Trong function trả một giá trị, phải bảo đảm mọi đường điều khiển cần thiết đều trả kết quả hợp lệ hoặc chủ động ném lỗi. Không dựa vào việc “chạy hết thân function” sẽ tự trả một giá trị kỳ vọng nếu chưa định nghĩa.

### 6.3. Cùng yêu cầu có thể viết bằng SQL CASE

Nếu chỉ cần phân loại bằng biểu thức, có thể không cần PL/pgSQL:

~~~sql
SELECT
    order_id,
    total_amount,
    CASE
        WHEN total_amount >= 500 THEN 'HIGH'
        WHEN total_amount >= 100 THEN 'MEDIUM'
        WHEN total_amount > 0 THEN 'LOW'
        ELSE 'ZERO'
    END AS amount_band
FROM sales_orders
ORDER BY order_id;
~~~

Vì `total_amount` của bảng mẫu `NOT NULL` và không âm, nhánh ELSE tương ứng số 0. Đây thường là cách **đơn giản hơn, dễ tối ưu hơn** khi chỉ biến đổi dữ liệu theo tập trong một câu SELECT.

Function PL/pgSQL trở nên có ích khi cần tái sử dụng quy tắc dưới tên function, kiểm tra lỗi phức tạp hoặc phối hợp nhiều bước có trạng thái điều khiển.

## 7. CASE biểu thức SQL và CASE câu lệnh PL/pgSQL

Hai cấu trúc dùng tên `CASE` nhưng **không giống nhau về nơi dùng và kết quả**.

### 7.1. CASE biểu thức trong SQL

Cấu trúc tìm kiếm (*searched CASE*):

~~~sql
CASE
    WHEN condition_1 THEN value_1
    WHEN condition_2 THEN value_2
    ELSE fallback_value
END
~~~

Ví dụ:

~~~sql
SELECT
    order_id,
    order_status,
    CASE
        WHEN order_status = 'PAID' THEN 'Da thanh toan'
        WHEN order_status = 'CANCELLED' THEN 'Da huy'
        ELSE 'Chua hoan tat'
    END AS status_label
FROM sales_orders;
~~~

`CASE ... END` trả **một giá trị** cho `status_label`. Nó có thể xuất hiện trong `SELECT`, `ORDER BY` hoặc biểu thức của `UPDATE SET`.

Dạng đơn giản (*simple CASE*) so sánh một biểu thức với các giá trị:

~~~sql
SELECT
    order_id,
    CASE order_status
        WHEN 'NEW'        THEN 'Moi'
        WHEN 'PROCESSING' THEN 'Dang xu ly'
        WHEN 'REVIEW'     THEN 'Can kiem tra'
        WHEN 'PAID'       THEN 'Da thanh toan'
        WHEN 'CANCELLED'  THEN 'Da huy'
        ELSE 'Khong xac dinh'
    END AS status_label
FROM sales_orders;
~~~

### 7.2. CASE câu lệnh trong PL/pgSQL

Trong khối thủ tục, `CASE` có thể quyết định **thực hiện nhóm câu lệnh**, không chỉ trả một giá trị biểu thức:

~~~sql
DO $$
DECLARE
    v_status TEXT := 'NEW';
    v_message TEXT;
BEGIN
    CASE v_status
        WHEN 'NEW' THEN
            v_message := 'Cho tiep nhan';
        WHEN 'PROCESSING' THEN
            v_message := 'Dang xu ly';
        WHEN 'REVIEW' THEN
            v_message := 'Can phe duyet';
        WHEN 'PAID' THEN
            v_message := 'Hoan tat';
        WHEN 'CANCELLED' THEN
            v_message := 'Da huy';
        ELSE
            v_message := 'Trang thai khong hop le';
    END CASE;

    RAISE NOTICE '%', v_message;
END;
$$;
~~~

**Dấu hiệu nhận biết:** statement PL/pgSQL kết thúc bằng **`END CASE;`**, trong khi biểu thức SQL kết thúc bằng **`END`** rồi tiếp tục cú pháp câu SQL bao ngoài.

### 7.3. CASE statement dạng searched

~~~sql
DO $$
DECLARE
    v_amount NUMERIC := 800;
    v_review BOOLEAN;
BEGIN
    CASE
        WHEN v_amount IS NULL THEN
            RAISE EXCEPTION 'Thieu so tien';
        WHEN v_amount >= 500 THEN
            v_review := TRUE;
        ELSE
            v_review := FALSE;
    END CASE;

    RAISE NOTICE 'Review required: %', v_review;
END;
$$;
~~~

Mỗi nhánh có thể chạy **nhiều câu lệnh**, ví dụ gán biến, thông báo hoặc truy vấn SQL, tùy nhu cầu.

### 7.4. Nếu không có ELSE thì điều gì xảy ra?

Đây là khác biệt quan trọng:

| Tình huống | SQL `CASE` biểu thức | PL/pgSQL `CASE` câu lệnh |
| --- | --- | --- |
| Có nhánh WHEN khớp | Trả giá trị của nhánh đó | Chạy nhóm câu lệnh của nhánh |
| Không nhánh nào khớp, có ELSE | Trả biểu thức ELSE | Chạy nhóm lệnh ELSE |
| Không nhánh nào khớp, **không có ELSE** | Giá trị biểu thức là **NULL** | PL/pgSQL phát sinh lỗi **`CASE_NOT_FOUND`** |
| Từ khóa kết thúc | `END` | `END CASE;` |

Ví dụ SQL:

~~~sql
SELECT CASE
    WHEN 1 = 2 THEN 'MATCH'
END AS result;
-- result = NULL
~~~

Ví dụ PL/pgSQL có lỗi nếu thực thi:

~~~sql
DO $$
DECLARE
    v_status TEXT := 'UNKNOWN';
BEGIN
    CASE v_status
        WHEN 'PAID' THEN
            RAISE NOTICE 'Paid';
        WHEN 'NEW' THEN
            RAISE NOTICE 'New';
    END CASE;
END;
$$;
-- PL/pgSQL: CASE_NOT_FOUND
~~~

Nếu một CASE statement được kỳ vọng bao phủ mọi giá trị, viết ELSE để xử lý trạng thái không mong muốn, ví dụ:

~~~sql
ELSE
    RAISE EXCEPTION 'Trang thai khong ho tro: %', v_status;
~~~

Trên MySQL và Oracle, CASE statement có cú pháp và xử lý lỗi không có nhánh phù hợp tương tự về ý tưởng nhưng mã lỗi/cú pháp chi tiết khác; không suy từ SQL CASE expression sang CASE statement.

### 7.5. Simple CASE và NULL

Một CASE đơn giản:

~~~sql
CASE v_status
    WHEN NULL THEN
        v_message := 'Missing';
    ELSE
        v_message := 'Other';
END CASE;
~~~

**Không phải cách kiểm tra NULL chuẩn**: so sánh bằng NULL không nhận TRUE như mong muốn. Sử dụng searched CASE hoặc IF:

~~~sql
CASE
    WHEN v_status IS NULL THEN
        v_message := 'Missing';
    ELSE
        v_message := 'Other';
END CASE;
~~~

### 7.6. CASE trong UPDATE thường thay vòng lặp

Yêu cầu: phân loại đơn `NEW` có tiền từ 500 trở lên sang `REVIEW`, còn lại sang `PROCESSING`. Trong PostgreSQL:

~~~sql
BEGIN;

UPDATE sales_orders
SET order_status = CASE
    WHEN total_amount >= 500 THEN 'REVIEW'
    ELSE 'PROCESSING'
END
WHERE order_status = 'NEW'
RETURNING
    order_id, total_amount, order_status;

ROLLBACK;
~~~

Trên dữ liệu mẫu, năm đơn NEW là 101, 102, 103, 106, 108. Kết quả:

| order_id | amount | status mới |
| ---: | ---: | --- |
| 101 | 120 | PROCESSING |
| 102 | 800 | REVIEW |
| 103 | 0 | PROCESSING |
| 106 | 600 | REVIEW |
| 108 | 50 | PROCESSING |

**Đây là một UPDATE theo tập**, thường rõ và hiệu quả hơn tạo vòng FOR để UPDATE từng hàng khi mọi hàng chỉ cần tính một biểu thức `CASE`.

## 8. LOOP và EXIT: vòng lặp không có điều kiện đầu

### 8.1. Cú pháp LOOP cơ bản

~~~sql
LOOP
    statements;
    EXIT WHEN exit_condition;
END LOOP;
~~~

Một `LOOP` không có điều kiện ở đầu có thể chạy **vô hạn** nếu không có đường thoát thực sự được thực hiện.

Ví dụ đếm từ 1 đến 5:

~~~sql
DO $$
DECLARE
    v_counter INTEGER := 0;
BEGIN
    LOOP
        v_counter := v_counter + 1;
        RAISE NOTICE 'Counter: %', v_counter;

        EXIT WHEN v_counter >= 5;
    END LOOP;
END;
$$;
~~~

Dãy thông báo:

~~~text
Counter: 1
Counter: 2
Counter: 3
Counter: 4
Counter: 5
~~~

Thứ tự câu lệnh rất quan trọng: **tăng → in → kiểm tra thoát**.

### 8.2. Điều kiện kết thúc đặt trước hay sau làm đổi kết quả

Hai cách:

~~~sql
LOOP
    v_counter := v_counter + 1;
    EXIT WHEN v_counter >= 5;
    RAISE NOTICE '%', v_counter;
END LOOP;
~~~

Nếu ban đầu bằng 0, cách này chỉ in **1, 2, 3, 4**. Lượt có `v_counter=5` bị thoát trước câu `RAISE NOTICE`.

Đối chiếu:

~~~sql
LOOP
    v_counter := v_counter + 1;
    RAISE NOTICE '%', v_counter;
    EXIT WHEN v_counter >= 5;
END LOOP;
~~~

cách này in **1, 2, 3, 4, 5**.

Đây là lỗi *off-by-one* rất thường gặp khi xử lý số lượt thử, phân trang hoặc tác vụ lặp.

### 8.3. EXIT WHEN tương đương điều kiện gác trong LOOP

~~~sql
DO $$
DECLARE
    v_attempt INTEGER := 0;
    v_max_attempt INTEGER := 3;
BEGIN
    LOOP
        EXIT WHEN v_attempt >= v_max_attempt;

        v_attempt := v_attempt + 1;
        RAISE NOTICE 'Thu lan %', v_attempt;
    END LOOP;
END;
$$;
~~~

Kết quả có **ba lượt**, không có vòng vô hạn vì biến đếm tăng đều và ngưỡng cố định.

Một vòng lặp đúng cần xác định:

1. **Trạng thái ban đầu**.
2. **Điều kiện kết thúc**.
3. **Thay đổi tiến độ** làm hệ tiến tới điều kiện kết thúc.
4. **Giới hạn an toàn** nếu trạng thái ngoài hệ có thể không bao giờ thay đổi.
5. **Hành vi khi hết lượt**: thành công, lỗi hay trả trạng thái đang chờ?

### 8.4. Không nên dùng LOOP để “đợi vô hạn” một điều kiện bên ngoài

Mẫu nguy hiểm:

~~~sql
-- Ý tưởng nguy hiểm, không chạy:
LOOP
    SELECT order_status
    INTO v_status
    FROM sales_orders
    WHERE order_id = 101;

    EXIT WHEN v_status = 'PAID';
END LOOP;
~~~

Rủi ro:

- Nếu trạng thái không bao giờ chuyển PAID, vòng lặp không kết thúc.
- Vòng lặp truy vấn liên tục gây tải CPU và database.
- Transaction có thể giữ snapshot cũ, nên không thấy thay đổi ngoài như mong đợi.
- Giữ transaction mở lâu có thể gây khóa, cản trở vacuum/cleanup hoặc tăng contention.
- Nếu không tìm thấy hàng, `v_status` có thể NULL và `EXIT WHEN v_status='PAID'` không bao giờ TRUE.

Thường nên đợi bằng **hàng đợi/scheduler/notification** hoặc cơ chế polling của ứng dụng với backoff, timeout, ranh giới transaction rõ, thay vì một vòng lặp SQL bận rộn vô hạn.

## 9. WHILE: kiểm tra điều kiện trước mỗi lượt

### 9.1. Cú pháp

~~~sql
WHILE boolean_condition LOOP
    statements;
END LOOP;
~~~

Ví dụ:

~~~sql
DO $$
DECLARE
    v_counter INTEGER := 1;
BEGIN
    WHILE v_counter <= 5 LOOP
        RAISE NOTICE 'Counter %', v_counter;
        v_counter := v_counter + 1;
    END LOOP;
END;
$$;
~~~

Dãy kết quả: 1, 2, 3, 4, 5.

Điều kiện `v_counter <= 5` được kiểm tra **trước khi vào mỗi lượt**. Nếu ban đầu `v_counter=6`, thân vòng lặp không chạy lần nào.

### 9.2. WHILE khác LOOP + EXIT WHEN ở đâu?

Hai mẫu tương đương về mục đích trong trường hợp này:

~~~sql
WHILE v_counter < 5 LOOP
    v_counter := v_counter + 1;
END LOOP;
~~~

và:

~~~sql
LOOP
    EXIT WHEN v_counter >= 5;
    v_counter := v_counter + 1;
END LOOP;
~~~

Cả hai dừng khi `v_counter` đạt ít nhất 5 nếu biến ban đầu hợp lệ và không có thay đổi khác.

**WHILE** thuận tiện khi điều kiện tiếp tục lặp rõ ràng ngay ở đầu. **LOOP + EXIT WHEN** thuận tiện khi phải thực hiện ít nhất một số bước trước mới biết có nên dừng, hoặc có nhiều điểm thoát.

### 9.3. Phải thay đổi biến điều khiển

Sai:

~~~sql
-- KHÔNG CHẠY: có thể lặp vô hạn.
DO $$
DECLARE
    v_counter INTEGER := 1;
BEGIN
    WHILE v_counter <= 5 LOOP
        RAISE NOTICE 'Counter %', v_counter;
        -- Thiếu v_counter := v_counter + 1;
    END LOOP;
END;
$$;
~~~

Vì `v_counter` luôn là 1, điều kiện luôn TRUE và vòng lặp không kết thúc.

Một phiên bản có bước tiến rõ:

~~~sql
WHILE v_counter <= 5 LOOP
    RAISE NOTICE '%', v_counter;
    v_counter := v_counter + 1;
END LOOP;
~~~

### 9.4. WHILE với điều kiện NULL

Nếu điều kiện của `WHILE` là NULL/UNKNOWN thay vì TRUE, trong PL/pgSQL thân vòng lặp không được thực thi. Ví dụ:

~~~sql
DO $$
DECLARE
    v_limit INTEGER := NULL;
    v_counter INTEGER := 0;
BEGIN
    WHILE v_counter < v_limit LOOP
        v_counter := v_counter + 1;
    END LOOP;

    RAISE NOTICE 'Counter=%', v_counter;
END;
$$;
~~~

Kết quả `Counter=0`. Nhưng việc bỏ qua lặp do `NULL` chưa chắc đúng nghiệp vụ. Nếu `v_limit` là tham số bắt buộc, hãy kiểm tra và từ chối:

~~~sql
IF p_limit IS NULL OR p_limit < 0 THEN
    RAISE EXCEPTION 'p_limit phai khac NULL va khong am';
END IF;
~~~

### 9.5. Mẫu giới hạn retry nhưng không tự retry mọi lỗi

~~~sql
DO $$
DECLARE
    v_attempt INTEGER := 0;
    v_max_attempt INTEGER := 3;
    v_done BOOLEAN := FALSE;
BEGIN
    WHILE v_attempt < v_max_attempt AND NOT v_done LOOP
        v_attempt := v_attempt + 1;

        -- Chỉ minh họa một điều kiện hoàn thành:
        IF v_attempt = 2 THEN
            v_done := TRUE;
        END IF;

        RAISE NOTICE 'Attempt %, done=%', v_attempt, v_done;
    END LOOP;

    IF NOT v_done THEN
        RAISE NOTICE 'Da het so lan thu cho phep';
    END IF;
END;
$$;
~~~

Khối minh họa sẽ kết thúc sau lượt 2. **Không biến ví dụ này thành vòng retry mọi lỗi production**: deadlock, serialization, timeout, xung đột nghiệp vụ và dữ liệu sai yêu cầu các chính sách khác nhau. Retry có thể cần rollback toàn transaction; một function/DO giữ transaction lâu và lặp liên tục không phải cách xử lý phổ quát.

## 10. FOR với khoảng số nguyên

### 10.1. FOR i IN lower..upper

PostgreSQL:

~~~sql
DO $$
BEGIN
    FOR i IN 1..5 LOOP
        RAISE NOTICE 'i=%', i;
    END LOOP;
END;
$$;
~~~

Biến `i` được khai báo ngầm cho vòng `FOR` số nguyên, không cần khai báo `i INTEGER` ở `DECLARE` để dùng trong vòng này.

Kết quả là các giá trị 1, 2, 3, 4, 5. **Hai cận đều được tính vào**, khác với nhiều vòng lặp dùng cận trên loại trừ trong ngôn ngữ khác.

### 10.2. REVERSE và BY step

Đếm ngược:

~~~sql
DO $$
BEGIN
    FOR i IN REVERSE 5..1 LOOP
        RAISE NOTICE '%', i;
    END LOOP;
END;
$$;
~~~

Dãy 5, 4, 3, 2, 1.

Bước nhảy 2:

~~~sql
DO $$
BEGIN
    FOR i IN 1..9 BY 2 LOOP
        RAISE NOTICE '%', i;
    END LOOP;
END;
$$;
~~~

Dãy 1, 3, 5, 7, 9.

Cần chú ý cú pháp ngôn ngữ khác: MySQL stored routines không có cùng dạng PostgreSQL `FOR i IN 1..9 BY 2 LOOP`; thường dùng `WHILE` hoặc `LOOP`, còn Oracle PL/SQL có kiểu FOR số nguyên nhưng cú pháp bước nhảy khác.

### 10.3. Cận được đánh giá khi vào vòng lặp

Ví dụ:

~~~sql
DO $$
DECLARE
    v_upper INTEGER := 3;
BEGIN
    FOR i IN 1..v_upper LOOP
        RAISE NOTICE 'i=%', i;

        v_upper := 10;
    END LOOP;
END;
$$;
~~~

Trong PostgreSQL PL/pgSQL, cận của integer FOR được đánh giá khi vào vòng lặp, vì thế thay `v_upper` trong thân không khiến vòng đang chạy kéo dài tới 10. Dãy giá trị là 1, 2, 3.

Nếu cần điều kiện dừng được đánh giá lại mỗi lượt theo trạng thái thay đổi, dùng `WHILE` hoặc `LOOP + EXIT WHEN` thay vì kỳ vọng FOR tự cập nhật cận.

### 10.4. Không có lượt khi cận không phù hợp

~~~sql
DO $$
BEGIN
    FOR i IN 5..1 LOOP
        RAISE NOTICE '%', i;
    END LOOP;
END;
$$;
~~~

Với vòng tăng mặc định, cận dưới 5 lớn hơn cận trên 1, nên vòng không chạy. Muốn đi ngược, phải dùng `REVERSE 5..1`.

### 10.5. FOR thích hợp khi biết trước số lượt

Dùng integer FOR cho:

- Lặp một số lượng lượt đã được giới hạn;
- Tạo dữ liệu thử hoặc kiểm tra một thuật toán nhỏ;
- Duyệt các chỉ số từ 1 đến N trong khối thủ tục;
- Tình huống **không thể dễ dàng diễn đạt bằng SQL theo tập**.

Không dùng FOR để tạo hàng triệu câu UPDATE đơn lẻ khi một câu set-based có thể làm cùng công việc.

## 11. FOR ... IN SELECT: duyệt kết quả truy vấn

### 11.1. Duyệt từng hàng với biến RECORD

~~~sql
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT
            order_id,
            total_amount,
            order_status
        FROM sales_orders
        WHERE order_status = 'NEW'
        ORDER BY order_id
    LOOP
        RAISE NOTICE
            'Order %, amount %, status %',
            r.order_id,
            r.total_amount,
            r.order_status;
    END LOOP;
END;
$$;
~~~

Dữ liệu mẫu có năm đơn NEW: `101, 102, 103, 106, 108`. Với `ORDER BY order_id`, các thông báo đi theo thứ tự ID tăng dần như kết quả SELECT.

`r` là biến kiểu `RECORD`, mỗi lượt nhận các cột của một hàng. Có thể tham chiếu `r.order_id` và `r.total_amount`.

### 11.2. FOR query không tồn tại qua nhiều statement

Phạm vi vòng lặp là **khối thủ tục** và truy vấn nguồn được thực hiện trong khi khối chạy. Sau khi khối `DO` kết thúc, biến `r` không còn tồn tại để một câu SELECT SQL độc lập tham chiếu.

Trong PL/pgSQL, ngữ nghĩa của FOR query là duyệt các hàng của kết quả truy vấn theo cơ chế thực thi. Đừng suy rằng nó “chạy SELECT mới sau mỗi lượt” để tự nhìn thấy mọi thay đổi vừa thực hiện hoặc thay đổi từ session khác.

### 11.3. Duyệt hàng để thực hiện xử lý riêng

~~~sql
BEGIN;

DO $$
DECLARE
    r RECORD;
    v_affected INTEGER;
BEGIN
    FOR r IN
        SELECT
            order_id,
            total_amount
        FROM sales_orders
        WHERE order_status = 'NEW'
        ORDER BY order_id
    LOOP
        IF r.total_amount >= 500 THEN
            UPDATE sales_orders
            SET
                order_status = 'REVIEW',
                attempts = attempts + 1
            WHERE order_id = r.order_id
              AND order_status = 'NEW';
        ELSE
            UPDATE sales_orders
            SET
                order_status = 'PROCESSING',
                attempts = attempts + 1
            WHERE order_id = r.order_id
              AND order_status = 'NEW';
        END IF;

        GET DIAGNOSTICS v_affected = ROW_COUNT;

        RAISE NOTICE
            'Order %, affected rows %',
            r.order_id,
            v_affected;
    END LOOP;
END;
$$;

SELECT order_id, total_amount, order_status, attempts
FROM sales_orders
ORDER BY order_id;

ROLLBACK;
~~~

Trong một môi trường không có ghi đồng thời và dựa trên dữ liệu ban đầu:

| order_id | amount | status sau xử lý | attempts sau |
| ---: | ---: | --- | ---: |
| 101 | 120 | PROCESSING | 1 |
| 102 | 800 | REVIEW | 1 |
| 103 | 0 | PROCESSING | 1 |
| 106 | 600 | REVIEW | 2 |
| 108 | 50 | PROCESSING | 1 |

Các đơn không ở NEW giữ nguyên.

**Lưu ý:** trong hệ thống có nhiều worker cùng xử lý, việc SELECT tập hàng rồi UPDATE từng dòng có thể tạo cạnh tranh. Điều kiện `AND order_status = 'NEW'` giảm nguy cơ ghi lại một hàng đã chuyển trạng thái, nhưng vẫn phải xét isolation, locking, idempotency và đúng số hàng được sửa. Mục 19 có mẫu thích hợp hơn cho batch.

### 11.4. Không có hàng: vòng FOR không chạy

Nếu `SELECT` trong `FOR r IN SELECT ... LOOP` trả 0 hàng, thân vòng lặp không thực hiện lượt nào. Điều đó không tự là lỗi.

Nếu nghiệp vụ yêu cầu ít nhất một hàng, cần kiểm tra/chọn logic khác. Không giả định `r.order_id` đã được gán hợp lệ khi vòng chưa từng chạy.

## 12. FOREACH duyệt mảng trong PL/pgSQL

PostgreSQL hỗ trợ `FOREACH` để duyệt các phần tử của array.

~~~sql
DO $$
DECLARE
    v_status TEXT;
    v_statuses TEXT[] :=
        ARRAY['NEW', 'REVIEW', 'PAID'];
BEGIN
    FOREACH v_status IN ARRAY v_statuses LOOP
        RAISE NOTICE 'Status: %', v_status;
    END LOOP;
END;
$$;
~~~

Kết quả thông báo lần lượt: NEW, REVIEW, PAID.

`FOREACH` hữu ích khi:

- Tham số procedure/function là mảng;
- Cần kiểm tra từng phần tử hoặc thực thi logic thủ tục theo phần tử;
- Làm việc với một tập tham số nhỏ trong cùng khối.

Ví dụ bỏ qua trạng thái `REVIEW`:

~~~sql
DO $$
DECLARE
    v_status TEXT;
BEGIN
    FOREACH v_status IN ARRAY
        ARRAY['NEW', 'REVIEW', 'PAID']
    LOOP
        CONTINUE WHEN v_status = 'REVIEW';
        RAISE NOTICE 'Xu ly: %', v_status;
    END LOOP;
END;
$$;
~~~

Chỉ thông báo NEW và PAID.

Không suy rằng mọi DBMS có `FOREACH ... IN ARRAY` theo cú pháp PL/pgSQL. Ở SQL Server/MySQL, dữ liệu mảng có thể được lưu/biểu diễn khác; đôi khi thao tác theo tập hoặc bảng tham số là phù hợp hơn.

## 13. EXIT, CONTINUE và RETURN: ba cách dừng khác nhau

### 13.1. EXIT rời vòng lặp

~~~sql
DO $$
DECLARE
    v_i INTEGER := 0;
BEGIN
    LOOP
        v_i := v_i + 1;

        EXIT WHEN v_i > 3;
        RAISE NOTICE 'i=%', v_i;
    END LOOP;

    RAISE NOTICE 'Da roi vong lap';
END;
$$;
~~~

Vòng lặp phát 1, 2, 3; sau đó chương trình tiếp tục ở câu `RAISE NOTICE 'Da roi vong lap'`.

`EXIT` **không tự kết thúc toàn bộ function**. Nó chỉ rời vòng lặp hoặc khối được chỉ định theo ngữ nghĩa nhãn.

### 13.2. CONTINUE bỏ qua phần còn lại của một lượt

~~~sql
DO $$
BEGIN
    FOR i IN 1..6 LOOP
        CONTINUE WHEN i % 2 = 0;
        RAISE NOTICE 'So le %', i;
    END LOOP;
END;
$$;
~~~

Dãy thông báo: 1, 3, 5. Các lượt i chẵn vẫn đã được xét, nhưng `CONTINUE` bỏ phần còn lại trong thân và chuyển sang lượt kế tiếp.

### 13.3. RETURN kết thúc function

~~~sql
CREATE OR REPLACE FUNCTION first_positive(
    p_numbers INTEGER[]
)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_number INTEGER;
BEGIN
    IF p_numbers IS NULL THEN
        RETURN NULL;
    END IF;

    FOREACH v_number IN ARRAY p_numbers LOOP
        IF v_number > 0 THEN
            RETURN v_number;
        END IF;
    END LOOP;

    RETURN NULL;
END;
$$;
~~~

Thử:

~~~sql
SELECT
    first_positive(ARRAY[-3, 0, 7, 9]) AS first_value,
    first_positive(ARRAY[-3, 0]) AS not_found;
~~~

Kết quả `first_value=7` và `not_found=NULL`.

`RETURN v_number` thoát **toàn bộ function** ngay khi tìm thấy số dương đầu tiên; không chạy tiếp vòng FOREACH. Ngược lại, `EXIT` rời vòng FOREACH rồi chạy câu lệnh tiếp sau vòng.

### 13.4. Bảng so sánh

| Câu lệnh | Tác động | Tiếp tục ở đâu? |
| --- | --- | --- |
| `EXIT;` | Thoát vòng lặp gần nhất | Sau `END LOOP` của vòng đó |
| `EXIT WHEN condition;` | Chỉ thoát khi điều kiện TRUE | Sau vòng nếu điều kiện thỏa |
| `CONTINUE;` | Bỏ phần còn lại của lượt hiện tại | Lượt kế tiếp của vòng gần nhất |
| `CONTINUE WHEN condition;` | Chỉ bỏ lượt khi điều kiện TRUE | Lượt kế tiếp nếu điều kiện thỏa |
| `EXIT loop_label;` | Thoát vòng có nhãn | Sau vòng có nhãn |
| `CONTINUE loop_label;` | Bỏ qua đến lượt sau của vòng có nhãn | Vòng được chỉ định |
| `RETURN value;` | Kết thúc scalar function, trả giá trị | Trả kết quả về nơi gọi |
| `RETURN;` | Kết thúc procedure hoặc function dạng thích hợp | Trở về nơi gọi |
| `RAISE EXCEPTION;` | Phát sinh lỗi, có thể bị bắt ở exception handler thích hợp | Hủy hoặc chuyển điều khiển theo xử lý lỗi |

### 13.5. Nhãn vòng lặp lồng nhau

Nếu có nhiều vòng lặp lồng nhau, `EXIT` không nhãn chỉ thoát vòng trong cùng. Muốn thoát vòng ngoài, đặt nhãn:

~~~sql
DO $$
BEGIN
    <<outer_loop>>
    FOR i IN 1..3 LOOP
        FOR j IN 1..3 LOOP
            RAISE NOTICE 'i=%, j=%', i, j;

            EXIT outer_loop WHEN i * j >= 4;
        END LOOP;
    END LOOP outer_loop;

    RAISE NOTICE 'Da thoat outer_loop';
END;
$$;
~~~

Diễn biến:

~~~text
i=1, j=1
i=1, j=2
i=1, j=3
i=2, j=1
i=2, j=2  ← điều kiện 2*2>=4, thoát outer_loop
Da thoat outer_loop
~~~

Nhãn giúp người đọc hiểu phạm vi thoát. Không nên dùng nhãn lồng nhiều tầng nếu có thể tách đoạn xử lý thành function dễ đọc.

### 13.6. CONTINUE với vòng ngoài

Ví dụ:

~~~sql
DO $$
BEGIN
    <<outer_loop>>
    FOR i IN 1..3 LOOP
        FOR j IN 1..3 LOOP
            CONTINUE outer_loop WHEN j = 2;
            RAISE NOTICE 'i=%, j=%', i, j;
        END LOOP;
    END LOOP outer_loop;
END;
$$;
~~~

Mỗi khi vòng trong đạt `j=2`, chương trình bỏ phần còn lại của lượt **vòng ngoài i** và chuyển sang `i` kế tiếp. Nó **không** chỉ bỏ lượt `j=2` của vòng trong.

Nhãn cần được đặt đúng đích. Đây là một lý do phải đọc rõ ý nghĩa `CONTINUE label` trước khi dùng trong thuật toán lồng nhau.

## 14. Chọn cấu trúc vòng lặp theo điều kiện kết thúc

| Nhu cầu | Cấu trúc gợi ý | Vì sao |
| --- | --- | --- |
| Biết trước lặp 5 lần | `FOR i IN 1..5 LOOP` | Cận rõ, ít lỗi quên tăng biến |
| Lặp khi biến còn nhỏ hơn ngưỡng | `WHILE condition LOOP` | Điều kiện nằm ngay đầu vòng |
| Luôn cần thực hiện ít nhất một bước trước khi xét dừng | `LOOP ... EXIT WHEN ...` | Điều kiện được đặt sau bước cần thực hiện |
| Duyệt kết quả SELECT | `FOR r IN SELECT ... LOOP` | Không phải tự quản lý cursor cho ví dụ đơn giản |
| Duyệt từng giá trị trong mảng | `FOREACH ... IN ARRAY` | Truy cập trực tiếp array PL/pgSQL |
| Bỏ qua bản ghi không phù hợp | `CONTINUE WHEN ...` | Diễn đạt skip một lượt |
| Đã tìm thấy kết quả thì kết thúc hàm | `RETURN` | Không cần chạy phần còn lại |
| Cần dừng toàn bộ các vòng lặp lồng nhau | `EXIT outer_label` hoặc `RETURN` | Rõ phạm vi thoát |

**Câu hỏi quan trọng không chỉ là “vòng nào chạy được”, mà là “vòng đó chắc chắn dừng bằng cơ chế nào?”**

### 14.1. Lập luận dừng bằng biến tiến độ

Ví dụ xử lý tối đa `p_max_attempts` lượt:

~~~text
Bất biến: 0 <= v_attempt <= p_max_attempts
Khởi tạo: v_attempt = 0
Bước tiến: v_attempt tăng đúng 1 mỗi lượt
Điều kiện: tiếp tục khi v_attempt < p_max_attempts
Kết thúc: sau nhiều nhất p_max_attempts lượt
~~~

Nếu `v_attempt` không tăng, hoặc biến ngưỡng có thể tăng theo cùng tốc độ mà không có giới hạn, lập luận dừng không còn đúng.

### 14.2. Đừng dùng điều kiện chỉ phụ thuộc trạng thái không đổi

Sai:

~~~sql
-- Không chạy trên môi trường thật: nếu status không đổi, vòng vô hạn.
WHILE v_status = 'NEW' LOOP
    RAISE NOTICE 'Dang cho xu ly';
END LOOP;
~~~

Không có câu lệnh nào làm `v_status` thay đổi, nên điều kiện sẽ không tự trở thành FALSE. Nếu trạng thái được cập nhật từ một nguồn khác, cần giải thích cách refresh biến, transaction snapshot, timeout và giới hạn lượt.

### 14.3. Dừng thành công và dừng do giới hạn là hai kết quả khác nhau

Một hàm tìm dữ liệu có thể dừng vì:

- Tìm được kết quả;
- Duyệt hết tập nguồn nhưng không thấy;
- Vượt số lượt tối đa;
- Người dùng hủy;
- Có lỗi bất ngờ.

Không nên gom tất cả thành “xử lý thành công”. Nếu function trả trạng thái, có thể phân biệt `FOUND`, `NOT_FOUND`, `LIMIT_REACHED` hoặc ném exception tùy hợp đồng.

## 15. SELECT INTO, FOUND và GET DIAGNOSTICS để quyết định nhánh

### 15.1. SELECT INTO gán kết quả vào biến trong PL/pgSQL

Ví dụ viết function đọc trạng thái của một đơn:

~~~sql
CREATE OR REPLACE FUNCTION describe_order(
    p_order_id INTEGER
)
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    v_status TEXT;
BEGIN
    SELECT o.order_status
    INTO v_status
    FROM sales_orders AS o
    WHERE o.order_id = p_order_id;

    IF NOT FOUND THEN
        RETURN 'NOT_FOUND';
    END IF;

    CASE v_status
        WHEN 'NEW' THEN
            RETURN 'Cho phan loai';
        WHEN 'PROCESSING' THEN
            RETURN 'Dang xu ly';
        WHEN 'REVIEW' THEN
            RETURN 'Can kiem tra';
        WHEN 'PAID' THEN
            RETURN 'Da thanh toan';
        WHEN 'CANCELLED' THEN
            RETURN 'Da huy';
        ELSE
            RAISE EXCEPTION
                'Trang thai khong hop le: %', v_status;
    END CASE;
END;
$$;
~~~

Gọi:

~~~sql
SELECT
    describe_order(101) AS new_order,
    describe_order(104) AS paid_order,
    describe_order(999) AS missing_order;
~~~

Kết quả:

| new_order | paid_order | missing_order |
| --- | --- | --- |
| Cho phan loai | Da thanh toan | NOT_FOUND |

**Phân biệt cú pháp:** `SELECT ... INTO variable` **bên trong PL/pgSQL** là phép gán kết quả truy vấn vào biến. Nó khác với cú pháp `SELECT ... INTO new_table` tạo bảng của một số ngữ cảnh/dialect SQL; đừng lẫn lộn.

### 15.2. FOUND là biến boolean đặc biệt

Trong PL/pgSQL, `FOUND` phản ánh một số thao tác truy vấn đã được thực hiện gần nhất theo quy tắc ngôn ngữ, ví dụ `SELECT INTO`, `PERFORM` hoặc `UPDATE`.

~~~sql
DO $$
DECLARE
    v_amount NUMERIC;
BEGIN
    SELECT o.total_amount
    INTO v_amount
    FROM sales_orders AS o
    WHERE o.order_id = 999;

    IF FOUND THEN
        RAISE NOTICE 'Found amount %', v_amount;
    ELSE
        RAISE NOTICE 'Order not found';
    END IF;
END;
$$;
~~~

Vì không có `order_id=999`, nhánh ELSE chạy.

**Đọc `FOUND` ngay sau thao tác mà bạn cần kiểm tra.** Những lệnh SQL PL/pgSQL khác có thể cập nhật nó; đừng chèn nhiều thao tác trung gian rồi giả định `FOUND` vẫn nói về SELECT đầu tiên.

### 15.3. SELECT INTO STRICT khi mong đúng một hàng

~~~sql
DO $$
DECLARE
    v_status TEXT;
BEGIN
    SELECT o.order_status
    INTO STRICT v_status
    FROM sales_orders AS o
    WHERE o.order_id = 101;

    RAISE NOTICE 'Status=%', v_status;
END;
$$;
~~~

`INTO STRICT` yêu cầu truy vấn trả **đúng một hàng**:

- 0 hàng → exception `NO_DATA_FOUND`.
- Nhiều hơn 1 hàng → exception `TOO_MANY_ROWS`.
- Đúng một hàng → gán biến.

Với truy vấn theo `PRIMARY KEY`, trường hợp nhiều hàng không xảy ra trên schema hợp lệ; nhưng ví dụ giúp hiểu khi dùng truy vấn không có ràng buộc duy nhất.

Nếu không dùng STRICT, `SELECT INTO` có thể lấy hàng đầu khi có nhiều kết quả theo quy tắc PL/pgSQL; **đừng dựa vào hàng đầu “tự nhiên”** nếu không có `ORDER BY` và tiêu chí rõ.

### 15.4. GET DIAGNOSTICS ROW_COUNT sau UPDATE

~~~sql
DO $$
DECLARE
    v_affected BIGINT;
BEGIN
    UPDATE sales_orders
    SET order_status = 'PROCESSING'
    WHERE order_id = 101
      AND order_status = 'NEW';

    GET DIAGNOSTICS v_affected = ROW_COUNT;

    IF v_affected = 1 THEN
        RAISE NOTICE 'Da cap nhat 1 don';
    ELSIF v_affected = 0 THEN
        RAISE NOTICE 'Don khong con NEW hoac khong ton tai';
    ELSE
        RAISE EXCEPTION 'Row count bat thuong: %', v_affected;
    END IF;
END;
$$;
~~~

Dạng này kiểm tra **hàng được cập nhật**. Với `order_id` là khóa chính, số hàng hợp lệ được chọn thường tối đa 1.

`GET DIAGNOSTICS ... = ROW_COUNT` là cú pháp PL/pgSQL, không phải một phép SELECT bảng. Đặt nó **ngay sau DML cần đo**, trước những thao tác SQL khác có thể thay đổi thông tin chẩn đoán.

### 15.5. Không làm CHECK-THEN-ACT dễ có race

Một mẫu thiếu an toàn khi có nhiều session:

~~~sql
-- Ý tưởng dễ race:
SELECT order_status INTO v_status
FROM sales_orders
WHERE order_id = p_order_id;

IF v_status = 'NEW' THEN
    UPDATE sales_orders
    SET order_status = 'PAID'
    WHERE order_id = p_order_id;
END IF;
~~~

Session khác có thể đổi trạng thái giữa SELECT và UPDATE. Khi đó câu UPDATE **không còn kiểm tra trạng thái nguồn** và có nguy cơ ghi đè không mong muốn.

Một cách tốt hơn là gộp điều kiện vào DML:

~~~sql
UPDATE sales_orders
SET
    order_status = 'PAID',
    processed_at = CURRENT_TIMESTAMP
WHERE order_id = p_order_id
  AND order_status = 'NEW';
~~~

Rồi kiểm tra `ROW_COUNT`/`FOUND`. Đây là thiết kế **cập nhật có điều kiện tại thời điểm ghi**, không dựa chỉ vào trạng thái đã đọc trước đó.

## 16. PROCEDURE có IF và kiểm tra kết quả UPDATE

Tạo một procedure chỉ chuyển đơn `NEW` thành `PAID` nếu trạng thái còn đúng. Đây là ví dụ kỹ thuật về chuyển trạng thái, không thay cho tích hợp thanh toán thực tế.

~~~sql
CREATE OR REPLACE PROCEDURE mark_order_paid(
    p_order_id INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_affected BIGINT;
BEGIN
    IF p_order_id IS NULL THEN
        RAISE EXCEPTION 'order_id khong duoc NULL';
    END IF;

    UPDATE sales_orders
    SET
        order_status = 'PAID',
        processed_at = CURRENT_TIMESTAMP
    WHERE order_id = p_order_id
      AND order_status = 'NEW';

    GET DIAGNOSTICS v_affected = ROW_COUNT;

    IF v_affected = 0 THEN
        RAISE EXCEPTION
            'Khong the chuyen order %: khong ton tai hoac khong con NEW',
            p_order_id;
    END IF;

    RAISE NOTICE 'Da chuyen order % sang PAID', p_order_id;
END;
$$;
~~~

Thử an toàn:

~~~sql
BEGIN;

CALL mark_order_paid(101);

SELECT order_id, order_status, processed_at
FROM sales_orders
WHERE order_id = 101;

ROLLBACK;
~~~

Với dữ liệu ban đầu, procedure đổi đơn 101 từ NEW sang PAID. Nhờ `WHERE order_status = 'NEW'`, việc gọi lần thứ hai khi đơn đã PAID sẽ **không cập nhật**, rồi phát exception theo chính sách.

Khi phát exception trong transaction đang mở, phải rollback transaction bị lỗi trước khi thực hành tiếp. Các ứng dụng có thể chọn trả trạng thái kết quả thay vì exception; điều quan trọng là **không báo thành công khi không có hàng chuyển trạng thái**.

### 16.1. Vì sao không dùng IF thay cho điều kiện UPDATE?

`IF` bên ngoài giúp kiểm tra tham số, quyết định luồng và xử lý kết quả. Nhưng điều kiện “đơn còn NEW” cần đặt trong **WHERE của UPDATE** để bảo vệ tính đúng đắn khi có ghi đồng thời.

Một procedure tốt thường kết hợp:

- `IF`: kiểm tra giá trị đầu vào và điều kiện điều khiển;
- SQL DML có guard: áp dụng thay đổi nguyên tử;
- `GET DIAGNOSTICS`: xem kết quả;
- `IF`: quyết định báo thành công hay lỗi.

Không chuyển một transaction race-sensitive thành hai câu `SELECT` và `UPDATE` chỉ vì có thể viết `IF`.

### 16.2. PROCEDURE khác FUNCTION về mục đích và cách gọi

Thử function:

~~~sql
SELECT classify_amount(120.00);
~~~

Gọi procedure:

~~~sql
CALL mark_order_paid(101);
~~~

Trong PostgreSQL, procedure không khai báo giá trị trả qua `RETURNS TEXT` như scalar function. Nó có thể có tham số `IN`/`OUT`/`INOUT` theo khả năng và phiên bản, nhưng cách dùng khác với function trong SELECT. Không chép nguyên `CALL` của PostgreSQL sang MySQL/SQL Server/Oracle mà không xét dialect.

## 17. RETURN NEXT và RETURN QUERY trong function trả tập hàng

### 17.1. RETURN QUERY: bổ sung nhiều hàng từ một SELECT

Một function có thể trả danh sách đơn cần review:

~~~sql
CREATE OR REPLACE FUNCTION list_review_orders(
    p_min_amount NUMERIC
)
RETURNS TABLE (
    out_order_id INTEGER,
    out_amount NUMERIC
)
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_min_amount IS NULL OR p_min_amount < 0 THEN
        RAISE EXCEPTION 'Nguong tien khong hop le';
    END IF;

    RETURN QUERY
        SELECT
            o.order_id,
            o.total_amount
        FROM sales_orders AS o
        WHERE o.total_amount >= p_min_amount
          AND o.order_status IN ('NEW', 'REVIEW')
        ORDER BY o.order_id;

    RETURN;
END;
$$;
~~~

Gọi:

~~~sql
SELECT *
FROM list_review_orders(500);
~~~

Với bảng mẫu, kết quả gồm các đơn 102 và 106 có giá trị 800 và 600.

`RETURN QUERY` thêm những hàng từ câu SELECT vào kết quả của function trả tập. **Nó không nhất thiết kết thúc function ngay lập tức**; có thể có câu lệnh tiếp theo trước `RETURN;`.

### 17.2. RETURN NEXT: trả lần lượt từng hàng

Ví dụ PL/pgSQL:

~~~sql
CREATE OR REPLACE FUNCTION first_n_numbers(
    p_n INTEGER
)
RETURNS SETOF INTEGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_n IS NULL OR p_n < 0 OR p_n > 1000 THEN
        RAISE EXCEPTION 'p_n phai nam trong [0,1000]';
    END IF;

    FOR i IN 1..p_n LOOP
        RETURN NEXT i;
    END LOOP;

    RETURN;
END;
$$;
~~~

Gọi:

~~~sql
SELECT *
FROM first_n_numbers(4);
~~~

Kết quả là 1, 2, 3, 4.

Sự khác biệt:

- `RETURN NEXT i` **bổ sung một hàng** vào kết quả; vòng lặp vẫn tiếp tục.
- `RETURN QUERY SELECT ...` bổ sung **một tập hàng** từ SELECT.
- `RETURN;` kết thúc function.
- `RETURN value;` của scalar function kết thúc và trả **một giá trị**.

### 17.3. Nên ưu tiên SQL theo tập khi chỉ cần dãy số

Đối với PostgreSQL, nếu mục đích chỉ tạo các số 1..N, có thể viết:

~~~sql
SELECT n
FROM generate_series(1, 4) AS g(n);
~~~

Không cần tạo function với vòng FOR. Ví dụ `RETURN NEXT` giúp hiểu điều khiển luồng, **không có nghĩa nó là phương pháp hiệu quả nhất** cho dãy số hay mọi truy vấn trả tập.

Với function trả nhiều hàng rất lớn, PL/pgSQL có thể lưu/đệm dữ liệu kết quả theo cơ chế engine, gây chi phí bộ nhớ/đĩa. Không coi `RETURN NEXT` là streaming vô hạn không tốn bộ nhớ.

## 18. Xử lý ngoại lệ trong khối PL/pgSQL

### 18.1. RAISE NOTICE khác RAISE EXCEPTION

~~~sql
RAISE NOTICE 'Don hang % can xem lai', p_order_id;
~~~

`NOTICE` đưa thông tin chẩn đoán cho client/log theo cấu hình, thường **không tự hủy transaction**.

~~~sql
RAISE EXCEPTION 'Don hang % khong hop le', p_order_id;
~~~

`EXCEPTION` phát sinh lỗi. Nếu không được bắt trong một khối xử lý thích hợp, statement/transaction có thể thất bại theo cơ chế PostgreSQL.

Không lạm dụng `NOTICE` để thay hệ thống audit chính thức: thông báo có thể không được lưu, bị lọc bởi cấu hình hoặc không liên kết đủ dữ liệu nghiệp vụ.

### 18.2. EXCEPTION WHEN xử lý một loại lỗi được dự đoán

Ví dụ minh họa một khối xử lý lỗi:

~~~sql
DO $$
DECLARE
    v_status TEXT;
BEGIN
    BEGIN
        SELECT o.order_status
        INTO STRICT v_status
        FROM sales_orders AS o
        WHERE o.order_id = 999;

        RAISE NOTICE 'Status %', v_status;

    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            RAISE NOTICE 'Order 999 khong ton tai';
    END;
END;
$$;
~~~

`SELECT INTO STRICT` ném `NO_DATA_FOUND` khi không có hàng. Nhánh `EXCEPTION WHEN NO_DATA_FOUND` xử lý loại lỗi cụ thể.

Trong PL/pgSQL, khối có `EXCEPTION` mang đặc tính subtransaction nội bộ; khi lỗi xảy ra, thay đổi dữ liệu persistent được thực hiện **trong phần khối bị lỗi** có thể được rollback, còn trạng thái biến cục bộ có quy tắc riêng. Không nghĩ rằng bắt exception đơn giản là “bỏ qua lỗi mà giữ mọi thay đổi DML trước đó trong khối”.

### 18.3. Không dùng WHEN OTHERS THEN NULL để nuốt mọi lỗi

Một anti-pattern:

~~~sql
-- KHÔNG KHUYẾN NGHỊ:
EXCEPTION
    WHEN OTHERS THEN
        NULL;
~~~

Cách này có thể che:

- Vi phạm `NOT NULL`, `CHECK`, `FOREIGN KEY`;
- Lỗi cú pháp SQL động;
- Lỗi quyền truy cập;
- Lỗi do dữ liệu đầu vào sai;
- Tình huống concurrency cần retry;
- Lỗi lập trình không lường trước.

Nếu thật sự cần xử lý lỗi từng hàng, hãy xác định loại lỗi được phép, lưu ngữ cảnh, trạng thái thực thi và chính sách rollback/savepoint. Không biến mọi exception thành “đã xử lý xong”.

### 18.4. Error handling và vòng lặp phải có giới hạn

Một mẫu nguy hiểm:

~~~text
LOOP
    TRY xử lý
    CATCH mọi lỗi
        CONTINUE
END LOOP
~~~

Nếu lỗi là dữ liệu thiếu hoặc câu SQL sai, vòng có thể lặp mãi. Khi cần retry:

- Chỉ retry lỗi thuộc nhóm có khả năng hồi phục;
- Có `max_attempts` rõ ràng;
- Có backoff và ranh giới transaction thích hợp;
- Có idempotency key để không lặp tác động đã commit;
- Báo hoặc ghi trạng thái thất bại khi hết lượt.

Cơ chế quản lý retry của worker/service ở lớp ứng dụng thường phù hợp hơn việc giữ một transaction SQL mở và lặp vô hạn.

## 19. Vòng lặp xử lý nhiều hàng và cạnh tranh đồng thời

### 19.1. Vòng FOR có thể đúng về logic nhưng không tốt về hiệu năng

Giả sử một triệu đơn `NEW` phải được phân nhóm theo số tiền. Dùng:

~~~sql
FOR r IN
    SELECT order_id, total_amount
    FROM sales_orders
    WHERE order_status = 'NEW'
LOOP
    -- UPDATE một hàng theo r.order_id.
END LOOP;
~~~

có thể tạo rất nhiều thao tác DML đơn lẻ, tăng chi phí xử lý câu lệnh, khóa, logging và xử lý lỗi. Nó cũng phức tạp khi cần commit theo lô hoặc retry.

Khi mọi hàng có thể được cập nhật bằng cùng quy tắc, hãy ưu tiên **một câu UPDATE set-based**:

~~~sql
BEGIN;

UPDATE sales_orders
SET
    order_status = CASE
        WHEN total_amount >= 500 THEN 'REVIEW'
        ELSE 'PROCESSING'
    END,
    attempts = attempts + 1
WHERE order_status = 'NEW'
RETURNING order_id, order_status, attempts;

ROLLBACK;
~~~

Câu lệnh ngắn hơn, mục đích rõ và tránh vòng lặp do người viết quản lý. PostgreSQL quyết định kế hoạch thực thi tập hàng.

### 19.2. Khi cần chia lô để nhiều worker cùng nhận việc

PostgreSQL có cơ chế `FOR UPDATE SKIP LOCKED` để phối hợp truy cập các hàng phù hợp cho dạng queue processing. Ví dụ thử nghiệm nhận tối đa hai đơn NEW:

~~~sql
BEGIN;

WITH picked AS (
    SELECT o.order_id
    FROM sales_orders AS o
    WHERE o.order_status = 'NEW'
    ORDER BY o.order_id
    FOR UPDATE SKIP LOCKED
    LIMIT 2
)
UPDATE sales_orders AS o
SET
    order_status = CASE
        WHEN o.total_amount >= 500 THEN 'REVIEW'
        ELSE 'PROCESSING'
    END,
    attempts = o.attempts + 1
FROM picked AS p
WHERE o.order_id = p.order_id
RETURNING o.order_id, o.order_status, o.attempts;

ROLLBACK;
~~~

Với không có cạnh tranh và dữ liệu ban đầu, hai đơn ID 101 và 102 có thể được nhận, với trạng thái PROCESSING và REVIEW tương ứng.

Ý tưởng `SKIP LOCKED`: một worker không chờ các hàng đang bị worker khác khóa, mà có thể chọn những hàng khác. Đây là công cụ hữu ích cho queue-like access, **không phải** cơ chế tạo snapshot đầy đủ hoặc bảo đảm công bằng/thứ tự tuyệt đối. Cần transaction ngắn, phục hồi job bị treo và xử lý idempotency.

**Đừng tự thay `FOR UPDATE SKIP LOCKED` của PostgreSQL bằng chuỗi giống hệt ở MySQL, SQL Server, Oracle hoặc SQLite.** Những engine có hỗ trợ ý tưởng tương tự nhưng cú pháp/semantics khác nhau.

### 19.3. Khi vòng lặp thực sự cần thiết

PL/pgSQL loops có giá trị khi:

- Bước sau phụ thuộc kết quả của bước trước theo thuật toán thủ tục;
- Cần gọi function/thủ tục riêng cho từng đối tượng;
- Cần điều kiện dừng phụ thuộc phản hồi sau mỗi bước;
- Cần duyệt cursor/stream logic theo quy tắc DBMS;
- Thuật toán không có biểu diễn set-based đơn giản, rõ và đúng.

Vẫn cần cân nhắc liệu logic nên nằm ở database hay tầng ứng dụng. Với nhiều thao tác mạng, gọi API bên ngoài hoặc chờ I/O, database procedure thường **không phải nơi tốt để giữ giao dịch mở**.

## 20. Vòng lặp đệ quy và CTE đệ quy: thay thế khi phù hợp

Một câu hỏi hay gặp: có thể dùng SQL thuần để tạo dãy 1..5 mà không cần `FOR` không?

Trong PostgreSQL và nhiều hệ có `WITH RECURSIVE`:

~~~sql
WITH RECURSIVE numbers(n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1
    FROM numbers
    WHERE n < 5
)
SELECT n
FROM numbers
ORDER BY n;
~~~

Kết quả:

~~~text
1
2
3
4
5
~~~

Điều kiện `WHERE n < 5` trong nhánh đệ quy là **điều kiện dừng tạo thêm hàng**. Nếu viết sai hoặc loại bỏ điều kiện, truy vấn có thể sinh nhiều hàng quá mức hoặc không kết thúc theo cách dự kiến, tùy giới hạn/bảo vệ của DBMS.

### 20.1. CTE đệ quy khác vòng lặp thủ tục

- `WITH RECURSIVE` tạo một **quan hệ kết quả** theo truy vấn anchor và nhánh recursive.
- `FOR/WHILE/LOOP` thực thi **các câu lệnh** trong khối thủ tục, có biến trạng thái và điều khiển thoát.
- CTE đệ quy phù hợp cho cây/phân cấp, đường đi, dãy số và tính toán có dạng truy vấn đệ quy.
- Vòng thủ tục phù hợp khi cần thay đổi trạng thái theo những bước có side effects hoặc điều kiện ngôn ngữ thủ tục.

Không cố dùng vòng PL/pgSQL để duyệt cây hàng triệu nút nếu một truy vấn đệ quy theo tập có thể biểu diễn đúng bài toán và được tối ưu tốt.

### 20.2. Điều kiện kết thúc trong truy vấn đệ quy cũng cần được chứng minh

Ở ví dụ trên:

- Anchor tạo n=1.
- Nhánh recursive chỉ tạo n+1 khi n<5.
- Giá trị n tăng đúng 1, không vượt 5.
- Vì vậy kết quả có hữu hạn 5 hàng.

Với dữ liệu đồ thị có chu trình, cần giải pháp tránh lặp nút, giới hạn độ sâu và/hoặc công cụ xử lý cycle của DBMS; chỉ dùng `UNION ALL` mà không xét chu trình có thể gây mở rộng không giới hạn.

## 21. So sánh cú pháp giữa các DBMS

Các cấu trúc thủ tục **không phải toàn bộ SQL chuẩn được hỗ trợ đồng nhất**. Khi chuyển code giữa PostgreSQL, MySQL, SQL Server, Oracle và SQLite, cần phân biệt ngôn ngữ thực thi.

### 21.1. PostgreSQL PL/pgSQL

~~~sql
DO $$
DECLARE
    v_i INTEGER := 0;
BEGIN
    IF v_i = 0 THEN
        RAISE NOTICE 'Start';
    ELSIF v_i > 0 THEN
        RAISE NOTICE 'Positive';
    ELSE
        RAISE NOTICE 'Negative';
    END IF;

    WHILE v_i < 3 LOOP
        v_i := v_i + 1;
        CONTINUE WHEN v_i = 2;
        RAISE NOTICE '%', v_i;
    END LOOP;
END;
$$;
~~~

Từ khóa chính:

- `IF ... ELSIF ... END IF;`
- `CASE ... END CASE;` (statement)
- `LOOP ... END LOOP;`, `WHILE ... LOOP ... END LOOP;`
- `FOR i IN 1..5 LOOP ... END LOOP;`
- `FOR r IN SELECT ... LOOP ... END LOOP;`
- `FOREACH ... IN ARRAY ... LOOP ... END LOOP;`
- `EXIT [label] [WHEN ...];`, `CONTINUE [label] [WHEN ...];`
- `RETURN`, `RAISE EXCEPTION`, `GET DIAGNOSTICS`.

### 21.2. MySQL stored procedures

MySQL dùng **`ELSEIF`** (không phải `ELSIF` như PL/pgSQL) và vòng `WHILE ... DO ... END WHILE`:

~~~sql
-- MySQL: DELIMITER là lệnh của một số SQL client.
DELIMITER //

CREATE PROCEDURE demo_count()
BEGIN
    DECLARE v_i INT DEFAULT 0;

    WHILE v_i < 3 DO
        SET v_i = v_i + 1;
    END WHILE;

    IF v_i = 3 THEN
        SELECT 'DONE' AS result, v_i AS count_value;
    ELSEIF v_i > 3 THEN
        SELECT 'OVER' AS result, v_i AS count_value;
    ELSE
        SELECT 'EARLY' AS result, v_i AS count_value;
    END IF;
END //

DELIMITER ;

CALL demo_count();
~~~

Kết quả mong đợi: `DONE`, `3`.

Các điểm riêng của MySQL:

- `DELIMITER //` là **lệnh cấu hình delimiter của SQL client**, không phải SQL chuẩn gửi nguyên vào database server ở mọi driver.
- `DECLARE` thường phải nằm ở **đầu BEGIN...END block** theo cú pháp MySQL stored routine.
- `SET v_i = ...` dùng để gán biến.
- Có `LOOP`, `WHILE`, `REPEAT ... UNTIL ... END REPEAT`.
- Dùng nhãn với `LEAVE` để thoát vòng/khối và `ITERATE` để sang lượt kế tiếp của vòng được gắn nhãn.
- `CASE` biểu thức và `CASE` statement là hai cách dùng khác nhau; cách xử lý ELSE và kết thúc cần theo MySQL.

Ví dụ `REPEAT` kiểm tra điều kiện ở cuối:

~~~sql
-- Bên trong stored routine MySQL:
REPEAT
    SET v_i = v_i + 1;
UNTIL v_i >= 3
END REPEAT;
~~~

`REPEAT` thường thực hiện thân ít nhất một lần nếu luồng đến vị trí này, khác `WHILE` kiểm tra trước. Không dùng ví dụ này ngoài một block/routine đã khai báo `v_i`.

Ví dụ nhãn:

~~~sql
-- Bên trong stored routine MySQL:
my_loop: LOOP
    SET v_i = v_i + 1;

    IF v_i >= 3 THEN
        LEAVE my_loop;
    END IF;
END LOOP my_loop;
~~~

Không thay `LEAVE` bằng `EXIT` của PostgreSQL trong MySQL một cách máy móc.

### 21.3. SQL Server T-SQL

SQL Server có cấu trúc `IF ... ELSE`, `BEGIN...END`, `WHILE`, `BREAK`, `CONTINUE`:

~~~sql
-- SQL Server / T-SQL:
DECLARE @i INT = 0;

WHILE @i < 5
BEGIN
    SET @i = @i + 1;

    IF @i = 3
        CONTINUE;

    IF @i = 5
        BREAK;

    PRINT CONCAT('i=', @i);
END;
~~~

Kết quả thông báo: 1, 2, 4.

Điểm riêng:

- Biến T-SQL thường có tiền tố `@`.
- `BEGIN...END` nhóm câu lệnh trong IF/WHILE.
- `BREAK` thoát vòng `WHILE`; `CONTINUE` đi tới lượt tiếp theo.
- T-SQL có `CASE` như **biểu thức** trong SELECT/UPDATE, nhưng **không dùng `CASE` làm công cụ trực tiếp thi hành nhiều câu lệnh điều khiển luồng** theo kiểu PL/pgSQL CASE statement.
- Không có `FOR i IN 1..5 LOOP` theo đúng cú pháp PL/pgSQL; có thể dùng `WHILE`, set-based SQL hoặc cursor khi thật cần.
- Có `TRY...CATCH` và `THROW`/`RAISERROR` với quy tắc riêng.

Ví dụ procedure T-SQL có guard:

~~~sql
CREATE OR ALTER PROCEDURE dbo.MarkOrderPaid
    @order_id INT
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE dbo.sales_orders
    SET order_status = 'PAID'
    WHERE order_id = @order_id
      AND order_status = 'NEW';

    DECLARE @affected INT = @@ROWCOUNT;

    IF @affected = 0
    BEGIN
        THROW 50001, 'Order not found or not NEW', 1;
    END
END;
~~~

Đây là **mẫu SQL Server**, giả định bảng `dbo.sales_orders` tương ứng đã tồn tại. `@@ROWCOUNT` cần được lấy ngay sau thao tác muốn kiểm tra; không thực hiện một statement trung gian làm thay đổi giá trị trước khi đọc.

### 21.4. Oracle PL/SQL

Oracle PL/SQL có cú pháp tương đồng với PL/pgSQL về `IF ... ELSIF`, `CASE`, `LOOP`, `WHILE` và `FOR`, nhưng ngôn ngữ và thư viện khác.

~~~sql
-- Oracle PL/SQL:
DECLARE
    v_i PLS_INTEGER := 0;
BEGIN
    LOOP
        v_i := v_i + 1;
        EXIT WHEN v_i >= 3;
    END LOOP;

    IF v_i = 3 THEN
        DBMS_OUTPUT.PUT_LINE('DONE');
    ELSE
        DBMS_OUTPUT.PUT_LINE('NOT_DONE');
    END IF;
END;
/
~~~

Lưu ý:

- Dấu `/` sau khối thường là ký hiệu của các client như SQL*Plus để chạy khối PL/SQL, không phải nội dung của mọi API SQL.
- `DBMS_OUTPUT.PUT_LINE` cần client cấu hình để hiển thị output, không giống `RAISE NOTICE` của PostgreSQL.
- Có cursor FOR loops và những cấu trúc kiểm soát khác.
- Dùng `RAISE_APPLICATION_ERROR`/exception handling theo Oracle; không dùng `RAISE EXCEPTION` của PL/pgSQL nguyên văn.
- Kiểu `BOOLEAN`, phạm vi biến, transaction control và cơ chế compile khác.

### 21.5. SQLite

SQLite hỗ trợ **SQL `CASE` biểu thức**, `WITH RECURSIVE` và trigger với các điều kiện `WHEN`, nhưng **không cung cấp một ngôn ngữ stored procedure PL/pgSQL-style tổng quát** với `IF ... END IF`, `WHILE ... LOOP` trong SQL như PostgreSQL.

Ví dụ hợp lệ với SQLite:

~~~sql
SELECT
    order_id,
    CASE
        WHEN total_amount >= 500 THEN 'HIGH'
        ELSE 'NORMAL'
    END AS band
FROM sales_orders;
~~~

Nếu cần một vòng lặp nhiều bước khi dùng SQLite, thường thực hiện ở **ngôn ngữ ứng dụng** (Java, Python...) hoặc chuyển bài toán thành `WITH RECURSIVE`/SQL theo tập khi phù hợp. Không tự viết `DO $$ BEGIN ... END $$` rồi kỳ vọng SQLite hiểu.

### 21.6. Bảng đối chiếu

| Khái niệm | PostgreSQL PL/pgSQL | MySQL stored routines | SQL Server T-SQL | Oracle PL/SQL | SQLite |
| --- | --- | --- | --- | --- | --- |
| Nhánh điều kiện | `IF...ELSIF...END IF` | `IF...ELSEIF...END IF` | `IF...ELSE` + `BEGIN...END` | `IF...ELSIF...END IF` | Thực hiện ở app hoặc trigger hạn chế |
| Biểu thức chọn giá trị | SQL `CASE...END` | SQL `CASE...END` | SQL `CASE...END` | SQL `CASE...END` | SQL `CASE...END` |
| Câu lệnh CASE thủ tục | `CASE...END CASE` | `CASE...END CASE` | Không tương đương theo kiểu PL/pgSQL | `CASE...END CASE` | Không có stored CASE statement tổng quát |
| Vòng không điều kiện | `LOOP` | `LOOP` | Thường dùng `WHILE` | `LOOP` | App/recursive CTE |
| Lặp khi điều kiện đúng | `WHILE...LOOP` | `WHILE...DO` | `WHILE...BEGIN` | `WHILE...LOOP` | App/recursive CTE |
| Lặp khoảng số | `FOR i IN 1..n` | Thường `WHILE` | Thường `WHILE` | `FOR i IN 1..n` | App/recursive CTE |
| Thoát vòng | `EXIT [WHEN]` | `LEAVE` | `BREAK` | `EXIT [WHEN]` | Cú pháp app |
| Bỏ lượt | `CONTINUE [WHEN]` | `ITERATE` | `CONTINUE` | `CONTINUE [WHEN]` | Cú pháp app |
| Trả giá trị function | `RETURN` | `RETURN` trong function | `RETURN` có quy tắc riêng; scalar UDF khác | `RETURN` | Theo app/extension |
| Xử lý exception | `EXCEPTION WHEN` | Handlers | `TRY...CATCH` | `EXCEPTION WHEN` | Theo mã lỗi của driver/app |

Bảng chỉ định hướng. Cần kiểm tra đúng **phiên bản, loại routine và ngữ cảnh thực thi**. Cú pháp gần giống nhau không bảo đảm ngữ nghĩa transaction hoặc xử lý lỗi giống nhau.

## 22. Chọn IF, CASE hay SQL theo tập?

### 22.1. IF phù hợp với điều khiển nhiều câu lệnh

Ví dụ:

~~~sql
IF p_order_id IS NULL THEN
    RAISE EXCEPTION 'Thieu order_id';
END IF;

UPDATE sales_orders
SET order_status = 'PROCESSING'
WHERE order_id = p_order_id
  AND order_status = 'NEW';
~~~

`IF` kiểm tra tham số rồi cho phép bước DML tiếp tục.

### 22.2. CASE expression phù hợp khi chọn giá trị cho nhiều hàng

~~~sql
UPDATE sales_orders
SET order_status = CASE
    WHEN total_amount >= 500 THEN 'REVIEW'
    ELSE 'PROCESSING'
END
WHERE order_status = 'NEW';
~~~

Không cần duyệt từng đơn để gán trạng thái khác nhau.

### 22.3. CASE statement phù hợp khi một trạng thái dẫn tới nhóm lệnh khác nhau

~~~sql
CASE v_status
    WHEN 'NEW' THEN
        v_action := 'TRIAGE';
    WHEN 'PROCESSING' THEN
        v_action := 'CONTINUE';
    WHEN 'PAID' THEN
        v_action := 'NO_ACTION';
    ELSE
        RAISE EXCEPTION 'Unsupported status: %', v_status;
END CASE;
~~~

`v_status` và `v_action` là các biến giả định đã khai báo trong một PL/pgSQL block. Cấu trúc phù hợp khi nhiều nhánh cần tác động thủ tục khác nhau.

### 22.4. LOOP phù hợp khi kết quả từng bước quyết định bước sau

Ví dụ tìm giá trị hợp lệ đầu tiên trong một mảng, hoặc thử một thuật toán có giới hạn. Nếu nhiệm vụ là **cập nhật hàng nghìn hàng bằng quy tắc đồng nhất**, ưu tiên SQL set-based.

### 22.5. Không chọn vì cảm giác “thủ tục mạnh hơn SQL”

Một procedure chứa hàng nghìn lệnh nhỏ có thể làm khó tối ưu, tăng chi phí, giữ transaction dài và phân tán business rule trong database.

Trước khi thêm vòng lặp, tự hỏi:

> Có thể viết một câu `SELECT`, `UPDATE ... CASE`, `INSERT ... SELECT`, `MERGE` hoặc `WITH RECURSIVE` đúng nghiệp vụ thay cho vòng này không?

Nếu có, lựa chọn khai báo theo tập thường dễ đọc và hiệu quả hơn. Nếu không, một vòng lặp thủ tục có điều kiện kết thúc rõ mới là lựa chọn hợp lý.

## 23. Các lỗi và hiểu nhầm thường gặp

| Lỗi/hiểu nhầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Dùng `IF` trực tiếp bên trong SELECT PostgreSQL | Sai cú pháp vì IF là statement PL/pgSQL | Dùng SQL `CASE`/`COALESCE` |
| Dùng `CASE...END CASE` như một biểu thức SQL | Sai cú pháp | SQL expression kết thúc bằng `END` |
| Dùng `CASE...END` trong PL/pgSQL statement | Sai cú pháp statement | Dùng `END CASE;` |
| Quên ELSE ở PL/pgSQL CASE statement | Có thể phát sinh `CASE_NOT_FOUND` | Thêm ELSE có chủ đích |
| Nghĩ SQL CASE không ELSE sẽ ném CASE_NOT_FOUND | Hiểu sai | SQL CASE expression trả NULL khi không khớp |
| Viết `ELSEIF` trong PostgreSQL PL/pgSQL | Sai cú pháp | Dùng `ELSIF` |
| Dùng `= NULL` trong IF/CASE | Điều kiện không TRUE | Dùng `IS NULL` |
| Đặt IF rộng trước IF cụ thể | Nhánh sau không được chạy | Xếp điều kiện theo ưu tiên |
| Bỏ bước tăng biến trong WHILE | Lặp vô hạn | Bảo đảm tiến độ/điều kiện dừng |
| Đặt EXIT WHEN trước câu cần thực hiện | Lỗi off-by-one | Xác định thứ tự xét điều kiện |
| Nhầm `EXIT` và `RETURN` | Chương trình tiếp tục ngoài vòng | RETURN khi muốn kết thúc function |
| Nhầm `CONTINUE` và `EXIT` | Bỏ qua sai phạm vi | CONTINUE sang lượt sau, EXIT rời vòng |
| Dùng nhãn sai ở vòng lặp lồng nhau | Thoát hoặc bỏ lượt ở vòng sai | Đặt tên nhãn rõ, giảm lồng nhau |
| Nghĩ integer FOR đọc lại cận mỗi lượt | Kết quả số lượt không như mong muốn | FOR cận tính lúc vào vòng |
| Dùng FOR r IN SELECT mà tưởng SELECT chạy lại mỗi lượt | Không thấy dữ liệu thay đổi như kỳ vọng | Hiểu snapshot/query execution |
| Dùng LOOP chờ trạng thái ngoài vô hạn | Tốn CPU, transaction dài | Polling/scheduler với timeout/backoff |
| Không kiểm tra `FOUND` hoặc ROW_COUNT | Báo đã UPDATE dù 0 hàng | Kiểm tra kết quả DML |
| Đọc `FOUND` sau nhiều câu SQL khác | Kết luận sai về truy vấn ban đầu | Kiểm tra ngay sau lệnh liên quan |
| SELECT rồi IF rồi UPDATE không guard | Race condition | Đặt điều kiện vào UPDATE WHERE |
| `WHEN OTHERS THEN NULL` | Nuốt mọi lỗi quan trọng | Xử lý đúng loại exception |
| Dùng vòng FOR UPDATE hàng triệu dòng | Chậm và khó quản trị lock | Ưu tiên UPDATE set-based |
| Gọi procedure và tưởng transaction tự commit | Sai ranh giới giao dịch | Quản lý transaction ở nơi gọi phù hợp |
| Giả định MySQL/SQL Server/Oracle cùng cú pháp | Không chạy hoặc sai ngữ nghĩa | Viết theo dialect |
| Nghĩ function trả tập dùng RETURN NEXT sẽ kết thúc | Thiếu các hàng sau hoặc hiểu sai | RETURN NEXT thêm hàng, RETURN mới kết thúc |
| Dùng vòng retry không có ngưỡng | Có thể lặp mãi | Đặt max attempts và trạng thái thất bại |

## 24. Bài tập thực hành có đáp án

Các bài dùng bảng `sales_orders` ở mục 3. Những đoạn có UPDATE nên chạy trong transaction rồi rollback, hoặc tạo lại dữ liệu mẫu. Các khối `DO` không sửa bảng có thể chạy trực tiếp.

### Bài 1 — IF đơn giản

Khai báo `v_amount=600`. In `REVIEW` nếu số tiền từ 500 trở lên.

**Đáp án:**

~~~sql
DO $$
DECLARE
    v_amount NUMERIC := 600;
BEGIN
    IF v_amount >= 500 THEN
        RAISE NOTICE 'REVIEW';
    END IF;
END;
$$;
~~~

Vì điều kiện TRUE, thông báo xuất hiện.

### Bài 2 — IF/ELSIF thứ tự ưu tiên

Một khoản tiền 120 cần được phân loại HIGH nếu ≥500, MEDIUM nếu ≥100, LOW nếu >0, ZERO nếu bằng 0. Viết đúng thứ tự.

**Đáp án:**

~~~sql
DO $$
DECLARE
    v_amount NUMERIC := 120;
    v_band TEXT;
BEGIN
    IF v_amount >= 500 THEN
        v_band := 'HIGH';
    ELSIF v_amount >= 100 THEN
        v_band := 'MEDIUM';
    ELSIF v_amount > 0 THEN
        v_band := 'LOW';
    ELSE
        v_band := 'ZERO';
    END IF;

    RAISE NOTICE '%', v_band;
END;
$$;
~~~

Kết quả MEDIUM.

### Bài 3 — IF và NULL

Nếu `v_amount = NULL`, điều kiện `IF v_amount >= 500` có chạy nhánh THEN không?

**Đáp án:** không. Biểu thức nhận UNKNOWN/NULL chứ không TRUE. Muốn báo “thiếu dữ liệu”, viết `IF v_amount IS NULL THEN ...` trước.

### Bài 4 — Phân biệt CASE expression và statement

Hai đoạn:

~~~sql
-- A: SQL expression
SELECT CASE WHEN 1 = 2 THEN 'YES' END AS label;

-- B: PL/pgSQL statement ở trong một block
CASE v_status
    WHEN 'PAID' THEN
        RAISE NOTICE 'Paid';
END CASE;
~~~

Giả sử `v_status='NEW'`. Điều gì xảy ra?

**Đáp án:** A trả `NULL`. B phát sinh `CASE_NOT_FOUND` nếu không có ELSE, vì CASE statement PL/pgSQL không khớp nhánh. Đoạn B chỉ hợp lệ bên trong block PL/pgSQL có biến `v_status`.

### Bài 5 — CASE đơn giản theo trạng thái

Tạo nhãn tiếng Anh: NEW → New, PAID → Paid, CANCELLED → Cancelled, còn lại → Other.

**Đáp án:**

~~~sql
SELECT
    order_id,
    CASE order_status
        WHEN 'NEW' THEN 'New'
        WHEN 'PAID' THEN 'Paid'
        WHEN 'CANCELLED' THEN 'Cancelled'
        ELSE 'Other'
    END AS status_label
FROM sales_orders;
~~~

Đây là biểu thức SQL dùng cho từng hàng, không phải CASE statement PL/pgSQL.

### Bài 6 — LOOP với EXIT WHEN

Đếm từ 1 đến 4, mỗi lượt in số rồi thoát khi đạt 4.

**Đáp án:**

~~~sql
DO $$
DECLARE
    v_i INTEGER := 0;
BEGIN
    LOOP
        v_i := v_i + 1;
        RAISE NOTICE '%', v_i;
        EXIT WHEN v_i >= 4;
    END LOOP;
END;
$$;
~~~

In 1, 2, 3, 4.

### Bài 7 — Off-by-one

Đoạn:

~~~sql
LOOP
    v_i := v_i + 1;
    EXIT WHEN v_i >= 4;
    RAISE NOTICE '%', v_i;
END LOOP;
~~~

với `v_i=0` ban đầu in gì?

**Đáp án:** 1, 2, 3; lần v_i=4 thoát **trước** RAISE NOTICE.

### Bài 8 — WHILE

In các số từ 1 đến 5 bằng WHILE.

**Đáp án:**

~~~sql
DO $$
DECLARE
    v_i INTEGER := 1;
BEGIN
    WHILE v_i <= 5 LOOP
        RAISE NOTICE '%', v_i;
        v_i := v_i + 1;
    END LOOP;
END;
$$;
~~~

Dừng vì v_i tăng tới 6, điều kiện không còn TRUE.

### Bài 9 — WHILE vô hạn

Vì sao đoạn sau nguy hiểm?

~~~sql
v_i := 1;
WHILE v_i <= 5 LOOP
    RAISE NOTICE '%', v_i;
END LOOP;
~~~

**Đáp án:** không có bước tăng hoặc thay đổi v_i, nên điều kiện luôn TRUE. Thêm `v_i := v_i + 1` hoặc thay bằng FOR nếu biết cận.

### Bài 10 — FOR số nguyên và REVERSE

In 5, 4, 3, 2, 1.

**Đáp án:**

~~~sql
DO $$
BEGIN
    FOR i IN REVERSE 5..1 LOOP
        RAISE NOTICE '%', i;
    END LOOP;
END;
$$;
~~~

### Bài 11 — FOR BY 2

In các số 2, 4, 6, 8.

**Đáp án:**

~~~sql
DO $$
BEGIN
    FOR i IN 2..8 BY 2 LOOP
        RAISE NOTICE '%', i;
    END LOOP;
END;
$$;
~~~

### Bài 12 — CONTINUE WHEN

In các số lẻ từ 1 đến 7 bằng FOR, bỏ qua số chẵn.

**Đáp án:**

~~~sql
DO $$
BEGIN
    FOR i IN 1..7 LOOP
        CONTINUE WHEN i % 2 = 0;
        RAISE NOTICE '%', i;
    END LOOP;
END;
$$;
~~~

Kết quả 1, 3, 5, 7.

### Bài 13 — EXIT và RETURN

Một function tìm số dương đầu tiên trong array. Khi tìm được, nên dùng `EXIT` hay `RETURN`?

**Đáp án:** dùng `RETURN value` nếu muốn **trả kết quả và kết thúc toàn function**. `EXIT` chỉ thoát vòng lặp, sau đó function vẫn chạy những câu lệnh phía sau và cần RETURN thích hợp.

### Bài 14 — FOR r IN SELECT

Duyệt các đơn `NEW` theo ID tăng dần và thông báo mã + số tiền.

**Đáp án:**

~~~sql
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN
        SELECT order_id, total_amount
        FROM sales_orders
        WHERE order_status = 'NEW'
        ORDER BY order_id
    LOOP
        RAISE NOTICE
            'Order %, amount %',
            r.order_id, r.total_amount;
    END LOOP;
END;
$$;
~~~

Với dữ liệu mẫu, có các ID 101, 102, 103, 106, 108.

### Bài 15 — Khi FOR SELECT không có hàng

Nếu vòng FOR query không tìm thấy đơn nào ở trạng thái `NEW`, thân vòng lặp chạy mấy lần?

**Đáp án:** **0 lần**. Không tự coi đó là lỗi. Nếu nghiệp vụ yêu cầu phải có ít nhất một đơn, cần kiểm tra hoặc báo trạng thái phù hợp.

### Bài 16 — FOUND sau SELECT INTO

Viết khối đọc trạng thái `order_id=999` rồi thông báo nếu không tìm thấy.

**Đáp án:**

~~~sql
DO $$
DECLARE
    v_status TEXT;
BEGIN
    SELECT o.order_status
    INTO v_status
    FROM sales_orders AS o
    WHERE o.order_id = 999;

    IF NOT FOUND THEN
        RAISE NOTICE 'NOT_FOUND';
    ELSE
        RAISE NOTICE '%', v_status;
    END IF;
END;
$$;
~~~

Kết quả NOT_FOUND.

### Bài 17 — UPDATE có điều kiện và ROW_COUNT

Chuyển đơn 101 từ NEW sang PROCESSING, nhưng chỉ khi hiện tại vẫn NEW. Sau đó kiểm tra số hàng được cập nhật.

**Đáp án:**

~~~sql
BEGIN;

DO $$
DECLARE
    v_affected BIGINT;
BEGIN
    UPDATE sales_orders
    SET order_status = 'PROCESSING'
    WHERE order_id = 101
      AND order_status = 'NEW';

    GET DIAGNOSTICS v_affected = ROW_COUNT;

    IF v_affected = 1 THEN
        RAISE NOTICE 'UPDATED';
    ELSE
        RAISE NOTICE 'NOT_UPDATED';
    END IF;
END;
$$;

ROLLBACK;
~~~

Với trạng thái gốc, có một hàng được chuyển. Điều kiện status nằm **trong chính UPDATE**, tránh kiểm tra cũ rồi ghi không bảo vệ.

### Bài 18 — CASE thay vòng lặp

Phân loại **tất cả đơn NEW**: tiền từ 500 trở lên thành REVIEW, còn lại PROCESSING.

**Đáp án:**

~~~sql
BEGIN;

UPDATE sales_orders
SET order_status = CASE
    WHEN total_amount >= 500 THEN 'REVIEW'
    ELSE 'PROCESSING'
END
WHERE order_status = 'NEW'
RETURNING order_id, total_amount, order_status;

ROLLBACK;
~~~

Với dữ liệu mẫu: đơn 102 và 106 thành REVIEW; 101, 103, 108 thành PROCESSING. Không cần FOR loop.

### Bài 19 — FOREACH

Duyệt mảng `['NEW','PAID','REVIEW']` và bỏ qua `PAID`.

**Đáp án:**

~~~sql
DO $$
DECLARE
    v_status TEXT;
BEGIN
    FOREACH v_status IN ARRAY
        ARRAY['NEW', 'PAID', 'REVIEW']
    LOOP
        CONTINUE WHEN v_status = 'PAID';
        RAISE NOTICE '%', v_status;
    END LOOP;
END;
$$;
~~~

Chỉ thông báo NEW và REVIEW.

### Bài 20 — FOR cận được tính khi nào?

`v_upper=3`. Trong vòng `FOR i IN 1..v_upper LOOP`, thân vòng gán `v_upper := 10`. Có chạy tới 10 không?

**Đáp án:** không. Trong PL/pgSQL, cận số được tính khi vào vòng; vẫn lặp 1, 2, 3. Nếu cần kiểm tra giới hạn thay đổi ở mỗi lượt, dùng WHILE/LOOP có điều kiện thích hợp.

### Bài 21 — Vòng lặp lồng nhau

Có hai vòng FOR lồng nhau, bạn muốn thoát **cả vòng ngoài** khi `i*j>=4`. Nên viết gì?

**Đáp án:** đặt nhãn:

~~~sql
DO $$
BEGIN
    <<outer_loop>>
    FOR i IN 1..3 LOOP
        FOR j IN 1..3 LOOP
            EXIT outer_loop WHEN i * j >= 4;
        END LOOP;
    END LOOP outer_loop;
END;
$$;
~~~

`EXIT` không nhãn chỉ thoát vòng trong.

### Bài 22 — RETURN NEXT và RETURN QUERY

Một function `RETURNS SETOF INTEGER` dùng `RETURN NEXT i` trong vòng FOR. Lệnh đó có kết thúc function ngay không?

**Đáp án:** không. Nó **thêm một hàng** vào tập kết quả rồi cho phép function tiếp tục. `RETURN QUERY SELECT...` thêm kết quả từ SELECT; `RETURN;` mới kết thúc function trả tập.

### Bài 23 — Ngoại lệ không phải vòng lặp bỏ qua lỗi

Một người viết `EXCEPTION WHEN OTHERS THEN NULL` bao quanh mọi xử lý đơn hàng. Vì sao nguy hiểm?

**Đáp án:** có thể che constraint, lỗi data, sai SQL, mất kết nối hoặc lỗi transaction. Cần bắt **đúng loại lỗi có thể xử lý**, ghi nhận nguyên nhân, rollback đúng phạm vi và có giới hạn retry. Không xem “không có exception đến client” là đã xử lý thành công.

### Bài 24 — So sánh PostgreSQL và MySQL

Hãy điền từ khóa tương ứng:

- PostgreSQL: `IF ... ____ ... END IF`.
- MySQL: `IF ... ____ ... END IF`.
- PostgreSQL: thoát vòng bằng `____`.
- MySQL: thoát vòng có nhãn bằng `____`.
- SQL Server: thoát WHILE bằng `____`.

**Đáp án:** PostgreSQL `ELSIF`; MySQL `ELSEIF`; PostgreSQL `EXIT`; MySQL `LEAVE`; SQL Server `BREAK`.

### Bài 25 — Đề xuất giải pháp điều khiển luồng

Một hệ thống cần mỗi đêm phân loại 100.000 đơn mới theo số tiền, dùng cùng quy tắc cho mọi đơn. Nên dùng một PL/pgSQL FOR loop UPDATE từng đơn, hay một SQL UPDATE với CASE?

**Đáp án:** bắt đầu bằng **UPDATE theo tập với CASE** và điều kiện WHERE rõ, rồi đo hiệu năng và phạm vi transaction. Vòng lặp chỉ nên dùng nếu mỗi đơn có workflow riêng thực sự cần điều khiển tuần tự. Nếu chia việc cho nhiều worker, dùng cơ chế queue/batch/locking phù hợp thay vì vòng lặp chờ vô hạn trong database.

## 25. Checklist trước khi triển khai thủ tục hoặc hàm

1. **Mục đích:** Logic này có cần thủ tục thật không, hay một câu SQL theo tập là đủ?
2. **Ngôn ngữ:** Đang dùng PL/pgSQL, MySQL routine, T-SQL hay PL/SQL? Từ khóa có đúng dialect?
3. **Nhánh:** Điều kiện nào ưu tiên? Các nhánh chồng lấn có bị che không?
4. **NULL:** Có phân biệt FALSE với UNKNOWN/NULL và dùng `IS NULL` chưa?
5. **CASE:** Đang cần một **giá trị** (`CASE expression`) hay **nhóm lệnh** (`CASE statement`)?
6. **ELSE:** Nếu không nhánh nào khớp, chương trình trả gì hoặc phát lỗi gì?
7. **Vòng lặp:** Có trạng thái khởi tạo, điều kiện dừng và bước tiến rõ ràng?
8. **Giới hạn:** Vòng retry có tối đa bao nhiêu lần và xử lý khi hết lượt ra sao?
9. **Off-by-one:** `EXIT WHEN` đặt trước hay sau tác động cần thực hiện?
10. **Nhãn:** `EXIT`/`CONTINUE` tác động vòng nào khi lồng nhau?
11. **RETURN:** Function có trả kết quả/exception trên mọi đường phù hợp không?
12. **Truy vấn nguồn:** `FOR ... IN SELECT` có giả định sai về thứ tự/snapshot không?
13. **ROW_COUNT/FOUND:** Có kiểm tra ngay sau lệnh liên quan và phân biệt 0/1/bất thường?
14. **Concurrency:** Kiểm tra trạng thái nghiệp vụ có nằm trong điều kiện UPDATE tại thời điểm ghi?
15. **Transaction:** Có giữ transaction mở quá lâu khi lặp không? Có side effects ngoài database?
16. **Exception:** Có phân loại lỗi và tránh `WHEN OTHERS THEN NULL`?
17. **Khối lượng:** Có đang tạo hàng nghìn DML nhỏ thay vì một câu theo tập?
18. **Tính khả chuyển:** Những chức năng nào cần viết lại khi chuyển DBMS?
19. **Quyền:** Function/procedure chạy với quyền người gọi hay chủ sở hữu theo khai báo?
20. **Quan sát:** Có logging/metrics phù hợp nhưng không spam NOTICE hoặc lộ dữ liệu nhạy cảm?

## 26. Tổng kết

Trong stored functions và procedures, **điều khiển luồng** giúp thể hiện rõ thứ tự và điều kiện thực thi:

- **`IF`** quyết định chạy nhánh lệnh nào theo điều kiện TRUE. `ELSIF` xét nhiều điều kiện theo thứ tự; với PostgreSQL, giá trị NULL trong điều kiện không được coi là TRUE.
- **`CASE` biểu thức SQL** chọn **giá trị** và kết thúc bằng `END`; không có ELSE thì trả NULL khi không khớp. **`CASE` statement PL/pgSQL** chạy **nhóm lệnh**, kết thúc bằng `END CASE;` và có thể phát sinh `CASE_NOT_FOUND` nếu không có nhánh phù hợp.
- **`LOOP`** cần đường thoát tường minh; **`WHILE`** kiểm tra điều kiện trước mỗi lượt; **`FOR`** thích hợp cho khoảng số hoặc tập hàng truy vấn; **`FOREACH`** duyệt mảng.
- **`EXIT`** rời vòng, **`CONTINUE`** bỏ phần còn lại của lượt, còn **`RETURN`** kết thúc function hoặc procedure theo ngữ cảnh. Nhãn giúp xác định phạm vi ở vòng lặp lồng nhau.
- **`FOUND`** và **`GET DIAGNOSTICS ROW_COUNT`** hỗ trợ quyết định sau truy vấn/DML, nhưng phải kiểm tra đúng thời điểm.
- Một vòng lặp an toàn cần **bước tiến, điều kiện kết thúc và giới hạn xử lý**. Một quy trình đồng thời phải dùng transaction và điều kiện DML phù hợp, không chỉ SELECT rồi IF.

**Nguyên tắc quan trọng nhất:** dùng điều khiển luồng khi thật sự cần các bước thủ tục; còn nếu cùng một quy tắc áp dụng được cho nhiều hàng, hãy ưu tiên **SQL theo tập** như `UPDATE ... CASE` hoặc CTE. Điều khiển luồng đúng không chỉ là biết cú pháp `IF` hay `LOOP`, mà còn biết **khi nào dừng, kết quả nào được trả và dữ liệu nào có thể bị thay đổi đồng thời**.
