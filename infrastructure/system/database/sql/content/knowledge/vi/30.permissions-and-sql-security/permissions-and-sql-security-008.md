# Danh sách cho phép khi xây dựng SQL động

Trong **Database SQL**, một số truy vấn cần thay đổi cấu trúc theo lựa chọn lúc chạy: chọn nguồn báo cáo, cột sắp xếp, chiều tăng/giảm, phép lọc hoặc danh sách trường trả về. Khi ứng dụng dựng câu lệnh từ các lựa chọn này, ta đang dùng **SQL động (dynamic SQL)**.

SQL động hữu ích nhưng dễ tạo ra **SQL injection** nếu input được ghép trực tiếp vào chuỗi SQL. Một biện pháp phòng vệ cốt lõi là **allowlist (danh sách cho phép)**: chỉ chấp nhận các lựa chọn cấu trúc đã được hệ thống phê duyệt; mọi lựa chọn khác bị từ chối.

Allowlist phải đi cùng **bind parameter**. Hai cơ chế giải quyết hai loại thành phần khác nhau:

- **Bind parameter** tách giá trị dữ liệu khỏi câu SQL: trạng thái đơn, mã khách, ngày bắt đầu, số lượng tối đa.
- **Allowlist** giới hạn các phần cấu trúc SQL không thể bind trực tiếp: tên schema, bảng, cột, toán tử, chiều sort, tên metric hoặc loại báo cáo.

Một tên bảng được quote đúng cú pháp vẫn có thể là **bảng mà caller không được phép truy cập**. Vì vậy cần kiểm tra chính sách cho phép trước, sau đó mới dựng câu lệnh bằng cơ chế quoting và binding phù hợp với DBMS.

## 1. SQL động là gì?

Một truy vấn tĩnh có cấu trúc cố định:

```sql
SELECT order_id, created_at, total_amount
FROM app.orders
WHERE status = $1;
```

Cấu trúc SELECT, danh sách cột, bảng và điều kiện đã được xác định. Chỉ giá trị status thay đổi theo lần gọi.

SQL động tạo hoặc thực thi câu lệnh từ những thành phần được quyết định lúc chạy:

```sql
-- PostgreSQL PL/pgSQL:
EXECUTE
    'SELECT order_id FROM app.orders WHERE status = $1'
USING p_status;
```

Câu lệnh được thực thi động, nhưng giá trị `p_status` vẫn được truyền bằng bind parameter. Không cần nối giá trị đó vào chuỗi.

Một ví dụ khác có cấu trúc thay đổi:

```sql
EXECUTE format(
    'SELECT order_id, total_amount
       FROM app.orders
      ORDER BY %I DESC',
    v_allowed_column
);
```

Tên cột không thể được truyền như một giá trị `$1` ở vị trí identifier. Vì vậy phải chọn identifier từ allowlist và quote đúng cách.

SQL động có thể hữu ích cho báo cáo nhiều nguồn, màn hình tìm kiếm có sort tùy chọn, công cụ quản trị, ETL theo phiên bản hoặc DDL được sinh từ metadata tin cậy. Nếu cấu trúc không cần thay đổi, **SQL tĩnh thường đơn giản hơn** và dễ cấp quyền, kiểm thử, tối ưu.

## 2. Phân biệt giá trị, identifier và cú pháp SQL

| Thành phần | Ví dụ | Bind trực tiếp được? | Cách xử lý |
| --- | --- | --- | --- |
| Giá trị dữ liệu | `'PAID'`, `42`, ngày tháng | Có | Prepared statement / USING |
| Tên schema | `app` | Không | Allowlist rồi quote identifier |
| Tên bảng | `orders` | Không | Allowlist rồi quote identifier |
| Tên cột | `created_at` | Không | Allowlist rồi quote identifier |
| Chiều sort | `ASC`, `DESC` | Không | Map token sang hằng cú pháp |
| Toán tử | `=`, `>=`, `LIKE` | Không | Map token sang toán tử cố định |
| SQL fragment | `GROUP BY`, `NULLS LAST` | Không | Chọn fragment do code định nghĩa |
| Danh sách giá trị | ID 1, 2, 3 | Không nên nối chuỗi | Array/table-valued parameter hoặc nhiều bind |
| Tên hàm | `COUNT`, `SUM` | Không | Allowlist function và kiểu đầu ra |

Ví dụ an toàn:

```sql
SELECT order_id
FROM app.orders
WHERE status = $1;
```

Ví dụ nguy hiểm:

```sql
-- Không làm thế này:
v_sql := 'SELECT order_id FROM app.orders WHERE status = '''
         || p_status || '''';
EXECUTE v_sql;
```

Nếu `p_status` chứa dấu nháy và phần cú pháp bổ sung, câu SQL cuối có thể bị thay đổi. Prepared statement giữ nó là **một giá trị dữ liệu**, không phải một phần của câu lệnh.

Tên cột cũng không thể bind theo cách sau:

```sql
SELECT $1
FROM app.orders;
```

Nếu `$1` bằng chuỗi `total_amount`, câu lệnh trả chuỗi đó như một giá trị; nó không đọc cột total_amount. Muốn chọn cột động phải dùng allowlist + identifier quoting.

## 3. Allowlist là chính sách, không phải bộ lọc ký tự

Một allowlist trả lời câu hỏi: **caller được chọn chính xác những đối tượng và thao tác nào?**

Ví dụ API báo cáo chỉ cho phép dataset `orders`, `customers`; sort key `created_at`, `total_amount`; direction `asc`, `desc`; operator `eq`, `gte` và các trường đầu ra đã công bố. Mọi token khác phải bị từ chối.

Không dùng cách “xóa ký tự nguy hiểm rồi chấp nhận phần còn lại”. Input `created_at; DROP TABLE users` không trở thành lựa chọn hợp lệ chỉ vì bỏ dấu chấm phẩy. Chính sách đúng là token đó không nằm trong danh sách đã công bố.

| Cách làm | Quy tắc | Hạn chế |
| --- | --- | --- |
| Allowlist | Chỉ chấp nhận lựa chọn được duyệt | Cần quản lý danh sách rõ |
| Denylist | Chặn một số chuỗi/ký tự | Không liệt kê hết mọi cú pháp nguy hiểm |
| Regex identifier | Chỉ cho chữ/số/gạch dưới | Tên hợp lệ cú pháp vẫn có thể không được phép |
| Quote identifier | Escape tên theo cú pháp DBMS | Không quyết định quyền truy cập |

