# Điều kiện trên nhiều cột và phép so sánh hàng theo phương ngữ

Khi lọc dữ liệu bằng SQL, không phải lúc nào ta cũng chỉ so sánh một cột với một giá trị. Những câu hỏi như **“đơn của khách 10 trong ngày 01/04”**, **“cặp mã khách hàng và ngày đặt hàng nằm trong danh sách cho phép”**, hay **“lấy những đơn nằm sau một vị trí cụ thể theo thứ tự ngày và mã đơn”** đều liên quan đến **nhiều cột cùng lúc**.

SQL cho phép kết hợp điều kiện bằng **AND**, **OR**, **NOT**. Một số hệ quản trị còn hỗ trợ **phép so sánh hàng** (*row comparison*, *row-value comparison*) để so sánh trực tiếp một bộ giá trị như **(order_date, order_id)** với một bộ giá trị khác. Những phép so sánh này tuân theo quy tắc **theo thứ tự từ trái sang phải** (*lexicographic ordering*) khi dùng các toán tử lớn hơn, nhỏ hơn; chúng **không** có nghĩa là tất cả cột đều phải lớn hơn hoặc nhỏ hơn tương ứng.

Bài học nằm trong chương **Điều kiện lọc** của module **Database SQL**. Các ví dụ có thể chạy trực tiếp trên **PostgreSQL 15 trở lên**, rồi được đối chiếu với **MySQL 8.0**, **SQLite 3.15 trở lên** và **SQL Server** để thấy giới hạn của từng phương ngữ. SQL giữa các hệ quản trị có nhiều điểm chung, nhưng không nên giả định cú pháp so sánh hàng chạy giống nhau ở mọi hệ.

## 1. Mục tiêu của bài

Sau bài này, bạn có thể:

1. Viết các điều kiện kết hợp **AND/OR/NOT** trên nhiều cột và đặt ngoặc đúng.
2. Hiểu sự khác nhau giữa **từng điều kiện đơn lẻ** và **một cặp/tổ hợp giá trị được so sánh như một hàng**.
3. Dùng phép bằng, khác, nhỏ hơn, lớn hơn giữa hai bộ giá trị trong hệ hỗ trợ.
4. Phân biệt **so sánh hàng theo thứ tự từ điển** với so sánh từng thành phần bằng AND.
5. Dùng **IN** với nhiều cột để kiểm tra các **cặp giá trị tương ứng**, tránh tạo các tổ hợp không mong muốn.
6. Xử lý **NULL** trong phép so sánh hàng, nhất là với **NOT IN**.
7. Áp dụng phép so sánh hàng vào **phân trang theo khóa** (*keyset pagination*) và điều kiện trên khóa ghép.
8. Viết cách diễn đạt tương đương bằng **AND/OR/EXISTS** khi phương ngữ không có cú pháp row-value mong muốn.

## 2. Tạo dữ liệu ví dụ độc lập

Các phần thực hành PostgreSQL sử dụng một **bảng tạm**. Dữ liệu giả lập gồm 12 đơn hàng, một số khách có nhiều đơn trong cùng ngày, và một số địa chỉ giao hàng chưa được nhập. Bảng tạm chỉ tồn tại trong phiên kết nối hiện tại.

~~~sql
CREATE TEMP TABLE multi_filter_orders (
    order_id      INTEGER PRIMARY KEY,
    customer_id   INTEGER NOT NULL,
    order_date    DATE NOT NULL,
    status        TEXT NOT NULL,
    total_vnd     NUMERIC(12, 2) NOT NULL,
    shipping_city TEXT,
    sales_channel TEXT NOT NULL
);

INSERT INTO multi_filter_orders
    (order_id, customer_id, order_date, status,
     total_vnd, shipping_city, sales_channel)
VALUES
    (1001, 10, '2026-04-01', 'paid',      350000, 'Ha Noi',  'web'),
    (1002, 10, '2026-04-01', 'pending',   180000, 'Ha Noi',  'app'),
    (1003, 11, '2026-04-02', 'paid',      700000, 'Da Nang', 'web'),
    (1004, 12, '2026-04-02', 'cancelled', 500000, NULL,      'app'),
    (1005, 10, '2026-04-03', 'paid',      900000, 'Ha Noi',  'web'),
    (1006, 13, '2026-04-03', 'paid',      250000, 'HCM',     'app'),
    (1007, 11, '2026-04-03', 'pending',   125000, 'Da Nang', 'web'),
    (1008, 14, '2026-04-04', 'paid',      610000, NULL,      'web'),
    (1009, 13, '2026-04-04', 'paid',      740000, 'HCM',     'app'),
    (1010, 15, '2026-04-05', 'pending',   300000, 'Hue',     'app'),
    (1011, 10, '2026-04-05', 'paid',      415000, 'Ha Noi',  'app'),
    (1012, 14, '2026-04-05', 'cancelled', 100000, 'HCM',     'web');
~~~

Có thể xem dữ liệu theo thứ tự ngày và mã đơn:

~~~sql
SELECT order_id, customer_id, order_date, status,
       total_vnd, shipping_city, sales_channel
FROM multi_filter_orders
ORDER BY order_date, order_id;
~~~

Các ví dụ bên dưới dùng **ngày theo định dạng ISO YYYY-MM-DD** và **tiền theo đơn vị VND**. Đây là dữ liệu học tập, không phải đơn hàng thật.

> Nếu chạy lại lệnh tạo bảng trong cùng phiên PostgreSQL, bảng đã tồn tại. Hãy mở phiên mới hoặc xóa riêng bảng tạm **multi_filter_orders** trước khi tạo lại. Không cần xóa dữ liệu của các bài khác.

## 3. Điều kiện trên nhiều cột bằng AND, OR, NOT

Cách phổ biến nhất để lọc theo nhiều cột là kết hợp các điều kiện độc lập.

### 3.1. AND: tất cả điều kiện phải đúng

Ví dụ: tìm đơn **của khách 10**, **đã thanh toán**, **giá trị từ 300.000 VND trở lên**:

~~~sql
SELECT order_id, customer_id, status, total_vnd
FROM multi_filter_orders
WHERE customer_id = 10
  AND status = 'paid'
  AND total_vnd >= 300000
ORDER BY order_id;
~~~

Các đơn phù hợp là **1001, 1005, 1011**. Một hàng chỉ được chọn khi **cả ba** biểu thức điều kiện cho TRUE.

### 3.2. OR: ít nhất một điều kiện đúng

Ví dụ: tìm đơn được gửi tới **Ha Noi hoặc HCM**:

~~~sql
SELECT order_id, shipping_city
FROM multi_filter_orders
WHERE shipping_city = 'Ha Noi'
   OR shipping_city = 'HCM'
ORDER BY order_id;
~~~

Lệnh giữ các đơn có địa điểm thuộc một trong hai giá trị. Có thể viết ngắn hơn bằng:

