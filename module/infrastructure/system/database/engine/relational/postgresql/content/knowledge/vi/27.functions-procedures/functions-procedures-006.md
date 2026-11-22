# Thuộc tính volatility, STRICT và parallel safety của hàm PostgreSQL

Khi viết một hàm PostgreSQL, bạn không chỉ quyết định **hàm tính toán điều gì**. Bạn còn phải khai báo các đặc tính để PostgreSQL biết **khi nào được phép tối ưu lời gọi hàm, điều gì xảy ra khi tham số là `NULL` và hàm có an toàn trong kế hoạch truy vấn song song hay không**.

Ba nhóm thuộc tính quan trọng:

- **Volatility:** `IMMUTABLE`, `STABLE`, `VOLATILE`.
- **Xử lý tham số NULL:** `STRICT` (đồng nghĩa `RETURNS NULL ON NULL INPUT`) hoặc `CALLED ON NULL INPUT`.
- **Parallel safety:** `PARALLEL SAFE`, `PARALLEL RESTRICTED`, `PARALLEL UNSAFE`.

Ví dụ một hàm toán học:

```sql
CREATE FUNCTION public.calculate_gross(
    net_amount numeric,
    tax_rate numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT net_amount * (1 + tax_rate)
$$;
```

Ba khai báo có **ba ý nghĩa khác nhau**:

1. `IMMUTABLE`: cùng hai giá trị đầu vào thì kết quả không thay đổi do thời gian, trạng thái database hoặc session settings.
2. `STRICT`: nếu **bất kỳ tham số nào là NULL**, PostgreSQL trả NULL mà không cần thực thi thân hàm.
3. `PARALLEL SAFE`: hàm được khai báo an toàn để thực hiện bên trong parallel worker, miễn các thao tác và hàm con bên trong thật sự đáp ứng điều đó.

**Khai báo thuộc tính không biến một hàm sai thành đúng.** PostgreSQL chủ yếu **tin vào lời khai báo của tác giả** để tối ưu. Gắn sai nhãn `IMMUTABLE` cho hàm đọc cấu hình thay đổi được, hoặc `PARALLEL SAFE` cho hàm truy cập sequence, có thể tạo kế hoạch không đúng, lỗi thực thi hoặc kết quả khó dự đoán.

Bài học đi từ quy tắc lựa chọn tới ví dụ SQL/PLpgSQL, planner, snapshot, chỉ mục biểu thức, prepared statements, catalog `pg_proc`, thực hành `EXPLAIN`, ứng dụng Java và các bài tập.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt chính xác tính bất biến, ổn định theo câu lệnh và biến động của một hàm.
2. Giải thích tác động của volatility tới constant folding, index conditions, prepared execution plans và MVCC snapshot.
3. Phân loại hàm toán học, hàm đọc bảng cấu hình, hàm đọc thời gian và hàm gọi sequence.
4. Dùng `STRICT` đúng lúc và hiểu vì sao nó không đồng nghĩa với `NOT NULL` cho giá trị trả về.
5. Viết hàm chủ động xử lý `NULL` bằng `CALLED ON NULL INPUT`.
6. Phân biệt `PARALLEL SAFE`, `PARALLEL RESTRICTED` và `PARALLEL UNSAFE`.
7. Biết những hoạt động làm hàm không an toàn hoặc chỉ an toàn ở leader: ghi dữ liệu, dùng sequence, temporary table, cursor, session/backend-local state.
8. Biết ba nhóm thuộc tính là các chiều **không thể suy luận thay thế nhau**.
9. Phân tích lời gọi hàm trong `WHERE`, `SELECT`, `ORDER BY` và biểu thức index.
10. Quan sát catalog `pg_proc.provolatile`, `proisstrict`, `proparallel` và định nghĩa hàm.
11. Dùng `ALTER FUNCTION` để sửa metadata sau khi đánh giá chính xác hành vi.
12. Phân biệt metadata ảnh hưởng optimizer với quyền truy cập, `SECURITY DEFINER` và các ràng buộc nghiệp vụ.
13. Thiết kế kiểm thử cho kết quả, NULL, thay đổi session/database state và parallel query.
14. Nhận biết trường hợp `CREATE PROCEDURE` không có cùng bộ tùy chọn với `CREATE FUNCTION`.

## 2. Bức tranh tổng thể: ba câu hỏi độc lập

| Thuộc tính | Câu hỏi cần trả lời | Các lựa chọn |
| --- | --- | --- |
| **Volatility** | Kết quả/hành vi có thể thay đổi như thế nào khi cùng tham số? | `IMMUTABLE`, `STABLE`, `VOLATILE` |
| **Null-input behavior** | PostgreSQL có được bỏ qua việc thực thi khi tham số NULL? | `STRICT` hoặc `CALLED ON NULL INPUT` |
| **Parallel safety** | Hàm được phép chạy ở đâu trong parallel plan? | `SAFE`, `RESTRICTED`, `UNSAFE` |

Các tổ hợp có thể rất khác:

```text
Hàm nhân hai số:
    IMMUTABLE + STRICT + PARALLEL SAFE

Hàm đọc giá hiện tại từ bảng:
    STABLE + STRICT + PARALLEL SAFE (nếu chỉ đọc bảng thường
    và tất cả các thao tác liên quan thật sự parallel-safe)

Hàm cấp số thứ tự bằng nextval():
    VOLATILE + PARALLEL UNSAFE
    (STRICT không liên quan nếu hàm không có tham số)

Hàm đọc state cục bộ của backend:
    Có thể STABLE nhưng PARALLEL RESTRICTED

Hàm quy đổi NULL thành số 0:
    IMMUTABLE + CALLED ON NULL INPUT + PARALLEL SAFE
```

Điểm cần ghi nhớ: **Volatility không tự động quyết định tính STRICT hoặc parallel safety**. Một hàm có thể ổn định về kết quả trong một câu SQL nhưng vẫn phụ thuộc trạng thái chỉ có ở leader.

## 3. Vai trò của thuộc tính trong CREATE FUNCTION

Cú pháp đơn giản:

```sql
CREATE FUNCTION function_name(arg1 integer, arg2 integer)
RETURNS integer
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT arg1 + arg2
$$;
```

Trong PostgreSQL, những nhóm khai báo liên quan gồm:

```sql
-- Chọn một nhóm volatility:
IMMUTABLE
STABLE
VOLATILE

-- Chọn một nhóm null-input behavior:
STRICT
RETURNS NULL ON NULL INPUT
CALLED ON NULL INPUT

-- Chọn một nhóm parallel safety:
PARALLEL SAFE
PARALLEL RESTRICTED
PARALLEL UNSAFE
```

### 3.1. Giá trị mặc định khi không khai báo

Với một hàm mới nếu không ghi các thuộc tính trên:

| Nhóm | Mặc định |
| --- | --- |
| Volatility | `VOLATILE` |
| Xử lý NULL | `CALLED ON NULL INPUT` |
| Parallel safety | `PARALLEL UNSAFE` |

Đây là những mặc định **thận trọng**: PostgreSQL không tự suy ra chỉ từ mã SQL rằng function luôn bất biến, bỏ qua NULL hoặc an toàn với parallel workers.

### 3.2. Ví dụ hàm dùng mặc định

```sql
CREATE FUNCTION public.add_numbers_default(a integer, b integer)
RETURNS integer
LANGUAGE sql
AS $$
    SELECT a + b
$$;
```

Về phép tính, hàm này có thể đủ điều kiện `IMMUTABLE STRICT PARALLEL SAFE`, nhưng vì không khai báo nên catalog ghi những giá trị mặc định: **VOLATILE**, **not strict**, **UNSAFE**.

Điều đó có thể hạn chế một số tối ưu của planner. **Đừng đổi nhãn chỉ vì thân hàm trông ngắn**: cần hiểu hàm con, kiểu dữ liệu, collation, cấu hình và tác động phụ thực tế.

### 3.3. CREATE FUNCTION khác CREATE PROCEDURE

Chương này tên “Hàm và thủ tục”, nhưng các thuộc tính `IMMUTABLE/STABLE/VOLATILE`, `STRICT` và `PARALLEL ...` là các khai báo trong **CREATE FUNCTION**. Cú pháp **CREATE PROCEDURE** có mục đích và các tùy chọn khác, không cung cấp bộ khai báo này theo cùng cách.

Thủ tục thường được gọi bằng `CALL`; hàm có thể tham gia biểu thức truy vấn `SELECT`, `WHERE`, `JOIN` và index expressions, nên planner đặc biệt quan tâm tới metadata của hàm.

## 4. Môi trường thực hành

Tạo schema riêng trên database học tập. Các ví dụ sau không cần kết nối internet hay extension đặc biệt.

### 4.1. Tạo schema

```sql
CREATE SCHEMA IF NOT EXISTS function_attrs_lab;
```

### 4.2. Bảng giá sản phẩm

```sql
CREATE TABLE function_attrs_lab.product_prices (
    product_id bigint PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    unit_price numeric(12,2) NOT NULL CHECK (unit_price >= 0),
    updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO function_attrs_lab.product_prices
    (product_id, sku, unit_price)
VALUES
    (10, 'BOOK-POSTGRES', 125.00),
    (20, 'BOOK-JAVA', 180.00),
    (30, 'ACCESS-ONLINE', 90.00);
```

### 4.3. Bảng đơn vị bán hàng

```sql
CREATE TABLE function_attrs_lab.sales (
    sale_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id bigint NOT NULL
        REFERENCES function_attrs_lab.product_prices(product_id),
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(12,2) NOT NULL CHECK (unit_price >= 0),
    sold_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO function_attrs_lab.sales
    (product_id, quantity, unit_price, sold_at)
VALUES
    (10, 2, 125.00, '2026-11-01 09:00:00+00'),
    (20, 1, 180.00, '2026-11-01 10:00:00+00'),
    (10, 3, 125.00, '2026-11-02 09:00:00+00'),
    (30, 4, 90.00,  '2026-11-03 09:00:00+00');

ANALYZE function_attrs_lab.product_prices;
ANALYZE function_attrs_lab.sales;
```

Trong các phần sau, ta tạo một số hàm độc lập để tránh chỉnh sửa dữ liệu mẫu không cần thiết. Những bài thử gây lỗi hoặc thay đổi dữ liệu sẽ có hướng dẫn transaction/ROLLBACK.

## 5. VOLATILITY là lời hứa với optimizer

Volatility classification trả lời câu hỏi: **cùng một bộ tham số đầu vào, PostgreSQL được phép giả định điều gì về kết quả và các tác động của lời gọi hàm?**

Ba mức:

```text
IMMUTABLE
    Cùng arguments -> cùng kết quả về lâu dài.
    Không phụ thuộc thời gian/session/database state thay đổi.

STABLE
    Cùng arguments -> cùng kết quả trong một SQL statement.
    Có thể khác ở statement tiếp theo.

VOLATILE
    Cùng arguments -> vẫn có thể trả kết quả khác ở mỗi lời gọi.
    Có thể có side effects; không được dùng các giả định tối ưu
    dành riêng cho STABLE/IMMUTABLE.
```

### 5.1. Không phải phép chứng minh tự động

PostgreSQL **không thể kiểm chứng hoàn toàn** xem hàm PL/pgSQL/SQL/C có thực sự luôn giữ lời hứa volatility hay không. Nếu khai báo sai:

- Planner có thể đánh giá trước hàm quá sớm.
- Prepared plan có thể giữ kết quả cũ.
- Index expression có thể lưu giá trị không còn phản ánh quy tắc thực.
- Một hàm đọc dữ liệu động có thể trả kết quả không như mong muốn.

Vì vậy chọn mức **chính xác và đủ thận trọng**, không chọn mức “tối ưu mạnh nhất” bằng mọi giá.

### 5.2. Mức độ biến động là thuộc tính của toàn bộ lời gọi

Nếu một hàm gọi hàm khác, đọc biến cấu hình hoặc bảng, tác động của **mọi dependency** đều quan trọng. Một phép nhân có vẻ thuần túy có thể không immutable nếu một hệ số được lấy từ bảng hoặc session setting.

## 6. IMMUTABLE: cùng tham số, cùng kết quả

Hàm immutable là hàm được khẳng định **không phụ thuộc dữ liệu/state thay đổi** và cùng input luôn trả cùng output theo ngữ nghĩa đã định.

Ví dụ:

```sql
CREATE FUNCTION function_attrs_lab.net_to_gross(
    net_amount numeric,
    tax_rate numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT net_amount * (1 + tax_rate)
$$;
```

Thử:

```sql
SELECT
    function_attrs_lab.net_to_gross(100, 0.08) AS gross1,
    function_attrs_lab.net_to_gross(100, 0.08) AS gross2;
```

Với cùng input 100 và 0.08, kết quả không phụ thuộc ngày hôm nay, role, nội dung bảng `product_prices` hay phiên làm việc.

### 6.1. Trường hợp thường phù hợp

- Phép toán số học cố định trên arguments.
- Chuẩn hóa chuỗi với các phép biến đổi mà ngữ nghĩa/collation phù hợp và đã được kiểm chứng là bất biến trong môi trường sử dụng.
- Hàm chuyển đổi format có đầu vào/định nghĩa rõ, không đọc cấu hình có thể thay đổi.
- Hàm tính checksum/deterministic transformation trên input khi implementation thật sự không phụ thuộc state ngoài.

### 6.2. Trường hợp không nên gắn IMMUTABLE

- Lấy giá mới nhất từ bảng.
- Đọc thời gian hiện tại.
- Đọc `current_setting(...)` mà GUC có thể khác giữa sessions/statements.
- Tạo random number.
- Lấy giá trị từ sequence.
- Phụ thuộc trạng thái file, server setting, timezone hoặc dữ liệu ngoài hàm mà không được truyền thành argument.

### 6.3. IMMUTABLE không có nghĩa function trả về NOT NULL

`IMMUTABLE` chỉ nói về mức biến động, **không nói giá trị trả ra có thể NULL hay không**. Hàm immutable hoàn toàn có thể trả NULL cho một input cụ thể.

## 7. STABLE: cùng tham số ổn định trong một statement

Hàm STABLE có thể phụ thuộc trạng thái có thể thay đổi **giữa các câu SQL** nhưng được cam kết không đổi cho các lời gọi cùng arguments **trong một statement**.

Ví dụ hàm đọc đơn giá đã lưu trong bảng:

```sql
CREATE FUNCTION function_attrs_lab.lookup_price(
    p_product_id bigint
)
RETURNS numeric
LANGUAGE sql
STABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT unit_price
    FROM function_attrs_lab.product_prices
    WHERE product_id = p_product_id
$$;
```

Thử:

```sql
SELECT
    function_attrs_lab.lookup_price(10) AS price_book_postgres,
    function_attrs_lab.lookup_price(20) AS price_book_java;
```

Ở dữ liệu mẫu, kết quả là 125.00 và 180.00.

### 7.1. Vì sao không phải IMMUTABLE?

Vì `unit_price` có thể được UPDATE:

```sql
BEGIN;

UPDATE function_attrs_lab.product_prices
SET unit_price = 135.00,
    updated_at = now()
WHERE product_id = 10;

SELECT function_attrs_lab.lookup_price(10);

ROLLBACK;
```

Hàm đọc từ bảng nên không thể hứa rằng giá sản phẩm 10 **mãi mãi là 125.00**.

### 7.2. Vì sao có thể STABLE?

Trong cơ chế snapshot phù hợp của PostgreSQL, hàm STABLE/IMMUTABLE dùng snapshot đã được thiết lập tại **đầu câu query gọi chúng**, nên một lookup nhất quán theo snapshot statement. Nó không được tự thay đổi dữ liệu.

Một statement chạy lâu không nên kỳ vọng một lời gọi STABLE đọc ra những commit mới vừa xảy ra sau khi statement đã bắt đầu.

### 7.3. STABLE không phải “trả giống nhau suốt transaction” trong mọi trường hợp

Định nghĩa cam kết của STABLE là **trong một statement**. Với isolation `READ COMMITTED`, các statement khác nhau trong cùng transaction có thể thấy snapshots khác nhau. Một STABLE function đọc bảng có thể trả giá trị mới hơn ở statement sau nếu có commit phù hợp.

Với `REPEATABLE READ`, transaction-level snapshot lại có semantics riêng. Đừng đồng nhất đặc tính STABLE của function với isolation level của transaction.

### 7.4. Đọc bảng trong hàm có thể tạo N+1 ở server

Hàm `lookup_price(product_id)` gọi từ mỗi row có thể tạo repeated table lookups:

```sql
SELECT
    s.sale_id,
    function_attrs_lab.lookup_price(s.product_id) AS current_price
FROM function_attrs_lab.sales AS s;
```

Ở một số query, JOIN trực tiếp bảng giá có thể đơn giản và hiệu quả hơn:

```sql
SELECT
    s.sale_id,
    p.unit_price AS current_price
FROM function_attrs_lab.sales AS s
JOIN function_attrs_lab.product_prices AS p
  ON p.product_id = s.product_id;
```

Đánh dấu STABLE không tự đảm bảo function chỉ được gọi một lần cho mọi row và không tự chữa mọi repeated work.

## 8. VOLATILE: mỗi lời gọi có thể khác, và có thể có side effects

VOLATILE là phân loại thận trọng nhất. PostgreSQL không được giả định cùng arguments tạo cùng kết quả.

Ví dụ:

```sql
SELECT
    random() AS random_1,
    random() AS random_2,
    clock_timestamp() AS time_1,
    clock_timestamp() AS time_2;
```

`random()` và `clock_timestamp()` là ví dụ về kết quả có thể thay đổi giữa các lời gọi.

### 8.1. Tạo hàm gọi random

```sql
CREATE FUNCTION function_attrs_lab.random_discount(
    max_discount numeric
)
RETURNS numeric
LANGUAGE sql
VOLATILE
PARALLEL UNSAFE
AS $$
    SELECT random() * max_discount
$$;
```

Trong bài lab, ta chủ động dùng `PARALLEL UNSAFE` bảo thủ để không cần đánh giá mọi dependency ở hàm này. Điều đó **không có nghĩa mọi hàm dùng random đều bắt buộc là UNSAFE**; parallel safety của mỗi lời gọi cần được kiểm tra riêng, bao gồm catalog của các hàm con.

### 8.2. Một phép UPDATE không cho phép gắn STABLE

Hàm PL/pgSQL có thể sửa bảng:

```sql
CREATE FUNCTION function_attrs_lab.set_product_price(
    p_product_id bigint,
    p_new_price numeric
)
RETURNS void
LANGUAGE plpgsql
VOLATILE
PARALLEL UNSAFE
AS $$
BEGIN
    UPDATE function_attrs_lab.product_prices
    SET unit_price = p_new_price,
        updated_at = now()
    WHERE product_id = p_product_id;
END;
$$;
```

Hàm này có side effect làm thay đổi dữ liệu, nên phải `VOLATILE` và `PARALLEL UNSAFE`.

Thử trong transaction:

```sql
BEGIN;

SELECT function_attrs_lab.set_product_price(20, 190.00);

SELECT product_id, unit_price
FROM function_attrs_lab.product_prices
WHERE product_id = 20;

ROLLBACK;
```

### 8.3. VOLATILE không có nghĩa “phải cho kết quả khác mỗi lần”

Một function VOLATILE vẫn có thể tình cờ trả giá trị giống nhau cho nhiều lần gọi. Từ khóa này chỉ nói PostgreSQL **không được dựa vào sự ổn định** như ở STABLE/IMMUTABLE.

Ví dụ hàm `add_numbers_default(2,3)` luôn trả 5 nhưng metadata mặc định là VOLATILE. Kết quả vẫn có thể trùng, chỉ là planner bị ràng buộc bởi khai báo bảo thủ.

## 9. Ba mốc thời gian: transaction, statement và wall clock

PostgreSQL có nhiều hàm thời gian, dễ bị nhầm:

```sql
SELECT
    now() AS transaction_time,
    transaction_timestamp() AS transaction_timestamp_value,
    statement_timestamp() AS statement_time,
    clock_timestamp() AS wall_clock_time;
```

Ý nghĩa:

| Hàm | Mốc thời gian | Đặc tính điển hình |
| --- | --- | --- |
| `now()` | Thời điểm bắt đầu transaction | STABLE |
| `transaction_timestamp()` | Tương đương ý nghĩa transaction start | STABLE |
| `statement_timestamp()` | Bắt đầu statement hiện tại | STABLE |
| `clock_timestamp()` | Thời gian thực tại thời điểm gọi | VOLATILE |

### 9.1. Vì sao now() không phải immutable?

Chạy câu SQL hôm nay và tuần sau có thể có transaction start time khác nhau. Vì vậy mặc dù `now()` giữ cùng giá trị trong transaction, nó **không thể là IMMUTABLE**.

### 9.2. Khác biệt trong transaction dài

```sql
BEGIN;

SELECT now(), statement_timestamp(), clock_timestamp();
SELECT pg_sleep(0.05);
SELECT now(), statement_timestamp(), clock_timestamp();

ROLLBACK;
```

Trong cùng transaction:

- `now()` giữ thời điểm bắt đầu transaction.
- `statement_timestamp()` phản ánh thời điểm bắt đầu mỗi statement.
- `clock_timestamp()` trả đồng hồ thực tại thời điểm được gọi.

Với hai statement rất gần nhau, khác biệt có thể nhỏ. `pg_sleep` chỉ giúp nhìn rõ bằng thí nghiệm, không nên đưa delay giả vào request production.

### 9.3. “STABLE” ở thời gian không đồng nhất với snapshot dữ liệu

`now()` là một thời điểm transaction; tính STABLE của một hàm đọc bảng lại gắn với snapshot và khả năng đọc dữ liệu. Không suy luận rằng mọi STABLE function chắc chắn giống nhau qua mọi statement của một transaction.

## 10. MVCC snapshot khi function thực thi SQL

PostgreSQL dùng MVCC để kiểm soát những phiên bản row mà một câu SQL có thể nhìn thấy.

Một khác biệt quan trọng:

- Với hàm **STABLE** hoặc **IMMUTABLE** thực thi câu SELECT bên trong, PostgreSQL thường dùng snapshot tại **bắt đầu câu truy vấn gọi hàm**.
- Với hàm **VOLATILE** thực thi SQL bên trong, các truy vấn nội bộ có thể lấy snapshot mới ở đầu mỗi truy vấn nội bộ, phù hợp các thay đổi của database trong quá trình thực thi.

### 10.1. Ý nghĩa thực tế

Nếu một VOLATILE function chạy nhiều SELECT nội bộ hoặc ghi dữ liệu, nó có thể quan sát những thay đổi mà STABLE function cùng ngữ cảnh không được hứa sẽ thấy.

### 10.2. Đây không phải cơ chế khóa hay isolation mới

Khai báo `STABLE` không:

- Tạo một transaction mới.
- Khóa mọi bảng mà function đọc.
- Thay `READ COMMITTED` thành `REPEATABLE READ`.
- Bảo đảm kết quả không thay đổi giữa các HTTP requests.

Nó là một phần **hợp đồng với planner và cơ chế snapshot của function**, không phải thiết lập isolation của connection.

### 10.3. Không ghi SQL trong STABLE/IMMUTABLE function

Nếu cố thực hiện `UPDATE`/`INSERT` trong hàm được khai báo STABLE hoặc IMMUTABLE, PostgreSQL có thể từ chối các câu lệnh không được phép trong hàm non-volatile. Nếu function cần tác động cơ sở dữ liệu, phân loại đúng là VOLATILE.

Đừng thử “lách” bằng cách gắn nhãn STABLE để planner tối ưu trong khi thân hàm vẫn ghi dữ liệu.

## 11. Constant folding: vì sao IMMUTABLE có thể được tính khi lập kế hoạch?

Giả sử:

```sql
SELECT function_attrs_lab.net_to_gross(100, 0.08);
```

Hàm IMMUTABLE với **các argument là constant** có thể được planner tính trước trong quá trình lập kế hoạch (*constant folding*). Trong một số execution plan, lời gọi hàm được thay bằng một constant result.

### 11.1. Lợi ích

- Bỏ bớt chi phí gọi hàm lúc thực thi.
- Suy ra điều kiện constant cho index/filter.
- Cho phép tối ưu hóa biểu thức phức tạp hơn trong query.

### 11.2. Vì sao đây là con dao hai lưỡi?

Nếu tác giả gắn nhãn IMMUTABLE cho hàm **thực sự phụ thuộc trạng thái có thể thay đổi**, planner có thể đánh giá trước rồi **giữ kết quả cũ trong cached execution plan**.