Tên `salary` có thể hợp lệ về cú pháp và được quote đúng, nhưng nếu role báo cáo không được chọn cột lương thì vẫn phải từ chối. **Allowlist quyết định được phép; quoting chỉ bảo vệ cú pháp.**

## 4. Dùng token công khai và tên nội bộ đã map

Tách tên API khỏi identifier vật lý giúp hợp đồng ổn định.

Ví dụ API gửi token `newest`, `oldest` hoặc `largest`:

| Token API | Cột SQL | Direction |
| --- | --- | --- |
| `newest` | `created_at` | `DESC` |
| `oldest` | `created_at` | `ASC` |
| `largest` | `total_amount` | `DESC` |
| `smallest` | `total_amount` | `ASC` |

Token công khai có thể giữ nguyên ngay cả khi schema đổi tên cột từ `created_at` sang `submitted_at`. Chỉ cần cập nhật mapping nội bộ và kiểm thử.

Map nên nằm trong code hoặc cấu hình do người có thẩm quyền quản trị. Nếu allowlist nằm trong bảng dữ liệu mà người dùng cuối có thể tự sửa, quyền ghi bảng đó cũng trở thành một phần của bề mặt bảo mật.

## 5. Từ chối mặc định (fail closed)

Khi token không khớp allowlist:

- Trả lỗi đầu vào rõ ràng.
- Không chạy câu SQL với identifier lạ.
- Không bỏ điều kiện để truy vấn rộng hơn.
- Không fallback sang `SELECT *`.
- Không tự động quote rồi thực thi input chưa được duyệt.

```text
Nhận token
    |
    v
Có trong allowlist?
  /          \
Có            Không
|               |
v               v
Lấy tên nội bộ  Từ chối request
đã map          Không thực thi SQL
|
v
Quote identifier
|
v
Dựng và thực thi câu SQL
```

Fallback về sort mặc định chỉ phù hợp khi hợp đồng API nói rõ hành vi đó. Với thao tác nhạy cảm, thường nên từ chối để caller biết request sai, đồng thời log đúng lựa chọn được yêu cầu.

## 6. Chuẩn hóa input trước khi so sánh

Có thể chấp nhận các biến thể chữ hoa/thường cho token direction bằng cách trim và lowercase: `ASC`, `asc`, `Asc` có thể chuẩn hóa thành `asc`. Một alias `created-at` có thể được map sang `created_at` nếu API công bố rõ.

Nhưng phải định nghĩa canonical form trước:

1. Chọn dạng chuẩn.
2. Chuẩn hóa đúng quy tắc giao thức.
3. So sánh chính xác với allowlist.
4. Lấy identifier nội bộ từ mapping.
5. Quote identifier theo DBMS.

Không dùng chuẩn hóa để biến input lạ thành một tên khác mà caller không được phép chọn. Cần thận trọng với Unicode lookalike, ký tự điều khiển và collation không phân biệt hoa/thường.

## 7. Nguy cơ khi nối input vào ORDER BY

Code ngây thơ:

```text
sql = "SELECT order_id, total_amount
       FROM app.orders
       ORDER BY " + sort_column + " " + sort_direction
```

Nếu nối raw input, caller có thể chèn cú pháp ngoài ý định. Các giá trị WHERE được bind ở chỗ khác không bảo vệ hai thành phần ORDER BY này.

Cách đúng:

- Token cột phải thuộc allowlist.
- Direction chỉ nhận hai giá trị đã map.
- Identifier được quote bằng API DBMS.
- Các giá trị lọc vẫn bind.
- Không chèn raw request vào chuỗi SQL.

Ví dụ, API gửi `amount` và `desc`; code map sang identifier `total_amount` và fragment `DESC`. Người gọi không được gửi nguyên biểu thức `total_amount DESC NULLS LAST; ...`.

## 8. PostgreSQL: EXECUTE ... USING cho giá trị

Trong PL/pgSQL:

```sql
DO $$
DECLARE
    v_status TEXT := 'PAID';
    v_count BIGINT;
BEGIN
    EXECUTE
        'SELECT count(*) FROM app.orders WHERE status = $1'
    INTO v_count
    USING v_status;

    RAISE NOTICE 'Số đơn: %', v_count;
END;
$$;
```

Trong câu SQL động, `$1` là placeholder và `USING v_status` cung cấp giá trị. Giá trị không được nối vào chuỗi SQL; PostgreSQL truyền theo cơ chế bind.

Có thể dùng nhiều placeholder:

```sql
EXECUTE
    'SELECT order_id
       FROM app.orders
      WHERE status = $1
        AND created_at >= $2
      LIMIT $3'
INTO v_order_id
USING p_status, p_from_date, p_limit;
```

Placeholder được gán theo thứ tự trong USING. Nếu câu SQL chỉ thay đổi giá trị, không cần dynamic SQL; câu truy vấn tĩnh với bind thường đủ.

## 9. PostgreSQL: format('%I') cho identifier

PostgreSQL `format()` có các placeholder quan trọng:

| Placeholder | Ý nghĩa |
| --- | --- |
| `%I` | Quote SQL identifier |
| `%L` | Quote SQL literal |
| `%s` | Chèn chuỗi text, không tự quote |

Ví dụ:

```sql
SELECT format(
    'SELECT * FROM %I.%I WHERE status = $1',
    'app',
    'orders'
);
```

`%I` xử lý quoting identifier, kể cả khi tên có chữ hoa hoặc ký tự đặc biệt.

Nhưng đoạn sau **chỉ bảo vệ cú pháp**, không bảo vệ chính sách:

```sql
v_sql := format('SELECT * FROM %I', p_table);
EXECUTE v_sql;
```

Nếu caller truyền bảng `payroll`, SQL có thể hợp lệ nhưng vẫn vượt quyền nghiệp vụ. Phải kiểm tra `p_table` trong allowlist trước khi gọi format.

### 9.1. %L và quote_literal

Có thể dựng literal bằng `%L`, nhưng với giá trị dữ liệu, **USING thường tốt hơn**: giữ kiểu dữ liệu, xử lý NULL rõ, tránh serialize thành SQL text và tách dữ liệu khỏi cấu trúc.

PostgreSQL còn có `quote_ident()`, `quote_literal()` và `quote_nullable()`. Chúng hỗ trợ tạo SQL text, nhưng không quyết định quyền truy cập. Ưu tiên `format('%I', ...)` cho identifier và `USING` cho dữ liệu.

