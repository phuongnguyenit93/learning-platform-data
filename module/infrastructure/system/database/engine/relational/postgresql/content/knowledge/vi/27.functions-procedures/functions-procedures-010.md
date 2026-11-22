# Chi phí gọi hàm, giới hạn tác dụng phụ và tiêu chí đưa logic vào database

Trong PostgreSQL, **hàm (function)** và **thủ tục (procedure)** giúp đưa một phần logic nghiệp vụ đến gần dữ liệu: tính toán giá trị, chuẩn hóa dữ liệu, thực hiện nhiều câu SQL, bảo vệ một thao tác cập nhật hoặc cung cấp giao diện SQL dùng chung. Tuy nhiên, đưa logic vào database **không tự động làm chương trình nhanh hơn, an toàn hơn hoặc dễ bảo trì hơn**. Quyết định đó phụ thuộc vào số lần gọi, ngôn ngữ thực thi, khả năng tối ưu của planner, hành vi giao dịch, tác dụng phụ, quyền truy cập và khả năng triển khai phiên bản mới.

Hãy xét hai cách tính tổng đơn hàng đã thanh toán cho 1.000 khách hàng:

- Cách A: chạy hàm `paid_order_count(customer_id)</BT> một lần cho mỗi hàng khách hàng. Nếu bên trong hàm lại thực hiện một câu `SELECT COUNT(*)</BT>, hệ thống có thể phải thực hiện nhiều lần truy vấn nội bộ.
- Cách B: dùng **một câu SQL tập hợp** với `JOIN</BT>, `GROUP BY</BT> hoặc một phép tổng hợp phù hợp, cho phép planner xem toàn bộ bài toán và tối ưu theo cách khác.

Cả hai có thể trả cùng kết quả, nhưng **chi phí khác nhau rõ rệt khi số dòng tăng**. Ngược lại, một hàm SQL nhỏ, đủ điều kiện **inlining**, có thể gần như không tạo ra ranh giới tối ưu hóa đáng kể. Vì vậy câu hỏi thực tế không phải “hàm PostgreSQL có chậm không?”, mà là **hàm được gọi ở đâu, bao nhiêu lần, thực hiện bao nhiêu công việc và planner nhìn thấy bao nhiêu logic bên trong?**

Bài thuộc chương **Hàm và thủ tục** của module *Database Engine Relational PostgreSQL*, tập trung vào ba chủ đề trong tên bài: **chi phí gọi hàm**, **giới hạn tác dụng phụ**, và **tiêu chí đưa logic vào database**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt function và procedure trong PostgreSQL.
2. Giải thích chi phí gọi hàm cố định và chi phí công việc bên trong hàm.
3. Nhận diện tình huống gọi hàm trên từng hàng gây *row-by-row overhead* hoặc mẫu N+1.
4. Hiểu khi nào hàm `LANGUAGE SQL</BT> có khả năng được planner *inline* và vì sao PL/pgSQL thường có biên thực thi riêng.
5. Viết lại một số logic từ loop sang set-based SQL.
6. Phân biệt `IMMUTABLE</BT>, `STABLE</BT>, `VOLATILE</BT> và các giới hạn sử dụng.
7. Hiểu planner metadata như `COST</BT>, `ROWS</BT>, `PARALLEL SAFE/RESTRICTED/UNSAFE</BT>, `STRICT</BT>.
8. Phân biệt thay đổi dữ liệu có tính transaction với sequence/external side effects.
9. Biết function không tự `COMMIT</BT> transaction của caller và điều kiện transaction control trong procedure.
10. Đánh giá lợi ích, rủi ro và chi phí vận hành khi đặt logic ở database thay vì Java/service.
11. Dùng `EXPLAIN (ANALYZE, BUFFERS)</BT> và công cụ thống kê để tìm nguyên nhân chậm.
12. Thiết kế API function/procedure an toàn, dễ versioning và dễ kiểm thử.

## 2. Bức tranh tổng thể: ứng dụng, SQL và logic bên trong database

~~~text
Java / HTTP service / batch job
            |
            | JDBC query / CALL
            v
       PostgreSQL server
            |
            +-- SQL parser / planner / executor
            |
            +-- SQL function
            |      +-- Có thể được inline nếu đủ điều kiện
            |      +-- Hoặc thực thi qua ranh giới hàm riêng
            |
            +-- PL/pgSQL function
            |      +-- Biến, IF, LOOP, RETURN
            |      +-- SQL statements chạy qua SQL engine
            |
            +-- Procedure
                   +-- CALL, thao tác SQL/procedural
                   +-- Transaction control trong điều kiện nhất định
~~~

Có **ba loại chi phí** cần đánh giá riêng:

- **Network round trips** giữa ứng dụng và database.
- **Overhead của mỗi lần gọi hàm** và của mỗi SQL statement bên trong.
- **Chi phí thực của dữ liệu**: đọc index/heap, JOIN, sort, aggregate, ghi WAL, locks và tranh chấp tài nguyên.

Đưa nhiều câu SQL từ Java vào một stored function có thể giảm round trips, nhưng nếu stored function tiếp tục chạy hàng nghìn truy vấn từng hàng, bạn chỉ chuyển mẫu N+1 từ tầng ứng dụng xuống database, không nhất thiết giải quyết bản chất.

## 3. Function và procedure khác nhau ở đâu?

| Khía cạnh | Function | Procedure |
|---|---|---|
| Tạo bằng | `CREATE FUNCTION</BT> | `CREATE PROCEDURE</BT> |
| Cách gọi thường gặp | `SELECT f(...)</BT>, trong biểu thức SQL | `CALL p(...)</BT> |
| Trả giá trị | Scalar, composite, SETOF/TABLE, void... | OUT/INOUT theo khả năng phiên bản, không dùng như scalar expression |
| Dùng trong SELECT/WHERE | Có, nếu kiểu/semantics phù hợp | Không theo cách gọi expression |
| Transaction control | Không tự BEGIN/COMMIT/ROLLBACK transaction của caller | Có thể trong điều kiện CALL/DO đặc biệt |
| Volatility labels | IMMUTABLE, STABLE, VOLATILE | Không cùng mô hình volatility cho expression |
| Inlining ở planner | Một số SQL functions đủ điều kiện | Không áp dụng như inline expression trong SELECT |
| Use case thường gặp | Tính toán, truy vấn có thể tái sử dụng, API trả dữ liệu, DML có kiểm soát | Workflow nhiều bước, tác vụ quản trị/batch cần CALL |

### 3.1. Function không phải “procedure viết bằng cú pháp khác”

Một function có thể thực hiện DML nếu được khai báo và thực thi phù hợp, nhưng không vì thế nó được phép commit riêng trong lúc caller còn transaction. Procedure có mô hình CALL và quy tắc transaction control đặc biệt.

### 3.2. Procedure không đương nhiên nhanh hơn function

Nếu procedure và function cùng chạy 10.000 câu UPDATE lặp, tổng chi phí phần lớn có thể vẫn là 10.000 thao tác SQL. Sự khác nhau về cách gọi không tự biến thuật toán row-by-row thành set-based.

### 3.3. Chọn loại đối tượng theo hợp đồng

- Cần expression trong SELECT hoặc tính giá trị: **function**.
- Cần một API thao tác qua `CALL</BT>, đôi khi cần quản lý transaction trong điều kiện hỗ trợ: **procedure**.
- Chỉ cần một câu SQL đơn giản do ứng dụng thực thi: không bắt buộc tạo function/procedure.

## 4. Một mô hình ước lượng chi phí gọi hàm

Để hiểu bottleneck, có thể mô hình hóa gần đúng:

\[
T_{\text{total}} \approx T_{\text{network}}+
N_{\text{calls}}\times T_{\text{call-overhead}}+
\sum_{i=1}^{N_{\text{calls}}} T_{\text{work},i}
+T_{\text{other}}
\]

Trong đó:

- `T_network</BT>: chi phí đưa yêu cầu qua network/protocol giữa client và PostgreSQL.
- `N_calls</BT>: số lần hàm thực sự được executor gọi.
- `T_call-overhead</BT>: dispatch, thiết lập ngữ cảnh, đánh giá arguments, xử lý kiểu, runtime/interpreter overhead nếu có.
- `T_work,i</BT>: chi phí SQL/biểu thức/ghi dữ liệu thực hiện trong lần thứ i.
- `T_other</BT>: planning, locks, serialization, fetch kết quả và overhead khác.

Đây là **mô hình tư duy**, không phải công thức chính xác mà PostgreSQL công khai dùng tính execution time.

### 4.1. Nhân nhỏ thành lớn

Nếu overhead mỗi lần gọi chỉ rất nhỏ, nhưng hàm xuất hiện ở biểu thức được đánh giá cho hàng triệu rows, tổng số lần gọi có thể biến overhead thành đáng kể.

### 4.2. Đừng đếm theo số hàng bảng một cách máy móc

Executor có thể lọc rows trước, inline biểu thức, thay đổi kế hoạch hoặc tránh gọi một biểu thức trong một số trường hợp. Số lần gọi phụ thuộc **plan thực tế**, không luôn bằng số rows vật lý trong bảng.

### 4.3. Chi phí bên trong hàm thường lớn hơn overhead thuần

Một PL/pgSQL function thực hiện `SELECT COUNT(*) FROM orders WHERE ...</BT> cho từng khách có thể tốn nhiều hơn một phép cộng số học rất nhiều. Vấn đề không chỉ là interpreter mà còn là **số truy vấn nội bộ và số lần đọc dữ liệu**.

## 5. Một function xuất hiện trong SELECT có thể bị gọi rất nhiều lần

Ví dụ:

~~~sql
SELECT
    order_id,
    amount,
    finance.apply_discount(amount, 0.10) AS after_discount
FROM sales.orders
WHERE status = 'paid';
~~~

Nếu câu SQL trả một triệu đơn, function có thể cần được đánh giá cho rất nhiều rows.

### 5.1. Hàm đơn giản không đồng nghĩa chi phí bằng không

Ngay cả khi thân function chỉ là một phép nhân và `round</BT>, PostgreSQL còn phải xử lý expression evaluation, argument types và kết quả; tác động thực tế phụ thuộc khả năng inline.

### 5.2. Hàm có SQL bên trong đáng lo hơn

~~~sql
SELECT customer_id,
       reporting.count_paid_orders(customer_id)
FROM core.customers;
~~~

Nếu `count_paid_orders</BT> chạy một câu SELECT bên trong cho mỗi customer, bạn có mô hình **per-row correlated work**, có thể gây hàng nghìn executor invocations và SQL executions.

### 5.3. Không nhất thiết mọi function call đều chậm

Hàm SQL đủ đơn giản có thể được inlined. Một function PL/pgSQL nhỏ cũng có thể hoàn toàn chấp nhận được nếu chỉ gọi vài lần mỗi request. **Đánh giá quy mô và plan**, không loại bỏ function chỉ vì có lời đồn “stored function chậm”.

## 6. SQL function và khả năng inlining

Hàm `LANGUAGE SQL</BT> chứa logic SQL. Trong một số điều kiện, PostgreSQL có thể **inline** thân hàm thành biểu thức hoặc quan hệ trong câu query gọi hàm.

Ví dụ:

~~~sql
CREATE FUNCTION finance.discounted_amount(
    p_amount NUMERIC,
    p_discount_rate NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT round(p_amount * (1 - p_discount_rate), 2);
$$;
~~~

Với một truy vấn gọi hàm:

~~~sql
SELECT finance.discounted_amount(amount, 0.10)
FROM sales.orders;
~~~

Planner **có thể** biến đổi logic tương ứng thành biểu thức nội bộ, giảm phần chi phí/rào cản của một lời gọi hàm riêng.

### 6.1. Inlining là khả năng, không phải cam kết

Không phải mọi SQL function đều được inline. Kết quả phụ thuộc:

- Cấu trúc function (scalar hay set-returning).
- Số câu lệnh và biểu thức trong thân.
- Volatility, strictness và thuộc tính khai báo.
- Security properties.
- `SET</BT> clauses, execution environment và các giới hạn planner.
- Cách hàm được gọi, operator types và PostgreSQL version.

### 6.2. SECURITY DEFINER và inlining

Hàm `SECURITY DEFINER</BT> có yêu cầu quyền riêng; planner không được phép tùy tiện inline làm thay đổi semantics quyền của function. Vì vậy nên xem SECURITY DEFINER là một trong các điều kiện có thể ngăn inline, không dùng chỉ để “gọi nhanh hơn”.

### 6.3. SQL function không luôn tốt hơn biểu thức trực tiếp

Một hàm SQL có cấu trúc phức tạp hoặc không đủ điều kiện inline vẫn là một lời gọi thực thi. Nếu chỉ dùng một lần và biểu thức đơn giản, viết trực tiếp trong SQL có thể dễ nhìn hơn. Nếu cần contract ổn định/tái sử dụng, function có thể đáng giá dù có overhead nhỏ.

### 6.4. Cách nhận diện

Dùng `EXPLAIN (VERBOSE)</BT> và theo dõi expression được hiển thị; có thể thấy biểu thức trong plan thay vì một lời gọi function rõ ràng. Tuy nhiên, output plan không phải API bảo đảm inlining dưới mọi điều kiện, nên kết hợp hiểu metadata và đo đạc.

## 7. PL/pgSQL function: sức mạnh và chi phí

`PL/pgSQL</BT> cung cấp biến, điều kiện, vòng lặp, xử lý lỗi, RETURN QUERY và gọi SQL statements.

~~~sql
CREATE FUNCTION finance.discounted_amount_pl(
    p_amount NUMERIC,
    p_discount_rate NUMERIC
)
RETURNS NUMERIC
LANGUAGE plpgsql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
BEGIN
    RETURN round(p_amount * (1 - p_discount_rate), 2);
END;
$$;
~~~

### 7.1. Không được inlined như SQL expression thông thường

PL/pgSQL function thường được thực thi thông qua runtime PL/pgSQL riêng, không có cùng kiểu SQL-function inlining với một số `LANGUAGE SQL</BT> functions. Điều này tạo ranh giới tối ưu hóa nếu hàm được gọi trong query.

### 7.2. SQL bên trong được thực hiện bởi PostgreSQL SQL engine

PL/pgSQL không “tự quét bảng” bằng interpreter riêng. Khi câu `SELECT</BT> hoặc `UPDATE</BT> được viết trong PL/pgSQL, nó vẫn được SQL engine phân tích/lập kế hoạch/thực thi theo các cơ chế tương ứng.

### 7.3. Caching plans không xóa overhead của nhiều lời gọi

PL/pgSQL có cơ chế lưu giữ kế hoạch cho những câu SQL phù hợp và cân nhắc custom/generic plans. Điều đó có thể giảm repeated planning, nhưng không làm 10.000 lần chạy SELECT trở thành một câu JOIN duy nhất.

### 7.4. Dynamic EXECUTE có trade-off riêng

Trong PL/pgSQL, `EXECUTE</BT> đối với SQL động thường yêu cầu lập kế hoạch lại câu SQL động mỗi lần chạy; nó có lợi khi cấu trúc SQL phải thay đổi hoặc cần custom plan theo giá trị, nhưng có thể tăng planning overhead và rủi ro injection nếu tạo chuỗi sai.

### 7.5. Khi nào PL/pgSQL phù hợp?

- Workflow nhiều bước cần transaction nhất quán.
- Điều kiện/logic procedural khó diễn đạt rõ bằng một câu SQL.
- Gói validation và DML thành một interface kiểm soát.
- Triggers hoặc chức năng cần xử lý trạng thái/bắt lỗi.
- Tác vụ quản trị có nghiệp vụ rõ.

Không chọn PL/pgSQL chỉ vì quen cú pháp IF/LOOP của Java.

## 8. Set-based SQL thường là lựa chọn đầu tiên

PostgreSQL được thiết kế để xử lý **tập hàng**. Khi có thể biểu diễn công việc bằng JOIN, aggregate, window function, `INSERT ... SELECT</BT> hoặc `UPDATE ... FROM</BT>, planner có nhiều cơ hội chọn access path và tổ chức công việc.

### 8.1. Row-by-row

~~~text
for customer in customers:
    count = SELECT COUNT(*)
            FROM orders
            WHERE orders.customer_id = customer.id
    save(customer, count)
~~~

Có thể phát sinh một truy vấn/call cho mỗi khách hàng.

### 8.2. Set-based

~~~sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS paid_count
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'paid'
GROUP BY c.customer_id;
~~~

Planner có thể tối ưu JOIN và aggregate trên nhiều khách cùng lúc.

### 8.3. COUNT ở LEFT JOIN

Dùng `COUNT(o.order_id)</BT> hoặc `COUNT(*) FILTER (WHERE ...)</BT> đúng cách; `COUNT(*)</BT> trên LEFT JOIN có thể đếm một null-extended row cho customer không có order, làm kết quả sai.

### 8.4. Không phải mọi correlated subquery đều xấu

Planner có thể decorrelate, cache hoặc chọn parameterized paths phù hợp trong một số SQL patterns. Vấn đề đặc biệt đáng xem là khi correlation bị đóng trong PL/pgSQL function mà planner của query ngoài không nhìn được cấu trúc truy vấn nội bộ.

## 9. Khi nào logic ở database giúp giảm network round trips?

Giả sử Java service cần:

1. Kiểm tra order đang `new</BT>.
2. Chuyển sang `paid</BT>.
3. Ghi audit log.
4. Trả kết quả.

Thực hiện bằng nhiều lệnh riêng từ Java có thể tạo nhiều network round trips và làm tăng nguy cơ các thao tác không nằm trong cùng transaction nếu code cấu hình sai.

Một function/procedure có thể thực hiện các bước này **gần dữ liệu** với một CALL/SELECT từ ứng dụng. Tuy nhiên:

- Phải giữ transaction semantics đúng.
- Phải kiểm tra concurrency.
- Không đưa network HTTP call không thể rollback vào giữa transaction nếu không có protocol phù hợp.
- Có thể viết một statement `UPDATE ... RETURNING</BT> kèm xử lý audit trigger/outbox thay vì procedural code nhiều bước.

**Giảm round trips là một lợi ích tiềm năng**, không phải bằng chứng mọi stored function đều nhanh hơn Java.

## 10. Volatility: IMMUTABLE, STABLE và VOLATILE

PostgreSQL sử dụng thuộc tính **volatility** để biết mức độ ổn định kết quả function và mức tự do optimizer có thể sử dụng.

| Thuộc tính | Ý nghĩa hợp đồng | Ví dụ phù hợp |
|---|---|---|
| `IMMUTABLE</BT> | Với cùng arguments, kết quả không đổi trong mọi lần gọi theo ngữ nghĩa hợp lệ | Toán học thuần túy, normalize thuần |
| `STABLE</BT> | Trong một statement, cùng arguments cho cùng kết quả trong semantics của lời gọi; có thể phụ thuộc trạng thái đọc ổn định | Lookup đọc bảng, thời gian hiện tại dạng transaction |
| `VOLATILE</BT> | Kết quả có thể đổi giữa các lần gọi hoặc có tác dụng phụ | `random()</BT>, `clock_timestamp()</BT>, sequence/DML |

### 10.1. Mặc định là VOLATILE

Khi không khai báo, function PostgreSQL thông thường được coi là `VOLATILE</BT> theo mặc định. Điều này bảo thủ, có thể hạn chế tối ưu nếu function thật sự thuần/stable.

### 10.2. Volatility là lời hứa của người tạo hàm

Đánh dấu sai là một lỗi correctness, không chỉ lỗi performance. Planner có thể dùng thông tin volatility để tối ưu/giảm đánh giá biểu thức hoặc lập plan dưới giả định kết quả ổn định.

### 10.3. Không chọn IMMUTABLE chỉ vì muốn dùng index

Một function đọc bảng giá/feature flags có thể trả kết quả khác sau INSERT/UPDATE dữ liệu, vì vậy nó không thật sự immutable. Cố gán `IMMUTABLE</BT> để PostgreSQL chấp nhận expression index hoặc generated column có thể dẫn đến kết quả cũ/sai sau khi dữ liệu thay đổi.

## 11. IMMUTABLE: hàm thuần và giới hạn

Ví dụ:

~~~sql
CREATE FUNCTION finance.add_tax(
    p_amount NUMERIC,
    p_tax_rate NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT round(p_amount * (1 + p_tax_rate), 2);
$$;
~~~

Hàm này dùng arguments và phép toán deterministic trong các điều kiện kiểu dữ liệu/thiết lập phù hợp.

### 11.1. Ứng dụng của IMMUTABLE

- Có thể đủ điều kiện dùng trong expression index.
- Có thể đủ điều kiện dùng trong generated column.
- Planner có thể constant-fold khi arguments là constants.
- Có thể hỗ trợ tối ưu với điều kiện volatility khác cũng được đáp ứng.

### 11.2. Không phụ thuộc bảng mutable

Nếu hàm đọc bảng cấu hình tỷ giá ngoại tệ hoặc bảng giá sản phẩm thay đổi, việc gán IMMUTABLE là sai. Kết quả không chỉ phụ thuộc arguments mà còn phụ thuộc dữ liệu bên ngoài arguments.

### 11.3. Timezone và settings là rủi ro

Một function chuyển timestamp dựa trên session TimeZone hoặc cấu hình có thể không thật sự IMMUTABLE. Không gán IMMUTABLE cho mọi phép định dạng ngày giờ chỉ vì “cùng thời điểm thì luôn cùng text”.

### 11.4. Caution với constant folding và cached plans

Nếu gán nhãn sai, một kết quả được tính trước và giữ trong cached plan có thể trở nên stale khi trạng thái môi trường/dữ liệu thay đổi. Lỗi có thể chỉ xuất hiện trên production với prepared statements và plan reuse.

## 12. STABLE: nhất quán trong statement

Ví dụ một function đọc tỷ lệ giảm giá đang lưu trong bảng:

~~~sql
CREATE FUNCTION pricing.current_discount(
    p_customer_id BIGINT
)
RETURNS NUMERIC
LANGUAGE SQL
STABLE
AS $$
    SELECT discount_rate
    FROM pricing.customer_discounts
    WHERE customer_id = p_customer_id;
$$;
~~~

Đây là cú pháp minh họa: các schemas/tables trên phải tồn tại.

### 12.1. Vì sao STABLE phù hợp hơn IMMUTABLE?

Tỷ lệ discount có thể đổi trong tương lai. Một statement đang chạy theo snapshot phù hợp có thể cần kết quả nhất quán, nhưng kết quả giữa các statements không được cam kết bất biến vĩnh viễn.

### 12.2. Giới hạn tác dụng phụ

`STABLE</BT> và `IMMUTABLE</BT> functions không được dùng để thực hiện database-modifying SQL theo rules mà PostgreSQL thực thi cho SQL/PL languages. Function có DML phải được định nghĩa `VOLATILE</BT> thích hợp.

### 12.3. Ví dụ thời gian

- `now()</BT>/`CURRENT_TIMESTAMP</BT> liên quan thời điểm transaction và có tính ổn định phù hợp với contract của chúng.
- `clock_timestamp()</BT> có thể thay đổi ngay trong cùng statement và được coi là VOLATILE.

### 12.4. Snapshot behavior

Với SQL và standard procedural languages, STABLE/IMMUTABLE functions có thể sử dụng snapshot của query gọi chúng theo semantics documented; VOLATILE functions thực hiện queries có thể thấy thay đổi qua những snapshots mới hơn trong cùng bối cảnh. Đây là vấn đề MVCC và độ ổn định kết quả, không chỉ planner cost.

## 13. VOLATILE: giá trị thay đổi và tác dụng phụ

Các function điển hình:

~~~sql
SELECT random();
SELECT clock_timestamp();
SELECT nextval('some_sequence');
~~~

Dòng `nextval</BT> yêu cầu sequence tồn tại; đây là ví dụ về một phép có tác dụng phụ.

### 13.1. DML bên trong function

Function muốn INSERT/UPDATE/DELETE dữ liệu theo workflow phải được khai báo với volatility phù hợp, thường là `VOLATILE</BT>.

### 13.2. VOLATILE không có nghĩa function được tự commit

Một function `VOLATILE</BT> vẫn nằm trong transaction của câu lệnh/caller và không tự `COMMIT</BT>/`ROLLBACK</BT> theo ý muốn.

### 13.3. Gọi nhiều lần có thể tạo nhiều side effects

Một hàm INSERT log được gọi trong SELECT của nhiều rows có thể ghi nhiều log rows, có thể nhiều hơn người gọi tưởng nếu query, joins, retries hoặc client behavior thay đổi. Không nên thiết kế một audit write cần đúng một lần bằng cách “đặt trong biểu thức SELECT tùy ý”.

### 13.4. Thứ tự đánh giá không nên là hợp đồng nghiệp vụ

SQL là ngôn ngữ khai báo. Không dựa vào thứ tự quan sát hiện tại của biểu thức, WHERE filters, joins hoặc LIMIT để bảo đảm một side-effect function chạy đúng thứ tự/số lần nếu tài liệu không cho bảo đảm đó.

### 13.5. Một side-effect function có thể gây khó tối ưu

Một số biến đổi của planner bị giới hạn để tôn trọng volatility semantics, nhưng gán VOLATILE cho function thuần chỉ để “cho chắc” cũng có thể hạn chế tối ưu hợp lệ. Phân loại theo thực tế, không theo thói quen.

## 14. STRICT và NULL semantics

Một function khai báo `STRICT</BT> (hoặc `RETURNS NULL ON NULL INPUT</BT>) thường không được thực thi khi có argument NULL; kết quả là NULL theo hợp đồng này.

