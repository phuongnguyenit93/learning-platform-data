# Hàm định dạng, chuyển đổi kiểu và phân tích dữ liệu trong PostgreSQL

Một hệ thống quản lý đơn hàng thường phải giải quyết ba nhóm công việc liên tiếp: **đọc dữ liệu đúng kiểu**, **tính toán/thống kê trên giá trị có ý nghĩa**, rồi **định dạng kết quả để hiển thị hoặc xuất báo cáo**. Ví dụ, giá trị tiền nên được lưu dưới dạng `numeric` để cộng chính xác, thời điểm đặt hàng nên dùng `timestamptz` nếu cần biểu diễn một thời điểm thực, còn giao diện có thể cần chuỗi như `125,000.50` và ngày `10/02/2026`.

PostgreSQL cung cấp nhiều hàm và biểu thức cho những nhu cầu đó:

- **Định dạng:** `to_char`, `format`, `concat_ws`, `lpad` và các hàm chuỗi.
- **Chuyển đổi kiểu:** `CAST(... AS ...)`, toán tử `::`, `to_date`, `to_timestamp`, `to_number`, `pg_typeof`.
- **Xử lý thời gian và JSON:** `date_trunc`, `extract`, `AT TIME ZONE`, `jsonb_build_object`, `->` và `->>`.
- **Phân tích dữ liệu:** `COUNT`, `SUM`, `AVG`, `FILTER`, `PERCENTILE_CONT`, `STDDEV_SAMP` và window functions như `ROW_NUMBER`, `LAG`, `LEAD`.

Những công cụ này liên quan chặt chẽ nhưng **không thay thế nhau**. `to_char` tạo **chuỗi phục vụ hiển thị**, không phải cách lưu một số tiền; `CAST` thay **kiểu giá trị**; còn window function có thể tính thống kê mà vẫn giữ từng hàng đầu vào.

Bài học sử dụng PostgreSQL hiện đại với các ví dụ SQL tự chứa, chỉ ra những lỗi thường gặp về `NULL`, múi giờ, định dạng số theo locale, dữ liệu nhập sai và độ chính xác số học. Phần cuối có bài tập thực hành, lời giải và hướng dẫn chọn hàm cho từng trường hợp.

## 1. Phân biệt giá trị, kiểu dữ liệu và cách biểu diễn

Xem ba biểu thức:

~~~sql
SELECT
    125000.50::numeric(12, 2) AS money_value,
    '125000.50'::text AS money_text,
    to_char(125000.50::numeric, 'FM999,999,990.00')
        AS formatted_money;
~~~

Chúng có thể trông gần giống nhau ở giao diện SQL, nhưng khác bản chất:

| Biểu thức | Kiểu/ý nghĩa | Thích hợp |
| --- | --- | --- |
| `125000.50::numeric(12,2)` | Số thập phân chính xác theo precision/scale | Lưu, so sánh, cộng/trừ/tính giá |
| `'125000.50'::text` | Chuỗi ký tự | Dữ liệu nhập thô, nhãn, tài liệu |
| `to_char(..., 'FM999,999,990.00')` | Chuỗi đã định dạng | Hiển thị số có dấu phân nhóm, xuất báo cáo |

Nếu sắp xếp các chuỗi tiền theo thứ tự chữ cái, kết quả có thể khác sắp xếp số. Ví dụ `'900'` có thể đứng sau `'1000'` trong so sánh từ điển, dù 900 nhỏ hơn 1000.

**Quy tắc:** lưu giá trị theo kiểu phản ánh ý nghĩa nghiệp vụ, xử lý bằng các phép toán phù hợp kiểu, và chỉ định dạng ở ranh giới hiển thị hoặc khi xuất dữ liệu.

### 1.1. Hàm và toán tử không phải lúc nào cũng trả về kiểu đầu vào

~~~sql
SELECT
    pg_typeof(125000.50::numeric) AS input_type,
    pg_typeof(to_char(125000.50::numeric, 'FM999999.00'))
        AS output_type,
    pg_typeof('2026-02-10'::date) AS date_type;
~~~

`pg_typeof(expression)` cho biết **kiểu mà PostgreSQL gán cho biểu thức**. Dùng nó khi bạn không chắc kết quả của phép tính, cast hoặc hàm được xử lý dưới dạng `text`, `numeric`, `date` hay `timestamptz`.

## 2. Chuẩn bị bộ dữ liệu thực hành

Những ví dụ dưới đây dành cho **database PostgreSQL thực hành**, không chạy DDL này trên hệ thống có dữ liệu cần giữ.

### 2.1. Tạo schema và bảng

~~~sql
CREATE SCHEMA expr_lab;

CREATE TABLE expr_lab.customers (
    customer_id integer PRIMARY KEY,
    full_name text NOT NULL,
    email text NOT NULL UNIQUE,
    signup_at timestamptz NOT NULL
);

CREATE TABLE expr_lab.orders (
    order_id integer PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES expr_lab.customers(customer_id),
    ordered_at timestamptz NOT NULL,
    status text NOT NULL CHECK (
        status IN ('paid', 'pending', 'cancelled', 'refunded')
    ),
    amount numeric(12, 2) NOT NULL CHECK (amount >= 0),
    channel text NOT NULL,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);
~~~

Cách chọn kiểu:

- `integer` cho các ID nhỏ trong lab; hệ thống tăng trưởng lớn có thể cần `bigint` hoặc chiến lược ID khác.
- `timestamptz` lưu **thời điểm tuyệt đối**; khi hiển thị cần chọn múi giờ tương ứng.
- `numeric(12,2)` để tính tiền bằng số thập phân, không dùng `float` nếu muốn tránh sai số nhị phân cho phép tính tài chính cơ bản.
- `metadata jsonb` chứa thông tin bổ sung thay đổi tùy đơn; các thuộc tính truy vấn thường xuyên như `status` và `channel` vẫn là cột rõ ràng.

### 2.2. Thêm khách hàng

~~~sql
INSERT INTO expr_lab.customers (
    customer_id, full_name, email, signup_at
) VALUES
    (1, 'Lan Nguyen', 'Lan@Example.test',
        '2026-01-05 08:00:00+07'),
    (2, 'Minh Tran', 'minh@example.test',
        '2026-01-08 10:00:00+07'),
    (3, 'An Le', 'an@example.test',
        '2026-01-10 09:00:00+07'),
    (4, 'Chi Pham', 'chi@example.test',
        '2026-02-01 14:00:00+07');
~~~

Khách Chi chưa có đơn hàng để minh họa nhóm rỗng trong thống kê.

### 2.3. Thêm chín đơn hàng

~~~sql
INSERT INTO expr_lab.orders (
    order_id, customer_id, ordered_at, status,
    amount, channel, metadata
) VALUES
    (1001, 1, '2026-01-10 10:15:00+07', 'paid',
        125000.50, 'web',
        '{"promo":"TET","risk_score":4,"labels":["gift","new"]}'),
    (1002, 1, '2026-01-12 14:00:00+07', 'pending',
        80000.00, 'web',
        '{"risk_score":2,"labels":["review"]}'),
    (1003, 2, '2026-01-13 09:00:00+07', 'paid',
        90000.00, 'store',
        '{"promo":"NONE","risk_score":1,"labels":[]}'),
    (1004, 3, '2026-01-14 11:20:00+07', 'paid',
        250000.00, 'partner',
        '{"promo":"TET","risk_score":5,"labels":["vip"]}'),
    (1005, 2, '2026-02-02 16:40:00+07', 'cancelled',
        50000.00, 'web',
        '{"labels":["cancel_request"]}'),
    (1006, 1, '2026-02-04 08:05:00+07', 'paid',
        140000.00, 'web',
        '{"risk_score":2,"labels":["vip"]}'),
    (1007, 3, '2026-02-08 19:00:00+07', 'refunded',
        100000.00, 'partner',
        '{"promo":"NONE","labels":["refund"]}'),
    (1008, 2, '2026-02-10 12:10:00+07', 'paid',
        65000.00, 'store',
        '{"risk_score":3,"labels":[]}'),
    (1009, 3, '2026-02-11 17:30:00+07', 'paid',
        200000.00, 'web',
        '{"risk_score":4,"labels":["gift","vip"]}');
~~~

Kiểm tra nhanh:

~~~sql
SELECT status, COUNT(*) AS order_count
FROM expr_lab.orders
GROUP BY status
ORDER BY status;
~~~

Kết quả dự kiến: **6 paid, 1 pending, 1 cancelled, 1 refunded**; tổng cộng 9 đơn. Tổng `amount` của **các đơn hiện có trạng thái paid** là **870000.50**. Con số này trong lab chỉ là tổng giá trị đơn theo trạng thái, chưa phải cách định nghĩa doanh thu thuần cho hệ thống kế toán thật.

## 3. Chuyển đổi kiểu bằng CAST và ::

PostgreSQL hỗ trợ hai cách ép kiểu phổ biến:

~~~sql
CAST(expression AS target_type)
~~~

và:

~~~sql
expression::target_type
~~~

Ví dụ:

~~~sql
SELECT
    CAST('123' AS integer) AS a,
    '123'::integer AS b,
    '2026-02-10'::date AS d,
    'true'::boolean AS flag,
    '125000.50'::numeric(12, 2) AS amount;
~~~

`CAST` là cú pháp chuẩn SQL, còn `::` là cú pháp PostgreSQL rất phổ biến. Cả hai yêu cầu một **phép chuyển đổi hợp lệ** giữa kiểu nguồn và kiểu đích.

### 3.1. Literal chuỗi và biểu thức đã có kiểu

~~~sql
SELECT '42'::integer;
~~~

Ở đây `'42'` là literal chuỗi chưa được gán một kiểu cụ thể cho tới khi PostgreSQL giải quyết biểu thức; việc ép sang integer rõ ràng.

Trong prepared statement hoặc biểu thức `text` đã có kiểu, quy tắc ép kiểu có thể khác; không phải mọi phép chuyển `text` sang enum, số hay ngày đều tự xảy ra một cách ngầm định.

### 3.2. Cast có thể thất bại

~~~sql
-- Cố ý gây lỗi:
SELECT '12x'::integer;

-- Cố ý gây lỗi:
SELECT 'not-a-date'::date;

-- Cố ý gây lỗi vì số ngoài phạm vi integer:
SELECT '9999999999999999999'::integer;
~~~

Nếu thực hiện trong transaction, lỗi PostgreSQL thường đưa transaction vào trạng thái *aborted*. Hãy dùng `ROLLBACK` hoặc rollback tới savepoint phù hợp trước khi tiếp tục.

### 3.3. Cast không đồng nghĩa bỏ phần thập phân

~~~sql
SELECT
    123.456::numeric(10, 2) AS rounded_to_scale,
    trunc(123.456::numeric, 2) AS truncated_to_scale,
    round(123.456::numeric, 2) AS explicit_round;
~~~

Kết quả kỳ vọng:

