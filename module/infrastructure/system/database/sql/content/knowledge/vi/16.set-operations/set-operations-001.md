# Điều kiện tương thích số cột và kiểu dữ liệu trong phép toán tập hợp SQL

Khi cần gộp kết quả của nhiều truy vấn, SQL cung cấp các **phép toán tập hợp** như `UNION`, `UNION ALL`, `INTERSECT` và `EXCEPT` (trong Oracle, `MINUS` là tên quen thuộc cho phép lấy hiệu). Ví dụ, hệ thống bán hàng muốn xem một danh sách đơn hàng chung từ kênh trực tuyến và cửa hàng, hoặc tìm đơn xuất hiện ở cả hai nguồn dữ liệu.

Nhưng không phải hai câu `SELECT` bất kỳ đều có thể đặt cạnh nhau bằng `UNION`. Chúng phải đáp ứng những điều kiện về **hình dạng kết quả** và **kiểu dữ liệu**:

1. Mỗi nhánh phải trả về **cùng số cột**.
2. Các cột được ghép **theo vị trí**, không phải theo tên.
3. Tại mỗi vị trí, các giá trị phải có **kiểu dữ liệu tương thích** theo quy tắc của hệ quản trị.
4. Với phép toán loại trùng hoặc so sánh tập, DBMS còn phải có khả năng **xác định các giá trị/dòng có bằng nhau hay không**.

Bài học tập trung vào cách đọc các điều kiện này, phát hiện lỗi, chuẩn hóa kiểu bằng `CAST`, xử lý `NULL` và các kiểu nâng cao, cũng như các khác biệt đáng chú ý giữa PostgreSQL, MySQL/MariaDB, SQL Server, Oracle và SQLite.

> Các ví dụ chính dùng **PostgreSQL** và bảng tạm để học trực tiếp. Các DBMS khác có quy tắc ép kiểu, chọn kiểu kết quả và hỗ trợ toán tử tập hợp riêng; truy vấn chạy được ở hệ này chưa chắc đúng cú pháp hoặc cùng ý nghĩa ở hệ khác.

## 1. Phép toán tập hợp nối các *hàng kết quả*, không phải nối bảng theo khóa

Cấu trúc tổng quát:

```sql
SELECT expression_1, expression_2, ...
FROM source_a
UNION ALL
SELECT expression_1, expression_2, ...
FROM source_b;
```

Hai nhánh `SELECT` tạo ra các tập hàng có cùng hình dạng. Toán tử tập hợp xử lý các hàng kết quả đó, khác với `JOIN` là phép nối **các cột của các hàng** theo quan hệ khớp.

| Toán tử | Ý nghĩa cơ bản | Có loại dòng trùng không? |
|---|---|---|
| `UNION` | Hợp các hàng từ hai nhánh | Có, mặc định là `DISTINCT` |
| `UNION ALL` | Ghép tất cả các hàng từ hai nhánh | Không |
| `INTERSECT` | Chỉ lấy các hàng có ở cả hai nhánh | Có, trong dạng mặc định |
| `EXCEPT` | Lấy các hàng thuộc nhánh trái nhưng không thuộc nhánh phải | Có, trong dạng mặc định |
| `MINUS` | Tên phép lấy hiệu trong Oracle và một số phương ngữ | Hành vi chi tiết tùy phiên bản |

Nếu viết `UNION`, DBMS phải xét các hàng trùng nhau để loại bản sao. Với `UNION ALL`, một hàng giống nhau ở hai nhánh vẫn có thể xuất hiện hai lần. Các biến thể `INTERSECT ALL` hoặc `EXCEPT ALL` tồn tại ở một số DBMS, nhưng **không được mọi hệ quản trị hỗ trợ**; phần này tập trung vào điều kiện tương thích chung cho các phép toán.

Điều kiện tương thích được áp dụng **trước khi có thể hiểu kết quả hợp/hiệu/giao**. Nếu một nhánh trả ba cột còn nhánh kia hai cột, SQL không thể tự đoán cột nào nên được ghép với cột nào.

## 2. Dữ liệu mẫu: đơn hàng từ hai kênh

Dùng hai bảng có cấu trúc tương tự để quan sát các phép tập hợp:

```sql
-- PostgreSQL: bảng tạm dùng trong phiên hiện tại.
CREATE TEMP TABLE demo_web_orders (
    order_id INTEGER NOT NULL,
    customer_name TEXT NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    placed_on DATE NOT NULL,
    status TEXT NOT NULL
);

CREATE TEMP TABLE demo_store_orders (
    order_id INTEGER NOT NULL,
    customer_name TEXT NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    placed_on DATE NOT NULL,
    status TEXT NOT NULL
);

INSERT INTO demo_web_orders
    (order_id, customer_name, amount, placed_on, status)
VALUES
    (101, 'An',   150, DATE '2026-11-01', 'PAID'),
    (102, 'Bình', 200, DATE '2026-11-02', 'PENDING'),
    (103, 'Chi',  300, DATE '2026-11-03', 'PAID');

INSERT INTO demo_store_orders
    (order_id, customer_name, amount, placed_on, status)
VALUES
    (102, 'Bình', 200, DATE '2026-11-02', 'PENDING'),
    (201, 'Dũng', 450, DATE '2026-11-04', 'PAID'),
    (202, 'Hà',   180, DATE '2026-11-05', 'CANCELLED');
```

Dữ liệu:

| Nguồn | order_id | customer_name | amount | placed_on | status |
|---|---:|---|---:|---|---|
| Web | 101 | An | 150 | 2026-11-01 | PAID |
| Web | 102 | Bình | 200 | 2026-11-02 | PENDING |
| Web | 103 | Chi | 300 | 2026-11-03 | PAID |
| Store | 102 | Bình | 200 | 2026-11-02 | PENDING |
| Store | 201 | Dũng | 450 | 2026-11-04 | PAID |
| Store | 202 | Hà | 180 | 2026-11-05 | CANCELLED |

Dòng `order_id = 102` được cố ý lặp **toàn bộ năm giá trị** ở hai nguồn để minh họa việc loại trùng của `UNION`. Trong hệ thống thực tế, cùng số ID ở hai hệ nguồn không nhất thiết là cùng một đơn hàng; không nên coi việc `UNION` tự loại trùng là giải pháp đối soát danh tính dữ liệu.

### 2.1. UNION ALL: ghép đủ sáu hàng

```sql
SELECT order_id, customer_name, amount, placed_on, status
FROM demo_web_orders

UNION ALL

SELECT order_id, customer_name, amount, placed_on, status
FROM demo_store_orders

ORDER BY order_id, customer_name;
```

Kết quả có **6 hàng**, gồm hai dòng ID 102. Hai nhánh đều trả **5 cột** theo cùng thứ tự và các cột tương ứng có kiểu giống nhau, nên kết quả phù hợp phép tập hợp.

### 2.2. UNION: loại dòng trùng toàn bộ

```sql
SELECT order_id, customer_name, amount, placed_on, status
FROM demo_web_orders

UNION

SELECT order_id, customer_name, amount, placed_on, status
FROM demo_store_orders

ORDER BY order_id, customer_name;
```

Kết quả có **5 hàng**: chỉ một bản sao của bộ giá trị `(102, 'Bình', 200, 2026-11-02, 'PENDING')`. `UNION` không loại hai hàng chỉ vì `order_id` giống nhau; việc xác định trùng xét **tất cả các cột được chọn**.

### 2.3. INTERSECT và EXCEPT dùng cùng hình dạng cột

```sql
-- Những dòng xuất hiện trong cả hai nguồn.
SELECT order_id, customer_name, amount, placed_on, status
FROM demo_web_orders

INTERSECT

SELECT order_id, customer_name, amount, placed_on, status
FROM demo_store_orders;
-- Một dòng: 102, Bình, 200, 2026-11-02, PENDING.
```

```sql
-- Những dòng thuộc Web nhưng không xuất hiện giống hệt ở Store.
SELECT order_id, customer_name, amount, placed_on, status
FROM demo_web_orders

EXCEPT

SELECT order_id, customer_name, amount, placed_on, status
FROM demo_store_orders

ORDER BY order_id;
-- Hai dòng: ID 101 và 103.
```

`EXCEPT` có tính hướng: `Web EXCEPT Store` có thể khác `Store EXCEPT Web`. Trong hai ví dụ, điều kiện **số cột và kiểu dữ liệu** vẫn giống nhau bất kể chọn `UNION`, `INTERSECT` hay `EXCEPT`.

## 3. Điều kiện thứ nhất: các nhánh phải có cùng số cột

