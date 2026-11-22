# Đánh giá chỉ mục cho khóa ngoại và các phép nối thường gặp

## Mục tiêu học tập

Sau bài học này, bạn có thể:

- Giải thích vai trò của chỉ mục ở phía bảng tham chiếu và bảng được tham chiếu trong quan hệ khóa ngoại.
- Nhận biết trường hợp hệ quản trị tự tạo chỉ mục cho cột khóa ngoại và trường hợp cần tạo thủ công.
- Chọn thứ tự cột cho chỉ mục đơn và chỉ mục ghép theo điều kiện JOIN, WHERE, ORDER BY và phân bố dữ liệu.
- Đánh giá chỉ mục cho quan hệ một-một, một-nhiều, nhiều-nhiều và các kiểu phép nối phổ biến.
- Dùng execution plan và số liệu tải để xác định chỉ mục có đem lại lợi ích thực tế hay chỉ làm tăng chi phí ghi.

## 1. Khóa ngoại, phép nối và vai trò của chỉ mục

Khóa ngoại (foreign key, FK) là ràng buộc bảo đảm giá trị ở một hoặc nhiều cột của bảng tham chiếu phải khớp với khóa được tham chiếu ở bảng khác, hoặc là NULL nếu ràng buộc cho phép. Ví dụ, `orders.customer_id` tham chiếu `customers.customer_id`: mỗi đơn hàng phải gắn với một khách hàng hợp lệ.

Phép nối (JOIN) dùng quan hệ giữa các bảng để kết hợp dữ liệu. Một truy vấn phổ biến có thể lấy đơn hàng cùng tên khách hàng:

```sql
SELECT o.order_id, o.created_at, c.customer_name
FROM orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
WHERE o.created_at >= DATE '2026-01-01';
```

Khóa ngoại bảo đảm tính toàn vẹn dữ liệu; nó không tự động bảo đảm phép nối chạy nhanh. Chỉ mục cung cấp đường truy cập để tìm hàng phù hợp mà không phải quét toàn bộ bảng trong những trường hợp thích hợp.

Trong quan hệ trên, khóa chính hoặc ràng buộc UNIQUE của `customers.customer_id` thường đã có chỉ mục ở phía được tham chiếu. Cột `orders.customer_id` ở phía tham chiếu có thể cần một chỉ mục riêng để tìm các đơn hàng theo khách hàng, hỗ trợ phép nối và xử lý một số thao tác xóa/cập nhật ở bảng cha.

Phạm vi DATABASE_PERFORMANCE yêu cầu đánh giá chỉ mục dựa trên tải, kế hoạch thực thi và cơ chế truy cập dữ liệu. Vì vậy, quyết định tạo chỉ mục cho FK cần xét tần suất JOIN, số hàng phù hợp, cách dữ liệu phân bố, thao tác ghi và hành vi thực tế của hệ quản trị.

## 2. Phân biệt phía được tham chiếu và phía tham chiếu

Xét hai bảng:

```sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    customer_name VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
);
```

- `customers.customer_id` là phía được tham chiếu (parent/referenced side). Khóa chính đã bảo đảm tính duy nhất và thường có chỉ mục để tìm một khách hàng theo ID.
- `orders.customer_id` là phía tham chiếu (child/referencing side). Cột này có thể chứa cùng một giá trị ở nhiều hàng vì một khách hàng có thể có nhiều đơn hàng.

Chỉ mục phía parent giúp tìm đúng một hàng cha. Chỉ mục phía child giúp tìm các hàng con thuộc một parent. Hai hướng truy cập này phục vụ các thao tác khác nhau.

### Vì sao cần xem xét chỉ mục ở phía child?

Chỉ mục trên `orders.customer_id` có thể hỗ trợ:

