# Tham chiếu bảng qua tên schema và bí danh

Khi làm việc với SQL, cùng một tên bảng có thể xuất hiện trong nhiều **schema**. Chẳng hạn, bảng `customers` của dữ liệu bán hàng hiện tại có thể khác bảng `customers` trong khu vực lưu trữ. Cách viết `schema_name.table_name` giúp chỉ rõ bảng nào được dùng. Khi truy vấn dài hoặc kết hợp nhiều bảng, **bí danh bảng** (*table alias*) như `c` và `o` giúp tham chiếu các cột ngắn gọn, dễ đọc và không nhầm lẫn.

Hai cơ chế có vai trò khác nhau:

- **Tên schema** xác định **không gian tên của đối tượng bảng** trong database.
- **Bí danh** đặt một **tên tham chiếu tạm thời cho bảng trong câu truy vấn**, không đổi tên bảng trong database.

Bài học thuộc phần **Database SQL → Truy vấn cơ bản**, trình bày cách dùng tên schema và bí danh, cách chúng phối hợp trong `SELECT` và `JOIN`, và các lỗi thường gặp khi tên bảng/cột bị nhầm. Ví dụ thực hành dùng **PostgreSQL**; cuối bài có phần đối chiếu cú pháp giữa các hệ quản trị.

## 1. Database, schema và bảng có quan hệ gì?

Trong PostgreSQL, một kết nối làm việc với một **database** cụ thể. Bên trong database có thể có nhiều **schema**, và mỗi schema chứa các đối tượng như bảng, view, hàm hoặc sequence.

~~~text
Database: practice_db
|
|-- Schema: lesson109_sales
|    |-- customers
|    +-- orders
|
|-- Schema: lesson109_archive
|    +-- customers
|
|-- Schema: public
     +-- ... (cac doi tuong khac neu co)
~~~

Tên `customers` có thể xuất hiện đồng thời trong hai schema vì tên đầy đủ của hai bảng khác nhau:

~~~sql
lesson109_sales.customers
lesson109_archive.customers
~~~

Đây là cách ghi **tên đối tượng** theo dạng `schema.table`, chưa phải hai câu lệnh SQL hoàn chỉnh.

Trong một câu `SELECT`, viết:

~~~sql
SELECT *
FROM lesson109_sales.customers;
~~~

Điều đó có nghĩa “đọc bảng `customers` trong schema `lesson109_sales`”. Phần `lesson109_sales` là tên schema; phần `customers` là tên bảng. Dấu chấm `.` phân cách các thành phần định danh.

### Vì sao chia schema?

Schema giúp nhóm các đối tượng theo chức năng hoặc phạm vi quản lý, chẳng hạn `sales`, `hr`, `reporting`. Nó cũng hỗ trợ quản trị quyền trên các không gian tên riêng. Tuy nhiên, **chỉ ghi rõ tên schema không cấp thêm quyền truy cập**: tài khoản vẫn phải có quyền phù hợp đối với schema và bảng.

Trong PostgreSQL, `public` thường là schema có sẵn, nhưng cấu hình quyền và schema mặc định không nên được đoán từ tên database. Dùng các truy vấn kiểm tra ở mục 7 để biết chính xác môi trường đang làm việc.

## 2. Chuẩn bị dữ liệu thực hành ở hai schema

Các ví dụ tiếp theo sử dụng hai schema `lesson109_sales` và `lesson109_archive` trong **database PostgreSQL thực hành riêng**. Cần tài khoản có quyền tạo schema/bảng. Chạy đoạn khởi tạo sau **một lần** ở database chưa có các đối tượng cùng tên:

~~~sql
CREATE SCHEMA lesson109_sales;
CREATE SCHEMA lesson109_archive;

CREATE TABLE lesson109_sales.customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name VARCHAR(80) NOT NULL,
    city VARCHAR(60) NOT NULL
);

CREATE TABLE lesson109_archive.customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name VARCHAR(80) NOT NULL,
    city VARCHAR(60) NOT NULL
);

CREATE TABLE lesson109_sales.orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL
        REFERENCES lesson109_sales.customers(customer_id),
    total_amount NUMERIC(12, 2) NOT NULL
        CHECK (total_amount >= 0)
);

INSERT INTO lesson109_sales.customers
    (customer_id, customer_name, city)