Giả sử nhánh đầu chọn ba cột, nhánh sau chỉ hai:

```sql
-- PostgreSQL: SAI, số cột khác nhau.
SELECT order_id, customer_name, amount
FROM demo_web_orders

UNION ALL

SELECT order_id, amount
FROM demo_store_orders;
```

Một nhánh có cấu trúc:

```text
(order_id, customer_name, amount)   → 3 cột
```

còn nhánh kia:

```text
(order_id, amount)                 → 2 cột
```

DBMS không thể tạo một hàng kết quả thống nhất từ những cấu trúc này. PostgreSQL báo lỗi dạng “each UNION query must have the same number of columns”.

### 3.1. Cách sửa: chọn cùng các cột ở cả hai nhánh

```sql
SELECT order_id, customer_name, amount
FROM demo_web_orders

UNION ALL

SELECT order_id, customer_name, amount
FROM demo_store_orders

ORDER BY order_id;
```

Bây giờ mỗi nhánh có **3 cột**, và cột thứ nhất là mã đơn, thứ hai tên khách, thứ ba số tiền.

### 3.2. Nguồn không có một thuộc tính: thêm cột giả có kiểu rõ

Giả sử dữ liệu từ hệ thống cũ chưa có `customer_name`, còn dữ liệu mới có. Muốn xuất cả hai theo schema gồm ba cột, nhánh cũ có thể bổ sung `NULL` ở vị trí tên khách.

```sql
-- Minh họa hai nguồn có thông tin không đồng đều.
SELECT
    order_id,
    customer_name,
    amount
FROM demo_web_orders

UNION ALL

SELECT
    order_id,
    NULL::TEXT AS customer_name,
    amount
FROM demo_store_orders;
```

Cả hai nhánh có ba cột; nhánh Store chủ động biểu diễn “tên khách chưa có trong nguồn” bằng `NULL` kiểu `TEXT`. Trong ví dụ dữ liệu Store thực tế có tên, nên ta chỉ dùng câu SQL này để mô phỏng **một nguồn thiếu thuộc tính**. Không nên thay giá trị có thật bằng `NULL` trong truy vấn sản xuất.

Trong SQL tương đối portable, dùng `CAST`:

```sql
SELECT
    order_id,
    customer_name,
    amount
FROM demo_web_orders

UNION ALL

SELECT
    order_id,
    CAST(NULL AS VARCHAR(100)) AS customer_name,
    amount
FROM demo_store_orders;
```

**`NULL` không phải chỗ trống vô danh.** Việc thêm một cột `NULL` là quyết định về ý nghĩa dữ liệu. Không dùng số 0 hoặc chuỗi rỗng để “lấp cho đủ cột” nếu đó có thể là một giá trị thật khiến báo cáo sai.

### 3.3. Tên cột và alias không tự tạo thêm cột

```sql
SELECT
    order_id AS id,
    customer_name AS name
FROM demo_web_orders

UNION ALL

SELECT
    order_id AS order_identifier,
    customer_name AS full_name
FROM demo_store_orders;
```

Mỗi nhánh vẫn có **2 cột**. `AS id` hoặc `AS name` chỉ đặt tên đầu ra, không ảnh hưởng số lượng cột. Ở phần lớn DBMS, tên cột **kết quả cuối** của phép tập hợp thường lấy từ **nhánh SELECT đầu tiên**, còn alias của nhánh sau không biến thành một cột mới.

### 3.4. SELECT * là nguồn lỗi khi schema thay đổi

```sql
-- Rủi ro nếu hai bảng không còn cùng cấu trúc.
SELECT * FROM demo_web_orders
UNION ALL
SELECT * FROM demo_store_orders;
```

Hôm nay hai bảng cùng năm cột nên có thể chạy. Nhưng nếu một bảng được thêm cột `discount` hoặc đổi thứ tự cột, `SELECT *` có thể:

- Làm số cột của hai nhánh khác nhau → lỗi.
- Giữ cùng số cột nhưng đổi vị trí → ghép nhầm dữ liệu hoặc lỗi kiểu.
- Làm hợp đồng cột trả về của ứng dụng thay đổi ngoài ý muốn.

Với phép tập hợp dùng trong API, view hoặc báo cáo, nên **liệt kê rõ các cột ở từng nhánh** để quản lý schema đầu ra.

## 4. Điều kiện thứ hai: ghép theo vị trí, không ghép theo tên

Trong `UNION`, hai cột được đối chiếu vì chúng đứng cùng **vị trí thứ n**, không vì chúng có cùng tên.

Ví dụ:

```sql
SELECT
    order_id,
    customer_name,
    amount
FROM demo_web_orders

UNION ALL

SELECT
    order_id,
    amount,
    customer_name
FROM demo_store_orders;
```

Nhánh Web trả:

```text
(1) INTEGER order_id
(2) TEXT    customer_name
(3) NUMERIC amount
```

Nhánh Store trả:

```text
(1) INTEGER order_id
(2) NUMERIC amount
(3) TEXT    customer_name
```

Cột thứ hai phải thống nhất giữa `TEXT` và `NUMERIC`, cột thứ ba cũng vậy. Trong PostgreSQL, truy vấn này thường bị từ chối do không thể ghép các nhóm kiểu đó trong `UNION`. Nhưng trên những DBMS có cơ chế ép kiểu rộng hơn, câu truy vấn có thể được ép kiểu hoặc cho lỗi chuyển đổi lúc thực thi. **Không xem việc truy vấn chạy được là bằng chứng các vị trí cột đã đúng về nghiệp vụ.**

### 4.1. Nguy hiểm hơn: đảo hai cột cùng kiểu

Xét hai cột `customer_name` và `status` đều là `TEXT`:

```sql
-- SAI về ý nghĩa dù các vị trí có kiểu tương thích.
SELECT
    customer_name,
    status
FROM demo_web_orders

UNION ALL

SELECT
    status,
    customer_name
FROM demo_store_orders;
```

DBMS không có lý do báo lỗi kiểu: cả hai cột ở mỗi vị trí đều là `TEXT`. Tuy nhiên, một hàng Store sẽ xuất hiện như:

| customer_name (tên từ nhánh đầu) | status (tên từ nhánh đầu) |
|---|---|
| PAID | Dũng |

Hàng đó đặt trạng thái `PAID` vào cột có nhãn `customer_name` và tên `Dũng` vào cột `status`. Lỗi này **khó phát hiện hơn lỗi cú pháp** vì câu SQL chạy thành công nhưng dữ liệu sai.

Cách sửa là đặt các biểu thức **theo cùng thứ tự ý nghĩa**:

```sql
SELECT customer_name, status
FROM demo_web_orders

UNION ALL

SELECT customer_name, status
FROM demo_store_orders;
```

Hãy coi danh sách đầu ra là một **hợp đồng theo vị trí**, ví dụ:

```text
Cột 1 = order_id       (INTEGER)
Cột 2 = customer_name  (TEXT)
Cột 3 = amount         (NUMERIC)
Cột 4 = placed_on      (DATE)
Cột 5 = status         (TEXT)
```

Mọi nhánh phải thực hiện đúng hợp đồng ấy.

## 5. Điều kiện thứ ba: kiểu dữ liệu ở từng vị trí phải tương thích

Cùng số cột mới chỉ giải quyết hình dạng. SQL còn phải xác định kiểu dữ liệu của từng cột kết quả sau khi gộp hai hoặc nhiều nhánh.

Ví dụ hợp lệ trong PostgreSQL:

```sql
SELECT 1::INTEGER AS amount
UNION ALL
SELECT 2.50::NUMERIC(10,2) AS amount;
```

Hai nhánh có một cột kiểu số. PostgreSQL có quy tắc tìm **kiểu chung** cho những kiểu tương thích; biểu thức kết quả có thể được nâng sang loại số đáp ứng cả hai đầu vào.

Ngược lại:

```sql
-- PostgreSQL: kiểu đã khai báo rõ là INTEGER và TEXT,
-- không có kiểu chung hợp lệ cho UNION ở đây.
SELECT 101::INTEGER AS value
UNION ALL
SELECT 'A101'::TEXT AS value;
```

PostgreSQL báo lỗi không thể so khớp kiểu dữ liệu tương ứng. SQL không có quy tắc chung “cứ khác kiểu thì tự chuyển hết thành chuỗi”; từng DBMS có hệ thống chuyển kiểu riêng.

### 5.1. Bảng minh họa tương thích theo họ kiểu

