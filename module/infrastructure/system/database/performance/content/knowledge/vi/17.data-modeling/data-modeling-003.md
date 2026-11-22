# Chuẩn hóa và phi chuẩn hóa dưới góc nhìn đường đọc ghi

## Mục tiêu bài học

Thiết kế dữ liệu ảnh hưởng trực tiếp đến số lần đọc, số phép nối, lượng dữ liệu phải ghi, mức tranh chấp và công việc bảo trì của cơ sở dữ liệu. Chuẩn hóa giúp giảm dữ liệu lặp và bảo vệ tính nhất quán khi cập nhật. Phi chuẩn hóa có thể rút ngắn đường đọc bằng cách lưu sẵn một phần dữ liệu hoặc kết quả tổng hợp, nhưng làm phát sinh chi phí đồng bộ và nguy cơ dữ liệu không nhất quán.

Trong chương **Mô hình dữ liệu** của module **DATABASE_PERFORMANCE**, bài học này phân tích chuẩn hóa và phi chuẩn hóa theo đường đọc/ghi thực tế. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung bao gồm thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, quyết định mô hình hóa cần bắt đầu từ workload, ràng buộc nghiệp vụ và số liệu, rồi mới chọn cách tổ chức dữ liệu.

Sau bài học, bạn có thể:

- Giải thích mục tiêu của chuẩn hóa và các dạng bất thường do dữ liệu lặp.
- Đánh giá tác động của mô hình chuẩn hóa lên đường đọc và đường ghi.
- Nhận diện tình huống phi chuẩn hóa có thể giảm phép nối hoặc công việc tổng hợp lặp lại.
- Chọn mẫu phi chuẩn hóa phù hợp như snapshot nghiệp vụ, bảng tổng hợp, materialized view hoặc read model.
- Thiết kế cách duy trì dữ liệu phi chuẩn hóa và xử lý cập nhật đồng thời, lỗi đồng bộ, rebuild.
- Đo lợi ích đọc cùng chi phí ghi, lưu trữ, I/O, khóa và độ phức tạp vận hành.

## 1. Chuẩn hóa và phi chuẩn hóa giải quyết vấn đề gì?

**Chuẩn hóa (normalization)** tổ chức dữ liệu thành các quan hệ sao cho mỗi sự kiện hoặc thuộc tính được lưu ở nơi có trách nhiệm rõ ràng, hạn chế lặp thông tin và giảm nguy cơ cập nhật không đồng bộ. Các bảng liên kết bằng khóa chính và khóa ngoại.

**Phi chuẩn hóa (denormalization)** chủ động lưu lặp một phần dữ liệu, hoặc lưu sẵn kết quả tính toán, nhằm phục vụ một đường đọc cụ thể với ít phép nối hoặc ít phép tính hơn. Dữ liệu lặp cần có quy tắc xác định nguồn sự thật và cơ chế duy trì.

Hai cách tiếp cận không phải lựa chọn tuyệt đối cho toàn bộ hệ thống. Một ứng dụng có thể dùng mô hình chuẩn hóa cho giao dịch lõi, đồng thời có bảng tổng hợp hoặc read model phi chuẩn hóa cho dashboard và tìm kiếm. Mỗi phần phục vụ một nhóm truy vấn và yêu cầu nhất quán khác nhau.

### 1.1. Ví dụ dữ liệu bán hàng

Một mô hình đơn giản có thể gồm:

```text
customers
  customer_id (PK)
  customer_name
  email
  region_id (FK)

regions
  region_id (PK)
  region_name

orders
  order_id (PK)
  customer_id (FK)
  created_at
  status

order_items
  order_item_id (PK)
  order_id (FK)
  product_id (FK)
  quantity
  unit_price

products
  product_id (PK)
  product_name
  current_price
```

Tên khách hàng và tên khu vực được lưu ở bảng có trách nhiệm quản lý chúng. Đơn hàng tham chiếu khách hàng; dòng đơn hàng tham chiếu sản phẩm. Khi tên khu vực thay đổi, hệ thống chỉ cập nhật một dòng trong `regions` thay vì sửa hàng triệu đơn hàng.

Đường đọc báo cáo doanh thu theo khu vực phải nối nhiều bảng:

```sql
SELECT
    r.region_id,
    r.region_name,
    SUM(oi.quantity * oi.unit_price) AS revenue
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
JOIN regions AS r
  ON r.region_id = c.region_id
JOIN order_items AS oi
  ON oi.order_id = o.order_id
WHERE o.status = 'COMPLETED'
  AND o.created_at >= TIMESTAMP '2026-10-01 00:00:00'
  AND o.created_at <  TIMESTAMP '2026-11-01 00:00:00'
GROUP BY r.region_id, r.region_name;
```