| Biểu thức | Giá trị |
| --- | ---: |
| `123.456::numeric(10,2)` | 123.46 |
| `trunc(123.456::numeric,2)` | 123.45 |
| `round(123.456::numeric,2)` | 123.46 |

`numeric(precision, scale)` giới hạn **độ chính xác và số chữ số thập phân**; khi chuyển kiểu sang scale thấp hơn, PostgreSQL có thể làm tròn. Nếu nghiệp vụ muốn **cắt** phần thập phân, hãy gọi `trunc` tường minh. Không giả định một cast sang `integer` luôn làm giống `trunc`; cách chuyển đổi số và chính sách làm tròn cần được hiểu theo kiểu nguồn/đích.

## 4. Chuyển đổi chuỗi nhập thô một cách an toàn

Trong import CSV hoặc dữ liệu API cũ, đầu vào có thể chứa dấu cách, chuỗi rỗng hoặc giá trị sai:

~~~text
'1250.50'
' 900.00 '
''
'N/A'
'15x'
NULL
~~~

Chạy `raw_value::numeric` trực tiếp trên mọi dòng có thể khiến **cả câu truy vấn thất bại** khi gặp một giá trị không hợp lệ.

### 4.1. Dùng BTRIM, NULLIF và CASE

~~~sql
WITH raw_input(raw_value) AS (
    VALUES
        ('1250.50'::text),
        (' 900.00 '::text),
        (''::text),
        ('N/A'::text),
        ('15x'::text),
        (NULL::text)
),
normalized AS (
    SELECT raw_value, NULLIF(btrim(raw_value), '') AS cleaned
    FROM raw_input
)
SELECT
    raw_value,
    cleaned,
    CASE
        WHEN cleaned ~ '^[0-9]+([.][0-9]{1,2})?$'
        THEN cleaned::numeric(12, 2)
        ELSE NULL
    END AS parsed_amount
FROM normalized;
~~~

Cách đọc:

1. `btrim` bỏ khoảng trắng đầu/cuối theo quy tắc mặc định.
2. `NULLIF(cleaned, '')` chuyển chuỗi rỗng thành SQL `NULL`.
3. Biểu thức regular expression kiểm tra **định dạng decimal đơn giản không âm** với tối đa hai chữ số sau dấu chấm.
4. Chỉ khi dữ liệu thỏa pattern mới ép sang `numeric`; giá trị không phù hợp được trả `NULL` để xử lý riêng.

### Hạn chế quan trọng

Biểu thức chính quy trên chỉ mô tả **định dạng**, không bảo đảm giá trị nằm trong phạm vi `numeric(12,2)`. Một chuỗi quá dài vẫn có thể overflow khi cast. Nếu cần pipeline import bền vững, hãy kiểm tra cả độ dài/phạm vi, định nghĩa chính sách lỗi và lưu giá trị nguồn để truy nguyên.

Trong hệ thống thực tế, không nên âm thầm coi mọi đầu vào sai là null rồi bỏ qua: có thể cần cột `parse_error`, bảng lỗi import hoặc bước từ chối bản ghi.

### 4.2. NULLIF không phải COALESCE

~~~sql
SELECT
    NULLIF('', '') AS empty_to_null,
    COALESCE(NULL::text, 'unknown') AS null_to_default;
~~~

- `NULLIF(a,b)` trả null khi `a=b`; hữu ích để chuyển placeholder như chuỗi rỗng thành null.
- `COALESCE(a,b,...)` trả đối số **khác null đầu tiên**; hữu ích khi muốn giá trị mặc định.

Với dữ liệu tài chính, “không biết số tiền” khác “số tiền bằng 0”. `COALESCE(parsed_amount, 0)` chỉ đúng nếu nghiệp vụ cho phép coi giá trị thiếu là 0.

## 5. Hàm định dạng số: TO_CHAR

`to_char` chuyển một số hoặc một giá trị ngày/giờ thành **text theo mẫu định dạng**.

Ví dụ số:

~~~sql
SELECT
    amount,
    to_char(amount, 'FM999,999,990.00') AS amount_display
FROM expr_lab.orders
WHERE order_id = 1001;
~~~

Giá trị số `125000.50` được biểu diễn dưới dạng có dấu phân nhóm và hai chữ số phần thập phân, ví dụ `125,000.50` theo mặt nạ định dạng đã chọn.

### 5.1. Một số ký hiệu mẫu số thường dùng

| Ký hiệu | Ý nghĩa | Ghi chú |
| --- | --- | --- |
| `9` | Vị trí chữ số, có thể để khoảng trống khi không cần | Phụ thuộc độ rộng mẫu |
| `0` | Vị trí chữ số buộc hiển thị 0 khi cần | Hữu ích để giữ số chữ số thập phân |
| `.` | Dấu phân cách thập phân trong mẫu | Có thể khác `D` theo locale |
| `,` | Dấu phân nhóm trong mẫu | Có thể khác `G` theo locale |
| `D` | Dấu thập phân theo locale | Xem cấu hình `lc_numeric` |
| `G` | Dấu phân nhóm theo locale | Xem cấu hình `lc_numeric` |
| `FM` | Fill mode, hạn chế khoảng đệm/0 đệm theo quy tắc mẫu | Đặt trước template |
| `S` | Dấu dương/âm theo mẫu | Không phải mọi định dạng tiền đều giống nhau |

Ví dụ:

~~~sql
SELECT
    to_char(125000.50::numeric, 'FM999,999,990.00')
        AS fixed_separator,
    to_char(125000.50::numeric, 'FM999G999G990D00')
        AS locale_separator,
    to_char(-1250.50::numeric, 'FM999,990.00')
        AS negative_number;
~~~

`D` và `G` dùng ký hiệu thập phân/phân nhóm theo locale; kết quả phụ thuộc thiết lập PostgreSQL. Nếu xuất dữ liệu giữa nhiều quốc gia, cần thống nhất **locale và contract định dạng**, không chỉ chọn template theo thói quen.

### 5.2. Không lưu TO_CHAR vào cột numeric

Không nên thiết kế bảng tiền:

~~~sql
amount_display text
~~~

làm **nguồn dữ liệu số tiền duy nhất** nếu ứng dụng cần tính toán. Chuỗi chứa dấu phân nhóm có thể khó parse, dễ phụ thuộc locale và dễ sắp xếp sai.

Hãy lưu `amount numeric`, còn việc hiển thị `amount_display` nên được tạo tại query hoặc tầng presentation phù hợp.

### 5.3. To_char làm mất thông tin kiểu

~~~sql
SELECT
    pg_typeof(amount) AS stored_type,
    pg_typeof(to_char(amount, 'FM9999990.00')) AS display_type
FROM expr_lab.orders
WHERE order_id = 1001;
~~~

Kết quả biểu thức định dạng là `text`. Muốn tiếp tục cộng, so sánh tiền, dùng `amount` gốc thay vì chuỗi đã format.

## 6. TO_NUMBER: đọc số từ chuỗi có mẫu

PostgreSQL có `to_number(text, template)` để chuyển văn bản có định dạng thành `numeric`:

~~~sql
SELECT
    to_number('1,250.50', '9,999.99') AS parsed_amount;
~~~

Khi dùng `to_number` phải hiểu template ứng với **cách dữ liệu được biểu diễn**. Mẫu có dấu phân nhóm, dấu thập phân, dấu âm hoặc locale khác nhau sẽ cần quy ước riêng.

### Khác nhau giữa ::numeric và to_number

~~~sql
SELECT '1250.50'::numeric AS simple_cast;
~~~

phù hợp với chuỗi decimal chuẩn không có ký tự định dạng bổ sung.

Trong khi đó:

~~~sql
SELECT to_number('1,250.50', '9,999.99') AS formatted_input;
~~~

xử lý chuỗi có dấu phân nhóm theo template.

**Cảnh báo:** `to_number` là parser theo mẫu, không phải một bộ xác thực nghiệp vụ tuyệt đối cho mọi input. Với CSV từ nhiều locale, dấu phẩy có thể là phân nhóm ở nơi này nhưng là dấu thập phân ở nơi khác. Chọn và xác thực format nguồn trước khi chuyển; không tự đoán locale từ một giá trị.

## 7. Định dạng ngày/giờ với TO_CHAR

Một thời điểm `timestamptz` nên được lưu dưới dạng thời điểm, không phải chuỗi `dd/mm/yyyy`. Khi cần báo cáo theo giờ địa phương, định dạng tường minh:

~~~sql
SELECT
    order_id,
    ordered_at,
    to_char(
        ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh',
        'DD/MM/YYYY HH24:MI:SS'
    ) AS order_time_vietnam
FROM expr_lab.orders
WHERE order_id = 1001;
~~~

Ví dụ, đơn 1001 hiển thị `10/01/2026 10:15:00` theo múi giờ `Asia/Ho_Chi_Minh`.

### 7.1. Các mẫu ngày/giờ phổ biến

| Mẫu | Ý nghĩa |
| --- | --- |
| `YYYY` | Năm bốn chữ số |
| `MM` | Tháng bằng số |
| `DD` | Ngày trong tháng |
| `HH24` | Giờ 24 giờ |
| `MI` | Phút |
| `SS` | Giây |
| `MS` | Mili giây theo template |
| `Mon` / `Month` | Tên tháng viết tắt/đầy đủ |
| `Dy` / `Day` | Tên thứ trong tuần |
| `FM` | Giảm khoảng đệm theo mẫu |

Ví dụ:

~~~sql
SELECT
    to_char(
        DATE '2026-02-10',
        'YYYY-MM-DD'
    ) AS iso_like_date,
    to_char(
        DATE '2026-02-10',
        'DD/MM/YYYY'
    ) AS vietnam_date,
    to_char(
        TIMESTAMP '2026-02-10 12:10:05',
        'HH24:MI:SS'
    ) AS time_only;
~~~

### 7.2. Chú ý tên tháng và lc_time

Tên tháng hoặc tên ngày có thể thay đổi theo locale/thiết lập thời gian và cách format. Nếu xây API cần ổn định giữa môi trường, nên trả kiểu thời gian/chuỗi ISO 8601 có múi giờ rõ ràng hoặc định nghĩa contract định dạng, thay vì phụ thuộc vào cách PostgreSQL dịch tên tháng.

### 7.3. TO_CHAR không làm đổi giá trị cột

~~~sql
SELECT
    pg_typeof(ordered_at),
    pg_typeof(
        to_char(ordered_at, 'YYYY-MM-DD HH24:MI')
    )
FROM expr_lab.orders
WHERE order_id = 1001;
~~~

`to_char` trả về `text`. Nó không chuyển cột `ordered_at` thành `timestamp` hoặc thay đổi múi giờ lưu trữ.

## 8. TO_DATE, TO_TIMESTAMP và chuyển đổi chuỗi thành thời gian

PostgreSQL có nhiều cách chuyển chuỗi thời gian:

