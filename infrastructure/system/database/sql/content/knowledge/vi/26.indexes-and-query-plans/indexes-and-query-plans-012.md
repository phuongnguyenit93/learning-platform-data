# Ranh giới giữa viết SQL hiệu quả và quản trị hiệu năng chuyên sâu

Khi một truy vấn SQL chạy chậm, phản ứng đầu tiên thường là “thêm index”, “viết lại `JOIN`” hoặc “tăng cấu hình database”. Nhưng ba hành động này thuộc **ba lớp vấn đề khác nhau**:

- **Viết SQL hiệu quả**: diễn đạt đúng nghiệp vụ, truy vấn đúng lượng dữ liệu, tránh nhân bản hàng, dùng điều kiện lọc và thứ tự có thể tối ưu được, chọn hình dạng kết quả phù hợp.
- **Hiểu chỉ mục và kế hoạch thực thi**: biết database có những con đường truy cập nào, đọc được các dấu hiệu cơ bản từ `EXPLAIN`, giải thích tại sao một truy vấn có thể đọc quá nhiều hàng hoặc sắp xếp tốn kém.
- **Quản trị hiệu năng chuyên sâu**: điều tra toàn bộ tải, độ lệch thống kê, tranh chấp khóa, I/O, bộ nhớ, WAL, vacuum/bloat, replication, cấu hình máy chủ, phân vùng, cạnh tranh tài nguyên, tính ổn định kế hoạch và chiến lược vận hành.

Bài học thuộc **Database SQL → Chỉ mục và kế hoạch → Ranh giới giữa viết SQL hiệu quả và quản trị hiệu năng chuyên sâu**. Mục tiêu là giúp người viết SQL biết **mình cần làm gì trước**, đọc dấu hiệu nào để quyết định hướng cải thiện, **khi nào cần phối hợp DBA/SRE**, và **khi nào không nên tự động can thiệp vào database đang phục vụ nhiều người dùng**.

Ví dụ chính sử dụng **PostgreSQL**. Các hệ như MySQL, SQL Server, Oracle và SQLite có tên công cụ, chỉ mục và cơ chế optimizer khác nhau; các nguyên tắc chẩn đoán có thể áp dụng rộng, nhưng **không sao chép nguyên cú pháp hoặc ngưỡng hiệu năng giữa các sản phẩm**.

> Một câu SQL nhanh nhưng trả kết quả sai **không phải truy vấn được tối ưu thành công**. Mọi thay đổi hiệu năng trước tiên phải giữ đúng ngữ nghĩa, quyền truy cập, tính nhất quán và hợp đồng dữ liệu của ứng dụng.

---

## 1. Hiệu năng SQL không chỉ là thời gian của một câu SELECT

Một request ứng dụng thường trải qua nhiều bước:

```text
Người dùng
   │
   ▼
API / ORM / business logic
   │  thời gian xây tham số, chờ connection
   ▼
Connection pool
   │  thời gian đợi kết nối, transaction đang mở
   ▼
Database
   ├─ parse / plan
   ├─ chờ khóa / chờ I/O / chờ tài nguyên
   ├─ đọc bảng hoặc index
   ├─ JOIN / FILTER / SORT / AGGREGATE
   └─ gửi rows
   │
   ▼
Ứng dụng đọc rows, chuyển object, xử lý kết quả
   │
   ▼
Serialize JSON / truyền mạng / hiển thị
```

Nếu API mất 1.500 ms còn `EXPLAIN ANALYZE` báo database thực thi truy vấn chỉ khoảng 30 ms trong môi trường thử, không thể kết luận chỉ cần thêm một index sẽ sửa toàn bộ 1.500 ms.

Ngược lại, một câu SQL chạy 5 ms trong laptop với 100 bản ghi có thể chạy nhiều giây trên dữ liệu thật gồm hàng triệu bản ghi hoặc dưới tải đồng thời.

### Ba cách hiểu “chạy chậm”

| Vấn đề | Ví dụ | Lớp xử lý thường phù hợp |
| --- | --- | --- |
| **Truy vấn làm việc dư thừa** | Lấy toàn bộ lịch sử đơn rồi lọc 10 đơn trong Java | Sửa SQL/ứng dụng |
| **Đường truy cập không phù hợp** | Lọc khách hàng theo khóa thường dùng nhưng chưa có index phù hợp | Phân tích kế hoạch + thiết kế index, review DDL |
| **Môi trường vận hành nghẽn** | Nhiều câu SQL bình thường cùng chờ I/O hoặc lock | Điều tra workload, cấu hình, transaction, DBA/SRE |

Không nên đoán nguyên nhân chỉ từ triệu chứng “API chậm”.

## 2. Mô hình tư duy: correctness → workload → plan → system

Một trình tự chẩn đoán hữu ích:

```text
1. NGỮ NGHĨA
   Truy vấn trả đúng những hàng/cột/đơn vị dữ liệu cần thiết chưa?
                     │
                     ▼
2. WORKLOAD
   Chậm ở đâu, bao lâu, với tham số nào, bao nhiêu lần mỗi giây?
                     │
                     ▼
3. KẾ HOẠCH
   Optimizer dự đoán số hàng thế nào, chọn scan/join/sort ra sao?
                     │
                     ▼
4. HỆ THỐNG
   Chờ khóa, I/O, CPU, bộ nhớ, thống kê, bloat, replication?
                     │
                     ▼
5. THỬ NGHIỆM VÀ TRIỂN KHAI
   Cải thiện có lặp lại được và an toàn cho các truy vấn khác không?
```

**Nguyên tắc:** bắt đầu từ điều bạn có thể mô tả và đo được; chỉ chuyển sang quản trị hệ thống khi có dấu hiệu vượt khỏi hình dạng truy vấn hoặc phạm vi một câu SQL.

### Không bắt buộc mọi vấn đề phải đi hết năm bước

Nếu câu truy vấn đang `SELECT *` trả 500.000 hàng trong khi màn hình chỉ cần 20 hàng, có thể sửa ngay sau khi xác nhận hợp đồng API. Không cần thay cấu hình shared buffers.

Nếu mọi truy vấn đột nhiên chậm cùng thời điểm, việc mổ xẻ một câu `SELECT` trước khi kiểm tra sự cố I/O hoặc lock toàn hệ có thể lãng phí thời gian.

---

## 3. Hai phạm vi trách nhiệm: câu SQL và dịch vụ database

| Phạm vi | Người viết SQL thường chịu trách nhiệm trực tiếp | Cần phối hợp DBA/SRE/owner hệ thống |
| --- | --- | --- |
| Đúng khóa JOIN, đúng lọc, đúng GROUP BY | Có | Khi phụ thuộc thiết kế schema/phân quyền |
| Lấy đúng cột, đúng số dòng, đúng thứ tự | Có | Thường không cần |
| Tránh N+1 query ở ORM | Có | Có thể cần hỗ trợ đo workload |
| Đọc `EXPLAIN` cơ bản, kiểm tra ước lượng | Có thể thực hiện trong môi trường phù hợp | Cần hỗ trợ khi cần thống kê hệ thống hoặc quyền |
| Đề xuất index theo workload | Có | **Review trước khi DDL trên production** |
| Chạy `CREATE INDEX CONCURRENTLY` trên bảng lớn | Không nên làm tùy hứng | Có kế hoạch triển khai, theo dõi và rollback |
| Điều chỉnh autovacuum, checkpoint, WAL, memory | Không phải biện pháp mặc định ở cấp SQL | Chủ yếu DBA/SRE/Platform |
| Phân tích bloat, I/O saturation, lock chain | Có thể cung cấp bằng chứng | Chuyên sâu, tác động đa workload |
| Phân vùng bảng hoặc migration schema lớn | Tham gia yêu cầu truy vấn | Cần thiết kế và triển khai phối hợp |
| Chọn SLO và cách đo p95/p99 | Cùng product/API owner | Cần observability toàn hệ |
| Thay đổi isolation/transaction policy | Phải hiểu ngữ nghĩa nghiệp vụ | Cần đánh giá concurrency/ràng buộc |

Ranh giới này **không phải ranh giới chức danh cứng**. Một lập trình viên có thể rất giỏi database, và DBA có thể sửa SQL. Điểm phân biệt là **phạm vi tác động**: một thay đổi ảnh hưởng riêng truy vấn của bạn hay có thể làm biến đổi cả hệ thống dùng chung?

---

## 4. Đúng ngữ nghĩa là điều kiện trước khi tối ưu

Giả sử API cần tổng doanh thu đã thanh toán của mỗi khách hàng. Một câu JOIN có thể nhân bản dữ liệu nếu nối sai mức:

```sql
-- CÓ THỂ SAI: nếu một đơn có nhiều dòng chi tiết,
-- tổng giá trị order sẽ bị lặp theo số dòng item.
SELECT
    o.customer_id,
    SUM(o.total_amount) AS revenue
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id
WHERE o.status = 'PAID'
GROUP BY o.customer_id;
```

Nếu đơn 101 có ba item, `o.total_amount` bị tính ba lần trong tổng.

Một người thấy kết quả quá lớn có thể thử:

```sql
SUM(DISTINCT o.total_amount)
```

nhưng đây cũng có thể sai: hai đơn thật cùng trị giá 100 sẽ chỉ được cộng một lần.

### Cách tiếp cận đúng

1. Xác định **grain**: một hàng `orders` đại diện **một đơn**, một hàng `order_items` đại diện **một dòng hàng**.
2. Nếu đã có `total_amount` trên bảng đơn và muốn tổng theo khách, dùng chính `orders`, không JOIN item nếu không cần.
3. Nếu cần tính lại từ item, tổng hợp ở mức `order_id` trước khi tổng theo khách.
4. Kiểm tra các đơn không có item và quy tắc hoàn tiền, VAT, chiết khấu.

Chỉ sau đó mới đo hiệu năng. **Truy vấn sai có thể chạy nhanh hơn rất nhiều vì nó xử lý thiếu dữ liệu cần thiết.**

## 5. Bộ dữ liệu thực hành PostgreSQL

Những ví dụ dưới đây dùng bảng nhỏ để người đọc **hiểu ngữ nghĩa và kế hoạch**. Trên bảng nhỏ, PostgreSQL hoàn toàn có thể chọn `Seq Scan` dù đã có index; đó **không phải lỗi**.

Hãy dùng một database/schema thử nghiệm riêng. Các câu DDL và DML sau **không dành cho production**.

### 5.1. Bảng khách hàng

```sql
CREATE TABLE lab_customers_333 (
    customer_id INTEGER PRIMARY KEY,
    email       TEXT NOT NULL UNIQUE,
    customer_name TEXT NOT NULL,
    active      BOOLEAN NOT NULL DEFAULT TRUE
);

INSERT INTO lab_customers_333 (
    customer_id, email, customer_name, active
)
VALUES
    (1, 'an@example.test',   'An',   TRUE),
    (2, 'binh@example.test', 'Bình', TRUE),
    (3, 'chi@example.test',  'Chi',  FALSE),
    (4, 'dung@example.test', 'Dũng', TRUE);
```

### 5.2. Bảng đơn hàng

```sql
CREATE TABLE lab_orders_333 (
    order_id     INTEGER PRIMARY KEY,
    customer_id  INTEGER NOT NULL
                 REFERENCES lab_customers_333(customer_id),
    placed_at    TIMESTAMPTZ NOT NULL,
    status       TEXT NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL
);

INSERT INTO lab_orders_333 (
    order_id, customer_id, placed_at, status, total_amount
)
VALUES
    (101, 1, TIMESTAMPTZ '2026-07-01 09:00:00+00', 'PAID',      100.00),
    (102, 1, TIMESTAMPTZ '2026-07-02 10:00:00+00', 'PAID',      180.00),
    (103, 1, TIMESTAMPTZ '2026-07-02 10:00:00+00', 'DRAFT',      50.00),
    (104, 2, TIMESTAMPTZ '2026-07-02 11:00:00+00', 'PAID',       80.00),
    (105, 2, TIMESTAMPTZ '2026-07-03 08:00:00+00', 'REFUNDED',   90.00),
    (106, 2, TIMESTAMPTZ '2026-07-03 09:00:00+00', 'PAID',       40.00),
    (107, 3, TIMESTAMPTZ '2026-07-03 10:00:00+00', 'PAID',      120.00),
    (108, 3, TIMESTAMPTZ '2026-07-04 10:00:00+00', 'DRAFT',      75.00),
    (109, 1, TIMESTAMPTZ '2026-07-04 11:00:00+00', 'PAID',       60.00),
    (110, 4, TIMESTAMPTZ '2026-07-04 12:00:00+00', 'PAID',       30.00),
    (111, 1, TIMESTAMPTZ '2026-07-04 12:00:00+00', 'PAID',       25.00),
    (112, 4, TIMESTAMPTZ '2026-07-05 13:00:00+00', 'CANCELLED',  20.00);

SELECT order_id, customer_id, placed_at, status, total_amount
FROM lab_orders_333
ORDER BY order_id;
```

Có **12 đơn** với nhiều trạng thái. Khách 1 có các đơn 101,102,103,109,111; trong đó **103** là `DRAFT` và không thuộc doanh thu đã thanh toán.

### 5.3. Bảng chi tiết đơn