- Tìm tất cả đơn hàng của một khách hàng.
- Nối `customers` với `orders` bằng nested loop khi mỗi khách hàng chỉ có số đơn hàng vừa phải.
- Kiểm tra các hàng tham chiếu khi xóa khách hàng hoặc thay đổi khóa được tham chiếu, tùy hành vi hệ quản trị và ràng buộc.
- Thực hiện thao tác `ON DELETE CASCADE` hoặc `ON UPDATE CASCADE` hiệu quả hơn khi cần tìm hàng con.

Nếu không có chỉ mục phù hợp, hệ quản trị có thể phải quét bảng `orders` để tìm các hàng có `customer_id` tương ứng. Với bảng nhỏ, việc quét có thể vẫn rẻ. Với bảng lớn và thao tác thường xuyên, chi phí quét có thể đáng kể.

### Hệ quản trị có tự tạo chỉ mục cho khóa ngoại không?

Hành vi khác nhau theo sản phẩm:

| Hệ quản trị | Hành vi thường gặp đối với cột FK phía tham chiếu |
| --- | --- |
| PostgreSQL | Tạo chỉ mục cho khóa được tham chiếu nếu cần ràng buộc PRIMARY KEY/UNIQUE, nhưng không tự động tạo chỉ mục trên cột FK ở bảng tham chiếu |
| MySQL InnoDB | Cần chỉ mục phù hợp ở phía FK; nếu chưa có chỉ mục thích hợp, InnoDB có thể tự tạo chỉ mục để đáp ứng ràng buộc |
| SQL Server | Tạo chỉ mục cho PRIMARY KEY/UNIQUE ở phía được tham chiếu, nhưng không tự động tạo chỉ mục trên cột FK |
| Oracle | Ràng buộc khóa ngoại không mặc nhiên tạo chỉ mục trên cột phía child; chỉ mục cần được thiết kế riêng theo workload |

Luôn kiểm tra tài liệu và phiên bản cụ thể. Nếu InnoDB đã tạo chỉ mục tự động, hãy kiểm tra tên, thứ tự cột và khả năng đáp ứng truy vấn trước khi tạo thêm chỉ mục trùng lặp.

## 3. Không phải mọi cột khóa ngoại đều cần một chỉ mục đơn

Chỉ mục FK hữu ích khi truy vấn thường lọc, nối hoặc tìm hàng con theo cột đó. Nhưng tạo một chỉ mục đơn cho mọi FK có thể làm tăng:

- Dung lượng lưu trữ và số trang chỉ mục cần giữ trong cache.
- CPU và I/O khi INSERT, DELETE hoặc UPDATE các cột khóa ngoại.
- Chi phí ghi log giao dịch và đồng bộ dữ liệu.
- Thời gian bảo trì, cập nhật thống kê, rebuild hoặc reorganize chỉ mục.
- Cạnh tranh trên các trang chỉ mục khi nhiều phiên ghi đồng thời.

Trước khi tạo chỉ mục, hãy trả lời:

1. Bảng child có lớn đến mức quét toàn bảng trở nên đắt không?
2. Truy vấn nào sử dụng FK và tần suất thực thi của chúng là bao nhiêu?
3. Giá trị FK có độ chọn lọc như thế nào? Một giá trị thường khớp vài hàng hay hàng triệu hàng?
4. Chỉ mục hiện có có bắt đầu bằng cột FK hoặc bao phủ truy vấn không?
5. Tải ghi có cao đến mức thêm chỉ mục làm giảm throughput đáng kể không?
6. Hệ quản trị có cần tìm hàng child khi kiểm tra DELETE/UPDATE ở parent không?

Chỉ mục không phải lựa chọn mặc định chỉ vì một cột được khai báo là FK. Cần dựa trên kích thước bảng, workload và chi phí tổng.

## 4. Chọn chỉ mục cho JOIN một-nhiều

Quan hệ một-nhiều thường có một hàng parent liên kết với nhiều hàng child. Ví dụ một khách hàng có nhiều đơn hàng.