~~~sql
SELECT
    '2026-02-10'::date AS cast_date,
    to_date('10/02/2026', 'DD/MM/YYYY') AS parsed_date,
    to_timestamp(
        '2026-02-10 12:10:05',
        'YYYY-MM-DD HH24:MI:SS'
    ) AS parsed_timestamp;
~~~

### 8.1. Phân biệt ba kết quả

| Biểu thức | Kiểu kết quả |
| --- | --- |
| `'2026-02-10'::date` | `date` |
| `to_date(text, template)` | `date` |
| `to_timestamp(text, template)` | `timestamp with time zone` / `timestamptz` |

Với `to_timestamp(text, template)`, nếu văn bản đầu vào không mang thông tin múi giờ rõ ràng, PostgreSQL diễn giải theo môi trường/session tương ứng. **Cần thống nhất múi giờ nguồn**, nhất là khi dịch vụ nhiều nơi gửi thời gian.

### 8.2. TO_TIMESTAMP một số epoch là dạng khác

~~~sql
SELECT to_timestamp(1700000000::double precision)
       AS timestamp_from_epoch_seconds;
~~~

Đây là overload nhận **số giây từ Unix epoch**, không phải parser text+template. Không nhầm:

~~~sql
to_timestamp(double precision)
~~~

với:

~~~sql
to_timestamp(text, text)
~~~

Khi dữ liệu epoch đến theo **mili giây**, cần đổi về giây theo chính sách đầu vào; không được truyền thẳng milliseconds rồi mong ra thời điểm đúng.

### 8.3. Parser có thể linh hoạt hơn định dạng nguồn nghiêm ngặt

`to_date`/`to_timestamp` sử dụng các mẫu parsing và có những quy tắc tiếp nhận văn bản; không nên dựa vào chúng như **toàn bộ hệ thống xác thực** chuỗi ngày của người dùng. Nếu yêu cầu chuỗi phải đúng tuyệt đối `DD/MM/YYYY`, cần kiểm tra độ dài/ký tự/miền ngày và đối chiếu kết quả nếu cần.

Nếu dữ liệu đã theo ISO 8601 và kiểu đích rõ ràng, phép cast:

~~~sql
SELECT '2026-02-10'::date;
~~~

thường đơn giản hơn một parser template phức tạp.

## 9. TIMESTAMP, TIMESTAMPTZ và AT TIME ZONE

Một nhầm lẫn lớn trong phân tích dữ liệu là coi mọi biểu thức thời gian như nhau.

- `timestamp without time zone` biểu diễn **ngày giờ dạng lịch**, không tự mang múi giờ/offset.
- `timestamptz` biểu diễn một **thời điểm tuyệt đối**; PostgreSQL hiển thị giá trị theo múi giờ của session hoặc biểu thức chuyển đổi.
- `AT TIME ZONE` có hai cách dùng với **kiểu kết quả khác nhau** tùy đầu vào.

### 9.1. Từ thời điểm tuyệt đối sang giờ địa phương

~~~sql
SELECT
    ordered_at,
    ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS local_wall_clock,
    pg_typeof(
        ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    ) AS local_type
FROM expr_lab.orders
WHERE order_id = 1001;
~~~

Nếu `ordered_at` có kiểu `timestamptz`, kết quả `AT TIME ZONE 'Asia/Ho_Chi_Minh'` là một **timestamp without time zone** thể hiện đồng hồ địa phương.

### 9.2. Từ đồng hồ địa phương sang một thời điểm

~~~sql
SELECT
    TIMESTAMP '2026-02-10 12:10:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
        AS exact_instant;
~~~

Ở chiều này, PostgreSQL diễn giải thời gian “12:10 tại Việt Nam” và trả **timestamptz**.

| Đầu vào | `AT TIME ZONE 'Asia/Ho_Chi_Minh'` trả |
| --- | --- |
| `timestamptz` | `timestamp without time zone` |
| `timestamp without time zone` | `timestamptz` |

Đối với vùng có daylight-saving time, thời điểm địa phương có thể **mơ hồ hoặc không tồn tại** ở một số ngày đổi giờ. Việt Nam hiện không đổi DST, nhưng hệ thống toàn cầu vẫn phải xem timezone theo tên vùng và chính sách lịch sử.

### 9.3. DATE_TRUNC theo tháng tại múi giờ nghiệp vụ

