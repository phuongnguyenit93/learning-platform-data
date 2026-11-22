# INTERSECT để tìm phần giao

## 1. Phép giao trả lời câu hỏi gì?

Trong toán học tập hợp, **giao của hai tập** là tập gồm những phần tử **có mặt ở cả hai tập**. Nếu:

~~~text
Tập A = {1, 2, 3, 4, 6}
Tập B = {1, 3, 5, 6}

A ∩ B = {1, 3, 6}
~~~

thì `1`, `3` và `6` là các phần tử chung. Trong SQL, toán tử **`INTERSECT`** cho phép lấy phần giao giữa **hai kết quả truy vấn**:

~~~sql
SELECT customer_id
FROM web_orders

INTERSECT

SELECT customer_id
FROM store_orders;
~~~

Ý nghĩa: lấy những mã khách hàng **đã mua trên website** và **cũng đã mua ở cửa hàng**.

Phần giao trong SQL không chỉ áp dụng cho một mã định danh. Có thể giao hai tập **cặp giá trị** như `(customer_id, product_id)` hoặc các hàng có nhiều cột. Khi đó, một hàng chỉ thuộc phần giao nếu **các giá trị tương ứng ở tất cả các cột** được coi là giống nhau theo ngữ nghĩa của phép toán tập hợp.

Điểm cần nhớ ngay từ đầu:

- `INTERSECT` kết hợp **kết quả của hai câu `SELECT`**, không tự nối từng hàng theo khóa như `JOIN`.
- Mặc định, `INTERSECT` dùng **ngữ nghĩa tập hợp**, nên hàng trùng trong kết quả giao chỉ xuất hiện **một lần**.
- Hai phía phải có **cùng số cột** và các kiểu dữ liệu ở **cùng vị trí** phải so sánh được theo quy tắc của DBMS.
- `INTERSECT` không tự bảo đảm **thứ tự các hàng**; muốn kết quả ổn định, đặt `ORDER BY` ở cuối biểu thức tập hợp.
- Nếu cần giữ số lần xuất hiện của mỗi hàng, một số DBMS hỗ trợ biến thể `INTERSECT ALL`; biến thể này không phải lúc nào cũng khả dụng.

Bài học thuộc nhóm **phép toán tập hợp** trong SQL và tập trung vào `INTERSECT`: cú pháp, kết quả, cách xử lý `NULL`, khác biệt với `JOIN`/`EXISTS`, khả chuyển và những lỗi thường gặp.

## 2. Dữ liệu ví dụ: khách mua qua website và cửa hàng

Để kết quả kiểm tra được bằng mắt, ta dùng hai bảng giao dịch:

- `web_orders`: giao dịch qua website.
- `store_orders`: giao dịch tại cửa hàng.

Mỗi giao dịch gắn với **một khách hàng** và **một sản phẩm** trong bộ dữ liệu minh họa. Đây là mô hình tối giản cho bài học về phép giao; hệ bán hàng thật thường có bảng đơn hàng và bảng dòng đơn hàng riêng để chứa nhiều sản phẩm trong một đơn.

### 2.1. Khởi tạo bảng

Các câu lệnh sau dùng cú pháp SQL phổ biến, phù hợp để thực hành trên PostgreSQL và các DBMS có hỗ trợ `INTERSECT`, sau khi điều chỉnh cú pháp DDL nếu cần.

~~~sql
CREATE TABLE customers (
    customer_id   INTEGER PRIMARY KEY,
    customer_name VARCHAR(80) NOT NULL
);

CREATE TABLE products (
    product_id   INTEGER PRIMARY KEY,
    product_name VARCHAR(80) NOT NULL
);

CREATE TABLE web_orders (
    web_order_id INTEGER PRIMARY KEY,
    customer_id  INTEGER NOT NULL,
    product_id   INTEGER NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (product_id)  REFERENCES products(product_id)
);

CREATE TABLE store_orders (
    store_order_id INTEGER PRIMARY KEY,
    customer_id    INTEGER NOT NULL,
    product_id     INTEGER NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (product_id)  REFERENCES products(product_id)
);
~~~

Trong hai bảng giao dịch, `customer_id` **không duy nhất**: một khách có thể mua nhiều lần. Tương tự, `product_id` có thể lặp khi nhiều giao dịch cùng mua một loại sản phẩm. Ràng buộc khóa ngoại đảm bảo mã khác `NULL` tham chiếu bản ghi cha tồn tại; trong ví dụ, hai cột mã giao dịch đều khai báo `NOT NULL`.

### 2.2. Thêm dữ liệu mẫu

~~~sql
INSERT INTO customers (customer_id, customer_name)
VALUES
    (1, 'An'),
    (2, 'Binh'),
    (3, 'Chi'),
    (4, 'Dung'),
    (5, 'Ha'),
    (6, 'Lan'),
    (7, 'Minh');

INSERT INTO products (product_id, product_name)
VALUES
    (10, 'So tay'),
    (20, 'But bi'),
    (30, 'Ban phim'),
    (40, 'Chuot');

INSERT INTO web_orders (web_order_id, customer_id, product_id)
VALUES
    (101, 1, 10),
    (102, 1, 20),
    (103, 2, 10),
    (104, 3, 20),
    (105, 4, 30),
    (106, 6, 10);

INSERT INTO store_orders (store_order_id, customer_id, product_id)
VALUES
    (201, 1, 10),
    (202, 1, 10),
    (203, 3, 30),
    (204, 5, 10),
    (205, 6, 10),
    (206, 6, 40);
~~~

Các giao dịch:

| Kênh | Mã giao dịch | Khách hàng | Sản phẩm |
| --- | ---: | --- | --- |
| Website | 101 | 1 — An | 10 — So tay |
| Website | 102 | 1 — An | 20 — But bi |
| Website | 103 | 2 — Binh | 10 — So tay |
| Website | 104 | 3 — Chi | 20 — But bi |
| Website | 105 | 4 — Dung | 30 — Ban phim |
| Website | 106 | 6 — Lan | 10 — So tay |
| Cửa hàng | 201 | 1 — An | 10 — So tay |
| Cửa hàng | 202 | 1 — An | 10 — So tay |
| Cửa hàng | 203 | 3 — Chi | 30 — Ban phim |
| Cửa hàng | 204 | 5 — Ha | 10 — So tay |
| Cửa hàng | 205 | 6 — Lan | 10 — So tay |
| Cửa hàng | 206 | 6 — Lan | 40 — Chuot |

Mã khách xuất hiện theo từng giao dịch:

~~~text
web_orders:   1, 1, 2, 3, 4, 6
store_orders: 1, 1, 3, 5, 6, 6

Khách khác nhau trên web:    {1, 2, 3, 4, 6}
Khách khác nhau ở cửa hàng: {1, 3, 5, 6}
Khách có mặt ở cả hai:     {1, 3, 6}
~~~

Dữ liệu có chủ đích chứa **mã trùng** ở từng kênh. Nhờ vậy ta có thể quan sát việc `INTERSECT` loại trùng như thế nào.

## 3. Cú pháp cơ bản của INTERSECT

Dạng phổ biến:

~~~sql
SELECT <cot_1>, <cot_2>, ...
FROM <nguon_A>
WHERE <dieu_kien_A>

INTERSECT

SELECT <cot_1_tuong_ung>, <cot_2_tuong_ung>, ...
FROM <nguon_B>
WHERE <dieu_kien_B>;
~~~

`INTERSECT` áp dụng trên **tập hàng đầu ra của hai toán hạng `SELECT`**. Hai truy vấn có thể đọc các bảng khác nhau, view khác nhau hoặc những điều kiện khác nhau trên cùng một bảng.

### 3.1. Tìm khách đã mua ở cả hai kênh

~~~sql
SELECT customer_id
FROM web_orders

INTERSECT

SELECT customer_id
FROM store_orders

ORDER BY customer_id;
~~~

Kết quả:

| customer_id |
| ---: |
| 1 |
| 3 |
| 6 |

Chỉ có ba hàng, dù khách An xuất hiện hai lần ở mỗi bảng giao dịch và Lan xuất hiện hai lần trong `store_orders`.

Hãy đọc câu SQL theo các bước **ngữ nghĩa**:

1. `SELECT customer_id FROM web_orders` tạo danh sách các mã từ giao dịch website.
2. `SELECT customer_id FROM store_orders` tạo danh sách các mã từ giao dịch cửa hàng.
3. `INTERSECT` giữ những **hàng có giá trị xuất hiện ở cả hai kết quả**, mặc định bỏ trùng.
4. `ORDER BY customer_id` sắp các hàng **của kết quả cuối** theo mã tăng dần.

Các bước trên là mô hình để hiểu kết quả, **không phải trình tự vật lý** mà hệ quản trị bắt buộc thực hiện. Bộ tối ưu có thể chọn hash, sort hoặc những phép biến đổi khác.

### 3.2. Đọc kết quả theo ý nghĩa nghiệp vụ

`customer_id = 1` có mặt ở hai kênh nên được giữ. `3` và `6` cũng vậy.

`customer_id = 2` và `4` chỉ có giao dịch web, nên không thuộc phần giao. `customer_id = 5` chỉ có giao dịch cửa hàng, nên cũng bị loại. Khách `7` chưa có giao dịch trong hai bảng, vì vậy không thuộc tập nào.

**`INTERSECT` không trả tên khách hàng ở ví dụ này** vì cả hai `SELECT` chỉ chọn `customer_id`. Muốn có tên, ta nối phần giao với bảng `customers` ở một bước riêng, xem mục 11.

## 4. INTERSECT mặc định loại hàng trùng

### 4.1. Hàng giống nhau chỉ xuất hiện một lần

Theo ngữ nghĩa thông dụng và SQL tiêu chuẩn, `INTERSECT` mặc định là **`INTERSECT DISTINCT`**: mỗi hàng phân biệt trong phần giao chỉ xuất hiện một lần.

Với dữ liệu mẫu:

~~~text
Website:  [1, 1, 2, 3, 4, 6]
Cửa hàng:[1, 1, 3, 5, 6, 6]

INTERSECT: [1, 3, 6]
~~~

Trong đó:

- Mã `1` xuất hiện hai lần ở web và hai lần ở cửa hàng, nhưng đầu ra chỉ có **một hàng `1`**.
- Mã `3` xuất hiện một lần mỗi phía, đầu ra có một hàng `3`.
- Mã `6` xuất hiện một lần ở web và hai lần ở cửa hàng, đầu ra có một hàng `6`.

Do đó câu sau thường **không cần thiết** chỉ để bảo đảm kết quả `INTERSECT` không trùng:

~~~sql
SELECT DISTINCT customer_id
FROM web_orders

INTERSECT

SELECT DISTINCT customer_id
FROM store_orders;
~~~

Nó có cùng **tập kết quả phân biệt** như phiên bản không thêm `DISTINCT` ở hai phía. Việc thêm `DISTINCT` vào từng `SELECT` có thể khiến câu truy vấn dài hơn và tạo các bước tính toán không cần thiết; bộ tối ưu có thể xử lý khác tùy DBMS.

### 4.2. INTERSECT ALL giữ số lần xuất hiện theo quy tắc khác

Một số DBMS, trong đó có PostgreSQL, hỗ trợ:

~~~sql
SELECT customer_id
FROM web_orders

INTERSECT ALL

SELECT customer_id
FROM store_orders

ORDER BY customer_id;
~~~

`INTERSECT ALL` dùng ngữ nghĩa **đa tập (bag/multiset)**. Với một hàng giá trị `x` xuất hiện `a` lần ở kết quả trái và `b` lần ở kết quả phải, số lần `x` xuất hiện trong kết quả giao là:

\[
\min(a,b)
\]

Áp dụng:

| customer_id | Số lần ở web | Số lần ở cửa hàng | `INTERSECT` | `INTERSECT ALL` |
| ---: | ---: | ---: | ---: | ---: |
| 1 | 2 | 2 | 1 | 2 |
| 2 | 1 | 0 | 0 | 0 |
| 3 | 1 | 1 | 1 | 1 |
| 4 | 1 | 0 | 0 | 0 |
| 5 | 0 | 1 | 0 | 0 |
| 6 | 1 | 2 | 1 | 1 |

Vì vậy `INTERSECT ALL` trả **4 hàng**, theo thứ tự sắp xếp là `1, 1, 3, 6`. Còn `INTERSECT` mặc định trả **3 hàng** là `1, 3, 6`.

Đây chỉ là **số lần xuất hiện cùng một giá trị trong hai kết quả**, không phải phép ghép giao dịch tương ứng. Hai đơn hàng website của An không tự động được “ghép đúng đơn” với hai biên lai cửa hàng của An.

**Lưu ý tính khả chuyển:** `INTERSECT ALL` không được mọi DBMS hoặc mọi phiên bản hỗ trợ. Nếu yêu cầu chỉ là tìm **tập khách hàng chung**, `INTERSECT` mặc định là lựa chọn đơn giản và phù hợp hơn.

## 5. Phần giao nhiều cột: so khớp toàn bộ hàng

### 5.1. Giao theo cặp khách hàng–sản phẩm

Một câu hỏi khác với mục 3:

> Những cặp **khách hàng và loại sản phẩm** nào xuất hiện trong giao dịch của cả hai kênh?

Ta cần so sánh **hai cột cùng lúc**:

~~~sql
SELECT customer_id, product_id
FROM web_orders

INTERSECT

SELECT customer_id, product_id
FROM store_orders

ORDER BY customer_id, product_id;
~~~

Kết quả:

| customer_id | product_id | Ý nghĩa |
| ---: | ---: | --- |
| 1 | 10 | An mua So tay ở cả hai kênh |
| 6 | 10 | Lan mua So tay ở cả hai kênh |

**Tại sao không có khách Chi (ID 3)?**

Chi có giao dịch web cho sản phẩm `20` và giao dịch cửa hàng cho sản phẩm `30`. Chi **có mặt ở cả hai kênh**, nhưng **cặp `(3, product_id)` không trùng** giữa hai bên:

~~~text
Web:     (3, 20)
Cửa hàng:(3, 30)

Hai hàng này khác nhau; không nằm trong phần giao của cặp giá trị.
~~~

Hai câu hỏi nghiệp vụ dẫn đến hai kết quả khác nhau:

| Câu hỏi | Cột tạo tập | Kết quả |
| --- | --- | --- |
| Khách nào mua ở cả hai kênh? | `customer_id` | 1, 3, 6 |
| Khách nào mua **cùng loại sản phẩm** ở cả hai kênh? | `customer_id, product_id` | (1,10), (6,10) |

Việc chọn **các cột tham gia phép giao** là một phần của định nghĩa bài toán, không chỉ là quyết định hiển thị.

### 5.2. Không khớp theo tên cột, mà khớp theo vị trí

Các phép toán tập hợp so các giá trị theo **thứ tự cột được liệt kê**. Ví dụ sau có hai cột số ở cả hai phía nhưng **không đúng ý nghĩa**:

~~~sql
-- Sai logic: thứ tự cột của truy vấn bên phải bị đảo.
SELECT customer_id, product_id
FROM web_orders

INTERSECT

SELECT product_id, customer_id
FROM store_orders;
~~~

DBMS có thể vẫn chấp nhận vì cả hai cột đều có kiểu số tương thích. Nhưng cột vị trí 1 ở web (mã khách) đang bị so với cột vị trí 1 ở cửa hàng (mã sản phẩm), và ngược lại. Đây là một **lỗi ngữ nghĩa** dù câu SQL không nhất thiết báo lỗi cú pháp.

Cần đảm bảo:

~~~text
Cột 1 bên trái  ↔ Cột 1 bên phải  (cùng ý nghĩa)
Cột 2 bên trái  ↔ Cột 2 bên phải  (cùng ý nghĩa)
...
~~~

### 5.3. Một hàng được coi là chung khi tất cả cột tương ứng khớp

Nếu chọn ba cột:

~~~sql
SELECT customer_id, product_id, web_order_id
FROM web_orders

INTERSECT

SELECT customer_id, product_id, store_order_id
FROM store_orders;
~~~

câu SQL đang so khớp **ba thành phần**, gồm cả **mã giao dịch** ở vị trí cuối. Các mã `web_order_id` và `store_order_id` thuộc hai hệ mã khác nhau, không có lý do để được coi là cùng thực thể chỉ vì đều là số. Truy vấn có thể trả **tập rỗng** với dữ liệu mẫu.