Truy vấn tìm đơn hàng của một khách hàng:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = ?;
```

Chỉ mục đơn trên `orders(customer_id)` có thể giúp tìm nhóm hàng cần thiết. Nếu truy vấn thường sắp xếp theo thời gian và chỉ lấy một số đơn gần nhất, chỉ mục ghép có thể hữu ích hơn:

```sql
CREATE INDEX ix_orders_customer_created
    ON orders (customer_id, created_at DESC);
```

Với truy vấn:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = ?
ORDER BY created_at DESC
LIMIT 20;
```

chỉ mục bắt đầu bằng `customer_id` có thể tìm vùng của khách hàng, sau đó đọc theo thứ tự thời gian và dừng khi đã lấy đủ 20 hàng. Nếu cần `total_amount` mà chỉ mục không chứa cột đó, hệ quản trị có thể phải lookup hàng trong bảng.

Ở các hệ quản trị hỗ trợ included columns, có thể cân nhắc bao phủ thêm cột nhỏ thường được trả về. Ví dụ PostgreSQL hoặc SQL Server có cú pháp `INCLUDE`; MySQL thường cần đưa cột vào phần khóa chỉ mục để có covering access. Cột thêm vào làm chỉ mục lớn hơn và tăng chi phí ghi, vì vậy không nên thêm hàng loạt.

### JOIN từ parent sang child

Khi truy vấn bắt đầu từ một nhóm khách hàng nhỏ rồi tìm đơn hàng của từng khách hàng, chỉ mục child trên `orders.customer_id` thường là đường truy cập quan trọng cho nested loop.

### JOIN từ child sang parent

Khi truy vấn đọc một nhóm đơn hàng rồi tìm khách hàng tương ứng, khóa chính `customers.customer_id` giúp tra cứu parent. Nếu child đã được lọc mạnh theo ngày hoặc trạng thái, bộ tối ưu có thể đọc các đơn hàng trước rồi lookup khách hàng.

Trong cả hai hướng, chỉ mục cần hỗ trợ phía được dùng làm đầu vào tra cứu. Không nhất thiết phải có hai chỉ mục mới nếu khóa chính parent và chỉ mục child hiện tại đã đáp ứng.

## 5. Chỉ mục ghép cho nhiều cột JOIN

Một số quan hệ dùng khóa ngoại ghép (composite foreign key), hoặc truy vấn JOIN trên nhiều cột, chẳng hạn tenant và mã khách hàng:

```sql
SELECT o.order_id, o.created_at
FROM orders AS o
JOIN customers AS c
  ON c.tenant_id = o.tenant_id
 AND c.customer_id = o.customer_id
WHERE o.tenant_id = ?
  AND o.customer_id = ?;
```

Nếu workload thường lọc và nối theo cả hai cột, chỉ mục ghép `(tenant_id, customer_id)` trên phía child có thể phù hợp:

```sql
CREATE INDEX ix_orders_tenant_customer
    ON orders (tenant_id, customer_id);
```

Thứ tự cột của chỉ mục ghép quan trọng. B-tree thường hỗ trợ tốt các điều kiện trên tiền tố trái (leftmost prefix). Chỉ mục `(tenant_id, customer_id)` phù hợp với điều kiện trên cả hai cột và thường có thể hỗ trợ điều kiện chỉ trên `tenant_id`; nó thường không hiệu quả tương đương cho truy vấn chỉ lọc `customer_id` mà không có `tenant_id`.

Chọn thứ tự theo workload:

- Cột được dùng độc lập trong nhiều truy vấn có thể cần đứng đầu.
- Các điều kiện bằng nhau thường được đặt trước cột dùng cho range hoặc thứ tự sắp xếp, tùy truy vấn.
- Nếu mọi truy vấn luôn cung cấp `tenant_id`, đặt tenant ở đầu có thể hỗ trợ phân vùng logic và giới hạn phạm vi.
- Nếu truy vấn chính cần tìm theo `customer_id` trên mọi tenant, có thể cần chỉ mục khác bắt đầu bằng `customer_id` hoặc thay đổi cách truy vấn.