~~~sql
SELECT
    date_trunc(
        'month',
        ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date AS vietnam_month,
    COUNT(*) AS n_orders
FROM expr_lab.orders
GROUP BY vietnam_month
ORDER BY vietnam_month;
~~~

Lưu ý tháng ở Việt Nam có thể khác tháng UTC đối với các sự kiện gần nửa đêm. Nếu cần báo cáo thống nhất theo ngày nghiệp vụ, định nghĩa múi giờ **trước khi nhóm**.

## 10. EXTRACT, DATE_TRUNC và phép toán thời gian

Ba cách xử lý thời gian có mục đích khác nhau:

~~~sql
SELECT
    order_id,
    EXTRACT(YEAR FROM ordered_at) AS order_year,
    EXTRACT(MONTH FROM ordered_at) AS order_month,
    date_trunc('day', ordered_at) AS day_boundary,
    ordered_at::date AS session_date
FROM expr_lab.orders
ORDER BY order_id;
~~~

**Cảnh báo:** với `timestamptz`, `EXTRACT(MONTH ...)`, `date_trunc('day', ...)` và `::date` có thể phụ thuộc múi giờ session. Nếu báo cáo theo vùng giờ cụ thể, chuyển sang `AT TIME ZONE` trước khi tách năm/tháng/ngày.

### 10.1. Nhóm theo ngày địa phương

~~~sql
SELECT
    (ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
        AS order_day,
    COUNT(*) AS order_count
FROM expr_lab.orders
GROUP BY order_day
ORDER BY order_day;
~~~

### 10.2. Tính khoảng thời gian thực

~~~sql
SELECT
    o.order_id,
    o.ordered_at,
    c.signup_at,
    o.ordered_at - c.signup_at AS time_since_signup,
    EXTRACT(EPOCH FROM (o.ordered_at - c.signup_at))
        AS seconds_since_signup
FROM expr_lab.orders AS o
JOIN expr_lab.customers AS c
    ON c.customer_id = o.customer_id
ORDER BY o.order_id;
~~~

Phép trừ hai `timestamptz` cho **interval**. `EXTRACT(EPOCH FROM interval)` có thể đổi khoảng thời gian sang số giây theo ý nghĩa của interval.

### 10.3. AGE không phải luôn là số giây chia cho 86400

~~~sql
SELECT age(
    TIMESTAMP '2026-03-01',
    TIMESTAMP '2026-01-31'
) AS symbolic_age;
~~~

`age` trả khoảng thời gian **có thành phần năm/tháng/ngày mang tính lịch**, hữu ích cho một số câu hỏi độ tuổi. Nếu cần duration chính xác giữa hai thời điểm, dùng phép trừ timestamp/timestamptz và chuyển `interval` sang đơn vị phù hợp.

### 10.4. Tạo trục ngày cho báo cáo

~~~sql
SELECT day_value::date AS report_day
FROM generate_series(
    DATE '2026-02-01'::timestamp,
    DATE '2026-02-07'::timestamp,
    INTERVAL '1 day'
) AS g(day_value)
ORDER BY report_day;
~~~

`generate_series` trả bảy ngày. Kết hợp `LEFT JOIN` với aggregate có thể giúp báo cáo **hiển thị cả những ngày không có đơn**, thay vì chỉ các ngày xuất hiện trong dữ liệu.

## 11. Hàm chuỗi phục vụ làm sạch và hiển thị

Dữ liệu nhập có thể khác nhau về chữ hoa/thường, dấu cách và cách nối tên.

~~~sql
SELECT
    full_name,
    upper(full_name) AS upper_name,
    lower(email) AS lowercase_email,
    initcap(lower(full_name)) AS title_like_name,
    length(full_name) AS chars_in_name,
    octet_length(full_name) AS bytes_in_name
FROM expr_lab.customers
ORDER BY customer_id;
~~~

### 11.1. LOWER và UPPER

`lower`/`upper` chuyển chữ theo quy tắc collation/locale đang áp dụng. Chúng hữu ích cho tìm kiếm hoặc chuẩn hóa hiển thị, nhưng **không tự giải quyết đầy đủ** mọi quy tắc Unicode, địa chỉ email hoặc tên người trên toàn thế giới.

Nếu nghiệp vụ coi email không phân biệt hoa/thường, cần chính sách nhất quán giữa:

- cách nhận và chuẩn hóa input;
- cách so sánh;
- unique constraint/index;
- API và các trường hợp di chuyển dữ liệu.

### 11.2. BTRIM, LTRIM, RTRIM

~~~sql
SELECT
    btrim('  AB  ') AS trim_both,
    ltrim('  AB  ') AS trim_left,
    rtrim('  AB  ') AS trim_right,
    btrim('---AB---', '-') AS trim_specific_chars;
~~~

`btrim(text, characters)` loại những ký tự thuộc tập được chỉ định ở **hai đầu chuỗi**, không xóa toàn bộ chúng ở giữa.

### 11.3. REPLACE và REGEXP_REPLACE

~~~sql
SELECT
    replace('ORD_2026_001', '_', '-') AS replaced,
    regexp_replace(
        '  hello   world  ',
        '[[:space:]]+',
        ' ',
        'g'
    ) AS condensed_whitespace;
~~~

`replace` thay chuỗi con cố định, còn `regexp_replace` xử lý mẫu regular expression. Cờ `g` yêu cầu thay thế toàn bộ các lần khớp; không có cờ thích hợp có thể chỉ xử lý một lần khớp theo hành vi của hàm.

### 11.4. SPLIT_PART và SUBSTRING

~~~sql
SELECT
    split_part('region/store/123', '/', 2) AS part_two,
    substring('ABC-2026-001' FROM 5 FOR 4) AS year_part,
    left('ABC-2026-001', 3) AS prefix,
    right('ABC-2026-001', 3) AS suffix;
~~~

`split_part` lấy một phần của chuỗi theo delimiter với vị trí **bắt đầu từ 1**. Hãy kiểm tra dữ liệu thiếu delimiter hoặc có cấu trúc biến đổi trước khi sử dụng kết quả như một mã nghiệp vụ.

### 11.5. LENGTH và OCTET_LENGTH

`length(text)` đếm số ký tự theo cách PostgreSQL xử lý chuỗi text, còn `octet_length(text)` đếm số byte. Với ký tự Unicode nhiều byte trong UTF-8, hai số có thể khác nhau.

Điều này quan trọng khi API hoặc hệ thống ngoài giới hạn dữ liệu theo **byte** thay vì số ký tự.

## 12. Nối chuỗi: ||, CONCAT, CONCAT_WS và FORMAT

Những cách nối chuỗi có **ngữ nghĩa `NULL` khác nhau**.

~~~sql
SELECT
    'A' || 'B' AS operator_concat,
    concat('A', NULL, 'B') AS function_concat,
    concat_ws(' - ', 'A', NULL, 'B') AS with_separator;
~~~

Kết quả:

| Biểu thức | Kết quả |
| --- | --- |
| `'A' || 'B'` | `AB` |
| `concat('A', NULL, 'B')` | `AB` |
| `concat_ws(' - ', 'A', NULL, 'B')` | `A - B` |

Toán tử `||` với một toán hạng `NULL` thường trả `NULL`:

~~~sql
SELECT 'A' || NULL::text AS concatenated;
~~~

Trong khi đó, `concat` bỏ qua những đối số null theo ngữ nghĩa của hàm. `concat_ws(separator,...)` bỏ qua giá trị null và chỉ đặt dấu phân cách giữa các phần còn lại.

### Ví dụ hiển thị mã khách

~~~sql
SELECT
    customer_id,
    concat_ws(
        ' | ',
        full_name,
        lower(email)
    ) AS customer_label
FROM expr_lab.customers
ORDER BY customer_id;
~~~

Nếu cần một chuỗi mã cố định:

~~~sql
SELECT
    customer_id,
    'CUST-' || lpad(customer_id::text, 6, '0')
        AS customer_code
FROM expr_lab.customers
ORDER BY customer_id;
~~~

Với `customer_id = 1`, `lpad` tạo `000001` và mã hiển thị là `CUST-000001`. **Đây chỉ là biểu diễn của ID**, không phải một khóa thay thế có bảo đảm duy nhất hoặc ổn định nếu quy tắc nghiệp vụ chưa quy định.

## 13. FORMAT: tạo chuỗi theo placeholder

Hàm `format(formatstr, ...)` trong PostgreSQL nhận các placeholder:

- `%s`: đưa đối số thành chuỗi (null có thể được thể hiện như chuỗi rỗng theo quy tắc hàm).
- `%I`: biểu diễn đối số như **SQL identifier** đã được quote phù hợp.
- `%L`: biểu diễn đối số như **SQL literal** đã được quote phù hợp; null có thể được biểu diễn dưới dạng từ khóa `NULL`.
- `%%`: ký tự `%` tường minh.

Ví dụ:

~~~sql
SELECT
    format('Xin chào %s!', 'Lan') AS greeting,
    format('%s - %s', 'ORD-1001', 'paid') AS order_label,
    format('%I', 'Order Items') AS quoted_identifier,
    format('%L', 'O''Reilly') AS quoted_literal;
~~~

### 13.1. FORMAT với SQL động: phân biệt identifier và giá trị

~~~sql
SELECT format(
    'SELECT %I FROM %I.%I WHERE %I = %L',
    'status',
    'expr_lab',
    'orders',
    'order_id',
    1001
) AS generated_sql;
~~~

Kết quả là một **chuỗi chứa câu SQL**, không tự được thực thi. `%I` dùng cho tên cột/schema/bảng; `%L` dành cho literal.

**Không dùng `format('... %s ...', raw_user_input)` để ghép dữ liệu người dùng trực tiếp thành SQL thực thi.** Trong Java/JDBC, ưu tiên **prepared statement** và bind parameters cho giá trị. Khi SQL động thật sự cần tên đối tượng biến đổi, phải dùng cơ chế quote identifier phù hợp và giới hạn danh sách tên được phép.

### 13.2. FORMAT khác TO_CHAR

| Hàm | Vai trò |
| --- | --- |
| `to_char(numeric, template)` | Định dạng số theo mặt nạ |
| `to_char(date/timestamp, template)` | Định dạng thời gian theo mặt nạ |
| `format(text, ...)` | Ghép nhiều đối số thành chuỗi theo placeholder |
| `concat_ws(separator,...)` | Nối các phần với dấu ngăn cách |

Nếu cần `DD/MM/YYYY`, dùng `to_char`. Nếu cần chuỗi “Đơn 1001: paid”, `format` hoặc `concat_ws` thường thuận tiện.

## 14. Chuyển đổi JSONB sang giá trị có kiểu

`jsonb` cho phép một trường chứa cấu trúc JSON. Nhưng cần phân biệt:

~~~sql
metadata -> 'risk_score'
~~~

trả **JSONB**, còn:

~~~sql
metadata ->> 'risk_score'
~~~

trả **text** của giá trị JSON đã lấy.

Ví dụ:

~~~sql
SELECT
    order_id,
    metadata -> 'risk_score' AS score_as_jsonb,
    metadata ->> 'risk_score' AS score_as_text,
    (metadata ->> 'risk_score')::integer AS score_as_integer,
    pg_typeof(metadata -> 'risk_score') AS json_type,
    pg_typeof(metadata ->> 'risk_score') AS text_type
FROM expr_lab.orders
ORDER BY order_id;
~~~

Trong dữ liệu mẫu, `risk_score` có mặt ở một số đơn và thiếu ở những đơn khác. Khi key không tồn tại, toán tử lấy key trả SQL `NULL`; cast `NULL` sang integer vẫn là null. Nhưng nếu key có chuỗi `"not-a-number"`, ép sang integer sẽ gây lỗi.

### 14.1. Khi nào nên dùng -> và ->>?

| Nhu cầu | Toán tử/hàm |
| --- | --- |
| Giữ giá trị JSONB để xử lý JSON tiếp | `->` |
| Đọc trường như text | `->>` |
| Truy cập nested key, lấy JSONB | `#>` |
| Truy cập nested key, lấy text | `#>>` |
| Tạo JSONB từ giá trị SQL | `to_jsonb` |
| Tạo JSON object từ cặp khóa/giá trị | `jsonb_build_object` |

Ví dụ:

~~~sql
SELECT
    order_id,
    metadata ->> 'promo' AS promo_code,
    metadata #>> '{labels,0}' AS first_label
FROM expr_lab.orders
ORDER BY order_id;
~~~

`#>> '{labels,0}'` đi theo đường dẫn: key `labels`, phần tử mảng ở index **0**. JSON array bắt đầu từ 0 khi dùng đường dẫn JSON theo cú pháp này, khác với `WITH ORDINALITY` trên set-returning function (bắt đầu từ 1).

### 14.2. Tạo JSONB cho API

~~~sql
SELECT
    jsonb_build_object(
        'order_id', order_id,
        'status', status,
        'amount', amount,
        'placed_at', to_char(
            ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh',
            'YYYY-MM-DD HH24:MI:SS'
        )
    ) AS order_json
FROM expr_lab.orders
WHERE order_id = 1001;
~~~

Hàm này tạo một JSON object. `amount` được đưa vào JSON như giá trị số theo quy tắc chuyển đổi của PostgreSQL; `placed_at` là một **chuỗi đã format** do ta chủ động tạo.

Nếu API cần thời điểm có offset và khả năng diễn giải đa múi giờ, nên xác định contract thời gian rõ ràng thay vì gửi chuỗi không kèm múi giờ.

## 15. Tách JSONB array thành các hàng để phân tích

Ví dụ tìm các nhãn của từng đơn:

~~~sql
SELECT
    o.order_id,
    tag.value AS label
FROM expr_lab.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements_text(
        o.metadata -> 'labels'
    ) AS tag(value)
ORDER BY o.order_id, tag.value;
~~~

`jsonb_array_elements_text` chuyển các phần tử của một JSON array thành nhiều hàng text.

### 15.1. LEFT JOIN LATERAL giữ đơn có mảng rỗng

~~~sql
SELECT
    o.order_id,
    tag.value AS label
FROM expr_lab.orders AS o
LEFT JOIN LATERAL
    jsonb_array_elements_text(
        o.metadata -> 'labels'
    ) AS tag(value) ON TRUE
ORDER BY o.order_id, tag.value NULLS LAST;
~~~

Nếu mảng `labels` rỗng, `CROSS JOIN LATERAL` không tạo hàng cho đơn ấy, trong khi `LEFT JOIN LATERAL` giữ một hàng với `label = NULL`.

### 15.2. WITH ORDINALITY giữ vị trí phần tử

~~~sql
SELECT
    o.order_id,
    tag.position,
    tag.value AS label
FROM expr_lab.orders AS o
CROSS JOIN LATERAL
    jsonb_array_elements_text(
        o.metadata -> 'labels'
    ) WITH ORDINALITY AS tag(value, position)
ORDER BY o.order_id, tag.position;
~~~

`position` bắt đầu từ 1. Đây là cách đáng tin cậy để lưu thứ tự xuất hiện của nhãn trong array.

**Cẩn thận:** sau khi mở rộng hai nhãn của một đơn thành hai hàng, `SUM(o.amount)` trực tiếp trên tập hàng đã mở rộng có thể **cộng số tiền đơn ấy hai lần**. Khi cần tổng giá trị đơn, phải giữ đúng **độ chi tiết một hàng mỗi đơn** hoặc tổng hợp trước khi mở rộng nhãn.

## 16. Aggregate: phân tích số lượng, tổng và trung bình

Các hàm tổng hợp phổ biến:

~~~sql
SELECT
    COUNT(*) AS total_orders,
    SUM(amount) AS total_order_amount,
    AVG(amount) AS avg_order_amount,
    MIN(amount) AS minimum_amount,
    MAX(amount) AS maximum_amount
FROM expr_lab.orders;
~~~

Mỗi hàm trả về một chỉ số trên tập hàng được chọn. `COUNT(*)` đếm tất cả hàng; `COUNT(amount)` đếm giá trị `amount` không null. Vì bảng lab có `amount NOT NULL`, hai cách đếm bằng nhau, nhưng trong bảng thực tế có null thì không nhất thiết như vậy.

### 16.1. GROUP BY chia tập hàng thành nhóm

~~~sql
SELECT
    channel,
    COUNT(*) AS order_count,
    SUM(amount) AS total_amount
FROM expr_lab.orders
GROUP BY channel
ORDER BY channel;
~~~

Kết quả gồm một hàng cho mỗi giá trị `channel` xuất hiện trong bảng đơn, không phải mọi kênh có thể tồn tại trong nghiệp vụ.

### 16.2. FILTER: nhiều phép thống kê có điều kiện

~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders,
    COUNT(*) FILTER (
        WHERE status = 'refunded'
    ) AS refunded_orders,
    SUM(amount) FILTER (
        WHERE status = 'paid'
    ) AS paid_amount
FROM expr_lab.orders;
~~~

Kết quả:

| all_orders | paid_orders | refunded_orders | paid_amount |
| ---: | ---: | ---: | ---: |
| 9 | 6 | 1 | 870000.50 |

`FILTER (WHERE ...)` chỉ chọn những hàng đưa vào **hàm tổng hợp tương ứng**. `WHERE` ở cấp truy vấn thì loại hàng khỏi **toàn bộ** tập đầu vào của các phép tổng hợp.

### 16.3. SUM và AVG trên tập rỗng

~~~sql
SELECT
    COUNT(*) FILTER (
        WHERE status = 'not_a_real_status'
    ) AS n,
    SUM(amount) FILTER (
        WHERE status = 'not_a_real_status'
    ) AS s,
    AVG(amount) FILTER (
        WHERE status = 'not_a_real_status'
    ) AS a
FROM expr_lab.orders;
~~~

`COUNT` trả **0**, nhưng `SUM` và `AVG` trả **NULL** khi không có giá trị đầu vào. Có thể dùng `COALESCE(SUM(...), 0)` khi nghiệp vụ muốn hiển thị tổng bằng 0; với average không có mẫu, `NULL` thường có ý nghĩa hơn 0.

## 17. Tính tỷ lệ: tránh chia nguyên và mẫu số bằng 0

Tỷ lệ đơn paid:

~~~sql
SELECT
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders,
    COUNT(*) AS all_orders,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE status = 'paid')
        / NULLIF(COUNT(*), 0),
        2
    ) AS paid_rate_pct