Mô hình chuẩn hóa giữ dữ liệu dễ cập nhật và hạn chế lặp, nhưng báo cáo phải thực hiện các phép nối và tổng hợp. Nếu báo cáo này chạy rất thường xuyên trên lượng dữ liệu lớn, một read model tổng hợp có thể đáng cân nhắc. Trước khi thay đổi, cần kiểm tra kế hoạch, số dòng qua từng join, chỉ mục và thống kê; số lượng bảng tham gia tự nó chưa chứng minh truy vấn chậm.

## 2. Chuẩn hóa và các bất thường dữ liệu

Chuẩn hóa thường được mô tả qua các dạng chuẩn. Trong công việc thiết kế ứng dụng, hiểu các nguyên tắc cốt lõi quan trọng hơn việc áp dụng máy móc một nhãn dạng chuẩn.

### 2.1. Dữ liệu lặp gây bất thường cập nhật

Giả sử một bảng đơn hàng lưu cả thông tin khách hàng:

| order_id | customer_id | customer_name | customer_email | total |
|---:|---:|---|---|---:|
| 1001 | 42 | An | an@example.test | 500000 |
| 1002 | 42 | An | an@example.test | 250000 |
| 1003 | 57 | Bình | binh@example.test | 900000 |

Nếu khách hàng 42 đổi email, tất cả dòng đơn hàng của khách đó phải được cập nhật. Nếu chỉ cập nhật một số dòng, dữ liệu mâu thuẫn. Đây là **bất thường cập nhật**.

Các dạng bất thường khác:

- **Bất thường chèn:** không thể lưu một khách hàng nếu chưa có đơn hàng, hoặc phải tạo dòng giả chỉ để giữ thông tin khách.
- **Bất thường xóa:** xóa đơn hàng cuối cùng có thể vô tình xóa luôn thông tin khách hàng nếu dữ liệu bị gộp trong cùng một bảng.
- **Bất thường cập nhật:** một thuộc tính được lưu ở nhiều dòng và có thể lệch nhau sau khi sửa.

Tách khách hàng ra bảng riêng giúp mỗi thuộc tính có một nơi quản lý:

```sql
CREATE TABLE customers (
    customer_id bigint PRIMARY KEY,
    customer_name text NOT NULL,
    customer_email text NOT NULL UNIQUE
);

CREATE TABLE orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL REFERENCES customers(customer_id),
    created_at timestamptz NOT NULL,
    status text NOT NULL
);
```

Đơn hàng vẫn có thể truy xuất thông tin khách qua phép nối. Khóa ngoại bảo đảm tham chiếu hợp lệ; chỉ mục trên cột khóa ngoại có thể cần thiết cho đường truy cập, nhưng PostgreSQL không tự động tạo index ở phía cột tham chiếu khi khai báo foreign key.

### 2.2. Một số nguyên tắc dạng chuẩn

- **First Normal Form (1NF):** mỗi ô chứa một giá trị theo miền dữ liệu đã xác định; tránh nhóm cột lặp hoặc danh sách giá trị không có cấu trúc trong một cột khi cần truy vấn từng phần tử.
- **Second Normal Form (2NF):** quan hệ đạt 1NF và thuộc tính không khóa phụ thuộc đầy đủ vào toàn bộ khóa ứng viên, không chỉ một phần của khóa ghép.
- **Third Normal Form (3NF):** quan hệ đạt 2NF và loại bỏ phụ thuộc bắc cầu không phù hợp giữa thuộc tính không khóa; thuộc tính mô tả một thực thể khác thường nên được đặt ở quan hệ của thực thể đó.
- **Boyce-Codd Normal Form (BCNF):** với mọi phụ thuộc hàm không tầm thường, vế trái phải là siêu khóa. BCNF xử lý chặt hơn một số trường hợp mà 3NF vẫn cho phép.

Ví dụ, nếu bảng `order_items` dùng khóa ghép `(order_id, product_id)` và lưu `product_name`, thì `product_name` phụ thuộc vào `product_id`, không phụ thuộc vào toàn bộ khóa dòng đơn hàng. Tên sản phẩm bị lặp ở mọi đơn chứa sản phẩm đó. Tách thông tin sản phẩm sang `products` loại bỏ phần lặp này.

Tuy nhiên, không phải mọi dữ liệu lặp đều là sai. `unit_price` trong `order_items` thường là giá đã chốt tại thời điểm mua, không phải bản sao thừa của `products.current_price`. Đây là **snapshot nghiệp vụ** cần giữ để hóa đơn lịch sử không thay đổi khi giá niêm yết được cập nhật. Phân biệt dữ liệu lặp vô tình với dữ liệu lịch sử có ý nghĩa là bước quan trọng trong mô hình hóa.

## 3. Tác động của chuẩn hóa lên đường đọc

Mô hình chuẩn hóa thường yêu cầu nối bảng để lấy dữ liệu liên quan. Chi phí thực tế phụ thuộc số dòng, độ chọn lọc, khóa nối, chỉ mục và thuật toán join.