Muốn tìm giao theo khách và sản phẩm, **không thêm mã giao dịch** vào danh sách `SELECT` tham gia `INTERSECT`. Nếu cần hiển thị thông tin giao dịch sau khi tìm giao, phải xác định quy tắc chọn/ghép giao dịch riêng.

## 6. Quy tắc tương thích cấu trúc giữa hai SELECT

Đối với một phép `INTERSECT` thông thường, hai phía phải đáp ứng những yêu cầu cơ bản:

| Yêu cầu | Ví dụ đúng | Ví dụ dễ sai |
| --- | --- | --- |
| **Cùng số cột** | Một cột ở cả hai phía | Một phía chọn một cột, phía kia chọn hai cột |
| **Kiểu tương thích theo vị trí** | Hai mã khách đều là `INTEGER` | Một phía là số, phía kia là văn bản không có cách so sánh phù hợp |
| **Thứ tự cột đúng ý nghĩa** | Cùng `customer_id, product_id` | Một phía `customer_id, product_id`, phía kia đảo thứ tự |
| **Cùng đơn vị/ngữ nghĩa** | Mã khách với mã khách | Mã khách với mã phòng ban dù cùng kiểu số |
| **Kết quả ở đúng cấp hạt** | Danh sách mã khách phân biệt | Một phía là giao dịch chi tiết, phía kia là báo cáo tổng theo tháng |

Ví dụ lỗi số lượng cột:

~~~sql
-- Truy vấn một cột INTERSECT truy vấn hai cột: không hợp lệ.
SELECT customer_id
FROM web_orders

INTERSECT

SELECT customer_id, product_id
FROM store_orders;
~~~

Sửa bằng cách chọn một cột ở cả hai phía:

~~~sql
SELECT customer_id
FROM web_orders

INTERSECT

SELECT customer_id
FROM store_orders;
~~~

DBMS xác định kiểu kết quả dựa trên **quy tắc tương thích/ép kiểu của toán tử tập hợp**. Các quy tắc này có thể khác giữa PostgreSQL, SQL Server, Oracle, SQLite và MySQL/MariaDB. Nếu một phía dùng `INTEGER`, phía kia dùng `VARCHAR` chứa chữ số, không nên phụ thuộc vào ép kiểu ngầm.

Khi thật sự cần chuẩn hóa, hãy chuyển kiểu tường minh **có kiểm soát**:

~~~sql
-- Ví dụ về cấu trúc nếu hai nguồn đang lưu mã dưới các kiểu khác nhau:
SELECT CAST(customer_id AS BIGINT) AS customer_id
FROM web_orders

INTERSECT

SELECT CAST(customer_id AS BIGINT) AS customer_id
FROM store_orders;
~~~

Trong dữ liệu mẫu, hai cột vốn đã là `INTEGER` nên không cần làm vậy. Ở dữ liệu thật, phải xử lý giá trị không chuyển kiểu được và mất độ chính xác trước khi viết phép ép kiểu.

### Tên cột kết quả lấy từ đâu?

Thông thường, **tên/nhãn cột của kết quả tập hợp** được xác định theo danh sách `SELECT` đầu tiên, với khác biệt chi tiết tùy DBMS.

~~~sql
SELECT customer_id AS shared_customer_id
FROM web_orders

INTERSECT

SELECT customer_id AS store_customer_id
FROM store_orders

ORDER BY shared_customer_id;
~~~

Nhãn kết quả dự kiến là `shared_customer_id`, không phải hai cột `shared_customer_id` và `store_customer_id`. Phép giao trả **một cột duy nhất** cho mỗi vị trí tương ứng.

Không dùng bí danh bên phải để kỳ vọng thay đổi thứ tự/ý nghĩa cột đầu ra. Trong ứng dụng, nên đặt alias ổn định ở phía đầu hoặc bọc truy vấn tập hợp trong CTE rồi chọn tên cột mong muốn bên ngoài.

## 7. NULL trong INTERSECT: khác với dấu bằng thông thường

Đây là điểm rất dễ nhầm khi người học đã biết:

~~~sql
SELECT NULL = NULL;
-- Kết quả logic UNKNOWN/NULL ở nhiều DBMS, không phải TRUE.
~~~

Trong phép so sánh thông thường, `NULL` biểu thị giá trị thiếu hoặc chưa biết; `NULL = NULL` **không trả `TRUE`**.

Tuy nhiên, khi các phép toán tập hợp như `INTERSECT` xác định hàng trùng và hàng chung, `NULL` ở các vị trí tương ứng được xử lý theo **quy tắc tương đương phục vụ tập hợp**: hai ô `NULL` được coi là **không phân biệt** để xác định hàng có mặt ở cả hai kết quả.

Ví dụ trên PostgreSQL và các DBMS có `INTERSECT`:

~~~sql
SELECT CAST(NULL AS INTEGER) AS code

INTERSECT

SELECT CAST(NULL AS INTEGER) AS code;
~~~

Kết quả là **một hàng** với `code = NULL`.

Ngược lại:

~~~sql
SELECT CAST(NULL AS INTEGER) AS code
WHERE CAST(NULL AS INTEGER) IN (
    SELECT CAST(NULL AS INTEGER)
);
~~~

trong các DBMS hỗ trợ cú pháp `SELECT` không cần `FROM` như PostgreSQL sẽ **không trả hàng**, vì `NULL IN {NULL}` cho `UNKNOWN`, và `WHERE` chỉ giữ hàng có điều kiện `TRUE`.

**Kết luận:** `INTERSECT` và `IN` đều liên quan đến tư cách thành viên, nhưng **không có cùng ngữ nghĩa về `NULL`** trong mọi trường hợp.

### 7.1. Giao nhiều cột có NULL

Nếu cả hai phía trả hàng `(NULL, 10)`, hàng đó có thể xuất hiện một lần trong `INTERSECT` mặc định. Nhưng `(NULL, 10)` và `(NULL, 20)` là **hai hàng khác nhau** vì cột thứ hai khác.

~~~sql
SELECT
    CAST(NULL AS INTEGER) AS customer_id,
    10 AS product_id

INTERSECT

SELECT
    CAST(NULL AS INTEGER) AS customer_id,
    10 AS product_id;
-- Một hàng: (NULL, 10)
~~~

Trong hệ thống thực, việc coi hai giá trị chưa biết là “giống nhau” theo ngữ nghĩa tập hợp **không chứng minh** chúng đại diện cho cùng một khách thật. Nếu cần nối khách hàng theo định danh, tốt nhất dùng khóa không `NULL` và được ràng buộc rõ ràng.

### 7.2. INTERSECT ALL với NULL

Ở những DBMS hỗ trợ `INTERSECT ALL`, các hàng `NULL` được tính số lần xuất hiện theo quy tắc **lấy số lần nhỏ hơn giữa hai phía**, tương tự hàng không `NULL`. Như vậy, nếu một phía có hai hàng `NULL` và phía kia có ba hàng `NULL` thì kết quả `INTERSECT ALL` có **hai hàng `NULL`**.

Điều này khác với việc dùng `JOIN ... ON a.code = b.code`: phép `=` thông thường không nối hai mã `NULL` với nhau. Khi thay `INTERSECT` bằng `JOIN` hoặc `EXISTS` trên cột có thể `NULL`, cần quyết định có muốn bảo toàn quy tắc so khớp `NULL` của phép giao hay không.

## 8. WHERE trong từng phía của INTERSECT

Mỗi `SELECT` là một truy vấn độc lập, có thể có bộ lọc riêng.

Ví dụ:

> Tìm khách hàng đã mua **Sổ tay (mã 10)** ở cả website và cửa hàng.

~~~sql
SELECT customer_id
FROM web_orders
WHERE product_id = 10

INTERSECT

SELECT customer_id
FROM store_orders
WHERE product_id = 10

ORDER BY customer_id;
~~~

Phía web với sản phẩm 10 có mã khách `1, 2, 6`. Phía cửa hàng với sản phẩm 10 có mã `1, 1, 5, 6`. Phần giao phân biệt là:

| customer_id |
| ---: |
| 1 |
| 6 |

