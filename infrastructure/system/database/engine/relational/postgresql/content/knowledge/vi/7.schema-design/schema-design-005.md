# Phi chuẩn hóa có chủ đích và đánh đổi tính nhất quán trong PostgreSQL

Trong thiết kế cơ sở dữ liệu quan hệ, **chuẩn hóa** giúp mỗi sự thật nghiệp vụ có một nơi lưu trữ rõ ràng, giảm dữ liệu dư thừa và hạn chế bất thường khi cập nhật. Tuy nhiên, một hệ thống thực tế còn phải đáp ứng những truy vấn nhanh, báo cáo phức tạp và nhu cầu hiển thị dữ liệu đã được “chụp” tại một thời điểm lịch sử. Khi đo lường cho thấy việc luôn tính toán hoặc kết hợp nhiều bảng gây chi phí đáng kể, nhóm phát triển có thể cân nhắc **phi chuẩn hóa có chủ đích** (*intentional denormalization*).

Phi chuẩn hóa không đơn giản là “bỏ chuẩn hóa để chạy nhanh”. Đó là quyết định **lưu thêm một biểu diễn của thông tin đã có thể suy ra từ nguồn khác** hoặc sắp xếp dữ liệu theo cách thuận tiện hơn cho một mẫu truy vấn cụ thể. Mỗi bản sao thông tin mới đi kèm câu hỏi: **ai cập nhật nó, cập nhật lúc nào, và nếu hai bản sao khác nhau thì bản nào đúng?**

Ví dụ, tổng tiền một đơn hàng có thể được tính từ các dòng `order_items`. Lưu thêm `orders.total_amount` giúp đọc danh sách đơn hàng nhanh hơn, nhưng nếu một dòng hàng thay đổi mà tổng tiền không đổi, database có thể trả về kết quả sai. Ngược lại, lưu `customer_name_at_order` trong đơn hàng có thể hoàn toàn đúng vì nghiệp vụ muốn giữ **tên khách hàng tại thời điểm đặt hàng**, dù tên hiện tại trong bảng `customers` đã thay đổi.

Bài học giải thích cách phân biệt **dư thừa gây rủi ro** với **dữ liệu lịch sử có ý nghĩa độc lập**, các mô hình phi chuẩn hóa phổ biến trong PostgreSQL, cách giữ nhất quán bằng transaction/trigger hoặc chấp nhận nhất quán cuối cùng, cùng quy trình đo đạc và vận hành an toàn.

## 1. Ôn lại chuẩn hóa: mỗi sự thật nên nằm ở đâu?

Trong thiết kế quan hệ, một mục tiêu của chuẩn hóa là loại bỏ sự phụ thuộc không cần thiết giữa những thuộc tính và những bản ghi. Ví dụ:

```text
customers
  customer_id  -> full_name, email

orders
  order_id     -> customer_id, created_at, status

order_items
  (order_id, line_no) -> product_code, quantity, unit_price
```

Với các quan hệ này, tên hiện tại của khách hàng nên được đọc qua `customers`; tổng tiền đơn hàng có thể tính từ `order_items`. Thông tin không cần bị sao chép thành nhiều giá trị luôn phải thay đổi đồng thời.

### 1.1. Những bất thường mà chuẩn hóa muốn giảm

Giả sử bảng `orders_flat` chứa nhiều dòng hàng và lặp lại thông tin khách:

| order_id | line_no | customer_id | customer_name | product | quantity |
| ---: | ---: | ---: | --- | --- | ---: |
| 101 | 1 | 1 | Lan | BOOK-SQL | 2 |
| 101 | 2 | 1 | Lan | NOTE-A5 | 1 |
| 102 | 1 | 1 | Lan | PEN-BLUE | 3 |

Nếu Lan đổi tên:

- **Update anomaly:** phải sửa nhiều dòng; bỏ sót một dòng khiến cùng `customer_id` có hai tên khác nhau.
- **Insert anomaly:** nếu bắt buộc lưu thông tin khách trong dòng đơn hàng, có thể khó tạo khách chưa đặt hàng.
- **Delete anomaly:** xóa đơn cuối cùng có thể làm mất luôn thông tin khách nếu không có bảng khách riêng.

Chuẩn hóa tách thực thể và phụ thuộc dữ liệu. Các dạng chuẩn như 1NF, 2NF, 3NF hoặc BCNF giúp nhận diện cấu trúc có nguy cơ trùng lặp, nhưng không thay thế việc định nghĩa đúng **khóa, ràng buộc và quy tắc nghiệp vụ**.

### 1.2. Chuẩn hóa không có nghĩa cấm JOIN

Một truy vấn cần dữ liệu ở nhiều bảng là điều bình thường trong database quan hệ:

```sql
SELECT
    o.order_id,
    c.full_name,
    o.created_at,
    o.status
FROM commerce_lab.orders AS o
JOIN commerce_lab.customers AS c
  ON c.customer_id = o.customer_id
WHERE o.customer_id = 1
ORDER BY o.created_at DESC;
```

PostgreSQL có bộ tối ưu truy vấn, chỉ mục, thống kê và nhiều thuật toán JOIN. **Sự tồn tại của JOIN không tự chứng minh rằng schema cần phi chuẩn hóa**. Cần đo chi phí thực tế trước.

## 2. Phi chuẩn hóa có chủ đích là gì?

**Phi chuẩn hóa** là đưa thêm thông tin đã suy ra được từ dữ liệu khác vào nơi phục vụ một mục đích xác định. Dữ liệu dư thừa được chấp nhận vì nó mang lại lợi ích đã được đo, ví dụ giảm JOIN, tránh tính tổng lặp lại hoặc tăng tốc truy vấn dashboard.

| Cách làm | Nguồn gốc giá trị | Lợi ích kỳ vọng | Rủi ro chính |
| --- | --- | --- | --- |
| Lưu `orders.total_amount` | Tổng các dòng `order_items` | Đọc danh sách đơn không phải cộng lại chi tiết | Tổng tiền có thể lệch nếu dòng hàng đổi mà tổng không đổi. |
| Lưu `orders.customer_name_at_order` | Tên khách khi xác nhận đơn | Giữ thông tin lịch sử, hiển thị hóa đơn đúng thời điểm | Dễ nhầm với tên hiện tại nếu không đặt ngữ nghĩa rõ. |
| Bảng `daily_sales_summary` | Tổng hợp các đơn theo ngày | Dashboard đọc nhanh một số dòng | Có thể cập nhật trễ, đếm đôi hoặc bỏ sót sự kiện. |
| Materialized view | Kết quả truy vấn SELECT tại lần refresh | Tăng tốc truy vấn báo cáo lặp lại | Kết quả cũ giữa các lần refresh. |
| JSONB chứa bản chụp cấu hình/chi tiết | Dữ liệu từ quan hệ hoặc hệ thống khác | Trả về một cấu trúc tài liệu thuận tiện | Dễ lệch schema, khó kiểm soát và truy vấn nếu lạm dụng. |

Một thiết kế tốt không chỉ ghi “thêm cột để nhanh” mà phải ghi kèm:

1. **Nguồn sự thật** (*source of truth*) là gì?
2. Giá trị lưu thêm **có phải luôn bằng nguồn** hay cố ý phản ánh một thời điểm?
3. **Mức độ trễ chấp nhận được** là bao nhiêu?
4. Cơ chế nào duy trì hoặc làm mới dữ liệu?
5. Có cách **phát hiện và sửa lệch** không?
6. Đã đo được lợi ích vượt chi phí ghi và vận hành chưa?

### 2.1. Ba kiểu dữ liệu rất khác nhau

| Kiểu | Ví dụ | Ngữ nghĩa |
| --- | --- | --- |
| **Giá trị dẫn xuất phải đồng bộ** | `orders.total_amount = SUM(order_items)` | Nếu dòng hàng thay đổi, tổng phải thay đổi tương ứng; lệch là lỗi dữ liệu. |
| **Snapshot lịch sử có chủ ý** | `customer_name_at_order` | Sau khi chốt đơn, tên có thể khác tên hiện tại; khác nhau không phải lỗi. |
| **Bản sao cho đọc có thể trễ** | Bảng tổng hợp doanh thu mỗi 5 phút | Cho phép lệch trong cửa sổ đã cam kết, nhưng phải có cách bắt kịp/đối soát. |

Nếu không phân loại trước, nhóm vận hành có thể cố “sửa” tên lịch sử cho giống tên hiện tại, hoặc ngược lại coi tổng tiền sai là một loại snapshot hợp lệ.

## 3. Ví dụ schema chuẩn hóa làm điểm xuất phát

Dùng schema `commerce_lab` trong môi trường PostgreSQL thử nghiệm. Ví dụ giữ riêng khách hàng, đơn hàng và dòng hàng để định nghĩa rõ khóa và quan hệ.

```sql
CREATE SCHEMA IF NOT EXISTS commerce_lab;

CREATE TABLE commerce_lab.customers (
    customer_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name text NOT NULL,
    email text NOT NULL UNIQUE
);

CREATE TABLE commerce_lab.orders (
    order_id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES commerce_lab.customers(customer_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    status text NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'confirmed', 'cancelled'))
);

CREATE TABLE commerce_lab.order_items (
    order_id bigint NOT NULL
        REFERENCES commerce_lab.orders(order_id),
    line_no integer NOT NULL CHECK (line_no > 0),
    product_code text NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price numeric(14, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);
```

Các ràng buộc giúp bảo vệ sự thật nền tảng:

- `customers.customer_id` là định danh khách.
- `orders.customer_id` tham chiếu khách hợp lệ.
- Một dòng hàng được định danh bởi cặp `(order_id, line_no)`.
- `quantity > 0` và `unit_price >= 0` ngăn một số giá trị không hợp lệ tại cấp database.
- `numeric` phù hợp hơn `float` cho phép tính tiền cần độ chính xác thập phân theo quy tắc nghiệp vụ.

Dữ liệu thử:

```sql
INSERT INTO commerce_lab.customers (customer_id, full_name, email)
VALUES
    (1, 'Lan', 'lan@example.test'),
    (2, 'Minh', 'minh@example.test');

INSERT INTO commerce_lab.orders
    (order_id, customer_id, created_at, status)
VALUES
    (101, 1, '2026-10-05 09:00:00+07', 'draft'),
    (102, 2, '2026-10-06 10:30:00+07', 'confirmed');

INSERT INTO commerce_lab.order_items
    (order_id, line_no, product_code, quantity, unit_price)
VALUES
    (101, 1, 'BOOK-SQL', 2, 150000.00),
    (101, 2, 'NOTE-A5',  1,  30000.00),
    (102, 1, 'PEN-BLUE', 3,  12000.00);
```