| Cột từ nhánh A | Cột từ nhánh B | Đánh giá cần làm |
|---|---|---|
| `SMALLINT` | `INTEGER` | Thường có kiểu số chung thích hợp |
| `INTEGER` | `NUMERIC(p,s)` | Thường có thể nâng kiểu; kiểm tra độ chính xác/scale |
| `VARCHAR(30)` | `TEXT` hoặc `VARCHAR(100)` | Thường tương thích trong cùng họ ký tự |
| `DATE` | `DATE` | Cùng kiểu, thường phù hợp |
| `DATE` | `TIMESTAMP` | Nhiều hệ hỗ trợ chuyển đổi, nhưng phải hiểu thời điểm nửa đêm/múi giờ |
| `TIMESTAMP WITHOUT TIME ZONE` | `TIMESTAMP WITH TIME ZONE` | Cần quy tắc múi giờ rõ, không chuyển ngầm tùy tiện |
| `INTEGER` | `TEXT` | Không portable; PostgreSQL thường không có kiểu chung |
| `DATE` | `TEXT` | Không nên dựa vào việc tự parse chuỗi; chủ động `CAST` |
| `UUID` | `TEXT` | Khác kiểu về ý nghĩa; cần chuyển đổi tường minh theo mục tiêu |
| `JSON` | `JSONB` | PostgreSQL có khác biệt về phép so sánh và kiểu, cần chọn rõ định dạng |
| Kiểu mảng SQL | Kiểu chuỗi | Không phải cùng cấu trúc; không nên tự ghép chỉ vì cùng biểu diễn văn bản |

“Thường tương thích” không có nghĩa có kết quả giống nhau trên mọi hệ. **Việc xác định kiểu kết quả** phụ thuộc hệ quy tắc chuyển đổi của từng DBMS, cả độ dài, precision/scale, collation và đôi khi là ngữ cảnh hàm/tên cột.

### 5.2. Kiểu kết quả không nhất thiết trùng kiểu nhánh đầu

```sql
-- PostgreSQL
SELECT amount, pg_typeof(amount) AS resulting_type
FROM (
    SELECT 10::INTEGER AS amount
    UNION ALL
    SELECT 25.75::NUMERIC(12,2) AS amount
) AS combined;
```

`pg_typeof` là hàm PostgreSQL, cho phép quan sát kiểu của biểu thức sau khi DBMS đã phân giải kiểu chung. Nói chung, không được giả định “nhánh đầu chọn INTEGER nên toàn bộ kết quả chắc chắn INTEGER”.

Khi dữ liệu tiền tệ, thuế hay báo cáo cần **độ chính xác thập phân**, nên chuyển các nhánh về cùng kiểu `NUMERIC/DECIMAL` và scale phù hợp, thay vì phụ thuộc vào pha trộn số nguyên/số thực một cách ngầm định.

## 6. Dùng CAST để chuẩn hóa kiểu dữ liệu

`CAST(expression AS target_type)` chủ động chuyển kiểu của một biểu thức trước khi tham gia phép tập hợp.

### 6.1. Chuẩn hóa số nguyên và số thập phân

```sql
SELECT
    order_id,
    CAST(amount AS NUMERIC(14,2)) AS amount
FROM demo_web_orders

UNION ALL

SELECT
    order_id,
    CAST(amount AS NUMERIC(14,2)) AS amount
FROM demo_store_orders;
```

Cả hai nhánh có cùng **hai cột**; cột thứ hai cùng kiểu mục tiêu. Ví dụ bảng mẫu vốn đã là `NUMERIC(12,2)` nên câu này mang tính minh họa cho việc chuẩn hóa schema chung từ những nguồn có kiểu khác nhau.

Nếu một nguồn lưu số tiền bằng chuỗi như `'200.50'`, có thể chuyển bằng `CAST(raw_amount AS NUMERIC(14,2))` **chỉ khi dữ liệu đầu vào được bảo đảm hợp lệ**. Chuỗi như `'N/A'` hoặc `'abc'` có thể làm truy vấn báo lỗi; cần quy trình làm sạch/kiểm tra dữ liệu, không đơn giản ghép chuỗi rồi mong DB tự đoán.

### 6.2. Chuẩn hóa các kiểu ký tự

```sql
SELECT CAST(customer_name AS VARCHAR(200)) AS customer_name
FROM demo_web_orders

UNION ALL

SELECT CAST(customer_name AS VARCHAR(200)) AS customer_name
FROM demo_store_orders;
```

Độ dài `VARCHAR(200)` trong ví dụ là **quy ước đầu ra**, không có nghĩa mọi hệ quản trị sẽ giữ nguyên metadata độ dài sau phép set operation. Một số hệ chọn độ dài dựa trên cả hai nhánh; một số có luật riêng cho chuỗi có độ dài cố định và không cố định.

Khi dùng Unicode và dữ liệu tiếng Việt, cần chú ý kiểu ký tự phù hợp và **collation**. SQL Server phân biệt `VARCHAR` và `NVARCHAR`; Oracle có các kiểu chuỗi riêng; MySQL có charset/collation cho cột và biểu thức. Đừng ép dữ liệu Unicode về một kiểu/charset không hỗ trợ dấu tiếng Việt.

### 6.3. Chuẩn hóa ngày và timestamp

Giả sử một nguồn có `DATE` còn nguồn kia có `TIMESTAMP`. Trước khi `UNION ALL`, phải chọn mục đích:

- Muốn **ngày lịch**: chuyển timestamp về `DATE`, chấp nhận mất phần giờ.
- Muốn **ngày giờ**: chuyển date thành timestamp ở một mốc quy ước, thường là nửa đêm, với múi giờ được xác định nếu có timestamp kèm múi giờ.
- Muốn **hiển thị văn bản**: chuyển cả hai về chuỗi định dạng nhất quán, nhưng lúc đó kết quả không còn là giá trị ngày/giờ để tính toán.

Ví dụ PostgreSQL ép cùng kiểu `DATE`:

```sql
SELECT placed_on::DATE AS event_day
FROM demo_web_orders

UNION ALL

SELECT placed_on::DATE AS event_day
FROM demo_store_orders;
```

Ví dụ mô phỏng nguồn thứ hai có thời gian đầy đủ:

```sql
SELECT DATE '2026-11-01' AS event_day

UNION ALL

SELECT CAST(TIMESTAMP '2026-11-02 15:30:00' AS DATE) AS event_day;
```

Kết quả chỉ giữ ngày `2026-11-01` và `2026-11-02`. Đây không phải chuyển đổi trung tính: thông tin 15:30 đã bị bỏ. Nếu thông tin giờ quan trọng, chọn kiểu timestamp cho cả hai nhánh thay vì ép về `DATE`.

### 6.4. Chuyển đổi kiểu có thể thất bại hoặc làm mất thông tin

| Chuyển đổi | Nguy cơ |
|---|---|
| `TEXT` → `INTEGER` | Chuỗi không phải số, tràn miền số |
| `NUMERIC` → `INTEGER` | Mất phần thập phân, quy tắc làm tròn/ép kiểu khác DBMS |
| `TIMESTAMP` → `DATE` | Mất giờ, phút, giây |
| `TIMESTAMPTZ` → `DATE` | Ngày có thể đổi theo múi giờ |
| `TEXT` → `DATE` | Định dạng mơ hồ, phụ thuộc quy tắc parse |
| `VARCHAR(200)` → `VARCHAR(20)` | Có thể bị từ chối hoặc cắt ngắn, tùy ngữ cảnh/DBMS |
| `UUID` → `TEXT` | Mất kiểu định danh đặc thù ở kết quả |
| `JSON` → `TEXT` | Kết quả trở thành văn bản, không còn ngữ nghĩa JSON gốc |

**`CAST` giải quyết tương thích kiểu, không tự giải quyết đúng/sai về nghiệp vụ.** Chọn kiểu chung phải bảo toàn dữ liệu mà các ứng dụng dùng tiếp thực sự cần.

## 7. NULL và literal chưa xác định kiểu

Đôi khi một nhánh cần thêm cột mà nguồn chưa có. Có thể viết `NULL`:

```sql
SELECT
    order_id,
    customer_name,
    amount
FROM demo_web_orders

UNION ALL

SELECT
    order_id,
    NULL AS customer_name,
    amount
FROM demo_store_orders;
```

Trong PostgreSQL, `NULL` chưa được ép kiểu rõ thường có thể nhận kiểu từ cột tương ứng ở nhánh kia. Tuy nhiên, khi truy vấn có nhiều nhánh, nhiều `NULL` hoặc các literal chưa rõ kiểu, **nên ép kiểu rõ ràng** để tránh bất ngờ.

