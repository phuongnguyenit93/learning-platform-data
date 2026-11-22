# Giá trị mặc định, tham số có tên và nạp chồng trong PostgreSQL

## 1. Vì sao thiết kế tham số hàm là một phần của hợp đồng SQL?

Một hệ thống bán hàng cần tính tiền đơn. Ban đầu chỉ có hai tham số:

```sql
SELECT calculate_total(100000, 2);
```

Sau đó nghiệp vụ yêu cầu hỗ trợ giảm giá, làm tròn và tiền tệ. Nếu liên tục thay đổi vị trí/thứ tự đối số mà không có quy ước, những câu SQL cũ dễ bị hiểu sai hoặc không còn chạy được.

PostgreSQL cung cấp ba cơ chế quan trọng:

- **Giá trị mặc định (default arguments):** cho phép người gọi bỏ qua một số tham số tùy chọn.
- **Tham số có tên (named arguments):** truyền giá trị theo tên thay vì chỉ theo vị trí.
- **Nạp chồng (function/procedure overloading):** nhiều routine cùng tên nhưng có các **kiểu tham số đầu vào khác nhau**.

Ví dụ:

```sql
CREATE FUNCTION app.calculate_total(
    p_unit_price numeric,
    p_quantity integer DEFAULT 1,
    p_discount_rate numeric DEFAULT 0
)
RETURNS numeric
...
```

Lúc này các lời gọi có thể diễn đạt:

```sql
SELECT app.calculate_total(100000);
SELECT app.calculate_total(100000, 2);
SELECT app.calculate_total(
    p_unit_price => 100000,
    p_discount_rate => 0.10
);
```

Ba hình thức có cùng điểm xuất phát, nhưng mang các ý nghĩa khác nhau về tính tùy chọn, khả năng đọc và tương thích khi thay đổi API database.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Khai báo default arguments chính xác cho `CREATE FUNCTION` và `CREATE PROCEDURE`.
2. Giải thích quy tắc: **các tham số đầu vào sau một tham số có DEFAULT cũng phải có DEFAULT**.
3. Gọi hàm theo **vị trí**, **tên** và kiểu **kết hợp**.
4. Phân biệt **bỏ qua đối số** với **truyền tường minh NULL**.
5. Hiểu ngữ nghĩa của default expression phụ thuộc thời gian hoặc dữ liệu.
6. Xác định overload dựa trên **tên + danh sách kiểu tham số đầu vào**, không dựa vào kiểu trả về hay tên tham số.
7. Đọc lỗi `function ... does not exist` và `function ... is not unique`.
8. Nhận biết các tình huống mơ hồ do default arguments, literal chưa có kiểu và chuyển kiểu ngầm định.
9. Dùng explicit casts và schema-qualified calls để định hướng lời gọi.
10. Thiết kế routine API bền vững khi refactor, tránh thay đổi tên tham số làm hỏng named calls.
11. Phân biệt gọi **function** bằng `SELECT` với gọi **procedure** bằng `CALL`.
12. Tra cứu overload bằng `pg_proc`, `regprocedure`, `pg_get_function_arguments` và công cụ `psql`.
13. Áp dụng quy tắc quyền, `search_path` và bảo mật khi dùng routine trong ứng dụng.
14. Thực hành và tự đánh giá bằng ví dụ SQL có kết quả dự kiến.

---

## 2. Hàm (function) và thủ tục (procedure) khác nhau ở đâu?

Cả hai đều là **routine** trong PostgreSQL, có thể nhận đối số, nhưng cách sử dụng không hoàn toàn giống nhau.

| Tiêu chí | Function | Procedure |
|---|---|---|
| Khai báo | `CREATE FUNCTION` | `CREATE PROCEDURE` |
| Cách gọi SQL phổ biến | `SELECT schema.f(...)` | `CALL schema.p(...)` |
| Dùng như biểu thức trong SELECT/WHERE | Có, nếu đúng kiểu/đặc tính | Không gọi trực tiếp bằng SELECT như function |
| Trả giá trị | `RETURNS ...`, `RETURNS TABLE`, OUT/INOUT | Có thể trả các OUT/INOUT qua kết quả CALL tùy định nghĩa |
| Thực thi nhiều lệnh | Có thể qua PL/pgSQL/SQL phù hợp | Có thể |
| Transaction control bên trong | Không tùy tiện COMMIT/ROLLBACK như một procedure | Một số CALL top-level và điều kiện cho phép transaction control |
| Named/default arguments | Có | Có |
| Overloading theo kiểu đầu vào | Có | Có |

Nội dung bài tập trung vào **hợp đồng tham số**. Không nên chọn procedure chỉ vì muốn có nhiều tham số; một function đơn giản có default/named arguments thường đủ cho phép tính không gây side effect.

### 2.1. Function không phải procedure “viết khác cú pháp”

Sai:

```sql
-- Với một function tên calculate_total:
CALL app.calculate_total(100000);
```

Đúng:

```sql
SELECT app.calculate_total(100000);
```

Ngược lại, đối với procedure `write_audit`, dùng `CALL`; không mặc nhiên gọi `SELECT write_audit(...)`.

### 2.2. Gọi routine bằng tên đủ schema

Tài liệu sẽ dùng:

```sql
routine344.function_name(...)
routine344.procedure_name(...)
```

thay vì phụ thuộc `search_path`. Đây là cách làm rõ routine được chọn và giảm rủi ro trùng tên giữa schema.

## 3. Chuẩn bị môi trường thực hành

Chạy các ví dụ trong một **database PostgreSQL học tập**, không chạy các lệnh tạo/sửa routine trong schema production nếu chưa qua migration review.

```sql
CREATE SCHEMA IF NOT EXISTS routine344;

SHOW server_version;
SHOW search_path;
```

Các ví dụ được viết theo cú pháp PostgreSQL hiện đại. Với server cũ, cần kiểm tra riêng mức hỗ trợ procedures, CALL, đặc điểm output arguments và các tùy chọn được dùng.

### 3.1. Không dùng object tên chung trong schema public

Tên như `sum`, `count`, `round` hoặc `format` có thể trùng tên hàm built-in hoặc routine do extension cung cấp. Đặt schema riêng và tên rõ nghĩa giúp tránh gọi nhầm.

### 3.2. Hướng dẫn về lỗi mong đợi

Một số phần có SQL được đánh dấu **“chủ đích lỗi”** để học quy tắc. Không chạy chung toàn bộ ví dụ có lỗi trong một transaction rồi kỳ vọng các câu sau vẫn thành công. Khi một transaction gặp lỗi, bạn có thể phải `ROLLBACK` hoặc xử lý savepoint.

## 4. Hàm có đối số mặc định đầu tiên

Tạo một hàm tính tổng có ba tham số:

```sql
CREATE OR REPLACE FUNCTION routine344.invoice_total(
    p_unit_price numeric,
    p_quantity integer DEFAULT 1,
    p_discount_rate numeric DEFAULT 0
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT round(
        p_unit_price * p_quantity * (1 - p_discount_rate),
        2
    );
$$;
```

**Ý nghĩa hợp đồng:**

- `p_unit_price`: bắt buộc, kiểu `numeric`.
- `p_quantity`: tùy chọn, mặc định bằng 1.
- `p_discount_rate`: tùy chọn, mặc định bằng 0.
- Kết quả là `numeric` đã làm tròn tới hai chữ số thập phân.

### 4.1. Những điều hàm này chưa bảo vệ

Hàm trên chỉ minh họa tham số. Nó **chưa từ chối** số lượng âm, đơn giá âm, discount nhỏ hơn 0 hoặc lớn hơn 1. Trong hệ thống thực tế cần thiết kế constraint/domain/validation tương ứng, đặc biệt với tính tiền.

### 4.2. IMMUTABLE có nghĩa gì ở đây?

Với cùng các đối số số học, hàm minh họa cho cùng kết quả và không đọc dữ liệu bảng hoặc đồng hồ. Vì vậy `IMMUTABLE` là lựa chọn hợp lý.

Không nên gán `IMMUTABLE` cho hàm truy vấn bảng thay đổi hoặc dùng `now()` chỉ để “tăng hiệu năng”.

## 5. Positional notation: truyền đối số theo vị trí

Truyền ba đối số:

```sql
SELECT routine344.invoice_total(
    100000::numeric,
    2,
    0.10::numeric
) AS total_amount;
```

Phép tính:

```text
100000 × 2 × (1 - 0.10) = 180000.00
```

Truyền hai đối số:

```sql
SELECT routine344.invoice_total(
    100000::numeric,
    2
) AS total_amount;
```

PostgreSQL dùng default của `p_discount_rate = 0`; kết quả:

```text
200000.00
```

Chỉ truyền một đối số:

```sql
SELECT routine344.invoice_total(
    100000::numeric
) AS total_amount;
```

Cả `p_quantity` và `p_discount_rate` dùng default:

```text
100000.00
```

### 5.1. Quy tắc bỏ tham số từ phải sang trái

Với positional notation, đối số nào **không được truyền** phải nằm ở đoạn cuối danh sách parameter.

Có thể:

```text
invoice_total(unit_price)
invoice_total(unit_price, quantity)
invoice_total(unit_price, quantity, discount_rate)
```

Nhưng nếu chỉ muốn truyền discount_rate và **giữ quantity mặc định**, không thể viết như thể tham số thứ hai là discount:

```sql
-- Nhầm ngữ nghĩa: giá trị thứ hai là quantity, không phải discount.
SELECT routine344.invoice_total(100000::numeric, 0.15);
```

Vì tham số thứ hai được khai báo `integer`, dạng literal thập phân ở đây còn có thể tạo lỗi khớp kiểu hoặc chuyển kiểu không như người viết mong muốn. Vấn đề gốc là **đối số positional thứ hai luôn ánh xạ vào p_quantity**.

Để bỏ qua quantity nhưng đặt discount, dùng **named notation**.

## 6. Named notation: gắn đối số với tên tham số

Cú pháp khuyến nghị:

```sql
parameter_name => argument_expression
```

Ví dụ:

```sql
SELECT routine344.invoice_total(
    p_unit_price => 100000::numeric,
    p_discount_rate => 0.15::numeric
) AS total_amount;
```

Vì không truyền `p_quantity`, giá trị mặc định 1 được sử dụng.

Kết quả:

```text
85000.00
```

### 6.1. Thứ tự named arguments có thể khác thứ tự khai báo

```sql
SELECT routine344.invoice_total(
    p_discount_rate => 0.15::numeric,
    p_unit_price => 100000::numeric
);
```

Vẫn là 85000.00. PostgreSQL gắn theo tên thay vì vị trí.

### 6.2. Named arguments tăng tính dễ đọc

So sánh:

```sql
SELECT routine344.invoice_total(250000, 4, 0.075);
```

với:

```sql
SELECT routine344.invoice_total(
    p_unit_price => 250000,
    p_quantity => 4,
    p_discount_rate => 0.075
);
```

Ở cách thứ hai, người đọc không cần nhớ nghĩa của từng vị trí. Điều này đặc biệt hữu ích với tham số boolean, ngưỡng thời gian, số lượng hoặc nhiều lựa chọn tùy chỉnh.

### 6.3. Tên tham số phải đúng

Cú pháp sau **không đúng tên parameter**:

```sql
-- Chủ đích lỗi:
SELECT routine344.invoice_total(
    unit_price => 100000
);
```

Routine đã khai báo `p_unit_price`, không phải `unit_price`. PostgreSQL có thể báo không tìm được function signature phù hợp với lời gọi named ấy.

### 6.4. Tên và chữ hoa/chữ thường

Identifier không quote trong PostgreSQL được chuyển về chữ thường. Nếu định nghĩa một tham số với identifier được quote, ví dụ `"DiscountRate"`, named call cũng cần đúng tên/định dạng quote tương ứng.

Trong API SQL, nên dùng tên ổn định dạng `snake_case` không quote.

## 7. Cú pháp named legacy: :=

PostgreSQL cũng hỗ trợ cách viết cũ:

```sql
SELECT routine344.invoice_total(
    p_unit_price := 100000,
    p_discount_rate := 0.15
);
```

Trong lời gọi hàm, `:=` là named-argument syntax tương thích lịch sử.

Tuy nhiên, nên ưu tiên:

```sql
p_discount_rate => 0.15
```

để tránh nhầm với toán tử gán biến `:=` trong PL/pgSQL và nhất quán với SQL hiện đại.

### 7.1. Named arguments không giống map JSON

Cú pháp:

```sql
p_quantity => 2
```

