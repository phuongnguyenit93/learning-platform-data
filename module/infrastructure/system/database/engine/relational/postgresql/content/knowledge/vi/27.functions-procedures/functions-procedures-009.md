# Phụ thuộc, đổi chữ ký và quản lý phiên bản hàm trong PostgreSQL

Trong PostgreSQL, một hàm không chỉ là đoạn SQL hoặc PL/pgSQL có tên. Hàm còn có **danh tính dựa trên tên, schema và các kiểu tham số đầu vào**, kiểu kết quả, quyền thực thi, thuộc tính thực thi và các đối tượng phụ thuộc. Vì vậy, một thay đổi tưởng như nhỏ — thêm tham số, đổi kiểu trả về, đổi tên hàm, sửa danh sách tham số mặc định — có thể làm hỏng view, trigger, câu SQL trong ứng dụng hoặc lời gọi từ JDBC.

Giả sử ứng dụng đang sử dụng:

~~~sql
SELECT api_lab.order_total(1001);
~~~

Bạn muốn bổ sung khả năng giảm giá:

~~~sql
SELECT api_lab.order_total_v2(1001, 10);
~~~

Sự thay đổi này đặt ra nhiều câu hỏi:

- Có thể dùng `CREATE OR REPLACE FUNCTION` để thêm tham số không?
- Nếu tạo thêm một overload, lời gọi cũ và lời gọi truyền `NULL`/literal không có kiểu rõ ràng có bị nhập nhằng?
- View đang gọi hàm cũ có bị xóa nếu chạy `DROP FUNCTION ... CASCADE`?
- Một hàm SQL/PLpgSQL tham chiếu bảng hoặc hàm khác có luôn được ghi đủ phụ thuộc trong `pg_depend`?
- Khi kiểu trả về thay đổi, làm sao giữ API cũ hoạt động trong lúc chuyển ứng dụng sang API mới?
- Khi thay thân hàm `SECURITY DEFINER`, quyền và `search_path` cần được kiểm tra thế nào?
- Nếu triển khai lỗi, có thể rollback mà không khiến những phiên ứng dụng cũ gặp lỗi không?

Bài học này tập trung vào **vòng đời một hàm như một hợp đồng giao diện của database**, gồm: định danh/chữ ký, overload, tham số mặc định, phụ thuộc, catalog, phân biệt `REPLACE` với `DROP/CREATE`, migration an toàn, versioning, bảo mật và kiểm thử tương thích.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả **chữ ký** (*signature*) và **danh tính** (*identity*) của hàm PostgreSQL.
2. Hiểu vai trò của `IN`, `OUT`, `INOUT`, `VARIADIC` và giá trị mặc định trong xác định overload.
3. Sử dụng tên hàm kèm kiểu tham số để tham chiếu đúng overload, ví dụ `api_lab.order_total(bigint)`.
4. Phân biệt những thay đổi có thể thực hiện bằng `CREATE OR REPLACE FUNCTION` với thay đổi cần tạo hàm mới.
5. Giải thích tại sao đổi kiểu kết quả/`RETURNS TABLE` có thể phá vỡ API và đối tượng phụ thuộc.
6. Dùng `pg_proc`, `pg_namespace`, `pg_depend`, `pg_get_functiondef` và `pg_get_function_identity_arguments` để quan sát hàm.
7. Nhận biết khác biệt giữa phụ thuộc được PostgreSQL ghi nhận trong catalog và phụ thuộc chỉ xuất hiện trong thân SQL dạng chuỗi/PL/pgSQL/dynamic SQL.
8. Dùng `DROP FUNCTION ... RESTRICT` cẩn thận, không lạm dụng `CASCADE`.
9. Thiết kế tiến trình versioning kiểu **expand–migrate–contract**, giữ hàm cũ và chuyển client từng bước.
10. Biết cách đặt quyền `EXECUTE`, phân biệt `SECURITY INVOKER`/`SECURITY DEFINER` và tránh lỗ hổng `search_path`.
11. Xây một lab PostgreSQL gồm bảng nguồn, hàm v1, hàm v2, view phụ thuộc và ví dụ migration.
12. Đặt kế hoạch rollback phù hợp khi có nhiều phiên bản ứng dụng và nhiều overload cùng tồn tại.

## 2. Hàm là một API của cơ sở dữ liệu

Một hàm có thể được gọi bởi nhiều đối tượng:

~~~text
     Ứng dụng Java / JDBC
               |
               v
    api_lab.order_total(bigint) <----- View / SQL report
               |
               +----> SQL function khác
               |
               +----> Trigger function / procedure
               |
               v
         Bảng nguồn orders
               |
               v
             products
~~~

Nếu thay đổi interface mà không kiểm tra các điểm gọi, ứng dụng có thể gặp:

- `function ... does not exist` vì tên/kiểu tham số không còn khớp.
- `function ... is not unique` vì overload hoặc tham số mặc định gây nhập nhằng.
- `cannot change return type of existing function` khi dùng `CREATE OR REPLACE` không đúng.
- Lỗi `DROP FUNCTION` vì có object phụ thuộc.
- Lỗi quyền `permission denied for function ...` sau khi tạo lại hàm.
- Kết quả sai vì thân hàm mới thay đổi logic hoặc kiểu dữ liệu.

Vì vậy nên quản lý hàm như **public API có phiên bản**, chứ không chỉ là một tập câu lệnh tiện ích trong database.

## 3. Chữ ký hàm: tên, schema và kiểu tham số đầu vào

Xét hai hàm:

~~~sql
CREATE FUNCTION api_lab.label_value(p_value integer)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'int:' || p_value::text
$$;

CREATE FUNCTION api_lab.label_value(p_value text)
RETURNS text
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT 'text:' || p_value
$$;
~~~

Hai hàm có thể tồn tại cùng lúc vì kiểu đầu vào khác nhau:

~~~text
api_lab.label_value(integer)
api_lab.label_value(text)
~~~

### 3.1. Không chỉ tên hàm

Khi truy vấn catalog hoặc drop function, không đủ để ghi `label_value` nếu có nhiều overload. PostgreSQL cần phân biệt bằng kiểu tham số, ví dụ:

~~~sql
DROP FUNCTION api_lab.label_value(integer);
~~~

Lệnh trên chỉ nhắm overload có đầu vào `integer`, không nhắm `label_value(text)`.

### 3.2. Tên tham số không tạo overload riêng

Những khai báo sau **không tạo hai chữ ký khác nhau**:

~~~sql
-- Cùng signature theo kiểu đầu vào: integer.
CREATE FUNCTION api_lab.calculate(p_amount integer) ...
CREATE FUNCTION api_lab.calculate(p_value integer)  ...
~~~

Tên `p_amount` và `p_value` có ý nghĩa khi gọi bằng **named notation**, nhưng chúng không làm hai hàm cùng tên/cùng kiểu trở thành hai overload khác nhau.

### 3.3. Kiểu trả về không phân biệt overload

Không thể có đồng thời hai hàm cùng schema, tên và cùng kiểu đầu vào nhưng khác mỗi kiểu trả về:

~~~sql
-- Không thể đồng thời tồn tại:
-- api_lab.convert(integer) RETURNS text
-- api_lab.convert(integer) RETURNS numeric
~~~

PostgreSQL không chọn overload dựa trên ngữ cảnh mong muốn kiểu trả về của biểu thức SQL.

### 3.4. Default value không phải một kiểu tham số mới

`p_rate numeric DEFAULT 0` vẫn là tham số kiểu `numeric`. Giá trị mặc định chỉ cho phép lược bớt đối số tại điểm gọi, không biến `numeric` thành một kiểu khác trong chữ ký.

## 4. Các mode tham số: IN, OUT, INOUT, VARIADIC

PostgreSQL hỗ trợ các mode tham số và chúng tác động khác nhau tới contract của hàm.

| Mode | Mục đích | Tác động đáng nhớ |
| --- | --- | --- |
| `IN` | Nhận giá trị vào | Thuộc danh sách kiểu đầu vào định danh hàm |
| `OUT` | Trả một cột/kết quả | Không dùng như một tham số đầu vào để phân biệt overload hàm |
| `INOUT` | Nhận vào và trả ra | Có cả vai trò input/output |
| `VARIADIC` | Nhận số lượng đối số biến thiên cùng một kiểu | Tham gia cách gọi/giải quyết hàm; cần cân nhắc ambiguity |
| `TABLE` | Định nghĩa cột kết quả set-returning function | Là một phần contract kết quả, không tạo overload theo tên output |

### 4.1. Hàm với OUT

~~~sql
CREATE FUNCTION api_lab.parse_ref(
    IN p_ref text,
    OUT prefix text,
    OUT suffix text
)
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT split_part(p_ref, '-', 1),
           split_part(p_ref, '-', 2)
$$;
~~~

Đầu vào định danh chính là `text`, còn hai `OUT` xác định **hình dạng kết quả**. Lời gọi:

~~~sql
SELECT * FROM api_lab.parse_ref('AB-123');
~~~

có hai cột `prefix` và `suffix`.

### 4.2. Không dùng OUT để đánh lừa identity

Đổi `OUT suffix text` thành `OUT suffix integer` là một thay đổi **contract kết quả**, không phải một overload khác chỉ vì OUT khác kiểu. Với hàm hiện có và các phụ thuộc, cần migration rõ ràng.

### 4.3. INOUT

Với `INOUT`, đối số có giá trị ở lúc gọi đồng thời tham gia kết quả. Khi xác định routine bằng kiểu đầu vào, tham số INOUT có vai trò input.

### 4.4. VARIADIC và call resolution

`VARIADIC` có cách xử lý lời gọi với nhiều đối số; overload cùng tên có thể trở nên khó dự đoán nếu còn các hàm khớp chính xác khác. Không thay các hàm API phổ biến sang `VARIADIC` mà chưa kiểm tra đường gọi thực tế.

## 5. Overloading: linh hoạt nhưng có rủi ro

Ví dụ hàm `label_value` đã có hai overload:

~~~sql
SELECT api_lab.label_value(42::integer);
SELECT api_lab.label_value('hello'::text);
~~~

Khi kiểu đối số rõ ràng, PostgreSQL có thể chọn chính xác.

### 5.1. Literal chưa định kiểu

~~~sql
SELECT api_lab.label_value('42');
~~~

Literal chuỗi không có cast tường minh ban đầu mang kiểu `unknown` để PostgreSQL suy kiểu từ ngữ cảnh. PostgreSQL áp các quy tắc lựa chọn overload, trong đó có loại/nhóm kiểu ưu tiên. Bạn không nên dựa vào trực giác rằng literal `'42'` sẽ luôn chọn overload số nguyên.

### 5.2. Bind parameter từ JDBC

Nếu driver gửi parameter với kiểu chưa xác định hoặc SQL dùng `NULL` không cast, có thể xuất hiện kết quả chọn overload không như dự kiến.

~~~sql
SELECT api_lab.label_value(NULL::integer);
SELECT api_lab.label_value(NULL::text);
~~~

Hai lời gọi trên có chữ ký mục tiêu rõ ràng.

### 5.3. Cast rõ khi overload có ý nghĩa nghiệp vụ khác

~~~sql
SELECT api_lab.label_value($1::integer);
~~~

trong một prepared statement giúp API contract xác định được loại overload. Tuy nhiên cần bind/cast đúng kiểu dữ liệu thực, không ép mọi đối số sang text để “cho khỏi lỗi”.

### 5.4. Schema cũng quan trọng

Nếu nhiều schema chứa các overload cùng tên và `search_path` khác nhau giữa các session, resolution có thể đổi. Với API quan trọng, dùng tên schema đầy đủ:

~~~sql
SELECT api_lab.label_value(42::integer);
~~~

## 6. Default arguments và tính mơ hồ

Tham số mặc định giúp bổ sung lựa chọn mà không phải truyền ở mọi lời gọi:

~~~sql
CREATE FUNCTION api_lab.apply_rate(
    p_amount numeric,
    p_rate numeric DEFAULT 10
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT round(p_amount * (1 + p_rate / 100), 2)
$$;
~~~

~~~sql
SELECT api_lab.apply_rate(100::numeric);
SELECT api_lab.apply_rate(100::numeric, 5::numeric);
~~~

### 6.1. Tham số mặc định vẫn thuộc danh sách input types

Hàm có identity:

~~~text
api_lab.apply_rate(numeric, numeric)
~~~

không phải `api_lab.apply_rate(numeric)` chỉ vì có thể bỏ `p_rate` khi gọi.

### 6.2. Default arguments có thể gây ambiguity

Giả sử đã tồn tại:

~~~sql
CREATE FUNCTION api_lab.tax(p_amount numeric)
RETURNS numeric
LANGUAGE sql IMMUTABLE
AS $$ SELECT p_amount * 1.1 $$;
~~~

Sau đó lại thêm overload:

~~~sql
-- Chỉ minh họa một thiết kế dễ gây nhập nhằng.
CREATE FUNCTION api_lab.tax(
    p_amount numeric,
    p_rate numeric DEFAULT 10
)
RETURNS numeric
LANGUAGE sql IMMUTABLE
AS $$ SELECT p_amount * (1 + p_rate / 100) $$;
~~~

Lời gọi:

~~~sql
SELECT api_lab.tax(100::numeric);
~~~

giờ có thể khớp cả overload một tham số lẫn overload hai tham số có default, dẫn tới vấn đề resolution và migration. Đặc biệt, khi **các hàm ở cùng schema cùng phù hợp do bỏ tham số mặc định**, PostgreSQL có những trường hợp báo `function ... is not unique` thay vì tự chọn “hàm cũ”.

### 6.3. Quy tắc triển khai

Trước khi thêm default vào API công khai:

1. Liệt kê overload hiện có.
2. Liệt kê mọi call forms (positional, named, bỏ tham số, `NULL`).
3. Thử từng call form với kiểu thực tế của application driver.
4. Nếu có nguy cơ nhập nhằng, cân nhắc **tên hàm v2 khác** hoặc một wrapper có contract rõ.

### 6.4. Không biến default thành giải pháp tương thích mặc định

Thêm một tham số default **không giống thay cùng một hàm tại chỗ**. Chữ ký mới là một routine khác; behavior của các lời gọi cũ phải được kiểm tra dưới tập overload mới.

## 7. Named notation và tên tham số

PostgreSQL hỗ trợ gọi theo tên:

~~~sql
SELECT api_lab.apply_rate(
    p_rate => 7::numeric,
    p_amount => 100::numeric
);
~~~

Tên tham số trở thành **một phần contract của các lời gọi dùng named notation**.

### 7.1. Thứ tự positional và named

Các lời gọi dùng vị trí quan tâm thứ tự đối số. Named notation cho phép chỉ rõ tên, và PostgreSQL có các quy tắc kết hợp positional/named.

### 7.2. Đổi tên tham số có thể phá API

Giả sử ứng dụng có:

~~~sql
SELECT api_lab.apply_rate(
    p_amount => 100,
    p_rate => 8
);
~~~

Nếu đổi `p_rate` thành `rate_pct`, ứng dụng đang dùng tên cũ sẽ không tự đổi theo.

### 7.3. CREATE OR REPLACE và tham số IN đã đặt tên

PostgreSQL hạn chế việc **đổi tên tham số input đã đặt tên** bằng `CREATE OR REPLACE FUNCTION` đối với hàm hiện có, vì điều đó làm thay đổi named-call contract. Muốn thay, cần xem phương án tạo API mới/giữ wrapper, không cố xem đó là sửa cosmetic.

### 7.4. Quy ước đặt tên

Một nhóm có thể dùng `p_` cho input như `p_order_id`, `p_discount_pct` và giữ ổn định sau khi public API triển khai. Dù gọi positional hiện không dùng tên, các client tương lai có thể dùng named notation.

## 8. CREATE OR REPLACE FUNCTION: điều gì được giữ?

Cú pháp:

~~~sql
CREATE OR REPLACE FUNCTION api_lab.some_function(
    p_id bigint
)
RETURNS numeric
LANGUAGE sql
STABLE
AS $$
    SELECT ...
$$;
~~~

Khi hàm **đã tồn tại với cùng identity và kiểu kết quả tương thích**, `CREATE OR REPLACE` sửa định nghĩa mà **không DROP hàm trước**.

### 8.1. Lợi ích lớn nhất: giữ danh tính đối tượng

Với overload hiện có, `CREATE OR REPLACE` thường giữ OID hàm, ownership và các quyền đã cấp trước đó; những đối tượng phụ thuộc gắn với hàm cũ không phải bị drop chỉ để thay thân hàm.

### 8.2. Có thể sửa thân hàm

Ví dụ đổi công thức tính toán nội bộ nhưng vẫn nhận `bigint` và trả `numeric`, hoặc sửa truy vấn bên trong:

~~~sql
CREATE OR REPLACE FUNCTION api_lab.order_total(
    p_order_id bigint
)
RETURNS numeric
LANGUAGE sql
STABLE
AS $$
    SELECT round(
        o.quantity * p.unit_price,
        2
    )
    FROM api_lab.orders AS o
    JOIN api_lab.products AS p
      ON p.product_id = o.product_id
    WHERE o.order_id = p_order_id
$$;
~~~

Đây là cùng một chữ ký `order_total(bigint)` và cùng kiểu kết quả.

### 8.3. Không tự xem semantic change là an toàn

Thân hàm mới có thể đổi cách xử lý `NULL`, ngoại lệ, rounding, timezone hoặc truy cập bảng khác. Dù PostgreSQL chấp nhận `REPLACE` về DDL, **application contract** vẫn có thể bị phá.

### 8.4. Đổi thuộc tính hàm cũng cần thận trọng

`VOLATILE`/`STABLE`/`IMMUTABLE`, `STRICT`, `SECURITY DEFINER` và thiết lập `SET search_path` có thể ảnh hưởng plan, quyền và kết quả thực tế. Không thay chỉ để “tối ưu” mà chưa hiểu điều kiện chính xác.

## 9. CREATE OR REPLACE không đổi identity

Giả sử hàm gốc:

~~~sql
api_lab.order_total(bigint) RETURNS numeric
~~~

Bạn viết:

~~~sql
CREATE OR REPLACE FUNCTION api_lab.order_total(
    p_order_id bigint,
    p_discount_pct numeric
)
RETURNS numeric
...
~~~

Lệnh này **không cập nhật cùng function object** của `order_total(bigint)`. Vì danh sách kiểu đầu vào khác, PostgreSQL xử lý như một hàm mới (một overload khác) nếu khai báo hợp lệ.

### 9.1. Hàm cũ có thể vẫn tồn tại

Sau migration, catalog có thể có:

~~~text
api_lab.order_total(bigint)
api_lab.order_total(bigint, numeric)
~~~

Ứng dụng gọi một đối số chưa tự chuyển sang hàm hai đối số, trừ khi resolution do default arguments và overload rules làm nó phù hợp theo cách khác.

### 9.2. Không “đổi tên cột trả về” bằng tưởng tượng

Nếu cần thay từ `RETURNS numeric` sang `RETURNS TABLE(...)`, đó là **thay contract kết quả**, và không thể coi là một `REPLACE` bình thường của cùng hàm.

### 9.3. Không lấy RETURNS làm identity

Chữ ký cần để `DROP FUNCTION` và `ALTER FUNCTION` thường chỉ gồm những kiểu tham số input định danh. Một kiểu trả về khác không tạo thêm overload cùng input types.

## 10. Đổi kiểu trả về: migration bắt buộc phải tính

Một hàm `RETURNS numeric` không thể trực tiếp đổi thành `RETURNS text` bằng `CREATE OR REPLACE` cho cùng chữ ký:

~~~sql
-- Ví dụ CỐ Ý KHÔNG HỢP LỆ với hàm đã trả numeric:
--
-- CREATE OR REPLACE FUNCTION api_lab.order_total(bigint)
-- RETURNS text ...
~~~

PostgreSQL từ chối việc đổi kiểu trả về theo cách đó.

### 10.1. Các kiểu trả về nhiều cột cũng là contract

~~~sql
CREATE FUNCTION api_lab.order_summary(
    p_order_id bigint
)
RETURNS TABLE (
    order_id bigint,
    total numeric
)
LANGUAGE sql
STABLE
AS $$
    SELECT o.order_id, (o.quantity * p.unit_price)::numeric
    FROM api_lab.orders AS o
    JOIN api_lab.products AS p
      ON p.product_id = o.product_id
    WHERE o.order_id = p_order_id
$$;
~~~

Đổi `RETURNS TABLE(order_id bigint, total numeric)` sang thêm cột `currency text` là thay đổi kết quả, có thể phá view, client mapping hoặc hàm gọi.

### 10.2. Một hướng tương thích hơn

Giữ `order_summary(bigint)` v1 và tạo:

~~~text
api_lab.order_summary_v2(bigint)
    -> (order_id bigint, total numeric, currency text)
~~~

Ứng dụng chuyển dần sang v2. Sau khi chắc chắn không còn caller v1 và các phụ thuộc, mới cân nhắc dọn v1.

### 10.3. Đổi kiểu trong cùng family vẫn cần xem xét

`numeric` sang `numeric(12,2)`, `integer` sang `bigint` hoặc `jsonb` sang `text` đều cần xem đúng ngữ nghĩa khai báo hàm, casts và output record; không dựa vào việc “kiểu trông gần nhau” để cho rằng không ảnh hưởng contract.

### 10.4. Không DROP/CREATE vội

`DROP FUNCTION` có thể bị chặn bởi dependencies hoặc, nếu thêm `CASCADE`, xóa cả các đối tượng cần giữ. Ngoài ra, hàm được tạo lại sẽ có OID/privileges/ownership/defaults cần đánh giá.

## 11. Phụ thuộc: vì sao database cần biết?

PostgreSQL lưu dependency metadata cho nhiều đối tượng trong system catalogs để:

- Ngăn xóa một đối tượng khi đối tượng khác vẫn phụ thuộc.
- Xác định những đối tượng có thể bị xóa dây chuyền với `CASCADE`.
- Bảo vệ kiểu dữ liệu, schema, hàm dùng trong expression, view/rule hoặc những liên hệ được ghi nhận.

Ví dụ:

~~~text
VIEW v_order_totals
    |
    +---- phụ thuộc function order_total(bigint)
                  |
                  +---- tham chiếu bảng orders, products trong thân SQL
~~~

Tuy nhiên, **mũi tên thứ hai không luôn được ghi nhận đầy đủ trong catalog**, tùy cách viết thân hàm và ngôn ngữ. Đây là một điểm rất quan trọng.

### 11.1. Dependent object là gì?

Ví dụ view có gọi hàm, expression index dùng hàm, constraint/generation expression gọi hàm hoặc một object type được dùng trong chữ ký.

### 11.2. Không phải mọi lời gọi đều là catalog dependency

Một câu SQL nằm trong source code Java, file migration, scheduler hoặc stored text/dynamic SQL không được PostgreSQL hiểu thành “một object phụ thuộc” có thể liệt kê đầy đủ trong `pg_depend`.

### 11.3. Không nhìn pg_depend rồi kết luận đã tìm hết callers

`pg_depend` là công cụ mạnh để xem phụ thuộc đã được ghi nhận, nhưng migration thực tế cần **đồng thời** kiểm tra các hàm khác, application code, SQL được tạo động, job/report và quyền.

## 12. Dựng lab phụ thuộc có thể chạy lại

Các ví dụ tiếp theo dùng một schema lab mới, trên database thử nghiệm. Không chạy `DROP ... CASCADE` với đối tượng production.

### 12.1. Tạo schema và bảng

~~~sql
CREATE SCHEMA api_lab;

CREATE TABLE api_lab.products (
    product_id bigint PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    unit_price numeric(12,2) NOT NULL
        CHECK (unit_price >= 0)
);

CREATE TABLE api_lab.orders (
    order_id bigint PRIMARY KEY,
    product_id bigint NOT NULL
        REFERENCES api_lab.products(product_id),
    quantity integer NOT NULL
        CHECK (quantity > 0),
    order_status text NOT NULL
        CHECK (order_status IN ('new', 'paid', 'cancelled'))
);
~~~

### 12.2. Chèn dữ liệu mẫu

~~~sql
INSERT INTO api_lab.products (product_id, sku, unit_price)
VALUES
    (10, 'SKU-A', 100.00),
    (20, 'SKU-B',  50.00),
    (30, 'SKU-C',  20.00);

INSERT INTO api_lab.orders (
    order_id, product_id, quantity, order_status
)
VALUES
    (1001, 10, 2, 'paid'),
    (1002, 20, 3, 'paid'),
    (1003, 30, 1, 'new'),
    (1004, 10, 1, 'cancelled');
~~~

### 12.3. Tạo hàm v1

~~~sql
CREATE FUNCTION api_lab.order_total(
    p_order_id bigint
)
RETURNS numeric
LANGUAGE sql
STABLE
AS $$
    SELECT (o.quantity * p.unit_price)::numeric
    FROM api_lab.orders AS o
    JOIN api_lab.products AS p
      ON p.product_id = o.product_id
    WHERE o.order_id = p_order_id
$$;
~~~

Lưu ý:

- `STABLE` phù hợp với ví dụ truy vấn đọc bảng theo snapshot của statement, không có side effects.
- Đây không phải hàm `IMMUTABLE` vì kết quả phụ thuộc dữ liệu bảng có thể thay đổi.
- Nếu không có order tương ứng, hàm SQL scalar không có hàng kết quả sẽ trả SQL `NULL` trong trường hợp này.
- Chúng ta dùng tên schema đầy đủ bên trong hàm để tránh phụ thuộc `search_path` cho hai bảng nguồn.

### 12.4. Kiểm tra hàm v1

~~~sql
SELECT
    api_lab.order_total(1001::bigint) AS order_1001,
    api_lab.order_total(1002::bigint) AS order_1002,
    api_lab.order_total(1003::bigint) AS order_1003;
~~~

Kỳ vọng:

| order_id | total |
| ---: | ---: |
| 1001 | 200.00 |
| 1002 | 150.00 |
| 1003 | 20.00 |

### 12.5. Tạo view gọi hàm

~~~sql
CREATE VIEW api_lab.v_order_totals AS
SELECT
    o.order_id,
    o.order_status,
    api_lab.order_total(o.order_id) AS order_total
FROM api_lab.orders AS o;
~~~

~~~sql
SELECT *
FROM api_lab.v_order_totals
ORDER BY order_id;
~~~

View này là một **dependent object** quan trọng khi thử `DROP FUNCTION`.

## 13. Xác định chính xác hàm bằng regprocedure

PostgreSQL có kiểu OID alias `regprocedure` giúp phân biệt hàm dựa trên tên và danh sách kiểu input.

~~~sql
SELECT
    'api_lab.order_total(bigint)'::regprocedure
        AS function_identity;
~~~

### 13.1. to_regprocedure tránh exception khi chưa tồn tại

~~~sql
SELECT
    to_regprocedure(
        'api_lab.order_total(bigint)'
    ) AS existing_function;
~~~

Nếu không tìm thấy routine phù hợp, `to_regprocedure` trả SQL `NULL` trong những trường hợp lookup hợp lệ, thuận tiện cho script kiểm tra trước migration.

### 13.2. Phân biệt với regproc

`regproc` biểu diễn function name theo ngữ cảnh không phân biệt overload bằng danh sách kiểu. Với API có nhiều overload, `regprocedure` thường phù hợp hơn.

### 13.3. Kiểu đầy đủ

Tham chiếu overload với `numeric` khác `integer`:

~~~sql
SELECT
    to_regprocedure('api_lab.apply_rate(numeric,numeric)');
~~~

Đối với một function có tham số mặc định, vẫn dùng **danh sách kiểu đầu vào đầy đủ** trong identity.

## 14. Liệt kê hàm trong pg_proc

`pg_proc` lưu metadata của functions, procedures và một số loại routines.

~~~sql
SELECT
    p.oid::regprocedure AS routine,
    n.nspname AS schema_name,
    p.proname AS routine_name,
    p.prokind,
    pg_get_function_identity_arguments(p.oid)
        AS identity_arguments,
    pg_get_function_result(p.oid)
        AS result_type
FROM pg_proc AS p
JOIN pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE n.nspname = 'api_lab'
ORDER BY p.proname,
         pg_get_function_identity_arguments(p.oid);
~~~

### 14.1. Những cột nên biết

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `oid` | Danh tính catalog của routine |
| `pronamespace` | Schema chứa routine |
| `proname` | Tên |
| `prokind` | Phân biệt function/procedure/aggregate/window theo mã catalog |
| `proargtypes` | Các kiểu input arguments trong catalog |
| `proallargtypes` | Các kiểu toàn bộ arguments khi cần (gồm output) |
| `proargmodes` | Mode của arguments nếu có |
| `proargnames` | Tên arguments |
| `proargdefaults` | Giá trị mặc định của input arguments |
| `prorettype` | Kiểu kết quả |
| `provolatile` | Phân loại volatility |
| `prosecdef` | SECURITY DEFINER hay không |
| `proparallel` | Khai báo parallel safety |

### 14.2. prokind

Giá trị `prokind` thường dùng để phân biệt routine:

~~~text
f = function
p = procedure
a = aggregate
w = window function
~~~

Với bài này, chủ yếu lọc `prokind = 'f'` khi muốn liệt kê riêng functions.

### 14.3. Không suy contract chỉ từ tên

Nếu có nhiều `order_total`, hãy hiển thị `oid::regprocedure` hoặc `pg_get_function_identity_arguments`, không chỉ `proname`.

## 15. pg_get_function_identity_arguments và pg_get_function_arguments

Hai hàm catalog có mục đích hơi khác:

~~~sql
SELECT
    p.oid::regprocedure AS routine,
    pg_get_function_identity_arguments(p.oid)
        AS identity_args,
    pg_get_function_arguments(p.oid)
        AS declaration_args,
    pg_get_function_result(p.oid)
        AS return_type
FROM pg_proc AS p
WHERE p.oid = 'api_lab.order_total(bigint)'::regprocedure;
~~~

### 15.1. Identity arguments

`pg_get_function_identity_arguments` tạo chuỗi tham số thích hợp cho các lệnh như `ALTER FUNCTION`/`DROP FUNCTION`, không dựa vào biểu thức default.

### 15.2. Declaration arguments

`pg_get_function_arguments` cung cấp biểu diễn khai báo tham số có thể bao gồm tên, mode và mặc định — hữu ích để xem **API contract đầy đủ**.

### 15.3. Function result

`pg_get_function_result` cho biết kiểu kết quả được công bố (ví dụ `numeric` hoặc `TABLE(...)`).

### 15.4. Vì sao cần cả hai?

Một migration có thể chỉ so identity mà bỏ qua:

- Tên tham số dùng trong named notation.
- Giá trị mặc định.
- Cột/trường của kết quả.

Những thay đổi này vẫn có thể ảnh hưởng client dù danh sách input types không đổi.

## 16. Lấy DDL của hàm bằng pg_get_functiondef

~~~sql
SELECT pg_get_functiondef(
    'api_lab.order_total(bigint)'::regprocedure
);
~~~

Hàm này tái tạo định nghĩa SQL phù hợp với đối tượng catalog.

### 16.1. Dùng để xem lại contract trước migration

Nên lưu lại một bản định nghĩa/DDL từ source control hoặc catalog để biết:

- Thân hàm hiện tại.
- Kiểu trả về.
- Thuộc tính volatility/strict/security.
- Thiết lập `SET` ở cấp hàm.
- Ngôn ngữ SQL/PLpgSQL.

### 16.2. pg_get_functiondef không là source control

Catalog phản ánh trạng thái đang chạy nhưng không cho biết vì sao thay đổi, ticket nào phê duyệt hoặc ứng dụng nào đang phụ thuộc. Migration scripts trong version control vẫn cần thiết.

### 16.3. Quyền và owner là metadata riêng

DDL của function body không đủ thay thế quy trình kiểm tra `ALTER OWNER`, `GRANT/REVOKE` và default privileges. Khi làm lại function mới, phải có kế hoạch tái áp những thông tin đó.

## 17. pg_depend: quan sát phụ thuộc đã được ghi nhận

`pg_depend` chứa quan hệ phụ thuộc giữa những đối tượng PostgreSQL quản lý.

### 17.1. Tìm đối tượng mà hàm phụ thuộc vào

~~~sql
SELECT
    d.deptype,
    d.refclassid::regclass AS referenced_catalog,
    pg_describe_object(
        d.refclassid,
        d.refobjid,
        d.refobjsubid
    ) AS referenced_object
FROM pg_depend AS d
WHERE d.classid = 'pg_proc'::regclass
  AND d.objid =
      'api_lab.order_total(bigint)'::regprocedure
ORDER BY referenced_catalog::text, referenced_object;
~~~

Ví dụ có thể thấy dependency tới schema, kiểu tham số/kết quả và những đối tượng catalog liên quan.

### 17.2. Vì sao không thấy đầy đủ orders/products?

Thân hàm SQL dạng chuỗi:

~~~sql
LANGUAGE sql
AS $$
    SELECT ... FROM api_lab.orders ...
$$;
~~~

có những giới hạn về việc ghi nhận phụ thuộc đến các bảng/hàm được nhắc **bên trong chuỗi body**. Không thấy bảng trong kết quả trên **không chứng minh** hàm không sử dụng bảng ấy.

### 17.3. Các loại phụ thuộc

`deptype` biểu thị phân loại dependency (normal, automatic, internal, extension-related...). Không hiểu mọi giá trị thành một quan hệ có thể xóa tùy ý; hành vi `DROP` phụ thuộc loại và quan hệ của đối tượng.

### 17.4. Catalog là điểm bắt đầu, không phải danh sách khách hàng đầy đủ

Ứng dụng Java, report được lưu ngoài DB, câu SQL động, trigger/procedure source không được lập dependency đầy đủ và bảng cấu hình có chuỗi SQL cần được rà soát riêng theo quy trình change management.

## 18. Phụ thuộc view tới function

View thường có rewrite rule; reference đến function trong biểu thức của view có thể được ghi qua `pg_rewrite` và `pg_depend`.

~~~sql
SELECT
    c.oid::regclass AS dependent_view,
    r.rulename AS rewrite_rule,
    d.deptype,
    pg_describe_object(
        d.refclassid,
        d.refobjid,
        d.refobjsubid
    ) AS referenced
FROM pg_depend AS d
JOIN pg_rewrite AS r
  ON r.oid = d.objid
JOIN pg_class AS c
  ON c.oid = r.ev_class
WHERE d.classid = 'pg_rewrite'::regclass
  AND d.refclassid = 'pg_proc'::regclass
  AND d.refobjid =
      'api_lab.order_total(bigint)'::regprocedure
ORDER BY dependent_view::text;
~~~

Kỳ vọng thấy dependency từ rewrite rule của `api_lab.v_order_totals` tới hàm.

### 18.1. Phụ thuộc thường được ghi bằng OID

View có thể giữ tham chiếu tới OID hàm trong biểu thức đã phân tích, nên `CREATE OR REPLACE FUNCTION` cùng identity có thể giữ tham chiếu hoạt động.

### 18.2. Đổi tên hàm và OID

`ALTER FUNCTION ... RENAME TO` thay **tên** nhưng không tạo routine mới. Các đối tượng đã gắn OID có thể tiếp tục được PostgreSQL quản lý, trong khi SQL viết trong ứng dụng gọi **tên cũ** sẽ lỗi sau khi đổi tên.

### 18.3. Không mọi phụ thuộc đều là view

Expression index, generated columns, check constraints, default expressions, policies và các đối tượng khác có thể tham chiếu hàm. Khi điều tra một thay đổi nguy hiểm, cần xem phụ thuộc nhiều classid, không chỉ `pg_rewrite`.

## 19. SQL function body: hai cách viết và mức ghi nhận dependency

PostgreSQL hỗ trợ cách khai báo SQL functions với thân là **string literal** và (ở các phiên bản hỗ trợ) cách viết **SQL-standard body** được phân tích khi định nghĩa.

### 19.1. Body dưới dạng chuỗi

~~~sql
CREATE FUNCTION api_lab.product_price_string(
    p_product_id bigint
)
RETURNS numeric
LANGUAGE sql
STABLE
AS $$
    SELECT unit_price
    FROM api_lab.products
    WHERE product_id = p_product_id
$$;
~~~

Trong cách này, việc theo dõi dependency trực tiếp tới bảng được nhắc trong thân SQL có thể không đầy đủ. PostgreSQL không nhất thiết lập dependency cho mọi bảng được nhắc bên trong chuỗi literal.

### 19.2. SQL-standard function body

Ở các phiên bản PostgreSQL có hỗ trợ cú pháp SQL-standard bodies:

~~~sql
CREATE FUNCTION api_lab.product_price_sql_body(
    p_product_id bigint
)
RETURNS numeric
LANGUAGE sql
STABLE
BEGIN ATOMIC
    SELECT unit_price
    FROM api_lab.products
    WHERE product_id = p_product_id;
END;
~~~

Thân được phân tích tại thời điểm định nghĩa và có thể ghi nhận dependencies đến các đối tượng được tham chiếu trực tiếp, như bảng `api_lab.products`.

### 19.3. Khi nào nên dùng SQL-standard body?

Nó hữu ích khi cần dependency tracking mạnh hơn và muốn lỗi tham chiếu được phát hiện ngay lúc tạo hàm. Nhưng cú pháp, giới hạn và phiên bản PostgreSQL mục tiêu phải được kiểm tra trong quy trình triển khai.

### 19.4. Không tự cho rằng mọi PLpgSQL đều được theo dõi như SQL-standard body

Thân PL/pgSQL lưu và thực thi theo cơ chế riêng, với cả SQL tĩnh và dynamic SQL. Không dựa vào `pg_depend` để khẳng định đã thấy toàn bộ bảng/hàm được gọi trong mọi câu lệnh của PL/pgSQL.

### 19.5. Dynamic SQL gần như luôn cần kiểm tra thêm

Ví dụ:

~~~sql
EXECUTE format(
    'SELECT count(*) FROM %I.%I',
    v_schema, v_table
);
~~~

Tên bảng được tạo khi runtime, nên catalog không thể liệt kê một tập target cố định chỉ từ định nghĩa routine.

## 20. Kiểm tra dependency trước khi đổi hàm

Một kế hoạch nên bao gồm hai lớp:

**Lớp 1 — catalog dependencies:**

- `pg_depend`, `pg_rewrite`, `pg_proc`, `pg_class` và các hệ thống object khác.
- `to_regprocedure` cho các chữ ký cụ thể.
- `pg_get_functiondef` để lấy hiện trạng.

**Lớp 2 — callers ngoài dependency metadata:**

- Java/JDBC, ORM, stored SQL ở repository.
- Migration/seed scripts.
- Scheduled jobs, dashboard/report definitions.
- Dynamic SQL và chuỗi gọi gián tiếp.
- Named-argument calls, overload resolution, type casts.

### 20.1. Không đọc mỗi tên routine

Một câu query tìm `order_total` có thể tìm sai overload hoặc bỏ sót lời gọi qua tên schema khác. Cần hiểu **tập chữ ký được công khai**, không chỉ một chuỗi tên.

### 20.2. Không dùng search-and-replace máy móc

Đổi tên trong source code có thể làm đổi cả text hiển thị, literal không phải SQL hoặc hàm overload không liên quan. Migration cần kiểm tra điểm gọi theo kiểu/ngữ cảnh và phát hành ứng dụng có kiểm soát.

### 20.3. Khi có client không do bạn kiểm soát

Nếu function là public API cho dịch vụ/đối tác, việc dọn v1 càng cần thời hạn deprecation và metrics từ các connection/statement logs, vì catalog không nói client nào còn gọi hàm cũ.

## 21. DROP FUNCTION và RESTRICT

Cú pháp thường gặp:

~~~sql
DROP FUNCTION api_lab.order_total(bigint) RESTRICT;
~~~

`RESTRICT` là lựa chọn an toàn để không tự xóa các dependent objects mà PostgreSQL biết.

### 21.1. Lab có view phụ thuộc

Vì `api_lab.v_order_totals` gọi `api_lab.order_total(bigint)`, PostgreSQL sẽ ngăn việc drop hàm khi `RESTRICT` phát hiện dependency này.

### 21.2. RESTRICT không sửa các caller bên ngoài

Ngay cả khi `DROP ... RESTRICT` thành công, Java client đang gọi tên hàm ấy có thể lỗi ở runtime vì application call không phải đối tượng `pg_depend`.

### 21.3. IF EXISTS không bỏ qua dependency

~~~sql
DROP FUNCTION IF EXISTS api_lab.order_total(bigint)
RESTRICT;
~~~

`IF EXISTS` giúp không báo lỗi khi routine không có, **không cho phép vượt dependency restrictions**.

### 21.4. Môi trường lab

Để quan sát lỗi, hãy chạy lệnh drop thử trong một transaction/sandbox mà không lo ảnh hưởng các đối tượng dùng chung. Không dùng `DROP` với production chỉ để “xem dependency” khi có các quy trình migration an toàn hơn.

## 22. DROP FUNCTION CASCADE: rủi ro dây chuyền

~~~sql
-- CHỈ minh họa; không chạy để giải quyết migration production.
DROP FUNCTION api_lab.order_total(bigint) CASCADE;
~~~

`CASCADE` yêu cầu PostgreSQL xóa cả các dependent objects mà catalog xác định theo quy tắc dependency.

### 22.1. Không chỉ xóa một hàm

Trong lab, view `v_order_totals` có thể bị xóa do phụ thuộc vào hàm. Những object phụ thuộc tiếp theo vào view ấy cũng có thể bị ảnh hưởng.

### 22.2. Không có nghĩa xóa toàn bộ các bảng được hàm đọc

Nếu hàm chỉ đọc `orders` và `products`, `DROP FUNCTION ... CASCADE` không mặc nhiên xóa cả bảng nguồn ấy. Hướng dependency và kiểu quan hệ rất quan trọng.

### 22.3. Xem xét chuỗi tác động

Với đối tượng production, lập danh sách:

- Những views/materialized views/rules phụ thuộc.
- Expression indexes/constraints/triggers liên quan.
- Routine khác sử dụng interface.
- Client bên ngoài.

Không lấy `CASCADE` làm cách “fix lỗi dependency” vì kết quả có thể làm hệ thống mất chức năng.

### 22.4. RESTRICT trước, migration rõ sau

Nếu phải thay một chữ ký không tương thích, thường tốt hơn là **tạo v2 trước**, chuyển consumers, rồi drop v1 với `RESTRICT` khi đã thực sự không còn dependency.

## 23. ALTER FUNCTION: đổi thuộc tính nhưng không đổi chữ ký

`ALTER FUNCTION` dùng để thay một số thuộc tính của một function hiện có.

Ví dụ:

~~~sql
ALTER FUNCTION api_lab.order_total(bigint)
STABLE;
~~~

Hoặc:

~~~sql
ALTER FUNCTION api_lab.order_total(bigint)
RENAME TO order_total_legacy;
~~~

**Lưu ý:** Lệnh `RENAME` ở đây chỉ minh họa và **không được chạy trong lab hiện tại** nếu các bước tiếp theo còn gọi tên `order_total`.

### 23.1. Đổi tên không tạo overload mới

Khi đổi tên bằng `ALTER FUNCTION ... RENAME TO`, routine vẫn là đối tượng cũ theo OID. Nhưng application đang gọi tên cũ không tự nhận tên mới, nên đây vẫn là breaking change đối với client.

### 23.2. Chuyển schema

~~~sql
-- Chỉ minh họa: schema đích phải tồn tại.
ALTER FUNCTION api_lab.order_total(bigint)
SET SCHEMA another_schema;
~~~

Thao tác này thay qualified name được ứng dụng dùng; `search_path` và permission trên schema đích cũng phải được xem xét.

### 23.3. Owner và security

~~~sql
-- Minh họa, role phải tồn tại và đủ quyền:
ALTER FUNCTION api_lab.order_total(bigint)
OWNER TO db_owner_role;
~~~

Thay owner có thể tác động tới quyền trong `SECURITY DEFINER` hoặc quyền quản lý routine; không coi đổi owner là cosmetic.

### 23.4. Không có ALTER FUNCTION đổi kiểu input/return như một rename

`ALTER FUNCTION` không phải lệnh đổi `order_total(bigint)` thành `order_total(text)` hoặc `RETURNS TABLE(...)` theo cách in-place tổng quát. Đó là bài toán API migration.

## 24. VOLATILE, STABLE, IMMUTABLE: hợp đồng với planner

PostgreSQL dùng volatility category để hiểu những đảm bảo của function.

| Thuộc tính | Ý nghĩa đơn giản | Ví dụ |
| --- | --- | --- |
| `VOLATILE` | Có thể đổi kết quả giữa các lời gọi và có thể có side effects | Hàm dựa vào clock thực, ghi dữ liệu |
| `STABLE` | Với cùng arguments, nhất quán trong một statement theo điều kiện phù hợp | Hàm SELECT đọc bảng theo snapshot của statement |
| `IMMUTABLE` | Kết quả chỉ phụ thuộc input, không đổi theo database/session/time | Hàm toán học thuần |

### 24.1. Hàm đọc bảng không phải IMMUTABLE

~~~sql
api_lab.order_total(p_order_id bigint)
~~~

đọc `orders/products`, nên nếu bảng đổi, tổng có thể đổi. Gắn `IMMUTABLE` chỉ để “bật index” là khai báo sai và có thể gây stale result do planner/cache/index.

### 24.2. Không chỉ performance

Khi sửa body từ thuần toán học sang đọc bảng, bạn có thể phải đổi volatility. Sự thay đổi ảnh hưởng các nơi được phép dùng function như expression index/generated column và cách optimizer xử lý.

### 24.3. PARALLEL, STRICT và các flags khác

- `STRICT` / `RETURNS NULL ON NULL INPUT` cho biết không gọi body khi input SQL NULL.
- `CALLED ON NULL INPUT` (mặc định) cho phép body tự xử lý NULL.
- `PARALLEL SAFE/RESTRICTED/UNSAFE` mô tả ràng buộc parallel execution.
- `COST` và `ROWS` hỗ trợ ước lượng chi phí khi phù hợp.

Đổi các thuộc tính này cần hiểu chính xác body, không sao chép annotation từ hàm khác.

## 25. Quyền EXECUTE và rủi ro DROP/CREATE

Quyền thực thi function là một phần của contract.

~~~sql
-- Chỉ minh họa, role ứng dụng phải tồn tại.
GRANT EXECUTE
ON FUNCTION api_lab.order_total(bigint)
TO app_reader;
~~~

### 25.1. CREATE OR REPLACE khác DROP rồi CREATE

Với cùng function identity, `CREATE OR REPLACE` thông thường giữ quyền và ownership của routine hiện có. Nếu `DROP` rồi `CREATE`, routine mới có OID/owner/privileges theo việc tạo mới và default privileges, không mặc nhiên có đúng grants cũ.

### 25.2. Cấu hình PUBLIC EXECUTE mặc định

PostgreSQL có mặc định cấp quyền `EXECUTE` cho `PUBLIC` trên function mới, trừ khi default privileges đã được quản lý phù hợp. Một chức năng nhạy cảm có thể bị lộ nếu deploy hàm mới trước rồi mới nhớ thu hồi quyền.

### 25.3. Tạo và thu hồi quyền trong cùng transaction

Một mẫu triển khai cho hàm nhạy cảm:

~~~sql
BEGIN;

-- CREATE FUNCTION ... tại đây.

-- Thu hồi thực thi công khai của hàm mới.
-- REVOKE EXECUTE ON FUNCTION schema.func(types) FROM PUBLIC;

-- Cấp cho role được phép, sau khi đã tồn tại.
-- GRANT EXECUTE ON FUNCTION schema.func(types) TO app_role;

COMMIT;
~~~

Chạy các thao tác phù hợp cùng transaction giúp tránh một cửa sổ truy cập ngoài ý muốn.

### 25.4. Quyền trên schema cũng quan trọng

Để gọi hàm qua schema, role có thể cần `USAGE` trên schema và `EXECUTE` trên function. Kiểm tra privilege thực tế thay vì chỉ nhìn `GRANT EXECUTE`.

### 25.5. Default privileges cần chiến lược riêng

`ALTER DEFAULT PRIVILEGES` ảnh hưởng objects **được tạo trong tương lai** bởi role tương ứng theo quy tắc PostgreSQL. Không tự giả định một thiết lập theo schema sẽ xóa mọi quyền mặc định toàn cục đã có; cần thiết kế rõ global/per-schema defaults.

## 26. SECURITY INVOKER và SECURITY DEFINER

Mặc định, function chạy theo ngữ cảnh quyền của người gọi (**SECURITY INVOKER**).

Với `SECURITY DEFINER`, function thực thi với quyền của **function owner** theo quy tắc PostgreSQL. Điều này hữu ích để đóng gói thao tác có kiểm soát, nhưng tăng rủi ro security nếu thân hàm hoặc namespace không an toàn.

### 26.1. Ví dụ skeleton an toàn hơn

~~~sql
CREATE FUNCTION api_lab.read_product_price(
    p_product_id bigint
)
RETURNS numeric
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, api_lab, pg_temp
AS $$
    SELECT p.unit_price
    FROM api_lab.products AS p
    WHERE p.product_id = p_product_id
$$;
~~~

Đây là minh họa về cách **khóa search_path vào các schema tin cậy** và dùng qualified table name; vẫn phải kiểm soát owner, grants, caller, chính sách RLS và quyền dữ liệu thực tế.

### 26.2. Tại sao search_path nguy hiểm?

Nếu function definer dùng tên không qualified và một schema trong `search_path` cho phép người không tin cậy tạo đối tượng, kẻ tấn công có thể lợi dụng name resolution để chuyển hành vi sang một object không mong muốn.

### 26.3. pg_temp và function lookup

Schema tạm cần được xử lý cẩn thận trong `search_path` của SECURITY DEFINER. Đặt `pg_temp` phía sau các schema tin cậy là một mẫu phòng vệ quan trọng, nhưng **không thay thế việc dùng schema-qualified names và audit quyền**.

### 26.4. Dynamic SQL bên trong definer

Nếu body xây SQL bằng input người dùng, phải dùng parameter binding/`EXECUTE ... USING` và identifier quoting phù hợp (ví dụ `format('%I', ...)` khi thật cần) để tránh SQL injection hoặc thao túng identifier.

### 26.5. Đổi owner hoặc body có thể đổi security boundary

Một `CREATE OR REPLACE` cùng signature nhưng thêm `SECURITY DEFINER`, bỏ `SET search_path`, hoặc chuyển owner sang role quyền cao có thể tạo thay đổi an ninh lớn dù SQL clients vẫn gọi cùng tên.

## 27. Các bước chọn phương án thay đổi

Trước yêu cầu “sửa function”, hãy hỏi:

| Yêu cầu thay đổi | Hướng thường hợp lý |
| --- | --- |
| Sửa bug body, cùng input/return contract | `CREATE OR REPLACE` cùng signature |
| Thay volatility hoặc thuộc tính được hỗ trợ | `ALTER FUNCTION`/`CREATE OR REPLACE` có kiểm tra |
| Đổi tên routine | `ALTER FUNCTION ... RENAME` nhưng cập nhật callers; hoặc wrapper cũ |
| Thêm tham số input | Hàm mới/overload; đánh giá defaults và ambiguity |
| Đổi kiểu input | Hàm mới hoặc overload mới; migration callers |
| Đổi kiểu return | API v2 mới, cutover, sau đó dọn v1 |
| Đổi số cột của RETURNS TABLE | API v2 và migration phụ thuộc |
| Đổi named input parameter | Xem là breaking change; tạo API mới nếu cần |
| Cần thay đổi contract mà nhiều clients còn gọi | Expand–migrate–contract |
| Dọn hàm không còn dùng | Kiểm tra callers/dependencies rồi `DROP ... RESTRICT` |

### 27.1. Không đo độ an toàn bằng việc DDL chạy thành công

Lệnh `CREATE OR REPLACE` thành công **không chứng minh** client behavior và dữ liệu vẫn tương thích.

### 27.2. Không đổi return chỉ vì API muốn thêm field

Thêm một field có thể tạo hệ quả tới JDBC mapping, `SELECT * FROM function(...)`, record type và mọi view phụ thuộc. Thường rõ ràng hơn khi giới thiệu routine v2.

### 27.3. Giữ đường rollback

Khi có nhiều phiên bản ứng dụng cùng tồn tại, không xóa interface cũ ngay sau khi một service deploy thành công; còn worker, cron và phiên cũ có thể dùng nó.

## 28. Versioning: expand–migrate–contract

Một quy trình phổ biến:

~~~text
EXPAND
  - Tạo hàm v2 độc lập.
  - Giữ hàm v1 chạy như trước.
  - Cấp quyền, tạo index/objects liên quan.
         |
         v
MIGRATE
  - Deploy client gọi v2 từng đợt.
  - Theo dõi lỗi và hành vi.
  - Cho phép v1/v2 tồn tại song song.
         |
         v
CONTRACT
  - Chứng minh không còn client cần v1.
  - Kiểm tra catalog + code + job dependencies.
  - DROP v1 với RESTRICT khi an toàn.
~~~

### 28.1. Vì sao không thay đổi trực tiếp?

Một hệ thống có thể có:

- API server vừa deploy v2.
- Batch worker chưa restart vẫn dùng v1.
- Mobile/partner client gọi SQL qua gateway cũ.
- Scheduled report chạy mỗi đêm.

Giữ v1 trong giai đoạn chuyển tiếp làm các thành phần có thể nâng cấp không đồng thời.

### 28.2. Versioning theo tên

~~~text
api_lab.order_total(bigint)                -- v1
api_lab.order_total_v2(bigint, numeric)    -- v2
~~~

Rõ ràng, dễ routing và dễ rollback.

### 28.3. Versioning theo schema

Một hướng khác:

~~~text
api_v1.order_total(bigint)
api_v2.order_total(bigint, numeric)
~~~

Phù hợp khi muốn version cả tập routines. Nhưng quyền schema, `search_path` và deployment phải được quản lý rõ.

### 28.4. Overloading không phải versioning tự thân

Hai overload cùng tên có thể hợp lý khi **cùng một thao tác ngữ nghĩa** với kiểu input khác nhau. Nếu contract thay đổi lớn, tên v2 tường minh thường dễ quan sát và giảm nhập nhằng.

## 29. Tạo order_total_v2 trong lab

Yêu cầu mới: tính tổng đơn hàng với mức giảm giá phần trăm từ 0 đến 100.

### 29.1. Tạo hàm v2 độc lập

~~~sql
CREATE FUNCTION api_lab.order_total_v2(
    p_order_id bigint,
    p_discount_pct numeric
)
RETURNS numeric
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_base numeric;
BEGIN
    IF p_discount_pct IS NULL
       OR p_discount_pct < 0
       OR p_discount_pct > 100 THEN
        RAISE EXCEPTION
            'Invalid discount percentage: %',
            p_discount_pct
            USING ERRCODE = '22023';
    END IF;

    SELECT
        (o.quantity * p.unit_price)::numeric
    INTO v_base
    FROM api_lab.orders AS o
    JOIN api_lab.products AS p
      ON p.product_id = o.product_id
    WHERE o.order_id = p_order_id;

    IF NOT FOUND THEN
        RETURN NULL;
    END IF;

    RETURN round(
        v_base * (1 - p_discount_pct / 100),
        2
    );
END;
$$;
~~~

Hàm v2 **không gọi v1**; nó tính trực tiếp từ bảng nguồn. Điều này cho phép sau này dùng v1 làm wrapper sang v2 **mà không tạo vòng gọi đệ quy**.

### 29.2. Thử kết quả

~~~sql
SELECT
    api_lab.order_total(1001::bigint)
        AS v1_full_price,
    api_lab.order_total_v2(
        1001::bigint,
        10::numeric
    ) AS v2_ten_percent_discount;
~~~

Với dữ liệu mẫu:

~~~text
v1_full_price              = 200.00
v2_ten_percent_discount    = 180.00
~~~

### 29.3. Không thay đổi v1 khi tạo v2

Mọi view/client gọi `api_lab.order_total(bigint)` tiếp tục sử dụng hàm v1 như trước.

### 29.4. Dữ liệu không tìm thấy

Với một ID chưa tồn tại, ví dụ `999999`, hàm trả SQL `NULL` trong thiết kế lab. Đó là lựa chọn contract cần ghi rõ: một hệ thống khác có thể yêu cầu raise exception hoặc trả một result type có cờ `found`.

### 29.5. Kiểm tra đầu vào bất hợp lệ

`p_discount_pct < 0`, `>100` hoặc SQL `NULL` sẽ báo lỗi. Không ngầm chấp nhận giảm giá 120% hoặc biến mất số tiền.

## 30. Wrapper giữ chữ ký cũ

Sau khi v2 đã được triển khai/kiểm thử, có thể giữ chữ ký v1 nhưng chuyển cách tính sang lõi mới với mức giảm 0%.

~~~sql
CREATE OR REPLACE FUNCTION api_lab.order_total(
    p_order_id bigint
)
RETURNS numeric
LANGUAGE sql
STABLE
AS $$
    SELECT api_lab.order_total_v2(
        p_order_id,
        0::numeric
    )
$$;
~~~

### 30.1. Vì sao wrapper này không đệ quy?

`order_total_v2` đọc bảng nguồn trực tiếp, **không gọi `order_total`**. Luồng gọi:

~~~text
order_total(bigint)
        |
        v
order_total_v2(bigint,numeric)
        |
        v
orders JOIN products
~~~

Nếu v2 lại gọi v1 để lấy base amount, sau khi đổi v1 thành wrapper sang v2 sẽ tạo vòng gọi vô hạn. Đây là bẫy phổ biến khi refactor API.

### 30.2. Chữ ký v1 được bảo toàn

View `v_order_totals` và application SQL gọi `order_total(bigint)` không phải sửa tên.

### 30.3. Kết quả phải tương thích

Với p_discount_pct=0, v2 phải cho kết quả có ngữ nghĩa giống v1. Nếu v2 có rounding/validation/timezone khác, wrapper có thể tạo breaking change dù input/return type không đổi. Bài toán **semantic versioning** quan trọng không kém schema signature.

### 30.4. Wrapper cần được duy trì

Giữ wrapper cũ có thể cần chi phí xử lý thêm và tăng số routines. Tuy nhiên, chi phí này thường nhỏ hơn nguy cơ phá hàng loạt clients khi thay contract đột ngột.

## 31. Khi nào dùng overload thay vì tên v2?

Nếu API mới chỉ thêm một dạng lời gọi cùng ý nghĩa, bạn có thể tạo:

~~~sql
CREATE FUNCTION api_lab.order_total(
    p_order_id bigint,
    p_discount_pct numeric
)
RETURNS numeric
LANGUAGE sql
STABLE
AS $$
    SELECT api_lab.order_total_v2(
        p_order_id,
        p_discount_pct
    )
$$;
~~~

Bây giờ:

~~~sql
SELECT api_lab.order_total(1001::bigint);
SELECT api_lab.order_total(
    1001::bigint,
    10::numeric
);
~~~

có hai chữ ký rõ ràng.

### 31.1. Không đặt DEFAULT ở overload mới khi không cần

Nếu overload hai tham số khai báo `DEFAULT 0`, nó có thể cạnh tranh với overload một tham số. Trong lab, ta **không dùng DEFAULT** để hai call forms tách biệt.

### 31.2. Vẫn có risk từ unknown/null literals

Khi có thêm overload kiểu khác, literal chưa cast và SQL `NULL` có thể dẫn tới resolution không mong muốn. Nên bind/cast rõ khi client dùng JDBC/ORM.

### 31.3. Overload phù hợp hơn khi cùng semantics

`order_total(bigint)` và `order_total(bigint,numeric)` có thể là hai cách lấy cùng loại kết quả. Nhưng nếu v2 trả JSONB hoặc một bảng nhiều cột, tên v2 rõ ràng thường tốt hơn.

### 31.4. Không dùng overload để che breaking change

Nếu v2 đổi cách diễn giải ý nghĩa tham số, thêm overload có thể khiến reviewer nhầm rằng chỉ là convenience API. Hãy công bố contract và thời điểm deprecate.

## 32. Đổi tên, giữ alias và cutover

Giả sử muốn đổi `order_total` thành `calculate_order_total`.

### 32.1. Đổi tên trực tiếp

~~~sql
-- Chỉ minh họa, không chạy trong lab còn dùng tên cũ.
ALTER FUNCTION api_lab.order_total(bigint)
RENAME TO calculate_order_total;
~~~

Hàm vẫn có thể được view bound theo OID sử dụng, nhưng application đang viết `api_lab.order_total(1001)` sẽ không tìm thấy tên cũ.

### 32.2. Đường an toàn hơn

1. Tạo `calculate_order_total(...)` với contract mới.
2. Giữ `order_total(...)` gọi implementation tương ứng.
3. Chuyển ứng dụng từng đợt sang tên mới.
4. Chỉ gỡ tên cũ sau khi không còn callers/dependencies.

### 32.3. Đừng đổi schema bất ngờ

Chuyển từ `api_lab.order_total` sang `api_v2.order_total` sẽ phá mọi caller dùng tên schema đầy đủ cũ. Nếu caller dùng tên unqualified, `search_path` càng làm cutover khó dự đoán.

## 33. Xóa v1 sau khi deprecate

Khi chắc chắn không còn callers, một quy trình có thể:

1. Xác nhận phiên bản v2 đang phục vụ.
2. Xác nhận application logs cho thấy các lời gọi v1 đã dừng theo khoảng thời gian đủ dài.
3. Xác nhận dependencies trong database.
4. Gỡ/đổi những view, trigger, scheduled jobs còn tham chiếu.
5. Dùng `DROP FUNCTION ... RESTRICT` với chữ ký chính xác.
6. Nếu bị chặn, **dừng và xác định dependency**, không thêm `CASCADE` để vượt qua.
7. Sau drop, theo dõi lỗi `function ... does not exist` ở các clients còn sót.

### 33.1. Lab hiện tại còn view phụ thuộc

`api_lab.v_order_totals` vẫn gọi v1. Muốn drop v1, trước tiên phải quyết định sửa view (dùng API v2 có discount 0) hoặc giữ v1 làm compatibility wrapper.

### 33.2. CREATE OR REPLACE VIEW không tự giải quyết mọi đổi kiểu

Nếu query view mới thay đổi cột/kiểu theo cách không được `CREATE OR REPLACE VIEW` cho phép, cũng cần migration view versioned. Không giả định mọi dependency có thể thay bằng một lệnh.

### 33.3. Một cách cập nhật view mà không đổi output shape

~~~sql
CREATE OR REPLACE VIEW api_lab.v_order_totals AS
SELECT
    o.order_id,
    o.order_status,
    api_lab.order_total_v2(
        o.order_id,
        0::numeric
    ) AS order_total
FROM api_lab.orders AS o;
~~~

Giữ các cột và kiểu cũ, đồng thời chuyển dependency sang v2. Đây chỉ là **một bước**; các callers khác vẫn cần rà soát.

### 33.4. Kiểm tra lại DROP RESTRICT

Sau khi mọi recorded dependents và external callers đã xử lý, `DROP FUNCTION api_lab.order_total(bigint) RESTRICT` có thể thành công. Đừng drop trong khi ví dụ khác của lab còn muốn sử dụng v1.

## 34. Versioning và rollback trong migration

Một bản triển khai tốt xác định cả forward path và reverse path.

### 34.1. Kịch bản deploy

~~~text
Database migration A:
  - CREATE order_total_v2
  - GRANT quyền cần thiết
  - Kiểm tra v2

Application deploy B:
  - Chuyển một tỷ lệ clients sang v2
  - Theo dõi lỗi/độ trễ/kết quả

Application deploy C:
  - Chuyển phần clients còn lại
  - Giữ v1 trong cửa sổ rollback

Database migration D:
  - Deprecate và drop v1 sau khi được xác minh
~~~

### 34.2. Rollback app

Nếu deploy B lỗi, rollback application về lời gọi v1. Điều này chỉ an toàn nếu bạn **chưa drop hoặc thay đổi không tương thích** hàm v1.

### 34.3. Rollback database

Nếu v2 có bug logic, có thể dùng `CREATE OR REPLACE` v2 với cùng chữ ký và return contract để sửa, hoặc rollback DDL/định nghĩa theo quy trình. Nhưng nếu v2 đã tạo side effects hay thay dữ liệu, rollback code không tự khôi phục dữ liệu.

### 34.4. Phiên ứng dụng cũ còn sống

Kể cả sau khi deploy thành công, worker cũ, connection pool hoặc job dài có thể còn gọi v1. Cần một cửa sổ tương thích đủ dài cho lifecycle thực của hệ thống.

### 34.5. Down migration không phải luôn an toàn

Một schema migration đã đổi kiểu/cấu trúc dữ liệu hoặc xóa cột có thể không đảo ngược hoàn toàn. Rollback plan phải nói rõ phần nào là reversible, phần nào cần khôi phục backup/backfill.

## 35. Dependency với expression index và tính bất biến

Giả sử tạo function thuần:

~~~sql
CREATE FUNCTION api_lab.normalize_sku(
    p_sku text
)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT lower(btrim(p_sku))
$$;
~~~

Tạo index:

~~~sql
CREATE INDEX idx_products_normalized_sku
ON api_lab.products (
    api_lab.normalize_sku(sku)
);
~~~

### 35.1. Index phụ thuộc function

Index expression dùng function nên PostgreSQL có thể ghi dependency tới function. Khi cố `DROP FUNCTION ... RESTRICT`, index liên quan có thể chặn.

### 35.2. CREATE OR REPLACE vẫn có rủi ro

Giả sử sửa `normalize_sku` để bỏ dấu, thay encoding hoặc thêm quy tắc normalize, dù signature và return type không đổi, các **index entries cũ** đã được tính theo logic trước đó. Cần lập kế hoạch `REINDEX` (và kiểm tra môi trường/ghi chép migration) để dữ liệu index phản ánh logic mới.

### 35.3. Generated column cũng cần backfill theo tình huống

Nếu một stored generated column dùng function có logic thay đổi, việc chỉ thay definition của function không có nghĩa mọi **giá trị stored đã tính** tự biến đổi ngay. Cần kế hoạch tính lại giá trị từ dữ liệu nguồn.

### 35.4. IMMUTABLE là cam kết mạnh

Không gắn `IMMUTABLE` cho function phụ thuộc bảng hoặc configuration có thể đổi. Vi phạm cam kết có thể làm index/plan cho kết quả cũ hoặc sai.

## 36. Function dùng trong constraint và generated expression

Một số constraint dùng user-defined function:

~~~sql
-- Minh họa ý tưởng kiểm tra SKU bằng pure function.
-- CHECK (api_lab.valid_sku(sku))
~~~

### 36.1. Thay logic CHECK function có thể làm dữ liệu cũ “sai”

Nếu function `valid_sku` được đổi chặt hơn, những row đã được chấp nhận trước đó có thể không còn hợp lệ theo logic mới, nhưng PostgreSQL không mặc định quét và validate toàn bảng chỉ vì body function đổi.

### 36.2. Không dùng function đọc dữ liệu bảng khác như CHECK tùy tiện

CHECK constraints được thiết kế cho điều kiện phù hợp với tính bất biến trên hàng. Nếu function đọc bảng khác, giá trị có thể đổi mà PostgreSQL không biết cần kiểm tra lại, gây lỗi logic và dump/restore. Dùng FK hoặc ràng buộc dữ liệu phù hợp.

### 36.3. Migration nên validate dữ liệu riêng

Sau khi thay business rule, cần khảo sát hàng cũ và thực hiện validate/backfill/constraint migration phù hợp, không chỉ `CREATE OR REPLACE FUNCTION`.

### 36.4. Triggers cũng cần kiểm tra phụ thuộc

Trigger được gắn với trigger function; xóa/đổi return contract hoặc semantics của trigger function có thể làm thay đổi việc INSERT/UPDATE/DELETE. Xem trigger definitions và những hoạt động ngoài database như CDC/job.

## 37. Hàm dùng trong VIEW và MATERIALIZED VIEW

View thường gọi function và nhận output theo signature đã định:

~~~sql
CREATE VIEW api_lab.v_order_totals AS
SELECT
    o.order_id,
    o.order_status,
    api_lab.order_total(o.order_id) AS order_total
FROM api_lab.orders AS o;
~~~

### 37.1. View thường không lưu kết quả

Khi function body được `REPLACE` mà vẫn giữ contract, query view tương lai có thể dùng logic mới.

### 37.2. Materialized view lưu kết quả

Nếu một materialized view gọi function, thay body function không tự cập nhật **hàng vật hóa đã lưu**. Cần `REFRESH MATERIALIZED VIEW` theo chính sách tương ứng để kết quả phản ánh logic mới.

### 37.3. Đổi kiểu return có thể yêu cầu dựng lại view

Một view đã được phân tích với kiểu cột do function trả về. Khi đổi return type, phải xử lý dependency và contract của view, không chỉ đổi routine rồi kỳ vọng rewrite rule tự cập nhật.

### 37.4. Dependency graph có thể nhiều tầng

~~~text
Function
   ^
   |
View A
   ^
   |
View B
   ^
   |
Materialized View C
~~~

Xóa một routine có thể tác động gián tiếp tới các tầng dùng view. Vì vậy tuyệt đối không dùng `DROP ... CASCADE` khi chưa hiểu đầy đủ hậu quả.

## 38. Hàm và thủ tục: FUNCTION khác PROCEDURE

PostgreSQL phân biệt:

~~~sql
SELECT api_lab.order_total(1001::bigint);
~~~

và:

~~~sql
CALL api_lab.some_procedure(...);
~~~

### 38.1. FUNCTION

Function trả giá trị hoặc tập kết quả và có thể được gọi như biểu thức trong nhiều SQL contexts.

### 38.2. PROCEDURE

Procedure được gọi bằng `CALL`. Ở những điều kiện/phiên bản phù hợp, procedure có khả năng điều khiển transaction theo giới hạn PostgreSQL. Không coi `CALL` là biến thể cú pháp tương đương của `SELECT function(...)`.

### 38.3. Chữ ký và quản lý phiên bản procedure

Procedure cũng có tên, argument contract và khả năng overload/DDL quản lý, nhưng `CREATE OR REPLACE PROCEDURE`, `ALTER PROCEDURE` và `DROP PROCEDURE` là các lệnh tương ứng. Cần dùng routine kind đúng, không tự lấy `DROP FUNCTION` để xóa procedure.

### 38.4. Catalog chung pg_proc

`pg_proc.prokind` giúp phân biệt function (`f`) với procedure (`p`) khi rà soát một tên routine có nhiều biến thể.

## 39. JDBC/Java: chữ ký SQL là contract ở runtime

Trong Java, bạn có thể dùng `PreparedStatement`:

~~~java
String sql = "SELECT api_lab.order_total(?::bigint)";

try (PreparedStatement ps =
         connection.prepareStatement(sql)) {
    ps.setLong(1, orderId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            BigDecimal total = rs.getBigDecimal(1);
            // Có thể null nếu orderId không tồn tại.
        }
    }
}
~~~