VALUES
    (1, 'An',   'Ho Chi Minh'),
    (2, 'Binh', 'Da Nang'),
    (3, 'Chi',  'Ha Noi');

INSERT INTO lesson109_archive.customers
    (customer_id, customer_name, city)
VALUES
    (1, 'An cu', 'Hue'),
    (4, 'Dung',  'Can Tho');

INSERT INTO lesson109_sales.orders
    (order_id, customer_id, total_amount)
VALUES
    (1001, 1, 120.00),
    (1002, 1,  80.00),
    (1003, 2, 250.00);
~~~

Sau khi khởi tạo:

| Bảng | Nội dung |
| --- | --- |
| `lesson109_sales.customers` | Ba khách hàng hiện tại: An (ID 1), Bình (ID 2), Chi (ID 3) |
| `lesson109_archive.customers` | Hai khách hàng lưu trữ: An cũ (ID 1), Dũng (ID 4) |
| `lesson109_sales.orders` | Ba đơn hàng; An có hai đơn, Bình có một đơn, Chi chưa có đơn |

Ở bảng đơn hàng, khóa ngoại viết `REFERENCES lesson109_sales.customers(customer_id)` để chỉ rõ bảng khách hàng được tham chiếu. Các bảng `customers` trong hai schema là **hai đối tượng độc lập**; cùng có `customer_id = 1` không biến chúng thành cùng một hàng.

## 3. Tham chiếu bảng bằng tên schema

### 3.1. Truy vấn bảng ở schema hiện tại của bài học

~~~sql
SELECT customer_id, customer_name, city
FROM lesson109_sales.customers
ORDER BY customer_id;
~~~

Kết quả mong đợi:

| customer_id | customer_name | city |
| ---: | --- | --- |
| 1 | An | Ho Chi Minh |
| 2 | Binh | Da Nang |
| 3 | Chi | Ha Noi |

### 3.2. Truy vấn bảng trùng tên nhưng thuộc schema khác

~~~sql
SELECT customer_id, customer_name, city
FROM lesson109_archive.customers
ORDER BY customer_id;
~~~

Kết quả:

| customer_id | customer_name | city |
| ---: | --- | --- |
| 1 | An cu | Hue |
| 4 | Dung | Can Tho |

Cả hai truy vấn đều lấy từ `customers`, nhưng **khác schema nên khác bảng**. Đây là lợi ích lớn nhất của định danh đầy đủ `schema.table`: không phụ thuộc vào việc phần mềm SQL Editor đang ưu tiên schema nào.

### 3.3. Cú pháp bảng có schema trong các mệnh đề khác

Tên schema còn dùng ở các vị trí tham chiếu đối tượng khác, không chỉ `FROM`:

~~~sql
-- Ten schema trong JOIN.
SELECT s.customer_name, a.customer_name
FROM lesson109_sales.customers AS s
JOIN lesson109_archive.customers AS a
    ON s.customer_id = a.customer_id;
~~~

Hoặc trong câu lệnh thay đổi dữ liệu (chỉ đọc minh họa cú pháp, không chạy trên dữ liệu cần giữ):

~~~sql
UPDATE lesson109_sales.customers
SET city = 'Da Nang'
WHERE customer_id = 2;
~~~

Câu `UPDATE` trên sẽ cập nhật **bảng thuộc `lesson109_sales`**, không tác động bảng `lesson109_archive.customers`. Đó là thao tác thay đổi dữ liệu thật; cần xác nhận mục tiêu và điều kiện `WHERE` trước khi chạy.

## 4. Khi không ghi schema: PostgreSQL dùng search_path

Một câu ngắn như:

~~~sql
SELECT customer_id, customer_name
FROM customers;
~~~

không ghi tên schema. Trong PostgreSQL, hệ quản trị sẽ tìm bảng `customers` theo **`search_path`** của phiên làm việc và các quy tắc phân giải tên liên quan. Nếu nhiều schema có bảng cùng tên, bảng ở schema được tìm thấy **trước** sẽ được tham chiếu.

Kiểm tra cấu hình và ngữ cảnh:

~~~sql
SHOW search_path;
SELECT current_schema();
SELECT current_schemas(true);
~~~

