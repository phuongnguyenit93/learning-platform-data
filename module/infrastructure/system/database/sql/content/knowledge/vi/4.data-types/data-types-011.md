# Ép kiểu tường minh, chuyển đổi ngầm và lựa chọn CAST

SQL làm việc với dữ liệu **có kiểu**. Giá trị `100` ở cột `INTEGER` có thể được cộng như số, còn `'100'` ở cột `TEXT` là chuỗi ký tự. Hai giá trị trông giống nhau khi hiển thị nhưng có thể được **so sánh, sắp xếp và tính toán** khác nhau. Khi dữ liệu từ CSV, API hoặc ứng dụng không cùng kiểu với cột trong cơ sở dữ liệu, câu hỏi đặt ra là: **ai quyết định phép chuyển kiểu, khi nào phép chuyển xảy ra và liệu thông tin có bị mất không?**

Bài học này phân biệt ba cơ chế: **ép kiểu tường minh** (*explicit casting*), **chuyển đổi ngầm** (*implicit conversion/coercion*) và **hàm chuyển đổi chuyên biệt**; sau đó hướng dẫn lựa chọn `CAST` theo yêu cầu nghiệp vụ. Các ví dụ chính sử dụng **PostgreSQL**. Cú pháp `CAST(expression AS target_type)` xuất hiện rộng rãi trong SQL, nhưng quy tắc chuyển kiểu và xử lý lỗi **khác nhau giữa các hệ quản trị**.

## 1. Kiểu dữ liệu không chỉ là cách hiển thị

Giả sử một ứng dụng nhập liệu nhận chuỗi `'125000.50'` từ biểu mẫu. Chuỗi này có thể đại diện cho số tiền, nhưng bản thân nó chưa bảo đảm là dữ liệu tiền hợp lệ.

| Dữ liệu | Kiểu/ý nghĩa | Hành vi mong muốn |
|---|---|---|
| `125000` | Số nguyên | Cộng/trừ và so sánh theo số |
| `125000.50` | Có thể là số thập phân chính xác khi biểu thức được xác định là `NUMERIC`/`DECIMAL` | Tính tiền với độ chính xác phù hợp |
| `'125000.50'` | Literal chuỗi; kiểu cụ thể có thể được suy ra từ ngữ cảnh | Cần xét kiểu tại vị trí sử dụng |
| Cột `amount_text TEXT` chứa `'125000.50'` | Văn bản được lưu trong cột | Muốn tính tiền cần chuyển thành kiểu số |
| `NULL` | Giá trị chưa có/không biết, có thể gắn với một kiểu | Không đồng nghĩa số `0` hoặc chuỗi rỗng |

**Ép kiểu** là yêu cầu diễn giải một biểu thức nguồn theo **kiểu đích**. Phép chuyển có thể:

- Giữ nguyên giá trị toán học nhưng đổi cách biểu diễn, chẳng hạn văn bản `'42'` thành số nguyên `42`.
- Thay đổi cách tính toán, chẳng hạn biến phép chia số nguyên thành phép chia thập phân.
- Làm mất thông tin, chẳng hạn bỏ thời gian khi đổi `TIMESTAMP` sang `DATE`, hoặc làm tròn số thập phân.
- Không thực hiện được vì chuỗi sai định dạng, giá trị vượt phạm vi, hoặc hai kiểu không có phép chuyển phù hợp.

```text
Nguồn có kiểu         Phép chuyển           Kết quả có kiểu
TEXT '125000.50'  ── CAST/parse ──>  NUMERIC 125000.50
TEXT 'không rõ'   ── CAST        ──>  Lỗi nếu không hợp lệ
INTEGER 5        ── CAST        ──>  NUMERIC 5.00 (khi chọn scale 2)
```

`CAST` trong truy vấn tạo **biểu thức có kiểu đích**; nó **không tự sửa kiểu khai báo của cột**. Để thay đổi kiểu lưu trữ của cả cột cần một thao tác thay đổi schema, ví dụ `ALTER TABLE`, cùng việc xem xét chuyển dữ liệu hiện có, quyền và tác động tới ứng dụng.

## 2. Ép kiểu tường minh và chuyển đổi ngầm

### 2.1. Ép kiểu tường minh: người viết SQL quyết định

```sql
SELECT CAST('42' AS INTEGER) AS quantity;
-- quantity là giá trị số nguyên 42.
```

Ý định của câu lệnh rất rõ: giá trị đầu vào phải được chuyển sang `INTEGER`. Nếu đầu vào thực tế không thể chuyển theo quy tắc của PostgreSQL, truy vấn báo lỗi.

### 2.2. Chuyển đổi ngầm: hệ quản trị quyết định trong một ngữ cảnh

Khi các toán hạng có kiểu khác nhau, bộ phân tích SQL phải tìm toán tử và kiểu kết quả phù hợp:

```sql
-- PostgreSQL:
SELECT 10 + 2.5 AS total;
-- total = 12.5.
```

Trong một số trường hợp, hệ quản trị tự chuyển một toán hạng sang kiểu tương thích. Nhưng điều này **không có nghĩa** mọi chuỗi “trông giống số” đều tự động được xem là số.

```sql
-- PostgreSQL: literal '3' ban đầu có thể được suy ra kiểu INTEGER.
SELECT 2 + '3' AS result;
-- result = 5.

-- Còn TEXT đã có kiểu thì không được ngầm coi là INTEGER trong phép +:
-- SELECT 2 + CAST('3' AS TEXT); -- Lỗi toán tử/kiểu.

-- Chuyển rõ ràng khi dữ liệu nguồn thật sự là TEXT:
SELECT 2 + CAST(CAST('3' AS TEXT) AS INTEGER) AS result;
```

Trong PostgreSQL, literal chuỗi trực tiếp như `'3'` có thể thuộc kiểu khởi đầu `unknown` và được **suy kiểu từ ngữ cảnh**. Một cột đã khai báo `TEXT` hoặc một tham số ứng dụng có kiểu xác định không nhất thiết được xử lý giống literal `unknown`.

