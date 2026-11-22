# Tra cứu đơn hàng với lọc, sắp xếp và phân trang ổn định

Một màn hình quản trị đơn hàng thường cho phép người dùng chọn trạng thái, khoảng ngày, khách hàng, mức tiền, nhập từ khóa, đổi cột sắp xếp và chuyển qua nhiều trang. Truy vấn đầu tiên có thể rất đơn giản:

```sql
SELECT *
FROM orders;
```

Nhưng khi bảng có hàng triệu đơn, nhiều người dùng tìm kiếm cùng lúc và đơn hàng vẫn được tạo/cập nhật liên tục, một câu truy vấn thiếu thiết kế có thể gây ra nhiều vấn đề:

- Người dùng chuyển trang nhưng thấy đơn hàng lặp lại hoặc bị bỏ sót.
- Các dòng có cùng `created_at` đổi thứ tự giữa hai lần truy vấn.
- Tham số sort bị nối trực tiếp vào SQL và tạo lỗ hổng injection.
- Bộ lọc ngày lấy thiếu giao dịch ở cuối ngày.
- JOIN với bảng chi tiết làm một đơn xuất hiện nhiều lần.
- `COUNT(*)` đếm dòng join thay vì đếm đơn hàng.
- `OFFSET` lớn khiến database phải đọc và bỏ qua rất nhiều dòng.
- Request thứ hai có dữ liệu mới làm ranh giới giữa các trang bị dịch chuyển.

Bài học **“Tra cứu đơn hàng với lọc, sắp xếp và phân trang ổn định”**, thuộc chương **Thực hành tổng hợp** của module **Database SQL**, xây dựng một quy trình tra cứu từ schema đến SQL, JDBC và API. Ví dụ chính dùng PostgreSQL; các phần so sánh chỉ rõ cách viết phân trang trên MySQL, SQL Server, SQLite và Oracle.

Sau bài học, bạn sẽ biết cách:

1. Thiết kế bộ lọc tùy chọn nhưng vẫn bind parameter an toàn.
2. Xác định khoảng ngày/giờ chính xác và có timezone rõ ràng.
3. Chỉ cho phép các trường sắp xếp nằm trong whitelist.
4. Tạo thứ tự xác định bằng khóa phụ duy nhất.
5. Chọn giữa `LIMIT/OFFSET` và keyset/cursor pagination.
6. Tránh JOIN làm nhân bản đơn hàng và đếm sai tổng số.
7. Xử lý dữ liệu thay đổi trong lúc người dùng chuyển trang.
8. Thiết kế index, kiểm tra execution plan và triển khai repository JDBC.

> **Quy tắc quan trọng nhất:** Một trang kết quả ổn định cần một thứ tự toàn phần (*total order*). Nếu sắp xếp theo `created_at`, hãy thêm một khóa duy nhất như `order_id` làm tie-breaker. Phân trang không thể ổn định nếu database được phép trả các dòng bằng nhau theo thứ tự bất kỳ.

## 1. Bài toán và hợp đồng tra cứu

Giả sử trang quản trị có các bộ lọc:

| Tham số | Ý nghĩa | Ví dụ |
|---|---|---|
| `status` | Trạng thái đơn | `PAID` |
| `customerId` | Khách hàng | `1024` |
| `createdFrom` | Thời điểm bắt đầu, inclusive | `2026-11-01T00:00:00+07:00` |
| `createdTo` | Thời điểm kết thúc, exclusive | `2026-12-01T00:00:00+07:00` |
| `minAmount` | Tổng tiền tối thiểu | `100.00` |
| `maxAmount` | Tổng tiền tối đa | `5000.00` |
| `keyword` | Từ khóa đơn hàng | `INV-2026` |
| `sort` | Trường và hướng sắp xếp | `createdAt,desc` |
| `pageSize` | Số dòng tối đa trong trang | `25` |
| `page` hoặc `cursor` | Vị trí trang | `0` hoặc token tiếp theo |

Một request tìm đơn đã thanh toán trong tháng 11, giá từ 100 đến 5000, sắp xếp mới nhất:

```text
GET /orders?status=PAID
    &createdFrom=2026-11-01T00:00:00%2B07:00
    &createdTo=2026-12-01T00:00:00%2B07:00
    &minAmount=100
    &maxAmount=5000
    &sort=createdAt,desc
    &pageSize=25
    &page=0
```

Ở tầng API, nên thống nhất các quy tắc:

- `page` bắt đầu từ 0 hay 1; chọn một cách và ghi rõ.
- `pageSize` có giới hạn tối đa, ví dụ 100.
- `createdFrom` và `createdTo` có semantics inclusive/exclusive rõ ràng.
- `sort` chỉ nhận các giá trị được hỗ trợ.
- Khi dùng cursor, cursor phải gắn với bộ lọc và sort tương ứng.
- Tenant/user scope được lấy từ ngữ cảnh xác thực, không tin một `tenantId` tùy ý từ query string.

## 2. Schema thực hành

Ví dụ dùng PostgreSQL. `created_at` là thời điểm tuyệt đối (`TIMESTAMPTZ`) và `order_id` là khóa duy nhất. Hai thuộc tính này sẽ tạo thứ tự ổn định.

### 2.1. Bảng khách hàng

```sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_name VARCHAR(160) NOT NULL,
    email VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tenant_id, customer_id)
);
```

### 2.2. Bảng đơn hàng

```sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    customer_id BIGINT NOT NULL,
    order_number VARCHAR(40) NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount NUMERIC(14,2) NOT NULL,
    currency_code CHAR(3) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMPTZ,
    CONSTRAINT uq_orders_tenant_number
        UNIQUE (tenant_id, order_number),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customers(tenant_id, customer_id),
    CONSTRAINT ck_orders_status
        CHECK (status IN (
            'PENDING', 'PAID', 'PROCESSING',
            'SHIPPED', 'DELIVERED', 'CANCELLED'
        )),
    CONSTRAINT ck_orders_amount
        CHECK (total_amount >= 0)
);
```

Thiết kế dùng khóa ngoại ghép `(tenant_id, customer_id)` để một đơn thuộc về khách hàng trong cùng tenant. Query vẫn phải lọc tenant; khóa ngoại không thay thế authorization.

### 2.3. Bảng chi tiết đơn hàng

```sql
CREATE TABLE order_items (
    order_item_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    product_id BIGINT NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(14,2) NOT NULL CHECK (unit_price >= 0)
);
```

Một đơn có thể có nhiều dòng chi tiết. Điều này quan trọng khi tra cứu theo sản phẩm: JOIN trực tiếp `orders` với `order_items` có thể làm một đơn xuất hiện nhiều lần.

### 2.4. Dữ liệu mẫu

```sql
INSERT INTO customers
    (customer_id, tenant_id, customer_name, email)
VALUES
    (101, 1, 'An Nguyen', 'an@example.test'),
    (102, 1, 'Binh Tran', 'binh@example.test'),
    (103, 1, 'Chi Le', 'chi@example.test'),
    (201, 2, 'Customer Other Tenant', 'other@example.test');

INSERT INTO orders
    (order_id, tenant_id, customer_id, order_number,
     status, total_amount, currency_code, created_at)
VALUES
    (1001, 1, 101, 'INV-2026-001', 'PAID',       250.00, 'VND', '2026-11-14 09:00:00+07'),
    (1002, 1, 102, 'INV-2026-002', 'PENDING',    120.00, 'VND', '2026-11-14 09:00:00+07'),
    (1003, 1, 101, 'INV-2026-003', 'SHIPPED',    900.00, 'VND', '2026-11-13 15:30:00+07'),
    (1004, 1, 103, 'INV-2026-004', 'CANCELLED',   75.00, 'VND', '2026-11-12 08:10:00+07'),
    (1005, 1, 102, 'INV-2026-005', 'PAID',      1250.00, 'VND', '2026-11-11 11:20:00+07'),
    (2001, 2, 201, 'INV-OTHER-001', 'PAID',      999.00, 'VND', '2026-11-14 10:00:00+07');

INSERT INTO order_items
    (order_item_id, order_id, product_id, product_name, quantity, unit_price)
VALUES
    (1, 1001, 501, 'Keyboard', 1, 250.00),
    (2, 1002, 502, 'Mouse',    2,  60.00),
    (3, 1003, 501, 'Keyboard', 2, 450.00),
    (4, 1003, 503, 'Cable',    1,  20.00),
    (5, 1005, 504, 'Monitor',  1, 1250.00);
```

Hai đơn `1001` và `1002` có cùng `created_at`. Nếu chỉ `ORDER BY created_at DESC`, database không có nghĩa vụ xếp hai dòng đó theo cùng một thứ tự ở mọi lần chạy.

## 3. Bộ lọc tùy chọn

Người dùng có thể chỉ điền một vài bộ lọc. Có hai cách thường gặp để xây dựng câu SQL.

### 3.1. Cách viết điều kiện tham số có thể NULL

```sql
SELECT
    o.order_id,
    o.order_number,
    o.status,
    o.total_amount,
    o.created_at
FROM orders AS o
WHERE o.tenant_id = $1
  AND ($2 IS NULL OR o.status = $2)
  AND ($3 IS NULL OR o.customer_id = $3)
  AND ($4 IS NULL OR o.created_at >= $4)
  AND ($5 IS NULL OR o.created_at < $5)
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT $6 OFFSET $7;
```