### 3.1. Khi phép nối không phải nút thắt

Một truy vấn nối nhiều bảng vẫn có thể rất nhanh nếu:

- Mỗi bảng được lọc bằng điều kiện chọn lọc tốt.
- Khóa nối có kiểu dữ liệu tương thích và có chỉ mục phù hợp.
- Ước lượng số dòng chính xác.
- Nested Loop chỉ lặp trên tập nhỏ, hoặc Hash/Merge Join xử lý tập lớn hiệu quả.
- Dữ liệu cần đọc nằm trong cache hoặc có I/O phù hợp.

Không nên phi chuẩn hóa chỉ vì truy vấn có ba hoặc bốn phép `JOIN`. Trước tiên hãy xem `EXPLAIN (ANALYZE, BUFFERS)`, estimated/actual rows, loops, buffer reads, sort/hash spill và thời gian của từng node.

### 3.2. Khi chuẩn hóa làm đường đọc tốn kém

Chuẩn hóa có thể tạo chi phí đáng kể trong một số workload:

- Dashboard liên tục nối nhiều bảng và tổng hợp lịch sử lớn.
- API đọc danh sách phải lấy cùng một số thuộc tính từ nhiều quan hệ cho mỗi dòng.
- Truy vấn lặp lại cùng một phép tính hoặc phép nối trên tập dữ liệu lớn.
- Báo cáo cần tổng hợp theo chiều thời gian, khu vực, sản phẩm và kênh bán.
- Một đường đọc có SLA rất thấp nhưng mô hình giao dịch tối ưu cho cập nhật chính xác.

Khi đó, thay vì sửa toàn bộ mô hình lõi, có thể bổ sung một cấu trúc đọc được thiết kế cho truy vấn quan trọng. Cấu trúc đó cần được duy trì và đo chi phí riêng.

## 4. Tác động của chuẩn hóa lên đường ghi

Chuẩn hóa thường giúp thay đổi một thuộc tính ở một nơi, nhưng một nghiệp vụ có thể cần ghi nhiều bảng trong cùng transaction.

Ví dụ tạo đơn hàng có thể phải:

1. Tạo dòng `orders`.
2. Tạo một hoặc nhiều dòng `order_items`.
3. Giảm tồn kho trong `inventory`.
4. Ghi thanh toán hoặc trạng thái liên quan.

Những thay đổi cần nhất quán phải được thực hiện trong transaction phù hợp. Giao dịch dài làm khóa được giữ lâu hơn, tăng khả năng chờ và rollback. Chỉ mục trên các bảng cũng phải được duy trì khi ghi, vì vậy thiết kế index quá rộng có thể làm chi phí ghi tăng.

Một lợi ích của chuẩn hóa là khi sửa tên khách hàng hoặc địa chỉ mặc định, chỉ cần cập nhật một bản ghi. Nếu cùng thông tin bị sao chép vào hàng triệu đơn hàng, một lần thay đổi có thể tạo nhiều lần ghi, WAL, khóa và I/O. Vì thế, phi chuẩn hóa để tăng tốc đọc có thể làm đường ghi đắt hơn đáng kể.

## 5. Phi chuẩn hóa có chủ đích

Phi chuẩn hóa là việc lưu thêm thông tin để phục vụ một đường đọc xác định. Mỗi mẫu có cách duy trì và yêu cầu nhất quán khác nhau.

### 5.1. Lưu snapshot nghiệp vụ

Một đơn hàng cần giữ tên hoặc địa chỉ nhận hàng tại thời điểm đặt, kể cả khi khách hàng cập nhật hồ sơ sau đó. Có thể lưu snapshot trên đơn hàng:

```sql
CREATE TABLE orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL REFERENCES customers(customer_id),
    created_at timestamptz NOT NULL,
    shipping_name text NOT NULL,
    shipping_address text NOT NULL,
    status text NOT NULL
);
```

Các trường `shipping_name` và `shipping_address` là dữ liệu lịch sử của giao dịch. Chúng không nhất thiết phải đồng bộ khi hồ sơ khách hàng thay đổi. Cần ghi rõ ý nghĩa trong mô hình để tránh một quy trình đồng bộ vô tình ghi đè snapshot.

Snapshot thường hợp lý khi giá trị tại thời điểm sự kiện là một phần của sự thật nghiệp vụ: giá bán, thuế suất, địa chỉ giao hàng, tên pháp lý trên hóa đơn hoặc tỷ giá được dùng để chốt giao dịch.

### 5.2. Sao chép thuộc tính để giảm phép nối

Có thể sao chép `customer_region` vào bảng đơn hàng nếu truy vấn rất thường xuyên lọc hoặc nhóm theo khu vực tại thời điểm tạo đơn. Nhưng phải quyết định ý nghĩa của trường:

- Nếu muốn biết khu vực hiện tại của khách, giá trị sao chép có thể lỗi thời khi khách đổi khu vực.
- Nếu muốn biết khu vực tại thời điểm đặt hàng, giá trị phải được xem là snapshot và không cập nhật theo hồ sơ hiện tại.

Hai khái niệm này khác nhau. Tên cột và tài liệu dữ liệu nên phản ánh rõ, ví dụ `customer_region_at_order` nếu là snapshot. Đừng dùng một cột mơ hồ cho cả báo cáo hiện tại và lịch sử.

### 5.3. Bảng tổng hợp (summary table)

Nếu dashboard thường xuyên tính doanh thu theo ngày và khu vực từ hàng trăm triệu dòng chi tiết, có thể duy trì bảng tổng hợp:

```sql
CREATE TABLE daily_region_sales (
    sales_date date NOT NULL,
    region_id bigint NOT NULL,
    order_count bigint NOT NULL DEFAULT 0,
    revenue numeric(18, 2) NOT NULL DEFAULT 0,
    PRIMARY KEY (sales_date, region_id)
);
```

Đường đọc trở nên đơn giản:

```sql
SELECT sales_date, region_id, order_count, revenue
FROM daily_region_sales
WHERE sales_date >= DATE '2026-10-01'
  AND sales_date <  DATE '2026-11-01'
ORDER BY sales_date, region_id;
```

Truy vấn đọc ít dòng và ít phép nối hơn nhiều so với tính lại từ bảng chi tiết. Đổi lại, hệ thống phải cập nhật bảng tổng hợp khi đơn hàng được tạo, hoàn tất, hủy hoặc điều chỉnh. Nếu không xử lý đầy đủ các chuyển trạng thái và thao tác lặp, số liệu có thể sai.

### 5.4. Materialized view

Materialized view lưu kết quả của một truy vấn tại thời điểm làm mới. Nó phù hợp với báo cáo có thể chấp nhận dữ liệu trễ theo lịch hoặc theo yêu cầu.

Ví dụ trong PostgreSQL:

```sql
CREATE MATERIALIZED VIEW monthly_region_sales AS
SELECT
    date_trunc('month', o.created_at)::date AS sales_month,
    c.region_id,
    COUNT(DISTINCT o.order_id) AS order_count,
    SUM(oi.quantity * oi.unit_price) AS revenue
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
JOIN order_items AS oi
  ON oi.order_id = o.order_id
WHERE o.status = 'COMPLETED'
GROUP BY date_trunc('month', o.created_at)::date, c.region_id;
```

Làm mới toàn bộ view:

```sql
REFRESH MATERIALIZED VIEW monthly_region_sales;
```

Trong PostgreSQL, `REFRESH MATERIALIZED VIEW CONCURRENTLY` có thể cho phép truy vấn đọc tiếp tục trong lúc làm mới, nhưng cần materialized view đã được populate và có ít nhất một unique index phù hợp bao phủ toàn bộ dòng; không thể chạy đồng thời nhiều refresh trên cùng một materialized view. Refresh vẫn phải tính lại nội dung theo truy vấn định nghĩa, nên có thể tiêu thụ đáng kể CPU, I/O và thời gian.

Materialized view phù hợp khi:

- Truy vấn nguồn nặng và được gọi nhiều lần.
- Dữ liệu có thể trễ theo một chu kỳ làm mới chấp nhận được.
- Có thể lập lịch refresh và giám sát thời gian hoàn tất.
- Có cơ chế xử lý lỗi refresh và xác định thời điểm dữ liệu mới nhất.

Nếu cần cập nhật từng thay đổi gần thời gian thực, bảng tổng hợp tăng dần hoặc pipeline CDC có thể phù hợp hơn, nhưng phức tạp hơn trong việc bảo đảm tính đúng đắn.

### 5.5. Read model và CQRS

Trong một số hệ thống, mô hình ghi và mô hình đọc có cấu trúc khác nhau:

- **Write model:** tối ưu cho quy tắc nghiệp vụ, transaction, ràng buộc và cập nhật nguồn sự thật.
- **Read model:** tổ chức dữ liệu theo màn hình, báo cáo hoặc truy vấn cụ thể; có thể gộp nhiều nguồn, lưu sẵn tổng hợp và được cập nhật bất đồng bộ.

Đây là một cách triển khai thường gặp trong kiến trúc CQRS (Command Query Responsibility Segregation). Nó không bắt buộc phải dùng hai loại database; hai mô hình có thể nằm trong cùng một hệ quản trị hoặc được phân tách thành các hệ thống khác nhau.

Read model giúp đường đọc đơn giản, nhưng phát sinh độ trễ đồng bộ, xử lý sự kiện trùng, thứ tự sự kiện, rebuild và giám sát. Chỉ nên dùng khi nhu cầu đọc và yêu cầu nghiệp vụ đủ rõ để biện minh cho chi phí vận hành.