### 39.1. Vì sao cast rõ?

`?::bigint` biểu diễn rõ overload kỳ vọng ở phía PostgreSQL. Với nhiều overload, điều này giúp tránh ambiguity do binding không xác định hoặc driver đổi kiểu parameter.

### 39.2. BigDecimal cho numeric

`numeric` nên được map sang `BigDecimal` thay vì `double` khi xử lý tiền. Nếu function v2 đổi return sang `jsonb`/record, code đọc `BigDecimal` sẽ cần sửa.

### 39.3. Parameter metadata và prepared statements

Ứng dụng có thể cache prepared statements hoặc dùng connection pool. Sau DDL thay đổi signature/return shape, những statement đã được chuẩn bị có thể cần được chuẩn bị lại, và có thể xuất hiện lỗi liên quan cached plan/result type tùy tình huống.

### 39.4. Named notation trong SQL của Java

Nếu query viết:

~~~sql
SELECT api_lab.apply_rate(
    p_amount => ?::numeric,
    p_rate => ?::numeric
);
~~~

thì việc đổi tên `p_rate` ảnh hưởng ngay tới câu SQL dù input types giữ nguyên.

### 39.5. Ghi nhận caller version

Nếu có nhiều phiên bản ứng dụng dùng cùng database, ghi metric/log của endpoint hoặc query name/version để biết hàm v1 còn được gọi không. System catalog không tự cho bạn danh sách Java services đang dùng nó.

