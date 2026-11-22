# Chỉ mục hỗ trợ phép nối và lựa chọn phía truy cập

Trong một truy vấn kết hợp nhiều bảng, chỉ mục có thể giúp hệ quản trị tìm nhanh các dòng khớp với khóa nối, thu hẹp dữ liệu trước khi nối hoặc cung cấp thứ tự cần thiết cho phép nối. Tuy nhiên, việc tạo chỉ mục trên mọi cột xuất hiện trong điều kiện JOIN không bảo đảm truy vấn sẽ nhanh hơn. Lợi ích phụ thuộc vào thuật toán nối, số dòng của mỗi phía, độ chọn lọc của điều kiện lọc, thứ tự cột trong chỉ mục và chi phí đọc dữ liệu thực tế.

Trong phạm vi **DATABASE_PERFORMANCE**, tối ưu hiệu năng cơ sở dữ liệu cần dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Bài học này trình bày cách thiết kế chỉ mục hỗ trợ phép nối, cách optimizer lựa chọn phía truy cập, và cách đánh giá liệu index lookup, hash join hay merge join phù hợp với workload.

## 1. Vai trò của chỉ mục trong phép nối

Phép nối (join) kết hợp dòng từ hai quan hệ theo một điều kiện. Ví dụ:

~~~sql
SELECT
    c.customer_id,
    c.customer_name,
    o.order_id,
    o.created_at
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE c.region = 'NORTH';
~~~

Hệ quản trị cần tìm những đơn hàng có customer_id khớp với khách hàng thuộc khu vực NORTH. Có nhiều cách thực hiện:

- Quét customers để tìm khách hàng phù hợp, rồi tra cứu orders theo customer_id.
- Quét orders, sau đó tra cứu customers theo customer_id.
- Đọc hai tập dữ liệu, xây dựng cấu trúc băm và dò tìm khóa khớp.
- Đọc hai tập dữ liệu theo thứ tự khóa nối rồi ghép các dòng có khóa tương ứng.

Chỉ mục có thể hỗ trợ các phương án này theo những cách khác nhau:

1. Tìm nhanh dòng ở phía được tra cứu trong nested loop join.
2. Giảm số dòng đầu vào nhờ điều kiện lọc trên cột không phải khóa nối.
3. Cung cấp thứ tự khóa cho merge join hoặc tránh một bước sort.
4. Bao phủ các cột cần đọc để giảm truy cập bảng.
5. Giúp thực hiện các truy vấn tham chiếu khóa ngoại hoặc kiểm tra sự tồn tại.

Một chỉ mục có thể rất hữu ích với một thuật toán nối nhưng không được sử dụng trong thuật toán khác. Ví dụ, hash join thường đọc đầu vào để xây hash table và probe; nó không cần index lookup trên khóa nối để tìm từng dòng khớp. Chỉ mục vẫn có thể giúp lọc một trong hai đầu vào trước khi hash join diễn ra.

## 2. Chọn phía truy cập trong nested loop join

Nested loop join xử lý từng dòng của một đầu vào rồi tìm các dòng khớp ở đầu vào còn lại. Có thể hình dung:

~~~text
Outer input
    |
    | lấy từng dòng
    v
Inner input lookup
    |
    | tìm dòng có khóa nối tương ứng
    v
Ghép kết quả
~~~

- **Outer side:** phía cung cấp các dòng để lặp qua.
- **Inner side:** phía được truy cập lặp lại cho từng dòng outer.

Nếu outer side chỉ có vài chục hoặc vài trăm dòng sau lọc, một chỉ mục trên khóa nối của inner side có thể giúp mỗi lần tra cứu rất nhanh.

Ví dụ, truy vấn lọc khách hàng theo region rồi lấy đơn hàng:

~~~sql
SELECT
    c.customer_id,
    o.order_id,
    o.created_at
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE c.region = 'NORTH';
~~~

Một phương án có thể là:

1. Dùng chỉ mục trên customers.region để tìm khách hàng ở NORTH.
2. Với mỗi customer_id tìm được, dùng chỉ mục trên orders.customer_id để lấy các đơn hàng tương ứng.
3. Trả kết quả nối.

Chỉ mục hỗ trợ phía inner có thể là:

~~~sql
CREATE INDEX idx_orders_customer
ON orders (customer_id);
~~~