Mỗi hệ quản trị có quy tắc suy kiểu, ưu tiên kiểu và chọn toán tử riêng. Không nên giả định PostgreSQL, SQL Server, MySQL và SQLite tự chuyển các giá trị theo cùng cách.

### 2.3. Hàm chuyển đổi chuyên biệt

Khi đầu vào có **mẫu định dạng riêng** hoặc đầu ra phải là **chuỗi trình bày**, đôi khi cần hàm chuyên biệt:

```sql
-- PostgreSQL: đọc chuỗi ngày theo mẫu ngày/tháng/năm.
SELECT TO_DATE('14/11/2026', 'DD/MM/YYYY') AS parsed_date;

-- PostgreSQL: đổi ngày thành chuỗi được định dạng.
SELECT TO_CHAR(DATE '2026-11-14', 'DD/MM/YYYY') AS display_date;
```

`CAST` tập trung vào **chuyển kiểu**; `TO_DATE`/`TO_CHAR` có thêm **mẫu phân tích hoặc định dạng**. Một phép chuyển chuỗi thành ngày vẫn cần dữ liệu đầu vào hợp lệ; việc khớp một mẫu ký tự không bảo đảm ngày lịch tồn tại.

## 3. Cú pháp `CAST` và hai cách viết trong PostgreSQL

### 3.1. Cú pháp SQL phổ biến

```sql
CAST(expression AS target_data_type)
```

`expression` có thể là literal, cột, phép tính, lời gọi hàm, `CASE` hoặc biểu thức khác. `target_data_type` là kiểu đích, có thể kèm thông số độ dài hoặc độ chính xác.

```sql
SELECT
    CAST('2026-11-14' AS DATE)           AS report_date,
    CAST('150000.75' AS NUMERIC(12, 2)) AS amount,
    CAST(42 AS VARCHAR(20))             AS code_text,
    CAST('true' AS BOOLEAN)             AS is_active;
```

Ở PostgreSQL, các biểu thức đầu ra lần lượt có kiểu `DATE`, `NUMERIC(12,2)`, `VARCHAR(20)` và `BOOLEAN`. `AS report_date` là **đặt tên cột kết quả**, khác với `AS DATE` nằm **bên trong** `CAST`.

PostgreSQL còn có cú pháp rút gọn:

```sql
SELECT
    CAST('42' AS INTEGER) AS standard_style,
    '42'::INTEGER         AS postgres_style;
```

Hai cách thường tương đương về ý nghĩa trong PostgreSQL. Dạng `::` tiện khi viết PostgreSQL thuần nhưng không phải cú pháp di động của mọi database. Đối với ví dụ SQL dùng nhiều nền tảng, `CAST(... AS ...)` thường là cách lựa chọn dễ đọc hơn.

### 3.2. Xem kiểu của biểu thức

PostgreSQL có hàm `pg_typeof` hỗ trợ học tập và chẩn đoán:

```sql
SELECT
    pg_typeof(CAST('42' AS INTEGER)) AS numeric_kind,
    pg_typeof(CAST('42' AS TEXT))    AS text_kind,
    pg_typeof(CAST('42' AS NUMERIC)) AS decimal_kind;
```

Hàm `pg_typeof` là tiện ích của PostgreSQL. SQL trên hệ quản trị khác có thể cần cơ chế kiểm tra kiểu dữ liệu riêng.

### 3.3. `CAST` xuất hiện ở đâu trong truy vấn?

Ép kiểu có thể nằm trong `SELECT`, `WHERE`, `ORDER BY`, `GROUP BY` hoặc các phép tính tổng hợp:

```sql
-- Ví dụ cấu trúc, giả sử cột amount_text chứa toàn chuỗi số hợp lệ.
SELECT CAST(amount_text AS NUMERIC(12, 2)) AS amount
FROM payment_import;

-- Lọc theo giá trị số thay vì theo văn bản.
SELECT *
FROM payment_import
WHERE CAST(amount_text AS NUMERIC(12, 2)) >= 100000;

-- Gom các cách viết '01' và '1' thành cùng khóa số 1.
SELECT CAST(group_code AS INTEGER) AS numeric_code, COUNT(*)
FROM raw_groups
GROUP BY CAST(group_code AS INTEGER);
```

Những truy vấn trên giả định bảng `payment_import`, `raw_groups` tồn tại và các giá trị liên quan đều chuyển được. **Vị trí cú pháp hợp lệ không đồng nghĩa dữ liệu luôn hợp lệ.** Khi cần xử lý dữ liệu thô, phải xác định cách phân loại trước khi cast; mục 9 cung cấp ví dụ đầy đủ.

## 4. Khi chuyển đổi ngầm làm kết quả khác dự kiến

### 4.1. So sánh văn bản không giống so sánh số

Giả sử các giá trị `2`, `10`, `001`, `1` được lưu dưới dạng `TEXT`. Thứ tự sắp xếp chuỗi có thể là `001`, `1`, `10`, `2`, tùy collation. Nếu coi chúng là **số**, thứ tự phải là 1, 1, 2, 10.

```sql
WITH sample(value_text) AS (
    VALUES ('2'), ('10'), ('001'), ('1')
)
SELECT value_text
FROM sample
ORDER BY value_text;
```

Sắp theo **giá trị số**:

```sql
WITH sample(value_text) AS (
    VALUES ('2'), ('10'), ('001'), ('1')
)
SELECT
    value_text,
    CAST(value_text AS INTEGER) AS value_number
FROM sample
ORDER BY CAST(value_text AS INTEGER), value_text;
```

Điểm quan trọng hơn thứ tự hiển thị: **`'001'` và `'1'` là hai chuỗi khác nhau nhưng cùng chuyển thành số 1**. Nếu đó là mã khách hàng, mã kho, mã đơn, mã bưu chính cần giữ số 0 đầu, ép sang `INTEGER` có thể làm mất ý nghĩa ban đầu. Nếu đó là số lượng, kiểu số lại phù hợp.

