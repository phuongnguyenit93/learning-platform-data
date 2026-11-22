# CAST và chuyển đổi an toàn theo khả năng hệ quản trị

Trong SQL, dữ liệu được lưu theo **kiểu**: số nguyên, số thập phân, văn bản, ngày giờ, boolean, UUID, JSON và nhiều kiểu khác. Một giá trị nhập từ CSV có thể là chuỗi `'1250.75'`, trong khi phép tính doanh thu cần giá trị số `1250.75`; dữ liệu `'2026-07-01'` có thể là văn bản, trong khi thao tác so sánh ngày cần kiểu `DATE`. Việc **chuyển kiểu dữ liệu** (*type conversion*) giúp đưa giá trị từ biểu diễn nguồn sang kiểu mà biểu thức, cột đích hoặc ứng dụng cần sử dụng.

`CAST` là cách chuyển kiểu tường minh phổ biến của SQL:

```sql
CAST(expression AS target_type)
```

Nhưng **có cú pháp CAST không đồng nghĩa với chuyển đổi luôn thành công hoặc luôn an toàn**. Giá trị `'abc'` không thể diễn giải thành một số nguyên hợp lệ theo quy tắc thông thường; `2147483648` vượt giới hạn của số nguyên 32-bit; `'2026-02-30'` không phải ngày lịch hợp lệ; và việc chuyển một số tiền nhiều chữ số sang kiểu số quá nhỏ có thể mất thông tin hoặc gây lỗi.

Các DBMS xử lý những trường hợp đó theo **khả năng và quy tắc riêng**: có hệ phát lỗi ngay, có hệ hỗ trợ `TRY_CAST` hoặc `SAFE_CAST` để trả `NULL` khi chuyển đổi thất bại, và có hệ chuyển đổi khá “dễ dãi”, đôi lúc trả `0` hoặc giá trị bị cắt với cảnh báo. Vì thế, chuyển đổi an toàn là **chọn đúng kiểu đích, kiểm soát đầu vào, phát hiện lỗi, xử lý dữ liệu thiếu và bảo vệ ý nghĩa nghiệp vụ** — không đơn giản là thêm từ khóa CAST.

Bài học này tập trung vào PostgreSQL, Microsoft SQL Server, MySQL, Oracle Database và nêu thêm BigQuery, SQLite để thấy rõ khác biệt. Ví dụ chính dùng **PostgreSQL** với bảng tạm, còn ví dụ theo DBMS được ghi nhãn riêng; **không nên chép nguyên truy vấn của hệ này sang hệ khác mà không kiểm tra cú pháp và quy tắc chuyển đổi**.

## 1. Vì sao cần chuyển kiểu?

Ba tình huống quen thuộc:

1. **Nhập dữ liệu từ bên ngoài:** CSV, API và biểu mẫu có thể gửi số hoặc ngày dưới dạng chuỗi; trước khi lưu vào `INTEGER`, `NUMERIC` hay `DATE` cần phân tích và xác nhận.
2. **Tạo biểu thức đầu ra:** muốn hiển thị số ở dạng văn bản, ghép mã hoặc chuẩn hóa giá trị cho một báo cáo.
3. **Ghép dữ liệu từ nhiều nguồn:** cột tham chiếu ở một bảng đang là số, bảng khác là văn bản; cần chuyển về cùng miền kiểu sau khi xác định quy ước dữ liệu.

Ví dụ PostgreSQL:

```sql
SELECT
    CAST('42' AS INTEGER) AS quantity,
    CAST('1250.75' AS NUMERIC(12, 2)) AS amount,
    CAST('2026-07-01' AS DATE) AS order_date;
```

Ba biểu thức lần lượt tạo giá trị **số nguyên**, **số thập phân có giới hạn precision/scale** và **ngày**. Đầu vào là chuỗi, nhưng giá trị được trả về có kiểu mới.

### 1.1. Chuyển kiểu khác thay đổi dữ liệu nguồn

Một câu SELECT:

```sql
SELECT CAST(raw_quantity AS INTEGER) AS quantity
FROM staging_import;
```

chỉ tạo ra **biểu thức kết quả**, không tự cập nhật `staging_import.raw_quantity`. Nếu muốn lưu giá trị sang bảng đích hoặc sửa cột hiện có, cần thao tác ghi riêng như `INSERT ... SELECT`, `UPDATE`, hoặc migration `ALTER TABLE`. Khi thao tác ghi, ràng buộc của cột đích như `NOT NULL`, `CHECK`, `UNIQUE` vẫn phải được đáp ứng.

### 1.2. Chuyển đổi tường minh và ngầm định

| Loại | Người viết SQL nhìn thấy gì? | Nguy cơ |
| --- | --- | --- |
| **Tường minh** | `CAST(raw_text AS INTEGER)` hoặc cú pháp tương đương | Có thể lỗi, cắt ngắn, làm tròn hoặc mất thông tin |
| **Ngầm định** | DBMS tự chuyển kiểu khi tính toán, so sánh hoặc gán cột | Ít lộ rõ ý định, phụ thuộc thứ tự ưu tiên kiểu và DBMS |
| **Chuyển đổi có kiểm soát lỗi** | `TRY_CAST`, `TRY_CONVERT`, `SAFE_CAST` hoặc mẫu xử lý riêng | Có thể trả NULL và che mất lý do lỗi nếu không ghi nhận |

Ví dụ điều kiện `number_column = '42'` có thể được một DBMS diễn giải bằng cách chuyển chuỗi sang số, nhưng hệ khác hoặc trường hợp khác có thể không cho phép hoặc áp dụng quy tắc khác. Để SQL rõ ràng và giảm phụ thuộc dialect, **bind tham số đúng kiểu** hoặc chuyển đổi tường minh ở nơi thật sự cần thiết.

## 2. CAST: cú pháp cơ bản và kiểu đích

Cú pháp chuẩn:

```sql
CAST(expression AS data_type)
```

Một số ví dụ trong PostgreSQL:

```sql
SELECT
    CAST('123' AS INTEGER) AS int_value,
    CAST('123.45' AS NUMERIC(10, 2)) AS decimal_value,
    CAST(123 AS TEXT) AS text_value,
    CAST('2026-07-01' AS DATE) AS date_value,
    CAST(NULL AS INTEGER) AS typed_null;
```

`CAST(NULL AS INTEGER)` vẫn cho giá trị **NULL**, nhưng biểu thức có kiểu INTEGER để DBMS giải quyết kiểu dữ liệu đầu ra. `CAST` không tự biến NULL thành 0, chuỗi rỗng hoặc giá trị mặc định.

### 2.1. Cú pháp khác biệt theo DBMS

| Hệ quản trị | Ví dụ chuyển kiểu | Ghi chú |
| --- | --- | --- |
| PostgreSQL | `CAST('42' AS INTEGER)` hoặc `'42'::INTEGER` | `::` là cú pháp rút gọn quen thuộc của PostgreSQL |
| SQL Server | `CAST('42' AS INT)` hoặc `CONVERT(INT, '42')` | `CONVERT` có tham số *style* hữu ích với ngày giờ và định dạng |
| MySQL | `CAST('42' AS SIGNED)` | Các tên kiểu được CAST chấp nhận có khác biệt; số không dấu dùng `UNSIGNED` |
| Oracle | `CAST('42' AS NUMBER(10))` | Có các hàm `TO_NUMBER`, `TO_DATE`, `TO_CHAR` với format model |
| BigQuery (GoogleSQL) | `CAST('42' AS INT64)` | Có `SAFE_CAST` cho một số chuyển đổi lỗi lúc chạy |
| SQLite | `CAST('42' AS INTEGER)` | Kiểu dữ liệu linh hoạt và hành vi chuyển đổi có thể khá dễ dãi |

Tên kiểu số nguyên, chuỗi, ngày và cú pháp ép kiểu **không thống nhất tuyệt đối**. Ví dụ `INT64` của BigQuery không phải tên kiểu `BIGINT` được mọi hệ chấp nhận; `SIGNED` trong cú pháp CAST của MySQL cũng không phải cách viết chung của SQL chuẩn.

### 2.2. Một số lựa chọn kiểu đích thường gặp

| Dữ liệu cần biểu diễn | Kiểu đích nên cân nhắc | Vì sao |
| --- | --- | --- |
| Số lượng đếm | `INTEGER`, `BIGINT` hoặc kiểu nguyên phù hợp | Không cần phần thập phân; chú ý giới hạn miền số |
| Số tiền | `NUMERIC(p,s)` / `DECIMAL(p,s)` | Hỗ trợ thập phân chính xác theo cấu hình, tránh sai số nhị phân của FLOAT cho các phép tính tiền |
| Ngày không có giờ | `DATE` | Diễn đạt ngày lịch, không gắn giờ |
| Mốc thời gian | Kiểu `TIMESTAMP`/`TIMESTAMPTZ` hoặc tương đương | Cần thống nhất ý nghĩa múi giờ và cách hiển thị |
| Mã chứa số 0 đầu | `TEXT` / `VARCHAR` | Giữ nguyên mã như `00123`; không phải mọi chuỗi chữ số đều là số để tính |
| Trạng thái đúng/sai | Kiểu boolean tương ứng DBMS | Phân biệt `FALSE` với `NULL` nếu có trạng thái chưa biết |