```sql
CREATE TABLE lab_order_items_333 (
    order_id   INTEGER NOT NULL
               REFERENCES lab_orders_333(order_id),
    line_no    INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity   INTEGER NOT NULL,
    unit_price NUMERIC(12, 2) NOT NULL,
    PRIMARY KEY (order_id, line_no)
);

INSERT INTO lab_order_items_333 (
    order_id, line_no, product_id, quantity, unit_price
)
VALUES
    (101, 1, 501, 1,  60.00),
    (101, 2, 502, 2,  20.00),
    (102, 1, 503, 1, 180.00),
    (103, 1, 501, 1,  50.00),
    (104, 1, 504, 1,  80.00),
    (105, 1, 505, 1,  90.00),
    (106, 1, 502, 2,  20.00),
    (107, 1, 506, 1, 120.00),
    (108, 1, 507, 1,  75.00),
    (109, 1, 501, 1,  60.00),
    (110, 1, 502, 1,  30.00),
    (111, 1, 504, 1,  25.00),
    (112, 1, 502, 1,  20.00);
```

Đơn 101 có hai dòng chi tiết; những đơn khác trong mẫu có một dòng. Ví dụ cố tình để `orders.total_amount` là giá trị báo cáo của đơn, còn `items` minh họa rủi ro **nhân bản hàng**.

### 5.4. Các index đã tồn tại

Ngay khi tạo `PRIMARY KEY` hoặc `UNIQUE`, PostgreSQL tạo các index phục vụ ràng buộc tương ứng:

- `lab_customers_333(customer_id)`: primary key.
- `lab_customers_333(email)`: unique index.
- `lab_orders_333(order_id)`: primary key.
- `lab_order_items_333(order_id, line_no)`: primary key ghép.

**Đừng tạo lại cùng index chỉ vì không nhớ nó đã được tạo tự động.** Dù index tồn tại, nó không nhất thiết là index phù hợp cho câu lọc/đặt thứ tự mà bạn đang nghiên cứu.

---

## 6. Tối ưu cấp SQL đầu tiên: chỉ lấy dữ liệu thật sự cần

Truy vấn ứng dụng cần hiển thị mã đơn, ngày và số tiền, nhưng viết:

```sql
SELECT *
FROM lab_orders_333
WHERE customer_id = 1;
```

Nếu bảng thực chứa thêm JSON lớn, địa chỉ giao hàng, ghi chú và nhiều cột, `SELECT *` có thể:

- Truyền nhiều byte hơn từ database tới ứng dụng.
- Tốn xử lý serialize/deserialze không cần thiết.
- Tăng CPU/memory ở ORM và network.
- Khiến một số kế hoạch index-only không khả thi vì cần lấy các cột ngoài index.
- Làm hợp đồng API dễ bị thay đổi khi schema thêm cột.

Mẫu rõ ràng hơn:

```sql
SELECT order_id, placed_at, total_amount
FROM lab_orders_333
WHERE customer_id = 1
ORDER BY placed_at DESC, order_id DESC
LIMIT 20;
```

Kết quả chỉ có cột màn hình cần và tối đa 20 đơn.

### Nhưng SELECT * không phải lúc nào cũng sai

Trong thao tác kiểm tra dữ liệu nhỏ, hoặc API thật sự cần mọi cột, `SELECT *` có thể hợp lý. Vấn đề là **bất cân xứng giữa nhu cầu và lượng dữ liệu lấy ra**, không phải dấu sao tự nó khiến query chậm.

### LIMIT không thay thế ORDER BY

```sql
SELECT order_id FROM lab_orders_333 LIMIT 5;
```

không định nghĩa **năm đơn nào**. Database có thể trả các hàng khác khi kế hoạch truy cập thay đổi.

Muốn “5 đơn mới nhất”, phải chỉ rõ:

```sql
SELECT order_id, placed_at
FROM lab_orders_333
ORDER BY placed_at DESC, order_id DESC
LIMIT 5;
```

Cột `order_id` phá hòa khi nhiều đơn có cùng `placed_at`, giúp thứ tự có tính xác định.

---

## 7. Predicate có thể dùng index: tránh bọc cột một cách vô ý

Một sai lầm phổ biến là biến cột ngày thành chuỗi hoặc ngày rời rồi so sánh:

```sql
-- PostgreSQL: dễ hiểu nhưng có thể khó tận dụng
-- index B-tree trên placed_at cho khoảng thời gian.
SELECT order_id
FROM lab_orders_333
WHERE (placed_at AT TIME ZONE 'UTC')::DATE
      = DATE '2026-07-02';
```

Biểu thức áp dụng phép biến đổi lên **giá trị cột** của từng hàng. Một index B-tree thông thường trên `placed_at` có thể không trực tiếp cung cấp tìm kiếm theo điều kiện biểu thức đã biến đổi, trừ khi planner có cách khác hoặc có index biểu thức phù hợp.

Viết theo **khoảng nửa mở** (*half-open range*) thường rõ ràng hơn:

```sql
SELECT order_id
FROM lab_orders_333
WHERE placed_at >= TIMESTAMPTZ '2026-07-02 00:00:00+00'
  AND placed_at <  TIMESTAMPTZ '2026-07-03 00:00:00+00';
```

Cách này có nhiều ưu điểm:

- Phù hợp với tìm kiếm theo khoảng trên B-tree `placed_at`.
- Không phụ thuộc số chữ số phần mili giây/micro giây cuối ngày.
- Không cần viết `23:59:59.999...` dễ thiếu phần lẻ giây.
- Tách rõ ý nghĩa “từ đầu ngày tới trước đầu ngày kế tiếp”.

### SARGability là gì?

Trong thực hành SQL, một predicate được gọi là **sargable** khi hình dạng điều kiện cho phép optimizer dùng cấu trúc tìm kiếm/index phù hợp, thay vì bắt buộc tính biểu thức cho quá nhiều hàng.

Tuy nhiên:

- Sargable **không bảo đảm** optimizer sẽ chọn index; nó còn xét kích thước bảng, tỷ lệ hàng khớp, chi phí I/O và độ tin cậy thống kê.
- Không sargable với index A **không có nghĩa** không thể tối ưu bằng **expression index** hoặc index loại khác.
- Việc rewrite phải giữ đúng **ngữ nghĩa thời gian và NULL**, không chỉ đổi cú pháp.

### Múi giờ là một phần ngữ nghĩa

Nếu báo cáo lấy **ngày Việt Nam** thay vì UTC, phạm vi phải xây dựng theo múi giờ Việt Nam rồi chuyển sang instant tương ứng. Không được tự thay `'2026-07-02 00:00:00+00'` thành giờ địa phương mà quên độ lệch múi giờ.

Với các múi giờ có chuyển đổi giờ mùa hè, một ngày địa phương có thể không đúng 24 giờ. Cách an toàn là xác định **hai mốc nửa đêm liên tiếp theo múi giờ nghiệp vụ**, không tùy tiện cộng chính xác 86.400 giây ở mọi nơi.

## 8. Biến đổi kiểu và hàm trên cột khóa lọc

Một số điều kiện có thể khiến index thông thường khó phát huy tác dụng.

### 8.1. Ép cột số thành chuỗi

```sql
-- Ví dụ không lý tưởng nếu customer_id là INTEGER:
WHERE customer_id::TEXT = '101'
```

Thay bằng so sánh theo **kiểu gốc**:

```sql
WHERE customer_id = 101
```

Nếu ứng dụng truyền `customer_id` qua JDBC, bind tham số **đúng kiểu số** thay vì biến cột thành chuỗi để so khớp với input.

### 8.2. So sánh email không phân biệt hoa/thường

```sql
SELECT customer_id
FROM lab_customers_333
WHERE LOWER(email) = LOWER('An@Example.Test');
```

Truy vấn này có ý nghĩa khác `email = 'An@Example.Test'` khi cần so khớp không phân biệt hoa/thường. Để tối ưu trong PostgreSQL, có thể cân nhắc **expression index**:

```sql
-- Chỉ chạy trong database thử nghiệm.
CREATE INDEX lab_customers_333_email_lower_idx
ON lab_customers_333 (LOWER(email));
```

Nhưng cần lưu ý:

- Đây là index cho **biểu thức cụ thể**, không biến mọi hàm trên `email` thành tìm kiếm index.
- Dù tạo index, planner có thể chọn `Seq Scan` vì bảng quá nhỏ.
- Chỉ mục bổ sung có chi phí ghi và dung lượng.
- Nếu nghiệp vụ muốn email duy nhất không phân biệt hoa/thường, cần thiết kế **ràng buộc duy nhất/chuẩn hóa/collation** phù hợp, không chỉ tạo một index không unique cho truy vấn.

### 8.3. Tìm chuỗi chứa từ bất kỳ

```sql
WHERE customer_name ILIKE '%an%'
```

Một B-tree thông thường không phải lúc nào phù hợp cho tìm kiếm chứa chuỗi bất kỳ với dấu `%` ở đầu. PostgreSQL có phương án như `pg_trgm` và GIN/GiST index cho một số dạng tìm kiếm, nếu extension và yêu cầu hệ thống cho phép.

Đó đã là **đề xuất thay đổi thiết kế vật lý**, cần cân nhắc độ chọn lọc, chi phí ghi, ngôn ngữ tìm kiếm và quyền triển khai. Không tự tạo extension/index trên production chỉ vì một câu `ILIKE` chậm.

---

## 9. JOIN đúng quan hệ và tránh nhân bản hàng

Một nguyên nhân của query chậm là kết quả JOIN lớn hơn đáng kể so với nhu cầu.

### Câu JOIN làm sai tổng doanh thu

```sql
SELECT c.customer_id,
       SUM(o.total_amount) AS paid_revenue
FROM lab_customers_333 AS c
JOIN lab_orders_333 AS o
  ON o.customer_id = c.customer_id
JOIN lab_order_items_333 AS i
  ON i.order_id = o.order_id
WHERE o.status = 'PAID'
GROUP BY c.customer_id
ORDER BY c.customer_id;
```

Đơn 101 của khách 1 có hai item, nên `o.total_amount = 100` được nhân đôi. Kết quả doanh thu khách 1 **không đúng**.

### Viết lại theo đúng grain

Nếu doanh thu là tổng của `orders.total_amount`:

```sql
SELECT
    o.customer_id,
    SUM(o.total_amount) AS paid_revenue
FROM lab_orders_333 AS o
WHERE o.status = 'PAID'
GROUP BY o.customer_id
ORDER BY o.customer_id;
```

Kết quả:

| customer_id | paid_revenue |
| ---: | ---: |
| 1 | 365.00 |
| 2 | 120.00 |
| 3 | 120.00 |
| 4 | 30.00 |

Khách 1: `100 + 180 + 60 + 25 = 365`. Khách 2: `80 + 40 = 120`. Chỉ những đơn `PAID` được tính.

### Nếu cần tên khách hàng

```sql
SELECT c.customer_id,
       c.customer_name,
       x.paid_revenue
FROM (
    SELECT customer_id,
           SUM(total_amount) AS paid_revenue
    FROM lab_orders_333
    WHERE status = 'PAID'
    GROUP BY customer_id
) AS x
JOIN lab_customers_333 AS c
  ON c.customer_id = x.customer_id
ORDER BY c.customer_id;
```

Bước tổng hợp theo khách tạo tối đa một hàng mỗi `customer_id` rồi mới JOIN sang bảng khách hàng. Trong trường hợp này, cách viết dễ kiểm soát grain và hạn chế nhân bản kết quả.

**Đừng giả định “JOIN luôn chậm hơn subquery” hoặc ngược lại.** Optimizer có thể biến đổi các biểu thức tương đương. Lợi ích đầu tiên của ví dụ là **ngữ nghĩa đúng, tập hàng trung gian có mục đích rõ**.

## 10. EXISTS khi chỉ cần biết có bản ghi liên quan

Giả sử muốn tìm khách hàng **có ít nhất một đơn PAID**.

Một cách không lý tưởng:

```sql
SELECT DISTINCT c.customer_id, c.customer_name
FROM lab_customers_333 AS c
JOIN lab_orders_333 AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

Nó tạo các hàng JOIN theo đơn, rồi cần loại trùng khách.

Cách diễn đạt đúng nhu cầu “tồn tại ít nhất một”:

```sql
SELECT
    c.customer_id,
    c.customer_name