## 40. Default values, NULL, lỗi trả về và hợp đồng nghiệp vụ

Khi tăng phiên bản, không chỉ kiểu input/output cần giống; những trường hợp biên cũng cần được bảo toàn hoặc công bố thay đổi.

### 40.1. NULL input

Với một hàm `STRICT`:

~~~sql
CREATE FUNCTION api_lab.is_nonblank(
    p_text text
)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT length(btrim(p_text)) > 0
$$;
~~~

PostgreSQL không gọi body khi `p_text` là SQL NULL và trả NULL.

### 40.2. Hàm không STRICT có thể xử lý NULL riêng

~~~sql
CREATE FUNCTION api_lab.is_nonblank_or_false(
    p_text text
)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT coalesce(
        length(btrim(p_text)) > 0,
        false
    )
$$;
~~~

Với SQL NULL, hàm này trả `false`; khác contract của `is_nonblank`.

### 40.3. Không đồng nhất “không tìm thấy” với “giá trị 0”

Trong lab, `order_total(9999)` trả SQL NULL nếu không có order. Nếu version mới trả `0` cho cùng ID, đó là **semantic change** có thể che giấu lỗi nghiệp vụ.

### 40.4. Exception cũng là một phần contract

V2 đang raise exception SQLSTATE `22023` cho discount ngoài 0..100. Caller Java có thể xử lý loại lỗi này để trả HTTP 400. Nếu v3 thay bằng `NULL` hoặc thông báo khác, cần cập nhật chính sách xử lý lỗi.