Nếu truy vấn còn lọc theo trạng thái đơn hàng:

~~~sql
SELECT
    c.customer_id,
    o.order_id,
    o.created_at
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE c.region = 'NORTH'
  AND o.status = 'PAID';
~~~

Một chỉ mục ghép trên orders có thể được cân nhắc:

~~~sql
CREATE INDEX idx_orders_customer_status
ON orders (customer_id, status);
~~~

Khi customer_id được cố định cho mỗi lần lookup, hệ quản trị có thể tiếp tục lọc status trong phạm vi khóa đó. Lợi ích cần được xác nhận bằng execution plan và số dòng thực tế.

### Vì sao số dòng outer quan trọng?

Giả sử outer có 50 dòng và mỗi lần tra cứu inner dùng index seek chi phí thấp. Nested loop có thể chỉ cần vài chục lần lookup.

Nếu outer có 2 triệu dòng, cùng index lookup có thể phải thực hiện 2 triệu lần. Ngay cả khi mỗi lần lookup nhanh, tổng chi phí truy cập ngẫu nhiên có thể rất lớn.

Do đó, cần quan sát:

- Actual rows của outer side.
- Số lần lặp (loops) của inner node.
- Số dòng tìm được trong mỗi lần lookup.
- Buffer hit/read và số lần truy cập bảng.
- Tổng thời gian của node inner và toàn bộ phép nối.

Không nên đánh giá nested loop chỉ bằng việc thấy index được sử dụng. Một kế hoạch có index lookup nhưng lặp hàng triệu lần vẫn có thể rất chậm.

## 3. Chỉ mục trên khóa nối ở cả hai phía

Với quan hệ customers và orders, customers.customer_id thường là khóa chính và đã có unique index. orders.customer_id là khóa ngoại tham chiếu customers.

Hai phía có vai trò khác nhau:

- Chỉ mục trên customers.customer_id hỗ trợ tìm một khách hàng theo khóa.
- Chỉ mục trên orders.customer_id hỗ trợ tìm các đơn hàng thuộc một khách hàng.

Nếu truy vấn bắt đầu từ orders đã được lọc rất mạnh, rồi tra cứu customers theo khóa chính, index trên customers.customer_id là đường truy cập tự nhiên. Nếu truy vấn bắt đầu từ một tập customers nhỏ rồi tìm đơn hàng, index trên orders.customer_id có thể rất quan trọng.

Không phải lúc nào cũng cần hai chỉ mục mới. Chỉ mục khóa chính có thể đã tồn tại. Hãy kiểm tra các chỉ mục hiện có trước khi tạo thêm.

### Chỉ mục trên cột khóa ngoại

Trong nhiều hệ quản trị, khai báo foreign key không đồng nghĩa hệ thống luôn tự tạo chỉ mục trên cột tham chiếu. PostgreSQL không tự động tạo index cho phía referencing column khi khai báo foreign key. Vì vậy, nếu workload thường xuyên nối hoặc tìm dòng con theo khóa ngoại, cần cân nhắc tạo chỉ mục phù hợp.

Ví dụ:

~~~sql
CREATE INDEX idx_orders_customer_id
ON orders (customer_id);
~~~

Chỉ mục trên cột khóa ngoại còn có thể giúp hệ quản trị kiểm tra các dòng con khi cập nhật hoặc xóa dòng cha. Nếu thiếu index, một số thao tác tham chiếu có thể phải quét bảng con để tìm khóa liên quan.

Một số hệ quản trị khác có thể tự tạo hoặc yêu cầu index ở một số tình huống. Cần kiểm tra hành vi của hệ quản trị cụ thể, tránh tạo trùng index đã được hệ thống sinh.

## 4. Chọn thứ tự cột trong chỉ mục ghép

Một phép nối thường đi kèm điều kiện lọc. Khi đó, chỉ mục ghép (composite index) có thể phục vụ cả việc tìm khóa nối và lọc dòng.

Giả sử truy vấn:

~~~sql
SELECT
    o.order_id,
    o.created_at,
    o.total_amount
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE c.region = 'NORTH'
  AND o.status = 'PAID'
  AND o.created_at >= TIMESTAMP '2026-01-01';
~~~

Nếu optimizer dùng customers làm outer và tra cứu orders làm inner, chỉ mục trên orders có thể được thiết kế theo:

~~~sql
CREATE INDEX idx_orders_customer_status_date
ON orders (customer_id, status, created_at);
~~~

Trong mỗi lần tra cứu, customer_id được xác định từ outer row; status được so khớp bằng; created_at là điều kiện phạm vi.

Nếu truy vấn chủ yếu lọc orders theo status và khoảng ngày trước khi nối với customers, một thứ tự khác có thể hợp lý:

~~~sql
CREATE INDEX idx_orders_status_date_customer
ON orders (status, created_at, customer_id);
~~~

Hai index không tương đương. B-tree thường tận dụng hiệu quả các cột tiền tố của chỉ mục. Khi cột đầu tiên không được ràng buộc, các cột phía sau có thể không tạo ra một range scan tương đương với trường hợp dùng tiền tố.

### Nguyên tắc lựa chọn thứ tự cột

Khi thiết kế index ghép cho join, hãy xem:

- Cột nào được dùng làm điều kiện bằng?
- Cột nào được dùng làm điều kiện phạm vi?
- Phía nào được chọn làm outer và phía nào được tra cứu?
- Có ORDER BY hoặc GROUP BY cần được hỗ trợ không?
- Các truy vấn khác có dùng tiền tố trái của index không?
- Phân bố dữ liệu và độ chọn lọc của từng cột ra sao?

Không có quy tắc đơn giản rằng cột có độ chọn lọc cao nhất luôn phải đứng đầu. Thứ tự phù hợp phụ thuộc vào mẫu điều kiện, phạm vi truy vấn, khả năng tái sử dụng index và cách optimizer tạo access path.

### Tránh tạo nhiều index gần giống nhau

Nếu đã có index (customer_id, status, created_at), một index riêng (customer_id) có thể không cần thiết cho một số workload vì index ghép có thể hỗ trợ tra cứu theo tiền tố customer_id. Tuy nhiên, index ghép lớn hơn và có thể không thay thế hoàn toàn index đơn trong mọi tình huống.

Cần so sánh kích thước, cache footprint, tốc độ ghi và kế hoạch thực tế trước khi loại bỏ index cũ.

## 5. Chỉ mục hỗ trợ hash join

Hash join thường gồm hai giai đoạn:

1. Đọc một đầu vào và xây dựng hash table theo khóa nối (build side).
2. Đọc đầu vào còn lại, tính hash của khóa và dò trong hash table (probe side).

~~~text
Build input                Probe input
    |                           |
    v                           v
Build hash table          Read each row
    |                           |
    +------------+--------------+
                 |
                 v
          Match join keys
                 |
                 v
            Join output
~~~

Trong hash join, chỉ mục trên khóa nối không nhất thiết được dùng để tìm từng dòng. Hệ quản trị thường cần đọc toàn bộ tập dữ liệu được chọn để xây dựng và dò hash table.

Tuy nhiên, chỉ mục vẫn có thể hữu ích:

- Lọc build input hoặc probe input trước khi join.
- Cung cấp dữ liệu từ một index-only/covering access nếu rẻ hơn đọc bảng.
- Hỗ trợ các điều kiện lọc khác ngoài khóa nối.
- Giảm kích thước dữ liệu đầu vào nếu index access chọn lọc.

### Chọn build side và probe side

Optimizer thường muốn build hash table từ phía có kích thước phù hợp, thường là phía nhỏ hơn sau khi lọc, vì hash table cần bộ nhớ. Nếu ước lượng sai, phía build có thể lớn hơn nhiều so với dự kiến và hash join có thể phải chia batch hoặc spill ra vùng nhớ tạm.

Khi đọc plan, xem:

- Số dòng và độ rộng của build input.
- Số dòng của probe input.
- Bộ nhớ sử dụng và số batch.
- Temp read/write hoặc dấu hiệu spill.
- Estimated rows so với actual rows.

Không nên thêm index trên khóa nối chỉ để cố biến hash join thành index lookup. Nếu hai phía đều lớn và phần lớn dữ liệu cần được đọc, hash join với scan có thể rẻ hơn nhiều lần truy cập ngẫu nhiên qua index.

## 6. Chỉ mục hỗ trợ merge join

Merge join kết hợp hai đầu vào đã được sắp xếp theo khóa nối. Khi cả hai đầu vào đã có thứ tự phù hợp, hệ quản trị có thể tiến hành ghép tuần tự các khóa.