## 6. Duy trì dữ liệu phi chuẩn hóa

Điểm khó nhất của phi chuẩn hóa không phải tạo thêm cột hay bảng, mà là bảo đảm chúng luôn được cập nhật đúng theo định nghĩa nghiệp vụ.

### 6.1. Xác định nguồn sự thật

Với mỗi thuộc tính lặp hoặc giá trị tổng hợp, hãy ghi rõ:

- Bảng hoặc sự kiện nào là nguồn dữ liệu chính thức.
- Bản sao là snapshot lịch sử hay bản sao cần phản ánh trạng thái hiện tại.
- Thay đổi nào làm bản sao phải cập nhật.
- Mức trễ tối đa chấp nhận được.
- Ai hoặc tiến trình nào chịu trách nhiệm sửa sai và rebuild.

Nếu không xác định được nguồn sự thật, nhiều nơi có thể cùng ghi vào một giá trị và tạo ra xung đột khó xử lý.

### 6.2. Cập nhật đồng bộ trong cùng transaction

Nếu bảng tổng hợp phải phản ánh ngay một thay đổi nghiệp vụ, có thể cập nhật nguồn và bảng tổng hợp trong cùng transaction. Ví dụ khi một đơn chuyển từ trạng thái chưa hoàn tất sang hoàn tất, ứng dụng cập nhật đơn và tổng hợp theo logic chuyển trạng thái.

Minh họa một thao tác cộng doanh thu vào một nhóm đã xác định:

```sql
INSERT INTO daily_region_sales
    (sales_date, region_id, order_count, revenue)
VALUES
    (DATE '2026-10-15', 7, 1, 125000.00)
ON CONFLICT (sales_date, region_id)
DO UPDATE SET
    order_count = daily_region_sales.order_count + EXCLUDED.order_count,
    revenue = daily_region_sales.revenue + EXCLUDED.revenue;
```

Đây chỉ là phần cập nhật số liệu tổng hợp. Trong hệ thống thực tế, chỉ được cộng khi đơn thực sự đi qua chuyển trạng thái đủ điều kiện và thao tác phải gắn với transaction cập nhật đơn. Nếu cùng một sự kiện được xử lý lại, phép cộng lặp sẽ làm sai số liệu. Cần cơ chế idempotency hoặc ghi nhận sự kiện đã áp dụng.

### 6.3. Xử lý chuyển trạng thái và điều chỉnh

Tổng hợp doanh thu không chỉ có thao tác cộng. Một đơn đã hoàn tất có thể bị hoàn tiền, hủy theo chính sách hoặc điều chỉnh giá trị. Nếu báo cáo chỉ tính đơn `COMPLETED`, khi trạng thái chuyển từ `COMPLETED` sang `CANCELLED`, hệ thống cần trừ phần đóng góp cũ khỏi nhóm tương ứng hoặc tính lại nhóm.

Một cách tư duy là tính chênh lệch:

\[
\Delta Aggregate = Contribution_{new} - Contribution_{old}
\]

Nếu trạng thái cũ không đủ điều kiện, contribution cũ bằng 0; nếu trạng thái mới không đủ điều kiện, contribution mới bằng 0. Với thay đổi khu vực hoặc ngày ghi nhận, cần trừ khỏi nhóm cũ và cộng vào nhóm mới. Quy tắc này phải bao phủ cập nhật, xóa, hoàn tiền và sửa dữ liệu lịch sử.

### 6.4. Cập nhật bất đồng bộ qua sự kiện hoặc CDC

Khi cập nhật read model qua hàng đợi hoặc CDC, transaction ghi nguồn có thể hoàn tất trước khi read model được cập nhật. Cách này giảm công việc đồng bộ trên đường giao dịch, nhưng tạo eventual consistency.

Các vấn đề cần thiết kế:

- **At-least-once delivery:** một sự kiện có thể được gửi lại; consumer phải idempotent.
- **Ordering:** các sự kiện của cùng một thực thể cần được xử lý theo thứ tự phù hợp hoặc có version để bỏ sự kiện cũ.
- **Atomicity giữa ghi nguồn và phát sự kiện:** transactional outbox giúp ghi thay đổi nghiệp vụ và sự kiện trong cùng transaction, sau đó tiến trình riêng phát sự kiện.
- **Retry và dead-letter:** lỗi tạm thời cần retry có giới hạn; lỗi không thể xử lý cần được lưu để điều tra.
- **Lag monitoring:** đo độ trễ từ commit nguồn tới khi read model cập nhật.
- **Rebuild/replay:** có thể tái tạo read model từ nguồn hoặc lịch sử sự kiện khi phát hiện sai lệch.