```sql
SELECT
    order_id,
    customer_name,
    amount
FROM demo_web_orders

UNION ALL

SELECT
    order_id,
    CAST(NULL AS TEXT) AS customer_name,
    amount
FROM demo_store_orders;
```

Nếu cả hai nhánh chỉ có literal `NULL` mà không có cột có kiểu làm mốc, DBMS phải tự phân giải kiểu kết quả. PostgreSQL thường có quy tắc chọn kiểu mặc định cho literal chưa xác định (ví dụ `TEXT` ở những ngữ cảnh phù hợp), nhưng các hệ khác có thể có cách suy luận khác. Khi tạo view, CTE dùng lại hoặc xuất API, nên chỉ định kiểu đầu ra tường minh:

```sql
SELECT CAST(NULL AS INTEGER) AS order_id,
       CAST(NULL AS NUMERIC(14,2)) AS amount
WHERE FALSE

UNION ALL

SELECT order_id,
       CAST(amount AS NUMERIC(14,2))
FROM demo_web_orders;
```

Nhánh đầu là một **khung schema có kiểu** nhưng không trả hàng vì `WHERE FALSE`. Nhánh thứ hai trả dữ liệu thật. Ví dụ này minh họa cách công bố kiểu đầu ra; trong ứng dụng thực tế, thường có thể đơn giản hơn bằng cách `CAST` trực tiếp từng cột của các nguồn.

### 7.1. Literal ngày dạng chuỗi có thể được hiểu khác với TEXT đã định kiểu

Trên PostgreSQL:

```sql
-- Literal '2026-11-02' chưa được định kiểu rõ có thể
-- được ép theo DATE ở nhánh kia.
SELECT DATE '2026-11-01' AS event_day
UNION ALL
SELECT '2026-11-02' AS event_day;
```

Nhưng:

```sql
-- TEXT đã định kiểu rõ không tự trở thành DATE trong UNION.
SELECT DATE '2026-11-01' AS event_day
UNION ALL
SELECT '2026-11-02'::TEXT AS event_day;
```

Câu thứ hai có thể báo lỗi phân giải kiểu ở PostgreSQL. Hai trường hợp khác nhau vì **literal chưa xác định kiểu** không giống một giá trị đã có kiểu `TEXT`. Tránh dựa vào các quy tắc suy luận ngầm phức tạp khi dữ liệu đến từ nhiều nguồn: viết kiểu đích rõ ràng.

## 8. UNION ALL và UNION có thêm yêu cầu về so sánh trùng

Hãy phân biệt:

- `UNION ALL`: cần ghép các cột có kiểu kết quả phù hợp, **không cần loại bản sao**.
- `UNION`, `INTERSECT`, `EXCEPT` dạng phân biệt: phải đánh giá liệu các dòng có **trùng nhau** hay không theo quy tắc của DBMS.

Điều này đặc biệt quan trọng với kiểu dữ liệu phức tạp.

### 8.1. Ví dụ PostgreSQL với kiểu JSON

PostgreSQL có hai kiểu JSON phổ biến:

- `JSON`: giữ biểu diễn JSON gần với văn bản đầu vào và không có toán tử so sánh bằng mặc định theo cách mà phép `UNION DISTINCT` yêu cầu.
- `JSONB`: dạng JSON được chuẩn hóa để thao tác, có phép so sánh phù hợp hơn trong nhiều ngữ cảnh.

Ví dụ PostgreSQL:

```sql
-- Có thể ghép hai giá trị JSON nếu không cần khử trùng.
SELECT '{"a":1}'::JSON AS payload
UNION ALL
SELECT '{"a":1}'::JSON AS payload;
```

Nhưng:

```sql
-- PostgreSQL: UNION cần phát hiện các JSON bằng nhau;
-- kiểu JSON không cung cấp toán tử so sánh phù hợp.
SELECT '{"a":1}'::JSON AS payload
UNION
SELECT '{"a":1}'::JSON AS payload;
```

Câu `UNION` trên có thể báo lỗi vì không xác định được cách so sánh bằng cho kiểu `JSON`. Một phương án là chuyển về `JSONB` khi ngữ nghĩa `JSONB` đúng với yêu cầu:

```sql
SELECT '{"a":1}'::JSONB AS payload
UNION
SELECT '{"a":1}'::JSONB AS payload;
```

Kết quả chỉ còn một giá trị JSONB tương đương. Nhưng **chuyển JSON → JSONB không phải thay đổi vô nghĩa**: thứ tự khóa đối tượng, khóa trùng và một số chi tiết biểu diễn có thể được chuẩn hóa. Chỉ chọn sau khi hiểu loại dữ liệu cần giữ.

### 8.2. Cột phức tạp và khả năng so sánh

Ngoài JSON, một số hệ có kiểu dữ liệu không hỗ trợ so sánh theo cách phép set operation dạng `DISTINCT` cần, như một số kiểu đối tượng, kiểu nhị phân lớn, XML hoặc kiểu không có toán tử bằng/sắp phù hợp.

Vì vậy, “cùng số cột và cùng kiểu” là **điều kiện cần**, nhưng đôi khi **chưa đủ**. Khi `UNION ALL` chạy mà `UNION` không chạy, hãy nghĩ tới yêu cầu **khử trùng/so sánh dòng**, không chỉ tên kiểu.

Trong nhiều trường hợp, nếu nghiệp vụ cho phép giữ toàn bộ hàng, `UNION ALL` vừa đơn giản hơn vừa tránh chi phí loại trùng; nhưng không dùng `UNION ALL` chỉ để né một lỗi khi thực tế cần phát hiện bản ghi trùng.

## 9. NULL được coi là trùng trong phép tập hợp như thế nào?

Phép so sánh thông thường trong SQL:

```sql
SELECT NULL::INTEGER = NULL::INTEGER;
-- Kết quả logic UNKNOWN, không phải TRUE.
```

Nhưng khi `UNION` hoặc `INTERSECT` xác định **dòng trùng**, các giá trị `NULL` tại vị trí tương ứng được coi là **không phân biệt** với nhau cho mục đích tập hợp. Đây không phải mâu thuẫn: `=` tuân theo logic ba giá trị, còn phép tập hợp có quy tắc xác định các dòng tương đương.

```sql
-- PostgreSQL: còn một hàng NULL vì UNION loại trùng.
SELECT NULL::INTEGER AS value
UNION
SELECT NULL::INTEGER AS value;
```

```sql
-- PostgreSQL: còn hai hàng NULL vì UNION ALL giữ bản sao.
SELECT NULL::INTEGER AS value
UNION ALL
SELECT NULL::INTEGER AS value;
```

```sql
-- PostgreSQL: giao của hai tập đều chứa NULL là một hàng NULL.
SELECT NULL::INTEGER AS value
INTERSECT
SELECT NULL::INTEGER AS value;
```

```sql
-- PostgreSQL: hiệu rỗng vì hàng NULL đã xuất hiện ở bên phải.
SELECT NULL::INTEGER AS value
EXCEPT
SELECT NULL::INTEGER AS value;
```

Với nhiều cột, phép loại trùng xét **toàn bộ bộ giá trị**. Ví dụ `(NULL, 'A')` và `(NULL, 'B')` không phải cùng dòng vì cột thứ hai khác. `(NULL, 'A')` và `(NULL, 'A')` là trùng theo quy tắc tập hợp.

Điều đó có ảnh hưởng đến API và báo cáo: nếu một cột phân biệt nguồn không có, hai bản ghi thiếu ID nhưng có các thuộc tính khác giống nhau có thể bị `UNION` gộp thành một, dù ứng dụng thực tế muốn giữ cả hai.

## 10. Thêm cột nguồn dữ liệu làm thay đổi ý nghĩa loại trùng

Trong bảng mẫu, hai nguồn có cùng hàng ID 102. Nếu cần **giữ dấu vết nguồn**, hãy thêm một cột nguồn vào **cả hai** nhánh:

```sql
SELECT
    order_id,
    customer_name,
    amount,
    placed_on,
    status,
    'WEB'::TEXT AS source_channel
FROM demo_web_orders

UNION ALL

SELECT
    order_id,
    customer_name,
    amount,
    placed_on,
    status,
    'STORE'::TEXT AS source_channel
FROM demo_store_orders

ORDER BY order_id, source_channel;
```

Bây giờ kết quả có **6 cột** và 6 hàng. Cột thứ sáu là chuỗi văn bản ở hai nhánh; `ORDER BY` dùng tên cột đầu ra.