là thành phần của **lời gọi routine** được parser hiểu theo danh sách tham số đã khai báo. Nó không tự tạo một object hoặc document JSON.

Không thay named arguments bằng:

```sql
SELECT routine344.invoice_total(
    '{"p_quantity":2}'::jsonb
);
```

trừ khi thật sự định nghĩa một overload nhận `jsonb` và tự xử lý tài liệu.

## 8. Mixed notation: positional trước, named sau

PostgreSQL hỗ trợ gọi kết hợp:

```sql
SELECT routine344.invoice_total(
    100000::numeric,
    p_discount_rate => 0.15::numeric
);
```

Ý nghĩa:

- `100000` ánh xạ theo vị trí đầu tiên → `p_unit_price`.
- `p_discount_rate` được truyền theo tên.
- `p_quantity` bị bỏ qua → dùng mặc định 1.

Kết quả: 85000.00.

Một ví dụ có hai positional:

```sql
SELECT routine344.invoice_total(
    100000::numeric,
    3,
    p_discount_rate => 0.10
);
```

Kết quả: 270000.00.

### 8.1. Positional arguments không được theo sau named arguments

Sai:

```sql
-- Chủ đích lỗi cú pháp:
SELECT routine344.invoice_total(
    p_unit_price => 100000,
    3,
    0.10
);
```

Quy tắc:

```text
Các đối số positional đi trước.
Sau khi bắt đầu dùng named arguments,
những đối số tiếp theo cũng phải là named arguments.
```

### 8.2. Không truyền cùng một parameter hai lần

Sai:

```sql
-- Chủ đích lỗi:
SELECT routine344.invoice_total(
    100000::numeric,
    p_unit_price => 90000::numeric
);
```

Tham số `p_unit_price` đã nhận positional 100000, nên named `p_unit_price` không thể được cung cấp lại.

### 8.3. Mixed notation tốt khi có tham số bắt buộc rõ

Một style phổ biến:

```sql
SELECT routine344.invoice_total(
    100000::numeric,
    p_quantity => 3,
    p_discount_rate => 0.05
);
```

Nó giữ gọn tham số bắt buộc, nhưng chỉ rõ tên các lựa chọn tùy chọn.

## 9. DEFAULT trong khai báo hàm: quy tắc thứ tự

PostgreSQL cho phép giá trị mặc định đối với **input parameters** gồm `IN` và `INOUT`, theo khả năng tương ứng. Nếu một input parameter có default, **mọi input parameter theo sau nó cũng phải có default**.

Hợp lệ:

```sql
CREATE FUNCTION routine344.sum_with_options(
    p_a integer,
    p_b integer DEFAULT 10,
    p_c integer DEFAULT 20
)
RETURNS integer
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT p_a + p_b + p_c;
$$;
```

Không hợp lệ:

```sql
-- Chủ đích lỗi: p_b không có default,
-- nhưng nằm sau p_a có default.
CREATE FUNCTION routine344.invalid_defaults(
    p_a integer DEFAULT 10,
    p_b integer
)
RETURNS integer
LANGUAGE sql
AS $$
    SELECT p_a + p_b;
$$;
```

### 9.1. Tại sao có quy tắc này?

Với positional calls, nếu hàm được khai báo:

```text
f(a DEFAULT 10, b required)
```

thì lời gọi `f(20)` không có cách hiểu đơn giản: 20 dành cho a hay b? PostgreSQL yêu cầu các input parameters từ tham số có default trở đi cũng phải có default để giữ quy tắc bỏ đối số cuối rõ ràng.

Dù named notation có thể tưởng tượng cho phép bỏ qua vị trí đầu, PostgreSQL **vẫn áp dụng** quy tắc này khi khai báo.

### 9.2. DEFAULT và dấu bằng

Cả hai cách khai báo có thể dùng:

```sql
p_quantity integer DEFAULT 1
```

hoặc:

```sql
p_quantity integer = 1
```

Nên thống nhất dùng `DEFAULT` vì dễ nhận biết đây là giá trị mặc định, không phải phép gán khi thực thi.

## 10. Bỏ qua đối số khác truyền tường minh NULL

Giả sử:

```sql
CREATE FUNCTION routine344.greeting(
    p_name text,
    p_salutation text DEFAULT 'Xin chào'
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT p_salutation || ', ' || p_name;
$$;
```

Lời gọi:

```sql
SELECT routine344.greeting('An');
```

trả:

```text
Xin chào, An
```

Nhưng:

```sql
SELECT routine344.greeting(
    'An',
    NULL::text
);
```

trả **SQL NULL**, vì nối chuỗi bằng `||` với một đối số NULL cho kết quả NULL.

### 10.1. Tại sao?

- **Không truyền** p_salutation → PostgreSQL dùng giá trị `DEFAULT 'Xin chào'`.
- **Truyền NULL** → bạn đã truyền một giá trị cụ thể là SQL NULL; default **không thay thế** nó.

Đây là khác biệt rất quan trọng trong ứng dụng.

### 10.2. Nếu muốn NULL cũng dùng fallback

Hãy viết logic rõ ràng:

```sql
CREATE FUNCTION routine344.greeting_null_safe(
    p_name text,
    p_salutation text DEFAULT 'Xin chào'
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT
        coalesce(p_salutation, 'Xin chào')
        || ', ' ||
        coalesce(p_name, 'bạn');
$$;
```

Lúc này:

```sql
SELECT routine344.greeting_null_safe(
    'An',
    NULL::text
);
```

trả `Xin chào, An`.

Nhưng **đây là quyết định nghiệp vụ** trong thân hàm, không phải đặc tính mặc nhiên của DEFAULT.

### 10.3. Trong function STRICT

Một hàm khai báo `STRICT`/`RETURNS NULL ON NULL INPUT` có thể trả NULL ngay khi một **đối số hiệu lực** là SQL NULL, không thực thi thân hàm theo cách thông thường.

Giá trị default được dùng khi đối số bị bỏ qua. Nếu người gọi cung cấp explicit NULL ở tham số có default, tính STRICT vẫn áp dụng với NULL ấy.

## 11. Default expression được tính ở đâu và lúc nào?

Một default argument không nhất thiết là hằng số. Ví dụ:

```sql
CREATE FUNCTION routine344.effective_time(
    p_time timestamptz DEFAULT CURRENT_TIMESTAMP
)
RETURNS timestamptz
LANGUAGE sql
STABLE
AS $$
    SELECT p_time;
$$;
```

Gọi:

```sql
SELECT routine344.effective_time();
```

Lời gọi nhận giá trị default biểu thức `CURRENT_TIMESTAMP`. Biểu thức này **không bị đóng băng ở thời điểm CREATE FUNCTION**.

### 11.1. CURRENT_TIMESTAMP trong PostgreSQL

`CURRENT_TIMESTAMP` và `now()` phản ánh **thời điểm bắt đầu transaction** theo ngữ nghĩa PostgreSQL, không phải đồng hồ thay đổi từng microsecond trong cùng transaction.

Vì thế, hai lần gọi trong cùng transaction có thể cùng timestamp.

### 11.2. Default expression phải hợp kiểu

Nếu khai báo:

```sql
p_quantity integer DEFAULT 'abc'
```

PostgreSQL sẽ không thể dùng chuỗi không chuyển được sang integer theo cách mong muốn. Default expression cần **coercible** về kiểu tham số.

### 11.3. Không dùng một “mẹo” thời gian sai

Trong những bối cảnh SQL khác có thể gặp cách viết timestamp literal kiểu `TIMESTAMP 'now'`, literal có thể được chuyển thành giá trị tại thời điểm parse/DDL. Nếu muốn giá trị thời gian động theo lời gọi, ưu tiên hàm/biểu thức thời gian thích hợp như `CURRENT_TIMESTAMP` và hiểu rõ transaction timestamp.

### 11.4. Default phức tạp là một dependency

Nếu default gọi function khác, sequence hoặc phụ thuộc cấu hình, hãy cân nhắc:

- Ai sở hữu function/default ấy?
- Nó có side effects không?
- Nó có phụ thuộc quyền người gọi không?
- Khi thay đổi cấu hình thì những lời gọi bỏ tham số có còn giống cũ không?
- Default expression có ảnh hưởng hiệu năng không?

Không xem default argument là metadata vô hại trong mọi trường hợp.

## 12. Tham số bắt buộc, tham số tùy chọn và API design

Một routine dễ sử dụng thường đặt:

1. Các tham số **bắt buộc**, dùng thường xuyên.
2. Các tham số **tùy chọn phổ biến**.
3. Các tùy chọn nâng cao ở cuối, với default rõ ràng.

Ví dụ:

```sql
CREATE FUNCTION routine344.make_label(
    p_id bigint,
    p_prefix text DEFAULT 'INV',
    p_uppercase boolean DEFAULT false
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE
        WHEN p_uppercase THEN
            upper(p_prefix || '-' || p_id::text)
        ELSE
            p_prefix || '-' || p_id::text
    END;
$$;
```

Các lời gọi:

```sql
SELECT routine344.make_label(1001);
SELECT routine344.make_label(1001, 'ORDER');
SELECT routine344.make_label(
    1001,
    p_uppercase => true
);
```

Kết quả lần lượt:

```text
INV-1001
ORDER-1001
INV-1001
```

Vì mặc định `INV` đã viết hoa, ví dụ thứ ba không thể hiện khác biệt case rõ, nhưng minh họa bỏ qua p_prefix.

Thử:

```sql
SELECT routine344.make_label(
    1001,
    p_prefix => 'invoice',
    p_uppercase => true
);
```

trả `INVOICE-1001`.

### 12.1. Không thêm quá nhiều boolean positional

Lời gọi kiểu:

```sql
SELECT routine344.some_report(1001, true, false, true, false);
```

khó hiểu và dễ đảo nghĩa. Named arguments giảm nhầm lẫn, nhưng nếu số tùy chọn quá nhiều, cần cân nhắc cấu trúc API khác thay vì mở rộng một routine vô hạn.

## 13. Named arguments và hợp đồng tên: tên cũng là API

Một hàm có tham số:

```sql
p_discount_rate numeric
```

có thể được gọi từ nhiều migration, view, script và service:

```sql
SELECT routine344.invoice_total(
    p_unit_price => 100000,
    p_discount_rate => 0.10
);
```

Nếu sau này đổi tên parameter từ `p_discount_rate` thành `p_rate`, những caller dùng named notation sẽ không tự hiểu đó là cùng một tham số.

### 13.1. Tên input parameter là hợp đồng tương thích

PostgreSQL có ràng buộc khi dùng `CREATE OR REPLACE FUNCTION`: không cho phép tùy tiện đổi tên một input parameter đã được đặt tên trong định nghĩa trước đó, vì điều đó có thể phá những named calls hiện hữu.

Đổi tên không chỉ là “refactor cho đẹp”; nó là một thay đổi API ở tầng SQL.

### 13.2. Đặt tên ít phụ thuộc nội bộ

Nên dùng:

```text
p_customer_id
p_effective_date
p_include_cancelled
p_limit
```

thay vì:

```text
p_x
p_tmp
p_v2
p_flag1
```

Tuy nhiên đừng biến tên parameter thành nơi chứa mô tả quá dài; phần contract chi tiết có thể nằm trong COMMENT ON FUNCTION/documentation.

### 13.3. Named calls và đổi thứ tự

Về mặt lời gọi, named notation khiến ánh xạ không phụ thuộc vị trí trong call. Nhưng **đổi thứ tự tham số trong định nghĩa** có thể tạo một chữ ký khác, ảnh hưởng overload/identity/defaults và positional callers. Không coi named calls là lời đảm bảo mọi thay đổi định nghĩa đều backward compatible.

## 14. Nạp chồng (overloading) là gì?

PostgreSQL cho phép nhiều function có **cùng tên trong một schema** nếu danh sách **kiểu tham số đầu vào** khác nhau.

Ví dụ:

```sql
CREATE FUNCTION routine344.display_value(
    p_value integer
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'integer:' || p_value::text;
$$;

CREATE FUNCTION routine344.display_value(
    p_value text
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'text:' || p_value;
$$;
```

Hai function cùng tên `display_value` nhưng tham số đầu vào khác kiểu.

Gọi:

```sql
SELECT routine344.display_value(42::integer);
SELECT routine344.display_value('42'::text);
```

Kết quả:

```text
integer:42
text:42
```

### 14.1. Identity của function

Trong các tình huống thông thường, PostgreSQL xác định function dựa trên:

```text
schema + function name + input argument types
```

Nó **không** dùng return type để làm thành phần phân biệt hai overload.

