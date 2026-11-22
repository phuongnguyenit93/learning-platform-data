# Chỉ mục phân cụm (clustered index) và cách tổ chức dữ liệu theo khóa chính

Trong InnoDB, bảng được tổ chức quanh một **chỉ mục phân cụm** (clustered index). Các trang lá (leaf pages) của chỉ mục này lưu cả dữ liệu của hàng, được sắp xếp theo giá trị khóa phân cụm. Khi bảng có khóa chính, khóa chính thường chính là khóa phân cụm. Vì vậy, thiết kế khóa chính ảnh hưởng trực tiếp đến cách InnoDB tìm hàng, cách các chỉ mục phụ trỏ đến hàng và chi phí lưu trữ, cập nhật dữ liệu.

Hiểu clustered index giúp bạn chọn khóa chính phù hợp, thiết kế chỉ mục phụ hiệu quả và giải thích vì sao truy vấn theo khóa chính thường có đường truy cập trực tiếp, trong khi truy vấn theo chỉ mục phụ có thể cần thêm một lần tra cứu.

## 1. Clustered index là gì?

Clustered index là cấu trúc B+Tree mà các trang lá chứa bản ghi dữ liệu của bảng. Các nút bên trong chứa khóa và con trỏ đến trang con để dẫn đường tìm kiếm. Các bản ghi ở trang lá được sắp xếp theo thứ tự khóa của B+Tree.

Với bảng InnoDB có khóa chính `id`, cấu trúc khái quát như sau:

```text
                 Root / Internal pages
                 [  100 |  200  ]
                  /      |      \
                 /       |       \
                v        v        v
          Leaf page  Leaf page  Leaf page
          id 1..99   id 100..199 id 200..299
          + rows     + rows      + rows
```

Hình trên chỉ mô tả logic tìm kiếm. Trong file dữ liệu, các trang không nhất thiết nằm liền kề về mặt vật lý. InnoDB quản lý chúng theo cấu trúc trang và liên kết thứ tự của B+Tree.