Đây không phải câu hỏi “khách mua qua web và từng mua sản phẩm 10 tại cửa hàng”. Điều kiện sản phẩm 10 ở **cả hai `SELECT`** yêu cầu mã khách xuất hiện trong **từng tập đã lọc theo sản phẩm 10**.

Nếu chỉ lọc sản phẩm ở một phía:

~~~sql
SELECT customer_id
FROM web_orders
WHERE product_id = 10

INTERSECT

SELECT customer_id
FROM store_orders

ORDER BY customer_id;
~~~

với dữ liệu mẫu cũng ra `1, 6`, nhưng **quy tắc nghiệp vụ khác**: khách phải mua sản phẩm 10 trên web và từng mua **bất kỳ sản phẩm** nào ở cửa hàng. Khi dữ liệu thay đổi, hai truy vấn có thể trả kết quả khác nhau.

### 8.1. Điều kiện của hai nguồn không nhất thiết giống nhau

Ví dụ tìm những khách **đã mua Bút bi trên web** và **đã mua Bàn phím tại cửa hàng**:

~~~sql
SELECT customer_id
FROM web_orders
WHERE product_id = 20

INTERSECT

SELECT customer_id
FROM store_orders
WHERE product_id = 30

ORDER BY customer_id;
~~~

Truy vấn web trả `1, 3`; cửa hàng với sản phẩm 30 trả `3`. Phần giao là **khách 3 — Chi**.

Điều này thể hiện khả năng của `INTERSECT`: hai nguồn có thể biểu diễn **hai điều kiện khác nhau**, và phần giao chính là những thực thể thỏa **cả hai điều kiện**.

### 8.2. Khi cần điều kiện trên bảng khác

Nếu chỉ muốn khách đang nằm trong một nhóm nghiệp vụ nào đó, có thể lọc bằng `JOIN` hoặc `WHERE` ở từng phía. Ví dụ tìm khách thuộc các ID `1` đến `5` đã mua cả hai kênh:

~~~sql
SELECT customer_id
FROM web_orders
WHERE customer_id BETWEEN 1 AND 5

INTERSECT

SELECT customer_id
FROM store_orders
WHERE customer_id BETWEEN 1 AND 5

ORDER BY customer_id;
-- 1, 3
~~~

Một cách khác là tìm phần giao đầy đủ, sau đó **lọc kết quả giao** ở câu truy vấn bên ngoài. Cách này có thể dễ đọc hơn khi một điều kiện áp dụng giống nhau cho kết quả cuối, xem mục 11.

## 9. Truy vấn con và CTE giúp dùng lại phần giao

Phép giao thường là một **tập trung gian**. Ta có thể đặt nó trong Common Table Expression (`WITH`), rồi truy vấn tiếp.

### 9.1. Lấy tên những khách mua ở cả hai kênh

~~~sql
WITH customers_in_both_channels AS (
    SELECT customer_id
    FROM web_orders

    INTERSECT

    SELECT customer_id
    FROM store_orders
)
SELECT
    c.customer_id,
    c.customer_name
FROM customers AS c
JOIN customers_in_both_channels AS both
    ON both.customer_id = c.customer_id
ORDER BY c.customer_id;
~~~

Kết quả:

| customer_id | customer_name |
| ---: | --- |
| 1 | An |
| 3 | Chi |
| 6 | Lan |

Ta không đưa `customer_name` vào hai truy vấn giao dịch vì hai bảng giao dịch **không cần lưu tên khách**. Chúng chỉ cần trả về **khóa chung** `customer_id`; sau khi xác định phần giao, nối với `customers` để lấy tên.

Nếu một bảng đơn hàng chứa tên khách lưu lặp và có thể thay đổi theo thời gian, đem tên vào phép giao cùng với ID có thể làm những khách thực sự trùng mã bị loại vì tên khác nhau. Hãy chọn **khóa nhận diện thực thể**, rồi bổ sung dữ liệu hiển thị ở lớp ngoài.

### 9.2. Dùng CTE để đặt tên cho từng tập

~~~sql
WITH
web_customers AS (
    SELECT customer_id
    FROM web_orders
    WHERE product_id = 10
),
store_customers AS (
    SELECT customer_id
    FROM store_orders
    WHERE product_id = 10
)
SELECT customer_id
FROM web_customers

INTERSECT

SELECT customer_id
FROM store_customers

ORDER BY customer_id;
-- 1, 6
~~~

Cách viết này có ý nghĩa khi mỗi tập cần nhiều điều kiện hoặc được tham chiếu nhiều lần. CTE giúp đặt tên **quy tắc chọn dữ liệu**, nhưng không tự đảm bảo DBMS phải vật chất hóa từng tập theo thứ tự đó; bộ tối ưu có thể inline hoặc thực thi bằng kế hoạch khác.

### 9.3. Lọc kết quả giao ở truy vấn ngoài

~~~sql
WITH common_customers AS (
    SELECT customer_id FROM web_orders
    INTERSECT
    SELECT customer_id FROM store_orders
)
SELECT customer_id
FROM common_customers
WHERE customer_id < 6
ORDER BY customer_id;
-- 1, 3
~~~

Điều kiện `customer_id < 6` áp dụng lên **kết quả phần giao**, không riêng phía web hay phía cửa hàng.

## 10. INTERSECT khác gì UNION và EXCEPT?

Ba phép toán tập hợp phục vụ ba câu hỏi khác nhau:

| Toán tử | Ý nghĩa tập hợp | Câu hỏi ví dụ | Kết quả mã khách với dữ liệu mẫu |
| --- | --- | --- | --- |
| `UNION` | Có trong **ít nhất một** bên | Ai từng mua ở web **hoặc** cửa hàng? | 1, 2, 3, 4, 5, 6 |
| `INTERSECT` | Có trong **cả hai** bên | Ai mua ở web **và** cửa hàng? | 1, 3, 6 |
| `EXCEPT` | Có ở bên trái nhưng **không có** ở bên phải | Ai mua ở web nhưng chưa mua tại cửa hàng? | 2, 4 |

### UNION: hợp của hai kết quả

~~~sql
SELECT customer_id FROM web_orders
UNION
SELECT customer_id FROM store_orders
ORDER BY customer_id;
-- 1, 2, 3, 4, 5, 6
~~~

`UNION` mặc định khử trùng. Nếu dùng `UNION ALL`, những giao dịch có cùng mã khách ở hai phía có thể làm mã đó xuất hiện nhiều lần; đây là kết quả đa tập, không phải tập mã khách duy nhất.

### INTERSECT: giao

~~~sql
SELECT customer_id FROM web_orders
INTERSECT
SELECT customer_id FROM store_orders
ORDER BY customer_id;
-- 1, 3, 6
~~~

### EXCEPT: hiệu

~~~sql
SELECT customer_id FROM web_orders
EXCEPT
SELECT customer_id FROM store_orders
ORDER BY customer_id;
-- 2, 4
~~~

`EXCEPT` là phép **có hướng**: đảo hai phía sẽ thay đổi ý nghĩa.

~~~sql
SELECT customer_id FROM store_orders
EXCEPT
SELECT customer_id FROM web_orders
ORDER BY customer_id;
-- 5
~~~

Ngược lại, `INTERSECT` về mặt **tập phần tử** có tính giao hoán: phần giao A với B giống phần giao B với A, nếu so đúng các cột cùng ý nghĩa và kiểu tương thích. Tuy nhiên **tên cột đầu ra** có thể chịu ảnh hưởng từ phía `SELECT` đầu tiên, nên đảo hai phía vẫn có thể làm thay đổi nhãn cột/metadata.

## 11. INTERSECT không giống INNER JOIN

### 11.1. INNER JOIN tạo cặp hàng khớp

Nếu dùng `JOIN` theo mã khách:

~~~sql
SELECT
    w.customer_id,
    w.web_order_id,
    s.store_order_id
FROM web_orders AS w
INNER JOIN store_orders AS s
    ON s.customer_id = w.customer_id
ORDER BY
    w.customer_id,
    w.web_order_id,
    s.store_order_id;
~~~

Kết quả:

| customer_id | web_order_id | store_order_id |
| ---: | ---: | ---: |
| 1 | 101 | 201 |
| 1 | 101 | 202 |
| 1 | 102 | 201 |
| 1 | 102 | 202 |
| 3 | 104 | 203 |
| 6 | 106 | 205 |
| 6 | 106 | 206 |

Có **7 hàng**:

- Khách `1` có hai giao dịch web và hai giao dịch cửa hàng → **2 × 2 = 4 cặp**.
- Khách `3` có một giao dịch mỗi kênh → **1 cặp**.
- Khách `6` có một giao dịch web và hai giao dịch cửa hàng → **2 cặp**.

`INNER JOIN` tạo ra **mỗi cặp hàng thỏa điều kiện nối**, còn `INTERSECT` trên chỉ một cột `customer_id` tạo ra **một hàng cho mỗi mã chung phân biệt**.

### 11.2. Có thể mô phỏng phần giao bằng JOIN và DISTINCT

~~~sql
SELECT DISTINCT
    w.customer_id
FROM web_orders AS w
INNER JOIN store_orders AS s
    ON s.customer_id = w.customer_id
ORDER BY w.customer_id;
-- 1, 3, 6
~~~

Với các khóa khách **không `NULL`** của ví dụ, câu này trả cùng tập mã như `INTERSECT`. Nhưng nó cần `DISTINCT` để loại những hàng lặp do `JOIN` tạo ra.

Không nên nghĩ `JOIN` lúc nào cũng thay thế `INTERSECT` mà không thay đổi ngữ nghĩa:

- `JOIN` có thể lấy cột từ **cả hai hàng nguồn** (giao dịch web và biên lai cửa hàng).
- `INTERSECT` chỉ trả các **hàng giá trị chung** giữa hai `SELECT`.
- `JOIN` với dấu `=` thông thường **không khớp hai giá trị `NULL`**, trong khi `INTERSECT` coi chúng là không phân biệt khi xác định phần giao.
- `JOIN` có thể tạo nhiều cặp cho một mã nếu mỗi bên có nhiều giao dịch.

Nếu bài toán chỉ hỏi **“những giá trị nào chung giữa hai tập?”**, `INTERSECT` thường diễn đạt trực tiếp hơn.

## 12. INTERSECT so với IN và EXISTS

Cùng bài toán khách đã mua cả hai kênh có thể được viết bằng `EXISTS`:

~~~sql
SELECT DISTINCT
    w.customer_id
FROM web_orders AS w
WHERE EXISTS (
    SELECT 1
    FROM store_orders AS s
    WHERE s.customer_id = w.customer_id
)
ORDER BY w.customer_id;
-- 1, 3, 6
~~~

Hoặc bằng `IN`:

~~~sql
SELECT DISTINCT
    w.customer_id
FROM web_orders AS w
WHERE w.customer_id IN (
    SELECT s.customer_id
    FROM store_orders AS s
)
ORDER BY w.customer_id;
-- 1, 3, 6
~~~

Với dữ liệu mẫu, ba cách trả cùng tập phân biệt:

1. `INTERSECT`.
2. `SELECT DISTINCT ... WHERE EXISTS`.
3. `SELECT DISTINCT ... WHERE ... IN (subquery)`.

### 12.1. Vì sao hai cách sau cần DISTINCT?

`EXISTS` và `IN` là **điều kiện lọc** trên các hàng của `web_orders`. An có hai hàng trong web nên khi cả hai thỏa điều kiện, nếu không có `DISTINCT`, ID `1` sẽ xuất hiện hai lần.

`INTERSECT` mặc định loại hàng trùng của kết quả giao, nên không cần thêm `DISTINCT`.

### 12.2. Tại sao không luôn chọn EXISTS?

`EXISTS` phù hợp khi:

- Điều kiện liên quan giữa hai nguồn **phức tạp hơn việc các hàng được chọn giống hệt nhau**.
- Cần biểu diễn “ít nhất một hàng bên kia thỏa điều kiện tương quan”.
- Muốn giữ các cột của một nguồn làm kết quả và lọc theo sự tồn tại.
- DBMS đích không hỗ trợ `INTERSECT` hoặc người viết cần kiểm soát rõ logic `NULL`.

`INTERSECT` phù hợp khi:

- Có hai truy vấn tự nhiên tạo ra **cùng cấu trúc hàng**.
- Muốn lấy **những hàng xuất hiện trong cả hai kết quả**, không cần cột bổ sung từ từng bản ghi khớp.
- Việc loại trùng theo hàng là đúng mục đích.
- Cần một biểu thức tập hợp ngắn gọn, dễ đọc.

Về **hiệu năng**, không có quy tắc rằng `INTERSECT` luôn nhanh hơn `EXISTS` hoặc `JOIN`. Bộ tối ưu có thể dùng chiến lược semi-join, sort/hash set operations hoặc kế hoạch khác. Hãy dùng `EXPLAIN` và dữ liệu đại diện khi hiệu năng quan trọng.

### 12.3. Vấn đề NULL khi viết lại

Nếu hai tập có `NULL`, `INTERSECT` có thể giữ một hàng `NULL` trong phần giao. Nhưng:

~~~sql
WHERE s.customer_id = w.customer_id
~~~

không xem `NULL = NULL` là `TRUE`, nên phiên bản `EXISTS` ở trên không khớp hai giá trị `NULL`.

Nếu nghiệp vụ **cần giữ đúng ý nghĩa set equality của INTERSECT** trong một bản viết lại, có thể dùng trên DBMS hỗ trợ:

~~~sql
WHERE s.customer_id IS NOT DISTINCT FROM w.customer_id
~~~

hoặc điều kiện:

~~~sql
WHERE s.customer_id = w.customer_id
   OR (
       s.customer_id IS NULL
       AND w.customer_id IS NULL
   )
~~~

và vẫn cần `DISTINCT` ở truy vấn ngoài nếu muốn các hàng phân biệt. Tuy nhiên, chỉ dùng cách null-safe khi việc coi hai hàng chưa xác định mã là chung **đúng theo nghiệp vụ**.

## 13. Kết hợp INTERSECT với nhiều phép toán tập hợp

Trong một truy vấn phức tạp có thể xuất hiện `UNION`, `INTERSECT`, `EXCEPT`. Vấn đề là **thứ tự ưu tiên** giữa các phép toán này và phạm vi của `ORDER BY`.

Nhiều hệ SQL, trong đó có PostgreSQL, cho `INTERSECT` **độ ưu tiên cao hơn** `UNION` và `EXCEPT`. Nếu viết:

~~~text
A UNION B INTERSECT C
~~~

thì nó có thể được hiểu như:

~~~text
A UNION (B INTERSECT C)
~~~

chứ không phải:

~~~text
(A UNION B) INTERSECT C
~~~

Phần ký hiệu trên minh họa ý nghĩa tập hợp, **không phải SQL chạy trực tiếp**.

Để tránh nhầm lẫn và khác biệt dialect, hãy **đặt nhóm rõ ràng** bằng ngoặc nếu DBMS hỗ trợ cú pháp phù hợp, hoặc dùng CTE:

~~~sql
WITH any_channel AS (
    SELECT customer_id
    FROM web_orders

    UNION

    SELECT customer_id
    FROM store_orders
)
SELECT customer_id
FROM any_channel

INTERSECT

SELECT customer_id
FROM customers
WHERE customer_id <= 3

ORDER BY customer_id;
-- 1, 2, 3
~~~

Trong ví dụ:

- `any_channel` gồm các mã `1, 2, 3, 4, 5, 6`.
- Tập khách có ID `<= 3` gồm `1, 2, 3`.
- Phần giao cuối gồm `1, 2, 3`.

Nếu muốn chỉ những người mua **cả hai kênh** và có ID `<= 3`, phải khác:

~~~sql
WITH both_channels AS (
    SELECT customer_id FROM web_orders
    INTERSECT
    SELECT customer_id FROM store_orders
)
SELECT customer_id
FROM both_channels
WHERE customer_id <= 3
ORDER BY customer_id;
-- 1, 3
~~~

Phân nhóm phép toán thay đổi kết quả. CTE giúp ghi rõ **tập trung gian** là gì, đặc biệt khi câu SQL dài hoặc có nhiều bộ lọc.

### ORDER BY đặt ở đâu?

Một `INTERSECT` tạo **kết quả không có thứ tự mặc định**. Muốn sắp xếp toàn bộ phần giao:

~~~sql
SELECT customer_id
FROM web_orders

INTERSECT

SELECT customer_id
FROM store_orders

ORDER BY customer_id DESC;
-- 6, 3, 1
~~~

`ORDER BY` ở cuối áp dụng cho **kết quả phép tập hợp**. Không nên đặt `ORDER BY` vào từng `SELECT` để kỳ vọng rằng phần giao sẽ giữ thứ tự của một bên. Cú pháp `ORDER BY` và `LIMIT`/`FETCH` bên trong từng toán hạng tập hợp cũng có quy tắc và giới hạn khác nhau giữa DBMS.

Nếu muốn **giới hạn số hàng của mỗi tập trước khi lấy giao**, cần nhóm từng toán hạng rõ ràng bằng subquery/CTE có điều kiện và thứ tự thích hợp. Nếu chỉ muốn **giới hạn số hàng sau khi lấy giao**, đặt giới hạn ở truy vấn cuối sau khi đã có `ORDER BY`.

## 14. INTERSECT có áp dụng cho dữ liệu ở cùng một bảng không?

Có. Hai phía của `INTERSECT` không bắt buộc đọc hai bảng khác nhau.

Ví dụ, nếu bảng `web_orders` có mã sản phẩm, ta có thể hỏi:

> Khách nào đã mua cả **Sổ tay (10)** lẫn **Bút bi (20)** trên website?

~~~sql
SELECT customer_id
FROM web_orders
WHERE product_id = 10

INTERSECT

SELECT customer_id
FROM web_orders
WHERE product_id = 20

ORDER BY customer_id;
~~~

Web có sản phẩm 10 ở khách `1, 2, 6`; có sản phẩm 20 ở khách `1, 3`. Phần giao là:

| customer_id |
| ---: |
| 1 |

Chỉ An đã mua cả hai loại sản phẩm trên website trong bộ dữ liệu mẫu.

Cách tương đương về mục đích là nhóm theo khách, kiểm tra có đủ cả hai sản phẩm:

~~~sql
SELECT customer_id
FROM web_orders
WHERE product_id IN (10, 20)
GROUP BY customer_id
HAVING COUNT(DISTINCT product_id) = 2
ORDER BY customer_id;
-- 1
~~~

Cách `GROUP BY` phù hợp khi cần kiểm tra **nhiều loại điều kiện cùng bảng** hoặc đếm số loại thuộc tập yêu cầu. Nhưng phải dùng `DISTINCT` trong `COUNT` nếu khách có thể mua cùng sản phẩm nhiều lần; hai giao dịch Sổ tay không tương đương với việc đã mua cả Sổ tay lẫn Bút bi.

`INTERSECT` trực tiếp biểu đạt giao hai tập, còn `GROUP BY ... HAVING` diễn đạt điều kiện trên số nhóm/loại. Chọn cách nào phụ thuộc độ rõ nghĩa và hiệu năng.

## 15. Lực lượng kết quả và công thức của phép giao

### 15.1. Số hàng kết quả mặc định

Gọi `A` là **tập hàng phân biệt** do truy vấn trái tạo ra, `B` là tập hàng phân biệt do truy vấn phải tạo ra.

Khi dùng `INTERSECT` mặc định:

\[
|A \cap B| \leq \min(|A|, |B|)
\]

Điều này có nghĩa **số hàng phân biệt** trong phần giao không thể vượt số hàng phân biệt của bất kỳ phía nào.

Trong dữ liệu mẫu:

~~~text
A = {1, 2, 3, 4, 6},  |A| = 5
B = {1, 3, 5, 6},     |B| = 4

A ∩ B = {1, 3, 6},    |A ∩ B| = 3
~~~

Phân biệt rõ **số bản ghi giao dịch** của bảng nguồn với **số giá trị khách phân biệt**. Hai bảng đều có sáu hàng giao dịch, nhưng điều đó không có nghĩa mỗi tập khách phân biệt đều có sáu phần tử.

### 15.2. Phần giao có thể rỗng

Nếu tìm khách mua sản phẩm 20 trên web và sản phẩm 40 ở cửa hàng:

~~~sql
SELECT customer_id
FROM web_orders
WHERE product_id = 20

INTERSECT

SELECT customer_id
FROM store_orders
WHERE product_id = 40;
~~~

Phía web có khách `1, 3`; phía cửa hàng sản phẩm 40 chỉ có khách `6`. Không có mã nào chung, nên truy vấn **hợp lệ và trả 0 hàng**.

Kết quả rỗng **không phải lỗi SQL**. Nó có nghĩa, theo điều kiện và dữ liệu hiện có, không có hàng nào thuộc cả hai tập.

### 15.3. Thay đổi số cột làm thay đổi số phần tử phân biệt

Với một cột `customer_id`, An chỉ đóng góp **một giá trị `1`** sau khử trùng.

Với hai cột `(customer_id, product_id)`, An có thể tạo các hàng phân biệt `(1,10)` và `(1,20)` ở web. Nhưng khi lấy giao với cửa hàng, chỉ `(1,10)` còn lại.

Vì vậy **thêm một cột vào `SELECT` không chỉ làm kết quả rộng hơn**, mà còn thay đổi chính **đơn vị được so sánh và khử trùng**.

## 16. Hiệu năng: điều gì xảy ra khi dữ liệu lớn?

Đối với bảng có hàng triệu giao dịch, `INTERSECT` phải xác định những hàng xuất hiện ở cả hai kết quả và, theo mặc định, loại trùng. DBMS có thể thực hiện bằng:

- Sắp xếp dữ liệu và so sánh các nhóm giá trị.
- Hash các hàng để tìm giá trị chung.
- Các biến đổi kế hoạch khác tùy bộ tối ưu, kiểu dữ liệu và số lượng hàng.

Không được mặc định `INTERSECT` luôn nhanh hơn mọi cách viết khác. Truy vấn có bộ lọc tốt và chỉ mục phù hợp có thể nhanh; truy vấn tạo hai tập kết quả lớn chứa nhiều cột hoặc nhiều giá trị trùng có thể tốn bộ nhớ/CPU.

### 16.1. Chỉ chọn những cột cần tìm giao

Nếu chỉ cần mã khách chung:

~~~sql
SELECT customer_id FROM web_orders
INTERSECT
SELECT customer_id FROM store_orders;
~~~

Đừng đưa thêm `web_order_id`, `store_order_id`, `product_id` hoặc các cột lớn không thuộc **định nghĩa phần giao**. Thêm cột có thể làm kết quả sai ý nghĩa và tăng chi phí so sánh/khử trùng.

### 16.2. Lọc càng đúng mức càng tốt

Giả sử chỉ quan tâm sản phẩm 10, hãy đặt điều kiện trong từng nguồn:

~~~sql
SELECT customer_id
FROM web_orders
WHERE product_id = 10

INTERSECT

SELECT customer_id
FROM store_orders
WHERE product_id = 10;
~~~

Khi chỉ vài giao dịch thuộc sản phẩm 10, bộ lọc có thể giúp DBMS giảm lượng dữ liệu đi vào phép tập hợp. Bộ tối ưu có thể đẩy điều kiện hoặc áp dụng phép biến đổi khác, nhưng **viết đúng bộ lọc theo yêu cầu nghiệp vụ** vẫn là bước đầu tiên.

### 16.3. Chỉ mục hỗ trợ các nguồn dữ liệu

Nếu thường xuyên lọc theo sản phẩm rồi lấy mã khách, có thể cân nhắc:

~~~sql
CREATE INDEX idx_web_orders_product_customer
    ON web_orders (product_id, customer_id);

CREATE INDEX idx_store_orders_product_customer
    ON store_orders (product_id, customer_id);
~~~

Thứ tự `(product_id, customer_id)` có thể phù hợp với các truy vấn có `WHERE product_id = ...` rồi đọc `customer_id`. Nếu truy vấn chủ yếu tìm giao của **toàn bộ khách hàng không lọc sản phẩm**, chỉ mục bắt đầu bằng `customer_id` có thể là lựa chọn khác tùy khối lượng và kế hoạch.

