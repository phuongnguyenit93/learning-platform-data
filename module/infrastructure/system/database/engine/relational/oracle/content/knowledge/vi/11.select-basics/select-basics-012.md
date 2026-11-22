# Giải thích và kiểm chứng một truy vấn bằng dữ liệu tối thiểu

Đọc một câu SQL không chỉ là nhìn các từ khóa `SELECT`, `FROM` hay `WHERE` rồi đoán kết quả. Muốn hiểu chắc một truy vấn, ta cần biết **dữ liệu đầu vào gồm những dòng nào**, **mỗi mệnh đề làm thay đổi tập dòng ra sao**, **giá trị NULL được xử lý thế nào**, và **kết quả mong đợi có thể được kiểm tra độc lập bằng cách nào**.

Một kỹ thuật rất hữu ích khi học Oracle SQL là tạo một **bộ dữ liệu tối thiểu có chủ đích**: ít bảng, ít cột, vài dòng đại diện cho những trường hợp khác nhau. Ta có thể tự tính kết quả bằng tay, chạy truy vấn trên Oracle, rồi đối chiếu hai kết quả. Cách làm này giúp phát hiện lỗi join, lọc nhầm dữ liệu, đếm sai dòng và hiểu nhầm hành vi của aggregate.

Bài học sử dụng một ví dụ bán hàng nhỏ gồm khách hàng và đơn hàng. Từ dữ liệu đó, ta đi từ truy vấn đơn bảng tới JOIN, LEFT JOIN, GROUP BY, NULL và kiểm chứng kết quả bằng `MINUS`.

## 1. Vì sao cần dữ liệu tối thiểu?

Một truy vấn chạy trên database thật có thể trả hàng nghìn hoặc hàng triệu dòng. Nếu kết quả không đúng, rất khó xác định nguyên nhân vì có nhiều yếu tố cùng tác động: dữ liệu lịch sử, trạng thái, bản ghi thiếu, quan hệ nhiều-nhiều, quyền truy cập và các điều kiện lọc.

Một bộ dữ liệu nhỏ giúp:

- **Biết trước kết quả:** có thể liệt kê từng dòng sẽ được giữ hoặc bị loại.
- **Cô lập một quy tắc:** chẳng hạn chỉ kiểm tra điều kiện `WHERE` hoặc cách `LEFT JOIN` giữ lại bản ghi không có dòng con.
- **Tái hiện lỗi:** người khác có thể chạy cùng DDL, DML và SQL để quan sát đúng tình huống.
- **Kiểm tra trường hợp biên:** không có dòng con, có NULL, có nhiều dòng con, giá trị trùng, hoặc trạng thái không hợp lệ.
- **Phân biệt lỗi logic với lỗi dữ liệu:** nếu truy vấn sai ngay trên bộ dữ liệu nhỏ, ta có ví dụ cụ thể để giải thích.

Một dataset tốt không nhất thiết có nhiều dòng. Nó cần có **đủ trường hợp để phân biệt các cách hiểu cạnh tranh**. Nếu chỉ tạo ba khách hàng mà tất cả đều có đúng một đơn hàng, ta chưa kiểm chứng được sự khác biệt giữa JOIN và LEFT JOIN, hoặc giữa `COUNT(*)` và `COUNT(child_id)`.

## 2. Đọc yêu cầu trước khi viết SQL

Giả sử yêu cầu báo cáo là:

> “Liệt kê các khách hàng đang hoạt động, cùng số đơn hàng đã thanh toán và tổng giá trị của các đơn đã thanh toán. Khách hàng chưa có đơn đã thanh toán vẫn phải xuất hiện với số đơn bằng 0 và tổng tiền bằng 0. Sắp xếp tổng tiền giảm dần; nếu bằng nhau thì sắp xếp theo mã khách hàng.”

Trước khi viết truy vấn, chuyển câu mô tả thành những điều kiện có thể kiểm chứng:

| Yêu cầu | Diễn giải thành SQL |
|---|---|
| Chỉ khách hàng đang hoạt động | `WHERE customer.active_flag = 'Y'` |
| Chỉ tính đơn đã thanh toán | Điều kiện trạng thái đặt trong `ON` của LEFT JOIN |
| Khách không có đơn vẫn xuất hiện | Dùng `LEFT JOIN` từ CUSTOMER sang ORDER |
| Đếm số đơn | `COUNT(order_id)`, không dùng `COUNT(*)` cho trường hợp không có đơn |
| Tổng tiền | `SUM(amount)`, xử lý NULL bằng `NVL` nếu cần hiển thị 0 |
| Sắp xếp tổng tiền giảm dần | `ORDER BY paid_total DESC` |
| Nếu bằng tiền thì theo mã khách | Thêm khóa phụ `customer_id ASC` |

Ta có thể viết câu SQL trước, nhưng nếu chưa định nghĩa rõ “đơn đã thanh toán” là gì, “khách hoạt động” được xác định ở đâu, hay khách chưa có đơn có được giữ không, thì kết quả sẽ phụ thuộc vào suy đoán của người viết.

## 3. Tạo bộ dữ liệu tối thiểu trong Oracle

Ta dùng hai bảng:

- `LAB_CUSTOMER`: mỗi dòng là một khách hàng.
- `LAB_ORDER`: mỗi dòng là một đơn hàng thuộc một khách hàng.

Bộ dữ liệu cần có bốn tình huống:

1. Khách hàng đang hoạt động có một đơn đã thanh toán và một đơn đã hủy.
2. Khách hàng đang hoạt động có hai đơn đã thanh toán.
3. Khách hàng đang không hoạt động nhưng có đơn đã thanh toán.
4. Khách hàng đang hoạt động nhưng không có đơn đã thanh toán.

Chính bốn trường hợp này cho phép kiểm tra điều kiện trạng thái, điều kiện khách hàng và LEFT JOIN.

### 3.1. Tạo bảng

Chạy trong một schema lab của PDB thực hành. Các tên `LAB_` được dành cho ví dụ; nếu đã có bảng cùng tên, hãy chọn tên khác thay vì ghi đè đối tượng đang tồn tại.

~~~sql
CREATE TABLE lab_customer (
    customer_id   NUMBER(5) PRIMARY KEY,
    customer_name VARCHAR2(50 CHAR) NOT NULL,
    active_flag   CHAR(1 CHAR) NOT NULL,
    CONSTRAINT ck_lab_customer_active
      CHECK (active_flag IN ('Y', 'N'))
);

CREATE TABLE lab_order (
    order_id    NUMBER(5) PRIMARY KEY,
    customer_id NUMBER(5) NOT NULL,
    order_status VARCHAR2(20 CHAR) NOT NULL,
    amount      NUMBER(10,2) NOT NULL,
    CONSTRAINT fk_lab_order_customer
      FOREIGN KEY (customer_id)
      REFERENCES lab_customer (customer_id),
    CONSTRAINT ck_lab_order_status
      CHECK (order_status IN ('PAID', 'CANCELLED', 'PENDING')),
    CONSTRAINT ck_lab_order_amount
      CHECK (amount >= 0)
);
~~~