### 4.2. `CASE`, `COALESCE` và `UNION` phải có kiểu kết quả tương thích

Các nhánh của biểu thức `CASE` cần một kiểu kết quả có thể dung hòa:

```sql
SELECT
    CASE
        WHEN TRUE THEN CAST(100.50 AS NUMERIC(10, 2))
        ELSE CAST(0 AS NUMERIC(10, 2))
    END AS selected_amount;
```

`COALESCE` chọn giá trị không `NULL` đầu tiên và cũng phải xác định một kiểu kết quả tương thích:

```sql
SELECT COALESCE(
    CAST(NULL AS NUMERIC(12, 2)),
    CAST(0 AS NUMERIC(12, 2))
) AS amount_or_zero;
```

Hai nhánh của `UNION ALL` tương ứng về số cột và kiểu:

```sql
SELECT CAST(1 AS NUMERIC(10, 2)) AS value
UNION ALL
SELECT CAST(2.50 AS NUMERIC(10, 2));
```

Việc ghi rõ kiểu rất hữu ích khi nhánh chỉ có `NULL`, tham số không xác định kiểu hoặc biểu thức phức tạp. Không nên coi `CASE` hay `UNION` là cơ chế tự động chữa mọi sai khác kiểu của dữ liệu.

### 4.3. Quy tắc chuyển kiểu phụ thuộc hệ quản trị

Một số hệ có thể tự biến chuỗi không hợp lệ thành số 0 hoặc sinh cảnh báo trong ngữ cảnh nhất định; hệ khác báo lỗi. Vì vậy, **có kết quả trả về chưa chắc là chuyển đổi đúng nghiệp vụ**. Khi thông tin về kiểu đích quan trọng, hãy chỉ rõ `CAST` hoặc truyền dữ liệu đã đúng kiểu từ ứng dụng.

## 5. Chuyển kiểu số: phần lẻ, độ chính xác và tràn phạm vi

### 5.1. Phép chia nguyên: phải cast **trước khi chia**

Trong PostgreSQL:

```sql
SELECT 5 / 2 AS integer_division;
-- 2: phép chia hai số nguyên không giữ phần lẻ.

SELECT CAST(5 AS NUMERIC) / 2 AS decimal_division;
-- 2.5: phép chia theo số thập phân.
```

So sánh vị trí cast:

```sql
SELECT CAST(5 / 2 AS NUMERIC(10, 2)) AS too_late;
-- 2.00: phép chia nguyên đã xảy ra.

SELECT CAST(5 AS NUMERIC(10, 2)) / 2 AS correct;
-- 2.50: phần lẻ được giữ.
```

Các phép tính tỷ lệ chuyển đổi, phần trăm, điểm trung bình và giá trung bình rất dễ sai nếu cast **sau** khi kết quả trung gian đã mất phần thập phân.

### 5.2. `NUMERIC`/`DECIMAL` khác `FLOAT`

| Nhóm | Đặc điểm | Ví dụ dùng |
|---|---|---|
| `SMALLINT`, `INTEGER`, `BIGINT` | Số nguyên, phạm vi hữu hạn | Số lượng, mã định danh dạng số |
| `NUMERIC(p,s)`, `DECIMAL(p,s)` | Số thập phân với độ chính xác và thang thập phân xác định | Tiền, thuế, số liệu yêu cầu tính toán thập phân |
| `REAL`, `DOUBLE PRECISION` | Số dấu phẩy động nhị phân gần đúng | Đo đạc và phép tính chấp nhận sai số |

```sql
SELECT
    CAST('123.45' AS NUMERIC(10, 2))    AS exact_decimal,
    CAST('123.45' AS DOUBLE PRECISION) AS approximate_float;
```

Hai kết quả có thể **hiển thị giống nhau** nhưng có cách biểu diễn nội bộ khác nhau. Nhiều số thập phân như 0.1 không biểu diễn chính xác dưới dạng dấu phẩy động nhị phân. Với tính tiền yêu cầu độ chính xác thập phân nhất quán, thường chọn `NUMERIC/DECIMAL` có giới hạn phù hợp.

### 5.3. `NUMERIC(10,2)` nghĩa là gì?

Ở PostgreSQL, `NUMERIC(10,2)` có **10 chữ số tổng cộng**, trong đó **2 chữ số sau dấu thập phân**; do đó phần nguyên có tối đa 8 chữ số.

```sql
SELECT
    CAST(12.345 AS NUMERIC(6, 2)) AS rounded_decimal;
-- 12.35.
```

Giảm thang thập phân có thể làm tròn. Chuyển sang kiểu có phạm vi nhỏ hơn có thể báo lỗi:

```sql
-- PostgreSQL: SMALLINT chỉ nhận từ -32768 đến 32767.
-- SELECT CAST(40000 AS SMALLINT);

-- NUMERIC(5,2) có tối đa 3 chữ số phần nguyên.
-- SELECT CAST(12345.67 AS NUMERIC(5,2));
```

Các ví dụ lỗi được chú thích; nếu muốn quan sát thông báo, hãy chạy riêng trong môi trường thử.

### 5.4. Cast sang số nguyên: làm tròn hay cắt?

Không nên mặc định `CAST(decimal AS INTEGER)` có nghĩa là **bỏ phần thập phân** ở mọi hệ quản trị. Trong PostgreSQL:

```sql
SELECT
    CAST(12.7 AS INTEGER)         AS rounded_integer,
    CAST(TRUNC(12.7) AS INTEGER) AS truncated_integer;
-- Lần lượt là 13 và 12.
```

PostgreSQL làm tròn khi chuyển `NUMERIC` sang số nguyên; dùng `TRUNC` nếu mục đích rõ ràng là bỏ phần lẻ. Những hệ quản trị khác có thể xử lý khác, nên hãy lựa chọn hàm/phép chuyển theo đúng quy định nghiệp vụ và kiểm tra tại hệ đích.