Không nên dùng cập nhật bất đồng bộ nếu nghiệp vụ yêu cầu số liệu đọc ngay sau commit phải phản ánh thay đổi mới nhất mà không có độ trễ. Hãy ghi rõ mức nhất quán mà API cam kết.

### 6.5. Tránh tranh chấp trên dòng tổng hợp nóng

Nếu hàng nghìn giao dịch cùng cập nhật một dòng `daily_region_sales` cho cùng ngày và khu vực, dòng đó có thể trở thành điểm nóng. Các transaction phải chờ khóa trên cùng bản ghi, làm tăng latency và giảm throughput.

Một số hướng xử lý có thể thử:

- Chia tổng hợp thành nhiều bucket hoặc shard theo khóa phụ rồi cộng khi đọc.
- Ghi sự kiện vào bảng append-only và tổng hợp theo lô.
- Gom nhiều thay đổi thành batch để giảm số lần cập nhật cùng dòng.
- Tách workload báo cáo khỏi transaction path nếu yêu cầu độ mới cho phép.
- Thiết kế lại khóa nhóm để phân tán cập nhật, sau đó kiểm tra chi phí tổng hợp.

Mỗi hướng đều có đánh đổi. Sharding summary giảm tranh chấp ghi nhưng làm truy vấn đọc phải cộng nhiều bucket; batch giảm số lần cập nhật nhưng tăng độ trễ dữ liệu.

## 7. So sánh chuẩn hóa và các mẫu phi chuẩn hóa

| Mẫu | Lợi ích đường đọc | Chi phí đường ghi/vận hành | Phù hợp khi |
|---|---|---|---|
| Mô hình chuẩn hóa | Dữ liệu nhất quán; đọc có thể cần join | Cập nhật thuộc tính chung thường ở một nơi; giao dịch có thể chạm nhiều bảng | Giao dịch nghiệp vụ, dữ liệu thay đổi thường xuyên |
| Snapshot trên bản ghi | Truy vấn lịch sử không cần suy ngược giá trị cũ | Tăng dung lượng; cần ghi đúng thời điểm và không đồng bộ nhầm | Hóa đơn, địa chỉ giao hàng, giá đã chốt |
| Sao chép thuộc tính hiện tại | Giảm một số join/filter | Phải đồng bộ khi nguồn thay đổi; dễ lỗi thời | Truy vấn nóng có lợi ích rõ và có chính sách cập nhật |
| Summary table | Báo cáo nhanh, ít tổng hợp lặp lại | Cập nhật tăng/giảm, idempotency, tranh chấp và rebuild | Dashboard hoặc báo cáo có mẫu truy vấn ổn định |
| Materialized view | Tái sử dụng kết quả truy vấn nặng | Refresh tốn tài nguyên và có độ trễ | Báo cáo chấp nhận refresh theo lịch |
| Read model/CQRS | Cấu trúc riêng theo màn hình hoặc use case | Pipeline, lag, retry, replay và vận hành phức tạp | Nhiều truy vấn đọc khác biệt, tải đọc lớn |

## 8. Chọn mô hình dựa trên workload

Không nên bắt đầu bằng câu hỏi “chuẩn hóa hay phi chuẩn hóa tốt hơn?”. Hãy bắt đầu bằng các câu hỏi về hành vi truy cập.

### 8.1. Đo đường đọc

Với từng truy vấn quan trọng, ghi nhận:

- Tần suất gọi và mức đồng thời.
- p50, p95, p99 và SLA.
- Số dòng đầu vào/đầu ra của từng node.
- Số phép join, sort, aggregate và lượng dữ liệu tạm.
- Buffer hit/read, I/O và CPU.
- Tỷ lệ dữ liệu được đọc lặp lại giữa các truy vấn.

Nếu truy vấn chậm do thiếu index hoặc thống kê sai, phi chuẩn hóa có thể không giải quyết đúng nguyên nhân. Nếu chi phí chủ yếu đến từ tổng hợp lịch sử lặp đi lặp lại, summary table hoặc materialized view có thể đem lại lợi ích rõ hơn.

### 8.2. Đo đường ghi

Ghi nhận:

- Số transaction/giây và tỷ lệ đọc/ghi.
- Số bảng và chỉ mục được cập nhật cho mỗi nghiệp vụ.
- WAL/redo sinh ra, IOPS và thời gian commit.
- Lock waits, deadlock và các dòng nóng.
- Tần suất cập nhật thuộc tính được sao chép.
- Chi phí batch, trigger, CDC hoặc refresh.

Nếu thêm bản sao khiến một giao dịch phải cập nhật nhiều bảng hoặc nhiều index hơn, độ trễ ghi có thể tăng. Cần đo dưới tải đồng thời chứ không chỉ chạy một câu SQL đơn lẻ.

### 8.3. Xác định yêu cầu nhất quán