**Chọn kiểu phải dựa trên ý nghĩa dữ liệu, không chỉ dựa trên hình thức chuỗi.** Mã khách hàng `'000123'` có vẻ toàn chữ số nhưng chuyển thành INTEGER sẽ mất ba số 0 đầu. Nếu số 0 đầu là một phần mã nghiệp vụ, không được ép kiểu sang số.

## 3. Bộ dữ liệu thực hành: dữ liệu ngoài không hoàn hảo

Trong PostgreSQL, tạo một bảng tạm chứa dữ liệu nguyên gốc như nhận từ CSV hoặc API:

```sql
CREATE TEMP TABLE demo_import_staging (
    source_row INTEGER PRIMARY KEY,
    raw_quantity TEXT NULL,
    raw_amount TEXT NULL,
    raw_order_date TEXT NULL,
    raw_customer_code TEXT NULL
);

INSERT INTO demo_import_staging
    (source_row, raw_quantity, raw_amount, raw_order_date, raw_customer_code)
VALUES
    (1, '12',         '1200.50',           '2026-07-01', '000123'),
    (2, '0',          '0.00',              '2026-07-02', '000124'),
    (3, 'abc',        '12x',               '2026-02-30', '000125'),
    (4, NULL,         NULL,               NULL,         NULL),
    (5, '2147483648', '1000000000000.00',  '2026-07-03', '000126'),
    (6, ' 7 ',        '1,234.56',          '07/04/2026', '000127'),
    (7, '-2',         '-5.00',             '2026-07-04', '000128');
```

| Dòng | raw_quantity | raw_amount | raw_order_date | Vấn đề cần xem xét |
| ---: | --- | --- | --- | --- |
| 1 | `'12'` | `'1200.50'` | `'2026-07-01'` | Dữ liệu đúng định dạng dự kiến |
| 2 | `'0'` | `'0.00'` | `'2026-07-02'` | Giá trị 0 hợp lệ, không phải thiếu |
| 3 | `'abc'` | `'12x'` | `'2026-02-30'` | Sai định dạng số và ngày không tồn tại |
| 4 | NULL | NULL | NULL | Dữ liệu thiếu; khác dữ liệu có mặt nhưng sai |
| 5 | `'2147483648'` | `'1000000000000.00'` | `'2026-07-03'` | Có hình thức số nhưng vượt giới hạn kiểu đích dự kiến |
| 6 | `' 7 '` | `'1,234.56'` | `'07/04/2026'` | Khoảng trắng, dấu phân tách và ngày dễ mơ hồ |
| 7 | `'-2'` | `'-5.00'` | `'2026-07-04'` | Chuyển kiểu được, nhưng có thể vi phạm quy tắc nghiệp vụ |

Các giá trị trong bảng được **lưu là TEXT**, vì đây là dữ liệu đầu vào chưa xác thực. Dữ liệu thô vẫn có thể được xem lại để điều tra lỗi, thay vì bị biến thành `0` hay NULL không phân biệt nguyên nhân ngay từ bước nhận.

### 3.1. Thử CAST thường và quan sát nguy cơ

```sql
-- PostgreSQL: hợp lệ.
SELECT CAST(raw_quantity AS INTEGER) AS quantity
FROM demo_import_staging
WHERE source_row = 1;
-- 12
```

```sql
-- PostgreSQL: lỗi vì 'abc' không biểu diễn số nguyên hợp lệ.
SELECT CAST(raw_quantity AS INTEGER) AS quantity
FROM demo_import_staging
WHERE source_row = 3;
```

```sql
-- PostgreSQL: lỗi vì vượt miền INTEGER 32-bit.
SELECT CAST(raw_quantity AS INTEGER) AS quantity
FROM demo_import_staging
WHERE source_row = 5;
```

`2147483648` là một chuỗi chữ số hợp lệ về **hình thức**, nhưng lớn hơn giới hạn tối đa `2147483647` của INTEGER có dấu 32-bit trong PostgreSQL. Đổi sang `BIGINT` có thể giải quyết trường hợp cụ thể nếu miền nghiệp vụ cho phép, nhưng không phải mọi chuỗi số dài đều hợp lệ trong BIGINT.

```sql
-- PostgreSQL: ngày 30 tháng 2 không tồn tại.
SELECT CAST(raw_order_date AS DATE)
FROM demo_import_staging
WHERE source_row = 3;
```

Câu lệnh gặp lỗi chuyển đổi, không được coi ngày 30/2 là một ngày hợp lệ. Tùy hàm parse và DBMS khác, dữ liệu ngày sai có thể bị từ chối, chuyển đổi về giá trị đặc biệt hoặc có quy tắc xử lý khác; **không giả định CAST và các hàm parse ngày luôn giống nhau**.

## 4. “An toàn” khi chuyển kiểu có nhiều tầng

Chuyển đổi an toàn không chỉ nghĩa là “không ném exception”. Cần phân biệt:

1. **Hợp lệ về cú pháp:** có thể đọc `'12'` thành số, `'2026-07-01'` thành DATE?
2. **Hợp lệ về miền kiểu:** giá trị có nằm trong giới hạn INTEGER, DECIMAL(p,s) và độ dài chuỗi không?
3. **Hợp lệ theo nghiệp vụ:** quantity có cần lớn hơn 0? Tổng tiền có được âm không?
4. **Không mất thông tin quan trọng:** có bị cắt chuỗi, đổi số 0 đầu, làm tròn quá mức hoặc đổi múi giờ không?
5. **Có phát hiện và ghi nhận lỗi:** khi parse thất bại, có biết **dòng nào**, **trường nào**, **giá trị gốc gì** và **vì sao** không?

| Đầu vào | Chuyển thành công về mặt kiểu? | Có thể chấp nhận trong nghiệp vụ? |
| --- | --- | --- |
| `'0'` → INTEGER 0 | Có | Có thể, nếu số lượng bằng 0 hợp lệ |
| `'-2'` → INTEGER -2 | Có | Không nếu quantity phải không âm |
| `'00123'` → INTEGER 123 | Có | Không nếu đây là mã phải giữ số 0 đầu |
| `'1.999'` → DECIMAL(10,2) | Tùy DBMS và quy tắc làm tròn | Cần quyết định được phép làm tròn hay không |
| `'2026-02-30'` → DATE | Không phải ngày hợp lệ | Không |
| `'abc'` → INTEGER | Không phải số nguyên hợp lệ | Không |

Một chức năng “thử chuyển đổi” trả NULL giúp tránh một số lỗi runtime, nhưng **NULL kết quả không nói rõ đầu vào thật sự thiếu hay chuyển đổi thất bại**. Đó là lý do pipeline nhập liệu nên lưu giá trị thô và một trạng thái chất lượng riêng.

## 5. PostgreSQL: CAST chặt chẽ, `::` và cách xử lý lỗi

PostgreSQL hỗ trợ cả hai cách:

```sql
SELECT
    CAST('125' AS INTEGER) AS a,
    '125'::INTEGER AS b,
    CAST('2026-07-01' AS DATE) AS d,
    '2026-07-01'::DATE AS d2;
```

`::` là cách viết ngắn của phép ép kiểu theo cú pháp PostgreSQL. Với người học SQL đa hệ quản trị, `CAST(... AS ...)` thường dễ chuyển ý tưởng sang hệ khác hơn, dù tên kiểu và ngữ nghĩa vẫn có khác biệt.

### 5.1. CAST lỗi thường làm cả truy vấn không hoàn tất

PostgreSQL không có một hàm `TRY_CAST` phổ thông mặc định tương đương trực tiếp SQL Server. Nếu một giá trị sai xuất hiện trong biểu thức CAST và được thực thi, hệ quản trị có thể báo lỗi, khiến câu truy vấn không trả được toàn bộ tập kết quả mong muốn. Một phép WHERE khác không phải lúc nào cũng là hàng rào bảo đảm an toàn do bộ tối ưu có thể tổ chức biểu thức theo cách khác.

Không nên viết kiểu:

```sql
-- Không an toàn để trông chờ WHERE luôn chặn giá trị sai trước CAST:
SELECT raw_quantity::INTEGER
FROM demo_import_staging
WHERE raw_quantity ~ '^[0-9]+$';
```