Hai bảng có primary key để nhận diện dòng. Foreign key bảo đảm mỗi đơn tham chiếu một khách hàng có thật. Các check constraint giới hạn cờ hoạt động, trạng thái và số tiền không âm.

### 3.2. Chèn dữ liệu khách hàng

~~~sql
INSERT INTO lab_customer
    (customer_id, customer_name, active_flag)
VALUES
    (1, 'An', 'Y');

INSERT INTO lab_customer
    (customer_id, customer_name, active_flag)
VALUES
    (2, 'Binh', 'Y');

INSERT INTO lab_customer
    (customer_id, customer_name, active_flag)
VALUES
    (3, 'Chi', 'N');

INSERT INTO lab_customer
    (customer_id, customer_name, active_flag)
VALUES
    (4, 'Dung', 'Y');
~~~

### 3.3. Chèn dữ liệu đơn hàng

~~~sql
INSERT INTO lab_order
    (order_id, customer_id, order_status, amount)
VALUES
    (101, 1, 'PAID', 120);

INSERT INTO lab_order
    (order_id, customer_id, order_status, amount)
VALUES
    (102, 1, 'CANCELLED', 30);

INSERT INTO lab_order
    (order_id, customer_id, order_status, amount)
VALUES
    (103, 2, 'PAID', 200);

INSERT INTO lab_order
    (order_id, customer_id, order_status, amount)
VALUES
    (104, 2, 'PAID', 200);

INSERT INTO lab_order
    (order_id, customer_id, order_status, amount)
VALUES
    (105, 3, 'PAID', 500);

COMMIT;
~~~

### 3.4. Kiểm tra dữ liệu nguồn trước khi đọc truy vấn

~~~sql
SELECT customer_id, customer_name, active_flag
FROM lab_customer
ORDER BY customer_id;

SELECT order_id, customer_id, order_status, amount
FROM lab_order
ORDER BY order_id;
~~~

Dữ liệu có thể tóm tắt bằng bảng:

**LAB_CUSTOMER**

| CUSTOMER_ID | CUSTOMER_NAME | ACTIVE_FLAG |
|---:|---|:---:|
| 1 | An | Y |
| 2 | Binh | Y |
| 3 | Chi | N |
| 4 | Dung | Y |

**LAB_ORDER**

| ORDER_ID | CUSTOMER_ID | ORDER_STATUS | AMOUNT |
|---:|---:|---|---:|
| 101 | 1 | PAID | 120 |
| 102 | 1 | CANCELLED | 30 |
| 103 | 2 | PAID | 200 |
| 104 | 2 | PAID | 200 |
| 105 | 3 | PAID | 500 |

Chú ý các đặc điểm được cài vào dữ liệu:

- `An` có hai đơn, nhưng chỉ một đơn `PAID`.
- `Binh` có hai đơn `PAID`, với số tiền bằng nhau.
- `Chi` có đơn `PAID` nhưng khách hàng không hoạt động.
- `Dung` hoạt động nhưng không có dòng nào trong `LAB_ORDER`.

Nếu không có các trường hợp này, ta khó phát hiện một số lỗi thường gặp trong truy vấn.

## 4. Giải thích truy vấn đơn bảng bằng cách dự đoán từng dòng

Trước khi JOIN, hãy bắt đầu bằng một câu SELECT đơn giản:

~~~sql
SELECT
    customer_id,
    customer_name
FROM lab_customer
WHERE active_flag = 'Y'
ORDER BY customer_id;
~~~

Đọc từng phần:

- `SELECT customer_id, customer_name`: chỉ lấy hai cột cần hiển thị.
- `FROM lab_customer`: tập dòng đầu vào đến từ bảng khách hàng.
- `WHERE active_flag = 'Y'`: chỉ giữ các dòng có cờ hoạt động bằng Y.
- `ORDER BY customer_id`: sắp xếp kết quả theo mã tăng dần.

Kiểm chứng bằng bảng nguồn:

| CUSTOMER_ID | CUSTOMER_NAME | ACTIVE_FLAG | Giữ lại? | Lý do |
|---:|---|:---:|:---:|---|
| 1 | An | Y | Có | Y = Y |
| 2 | Binh | Y | Có | Y = Y |
| 3 | Chi | N | Không | N khác Y |
| 4 | Dung | Y | Có | Y = Y |

Kết quả mong đợi:

| CUSTOMER_ID | CUSTOMER_NAME |
|---:|---|
| 1 | An |
| 2 | Binh |
| 4 | Dung |

Đây là cách kiểm chứng cơ bản nhất: **đánh dấu từng dòng theo điều kiện WHERE**, rồi so sánh với output Oracle. Nếu Oracle trả thêm `Chi`, hãy xem lại điều kiện hoặc dữ liệu thực tế trước khi sửa truy vấn.

### 4.1. SELECT * và SELECT cột cụ thể

`SELECT *` yêu cầu trả tất cả cột của các bảng trong phạm vi truy vấn:

~~~sql
SELECT *
FROM lab_customer;
~~~

Nó tiện khi khám phá bảng nhỏ, nhưng trong ứng dụng nên chọn cột cần dùng:

~~~sql
SELECT customer_id, customer_name
FROM lab_customer;
~~~

Chọn cột rõ ràng giúp người đọc hiểu dữ liệu đầu ra, giảm dữ liệu truyền về, tránh phụ thuộc thứ tự cột và hạn chế thay đổi ngoài ý muốn khi schema được thêm cột. Khi JOIN hai bảng cùng có cột `CUSTOMER_ID`, hãy dùng alias bảng để xác định rõ cột thuộc bên nào.

### 4.2. Bí danh cột

~~~sql
SELECT
    customer_id AS id,
    customer_name AS full_name
FROM lab_customer;
~~~

`AS` đặt nhãn cho biểu thức trong kết quả. Bí danh giúp báo cáo dễ đọc, nhưng **không đổi tên cột trong bảng**. Oracle cho phép tham chiếu select-list alias trong `ORDER BY` ở cùng query block, nhưng không thể mặc định dùng alias đó trong `WHERE` cùng cấp.

## 5. Giải thích JOIN bằng cách ghép từng dòng

Muốn kết hợp khách hàng với đơn hàng, ta dùng điều kiện khóa:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.order_status,
    o.amount
FROM lab_customer c
JOIN lab_order o
  ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
~~~

`c` và `o` là table alias. `ON o.customer_id = c.customer_id` chỉ ra cách hai bảng liên hệ. Đây là **INNER JOIN** (từ khóa `JOIN` không kèm `LEFT` mặc định là inner join): chỉ các cặp dòng thỏa điều kiện mới xuất hiện.

Kết quả dự kiến:

| CUSTOMER_ID | CUSTOMER_NAME | ORDER_ID | ORDER_STATUS | AMOUNT |
|---:|---|---:|---|---:|
| 1 | An | 101 | PAID | 120 |
| 1 | An | 102 | CANCELLED | 30 |
| 2 | Binh | 103 | PAID | 200 |
| 2 | Binh | 104 | PAID | 200 |
| 3 | Chi | 105 | PAID | 500 |

`Dung` không xuất hiện vì không có dòng đơn hàng nào có `CUSTOMER_ID = 4`. Trong inner join, một dòng ở bảng trái không tìm thấy dòng tương ứng ở bảng phải sẽ bị loại khỏi kết quả.

### 5.1. Vì sao một khách hàng xuất hiện nhiều lần?

`An` có hai đơn nên JOIN tạo hai dòng kết quả. Đây là hành vi đúng của quan hệ 1:N, không phải Oracle tự nhân bản sai dữ liệu.

Nếu chỉ muốn mỗi khách một dòng, cần xác định **cần thông tin nào của các đơn**:

- Muốn đếm số đơn: dùng `COUNT`.
- Muốn tổng tiền: dùng `SUM`.
- Muốn lấy đơn mới nhất: dùng hàm phân tích hoặc cách chọn dòng có thứ tự rõ ràng.
- Muốn liệt kê từng đơn: giữ nhiều dòng như kết quả JOIN.

Không dùng `DISTINCT` một cách tùy tiện để “xóa dòng trùng”, vì hai đơn khác nhau có thể có cùng các cột đang chọn; việc loại trùng sẽ làm mất thông tin hợp lệ.

### 5.2. JOIN không có điều kiện

~~~sql
-- Ví dụ này tạo tích Descartes, không phải cách nối hai bảng theo quan hệ.
SELECT c.customer_name, o.order_id
FROM lab_customer c
CROSS JOIN lab_order o;
~~~

Với 4 khách và 5 đơn, `CROSS JOIN` tạo **4 × 5 = 20 dòng**. Nếu bỏ quên điều kiện nối trong cú pháp join cũ, truy vấn có thể vô tình tạo kết quả phình lớn. Hãy kiểm tra khóa nối và số dòng dự kiến trước khi chạy truy vấn trên dữ liệu thật.

## 6. LEFT JOIN: giữ khách hàng không có đơn

Yêu cầu ban đầu nói khách đang hoạt động **vẫn phải xuất hiện dù chưa có đơn đã thanh toán**. INNER JOIN không đáp ứng. Ta cần `LEFT JOIN`:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.order_status,
    o.amount
FROM lab_customer c
LEFT JOIN lab_order o
  ON o.customer_id = c.customer_id
WHERE c.active_flag = 'Y'
ORDER BY c.customer_id, o.order_id;
~~~

`LEFT JOIN` giữ mọi dòng của bảng bên trái (`LAB_CUSTOMER`). Khi không tìm thấy dòng bên phải, các cột thuộc `LAB_ORDER` được điền **NULL** trong dòng kết quả mở rộng.

Kết quả:

| CUSTOMER_ID | CUSTOMER_NAME | ORDER_ID | ORDER_STATUS | AMOUNT |
|---:|---|---:|---|---:|
| 1 | An | 101 | PAID | 120 |
| 1 | An | 102 | CANCELLED | 30 |
| 2 | Binh | 103 | PAID | 200 |
| 2 | Binh | 104 | PAID | 200 |
| 4 | Dung | NULL | NULL | NULL |

`Dung` vẫn xuất hiện, với các cột đơn hàng là NULL. Đây là ý nghĩa quan trọng nhất của LEFT JOIN: **giữ dòng bên trái ngay cả khi không có dòng khớp bên phải**.

### 6.1. Đặt điều kiện trạng thái ở ON hay WHERE?

Hai câu SQL sau **không tương đương**:

**Cách A — chỉ nối những đơn đã thanh toán:**

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.amount
FROM lab_customer c
LEFT JOIN lab_order o
  ON o.customer_id = c.customer_id
 AND o.order_status = 'PAID'
WHERE c.active_flag = 'Y'
ORDER BY c.customer_id, o.order_id;
~~~

Kết quả có:

| CUSTOMER_ID | CUSTOMER_NAME | ORDER_ID | AMOUNT |
|---:|---|---:|---:|
| 1 | An | 101 | 120 |
| 2 | Binh | 103 | 200 |
| 2 | Binh | 104 | 200 |
| 4 | Dung | NULL | NULL |

Đơn `102` bị hủy không khớp điều kiện trong `ON`. Tuy nhiên, `Dung` vẫn giữ lại vì LEFT JOIN không tìm được đơn đã thanh toán.

**Cách B — lọc trạng thái sau khi JOIN:**

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.amount
FROM lab_customer c
LEFT JOIN lab_order o
  ON o.customer_id = c.customer_id
WHERE c.active_flag = 'Y'
  AND o.order_status = 'PAID'
ORDER BY c.customer_id, o.order_id;
~~~

Ở đây dòng của `Dung` có `o.order_status = NULL`. Điều kiện `NULL = 'PAID'` không TRUE, nên dòng bị WHERE loại bỏ. Kết quả chỉ còn `An` và `Binh`. Về mặt kết quả, điều kiện WHERE này khiến truy vấn có hành vi giống inner join đối với predicate đó.

**Quy tắc đọc:** Điều kiện mô tả *dòng bên phải nào được coi là khớp* thường đặt trong `ON` khi cần giữ dòng bên trái không có kết quả. Điều kiện mô tả *dòng bên trái nào được đưa vào báo cáo* đặt trong `WHERE`. Cần quyết định theo ngữ nghĩa, không chỉ theo thói quen.

## 7. Truy vấn chính: kết hợp JOIN và aggregate

Ta quay lại yêu cầu ban đầu:

> Liệt kê khách hàng đang hoạt động, đếm số đơn PAID và cộng tổng tiền PAID. Khách chưa có đơn PAID vẫn phải xuất hiện với kết quả bằng 0. Sắp xếp tổng tiền giảm dần, nếu bằng nhau thì theo mã khách tăng dần.

Truy vấn:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count,
    NVL(SUM(o.amount), 0) AS paid_total
FROM lab_customer c
LEFT JOIN lab_order o
  ON o.customer_id = c.customer_id
 AND o.order_status = 'PAID'
WHERE c.active_flag = 'Y'
GROUP BY
    c.customer_id,
    c.customer_name
ORDER BY
    paid_total DESC,
    c.customer_id ASC;
~~~

### 7.1. Đọc từng mệnh đề

**`FROM lab_customer c`**

Lấy bảng khách hàng làm tập cơ sở. Alias `c` được dùng để viết ngắn và tránh mơ hồ khi các bảng có cột trùng tên.

**`LEFT JOIN lab_order o`**

Nối thêm đơn hàng theo khóa `customer_id`. Vì là LEFT JOIN, khách hàng không có đơn khớp vẫn được giữ.