B-tree index có thể cung cấp thứ tự này nếu:

- Index được tạo trên cột nối hoặc tiền tố phù hợp.
- Điều kiện lọc không làm mất khả năng sử dụng thứ tự.
- Chiều sắp xếp và collation tương thích.
- Optimizer đánh giá index scan rẻ hơn sort.

Ví dụ, giả sử orders có chỉ mục trên customer_id và customers.customer_id là khóa chính nên đã có unique index:

~~~sql
CREATE INDEX idx_orders_customer
ON orders (customer_id);
~~~

Một merge join theo customer_id có thể tận dụng thứ tự từ index scan nếu kế hoạch và chi phí phù hợp.

Tuy nhiên, việc có index không bảo đảm merge join được chọn. Nếu index scan phải đọc gần toàn bộ bảng và truy cập heap nhiều lần, sequential scan cộng sort có thể rẻ hơn. Nếu dữ liệu đã có thứ tự nhờ một bước trước đó, merge join có thể không cần sort.

### Sort có thể làm mất lợi ích của index

Nếu một phía cần sắp xếp rất nhiều dòng trước khi merge, tổng chi phí sort có thể lớn. Hãy so sánh:

- Chi phí index scan để lấy dòng theo thứ tự.
- Chi phí table scan rồi sort.
- Bộ nhớ sort và temp I/O khi tràn ra đĩa.
- Số dòng thực tế ở hai phía.

## 7. Chỉ mục bao phủ và giảm truy cập bảng trong phép nối

Một index có thể chứa cả cột nối, cột lọc và cột được SELECT. Khi đó hệ quản trị có thể lấy phần lớn dữ liệu từ chỉ mục mà không phải đọc bảng cho từng dòng, tùy engine và điều kiện visibility.

Ví dụ:

~~~sql
SELECT
    o.customer_id,
    o.order_id,
    o.created_at
FROM orders AS o
WHERE o.status = 'PAID'
  AND o.created_at >= TIMESTAMP '2026-01-01';
~~~

Một chỉ mục có thể được thiết kế:

~~~sql
CREATE INDEX idx_orders_status_date
ON orders (status, created_at)
INCLUDE (customer_id, order_id);
~~~

PostgreSQL hỗ trợ INCLUDE để lưu các cột không tham gia khóa tìm kiếm trong leaf entries của B-tree. MySQL InnoDB có cách tổ chức secondary index khác; primary key thường được lưu kèm trong secondary index, và không có cú pháp INCLUDE tương đương theo cùng nghĩa. Cần thiết kế theo khả năng của từng engine.

Trong một truy vấn join, covering index có thể giảm số lần truy cập bảng ở phía inner. Nhưng index càng rộng thì:

- Dung lượng càng lớn.
- Ít trang index hơn có thể nằm trong cache.
- INSERT/UPDATE/DELETE tốn thêm công việc.
- Cập nhật cột được lưu trong index có thể gây ghi lại index.
- Chi phí bảo trì và vacuum/reorganization có thể tăng tùy hệ quản trị.

Chỉ thêm cột INCLUDE hoặc cột phụ khi số liệu cho thấy giảm truy cập bảng có giá trị rõ ràng.

## 8. Phép nối nhiều-nhiều và chỉ mục trên bảng trung gian

Trong quan hệ nhiều-nhiều, bảng trung gian (bridge table hoặc junction table) thường chứa hai khóa ngoại.

Ví dụ students và courses được nối qua enrollments:

~~~sql
SELECT
    s.student_name,
    c.course_name
FROM students AS s
JOIN enrollments AS e
    ON e.student_id = s.student_id
JOIN courses AS c
    ON c.course_id = e.course_id
WHERE s.student_id = 1001;
~~~

Một chỉ mục ghép:

~~~sql
CREATE INDEX idx_enrollments_student_course
ON enrollments (student_id, course_id);
~~~

phù hợp khi bắt đầu từ một student và tìm các course đã đăng ký.

Nếu workload thường bắt đầu từ course để tìm tất cả student:

~~~sql
SELECT
    s.student_name
FROM courses AS c
JOIN enrollments AS e
    ON e.course_id = c.course_id
JOIN students AS s
    ON s.student_id = e.student_id
WHERE c.course_id = 200;
~~~

một index theo chiều ngược lại có thể cần thiết:

~~~sql
CREATE INDEX idx_enrollments_course_student
ON enrollments (course_id, student_id);
~~~

Chỉ mục (student_id, course_id) không tương đương với (course_id, student_id). Cả hai có thể cần nếu workload truy cập thường xuyên theo hai chiều và lợi ích vượt chi phí ghi/dung lượng.

Nếu cặp student_id, course_id phải duy nhất, có thể dùng unique constraint/index để vừa bảo vệ tính toàn vẹn vừa hỗ trợ truy vấn theo tiền tố phù hợp.

## 9. Chỉ mục và phép nối có điều kiện lọc ở cả hai bảng

Một truy vấn thường có điều kiện trên cả hai phía:

~~~sql
SELECT
    c.customer_id,
    o.order_id
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE c.region = 'CENTRAL'
  AND o.status = 'SHIPPED';
~~~

Có thể cân nhắc index trên customers(region, customer_id) và orders(customer_id, status), hoặc một thiết kế khác tùy phía truy cập.

Nếu optimizer chọn lọc customers trước, index region có thể giảm outer input. Nếu mỗi khách hàng sau đó tra cứu orders, index orders(customer_id, status) có thể hỗ trợ inner lookup.

Nếu optimizer chọn lọc orders trước theo status, index orders(status, customer_id) có thể hỗ trợ tạo outer input nhỏ rồi tra cứu customers theo primary key.

Lựa chọn phía truy cập phụ thuộc ước lượng số dòng sau lọc. Cần kiểm tra histogram, giá trị phổ biến và tham số thực tế. Một region có thể chứa 2% khách hàng trong khi status SHIPPED có thể chứa 80% đơn hàng; khi đó bắt đầu từ customers có thể rẻ hơn. Nhưng với một trạng thái rất hiếm hoặc một khoảng ngày chọn lọc, hướng ngược lại có thể tốt hơn.

## 10. Những trường hợp index trên khóa nối không được sử dụng

Có nhiều lý do khiến optimizer không chọn index dù cột xuất hiện trong điều kiện JOIN:

### Hash join có chi phí thấp hơn

Nếu phải đọc phần lớn hai bảng, scan và hash join có thể ít tốn kém hơn index lookup lặp lại.

### Điều kiện nối không chọn lọc

Nếu mỗi dòng ở phía outer khớp với nhiều dòng inner và phần lớn bảng cần được đọc, index có thể không giảm lượng dữ liệu đáng kể.

### Sai kiểu dữ liệu hoặc ép kiểu

Ví dụ nối một cột integer với một biểu thức text phải chuyển kiểu. Nếu phép chuyển đổi được áp dụng lên cột được đánh chỉ mục, optimizer có thể không dùng index theo cách mong đợi.

Nên bảo đảm hai cột join có kiểu dữ liệu tương thích và tránh chuyển đổi không cần thiết trên cột được truy cập.

### Hàm hoặc biểu thức trên khóa

Ví dụ:

~~~sql
ON LOWER(a.email) = LOWER(b.email)
~~~

Index B-tree thông thường trên email có thể không phục vụ trực tiếp biểu thức LOWER(email). Một số hệ quản trị hỗ trợ expression/function-based index; lựa chọn cụ thể phụ thuộc engine và collation. Cần kiểm tra tính đúng đắn của chuẩn hóa chuỗi, Unicode và quy tắc so sánh.

### Thống kê không chính xác

Nếu số dòng ước lượng sai, optimizer có thể chọn hướng truy cập không phù hợp. Cập nhật thống kê và so sánh estimated rows với actual rows là bước điều tra quan trọng.

### Index có độ chọn lọc thấp

Nếu giá trị khóa lặp lại trên phần lớn bảng, index lookup có thể phải đọc rất nhiều dòng và trang heap. Scan tuần tự có thể rẻ hơn.

### Điều kiện nối có NULL hoặc ngữ nghĩa đặc biệt

Với phép so sánh bằng thông thường, NULL không khớp với NULL. Với null-safe equality hoặc các phép nối đặc biệt, hành vi và khả năng dùng index phụ thuộc hệ quản trị. Không thay đổi ngữ nghĩa chỉ để làm optimizer dùng index.

## 11. Outer join và vị trí điều kiện lọc