### 5.5. Chuỗi số có dấu phân cách không luôn hợp lệ

```sql
SELECT CAST('125000.50' AS NUMERIC(12, 2)) AS amount;

-- Không nên giả định những chuỗi dưới đây được CAST chấp nhận:
-- '125,000.50'
-- '125.000,50'
-- '125 000,50 VND'
```

Dấu phẩy, dấu chấm và khoảng trắng có thể mang ý nghĩa khác nhau theo định dạng quốc gia. Hãy quy định **một định dạng dữ liệu nguồn** hoặc dùng hàm phân tích phù hợp với mẫu đã biết; đừng để quy tắc hiển thị tiền tệ chi phối kiểu dữ liệu nội bộ.

## 6. Văn bản: đổi sang chuỗi không đồng nghĩa định dạng

### 6.1. Số thành chuỗi

```sql
SELECT
    CAST(101 AS VARCHAR(20)) AS order_code,
    CAST(125000.50 AS VARCHAR(30)) AS amount_text;
```

Kết quả có kiểu chuỗi, phù hợp nếu cần ghép hoặc hiển thị thông tin. Nhưng `CAST` thường dùng cách biểu diễn mặc định của hệ quản trị; nó không bảo đảm chèn dấu phân tách hàng nghìn hay định dạng tiền tệ.

Nếu muốn một **chuỗi trình bày** theo mẫu trong PostgreSQL:

```sql
SELECT TO_CHAR(125000.50, 'FM999,999,990.00') AS display_amount;
```

`TO_CHAR` trả về văn bản. Khi cần tiếp tục cộng, trừ, tổng hợp, hãy giữ dữ liệu ở kiểu số.

### 6.2. Chuỗi thành số

```sql
SELECT CAST('125000.50' AS NUMERIC(12, 2)) AS amount;
```

Phép chuyển chỉ hợp lệ khi chuỗi có dạng được hệ quản trị chấp nhận. Ví dụ trong PostgreSQL:

```sql
-- Lỗi: không thể diễn giải chuỗi thành NUMERIC.
-- SELECT CAST('không rõ' AS NUMERIC(12, 2));
```

`CAST` không phải hàm tự động trả `NULL` khi gặp dữ liệu sai. Nếu cần tiếp nhận dữ liệu từ file CSV hay API, phải phân biệt **dữ liệu thiếu**, **dữ liệu sai cú pháp** và **dữ liệu số hợp lệ** trước khi cộng vào báo cáo.

### 6.3. Giảm độ dài chuỗi có thể mất ký tự

Trong PostgreSQL, ép kiểu **tường minh** sang `VARCHAR(n)` có thể cắt chuỗi xuống `n` ký tự:

```sql
SELECT CAST('DATABASE' AS VARCHAR(4)) AS short_text;
-- 'DATA'.
```

Điều này khác với nhiều trường hợp gán chuỗi quá dài vào cột `VARCHAR(n)` vốn gây lỗi. Không nên dùng một cast hẹp như cách “kiểm tra chuỗi đủ ngắn”, vì dữ liệu có thể đã bị cắt trước khi kiểm tra.

Với Unicode, **số ký tự khác số byte**:

```sql
SELECT
    CHAR_LENGTH('Đà Nẵng') AS number_of_characters,
    OCTET_LENGTH('Đà Nẵng') AS number_of_bytes;
```

Trong UTF-8, một số ký tự cần nhiều byte. Đổi `TEXT` thành `VARCHAR` không đồng nghĩa thay đổi encoding. Tương tự, **collation** quyết định cách so sánh/sắp xếp chuỗi; cast giữa hai kiểu văn bản không tự bảo đảm thứ tự tên tiếng Việt đúng theo mong muốn.

## 7. Ngày giờ: có thể mất thông tin và thay đổi ngày lịch

### 7.1. Chuỗi thành `DATE`

```sql
-- PostgreSQL: định dạng ISO rõ ràng.
SELECT CAST('2026-11-14' AS DATE) AS due_date;
```

Ưu tiên dạng ISO `YYYY-MM-DD` để giảm nhập nhằng. Chuỗi `'11/12/2026'` có thể mang nghĩa 11 tháng 12 hoặc 12 tháng 11 tùy khuôn mẫu và hệ thống. Khi định dạng đầu vào cố định là `DD/MM/YYYY`, PostgreSQL cho phép:

```sql
SELECT TO_DATE('14/11/2026', 'DD/MM/YYYY') AS due_date;
```

Hãy kiểm tra tính hợp lệ của ngày nguồn; khớp hình dạng ký tự không tự bảo đảm ngày tháng là hợp lệ.

### 7.2. Ba kiểu thời gian trong PostgreSQL

| Kiểu | Ý nghĩa | Ví dụ |
|---|---|---|
| `DATE` | Ngày theo lịch, không có giờ | Ngày sinh, ngày đến hạn |
| `TIMESTAMP WITHOUT TIME ZONE` (`TIMESTAMP`) | Ngày + giờ trên đồng hồ, không tự xác định múi giờ | Giờ mở cửa theo lịch địa phương |
| `TIMESTAMP WITH TIME ZONE` (`TIMESTAMPTZ`) | Một thời điểm xác định; hiển thị theo múi giờ phiên | Thời điểm đơn hàng được tạo |

```sql
SELECT
    CAST(DATE '2026-11-14' AS TIMESTAMP) AS start_of_day,
    CAST(TIMESTAMP '2026-11-14 09:30:45' AS DATE) AS just_date;
```

Từ `DATE` thành `TIMESTAMP` thường là 00:00:00 của ngày đó. Từ `TIMESTAMP` sang `DATE` **bỏ thông tin giờ**. Nếu câu hỏi nghiệp vụ cần cả ngày lẫn giờ, không thể lấy lại phần giờ từ kết quả đã cast thành `DATE`.

### 7.3. `TIMESTAMPTZ` thành `DATE` phụ thuộc múi giờ phiên