Đáng chú ý, nếu đổi `UNION ALL` thành `UNION`, cả hai dòng ID 102 **vẫn không trùng toàn bộ**, vì `source_channel` là `WEB` ở một dòng và `STORE` ở dòng kia. Do đó `UNION` cũng trả 6 dòng trong ví dụ này.

**Phép tập hợp không tự hiểu khóa chính hoặc danh tính liên hệ giữa hai nguồn.** Nó so sánh đúng các cột mà bạn chọn. Muốn hợp nhất bản ghi khách hàng hoặc đơn hàng từ nhiều hệ thống, cần một quy tắc định danh và hợp nhất riêng, không chỉ đổi `UNION ALL` thành `UNION`.

### 10.1. Bổ sung cột thiếu đúng vị trí

Một nguồn không có trạng thái nhưng có số tiền:

```sql
SELECT
    order_id,
    customer_name,
    amount,
    status
FROM demo_web_orders

UNION ALL

SELECT
    order_id,
    customer_name,
    amount,
    CAST(NULL AS TEXT) AS status
FROM demo_store_orders;
```

Bốn cột ở cả hai nhánh khớp theo thứ tự. Nếu nhầm đặt `NULL AS status` ở vị trí thứ ba, trong khi cột thứ ba bên trên là `amount`, ta có thể gặp lỗi kiểu hoặc dữ liệu sai. Khi chuẩn hóa nguồn, hãy luôn **đặt tên, thứ tự, ý nghĩa và kiểu cột trong một hợp đồng thống nhất**.

## 11. Tên cột kết quả và ORDER BY sau phép tập hợp

Tên cột cuối của phép tập hợp thường lấy từ **danh sách SELECT đầu tiên**. Vì vậy, khi chuẩn hóa nhiều nguồn, có thể cố ý đặt alias ở nhánh đầu để công bố schema:

```sql
SELECT
    order_id AS order_key,
    amount AS total_amount
FROM demo_web_orders

UNION ALL

SELECT
    order_id AS id_from_store,
    amount AS money
FROM demo_store_orders

ORDER BY order_key;
```

Ở PostgreSQL, kết quả có các tên cột `order_key` và `total_amount` (từ nhánh đầu). Không nên `ORDER BY id_from_store` như thể alias ở nhánh sau tự trở thành cột kết quả cuối.

### 11.1. ORDER BY toàn tập, không chỉ một nhánh

```sql
SELECT order_id, amount
FROM demo_web_orders

UNION ALL

SELECT order_id, amount
FROM demo_store_orders

ORDER BY amount DESC, order_id;
```

`ORDER BY` đặt sau toàn bộ phép tập hợp sẽ sắp **kết quả đã gộp**. Nếu một nhánh cần lấy “top 3” trước rồi mới hợp với nhánh khác, đó là một yêu cầu khác và thường phải dùng **truy vấn con hoặc ngoặc theo cú pháp phương ngữ**.

PostgreSQL cho phép cấu trúc nhóm nhánh ví dụ:

```sql
(
    SELECT order_id, amount
    FROM demo_web_orders
    ORDER BY amount DESC, order_id
    LIMIT 2
)
UNION ALL
(
    SELECT order_id, amount
    FROM demo_store_orders
    ORDER BY amount DESC, order_id
    LIMIT 2
)
ORDER BY amount DESC, order_id;
```

Ở đây mỗi nhánh được giới hạn 2 hàng **trước** khi ghép. `ORDER BY` ngoài cùng vẫn là điều kiện quyết định thứ tự kết quả tổng thể. Cú pháp ngoặc và cách đặt `LIMIT`/`FETCH` khác nhau theo DBMS; không sao chép nguyên từ PostgreSQL sang mọi hệ.

### 11.2. Nhiều phép set operation trong một câu

```sql
SELECT ... FROM source_a
UNION
SELECT ... FROM source_b
INTERSECT
SELECT ... FROM source_c;
```

Khi có ba nhánh trở lên, **mọi đầu vào của từng phép tập hợp** đều phải tương thích về số cột và kiểu ở vị trí tương ứng. Một nhánh có ba cột giữa chuỗi các phép hai cột vẫn làm câu SQL không hợp lệ.

Thứ tự ưu tiên của các phép toán tập hợp có thể khác nhau theo phương ngữ hoặc gây khó đọc; trong PostgreSQL, `INTERSECT` có mức ưu tiên cao hơn `UNION` và `EXCEPT`. Nếu nghiệp vụ cần một cách kết hợp cụ thể, **dùng ngoặc hoặc CTE** để làm rõ thay vì trông chờ người đọc nhớ ưu tiên.

## 12. Khác biệt giữa các hệ quản trị

Điều kiện **cùng số cột** và **ghép theo vị trí** là nền tảng rất rộng rãi. Điểm khác biệt quan trọng nằm ở **cơ chế ép kiểu**, **kiểu được phép dùng** và **toán tử được hỗ trợ**.

| Hệ quản trị | Toán tử tập hợp phổ biến | Đặc điểm kiểu dữ liệu cần lưu ý |
|---|---|---|
| **PostgreSQL** | `UNION`, `UNION ALL`, `INTERSECT`, `EXCEPT` và các biến thể `ALL` phù hợp | Yêu cầu tìm kiểu chung theo từng vị trí; kiểu `TEXT` và `INTEGER` được định rõ thường không tự ghép; kiểu `JSON` có hạn chế so sánh cho `UNION DISTINCT` |
| **MySQL** | `UNION`/`UNION ALL`; `INTERSECT` và `EXCEPT` ở MySQL 8.0.31 trở lên | Quy tắc suy luận và chuyển kiểu linh hoạt hơn trong một số tình huống; kiểu/độ dài kết quả có thể chịu ảnh hưởng từ cả hai nhánh |
| **MariaDB** | `UNION`, `INTERSECT`, `EXCEPT` ở các phiên bản hỗ trợ | Có quy tắc ép kiểu và thứ tự ưu tiên riêng; không đồng nhất hoàn toàn với MySQL hiện đại |
| **SQL Server** | `UNION`/`UNION ALL`, `INTERSECT`, `EXCEPT` | Dựa vào quy tắc độ ưu tiên kiểu và chuyển đổi ngầm; kiểu kết quả phải so sánh được khi loại trùng; các kiểu như `xml`, `text`/`ntext`/`image` có hạn chế trong set operators |
| **Oracle Database** | `UNION`/`UNION ALL`, `INTERSECT`, `MINUS`; các tên/cú pháp mới tùy phiên bản | Nhấn mạnh nhóm kiểu tương thích; không mặc nhiên tự chuyển giữa kiểu ký tự và số; có hạn chế với `CLOB`, `BLOB`, `LONG` và một số kiểu đặc thù |
| **SQLite** | `UNION`/`UNION ALL`, `INTERSECT`, `EXCEPT` | Có cơ chế *dynamic typing* và quy tắc so sánh/affinity khác nhiều DBMS; vẫn yêu cầu cùng số cột, nhưng giá trị ở từng vị trí có thể mang nhiều lớp lưu trữ khác nhau |

**Lưu ý:** Bảng chỉ nêu các đặc điểm thực hành; hỗ trợ `ALL` với `INTERSECT`/`EXCEPT` và chi tiết các kiểu mở rộng phụ thuộc phiên bản cụ thể. Không nên suy rằng cùng cú pháp chạy trên mọi DBMS hoặc rằng kiểu kết quả/độ chính xác được chọn giống nhau.

### 12.1. PostgreSQL: kiểu chung theo vị trí

PostgreSQL thực hiện phân giải kiểu cho các cột tương ứng trong `UNION`/`CASE` và những ngữ cảnh khác. Ví dụ:

```sql
-- Cùng họ số: có thể ghép.
SELECT 10::INTEGER AS value
UNION ALL
SELECT 12.50::NUMERIC AS value;

-- Khác họ kiểu đã định rõ: lỗi tương thích.
SELECT 10::INTEGER AS value
UNION ALL
SELECT '10'::TEXT AS value;
```

Với nhiều nhánh, PostgreSQL có thể phân giải kiểu theo từng cặp/trật tự cấu trúc biểu thức, nên một chuỗi toàn `NULL`/literal không xác định kiểu có thể cho kết quả khác kỳ vọng nếu không có kiểu đích rõ ràng. Dùng `CAST` tường minh là cách dễ bảo trì khi kết quả trở thành một API/view ổn định.

### 12.2. SQL Server: type precedence không có nghĩa dữ liệu an toàn

Trong T-SQL, nếu hai nhánh trả các kiểu khác nhau, DBMS có thể áp dụng **độ ưu tiên kiểu dữ liệu** và quy tắc chuyển đổi ngầm để quyết định kiểu cuối.