Ngay cả khi biểu thức chính quy chỉ nhận chữ số, nó **không kiểm tra tràn miền số**: dòng 5 vẫn là chữ số nhưng không ép được thành INTEGER. Ngoài ra, các phép lọc và phép tính có thể được DBMS sắp xếp, đẩy hoặc rút gọn khi tối ưu; điều kiện kiểm tra trước khi CAST phải được thiết kế một cách có căn cứ.

### 5.2. PostgreSQL 16+: `pg_input_is_valid`

PostgreSQL 16 trở lên có hàm hỗ trợ kiểm tra khả năng nhập một giá trị văn bản cho kiểu được chỉ định: **`pg_input_is_valid(text, type_name)`**.

```sql
SELECT
    source_row,
    raw_quantity,
    pg_input_is_valid(raw_quantity, 'integer') AS can_parse_integer
FROM demo_import_staging
ORDER BY source_row;
```

Trên dữ liệu mẫu, `'12'`, `'0'`, `' 7 '` và `'-2'` có thể được nhập làm INTEGER; `'abc'` và `'2147483648'` không hợp lệ cho INTEGER. Đầu vào NULL cần được phân biệt riêng, không coi kết quả kiểm tra NULL là một phản hồi lỗi định dạng.

Có thể đưa điều kiện kiểm tra vào một **CASE**:

```sql
SELECT
    source_row,
    raw_quantity,
    CASE
        WHEN raw_quantity IS NULL
             OR BTRIM(raw_quantity) = ''
            THEN NULL
        WHEN pg_input_is_valid(BTRIM(raw_quantity), 'integer')
            THEN BTRIM(raw_quantity)::INTEGER
        ELSE NULL
    END AS quantity
FROM demo_import_staging
ORDER BY source_row;
```

Với kiểu có cơ chế báo lỗi mềm được PostgreSQL hỗ trợ, `pg_input_is_valid` giúp tránh lỗi do văn bản số không hợp lệ hoặc vượt miền số; CASE chỉ ép kiểu ở nhánh đã xác nhận. **Hàm này phụ thuộc phiên bản và khả năng báo lỗi mềm của input function từng kiểu**: với các kiểu/extension không hỗ trợ, nó có thể vẫn phát lỗi thay vì chỉ trả FALSE. Cần kiểm tra loại dữ liệu đang sử dụng và tài liệu phiên bản DBMS thực tế.

Nếu đầu vào là ngày dạng ISO, có thể kết hợp **chính sách định dạng chính xác** và kiểm tra khả năng nhập DATE:

```sql
SELECT
    source_row,
    raw_order_date,
    CASE
        WHEN raw_order_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
         AND pg_input_is_valid(raw_order_date, 'date')
        THEN raw_order_date::DATE
        ELSE NULL
    END AS parsed_date
FROM demo_import_staging;
```

Biểu thức chính quy xác định định dạng `YYYY-MM-DD`; kiểm tra kiểu DATE giúp từ chối **ngày lịch không tồn tại** mà một regex hình thức đơn thuần không phát hiện. Các ứng dụng yêu cầu xử lý ngày/giờ quốc tế vẫn phải có quy tắc múi giờ và định dạng đầu vào khác nhau khi cần.

### 5.3. Phiên bản PostgreSQL cũ và xử lý ngoại lệ

Trên phiên bản chưa có `pg_input_is_valid`, có thể:

- Kiểm tra dữ liệu tại tầng ứng dụng trước khi bind vào cột kiểu đích.
- Chuẩn hóa và kiểm tra biểu thức định dạng, **kèm kiểm tra miền giá trị**; không tin regex một mình.
- Dùng quy trình staging và một hàm PL/pgSQL bắt các lỗi chuyển đổi cụ thể khi thực sự cần chuyển đổi không làm gián đoạn cả lô.

Ví dụ về một hàm minh họa, **chỉ dành cho PostgreSQL**:

```sql
CREATE OR REPLACE FUNCTION demo_try_integer(p_text TEXT)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_text IS NULL OR BTRIM(p_text) = '' THEN
        RETURN NULL;
    END IF;

    RETURN BTRIM(p_text)::INTEGER;
EXCEPTION
    WHEN invalid_text_representation OR numeric_value_out_of_range
    THEN RETURN NULL;
END;
$$;

SELECT
    source_row,
    raw_quantity,
    demo_try_integer(raw_quantity) AS quantity
FROM demo_import_staging
ORDER BY source_row;
```

Hàm bắt lỗi chữ số không hợp lệ và tràn số; các lỗi khác không được nuốt mặc định. Trong mã thực tế, phạm vi exception cần được chọn đúng ý định; bắt mọi lỗi một cách vô điều kiện dễ che giấu vấn đề hệ thống. Gọi hàm PL/pgSQL bắt exception trên lượng dữ liệu rất lớn cũng có chi phí, nên phải đánh giá với quy mô và quy trình nhập thực tế. Hàm trên được tạo trong schema hiện hành; nếu chỉ dùng để học, có thể xóa bằng `DROP FUNCTION demo_try_integer(TEXT);`.

### 5.4. `to_date` và `to_timestamp` không thay thế mọi kiểm tra

PostgreSQL còn có các hàm parse theo format:

```sql
SELECT TO_DATE('2026-07-01', 'YYYY-MM-DD');
```

Hàm format hữu ích khi đầu vào có một mẫu xác định. Tuy nhiên, việc parse theo mẫu có thể có quy tắc bỏ qua ký tự hoặc chuẩn hóa khác so với CAST DATE; không nên mặc định chỉ cần `TO_DATE(raw, 'YYYY-MM-DD')` là mọi đầu vào sai đều sẽ bị từ chối đúng theo hợp đồng nguồn.

Khi nghiệp vụ yêu cầu ngày ISO chuẩn, hãy **kiểm tra đúng định dạng và tính hợp lệ của ngày**; khi xử lý mốc thời gian, phải xác định có offset/múi giờ không. Tên hàm parse và format model có thể khác giữa các DBMS.

## 6. SQL Server: `TRY_CAST`, `TRY_CONVERT` và style

Microsoft SQL Server hỗ trợ hai cơ chế giúp chuyển đổi có kiểm soát:

```sql
SELECT
    TRY_CAST('123' AS INT) AS valid_integer,    -- 123
    TRY_CAST('abc' AS INT) AS invalid_integer,  -- NULL
    TRY_CAST('2147483648' AS INT) AS overflowed;-- NULL
```

`TRY_CAST` thường trả NULL khi chuyển đổi được phép nhưng **giá trị đầu vào không thể chuyển hợp lệ**. Đây là khác biệt với CAST thường, nơi lỗi chuyển đổi có thể chặn truy vấn.

**Không hiểu TRY_CAST là lời hứa không bao giờ phát lỗi:** SQL Server vẫn có thể báo lỗi nếu yêu cầu chuyển đổi **bị cấm rõ ràng** giữa hai kiểu; một số trường hợp đầu vào hoặc giới hạn kích thước cũng có hạn chế riêng.

### 6.1. `TRY_CONVERT` khi cần chọn kiểu ngày

SQL Server có `TRY_CONVERT(data_type, expression, style)`:

```sql
SELECT
    TRY_CONVERT(DATE, '2026-07-01', 23) AS valid_date,
    TRY_CONVERT(DATE, '2026-02-30', 23) AS invalid_date;
```

Style `23` biểu diễn dạng `yyyy-mm-dd` trong SQL Server. Kết quả đầu là ngày hợp lệ, trường hợp ngày không tồn tại cho NULL khi chuyển đổi thất bại.

Một ví dụ với chuỗi thời điểm ISO 8601:

```sql
SELECT TRY_CONVERT(
    DATETIME2,
    '2026-07-01T14:30:00',
    126
) AS parsed_timestamp;
```

Style `126` được dùng cho dạng ISO 8601 liên quan. Cần chọn kiểu có hoặc không có offset phù hợp với dữ liệu thật; `DATETIME2` không mang ý nghĩa offset như `DATETIMEOFFSET`.

### 6.2. Phân biệt dữ liệu rỗng trước khi TRY_CAST

Một số quy tắc chuyển kiểu trong SQL Server có thể biến **chuỗi rỗng** thành một giá trị số hoặc ngày mặc định thay vì trả NULL. Vì vậy, không nên mặc định `TRY_CAST(raw AS INT) IS NULL` sẽ phát hiện **mọi** trường hợp trường nhập trống.

Nếu chính sách sản phẩm coi chuỗi rỗng hoặc chỉ chứa khoảng trắng là **thiếu dữ liệu**, hãy chuẩn hóa trước:

```sql
-- SQL Server 2017+ hỗ trợ TRIM.
SELECT
    TRY_CONVERT(INT, NULLIF(TRIM(raw_quantity), ''))
        AS quantity,
    TRY_CONVERT(DECIMAL(12, 2), NULLIF(TRIM(raw_amount), ''))
        AS amount,
    TRY_CONVERT(DATE, NULLIF(TRIM(raw_order_date), ''), 23)
        AS order_date
FROM import_staging;
```