## 10. PostgreSQL: function cho phép sort theo allowlist

Giả định có bảng:

```sql
CREATE SCHEMA app;

CREATE TABLE app.orders (
    order_id BIGINT PRIMARY KEY,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    total_amount NUMERIC(12,2) NOT NULL
);
```

Function chỉ cho sort theo ngày hoặc số tiền:

```sql
CREATE OR REPLACE FUNCTION app.search_orders(
    p_sort_key TEXT,
    p_direction TEXT,
    p_status TEXT,
    p_limit INTEGER
)
RETURNS TABLE (
    order_id BIGINT,
    created_at TIMESTAMPTZ,
    total_amount NUMERIC(12,2),
    status TEXT
)
LANGUAGE plpgsql
AS $func$
DECLARE
    v_sort_column TEXT;
    v_direction TEXT;
BEGIN
    CASE p_sort_key
        WHEN 'date' THEN
            v_sort_column := 'created_at';
        WHEN 'amount' THEN
            v_sort_column := 'total_amount';
        ELSE
            RAISE EXCEPTION USING
                ERRCODE = '22023',
                MESSAGE = 'Sort key không được hỗ trợ';
    END CASE;

    CASE lower(btrim(p_direction))
        WHEN 'asc' THEN
            v_direction := 'ASC';
        WHEN 'desc' THEN
            v_direction := 'DESC';
        ELSE
            RAISE EXCEPTION USING
                ERRCODE = '22023',
                MESSAGE = 'Sort direction phải là asc hoặc desc';
    END CASE;

    IF p_limit IS NULL OR p_limit < 1 OR p_limit > 100 THEN
        RAISE EXCEPTION USING
            ERRCODE = '22023',
            MESSAGE = 'Limit phải nằm trong khoảng 1 đến 100';
    END IF;

    RETURN QUERY EXECUTE format(
        'SELECT o.order_id, o.created_at, o.total_amount, o.status
           FROM app.orders AS o
          WHERE o.status = $1
          ORDER BY o.%I %s, o.order_id DESC
          LIMIT $2',
        v_sort_column,
        v_direction
    )
    USING p_status, p_limit;
END;
$func$;
```

Phân tích:

1. Request chỉ gửi token `date` hoặc `amount`.
2. CASE map token sang identifier nội bộ.
3. Direction chỉ nhận `ASC` hoặc `DESC` đã định nghĩa.
4. `%I` quote tên cột.
5. `%s` chỉ nhận `v_direction` đã map từ hai hằng an toàn; không truyền raw request vào %s.
6. `p_status` và `p_limit` được bind bằng USING.
7. `order_id DESC` là tie-breaker để thứ tự ổn định khi giá trị sort trùng.
8. LIMIT bị giới hạn để tránh request lấy lượng dữ liệu quá lớn.

Gọi:

```sql
SELECT *
FROM app.search_orders('date', 'desc', 'PAID', 20);
```

Token không hợp lệ:

```sql
-- Dự kiến SQLSTATE 22023; không thực thi SQL với tên cột lạ.
SELECT *
FROM app.search_orders('salary', 'desc', 'PAID', 20);
```

Đây là mẫu độc lập. Khi áp dụng thực tế, phải dùng đối tượng đã được phê duyệt, cấp quyền EXECUTE đúng role và kiểm tra quyền truy cập bảng nguồn.

## 11. Khi nào SQL tĩnh tốt hơn?

Nếu chỉ có hai lựa chọn, có thể dùng hai nhánh IF hoặc câu SQL tĩnh với CASE. Ví dụ ý tưởng:

```sql
SELECT order_id, created_at, total_amount
FROM app.orders
WHERE status = $1
ORDER BY
    CASE WHEN $2 = 'date' THEN created_at END DESC,
    CASE WHEN $2 = 'amount' THEN total_amount END DESC,
    order_id DESC
LIMIT $3;
```

Tùy DBMS, các biểu thức CASE có thể cần kiểu tương thích hoặc tách nhánh vì cột có kiểu khác nhau. SQL tĩnh có ưu điểm: không ghép identifier, dễ review, dễ cấp quyền và ít lỗi quoting. Chỉ dùng dynamic SQL khi cấu trúc thực sự thay đổi và lợi ích đủ rõ.

## 12. Allowlist tên bảng và schema

Nếu routine chọn một nguồn báo cáo, map token nghiệp vụ sang cặp schema/table:

| Token caller | Schema | Table |
| --- | --- | --- |
| `orders` | `reporting` | `orders_view` |
| `customers` | `reporting` | `customers_view` |
| `products` | `reporting` | `products_view` |

Không nhận chuỗi `schema.table` tùy ý rồi tách bằng dấu chấm. Identifier có thể chứa dấu chấm nếu được quote; tách chuỗi không tương đương parser SQL.

Mẫu PostgreSQL:

```sql
CASE p_dataset
    WHEN 'orders' THEN
        v_schema := 'reporting';
        v_table := 'orders_view';
    WHEN 'customers' THEN
        v_schema := 'reporting';
        v_table := 'customers_view';
    ELSE
        RAISE EXCEPTION USING
            ERRCODE = '22023',
            MESSAGE = 'Dataset không được hỗ trợ';
END CASE;

v_sql := format(
    'SELECT * FROM %I.%I WHERE created_at >= $1',
    v_schema,
    v_table
);

RETURN QUERY EXECUTE v_sql USING p_from_date;
```

Nếu các view có cấu trúc cột khác nhau, không ép chúng vào một kiểu kết quả bằng `SELECT *`. Tạo API riêng hoặc một cấu trúc đầu ra chung có schema được định nghĩa.

Dùng rõ `schema.table` giảm phụ thuộc vào `search_path` hoặc schema mặc định. Tuy nhiên, qualification và quoting vẫn không thay allowlist: cặp schema/table phải thuộc phạm vi caller được phép.

## 13. Allowlist danh sách cột SELECT

Một công cụ báo cáo có thể cho caller chọn vài trường:

```json
{
  "fields": ["order_id", "created", "amount"]
}
```

Mapping:

| Token API | Identifier SQL |
| --- | --- |
| `order_id` | `order_id` |
| `created` | `created_at` |
| `amount` | `total_amount` |

Mỗi token phải được kiểm tra trước khi đưa vào danh sách SELECT. Nếu số cột thay đổi, lặp qua danh sách token, map sang identifier rồi dùng `format('%I', ...)` cho từng cột.