~~~sql
SELECT order_id, shipping_city
FROM multi_filter_orders
WHERE shipping_city IN ('Ha Noi', 'HCM')
ORDER BY order_id;
~~~

**IN trên một cột** tiện cho việc kiểm tra nhiều giá trị của **cùng cột**. Phần sau sẽ dùng IN trên **một bộ nhiều cột**.

### 3.3. Ngoặc quyết định ý nghĩa

Muốn lấy **đơn đã thanh toán và giao tới Ha Noi hoặc HCM**, viết:

~~~sql
SELECT order_id, status, shipping_city
FROM multi_filter_orders
WHERE status = 'paid'
  AND (shipping_city = 'Ha Noi' OR shipping_city = 'HCM')
ORDER BY order_id;
~~~

Kết quả gồm **1001, 1005, 1006, 1009, 1011**.

Nếu bỏ ngoặc:

~~~sql
WHERE status = 'paid'
  AND shipping_city = 'Ha Noi'
   OR shipping_city = 'HCM'
~~~

SQL hiểu theo độ ưu tiên **AND trước OR**. Vì vậy, điều kiện còn chọn **1012**, một đơn **cancelled** có shipping_city = 'HCM'. Đây là lỗi logic, dù cú pháp SQL vẫn hợp lệ.

Một cách diễn giải rõ yêu cầu là:

~~~text
status = paid
      AND
(city = Ha Noi OR city = HCM)
~~~

**NOT** được đánh giá trước AND, còn OR sau AND theo quy tắc ưu tiên thông thường. Khi truy vấn phức tạp, nên đặt ngoặc để làm rõ ý định thay vì buộc người đọc phải nhớ thứ tự ưu tiên.

### 3.4. NULL khiến nhiều biểu thức trở thành UNKNOWN

Hai đơn **1004, 1008** có shipping_city = NULL. Điều kiện:

~~~sql
WHERE shipping_city <> 'Ha Noi'
~~~

không chọn hai đơn đó vì so sánh với NULL cho **UNKNOWN**, trong khi WHERE chỉ giữ TRUE.

Nếu yêu cầu là “giao tới nơi khác Ha Noi **hoặc chưa biết nơi giao**”, viết:

~~~sql
SELECT order_id, shipping_city
FROM multi_filter_orders
WHERE shipping_city <> 'Ha Noi'
   OR shipping_city IS NULL
ORDER BY order_id;
~~~

Điều kiện có nhiều cột càng cần lưu ý UNKNOWN, đặc biệt khi sử dụng **NOT**, **IN** và phép so sánh hàng.

## 4. Khi nào cần so sánh một hàng nhiều giá trị?

Giả sử mã khách hàng **10** có đơn ở nhiều ngày. Yêu cầu là tìm **tổ hợp (customer_id, order_date)** bằng **(10, ngày 01/04/2026)**. Ta có thể viết:

~~~sql
SELECT order_id, customer_id, order_date
FROM multi_filter_orders
WHERE customer_id = 10
  AND order_date = DATE '2026-04-01'
ORDER BY order_id;
~~~

PostgreSQL cũng cho phép so sánh trực tiếp **hai hàng giá trị**:

~~~sql
SELECT order_id, customer_id, order_date
FROM multi_filter_orders
WHERE (customer_id, order_date) =
      (10, DATE '2026-04-01')
ORDER BY order_id;
~~~

Hai truy vấn đều trả về **1001, 1002**.

Biểu thức **(customer_id, order_date)** không phải một phép tính số học. Nó là **row value**, gồm hai thành phần ở vị trí đã xác định. Bên phải cũng phải có hai thành phần kiểu dữ liệu tương thích ở từng vị trí.

Trong PostgreSQL, có thể viết tường minh bằng **ROW(...)**:

~~~sql
WHERE ROW(customer_id, order_date) =
      ROW(10, DATE '2026-04-01')
~~~

Với **hai thành phần trở lên**, PostgreSQL thường cho phép bỏ từ khóa ROW. Tuy nhiên, **(customer_id)** chỉ là một biểu thức đặt trong ngoặc, không phải một cặp giá trị hai thành phần; số thành phần của các vế so sánh phải tương ứng.

### So sánh hàng và khóa ghép

Một khóa tự nhiên có thể gồm hai trường, chẳng hạn **(order_id, product_id)** của bảng chi tiết đơn hàng. Muốn truy xuất một bản ghi theo cả khóa:

~~~sql
-- Với bảng order_items(order_id, product_id, quantity):
SELECT order_id, product_id, quantity
FROM order_items
WHERE (order_id, product_id) = (1001, 102);
~~~

Ví dụ này minh họa cách đọc khóa ghép; **order_items** không được tạo trong dữ liệu tạm ở phần 2. Với hệ không hỗ trợ so sánh hàng, điều kiện tương đương là:

~~~sql
WHERE order_id = 1001 AND product_id = 102
~~~

**So sánh bằng của hàng** là cách viết gọn để thể hiện rằng các giá trị cùng thuộc **một tổ hợp**.

## 5. Các toán tử so sánh hàng: bằng, khác và thứ tự

Trong PostgreSQL, phép so sánh hàng thông thường hỗ trợ:

| Toán tử | Ý nghĩa với hai hàng giá trị |
| --- | --- |
| **=** | Mọi thành phần tương ứng phải bằng nhau (với quy tắc ba giá trị khi có NULL) |
| **<>** hoặc **!=** | Hai hàng khác nhau nếu có ít nhất một cặp thành phần xác định khác nhau |
| **<**, **<=** | So sánh theo thứ tự từ trái sang phải |
| **>**, **>=** | So sánh theo thứ tự từ trái sang phải |
| **IS DISTINCT FROM** | So sánh khác nhau với quy tắc NULL xác định trong PostgreSQL |
| **IS NOT DISTINCT FROM** | So sánh bằng nhau với quy tắc NULL xác định trong PostgreSQL |

Các toán tử có thứ tự yêu cầu kiểu của từng cặp thành phần có phép so sánh phù hợp. Ví dụ **DATE** so với **DATE**, **INTEGER** so với **INTEGER**; không nên so sánh tùy tiện một cột DATE với chuỗi có định dạng mơ hồ.

### 5.1. Bằng và khác của cả hàng

~~~sql
SELECT
    (1, 2) = (1, 2)   AS equal_rows,
    (1, 2) = (1, 3)   AS unequal_rows,
    (1, 2) <> (1, 3)  AS distinct_rows;
~~~

Kết quả là **TRUE, FALSE, TRUE**.

Có thể hình dung:

~~~text
(a, b) = (x, y)

  tương đương, khi các giá trị đều không NULL:

(a = x) AND (b = y)
~~~

Tương tự, với các giá trị đều không NULL:

~~~text
(a, b) <> (x, y)