`import_staging` trong đoạn T-SQL là bảng nguồn giả định trên SQL Server, không phải bảng tạm PostgreSQL đã tạo ở mục 3. `NULLIF(TRIM(raw_quantity), '')` đổi chuỗi đã trim thành NULL nếu rỗng; sau đó TRY_CONVERT xử lý giá trị có mặt. Với phiên bản cũ không có TRIM, SQL Server có thể dùng tổ hợp `LTRIM(RTRIM(...))`.

### 6.3. TRY_CAST không tự nói vì sao giá trị NULL

Giả sử nhập ba dòng: `NULL`, `'abc'`, `'0'`. Với SQL Server, sau khi chuẩn hóa:

```sql
SELECT
    raw_quantity,
    CASE
        WHEN raw_quantity IS NULL THEN 'MISSING'
        WHEN TRIM(raw_quantity) = '' THEN 'BLANK'
        WHEN TRY_CONVERT(INT, raw_quantity) IS NULL THEN 'INVALID'
        ELSE 'VALID'
    END AS parse_state
FROM import_staging;
```

Các nhãn `MISSING`, `BLANK`, `INVALID`, `VALID` giúp phân biệt **thiếu giá trị**, **trường rỗng**, **đầu vào sai** và **giá trị hợp lệ**. Đây mới là thông tin cần thiết để xử lý lỗi nhập liệu; chỉ dùng `COALESCE(TRY_CAST(raw AS INT), 0)` sẽ biến cả dữ liệu thiếu và dữ liệu sai thành số 0.

## 7. Oracle: `TO_NUMBER`, `TO_DATE` và xử lý lỗi chuyển đổi

Oracle hỗ trợ `CAST` và các hàm chuyển kiểu chuyên dụng:

```sql
SELECT
    CAST('42' AS NUMBER(10)) AS quantity,
    TO_NUMBER('1250.75', '9999999D99',
              'NLS_NUMERIC_CHARACTERS=''.,''') AS amount,
    TO_DATE('2026-07-01', 'YYYY-MM-DD') AS order_date
FROM dual;
```

Trong Oracle, định dạng số có thể chịu ảnh hưởng cấu hình **NLS**. Dấu thập phân `.` hoặc `,` cần được giải thích theo quy ước nguồn. `D` là ký hiệu dấu thập phân theo NLS trong format model của `TO_NUMBER`; tham số `NLS_NUMERIC_CHARACTERS` có thể giúp quy định rõ dấu thập phân và dấu nhóm cho biểu thức chuyển đổi.

### 7.1. `DEFAULT ... ON CONVERSION ERROR`

Oracle Database từ 12.2 hỗ trợ lựa chọn trả một giá trị dự phòng cho một số hàm chuyển đổi khi quá trình chuyển đổi giá trị ký tự gặp lỗi:

```sql
SELECT
    TO_NUMBER('abc' DEFAULT NULL ON CONVERSION ERROR)
        AS invalid_number,
    TO_DATE('2026-02-30' DEFAULT NULL ON CONVERSION ERROR,
            'FXYYYY-MM-DD')
        AS invalid_date
FROM dual;
```

Hai giá trị không thể chuyển theo quy tắc được chỉ định sẽ cho NULL thay vì lỗi chuyển đổi từ đầu vào ký tự. Tiền tố `FX` trong format model ngày của Oracle yêu cầu đối chiếu mẫu chặt chẽ hơn trong các tình huống định dạng liên quan.

Lựa chọn `DEFAULT ... ON CONVERSION ERROR` **không che mọi lỗi có thể xảy ra khi đánh giá biểu thức nguồn**. Nếu bản thân biểu thức truyền vào hàm phát lỗi trước khi chuyển đổi, cơ chế dự phòng không nhất thiết xử lý được. Ngoài ra, chính giá trị default phải có kiểu/định dạng phù hợp.

Nếu chương trình muốn phân biệt dữ liệu thiếu và lỗi parse, Oracle có `VALIDATE_CONVERSION` trên các phiên bản hỗ trợ để kiểm tra giá trị có thể chuyển sang kiểu đích mà không cần chuyển và lưu ngay. Khi sử dụng, cần chọn format model/NLS tương ứng với hàm chuyển đổi đích, và kiểm tra trường hợp NULL theo chính sách của ứng dụng.

### 7.2. Chuỗi rỗng trong Oracle khác PostgreSQL

Trong các kiểu ký tự thông dụng như `VARCHAR2`, Oracle hiện xử lý chuỗi rỗng `''` như `NULL`. Vì vậy, một quy trình nhập liệu dựa trên sự khác nhau giữa `''` và NULL ở PostgreSQL/MySQL có thể thay đổi nghĩa khi chạy trên Oracle.

Không có quy tắc chuyển đổi an toàn toàn cục nếu không xác định DBMS đích và miền dữ liệu. Bên cạnh `CAST`/`TO_*`, cần kiểm tra cách Oracle xử lý dấu cách, NLS, chuỗi rỗng và định dạng ngày.

## 8. MySQL: CAST có thể chuyển đổi kèm warning hoặc giá trị mặc định

MySQL hỗ trợ CAST nhưng tên kiểu đích có đặc thù:

```sql
SELECT
    CAST('42' AS SIGNED) AS signed_value,
    CAST('42' AS UNSIGNED) AS unsigned_value,
    CAST('1250.75' AS DECIMAL(12, 2)) AS amount,
    CAST('2026-07-01' AS DATE) AS order_date;
```

**Không mặc định MySQL sẽ phát lỗi khi đầu vào không phải số hợp lệ**, đặc biệt trong biểu thức SELECT. Một số chuyển đổi chuỗi sang số của MySQL có thể dùng **phần tiền tố số** và sinh cảnh báo, hoặc cho giá trị 0 khi không tìm được phần số phù hợp; hành vi chính xác còn tùy kiểu đích, ngữ cảnh câu lệnh, `sql_mode` và phiên bản.

Ví dụ cần cảnh giác:

```sql
-- MySQL: cần kiểm tra kết quả và warnings,
-- không giả định hai biểu thức đều phát lỗi giống PostgreSQL.
SELECT
    CAST('12x' AS UNSIGNED) AS maybe_twelve,
    CAST('abc' AS UNSIGNED) AS maybe_zero;
```

Khi cần phát hiện warning trong môi trường thử nghiệm, có thể dùng:

```sql
SHOW WARNINGS;
```

Warning cho thấy phép chuyển có thể không phản ánh đúng giá trị gốc; **một kết quả 0 không chứng minh người dùng đã nhập số 0**. Hãy phân biệt `raw = '0'` với `raw = 'abc'` bằng cách kiểm tra dữ liệu trước khi chuyển.

### 8.1. Không có một TRY_CAST phổ thông như SQL Server

Trong MySQL, không nên giả định có hàm chuẩn `TRY_CAST` hoặc `SAFE_CAST` hoạt động giống SQL Server/BigQuery. Chiến lược thực tế có thể là:

1. Chuẩn hóa văn bản theo hợp đồng nguồn (khoảng trắng, dấu thập phân).
2. Kiểm tra **cú pháp** đúng kiểu bằng biểu thức phù hợp.
3. Kiểm tra **miền số** và ngày lịch hợp lệ, không chỉ kiểm tra có chữ số.
4. CAST có chủ đích và quan sát warning/error của ngữ cảnh truy vấn.
5. Đưa giá trị không hợp lệ vào khu vực lỗi hoặc xử lý ở tầng ứng dụng thay vì âm thầm biến thành 0.

Biểu thức chính quy chỉ kiểm tra **hình thức**. Ví dụ `'99999999999999999999999'` vẫn là chữ số nhưng có thể vượt kiểu số đích; `'2026-02-30'` khớp mẫu `YYYY-MM-DD` nhưng là ngày không tồn tại.

### 8.2. Hàm ngày có format không phải phép kiểm tra hoàn chỉnh

MySQL có các hàm như `STR_TO_DATE` để phân tích ngày theo định dạng:

```sql
-- MySQL: ý tưởng phân tích ngày theo định dạng xác định.
SELECT STR_TO_DATE('2026-07-01', '%Y-%m-%d');
```

Việc chấp nhận giá trị ngày không hợp lệ và kiểu cảnh báo/lỗi của MySQL đã thay đổi qua các phiên bản và có thể chịu tác động của chế độ SQL. **Không suy luận rằng mọi giá trị không hợp lệ đều luôn được trả NULL**; nếu nghiệp vụ cần kiểm tra ngày nghiêm ngặt, phải xác minh hành vi phiên bản và kiểm soát đầu vào.