**`AND o.order_status = 'PAID'` trong ON**

Chỉ những dòng đơn đã thanh toán mới được coi là dòng khớp. Đơn `CANCELLED` hoặc `PENDING` không tham gia vào số lượng và tổng tiền.

**`WHERE c.active_flag = 'Y'`**

Loại khách không hoạt động khỏi tập đầu vào. `Chi` bị loại, dù có đơn PAID trị giá 500.

**`GROUP BY c.customer_id, c.customer_name`**

Gộp những dòng sau JOIN thành một nhóm cho mỗi khách hàng. Hai cột không nằm trong hàm aggregate được đưa vào GROUP BY.

**`COUNT(o.order_id)`**

Đếm số đơn khớp. Dùng cột ở bảng phải có giá trị NULL khi không có đơn, nên khách `Dung` được đếm là 0.

**`NVL(SUM(o.amount), 0)`**

`SUM` trên nhóm không có giá trị đơn hàng trả NULL. `NVL` đổi NULL thành số 0 để báo cáo thể hiện đúng yêu cầu.

**`ORDER BY paid_total DESC, c.customer_id ASC`**

Xếp tổng tiền lớn trước; khi tổng bằng nhau, dùng customer ID tăng dần để thứ tự ổn định và dự đoán được.

### 7.2. Tự tính kết quả bằng tay

Trước tiên xét các khách hàng hoạt động: `An`, `Binh` và `Dung`. Sau đó nối chỉ các đơn PAID:

| Khách | Các dòng PAID khớp | COUNT(order_id) | SUM(amount) | Sau NVL |
|---|---|---:|---:|---:|
| An | 101 / 120 | 1 | 120 | 120 |
| Binh | 103 / 200; 104 / 200 | 2 | 400 | 400 |
| Dung | Không có | 0 | NULL | 0 |

Kết quả cuối theo thứ tự:

| CUSTOMER_ID | CUSTOMER_NAME | PAID_ORDER_COUNT | PAID_TOTAL |
|---:|---|---:|---:|
| 2 | Binh | 2 | 400 |
| 1 | An | 1 | 120 |
| 4 | Dung | 0 | 0 |

Nếu Oracle trả kết quả khác, hãy kiểm tra lần lượt dữ liệu nguồn, điều kiện JOIN, predicate trong ON, WHERE, GROUP BY và hàm aggregate. Không sửa SQL ngay khi chưa biết **dòng nào được thêm hoặc bị loại**.

## 8. COUNT(*), COUNT(column), SUM và NULL

Đây là điểm thường làm truy vấn LEFT JOIN đếm sai.

### 8.1. COUNT(*) khác COUNT(o.order_id)

Chạy:

~~~sql
SELECT
    c.customer_id,
    COUNT(*) AS row_count,
    COUNT(o.order_id) AS paid_order_count
FROM lab_customer c
LEFT JOIN lab_order o
  ON o.customer_id = c.customer_id
 AND o.order_status = 'PAID'
WHERE c.active_flag = 'Y'
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

Kết quả mong đợi:

| CUSTOMER_ID | ROW_COUNT | PAID_ORDER_COUNT |
|---:|---:|---:|
| 1 | 1 | 1 |
| 2 | 2 | 2 |
| 4 | 1 | 0 |

Với `Dung`, LEFT JOIN vẫn tạo **một dòng kết quả mở rộng**: các cột khách có giá trị, cột đơn hàng là NULL. Do đó `COUNT(*)` đếm dòng mở rộng này thành 1. `COUNT(o.order_id)` chỉ đếm những giá trị order_id khác NULL, nên bằng 0.

Nếu dùng `COUNT(*)` trong truy vấn báo cáo chính, Dung sẽ bị đếm thành **một đơn PAID**, sai yêu cầu. Đây là lý do phải hiểu aggregate hoạt động trên tập dòng sau JOIN như thế nào.

### 8.2. COUNT(column) bỏ qua NULL

`COUNT(expr)` đếm những dòng mà biểu thức `expr` không NULL. `COUNT(*)` đếm dòng bất kể các cột có NULL hay không.

Ví dụ:

~~~sql
SELECT
    COUNT(*) AS all_rows,
    COUNT(email) AS rows_with_email
FROM lab_customer;
~~~

Trong dataset hiện tại, `EMAIL` chưa được tạo nên câu query trên không áp dụng nguyên văn cho bảng lab đã định nghĩa. Nếu mở rộng bảng có cột `EMAIL` nullable, hãy hiểu rằng `COUNT(email)` chỉ đếm các khách có email khác NULL. Cột được đếm phải tồn tại trong schema thực tế.

### 8.3. SUM trên tập rỗng

`SUM(amount)` cộng các giá trị khác NULL. Khi nhóm không có giá trị nào để cộng, kết quả là NULL; `NVL(SUM(...), 0)` đổi thành 0 theo yêu cầu hiển thị/tính toán.

Không phải lúc nào NULL cũng đồng nghĩa 0. Ví dụ “chưa có dữ liệu đo” khác “đã đo và kết quả bằng 0”. Chỉ dùng `NVL` khi nghiệp vụ xác nhận hai trạng thái được phép hiển thị như nhau trong ngữ cảnh đó.

## 9. GROUP BY và HAVING: lọc nhóm khác lọc dòng

`WHERE` lọc **dòng trước khi nhóm**. `HAVING` lọc **nhóm sau khi GROUP BY**.

Ví dụ chỉ muốn khách đang hoạt động có ít nhất hai đơn PAID:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count,
    SUM(o.amount) AS paid_total
FROM lab_customer c
JOIN lab_order o
  ON o.customer_id = c.customer_id
 AND o.order_status = 'PAID'
WHERE c.active_flag = 'Y'
GROUP BY c.customer_id, c.customer_name
HAVING COUNT(o.order_id) >= 2
ORDER BY paid_total DESC;
~~~

Kết quả chỉ có `Binh` với hai đơn và tổng 400. Ở ví dụ này dùng INNER JOIN vì chỉ quan tâm nhóm có ít nhất hai đơn PAID; khách không có đơn không thể đáp ứng HAVING.

So sánh:

| Mệnh đề | Thời điểm logic | Ví dụ |
|---|---|---|
| `WHERE` | Trước GROUP BY | Chỉ lấy khách active, chỉ lấy dữ liệu trong khoảng ngày |
| `HAVING` | Sau GROUP BY | Chỉ lấy khách có ít nhất hai đơn PAID |

Không viết `WHERE COUNT(o.order_id) >= 2` ở cùng query block vì aggregate không được dùng như điều kiện lọc dòng trước nhóm theo cách đó.

## 10. DISTINCT và giá trị trùng

Trong dataset, Binh có hai đơn cùng amount 200. Hai dòng này là **hai giao dịch khác nhau** vì order_id khác nhau.

~~~sql
SELECT DISTINCT amount
FROM lab_order
WHERE customer_id = 2
ORDER BY amount;
~~~

