# Phân biệt lỗi cú pháp, lỗi kiểu, lỗi ràng buộc và lỗi logic

Một câu SQL có thể thất bại ngay khi được phân tích, bị từ chối khi kiểm tra kiểu dữ liệu, bị chặn lúc ghi vào bảng, hoặc **chạy thành công nhưng trả về kết quả sai với yêu cầu**. Bốn hiện tượng này cần được phân biệt vì cách sửa hoàn toàn khác nhau.

Ví dụ: truy vấn sai chính tả từ khóa cần sửa cấu trúc SQL; phép cộng giữa số tiền và tên khách hàng cần sửa kiểu/toán tử; việc thêm một khóa chính đã tồn tại cần xử lý dữ liệu và ràng buộc; còn việc đếm đơn hàng nhưng gọi là “số khách hàng” cần xem lại ý nghĩa nghiệp vụ của truy vấn.

Bài học thuộc phần **Cú pháp và ngữ nghĩa** của Database SQL. Mục tiêu là đọc một câu SQL, hiểu nó đang vi phạm quy tắc nào, xác định nơi tìm nguyên nhân và chọn cách khắc phục phù hợp.

## 1. Bản đồ bốn nhóm lỗi

| Nhóm | Bản chất | Khi nào thường được phát hiện? | Dấu hiệu điển hình | Hướng xử lý |
| --- | --- | --- | --- | --- |
| **Lỗi cú pháp** (*syntax error*) | Câu SQL không tuân theo ngữ pháp của hệ quản trị | Khi phân tích cú pháp câu lệnh | Sai từ khóa, thiếu dấu phẩy, ngoặc chưa đóng | Sửa cách viết câu SQL |
| **Lỗi kiểu** (*type error*) | Giá trị, biểu thức hoặc toán tử không tương thích kiểu; hoặc chuyển đổi giá trị sang kiểu đích không hợp lệ | Khi phân tích kiểu hoặc lúc đánh giá/chuyển đổi giá trị | Cộng số với văn bản, ép văn bản không phải số thành số nguyên | Dùng đúng kiểu, toán tử, giá trị và phép chuyển đổi |
| **Lỗi ràng buộc** (*constraint violation*) | Dữ liệu định ghi vi phạm quy tắc đã khai báo trong schema | Thường khi `INSERT`, `UPDATE`, `DELETE` hoặc xác nhận transaction | Trùng khóa, thiếu giá trị bắt buộc, khóa ngoại không tồn tại, vi phạm `CHECK` | Kiểm tra quy tắc và dữ liệu liên quan |
| **Lỗi logic** (*logical error*) | SQL hợp lệ, chạy được, nhưng không thực hiện đúng ý định | Không nhất thiết có thông báo lỗi; thường chỉ phát hiện khi so sánh kết quả với yêu cầu | Đếm sai đối tượng, lọc nhầm, nối bảng sai, cập nhật quá nhiều hàng | Sửa điều kiện và mô hình truy vấn; xác minh bằng dữ liệu kiểm thử |

Một cách hình dung đơn giản:

~~~text
Viết câu SQL
     |
     v
Phân tích cú pháp -------- sai ngữ pháp ----------> LỖI CÚ PHÁP
     |
     v
Phân giải tên, kiểu ------ kiểu/toán tử không hợp lệ -> LỖI KIỂU
     |
     v
Thực thi, đọc/ghi ------- vi phạm quy tắc schema --> LỖI RÀNG BUỘC
     |
     v
Kết quả hoặc thay đổi dữ liệu
     |
     v
So với yêu cầu ---------- khác điều mong đợi ------> LỖI LOGIC
~~~

Sơ đồ diễn tả **cách suy nghĩ**, không phải lời khẳng định rằng mọi hệ quản trị luôn phát hiện lỗi theo đúng thứ tự đó. Một số lỗi kiểu chỉ lộ ra khi chuyển đổi dữ liệu lúc thực thi; ràng buộc có thể được kiểm tra vào cuối transaction nếu cơ sở dữ liệu hỗ trợ cơ chế trì hoãn; và một lỗi logic đôi khi làm phát sinh lỗi ràng buộc ở bước sau.

