# Thiết kế dữ liệu kiểm thử nhỏ nhưng phân biệt được lỗi

Một truy vấn SQL có thể chạy thành công nhưng vẫn trả sai kết quả. Ví dụ, báo cáo doanh thu tháng dùng LEFT JOIN nhưng đặt điều kiện trạng thái đơn trong WHERE, khiến khách hàng chưa có đơn biến mất. Một truy vấn khác JOIN orders với order_items rồi SUM lại số tiền đơn hàng, làm tổng tiền bị nhân lên theo số dòng chi tiết. Nếu bộ dữ liệu thử chỉ có một khách, một đơn và một dòng hàng, cả hai lỗi có thể không bao giờ lộ ra.

Thiết kế dữ liệu kiểm thử tốt không phải là tạo thật nhiều bản ghi. Mục tiêu là tạo **một tập nhỏ có chủ đích**, trong đó mỗi bản ghi hoặc cặp bản ghi phân biệt được một hành vi đúng với một lỗi có thể xảy ra. Một bộ dữ liệu nhỏ nhưng có khách không có đơn, khách có nhiều đơn, trạng thái khác nhau, giá trị NULL, số tiền 0, ngày đúng ranh giới và đơn có nhiều dòng chi tiết thường phát hiện được nhiều lỗi hơn hàng nghìn dòng ngẫu nhiên.

Bài **“Thiết kế dữ liệu kiểm thử nhỏ nhưng phân biệt được lỗi”** thuộc chương **Kiểm thử và gỡ lỗi**, module **Database SQL**. Bài dùng một bộ dữ liệu mẫu cho customers, orders và order_items để xây dựng các ca kiểm thử phân biệt lỗi JOIN, LEFT JOIN, COUNT, SUM, lọc ngày, NULL, NOT IN, ràng buộc và transaction. Trọng tâm là cách suy ra dữ liệu từ hợp đồng truy vấn, cách xác định kết quả kỳ vọng, và cách giữ test độc lập, lặp lại được.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích vì sao dữ liệu kiểm thử phải được thiết kế theo **lỗi cần phát hiện**, không chỉ theo số lượng.
2. Chuyển yêu cầu nghiệp vụ và hợp đồng truy vấn thành các điều kiện dữ liệu cần có.
3. Tạo **minimal counterexample**: tập bản ghi nhỏ nhất làm lộ một lỗi cụ thể.
4. Dùng cặp đối chứng để phân biệt hai cách triển khai gần giống nhau.
5. Thiết kế fixture có NULL, zero, duplicate, missing relationship, nhiều hàng liên quan và boundary.
6. Phát hiện lỗi INNER/LEFT JOIN, điều kiện ON/WHERE, COUNT(*), COUNT(column), SUM và fan-out.
7. Kiểm thử khoảng thời gian bằng khoảng nửa mở và dữ liệu đúng sát biên.
8. Phân biệt NOT IN với NOT EXISTS khi subquery có NULL.
9. Kiểm tra constraint, khóa ngoại, uniqueness và hành vi transaction.
10. Viết assertion so sánh kết quả thực tế với expected result, kể cả số lượng và duplicate.
11. Làm cho test độc lập, deterministic, có thể chạy lại và không phụ thuộc thứ tự.
12. Chọn dữ liệu nhỏ phù hợp cho unit test, integration test, regression test và kiểm thử hiệu năng.

## 2. Dữ liệu kiểm thử nhỏ nhưng phân biệt được lỗi là gì?

Một tập fixture tốt có hai đặc tính:

- **Nhỏ:** đủ dễ đọc, hiểu và dự đoán kết quả bằng tay.
- **Phân biệt được lỗi:** mỗi trường hợp quan trọng làm cho cách đúng và ít nhất một cách sai cho kết quả khác nhau.

Ví dụ, nếu muốn kiểm tra truy vấn lấy khách hàng chưa có đơn, một bộ dữ liệu chỉ có khách đã có đơn là vô ích. Truy vấn INNER JOIN sai và LEFT JOIN đúng có thể cùng trả kết quả giống nhau vì không có hàng nào buộc chúng phải khác nhau.

### 2.1. Fixture phải được thiết kế từ câu hỏi

Hãy bắt đầu bằng câu hỏi:

> Truy vấn hoặc logic SQL cần đúng điều gì, và một lỗi thường gặp sẽ làm kết quả sai ra sao?

Ví dụ yêu cầu:

“Liệt kê tất cả khách hàng ACTIVE cùng số đơn PAID và tổng tiền PAID trong tháng 1 năm 2026. Khách chưa có đơn PAID vẫn phải xuất hiện với số đơn và tổng tiền bằng 0.”

Từ hợp đồng này, ta suy ra các trường hợp phải có:

| Trường hợp cần phân biệt | Vì sao cần dữ liệu đó? |
| --- | --- |
| Khách có hai đơn PAID | Phát hiện chỉ lấy một đơn hoặc đếm sai |
| Khách có đơn NEW | Phát hiện quên lọc trạng thái |
| Khách có đơn CANCELLED | Phát hiện tính cả đơn hủy |
| Khách chưa có đơn | Phân biệt LEFT JOIN với INNER JOIN |
| Khách INACTIVE có đơn | Phân biệt lọc khách ACTIVE |
| Đơn có amount = 0 | Phát hiện nhầm zero với NULL/không có hàng |
| Đơn đúng ngày bắt đầu | Kiểm tra biên đầu |
| Đơn đúng ngày kết thúc | Kiểm tra khoảng thời gian nửa mở |
| Một đơn có nhiều order_items | Phát hiện fan-out khi JOIN nhiều bảng |
| Hai đơn có cùng amount | Phát hiện SUM(DISTINCT amount) sai |

Đây là **danh sách điều kiện dữ liệu**, không phải danh sách phải tạo hàng trăm bản ghi. Một hàng có thể đồng thời kiểm tra nhiều điều kiện, miễn là ta vẫn hiểu được tác dụng của nó.

### 2.2. Mỗi hàng nên có lý do tồn tại

Một fixture dễ review thường có bảng giải thích:

| Bản ghi | Đặc điểm | Lỗi có thể phát hiện |
| --- | --- | --- |
| Customer 1 | ACTIVE, nhiều đơn | COUNT/SUM nhiều đơn |
| Customer 2 | ACTIVE, đơn cùng amount và một đơn ở boundary | SUM(DISTINCT amount), lọc ngày |
| Customer 3 | INACTIVE, chỉ có đơn CANCELLED | Lọc trạng thái khách và đơn |
| Customer 4 | ACTIVE, không có đơn, email NULL | LEFT JOIN, COUNT, NULL |
| Order 101 | Có hai dòng chi tiết | Fan-out |
| Order 103 | Amount 0, đúng thời điểm kết thúc | Zero và boundary |

Nếu không thể giải thích một hàng giúp phát hiện điều gì, có thể hàng đó chưa cần thiết trong fixture tối thiểu.

### 2.3. Dùng minimal counterexample

**Minimal counterexample** là tập dữ liệu nhỏ nhất chứng minh một cách triển khai sai.

Ví dụ để chứng minh COUNT(*) sai khi LEFT JOIN:

~~~text
customers
id
1

orders
order_id | customer_id
(không có hàng)
~~~

Kết quả:

- COUNT(*) = 1 vì LEFT JOIN tạo một hàng với các cột orders NULL.
- COUNT(order_id) = 0 vì order_id NULL không được COUNT.

Chỉ cần **một khách và không có đơn** là đủ phân biệt hai cách đếm. Không cần tạo 100 khách.

### 2.4. Cặp đối chứng

Cặp đối chứng là hai bản ghi chỉ khác một đặc điểm quan trọng, để test chứng minh điều kiện lọc hoạt động:

~~~text
order A: status = 'PAID'
order B: status = 'CANCELLED'
~~~

Nếu truy vấn doanh thu chỉ tính PAID, A phải được tính còn B phải bị loại. Nếu cả hai cùng xuất hiện hoặc cùng bị loại, ta có tín hiệu rõ ràng về lỗi.

### 2.5. Tách test độc lập khi cần

Một hàng có thể vừa kiểm tra trạng thái, ngày, NULL và amount. Tuy nhiên, nếu assertion thất bại, ta có thể không biết điều kiện nào gây lỗi. Khi test phức tạp:

- Giữ fixture tích hợp nhỏ cho truy vấn end-to-end.
- Thêm fixture riêng cho boundary đặc biệt.
- Tạo một test nhỏ cho mỗi lỗi logic quan trọng.

Không cần một bộ dữ liệu khổng lồ để mọi test đều dùng chung.

## 3. Quy trình thiết kế fixture

~~~text
Yêu cầu / hợp đồng SQL
          |
          v
Liệt kê điều kiện phải đúng
          |
          v
Liệt kê lỗi có thể xảy ra
          |
          v