Cùng một thời điểm lúc 00:30 tại Việt Nam vẫn là ngày hôm trước ở UTC:

```sql
SET TIME ZONE 'UTC';

SELECT CAST(
    TIMESTAMPTZ '2026-11-14 00:30:00+07' AS DATE
) AS date_in_utc;
-- 2026-11-13.

SET TIME ZONE 'Asia/Ho_Chi_Minh';

SELECT CAST(
    TIMESTAMPTZ '2026-11-14 00:30:00+07' AS DATE
) AS date_in_vietnam;
-- 2026-11-14.

RESET TIME ZONE;
```

`SET TIME ZONE` thay đổi **cách diễn giải ngày lịch của một thời điểm trong phiên**, không thay đổi thời điểm nguồn. Nếu báo cáo yêu cầu “ngày tại Việt Nam” bất kể cấu hình kết nối, hãy chỉ rõ khu vực:

```sql
SELECT CAST(
    TIMESTAMPTZ '2026-11-14 00:30:00+07'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    AS DATE
) AS business_date_in_vietnam;
```

Trong PostgreSQL, `TIMESTAMPTZ AT TIME ZONE 'Asia/Ho_Chi_Minh'` đưa thời điểm về `TIMESTAMP` địa phương tại vùng chọn; cast tiếp sang `DATE` lấy ngày lịch ở đó.

### 7.4. Dữ liệu thời gian khác chuỗi trình bày

```sql
SELECT
    CAST(TIMESTAMP '2026-11-14 09:30:45' AS DATE) AS date_value,
    TO_CHAR(TIMESTAMP '2026-11-14 09:30:45', 'DD/MM/YYYY') AS display_text;
```

`date_value` là kiểu `DATE` để so sánh/tính toán lịch. `display_text` là văn bản cho người đọc. Sắp chuỗi `DD/MM/YYYY` theo thứ tự chữ **không có nghĩa** là sắp theo thời gian.

## 8. `BOOLEAN`, `NULL` và lỗi khi cast

### 8.1. Boolean

```sql
-- PostgreSQL:
SELECT
    CAST('true' AS BOOLEAN)  AS active,
    CAST('false' AS BOOLEAN) AS disabled;
```

Các hệ quản trị không có cùng quy tắc cho `'1'`, `'yes'`, `'false'` hoặc kiểu boolean nội bộ. Không nên chuyển các giá trị biểu mẫu thành boolean theo một giả định dùng chung cho tất cả database.

### 8.2. `CAST(NULL AS type)` vẫn là `NULL`

```sql
SELECT
    CAST(NULL AS INTEGER) AS missing_count,
    CAST(NULL AS DATE)    AS missing_date;
```

Cả hai biểu thức vẫn không có giá trị nhưng đã có **kiểu xác định**. Đây là kỹ thuật hữu ích trong `CASE`, `UNION` hoặc truy vấn cần metadata kiểu đầu ra khi dữ liệu chưa có.

`CAST` không tự biến `NULL` thành 0:

```sql
SELECT COALESCE(
    CAST(NULL AS NUMERIC(12, 2)),
    CAST(0 AS NUMERIC(12, 2))
) AS amount_or_zero;
```

Chỉ thay `NULL` bằng 0 khi đúng quy ước nghiệp vụ, vì “chưa biết số tiền” và “số tiền bằng 0” có thể khác nhau.

### 8.3. `CAST` không phải phép “thử chuyển”

Trong PostgreSQL:

```sql
-- Chạy riêng trên môi trường thử để quan sát lỗi:
-- SELECT CAST('abc' AS INTEGER);
-- SELECT CAST('2026-02-30' AS DATE);
```

Giá trị không hợp lệ thường khiến câu lệnh **báo lỗi**. Một số hệ quản trị cung cấp hàm “thử chuyển rồi trả `NULL`” như `TRY_CAST` (SQL Server) hoặc `SAFE_CAST` (BigQuery). PostgreSQL thông thường không có hàm `TRY_CAST` tích hợp theo đúng cú pháp đó.

## 9. Thực hành: chuyển dữ liệu tiền từ CSV một cách có kiểm soát

Giả sử nguồn ngoài gửi một cột tiền dưới dạng văn bản. Ta giữ nguyên chuỗi gốc trong bảng staging để phân biệt số hợp lệ, dữ liệu sai và dữ liệu thiếu.

### 9.1. Tạo dữ liệu mẫu trong PostgreSQL

```sql
CREATE TEMP TABLE incoming_amounts (
    source_id INTEGER PRIMARY KEY,
    amount_text TEXT
);

INSERT INTO incoming_amounts (source_id, amount_text) VALUES
    (1, '125000.50'),
    (2, ' 200000 '),
    (3, 'N/A'),
    (4, ''),
    (5, NULL),
    (6, '99000');

SELECT source_id, amount_text
FROM incoming_amounts
ORDER BY source_id;
```

Đây là bảng **tạm** của phiên PostgreSQL hiện tại. Nếu muốn chạy lại từ đầu, mở phiên kết nối mới hoặc sử dụng tên bảng tạm khác. Một truy vấn `CAST(amount_text AS NUMERIC(12,2))` trên mọi dòng sẽ lỗi khi gặp `N/A`.

### 9.2. Quy định dữ liệu hợp lệ

Bài tập đặt quy tắc cụ thể: số tiền **không âm**, phần nguyên có từ 1 đến 10 chữ số, phần thập phân nếu có gồm 1–2 chữ số và dùng dấu chấm; bỏ khoảng trắng đầu/cuối. Chuỗi rỗng hoặc `NULL` là **missing**, chuỗi khác quy tắc là **invalid**. Đây là **quy ước ví dụ**, không phải chuẩn nhập tiền duy nhất cho mọi hệ thống.