**Lưu ý về phạm vi:** còn nhiều loại lỗi khác như bảng/cột không tồn tại, thiếu quyền, mất kết nối, deadlock, hết dung lượng, chia cho không hoặc lỗi tài nguyên. Không nên ép tất cả những lỗi này vào bốn nhóm đang học.

## 2. Chuẩn bị dữ liệu mẫu để đối chiếu

Các ví dụ chính dùng **PostgreSQL** để giải thích thông báo lỗi và mã SQLSTATE một cách nhất quán. Nhiều câu SQL bên dưới cũng gần với SQL chuẩn và dùng được trên hệ khác, nhưng cơ chế ép kiểu, ràng buộc và thông báo lỗi có thể khác giữa PostgreSQL, MySQL, SQL Server, SQLite.

Hãy sử dụng **database thực hành riêng**, với bảng chưa tồn tại, để chạy dữ liệu khởi tạo sau đúng một lần:

~~~sql
CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    full_name VARCHAR(80) NOT NULL,
    email VARCHAR(120) NOT NULL UNIQUE,
    age INTEGER NOT NULL CHECK (age >= 0)
);

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    amount NUMERIC(10, 2) NOT NULL CHECK (amount > 0)
);

INSERT INTO customers (customer_id, full_name, email, age)
VALUES
    (1, 'An',   'an@example.test',   22),
    (2, 'Binh', 'binh@example.test', 26),
    (3, 'Chi',  'chi@example.test',  19);

INSERT INTO orders (order_id, customer_id, amount)
VALUES
    (101, 1, 120.00),
    (102, 1,  80.00),
    (103, 2,  50.00);
~~~

Từ đây, bảng `customers` có **ba khách hàng**, còn `orders` có **ba đơn hàng**: An có hai đơn, Bình có một đơn và Chi chưa có đơn. Hai bảng nối với nhau qua `orders.customer_id = customers.customer_id`.

Chạy câu sau để xem quan hệ dữ liệu:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    o.order_id,
    o.amount
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
~~~

| customer_id | full_name | order_id | amount |
| ---: | --- | ---: | ---: |
| 1 | An | 101 | 120.00 |
| 1 | An | 102 | 80.00 |
| 2 | Binh | 103 | 50.00 |
| 3 | Chi | `NULL` | `NULL` |

Những câu lệnh được đánh dấu **sai** trong các mục tiếp theo là ví dụ để quan sát lỗi. Chỉ chạy từng câu một trong database thử nghiệm. Câu được kỳ vọng báo lỗi không phải là script nên ghép chung để chạy liên tục với phần khởi tạo.

## 3. Lỗi cú pháp: SQL không tạo thành câu lệnh hợp lệ

Hệ quản trị SQL hiểu ngôn ngữ dựa trên từ khóa, biểu thức, dấu phân cách và một số quy tắc cú pháp. Khi chuỗi ký tự không thể được phân tích thành một câu lệnh hợp lệ, bộ phân tích cú pháp sẽ từ chối.

### Ví dụ A — Sai từ khóa

~~~sql
-- SAI: SELECT bi viet thieu chu T.
SELEC customer_id, full_name
FROM customers;
~~~

Trong PostgreSQL, lỗi có thể có dạng `syntax error at or near "SELEC"`. Dấu hiệu chính là trình phân tích không nhận ra từ khóa mở đầu câu lệnh.

Sửa:

~~~sql
SELECT customer_id, full_name
FROM customers;
~~~

### Ví dụ B — Thiếu biểu thức sau WHERE

~~~sql
-- SAI: WHERE can mot dieu kien hop le.
SELECT customer_id
FROM customers
WHERE ;
~~~

Từ khóa `WHERE` phải đi cùng biểu thức điều kiện, chẳng hạn:

~~~sql
SELECT customer_id
FROM customers
WHERE age >= 20;
~~~

Một số lỗi cú pháp khác gồm thiếu dấu phẩy giữa các cột, dùng dấu ngoặc không cân bằng, đặt từ khóa sai vị trí và viết cú pháp chỉ được hệ quản trị khác hỗ trợ. Nếu dùng tham số, biến hoặc cú pháp của một công cụ chuyên biệt, hãy kiểm tra xem câu lệnh đang được gửi vào đúng client và đúng SQL dialect hay chưa.