Đây là PostgreSQL với positional parameters. Cách viết ngắn, dễ đọc và thể hiện rõ filter tùy chọn.

Tuy nhiên, điều kiện dạng:

```sql
($2 IS NULL OR o.status = $2)
```

có thể khiến optimizer khó chọn một plan tối ưu cho mọi tổ hợp tham số. Tùy DBMS, prepared statement có thể dùng generic plan hoặc custom plan; với bảng lớn và filter chọn lọc cao, cần đo thực tế.

### 3.2. Dynamic SQL có kiểm soát

Một lựa chọn là chỉ thêm predicate khi filter có giá trị:

```sql
SELECT
    o.order_id,
    o.order_number,
    o.status,
    o.total_amount,
    o.created_at
FROM orders AS o
WHERE o.tenant_id = $1
  AND o.status = $2
  AND o.created_at >= $3
  AND o.created_at < $4
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT $5 OFFSET $6;
```

Nếu request không có `status`, application không thêm `AND o.status = ...`. Giá trị vẫn được bind bằng parameter.

Dynamic SQL **không có nghĩa nối trực tiếp dữ liệu người dùng vào chuỗi SQL**. Chỉ nối các đoạn SQL cố định do code kiểm soát; mọi giá trị đều dùng placeholder.

### 3.3. Vì sao tenant filter phải luôn có?

Query trong ví dụ luôn có:

```sql
WHERE o.tenant_id = $1
```

Tenant ID phải lấy từ principal/session đã xác thực. Nếu API cho người dùng truyền `tenantId` tùy ý và query tin giá trị đó, người dùng có thể đọc đơn của tenant khác.

Ngay cả khi `order_id` là UUID khó đoán hoặc số lớn, nó không thay authorization. Phải kiểm tra quyền trên từng phạm vi dữ liệu.

## 4. Bộ lọc theo ngày giờ và timezone

Tra cứu theo ngày thường là nguồn lỗi vì cột lưu thời điểm nhưng UI gửi ngày lịch.

### 4.1. Dùng khoảng nửa mở

Muốn lấy toàn bộ đơn trong tháng 11/2026 theo giờ Việt Nam, hãy dùng:

```sql
WHERE created_at >= TIMESTAMPTZ '2026-11-01 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-12-01 00:00:00+07'
```

Khoảng này gồm thời điểm đầu tháng và loại trừ đúng thời điểm đầu tháng sau.

### 4.2. Vì sao không dùng BETWEEN cho ngày cuối?

Không nên viết:

```sql
WHERE created_at BETWEEN
      TIMESTAMP '2026-11-01 00:00:00'
  AND TIMESTAMP '2026-11-30 23:59:59';
```

Giá trị có phần microsecond sau `23:59:59` có thể bị bỏ sót. Cột có precision khác nhau giữa DBMS cũng làm việc đoán “giây cuối ngày” trở nên mong manh.

Với khoảng nửa mở:

```sql
created_at >= start_instant
AND created_at < end_instant
```

không cần đoán độ chính xác nhỏ nhất của database.

### 4.3. Tạo instant từ ngày địa phương

Nếu UI gửi ngày `2026-11-14` và nghiệp vụ hiểu là ngày ở `Asia/Ho_Chi_Minh`, application tạo:

```java
LocalDate day = LocalDate.parse("2026-11-14");
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");

OffsetDateTime from = day.atStartOfDay(zone).toOffsetDateTime();
OffsetDateTime to = day.plusDays(1)
    .atStartOfDay(zone)
    .toOffsetDateTime();
```

Sau đó bind `from` và `to` vào query `TIMESTAMPTZ`. Không dựa vào timezone mặc định của JVM hoặc database session.

### 4.4. Tránh bọc cột trong hàm ngày

```sql
-- Thường không thuận lợi cho index thường trên created_at:
WHERE DATE(created_at) = DATE '2026-11-14'
```

Ngoài vấn đề hiệu năng, với timestamp có timezone, ngày thu được còn phụ thuộc timezone dùng để chuyển instant thành ngày. Xác định ranh giới theo zone nghiệp vụ rồi so sánh trực tiếp cột thường rõ nghĩa và dễ dùng index hơn.

### 4.5. Từ đầu và tới cuối có thể bỏ trống

Nếu chỉ có `createdFrom`, dùng:

```sql
created_at >= ?
```

Nếu chỉ có `createdTo`, dùng:

```sql
created_at < ?
```

Không tự đặt ngày kết thúc mặc định mà người dùng không biết; hãy định nghĩa default trong hợp đồng API.

## 5. Lọc theo trạng thái, số tiền và từ khóa

### 5.1. Trạng thái

```sql
AND o.status = $2
```

Nếu người dùng chọn nhiều trạng thái:

```sql
AND o.status = ANY($2::varchar[])
```

Đây là cú pháp PostgreSQL. Cách portable hơn là tạo số placeholder tương ứng với số phần tử trong `IN (?, ?, ...)`, không nối giá trị thô vào SQL.

Nếu danh sách trạng thái rỗng, cần định nghĩa semantics:

- Không có filter trạng thái.
- Hoặc kết quả rỗng vì người dùng chủ động chọn “không trạng thái nào”.

Đừng để danh sách rỗng vô tình tạo SQL sai hoặc bỏ mất filter bảo mật.

### 5.2. Khoảng tiền

```sql
AND o.total_amount >= $2
AND o.total_amount < $3
```

Nếu nghiệp vụ muốn biên trên inclusive, có thể dùng `<=`. Hãy thống nhất UI và API. Với tiền, dùng `BigDecimal` trong Java và `NUMERIC/DECIMAL` trong database.

### 5.3. Từ khóa prefix

```sql
AND o.order_number LIKE $2
```

Application có thể bind `"INV-2026%"`. Nếu cho người dùng nhập ký tự `%` hoặc `_` theo nghĩa literal, cần escape wildcard và dùng `ESCAPE` rõ ràng.

### 5.4. Tìm kiếm chứa chuỗi

```sql
AND o.order_number ILIKE $2
```

`ILIKE` là PostgreSQL extension, không portable. MySQL/SQL Server/Oracle có collation hoặc hàm riêng. Tìm kiếm dạng `%keyword%` thường không dùng B-tree index thông thường hiệu quả; cân nhắc full-text/trigram/search service theo nhu cầu.

### 5.5. Lọc sản phẩm trong đơn mà không nhân bản order

Muốn tìm các đơn có sản phẩm `501`, không nhất thiết JOIN trực tiếp rồi DISTINCT:

```sql
SELECT o.order_id, o.order_number, o.status
FROM orders AS o
WHERE o.tenant_id = $1
  AND EXISTS (
      SELECT 1
      FROM order_items AS i
      WHERE i.order_id = o.order_id
        AND i.product_id = $2
  );
```

`EXISTS` kiểm tra có ít nhất một item phù hợp, nhưng mỗi đơn chỉ xuất hiện một lần.

## 6. Sắp xếp phải an toàn và xác định

Sắp xếp không chỉ là `ORDER BY` theo cột người dùng chọn. Để phân trang đúng, thứ tự phải xác định và không được phép biến thành SQL injection.

### 6.1. Không bind tên cột bằng placeholder

Đoạn sau không làm điều bạn mong muốn:

```sql
SELECT *
FROM orders
ORDER BY ?;
```

Parameter đại diện cho **giá trị**, không phải identifier. Driver thường coi `?` là một giá trị hằng, không thay nó bằng tên cột.

### 6.2. Không nối trực tiếp sort từ request

Không làm:

```java
String sql = "SELECT ... ORDER BY " + request.sort();
```

Người dùng có thể gửi nội dung SQL thay cho tên cột/hướng sort. `PreparedStatement` không bảo vệ phần identifier được nối chuỗi.

### 6.3. Dùng whitelist

Java:

```java
enum OrderSort {
    CREATED_AT,
    TOTAL_AMOUNT,
    ORDER_NUMBER
}

enum SortDirection {
    ASC,
    DESC
}
```

Map enum sang đoạn SQL cố định:

```java
String sortExpression = switch (sort) {
    case CREATED_AT -> "o.created_at";
    case TOTAL_AMOUNT -> "o.total_amount";
    case ORDER_NUMBER -> "o.order_number";
};

String directionSql = switch (direction) {
    case ASC -> "ASC";
    case DESC -> "DESC";
};
```

Chỉ các chuỗi hằng trong code được đưa vào SQL. Nếu parse sort không hợp lệ, trả validation error hoặc dùng default đã công bố.

### 6.4. Thêm tie-breaker duy nhất

Không ổn định:

```sql
ORDER BY o.created_at DESC
```

Ổn định hơn:

```sql
ORDER BY o.created_at DESC, o.order_id DESC
```

`created_at` có thể trùng, nhưng `order_id` là primary key nên toàn bộ thứ tự là xác định tại một snapshot.

Với sort tiền:

```sql
ORDER BY o.total_amount DESC, o.order_id DESC
```

Với sort mã đơn:

```sql
ORDER BY o.order_number ASC, o.order_id ASC
```

Hướng tie-breaker phải được quy định. Không đổi tie-breaker tùy tiện giữa các request của cùng một cursor.

### 6.5. Thứ tự ổn định không có nghĩa dữ liệu không thay đổi

`ORDER BY created_at DESC, order_id DESC` bảo đảm một thứ tự xác định cho tập dữ liệu đang được query. Nếu có đơn mới hoặc một đơn bị xóa giữa hai request, tập dữ liệu đã thay đổi. Thứ tự xác định không tự tạo snapshot nhất quán xuyên nhiều HTTP request.

## 7. NULL trong ORDER BY

Nếu cột sort có thể NULL, vị trí NULL khác nhau giữa DBMS và hướng sort.

### 7.1. PostgreSQL

```sql
ORDER BY shipped_at DESC NULLS LAST, order_id DESC
```

PostgreSQL cho phép `NULLS FIRST`/`NULLS LAST`.

### 7.2. MySQL và SQLite

Thứ tự NULL được quy định theo semantics riêng của DBMS; nếu muốn hành vi rõ ràng, dùng biểu thức sort:

```sql
ORDER BY
    CASE WHEN shipped_at IS NULL THEN 1 ELSE 0 END ASC,
    shipped_at DESC,
    order_id DESC
```

### 7.3. SQL Server

SQL Server không dùng cú pháp `NULLS LAST` trong `ORDER BY`; có thể dùng `CASE` tương tự:

```sql
ORDER BY
    CASE WHEN shipped_at IS NULL THEN 1 ELSE 0 END ASC,
    shipped_at DESC,
    order_id DESC
```

### 7.4. Cursor với sort key nullable

Keyset pagination trên cột nullable phức tạp hơn vì so sánh với NULL cho kết quả UNKNOWN. Nếu có thể, hãy:

- Chọn sort key `NOT NULL`, ví dụ `created_at`.
- Hoặc đưa null-rank vào thứ tự và cursor.
- Viết predicate seek tương ứng từng nhánh NULL/non-NULL.

Không viết `shipped_at < ?` rồi kỳ vọng nó tự bao gồm các dòng NULL.

## 8. LIMIT/OFFSET pagination

Offset pagination là cách phân trang quen thuộc, phù hợp cho giao diện cần nhảy đến một số trang bất kỳ.

### 8.1. Công thức

Với page index bắt đầu từ 0:

\[
\text{offset} = \text{page} \times \text{pageSize}
\]

Ví dụ `page=3`, `pageSize=25`:

\[
3 \times 25 = 75
\]

Database bỏ qua 75 dòng đầu rồi trả 25 dòng tiếp theo.

### 8.2. PostgreSQL

```sql
SELECT
    o.order_id,
    o.order_number,
    o.status,
    o.total_amount,
    o.created_at,
    c.customer_name
FROM orders AS o
JOIN customers AS c
    ON c.tenant_id = o.tenant_id
   AND c.customer_id = o.customer_id
WHERE o.tenant_id = $1
  AND o.deleted_at IS NULL
  AND o.status = $2
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT $3 OFFSET $4;
```

`LIMIT` là số dòng tối đa; `OFFSET` là số dòng bỏ qua.

### 8.3. Tính offset an toàn

Không để integer overflow:

```java
long offset = Math.multiplyExact((long) page, pageSize);
```

Validate `page >= 0`, `pageSize >= 1` và `pageSize <= MAX_PAGE_SIZE`. Không nhận pageSize hàng triệu từ client.

### 8.4. COUNT tổng số kết quả

```sql
SELECT COUNT(*)
FROM orders AS o
WHERE o.tenant_id = $1
  AND o.deleted_at IS NULL
  AND o.status = $2;
```

Count phải dùng **cùng tập điều kiện lọc** với query lấy trang. Không có `ORDER BY`, `LIMIT` hoặc `OFFSET`.

### 8.5. Hai query có thể nhìn hai snapshot khác nhau

Nếu count và select chạy ở hai transaction/request khác nhau, dữ liệu có thể thay đổi giữa chúng. UI có thể hiển thị `total=101` nhưng trang lấy ra từ tập có 102 dòng. Với màn hình tra cứu thông thường, sai lệch nhỏ có thể chấp nhận; nếu cần count và page nhất quán tuyệt đối, phải xác định isolation/snapshot và chi phí.

## 9. Cú pháp phân trang giữa các DBMS

| DBMS | Cú pháp phổ biến |
|---|---|
| PostgreSQL | `LIMIT n OFFSET m` |
| MySQL | `LIMIT m, n` hoặc `LIMIT n OFFSET m` |
| SQLite | `LIMIT n OFFSET m` |
| SQL Server | `ORDER BY ... OFFSET m ROWS FETCH NEXT n ROWS ONLY` |
| Oracle 12c+ | `ORDER BY ... OFFSET m ROWS FETCH NEXT n ROWS ONLY` |

### 9.1. SQL Server

```sql
SELECT
    o.order_id,
    o.order_number,
    o.status,
    o.total_amount,
    o.created_at
FROM dbo.orders AS o
WHERE o.tenant_id = @tenant_id
  AND o.deleted_at IS NULL
ORDER BY o.created_at DESC, o.order_id DESC
OFFSET @offset ROWS
FETCH NEXT @page_size ROWS ONLY;
```

SQL Server yêu cầu `ORDER BY` khi dùng `OFFSET/FETCH`.

### 9.2. MySQL

```sql
SELECT
    o.order_id,
    o.order_number,
    o.status,
    o.total_amount,
    o.created_at
FROM orders AS o
WHERE o.tenant_id = ?
  AND o.deleted_at IS NULL
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT ? OFFSET ?;
```

Hoặc:

```sql
LIMIT offset_value, row_count
```

Thứ tự hai tham số trong dạng dấu phẩy là offset trước, count sau.

### 9.3. SQLite

```sql
SELECT order_id, order_number, status, total_amount, created_at
FROM orders
WHERE tenant_id = ?
ORDER BY created_at DESC, order_id DESC
LIMIT ? OFFSET ?;
```

### 9.4. Oracle 12c+

```sql
SELECT
    order_id,
    order_number,
    status,
    total_amount,
    created_at
FROM orders
WHERE tenant_id = :tenant_id
ORDER BY created_at DESC, order_id DESC
OFFSET :offset ROWS
FETCH NEXT :page_size ROWS ONLY;
```

Với Oracle cũ hơn, thường gặp các mẫu dùng `ROWNUM` hoặc analytic `ROW_NUMBER()`. Không dùng cú pháp 12c+ nếu hệ thống triển khai trên phiên bản cũ.

## 10. Vấn đề của OFFSET khi dữ liệu thay đổi

Giả sử thứ tự giảm dần:

```text
Trang 1 (pageSize=3)
100  99  98

Trang 2
97   96  95
```

Người dùng đọc trang 1. Trước khi họ gọi trang 2, một đơn mới `101` được tạo và đứng đầu:

```text
Thứ tự mới:
101 100 99 98 97 96 95
```

Query trang 2 với `OFFSET 3` trả:

```text
98 97 96
```

Đơn `98` bị lặp lại vì vị trí của nó đã dịch chuyển.

Nếu một dòng bị xóa trước offset, trang sau có thể bỏ sót một dòng. Vì vậy:

- `ORDER BY` ổn định giải quyết tie/không xác định trong một snapshot.
- `OFFSET` vẫn nhạy với insert/delete/update xảy ra trước vị trí offset giữa các request.
- Với bảng thay đổi liên tục và trang sâu, keyset pagination thường phù hợp hơn.

## 11. Keyset pagination (seek pagination)

Keyset pagination dùng **giá trị của dòng cuối trang hiện tại** làm mốc để tìm dòng kế tiếp, thay vì đếm số dòng cần bỏ qua.

Giả sử thứ tự:

```sql
ORDER BY created_at DESC, order_id DESC
```

Trang đầu:

```sql
SELECT
    order_id, order_number, status, created_at
FROM orders
WHERE tenant_id = $1
  AND deleted_at IS NULL
ORDER BY created_at DESC, order_id DESC
LIMIT $2;
```

Giả sử dòng cuối trang có:

```text
created_at = 2026-11-14 09:00:00+07
order_id   = 1001
```

### 11.1. Predicate cho trang kế tiếp

Vì thứ tự giảm dần, dòng tiếp theo phải **nhỏ hơn** cặp khóa cursor:

```sql
SELECT
    order_id, order_number, status, created_at
FROM orders
WHERE tenant_id = $1
  AND deleted_at IS NULL
  AND (
      created_at < $2
      OR (
          created_at = $2
          AND order_id < $3
      )
  )
ORDER BY created_at DESC, order_id DESC
LIMIT $4;
```

Đây là điều kiện lexicographic cho hai cột sort.

### 11.2. Vì sao phải có order_id?

Hai đơn có thể cùng `created_at`. Nếu cursor chỉ chứa timestamp, predicate:

```sql
created_at < $cursor_created_at
```

sẽ bỏ qua những đơn khác có cùng timestamp nhưng nằm sau dòng cuối trang. Thêm `order_id` làm tie-breaker tạo ranh giới chính xác:

```sql
created_at < cursor_time
OR (created_at = cursor_time AND order_id < cursor_id)
```

### 11.3. Row-value comparison trong PostgreSQL

Với các cột không NULL và cùng hướng sort giảm dần, PostgreSQL có thể viết ngắn:

```sql
AND (created_at, order_id) < ($2, $3)
```

Điều kiện này tương đương phép so sánh tuple theo thứ tự từ trái sang phải. Dạng OR tường minh dễ chuyển đổi và giải thích hơn cho nhiều DBMS.

### 11.4. Trang đầu không có cursor

Trang đầu không thêm seek predicate. Không nên dùng cursor giả như timestamp 1970 hoặc ID 0 vì có thể loại nhầm dữ liệu hợp lệ.

### 11.5. Lấy thêm một dòng để biết còn trang sau

Nếu page size là 25, query lấy 26 dòng:

```sql
LIMIT 26
```

Nếu nhận 26:

- Trả 25 dòng đầu.
- `hasNext = true`.
- Cursor tiếp theo lấy từ dòng thứ 25, tức dòng cuối **được trả về**.

Nếu nhận tối đa 25:

- Trả tất cả.
- `hasNext = false`.

Không tạo cursor từ dòng dư thứ 26; nếu làm vậy, trang kế tiếp sẽ bỏ qua dòng đó.

## 12. Keyset với thứ tự tăng dần và nhiều cột

Với:

```sql
ORDER BY created_at ASC, order_id ASC
```

predicate trang tiếp theo đổi thành:

```sql
created_at > $cursor_time
OR (
    created_at = $cursor_time
    AND order_id > $cursor_id
)
```

Với thứ tự trộn chiều:

```sql
ORDER BY total_amount DESC, created_at ASC, order_id ASC
```

predicate trang sau phải phản ánh từng chiều:

```sql
total_amount < $amount
OR (
    total_amount = $amount
    AND created_at > $created_at
)
OR (
    total_amount = $amount
    AND created_at = $created_at
    AND order_id > $order_id
)
```

Mỗi cột trước đó phải bằng cursor trước khi so cột kế tiếp. Chiều giảm dùng `<`; chiều tăng dùng `>`.

### 12.1. Tránh tạo predicate cursor bằng chuỗi người dùng

Ứng dụng nên có bộ tạo predicate theo enum sort đã whitelist. Không lấy `ASC`/`DESC` tùy ý từ token hoặc query string rồi nối trực tiếp.

### 12.2. Cursor phải giữ đầy đủ sort key

Nếu sort theo ba cột, cursor cần giá trị của cả ba cột. Không chỉ lưu ID nếu ID không phản ánh thứ tự đang dùng.

## 13. Keyset khi sort key có thể NULL

Giả sử muốn:

```sql
ORDER BY shipped_at DESC NULLS LAST, order_id DESC
```

Thứ tự chia thành hai nhóm:

1. Dòng có `shipped_at` khác NULL, giảm dần.
2. Dòng `shipped_at IS NULL`, giảm dần theo `order_id`.

Cursor cần biết đang ở nhóm nào.

### 13.1. Cursor ở nhóm có timestamp

Trang sau gồm:

- Các dòng có `shipped_at` nhỏ hơn timestamp cursor.
- Các dòng có timestamp bằng nhau và ID nhỏ hơn.
- Tất cả dòng NULL vì NULLS LAST.

```sql
WHERE
    shipped_at < $cursor_time
    OR (shipped_at = $cursor_time AND order_id < $cursor_id)
    OR shipped_at IS NULL
```

### 13.2. Cursor đã ở nhóm NULL

Chỉ còn các dòng NULL có ID nhỏ hơn:

```sql
WHERE shipped_at IS NULL
  AND order_id < $cursor_id
```

### 13.3. Khuyến nghị

Nếu API cần cursor đơn giản, ưu tiên sort key `NOT NULL` như `created_at`. Nếu phải sort cột nullable, định nghĩa null ordering rõ và triển khai predicate riêng, có test cho cả hai nhánh.

## 14. Offset và keyset: chọn theo nhu cầu

| Tiêu chí | LIMIT/OFFSET | Keyset/cursor |
|---|---|---|
| Nhảy thẳng đến trang 50 | Dễ | Không tự nhiên; phải đi tuần tự hoặc có mốc |
| Trang sâu | Có thể chậm vì bỏ qua nhiều dòng | Thường hiệu quả hơn nếu có index |
| Insert trước vị trí hiện tại | Có thể làm lặp/bỏ sót | Ít bị dịch chuyển ranh giới |
| Cần thứ tự xác định | Có | Có |
| Cần khóa sort ổn định | Nên | Rất quan trọng |
| Hiển thị tổng số trang | Dễ kết hợp COUNT | Thường không cần/không rẻ |
| API “Load more” | Dùng được | Rất phù hợp |
| Báo cáo snapshot tuyệt đối | Cần snapshot riêng | Cần snapshot riêng |

### 14.1. Chọn OFFSET khi

- Bảng vừa phải.
- Người dùng cần nhảy tới số trang bất kỳ.
- Trang thường ở đầu.
- Tập dữ liệu ít thay đổi trong phiên tra cứu.
- Có yêu cầu hiển thị tổng trang và count.

### 14.2. Chọn keyset khi

- Bảng lớn, trang sâu.
- Giao diện cuộn vô hạn hoặc “Load more”.
- Sort key có thể xác định đầy đủ và ổn định.
- Cần tránh chi phí skip nhiều dòng.
- Người dùng thường đi tuần tự từ trang đầu tới trang sau.

### 14.3. Có thể hỗ trợ cả hai

Một API có thể dùng offset cho màn hình admin cần jump-to-page, nhưng dùng cursor cho mobile feed hoặc lịch sử đơn hàng dài. Không cần ép mọi endpoint vào một kiểu pagination.

## 15. Phân trang ổn định không đồng nghĩa snapshot xuyên nhiều request

Đây là khác biệt cần hiểu rõ.

### 15.1. Deterministic order

```sql
ORDER BY created_at DESC, order_id DESC
```

Mỗi dòng có vị trí xác định khi truy vấn một snapshot.

### 15.2. Stable page boundary

Keyset cursor giữ ranh giới theo giá trị sort key của dòng cuối trang. Một insert mới đứng trước cursor thường không đẩy các dòng cũ sang trang khác như OFFSET.

### 15.3. Snapshot consistency

Nếu một đơn cũ bị cập nhật `created_at` hoặc `total_amount` (cột đang sort) giữa hai request, nó có thể di chuyển qua ranh giới cursor. Keyset không thể ngăn mọi dịch chuyển nếu sort key thay đổi.

Muốn snapshot chính xác xuyên nhiều trang, cần cơ chế khác:

- Một transaction/snapshot giữ mở trong suốt quá trình đọc (thường không phù hợp cho HTTP nhiều phút).
- Snapshot/as-of query nếu DBMS hỗ trợ và hệ thống thiết kế theo đó.
- Materialize danh sách ID của kết quả tại thời điểm bắt đầu.
- Dùng dữ liệu bất biến và cursor theo khóa tạo đơn nếu semantics cho phép.

### 15.4. Dùng sort key bất biến

Với lịch sử đơn hàng, `created_at` và `order_id` thường ít thay đổi hơn `updated_at`, `status` hoặc `total_amount`. Nếu mục tiêu là duyệt các đơn theo thời điểm tạo, dùng:

```sql
ORDER BY created_at DESC, order_id DESC
```

thay vì sort theo cột thường xuyên cập nhật.

### 15.5. Không giữ transaction mở qua thao tác người dùng

Giữ một transaction database mở trong khi người dùng đọc trang, suy nghĩ hoặc bấm nút sau có thể giữ connection, snapshot và tài nguyên lâu. Với UI web thông thường, hãy dùng keyset/cursor hoặc snapshot vật chất hóa nếu cần, thay vì giữ transaction qua nhiều HTTP request.

## 16. JOIN và nguy cơ nhân bản đơn hàng

Muốn hiển thị khách hàng cùng đơn, JOIN bảng customers là quan hệ nhiều đơn đến một khách:

```sql
SELECT
    o.order_id,
    o.order_number,
    c.customer_name
FROM orders AS o
JOIN customers AS c
  ON c.tenant_id = o.tenant_id
 AND c.customer_id = o.customer_id;
```

Một đơn khớp tối đa một customer theo khóa duy nhất nên không nhân bản.

Ngược lại:

```sql
SELECT o.order_id, i.product_id
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id;
```

mỗi đơn có thể xuất hiện nhiều lần vì có nhiều item.

### 16.1. Vì sao LIMIT sau JOIN có thể sai?

Nếu một đơn có 10 item, nó chiếm 10 dòng trong tập join. `LIMIT 25` có thể chỉ đại diện cho vài đơn, không phải 25 đơn.

### 16.2. Dùng EXISTS khi chỉ lọc theo item

```sql
SELECT
    o.order_id,
    o.order_number,
    o.status,
    o.created_at
FROM orders AS o
WHERE o.tenant_id = $1
  AND EXISTS (
      SELECT 1
      FROM order_items AS i
      WHERE i.order_id = o.order_id
        AND i.product_id = $2
  )
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT $3;
```