(a <> x) OR (b <> y)
~~~

Điều này khác hẳn phép so sánh “mọi cột phải khác nhau”:

~~~sql
-- Không cùng nghĩa với (a, b) <> (x, y):
WHERE a <> x AND b <> y
~~~

Nếu a khác x nhưng b bằng y, **hai hàng đã khác nhau**, trong khi điều kiện AND phía trên lại FALSE.

### 5.2. So sánh thứ tự là so sánh từ trái sang phải

Với hai bộ **(a, b)** và **(x, y)**, SQL so sánh thành phần đầu tiên trước:

1. Nếu **a < x** được xác định là TRUE, thì **(a, b) < (x, y)** là TRUE, bất kể b và y.
2. Nếu **a > x** được xác định là TRUE, kết quả nhỏ hơn là FALSE.
3. Nếu **a = x**, mới cần so sánh **b** với **y**.
4. Nếu phải dựa vào một so sánh chứa NULL chưa xác định, kết quả có thể là UNKNOWN.

Ví dụ:

~~~sql
SELECT
    (2, 1) > (1, 9999) AS first_column_decides,
    (2, 1) > (2, 0)    AS second_column_decides,
    (2, 1) > (2, 9)    AS second_column_rejects;
~~~

Kết quả lần lượt **TRUE, TRUE, FALSE**.

Đặc biệt, **(2, 1) > (1, 9999) là TRUE** dù **1 > 9999 là FALSE**, vì cột đầu tiên **2 > 1** đã quyết định. So sánh hàng **không phải** phép AND của hai dấu lớn hơn.

Với cặp giá trị không NULL:

\[
(a,b)>(x,y)\quad\Longleftrightarrow\quad
(a>x)\ \mathrm{OR}\ (a=x\ \mathrm{AND}\ b>y).
\]

Tương tự:

\[
(a,b)<(x,y)\quad\Longleftrightarrow\quad
(a<x)\ \mathrm{OR}\ (a=x\ \mathrm{AND}\ b<y).
\]

Đây cũng là cách triển khai thay thế trong phương ngữ không hỗ trợ phép so sánh hàng.

### 5.3. So sánh ba cột trở lên

Nếu cần so sánh bộ **(a, b, c)**, các giá trị được xét lần lượt từ **a → b → c**, chỉ chuyển sang cột sau nếu cột trước bằng nhau.

Ví dụ:

~~~sql
SELECT
    (1, 4, 9) < (1, 5, 0) AS result_one,
    (1, 4, 9) < (1, 4, 8) AS result_two;
~~~

Kết quả: **TRUE** vì 4 < 5 trong cặp đầu; **FALSE** vì 9 < 8 là FALSE trong cặp thứ hai. Không cần tổng hay lấy trung bình ba thành phần.

## 6. NULL trong so sánh hàng

Khi hàng có NULL, cần phân biệt **toán tử bằng/khác**, **toán tử thứ tự** và **cách xử lý NULL chủ đích**.

### 6.1. Bằng nhau khi có NULL

~~~sql
SELECT
    ROW(1, NULL::INTEGER) = ROW(1, NULL::INTEGER)
        AS same_known_part,
    ROW(1, NULL::INTEGER) = ROW(2, NULL::INTEGER)
        AS different_first_part,
    ROW(1, NULL::INTEGER) <> ROW(1, 7)
        AS not_equal_unknown_part;
~~~

Kết quả lần lượt:

| Biểu thức | Kết quả |
| --- | --- |
| (1, NULL) = (1, NULL) | **UNKNOWN** |
| (1, NULL) = (2, NULL) | **FALSE** |
| (1, NULL) <> (1, 7) | **UNKNOWN** |

Giải thích:

- Hai thành phần thứ nhất bằng nhau nhưng thành phần thứ hai không thể so sánh bằng bằng toán tử thông thường, nên **UNKNOWN**.
- Trong trường hợp thứ hai, **1 = 2** chắc chắn FALSE, đủ kết luận hai hàng không bằng nhau.
- Ở trường hợp thứ ba, ta không biết NULL có bằng 7 hay không; vì thành phần đầu giống nhau, kết quả **<>** chưa xác định.

**NULL = NULL không phải TRUE**; với so sánh nhiều cột, đừng tự coi hai hàng cùng thiếu thông tin là bằng nhau nếu đang dùng toán tử **=**.

### 6.2. Thứ tự với NULL: thành phần trước có thể đã quyết định

~~~sql
SELECT
    ROW(1, NULL::INTEGER) < ROW(2, 0) AS decided_early,
    ROW(1, NULL::INTEGER) < ROW(1, 0) AS undecidable_later;
~~~

Kết quả là **TRUE**, **UNKNOWN**.

Ở biểu thức đầu, **1 < 2** đã đúng nên không cần xét NULL ở cột thứ hai. Biểu thức sau có thành phần đầu bằng nhau, phải so sánh NULL với 0 nên kết quả UNKNOWN.

Nếu một so sánh hàng trong **WHERE** cho UNKNOWN, hàng đó sẽ **không được chọn**, vì WHERE chỉ giữ TRUE.

### 6.3. So sánh an toàn với NULL khi nghiệp vụ yêu cầu

PostgreSQL hỗ trợ **IS [NOT] DISTINCT FROM** để trả về TRUE/FALSE cả khi có NULL:

~~~sql
SELECT
    ROW(NULL::TEXT, 'paid')
        IS NOT DISTINCT FROM ROW(NULL::TEXT, 'paid')
        AS same_missing_value,
    ROW(NULL::TEXT, 'paid')
        IS DISTINCT FROM ROW('Ha Noi', 'paid')
        AS different_city;
~~~

Cả hai biểu thức trên trả về **TRUE**. Trong quy tắc này, hai NULL ở cùng vị trí được coi là **không khác nhau**.

Áp dụng với bảng mẫu:

~~~sql
SELECT order_id, shipping_city, status
FROM multi_filter_orders
WHERE ROW(shipping_city, status)
      IS NOT DISTINCT FROM ROW(NULL::TEXT, 'paid')
ORDER BY order_id;
~~~

Kết quả là **1008**: chưa có shipping_city và status = 'paid'. Cách viết tường minh, dễ chuyển đổi giữa các hệ hơn:

~~~sql
WHERE shipping_city IS NULL AND status = 'paid'
~~~

Quyết định coi hai NULL là tương ứng phải xuất phát từ **ý nghĩa nghiệp vụ**. Hai khách đều thiếu địa chỉ không chứng minh họ sống cùng một thành phố.

## 7. IN với nhiều cột: giữ đúng các cặp tương ứng

Đây là một trong những ứng dụng quan trọng nhất của row-value comparison. Giả sử cần lấy các đơn thỏa **một trong hai cặp**:

- **(customer_id = 10, order_date = 01/04/2026)**.
- **(customer_id = 13, order_date = 03/04/2026)**.