**Cách chẩn đoán:** đọc vị trí mà thông báo lỗi chỉ ra, đồng thời nhìn một vài ký tự **trước** vị trí đó. Nơi hệ quản trị “vấp” thường nằm gần nguyên nhân, nhưng không nhất thiết trùng chính xác với ký tự bị viết sai. Tách câu lệnh dài thành đoạn nhỏ hơn có thể giúp nhìn thấy dấu phẩy, ngoặc hoặc từ khóa bị thiếu.

Đừng chỉ kiểm tra dấu `;`: trong công cụ chạy script, nó thường dùng để kết thúc câu lệnh, nhưng một câu đúng ngữ pháp vẫn có thể báo lỗi khi bảng chưa có hoặc khi dữ liệu không hợp lệ.

## 4. Lỗi kiểu: biểu thức hoặc giá trị không phù hợp kiểu dữ liệu

SQL có các kiểu như `INTEGER`, `NUMERIC`, `VARCHAR`, `DATE`, `BOOLEAN`. Hệ quản trị cần biết toán tử nào áp dụng được lên kiểu nào, và một giá trị có thể chuyển sang kiểu của cột đích hay không.

### Ví dụ A — Dùng toán tử không hỗ trợ hai kiểu

~~~sql
-- SAI tren PostgreSQL: cong so tien NUMERIC voi ten VARCHAR.
SELECT o.amount + c.full_name AS gia_tri
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id;
~~~

`o.amount` là số, `c.full_name` là văn bản. Với PostgreSQL, toán tử `+` không được định nghĩa cho cặp kiểu `numeric` và `character varying` này, nên có thể thấy thông báo kiểu `operator does not exist`.

Không nên “sửa” bằng cách ép tên khách hàng sang số: vấn đề nằm ở việc chọn **sai phép toán so với mục đích**. Nếu muốn xem hai thông tin cạnh nhau, viết:

~~~sql
SELECT o.amount, c.full_name
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id;
~~~

### Ví dụ B — Chuyển một giá trị văn bản không hợp lệ sang số

~~~sql
-- SAI: 'hai_muoi' khong phai cach bieu dien so nguyen hop le.
INSERT INTO customers (customer_id, full_name, email, age)
VALUES (4, 'Dung', 'dung@example.test', 'hai_muoi');
~~~

Vì `age` là `INTEGER`, PostgreSQL cố chuyển văn bản sang số nguyên nhưng không thể. Đây là lỗi chuyển đổi giá trị, thường được hiển thị như `invalid input syntax for type integer`.

Sửa giá trị nhập:

~~~sql
INSERT INTO customers (customer_id, full_name, email, age)
VALUES (4, 'Dung', 'dung@example.test', 20);
~~~

Chỉ chạy câu đúng nếu bạn muốn thêm dữ liệu thử nghiệm: nó **thực sự chèn một hàng**. Các ví dụ tiếp theo giả định bảng vẫn chỉ chứa ba khách hàng ban đầu; nếu bạn đã thêm hàng này, hãy chú ý các ID/email trùng và kết quả đếm có thể đổi.

### Ép kiểu tường minh có giải quyết mọi vấn đề?

Không. Phép ép kiểu là hợp lý khi dữ liệu đầu vào có biểu diễn hợp lệ:

~~~sql
SELECT CAST('25' AS INTEGER) AS tuoi;
~~~

Nhưng ép một chuỗi không có dạng số vẫn có thể thất bại:

~~~sql
-- SAI: gia tri khong chuyen duoc thanh INTEGER tren PostgreSQL.
SELECT CAST('hai_muoi' AS INTEGER);
~~~

Ngược lại, các hệ quản trị có mức độ **ép kiểu ngầm** khác nhau. Một hệ có thể tự chuyển chuỗi chứa chữ số, hệ khác từ chối; một số hệ thậm chí đưa ra cảnh báo hoặc giá trị bị chuyển đổi theo quy tắc riêng. Không dùng sự “dễ tính” của một hệ quản trị làm bảo đảm rằng câu SQL sẽ đúng ở nơi khác.