Chọn dữ liệu phân biệt đúng và sai
          |
          v
Tạo fixture nhỏ, có khóa ổn định
          |
          v
Tính expected result độc lập
          |
          v
Chạy query và assertion
          |
          v
ROLLBACK / cleanup / chạy lại
~~~

### 3.1. Viết hợp đồng trước khi viết INSERT

Không nên bắt đầu bằng việc nghĩ “mình cần 20 dòng dữ liệu”. Hãy viết câu mô tả kết quả:

- Tập khách nào được đưa vào?
- Trạng thái đơn nào được tính?
- Khoảng thời gian đóng hay mở ở mỗi đầu?
- Khách không có đơn có xuất hiện không?
- NULL được xử lý thế nào?
- Nếu có nhiều dòng chi tiết, tổng cần tính ở cấp đơn hay cấp dòng?
- Thứ tự kết quả có phải một phần của hợp đồng không?

Nếu các câu này chưa rõ, dữ liệu test chưa thể có expected result đáng tin.

### 3.2. Liệt kê lỗi trước rồi tìm phản ví dụ

| Lỗi giả định | Dữ liệu tối thiểu cần có |
| --- | --- |
| INNER JOIN thay cho LEFT JOIN | Một khách không có đơn |
| Điều kiện trạng thái đặt ở WHERE làm mất khách không có đơn | Một khách không có đơn và một đơn không phù hợp |
| COUNT(*) thay cho COUNT(order_id) | Hàng LEFT JOIN không có đơn |
| Quên lọc CANCELLED | Một đơn CANCELLED có amount dương |
| Quên lọc NEW | Một đơn NEW có amount dương |
| Khoảng ngày dùng <= ngày kết thúc | Một đơn đúng lúc boundary kết thúc |
| JOIN order_items rồi SUM order.amount | Một đơn có hai dòng chi tiết |
| SUM(DISTINCT order.amount) | Hai đơn hợp lệ có cùng amount |
| Dùng NOT IN với tập có NULL | Subquery trả ít nhất một NULL |

### 3.3. Không biến fixture thành dữ liệu ngẫu nhiên

Dữ liệu ngẫu nhiên hữu ích cho fuzz/property-based testing, nhưng không nên là cách duy nhất để kiểm tra một quy tắc SQL. Khi một test thất bại, cần biết hàng nào gây lỗi và expected result là gì. Với fixture chủ đích, mỗi ID và giá trị có ý nghĩa có thể được mô tả trong bảng.

## 4. Bộ dữ liệu mẫu: customers, orders và order_items

Ta xây dựng một fixture có **4 khách hàng, 7 đơn hàng và 6 dòng chi tiết**. Bộ dữ liệu cố ý có:

- Một khách ACTIVE không có đơn.
- Một khách INACTIVE có đơn CANCELLED.
- Khách có nhiều đơn PAID hợp lệ trong tháng.
- Hai đơn cùng số tiền để phát hiện SUM(DISTINCT amount).
- Một đơn có hai dòng chi tiết để phát hiện nhân bản do JOIN.
- Một đơn amount bằng 0 đúng tại thời điểm kết thúc khoảng.
- Một đơn NEW gần cuối ngày để phát hiện lọc nhầm trạng thái.
- Email NULL để kiểm tra NULL.

### 4.1. Tạo bảng

Ví dụ dùng cú pháp gần ANSI SQL, chạy trên database học tập. TEMP table có cú pháp và vòng đời hơi khác nhau giữa các hệ; nếu engine không hỗ trợ cú pháp này, dùng bảng fixture riêng trong schema test và dọn sau khi chạy.

~~~sql
CREATE TEMP TABLE customers (
    customer_id      INTEGER PRIMARY KEY,
    display_name     VARCHAR(80) NOT NULL,
    customer_status  VARCHAR(20) NOT NULL,
    email            VARCHAR(120)
);

CREATE TEMP TABLE orders (
    order_id      INTEGER PRIMARY KEY,
    customer_id   INTEGER NOT NULL,
    amount        DECIMAL(12,2) NOT NULL CHECK (amount >= 0),
    status        VARCHAR(20) NOT NULL,
    created_at    TIMESTAMP NOT NULL,
    FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
);

CREATE TEMP TABLE order_items (
    item_id       INTEGER PRIMARY KEY,
    order_id      INTEGER NOT NULL,
    line_amount   DECIMAL(12,2) NOT NULL CHECK (line_amount >= 0),
    FOREIGN KEY (order_id)
        REFERENCES orders(order_id)
);
~~~

Ba bảng đại diện cho ba mức hạt dữ liệu:

- **customers:** một hàng cho một khách hàng.
- **orders:** một hàng cho một đơn hàng.
- **order_items:** một hàng cho một dòng chi tiết đơn hàng.

Khi JOIN nhiều mức hạt, phải biết mỗi hàng đại diện cho cái gì. Đây là điều kiện quan trọng để tổng hợp đúng.

### 4.2. Nạp khách hàng

~~~sql
INSERT INTO customers
    (customer_id, display_name, customer_status, email)
VALUES
    (1, 'An Nguyen',  'ACTIVE',   'an@example.test'),
    (2, 'Binh Tran',  'ACTIVE',   'binh@example.test'),
    (3, 'Chi Le',     'INACTIVE', 'chi@example.test'),
    (4, 'Dung Pham',  'ACTIVE',   NULL);
~~~

### 4.3. Nạp đơn hàng

~~~sql
INSERT INTO orders
    (order_id, customer_id, amount, status, created_at)
VALUES
    (101, 1, 100.00, 'PAID',
        TIMESTAMP '2026-01-01 00:00:00'),
    (102, 1, 100.00, 'NEW',
        TIMESTAMP '2026-01-31 23:59:59.500'),
    (103, 2,   0.00, 'PAID',
        TIMESTAMP '2026-02-01 00:00:00'),
    (104, 3,  50.00, 'CANCELLED',
        TIMESTAMP '2026-01-15 12:00:00'),
    (105, 2, 100.00, 'PAID',
        TIMESTAMP '2026-01-31 12:00:00'),
    (106, 1, 100.00, 'PAID',
        TIMESTAMP '2026-01-20 09:00:00'),
    (107, 2, 100.00, 'PAID',
        TIMESTAMP '2026-01-31 23:59:59.500');
~~~

Với test qua ứng dụng, có thể dùng bind parameter kiểu timestamp để tránh phụ thuộc định dạng literal của từng hệ.

### 4.4. Nạp dòng chi tiết

~~~sql
INSERT INTO order_items
    (item_id, order_id, line_amount)
VALUES
    (1, 101, 60.00),
    (2, 101, 40.00),
    (3, 102, 100.00),
    (4, 105, 100.00),
    (5, 106, 100.00),
    (6, 107, 100.00);
~~~

Đơn 101 có **hai dòng chi tiết**, tổng dòng = 100. Các đơn 101 và 106 đều có amount = 100 nhưng là **hai đơn khác nhau**. Dữ liệu này phân biệt được nhiều lỗi tổng hợp.

### 4.5. Sơ đồ quan hệ

~~~text
customers (1)
   | customer_id
   | 1:N
   v
orders (1)
   | order_id
   | 1:N
   v
order_items
~~~

Nếu JOIN customers → orders → order_items, một khách hàng có thể lặp lại qua nhiều đơn và một đơn có thể lặp lại qua nhiều dòng chi tiết. Đây là hành vi bình thường của quan hệ 1:N; lỗi nằm ở việc tổng hợp sai cấp độ.

## 5. Bảng kiểm kê: mỗi bản ghi phân biệt điều gì?

### 5.1. Khách hàng

| customer_id | Tên | Trạng thái | Email | Mục đích |
| ---: | --- | --- | --- | --- |
| 1 | An Nguyen | ACTIVE | Có | Hai đơn PAID trong tháng; phát hiện đếm/tổng |
| 2 | Binh Tran | ACTIVE | Có | Hai đơn PAID, một đơn amount 0 ở boundary |
| 3 | Chi Le | INACTIVE | Có | Có đơn CANCELLED; kiểm tra lọc khách và trạng thái |
| 4 | Dung Pham | ACTIVE | NULL | Không có đơn; kiểm tra LEFT JOIN, COUNT và NULL |

### 5.2. Đơn hàng

| order_id | customer_id | amount | status | created_at | Mục đích |
| ---: | ---: | ---: | --- | --- | --- |
| 101 | 1 | 100 | PAID | 2026-01-01 00:00 | Biên đầu, có hai item |
| 102 | 1 | 100 | NEW | 2026-01-31 23:59:59.500 | Gần cuối tháng nhưng không PAID |
| 103 | 2 | 0 | PAID | 2026-02-01 00:00 | Đúng boundary kết thúc, amount 0 |
| 104 | 3 | 50 | CANCELLED | 2026-01-15 12:00 | Trạng thái hủy, khách inactive |
| 105 | 2 | 100 | PAID | 2026-01-31 12:00 | PAID hợp lệ gần cuối tháng |
| 106 | 1 | 100 | PAID | 2026-01-20 09:00 | Đơn thứ hai cùng amount của An |
| 107 | 2 | 100 | PAID | 2026-01-31 23:59:59.500 | PAID gần sát cuối tháng |