Quy định rõ: có cho phép danh sách rỗng không; có cho phép cột lặp không; thứ tự có theo request không; có cột nhạy cảm bị cấm theo role không; kiểu kết quả có ổn định không; cột nào được phép dùng trong WHERE và ORDER BY?

Không dùng `information_schema.columns` làm allowlist duy nhất. Catalog cho biết cột tồn tại, không cho biết caller được phép chọn cột đó cho mục đích này.

## 14. Allowlist toán tử và biểu thức lọc

API có thể công bố:

| Token | Cú pháp SQL nội bộ |
| --- | --- |
| `eq` | `=` |
| `gte` | `>=` |
| `lte` | `<=` |
| `contains` | `ILIKE` hoặc biểu thức đã định nghĩa |
| `is_null` | `IS NULL` |

Không ghép toán tử raw. Map token:

```sql
CASE p_operator
    WHEN 'eq' THEN v_operator := '=';
    WHEN 'gte' THEN v_operator := '>=';
    WHEN 'lte' THEN v_operator := '<=';
    ELSE
        RAISE EXCEPTION USING
            ERRCODE = '22023',
            MESSAGE = 'Filter operator không được hỗ trợ';
END CASE;
```

Rồi chèn toán tử nội bộ và bind giá trị:

```sql
v_sql := format(
    'SELECT order_id FROM app.orders WHERE total_amount %s $1',
    v_operator
);
RETURN QUERY EXECUTE v_sql USING p_amount;
```

Ở đây `%s` chỉ nhận một trong ba chuỗi hằng do CASE tạo. Với `IS NULL`, tạo nhánh riêng vì đó là cú pháp, không phải phép so sánh với một giá trị bind. Không viết `column = NULL` để tìm NULL.

## 15. Danh sách IN: bind array thay vì nối nhiều giá trị

Không nối danh sách ID thành chuỗi. PostgreSQL có thể bind array:

```sql
SELECT order_id
FROM app.orders
WHERE customer_id = ANY($1::BIGINT[]);
```

Trong PL/pgSQL dynamic SQL:

```sql
EXECUTE
    'SELECT order_id FROM app.orders WHERE customer_id = ANY($1)'
USING p_customer_ids;
```

`p_customer_ids` là array có kiểu phù hợp, ví dụ `BIGINT[]`. Danh sách vẫn là một giá trị có kiểu, không phải chuỗi SQL.

Với danh sách lớn, cân nhắc array parameter, table-valued parameter (SQL Server), temporary/staging table hoặc bulk load. Cần giới hạn số phần tử và tài nguyên xử lý.

## 16. LIKE và wildcard có ngữ nghĩa riêng

Bind parameter:

```sql
SELECT order_id
FROM app.orders
WHERE customer_name ILIKE $1;
```

đã bảo vệ cấu trúc SQL. Tuy nhiên `%` và `_` trong giá trị vẫn là wildcard của LIKE. Đây không phải SQL injection, nhưng có thể làm tìm kiếm rộng hơn mong đợi.

Nếu muốn tìm chuỗi literal, cần escape wildcard theo quy tắc LIKE và khai báo ESCAPE phù hợp, rồi bind pattern đã xử lý. **Escape wildcard khác escape SQL**. Cũng cần giới hạn độ dài search term và xem xét hiệu năng của pattern bắt đầu bằng `%`.

## 17. ORDER BY, NULLS FIRST/LAST và tie-breaker

`ASC`, `DESC`, `NULLS FIRST` và `NULLS LAST` đều là cú pháp, không phải giá trị bind. Nếu API cho chọn null ordering, hãy map token riêng:

| Token | Fragment |
| --- | --- |
| `nulls_first` | `NULLS FIRST` |
| `nulls_last` | `NULLS LAST` |

Không nhận raw fragment như `DESC NULLS LAST; ...`.

Thứ tự ổn định nên có khóa phụ duy nhất:

```sql
ORDER BY created_at DESC, order_id DESC
```

Nếu chỉ sort theo timestamp không duy nhất, các hàng có cùng timestamp không có thứ tự tương đối được đảm bảo. Điều này có thể làm pagination trùng hoặc bỏ sót hàng. Cũng cần xét role: caller có thể được phép sort theo ngày nhưng không được sort theo cột bí mật mà thứ tự có thể làm lộ thông tin.

## 18. Allowlist function tổng hợp

Nếu API cho chọn metric, map token sang biểu thức cố định:

| Token | SQL expression |
| --- | --- |
| `count` | `COUNT(*)` |
| `sum_amount` | `SUM(total_amount)` |
| `avg_amount` | `AVG(total_amount)` |
| `max_amount` | `MAX(total_amount)` |

Không nối tên hàm tùy ý từ input. Tên hàm hợp lệ về SQL không có nghĩa caller được phép gọi. Một số function có thể đọc dữ liệu hoặc gây side effect theo quyền của chúng.

Allowlist function cũng cần xét kiểu trả về, ý nghĩa NULL, độ nhạy cảm dữ liệu và quyền thực thi.

## 19. Không dùng catalog làm allowlist tự động

`information_schema.tables` cho biết bảng nào tồn tại; `information_schema.columns` cho biết cột nào tồn tại. Chúng không định nghĩa caller được phép chọn những đối tượng nào.

Ví dụ service account có thể đọc `app.orders`, `app.customers` và `hr.payroll`, nhưng API báo cáo chỉ cho phép hai view đầu. Allowlist phải phản ánh **hợp đồng API và role**, không phải tất cả quyền vật lý của service account.

## 20. SECURITY DEFINER và quyền tối thiểu

PostgreSQL function mặc định chạy theo quyền invoker; function `SECURITY DEFINER` có thể chạy bằng quyền owner. Nếu routine definer có quyền rộng mà caller được chọn bảng tùy ý, nó có thể trở thành đường vòng vượt quyền.

Nguyên tắc:

1. Ưu tiên invoker nếu caller có thể được cấp quyền phù hợp.
2. Nếu cần definer, owner chỉ có quyền tối thiểu.
3. Qualification schema/table/function rõ ràng.
4. Cấu hình `search_path` an toàn, không để schema do caller ghi đứng trước schema tin cậy.
5. Không lấy schema/table/function từ input tự do.
6. Allowlist hẹp theo use case và role.
7. Thu hồi EXECUTE khỏi PUBLIC nếu function đặc quyền không dành cho mọi role.
8. Kiểm thử bằng role ít quyền thực tế, không chỉ bằng superuser.