Đây là lỗi dễ gặp khi sử dụng prepared statements, driver có server-side prepare hoặc PL/pgSQL cached plans.

### 11.3. Đừng kỳ vọng function body được thực thi đúng một lần

Optimizer có thể inline, fold, đánh giá lại hoặc bỏ qua function tùy biểu thức và kế hoạch. Metadata volatility là một lời hứa cho phép/giới hạn tối ưu, **không phải bộ đếm số lần gọi hàm**.

Nếu logic nghiệp vụ đòi side effect thực hiện chính xác một lần, không nên gắn side effect vào biểu thức SQL rồi dựa vào thứ tự/đếm evaluation của SELECT.

## 12. Sai lầm nghiêm trọng: đánh dấu IMMUTABLE cho session setting

Giả sử hệ thống dùng một custom GUC lưu hệ số hiển thị:

```sql
SET function_attrs_lab.demo_factor = '1.10';
```

Một hàm **sai**:

```sql
-- CỐ Ý SAI: ví dụ minh họa anti-pattern, KHÔNG dùng production.
CREATE FUNCTION function_attrs_lab.wrong_factor(
    x numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT x * current_setting(
        'function_attrs_lab.demo_factor'
    )::numeric
$$;
```

Vì `current_setting(...)` có thể thay đổi giữa sessions/statements, hàm trên **không thực sự IMMUTABLE**.

### 12.1. Rủi ro với prepared plan

Hình dung:

```sql
PREPARE demo_wrong AS
SELECT function_attrs_lab.wrong_factor(100);

EXECUTE demo_wrong;

SET function_attrs_lab.demo_factor = '1.20';

EXECUTE demo_wrong;

DEALLOCATE demo_wrong;
```

Nếu planner đã constant-fold lời gọi `wrong_factor(100)` trong plan được cache, lần EXECUTE sau **có thể dùng giá trị cũ** thay vì phản ánh GUC mới. Hành vi cụ thể phụ thuộc kế hoạch/inlining/caching và thời điểm chuẩn bị; **không được coi một lần chạy tình cờ đúng là bằng chứng IMMUTABLE hợp lệ**.

### 12.2. Cách khai báo đúng hơn

```sql
CREATE FUNCTION function_attrs_lab.factor_for_session(
    x numeric
)
RETURNS numeric
LANGUAGE sql
STABLE
AS $$
    SELECT x * current_setting(
        'function_attrs_lab.demo_factor'
    )::numeric
$$;
```

Gắn `STABLE` vì hệ số có thể thay đổi giữa những statement/session, nhưng hàm được kỳ vọng ổn định trong một statement theo ngữ nghĩa hỗ trợ của PostgreSQL.

Ở ví dụ này ta để **parallel safety ở mặc định UNSAFE**, tránh tuyên bố worker-safe khi chưa xem xét đầy đủ cách cài đặt, session state và hàm con.

### 12.3. Truyền config thành argument khi phù hợp

Nếu business logic cần kết quả thuần và có thể cache/index, giải pháp tốt là:

```sql
SELECT function_attrs_lab.net_to_gross(100, 0.20);
```

Khi hệ số là argument tường minh, function tính toán có thể thật sự immutable. Cách này làm dependency rõ hơn và tránh “tham số bí mật” từ session.

## 13. Sai lầm: lookup bảng nhưng khai báo IMMUTABLE

Ví dụ:

```sql
-- KHÔNG tạo phiên bản này trên production:
-- CREATE FUNCTION product_price_immutable(p_id bigint)
-- RETURNS numeric
-- LANGUAGE sql
-- IMMUTABLE
-- AS $$
--     SELECT unit_price
--     FROM function_attrs_lab.product_prices
--     WHERE product_id = p_id
-- $$;
```

Nội dung `product_prices` có thể được cập nhật, nên kết quả **không bất biến mãi mãi**. Khai báo STABLE phù hợp hơn cho một lookup đọc giá theo snapshot statement.

### 13.1. Tác hại không chỉ ở prepared statements

Nếu dùng hàm sai metadata trong biểu thức index hoặc generated column, giá trị tính ra có thể gắn với trạng thái bảng tại thời điểm ghi/index build và không tự cập nhật khi bảng tham chiếu thay đổi.

**Function declaration phải đúng trước khi được dùng làm cơ sở cho persisted derived data.**

### 13.2. Ngoại lệ “bảng tham chiếu không bao giờ đổi” cần rất thận trọng

Một bảng được cho là “configuration cố định” vẫn có thể thay khi migration, sửa lỗi hoặc restore. Nếu hàm phụ thuộc dữ liệu ở bảng, thường không nên gọi là IMMUTABLE chỉ vì vận hành hiện tại ít cập nhật.

## 14. Volatility ảnh hưởng điều kiện dùng index

Giả sử:

```sql
CREATE INDEX idx_lab_sales_sold_at
ON function_attrs_lab.sales (sold_at);
```

Điều kiện:

```sql
SELECT sale_id, sold_at
FROM function_attrs_lab.sales
WHERE sold_at < now();
```

`now()` là STABLE. PostgreSQL có thể dùng nó như giá trị so sánh ổn định trong một scan và xem xét kế hoạch index phù hợp.

Ngược lại:

```sql
SELECT sale_id, sold_at
FROM function_attrs_lab.sales
WHERE sold_at < clock_timestamp();
```

`clock_timestamp()` là VOLATILE; PostgreSQL không thể giả định một giá trị timestamp cố định cho toàn scan như cách với hàm STABLE. Truy vấn có thể cần đánh giá điều kiện từng hàng và không tạo cùng index boundary tối ưu như mong muốn.

### 14.1. Không có nghĩa VOLATILE cấm mọi index

Một WHERE có điều kiện khác vẫn có thể dùng index. Ví dụ:

```sql
SELECT sale_id, sold_at
FROM function_attrs_lab.sales
WHERE product_id = 10
  AND sold_at < clock_timestamp();
```

PostgreSQL vẫn có thể dùng index trên `product_id` nếu có và có lợi, dù điều kiện `clock_timestamp()` có thể phải áp dụng như filter.

### 14.2. Đọc EXPLAIN, đừng suy đoán kiểu scan

Trên bảng chỉ bốn rows, Seq Scan thường rẻ. Khi mở rộng lab, dùng `EXPLAIN` và `EXPLAIN (ANALYZE, BUFFERS)` để xem `Index Cond`, `Filter`, rows và buffers của query thật.

## 15. IMMUTABLE là yêu cầu thường gặp của expression index

Ví dụ chuẩn hóa mã SKU:

```sql
CREATE FUNCTION function_attrs_lab.normalize_sku(
    raw_sku text
)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT lower(btrim(raw_sku))
$$;
```

Sau đó:

```sql
CREATE INDEX idx_lab_products_normalized_sku
ON function_attrs_lab.product_prices (
    function_attrs_lab.normalize_sku(sku)
);
```

Truy vấn:

```sql
SELECT product_id, sku, unit_price
FROM function_attrs_lab.product_prices
WHERE function_attrs_lab.normalize_sku(sku)
    = function_attrs_lab.normalize_sku('  book-postgres  ');
```

### 15.1. Vì sao index cần IMMUTABLE?

Một expression index lưu **kết quả biểu thức khi xây dựng/duy trì index**. Nếu cùng `sku` nhưng function trả kết quả khác vào ngày mai, index có thể không còn phản ánh giá trị phải tìm.

Do đó, PostgreSQL yêu cầu các hàm trong index expression (và các thành phần predicate của partial index) phù hợp với tính **IMMUTABLE**.

### 15.2. Lưu ý collation và thay đổi thư viện

`lower(text)` có thể phụ thuộc quy tắc case của collation/locale. Nếu môi trường nâng cấp collation provider hoặc quy tắc Unicode đổi, kết quả normalization có thể thay so với index đã xây trước đó. Dù function được khai báo immutable theo hợp đồng hệ thống, vận hành vẫn cần đánh giá khả năng **REINDEX** sau thay đổi collation rules.

Không suy luận rằng chữ “IMMUTABLE” khiến kết quả bất biến qua **mọi nâng cấp hệ điều hành, thư viện, collation, extension hoặc phiên bản PostgreSQL**.

### 15.3. Nếu function chỉ STABLE thì sao?

Một function STABLE phụ thuộc bảng giá/config không thích hợp làm expression index lưu giá trị lâu dài. PostgreSQL thông thường sẽ không chấp nhận dùng hàm không immutable trong index definition.

## 16. IMMUTABLE và partial index

Một partial index chỉ lưu rows thỏa predicate:

```sql
CREATE INDEX idx_lab_products_price_positive
ON function_attrs_lab.product_prices (product_id)
WHERE unit_price > 0;
```

Predicate `unit_price > 0` có ngữ nghĩa cố định theo giá trị hàng; index có thể được duy trì khi unit_price thay đổi.

Nhưng không nên dùng:

```sql
-- KHÔNG HỢP LỆ cho index predicate:
-- CREATE INDEX idx_recent_sales
-- ON function_attrs_lab.sales (sale_id)
-- WHERE sold_at >= now() - INTERVAL '7 days';
```

Vì `now()` là STABLE, không phải IMMUTABLE. Một row “trong bảy ngày gần nhất” sẽ tự trôi ra khỏi điều kiện theo thời gian **mà không có UPDATE row**, nên index không thể tự duy trì đúng chỉ bằng thay đổi row.

### 16.1. Giải pháp

Nếu cần index dữ liệu gần đây, cân nhắc:

- Predicate cố định theo một cutoff không tự trôi và được quản lý/migration có kiểm soát.
- Partition theo thời gian kết hợp pruning.
- B-tree trên `sold_at` và WHERE với `now() - interval ...` ở query.
- Data lifecycle flags được cập nhật có kiểm soát nếu business thật sự cần.

Không “sửa” bằng cách khai báo sai hàm thời gian là IMMUTABLE.

## 17. IMMUTABLE và generated columns

PostgreSQL generated columns sử dụng các biểu thức có hạn chế, trong đó thường yêu cầu **immutable expressions**.

Ví dụ:

```sql
CREATE TABLE function_attrs_lab.sku_inputs (
    sku_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    raw_sku text NOT NULL,
    normalized_sku text GENERATED ALWAYS AS (
        function_attrs_lab.normalize_sku(raw_sku)
    ) STORED
);

INSERT INTO function_attrs_lab.sku_inputs (raw_sku)
VALUES (' Book-Postgres '), ('BOOK-JAVA');

SELECT sku_id, raw_sku, normalized_sku
FROM function_attrs_lab.sku_inputs
ORDER BY sku_id;
```

### 17.1. Tại sao không cho generated column đọc giá hiện tại?

Nếu `generated_price` phụ thuộc bảng `product_prices`, thay đổi giá ở một bảng khác sẽ không tự làm một row generated tương ứng được cập nhật đúng chỉ vì dữ liệu bảng kia thay đổi.

Generated expressions nên được tạo từ **giá trị trong hàng** và những phép toán bất biến phù hợp, theo giới hạn PostgreSQL.

### 17.2. Không nhầm generated column với VIEW

Regular view tính biểu thức trong quá trình query; generated stored column lưu giá trị theo cơ chế ghi. Yêu cầu immutability và chi phí bảo trì khác nhau.

## 18. CHECK constraint và sự bất biến

Một constraint:

```sql
CREATE TABLE function_attrs_lab.tax_rules (
    rule_id integer PRIMARY KEY,
    rate numeric NOT NULL
        CHECK (rate BETWEEN 0 AND 1)
);
```

thuần theo dữ liệu row và phép so sánh ổn định, thích hợp làm bất biến.

Nếu cố đưa hàm phụ thuộc thời gian hoặc bảng khác vào CHECK, có thể xảy ra:

- Một row hợp lệ hôm nay nhưng “trở thành không hợp lệ” ngày mai mà không được UPDATE.
- Backup/restore gặp vấn đề vì thứ tự nạp dữ liệu hoặc trạng thái thay đổi.
- Constraint không được tái kiểm tra liên tục mỗi khi bảng khác thay đổi.

PostgreSQL thiết kế CHECK dựa trên giả định biểu thức điều kiện **bất biến với cùng giá trị row**. Nó không kiểm tra toàn bộ các dependency động thay tác giả.

### 18.1. Khi cần ràng buộc liên bảng