Ví dụ:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    city VARCHAR(100) NOT NULL,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email)
) ENGINE = InnoDB;
```

Trong bảng này, `customer_id` là khóa chính nên clustered index được tổ chức theo `customer_id`. Trang lá chứa các hàng khách hàng, bao gồm `email`, `full_name` và `city`, chứ không chỉ chứa riêng giá trị `customer_id`.

Một bảng InnoDB chỉ có một clustered index vì một hàng dữ liệu chỉ có một cách tổ chức phân cụm. Bảng có thể có nhiều secondary index (chỉ mục phụ) để hỗ trợ các cách tìm kiếm khác nhau.

## 2. InnoDB chọn khóa phân cụm như thế nào?

InnoDB chọn clustered index theo thứ tự ưu tiên sau:

1. Dùng khóa chính (`PRIMARY KEY`) nếu bảng khai báo khóa chính.
2. Nếu không có khóa chính, dùng chỉ mục `UNIQUE` đầu tiên mà tất cả cột đều được khai báo `NOT NULL`.
3. Nếu không có khóa chính hoặc chỉ mục `UNIQUE NOT NULL` phù hợp, InnoDB tạo một clustered index ẩn dựa trên row ID nội bộ.

Ví dụ bảng không khai báo khóa chính nhưng có unique key không null:

```sql
CREATE TABLE devices (
    serial_number VARCHAR(40) NOT NULL,
    model VARCHAR(100) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_devices_serial (serial_number)
) ENGINE = InnoDB;
```

Trong trường hợp này, `serial_number` có thể được chọn làm clustered key vì unique và tất cả cột trong chỉ mục đều `NOT NULL`.

Nếu bảng không có khóa chính và cũng không có unique index thỏa điều kiện, InnoDB tạo một row ID ẩn dài 6 byte để tổ chức clustered index. Row ID này không phải cột mà ứng dụng có thể truy vấn trực tiếp. Dù bảng vẫn hoạt động, bạn mất đi một định danh hàng rõ ràng để tham chiếu, kiểm soát cập nhật và thiết kế quan hệ. Vì vậy, nên chủ động khai báo khóa chính cho bảng InnoDB.

## 3. Truy vấn theo khóa chính đi qua clustered index

Khi truy vấn bằng khóa chính, InnoDB tìm trực tiếp trong B+Tree phân cụm và đọc hàng tại trang lá:

```sql
SELECT customer_id, email, full_name, city
FROM customers
WHERE customer_id = 105;
```

Đường truy cập khái quát:

1. Bắt đầu từ root page.
2. So sánh `customer_id` để đi xuống các internal page phù hợp.
3. Đến leaf page chứa khóa `105`.
4. Đọc toàn bộ hàng từ trang lá.

Với điều kiện bằng trên một khóa chính duy nhất, kết quả tối đa là một hàng. Truy vấn theo một khoảng khóa chính cũng có thể duyệt các leaf page theo thứ tự khóa:

```sql
SELECT customer_id, full_name
FROM customers
WHERE customer_id BETWEEN 100 AND 150
ORDER BY customer_id;
```

Đây là một lý do khóa chính có ý nghĩa với hiệu năng: nó vừa định danh hàng, vừa xác định thứ tự của clustered index và hỗ trợ các truy vấn tìm kiếm hoặc quét theo khoảng.

## 4. Secondary index lưu gì?

Secondary index là B+Tree riêng, có trang lá lưu giá trị cột được lập chỉ mục cùng giá trị khóa chính cần thiết để xác định hàng trong clustered index.

Ví dụ tạo chỉ mục phụ trên thành phố:

```sql
CREATE INDEX idx_customers_city
ON customers (city);
```

Khi truy vấn theo `city`, InnoDB có thể thực hiện hai bước:

1. Tìm các mục phù hợp trong B+Tree `idx_customers_city`.
2. Lấy `customer_id` từ mục chỉ mục phụ và dùng nó tìm hàng đầy đủ trong clustered index.

Ví dụ:

```sql
SELECT customer_id, email, full_name
FROM customers
WHERE city = 'Da Nang';
```

Nếu chỉ mục phụ không chứa đủ các cột mà truy vấn cần, InnoDB phải tra cứu clustered index để lấy phần còn thiếu. Đây thường được gọi là bookmark lookup hoặc truy cập hàng qua chỉ mục phụ.

### Vì sao khóa chính làm tăng kích thước chỉ mục phụ?

Mỗi secondary index cần mang khóa chính để xác định hàng tương ứng. Do đó, khóa chính càng rộng thì các secondary index thường càng tốn chỗ. Với khóa chính ghép, các thành phần khóa chính cần thiết cũng được lưu trong các mục chỉ mục phụ.

Ví dụ, nếu bảng dùng khóa chính ghép `(tenant_id, order_id)`, các chỉ mục phụ phải chứa đủ thành phần khóa chính cần để định vị hàng, trừ những thành phần đã có sẵn trong chính secondary index. Nếu có nhiều chỉ mục phụ, phần khóa chính được mang theo có thể làm tổng dung lượng index tăng đáng kể.

Vì thế, khóa chính nên ngắn gọn và ổn định. Một khóa chính `BIGINT` thường làm các secondary index gọn hơn so với một khóa chuỗi dài, nếu cả hai đều đáp ứng yêu cầu định danh của nghiệp vụ.

## 5. Covering index và trường hợp không cần quay lại clustered index

Nếu secondary index chứa tất cả cột cần cho truy vấn, InnoDB có thể trả kết quả trực tiếp từ chỉ mục phụ. Đây là covering index (chỉ mục bao phủ), giúp tránh bước tra cứu hàng trong clustered index.

Ví dụ:

```sql
CREATE INDEX idx_customers_city_name
ON customers (city, full_name);