Ví dụ cấu hình:

```sql
CREATE FUNCTION reporting.safe_count(p_status TEXT)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, reporting, pg_temp
AS $$
BEGIN
    RETURN (
        SELECT count(*)
        FROM reporting.orders_view
        WHERE status = p_status
    );
END;
$$;
```

Đây chỉ là cấu hình minh họa; không tự động làm function an toàn nếu quyền owner, schema và dependency chưa được rà soát. Tên đối tượng nhạy cảm vẫn nên qualification đầy đủ.

## 21. Dynamic SQL và tenant isolation

Trong hệ multi-tenant, tenant ID phải đến từ **ngữ cảnh xác thực đáng tin cậy**, không mặc nhiên tin JSON do client gửi.

```sql
EXECUTE
    'SELECT order_id, total_amount
       FROM app.orders
      WHERE tenant_id = $1
        AND status = $2'
USING v_authenticated_tenant_id, p_status;
```

Bind parameter bảo vệ cú pháp, không xác thực quyền tenant. Nếu caller tự gửi tenant ID khác và service tin giá trị đó, dữ liệu tenant khác vẫn có thể bị lộ dù không có SQL injection.

Allowlist dataset cũng có thể theo role. Người đọc bán hàng chỉ được chọn view đơn hàng/khách hàng; người đọc kho chỉ được chọn view sản phẩm/tồn kho; tài chính có view riêng. Không tin trường role/tenant tự do trong request.

## 22. SQL Server: QUOTENAME và sp_executesql

SQL Server dùng `sp_executesql` để thực thi SQL động có tham số:

```sql
DECLARE @status NVARCHAR(20) = N'PAID';
DECLARE @sql NVARCHAR(MAX) =
    N'SELECT OrderId, TotalAmount
      FROM dbo.Orders
      WHERE Status = @p_status;';

EXEC sys.sp_executesql
    @sql,
    N'@p_status NVARCHAR(20)',
    @p_status = @status;
```

`@p_status` được bind. Không nối status vào SQL.

`QUOTENAME()` quote identifier theo quy tắc SQL Server, mặc định dùng ngoặc vuông. Nhưng vẫn phải allowlist trước:

```sql
IF @dataset = N'orders'
    SET @tableName = N'Orders';
ELSE IF @dataset = N'customers'
    SET @tableName = N'Customers';
ELSE
    THROW 51001, 'Dataset is not allowed', 1;

SET @sql =
    N'SELECT COUNT(*)
      FROM dbo.' + QUOTENAME(@tableName) + N'
      WHERE Status = @p_status;';

EXEC sys.sp_executesql
    @sql,
    N'@p_status NVARCHAR(20)',
    @p_status = @status;
```

Tên bảng được map từ allowlist; status vẫn bind. `QUOTENAME` có giới hạn identifier theo `sysname` (128 ký tự); input quá dài có thể cho kết quả NULL, cần kiểm tra.

### 22.1. Sort động trong SQL Server

Map sort token sang tên cột, quote bằng `QUOTENAME`; map direction sang đúng hai hằng `ASC`/`DESC`. Direction là keyword, không phải identifier, nên không quote bằng QUOTENAME.

```sql
IF @sortKey = N'date'
    SET @sortColumn = N'CreatedAt';
ELSE IF @sortKey = N'amount'
    SET @sortColumn = N'TotalAmount';
ELSE
    THROW 51002, 'Sort key is not allowed', 1;

IF @direction = N'asc'
    SET @directionSql = N'ASC';
ELSE IF @direction = N'desc'
    SET @directionSql = N'DESC';
ELSE
    THROW 51003, 'Sort direction is not allowed', 1;
```

Chỉ các giá trị đã map mới được ghép vào SQL. Không lấy raw request cho hai biến này.

## 23. MySQL/MariaDB: PREPARE và bind marker

MySQL/MariaDB prepared statement dùng placeholder `?` cho giá trị:

```sql
SET @status_value = 'PAID';

SET @sql_text =
    'SELECT order_id, total_amount
       FROM orders
      WHERE status = ?';

PREPARE stmt FROM @sql_text;
EXECUTE stmt USING @status_value;
DEALLOCATE PREPARE stmt;
```

Tên bảng/cột không bind được. Nếu cần chọn bảng, dùng CASE/IF allowlist để gán tên nội bộ rồi quote identifier theo dialect MySQL (backtick) đúng cách. Nếu tự xử lý backtick trong identifier, phải escape đúng quy tắc và kiểm tra giới hạn; không viết hàm escape sơ sài.

Cú pháp PREPARE trong routine và hỗ trợ cụ thể thay đổi theo phiên bản/engine. Kiểm tra phiên bản mục tiêu thay vì giả định mọi MySQL/MariaDB giống nhau.

## 24. Oracle: bind variables và DBMS_ASSERT

Oracle dynamic SQL thường dùng `EXECUTE IMMEDIATE` hoặc `DBMS_SQL`.

Bind giá trị:

```sql
DECLARE
    v_status VARCHAR2(20) := 'PAID';
    v_count NUMBER;
BEGIN
    EXECUTE IMMEDIATE
        'SELECT COUNT(*) FROM orders WHERE status = :1'
        INTO v_count
        USING v_status;
END;
/
```

Oracle có package `DBMS_ASSERT` với các hàm như `SIMPLE_SQL_NAME`, `SQL_OBJECT_NAME`, `ENQUOTE_NAME` và `ENQUOTE_LITERAL`. Chúng xác nhận hoặc quote một số dạng tên/literal, nhưng **không thay allowlist chính sách**. Tên bảng hợp lệ và tồn tại vẫn có thể nằm ngoài tập đối tượng API cho phép.

Cách làm: map token sang tên đã duyệt; nếu cần, xác nhận/quote bằng DBMS_ASSERT; dựng SQL với identifier đã kiểm soát; bind mọi giá trị bằng USING; giới hạn quyền execute và quyền schema owner. Với số bind động hoặc câu phức tạp, DBMS_SQL có thể phù hợp hơn.

## 25. SQLite: prepared statements trong API

SQLite không có stored procedure SQL tích hợp như PostgreSQL hay SQL Server. Dynamic SQL thường được dựng ở tầng ứng dụng.

Ví dụ Python:

```python
# Giá trị dữ liệu được bind:
cursor.execute(
    "SELECT order_id, total_amount "
    "FROM orders WHERE status = ?",
    (status,)
)
```