Kết quả chỉ có một dòng 200 vì DISTINCT loại các tổ hợp giá trị trùng nhau trong danh sách SELECT.

Nếu viết:

~~~sql
SELECT DISTINCT order_id, amount
FROM lab_order
WHERE customer_id = 2
ORDER BY order_id;
~~~

Kết quả vẫn có hai dòng vì `ORDER_ID` khác nhau. DISTINCT không phải “chỉ lấy một đơn cho mỗi khách” trừ khi tập cột được chọn và quy tắc dữ liệu tình cờ tạo ra kết quả như vậy.

**Không dùng DISTINCT để che lỗi JOIN.** Nếu một bảng danh mục có hai dòng khớp cho một khóa do thiếu unique constraint, JOIN có thể nhân đôi kết quả. Thêm DISTINCT đôi khi làm báo cáo nhìn có vẻ đúng nhưng không sửa nguyên nhân cardinality sai.

## 11. NULL và điều kiện lọc

Trong SQL, NULL biểu thị giá trị chưa biết/không có theo ngữ cảnh; nó không bằng 0, chuỗi rỗng theo mọi hệ quản trị, hay một giá trị cụ thể. Oracle coi chuỗi ký tự rỗng trong kiểu ký tự là NULL theo hành vi SQL hiện hành.

Không kiểm tra NULL bằng dấu bằng:

~~~sql
-- Sai ý định: phép so sánh với NULL không trả TRUE.
SELECT *
FROM lab_order
WHERE order_status = NULL;

-- Đúng:
SELECT *
FROM lab_order
WHERE order_status IS NULL;
~~~

Trong bảng lab, `ORDER_STATUS` được khai báo NOT NULL nên query thứ hai trả 0 dòng. Đây vẫn là cách viết đúng để tìm NULL trong một cột nullable khác.

### 11.1. Ba trạng thái logic

Điều kiện SQL có thể cho kết quả:

- **TRUE**: dòng được giữ bởi WHERE.
- **FALSE**: dòng bị loại.
- **UNKNOWN**: thường xuất hiện khi so sánh có NULL; dòng cũng không được giữ bởi WHERE.

Ví dụ:

~~~sql
SELECT
    CASE WHEN NULL = 1 THEN 'TRUE'
         WHEN NOT (NULL = 1) THEN 'FALSE'
         ELSE 'UNKNOWN'
    END AS comparison_result
FROM dual;
~~~

Kết quả là `UNKNOWN`. Vì vậy điều kiện `o.order_status = 'PAID'` ở WHERE loại dòng mở rộng NULL của LEFT JOIN, khiến khách không có đơn biến mất.

### 11.2. NVL, COALESCE và điều kiện NULL

`NVL(expr1, expr2)` trả `expr2` khi `expr1` là NULL. `COALESCE` trả biểu thức đầu tiên không NULL trong danh sách và hỗ trợ nhiều đối số:

~~~sql
SELECT
    NVL(NULL, 0) AS nvl_value,
    COALESCE(NULL, NULL, 0) AS coalesce_value
FROM dual;
~~~

Trong truy vấn báo cáo, `NVL(SUM(o.amount), 0)` phù hợp khi tổng không có đơn được quy ước hiển thị là 0. Với cột văn bản hoặc ngày, cần chọn giá trị thay thế cùng kiểu và có ý nghĩa nghiệp vụ.

## 12. Thứ tự xử lý logic của SELECT

Khi đọc truy vấn, nên hình dung thứ tự logic phổ biến:

~~~text
FROM / JOIN
      |
      v
ON
      |
      v
WHERE
      |
      v
GROUP BY
      |
      v
HAVING
      |
      v
SELECT
      |
      v
DISTINCT
      |
      v
ORDER BY
      |
      v
FETCH FIRST / OFFSET (nếu có)
~~~

Đây là **thứ tự logic để hiểu kết quả**, không phải cam kết optimizer thực thi vật lý đúng từng bước theo sơ đồ. Oracle có thể biến đổi truy vấn, đẩy predicate hoặc chọn join order khác nếu vẫn bảo toàn ngữ nghĩa. Khi học SELECT, thứ tự logic giúp giải thích vì sao:

- Alias trong SELECT thường không dùng được trong WHERE cùng query block.
- WHERE không lọc trực tiếp kết quả aggregate; HAVING làm việc đó.
- LEFT JOIN tạo dòng NULL trước khi WHERE có thể loại dòng đó.
- ORDER BY quyết định thứ tự cuối; nếu không có ORDER BY, không được giả định thứ tự kết quả.

## 13. ORDER BY: kết quả đúng nhưng thứ tự có thể không ổn định

Một truy vấn không có `ORDER BY` không bảo đảm dòng được trả theo thứ tự chèn, primary key hay thứ tự hiển thị trước đó:

~~~sql
SELECT order_id, amount
FROM lab_order;
~~~

Nếu cần thứ tự xác định:

~~~sql
SELECT order_id, amount
FROM lab_order
ORDER BY amount DESC, order_id ASC;
~~~

Khi hai dòng có cùng `AMOUNT`, `ORDER_ID` làm tiêu chí phụ để quyết định thứ tự. Nếu chỉ viết `ORDER BY amount DESC`, thứ tự giữa các dòng cùng số tiền không được bảo đảm.

Trong truy vấn chính, `ORDER BY paid_total DESC, customer_id ASC` làm thứ tự dự đoán được. Đây là điều cần thiết khi đối chiếu kết quả bằng tay hoặc viết kiểm thử tự động.

## 14. FETCH FIRST và giới hạn số dòng trong Oracle

Oracle hỗ trợ cú pháp giới hạn số dòng:

~~~sql
SELECT order_id, customer_id, amount
FROM lab_order
ORDER BY amount DESC, order_id
FETCH FIRST 3 ROWS ONLY;
~~~

Với dataset hiện tại, ba dòng đầu theo amount giảm dần là đơn 105 (500), 103 (200) và 104 (200). `ORDER_ID` làm tiêu chí phụ bảo đảm thứ tự giữa hai dòng cùng 200.

| ORDER_ID | AMOUNT |
|---:|---:|
| 105 | 500 |
| 103 | 200 |
| 104 | 200 |

Không dùng `ROWNUM` như thể nó luôn áp dụng sau ORDER BY cùng query block. Với cách viết cũ dùng ROWNUM, cần hiểu thứ tự chọn dòng và sắp xếp; cú pháp `FETCH FIRST` thường rõ ràng hơn cho bài toán giới hạn kết quả.

Nếu phân trang với `OFFSET ... FETCH NEXT ...`, cần ORDER BY ổn định. Khi dữ liệu thay đổi giữa các lần đọc trang, ứng dụng vẫn cần chính sách nhất quán phù hợp; offset không tự tạo snapshot nghiệp vụ cho toàn bộ quá trình phân trang.

## 15. Kiểm chứng kết quả theo nhiều lớp