FROM expr_lab.orders;
~~~

Với sáu đơn paid trên chín đơn, tỷ lệ là **66.67%** (làm tròn hai chữ số).

Hai chi tiết quan trọng:

1. Dùng `100.0` để tính theo số thập phân thay vì vô tình chia số nguyên trong biểu thức khác.
2. `NULLIF(COUNT(*), 0)` trả null khi mẫu số bằng 0, tránh lỗi chia cho 0.

### Tỷ lệ theo kênh

~~~sql
SELECT
    channel,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE status = 'paid')
        / NULLIF(COUNT(*), 0),
        2
    ) AS paid_rate_pct
FROM expr_lab.orders
GROUP BY channel
ORDER BY channel;
~~~

Đừng tính tỷ lệ tổng bằng trung bình không trọng số của tỷ lệ từng kênh khi các kênh có số đơn khác nhau. Mẫu số của **tỷ lệ toàn hệ thống** phải dựa trên tổng số đơn toàn hệ thống.

## 18. DATE_TRUNC kết hợp aggregate: báo cáo theo tháng

~~~sql
WITH monthly_orders AS (
    SELECT
        date_trunc(
            'month',
            ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date AS month_start,
        status,
        amount
    FROM expr_lab.orders
)
SELECT
    month_start,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders,
    COALESCE(
        SUM(amount) FILTER (
            WHERE status = 'paid'
        ),
        0::numeric
    ) AS paid_amount
FROM monthly_orders
GROUP BY month_start
ORDER BY month_start;
~~~

Kết quả dự kiến:

| month_start | all_orders | paid_orders | paid_amount |
| --- | ---: | ---: | ---: |
| 2026-01-01 | 4 | 3 | 465000.50 |
| 2026-02-01 | 5 | 3 | 405000.00 |

Thống kê theo tháng là ví dụ kết hợp **chuyển kiểu giờ địa phương**, **rút gọn thời gian** và **aggregate có điều kiện**. Mỗi bước có tác dụng rõ ràng; nếu bỏ `AT TIME ZONE`, mốc tháng có thể bị tính theo TimeZone của session.

### WHERE theo khoảng thời gian thay vì TO_CHAR trên cột

Nếu chỉ cần các đơn tháng 2 theo thời điểm tại Việt Nam, có thể viết điều kiện kiểu thời điểm:

~~~sql
SELECT COUNT(*)
FROM expr_lab.orders
WHERE ordered_at >= (
    TIMESTAMP '2026-02-01 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
AND ordered_at < (
    TIMESTAMP '2026-03-01 00:00:00'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
);
~~~

Cách này biểu diễn rõ **khoảng nửa mở [bắt đầu, kết thúc)** và cho planner cơ hội dùng một B-tree index trên `ordered_at`.

Ngược lại, điều kiện:

~~~sql
WHERE to_char(ordered_at, 'YYYY-MM') = '2026-02'
~~~

vừa phụ thuộc múi giờ/định dạng, vừa đặt hàm trên cột nên không tận dụng trực tiếp index thường trên `ordered_at` theo cùng cách. Khi lọc theo kỳ thời gian, ưu tiên ranh giới kiểu thời điểm.

## 19. Window functions: phân tích nhưng không làm mất từng hàng

Aggregate kèm `GROUP BY` tạo một hàng mỗi nhóm. Window function giúp **giữ từng dòng** mà vẫn gắn thông tin của nhóm.

### 19.1. ROW_NUMBER xếp thứ tự đơn của từng khách

~~~sql
SELECT
    customer_id,
    order_id,
    ordered_at,
    amount,
    ROW_NUMBER() OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at DESC, order_id DESC
    ) AS newest_first
FROM expr_lab.orders
ORDER BY customer_id, newest_first;
~~~

`PARTITION BY customer_id` chia các hàng thành nhóm khách, `ORDER BY` xếp đơn trong từng nhóm, `ROW_NUMBER` gán thứ tự 1, 2, 3...

Để lấy **đơn mới nhất mỗi khách**, dùng CTE:

~~~sql
WITH ranked AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM expr_lab.orders AS o
)
SELECT customer_id, order_id, ordered_at, amount
FROM ranked
WHERE rn = 1
ORDER BY customer_id;
~~~

PostgreSQL không cho sử dụng trực tiếp window function như điều kiện `WHERE ROW_NUMBER() ... = 1` cùng cấp truy vấn, vì window function được tính ở giai đoạn phù hợp sau `WHERE`. Dùng CTE/subquery là cách rõ ràng.

### 19.2. RANK và DENSE_RANK khác ROW_NUMBER

~~~sql
WITH scores(name, points) AS (
    VALUES
        ('A', 95),
        ('B', 90),
        ('C', 90),
        ('D', 80)
)
SELECT
    name,
    points,
    ROW_NUMBER() OVER (
        ORDER BY points DESC, name
    ) AS row_no,
    RANK() OVER (
        ORDER BY points DESC
    ) AS rank_no,
    DENSE_RANK() OVER (
        ORDER BY points DESC
    ) AS dense_rank_no
FROM scores
ORDER BY points DESC, name;
~~~

Kết quả:

| name | points | row_no | rank_no | dense_rank_no |
| --- | ---: | ---: | ---: | ---: |
| A | 95 | 1 | 1 | 1 |
| B | 90 | 2 | 2 | 2 |
| C | 90 | 3 | 2 | 2 |
| D | 80 | 4 | 4 | 3 |

`RANK` để khoảng trống thứ hạng khi có đồng hạng, còn `DENSE_RANK` không để khoảng trống. `ROW_NUMBER` đánh số **từng hàng**, nên nếu cần thứ tự ổn định giữa hai hàng đồng điểm, cần khóa phụ như `name` trong `ORDER BY` riêng của hàm.

## 20. LAG và LEAD: so sánh với hàng trước/sau

`LAG` và `LEAD` đọc giá trị ở hàng trước/sau theo thứ tự cửa sổ.

~~~sql
SELECT
    customer_id,
    order_id,
    ordered_at,
    amount,
    LAG(amount) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ) AS previous_amount,
    amount - LAG(amount) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ) AS change_from_previous
FROM expr_lab.orders
ORDER BY customer_id, ordered_at, order_id;
~~~

Đối với đơn đầu tiên của mỗi khách, không có hàng trước, nên `LAG(amount)` trả `NULL`; hiệu số cũng thành null. Có thể dùng `COALESCE` nếu nghiệp vụ muốn giả định “mức trước bằng 0”, nhưng nhiều báo cáo nên giữ null để biểu thị **chưa có giá trị so sánh**.

### LEAD để xem trạng thái tiếp theo

~~~sql
SELECT
    customer_id,
    order_id,
    status,
    LEAD(status) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ) AS next_order_status
FROM expr_lab.orders
ORDER BY customer_id, ordered_at, order_id;
~~~

`LEAD` ở đây so trạng thái **đơn kế tiếp trong lịch sử**, không phải lịch sử chuyển trạng thái **của cùng một đơn**. Nếu cần phân tích state transition của một order, phải có bảng log sự kiện thay đổi trạng thái theo thời gian.

## 21. Tổng lũy kế và trung bình trượt

### 21.1. Tổng paid lũy kế theo khách

~~~sql
SELECT
    customer_id,
    order_id,
    ordered_at,
    status,
    amount,
    COALESCE(
        SUM(amount) FILTER (
            WHERE status = 'paid'
        ) OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at, order_id
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND CURRENT ROW
        ),
        0::numeric
    ) AS running_paid_amount
FROM expr_lab.orders
ORDER BY customer_id, ordered_at, order_id;
~~~

`FILTER` cho phép chỉ **đơn paid** đóng góp vào tổng, trong khi các đơn pending/cancelled/refunded vẫn xuất hiện như những hàng kết quả.

Đối với Lan, tổng paid sau đơn 1001 là `125000.50`; sau đơn 1002 (pending) vẫn như cũ; sau đơn 1006 (paid) là `265000.50`.

### 21.2. Trung bình trượt ba đơn gần nhất

~~~sql
SELECT
    customer_id,
    order_id,
    ordered_at,
    amount,
    AVG(amount) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS avg_last_three_orders
FROM expr_lab.orders
ORDER BY customer_id, ordered_at, order_id;
~~~

Ý nghĩa: tại mỗi đơn, tính trung bình **tối đa ba hàng** gồm dòng hiện tại và hai dòng trước, trong phạm vi một khách hàng.

Đây là **moving average theo số dòng**, không phải trung bình trong **ba ngày**. Nếu muốn cửa sổ thời gian, cần xây dựng frame theo trục thời gian hoặc nhóm theo ngày rồi phân tích, tùy dữ liệu và phiên bản PostgreSQL.

### 21.3. LAST_VALUE và window frame

~~~sql
SELECT
    customer_id,
    order_id,
    amount,
    LAST_VALUE(amount) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
        ROWS BETWEEN UNBOUNDED PRECEDING
                 AND UNBOUNDED FOLLOWING
    ) AS last_amount_in_customer_history
FROM expr_lab.orders
ORDER BY customer_id, ordered_at, order_id;
~~~

Với `LAST_VALUE`, khung (*frame*) rất quan trọng. Nếu chỉ có `ORDER BY` mà không xác định frame, kết quả có thể là giá trị của **hàng hiện tại hoặc peer cuối trong frame mặc định**, chứ không phải đơn cuối cùng của **toàn partition**. Muốn giá trị cuối của cả nhóm theo thứ tự đã chọn, viết frame tới `UNBOUNDED FOLLOWING` như ví dụ.

## 22. Phân vị, median và độ phân tán

Ngoài trung bình, báo cáo thường cần **trung vị** (*median*), độ lệch chuẩn hoặc phân bố mức tiền.

### 22.1. Median với PERCENTILE_CONT

~~~sql
SELECT
    PERCENTILE_CONT(0.5)
        WITHIN GROUP (
            ORDER BY amount::double precision
        ) AS median_paid_amount
FROM expr_lab.orders
WHERE status = 'paid';
~~~

Sáu giá trị paid theo thứ tự tăng:

~~~text
65000.00
90000.00
125000.50
140000.00
200000.00
250000.00
~~~