FROM lab_customers_333 AS c
WHERE EXISTS (
    SELECT 1
    FROM lab_orders_333 AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
```

Đây là mẫu **semi-join về mặt ý nghĩa**: chỉ cần biết có nguồn khớp, không cần sinh một hàng cho mọi đơn.

### EXISTS so với COUNT(*) > 0

```sql
WHERE (
    SELECT COUNT(*)
    FROM lab_orders_333 AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
) > 0
```

có thể cùng ngữ nghĩa tồn tại, nhưng diễn đạt ý định đếm hơn là kiểm tra tồn tại. Một số kế hoạch `EXISTS` có thể dừng khi tìm thấy hàng phù hợp.

Tuy vậy, đừng khẳng định `EXISTS` **luôn** nhanh hơn `COUNT(*)`: cần xem optimizer, index, thống kê và kế hoạch thực tế.

### Không dùng DISTINCT để chữa JOIN không đúng

Nếu dùng `DISTINCT` để xóa bản sao sau một JOIN nhầm quan hệ, bạn có thể:

- Che dấu lỗi khóa.
- Tốn thêm sort/hash để loại trùng.
- Vẫn giữ tổng hợp sai nếu SUM đã cộng trùng.

Hãy xác định **tại sao mỗi hàng xuất hiện** trước khi thêm `DISTINCT`.

---

## 11. Lọc sớm, nhưng không phá ngữ nghĩa OUTER JOIN

Một ý tưởng phổ biến là đưa điều kiện lọc xuống càng gần nguồn càng tốt. Optimizer thường có thể tự đẩy điều kiện thích hợp (*predicate pushdown*), nhưng **không phải mọi vị trí WHERE đều tương đương** khi có `LEFT JOIN`.

### Giữ mọi khách, kể cả người không có đơn PAID

```sql
SELECT
    c.customer_id,
    c.customer_name,
    COUNT(o.order_id) AS paid_orders
FROM lab_customers_333 AS c
LEFT JOIN lab_orders_333 AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Điều kiện `o.status = 'PAID'` ở `ON` giúp giữ cả khách **không có đơn PAID**, với `COUNT(o.order_id)=0`.

### Đặt điều kiện ở WHERE đổi kết quả

```sql
SELECT c.customer_id, COUNT(o.order_id)
FROM lab_customers_333 AS c
LEFT JOIN lab_orders_333 AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
GROUP BY c.customer_id;
```

Hàng không có đơn khớp tạo `o.status = NULL` sau LEFT JOIN và bị `WHERE` loại đi. Truy vấn trở nên tương tự INNER JOIN về tập khách, trái yêu cầu “giữ mọi khách”.

**Không tối ưu bằng cách đẩy lọc mà làm thay đổi quan hệ trái/phải của OUTER JOIN.**

## 12. GROUP BY, pre-aggregation và chi phí dữ liệu trung gian

Một truy vấn phân tích cần trả doanh thu theo tháng cho từng khách.

Có thể viết:

```sql
SELECT
    customer_id,
    DATE_TRUNC('month', placed_at AT TIME ZONE 'UTC')::DATE
        AS month_start,
    SUM(total_amount) AS total_paid
FROM lab_orders_333
WHERE status = 'PAID'
GROUP BY
    customer_id,
    DATE_TRUNC('month', placed_at AT TIME ZONE 'UTC')::DATE
ORDER BY customer_id, month_start;
```

Trên dữ liệu lớn, việc GROUP BY tạo hash/sort có thể tốn bộ nhớ hoặc spill ra đĩa. Nhưng điều đó không chứng minh phải tạo materialized view ngay lập tức.

Trước tiên hãy hỏi:

1. Dashboard cần **mỗi giao dịch** hay chỉ cần **kết quả đã tổng hợp**?
2. Có đang nhóm ở mức quá chi tiết, ví dụ nhóm theo `order_id` rồi lại tổng ở Java?
3. Có JOIN một-nhiều trước khi tổng hợp khiến tập trung gian phình to?
4. Có lọc trạng thái và thời gian đúng trước khi aggregate?
5. Có dùng bảng nguồn rất lớn cho các yêu cầu lặp lại liên tục?
6. Có độ trễ cho phép để lưu bảng tổng hợp hoặc cache hay không?

### Không giả định CTE luôn tối ưu

`WITH ...` giúp cấu trúc truy vấn, nhưng không có bảo đảm cứ đưa subquery vào CTE là nhanh hơn. PostgreSQL có các quy tắc inlining/materialization tùy phiên bản và cách tham chiếu CTE.

Một CTE được materialize có thể giúp tránh tính lại trong một số trường hợp, hoặc làm mất một số cơ hội đẩy điều kiện xuống trong trường hợp khác. Khi lựa chọn ảnh hưởng hiệu năng, cần xem `EXPLAIN`, không coi CTE là “mệnh lệnh tối ưu” chung.

---

## 13. Phân trang: OFFSET và keyset

Một màn hình hiển thị 20 đơn mới nhất của khách 1.

### OFFSET đơn giản

```sql
SELECT order_id, placed_at, total_amount
FROM lab_orders_333
WHERE customer_id = 1
ORDER BY placed_at DESC, order_id DESC
LIMIT 20 OFFSET 0;
```

Với trang sâu, chẳng hạn `OFFSET 100000`, database có thể vẫn phải duyệt/loại bỏ nhiều hàng trước khi lấy 20 hàng cần trả.

### Keyset pagination

Nếu trang trước kết thúc ở bộ giá trị:

```text
placed_at = 2026-07-02 10:00:00+00
order_id  = 102
```

trang tiếp theo có thể lọc theo cặp cursor:

```sql
SELECT order_id, placed_at, total_amount
FROM lab_orders_333
WHERE customer_id = 1
  AND (placed_at, order_id) <
      (
        TIMESTAMPTZ '2026-07-02 10:00:00+00',
        102
      )
ORDER BY placed_at DESC, order_id DESC
LIMIT 20;
```

Với thứ tự `placed_at DESC, order_id DESC`, điều kiện cặp “nhỏ hơn cursor” lấy các hàng **đi sau** trong thứ tự sắp xếp, nếu cả hai thành phần cursor không `NULL`.

### Index phù hợp với hình dạng query

```sql
CREATE INDEX lab_orders_333_customer_time_id_idx
ON lab_orders_333 (
    customer_id,
    placed_at DESC,
    order_id DESC
);
```

Index này mô tả rõ: lọc theo customer, tiếp đến duyệt theo thời gian và ID giảm dần.

### Cảnh báo

- Keyset cần **ORDER BY có khóa phá hòa** để thứ tự ổn định.
- Nếu điều kiện lọc có nhiều cột hoặc sort theo nhiều hướng, biểu thức cursor và index phải được thiết kế phù hợp.
- Nếu có INSERT/UPDATE/DELETE giữa các request trang, các trang vẫn có thể khác; keyset hạn chế một số vấn đề của OFFSET nhưng không bảo đảm snapshot xuyên các request.
- Không dùng keyset như cách bí mật bỏ qua yêu cầu “nhảy tới trang số 500” nếu UI cần tính năng đó.

---

## 14. Chỉ mục B-tree: biết đủ để đề xuất, không biến thành "thêm mọi index"

Trong PostgreSQL, B-tree là loại index phổ biến cho các phép so sánh bằng, khoảng và nhiều truy vấn `ORDER BY`. Nhưng loại index, thứ tự cột và độ chọn lọc phải phục vụ **workload cụ thể**.

### Index một cột

```sql
CREATE INDEX lab_orders_333_status_idx
ON lab_orders_333 (status);
```

Có thể giúp một số truy vấn lọc theo `status`. Nhưng nếu 95% bảng có `status='PAID'`, lọc `PAID` có thể cần đọc phần lớn bảng; optimizer có thể thích `Seq Scan` hơn.

### Index ghép

```sql
CREATE INDEX lab_orders_333_customer_status_time_idx
ON lab_orders_333 (
    customer_id,
    status,
    placed_at DESC
);
```

Hữu ích cho truy vấn thường lọc bằng `customer_id` và `status` rồi sắp xếp theo `placed_at DESC`, tùy yêu cầu trả cột/ORDER BY và thống kê.

Để bảo đảm thứ tự xác định có `order_id DESC`, index có thể cân nhắc bổ sung `order_id DESC` theo workload.

### Thứ tự cột quan trọng

Với index `(customer_id, status, placed_at)`:

- Lọc `customer_id = ?` có thể tận dụng phần đầu của B-tree.
- Lọc `customer_id = ? AND status = ?` có thể phù hợp hơn.
- Chỉ lọc `status = ?` có thể không khai thác index theo cách mong muốn, tùy phiên bản/optimizer và tỷ lệ dữ liệu.

Không suy rằng index ghép có thể tối ưu tương đương mọi hoán vị cột.

### Index phục vụ ORDER BY

B-tree có thể cung cấp dữ liệu theo thứ tự của key. Khi điều kiện lọc và thứ tự phù hợp, optimizer có thể tránh hoặc giảm công việc `Sort`.

Nhưng nếu query phải đọc rất nhiều cột không nằm trong index, chi phí tra bảng gốc vẫn có thể lớn. Tối ưu index cần cân bằng **lọc, sắp xếp, cột trả về và số hàng khớp**.

---

## 15. INCLUDE, partial index và expression index: công cụ có điều kiện

### 15.1. Index có cột INCLUDE

PostgreSQL hỗ trợ đưa một số cột làm payload:

```sql
CREATE INDEX lab_orders_333_customer_paging_cover_idx
ON lab_orders_333 (
    customer_id,
    placed_at DESC,
    order_id DESC
)
INCLUDE (total_amount);
```

Đây là một index **minh họa thay thế**, không cần tạo đồng thời với mọi index tương tự trên bảng thật.

`INCLUDE` giúp một số truy vấn có thể lấy các cột cần thiết từ index, hỗ trợ cơ hội `Index Only Scan` khi điều kiện visibility map và kế hoạch phù hợp.

**Có đủ cột trong index không bảo đảm Index Only Scan hoàn toàn tránh đọc heap**, vì PostgreSQL cần biết visibility của tuple theo MVCC.

### 15.2. Partial index

Nếu gần như mọi query quan trọng đều lấy đơn PAID theo ngày:

```sql
CREATE INDEX lab_orders_333_paid_time_idx
ON lab_orders_333 (placed_at DESC, order_id DESC)
WHERE status = 'PAID';
```

Index chỉ chứa những hàng thỏa predicate. Nó có thể nhỏ hơn index toàn bảng và hữu ích cho query có điều kiện cho phép optimizer xác nhận phù hợp với `status='PAID'`.

Nhưng:

- Câu query cần có predicate phù hợp để planner có thể dùng index.
- Tham số hóa và generic plan có thể làm planner khó chứng minh predicate `status = $1` luôn tương đương `status='PAID'`.
- Nếu ứng dụng cũng tìm `DRAFT` hoặc `REFUNDED`, partial index này không bao phủ các trường hợp đó.
- Index này không giúp tra cứu tất cả khách theo ID vì nó được thiết kế cho query khác.

### 15.3. Expression index

```sql
CREATE INDEX lab_customers_333_lower_email_idx
ON lab_customers_333 (LOWER(email));
```

Đây là ví dụ index phục vụ biểu thức `LOWER(email)` đã nói ở mục 8.

**Ba loại index trên là công cụ thiết kế vật lý**, không phải yêu cầu người viết SQL nào cũng phải tự triển khai.

### 15.4. Cẩn thận khi thử nhiều index giống nhau

Trong một lab nhỏ, có thể tạo nhiều index để xem cú pháp, nhưng trong production không nên giữ cùng lúc một loạt index bao phủ gần như cùng workload chỉ để “tăng tốc”. Chúng tiêu tốn:

- Dung lượng và cache.
- Công việc mỗi lần `INSERT`, `UPDATE`, `DELETE`.
- Thời gian `VACUUM` và bảo trì.
- Thời gian backup/restore và vận hành.
- Độ phức tạp của migration và đo hiệu quả.

Nếu định đề xuất index mới, hãy liệt kê **index hiện có**, workload mục tiêu, kế hoạch cũ/mới và ảnh hưởng ghi dự kiến.

---

## 16. Đọc EXPLAIN đúng mục đích

Trong PostgreSQL:

```sql
EXPLAIN
SELECT order_id, placed_at
FROM lab_orders_333
WHERE customer_id = 1
ORDER BY placed_at DESC, order_id DESC
LIMIT 20;
```

`EXPLAIN` thông thường cho biết **kế hoạch ước lượng** mà optimizer chọn. Nó không chạy truy vấn SELECT để đo toàn bộ kết quả.

Còn:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, placed_at
FROM lab_orders_333
WHERE customer_id = 1
ORDER BY placed_at DESC, order_id DESC
LIMIT 20;
```

sẽ **thực sự thực thi SELECT** và ghi nhận số liệu như thời gian thực thi, số hàng thực, số lần node chạy và buffer usage.

### Bảng so sánh

| Công cụ | Có chạy truy vấn? | Mục tiêu |
| --- | --- | --- |
| `EXPLAIN SELECT ...` | Không chạy SELECT để trả kết quả | Xem kế hoạch ước lượng |
| `EXPLAIN (ANALYZE) SELECT ...` | **Có** | Đo kế hoạch thực tế và so sánh ước lượng |
| `EXPLAIN (ANALYZE, BUFFERS) ...` | **Có** | Bổ sung chỉ số buffer để tìm manh mối I/O/cache |
| `EXPLAIN (FORMAT JSON) ...` | Với `EXPLAIN` thường, không chạy SELECT | Máy hoặc công cụ có thể phân tích cấu trúc |
| `EXPLAIN (ANALYZE, FORMAT JSON) ...` | **Có** | Đo thực tế và xuất dữ liệu có cấu trúc |

### Cảnh báo đặc biệt với DML

`EXPLAIN (ANALYZE) UPDATE ...`, `INSERT ...` hoặc `DELETE ...` **thực sự thực hiện thao tác ghi**. Không chạy câu đó trên production để “xem kế hoạch” khi chưa có kế hoạch an toàn.

Trong môi trường thực hành, có thể đặt:

```sql
BEGIN;

EXPLAIN (ANALYZE, BUFFERS)
UPDATE lab_orders_333
SET total_amount = total_amount + 1
WHERE order_id = 101;

ROLLBACK;
```

Ví dụ này giúp hoàn tác thay đổi dữ liệu **trong transaction**, nhưng `ROLLBACK` không phải biện pháp bảo đảm không có **mọi tác dụng phụ ngoài transaction**. Sequence, trigger gọi dịch vụ bên ngoài hoặc tích hợp hệ khác có thể có hậu quả riêng. Dùng cách này chỉ khi hiểu rõ schema/trigger và trong môi trường thử nghiệm phù hợp.

**EXPLAIN ANALYZE có chi phí** và làm tăng thời gian truy vấn do đo lường; không nên chạy liên tục trên query nặng trong giờ cao điểm.

---

## 17. Đọc kế hoạch từ dưới lên

Một sơ đồ **minh họa ý tưởng**, không phải output được đo trực tiếp từ bộ dữ liệu nhỏ:

```text
Limit                          rows: 20
  └─ Index Scan using idx_customer_recent_orders
       Index Cond: customer_id = 1
       Output: order_id, placed_at, total_amount
```

Đọc từ phần truy cập dưới lên:

1. `Index Scan`: database cân nhắc dùng index để tìm và đi qua các hàng thỏa điều kiện.
2. `Index Cond`: điều kiện được áp vào đường truy cập index.
3. `Limit`: chỉ trả số hàng cần, nếu kế hoạch và điều kiện cho phép dừng sớm.
4. Nếu không có `Sort` riêng, index có thể đã cung cấp thứ tự phù hợp; phải so khớp với `ORDER BY` đầy đủ.

Một kế hoạch khác có thể là:

```text
Limit
  └─ Sort
       Sort Key: placed_at DESC, order_id DESC
       └─ Seq Scan on lab_orders_333
            Filter: customer_id = 1
```

Điều này không **mặc nhiên xấu**. Trên bảng 12 hàng, quét tuần tự và sort có thể rẻ hơn đi qua index.

### Một số node hay gặp

| Node | Ý nghĩa cơ bản | Câu hỏi cần xem |
| --- | --- | --- |
| `Seq Scan` | Đọc tuần tự bảng | Có đọc phần lớn bảng một cách hợp lý không? |
| `Index Scan` | Tìm qua index rồi lấy hàng | Index có lọc tốt không? Có phải tra heap nhiều không? |
| `Index Only Scan` | Tìm dữ liệu từ index, kiểm tra visibility theo nhu cầu | `Heap Fetches` còn lớn không? |
| `Bitmap Index Scan` + `Bitmap Heap Scan` | Gom vị trí hàng phù hợp rồi đọc heap | Có giảm I/O so với từng index scan không? |
| `Filter` | Loại hàng sau bước truy cập | Có quá nhiều `Rows Removed by Filter` không? |
| `Sort` | Sắp xếp các hàng | Có sort lượng lớn, dùng đĩa không? |
| `Hash` / `Hash Join` | Dựng hash để nối | Hash có vượt bộ nhớ/batch ra đĩa không? |
| `Nested Loop` | Lặp truy cập một phía theo phía còn lại | Số vòng lặp và hàng mỗi vòng có lớn không? |
| `Merge Join` | Nối hai nguồn theo thứ tự khóa | Chi phí sort/đọc đã phù hợp chưa? |
| `Aggregate` / `HashAggregate` | Tính tổng hợp/nhóm | Có nhiều nhóm, thiếu bộ nhớ hoặc spill không? |
| `Gather` / `Gather Merge` | Kết hợp kết quả từ worker song song | Parallelism có hữu ích cho workload này không? |

Không được đọc tên node như một nhãn “tốt” hoặc “xấu” cố định. `Hash Join` rất hợp lý với nhiều trường hợp, còn `Nested Loop` có thể cực nhanh khi phía ngoài ít hàng và phía trong có index tốt.

---

## 18. Chênh lệch estimated rows và actual rows

Một tín hiệu quan trọng khi đọc `EXPLAIN (ANALYZE)` là **ước lượng số hàng** so với **số hàng thật**.

Ví dụ minh họa:

```text
Nested Loop  (estimated rows=10)
  actual rows=800000
  ...
```

Nếu optimizer ước lượng 10 hàng nhưng thực tế sinh 800.000 hàng, nó có thể chọn một chiến lược phù hợp cho 10 hàng nhưng không phù hợp khi dữ liệu lớn.

### Nguyên nhân thường gặp

- Thống kê bảng/cột quá cũ hoặc chưa đại diện dữ liệu hiện tại.
- Phân bố dữ liệu lệch mạnh (skew): một khách hàng có hàng triệu đơn, khách khác chỉ vài đơn.
- Tương quan giữa hai cột, nhưng optimizer ước lượng chúng tương đối độc lập.
- Hàm/biểu thức làm khó ước lượng độ chọn lọc.
- Điều kiện JOIN thiếu khóa dẫn đến nhân bản lớn.
- Tham số generic plan không đại diện cho giá trị cụ thể.
- Câu query có logic phân phối hoặc điều kiện phức tạp mà statistics hiện tại không mô tả tốt.

### actual rows và loops

Trong output PostgreSQL, `actual rows` ở một node thường được biểu thị như **giá trị trung bình mỗi lần thực thi node** khi nó có `loops > 1`. Muốn ước tính tổng hàng node sản xuất, cần xét **cả actual rows và loops**, không chỉ đọc mỗi con số rows.

Ví dụ minh họa:

```text
Index Scan ... (actual rows=20 loops=1000)
```

Có thể tương ứng khoảng **20.000 hàng được trả cộng dồn** từ node đó, dù ở mỗi vòng lặp chỉ 20.

### Đừng dựa vào một sự sai khác nhỏ

Ước lượng 100 và thực tế 120 chưa chắc là nguyên nhân chậm. Cần xem sai lệch **tích lũy** vào chọn join/sort và chi phí chung.

---

## 19. COST, TIME và BUFFERS: đọc đúng đơn vị

Trong PostgreSQL, output `EXPLAIN` có thể hiện:

```text
cost=0.00..123.45
rows=1000
width=64
actual time=0.100..5.200
actual rows=980
loops=1
Buffers: shared hit=100 read=10
```

Đây là **ví dụ mô tả trường thông tin**, không phải kết quả đo từ bảng lab.

### COST không phải mili giây

`cost=...` là **đơn vị chi phí tương đối nội bộ của planner**, dựa trên một mô hình chi phí. Không đọc `cost=123.45` thành “123.45 ms”.

### TIME từ ANALYZE

`actual time` là thời gian đo trong quá trình thực thi node; tùy cách diễn giải node và loops, không nên cộng ngây thơ toàn bộ actual time của các node con thành tổng wall-clock time vì thời gian có quan hệ lồng nhau.

### BUFFERS

- `shared hit`: các block đã có trong shared buffer cache.
- `shared read`: các block cần được đọc vào shared buffers từ lớp lưu trữ/hệ thống; không đồng nghĩa **mỗi block là một lần I/O đĩa vật lý**, vì OS page cache cũng tồn tại.
- `temp read/written`: liên quan dữ liệu tạm, có thể gợi ý sort/hash spill, nhưng phải đọc đúng node và workload.
- Các chỉ số buffer cung cấp **manh mối**, không tự cho biết toàn bộ thời gian chờ ở storage.

### Một kết quả đo không phải bằng chứng đầy đủ

Lần chạy đầu có thể chậm do cold cache, lần sau nhanh do warm cache. Cũng có ảnh hưởng của connection pool, tải đồng thời, checkpoint và hoạt động hệ thống.

Cần đo lặp lại trong điều kiện phù hợp và thu dữ liệu **thống kê theo thời gian**, không tuyên bố tối ưu sau đúng một lần `EXPLAIN ANALYZE` trên máy cá nhân.

---

## 20. Seq Scan không phải kẻ thù

Một truy vấn:

```sql
SELECT *
FROM lab_orders_333
WHERE status = 'PAID';
```

trên bảng 12 hàng có thể chọn `Seq Scan` dù đã tạo `INDEX(status)`. Với vài hàng, đọc toàn bộ bảng thường rẻ hơn việc đi qua index và heap.

Ngay cả trên bảng rất lớn, nếu `status='PAID'` chiếm 98% số hàng và query cần nhiều cột, `Seq Scan` hoặc phương án quét song song có thể là lựa chọn hợp lý.

### Khi nào Seq Scan đáng điều tra?

- Câu query chỉ cần vài hàng trên bảng rất lớn.
- Predicate có độ chọn lọc cao nhưng `Seq Scan` đọc hàng triệu hàng.
- Có index phù hợp nhưng planner không nhận diện hoặc ước lượng sai.
- Điều kiện dùng hàm/cast khiến index hiện có không giúp được.
- Bảng khác hẳn trong production so với môi trường thử.

### Khi nào không cần sửa?

- Bảng rất nhỏ.
- Query phải đọc phần lớn bảng.
- Kết quả chạy nhanh và không gây vấn đề cho workload.
- Việc dùng index làm tăng nhiều random heap fetch hơn so với sequential read.

**Mục tiêu là giảm tổng chi phí và độ trễ cho workload, không phải làm biến mất chữ “Seq Scan” trong kế hoạch.**

---

## 21. Index cần được đánh giá theo cả chi phí ghi

Hãy tưởng tượng bảng giao dịch nhận **10.000 hàng mới/phút** và có 12 index phụ. Mỗi `INSERT` phải bảo trì các cấu trúc index tương ứng, ảnh hưởng WAL, CPU, I/O và cache.

Đề xuất thêm một index phục vụ một báo cáo ít được dùng có thể:

- Giảm thời gian một SELECT.
- Làm tăng độ trễ INSERT/UPDATE.
- Chiếm thêm ổ đĩa và memory cache.
- Kéo dài migration hoặc quá trình khôi phục.
- Làm tăng chi phí bảo trì index và thời gian vacuum/maintenance.
- Tăng nguy cơ tranh chấp tài nguyên trong giờ cao điểm.

### Đánh giá lợi ích ròng

Một index phù hợp khi lợi ích tổng thể lớn hơn chi phí nó tạo ra **trong workload thật**. Cần biết:

- Tần suất câu SELECT mục tiêu.
- Mức giảm latency hoặc tài nguyên đọc.
- Tần suất và kiểu ghi vào bảng.
- Index hiện có có thể dùng lại không.
- Tác động tới các truy vấn khác và kế hoạch khác.
- Dung lượng index và kế hoạch vận hành khi triển khai.

Điều này giải thích vì sao **thiết kế index trên hệ thống dùng chung thường là thay đổi cần review**, dù lập trình viên hoàn toàn có thể đề xuất DDL rất cụ thể.

---

## 22. Index trên production: vì sao không tự tạo vội

PostgreSQL hỗ trợ:

```sql
-- Ví dụ cấu trúc cho DBA xem xét:
CREATE INDEX CONCURRENTLY idx_orders_customer_time
ON orders (customer_id, placed_at DESC);
```

`CREATE INDEX CONCURRENTLY` được thiết kế để giảm một số tác động chặn ghi so với tạo index thông thường, nhưng **không có nghĩa hoàn toàn không tốn tài nguyên hoặc không có rủi ro**.

Các điểm vận hành:

- Không thể chạy `CREATE INDEX CONCURRENTLY` trong một transaction block thông thường.
- Quá trình có thể lâu, dùng CPU/I/O đáng kể và chờ các transaction liên quan.
- Nếu thất bại, có thể để lại một index **INVALID** cần điều tra và xử lý.
- Cần tên index không trùng, đủ dung lượng và hiểu rủi ro replication lag.
- Migration tool có thể mặc định gói nhiều DDL trong transaction; phải cấu hình phù hợp.
- Khi không còn cần index, `DROP INDEX CONCURRENTLY` cũng có ràng buộc thực thi riêng.

**Một lệnh CREATE INDEX đúng cú pháp chưa phải một kế hoạch triển khai an toàn.**

Trong bài tập, chỉ nên thực hiện DDL trên bảng lab. Với production, lập đề xuất dựa trên số liệu và có quy trình phê duyệt/triển khai/quan sát.

---

## 23. Khi chậm không phải do đường truy cập: chờ khóa

Một truy vấn có kế hoạch rất đẹp vẫn có thể mất 30 giây nếu bị **blocked** bởi transaction khác.

Ví dụ PostgreSQL:

```text
Transaction A:
  BEGIN;
  UPDATE inventory SET qty=... WHERE sku='A';
  -- chưa COMMIT

Transaction B:
  UPDATE inventory SET qty=... WHERE sku='A';
  -- phải chờ khóa hàng của A
```

Nếu chỉ nhìn cấu trúc query B, nó có thể tìm đúng một hàng theo primary key. Thêm index mới thường không xử lý được **việc hai transaction cùng sửa một hàng**.

### Dấu hiệu lock/contention

- Query trong log chậm bất thường nhưng `EXPLAIN ANALYZE` trên bản sao rảnh rỗi lại nhanh.
- Nhiều session chờ cùng tài nguyên.
- Transaction mở lâu, không commit.
- Nhiều update lên cùng một hàng “hot”, như bộ đếm tổng.
- Deadlock hoặc lock timeout.

### Công cụ chẩn đoán cơ bản PostgreSQL

Trong môi trường được cấp quyền quan sát:

```sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    now() - query_start AS query_age
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
ORDER BY query_start;
```

Các cột như `wait_event_type` giúp biết session đang chờ loại sự kiện nào. Nhưng:

- `query_age` không đồng nghĩa toàn bộ thời gian **thực thi CPU**; có thể gồm chờ.
- Quyền hạn có thể giới hạn dữ liệu session khác được thấy.
- Không lấy một snapshot quan sát rồi kết luận nguyên nhân gốc nếu thiếu lịch sử.
- Query text của người dùng có thể chứa thông tin nhạy cảm; thu thập/ghi log theo chính sách bảo mật.

Điều tra blocker chain, deadlock graph, transaction timeout và chính sách isolation đã thuộc **vùng phối hợp DBA/SRE**, không chỉ rewrite một câu SELECT.

---

## 24. Thống kê, ANALYZE và lý do planner đoán sai

Optimizer không biết chính xác mọi giá trị của mọi hàng trước khi lập kế hoạch. Nó dùng **statistics** về số hàng, phân bố giá trị, độ chọn lọc, số distinct, tương quan và các yếu tố khác.

Trên PostgreSQL, sau khi nạp dữ liệu thử nghiệm có thể dùng:

```sql
ANALYZE lab_orders_333;
```

Điều này cập nhật thống kê phục vụ planner cho bảng lab. Nhưng **không phải một thao tác chữa mọi truy vấn chậm**.

### Khi thống kê có thể là vấn đề?

- Bảng vừa bulk-load thêm một lượng dữ liệu rất lớn.
- Phân bố `status` thay đổi mạnh, như từ 10% PAID thành 95% PAID.
- Một vài khách đặc biệt có hàng triệu đơn, trong khi phần lớn khách có rất ít.
- Dữ liệu theo ngày mới thường xuyên được thêm vào, vượt xa những giá trị mà thống kê hiện tại mô tả tốt.
- Điều kiện nhiều cột có tương quan mạnh mà thống kê đơn cột không diễn tả đủ.

### Extended statistics

PostgreSQL có `CREATE STATISTICS` cho một số loại thông tin đa cột. Ví dụ ý tưởng:

```sql
-- Ví dụ lab: thống kê quan hệ customer_id và status.
CREATE STATISTICS lab_orders_333_customer_status_stats
    (dependencies, ndistinct)
ON customer_id, status
FROM lab_orders_333;

ANALYZE lab_orders_333;
```

Điều này có thể giúp planner trong những tình huống tương quan nhất định, nhưng:

- Không mọi kiểu điều kiện/JOIN đều hưởng lợi.
- Không thay đổi ngữ nghĩa dữ liệu.
- Statistics bản thân có chi phí thu thập, và có thể cần cấu hình độ chi tiết.
- Không nên áp dụng thống kê đa cột tùy tiện cho mọi cặp cột của bảng lớn.

Khi cần thay `default_statistics_target`, chính sách autovacuum/analyze hoặc sửa các thông số toàn hệ, đó là **bài toán quản trị** cần số liệu và phạm vi tác động.

---

## 25. Kế hoạch khác nhau theo tham số: data skew và prepared statements

Một câu truy vấn có thể nhanh cho khách hàng A nhưng chậm cho khách hàng B:

```sql
SELECT order_id, placed_at, total_amount
FROM lab_orders_333
WHERE customer_id = $1
ORDER BY placed_at DESC, order_id DESC
LIMIT 100;
```

Trên dữ liệu thật:

- Khách A có 5 đơn.
- Khách B có 5 triệu đơn.
- Hai người dùng cùng một SQL text.

Optimizer có thể chọn kế hoạch khác nếu ước lượng được độ chọn lọc của tham số thực tế. Với **prepared statements**, PostgreSQL có khái niệm **custom plan** và **generic plan**, lựa chọn theo cơ chế và điều kiện của phiên bản.

### Vì sao điều này quan trọng?

- Kế hoạch tốt cho giá trị phổ biến có thể không tốt cho giá trị hiếm.
- Một cache kế hoạch generic có thể không phản ánh một tham số đặc biệt lệch phân bố.
- Cùng một câu SQL chạy trên staging với dữ liệu cân bằng có thể không đại diện production.

### Hướng xử lý

- Ghi nhận ví dụ tham số chậm và nhanh **sau khi đã loại bỏ thông tin nhạy cảm**.
- So sánh estimated/actual rows và plan shape trong môi trường an toàn.
- Xác định index có phù hợp nhiều dạng truy vấn hay không.
- Nếu cần can thiệp policy generic/custom plan, kiểm tra phiên bản và đánh giá rộng cùng DBA.

**Đừng tự động chèn literal thay cho mọi tham số để ép một kế hoạch.** Prepared statements có vai trò an toàn, khả năng tái sử dụng và quản lý query. Cần giải quyết bằng thiết kế và đo lường, không đánh đổi SQL injection protection.

---

## 26. N+1 query: vấn đề thường nằm ở ứng dụng, không phải planner

Một đoạn ứng dụng:

```text
1 query lấy 100 khách
100 query lần lượt lấy đơn của từng khách
→ tổng 101 lần gọi database
```

Mỗi câu nhỏ có thể chỉ mất 2 ms, nhưng tổng latency còn bao gồm round trip, connection occupancy và serialize dữ liệu.

### Một ví dụ cách thay đổi hình dạng truy vấn

Thay vì gọi một lần cho từng khách:

```sql
SELECT *
FROM lab_orders_333
WHERE customer_id = :customer_id;
```

có thể tải theo nhóm khách:

```sql
SELECT
    order_id, customer_id, placed_at, total_amount
FROM lab_orders_333
WHERE customer_id IN (1, 2, 3, 4)
ORDER BY customer_id, placed_at DESC, order_id DESC;
```

Sau đó ứng dụng gom đơn theo `customer_id`.

### Nhưng nếu mỗi khách chỉ cần 3 đơn mới nhất?

Truy vấn `IN (...)` phía trên lấy **tất cả** đơn của bốn khách. Nó có thể giảm round trip nhưng vẫn tải dư dữ liệu.

PostgreSQL có thể dùng `ROW_NUMBER()`:

```sql
WITH ranked AS (
    SELECT
        o.order_id,
        o.customer_id,
        o.placed_at,
        o.total_amount,
        ROW_NUMBER() OVER (
            PARTITION BY o.customer_id
            ORDER BY o.placed_at DESC, o.order_id DESC
        ) AS rn
    FROM lab_orders_333 AS o
    WHERE o.customer_id IN (1, 2, 3, 4)
)
SELECT order_id, customer_id, placed_at, total_amount
FROM ranked
WHERE rn <= 3
ORDER BY customer_id, rn;
```

Hoặc dùng `LATERAL`/`LIMIT` theo từng khách nếu workload/index phù hợp. Không có một cách luôn nhanh nhất; điều quan trọng là **diễn đạt đúng “top N per group”** để tránh 100 lượt query nhỏ và tránh tải toàn bộ lịch sử không cần thiết.

---

## 27. Những tác vụ quản trị không nên chữa bằng rewrite SQL mù quáng

| Dấu hiệu | Có thể liên quan | Vì sao đã vượt phạm vi một câu SQL |
| --- | --- | --- |
| Mọi truy vấn đều chậm cùng lúc | CPU/I/O saturation, storage, connection pressure | Cần số liệu toàn hệ và điều phối workload |
| SELECT nhanh nhưng ghi chậm kéo dài | WAL, fsync, lock, index write overhead | Cần điều tra đường ghi và cấu hình |
| Planner chọn sai sau bulk load | Statistics/autovacuum/analyze | Cần hiểu lịch thống kê và table maintenance |
| Bảng/index phình to bất thường | Dead tuples, bloat, vacuum lag | Cần điều tra retention, transaction dài, maintenance |
| Replica hiển thị dữ liệu trễ | Replication lag hoặc query trên replica | Query ở primary có thể bình thường |
| Deadlock tăng | Thứ tự lock, transaction dài, concurrency | Cần xem giao dịch và ứng dụng, không chỉ SELECT |
| Query spill ra temp disk hàng loạt | Memory per query, số phép sort/hash đồng thời | Tăng `work_mem` toàn hệ có thể làm tệ hơn |
| Pool luôn hết connection | Request concurrency, connection leaks, transaction lâu | Phải tối ưu tổng hệ, không thêm index đơn thuần |
| Checkpoint gây spike | WAL/checkpoint configuration, I/O scheduling | Thay đổi global config ảnh hưởng nhiều workload |
| Query biến động mạnh theo giờ | Batch jobs, cache, autovacuum, backup | Cần correlation theo thời gian |

### Vì sao không tăng work_mem tùy ý?

`work_mem` trong PostgreSQL có thể được sử dụng bởi **nhiều node sort/hash trong cùng một query**, và có nhiều query/session đồng thời. Tăng mức này lên rất cao cho toàn hệ có thể làm tổng tiêu thụ bộ nhớ tăng mạnh và gây áp lực RAM.

Một phép sort spill ra đĩa có thể cần cải thiện query, index, lượng dữ liệu hoặc điều chỉnh memory **theo session/workload** dưới sự giám sát, thay vì tăng một thông số toàn server khi chưa tính concurrency.

---

## 28. VACUUM, bloat và tính đặc thù của PostgreSQL

PostgreSQL dùng MVCC, vì thế những phiên bản hàng cũ và dead tuples cần được quản lý theo cơ chế vacuum/autovacuum.

Nếu bảng có nhiều update/delete, index và heap có thể cần bảo trì. Những vấn đề có thể xuất hiện:

- Bloat làm tăng số page phải đọc.
- Visibility map ảnh hưởng cơ hội `Index Only Scan`.
- Transaction mở quá lâu cản trở thu hồi phiên bản hàng cũ.
- Autovacuum không theo kịp workload hoặc cần tuning theo bảng.
- Chỉ mục có thể cần chiến lược bảo trì phù hợp khi phình to.

### Điều người viết SQL nên làm

- Giảm UPDATE không cần thiết và transaction dài trong ứng dụng.
- Đảm bảo WHERE dùng đúng khóa để tránh ghi hàng loạt ngoài ý định.
- Báo cáo số hàng thay đổi, tỷ lệ update/delete, thời điểm job import lớn.
- Đưa bằng chứng như `EXPLAIN (BUFFERS)`, chênh lệch estimated/actual rows, tần suất lỗi timeout.

### Điều cần phối hợp

- Đánh giá autovacuum settings và lịch vận hành.
- Phân tích bloat và disk usage.
- Quyết định có cần `REINDEX` hoặc bảo trì online.
- Kiểm tra replication slots/long transactions gây giữ dữ liệu cũ.
- Đánh giá I/O và dung lượng dự phòng.

Không chạy `VACUUM FULL` hoặc một đợt `REINDEX` lớn trên production chỉ vì nghe từ “bloat”. Các thao tác này có thể yêu cầu khóa, dung lượng và kế hoạch downtime/rollback riêng.

---

## 29. Caching, materialized views và độ mới

Khi nhiều truy vấn liên tục tính cùng một báo cáo lớn, có thể nghĩ tới:

- **Cache kết quả** ở ứng dụng.
- **Bảng tổng hợp** cập nhật theo batch.
- **Materialized view**.
- **Pre-aggregation** ở kho dữ liệu.
- **Replication/read replica** để tách tải đọc.

Nhưng đây không còn chỉ là viết câu SQL; bạn phải xác định:

1. Dữ liệu được làm mới **khi nào**?
2. Có chấp nhận **stale data** không?
3. Ai invalidates cache và khi job thất bại thì sao?
4. Người dùng có cần **read-your-writes** không?
5. Dữ liệu có phân tách tenant/quyền truy cập không?
6. Lợi ích đọc có đáng chi phí lưu và cập nhật không?

Nếu API chuyển từ đọc đơn trực tiếp sang bảng tổng hợp chậm 5 phút, latency có thể giảm nhưng **ngữ nghĩa độ mới đã thay đổi**. Đây là quyết định sản phẩm/hệ thống, không thể gọi đơn thuần là “query optimization”.

---

## 30. Độ trễ p95/p99 và đo workload thật

Một query chạy nhanh ở trung bình chưa chắc đáp ứng trải nghiệm người dùng.

Ví dụ giả định:

| Phân vị | API latency |
| --- | ---: |
| p50 | 40 ms |
| p95 | 550 ms |
| p99 | 2.400 ms |

Nếu tối ưu làm p50 từ 40 xuống 30 ms nhưng p99 vẫn 2.400 ms vì lock waits, người dùng ở phần đuôi phân phối vẫn gặp vấn đề.

### Metrics đáng thu thập

- Số lần chạy mỗi phút hoặc request rate.
- p50/p95/p99 latency của API và truy vấn.
- Tổng thời gian database tiêu thụ theo query fingerprint.
- Số hàng trả về, byte truyền và rows examined.
- Số lỗi timeout, deadlock, serialization failure.
- Lock wait, buffer/cache behavior, I/O, temp spill.
- CPU/memory sử dụng ở thời điểm chậm.
- Tham số hoặc mẫu dữ liệu liên quan, theo chính sách bảo mật.

### “Query chậm nhất” không phải lúc nào cũng ưu tiên số một

Một câu chạy 10 giây **một lần/ngày** có thể ít ảnh hưởng tổng tải hơn một câu chạy 50 ms **100.000 lần/giờ**, dù câu thứ hai trông không chậm ở từng lượt.

Phải xét **tần suất × chi phí × tác động nghiệp vụ**, chứ không chỉ sắp xếp theo một lần thực thi lâu nhất.

---

## 31. Công cụ quan sát truy vấn ở PostgreSQL

### 31.1. pg_stat_statements

Extension `pg_stat_statements` (khi được triển khai/cấu hình) cung cấp thống kê **tổng hợp theo dạng truy vấn được chuẩn hóa**, giúp tìm những query tiêu thụ nhiều tổng thời gian hoặc được gọi quá nhiều.

Ví dụ mang tính tham khảo:

```sql
-- PostgreSQL: chỉ chạy nếu pg_stat_statements đã
-- được cấu hình và người dùng có quyền phù hợp.
SELECT
    calls,
    total_exec_time,
    mean_exec_time,
    rows,
    query
FROM pg_stat_statements
ORDER BY total_exec_time DESC
LIMIT 10;
```

Các cột và khả năng truy cập phụ thuộc phiên bản/config/quyền. `total_exec_time` là tổng thời gian **thực thi** đã được ghi nhận trong cửa sổ thống kê, không tự bao gồm toàn bộ thời gian API/queue.

**Không tự bật extension hoặc đổi preload libraries trên production** chỉ để chạy thử một câu quan sát. Việc này có thể cần quyền đặc biệt và thay đổi cấu hình, thậm chí restart tùy setup.

### 31.2. pg_stat_activity

`pg_stat_activity` giúp quan sát trạng thái session và loại chờ hiện thời; nó hữu ích với truy vấn đang chạy hoặc bị khóa, nhưng không phải công cụ thay thế một hệ thống metrics theo thời gian.

### 31.3. EXPLAIN cùng thông số BUFFERS

`EXPLAIN (ANALYZE, BUFFERS)` phù hợp để điều tra một query đại diện trong môi trường an toàn. Với query đang chạy lâu và có side effect, không nên tái hiện vô tội vạ vào giờ cao điểm chỉ vì muốn đo.

### 31.4. Logs và auto_explain

PostgreSQL có cơ chế log slow statements và extension `auto_explain` trong những cấu hình phù hợp. Chúng có thể giúp bắt kế hoạch của một truy vấn khó tái hiện, nhưng cũng thêm overhead và có khả năng ghi dữ liệu/SQL nhạy cảm.

Thiết kế logging, retention, sampling và quyền truy cập thuộc phạm vi vận hành, phải cân bằng hiệu năng với bảo mật.

---

## 32. Phân tích một truy vấn chậm theo từng giả thuyết

Giả sử trên production, API “đơn gần đây của khách hàng” từ 80 ms tăng lên 3 giây khi bảng `orders` lớn dần.

Câu SQL đang chạy:

```sql
SELECT *
FROM orders
WHERE customer_id = :customer_id
ORDER BY placed_at DESC
LIMIT 50 OFFSET 50000;
```

### Giả thuyết 1: tải dư nhiều hàng

`SELECT *` có thể lấy các cột lớn không cần thiết. Hãy xác định contract API; nếu chỉ cần `order_id,placed_at,total_amount`, thay projection.

### Giả thuyết 2: OFFSET quá sâu

`OFFSET 50000` có thể buộc database bỏ qua rất nhiều hàng. Nếu UI có thể dùng cursor, cân nhắc keyset pagination với `ORDER BY placed_at DESC, order_id DESC`.

### Giả thuyết 3: index không phù hợp

Index `(customer_id, placed_at DESC, order_id DESC)` có thể phù hợp với lọc khách và thứ tự. Nhưng cần kiểm tra index hiện có, kế hoạch và số hàng thực trước khi tạo.

### Giả thuyết 4: data skew

Một khách có 10 triệu đơn; khách khác 20 đơn. Cùng SQL có thể yêu cầu kế hoạch/chiến lược phân trang khác nhau. Cần đo với tham số đại diện.

### Giả thuyết 5: hệ thống nghẽn

Nếu plan và thời gian database ở thử nghiệm tốt nhưng production chậm vào giờ nhất định, cần xem I/O, lock, connection pool, batch jobs và cache.

### Thứ tự hành động

1. Xác minh đúng API output.
2. Thu query fingerprint, số hàng, tham số đại diện, tần suất và latency.
3. Đọc plan và thống kê ước lượng/thực tế.
4. Thử sửa hình dạng query trước nếu có lỗi rõ.
5. Đề xuất index có bằng chứng và review.
6. Nếu phần chậm đến từ toàn hệ, chuyển điều tra cùng DBA/SRE.

Đừng làm đồng thời mọi thay đổi rồi không biết biện pháp nào tạo ra cải thiện.

---

## 33. Một quy trình benchmark tối thiểu có thể tái hiện

Để đánh giá hai phiên bản truy vấn, có thể chuẩn bị bảng thí nghiệm:

| Nội dung | Ghi lại |
| --- | --- |
| Phiên bản DBMS | PostgreSQL version/cấu hình liên quan |
| Phiên bản SQL | Query A/B nguyên văn sau khi loại dữ liệu nhạy cảm |
| Tham số | Một số trường hợp phổ biến, hiếm, giá trị gây chậm |
| Quy mô dữ liệu | Số hàng bảng, phân bố khóa, phạm vi ngày |
| Chỉ mục | Những index đã tồn tại trước/sau |
| Thống kê | Thời điểm ANALYZE/autovacuum gần đây nếu liên quan |
| Kế hoạch | Node chính, estimated/actual rows, loops |
| Tài nguyên | BUFFERS, temp I/O, wait events, CPU |
| Kết quả | Số hàng, tổng kiểm tra, row keys, NULL semantics |
| Thời gian | Đo nhiều lần và trong workload đại diện |
| Concurrency | Số session/requests đồng thời |
| Điều kiện triển khai | Lock, disk space, rollback plan |

### Bước đo an toàn trong lab

```sql
-- Query chỉ đọc, trên các bảng thử nghiệm của bài:
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, placed_at, total_amount
FROM lab_orders_333
WHERE customer_id = 1
ORDER BY placed_at DESC, order_id DESC
LIMIT 20;
```

Sau đó thử một query khác có cùng nghĩa:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, placed_at, total_amount
FROM lab_orders_333
WHERE customer_id = 1
  AND (placed_at, order_id) <
      (
        TIMESTAMPTZ '2026-07-05 00:00:00+00',
        999999
      )
ORDER BY placed_at DESC, order_id DESC
LIMIT 20;
```

Hai query trên **không có cùng tập đầu ra** vì query thứ hai có điều kiện cursor; chúng minh họa hai cấu trúc phân trang nhưng **không được dùng để tuyên bố một cách nhanh hơn theo phép so sánh tương đương**.

Muốn benchmark công bằng, phải đảm bảo hai cách giải **cùng nghiệp vụ và cùng vị trí trang**, với dữ liệu ổn định và số lần đo đủ đại diện.

---

## 34. Các thay đổi thường ở phạm vi người viết SQL

Dưới đây là những việc có thể bắt đầu mà không cần đổi cấu hình database:

| Thay đổi | Điều cần kiểm chứng |
| --- | --- |
| Bỏ cột không cần | API/ứng dụng không phụ thuộc cột đó |
| Trả số hàng phù hợp, thêm LIMIT | `ORDER BY` xác định và business contract đúng |
| Chuyển lọc ngày thành khoảng nửa mở | Múi giờ, ranh giới, precision đúng |
| Sửa JOIN đúng khóa | Không mất hàng hoặc nhân bản |
| Dùng `EXISTS` khi chỉ cần tồn tại | Không cần dữ liệu từ phía JOIN |
| Tính tổng theo grain chính xác | NULL, DISTINCT, các hàng không có match |
| Gộp N+1 thành truy vấn có batch | Không tải dữ liệu dư, không mất phân trang theo nhóm |
| Dùng keyset thay OFFSET sâu | Cursor chính xác, có khóa phá hòa, UI chấp nhận |
| Parameterize giá trị | Kiểu tham số phù hợp, giữ chống SQL injection |
| Thêm điều kiện lọc phù hợp | Không loại dữ liệu nghiệp vụ cần thiết |

**Có thể sửa SQL chưa có nghĩa được tự sửa mọi schema/index đi kèm.** Cần review khi thay đổi có phạm vi ảnh hưởng rộng hoặc thuộc một schema dùng chung.

---

## 35. Các thay đổi nên giao tiếp theo đề xuất kỹ thuật

Khi cần DBA/SRE, thay vì nhắn “database chậm, thêm RAM đi”, hãy cung cấp một hồ sơ gọn:

### Ví dụ đề xuất có căn cứ

```text
Chức năng:
  API GET /customers/{id}/orders

Triệu chứng:
  p95 latency tăng từ 120 ms lên 900 ms sau khi bảng lớn hơn.

Truy vấn:
  WHERE customer_id = ?
  ORDER BY placed_at DESC, order_id DESC
  LIMIT 20

Dữ liệu:
  orders ~40 triệu hàng; customer_id phân bố lệch.
  Giá trị gây chậm thuộc nhóm khách có nhiều đơn.

Kế hoạch:
  estimated rows thấp hơn actual rows nhiều.
  Sort trên tập trung gian lớn / đọc nhiều pages.

Giả thuyết:
  Thiếu hoặc chưa tận dụng index phù hợp lọc + thứ tự.

Đề xuất:
  Đánh giá index (customer_id, placed_at DESC, order_id DESC).
  Đo thay đổi p95, tổng I/O, write overhead và index size.

Rủi ro:
  Bảng có tải ghi cao; cần kế hoạch CREATE INDEX CONCURRENTLY,
  theo dõi replication lag/dung lượng và cách xử lý index INVALID.
```

Các con số trong mẫu là **tình huống giả định**, không phải phép đo từ môi trường người học.

### Điều nên nêu rõ trong đề xuất

- Thay đổi tác động **truy vấn nào** và **người dùng nào**.
- Nguyên nhân được **quan sát** hay mới là **giả thuyết**.
- Cách chứng minh cải thiện và cách **quay lại** nếu kém hơn.
- Những workload khác có thể bị ảnh hưởng.
- Cần quyền/công cụ hoặc thời gian bảo trì gì.

Một cuộc trao đổi như vậy giúp DBA/SRE xử lý nhanh hơn nhiều so với “cứ tạo thêm index rồi thử”.

---

## 36. Cấu hình, partitioning và read replica: khi tối ưu trở thành kiến trúc

### 36.1. Tăng máy chủ hoặc đổi storage

Nếu mọi câu query có kế hoạch hợp lý nhưng I/O đã bão hòa, việc thêm index có thể không đủ. Có thể cần storage nhanh hơn, tách workload, thay cách ghi, hoặc tăng tài nguyên.

Nhưng tăng tài nguyên không được dùng để che truy vấn đọc dư hàng trong thời gian dài nếu có thể sửa hình dạng câu SQL.

### 36.2. Partitioning

Bảng `orders` rất lớn và truy vấn thường giới hạn theo tháng có thể cân nhắc partition theo thời gian. Nhưng thiết kế cần xem:

- Điều kiện partition pruning có được viết/hiểu đúng không.
- Khóa primary/unique bị ràng buộc thế nào trên bảng partitioned.
- Cách thêm/xóa/retention partition.
- Index local và truy vấn xuyên nhiều partition.
- Chi phí migration và độ phức tạp vận hành.

**Partitioning không mặc định nhanh hơn**. Nếu query liên tục phải đọc mọi partition, overhead có thể tăng.

### 36.3. Read replica

Tách tải báo cáo sang replica có thể giảm áp lực đọc primary, nhưng:

- Có **replication lag**.
- Dữ liệu người dùng vừa ghi có thể chưa xuất hiện.
- Query nặng trên replica vẫn có thể gây tranh chấp tài nguyên.
- Snapshot và quyền có thể khác cấu hình primary.

Nếu nghiệp vụ cần “vừa tạo đơn xong thì lập tức nhìn thấy đơn”, không thể chỉ định mọi SELECT đi qua replica trễ mà không có cơ chế consistency phù hợp.

### 36.4. Materialized view / cache

Đọc nhanh hơn từ bản tổng hợp đi kèm **hợp đồng độ mới** và quy trình refresh. Đây là quyết định ở cấp hệ thống, phải được sản phẩm chấp nhận.

---

## 37. SQL Server, MySQL, Oracle và SQLite: công cụ khác nhau

### 37.1. MySQL/InnoDB

MySQL có `EXPLAIN` và ở các phiên bản MySQL 8.0 phù hợp có `EXPLAIN ANALYZE` để quan sát execution plan thực tế. Có thể dùng Performance Schema và các công cụ ghi nhận workload.

Ví dụ MySQL:

```sql
EXPLAIN
SELECT order_id
FROM orders
WHERE customer_id = 1
ORDER BY placed_at DESC
LIMIT 20;
```

Không dùng trực tiếp cú pháp `EXPLAIN (ANALYZE, BUFFERS)` của PostgreSQL rồi nghĩ MySQL sẽ hiểu giống hệt.

MySQL optimizer/index, histograms, kiểu index và cách hiển thị plan khác PostgreSQL. Những thao tác như `ANALYZE TABLE`, invisible index hoặc đổi optimizer switches cần kiểm tra bản MySQL và quyền vận hành.

### 37.2. SQL Server

SQL Server có **estimated/actual execution plans**, `SET STATISTICS IO ON`, `SET STATISTICS TIME ON`, Query Store và DMVs phù hợp để điều tra query chậm.

Ví dụ:

```sql
-- SQL Server, trong database thử nghiệm:
SET STATISTICS IO ON;
SET STATISTICS TIME ON;

SELECT order_id, placed_at
FROM dbo.Orders
WHERE customer_id = 1
ORDER BY placed_at DESC;

SET STATISTICS IO OFF;
SET STATISTICS TIME OFF;
```

Khi dùng actual plan, cần hiểu operator, actual vs estimated rows, logical reads, spills, blocking và parameter sniffing/plan reuse. Index hints hoặc query hints có thể là biện pháp đặc thù, nhưng không nên là bước đầu tiên.

### 37.3. Oracle Database

Oracle có `EXPLAIN PLAN` và các cách xem kế hoạch thực thi như `DBMS_XPLAN.DISPLAY_CURSOR` khi có quyền/thông tin thích hợp.

`EXPLAIN PLAN` thể hiện **kế hoạch ước lượng**, không mặc định là actual plan của lần chạy cụ thể. Với truy vấn đã thực thi, công cụ xem cursor runtime statistics mới có thể cung cấp các số liệu tương ứng, tùy cấu hình.

Các tính năng giám sát chuyên sâu như AWR/ASH có yêu cầu về quyền và **giấy phép** trong nhiều môi trường; không tự bật hoặc sử dụng ngoài phạm vi được phép.

### 37.4. SQLite

SQLite có:

```sql
EXPLAIN QUERY PLAN
SELECT order_id
FROM orders
WHERE customer_id = 1;
```

Dòng output thường giúp thấy `SCAN` hay `SEARCH ... USING INDEX` ở mức phù hợp. SQLite có planner và cơ chế thống kê/chỉ mục riêng, không có các node PostgreSQL như `HashAggregate` hiển thị cùng một cách.

### 37.5. Bảng đối chiếu

| Mục tiêu | PostgreSQL | MySQL | SQL Server | Oracle | SQLite |
| --- | --- | --- | --- | --- | --- |
| Kế hoạch ước lượng | `EXPLAIN` | `EXPLAIN` | Estimated plan | `EXPLAIN PLAN` | `EXPLAIN QUERY PLAN` |
| Đo kế hoạch khi thực thi | `EXPLAIN (ANALYZE)` | `EXPLAIN ANALYZE` ở phiên bản hỗ trợ | Actual plan/STATISTICS | Cursor runtime plan/statistics | Công cụ/timing theo SQLite |
| Thu workload | `pg_stat_statements`/logs | Performance Schema | Query Store/DMVs | Công cụ cursor/monitoring theo quyền | Công cụ ứng dụng/profiler |
| Bảo trì thống kê | `ANALYZE`, autovacuum | `ANALYZE TABLE`/histograms | Auto/update statistics | DBMS_STATS | `ANALYZE`/các cơ chế tối ưu phù hợp |
| Can thiệp kế hoạch | Index, query/schema và cấu hình optimizer có kiểm soát | Optimizer hints/indexes | Query hints, plan guides, Query Store hints tùy môi trường | Hints/profiles/SQL plan management theo môi trường | Index và cấu trúc SQL |

**Điểm chung:** bắt đầu từ ngữ nghĩa đúng, thu đo workload và đọc kế hoạch. **Điểm khác:** công cụ, cơ chế stats, concurrency, privilege và tác động khi thay đổi.

---

## 38. Ranh giới “biết EXPLAIN” và “điều khiển optimizer”

Biết đọc `EXPLAIN` đủ để trả lời các câu:

- Truy vấn đang quét cả bảng hay tìm theo index?
- Có sort lớn, nhiều rows removed by filter, join phát sinh dữ liệu khổng lồ không?
- Estimated rows và actual rows có lệch mạnh không?
- Thời gian dành cho node nào, có nhiều loops, buffer reads hay temp I/O không?
- Plan trên dữ liệu lớn có phù hợp dự đoán ban đầu không?

Nhưng **điều khiển optimizer chuyên sâu** có thể liên quan:

- Thay đổi cost constants hoặc planner settings.
- Giải quyết plan instability khi phân bố dữ liệu thay đổi.
- Chọn custom/generic plan cho prepared statements.
- Thay chiến lược thống kê và extended statistics.
- Dùng hints/plan forcing của sản phẩm khi có căn cứ.
- Partition pruning và phức tạp của parallel execution.
- Thiết kế indexing trên nhiều truy vấn cạnh tranh.
- Quản lý nâng cấp phiên bản ảnh hưởng optimizer.

Những hoạt động đó cần hiểu **không chỉ câu SQL mục tiêu mà cả hệ thống và phiên bản DBMS**.

### Đừng ép kế hoạch bằng mọi giá

Nếu một index scan hiện nhanh hơn trên một mẫu tham số, không có nghĩa phải **force** index đó cho mọi trường hợp. Hints/plan forcing có thể biến giải pháp tạm thành sự phụ thuộc giòn khi dữ liệu lớn lên hoặc phân bố đổi.

Nên dùng hints khi có bằng chứng và kế hoạch duy trì, không coi nó là thay thế cho thống kê/index/query design đúng.

---

## 39. Ba tình huống để xác định ranh giới xử lý

### Tình huống A: một báo cáo thiếu WHERE

```sql
SELECT order_id, customer_id, total_amount
FROM orders;
```

Ứng dụng chỉ cần đơn của một khách. Đây là lỗi **viết SQL/ứng dụng**: cần thêm `WHERE customer_id = ?` theo quyền truy cập, chọn đúng cột, LIMIT/ORDER BY phù hợp. Chưa cần yêu cầu DBA tăng RAM.

### Tình huống B: truy vấn đúng nhưng table scan hàng trăm triệu rows

```sql
SELECT order_id
FROM orders
WHERE customer_id = ?
ORDER BY placed_at DESC
LIMIT 20;
```

Nếu thiếu index phù hợp và plan chứng minh quét quá nhiều hàng, người viết SQL có thể đề xuất index `(customer_id, placed_at DESC, order_id DESC)`, còn việc triển khai trên bảng lớn cần **review và kế hoạch DDL**.

### Tình huống C: cùng câu SQL nhanh ban ngày, chậm khi ETL chạy

Kế hoạch có thể không đổi nhưng latency tăng theo thời điểm batch, I/O và lock waits. Đây là vấn đề **workload/resource contention**. Cần đo theo giờ và phối hợp nhóm vận hành, không chỉ sửa `WHERE` hoặc force index.

### Tình huống D: p99 cao do connection pool

Database ghi nhận query duration 12 ms, nhưng request chờ connection 700 ms. Dù câu SQL có thể tối ưu hơn, bottleneck hiện tại liên quan pool, transaction lifetime, request concurrency hoặc leak. Cần phối hợp tầng ứng dụng và hạ tầng.

---

## 40. Những ngộ nhận thường gặp

| Ngộ nhận | Vì sao không đủ chính xác | Hướng làm đúng |
| --- | --- | --- |
| “Thấy Seq Scan là query sai” | Quét tuần tự có thể tối ưu cho bảng nhỏ hoặc đọc nhiều hàng | Xem selectivity, cost và actual timing |
| “Có index là query chắc chắn nhanh” | Index có chi phí tra cứu/ghi và không luôn được chọn | Đo workload, kiểm tra plan |
| “Thêm index cho mọi cột WHERE” | Nhiều index tốn ghi, dung lượng và có thể trùng nhau | Thiết kế theo mẫu query phổ biến |
| “WHERE có hàm là luôn không thể tối ưu” | Có expression index/loại index khác và planner linh hoạt | Kiểm tra semantics và đường truy cập |
| “LIMIT 20 trả đúng 20 bản mới nhất” | Không có ORDER BY thì không định nghĩa “mới nhất” | Sort xác định có khóa phá hòa |
| “OFFSET 100000 vẫn nhanh vì LIMIT 20” | Có thể phải bỏ qua rất nhiều hàng | Cân nhắc keyset |
| “JOIN luôn chậm, thay bằng subquery sẽ nhanh” | Planner có thể rewrite; đúng grain quan trọng hơn | Đọc plan, đo và kiểm tra kết quả |
| “DISTINCT sửa được duplicate do JOIN” | Có thể che lỗi và vẫn tạo tổng sai | Sửa khóa và grain |
| “EXISTS luôn nhanh hơn COUNT” | Phụ thuộc kế hoạch và dữ liệu | Dùng đúng ngữ nghĩa, benchmark khi cần |
| “Index Only Scan không đụng heap” | MVCC visibility có thể yêu cầu heap fetches | Xem `Heap Fetches` |
| “COST là thời gian mili giây” | COST là đơn vị tương đối của planner | Xem actual execution time |
| “EXPLAIN ANALYZE chỉ xem kế hoạch, không chạy” | ANALYZE thực sự thực thi truy vấn | Cẩn thận đặc biệt với DML/side effect |
| “BUFFERS shared read = đọc đĩa vật lý” | Có thể qua OS cache | Đọc theo ngữ cảnh I/O |
| “Tăng work_mem toàn server chắc chắn nhanh” | Nhiều node/query đồng thời có thể dùng nhiều RAM | Đo spill và tổng memory |
| “Query nhanh trong staging thì production cũng nhanh” | Dữ liệu, stats, cache, concurrency khác | Đo trường hợp đại diện |
| “p50 giảm là người dùng hết chậm” | p95/p99 có thể do waits/cạnh tranh | Theo dõi phân phối latency |
| “READ COMMITTED là đủ cho mọi báo cáo” | Nhiều SELECT có thể thấy snapshot khác nhau | Xác định consistency requirement |
| “Read replica giảm tải mà không đổi dữ liệu nhìn thấy” | Replica có thể lag | Định nghĩa freshness/read-your-writes |
| “Materialized view luôn là bản nhanh, mới nhất” | Cần refresh/duy trì và có chi phí ghi | Theo dõi watermark và SLO |
| “DBA cần sửa mọi query chậm” | Nhiều lỗi nằm ở SQL, ORM hoặc API | Phân công theo phạm vi, đưa bằng chứng |
| “Lập trình viên có thể tự tạo index trên prod nếu SQL đúng” | DDL ảnh hưởng toàn bảng và người dùng khác | Review triển khai, rollback và monitoring |

---

## 41. Bài tập tự luyện

Các bài 1–14 dùng bộ dữ liệu PostgreSQL `lab_customers_333`, `lab_orders_333`, `lab_order_items_333` đã tạo ở mục 5. Các bài còn lại tập trung vào kế hoạch và ranh giới quản trị.

### Bài 1. Xác định lớp vấn đề

API mất 1.500 ms, nhưng truy vấn SELECT sau khi được cấp connection chỉ tốn 20 ms. Hãy liệt kê ít nhất ba thành phần ngoài câu SELECT có thể gây trễ và giải thích vì sao thêm index chưa chắc giải quyết.

### Bài 2. Projection và limit

Viết truy vấn chỉ lấy `order_id, placed_at, total_amount` của khách 1, sắp mới nhất theo `placed_at` và `order_id` giảm dần, tối đa ba đơn.

### Bài 3. Tìm đúng doanh thu PAID

Tính tổng `total_amount` theo `customer_id` chỉ với `status='PAID'`. Vì sao không cần JOIN `lab_order_items_333`?

### Bài 4. Phát hiện JOIN nhân bản

Đơn 101 có hai item, `total_amount=100`. Nếu JOIN orders với items rồi `SUM(o.total_amount)` theo khách, đóng góp của đơn 101 là bao nhiêu? Vì sao `SUM(DISTINCT o.total_amount)` không phải cách sửa tổng quát?

### Bài 5. EXISTS

Tìm các khách có ít nhất một đơn `PAID` bằng `EXISTS`, không dùng `JOIN + DISTINCT`.

### Bài 6. LEFT JOIN và COUNT

Trả mọi khách hàng cùng số đơn `PAID`, kể cả khách không có đơn `PAID`. Đặt điều kiện `status` ở đâu để giữ khách không có match?

### Bài 7. Lọc theo ngày UTC

Viết `WHERE` để chọn đơn trong **ngày UTC 2026-07-02** bằng khoảng nửa mở trên `placed_at TIMESTAMPTZ`.

### Bài 8. Viết query keyset

Lấy tối đa 20 đơn cũ hơn cursor `(placed_at='2026-07-02 10:00:00+00', order_id=102)` của khách 1, sắp ngày và ID giảm dần.

### Bài 9. Đề xuất index

Cho query lọc `customer_id`, sắp `placed_at DESC, order_id DESC`, `LIMIT 20`. Hãy đề xuất index PostgreSQL và nêu một rủi ro khi tạo nó trên bảng đơn hàng lớn.

### Bài 10. Seq Scan

Bảng chỉ có 12 hàng; query trên `status='PAID'` sử dụng `Seq Scan` mặc dù đã có index trên status. Có đủ căn cứ nói planner sai không?

### Bài 11. EXPLAIN và ANALYZE

Phân biệt `EXPLAIN` với `EXPLAIN (ANALYZE, BUFFERS)`. Nếu cần xem kế hoạch của một câu `UPDATE` trên production mà không muốn thực thi UPDATE, nên bắt đầu bằng dạng nào?

### Bài 12. Estimated/actual rows

Một node dự đoán 10 hàng nhưng thực tế trả 800.000. Nêu ba hướng điều tra trước khi yêu cầu tăng CPU/RAM.

### Bài 13. Rows và loops

Một node hiển thị `actual rows=20 loops=1000` trong PostgreSQL. Vì sao không được nói node đó chỉ xử lý 20 hàng?

### Bài 14. Partial index

Viết partial index cho những đơn `PAID` để hỗ trợ query sắp theo `placed_at DESC, order_id DESC`. Nêu một giới hạn của index.

### Bài 15. Khi nào không thêm index?

Một query lấy 98% hàng từ bảng lớn và trả nhiều cột. Vì sao planner có thể chọn Seq Scan ngay cả khi có index?

### Bài 16. N+1

Ứng dụng chạy 1 câu lấy 100 khách và 100 câu lấy đơn của từng khách. Hãy đề xuất ít nhất hai phương án giảm round trip, đồng thời tránh lấy quá nhiều đơn khi chỉ cần top 3 mỗi khách.

### Bài 17. Chờ khóa

Một UPDATE theo khóa chính có kế hoạch đơn giản nhưng mất 30 giây khi transaction khác chưa commit trên cùng hàng. Đây có phải bằng chứng cần index mới không? Nhóm nào cần phối hợp?

### Bài 18. Tải ghi và index

Có đề xuất tạo năm index mới cho một bảng ghi 10.000 hàng/phút để tăng tốc một báo cáo chạy một lần/ngày. Bạn cần thu thập những chỉ số và rủi ro nào trước khi đồng ý?

### Bài 19. Query chậm theo tham số

Cùng SQL `WHERE customer_id=?` chạy nhanh cho khách có 5 đơn, chậm cho khách có 5 triệu đơn. Nêu khái niệm **data skew**, vấn đề generic/custom plan và kế hoạch đo.

### Bài 20. Cải thiện p95 nhưng không làm tăng rủi ro hệ thống

API có p95 cao do cả query scan và connection pool wait. Hãy nêu kế hoạch đo/cải thiện theo hai lớp, không chỉ thay index.

### Bài 21. DDL production

Vì sao `CREATE INDEX CONCURRENTLY` không phải lệnh “không rủi ro”? Nó có chạy bên trong transaction block như CREATE INDEX thông thường không?

### Bài 22. Nói chuyện với DBA/SRE

Viết một yêu cầu điều tra kỹ thuật ngắn cho query chậm, gồm: triệu chứng, SQL shape, số liệu, estimated/actual rows, giả thuyết, đề xuất và rủi ro.

### Bài 23. Chọn công cụ đúng DBMS

Nêu một công cụ xem kế hoạch của PostgreSQL, MySQL, SQL Server, Oracle và SQLite. Vì sao không copy cú pháp `EXPLAIN (ANALYZE, BUFFERS)` sang mọi hệ?

### Bài 24. Ranh giới tối ưu và kiến trúc

Dashboard chạy 100 lần/phút một báo cáo phải tổng hợp 100 triệu sự kiện; dữ liệu được phép trễ 5 phút. Khi nào nên cân nhắc materialized view/cache/pre-aggregation? Phải bổ sung những cam kết nào ngoài thời gian SELECT?

---

## 42. Gợi ý lời giải

### Bài 1

Các thành phần có thể gồm:

- Chờ lấy connection từ pool.
- ORM chạy nhiều query (N+1), chờ network round trip.
- Đọc và chuyển đổi nhiều object rồi serialize JSON.
- Chờ lock hoặc batch khác ở thời điểm thực tế.
- Cache, backend logic hoặc network response.

Cần đo **phân rã thời gian request** trước khi kết luận index sẽ giảm 1.500 ms.

### Bài 2

```sql
SELECT order_id, placed_at, total_amount
FROM lab_orders_333
WHERE customer_id = 1
ORDER BY placed_at DESC, order_id DESC
LIMIT 3;
```

Theo dữ liệu lab, ba đơn mới nhất của khách 1 theo thứ tự này là **111, 109, 103**. Bài này không lọc trạng thái, nên đơn 103 `DRAFT` vẫn được lấy.

### Bài 3

```sql
SELECT customer_id,
       SUM(total_amount) AS paid_revenue
FROM lab_orders_333
WHERE status = 'PAID'
GROUP BY customer_id
ORDER BY customer_id;
```

Kết quả **1→365, 2→120, 3→120, 4→30**. `total_amount` đã ở grain **một đơn**, nên JOIN item có thể nhân bản tổng.

### Bài 4

Đơn 101 có hai item, nên `SUM(o.total_amount)` sau JOIN có thể cộng **100 hai lần = 200** cho riêng đơn đó.

`SUM(DISTINCT o.total_amount)` chỉ cộng các **giá trị tiền khác nhau**, nên nếu có hai đơn thật cùng trị giá 100, nó lại bỏ mất một đóng góp. Sửa bằng cách tổng hợp ở đúng grain và chỉ JOIN khi cần.

### Bài 5

```sql
SELECT c.customer_id, c.customer_name
FROM lab_customers_333 AS c
WHERE EXISTS (
    SELECT 1
    FROM lab_orders_333 AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
)
ORDER BY c.customer_id;
```

Bộ dữ liệu lab có cả bốn khách có ít nhất một đơn PAID.

### Bài 6

```sql
SELECT c.customer_id,
       c.customer_name,
       COUNT(o.order_id) AS paid_orders
FROM lab_customers_333 AS c
LEFT JOIN lab_orders_333 AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID'
GROUP BY c.customer_id, c.customer_name
ORDER BY c.customer_id;
```

Đặt điều kiện nguồn PAID ở **ON** để giữ khách không khớp; dùng `COUNT(o.order_id)`, không dùng `COUNT(*)` để đếm hàng đơn thật sau LEFT JOIN.

### Bài 7

```sql
WHERE placed_at >= TIMESTAMPTZ '2026-07-02 00:00:00+00'
  AND placed_at <  TIMESTAMPTZ '2026-07-03 00:00:00+00'
```

Đây là phạm vi ngày **UTC** với ranh giới nửa mở, phù hợp cả timestamp có phần giây lẻ.

### Bài 8

```sql
SELECT order_id, placed_at, total_amount
FROM lab_orders_333
WHERE customer_id = 1
  AND (placed_at, order_id) <
      (
        TIMESTAMPTZ '2026-07-02 10:00:00+00',
        102
      )
ORDER BY placed_at DESC, order_id DESC
LIMIT 20;
```

Phải giữ đúng thứ tự hai cột và khóa phá hòa để cursor có nghĩa.

### Bài 9

```sql
CREATE INDEX lab_orders_333_customer_recent_idx
ON lab_orders_333 (
    customer_id,
    placed_at DESC,
    order_id DESC
);
```

Index phù hợp với lọc bằng customer và sort mới nhất. Trên production, phải xét tải ghi, dung lượng, index hiện có, thời gian DDL, khóa và replication lag trước khi triển khai.

### Bài 10

Không. Trên 12 hàng, chi phí Seq Scan thường nhỏ. Optimizer có thể chọn quét toàn bộ bảng hợp lý hơn index. Cần đo actual time và điều kiện workload.

### Bài 11

`EXPLAIN` thường chỉ tạo kế hoạch ước lượng. `EXPLAIN (ANALYZE, BUFFERS)` **thực thi** câu SQL, đo số hàng/time/buffers.

Để xem kế hoạch của UPDATE mà **không thực thi**, bắt đầu bằng `EXPLAIN UPDATE ...` (không ANALYZE), đồng thời đánh giá quyền và tác dụng tiềm tàng của các biểu thức theo ngữ cảnh.

### Bài 12

Ba hướng:

1. Xem thống kê có cũ hoặc phân bố dữ liệu lệch không.
2. Kiểm tra predicate/JOIN có thiếu khóa hoặc nhân bản hàng không.
3. Xem correlation, data skew, tham số prepared plan và biểu thức khiến ước lượng sai.

Cần xem cả node downstream và tải tài nguyên; không kết luận thiếu RAM chỉ từ chênh lệch rows.

### Bài 13

`actual rows` có thể là giá trị **trung bình mỗi vòng** khi node được lặp. `20 × 1000` gợi ý khoảng **20.000** hàng được trả cộng dồn từ node đó, không chỉ 20.

### Bài 14

```sql
CREATE INDEX lab_orders_333_paid_recent_idx
ON lab_orders_333 (placed_at DESC, order_id DESC)
WHERE status = 'PAID';
```

Nó không bao phủ đơn `DRAFT`; query/parameter phải có điều kiện phù hợp để planner có thể dùng index. Thêm index cũng có chi phí ghi và dung lượng.

### Bài 15

Nếu cần đọc 98% hàng và nhiều cột, index scan có thể phải tra nhiều heap pages và tốn random I/O; Seq Scan có thể rẻ hơn. Có index không bắt buộc phải dùng index.

### Bài 16

Hai hướng:

- Batch query theo nhiều `customer_id` và nhóm kết quả ở ứng dụng.
- Dùng `ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY placed_at DESC, order_id DESC)` rồi lọc `rn <= 3`.

Có thể xem xét `LATERAL` lấy top 3 cho từng khách nếu index/workload phù hợp. Mục tiêu là giảm round trip **và** không tải dư lịch sử.

### Bài 17

Không. Khi UPDATE theo khóa chính phải **chờ khóa hàng**, index có thể đã hoàn toàn phù hợp. Cần điều tra transaction giữ khóa, thời gian mở transaction, thứ tự ghi và contention cùng DBA/SRE hoặc owner luồng ghi.

### Bài 18

Cần đo:

- Tần suất/latency báo cáo cần tối ưu.
- Tổng số và kích thước index hiện tại.
- TPS ghi, latency INSERT/UPDATE/DELETE, WAL/I/O.
- Tỷ lệ truy vấn được hưởng lợi, kế hoạch và actual buffers.
- Dung lượng dự phòng, thời gian DDL, lock/replication lag.
- Cách rollback nếu index không đem lại hiệu quả.

Năm index mới cho một báo cáo ít dùng có thể gây chi phí toàn hệ lớn hơn lợi ích.

### Bài 19

**Data skew:** số hàng theo customer không đều. Một plan lý tưởng cho khách 5 đơn có thể khác cho khách 5 triệu đơn.

So sánh cùng query với các tham số đại diện, estimated/actual rows, index usage, generic/custom plan behavior và p95/p99 dưới tải. Giữ parameterization an toàn, tránh thay literal tùy tiện chỉ để ép plan.

### Bài 20

Tách hai dòng thời gian:

1. Đo **database execution time** và buffer/plan; sửa query scan dư, index phù hợp nếu có bằng chứng.
2. Đo **pool wait time**, transaction duration, số connection, N+1 và concurrency; xử lý leak/giới hạn pool hoặc workload.

Dùng p95/p99 API sau khi thay đổi để xác minh lợi ích tổng, không chỉ số miligiây trong `EXPLAIN`.

### Bài 21

`CREATE INDEX CONCURRENTLY` có thể dùng CPU/I/O, chiếm dung lượng, chờ transaction và để lại index INVALID khi thất bại. Nó **không chạy trong transaction block thông thường**. Vì vậy cần migration kế hoạch, giám sát và xử lý sự cố; không tự chạy trong giờ cao điểm.

### Bài 22

Một đề xuất có thể viết:

> Query lấy 20 đơn gần nhất cho khách đang có p95 khoảng 900 ms trên production, trước đây 120 ms. Bảng có khoảng 40 triệu đơn. Kế hoạch trên tham số chậm cho thấy số hàng thực lớn hơn ước lượng và sort nhiều hàng. Giả thuyết: thiếu index phục vụ `customer_id` + thứ tự `placed_at`/`order_id`. Đề xuất DBA cùng đánh giá `(customer_id, placed_at DESC, order_id DESC)`, so sánh p95, actual buffers và chi phí ghi. Rủi ro gồm disk, DDL concurrency và replication lag; cần plan rollback.

Đây là tình huống giả định, nhưng đầy đủ **triệu chứng → bằng chứng → giả thuyết → giải pháp → rủi ro**.

### Bài 23

- PostgreSQL: `EXPLAIN` và `EXPLAIN (ANALYZE, BUFFERS)`.
- MySQL: `EXPLAIN` hoặc `EXPLAIN ANALYZE` khi hỗ trợ.
- SQL Server: estimated/actual execution plan, `SET STATISTICS IO`.
- Oracle: `EXPLAIN PLAN` hoặc `DBMS_XPLAN.DISPLAY_CURSOR` theo quyền.
- SQLite: `EXPLAIN QUERY PLAN`.

Cú pháp và thông tin runtime/estimated khác nhau nên không thể copy từng từ giữa DBMS.

### Bài 24

Khi cùng một phép tổng hợp nặng được gọi thường xuyên và **độ trễ cho phép 5 phút**, có thể cân nhắc materialized view, bảng tổng hợp hoặc cache để giảm quét nguồn.

Nhưng phải thiết kế:

- Chu kỳ/cơ chế refresh và lúc công bố.
- `source_watermark` hoặc `as_of`, độ trễ nguồn→hiển thị.
- Cách xử lý update/delete/late-arriving data.
- Atomic publish khi job lỗi và theo dõi retry.
- Quyền truy cập, phân tách tenant, kiểm tra chất lượng dữ liệu.
- Tổng chi phí ghi/tính toán/refresh và rủi ro stale.

Đó là quyết định ở **cấp hệ thống**, không phải chỉ thay một JOIN để query chạy nhanh.

---

## 43. Danh sách quyết định khi gặp truy vấn chậm

Thay vì bắt đầu bằng “index nào?”, hãy tự trả lời:

1. **Query hiện có đúng ngữ nghĩa không?** Đúng khóa, grain, NULL, OUTER JOIN, phân quyền và thứ tự?
2. **API cần bao nhiêu dữ liệu?** Có `SELECT *`, N+1, OFFSET sâu hoặc trả quá nhiều hàng không?
3. **Đơn vị đo nào đang chậm?** API, pool wait, database execution, network hay serialize?
4. **Chậm với tham số nào?** Có data skew, bảng tăng trưởng hoặc trường hợp hiếm không?
5. **EXPLAIN cho thấy gì?** Scan, filter, join, sort, loops, estimated/actual rows và buffer usage?
6. **Index hiện có là gì?** Có đáp ứng lọc, thứ tự và projection chưa?
7. **Một index mới ảnh hưởng ghi ra sao?** Chi phí dung lượng, WAL, migration, lock và các truy vấn khác?
8. **Có chờ khóa hoặc tài nguyên toàn hệ không?** Nếu có, đừng chỉ rewrite SQL.
9. **Độ mới và consistency có thay đổi không?** Cache/materialized view/replica không phải nguồn đọc tương đương tuyệt đối.
10. **Có thể chứng minh cải thiện và quay lại được không?** Đo trên workload đại diện, review, giám sát p95/p99 và plan rollback.

### Kết luận

**Ranh giới giữa viết SQL hiệu quả và quản trị hiệu năng chuyên sâu nằm ở phạm vi bằng chứng và phạm vi tác động.** Người viết SQL nên chịu trách nhiệm diễn đạt đúng nghiệp vụ, giảm công việc dư thừa, hiểu chỉ mục cơ bản và đọc kế hoạch đủ để đưa ra giả thuyết có căn cứ. Khi lời giải đụng tới **thống kê toàn hệ, khóa, I/O, bộ nhớ, WAL, autovacuum, partitioning, replica, migration index lớn hoặc phân phối tài nguyên giữa nhiều workload**, cần phối hợp nhóm quản trị hiệu năng và vận hành.

Tối ưu SQL tốt không phải là ép mọi truy vấn dùng index hoặc làm một lần `EXPLAIN` trông đẹp hơn. Đó là quá trình **giữ kết quả đúng, đo đúng vấn đề, chọn thay đổi có tác động hợp lý, kiểm chứng dưới dữ liệu thật và triển khai an toàn**.