- `SHOW search_path` hiển thị giá trị cấu hình đường tìm kiếm.
- `current_schema()` trả về schema hiện tại theo quy tắc chọn schema mặc định của PostgreSQL.
- `current_schemas(true)` hiển thị các schema hiệu lực trong đường tìm kiếm, kể cả những schema hệ thống được xét ngầm.

Đừng kết luận mặc định luôn là `public`: cấu hình có thể thay đổi theo tài khoản, database, phiên kết nối hoặc câu lệnh `SET`.

### 4.1. Minh họa chọn bảng theo search_path

Để không làm thay đổi vĩnh viễn cấu hình phiên thực hành, ví dụ dùng `SET LOCAL` trong một transaction PostgreSQL:

~~~sql
BEGIN;

SET LOCAL search_path TO lesson109_sales, public;

SELECT customer_id, customer_name
FROM customers
ORDER BY customer_id;

ROLLBACK;
~~~

Kết quả gồm **An, Bình, Chi**: PostgreSQL tìm thấy bảng `customers` trong `lesson109_sales`. Sau `ROLLBACK`, thiết lập `SET LOCAL` hết hiệu lực khi transaction kết thúc.

Đổi schema đứng đầu:

~~~sql
BEGIN;

SET LOCAL search_path TO lesson109_archive, public;

SELECT customer_id, customer_name
FROM customers
ORDER BY customer_id;

ROLLBACK;
~~~

Lần này truy vấn `FROM customers` đọc **An cũ, Dũng** vì bảng trong `lesson109_archive` được tìm trước.

**Điều quan trọng:** chỉ đổi `search_path` có thể làm **cùng một câu SQL không ghi schema trả về dữ liệu từ bảng khác**. Với những câu SQL cần phân biệt chính xác bảng hiện tại và bảng lưu trữ, ghi đầy đủ `schema.table` là cách rõ ràng hơn.

### 4.2. Tên schema tường minh có phụ thuộc search_path không?

~~~sql
SELECT customer_id, customer_name
FROM lesson109_sales.customers
ORDER BY customer_id;
~~~

Tên schema đã được chỉ rõ, nên việc thay đổi thứ tự tìm kiếm schema **không chuyển tham chiếu này** sang `lesson109_archive.customers`.

Tuy nhiên, định danh đầy đủ vẫn phải thỏa điều kiện: schema và bảng thật sự tồn tại trong database đang kết nối, tên được viết đúng và tài khoản có quyền sử dụng chúng.

### 4.3. search_path ảnh hưởng cả tạo đối tượng

Trong PostgreSQL, nếu viết `CREATE TABLE unqualified_name (...)` mà không ghi schema, bảng thường được tạo trong schema hiện tại thích hợp theo `search_path`, tùy quyền và cấu hình. Vì thế khi tạo bảng thực hành hoặc migration, nên chỉ định schema đích rõ:

~~~sql
CREATE TABLE lesson109_sales.demo_notes (
    note_id INTEGER PRIMARY KEY,
    note_text TEXT
);
~~~

Đây là ví dụ DDL độc lập: nó tạo thêm bảng thật nếu được chạy. Mục tiêu là chỉ rõ vị trí của bảng mới; không cần chạy lệnh này để làm các bài tập phía dưới.

Với hệ thống có nhiều schema và tài khoản, danh sách `search_path` nên được cấu hình có chủ đích. Không tùy tiện thêm schema mà các tài khoản không tin cậy có thể tạo đối tượng vào đường tìm kiếm của ứng dụng quan trọng.

## 5. Bí danh bảng (table alias) là gì?

Bí danh là tên ngắn được gán cho một đối tượng ở phần `FROM` hoặc `JOIN` của **câu truy vấn hiện tại**.

~~~sql
SELECT c.customer_id, c.customer_name
FROM lesson109_sales.customers AS c
WHERE c.city = 'Da Nang';
~~~

Trong câu này:

- `lesson109_sales`: schema của bảng.
- `customers`: tên bảng.
- `c`: **bí danh bảng** tạo bởi `AS c`.
- `c.customer_id` và `c.city`: cách tham chiếu cột bằng bí danh.

Kết quả là một khách hàng: **Bình** (ID 2).

`AS` thường **có thể bỏ** khi đặt bí danh bảng trong PostgreSQL:

~~~sql
SELECT c.customer_id, c.customer_name
FROM lesson109_sales.customers c
WHERE c.city = 'Da Nang';
~~~