Nếu viết các điều kiện theo từng cặp:

~~~sql
SELECT order_id, customer_id, order_date
FROM multi_filter_orders
WHERE (customer_id = 10 AND order_date = DATE '2026-04-01')
   OR (customer_id = 13 AND order_date = DATE '2026-04-03')
ORDER BY order_id;
~~~

Kết quả: **1001, 1002, 1006**.

Trong PostgreSQL, có thể diễn đạt trực tiếp bằng **IN với cặp giá trị**:

~~~sql
SELECT order_id, customer_id, order_date
FROM multi_filter_orders
WHERE (customer_id, order_date) IN (
    (10, DATE '2026-04-01'),
    (13, DATE '2026-04-03')
)
ORDER BY order_id;
~~~

Kết quả giống hệt: **1001, 1002, 1006**. Mỗi hàng bên phải là một **tổ hợp được phép**; SQL không hoán đổi các phần tử giữa các cặp.

### Sai lầm: dùng hai IN độc lập

~~~sql
SELECT order_id, customer_id, order_date
FROM multi_filter_orders
WHERE customer_id IN (10, 13)
  AND order_date IN (DATE '2026-04-01', DATE '2026-04-03')
ORDER BY order_id;
~~~

Truy vấn này trả về **1001, 1002, 1005, 1006**. Đơn **1005** lọt vào vì customer_id = 10 và order_date = 03/04, mặc dù **cặp (10, 03/04)** không nằm trong danh sách cần lấy.

| Cách viết | Điều được phép |
| --- | --- |
| **(a, b) IN ((x1, y1), (x2, y2))** | Chỉ hai cặp **(x1, y1)** và **(x2, y2)** |
| **a IN (x1, x2) AND b IN (y1, y2)** | Có thể cho phép cả bốn tổ hợp **(x1,y1), (x1,y2), (x2,y1), (x2,y2)** |

Khi danh sách nhiều cột biểu diễn **quan hệ ghép cặp**, hai IN độc lập thường sai ý nghĩa.

### IN với truy vấn con

Danh sách cặp không nhất thiết phải viết cố định trong câu SQL. Có thể lấy từ một bảng hoặc truy vấn con:

~~~sql
WITH allowed_pairs(customer_id, order_date) AS (
    VALUES
        (10, DATE '2026-04-01'),
        (13, DATE '2026-04-03')
)
SELECT o.order_id, o.customer_id, o.order_date
FROM multi_filter_orders AS o
WHERE (o.customer_id, o.order_date) IN (
    SELECT p.customer_id, p.order_date
    FROM allowed_pairs AS p
)
ORDER BY o.order_id;
~~~

Đây là cách tiện để lọc theo những **khóa ghép** hoặc **cặp điều kiện** lưu ở một nguồn khác, miễn là kiểu và thứ tự cột của hai phía tương thích.

## 8. NOT IN với nhiều cột và bẫy NULL

**NOT IN** là phủ định của điều kiện thành viên. Nhưng nếu so sánh với một cặp có NULL, kết quả có thể là UNKNOWN, và hàng sẽ bị loại trong WHERE.

~~~sql
SELECT
    ROW(10, 'Ha Noi') NOT IN (
        ROW(10, NULL::TEXT)
    ) AS not_in_unknown,
    ROW(11, 'Da Nang') NOT IN (
        ROW(10, NULL::TEXT)
    ) AS not_in_decided;
~~~

Trong PostgreSQL, biểu thức thứ nhất là **UNKNOWN**, vì thành phần customer_id bằng nhau nhưng không thể biết 'Ha Noi' có bằng NULL hay không. Biểu thức thứ hai là **TRUE**, vì **11 khác 10**, đủ kết luận không trùng hàng bên phải.

Điều này có nghĩa **một NULL trong một tuple không nhất thiết làm mọi kết quả NOT IN trở thành UNKNOWN**; kết quả phụ thuộc từng cặp hàng. Tuy nhiên, nó làm NOT IN khó dự đoán hơn khi dữ liệu có thể thiếu.

Nếu muốn kiểm tra **không tồn tại cặp nào khớp** trong tập dữ liệu khác, **NOT EXISTS** thường diễn đạt ý định rõ ràng:

~~~sql
WITH blocked_pairs(customer_id, shipping_city) AS (
    VALUES
        (10, 'Ha Noi'::TEXT),
        (14, NULL::TEXT)
)
SELECT o.order_id, o.customer_id, o.shipping_city
FROM multi_filter_orders AS o
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_pairs AS b
    WHERE o.customer_id = b.customer_id
      AND o.shipping_city = b.shipping_city
)
ORDER BY o.order_id;
~~~

Lưu ý: so sánh bằng thông thường **không coi NULL = NULL là TRUE**. Do đó, truy vấn trên **không loại** đơn 1008 với cặp (14, NULL), dù danh sách có (14, NULL). Nếu nghiệp vụ muốn hai NULL được xem là tương ứng, thay điều kiện trong NOT EXISTS bằng:

~~~sql
WHERE o.customer_id IS NOT DISTINCT FROM b.customer_id
  AND o.shipping_city IS NOT DISTINCT FROM b.shipping_city
~~~

Lúc đó các đơn có cặp **(10, 'Ha Noi')** và **(14, NULL)** đều bị loại.

**Bài học:** phải thống nhất **NULL có được xem là một phần giá trị khóa ghép hay không**, rồi chọn **=**, **IS NOT DISTINCT FROM** hoặc điều kiện IS NULL rõ ràng.

## 9. So sánh hàng với <, <=, >, >= trong điều kiện lọc

Giả sử các đơn được sắp theo:

~~~sql
ORDER BY order_date ASC, order_id ASC
~~~

Yêu cầu là lấy những đơn **nằm sau** cặp **(ngày 03/04/2026, mã 1006)** trong thứ tự này.

### 9.1. Viết bằng AND/OR

~~~sql
SELECT order_id, order_date
FROM multi_filter_orders
WHERE order_date > DATE '2026-04-03'
   OR (
       order_date = DATE '2026-04-03'
       AND order_id > 1006
   )
ORDER BY order_date, order_id;
~~~

Điều kiện có hai trường hợp: ngày muộn hơn, hoặc cùng ngày nhưng mã lớn hơn.

### 9.2. Viết bằng row comparison

~~~sql
SELECT order_id, order_date
FROM multi_filter_orders
WHERE (order_date, order_id) >
      (DATE '2026-04-03', 1006)
ORDER BY order_date, order_id;
~~~

Cả hai truy vấn trả về các mã **1007, 1008, 1009, 1010, 1011, 1012**. So sánh theo thứ tự từ trái sang phải trùng với thứ tự **ORDER BY order_date ASC, order_id ASC**.

Không nên viết:

~~~sql
-- Sai ý nghĩa: bắt buộc cả hai cột cùng lớn hơn.
WHERE order_date > DATE '2026-04-03'
  AND order_id > 1006
~~~

Điều kiện AND này **mạnh hơn cần thiết**. Trong dữ liệu khác, một đơn có ngày muộn hơn nhưng order_id nhỏ hơn sẽ bị loại dù vẫn phải nằm sau trong thứ tự theo ngày.

Tương tự, điều kiện:

~~~sql
-- Sai ý nghĩa: hai điều kiện độc lập có thể bao gồm hàng trước vị trí.
WHERE order_date > DATE '2026-04-03'
   OR order_id > 1006
~~~

**rộng hơn cần thiết**: nó có thể chọn cả đơn có ngày trước nhưng mã đơn lớn hơn, vì quên giới hạn **cùng ngày** ở vế thứ hai.

### 9.3. Khoảng giá trị theo hàng

PostgreSQL có thể diễn đạt một khoảng theo thứ tự hàng bằng **>=** và **<=**:

~~~sql
SELECT order_id, order_date
FROM multi_filter_orders
WHERE (order_date, order_id) >=
      (DATE '2026-04-02', 1003)
  AND (order_date, order_id) <=
      (DATE '2026-04-04', 1009)
ORDER BY order_date, order_id;
~~~

Điều này chọn một **đoạn liên tục theo thứ tự của cặp giá trị**, gồm cả hai đầu: **1003 đến 1009** trong dữ liệu mẫu.

Trong hệ và phiên bản cho phép, có thể viết điều kiện khoảng bằng **BETWEEN** trên row value:

~~~sql
WHERE (order_date, order_id) BETWEEN
      (DATE '2026-04-02', 1003)
  AND (DATE '2026-04-04', 1009)
~~~

Đây **không phải** yêu cầu từng cột tự nằm trong hai khoảng độc lập; nó vẫn là **khoảng từ điển** theo cặp giá trị. Khi cần tính di động cao, cách viết >= và <= bằng hai row comparison, hoặc triển khai bằng AND/OR, dễ đối chiếu khả năng hỗ trợ hơn.

## 10. Phân trang theo khóa bằng cặp (ngày, mã đơn)

Khi kết quả có nhiều trang, ứng dụng thường dùng **OFFSET/LIMIT** hoặc **keyset pagination**. Keyset pagination dựa vào vị trí cuối cùng đã lấy, được xác định bằng một hoặc nhiều cột sắp xếp.

### 10.1. Vì sao chỉ dùng ngày có thể bỏ sót dữ liệu?

Nhiều đơn có cùng **order_date**. Nếu trang trước kết thúc ở:

~~~text
order_date = 2026-04-03
order_id   = 1006
~~~

mà trang tiếp theo dùng:

~~~sql
WHERE order_date > DATE '2026-04-03'
~~~

thì đơn **1007**, vẫn thuộc ngày 03/04 nhưng đứng sau 1006, sẽ **bị bỏ sót**.

### 10.2. Đặt thứ tự ổn định rồi dùng row comparison

~~~sql
-- Trang kế tiếp sau cặp (2026-04-03, 1006).
SELECT order_id, order_date, customer_id, total_vnd
FROM multi_filter_orders
WHERE (order_date, order_id) >
      (DATE '2026-04-03', 1006)
ORDER BY order_date ASC, order_id ASC
LIMIT 4;
~~~

Kết quả là **1007, 1008, 1009, 1010**. Cặp **(order_date, order_id)** xác định được thứ tự vì order_id là duy nhất; khi có nhiều đơn cùng ngày, cột thứ hai phá hòa.

Lần kế tiếp, sử dụng **(ngày 05/04/2026, mã 1010)** làm vị trí cuối:

~~~sql
SELECT order_id, order_date
FROM multi_filter_orders
WHERE (order_date, order_id) >
      (DATE '2026-04-05', 1010)
ORDER BY order_date ASC, order_id ASC
LIMIT 4;
~~~

Lúc này kết quả là **1011, 1012**.

### 10.3. Nếu thứ tự giảm dần

Khi ORDER BY dùng cả hai cột **DESC**:

~~~sql
ORDER BY order_date DESC, order_id DESC
~~~

trang tiếp theo theo chiều giảm dần sẽ dùng **<** so với cặp cuối:

~~~sql
WHERE (order_date, order_id) <
      (DATE '2026-04-03', 1006)
~~~

Điều kiện này tương ứng với việc đi **xuống dưới** trong danh sách giảm dần.

### 10.4. Khi ORDER BY trộn ASC và DESC

Với:

~~~sql
ORDER BY order_date DESC, order_id ASC
~~~

không thể đơn giản thay bằng một dấu **<** hoặc **>** trên cặp (order_date, order_id), vì hai cột được xếp theo **hai chiều ngược nhau**.

Nếu vị trí cuối là (2026-04-03, 1006), điều kiện trang tiếp theo phải là:

~~~sql
WHERE order_date < DATE '2026-04-03'
   OR (
       order_date = DATE '2026-04-03'
       AND order_id > 1006
   )
~~~

Cột ngày giảm dần nên **ngày nhỏ hơn** đi sau; trong cùng ngày, mã đơn tăng dần nên **mã lớn hơn** đi sau.

### 10.5. Khi cột sắp xếp có thể NULL

Phép so sánh hàng với NULL có thể cho UNKNOWN. Trong khi đó, **ORDER BY** có thể đặt NULL trước hoặc sau theo quy tắc riêng của hệ quản trị (PostgreSQL có **NULLS FIRST/NULLS LAST**).

Nếu dùng cột nullable làm một phần khóa phân trang, phải định nghĩa **vị trí của NULL trong thứ tự**, rồi viết bộ lọc khớp với quy tắc đó; phép so sánh hàng thông thường không tự bao phủ mọi vị trí chứa NULL.

Keyset pagination còn phụ thuộc việc dữ liệu có bị chèn, xóa hay cập nhật giữa các lần lấy trang. Nó giúp tránh lỗi và chi phí phổ biến của OFFSET lớn, nhưng không tự tạo ra **snapshot bất biến** giữa nhiều truy vấn. Nếu ứng dụng yêu cầu một tập kết quả cố định, cần giải pháp giao dịch/snapshot tương ứng.

## 11. Kết hợp row comparison với JOIN nhiều cột

Không chỉ WHERE, một điều kiện JOIN cũng có thể cần **nhiều cột để xác định sự khớp**. Giả sử bảng cấu hình có cặp **(shipping_city, sales_channel)**.

~~~sql
WITH channel_rules(shipping_city, sales_channel, service_level) AS (
    VALUES
        ('Ha Noi'::TEXT, 'web'::TEXT, 'priority'::TEXT),
        ('HCM'::TEXT, 'app'::TEXT, 'standard'::TEXT),
        ('Da Nang'::TEXT, 'web'::TEXT, 'economy'::TEXT)
)
SELECT
    o.order_id,
    o.shipping_city,
    o.sales_channel,
    r.service_level