### 16.3. Aggregate item trước khi JOIN

Nếu cần hiển thị số lượng item:

```sql
SELECT
    o.order_id,
    o.order_number,
    item_summary.item_count
FROM orders AS o
LEFT JOIN (
    SELECT order_id, COUNT(*) AS item_count
    FROM order_items
    GROUP BY order_id
) AS item_summary
    ON item_summary.order_id = o.order_id
WHERE o.tenant_id = $1
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT $2;
```

Subquery trả một dòng mỗi order nên không nhân bản target.

### 16.4. Đếm đơn đúng

Nếu bắt buộc JOIN one-to-many, có thể:

```sql
COUNT(DISTINCT o.order_id)
```

nhưng tốt hơn là thiết kế count bằng `EXISTS` hoặc count từ tập đơn trước khi join chi tiết. `DISTINCT` có thể tốn chi phí và che một lỗi thiết kế truy vấn.

## 17. Count, hasNext và tổng số trang

Một trang tra cứu thường cần:

- `items`: các đơn trong trang.
- `pageSize`.
- `hasNext`.
- Có thể có `totalElements` và `totalPages`.

### 17.1. Count với cùng filter

```sql
SELECT COUNT(*)
FROM orders AS o
WHERE o.tenant_id = $1
  AND o.deleted_at IS NULL
  AND ($2 IS NULL OR o.status = $2)
  AND ($3 IS NULL OR o.customer_id = $3)
  AND ($4 IS NULL OR o.created_at >= $4)
  AND ($5 IS NULL OR o.created_at < $5);
```

Không đưa `ORDER BY`, `LIMIT`, `OFFSET` vào count.

### 17.2. Count và query trang phải cùng semantics

Nếu query trang có filter sản phẩm bằng EXISTS, count cũng phải có cùng EXISTS. Nếu một query dùng tenant filter mà query còn lại quên tenant, tổng số hiển thị có thể rò rỉ số lượng dữ liệu tenant khác.

### 17.3. COUNT(DISTINCT) khi JOIN nhiều dòng

```sql
SELECT COUNT(DISTINCT o.order_id)
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id
WHERE o.tenant_id = $1
  AND i.product_id = $2;
```

### 17.4. `COUNT(*) OVER()` có tiện không?

PostgreSQL:

```sql
SELECT
    o.order_id,
    o.order_number,
    COUNT(*) OVER() AS total_count
FROM orders AS o
WHERE o.tenant_id = $1
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT $2 OFFSET $3;
```

Ưu điểm: count và page rows được tính trong cùng statement/snapshot. Hạn chế:

- Database vẫn phải xác định tổng số dòng phù hợp, có thể đắt.
- Nếu trang không có dòng, không có row nào để mang `total_count`.
- Không tự giải quyết JOIN nhân bản.

### 17.5. Không phải màn hình nào cũng cần total count

Với keyset pagination, lấy `pageSize + 1` dòng để tính `hasNext` thường đủ. Tránh chạy `COUNT(*)` đắt chỉ để hiển thị tổng số trang nếu sản phẩm không cần.

## 18. Keyset cursor và token API

Client không nên tự gửi một chuỗi tùy ý đại diện cursor rồi server tin ngay. Một cursor có thể chứa:

```json
{
  "version": 1,
  "sort": "createdAtDesc",
  "createdAt": "2026-11-14T09:00:00.123456+07:00",
  "orderId": 1001,
  "filterHash": "..."
}
```

Đây là nội dung minh họa, không phải token nên dùng nguyên văn.

### 18.1. Cursor cần chứa gì?

- Version format để có thể nâng cấp.
- Tên sort đã whitelist.
- Tất cả sort key của dòng cuối trang.
- Hướng sort/tie-breaker.
- Dấu vân tay bộ lọc nếu cursor chỉ hợp lệ cho cùng filter.
- Có thể có mốc snapshot/as-of nếu kiến trúc hỗ trợ.

Tenant và quyền truy cập vẫn phải lấy từ principal xác thực ở server, không tin tenant nằm trong token.

### 18.2. Ký token

Nếu client có thể sửa cursor, nó có thể nhảy đến ranh giới tùy ý hoặc thay filter. Một cách phổ biến:

1. Serialize payload.
2. Base64URL encode.
3. Tạo HMAC bằng secret server.
4. Trả `payload.signature`.
5. Khi nhận lại, kiểm tra signature bằng constant-time comparison.
6. Validate version, sort, filter fingerprint và kiểu dữ liệu.

HMAC giúp phát hiện sửa đổi, nhưng không mã hóa payload. Nếu cursor chứa dữ liệu nhạy cảm, dùng token opaque lưu server-side hoặc mã hóa có xác thực.

### 18.3. Không đưa SQL vào cursor

Cursor chỉ chứa dữ liệu và metadata đã định nghĩa. Không chứa câu ORDER BY, tên bảng hoặc biểu thức SQL do client có thể sửa.

### 18.4. Filter thay đổi thì cursor cũ không còn hợp lệ

Nếu trang đầu lọc `status=PAID` nhưng trang sau client đổi thành `status=PENDING` mà dùng cursor cũ, ranh giới không còn cùng một tập dữ liệu. Hãy so filter hash và từ chối cursor không khớp.

## 19. Thiết kế index cho tra cứu đơn hàng

Một query điển hình:

```sql
WHERE tenant_id = ?
  AND deleted_at IS NULL
  AND status = ?
ORDER BY created_at DESC, order_id DESC
LIMIT 25;
```

Có thể cân nhắc index:

```sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (
    tenant_id,
    status,
    created_at DESC,
    order_id DESC
);
```

### 19.1. Vì sao tenant/status đứng trước?

Các điều kiện equality thường được đặt trước sort keys trong một composite B-tree index để database thu hẹp phạm vi theo tenant và status, sau đó đọc theo thứ tự thời gian/ID.

### 19.2. Khi status là tùy chọn

Query không có `status` có thể không tận dụng tối ưu index bắt đầu bằng `(tenant_id, status, ...)` để đáp ứng `ORDER BY created_at`. Cân nhắc index khác:

```sql
CREATE INDEX idx_orders_tenant_created
ON orders (
    tenant_id,
    created_at DESC,
    order_id DESC
);
```

Không tạo mọi tổ hợp index một cách máy móc. Chọn theo tần suất query, cardinality, selectivity và chi phí ghi.

### 19.3. Partial index cho đơn chưa xóa

PostgreSQL:

```sql
CREATE INDEX idx_orders_active_tenant_created
ON orders (tenant_id, created_at DESC, order_id DESC)
WHERE deleted_at IS NULL;
```

Nếu phần lớn truy vấn luôn lọc `deleted_at IS NULL`, partial index có thể nhỏ hơn index đầy đủ. DBMS khác có filtered/partial index với cú pháp và giới hạn riêng.

### 19.4. Index theo customer

```sql
CREATE INDEX idx_orders_tenant_customer_created
ON orders (
    tenant_id,
    customer_id,
    created_at DESC,
    order_id DESC
);
```

Hữu ích khi query thường lọc tenant và customer rồi sort theo thời gian.

### 19.5. Index cho order_items

```sql
CREATE INDEX idx_order_items_product_order
ON order_items (product_id, order_id);
```

Có thể hỗ trợ EXISTS theo `product_id` và liên kết order. Nếu query chủ yếu bắt đầu từ order rồi tìm item, thứ tự index có thể cần khác `(order_id, product_id)`.

### 19.6. Sort theo nhiều cột khác nhau

Nếu người dùng được sort theo `total_amount`, index `(tenant_id, created_at, order_id)` không thể tự đáp ứng mọi sort:

```sql
ORDER BY total_amount DESC, order_id DESC
```

Có thể cần index riêng:

```sql
CREATE INDEX idx_orders_tenant_amount
ON orders (tenant_id, total_amount DESC, order_id DESC);
```

Chỉ tạo khi workload chứng minh cần. Mỗi index thêm chi phí INSERT/UPDATE/DELETE và dung lượng.

## 20. Kiểm tra execution plan

PostgreSQL:

```sql
EXPLAIN
SELECT
    order_id, order_number, status, total_amount, created_at
FROM orders
WHERE tenant_id = 1
  AND deleted_at IS NULL
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 25;
```

Trong môi trường thử nghiệm, có thể dùng:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT ...;
```

`ANALYZE` thực thi query thật. Với SELECT, điều này thường an toàn hơn DML nhưng vẫn có tải; không chạy tùy tiện trên production trong giờ cao điểm.

Quan sát:

- Có dùng index scan phù hợp không?
- Có sort lớn trên hàng nghìn/hàng triệu dòng không?
- Filter loại bỏ bao nhiêu dòng?
- Estimate rows khác actual rows nhiều không?
- OFFSET lớn có phải đọc rất nhiều dòng không?
- JOIN có làm nhân bản dữ liệu trước LIMIT không?

SQL Server dùng Actual/Estimated Execution Plan và thống kê IO/time; MySQL dùng `EXPLAIN`/`EXPLAIN ANALYZE` theo phiên bản; SQLite dùng `EXPLAIN QUERY PLAN`; Oracle dùng execution plan và runtime statistics.

## 21. Triển khai dynamic filters bằng JDBC

Ví dụ dưới đây dùng Java JDBC và PostgreSQL. Mục tiêu là:

- Tenant luôn bắt buộc.
- Chỉ thêm predicate cho filter có giá trị.
- Tất cả dữ liệu người dùng đều bind.
- Sort chỉ chọn từ enum whitelist.
- Luôn có `order_id` tie-breaker.
- Page size và offset được kiểm soát.

### 21.1. Model filter

```java
import java.math.BigDecimal;
import java.time.OffsetDateTime;