### 14.2. Overload là lựa chọn thiết kế, không phải polymorphism vô hạn

PostgreSQL có cơ chế giải quyết kiểu và một số polymorphic types, nhưng nạp chồng không có nghĩa hệ thống sẽ luôn đoán đúng overload mà lập trình viên mong muốn.

Mỗi overload bổ sung làm tăng khả năng:

- Gọi nhầm do implicit cast.
- Lời gọi trở nên ambiguous.
- Break changes khi thêm default.
- Nhầm lẫn khi dùng untyped string hoặc NULL.
- Bị shadow/hijack qua search_path trong schema không đáng tin.

## 15. Những gì KHÔNG tạo thành overload khác

### 15.1. Chỉ đổi tên tham số

Hai khai báo:

```sql
CREATE FUNCTION routine344.same_signature(
    p_a integer
)
RETURNS integer
LANGUAGE sql
AS $$
    SELECT p_a;
$$;
```

và:

```sql
-- Chủ đích lỗi: không phải overload mới,
-- vì input argument type vẫn là integer.
CREATE FUNCTION routine344.same_signature(
    p_number integer
)
RETURNS integer
LANGUAGE sql
AS $$
    SELECT p_number * 2;
$$;
```

có cùng identity xét theo input types. Chỉ khác tên tham số nên không tạo hai function độc lập.

### 15.2. Chỉ đổi RETURNS

Không thể định nghĩa đồng thời:

```text
f(integer) RETURNS integer
f(integer) RETURNS text
```

như hai overload cùng schema chỉ phân biệt bằng return type.

Nếu cần hai cách biểu diễn, hãy:

- Đặt tên khác, hoặc
- Dùng kiểu input rõ làm tiêu chí thực sự, nếu hợp nghĩa.

### 15.3. Chỉ đổi default value

Một hàm:

```sql
f(p_x integer, p_y integer DEFAULT 10)
```

và:

```sql
f(p_x integer, p_y integer DEFAULT 20)
```

vẫn có cùng input signature `(integer,integer)`. Default expression không tạo overload thứ hai.

### 15.4. Chỉ đổi OUT arguments

Đối với identity function, các `OUT` parameters không được dùng để phân biệt overload nếu các input types vẫn giống nhau. OUT định hình dữ liệu trả về, không phải đầu vào để chọn routine.

## 16. OUT và INOUT trong function: ảnh hưởng chữ ký

PostgreSQL hỗ trợ các chế độ tham số:

| Mode | Ý nghĩa |
|---|---|
| `IN` | Chỉ đầu vào; mode mặc định |
| `OUT` | Đầu ra; giúp định nghĩa giá trị/cột kết quả |
| `INOUT` | Vừa đầu vào vừa đầu ra |
| `VARIADIC` | Tham số có thể nhận số lượng đối số biến thiên qua mảng |

Ví dụ function có hai output fields:

```sql
CREATE FUNCTION routine344.sum_and_difference(
    IN p_a integer,
    IN p_b integer,
    OUT sum_value integer,
    OUT difference_value integer
)
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    sum_value := p_a + p_b;
    difference_value := p_a - p_b;
END;
$$;
```

Gọi:

```sql
SELECT *
FROM routine344.sum_and_difference(10, 3);
```

Kết quả:

```text
sum_value | difference_value
----------+-----------------
13        | 7
```

### 16.1. Tại sao OUT không tính vào identity?

Với function trên, danh sách input types là:

```text
(integer, integer)
```

không phải:

```text
(integer, integer, integer, integer)
```

Vì hai giá trị OUT không được truyền như input values thông thường khi gọi bằng SELECT.

### 16.2. INOUT khác OUT

`INOUT` có giá trị đầu vào và có thể mang giá trị ra sau khi thực thi. Vì nó tham gia input, kiểu của `INOUT` được tính vào identity.

Một function dùng INOUT phù hợp khi cần một tham số vừa truyền vào vừa cập nhật kết quả, nhưng với API thuần tính toán, RETURNS scalar/record rõ ràng thường dễ hiểu hơn.

### 16.3. Default trên tham số nào?

Trong `CREATE FUNCTION`, giá trị mặc định áp dụng cho input parameters, bao gồm `INOUT`. Không đặt DEFAULT cho `OUT` thuần như thể đó là một input có thể bỏ qua.

## 17. Chọn overload bằng kiểu đầu vào

Khi gọi:

```sql
SELECT routine344.display_value(42::integer);
```

PostgreSQL có một ứng viên khớp chính xác kiểu integer.

Khi gọi:

```sql
SELECT routine344.display_value('42'::text);
```

có một ứng viên khớp chính xác kiểu text.

### 17.1. Explicit cast làm ý định rõ ràng

Cú pháp:

```sql
42::integer
'42'::text
NULL::integer
DATE '2026-11-14'
```

giúp người đọc và PostgreSQL hiểu kiểu input người viết chủ ý.

Với nhiều overload, explicit casts thường quan trọng hơn việc viết SQL ngắn nhất.

### 17.2. Không dựa vào kiểu cột output để chọn overload

Ví dụ:

```sql
SELECT routine344.display_value(42) AS value_text;
```

Alias `value_text` không quyết định overload. Kiểu input mới là yếu tố chính.

Tương tự, việc bạn gán kết quả vào một cột text không có nghĩa PostgreSQL sẽ chọn overload trả text nếu có hai overload cùng input type: hai overload ấy không được tạo chỉ bằng sự khác nhau của RETURNS.

## 18. Chuỗi literal kiểu unknown: nguồn lỗi tinh vi

Trong PostgreSQL, literal chuỗi chưa ép kiểu như:

```sql
'42'
```

ban đầu thường được xử lý dưới kiểu `unknown` để parser chọn kiểu phù hợp trong bối cảnh.

Nếu overload gồm `display_value(integer)` và `display_value(text)`:

```sql
SELECT routine344.display_value('42');
```

đừng vội khẳng định nó sẽ chọn integer vì nội dung “42” nhìn giống số. PostgreSQL có quy trình function type resolution, trong đó unknown string literals và ưu tiên nhóm kiểu có thể dẫn đến lựa chọn khác suy đoán trực giác.

**Cách chắc chắn hơn:** ép kiểu theo hợp đồng API.

```sql
SELECT routine344.display_value('42'::integer);
SELECT routine344.display_value('42'::text);
```

### 18.1. Tại sao implicit cast không phải phép đoán ngữ nghĩa?

Một chuỗi:

```text
00123
```

có thể là mã sản phẩm cần giữ số 0 đầu, không phải integer 123.

Một chuỗi:

```text
2026-11-14
```

có thể là text do người dùng nhập, date hoặc thành phần định danh theo nghiệp vụ.

Những nghĩa này phải được xác định bằng **kiểu dữ liệu trong hợp đồng**, không để parser hoặc implicit cast vô tình quyết định.

## 19. NULL chưa có kiểu và lời gọi mơ hồ

`NULL` không tự chỉ rõ phải là integer, text hay date.

Tạo hai overload:

```sql
CREATE FUNCTION routine344.describe_optional(
    p_value integer
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'integer variant';
$$;

CREATE FUNCTION routine344.describe_optional(
    p_value date
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'date variant';
$$;
```

Gọi:

```sql
-- Có thể bị lỗi ambiguous function call:
SELECT routine344.describe_optional(NULL);
```

Có hai ứng viên hợp lệ về mặt kiểu cho unknown NULL, nhưng PostgreSQL không có đủ thông tin để xác định người gọi muốn integer hay date.

Sửa bằng cast:

```sql
SELECT routine344.describe_optional(NULL::integer);
SELECT routine344.describe_optional(NULL::date);
```

Hai câu trả lần lượt:

```text
integer variant
date variant
```

### 19.1. Không phải mọi lời gọi NULL đều ambiguous

Nếu chỉ có **một overload**, hoặc type resolution đủ thông tin chọn một ứng viên theo luật của PostgreSQL, lời gọi NULL có thể hợp lệ. Điều cần nhớ là **NULL chưa có kiểu có thể gây mơ hồ**, nhất là khi overload phát triển.

### 19.2. Prepared statements và typed parameters

Trong ứng dụng, hãy truyền parameter types rõ ràng theo driver/API thay vì xây SQL string chứa literal không định kiểu, đặc biệt khi tên routine có nhiều overload.

Khi cần, ép kiểu ở SQL:

```sql
SELECT routine344.describe_optional($1::integer);
```

Đây là cú pháp PostgreSQL prepared parameter, không chạy như query ad-hoc không có bind value.

## 20. Overloading theo số lượng tham số và giá trị mặc định

Một câu hỏi quan trọng:

> Nếu đã có `f(integer)`, có thể tạo thêm `f(integer, integer DEFAULT 10)` không?

PostgreSQL có thể **cho phép khai báo**, vì danh sách kiểu input của hai function khác nhau.

Nhưng lời gọi:

```sql
f(5)
```

có thể khớp **cả hai**:

- `f(integer)` nhận một đối số.
- `f(integer,integer DEFAULT 10)` nhận một đối số và dùng default cho đối số thứ hai.

Kết quả có thể là **ambiguous function call**.

### 20.1. Tạo ví dụ mơ hồ tách riêng

```sql
CREATE FUNCTION routine344.default_clash(
    p_x integer
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'one argument';
$$;

CREATE FUNCTION routine344.default_clash(
    p_x integer,
    p_y integer DEFAULT 10
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'two arguments with default';
$$;
```

Lời gọi:

```sql
-- Chủ đích lỗi do xung đột giữa các chữ ký có default:
SELECT routine344.default_clash(5);
```

PostgreSQL cảnh báo rõ trong tài liệu rằng hai function như ví dụ trên có thể làm lời gọi một đối số không phân giải được do ambiguity.

### 20.2. Hai tham số tường minh thì phân biệt được

```sql
SELECT routine344.default_clash(5, 20);
```

chỉ khớp overload nhận hai input types.

### 20.3. Cách sửa thiết kế

Thay vì cố thêm overload trùng tập lời gọi:

**Cách A — Chỉ giữ routine có defaults:**

```sql
DROP FUNCTION routine344.default_clash(integer);

SELECT routine344.default_clash(5);
```

Lúc này chỉ còn overload hai tham số với p_y mặc định 10.

**Cách B — Dùng tên khác:**

```text
format_short(integer)
format_with_options(integer, integer DEFAULT 10)
```

**Cách C — Bỏ default ở overload dài:**

```text
f(integer)
f(integer, integer)
```

Lúc đó lời gọi một đối số không khớp overload hai đối số nếu p_y không có default.

### 20.4. Không thêm overload tùy tiện để backward compatibility

Với function đã có default, thay vì thêm wrapper cùng tên và cùng tập lời gọi, hãy phân tích đầy đủ các lời gọi hiện hữu trước. Một migration tạo thêm overload có thể khiến SQL cũ đang chạy tốt **bỗng thành ambiguous** mà không cần sửa câu SQL ấy.

## 21. Named arguments có luôn giải được overload ambiguity?

Không phải lúc nào.

Ví dụ hai overload:

```sql
CREATE FUNCTION routine344.named_clash(
    p_id integer,
    p_mode text DEFAULT 'short'
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'text mode';
$$;

CREATE FUNCTION routine344.named_clash(
    p_id integer,
    p_limit integer DEFAULT 10
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'integer limit';
$$;
```

Lời gọi chỉ cung cấp:

```sql
-- Có thể mơ hồ vì cả hai overload nhận p_id và
-- bỏ qua tham số tùy chọn còn lại:
SELECT routine344.named_clash(p_id => 7);
```

Nhưng khi chỉ rõ một tên tham số chỉ có trong một overload:

```sql
SELECT routine344.named_clash(
    p_id => 7,
    p_mode => 'full'
);
```

hoặc:

```sql
SELECT routine344.named_clash(
    p_id => 7,
    p_limit => 20
);
```

việc phân biệt có cơ sở rõ ràng hơn.

### 21.1. Đừng phụ thuộc tên để thay thế thiết kế chữ ký tốt

Named notation có thể giúp chọn overload trong những trường hợp phù hợp, nhưng **tập lời gọi hợp lệ và type resolution** vẫn cần rõ. Thêm overload/default có thể gây ambiguity khác ở các caller positional hoặc trong những query dùng unknown literals.

## 22. Sơ đồ phân giải lời gọi function

Cách hình dung đơn giản:

```text
SELECT schema.f(arguments...)
             |
             v
Tìm routines tên f có thể thấy trong schema/search_path
             |
             v
Xét số lượng đối số, named args, defaults, VARIADIC
             |
             v
Xem kiểu input và khả năng coercion
             |
             v
Ưu tiên exact matches và các quy tắc type resolution
             |
      +------+------+
      |             |
   Một lựa chọn    Không/đa lựa chọn
      |             |
      v             v
   Thực thi     "does not exist" / "ambiguous"
```

Đây là sơ đồ học tập, không phải bản sao đầy đủ thuật toán planner/parser. PostgreSQL có quy tắc chi tiết về:

- Schema visibility/search_path.
- Exact input type matches.
- Implicit conversions.
- Unknown literal categories.
- Preferred types.
- Variadic expansion.
- Defaults và overload conflicts.

Khi gặp case phức tạp, tra mục *Function Type Resolution* trong tài liệu chính thức thay vì suy luận bằng “chắc PostgreSQL chọn overload gần nhất”.

## 23. Phân biệt “không tìm thấy routine” và “mơ hồ”

Hai lỗi phổ biến:

### 23.1. Không có ứng viên phù hợp

```text
ERROR: function ... does not exist
```

Nguyên nhân có thể:

- Sai schema hoặc `search_path`.
- Sai tên routine.
- Sai tên named argument.
- Thiếu tham số bắt buộc.
- Số đối số không hợp lệ.
- Kiểu không có implicit cast phù hợp.
- Đang gọi function bằng `SELECT` nhưng thực tế là procedure.

### 23.2. Nhiều ứng viên phù hợp

```text
ERROR: function ... is not unique
HINT: Could not choose a best candidate function.
```

Nguyên nhân thường gặp:

- Có nhiều overload và literal/NULL chưa định kiểu.
- Các overload có defaults tạo lời gọi trùng nhau.
- Search_path nhìn thấy nhiều chữ ký cạnh tranh.
- VARIADIC expansion tạo tập ứng viên có thể giao nhau.
- Implicit coercions dẫn đến nhiều candidates ngang nhau.

### 23.3. Cách xử lý tuần tự

1. Xác nhận object là function hay procedure.
2. Ghi rõ schema của routine.
3. Kiểm tra danh sách overload trong catalog.
4. Kiểm tra tên parameters và defaults.
5. Ép kiểu input có chủ đích.
6. Nếu vẫn mơ hồ, sửa thiết kế overload/defaults.
7. Test lại mọi lời gọi đã phát hành trong ứng dụng.

Đừng “thử cast ngẫu nhiên tới khi chạy” mà chưa biết business type đúng.

## 24. Các overload nhận numeric: integer, bigint, numeric

Đối với tiền, không dùng kiểu theo cảm tính.

Ví dụ:

```sql
CREATE FUNCTION routine344.type_route(
    p_value integer
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'integer';
$$;

CREATE FUNCTION routine344.type_route(
    p_value bigint
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'bigint';
$$;

CREATE FUNCTION routine344.type_route(
    p_value numeric
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'numeric';
$$;
```

Gọi tường minh:

```sql
SELECT routine344.type_route(10::integer);
SELECT routine344.type_route(10::bigint);
SELECT routine344.type_route(10::numeric);
```

Kết quả tương ứng:

```text
integer
bigint
numeric
```

### 24.1. Vì sao input literal quan trọng?

PostgreSQL có kiểu mặc định cho các literal số tùy giá trị/văn cảnh. Literal `10` có thể được nhận diện là integer, còn các literal có phần thập phân thường có quy tắc khác. Với routine API lâu dài, explicit cast giúp tránh phụ thuộc vào những lựa chọn không được người viết chủ ý.

### 24.2. Đừng overload chỉ để “đổi làm tròn tiền”

Nếu các overload nhận numeric và double precision có ngữ nghĩa làm tròn hoặc độ chính xác khác nhau, người gọi có thể vô tình lấy kết quả khác vì input type. Trong nghiệp vụ tài chính, ưu tiên một hợp đồng kiểu tiền rõ và test chuyển đổi.

## 25. Hàm trả cùng kiểu với nhiều overload có nên dùng?

Overloading hữu ích khi cùng một **khái niệm thao tác** áp dụng cho các kiểu đầu vào, ví dụ:

```text
normalize_code(text)
normalize_code(uuid)
```

Nhưng nếu hai overload có **nghiệp vụ hoàn toàn khác**:

```text
process(text)  -> gửi email
process(int)   -> xóa đơn
```

thì một tên chung gây nhầm lẫn, tăng rủi ro bảo mật và giảm khả năng đọc code.

Nên dùng overloading khi:

- Hành vi cùng “ý nghĩa” với các kiểu dữ liệu khác nhau.
- Có lợi ích rõ cho API.
- Các lời gọi có kiểu tường minh hoặc không mơ hồ.
- Không phá callers đã tồn tại.
- Tài liệu mô tả từng overload đầy đủ.

## 26. Default values và backward compatibility khi thay đổi API

Giả sử ban đầu:

```sql
CREATE FUNCTION routine344.shipping_fee(
    p_weight_kg numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT p_weight_kg * 10000;
$$;
```

Muốn thêm lựa chọn “phí đóng gói”.

Có hai cách tiếp cận.

### 26.1. Thêm overload cùng tên với default có thể gây ambiguity

```sql
-- Không nên làm nếu chưa phân tích calls cũ:
CREATE FUNCTION routine344.shipping_fee(
    p_weight_kg numeric,
    p_packaging_fee numeric DEFAULT 5000
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT p_weight_kg * 10000 + p_packaging_fee;
$$;
```

Vì vẫn còn `shipping_fee(numeric)`, lời gọi một tham số có thể thành ambiguous như phần 20.

### 26.2. Một phương án tránh chồng lấn

Giữ function cũ, thêm overload **bắt buộc** hai tham số (không DEFAULT):

```sql
-- Chỉ là phương án thiết kế sau khi xử lý xung đột
-- với overload hai tham số có DEFAULT ở ví dụ trước.
-- Nếu đã tạo overload ấy, phải drop/sửa phù hợp.
CREATE FUNCTION routine344.shipping_fee(
    p_weight_kg numeric,
    p_packaging_fee numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT p_weight_kg * 10000 + p_packaging_fee;
$$;
```

Đây là **khuôn mẫu migration thay thế**, không chạy liên tiếp ngay sau ví dụ 26.1 vì sẽ trùng identity `(numeric,numeric)`. Mục tiêu là phân biệt lời gọi một tham số và hai tham số bằng arity rõ ràng.

Một phương án khác là đặt tên mới `shipping_fee_with_packaging`.

### 26.3. Khi muốn chuyển hoàn toàn sang routine có default

Một migration kiểm soát có thể:

1. Rà soát callers/view/dependencies.
2. Chuẩn bị routine mới trong phiên bản thích hợp.
3. Chuyển lời gọi ứng dụng sang named API hoặc tên mới.
4. Loại overload cũ khi an toàn.
5. Thiết lập defaults sau khi không còn xung đột.
6. Kiểm tra permission, owner, search_path, dependency.
7. Rollout/rollback có kế hoạch.

Không tự drop routine đang được view, trigger, procedure hoặc service phụ thuộc.

## 27. CREATE OR REPLACE FUNCTION thay được gì?

`CREATE OR REPLACE FUNCTION` thường phù hợp để sửa **thân hàm** khi giữ nguyên identity và return type.

Ví dụ:

```sql
CREATE OR REPLACE FUNCTION routine344.make_label(
    p_id bigint,
    p_prefix text DEFAULT 'INV',
    p_uppercase boolean DEFAULT false
)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT CASE
        WHEN p_uppercase THEN
            upper(p_prefix || '-' || lpad(p_id::text, 8, '0'))
        ELSE
            p_prefix || '-' || lpad(p_id::text, 8, '0')
    END;
$$;
```

Identity vẫn là:

```text
routine344.make_label(bigint, text, boolean)
```

Nhưng behavior khác: ID được padding. Đây là thay đổi kết quả trả về cho **mọi caller**, nên vẫn phải đánh giá tương thích nghiệp vụ.

### 27.1. Thay input types không phải replace routine cũ

Nếu đổi:

```text
p_id bigint
```

thành:

```text
p_id text
```

thì chữ ký thay đổi, PostgreSQL coi đó là routine **khác** (nếu CREATE cho phép), không phải update overload bigint.

### 27.2. Thay return type không được qua OR REPLACE đơn giản

Một function có same input signature nhưng từ `RETURNS text` đổi sang `RETURNS integer` không được coi là overload mới và không thể thay return type của function hiện có chỉ bằng `CREATE OR REPLACE FUNCTION`.

Cần migration có kế hoạch, xem dependencies.

### 27.3. Tên tham số cũng có ràng buộc

Như phần 13, PostgreSQL không cho phép tùy tiện đổi tên input parameters đã đặt khi OR REPLACE; điều này bảo vệ named callers.

### 27.4. Quyền sở hữu và grants

OR REPLACE không giống DROP + CREATE. Khi replace cùng identity, owner và permissions được giữ theo semantics PostgreSQL; khi drop rồi create, object mới có thể mất các dependency/grants và cần triển khai lại.

## 28. Function identity và câu lệnh DROP/ALTER

Một function có defaults vẫn được nhận diện theo **danh sách input types đầy đủ**, không theo số đối số mà một caller thực truyền.

Ví dụ `invoice_total` có chữ ký:

```text
routine344.invoice_total(numeric, integer, numeric)
```

Khi cần chỉ định chính xác routine:

```sql
-- Chỉ ví dụ cú pháp, KHÔNG chạy nếu muốn giữ lab:
DROP FUNCTION routine344.invoice_total(
    numeric,
    integer,
    numeric
);
```

Không dùng:

```sql
DROP FUNCTION routine344.invoice_total(numeric);
```

với giả định default cho phép nhận diện function theo một input type; câu lệnh DROP dùng identity đầy đủ, và dạng chỉ một tham số có thể chỉ một function khác hoặc báo không tồn tại.

### 28.1. ALTER FUNCTION cũng dùng identity đầy đủ

Ví dụ:

```sql
ALTER FUNCTION routine344.invoice_total(
    numeric,
    integer,
    numeric
)
COST 50;
```

Tác động tới overload cụ thể, không phải tất cả routine có cùng tên.

### 28.2. DROP FUNCTION không xét tên tham số hoặc OUT thuần

Khi xác định routine để DROP, tên tham số không quyết định identity. OUT-only parameters không phải thành phần phân biệt input signature.

Nên viết đầy đủ schema và input types, đặc biệt trong migration có nhiều overload.

### 28.3. Tránh CASCADE không kiểm soát

`DROP FUNCTION ... CASCADE` có thể kéo theo các đối tượng phụ thuộc. Với production, ưu tiên review dependency và không dùng CASCADE để “dọn lỗi” khi chưa biết những gì sẽ bị xóa.

## 29. Thủ tục (procedure) với giá trị mặc định

Tạo bảng audit lab:

```sql
CREATE TABLE routine344.audit_events (
    audit_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    entity_id bigint NOT NULL,
    event_kind text NOT NULL,
    actor_name text NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now()
);
```

Tạo procedure:

```sql
CREATE PROCEDURE routine344.write_audit(
    p_entity_id bigint,
    p_event_kind text DEFAULT 'CREATED',
    p_actor_name text DEFAULT 'system'
)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO routine344.audit_events(
        entity_id,
        event_kind,
        actor_name
    )
    VALUES (
        p_entity_id,
        p_event_kind,
        p_actor_name
    );
END;
$$;
```

### 29.1. Gọi bằng CALL

```sql
CALL routine344.write_audit(1001);
```

Dùng cả hai defaults.

```sql
CALL routine344.write_audit(1002, 'UPDATED');
```

Dùng default actor_name='system'.

```sql
CALL routine344.write_audit(
    p_entity_id => 1003,
    p_actor_name => 'operator'
);
```

Bỏ qua p_event_kind nên nhận 'CREATED'.

### 29.2. Kiểm tra dữ liệu được thêm

```sql
SELECT
    entity_id,
    event_kind,
    actor_name,
    occurred_at
FROM routine344.audit_events
ORDER BY audit_id;
```

Nếu chạy ba CALL đúng một lần trên bảng trống, dự kiến:

| entity_id | event_kind | actor_name |
|---:|---|---|
| 1001 | CREATED | system |
| 1002 | UPDATED | system |
| 1003 | CREATED | operator |

Không có bảo đảm `occurred_at` luôn khác nhau cho từng hàng nếu các lệnh thuộc cùng transaction vì `now()` có ngữ nghĩa transaction timestamp.

## 30. Procedure cũng có named và mixed notation