Tên cột động cần map:

```python
sort_columns = {
    "date": "created_at",
    "amount": "total_amount",
}
directions = {
    "asc": "ASC",
    "desc": "DESC",
}

column = sort_columns.get(sort_key)
direction = directions.get(direction_key.lower())

if column is None or direction is None:
    raise ValueError("Sort option is not allowed")

sql = (
    "SELECT order_id, total_amount "
    "FROM orders "
    f"ORDER BY {column} {direction}, order_id DESC"
)
cursor.execute(sql, (status,))
```

Tên cột và direction chỉ đến từ dictionary do code kiểm soát. Status vẫn bind. Không thay dictionary bằng input raw.

Dù SQLite chạy trong tiến trình ứng dụng, SQL injection vẫn có thể đọc/sửa/xóa dữ liệu ngoài ý muốn nếu chuỗi SQL được ghép từ input.

## 26. Quote đúng vẫn chưa đủ

Xét:

```sql
SELECT * FROM "payroll";
```

Câu lệnh có thể hợp lệ về cú pháp, nhưng nếu endpoint chỉ cho phép xem báo cáo đơn hàng thì `payroll` vẫn là đối tượng không được phép.

Ba lớp cần tách biệt:

| Lớp | Câu hỏi | Cơ chế |
| --- | --- | --- |
| Xác thực | Ai đang gọi? | Session, identity, token, database role |
| Ủy quyền | Caller được chọn dữ liệu nào? | Allowlist theo role/tenant/use case |
| An toàn cú pháp | Tên/giá trị được đặt vào SQL thế nào? | Bind parameter, quote identifier |

`quote_ident`, `QUOTENAME` và `DBMS_ASSERT` chỉ giải quyết một phần lớp cú pháp/kiểm tra tên. Chúng không thay authentication, authorization hay least privilege.

## 27. Second-order SQL injection

Input nguy hiểm không nhất thiết được thực thi ngay khi nhận:

1. Người dùng lưu `sort_column` vào bảng cấu hình.
2. Job chạy đêm đọc cấu hình.
3. Job nối giá trị vào ORDER BY.
4. Chuỗi đã lưu làm thay đổi SQL khi job chạy.

Đây là second-order injection: dữ liệu được lưu trước rồi bị sử dụng sai như cú pháp SQL.

Vì vậy validate tại **điểm thực thi**, kể cả dữ liệu đọc từ database; hạn chế quyền sửa bảng cấu hình; không tin dữ liệu cũ chỉ vì đã qua validation ở phiên bản ứng dụng trước; migration/import cũng phải xác thực các lựa chọn cấu trúc.

**Dữ liệu đã nằm trong database không tự trở thành SQL đáng tin cậy.**

## 28. Không nhận raw WHERE clause từ client

Một API nhận:

```json
{
  "where": "status = 'PAID' OR 1=1"
}
```

đang cho caller cung cấp cú pháp SQL. Không giải quyết bằng regex chuỗi where.

Thay vào đó, nhận cấu trúc có kiểu:

```json
{
  "filters": [
    {"field": "status", "operator": "eq", "value": "PAID"},
    {"field": "created", "operator": "gte", "value": "2026-01-01"}
  ]
}
```

Xử lý: field map qua allowlist identifier; operator map qua allowlist cú pháp; value bind theo kiểu đã định nghĩa; AND/OR chỉ theo grammar API công bố; giới hạn số filter, độ sâu nhóm và kích thước danh sách. Không nhận function, subquery hay SQL fragment tùy ý.

Đây là query builder theo ngôn ngữ nghiệp vụ có giới hạn, không phải bộ thực thi SQL tổng quát.

## 29. Quyền tối thiểu và allowlist theo role

Một routine có thể chạy theo quyền invoker hoặc quyền owner/definer tùy DBMS. Cần phân biệt quyền login, role hiện hành, quyền chủ routine, quyền trên schema/table/function và quyền qua role khác hoặc PUBLIC.

Ví dụ:

| Role ứng dụng | Dataset | Sort keys |
| --- | --- | --- |
| `sales_reader` | `orders`, `customers` | `date`, `amount` |
| `inventory_reader` | `products`, `stock` | `sku`, `quantity` |
| `finance_reader` | `orders_finance` | `date`, `amount` |
| `support_reader` | `orders_support` | `date` |

Một allowlist chung có thể cho người đọc bán hàng chọn dataset tài chính chỉ vì service account có quyền đọc. Hãy kiểm tra principal và use case trước khi map token. Tenant phải gắn với identity đã xác thực, không lấy từ một trường tự do trong JSON.

Nguyên tắc: chỉ cấp quyền tới view/procedure mà ứng dụng cần; hạn chế quyền DDL; không chạy routine bằng superuser; tách role triển khai khỏi runtime; log token và request ID mà không lộ dữ liệu nhạy cảm.

## 30. Giới hạn tài nguyên của SQL động

Allowlist không chỉ chống injection; nó còn giới hạn công việc caller có thể yêu cầu.

Cân nhắc giới hạn LIMIT tối đa, số filter và độ sâu nhóm, số phần tử IN, độ dài search term, danh sách cột trả về, dataset/metric được phép, timeout và concurrency, kích thước kết quả và export.

Một truy vấn an toàn về cú pháp vẫn có thể rất tốn kém. API không nên cho caller yêu cầu toàn bộ bảng hoặc sort theo biểu thức phức tạp mà không có giới hạn.

## 31. Kiểm thử allowlist và SQL động

Kiểm thử cả đường hợp lệ lẫn đường bị từ chối.

**Trường hợp hợp lệ:** dataset đúng trả đúng nguồn; sort date/amount hoạt động; direction asc/desc map đúng; giá trị chứa dấu nháy vẫn là dữ liệu; LIMIT trong khoảng; filter array đúng kiểu và số phần tử.

**Trường hợp không hợp lệ:** dataset lạ `payroll`; sort key `password_hash`; direction `DESC; DROP TABLE ...`; operator lạ; chuỗi có dấu nháy/comment/separator; identifier có dấu chấm/quote; input NULL/rỗng/quá dài/Unicode lookalike; role không được chọn dataset; tenant ID không khớp identity; cấu hình cũ chứa token đã bị thu hồi.

Ví dụ PostgreSQL:

```sql
-- Hợp lệ:
SELECT *
FROM app.search_orders('date', 'desc', 'PAID', 20);

-- Không hợp lệ: dự kiến SQLSTATE 22023:
SELECT *
FROM app.search_orders('salary', 'desc', 'PAID', 20);

-- Không hợp lệ: direction ngoài allowlist:
SELECT *
FROM app.search_orders('date', 'desc; DROP TABLE app.orders', 'PAID', 20);

-- Không hợp lệ: limit quá lớn:
SELECT *
FROM app.search_orders('amount', 'asc', 'PAID', 1000000);
```

Chạy từng câu lỗi riêng trong database thử nghiệm. Cần xác nhận **không có truy vấn nào được thực thi khi allowlist từ chối**, không chỉ kiểm tra câu lệnh không có syntax error.

## 32. Quan sát và audit

Log nên trả lời ai gọi routine, dataset/token nào được yêu cầu, token được chấp nhận hay từ chối, request ID/correlation ID là gì, loại truy vấn nào được thực hiện, có lỗi validation/permission không và có retry không.

Không nhất thiết log toàn bộ SQL đã render hoặc mọi giá trị bind. Chúng có thể chứa email, thông tin tài chính hoặc bí mật. Ưu tiên log template ID, token đã map, SQLSTATE và request ID với quyền truy cập/retention phù hợp.

## 33. Quản lý thay đổi allowlist

Allowlist là một phần hợp đồng sản phẩm. Khi thêm token sort hoặc dataset:

- Xác định identifier nội bộ được map.
- Kiểm tra role nào được phép.
- Kiểm tra index và chi phí.
- Cập nhật tài liệu API và test.
- Xem xét tương thích client cũ.
- Audit request dùng token mới.

Không tự động cho phép mọi cột mới xuất hiện trong bảng. Nếu allowlist sinh từ metadata runtime, migration thêm cột nhạy cảm có thể vô tình mở cột đó cho API mà không qua review.

## 34. Checklist trước production

1. Có thực sự cần dynamic SQL hay câu tĩnh/IF/view đơn giản hơn?
2. Mọi giá trị dữ liệu đã bind chưa?
3. Schema, table, column, operator, direction và SQL fragment đã qua allowlist chưa?
4. Có map token công khai sang identifier nội bộ không?
5. Token lạ có bị từ chối mặc định không?
6. Identifier được quote đúng dialect không?
7. Schema qualification có rõ ràng không?
8. Authorization theo role/tenant đã kiểm tra chưa?
9. Routine/service account có quyền tối thiểu không?
10. SECURITY DEFINER/EXECUTE AS có cấu hình context an toàn không?
11. LIMIT, filter count và kích thước IN có giới hạn không?
12. NULL, case, whitespace và Unicode có chính sách rõ không?
13. Dữ liệu cấu hình đã lưu có được validate tại điểm thực thi không?
14. Đã thử input đối kháng và role thiếu quyền chưa?
15. Log có đủ chẩn đoán mà không lộ dữ liệu không?
16. Thay đổi allowlist có migration, version và review không?

## 35. Bài tập thực hành

Các bài dựa trên ví dụ `app.orders` và function `app.search_orders`, trừ khi ghi rõ. Những câu có chủ đích phát sinh lỗi nên chạy riêng trong database học tập.

### Bài 1 — Phân loại thành phần

Phân loại từng phần là giá trị bind hay cấu trúc phải allowlist/quote:

a. `status = 'PAID'`

b. `FROM app.orders`

c. `ORDER BY total_amount DESC`

d. `LIMIT 20`

e. `total_amount >= 100`

f. `GROUP BY customer_id`

### Bài 2 — Vì sao không bind identifier?

Giải thích kết quả của:

```sql
SELECT $1 FROM app.orders;
```

Nếu `$1` bằng chuỗi `total_amount`, câu lệnh có đọc cột total_amount không?

### Bài 3 — Allowlist sort

Viết mapping ba token: `newest -> created_at DESC`, `oldest -> created_at ASC`, `largest -> total_amount DESC`. Token khác phải bị từ chối. Vì sao không lấy direction trực tiếp từ request?

### Bài 4 — PostgreSQL format

`%I`, `%L` và `%s` khác nhau thế nào? Placeholder nào phù hợp cho tên cột? Cách nào nên dùng cho giá trị status?

### Bài 5 — Bind trong dynamic SQL

Viết PL/pgSQL EXECUTE để chọn order_id từ app.orders với điều kiện status = $1, bind p_status bằng USING.

### Bài 6 — Tên bảng theo token

API cho phép orders và customers. Viết CASE map sang hai view cố định trong schema reporting. Vì sao không chỉ kiểm tra bảng có tồn tại trong information_schema?

### Bài 7 — Operator allowlist

Cho API hỗ trợ eq, gte, lte. Map chúng sang =, >=, <= rồi bind giá trị. Vì sao không nhận raw operator?

### Bài 8 — IN list

Một request gửi 200 customer ID. Nêu cách PostgreSQL bind array bằng `= ANY($1::BIGINT[])`. Vì sao không nối chuỗi ID vào IN?

### Bài 9 — SQL Server

Giải thích vai trò QUOTENAME và sp_executesql. Vì sao cần allowlist trước khi gọi QUOTENAME?

### Bài 10 — Oracle

Nêu vai trò DBMS_ASSERT và bind variable. Vì sao SQL_OBJECT_NAME không tự quyết định caller được truy cập bảng nào?

### Bài 11 — MySQL và SQLite

Vì sao prepared statement không bind được tên cột? Nêu cách xử lý sort động an toàn.

### Bài 12 — Regex và denylist

Một developer chỉ cho phép identifier khớp mẫu chữ/số/gạch dưới. Vì sao chưa đủ? Nêu một cột hợp lệ cú pháp nhưng không được phép theo chính sách.

### Bài 13 — Second-order injection

Một cấu hình sort_column đã lưu trong database từ nhiều tháng trước. Vì sao job chạy đêm vẫn phải kiểm tra allowlist khi thực thi?

### Bài 14 — SECURITY DEFINER

Function SECURITY DEFINER có quyền đọc payroll. Caller truyền tên bảng tùy ý, function quote bằng %I. Vì sao vẫn nguy hiểm? Nêu ba biện pháp giảm rủi ro.

### Bài 15 — Tenant ID

Một API bind tenant_id bằng $1, nhưng giá trị lấy trực tiếp từ JSON client. Vì sao câu SQL không bị injection vẫn có thể lộ dữ liệu tenant khác?