Các ID thủ công ở đây giúp dễ đọc kết quả bài tập. Khi dùng identity columns trong ứng dụng thật, cần xem lại trạng thái sequence nếu kết hợp chèn ID thủ công với việc tự sinh ID tiếp theo.

### 3.1. Tính tổng tiền không cần lưu thêm

```sql
SELECT
    o.order_id,
    COALESCE(SUM(i.quantity::numeric * i.unit_price), 0)
        AS calculated_total
FROM commerce_lab.orders AS o
LEFT JOIN commerce_lab.order_items AS i
  ON i.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
```

Kết quả từ ví dụ:

| order_id | calculated_total |
| ---: | ---: |
| 101 | 330000.00 |
| 102 | 36000.00 |

`LEFT JOIN` cùng `COALESCE` giúp đơn chưa có dòng hàng vẫn trả tổng `0`. Đây là cách lấy tổng từ **nguồn sự thật**. Nó luôn tính trên những bản ghi nhìn thấy được theo snapshot MVCC của câu truy vấn.

### 3.2. Vì sao có lúc tổng hợp động là đủ?

Nếu màn hình chỉ mở vài đơn, mỗi đơn có ít dòng và chỉ mục `PRIMARY KEY (order_id, line_no)` hỗ trợ tìm dòng theo `order_id`, phép tính tổng có thể rất rẻ. Lưu thêm `total_amount` khi chưa có dấu hiệu nghẽn sẽ làm tăng độ phức tạp mà chưa chắc cải thiện đáng kể.

Ngược lại, một màn hình danh sách 500 đơn mỗi lần, có hàng nghìn lượt xem mỗi giây và cần lọc/sắp xếp theo tổng tiền có thể tạo chi phí tổng hợp lặp lại đáng cân nhắc. **Workload và kế hoạch truy vấn**, không phải trực giác về số bảng, mới định hướng quyết định.

## 4. Tối ưu thiết kế chuẩn hóa trước khi phi chuẩn hóa

Trước khi thêm cột dư thừa, hãy kiểm tra những phương án thường ít rủi ro hơn.

### 4.1. Chỉ mục theo mẫu truy vấn

Ví dụ màn hình tìm đơn theo khách và thời gian:

```sql
CREATE INDEX idx_orders_customer_created
ON commerce_lab.orders (customer_id, created_at DESC)
INCLUDE (status);
```

Truy vấn:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT o.order_id, o.created_at, o.status
FROM commerce_lab.orders AS o
WHERE o.customer_id = 1
ORDER BY o.created_at DESC
LIMIT 50;
```

`INCLUDE` cho phép lưu những cột không thuộc khóa tìm kiếm trong index B-tree. PostgreSQL **có thể** dùng index-only scan khi điều kiện visibility map và kế hoạch phù hợp; không được kết luận truy vấn chắc chắn không đọc heap chỉ vì có `INCLUDE`.

Nếu truy vấn chậm do thiếu chỉ mục, phi chuẩn hóa tên khách hoặc tổng tiền có thể không giải quyết đúng điểm nghẽn.

### 4.2. Viết lại truy vấn thay vì sao chép dữ liệu

Ví dụ, không phải lúc nào cũng cần lấy toàn bộ dòng hàng trước khi lọc số lượng:

```sql
SELECT
    o.order_id,
    o.created_at,
    (
        SELECT COALESCE(SUM(i.quantity * i.unit_price), 0)
        FROM commerce_lab.order_items AS i
        WHERE i.order_id = o.order_id
    ) AS total_amount
FROM commerce_lab.orders AS o
WHERE o.customer_id = 1
ORDER BY o.created_at DESC
LIMIT 20;
```

Mẫu truy vấn tương quan này có thể phù hợp khi chỉ lấy ít đơn và có chỉ mục theo `order_id`. Nhưng **không mặc định** nó nhanh hơn cách `GROUP BY`: PostgreSQL có thể chọn kế hoạch khác nhau theo số đơn, phân bố dòng và thống kê. Cần đo cả hai cách trên dữ liệu đại diện.

### 4.3. VIEW không tự phi chuẩn hóa vật lý

Một view thường là định nghĩa truy vấn:

```sql
CREATE VIEW commerce_lab.v_order_totals AS
SELECT
    o.order_id,
    COALESCE(SUM(i.quantity * i.unit_price), 0)
        AS total_amount
FROM commerce_lab.orders AS o
LEFT JOIN commerce_lab.order_items AS i
  ON i.order_id = o.order_id
GROUP BY o.order_id;
```

Sau đó:

```sql
SELECT *
FROM commerce_lab.v_order_totals
WHERE order_id = 101;
```

View giúp tái sử dụng logic và tạo giao diện đọc nhất quán, nhưng **không mặc nhiên lưu sẵn kết quả**. Truy vấn vẫn được PostgreSQL lập kế hoạch dựa trên định nghĩa view. Muốn lưu sẵn kết quả cần cơ chế như materialized view hoặc bảng tổng hợp do ứng dụng/trigger duy trì.

## 5. Lưu tổng tiền đơn hàng: một trường hợp phi chuẩn hóa rõ ràng

Giả sử đã đo và thấy việc tính tổng cho hàng loạt đơn quá tốn kém. Ta có thể lưu thêm `orders.total_amount`:

```sql
ALTER TABLE commerce_lab.orders
ADD COLUMN total_amount numeric(18, 2) NOT NULL DEFAULT 0
    CHECK (total_amount >= 0);
```

Từ lúc này, cùng một sự thật xuất hiện ở hai chỗ:

```text
order_items:
  (quantity, unit_price) theo từng dòng
            |
            | SUM(quantity * unit_price)
            v
orders.total_amount
```

**Bất biến dữ liệu** (*data invariant*) cần duy trì là:

```text
Với mỗi order_id:

orders.total_amount
    = SUM(order_items.quantity * order_items.unit_price)

Quy ước: đơn không có dòng hàng có total_amount = 0
```

Trong ví dụ, tổng tiền không gồm thuế, phí vận chuyển, giảm giá hay hoàn tiền. Nếu nghiệp vụ có các thành phần đó, định nghĩa tổng phải được viết lại rõ ràng; không dùng `SUM(quantity * unit_price)` như một công thức doanh thu phổ quát.

### 5.1. Sai sót nếu cập nhật hai nơi một cách rời rạc

Ví dụ lỗi:

```sql
-- Tăng số lượng một dòng hàng.
UPDATE commerce_lab.order_items
SET quantity = 3
WHERE order_id = 101 AND line_no = 1;

-- Quên cập nhật commerce_lab.orders.total_amount.
```

Nếu ứng dụng đọc `orders.total_amount`, giá trị có thể vẫn là 330000.00 trong khi tổng thực từ dòng hàng đã thành 480000.00. **Một chỉ mục tốt không thể sửa một giá trị đã lưu sai.**

### 5.2. Ba chiến lược duy trì giá trị dẫn xuất

| Chiến lược | Cách làm | Độ nhất quán kỳ vọng |
| --- | --- | --- |
| **Transaction trong application/service** | Mọi thay đổi dòng hàng và tổng tiền thực hiện trong cùng transaction | Có thể mạnh nếu mọi writer tuân thủ và xử lý concurrency đúng. |
| **Database trigger** | PostgreSQL cập nhật tổng khi row của `order_items` thay đổi | Có thể duy trì đồng bộ trong cùng transaction, nếu trigger bao phủ đầy đủ mọi đường ghi. |
| **Xử lý bất đồng bộ** | Worker/stream đọc sự kiện và cập nhật tổng/bảng chiếu | Có khoảng trễ; cần idempotency, retry và reconciliation. |

Chọn chiến lược theo **đường ghi thực tế**, quyền kiểm soát source of truth và yêu cầu nhất quán. Với một database PostgreSQL duy nhất và tổng tiền ảnh hưởng giao dịch tài chính, cập nhật **cùng transaction** thường là lựa chọn dễ diễn giải hơn so với việc chấp nhận kết quả có thể trễ.

## 6. Giữ nhất quán mạnh bằng transaction trong PostgreSQL

Transaction cho phép cập nhật nhiều bảng dưới cùng ranh giới commit:

```sql
BEGIN;

INSERT INTO commerce_lab.order_items
    (order_id, line_no, product_code, quantity, unit_price)
VALUES
    (101, 3, 'PEN-BLUE', 2, 12000.00);

UPDATE commerce_lab.orders AS o
SET total_amount = (
    SELECT COALESCE(SUM(i.quantity * i.unit_price), 0)
    FROM commerce_lab.order_items AS i
    WHERE i.order_id = o.order_id
)
WHERE o.order_id = 101;

COMMIT;
```

Nếu lỗi xuất hiện trước `COMMIT` và transaction bị rollback, hai thao tác đều bị hủy. Khi commit thành công, người đọc bên ngoài transaction không nhìn thấy trạng thái “có dòng hàng mới nhưng tổng tiền chưa cập nhật” do hai lệnh nằm trong một transaction, **với điều kiện mọi đường ghi liên quan đều tuân thủ quy trình**.

Tuy nhiên, ví dụ này là **minh họa transaction đơn giản**, chưa phải giải pháp an toàn trước mọi tình huống ghi đồng thời. Hai transaction cùng thêm dòng hàng và tính lại tổng theo snapshot khác nhau có thể dẫn đến kết quả không khớp nếu không có chiến lược khóa/đồng bộ đúng.

### 6.1. Khóa hàng cha trước khi thay đổi dòng hàng

Một cách thiết kế luồng ghi nhất quán là yêu cầu mọi writer cập nhật dòng hàng của cùng đơn phải **khóa hàng `orders` trước**, sau đó mới sửa chi tiết và tính tổng.

```sql
BEGIN;

-- Các writer của cùng order_id phải tuân thủ quy ước này.
SELECT order_id
FROM commerce_lab.orders
WHERE order_id = 101
FOR UPDATE;

UPDATE commerce_lab.order_items
SET quantity = 3
WHERE order_id = 101
  AND line_no = 1;

UPDATE commerce_lab.orders AS o
SET total_amount = (
    SELECT COALESCE(SUM(i.quantity * i.unit_price), 0)
    FROM commerce_lab.order_items AS i
    WHERE i.order_id = o.order_id
)
WHERE o.order_id = 101;