public record OrderSearchFilter(
    String status,
    Long customerId,
    OffsetDateTime createdFrom,
    OffsetDateTime createdTo,
    BigDecimal minAmount,
    BigDecimal maxAmount,
    String orderNumberPrefix
) {}
```

### 21.2. Sort enum

```java
public enum OrderSort {
    CREATED_AT,
    TOTAL_AMOUNT,
    ORDER_NUMBER
}

public enum SortDirection {
    ASC,
    DESC
}
```

### 21.3. Query builder

```java
import java.util.ArrayList;
import java.util.List;

public record SqlQuery(String sql, List<Object> parameters) {}

public static SqlQuery buildOrderSearch(
        long tenantId,
        OrderSearchFilter filter,
        OrderSort sort,
        SortDirection direction,
        int pageSize,
        long offset) {

    if (pageSize < 1 || pageSize > 100) {
        throw new IllegalArgumentException("Invalid pageSize");
    }
    if (offset < 0) {
        throw new IllegalArgumentException("Invalid offset");
    }

    StringBuilder sql = new StringBuilder("""
        SELECT
            o.order_id,
            o.order_number,
            o.status,
            o.total_amount,
            o.currency_code,
            o.created_at,
            c.customer_name
        FROM orders AS o
        JOIN customers AS c
          ON c.tenant_id = o.tenant_id
         AND c.customer_id = o.customer_id
        WHERE o.tenant_id = ?
          AND o.deleted_at IS NULL
        """);

    List<Object> parameters = new ArrayList<>();
    parameters.add(tenantId);

    if (filter.status() != null && !filter.status().isBlank()) {
        sql.append(" AND o.status = ?");
        parameters.add(filter.status());
    }

    if (filter.customerId() != null) {
        sql.append(" AND o.customer_id = ?");
        parameters.add(filter.customerId());
    }

    if (filter.createdFrom() != null) {
        sql.append(" AND o.created_at >= ?");
        parameters.add(filter.createdFrom());
    }

    if (filter.createdTo() != null) {
        sql.append(" AND o.created_at < ?");
        parameters.add(filter.createdTo());
    }

    if (filter.minAmount() != null) {
        sql.append(" AND o.total_amount >= ?");
        parameters.add(filter.minAmount());
    }

    if (filter.maxAmount() != null) {
        sql.append(" AND o.total_amount <= ?");
        parameters.add(filter.maxAmount());
    }

    if (filter.orderNumberPrefix() != null
            && !filter.orderNumberPrefix().isBlank()) {
        sql.append(" AND o.order_number LIKE ? ESCAPE '!' ");
        parameters.add(escapeLike(filter.orderNumberPrefix()) + "%");
    }

    String sortColumn = switch (sort) {
        case CREATED_AT -> "o.created_at";
        case TOTAL_AMOUNT -> "o.total_amount";
        case ORDER_NUMBER -> "o.order_number";
    };

    String sortDirection = switch (direction) {
        case ASC -> "ASC";
        case DESC -> "DESC";
    };

    String tieDirection = sortDirection;

    sql.append(" ORDER BY ")
       .append(sortColumn).append(" ")
       .append(sortDirection)
       .append(", o.order_id ")
       .append(tieDirection)
       .append(" LIMIT ? OFFSET ?");

    parameters.add(pageSize);
    parameters.add(offset);

    return new SqlQuery(sql.toString(), List.copyOf(parameters));
}

private static String escapeLike(String value) {
    return value
        .replace("!", "!!")
        .replace("%", "!%")
        .replace("_", "!_");
}
```

Đoạn `LIKE` ở trên cần khai báo escape tương ứng trong SQL:

```sql
AND o.order_number LIKE ? ESCAPE '!'
```

Ví dụ dùng ký tự ! làm escape character để tránh khác biệt cách biểu diễn backslash giữa các ngôn ngữ và cấu hình SQL. Helper phải escape chính ký tự ! trước, sau đó mới escape % và _.

Tie-breaker ở ví dụ dùng cùng hướng với cột sort chính. Hợp đồng này phải nhất quán với keyset predicate nếu chuyển sang cursor.

### 21.4. Bind parameter

```java
try (PreparedStatement statement =
        connection.prepareStatement(query.sql())) {

    for (int i = 0; i < query.parameters().size(); i++) {
        statement.setObject(i + 1, query.parameters().get(i));
    }

    try (ResultSet result = statement.executeQuery()) {
        while (result.next()) {
            long orderId = result.getLong("order_id");
            String orderNumber = result.getString("order_number");
            String status = result.getString("status");
            BigDecimal total = result.getBigDecimal("total_amount");
            OffsetDateTime createdAt =
                result.getObject("created_at", OffsetDateTime.class);
        }
    }
}
```

`setObject` phù hợp với nhiều kiểu JDBC 4.2, nhưng mapping thực tế phụ thuộc driver. Có thể dùng setter có kiểu (`setLong`, `setBigDecimal`, `setObject` với SQL type cụ thể) khi muốn kiểm soát chặt hơn.

### 21.5. Kiểm tra filter range

Trước khi query:

```java
if (filter.createdFrom() != null
        && filter.createdTo() != null
        && !filter.createdFrom().isBefore(filter.createdTo())) {
    throw new IllegalArgumentException(
        "createdFrom must be earlier than createdTo"
    );
}

if (filter.minAmount() != null
        && filter.maxAmount() != null
        && filter.minAmount().compareTo(filter.maxAmount()) > 0) {
    throw new IllegalArgumentException(
        "minAmount must not exceed maxAmount"
    );
}
```

Validation này cải thiện phản hồi API. Database vẫn cần constraints và query predicate đúng.

## 22. JDBC keyset pagination

Ví dụ keyset theo `created_at DESC, order_id DESC`.

### 22.1. SQL trang tiếp theo

```sql
SELECT
    o.order_id,
    o.order_number,
    o.status,
    o.total_amount,
    o.created_at
FROM orders AS o
WHERE o.tenant_id = ?
  AND o.deleted_at IS NULL
  AND (
      o.created_at < ?
      OR (
          o.created_at = ?
          AND o.order_id < ?
      )
  )
ORDER BY o.created_at DESC, o.order_id DESC
LIMIT ?;
```

Các tham số cursor:

1. `tenantId`.
2. `lastCreatedAt`.
3. `lastCreatedAt` lần thứ hai.
4. `lastOrderId`.
5. `pageSize + 1`.

### 22.2. Java skeleton

```java
public record OrderCursor(
    OffsetDateTime createdAt,
    long orderId
) {}

public record OrderPage<T>(
    List<T> items,
    boolean hasNext,
    OrderCursor nextCursor
) {}
```

Sau khi đọc:

```java
int fetchSize = pageSize + 1;
List<OrderRow> rows = executeKeysetQuery(fetchSize, cursor);

boolean hasNext = rows.size() > pageSize;

if (hasNext) {
    rows.remove(rows.size() - 1); // Bỏ dòng dư.
}

OrderCursor nextCursor = rows.isEmpty()
    ? null
    : new OrderCursor(
        rows.get(rows.size() - 1).createdAt(),
        rows.get(rows.size() - 1).orderId()
    );
```

Cursor tiếp theo lấy từ dòng cuối **được trả về**, không lấy dòng dư đã bị bỏ.

### 22.3. Bảo toàn precision timestamp

PostgreSQL timestamp thường lưu microsecond. Đừng tạo cursor từ timestamp đã format hiển thị chỉ còn giây hoặc mili giây nếu giá trị gốc có microsecond. Dùng giá trị chính xác lấy từ `ResultSet` để bind lại.

### 22.4. Kiểm tra filter/sort với cursor

Nếu cursor được tạo cho:

```text
status=PAID
sort=createdAt,desc
tenant=1
```

thì request kế tiếp phải giữ cùng filter và sort. Nếu client thay `status=PENDING`, server nên từ chối cursor cũ hoặc bắt đầu truy vấn mới từ trang đầu.

## 23. API response và cursor contract

Offset response có thể là:

```json
{
  "items": [],
  "page": 0,
  "pageSize": 25,
  "totalElements": 138,
  "totalPages": 6,
  "hasNext": true
}
```

Cursor response có thể là:

```json
{
  "items": [],
  "hasNext": true,
  "nextCursor": "opaque-signed-token"
}
```

### 23.1. Không cần gửi cả page và cursor

Offset và keyset giải quyết nhu cầu khác nhau. API có thể có endpoint/contract riêng hoặc tham số `paginationMode`, nhưng tránh trộn lẫn `page=20` với cursor không rõ semantics.

### 23.2. Giới hạn page size phía server

Ví dụ:

```java
int effectiveSize = Math.min(Math.max(requestedSize, 1), 100);
```

Nếu request gửi 0 hoặc số âm, có thể trả validation error thay vì âm thầm sửa; quan trọng là hợp đồng rõ.

### 23.3. Cursor không phải quyền truy cập

Một cursor hợp lệ chỉ cho biết vị trí tiếp theo trong truy vấn. Mỗi request vẫn phải:

- Xác thực người dùng.
- Kiểm tra quyền.
- Lấy tenant scope từ server-side principal.
- Áp lại mọi filter bảo mật.

Không cho phép dùng cursor của tenant A để đọc dữ liệu tenant B.

## 24. Xử lý count và truy vấn trang trong cùng transaction

Nếu sản phẩm yêu cầu `totalElements` phải tương ứng đúng với page rows tại cùng một snapshot, có thể chạy count và page query trong transaction isolation phù hợp.

PostgreSQL:

```sql
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;