`CALL` chấp nhận named arguments với cú pháp tương tự:

```sql
CALL routine344.write_audit(
    p_actor_name => 'batch-worker',
    p_entity_id => 1004,
    p_event_kind => 'RETRIED'
);
```

Và mixed notation:

```sql
CALL routine344.write_audit(
    1005,
    p_actor_name => 'scheduler'
);
```

Trong ví dụ thứ hai, p_event_kind dùng default 'CREATED'.

### 30.1. Phải phân biệt CALL trong SQL với CALL trong PL/pgSQL

Khi procedure có OUT/INOUT parameters, cách truyền/nhận đầu ra khác nhau giữa SQL CALL và khi gọi từ khối PL/pgSQL có biến. Ngoài ra, phiên bản PostgreSQL có những chi tiết riêng với OUT arguments.

Nếu thiết kế procedure xuất nhiều giá trị, hãy kiểm tra tài liệu `CALL` và phiên bản máy chủ. Không mặc định một đoạn CALL SQL và một đoạn CALL trong PL/pgSQL thay thế cơ học cho nhau.

### 30.2. Procedure không trở thành function nhờ OUT

Một procedure có OUT/INOUT có thể trả một hàng kết quả từ CALL, nhưng vẫn không phải routine dùng như biểu thức `SELECT p(...)`.

## 31. INOUT trong procedure: một trường hợp đặc biệt

Ví dụ procedure điều chỉnh một giá trị numeric:

```sql
CREATE PROCEDURE routine344.add_fee(
    INOUT p_amount numeric,
    IN p_fee numeric DEFAULT 0
)
LANGUAGE plpgsql
AS $$
BEGIN
    p_amount := p_amount + p_fee;
END;
$$;
```

Gọi ở SQL:

```sql
CALL routine344.add_fee(
    100::numeric,
    p_fee => 15::numeric
);
```

Kết quả trả qua output parameter `p_amount` có thể hiển thị:

```text
p_amount
--------
115
```

Lời gọi:

```sql
CALL routine344.add_fee(100::numeric);
```

dùng p_fee mặc định 0, cho kết quả 100.

### 31.1. INOUT vừa nằm trong identity vừa là output

Khác `OUT` thuần, `INOUT p_amount numeric` có một giá trị đầu vào. Vì thế nó tham gia danh sách kiểu input để PostgreSQL xác định procedure signature.

### 31.2. Đừng lạm dụng INOUT cho phép tính thuần

Nếu chỉ cần tính tổng không gây side effect, một SQL function trả numeric có thể gọn và tự nhiên hơn. Procedure với INOUT hợp lý khi hợp đồng CALL/procedural workflow thực sự cần.

## 32. Procedure và kiểm soát transaction: giới hạn cần nhớ

Một lợi ích của procedure trong PostgreSQL là có thể thực hiện transaction control **trong một số hoàn cảnh được cho phép**, nhưng không phải mọi CALL đều được COMMIT/ROLLBACK bên trong.

Một số giới hạn điển hình:

- Nếu CALL được thực thi **bên trong explicit transaction block**, procedure không được thực hiện transaction control theo cách top-level cho phép.
- Các procedure được định nghĩa `SECURITY DEFINER` có hạn chế transaction control.
- Các procedure có clause `SET` attached cũng bị hạn chế transaction control.
- Chuỗi CALL/DO và ngữ cảnh lệnh xen giữa có thể ảnh hưởng tính hợp lệ.
- PL/pgSQL và SQL-level CALL có đặc điểm khác khi dùng output variables.

Bài về default/named/overload **không cần** procedure tự COMMIT để học tham số; các ví dụ dùng transaction của caller bình thường.

### 32.1. Không ngụ ý CALL luôn tự commit

`CALL write_audit(...)` không mặc định nghĩa là một transaction nghiệp vụ mới được commit bất kể caller. Nếu ứng dụng đang ở một transaction và rollback, INSERT trong procedure cũng rollback cùng transaction theo cơ chế PostgreSQL.

## 33. Overloading áp dụng cho procedures như thế nào?

Có thể có nhiều procedure cùng tên khi khác danh sách input types.

Ví dụ:

```sql
CREATE PROCEDURE routine344.log_message(
    p_message text
)
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE NOTICE 'message: %', p_message;
END;
$$;

CREATE PROCEDURE routine344.log_message(
    p_code integer
)
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE NOTICE 'code: %', p_code;
END;
$$;
```

Gọi:

```sql
CALL routine344.log_message('hello'::text);
CALL routine344.log_message(42::integer);
```

Kết quả là các thông báo NOTICE tương ứng. Một procedure không tự trở thành overload của function có **cùng tên và input signature** trong cùng schema; PostgreSQL có những giới hạn trùng identity giữa functions và procedures.

### 33.1. Defaults cũng có thể làm procedure calls ambiguous

Nếu có:

```text
log_event(bigint)
log_event(bigint, text DEFAULT 'CREATED')
```

thì một lời gọi `CALL log_event(1)` có thể rơi vào tình huống chồng lấn signature tương tự function.

Không tạo nhiều procedures chỉ khác số tham số khi một trong số đó có defaults mà chưa kiểm tra tất cả callers.

## 34. VARIADIC: nạp chồng theo số đối số có liên quan nhưng khác nhau

`VARIADIC` không phải chỉ là default argument hay overload; nó cho phép một routine nhận số lượng phần tử biến thiên thông qua một array parameter.

Ví dụ:

```sql
CREATE FUNCTION routine344.sum_integers(
    VARIADIC p_values integer[]
)
RETURNS bigint
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT coalesce(sum(x), 0)::bigint
    FROM unnest(p_values) AS t(x);
$$;
```

Gọi:

```sql
SELECT routine344.sum_integers(1, 2, 3);
```

trả 6.

### 34.1. Gọi bằng array

```sql
SELECT routine344.sum_integers(
    VARIADIC ARRAY[1,2,3]::integer[]
);
```

Với named notation, có thể dùng:

```sql
SELECT routine344.sum_integers(
    VARIADIC p_values => ARRAY[1,2,3]::integer[]
);
```

### 34.2. Vì sao named notation với VARIADIC cần chú ý?

Những phần tử được mở rộng từ variadic array **không có tên parameter độc lập**. Vì vậy không thể tùy tiện viết:

```sql
-- Chủ đích lỗi/không phải cú pháp gọi variadic thích hợp:
SELECT routine344.sum_integers(
    p_values => 1
);
```

Để truyền array theo tên, dùng cú pháp `VARIADIC p_values => ARRAY[...]` như tài liệu.

### 34.3. VARIADIC và overload cũng có thể va chạm

Các candidate sau khi mở rộng variadic arguments có thể cạnh tranh với các routine có input types thông thường. PostgreSQL có quy tắc ưu tiên, nhưng không nên dùng variadic chỉ để né thiết kế overload rõ ràng.

## 35. Tham số kiểu anyelement, anyarray và polymorphic functions

PostgreSQL có các pseudo-types hỗ trợ function polymorphism. Những function này linh hoạt theo kiểu đối số, nhưng làm **type resolution** tinh tế hơn.

Ví dụ ý tưởng:

```sql
CREATE FUNCTION routine344.first_value(
    p_values anyarray
)
RETURNS anyelement
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT p_values[1];
$$;
```

Gọi với array cụ thể:

```sql
SELECT routine344.first_value(
    ARRAY[10,20,30]::integer[]
);
```

Kết quả 10.

### 35.1. Khi kiểu không đủ rõ, explicit cast vẫn quan trọng

Một array không có kiểu phần tử phù hợp hoặc NULL chưa định kiểu có thể làm PostgreSQL không suy ra được kiểu polymorphic cần thiết.

### 35.2. Đừng dùng polymorphism chỉ để tránh vài overload hợp nghĩa

Polymorphic function có nhiều quy tắc type inference. Với API trả dữ liệu quan trọng, một vài overload có kiểu cụ thể đôi khi dễ hiểu và ổn định hơn.

## 36. Hàm SQL và PL/pgSQL với named parameters

Đối với SQL function:

```sql
CREATE FUNCTION routine344.double_value(
    p_number integer
)
RETURNS integer
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT p_number * 2;
$$;
```

Đối với PL/pgSQL function:

```sql
CREATE FUNCTION routine344.double_value_pl(
    p_number integer,
    p_multiplier integer DEFAULT 2
)
RETURNS integer
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    RETURN p_number * p_multiplier;
END;
$$;
```

Gọi:

```sql
SELECT routine344.double_value_pl(
    p_multiplier => 3,
    p_number => 10
);
```

Kết quả 30.

### 36.1. Tên tham số dùng trong thân hàm

`p_number` và `p_multiplier` là biến tham số, có thể được dùng trực tiếp trong SQL/PLpgSQL theo quy tắc của language.

Khi viết SQL bên trong PL/pgSQL có tên biến trùng tên cột, có thể gây ambiguity. Thực hành phổ biến là:

- Dùng prefix `p_` cho input variables.
- Dùng alias rõ cho bảng và cột.
- Không dựa vào một tên không được qualify khi có thể là cả column lẫn variable.

### 36.2. $1, $2 theo vị trí khai báo

Trong một số định nghĩa function, có thể tham chiếu tham số theo vị trí `$1`, `$2`. Nhưng khi người gọi truyền named arguments, PostgreSQL vẫn ánh xạ thành các tham số đã khai báo đúng nghĩa.

Thứ tự named arguments **trong lời gọi** không làm định nghĩa `$1` trong thân hàm tự đổi thành tham số được viết đầu tiên ở lời gọi.

## 37. Lời gọi hàm trong SELECT, FROM và WHERE

Một scalar function có thể được gọi như biểu thức:

```sql
SELECT routine344.invoice_total(
    100000,
    p_quantity => 3
);
```

Hoặc trong SELECT của query có bảng:

```sql
WITH line_items(unit_price, quantity) AS (
    VALUES
        (100000::numeric, 2),
        (25000::numeric, 4)
)
SELECT
    unit_price,
    quantity,
    routine344.invoice_total(
        p_unit_price => unit_price,
        p_quantity => quantity
    ) AS line_total
FROM line_items;
```

Kết quả:

| unit_price | quantity | line_total |
|---:|---:|---:|
| 100000 | 2 | 200000.00 |
| 25000 | 4 | 100000.00 |

### 37.1. Default được áp dụng cho từng invocation

Khi dùng scalar function trong một query nhiều hàng, tham số bị bỏ qua được xử lý theo lời gọi trong bối cảnh thực thi/biểu thức tương ứng. Không nên tưởng tượng giá trị default luôn được “thay trực tiếp vào dữ liệu” theo một cách có cùng thời điểm đánh giá cho mọi biểu thức volatile.

### 37.2. Không dùng function volatile làm điều kiện lọc mà thiếu cân nhắc

Nếu một function có side effects, truy vấn chứa nó trong WHERE/ORDER BY có thể khiến số lần/thứ tự đánh giá phụ thuộc kế hoạch. Đừng viết logic nghiệp vụ yêu cầu đúng một side effect mỗi hàng bằng cách nhét một function volatile vào một biểu thức bất kỳ mà không thiết kế transaction và kế hoạch an toàn.

## 38. Query catalog pg_proc: xem overload thật sự đang có

PostgreSQL lưu metadata routine trong hệ thống catalog. Một truy vấn hữu ích:

```sql
SELECT
    n.nspname AS schema_name,
    p.proname AS routine_name,
    p.prokind,
    pg_get_function_identity_arguments(p.oid)
        AS identity_arguments,
    pg_get_function_arguments(p.oid)
        AS full_arguments,
    pg_get_function_result(p.oid)
        AS result_type
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname = 'routine344'
ORDER BY p.proname, identity_arguments;
```

Giải thích:

- `pg_proc` lưu metadata functions, procedures và các dạng routine khác.
- `prokind='f'` thường là function.
- `prokind='p'` thường là procedure.
- `pg_get_function_identity_arguments` hiển thị danh sách đối số dùng để nhận diện routine.
- `pg_get_function_arguments` hiển thị các đối số theo định nghĩa, có thể gồm tên, modes và defaults.
- `pg_get_function_result` phù hợp để xem result type của function.

### 38.1. Xác định overload bằng OID/regprocedure

Ví dụ:

```sql
SELECT
    'routine344.display_value(integer)'::regprocedure
        AS integer_overload,
    'routine344.display_value(text)'::regprocedure
        AS text_overload;
```

`regprocedure` cho phép tham chiếu routine theo tên và input types, rất hữu ích khi cần đọc catalog/định nghĩa một overload cụ thể.