Cân nhắc foreign key, UNIQUE, exclusion constraints, transaction logic, trigger có khóa phù hợp hoặc mô hình dữ liệu khác, thay vì giả mạo một function tra bảng là immutable trong CHECK.

## 19. Prepared statements: hiệu năng và rủi ro stale plan

Ứng dụng Java/PostgreSQL thường tái sử dụng query đã chuẩn bị:

```sql
PREPARE sale_gross(numeric, numeric) AS
SELECT function_attrs_lab.net_to_gross($1, $2);

EXECUTE sale_gross(100, 0.08);
EXECUTE sale_gross(200, 0.10);

DEALLOCATE sale_gross;
```

Với hàm thật sự immutable, planner có thể an toàn sử dụng các tối ưu phù hợp.

### 19.1. Generic plan vs custom plan

PostgreSQL có thể lựa chọn kế hoạch generic hoặc custom cho prepared statements tùy tình huống:

- **Custom plan** được tối ưu với giá trị tham số đã biết.
- **Generic plan** được tái sử dụng cho nhiều lần thực thi với tham số khác nhau.

Nếu một function bị đánh dấu IMMUTABLE sai và được constant-fold trong cached plan với một số argument constant, dữ liệu session/table có thể thay đổi nhưng plan cũ không được tái tính đúng.

### 19.2. Không phải mọi expression được fold ở PREPARE

Có những kế hoạch PostgreSQL lập lại hoặc hoãn tối ưu theo giá trị tham số. **Không hứa** function sẽ được gọi ở một thời điểm chính xác chỉ vì có PREPARE.

Điều cần khẳng định là **misclassification cho phép những tối ưu không hợp lệ**, còn loại plan/số lần gọi thật phải xem trong hệ thống thực.

## 20. STRICT: bỏ qua thân hàm nếu bất kỳ đối số là NULL

Trong PostgreSQL:

```sql
STRICT
```

và:

```sql
RETURNS NULL ON NULL INPUT
```

là hai cách khai báo cùng ý nghĩa đối với SQL function: nếu **bất kỳ argument đầu vào là NULL**, PostgreSQL có thể trả **NULL ngay** mà **không gọi thân hàm**.

Ví dụ:

```sql
CREATE FUNCTION function_attrs_lab.double_strict(
    x numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT x * 2
$$;
```

Thử:

```sql
SELECT
    function_attrs_lab.double_strict(5) AS five_doubled,
    function_attrs_lab.double_strict(NULL::numeric) AS null_doubled;
```

Kết quả:

```text
five_doubled = 10
null_doubled = NULL
```

### 20.1. Nhiều tham số: chỉ cần một NULL

Hàm `net_to_gross(net_amount, tax_rate)` đã khai báo STRICT:

```sql
SELECT
    function_attrs_lab.net_to_gross(100, 0.08) AS normal,
    function_attrs_lab.net_to_gross(NULL::numeric, 0.08) AS missing_amount,
    function_attrs_lab.net_to_gross(100, NULL::numeric) AS missing_rate,
    function_attrs_lab.net_to_gross(NULL::numeric, NULL::numeric)
        AS both_missing;
```

Ba biểu thức có ít nhất một NULL trả NULL mà thân hàm không cần thực thi.

### 20.2. STRICT không chỉ là cách viết ngắn của COALESCE

Một hàm có `COALESCE(x,0)` muốn trả 0 khi x là NULL **không nên STRICT**, vì nếu STRICT PostgreSQL sẽ bỏ qua thân hàm và trả NULL trước khi COALESCE có cơ hội chạy.

## 21. CALLED ON NULL INPUT: cho thân hàm tự quyết định

Đây là mặc định khi không khai báo STRICT.

Ví dụ:

```sql
CREATE FUNCTION function_attrs_lab.zero_if_null(
    x numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
CALLED ON NULL INPUT
PARALLEL SAFE
AS $$
    SELECT COALESCE(x, 0)
$$;
```

Thử:

```sql
SELECT
    function_attrs_lab.zero_if_null(NULL::numeric) AS null_to_zero,
    function_attrs_lab.zero_if_null(25) AS stays_25;
```

Kết quả: 0 và 25.

### 21.1. Tại sao không chọn STRICT?

Vì mục tiêu nghiệp vụ là **xử lý input NULL**. Nếu gắn STRICT, biểu thức `COALESCE(x,0)` ở trong function sẽ không được thực thi cho NULL.

### 21.2. Một hàm có thể tự xử lý NULL khác nhau theo từng argument

```sql
CREATE FUNCTION function_attrs_lab.line_total_with_default(
    unit_price numeric,
    quantity integer
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
CALLED ON NULL INPUT
PARALLEL SAFE
AS $$
    SELECT COALESCE(unit_price, 0)
         * COALESCE(quantity, 1)
$$;
```

Ở đây:

- `unit_price=NULL` được coi là 0.
- `quantity=NULL` được coi là 1.

Đây là **chính sách của ví dụ**, không phải default hợp lý cho mọi nghiệp vụ. Trong hóa đơn thực, một `NULL` đôi khi nên bị từ chối thay vì âm thầm chuyển thành 0 hoặc 1.

### 21.3. Có thể không ghi CALLED ON NULL INPUT

Nếu không ghi cả hai thuộc tính, PostgreSQL mặc định vẫn gọi thân hàm khi NULL. Nhưng khai báo `CALLED ON NULL INPUT` tường minh có thể giúp người đọc thấy rõ chủ đích.

## 22. STRICT không bảo đảm output luôn NOT NULL

Ví dụ:

```sql
CREATE FUNCTION function_attrs_lab.safe_ratio(
    numerator numeric,
    denominator numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT numerator / NULLIF(denominator, 0)
$$;
```

Thử:

```sql
SELECT
    function_attrs_lab.safe_ratio(10, 2) AS valid_ratio,
    function_attrs_lab.safe_ratio(10, 0) AS zero_denominator,
    function_attrs_lab.safe_ratio(10, NULL::numeric)
        AS missing_denominator;
```

- `safe_ratio(10,2)` trả 5.
- `safe_ratio(10,0)` trả NULL vì `NULLIF(0,0)` là NULL, và phép chia cho NULL trả NULL.
- `safe_ratio(10,NULL)` trả NULL mà không chạy thân hàm do STRICT.

**STRICT chỉ cam kết hành vi khi có NULL input; không cam kết với input không NULL thì output phải không NULL.**

### 22.1. NULL khác giá trị không hợp lệ

Giá trị `0` là một số không NULL. STRICT không tự phát hiện mẫu số bằng 0, hạn mức âm, mã không tồn tại hoặc JSON sai schema.

Nếu muốn bắt lỗi chia cho 0 thay vì trả NULL, function phải triển khai chính sách riêng.

### 22.2. Cần hiểu SQL NULL propagation trong expression

Một hàm không STRICT nhưng chỉ chứa `SELECT x*2` vẫn có thể trả NULL cho `x=NULL` bởi chính phép nhân SQL trả NULL. Đó là **kết quả của body**, khác với cơ chế STRICT tự bỏ qua body.

## 23. STRICT và side effects

Giả sử một function có tác động ngoài (ghi bảng/log/sequence), nếu khai báo STRICT và argument NULL, PostgreSQL không cần gọi thân hàm, nên side effect có thể **không xảy ra**.

### 23.1. Ví dụ sequence

```sql
CREATE SEQUENCE function_attrs_lab.event_sequence
START WITH 1000;

CREATE FUNCTION function_attrs_lab.reserve_event_id(
    event_type text
)
RETURNS bigint
LANGUAGE sql
VOLATILE
STRICT
PARALLEL UNSAFE
AS $$
    SELECT nextval(
        'function_attrs_lab.event_sequence'::regclass
    )
$$;
```

Thử:

```sql
SELECT function_attrs_lab.reserve_event_id('ORDER') AS new_event_id;
SELECT function_attrs_lab.reserve_event_id(NULL::text)
    AS null_event_type;
```

Với `event_type=NULL`, body không được gọi và không lấy thêm số sequence theo contract STRICT.

### 23.2. Tại sao hàm sequence là VOLATILE?

`nextval()` thay đổi trạng thái sequence và có thể trả giá trị mới mỗi lần. Nó không thể là STABLE/IMMUTABLE.

### 23.3. Tại sao PARALLEL UNSAFE?

Sequence access có side effects/trạng thái cần được xử lý ngoài parallel workers; function sử dụng `nextval()` không được gắn PARALLEL SAFE.

### 23.4. Lưu ý với ROLLBACK

Giá trị sequence đã cấp **không được hoàn tác** chỉ vì transaction rollback. Không dùng ví dụ sequence để yêu cầu ID liên tục không có khoảng trống.

### 23.5. Đừng dùng STRICT làm bảo đảm audit

Nếu một yêu cầu nghiệp vụ đòi “mọi lần gọi API đều tạo audit row”, một function STRICT có thể bỏ qua body khi input NULL. Audit phải được thiết kế ở tầng workflow/transaction thích hợp, không phụ thuộc mơ hồ vào evaluation của expression.

## 24. STRICT và hàm trả về boolean

Ví dụ:

```sql
CREATE FUNCTION function_attrs_lab.is_positive_strict(
    x numeric
)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT x > 0
$$;
```

Với input NULL, kết quả là NULL chứ không phải FALSE.

Nếu sản phẩm muốn NULL được coi là **không dương**, cần xử lý tường minh:

```sql
CREATE FUNCTION function_attrs_lab.is_positive_or_false(
    x numeric
)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
CALLED ON NULL INPUT
PARALLEL SAFE
AS $$
    SELECT COALESCE(x > 0, false)
$$;
```

### 24.1. SQL ba giá trị

Một biểu thức WHERE:

```sql
WHERE function_attrs_lab.is_positive_strict(x)
```

chỉ giữ rows mà kết quả TRUE. NULL không được coi là TRUE.

### 24.2. Trả NULL hay FALSE là quyết định nghiệp vụ

Nếu NULL nghĩa là **chưa biết**, trả NULL có thể diễn đạt tốt hơn false. Nếu NULL nghĩa là **không hợp lệ**, cần constraint/validation riêng. Đừng thay tất cả NULL bằng FALSE chỉ để không phải xử lý ba giá trị.

## 25. STRICT với nhiều kiểu và overload

PostgreSQL cho phép **function overloading** theo signature. Khi gọi:

```sql
SELECT function_attrs_lab.double_strict(NULL);
```

giá trị literal NULL không mang kiểu tường minh. Nếu trong schema có nhiều overload cùng tên hoặc khả năng ép kiểu gây mơ hồ, PostgreSQL có thể cần thêm type cast để chọn function đúng.

Nên viết khi muốn kiểm thử chính xác:

```sql
SELECT function_attrs_lab.double_strict(NULL::numeric);
```

### 25.1. STRICT là thuộc tính của từng function signature

Nếu có:

```sql
f(integer)
f(numeric)
f(text)
```

thì mỗi signature là một function khác nhau trong catalog và có thể có volatility/strict/parallel labels riêng.

### 25.2. NULL input evaluation với composite/record types

Các kiểu tổng hợp và row expressions có quy tắc NULL phức tạp hơn scalar thông thường. Với ứng dụng cần xử lý composite values và NULL fields, nên kiểm thử trực tiếp call signature, `IS NULL` và `IS NOT NULL` thay vì suy luận như một tham số scalar đơn giản.

## 26. Parallel query trong PostgreSQL là gì?

PostgreSQL có thể chọn **parallel execution plan** để một số worker processes xử lý phần công việc truy vấn, trong khi một backend đóng vai trò **leader** điều phối.

Một kế hoạch có thể chứa:

```text
Finalize Aggregate
  -> Gather
       Workers Planned: 2
       -> Partial Aggregate
            -> Parallel Seq Scan on large_table
```

Đây là một hình dạng minh họa. Không phải mọi SELECT đều có Gather hoặc workers.

### 26.1. Parallel safety phục vụ điều gì?

Planner cần biết một function có thể chạy:

- Trực tiếp trong worker.
- Chỉ trong leader của parallel group.
- Hay không được nằm trong một parallel plan.

Đó là lý do có ba mức `PARALLEL SAFE`, `PARALLEL RESTRICTED` và `PARALLEL UNSAFE`.

### 26.2. Parallel safety không đồng nghĩa “hàm tự chạy nhiều luồng”

Một function ghi `PARALLEL SAFE` **không tự tạo workers**. Nó chỉ được phép nằm trong phần plan có worker khi planner chọn parallel plan và mọi điều kiện khác phù hợp.