**Lỗi kiểu và lỗi ràng buộc khác nhau ở đâu?** Nếu chuỗi `'hai_muoi'` không thể thành `INTEGER` thì dữ liệu chưa đạt kiểu của cột. Nếu số `-5` đã là số nguyên hợp lệ nhưng vi phạm `CHECK (age >= 0)` thì vấn đề là **ràng buộc**, không phải kiểu.

Một số lỗi giá trị như tràn giới hạn số, chuỗi vượt độ dài hoặc ngày không hợp lệ thường được hệ quản trị xếp vào nhóm *data exception* với mã riêng; cần đọc thông báo cụ thể thay vì gọi mọi trường hợp là “không đúng kiểu”.

## 5. Lỗi ràng buộc: dữ liệu hợp kiểu nhưng vi phạm quy tắc bảng

Ràng buộc (*constraint*) là quy tắc mà database có trách nhiệm bảo vệ khi dữ liệu được ghi hay thay đổi. Một giá trị có thể hoàn toàn đúng kiểu mà vẫn bị từ chối.

Trong schema mẫu:

| Ràng buộc | Được khai báo ở đâu? | Ý nghĩa |
| --- | --- | --- |
| `PRIMARY KEY` | `customers.customer_id` và `orders.order_id` | Mỗi bản ghi có định danh không trùng và không `NULL` |
| `UNIQUE` | `customers.email` | Hai khách hàng không dùng cùng email |
| `NOT NULL` | `full_name`, `email`, `age`, `customer_id`, `amount` | Cột bắt buộc có giá trị khác `NULL` |
| `FOREIGN KEY` | `orders.customer_id` tham chiếu `customers.customer_id` | Mỗi đơn phải thuộc về một khách hàng đang tồn tại |
| `CHECK` | `age >= 0`; `amount > 0` | Giá trị phải thỏa điều kiện đã khai báo |

Các ví dụ dưới đây cố tình sai và được xem **độc lập** trên dữ liệu mẫu.

### Ví dụ A — Trùng khóa chính

~~~sql
-- SAI: customer_id = 1 da thuoc ve An.
INSERT INTO customers (customer_id, full_name, email, age)
VALUES (1, 'Nguoi khac', 'khac@example.test', 25);
~~~

Hệ quản trị từ chối vì khóa chính `customer_id` phải duy nhất. Việc thay tên hoặc email không giải quyết trùng ID; bạn cần chọn ID chưa dùng, hoặc xác định có phải mục tiêu thật sự là **cập nhật** khách hàng ID 1 thay vì thêm khách mới.

### Ví dụ B — Trùng giá trị UNIQUE

~~~sql
-- SAI: email cua An da ton tai.
INSERT INTO customers (customer_id, full_name, email, age)
VALUES (4, 'Dung', 'an@example.test', 20);
~~~

ID 4 chưa trùng nhưng email đã được sử dụng. Nếu yêu cầu nghiệp vụ cho phép hai người dùng chung email, phải xem lại thiết kế schema và yêu cầu, không tự ý bỏ `UNIQUE` chỉ để một câu chèn chạy qua.

### Ví dụ C — Thiếu giá trị NOT NULL

~~~sql
-- SAI: full_name khong cho phep NULL.
INSERT INTO customers (customer_id, full_name, email, age)
VALUES (4, NULL, 'dung@example.test', 20);
~~~

Chuỗi rỗng `''` và `NULL` là hai khái niệm khác nhau: `NOT NULL` ngăn `NULL`, nhưng không tự ngăn chuỗi rỗng. Nếu cần bắt buộc nhập tên có nội dung, có thể cần thêm kiểm tra ở ứng dụng hoặc ràng buộc phù hợp.

### Ví dụ D — Khóa ngoại không tồn tại

~~~sql
-- SAI: chua co customer_id = 999.
INSERT INTO orders (order_id, customer_id, amount)
VALUES (104, 999, 25.00);
~~~

`customer_id = 999` là số nguyên hợp lệ nhưng không chỉ tới khách hàng nào, nên vi phạm khóa ngoại. Cách khắc phục là dùng một khách hàng tồn tại hoặc tạo khách hàng hợp lệ trước, nếu đó đúng là yêu cầu.