Hỏi rõ:

- Đọc ngay sau commit có phải thấy dữ liệu mới không?
- Dashboard được phép trễ 5 giây, 1 phút hay 1 giờ?
- Số liệu lịch sử có được phép thay đổi khi hồ sơ nguồn thay đổi không?
- Có cần một snapshot nhất quán cho cả phiên báo cáo không?
- Khi pipeline lỗi, thời gian phục hồi và cách phát lại dữ liệu là gì?

Yêu cầu nhất quán quyết định mẫu phi chuẩn hóa nào có thể dùng. Không chọn read model bất đồng bộ nếu API đang cam kết đọc-your-writes mà chưa có cơ chế đọc từ nguồn hoặc chờ đồng bộ.

## 9. Ví dụ thực tế: dashboard doanh thu và API đặt hàng

Một hệ thống thương mại điện tử có hai workload:

| Workload | Đặc điểm | Mục tiêu |
|---|---|---|
| API đặt hàng | Nhiều transaction ngắn; tạo đơn, ghi dòng hàng, cập nhật tồn kho | Đúng dữ liệu, commit ổn định, ít tranh chấp |
| Dashboard doanh thu | Đọc lịch sử lớn, nhóm theo ngày/khu vực/sản phẩm; nhiều người xem cùng lúc | Phản hồi nhanh, dữ liệu có thể trễ một khoảng đã thống nhất |

Mô hình giao dịch chuẩn hóa giúp cập nhật đơn hàng và sản phẩm nhất quán. Dashboard chạy truy vấn tổng hợp lớn trên các bảng giao dịch có thể tranh chấp I/O và CPU với API đặt hàng.

Một kiến trúc có thể giữ mô hình chuẩn hóa làm nguồn sự thật và xây bảng tổng hợp theo ngày/khu vực cho dashboard. Pipeline cập nhật summary có thể chạy theo batch mỗi phút hoặc qua sự kiện. Nếu chọn batch, dashboard phải hiển thị thời điểm dữ liệu được làm mới. Nếu chọn sự kiện, cần theo dõi lag và xử lý sự kiện lặp.

Trước khi triển khai, đo:

1. p95/p99 và throughput của API đặt hàng khi dashboard chạy.
2. Thời gian truy vấn dashboard, số dòng quét và temp I/O.
3. CPU, memory, I/O và lock waits trên cơ sở dữ liệu.
4. Chi phí ghi bổ sung vào summary hoặc pipeline.
5. Độ trễ và độ chính xác của số liệu dashboard.

Sau khi triển khai, chạy lại cùng kịch bản hỗn hợp. Nếu dashboard nhanh hơn nhưng API đặt hàng chậm hơn do cập nhật summary trên một dòng nóng, thiết kế cần được điều chỉnh, ví dụ chia bucket hoặc cập nhật theo batch. Nếu số liệu dashboard trễ vượt cam kết, cần thay đổi tần suất hoặc cơ chế đồng bộ.

## 10. Quy trình quyết định chuẩn hóa hay phi chuẩn hóa

**Bước 1 — Xác định sự thật nghiệp vụ.** Liệt kê thực thể, thuộc tính, khóa, quan hệ và vòng đời dữ liệu. Phân biệt thuộc tính hiện tại với snapshot lịch sử.

**Bước 2 — Mô hình hóa và chuẩn hóa dữ liệu lõi.** Đặt thuộc tính ở quan hệ có trách nhiệm quản lý; xác định khóa chính, khóa ngoại, unique constraint và các ràng buộc cần thiết.

**Bước 3 — Thu thập workload.** Chọn truy vấn đọc và transaction ghi quan trọng; đo tần suất, đồng thời, độ trễ, số dòng, join, I/O, WAL và lock waits.

**Bước 4 — Tìm đúng nút thắt.** Đọc kế hoạch thực thi, kiểm tra index, thống kê, filter pushdown, số dòng ước lượng/thực tế, sort/hash spill và tài nguyên hệ thống.

**Bước 5 — Đề xuất mẫu phi chuẩn hóa tối thiểu.** Chọn snapshot, summary table, materialized view hoặc read model theo nhu cầu; chỉ lưu dữ liệu cần cho truy vấn mục tiêu.

**Bước 6 — Định nghĩa nguồn sự thật và cách duy trì.** Chọn cập nhật đồng bộ, trigger, batch, outbox/CDC hoặc refresh; xác định idempotency, thứ tự sự kiện, lag, retry và rebuild.

**Bước 7 — Kiểm tra nhất quán.** So sánh giá trị phi chuẩn hóa với truy vấn tính từ nguồn chuẩn hóa; kiểm tra insert, update, delete, đổi trạng thái, hoàn tiền và xử lý lặp.

**Bước 8 — Benchmark tải hỗn hợp.** Chạy đồng thời workload đọc và ghi. Đo latency, throughput, CPU, memory, I/O, WAL, lock waits, storage và độ trễ đồng bộ.