**Chỉ mục không tự làm phép `INTERSECT` miễn phí.** DBMS vẫn phải xác định giao và loại trùng. Việc thêm chỉ mục cũng làm tăng chi phí ghi và dung lượng; không tạo hàng loạt chỉ mục chỉ dựa trên cú pháp ví dụ.

### 16.4. Xem kế hoạch thực thi

Trong PostgreSQL:

~~~sql
EXPLAIN
SELECT customer_id FROM web_orders
INTERSECT
SELECT customer_id FROM store_orders;
~~~

Có thể dùng `EXPLAIN (ANALYZE, BUFFERS)` để đo thực thi thật. Với `SELECT`, thao tác này chạy truy vấn đọc; đối với câu lệnh ghi phải thận trọng về tác động. Bộ dữ liệu mẫu quá nhỏ nên DBMS có thể chọn quét toàn bảng; không lấy kết quả này làm kết luận cho bảng lớn.

Khi tối ưu, hãy so sánh **kết quả đúng theo ngữ nghĩa trước**, rồi mới đo `INTERSECT`, `EXISTS`/`JOIN` và những chỉ mục có thể dùng. Cách viết nhanh nhất nhưng làm mất quy tắc `NULL` hoặc biến kết quả thành các cặp giao dịch khác với yêu cầu là **không đúng**.

## 17. Tính khả chuyển giữa các DBMS

`INTERSECT` là toán tử tập hợp quen thuộc trong SQL, nhưng **khả năng hỗ trợ và chi tiết cú pháp có thể khác theo sản phẩm và phiên bản**.

| DBMS | `INTERSECT` cơ bản | Điểm cần lưu ý |
| --- | --- | --- |
| PostgreSQL | Có | Hỗ trợ `INTERSECT` và `INTERSECT ALL`; có các quy tắc ưu tiên/ngoặc cho phép toán tập hợp |
| SQL Server | Có | Cú pháp kết hợp với `ORDER BY`, kiểu cột và kế hoạch thực thi theo T-SQL; kiểm tra giới hạn loại dữ liệu |
| Oracle | Có | Cú pháp tập hợp và định dạng kiểu dữ liệu theo Oracle; việc hỗ trợ biến thể `ALL` phụ thuộc phiên bản |
| SQLite | Có | Có `INTERSECT` cơ bản, nhưng hạn chế và quy tắc của compound SELECT có đặc điểm riêng |
| MySQL / MariaDB | Tùy phiên bản | Không suy từ việc hệ hỗ trợ `UNION` rằng phiên bản đang chạy cũng hỗ trợ `INTERSECT` và `ALL` |

Những điểm cần xác minh khi chuyển truy vấn:

1. **Sản phẩm và phiên bản có hỗ trợ `INTERSECT` hay không?**
2. **Có hỗ trợ `INTERSECT ALL` không?** Nếu không, dùng `INTERSECT` mặc định hoặc thiết kế một cách tính bội số khác.
3. **Quy tắc tương thích kiểu** ở cùng vị trí cột là gì?
4. **Collation** tác động thế nào đến so sánh chuỗi? Hai tên có khác chữ hoa/thường hay dấu có thể được coi là giống nhau tùy collation và DBMS.
5. **NULL** trong set operations được xử lý theo quy tắc tập hợp, nhưng khi viết lại bằng `JOIN`/`IN` cần xét riêng.
6. **ORDER BY, LIMIT/FETCH/TOP** và ngoặc của các truy vấn thành phần có cú pháp gì?
7. Kế hoạch hash/sort và hiệu năng có phù hợp với dữ liệu thực không?

Nếu cần một cách viết thay thế cho phép giao mã khách khi DBMS không hỗ trợ `INTERSECT`, có thể dùng:

~~~sql
SELECT DISTINCT w.customer_id
FROM web_orders AS w
WHERE EXISTS (
    SELECT 1
    FROM store_orders AS s
    WHERE s.customer_id = w.customer_id
)
ORDER BY w.customer_id;
~~~

Với hai cột `customer_id NOT NULL` trong ví dụ, truy vấn này trả đúng `1, 3, 6`. Nếu sử dụng trên cột nullable hoặc cần giao nhiều cột, phải điều chỉnh điều kiện tương đương với quy tắc phần giao, không bê nguyên mẫu này rồi mặc định hoàn toàn giống nhau.

## 18. Những lỗi và hiểu nhầm thường gặp

| Lỗi hoặc ngộ nhận | Vấn đề | Cách khắc phục |
| --- | --- | --- |
| “`INTERSECT` ghép từng giao dịch như `JOIN`.” | Nó lấy các **hàng giá trị chung**, không tạo cặp nguồn | Dùng `JOIN` nếu cần thông tin từ từng cặp giao dịch |
| “An có hai đơn mỗi bên nên `INTERSECT` trả hai hàng An.” | Mặc định khử trùng | Dùng `INTERSECT ALL` chỉ khi cần bội số và DBMS hỗ trợ |
| Chọn một cột bên trái, hai cột bên phải | Không khớp số cột | Chọn cùng số cột |
| Đảo `customer_id` và `product_id` ở phía phải | Có thể chạy nhưng so sai ý nghĩa theo vị trí | Giữ cùng thứ tự và kiểu dữ liệu |
| Đưa mã giao dịch vào phép giao khách–sản phẩm | So thêm cột không thuộc tiêu chí giao | Chỉ chọn cột định nghĩa phần giao |
| Nghĩ `NULL INTERSECT NULL` không có kết quả vì `NULL = NULL` không TRUE | Nhầm logic so sánh với quy tắc set equality | Hiểu `NULL` được coi là không phân biệt trong set operations |
| Viết lại bằng `JOIN` rồi quên `DISTINCT` | Nhân hàng theo số cặp khớp | Dùng `INTERSECT` hoặc `DISTINCT` theo mức hạt mong muốn |
| Dùng `IN (SELECT ...)` và cho rằng tương đương với `INTERSECT` khi có NULL | `IN` dùng logic ba giá trị | Kiểm tra `NULL` và quy tắc nghiệp vụ |
| Dùng `ORDER BY` của từng toán hạng để sắp phần giao | Không bảo đảm thứ tự kết quả cuối | Đặt `ORDER BY` ở truy vấn ngoài cùng |
| Kết hợp `UNION`/`INTERSECT`/`EXCEPT` không nhóm rõ | Có thể hiểu sai ưu tiên toán tử | Dùng CTE/ngoặc tường minh |
| Thêm `DISTINCT` vào cả hai nguồn một cách máy móc | Có thể tạo xử lý thừa, không đổi tập kết quả mặc định | Chỉ dùng khi có mục đích rõ |
| Coi tập kết quả rỗng là lỗi SQL | Giao hai tập có thể rỗng hợp lệ | Xử lý kết quả 0 hàng trong ứng dụng |
| So chuỗi mã ở hai nguồn với collation khác nhau | Có thể ra tập giao không như kỳ vọng | Chuẩn hóa kiểu/collation và quy tắc dữ liệu |
| Cho rằng `INTERSECT ALL` hoạt động ở mọi SQL dialect | Phạm vi hỗ trợ khác nhau | Xác minh DBMS/phiên bản trước khi dùng |
| Tối ưu bằng `JOIN` mà không kiểm tra ý nghĩa thống kê | Dễ tạo fanout | Xác định mức hạt và đo kế hoạch sau khi đảm bảo đúng kết quả |

## 19. Bài tập thực hành

Dùng dữ liệu mẫu ở mục 2, không sửa các bảng trong quá trình làm bài. Mỗi bài tập có một đáp án tham khảo; nên dự đoán kết quả trước khi xem.

### Bài 1 — Giao mã khách giữa hai kênh

Viết câu SQL tìm các mã khách mua hàng trên **cả website lẫn cửa hàng**, sắp tăng dần.

**Đáp án:**

~~~sql
SELECT customer_id FROM web_orders
INTERSECT
SELECT customer_id FROM store_orders
ORDER BY customer_id;
~~~

Kết quả: **1, 3, 6**. Các bản ghi trùng mã khách trong mỗi kênh không làm tăng số hàng `INTERSECT` mặc định.

### Bài 2 — Giao theo khách và sản phẩm

Viết câu SQL tìm **cặp khách–sản phẩm** có ở cả hai kênh.

**Đáp án:**