### 40.5. Đặt quy ước ổn định

Tài liệu API nên nêu rõ:

- Trường hợp không tìm thấy.
- Kiểu và độ chính xác số.
- Quy tắc làm tròn.
- Timezone.
- Xử lý SQL NULL.
- Exception/SQLSTATE.
- Có side effects hay không.

## 41. Dependency không đồng nghĩa kiểm soát mọi caller

Ngay cả khi một function không còn thấy dependent object trong `pg_depend`, những chỗ sau vẫn có thể gọi nó:

~~~text
Java source
Spring Data native query
JOOQ/ORM generated SQL
Scheduled job/BI dashboard
Stored procedure dynamic EXECUTE
SQL literal trong application settings
ETL/CDC transformation
CLI scripts và notebook
External partner integration
~~~

### 41.1. Vì sao kiểm tra trong database là chưa đủ?

Không có một quan hệ catalog chắc chắn được sinh ra mỗi khi một chương trình bên ngoài *có thể* gọi function trong tương lai.

### 41.2. Ngay cả các function trong database cũng không đơn giản

Body ngôn ngữ PL/pgSQL hoặc SQL string có thể không ghi đầy đủ phụ thuộc tới mọi object xuất hiện trong code. Dynamic SQL đặc biệt khó thống kê.

