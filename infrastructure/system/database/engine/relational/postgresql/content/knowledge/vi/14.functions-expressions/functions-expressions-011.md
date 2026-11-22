# IMMUTABLE, STABLE, VOLATILE và ý nghĩa với tối ưu hóa trong PostgreSQL

Khi tạo một hàm do người dùng định nghĩa (*user-defined function*, UDF) trong PostgreSQL, bạn có thể khai báo một trong ba mức **volatility**: `IMMUTABLE`, `STABLE` hoặc `VOLATILE`. Đây không chỉ là nhãn mô tả. Nó là **lời cam kết với bộ tối ưu truy vấn (query planner)** về việc giá trị hàm có thể thay đổi đến mức nào, từ đó ảnh hưởng tới cách PostgreSQL đánh giá biểu thức, lập kế hoạch truy vấn và sử dụng chỉ mục.

Ví dụ:

- Tính `price * (1 - discount_rate)` chỉ phụ thuộc hai tham số số học: ứng viên cho `IMMUTABLE`.
- Lấy hạng khách hàng từ một bảng: dữ liệu có thể đổi giữa các câu lệnh nhưng được đọc nhất quán trong phạm vi một câu lệnh: thường phù hợp với `STABLE`.
- Gọi `random()`, `clock_timestamp()`, `nextval()` hoặc sửa dữ liệu: cần `VOLATILE`.

Một khai báo quá dè dặt, ví dụ đánh dấu phép toán thuần là `VOLATILE`, có thể làm PostgreSQL bỏ lỡ một số cơ hội tối ưu. Nguy hiểm hơn, **khai báo quá mạnh**, ví dụ đánh dấu hàm đọc bảng thay đổi thường xuyên là `IMMUTABLE`, có thể khiến planner tái sử dụng giá trị không còn đúng, đặc biệt với prepared statement và cached plan.

Bài học đi từ định nghĩa, ví dụ SQL có thể chạy trong PostgreSQL, tới tác động của volatility lên **constant folding**, điều kiện index scan, **expression index**, **partial index**, generated column, snapshot trong hàm, transaction và plan cache.

## 1. Volatility là lời hứa về khả năng thay đổi kết quả

Hãy tưởng tượng PostgreSQL nhìn thấy biểu thức:

~~~sql
SELECT my_function(10);
~~~

Planner cần biết:

- Có thể **tính trước biểu thức ngay khi lập kế hoạch** hay không?
- Nếu một truy vấn đọc một triệu hàng, có thể **tính một lần rồi dùng lại** hay phải giữ khả năng đánh giá tại mỗi hàng?
- Có thể dùng kết quả hàm làm điều kiện so sánh với một **B-tree index** không?
- Có thể lưu kết quả hàm như một phần khóa chỉ mục hoặc cột được sinh tự động không?
- Hàm có thể quan sát dữ liệu thay đổi trong quá trình statement thực thi không?

Ba mức volatility cung cấp các bảo đảm khác nhau.

| Mức | Cam kết về kết quả | Có thể sửa database trong hàm? | Tác động chính tới planner |
| --- | --- | --- | --- |
| **`IMMUTABLE`** | Cùng đối số luôn cho cùng kết quả, độc lập thời điểm và trạng thái database/session | Không | Có thể tính trước khi đối số là hằng; phù hợp với expression index |
| **`STABLE`** | Cùng đối số cho cùng kết quả trong phạm vi **một statement** | Không | Có thể xem như không đổi trong statement, phù hợp nhiều điều kiện index scan |
| **`VOLATILE`** | Kết quả có thể đổi giữa các lần gọi, kể cả trong cùng statement; hàm có thể có side effect | Có thể, nếu quyền và ngôn ngữ cho phép | Không được giả định giá trị bất biến; hạn chế việc tính trước và dời lời gọi |

Đây là **phân loại theo hợp đồng của hàm**, không phải PostgreSQL tự quan sát vài lần rồi suy ra mức chính xác. Khi tự khai báo, lập trình viên chịu trách nhiệm chọn mức phù hợp với mọi hành vi mà hàm thực hiện.

### “Cùng đối số” quan trọng như thế nào?

Giả sử hàm `f(10)` được gọi nhiều lần:

- `IMMUTABLE`: kết quả không được phụ thuộc vào thời gian hiện tại, bảng dữ liệu, cấu hình session hay trạng thái bên ngoài có thể đổi.
- `STABLE`: có thể phụ thuộc vào dữ liệu đọc hoặc giá trị cố định trong statement; các statement tiếp theo có thể thấy kết quả khác.
- `VOLATILE`: mỗi lần cần tính có thể cho giá trị khác, hoặc có hiệu ứng ghi dữ liệu.

Nếu một hàm không nhận tham số mà trả thời gian đồng hồ hiện tại, bản chất nó **không thể là IMMUTABLE** chỉ vì chữ ký không có đối số.

## 2. Ba mức không phải ba “mức tốc độ”

Một cách diễn giải sai là:

~~~text
IMMUTABLE = nhanh
STABLE    = trung bình
VOLATILE  = chậm
~~~

Thực tế, volatility mô tả **những tối ưu nào được phép áp dụng**, không tự đo thời gian chạy của hàm.

Một hàm `IMMUTABLE` có thể làm phép tính khoa học rất tốn CPU. Một hàm `VOLATILE` có thể chỉ trả một số ngẫu nhiên trong thời gian rất ngắn. Thời gian thực tế còn phụ thuộc số lần gọi, truy cập bảng, biểu thức, kế hoạch thực thi, cache, chỉ mục và concurrency.

Điều quan trọng là **không được đổi tính đúng đắn lấy sự tối ưu**. Đánh dấu hàm sai thành `IMMUTABLE` có thể tạo lỗi dữ liệu khó phát hiện hơn nhiều so với mất vài mili giây hiệu năng.

~~~mermaid
flowchart TD
    A["Phân tích hành vi thực của hàm"] --> B{"Kết quả chỉ phụ thuộc đối số, không đổi theo thời gian/trạng thái?"}
    B -->|"Có"| C["IMMUTABLE"]
    B -->|"Không"| D{"Không sửa dữ liệu và ổn định trong một statement?"}
    D -->|"Có"| E["STABLE"]
    D -->|"Không"| F["VOLATILE"]
    C --> G["Planner có thể constant-fold"]
    E --> H["Planner có thể dùng như giá trị ổn định trong statement"]
    F --> I["Planner phải giữ khả năng tính lại/side effects"]
~~~

Sơ đồ là quy tắc lựa chọn ban đầu; với hàm phụ thuộc collation, múi giờ, snapshot, extension hoặc API bên ngoài, phải xét cả các phụ thuộc ít lộ rõ.

## 3. Những hàm PostgreSQL quen thuộc thuộc nhóm nào?

Bảng sau giúp nhận biết sự khác biệt:

| Biểu thức/hàm | Volatility thường gặp | Lý do |
| --- | --- | --- |
| `abs(-10)` | `IMMUTABLE` | Phép toán xác định chỉ từ đối số |
| `lower(text)` | `IMMUTABLE` | Chuyển đổi text theo quy tắc so sánh/collation của môi trường |
| `now()` / `current_timestamp` | `STABLE` | Thời điểm bắt đầu transaction, không đổi trong transaction |
| `transaction_timestamp()` | `STABLE` | Cùng ý nghĩa mốc bắt đầu transaction |
| `statement_timestamp()` | `STABLE` | Thời điểm bắt đầu statement hiện tại |
| `current_setting('TimeZone')` | `STABLE` | Đọc cấu hình có thể đổi giữa những lần thực thi |
| `clock_timestamp()` | `VOLATILE` | Đọc đồng hồ thực, giá trị có thể thay đổi trong cùng statement |
| `random()` | `VOLATILE` | Sinh giá trị pseudo-random mỗi lần gọi |
| `nextval('some_seq')` | `VOLATILE` | Thay đổi trạng thái sequence |
| Hàm đọc bảng khách hàng | Thường `STABLE` nếu chỉ đọc và bảo đảm ổn định trong statement | Dữ liệu bảng thay đổi theo thời gian |
| Hàm `INSERT`/`UPDATE`/`DELETE` | `VOLATILE` | Có side effect ghi dữ liệu |

Điểm dễ nhầm nhất là **`now()` không phải VOLATILE** chỉ vì tên có nghĩa “bây giờ”. Trong PostgreSQL, `now()` tương đương thời điểm bắt đầu **transaction**, nên giữ nguyên giá trị trong transaction; `clock_timestamp()` mới là hàm xem đồng hồ thực tại thời điểm gọi.

Không thể suy volatility chỉ từ tên hàm. Khi cần chính xác, xem catalog `pg_proc`, tài liệu phiên bản server và chức năng thật của UDF.

## 4. Phân biệt ba loại thời gian qua giao dịch

Chạy ví dụ trong phiên PostgreSQL của database lab:

~~~sql
BEGIN;

SELECT
    now() AS transaction_time,
    statement_timestamp() AS statement_time,
    clock_timestamp() AS wall_clock_time;

-- Chỉ để quan sát đồng hồ trong lab.
SELECT pg_sleep(0.3);

SELECT
    now() AS transaction_time,
    statement_timestamp() AS statement_time,
    clock_timestamp() AS wall_clock_time;

