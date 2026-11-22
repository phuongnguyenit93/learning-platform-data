# Phân biệt xử lý giao dịch và phân tích dữ liệu trong PostgreSQL

## 1. Hai nhu cầu khác nhau trên cùng một hệ thống dữ liệu

Một hệ thống thương mại điện tử thường có hai loại câu hỏi:

- **“Khách hàng vừa đặt đơn, còn đủ hàng để bán không? Thanh toán và cập nhật tồn kho có thành công không?”** Đây là nhu cầu **xử lý giao dịch**.
- **“Doanh thu mỗi tháng tăng bao nhiêu phần trăm? Nhóm khách hàng nào tạo ra nhiều doanh thu nhất trong quý?”** Đây là nhu cầu **phân tích dữ liệu**.

Cả hai đều sử dụng SQL và dữ liệu quan hệ, nhưng **hình dạng truy vấn, thời gian phản hồi mong muốn, số dòng phải đọc, kiểu cập nhật và cách tổ chức hệ thống** rất khác nhau. Một database có thể vận hành ổn cho 1.000 thao tác đặt hàng mỗi giây nhưng gặp khó nếu vài báo cáo phải quét hàng trăm triệu giao dịch cùng lúc trên chính máy chủ ấy.

Hai nhóm workload thường được gọi là:

- **OLTP (Online Transaction Processing):** xử lý các giao dịch nghiệp vụ trực tuyến, thường truy cập ít hàng, có nhiều thao tác ghi, yêu cầu đúng đắn và phản hồi nhanh.
- **OLAP (Online Analytical Processing):** phân tích dữ liệu trên tập lớn, thường đọc và tổng hợp nhiều hàng, có nhiều phép `JOIN`, `GROUP BY`, thống kê và so sánh theo thời gian.

PostgreSQL là hệ quản trị cơ sở dữ liệu quan hệ đa năng, có thể phục vụ **cả OLTP lẫn nhiều loại phân tích**, nhưng điều đó **không có nghĩa hai workload luôn nên chạy với cùng cơ sở hạ tầng, cùng schema hoặc cùng chính sách tối ưu**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận biết truy vấn OLTP và OLAP từ yêu cầu nghiệp vụ.
2. Phân biệt yêu cầu về độ trễ, thông lượng, tính nhất quán và độ mới của dữ liệu.
3. Thiết kế schema và chỉ mục ban đầu phù hợp cho từng nhóm truy vấn.
4. Viết các câu SQL PostgreSQL minh họa xử lý giao dịch và phân tích.
5. Hiểu vai trò của MVCC, transaction, WAL, bản sao đọc và materialized view.
6. Chọn khi nào nên phân tích trực tiếp trên PostgreSQL, khi nào nên tách workload sang hệ thống phân tích.

**Phạm vi:** ví dụ dùng PostgreSQL hiện đại với bảng thông thường và SQL chuẩn PostgreSQL. Mục đích là hiểu kiến trúc và thực hành; các số liệu hiệu năng trong bài chỉ là minh họa, không phải benchmark đã đo.

---

## 2. OLTP là gì?

**OLTP** tập trung ghi nhận và cập nhật trạng thái nghiệp vụ khi nhiều người dùng hoặc dịch vụ đang hoạt động đồng thời.

Một giao dịch đặt hàng có thể gồm:

1. Xác minh khách hàng và sản phẩm.
2. Kiểm tra hàng còn đủ.
3. Giảm số lượng tồn kho.
4. Tạo đơn hàng.
5. Tạo các dòng chi tiết đơn hàng.
6. `COMMIT` nếu tất cả bước cần tính nguyên tử đều thành công; `ROLLBACK` nếu có lỗi.

Nếu giảm tồn kho thành công nhưng tạo đơn thất bại mà không rollback, dữ liệu sẽ không còn phản ánh đúng thực tế. Do đó tính **nguyên tử (atomicity)** và **toàn vẹn dữ liệu** là yêu cầu trung tâm.

### 2.1. Đặc điểm thường gặp của OLTP

- Truy cập **một hoặc một số ít hàng** bằng khóa chính/unique key hoặc chỉ mục chọn lọc.
- Có nhiều câu `INSERT`, `UPDATE`, `DELETE` và `SELECT` ngắn.
- Nhiều giao dịch chạy **đồng thời**, đôi khi cập nhật cùng một mặt hàng hoặc tài khoản.
- Thời gian phản hồi kỳ vọng ở mức rất thấp, ví dụ vài đến vài chục mili giây cho thao tác DB đơn giản trong điều kiện phù hợp.
- Dùng ràng buộc `PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE`, `CHECK` và transaction để tránh trạng thái dữ liệu sai.
- Thường thiết kế **chuẩn hóa** nhằm giảm trùng lặp và duy trì một nguồn sự thật cho mỗi thực thể.

Ví dụ một truy vấn tra cứu đơn hàng:

~~~sql
SELECT order_id, customer_id, status, total_amount
FROM orders
WHERE order_id = 1001;
~~~

Nếu `order_id` là primary key, PostgreSQL có thể tìm hàng đó bằng chỉ mục thay vì quét toàn bộ bảng. Kết quả thường chỉ có một dòng.

### 2.2. Transaction không đồng nghĩa “một câu SQL”

Một transaction có thể bao gồm nhiều câu lệnh SQL cần thành công cùng nhau:

~~~sql
BEGIN;

-- Kiểm tra/cập nhật tồn kho có điều kiện.
-- Tạo đơn hàng.
-- Tạo chi tiết đơn hàng.

COMMIT;
~~~

Điểm quan trọng là **ranh giới transaction theo nghiệp vụ**. Transaction quá dài có thể giữ khóa, làm tăng tranh chấp và giữ những phiên bản cũ trong MVCC lâu hơn cần thiết.

---

## 3. OLAP là gì?

**OLAP** phục vụ câu hỏi về xu hướng, tổng hợp và ra quyết định:

- Doanh thu theo ngày/tháng/quý.
- Tỷ lệ đơn hủy theo kênh bán.
- Số khách hàng quay lại trong 30 ngày.
- Top sản phẩm theo doanh thu và mức tăng trưởng.
- So sánh doanh số giữa các vùng/nhóm khách hàng.
- Tính giá trị trung bình đơn hàng, tỷ trọng, lũy kế, thứ hạng.

Một câu phân tích có thể phải đọc hàng triệu dòng để trả về **chỉ 12 dòng tổng doanh thu theo tháng**.

~~~sql
SELECT
    date_trunc('month', ordered_at)::date AS month,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM orders
WHERE status = 'PAID'
GROUP BY date_trunc('month', ordered_at)::date
ORDER BY month;
~~~

Đoạn trên minh họa ý tưởng; khi `ordered_at` là `timestamptz` và báo cáo yêu cầu tháng theo giờ địa phương, cần xác định **múi giờ nghiệp vụ** thay vì phụ thuộc ngầm vào time zone của session. Bài sẽ trình bày cách làm cụ thể bên dưới.

### 3.1. Đặc điểm thường gặp của OLAP

- Đọc **nhiều hàng** và **nhiều cột** theo nhu cầu tổng hợp.
- Thường có `JOIN`, `GROUP BY`, `HAVING`, `ORDER BY`, CTE và hàm cửa sổ.
- Một truy vấn có thể có chi phí CPU, I/O, RAM lớn dù kết quả rất ít dòng.
- Số truy vấn đồng thời có thể thấp hơn OLTP, nhưng **mỗi truy vấn nặng hơn nhiều**.
- Dữ liệu có thể là một bản snapshot, bản tổng hợp đã chuẩn bị trước hoặc dữ liệu từ pipeline.
- Đôi khi chấp nhận dữ liệu chậm vài phút/giờ; trong trường hợp khác lại yêu cầu gần thời gian thực.

Không phải OLAP luôn “chỉ đọc”. Hệ thống phân tích vẫn cần nạp dữ liệu, làm sạch, tính bảng tổng hợp và cập nhật các cấu trúc lưu trữ. Điểm khác biệt nằm ở **mục đích và hình dạng workload**, không phải một quy tắc rằng OLAP không bao giờ ghi.

---

## 4. Bảng so sánh tổng quan OLTP và OLAP