Ví dụ ý tưởng:

```sql
-- SQL Server: chỉ minh họa khả năng chuyển kiểu.
SELECT CAST(10 AS INT) AS value
UNION ALL
SELECT CAST('20' AS VARCHAR(20)) AS value;
```

DBMS có thể chọn kiểu số và chuyển chuỗi số hợp lệ. Nhưng nếu nhánh hai chứa `'ABC'`, một phép chuyển sang kiểu số sẽ thất bại. Như vậy, **cú pháp được chấp nhận không bảo đảm mọi dữ liệu thực tế đều chuyển được**.

Khi đầu vào là chuỗi chưa tin cậy, có thể sử dụng `TRY_CAST`/`TRY_CONVERT` của SQL Server theo đúng hợp đồng xử lý bản ghi lỗi; với hệ khác, chọn cơ chế chuyển đổi an toàn tương ứng. Không xem việc ép sai thành `NULL` là tự nhiên đúng nghiệp vụ nếu phải theo dõi dữ liệu lỗi.

### 12.3. Oracle: không ngầm ghép mọi nhóm kiểu

Oracle nổi bật ở việc kiểm soát các **nhóm kiểu** trong set operators. Ví dụ, không nên cho rằng một cột `NUMBER` và một cột `VARCHAR2` sẽ tự ghép thành kiểu chuỗi giống một số DBMS khác.

Nếu mong xuất văn bản, dùng các hàm chuyển đổi phù hợp như `TO_CHAR` theo quy tắc định dạng; nếu muốn số, chuyển chuỗi hợp lệ sang số theo chính sách `TO_NUMBER`/cơ chế chuyển an toàn của phiên bản. `DATE` của Oracle còn chứa thành phần giờ, nên xử lý chung với `DATE` của PostgreSQL không phải lúc nào cũng cùng ngữ nghĩa.

Oracle có tên `MINUS` truyền thống cho phép lấy hiệu; một số phiên bản mới hỗ trợ thêm từ khóa tương ứng chuẩn SQL. Khi viết SQL dùng nhiều hệ, nên chọn cú pháp theo hệ đích và tránh giả định về các biến thể `ALL`.

### 12.4. MySQL/MariaDB: kết quả có thể được mở rộng kiểu

MySQL có thể xác định kiểu/độ dài cột kết quả dựa trên cả hai nhánh của `UNION`. Điều đó hữu ích khi một nhánh có chuỗi ngắn còn nhánh khác có chuỗi dài, nhưng cũng khiến biểu thức trông hợp lệ trong khi ứng dụng nhận kiểu ngoài mong đợi.

Với các nguồn số tiền, ngày giờ và mã định danh, nên định nghĩa kiểu chuẩn rõ ràng thay vì đặt niềm tin vào chuyển đổi ngầm. MySQL 8.0.31 trở lên hỗ trợ thêm `INTERSECT` và `EXCEPT`; trên phiên bản cũ, hai phép này không có cú pháp tương đương trực tiếp, có thể phải diễn đạt bằng `JOIN`/`EXISTS`/`NOT EXISTS` theo đúng logic và `NULL`.

MariaDB có lịch sử hỗ trợ và thứ tự ưu tiên phép toán riêng; không dùng phiên bản MySQL làm tiêu chuẩn cho mọi tính năng MariaDB.

### 12.5. SQLite: cùng số cột không đồng nghĩa một kiểu thống nhất mạnh

SQLite sử dụng *dynamic typing*: một cột/kết quả có thể mang các giá trị với lớp lưu trữ khác nhau. Một phép `UNION ALL` giữa số và văn bản có thể chạy mà không yêu cầu chuyển hết thành một kiểu mạnh cố định theo cách PostgreSQL làm.

```sql
-- SQLite minh họa: một cột nhưng có thể có nhiều storage class.
SELECT 10 AS value
UNION ALL
SELECT 'ABC' AS value;
```

Kết quả có thể chứa một số nguyên và một chuỗi văn bản trong cùng cột kết quả. Nhưng điều đó **không làm chúng trở thành cùng một loại dữ liệu về nghiệp vụ**. Khi xuất API hoặc tính toán tiếp, cần quy ước và chuyển đổi rõ ràng.

Với `UNION DISTINCT`, `INTERSECT` và `EXCEPT`, cách so sánh các giá trị trong SQLite chịu ảnh hưởng của kiểu lưu trữ và collation; không giả định số `10` và chuỗi `'10'` luôn là cùng một giá trị.

## 13. Tương thích kiểu dữ liệu và collation

Đối với kiểu ký tự, “cùng là VARCHAR/TEXT” chưa nói hết khả năng so sánh. **Collation** có thể quyết định chuỗi có phân biệt chữ hoa/chữ thường, dấu tiếng Việt và các quy tắc thứ tự hay không.

Ví dụ, tùy collation và DBMS:

```text
'An'
'an'
'Án'
```

có thể được so sánh bằng hoặc khác nhau theo các quy tắc cụ thể. Điều đó ảnh hưởng tới:

- `UNION`: dòng nào được xem là trùng khi loại bản sao?
- `INTERSECT`: dòng bên trái nào khớp với bên phải?
- `EXCEPT`: dòng nào bị loại vì xuất hiện ở bên phải?
- `ORDER BY`: thứ tự hiển thị cuối cùng.

Trên SQL Server, các chuỗi/cột có collation xung đột có thể cần chỉ định `COLLATE` phù hợp trong câu truy vấn. PostgreSQL và các hệ khác có quy tắc gắn/chọn collation riêng. Không chỉ ép kiểu ký tự mà quên chọn quy tắc so sánh khi dữ liệu phải nhất quán giữa các môi trường.

### 13.1. Chuỗi rỗng không phải lúc nào cũng giống nhau giữa DBMS

Trong PostgreSQL, `''` là chuỗi rỗng, khác SQL `NULL`. Oracle truyền thống thường xem chuỗi ký tự độ dài zero như `NULL` trong các trường hợp kiểu chuỗi. Khi `UNION` dữ liệu ký tự từ nhiều môi trường, cần quyết định “không nhập tên” sẽ được biểu diễn bằng **chuỗi rỗng** hay **`NULL`** theo chuẩn dữ liệu, tránh trường hợp cùng ngữ nghĩa nhưng bị coi là hai kết quả khác nhau.

## 14. Kết hợp các nguồn có schema khác nhau một cách an toàn

Một tình huống thực tế: nguồn A lưu mã giao dịch là số nguyên, nguồn B lưu mã chuỗi có tiền tố, trong khi báo cáo chung muốn có cột `transaction_code` kiểu văn bản.

Định nghĩa hợp đồng đầu ra trước:

| Vị trí | Cột kết quả | Kiểu mục tiêu | Ý nghĩa |
|---:|---|---|---|
| 1 | transaction_code | VARCHAR/TEXT phù hợp | Mã hiển thị, có thể chứa chữ |
| 2 | amount | DECIMAL(14,2) | Số tiền cùng đơn vị |
| 3 | occurred_on | DATE | Ngày lịch theo quy tắc xác định |
| 4 | source | VARCHAR/TEXT | Mã hệ thống nguồn |

Ví dụ PostgreSQL với các giá trị minh họa:

```sql
SELECT
    CAST(101 AS TEXT) AS transaction_code,
    CAST(150.00 AS NUMERIC(14,2)) AS amount,
    DATE '2026-11-01' AS occurred_on,
    CAST('WEB' AS TEXT) AS source

UNION ALL

SELECT
    CAST('POS-201' AS TEXT) AS transaction_code,
    CAST(450.00 AS NUMERIC(14,2)) AS amount,
    DATE '2026-11-04' AS occurred_on,
    CAST('STORE' AS TEXT) AS source;
```

Mọi vị trí được khai báo rõ và có **nghĩa giống nhau**. Số `101` được chuyển thành chữ vì mã của hệ thống chung có thể chứa cả chữ; nó không còn phù hợp cho phép cộng số học hoặc sắp theo thứ tự số nếu không có bước chuyển đổi riêng.

Một cách xây truy vấn nhiều nguồn dễ bảo trì hơn là sử dụng **CTE chuẩn hóa**:

```sql
WITH web_normalized AS (
    SELECT
        CAST(order_id AS TEXT) AS transaction_code,
        CAST(amount AS NUMERIC(14,2)) AS amount,
        CAST(placed_on AS DATE) AS occurred_on,
        CAST('WEB' AS TEXT) AS source
    FROM demo_web_orders
),
store_normalized AS (
    SELECT
        CAST(order_id AS TEXT) AS transaction_code,
        CAST(amount AS NUMERIC(14,2)) AS amount,
        CAST(placed_on AS DATE) AS occurred_on,
        CAST('STORE' AS TEXT) AS source
    FROM demo_store_orders
)
SELECT transaction_code, amount, occurred_on, source
FROM web_normalized
UNION ALL
SELECT transaction_code, amount, occurred_on, source
FROM store_normalized
ORDER BY occurred_on, transaction_code, source;
```

Mỗi CTE có cùng **bốn vị trí** và cùng kiểu/ý nghĩa. Như vậy, khi nguồn thay đổi cột, người bảo trì có thể điều chỉnh từng lớp chuẩn hóa mà không sửa toàn bộ logic báo cáo.

### 14.1. Quy trình đọc lỗi cột và kiểu

Khi gặp lỗi `UNION`/`INTERSECT`/`EXCEPT`, có thể xử lý theo thứ tự:

1. **Đếm số biểu thức trong mỗi `SELECT`** (không chỉ đếm tên cột vật lý).
2. **Ghi bảng vị trí:** cột 1 ở từng nhánh là gì, cột 2 là gì...
3. **Xác định kiểu thực tế** của từng biểu thức, bao gồm `CASE`, hàm tổng hợp, literal và giá trị `NULL`.
4. **Kiểm tra ý nghĩa nghiệp vụ:** hai biểu thức tương ứng có thật sự diễn đạt cùng loại dữ liệu không?
5. **Chọn kiểu đích** và `CAST` tường minh, kiểm tra các chuyển đổi có thể mất dữ liệu hoặc lỗi.
6. **Xem yêu cầu khử trùng:** nếu dùng `UNION`/`INTERSECT`/`EXCEPT`, kiểu có hỗ trợ so sánh không?
7. **Kiểm soát thứ tự kết quả** bằng `ORDER BY` cuối nếu cần.
8. **Kiểm tra ràng buộc ứng dụng** về kiểu dữ liệu, số cột và tên cột mà client dựa vào.

Đây là chuỗi câu hỏi thiết kế, không phải chỉ sửa cho câu SQL “hết báo lỗi”. Lỗi hình dạng có thể được phát hiện sớm, còn lỗi ghép sai hai cột cùng kiểu có thể xuất hiện âm thầm trong dữ liệu báo cáo.

## 15. Khi nào nên dùng UNION ALL thay cho UNION?

Mặc dù bài học nhấn mạnh điều kiện tương thích, lựa chọn `UNION` hay `UNION ALL` cũng ảnh hưởng cách DBMS xử lý các kiểu dữ liệu.

| Tiêu chí | `UNION ALL` | `UNION` |
|---|---|---|
| Giữ hàng trùng | Có | Không |
| Cần xác định trùng giữa các hàng | Không | Có |
| Có thể dùng với kiểu thiếu phép so sánh bằng | Có thể, nếu có kiểu đầu ra phù hợp | Có thể bị hạn chế |
| Chi phí xử lý | Thường ít hơn vì không khử trùng | Có thể phải sort/hash/khử trùng |
| Dùng khi | Gộp bản ghi/sự kiện từ nhiều nguồn, cần giữ từng dòng | Cần tập các hàng khác nhau theo toàn bộ cột chọn |

Không kết luận `UNION ALL` luôn nhanh hơn trong mọi môi trường mà không đo, nhưng về nguyên tắc nó **không thực hiện bước loại dòng trùng**. Nếu đang gộp sự kiện, nhật ký hoặc dòng giao dịch, giữ bản sao có thể là yêu cầu đúng; nếu cần tập mã khách khác nhau, `UNION` hoặc `SELECT DISTINCT` trên hợp kết quả có thể phù hợp.

`UNION` không giải quyết việc bản ghi **khác ID nhưng cùng thực thể** hoặc **cùng ID nhưng khác chi tiết**. Bài toán hợp nhất thực thể đòi hỏi một khóa/luật matching riêng.

## 16. Hiệu năng và thứ tự thực thi

Phép tập hợp xử lý toàn bộ số hàng do các nhánh tạo ra, trừ khi có giới hạn hoặc điều kiện phù hợp. Việc chọn kiểu đầu ra cũng ảnh hưởng chi phí:

- Ép từ `INTEGER` sang `TEXT` khiến việc so sánh/sắp mã có thể trở thành so sánh chuỗi.
- Chuyển kiểu ngày giờ qua chuỗi có thể làm mất khả năng so sánh thời gian tự nhiên và tối ưu chỉ mục theo cột gốc.
- `UNION`, `INTERSECT`, `EXCEPT` phải xác định các dòng trùng theo ngữ nghĩa DBMS, có thể dùng sort/hash và bộ nhớ đáng kể.
- `UNION ALL` thường có thể nối kết quả mà không cần loại trùng.
- Biểu thức `CAST` trên cột có thể ảnh hưởng khả năng dùng chỉ mục hiện có; tùy DBMS và kế hoạch, có thể cần chuẩn hóa schema trước hoặc dùng chỉ mục biểu thức.
- Khi nhánh có bộ lọc `WHERE`, việc lọc sớm đúng ngữ nghĩa có thể giảm số hàng đầu vào, nhưng không nên tự thay đổi logic chỉ để “nhanh hơn”.

Ví dụ PostgreSQL:

```sql
EXPLAIN
SELECT order_id, customer_name, amount
FROM demo_web_orders

UNION

SELECT order_id, customer_name, amount
FROM demo_store_orders;
```

`EXPLAIN` cho thấy kế hoạch dự kiến. Có thể so với dạng `UNION ALL` để hiểu bước khử trùng, nhưng dữ liệu mẫu chỉ vài hàng nên chưa đại diện cho hiệu năng trên bảng lớn. Việc tối ưu sâu cần thuộc một quá trình đo đạc có dữ liệu và chỉ mục tương ứng.

### 16.1. Dùng phép tập hợp để thay JOIN là sai bài toán

Ví dụ muốn **lấy thông tin khách hàng tương ứng với đơn hàng**, `JOIN` giúp nối cột theo khóa. `UNION` sẽ xếp hàng khách và hàng đơn thành các bản ghi chung một schema, chỉ hợp lý khi chúng thực sự cùng một loại kết quả đã chuẩn hóa.

Câu hỏi định hướng:

- “Gộp **danh sách bản ghi cùng ý nghĩa** từ hai nguồn?” → xem xét `UNION ALL`/`UNION`.
- “Ghép **thuộc tính khác nhau** của những bản ghi liên quan?” → xem xét `JOIN`.
- “Lấy bản ghi xuất hiện trong cả hai tập?” → `INTERSECT` hoặc `EXISTS`/`JOIN` theo yêu cầu.
- “Lấy bản ghi chỉ có ở nguồn A?” → `EXCEPT` hoặc `NOT EXISTS` với quy tắc `NULL` phù hợp.

## 17. Các lỗi thường gặp

| Sai lầm | Điều xảy ra | Hướng xử lý |
|---|---|---|
| Nhánh A có 3 cột, nhánh B có 2 cột | Lỗi số cột | Chọn cùng số biểu thức ở mỗi nhánh |
| Dùng alias giống nhau nhưng thứ tự khác nhau | Ghép sai vị trí hoặc lỗi kiểu | Đặt đúng thứ tự cột theo hợp đồng |
| Đổi chỗ hai cột cùng kiểu `TEXT` | Truy vấn chạy nhưng dữ liệu sai nghĩa | Soát ý nghĩa từng vị trí, không chỉ kiểu |
| Dùng `SELECT *` từ hai bảng phát triển độc lập | Schema drift làm hỏng query | Liệt kê cột tường minh |
| Kỳ vọng SQL tự đổi `TEXT` thành `INTEGER` an toàn | Lỗi ép kiểu hoặc dữ liệu sai | Xác thực dữ liệu và `CAST` theo kiểu đích |
| Trộn `DATE` với chuỗi ngày không chuẩn | Khác cách parse hoặc lỗi kiểu | Chọn kiểu `DATE` chuẩn và chuyển đổi rõ |
| Nghĩ tên cột nhánh sau là tên kết quả cuối | Sai alias trong `ORDER BY`/client | Đặt alias ở nhánh đầu, nêu schema kết quả |
| Dùng `UNION` khi muốn giữ mọi sự kiện | Mất dòng trùng hợp lệ | Dùng `UNION ALL` nếu cần giữ bản sao |
| Dùng `UNION ALL` khi muốn khử trùng | Dữ liệu lặp trong báo cáo | Xác định khóa và tiêu chí loại trùng |
| Dùng `UNION DISTINCT` với kiểu không so sánh được | Lỗi dù số cột/kiểu đầu vào phù hợp | Chọn biểu diễn so sánh được hoặc đổi thiết kế |
| Nghĩ `NULL = NULL` là `TRUE` vì `UNION` loại trùng | Hiểu sai logic ba giá trị | Tách quy tắc so sánh bình thường và quy tắc dòng trùng |
| Đặt `ORDER BY` ở nhánh đầu rồi mong sắp toàn tập | Kết quả cuối không theo thứ tự mong muốn | `ORDER BY` sau toàn bộ phép tập hợp |
| Nghĩ `UNION` ghép theo tên cột | Không nhận ra lỗi vị trí | Ghi schema thứ tự 1, 2, 3... |
| Cho rằng mọi DBMS chọn cùng kiểu kết quả | API/driver nhận kiểu khác, lỗi chuyển | `CAST` và kiểm tra phương ngữ |
| Gộp hai nguồn có ID trùng nhưng không lưu tên nguồn | Nhầm các bản ghi khác thực thể | Thêm khóa nguồn khi cần và định nghĩa quy tắc hợp nhất |