Không nên chỉ chạy câu SELECT một lần rồi kết luận “trông có vẻ đúng”. Một quy trình kiểm chứng dễ lặp lại gồm các bước:

1. **Xác nhận dataset:** số dòng, khóa, trạng thái và quan hệ nguồn đúng như giả định.
2. **Dự đoán thủ công:** ghi rõ dòng nào phải xuất hiện, dòng nào phải bị loại.
3. **Chạy truy vấn:** giữ nguyên SQL và dữ liệu đã chuẩn bị.
4. **Đối chiếu số lượng:** số dòng và giá trị aggregate có đúng không?
5. **Thử biến thể có chủ đích:** đổi LEFT JOIN thành JOIN, chuyển predicate ON sang WHERE, thay COUNT(column) bằng COUNT(*).
6. **Kiểm tra kết quả mong đợi bằng SQL độc lập:** so sánh tập kết quả thực tế với tập expected.

### 15.1. Kiểm tra số lượng nguồn

~~~sql
SELECT COUNT(*) AS customer_rows
FROM lab_customer;

SELECT COUNT(*) AS order_rows
FROM lab_order;

SELECT active_flag, COUNT(*) AS customer_count
FROM lab_customer
GROUP BY active_flag
ORDER BY active_flag;

SELECT order_status, COUNT(*) AS order_count
FROM lab_order
GROUP BY order_status
ORDER BY order_status;
~~~

Kết quả kỳ vọng:

| Kiểm tra | Kết quả |
|---|---:|
| Tổng khách hàng | 4 |
| Tổng đơn hàng | 5 |
| Khách active Y | 3 |
| Khách active N | 1 |
| Đơn PAID | 4 |
| Đơn CANCELLED | 1 |

Nếu dữ liệu nguồn không đúng, không nên dùng output của truy vấn chính để kết luận lỗi nằm ở SELECT. Có thể script seed đã chạy nhiều lần, dữ liệu lab đã bị thay đổi hoặc kết nối nhầm schema/PDB.

### 15.2. Kiểm tra từng nhóm trước aggregate

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.amount
FROM lab_customer c
LEFT JOIN lab_order o
  ON o.customer_id = c.customer_id
 AND o.order_status = 'PAID'
WHERE c.active_flag = 'Y'
ORDER BY c.customer_id, o.order_id;
~~~

Hãy kiểm tra tập dòng trung gian này trước khi thêm `GROUP BY`. Nếu dòng `Dung` không còn, lỗi đã xuất hiện trước aggregate. Nếu An có cả đơn CANCELLED, điều kiện status trong ON chưa đúng hoặc đang dùng một truy vấn khác.

### 15.3. Đối chiếu với kết quả kỳ vọng bằng MINUS

Oracle có toán tử tập hợp `MINUS`, trả các dòng xuất hiện trong tập bên trái nhưng không có trong tập bên phải. Ta có thể khai báo tập kết quả kỳ vọng và tập kết quả thực tế, rồi so sánh hai chiều.

~~~sql
WITH expected AS (
    SELECT 2 AS customer_id,
           'Binh' AS customer_name,
           2 AS paid_order_count,
           400 AS paid_total
    FROM dual
    UNION ALL
    SELECT 1, 'An', 1, 120 FROM dual
    UNION ALL
    SELECT 4, 'Dung', 0, 0 FROM dual
),
actual AS (
    SELECT
        c.customer_id,
        c.customer_name,
        COUNT(o.order_id) AS paid_order_count,
        NVL(SUM(o.amount), 0) AS paid_total
    FROM lab_customer c
    LEFT JOIN lab_order o
      ON o.customer_id = c.customer_id
     AND o.order_status = 'PAID'
    WHERE c.active_flag = 'Y'
    GROUP BY c.customer_id, c.customer_name
)
SELECT 'EXPECTED_NOT_ACTUAL' AS difference,
       customer_id, customer_name,
       paid_order_count, paid_total
FROM (
    SELECT * FROM expected
    MINUS
    SELECT * FROM actual
)
UNION ALL
SELECT 'ACTUAL_NOT_EXPECTED',
       customer_id, customer_name,
       paid_order_count, paid_total
FROM (
    SELECT * FROM actual
    MINUS
    SELECT * FROM expected
)
ORDER BY difference, customer_id;
~~~

Nếu không có dòng nào, hai tập kết quả **bằng nhau theo các cột đã chọn**. Nếu xuất hiện `EXPECTED_NOT_ACTUAL`, dòng kỳ vọng đang thiếu hoặc giá trị không khớp trong actual. Nếu xuất hiện `ACTUAL_NOT_EXPECTED`, truy vấn trả thêm dòng hoặc giá trị khác mong đợi.

`MINUS` là phép toán tập hợp có ngữ nghĩa loại trùng; nếu bài toán yêu cầu so sánh **multiset** và đếm cả số lần xuất hiện, cần kiểm tra thêm số lượng mỗi tổ hợp bằng `GROUP BY`/`COUNT(*)`. Trong ví dụ, khóa `CUSTOMER_ID` bảo đảm một dòng cho mỗi khách trong kết quả aggregate nên so sánh này đủ cho mục tiêu.

### 15.4. Kiểm tra từng giá trị thay vì chỉ tổng cuối

Một tổng tiền đúng chưa chắc mọi dòng đúng. Ví dụ một đơn bị bỏ sót và một đơn khác bị đếm lặp với giá bằng nhau có thể tạo ra tổng gần giống hoặc thậm chí trùng nhau. Vì vậy:

- Kiểm tra **danh sách order_id** trước khi cộng tiền.
- Kiểm tra **số lượng đơn** độc lập với tổng tiền.
- Đối chiếu từng dòng khi có thể.
- Dùng khóa ổn định trong ORDER BY và kết quả kiểm thử.

Kiểm chứng tốt thường kết hợp **tập dòng trung gian**, **aggregate**, và **đối chiếu tập kết quả cuối**.

## 16. Dùng dữ liệu tối thiểu để phát hiện các lỗi SQL thường gặp

### Lỗi 1: INNER JOIN làm mất khách không có đơn

**Dấu hiệu:** Dung không xuất hiện dù yêu cầu muốn giữ khách chưa có đơn.

**Nguyên nhân:** Dùng `JOIN` thay cho `LEFT JOIN`.

**Cách sửa:** Đổi loại JOIN, đặt điều kiện trạng thái bên phải trong ON và kiểm tra cột NULL mở rộng.

### Lỗi 2: Predicate ở WHERE làm mất dòng NULL của LEFT JOIN

**Dấu hiệu:** LEFT JOIN có trong SQL nhưng khách không có đơn vẫn biến mất.

**Nguyên nhân:** Viết `WHERE o.order_status = 'PAID'`.

**Cách sửa:** Chuyển predicate xác định đơn khớp vào ON nếu yêu cầu là giữ khách không có đơn phù hợp.

### Lỗi 3: Dùng COUNT(*) để đếm bản ghi con