### 5.3. Dòng chi tiết

| item_id | order_id | line_amount |
| ---: | ---: | ---: |
| 1 | 101 | 60 |
| 2 | 101 | 40 |
| 3 | 102 | 100 |
| 4 | 105 | 100 |
| 5 | 106 | 100 |
| 6 | 107 | 100 |

Fixture có ít hàng nhưng mỗi hàng đều có vai trò. Nó đủ để phát hiện INNER JOIN sai, filter sai vị trí, đếm sai, fan-out và SUM(DISTINCT) sai.

## 6. Tính expected result trước khi chạy query

Yêu cầu báo cáo:

> Liệt kê khách hàng ACTIVE và thống kê các đơn PAID trong khoảng từ đầu ngày 01/01/2026 đến trước 01/02/2026. Khách ACTIVE chưa có đơn PAID vẫn xuất hiện với số đơn = 0 và tổng = 0.

Khoảng thời gian là:

~~~text
[2026-01-01 00:00, 2026-02-01 00:00)
~~~

Điều kiện:

- customer_status = 'ACTIVE'
- status = 'PAID'
- created_at >= start
- created_at < end

Tính bằng tay:

| Khách | Đơn PAID trong tháng 1 | Số đơn | Tổng amount |
| --- | --- | ---: | ---: |
| An Nguyen | 101, 106 | 2 | 200 |
| Binh Tran | 105, 107 | 2 | 200 |
| Dung Pham | Không có | 0 | 0 |
| Chi Le | Bị loại: INACTIVE | — | — |

Đây là **expected result**. Ta cần giữ kết quả này độc lập với SQL truy vấn thật để tránh viết cùng một lỗi trong cả query lẫn test oracle.

## 7. Truy vấn đúng cho báo cáo

~~~sql
SELECT
    c.customer_id,
    c.display_name,
    COUNT(o.order_id) AS paid_order_count,
    COALESCE(SUM(o.amount), 0) AS paid_total
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
   AND o.created_at >= TIMESTAMP '2026-01-01 00:00:00'
   AND o.created_at <  TIMESTAMP '2026-02-01 00:00:00'
WHERE c.customer_status = 'ACTIVE'
GROUP BY
    c.customer_id,
    c.display_name
ORDER BY c.customer_id;
~~~

Kết quả:

| customer_id | display_name | paid_order_count | paid_total |
| ---: | --- | ---: | ---: |
| 1 | An Nguyen | 2 | 200.00 |
| 2 | Binh Tran | 2 | 200.00 |
| 4 | Dung Pham | 0 | 0.00 |

### 7.1. Vì sao điều kiện đơn hàng nằm trong ON?

Ta muốn giữ khách ACTIVE dù không có đơn PAID. LEFT JOIN tạo hàng phía phải NULL khi không tìm được đơn thỏa điều kiện. Nếu chuyển điều kiện status/ngày sang WHERE, hàng không có đơn sẽ bị loại.

### 7.2. Vì sao COUNT(o.order_id)?

Với khách Dung, LEFT JOIN tạo một hàng có các cột orders NULL:

- COUNT(*) đếm hàng join này thành 1.
- COUNT(o.order_id) bỏ NULL và trả 0.

### 7.3. Vì sao COALESCE(SUM(...),0)?

Không có đơn phù hợp thì SUM trả NULL. Hợp đồng báo cáo yêu cầu tổng tiền hiển thị là 0, nên dùng COALESCE. Nếu nghiệp vụ muốn phân biệt “chưa có dữ liệu” với “tổng bằng 0”, hãy giữ NULL thay vì ép về 0.

## 8. Fixture phát hiện lỗi INNER JOIN và WHERE

### 8.1. Lỗi 1: dùng INNER JOIN

~~~sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS order_count
FROM customers AS c
INNER JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
   AND o.created_at >= TIMESTAMP '2026-01-01 00:00:00'
   AND o.created_at <  TIMESTAMP '2026-02-01 00:00:00'
WHERE c.customer_status = 'ACTIVE'
GROUP BY c.customer_id;
~~~

Kết quả mất customer 4. Nếu fixture không có khách nào chưa có đơn, truy vấn sai này có thể vẫn vượt qua test.

### 8.2. Lỗi 2: đặt điều kiện phía phải trong WHERE

~~~sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS order_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE c.customer_status = 'ACTIVE'
  AND o.status = 'PAID'
  AND o.created_at >= TIMESTAMP '2026-01-01 00:00:00'
  AND o.created_at <  TIMESTAMP '2026-02-01 00:00:00'
GROUP BY c.customer_id;
~~~

Điều kiện o.status = 'PAID' loại hàng có o.status NULL, nên LEFT JOIN hoạt động giống INNER JOIN đối với điều kiện đó. Customer 4 biến mất.

### 8.3. Test phải kiểm tra cả sự hiện diện và giá trị

Không chỉ assert tổng doanh thu = 400. Truy vấn sai có thể trả tổng đúng nhưng thiếu một khách chưa có đơn. Cần kiểm tra:

- Số hàng kết quả là 3.
- Có customer_id 4.
- Dung có paid_order_count = 0.
- Dung có paid_total = 0.
- An và Binh có số đơn/tổng riêng đúng.

Một assertion chỉ kiểm tra SUM tổng thể là chưa đủ phân biệt lỗi.

## 9. Fixture phát hiện COUNT(*) và COUNT(column)

Với LEFT JOIN:

~~~sql
SELECT
    c.customer_id,
    COUNT(*) AS rows_after_join,
    COUNT(o.order_id) AS matched_orders
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
   AND o.created_at >= TIMESTAMP '2026-01-01 00:00:00'
   AND o.created_at <  TIMESTAMP '2026-02-01 00:00:00'
WHERE c.customer_id = 4
GROUP BY c.customer_id;
~~~

Kết quả:

| customer_id | rows_after_join | matched_orders |
| ---: | ---: | ---: |
| 4 | 1 | 0 |

Đây là test tối thiểu rất hữu ích: chỉ một customer không có order đã phân biệt được COUNT(*) và COUNT(order_id).

### 9.1. COUNT(column) cũng bỏ qua NULL thật

~~~sql
SELECT
    COUNT(*) AS customer_count,
    COUNT(email) AS email_count
FROM customers;
~~~

Expected: customer_count = 4, email_count = 3. Hàng Dung có email NULL.

Đừng dùng COUNT(email) khi nghiệp vụ cần đếm khách; cũng đừng dùng COUNT(*) khi cần đếm số email đã được nhập.

## 10. Fixture phát hiện lỗi fan-out khi JOIN nhiều bảng

Một đơn có nhiều order_items. Nếu JOIN orders với order_items, số tiền cấp đơn bị lặp theo số dòng chi tiết.

~~~sql
SELECT
    o.customer_id,
    COUNT(o.order_id) AS order_count_wrong,
    SUM(o.amount) AS total_wrong
FROM orders AS o
JOIN order_items AS i
    ON i.order_id = o.order_id
WHERE o.status = 'PAID'
  AND o.created_at >= TIMESTAMP '2026-01-01 00:00:00'
  AND o.created_at <  TIMESTAMP '2026-02-01 00:00:00'
GROUP BY o.customer_id
ORDER BY o.customer_id;
~~~

Với An:

- Order 101 có hai dòng item nên amount 100 xuất hiện hai lần.
- Order 106 có một dòng nên amount 100 xuất hiện một lần.
- Tổng sai = 100 + 100 + 100 = **300**, trong khi đúng là 200.
- COUNT sai = 3, trong khi số đơn đúng là 2.

Fixture chỉ cần **một đơn có hai dòng chi tiết** để phát hiện lỗi nhân bản; thêm đơn thứ hai cùng amount giúp phát hiện một cách “sửa” sai khác.

### 10.1. Vì sao SUM(DISTINCT amount) không sửa được?

~~~sql
SELECT
    o.customer_id,
    SUM(DISTINCT o.amount) AS distinct_total
FROM orders AS o
JOIN order_items AS i
    ON i.order_id = o.order_id
WHERE o.status = 'PAID'
  AND o.created_at >= TIMESTAMP '2026-01-01 00:00:00'
  AND o.created_at <  TIMESTAMP '2026-02-01 00:00:00'
GROUP BY o.customer_id;
~~~

An có hai đơn khác nhau, mỗi đơn 100. SUM(DISTINCT amount) chỉ cộng giá trị 100 một lần, kết quả **100**, vẫn sai. DISTINCT theo số tiền không tương đương DISTINCT theo đơn hàng.