Với sáu phần tử, median liên tục là trung bình của phần tử thứ ba và thứ tư:

~~~text
(125000.50 + 140000.00) / 2 = 132500.25
~~~

`PERCENTILE_CONT(0.5)` là **ordered-set aggregate**, có thể nội suy giữa các giá trị. Với tham số `amount::double precision` ở ví dụ, kết quả là kiểu số thực tương ứng. Nếu yêu cầu chính xác decimal nghiêm ngặt cho nghiệp vụ tiền, cần lưu ý tính chất của phép nội suy và việc chuyển sang floating-point.

### 22.2. PERCENTILE_DISC: giá trị có trong tập

~~~sql
SELECT
    PERCENTILE_DISC(0.5)
        WITHIN GROUP (ORDER BY amount)
        AS discrete_median_paid_amount
FROM expr_lab.orders
WHERE status = 'paid';
~~~

`PERCENTILE_DISC` chọn một giá trị **có trong dữ liệu** theo quy tắc phân vị rời rạc, thay vì nội suy như `PERCENTILE_CONT`. Với sáu giá trị trên và phân vị 0.5, một kết quả theo quy tắc rời rạc là `125000.50`.

Không nên mặc định “median” trong mọi báo cáo luôn dùng cùng công thức khi số lượng phần tử chẵn; xác định rõ **continuous median** hay **discrete percentile** theo nghiệp vụ.

### 22.3. Độ lệch chuẩn

~~~sql
SELECT
    COUNT(*) AS n_paid,
    ROUND(AVG(amount), 2) AS mean_paid_amount,
    ROUND(STDDEV_SAMP(amount), 2) AS sample_stddev,
    ROUND(STDDEV_POP(amount), 2) AS population_stddev
FROM expr_lab.orders
WHERE status = 'paid';
~~~

- `STDDEV_SAMP` dùng công thức độ lệch chuẩn mẫu.
- `STDDEV_POP` dùng công thức độ lệch chuẩn tổng thể.
- Với quá ít quan sát, một số hàm thống kê mẫu có thể trả null do không đủ bậc tự do.

Phân tích dữ liệu cần xác định **tập đang xem là mẫu hay toàn bộ tổng thể**, và số liệu có bị ảnh hưởng bởi outlier hoặc việc lọc trạng thái hay không.

### 22.4. Z-score đơn giản

~~~sql
WITH paid_orders AS (
    SELECT order_id, amount
    FROM expr_lab.orders
    WHERE status = 'paid'
),
stats AS (
    SELECT
        AVG(amount) AS mean_amount,
        STDDEV_POP(amount) AS sd_amount
    FROM paid_orders
)
SELECT
    p.order_id,
    p.amount,
    ROUND(
        (p.amount - s.mean_amount)
        / NULLIF(s.sd_amount, 0),
        3
    ) AS z_score
FROM paid_orders AS p
CROSS JOIN stats AS s
ORDER BY p.order_id;
~~~

`Z-score` diễn đạt độ lệch khỏi trung bình theo số độ lệch chuẩn trong tập đã chọn. Nếu độ lệch chuẩn bằng 0 (tất cả giá trị giống nhau), mẫu số sẽ bằng 0; `NULLIF` giúp trả null thay vì lỗi. Không dùng z-score như nhãn gian lận/tài chính chỉ dựa vào một ngưỡng không được kiểm chứng.

## 23. Phân tích dữ liệu theo nhóm với ROLLUP và GROUPING

Báo cáo có thể cần vừa tổng theo kênh, vừa một hàng toàn hệ thống.

~~~sql
SELECT
    CASE
        WHEN GROUPING(channel) = 1 THEN 'ALL_CHANNELS'
        ELSE channel
    END AS channel_group,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (
        WHERE status = 'paid'
    ) AS paid_orders,
    COALESCE(
        SUM(amount) FILTER (
            WHERE status = 'paid'
        ),
        0::numeric
    ) AS paid_amount
FROM expr_lab.orders
GROUP BY ROLLUP (channel)
ORDER BY GROUPING(channel), channel_group;
~~~

`ROLLUP(channel)` tạo nhóm theo từng kênh và nhóm tổng. `GROUPING(channel)` phân biệt hàng tổng do `ROLLUP` tạo với một nhóm có `channel = NULL` thật nếu dữ liệu cho phép.

Những cấu trúc như `GROUPING SETS` và `CUBE` có thể tạo nhiều cấp thống kê; chỉ dùng khi định dạng kết quả phù hợp nhu cầu, vì số nhóm có thể tăng đáng kể.

### Tạo báo cáo “mỗi ngày kể cả không phát sinh đơn”