### 26.3. Parallel plan không luôn nhanh hơn

Chi phí tạo worker, chuyển tuples qua Gather, phối hợp, memory/CPU contention có thể vượt lợi ích trên bảng nhỏ. Việc không thấy workers ở lab nhỏ thường bình thường.

## 27. PARALLEL SAFE

Khai báo:

```sql
PARALLEL SAFE
```

nghĩa là function **được khẳng định an toàn để thực hiện trong parallel worker**.

Ví dụ hàm thuần toán học:

```sql
CREATE FUNCTION function_attrs_lab.line_amount(
    quantity integer,
    unit_price numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT quantity * unit_price
$$;
```

Truy vấn:

```sql
SELECT SUM(
    function_attrs_lab.line_amount(quantity, unit_price)
) AS gross_sales
FROM function_attrs_lab.sales;
```

Hàm này chỉ thực hiện phép nhân hai arguments, không truy cập sequence, session-specific cursor, temporary table hay ghi dữ liệu. Vì thế có thể đánh dấu SAFE.

### 27.1. Thỏa điều kiện cần nhưng không đủ để có parallel plan

Ngay cả khi `line_amount` SAFE, PostgreSQL còn phải xét:

- Kích thước dữ liệu.
- Khả năng parallel của scan/aggregate/join.
- Cấu hình máy chủ và worker availability.
- Chi phí thiết lập song song.
- Những biểu thức/hàm khác trong cùng query.

### 27.2. Dependencies phải an toàn

Một function định nghĩa bằng SQL nhưng bên trong gọi hàm C/extension không parallel-safe thì **không được tùy tiện đánh dấu SAFE** chỉ vì bản thân wrapper đơn giản.

PostgreSQL không phải lúc nào cũng tự phân tích mọi tình huống qua procedural code và dependencies để sửa nhãn sai cho bạn.

## 28. PARALLEL RESTRICTED

Khai báo:

```sql
PARALLEL RESTRICTED
```

nghĩa là function **không được thực thi bên trong parallel worker**, nhưng có thể được thực thi bởi **leader** trong một parallel query khi kế hoạch cho phép.

### 28.1. Ví dụ loại trạng thái cần leader

Những function phụ thuộc:

- Temporary tables của session.
- Cursors.
- Prepared statements hoặc backend-local state không đồng bộ tới worker.
- Trạng thái kết nối client hoặc đối tượng backend-local.

thường cần được đánh giá là **RESTRICTED** thay vì SAFE.

### 28.2. Ví dụ mã minh họa đọc backend identity

```sql
CREATE FUNCTION function_attrs_lab.backend_identity()
RETURNS integer
LANGUAGE sql
STABLE
PARALLEL RESTRICTED
AS $$
    SELECT pg_backend_pid()
$$;
```

Hàm này trả identity của backend tại nơi thực thi. Ta khai báo RESTRICTED để không cho code quan sát thông tin backend-local chạy bên trong workers theo cách làm thay đổi ý nghĩa mong muốn.

Đây là lựa chọn **bảo thủ có chủ đích** cho ví dụ; khi triển khai thật, cần xem semantics và catalog của mọi hàm con theo phiên bản PostgreSQL đang dùng.

### 28.3. RESTRICTED không bảo đảm planner vẫn dùng workers

Nếu function RESTRICTED nằm ở chỗ phải đánh giá trên từng row trước một phép lọc hoặc join không thể chuyển lên leader một cách hợp lệ/hiệu quả, PostgreSQL có thể quyết định **không parallelize** phần đó.

Không suy luận rằng RESTRICTED luôn tạo plan “Parallel Scan rồi function chạy sau Gather”; planner phải bảo toàn ngữ nghĩa và cân nhắc chi phí.

## 29. PARALLEL UNSAFE

Khai báo:

```sql
PARALLEL UNSAFE
```

nghĩa là function được đánh giá không an toàn trong parallel mode, nên **sự có mặt của function trong query có thể buộc planner chọn kế hoạch tuần tự**.

Những ví dụ phổ biến:

- Thực hiện `INSERT`, `UPDATE`, `DELETE` hoặc thay đổi trạng thái dữ liệu.
- Gọi `nextval()` và tác động tới sequence.
- Thay đổi transaction state hoặc cấu hình backend theo cách không an toàn để phân tán sang workers.
- Có side effects hay dependency không tương thích với parallel worker model.

### 29.1. Ví dụ sequence

Hàm đã tạo:

```sql
SELECT function_attrs_lab.reserve_event_id('ORDER');
```

được khai báo `VOLATILE STRICT PARALLEL UNSAFE`. Nếu một SELECT lớn gọi function này, không nên mong PostgreSQL sử dụng parallel plan để gọi sequence trong workers.

### 29.2. Ví dụ hàm ghi dữ liệu

```sql
SELECT function_attrs_lab.set_product_price(10, 130.00);
```

Hàm có UPDATE bảng nên UNSAFE. Dù PostgreSQL có thể hỗ trợ parallel scan cho những query đọc dữ liệu khác, không được sửa nhãn hàm ghi thành SAFE chỉ để nhìn thấy Gather.

### 29.3. Mặc định UNSAFE bảo thủ

Khi viết hàm mới mà chưa đánh giá đầy đủ các tác động phụ, để mặc định PARALLEL UNSAFE thường an toàn hơn việc gắn SAFE theo cảm tính. Nhưng nếu function thật sự thuần toán học và được gọi trên hàng triệu rows, khai báo đúng SAFE có thể mở ra cơ hội tối ưu đáng kể.

## 30. Volatility và parallel safety là hai chiều độc lập

Không thể suy ra:

```text
IMMUTABLE  => PARALLEL SAFE
STABLE     => PARALLEL RESTRICTED
VOLATILE   => PARALLEL UNSAFE
```

Các suy luận này **sai**.

### 30.1. IMMUTABLE nhưng chưa chắc safe

Một function có thể cho kết quả bất biến nhưng truy cập tài nguyên backend-local hoặc API không an toàn trong worker. Khi đó thuộc tính volatility và parallel safety phải được xem xét độc lập.

### 30.2. STABLE và PARALLEL SAFE

Hàm `lookup_price(product_id)` đọc bảng thường và không có side effects, nên trong ví dụ được phân loại `STABLE PARALLEL SAFE`. Nếu thay nguồn thành temporary table, phân loại parallel safety sẽ cần đổi dù volatility có thể vẫn STABLE.

### 30.3. VOLATILE không tự đồng nghĩa UNSAFE

Một hàm có thể biến động về kết quả nhưng không thao tác tài nguyên bị cấm với workers. Vì vậy mức volatility không tự quyết định parallel label.

Tuy nhiên, **hàm ghi dữ liệu hoặc thao tác sequence** vừa VOLATILE vừa UNSAFE trong các tình huống đã nêu.

### 30.4. STRICT cũng độc lập

Một hàm `VOLATILE STRICT PARALLEL UNSAFE` hoàn toàn hợp lệ. Chính ví dụ `reserve_event_id(event_type)` minh họa:

- VOLATILE vì sequence.
- STRICT vì không cần cấp ID nếu event_type NULL.
- UNSAFE vì sequence access.

## 31. Temporary tables: một trường hợp thường cần RESTRICTED

Giả sử session tạo temporary table để xử lý dữ liệu:

```sql
CREATE TEMP TABLE session_discounts (
    product_id bigint PRIMARY KEY,
    discount_rate numeric NOT NULL
) ON COMMIT PRESERVE ROWS;

INSERT INTO session_discounts
VALUES (10, 0.10), (20, 0.05);
```

Một function đọc temporary table có dependency vào **session-local state**.

Ví dụ định hướng:

```sql
CREATE FUNCTION function_attrs_lab.session_discount(
    p_product_id bigint
)
RETURNS numeric
LANGUAGE plpgsql
STABLE
STRICT
PARALLEL RESTRICTED
AS $$
DECLARE
    result numeric;
BEGIN
    SELECT d.discount_rate
    INTO result
    FROM pg_temp.session_discounts AS d
    WHERE d.product_id = p_product_id;

    RETURN result;
END;
$$;
```

### 31.1. Tại sao không PARALLEL SAFE?

Temporary table tồn tại ở phạm vi session/backend; parallel workers có giới hạn truy cập trạng thái này. Vì vậy function tham chiếu temp table không nên được đặt chạy trực tiếp trong workers.

### 31.2. Tại sao STABLE vẫn có thể hợp lý?

Function chỉ đọc discount rows, không ghi. Trong một statement, nó được kỳ vọng có snapshot consistent theo semantics STABLE. Nó vẫn có thể thấy nội dung khác giữa statements khi temp table thay đổi.

### 31.3. Cẩn trọng với vòng đời temp table

Function tham chiếu `pg_temp.session_discounts` giả định bảng temp đã được tạo trong session đang gọi. Nếu không có bảng, function có thể lỗi khi thực thi. Đây là ví dụ lab; API production cần quản lý lifecycle của temporary table và connection pool đúng cách.

### 31.4. Session pool có thể tái sử dụng connection

Đừng vô tình để temp table của request trước ảnh hưởng request sau hoặc dựa vào temp state khi client chuyển connection. Nếu cần state per request, phải có cleanup/transaction contract rõ.

## 32. Kiểm tra catalog pg_proc

Các thuộc tính được lưu trong PostgreSQL catalog `pg_proc`.

Một số cột:

| Cột catalog | Giá trị | Ý nghĩa |
| --- | --- | --- |
| `provolatile` | `i` / `s` / `v` | IMMUTABLE / STABLE / VOLATILE |
| `proisstrict` | `true` / `false` | STRICT hay CALLED ON NULL INPUT |
| `proparallel` | `s` / `r` / `u` | SAFE / RESTRICTED / UNSAFE |
| `prolang` | OID | Ngôn ngữ thực thi |
| `prosecdef` | boolean | SECURITY DEFINER hay invoker |
| `procost` | số | Ước lượng cost của lời gọi |
| `prorows` | số | Ước lượng số row với set-returning functions |
| `prokind` | ký tự | Function/procedure/aggregate/window classification |

### 32.1. Query thực hành

```sql
SELECT
    p.oid::regprocedure AS function_signature,
    CASE p.provolatile
        WHEN 'i' THEN 'IMMUTABLE'
        WHEN 's' THEN 'STABLE'
        WHEN 'v' THEN 'VOLATILE'
    END AS volatility,
    p.proisstrict AS is_strict,
    CASE p.proparallel
        WHEN 's' THEN 'SAFE'
        WHEN 'r' THEN 'RESTRICTED'
        WHEN 'u' THEN 'UNSAFE'
    END AS parallel_safety,
    p.procost AS estimated_cost
FROM pg_proc AS p
JOIN pg_namespace AS n
  ON n.oid = p.pronamespace
WHERE n.nspname = 'function_attrs_lab'
  AND p.prokind = 'f'
ORDER BY p.proname, function_signature::text;
```

Truy vấn `prokind='f'` tập trung vào **normal functions** do lab tạo, thay vì vô tình trộn procedures/aggregates.

### 32.2. Xem catalog của built-ins

```sql
SELECT
    p.oid::regprocedure AS function_signature,
    p.provolatile,
    p.proisstrict,
    p.proparallel
FROM pg_proc AS p
WHERE p.oid IN (
    'pg_catalog.now()'::regprocedure,
    'pg_catalog.clock_timestamp()'::regprocedure,
    'pg_catalog.random()'::regprocedure,
    'pg_catalog.pg_backend_pid()'::regprocedure
)
ORDER BY function_signature::text;
```

Đây là cách biết **đúng metadata trên phiên bản PostgreSQL đang chạy**, thay vì đoán parallel label của built-in theo tên gọi.

### 32.3. OID và signature quan trọng

Vì một function name có thể có nhiều overloads, khi muốn kiểm tra/sửa một function, hãy dùng:

```sql
'function_attrs_lab.double_strict(numeric)'::regprocedure
```

để xác định đúng signature.

## 33. Xem định nghĩa function

```sql
SELECT pg_get_functiondef(
    'function_attrs_lab.net_to_gross(numeric,numeric)'::regprocedure
) AS ddl;
```

`pg_get_functiondef` dựng lại câu lệnh tạo function, giúp xem:

- Arguments, return type.
- Language.
- Volatility.
- Strictness.
- Parallel safety.
- Security/cost/options liên quan.
- Function body.