Đừng chọn thứ tự chỉ dựa trên cardinality cao nhất. Tần suất truy vấn, điều kiện lọc thực tế, phân bố dữ liệu và thứ tự ORDER BY cũng quyết định lợi ích.

## 6. Chỉ mục cho quan hệ nhiều-nhiều và bảng liên kết

Quan hệ nhiều-nhiều thường được biểu diễn bằng bảng liên kết (junction/bridge table). Ví dụ học viên đăng ký nhiều khóa học và mỗi khóa học có nhiều học viên:

```sql
CREATE TABLE enrollments (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    enrolled_at TIMESTAMP NOT NULL,
    PRIMARY KEY (student_id, course_id),
    FOREIGN KEY (student_id) REFERENCES students(student_id),
    FOREIGN KEY (course_id) REFERENCES courses(course_id)
);
```

Khóa chính ghép `(student_id, course_id)` tạo chỉ mục hỗ trợ tìm khóa học của một học viên và bảo đảm cặp đăng ký không trùng. Nhưng chỉ mục này không nhất thiết hỗ trợ tốt truy vấn đi theo chiều ngược lại:

```sql
SELECT student_id
FROM enrollments
WHERE course_id = ?;
```

Nếu truy vấn theo khóa học phổ biến, hãy cân nhắc chỉ mục đảo chiều:

```sql
CREATE INDEX ix_enrollments_course_student
    ON enrollments (course_id, student_id);
```

Chỉ mục thứ hai cũng có thể hỗ trợ JOIN từ `courses` sang `enrollments`. Nếu truy vấn cần `enrolled_at`, có thể đánh giá chỉ mục `(course_id, student_id, enrolled_at)` hoặc phương án bao phủ khác. Cần tính đến việc mỗi thao tác đăng ký hoặc hủy đăng ký phải duy trì cả hai chỉ mục.

Với bảng liên kết lớn, hãy kiểm tra:

- Các hướng truy vấn thường gặp: parent A sang child, parent B sang child, hoặc kết hợp cả hai.
- Có cần duy nhất cặp khóa hay cho phép nhiều bản ghi theo thời gian.
- Tỷ lệ hàng được đọc theo mỗi parent và phân bố khóa nóng.
- Chỉ mục hiện tại có hỗ trợ thứ tự sắp xếp hoặc phân trang không.
- Chi phí ghi và xóa khi cập nhật liên kết.

## 7. Chỉ mục và các thuật toán JOIN

Bộ tối ưu có thể lựa chọn các thuật toán JOIN khác nhau. Chỉ mục có thể ảnh hưởng mạnh đến một số thuật toán nhưng không có nghĩa mọi JOIN đều phải dùng index.

### Nested loop join

Nested loop thường lấy từng hàng từ đầu vào bên ngoài rồi tìm hàng phù hợp ở đầu vào bên trong. Nếu đầu vào ngoài nhỏ và đầu vào trong có chỉ mục trên cột JOIN, hệ quản trị có thể thực hiện nhiều lần index seek/lookup.

Ví dụ, tìm đơn hàng cho 10 khách hàng đã chọn. Chỉ mục `orders(customer_id)` có thể giúp truy xuất nhanh từng nhóm đơn hàng.

Nếu đầu vào ngoài có hàng triệu hàng, việc lặp index lookup hàng triệu lần có thể rất tốn kém. Khi đó hash join hoặc một phương án quét có thể rẻ hơn.

### Hash join

Hash join thường xây dựng bảng băm từ một đầu vào rồi dò đầu vào còn lại theo khóa nối. Nó thường phù hợp với các tập dữ liệu lớn và điều kiện bằng nhau. Chỉ mục trên cột JOIN không nhất thiết được dùng để tra từng hàng như nested loop; bộ tối ưu có thể chọn scan hai đầu vào.