**Dấu hiệu:** Khách không có đơn được đếm thành 1.

**Nguyên nhân:** COUNT(*) đếm dòng LEFT JOIN mở rộng.

**Cách sửa:** Dùng `COUNT(o.order_id)` hoặc một khóa con NOT NULL.

### Lỗi 4: JOIN nhân số tiền

**Dấu hiệu:** Tổng tiền tăng gấp đôi hoặc nhiều lần sau khi nối thêm bảng.

**Nguyên nhân:** Quan hệ 1:N hoặc N:M tạo nhiều dòng trung gian; aggregate được tính sau khi nhân dòng.

**Cách sửa:** Xác định grain của từng bảng và cardinality của JOIN. Nếu nối thêm bảng chi tiết khác, có thể cần aggregate từng phía trong CTE/subquery trước khi nối.

Ví dụ, nếu mỗi đơn có nhiều dòng sản phẩm và nhiều lần thanh toán, nối thẳng ORDER_ITEM với PAYMENT có thể tạo tích giữa hai tập con. Tổng tiền hàng và tổng tiền thanh toán phải được tính ở đúng grain trước khi kết hợp.

### Lỗi 5: Dùng DISTINCT để sửa JOIN

**Dấu hiệu:** Số dòng nhìn giảm nhưng tổng aggregate hoặc dữ liệu chi tiết sai.

**Nguyên nhân:** DISTINCT xóa những tổ hợp cột trùng, không sửa quan hệ bị nhân dòng.

**Cách sửa:** Kiểm tra khóa nối, unique constraint và mức chi tiết; sửa mô hình truy vấn.

### Lỗi 6: Không có ORDER BY nhưng mong kết quả luôn cùng thứ tự

**Dấu hiệu:** Lần chạy này An đứng trước, lần khác Binh đứng trước.

**Nguyên nhân:** SQL không bảo đảm thứ tự khi thiếu ORDER BY.

**Cách sửa:** Thêm cột sắp xếp và tiêu chí phụ đủ xác định thứ tự.

### Lỗi 7: Lọc aggregate bằng WHERE

**Dấu hiệu:** Oracle báo lỗi khi dùng COUNT/SUM trong WHERE cùng query block.

**Nguyên nhân:** WHERE lọc dòng trước GROUP BY.

**Cách sửa:** Dùng HAVING cho điều kiện trên nhóm.

## 17. Khi truy vấn đúng logic nhưng chạy chậm

**Kiểm chứng kết quả** và **đánh giá hiệu năng** là hai việc khác nhau. Trên dataset năm dòng, một truy vấn full table scan có thể là lựa chọn tối ưu; không nên tạo index chỉ để làm plan trông phức tạp.

Khi dữ liệu lớn, có thể xem execution plan:

~~~sql
EXPLAIN PLAN FOR
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_order_count,
    NVL(SUM(o.amount), 0) AS paid_total
FROM lab_customer c
LEFT JOIN lab_order o
  ON o.customer_id = c.customer_id
 AND o.order_status = 'PAID'
WHERE c.active_flag = 'Y'
GROUP BY c.customer_id, c.customer_name
ORDER BY paid_total DESC, c.customer_id;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

`EXPLAIN PLAN` thể hiện kế hoạch ước lượng theo môi trường phân tích, không tự chứng minh kết quả đúng hoặc cho số liệu runtime của lần thực thi. Khi có quyền và đã chạy truy vấn, `DBMS_XPLAN.DISPLAY_CURSOR` có thể cho thông tin cursor thực tế, nhất là khi thu thập runtime statistics phù hợp.

Một số câu hỏi hiệu năng:

- Predicate trên bảng lớn có chọn lọc không?
- Cột join có index phù hợp và thống kê đủ không?
- Truy vấn có đọc nhiều dòng hơn yêu cầu không?
- Có chuyển kiểu ngầm định trên cột join/filter không?
- Có join sai cardinality làm nhân dòng và tăng aggregate?
- Có thể lọc hoặc aggregate trước khi nối để giảm tập trung gian không?

**Không thay đổi truy vấn đúng chỉ để ép một plan cụ thể** nếu chưa hiểu workload, statistics và chi phí thực tế. Dữ liệu tối thiểu chủ yếu giúp kiểm chứng logic; đánh giá hiệu năng cần dữ liệu và môi trường đại diện.

## 18. Tái tạo bài kiểm chứng trong môi trường khác

Một ví dụ SQL chỉ thực sự hữu ích khi người khác có thể chạy lại. Nên đóng gói:

~~~text
select-lab/
├── 01_create_tables.sql
├── 02_insert_minimal_data.sql
├── 03_verify_source_data.sql
├── 04_query_steps.sql
├── 05_expected_results.md
└── README.md
~~~

Mỗi file có mục đích:

- `01_create_tables.sql`: DDL tạo bảng và constraint.
- `02_insert_minimal_data.sql`: DML chèn dataset tối thiểu, kèm `COMMIT`.
- `03_verify_source_data.sql`: kiểm tra số dòng, khóa và phân bố trạng thái.
- `04_query_steps.sql`: truy vấn đơn bảng, JOIN, LEFT JOIN và truy vấn tổng hợp.
- `05_expected_results.md`: kết quả dự kiến, giải thích dòng được giữ/bị loại.
- `README.md`: phiên bản Oracle cần thiết, PDB/service, schema và cách chạy theo thứ tự.

Không lưu password trong các file này. Dùng tài khoản lab có quyền tối thiểu và kết nối tới PDB đúng. Với môi trường CI, tạo schema/database thử nghiệm riêng và dọn bằng quy trình được kiểm soát.

### 18.1. Script seed có chạy lại an toàn không?

Các câu INSERT trực tiếp trong phần 3 chỉ dành cho lần tạo mới. Nếu chạy lại, primary key trùng sẽ làm script báo lỗi. Có thể:

- Dùng database/schema lab mới cho mỗi lượt thử.
- Dùng script reset riêng sau khi chắc chắn dữ liệu lab không cần giữ.
- Viết seed idempotent với MERGE hoặc kiểm tra dữ liệu đã tồn tại theo business key.

Không tự động đặt `DROP TABLE` hoặc `TRUNCATE TABLE` ở đầu một script dùng chung nếu người chạy có thể đang trỏ nhầm schema/PDB. Việc reset phải hiển thị rõ phạm vi và yêu cầu xác nhận phù hợp.

## 19. Bài tập tự kiểm tra

### Bài 1 — Dự đoán INNER JOIN

Với dataset ban đầu, chạy:

~~~sql
SELECT c.customer_name, o.order_id
FROM lab_customer c
JOIN lab_order o
  ON o.customer_id = c.customer_id
ORDER BY c.customer_id, o.order_id;
~~~

**Câu hỏi:** Có bao nhiêu dòng? Khách nào không xuất hiện và tại sao?