**Bước 9 — Quyết định và giám sát.** Chỉ giữ thay đổi khi cải thiện SLA tổng thể, dữ liệu đúng theo cam kết và chi phí vận hành chấp nhận được. Thiết lập cảnh báo cho lag, sai lệch summary và lỗi refresh.

## 11. Những nhầm lẫn thường gặp

- **“Chuẩn hóa luôn chậm vì phải JOIN.”** Join có thể rẻ với index và cardinality phù hợp; cần xem kế hoạch trước khi thay mô hình.
- **“Phi chuẩn hóa luôn nhanh hơn.”** Đường đọc có thể ngắn hơn nhưng đường ghi, dung lượng, cache footprint và đồng bộ có thể đắt hơn.
- **“Mọi dữ liệu lặp đều là dư thừa.”** Giá đã chốt, địa chỉ giao hàng hoặc thuế suất tại thời điểm giao dịch là snapshot nghiệp vụ có ý nghĩa.
- **“Trigger tự giải quyết tính nhất quán.”** Trigger có thể cập nhật đồng bộ nhưng vẫn cần xử lý khóa, lỗi, logic chuyển trạng thái và tác động tới transaction.
- **“Bảng tổng hợp chỉ cần cộng khi có đơn mới.”** Hủy, hoàn tiền, sửa đơn, đổi khu vực và sự kiện lặp cũng phải được xử lý.
- **“Materialized view tự cập nhật khi bảng nguồn đổi.”** PostgreSQL yêu cầu refresh; thời điểm và chi phí refresh cần được thiết kế.
- **“Eventual consistency không ảnh hưởng người dùng.”** Độ trễ phải nằm trong cam kết sản phẩm và được quan sát.
- **“Tăng thêm một cột sao chép không có chi phí.”** Mỗi lần cập nhật có thể tăng WAL, index maintenance, row width và tranh chấp.
- **“Chỉ benchmark truy vấn đọc là đủ.”** Phi chuẩn hóa tác động đến transaction ghi và workload đồng thời; cần benchmark cả hai.
- **“Read model là nguồn sự thật thứ hai.”** Nguồn sự thật phải được xác định rõ; read model có thể được tái tạo từ nguồn hoặc sự kiện.

## 12. Checklist đánh giá mô hình dữ liệu theo đường đọc ghi

- [ ] Đã xác định nguồn sự thật cho từng thực thể và thuộc tính.
- [ ] Đã phân biệt dữ liệu hiện tại với snapshot lịch sử.
- [ ] Đã ghi nhận các bất thường chèn, cập nhật và xóa do dữ liệu lặp.
- [ ] Đã đo truy vấn đọc và transaction ghi quan trọng bằng workload đại diện.
- [ ] Đã kiểm tra kế hoạch, cardinality, index, thống kê và I/O trước khi phi chuẩn hóa.
- [ ] Đã chọn mẫu phi chuẩn hóa đúng nhu cầu: snapshot, summary, materialized view hoặc read model.
- [ ] Đã định nghĩa cách cập nhật, idempotency, xử lý lỗi và rebuild.
- [ ] Đã xác định mức trễ và yêu cầu nhất quán mà người dùng chấp nhận.
- [ ] Đã đánh giá lock contention, dòng nóng, WAL, dung lượng và chi phí bảo trì.
- [ ] Đã kiểm thử insert, update, delete, chuyển trạng thái và sự kiện lặp.
- [ ] Đã so sánh số liệu phi chuẩn hóa với nguồn chuẩn hóa để phát hiện sai lệch.
- [ ] Đã benchmark tải đọc/ghi đồng thời và đo p95/p99, throughput cùng tài nguyên.

## Kết luận

Chuẩn hóa giúp đặt dữ liệu ở đúng nơi, giảm lặp và bảo vệ tính nhất quán khi ghi. Phi chuẩn hóa chủ động lưu snapshot, bản sao hoặc kết quả tổng hợp để rút ngắn đường đọc. Lựa chọn phù hợp phụ thuộc vào workload, SLA, mức đồng thời, chi phí join/tổng hợp và yêu cầu nhất quán.

Hãy giữ mô hình nguồn sự thật rõ ràng, đo đúng nút thắt trước khi thay đổi và chọn mẫu phi chuẩn hóa nhỏ nhất giải quyết được truy vấn mục tiêu. Thiết kế cách duy trì dữ liệu lặp ngay từ đầu, bao gồm cập nhật, xóa, chuyển trạng thái, sự kiện lặp, độ trễ và rebuild. Chỉ xác nhận thành công khi benchmark tải đọc/ghi cho thấy hiệu năng tổng thể tốt hơn và dữ liệu vẫn đúng theo cam kết nghiệp vụ.