Chỉ mục vẫn có thể hữu ích nếu giúp lọc một đầu vào trước khi hash, giảm số hàng hoặc giảm số cột cần đưa vào bảng băm. Cần kiểm tra bộ nhớ và hiện tượng spill ra đĩa khi hash table lớn hơn ngân sách.

### Merge join

Merge join kết hợp hai đầu vào đã được sắp xếp theo khóa nối. Chỉ mục có thứ tự phù hợp có thể cung cấp dữ liệu theo thứ tự cần thiết và tránh một bước sort. Nếu dữ liệu chưa được sắp xếp, hệ quản trị có thể phải sort trước khi nối.

Chỉ mục phục vụ merge join có thể có lợi khi truy vấn thường xuyên nối các tập lớn theo cùng một khóa và thứ tự. Tuy nhiên, sort có thể vẫn rẻ hơn duy trì một chỉ mục lớn nếu workload ít dùng đường truy cập đó.

| Thuật toán | Khi thường phù hợp | Vai trò của chỉ mục |
| --- | --- | --- |
| Nested loop | Một đầu vào nhỏ, tra cứu đầu vào kia theo từng hàng | Index seek trên đầu vào trong có thể giảm chi phí mỗi lần dò |
| Hash join | Hai tập lớn, nối bằng điều kiện bằng nhau | Có thể giúp lọc đầu vào; không nhất thiết dùng index lookup cho từng hàng |
| Merge join | Hai đầu vào có thể được đọc theo thứ tự khóa nối | Index có thứ tự phù hợp có thể tránh hoặc giảm sort |

Đừng ép thuật toán JOIN chỉ vì một chỉ mục tồn tại. Hãy kiểm tra số hàng thực tế, ước lượng của bộ tối ưu, chi phí sort/hash, số lần lookup và I/O.

## 8. JOIN kèm điều kiện lọc, sắp xếp và phân trang

Trong truy vấn thực tế, điều kiện JOIN thường kết hợp với WHERE, ORDER BY và LIMIT. Chỉ mục nên phục vụ mẫu truy vấn hoàn chỉnh.

Ví dụ lấy các đơn hàng đã thanh toán của một khách hàng, mới nhất trước:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = ?
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
```

Một chỉ mục ghép có thể được thử nghiệm:

```sql
CREATE INDEX ix_orders_customer_status_created
    ON orders (customer_id, status, created_at DESC);