### 38.2. Lấy định nghĩa

```sql
SELECT pg_get_functiondef(
    'routine344.invoice_total(numeric,integer,numeric)'
        ::regprocedure
);
```

Kết quả là DDL biểu diễn định nghĩa function tại server theo các quy tắc formatter của PostgreSQL. Đừng tự đọc `pg_proc.prosrc` rồi cho rằng luôn tái tạo được đầy đủ mọi dạng routine.

## 39. Công cụ psql hỗ trợ xem định nghĩa routine

Trong `psql`, các lệnh meta có thể hữu ích:

```text
\df routine344.*
\df+ routine344.*
\sf routine344.invoice_total(numeric, integer, numeric)
```

Tùy phiên bản `psql`, cú pháp và mức hiển thị có thể khác. Các lệnh bắt đầu bằng dấu `\` là **psql meta-commands**, không phải SQL gửi nguyên văn qua JDBC hoặc những database clients không hỗ trợ psql syntax.

### 39.1. Vì sao nên tra catalog trước khi sửa?

Nếu bạn thấy:

```text
invoice_total(numeric, integer, numeric)
invoice_total(numeric)
```

đừng chỉ đọc một file migration rồi kết luận cái thứ hai “đã cũ, có thể bỏ”. Nó có thể là một overload đang được service khác gọi hoặc gây ambiguity. Cần đối chiếu definitions, grants, dependencies và callers.

## 40. search_path có thể ảnh hưởng đến overload được chọn

Nếu một lời gọi không ghi schema:

```sql
SELECT display_value(42);
```

PostgreSQL tìm routines theo visibility và `search_path`. Một schema khác có thể chứa routine cùng tên, cùng kiểu hoặc kiểu có thể implicit-convert.

Do đó:

- Kết quả resolve có thể khác giữa hai connections cấu hình search_path khác nhau.
- Overload cùng tên ở nhiều schema có quy tắc tìm kiếm/ưu tiên riêng.
- Một schema cho phép người dùng không tin cậy CREATE routine có thể tạo rủi ro security/availability.

### 40.1. Schema-qualified calls

Ưu tiên:

```sql
SELECT routine344.display_value(42::integer);
```

đặc biệt trong:

- Migration scripts.
- SECURITY DEFINER code.
- Admin commands.
- Dịch vụ nhiều tenant.
- Code yêu cầu kết quả luôn ổn định theo kiểu input.

### 40.2. Schema-qualified không loại mọi vấn đề

Ngay trong cùng một schema vẫn có thể có nhiều overload mơ hồ do defaults/implicit casts. Khi đó cần explicit type casts hoặc sửa thiết kế chữ ký.

### 40.3. Tránh schema không đáng tin

Chỉ người đáng tin mới được CREATE objects trong những schema chứa routines được ứng dụng gọi. Hạn chế CREATE trên schema, kiểm tra owner và cấu hình search_path theo nguyên tắc least privilege.

## 41. Quyền EXECUTE và bảo mật routine API

Routine là một API database: người được gọi function/procedure có thể thực thi logic, thậm chí đọc/ghi dữ liệu nếu quyền cho phép.

Kiểm tra quyền:

```sql
SELECT
    p.proname,
    p.prokind,
    p.proacl
FROM pg_proc p
JOIN pg_namespace n ON n.oid=p.pronamespace
WHERE n.nspname='routine344'
ORDER BY p.proname;
```

### 41.1. Không mặc định ai gọi cũng được

PostgreSQL có chính sách default privileges cho functions/procedures, và trong cấu hình phổ biến quyền EXECUTE có thể được grant cho PUBLIC khi tạo routine. Một API có quyền nhạy cảm nên xem xét thu hồi/quy định EXECUTE rõ ràng.

Ví dụ:

```sql
-- Chỉ chạy khi bạn là owner/DBA được ủy quyền và
-- đã xác nhận không cắt quyền cần thiết:
REVOKE ALL ON FUNCTION
    routine344.invoice_total(numeric, integer, numeric)
FROM PUBLIC;
```

Sau đó grant cho vai trò ứng dụng phù hợp theo chính sách thực tế.

### 41.2. SECURITY DEFINER cần cẩn trọng

Một function `SECURITY DEFINER` chạy với quyền của owner theo ngữ nghĩa PostgreSQL. Nếu gọi các object không qualify hoặc để `search_path` chứa schema người không đáng tin, có thể mở ra đường tấn công qua object shadowing.

Khi thực sự cần SECURITY DEFINER:

- Chỉ dùng khi có yêu cầu.
- Chọn schema/search_path an toàn.
- Qualify object names quan trọng.
- Giới hạn EXECUTE theo role.
- Đánh giá dynamic SQL và input.
- Kiểm thử quyền thực tế của người gọi.

Không đánh dấu routine là SECURITY DEFINER chỉ để “không còn lỗi permission”.

### 41.3. Defaults không vượt qua kiểm tra quyền

Một default parameter không biến function thành quyền truy cập miễn phí. Các thao tác trong routine vẫn tuân thủ security invoker/definer, grants, RLS và transaction rules tương ứng.

## 42. Named parameters, SQL injection và dynamic SQL

Named arguments giúp đọc lời gọi, nhưng **không tự ngăn SQL injection**.

An toàn hơn khi dùng bind parameters:

```sql
SELECT routine344.invoice_total(
    p_unit_price => $1::numeric,
    p_quantity => $2::integer,
    p_discount_rate => $3::numeric
);
```

Ứng dụng bind các giá trị qua driver. Đừng ghép chuỗi input trực tiếp thành SQL:

```text
"SELECT ... p_name => '" + userInput + "'"
```

### 42.1. Named arguments không phải placeholder của client

`p_unit_price => ...` là tên **tham số function**; `$1` hoặc placeholder theo driver là **bind parameter** của câu SQL. Hai thứ giải quyết hai mục đích khác nhau.

### 42.2. Dynamic SQL trong PL/pgSQL

Nếu cần dynamic identifier, phải dùng cơ chế quote/format thích hợp như `format('%I', identifier)` và truyền giá trị qua `USING` khi phù hợp. Không biến tên routine hoặc tên cột do client cung cấp thành SQL chưa kiểm tra.

## 43. Default, NULL và xử lý giá trị không hợp lệ

Thiết kế tham số cần phân biệt:

1. Bị bỏ qua → dùng default.
2. Được truyền NULL → nhận SQL NULL.
3. Giá trị có mặt nhưng ngoài miền hợp lệ → nên từ chối theo hợp đồng.
4. Giá trị đúng kiểu nhưng sai nghĩa (ví dụ quantity=0 trong mua hàng) → cần validation nghiệp vụ.

### 43.1. Một function kiểm tra đơn giá/số lượng

Ví dụ dùng PL/pgSQL:

```sql
CREATE FUNCTION routine344.safe_total(
    p_unit_price numeric,
    p_quantity integer DEFAULT 1,
    p_discount_rate numeric DEFAULT 0
)
RETURNS numeric
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_unit_price IS NULL OR p_unit_price < 0 THEN
        RAISE EXCEPTION
            'unit price must be a nonnegative number'
            USING ERRCODE = '22023';
    END IF;

    IF p_quantity IS NULL OR p_quantity <= 0 THEN
        RAISE EXCEPTION
            'quantity must be a positive integer'
            USING ERRCODE = '22023';
    END IF;

    IF p_discount_rate IS NULL
       OR p_discount_rate < 0
       OR p_discount_rate > 1 THEN
        RAISE EXCEPTION
            'discount rate must be between 0 and 1'
            USING ERRCODE = '22023';
    END IF;

    RETURN round(
        p_unit_price * p_quantity * (1 - p_discount_rate),
        2
    );
END;
$$;
```

### 43.2. Lời gọi

```sql
SELECT routine344.safe_total(
    100000,
    p_discount_rate => 0.05
);
```

Kết quả: 95000.00.

### 43.3. Bỏ qua khác NULL

```sql
-- Sử dụng default 1:
SELECT routine344.safe_total(100000);

-- Chủ đích lỗi validation:
SELECT routine344.safe_total(
    100000,
    p_quantity => NULL::integer
);
```

Câu thứ hai không dùng default; hàm thấy NULL và chủ động báo lỗi. Đây là cách bảo vệ hợp đồng “quantity phải dương”.

## 44. Kiểm thử với bảng dữ liệu thực hành

Tạo một bảng nhỏ để kết nối function với một query có dữ liệu:

```sql
CREATE TABLE routine344.order_lines (
    line_id integer PRIMARY KEY,
    unit_price numeric NOT NULL CHECK (unit_price >= 0),
    quantity integer NOT NULL CHECK (quantity > 0),
    discount_rate numeric NOT NULL DEFAULT 0
        CHECK (discount_rate BETWEEN 0 AND 1)
);

INSERT INTO routine344.order_lines(
    line_id, unit_price, quantity, discount_rate
)
VALUES
    (1, 100000, 2, 0.10),
    (2, 50000, 1, 0.00),
    (3, 200000, 3, 0.25);
```

Gọi hàm bằng named arguments từ cột:

```sql
SELECT
    line_id,
    unit_price,
    quantity,
    discount_rate,
    routine344.safe_total(
        p_unit_price => unit_price,
        p_quantity => quantity,
        p_discount_rate => discount_rate
    ) AS line_total
FROM routine344.order_lines
ORDER BY line_id;
```

Kết quả dự kiến:

| line_id | unit_price | quantity | discount_rate | line_total |
|---:|---:|---:|---:|---:|
| 1 | 100000 | 2 | 0.10 | 180000.00 |
| 2 | 50000 | 1 | 0.00 | 50000.00 |
| 3 | 200000 | 3 | 0.25 | 450000.00 |

### 44.1. Ở đây default không được dùng cho tham số discount

Vì câu query truyền `discount_rate` từ cột cho mọi hàng, PostgreSQL không dùng default p_discount_rate=0. Nếu muốn dùng default cho một trường hợp, query phải bỏ đối số hoặc tự quyết định logic gọi phù hợp; việc truyền NULL không tự dùng default.

## 45. Kết hợp defaults và function trong biểu thức truy vấn

Một ví dụ cần một mức chiết khấu cố định cho tất cả hàng:

```sql
SELECT
    line_id,
    routine344.safe_total(
        unit_price,
        p_quantity => quantity,
        p_discount_rate => 0.05
    ) AS promo_total
FROM routine344.order_lines
ORDER BY line_id;
```

### 45.1. Một API tốt cho report

Nếu report thường dùng cùng discount 5%, có thể tạo wrapper với tên rõ:

```sql
CREATE FUNCTION routine344.promo_total_5_percent(
    p_unit_price numeric,
    p_quantity integer DEFAULT 1
)
RETURNS numeric
LANGUAGE sql
AS $$
    SELECT routine344.safe_total(
        p_unit_price => p_unit_price,
        p_quantity => p_quantity,
        p_discount_rate => 0.05
    );
$$;
```

Không nên tạo wrapper cùng tên `safe_total` có một/two input types chồng lấn với defaults của function gốc vì có thể gây ambiguity.

### 45.2. Cần giữ một nơi định nghĩa business rule

Nếu nhiều overload/wrappers cùng sao chép công thức giảm giá, thay đổi chính sách có thể làm kết quả không nhất quán. Khi cần, route qua một core function có validation rõ hoặc dịch vụ nghiệp vụ có quyền phù hợp.

## 46. Default arguments và hiệu năng

Default/named arguments chủ yếu là **cơ chế API và phân giải lời gọi**. Chúng không tự làm một function nhanh hơn.

Những yếu tố hiệu năng thật sự có thể là:

- Function SQL có được inlining trong tình huống cụ thể không.
- Function gọi mỗi hàng hay một lần.
- Hàm có truy vấn bảng lớn hoặc dùng I/O không.
- Volatility/parallel-safety đã khai báo đúng chưa.
- Kế hoạch thực thi, index, selectivity.
- Chi phí các default expressions.
- Số lượng overload có làm call resolution phức tạp hoặc ambiguous không.
- Tác động PL/pgSQL/SPI và các câu query bên trong.
- Mức độ đồng thời và contention nếu procedure ghi dữ liệu.

### 46.1. Không khẳng định SQL function luôn được inline

PostgreSQL có những tối ưu với SQL functions trong một số ngữ cảnh, nhưng còn phụ thuộc nội dung, đặc tính và kế hoạch. Không phải mọi SQL function đều bị thay bằng biểu thức trong caller.

### 46.2. EXPLAIN dùng đúng mục tiêu

Ví dụ:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    routine344.safe_total(
        unit_price,
        p_quantity => quantity,
        p_discount_rate => discount_rate
    )
FROM routine344.order_lines;
```