SELECT city, full_name
FROM customers
WHERE city = 'Da Nang';
```

Các cột truy vấn đều nằm trong chỉ mục `(city, full_name)`, nên truy vấn có thể được bao phủ bởi index này. Trên InnoDB, khóa chính cũng có mặt trong secondary index, vì vậy một truy vấn chỉ lấy `customer_id` cùng `city` có thể được bao phủ bởi chỉ mục phụ trên `city`.

Không nên thêm quá nhiều cột vào index chỉ để tạo covering index. Index rộng làm tăng dung lượng, chi phí ghi, cập nhật và bảo trì. Hãy dựa vào truy vấn thực tế và kết quả `EXPLAIN` để quyết định.

## 6. Khóa chính ghép và thứ tự dữ liệu

Khóa chính có thể gồm nhiều cột. InnoDB sắp xếp clustered index theo thứ tự từ trái sang phải của các thành phần khóa.

Ví dụ bảng chi tiết đơn hàng:

```sql
CREATE TABLE order_items (
    order_id BIGINT UNSIGNED NOT NULL,
    line_no INT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id, line_no),
    KEY idx_order_items_product (product_id)
) ENGINE = InnoDB;
```

Khóa chính `(order_id, line_no)` tạo thứ tự từ điển: trước hết theo `order_id`, sau đó theo `line_no` trong cùng một đơn hàng.

Truy vấn sau phù hợp với thứ tự clustered index:

```sql
SELECT order_id, line_no, product_id, quantity
FROM order_items
WHERE order_id = 7001
ORDER BY line_no;
```

Truy vấn chỉ lọc theo `line_no` mà không có điều kiện trên `order_id` thường không tận dụng được phần đầu của khóa ghép một cách hiệu quả:

```sql
SELECT order_id, line_no
FROM order_items
WHERE line_no = 2;
```

Đây là quy tắc leftmost prefix (tiền tố trái): chỉ mục ghép `(a, b, c)` hỗ trợ hiệu quả các điều kiện bắt đầu từ `a`, như `(a)`, `(a, b)` hoặc `(a, b, c)`. Điều kiện chỉ có `b` thường cần một chỉ mục khác nếu truy vấn đó quan trọng.

Chọn khóa ghép theo cách truy cập dữ liệu thường xuyên. Nếu hầu hết thao tác lấy toàn bộ dòng hàng của một đơn hàng, `(order_id, line_no)` là lựa chọn tự nhiên. Nếu cần tra cứu sản phẩm ở nhiều đơn hàng, secondary index trên `product_id` hỗ trợ đường truy cập đó.

## 7. Chọn khóa chính để giảm chi phí lưu trữ và ghi

Một khóa chính tốt thường có các đặc điểm:

- **Duy nhất và không null:** mỗi hàng có một định danh rõ ràng.
- **Ngắn gọn:** giảm dung lượng clustered index và các secondary index.
- **Ổn định:** tránh thay đổi giá trị khóa sau khi tạo hàng.
- **Phù hợp với truy vấn:** hỗ trợ các truy vấn định danh và truy vấn theo khoảng quan trọng.
- **Có kiểu dữ liệu phù hợp:** tránh dùng chuỗi lớn khi một kiểu số hoặc kiểu nhị phân gọn hơn đáp ứng được yêu cầu.

### Khóa tăng dần

Khóa `AUTO_INCREMENT` như `BIGINT UNSIGNED` thường tạo vị trí chèn gần cuối B+Tree:

```sql
CREATE TABLE events (
    event_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    event_type VARCHAR(80) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (event_id)
) ENGINE = InnoDB;
```

Kiểu chèn tăng dần thường có tính cục bộ tốt và giảm việc chèn vào các trang rải rác. Tuy nhiên, với tải ghi đồng thời rất cao, vùng trang cuối có thể trở thành điểm tranh chấp; cần đo đạc trước khi điều chỉnh cấu hình hoặc thay đổi chiến lược khóa.

### Khóa ngẫu nhiên

Khóa UUID dạng chuỗi `CHAR(36)` dài hơn đáng kể so với số nguyên 64 bit. UUID ngẫu nhiên cũng có thể khiến các lần chèn rải rác trên nhiều vùng của B+Tree, dẫn đến nhiều lần đọc trang, page split và phân mảnh hơn so với khóa tăng dần.

Nếu nghiệp vụ cần UUID, cân nhắc lưu ở dạng `BINARY(16)` để giảm kích thước so với `CHAR(36)`. Với loại UUID có thành phần thời gian, có thể chọn cách biểu diễn/sắp xếp giúp tính cục bộ tốt hơn, nhưng phải thống nhất cách chuyển đổi giữa ứng dụng và database. Không thay đổi thứ tự byte một cách tùy tiện vì sẽ ảnh hưởng cách so sánh và sắp xếp.

### Tránh khóa chính thay đổi thường xuyên

Khi giá trị clustered key thay đổi, InnoDB phải di chuyển bản ghi đến vị trí mới trong clustered index và cập nhật các secondary index mang khóa chính đó. Vì vậy, nên dùng một định danh bất biến làm primary key; các thuộc tính nghiệp vụ có thể thay đổi nên được đặt ở cột thường hoặc unique secondary index nếu cần.

## 8. Page split và tính cục bộ của dữ liệu

B+Tree được lưu trong các trang (page). Khi chèn một hàng vào trang lá đã gần đầy, InnoDB có thể phải chia trang (page split) để tạo chỗ. Việc chèn theo khóa tăng dần thường tập trung gần vùng cuối cây; chèn khóa ngẫu nhiên có thể tác động đến nhiều trang khác nhau.

Page split là hoạt động bình thường của B+Tree, không đồng nghĩa dữ liệu bị hỏng. Tuy nhiên, chèn ngẫu nhiên với khối lượng lớn có thể làm tăng số lần chia trang, tăng phân mảnh và làm giảm tính cục bộ của cache. Hãy xem xét đặc điểm khóa và workload thay vì chỉ dựa vào một quy tắc chung.

Các trang lá được nối theo thứ tự khóa để hỗ trợ duyệt tuần tự, nhưng không nên hiểu rằng mọi hàng có khóa liền kề luôn nằm cạnh nhau trong file vật lý. InnoDB quản lý phân bổ trang riêng; thứ tự logic của index và vị trí vật lý trên đĩa là hai khái niệm khác nhau.

## 9. Quan sát đường truy cập bằng `EXPLAIN`

`EXPLAIN` cho biết MySQL dự kiến truy cập bảng và chỉ mục như thế nào:

```sql
EXPLAIN
SELECT customer_id, email, full_name
FROM customers
WHERE customer_id = 105;
```

Với truy vấn theo khóa chính, hãy kiểm tra các thông tin như:

- `key`: chỉ mục MySQL chọn; thường là `PRIMARY` cho tra cứu theo khóa chính.
- `type`: kiểu truy cập; ví dụ `const` cho điều kiện bằng trên khóa duy nhất với hằng số, hoặc `range` cho truy vấn khoảng.
- `rows`: số hàng ước lượng cần đọc.
- `Extra`: thông tin bổ sung như `Using index` khi có thể dùng covering index.

So sánh truy vấn theo khóa chính với truy vấn theo secondary index:

```sql
EXPLAIN
SELECT customer_id, email, full_name
FROM customers
WHERE city = 'Da Nang';