### Ví dụ E — Vi phạm CHECK

~~~sql
-- SAI: amount phai lon hon 0.
INSERT INTO orders (order_id, customer_id, amount)
VALUES (104, 1, -10.00);
~~~

`-10.00` đúng kiểu `NUMERIC`, khách hàng ID 1 tồn tại, nhưng giá trị không thỏa `CHECK (amount > 0)`.

Tương tự, `age = -1` đúng kiểu `INTEGER` nhưng vi phạm `CHECK (age >= 0)`.

Một điểm ngữ nghĩa quan trọng: trong SQL, điều kiện `CHECK` thường chấp nhận kết quả **TRUE** hoặc **UNKNOWN**; vì thế `CHECK (age >= 0)` **một mình** không bảo đảm tuổi khác `NULL`. Schema mẫu thêm `age INTEGER NOT NULL` để bảo đảm cả hai điều kiện.

### Lỗi ràng buộc khi xóa/sửa dữ liệu

Ràng buộc không chỉ xuất hiện ở `INSERT`. Ví dụ:

~~~sql
-- SAI: xoa khach hang 1 khi orders van tham chieu toi ho.
DELETE FROM customers
WHERE customer_id = 1;
~~~

Trong schema PostgreSQL mẫu, khóa ngoại trên `orders` không khai báo `ON DELETE CASCADE`. Vì khách hàng 1 đang có đơn hàng, thao tác xóa sẽ bị chặn để bảo vệ tính toàn vẹn tham chiếu. Không nên tự đổi sang cascade nếu chưa hiểu liệu dữ liệu đơn hàng có cần được giữ lại hay không.

**Ghi nhớ:** thông báo lỗi ràng buộc thường cho biết loại ràng buộc và tên bảng/constraint liên quan. Muốn sửa đúng, cần hiểu lý do quy tắc tồn tại, không chỉ tìm cách làm câu SQL “chạy thành công”.

## 6. Lỗi logic: hệ quản trị chạy đúng câu SQL, nhưng câu SQL diễn tả sai ý định

Đây là nhóm dễ bỏ sót nhất vì nhiều trường hợp **không có ngoại lệ, không có dòng báo đỏ và không có SQLSTATE**. Database đã thực hiện chính xác điều bạn viết; vấn đề là điều bạn viết không khớp điều bạn muốn.

### Ví dụ A — Đếm đơn hàng nhưng tưởng là đếm khách hàng

Yêu cầu: “Có bao nhiêu **khách hàng đã từng có đơn hàng**?”

Truy vấn sai về ngữ nghĩa:

~~~sql
SELECT COUNT(*) AS so_khach_co_don
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id;
~~~

Kết quả là **3**, vì kết quả của `JOIN` có ba dòng: An xuất hiện hai lần, Bình một lần. `COUNT(*)` đếm **dòng sau khi JOIN**, không đếm khách hàng duy nhất. Câu lệnh hoàn toàn hợp lệ nhưng tên cột `so_khach_co_don` đang gán ý nghĩa sai cho con số.

Sửa đúng theo yêu cầu:

~~~sql
SELECT COUNT(DISTINCT c.customer_id) AS so_khach_co_don
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id;
~~~

Kết quả mong đợi là **2**: An và Bình. Nếu yêu cầu đổi thành “Có bao nhiêu **đơn hàng**?”, `COUNT(*)` ban đầu lại là hợp lý. Vì vậy, muốn kết luận lỗi logic, cần biết rõ câu hỏi nghiệp vụ.

### Ví dụ B — Đặt điều kiện WHERE làm mất dòng của LEFT JOIN

Yêu cầu: “Hiển thị **tất cả khách hàng**, kèm mã đơn có giá trị lớn hơn 100; khách không có đơn như vậy vẫn phải xuất hiện.”

Truy vấn nhìn có vẻ hợp lý nhưng làm mất khách hàng không thỏa điều kiện:

~~~sql
SELECT c.customer_id, c.full_name, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE o.amount > 100
ORDER BY c.customer_id;
~~~