ROLLBACK;
~~~

Dự kiến:

- Hai giá trị `now()` trong cùng transaction **bằng nhau**, vì cùng tham chiếu thời điểm bắt đầu transaction.
- `statement_timestamp()` khác nhau giữa hai câu `SELECT` vì chúng là hai statement riêng.
- `clock_timestamp()` phản ánh thời gian lúc gọi, thay đổi theo đồng hồ thực.

**Không khẳng định mọi lần gọi `clock_timestamp()` luôn trả số khác nhau**: nếu hai lần gọi sát nhau hơn độ phân giải của đồng hồ, có thể trùng về mặt giá trị. Điều khác biệt là PostgreSQL **không cam kết nó bất biến trong statement**.

### NOW() dùng trong lọc dữ liệu có sao không?

Hoàn toàn có thể:

~~~sql
SELECT order_id
FROM orders
WHERE expires_at < now();
~~~

`now()` là `STABLE`, nên là một mốc so sánh thích hợp trong statement. Nếu cần thời điểm thực thay đổi khi một truy vấn chạy rất lâu, phải xác định rõ yêu cầu và cân nhắc `clock_timestamp()`, với những đánh đổi về kế hoạch thực thi và tính nhất quán.

## 5. Chuẩn bị schema thực hành

Dùng một database PostgreSQL **riêng cho thực hành**. Đoạn này xóa schema `volatility_lab` nếu nó đã tồn tại; **không chạy trên database chứa dữ liệu thật hoặc schema dùng chung**.

~~~sql
-- CHỈ CHẠY TRONG DATABASE LAB CỦA BẠN.
DROP SCHEMA IF EXISTS volatility_lab CASCADE;
CREATE SCHEMA volatility_lab;

CREATE TABLE volatility_lab.customers (
    customer_id bigint PRIMARY KEY,
    email text NOT NULL UNIQUE,
    full_name text NOT NULL,
    segment text NOT NULL
        CHECK (segment IN ('standard', 'silver', 'gold'))
);

CREATE TABLE volatility_lab.orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES volatility_lab.customers(customer_id),
    status text NOT NULL
        CHECK (status IN ('pending', 'paid', 'cancelled')),
    amount numeric(12, 2) NOT NULL CHECK (amount >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL
);

CREATE INDEX idx_orders_customer
    ON volatility_lab.orders(customer_id);

CREATE INDEX idx_orders_expires
    ON volatility_lab.orders(expires_at);
~~~

Nạp dữ liệu:

~~~sql
INSERT INTO volatility_lab.customers
    (customer_id, email, full_name, segment)
VALUES
    (1, 'an@example.test', 'An', 'gold'),
    (2, 'binh@example.test', 'Binh', 'silver'),
    (3, 'chi@example.test', 'Chi', 'standard');

INSERT INTO volatility_lab.orders
    (order_id, customer_id, status, amount, expires_at)
VALUES
    (101, 1, 'paid',      120.00, now() - interval '1 day'),
    (102, 1, 'pending',    80.00, now() + interval '2 days'),
    (103, 2, 'pending',   200.00, now() - interval '2 hours'),
    (104, 3, 'cancelled',  40.00, now() + interval '1 day');
~~~

Bảng có ba khách hàng và bốn đơn:

| order_id | customer_id | status | amount | expires_at |
| ---: | ---: | --- | ---: | --- |
| 101 | 1 | paid | 120.00 | Một ngày trước khi seed |
| 102 | 1 | pending | 80.00 | Hai ngày sau khi seed |
| 103 | 2 | pending | 200.00 | Hai giờ trước khi seed |
| 104 | 3 | cancelled | 40.00 | Một ngày sau khi seed |

Không ghi cứng ngày giờ vì bài muốn minh họa tính chất **phụ thuộc thời gian**; các mốc được tính lúc seed. Kết quả của những ví dụ so sánh theo `now()` sẽ phụ thuộc thời gian trôi qua nếu để database lab chạy nhiều ngày. Có thể reset lab theo quy tắc an toàn ở đầu mục này để giữ các quan hệ thời gian ban đầu.

## 6. Tạo hàm IMMUTABLE: phép tính thuần

Ví dụ tính số tiền sau chiết khấu, khi cả số tiền và phần trăm đều được truyền vào hàm:

~~~sql
CREATE FUNCTION volatility_lab.net_amount(
    p_amount numeric,
    p_discount_percent numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT p_amount * (1 - p_discount_percent / 100)
$$;
~~~

Khai báo:

- `LANGUAGE sql`: thân hàm là một biểu thức SQL.
- `IMMUTABLE`: kết quả chỉ phụ thuộc `p_amount` và `p_discount_percent`.
- `STRICT`: nếu một đối số là NULL, hàm trả NULL mà không thực thi thân hàm.
- Hàm không đọc bảng, không phụ thuộc thời gian, cấu hình session hay trạng thái bên ngoài.

Dùng thử:

~~~sql
SELECT volatility_lab.net_amount(100.00, 10.00) AS result;
~~~

Kết quả: `90.0000` hoặc dạng numeric tương đương theo cách trình bày của client.

Với đơn hàng:

~~~sql
SELECT
    order_id,
    amount,
    volatility_lab.net_amount(amount, 10) AS discounted_amount
FROM volatility_lab.orders
ORDER BY order_id;
~~~

Giả sử mức giảm 10% được truyền như đối số rõ ràng, kết quả tuân công thức với từng `amount`.

**Hàm minh họa không kiểm tra phần trăm nằm trong khoảng 0–100.** Trong ứng dụng thật, validate ở tầng phù hợp hoặc thiết kế hàm để từ chối đầu vào không hợp lệ. `IMMUTABLE` không đồng nghĩa với “đúng quy tắc nghiệp vụ cho mọi giá trị”.

## 7. Vì sao phép tính này được gọi là IMMUTABLE?

Nếu chạy:

~~~sql
SELECT
    volatility_lab.net_amount(100, 10) AS a,
    volatility_lab.net_amount(100, 10) AS b;
~~~

thì `a` và `b` có cùng giá trị.

Đổi múi giờ, chèn đơn mới, thay phân khúc khách hàng hoặc gọi lại ngày mai **không đổi kết quả** của hai đối số trên. Đó là lời hứa mà `IMMUTABLE` cung cấp.

Một điểm sâu hơn: PostgreSQL có thể **tính trước** kết quả khi mọi đối số là hằng trong quá trình planning:

~~~sql
SELECT volatility_lab.net_amount(100, 10);
~~~

Hàm có thể được rút gọn thành kết quả tương đương `90` trong kế hoạch mà không phải gọi hàm theo từng hàng dữ liệu. Đây được gọi là **constant folding**.

Không phải mọi lần gọi hàm immutable đều được tính đúng một lần: nếu đối số là cột thay đổi theo từng hàng, PostgreSQL vẫn phải áp dụng hàm cho những giá trị tương ứng, trừ khi có cách tối ưu khác. Volatility chỉ **cho phép** một số biến đổi, không hứa một lịch thực thi cố định.

## 8. Tạo hàm STABLE: đọc dữ liệu trong bảng

Giả sử muốn lấy phân khúc hiện tại của khách hàng theo ID:

~~~sql
CREATE FUNCTION volatility_lab.customer_segment(
    p_customer_id bigint
)
RETURNS text
LANGUAGE sql
STABLE
AS $$
    SELECT c.segment
    FROM volatility_lab.customers AS c
    WHERE c.customer_id = p_customer_id
$$;
~~~

Dùng:

~~~sql
SELECT
    customer_id,
    volatility_lab.customer_segment(customer_id) AS segment
FROM volatility_lab.customers
ORDER BY customer_id;
~~~

Kết quả:

| customer_id | segment |
| ---: | --- |
| 1 | gold |
| 2 | silver |
| 3 | standard |

Tại sao không phải `IMMUTABLE`?

Vì kết quả phụ thuộc **dữ liệu bảng**. Cùng đối số `p_customer_id = 1`, hôm nay khách hàng có thể thuộc `gold`, nhưng tháng sau được đổi thành `standard`:

~~~sql
BEGIN;

UPDATE volatility_lab.customers
SET segment = 'standard'
WHERE customer_id = 1;

SELECT volatility_lab.customer_segment(1) AS segment_after_update;

ROLLBACK;
~~~

Câu `SELECT` riêng sau `UPDATE` trong cùng transaction sẽ quan sát phân khúc mới theo cơ chế nhìn thấy thay đổi của chính transaction. Sau `ROLLBACK`, lab quay về trạng thái ban đầu.

Hàm vẫn hợp với `STABLE` vì nó **chỉ đọc** và PostgreSQL có thể sử dụng snapshot của statement để đảm bảo cách nhìn dữ liệu nhất quán.

### STABLE không có nghĩa dữ liệu không bao giờ đổi

`STABLE` chỉ cam kết ổn định **trong một statement** cho cùng đối số và theo ngữ nghĩa snapshot phù hợp. Nó không cam kết cùng ID khách hàng giữ cùng phân khúc trong mọi ngày, mọi transaction hoặc mọi lần chạy prepared statement.

## 9. Tạo hàm VOLATILE: kết quả có thể thay đổi giữa các lần gọi

Ví dụ một hàm trả số ngẫu nhiên:

~~~sql
CREATE FUNCTION volatility_lab.sample_random()
RETURNS double precision
LANGUAGE sql
VOLATILE
AS $$
    SELECT random()
$$;
~~~

Gọi theo từng hàng:

~~~sql
SELECT
    n,
    volatility_lab.sample_random() AS random_value
FROM generate_series(1, 5) AS g(n);
~~~

Các giá trị có thể khác nhau giữa các hàng và giữa những lần chạy.

Một hàm VOLATILE khác trả đồng hồ thực:

~~~sql
CREATE FUNCTION volatility_lab.wall_clock()
RETURNS timestamptz
LANGUAGE sql
VOLATILE
AS $$
    SELECT clock_timestamp()
$$;
~~~

`VOLATILE` cho phép PostgreSQL hiểu rằng **không được coi kết quả là hằng** trong phạm vi mà lời gọi cần được đánh giá. Nó cũng là mức cần thiết khi thân hàm có thao tác ghi database hoặc gọi hàm có side effect, chẳng hạn `nextval()`.

**Không suy rằng mỗi lần gọi VOLATILE phải tạo giá trị khác nhau.** `random()` có thể tình cờ tạo hai giá trị bằng nhau; `clock_timestamp()` có thể trùng khi gọi quá sát. Cam kết là **có thể thay đổi**, không phải **bắt buộc khác nhau**.

## 10. VOLATILE là mặc định khi CREATE FUNCTION

Nếu không khai báo volatility:

~~~sql
CREATE FUNCTION volatility_lab.double_amount(
    p_amount numeric
)
RETURNS numeric
LANGUAGE sql
AS $$
    SELECT p_amount * 2
$$;
~~~

PostgreSQL mặc định hàm là **`VOLATILE`**, dù thân hàm trong ví dụ thực chất là phép tính thuần.

Điều đó thường **không khiến kết quả toán học sai**, nhưng có thể làm planner ít được phép tối ưu hơn và khiến hàm không dùng được ở những nơi yêu cầu immutable.

Nếu đây là hàm thuần và được triển khai đúng, khai báo chính xác:

~~~sql
CREATE OR REPLACE FUNCTION volatility_lab.double_amount(
    p_amount numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT p_amount * 2
$$;
~~~

Như vậy bài toán không phải “mặc định PostgreSQL tự đoán” mà là **người viết hàm phải cung cấp lời cam kết phù hợp**.

### IMMUTABLE mạnh hơn STABLE, STABLE mạnh hơn VOLATILE

Có thể nhìn ba mức như các lớp cho phép tối ưu:

~~~text
IMMUTABLE  → ổn định mãi theo đối số
   ↓
STABLE     → ổn định trong một statement
   ↓
VOLATILE   → có thể thay đổi trong một statement
~~~

Hàm thực sự immutable có thể bị đánh dấu stable hoặc volatile một cách bảo thủ, dù giảm cơ hội tối ưu. Ngược lại, **không được nâng một hàm volatile thành immutable** nếu hành vi thật không đáp ứng lời hứa.

## 11. Constant folding: planner tính trước kết quả

Hãy xem hai ví dụ:

~~~sql
SELECT volatility_lab.net_amount(100, 10);

SELECT volatility_lab.sample_random();
~~~

Ở ví dụ đầu, tham số là hằng và hàm được khai báo `IMMUTABLE`. PostgreSQL **có thể** đánh giá ngay khi planning và dùng kết quả trong execution plan.

Ở ví dụ thứ hai, `sample_random()` là `VOLATILE`. Planner không được thay lời gọi bằng một số cố định chỉ vì hàm không có đối số.

### STABLE và constant folding

Một hàm `STABLE` không nên được thay bằng hằng **bền vững qua nhiều lần thực thi plan**, bởi dữ liệu hay cấu hình mà nó đọc có thể thay đổi giữa các statement.

Ví dụ:

~~~sql
SELECT volatility_lab.customer_segment(1);
~~~

Hôm nay kết quả là `gold`; sau một lệnh `UPDATE` của transaction khác, statement mới có thể trả `silver`. Nếu planner đóng băng `gold` lâu dài vì hàm bị khai báo `IMMUTABLE` sai, ứng dụng nhận giá trị cũ.

Cần phân biệt:

- **Planner có thể dùng STABLE như giá trị ổn định trong quá trình chạy một statement**, nhất là điều kiện index scan.
- Nhưng **STABLE không được coi là hằng đúng mãi** để thay thế trong một cached plan tái sử dụng qua các lần thực thi.

## 12. Prepared statement và nguy cơ “giá trị cũ” do khai báo sai

Prepared statement và cached plan giúp ứng dụng tránh lặp lại một số công việc lập kế hoạch. Điều đó khiến volatility trở nên quan trọng.

Hãy hình dung một hàm:

~~~sql
-- MÔ TẢ SAI, KHÔNG TẠO HÀM NÀY:
-- CREATE FUNCTION bad_customer_segment(customer_id bigint)
-- RETURNS text
-- IMMUTABLE
-- AS $$ SELECT segment FROM customers WHERE id = customer_id $$;
~~~

Nếu một hàm đọc bảng bị **khai báo sai `IMMUTABLE`**, PostgreSQL có thể tính nó tại thời điểm lập kế hoạch khi đối số là hằng. Kế hoạch sau đó được sử dụng lại, trong khi bảng đã đổi.

Sơ đồ rủi ro:

~~~mermaid
flowchart TD
    A["Hàm đọc bảng nhưng bị khai báo IMMUTABLE sai"] --> B["Planner thấy đối số hằng"]
    B --> C["Có thể constant-fold giá trị lúc lập kế hoạch"]
    C --> D["Plan được cache / tái dùng"]
    D --> E["Bảng dữ liệu đã đổi"]
    E --> F["Kết quả từ plan có thể cũ hoặc sai"]
~~~

**Không có bảo đảm rằng lỗi sẽ lộ ra ngay trong từng truy vấn đơn giản.** Một số trường hợp có thể tình cờ cho kết quả đúng, khiến sai nhãn bị che giấu cho tới khi ứng dụng chạy prepared statement, plan cache, PL/pgSQL hoặc truy vấn tối ưu khác.

### Quy tắc chọn

- Hàm đọc bảng thay đổi theo thời gian → **`STABLE`** nếu chỉ đọc, ổn định theo snapshot statement.
- Hàm đọc biến cấu hình session → thường **`STABLE`**, không phải `IMMUTABLE`.
- Hàm gọi `random()`, `clock_timestamp()`, sequence hoặc có ghi dữ liệu → **`VOLATILE`**.
- Chỉ phép tính xác định từ đối số và không phụ thuộc trạng thái thay đổi → **`IMMUTABLE`**.

Nếu một hàm trả sai dữ liệu sau thay đổi bảng hoặc cấu hình, đừng lập tức “xóa cache” để che vấn đề; phải xem **volatility contract** có bị khai báo sai hay không.

## 13. STABLE giúp các điều kiện index scan

Giả sử bảng `orders` có B-tree index:

~~~sql
CREATE INDEX idx_orders_expires
ON volatility_lab.orders(expires_at);
~~~

Với câu truy vấn:

~~~sql
SELECT order_id, expires_at
FROM volatility_lab.orders
WHERE expires_at < now()
ORDER BY expires_at;
~~~

`now()` là `STABLE`. PostgreSQL có thể xem mốc so sánh là ổn định trong statement, nhờ vậy điều kiện `expires_at < now()` **có thể phù hợp với index scan** trên `expires_at`.

Điều đó không có nghĩa PostgreSQL **bắt buộc** dùng index. Với bảng có bốn hàng, quét tuần tự `Seq Scan` có thể rẻ hơn.

### So sánh với biểu thức VOLATILE

~~~sql
SELECT order_id
FROM volatility_lab.orders
WHERE expires_at < clock_timestamp();
~~~

`clock_timestamp()` có thể đổi giữa những lần được đánh giá. Nếu planner giả định nó là một mốc duy nhất dùng làm ranh giới index từ đầu rồi không tính lại, hành vi có thể khác với ngữ nghĩa VOLATILE.

Vì vậy những **index scan condition** đòi hỏi biểu thức phía so sánh phải thỏa mức ổn định phù hợp; hàm VOLATILE thường không được dùng như một **runtime index key bất biến trong cả scan** theo cách hàm STABLE được phép.

**Không nói tuyệt đối rằng truy vấn có VOLATILE sẽ không dùng bất kỳ index nào.** Nếu câu query có thêm điều kiện khác có thể dùng index, PostgreSQL vẫn có thể dùng index cho phần đó rồi áp bộ lọc VOLATILE riêng. Cần đọc execution plan thực tế.

## 14. Expression index yêu cầu hàm IMMUTABLE

**Expression index** lưu giá trị của một biểu thức tính từ cột bảng. PostgreSQL phải tin rằng, nếu các giá trị cột **không thay đổi**, biểu thức sẽ luôn cho **cùng kết quả**. Vì thế các hàm dùng trong biểu thức index phải có volatility phù hợp — thực tế là **`IMMUTABLE`**.

Ví dụ index hỗ trợ tìm email không phân biệt chữ hoa/thường theo cách dùng `lower`:

~~~sql
CREATE INDEX idx_customers_email_lower
ON volatility_lab.customers (lower(email));
~~~

Truy vấn:

~~~sql
SELECT customer_id, full_name
FROM volatility_lab.customers
WHERE lower(email) = lower('AN@EXAMPLE.TEST');
~~~

Vì biểu thức `lower(email)` có thể đưa vào index, PostgreSQL có một lựa chọn truy cập tối ưu khi số hàng và thống kê phù hợp.

### Index biểu thức từ hàm tự định nghĩa

~~~sql
CREATE INDEX idx_orders_net_amount
ON volatility_lab.orders (
    volatility_lab.net_amount(amount, 10::numeric)
);
~~~

`net_amount` đã được khai báo `IMMUTABLE` và kết quả chỉ phụ thuộc `amount` cùng hằng số 10, nên biểu thức này là ứng viên hợp lệ.

Điểm quan trọng: index lưu kết quả của **đúng biểu thức được định nghĩa**, không phải mọi phép tính gần giống. Planner cân nhắc việc biểu thức trong query có khớp với index, kiểu dữ liệu, thống kê và chi phí hay không.

### Ví dụ sai: đưa now() vào index expression

~~~sql
-- KHÔNG CHẠY: PostgreSQL sẽ từ chối vì now() không IMMUTABLE.
CREATE INDEX idx_bad_expiry_boolean
ON volatility_lab.orders ((expires_at < now()));
~~~

Biểu thức `expires_at < now()` có thể đổi từ false thành true chỉ vì thời gian trôi qua **mà không có UPDATE hàng**. Một index lưu giá trị boolean cũ sẽ không còn phản ánh sự thật.

Vì vậy không thể giải quyết bài toán “đơn đã hết hạn” bằng một expression index đóng băng trạng thái so sánh với `now()`.

### Cách đúng

Tạo index trên giá trị dữ liệu **bất biến giữa các lần sửa hàng**:

~~~sql
CREATE INDEX idx_orders_expires_at
ON volatility_lab.orders(expires_at);
~~~

Sau đó truy vấn với mốc động:

~~~sql
SELECT order_id
FROM volatility_lab.orders
WHERE expires_at < now();
~~~

Index trên `expires_at` có thể phục vụ so sánh với mốc `STABLE` được tính khi truy vấn chạy. Với bảng thực hành đã tạo `idx_orders_expires` tương đương, không cần giữ hai index giống nhau trong hệ thống thực tế.

## 15. Partial index: vị từ cũng cần IMMUTABLE

**Partial index** chỉ chứa hàng thỏa một điều kiện `WHERE` cố định tại thời điểm hệ thống duy trì index.

Ví dụ chỉ đánh index đơn đang ở trạng thái pending:

~~~sql
CREATE INDEX idx_orders_pending_expiry
ON volatility_lab.orders(expires_at)
WHERE status = 'pending';
~~~

Ở đây `status = 'pending'` chỉ phụ thuộc giá trị cột của hàng. Khi trạng thái được UPDATE, PostgreSQL cập nhật khả năng hàng có thuộc index hay không.

Một truy vấn phù hợp:

~~~sql
SELECT order_id
FROM volatility_lab.orders
WHERE status = 'pending'
  AND expires_at < now();
~~~

Có thể tận dụng partial index trong những điều kiện và kế hoạch phù hợp.

### Sai lầm: partial index “các hàng chưa hết hạn tính tới hiện tại”

~~~sql
-- KHÔNG CHẠY: now() là STABLE, không phải IMMUTABLE.
CREATE INDEX idx_bad_not_expired
ON volatility_lab.orders(order_id)
WHERE expires_at > now();
~~~

Vị từ `expires_at > now()` tự đổi giá trị khi thời gian trôi qua, dù bảng không có bản ghi nào được cập nhật. Vì thế nó không thể là tiêu chí duy trì membership bất biến của partial index theo cách PostgreSQL yêu cầu.

**Giải pháp:** index trên `expires_at`, hoặc một chỉ mục một phần dựa trên trạng thái được ứng dụng cập nhật theo quy tắc rõ ràng, rồi áp điều kiện thời gian trong truy vấn.

Không giả định có thể “lách” bằng cách tạo wrapper được đánh dấu `IMMUTABLE` nhưng bên trong vẫn gọi `now()`. Đó là **khai báo sai hợp đồng**, không phải tối ưu hợp lệ.

## 16. Generated column và volatility

Cột được sinh theo biểu thức (*generated column*) trong PostgreSQL có các yêu cầu tính toán nhất định. Với **stored generated column**, biểu thức sinh phải dùng các hàm có tính **`IMMUTABLE`** và phù hợp quy tắc biểu thức generated.

Ví dụ:

~~~sql
CREATE TABLE volatility_lab.price_examples (
    price_id bigint PRIMARY KEY,
    base_price numeric(12,2) NOT NULL
        CHECK (base_price >= 0),
    tax_rate numeric(5,4) NOT NULL
        CHECK (tax_rate BETWEEN 0 AND 1),
    final_price numeric
        GENERATED ALWAYS AS (
            base_price * (1 + tax_rate)
        ) STORED
);
~~~

Bảng chứa giá và tỷ lệ thuế đã được lưu như **dữ liệu đầu vào của mỗi hàng**. Khi một trong hai cột thay đổi, PostgreSQL tính lại `final_price`. Biểu thức chỉ dựa vào giá trị hàng nên phù hợp tính bất biến.

### Không dùng now() làm biểu thức generated

~~~sql
-- KHÔNG CHẠY: now() không IMMUTABLE và không phải
-- biểu thức generated thích hợp cho trạng thái thay đổi theo thời gian.
CREATE TABLE volatility_lab.bad_generated (
    expires_at timestamptz NOT NULL,
    is_expired boolean
        GENERATED ALWAYS AS (expires_at < now()) STORED
);
~~~

Nếu lưu `is_expired` ở một thời điểm mà không cập nhật hàng sau đó, giá trị sẽ cũ khi thời gian trôi qua.

### DEFAULT khác generated expression

Không được nhầm yêu cầu của generated column với **DEFAULT**.

~~~sql
CREATE TABLE volatility_lab.events (
    event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    transaction_time timestamptz NOT NULL DEFAULT now(),
    captured_clock timestamptz NOT NULL DEFAULT clock_timestamp()
);
~~~

`DEFAULT` được tính khi chèn hàng mà không cung cấp giá trị cột, nên có thể sử dụng cả những hàm **`STABLE`** hoặc **`VOLATILE`** theo quy tắc hợp lệ của biểu thức mặc định. Việc dùng `clock_timestamp()` trong DEFAULT không đòi hỏi nó phải được gắn sai nhãn `IMMUTABLE`.

## 17. CHECK constraint và giả định tính bất biến

Một `CHECK` constraint diễn tả quy tắc hợp lệ của **giá trị hàng**. PostgreSQL giả định điều kiện được dùng để kiểm tra hàng sẽ giữ ngữ nghĩa đúng khi dữ liệu của hàng không thay đổi.

Ví dụ hợp lý:

~~~sql
CREATE TABLE volatility_lab.accounts (
    account_id bigint PRIMARY KEY,
    balance numeric(12,2) NOT NULL
        CHECK (balance >= 0)
);
~~~

Nếu không cập nhật `balance`, trạng thái thỏa `balance >= 0` không tự đổi do thời gian.

### Anti-pattern: CHECK phụ thuộc now()

~~~sql
-- KHÔNG KHUYẾN NGHỊ: điều kiện tự thay đổi theo thời gian.
CREATE TABLE volatility_lab.bad_check (
    item_id bigint PRIMARY KEY,
    expires_at timestamptz NOT NULL,
    CHECK (expires_at > now())
);
~~~

Một hàng hợp lệ khi INSERT có thể trở thành “không hợp lệ” một ngày sau chỉ vì đồng hồ chạy, nhưng PostgreSQL **không tự duyệt lại mọi hàng để đánh giá lại CHECK theo thời gian**.

Với CHECK, PostgreSQL không cấm mọi cách sử dụng hàm không immutable theo cùng cơ chế chặt như expression index; chính vì vậy một định nghĩa có thể được chấp nhận nhưng mang **ngữ nghĩa nguy hiểm**. Các rủi ro gồm dữ liệu được xem là hợp lệ ở thời điểm khác nhau và vấn đề khi dump/restore hoặc thao tác cập nhật sau này.

Nếu nghiệp vụ yêu cầu “không cho tạo bản ghi đã hết hạn”, hãy dùng cơ chế kiểm tra **tại thời điểm thao tác** thích hợp; nếu muốn truy vấn bản ghi đang còn hiệu lực, dùng `WHERE expires_at > now()` và index trên `expires_at`. Không tự coi CHECK thời gian động là bộ hẹn giờ.

## 18. Snapshot bên trong hàm STABLE/IMMUTABLE và VOLATILE

PostgreSQL có một khác biệt tinh tế nhưng quan trọng khi hàm **thực thi truy vấn SQL** bên trong thân hàm:

- Hàm khai báo **`STABLE`** hoặc **`IMMUTABLE`** sử dụng snapshot được thiết lập tại lúc bắt đầu câu truy vấn gọi nó cho các truy vấn nó thực hiện.
- Hàm khai báo **`VOLATILE`** có thể lấy snapshot mới ở đầu mỗi truy vấn SQL bên trong thân hàm; vì vậy có khả năng quan sát những thay đổi xảy ra trong lúc câu truy vấn gọi đang thực hiện theo ngữ nghĩa PostgreSQL.

Điều này gắn với MVCC (*multi-version concurrency control*) chứ không chỉ là “có cache kết quả hàm hay không”.

### Vì sao STABLE phù hợp với đọc cấu hình từ bảng?

Ví dụ `customer_segment(customer_id)` đọc bảng `customers`. Trong một statement kéo dài, ta muốn các lần đọc đó có cách nhìn nhất quán theo snapshot của statement, thay vì một lần thấy phân khúc cũ và lần sau thấy phân khúc mới do transaction khác vừa commit.

`STABLE` giúp planner và executor có cơ sở xử lý nó như một phép đọc ổn định trong phạm vi statement.

### Vì sao VOLATILE cần snapshot linh hoạt?

Một hàm VOLATILE có thể ghi dữ liệu, gọi hàm có side effect hoặc thực hiện nhiều truy vấn cần quan sát trạng thái thay đổi. Việc không bị trói vào cam kết snapshot như hàm STABLE là một phần của ngữ nghĩa cho phép những hành vi đó.

**Lưu ý:** chi tiết nhìn thấy dữ liệu còn phụ thuộc mức isolation, kiểu câu SQL, khóa và kế hoạch thực thi. Đừng xây workflow dựa vào giả định “hàm VOLATILE luôn thấy mọi thay đổi từ mọi transaction ngay lập tức” — đó không phải mô tả đúng MVCC.

## 19. STABLE không được ghi database

Khi dùng `LANGUAGE sql` hoặc `LANGUAGE plpgsql`, các hàm **`STABLE`** và **`IMMUTABLE`** được ràng buộc ở mức không được thực hiện câu lệnh sửa dữ liệu như một hàm VOLATILE.

Ví dụ hàm ghi dữ liệu hợp lệ về ý nghĩa volatility:

~~~sql
CREATE FUNCTION volatility_lab.mark_order_paid(
    p_order_id bigint
)
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
    v_rows integer;
BEGIN
    UPDATE volatility_lab.orders
    SET status = 'paid'
    WHERE order_id = p_order_id
      AND status = 'pending';

    GET DIAGNOSTICS v_rows = ROW_COUNT;

    RETURN v_rows = 1;
END;
$$;
~~~

Thử trong transaction:

~~~sql
BEGIN;

SELECT volatility_lab.mark_order_paid(102) AS changed;
SELECT order_id, status
FROM volatility_lab.orders
WHERE order_id = 102;

ROLLBACK;
~~~

Với seed, đơn 102 là pending; hàm trả true và trạng thái tạm thành paid. Sau rollback, dữ liệu gốc được phục hồi.

Nếu đổi khai báo thành `STABLE` hoặc `IMMUTABLE` nhưng vẫn thực hiện UPDATE, hàm sẽ vi phạm quy tắc không sửa dữ liệu. Không nên sửa nhãn chỉ để planner “chạy nhanh”.

### Cần chú ý quyền

`VOLATILE` chỉ nói hàm **có thể** làm thay đổi dữ liệu. Nó **không cấp thêm quyền** cho role gọi hàm. Quyền thực tế phụ thuộc owner, quyền trên đối tượng, `SECURITY INVOKER`/`SECURITY DEFINER` và các chính sách bảo mật khác.

## 20. Một hàm STABLE có được dùng hàm VOLATILE bên trong không?

Về mặt **hợp đồng**, nếu một hàm gọi thành phần có khả năng thay đổi kết quả trong cùng statement hoặc có side effect, thì nhãn của hàm bao ngoài **không được cam kết mạnh hơn hành vi thực tế**.

Ví dụ không nên làm:

~~~sql
-- PHẢN VÍ DỤ VỀ THIẾT KẾ, KHÔNG TẠO:
-- CREATE FUNCTION bad_random()
-- RETURNS double precision
-- LANGUAGE sql
-- STABLE
-- AS $$ SELECT random() $$;
~~~

`random()` là VOLATILE; một wrapper trả thẳng giá trị random không trở thành STABLE chỉ vì người viết thêm từ khóa đó.

Tương tự, một wrapper quanh `clock_timestamp()` không phải IMMUTABLE hoặc STABLE nếu muốn giữ đúng ý nghĩa “đồng hồ tại thời điểm gọi”.

Trong một số trường hợp PostgreSQL không thể phân tích đầy đủ hành vi của hàm ở mọi ngôn ngữ/extension để ngăn toàn bộ khai báo sai. **Khả năng tạo function thành công không chứng minh nhãn volatility đúng.**

## 21. Cấu hình session và múi giờ có thể làm hàm không IMMUTABLE

Một hàm có vẻ chỉ biến đổi tham số đầu vào nhưng thực ra còn phụ thuộc vào **`TimeZone`**, `DateStyle`, collation hoặc cấu hình khác.

Ví dụ chuyển `timestamptz` thành ngày theo múi giờ session:

~~~sql
SELECT
    timestamptz '2026-11-14 00:30:00+00'::date;
~~~

Giá trị ngày thu được có thể khác theo `TimeZone` của session:

- Ở múi giờ UTC, thời điểm này là ngày 14/11.
- Ở một số múi giờ phía tây UTC, nó vẫn có thể là ngày 13/11.

Một wrapper chuyển thời gian theo múi giờ **session hiện tại** không thể được xem là IMMUTABLE chỉ vì đối số `timestamptz` không đổi.

### Date_trunc và kiểu timestamp

Hai biểu thức có ngữ nghĩa khác nhau:

~~~sql
-- timestamp WITHOUT time zone: thao tác trên mốc local đã truyền.
SELECT date_trunc(
    'day',
    timestamp '2026-11-14 12:30:00'
);

-- timestamptz: kết quả ngày phụ thuộc múi giờ dùng để diễn giải.
SELECT date_trunc(
    'day',
    timestamptz '2026-11-14 12:30:00+00'
);
~~~

Các overload của hàm có thể có volatility khác nhau. Với phiên bản phổ biến của PostgreSQL, `date_trunc(text, timestamp)` có thể là `IMMUTABLE`, trong khi `date_trunc(text, timestamptz)` là `STABLE` do phụ thuộc múi giờ session.

Đừng dựa vào tên `date_trunc` rồi suy mọi overload cùng một volatility. Phải xem **đúng chữ ký hàm và kiểu đối số**.

### Thiết kế biểu thức chỉ mục theo thời gian

Nếu cần index phân nhóm theo ngày, hãy xác định:

1. Kiểu cột là `timestamp` hay `timestamptz`.
2. “Ngày” là ngày UTC hay ngày theo một múi giờ nghiệp vụ cố định.
3. Biểu thức có đáp ứng IMMUTABLE hay không.
4. Nếu cấu hình/tzdata/collation thay đổi, index có cần được xây lại theo quy trình phù hợp không.

**Không bọc `date_trunc` phụ thuộc session trong một UDF gắn nhãn IMMUTABLE sai** chỉ để vượt kiểm tra index.

## 22. Hàm phụ thuộc dữ liệu ngoài database

Một hàm có thể đọc:

- Biến môi trường hoặc file cấu hình bên ngoài.
- Giá trị trả về từ mạng/API.
- Trạng thái của một hệ thống khác.
- Đồng hồ, nguồn random hoặc sequence.
- Nội dung một bảng có thể sửa.

Những nguồn đó có thể thay đổi **dù đối số hàm không đổi**. Do đó không được kết luận hàm là IMMUTABLE chỉ vì nó không có lệnh `UPDATE` trong thân SQL.

Ví dụ một hàm tra tỷ giá ngoại tệ theo endpoint web sẽ không trở thành IMMUTABLE nếu tỷ giá thay đổi mỗi phút. Trong một số môi trường, nguồn dữ liệu ngoài còn có hành vi không được snapshot của PostgreSQL bảo vệ; gắn nhãn STABLE cũng phải cân nhắc xem có thực sự ổn định trong statement hay không.

Khi có nghi ngờ, mặc định `VOLATILE` là lựa chọn an toàn về mặt tối ưu hóa. Chỉ hạ mức biến động khi **chứng minh được cam kết mạnh hơn**.

## 23. Volatility độc lập với STRICT, PARALLEL và COST

`CREATE FUNCTION` có những thuộc tính khác ngoài volatility:

| Thuộc tính | Câu hỏi nó trả lời |
| --- | --- |
| `IMMUTABLE` / `STABLE` / `VOLATILE` | Hàm thay đổi kết quả tới mức nào? |
| `STRICT` / `RETURNS NULL ON NULL INPUT` | Khi đối số NULL, có thể trả NULL mà không chạy thân hàm không? |
| `PARALLEL SAFE/RESTRICTED/UNSAFE` | Hàm có được chạy ở parallel worker không và với hạn chế nào? |
| `COST` | Ước lượng chi phí tương đối của một lần đánh giá hàm |
| `ROWS` | Ước lượng số hàng trả về với hàm set-returning |
| `SECURITY INVOKER/DEFINER` | Hàm chạy với quyền của ai? |
| `LEAKPROOF` | Một thuộc tính bảo mật đặc biệt, chỉ được dùng khi bảo đảm nghiêm ngặt |

Các thuộc tính này **không thay thế nhau**.

Một hàm `IMMUTABLE` chưa chắc an toàn chạy parallel nếu có hành vi khác không tương thích với parallel execution. Một hàm `VOLATILE` không đồng nghĩa mọi câu lệnh dùng nó bắt buộc bị loại khỏi parallel execution theo cùng một quy tắc giản đơn — hãy xem chính xác khai báo parallel safety và kế hoạch.

Với PostgreSQL, nhiều hàm do người dùng định nghĩa mặc định **`VOLATILE`** và **`PARALLEL UNSAFE`** nếu không khai báo khác. Không đánh dấu `PARALLEL SAFE` chỉ vì đã đánh dấu `IMMUTABLE`; cần đánh giá độc lập.

### Ví dụ STRICT

~~~sql
SELECT
    volatility_lab.net_amount(NULL::numeric, 10::numeric)
        AS null_result;
~~~

`net_amount` khai báo `STRICT`, nên kết quả là NULL khi một đối số NULL. Điều này không liên quan trực tiếp tới việc kết quả ổn định theo thời gian.

## 24. Xem volatility thật qua catalog pg_proc

PostgreSQL lưu metadata của function trong catalog `pg_proc`. Trường `provolatile` có mã:

| Mã | Volatility |
| --- | --- |
| `i` | `IMMUTABLE` |
| `s` | `STABLE` |
| `v` | `VOLATILE` |

Truy vấn những hàm đã tạo ở lab:

~~~sql
SELECT
    n.nspname AS schema_name,
    p.proname AS function_name,
    pg_get_function_identity_arguments(p.oid) AS arguments,
    CASE p.provolatile
        WHEN 'i' THEN 'IMMUTABLE'
        WHEN 's' THEN 'STABLE'
        WHEN 'v' THEN 'VOLATILE'
    END AS volatility
FROM pg_proc AS p
JOIN pg_namespace AS n
    ON n.oid = p.pronamespace
WHERE n.nspname = 'volatility_lab'
ORDER BY p.proname, arguments;
~~~

Ví dụ đầu ra có:

- `net_amount(numeric, numeric)` → `IMMUTABLE`.
- `customer_segment(bigint)` → `STABLE`.
- `sample_random()` → `VOLATILE`.
- `wall_clock()` → `VOLATILE`.
- `mark_order_paid(bigint)` → `VOLATILE`.
- `double_amount(numeric)` → `IMMUTABLE` sau khi thay bằng `CREATE OR REPLACE`.

### Xem chính xác built-in theo chữ ký

~~~sql
SELECT
    p.oid::regprocedure AS function_signature,
    p.provolatile,
    CASE p.provolatile
        WHEN 'i' THEN 'IMMUTABLE'
        WHEN 's' THEN 'STABLE'
        WHEN 'v' THEN 'VOLATILE'
    END AS volatility
FROM pg_proc AS p
WHERE p.oid IN (
    'pg_catalog.now()'::regprocedure,
    'pg_catalog.statement_timestamp()'::regprocedure,
    'pg_catalog.clock_timestamp()'::regprocedure,
    'pg_catalog.random()'::regprocedure,
    'pg_catalog.nextval(regclass)'::regprocedure,
    'pg_catalog.current_setting(text)'::regprocedure
)
ORDER BY function_signature::text;
~~~

Cách này dựa trên đúng **signature**, tránh nhầm các overload cùng tên nhưng khác kiểu tham số.

Trong `psql`, có thể dùng meta-command `\df+ volatility_lab.*` để xem thông tin function, hoặc `\sf volatility_lab.net_amount` để xem định nghĩa nguồn. Đây là lệnh của `psql`, không phải câu SQL chuẩn gửi từ JDBC.

## 25. EXPLAIN: quan sát tác động với kế hoạch truy vấn

Câu lệnh `EXPLAIN` giúp xem planner dự định xử lý query thế nào.

Ví dụ với một điều kiện STABLE:

~~~sql
EXPLAIN
SELECT order_id, expires_at
FROM volatility_lab.orders
WHERE expires_at < now();
~~~

So với điều kiện dùng VOLATILE:

~~~sql
EXPLAIN
SELECT order_id, expires_at
FROM volatility_lab.orders
WHERE expires_at < clock_timestamp();
~~~

Nếu có index trên `expires_at` và bảng đủ lớn, bạn có thể quan sát sự khác nhau giữa `Index Cond` và `Filter` trong một số kế hoạch. Điều cần rút ra là planner có quyền đối xử khác với hai biểu thức vì **`now()` ổn định**, còn `clock_timestamp()` có thể đổi trong lúc thực thi.

**Không cam kết trong lab bốn hàng sẽ hiện Index Scan**. Planner chọn kế hoạch theo chi phí, và Seq Scan thường rẻ hơn khi bảng nhỏ.

### EXPLAIN ANALYZE thực sự chạy

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id
FROM volatility_lab.orders
WHERE expires_at < now();
~~~

Với `SELECT` chỉ đọc, ví dụ thích hợp để quan sát số hàng và bộ đệm.

Nhưng:

~~~sql
-- KHÔNG chạy trên dữ liệu thật chỉ để xem plan:
EXPLAIN (ANALYZE)
UPDATE volatility_lab.orders
SET status = 'paid'
WHERE order_id = 102;
~~~

`EXPLAIN ANALYZE` **thực sự thực thi UPDATE**. Nếu muốn đo thay đổi trong lab, bọc bằng `BEGIN ... ROLLBACK`; đừng ngộ nhận `EXPLAIN` có `ANALYZE` là chế độ mô phỏng không ghi.

## 26. Hiệu năng không chỉ do volatility

Khi một truy vấn gọi UDF trên nhiều hàng, chi phí còn phụ thuộc:

1. Hàm có được SQL function inlining hay không.
2. Thân hàm có truy vấn bảng hay chỉ tính toán số học.
3. Có index hỗ trợ biểu thức/điều kiện không.
4. Thống kê cardinality và độ chọn lọc của điều kiện.
5. Có điều kiện lọc bớt hàng trước khi đánh giá hàm không.
6. Planner có thể tái sử dụng biểu thức, rút gọn hằng hoặc thay đổi thứ tự đánh giá không.
7. Hàm được gọi bao nhiêu lần trong **kế hoạch thực tế**, không chỉ số lần xuất hiện trong văn bản SQL.
8. Cấu hình parallel safety, COST và ngữ cảnh gọi hàm.

Ví dụ:

~~~sql
SELECT
    o.order_id,
    volatility_lab.customer_segment(o.customer_id)
FROM volatility_lab.orders AS o;
~~~

Một hàm STABLE đọc bảng theo từng `customer_id` có thể vẫn tốn chi phí nếu được gọi nhiều lần. Đôi khi **JOIN trực tiếp** rõ ràng và hiệu quả hơn:

~~~sql
SELECT
    o.order_id,
    c.segment
FROM volatility_lab.orders AS o
JOIN volatility_lab.customers AS c
    ON c.customer_id = o.customer_id;
~~~

Cả hai truy vấn có thể cùng ý nghĩa trên dữ liệu hợp lệ, nhưng cách biểu diễn bằng JOIN giúp planner thấy quan hệ dữ liệu rõ hơn trong nhiều trường hợp.

**Đừng dùng UDF để che một JOIN quan trọng rồi kỳ vọng chỉ cần gắn nhãn STABLE là tối ưu tự động.** So sánh kế hoạch trên dữ liệu thực tế.

## 27. Đánh giá biểu thức và tác dụng phụ: đừng dựa vào số lần gọi

Người mới đôi khi viết một hàm VOLATILE có side effect rồi đặt nó ở `WHERE` hoặc `SELECT`, mong rằng nó được gọi **chính xác một lần cho từng hàng của bảng gốc**.

Ví dụ:

~~~sql
SELECT
    order_id,
    random() AS sample_value
FROM volatility_lab.orders
WHERE status = 'pending';
~~~

Hàm `random()` được đánh giá khi cần tạo giá trị cho những hàng kết quả. Nhưng việc PostgreSQL chọn kế hoạch, đẩy biểu thức, sắp xếp, lọc hoặc thực hiện các phép biến đổi hợp lệ vẫn có thể ảnh hưởng thời điểm/số lời gọi trong các truy vấn phức tạp.

### Quy tắc thực hành

- Không dùng side effect ẩn trong một hàm được gọi từ `WHERE` để điều phối nghiệp vụ quan trọng.
- Không suy số lần gọi chính xác chỉ từ số hàng ban đầu của bảng.
- Nếu cần ghi audit/movement, dùng SQL `INSERT`/`UPDATE` rõ ràng, transaction và `RETURNING` phù hợp.
- Nếu cần một giá trị random duy nhất dùng cho nhiều bước, hãy **sinh và truyền nó như dữ liệu rõ ràng**, thay vì mặc định mọi lời gọi `random()` tự chia sẻ giá trị.

Volatility giúp planner biết **được phép tối ưu gì**, nhưng không thay thế một hợp đồng nghiệp vụ về side effect hoặc số lần xử lý.

## 28. IMMUTABLE không có nghĩa an toàn khi phụ thuộc thư viện/môi trường thay đổi

Một số phép tính phụ thuộc vào quy tắc ngoài biểu thức trực tiếp, ví dụ:

- Collation của hệ điều hành hoặc ICU.
- Phiên bản extension xử lý text/Unicode.
- Quy tắc timezone/tzdata.
- Thay đổi thuật toán trong một phiên bản code deploy mới.

Một hàm được xem immutable theo môi trường hiện tại có thể cần **đánh giá lại chỉ mục** nếu ý nghĩa so sánh hoặc thuật toán của nó thay đổi sau nâng cấp.

Ví dụ `lower(email)` trong expression index sử dụng quy tắc case conversion/collation. Khi hệ thống nâng cấp collation/ICU hoặc định nghĩa function được thay đổi, có thể cần **REINDEX** hoặc kế hoạch tái xây dựng index để dữ liệu index phù hợp ngữ nghĩa mới.

**Không thay đổi thân một hàm IMMUTABLE đang được dùng trong expression index mà mặc định index đã tự tính lại toàn bộ các khóa cũ.** Đây là vấn đề bảo trì dữ liệu/chỉ mục, khác với việc hàm hoạt động đúng trên những dòng mới.

## 29. Function volatility và tính nhất quán trong transaction

Một transaction có thể gồm nhiều statement:

~~~sql
BEGIN;

SELECT volatility_lab.customer_segment(1);

UPDATE volatility_lab.customers
SET segment = 'silver'
WHERE customer_id = 1;

SELECT volatility_lab.customer_segment(1);

ROLLBACK;
~~~

Hai câu `SELECT` có thể trả giá trị khác nhau: trước UPDATE là `gold`, sau UPDATE là `silver`. Điều đó **không vi phạm STABLE**, bởi lời hứa chỉ áp dụng trong phạm vi **một statement**, không phải toàn transaction.

Trong khi đó:

~~~sql
BEGIN;

SELECT now();
SELECT pg_sleep(0.2);
SELECT now();

ROLLBACK;
~~~

hai giá trị `now()` là cùng mốc bắt đầu transaction. Đây là **đặc tính cụ thể của hàm now()**, mạnh hơn yêu cầu tối thiểu của nhãn STABLE.

Nếu một hàm cần biết thời điểm bắt đầu statement thay vì transaction, PostgreSQL có `statement_timestamp()`. Nếu cần đồng hồ thực thay đổi theo thời gian thực thi, có `clock_timestamp()`. Chọn đúng **ngữ nghĩa thời gian**, không chọn theo sở thích về tên.

## 30. Những sai lầm phổ biến

### 30.1. Gắn IMMUTABLE cho hàm đọc bảng để “chạy nhanh”

Dữ liệu bảng có thể đổi, nên kết quả có thể khác giữa các statement. Gắn IMMUTABLE sai có thể làm cached plan trả giá trị cũ.

### 30.2. Nghĩ now() là VOLATILE vì tên “bây giờ”

`now()` là STABLE trong PostgreSQL, trả thời điểm bắt đầu transaction. `clock_timestamp()` mới là hàm đọc đồng hồ thực VOLATILE.

### 30.3. Dùng now() trong expression index

Biểu thức `expires_at < now()` thay đổi chỉ vì thời gian, nên không phù hợp yêu cầu IMMUTABLE của expression index.

### 30.4. Dùng now() trong partial index predicate

`WHERE expires_at > now()` không là điều kiện membership bất biến theo giá trị hàng. Thay bằng index trên `expires_at` và filter động khi truy vấn.

### 30.5. Dùng CHECK thời gian động để tưởng dữ liệu tự hết hạn

`CHECK (expires_at > now())` có thể đúng khi INSERT nhưng không được tự đánh giá lại theo thời gian. CHECK không phải scheduler.

### 30.6. Quên rằng CREATE FUNCTION mặc định VOLATILE

Hàm thuần nếu không khai báo sẽ bị gắn mức dè dặt nhất. Có thể mất cơ hội constant folding hoặc dùng trong expression index.

### 30.7. Gắn STABLE cho wrapper quanh random()

Hàm bao ngoài có thể thay đổi trong cùng statement nên phải theo contract VOLATILE tương ứng.

### 30.8. Nhầm STABLE với “giữ nguyên trong cả transaction”

STABLE cam kết trong một statement; một hàm đọc bảng có thể trả kết quả khác ở statement tiếp theo trong cùng transaction sau khi dữ liệu được cập nhật.

### 30.9. Nhầm IMMUTABLE với “không có đối số”

Hàm không có tham số vẫn có thể đọc giờ, bảng hoặc cấu hình, nên không có lý do mặc định để gọi là immutable.

### 30.10. Nghĩ IMMUTABLE tự làm hàm chạy nhanh trong mọi trường hợp

Tính chất này cho phép tối ưu, nhưng hàm có thể tốn CPU/I/O; planner còn dựa vào COST, index, data distribution và execution plan.

### 30.11. Coi mọi overload cùng tên có cùng volatility

`date_trunc` với `timestamp` và `timestamptz` có khác biệt vì múi giờ. Kiểm tra chữ ký trong `pg_proc`.

### 30.12. Dùng VOLATILE để bảo đảm hàm gọi đúng một lần mỗi hàng gốc

Quy tắc đánh giá biểu thức trong truy vấn phức tạp không thể thay bằng giả định đơn giản đó. Nếu cần side effect chắc chắn, thiết kế thao tác DML/transaction rõ ràng.

### 30.13. Dùng IMMUTABLE để né yêu cầu generated column

Một wrapper có nhãn immutable nhưng thực tế gọi `now()` hay đọc bảng vẫn sai; chức năng có thể được tạo thành công nhưng kết quả index/generated column trở nên không đáng tin.

### 30.14. Thay code hàm immutable mà quên dữ liệu index cũ

Nếu function dùng trong expression index đổi cách tính, các khóa đã lưu không tự được tính lại ngay lập tức cho mọi hàng. Cần kế hoạch cập nhật/reindex.

### 30.15. Nhầm volatility với parallel safety và quyền bảo mật

Một function immutable không tự có nghĩa `PARALLEL SAFE` hoặc an toàn với `SECURITY DEFINER`. Đây là các hợp đồng khác nhau.

### 30.16. Bỏ qua MVCC/snapshot

Hàm STABLE đọc bảng với snapshot của statement; không nên thiết kế nó để thấy mọi cập nhật giữa chừng của các phiên khác. Đối với các yêu cầu đọc/ghi phức tạp, phải hiểu isolation và transaction.

## 31. Bài tập thực hành có đáp án

Các bài sau dùng `volatility_lab` đã tạo ở mục 5, trừ những ví dụ chỉ là câu hỏi khái niệm.

### Bài 1. Chọn volatility cho hàm cộng hai số

~~~sql
CREATE FUNCTION volatility_lab.add_numbers(
    a numeric, b numeric
)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
STRICT
AS $$
    SELECT a + b
$$;
~~~

**Đáp án:** `IMMUTABLE` vì chỉ phụ thuộc hai đối số, không đọc dữ liệu thay đổi, không có side effect.

### Bài 2. Chọn volatility cho hàm tra hạng khách hàng

Hàm đọc `segment` từ bảng `customers` theo `customer_id`.

**Đáp án:** `STABLE` khi chỉ đọc bảng và cần kết quả nhất quán trong một statement. Không dùng `IMMUTABLE` vì bảng có thể đổi giữa những statement.

### Bài 3. Chọn volatility cho random()

~~~sql
SELECT random() FROM generate_series(1, 3);
~~~

**Đáp án:** `VOLATILE`. PostgreSQL không được xem random là hằng chỉ vì không có đối số.

### Bài 4. now() hay clock_timestamp() cho thời gian thực?

Một hàm phải trả giờ thực ngay khi mỗi lần gọi, kể cả trong cùng transaction.

**Đáp án:** `clock_timestamp()`, thuộc `VOLATILE`. `now()` trả thời điểm bắt đầu transaction.

### Bài 5. Vì sao expression index này sai?

~~~sql
CREATE INDEX bad_idx
ON volatility_lab.orders ((expires_at < now()));
~~~

**Đáp án:** `now()` là STABLE, không IMMUTABLE; thời gian trôi qua làm kết quả thay đổi mà không có UPDATE hàng. Dùng index trên `expires_at`.

### Bài 6. Partial index trạng thái pending

Viết index chỉ phục vụ các đơn có trạng thái pending, sắp theo hạn:

~~~sql
CREATE INDEX idx_exercise_pending_expiry
ON volatility_lab.orders(expires_at)
WHERE status = 'pending';
~~~

**Đáp án:** Vị từ chỉ phụ thuộc `status` của hàng, phù hợp; còn điều kiện `expires_at < now()` có thể được áp ở truy vấn.

### Bài 7. Nếu bỏ volatility khi CREATE FUNCTION?

**Đáp án:** PostgreSQL mặc định là `VOLATILE`. Nếu hàm thuần, cần khai báo `IMMUTABLE` phù hợp để mở cơ hội tối ưu.

### Bài 8. Vì sao hàm đọc TimeZone không immutable?

~~~sql
SELECT current_setting('TimeZone');
~~~

**Đáp án:** Kết quả có thể thay đổi khi cấu hình session đổi, dù không có đối số của hàm thay đổi. Vì thế không thể cam kết same arguments → same result forever.

### Bài 9. Xem volatility thực tế của now()

~~~sql
SELECT
    proname,
    provolatile
FROM pg_proc
WHERE oid = 'pg_catalog.now()'::regprocedure;
~~~

**Đáp án:** `provolatile = 's'`, nghĩa là `STABLE`.

### Bài 10. Hàm UPDATE status nên khai báo gì?

Hàm có thân:

~~~sql
UPDATE volatility_lab.orders
SET status = 'paid'
WHERE order_id = p_order_id;
~~~

**Đáp án:** `VOLATILE` vì thực hiện thay đổi dữ liệu; việc khai báo STABLE/IMMUTABLE sẽ không đúng contract.

### Bài 11. Vì sao cached plan có thể nguy hiểm khi khai báo sai?

Một hàm lấy giá từ bảng được đánh dấu IMMUTABLE. Lần đầu trả 100; giá đổi thành 120; prepared statement vẫn có thể giữ giá 100.

**Đáp án:** Planner có thể constant-fold IMMUTABLE với đối số hằng tại planning và tái dùng kết quả trong cached plan. Hàm đọc bảng thay đổi phải có nhãn phù hợp, thường là STABLE.

### Bài 12. Generated column cho tổng có thuế

~~~sql
CREATE TABLE volatility_lab.invoice_lines (
    line_id bigint PRIMARY KEY,
    amount numeric(12,2) NOT NULL,
    tax_rate numeric(5,4) NOT NULL,
    total numeric
        GENERATED ALWAYS AS (amount * (1 + tax_rate)) STORED
);
~~~

**Đáp án:** Biểu thức dựa trên dữ liệu cùng hàng và phép toán immutable nên phù hợp. Không thay `amount * ...` bằng biểu thức `now()` chỉ để lấy thời điểm hiện tại.

### Bài 13. Hai statement trong một transaction có phải cùng snapshot của STABLE?

**Đáp án:** Không được suy như vậy. `STABLE` có lời hứa ổn định trong **mỗi statement**; snapshot và khả năng nhìn thấy thay đổi của statement sau còn theo isolation/transaction. `now()` giữ nguyên trong transaction là tính chất riêng của nó.

### Bài 14. Vì sao không nên gắn IMMUTABLE cho wrapper ngày local?

Hàm nhận `timestamptz` rồi trả `::date` theo TimeZone của session.

**Đáp án:** Cùng thời điểm tuyệt đối có thể ra ngày khác nếu TimeZone thay đổi. Nên biểu diễn múi giờ nghiệp vụ tường minh và phân loại hàm theo hành vi thật.

### Bài 15. Hàm STABLE có thể trả giá trị mới ở statement sau không?

~~~sql
BEGIN;
SELECT volatility_lab.customer_segment(1);
UPDATE volatility_lab.customers
SET segment = 'silver'
WHERE customer_id = 1;
SELECT volatility_lab.customer_segment(1);
ROLLBACK;
~~~

**Đáp án:** Có. Statement sau trong transaction thấy cập nhật của chính mình; hàm STABLE không cam kết bất biến qua nhiều statement.

### Bài 16. Index có được planner bắt buộc dùng nếu WHERE có now() STABLE?

**Đáp án:** Không. `STABLE` làm biểu thức đủ điều kiện cho một số index scan, nhưng planner vẫn so chi phí; trên bảng nhỏ có thể chọn seq scan.

## 32. Quy trình phân loại function khi viết dự án thực tế

Khi tạo hoặc sửa một function trong PostgreSQL, làm theo trình tự:

1. **Liệt kê mọi nguồn phụ thuộc:** đối số, bảng, sequence, thời gian, random, cấu hình, file/mạng, extension, collation.
2. **Kiểm tra side effect:** hàm có INSERT/UPDATE/DELETE hoặc gọi hàm ghi dữ liệu không?
3. **Hỏi mức bất biến dài hạn:** cùng đối số có luôn cho cùng kết quả ngay cả khi dữ liệu/cấu hình/thời gian đổi không?
4. **Nếu có, chọn IMMUTABLE** và chỉ khi có thể chứng minh.
5. **Nếu không, hỏi ổn định trong một statement:** hàm chỉ đọc, phù hợp snapshot statement và không có khả năng đổi kết quả trong cùng statement không?
6. **Nếu có, chọn STABLE**; nếu không, chọn VOLATILE.
7. **Kiểm tra các hàm được gọi bên trong:** wrapper không được cam kết mạnh hơn thành phần thực tế quyết định kết quả.
8. **Kiểm tra overload/kiểu tham số:** cùng tên hàm có thể có volatility khác nhau.
9. **Xác định ngữ cảnh dùng:** ordinary SELECT, index condition, expression/partial index, generated column, DEFAULT, CHECK hay prepared plan.
10. **Đánh giá độc lập các thuộc tính khác:** STRICT, PARALLEL, COST, quyền, SECURITY DEFINER.
11. **Quan sát catalog và plan:** `pg_proc.provolatile`, `EXPLAIN`, biểu thức `Index Cond`/`Filter`.
12. **Kiểm tra tình huống biên:** thay bảng giữa hai statement, thay TimeZone, nhiều phiên, prepared statement, NULL, upgrade extension/collation.
13. **Lập kế hoạch nếu đổi định nghĩa hàm:** biểu thức chỉ mục hoặc dữ liệu sinh sẵn có thể cần tính lại, migration phải đảm bảo nhất quán.
14. **Không chạy thử DML nguy hiểm ngoài lab:** dùng transaction và rollback cho thí nghiệm.

Quy trình này làm rõ hai câu hỏi tách biệt: **hàm thực sự cam kết điều gì** và **planner có thể tận dụng lời cam kết đó vào việc gì**.

## 33. Tài liệu PostgreSQL chính thức

Đối với một hệ thống thật, nên đối chiếu tài liệu đúng **major version PostgreSQL** đang vận hành:

- [Function Volatility Categories](https://www.postgresql.org/docs/current/xfunc-volatility.html): định nghĩa IMMUTABLE, STABLE, VOLATILE và quy tắc snapshot.
- [CREATE FUNCTION](https://www.postgresql.org/docs/current/sql-createfunction.html): cú pháp khai báo volatility, STRICT, PARALLEL, COST.
- [Indexes on Expressions](https://www.postgresql.org/docs/current/indexes-expressional.html): chỉ mục trên biểu thức.
- [Partial Indexes](https://www.postgresql.org/docs/current/indexes-partial.html): chỉ mục có điều kiện.
- [Generated Columns](https://www.postgresql.org/docs/current/ddl-generated-columns.html): quy tắc biểu thức generated.
- [Date/Time Functions](https://www.postgresql.org/docs/current/functions-datetime.html): now, statement_timestamp, clock_timestamp, date_trunc.
- [System Catalog pg_proc](https://www.postgresql.org/docs/current/catalog-pg-proc.html): trường provolatile và các metadata của hàm.
- [Using EXPLAIN](https://www.postgresql.org/docs/current/using-explain.html): phân tích kế hoạch truy vấn.

Tài liệu `/current/` trỏ đến phiên bản PostgreSQL hiện hành trên website. Khi soạn migration hoặc chẩn đoán server cũ, thay `current` bằng số phiên bản tương ứng để tránh áp dụng nhầm tính năng/cú pháp mới.

## 34. Tổng kết

Ba mức volatility là **hợp đồng giữa người viết hàm và PostgreSQL planner**:

| Mức | Ghi nhớ ngắn | Ứng dụng điển hình |
| --- | --- | --- |
| **`IMMUTABLE`** | Cùng đối số, cùng kết quả lâu dài | Phép toán thuần; expression index; biểu thức generated |
| **`STABLE`** | Cùng đối số, kết quả ổn định trong một statement | `now()`, đọc bảng, đọc cấu hình; điều kiện index scan |
| **`VOLATILE`** | Kết quả/side effect có thể thay đổi giữa các lần gọi | `random()`, `clock_timestamp()`, `nextval()`, hàm thay đổi dữ liệu |

**Sự khác biệt quan trọng nhất với tối ưu hóa:**

- `IMMUTABLE` cho phép planner **tính trước biểu thức hằng** và là mức cần thiết cho các biểu thức phải bất biến như khóa expression index.
- `STABLE` cho phép coi biểu thức là ổn định trong một statement, nên có thể dùng làm mốc so sánh cho các index scan thích hợp.
- `VOLATILE` buộc PostgreSQL tôn trọng khả năng biến động/side effect, không được tùy tiện đóng băng giá trị theo giả định nó không đổi.
- Khai báo sai có thể dẫn tới **kết quả stale hoặc không chính xác**, đặc biệt với cached plan, index và dữ liệu generated.

Chọn mức **mạnh nhất mà hành vi thật sự của hàm có thể bảo đảm**, không chọn mức mạnh nhất chỉ để hy vọng truy vấn nhanh hơn. Khi volatility đúng, planner có thêm cơ hội tối ưu mà vẫn duy trì tính nhất quán của dữ liệu và ý nghĩa nghiệp vụ.