~~~sql
WITH days AS (
    SELECT day_value::date AS order_day
    FROM generate_series(
        TIMESTAMP '2026-02-08',
        TIMESTAMP '2026-02-12',
        INTERVAL '1 day'
    ) AS g(day_value)
),
orders_per_day AS (
    SELECT
        (ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
            AS order_day,
        COUNT(*) AS n_orders
    FROM expr_lab.orders
    GROUP BY 1
)
SELECT
    d.order_day,
    COALESCE(o.n_orders, 0) AS order_count
FROM days AS d
LEFT JOIN orders_per_day AS o USING (order_day)
ORDER BY d.order_day;
~~~

Vì có trục ngày `generate_series`, ngày không có đơn vẫn xuất hiện với `order_count = 0`. Nếu chỉ `GROUP BY order_day` trực tiếp trên bảng đơn hàng, những ngày không có hàng sẽ không được tự tạo.

## 24. Hiệu năng: hàm trên cột và khả năng dùng index

Một vấn đề thường gặp:

~~~sql
WHERE lower(email) = 'lan@example.test'
~~~

Nếu chỉ có index thường trên `email`, PostgreSQL không nhất thiết dùng index đó để đáp ứng biểu thức `lower(email)`.

### 24.1. Expression index

~~~sql
CREATE INDEX idx_customers_email_lower
ON expr_lab.customers (lower(email));
~~~

Sau đó truy vấn:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT customer_id, full_name
FROM expr_lab.customers
WHERE lower(email) = 'lan@example.test';
~~~

có thể được planner cân nhắc dùng expression index. Tuy nhiên, bảng lab chỉ có bốn khách, nên `Seq Scan` vẫn có thể là lựa chọn rẻ hơn; điều đó không có nghĩa index sai.

**Expression index không tự bảo đảm uniqueness** nếu tạo bằng `CREATE INDEX` thông thường. Nếu cần uniqueness không phân biệt hoa/thường, phải thiết kế **unique expression index** hoặc một cơ chế tương đương, xử lý dữ liệu trùng hiện có và thống nhất chính sách normalization/collation.

### 24.2. Ưu tiên khoảng thời gian khi lọc ngày

So sánh:

~~~sql
-- Có thể áp dụng hàm cho từng hàng và bỏ cơ hội
-- sử dụng trực tiếp một index thường trên ordered_at:
WHERE to_char(ordered_at, 'YYYY-MM') = '2026-02'
~~~

và:

~~~sql
-- Khoảng thời gian có kiểu rõ ràng:
WHERE ordered_at >= (
    TIMESTAMP '2026-02-01'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
AND ordered_at < (
    TIMESTAMP '2026-03-01'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
~~~

Với index:

~~~sql
CREATE INDEX idx_orders_ordered_at
ON expr_lab.orders (ordered_at);
~~~

planner có thể dùng index để truy cập khoảng thời gian. Giới hạn theo kiểu thời điểm cũng tránh phải so sánh chuỗi ngày đã format.

### 24.3. Không tạo index trước khi hiểu workload

Index có chi phí:

- Chiếm dung lượng đĩa và cache.
- `INSERT`, `UPDATE` và `DELETE` cần bảo trì những mục index liên quan.
- Index expression có thể cần tính hàm khi dữ liệu thay đổi.
- Một vài hàm phụ thuộc cấu hình session/locale không phù hợp yêu cầu immutable của expression index.

Hãy so sánh bằng `EXPLAIN (ANALYZE, BUFFERS)` trên dữ liệu đại diện và xem độ trễ/throughput toàn workload. Không tự khẳng định viết `to_char` trong `WHERE` “luôn chậm”; vấn đề là **cơ hội tối ưu, khả năng index và tính đúng ngữ nghĩa**.

## 25. Kiểm tra kiểu và debug biểu thức

Khi SQL phức tạp, lỗi có thể phát sinh do PostgreSQL suy ra kiểu không như mong muốn.

### 25.1. PG_TYPEOF

~~~sql
SELECT
    pg_typeof(1) AS integer_literal_type,
    pg_typeof(1.0) AS decimal_literal_type,
    pg_typeof('123'::text) AS cast_text_type,
    pg_typeof('2026-02-10'::date) AS date_type,
    pg_typeof(now()) AS now_type,
    pg_typeof(to_char(now(), 'YYYY-MM-DD')) AS formatted_type;
~~~

Đặc biệt với `CASE`, `COALESCE` hoặc `UNION`, PostgreSQL cần tìm **một kiểu kết quả chung** cho những nhánh/biểu thức phù hợp.

### 25.2. CASE cần các nhánh cùng kiểu tương thích

Đúng:

~~~sql
SELECT
    CASE
        WHEN status = 'paid' THEN amount
        ELSE 0::numeric
    END AS amount_if_paid
FROM expr_lab.orders;
~~~

Dễ lỗi:

~~~sql
-- Không nên trộn numeric với nhãn text làm kết quả cùng CASE:
SELECT
    CASE
        WHEN status = 'paid' THEN amount
        ELSE 'N/A'
    END
FROM expr_lab.orders;
~~~

Trong nhánh sai ý tưởng trên, PostgreSQL phải giải quyết kiểu của biểu thức; literal `'N/A'` không thể được chuyển thành numeric một cách hợp lệ.

Nếu mục tiêu là một **cột hiển thị dạng text**, hãy chủ động định dạng hai nhánh thành text:

~~~sql
SELECT
    CASE
        WHEN status = 'paid'
        THEN to_char(amount, 'FM999,999,990.00')
        ELSE 'N/A'
    END AS amount_display
FROM expr_lab.orders;
~~~

### 25.3. Hàm format không thay thế prepared statements

Khi giao tiếp với Java/JDBC, giá trị từ người dùng nên được bind bằng tham số:

~~~java
String sql = """
    SELECT order_id, amount
    FROM expr_lab.orders
    WHERE customer_id = ?
      AND ordered_at >= ?
      AND ordered_at < ?
    ORDER BY ordered_at
    """;
~~~

Ví dụ trên dùng Java text block (Java 15+), minh họa query có parameter placeholders. Hãy dùng `PreparedStatement` với giá trị/kiểu thời gian phù hợp thay vì ghép text đã format thành SQL. Trình bày giá trị ra màn hình và xây câu SQL an toàn là **hai công việc khác nhau**.

## 26. Những lỗi thường gặp

### Lỗi 1. Dùng text đã định dạng để sắp xếp số

~~~sql
ORDER BY to_char(amount, 'FM999,999,990.00')
~~~

sắp theo **text**, không nhất thiết theo số. Nếu cần sắp tiền từ nhỏ đến lớn, dùng `ORDER BY amount`, chỉ dùng `to_char` trong `SELECT` để hiển thị.

### Lỗi 2. Không phân biệt timestamp và timestamptz

Một chuỗi `'2026-02-10 12:10'` không cho biết múi giờ. Khi phân tích nhiều quốc gia, phải xác định dữ liệu là đồng hồ địa phương hay thời điểm tuyệt đối trước khi cast, format hoặc nhóm theo tháng.

### Lỗi 3. Lọc thời gian bằng chuỗi hiển thị

`WHERE to_char(ordered_at, 'YYYY-MM') = ...` dễ phụ thuộc múi giờ và có thể khó dùng index. Ưu tiên khoảng `timestamptz` đúng múi giờ nghiệp vụ.

### Lỗi 4. Cast trực tiếp dữ liệu nguồn không tin cậy

`'15x'::numeric` gây lỗi và có thể làm thất bại toàn bộ lệnh import. Kiểm tra/chuẩn hóa trước, ghi nhận dòng lỗi và không âm thầm mất dữ liệu.

### Lỗi 5. Cho rằng TO_NUMBER tự hiểu mọi locale

`'1,250.50'` và `'1.250,50'` có thể mang cùng giá trị số ở hai locale nhưng khác format. Cần biết định dạng nguồn và template/cấu hình tương ứng.

### Lỗi 6. Nghĩ CHECK định dạng tương đương CHECK nghiệp vụ

Regex nhận `'999999999999999999'` là dãy chữ số, nhưng có thể vượt phạm vi kiểu numeric đích hoặc trái giới hạn nghiệp vụ. Kiểm tra cả phạm vi, số chữ số và quy tắc sử dụng.

### Lỗi 7. Gộp NULL với 0

Không có số tiền hoặc không có dữ liệu để tính AVG khác với giá trị thật bằng 0. `COALESCE` phải dựa trên ý nghĩa nghiệp vụ.

### Lỗi 8. Dùng AVG(CASE WHEN ... ELSE 0) sai mẫu số

~~~sql
AVG(CASE WHEN status = 'paid' THEN amount ELSE 0 END)
~~~

chia trên mọi hàng, không phải chỉ hàng paid. Nếu cần trung bình **đơn paid**, dùng:

~~~sql
AVG(amount) FILTER (WHERE status = 'paid')
~~~

### Lỗi 9. Quên frame của LAST_VALUE

`LAST_VALUE` không mặc nhiên lấy hàng cuối toàn partition khi frame mặc định dừng tại hàng hiện tại/peer. Hãy khai báo frame phù hợp với câu hỏi.

### Lỗi 10. SUM sau JOIN một-nhiều hoặc mở rộng JSON

Một đơn có hai nhãn hoặc hai dòng sản phẩm có thể xuất hiện hai lần trong kết quả join, khiến `SUM(amount)` bị nhân đôi. Xác định **đơn vị thống kê** trước khi tổng hợp.

### Lỗi 11. Coi định dạng chuỗi là làm tròn số đã lưu

`to_char(amount, '...00')` chỉ thay cách biểu diễn. Nó không cập nhật cột `amount` hoặc làm mất những chữ số bên trong giá trị gốc.

### Lỗi 12. Tạo expression index theo hàm mà không đo plan

Không phải mọi hàm đều được dùng làm biểu thức index phù hợp, và ngay cả khi index hợp lệ, planner vẫn có thể chọn cách đọc khác trên tập dữ liệu nhỏ. Cần đánh giá query pattern, tính immutable và chi phí ghi.

## 27. Bài tập thực hành

Các bài sau dựa vào schema `expr_lab` và chín đơn hàng mẫu. Nên dự đoán kiểu kết quả và các trường hợp `NULL` trước khi chạy.

### Bài 1. Phân biệt giá trị và biểu diễn

Viết truy vấn trả `order_id`, `amount` gốc và cột `amount_display` có dấu phân nhóm và hai chữ số thập phân. Vì sao không nên `ORDER BY amount_display` khi muốn sắp theo giá tiền?

### Bài 2. CAST và độ chính xác

So sánh kết quả:

~~~sql
123.456::numeric(10, 2)
trunc(123.456::numeric, 2)
round(123.456::numeric, 2)
~~~

Nhận xét sự khác nhau giữa cast theo scale và cắt phần thập phân.

### Bài 3. Làm sạch số từ text

Cho các chuỗi `' 1200.50 '`, `''`, `'N/A'` và `'12x'`. Dùng `btrim`, `nullif`, `CASE` và regular expression để chỉ cast những chuỗi decimal đơn giản hợp lệ.

### Bài 4. TO_DATE

Viết biểu thức chuyển `'10/02/2026'` thành kiểu `date` và biểu thức format kết quả ra `'2026-02-10'`.

### Bài 5. Múi giờ

Với `ordered_at timestamptz`, viết biểu thức hiển thị `DD/MM/YYYY HH24:MI` theo `Asia/Ho_Chi_Minh` và biểu thức nhóm đơn theo tháng địa phương.

### Bài 6. TO_TIMESTAMP

Phân biệt `to_timestamp('2026-02-10 12:10:05', 'YYYY-MM-DD HH24:MI:SS')` với `to_timestamp(1700000000::double precision)`.

### Bài 7. String functions

Viết biểu thức chuyển email về chữ thường, bỏ khoảng trắng hai đầu một chuỗi, và tạo mã khách `CUST-000001` từ `customer_id = 1`.

### Bài 8. JSONB type conversion

Trả `risk_score` dưới dạng integer từ `metadata`. Nếu key không tồn tại, biểu thức dự kiến trả gì? Nếu key chứa văn bản không phải số, điều gì xảy ra?

### Bài 9. Thống kê paid

Tính tổng đơn, số đơn paid, tổng `amount` của đơn paid và tỷ lệ paid trên tổng đơn. Dự đoán các kết quả dựa trên chín đơn mẫu.

### Bài 10. Nhóm theo tháng

Trả một hàng mỗi tháng theo giờ Việt Nam: tháng, tổng đơn, đơn paid và tổng giá trị đơn paid. Kiểm tra kết quả tháng 1 và tháng 2.

### Bài 11. ROW_NUMBER

Với mỗi khách có đơn, lấy đơn mới nhất bằng `ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY ordered_at DESC, order_id DESC)`.

### Bài 12. LAG

Tính `previous_amount` và hiệu số giữa `amount` hiện tại với đơn trước của cùng khách. Vì sao đơn đầu của mỗi khách cho hiệu số null?

### Bài 13. RANK và DENSE_RANK

Với điểm `95,90,90,80`, giải thích sự khác nhau giữa `RANK` và `DENSE_RANK`.

### Bài 14. Median

Tính median liên tục cho những đơn paid bằng `PERCENTILE_CONT(0.5) WITHIN GROUP`. Median là bao nhiêu?

### Bài 15. Độ lệch chuẩn

Viết truy vấn tính `AVG`, `STDDEV_SAMP`, `STDDEV_POP` cho `amount` của đơn paid. Khi nào thống kê mẫu có thể trả null?

### Bài 16. Window frame

Viết tổng tiền paid lũy kế theo từng khách với frame `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`. Những đơn không paid có được giữ trong kết quả không?

### Bài 17. Dữ liệu JSON array

Tách `metadata.labels` thành nhiều hàng cùng `order_id`. Làm sao giữ vị trí phần tử và làm sao giữ cả đơn có array rỗng?

### Bài 18. FORMAT và SQL động

Phân biệt placeholder `%s`, `%I` và `%L`. Vì sao không nối nguyên văn input người dùng vào SQL động bằng `%s`?

### Bài 19. Query performance

Chọn cách lọc những đơn tháng 2 theo múi giờ Việt Nam sao cho PostgreSQL có thể cân nhắc B-tree index thông thường trên `ordered_at`. Vì sao nên tránh lọc bằng `to_char(ordered_at, 'YYYY-MM')`?

### Bài 20. Khi tập thống kê rỗng

`COUNT(*)`, `SUM(amount)` và `AVG(amount)` có kết quả gì khi không có hàng thỏa điều kiện? Có nên thay mọi giá trị null bằng 0 không?

## 28. Lời giải và gợi ý

### Bài 1. Số và chuỗi hiển thị

~~~sql
SELECT
    order_id,
    amount,
    to_char(amount, 'FM999,999,990.00') AS amount_display
FROM expr_lab.orders
ORDER BY amount;
~~~

`ORDER BY amount` dùng giá trị `numeric`; `amount_display` có kiểu `text` và không bảo đảm thứ tự số đúng.

### Bài 2. Cast, TRUNC, ROUND

`123.456::numeric(10,2) = 123.46`; `trunc(...,2) = 123.45`; `round(...,2) = 123.46`. Cast theo scale có thể làm tròn, còn `trunc` cắt phần thập phân.

### Bài 3. Chuẩn hóa input

~~~sql
WITH inputs(raw) AS (
    VALUES
        (' 1200.50 '::text),
        (''::text),
        ('N/A'::text),
        ('12x'::text)
)
SELECT
    raw,
    CASE
        WHEN btrim(raw) ~ '^[0-9]+([.][0-9]{1,2})?$'
        THEN btrim(raw)::numeric(12,2)
        ELSE NULL
    END AS amount
FROM inputs;
~~~

Chuỗi `' 1200.50 '` được đổi thành số `1200.50`; ba chuỗi còn lại cho null trong công thức minh họa.

### Bài 4. Ngày có định dạng

~~~sql
SELECT
    to_date('10/02/2026', 'DD/MM/YYYY') AS parsed_date,
    to_char(
        to_date('10/02/2026', 'DD/MM/YYYY'),
        'YYYY-MM-DD'
    ) AS formatted_date;
~~~

### Bài 5. Chuyển múi giờ

~~~sql
SELECT
    order_id,
    to_char(
        ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh',
        'DD/MM/YYYY HH24:MI'
    ) AS local_time,
    date_trunc(
        'month',
        ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date AS local_month
FROM expr_lab.orders;
~~~

### Bài 6. Hai overload của TO_TIMESTAMP

Hàm nhận `text, text` đọc timestamp theo template; hàm nhận `double precision` nhận số giây từ Unix epoch. Cần chú ý TimeZone của quá trình parsing khi chuỗi không mang offset.

### Bài 7. String helpers

~~~sql
SELECT
    lower('Lan@Example.test') AS email_lower,
    btrim('   hello   ') AS trimmed,
    'CUST-' || lpad(1::text, 6, '0') AS customer_code;
~~~

### Bài 8. JSONB sang integer

~~~sql
SELECT
    order_id,
    (metadata ->> 'risk_score')::integer AS risk_score
FROM expr_lab.orders;
~~~

Thiếu key trả null. Giá trị text sai kiểu số có thể gây lỗi; với dữ liệu nguồn không tin cậy cần kiểm tra trước khi cast.

### Bài 9. Paid summary

~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders,
    SUM(amount) FILTER (WHERE status = 'paid') AS paid_amount,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE status = 'paid')
        / NULLIF(COUNT(*), 0),
        2
    ) AS paid_rate_pct
FROM expr_lab.orders;
~~~

Kết quả: **9, 6, 870000.50, 66.67**.

### Bài 10. Monthly paid

~~~sql
WITH src AS (
    SELECT
        date_trunc(
            'month',
            ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
        )::date AS month_start,
        status,
        amount
    FROM expr_lab.orders
)
SELECT
    month_start,
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE status = 'paid') AS paid_orders,
    SUM(amount) FILTER (WHERE status = 'paid') AS paid_amount
FROM src
GROUP BY month_start
ORDER BY month_start;
~~~

Tháng 1: **4 đơn, 3 paid, 465000.50**. Tháng 2: **5 đơn, 3 paid, 405000.00**.

### Bài 11. Latest order

~~~sql
WITH ranked AS (
    SELECT
        order_id, customer_id, ordered_at, status,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at DESC, order_id DESC
        ) AS rn
    FROM expr_lab.orders
)
SELECT customer_id, order_id, status
FROM ranked
WHERE rn = 1
ORDER BY customer_id;
~~~