## 9. BigQuery và SQLite cho thấy “an toàn” không có một chuẩn duy nhất

### 9.1. BigQuery (GoogleSQL): `SAFE_CAST`

BigQuery hỗ trợ:

```sql
SELECT
    SAFE_CAST('42' AS INT64) AS valid_number,
    SAFE_CAST('abc' AS INT64) AS invalid_number,
    SAFE_CAST('2026-07-01' AS DATE) AS valid_date,
    SAFE_CAST('2026-02-30' AS DATE) AS invalid_date;
```

`SAFE_CAST` thường trả NULL khi chuyển đổi có thể biểu diễn về mặt kiểu nhưng **giá trị cụ thể gây lỗi lúc chạy**. Với kiểu không thể chuyển đổi hợp lệ ngay từ khâu phân tích, SQL có thể vẫn bị từ chối trước khi chạy; SAFE không làm mọi cặp kiểu bất kỳ trở nên hợp lệ.

Điểm quan trọng là kết quả NULL từ SAFE_CAST cần được kết hợp với giá trị gốc hoặc cột trạng thái nếu phải phân biệt dữ liệu thiếu với dữ liệu không parse được.

### 9.2. SQLite: ép kiểu khá dễ dãi, cần tự kiểm tra dữ liệu

SQLite sử dụng kiểu động và **type affinity**, nên hành vi CAST khác đáng kể so với PostgreSQL:

```sql
-- SQLite: ví dụ minh họa hành vi có thể gây bất ngờ.
SELECT
    CAST('123' AS INTEGER) AS valid_integer,
    CAST('abc' AS INTEGER) AS nonnumeric_to_zero,
    CAST('12x' AS INTEGER) AS numeric_prefix;
```

Với cách ép kiểu INTEGER của SQLite, `'abc'` có thể trở thành **0**, còn `'12x'` có thể trở thành **12** do lấy phần tiền tố có thể diễn giải. Điều này không đáp ứng yêu cầu “nhập sai phải được báo lỗi”.

Vì vậy, ngay cả khi bảng dùng chế độ `STRICT` ở những phiên bản SQLite hỗ trợ, **không nên dùng kết quả CAST đơn lẻ làm chứng cứ rằng văn bản gốc là số hợp lệ**. Kiểm tra định dạng và phạm vi ở tầng dữ liệu/ứng dụng, lưu raw input hoặc dùng cơ chế validation phù hợp.

### 9.3. Bảng đối chiếu các cơ chế

| DBMS | Chuyển kiểu thường | Cơ chế an toàn hoặc hướng xử lý đáng chú ý | Cần tránh hiểu sai |
| --- | --- | --- | --- |
| PostgreSQL | `CAST`, `::` | `pg_input_is_valid` (16+ cho kiểu hỗ trợ), CASE, PL/pgSQL exception, kiểm tra từ ứng dụng | Không có TRY_CAST phổ thông mặc định; regex không đủ kiểm tra miền |
| SQL Server | `CAST`, `CONVERT` | `TRY_CAST`, `TRY_CONVERT` với style | TRY không che mọi lỗi hoặc tự phân biệt chuỗi rỗng |
| Oracle | `CAST`, `TO_NUMBER`, `TO_DATE` | `DEFAULT ... ON CONVERSION ERROR` trên hàm hỗ trợ (12.2+), `VALIDATE_CONVERSION` | NLS, format model và chuỗi rỗng ảnh hưởng kết quả |
| MySQL | `CAST(... AS SIGNED/UNSIGNED/DECIMAL/DATE...)` | Kiểm tra trước, xử lý warning, chế độ SQL và hợp đồng nguồn | Một số phép ép có thể trả số từ phần tiền tố hoặc 0 |
| BigQuery | `CAST` | `SAFE_CAST` | Các cặp kiểu bất khả thi vẫn có thể lỗi khi phân tích |
| SQLite | `CAST` | Validation riêng ở ứng dụng/schema/dữ liệu | CAST dễ dãi có thể trả 0 hay lấy tiền tố số |

**Không có cú pháp “TRY_CAST chạy giống nhau trên mọi hệ”**. Khi dự án dùng ORM hoặc thư viện SQL đa dialect, vẫn cần thử nghiệm chuyển đổi theo hệ quản trị và phiên bản thực tế.

## 10. Số thập phân, tràn số và mất độ chính xác

### 10.1. Precision và scale của DECIMAL/NUMERIC

Kiểu `DECIMAL(p,s)` hoặc `NUMERIC(p,s)` thường dùng:

- **Precision p:** tổng số chữ số thập phân được phép.
- **Scale s:** số chữ số sau dấu thập phân.
- **p - s:** số chữ số tối đa trước dấu thập phân.

Ví dụ `NUMERIC(12,2)` lưu tối đa **10 chữ số trước dấu thập phân** và **2 chữ số sau dấu thập phân**, trong giới hạn kiểu cụ thể. Giá trị `1200.50` phù hợp, còn `1000000000000.00` (một nghìn tỷ) vượt miền của NUMERIC(12,2).

```sql
-- PostgreSQL: hợp lệ.
SELECT CAST('1200.50' AS NUMERIC(12, 2));

-- PostgreSQL: lỗi vì quá nhiều chữ số trước dấu thập phân.
-- SELECT CAST('1000000000000.00' AS NUMERIC(12, 2));
```

Việc ép giá trị có **nhiều chữ số sau dấu thập phân hơn s** có thể làm tròn theo quy tắc DBMS/kiểu; không nên giả định CAST luôn bảo toàn nguyên văn số ban đầu.

```sql
-- PostgreSQL: làm tròn đến hai chữ số sau dấu thập phân.
SELECT CAST('12.345' AS NUMERIC(12, 2));
```

Nếu yêu cầu nghiệp vụ là **từ chối số có quá hai chữ số thập phân**, không được chỉ CAST rồi thấy kết quả hợp lệ mà kết luận dữ liệu đầu vào hợp lệ. Cần kiểm tra scale của nguồn trước khi ép hoặc áp dụng quy tắc nghiệp vụ rõ ràng.

### 10.2. FLOAT không tương đương DECIMAL

Các kiểu số thực dấu phẩy động (`FLOAT`, `REAL`, `DOUBLE PRECISION`) thường sử dụng biểu diễn nhị phân xấp xỉ. Nhiều số thập phân như 0.1 không được biểu diễn chính xác trong nhị phân hữu hạn. Nếu chuyển FLOAT sang DECIMAL, kết quả còn phụ thuộc vào cách làm tròn hoặc số chữ số được biểu diễn ở bước chuyển.

Với bài toán tiền tệ cần độ chính xác theo đơn vị nhỏ, thường ưu tiên **DECIMAL/NUMERIC** hoặc số nguyên đại diện cho đơn vị nhỏ nhất theo quy ước, thay vì FLOAT. Dù chọn kiểu nào, **phép làm tròn ở ranh giới tính toán** cần được quyết định thống nhất.

### 10.3. INTEGER và giới hạn miền giá trị

Một chuỗi gồm toàn chữ số **không chứng minh** chuyển được sang INTEGER:

```sql
-- PostgreSQL: chuyển kiểu sẽ báo lỗi tràn số.
SELECT '2147483648'::INTEGER;

-- BIGINT có miền rộng hơn cho giá trị cụ thể này.
SELECT '2147483648'::BIGINT;
```

Giá trị âm cũng có thể chuyển hợp lệ sang INTEGER, nhưng có thể bị ràng buộc `CHECK (quantity >= 0)` từ chối khi ghi vào bảng đích. **Kiểm tra chuyển kiểu và kiểm tra nghiệp vụ là hai bước riêng**.

### 10.4. CAST sang chuỗi có độ dài giới hạn

```sql
-- PostgreSQL: ép kiểu tường minh sang VARCHAR(3)
-- có thể cắt bớt dữ liệu quá độ dài.
SELECT CAST('ABCDEF' AS VARCHAR(3));
```

Trong PostgreSQL, ép kiểu tường minh sang kiểu ký tự có giới hạn độ dài có thể dẫn đến **cắt bớt** thay vì báo lỗi, khác với một số ngữ cảnh gán vào cột. SQL Server cũng có các trường hợp chuyển sang VARCHAR(n) làm cắt chuỗi. Do đó, **không dùng CAST làm cơ chế kiểm tra độ dài** mà không biết quy tắc của DBMS.

Khi chuyển mã định danh, số điện thoại hoặc SKU, tránh cắt dữ liệu chỉ để vừa cột đích. Tốt hơn là kiểm tra chiều dài, giải thích lỗi và chọn kiểu/dung lượng có ý nghĩa.

## 11. Ngày giờ: định dạng, múi giờ và ngày lịch