Hai cách viết `FROM lesson109_sales.customers AS c` và `FROM lesson109_sales.customers c` có cùng ý nghĩa trong trường hợp này. Dùng `AS` rõ ràng giúp người mới đọc dễ nhận ra chỗ khai báo bí danh.

### Bí danh không phải tên schema và không đổi tên bảng

Sau khi chạy `SELECT ... FROM lesson109_sales.customers AS c`, bảng thật **vẫn** là `lesson109_sales.customers`. Một câu truy vấn sau đó không tự biết `c` là bảng nào:

~~~sql
-- SAI neu chay rieng: c khong phai mot bang/schema that.
SELECT * FROM c;
~~~

Để dùng lại bí danh, phải khai báo nó trong câu truy vấn mới. Bí danh là tên có phạm vi áp dụng trong biểu thức truy vấn, không phải lệnh `RENAME TABLE` hay cách tạo view.

## 6. Vì sao JOIN thường cần bí danh?

Khi kết hợp khách hàng với đơn hàng, cả hai bảng đều có cột `customer_id`. Nếu chỉ viết `customer_id`, hệ quản trị không thể biết bạn muốn nói đến cột ở bảng nào.

Ví dụ dễ bị lỗi trong PostgreSQL:

~~~sql
-- SAI: customer_id ton tai trong ca c va o.
SELECT customer_id, customer_name, order_id
FROM lesson109_sales.customers AS c
JOIN lesson109_sales.orders AS o
    ON c.customer_id = o.customer_id;
~~~

Câu này có thể báo `column reference "customer_id" is ambiguous`. Sửa bằng cách xác định rõ cột qua bí danh:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.total_amount
FROM lesson109_sales.customers AS c
JOIN lesson109_sales.orders AS o
    ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
~~~

Kết quả:

| customer_id | customer_name | order_id | total_amount |
| ---: | --- | ---: | ---: |
| 1 | An | 1001 | 120.00 |
| 1 | An | 1002 | 80.00 |
| 2 | Binh | 1003 | 250.00 |

Chi không có đơn hàng nên không xuất hiện trong `INNER JOIN` này.

**Tên schema và bí danh phối hợp như sau:**

~~~text
FROM lesson109_sales.customers AS c
     |--------------|      |-|
       ten bang day du     bi danh

JOIN lesson109_sales.orders AS o
     |-----------|       |-|
      ten bang day du     bi danh

ON c.customer_id = o.customer_id
   |                |
   cot tu c         cot tu o
~~~

Schema xác định **bảng nào**, còn bí danh xác định **cách gọi bảng đó trong truy vấn**.

### 6.1. JOIN bảng trùng tên ở hai schema

Khi cần so sánh bản ghi hiện hành và lưu trữ:

~~~sql
SELECT
    cur.customer_id,
    cur.customer_name AS current_name,
    arc.customer_name AS archived_name
FROM lesson109_sales.customers AS cur
JOIN lesson109_archive.customers AS arc
    ON cur.customer_id = arc.customer_id
ORDER BY cur.customer_id;
~~~

Kết quả:

| customer_id | current_name | archived_name |
| ---: | --- | --- |
| 1 | An | An cu |

Đây là ví dụ điển hình cần **cả** định danh schema **và** bí danh: tên bảng gốc ở hai phía đều là `customers`, nhưng mỗi phía có schema và bí danh khác nhau.

### 6.2. Cùng một bảng xuất hiện hai lần

Ngay cả khi chỉ có **một bảng**, ta vẫn có thể dùng hai bí danh để so sánh những hàng khác nhau trong cùng bảng (*self join*):

~~~sql
SELECT
    a.customer_name AS name_a,
    b.customer_name AS name_b
FROM lesson109_sales.customers AS a
JOIN lesson109_sales.customers AS b
    ON a.customer_id < b.customer_id
ORDER BY a.customer_id, b.customer_id;
~~~

Kết quả là ba cặp: An–Bình, An–Chi, Bình–Chi. `a` và `b` cùng trỏ tới đối tượng bảng nguồn nhưng đại diện cho **hai vai trò** của bảng trong phép nối. Nếu dùng cùng một bí danh cho cả hai vai trò, tên tham chiếu sẽ không thể phân biệt.

## 7. Phân biệt bí danh bảng và bí danh cột