```sql
SELECT
    source_id,
    amount_text,
    CASE
        WHEN amount_text IS NULL OR BTRIM(amount_text) = ''
            THEN 'missing'
        WHEN BTRIM(amount_text) ~ '^[0-9]{1,10}([.][0-9]{1,2})?$'
            THEN 'valid'
        ELSE 'invalid'
    END AS parse_status
FROM incoming_amounts
ORDER BY source_id;
```

Toán tử `~` là so khớp biểu thức chính quy của PostgreSQL. Kết quả mong đợi:

| source_id | amount_text | parse_status |
|---:|---|---|
| 1 | `125000.50` | `valid` |
| 2 | ` 200000 ` | `valid` |
| 3 | `N/A` | `invalid` |
| 4 | Chuỗi rỗng | `missing` |
| 5 | `NULL` | `missing` |
| 6 | `99000` | `valid` |

### 9.3. Chỉ cast dữ liệu thỏa quy tắc

```sql
WITH parsed AS (
    SELECT
        source_id,
        amount_text,
        CASE
            WHEN BTRIM(amount_text) ~ '^[0-9]{1,10}([.][0-9]{1,2})?$'
                THEN CAST(BTRIM(amount_text) AS NUMERIC(12, 2))
            ELSE CAST(NULL AS NUMERIC(12, 2))
        END AS amount_value,
        CASE
            WHEN amount_text IS NULL OR BTRIM(amount_text) = ''
                THEN 'missing'
            WHEN BTRIM(amount_text) ~ '^[0-9]{1,10}([.][0-9]{1,2})?$'
                THEN 'valid'
            ELSE 'invalid'
        END AS parse_status
    FROM incoming_amounts
)
SELECT source_id, amount_text, amount_value, parse_status
FROM parsed
ORDER BY source_id;
```

| source_id | amount_value | parse_status |
|---:|---:|---|
| 1 | 125000.50 | `valid` |
| 2 | 200000.00 | `valid` |
| 3 | `NULL` | `invalid` |
| 4 | `NULL` | `missing` |
| 5 | `NULL` | `missing` |
| 6 | 99000.00 | `valid` |

Biểu thức chính quy ở đây chỉ chấp nhận tối đa 10 chữ số phần nguyên và 2 chữ số phần thập phân, tương ứng giới hạn giá trị của `NUMERIC(12,2)`. Một quy tắc kiểm tra khác có thể chấp nhận chuỗi “đúng cú pháp số” nhưng vẫn **vượt phạm vi kiểu đích**. Cần xét cả cú pháp, phạm vi và độ chính xác.

Không nên bỏ cột `parse_status` khi xử lý dữ liệu thô: `NULL` sau parse có thể đến từ **giá trị thiếu** hoặc **giá trị sai**. Một quy trình nhập dữ liệu thực tế nên lưu lý do sai để người vận hành sửa, thay vì âm thầm coi chúng như khoản tiền 0 đồng.

### 9.4. Tổng hợp số tiền sau khi đã parse

```sql
WITH parsed AS (
    SELECT
        CASE
            WHEN BTRIM(amount_text) ~ '^[0-9]{1,10}([.][0-9]{1,2})?$'
                THEN CAST(BTRIM(amount_text) AS NUMERIC(12, 2))
            ELSE CAST(NULL AS NUMERIC(12, 2))
        END AS amount_value
    FROM incoming_amounts
)
SELECT
    COUNT(amount_value) AS valid_amount_count,
    SUM(amount_value) AS total_amount
FROM parsed;
```

Kết quả: **3 khoản tiền hợp lệ**, tổng **424000.50**. `COUNT(amount_value)` và `SUM(amount_value)` bỏ qua các giá trị `NULL`. Đây là tổng của **các giá trị hợp lệ theo quy tắc bài tập**; không có nghĩa một quy trình nghiệp vụ đã xử lý xong các bản ghi `invalid`.

### 9.5. Quy trình tư duy cho dữ liệu nhập

```text
CSV / API ngoài hệ thống
          │
          ▼
Giữ nguyên chuỗi gốc (staging)
          │
          ▼
Định nghĩa định dạng và miền giá trị hợp lệ
          │
          ▼
Phân loại valid / invalid / missing
          │
       ┌──┴─────────────┐
       ▼                ▼
      valid       invalid / missing
       │                │
       ▼                ▼
 CAST với kiểu      Ghi nhận lỗi và
 đích phù hợp       xử lý lại nguồn
       │
       ▼
Lưu vào cột dữ liệu có kiểu đúng
```

Khi có thể, nên khai báo đúng kiểu cột ngay từ thiết kế và kiểm tra dữ liệu tại ranh giới ứng dụng/database. Không nên để số tiền nằm ở `TEXT` lâu dài rồi bắt mọi truy vấn báo cáo tự cast lại.

## 10. Lựa chọn vị trí `CAST` và tác động đến hiệu năng

### 10.1. Cast trên cột trong `WHERE` có thể ảnh hưởng chỉ mục

Giả sử bảng `orders` có cột `created_at TIMESTAMP` và chỉ mục B-tree thông thường:

```sql
-- Cast cột thành DATE tại điều kiện lọc.
SELECT order_id
FROM orders
WHERE CAST(created_at AS DATE) = DATE '2026-11-14';
```

Yêu cầu “trong ngày 14/11/2026” có thể biểu diễn bằng **khoảng nửa mở**:

```sql
SELECT order_id
FROM orders
WHERE created_at >= TIMESTAMP '2026-11-14 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-15 00:00:00';
```

Đối với cột `TIMESTAMP` **không kèm múi giờ** như giả định, cách thứ hai thường giúp bộ tối ưu tận dụng chỉ mục trực tiếp trên `created_at` dễ hơn, vì không cần tính `CAST` trên mỗi giá trị trước khi so sánh. Hệ quản trị có thể hỗ trợ **expression index/function-based index** hoặc tối ưu riêng, nên đây là nguyên tắc xem xét, không phải quy tắc “mọi cast đều chậm”.