FROM multi_filter_orders AS o
JOIN channel_rules AS r
    ON o.shipping_city = r.shipping_city
   AND o.sales_channel = r.sales_channel
ORDER BY o.order_id;
~~~

Ở đây điều kiện JOIN có **hai phép bằng kết hợp AND**. PostgreSQL có thể viết gọn thành:

~~~sql
ON (o.shipping_city, o.sales_channel) =
   (r.shipping_city, r.sales_channel)
~~~

Với các cột khác NULL, hai cách thể hiện cùng quy tắc ghép. **Nếu chỉ JOIN theo shipping_city**, một thành phố có nhiều kênh sẽ có thể ghép nhầm cấu hình của kênh khác, làm phát sinh hàng sai hoặc nhân bản.

Nếu một trong các cột khóa ghép có NULL, toán tử bằng thông thường không coi NULL = NULL là TRUE. Với yêu cầu “hai giá trị NULL được xem là cùng một khóa” trên PostgreSQL, có thể cân nhắc **IS NOT DISTINCT FROM** cho từng cột:

~~~sql
ON o.shipping_city IS NOT DISTINCT FROM r.shipping_city
AND o.sales_channel IS NOT DISTINCT FROM r.sales_channel
~~~

Việc coi hai NULL là tương ứng phải được quy định trước; không nên thực hiện chỉ để làm tăng số hàng JOIN.

## 12. Chỉ mục ghép và hiệu năng điều kiện nhiều cột

Khi thường xuyên lọc hoặc sắp theo **(order_date, order_id)**, một chỉ mục B-tree ghép có thể hỗ trợ:

~~~sql
CREATE INDEX idx_multi_filter_orders_date_id
    ON multi_filter_orders (order_date, order_id);
~~~

Truy vấn:

~~~sql
SELECT order_id, order_date
FROM multi_filter_orders
WHERE (order_date, order_id) >
      (DATE '2026-04-03', 1006)
ORDER BY order_date, order_id
LIMIT 4;
~~~

phù hợp với **thứ tự khóa** trong chỉ mục. Trên bảng lớn, hệ quản trị có thể sử dụng chỉ mục để lọc khoảng và đọc theo thứ tự; với bảng chỉ 12 hàng, quét bảng đơn giản có thể rẻ hơn.

### 12.1. Thứ tự cột trong index rất quan trọng

Chỉ mục:

~~~sql
CREATE INDEX idx_multi_filter_orders_customer_date
    ON multi_filter_orders (customer_id, order_date);
~~~

khác với:

~~~sql
CREATE INDEX idx_multi_filter_orders_date_customer
    ON multi_filter_orders (order_date, customer_id);
~~~

Trường hợp tra cứu thường xuyên theo **customer_id rồi theo khoảng ngày** có thể hưởng lợi từ chỉ mục bắt đầu bằng customer_id. Nếu chủ yếu lọc theo khoảng ngày cho mọi khách, chỉ mục bắt đầu bằng order_date có thể hợp lý hơn. Đây là nguyên tắc thường gọi là **cột đứng đầu của chỉ mục ghép**.

Không được kết luận “viết row comparison thì lúc nào cũng nhanh hơn AND/OR”. Bộ tối ưu của từng hệ khác nhau; hiệu quả phụ thuộc **loại chỉ mục, tính chọn lọc, thống kê, phép toán, kiểu dữ liệu và cách viết truy vấn**.

### 12.2. Tránh biến đổi cột một cách không cần thiết

Nếu chỉ mục lưu trực tiếp order_date, điều kiện:

~~~sql
WHERE order_date >= DATE '2026-04-03'
~~~

thường dễ tối ưu bằng chỉ mục hơn một điều kiện tính toán phức tạp trên cột:

~~~sql
WHERE TO_CHAR(order_date, 'YYYY-MM-DD') >= '2026-04-03'
~~~

Điều kiện thứ hai chuyển DATE sang chuỗi và có thể ngăn hệ quản trị dùng hiệu quả chỉ mục thường trên order_date. Khi có nhu cầu biến đổi cố định, có thể xem xét **expression index** trong hệ hỗ trợ, nhưng ưu tiên so sánh với **kiểu dữ liệu gốc** khi phù hợp.

Với các truy vấn quan trọng, dùng **EXPLAIN** hoặc công cụ kế hoạch thực thi của hệ quản trị để quan sát lựa chọn chỉ mục. Bản thân cú pháp đúng không chứng minh một cách viết nhanh hơn cách khác.

## 13. Khác biệt giữa các phương ngữ SQL

Khái niệm “điều kiện trên nhiều cột” được hỗ trợ rộng rãi bằng AND/OR. Tuy nhiên, khả năng viết **(a, b) = (x, y)** hoặc **(a, b) > (x, y)** phụ thuộc hệ quản trị.

| Hệ quản trị | Bằng và thứ tự giữa row values | IN với nhiều cột | Ghi chú sử dụng |
| --- | --- | --- | --- |
| **PostgreSQL 15+** | Có, với toán tử và kiểu phù hợp | Có, kể cả danh sách tuple và truy vấn con | Hỗ trợ ROW(...), IS [NOT] DISTINCT FROM; row comparison B-tree |
| **MySQL 8.0** | Có, với row constructors và toán tử phù hợp | Có | Có giới hạn biểu thức và khác biệt tối ưu chỉ mục; xem kế hoạch thực thi |
| **SQLite 3.15+** | Có row values với phép so sánh hỗ trợ | Có, nhưng phía phải của row-value IN là một truy vấn con | Có thể dùng SELECT từ VALUES/CTE để diễn đạt danh sách cặp |
| **SQL Server** | Không hỗ trợ cú pháp so sánh tuple tổng quát trong WHERE như PostgreSQL | Không hỗ trợ dạng tuple IN tương ứng | Dùng AND/OR, JOIN hoặc EXISTS trên các cột riêng |

Các hệ có thể dùng quy tắc **collation**, chuyển kiểu ngầm và xử lý NULL khác nhau ở một số trường hợp. Khi chuyển mã giữa các hệ, cần xác minh **phiên bản thực tế**, không chỉ tên sản phẩm.

### 13.1. PostgreSQL: cú pháp tuple trực tiếp

~~~sql
SELECT order_id
FROM multi_filter_orders
WHERE (customer_id, order_date) IN (
    (10, DATE '2026-04-01'),
    (13, DATE '2026-04-03')
)
ORDER BY order_id;
~~~

Với toán tử thứ tự:

~~~sql
SELECT order_id, order_date
FROM multi_filter_orders
WHERE (order_date, order_id) >
      (DATE '2026-04-03', 1006)
ORDER BY order_date, order_id;
~~~