Chuỗi `'2026-07-01'` có thể diễn giải rõ khi nguồn cam kết ISO `YYYY-MM-DD`. Nhưng `'07/04/2026'` có ít nhất hai cách hiểu phổ biến: **7 tháng 4** theo `DD/MM/YYYY` hoặc **4 tháng 7** theo `MM/DD/YYYY`.

Nếu dùng CAST ngày tự động, một DBMS có thể tham chiếu thiết lập ngôn ngữ, DATESTYLE hoặc NLS và trả kết quả khác với kỳ vọng. **Định dạng phải là phần của hợp đồng dữ liệu**, không nên phó mặc cho thiết lập session.

### 11.1. Ngày và timestamp không giống nhau

| Kiểu khái niệm | Ví dụ | Câu hỏi đang biểu diễn |
| --- | --- | --- |
| DATE | `2026-07-01` | Ngày lịch nào? |
| TIMESTAMP không múi giờ | `2026-07-01 09:30:00` | Thời điểm hiển thị theo đồng hồ địa phương nào? |
| TIMESTAMP có offset/múi giờ tương ứng | `2026-07-01T09:30:00+07:00` | Mốc thời gian nào trên trục thời gian? |

Trong PostgreSQL, chuyển từ `TIMESTAMPTZ` sang `DATE` có thể chịu ảnh hưởng **múi giờ phiên**, vì cùng một thời điểm UTC có thể thuộc hai ngày lịch khác nhau ở hai vùng.

```sql
-- PostgreSQL: quy định rõ ngày theo múi giờ nghiệp vụ.
SELECT
    (TIMESTAMPTZ '2026-07-01 00:30:00+07'
        AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
        AS business_date;
```

Nếu ứng dụng báo cáo doanh thu theo ngày tại Việt Nam, cần thống nhất ngày được tính theo múi giờ nào; không chỉ CAST timestamp sang DATE theo session mặc định rồi kỳ vọng mọi môi trường có cùng kết quả.

### 11.2. Lọc theo ngày: tránh ép kiểu cột trong WHERE khi có thể

Thay vì:

```sql
-- PostgreSQL: cách viết đơn giản nhưng có thể làm khó dùng index
-- và với TIMESTAMPTZ phụ thuộc timezone session.
SELECT order_id
FROM orders
WHERE created_at::DATE = DATE '2026-07-01';
```

nếu đã xác định rõ **ranh giới thời gian nghiệp vụ**, có thể dùng khoảng **nửa mở**:

```sql
-- Ví dụ PostgreSQL: một ngày theo offset +07.
SELECT order_id
FROM orders
WHERE created_at >= TIMESTAMPTZ '2026-07-01 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-07-02 00:00:00+07';
```

Cách viết này so sánh cột theo kiểu thời gian gốc, thường tạo điều kiện tốt hơn để sử dụng chỉ mục B-tree trên `created_at`, đồng thời tránh bỏ sót các hàng có phần mili/vi giây cuối ngày. Không dùng `BETWEEN start AND end` nếu `end` là nửa đêm ngày hôm sau: BETWEEN bao gồm cả hai đầu và có thể lấy nhầm bản ghi của ngày kế tiếp.

Ví dụ +07 phù hợp với ngày Việt Nam minh họa. Với các vùng có giờ mùa hè, **không mặc định mỗi ngày lịch luôn đúng 24 giờ theo UTC**; cần tính hai ranh giới theo múi giờ IANA của nghiệp vụ.

### 11.3. Không dùng chuyển đổi ngầm của ngày cho dữ liệu nguồn mơ hồ

Đối với đầu vào như `'07/04/2026'`, trước tiên phải xác định nguồn muốn nói `DD/MM/YYYY` hay `MM/DD/YYYY`, rồi dùng hàm parse và format model theo DBMS. Nếu nguồn không có hợp đồng hoặc lẫn nhiều định dạng, hãy **đưa vào hàng chờ làm sạch**, không đoán theo thiết lập môi trường sản xuất.

## 12. Chuyển đổi an toàn trong quy trình nhập liệu

Một quy trình nhập liệu đáng tin cậy có thể tách thành bốn bước:

```text
CSV / API / dữ liệu ngoài
         |
         v
Staging: lưu nguyên văn raw_* và định danh dòng nguồn
         |
         v
Chuẩn hóa theo quy ước nguồn (khoảng trắng, dấu phân cách, mã)
         |
         v
Kiểm tra định dạng + miền kiểu + ràng buộc nghiệp vụ
         |
         +---- hợp lệ ----> chuyển kiểu, INSERT vào bảng đích
         |
         +---- không hợp lệ ---> lưu lỗi, giữ dữ liệu gốc,
                                 không tự sửa thành 0 / giá trị giả
```

### 12.1. Giữ trạng thái để phân biệt thiếu và sai

Trong PostgreSQL 16+ có thể phân loại chuỗi số nguyên:

```sql
SELECT
    source_row,
    raw_quantity,
    CASE
        WHEN raw_quantity IS NULL THEN 'MISSING'
        WHEN BTRIM(raw_quantity) = '' THEN 'BLANK'
        WHEN NOT pg_input_is_valid(BTRIM(raw_quantity), 'integer')
            THEN 'INVALID_INTEGER'
        WHEN BTRIM(raw_quantity)::INTEGER < 0
            THEN 'NEGATIVE_NOT_ALLOWED'
        ELSE 'VALID'
    END AS quantity_state
FROM demo_import_staging
ORDER BY source_row;
```

Ý nghĩa:

- Dòng 1 có số lượng 12 → `VALID`.
- Dòng 2 có số lượng 0 → `VALID` **nếu quy tắc cho phép 0**.
- Dòng 3 chứa `abc` → `INVALID_INTEGER`.
- Dòng 4 NULL → `MISSING`.
- Dòng 5 vượt INTEGER → `INVALID_INTEGER`.
- Dòng 6 có `' 7 '` → `VALID` sau BTRIM.
- Dòng 7 có `-2` → `NEGATIVE_NOT_ALLOWED`.

Nếu nghiệp vụ yêu cầu quantity **lớn hơn 0**, đổi ràng buộc thành `<= 0` để cả dòng 2 bị loại. Không được mặc định số 0 luôn là lỗi chỉ vì nó thường đại diện “không có”.

### 12.2. Bảng đích có ràng buộc thích hợp

```sql
CREATE TEMP TABLE demo_imported_orders (
    source_row INTEGER PRIMARY KEY,
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    order_date DATE NOT NULL,
    customer_code TEXT NOT NULL
);
```

Các ràng buộc giữ tính đúng của bảng đích:

- `quantity` và `amount` không NULL, không âm.
- `order_date` phải là DATE được xác định.
- `customer_code` là TEXT để bảo toàn `'000123'`.
- `source_row` định danh một dòng nhập, hỗ trợ truy vết.

Không nên đưa toàn bộ dữ liệu thô vào bảng đích bằng một câu CAST không kiểm tra. Những dòng sai cần được xử lý riêng; một chuyển đổi thành công về kiểu chưa đủ để bảo đảm hợp lệ về miền nghiệp vụ.

### 12.3. Một truy vấn đưa dữ liệu hợp lệ vào bảng đích

Để minh họa rõ ý định mà không phụ thuộc một hàm TRY_CAST không có sẵn trong PostgreSQL, dưới đây dùng một **CTE** và dữ liệu PostgreSQL 16+ đã kiểm tra:

```sql
WITH checked AS (
    SELECT
        source_row,
        raw_quantity,
        raw_amount,
        raw_order_date,
        raw_customer_code,
        pg_input_is_valid(BTRIM(raw_quantity), 'integer') AS qty_ok,
        pg_input_is_valid(BTRIM(raw_amount), 'numeric') AS amount_ok,
        (
            raw_order_date ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
            AND pg_input_is_valid(raw_order_date, 'date')
        ) AS date_ok
    FROM demo_import_staging
)
SELECT
    source_row,
    CASE WHEN qty_ok THEN BTRIM(raw_quantity)::INTEGER END AS quantity,
    CASE WHEN amount_ok THEN BTRIM(raw_amount)::NUMERIC END AS amount,
    CASE WHEN date_ok THEN raw_order_date::DATE END AS order_date,
    raw_customer_code AS customer_code
FROM checked
ORDER BY source_row;
```

Đây là **bước xem kết quả đã parse ở dạng SELECT**, chưa phải phép INSERT đủ điều kiện. Có thể xuất hiện NULL ở các trường không hợp lệ, số âm vi phạm nghiệp vụ hoặc số quá lớn so với `NUMERIC(12,2)`. Muốn ghi bảng đích cần thêm kiểm tra **precision/scale**, ngưỡng số, sự bắt buộc và tính hợp lệ của mã, rồi chỉ chèn những dòng đã qua toàn bộ điều kiện.