Điều kiện `WHERE o.amount > 100` loại bỏ các dòng mà `o.amount` là `NULL` hoặc không lớn hơn 100. Với dữ liệu mẫu, chỉ còn An và đơn 101; Bình và Chi biến mất khỏi kết quả.

Muốn giữ **mọi khách hàng** và chỉ nối các đơn lớn hơn 100, đặt điều kiện thuộc bảng phải vào `ON`:

~~~sql
SELECT c.customer_id, c.full_name, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.amount > 100
ORDER BY c.customer_id;
~~~

Kết quả:

| customer_id | full_name | order_id |
| ---: | --- | ---: |
| 1 | An | 101 |
| 2 | Binh | `NULL` |
| 3 | Chi | `NULL` |

Quy tắc cần nhớ là điều kiện lọc **trước/trong phép nối** và điều kiện lọc **sau phép nối** không phải lúc nào cũng tương đương, nhất là với `LEFT JOIN`.

### Ví dụ C — Cập nhật đúng cú pháp nhưng sai phạm vi

Nếu yêu cầu là “Tăng tuổi khách hàng ID 1 thêm 1”, câu dưới đây là lỗi logic nguy hiểm:

~~~sql
-- SAI VOI YEU CAU: tang tuoi TAT CA khach hang.
UPDATE customers
SET age = age + 1;
~~~

Nó hợp cú pháp, hợp kiểu và không vi phạm `CHECK`, nhưng thiếu `WHERE` nên cập nhật toàn bộ bảng. Câu đúng theo yêu cầu là:

~~~sql
UPDATE customers
SET age = age + 1
WHERE customer_id = 1;
~~~

Trong ví dụ này, không cần chạy cả hai câu để “thử lỗi”. Hãy đọc điều kiện và dùng một câu `SELECT` cùng `WHERE` để xem những dòng nào sẽ bị tác động trước khi thay đổi dữ liệu.

### Ví dụ D — Sai ngữ nghĩa của NULL

`NULL` biểu diễn giá trị không biết/không có, không bằng một chuỗi rỗng, số 0 hay bất kỳ giá trị thông thường nào. Trong logic ba giá trị của SQL, phép so sánh `NULL = NULL` cho kết quả **UNKNOWN** (thường biểu diễn bằng `NULL`), không phải TRUE.

~~~sql
-- Khong dung de tim gia tri NULL.
SELECT customer_id
FROM customers
WHERE full_name = NULL;
~~~

Cách kiểm tra có `NULL` là:

~~~sql
SELECT customer_id
FROM customers
WHERE full_name IS NULL;
~~~

Ở schema mẫu, `full_name` bị ràng buộc `NOT NULL` nên câu đúng cũng trả về không dòng nào; điểm cần học là **toán tử kiểm tra**. Trên bảng có cột cho phép `NULL`, dùng `= NULL` có thể âm thầm bỏ sót những hàng cần tìm.

### Sai logic và thiếu ràng buộc có liên quan nhưng không giống nhau

Schema hiện chỉ quy định `age >= 0`. Thêm khách hàng có `age = 200` có thể vượt qua ràng buộc đó nếu các trường khác hợp lệ. Nếu nghiệp vụ yêu cầu tuổi không quá 120, cần bổ sung quy tắc ở đúng nơi được thiết kế để thực thi (ví dụ ràng buộc `CHECK` được phê duyệt hoặc kiểm tra đầu vào). **Không có lỗi ràng buộc** khi database chưa hề được yêu cầu bảo vệ quy tắc đó.

## 7. Đọc thông báo lỗi mà không nhầm loại

Trong PostgreSQL, mã **SQLSTATE** giúp nhận diện một số lỗi chính xác hơn nội dung thông báo tự nhiên. Các ví dụ tiêu biểu:

| SQLSTATE | Tên ý nghĩa thường gặp | Nhóm trong bài |
| --- | --- | --- |
| `42601` | Syntax error | Cú pháp |
| `42883` | Undefined function/operator (ví dụ không tồn tại toán tử cho hai kiểu) | Thường là vấn đề kiểu/toán tử |
| `42804` | Datatype mismatch | Kiểu |
| `22P02` | Invalid text representation (ví dụ ép `'abc'` thành số nguyên) | Chuyển đổi giá trị/kiểu |
| `23505` | Unique violation (bao gồm khóa chính trùng) | Ràng buộc |
| `23502` | Not-null violation | Ràng buộc |
| `23503` | Foreign-key violation | Ràng buộc |
| `23514` | Check violation | Ràng buộc |