EXPLAIN
SELECT city, full_name
FROM customers
WHERE city = 'Da Nang';
```

Truy vấn đầu có thể cần tra cứu clustered index để lấy `email` và `full_name` nếu secondary index không chứa các cột đó. Truy vấn thứ hai có thể dùng covering index `(city, full_name)`. Kết quả thực tế phụ thuộc dữ liệu, thống kê và các chỉ mục hiện có; hãy đọc kế hoạch thực thi trên môi trường đại diện thay vì suy luận chỉ từ câu SQL.

## 10. Các lỗi thiết kế thường gặp

**Không khai báo khóa chính.** InnoDB vẫn có thể tạo clustered index ẩn, nhưng ứng dụng thiếu định danh hàng rõ ràng. Hãy chủ động thiết kế primary key cho bảng.

**Dùng khóa chính quá rộng.** Khóa chuỗi dài hoặc khóa ghép nhiều cột làm tăng kích thước của các secondary index. Chỉ đưa vào khóa chính các cột thật sự cần để định danh và tổ chức truy cập.

**Dùng cột có thể thay đổi làm clustered key.** Cập nhật khóa phân cụm kéo theo chi phí di chuyển hàng và cập nhật index phụ. Ưu tiên khóa ổn định.

**Cho rằng secondary index chứa toàn bộ hàng.** Trang lá của secondary index chủ yếu chứa khóa index và khóa chính. Nếu truy vấn cần thêm cột, engine có thể phải tra cứu clustered index.

**Tạo quá nhiều index rộng.** Mỗi index làm tăng dung lượng và chi phí ghi. Chỉ tạo index theo truy vấn quan trọng, kiểm tra bằng `EXPLAIN` và theo dõi workload.

**Nhầm thứ tự index với thứ tự vật lý của file.** Clustered index sắp xếp dữ liệu theo khóa trong cấu trúc B+Tree; không bảo đảm các hàng có khóa gần nhau luôn nằm liền kề trên thiết bị lưu trữ.

## 11. Tự kiểm tra

1. Vì sao một bảng InnoDB chỉ có một clustered index?
2. InnoDB chọn clustered index thế nào nếu bảng không khai báo `PRIMARY KEY`?
3. Vì sao secondary index cần lưu khóa chính?
4. Truy vấn theo secondary index có thể phải thực hiện thêm bước nào để lấy đầy đủ hàng?
5. Covering index giúp giảm chi phí truy cập như thế nào?
6. Khóa chính ghép `(order_id, line_no)` hỗ trợ loại truy vấn nào tốt nhất?
7. Vì sao khóa chính ngẫu nhiên và quá rộng có thể làm tăng chi phí lưu trữ và ghi?
8. `EXPLAIN` giúp xác minh lựa chọn clustered index và secondary index ra sao?