Trả đơn mới nhất của Lan, Minh và An. Khách Chi không có đơn nên không có hàng ở nguồn `orders`.

### Bài 12. LAG

~~~sql
SELECT
    customer_id,
    order_id,
    amount,
    LAG(amount) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ) AS previous_amount,
    amount - LAG(amount) OVER (
        PARTITION BY customer_id
        ORDER BY ordered_at, order_id
    ) AS amount_delta
FROM expr_lab.orders
ORDER BY customer_id, ordered_at, order_id;
~~~

Hàng đầu mỗi partition không có hàng trước để so sánh.

### Bài 13. Ranking

`RANK` trả thứ hạng `1,2,2,4`; `DENSE_RANK` trả `1,2,2,3`. `ROW_NUMBER` trả số thứ tự từng dòng và cần khóa phá hòa để thứ tự ổn định.

### Bài 14. Median

~~~sql
SELECT
    PERCENTILE_CONT(0.5)
        WITHIN GROUP (ORDER BY amount::double precision)
        AS median_paid
FROM expr_lab.orders
WHERE status = 'paid';
~~~

Kết quả **132500.25**.

### Bài 15. Độ lệch chuẩn

~~~sql
SELECT
    AVG(amount) AS avg_amount,
    STDDEV_SAMP(amount) AS sample_sd,
    STDDEV_POP(amount) AS population_sd
FROM expr_lab.orders
WHERE status = 'paid';
~~~

Thống kê mẫu như `STDDEV_SAMP` cần đủ quan sát để tính phương sai mẫu; với một giá trị không null, độ lệch chuẩn mẫu không được xác định nên trả null.

### Bài 16. Tổng lũy kế

~~~sql
SELECT
    customer_id, order_id, status, amount,
    COALESCE(
        SUM(amount) FILTER (
            WHERE status = 'paid'
        ) OVER (
            PARTITION BY customer_id
            ORDER BY ordered_at, order_id
            ROWS BETWEEN UNBOUNDED PRECEDING
                     AND CURRENT ROW
        ),
        0::numeric
    ) AS running_paid_amount
FROM expr_lab.orders
ORDER BY customer_id, ordered_at, order_id;
~~~

Hàng không paid **vẫn xuất hiện**, nhưng không đóng góp `amount` vào tổng.

### Bài 17. JSONB labels

~~~sql
SELECT
    o.order_id,
    tag.position,
    tag.label
FROM expr_lab.orders AS o
LEFT JOIN LATERAL
    jsonb_array_elements_text(
        o.metadata -> 'labels'
    ) WITH ORDINALITY AS tag(label, position)
    ON TRUE
ORDER BY o.order_id, tag.position NULLS LAST;
~~~

`LEFT JOIN LATERAL` giữ hàng có array rỗng; `WITH ORDINALITY` ghi vị trí bắt đầu từ 1.

### Bài 18. FORMAT

`%s` trình bày đối số dưới dạng chuỗi, `%I` quote tên đối tượng SQL, `%L` quote literal SQL. Trong ứng dụng nên bind giá trị qua prepared statement; `%s` không có chức năng bảo vệ SQL động khỏi input nguy hiểm.

### Bài 19. Khoảng thời gian

~~~sql
SELECT order_id, ordered_at
FROM expr_lab.orders
WHERE ordered_at >= (
    TIMESTAMP '2026-02-01'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
)
AND ordered_at < (
    TIMESTAMP '2026-03-01'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
);
~~~

Khoảng kiểu `timestamptz` phản ánh đúng mốc tháng ở Việt Nam và cho planner cơ hội dùng index trên cột gốc. `to_char` tạo text và có thể làm việc so sánh, tối ưu phức tạp hơn.

### Bài 20. Nhóm rỗng

`COUNT(*) = 0`, `SUM(amount) = NULL`, `AVG(amount) = NULL`. `COALESCE` thích hợp khi quy tắc hiển thị muốn tổng 0, nhưng average chưa có dữ liệu nên thường nên giữ null hoặc hiển thị “N/A”.

## 29. Bảng tra cứu nhanh

| Mục tiêu | Công cụ |
| --- | --- |
| Ép kiểu SQL chuẩn | `CAST(x AS type)` |
| Ép kiểu PostgreSQL | `x::type` |
| Xem kiểu biểu thức | `pg_typeof(x)` |
| Format số theo mẫu | `to_char(number, template)` |
| Format ngày giờ | `to_char(timestamp, template)` |
| Parse ngày | `to_date(text, template)` |
| Parse timestamp theo mẫu | `to_timestamp(text, template)` |
| Epoch seconds sang thời điểm | `to_timestamp(double precision)` |
| Parse số theo mẫu | `to_number(text, template)` |
| Nối text và bỏ null theo quy tắc | `concat`, `concat_ws` |
| Tạo chuỗi có placeholder | `format('%s %I %L', ...)` |
| Bỏ khoảng trắng | `btrim`, `ltrim`, `rtrim` |
| Chuẩn hóa chữ hoa/thường | `lower`, `upper` |
| Thay mẫu regex | `regexp_replace` |
| Tách chuỗi theo delimiter | `split_part` |
| Đổi giờ theo múi giờ | `AT TIME ZONE` |
| Lấy thành phần thời gian | `extract` |
| Gom về mốc ngày/tháng | `date_trunc` |
| Tạo trục thời gian | `generate_series` |
| JSONB value sang text | `->>`, `#>>` |
| Tạo JSONB | `to_jsonb`, `jsonb_build_object` |
| Mở rộng JSON array | `jsonb_array_elements_text` |
| Thống kê theo nhóm | `GROUP BY` + `COUNT/SUM/AVG` |
| Tổng hợp có điều kiện | `FILTER (WHERE condition)` |
| Tỷ lệ có mẫu số an toàn | `NULLIF(denominator, 0)` |
| Xếp thứ tự theo nhóm | `ROW_NUMBER`, `RANK`, `DENSE_RANK` |
| Xem hàng trước/sau | `LAG`, `LEAD` |
| Tổng lũy kế/trung bình trượt | Aggregate `OVER (...) ROWS ...` |
| Trung vị/phân vị | `PERCENTILE_CONT`, `PERCENTILE_DISC` |
| Độ lệch chuẩn | `STDDEV_SAMP`, `STDDEV_POP` |
| Phân tích kế hoạch truy vấn | `EXPLAIN (ANALYZE, BUFFERS)` |

## 30. Checklist trước khi đưa truy vấn phân tích vào vận hành

| Câu hỏi | Vì sao cần trả lời? |
| --- | --- |
| Giá trị gốc đang có kiểu gì? | Tránh so sánh text với numeric/date sai nghĩa |
| Việc format chỉ nhằm hiển thị? | Tránh lưu số/ngày đã format làm nguồn chính |
| Dữ liệu import có thể sai không? | Tránh một cast thất bại làm hỏng cả pipeline |
| Locale và dấu thập phân đã được thống nhất? | Tránh parse sai tiền |
| Thời điểm là timestamp hay timestamptz? | Tránh nhầm múi giờ và ngày báo cáo |
| Giới hạn khoảng thời gian đã rõ [start,end)? | Tránh thiếu/đếm trùng sự kiện biên |
| NULL có ý nghĩa gì? | Phân biệt thiếu dữ liệu và giá trị 0 |
| Một dòng kết quả đại diện cho đơn, khách hay nhãn? | Tránh aggregate bị nhân hàng |
| Mẫu số của tỷ lệ/trung bình là gì? | Tránh thống kê đúng cú pháp nhưng sai nghiệp vụ |
| Window ORDER BY có khóa phá hòa? | Kết quả ranking và LAG ổn định |
| Window frame đúng mục tiêu? | Tránh LAST_VALUE hoặc running total sai |
| Cần xử lý hiệu năng với dữ liệu lớn? | Xem index, expression, EXPLAIN và bộ nhớ |
| SQL động có dùng parameter binding? | Tránh lỗi quote và SQL injection |

## 31. Tổng kết

Trong PostgreSQL, **định dạng**, **chuyển đổi kiểu** và **phân tích dữ liệu** là ba bước khác nhau nhưng thường đi chung trong một câu SQL.

**Định dạng** bằng `to_char`, `format` hay hàm chuỗi giúp tạo chuỗi thân thiện với người đọc. Dữ liệu sau định dạng thường là **text**, nên không nên dùng thay số hoặc thời điểm gốc cho những phép toán và so sánh quan trọng.

**Chuyển đổi kiểu** bằng `CAST`/`::`, `to_date`, `to_timestamp` hoặc `to_number` giúp đưa dữ liệu về hình thức thích hợp để xử lý. Cast có thể lỗi, làm tròn hoặc phụ thuộc template/múi giờ; dữ liệu đầu vào không tin cậy cần được kiểm tra và có chính sách xử lý lỗi.

**Phân tích dữ liệu** bằng aggregate, `FILTER`, window function, phân vị và các hàm thời gian cho phép tạo báo cáo có điều kiện, so sánh giữa các hàng, tính lũy kế và đo phân bố. Kết quả chỉ đúng khi người viết xác định đúng tập hàng, độ chi tiết, khoảng thời gian, mẫu số và ngữ nghĩa `NULL`.

Hãy duy trì nguyên tắc: **lưu kiểu dữ liệu đúng — chuẩn hóa và kiểm tra trước khi cast — tính toán trên giá trị có kiểu — định dạng ở bước cuối — đối chiếu kết quả với ý nghĩa nghiệp vụ và query plan**. Đây là nền tảng giúp truy vấn PostgreSQL vừa dễ đọc, vừa giữ được độ chính xác và khả năng mở rộng khi dữ liệu tăng trưởng.