Quan sát actual rows/time/buffers và đo workload đại diện. Bảng lab ba hàng chỉ đủ minh họa cú pháp, không đủ benchmark production.

### 46.3. Không gắn IMMUTABLE sai để ép tăng tốc

Nếu một function phụ thuộc now(), config thay đổi, bảng dữ liệu hay trạng thái phiên, cần khai báo volatility đúng theo semantics. Khai báo sai có thể tạo kết quả không đúng vì optimizer được phép dùng giả định sai ấy.

## 47. Đánh giá tương thích khi thêm overload vào hệ thống đang chạy

Trước migration, cần thu thập:

```text
Tên routine và schema
Mọi overload hiện hữu
Input names/types/modes/default expressions
Return types
Các lời gọi từ application/views/jobs/triggers
Thứ tự search_path của application
Những literal chưa cast kiểu
Quyền EXECUTE và owner
Các hàm SECURITY DEFINER liên quan
Khả năng rollback
```

### 47.1. Những thay đổi dễ gây break

| Thay đổi | Rủi ro |
|---|---|
| Đổi tên input parameter | Làm hỏng named callers |
| Đổi input type | Tạo routine mới, caller có thể chọn overload khác |
| Thêm overload có trailing DEFAULT | Gây ambiguous calls cũ |
| Thay default expression | Caller bỏ tham số nhận hành vi mới |
| Đổi thứ tự tham số | Positional callers đổi nghĩa |
| Đổi return type | Không thay đơn giản bằng OR REPLACE, ảnh hưởng dependencies |
| Đổi schema/search_path | Routine được resolve khác |
| Thay volatility/security | Thay semantics và quyền thực thi |
| DROP/CREATE lại function | Có thể mất grants/dependencies |
| Thêm overload numeric/text | Literal unknown chọn khác dự kiến |
| Đổi tên cột OUT | Thay cấu trúc kết quả cho consumers |

### 47.2. Quy trình migration an toàn

1. Liệt kê signatures từ `pg_proc`.
2. Thu thập SQL calls hiện có.
3. Phân loại positional/named/mixed callers.
4. Kiểm tra tính duy nhất của resolution theo input types thực.
5. Chạy test với literals, NULL và bind parameters.
6. Đánh giá quyền và search_path.
7. Triển khai bằng migration có version.
8. Quan sát lỗi `42883` (undefined function) và `42725` (ambiguous function) khi phù hợp.
9. Giữ khả năng rollback không xóa mất dependencies ngoài ý muốn.
10. Dọn overload cũ sau giai đoạn tương thích được kiểm soát.

Mã SQLSTATE nêu trong phần này là những mã lỗi có thể gặp; lỗi thực tế tùy câu SQL và kiểu xung đột.

## 48. Bài tập thực hành có đáp án

Các bài dùng schema `routine344`. Một số câu cố ý minh họa lỗi; chỉ chạy trong môi trường thử nghiệm.

### Bài 1. Tính một sản phẩm 100000, không giảm giá

```sql
SELECT routine344.invoice_total(100000::numeric);
```

**Đáp án:** 100000.00.

### Bài 2. Tính ba sản phẩm, discount mặc định

```sql
SELECT routine344.invoice_total(
    100000::numeric,
    3
);
```

**Đáp án:** 300000.00.

### Bài 3. Tính hai sản phẩm giảm 10%

```sql
SELECT routine344.invoice_total(
    100000::numeric,
    2,
    0.10::numeric
);
```

**Đáp án:** 180000.00.

### Bài 4. Bỏ quantity nhưng đặt discount 20%

```sql
SELECT routine344.invoice_total(
    p_unit_price => 100000,
    p_discount_rate => 0.20
);
```

**Đáp án:** 80000.00.

### Bài 5. Đảo thứ tự named arguments

```sql
SELECT routine344.invoice_total(
    p_discount_rate => 0.20,
    p_unit_price => 100000
);
```

**Đáp án:** vẫn 80000.00.

### Bài 6. Mixed notation

```sql
SELECT routine344.invoice_total(
    100000,
    p_discount_rate => 0.20
);
```

**Đáp án:** 80000.00.

### Bài 7. Named trước positional có hợp lệ không?

```sql
-- Chủ đích lỗi:
SELECT routine344.invoice_total(
    p_unit_price => 100000,
    2
);
```

**Đáp án:** không; positional arguments phải đứng trước named arguments trong mixed notation.

### Bài 8. Có thể cung cấp hai lần p_quantity không?

```sql
-- Chủ đích lỗi:
SELECT routine344.invoice_total(
    100000,
    2,
    p_quantity => 3
);
```

**Đáp án:** không, p_quantity đã được truyền ở vị trí thứ hai.

### Bài 9. Giá trị default có áp dụng khi truyền explicit NULL không?

**Đáp án:** không. Truyền NULL là cung cấp đối số có giá trị SQL NULL; bỏ qua mới dùng default.

### Bài 10. Hàm STRICT nhận NULL ở một tham số thì sao?

**Đáp án:** một function được đánh dấu STRICT có thể trả NULL theo hợp đồng `RETURNS NULL ON NULL INPUT`. Default không thay thế explicit NULL.

### Bài 11. Vì sao các input sau default cũng phải có default?

**Đáp án:** PostgreSQL yêu cầu trailing default parameters để positional notation có nghĩa rõ.

### Bài 12. Cách khai báo này có hợp lệ không?

```sql
-- Chủ đích lỗi:
CREATE FUNCTION routine344.bad(
    p_a integer DEFAULT 1,
    p_b integer
)
RETURNS integer LANGUAGE sql
AS $$ SELECT p_a + p_b; $$;
```

**Đáp án:** không vì p_b là input bắt buộc đứng sau tham số có default.

### Bài 13. CURRENT_TIMESTAMP default được cố định lúc CREATE không?

**Đáp án:** không; default expression được dùng khi lời gọi bỏ đối số. CURRENT_TIMESTAMP phản ánh thời điểm bắt đầu transaction theo PostgreSQL.

### Bài 14. Tạo hai overload integer và text

```sql
SELECT routine344.display_value(42::integer);
SELECT routine344.display_value('42'::text);
```

**Đáp án:** lần lượt `integer:42` và `text:42`.

### Bài 15. Có thể overload chỉ bằng return type không?

**Đáp án:** không. Identity function xét tên và input types, không dùng kiểu trả về để phân biệt.

### Bài 16. Có thể overload chỉ bằng tên parameter không?

**Đáp án:** không. `f(p_id integer)` và `f(p_number integer)` có cùng input signature.

### Bài 17. Vì sao `display_value('42')` không nhất thiết gọi overload integer?

**Đáp án:** literal chuỗi ban đầu có kiểu unknown; PostgreSQL áp dụng type resolution. Hãy dùng `'42'::integer` nếu muốn integer overload.

### Bài 18. NULL với overload integer/date?

```sql
-- Chủ đích lỗi/mơ hồ:
SELECT routine344.describe_optional(NULL);
```

**Đáp án:** phải ép kiểu rõ khi nhiều overload đều có thể khớp:

```sql
SELECT routine344.describe_optional(NULL::integer);
```

### Bài 19. Vì sao default_clash(5) nguy hiểm?

**Đáp án:** cả overload nhận một integer và overload nhận (integer, integer DEFAULT 10) đều có thể phù hợp với một đối số → ambiguous.

### Bài 20. Cách tránh default_clash?

**Đáp án:** chỉ giữ một routine có default, bỏ default ở overload dài hoặc dùng tên khác.

### Bài 21. named_clash(p_id=>7) có chắc chọn đúng không?

**Đáp án:** không. Hai overload cùng nhận p_id và bỏ được tham số thứ hai nên có thể ambiguous.

### Bài 22. Chọn overload có p_limit

```sql
SELECT routine344.named_clash(
    p_id => 7,
    p_limit => 25
);
```

**Đáp án:** hướng tới overload có p_limit integer.

### Bài 23. Function có OUT parameters có input signature gì?

```text
sum_and_difference(IN integer, IN integer, OUT integer, OUT integer)
```

**Đáp án:** input signature là `(integer,integer)`.

### Bài 24. Gọi procedure write_audit dùng mọi defaults

```sql
CALL routine344.write_audit(1234);
```

**Đáp án:** ghi entity_id 1234 với event_kind='CREATED', actor_name='system' (trong lab).

### Bài 25. Gọi procedure bỏ event_kind nhưng truyền actor

```sql
CALL routine344.write_audit(
    p_entity_id => 1234,
    p_actor_name => 'batch'
);
```

**Đáp án:** event_kind dùng default 'CREATED'.

### Bài 26. Procedure gọi bằng SELECT được không?

**Đáp án:** procedure dùng `CALL`, không dùng như một function trong SELECT.

### Bài 27. INOUT add_fee mặc định p_fee=0

```sql
CALL routine344.add_fee(100::numeric);
```

**Đáp án:** output p_amount=100.

### Bài 28. INOUT add_fee với phí 12.5

```sql
CALL routine344.add_fee(
    p_amount => 100::numeric,
    p_fee => 12.5::numeric
);
```

**Đáp án:** output p_amount=112.5.

### Bài 29. VARIADIC nhận 4 số

```sql
SELECT routine344.sum_integers(1, 2, 3, 4);
```

**Đáp án:** 10.

### Bài 30. VARIADIC gọi với named array

```sql
SELECT routine344.sum_integers(
    VARIADIC p_values => ARRAY[4,5,6]::integer[]
);
```

**Đáp án:** 15.

### Bài 31. Function identity của invoice_total là gì?

**Đáp án:** `routine344.invoice_total(numeric,integer,numeric)`, bất kể caller có thể bỏ quantity/discount nhờ defaults.

### Bài 32. Dùng DROP FUNCTION với một numeric có xóa invoice_total không?

**Đáp án:** không thể dùng chữ ký rút gọn làm identity thay cho ba input types. Trong migration phải chỉ rõ đầy đủ types của routine cần xóa.

### Bài 33. Vì sao OR REPLACE không thay được return type?

**Đáp án:** PostgreSQL không nhận return type là chiều overload mới. Muốn thay cần migration/drop-create hoặc tên mới, xử lý dependencies.

### Bài 34. Vì sao đổi tên p_discount_rate là breaking change?

**Đáp án:** named callers truyền theo đúng tên ấy, và PostgreSQL có ràng buộc bảo vệ khi OR REPLACE.

### Bài 35. Khi function không tìm thấy, kiểm tra gì?

**Đáp án:** tên/schema, input types, named parameter names, defaults, arity, search_path và loại routine function/procedure.

### Bài 36. Khi function call ambiguous, xử lý gì?

**Đáp án:** xem overloads, cast input, loại chồng lấn mặc định hoặc thay đổi tên/chữ ký hợp lý.

### Bài 37. Vì sao nên schema-qualify routine trong SECURITY DEFINER?

**Đáp án:** giảm nguy cơ chọn nhầm object do search_path và schema không đáng tin; vẫn cần đặt search_path an toàn và kiểm soát quyền.

### Bài 38. Named parameters có ngăn SQL injection không?

**Đáp án:** không; dùng bind parameters và kiểm soát dynamic SQL phù hợp.

### Bài 39. Function safe_total(100000,p_quantity=>NULL::integer) cho kết quả gì?

**Đáp án:** hàm chủ động báo lỗi invalid_parameter_value (22023), không lấy default 1.

### Bài 40. Khi nào nên dùng overload thay vì default?

**Đáp án:** khi **kiểu/arity khác nhau thực sự biểu đạt biến thể cùng một thao tác** mà không tạo ambiguity. Nếu chỉ cần tùy chọn bổ sung, default ở một routine thường dễ hiểu hơn nhiều overload.

## 49. Lỗi phổ biến và cách tránh

### Lỗi 1 — Tưởng DEFAULT là giá trị khi đối số NULL

Default chỉ được dùng khi tham số không được cung cấp, không tự thay explicit NULL.

### Lỗi 2 — Đặt tham số bắt buộc sau tham số có default

PostgreSQL không cho phép thứ tự này đối với input parameters.

### Lỗi 3 — Dùng positional để nhảy qua tham số giữa

Positional only được bỏ tham số mặc định từ bên phải; muốn bỏ tham số giữa, dùng named.

### Lỗi 4 — Viết named trước positional

Mixed notation yêu cầu positional arguments trước named arguments.

### Lỗi 5 — Truyền cùng parameter bằng positional và named