### 41.3. Cần source-level và runtime-level evidence

Một dự án có thể kết hợp:

- Search trong repository và migration scripts.
- Catalog queries.
- API/SQL query logs được kiểm soát quyền và chi phí.
- Tracing theo function/query endpoint.
- Canary deploy để phát hiện call forms không tương thích.

**Không kết luận “an toàn để drop” chỉ từ một phép đếm `pg_depend` bằng 0.**

## 42. Transactional DDL và giới hạn rollback

PostgreSQL hỗ trợ nhiều thao tác DDL trong transaction:

~~~sql
BEGIN;

-- CREATE OR REPLACE FUNCTION ...
-- GRANT / REVOKE ...
-- CREATE OR REPLACE VIEW ...

COMMIT;
~~~

### 42.1. Lợi ích

Khi thay đổi liên quan cùng một nhóm objects và có thể thực hiện trong transaction, lỗi một bước có thể cho phép rollback các thay đổi chưa commit.

### 42.2. Nhưng transaction không giải quyết mọi migration

Một deploy có nhiều service, dữ liệu được sửa bằng side-effect, cache bên ngoài hoặc background job không được tự rollback chỉ vì SQL migration rollback.

### 42.3. Long-running transaction

Giữ transaction migration quá lâu có thể giữ khóa, khiến các query/DDL khác phải chờ, làm giảm availability. Với thao tác chậm, cần phân tách các giai đoạn và thiết kế tương thích giữa chúng.

### 42.4. Advisory or migration lock

Nhiều deployment workers cùng chạy migration có thể tranh chấp. Một hệ thống migration nên có điều phối để chỉ một migration owner thực hiện tại một thời điểm.

## 43. CI/CD và quản lý lịch sử hàm

Đối với một hệ thống dùng nhiều functions, nên lưu định nghĩa hàm và migration SQL trong version control.

Ví dụ cấu trúc logic:

~~~text
database/
  migrations/
    V001__create_orders.sql
    V012__create_order_total_v1.sql
    V025__add_order_total_v2.sql
    V030__switch_view_to_v2.sql
    V041__deprecate_order_total_v1.sql
  routines/
    order_total_v1.sql
    order_total_v2.sql
~~~

Đây chỉ là cấu trúc minh họa; framework migrations thực tế có thể có quy tắc đặt tên và thứ tự khác.

### 43.1. Chia migration thành các bước độc lập khi cần

Đừng gộp thêm v2, chuyển toàn bộ client và drop v1 trong một bản deploy nếu các thành phần không thể nâng cấp nguyên tử.

### 43.2. Dùng DDL idempotent cẩn thận

`CREATE OR REPLACE` giúp chạy lại một số migration cho cùng signature, nhưng không làm thay đổi return type mà không phá dependency. `DROP IF EXISTS` tránh lỗi thiếu object nhưng không bảo đảm lệnh an toàn với dữ liệu/clients.

### 43.3. Kiểm tra chữ ký trước và sau

Lưu danh sách `regprocedure` và kết quả `pg_get_function_identity_arguments`, `pg_get_function_result` trước/sau giúp phát hiện chữ ký mới bị tạo ngoài ý muốn.

### 43.4. Quyền là một phần migration

Cần test bằng role ứng dụng thật hoặc role mô phỏng có đúng privileges, không chỉ superuser. Một function gọi được dưới DBA nhưng bị chặn dưới app role là lỗi deploy.

### 43.5. Test backward compatibility

Trong giai đoạn v1 và v2 cùng tồn tại, CI có thể test:

- Query v1 vẫn trả dữ liệu/shape như trước.
- Query v2 xử lý input mới/biên.
- Views/procedures phụ thuộc còn chạy.
- Permissions đủ cho app role.
- Index/constraint dùng hàm còn hợp lệ.