### 33.1. Xem body thôi chưa đủ

Một function ngắn có thể gọi function khác, dynamic SQL hoặc extension. Để khẳng định parallel safety/volatility, phải đánh giá **đường thực thi thực tế**, không chỉ vài dòng body đầu tiên.

### 33.2. information_schema

Các view trong `information_schema` cung cấp metadata theo chuẩn SQL và có thể hữu ích để xem routines, nhưng `pg_proc` là nơi trực tiếp thể hiện ba nhóm thuộc tính PostgreSQL-specific này.

## 34. ALTER FUNCTION: sửa metadata của một function đã tồn tại

PostgreSQL có thể thay metadata bằng `ALTER FUNCTION`, không nhất thiết phải viết lại body.

Ví dụ:

```sql
ALTER FUNCTION function_attrs_lab.add_numbers_default(
    integer, integer
)
IMMUTABLE
STRICT
PARALLEL SAFE;
```

Sau khi xác nhận phép cộng không phụ thuộc state và không có side effects, ta sửa ba thuộc tính cho hàm lab.

### 34.1. Đọc lại catalog

```sql
SELECT
    p.oid::regprocedure,
    p.provolatile,
    p.proisstrict,
    p.proparallel
FROM pg_proc AS p
WHERE p.oid =
    'function_attrs_lab.add_numbers_default(integer,integer)'
        ::regprocedure;
```

Kỳ vọng metadata: `i`, `true`, `s`.

### 34.2. Đổi nhãn không thay nội dung function

ALTER FUNCTION chỉ đổi metadata; nó không biến một function đọc bảng thành hàm toán học, không loại side effects và không viết lại SQL. Trước khi thay, phải kiểm tra correctness và dependencies.

### 34.3. Điều gì cần xem khi function từng dùng trong index?

Nếu một function có expression index hoặc generated column phụ thuộc, việc thay body/semantics hoặc khai báo volatility sai có thể ảnh hưởng persisted derived values. Có thể cần REINDEX, recompute, kiểm tra dữ liệu và deployment plan tùy thay đổi.

Không chỉ ALTER nhãn rồi coi tất cả index rows đã được tái tính.

## 35. CREATE OR REPLACE FUNCTION và thay đổi thuộc tính

Trong migration, `CREATE OR REPLACE FUNCTION` thường được dùng để thay body/metadata với signature tương thích.

```sql
CREATE OR REPLACE FUNCTION function_attrs_lab.net_to_gross(
    net_amount numeric,
    tax_rate numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT net_amount * (1 + tax_rate)
$$;
```

### 35.1. Chú ý return type và function identity

PostgreSQL xác định function identity từ tên và argument types. Không thể tùy ý đổi return type bằng CREATE OR REPLACE trong mọi trường hợp. Nếu cần đổi incompatible signature, phải thiết kế migration, dependencies và privileges.

### 35.2. Khai báo rõ mỗi lần replace

Đừng giả định một migration thay function body nhưng bỏ qua thuộc tính sẽ luôn giữ đúng metadata mong muốn. Khi review code, đọc lại function definition sau deploy để chắc volatility/strict/parallel flags đúng.

### 35.3. Không đổi labels chỉ để làm EXPLAIN đẹp hơn

Một function có hiệu năng tốt nhưng metadata sai sẽ gây lỗi correctness nghiêm trọng hơn một plan hơi chậm. Tối ưu phải bắt đầu từ semantics đúng.

## 36. COST và ROWS: metadata tối ưu khác với ba thuộc tính chính

PostgreSQL còn có:

```sql
COST <estimated_execution_cost>
ROWS <estimated_result_rows>
```

`COST` giúp planner ước lượng chi phí gọi function. `ROWS` áp dụng cho set-returning functions.

Ví dụ:

```sql
CREATE FUNCTION function_attrs_lab.slowish_calculation(
    x numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
COST 10
AS $$
    SELECT x * x + sqrt(abs(x))
$$;
```

### 36.1. COST không phải mili giây

Cost là đơn vị tương đối của PostgreSQL planner, không phải lời hứa mỗi call tốn 10 ms.

### 36.2. COST không sửa sai volatility

Hàm VOLATILE nhưng chi phí thấp vẫn VOLATILE. Hàm IMMUTABLE có cost cao vẫn immutable về semantics. Hai loại metadata giải quyết vấn đề khác nhau.

### 36.3. Hàm có thể được inline

Một số SQL-language functions đủ điều kiện có thể được planner inline vào query. Vì vậy không nên dựa vào số lần xuất hiện trong EXPLAIN để kết luận function body được gọi đúng N lần.

## 37. EXPLAIN: quan sát tác động mà không đoán số call

Ví dụ:

```sql
EXPLAIN (VERBOSE)
SELECT
    function_attrs_lab.net_to_gross(100, 0.08) AS constant_gross,
    function_attrs_lab.net_to_gross(
        s.quantity * s.unit_price,
        0.08
    ) AS gross_from_row
FROM function_attrs_lab.sales AS s;
```

Hàm với arguments constant có thể được fold, trong khi lời gọi phụ thuộc `s.quantity` và `s.unit_price` phải dựa vào dữ liệu hàng.

### 37.1. So condition STABLE và VOLATILE

```sql
EXPLAIN (VERBOSE)
SELECT sale_id, sold_at
FROM function_attrs_lab.sales
WHERE sold_at < now();

EXPLAIN (VERBOSE)
SELECT sale_id, sold_at
FROM function_attrs_lab.sales
WHERE sold_at < clock_timestamp();
```

Tìm:

- `Index Cond`.
- `Filter`.
- `Seq Scan` hoặc `Index Scan`.
- Các expression được planner giữ hay thay bằng constant.

### 37.2. Với ANALYZE

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT SUM(
    function_attrs_lab.line_amount(quantity, unit_price)
)
FROM function_attrs_lab.sales;
```

Xem actual rows, loops, buffers và execution time.

### 37.3. Không được nhầm EXPLAIN ANALYZE trên SELECT và DML

`EXPLAIN ANALYZE` **thực thi câu SQL**. Nếu SELECT gọi một VOLATILE function **ghi dữ liệu hoặc tăng sequence**, nó vẫn có thể tạo side effects.

Do đó ngay cả `EXPLAIN ANALYZE SELECT function_attrs_lab.set_product_price(...)` cũng **không phải thao tác quan sát thuần túy**. Trên production, đừng chạy khi chưa xác định function an toàn.

## 38. Kiểm tra parallel plan

Một truy vấn phù hợp:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    SUM(function_attrs_lab.line_amount(quantity, unit_price))
FROM function_attrs_lab.sales;
```

Trên lab bốn rows sẽ thường không có Gather. Để thí nghiệm với nhiều dữ liệu, có thể dùng bảng test lớn riêng.

### 38.1. Tạo bảng benchmark tùy chọn

```sql
CREATE TABLE function_attrs_lab.large_sales AS
SELECT
    g.n AS sale_id,
    ((g.n % 5) + 1)::integer AS quantity,
    ((g.n % 1000) + 100)::numeric AS unit_price
FROM generate_series(1, 500000) AS g(n);

ANALYZE function_attrs_lab.large_sales;
```

Đo:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT SUM(
    function_attrs_lab.line_amount(quantity, unit_price)
)
FROM function_attrs_lab.large_sales;
```

Đây là lab tạo thêm 500.000 rows, **chỉ chạy trong database thử nghiệm** và cần cân nhắc disk/WAL/CPU.

### 38.2. Gợi ý cấu hình thử nghiệm trong transaction

Trong môi trường lab nếu người chạy có quyền:

```sql
BEGIN;
SET LOCAL max_parallel_workers_per_gather = 2;
SET LOCAL min_parallel_table_scan_size = '0';
SET LOCAL parallel_setup_cost = 0;
SET LOCAL parallel_tuple_cost = 0;

EXPLAIN (ANALYZE, BUFFERS)
SELECT SUM(
    function_attrs_lab.line_amount(quantity, unit_price)
)
FROM function_attrs_lab.large_sales;