COMMIT;
```

Nếu mọi writer đều khóa `orders(order_id)` trước khi thay đổi `order_items`, họ được tuần tự hóa theo từng đơn ở bước lấy khóa. Bước tính tổng sẽ không cạnh tranh với một writer khác cùng tuân thủ quy tắc trên tại cùng thời điểm.

**Giới hạn:** nếu có một code path khác chèn/sửa dòng hàng mà không dùng quy ước khóa, tính nhất quán có thể lại bị phá vỡ. Không thể gọi một quy tắc trong README là ràng buộc cưỡng chế của database. Muốn bảo vệ toàn bộ đường ghi, cần quản lý quyền hoặc cơ chế database phù hợp.

### 6.2. Đừng dùng transaction như một phép màu

Chỉ vì hai `UPDATE` nằm trong cùng `BEGIN ... COMMIT` **không đủ** để xử lý mọi cuộc đua:

- Đọc trước rồi tính toán trên giá trị cũ có thể gây *lost update* nếu thiếu khóa hoặc toán tử cập nhật phù hợp.
- Các transaction có thể bị deadlock khi lấy khóa theo thứ tự khác nhau.
- Ở isolation level `SERIALIZABLE`, PostgreSQL có thể hủy transaction bằng lỗi serialization; ứng dụng phải retry **toàn transaction** theo chính sách an toàn.
- Ranh giới transaction không bao trùm tự động các thay đổi ở một hệ thống ngoài PostgreSQL.

Đối với dữ liệu được phi chuẩn hóa, cần thiết kế **quy tắc concurrency** rõ như thiết kế ràng buộc nghiệp vụ.

## 7. Duy trì tổng bằng trigger trong cùng transaction

Một trigger PostgreSQL có thể tự động điều chỉnh `orders.total_amount` mỗi khi `order_items` thay đổi. Ví dụ dưới đây dùng **cập nhật delta**, tức cộng phần thay đổi thay vì quét và tính lại toàn bộ dòng hàng.

Vì bảng `orders` vừa được thêm cột `total_amount` mặc định 0, trước khi kích hoạt trigger cho dữ liệu hiện có, cần **backfill** tổng từ những dòng hàng đã lưu (ở lab không có writer cạnh tranh):

```sql
UPDATE commerce_lab.orders AS o
SET total_amount = (
    SELECT COALESCE(SUM(i.quantity * i.unit_price), 0)
    FROM commerce_lab.order_items AS i
    WHERE i.order_id = o.order_id
);
```

Trong production đang có ghi đồng thời, không nên chạy bản backfill trên một snapshot tùy ý rồi coi nó luôn chính xác: cần lên kế hoạch điều phối viết dữ liệu, khóa, migration hai giai đoạn hoặc cơ chế watermark/reconciliation thích hợp. Ví dụ này giả định lab đã được đồng bộ trước khi tạo trigger.

### 7.1. Hàm trigger tính delta

```sql
CREATE OR REPLACE FUNCTION commerce_lab.adjust_order_total()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_order_id bigint;
    v_old_amount numeric(18, 2) := 0;
    v_new_amount numeric(18, 2) := 0;
BEGIN
    IF TG_OP = 'INSERT' THEN
        v_order_id := NEW.order_id;
        v_new_amount := NEW.quantity * NEW.unit_price;

    ELSIF TG_OP = 'DELETE' THEN
        v_order_id := OLD.order_id;
        v_old_amount := OLD.quantity * OLD.unit_price;

    ELSIF TG_OP = 'UPDATE' THEN
        IF OLD.order_id IS DISTINCT FROM NEW.order_id THEN
            RAISE EXCEPTION
                'Changing order_id is not supported by adjust_order_total';
        END IF;

        v_order_id := NEW.order_id;
        v_old_amount := OLD.quantity * OLD.unit_price;
        v_new_amount := NEW.quantity * NEW.unit_price;
    END IF;

    UPDATE commerce_lab.orders
    SET total_amount =
        total_amount + v_new_amount - v_old_amount
    WHERE order_id = v_order_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Order % does not exist', v_order_id;
    END IF;

    RETURN NULL; -- Giá trị trả về của AFTER row trigger bị bỏ qua.
END;
$$;

CREATE TRIGGER trg_adjust_order_total
AFTER INSERT OR UPDATE OR DELETE
ON commerce_lab.order_items
FOR EACH ROW
EXECUTE FUNCTION commerce_lab.adjust_order_total();
```

Trong trigger:

- `INSERT` tạo delta dương bằng tiền dòng hàng mới.
- `DELETE` tạo delta âm bằng tiền dòng hàng bị xóa.
- `UPDATE` lấy giá trị mới trừ giá trị cũ.
- Không cho đổi `order_id` bằng một `UPDATE` vì sẽ cần đồng bộ cả **hai đơn hàng** và quy tắc khóa phức tạp hơn. Trong ví dụ, trigger chủ động báo lỗi để transaction bị rollback.
- `UPDATE orders SET total_amount = total_amount + delta` là phép cập nhật trên hàng `orders` và được PostgreSQL xử lý theo cơ chế khóa hàng/transaction, giúp tránh kiểu ghi đè tổng được tính trước ở phía client.

**Điểm quan trọng:** `AFTER ROW trigger` chạy trong **cùng transaction** với thao tác tạo ra nó. Nếu phép điều chỉnh tổng gặp lỗi, thao tác dữ liệu gây ra trigger cũng không thể commit thành công theo cách thông thường.

### 7.2. Thử INSERT, UPDATE và DELETE

Sau khi trigger được tạo, mỗi thao tác sau sẽ điều chỉnh tổng tương ứng:

```sql
-- Thêm một dòng 2 * 12.000 = 24.000 cho đơn 101.
INSERT INTO commerce_lab.order_items
    (order_id, line_no, product_code, quantity, unit_price)
VALUES
    (101, 3, 'PEN-BLUE', 2, 12000.00);

-- Tăng số lượng dòng 1 từ 2 lên 3: tổng tăng thêm 150.000.
UPDATE commerce_lab.order_items
SET quantity = 3
WHERE order_id = 101 AND line_no = 1;

-- Xóa dòng 3: tổng giảm 24.000.
DELETE FROM commerce_lab.order_items
WHERE order_id = 101 AND line_no = 3;
```

Nếu đang làm lab theo thứ tự trong bài, chú ý phần 6 đã minh họa một `INSERT` với `line_no = 3`. **Không chạy đồng thời cả hai đoạn minh họa như một script duy nhất khi dòng 3 đã tồn tại**, vì khóa chính sẽ từ chối insert trùng. Có thể reset lab, bỏ qua thao tác trùng hoặc chọn số dòng chưa sử dụng.

Kiểm tra đối chiếu:

```sql
SELECT
    o.order_id,
    o.total_amount AS stored_total,
    COALESCE(SUM(i.quantity * i.unit_price), 0)
        AS calculated_total
FROM commerce_lab.orders AS o
LEFT JOIN commerce_lab.order_items AS i
  ON i.order_id = o.order_id
GROUP BY o.order_id, o.total_amount
ORDER BY o.order_id;
```

### 7.3. Rủi ro và giới hạn của trigger

Trigger giúp tập trung logic tại database nhưng không có nghĩa “không thể xảy ra sai lệch”:

1. **Mọi loại thao tác phải được bao phủ.** Trigger row-level `INSERT/UPDATE/DELETE` không tự xử lý `TRUNCATE` theo cách `DELETE` từng hàng; cần cấm hoặc quản lý những đường vận hành khác làm thay đổi nguồn dữ liệu.
2. **Chi phí ghi tăng.** Mỗi thay đổi dòng hàng còn làm thay đổi hàng `orders`. Một đơn có nhiều writer có thể trở thành điểm tranh chấp khóa.
3. **Deadlock vẫn có thể xảy ra.** Nhiều transaction sửa nhiều đơn theo thứ tự khác nhau có thể lấy khóa ngược nhau. Cần thống nhất thứ tự khóa và xử lý retry an toàn khi có deadlock.
4. **Thao tác ghi đặc biệt cần xem xét.** Bulk import, thay đổi partition, trigger bị disable bởi người có đặc quyền hoặc các đường dữ liệu ngoài PostgreSQL có thể không tuân thủ kỳ vọng.
5. **Xóa hàng cha cần quy trình riêng.** Ví dụ dùng foreign key mặc định, không dùng `ON DELETE CASCADE`. Nếu thiết kế cascade, phải xét thứ tự trigger và hàng cha được cập nhật trong lúc xóa.
6. **Logic không được phân tán mơ hồ.** Không để ứng dụng vừa tự cộng tổng lại vừa có trigger cộng tổng lần thứ hai.

Trigger phù hợp khi tất cả thay đổi liên quan nằm cùng PostgreSQL database và muốn database cưỡng chế việc cập nhật dẫn xuất. Với hệ thống có nhiều nguồn dữ liệu, xử lý sự kiện ngoài database hoặc nghiệp vụ cần độ trễ có kiểm soát, một mô hình khác có thể dễ vận hành hơn.

## 8. Đọc trigger dưới góc độ concurrency

Giả sử transaction A và B đồng thời thêm hai dòng hàng khác nhau vào đơn 101.

```text
Transaction A                           Transaction B
--------------                          --------------
INSERT item A                            INSERT item B
  |                                        |
  v                                        v
AFTER trigger                            AFTER trigger
UPDATE orders.total_amount              UPDATE orders.total_amount
  |                                        |
  +---- lấy khóa trên hàng orders(101) ---+
  |                                        |
COMMIT                         chờ / tiếp tục khi khóa được giải phóng
                                           |
                                         COMMIT
```

Nếu cả hai trigger dùng `total_amount = total_amount + delta`, PostgreSQL xử lý các cập nhật trên cùng hàng theo khóa và thứ tự transaction, nên không đơn giản xảy ra lỗi “cả hai đều đọc 330.000 rồi ghi kết quả riêng lên nhau” như cách cập nhật giá trị tính sẵn từ client mà không khóa.

Tuy nhiên:

- Nếu A đang giữ khóa lâu, B phải chờ, làm tăng latency.
- Nếu một transaction cập nhật nhiều đơn theo thứ tự `101 → 102`, còn transaction khác theo `102 → 101`, có thể xuất hiện deadlock.
- Nếu logic trigger thực hiện thêm truy vấn và side effect phức tạp, cần cân nhắc isolation level, thứ tự khóa và khả năng retry.

**Không phải mọi tính toán aggregate đều an toàn chỉ vì nằm trong trigger.** Một trigger kiểu “SELECT SUM(...) rồi ghi đè tổng” có thể có race khi truy vấn dùng snapshot chưa nhìn thấy transaction khác. Cách delta làm ví dụ cho một pattern đơn giản hơn, nhưng vẫn cần kiểm thử trên workload thật.

### 8.1. SERIALIZABLE không loại bỏ nhu cầu xử lý lỗi

PostgreSQL hỗ trợ `SERIALIZABLE` isolation, có thể ngăn những kết quả không phù hợp với một thứ tự giao dịch tuần tự bằng cơ chế phát hiện xung đột và hủy transaction. Khi gặp SQLSTATE `40001` (serialization_failure), ứng dụng thường cần retry **toàn bộ logic transaction** theo chính sách giới hạn số lần thử.

Vì vậy không nên đặt `SERIALIZABLE` rồi kết luận mọi cập nhật dẫn xuất sẽ tự động thành công, không phát sinh lỗi hoặc không có chi phí. Hãy chọn mức isolation dựa trên bất biến cần bảo vệ, khả năng retry và đo hiệu năng.

## 9. Snapshot lịch sử: không phải cứ khác bảng gốc là sai

Ví dụ khách hàng Lan đổi tên sau khi đặt hàng:

```sql
UPDATE commerce_lab.customers
SET full_name = 'Nguyễn Lan'
WHERE customer_id = 1;
```

Khi hiển thị danh bạ hoặc trang tài khoản, tên hiện tại là `'Nguyễn Lan'`. Nhưng trên hóa đơn đã phát hành trước khi đổi tên, hệ thống có thể cần hiển thị **tên tại thời điểm mua hàng**, không phải tên mới.

Khi đó, lưu cột snapshot là hợp lý:

```sql
ALTER TABLE commerce_lab.orders
ADD COLUMN customer_name_at_order text;
```

Tại thời điểm xác nhận đơn, ứng dụng có thể chụp giá trị trong cùng transaction:

```sql
BEGIN;