```

Thứ tự trên đặt hai điều kiện bằng nhau trước cột thời gian. Nếu workload chủ yếu truy vấn theo tenant, trạng thái và ngày, cấu trúc phù hợp có thể khác. Nếu `status` có rất ít giá trị và truy vấn thường chỉ lọc theo status trên toàn bảng, chỉ mục bắt đầu bằng status có thể tạo ra đường truy cập khác nhưng cũng có thể có độ chọn lọc thấp.

Đối với truy vấn phân trang, chỉ mục nên hỗ trợ cả điều kiện lọc lẫn thứ tự ổn định. Keyset pagination theo `(created_at, order_id)` thường tránh phải bỏ qua một số lượng lớn hàng như OFFSET sâu, nhưng cần chỉ mục có thứ tự tương ứng và điều kiện so sánh đúng với chiều sắp xếp.

## 9. Kiểu dữ liệu, biểu thức và tính tương thích của khóa nối

Chỉ mục có thể không được dùng hiệu quả nếu hai phía JOIN có kiểu dữ liệu không tương thích hoặc hệ quản trị phải chuyển đổi một cột trong quá trình so sánh.

Ví dụ, nếu `orders.customer_id` là BIGINT nhưng `customers.customer_id` là VARCHAR, phép nối có thể phát sinh implicit conversion hoặc không thể dùng đường truy cập mong muốn. Thiết kế khóa liên kết nên thống nhất kiểu, độ dài và quy tắc so sánh.

Các biểu thức trên cột nối cũng có thể làm giảm khả năng dùng chỉ mục thông thường:

```sql
-- Có thể làm giảm khả năng dùng chỉ mục thông thường
ON CAST(o.customer_id AS VARCHAR(30)) = c.customer_code
```

Nếu cần nối theo biểu thức chuẩn hóa, hãy cân nhắc cột chuẩn hóa hoặc expression index nếu hệ quản trị hỗ trợ. Đảm bảo quy tắc chuyển đổi, collation và tính duy nhất phù hợp với ngữ nghĩa dữ liệu.

## 10. Khóa ngoại và thao tác DELETE/UPDATE ở bảng cha

Chỉ mục phía child không chỉ phục vụ SELECT JOIN. Khi xóa một hàng parent hoặc thay đổi khóa được tham chiếu, hệ quản trị phải xác định có hàng child nào đang tham chiếu đến nó hay không.

Ví dụ:

```sql
DELETE FROM customers
WHERE customer_id = 42;
```

Nếu có ràng buộc FK không cho phép xóa parent đang được tham chiếu, hệ quản trị cần kiểm tra các hàng `orders` có `customer_id = 42`. Nếu có `ON DELETE CASCADE`, nó cần tìm và xóa các hàng con tương ứng. Chỉ mục child có thể giúp định vị các hàng đó.

Khi không có chỉ mục, việc kiểm tra có thể cần quét bảng child. Điều này có thể làm thao tác xóa parent chậm và giữ khóa lâu hơn. Với bảng child rất lớn, tác động còn có thể ảnh hưởng các giao dịch đồng thời.

Tuy nhiên, chỉ mục không làm cho một thao tác cascade xóa hàng triệu bản ghi trở nên rẻ. Nó giúp tìm hàng nhanh hơn; hệ thống vẫn phải xóa dữ liệu, cập nhật mọi chỉ mục liên quan và ghi log giao dịch. Hãy kiểm tra số lượng hàng bị tác động, thời gian transaction, lock wait và kích thước log.

## 11. Đọc execution plan để xác minh chỉ mục

Đừng kết luận chỉ mục có ích chỉ vì truy vấn chạy nhanh trong một lần thử. Hãy đọc kế hoạch thực thi và số liệu thực tế.

Các điểm cần kiểm tra:

- Bảng nào là outer input và bảng nào là inner input trong nested loop.
- JOIN dùng nested loop, hash join hay merge join.
- Có Index Seek/Scan, Index Lookup, Key Lookup hoặc Heap Fetch không.
- Estimated rows có gần Actual rows không.
- Số lần thực thi (loops) của một operator có cao bất thường không.
- Có sort, hash spill hoặc đọc quá nhiều trang không.
- Chỉ mục có được dùng để lọc trước khi JOIN hay chỉ để tra cứu sau khi đã đọc nhiều hàng.
- Thời gian CPU, elapsed time, logical reads và physical reads thay đổi ra sao.

### Ví dụ với PostgreSQL

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT o.order_id, c.customer_name
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE c.customer_id = 42;
```

Kiểm tra `Nested Loop`, `Hash Join` hoặc `Merge Join`, các node scan, `actual rows`, `loops` và thông tin buffer. `EXPLAIN ANALYZE` thực thi câu lệnh để đo; với câu lệnh ghi, cần hiểu tác dụng phụ và dùng môi trường hoặc transaction thử nghiệm phù hợp.

### Ví dụ với SQL Server

```sql
SET STATISTICS IO, TIME ON;

SELECT o.OrderId, c.CustomerName
FROM dbo.Customers AS c
JOIN dbo.Orders AS o
  ON o.CustomerId = c.CustomerId
WHERE c.CustomerId = 42;

SET STATISTICS IO, TIME OFF;
```