SELECT COUNT(*)
FROM orders
WHERE tenant_id = 1
  AND deleted_at IS NULL;

SELECT order_id, order_number, created_at
FROM orders
WHERE tenant_id = 1
  AND deleted_at IS NULL
ORDER BY created_at DESC, order_id DESC
LIMIT 25 OFFSET 0;

COMMIT;
```

Hai câu query trong transaction `REPEATABLE READ` nhìn cùng snapshot theo semantics PostgreSQL. Tuy nhiên, chỉ giữ snapshot trong một request; nó không tự giữ qua request trang 2.

### 24.1. Chi phí snapshot

Transaction đọc lâu có thể giữ snapshot, làm vacuum khó thu hồi phiên bản row cũ và tiêu thụ connection. Không mở transaction rồi trả response cho người dùng và chờ họ bấm trang kế tiếp.

### 24.2. Khi không cần consistency tuyệt đối

Với màn hình admin thông thường, có thể:

- Chạy count riêng.
- Chạy page query riêng.
- Chấp nhận tổng count thay đổi nhẹ theo dữ liệu mới.
- Hiển thị `hasNext` dựa trên `pageSize+1`.

Hãy để yêu cầu sản phẩm quyết định mức consistency thay vì mặc định chọn isolation cao nhất.

## 25. Các lỗi thường gặp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| `ORDER BY created_at` không tie-breaker | Thứ tự các dòng cùng timestamp không xác định | Thêm khóa duy nhất |
| ORDER BY lấy trực tiếp từ request | SQL injection | Whitelist enum/identifier |
| Dùng `ORDER BY ?` để bind tên cột | Sort theo hằng/không đúng ý | Chọn fragment SQL cố định |
| OFFSET không giới hạn | Query trang sâu rất tốn | Page size cap, keyset |
| Không kiểm tra page/pageSize | Overflow hoặc request quá lớn | Validate và dùng `Math.multiplyExact` |
| Dùng BETWEEN với 23:59:59 | Bỏ sót fractional seconds | Khoảng `[from,to)` |
| Bọc cột timestamp bằng DATE() | Khó dùng index, phụ thuộc zone | Bind hai instant |
| Dùng timezone JVM ngầm định | Kết quả khác môi trường | Zone nghiệp vụ rõ |
| JOIN order_items trước LIMIT | Một đơn lặp nhiều lần, trang thiếu đơn | EXISTS hoặc aggregate trước |
| COUNT(*) sau one-to-many JOIN | Đếm item thay vì order | EXISTS hoặc COUNT DISTINCT |
| Count query thiếu tenant/filter | Tổng số sai hoặc rò rỉ dữ liệu | Dùng chung predicate |
| Cursor chỉ lưu timestamp | Bỏ sót dòng có timestamp trùng | Lưu timestamp + unique ID |
| Cursor tạo từ giá trị đã làm tròn | Ranh giới bị sai | Dùng giá trị DB đầy đủ precision |
| Keyset sort trên cột hay đổi | Dòng di chuyển qua cursor | Dùng sort key bất biến khi có thể |
| Coi keyset là snapshot | Vẫn có thay đổi do update/delete | Snapshot/as-of/materialized IDs nếu cần |
| Cursor không gắn filter | Trang sau chạy tập dữ liệu khác | Filter fingerprint |
| Tin tenant trong cursor/request | Có thể truy cập chéo tenant | Lấy tenant từ principal |
| Sort nullable không định nghĩa NULL order | Cursor bị lặp/bỏ sót | NULLS FIRST/LAST và predicate riêng |
| Lấy cursor từ dòng dư pageSize+1 | Bỏ qua dòng ở trang kế | Cursor từ dòng cuối được trả |
| COUNT(*) luôn chạy cho feed | Tốn chi phí không cần | `hasNext` bằng fetch thêm một dòng |
| Tạo quá nhiều composite index | INSERT/UPDATE chậm, tốn disk | Index theo workload |
| Chạy EXPLAIN ANALYZE DML trên production | Thực thi thay đổi dữ liệu | Dùng môi trường test/rollback có kiểm soát |
| Giữ transaction qua nhiều request UI | Giữ connection/snapshot lâu | Cursor/stateless pagination |

## 26. Bài tập tự luyện

Các bài tập dùng schema `customers`, `orders`, `order_items` ở mục 2. Ví dụ SQL chính dùng PostgreSQL, trừ khi đề bài nêu DBMS khác.

### Bài 1 — Bộ lọc cơ bản

Viết truy vấn lấy đơn của tenant `1`, chưa soft-delete, trạng thái `PAID`.

### Bài 2 — Bộ lọc tùy chọn

Viết query PostgreSQL có filter `status` và `customer_id` tùy chọn, trong đó NULL nghĩa là bỏ filter.

### Bài 3 — Khoảng ngày

Viết predicate lấy toàn bộ đơn ngày 14/11/2026 theo `Asia/Ho_Chi_Minh` bằng khoảng nửa mở. Vì sao không dùng `23:59:59`?

### Bài 4 — Khoảng tiền

Lọc đơn có `total_amount` từ 100 inclusive đến 500 exclusive.

### Bài 5 — Sắp xếp xác định

Viết `ORDER BY` cho đơn mới nhất trước. Vì sao cần thêm `order_id`?

### Bài 6 — Sort whitelist

Người dùng gửi `sort=totalAmount,desc`. Hãy nêu cách map thành SQL an toàn và giải thích vì sao `ORDER BY ?` không thay tên cột.

### Bài 7 — OFFSET

Với `page=4`, `pageSize=25`, tính offset. Viết query PostgreSQL lấy trang.

### Bài 8 — Phân trang SQL Server

Viết cú pháp SQL Server lấy 25 dòng bắt đầu từ offset 50, có thứ tự xác định.

### Bài 9 — Phân trang MySQL

Viết hai dạng LIMIT tương đương cho offset 50, row count 25.

### Bài 10 — Keyset giảm dần

Với `ORDER BY created_at DESC, order_id DESC`, cursor `(created_at=..., order_id=1002)`, viết predicate cho trang tiếp theo.

### Bài 11 — Keyset tăng dần

Viết predicate trang tiếp theo cho `ORDER BY created_at ASC, order_id ASC`.

### Bài 12 — Timestamp trùng

Hai đơn cùng timestamp. Vì sao cursor chỉ có timestamp có thể bỏ sót một đơn? Thêm tie-breaker thế nào?

### Bài 13 — Page size + 1

Với page size 25, query lấy bao nhiêu dòng để biết còn trang sau? Cursor lấy từ dòng nào?

### Bài 14 — OFFSET drift

Trang đầu lấy 3 dòng. Một dòng mới được insert ở đầu trước khi request trang 2 với OFFSET 3. Điều gì có thể xảy ra?

### Bài 15 — Keyset và concurrent update

Keyset có bảo đảm snapshot tuyệt đối nếu `created_at`/sort key có thể bị update không? Nêu giải pháp khi cần snapshot.

### Bài 16 — JOIN one-to-many

Một đơn có 5 item. Vì sao JOIN `orders` với `order_items` trước LIMIT có thể làm trang chỉ có ít hơn số đơn mong muốn?

### Bài 17 — EXISTS

Viết query lấy các đơn của tenant 1 có sản phẩm `501`, mỗi đơn chỉ xuất hiện một lần.

### Bài 18 — COUNT

Vì sao `COUNT(*)` trên JOIN `orders` và `order_items` có thể đếm sai số đơn? Viết cách sửa.

### Bài 19 — NULL ordering

Viết thứ tự `shipped_at DESC NULLS LAST, order_id DESC` cho SQL Server không dùng cú pháp `NULLS LAST`.

### Bài 20 — Cursor nullable

Nếu cursor đang ở nhóm `shipped_at IS NULL` và sort NULLS LAST, predicate trang sau cần điều kiện gì?

### Bài 21 — Index

Đề xuất index PostgreSQL cho query lọc tenant/status, soft-delete và sort theo created_at/order_id.

### Bài 22 — Filter status tùy chọn

Vì sao một index `(tenant_id, status, created_at, order_id)` chưa chắc tối ưu cho query không có filter status? Đề xuất index thay thế.

### Bài 23 — Cursor token

Nêu ít nhất năm thành phần cần có trong cursor token và cách ngăn client sửa token.

### Bài 24 — JDBC

Viết skeleton `PreparedStatement` cho query tenant + status + pageSize + offset. Vì sao sort fragment không được bind như giá trị?

### Bài 25 — Consistency

API cần `totalElements` chính xác cùng snapshot với page rows trong một request. Đề xuất transaction/isolation PostgreSQL và nêu chi phí.

<details>
<summary>Gợi ý đáp án và lời giải</summary>

**Bài 1:**

```sql
SELECT order_id, order_number, status, total_amount, created_at
FROM orders
WHERE tenant_id = 1
  AND deleted_at IS NULL
  AND status = 'PAID';