UPDATE commerce_lab.orders AS o
SET
    customer_name_at_order = c.full_name,
    status = 'confirmed'
FROM commerce_lab.customers AS c
WHERE o.customer_id = c.customer_id
  AND o.order_id = 101
  AND o.status = 'draft';

COMMIT;
```

Sau khi xác nhận, `customer_name_at_order` mang ý nghĩa lịch sử độc lập. Nếu tên khách hiện tại tiếp tục thay đổi, **không nên tự động đồng bộ snapshot cho giống `customers.full_name`**, trừ khi nghiệp vụ và quy định dữ liệu có yêu cầu chỉnh sửa cụ thể.

### 9.1. Đặt tên cột thể hiện chính sách cập nhật

So sánh:

```text
orders.customer_name                -- Mơ hồ: hiện tại hay lúc đặt?
orders.customer_name_at_order       -- Rõ: snapshot lúc đặt
orders.current_customer_name_cache  -- Rõ: bản sao phục vụ đọc, cần sync
```

Đặt tên và documentation rõ ràng giúp người đọc phân biệt **snapshot intentional** với **cached duplicate**. Hai giá trị có thể khác nhau mà chỉ một trong hai là lỗi.

### 9.2. Các ví dụ snapshot hợp lý

- Giá bán/thuế suất/điều khoản áp dụng tại thời điểm chốt đơn.
- Địa chỉ giao hàng được khách xác nhận cho đơn.
- Tên công ty trên chứng từ tại thời điểm phát hành.
- Phiên bản cấu hình chính sách mà giao dịch sử dụng.

Một sản phẩm có giá hiện tại 200.000 không có nghĩa dòng hàng của đơn đã chốt tháng trước phải tự cập nhật thành 200.000. Trong nhiều hệ thống, `order_items.unit_price` vốn là **giá giao dịch**, không phải bản sao luôn đồng bộ với `products.current_price`.

**Câu hỏi đúng không phải “dữ liệu có lặp hay không?” mà là “hai cột đại diện cùng sự thật tại cùng thời điểm hay hai sự thật khác thời điểm?”**

## 10. Materialized view: lưu sẵn kết quả truy vấn để phục vụ báo cáo

PostgreSQL hỗ trợ `MATERIALIZED VIEW`: lưu kết quả của một truy vấn vào một đối tượng được quản lý như dữ liệu đã materialize. Truy vấn đọc materialized view không phải tính lại toàn bộ query gốc mỗi lần.

Ví dụ báo cáo số đơn và tổng tiền theo ngày, tính theo giờ Việt Nam:

```sql
CREATE MATERIALIZED VIEW commerce_lab.mv_daily_sales AS
SELECT
    (o.created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS sale_date,
    count(*) AS order_count,
    COALESCE(SUM(o.total_amount), 0) AS gross_amount
FROM commerce_lab.orders AS o
WHERE o.status = 'confirmed'
GROUP BY (o.created_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date
WITH DATA;
```

Sau đó:

```sql
SELECT *
FROM commerce_lab.mv_daily_sales
ORDER BY sale_date DESC
LIMIT 30;
```

Ở đây:

- `gross_amount` dựa trên giá trị `orders.total_amount` đã được duy trì theo chính sách của hệ thống; nếu cột này sai, materialized view cũng kế thừa sai sót.
- Chỉ lấy `confirmed` là **quy ước ví dụ**, không phải định nghĩa doanh thu kế toán phổ quát.
- Việc chuyển `timestamptz` sang ngày được cố định bằng múi giờ `Asia/Ho_Chi_Minh` để tránh ngày báo cáo thay đổi tùy `TimeZone` session.

### 10.1. Materialized view không tự cập nhật

Sau khi bảng gốc thay đổi, materialized view **không tự động refresh ngay**:

```sql
REFRESH MATERIALIZED VIEW commerce_lab.mv_daily_sales;
```

Lệnh này làm mới dữ liệu được lưu theo kết quả truy vấn tại lần refresh. Cho đến lần làm mới tiếp theo, người đọc có thể thấy tổng hợp cũ.

Điều đó tạo ra một **đánh đổi nhất quán**:

```text
orders thay đổi       10:00
người dùng xem MV      10:01  -> có thể thấy dữ liệu cũ
REFRESH MV             10:05
người dùng xem MV      10:06  -> thấy kết quả của lần refresh
```

Thời điểm thực tế phụ thuộc lịch refresh và thời gian hoàn thành refresh. Không nên gọi đây là “real-time dashboard” nếu không có cơ chế cập nhật theo SLA thời gian thực.

### 10.2. REFRESH CONCURRENTLY

Nếu muốn giảm việc khóa truy cập đọc vào materialized view trong lúc refresh, PostgreSQL hỗ trợ:

```sql
CREATE UNIQUE INDEX ux_mv_daily_sales_date
ON commerce_lab.mv_daily_sales (sale_date);

REFRESH MATERIALIZED VIEW CONCURRENTLY
    commerce_lab.mv_daily_sales;
```

`CONCURRENTLY` có các điều kiện tiên quyết. Một điều kiện trọng tâm là materialized view đã được populate và có **ít nhất một UNIQUE index thích hợp chỉ dùng tên cột, bao phủ mọi hàng** (không phải index biểu thức hoặc partial index). Ví dụ dùng `sale_date` là khóa duy nhất vì mỗi ngày chỉ có một hàng.

`CONCURRENTLY` giúp giảm chặn các lượt `SELECT` trên materialized view so với refresh thông thường, nhưng **không miễn phí**: nó cần thêm công việc I/O/CPU và không đồng nghĩa nhiều refresh trên cùng view sẽ chạy đồng thời. Cần đo thời gian refresh và tải trên nguồn dữ liệu.

### 10.3. Khi nào dùng materialized view?

Phù hợp khi:

- Query tổng hợp tốn kém và được đọc nhiều lần.
- Có thể chấp nhận dữ liệu tại một mốc refresh.
- Không cần cập nhật từng dòng summary tức thời sau mỗi giao dịch.
- Có lịch làm mới, monitoring và cơ chế xử lý khi refresh lỗi.

Không phù hợp nếu mỗi giao dịch thanh toán phải đọc ngay tổng số chính xác cho mọi đối tượng, hoặc nếu chi phí refresh toàn bộ lớn hơn lợi ích.

## 11. Bảng tổng hợp được cập nhật dần bằng sự kiện

Thay vì refresh toàn bộ materialized view, có thể duy trì **bảng tổng hợp tăng dần**.

Ví dụ bảng doanh số theo ngày:

```sql
CREATE TABLE commerce_lab.daily_sales_summary (
    sale_date date PRIMARY KEY,
    confirmed_order_count bigint NOT NULL DEFAULT 0
        CHECK (confirmed_order_count >= 0),
    gross_amount numeric(18, 2) NOT NULL DEFAULT 0
);
```

Khi có một sự kiện đơn được xác nhận thành công, worker hoặc transaction tương ứng có thể dùng upsert:

```sql
INSERT INTO commerce_lab.daily_sales_summary
    (sale_date, confirmed_order_count, gross_amount)
VALUES
    (DATE '2026-10-05', 1, 330000.00)
ON CONFLICT (sale_date)
DO UPDATE SET
    confirmed_order_count =
        commerce_lab.daily_sales_summary.confirmed_order_count
        + EXCLUDED.confirmed_order_count,
    gross_amount =
        commerce_lab.daily_sales_summary.gross_amount
        + EXCLUDED.gross_amount;
```

`ON CONFLICT` xử lý cạnh tranh tại khóa `sale_date` và phép cộng cập nhật trên hàng đang bị khóa thích hợp. Tuy nhiên, **nó không tự biết hai sự kiện nhận được là cùng một sự kiện nghiệp vụ**.

Nếu một event “đơn 101 đã xác nhận” được xử lý hai lần, cùng một lệnh có thể cộng hai lần. Database có thể nhất quán về mặt transaction mà **số liệu nghiệp vụ vẫn sai vì duplicate event**.

### 11.1. Cập nhật tổng hợp với idempotency key

Một phương án là ghi nhận những event đã xử lý ngay trong cùng PostgreSQL transaction:

```sql
CREATE TABLE commerce_lab.processed_projection_events (
    projection_name text NOT NULL,
    event_id uuid NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (projection_name, event_id)
);
```

Ví dụ xử lý một event bằng CTE:

```sql
BEGIN;

WITH accepted AS (
    INSERT INTO commerce_lab.processed_projection_events
        (projection_name, event_id)
    VALUES
        ('daily_sales', '1fa80ca8-e121-43cf-8afe-27124d141f42'::uuid)
    ON CONFLICT (projection_name, event_id) DO NOTHING
    RETURNING event_id
)
INSERT INTO commerce_lab.daily_sales_summary
    (sale_date, confirmed_order_count, gross_amount)
SELECT
    DATE '2026-10-05', 1, 330000.00
FROM accepted
ON CONFLICT (sale_date)
DO UPDATE SET
    confirmed_order_count =
        commerce_lab.daily_sales_summary.confirmed_order_count + 1,
    gross_amount =
        commerce_lab.daily_sales_summary.gross_amount
        + EXCLUDED.gross_amount;

COMMIT;
```

Nếu chạy lại cùng `event_id` cho projection `daily_sales`, CTE `accepted` không trả hàng; câu `INSERT ... SELECT` tiếp theo không tạo dòng và không cộng thêm vào summary. Nếu một bước lỗi trước `COMMIT`, toàn transaction rollback.

Điểm cần nhớ:

- Event ID phải **ổn định qua retry**, không sinh UUID mới mỗi lần xử lý lại cùng sự kiện.
- Ghi nhận event và thay đổi summary cần nằm trong **cùng transaction** để tránh “đã đánh dấu processed nhưng chưa cộng” hoặc ngược lại.
- Việc tạo sự kiện từ nguồn và giao sự kiện tới consumer ở hệ thống ngoài PostgreSQL vẫn cần thiết kế riêng. Ví dụ chỉ xử lý idempotency **tại consumer trong một database**.
- Khi hủy đơn hoặc hoàn tiền, hệ thống cần sự kiện bù trừ, không chỉ có luồng tăng doanh số.

### 11.2. Mức độ nhất quán cuối cùng

Nếu một worker nhận event qua hàng đợi và cập nhật `daily_sales_summary` sau vài giây hoặc vài phút, bảng này là một **projection có độ trễ**. Cần xác định SLA:

```text
Ví dụ chính sách:
  Dữ liệu source được commit lúc T.
  Projection cần bắt kịp trong vòng 60 giây ở điều kiện thường.
  Nếu lag > 60 giây: cảnh báo và đánh dấu dashboard stale.
```

Con số 60 giây là ví dụ sản phẩm, không phải bảo đảm của PostgreSQL. Cần đo độ trễ **từ lúc transaction nguồn commit** đến lúc projection áp dụng xong, không chỉ độ trễ nhận message từ queue.

## 12. Đồng bộ dữ liệu bằng application, trigger hay CDC?

Sơ đồ lựa chọn:

```text
                   Có dữ liệu cần lưu thêm
                            |
                 Có bắt buộc nhất quán
                 ngay tại mỗi COMMIT?
                    /                 \
                  Có                 Không
                   |                   |
        Cùng database/transaction?   Có SLA lag + đối soát?
             /          \             /          \
           Có           Không        Có           Không
            |             |           |            |
      Transaction/      Thiết kế    Event/CDC    Chưa sẵn sàng
      trigger           workflow    projection   làm bản sao
                        và lỗi      + retry      đáng tin cậy
```

| Cơ chế | Thuận lợi | Rủi ro/chi phí |
| --- | --- | --- |
| Application transaction | Logic nghiệp vụ tập trung trong service, có thể phối hợp nhiều bảng | Các writer khác có thể bỏ qua quy trình; cần khóa và test concurrency. |
| Database trigger | Có thể cưỡng chế đồng bộ ở tầng database, cùng transaction | Logic ẩn khỏi câu SQL gọi, tăng thời gian ghi, tranh chấp khóa, cần quản lý migration. |
| Materialized view + refresh | Không phải tự viết logic delta; dễ đọc như bảng | Dữ liệu cũ giữa các lần refresh; refresh có chi phí và lịch vận hành. |
| Event-driven projection | Có thể tách tải đọc/ghi, mở rộng consumer | Retry, duplicate, out-of-order events, lag, backfill và reconciliation. |
| Logical decoding/CDC | Lấy thay đổi database theo luồng thay vì chỉnh mọi code path | WAL retention, slot, schema evolution, thứ tự sự kiện và vận hành connector. |

### 12.1. CDC không tự động bảo đảm exactly-once

PostgreSQL hỗ trợ **logical decoding** và logical replication trong những điều kiện phù hợp. Một connector có thể đọc thay đổi từ WAL rồi xuất sự kiện cho hệ thống downstream.

Nhưng một transaction nguồn đã commit và một thông điệp gửi ra broker là **hai ranh giới khác nhau**. Nếu connector gửi event rồi bị crash trước khi lưu checkpoint tiến độ, event có thể được gửi lại. Đây là một lý do consumer phải thiết kế **idempotency** và xử lý sự kiện theo thứ tự/khoá cần thiết.

Ngoài ra, replication slot có thể giữ WAL khi consumer bị chậm; việc tạo projection mới cần kế hoạch monitor slot, giới hạn dung lượng và phục hồi khi thiếu lịch sử thay đổi.

### 12.2. Transactional outbox

Nếu ứng dụng vừa ghi đơn hàng vừa muốn phát sự kiện cho projection ngoài database, một pattern phổ biến là **transactional outbox**:

```text
BEGIN PostgreSQL transaction
   UPDATE orders
   INSERT outbox_events
COMMIT
          |
          v
Publisher/CDC đọc outbox
          |
          v
Broker / consumer
          |
          v
Projection được cập nhật có idempotency
```

Outbox giúp ghi thay đổi nghiệp vụ và **ý định phát sự kiện** trong cùng transaction PostgreSQL. Nó không làm việc truyền tới broker thành một distributed transaction tuyệt đối; publisher có thể gửi lặp, consumer có thể chạy lại, và vẫn cần retry cùng monitoring.

Phi chuẩn hóa qua event stream chỉ đáng tin khi hệ thống có cả **định danh event, chính sách xử lý lại, thứ tự sự kiện cần thiết và đối soát**.

## 13. JSONB và dữ liệu lồng nhau: không phải lúc nào cũng là phi chuẩn hóa

PostgreSQL có kiểu `jsonb`, hữu ích khi một thực thể có phần thuộc tính linh hoạt hoặc cần lưu snapshot tài liệu.

Ví dụ một đơn hàng lưu bản chụp địa chỉ giao nhận:

```sql
ALTER TABLE commerce_lab.orders
ADD COLUMN shipping_address_snapshot jsonb;

UPDATE commerce_lab.orders
SET shipping_address_snapshot = jsonb_build_object(
    'recipient', 'Lan',
    'city', 'Ho Chi Minh City',
    'street', 'Example Street 12'
)
WHERE order_id = 101;
```

Đây có thể là một snapshot hợp lý: địa chỉ của đơn đã chốt không nhất thiết thay đổi khi khách hàng chỉnh địa chỉ mặc định trong tài khoản.

Ngược lại, nhúng toàn bộ hồ sơ khách hàng, nhiều bản sao sản phẩm và lịch sử thanh toán vào JSONB của mỗi đơn chỉ để giảm JOIN có thể tạo chi phí lớn:

- Dữ liệu được sao chép nhiều lần và không rõ trường nào được cập nhật.
- Ràng buộc foreign key giữa trường lồng nhau và bảng khác không được thực thi như cột quan hệ thông thường.
- Truy vấn/cập nhật có thể cần xử lý cả cấu trúc JSONB và index chuyên biệt.
- Thay đổi schema khó kiểm soát nếu nhiều phiên bản payload tồn tại.
- Việc cập nhật một phần JSONB có thể tạo phiên bản tuple mới theo MVCC, không miễn phí chỉ vì biểu diễn dạng document.

**JSONB không mặc nhiên xấu hoặc tốt hơn schema quan hệ.** Hãy dùng cho cấu trúc linh hoạt/snapshot có ranh giới rõ, trong khi dữ liệu cần join, uniqueness, tham chiếu và cập nhật độc lập thường phù hợp hơn với bảng/cột có khóa và constraint.

### 13.1. Chỉ mục JSONB vẫn cần thiết kế theo workload

Nếu có truy vấn theo đường dẫn JSONB lặp lại, PostgreSQL hỗ trợ GIN/expression indexes trong những tình huống phù hợp.

```sql
CREATE INDEX idx_orders_shipping_snapshot
ON commerce_lab.orders
USING gin (shipping_address_snapshot);
```

Nhưng chỉ mục bổ sung tốn dung lượng và chi phí cập nhật. Không tạo GIN index cho mọi cột JSONB nếu truy vấn chủ yếu đọc toàn bộ đối tượng theo primary key.

## 14. Generated column: lưu giá trị dẫn xuất trong cùng một hàng

PostgreSQL có **generated columns**, cho phép database duy trì giá trị từ biểu thức dựa trên các cột của **chính hàng đó**, theo giới hạn biểu thức/phiên bản.

Ví dụ thêm thành tiền mỗi dòng:

```sql
ALTER TABLE commerce_lab.order_items
ADD COLUMN line_total numeric(18, 2)
GENERATED ALWAYS AS (quantity * unit_price) STORED;
```

Sau đó:

```sql
SELECT
    order_id, line_no, quantity, unit_price, line_total
FROM commerce_lab.order_items
WHERE order_id = 101
ORDER BY line_no;
```

Giá trị `line_total` được PostgreSQL tính từ `quantity` và `unit_price` theo định nghĩa, giảm nguy cơ ứng dụng tự ghi sai thành tiền của **một hàng**.

Tuy nhiên, không thể biến trực tiếp `orders.total_amount` thành generated column bằng một biểu thức `SUM(order_items)` tham chiếu nhiều hàng/bảng theo cách thông thường. Generated column có các giới hạn về biểu thức, tính bất biến (*immutability*), việc tham chiếu bảng khác và kiểu lưu trữ theo phiên bản.

| Nhu cầu | Công cụ phù hợp để cân nhắc |
| --- | --- |
| `line_total = quantity * unit_price` trong cùng hàng | Generated column, hoặc tính tại thời điểm truy vấn. |
| `order_total = SUM(items)` qua nhiều hàng | Query/VIEW, trigger, transaction hoặc bảng projection. |
| Tổng doanh số của hàng triệu đơn theo ngày | Materialized view hoặc bảng tổng hợp được duy trì. |
| Địa chỉ khách lúc xác nhận đơn | Snapshot có quy tắc bất biến rõ. |

Generated column không phải lời giải cho mọi phép phi chuẩn hóa, nhưng giúp giảm số nơi phải cập nhật thủ công đối với những biểu thức đủ đơn giản.

## 15. Tính nhất quán: mạnh, cuối cùng và lịch sử

Trước khi đánh đổi, cần đặt tên cho **cam kết nhất quán mà người dùng và service thực sự cần**.

### 15.1. Nhất quán đồng bộ tại ranh giới commit

Ví dụ một đơn không được xác nhận nếu tổng tiền đã lưu chưa bằng tổng tiền dòng hàng.

```text
COMMIT thành công
     |
     v
order_items và orders.total_amount
phải biểu diễn cùng trạng thái nghiệp vụ
```

Khi tất cả thay đổi được thực hiện trong cùng transaction và concurrency được xử lý đúng, người đọc khác không thấy “một nửa transaction” đã commit. Đây là yêu cầu thường gặp với dữ liệu mang tính quyết định như tiền cần thu, số dư, hạn mức hoặc tồn kho.

### 15.2. Nhất quán cuối cùng (*eventual consistency*)

Ví dụ dashboard quản lý có thể chấp nhận tổng số đơn mới trễ 30 giây.

```text
10:00:00 đơn được xác nhận trong orders
10:00:03 event được phát
10:00:12 projection được cập nhật
10:00:12 dashboard phản ánh đơn mới
```

Độ trễ thực tế cần đo và giám sát. “Eventual” không phải lời hứa rằng dữ liệu **chắc chắn** sẽ đúng mà không cần xử lý lỗi, backfill hay reconciliation. Một consumer ngừng chạy có thể khiến projection sai vô thời hạn nếu không có hệ thống phát hiện.

### 15.3. Snapshot lịch sử

`customer_name_at_order` khác `customers.full_name` sau khi đổi tên có thể hoàn toàn đúng. Nó không “chưa kịp đồng bộ”, mà **không được phép đồng bộ theo cơ chế thông thường** bởi hai giá trị mang ý nghĩa khác thời điểm.

### 15.4. Cùng một hệ thống có thể dùng nhiều mô hình

| Dữ liệu | Cam kết đề xuất tùy nghiệp vụ | Lý do |
| --- | --- | --- |
| Số dư được dùng để quyết định giao dịch thanh toán | Nhất quán mạnh trong transaction | Quyết định tiền không thể dựa vào một bản sao trễ không kiểm soát. |
| Tổng tiền của đơn đang chốt | Đồng bộ với dòng hàng tại lúc chốt | Hóa đơn không được sai giá trị. |
| Tên trên hóa đơn đã phát hành | Snapshot lịch sử | Giữ đúng thông tin tại thời điểm phát hành. |
| Biểu đồ doanh thu nội bộ | Eventual theo SLA | Có thể ưu tiên tốc độ đọc, cho phép trễ có thông báo. |
| Cache trang danh sách sản phẩm | Eventual theo TTL/invalidation | Có thể lấy lại từ nguồn sự thật khi hết hạn. |

Vấn đề không phải chọn “strong” cho mọi dữ liệu hoặc “eventual” cho mọi dữ liệu, mà là **xác định cam kết đúng cho từng luồng nghiệp vụ**.

## 16. PostgreSQL MVCC: đọc có nhất quán nhưng vẫn cần xác định nguồn

PostgreSQL sử dụng MVCC. Ở isolation level `READ COMMITTED` (mặc định), mỗi câu lệnh thường thấy snapshot phù hợp tại lúc câu lệnh bắt đầu. Điều này giúp một truy vấn tổng hợp không đọc tùy ý một nửa thay đổi của transaction khác đang chưa commit.

Nhưng có hai điểm cần phân biệt:

1. Một câu `SELECT` trên dữ liệu chuẩn hóa có thể đọc một snapshot nhất quán theo quy tắc isolation hiện hành.
2. Một cột cache đã bị cập nhật sai từ transaction trước là **dữ liệu đã commit sai về mặt nghiệp vụ**. MVCC không tự sửa cột đó.

Ví dụ:

```sql
SELECT
    o.total_amount,
    (
        SELECT COALESCE(SUM(i.quantity * i.unit_price), 0)
        FROM commerce_lab.order_items AS i
        WHERE i.order_id = o.order_id
    ) AS calculated_total
FROM commerce_lab.orders AS o
WHERE o.order_id = 101;
```

Nếu hai giá trị khác nhau trong cùng kết quả, cần điều tra quy tắc cập nhật dẫn xuất. Không thể chỉ bật isolation level cao hơn rồi kỳ vọng mọi giá trị lịch sử được “hòa giải”.

### 16.1. Nhiều SELECT riêng rẽ có thể nhìn các thời điểm khác

Ở `READ COMMITTED`, một transaction có hai câu `SELECT` liên tiếp có thể quan sát trạng thái đã commit mới hơn ở câu sau. Nếu ứng dụng tính một báo cáo bằng nhiều truy vấn tách rời và mong tất cả sử dụng cùng snapshot, cần xem transaction isolation/snapshot phù hợp.

Ví dụ đọc đối soát ở một snapshot ổn định:

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;

SELECT count(*) FROM commerce_lab.orders;
SELECT count(*) FROM commerce_lab.order_items;

COMMIT;
```

Điều này hữu ích cho **báo cáo đọc nhiều câu SQL**, nhưng giữ transaction dài vẫn có chi phí MVCC và có thể cản trở hoạt động dọn dẹp dữ liệu cũ. Không giữ một transaction đọc nhiều giờ chỉ để tránh thiết kế cơ chế snapshot/báo cáo tốt hơn.

## 17. Phát hiện độ lệch (*drift*) bằng reconciliation

Ngay cả khi ứng dụng hoặc trigger được viết cẩn thận, một hệ thống phi chuẩn hóa vận hành lâu dài vẫn nên có khả năng **đối soát giá trị lưu thêm với nguồn sự thật**.

Ví dụ tìm đơn có `total_amount` khác tổng chi tiết:

```sql
SELECT
    o.order_id,
    o.total_amount AS stored_total,
    COALESCE(SUM(i.quantity * i.unit_price), 0)
        AS recalculated_total,
    o.total_amount
        - COALESCE(SUM(i.quantity * i.unit_price), 0)
        AS difference
FROM commerce_lab.orders AS o
LEFT JOIN commerce_lab.order_items AS i
  ON i.order_id = o.order_id
GROUP BY o.order_id, o.total_amount
HAVING o.total_amount IS DISTINCT FROM
       COALESCE(SUM(i.quantity * i.unit_price), 0)
ORDER BY o.order_id;
```

Nếu truy vấn không trả hàng, các tổng được kiểm tra đang khớp trong snapshot của câu SQL. Nếu trả hàng, cần xác định **nguyên nhân** trước khi sửa:

- Có đường ghi bỏ qua trigger hoặc cập nhật thiếu transaction không?
- Có thao tác import/maintenance thay đổi `order_items` trực tiếp?
- Có event duplicate/out-of-order nếu tổng được cập nhật bất đồng bộ?
- Công thức tính tổng có bị đổi (chiết khấu, thuế, hoàn tiền) nhưng backfill chưa theo?
- Có race khi triển khai migration hoặc thời điểm chuyển cơ chế không?

### 17.1. Đối soát không phải tự động ghi đè mọi giá trị

Câu sửa đơn giản:

```sql
UPDATE commerce_lab.orders AS o
SET total_amount = (
    SELECT COALESCE(SUM(i.quantity * i.unit_price), 0)
    FROM commerce_lab.order_items AS i
    WHERE i.order_id = o.order_id
);
```

có thể hợp lý trong **lab đã dừng mọi writer**. Trong production đang ghi, nó có thể tranh chấp khóa hoặc ghi đè giá trị mới bằng một tổng tính từ snapshot không phù hợp.

Quy trình sửa thực tế nên gồm:

1. Xác định nhóm khóa bị lệch và mức độ ảnh hưởng.
2. Định nghĩa nguồn sự thật và công thức tính đúng.
3. Chọn cửa sổ kiểm soát ghi hoặc thiết kế transaction/locking để sửa từng nhóm khóa an toàn.
4. Ghi log/biên bản sửa và đo lại sự chênh lệch sau sửa.
5. Sửa nguyên nhân gốc: trigger, worker, idempotency, migration hoặc khóa concurrency.

Nếu không xử lý nguyên nhân, một công việc reconcile chạy mỗi đêm chỉ che giấu lỗi cập nhật lặp lại trong ngày.

### 17.2. Chỉ số drift cần giám sát

Với projection bất đồng bộ, có thể đo:

- **Lag:** độ trễ giữa commit nguồn và projection áp dụng.
- **Count divergence:** chênh số bản ghi giữa nguồn và projection theo khóa/kỳ.
- **Value divergence:** chênh số lượng, tiền, trạng thái hoặc hash theo nhóm.
- **Retry/dead-letter:** số event thất bại, xử lý lại, hoặc chưa thể áp dụng.
- **Backfill progress:** số khóa đã xử lý, vị trí cursor/watermark, phạm vi đã đối soát.

Với dữ liệu tài chính, cần xác định ngưỡng và quy trình phản hồi rõ ràng. Không chấp nhận một bảng tổng hợp sai vô thời hạn chỉ vì đã chọn nhất quán cuối cùng.

## 18. Migration từ chuẩn hóa sang phi chuẩn hóa

Việc thêm cột dư thừa vào một bảng đang phục vụ nhiều ứng dụng là **quá trình chuyển đổi dữ liệu và quyền sở hữu cập nhật**, không chỉ là một câu `ALTER TABLE`.

Một kế hoạch có kiểm soát:

### Giai đoạn 1 — Định nghĩa bất biến và chủ sở hữu

Ghi rõ:

```text
orders.total_amount:
  source of truth = order_items
  formula         = SUM(quantity * unit_price)
  consistency     = synchronous per transaction
  writer          = database trigger OR single application service
  repair          = recompute under controlled locking/window
```

Nếu chưa có đặc tả, người viết backend có thể tự cập nhật tổng, job báo cáo cũng cập nhật tổng, trigger lại cộng thêm một lần — mỗi thành phần đều “đúng ý riêng” nhưng hệ thống sai.

### Giai đoạn 2 — Thêm cấu trúc mới

Có thể thêm cột nullable trước hoặc đặt default theo kế hoạch migration:

```sql
ALTER TABLE commerce_lab.orders
ADD COLUMN total_amount_new numeric(18, 2);
```

Tên `total_amount_new` dùng để minh họa chiến lược triển khai nhiều giai đoạn, **không phải yêu cầu tạo thêm cột này nếu lab đã có `total_amount`**. Trên production, cần thiết kế để không tạo hai cột đích có ý nghĩa nhập nhằng.

### Giai đoạn 3 — Bảo vệ ghi mới và backfill cũ

Một lỗi điển hình:

```text
T1: Job backfill đọc tổng đơn 101 = 330.000
T2: Ứng dụng thêm dòng hàng và cập nhật tổng = 354.000
T3: Job backfill ghi lại 330.000

Kết quả: cột tổng bị cũ do race, dù cả hai bên đều chạy SQL hợp lệ.
```

Cần chọn một phương án cụ thể:

- Cửa sổ maintenance để tạm ngừng những writer liên quan, backfill rồi kiểm tra.
- Backfill theo nhóm khóa với khóa phù hợp và cơ chế tiếp nhận/đợi transaction ghi.
- Dùng event log/watermark để bắt lại mọi thay đổi xảy ra giữa snapshot và thời điểm cutover.
- Triển khai dual-write có kiểm soát, theo dõi/đối soát hai cách đọc trước khi chuyển hoàn toàn.

Không có một câu `UPDATE all rows` nào mặc nhiên an toàn với mọi workload đang ghi.

### Giai đoạn 4 — So sánh trước khi chuyển đường đọc

Trong một khoảng chạy song song, ứng dụng có thể tính tổng từ `order_items` và so với cột mới để phát hiện mismatch. Kết quả nên được đưa vào metric/log có kiểm soát, không làm lộ dữ liệu nhạy cảm.

Khi tỷ lệ sai khác nằm trong giới hạn **đúng theo yêu cầu nghiệp vụ** (thường bằng 0 với tổng phải đồng bộ), mới chuyển màn hình/endpoint đọc sang cột lưu sẵn.

### Giai đoạn 5 — Cutover và rollback

Khi chuyển đường đọc:

- Ghi rõ version ứng dụng và schema tương thích.
- Có phương án quay lại tính tổng từ nguồn nếu cột cache sai.
- Duy trì kiểm tra drift một thời gian sau cutover.
- Không vội xóa code/constraint nguồn trước khi xác nhận cơ chế mới ổn định.

**Rollback ứng dụng không tự rollback DDL**: một số thay đổi schema và dữ liệu cần kế hoạch đảo riêng. Mục tiêu của migration là vừa giảm rủi ro dữ liệu vừa tránh thay đổi cắt ngang khi các phiên bản service đang chạy chồng nhau.

## 19. Định lượng lợi ích và chi phí

Phi chuẩn hóa chỉ đáng cân nhắc nếu có bằng chứng về điểm nghẽn và lợi ích dự kiến.

### 19.1. Mô hình chi phí đơn giản

Giả sử:

```text
Hệ thống A:
  100.000 lần đọc tổng tiền/giờ
  1.000 lần thay đổi dòng hàng/giờ

Phương án chuẩn hóa:
  mỗi lần đọc phải cộng các dòng hàng liên quan

Phương án phi chuẩn hóa:
  mỗi lần đọc lấy cột orders.total_amount
  mỗi lần ghi phát sinh thêm cập nhật/tính toán tổng
```

Nếu tiết kiệm trung bình nhiều chi phí đọc hơn chi phí write bổ sung, phương án lưu tổng có thể có lợi. Nhưng phải đo:

| Chi phí | Chuẩn hóa | Phi chuẩn hóa |
| --- | --- | --- |
| Đọc một đơn theo ID | Query có thể phải SUM dòng hàng | Đọc thêm một cột đã lưu. |
| Ghi/sửa một dòng hàng | Sửa một bảng và index liên quan | Còn cập nhật tổng/trigger và WAL cho hàng cha. |
| Tranh chấp khóa | Thường ở dòng hàng bị sửa | Có thể thêm điểm nóng trên `orders`. |
| Dung lượng | Ít bản sao dữ liệu hơn | Thêm cột, index, summary, WAL và backup. |
| Tính đúng đắn | Ít trạng thái dẫn xuất phải duy trì | Cần invariant, kiểm thử và đối soát. |
| Vận hành | Schema ít cơ chế đồng bộ hơn | Thêm job refresh/consumer/monitor nếu dùng projection. |

Một mô hình ra quyết định mang tính khái niệm:

```text
Lợi ích đọc đo được
    > Chi phí ghi bổ sung
      + chi phí đồng bộ
      + chi phí giám sát/đối soát
      + rủi ro sai dữ liệu và xử lý sự cố
```

Không quy tất cả chi phí thành mili giây nếu hệ thống chưa có cách đo hậu quả nghiệp vụ. Một lỗi tổng tiền có thể nghiêm trọng hơn nhiều so với vài mili giây truy vấn nhanh hơn.

### 19.2. EXPLAIN (ANALYZE, BUFFERS)

PostgreSQL cho phép đo kế hoạch truy vấn với:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    o.order_id,
    COALESCE(SUM(i.quantity * i.unit_price), 0) AS total_amount
FROM commerce_lab.orders AS o
JOIN commerce_lab.order_items AS i
  ON i.order_id = o.order_id
WHERE o.customer_id = 1
GROUP BY o.order_id;
```

Và so sánh sau khi đã triển khai dữ liệu dẫn xuất:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, total_amount
FROM commerce_lab.orders
WHERE customer_id = 1;
```

Lưu ý: hai truy vấn đang khác nhau ở trường hợp đơn không có item vì truy vấn đầu dùng `JOIN` thường. Nếu cần so sánh kết quả nghiệp vụ tương đương với mọi đơn, dùng `LEFT JOIN` như phần trước.

`EXPLAIN ANALYZE` thực sự chạy câu query nên cần đánh giá tải khi đo trên production. Với dữ liệu quá ít, planner có thể chọn seq scan và kết quả benchmark không đại diện cho hệ thống hàng triệu dòng. Nên đo trên dữ liệu có số lượng, phân bố, tỷ lệ đọc/ghi và index gần thực tế.

### 19.3. Đo cả chiều ghi

Đừng chỉ benchmark trang dashboard. Với trigger hoặc cập nhật `orders.total_amount`, cần đo:

- Latency `INSERT/UPDATE/DELETE order_items`.
- Số transaction phải chờ lock hàng `orders`.
- Tần suất deadlock và serialization failure.
- Lượng WAL ghi thêm, mức phình dữ liệu/index và autovacuum.
- Tác động khi 10–100 người cùng sửa một đơn hoặc một summary key nóng.
- Thời gian khôi phục và ảnh hưởng tới backup/replication.

Một tối ưu giảm thời gian đọc 20% nhưng tăng tranh chấp khóa đến mức đơn hàng không commit được dưới tải cao có thể là lựa chọn kém.

## 20. Bảo mật và quyền truy cập của dữ liệu phi chuẩn hóa

Sao chép dữ liệu qua nhiều bảng hoặc projection cũng tạo thêm **đường truy cập và nơi lưu dữ liệu nhạy cảm**.

Ví dụ:

- Nếu lưu email khách hàng trong mọi đơn hàng, một tài khoản có `SELECT` trên `orders` có thể truy cập email dù không được đọc bảng `customers`.
- Một materialized view có thể chứa tên, số điện thoại hoặc địa chỉ đã được tổng hợp/snapshot.
- JSONB snapshot có thể giữ dữ liệu lâu hơn chính sách retention của bảng gốc.
- Log hoặc event stream có thể sao chép dữ liệu nhận dạng sang broker và downstream projection.

Do đó, ngoài performance và consistency, cần kiểm tra:

1. **Phạm vi quyền:** role nào được đọc bảng dẫn xuất, materialized view hoặc JSONB payload?
2. **Dữ liệu nhạy cảm:** có trường nào được sao chép mà downstream không cần không?
3. **Retention:** khi xóa/ẩn thông tin theo chính sách, các bản sao cache/snapshot có được xử lý đúng quy tắc không?
4. **Audit:** có thể biết nguồn nào đã tạo/cập nhật một bản sao dữ liệu không?
5. **Backup:** bản sao phụ có được sao lưu và khôi phục phù hợp, hoặc có thể tái tạo từ nguồn đáng tin không?

Một phép JOIN có thể chậm hơn chút nhưng giữ thông tin nhạy cảm ở một bảng được bảo vệ tốt hơn. Vì thế, phi chuẩn hóa không chỉ là bài toán SQL.

## 21. Checklist quyết định trước khi thêm một cột dư thừa

Với mỗi yêu cầu, hãy trả lời lần lượt:

1. **Truy vấn nào đang chậm?** Có số liệu `EXPLAIN (ANALYZE, BUFFERS)`, p95/p99 latency và tần suất truy cập không?
2. **Có phương án không lưu dữ liệu dư?** Chỉ mục, query rewrite, phân trang, summary trong ứng dụng, caching thích hợp?
3. **Thông tin được sao chép là cùng một sự thật hay snapshot lịch sử?**
4. **Nguồn sự thật nằm ở đâu?** Một bảng, nhiều bảng, hay một hệ thống ngoài PostgreSQL?
5. **Cập nhật phải đồng bộ khi commit hay được trễ?** Nếu trễ, SLA là gì và hiển thị thế nào?
6. **Writer nào được phép thay đổi nguồn?** Có script maintenance, migration, import hoặc CDC nào không?
7. **Concurrency và retry được xử lý thế nào?** Lock ordering, idempotency, deadlock, `SERIALIZABLE` và lỗi kết nối.
8. **Có kiểm tra drift không?** Truy vấn reconcile, cảnh báo, repair process và trách nhiệm vận hành.
9. **Có đường migration/rollback không?** Backfill và cutover có tránh ghi đè thay đổi mới?
10. **Dữ liệu bổ sung có ảnh hưởng quyền/retention không?** PII, snapshot, audit, downstream.

Nếu thiếu cơ chế duy trì và đối soát, “tăng tốc bằng cách lưu thêm cột” chỉ chuyển chi phí từ truy vấn sang **rủi ro âm thầm sai dữ liệu**.

## 22. Các sai lầm phổ biến

**1. “JOIN là chậm, nên luôn bỏ JOIN.”** PostgreSQL có thể JOIN rất hiệu quả với index/statistics phù hợp. Phi chuẩn hóa phải dựa trên đo lường chứ không phải định kiến về JOIN.

**2. “Đã có transaction thì mọi cache column luôn đúng.”** Transaction bảo đảm atomicity, nhưng code path khác, read-modify-write không khóa hoặc migration có thể phá invariant.

**3. “Trigger luôn sửa được mọi kiểu cập nhật.”** Trigger có loại sự kiện, phạm vi hàng/câu lệnh và hạn chế; `TRUNCATE` không hoạt động như `DELETE` từng hàng. Trigger phải được thiết kế cho toàn bộ đường ghi.

**4. “Chỉ cần lưu SUM vào generated column.”** Generated column thông thường dùng biểu thức trong cùng hàng với các giới hạn của PostgreSQL, không tự tổng hợp các hàng ở bảng con.

**5. “Materialized view tự cập nhật khi bảng nguồn đổi.”** Không. Cần `REFRESH MATERIALIZED VIEW` hoặc cơ chế cập nhật riêng.

**6. “REFRESH CONCURRENTLY nghĩa là miễn phí và tức thời.”** Nó giảm chặn đọc theo cơ chế phù hợp nhưng có điều kiện về unique index và vẫn tiêu thụ tài nguyên.

**7. “Dữ liệu snapshot khác bảng khách hiện tại là lỗi đồng bộ.”** Không phải lúc nào. Tên/địa chỉ/giá tại thời điểm giao dịch có thể cần giữ nguyên vì có ý nghĩa lịch sử.

**8. “ON CONFLICT bảo đảm consumer exactly-once.”** Nó bảo vệ xung đột khóa được thiết kế; nếu một sự kiện được cộng hai lần với khóa summary giống nhau, `ON CONFLICT DO UPDATE` vẫn có thể làm tăng số liệu hai lần.

**9. “Eventual consistency nghĩa là không phải giám sát.”** Sai. Nếu consumer ngừng, projection có thể trễ mãi. Cần SLA lag, retry, idempotency và reconciliation.

**10. “Tăng isolation level sẽ tự chữa dữ liệu đã lưu sai.”** Isolation kiểm soát cách transaction quan sát/cạnh tranh, không sửa bản sao đã commit sai trước đó.

**11. “JSONB luôn giúp truy vấn nhanh vì không cần JOIN.”** Có thể làm dữ liệu lặp nhiều, tăng chi phí cập nhật và khó enforce constraint; cần đo đường truy vấn thật.

**12. “Bảng báo cáo chỉ chứa dữ liệu tổng hợp nên không cần phân quyền.”** Projection vẫn có thể làm lộ thông tin nhạy cảm hoặc những giá trị kinh doanh cần bảo vệ.

**13. “Backfill không ảnh hưởng ghi mới.”** Một job ghi tổng theo snapshot cũ có thể ghi đè giá trị mới trong lúc service đang cập nhật; cần cơ chế đồng bộ/cutover.

**14. “Có bảng summary thì không cần lưu event ID.”** Nếu sự kiện được gửi lại, summary có thể bị đếm đôi; event identity và idempotency thường là yêu cầu thiết yếu.

**15. “Lưu trước nhiều cột chắc sẽ dùng đến.”** Dữ liệu dư thừa không có use case đo được chỉ tăng storage, WAL, migration và bề mặt sai lệch.

## 23. Bài tập thực hành

Các bài tập dùng schema `commerce_lab` đã tạo ở phần 3. Đối với trigger và các đoạn sửa dữ liệu, hãy chạy trên môi trường lab riêng. Các ví dụ ở nhiều phần trình bày các **phương án khác nhau**; không nên chạy tất cả DML theo một mạch mà bỏ qua trạng thái dữ liệu đã thay đổi ở bài trước.

### Bài 1. Nhận diện dữ liệu dẫn xuất và snapshot

Cho các cột:

```text
orders.total_amount
orders.customer_name_at_order
orders.current_customer_name_cache
order_items.unit_price
daily_sales_summary.confirmed_order_count
```

Hãy phân loại:

- Giá trị nào **phải đồng bộ** với một nguồn sau mọi commit?
- Giá trị nào là **snapshot theo thời điểm nghiệp vụ**?
- Giá trị nào có thể **eventually consistent** nếu SLA cho phép?

**Đáp án gợi ý:** `total_amount` cần khớp tổng các dòng theo công thức đã định; `customer_name_at_order` và `unit_price` ở dòng hàng đã chốt thường là snapshot lịch sử; `current_customer_name_cache` phải có chính sách đồng bộ với tên hiện tại; `daily_sales_summary` có thể trễ theo SLA. Phân loại cuối cùng còn phụ thuộc định nghĩa nghiệp vụ của sản phẩm.

### Bài 2. Truy vấn phát hiện tổng tiền lệch

```sql
SELECT
    o.order_id,
    o.total_amount AS stored,
    COALESCE(SUM(i.quantity * i.unit_price), 0) AS calculated
FROM commerce_lab.orders AS o
LEFT JOIN commerce_lab.order_items AS i
  ON i.order_id = o.order_id
GROUP BY o.order_id, o.total_amount
HAVING o.total_amount IS DISTINCT FROM
       COALESCE(SUM(i.quantity * i.unit_price), 0);
```

**Câu hỏi:** Vì sao nên có `LEFT JOIN` thay vì `JOIN`?

**Giải thích:** `LEFT JOIN` vẫn giữ đơn chưa có dòng hàng để đối soát với tổng bằng 0; dùng `JOIN` có thể bỏ qua những đơn ấy.

### Bài 3. Transaction và rollback

Trong lab đã có trigger `trg_adjust_order_total`:

```sql
BEGIN;

UPDATE commerce_lab.order_items
SET quantity = quantity + 1
WHERE order_id = 101 AND line_no = 1;

SELECT total_amount
FROM commerce_lab.orders
WHERE order_id = 101;

ROLLBACK;
```

**Câu hỏi:** sau `ROLLBACK`, tổng tiền có giữ mức cộng thêm do trigger không?

**Đáp án:** Không. Trigger hoạt động trong cùng transaction, nên thay đổi `order_items` và `orders.total_amount` cùng rollback.

### Bài 4. Hai writer sửa cùng một đơn

Giả sử transaction A và B cùng thêm dòng hàng vào đơn 101. Hãy giải thích vì sao:

```sql
UPDATE commerce_lab.orders
SET total_amount = total_amount + 12000
WHERE order_id = 101;
```

thường an toàn hơn kiểu ứng dụng đọc `total_amount` về máy, cộng 12000 rồi ghi một giá trị tính trước mà không khóa.

**Gợi ý:** câu `UPDATE ... total_amount + delta` thực hiện phép cộng trên hàng database trong transaction và phối hợp với khóa hàng. Read-modify-write ở client có thể gây ghi đè khi hai client cùng dùng một giá trị đọc cũ.

### Bài 5. Materialized view có bị stale không?

Tạo và đọc `mv_daily_sales`, sau đó xác nhận thêm một đơn mới trong bảng `orders` mà không refresh view.

**Câu hỏi:** Vì sao query `SELECT * FROM mv_daily_sales` có thể chưa thấy thay đổi?

**Đáp án:** materialized view lưu kết quả của lần refresh trước. Muốn cập nhật phải chạy `REFRESH MATERIALIZED VIEW` theo chính sách vận hành phù hợp.

### Bài 6. Sự kiện bị gửi lại

Một worker nhận hai lần cùng event:

```text
event_id = 1fa80ca8-e121-43cf-8afe-27124d141f42
sale_date = 2026-10-05
amount = 330000
```

**Câu hỏi:** nếu chỉ thực hiện upsert cộng tiền hai lần thì sai ở đâu? Cách giải quyết?

**Đáp án:** doanh số bị tăng hai lần. Consumer cần đánh dấu event duy nhất theo projection cùng transaction cập nhật summary, chẳng hạn bảng `processed_projection_events` và `ON CONFLICT DO NOTHING`.

### Bài 7. Thiết kế backfill không ghi đè dữ liệu mới

Một job đọc tổng tiền tại T1, trong khi service thay đổi dòng hàng tại T2 và job ghi tổng cũ tại T3.

**Yêu cầu:** đề xuất hai phương án giảm rủi ro.

**Gợi ý:** chạy backfill trong cửa sổ kiểm soát ghi; hoặc khóa/serialize theo đơn với các writer; hoặc lưu watermark thay đổi để bắt lại event sau snapshot và đối soát trước cutover. Chọn một quy trình cụ thể và kiểm thử dưới concurrency.

### Bài 8. Cân nhắc chi phí

Một endpoint đọc tổng tiền 5 lần/giây, mỗi đơn chỉ vài dòng, `EXPLAIN ANALYZE` cho thấy truy vấn tổng chi tiết rất nhanh. Team muốn thêm cột `total_amount` chỉ để tránh JOIN.

**Đánh giá:** chưa có bằng chứng cần phi chuẩn hóa. Có thể dùng query hiện tại hoặc tối ưu chỉ mục/cách lấy dữ liệu. Lợi ích đọc nhỏ có thể không bù chi phí trigger, tranh chấp khóa và reconciliation.

### Bài 9. Đề xuất dữ liệu phi chuẩn hóa phù hợp

Hệ thống báo cáo 30 ngày gần nhất, mỗi giờ có hàng triệu dòng sự kiện và dashboard cần hiển thị trong 2 giây. Báo cáo có thể trễ tối đa 2 phút.

**Hướng giải quyết:** cân nhắc materialized view theo lịch refresh hoặc bảng aggregate incremental. Cần đo chi phí refresh, lag, cách phát hiện bỏ sót sự kiện, trạng thái last_refresh và query latency. Không dùng `orders.total_amount` như phương án duy nhất nếu điểm nghẽn thực sự là phép tổng hợp toàn bộ số đơn theo ngày.

## 24. Tổng kết

Phi chuẩn hóa có chủ đích là quyết định **đánh đổi sự đơn giản và tính nhất quán tự nhiên của dữ liệu chuẩn hóa lấy tốc độ đọc, khả năng báo cáo hoặc giá trị lưu giữ lịch sử**. Đánh đổi đó chỉ có cơ sở khi biết rõ nguồn sự thật, ngữ nghĩa của bản sao và cam kết đồng bộ.

Các nguyên tắc quan trọng:

- **Chuẩn hóa là điểm xuất phát.** Đầu tiên đo `EXPLAIN (ANALYZE, BUFFERS)` và thử chỉ mục/viết lại truy vấn, không bỏ JOIN theo cảm tính.
- **Không phải mọi bản sao đều cần đồng bộ.** Snapshot tên, địa chỉ hoặc giá tại thời điểm chốt giao dịch có thể khác dữ liệu hiện tại một cách hoàn toàn đúng.
- **Dữ liệu dẫn xuất phải có invariant.** Nếu lưu `orders.total_amount`, phải định nghĩa công thức, ranh giới cập nhật và đường ghi nào được phép sửa.
- **Transaction/trigger bảo vệ đồng bộ trong một PostgreSQL database** khi logic và concurrency được thiết kế đúng; chúng vẫn có chi phí ghi, lock và yêu cầu test.
- **Materialized view và projection bất đồng bộ đổi độ mới dữ liệu lấy tốc độ đọc.** Phải có SLA, refresh/retry, idempotency và reconciliation.
- **JSONB, generated column và bảng aggregate phục vụ nhu cầu khác nhau.** Không có một kỹ thuật phi chuẩn hóa phù hợp mọi kiểu dữ liệu.
- **Migration cần chống race.** Backfill, dual-write và cutover phải được điều phối để không ghi đè những thay đổi vừa được commit.
- **Đối soát là phần của thiết kế**, không phải công việc sửa lỗi được bổ sung sau khi hệ thống đã trả dữ liệu sai.

Một lựa chọn tốt có thể diễn đạt trong một câu rõ ràng: **“Chúng tôi lưu thêm giá trị X để tối ưu truy vấn Y đã đo được; nguồn sự thật là Z; dữ liệu được làm mới theo cơ chế M với độ trễ tối đa T; job R phát hiện và sửa sai lệch.”** Khi trả lời được câu đó và kiểm chứng được bằng số liệu, phi chuẩn hóa mới thực sự có chủ đích, thay vì chỉ là sự dư thừa khó kiểm soát.