LEFT JOIN giữ lại mọi dòng ở phía trái, kể cả khi không có dòng phù hợp ở phía phải. Điều này ảnh hưởng đến thứ tự truy cập và việc đẩy điều kiện lọc.

Ví dụ:

~~~sql
SELECT
    c.customer_id,
    o.order_id
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'PAID'
WHERE c.region = 'NORTH';
~~~

Một chỉ mục trên orders có thể hỗ trợ tra cứu theo customer_id và status khi customers là outer:

~~~sql
CREATE INDEX idx_orders_customer_status
ON orders (customer_id, status);
~~~

Nếu chuyển điều kiện o.status = 'PAID' từ ON sang WHERE, các dòng không có đơn PAID sẽ có o.status = NULL và bị loại bỏ. Kết quả có thể thay đổi từ giữ tất cả khách hàng sang chỉ giữ khách hàng có đơn phù hợp.

Vì vậy, không nên di chuyển điều kiện chỉ để ép optimizer dùng một index. Phải giữ đúng ngữ nghĩa trước, rồi đánh giá access path phù hợp.

## 12. Chỉ mục cho EXISTS, semi join và anti join

Khi truy vấn chỉ cần biết một dòng có dòng liên quan hay không, EXISTS thường diễn đạt ý định rõ ràng:

~~~sql
SELECT c.customer_id, c.customer_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
~~~

Optimizer có thể biến đổi thành semi join hoặc một chiến lược tương đương. Với nested-loop semi join, index trên orders(customer_id, status) có thể giúp tìm nhanh dòng đầu tiên thỏa điều kiện.

Với NOT EXISTS:

~~~sql
SELECT c.customer_id
FROM customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
);
~~~

index trên orders.customer_id có thể giúp kiểm tra sự tồn tại. Tuy nhiên, nếu nhiều khách hàng được kiểm tra và phần lớn không có đơn, chiến lược tối ưu vẫn phụ thuộc số dòng, thống kê và thuật toán anti join.

Không nên thay NOT EXISTS bằng NOT IN một cách máy móc vì NULL có thể làm thay đổi kết quả logic.

## 13. Lựa chọn access path theo từng thuật toán join

Bảng sau tóm tắt vai trò thường gặp của index:

| Thuật toán join | Vai trò của index | Khi có lợi | Khi có thể không lợi |
|---|---|---|---|
| Nested loop | Index lookup ở inner side; index lọc outer side | Outer nhỏ, lookup chọn lọc, số vòng lặp thấp | Outer rất lớn, inner lookup lặp nhiều và đọc rải rác |
| Hash join | Có thể lọc đầu vào hoặc cung cấp covering access | Index giảm đáng kể build/probe input | Hai phía cần đọc phần lớn bảng; scan tuần tự rẻ hơn |
| Merge join | Cung cấp thứ tự theo khóa nối, giảm sort | Cả hai phía có thứ tự phù hợp và index scan có chi phí hợp lý | Index scan đọc nhiều trang ngẫu nhiên hoặc vẫn phải sort lớn |
| Semi/anti join | Hỗ trợ kiểm tra tồn tại hoặc không tồn tại | Lookup theo khóa nối có chọn lọc | Tập đầu vào lớn hoặc số dòng phù hợp quá nhiều |

Các mô tả này là hướng dẫn phân tích, không phải quy tắc bắt buộc. Optimizer có thể chọn kế hoạch khác tùy hệ quản trị, phiên bản, thống kê và cấu hình.

## 14. Đọc execution plan để kiểm tra index hỗ trợ join

Khi truy vấn chậm, hãy bắt đầu từ kế hoạch thực thi thay vì suy luận chỉ từ câu SQL.

Ví dụ PostgreSQL:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    c.customer_id,
    o.order_id,
    o.created_at
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE c.region = 'NORTH'
  AND o.status = 'PAID';
~~~

Các dấu hiệu cần xem:

- **Nested Loop:** node nào là outer, node nào là inner?
- **Index Scan / Index Only Scan:** index được dùng ở phía nào và điều kiện nào?
- **Hash Join:** kích thước build side, số batch và temp I/O?
- **Merge Join:** đầu vào đã có thứ tự hay cần Sort?
- **Actual rows:** số dòng thực tế sau lọc và sau join?
- **Loops:** inner lookup được lặp bao nhiêu lần?
- **Buffers:** có nhiều heap block hoặc index block được đọc không?
- **Rows Removed by Filter:** có đọc nhiều dòng rồi loại bỏ phần lớn không?