Những mã trên chỉ mang tính minh họa cho PostgreSQL và chuẩn lớp SQLSTATE liên quan, **không phải bảng mã chung của mọi công cụ**. Lỗi logic thông thường không có mã vì bộ máy SQL không biết bạn định hỏi câu gì.

Khi xem lỗi, hãy thu thập cả: câu SQL đã gửi, dòng/vị trí mà công cụ báo, tên bảng/cột/ràng buộc, kiểu dữ liệu, giá trị tham gia và trạng thái transaction. Nếu thấy một lỗi trùng khóa sau khi đã thử sửa lỗi kiểu, có thể bạn đang chạy lại một câu `INSERT` đã thành công trước đó; hãy kiểm tra dữ liệu hiện có trước khi kết luận.

### Trường hợp không thuộc bốn nhóm một cách trực tiếp

~~~sql
-- Bang khong ton tai: loi giai quyet ten doi tuong.
SELECT * FROM customers_typo;
~~~

Lỗi không tìm thấy bảng/cột thuộc quá trình phân giải tên đối tượng; về mặt giáo trình có thể được nói đến như lỗi ngữ nghĩa SQL, nhưng không nhất thiết là lỗi cú pháp, kiểu, ràng buộc hoặc logic theo cách định nghĩa hẹp của bài này.

Tương tự, `permission denied` là vấn đề phân quyền; `connection refused` là vấn đề kết nối; lỗi deadlock là vấn đề đồng thời. Cách khắc phục khác với việc sửa dấu phẩy hay ép kiểu.

## 8. Quy trình chẩn đoán thực tế

Khi một câu SQL không hoạt động như mong đợi, có thể lần lượt làm như sau:

1. **Xác định kết quả mong muốn.** Phải biết cần xem hay đổi đối tượng nào, số hàng nào, và tác động mong đợi là gì. Đây là căn cứ để phát hiện lỗi logic.
2. **Đọc lỗi đầu tiên** từ database, không chỉ thông báo chung của ứng dụng. Lỗi cú pháp dẫn tới sửa câu; lỗi kiểu dẫn tới xem biểu thức và phép chuyển đổi; lỗi ràng buộc dẫn tới xem quy tắc bảng và dữ liệu tham chiếu.
3. **Kiểm tra schema và ngữ cảnh.** Xác nhận database/schema đang kết nối, cột và kiểu dữ liệu, khóa chính/khóa ngoại/`CHECK`. Đừng đoán kiểu chỉ từ tên cột.
4. **Thu nhỏ ví dụ.** Chạy riêng phần `SELECT`, biểu thức `CAST` hoặc điều kiện `WHERE` liên quan để thấy nguyên nhân; giữ nguyên dữ liệu có ích cho việc tái hiện.
5. **So sánh kết quả bằng dữ liệu kiểm thử.** Dùng trường hợp có một khách nhiều đơn, khách không có đơn, giá trị biên và `NULL`. Đối chiếu từng dòng/số đếm với kết quả dự kiến, đặc biệt khi SQL không báo lỗi.
6. **Kiểm tra số hàng bị tác động và transaction.** Với lệnh thay đổi dữ liệu, xem số hàng thay đổi; trước khi `COMMIT` cần chắc rằng điều kiện `WHERE` và các quy tắc nghiệp vụ đều đúng.

Trong PostgreSQL, có thể thử một thay đổi trên database thực hành rồi hoàn tác:

~~~sql
BEGIN;

UPDATE customers
SET age = age + 1
WHERE customer_id = 1;

SELECT customer_id, full_name, age
FROM customers
ORDER BY customer_id;

ROLLBACK;
~~~

`ROLLBACK` hoàn tác thay đổi chưa commit của transaction này. Trên PostgreSQL, nếu câu lệnh gặp lỗi trong transaction, transaction thường chuyển sang trạng thái lỗi và cần `ROLLBACK` trước khi chạy tiếp. Cơ chế DDL/transaction và autocommit có thể khác ở các hệ quản trị khác; không mặc định mọi lệnh trên mọi cơ sở dữ liệu đều hoàn tác được.