Đọc actual execution plan và thông báo STATISTICS IO/TIME. Chú ý logical reads của từng bảng, số hàng thực tế, số lần lookup và operator có spill. Một index seek không tự động chứng minh kế hoạch tối ưu nếu nó dẫn đến rất nhiều lookup.

## 12. Quy trình đánh giá chỉ mục cho FK và JOIN

1. **Liệt kê mẫu truy vấn.** Tìm các JOIN thường chạy, thao tác xóa/cập nhật parent và truy vấn lọc theo FK.
2. **Xác định quan hệ và hướng truy cập.** Ghi rõ bảng parent, child, khóa đơn hay ghép, quan hệ một-một, một-nhiều hoặc nhiều-nhiều.
3. **Kiểm tra chỉ mục hiện có.** Xác nhận chỉ mục PK/UNIQUE phía parent, chỉ mục phía child và thứ tự cột. Tránh tạo bản sao có cùng tiền tố và chức năng.
4. **Đo phân bố dữ liệu.** Xem số hàng mỗi parent, cardinality, giá trị nóng, tỷ lệ NULL và số hàng được truy vấn chọn.
5. **Đọc kế hoạch hiện tại.** Ghi loại JOIN, scan/seek, lookup, estimated/actual rows, loops, sort/hash và số trang đọc.
6. **Đề xuất chỉ mục theo mẫu truy vấn.** Chọn cột JOIN trước hoặc theo thứ tự điều kiện bằng nhau, sau đó cân nhắc range, sort và cột bao phủ.
7. **Thử trên dữ liệu đại diện.** Giữ nguyên workload, tốc độ đến, concurrency, trạng thái cache và phân bố tham số.
8. **Đo lợi ích và chi phí.** So sánh p50/p95/p99, throughput, logical reads, physical reads, CPU, dung lượng chỉ mục và thời gian ghi.
9. **Kiểm tra tác động phụ.** Đánh giá INSERT/UPDATE/DELETE, cascade, lock wait, deadlock, log và bảo trì chỉ mục.
10. **Theo dõi sau triển khai.** Xem mức sử dụng chỉ mục, plan regression và thay đổi phân bố dữ liệu trong tải thực tế.

## 13. Ví dụ tổng hợp: chỉ mục cho đơn hàng và khách hàng

Giả sử workload có ba truy vấn phổ biến:

1. Lấy thông tin khách hàng từ một đơn hàng.
2. Liệt kê 20 đơn hàng mới nhất của một khách hàng.
3. Xóa khách hàng đã được xác nhận không còn đơn hàng.

Khóa chính `customers(customer_id)` đã có chỉ mục. Các truy vấn thứ hai và thứ ba cần tìm hàng trong `orders` theo `customer_id`; truy vấn thứ hai còn lọc/sắp xếp theo thời gian.

Một chỉ mục ghép có thể đáp ứng cả hai:

```sql
CREATE INDEX ix_orders_customer_created
    ON orders (customer_id, created_at DESC);
```

Chỉ mục này bắt đầu bằng `customer_id`, nên có thể hỗ trợ tìm đơn hàng theo khách hàng và kiểm tra các hàng con theo FK. Phần `created_at` hỗ trợ đọc đơn hàng mới nhất theo thứ tự trong nhóm khách hàng.

Nếu truy vấn đầu tiên bắt đầu từ một đơn hàng đã biết, khóa chính `orders(order_id)` tìm được hàng đơn hàng; sau đó chỉ mục PK của `customers` tìm khách hàng. Không cần thêm chỉ mục mới cho hướng đó.

Trước khi triển khai, hãy kiểm tra chỉ mục hiện có có bắt đầu bằng `customer_id` hay không. Nếu đã có `(customer_id, status, created_at)`, có thể nó đã hỗ trợ một số truy vấn và kiểm tra FK; thêm `(customer_id, created_at)` có thể trùng lặp hoặc vẫn cần thiết tùy cách sử dụng. Chỉ giữ cả hai khi có bằng chứng workload cho thấy lợi ích.