## 18. Bài tập thực hành kèm hướng dẫn

### Bài 1. Số cột khác nhau

Đoạn SQL sau vì sao sai?

```sql
SELECT order_id, customer_name
FROM demo_web_orders

UNION ALL

SELECT order_id, customer_name, amount
FROM demo_store_orders;
```

**Đáp án:** nhánh đầu có **2 cột**, nhánh sau **3 cột**. Sửa bằng cách chọn cùng ba cột ở cả hai nhánh hoặc cùng hai cột nếu số tiền không cần thiết. Không thể dùng tên alias để thay cho cột thiếu.

### Bài 2. Cột thứ hai bị đảo

```sql
SELECT customer_name, status FROM demo_web_orders
UNION ALL
SELECT status, customer_name FROM demo_store_orders;
```

**Câu hỏi:** truy vấn có bắt buộc báo lỗi không?

**Đáp án:** không. Hai vị trí đều là `TEXT` ở cả hai nhánh nên phép gộp **tương thích kiểu** nhưng **sai ý nghĩa**. Cột thứ nhất của nhánh Store chứa trạng thái thay vì tên; cần đặt `SELECT customer_name, status` ở cả hai nhánh.

### Bài 3. Gộp số nguyên và mã chuỗi

**Yêu cầu:** tạo một cột `code` kiểu văn bản từ số `101` và chuỗi `'POS-202'`, dùng PostgreSQL.

**Đáp án:**

```sql
SELECT CAST(101 AS TEXT) AS code
UNION ALL
SELECT CAST('POS-202' AS TEXT) AS code;
```

Cả hai nhánh có một cột `TEXT`. Sau chuyển đổi, `code` là mã dạng chuỗi, không nên coi nó là số để tính toán.

### Bài 4. Phân biệt UNION và UNION ALL

**Câu hỏi:** với năm cột trong dữ liệu mẫu, `UNION ALL` trả mấy hàng và `UNION` trả mấy hàng?

**Đáp án:** `UNION ALL` trả **6** hàng; `UNION` trả **5** vì một dòng ID 102 trùng **cả năm giá trị** ở hai nguồn.

### Bài 5. Nếu thêm cột nguồn thì sao?

**Yêu cầu:** ở cả hai nhánh, thêm cột `source_channel` có giá trị `'WEB'` hoặc `'STORE'`. Nếu dùng `UNION` thì còn mấy hàng?

**Đáp án:** **6** hàng, vì hai dòng ID 102 lúc này khác nhau ở `source_channel`. `UNION` chỉ loại hàng trùng trên **toàn bộ các cột** được chọn.

### Bài 6. Truy vấn con có NULL

Dự đoán số hàng:

```sql
SELECT NULL::INTEGER AS x
UNION
SELECT NULL::INTEGER AS x;
```

**Đáp án:** **1 hàng** với giá trị `NULL` vì phép khử trùng xem hai hàng `NULL` là không phân biệt cho mục đích tập hợp. Nếu thay `UNION` bằng `UNION ALL`, kết quả là **2 hàng `NULL`**.

### Bài 7. Có thể ghép kiểu JSON qua UNION không?

**Câu hỏi:** PostgreSQL có thể `UNION ALL` hai giá trị kiểu `JSON`, vậy `UNION` hai giá trị cùng kiểu có nhất thiết hợp lệ không?

**Đáp án:** không. `UNION` cần so sánh để loại trùng, còn `JSON` PostgreSQL thiếu cơ chế so sánh bằng phù hợp trong ngữ cảnh này. Có thể chọn `JSONB` nếu quy tắc chuẩn hóa/so sánh của `JSONB` đúng nghiệp vụ, hoặc dùng `UNION ALL` nếu không cần loại trùng.

### Bài 8. Sắp xếp kết quả cuối

**Yêu cầu:** gộp tên và số tiền của hai bảng bằng `UNION ALL`, sắp số tiền giảm dần; nếu bằng nhau thì sắp theo tên tăng dần.

**Đáp án:**

```sql
SELECT customer_name, amount
FROM demo_web_orders

UNION ALL

SELECT customer_name, amount
FROM demo_store_orders

ORDER BY amount DESC, customer_name ASC;
```

`ORDER BY` nằm sau phép tập hợp, áp dụng cho **toàn bộ các hàng đã gộp**.

### Bài 9. Trộn kiểu ngày và chuỗi

**Yêu cầu:** một nhánh trả `DATE '2026-11-01'`, nhánh khác trả chuỗi `'2026-11-02'`. Muốn kết quả là cột `DATE` có thể tiếp tục tính toán. Viết PostgreSQL.

**Đáp án:**

```sql
SELECT DATE '2026-11-01' AS event_day
UNION ALL
SELECT CAST('2026-11-02' AS DATE) AS event_day;
```

Cách này chỉ định rõ kiểu ngày; không dựa vào ép kiểu ngầm từ chuỗi đã định kiểu `TEXT`. Trong ứng dụng thực tế, cần bảo đảm định dạng và giá trị nhập là ngày hợp lệ.

### Bài 10. Thêm một cột còn thiếu

**Yêu cầu:** nguồn A có `order_id`, `amount`, `note`; nguồn B chỉ có `order_id`, `amount`. Muốn kết quả chung ba cột theo đúng thứ tự, cột `note` của nguồn B thể hiện “không có dữ liệu”.

**Đáp án:**

```sql
-- Ví dụ mẫu, giả sử bảng a và b tồn tại.
SELECT order_id,
       CAST(amount AS NUMERIC(14,2)) AS amount,
       CAST(note AS TEXT) AS note
FROM a

UNION ALL

SELECT order_id,
       CAST(amount AS NUMERIC(14,2)) AS amount,
       CAST(NULL AS TEXT) AS note
FROM b;
```

Ba vị trí lần lượt là mã, số tiền, ghi chú; các kiểu được chuẩn hóa. Không chèn `NULL` vào vị trí thứ hai vì đó là vị trí của số tiền.

## Kết luận

Phép toán tập hợp trong SQL yêu cầu các nhánh `SELECT` có **cùng số cột**, được ghép **theo thứ tự vị trí** và có **kiểu dữ liệu tương thích** ở từng vị trí. Tên alias không làm các cột tự ghép theo tên; một truy vấn có hai cột `TEXT` bị đảo vẫn có thể chạy và tạo dữ liệu sai.

Khi các kiểu khác nhau, hãy chọn một **schema đầu ra** với ý nghĩa, thứ tự và kiểu rõ ràng, rồi dùng `CAST` hoặc quy trình chuẩn hóa phù hợp. Khi dùng `UNION`, `INTERSECT` hoặc `EXCEPT`, còn phải xét **khả năng so sánh và loại trùng**, bao gồm cách xử lý `NULL` và kiểu đặc thù như JSON. `UNION ALL` giữ nguyên các dòng và thường phù hợp khi gộp sự kiện từ nhiều nguồn; `UNION` chỉ loại các hàng trùng **toàn bộ cột**.

Với dữ liệu đa hệ quản trị, điều quan trọng không phải viết một câu SQL “chạy được ở đâu đó”, mà là bảo đảm **mỗi vị trí kết quả luôn mang cùng ý nghĩa và kiểu dữ liệu đã thống nhất**. Đây là nền tảng để áp dụng các phép toán tập hợp một cách đúng đắn, an toàn và dễ bảo trì.