### 10.2. Cách đúng: tổng hợp trước ở đúng grain

~~~sql
WITH order_totals AS (
    SELECT
        customer_id,
        COUNT(*) AS order_count,
        SUM(amount) AS amount_total
    FROM orders
    WHERE status = 'PAID'
      AND created_at >= TIMESTAMP '2026-01-01 00:00:00'
      AND created_at <  TIMESTAMP '2026-02-01 00:00:00'
    GROUP BY customer_id
),
item_totals AS (
    SELECT
        o.customer_id,
        SUM(i.line_amount) AS line_total
    FROM orders AS o
    JOIN order_items AS i
        ON i.order_id = o.order_id
    WHERE o.status = 'PAID'
      AND o.created_at >= TIMESTAMP '2026-01-01 00:00:00'
      AND o.created_at <  TIMESTAMP '2026-02-01 00:00:00'
    GROUP BY o.customer_id
)
SELECT
    c.customer_id,
    COALESCE(ot.order_count, 0) AS order_count,
    COALESCE(ot.amount_total, 0) AS amount_total,
    COALESCE(it.line_total, 0) AS line_total
FROM customers AS c
LEFT JOIN order_totals AS ot
    ON ot.customer_id = c.customer_id
LEFT JOIN item_totals AS it
    ON it.customer_id = c.customer_id
WHERE c.customer_status = 'ACTIVE'
ORDER BY c.customer_id;
~~~

Đây là cách giữ mỗi tập đã tổng hợp ở **grain customer** trước khi JOIN lại. Trong hệ thật, cần xác định rõ những đơn nào có đầy đủ item; nếu item có thể thiếu, amount cấp đơn và line_total có thể khác nhau vì nghiệp vụ, không nhất thiết là lỗi.

## 11. Fixture phát hiện lỗi khoảng thời gian

Một quy tắc tốt cho báo cáo tháng là dùng khoảng **nửa mở**:

~~~sql
created_at >= start_time
AND created_at < end_time
~~~

Với tháng 1 năm 2026:

~~~sql
created_at >= TIMESTAMP '2026-01-01 00:00:00'
AND created_at <  TIMESTAMP '2026-02-01 00:00:00'
~~~

### 11.1. Vì sao không dùng BETWEEN?

BETWEEN bao gồm cả hai đầu:

~~~sql
created_at BETWEEN
    TIMESTAMP '2026-01-01 00:00:00'
    AND TIMESTAMP '2026-02-01 00:00:00'
~~~

Điều này sẽ lấy cả order 103 đúng lúc 2026-02-01 00:00:00, dù đó là thời điểm bắt đầu tháng 2.

Nếu chọn end = 2026-01-31 23:59:59, có thể bỏ sót giá trị có phần fractional seconds sau đó, tùy độ chính xác timestamp của hệ.

### 11.2. Cặp dữ liệu boundary

| Order | created_at | Kỳ vọng với tháng 1 |
| ---: | --- | --- |
| 101 | 2026-01-01 00:00:00 | Được tính |
| 105 | 2026-01-31 12:00:00 | Được tính |
| 107 | 2026-01-31 23:59:59.500 | Được tính |
| 103 | 2026-02-01 00:00:00 | Không tính |

Nếu không có order 103 đúng thời điểm end, BETWEEN và khoảng nửa mở có thể cho cùng kết quả trong fixture; lỗi boundary sẽ không bị phát hiện.

### 11.3. Múi giờ

Nếu cột là timestamp có timezone hoặc lưu UTC, fixture phải bao gồm một thời điểm sát biên theo timezone nghiệp vụ:

- Chọn timezone báo cáo, ví dụ Asia/Ho_Chi_Minh.
- Chuyển start/end local thành instant tương ứng.
- Bind giá trị thời gian có timezone.
- Test thời điểm ngay trước, đúng tại và ngay sau boundary.

Không dùng CURRENT_DATE, NOW() hoặc timezone máy test làm dữ liệu cố định nếu expected result phải ổn định. Hãy đóng băng clock hoặc truyền mốc thời gian rõ ràng.

## 12. Fixture phát hiện lỗi NULL và NOT IN

SQL có logic ba giá trị: TRUE, FALSE và UNKNOWN. NULL không có nghĩa là chuỗi rỗng, số 0 hay một giá trị mặc định.

Tạo danh sách chặn:

~~~sql
CREATE TEMP TABLE suppression_list (
    customer_id INTEGER
);

INSERT INTO suppression_list(customer_id)
VALUES (2), (NULL);
~~~

Ta muốn tìm customer không có trong suppression_list.

### 12.1. NOT IN dễ bị ảnh hưởng bởi NULL

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE c.customer_id NOT IN (
    SELECT s.customer_id
    FROM suppression_list AS s
)
ORDER BY c.customer_id;
~~~

Subquery có NULL. Với những customer không khớp giá trị 2, biểu thức customer_id NOT IN (2, NULL) trở thành UNKNOWN thay vì TRUE; vì vậy truy vấn có thể trả **không hàng nào**.

### 12.2. NOT EXISTS

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM suppression_list AS s
    WHERE s.customer_id = c.customer_id
)
ORDER BY c.customer_id;
~~~

Kết quả: **1, 3, 4**. NULL trong suppression_list không tạo một equality match với customer_id nào.

### 12.3. Test phải chứa NULL trong tập con

Nếu suppression_list chỉ có giá trị 2, NOT IN và NOT EXISTS có thể cho kết quả giống nhau. Chỉ thêm NULL mới phân biệt được lỗi. Đây là ví dụ điển hình của **một hàng có chủ đích** làm lộ một khác biệt ngữ nghĩa.

Nếu nghiệp vụ cho phép customer_id NULL trong bảng nguồn, cần định nghĩa thêm cách xử lý NULL phía ngoài; NOT EXISTS không tự quyết định NULL có được coi là “không bị chặn” hay không.

## 13. Fixture cho DISTINCT, GROUP BY và duplicate

Duplicate không phải lúc nào cũng là dữ liệu lỗi. Cần biết duplicate ở **cấp nào**:

- Hai dòng giống giá trị nhưng là hai đơn khác nhau.
- Một order bị lặp do JOIN với hai item.
- Hai khách có cùng display_name nhưng khác customer_id.
- Hai dòng import có cùng business key.

### 13.1. DISTINCT có thể che lỗi JOIN

~~~sql
SELECT DISTINCT
    c.customer_id,
    c.display_name
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id;
~~~

DISTINCT làm mỗi khách xuất hiện một lần, nhưng không chứng minh JOIN đúng. Nếu JOIN nhầm khóa, DISTINCT có thể che một phần biểu hiện của lỗi trong khi các tổng hợp khác vẫn sai.

### 13.2. Hai khách cùng tên

Nếu cần kiểm tra khóa chính và GROUP BY:

~~~sql
INSERT INTO customers
    (customer_id, display_name, customer_status, email)
VALUES
    (5, 'An Nguyen', 'ACTIVE', 'an2@example.test');
~~~

Hai khách có cùng tên nhưng khác ID. Nếu truy vấn GROUP BY display_name, họ có thể bị gộp. Nếu nghiệp vụ cần mỗi khách một dòng, phải GROUP BY customer_id và các thuộc tính cần thiết.

Chỉ thêm trường hợp này khi bài toán có nguy cơ nhóm theo tên hiển thị; fixture không cần tất cả biến thể trong mọi test.

## 14. Fixture cho constraint và dữ liệu không hợp lệ

Dữ liệu test không chỉ kiểm tra truy vấn trả đúng; còn phải xác nhận database từ chối trạng thái không hợp lệ.

Với bảng orders:

- amount phải >= 0.
- order_id duy nhất.
- customer_id phải tồn tại.
- status nằm trong miền hợp lệ.

### 14.1. Thử vi phạm CHECK

~~~sql
INSERT INTO orders
    (order_id, customer_id, amount, status, created_at)
VALUES
    (999, 1, -1, 'PAID', TIMESTAMP '2026-01-10 00:00:00');
~~~

Kỳ vọng: database từ chối vì amount âm.

### 14.2. Thử vi phạm FOREIGN KEY

~~~sql
INSERT INTO orders
    (order_id, customer_id, amount, status, created_at)
VALUES
    (998, 9999, 10, 'PAID', TIMESTAMP '2026-01-10 00:00:00');
~~~

Kỳ vọng: database từ chối vì customer_id không tồn tại.

### 14.3. Thử trùng PRIMARY KEY

~~~sql
INSERT INTO orders
    (order_id, customer_id, amount, status, created_at)
VALUES
    (101, 1, 10, 'PAID', TIMESTAMP '2026-01-10 00:00:00');
~~~

Kỳ vọng: database từ chối trùng order_id.