Một tham số không thể nhận hai giá trị trong cùng lời gọi.

### Lỗi 6 — Viết sai tên named parameter

Named call đòi tên parameter đúng như hợp đồng routine.

### Lỗi 7 — Dùng := như phép gán trong SQL call

`:=` có thể được hỗ trợ theo legacy named notation, nhưng dùng `=>` giúp rõ hơn.

### Lỗi 8 — Tưởng named argument là bind parameter

Named arguments ánh xạ vào function inputs; bind parameters là phần ứng dụng truyền dữ liệu an toàn vào câu SQL.

### Lỗi 9 — Nghĩ hai functions khác RETURNS là hai overload

Không thể overload chỉ bằng return type.

### Lỗi 10 — Nghĩ đổi tên input parameter tạo overload mới

Names không làm input signature khác.

### Lỗi 11 — Thêm overload với trailing DEFAULT trùng tập lời gọi

Lời gọi cũ có thể thành ambiguous.

### Lỗi 12 — Tự tin PostgreSQL chọn overload theo giá trị trông giống số

Untyped string literals và implicit casts có quy tắc; explicit casts giúp xác định ý định.

### Lỗi 13 — Truyền NULL chưa cast khi có nhiều overload

Có thể gây ambiguity; dùng NULL::desired_type.

### Lỗi 14 — Dùng chữ ký rút gọn khi DROP function có defaults

DROP/ALTER dùng identity theo toàn bộ input types, không theo số đối số tối thiểu.

### Lỗi 15 — OR REPLACE rồi đổi RETURN TYPE

Không phải một thay đổi đơn giản được cho phép trên routine cùng identity.

### Lỗi 16 — Refactor tên parameter mà quên named callers

Đổi tên là API breaking change.

### Lỗi 17 — Gọi procedure bằng SELECT

Phải dùng CALL; function dùng SELECT hoặc trong biểu thức.

### Lỗi 18 — Nghĩ CALL luôn cho phép COMMIT trong procedure

Transaction-control còn phụ thuộc ngữ cảnh CALL, explicit transaction block, SECURITY DEFINER và các giới hạn khác.

### Lỗi 19 — Tưởng OUT parameters tham gia overload function như IN

OUT-only không phân biệt function identity; INOUT tham gia input.

### Lỗi 20 — Gọi VARIADIC bằng named scalar bình thường

Các phần tử mở rộng không có tên riêng; dùng `VARIADIC name => array_expression` nếu muốn named array.

### Lỗi 21 — Không kiểm tra schema/search_path

Có thể gọi nhầm overload khác schema hoặc bị ảnh hưởng bởi objects trong schema không đáng tin.

### Lỗi 22 — Khai báo IMMUTABLE cho hàm phụ thuộc thời gian/bảng

Có thể làm optimizer dựa vào giả định sai và trả kết quả không mong muốn.

### Lỗi 23 — Tách validation khỏi routine rồi tin input luôn đúng

Defaulted quantity=1 không có nghĩa caller sẽ không gửi 0, NULL hoặc số âm.

### Lỗi 24 — Nhầm default expression được cố định lúc CREATE

Các expression động có ngữ nghĩa thời điểm đánh giá riêng; CURRENT_TIMESTAMP không bị đóng băng tại thời điểm tạo function.

### Lỗi 25 — Không test gọi hàm từ driver với typed binds

ORM/driver có thể truyền types khác literal ở SQL console, dẫn đến resolution khác.

### Lỗi 26 — Drop routine và không xem dependencies/grants

Một function được view, trigger, script hoặc service dùng có thể gây lỗi vận hành nếu xóa không có kế hoạch.

### Lỗi 27 — Dùng SECURITY DEFINER để “sửa lỗi quyền” nhanh

Có thể mở đường privilege escalation nếu thiết kế quyền/search_path không an toàn.

### Lỗi 28 — Chỉ benchmark trên bảng vài hàng

Không thể suy ra chi phí function calls ở workload thật từ fixture nhỏ.

## 50. Checklist thiết kế routine có tham số tốt

| Câu hỏi cần xác định | Vì sao quan trọng |
|---|---|
| Routine là function hay procedure? | SELECT vs CALL, return và transaction rules |
| Chọn schema/name có rõ nghĩa không? | Tránh trùng built-in/routine khác |
| Input types có sát nghiệp vụ không? | Tránh implicit cast sai |
| Tham số nào thật sự bắt buộc? | Hợp đồng rõ |
| Tất cả input sau default đều có default? | DDL hợp lệ |
| Có cần bỏ qua tham số ở giữa không? | Named notation |
| Named parameters có tên ổn định không? | Backward compatibility |
| Đã phân biệt omit và explicit NULL? | Không phá nghĩa default |
| Default expression có phụ thuộc thời gian/side effect? | Volatility và consistency |
| Các kiểu input có gây overload ambiguity? | Runtime/query parse correctness |
| Có overload cùng arity nhưng types convert được? | Cần cast cụ thể |
| Có overload chồng với defaulted arity? | Lời gọi cũ bị ambiguous |
| Return type có đang bị dùng làm cách phân biệt overload? | Không hợp lệ |
| OUT/INOUT/VARIADIC đã hiểu đúng? | Chữ ký và named invocation |
| Có validation cho giá trị ngoài miền? | Data/business correctness |
| Có test NULL, unknown literals và driver binds? | Mismatch giữa environments |
| Có schema-qualified calls trong code nhạy cảm? | Rõ resolution và bảo mật |
| search_path và CREATE privileges đã kiểm soát? | Tránh shadow/hijack |
| EXECUTE permissions có phù hợp role? | Least privilege |
| SECURITY DEFINER có thật sự cần? | Tránh privilege escalation |
| Có xem dependency trước DROP/REPLACE? | Tránh lỗi downstream |
| Có catalog inspection và migration rollback? | Vận hành an toàn |
| Có đo workload nếu function gọi trên nhiều hàng? | Hiệu năng thật |
| Tài liệu có ví dụ positional/named/mixed? | Người gọi hiểu contract |

## 51. Bảng tra cứu nhanh

| Bài toán | Cú pháp | Chú ý |
|---|---|---|
| Giá trị mặc định | `p_qty integer DEFAULT 1` | Chỉ dùng khi bỏ đối số |
| Bỏ tham số cuối | `f(100)` | Positional omits từ phải qua trái |
| Truyền theo tên | `f(p_qty => 3)` | Phải đúng tên input |
| Bỏ tham số giữa | `f(p_a => 1, p_c => 3)` | p_b phải có default |
| Kết hợp positional/named | `f(1, p_c => 3)` | Positional đi trước named |
| Cú pháp cũ | `p_c := 3` | Nên ưu tiên `=>` |
| Không dùng default khi truyền NULL | `f(NULL::integer)` | NULL là giá trị tường minh |
| Function SQL | `SELECT schema.f(...)` | Có return |
| Procedure | `CALL schema.p(...)` | Có thể ghi dữ liệu |
| Nạp chồng | `f(integer)` và `f(text)` | Input types khác nhau |
| Không phải nạp chồng | `f(x integer)` và `f(y integer)` | Tên input không tạo chữ ký |
| Không overload theo return type | `RETURNS text/integer` | Không có tính phân biệt |
| Default/overload clash | `f(int)` và `f(int,int DEFAULT 1)` | Có thể ambiguous |
| Ép kiểu gọi overload | `f(NULL::integer)` | Tránh unknown |
| Procedure INOUT | `CALL p(100, p_fee => 1)` | Nhận output theo CALL |
| VARIADIC named | `f(VARIADIC p_arr => ARRAY[1,2])` | Không named mỗi phần tử |
| Thay thân hàm | `CREATE OR REPLACE FUNCTION` | Không đổi return type/input identity |
| Xác định routine | `pg_get_function_identity_arguments(oid)` | Xem input signature |
| DROP overload | `DROP FUNCTION f(type1,type2)` | Chỉ rõ đủ input types |
| Bảo mật | Schema-qualified + grants + safe search_path | Đặc biệt SECURITY DEFINER |

## 52. Tài liệu PostgreSQL chính thức

Đối chiếu với **phiên bản PostgreSQL đang sử dụng**, vì một số chi tiết procedures, OUT arguments và cú pháp có thể khác giữa các phiên bản:

- [Calling Functions](https://www.postgresql.org/docs/current/sql-syntax-calling-funcs.html): positional, named và mixed notation.
- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html): DEFAULT, IN/OUT/INOUT, overloading, CREATE OR REPLACE.
- [Query Language (SQL) Functions](https://www.postgresql.org/docs/current/xfunc-sql.html): SQL function examples, default arguments, VARIADIC.
- [Function Type Resolution](https://www.postgresql.org/docs/current/typeconv-func.html): cách chọn overload, unknown literals, implicit casts và security implications.
- [CREATE PROCEDURE](https://www.postgresql.org/docs/current/sql-createprocedure.html): parameters, defaults và procedure properties.
- [CALL](https://www.postgresql.org/docs/current/sql-call.html): gọi procedures, named parameters, output và transaction-control conditions.
- [PL/pgSQL](https://www.postgresql.org/docs/current/plpgsql.html): bodies, biến tham số, RETURN và CALL.
- [DROP FUNCTION](https://www.postgresql.org/docs/current/sql-dropfunction.html): cách chỉ định signature để xóa một overload.
- [ALTER FUNCTION](https://www.postgresql.org/docs/current/sql-alterfunction.html): thay đổi routine properties/owner/schema.
- [Functions and Operators](https://www.postgresql.org/docs/current/functions.html): kiểu kết quả và tích hợp function vào câu SQL.
- [Date/Time Functions](https://www.postgresql.org/docs/current/functions-datetime.html): CURRENT_TIMESTAMP, now() và transaction time.
- [System Catalog pg_proc](https://www.postgresql.org/docs/current/catalog-pg-proc.html): metadata routines.
- [Function Security](https://www.postgresql.org/docs/current/perm-functions.html): bảo vệ các hàm và search_path trong ngữ cảnh quyền.

Các ví dụ trong bài là hướng dẫn học tập. Chưa có thao tác SQL nào trong bài được thực thi trên cơ sở dữ liệu thực tế khi soạn Markdown; với production cần chạy kiểm thử/migration review riêng.

## 53. Tổng kết: ba cơ chế và một nguyên tắc thiết kế

**Giá trị mặc định** làm cho một API có các tham số tùy chọn:

```sql
CREATE FUNCTION f(
    p_required integer,
    p_optional integer DEFAULT 10
) ...
```

**Named arguments** làm rõ một lời gọi và cho phép bỏ qua các tham số tùy chọn ở giữa:

```sql
SELECT routine344.invoice_total(
    p_unit_price => 100000,
    p_discount_rate => 0.05
);
```

**Overloading** dùng cùng tên routine cho nhiều **kiểu tham số đầu vào**:

```sql
display_value(integer)
display_value(text)
```

Nhưng phải nhớ:

```text
Bỏ tham số               != truyền NULL
Named argument name       != bind placeholder
Input type khác           có thể là overload
Return type khác          không tạo overload
Parameter name khác       không tạo overload
DEFAULT + overload        có thể tạo ambiguity
Function call             SELECT
Procedure call            CALL
```

### Các nguyên tắc nên áp dụng

1. Đặt required parameters trước, optional/default parameters sau.
2. Với nhiều lựa chọn, ưu tiên named notation `=>` cho tính dễ đọc.
3. Không thay default khi người gọi truyền explicit NULL, trừ khi function chủ động định nghĩa fallback.
4. Tránh thêm overload tạo **cùng tập lời gọi hợp lệ** với một function đã có DEFAULT.
5. Dùng casts rõ ràng khi làm việc với NULL, literal unknown hoặc nhiều overload gần nhau.
6. Coi tên input parameters của named API là một **cam kết tương thích**.
7. Không dùng return type để phân biệt function overloads.
8. Xác định routine bằng danh sách **input types đầy đủ** khi DROP/ALTER/tra catalog.
9. Dùng schema-qualified calls, kiểm soát grants và search_path ở những chỗ nhạy cảm.
10. Trước migration, kiểm tra cả positional callers, named callers, default values, phụ thuộc và quyền.

**Một câu để nhớ:** giá trị mặc định giúp **bỏ qua đối số**, named arguments giúp **truyền đúng đối số**, còn overloading giúp **chọn đúng routine theo kiểu đầu vào**. Ba cơ chế chỉ thật sự hữu ích khi chữ ký được thiết kế **rõ ràng, không mơ hồ và ổn định cho người gọi**.