**Đáp án định hướng:** Có 5 dòng; Dung không xuất hiện vì không có đơn. Chi xuất hiện vì có đơn, dù inactive; truy vấn chưa lọc active flag.

### Bài 2 — Đổi vị trí predicate

Chạy hai câu sau và ghi lại số dòng:

~~~sql
-- A
SELECT c.customer_id, o.order_id
FROM lab_customer c
LEFT JOIN lab_order o
  ON o.customer_id = c.customer_id
 AND o.order_status = 'PAID'
WHERE c.active_flag = 'Y';

-- B
SELECT c.customer_id, o.order_id
FROM lab_customer c
LEFT JOIN lab_order o
  ON o.customer_id = c.customer_id
WHERE c.active_flag = 'Y'
  AND o.order_status = 'PAID';
~~~

**Câu hỏi:** Vì sao A có dòng Dung nhưng B không có?

**Đáp án định hướng:** A chỉ giới hạn dòng bên phải được coi là khớp; B lọc sau join và loại dòng NULL mở rộng vì phép so sánh không TRUE.

### Bài 3 — COUNT

~~~sql
SELECT
  c.customer_name,
  COUNT(*) AS count_star,
  COUNT(o.order_id) AS count_order
FROM lab_customer c
LEFT JOIN lab_order o
  ON o.customer_id = c.customer_id
 AND o.order_status = 'PAID'
WHERE c.active_flag = 'Y'
GROUP BY c.customer_name
ORDER BY c.customer_name;
~~~

**Câu hỏi:** Vì sao Dung có `COUNT_STAR = 1` nhưng `COUNT_ORDER = 0`?

**Đáp án định hướng:** Dòng LEFT JOIN mở rộng vẫn tồn tại; cột order_id là NULL nên COUNT(order_id) bỏ qua.

### Bài 4 — Thêm một khách hàng không có đơn

~~~sql
INSERT INTO lab_customer
    (customer_id, customer_name, active_flag)
VALUES
    (5, 'Ha', 'Y');
COMMIT;
~~~

Chạy lại truy vấn chính. Hãy dự đoán Ha xuất hiện với bao nhiêu đơn và tổng tiền là bao nhiêu.

**Đáp án định hướng:** Ha có 0 đơn PAID và tổng 0, tương tự Dung. Nếu không xuất hiện, hãy xem loại JOIN và predicate trạng thái.

### Bài 5 — Thêm đơn PENDING

~~~sql
INSERT INTO lab_order
    (order_id, customer_id, order_status, amount)
VALUES
    (106, 4, 'PENDING', 700);
COMMIT;
~~~

**Câu hỏi:** Kết quả truy vấn chính của Dung có thay đổi không?

**Đáp án định hướng:** Không. Điều kiện status trong ON chỉ cho PAID khớp; PENDING không được tính. Dung vẫn có 0 đơn PAID và tổng 0.

### Bài 6 — Lỗi nhân dòng

Tưởng tượng bảng `LAB_ORDER_TAG` có nhiều tag cho mỗi đơn. Nếu nối ORDER với ORDER_TAG trước khi SUM amount, tổng tiền có thể bị nhân theo số tag. Hãy tạo một đơn có hai tag và kiểm tra số dòng trung gian.

**Câu hỏi:** Cách nào để tránh cộng lặp tiền đơn hàng?

**Đáp án định hướng:** Xác định grain; aggregate tag riêng hoặc tổng hợp order ở cấp đơn trước khi nối với tập tag, tùy mục tiêu báo cáo. Không chữa bằng DISTINCT sau khi tổng đã bị nhân.

### Bài 7 — Đối chiếu bằng MINUS

Thay một giá trị expected trong phần 15.3, ví dụ tổng của Binh từ 400 thành 390. Chạy truy vấn so sánh hai chiều.

**Câu hỏi:** Vì sao phải có cả `EXPECTED_NOT_ACTUAL` và `ACTUAL_NOT_EXPECTED`?

**Đáp án định hướng:** Một chiều phát hiện dòng kỳ vọng bị thiếu/sai; chiều còn lại phát hiện dòng thừa hoặc giá trị ngoài mong đợi.

## 20. Quy trình giải thích một SELECT bất kỳ

Khi nhận một truy vấn mới, hãy áp dụng trình tự sau:

1. **Viết lại yêu cầu bằng ngôn ngữ nghiệp vụ:** kết quả cần có một dòng cho entity nào, và những trường hợp nào phải giữ?
2. **Xác định grain của bảng nguồn:** mỗi dòng là khách hàng, đơn hàng, hay dòng chi tiết?
3. **Liệt kê khóa nối:** JOIN dựa trên PK/FK nào; cardinality là 1:1, 1:N hay N:M?
4. **Tạo dataset nhỏ có chủ đích:** ít nhất một trường hợp khớp, không khớp, nhiều dòng con và NULL nếu truy vấn có liên quan.
5. **Đọc từng predicate:** điều kiện nằm trong ON hay WHERE, có loại dòng mở rộng không?
6. **Tính aggregate theo nhóm:** COUNT đang đếm dòng nào, SUM có thể NULL không, có bị nhân dòng không?
7. **Xác định thứ tự và giới hạn:** ORDER BY có đủ khóa phụ chưa, FETCH FIRST đang giới hạn kết quả nào?
8. **Đối chiếu output:** so sánh dòng thực tế với expected, dùng MINUS hoặc phương pháp kiểm thử tương đương.
9. **Sau khi logic đúng mới xem hiệu năng:** execution plan, index, statistics, số dòng thực tế và network fetch.

Sơ đồ:

~~~text
YÊU CẦU NGHIỆP VỤ
       |
       v
XÁC ĐỊNH GRAIN VÀ QUAN HỆ
       |
       v
TẠO DỮ LIỆU TỐI THIỂU
       |
       v
GIẢI THÍCH FROM / JOIN / ON / WHERE
       |
       v
GROUP BY / HAVING / AGGREGATE
       |
       v
ORDER BY / FETCH
       |
       v
DỰ ĐOÁN KẾT QUẢ BẰNG TAY
       |
       v
CHẠY SQL VÀ ĐỐI CHIẾU
       |
       v
LOGIC ĐÚNG? ── Không ──▶ Tìm dòng sai và nguyên nhân
       |
      Có
       |
       v
ĐÁNH GIÁ HIỆU NĂNG TRÊN DỮ LIỆU ĐẠI DIỆN
~~~

Một truy vấn được hiểu chắc khi ta có thể **giải thích vì sao từng dòng xuất hiện hoặc không xuất hiện**, dự đoán được số dòng và giá trị đầu ra, rồi chứng minh dự đoán bằng một bộ dữ liệu tối thiểu. Với Oracle SQL, cách học này đặc biệt hữu ích cho JOIN, LEFT JOIN, NULL và aggregate: chỉ cần vài dòng được chọn đúng, ta có thể nhìn thấy những khác biệt mà một bảng dữ liệu lớn thường che khuất.