## 44. Quan sát việc hàm được gọi

Ngoài source search và pg_depend, thống kê PostgreSQL có thể hỗ trợ đánh giá mức dùng function nếu đã cấu hình thu thập phù hợp.

### 44.1. pg_stat_user_functions

~~~sql
SELECT
    schemaname,
    funcname,
    calls,
    total_time,
    self_time
FROM pg_stat_user_functions
WHERE schemaname = 'api_lab'
ORDER BY calls DESC;
~~~

### 44.2. Không mặc định có đầy đủ số liệu

Thống kê function phụ thuộc cấu hình như `track_functions` và ngữ cảnh thực thi; một số hàm (đặc biệt SQL function có thể inline theo plan) có thể không được phản ánh như bạn kỳ vọng. Số `calls=0` **không chứng minh** không có client nào phụ thuộc vào function.

### 44.3. Khoảng thời gian quan sát

Counters có thể reset và không bao phủ toàn bộ lịch sử deploy. Để deprecate v1, cần thu thập metrics trong một cửa sổ đủ dài bao gồm job ít chạy (ví dụ báo cáo hàng tuần/tháng).

### 44.4. Cẩn thận với log chứa tham số nhạy cảm

SQL logs có thể chứa PII/financial data. Thiết kế quan sát cần tránh ghi dữ liệu nhạy cảm không cần thiết, giới hạn quyền đọc và retention.

## 45. Các lỗi thiết kế phổ biến

### Lỗi 1. Nghĩ đổi parameter types bằng CREATE OR REPLACE là sửa cùng hàm

Identity khác tạo overload mới, không thay routine cũ.

### Lỗi 2. Nghĩ return type dùng để phân biệt overload

PostgreSQL không cho hai function cùng input signature chỉ khác return type.

### Lỗi 3. Đổi input parameter name rồi cho rằng không breaking

Named calls dựa vào tên; `CREATE OR REPLACE` cũng có các giới hạn khi đổi tên input đã đặt.

### Lỗi 4. Thêm DEFAULT vào overload mới mà không kiểm tra ambiguity

Một lời gọi ít đối số có thể phù hợp nhiều routine. Đặc biệt nguy hiểm với ứng dụng dùng literal unknown hoặc NULL.

### Lỗi 5. Không cast JDBC parameters

Kiểu parameter không rõ có thể chọn overload khác hoặc gây lỗi resolution. Dùng bind/cast đúng contract.

### Lỗi 6. Dùng DROP FUNCTION không ghi kiểu input

Khi có nhiều overload, tên không đủ để nêu đúng function; hãy dùng `function_name(type,...)`.

### Lỗi 7. Thêm CASCADE để bỏ lỗi dependency

`CASCADE` có thể xóa view, index, constraint hoặc object phụ thuộc quan trọng.

### Lỗi 8. Nghĩ pg_depend cho biết toàn bộ ứng dụng đang gọi hàm

Catalog chỉ chứa dependencies được PostgreSQL ghi nhận. Java/JDBC, dynamic SQL và body string có thể không được bao phủ.

### Lỗi 9. Nghĩ SQL string body được track giống SQL-standard body

Phân tích/ghi nhận dependencies có khác biệt. Đừng dựa vào một catalog scan để bảo đảm đã nhìn thấy mọi bảng hàm đọc.

### Lỗi 10. Quên view rewrite dependencies

View gọi hàm có thể làm DROP RESTRICT thất bại; điều đó là biện pháp bảo vệ, không phải lỗi cần vượt bằng CASCADE.

### Lỗi 11. Đổi tên bằng ALTER rồi bỏ quên client gọi tên cũ

Object OID được giữ nhưng lời gọi SQL từ ứng dụng vẫn dùng tên, có thể hỏng.

### Lỗi 12. Đổi schema nhưng không cập nhật qualified names

`api_lab.func` không tự biến thành `api_v2.func` trong Java SQL và migration scripts.

### Lỗi 13. Thay body giữ signature nhưng đổi semantics

NULL behavior, rounding, timezone và exceptions đều thuộc contract; không kiểm tra chúng có thể trả sai kết quả.

### Lỗi 14. Khai báo IMMUTABLE cho hàm đọc bảng

Kết quả phụ thuộc dữ liệu thay đổi; khai báo sai có thể làm index/optimizer giữ giả định không đúng.

### Lỗi 15. Sửa IMMUTABLE function dùng trong index mà không REINDEX

Entries cũ có thể được tính theo logic trước và không tự tái tính cho mọi row chỉ vì function body đổi.

### Lỗi 16. Quên stored generated columns

Giá trị lưu có thể không tự đổi khi logic function phụ thuộc thay đổi; cần backfill/recompute.

### Lỗi 17. Đổi SECURITY DEFINER không kiểm tra search_path

Một schema không tin cậy trong name resolution có thể gây lỗ hổng hoặc thực thi nhầm object.

### Lỗi 18. DROP/CREATE làm mất grants

Function mới có OID/owner/ACL mặc định khác; app role có thể mất EXECUTE hoặc PUBLIC được cấp ngoài ý muốn.

### Lỗi 19. Giả định REPLACE sửa mọi quyền

`CREATE OR REPLACE` thường giữ ownership/privileges cũ; nếu cần thay quyền, phải có `GRANT/REVOKE`/owner migration rõ.

### Lỗi 20. Đổi hàm rồi nghĩ materialized view tự tính lại

MV lưu kết quả vật lý; cần refresh để dùng logic function mới.

### Lỗi 21. Wrapper v1 gọi v2 trong khi v2 gọi ngược v1

Tạo vòng đệ quy không mong muốn. Tách core implementation hoặc đảm bảo graph lời gọi không vòng.

### Lỗi 22. Dọn v1 ngay sau một đợt deploy

Các worker cũ, scheduled jobs hoặc clients ngoài hệ thống có thể còn gọi v1.

### Lỗi 23. Dựa vào pg_stat_user_functions calls=0 để drop

Instrumentation và cửa sổ quan sát có hạn; số 0 không chứng minh không còn caller.

### Lỗi 24. Migration chạy chỉ dưới superuser

Không phát hiện lỗi quyền `USAGE` schema, `EXECUTE` function hoặc SECURITY INVOKER access của app role.

### Lỗi 25. Dùng function chứa side effects mà khai báo STABLE/IMMUTABLE

Volatility sai tạo giả định planner/semantics không phù hợp; việc gọi trong query khác có thể cho kết quả bất ngờ.

### Lỗi 26. Cho rằng RESTRICT phát hiện mọi external dependency

RESTRICT ngăn xóa khi có dependencies catalog, không ngăn client ở ngoài DB vẫn gọi.

### Lỗi 27. Rollback DDL mà quên dữ liệu/side effects

Nếu v2 thay dữ liệu hoặc gọi service bên ngoài, rollback định nghĩa hàm không khôi phục tự động các side effects đó.

### Lỗi 28. Chuyển return scalar sang RETURNS TABLE không đổi clients

Type và column shape đổi làm hỏng JDBC mapper, view/function phụ thuộc và contract SQL.

### Lỗi 29. Thay function dùng trong CHECK mà không validate hàng cũ

Data trước đây hợp lệ có thể không phù hợp rule mới; PostgreSQL không tự quét lại tất cả row khi body function đổi.

### Lỗi 30. Tạo overload với default rồi không chạy compatibility tests

Các câu positional/named/NULL/unknown có thể chọn overload không mong đợi hoặc báo ambiguity.

## 46. Bài tập thực hành

Các bài dựa trên `api_lab`. Những bài `DROP`, `RENAME` hoặc đổi contract nên thực hiện trong bản sao database lab hoặc trả lời dưới dạng SQL minh họa, tránh phá các ví dụ đang dùng.

### Bài 1. Định danh hàm

PostgreSQL phân biệt hai overload `label_value(integer)` và `label_value(text)` dựa trên điều gì?

### Bài 2. Kiểu trả về

Có thể tạo hai hàm `convert(integer)` cùng schema, chỉ khác `RETURNS text` và `RETURNS numeric` không?

### Bài 3. IN và OUT

Tại sao tham số `OUT` không đủ để tạo hai overload input giống nhau?

### Bài 4. Default arguments

`apply_rate(numeric,numeric DEFAULT 10)` có identity gồm mấy kiểu đầu vào?

### Bài 5. Named arguments

Viết lời gọi `apply_rate` bằng named notation với amount=100, rate=7.

### Bài 6. Ambiguity

Giải thích rủi ro khi cùng schema có `tax(numeric)` và `tax(numeric,numeric DEFAULT 10)`.

### Bài 7. Đúng overload

Viết hai câu gọi `label_value` với kiểu tường minh integer và text.

### Bài 8. regprocedure

Viết SQL lấy OID/identity của `api_lab.order_total(bigint)` mà không nhầm overload.

### Bài 9. to_regprocedure

Viết câu kiểm tra routine tồn tại mà không bắt buộc raise exception khi không có.

### Bài 10. Catalog

Viết SQL liệt kê tên, identity arguments và return type của mọi function trong `api_lab`.

### Bài 11. Lấy function definition

Viết SQL xem định nghĩa DDL hiện tại của `api_lab.order_total(bigint)`.

### Bài 12. CREATE OR REPLACE

Nếu chỉ đổi cách làm tròn trong thân hàm nhưng giữ input/return types, nên dùng hướng nào?

### Bài 13. Thêm input

Nếu thêm `p_discount_pct numeric` vào `order_total(bigint)`, PostgreSQL có tự thay function cũ không?

### Bài 14. Return type

Có thể dùng `CREATE OR REPLACE FUNCTION order_total(bigint) RETURNS text` để đổi trực tiếp từ numeric không?

### Bài 15. View phụ thuộc

Viết query tìm view dùng `api_lab.order_total(bigint)` qua `pg_depend` và `pg_rewrite`.

### Bài 16. SQL bodies

Vì sao catalog dependency của một SQL function body dạng `AS $$ ... $$` có thể khác SQL-standard `BEGIN ATOMIC ... END`?

### Bài 17. RESTRICT

Điều gì xảy ra khi chạy `DROP FUNCTION api_lab.order_total(bigint) RESTRICT` trong khi `v_order_totals` còn phụ thuộc?

### Bài 18. CASCADE

Giải thích vì sao không nên dùng `DROP FUNCTION ... CASCADE` chỉ để vượt lỗi dependency.

### Bài 19. ALTER FUNCTION RENAME

Đổi tên function bằng `ALTER FUNCTION` có tự sửa câu SQL trong ứng dụng Java đang gọi tên cũ không?

### Bài 20. Quyền

Khác biệt quan trọng về owner/EXECUTE khi `CREATE OR REPLACE` và `DROP + CREATE` cùng function?

### Bài 21. SECURITY DEFINER

Nêu hai yêu cầu quan trọng để giảm rủi ro khi tạo function SECURITY DEFINER.

### Bài 22. VOLATILITY

Tại sao `api_lab.order_total(bigint)` đọc bảng nguồn không phải IMMUTABLE?

### Bài 23. Hàm v2

Viết lời gọi tính order 1001 sau giảm giá 10% bằng `order_total_v2` và dự kiến kết quả.

### Bài 24. Wrapper

Tại sao cần bảo đảm `order_total_v2` không gọi ngược v1 nếu v1 được sửa thành wrapper gọi v2?

### Bài 25. Overload mới

Viết overload `order_total(bigint,numeric)` không có default, delegate sang `order_total_v2`.

### Bài 26. Expand–migrate–contract

Nêu thứ tự triển khai khi Java service A dùng v1 và service B sắp dùng v2.

### Bài 27. Index expression

Nếu đổi logic `normalize_sku` được dùng trong expression index, điều gì cần làm với index?

### Bài 28. Stored generated column

Tại sao chỉ `REINDEX` không nhất thiết cập nhật giá trị stored generated column khi logic function đổi?

### Bài 29. MV

Một materialized view gọi `order_total` có tự phản ánh body function mới ngay sau `CREATE OR REPLACE` không?

### Bài 30. PLpgSQL dynamic SQL

Vì sao `pg_depend` không thể tự mô tả đầy đủ mọi bảng được gọi bằng `EXECUTE format(...)`?

### Bài 31. JDBC

Viết một câu `SELECT` có placeholder và cast `bigint` để ứng dụng Java chọn đúng overload.

### Bài 32. NULL contract

`order_total(999999)` trong lab trả gì? Vì sao đổi thành 0 có thể là breaking change?

### Bài 33. pg_stat_user_functions

`calls=0` có đủ chứng minh không còn client gọi function? Vì sao?

### Bài 34. Procedure

Sự khác nhau cơ bản giữa `SELECT function(...)` và `CALL procedure(...)` là gì?

### Bài 35. Migration rollback

Nếu deploy v2 có lỗi, điều kiện nào giúp rollback application sang v1 an toàn?

### Bài 36. Dọn hàm

Nêu một checklist ngắn trước khi `DROP FUNCTION ... RESTRICT` để ngừng v1.

## 47. Lời giải tham khảo

### Bài 1–4. Identity và modes

Identity phụ thuộc schema/name và kiểu input arguments. Return type không phân biệt overload. OUT xác định result contract, không tạo một overload mới chỉ nhờ khác OUT. Hàm `apply_rate(numeric,numeric DEFAULT 10)` có hai input types trong identity.

### Bài 5. Named notation