```

**Bài 2:**

```sql
SELECT *
FROM orders
WHERE tenant_id = $1
  AND deleted_at IS NULL
  AND ($2 IS NULL OR status = $2)
  AND ($3 IS NULL OR customer_id = $3);
```

**Bài 3:**

```sql
WHERE created_at >= TIMESTAMPTZ '2026-11-14 00:00:00+07'
  AND created_at <  TIMESTAMPTZ '2026-11-15 00:00:00+07'
```

Khoảng nửa mở bao gồm mọi fractional seconds trước đầu ngày kế tiếp, không cần đoán precision.

**Bài 4:**

```sql
WHERE total_amount >= 100
  AND total_amount < 500
```

**Bài 5:**

```sql
ORDER BY created_at DESC, order_id DESC
```

Timestamp có thể trùng; primary key tạo thứ tự phụ duy nhất.

**Bài 6:** Dùng enum `TOTAL_AMOUNT` ánh xạ thành chuỗi hằng `"o.total_amount"` và enum `DESC` thành `"DESC"`. `?` chỉ bind giá trị, không bind identifier.

**Bài 7:** Offset `4 * 25 = 100`.

```sql
SELECT *
FROM orders
WHERE tenant_id = $1
ORDER BY created_at DESC, order_id DESC
LIMIT 25 OFFSET 100;
```

**Bài 8 — SQL Server:**

```sql
SELECT *
FROM dbo.orders
WHERE tenant_id = @tenant_id
ORDER BY created_at DESC, order_id DESC
OFFSET 50 ROWS FETCH NEXT 25 ROWS ONLY;
```

**Bài 9 — MySQL:**

```sql
LIMIT 50, 25
```

hoặc:

```sql
LIMIT 25 OFFSET 50
```

**Bài 10:**

```sql
created_at < $cursor_time
OR (created_at = $cursor_time AND order_id < $cursor_id)
```

**Bài 11:**

```sql
created_at > $cursor_time
OR (created_at = $cursor_time AND order_id > $cursor_id)
```

**Bài 12:** Các dòng có cùng timestamp không được phân biệt bởi cursor time; thêm `order_id` làm tie-breaker và lưu cả hai giá trị trong cursor.

**Bài 13:** Lấy 26 dòng. Nếu có 26, trả 25 và `hasNext=true`; cursor lấy từ dòng thứ 25 được trả về, không lấy dòng thứ 26.

**Bài 14:** Dòng mới đẩy các dòng cũ xuống một vị trí; OFFSET 3 có thể trả lại dòng cuối trang 1, gây lặp.

**Bài 15:** Không. Nếu sort key thay đổi, dòng có thể di chuyển qua cursor. Dùng sort key bất biến, snapshot/as-of query hoặc materialize ID set khi cần snapshot xuyên nhiều trang.

**Bài 16:** Một đơn tạo 5 dòng join nên chiếm 5 vị trí LIMIT. Trang có thể chứa ít hơn 25 đơn duy nhất. Dùng EXISTS hoặc aggregate trước JOIN.

**Bài 17:**

```sql
SELECT o.order_id, o.order_number, o.status
FROM orders o
WHERE o.tenant_id = 1
  AND EXISTS (
      SELECT 1
      FROM order_items i
      WHERE i.order_id = o.order_id
        AND i.product_id = 501
  )
ORDER BY o.created_at DESC, o.order_id DESC;
```

**Bài 18:** Mỗi item tạo một dòng join. Có thể dùng `COUNT(DISTINCT o.order_id)` hoặc EXISTS để đếm từ bảng orders.

**Bài 19 — SQL Server:**

```sql
ORDER BY
    CASE WHEN shipped_at IS NULL THEN 1 ELSE 0 END ASC,
    shipped_at DESC,
    order_id DESC
```

**Bài 20:**

```sql
WHERE shipped_at IS NULL
  AND order_id < $cursor_id
```

Vì đã ở nhóm NULLS LAST, trang sau chỉ còn dòng NULL với ID nhỏ hơn.

**Bài 21:**

```sql
CREATE INDEX idx_orders_tenant_status_created
ON orders (tenant_id, status, created_at DESC, order_id DESC)
WHERE deleted_at IS NULL;
```

Đây là một phương án; xác nhận bằng execution plan và workload thực tế.

**Bài 22:** Khi không lọc status, index có cột status ở giữa không thể luôn trả thứ tự created_at toàn cục cho tenant. Có thể cần:

```sql
CREATE INDEX idx_orders_tenant_created
ON orders (tenant_id, created_at DESC, order_id DESC)
WHERE deleted_at IS NULL;
```

**Bài 23:** Version, sort key đầy đủ, sort direction, filter fingerprint, tie-breaker; ký HMAC hoặc dùng token opaque server-side để phát hiện sửa đổi.

**Bài 24:**

```java
String sql = """
    SELECT order_id, order_number, status, created_at
    FROM orders
    WHERE tenant_id = ?
      AND status = ?
      AND deleted_at IS NULL
    ORDER BY created_at DESC, order_id DESC
    LIMIT ? OFFSET ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, tenantId);
    ps.setString(2, status);
    ps.setInt(3, pageSize);
    ps.setLong(4, offset);
}
```

Sort fragment là identifier/direction, không phải giá trị; chọn từ whitelist.

**Bài 25:** Chạy count và page query trong một transaction `REPEATABLE READ` trên PostgreSQL để cùng snapshot. Chi phí là giữ snapshot/connection lâu hơn và có thể ảnh hưởng vacuum nếu transaction kéo dài; chỉ giữ trong phạm vi request ngắn.

</details>

## 27. Checklist triển khai

Trước khi đưa chức năng tra cứu đơn hàng vào production, hãy xác nhận:

1. **Phạm vi dữ liệu:** tenant/user scope luôn có và lấy từ principal xác thực.
2. **Filter:** mọi giá trị bind bằng PreparedStatement; filter tùy chọn có semantics rõ.
3. **Ngày giờ:** dùng instant và khoảng `[from,to)`; zone nghiệp vụ được chỉ định.
4. **Sort:** tên cột và hướng sort nằm trong whitelist.
5. **Thứ tự:** luôn có tie-breaker duy nhất.
6. **Pagination:** chọn OFFSET hay keyset theo nhu cầu; page size có giới hạn.
7. **Cursor:** chứa đầy đủ sort key, gắn với filter/sort, có chữ ký hoặc opaque storage.
8. **JOIN:** không nhân bản order trước LIMIT; dùng EXISTS/aggregate khi phù hợp.
9. **Count:** dùng cùng điều kiện và cùng tenant scope; không count dòng item thay vì order.
10. **Consistency:** xác định có chấp nhận dữ liệu thay đổi giữa các trang hay cần snapshot.
11. **Index:** phù hợp equality filters, sort keys và workload; đo bằng execution plan.
12. **Observability:** theo dõi latency, rows scanned, count duration, page depth và query timeout.

## 28. Kết luận

Tra cứu đơn hàng là một bài toán kết hợp giữa lọc, sắp xếp, phân trang, bảo mật dữ liệu và hiệu năng. Một truy vấn đúng cú pháp chưa đủ; nó phải trả về đúng tập đơn, đúng thứ tự, đúng ranh giới trang và đúng phạm vi người dùng được phép xem.

```text
Request filters
      │
      ▼
Validate + tenant scope
      │
      ▼
Build predicates with bound values
      │
      ▼
Whitelist sort + unique tie-breaker
      │
      ▼
OFFSET or keyset predicate
      │
      ▼
Index-supported query plan
      │
      ▼
One row per order + consistent response
```

Hãy nhớ bốn nguyên tắc:

1. **Lọc chính xác:** tenant luôn được áp dụng; ngày giờ dùng khoảng nửa mở; giá trị được bind.
2. **Sắp xếp xác định:** sort whitelist và thêm khóa duy nhất làm tie-breaker.
3. **Chọn pagination đúng:** OFFSET tiện cho nhảy trang; keyset phù hợp trang sâu và luồng dữ liệu thay đổi, nhưng không tự tạo snapshot tuyệt đối.
4. **Giữ một dòng cho mỗi đơn:** tránh JOIN one-to-many trước LIMIT; dùng EXISTS hoặc aggregate và đếm đúng entity.

Khi bốn phần này được thiết kế cùng nhau, màn hình tra cứu có thể hoạt động ổn định hơn khi dữ liệu lớn, nhiều người dùng tìm kiếm đồng thời và đơn hàng liên tục được tạo hoặc cập nhật.