Với PostgreSQL, EXPLAIN ANALYZE thực thi câu truy vấn. Cần chọn truy vấn phù hợp và môi trường có thể chịu tải. Với câu lệnh ghi, phải hiểu tác động và transaction trước khi chạy.

### So sánh estimated rows với actual rows

Nếu optimizer ước lượng outer có 100 dòng nhưng thực tế có 500.000 dòng, nested loop với index lookup có thể trở nên rất đắt. Tìm node đầu tiên có sai lệch lớn, sau đó kiểm tra thống kê, phân bố tham số và tương quan giữa các cột.

Nếu actual rows thấp hơn nhiều so với ước lượng, optimizer có thể đã chọn hash join hoặc scan rộng trong khi một index lookup có thể rẻ hơn.

### Đo cả truy vấn và workload

Một index mới có thể cải thiện truy vấn mục tiêu nhưng làm tăng thời gian ghi hoặc khiến các truy vấn khác chọn kế hoạch kém. Hãy đo:

- p50, p95, p99 của truy vấn.
- Số lần gọi và throughput.
- CPU, buffers, I/O và temp I/O.
- Thời gian INSERT/UPDATE/DELETE.
- Dung lượng index và ảnh hưởng đến cache.
- Hiệu năng các truy vấn khác trên cùng bảng.

## 15. Ví dụ lựa chọn index cho hai hướng truy cập

Giả sử có:

- customers: 5 triệu dòng.
- orders: 80 triệu dòng.
- customers.customer_id là primary key.
- orders.customer_id là foreign key.
- region phân bố tương đối đều, còn status có giá trị PAID rất phổ biến và CANCELLED hiếm.

Truy vấn:

~~~sql
SELECT c.customer_name, o.order_id
FROM customers AS c
JOIN orders AS o
    ON o.customer_id = c.customer_id
WHERE c.region = 'NORTH'
  AND o.status = 'CANCELLED';
~~~

Có hai hướng đáng đánh giá.

### Hướng A: lọc khách hàng rồi tra cứu đơn hàng

Nếu region NORTH chỉ chọn một tỷ lệ nhỏ khách hàng, optimizer có thể dùng index trên customers.region để tạo outer input nhỏ. Sau đó index trên orders(customer_id, status) hỗ trợ tra cứu đơn theo từng khách hàng.

### Hướng B: lọc đơn hàng rồi tra cứu khách hàng

Nếu CANCELLED rất hiếm, optimizer có thể bắt đầu từ orders với index trên status hoặc index ghép phù hợp, sau đó dùng primary key customers.customer_id để tìm khách hàng tương ứng.

Trong ví dụ này, cả region và status đều có thể chọn lọc. Hướng tốt hơn phụ thuộc tần suất thực tế, số dòng khớp, tương quan giữa status và region, cùng chi phí của từng index. Không nên chọn hướng chỉ bằng số dòng tổng của bảng.

Sau khi tạo index thử nghiệm, hãy đo execution plan với nhiều nhóm tham số đại diện, gồm giá trị phổ biến và hiếm. Một kế hoạch tốt cho CANCELLED có thể không phù hợp cho PAID.

## 16. Quy trình thiết kế chỉ mục hỗ trợ phép nối

Có thể áp dụng quy trình sau:

1. **Xác định mẫu truy vấn:** ghi nhận JOIN predicate, WHERE, ORDER BY, GROUP BY và số lần gọi.
2. **Xác định quan hệ dữ liệu:** khóa chính, khóa ngoại, unique key, một-nhiều hoặc nhiều-nhiều.
3. **Đo số dòng sau lọc:** xác định phía nào có thể trở thành outer hoặc đầu vào nhỏ.
4. **Đọc kế hoạch hiện tại:** xem thuật toán join, access path, loops, estimated rows và actual rows.
5. **Chọn mục tiêu index:** hỗ trợ inner lookup, lọc đầu vào, cung cấp thứ tự hoặc bao phủ truy vấn.
6. **Thiết kế thứ tự cột:** cân nhắc equality, range, join key và ORDER BY theo workload.
7. **Kiểm tra index hiện có:** tránh tạo index trùng hoặc gần giống mà không có lợi ích rõ ràng.
8. **Tạo thay đổi trong môi trường phù hợp:** ghi lại cấu trúc và baseline trước khi thử.
9. **Đo lại:** so sánh latency, throughput, buffers, I/O và số vòng lặp dưới cùng điều kiện tải.
10. **Đo tác động phụ:** kiểm tra thời gian ghi, dung lượng, cache và truy vấn liên quan.
11. **Theo dõi theo thời gian:** đánh giá lại khi phân bố dữ liệu hoặc tỷ lệ tham số thay đổi.