~~~sql
SELECT api_lab.apply_rate(
    p_rate => 7::numeric,
    p_amount => 100::numeric
);
~~~

### Bài 6. Default và overload

Cả hàm một tham số và hàm hai tham số với default có thể phù hợp với lời gọi một đối số. Đây là thiết kế dễ gây ambiguity; cần dùng tên mới hoặc loại bỏ overload cạnh tranh, sau khi xem compatibility.

### Bài 7. Kiểu tường minh

~~~sql
SELECT api_lab.label_value(42::integer);
SELECT api_lab.label_value('42'::text);
~~~

### Bài 8–9. regprocedure

~~~sql
SELECT 'api_lab.order_total(bigint)'::regprocedure;

SELECT to_regprocedure(
    'api_lab.order_total(bigint)'
);
~~~

### Bài 10. pg_proc

~~~sql
SELECT
    p.oid::regprocedure AS function_name,
    pg_get_function_identity_arguments(p.oid)
        AS input_identity,
    pg_get_function_result(p.oid) AS return_type
FROM pg_proc AS p
JOIN pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE n.nspname = 'api_lab'
  AND p.prokind = 'f'
ORDER BY function_name::text;
~~~

### Bài 11. Function DDL

~~~sql
SELECT pg_get_functiondef(
    'api_lab.order_total(bigint)'::regprocedure
);
~~~

### Bài 12–14. REPLACE và breaking changes

Giữ nguyên identity/return type thì dùng `CREATE OR REPLACE` để sửa body. Thêm input type tạo signature mới/overload. Đổi return `numeric` sang `text` không được hỗ trợ trực tiếp bởi `CREATE OR REPLACE` với cùng signature; hãy dùng API mới và migration callers/dependencies.

### Bài 15. View dependency

~~~sql
SELECT
    c.oid::regclass AS view_name
FROM pg_depend AS d
JOIN pg_rewrite AS r
  ON r.oid = d.objid
JOIN pg_class AS c
  ON c.oid = r.ev_class
WHERE d.classid = 'pg_rewrite'::regclass
  AND d.refclassid = 'pg_proc'::regclass
  AND d.refobjid =
      'api_lab.order_total(bigint)'::regprocedure;
~~~

### Bài 16. Dependency tracking

SQL-standard body được phân tích khi định nghĩa và có thể ghi direct dependencies. Function body dạng string literal/PLpgSQL/dynamic SQL không bảo đảm ghi đủ mọi reference bên trong thân vào `pg_depend`.

### Bài 17–18. DROP behavior

`RESTRICT` từ chối drop khi view `v_order_totals` phụ thuộc. `CASCADE` có thể xóa view và dependent objects khác; không nên dùng chỉ để vượt lỗi.

### Bài 19. Rename

Không. Tên SQL trong Java không tự được PostgreSQL thay; phải giữ wrapper hoặc deploy client chuyển sang tên mới.

### Bài 20. Permissions

`CREATE OR REPLACE` thường giữ OID/owner/ACL của hàm cũ. `DROP/CREATE` tạo object mới với các thuộc tính quyền/owner theo thao tác tạo và defaults; phải kiểm tra lại grants.

### Bài 21. Security

Dùng schema tin cậy và `SET search_path` an toàn, qualified object names, kiểm soát owner/privileges cùng input; kiểm tra dynamic SQL và security boundary.

### Bài 22. STABLE

Vì kết quả phụ thuộc `api_lab.orders/products` có thể đổi. `STABLE` phù hợp để đọc theo snapshot của statement; `IMMUTABLE` hứa kết quả không đổi với cùng input trong mọi tình huống.

### Bài 23. v2

~~~sql
SELECT api_lab.order_total_v2(
    1001::bigint,
    10::numeric
);
~~~

Kết quả với dữ liệu mẫu: `180.00`.

### Bài 24. Recursion

Nếu v1 gọi v2 và v2 gọi v1, tạo vòng recursion không chủ ý. V2 cần logic core độc lập hoặc dùng một implementation thứ ba không quay ngược về wrapper.

### Bài 25. Overload không default

~~~sql
CREATE FUNCTION api_lab.order_total(
    p_order_id bigint,
    p_discount_pct numeric
)
RETURNS numeric
LANGUAGE sql
STABLE
AS $$
    SELECT api_lab.order_total_v2(
        p_order_id,
        p_discount_pct
    )
$$;
~~~

### Bài 26. Migrate

Tạo và cấp quyền v2 trước; giữ v1; deploy B gọi v2; theo dõi metrics/lỗi; chuyển A; quan sát các job cũ; chỉ drop v1 khi callers đã chuyển và dependency graph được giải quyết.

### Bài 27–28. Index và stored values

Expression index chứa kết quả function cũ có thể cần `REINDEX` sau khi logic đổi. Stored generated columns là **giá trị vật lý đã lưu**: `REINDEX` trên các giá trị đó không tự tính lại expression từ source columns; phải thực hiện backfill/recompute phù hợp.

### Bài 29. Materialized view

Không. Materialized view lưu dữ liệu tại lần refresh; đổi logic function không cập nhật nội dung cũ. Cần `REFRESH MATERIALIZED VIEW` theo thiết kế vận hành.

### Bài 30. Dynamic SQL

Tên bảng được xây ở runtime nên không có tập đối tượng tĩnh để dependency tracker liệt kê đủ tại thời điểm tạo routine.

### Bài 31. JDBC

~~~sql
SELECT api_lab.order_total(?::bigint);
~~~

Driver bind giá trị phù hợp kiểu `bigint`.

### Bài 32. NULL contract

Hàm SQL scalar v1 trả SQL `NULL` cho order ID không tồn tại. Đổi thành 0 có thể làm app nhầm “không có đơn” thành “đơn có tổng tiền bằng 0”.

### Bài 33. Statistics

Không. `track_functions` có thể chưa bật, function có thể inline hoặc thống kê reset, và vẫn có clients không gọi trong cửa sổ quan sát. Cần thêm code search, catalog, logs/metrics và deprecation window.

### Bài 34. Procedure

Function được gọi qua `SELECT`/biểu thức và trả kết quả; procedure được gọi qua `CALL` và có semantics/transaction-control khác trong những điều kiện được hỗ trợ.

### Bài 35. Rollback

V1 còn tồn tại, vẫn có quyền và behavior tương thích; dữ liệu/schema không bị thay theo cách v1 không thể xử lý; các callers chưa bị buộc dùng v2.

### Bài 36. Checklist dọn v1

Xác nhận: callers trong code và jobs đã chuyển, metrics/log bao phủ cửa sổ đủ dài, view/index/constraints/procedures không còn phụ thuộc, v2 hoạt động và có rollback plan, backup/DDL được kiểm soát. Sau đó thử `DROP FUNCTION ... RESTRICT` với đúng signature; nếu bị chặn thì điều tra, không tự thêm CASCADE.

## 48. Bảng tra cứu nhanh

| Việc cần làm | Cú pháp/công cụ |
| --- | --- |
| Gọi overload rõ kiểu | `api_lab.func(1::bigint)` |
| Xác định routine bằng signature | `'schema.func(bigint)'::regprocedure` |
| Lookup không tồn tại | `to_regprocedure('schema.func(bigint)')` |
| Lấy input identity | `pg_get_function_identity_arguments(oid)` |
| Lấy tham số khai báo | `pg_get_function_arguments(oid)` |
| Lấy return type | `pg_get_function_result(oid)` |
| Lấy DDL | `pg_get_functiondef(oid)` |
| Liệt kê routines | `pg_proc` + `pg_namespace` |
| Xem dependencies catalog | `pg_depend`, `pg_rewrite` |
| Đổi thân cùng chữ ký/return | `CREATE OR REPLACE FUNCTION` |
| Đổi tên routine | `ALTER FUNCTION f(types) RENAME TO name` |
| Đổi schema | `ALTER FUNCTION f(types) SET SCHEMA schema` |
| Đổi owner | `ALTER FUNCTION f(types) OWNER TO role` |
| Drop không tự xóa dependent | `DROP FUNCTION f(types) RESTRICT` |
| Drop dây chuyền (nguy hiểm) | `DROP FUNCTION f(types) CASCADE` |
| Tạo version mới | `CREATE FUNCTION ..._v2(...)` |
| Giữ API cũ | Compatibility wrapper với signature cũ |
| Loại overload ambiguity | Tránh DEFAULT cạnh tranh; bind/cast rõ |
| Thu hồi thực thi công khai | `REVOKE EXECUTE ON FUNCTION ... FROM PUBLIC` |
| Cấp thực thi app role | `GRANT EXECUTE ON FUNCTION ... TO role` |
| Security boundary | `SECURITY DEFINER` với `SET search_path` an toàn |
| Hàm chỉ đọc bảng | Thường cân nhắc `STABLE`, không `IMMUTABLE` |
| Expression index phụ thuộc hàm | Lên kế hoạch `REINDEX` khi body semantic thay |
| Stored generated values | Backfill/recompute khi logic phụ thuộc đổi |
| MV phụ thuộc function | Refresh dữ liệu vật hóa khi cần |
| Procedure | `CALL` và `ALTER/DROP PROCEDURE` |
| Runtime function statistics | `pg_stat_user_functions` nếu đã bật tracking |

## 49. Checklist thay đổi hàm trong production

1. **Xác định đúng schema/name/input types** của routine cần đổi?
2. Đã xem `pg_get_functiondef`, return type, defaults, names và modes chưa?
3. Đang sửa **body**, **signature**, **return shape** hay **semantics**?
4. Có overload cạnh tranh vì defaults/unknown/NULL không?
5. Named notation callers có bị ảnh hưởng khi đổi parameter names?
6. `CREATE OR REPLACE` có giữ đúng OID/ACL và những thuộc tính cần không?
7. Thay đổi có ảnh hưởng volatility, STRICT, parallel, cost hoặc security?
8. `SECURITY DEFINER` có owner/search_path/qualified names an toàn?
9. Đã liệt kê recorded dependencies từ `pg_depend`/view rules?
10. Đã kiểm tra source-level callers và dynamic SQL ngoài catalog?
11. Đã xét trigger/index/constraint/generated column dùng function?
12. Nếu function dùng trong index, có cần `REINDEX`?
13. Nếu function dùng trong stored values/MV, có cần recompute/refresh?
14. Nếu kiểu trả về thay đổi, có API v2 và kế hoạch chuyển callers?
15. Đã cấp lại `USAGE` schema/`EXECUTE` theo vai trò?
16. Có giai đoạn v1/v2 cùng hoạt động để rollback?
17. Các services/job cũ có thể còn chạy trong bao lâu?
18. Có metrics và logs cho lỗi call resolution, query timeout, SQLSTATE?
19. CI đã test positional, named, NULL, unknown literal, default args?
20. Có thể chạy migration DDL trong transaction ngắn và an toàn?
21. Đã xác định cách xử lý rollback nếu v2 đổi dữ liệu?
22. Đã có lịch deprecation cho v1 và owners của các consumers?
23. `DROP ... RESTRICT` được dùng sau khi giải quyết dependency?
24. Có quy định **không tự thêm CASCADE** khi migration lỗi?
25. Đã xác minh version database thực hỗ trợ cú pháp định dùng?

## 50. Tổng kết

Trong PostgreSQL, **chữ ký hàm** là một phần quan trọng của giao diện database: tên, schema và các kiểu tham số đầu vào xác định overload; tên tham số, defaults, modes và kiểu trả về vẫn có thể ảnh hưởng callers dù không cùng vai trò định danh.

Nhớ năm nguyên tắc cốt lõi:

1. **`CREATE OR REPLACE FUNCTION` không phải lệnh đổi chữ ký.** Với input types khác, PostgreSQL có thể tạo overload mới. Với cùng identity, không thể đổi trực tiếp return type theo ý muốn; vẫn cần migration.
2. **Dependencies có hướng và không đầy đủ cho mọi call site.** `pg_depend` giúp bảo vệ recorded objects, nhưng SQL string bodies, PL/pgSQL dynamic SQL, Java/JDBC và external jobs không luôn được catalog liệt kê.
3. **`DROP FUNCTION ... RESTRICT` là biện pháp an toàn mặc định.** `CASCADE` có thể xóa dây chuyền views/indexes/constraints; không dùng để vượt lỗi mà chưa hiểu tác động.
4. **Versioning kiểu expand–migrate–contract giúp giảm gián đoạn.** Tạo v2, giữ v1/wrapper, chuyển clients từng bước, quan sát lỗi và chỉ gỡ v1 khi thực sự không còn phụ thuộc.
5. **Contract không chỉ là kiểu dữ liệu.** Cần giữ hoặc công bố thay đổi về SQL NULL, exceptions, rounding, volatility, privileges, `SECURITY DEFINER`, index-derived values và stored/materalized outputs.

Khi được yêu cầu “chỉ thêm một tham số” hoặc “chỉ đổi kiểu trả về”, hãy bắt đầu bằng ba câu hỏi: **“Đây có còn là cùng một identity trong PostgreSQL không?”, “Có những dependent objects/callers nào cần tương thích?”, và “Khi deploy lỗi, chúng ta có thể quay về API cũ không?”**. Trả lời rõ ba câu ấy trước khi chạy DDL sẽ giúp bạn quản lý phiên bản hàm an toàn, có thể kiểm chứng và có đường rollback.