~~~sql
SELECT customer_id, product_id FROM web_orders
INTERSECT
SELECT customer_id, product_id FROM store_orders
ORDER BY customer_id, product_id;
~~~

Kết quả: **(1, 10)** và **(6, 10)**. Khách Chi ID 3 có mặt ở hai kênh nhưng mua **hai sản phẩm khác nhau**, nên không xuất hiện trong phần giao cặp giá trị.

### Bài 3 — Đếm hàng của INTERSECT ALL

Không thay dữ liệu, nếu DBMS hỗ trợ `INTERSECT ALL`, truy vấn giao chỉ một cột `customer_id` trả bao nhiêu hàng?

**Đáp án:** **4 hàng**, gồm `1, 1, 3, 6` khi sắp theo mã tăng dần. Với mã 1, số lần xuất hiện là `min(2, 2) = 2`; mã 6 là `min(1, 2) = 1`.

### Bài 4 — Đổi điều kiện hai phía

Tìm khách đã mua **Bút bi (20) trên web** và **Bàn phím (30) ở cửa hàng**.

**Đáp án:**

~~~sql
SELECT customer_id
FROM web_orders
WHERE product_id = 20
INTERSECT
SELECT customer_id
FROM store_orders
WHERE product_id = 30
ORDER BY customer_id;
~~~

Kết quả: **3 — Chi**.

### Bài 5 — Phần giao rỗng

Dự đoán kết quả của:

~~~sql
SELECT customer_id FROM web_orders WHERE product_id = 20
INTERSECT
SELECT customer_id FROM store_orders WHERE product_id = 40;
~~~

**Đáp án:** **0 hàng**, vì các mã khách web mua Bút bi là `1` và `3`, trong khi cửa hàng có sản phẩm Chuột mã 40 chỉ ở khách `6`. Hai tập không có phần tử chung.

### Bài 6 — Tìm khách đã mua cả hai loại sản phẩm ở cùng kênh

Tìm khách mua cả **Sổ tay (10)** và **Bút bi (20)** trên website bằng `INTERSECT` giữa hai truy vấn cùng bảng.

**Đáp án:**

~~~sql
SELECT customer_id FROM web_orders WHERE product_id = 10
INTERSECT
SELECT customer_id FROM web_orders WHERE product_id = 20
ORDER BY customer_id;
~~~

Kết quả: **1 — An**.

### Bài 7 — So với INNER JOIN

Vì sao câu truy vấn:

~~~sql
SELECT w.customer_id, w.web_order_id, s.store_order_id
FROM web_orders AS w
JOIN store_orders AS s
    ON s.customer_id = w.customer_id;
~~~

trả **7 hàng**, còn:

~~~sql
SELECT customer_id FROM web_orders
INTERSECT
SELECT customer_id FROM store_orders;
~~~

trả **3 hàng**?

**Đáp án:** `JOIN` tạo **mỗi cặp giao dịch có cùng mã khách**, vì thế An có `2 × 2 = 4` cặp và Lan có `1 × 2 = 2` cặp. `INTERSECT` một cột chỉ giữ **mã khách phân biệt chung** là `1`, `3`, `6`.

### Bài 8 — Giao và NULL

Dự đoán số hàng của:

~~~sql
SELECT CAST(NULL AS INTEGER) AS code
INTERSECT
SELECT CAST(NULL AS INTEGER) AS code;
~~~

Sau đó giải thích vì sao điều này không mâu thuẫn với `NULL = NULL` không trả `TRUE`.

**Đáp án:** một hàng `NULL`. Phép tập hợp áp dụng quy tắc **không phân biệt các ô `NULL` tương ứng** khi xác định hàng chung. Phép so sánh `=` thông thường thuộc logic ba giá trị và hoạt động khác.

### Bài 9 — Thêm tên khách sau phép giao

Viết truy vấn trả mã và tên của khách mua ở cả hai kênh, không đưa tên khách vào hai nhánh `INTERSECT`.

**Đáp án:**

~~~sql
WITH common_customers AS (
    SELECT customer_id FROM web_orders
    INTERSECT
    SELECT customer_id FROM store_orders
)
SELECT c.customer_id, c.customer_name
FROM customers AS c
JOIN common_customers AS x
    ON x.customer_id = c.customer_id
ORDER BY c.customer_id;
~~~

Kết quả: **(1, An)**, **(3, Chi)**, **(6, Lan)**.

### Bài 10 — Phân biệt UNION, INTERSECT và EXCEPT

Dự đoán kết quả của ba câu truy vấn:

~~~sql
-- A
SELECT customer_id FROM web_orders
UNION
SELECT customer_id FROM store_orders;

-- B
SELECT customer_id FROM web_orders
INTERSECT
SELECT customer_id FROM store_orders;

-- C
SELECT customer_id FROM web_orders
EXCEPT
SELECT customer_id FROM store_orders;
~~~

**Đáp án:** A có các mã **1, 2, 3, 4, 5, 6**; B có **1, 3, 6**; C có **2, 4**. Khi không có `ORDER BY`, **thứ tự hiển thị không được bảo đảm**.

### Bài 11 — Tìm lỗi thứ tự cột

Hai bên của truy vấn sau có cùng số cột và đều là số:

~~~sql
SELECT customer_id, product_id FROM web_orders
INTERSECT
SELECT product_id, customer_id FROM store_orders;
~~~

Tại sao không nên dùng để tìm các cặp khách–sản phẩm chung?

**Đáp án:** các phép toán tập hợp so theo **vị trí cột**, nên cột `customer_id` bên trái đang được so với `product_id` bên phải. Phải sửa thứ tự bên phải thành `customer_id, product_id`.

### Bài 12 — Thiết kế một truy vấn thay thế

Nếu DBMS đang dùng chưa hỗ trợ `INTERSECT`, hãy viết truy vấn trả đúng các khách hàng chung **trong dữ liệu mẫu** bằng `EXISTS`.

**Đáp án:**

~~~sql
SELECT DISTINCT w.customer_id
FROM web_orders AS w
WHERE EXISTS (
    SELECT 1
    FROM store_orders AS s
    WHERE s.customer_id = w.customer_id
)
ORDER BY w.customer_id;
~~~

Kết quả: **1, 3, 6**. `DISTINCT` cần thiết vì một khách có thể có nhiều `web_orders`. Nếu cột tham gia có `NULL` và cần giữ ngữ nghĩa so khớp `NULL` của phép giao, phải dùng điều kiện tương đương có xét `NULL` theo DBMS.

## 20. Tổng kết

**`INTERSECT` tìm các hàng có mặt trong cả hai kết quả `SELECT`**. Ở dạng mặc định, nó trả **mỗi hàng phân biệt một lần**, kể cả khi nguồn có nhiều hàng trùng. Với nhiều cột, phép giao xét **toàn bộ bộ giá trị theo đúng thứ tự cột**, không chỉ một khóa riêng lẻ.

Khi sử dụng, hãy kiểm tra năm điểm:

1. **Đối tượng chung là gì?** Khách hàng, sản phẩm hay cặp khách–sản phẩm?
2. **Hai phía có cùng số cột, thứ tự và kiểu tương thích không?**
3. **Có cần giữ số lần xuất hiện?** Nếu có, xem `INTERSECT ALL` có được DBMS hỗ trợ và có đúng ý nghĩa hay không.
4. **Có `NULL` không?** Quy tắc so khớp hàng của phép tập hợp khác phép `=` thông thường và có thể khác khi viết lại bằng `IN`/`JOIN`.
5. **Kết quả cần sắp xếp và dùng tiếp không?** Đặt `ORDER BY` ở đầu ra cuối cùng; dùng CTE hoặc truy vấn con để lấy thêm thông tin từ những bảng khác.

Đối với câu hỏi **“Giá trị nào xuất hiện trong cả hai tập dữ liệu?”**, `INTERSECT` thường là biểu thức gọn và đúng ý nghĩa nhất. Nếu cần từng **cặp hàng liên quan**, dùng `JOIN`; nếu chỉ cần kiểm tra **có hàng khớp không**, `EXISTS` có thể phù hợp. Hãy chọn toán tử dựa trên **mức hạt và ý nghĩa của kết quả**, rồi mới xét phương án tối ưu trên dữ liệu thực.