### 14.4. Không bắt mọi lỗi rồi coi là test PASS

Trong test tự động, phải xác nhận đúng loại lỗi hoặc SQLSTATE/constraint name mong đợi. Nếu lệnh thất bại vì mất quyền, thiếu bảng hoặc lỗi cú pháp, đó không phải bằng chứng CHECK/FK hoạt động.

## 15. Viết assertion so sánh actual với expected

Một truy vấn test cần xác nhận **cả hàng, cột, duplicate và thứ tự nếu thứ tự là hợp đồng**.

### 15.1. Expected relation bằng VALUES

~~~sql
WITH actual AS (
    SELECT
        c.customer_id,
        COUNT(o.order_id) AS paid_order_count,
        COALESCE(SUM(o.amount), 0) AS paid_total
    FROM customers AS c
    LEFT JOIN orders AS o
        ON o.customer_id = c.customer_id
       AND o.status = 'PAID'
       AND o.created_at >= TIMESTAMP '2026-01-01 00:00:00'
       AND o.created_at <  TIMESTAMP '2026-02-01 00:00:00'
    WHERE c.customer_status = 'ACTIVE'
    GROUP BY c.customer_id
),
expected(customer_id, paid_order_count, paid_total) AS (
    VALUES
        (1, 2, 200.00),
        (2, 2, 200.00),
        (4, 0,   0.00)
),
missing_or_wrong AS (
    SELECT * FROM expected
    EXCEPT
    SELECT * FROM actual
),
unexpected AS (
    SELECT * FROM actual
    EXCEPT
    SELECT * FROM expected
)
SELECT 'missing_or_wrong' AS issue, *
FROM missing_or_wrong
UNION ALL
SELECT 'unexpected' AS issue, *
FROM unexpected;
~~~

Nếu kết quả rỗng, actual và expected giống nhau theo phép so sánh tập hợp ở đây. Với bài toán có thể xuất hiện duplicate cần kiểm tra, hãy dùng **EXCEPT ALL** trên hệ hỗ trợ hoặc so sánh thêm số lượng/tần suất từng khóa; EXCEPT thường loại duplicate trước khi so sánh.

### 15.2. So sánh số hàng

~~~sql
SELECT COUNT(*) AS actual_rows
FROM (
    SELECT c.customer_id
    FROM customers AS c
    LEFT JOIN orders AS o
        ON o.customer_id = c.customer_id
       AND o.status = 'PAID'
       AND o.created_at >= TIMESTAMP '2026-01-01 00:00:00'
       AND o.created_at <  TIMESTAMP '2026-02-01 00:00:00'
    WHERE c.customer_status = 'ACTIVE'
    GROUP BY c.customer_id
) AS result_set;
~~~

Expected = **3**. Nhưng chỉ đếm hàng vẫn chưa đủ; cần kiểm tra từng giá trị.

### 15.3. Assertion có thông điệp rõ

Trong PostgreSQL có thể dùng DO block:

~~~sql
DO $$
DECLARE
    v_count INTEGER;
    v_dung_total NUMERIC;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM customers
    WHERE customer_status = 'ACTIVE';

    IF v_count <> 3 THEN
        RAISE EXCEPTION
            'Expected 3 active customers, got %', v_count;
    END IF;

    SELECT COALESCE(SUM(o.amount), 0)
    INTO v_dung_total
    FROM customers AS c
    LEFT JOIN orders AS o
        ON o.customer_id = c.customer_id
       AND o.status = 'PAID'
       AND o.created_at >= TIMESTAMP '2026-01-01 00:00:00'
       AND o.created_at <  TIMESTAMP '2026-02-01 00:00:00'
    WHERE c.customer_id = 4;

    IF v_dung_total <> 0 THEN
        RAISE EXCEPTION
            'Expected Dung total 0, got %', v_dung_total;
    END IF;
END;
$$;
~~~

Đây là cú pháp PostgreSQL. Các hệ khác có cơ chế assertion/procedural test khác; nguyên tắc là thông báo test phải nêu rõ expected và actual.

## 16. Thiết kế dữ liệu kiểm thử cho NULL, zero và empty string

Ba trường hợp này thường bị nhập làm một:

| Giá trị | Ý nghĩa |
| --- | --- |
| NULL | Không có/không biết giá trị |
| 0 | Có giá trị số bằng 0 |
| '' | Có chuỗi nhưng không có ký tự (Oracle có semantics đặc biệt) |

Ví dụ amount = 0 ở order 103 là đơn hợp lệ có giá trị 0, không phải không có đơn. Customer 4 không có đơn nên COUNT(order_id) = 0 và SUM(amount) = NULL trước COALESCE. Email của Dung là NULL vì chưa có email.

### 16.1. Vì sao cần cả zero và không có hàng?

Nếu fixture chỉ có đơn amount > 0, truy vấn nhầm SUM/COALESCE hoặc điều kiện amount > 0 có thể vượt qua test. Hàng amount = 0 giúp phân biệt:

- Có đơn hợp lệ với số tiền 0.
- Không có đơn nào.
- Có đơn nhưng dữ liệu amount NULL (nếu schema cho phép).

Không nên cho phép amount NULL nếu nghiệp vụ yêu cầu NOT NULL; thay vào đó hãy test constraint từ chối NULL.

### 16.2. Test NULL ở cột nullable

~~~sql
SELECT
    COUNT(*) AS all_customers,
    COUNT(email) AS customers_with_email,
    COUNT(*) - COUNT(email) AS customers_without_email
FROM customers;
~~~

Expected: **4, 3, 1**.

## 17. Dữ liệu kiểm thử cho GROUP BY và phép tổng hợp

Khi viết test cho SUM, AVG, MIN, MAX, COUNT, phải tạo dữ liệu có thể phân biệt các lỗi:

- Một nhóm có nhiều hàng.
- Một nhóm không có hàng (nếu dùng LEFT JOIN).
- NULL trong cột tổng hợp nếu schema cho phép.
- Giá trị 0.
- Hai giá trị giống nhau nhưng là hai event riêng.
- Giá trị âm nếu nghiệp vụ cho phép hoàn trả/điều chỉnh.
- Nhóm có khóa khác nhưng cùng tên hiển thị.

### 17.1. AVG có thể sai khi lấy trung bình của các trung bình

~~~text
Nhóm A: 10, 20        → AVG = 15
Nhóm B: 100           → AVG = 100
~~~

Trung bình của hai average = 57.5, nhưng average toàn bộ ba dòng = 43.333... . Nếu cần tổng thể, phải cộng tổng và số lượng, hoặc tính AVG trên tập gốc; không lấy trung bình các average mà không weighting.

### 17.2. SUM(DISTINCT) không sửa fan-out tổng quát

Nếu hai đơn khác nhau cùng amount 100, SUM(DISTINCT amount) chỉ cộng 100 một lần. Fixture cần **hai đơn cùng amount** để phát hiện cách sửa sai này.

## 18. Dữ liệu kiểm thử cho JOIN và quan hệ

Một bộ fixture quan hệ nhỏ nên có:

1. Một parent không có child.
2. Một parent có đúng một child.
3. Một parent có nhiều child.
4. Một child có thuộc tính NULL nếu cho phép.
5. Hai parent có thuộc tính hiển thị giống nhau nhưng khóa khác.
6. Một khóa ngoại sai để test constraint (thực hiện trong ca negative riêng).
7. Nhiều child cùng một giá trị đo lường để phát hiện DISTINCT sai.

### 18.1. Chọn khóa ổn định

Dùng ID rõ ràng như 101, 102, 103 trong fixture thay vì dựa vào IDENTITY/AUTO_INCREMENT/sequence tăng liên tục. ID tự sinh có thể không rollback hoặc có khoảng trống tùy engine.

### 18.2. Không JOIN bằng cột hiển thị

Nếu hai khách cùng tên An Nguyen, JOIN bằng display_name có thể ghép nhầm hoặc nhân bản. Dùng khóa quan hệ đã định nghĩa, thường là customer_id hoặc khóa ghép phù hợp tenant.

## 19. Dữ liệu kiểm thử cho NOT EXISTS, anti-join và NULL

Một truy vấn anti-join tìm khách không có đơn:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
)
ORDER BY c.customer_id;
~~~

Expected: **4**.

Nếu muốn tìm khách không có đơn PAID:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
~~~

Expected gồm customer **3 và 4**:

- Customer 3 chỉ có đơn CANCELLED.
- Customer 4 không có đơn.

Hai trường hợp khác nhau nhưng cùng thỏa “không có PAID”. Nếu logic nghiệp vụ cần phân biệt “chưa từng có đơn” với “có đơn nhưng tất cả bị hủy”, fixture đã có đủ dữ liệu để làm việc đó.

## 20. Tính deterministic: dữ liệu cố định và thứ tự rõ ràng