Đây là các ví dụ chính đã dùng xuyên suốt bài. PostgreSQL còn hỗ trợ **ROW(...)** khi muốn viết tường minh một row constructor.

### 13.2. MySQL 8.0: row constructor và chú ý tối ưu

Ví dụ dưới đây dành cho bảng tương đương trên MySQL (không phải chạy trên bảng tạm PostgreSQL):

~~~sql
SELECT order_id, customer_id, order_date
FROM orders
WHERE (customer_id, order_date) IN (
    (10, '2026-04-01'),
    (13, '2026-04-03')
)
ORDER BY order_id;
~~~

So sánh theo thứ tự cũng có thể dùng row constructor:

~~~sql
SELECT order_id, order_date
FROM orders
WHERE (order_date, order_id) > ('2026-04-03', 1006)
ORDER BY order_date, order_id
LIMIT 4;
~~~

MySQL hỗ trợ cú pháp row comparisons, nhưng cách bộ tối ưu tận dụng **chỉ mục ghép** có thể khác so với điều kiện mở rộng thành OR/AND. Với một truy vấn thực tế chạy chậm, hãy xem **EXPLAIN** và thử cách diễn đạt tương đương trước khi quyết định dùng cú pháp nào.

### 13.3. SQLite 3.15+: so sánh row values, IN dùng truy vấn con

SQLite hỗ trợ so sánh row values từ phiên bản **3.15.0**. Tuy nhiên, dạng **row-value IN** yêu cầu phía phải là **subquery**. Có thể dùng CTE kết hợp VALUES:

~~~sql
WITH allowed(customer_id, order_date) AS (
    VALUES
        (10, '2026-04-01'),
        (13, '2026-04-03')
)
SELECT order_id
FROM orders
WHERE (customer_id, order_date) IN (
    SELECT customer_id, order_date
    FROM allowed
)
ORDER BY order_id;
~~~

Trong ví dụ SQLite, giả định order_date được lưu theo định dạng ngày ISO nhất quán. SQLite không có kiểu DATE lưu trữ giống PostgreSQL; nếu dùng số nguyên hoặc dạng thời gian khác, cần thống nhất cách lưu và so sánh.

Một ví dụ so sánh thứ tự tương tự:

~~~sql
SELECT order_id, order_date
FROM orders
WHERE (order_date, order_id) > ('2026-04-03', 1006)
ORDER BY order_date, order_id
LIMIT 4;
~~~

Điều kiện ngày theo chuỗi ở đây dựa trên việc **các giá trị đều theo ISO YYYY-MM-DD**. Nếu trộn '03/04/2026' với '2026-04-03', thứ tự từ vựng của chuỗi có thể không trùng thứ tự ngày tháng.

### 13.4. SQL Server: dùng AND/OR hoặc EXISTS

SQL Server không hỗ trợ trực tiếp cú pháp:

~~~sql
-- Cú pháp minh họa KHÔNG hợp lệ trong SQL Server:
WHERE (order_date, order_id) > ('2026-04-03', 1006)
~~~

Thay bằng phép logic tường minh:

~~~sql
SELECT TOP (4) order_id, order_date
FROM dbo.orders
WHERE order_date > CONVERT(date, '2026-04-03')
   OR (
       order_date = CONVERT(date, '2026-04-03')
       AND order_id > 1006
   )
ORDER BY order_date ASC, order_id ASC;
~~~

Để kiểm tra danh sách cặp:

~~~sql
SELECT o.order_id, o.customer_id, o.order_date
FROM dbo.orders AS o
WHERE EXISTS (
    SELECT 1
    FROM (
        VALUES
            (10, CONVERT(date, '2026-04-01')),
            (13, CONVERT(date, '2026-04-03'))
    ) AS p(customer_id, order_date)
    WHERE p.customer_id = o.customer_id
      AND p.order_date = o.order_date
)
ORDER BY o.order_id;
~~~

**VALUES** tạo bảng giá trị tạm trong FROM; **EXISTS** kiểm tra có cặp nào khớp toàn bộ khóa. Đây là cách diễn đạt dễ hiểu, đồng thời bảo toàn việc ghép đúng **customer_id với order_date**.

### 13.5. Dạng SQL dễ di chuyển hơn

Nếu ứng dụng phải chạy trên nhiều phương ngữ, bộ lọc bằng nhau có thể viết:

~~~sql
WHERE a = x AND b = y
~~~

Danh sách các cặp có thể viết:

~~~sql
WHERE (a = x1 AND b = y1)
   OR (a = x2 AND b = y2)
~~~

So sánh thứ tự tăng dần có thể viết:

~~~sql
WHERE a > x OR (a = x AND b > y)
~~~

Đó là những biểu thức logic phổ biến, nhưng vẫn cần kiểm tra **NULL**, **kiểu dữ liệu**, **collation**, và **hàm/ngày tháng** theo hệ dùng. Khi danh sách cặp dài, nên dùng bảng tạm, bảng tham chiếu hoặc **EXISTS/JOIN** thay vì nối quá nhiều điều kiện OR trong chuỗi SQL.

## 14. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Dùng hai **IN** độc lập để chọn những cặp tương ứng | Vô tình chấp nhận tổ hợp chéo | Dùng tuple IN hoặc OR giữa từng cặp AND |
| Hiểu **(a,b) > (x,y)** là **a>x AND b>y** | Row comparison xét từ trái sang phải | Dùng **a>x OR (a=x AND b>y)** |
| JOIN chỉ theo một cột của khóa ghép | Ghép sai hàng hoặc tăng số dòng | JOIN đầy đủ các cột khóa liên quan |
| Dùng **= NULL** để tìm cột trống | Phép so sánh cho UNKNOWN | Dùng **IS NULL** |
| Dùng **NOT IN** trên các cặp có NULL mà không xác định quy tắc | Có thể tạo UNKNOWN, mất hàng ngoài dự kiến | Xem xét NOT EXISTS và so sánh NULL đúng nghiệp vụ |
| Dùng row comparison để phân trang nhưng ORDER BY khác thứ tự cột | Bộ lọc không khớp thứ tự hiển thị | Sắp cùng cột và cùng chiều hoặc mở rộng điều kiện tường minh |
| Dùng dấu **>** cho ORDER BY trộn ASC/DESC | Chiều so sánh khác nhau theo từng cột | Viết OR/AND theo từng cột |
| Sắp theo cột không duy nhất khi phân trang | Các hàng trùng khóa sắp xếp có thể bị bỏ sót | Thêm cột định danh duy nhất làm khóa phá hòa |
| Coi **NULLS FIRST/LAST** được xử lý tự động trong row comparison | So sánh với NULL có thể UNKNOWN | Thiết kế riêng bộ lọc cho NULL |
| Sao chép cú pháp tuple PostgreSQL sang SQL Server | Không hỗ trợ cú pháp đó | Dùng AND/OR hoặc EXISTS |
| Giả định tuple predicate luôn dùng index tối ưu nhất | Tối ưu tùy hệ, phiên bản và dữ liệu | Xem EXPLAIN và thiết kế chỉ mục theo điều kiện thực |
| So sánh ngày lưu ở định dạng chuỗi lẫn lộn | Thứ tự chuỗi không phản ánh đúng thứ tự thời gian | Dùng kiểu DATE hoặc định dạng ISO thống nhất |