### Bài 16 — ORDER BY và pagination

Vì sao truy vấn dynamic sort nên thêm tie-breaker duy nhất như order_id? Điều gì xảy ra nếu chỉ sort timestamp không duy nhất?

### Bài 17 — Kiểm thử âm

Nêu ít nhất sáu input cần thử: token lạ, dấu nháy, comment, separator, identifier có dấu chấm, NULL, quá dài hoặc Unicode lookalike.

### Bài 18 — Thiết kế query builder

API nhận field, operator, value, direction. Mô tả cách validate/map/bind từng trường và giới hạn tài nguyên.

## 36. Gợi ý đáp án

**Bài 1.** a: status là identifier cố định, PAID là giá trị bind. b: schema/table là identifier. c: column là identifier, DESC là cú pháp. d: 20 là giá trị bind được. e: cột/toán tử là cấu trúc, 100 là giá trị bind. f: GROUP BY và customer_id là cấu trúc.

**Bài 2.** `$1` là một giá trị biểu thức; query trả chuỗi total_amount cho mỗi hàng, không biến nó thành tên cột.

**Bài 3.**

```sql
CASE p_sort
    WHEN 'newest' THEN
        v_column := 'created_at';
        v_direction := 'DESC';
    WHEN 'oldest' THEN
        v_column := 'created_at';
        v_direction := 'ASC';
    WHEN 'largest' THEN
        v_column := 'total_amount';
        v_direction := 'DESC';
    ELSE
        RAISE EXCEPTION USING
            ERRCODE = '22023',
            MESSAGE = 'Sort option không hợp lệ';
END CASE;
```

Direction là cú pháp; bind parameter không thể thay keyword. Mapping cũng giới hạn chính sách.

**Bài 4.** `%I` quote identifier, `%L` quote literal, `%s` chèn text không quote. Dùng %I cho tên cột đã allowlist; dùng USING cho status.

**Bài 5.**

```sql
EXECUTE
    'SELECT order_id FROM app.orders WHERE status = $1'
USING p_status;
```

Trong function cụ thể cần INTO hoặc RETURN QUERY tùy kiểu kết quả.

**Bài 6.** Dùng CASE map orders/customers sang tên view cố định. Catalog chỉ cho biết đối tượng tồn tại, không phản ánh hợp đồng API hoặc role được phép.

**Bài 7.** Map eq/gte/lte sang operator cố định, chèn fragment nội bộ và bind giá trị. Raw operator có thể chứa thêm cú pháp SQL.

**Bài 8.**

```sql
SELECT order_id
FROM app.orders
WHERE customer_id = ANY($1::BIGINT[]);
```

Array bind giữ danh sách là một tham số có kiểu, tránh lỗi escaping và injection do nối chuỗi.

**Bài 9.** QUOTENAME quote identifier SQL Server; sp_executesql thực thi SQL có bind. Allowlist quyết định caller được chọn bảng nào; QUOTENAME chỉ xử lý cú pháp tên.

**Bài 10.** DBMS_ASSERT xác nhận/quote một số dạng tên Oracle; bind variable tách dữ liệu khỏi SQL. Object tồn tại vẫn có thể ngoài chính sách endpoint.

**Bài 11.** Placeholder là biểu thức giá trị, không phải grammar identifier. Map token sang tên cột nội bộ, quote theo dialect, map direction sang ASC/DESC cố định, bind filter value.

**Bài 12.** Regex chỉ kiểm tra hình thức. `salary` có thể khớp nhưng role báo cáo không được xem lương; cần allowlist theo use case và role.

**Bài 13.** Dữ liệu cấu hình có thể bị thay đổi hoặc qua validation cũ. Validate lại tại điểm nó được chuyển thành cấu trúc SQL.

**Bài 14.** Caller có thể chọn payroll bằng quyền owner; %I chỉ quote tên. Biện pháp: allowlist dataset hẹp, owner quyền tối thiểu, schema qualification/search_path an toàn, hạn chế EXECUTE, kiểm thử bằng role ít quyền.

**Bài 15.** Bind bảo vệ cú pháp, không xác thực quyền tenant. Caller có thể gửi tenant khác nếu service tin dữ liệu client; tenant phải gắn với identity đã xác thực và được authorization.

**Bài 16.** Timestamp có thể trùng, thứ tự tương đối không được đảm bảo và pagination có thể trùng/bỏ sót. Thêm khóa duy nhất như order_id.

**Bài 17.** Ví dụ: payroll, `' OR 1=1 --`, `DESC; DROP TABLE x`, `app.orders`, chuỗi rỗng, NULL, chuỗi quá dài, Unicode lookalike, khoảng trắng, comment marker, ký tự điều khiển.

**Bài 18.** Field map qua allowlist identifier; operator map qua cú pháp cố định; value bind theo kiểu cột; direction map ASC/DESC; từ chối token lạ; giới hạn filter count, độ sâu, IN size, LIMIT và timeout; kiểm tra role/tenant trước khi execute.

## 37. Kết luận

Danh sách cho phép là **ranh giới chính sách** khi cấu trúc SQL thay đổi theo request. Nó xác định caller được chọn dataset, bảng, cột, phép toán và kiểu sắp xếp nào. Sau khi xác nhận lựa chọn, code mới dùng cơ chế quoting identifier phù hợp với DBMS.

Giá trị dữ liệu phải được truyền bằng **prepared statement/bind parameter**: `USING` trong PostgreSQL, `sp_executesql` trong SQL Server, bind variable trong Oracle, placeholder của MySQL/SQLite. Identifier và mảnh cú pháp không thể bind như một giá trị; chúng cần được **map từ token đã duyệt**, rồi quote đúng dialect. `%I`, `QUOTENAME()` và `DBMS_ASSERT` giúp bảo vệ cách tên được phân tích, nhưng **không thay allowlist, authentication, authorization hay quyền tối thiểu**.

Hãy từ chối mặc định token không được công bố, không nhận raw WHERE/ORDER BY từ client, không tin dữ liệu cấu hình chỉ vì nó đã được lưu, và kiểm thử cả input hợp lệ lẫn đối kháng. Khi routine chạy với quyền cao, đặc biệt SECURITY DEFINER, allowlist phải hẹp và được quản lý như một phần của API bảo mật. **SQL động an toàn là sự kết hợp của chính sách lựa chọn rõ ràng, bind giá trị, quote identifier đúng, quyền tối thiểu và kiểm thử tại điểm thực thi.**