## 17. Những sai lầm thường gặp

- **Tạo index trên mọi cột JOIN:** tăng dung lượng và chi phí ghi mà không bảo đảm optimizer dùng chúng.
- **Cho rằng cả hai phía luôn cần index:** hash join có thể hiệu quả hơn khi phải đọc phần lớn dữ liệu.
- **Chỉ nhìn tên index trong plan:** cần xem actual rows, loops, buffers và thời gian thực tế.
- **Bỏ qua số dòng outer:** nested loop có thể trở nên đắt khi outer lớn.
- **Thiết kế composite index chỉ theo thứ tự cột trong câu SQL:** thứ tự cột cần dựa trên access path và workload, không phải thứ tự văn bản.
- **Quên index ở phía khóa ngoại:** join hoặc kiểm tra dòng con có thể phải quét bảng lớn.
- **Thêm INCLUDE quá nhiều:** covering index rộng làm tăng dung lượng và chi phí ghi.
- **Dùng index scan cho kết quả chiếm phần lớn bảng:** sequential scan có thể rẻ hơn.
- **Bỏ qua kiểu dữ liệu và biểu thức join:** ép kiểu hoặc hàm có thể cản trở index access.
- **Thay đổi ngữ nghĩa outer join để tận dụng index:** kết quả có thể sai dù truy vấn chạy nhanh hơn.
- **Ép join algorithm hoặc join order quá sớm:** kế hoạch cố định có thể kém khi dữ liệu và workload thay đổi.
- **Chỉ đo truy vấn đọc:** index mới có thể làm chậm ghi và các luồng nghiệp vụ khác.

## 18. Checklist kiểm tra chỉ mục hỗ trợ join

Trước khi kết luận cần thêm hoặc thay đổi index, hãy trả lời:

1. Điều kiện JOIN sử dụng những cột nào và hai cột có kiểu dữ liệu tương thích không?
2. Phía nào có thể được lọc xuống tập nhỏ trước?
3. Nếu dùng nested loop, index lookup sẽ nằm ở inner side nào?
4. Số dòng outer và số loops thực tế là bao nhiêu?
5. Nếu dùng hash join, index có giúp giảm build/probe input không hay scan sẽ rẻ hơn?
6. Nếu dùng merge join, index có cung cấp thứ tự cần thiết và tránh sort không?
7. Index ghép có đúng tiền tố cho điều kiện bằng, điều kiện phạm vi và khóa nối không?
8. Có thể dùng covering index mà không làm index quá rộng không?
9. Khóa ngoại đã có index phù hợp chưa?
10. Có outer join, NULL, EXISTS hoặc NOT EXISTS cần giữ đúng ngữ nghĩa không?
11. Estimated rows có gần actual rows không?
12. Sau thay đổi, latency, throughput, I/O và chi phí ghi có cải thiện ở cùng mức tải không?

## Kết luận

Chỉ mục hỗ trợ phép nối bằng cách giảm số dòng cần đọc, giúp nested loop tra cứu nhanh ở inner side, cung cấp thứ tự cho merge join hoặc bao phủ dữ liệu cần thiết. Tuy nhiên, hash join có thể không cần index trên khóa nối nếu scan hai đầu vào và xây hash table rẻ hơn. Vì vậy, lựa chọn phía truy cập phải dựa trên số dòng sau lọc, độ chọn lọc, thuật toán join, thống kê và kế hoạch thực thi.

Thiết kế index tốt bắt đầu từ workload và quan hệ dữ liệu: xác định phía được lọc, phía được tra cứu, thứ tự cột trong index ghép và các cột có thể bao phủ. Sau đó đọc execution plan, so sánh estimated rows với actual rows, đo buffers/I/O và kiểm tra cả chi phí ghi. Chỉ khi kết quả đo xác nhận lợi ích trên workload liên quan mới nên giữ thay đổi.