Test phải cho cùng kết quả khi chạy nhiều lần trên cùng điều kiện.

Tránh phụ thuộc vào:

- CURRENT_DATE, NOW() hoặc SYSDATE nếu không đóng băng thời gian.
- RANDOM()/RAND() không seed.
- IDENTITY/sequence cụ thể phải bắt đầu từ 1.
- Thứ tự hàng mặc định khi không ORDER BY.
- Locale/collation mặc định của máy test.
- Timezone hệ điều hành.
- Dữ liệu tồn tại từ lần test trước.
- Một test khác chạy trước đã sửa bảng.

### 20.1. ORDER BY trong assertion

SQL không bảo đảm thứ tự kết quả nếu không có ORDER BY. Nếu hợp đồng yêu cầu sắp xếp:

~~~sql
SELECT customer_id, display_name
FROM customers
ORDER BY display_name, customer_id;
~~~

Thêm khóa phá hòa customer_id để thứ tự ổn định khi hai tên giống nhau.

Nếu test chỉ kiểm tra tập kết quả, hãy so sánh theo key/set thay vì giả định thứ tự trả về.

### 20.2. Không dùng thời gian hiện tại để tạo boundary

Đừng INSERT dữ liệu bằng CURRENT_TIMESTAMP rồi so với “tháng hiện tại” trong test mà không kiểm soát clock. Test có thể đổi kết quả vào ngày đầu tháng, cuối tháng hoặc khi chạy ở timezone khác.

Dùng timestamp cố định như bộ fixture ở phần 4, hoặc truyền start/end qua bind parameters.

## 21. Test độc lập, transaction và cleanup

Một test không được phụ thuộc test trước đã chèn dữ liệu hoặc thay trạng thái.

Một mẫu cho PostgreSQL:

~~~sql
BEGIN;

-- Setup fixture cho test.
-- Chạy query cần kiểm tra.
-- Assert kết quả.

ROLLBACK;
~~~

Nếu test có lỗi giữa chừng, transaction được rollback để không để lại thay đổi. Với PostgreSQL, sau lỗi trong transaction, cần rollback toàn bộ hoặc rollback tới savepoint trước khi chạy câu lệnh tiếp theo.

### 21.1. SAVEPOINT cho test negative

~~~sql
BEGIN;
SAVEPOINT before_invalid_insert;

-- Cố ý vi phạm CHECK amount >= 0.
INSERT INTO orders
    (order_id, customer_id, amount, status, created_at)
VALUES
    (999, 1, -1, 'PAID', TIMESTAMP '2026-01-10 00:00:00');

-- Sau lỗi, khôi phục tới savepoint trong cùng connection.
ROLLBACK TO SAVEPOINT before_invalid_insert;

SELECT COUNT(*) AS invalid_order_count
FROM orders
WHERE order_id = 999;

ROLLBACK;
~~~

Kết quả count = 0. Một số client dừng script ngay khi câu INSERT lỗi; khi đó cần xử lý lỗi và gửi ROLLBACK TO SAVEPOINT qua cùng connection.

### 21.2. DDL và transaction khác nhau theo hệ

Không giả định mọi DDL được rollback giống nhau:

- PostgreSQL hỗ trợ transaction cho nhiều thao tác DDL.
- MySQL có nhiều DDL implicit commit.
- Oracle có nhiều DDL implicit commit.
- SQL Server hỗ trợ transaction cho nhiều DDL nhưng còn phụ thuộc loại thao tác.
- SQLite có nhiều DDL có thể tham gia transaction.

Nếu fixture tạo schema/table trong test, phải biết engine và framework test quản lý DDL như thế nào.

### 21.3. Tránh cleanup bằng TRUNCATE tùy tiện

TRUNCATE có thể gây implicit commit hoặc giới hạn khác theo engine, bị chặn bởi foreign key, reset identity/sequence khác nhau hoặc tác động dữ liệu dùng chung ngoài fixture. Trong môi trường test cô lập, chọn cleanup phù hợp. Nếu dùng transaction rollback, thường không cần xóa từng hàng sau mỗi test.

## 22. Chia fixture theo loại kiểm thử

| Loại test | Fixture phù hợp | Mục tiêu |
| --- | --- | --- |
| Unit test truy vấn/hàm | 1–10 hàng có chủ đích | Logic và boundary |
| Integration test | Nhiều bảng, FK, role, transaction | Tương tác thật giữa các thành phần |
| Regression test | Fixture tái hiện bug đã xảy ra | Ngăn lỗi quay lại |
| Migration test | Schema cũ + dữ liệu đại diện | Kiểm tra nâng cấp |
| Performance test | Dữ liệu lớn, phân bố thực tế | Độ trễ, index, cardinality |
| Concurrency test | Nhiều session và trạng thái cạnh tranh | Lock, isolation, race condition |

**Dữ liệu nhỏ không thay thế performance dataset.** Bộ nhỏ giúp kiểm tra logic dễ hiểu; hiệu năng cần khối lượng và phân bố gần thực tế.

### 22.1. Regression fixture

Khi bug được tìm thấy:

1. Ghi lại câu truy vấn và dữ liệu tối thiểu làm lỗi tái hiện.
2. Tạo test độc lập có expected result.
3. Chạy test để xác nhận lỗi tồn tại trước khi sửa nếu có thể.
4. Sửa logic.
5. Chạy lại test và các test liên quan.
6. Giữ fixture trong repository cùng migration/schema tương ứng.

Một bug có thể tái hiện bằng hai hoặc ba hàng; đừng biến regression test thành bản sao toàn bộ production.

## 23. Pairwise và combinatorial testing

Nếu có nhiều chiều dữ liệu:

- customer_status: ACTIVE/INACTIVE.
- order_status: PAID/NEW/CANCELLED.
- amount: zero/positive.
- email: NULL/not NULL.
- created_at: before/in/at end.

Số tổ hợp đầy đủ tăng rất nhanh. Không phải lúc nào cũng cần tạo tích Descartes mọi giá trị.

**Pairwise testing** chọn các trường hợp sao cho mọi cặp giá trị của các chiều đều xuất hiện ít nhất một lần. Nó hữu ích khi lỗi thường do tương tác giữa hai yếu tố.

Nhưng pairwise không bảo đảm bắt được lỗi chỉ xuất hiện khi ba hoặc nhiều điều kiện kết hợp. Với ranh giới quan trọng, hãy viết ca kiểm thử riêng và có chủ đích.

### 23.1. Khi nào cần full combination?

Nên xét đầy đủ tổ hợp hoặc test có cấu trúc mạnh hơn khi:

- Có logic phân quyền nhạy cảm.
- Các điều kiện phụ thuộc lẫn nhau.
- Một lỗi có thể làm lộ dữ liệu hoặc gây giao dịch sai.
- Có state machine nhiều bước.
- Một tổ hợp đã gây incident thực tế.

## 24. Tách expected result khỏi implementation

Một lỗi phổ biến là dùng cùng một biểu thức SQL để tính cả actual và expected. Nếu biểu thức sai, test vẫn pass.

Ví dụ không tốt:

~~~sql
WITH actual AS (
    SELECT SUM(amount) AS total
    FROM orders
    WHERE status = 'PAID'
),
expected AS (
    SELECT SUM(amount) AS total
    FROM orders
    WHERE status = 'PAID'
)
SELECT * FROM actual
EXCEPT
SELECT * FROM expected;
~~~

Hai phía cùng lặp lại implementation, không tạo oracle độc lập.

Tốt hơn:

- Tính expected từ yêu cầu và fixture bằng tay với dataset nhỏ.
- Ghi expected thành VALUES/JSON/test assertion.
- Hoặc dùng một cách triển khai độc lập có ngữ nghĩa đơn giản hơn.

Ví dụ expected relation ở phần 15 được ghi rõ ba hàng: (1,2,200), (2,2,200), (4,0,0).

## 25. Kiểm thử số học và kiểu dữ liệu

Dữ liệu số cũng cần các cặp phân biệt:

- 0 và NULL.
- Số âm và số dương.
- Giá trị đúng giới hạn DECIMAL.
- Giá trị vượt precision/scale.
- Hai giá trị khác nhau sau rounding.
- Phép chia có dư.
- Tổng vượt miền kiểu dữ liệu.

### 25.1. Dùng DECIMAL cho tiền

~~~sql
CREATE TEMP TABLE money_cases (
    case_id INTEGER PRIMARY KEY,
    amount DECIMAL(12,2) NOT NULL
);

INSERT INTO money_cases(case_id, amount)
VALUES
    (1, 0.00),
    (2, 0.01),
    (3, 1.005),
    (4, 999999999.99);
~~~

Lưu ý: việc literal 1.005 được lưu thành 1.01, 1.00 hay bị làm tròn khác còn phụ thuộc engine và quy tắc chuyển kiểu. Nếu muốn test rounding, hãy quy định precision đầu vào, phép toán và rounding mode rõ ràng, rồi xác định expected theo đúng engine.