Không nên hiểu rằng kiểm tra `pg_input_is_valid(raw_amount, 'numeric')` đã bảo đảm mọi giá trị đều vừa `NUMERIC(12,2)`: hàm đang xác nhận **khả năng nhập kiểu numeric** chung, không thay thế yêu cầu miền và phần thập phân của cột đích. Truy vấn minh họa cố ý để các bước validation nghiệp vụ ở lớp riêng, tránh che giấu rủi ro làm tròn và tràn precision.

### 12.4. Ghi nhận lỗi thay vì lặng lẽ thay số

Một bảng lỗi có thể gồm:

| source_row | column_name | raw_value | error_code | detail |
| ---: | --- | --- | --- | --- |
| 3 | raw_quantity | abc | INVALID_INTEGER | Không chuyển được sang số nguyên |
| 3 | raw_order_date | 2026-02-30 | INVALID_DATE | Ngày không tồn tại |
| 5 | raw_quantity | 2147483648 | OUT_OF_RANGE | Vượt miền INTEGER |
| 6 | raw_amount | 1,234.56 | AMBIGUOUS_SEPARATOR | Chưa xác định quy ước dấu phân cách |
| 7 | raw_quantity | -2 | BUSINESS_RULE | Số lượng phải không âm |

Đây là ví dụ về **dữ liệu kiểm soát lỗi**, không phải kết quả SQL tự động tạo từ các câu trên. Tổ chức cần thiết kế mã lỗi và cách khắc phục để người nhập dữ liệu có thể sửa và nạp lại.

### 12.5. Không biến lỗi thành 0 bằng COALESCE

Một mẫu nguy hiểm trong các hệ có TRY_CAST:

```sql
-- SQL Server: coi lỗi và thiếu dữ liệu giống số 0.
SELECT COALESCE(TRY_CAST(raw_amount AS DECIMAL(12, 2)), 0)
FROM import_staging;
```

Đầu vào `NULL`, `'abc'`, `'999999999999999999999'` có thể cùng tạo ra số 0 ở kết quả. Nếu đây là số tiền, thống kê sẽ ghi nhận **0 đồng** như thể một giá trị xác định đã được cung cấp.

Thay vì vậy, hãy giữ hai đầu ra khác nhau: **giá trị chuyển đổi** (nullable) và **trạng thái chất lượng**, hoặc đưa hàng sai vào bảng từ chối nhập. Dùng COALESCE chỉ khi “không có giá trị thì đúng là 0” là quy ước nghiệp vụ đã được xác minh.

## 13. Chuyển kiểu trong WHERE, JOIN và ảnh hưởng hiệu năng

Chuyển kiểu có thể làm đúng ngữ nghĩa nhưng **ảnh hưởng khả năng dùng chỉ mục**.

Ví dụ giả sử `orders.customer_id` là INTEGER và có index:

```sql
-- Truy vấn có thể phải biến đổi giá trị của cột cho từng hàng.
SELECT order_id
FROM orders
WHERE CAST(customer_id AS TEXT) = '42';
```

Nếu người dùng cần tìm customer_id = 42, tốt hơn là **bind một giá trị INTEGER** và so sánh trực tiếp:

```sql
SELECT order_id
FROM orders
WHERE customer_id = 42;
```

Việc đặt biểu thức CAST trên cột có thể ngăn sử dụng chỉ mục B-tree bình thường trên chính cột đó trong một số kế hoạch, trừ khi DBMS có khả năng tối ưu phù hợp hoặc có chỉ mục biểu thức. Dùng phép so sánh cùng kiểu thường thể hiện ý định tốt hơn và tránh phải chuyển cột từng hàng.

### 13.1. Trường hợp JOIN hai cột khác kiểu

```sql
-- Ví dụ khái niệm:
SELECT a.id, b.description
FROM orders AS a
JOIN legacy_orders AS b
    ON CAST(a.order_id AS TEXT) = b.legacy_order_id;
```

JOIN kiểu này có thể hoạt động khi mọi mã có ý nghĩa phù hợp, nhưng vẫn có rủi ro:

- Một phía có `'00042'`, phía kia có `42`: chuyển số thành TEXT cho `'42'` không khớp `'00042'`.
- Chuyển văn bản thành số gặp lỗi hoặc hành vi dễ dãi với các mã không phải số.
- Bộ tối ưu có thể khó khai thác chỉ mục ở cột đang bị biến đổi.
- Hai nguồn có thể có **phạm vi định danh khác nhau** dù cùng hình thức số.

Giải pháp dài hạn thường là **chuẩn hóa kiểu tại tầng nhập liệu hoặc migration** và định nghĩa cột khóa có cùng ý nghĩa, thay vì duy trì CAST trong mọi JOIN. Khi không đổi schema được, cần chuyển đổi có kiểm soát, chỉ mục phù hợp và quy tắc xử lý mã không hợp lệ.

### 13.2. Kiểm tra kế hoạch thay vì khẳng định CAST luôn chậm

Trong PostgreSQL:

```sql
EXPLAIN
SELECT order_id
FROM orders
WHERE customer_id = 42;
```

Khi có dữ liệu đại diện, `EXPLAIN (ANALYZE, BUFFERS)` có thể dùng để quan sát số hàng, cách quét, chi phí và buffer; `ANALYZE` **thực sự thực thi câu SELECT**. Một DBMS đôi khi có thể tối ưu CAST hoặc dùng expression index phù hợp; vì vậy tránh quy tắc đơn giản hóa “mọi CAST trong WHERE đều không dùng index”. Vấn đề chính là **so sánh đúng kiểu ở nơi đúng** và đo kế hoạch thực tế.

## 14. Chuyển kiểu và tham số hóa trong ứng dụng

Khi tham số đến từ API hoặc form, hãy phân biệt:

- **Validation ở biên ứng dụng:** nguồn có đúng định dạng, đúng kích thước và quy tắc nghiệp vụ không?
- **Binding đúng kiểu:** SQL nhận số dưới dạng tham số số, ngày dưới dạng tham số ngày nếu API driver hỗ trợ.
- **Ràng buộc database:** bảng đích tiếp tục bảo vệ NOT NULL, CHECK, UNIQUE, FOREIGN KEY.
- **Ghi nhận lỗi:** giữ được dữ liệu đầu vào và thông điệp sửa lỗi khi không hợp lệ.

Ví dụ Java/JDBC, giả sử đã parse giá trị ở ứng dụng thành kiểu tương ứng:

```java
String sql = """
    SELECT order_id, customer_id, total_amount
    FROM orders
    WHERE customer_id = ?
      AND total_amount >= ?
    ORDER BY order_id
    """;

try (PreparedStatement statement = connection.prepareStatement(sql)) {
    statement.setLong(1, customerId);
    statement.setBigDecimal(2, minimumAmount);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
            BigDecimal total = rs.getBigDecimal("total_amount");
            // Xử lý dữ liệu theo nghiệp vụ.
        }
    }
}
```

Ví dụ giả định có `Connection connection`, biến `long customerId`, `BigDecimal minimumAmount` và các import JDBC/Java thích hợp. Nó **không cần CAST cột trong WHERE** vì tham số được truyền đúng kiểu. Prepared statement cũng giảm nguy cơ SQL injection so với ghép chuỗi giá trị người dùng vào câu SQL.

Khi dùng kiểu `TIMESTAMP`, `DATE`, UUID hoặc mảng, cần kiểm tra mapping cụ thể của JDBC driver và phiên bản. Không nên giả định một chuỗi ngày bất kỳ được driver diễn giải giống nhau trên mọi DBMS.

## 15. Các lỗi và ngộ nhận thường gặp