| Tiêu chí | OLTP | OLAP |
|---|---|---|
| Mục đích | Thực hiện, ghi nhận giao dịch nghiệp vụ | Tổng hợp, khám phá và hỗ trợ quyết định |
| Đơn vị thao tác | Một khách hàng/đơn hàng/tài khoản hoặc vài hàng liên quan | Nhiều khách hàng/đơn hàng, toàn bộ kỳ báo cáo |
| SQL phổ biến | `INSERT`, `UPDATE`, `DELETE`, `SELECT` theo khóa | `SELECT` với `JOIN`, `GROUP BY`, window functions |
| Khối lượng đọc | Thường nhỏ, chọn lọc | Thường lớn, có thể quét nhiều partition |
| Khả năng đồng thời | Nhiều thao tác ngắn | Ít hoặc vừa số truy vấn nặng; tùy nền tảng |
| Chỉ số quan trọng | Độ trễ p95/p99, TPS, tỷ lệ lỗi, lock wait | Thời gian báo cáo, hàng/byte được quét, CPU/I/O, độ mới dữ liệu |
| Cách tổ chức dữ liệu | Thường chuẩn hóa, ưu tiên ghi chính xác | Có thể dùng star schema, bảng tổng hợp hoặc mô hình chuyên phân tích |
| Chỉ mục | Theo khóa chính, khóa ngoại, điều kiện chọn lọc | Theo bộ lọc, khoảng thời gian, `JOIN`; đôi khi BRIN/partition |
| Dữ liệu | Thường yêu cầu trạng thái hiện hành | Có thể theo kỳ, snapshot hoặc độ trễ đã thỏa thuận |
| Tác động lỗi | Mất đơn, sai tồn kho, sai số dư | Sai báo cáo, dashboard chậm, quyết định dựa trên dữ liệu cũ |
| Chi phí cần kiểm soát | Lock contention, commit, kết nối, ghi WAL | Quét dữ liệu lớn, sort/hash, bộ nhớ, temp files, cạnh tranh I/O |
| Mẫu thiết kế | Transaction và ràng buộc | Pipeline, dữ liệu lịch sử, tổng hợp, partitioning |

**Không phải phân loại nhị phân tuyệt đối:** một API có thể thực hiện truy vấn thống kê đơn giản; một pipeline dữ liệu vẫn phải dùng transaction. Cần phân loại **từng workload cụ thể**, không chỉ gắn nhãn hệ thống là “OLTP” hoặc “OLAP”.

## 5. Vì sao PostgreSQL có thể phục vụ cả hai?

PostgreSQL lưu trữ dữ liệu quan hệ theo các bảng dạng hàng, hỗ trợ SQL mạnh, transaction ACID, chỉ mục, bộ tối ưu truy vấn và các cơ chế xử lý song song phù hợp với nhiều kiểu truy vấn.

### 5.1. Những cơ chế quan trọng cho OLTP

**Transaction và ACID:**

- **Atomicity:** toàn bộ thay đổi trong transaction được commit hoặc rollback theo ngữ nghĩa giao dịch.
- **Consistency:** các quy tắc toàn vẹn dữ liệu được duy trì khi ứng dụng và ràng buộc được thiết kế đúng.
- **Isolation:** nhiều transaction đồng thời được điều phối theo mức cô lập.
- **Durability:** một giao dịch commit bền vững theo cấu hình bảo đảm lưu trữ/WAL.

**MVCC (Multi-Version Concurrency Control):** PostgreSQL có thể cho các giao dịch đọc một phiên bản hàng phù hợp với snapshot mà không cần khóa ghi mọi hàng đang đọc. Điều này giúp nhiều lượt đọc và ghi diễn ra đồng thời hơn so với mô hình chỉ dùng khóa đọc/ghi đơn giản.

**Write-Ahead Log (WAL):** thay đổi được ghi vào log phục vụ durability và phục hồi. WAL còn được dùng cho physical streaming replication và các cơ chế truyền thay đổi khác. WAL **không thay thế backup độc lập**.

**Indexes:** B-tree trên primary key, unique key và các cột thường dùng giúp truy cập một số ít hàng nhanh chóng.

### 5.2. Những cơ chế quan trọng cho OLAP

- `JOIN`, aggregate functions, grouping sets, window functions và CTE giúp xử lý nhiều loại phân tích.
- Bộ tối ưu chọn `Seq Scan`, `Index Scan`, `Bitmap Heap Scan`, các thuật toán `Hash Join`, `Merge Join`, `Nested Loop` hoặc các phương án phù hợp khác.
- Các kế hoạch **parallel query** có thể chia một số công việc đọc/tính toán cho nhiều worker khi phù hợp.
- **Declarative partitioning** giúp tổ chức dữ liệu lớn theo tháng/năm và có thể bỏ qua những partition ngoài bộ lọc.
- **BRIN index** có thể tiết kiệm dung lượng cho bảng lớn có giá trị tương quan với thứ tự lưu trữ (ví dụ log thời gian tăng dần).
- **Materialized view** lưu kết quả truy vấn đã tính để báo cáo đọc nhanh hơn tại thời điểm được làm mới.

Tuy nhiên, PostgreSQL ở cấu hình bảng hàng thông thường **không tự biến thành kho dữ liệu cột chuyên dụng**. Một workload quét số lượng rất lớn bản ghi có thể phù hợp hơn với hệ thống OLAP chuyên biệt hoặc một kiến trúc tách riêng.

## 6. Dựng dữ liệu bán hàng mẫu

Để quan sát hai nhóm truy vấn, sử dụng schema thực hành riêng. DDL sau phù hợp PostgreSQL, không phải cú pháp MySQL.

### 6.1. Tạo schema và bảng

~~~sql
CREATE SCHEMA IF NOT EXISTS learning_shop;

CREATE TABLE learning_shop.customers (
    customer_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    customer_name TEXT NOT NULL,
    segment TEXT NOT NULL
        CHECK (segment IN ('VIP', 'STANDARD'))
);

CREATE TABLE learning_shop.products (
    product_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    stock_qty INTEGER NOT NULL CHECK (stock_qty >= 0)
);

CREATE TABLE learning_shop.orders (
    order_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES learning_shop.customers(customer_id),
    ordered_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status TEXT NOT NULL
        CHECK (status IN ('PENDING', 'PAID', 'CANCELED')),
    total_amount NUMERIC(12, 2) NOT NULL
        CHECK (total_amount >= 0)
);

CREATE TABLE learning_shop.order_items (
    order_item_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL
        REFERENCES learning_shop.orders(order_id),
    product_id BIGINT NOT NULL
        REFERENCES learning_shop.products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0)
);
~~~

Các giá trị tiền dùng `NUMERIC` thay vì số thực dấu phẩy động để biểu diễn chính xác những lượng tiền có hai chữ số thập phân.

Schema trên được **chuẩn hóa theo thực thể**: khách hàng, sản phẩm, đơn và chi tiết đơn là các bảng riêng, nối bằng khóa ngoại. `unit_price` trong `order_items` là **giá tại lúc mua**, khác giá niêm yết hiện tại ở `products.unit_price`. Giữ bản chụp giá là quyết định nghiệp vụ hợp lý cho lịch sử đơn hàng.

> Đây là mô hình lab, không phải thiết kế thương mại điện tử hoàn chỉnh: hệ thống thật còn có thanh toán, hoàn tiền, địa chỉ, thuế, vận chuyển và quy tắc đối chiếu tổng tiền.

### 6.2. Nạp dữ liệu mẫu

~~~sql
INSERT INTO learning_shop.customers
    (customer_id, email, customer_name, segment)
VALUES
    (1, 'an@example.com', 'An', 'VIP'),
    (2, 'binh@example.com', 'Binh', 'STANDARD'),
    (3, 'chi@example.com', 'Chi', 'VIP');

INSERT INTO learning_shop.products
    (product_id, sku, product_name, unit_price, stock_qty)
VALUES
    (11, 'KB-01', 'Ban phim', 350000.00, 50),
    (12, 'MS-01', 'Chuot',    150000.00, 80),
    (13, 'MN-01', 'Man hinh', 2200000.00, 20);

INSERT INTO learning_shop.orders
    (order_id, customer_id, ordered_at, status, total_amount)
VALUES
    (1001, 1, TIMESTAMPTZ '2026-01-05 10:00:00+07', 'PAID',     500000.00),
    (1002, 2, TIMESTAMPTZ '2026-01-05 15:00:00+07', 'PAID',    2200000.00),
    (1003, 1, TIMESTAMPTZ '2026-01-08 16:00:00+07', 'PAID',     300000.00),
    (1004, 3, TIMESTAMPTZ '2026-01-10 09:00:00+07', 'CANCELED', 350000.00),
    (1005, 2, TIMESTAMPTZ '2026-02-01 11:00:00+07', 'PAID',     350000.00),
    (1006, 3, TIMESTAMPTZ '2026-02-04 11:00:00+07', 'PENDING',  150000.00);