### 25.2. Tránh dùng float để kiểm tra tiền chính xác

FLOAT/REAL dùng biểu diễn nhị phân gần đúng cho nhiều số thập phân. Test so sánh bằng tuyệt đối có thể sai vì representation. Dùng DECIMAL/NUMERIC hoặc integer đơn vị nhỏ nhất theo nghiệp vụ; khi dùng số gần đúng, chọn tolerance có giải thích.

## 26. Kiểm thử collation và chuỗi

Fixture nhỏ có thể chứa:

~~~text
An
AN
An 
Án
An (NFC)
An (NFD nếu có ký tự tổ hợp)
~~~

Các giá trị này giúp kiểm tra case-sensitive/case-insensitive, accent-sensitive/accent-insensitive, khoảng trắng cuối, Unicode normalization và UNIQUE index.

Không chỉ ghi kết quả trên một database rồi áp dụng cho hệ khác; collation và normalization khác nhau theo engine/version.

## 27. Kiểm thử NULL và ba-valued logic

Các điều kiện sau không tương đương:

~~~sql
column = NULL
column IS NULL
column <> NULL
column IS NOT NULL
~~~

Trong SQL, = NULL và <> NULL thường trả UNKNOWN, không phải phép kiểm tra NULL. Hãy dùng IS NULL/IS NOT NULL.

Một fixture NULL có thể phân biệt:

~~~sql
SELECT customer_id
FROM customers
WHERE email IS NULL;
~~~

Expected: customer 4.

### 27.1. NULL trong phép so sánh

~~~sql
SELECT
    NULL = NULL AS equals_null,
    NULL <> NULL AS not_equals_null,
    NULL IS NULL AS is_null;
~~~

Trong SQL logic thông thường, hai biểu thức đầu là UNKNOWN/NULL; biểu thức cuối là TRUE.

### 27.2. NULL trong aggregate

COUNT(column), SUM và AVG thường bỏ qua giá trị NULL; COUNT(*) đếm hàng. Fixture cần NULL nếu logic dựa trên số lượng giá trị đã nhập.

## 28. Kiểm thử transaction và concurrency

Một fixture đơn session không phát hiện mọi lỗi transaction. Nếu logic phụ thuộc nhiều session, cần thiết kế test cạnh tranh:

- Hai transaction cùng đọc một hàng rồi cùng UPDATE.
- Hai request tạo cùng business key.
- Một transaction xóa parent trong khi transaction khác thêm child.
- Hai giao dịch cập nhật các hàng theo thứ tự ngược nhau, có nguy cơ deadlock.
- Một request retry sau khi client không biết COMMIT đã thành công hay chưa.

### 28.1. Kiểm thử race condition cần nhiều connection

~~~text
Session A: BEGIN
Session A: SELECT balance

Session B: BEGIN
Session B: SELECT balance

Session A: UPDATE balance = ...
Session A: COMMIT

Session B: UPDATE dựa trên giá trị cũ
Session B: COMMIT
~~~

Expected result phụ thuộc isolation level và cách cập nhật. Test phải mô tả invariant, chẳng hạn balance không âm hoặc số lượng tồn không bị bán vượt mức, thay vì chỉ kiểm tra từng statement riêng.

### 28.2. Đừng giả lập concurrency bằng một connection tuần tự

Chạy A rồi B trên cùng một session không tương đương hai transaction thực sự cạnh tranh. Dùng hai connection, đồng bộ điểm bắt đầu và xác nhận isolation/lock đúng engine.

## 29. Kiểm thử đa hệ quản trị

Cùng một fixture nghiệp vụ có thể dùng để so sánh PostgreSQL, MySQL, SQL Server, Oracle và SQLite, nhưng cần tách:

- **Expected nghiệp vụ:** khách nào, đơn nào, tổng tiền nào.
- **Expected theo phương ngữ:** kiểu dữ liệu, NULL/empty string, timestamp precision, collation và error code.

### 29.1. Các khác biệt cần lưu ý

| Chủ đề | Điều phải kiểm tra khi port fixture |
| --- | --- |
| TEMP table | Phạm vi session, cú pháp và vòng đời |
| Timestamp | Precision, timezone, literal và bind type |
| DECIMAL | Precision/scale và rounding |
| Empty string | Oracle coi chuỗi rỗng như NULL trong nhiều ngữ cảnh |
| Boolean | Kiểu/biểu diễn khác nhau; SQLite thường dùng integer convention |
| Identity/sequence | Có thể có gap sau rollback |
| DDL transaction | Implicit commit và hỗ trợ rollback khác nhau |
| EXCEPT/INTERSECT | Cú pháp và hỗ trợ EXCEPT ALL khác nhau |
| Constraint error | SQLSTATE/error number và tên constraint khác nhau |
| Collation | Case/accent/padding/Unicode khác nhau |

### 29.2. Không dùng một expected byte-for-byte cho mọi hệ

Một kết quả số có thể cùng giá trị nhưng scale hiển thị khác nhau: 200, 200.0, 200.00. Nếu scale không phải một phần hợp đồng, so sánh giá trị số thay vì chuỗi output. Nếu API yêu cầu scale cố định, kiểm tra riêng kiểu/serialization.

## 30. Dữ liệu tổng hợp, dữ liệu production và quyền riêng tư

Fixture cho unit/integration test nên ưu tiên **dữ liệu tổng hợp**:

- Tên giả lập.
- Email thuộc domain dành cho ví dụ như example.test.
- ID không trùng dữ liệu thật.
- Không có số định danh, token, mật khẩu hoặc ghi chú khách hàng thật.

Nếu cần dữ liệu production-like để performance test:

1. Dùng dữ liệu tổng hợp có phân bố tương tự.
2. Hoặc masking/anonymization có đánh giá rủi ro.
3. Không sao chép dữ liệu nhạy cảm vào máy cá nhân/CI chỉ để tiện test.
4. Bảo vệ backup, log và artifact test.
5. Ghi rõ nguồn và thời hạn lưu dữ liệu test.

Dữ liệu nhỏ được thiết kế tốt thường không cần lấy dữ liệu khách hàng thật.

## 31. Một checklist suy nghĩ trước khi thêm bản ghi

Trước mỗi hàng mới, hãy hỏi:

1. Nó kiểm tra yêu cầu nào?
2. Nó phân biệt implementation đúng với lỗi nào?
3. Nếu bỏ hàng này, test nào sẽ không còn phát hiện được?
4. Có thể gộp vai trò của nó với hàng khác mà vẫn dễ hiểu không?
5. Nó có làm expected result khó tính bằng tay không?
6. Nó có phụ thuộc thứ tự insert hoặc ID tự sinh không?
7. Nó có tạo duplicate ngoài chủ ý không?
8. Nó có vi phạm constraint làm fixture không thể tạo không?
9. Nó có thể làm test khác bị ảnh hưởng không?
10. Có cần một fixture riêng để cô lập lỗi thay vì thêm vào fixture chung không?

Không phải cứ nhiều hàng là test tốt; **mỗi hàng cần đóng góp thông tin kiểm thử**.

## 32. Những lỗi thường gặp khi thiết kế test data

| Lỗi thiết kế | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| Chỉ có một hàng happy path | Lỗi boundary/NULL/duplicate không lộ | Thêm trường hợp đối chứng có chủ đích |
| Dữ liệu ngẫu nhiên không có expected rõ | Khó biết kết quả đúng | Chọn ID/giá trị cố định và expected bằng tay |
| Không có parent không có child | INNER JOIN sai vẫn pass | Thêm một parent không có child |
| Mọi đơn cùng trạng thái | Quên lọc status không bị phát hiện | Thêm PAID/NEW/CANCELLED |
| Mọi amount khác nhau | SUM(DISTINCT) sai có thể không lộ | Hai đơn riêng có cùng amount |
| Mỗi order chỉ có một item | Fan-out không xuất hiện | Một order có ít nhất hai item |
| Không có hàng đúng boundary | BETWEEN sai vẫn pass | Thêm hàng đúng thời điểm end |
| Không có NULL trong tập con | NOT IN có thể vẫn đúng | Thêm một NULL để phân biệt |
| Chỉ assert tổng toàn bộ | Thiếu hàng vẫn có thể cho tổng đúng | Assert từng key và từng giá trị |
| Chỉ assert COUNT(*) | Giá trị cột sai không lộ | So sánh toàn bộ expected relation |
| Dùng DISTINCT để che duplicate | Bug JOIN bị che | Kiểm tra grain và multiplicity |
| Dùng SUM(DISTINCT amount) | Gộp hai đơn cùng amount | Aggregate theo order_id trước |
| Expected tính bằng cùng query | Cùng một bug ở cả hai phía | Expected độc lập |
| Test phụ thuộc dữ liệu test trước | Chạy riêng thất bại | Fixture setup/teardown riêng |
| Dựa vào IDENTITY bắt đầu từ 1 | Flaky sau rollback/retry | Dùng ID cố định hoặc tra key |
| Không ORDER BY | Thứ tự không ổn định | ORDER BY với tie-breaker |
| Dùng NOW/CURRENT_DATE | Test thay đổi theo ngày/timezone | Clock cố định, timestamp tường minh |
| Không test constraint âm | Dữ liệu sai được chấp nhận | Negative test đúng constraint |
| Bắt mọi exception là PASS | Lỗi sai cũng bị coi là đúng | Assert SQLSTATE/constraint cụ thể |
| Dùng fixture nhỏ để kết luận hiệu năng | Không phản ánh production | Dataset performance riêng |
| Chạy concurrency trên một session | Không tạo cạnh tranh thật | Nhiều connection đồng bộ |
| Dùng dữ liệu thật trong test | Rủi ro riêng tư | Synthetic/masked data |