ROLLBACK;
```

Các setting này làm parallel plan dễ được cân nhắc hơn, **không cam kết PostgreSQL sẽ sinh workers**. Cấu hình thực tế, giới hạn tài nguyên, query shape và parallel labeling của các hàm đều ảnh hưởng.

### 38.3. So với function UNSAFE

Một lời gọi `reserve_event_id()` hoặc `set_product_price()` là unsafe. Đừng đặt function có side effects vào aggregate benchmark chỉ để chứng minh serial: nó sẽ **thực hiện side effects thật** và làm sai dữ liệu/sequence.

Nếu cần so plan, có thể tạo function UNSAFE thuần toán học riêng trong lab nhưng nhớ rằng nhãn là hạn chế planner, không phải kết quả benchmark của một thuật toán khác:

```sql
CREATE FUNCTION function_attrs_lab.line_amount_conservative(
    quantity integer,
    unit_price numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL UNSAFE
AS $$
    SELECT quantity * unit_price
$$;
```

Thử:

```sql
EXPLAIN
SELECT SUM(
    function_attrs_lab.line_amount_conservative(
        quantity,
        unit_price
    )
)
FROM function_attrs_lab.large_sales;
```

Trường hợp này mô phỏng **khai báo bảo thủ**, không cho thấy một function thực sự nguy hiểm. Khi planner nhận diện lời gọi UNSAFE trong query, cơ hội chọn parallel execution sẽ bị hạn chế theo contract.

### 38.4. Không ép parallel trên production

Những tham số `SET LOCAL` trên chỉ để thực nghiệm; không điều chỉnh global cost settings hay số workers production chỉ để plan trông nhiều node hơn.

## 39. Tại sao chức năng đọc bảng phải xem loại bảng?

Hàm:

```sql
SELECT unit_price
FROM function_attrs_lab.product_prices
WHERE product_id = p_product_id
```

chỉ đọc bảng thường, không có temp/session-local state, nên có thể phù hợp `STABLE PARALLEL SAFE` như ví dụ.

Nhưng một hàm khác:

```sql
SELECT discount_rate
FROM pg_temp.session_discounts
WHERE product_id = p_product_id
```

đọc temporary table của session, nên không nên gắn SAFE. Tính chất “chỉ SELECT” không tự động chứng minh parallel-safe; **nguồn dữ liệu và context** rất quan trọng.

### 39.1. Unlogged tables và foreign tables

Các loại relation/truy cập bên ngoài có semantics riêng. Nếu function đi qua FDW/extension hoặc relation đặc biệt, phải xét đường thực thi thực tế và parallel support của từng thành phần, không suy luận SAFE chỉ từ chữ SELECT.

### 39.2. Dynamic SQL

Một function PL/pgSQL dùng `EXECUTE dynamic_sql` có thể chạy những truy vấn khác nhau theo input. Nếu tác giả không kiểm soát được mọi đường thực thi, đánh dấu IMMUTABLE hoặc PARALLEL SAFE là rủi ro cao.

## 40. Hàm gọi hàm khác: tính transitive của dependency

Giả sử:

```sql
CREATE FUNCTION function_attrs_lab.gross_with_factor(
    net_amount numeric,
    tax_rate numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT function_attrs_lab.net_to_gross(
        net_amount, tax_rate
    )
$$;
```

Hàm con `net_to_gross` là thuần toán học, nên wrapper có thể phù hợp cả ba nhãn.

Nếu thay thân wrapper thành:

```sql
-- Ý tưởng không dùng production:
-- SELECT function_attrs_lab.net_to_gross(
--     net_amount,
--     current_setting('app.tax_rate')::numeric
-- );
```

thì wrapper không còn IMMUTABLE vì hệ số thuế được đọc từ state động, bất kể tên hàm con là immutable.

### 40.1. Đọc catalog của hàm con

Đối với các dependencies có thể xác định, kiểm tra:

```sql
SELECT
    p.oid::regprocedure,
    p.provolatile,
    p.proparallel
FROM pg_proc AS p
WHERE p.oid =
    'function_attrs_lab.net_to_gross(numeric,numeric)'
        ::regprocedure;
```

Nếu dùng extension hoặc native code, ngoài catalog còn cần hiểu tài liệu/hành vi thật.

### 40.2. PostgreSQL không tự “chữa” wrapper sai nhãn

Đừng mong planner luôn phát hiện wrapper được khai báo SAFE nhưng gọi UNSAFE rồi tự đổi thành UNSAFE. Phân loại đúng là trách nhiệm của người viết function và quy trình review.

## 41. Volatility không phải transaction isolation

So sánh:

| Khái niệm | Giải quyết |
| --- | --- |
| `IMMUTABLE/STABLE/VOLATILE` | Mức độ ổn định kết quả/hành vi của function cho optimizer và snapshot khi function chạy SQL |
| `READ COMMITTED` | Snapshot thường được làm mới theo từng statement |
| `REPEATABLE READ` | Snapshot của transaction ổn định theo semantics PostgreSQL |
| `SERIALIZABLE` | Cung cấp mức isolation mạnh hơn với khả năng serialization failure |
| `SELECT ... FOR UPDATE` | Khóa row cho hoạt động cập nhật phối hợp |

Một function STABLE đọc bảng giá không ngăn transaction khác UPDATE bảng giá; một function IMMUTABLE tính tổng không tạo ra transaction isolation mới.

## 42. Volatility không phải thread safety của Java

Trong Java, “thread-safe” nghĩa có thể dùng qua nhiều threads mà không có race/state corruption theo contract.

Trong PostgreSQL:

- `PARALLEL SAFE` nghĩa có thể chạy trong PostgreSQL parallel worker trong những điều kiện phù hợp.
- `IMMUTABLE` nghĩa kết quả không phụ thuộc state thay đổi với cùng arguments.
- `STRICT` nghĩa có thể bỏ qua body khi argument NULL.

Đừng mang định nghĩa thread-safety của một class Java sang áp trực tiếp vào các thuộc tính của function PostgreSQL.

### 42.1. PostgreSQL parallel workers là processes

Parallel query dùng các backend worker processes với quy tắc riêng về snapshot, connection/backend state và shared resources. Không nên hình dung chúng như các Java threads cùng chia sẻ mọi object trong một process.

## 43. Security DEFINER/INVOKER là một chiều khác

PostgreSQL có:

```sql
SECURITY INVOKER
SECURITY DEFINER
```

để điều khiển quyền thực thi/role của function theo cơ chế phù hợp.

Chúng **khác** với volatility, STRICT và parallel safety.

### 43.1. SECURITY DEFINER không tự có nghĩa IMMUTABLE

Một function được chạy với quyền owner vẫn có thể đọc bảng, thay đổi dữ liệu, lấy sequence hoặc truy cập session settings. Cần đánh giá volatility và parallel safety theo hành vi thật, không theo tên mode bảo mật.

### 43.2. Tránh search_path injection

Với SECURITY DEFINER function, cần thiết kế schema qualification, search_path cố định/an toàn và quyền execute. Một function được đánh dấu IMMUTABLE không làm nó miễn nhiễm khỏi vấn đề search_path hoặc SQL injection.

### 43.3. Không cần SECURITY DEFINER để tối ưu

Nếu function chỉ tính toán số học, không có lý do tự động nâng quyền bằng SECURITY DEFINER. Đây là quyết định bảo mật tách biệt.

## 44. Hàm trong WHERE, JOIN, ORDER BY và sự đánh giá lại

Ví dụ một SQL:

```sql
SELECT
    s.sale_id,
    function_attrs_lab.line_amount(
        s.quantity, s.unit_price
    ) AS total
FROM function_attrs_lab.sales AS s
WHERE function_attrs_lab.line_amount(
    s.quantity, s.unit_price
) > 100
ORDER BY total DESC;
```

### 44.1. Số lần xuất hiện trong SQL không bằng số lần body chạy

Planner có thể:

- Inline một số SQL functions.
- Loại bỏ expression không dùng.
- Sắp xếp lại evaluation phù hợp với volatility và semantics.
- Tính một expression ở stage khác.

Không suy luận “function xuất hiện hai lần thì chắc chắn thân hàm gọi đúng hai lần mỗi row”.

### 44.2. VOLATILE function trong ORDER BY

`ORDER BY random()` tạo thứ tự ngẫu nhiên theo việc đánh giá biểu thức, nhưng có chi phí sort và không phù hợp cho paging ổn định.

```sql
SELECT sale_id
FROM function_attrs_lab.sales
ORDER BY random()
LIMIT 2;
```

Nếu application cần pagination nhất quán, dùng key rõ và tie-breaker unique thay vì một random key biến động.

### 44.3. Các phép logic không có short-circuit tuyệt đối

Không dựa vào:

```sql
WHERE condition_a
  AND dangerous_function(...)
```

với giả định PostgreSQL **luôn đánh giá condition_a trước**, rồi chỉ gọi function sau. SQL planner có thể sắp xếp biểu thức theo quy tắc cho phép.

Để tránh lỗi như chia cho 0 trong expression, dùng `CASE`/`NULLIF` hoặc thiết kế function phù hợp, chứ không dựa vào thứ tự AND/OR.

## 45. Lựa chọn cách khai báo theo checklist

Khi tạo một function mới:

### 45.1. Bước 1 — phân loại volatility

Hỏi:

- Hàm có thể ghi dữ liệu/sequence hoặc side effects không? → **VOLATILE**.
- Hàm đọc thời gian thực `clock_timestamp()`, random, dữ liệu/state thay đổi trong statement không? → **VOLATILE**.
- Hàm đọc bảng thường, session setting hoặc transaction/statement timestamp và hứa ổn định trong câu query không? → xem **STABLE**.
- Hàm thuần trên input, không đọc state có thể đổi không? → xem **IMMUTABLE**.

### 45.2. Bước 2 — quyết định STRICT

Hỏi:

- Khi **bất kỳ input là NULL**, có đúng là kết quả phải NULL và không cần chạy body? → **STRICT**.
- Hàm cần xử lý, mặc định hóa hoặc ghi nhận NULL theo logic riêng? → **CALLED ON NULL INPUT**.
- Có side effects nào bắt buộc diễn ra ngay cả với NULL không? → không chọn STRICT theo thói quen.

### 45.3. Bước 3 — quyết định parallel safety

Hỏi:

- Có UPDATE/INSERT/DELETE, sequence hoặc thay đổi transaction/config state không? → **UNSAFE**.
- Có temporary table, cursor, connection/backend-local state không đồng bộ với workers không? → **RESTRICTED**.
- Chỉ đọc các relation an toàn, dùng functions an toàn và không tác động state? → có thể **SAFE**.
- Không hiểu rõ external extension/native dependency? → giữ mặc định **UNSAFE** cho tới khi xác minh.

### 45.4. Bước 4 — đo, không chỉ suy luận

- Query `pg_proc` kiểm tra metadata.
- Thử input bình thường và NULL.
- Thử thay state giữa statements nếu gắn STABLE.
- Thử prepared plans nếu có cơ hội constant folding.
- Kiểm tra EXPLAIN cho expression index và parallel scan.
- Kiểm thử cả correctness lẫn latency trên dữ liệu đại diện.

## 46. Bảng ví dụ tổng hợp

| Loại hàm | Volatility | Null-input | Parallel | Lý do |
| --- | --- | --- | --- | --- |
| `x * y` thuần số học | IMMUTABLE | STRICT nếu NULL → NULL | SAFE | Chỉ dùng arguments |
| `COALESCE(x,0)` | IMMUTABLE | CALLED ON NULL INPUT | SAFE | Cần tự xử lý NULL |
| Tra giá từ bảng thường | STABLE | STRICT nếu thiếu ID phải trả NULL | SAFE nếu dependencies an toàn | Dữ liệu bảng có thể đổi giữa statements |
| Đọc `now()` | STABLE | Không áp dụng nếu không args | Tùy dependencies; xem catalog | Transaction timestamp |
| Đọc `clock_timestamp()` | VOLATILE | Không áp dụng nếu không args | Xem catalog | Wall clock thay đổi |
| `random()` | VOLATILE | Không áp dụng nếu không args | Xem catalog | Kết quả có thể biến động |
| `nextval()` | VOLATILE | Tùy wrapper | UNSAFE | Thay sequence state |
| UPDATE bảng trong function | VOLATILE | Tùy nghiệp vụ | UNSAFE | Ghi dữ liệu |
| Đọc temporary table | STABLE nếu chỉ đọc ổn định trong statement | Tùy input | RESTRICTED | Session-local state |
| Wrapper phụ thuộc GUC | STABLE trong mô hình phù hợp | Tùy input | Đánh giá riêng | Phụ thuộc config/session |
| Hàm không khai báo gì | VOLATILE | CALLED ON NULL INPUT | UNSAFE | Các mặc định bảo thủ |

Bảng này là **gợi ý phân tích**, không thay thế việc đọc thân hàm, loại relation, các hàm con và catalog PostgreSQL đang chạy.

## 47. Anti-pattern thường gặp

| Anti-pattern | Rủi ro | Hướng đúng |
| --- | --- | --- |
| Gắn IMMUTABLE cho `now()` | Kết quả bị fold/cache sai | STABLE theo bản chất thời gian |
| Gắn IMMUTABLE cho lookup bảng | Cached/indexed results có thể lỗi thời | STABLE nếu chỉ đọc theo statement |
| Gắn STABLE cho hàm UPDATE | Sai mức side effect; có thể lỗi SQL runtime | VOLATILE + UNSAFE |
| Gắn VOLATILE cho mọi phép toán thuần | Bỏ lỡ tối ưu hợp lệ | Đánh giá IMMUTABLE đúng |
| Dùng STRICT cho hàm `COALESCE(x,0)` | NULL bị trả sớm, không thành 0 | CALLED ON NULL INPUT |
| Hiểu STRICT là output NOT NULL | Trả NULL với denominator=0 vẫn hợp lệ | Xem body và domain |
| Dùng STRICT để bắt validation lỗi | NULL được trả sớm thay vì phát lỗi | Chủ động xử lý input |
| Gắn SAFE cho wrapper gọi nextval | Parallel worker không an toàn | UNSAFE |
| Gắn SAFE cho đọc temp table | Worker không dùng session temp state như leader | RESTRICTED |
| Nghĩ IMMUTABLE tự động SAFE | Hai hợp đồng độc lập | Đánh giá parallel riêng |
| Nghĩ VOLATILE đồng nghĩa UNSAFE | Không phải suy luận tổng quát | Xem side effects và dependencies |
| Nghĩ SAFE chắc chắn có Gather | Parallel plan phụ thuộc planner và workload | EXPLAIN trên dữ liệu đại diện |
| Nghĩ RESTRICTED luôn vẫn parallel | Có thể không thể hoãn evaluation lên leader | Đánh giá plan |
| Đổi nhãn để “ép” index được tạo | Index semantics bị sai | Chỉ dùng IMMUTABLE thật |
| Dùng `now()` trong partial index | Predicate trôi theo thời gian | Index sold_at + query bound |
| Dùng function volatile trong generated column | Persisted value không hợp lệ về mô hình | Chỉ expression immutable phù hợp |
| Đặt side effect trong WHERE mong chạy đúng N lần | Planner có thể thay đổi evaluation | Workflow DML rõ ràng |
| Coi COST là milliseconds | Planner cost tương đối | Đo EXPLAIN ANALYZE |
| Dùng EXPLAIN ANALYZE để “xem thử” function ghi | Side effect thật | Chỉ EXPLAIN hoặc lab rollback khi phù hợp |
| Dùng sequence rồi ROLLBACK để “trả ID” | Sequence vẫn tiến | Chấp nhận gaps |
| Bỏ qua metadata khi CREATE OR REPLACE | Flags sai sau migration | Đọc pg_proc/pg_get_functiondef |
| Tin generic plan luôn phản ánh GUC mới với hàm IMMUTABLE sai | Stale constants | Chọn STABLE/truyền args |
| Dùng SECURITY DEFINER để giải quyết planner | Nâng quyền không cần thiết | Tách vấn đề security |
| Gắn SAFE cho function có dynamic SQL không kiểm soát | Path thực thi có thể unsafe | Audit mọi nhánh |
| Dùng SQL NULL như FALSE mặc định | Sai semantics ba giá trị | Quy định policy và viết explicit |

## 48. Bài tập thực hành PostgreSQL

Thực hiện trên schema `function_attrs_lab`. Với bài yêu cầu thay dữ liệu, có thể dùng `BEGIN ... ROLLBACK` để trả về trạng thái mẫu. Các bài parallel/explain cần dữ liệu lớn tùy chọn để có plan đáng quan sát.

1. **Khái niệm:** diễn đạt sự khác nhau giữa volatility, STRICT và parallel safety bằng ba câu độc lập.
2. **Mặc định:** tạo function cộng số không khai báo attributes và đọc metadata mặc định từ `pg_proc`.
3. **Phân loại:** hàm cộng hai số với args numeric có thể là IMMUTABLE không? Vì sao?
4. **STABLE:** hàm đọc giá từ bảng product_prices nên STABLE hay IMMUTABLE?
5. **VOLATILE:** giải thích vì sao hàm dùng `nextval()` phải VOLATILE.
6. **Wall clock:** so `now()` và `clock_timestamp()` trong một SELECT.
7. **Statement time:** so `now()` với `statement_timestamp()` qua hai statements trong một transaction.
8. **Clock demo:** dùng pg_sleep ngắn trong lab để thấy thời gian thay đổi.
9. **Pure function:** tạo `net_to_gross(numeric,numeric) IMMUTABLE STRICT PARALLEL SAFE`.
10. **Test tính toán:** gọi net_to_gross với cùng arguments nhiều lần.
11. **Strict null:** gọi net_to_gross với net_amount NULL và tax_rate 0.08.
12. **Second arg NULL:** gọi net_to_gross với amount=100 và tax_rate=NULL.
13. **NULL policy:** giải thích vì sao hàm `COALESCE(x,0)` không nên STRICT.
14. **Default on null:** viết `zero_if_null` và kiểm tra output 0 khi NULL.
15. **Strict boolean:** so `is_positive_strict(NULL)` và `is_positive_or_false(NULL)`.
16. **Output NULL:** phân tích `safe_ratio(10,0)` và chứng minh STRICT không cấm output NULL.
17. **Zero denominator:** thiết kế phiên bản safe_ratio ném lỗi khi mẫu số bằng 0, chọn STRICT thế nào?
18. **Side effect:** tạo `reserve_event_id(event_type)` với sequence, VOLATILE STRICT UNSAFE.
19. **NULL side effect:** giải thích vì sao reserve_event_id(NULL) không cấp sequence value.
20. **Sequence rollback:** thực hiện nextval trong transaction rồi rollback, kiểm tra sequence không quay lại số cũ.
21. **Table lookup:** viết `lookup_price(bigint)` và thử thay giá giữa statements trong transaction lab.
22. **Snapshot:** so ý nghĩa snapshot của STABLE SQL function và VOLATILE function.
23. **Mislabel IMMUTABLE:** giải thích lỗi khi lookup bảng bị gắn immutable.
24. **GUC:** tạo demo factor session, giải thích vì sao current_setting không immutable.
25. **Prepared plans:** mô tả trường hợp cached plan giữ kết quả sai nếu function phụ thuộc GUC bị khai báo IMMUTABLE.
26. **Argument explicit:** chuyển dependency config thành tax_rate argument cho immutable calculation.
27. **Expression index:** tạo `normalize_sku` và index trên `normalize_sku(sku)`.
28. **Index semantics:** vì sao một expression index không chấp nhận function chỉ STABLE?
29. **Collation drift:** khi cập nhật library/ICU collation rules, index normalization có thể cần làm gì?
30. **Partial index:** vì sao `WHERE sold_at >= now() - interval '7 days'` không phù hợp trong index predicate?
31. **Index thay thế:** đề xuất B-tree sold_at và query WHERE với now() để tìm bảy ngày gần nhất.
32. **Generated column:** tạo bảng sku_inputs và generated normalized_sku từ immutable function.
33. **CHECK constraint:** tại sao không nên dùng lookup bảng hoặc now() làm ràng buộc động trong CHECK?
34. **Volatile DML:** viết function `set_product_price`, xác định volatility và parallel classification.
35. **Thay giá:** chạy set_product_price trong transaction lab và rollback.
36. **Parallel SAFE:** xác định vì sao `line_amount(quantity,unit_price)` có thể SAFE.
37. **Parallel RESTRICTED:** giải thích tại sao đọc temp table/session state có thể cần RESTRICTED.
38. **Backend identity:** tạo function backend_identity() và lý giải nhãn PARALLEL RESTRICTED.
39. **Parallel UNSAFE:** kể ba hoạt động buộc dùng UNSAFE.
40. **Độc lập:** nêu một function STABLE SAFE và một function VOLATILE UNSAFE.
41. **Độc lập nữa:** giải thích tại sao VOLATILE không tự suy ra UNSAFE cho mọi function.
42. **Nested function:** wrapper gọi immutable child nhưng dùng GUC có còn immutable không?
43. **Catalog:** query `pg_proc.provolatile,proisstrict,proparallel` toàn schema lab.
44. **Built-ins:** đọc metadata now, clock_timestamp, random, pg_backend_pid trên server của bạn.
45. **Signature:** phân biệt `f(integer)` và `f(numeric)`; vì sao phải dùng casts khi test NULL?
46. **Function DDL:** dùng pg_get_functiondef để xem declarations đầy đủ.
47. **ALTER FUNCTION:** đổi add_numbers_default thành IMMUTABLE STRICT PARALLEL SAFE rồi đọc catalog.
48. **Migration:** giải thích vì sao ALTER FUNCTION không tái tính mọi indexed values.
49. **EXPLAIN:** so expression net_to_gross với constants và với column references.
50. **WHERE:** so EXPLAIN WHERE sold_at<now() và WHERE sold_at<clock_timestamp().
51. **Index Cond/Filter:** giải thích khác biệt khi volatile expression không thể dùng như hằng scan.
52. **Benchmark:** tạo large_sales 500.000 rows trên lab, dùng EXPLAIN ANALYZE BUFFERS để đo SUM(line_amount(...)).
53. **Parallel plan:** đặt SET LOCAL parallel costs trong transaction lab, quan sát có Gather không.
54. **Parallel conservatism:** so line_amount SAFE với line_amount_conservative UNSAFE.
55. **No Gather:** giải thích vì sao bảng bốn hàng không parallel dù function SAFE.
56. **COST:** thêm COST cho function, phân biệt với thời gian milliseconds.
57. **Inlining:** tại sao một SQL function không luôn xuất hiện thành một node riêng trong EXPLAIN?
58. **Concurrency:** một STABLE function lookup bảng có khóa các rows để chống transaction khác update không?
59. **Java:** giải thích vì sao prepared/cached plans trong driver làm tăng rủi ro khi khai báo immutable sai.
60. **Evaluation order:** vì sao đặt VOLATILE side-effect function trong WHERE không phải cách chắc chắn gọi đúng một lần mỗi row?
61. **Security:** SECURITY DEFINER ảnh hưởng quyền chứ không tự đảm bảo IMMUTABLE/SAFE, đúng hay sai?
62. **Review:** xây checklist để đánh giá volatility/strict/parallel safety của một function PL/pgSQL có dynamic SQL.
63. **Edge NULL:** thiết kế hàm nhận quantity=NULL và coi là lỗi thay vì mặc định 1; bạn chọn STRICT hay tự kiểm tra?
64. **Temp table:** mô tả vòng đời temp table khi connection pool tái sử dụng session và rủi ro của function RESTRICTED.
65. **Regression test:** thiết kế test thay GUC, UPDATE bảng giá, truyền NULL và chạy EXPLAIN trước/sau sửa metadata.
66. **Đề bài tổng hợp:** một tính năng bán hàng cần tính tiền thuần, tra giá hiện hành, cấp order ID và đọc session discount; hãy phân loại cả ba thuộc tính cho từng hàm và giải thích từng lựa chọn.

## 49. Checklist review function trước khi đưa lên production

Trước khi duyệt migration `CREATE FUNCTION`/`ALTER FUNCTION`:

1. **Cùng input có luôn cho kết quả như nhau, không phụ thuộc thời gian hoặc database state?**
2. **Function có gọi random, now, clock_timestamp, current_setting, nextval hoặc đọc bảng không?**
3. **Nếu đọc bảng, snapshot statement và khả năng dữ liệu thay đổi đã được tính tới?**
4. **Có PL/pgSQL dynamic SQL, extension/native call hoặc hàm con chưa được audit không?**
5. **Volatility mặc định VOLATILE đã đúng hay quá bảo thủ?**
6. **STRICT có thật sự đúng khi bất kỳ argument nào NULL?**
7. **Có yêu cầu NULL→0/FALSE/default mà STRICT sẽ chặn body không?**
8. **Output có thể NULL dù input không NULL không?**
9. **Có side effects phải diễn ra với NULL arguments không?**
10. **Function có ghi dữ liệu, thay sequence, transaction/config state không?**
11. **Có đọc temp table/cursor/backend-local state không?**
12. **Các hàm con/relations có parallel-safe thật không?**
13. **Có bị đánh dấu SAFE chỉ để ép planner parallelize không?**
14. **Expression index/generated column/partial index có phụ thuộc hàm này không?**
15. **Nếu thay function body, có cần REINDEX/recompute persisted values không?**
16. **Prepared statement/cached plan có thể giữ kết quả từ phân loại sai không?**
17. **COST/ROWS đã phản ánh workload ở mức hợp lý chưa?**
18. **Có quyền SECURITY DEFINER/INVOKER và search_path phù hợp không?**
19. **Catalog pg_proc và pg_get_functiondef sau deploy có đúng metadata dự kiến không?**
20. **Đã kiểm tra correctness, EXPLAIN, NULL cases, concurrent changes và migration rollback plan không?**

## 50. Tổng kết

Ba thuộc tính giúp PostgreSQL hiểu **lời hứa của hàm với planner và executor**:

```text
VOLATILITY
    IMMUTABLE -> Cùng args, kết quả không đổi theo state/thời gian.
                 Có thể dùng constant folding và expression indexes.
    STABLE    -> Cùng args, ổn định trong một SQL statement.
                 Thích hợp với thời gian statement/transaction, lookup đọc.
    VOLATILE  -> Kết quả có thể đổi, có thể có side effects.
                 Không dùng các giả định ổn định để tối ưu.

NULL-INPUT
    STRICT / RETURNS NULL ON NULL INPUT
              -> Bất kỳ args=NULL: trả NULL, bỏ qua body.
    CALLED ON NULL INPUT
              -> Body chạy và tự xử lý NULL khi cần.

PARALLEL SAFETY
    SAFE       -> Có thể chạy trong parallel worker.
    RESTRICTED -> Chỉ chạy trong leader của parallel group.
    UNSAFE     -> Không an toàn trong parallel mode; hạn chế parallel plan.
```

Các quy tắc quan trọng nhất:

- **Không khai báo theo hiệu năng mong muốn**. Chọn thuộc tính theo hành vi thật của hàm.
- **IMMUTABLE** phù hợp phép tính thuần trên arguments; **STABLE** phù hợp các giá trị có thể thay đổi giữa statements nhưng ổn định trong một statement; **VOLATILE** phù hợp random, clock thay đổi, sequence và side effects.
- **STRICT** là một shortcut cho NULL inputs, không cam kết kết quả không NULL với mọi input khác.
- **PARALLEL SAFE/RESTRICTED/UNSAFE** độc lập với volatility và strictness. Đặc biệt, temporary table/backend state thường đòi leader, còn ghi dữ liệu/sequence phải được xem là unsafe.
- **Sai IMMUTABLE có thể nguy hiểm với prepared plans, expression indexes, generated columns và partial indexes.** Không “sửa” lỗi tạo index bằng metadata giả.
- **Function đọc bảng có thể STABLE mà không IMMUTABLE**; nhãn STABLE không tạo lock hay isolation mới.
- **Bảo mật, COST, ROWS và transaction isolation là những chiều khác**. Không dùng một thuộc tính để suy luận bừa sang chiều còn lại.
- **Dùng pg_proc để xác minh metadata**, `pg_get_functiondef` để xem DDL, và `EXPLAIN (ANALYZE, BUFFERS)` một cách an toàn để quan sát ảnh hưởng của planner.
- **Khi SELECT gọi function có side effects, EXPLAIN ANALYZE vẫn thực hiện side effects**. Không chạy các ví dụ ghi dữ liệu/sequence trên production chỉ để xem kế hoạch.

Khi viết đúng volatility, STRICT và parallel safety, bạn giúp PostgreSQL vừa **tối ưu đúng những gì có thể tối ưu**, vừa **không thực hiện các giả định nguy hiểm về kết quả, NULL và worker execution**. Đây là nền tảng để viết hàm SQL/PLpgSQL có tính đúng cao, hoạt động dự đoán được và phù hợp với những truy vấn PostgreSQL quy mô lớn.