| Ngộ nhận / sai lầm | Vấn đề | Cách xử lý |
| --- | --- | --- |
| “`CAST` lúc nào cũng an toàn” | Chuỗi sai và tràn số có thể phát lỗi | Kiểm tra đầu vào hoặc dùng cơ chế thử chuyển có hỗ trợ |
| “Mọi hệ có `TRY_CAST`” | PostgreSQL/MySQL/SQLite không có hàm TRY_CAST phổ thông mặc định giống SQL Server | Chọn cơ chế theo DBMS và phiên bản |
| “`TRY_CAST` trả NULL nghĩa là trường bị bỏ trống” | NULL có thể là lỗi parse hoặc giá trị nguồn NULL | Lưu raw input và trạng thái parse |
| “`COALESCE(TRY_CAST(...), 0)` sửa được mọi lỗi” | Dữ liệu không hợp lệ bị biến thành số 0 giả | Chỉ thay 0 theo nghiệp vụ, không che lỗi |
| “Chuỗi chỉ có chữ số chắc chắn ép được INTEGER” | Có thể tràn miền 32-bit/64-bit | Kiểm tra giới hạn kiểu đích |
| “Regex `YYYY-MM-DD` xác minh được ngày” | `'2026-02-30'` đúng mẫu nhưng ngày không tồn tại | Kiểm tra ngày lịch bằng parser phù hợp |
| “MySQL/SQLite chắc sẽ báo lỗi nếu chuỗi là `'abc'`” | Có hệ trả 0 hoặc phần tiền tố với cảnh báo | Xác thực rõ, quan sát warning và phiên bản |
| “`DECIMAL(12,2)` giữ mọi chữ số đầu vào” | Có giới hạn precision/scale, có thể làm tròn hoặc tràn | Kiểm tra scale và khoảng giá trị |
| “Mã `'000123'` phải đổi thành INTEGER” | Mất số 0 đầu và có thể mất ý nghĩa mã | Lưu mã dạng văn bản nếu cần bảo toàn |
| “Ép thời điểm sang DATE luôn cho cùng ngày” | Có thể phụ thuộc múi giờ session | Xác định timezone của ngày nghiệp vụ |
| “Chuỗi rỗng giống NULL ở mọi hệ” | PostgreSQL/MySQL khác Oracle trong nhiều kiểu ký tự | Kiểm tra ngữ nghĩa của DBMS |
| “CAST sang VARCHAR(n) sẽ luôn báo lỗi nếu dài hơn” | Một số hệ cắt dữ liệu | Kiểm tra độ dài trước chuyển |
| “CAST cột trong WHERE không ảnh hưởng index” | Có thể đổi đường truy cập và tăng chi phí | Bind tham số đúng kiểu, xem EXPLAIN |
| “TRY không cần kiểm tra nghiệp vụ” | Chuyển được `-2` nhưng quantity có thể không được âm | CHECK/validation theo miền nghiệp vụ |
| “Dấu phẩy trong `1,234.56` luôn là phân nhóm hàng nghìn” | Cách dùng dấu phân cách phụ thuộc locale | Quy định format nguồn và parse tường minh |

## 16. Bài tập thực hành

### Bài 1 — CAST cơ bản

Trong PostgreSQL, hãy chuyển `'42'` thành INTEGER, `'12.50'` thành NUMERIC(10,2), và `'2026-07-01'` thành DATE. Sau đó thử ép `'abc'` sang INTEGER. Phân biệt một **lỗi nhập kiểu** với việc nguồn đang là NULL.

Gợi ý: sử dụng `CAST(... AS ...)`; trong PostgreSQL có thể dùng `::`.

### Bài 2 — Số 0, NULL và chuỗi sai

Một danh sách số lượng đầu vào chứa `'0'`, `NULL`, `''`, `'abc'`, `'12'`. Thiết kế ba trạng thái tối thiểu: `VALID`, `MISSING_OR_BLANK`, `INVALID`. Vì sao chỉ dùng `COALESCE(TRY_CAST(raw AS INTEGER), 0)` sẽ làm mất thông tin? Với SQL Server, hãy viết CASE kết hợp `NULLIF(TRIM(...), '')` và TRY_CONVERT.

### Bài 3 — Tràn số

Giải thích vì sao `'2147483648'` có toàn chữ số nhưng không chuyển được sang INTEGER của PostgreSQL. BIGINT có giải quyết được giá trị này không? Điều gì xảy ra nếu ứng dụng vẫn cố chuyển một giá trị vượt giới hạn BIGINT?

### Bài 4 — Ngày đúng mẫu nhưng sai lịch

So sánh `'2026-07-01'`, `'2026-02-30'` và `'07/04/2026'`. Giá trị nào có định dạng ISO và là ngày thực? Vì sao regex chỉ kiểm tra `^[0-9]{4}-[0-9]{2}-[0-9]{2}$` không đủ? Hãy đề xuất cách kiểm tra ngày theo PostgreSQL 16+ và SQL Server `TRY_CONVERT` với style phù hợp.

### Bài 5 — Giữ số 0 ở đầu mã

`raw_customer_code = '000123'`. Nếu chuyển sang số nguyên rồi lưu lại thành văn bản, giá trị nào có thể bị mất? Vì sao `customer_code TEXT` có thể phù hợp hơn `INTEGER` dù mã chứa toàn chữ số? Khi nào mã thực sự nên là số?

### Bài 6 — Chuyển từ CSV sang số tiền

Nguồn có các chuỗi `'1200.50'`, `'1,200.50'`, `'1200,50'`, `'12x'`, `'1000000000000.00'`. Hãy xác định hợp đồng định dạng: dấu thập phân, dấu phân nhóm, số chữ số thập phân và miền giá trị. Phân loại các trường hợp cần từ chối hoặc chuẩn hóa trước khi ghi `NUMERIC(12,2)`; không tự động bỏ mọi dấu phẩy khi chưa biết locale.

### Bài 7 — Viết SQL theo hai DBMS

Lấy giá trị số nguyên từ văn bản `'abc'` mà không để lỗi chuyển đổi đầu vào này chặn toàn bộ truy vấn:

1. Viết câu SQL Server sử dụng `TRY_CAST`.
2. Viết câu PostgreSQL 16+ sử dụng `pg_input_is_valid` với CASE.

Hãy nêu sự khác nhau về tính sẵn có của hai cơ chế và giới hạn của việc chỉ xem kết quả NULL.

### Bài 8 — TRY_CAST và kiểm soát miền nghiệp vụ

Nếu `TRY_CAST('-5' AS INT)` chuyển thành công trong SQL Server, có được lưu `quantity = -5` vào bảng hàng hóa không? Viết thêm ràng buộc `CHECK(quantity >= 0)` hoặc một bước kiểm tra nghiệp vụ phù hợp. Giải thích vì sao TRY_CAST không thay thế CHECK.

### Bài 9 — Chọn kiểu trong WHERE

Một bảng có cột `customer_id BIGINT` và chỉ mục trên cột đó. So sánh `WHERE CAST(customer_id AS TEXT) = '42'` với `WHERE customer_id = ?` và bind tham số số nguyên trong JDBC. Vì sao cách thứ hai thường có lợi cho khả năng dùng index và ngữ nghĩa? Khi nào việc ép cột vẫn là yêu cầu hợp lệ?

### Bài 10 — Báo cáo theo ngày tại Việt Nam

Một cột `created_at TIMESTAMPTZ` lưu mốc thời gian. Nghiệp vụ muốn lấy các giao dịch thuộc ngày `2026-07-01` theo múi giờ `Asia/Ho_Chi_Minh`. Hãy viết điều kiện khoảng thời gian nửa mở và giải thích vì sao `created_at::DATE = ...` có thể phụ thuộc múi giờ session. Nếu chuyển sang vùng có DST, cần thay đổi cách xác định ranh giới thế nào?

## 17. Kết luận: chuyển đổi an toàn là giữ đúng ý nghĩa và phát hiện lỗi

Có thể tóm lược một chiến lược lựa chọn cơ chế:

```text
Nguồn dữ liệu có kiểu và định dạng rõ ràng?
      |
      +-- Không -> xác định hợp đồng nguồn / lưu raw / phân loại lỗi
      |
      +-- Có -> chọn kiểu đích theo ý nghĩa nghiệp vụ
                      |
                      +-- CAST thường cho dữ liệu đã kiểm soát
                      |
                      +-- Nếu đầu vào có thể lỗi:
                          SQL Server -> TRY_CAST / TRY_CONVERT
                          BigQuery   -> SAFE_CAST
                          Oracle     -> DEFAULT ... ON CONVERSION ERROR
                          PostgreSQL -> pg_input_is_valid (16+) / xử lý riêng
                          MySQL      -> kiểm tra đầu vào, warning, sql_mode
                          SQLite     -> validation riêng vì CAST dễ dãi
                      |
                      v
             Kiểm tra miền, precision, format, timezone
                      |
                      v
             Lưu trạng thái lỗi hoặc ghi vào bảng đích
             có NOT NULL / CHECK / các ràng buộc cần thiết
```

**`CAST` chuyển kiểu, nhưng không chứng minh dữ liệu hợp lệ hoặc không mất thông tin.** Những hàm thử chuyển đổi giúp xử lý đầu vào lỗi êm hơn, song `NULL` sau chuyển đổi có thể mang nhiều nguyên nhân. Đối với số tiền, ngày giờ, mã định danh và dữ liệu nhập từ bên ngoài, hãy xác định kiểu đích, định dạng, độ chính xác, phạm vi và cách ghi nhận lỗi trước khi triển khai.

Nguyên tắc thực hành: **chọn cơ chế theo DBMS và phiên bản thực tế, chuyển đổi có chủ đích, kiểm tra cả kỹ thuật lẫn nghiệp vụ, không âm thầm biến dữ liệu sai thành 0 hoặc chuỗi rỗng**. Nhờ đó câu SQL vừa ổn định hơn khi vận hành, vừa giữ được ý nghĩa dữ liệu mà hệ thống đang cố gắng bảo vệ.