Nếu cột thực tế là `TIMESTAMPTZ`, phải xác định múi giờ nghiệp vụ cho ngày cần lọc rồi tính hai thời điểm biên tương ứng; không thể thay máy móc bằng hai mốc ngày không có vùng.

### 10.2. Cast tham số cho đúng kiểu, không cast cột vô cớ

Giả sử `orders.order_id` là `INTEGER`:

```sql
-- So sánh cùng kiểu số.
SELECT order_id
FROM orders
WHERE order_id = 101;

-- Có thể làm thay đổi kiểu so sánh và khả năng dùng chỉ mục:
SELECT order_id
FROM orders
WHERE CAST(order_id AS TEXT) = '101';
```

Nếu tham số từ ứng dụng đang ở dạng chuỗi, nên **bind đúng kiểu** bằng driver hoặc chuyển **tham số** ở ranh giới có kiểm soát. Không nhất thiết biến mọi giá trị của cột số thành chuỗi để so sánh. Khi tối ưu, kiểm tra `EXPLAIN` và kế hoạch thực thi thực tế sau khi đã xác nhận ngữ nghĩa kết quả.

### 10.3. Chọn `CAST` vì ý nghĩa dữ liệu, không vì câu SQL ngắn hơn

Một số câu hỏi trước khi cast:

1. Giá trị này là **mã** cần giữ hình thức hay **số** để tính toán?
2. Kiểu nguồn là gì: kiểu cột, kiểu tham số, literal hay kiểu kết quả của một biểu thức?
3. Có nguy cơ mất phần lẻ, số 0 đầu, ký tự, phạm vi số hoặc ngày lịch không?
4. Dữ liệu nguồn có thể sai định dạng hoặc chứa `NULL` không?
5. Cần chuyển để **tính toán** hay chỉ cần **định dạng hiển thị**?
6. Cast đặt trên cột có chỉ mục hay đặt ở ranh giới nhập liệu/tham số?

Nếu kiểu dữ liệu đã đúng và toán tử có ngữ nghĩa đúng, không cần thêm `CAST` chỉ để “cho chắc”.

## 11. Khác biệt giữa các hệ quản trị

`CAST` có cú pháp phổ biến, nhưng **đích kiểu** và **hành vi lỗi** không hoàn toàn tương thích.

| Hệ quản trị | Cú pháp thông dụng | Lưu ý chính |
|---|---|---|
| PostgreSQL | `CAST(x AS INTEGER)`, `x::INTEGER` | Có suy kiểu literal `unknown`; cast giá trị sai thường báo lỗi; không có `TRY_CAST` tích hợp thông dụng |
| SQL Server | `CAST(x AS INT)`, `CONVERT(INT, x)` | Có `TRY_CAST`/`TRY_CONVERT` cho nhiều trường hợp trả `NULL` khi chuyển đổi thất bại |
| MySQL | `CAST(x AS SIGNED)`, `CAST(x AS DECIMAL(12,2))` | Có thể sinh cảnh báo hoặc hành vi chuyển số bất ngờ; lỗi phụ thuộc ngữ cảnh và `sql_mode` |
| SQLite | `CAST(x AS INTEGER)`, `CAST(x AS REAL)` | Kiểu động và type affinity; có giá trị không phải số cast sang số thành 0 |
| BigQuery (GoogleSQL) | `CAST(x AS INT64)`, `SAFE_CAST(x AS INT64)` | `SAFE_CAST` có thể trả `NULL` cho nhiều lỗi chuyển đổi lúc thực thi |

Ví dụ dành riêng cho SQL Server:

```sql
-- SQL Server:
SELECT
    TRY_CAST('123' AS INT) AS valid_number,
    TRY_CAST('abc' AS INT) AS invalid_number;
-- Trong ví dụ này: 123 và NULL.
```

`TRY_CAST` không phải lời hứa xử lý được mọi phép chuyển bị cấm hoặc mọi trường hợp đặc biệt. Nếu giá trị sai biến thành `NULL`, cần lưu thêm trạng thái để phân biệt với dữ liệu thiếu thật.

Ví dụ dành riêng cho BigQuery:

```sql
-- BigQuery (GoogleSQL):
SELECT
    SAFE_CAST('123' AS INT64) AS valid_number,
    SAFE_CAST('abc' AS INT64) AS invalid_number;
```

Ví dụ dành riêng cho SQLite:

```sql
-- SQLite:
SELECT CAST('abc' AS INTEGER) AS result;
-- Giá trị 0 trong SQLite, không phải lỗi giống PostgreSQL.
```

Không nên bê nguyên chiến lược kiểm tra lỗi từ PostgreSQL sang SQLite/MySQL mà chưa xem quy tắc chuyển đổi. Trong dữ liệu tài chính, `0` là một giá trị hợp lệ nên việc tự chuyển dữ liệu sai sang `0` có thể gây lỗi khó phát hiện.

Nếu cần SQL dễ di chuyển giữa các nền tảng, ưu tiên `CAST(... AS ...)` với kiểu phổ biến, tránh cú pháp riêng khi không cần, và **kiểm tra lại** chuyển số thực sang số nguyên, giới hạn chuỗi, ngày giờ, `NULL`, overflow, xử lý đầu vào sai trên hệ đích.

## 12. Bảng chọn cách chuyển đổi