## 14. Những sai lầm thường gặp

- **Cho rằng khai báo FK tự động tạo chỉ mục ở mọi hệ quản trị.** Hành vi khác nhau; cần kiểm tra chỉ mục thực tế.
- **Chỉ mục hóa mọi cột FK mà không đo.** Chỉ mục làm tăng chi phí ghi và dung lượng, trong khi bảng nhỏ có thể quét nhanh.
- **Chỉ nhìn phía parent.** PK/UNIQUE phía parent thường đã được lập chỉ mục; nhiều vấn đề JOIN và cascade nằm ở phía child.
- **Bỏ qua thứ tự cột trong chỉ mục ghép.** Chỉ mục không có tiền tố phù hợp có thể không hỗ trợ truy vấn cần thiết.
- **Tạo chỉ mục trùng lặp.** Chỉ mục hiện có có thể đã bắt đầu bằng cột FK và đáp ứng cùng đường truy cập.
- **Cho rằng mọi JOIN đều cần index seek.** Hash join hoặc sequential scan có thể tốt hơn khi phải xử lý nhiều hàng.
- **Chỉ kiểm tra một giá trị khóa.** Phân bố lệch và khóa nóng có thể làm hiệu năng khác nhau đáng kể.
- **Bỏ qua DELETE/UPDATE và cascade.** Truy vấn kiểm tra hàng con có thể quét bảng lớn nếu thiếu chỉ mục.
- **Chỉ đo SELECT.** Chỉ mục mới có thể làm INSERT, UPDATE, DELETE chậm hơn.
- **Không kiểm tra kiểu dữ liệu hai phía JOIN.** Implicit conversion hoặc biểu thức có thể làm giảm hiệu quả chỉ mục.

## 15. Danh sách kiểm tra trước khi tạo chỉ mục

- [ ] Đã xác định rõ bảng parent, child và cột FK được tham chiếu.
- [ ] Đã kiểm tra hệ quản trị có tự tạo chỉ mục FK hay không.
- [ ] Khóa parent có PRIMARY KEY hoặc UNIQUE phù hợp.
- [ ] Đã kiểm tra các chỉ mục hiện có và tránh chỉ mục trùng lặp.
- [ ] Đã thu thập truy vấn JOIN, DELETE/UPDATE và cascade thực tế.
- [ ] Thứ tự cột của chỉ mục ghép phù hợp với điều kiện JOIN, WHERE và ORDER BY.
- [ ] Kiểu dữ liệu, độ dài và collation của hai phía JOIN tương thích.
- [ ] Đã xem phân bố số hàng child trên mỗi parent và độ chọn lọc.
- [ ] Execution plan và số liệu logical/physical reads được ghi nhận trước/sau.
- [ ] Đã đo throughput, độ trễ và chi phí INSERT/UPDATE/DELETE.
- [ ] Đã đánh giá dung lượng, cache footprint, lock wait và chi phí bảo trì.
- [ ] Chỉ mục được theo dõi trong workload thực tế sau khi triển khai.

## Kết luận

Chỉ mục cho khóa ngoại và phép nối cần được thiết kế theo cả hai phía của quan hệ và theo hướng truy cập thực tế. Khóa chính hoặc UNIQUE phía parent thường đã có chỉ mục, trong khi phía child có thể cần chỉ mục để tìm hàng tham chiếu, hỗ trợ JOIN và giảm chi phí kiểm tra DELETE/UPDATE hoặc cascade. Với workload nhiều điều kiện, chỉ mục ghép phải có thứ tự cột phù hợp; với bảng liên kết nhiều-nhiều, có thể cần hỗ trợ cả hai hướng truy vấn. Hãy đọc execution plan, đo số hàng và số trang thực tế, sau đó cân bằng lợi ích đọc với chi phí ghi, dung lượng và bảo trì trước khi quyết định giữ chỉ mục.