## 15. Bài tập thực hành

Dùng bảng **multi_filter_orders** trong PostgreSQL ở phần 2, tự viết và giải thích kết quả:

1. Lấy tất cả đơn **đã thanh toán** và có **total_vnd >= 500000**, sắp theo total_vnd giảm dần.
2. Lấy đơn có shipping_city **Ha Noi hoặc HCM**, đồng thời status = 'paid'. Thử bỏ ngoặc quanh OR và quan sát khác biệt.
3. Dùng **(customer_id, order_date) = (...)** để lấy các đơn của khách 10 trong ngày 01/04/2026. Viết lại bằng hai điều kiện AND.
4. Dùng tuple IN lấy đúng hai cặp **(10, 01/04/2026)** và **(13, 03/04/2026)**. Kết quả có những order_id nào?
5. Thay tuple IN ở bài 4 bằng hai IN độc lập. Vì sao đơn **1005** xuất hiện thêm?
6. Dự đoán kết quả **(2,1)>(1,9999)** và **(2,1)>(2,9)**, sau đó chạy SELECT kiểm tra.
7. Viết điều kiện lọc các đơn đứng **sau (03/04/2026, 1006)** theo thứ tự **order_date ASC, order_id ASC** bằng hai cách: row comparison và AND/OR.
8. Dùng LIMIT 4 để lấy trang sau cặp **(03/04/2026,1006)**. Tiếp tục bằng cặp cuối trang và giải thích vì sao không bỏ sót 1007.
9. Viết điều kiện trang tiếp theo cho thứ tự **order_date DESC, order_id ASC** và giải thích vì sao không thể dùng trực tiếp một dấu > hoặc < trên cặp.
10. Tìm những đơn có **shipping_city chưa có dữ liệu**, status = 'paid'. So sánh kết quả giữa IS NULL + AND và IS NOT DISTINCT FROM trên tuple.
11. Tạo một CTE chứa các cặp **(shipping_city, sales_channel)** được phép; dùng EXISTS hoặc JOIN để lọc các đơn khớp đủ hai cột.
12. Thử so sánh **ROW(1,NULL) = ROW(1,NULL)**, **ROW(1,NULL) = ROW(2,NULL)** và **ROW(1,NULL) < ROW(2,0)**. Giải thích kết quả TRUE/FALSE/UNKNOWN.
13. Viết truy vấn chọn các đơn **không nằm trong danh sách cặp** có một giá trị NULL. Dùng NOT EXISTS và xác định rõ NULL có được coi là khớp NULL hay không.
14. Tạo chỉ mục ghép **(order_date, order_id)**, viết truy vấn keyset phù hợp. Giải thích vì sao chỉ mục này có thể hữu ích trên bảng nhiều hàng nhưng chưa chắc được dùng trên bảng tạm nhỏ.
15. Chuyển một truy vấn tuple IN và một truy vấn tuple > từ PostgreSQL sang **SQL Server** bằng EXISTS và AND/OR.
16. Với SQLite 3.15+, viết cặp giá trị cho **IN** thông qua subquery lấy từ CTE **VALUES**.

### Câu hỏi tự kiểm tra

**Câu 1:** Hai biểu thức sau có tương đương không?

~~~sql
(a, b) > (x, y)
a > x AND b > y
~~~

**Đáp án:** **Không.** Biểu thức thứ nhất so sánh từ trái sang phải. Với giá trị không NULL, biểu thức tương đương là **a > x OR (a = x AND b > y)**.

**Câu 2:** Nếu cần đúng hai cặp (10, ngày A) và (13, ngày B), có thể dùng customer_id IN (10,13) AND order_date IN (A,B) không?

**Đáp án:** **Không**, vì có thể lấy thêm (10, ngày B) và (13, ngày A). Cần chọn **cặp đầy đủ**.

**Câu 3:** Với **ROW(1,NULL) = ROW(2,NULL)**, kết quả có phải UNKNOWN không?

**Đáp án:** **Không.** Hai thành phần đầu chắc chắn khác nhau nên kết quả bằng của hai hàng là **FALSE**.

**Câu 4:** Tại sao phân trang bằng order_date > ngày cuối có thể làm mất đơn?

**Đáp án:** Nhiều đơn có thể cùng ngày; các đơn có ngày bằng ngày cuối nhưng mã đơn lớn hơn cần nằm ở trang tiếp theo. Dùng thêm **order_id** làm cột phá hòa.

**Câu 5:** Cú pháp **WHERE (a,b) = (x,y)** có thể dùng nguyên văn trên SQL Server không?

**Đáp án:** **Không** trong so sánh tuple tổng quát của SQL Server. Dùng **a=x AND b=y** hoặc EXISTS/JOIN trên các cột tương ứng.

**Câu 6:** Một cặp có NULL trong NOT IN sẽ luôn loại mọi hàng chứ?

**Đáp án:** **Không phải mọi hàng**, nhưng có thể làm điều kiện thành UNKNOWN khi các phần không NULL chưa đủ kết luận khác nhau. Cần xem ngữ nghĩa NULL của từng phép so sánh.

## 16. Ghi nhớ cốt lõi

**Điều kiện trên nhiều cột** có thể viết bằng **AND/OR** hoặc bằng **row comparison** khi phương ngữ hỗ trợ. So sánh bằng của hàng xét các thành phần tương ứng; **so sánh thứ tự xét từ trái sang phải**, tương tự cách sắp xếp theo nhiều cột. Với **IN**, tuple giữ đúng các **cặp giá trị liên quan** và tránh tổ hợp chéo mà hai IN độc lập có thể tạo ra.

**NULL** có thể làm kết quả bằng, khác hoặc thứ tự trở thành UNKNOWN. Với các cặp chứa NULL, cần xác định rõ chính sách so khớp và cân nhắc **IS [NOT] DISTINCT FROM** hoặc **EXISTS/NOT EXISTS**. Trong phân trang, bộ lọc bằng row comparison phải phù hợp chính xác với **thứ tự ORDER BY** và cần một cột phá hòa ổn định.

Cuối cùng, **PostgreSQL, MySQL, SQLite và SQL Server không có cùng cú pháp tuple**. Dù viết được biểu thức gọn trên một hệ, vẫn phải kiểm tra khả năng hỗ trợ, kiểu dữ liệu và kế hoạch thực thi trước khi dùng trên hệ khác.