~~~sql
CREATE FUNCTION finance.multiply_amount(
    p_amount NUMERIC,
    p_factor NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
STRICT
AS $$
    SELECT p_amount * p_factor;
$$;
~~~

### 14.1. Vì sao có lợi?

Nó tránh thực thi thân function trong những trường hợp đã biết kết quả NULL, và làm rõ contract.

### 14.2. Không gắn STRICT nếu cần xử lý NULL theo nghiệp vụ

Nếu function muốn coi `NULL</BT> là 0, hoặc NULL có nghĩa “dùng mức mặc định”, khai báo STRICT sẽ khiến thân function không chạy khi đầu vào NULL và làm kết quả khác mong muốn.

### 14.3. Không dùng STRICT để thay validate

STRICT không kiểm tra discount nằm trong [0,1], amount không âm hoặc ID có hợp lệ; cần constraints/validation độc lập.

## 15. Planner COST: ước lượng, không phải thời gian thực

PostgreSQL cho phép khai báo chi phí ước lượng khi chạy function:

~~~sql
CREATE FUNCTION finance.expensive_score(
    p_amount NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
COST 200
AS $$
    SELECT sqrt(abs(p_amount)::double precision)::numeric;
$$;
~~~

### 15.1. COST dùng làm gì?

`COST</BT> là **hướng dẫn cho planner**, không phải phép đo milliseconds. Giá trị nằm trong đơn vị cost model PostgreSQL, thông thường liên quan `cpu_operator_cost</BT>. Với set-returning functions, semantics ước lượng chi phí có thể được tính trên mỗi row kết quả.

### 15.2. Giá trị mặc định

Các PostgreSQL versions thông thường sử dụng cost mặc định thấp hơn cho internal/C functions (thường 1) và giá trị cao hơn cho function ngôn ngữ khác (thường 100), nếu không được định nghĩa khác. Đây là các **hằng số ước lượng**, không phải benchmarking thực tế.

### 15.3. COST không buộc planner gọi hàm ít lần

Tăng `COST</BT> không biến PL/pgSQL loop thành JOIN. Planner có thể cân nhắc đặt biểu thức/plan theo cách khác trong các ngữ cảnh cho phép, nhưng không phải “tối ưu tự động” cho một thuật toán O(N²).

### 15.4. Có thể bị inlining làm thay đổi vai trò COST

Nếu SQL function được inline, planner đánh giá biểu thức đã biến đổi; không được suy luận `COST</BT> luôn có ảnh hưởng như khi function là một opaque call.

### 15.5. Chỉ điều chỉnh sau khi đo

Nếu function thực sự đắt nhưng COST mặc định quá thấp, planner có thể đánh giá lệch. Ngược lại khai báo quá đắt có thể làm plan không tốt. Cần đo representative workload và so EXPLAIN, không bốc một số “cao cho nhanh”.

## 16. ROWS: ước lượng cho set-returning function

Function trả nhiều rows có thể khai báo `ROWS</BT>:

~~~sql
CREATE FUNCTION reporting.paid_orders_for_customer(
    p_customer_id BIGINT
)
RETURNS TABLE (
    order_id BIGINT,
    amount NUMERIC
)
LANGUAGE SQL
STABLE
ROWS 100
AS $$
    SELECT order_id, amount
    FROM sales.orders
    WHERE customer_id = p_customer_id
      AND status = 'paid';
$$;
~~~

### 16.1. ROWS không giới hạn kết quả

`ROWS 100</BT> **không phải LIMIT 100**. Đây là estimate planner về số rows function có thể trả khi chạy theo semantics của nó.

### 16.2. Vì sao quan trọng?

Nếu planner tưởng function trả 1.000 rows nhưng thực tế trả một triệu, JOIN order, join algorithm, memory và intermediate cardinality estimates có thể sai đáng kể.

### 16.3. Mặc định thông dụng

Với set-returning functions, PostgreSQL thường mặc định estimated `ROWS 1000</BT> khi không khai báo, nhưng thực tế tùy function/planner inlining và version. Không coi 1000 là giới hạn dữ liệu.

### 16.4. Điều chỉnh qua ALTER FUNCTION

~~~sql
ALTER FUNCTION reporting.paid_orders_for_customer(BIGINT)
ROWS 50 COST 100;
~~~

Ví dụ yêu cầu function tồn tại. Đây là thay đổi planner metadata, không sửa dữ liệu và không bảo đảm plan mới nhanh hơn.

## 17. PARALLEL SAFE, RESTRICTED và UNSAFE

Function labels còn ảnh hưởng query parallelization.

| Label | Ý nghĩa |
|---|---|
| `PARALLEL SAFE</BT> | Function an toàn để chạy trong parallel worker trong các điều kiện được công bố |
| `PARALLEL RESTRICTED</BT> | Không chạy trong worker, có thể chỉ được thực hiện ở leader trong phần kế hoạch phù hợp |
| `PARALLEL UNSAFE</BT> | Function có thể làm query không được parallelize theo các quy tắc planner |

### 17.1. Mặc định cần thận trọng

User-defined functions thường mặc định `PARALLEL UNSAFE</BT> nếu không khai báo. Một function thuần có thể được đánh dấu SAFE nếu đã xác minh đúng điều kiện.

### 17.2. Ví dụ hàm tính toán thuần

~~~sql
CREATE FUNCTION finance.square_number(
    p_input NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT p_input * p_input;
$$;
~~~

### 17.3. Những hoạt động cần thận trọng

Function làm thay đổi trạng thái database, gọi sequences, dùng temporary tables hoặc truy cập backend-local state có thể không an toàn để chạy trong worker. Phân loại đúng phụ thuộc hành vi cụ thể; không chỉ nhìn ngôn ngữ SQL hay PL/pgSQL.

### 17.4. Sai nhãn có thể nguy hiểm

Đánh dấu một function có side effects là PARALLEL SAFE để “ép query chạy nhanh” có thể gây lỗi hoặc hành vi không đúng. Không khai báo SAFE nếu chưa xác định đầy đủ behavior của function và các hàm nó gọi.

### 17.5. Có SAFE chưa chắc có Parallel Seq Scan

Planner còn phụ thuộc kích thước bảng, chi phí, cấu hình, operators, JOIN shape và workload. Đây là **điều kiện cho phép**, không phải yêu cầu bắt buộc chạy song song.

## 18. Side effects: định nghĩa đúng phạm vi

“Tác dụng phụ” không chỉ là DML. Cần phân loại:

1. **Thay đổi dữ liệu trong PostgreSQL transaction**: INSERT/UPDATE/DELETE.
2. **Sequence state**: `nextval</BT>, `setval</BT>, thường không rollback giống table rows.
3. **Locks**: row/table/advisory locks với lifetime khác nhau.
4. **Session/backend state**: một số GUCs, temporary objects, trạng thái phiên.
5. **External I/O**: HTTP, file, hệ thống thứ ba qua extension/procedural language hoặc cơ chế kết nối.
6. **Thông báo/đẩy sự kiện**: ví dụ `NOTIFY</BT>, logical outbox hoặc extension integration.
7. **Thời gian/ngẫu nhiên**: gọi random/clock có thể đổi kết quả dù không ghi bảng.

### 18.1. Side effect có thể làm hàm khó dự đoán

Một hàm “tính giá” nhưng âm thầm ghi log và gọi dịch vụ ngoài sẽ khó benchmark, retry và test hơn hàm thuần chỉ phụ thuộc arguments.

### 18.2. Phân biệt observable result với mutable state

Hàm đọc bảng có thể là STABLE và trả kết quả khác giữa các statements; đây là dependency vào database state, không nhất thiết là **DML side effect**. Nhưng nó cũng không phải IMMUTABLE.

### 18.3. Ranh giới transaction là chìa khóa

Không phải tất cả side effects đều được rollback theo transaction PostgreSQL. Cần biết chính xác thành phần nào atomic với dữ liệu chính.

## 19. DML trong function vẫn nằm trong transaction của caller

Ví dụ:

~~~sql
CREATE FUNCTION audit.record_event(
    p_type TEXT,
    p_detail TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
    v_id BIGINT;
BEGIN
    INSERT INTO audit.events(event_type, detail)
    VALUES (p_type, p_detail)
    RETURNING event_id INTO v_id;

    RETURN v_id;
END;
$$;
~~~

### 19.1. Không commit riêng trong function

Nếu function được gọi từ một transaction, hàng được INSERT sẽ commit hoặc rollback cùng transaction tương ứng (với các quy tắc PostgreSQL).

### 19.2. Một ví dụ rollback

~~~sql
BEGIN;

SELECT audit.record_event(
    'demo',
    'row này chỉ thuộc transaction thử nghiệm'
);

ROLLBACK;
~~~

Row INSERT vào `audit.events</BT> sẽ không còn sau rollback.

### 19.3. Sequence có thể vẫn tăng

Nếu `event_id</BT> được tạo bằng identity/sequence, việc gọi `nextval</BT> để cấp ID thường **không rollback** theo row transaction. Sau ROLLBACK, sequence có thể đã tiến và ID tiếp theo bị nhảy.

### 19.4. Vì sao quan trọng?

Nếu business logic dựa vào “ID liên tiếp không có lỗ hổng” hoặc dùng ID sequence như số tiền/tổng giao dịch, đây là thiết kế sai. Sequence dành cho tạo định danh, không phải sổ kế toán liên tục không khuyết.

## 20. Function không được BEGIN/COMMIT/ROLLBACK giao dịch tùy ý

PL/pgSQL **function** được gọi trong một statement hoặc expression không có quyền tự kết thúc transaction của caller bằng `COMMIT</BT>/`ROLLBACK</BT>.

~~~sql
-- KHÔNG PHẢI MẪU HỢP LỆ CHO FUNCTION
CREATE FUNCTION demo_wrong_transaction()
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    COMMIT;
END;
$$;
~~~

Đoạn này là ví dụ **không chạy như một transaction-control function hợp lệ**. Không copy vào production.

### 20.1. Vì sao?

Một statement PostgreSQL có transaction boundary được quản lý ở cấp transaction/session. Hàm bên trong không được tự commit nửa công việc trong khi câu SQL gọi nó chưa kết thúc.

### 20.2. Nếu muốn atomic nhiều bước

Hãy để caller bắt đầu transaction và gọi các SQL/function statements thích hợp:

~~~sql
BEGIN;
-- Các bước cần atomic
COMMIT;
~~~

Hoặc gói DML trong function/procedure **không tự commit**, để transaction bên ngoài quyết định commit/rollback.

### 20.3. Nếu muốn batch commit thành nhiều transaction

Đánh giá procedure/DO và quy tắc CALL đặc biệt, hoặc orchestrate từ ứng dụng theo batches với transaction boundary rõ. Không mô phỏng autonomous transaction bằng trick thiếu kiểm soát.

## 21. Procedure và quyền kiểm soát transaction

Từ PostgreSQL 11, `CREATE PROCEDURE</BT> kết hợp `CALL</BT> cho phép transaction control trong những hoàn cảnh cụ thể.

### 21.1. Procedure thông thường

~~~sql
CREATE PROCEDURE orders.mark_paid(
    p_order_id BIGINT
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE orders.orders
    SET status = 'paid'
    WHERE order_id = p_order_id
      AND status = 'new';
END;
$$;
~~~

Lệnh này tự nó **không có COMMIT**. Caller có thể kiểm soát transaction, và thủ tục chạy trong transaction context phù hợp.

### 21.2. Procedure có COMMIT bên trong

Trong điều kiện được PostgreSQL hỗ trợ, một top-level CALL không nằm trong explicit transaction block có thể thực hiện transaction control qua procedure:

~~~sql
CREATE PROCEDURE audit.commit_one_event(
    p_detail TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO audit.events(event_type, detail)
    VALUES ('procedure_demo', p_detail);

    COMMIT;
END;
$$;
~~~

Đây là ví dụ chuyên biệt, **không phải khuyến nghị mặc định**.

### 21.3. Điều kiện quan trọng

Transaction control trong procedure phụ thuộc:

- CALL/DO invocation context.
- Không bị đặt trong explicit transaction block không cho phép.
- Các quy tắc chuỗi CALL/DO được hỗ trợ, không có lời gọi trung gian vi phạm.
- Không dùng SECURITY DEFINER hoặc SET clause theo những giới hạn PostgreSQL có liên quan.
- Không đặt transaction end trong phần EXCEPTION block đang có subtransaction chưa kết thúc.
- PostgreSQL version hỗ trợ.

### 21.4. Khi nào CALL ... COMMIT có thể lỗi?

Nếu client đã:

~~~sql
BEGIN;
CALL audit.commit_one_event('abc');
COMMIT;
~~~

thủ tục tự COMMIT bên trong thường bị từ chối vì nó chạy trong explicit transaction block không cho phép transaction control. Trong JDBC, `autoCommit=false</BT> có thể đặt lệnh trong transaction context tương đương.

### 21.5. Đừng biến mọi procedure thành commit manager

Nhiều business workflows cần caller phối hợp nhiều thao tác atomic. Một procedure âm thầm commit có thể phá hợp đồng transaction của application service. Chỉ dùng transaction control nội bộ khi thực sự cần và đã thiết kế API tương ứng.

## 22. EXCEPTION và subtransaction overhead

Trong PL/pgSQL, block có `EXCEPTION</BT> được xử lý với cơ chế subtransaction, tạo thêm overhead.

~~~sql
CREATE FUNCTION orders.try_mark_paid(
    p_order_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
VOLATILE
AS $$
BEGIN
    BEGIN
        UPDATE orders.orders
        SET status = 'paid'
        WHERE order_id = p_order_id
          AND status = 'new';
        RETURN FOUND;
    EXCEPTION WHEN unique_violation THEN
        RETURN FALSE;
    END;
END;
$$;
~~~

Ví dụ minh họa cách exception block hoạt động; **unique_violation** không nhất thiết là lỗi thông thường của UPDATE này. Không dùng mẫu bắt sai lỗi trong production.

### 22.1. EXCEPTION không miễn phí

Một block có exception handler có thể tốn chi phí thiết lập/điều phối subtransaction ngay cả khi không có lỗi. Không bọc mỗi hàng trong EXCEPTION nếu có thể xử lý bằng SQL constraints và `ON CONFLICT</BT> đúng semantics.

### 22.2. Khi xảy ra lỗi

Các thay đổi database bên trong block bị bắt lỗi có thể được rollback theo subtransaction tương ứng; biến PL/pgSQL và các side effects ngoài transaction không nhất thiết trở về trạng thái trước block.

### 22.3. Không bắt WHEN OTHERS rồi nuốt mọi lỗi

Làm vậy có thể che dữ liệu sai, deadlocks, permission errors và lỗi quan trọng. Nếu bắt lỗi, phân loại lỗi mong đợi, ghi context và quyết định rõ có retry/propagate hay không.

### 22.4. Khi nào nên dùng EXCEPTION?

Khi cần chuyển một số lỗi database thành business outcome có kiểm soát và không có cách set-based/constraint conflict handling tốt hơn. Với error path hiếm, overhead có thể chấp nhận được; với hot per-row path, cần đo cẩn thận.

## 23. DML side effects trong SELECT: một anti-pattern dễ bị bỏ sót

~~~sql
SELECT
    order_id,
    audit.record_event('read_order', order_id::text)
FROM orders.orders
WHERE status = 'paid'
LIMIT 100;
~~~

### 23.1. Hậu quả

Truy vấn “đọc” bây giờ có thể INSERT audit rows. Nếu client retry SELECT, bạn có thể ghi log nhiều lần. Nếu planner/executor thay đổi evaluation context, không nên coi thứ tự và số lần side-effect calls là một business guarantee ngoài điều được tài liệu xác định.

### 23.2. Đọc không nên âm thầm sửa nghiệp vụ

Một API GET hoặc báo cáo SELECT thường nên có side-effect contract rõ. Nếu cần audit truy cập, hãy dùng logging/telemetry thích hợp thay vì tùy tiện chèn INSERT vào biểu thức SELECT.

### 23.3. Khi vẫn có lý do dùng function DML

Một function `record_payment(...)</BT> được gọi rõ ràng như command có thể hợp lý, nếu transaction, idempotency và grants được kiểm soát. Quan trọng là **người gọi biết đây là thao tác ghi**.

### 23.4. Đừng dựa vào LIMIT như bộ đếm chính xác side effects

LIMIT giới hạn rows kết quả, không phải một hợp đồng độc lập để bảo đảm hàm có tác dụng phụ được gọi đúng bao nhiêu lần trong mọi kế hoạch SQL. Thiết kế thao tác ghi thành statement/procedure tường minh khi cần exactly-once business effect.

## 24. Transaction rollback không bao phủ mọi side effects

### 24.1. Table DML

INSERT/UPDATE/DELETE trong cùng transaction thường được rollback nếu transaction rollback.

### 24.2. Sequence

`nextval</BT> và một số thao tác sequence state không rollback như table rows. Sequence gaps là bình thường.

### 24.3. NOTIFY

`NOTIFY</BT> bên trong transaction có semantics giao thông báo gắn với commit; không đồng nghĩa gửi external email/webhook vĩnh viễn khi statement được thực thi.

### 24.4. External I/O

Nếu một extension hoặc external helper thực hiện HTTP request, gửi email hoặc ghi một hệ thống bên ngoài, rollback transaction PostgreSQL **không tự hoàn tác** external side effect đó.

### 24.5. Advisory locks

Transaction-level advisory locks và session-level advisory locks có lifetime khác nhau. Session-level advisory locks có thể còn giữ sau khi transaction rollback; cần chọn đúng loại và đảm bảo release phù hợp.

### 24.6. Kết luận nghiệp vụ

Nếu side effect phải cùng commit với transaction, nên thiết kế **transactional outbox** trong PostgreSQL rồi một worker đáng tin cậy phát sự kiện ra bên ngoài sau commit, thay vì gọi dịch vụ ngoài tùy ý bên trong transaction.

## 25. Transactional outbox: phương án khi cần phát sự kiện

Giả sử cập nhật order và gửi `OrderPaid</BT> đến hệ thống khác. Dùng outbox:

~~~text
Transaction PostgreSQL:
  UPDATE orders SET status='paid'
  INSERT INTO event_outbox(...)
  COMMIT
                |
                v
Worker ngoài database đọc outbox
  -> gửi message / HTTP
  -> đánh dấu đã xử lý / retry
~~~

### 25.1. Atomic phần ghi trong database

Order update và outbox INSERT cùng transaction; nếu rollback, cả hai thay đổi dữ liệu không commit.

### 25.2. Message delivery không tự exactly-once

Worker có thể gửi message rồi lỗi trước khi đánh dấu đã gửi, sau đó retry. Hệ thống nhận cần xử lý idempotency/deduplication theo event ID.

### 25.3. Vì sao tốt hơn gọi HTTP trong function?

Network latency/failure ngoài PostgreSQL không giữ database transaction mở không cần thiết; rollback và retry rules minh bạch hơn.

### 25.4. Outbox cũng có giá

Cần worker, polling/CDC, retention, monitoring, retry/dead-letter và dữ liệu idempotency. Nó là giải pháp có chủ đích cho side effects phân tán, không phải một phép màu miễn phí.

## 26. Security Invoker và Security Definer

PostgreSQL functions mặc định chạy theo **SECURITY INVOKER** trừ khi được khai báo khác. Với `SECURITY DEFINER</BT>, code có thể thực thi với quyền của function owner theo quy tắc phù hợp.

### 26.1. SECURITY INVOKER

Caller cần những quyền phù hợp cho thao tác được thực hiện. Phù hợp khi muốn RLS/grants của caller được tôn trọng theo cách rõ ràng.

### 26.2. SECURITY DEFINER

Có thể tạo một interface cho phép caller thực hiện một thao tác hẹp mà không cần quyền rộng trên bảng nền.

~~~sql
CREATE FUNCTION api.safe_mark_paid(
    p_order_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app_private, pg_temp
AS $$
BEGIN
    UPDATE app_private.orders
    SET status = 'paid'
    WHERE order_id = p_order_id
      AND status = 'new';

    RETURN FOUND;
END;
$$;
~~~

Đây là ví dụ kiến trúc yêu cầu schemas/tables/role phù hợp; không chạy trực tiếp nếu chưa thiết kế quyền.

### 26.3. Search path an toàn

Với SECURITY DEFINER, chỉ đưa **trusted schemas** vào `search_path</BT>; đặt `pg_temp</BT> sau cùng theo hướng dẫn an toàn tương ứng; schema-qualify tables/functions quan trọng. Tránh schema mà user không tin cậy có quyền CREATE objects, nếu có thể ảnh hưởng name resolution.

### 26.4. Owner phải có quyền tối thiểu

Không dùng một superuser làm owner cho mọi SECURITY DEFINER function chỉ để tránh cấu hình grants. Tạo dedicated role với đúng quyền dữ liệu cần thiết.

### 26.5. GRANT EXECUTE rõ ràng

PostgreSQL thường có mặc định EXECUTE cho PUBLIC trên functions mới theo quy tắc privileges. Với function nhạy cảm, tạo và REVOKE/GRANT trong cùng transaction để không có khoảng hở truy cập không mong muốn.

### 26.6. RLS cần được thử trong đúng role

Owner hoặc role có bypass privileges có thể chịu RLS behavior khác user bình thường. SECURITY DEFINER có thể thay đổi cách policies được áp dụng. Cần integration tests dưới role thực tế, không chỉ superuser.

## 27. Quyền EXECUTE là một phần API

Một cách vận hành:

~~~sql
BEGIN;

CREATE FUNCTION app_private.log_action(
    p_action TEXT
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app_private, pg_temp
AS $$
BEGIN
    INSERT INTO app_private.audit_events(action_name)
    VALUES (p_action);
END;
$$;

REVOKE ALL
ON FUNCTION app_private.log_action(TEXT)
FROM PUBLIC;

GRANT EXECUTE
ON FUNCTION app_private.log_action(TEXT)
TO app_writer;

COMMIT;
~~~

Ví dụ yêu cầu `app_private.audit_events</BT> và role `app_writer</BT> tồn tại; ở đây chỉ minh họa quyền.

### 27.1. Cần USAGE trên schema

Role gọi function còn cần quyền truy cập schema theo mô hình PostgreSQL. GRANT EXECUTE trên function không tự thay mọi schema privileges.

### 27.2. Một function có quyền ghi là interface nhạy cảm

Nếu chỉ cấp EXECUTE vào function DML, phải kiểm soát input, tenant ownership, state transitions và business constraints, để user không lợi dụng function làm thay đổi rows của tenant khác.

### 27.3. Không dùng function như cách vượt qua mọi policy

SECURITY DEFINER là công cụ quyền đặc biệt, không phải lối tắt để né phân quyền. Audit, tests và review đường đi của dữ liệu là bắt buộc trong thiết kế thật.

## 28. Logic nào nên nằm trong constraint thay vì function?

Nhiều quy tắc **toàn vẹn đơn giản và phổ quát** nên dùng constraints:

~~~sql
CREATE TABLE example_items (
    item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    sku TEXT NOT NULL UNIQUE,
    customer_id BIGINT REFERENCES customers(customer_id)
);
~~~

### 28.1. Vì sao constraint tốt?

- Dù Java, ETL, BI tool hay script nhập dữ liệu, database đều bảo vệ invariant.
- Constraints có semantics concurrency/locking chuyên dụng.
- Dễ để planner và schema tools hiểu hơn một function kiểm tra thủ công.
- Giảm rủi ro application bỏ quên validate.

### 28.2. Không thay unique bằng function SELECT COUNT

Một function “kiểm tra SKU chưa tồn tại rồi INSERT” có race khi hai transactions đồng thời chạy. Dùng UNIQUE constraint và xử lý conflict theo nghiệp vụ.

### 28.3. Không thay FK bằng function exists check

Kiểm tra trước khi INSERT không tự bảo vệ khỏi concurrent delete/update giữa bước check và bước insert. Dùng FOREIGN KEY nếu quan hệ nằm trong khả năng ràng buộc.

### 28.4. CHECK có giới hạn

CHECK phù hợp bất biến theo row và các biểu thức được hỗ trợ. Không dùng function đọc bảng khác trong CHECK rồi nghĩ PostgreSQL sẽ tự bảo đảm mọi cross-row invariant an toàn ở mọi transaction.

## 29. Trigger function: khi nào có tác dụng và rủi ro gì?

Trigger là một cách PostgreSQL tự gọi function khi có sự kiện trên bảng.

### 29.1. Trường hợp hữu ích

- Cập nhật audit fields.
- Ghi outbox cùng transaction.
- Bảo trì dữ liệu dẫn xuất mà application không được bỏ sót.
- Từ chối một số chuyển trạng thái trong phạm vi cần thiết.

### 29.2. Chi phí per-row trigger

Một `FOR EACH ROW</BT> trigger trên bulk INSERT 1 triệu hàng có thể chạy function 1 triệu lần. Nếu mỗi invocation còn query nhiều bảng, tổng chi phí lớn.

### 29.3. Khi dùng statement-level triggers

Nếu công việc có thể xử lý theo tập, xem `FOR EACH STATEMENT</BT> triggers và transition tables ở các trường hợp được PostgreSQL hỗ trợ, thay vì ghi từng hàng mà không cần thiết.

### 29.4. Không ẩn các external effects trong trigger

Gửi HTTP, email hoặc kết nối hệ khác trong trigger làm database writes phụ thuộc network và có side effects không rollback như table rows. Outbox hoặc asynchronous worker thường dễ kiểm soát hơn.

### 29.5. Tránh trigger “ma thuật”

Một INSERT đơn giản có thể làm hàng chục thao tác ngầm do trigger cascade. Cần tài liệu hóa side effects và đo chi phí thực tế trước khi chấp nhận.

## 30. Lab: chuẩn bị dữ liệu để đo chi phí gọi hàm

Phần lab dùng schema riêng `fn_cost_lab</BT> trong **database thử nghiệm**, không chạy trên production. Nếu schema đã tồn tại, chọn schema khác thay vì xóa dữ liệu của người khác.

### 30.1. Tạo schema

~~~sql
CREATE SCHEMA fn_cost_lab;
~~~

### 30.2. Bảng khách hàng

~~~sql
CREATE TABLE fn_cost_lab.customers (
    customer_id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    tier TEXT NOT NULL
        CHECK (tier IN ('regular', 'premium')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

### 30.3. Bảng đơn hàng

~~~sql
CREATE TABLE fn_cost_lab.orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES fn_cost_lab.customers(customer_id),
    amount NUMERIC(12,2) NOT NULL CHECK (amount >= 0),
    status TEXT NOT NULL
        CHECK (status IN ('new', 'paid', 'cancelled', 'archived')),
    created_at TIMESTAMPTZ NOT NULL
);
~~~

### 30.4. Bảng audit

~~~sql
CREATE TABLE fn_cost_lab.audit_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_type TEXT NOT NULL,
    detail TEXT NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
~~~

### 30.5. Nạp 1.000 khách hàng

~~~sql
INSERT INTO fn_cost_lab.customers (
    customer_id, name, tier
)
SELECT
    n,
    'Customer ' || n::text,
    CASE
        WHEN n % 10 = 0 THEN 'premium'
        ELSE 'regular'
    END
FROM generate_series(1, 1000) AS gs(n);
~~~

### 30.6. Nạp 100.000 đơn hàng

~~~sql
INSERT INTO fn_cost_lab.orders (
    order_id, customer_id, amount, status, created_at
)
SELECT
    n,
    ((n - 1) % 1000) + 1,
    ((n % 997) + 1)::numeric(12,2),
    CASE
        WHEN n % 13 = 0 THEN 'cancelled'
        WHEN n % 3  = 0 THEN 'paid'
        ELSE 'new'
    END,
    TIMESTAMPTZ '2026-01-01 00:00:00+00'
       + n * INTERVAL '1 minute'
FROM generate_series(1, 100000) AS gs(n);
~~~

### 30.7. Index và thống kê

~~~sql
CREATE INDEX orders_customer_status_idx
ON fn_cost_lab.orders(customer_id, status);

ANALYZE fn_cost_lab.customers;
ANALYZE fn_cost_lab.orders;
~~~

Dữ liệu được tạo theo modulo để dễ lặp lại. Đây không phải workload production đại diện; số liệu hiệu năng đo được chỉ có giá trị trong môi trường và dữ liệu thử nghiệm.

## 31. Lab: hàm SQL thuần để tính toán

Tạo hàm giảm giá:

~~~sql
CREATE FUNCTION fn_cost_lab.discounted_amount(
    p_amount NUMERIC,
    p_discount_rate NUMERIC
)
RETURNS NUMERIC
LANGUAGE SQL
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
    SELECT round(p_amount * (1 - p_discount_rate), 2);
$$;
~~~

### 31.1. Kiểm tra một lần gọi

~~~sql
SELECT fn_cost_lab.discounted_amount(100.00, 0.10)
    AS after_discount;
~~~

Kỳ vọng là `90.00</BT> theo kiểu numeric tương ứng.

### 31.2. Dùng trong truy vấn tập hàng

~~~sql
SELECT
    order_id,
    amount,
    fn_cost_lab.discounted_amount(amount, 0.10)
        AS after_discount
FROM fn_cost_lab.orders
WHERE status = 'paid'
ORDER BY order_id
LIMIT 20;
~~~

### 31.3. Đo trên nhiều rows

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    SUM(fn_cost_lab.discounted_amount(amount, 0.10))
FROM fn_cost_lab.orders;
~~~

### 31.4. So với biểu thức trực tiếp

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT SUM(round(amount * (1 - 0.10::numeric), 2))
FROM fn_cost_lab.orders;
~~~

Hai cách biểu đạt cùng ý tưởng tính toán. Do hàm SQL đơn giản có thể inline, không được khẳng định luôn có một khoản overhead cố định lớn.

## 32. Lab: cùng phép tính bằng PL/pgSQL

~~~sql
CREATE FUNCTION fn_cost_lab.discounted_amount_pl(
    p_amount NUMERIC,
    p_discount_rate NUMERIC
)
RETURNS NUMERIC
LANGUAGE plpgsql
IMMUTABLE
STRICT
PARALLEL SAFE
AS $$
BEGIN
    RETURN round(p_amount * (1 - p_discount_rate), 2);
END;
$$;
~~~

### 32.1. Đo cùng dataset

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    SUM(fn_cost_lab.discounted_amount_pl(amount, 0.10))
FROM fn_cost_lab.orders;
~~~

### 32.2. Mục tiêu so sánh

Quan sát total execution time và plan shape qua nhiều lần chạy trên cùng dữ liệu; PL/pgSQL được gọi qua runtime function thay vì inline như một số SQL functions.

### 32.3. Thận trọng với cache và JIT

Lần chạy đầu có thể gồm warm-up, compilation/planning và I/O khác nhau. Nếu JIT được bật, timing có thể bị ảnh hưởng. Không dùng một cặp số đo duy nhất để khẳng định “PL/pgSQL chậm X lần” trong mọi hệ thống.

### 32.4. Cách chọn

Với phép toán rất đơn giản và gọi trên nhiều rows, biểu thức SQL hoặc SQL function dễ inline thường đáng thử. Với business workflow nhiều bước, PL/pgSQL có thể dễ duy trì hơn dù overhead cao hơn.

## 33. Lab: một PL/pgSQL function query bảng mỗi lần gọi

Tạo function đếm đơn đã thanh toán của một customer:

~~~sql
CREATE FUNCTION fn_cost_lab.paid_order_count_pl(
    p_customer_id BIGINT
)
RETURNS BIGINT
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_count BIGINT;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM fn_cost_lab.orders
    WHERE customer_id = p_customer_id
      AND status = 'paid';

    RETURN v_count;
END;
$$;
~~~

### 33.1. Gọi một khách

~~~sql
SELECT fn_cost_lab.paid_order_count_pl(42);
~~~

Có thể là một operation chấp nhận được nếu tần suất gọi thấp.

### 33.2. Gọi 500 khách

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    c.customer_id,
    fn_cost_lab.paid_order_count_pl(c.customer_id)
        AS paid_count
FROM fn_cost_lab.customers AS c
WHERE c.customer_id <= 500
ORDER BY c.customer_id;
~~~

### 33.3. Mẫu N+1 được đẩy vào database

Query ngoài trả 500 khách, nhưng function có thể phải chạy một câu SQL riêng cho từng customer. Index trên `orders(customer_id,status)</BT> giúp mỗi truy vấn nội bộ, nhưng vẫn không làm nó chỉ còn một lần aggregate.

### 33.4. EXPLAIN ngoài có thể giấu SQL nội bộ

Plan của SELECT ngoài không nhất thiết hiển thị chi tiết plan SQL bên trong PL/pgSQL function. Đừng kết luận function rẻ chỉ vì query ngoài hiện một Index Scan đơn giản trên customers.

### 33.5. So tổng chi phí

Có thể đo bằng thống kê function hoặc nested-statement instrumentation phù hợp để biết số invocation và thời gian SQL nội bộ, rồi so với phương án set-based ở phần kế tiếp.

## 34. Lab: viết lại thành một truy vấn set-based

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    c.customer_id,
    COUNT(o.order_id) AS paid_count
FROM fn_cost_lab.customers AS c
LEFT JOIN fn_cost_lab.orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'paid'
WHERE c.customer_id <= 500
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

### 34.1. Vì sao thường đáng thử?

Planner nhìn được JOIN, cardinality, indexes và aggregate của toàn tập. Nó có thể chọn hash/merge/nested-loop JOIN cùng aggregate phù hợp thay vì một câu SELECT ẩn bên trong function cho từng row.

### 34.2. Kết quả customer không có đơn

`COUNT(o.order_id)</BT> cho 0 nếu không có order paid vì những null-extended rows từ LEFT JOIN không có non-NULL order_id.

### 34.3. Không phải lúc nào JOIN cũng luôn nhanh hơn

Với một customer duy nhất, một query theo index có thể rẻ. Set-based approach thường có tiềm năng lớn khi xử lý nhiều customers, nhưng phải đo workload cụ thể.

### 34.4. Một phương án pre-aggregate

~~~sql
SELECT
    c.customer_id,
    COALESCE(p.paid_count, 0) AS paid_count
FROM fn_cost_lab.customers AS c
LEFT JOIN (
    SELECT customer_id, COUNT(*) AS paid_count
    FROM fn_cost_lab.orders
    WHERE status = 'paid'
    GROUP BY customer_id
) AS p
  ON p.customer_id = c.customer_id
WHERE c.customer_id <= 500
ORDER BY c.customer_id;
~~~

Tùy dữ liệu, planner có thể aggregate nhiều customers ngoài phạm vi, hoặc đẩy lọc/biến đổi. Đo EXPLAIN để so với LEFT JOIN trực tiếp.

## 35. Lab: function thực hiện DML có kiểm soát

Tạo một command function để chuyển order từ `new</BT> sang `paid</BT>:

~~~sql
CREATE FUNCTION fn_cost_lab.mark_order_paid(
    p_order_id BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
AS $$
BEGIN
    UPDATE fn_cost_lab.orders
    SET status = 'paid'
    WHERE order_id = p_order_id
      AND status = 'new';

    RETURN FOUND;
END;
$$;
~~~

### 35.1. Tại sao WHERE có status?

Đây là một dạng **conditional state transition**. Hai requests cùng cố cập nhật order đang new không nên cùng nghĩ mình đã chuyển thành công. UPDATE cùng WHERE và row locking/MVCC giúp chỉ cập nhật row thỏa trạng thái tại thời điểm xử lý theo semantics database.

### 35.2. Thử trong transaction và rollback

~~~sql
BEGIN;

SELECT fn_cost_lab.mark_order_paid(10) AS changed;

SELECT order_id, status
FROM fn_cost_lab.orders
WHERE order_id = 10;

ROLLBACK;
~~~

Order 10 trong dữ liệu sinh mẫu ban đầu có status new. Sau ROLLBACK, thay đổi trạng thái không commit.

### 35.3. RETURN FOUND không phải bộ đếm tuyệt đối cho mọi logic

Ở đây `FOUND</BT> phản ánh câu UPDATE vừa thực thi trong PL/pgSQL. Nếu thêm nhiều câu SQL khác vào trước RETURN, cần lưu kết quả vào biến hoặc dùng `GET DIAGNOSTICS ... ROW_COUNT</BT> theo đúng thời điểm.

### 35.4. Không thay được business authorization

Function SECURITY INVOKER này không kiểm tra tenant/owner. Trong hệ thống thật phải bổ sung quyền và scope đúng (ví dụ tenant_id/role hoặc RLS). Không đưa function này vào production nguyên trạng như một API thanh toán đầy đủ.

## 36. Lab: side effect và rollback với audit table

Tạo function ghi audit:

~~~sql
CREATE FUNCTION fn_cost_lab.record_event(
    p_event_type TEXT,
    p_detail TEXT
)
RETURNS BIGINT
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
    v_event_id BIGINT;
BEGIN
    INSERT INTO fn_cost_lab.audit_events(
        event_type, detail
    )
    VALUES (p_event_type, p_detail)
    RETURNING event_id INTO v_event_id;

    RETURN v_event_id;
END;
$$;
~~~

### 36.1. Ghi và rollback

~~~sql
BEGIN;

SELECT fn_cost_lab.record_event(
    'lab_demo',
    'this row should roll back'
) AS generated_id;

SELECT COUNT(*)
FROM fn_cost_lab.audit_events
WHERE event_type = 'lab_demo';

ROLLBACK;
~~~

### 36.2. Kiểm tra sau rollback

~~~sql
SELECT COUNT(*)
FROM fn_cost_lab.audit_events
WHERE event_type = 'lab_demo';
~~~

Nếu không có sự kiện cùng loại từ trước, kỳ vọng 0. Nhưng sequence cấp event_id có thể đã tăng, dù row bị rollback.

### 36.3. Đừng suy ra gap trong sequence là lỗi

Sequence có thể có gaps do rollback, caching, failover và concurrency. Muốn số thứ tự chứng từ liên tục theo pháp lý cần quy trình khác và transaction consistency rõ.

### 36.4. Side effect function có tên rõ

`record_event</BT> biểu thị ghi dữ liệu. Tên function như `get_customer_name</BT> nhưng âm thầm INSERT log sẽ làm contract khó hiểu và khó retry.

## 37. Lab: procedure cho workflow nhiều bước

Tạo procedure chuyển order sang paid và ghi audit cùng transaction:

~~~sql
CREATE PROCEDURE fn_cost_lab.confirm_order(
    p_order_id BIGINT
)
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE fn_cost_lab.orders
    SET status = 'paid'
    WHERE order_id = p_order_id
      AND status = 'new';

    IF NOT FOUND THEN
        RAISE EXCEPTION
            'Order % not found or not in new state',
            p_order_id;
    END IF;

    INSERT INTO fn_cost_lab.audit_events(
        event_type, detail
    )
    VALUES ('order_paid', p_order_id::text);
END;
$$;
~~~

### 37.1. Gọi qua CALL

~~~sql
BEGIN;

CALL fn_cost_lab.confirm_order(10);

SELECT order_id, status
FROM fn_cost_lab.orders
WHERE order_id = 10;

ROLLBACK;
~~~

Procedure không tự commit nên các thay đổi rollback theo transaction caller.

### 37.2. Vì sao sử dụng transaction ngoài?

Trong hệ thống thật, application có thể cần thao tác thêm như ghi payment record hoặc cập nhật ledger trong cùng transaction. Procedure tự commit giữa chừng có thể phá atomicity đó.

### 37.3. Khi nào nên viết UPDATE ... RETURNING?

Nếu workflow chỉ có một UPDATE và caller chỉ cần biết có row nào thay đổi, một câu:

~~~sql
UPDATE fn_cost_lab.orders
SET status = 'paid'
WHERE order_id = 10
  AND status = 'new'
RETURNING order_id, status;
~~~

có thể đơn giản hơn procedure. **Không tạo stored procedure nếu một DML statement rõ ràng đã đáp ứng đầy đủ contract.**

### 37.4. Idempotency cần thiết kế riêng

Nếu request thanh toán được retry, procedure có thể báo “không còn new” thay vì coi lần thứ hai đã hoàn tất. Tùy API, có thể cần idempotency key và bảng request/ledger riêng; không chỉ đổi RETURN FALSE thành TRUE mà bỏ qua phân biệt trạng thái.

## 38. Transaction control trong procedure: lab nâng cao

Chỉ thực hiện phần này khi dùng PostgreSQL 11+ và đã hiểu điều kiện CALL.

~~~sql
CREATE PROCEDURE fn_cost_lab.commit_marker(
    p_detail TEXT
)
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO fn_cost_lab.audit_events(
        event_type, detail
    )
    VALUES ('commit_marker', p_detail);

    COMMIT;
END;
$$;
~~~

### 38.1. CALL ở top level

Khi không nằm trong explicit transaction block và không vi phạm các giới hạn liên quan, câu:

~~~sql
CALL fn_cost_lab.commit_marker('top-level call');
~~~

có thể cho procedure thực hiện COMMIT nội bộ.

### 38.2. CALL trong transaction block

~~~sql
-- MINH HỌA LỖI: ĐỪNG CHẠY NHƯ TRANSACTION THÀNH CÔNG
BEGIN;
CALL fn_cost_lab.commit_marker('inside transaction');
COMMIT;
~~~

PostgreSQL thường từ chối transaction control bên trong procedure trong hoàn cảnh này. Sau lỗi, cần ROLLBACK transaction bị aborted.

### 38.3. JDBC autocommit

Nếu muốn thử semantics top-level CALL, kiểm tra cách JDBC driver quản lý autocommit và transaction. Với `autoCommit=false</BT>, CALL thường nằm trong transaction do client mở.

### 38.4. Không dùng SECURITY DEFINER cho procedure này

Các procedure SECURITY DEFINER hoặc có SET clauses liên quan bị hạn chế về transaction control. Không kết hợp hai nhóm tính năng mà không kiểm tra quy tắc PostgreSQL.

### 38.5. Hợp đồng nên nói rõ ai sở hữu transaction

Một API procedure cho phép COMMIT nội bộ khác rất xa một procedure chỉ thực hiện công việc trong transaction của caller. Người dùng API phải biết điều này trước khi gọi.

## 39. Đọc EXPLAIN đúng khi có function

Một câu lệnh:

~~~sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    c.customer_id,
    fn_cost_lab.paid_order_count_pl(c.customer_id)
FROM fn_cost_lab.customers AS c
WHERE c.customer_id <= 500;
~~~

### 39.1. Plan ngoài không phải toàn bộ plan trong function

PL/pgSQL statements bên trong có thể được thực thi qua SPI và không hiển thị như các child nodes trong một EXPLAIN của outer query. Cần chú ý instrumentation bổ sung khi muốn đo tổng số nested statements.

### 39.2. Rows estimated và actual

Nếu planner ước lượng 10 rows nhưng thực tế trả 1 triệu, có thể có vấn đề statistics/selectivity hoặc function ROWS cost. Không kết luận tốc độ chỉ từ cost số tuyệt đối.

### 39.3. Buffers

`BUFFERS</BT> giúp đọc shared hit/read và các buffer types phù hợp. Tuy nhiên, nested SQL trong function có thể khiến việc diễn giải tổng công việc từ plan ngoài không đầy đủ như khi mọi logic được viết trực tiếp set-based.

### 39.4. Planning time vs execution time

Dynamic SQL, nhiều lần gọi và query phức tạp có thể tăng planning/execution ở những vị trí khác nhau. Tránh nhầm `Planning Time</BT> của outer query với tổng planning của mọi internal statements.

### 39.5. EXPLAIN ANALYZE thực thi DML

Nếu chạy `EXPLAIN ANALYZE</BT> cho UPDATE/CALL thông qua wrappers, transaction side effects có thể thật sự xảy ra. Dùng môi trường thử nghiệm hoặc transaction có rollback đúng điều kiện; không chỉ xem đó là mô phỏng.

## 40. Theo dõi function bằng thống kê PostgreSQL

### 40.1. pg_stat_user_functions

Khi cấu hình `track_functions</BT> cho phép theo dõi loại function tương ứng, view `pg_stat_user_functions</BT> cung cấp counters như calls, total_time và self_time cho user-defined functions.

~~~sql
SELECT
    schemaname,
    funcname,
    calls,
    total_time,
    self_time
FROM pg_stat_user_functions
WHERE schemaname = 'fn_cost_lab'
ORDER BY total_time DESC;
~~~

### 40.2. track_functions

Các lựa chọn thường gồm `none</BT>, `pl</BT>, `all</BT> theo PostgreSQL; cấu hình phải phù hợp và có quyền thay đổi. Không bật instrumenting rộng trên production mà không đánh giá overhead/monitoring policy.

### 40.3. Self time vs total time

`self_time</BT> và `total_time</BT> có semantics khác về lời gọi lồng nhau. Không xem số liệu là tổng CPU chính xác của toàn database nếu chỉ theo dõi một loại functions.

### 40.4. Inlined functions có thể không xuất hiện như calls độc lập

Nếu một SQL function được planner inline, counters kiểu “số lần gọi function” có thể không phản ánh đúng theo cách mong đợi một lời gọi riêng. Đọc dữ liệu thống kê trong bối cảnh plan.

### 40.5. pg_stat_statements

Extension `pg_stat_statements</BT>, nếu được cài và cấu hình, giúp theo dõi SQL statements, số lần thực thi và thời gian theo thống kê tổng hợp. Khả năng track nested statements phụ thuộc cấu hình như `pg_stat_statements.track</BT> và loại statements.

### 40.6. auto_explain

Extension `auto_explain</BT> có thể ghi query plans tự động, kể cả nested statements trong trường hợp được bật cấu hình tương ứng. Đây là công cụ phân tích nâng cao với overhead/log volume cần kiểm soát.

## 41. Dynamic SQL trong PL/pgSQL

PL/pgSQL hỗ trợ:

~~~sql
EXECUTE dynamic_sql_text
USING parameter_value;
~~~

### 41.1. Vì sao dùng?

- Tên bảng/schema cần chọn lúc runtime theo whitelist.
- Cấu trúc điều kiện SELECT thật sự thay đổi.
- Có nhu cầu plan theo cấu trúc/giá trị thay đổi mà SQL tĩnh không phù hợp.

### 41.2. Chi phí

Dynamic EXECUTE thường không hưởng cùng cơ chế cache plan của static PL/pgSQL statements; có thể phải parse/plan cho mỗi lần thực thi.

### 41.3. SQL injection

Không nối thẳng input người dùng vào SQL text. Dùng `format('%I', identifier)</BT> cho identifiers sau validation, `USING</BT> cho data values khi phù hợp, và whitelist đối tượng được phép.

### 41.4. Không dùng EXECUTE khi SQL cố định

Một câu SQL tĩnh trong PL/pgSQL thường dễ hiểu và có khả năng reuse plan hơn. Viết `EXECUTE 'SELECT ...'</BT> cho query không thay đổi có thể chỉ làm phức tạp và tốn thêm planning.

### 41.5. Quyền và search_path

Dynamic SQL trong SECURITY DEFINER function đặc biệt nhạy cảm. Phải kiểm soát cả identifiers, search_path và dữ liệu caller nhập vào, không coi parameterization của values là đủ nếu cho caller chọn table names tùy ý.

## 42. Sự khác nhau giữa tính toán ở Java và database

| Tiêu chí | Logic trong PostgreSQL | Logic trong Java/service |
|---|---|---|
| Data locality | Gần bảng/index, giảm truyền dữ liệu thô trong một số trường hợp | Có thể cần fetch dữ liệu qua network |
| Set-based SQL | Planner xử lý tập dữ liệu trực tiếp | Thường phải gửi SQL tới DB để khai thác set-based |
| Transaction | Tích hợp với DML một cluster | Có thể điều phối transaction qua JDBC |
| Scale compute | Dùng CPU/RAM trên DB server, tài nguyên thường đắt và tập trung | Có thể scale service instances độc lập |
| Versioning | Migrations và quyền DB | CI/CD ứng dụng, rolling deploy |
| Portability | Có thể phụ thuộc PostgreSQL/PL/pgSQL | Logic ít lệ thuộc database hơn |
| Observability | Cần SQL/function monitoring | App tracing/profiling thuận tiện |
| Security | EXECUTE, DEFINER/INVOKER, RLS | AuthN/AuthZ và service boundaries |
| External APIs | Không lý tưởng trong transaction | Dễ quản lý client/network/retries |
| Business consistency | Constraint/transaction mạnh cho dữ liệu cùng DB | Cần dùng DB constraints/transaction đúng |
| Testability | Cần test DB tích hợp, fixtures/migrations | Unit tests và mocks thuận tiện |
| Tính tái sử dụng | Nhiều clients SQL cùng gọi một contract | Nhiều services có thể chia sẻ library/API |

### 42.1. Câu hỏi không phải “chọn một bên duy nhất”

Một kiến trúc hợp lý thường chia trách nhiệm:

- Database bảo vệ invariants cốt lõi và chạy set-based operations.
- Java làm orchestration, UI/API validation, external integrations và cross-service workflows.
- Function/procedure gói những thao tác dữ liệu cần atomic/tái sử dụng.
- Outbox/worker kết nối side effects ngoài database.

### 42.2. Tránh duplicate business logic

Nếu giá trị thuế cùng một quy tắc được tính trong Java và PL/pgSQL nhưng triển khai khác nhau, dữ liệu có thể lệch. Hãy chỉ định **nguồn chân lý** rõ cho từng rule và có contract tests giữa các lớp.

## 43. Tiêu chí đặt logic vào database: mức độ gần dữ liệu

Logic có lợi khi ở gần dữ liệu nếu:

- Cần xử lý nhiều rows mà ứng dụng không cần tải chúng ra.
- Có thể viết bằng một hoặc vài SQL statements set-based.
- Cần atomicity cùng dữ liệu trong một PostgreSQL cluster.
- Nhiều clients phải dùng chung một phép kiểm tra/biến đổi.
- Có thể tạo interface SQL ổn định.
- Truy cập các bảng nền cần được kiểm soát qua grants/function API.

### 43.1. Ví dụ tốt: tính tổng qua GROUP BY

Nếu muốn tổng đơn hàng theo customer, nên cho PostgreSQL aggregate; không fetch mọi order về Java chỉ để SUM nếu database có thể làm việc đó hiệu quả.

### 43.2. Ví dụ tốt: state transition atomic

`UPDATE ... WHERE status='new' RETURNING ...</BT> là thao tác thích hợp trong DB vì concurrency/transaction matters.

### 43.3. Ví dụ có thể tốt: bulk normalization

Một `UPDATE ... FROM</BT> hoặc `INSERT ... SELECT</BT> để chuẩn hóa nhiều hàng có thể được database thực thi hiệu quả mà không qua mỗi row về Java.

### 43.4. Không phải mọi validation đều là stored function

Validation định dạng request, UX messages hoặc business orchestration ở service có thể nằm Java; invariants quan trọng vẫn cần được DB bảo vệ bằng constraints/transaction.

## 44. Tiêu chí giữ logic ở application/service

Một số logic thường phù hợp ngoài database hơn:

1. Gọi HTTP/gRPC tới dịch vụ bên thứ ba.
2. Gửi email, webhook, push notification.
3. Xử lý file, PDF, media, object storage.
4. Tính toán CPU-heavy không phụ thuộc dữ liệu DB và có thể scale riêng.
5. Thay đổi nghiệp vụ liên tục, cần A/B rollout theo traffic.
6. Workflow phân tán qua nhiều hệ thống, cần saga/idempotency.
7. Tính toán cần thư viện Java chuyên biệt hoặc GPU/ML.
8. Logic trình bày, localization hoặc client-specific formatting.
9. Quy trình yêu cầu retries/timeouts/rate limits ngoài DB.
10. Bài toán không cần transaction nội bộ của PostgreSQL.

### 44.1. Đừng giữ database transaction mở khi gọi mạng

Một transaction chờ HTTP nhiều giây có thể giữ locks, snapshots và tài nguyên, tăng contention/autovacuum pressure. Thường nên ghi intent/outbox rồi xử lý bên ngoài.

### 44.2. Scale-out CPU

Application servers có thể dễ tăng replicas; PostgreSQL primary thường là tài nguyên tập trung. Đưa quá nhiều tính toán không liên quan I/O dữ liệu vào DB có thể lấy CPU của những queries cốt lõi.

### 44.3. Versioning và rollback

Một rule thay đổi nhiều lần/ngày có thể dễ deploy/roll back ở Java hơn migration stored functions. Nhưng quy tắc ảnh hưởng dữ liệu vẫn cần giữ consistency với schemas và constraints.

## 45. Tiêu chí đưa logic vào function hoặc procedure

Chọn function/procedure khi có một hoặc nhiều lợi ích rõ:

- **Reusability**: cùng logic cần dùng trong nhiều truy vấn/clients.
- **Atomicity**: nhiều bước DML trên cùng cluster phải cùng transaction.
- **Reduced round trips**: tránh quá nhiều lệnh nhỏ từ ứng dụng.
- **Data access control**: cấp một capability hẹp thay vì cho caller quyền rộng trên bảng nền.
- **Data locality**: tính toán ngay nơi có dữ liệu, tránh truyền lượng lớn rows.
- **Set-oriented implementation**: function SQL có thể viết theo tập và có khả năng inline.
- **Stable interface**: contract function có versioning và ownership rõ.
- **Operational discipline**: migration/test/monitoring cho đối tượng DB có sẵn.

### 45.1. Khi không nên

Nếu function chỉ bọc một câu `SELECT</BT> trivial, được gọi một lần, không có lợi ích về API, quyền hoặc tái sử dụng, độ phức tạp có thể không đáng.

### 45.2. Khi cần nhiều bước

PL/pgSQL có thể hữu ích cho kiểm tra điều kiện, cập nhật nhiều bảng và xử lý một số lỗi. Nhưng **hãy cố viết DML set-based bên trong**, thay vì `FOR row IN SELECT LOOP UPDATE ... END LOOP</BT> khi có thể dùng `UPDATE ... FROM</BT>.

### 45.3. Tiêu chí cuối cùng là chất lượng hệ thống

Hiệu năng, correctness, security, observability, deployability và team capability đều quan trọng; không lấy chỉ số execution time nhỏ nhất làm tiêu chí duy nhất.

## 46. Ma trận quyết định ví dụ

| Bài toán | Giải pháp nên đánh giá đầu tiên | Lý do |
|---|---|---|
| Tính amount × 1.1 cho 10 triệu hàng | Biểu thức SQL hoặc SQL function thuần | Set-based, có thể inline |
| Đếm paid orders cho 1.000 customers | JOIN/GROUP BY | Tránh per-row SQL lookup |
| Bảo vệ quantity >= 0 | CHECK constraint | Invariant luôn áp dụng |
| SKU unique | UNIQUE constraint | Concurrency-safe uniqueness |
| Order state transition new → paid | UPDATE có điều kiện; function/procedure nếu cần API | Atomic row update |
| Ghi order và outbox cùng commit | Transaction/statement/function phù hợp | Atomic trong PostgreSQL |
| Gửi email sau thanh toán | Worker bên ngoài + outbox | External I/O, retries |
| Tính score ML rất nặng | Service chuyên dụng hoặc extension đã đánh giá | Scale compute riêng |
| Admin batch nhiều transaction | Service orchestrator hoặc CALL procedure có kiểm soát | Transaction boundaries rõ |
| Tra cứu bảng cấu hình trong function | STABLE nếu ngữ nghĩa phù hợp | Không được gán IMMUTABLE |
| Random ID/sequence | VOLATILE semantics | Side effect/kết quả thay đổi |
| Validation request JSON/UI | Java/service | Gần API, dễ versioning |
| Quyền ghi giới hạn của caller | SECURITY DEFINER function được harden | Capability hẹp, audit |
| Báo cáo tổng hợp nhiều bảng | SQL query/view/materialized view tùy freshness | Planner, data locality |

## 47. Versioning stored functions và API contracts

Stored function signature là một interface:

~~~sql
SELECT fn_cost_lab.discounted_amount(100, 0.10);
~~~

Một client có thể phụ thuộc vào:

- Schema/function name.
- Số arguments và argument types.
- Default arguments, named parameters.
- Return type, column names khi RETURNS TABLE.
- Volatility/side effects.
- Exception behavior.
- Required EXECUTE privileges.
- Transaction ownership.
- Runtime/performance expectations.

### 47.1. CREATE OR REPLACE FUNCTION có giới hạn

PostgreSQL không cho đổi tùy ý return type của một function hiện hữu bằng `CREATE OR REPLACE FUNCTION</BT>; có thể cần tạo signature/version mới hoặc DROP rồi CREATE với tác động dependency/privileges tương ứng.

### 47.2. Đổi semantics mà giữ signature vẫn có thể breaking

Nếu function `calculate_total</BT> trước tính chưa thuế, sau tính đã thuế dù cùng `NUMERIC</BT>, client có thể sai. Cần versioning và contract tests.

### 47.3. Overloading có thể gây ambiguous calls

Tạo nhiều overload cùng tên nhưng khác numeric/integer/unknown type có thể khiến calls không rõ kiểu chọn function nào, đặc biệt với NULL hoặc string literals. Dùng explicit casts và API names rõ khi cần.

### 47.4. Đặt tên rõ tác dụng phụ

`get_...</BT>, `calculate_...</BT> nên không ghi dữ liệu theo contract. `record_...</BT>, `mark_...</BT>, `confirm_...</BT> nên được mô tả là commands, kèm idempotency và quyền.

### 47.5. Java JDBC cần test return shape

Mapping `RETURNS TABLE</BT> hay composite results trong JDBC cần đảm bảo tên/kiểu cột đúng. Thay return shape có thể ảnh hưởng callers dù SQL migration chạy thành công.

## 48. Triển khai và rollback function/procedure

### 48.1. Database migrations là code deployment

Source function/procedure cần được version control, reviewed, đưa qua staging và test trên PostgreSQL version đích.

### 48.2. Expand-contract cho DB API

Một chiến lược:

1. Tạo function v2.
2. Giữ v1 cho app instances cũ.
3. Deploy Java dùng v2 theo từng đợt.
4. Theo dõi invocation của v1/v2.
5. Xác minh toàn bộ callers đã chuyển.
6. REVOKE/DROP v1 chỉ khi an toàn.

### 48.3. Không DROP CASCADE tùy tiện

Function có thể được view/trigger/other function hoặc application phụ thuộc. CASCADE có thể xóa objects ngoài dự định. SQL text ở Java có thể không hiện trong catalog dependency graph.

### 48.4. Permissions sau thay đổi

`CREATE OR REPLACE FUNCTION</BT> và DROP/CREATE có ảnh hưởng khác đến object identity, grants và ownership. Khi đổi function phải kiểm tra quyền cuối cùng thay vì nghĩ chỉ cần đổi thân.

### 48.5. Lock và transaction

DDL thay function, đổi owner hoặc privileges có thể tác động queries đang chạy và cached plans. Có migration/rollback plan, không deploy trực tiếp bằng script thiếu kiểm soát trên production.

## 49. Benchmark có giá trị: đo cả read và write

Một benchmark muốn so function SQL và PL/pgSQL cần:

1. Cùng dataset.
2. Cùng query semantics.
3. Cùng số hàng đầu vào.
4. Cùng cột output/aggregate.
5. Cùng PostgreSQL settings chính.
6. Chạy nhiều lần để giảm hiệu ứng cache.
7. Quan sát planning/execution time.
8. Theo dõi buffers.
9. Theo dõi function calls khi có instrumentation.
10. Đánh giá cả throughput và p95/p99.
11. Ghi CPU/I/O/WAL/locks nếu có DML.
12. Tách CPU-heavy math và nested SQL lookup.
13. Không lạm dụng SET enable_seqscan=off như tối ưu production.
14. Không coi EXPLAIN cost là milliseconds.
15. Không đo DML thật rồi vô tình commit dữ liệu test.

### 49.1. Một phép đo không có cùng semantics là vô nghĩa

Nếu PL function tính thuế có rounding khác SQL expression, chênh lệch kết quả có thể lớn hơn vấn đề hiệu năng. Xác định business rounding và precision trước.

### 49.2. LIMIT không xóa mọi công việc

Query có `ORDER BY expensive_function(...)</BT> rồi LIMIT 20 có thể vẫn cần đánh giá function trên nhiều rows trước khi biết top 20.

### 49.3. Đừng bỏ qua network

Một Java loop thực hiện 1.000 JDBC queries có thể chịu latency network đáng kể; gom thành một SQL set-based query có thể giảm network và tận dụng optimizer.

### 49.4. Đừng tối ưu nhầm tầng

Nếu 99% thời gian nằm ở remote API call, chuyển một phép cộng từ Java vào SQL function không giải quyết bottleneck. Cần đo end-to-end.

## 50. Các sai lầm thường gặp

### 50.1. “Stored function luôn nhanh hơn Java”

**Sai.** Database execution có lợi data locality/transaction, nhưng có overhead và chiếm CPU primary.

### 50.2. “Function trong SELECT chỉ chạy một lần”

**Sai nói chung.** Nó có thể được đánh giá cho nhiều rows, tùy plan và optimizer.

### 50.3. “PL/pgSQL chỉ là SQL function nên sẽ inline”

**Sai.** Inlining của một số LANGUAGE SQL functions khác thực thi PL/pgSQL.

### 50.4. “Hàm SQL nào cũng inline”

**Sai.** Có các điều kiện và giới hạn planner.

### 50.5. “Cached plan làm 1.000 internal SELECT thành một JOIN”

**Sai.** Plan reuse khác set-based execution.

### 50.6. “Có index thì function gọi mỗi hàng không thể chậm”

**Sai.** Nhiều index lookups vẫn tạo công việc đáng kể.

### 50.7. “Nên dùng LOOP vì dễ viết hơn GROUP BY”

Không mặc định. SQL set-based thường đáng thử trước cho khối lượng lớn.

### 50.8. “IMMUTABLE giúp nhanh, gán cho mọi function”

**Sai và nguy hiểm.** Đánh dấu sai có thể trả kết quả stale.

### 50.9. “STABLE cho phép mọi DML vì chỉ đọc snapshot”

**Sai.** STABLE/IMMUTABLE có giới hạn đối với database-modifying statements.

### 50.10. “VOLATILE cho phép function tự COMMIT”

**Sai.** Volatility không thay transaction boundary.

### 50.11. “Function bị rollback thì sequence không tăng”

**Sai.** Sequence state không rollback như table rows.

### 50.12. “Gọi HTTP trong function sẽ rollback cùng transaction”

**Sai.** External side effects không tự rollback.

### 50.13. “COST 100 nghĩa 100 milliseconds”

**Sai.** Là planner cost estimate.

### 50.14. “ROWS 50 nghĩa function chỉ được trả 50 rows”

**Sai.** Là cardinality estimate, không phải LIMIT.

### 50.15. “PARALLEL SAFE làm mọi query chạy parallel”

**Sai.** Chỉ cho phép trong điều kiện phù hợp.

### 50.16. “Gắn SAFE cho function có sequence giúp nhanh”

**Sai và có thể không an toàn.**

### 50.17. “Bắt WHEN OTHERS rồi RETURN FALSE luôn ổn”

**Không.** Có thể che lỗi nghiêm trọng.

### 50.18. “EXCEPTION block không tốn tài nguyên nếu không có lỗi”

**Không mặc định.** Có chi phí quản lý subtransaction.

### 50.19. “SELECT không thể ghi dữ liệu”

**Sai nếu gọi VOLATILE function làm DML**, trong bối cảnh được phép.

### 50.20. “LIMIT bảo đảm function ghi log đúng N lần”

**Không nên dựa vào**, nếu không có hợp đồng thực thi đảm bảo cụ thể.

### 50.21. “Procedure được phép COMMIT trong mọi CALL”

**Sai.** Chỉ trong các hoàn cảnh transaction control được hỗ trợ.

### 50.22. “JDBC autoCommit=false vẫn cho procedure COMMIT độc lập”

**Không mặc định.** CALL thường nằm trong transaction do client quản lý.

### 50.23. “SECURITY DEFINER luôn an toàn hơn INVOKER”

**Sai.** Nó có thể nâng quyền và bị khai thác nếu search_path/permissions/input không được harden.

### 50.24. “Function có EXECUTE cho PUBLIC không quan trọng”

**Sai với function ghi dữ liệu/quyền đặc biệt.**

### 50.25. “RLS được giữ nguyên dù đổi chủ sở hữu function”

**Không chắc.** Owner/DEFINER và bypass semantics có thể ảnh hưởng.

### 50.26. “Gọi function check unique thay UNIQUE constraint”

**Sai.** Có race dưới concurrency.

### 50.27. “Outbox tự bảo đảm exactly-once ngoài hệ thống”

**Sai.** Consumer vẫn cần idempotency và retry handling.

### 50.28. “Dùng dynamic EXECUTE cho mọi query thì linh hoạt và nhanh hơn”

**Không đúng chung.** Dynamic EXECUTE có planning/security costs.

### 50.29. “EXPLAIN ngoài hiển thị mọi truy vấn PL/pgSQL bên trong”

**Không mặc định.** Có thể cần nested instrumentation.

### 50.30. “Một benchmark đủ để kết luận lâu dài”

**Sai.** Cần workload đại diện, warmup, read/write và concurrency.

## 51. Bài tập thực hành

### Bài 1 — Function hay procedure?

Bạn cần tính giá sau thuế trong SELECT. Đối tượng PostgreSQL phù hợp hơn?

**Gợi ý:** Function trả scalar, có thể dùng LANGUAGE SQL và thuộc tính volatility đúng.

### Bài 2 — Gọi hàm theo hàng

Một query trả 800.000 rows và có PL/pgSQL function trong SELECT list. Vấn đề nào cần đo?

**Gợi ý:** Số lần gọi thực tế, overhead và công việc bên trong mỗi lần.

### Bài 3 — Round trips

Java chạy 1.000 SELECTs qua JDBC. Vì sao một set-based query có thể nhanh hơn?

**Gợi ý:** Giảm network round trips và cho planner xử lý toàn tập.

### Bài 4 — SQL inlining

Mọi LANGUAGE SQL function có được inline không?

**Đáp án:** Không, phụ thuộc điều kiện và cấu trúc.

### Bài 5 — PL/pgSQL

Có thể coi PL/pgSQL function là một biểu thức SQL luôn inline không?

**Đáp án:** Không.

### Bài 6 — N+1 ẩn

`SELECT c.id, count_orders(c.id) FROM customers c</BT> có thể giấu điều gì?

**Gợi ý:** Một truy vấn nội bộ cho mỗi c.id.

### Bài 7 — Set-based

Viết một query GROUP BY đếm paid orders theo customer.

**Gợi ý:** Dùng LEFT JOIN với `status='paid'</BT> trong ON và COUNT(order_id).

### Bài 8 — COUNT với LEFT JOIN

Vì sao COUNT(*) có thể trả 1 cho customer không có order?

**Đáp án:** LEFT JOIN tạo một null-extended row.

### Bài 9 — IMMUTABLE

Hàm `square(numeric)</BT> chỉ nhân tham số với chính nó có thể khai báo volatility nào?

**Gợi ý:** IMMUTABLE khi thực sự không phụ thuộc trạng thái khác.

### Bài 10 — STABLE

Hàm đọc bảng tỷ giá có phù hợp IMMUTABLE không?

**Đáp án:** Không nếu tỷ giá có thể thay đổi; cân nhắc STABLE/VOLATILE theo semantics.

### Bài 11 — VOLATILE

`random()</BT> có thuộc tính gì?

**Đáp án:** VOLATILE.

### Bài 12 — Time

`clock_timestamp()</BT> và `now()</BT> có cùng mức biến thiên không?

**Đáp án:** Không.

### Bài 13 — INSERT function

Function ghi audit rows nên khai báo volatility gì?

**Gợi ý:** VOLATILE.

### Bài 14 — Function COMMIT

Một function được gọi từ SELECT có được tự COMMIT không?

**Đáp án:** Không.

### Bài 15 — Procedure COMMIT

CALL trong explicit transaction block có cho procedure COMMIT nội bộ tự do không?

**Đáp án:** Không, transaction control có hạn chế.

### Bài 16 — JDBC

Vì sao cần hiểu `autoCommit</BT> trước khi gọi procedure có transaction control?

**Gợi ý:** Driver quyết định có implicit/explicit transaction context.

### Bài 17 — Sequence rollback

Sau ROLLBACK, ID identity/sequence có thể bị nhảy không?

**Đáp án:** Có.

### Bài 18 — External effects

Gửi email qua external API trong function có được rollback cùng INSERT không?

**Đáp án:** Không tự động.

### Bài 19 — Outbox

Outbox giải quyết tính atomic của những gì?

**Gợi ý:** Business state update và event intent trong cùng DB transaction.

### Bài 20 — Exactly-once

Outbox với retry có cần idempotent consumer không?

**Đáp án:** Có.

### Bài 21 — COST

`COST 100</BT> có nghĩa 100ms mỗi lần gọi không?

**Đáp án:** Không, planner cost units.

### Bài 22 — ROWS

`ROWS 100</BT> có cắt kết quả function ở 100 rows không?

**Đáp án:** Không.

### Bài 23 — PARALLEL SAFE

Một function có side effects trên sequence nên được gán PARALLEL SAFE cho nhanh không?

**Đáp án:** Không.

### Bài 24 — STRICT

Hàm cần xử lý NULL như 0 có nên khai báo STRICT không?

**Gợi ý:** Không nếu NULL phải được xử lý trong thân.

### Bài 25 — EXCEPTION

EXCEPTION block trong PL/pgSQL có thể tăng chi phí gì?

**Gợi ý:** Subtransaction management.

### Bài 26 — Constraints

Vì sao dùng UNIQUE thay SELECT COUNT rồi INSERT khi cần uniqueness?

**Gợi ý:** Concurrency race.

### Bài 27 — FK

Vì sao một application pre-check không thay FOREIGN KEY?

**Gợi ý:** Concurrent delete/update có thể xảy ra sau kiểm tra.

### Bài 28 — Trigger

Một per-row trigger trên một triệu INSERT có thể gọi function bao nhiêu lần?

**Gợi ý:** Khoảng một triệu lần theo trigger firing semantics.

### Bài 29 — SQL UPDATE

Một million-row update có luôn nên dùng FOR LOOP UPDATE từng row không?

**Đáp án:** Không; thử set-based UPDATE.

### Bài 30 — SECURITY DEFINER

Tại sao cần SET search_path an toàn?

**Gợi ý:** Ngăn name resolution sang objects ở schema không tin cậy.

### Bài 31 — Quyền

Function mới có EXECUTE mặc định cho PUBLIC trong các điều kiện thông thường; với function nhạy cảm cần làm gì?

**Gợi ý:** REVOKE/GRANT có kiểm soát, tốt nhất cùng transaction tạo.

### Bài 32 — RLS

Test dưới superuser có đủ chứng minh function an toàn cho application role không?

**Đáp án:** Không.

### Bài 33 — EXPLAIN

EXPLAIN outer query có luôn hiện từng SELECT nội bộ PL/pgSQL không?

**Đáp án:** Không.

### Bài 34 — pg_stat_user_functions

Muốn đếm function calls và timing, cần cấu hình nào được bật?

**Gợi ý:** track_functions phù hợp.

### Bài 35 — Dynamic SQL

Vì sao EXECUTE dynamic SQL có thể tốn hơn static PL/pgSQL statement?

**Gợi ý:** Parse/plan lại, cùng chi phí xây chuỗi và kiểm soát injection.

### Bài 36 — pg_stat_statements

Cần xem nested statements thì phải chú ý cấu hình gì?

**Gợi ý:** pg_stat_statements.track và phạm vi ghi nhận phù hợp.

### Bài 37 — Java vs DB

Logic gửi webhook sau thanh toán nên đặt trực tiếp trong transaction function hay ngoài DB?

**Gợi ý:** Worker/outbox ngoài DB thường kiểm soát retries tốt hơn.

### Bài 38 — API contract

Đổi function trả numeric thành text có thể làm client Java lỗi không?

**Đáp án:** Có; return type là phần contract.

### Bài 39 — Versioning

Nếu app cũ còn gọi function v1, nên drop v1 ngay khi tạo v2 không?

**Đáp án:** Không; chuyển consumers và xác minh trước.

### Bài 40 — Bài toán thiết kế

Một SaaS có 2 triệu orders/ngày, mỗi order cần validation quantity >=0, chuyển trạng thái payment, ghi audit và gửi email. Hãy phân trách nhiệm giữa DB và service.

**Gợi ý:** CHECK/PK/FK cho invariants, UPDATE state transition atomic, audit/outbox cùng transaction, worker gửi email sau commit, Java orchestration và retry/idempotency.

### Bài 41 — Đo đạc

Hai bản tính thuế SQL và PL/pgSQL có kế hoạch/latency khác nhau. Liệt kê năm yếu tố cần giữ giống nhau trong benchmark.

**Gợi ý:** Dataset, query semantics, số rows, PostgreSQL settings, warm-up/cache và output shape.

### Bài 42 — Planner

Một SQL function có COST cao nhưng được inline. Có nên suy luận planner luôn trả đúng COST như lời gọi opaque function không?

**Đáp án:** Không.

### Bài 43 — DML return

Ở hàm mark_order_paid, `FOUND</BT> trả điều gì sau UPDATE?

**Gợi ý:** Statement UPDATE vừa thực thi có tìm/ảnh hưởng row theo semantics PL/pgSQL không.

### Bài 44 — Transaction API

Procedure tự COMMIT nội bộ có phù hợp khi caller cần gộp nó với ba bước khác cùng atomic transaction không?

**Đáp án:** Thường không; phải thiết kế quyền sở hữu transaction rõ.

### Bài 45 — Kiến trúc hoàn chỉnh

Cho function tính discount, function tra cứu bảng discount, và function gọi external recommendation API. Bạn sẽ phân loại volatility/placement như thế nào?

**Gợi ý:** Toán học thuần IMMUTABLE; lookup bảng STABLE nếu snapshot semantics phù hợp; external call thường nên nằm ở service/worker và không được gán IMMUTABLE.

## 52. Checklist trước khi đưa logic vào PostgreSQL

### 52.1. Về thuật toán và hiệu năng

- Logic có thể viết thành set-based SQL không?
- Hàm sẽ được gọi bao nhiêu lần trong một request?
- Có câu SELECT nội bộ chạy theo từng row không?
- SQL function có khả năng được inline không?
- PL/pgSQL có cần thiết cho nhánh/exception không?
- Có thể giảm network round trips mà không tạo per-row SQL overhead không?
- Có dữ liệu benchmark representative không?
- Đã đo p95/p99 và chi phí write/locks/WAL chưa?

### 52.2. Về correctness

- Function được phân loại đúng IMMUTABLE/STABLE/VOLATILE chưa?
- NULL/STRICT semantics đúng chưa?
- Constraints có thể thay validation function ở đâu?
- Concurrency/race được xử lý bằng UPDATE có điều kiện, unique/FK/locks chưa?
- Tác dụng phụ nào không rollback?
- Idempotency/retry behavior được mô tả chưa?
- Caller hay procedure sở hữu transaction?
- Có side effects ẩn trong SELECT/trigger không?

### 52.3. Về planner

- COST/ROWS estimates có hợp lý chưa?
- PARALLEL SAFE/RESTRICTED/UNSAFE có đúng behavior không?
- Query plans được đo thực tế bằng EXPLAIN chưa?
- Có function opaque che JOIN/filter bên trong không?
- Có dynamic SQL làm tăng parse/plan mỗi lần không?
- Statistics và indexes trên bảng nền đã phù hợp chưa?

### 52.4. Về security

- SECURITY INVOKER hay DEFINER?
- Function owner có quyền tối thiểu?
- Search path có chỉ trusted schemas?
- Schema-qualification cho objects quan trọng?
- EXECUTE cho PUBLIC đã được kiểm soát?
- Tenant/RLS/authorization đã được test dưới application role?
- Input validation và SQL injection được xử lý?

### 52.5. Về vận hành

- Stored code có migration/version control?
- Có thể deploy v2 cùng v1?
- Có rollback plan nếu function output/semantics đổi?
- Đã tài liệu hóa caller/contract/side effects?
- Có monitoring calls/time/locks/errors?
- Có thể scale DB CPU nếu thêm nhiều function workloads?
- Các external effects dùng worker/outbox thay vì giữ transaction mở?
- Có đội chịu trách nhiệm lâu dài cho function/procedure?

## 53. Bảng tra cứu nhanh

| Khái niệm | Ghi nhớ |
|---|---|
| `CREATE FUNCTION</BT> | Hàm có thể dùng trong SQL expression |
| `CREATE PROCEDURE</BT> | Thủ tục được gọi bằng CALL |
| `LANGUAGE SQL</BT> | Có cơ hội inlining nếu đủ điều kiện |
| `LANGUAGE plpgsql</BT> | Procedural logic, runtime riêng |
| Per-row function call | Nhiều invocations khi xử lý nhiều rows |
| N+1 ẩn trong DB | Function chạy SQL nội bộ nhiều lần |
| Set-based SQL | JOIN, GROUP BY, UPDATE FROM, INSERT SELECT |
| Inlining | Planner đưa body SQL function vào query trong điều kiện hỗ trợ |
| Static SQL PL/pgSQL | Có cơ chế lưu/reuse plans thích hợp |
| Dynamic EXECUTE | SQL động, thường plan lại mỗi lần |
| `IMMUTABLE</BT> | Kết quả không đổi với cùng arguments |
| `STABLE</BT> | Ổn định theo snapshot/statement semantics |
| `VOLATILE</BT> | Có thể thay đổi, đọc trạng thái mới hoặc DML |
| `STRICT</BT> | Null argument dẫn tới null result, không chạy body |
| `COST</BT> | Planner estimate, không phải thời gian đo |
| `ROWS</BT> | Estimated cardinality cho set-returning function |
| `PARALLEL SAFE</BT> | Có thể chạy trong workers khi thật sự an toàn |
| `PARALLEL RESTRICTED</BT> | Giới hạn vào leader |
| `PARALLEL UNSAFE</BT> | Có thể cản parallel plan |
| Function transaction | Không tự COMMIT/ROLLBACK |
| Procedure transaction | Có thể COMMIT trong điều kiện CALL/DO hỗ trợ |
| EXCEPTION | Subtransaction overhead |
| Sequence | nextval không rollback như table rows |
| DML side effect | Ghi bảng trong transaction |
| External side effect | Không tự rollback cùng PostgreSQL |
| Transactional outbox | Ghi event intent cùng business transaction |
| Idempotency | Retry không tạo business effect ngoài ý muốn |
| SECURITY INVOKER | Quyền theo caller trong semantics phù hợp |
| SECURITY DEFINER | Quyền theo owner, cần harden |
| search_path | Tránh schema không tin cậy ở SECURITY DEFINER |
| GRANT EXECUTE | Quyền gọi function/procedure |
| RLS | Bảo vệ phạm vi rows theo policy |
| Trigger function | Logic tự chạy khi sự kiện DML xảy ra |
| `EXPLAIN (ANALYZE, BUFFERS)</BT> | Đo kế hoạch thực thi và buffers |
| `track_functions</BT> | Thu thập thống kê lời gọi function |
| `pg_stat_user_functions</BT> | Calls, total_time, self_time |
| `pg_stat_statements</BT> | Query statistics với extension/cấu hình |
| `auto_explain</BT> | Plan logging, nested statements tùy cấu hình |
| DB API versioning | Tạo v2, chuyển callers, gỡ v1 sau |
| Decision boundary | Correctness, locality, scale, observability, maintenance |

---

## Kết luận

**Không có quy tắc “đưa logic vào PostgreSQL luôn nhanh hơn” hoặc “hàm PostgreSQL luôn chậm”.** Chi phí thực phụ thuộc số lần gọi, công việc bên trong, ngôn ngữ function, khả năng SQL inlining, query planner, network round trips và cách SQL khai thác xử lý theo tập. Với một phép tính đơn giản gọi trên hàng triệu rows, biểu thức SQL hoặc SQL function thuần có thể là lựa chọn tốt. Với một workflow nhiều bước cần atomicity, PL/pgSQL function/procedure có thể giảm round trips và tập trung invariant. Với một hàm đếm orders cho từng customer, một câu JOIN/GROUP BY thường đáng đo trước khi chấp nhận N+1 internal queries.

**Volatility và side effects là hợp đồng correctness, không phải cờ tăng tốc.** `IMMUTABLE</BT> chỉ đúng với hàm thực sự không thay kết quả theo trạng thái ngoài arguments; `STABLE</BT> cho một số truy vấn đọc trạng thái theo snapshot ổn định; `VOLATILE</BT> cho giá trị thay đổi hoặc ghi dữ liệu. `COST</BT>, `ROWS</BT> và `PARALLEL</BT> mô tả giả định cho optimizer; khai báo sai có thể làm kế hoạch tệ hoặc vi phạm ngữ nghĩa. Function không tự COMMIT, procedure chỉ có transaction control trong điều kiện được phép, và rollback PostgreSQL không tự hoàn tác sequence hoặc external network effects.

**Đưa logic vào database khi nó thực sự hưởng lợi từ tính gần dữ liệu, set-based execution, transaction atomicity, constraints và quyền truy cập có kiểm soát.** Giữ orchestration đa hệ thống, HTTP/email/webhook, xử lý UI và các tác vụ CPU-heavy có thể scale riêng ở tầng ứng dụng/worker; dùng outbox/idempotency khi cần liên kết một giao dịch PostgreSQL với sự kiện bên ngoài. Trước khi quyết định, hãy xác định nguồn chân lý của business rule, đo bằng EXPLAIN và thống kê function, kiểm tra quyền/transaction/retry dưới role thực tế, và lên kế hoạch versioning/rollback cho DB API.

Một nguyên tắc hữu ích: **ưu tiên SQL theo tập và constraints cho tính đúng; dùng function/procedure để tạo hợp đồng và đóng gói nơi thực sự cần; tuyệt đối không để các side effects quan trọng bị ẩn trong những lời gọi khó dự đoán.**