Không tắt khóa ngoại, bỏ `NOT NULL`, bỏ `CHECK` hay sửa dữ liệu hàng loạt chỉ để làm một câu SQL hết báo lỗi. Trước tiên hãy xác định điều kiện đúng theo nghiệp vụ.

## 9. Bài tập phân loại lỗi

Giả sử chỉ có dữ liệu ba khách hàng và ba đơn hàng ở mục 2. Hãy xác định nhóm lỗi chính trước khi xem lời giải.

**Tình huống 1**

~~~sql
SELET full_name FROM customers;
~~~

**Tình huống 2**

~~~sql
SELECT amount + full_name
FROM orders
JOIN customers
    ON customers.customer_id = orders.customer_id;
~~~

**Tình huống 3**

~~~sql
INSERT INTO orders (order_id, customer_id, amount)
VALUES (105, 999, 20.00);
~~~

**Tình huống 4**

Yêu cầu: “Đếm số khách hàng có đơn hàng”; người viết dùng:

~~~sql
SELECT COUNT(*) AS so_khach
FROM customers
JOIN orders
    ON orders.customer_id = customers.customer_id;
~~~

**Tình huống 5**

~~~sql
INSERT INTO customers (customer_id, full_name, email, age)
VALUES (5, 'Ha', 'ha@example.test', 'khong_ro');
~~~

**Tình huống 6**

Yêu cầu: “Hiển thị toàn bộ khách hàng kể cả người chưa mua hàng”; người viết dùng:

~~~sql
SELECT c.full_name, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
    ON c.customer_id = o.customer_id
WHERE o.order_id IS NOT NULL;
~~~

### Đáp án và giải thích

| Tình huống | Phân loại | Vì sao? |
| --- | --- | --- |
| 1 | **Cú pháp** | `SELET` không phải từ khóa `SELECT`. |
| 2 | **Kiểu** | Phép cộng `NUMERIC + VARCHAR` không hợp lệ trên PostgreSQL. |
| 3 | **Ràng buộc** | Đơn tham chiếu tới khách hàng 999 không tồn tại, vi phạm khóa ngoại. |
| 4 | **Logic** | `COUNT(*)` đếm 3 dòng sau `JOIN`; yêu cầu là 2 khách hàng phân biệt. |
| 5 | **Kiểu/chuyển đổi dữ liệu** | Văn bản `'khong_ro'` không thể đổi thành `INTEGER` của cột `age`. |
| 6 | **Logic** | `WHERE o.order_id IS NOT NULL` bỏ khách hàng không có đơn, trái với yêu cầu. |

Thử mở rộng bài tập bằng cách tự viết một câu `SELECT` đúng cho tình huống 4 và 6, sau đó đối chiếu với dữ liệu mẫu. Bài tập loại 1–3 và 5 chủ yếu được database chỉ ra bằng lỗi; loại 4 và 6 buộc người viết phải tự kiểm tra ý nghĩa kết quả.

## 10. Ghi nhớ khi viết và sửa SQL

- **Sai cú pháp:** bộ máy không thể phân tích câu SQL; sửa ngữ pháp và dấu phân cách.
- **Sai kiểu:** biểu thức hoặc giá trị không phù hợp với kiểu/toán tử; sửa phép toán, kiểu và cách chuyển đổi.
- **Sai ràng buộc:** dữ liệu vi phạm quy tắc mà schema đang bảo vệ; tìm lý do quy tắc tồn tại và sửa dữ liệu/thao tác cho đúng.
- **Sai logic:** SQL chạy được nhưng hiểu sai yêu cầu; kiểm tra số dòng, khóa nối, lọc, nhóm, `NULL` và kỳ vọng nghiệp vụ.

Hai câu hỏi luôn hữu ích là **“Database từ chối điều gì, nếu có?”** và **“Nếu database chấp nhận, kết quả có đúng điều mình yêu cầu không?”**. Trả lời cả hai giúp bạn không nhầm câu SQL hết báo lỗi với một câu SQL đã đúng.