| Yêu cầu | Hướng xử lý phù hợp | Bẫy cần tránh |
|---|---|---|
| Chuỗi `'150000.75'` đã được xác minh là tiền | `CAST(... AS NUMERIC(12,2))` | Dùng `FLOAT` tùy tiện cho tiền |
| Chia hai số nguyên nhưng cần phần lẻ | Cast **một toán hạng trước khi chia** sang `NUMERIC` | Cast sau khi phép chia nguyên đã kết thúc |
| Xuất ngày thành `DD/MM/YYYY` | Hàm định dạng hoặc tầng hiển thị | Sắp xếp chuỗi ngày theo chữ rồi coi là theo thời gian |
| Đọc ngày nhập `DD/MM/YYYY` | Hàm phân tích với mẫu và xác minh ngày hợp lệ | Dựa vào mặc định phiên cho ngày mơ hồ |
| Văn bản nhập có `N/A` | Phân loại nguồn, rồi chỉ cast giá trị hợp lệ | Cast cả cột và chờ hệ thống tự cho `NULL` |
| Cần giữ mã `'00045'` | Lưu `TEXT`/`VARCHAR` với quy tắc phù hợp | Biến thành số 45 rồi mất định dạng |
| Lọc cột `INTEGER` theo tham số ngoài | Bind/chuyển tham số đúng kiểu | Ép toàn bộ cột thành `TEXT` ở mỗi truy vấn |
| `NULL` cần thay giá trị khi báo cáo | `COALESCE` với giá trị thay thế đúng nghiệp vụ | Tự coi mọi giá trị thiếu là 0 |

## 13. Bài tập tự luyện

Các bài sau dành cho PostgreSQL. Trước khi chạy, hãy dự đoán **kiểu kết quả**, **giá trị** và **nơi có thể phát sinh lỗi**.

### Bài 1 — Vị trí cast

```sql
SELECT CAST(7 / 2 AS NUMERIC(10,2)) AS a;
SELECT CAST(7 AS NUMERIC(10,2)) / 2 AS b;
```

Vì sao `a` và `b` khác nhau?

### Bài 2 — Mã có số 0 đầu

Đơn hàng có mã `'00045'`. Bạn chọn kiểu gì nếu cần giữ nguyên mã trên hóa đơn? `CAST('00045' AS INTEGER)` làm mất thông tin nào?

### Bài 3 — Số tiền nhập dưới dạng văn bản

Cho bốn đầu vào `'120.50'`, `'abc'`, `''` và `NULL`. Theo quy tắc chỉ chấp nhận số thập phân dùng dấu chấm, hãy phân loại **valid/invalid/missing**; giải thích vì sao không nên biến mọi đầu vào sai thành số 0.

### Bài 4 — Lọc ngày không cast cột

Giả sử có `visits(visit_id INTEGER, visited_at TIMESTAMP)` và chỉ mục trên `visited_at`. Viết truy vấn lấy tất cả lượt trong ngày 14/11/2026 bằng khoảng nửa mở thay vì `CAST(visited_at AS DATE)`.

### Bài 5 — Ngày ở hai múi giờ

Với `TIMESTAMPTZ '2026-11-14 00:30:00+07'`, kết quả `CAST(... AS DATE)` ở phiên PostgreSQL đặt `UTC` là ngày nào? Ở `Asia/Ho_Chi_Minh` là ngày nào? Cách nào diễn đạt “ngày tại Việt Nam” bất kể múi giờ phiên?

### Bài 6 — Tổng hợp dữ liệu import

Với bảng `incoming_amounts` ở mục 9, tính tổng các khoản tiền hợp lệ; cho biết số dòng `valid`, `invalid`, `missing`. Nêu vì sao nên lưu số tiền đã phân tích thành `NUMERIC`, không giữ ở `TEXT` để tính báo cáo lâu dài.

<details>
<summary>Gợi ý lời giải</summary>

**Bài 1:** `a = 3.00`, vì `7 / 2` là phép chia nguyên trong PostgreSQL, phần lẻ đã mất trước khi cast. `b = 3.50`, vì một toán hạng đã là `NUMERIC` trước phép chia.

**Bài 2:** Chọn `VARCHAR`/`TEXT` với quy tắc độ dài và hình thức phù hợp; cast sang `INTEGER` cho số `45` và làm mất các số 0 ở đầu.

**Bài 3:** `'120.50'` hợp lệ; `'abc'` sai cú pháp; `''` và `NULL` được coi là thiếu theo quy ước bài tập. Số 0 là một giá trị tiền hợp lệ, không thể dùng để che mọi dữ liệu sai.

**Bài 4:**

```sql
SELECT visit_id, visited_at
FROM visits
WHERE visited_at >= TIMESTAMP '2026-11-14 00:00:00'
  AND visited_at <  TIMESTAMP '2026-11-15 00:00:00';
```

**Bài 5:** Phiên UTC cho `2026-11-13`; phiên Việt Nam cho `2026-11-14`. Có thể cố định cách tính ngày:

```sql
SELECT CAST(
    TIMESTAMPTZ '2026-11-14 00:30:00+07'
        AT TIME ZONE 'Asia/Ho_Chi_Minh'
    AS DATE
) AS vietnam_date;
```

**Bài 6:** Có 3 dòng hợp lệ, 1 dòng sai và 2 dòng thiếu; tổng tiền hợp lệ bằng `424000.50`. Kiểu `NUMERIC` phục vụ phép toán số học và độ chính xác thập phân; `TEXT` không mang ngữ nghĩa tính tiền.

</details>

## 14. Nguyên tắc mang sang các bài SQL tiếp theo

**Chuyển đổi ngầm** là quyết định của hệ quản trị trong một ngữ cảnh biểu thức cụ thể; nó không bảo đảm mọi dữ liệu “trông đúng” sẽ được chuyển đúng. **Ép kiểu tường minh** bằng `CAST(expression AS target_type)` làm ý định của truy vấn rõ ràng, nhưng không bảo đảm dữ liệu nguồn hợp lệ, không ngăn mất độ chính xác và không tự giải quyết lỗi chuyển đổi.

Hãy chọn kiểu đúng với **ý nghĩa nghiệp vụ** từ khi thiết kế cột; làm sạch và xác minh dữ liệu tại **ranh giới nhập liệu**; cast **trước phép tính** khi cần đổi cách tính; phân biệt **chuyển kiểu** với **định dạng hiển thị**; và xét tác động của múi giờ, phạm vi số, độ dài chuỗi và chỉ mục trước khi đưa `CAST` vào truy vấn. Một phép cast được lựa chọn có chủ đích giúp SQL dễ đọc và giảm các sai lệch âm thầm trong dữ liệu.