## 33. Bài tập thực hành

Sử dụng fixture ở phần 4. Hãy viết expected result trước khi chạy câu SQL cần kiểm tra.

1. Tạo ba bảng customers, orders, order_items cùng PK/FK/CHECK.
2. Nạp bốn customer và bảy order theo bộ dữ liệu mẫu.
3. Giải thích mục đích của từng customer và từng order.
4. Viết truy vấn đếm số đơn PAID tháng 1 theo customer.
5. Viết truy vấn tổng tiền PAID tháng 1 theo customer, giữ khách không có đơn.
6. Thay LEFT JOIN bằng INNER JOIN; xác định hàng nào biến mất.
7. Chuyển điều kiện status từ ON sang WHERE; giải thích kết quả.
8. So sánh COUNT(*) và COUNT(order_id) cho customer 4.
9. So sánh COUNT(*) và COUNT(email) trên customers.
10. Thêm đơn CANCELLED amount 50; kiểm tra nó không vào tổng PAID.
11. Thêm đơn NEW sát cuối tháng; kiểm tra không tính.
12. Thử BETWEEN đến 2026-02-01; xác định order 103 có bị lấy sai không.
13. Thử khoảng nửa mở [2026-01-01, 2026-02-01); xác nhận order 103 bị loại.
14. JOIN orders với order_items rồi SUM order.amount; tính fan-out cho An.
15. Thử SUM(DISTINCT amount); giải thích vì sao tổng An sai.
16. Viết CTE tổng hợp orders theo customer trước khi JOIN.
17. Thêm suppression_list chứa customer_id 2 và NULL; so sánh NOT IN với NOT EXISTS.
18. Tạo test anti-join để tìm khách không có đơn PAID.
19. Thêm một customer trùng display_name nhưng customer_id khác; thử GROUP BY theo tên và theo ID.
20. Viết assertion actual/expected bằng VALUES và EXCEPT.
21. Giải thích khi nào cần EXCEPT ALL hoặc so multiplicity.
22. Viết DO block PostgreSQL kiểm tra customer 4 có paid_total = 0.
23. Thử INSERT amount âm và xác nhận CHECK constraint từ chối.
24. Thử INSERT customer_id không tồn tại và xác nhận FK từ chối.
25. Thử INSERT trùng order_id và xác nhận PK từ chối.
26. Chạy negative test trong SAVEPOINT rồi ROLLBACK TO SAVEPOINT.
27. Viết test NULL/zero/empty string cho trường email/ghi chú.
28. Thiết kế fixture kiểm tra AVG của các nhóm có số hàng khác nhau.
29. Viết test hai session cập nhật cùng một số dư và mô tả invariant cần giữ.
30. Tạo regression fixture tối thiểu cho một lỗi bạn tự tạo, ghi expected result.
31. Chọn một test cần dữ liệu 10 hàng và một test cần dataset lớn; giải thích vì sao.
32. Thiết kế pairwise test cho customer_status, order_status, amount và email.
33. Viết test dùng timestamp cố định thay CURRENT_TIMESTAMP.
34. Viết test thứ tự có tie-breaker khi hai khách cùng tên.
35. Đề xuất cách tạo dữ liệu tổng hợp để performance test mà không dùng dữ liệu thật.

### Câu hỏi tự kiểm tra

**Câu 1.** Bộ dữ liệu kiểm thử tốt nhất là bộ có nhiều hàng nhất?

**Đáp án:** **Không.** Bộ tốt là bộ nhỏ nhưng phân biệt được các hành vi đúng/sai quan trọng.

**Câu 2.** Muốn phát hiện INNER JOIN sai khi yêu cầu giữ parent không có child, cần loại dữ liệu nào?

**Đáp án:** Ít nhất một parent không có child phù hợp.

**Câu 3.** LEFT JOIN một khách không có đơn, COUNT(*) và COUNT(order_id) có cùng kết quả không?

**Đáp án:** **Không.** COUNT(*) đếm hàng outer join; COUNT(order_id) bỏ NULL.

**Câu 4.** Vì sao cần hai đơn khác nhau cùng amount khi test SUM(DISTINCT amount)?

**Đáp án:** Vì DISTINCT theo amount sẽ gộp hai đơn hợp lệ thành một giá trị.

**Câu 5.** Vì sao cần một đơn đúng tại thời điểm 2026-02-01 00:00:00?

**Đáp án:** Để phân biệt khoảng tháng 1 nửa mở với BETWEEN bao gồm cả điểm cuối.

**Câu 6.** NOT IN luôn an toàn khi subquery chứa NULL?

**Đáp án:** **Không.** NULL có thể làm điều kiện thành UNKNOWN; NOT EXISTS thường phù hợp hơn cho anti-join.

**Câu 7.** SUM(DISTINCT order.amount) có sửa được fan-out khi JOIN order_items không?

**Đáp án:** **Không.** Hai order riêng có cùng amount sẽ bị gộp; phải aggregate theo grain đúng.

**Câu 8.** Một test chỉ assert tổng tiền toàn bộ có đủ phát hiện khách bị mất khỏi kết quả không?

**Đáp án:** **Không.** Cần kiểm tra từng khóa/hàng và giá trị tương ứng.

**Câu 9.** Dùng NOW() để tạo fixture ngày tháng có bảo đảm test deterministic không?

**Đáp án:** **Không.** Hãy dùng timestamp cố định hoặc clock được kiểm soát.

**Câu 10.** Chạy hai truy vấn lần lượt trên cùng connection có tương đương kiểm thử concurrency không?

**Đáp án:** **Không.** Cần nhiều session/connection thực sự cạnh tranh.

**Câu 11.** Dữ liệu nhỏ có thay thế performance test trên hàng triệu bản ghi không?

**Đáp án:** **Không.** Logic test và performance test cần bộ dữ liệu khác mục tiêu.

**Câu 12.** Expected result nên được tính bằng cách lặp lại nguyên query đang test không?

**Đáp án:** **Không.** Cách đó có thể lặp lại cùng một lỗi; expected cần độc lập.

## 34. Ghi nhớ cốt lõi

**Hãy thiết kế dữ liệu kiểm thử từ lỗi cần phát hiện.** Viết hợp đồng truy vấn, liệt kê lỗi có thể xảy ra, rồi tạo những bản ghi tối thiểu khiến kết quả đúng và sai khác nhau.

Một bộ fixture SQL nhỏ nhưng hữu ích thường có:

~~~text
1 parent không có child
1 parent có một child
1 parent có nhiều child
2 bản ghi khác nhau cùng giá trị đo lường
1 giá trị NULL
1 giá trị zero
1 trạng thái không được tính
1 hàng ngay trước/đúng tại boundary
1 quan hệ 1:N gây fan-out
1 negative case vi phạm constraint
~~~

Với truy vấn tổng hợp, hãy biết **grain** của từng bảng và tổng hợp trước khi JOIN làm nhân bản hàng. Với LEFT JOIN, kiểm tra điều kiện ON/WHERE và COUNT(column). Với anti-join, test NULL để phát hiện NOT IN. Với thời gian, dùng khoảng nửa mở và dữ liệu đúng sát biên. Với assertion, so sánh cả tập hàng, giá trị và multiplicity khi cần, không chỉ tổng số hoặc tổng tiền.

Cuối cùng, fixture phải **deterministic, độc lập và an toàn**: ID/timestamp cố định, thứ tự có ORDER BY, không phụ thuộc test trước, rollback/cleanup rõ ràng và ưu tiên dữ liệu tổng hợp. Dùng dataset nhỏ để kiểm tra logic, dataset đại diện để đo hiệu năng, và nhiều connection khi cần kiểm thử concurrency. Một vài hàng có lý do tồn tại rõ ràng có thể phát hiện lỗi mà hàng nghìn dòng ngẫu nhiên không bao giờ chạm tới.