INSERT INTO learning_shop.order_items
    (order_item_id, order_id, product_id, quantity, unit_price)
VALUES
    (2001, 1001, 11, 1,  350000.00),
    (2002, 1001, 12, 1,  150000.00),
    (2003, 1002, 13, 1, 2200000.00),
    (2004, 1003, 12, 2,  150000.00),
    (2005, 1004, 11, 1,  350000.00),
    (2006, 1005, 11, 1,  350000.00),
    (2007, 1006, 12, 1,  150000.00);
~~~

Bảng `orders` có sáu đơn, trong đó bốn đơn `PAID`, một `CANCELED` và một `PENDING`. Doanh thu giả định tính theo `orders.total_amount` **chỉ với `status = 'PAID'`**:

| Kỳ theo giờ Việt Nam | Số đơn PAID | Doanh thu |
|---|---:|---:|
| Tháng 01/2026 | 3 | 3.000.000 |
| Tháng 02/2026 | 1 | 350.000 |
| Tổng cộng | 4 | 3.350.000 |

Các thống kê này là kỳ vọng từ **dữ liệu SQL được nêu ở trên**, không đại diện cho doanh thu thực tế. Dữ liệu chỉ có vài dòng nên PostgreSQL có thể chọn `Seq Scan` thay vì index ở hầu hết truy vấn; không dùng lab nhỏ để kết luận về hiệu năng.

## 7. Ví dụ OLTP: đọc và cập nhật từng giao dịch

### 7.1. Tra cứu một đơn theo khóa chính

~~~sql
SELECT
    o.order_id,
    o.status,
    o.ordered_at,
    o.total_amount,
    c.customer_name
FROM learning_shop.orders AS o
JOIN learning_shop.customers AS c
  ON c.customer_id = o.customer_id
WHERE o.order_id = 1001;
~~~

Truy vấn chỉ cần một đơn, một khách hàng tương ứng. PostgreSQL có thể đi theo primary key của `orders`, rồi dùng primary key của `customers` để lấy khách.

Nếu một trang danh sách hiển thị 20 đơn gần nhất của một khách, một chỉ mục ghép có thể hữu ích:

~~~sql
CREATE INDEX idx_orders_customer_time
ON learning_shop.orders (customer_id, ordered_at DESC, order_id DESC);

SELECT order_id, ordered_at, status, total_amount
FROM learning_shop.orders
WHERE customer_id = 1
ORDER BY ordered_at DESC, order_id DESC
LIMIT 20;
~~~

Index có `customer_id` đứng đầu phục vụ điều kiện bằng; hai key part sau giúp đọc theo thứ tự mới nhất, có thứ tự phân định bằng `order_id`. Tuy nhiên, PostgreSQL vẫn có quyền chọn đường quét khác nếu tập dữ liệu nhỏ.

### 7.2. Cập nhật tồn kho nguyên tử

Sai lầm khi có nhiều người mua cùng sản phẩm là làm theo quy trình không khóa:

~~~text
Request A: SELECT stock_qty → 1
Request B: SELECT stock_qty → 1
Request A: quyết định trừ 1
Request B: quyết định trừ 1
~~~

Nếu ứng dụng tự tính dữ liệu cũ rồi ghi lại mà không kiểm soát đồng thời, kết quả có thể sai hoặc một request bị xử lý không đúng.

Có thể dùng `UPDATE` **có điều kiện**:

~~~sql
UPDATE learning_shop.products
SET stock_qty = stock_qty - 2
WHERE product_id = 12
  AND stock_qty >= 2
RETURNING product_id, stock_qty, unit_price;
~~~

Nếu câu lệnh trả **một dòng**, nó đã giảm tồn kho hai đơn vị và trả về giá trị mới cùng giá. Nếu trả **không dòng nào**, nghĩa là không có sản phẩm tương ứng hoặc không đủ hàng theo điều kiện. Đây là một thao tác ghi đơn có kiểm soát, không phụ thuộc vào việc ứng dụng đã đọc lượng tồn kho cách đây bao lâu.

Đối với một đơn đặt hàng đầy đủ, thao tác giảm tồn và tạo đơn cần chung transaction:

~~~sql
BEGIN;

UPDATE learning_shop.products
SET stock_qty = stock_qty - 2
WHERE product_id = 12
  AND stock_qty >= 2
RETURNING unit_price;

-- Ứng dụng PHẢI kiểm tra có đúng một dòng RETURNING.
-- Nếu 0 dòng: ROLLBACK ngay, không tạo đơn.

INSERT INTO learning_shop.orders
    (order_id, customer_id, status, total_amount)
VALUES
    (1007, 1, 'PAID', 300000.00);

INSERT INTO learning_shop.order_items
    (order_item_id, order_id, product_id, quantity, unit_price)
VALUES
    (2008, 1007, 12, 2, 150000.00);

COMMIT;
~~~

Ví dụ này cố định ID và giá để dễ học; **chỉ chạy một lần** trên dữ liệu lab. Trong ứng dụng thật, nên để database cấp `IDENTITY`, dùng `INSERT ... RETURNING` lấy ID, tính giá từ dữ liệu đã kiểm tra trong transaction, và **không commit nếu bất kỳ bước nào thất bại**. Quá trình thanh toán thật còn đòi tích hợp cổng thanh toán, idempotency và các trạng thái nghiệp vụ phù hợp; không thể giả định chỉ có một transaction MySQL/PostgreSQL là đủ cho toàn bộ quy trình xuyên hệ thống.

### 7.3. Vì sao transaction là trung tâm của OLTP?

Nếu `UPDATE products` thành công nhưng `INSERT order_items` vi phạm khóa ngoại, ứng dụng cần `ROLLBACK` để cả tồn kho và đơn hàng trở về trạng thái hợp lệ. Nếu đã `COMMIT` từng câu riêng biệt, không thể chỉ dựa vào một rollback cuối để đảo mọi thay đổi.

Các khối mã OLTP thường phải giải quyết:

- Kiểm tra điều kiện nghiệp vụ ở thời điểm ghi.
- Transaction boundary ngắn và rõ.
- Xử lý deadlock, serialization failure, connection failure.
- Retry có giới hạn và **idempotency** với request có thể bị gửi lặp.
- Quyền ghi tối thiểu và ràng buộc tại database.

## 8. Ví dụ OLAP: đọc và tổng hợp nhiều giao dịch

### 8.1. Doanh thu theo tháng

PostgreSQL lưu `TIMESTAMPTZ` dưới dạng mốc thời gian có tính đến múi giờ. Nếu báo cáo tính ngày/tháng theo **Asia/Ho_Chi_Minh**, hãy chuyển sang giờ địa phương trước khi nhóm:

~~~sql
SELECT
    date_trunc(
        'month',
        ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date AS month_start,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS revenue
FROM learning_shop.orders
WHERE status = 'PAID'
GROUP BY 1
ORDER BY 1;
~~~

Kết quả kỳ vọng trước khi chạy thao tác tạo đơn mẫu ở phần 7.2:

| month_start | paid_orders | revenue |
|---|---:|---:|
| 2026-01-01 | 3 | 3000000.00 |
| 2026-02-01 | 1 | 350000.00 |

Khác truy vấn tra một đơn, câu này phải xét **mọi đơn `PAID`** trong phạm vi dữ liệu rồi nhóm theo tháng.

> Nếu đã chạy phần 7.2 và tạo đơn 1007 ở thời điểm hiện tại, kết quả báo cáo sẽ thay đổi. Hãy giữ đúng cùng một **trạng thái dữ liệu đầu vào** khi so sánh kết quả trong bài lab.

### 8.2. Tổng hợp theo ngày có giới hạn thời gian

~~~sql
SELECT
    (ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS order_day,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS revenue
FROM learning_shop.orders
WHERE status = 'PAID'
  AND ordered_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
  AND ordered_at <  TIMESTAMPTZ '2026-02-01 00:00:00+07'
GROUP BY 1
ORDER BY 1;
~~~

Kỳ vọng từ dữ liệu gốc:

| order_day | paid_orders | revenue |
|---|---:|---:|
| 2026-01-05 | 2 | 2700000.00 |
| 2026-01-08 | 1 | 300000.00 |

Bộ lọc dùng **khoảng nửa mở** (bao gồm đầu, không bao gồm cuối) trên giá trị gốc `ordered_at`, tránh bỏ sót giao dịch có phút/giây cuối ngày và có cơ hội tận dụng B-tree index trên cột thời gian.

### 8.3. Top khách hàng theo doanh thu

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    c.segment,
    COUNT(*) AS paid_orders,
    SUM(o.total_amount) AS total_revenue
FROM learning_shop.orders AS o
JOIN learning_shop.customers AS c
  ON c.customer_id = o.customer_id
WHERE o.status = 'PAID'
GROUP BY c.customer_id, c.customer_name, c.segment
ORDER BY total_revenue DESC, c.customer_id
LIMIT 10;
~~~

Điểm khác OLTP:

- Phải nối nhiều đơn với khách hàng.
- Phải tính tổng `SUM` trên các dòng.
- Chỉ sau khi tính tổng mới có thể xác định ai có `total_revenue` lớn nhất.
- `LIMIT 10` giảm dòng kết quả, **không đảm bảo** chỉ đọc 10 đơn.

Với dữ liệu mẫu, khách hàng **Binh** có tổng 2.550.000 và **An** có tổng 800.000; khách hàng Chi không có đơn `PAID` nên không xuất hiện trong kiểu `INNER JOIN` này. Nếu muốn giữ tất cả khách, kể cả người chưa mua, cần sửa ý nghĩa truy vấn bằng `LEFT JOIN` và đưa bộ lọc đơn vào phần `ON` cho phù hợp.

### 8.4. Phân tích lũy kế bằng window function

~~~sql
WITH daily_revenue AS (
    SELECT
        (ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS order_day,
        SUM(total_amount) AS revenue
    FROM learning_shop.orders
    WHERE status = 'PAID'
    GROUP BY 1
)
SELECT
    order_day,
    revenue,
    SUM(revenue) OVER (
        ORDER BY order_day
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_revenue
FROM daily_revenue
ORDER BY order_day;
~~~

CTE đầu tạo doanh thu theo ngày. Hàm cửa sổ tính tổng cộng dồn từ đầu chuỗi thời gian đến từng ngày. Đây là mẫu phân tích không có mục tiêu cập nhật từng đơn, mà biến nhiều dòng sự kiện thành **chỉ số** phục vụ quyết định.

### 8.5. Tính tỷ lệ đơn theo trạng thái

~~~sql
SELECT
    status,
    COUNT(*) AS order_count,
    ROUND(
        100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0),
        2
    ) AS percentage
FROM learning_shop.orders
GROUP BY status
ORDER BY order_count DESC, status;
~~~

Truy vấn kết hợp `GROUP BY` và `SUM(COUNT(*)) OVER ()` để tính tỷ trọng theo tổng số đơn trong tập. Nó hữu ích cho dashboard, nhưng vẫn phải xác định **mẫu số** đúng với nghiệp vụ: toàn bộ đơn, đơn trong tháng hay chỉ đơn hợp lệ?

## 9. Chuẩn hóa dữ liệu và mô hình chiều (dimensional model)

### 9.1. Vì sao OLTP thường dùng schema chuẩn hóa?

Bảng `orders` giữ `customer_id` thay vì sao chép toàn bộ thông tin khách vào từng đơn. Nếu tên khách thay đổi, ứng dụng có thể sửa một bản ghi `customers`.

Cách này giúp:

- Giảm trùng lặp không cần thiết.
- Kiểm soát khóa ngoại.
- Tránh các bất thường khi chèn/cập nhật/xóa.
- Dễ xác định nguồn dữ liệu đúng cho mỗi thực thể.

Tuy nhiên, để lập báo cáo có thể phải `JOIN` nhiều bảng và xử lý nhiều dòng lịch sử.

### 9.2. Vì sao phân tích thường dùng fact và dimension?

Một mô hình phân tích có thể tổ chức dữ liệu thành:

~~~text
                  dim_customer
                        |
+----------+      +--------------+      +------------+
| dim_date | ---- | fact_sales   | ---- | dim_product|
+----------+      +--------------+      +------------+
                        |
                   dim_channel
~~~

- **Fact table** (`fact_sales`): các sự kiện định lượng như số lượng, doanh thu, giảm giá, thuế; mỗi dòng có mức chi tiết (*grain*) xác định.
- **Dimension tables** (`dim_customer`, `dim_product`, `dim_date`): thông tin để phân nhóm, lọc và cắt dữ liệu theo nhiều chiều.

Ví dụ một dòng fact có thể tương ứng **một dòng chi tiết đơn đã thanh toán**, thay vì một đơn. Nếu grain là dòng chi tiết, số đơn phải đếm bằng `COUNT(DISTINCT order_id)` hoặc theo mô hình phù hợp, tránh đếm dòng chi tiết thành số đơn.

Một mô hình star schema giúp nhiều truy vấn phân tích dễ hiểu và tối ưu hơn, nhưng **không phải điều kiện bắt buộc để chạy OLAP trên PostgreSQL**. Trong giai đoạn nhỏ, truy vấn trực tiếp schema OLTP có thể đáp ứng đủ.

### 9.3. Lịch sử là yêu cầu riêng

Giả sử một khách hàng hôm nay thuộc segment `VIP` nhưng hồi tháng trước là `STANDARD`. Báo cáo tháng trước cần hiển thị segment **hiện tại** hay **segment tại thời điểm mua**?

Nếu JOIN trực tiếp đơn hàng lịch sử với dòng `customers.segment` hiện hành, báo cáo có thể thay đổi sau khi khách được nâng hạng. Trong kho phân tích, có thể cần **lịch sử dimension** (ví dụ Slowly Changing Dimension Type 2) hoặc lưu thuộc tính tại thời điểm sự kiện.

Đây là khác biệt quan trọng: **dữ liệu transaction hiện hành chưa chắc đủ để tái dựng đúng mọi chiều lịch sử của báo cáo**. Phải xác định quy tắc “as-of” từ yêu cầu nghiệp vụ.

## 10. Chỉ mục cho workload OLTP và OLAP trong PostgreSQL

### 10.1. Chỉ mục B-tree cho truy cập chọn lọc

B-tree rất phù hợp với khóa chính, lookup bằng, khoảng và một số kiểu sắp xếp.

Ví dụ tra danh sách đơn mới nhất của khách:

~~~sql
CREATE INDEX idx_orders_customer_ordered
ON learning_shop.orders
    (customer_id, ordered_at DESC, order_id DESC);
~~~

Với một báo cáo thường lọc đơn `PAID` theo khoảng ngày:

~~~sql
CREATE INDEX idx_orders_paid_time
ON learning_shop.orders (ordered_at)
WHERE status = 'PAID';
~~~

Đây là **partial index**: chỉ chứa các hàng thỏa `status = 'PAID'`. Nó có thể gọn hơn index tất cả trạng thái nếu chỉ một phần đơn đã thanh toán. Trình tối ưu chỉ dùng khi nhận ra điều kiện truy vấn **ngụ ý được predicate** của partial index; với prepared statement và kế hoạch generic, không nên mặc định mọi tham số status đều khớp.

Cần cân nhắc:

- Index giúp đọc nhưng làm `INSERT/UPDATE/DELETE` phải duy trì thêm cấu trúc.
- Nếu có quá ít hàng hoặc báo cáo đọc phần lớn bảng, `Seq Scan` có thể nhanh hơn.
- Partial index cần điều kiện đủ phù hợp, không phải mọi query trên cột `ordered_at` đều dùng được.
- Giữ những index phản ánh **truy vấn quan trọng đã được đo**, không thêm index theo cảm tính.

### 10.2. BRIN cho dữ liệu rất lớn, tương quan theo thời gian

Với bảng sự kiện append-heavy cực lớn có `event_time` tăng gần theo thứ tự vật lý, **BRIN** lưu thông tin tóm tắt của các dải block. Index thường nhỏ hơn B-tree và có thể giúp bỏ qua các dải block ngoài điều kiện:

~~~sql
-- Minh họa trên bảng sự kiện quy mô lớn nếu có.
CREATE INDEX idx_event_time_brin
ON event_logs USING BRIN (event_time);
~~~

BRIN **không xác định chính xác từng hàng** như B-tree. Nếu thời gian phân bố ngẫu nhiên khắp các block, hiệu quả có thể thấp. Không nên chọn BRIN chỉ vì dữ liệu có cột timestamp; cần đo tương quan vật lý, quy mô và truy vấn.

### 10.3. `GIN` không phải index cho mọi aggregate

PostgreSQL có `GIN` hữu ích cho các toán tử như tìm kiếm full-text, mảng hoặc JSONB khi phù hợp. Nhưng báo cáo `SUM(total_amount) GROUP BY month` không tự nhanh hơn chỉ vì tạo GIN trên `total_amount`. Chọn loại index phải dựa trên **toán tử được dùng**.

### 10.4. Partitioning cho bảng lịch sử lớn

Giả sử `orders` có hàng trăm triệu bản ghi và mỗi báo cáo thường lọc một khoảng ngày. Có thể xét **declarative partitioning** theo thời gian để quản lý từng tháng và hỗ trợ pruning:

~~~sql
CREATE TABLE report_events (
    event_id BIGINT NOT NULL,
    event_time TIMESTAMPTZ NOT NULL,
    event_type TEXT NOT NULL,
    payload JSONB
) PARTITION BY RANGE (event_time);

CREATE TABLE report_events_2026_01
PARTITION OF report_events
FOR VALUES FROM ('2026-01-01 00:00:00+00')
           TO   ('2026-02-01 00:00:00+00');

CREATE TABLE report_events_2026_02
PARTITION OF report_events
FOR VALUES FROM ('2026-02-01 00:00:00+00')
           TO   ('2026-03-01 00:00:00+00');
~~~

Ví dụ này partition theo **ranh giới UTC tường minh**. Nếu nghiệp vụ phân tháng theo múi giờ Việt Nam, phải thiết kế ranh giới tương ứng thay vì giả định tháng UTC trùng tháng địa phương.

Partitioning có thể giúp tránh đọc partition không liên quan khi điều kiện lọc phù hợp, đồng thời thuận tiện lưu trữ/xóa dữ liệu cũ. Nhưng:

- Không phải mọi truy vấn đều được cải thiện.
- Số partition quá lớn làm tăng chi phí lập kế hoạch/quản trị.
- Unique constraint/primary key trên partitioned table có quy tắc liên quan đến khóa partition.
- Partitioning **không thay thế chỉ mục và mô hình dữ liệu hợp lý**.

## 11. MVCC, tính nhất quán và độ mới dữ liệu

### 11.1. Snapshot đọc trong PostgreSQL

Ở mức cô lập `READ COMMITTED` mặc định, mỗi câu lệnh đọc thường thấy ảnh chụp những thay đổi đã cam kết tính đến lúc bắt đầu câu lệnh. Hai `SELECT` trong cùng transaction có thể nhìn hai trạng thái khác nhau nếu có giao dịch khác commit giữa chúng.

Ở `REPEATABLE READ`, các câu lệnh dùng cùng snapshot giao dịch theo ngữ nghĩa của PostgreSQL; snapshot thường được thiết lập từ câu lệnh đầu tiên cần dùng snapshot, không nên xem `BEGIN` là tự động chụp mọi dữ liệu theo nghĩa đơn giản. PostgreSQL `REPEATABLE READ` cung cấp snapshot isolation mạnh hơn mức tối thiểu mà chuẩn SQL yêu cầu ở một số khía cạnh.

Ở `SERIALIZABLE`, PostgreSQL dùng **Serializable Snapshot Isolation (SSI)** để phát hiện những lịch chạy có thể vi phạm tính tuần tự; một transaction có thể bị hủy với **serialization failure**, nên ứng dụng cần cơ chế retry **toàn bộ transaction** một cách an toàn.

### 11.2. Giao dịch báo cáo và người ghi vẫn cạnh tranh tài nguyên

MVCC giúp nhiều lượt `SELECT` thông thường không phải đợi khóa ghi trên từng hàng để đọc phiên bản phù hợp. Nhưng truy vấn phân tích dài vẫn có thể gây ảnh hưởng:

- Đọc lượng lớn dữ liệu, dùng CPU và băng thông lưu trữ.
- Cạnh tranh bộ nhớ với hash/sort và các query khác.
- Tạo temporary files nếu `work_mem` hoặc chiến lược thực thi không giữ được dữ liệu trung gian trong bộ nhớ.
- Transaction/snapshot mở rất lâu có thể cản trở việc dọn phiên bản cũ bằng `VACUUM`, làm tăng bloat và áp lực I/O.
- Có thể tương tác với lock cấp bảng/metadata khi có DDL, dù không khóa hàng như một thao tác cập nhật.

Vì vậy, nhận định “PostgreSQL có MVCC nên chạy mọi báo cáo nặng trên primary không ảnh hưởng đặt hàng” là **không đúng**.

### 11.3. Chính xác không đồng nghĩa mới nhất

Một báo cáo có thể **nhất quán** tại snapshot lúc 10:00 nhưng **không mới** so với giao dịch lúc 10:05. Ngược lại, một dashboard chạy mỗi câu trên dữ liệu mới nhất có thể lắp ghép các chỉ số từ **những thời điểm khác nhau**.

Khi thiết kế báo cáo, cần xác định:

- Chấp nhận trễ dữ liệu tối đa bao lâu?
- Các ô trên cùng dashboard có bắt buộc thuộc **cùng snapshot** không?
- Người dùng vừa đặt đơn có cần thấy đơn của chính mình ngay không?
- Kết quả báo cáo là dữ liệu kiểm toán/chốt sổ hay chỉ là xu hướng gần đúng?
- Có cần lịch sử thay đổi hoặc khả năng chạy lại theo thời điểm không?

Những câu hỏi này quyết định cách chọn read replica, materialized view hay một hệ thống phân tích riêng.

## 12. Vì sao báo cáo nặng có thể làm chậm OLTP?

Giả sử primary PostgreSQL vừa xử lý đặt hàng, vừa chạy:

~~~sql
SELECT
    c.segment,
    date_trunc('month', o.ordered_at) AS report_month,
    SUM(o.total_amount)
FROM learning_shop.orders AS o
JOIN learning_shop.customers AS c
  ON c.customer_id = o.customer_id
WHERE o.status = 'PAID'
GROUP BY c.segment, date_trunc('month', o.ordered_at);
~~~

Trên bảng nhỏ thì gần như không đáng kể. Trên hàng trăm triệu dòng, cùng một truy vấn có thể tiêu tốn nhiều tài nguyên.

### 12.1. Cạnh tranh CPU và I/O

Nếu báo cáo quét phần lớn bảng, dữ liệu OLTP có thể bị đẩy khỏi cache chia sẻ và I/O đọc tăng. Request đặt hàng vốn chỉ tra vài khóa chính có thể chậm hơn do phải tranh CPU/I/O, dù không phải đợi row lock.

### 12.2. Sort và hash aggregate tiêu thụ bộ nhớ

Một số kế hoạch `Sort`, `HashAggregate`, `Hash Join` cần bộ nhớ xử lý. Khi không đủ, PostgreSQL có thể ghi dữ liệu tạm ra đĩa. Đặt `work_mem` quá lớn trên toàn hệ thống cũng nguy hiểm vì một query có thể có nhiều node và nhiều query chạy đồng thời.

### 12.3. Báo cáo dài và `VACUUM`

Một transaction giữ snapshot lâu khiến PostgreSQL có thể phải duy trì các phiên bản hàng cũ; điều đó cản trở dọn dẹp và làm bảng/index lớn dần. Với hệ thống ghi dày đặc, đây là chi phí đáng kể.

### 12.4. Tác động đến mục tiêu dịch vụ

OLTP thường cần đáp ứng những phân vị như **p95/p99**; một báo cáo nặng diễn ra mỗi giờ có thể khiến nhóm request trùng thời điểm bị chậm rõ rệt. Chỉ nhìn **thời gian trung bình** có thể che mất những đợt chậm.

Giải pháp không chỉ là “tăng số connection”. Pool lớn hơn có thể khiến thêm nhiều báo cáo nặng cạnh tranh tài nguyên cùng lúc.

## 13. Các cách triển khai OLTP và OLAP trong hệ sinh thái PostgreSQL

### 13.1. Cách 1 — Phân tích trực tiếp trên primary

~~~text
Ứng dụng giao dịch ─┐
                    ├── PostgreSQL primary ─── Bảng giao dịch
Dashboard/report ───┘
~~~

**Ưu điểm:** đơn giản, không cần đồng bộ dữ liệu sang hệ khác, báo cáo truy cập trạng thái đã cam kết theo snapshot của câu query.

**Hạn chế:** báo cáo nặng cạnh tranh tài nguyên với ghi; khó tách ngân sách CPU/I/O; transaction đọc dài có tác động vận hành.

Phù hợp khi dữ liệu/tải còn nhỏ, báo cáo tương đối nhẹ hoặc tần suất thấp, đã đo tác động và chấp nhận được.

### 13.2. Cách 2 — Read replica phục vụ báo cáo

~~~text
                        WAL/streaming replication
Ứng dụng ──► Primary ─────────────────────────► Read replica
                 │                                  │
                 └── Ghi nghiệp vụ                  └── Report SELECT
~~~

Một **physical standby** PostgreSQL có thể tiếp nhận WAL và phục vụ truy vấn đọc trong chế độ hot standby nếu được cấu hình phù hợp. Điều này tách một phần tải đọc khỏi primary.

Nhưng cần lưu ý:

- **Replica có thể chậm** so với primary do lag, đặc biệt khi sao chép bất đồng bộ.
- Ngay sau khi đặt đơn trên primary, người dùng đọc replica **có thể chưa thấy** đơn vừa tạo.
- Truy vấn dài trên standby có thể gặp xung đột với WAL replay và bị hủy tùy chính sách; một số cấu hình hạn chế xung đột lại có thể tăng bloat trên primary.
- Replica vẫn thường lưu các bảng theo dạng hàng và không tự trở thành kho dữ liệu cột.
- Primary vẫn phải sinh/truyền WAL; cần giám sát replication lag và khả năng phục hồi.

Vì vậy replica phù hợp với dashboard chấp nhận trễ nhất định, hoặc báo cáo đọc có thể điều tiết. Những thao tác **read-after-write bắt buộc** có thể cần đọc primary hoặc một cơ chế chờ replica đạt vị trí WAL phù hợp.

### 13.3. Cách 3 — Materialized view hoặc bảng tổng hợp

PostgreSQL hỗ trợ **materialized view**, tức lưu kết quả truy vấn và chỉ thay đổi khi được refresh.

~~~sql
CREATE MATERIALIZED VIEW learning_shop.monthly_paid_revenue AS
SELECT
    date_trunc(
        'month',
        ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh'
    )::date AS month_start,
    COUNT(*) AS paid_orders,
    SUM(total_amount) AS revenue
FROM learning_shop.orders
WHERE status = 'PAID'
GROUP BY 1;

SELECT *
FROM learning_shop.monthly_paid_revenue
ORDER BY month_start;
~~~

Sau khi bảng `orders` thay đổi, materialized view **không tự cập nhật ngay**:

~~~sql
REFRESH MATERIALIZED VIEW learning_shop.monthly_paid_revenue;
~~~

Cần có lịch refresh hoặc quy trình chủ động phù hợp mức trễ chấp nhận được.

Nếu muốn dùng:

~~~sql
CREATE UNIQUE INDEX ux_monthly_paid_revenue_month
ON learning_shop.monthly_paid_revenue (month_start);

REFRESH MATERIALIZED VIEW CONCURRENTLY
    learning_shop.monthly_paid_revenue;
~~~

`CONCURRENTLY` cho phép hạn chế chặn các `SELECT` đọc materialized view trong lúc refresh, nhưng có các điều kiện: materialized view phải **đã được populate**, và phải có **unique index hợp lệ trên cột thông thường, bao phủ tất cả dòng, không phải index biểu thức hoặc partial index**. Không thể tùy tiện dùng `CONCURRENTLY` cho mọi view. Refresh vẫn tốn CPU/I/O, và **PostgreSQL core không tự thực hiện incremental refresh** trên từng hàng chỉ vì có materialized view.

**Khi nào đáng dùng:** báo cáo nhóm cố định, tính lặp lại nhiều lần và có thể chấp nhận dữ liệu theo lịch. Không phù hợp khi truy vấn tùy biến rất đa dạng hoặc cần phản ánh mọi commit ngay lập tức, trừ khi có kiến trúc bổ sung.

### 13.4. Cách 4 — Tách sang hệ thống phân tích

~~~mermaid
flowchart LR
    A["Ứng dụng"] --> B["PostgreSQL OLTP Primary"]
    B --> C["CDC / ETL / Batch"]
    C --> D["Kho dữ liệu / hệ OLAP"]
    D --> E["Dashboard & phân tích"]
~~~

Có thể dùng **ETL/ELT** theo lô hoặc **CDC (Change Data Capture)** từ thay đổi trong PostgreSQL để chuyển dữ liệu sang nơi phân tích riêng.

Lợi ích tiềm năng:

- Tách tài nguyên phân tích khỏi primary.
- Tổ chức schema fact/dimension hoặc lưu trữ hướng cột theo truy vấn phân tích.
- Lưu lịch sử và làm sạch dữ liệu từ nhiều nguồn.
- Mở rộng tính toán báo cáo độc lập hơn với traffic giao dịch.

Đánh đổi:

- Pipeline cần giám sát, khôi phục khi lỗi và đối soát.
- Có độ trễ dữ liệu.
- Cần xử lý xóa, cập nhật, event trùng, event đến lệch thứ tự.
- Chi phí lưu trữ và vận hành tăng.
- Phải kiểm soát thông tin cá nhân và quyền trên dữ liệu bản sao.

**Không có một kiến trúc luôn tốt nhất.** Với một shop nhỏ, PostgreSQL duy nhất có thể đủ. Với nền tảng lớn có dashboard quét dữ liệu liên tục, tách workload thường quan trọng hơn việc tăng số index trên primary.

## 14. So sánh yêu cầu nhất quán giữa OLTP và phân tích

| Câu hỏi | Cách xử lý nên ưu tiên |
|---|---|
| Có thể giảm tồn kho cho đơn đang tạo không? | Kiểm tra/cập nhật nguyên tử trong transaction |
| Tổng tiền đơn vừa thanh toán đã được commit chưa? | Đọc dữ liệu transaction ở nguồn phù hợp |
| Báo cáo tổng doanh thu tháng trước có thể chậm 30 phút không? | Nếu chấp nhận, dùng materialized view hoặc pipeline |
| Sau khi ghi, người dùng có phải đọc thấy thay đổi ngay? | Tránh đọc replica chưa bắt kịp hoặc có cơ chế consistency |
| Một dashboard có nhiều biểu đồ phải dùng cùng một mốc dữ liệu? | Dùng snapshot chung hoặc dataset/report snapshot được xác định |
| Báo cáo kiểm toán cần tái lập số liệu quá khứ? | Lưu sự kiện/phiên bản lịch sử và quy tắc chốt dữ liệu |
| Truy vấn ad hoc quét toàn lịch sử gây chậm đặt hàng? | Giới hạn tài nguyên, tối ưu và cân nhắc tách tầng phân tích |

Dù OLTP thường đòi độ mới cao, **OLAP cũng có thể cần độ chính xác tuyệt đối**; khác biệt là hệ thống phân tích có thể chấp nhận một **độ trễ được công bố** trong khi vẫn đòi tổng, phân nhóm và lịch sử đúng với mốc đã chốt.

## 15. Đối chiếu kế hoạch truy vấn bằng PostgreSQL

PostgreSQL có công cụ quan trọng để xem và đo đường thực thi:
 
~~~sql
EXPLAIN
SELECT order_id, customer_id, status
FROM learning_shop.orders
WHERE order_id = 1001;
~~~

Với truy vấn phân tích:

~~~sql
EXPLAIN
SELECT
    c.segment,
    SUM(o.total_amount) AS revenue
FROM learning_shop.orders AS o
JOIN learning_shop.customers AS c
  ON c.customer_id = o.customer_id
WHERE o.status = 'PAID'
GROUP BY c.segment;
~~~

Một số node thường gặp:

| Node | Ý nghĩa |
|---|---|
| `Seq Scan` | Đọc tuần tự nhiều/trọn bảng |
| `Index Scan` | Dùng index tìm khóa, sau đó có thể lấy dữ liệu bảng |
| `Index Only Scan` | Có thể lấy dữ liệu từ index trong điều kiện thích hợp; kiểm tra visibility vẫn có thể cần truy cập heap |
| `Bitmap Index Scan` + `Bitmap Heap Scan` | Tập hợp vị trí hàng qua index rồi truy cập các trang heap |
| `Nested Loop` | Lặp phép nối theo một nhánh và tìm hàng bên kia |
| `Hash Join` | Xây bảng băm để nối các tập |
| `Merge Join` | Nối các tập đã được sắp phù hợp |
| `HashAggregate` / `GroupAggregate` | Tính tổng hợp theo nhóm |
| `Sort` | Sắp xếp dữ liệu |
| `Gather` / `Gather Merge` | Thu kết quả từ các parallel workers |

`EXPLAIN` hiển thị **kế hoạch và ước lượng**. Muốn biết số hàng/thời gian thực tế, dùng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    c.segment,
    SUM(o.total_amount) AS revenue
FROM learning_shop.orders AS o
JOIN learning_shop.customers AS c
  ON c.customer_id = o.customer_id
WHERE o.status = 'PAID'
GROUP BY c.segment;
~~~

**Cảnh báo:** `EXPLAIN ANALYZE` thực thi câu SQL thật. Ở ví dụ là `SELECT`; nếu áp dụng cho `UPDATE/DELETE/INSERT`, thay đổi có thể xảy ra. Khi muốn thử DML với `EXPLAIN ANALYZE` trong lab, phải có phương án transaction và rollback phù hợp, và vẫn cần xét các tác dụng phụ không thể rollback hoàn toàn.

### 15.1. Đừng đánh giá hiệu năng bằng số dòng kết quả

Một query OLAP có thể trả **12 dòng** nhưng đọc 500 triệu hàng. Trái lại query OLTP trả **100 dòng** nhưng dùng index tra trong vài mili giây. Số dòng **trả về** khác số dòng **phải xử lý**.

### 15.2. Vì sao cùng một SQL dùng kế hoạch khác nhau?

Optimizer phụ thuộc:

- Thống kê về số hàng và phân bố dữ liệu.
- Index sẵn có.
- Giá trị điều kiện và tính chọn lọc.
- Chi phí I/O/CPU được ước lượng.
- Bộ nhớ, mức parallelism và phiên bản PostgreSQL.
- Tình trạng cache và cấu hình môi trường.

Bảng lab rất nhỏ thường thích hợp với `Seq Scan`. **Đừng dùng `SET enable_seqscan = off` như phương pháp tối ưu mặc định.** Cách can thiệp đó chỉ hữu ích có kiểm soát khi điều tra phương án, không giải quyết nguyên nhân gốc của một index chưa được chọn.

### 15.3. Cách đo cho hệ thống thật

Lưu cùng một truy vấn với cùng bộ tham số, sau đó so:

- Thời gian p50/p95/p99 và số lần chạy.
- Kế hoạch, hàng ước lượng/thực tế, `BUFFERS`.
- CPU/I/O và temporary files.
- Lock waits và số transaction dài.
- Độ trễ replica hoặc pipeline nếu dùng bản sao.
- Chi phí `INSERT/UPDATE` sau khi thêm index.

Có thể dùng `pg_stat_statements` nếu extension và cấu hình theo môi trường đã được bật; không mặc định nó luôn sẵn có hoặc muốn truy cập metric là chỉ cần chạy một câu `SELECT`.

## 16. Những thiết kế nên tránh

### 16.1. Dùng primary phục vụ báo cáo full-scan không giới hạn

Bản thân truy vấn phân tích không sai, nhưng chạy đồng thời không kiểm soát có thể tranh tài nguyên với đặt hàng. Cần giới hạn khối lượng, lên lịch, tối ưu hoặc tách sang replica/kho phân tích.

### 16.2. Cố bắt mọi truy vấn dùng index

Một báo cáo đọc 80% bảng có thể hợp lý với `Seq Scan`, trong khi truy vấn tra một đơn nên ưu tiên index nếu dữ liệu đủ lớn. Mục tiêu là **chi phí thực thi tổng thể**, không phải “không bao giờ quét bảng”.

### 16.3. Tạo quá nhiều index lên bảng ghi liên tục

Mỗi index tăng chi phí ghi và sử dụng dung lượng. Thêm 10 index để hỗ trợ 10 báo cáo ít dùng có thể làm chậm hàng triệu thao tác OLTP mỗi ngày. Xem xét index dùng chung, tổng hợp trước hoặc chuyển workload.

### 16.4. Nhầm transaction snapshot với dữ liệu cập nhật tức thì

Một truy vấn theo snapshot có thể nhất quán nhưng không chứa commit mới hơn snapshot. Dữ liệu trên replica hay bảng materialized còn có chính sách trễ riêng.

### 16.5. Nhầm replication với backup

Replica có thể sao chép cả thay đổi sai hoặc thao tác xóa. WAL/replication giúp đồng bộ và phục hồi theo quy trình, nhưng vẫn cần backup, kiểm tra restore và kế hoạch PITR đúng yêu cầu RPO.

### 16.6. Tổng hợp đơn hàng và chi tiết bị nhân dòng

Ví dụ JOIN `orders` với `order_items` rồi `SUM(orders.total_amount)` sẽ **đếm lại tổng đơn nhiều lần** nếu đơn có nhiều dòng chi tiết. Phải xác định grain và chọn chỉ số đúng: tổng tiền theo đơn thì tổng hợp ở cấp đơn, còn doanh thu theo sản phẩm thường dựa vào `quantity * unit_price` ở cấp chi tiết.

### 16.7. Không cố định múi giờ báo cáo

`timestamptz` là một thời điểm tuyệt đối; “doanh thu ngày 01/02” phải được quy định theo múi giờ. Nếu nhóm theo time zone mặc định của session, cùng dữ liệu có thể rơi sang ngày khác khi cấu hình thay đổi.

### 16.8. Giữ transaction báo cáo mở quá lâu

Snapshot lâu có thể khiến `VACUUM` không dọn được phiên bản cũ và tăng bloat. Cần phân biệt một câu query dài hợp lệ với transaction “idle in transaction” bị bỏ quên.

### 16.9. Không định nghĩa độ mới của dữ liệu

Dashboard trên replica bất đồng bộ hoặc materialized view có thể hiển thị số liệu cũ. Nếu sản phẩm yêu cầu gần thời gian thực, cần ghi rõ độ trễ mục tiêu, giám sát và cơ chế fallback.

### 16.10. Đánh đồng star schema với dữ liệu luôn đúng

Fact/dimension, ETL và bảng tổng hợp có thể giúp truy vấn nhanh, nhưng nếu pipeline nạp thiếu hoặc nhân đôi sự kiện thì báo cáo sai. Cần đối soát, khóa định danh, xử lý cập nhật/xóa và lịch sử.

## 17. Kịch bản thiết kế hệ thống: từ shop nhỏ tới nền tảng lớn

### Giai đoạn A — shop nhỏ

- Một PostgreSQL instance lưu bảng khách hàng, đơn hàng, chi tiết, sản phẩm.
- OLTP sử dụng primary key, foreign key, transaction, chỉ mục chọn lọc.
- Báo cáo theo tháng chạy không thường xuyên, tập dữ liệu nhỏ.
- Theo dõi thời gian query; chưa cần ETL hoặc kho dữ liệu độc lập.

**Lý do:** đơn giản hóa vận hành; tối ưu kiến trúc lớn khi chưa có yêu cầu thực tế thường không đáng.

### Giai đoạn B — dữ liệu và dashboard tăng

- Tối ưu SQL và index cho các bộ lọc phổ biến.
- Xét bảng tổng hợp hoặc materialized view cho chỉ số tính lặp lại.
- Giới hạn thời gian/tần suất báo cáo nặng trên primary.
- Có thể thêm read replica nếu dashboard chấp nhận độ trễ.
- Theo dõi p95/p99 OLTP, CPU/I/O, `VACUUM` và replication lag.

**Lý do:** giảm tranh chấp workload mà chưa phải thay toàn bộ mô hình.

### Giai đoạn C — phân tích đa nguồn và lịch sử lớn

- PostgreSQL primary vẫn ưu tiên transaction nghiệp vụ.
- Tách ingestion bằng CDC/ETL/batch sang tầng phân tích.
- Thiết kế fact/dimension, định nghĩa grain và dữ liệu lịch sử.
- Áp dụng chất lượng dữ liệu, đối soát, quản lý quyền truy cập.
- Xác định SLA độ mới, cơ chế xử lý sự kiện trễ/nhân đôi và khôi phục pipeline.

**Lý do:** phân tích trở thành một sản phẩm dữ liệu với quy mô, lịch sử và yêu cầu vận hành riêng.

## 18. Bài tập thực hành

Dùng schema `learning_shop` ở phần 6. Mỗi bài yêu cầu giải thích vì sao truy vấn thiên về OLTP hoặc OLAP, không chỉ viết SQL đúng cú pháp.

### Bài 1 — Phân loại workload

Phân loại các thao tác sau, nêu ít nhất một chỉ số cần tối ưu:

1. Lấy đơn hàng có `order_id = 1001`.
2. Giảm tồn kho cho sản phẩm 12 và tạo đơn mới.
3. Tính doanh thu từng tháng của ba năm gần nhất.
4. Liệt kê top 20 khách chi tiêu cao nhất.
5. Kiểm tra email đã tồn tại trước khi đăng ký.
6. Tạo bảng tổng doanh thu theo ngày để dashboard truy vấn lại.

### Bài 2 — Viết giao dịch có điều kiện

Viết câu `UPDATE` giảm tồn kho sản phẩm 11 đi ba đơn vị **chỉ nếu đủ hàng**, trả lại số tồn còn lại. Nêu cách xử lý khi không có dòng `RETURNING`.

### Bài 3 — Doanh thu theo ngày

Viết truy vấn chỉ lấy đơn `PAID` trong tháng 01/2026 theo **giờ Việt Nam**, nhóm theo ngày, trả tổng số đơn và tổng doanh thu. Giải thích lý do dùng khoảng nửa mở trên `ordered_at`.

### Bài 4 — Top khách

Viết truy vấn `JOIN` khách hàng với đơn hàng để tính doanh thu `PAID` theo khách. Vì sao `SUM(o.total_amount)` có thể bị nhân lên khi JOIN tiếp với `order_items`?

### Bài 5 — Chọn chỉ mục

So sánh hai điều kiện:

~~~sql
-- Trường hợp A: tra một khách và sắp đơn mới nhất.
WHERE customer_id = 1
ORDER BY ordered_at DESC
LIMIT 20

-- Trường hợp B: lấy doanh thu PAID theo toàn bộ năm.
WHERE status = 'PAID'
  AND ordered_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
  AND ordered_at <  TIMESTAMPTZ '2027-01-01 00:00:00+07'
~~~

Đề xuất index đáng thử cho A và B. Liệt kê lý do B có thể vẫn dùng `Seq Scan` khi dữ liệu lớn nhưng phần lớn đơn đều `PAID`.

### Bài 6 — Vấn đề độ mới dữ liệu

Người dùng vừa tạo đơn trên primary. Ứng dụng đọc `orders` trên read replica nhưng chưa thấy đơn. Điều này có nhất thiết là database bị mất dữ liệu không? Nêu hai phương án đáp ứng yêu cầu read-after-write.

### Bài 7 — Materialized view

Tạo materialized view doanh thu theo tháng từ `orders`. Nếu sau đó thêm một đơn `PAID`, tại sao `SELECT` trên view có thể chưa đổi? Muốn refresh concurrently cần đáp ứng điều kiện gì?

### Bài 8 — Đo kế hoạch

Dùng `EXPLAIN (ANALYZE, BUFFERS)` trên một truy vấn tổng doanh thu theo trạng thái. Ghi:

- `Seq Scan` hay `Index Scan`?
- Aggregate dùng node nào?
- `actual rows` và thời gian thực tế?
- Buffers đọc từ cache hay từ đĩa?
- Có thể kết luận gì về dữ liệu vài dòng của lab và điều gì **không thể kết luận** cho production?

### Bài 9 — Chọn kiến trúc

Một shop có 10 triệu đơn; API đặt hàng cần p99 rất thấp, dashboard báo cáo chấp nhận chậm 15 phút và chạy những truy vấn nặng hàng phút. Bạn chọn một primary duy nhất, primary + replica, hay pipeline sang OLAP? Nêu cách kiểm tra trước khi quyết định.

## 19. Gợi ý lời giải

### Bài 1

1. Tra đơn theo khóa: **OLTP**, tối ưu lookup và độ trễ.
2. Trừ tồn và tạo đơn: **OLTP**, tối ưu tính đúng đắn, lock contention và tỷ lệ commit thành công.
3. Tổng tháng ba năm: **OLAP**, quan tâm lượng dữ liệu đọc, aggregate và thời gian báo cáo.
4. Top khách: **OLAP**, quan tâm JOIN/group/sort.
5. Kiểm tra email: **OLTP**; dùng unique constraint để **database bảo vệ tính duy nhất**, không chỉ `SELECT` rồi tin rằng không có race condition.
6. Tạo bảng tổng: **pipeline/phần chuẩn bị phân tích**; có ghi nhưng mục tiêu là hỗ trợ OLAP.

### Bài 2

~~~sql
UPDATE learning_shop.products
SET stock_qty = stock_qty - 3
WHERE product_id = 11
  AND stock_qty >= 3
RETURNING product_id, stock_qty;
~~~

Nếu không có dòng kết quả, ứng dụng báo không tìm thấy hoặc không đủ tồn kho theo nghiệp vụ; trong transaction nhiều bước phải rollback nếu không đạt điều kiện.

### Bài 3

~~~sql
SELECT
    (ordered_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date AS order_day,
    COUNT(*) AS order_count,
    SUM(total_amount) AS revenue
FROM learning_shop.orders
WHERE status = 'PAID'
  AND ordered_at >= TIMESTAMPTZ '2026-01-01 00:00:00+07'
  AND ordered_at <  TIMESTAMPTZ '2026-02-01 00:00:00+07'
GROUP BY 1
ORDER BY 1;
~~~

Khoảng nửa mở bao trọn mọi thời điểm trong tháng, không phụ thuộc độ chính xác mili/vi giây của cột.

### Bài 4

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    COALESCE(
        SUM(o.total_amount) FILTER (WHERE o.status = 'PAID'),
        0
    ) AS paid_revenue
FROM learning_shop.customers AS c
LEFT JOIN learning_shop.orders AS o
  ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.customer_name
ORDER BY paid_revenue DESC, c.customer_id;
~~~

Cách này giữ cả khách chưa có đơn và trả 0. Nếu nối tiếp `order_items`, một đơn có hai dòng item sẽ khiến `orders.total_amount` bị lặp trong kết quả JOIN; phải tổng hợp ở đúng grain hoặc xây các aggregate con trước khi nối.

### Bài 5

A có thể dùng `(customer_id, ordered_at DESC, order_id DESC)`. B có thể thử partial index `(ordered_at) WHERE status = 'PAID'`, nhưng nếu cần đọc phần rất lớn bảng để cộng doanh thu, `Seq Scan` vẫn có thể rẻ hơn. Không thể quyết định nếu chưa xem `EXPLAIN` và dữ liệu.

### Bài 6

Replica bất đồng bộ có thể **lag**, không nhất thiết mất dữ liệu. Có thể đọc primary ngay sau giao dịch ghi hoặc thiết kế cơ chế nhất quán theo vị trí WAL/đợi replica đạt mốc cần thiết, có timeout và fallback phù hợp.

### Bài 7

Materialized view chỉ phản ánh lần populate/refresh trước. `REFRESH MATERIALIZED VIEW` cập nhật lại; `CONCURRENTLY` có các điều kiện về populated view và unique index hợp lệ trên các cột thường, bao phủ mọi dòng.

### Bài 8

Không có một kế hoạch/thời gian duy nhất cho mọi PostgreSQL. Dữ liệu lab rất nhỏ thường khiến `Seq Scan` phù hợp; điều này **không chứng minh** B-tree vô ích khi bảng có hàng triệu dòng. Cần đo trên dữ liệu đại diện.

### Bài 9

Với phân tích nặng và SLA p99 OLTP khắt khe, nên ưu tiên **tách tài nguyên đọc phân tích**. Nếu dashboard chủ yếu là truy vấn PostgreSQL tương thích và chấp nhận độ trễ, replica hoặc các bảng tổng hợp có thể là bước đầu. Nếu báo cáo phức tạp, đa nguồn, quét lịch sử lớn hoặc cần mô hình dimensional, pipeline tới hệ OLAP chuyên biệt có thể phù hợp hơn. Trước khi chốt cần đo workload, CPU/I/O, lag và chi phí vận hành.

## 20. Kết luận

**OLTP** hướng tới xử lý **những thay đổi nhỏ, đồng thời, chính xác**: tra cứu theo khóa, cập nhật có điều kiện, transaction và ràng buộc. **OLAP** hướng tới hiểu **bức tranh tổng hợp của nhiều giao dịch**: quét dữ liệu, JOIN, GROUP BY, window functions, phân tích theo thời gian và lịch sử.

PostgreSQL đủ linh hoạt để đáp ứng cả hai ở nhiều quy mô, nhưng khác biệt về hình dạng workload đòi hỏi thiết kế **schema, index, transaction, độ mới dữ liệu và kiến trúc triển khai** có chủ đích. Một query OLAP nặng có thể ảnh hưởng OLTP ngay cả khi MVCC giảm xung đột đọc–ghi ở mức hàng.

Khi bắt đầu một bài toán, hãy tự hỏi: **“Tôi đang thay đổi trạng thái của một nghiệp vụ, hay phân tích nhiều sự kiện để rút ra chỉ số?”** Từ câu trả lời đó, lựa chọn cách đọc/ghi, ranh giới transaction, chỉ mục, chiến lược tổng hợp và nơi chạy truy vấn. Quyết định tốt không dựa trên nhãn OLTP/OLAP một cách máy móc, mà dựa trên **tính đúng đắn, độ trễ, quy mô, độ mới và chi phí thực tế**.