SQL dùng `AS` cho cả hai loại, nhưng vị trí và mục đích khác nhau:

~~~sql
SELECT
    c.customer_id,
    c.customer_name AS display_name
FROM lesson109_sales.customers AS c
WHERE c.city = 'Ho Chi Minh'
ORDER BY display_name;
~~~

| Phần | Loại tên | Ý nghĩa |
| --- | --- | --- |
| `AS c` sau `FROM lesson109_sales.customers` | Bí danh **bảng** | Gọi bảng bằng `c` trong truy vấn |
| `c.customer_name` | Tham chiếu **cột** | Đọc cột `customer_name` từ vai trò bảng `c` |
| `AS display_name` trong danh sách `SELECT` | Bí danh **cột kết quả** | Đặt tên hiển thị cho cột đầu ra |
| `ORDER BY display_name` | Dùng bí danh cột trong `ORDER BY` | Sắp xếp theo biểu thức đầu ra được đặt tên |

Kết quả câu trên có An, với cột tên `display_name`.

Trong PostgreSQL, không thể giả định bí danh cột `SELECT` đã có sẵn trong `WHERE` của **cùng cấp truy vấn**. Ví dụ sau không đúng nếu chỉ dựa vào alias `display_name`:

~~~sql
-- SAI trong PostgreSQL: alias cua SELECT khong dung truc tiep trong WHERE cung cap.
SELECT c.customer_name AS display_name
FROM lesson109_sales.customers AS c
WHERE display_name = 'An';
~~~

Viết đúng bằng cột nguồn:

~~~sql
SELECT c.customer_name AS display_name
FROM lesson109_sales.customers AS c
WHERE c.customer_name = 'An';
~~~

Bí danh bảng `c` được khai báo ở `FROM` và được dùng để tham chiếu cột trong `WHERE`, `JOIN ON`, `SELECT` hay `ORDER BY`. Bí danh cột `display_name` đặt tên một **biểu thức kết quả**, và quy tắc nơi được phép dùng lại nó phụ thuộc mệnh đề và SQL dialect.

## 8. Quy tắc phạm vi: sau khi đặt bí danh, dùng chính bí danh đó

Trong PostgreSQL, khi một mục bảng ở `FROM` đã được đặt bí danh, **bí danh thay thế tên bảng trong phạm vi truy vấn đó**.

~~~sql
-- SAI: customers duoc dat bi danh c, nen khong dung lai ten goc tai day.
SELECT lesson109_sales.customers.customer_name
FROM lesson109_sales.customers AS c;
~~~

Truy vấn thường báo lỗi kiểu `invalid reference to FROM-clause entry`. Sửa:

~~~sql
SELECT c.customer_name
FROM lesson109_sales.customers AS c;
~~~

Không bắt buộc mọi cột đều phải có tiền tố `c.` nếu chỉ có một bảng và không gây nhập nhằng:

~~~sql
SELECT customer_id, customer_name
FROM lesson109_sales.customers AS c;
~~~

Câu trên vẫn hợp lệ. Tuy nhiên, viết `c.customer_id` hữu ích khi câu SQL có thể được mở rộng thêm `JOIN` hoặc khi nhiều bảng có cột trùng tên.

### 8.1. Bí danh trong truy vấn con

Bí danh của truy vấn ngoài có thể được dùng trong một **truy vấn con có liên hệ** (*correlated subquery*) thích hợp:

~~~sql
SELECT c.customer_id, c.customer_name
FROM lesson109_sales.customers AS c
WHERE EXISTS (
    SELECT 1
    FROM lesson109_sales.orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
~~~

Kết quả gồm **An và Bình**, vì chỉ hai khách hàng này có ít nhất một đơn. Trong truy vấn con, `o` là bí danh của `orders` còn `c` là bí danh đã khai báo ở truy vấn ngoài.

Ngược lại, bí danh được tạo **chỉ bên trong truy vấn con** không tự động có hiệu lực ở cấp truy vấn ngoài. Khi cần tham chiếu kết quả của một truy vấn con đặt trong `FROM`, hãy đặt bí danh cho chính bảng dẫn xuất:

~~~sql
SELECT q.customer_name
FROM (
    SELECT customer_name
    FROM lesson109_sales.customers
    WHERE city = 'Da Nang'
) AS q;
~~~

Kết quả là Bình. `q` đại diện cho **tập kết quả của truy vấn con trong `FROM`**, không đổi tên bảng `lesson109_sales.customers`.

## 9. Các lỗi thường gặp và cách xử lý

| Hiện tượng hoặc câu SQL sai | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `FROM customers` đọc nhầm bảng lưu trữ | `search_path` ưu tiên schema chứa bảng đó | Ghi rõ `FROM lesson109_sales.customers` hoặc kiểm tra cấu hình `search_path` |
| `relation "customers" does not exist` | Không tìm thấy bảng không ghi schema trong đường tìm kiếm, hoặc tên sai | Kiểm tra database/schema/bảng và thử tên đầy đủ |
| `schema "..." does not exist` | Gõ sai tên schema hoặc schema chưa được tạo | Kiểm tra schema tồn tại và kết nối đúng database |
| `permission denied` | Tài khoản thiếu quyền phù hợp | Kiểm tra quyền truy cập schema/bảng; đổi tên không giải quyết vấn đề quyền |
| `column reference "customer_id" is ambiguous` | Nhiều bảng trong truy vấn có cột cùng tên | Dùng `c.customer_id` hoặc `o.customer_id` tùy mục đích |
| `FROM lesson109_sales.customers AS c` nhưng lại dùng `customers.customer_name` | Tên bảng đã được thay bởi alias ở cấp truy vấn này | Dùng `c.customer_name` |
| `FROM lesson109_sales.c` với ý định `c` là alias | Hệ quản trị coi `c` là tên **bảng** trong schema `lesson109_sales` | Viết `FROM lesson109_sales.customers AS c` |
| Dùng `display_name` ở `WHERE` dù chỉ đặt tên trong `SELECT` | Bí danh **cột** không có phạm vi như bí danh **bảng** trong PostgreSQL | Dùng biểu thức hoặc cột gốc trong `WHERE` |
| Hai bảng cùng `AS c` trong một phép `JOIN` | Bí danh tham chiếu bị trùng | Đặt bí danh khác nhau như `current_c` và `archive_c` |

### Tên có chữ hoa và dấu nháy kép

PostgreSQL chuyển các định danh **không đặt trong dấu nháy kép** về chữ thường khi phân giải. Nếu một schema/bảng được tạo bằng tên chữ hoa có dấu nháy kép, chẳng hạn `"SalesData"."Customers"`, các truy vấn về sau phải viết đúng tên và kiểu chữ có dấu nháy kép tương ứng.

Vì vậy nên dùng tên không có khoảng trắng, chữ thường và dấu gạch dưới như `lesson109_sales.customers` để giảm nhầm lẫn. Dấu nháy đơn `'...'` dành cho **giá trị chuỗi**, không dùng thay dấu nháy kép để trích dẫn định danh PostgreSQL.

## 10. Kiểm tra schema, bảng và quyền truy cập trong môi trường thực hành

Để biết hai bảng `customers` đang ở đâu, có thể xem metadata:

~~~sql
SELECT
    table_schema,
    table_name,
    table_type
FROM information_schema.tables
WHERE table_schema IN ('lesson109_sales', 'lesson109_archive')
ORDER BY table_schema, table_name;
~~~

Với các bảng đã tạo, kết quả cho biết bảng khách hàng thuộc cả hai schema và bảng đơn hàng thuộc `lesson109_sales`. Khả năng nhìn thấy đối tượng trong `information_schema` phụ thuộc quyền của tài khoản và loại đối tượng.

Kiểm tra database hiện hành và schema ưu tiên trong PostgreSQL:

~~~sql
SELECT current_database() AS database_name;
SELECT current_schema() AS current_schema_name;
SHOW search_path;
~~~

Nếu một truy vấn không ghi schema hoạt động ở một công cụ nhưng báo lỗi ở công cụ khác, hãy kiểm tra **kết nối**, **database**, **user/role**, **search_path** và **quyền** của từng phiên. Không phải mọi SQL Editor đều dùng chung một phiên kết nối hoặc cùng cấu hình khi mở tab mới.

Nếu dùng `psql`, lệnh `\dt lesson109_sales.*` có thể liệt kê các bảng trong schema này. Đây là **lệnh của chương trình `psql`**, không phải câu SQL chuẩn để gửi vào mọi SQL Editor. Các ví dụ `information_schema` ở trên có thể thực thi như SQL thông thường.

## 11. Khác biệt giữa PostgreSQL và các SQL dialect khác

Không nên giả định cấu trúc tên đối tượng hay cơ chế chọn schema giống hệt nhau giữa mọi hệ quản trị.

| Hệ quản trị | Cách tham chiếu điển hình | Điểm cần lưu ý |
| --- | --- | --- |
| **PostgreSQL** | `schema_name.table_name` | Database được chọn qua kết nối; tên `database.schema.table` không phải đường truy cập trực tiếp đến database khác bằng cú pháp bảng thông thường; bảng không ghi schema được giải theo `search_path` |
| **MySQL** | `database_name.table_name` | Trong MySQL, khái niệm `SCHEMA` và `DATABASE` được dùng gần như đồng nghĩa; `USE database_name` đặt database mặc định; alias thường dùng tương tự `FROM db.table AS t` |
| **SQL Server** | `schema_name.table_name` hoặc `database_name.schema_name.table_name` | Có khái niệm database và schema riêng; schema mặc định của tài khoản ảnh hưởng tên không đầy đủ |
| **SQLite** | `main.table_name`, `temp.table_name` hoặc `attached_name.table_name` | SQLite không tổ chức schema như PostgreSQL; `main` và tên database gắn bằng `ATTACH` là không gian tên trong kết nối |
| **Oracle Database** | `schema_name.table_name` | Schema gắn với chủ sở hữu đối tượng; synonym và quy tắc phân giải tên có thể ảnh hưởng cách tham chiếu |

Ví dụ cú pháp ở MySQL:

~~~sql
SELECT c.customer_id, c.customer_name
FROM sales_db.customers AS c;
~~~

Trong PostgreSQL của bài thực hành, phần đứng trước dấu chấm là **schema**, còn `sales_db` trong ví dụ MySQL thường là **database**. Không lấy tên gọi “schema” trong giao diện một công cụ rồi suy ra cấu trúc phân cấp dữ liệu của mọi hệ quản trị đều như nhau.

Dù khác dialect, ý tưởng chung vẫn hữu ích: **chỉ rõ nguồn dữ liệu khi cần tránh nhập nhằng, và đặt bí danh riêng cho mỗi vai trò bảng trong truy vấn**.

## 12. Bài tập thực hành

Các bài tập dưới đây sử dụng đúng ba bảng và dữ liệu mẫu ở mục 2. Dữ liệu không được thay đổi trong quá trình giải bài, trừ khi bạn chủ động thao tác trong database thử nghiệm.

### Bài 1 — Truy vấn đúng schema

**Yêu cầu:** lấy `customer_id` và `customer_name` của khách hàng trong schema lưu trữ, sắp theo ID. Không dựa vào `search_path`.

**Đáp án tham khảo:**

~~~sql
SELECT customer_id, customer_name
FROM lesson109_archive.customers
ORDER BY customer_id;
~~~

Kết quả là hai hàng: `(1, An cu)` và `(4, Dung)`.

### Bài 2 — Đặt bí danh và lọc dữ liệu

**Yêu cầu:** đặt bí danh `c` cho bảng khách hàng hiện tại, chỉ lấy tên và thành phố của người sống ở `Da Nang`.

**Đáp án tham khảo:**

~~~sql
SELECT c.customer_name, c.city
FROM lesson109_sales.customers AS c
WHERE c.city = 'Da Nang';
~~~

Kết quả là Bình ở Đà Nẵng. `c` là tên tham chiếu của bảng, không phải schema mới.

### Bài 3 — Sửa lỗi cột nhập nhằng

Truy vấn sau có vấn đề:

~~~sql
SELECT customer_id, order_id
FROM lesson109_sales.customers AS c
JOIN lesson109_sales.orders AS o
    ON c.customer_id = o.customer_id;
~~~

**Yêu cầu:** sửa danh sách cột để biết đó là ID của khách hàng và mã đơn hàng.

**Đáp án tham khảo:**

~~~sql
SELECT c.customer_id, o.order_id
FROM lesson109_sales.customers AS c
JOIN lesson109_sales.orders AS o
    ON c.customer_id = o.customer_id
ORDER BY c.customer_id, o.order_id;
~~~

Kết quả: `(1,1001)`, `(1,1002)`, `(2,1003)`.

### Bài 4 — So sánh hai bảng cùng tên

**Yêu cầu:** tìm khách hàng có cùng `customer_id` trong bảng hiện tại và bảng lưu trữ; hiển thị ID, tên hiện tại và tên lưu trữ.

**Đáp án tham khảo:**

~~~sql
SELECT
    s.customer_id,
    s.customer_name AS current_name,
    a.customer_name AS archive_name
FROM lesson109_sales.customers AS s
JOIN lesson109_archive.customers AS a
    ON s.customer_id = a.customer_id
ORDER BY s.customer_id;
~~~

Chỉ có ID 1 khớp, với hai tên `An` và `An cu`. Hai bí danh `s` và `a` làm rõ vai trò của từng bảng trong cùng câu truy vấn.

### Bài 5 — Dự đoán kết quả khi đổi search_path

Xét hai truy vấn độc lập trong PostgreSQL:

~~~sql
BEGIN;
SET LOCAL search_path TO lesson109_sales, public;
SELECT COUNT(*) AS so_khach FROM customers;
ROLLBACK;
~~~

~~~sql
BEGIN;
SET LOCAL search_path TO lesson109_archive, public;
SELECT COUNT(*) AS so_khach FROM customers;
ROLLBACK;
~~~

**Câu hỏi:** vì sao hai câu `SELECT` có cùng văn bản mà có thể trả về hai số khác nhau?

**Đáp án:** truy vấn đầu đọc `lesson109_sales.customers`, cho kết quả **3**; truy vấn sau đọc `lesson109_archive.customers`, cho kết quả **2**. Tên bảng không có schema được phân giải theo `search_path` hiệu lực của từng transaction.

### Bài 6 — Sửa tham chiếu sau khi đặt bí danh

~~~sql
-- SAI trong PostgreSQL sau khi da khai bao AS c.
SELECT lesson109_sales.customers.customer_name
FROM lesson109_sales.customers AS c;
~~~

**Yêu cầu:** sửa mà vẫn giữ bí danh `c`.

**Đáp án:**

~~~sql
SELECT c.customer_name
FROM lesson109_sales.customers AS c
ORDER BY c.customer_id;
~~~

Kết quả theo thứ tự là An, Bình, Chi. Khi đã có `AS c`, sử dụng `c` để tham chiếu bảng trong truy vấn.

### Bài 7 — Phân biệt hai loại AS

~~~sql
SELECT c.customer_name AS label
FROM lesson109_sales.customers AS c
ORDER BY label;
~~~

**Câu hỏi:** hai lần `AS` có cùng vai trò không?

**Đáp án:** không. `AS c` khai báo **bí danh bảng**, dùng để tham chiếu cột `c.customer_name`. `AS label` khai báo **bí danh cột kết quả**, có thể được dùng ở `ORDER BY` trong PostgreSQL. Việc đặt bí danh cột không đổi tên cột `customer_name` trong lược đồ.

## 13. Ghi nhớ

| Nhu cầu | Cách viết | Ý nghĩa |
| --- | --- | --- |
| Chỉ rõ bảng trong schema | `FROM lesson109_sales.customers` | Chọn đối tượng bảng chính xác |
| Đặt bí danh ngắn | `FROM lesson109_sales.customers AS c` | Gọi bảng là `c` trong truy vấn |
| Tham chiếu cột qua bí danh | `SELECT c.customer_name` | Cột `customer_name` của vai trò bảng `c` |
| Kết hợp nhiều bảng | `JOIN lesson109_sales.orders AS o` | Đặt mỗi bảng một tên tham chiếu riêng |
| Tránh cột trùng tên | `c.customer_id = o.customer_id` | Phân biệt cột ở mỗi phía của phép nối |
| Kiểm tra bảng không ghi schema | `SHOW search_path;` | Xem đường tìm kiếm của PostgreSQL |

Tên schema và bí danh thường xuất hiện cùng nhau nhưng giải quyết **hai vấn đề khác nhau**: `schema.table` chọn đúng **đối tượng dữ liệu**, còn `AS alias` giúp **gọi và phân biệt các vai trò bảng trong câu SQL**. Khi viết truy vấn nhiều bảng, hãy xác định đúng database/schema trước, đặt bí danh dễ hiểu cho từng bảng, rồi tham chiếu những cột có thể nhập nhằng qua bí danh tương ứng.
