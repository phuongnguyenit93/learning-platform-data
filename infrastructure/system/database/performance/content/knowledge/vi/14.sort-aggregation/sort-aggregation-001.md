# ORDER BY, thứ tự chỉ mục và khi nào có thể tránh sắp xếp

Truy vấn cơ sở dữ liệu thường cần trả về dữ liệu theo một thứ tự cụ thể: đơn hàng mới nhất, sản phẩm có giá thấp nhất, giao dịch theo thời gian hoặc danh sách theo tên. Mệnh đề ORDER BY biểu đạt thứ tự đó. Để tạo kết quả, hệ quản trị có thể phải sắp xếp các hàng sau khi đọc, hoặc tận dụng thứ tự vốn có của một chỉ mục phù hợp để trả kết quả theo đúng thứ tự.

Sắp xếp có thể tiêu tốn CPU, bộ nhớ và I/O. Khi tập dữ liệu lớn hơn vùng nhớ được cấp, DB có thể ghi các phần dữ liệu trung gian ra đĩa rồi trộn lại. Một chỉ mục có thứ tự phù hợp đôi khi cho phép đọc dữ liệu theo thứ tự cần thiết và dừng sớm khi đã đủ số hàng. Tuy nhiên, thêm chỉ mục cũng làm tăng dung lượng và chi phí ghi. Vì vậy, cần dựa trên workload và kế hoạch thực thi để quyết định khi nào nên dùng chỉ mục, khi nào chấp nhận sort và khi nào cần thay đổi truy vấn.

Trong phạm vi DATABASE_PERFORMANCE, bài học này tập trung vào cách ORDER BY tương tác với thứ tự chỉ mục, điều kiện lọc, LIMIT, join và bộ nhớ; cách nhận diện sort trong execution plan; và cách kiểm chứng hiệu quả sau điều chỉnh.

## 1. ORDER BY là cam kết về thứ tự kết quả

Quan hệ dữ liệu trong bảng không có thứ tự mặc định được bảo đảm. Thứ tự hàng mà một lần quét bảng hoặc một kế hoạch thực thi tình cờ trả về có thể thay đổi sau khi thêm chỉ mục, cập nhật dữ liệu, vacuum, rebuild, parallel execution hoặc nâng cấp hệ quản trị.

Nếu ứng dụng cần thứ tự xác định, truy vấn phải chỉ rõ ORDER BY:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC;
```

Không có ORDER BY, DBMS được quyền trả hàng theo bất kỳ thứ tự nào phù hợp với kế hoạch. Việc một truy vấn hôm nay trả về theo thứ tự khóa chính không tạo ra cam kết cho lần chạy sau.

### Thứ tự không duy nhất và kết quả không ổn định

Nếu nhiều hàng có cùng giá trị sắp xếp, thứ tự giữa chúng chưa được xác định. Ví dụ:

```sql
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC
LIMIT 20;
```

Nếu nhiều đơn hàng có cùng created_at, DB có thể trả về các hàng đó theo thứ tự khác nhau giữa các lần chạy hoặc kế hoạch. Để có thứ tự toàn phần ổn định, thêm khóa phân biệt:

```sql
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Khóa phụ giúp xác định thứ tự giữa các hàng có timestamp giống nhau. Điều này quan trọng với phân trang, đồng bộ dữ liệu và kiểm thử kết quả.

### NULL, collation và biểu thức

ORDER BY còn chịu ảnh hưởng của quy tắc NULL, collation và cách biểu diễn biểu thức:

- Một số DBMS mặc định đưa NULL lên đầu, hệ khác đưa xuống cuối tùy ASC/DESC. Nếu yêu cầu nghiệp vụ rõ ràng, dùng cú pháp NULLS FIRST/NULLS LAST khi được hỗ trợ hoặc biểu thức CASE tương đương.
- Collation quyết định cách sắp xếp chuỗi, bao gồm hoa/thường, dấu và quy tắc ngôn ngữ. Chỉ mục được xây theo collation cụ thể; truy vấn dùng collation khác có thể không tận dụng được thứ tự đó.
- ORDER BY lower(name), date(created_at) hoặc một biểu thức tính toán có thể cần expression index, computed column hoặc persisted/generated column để có thứ tự chỉ mục tương ứng.
- Ép kiểu hoặc áp dụng hàm lên cột có thể làm thứ tự của chỉ mục gốc không còn phù hợp với biểu thức ORDER BY.

Ví dụ chỉ định NULL ở cuối:

```sql
SELECT product_id, discontinued_at
FROM products
ORDER BY discontinued_at ASC NULLS LAST, product_id;
```

Cú pháp NULLS LAST không có trong mọi hệ quản trị. Với DBMS không hỗ trợ, có thể dùng:

```sql
SELECT product_id, discontinued_at
FROM products
ORDER BY
    CASE WHEN discontinued_at IS NULL THEN 1 ELSE 0 END,
    discontinued_at,
    product_id;
```

Biểu thức CASE có thể cần một chỉ mục biểu thức hoặc cột tính toán tương ứng nếu muốn tránh sort. Hãy xác minh trên đúng hệ quản trị và phiên bản.

## 2. Vì sao thao tác sort tốn tài nguyên?

Nếu không có đường truy cập cung cấp sẵn thứ tự mong muốn, DB thường phải đọc các hàng ứng viên rồi sắp xếp theo các khóa ORDER BY. Chi phí phụ thuộc số hàng, số cột khóa, kích thước hàng trung gian, loại thuật toán, bộ nhớ được cấp và khả năng tận dụng song song.

Một thao tác sort thường có các giai đoạn:

1. Nhận các hàng từ toán tử phía trước như scan, join hoặc aggregate.
2. Tính các khóa sắp xếp và giữ thông tin cần thiết cho mỗi hàng.
3. Sắp xếp trong bộ nhớ nếu vùng làm việc đủ lớn.
4. Nếu không đủ bộ nhớ, chia dữ liệu thành các run hoặc phần trung gian, ghi ra vùng lưu trữ tạm rồi trộn lại.
5. Trả các hàng theo thứ tự đã yêu cầu cho toán tử tiếp theo hoặc client.

Các DBMS có thể dùng quicksort, heapsort, external merge sort hoặc thuật toán chuyên biệt khác. Tên thuật toán và cách cấp bộ nhớ khác nhau; khi chẩn đoán nên dựa vào plan, memory grant, sort spill và I/O thực tế thay vì giả định mọi engine đều dùng một thuật toán.

### In-memory sort và external sort

Nếu tập dữ liệu cần sắp xếp vừa vùng nhớ, sort có thể hoàn thành mà không cần ghi dữ liệu tạm ra đĩa. Khi dữ liệu vượt giới hạn, hệ quản trị có thể thực hiện external sort. Việc ghi và đọc các run trung gian làm tăng I/O và thời gian.

Các dấu hiệu cần theo dõi:

- Sort operator có thời gian hoặc chi phí cao trong execution plan.
- Sort spill, temporary file hoặc workfile tăng.
- Memory grant lớn, không đủ hoặc chờ cấp phát.
- I/O trên volume chứa file tạm tăng trong lúc truy vấn chạy.
- CPU tăng do so sánh khóa và trộn các run.
- Độ trễ p95/p99 tăng mạnh khi số hàng đầu vào tăng.

Sort spill không phải lúc nào cũng chứng minh cấu hình bộ nhớ quá thấp. Ước lượng số hàng sai, hàng trung gian quá rộng, nhiều truy vấn sort đồng thời hoặc memory grant bị giới hạn đều có thể góp phần. Tăng bộ nhớ toàn hệ thống có thể làm các truy vấn khác thiếu tài nguyên; cần xác định nguyên nhân trước.

### Chi phí không chỉ nằm ở toán tử sort

Sort thường nhận dữ liệu từ scan hoặc join. Nếu truy vấn đọc hàng triệu bản ghi nhưng cuối cùng chỉ trả về 20 hàng, phần lớn chi phí có thể nằm ở việc tạo tập ứng viên trước khi sort. Một chỉ mục phù hợp có thể giảm cả số hàng phải đọc và nhu cầu sắp xếp.

Ngược lại, nếu truy vấn cần trả về phần lớn bảng, đọc tuần tự rồi sort có thể rẻ hơn việc đi qua một chỉ mục rồi truy cập hàng dữ liệu theo thứ tự ngẫu nhiên. Bộ tối ưu cần cân bằng chi phí truy cập và sort; không phải mọi ORDER BY đều cần một chỉ mục riêng.

## 3. B-tree lưu thứ tự từ trái sang phải

B-tree index tổ chức khóa theo thứ tự từ điển (lexicographic). Với chỉ mục ghép trên (A, B, C), các hàng được sắp xếp trước theo A; trong cùng giá trị A, sắp theo B; trong cùng cặp (A, B), sắp theo C.

Ví dụ:

```sql
CREATE INDEX idx_orders_customer_created_id
ON orders (customer_id, created_at, order_id);
```

Thứ tự logic của chỉ mục là:

1. customer_id tăng dần.
2. Trong từng customer_id, created_at tăng dần.
3. Với cùng customer_id và created_at, order_id tăng dần.

Chỉ mục này có thể hỗ trợ truy vấn lọc customer_id bằng một giá trị và sắp xếp theo created_at, order_id nếu hướng sắp xếp tương thích hoặc DB có thể đọc ngược chỉ mục.

### Equality prefix và cột sắp xếp

Một mẫu rất phổ biến là lọc bằng trên các cột đầu của chỉ mục rồi sắp xếp theo các cột tiếp theo:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Chỉ mục phù hợp có thể là:

```sql
CREATE INDEX idx_orders_customer_created_desc
ON orders (customer_id, created_at DESC, order_id DESC);
```

Vì customer_id được cố định bằng một giá trị, phần còn lại của dải chỉ mục có thứ tự theo created_at và order_id. DB có thể đi vào vị trí tương ứng của customer_id, đọc theo thứ tự cần thiết và dừng khi đủ 20 hàng, tùy khả năng của hệ quản trị và điều kiện truy vấn.

Nếu truy vấn không cố định cột đầu tiên:

```sql
SELECT order_id, customer_id, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Chỉ mục bắt đầu bằng customer_id thường không cung cấp thứ tự toàn cục theo created_at, vì các hàng được chia thành từng nhóm customer_id trước. Cần một chỉ mục bắt đầu bằng created_at nếu workload này đủ quan trọng và chi phí chỉ mục được chấp nhận.

### Range predicate làm thay đổi khả năng dùng thứ tự

Điều kiện bằng trên tiền tố thường cho phép dùng các cột tiếp theo làm thứ tự. Nhưng nếu cột trước cột ORDER BY có điều kiện khoảng, thứ tự trên cột sau có thể chỉ đúng bên trong từng giá trị của cột khoảng, không phải thứ tự toàn cục.

Ví dụ chỉ mục (region_id, created_at):

```sql
SELECT order_id, region_id, created_at
FROM orders
WHERE region_id >= 3
ORDER BY created_at DESC;
```

Chỉ mục được nhóm theo region_id trước, nên đọc toàn bộ các vùng từ 3 trở lên không tự tạo ra thứ tự toàn cục theo created_at. DB có thể cần merge nhiều dải hoặc sort kết quả. Kế hoạch thực tế phụ thuộc khả năng của DBMS và cách truy vấn được tối ưu.

Nguyên tắc cần nhớ: các cột chỉ mục được cố định bằng điều kiện bằng thường tạo thành equality prefix; thứ tự sau prefix có thể phục vụ ORDER BY. Điều kiện range, IN nhiều giá trị, join và predicate khác có thể làm tình huống phức tạp hơn, cần kiểm tra execution plan.

## 4. ASC, DESC và thứ tự hỗn hợp

Một B-tree có thể được đọc theo chiều xuôi hoặc ngược trong nhiều hệ quản trị. Vì vậy, chỉ mục (created_at ASC) thường có thể phục vụ cả ORDER BY created_at ASC lẫn DESC bằng cách đổi hướng scan.

Với chỉ mục ghép, đọc ngược sẽ đảo chiều tất cả các cột khóa cùng lúc. Điều đó không tương đương mọi tổ hợp ASC/DESC hỗn hợp.

Ví dụ:

```sql
SELECT order_id, created_at, priority
FROM orders
ORDER BY created_at DESC, priority ASC;
```

Một chỉ mục (created_at ASC, priority ASC) khi đọc ngược sẽ cho (created_at DESC, priority DESC), không khớp hoàn toàn với thứ tự yêu cầu. Chỉ mục được khai báo hướng hỗn hợp:

```sql
CREATE INDEX idx_orders_created_desc_priority_asc
ON orders (created_at DESC, priority ASC);
```

có thể cung cấp thứ tự phù hợp trực tiếp nếu DBMS hỗ trợ khai báo hướng cho từng khóa và các điều kiện khác cho phép.

Một số hệ quản trị lưu hoặc xử lý hướng khóa khác nhau. SQL Server, PostgreSQL, MySQL và Oracle đều có chi tiết riêng về ascending/descending index, reverse scan và NULL ordering. Không nên suy ra khả năng chỉ từ cú pháp DDL; hãy xem plan.

## 5. ORDER BY kết hợp LIMIT và Top-N

Một truy vấn chỉ cần một số hàng đầu tiên có thể được tối ưu tốt hơn nhiều so với việc sắp xếp toàn bộ tập dữ liệu.

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Có hai hướng chính:

- **Dùng chỉ mục theo thứ tự:** DB đọc từ vị trí thích hợp và dừng sau khi tìm đủ 20 hàng thỏa điều kiện.
- **Top-N sort:** DB vẫn phải đọc tập ứng viên, nhưng chỉ giữ một tập nhỏ các hàng tốt nhất thay vì sắp xếp toàn bộ theo cách thông thường.

Top-N sort giảm bộ nhớ và công việc so với full sort trong một số trường hợp, nhưng không loại bỏ chi phí đọc và kiểm tra toàn bộ hàng ứng viên. Nếu hàng triệu hàng phải được kiểm tra mới tìm được 20 hàng phù hợp, truy vấn vẫn có thể chậm.

Một chỉ mục có thể hỗ trợ cả điều kiện lọc và thứ tự thường đem lại lợi ích lớn hơn vì có thể giảm số hàng đọc. Tuy nhiên, nếu predicate phụ không nằm trong chỉ mục hoặc có độ chọn lọc thấp, DB có thể phải bỏ qua nhiều mục chỉ mục trước khi tìm đủ N hàng.

### OFFSET pagination

Phân trang kiểu OFFSET:

```sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 10000;
```

DB vẫn phải đi qua hoặc loại bỏ khoảng 10.000 hàng đầu trước khi trả 20 hàng tiếp theo. Chỉ mục phù hợp giúp tránh sort và giảm chi phí truy cập, nhưng không nhất thiết loại bỏ chi phí bỏ qua các hàng.

### Keyset pagination

Keyset pagination dùng khóa của hàng cuối trang trước làm điểm bắt đầu:

```sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = 42
  AND (created_at, order_id) < (:last_created_at, :last_order_id)
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Truy vấn cần chỉ mục tương thích, ví dụ (customer_id, created_at DESC, order_id DESC). So sánh tuple và quy tắc NULL phụ thuộc hệ quản trị; nếu không hỗ trợ tuple comparison, có thể biểu diễn bằng điều kiện OR tương đương:

```sql
WHERE customer_id = 42
  AND (
       created_at < :last_created_at
       OR (
           created_at = :last_created_at
           AND order_id < :last_order_id
       )
  )
```

Keyset pagination thường ổn định và hiệu quả hơn khi đi sâu vào tập dữ liệu lớn. Cần bảo đảm khóa sắp xếp tạo thứ tự duy nhất và xử lý nhất quán nếu dữ liệu thay đổi giữa các trang.

## 6. Khi nào chỉ mục có thể loại bỏ Sort?

Một chỉ mục có thể cung cấp thứ tự cần thiết khi các điều kiện sau tương thích:

1. Các cột ORDER BY xuất hiện trong chỉ mục theo thứ tự phù hợp sau phần tiền tố được cố định bởi điều kiện bằng.
2. Hướng ASC/DESC và thứ tự hỗn hợp tương thích với hướng scan được DBMS hỗ trợ.
3. Biểu thức, kiểu dữ liệu và collation của ORDER BY khớp với khóa chỉ mục hoặc expression index tương ứng.
4. Các phép toán phía trước không phá vỡ thứ tự, hoặc DBMS có thể bảo toàn/ghép thứ tự một cách rõ ràng.
5. Các predicate còn lại không buộc hệ thống phải tạo tập kết quả trung gian rồi sắp xếp lại.

Ví dụ:

```sql
CREATE INDEX idx_events_tenant_time
ON events (tenant_id, occurred_at DESC, event_id DESC);

SELECT event_id, occurred_at
FROM events
WHERE tenant_id = 7
ORDER BY occurred_at DESC, event_id DESC
LIMIT 50;
```

Nếu kế hoạch chọn index range scan theo tenant và trả kết quả theo thứ tự khóa, toán tử Sort có thể không còn. DB có thể đọc đúng dải khóa và dừng sau 50 hàng.

Tuy nhiên, chỉ mục không tự bảo đảm sort biến mất. Bộ tối ưu có thể chọn scan khác vì chi phí thấp hơn, thống kê có thể sai, predicate có thể làm giảm hiệu quả của đường chỉ mục, hoặc một toán tử phía sau có thể yêu cầu thứ tự khác.

### Sort có thể vẫn xuất hiện sau join

Một truy vấn có thể đọc bảng chính theo thứ tự chỉ mục nhưng phép join tiếp theo làm thay đổi thứ tự hoặc tạo nhiều nhánh kết quả. Hash join thường không bảo đảm thứ tự đầu ra. Parallel execution cũng có thể làm mất thứ tự khi các luồng được gom lại, trừ khi có toán tử merge/gather bảo toàn thứ tự theo cơ chế DBMS.

Nested loop có thể giữ một dạng thứ tự của outer input trong một số kế hoạch, nhưng không nên dựa vào hành vi tình cờ đó nếu SQL không yêu cầu và plan không bảo đảm. Nếu ORDER BY nằm sau join, hãy kiểm tra node cuối cùng trước kết quả và xem sort có cần thiết không.

GROUP BY cũng không bảo đảm kết quả được trả theo thứ tự nhóm. Nếu ứng dụng cần thứ tự nhóm, phải có ORDER BY riêng. Tương tự, DISTINCT, UNION, window function và aggregate có thể dùng sort hoặc hash riêng; việc một toán tử dùng thứ tự không đồng nghĩa kết quả cuối cùng đã được sắp theo yêu cầu.

## 7. Covering index và INCLUDE columns

Chỉ mục có thể chứa các cột trả về để DB không cần quay lại bảng lấy dữ liệu. Đây là covering index hoặc index-only access tùy hệ quản trị.

Ví dụ:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Một chỉ mục có khóa (customer_id, created_at DESC, order_id DESC) cung cấp điều kiện và thứ tự. Nếu total_amount được lưu kèm trong chỉ mục, DB có thể trả dữ liệu mà không cần lookup hàng trong bảng ở những trường hợp phù hợp.

SQL Server hỗ trợ INCLUDE columns:

```sql
CREATE INDEX idx_orders_customer_created
ON dbo.Orders (CustomerId, CreatedAt DESC, OrderId DESC)
INCLUDE (TotalAmount);
```

PostgreSQL hỗ trợ INCLUDE trong nhiều loại B-tree index:

```sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at DESC, order_id DESC)
INCLUDE (total_amount);
```

MySQL thường đưa cột bổ sung vào phần khóa của composite index nếu cần covering, vì cú pháp và cách tổ chức khác. Không nên sao chép cú pháp INCLUDE giữa các DBMS.

INCLUDE columns không tham gia thứ tự khóa và không giúp sắp xếp theo cột được include. Chúng chỉ bổ sung dữ liệu để đáp ứng truy vấn. Thêm quá nhiều cột làm chỉ mục rộng, tăng dung lượng và chi phí ghi. Với PostgreSQL, index-only scan còn phụ thuộc visibility map; có thể vẫn cần truy cập heap để xác minh phiên bản hàng.

## 8. Expression index và collation cho ORDER BY

Truy vấn có thể yêu cầu thứ tự theo biểu thức thay vì giá trị cột gốc:

```sql
SELECT customer_id, display_name
FROM customers
ORDER BY lower(display_name);
```

Chỉ mục B-tree thông thường trên display_name không nhất thiết cung cấp thứ tự theo lower(display_name). PostgreSQL hỗ trợ expression index:

```sql
CREATE INDEX idx_customers_lower_name
ON customers (lower(display_name));
```

Một số DBMS khác dùng computed column hoặc function-based index. Cần bảo đảm biểu thức trong truy vấn khớp với biểu thức chỉ mục và đáp ứng quy tắc bất biến/ deterministic của hệ quản trị.

Với collation, ví dụ người dùng muốn sắp xếp tên theo quy tắc tiếng Việt. Nếu chỉ mục được tạo theo collation mặc định khác, DB có thể không sử dụng nó để đáp ứng thứ tự theo collation yêu cầu. Cần tạo index tương thích với collation hoặc biểu thức sắp xếp, sau đó kiểm tra plan.

Không nên chuyển đổi cột bằng hàm trong mọi truy vấn nếu có thể chuẩn hóa dữ liệu hoặc dùng cột tính toán phù hợp. Một biểu thức được tính lại cho hàng triệu bản ghi vừa tăng CPU vừa có thể ngăn sử dụng chỉ mục gốc.

## 9. Partial/filtered index cho workload có điều kiện cố định

Nếu truy vấn thường xuyên lấy một tập con nhỏ, partial index hoặc filtered index có thể giảm dung lượng và cung cấp thứ tự cần thiết cho đúng tập con.

Ví dụ PostgreSQL:

```sql
CREATE INDEX idx_orders_open_customer_created
ON orders (customer_id, created_at DESC, order_id DESC)
WHERE status = 'OPEN';
```

Truy vấn:

```sql
SELECT order_id, created_at
FROM orders
WHERE status = 'OPEN'
  AND customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Nếu điều kiện truy vấn chứng minh được nó chỉ cần hàng nằm trong predicate của index, DB có thể dùng index nhỏ hơn và đọc theo thứ tự mong muốn. SQL Server có filtered index với cú pháp riêng. Khả năng tương đương và điều kiện áp dụng khác giữa các DBMS.

Khi status thay đổi, hàng có thể được thêm vào hoặc loại khỏi index. Nếu trạng thái cập nhật thường xuyên, chi phí ghi có thể tăng; cần đo cùng workload.

## 10. ORDER BY trong truy vấn có GROUP BY và aggregate

GROUP BY gom các hàng thành nhóm để tính COUNT, SUM, AVG, MIN hoặc MAX. Thứ tự nhóm đầu ra không được bảo đảm nếu không có ORDER BY.

Ví dụ:

```sql
SELECT customer_id, COUNT(*) AS order_count
FROM orders
GROUP BY customer_id
ORDER BY order_count DESC, customer_id;
```

DB có thể dùng hash aggregate hoặc sort-based/group aggregate. Nếu dữ liệu đầu vào đã được sắp theo customer_id, một số hệ quản trị có thể thực hiện grouped aggregation bằng cách đọc từng nhóm liên tiếp mà không cần sort riêng. Nhưng ORDER BY order_count DESC là thứ tự theo kết quả tính toán; thứ tự đầu vào theo customer_id không đáp ứng được nó. DB có thể cần sort các nhóm sau khi aggregate.

Một chỉ mục theo cột GROUP BY có thể giúp giảm sort cho bước nhóm, nhưng không nhất thiết loại bỏ sort cuối cùng. Phải phân biệt:

- Sort để hỗ trợ GROUP BY hoặc ordered aggregate.
- Sort để đáp ứng ORDER BY cuối truy vấn.
- Sort bên trong window function hoặc hàm tổng hợp có thứ tự.

Với aggregate có thứ tự, ví dụ nối chuỗi theo thời gian, thứ tự cần được đặt bên trong hàm aggregate theo cú pháp DBMS hỗ trợ; ORDER BY ở cuối truy vấn chỉ sắp xếp các hàng kết quả, không quyết định thứ tự phần tử bên trong mỗi giá trị tổng hợp.

## 11. Đọc execution plan để xác định Sort

Khi phân tích truy vấn, hãy tìm toán tử sort và đường truy cập dữ liệu cung cấp thứ tự:

- Sort hoặc explicit sort: DB phải sắp xếp các hàng.
- Top-N sort / top-N heapsort: chỉ giữ một số hàng tốt nhất, thường dùng với LIMIT.
- Index scan / index range scan: có thể trả hàng theo thứ tự khóa nếu hướng và phạm vi phù hợp.
- Index-only scan: có thể đọc từ index và cung cấp thứ tự mà không cần truy cập bảng, tùy DBMS.
- Merge join: thường cần đầu vào có thứ tự theo khóa join; có thể tận dụng thứ tự sẵn có hoặc yêu cầu sort.
- Hash join: thường không bảo toàn thứ tự đầu vào.
- Gather/gather merge: trong kế hoạch song song, gather thông thường có thể không giữ thứ tự; gather merge có thể ghép các luồng đã sắp theo thứ tự.

Trong PostgreSQL, có thể dùng:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Quan sát Sort Method, Memory, Disk hoặc thông tin tương đương nếu sort xuất hiện. So sánh actual rows, loops, buffer reads và thời gian. Trong SQL Server, xem Sort operator, memory grant, spill warnings và actual plan. Trong MySQL, kiểm tra EXPLAIN/EXPLAIN ANALYZE và thông tin filesort nếu có. Trong Oracle, xem operation SORT ORDER BY, SORT ORDER BY STOPKEY hoặc các operation liên quan.

Tên operation khác nhau, nhưng câu hỏi chung là:

1. Có sort không, ở node nào?
2. Bao nhiêu hàng đi vào sort và bao nhiêu hàng được trả ra?
3. Sort có spill ra đĩa hoặc chờ memory grant không?
4. Có chỉ mục nào cung cấp đúng thứ tự không?
5. Chi phí đọc index và lookup có rẻ hơn scan + sort không?
6. LIMIT có giúp dừng sớm hay DB vẫn phải xử lý toàn bộ tập ứng viên?

Không nên đánh giá chỉ bằng việc chữ Sort biến mất. Một index scan có thể đọc gần như toàn bộ bảng và gây random I/O, trong khi sequential scan + sort có thể nhanh hơn. Hãy so sánh elapsed time, logical/physical reads, CPU, I/O và ảnh hưởng đến ghi.

## 12. Ví dụ thực tế: danh sách đơn hàng mới nhất

Giả sử ứng dụng thường hiển thị 20 đơn hàng mới nhất của một khách hàng. Truy vấn:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = :customer_id
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

### Trường hợp A: không có chỉ mục phù hợp

DB có thể quét bảng hoặc dùng chỉ mục chỉ trên customer_id, lấy tất cả đơn của khách hàng, rồi sort theo created_at và order_id. Nếu khách hàng có hàng trăm nghìn đơn, sort có thể tốn CPU và bộ nhớ; nếu không đủ bộ nhớ, có thể spill ra đĩa.

### Trường hợp B: chỉ mục theo khách hàng và thời gian

Tạo:

```sql
CREATE INDEX idx_orders_customer_recent
ON orders (customer_id, created_at DESC, order_id DESC);
```

DB có thể tìm dải khóa của customer_id, đọc theo thứ tự mới nhất và dừng sau 20 hàng. Nếu total_amount không nằm trong index, DB có thể phải lookup tối đa 20 hàng trong bảng; đây có thể vẫn là lựa chọn rẻ.

### Trường hợp C: thêm cột bao phủ

Nếu truy vấn này rất thường xuyên và lookup tạo chi phí đáng kể, có thể xem xét INCLUDE total_amount trên hệ quản trị hỗ trợ:

```sql
CREATE INDEX idx_orders_customer_recent_cover
ON orders (customer_id, created_at DESC, order_id DESC)
INCLUDE (total_amount);
```

Index rộng hơn, tốn dung lượng và tăng chi phí insert/update. Nếu total_amount không thay đổi sau khi tạo đơn, chi phí cập nhật có thể chấp nhận được; nếu cột thường xuyên thay đổi, cần cân nhắc kỹ.

### So sánh trước và sau

| Chỉ số | Trước | Sau khi có index phù hợp |
|---|---|---|
| Hàng ứng viên | Có thể là toàn bộ đơn của khách hàng | Có thể dừng sau số hàng cần |
| Sort | Có thể cần sort toàn bộ hoặc Top-N | Có thể không cần Sort |
| Bộ nhớ sort | Có thể đáng kể | Có thể giảm hoặc bằng 0 cho truy vấn |
| I/O | Scan và sort; có thể spill | Index range scan và một số lookup |
| Chi phí ghi | Không có chi phí index mới | Tăng khi insert/update/delete |
| Dung lượng | Thấp hơn | Tăng do index |

Các kết quả phụ thuộc dữ liệu, DBMS, cache và workload. Sau khi tạo index, hãy kiểm tra plan thực tế và đo p95/p99, throughput ghi, kích thước index và thời gian bảo trì.

## 13. Các trường hợp chỉ mục không loại bỏ được sort

Ngay cả khi có chỉ mục, sort có thể vẫn cần thiết:

- ORDER BY dùng biểu thức khác thứ tự khóa index.
- Collation của truy vấn khác collation của index.
- Cột đầu index không được cố định và thứ tự yêu cầu bắt đầu từ cột sau.
- Range predicate trên cột trước làm thứ tự toàn cục của cột sau không được đáp ứng.
- Hướng ASC/DESC hỗn hợp không tương thích với hướng scan.
- Join hoặc parallel operator làm mất thứ tự.
- GROUP BY/aggregate tạo ra giá trị mới cần sắp xếp theo kết quả tính toán.
- Truy vấn cần sắp theo cột không có trong index hoặc không thể suy ra thứ tự.
- Bộ tối ưu ước lượng rằng scan + sort rẻ hơn index scan.

Một số DBMS có thể dùng incremental sort khi đầu vào đã được sắp một phần theo tiền tố khóa. Khi đó, engine chỉ cần sort trong từng nhóm còn lại thay vì sắp xếp toàn bộ tập dữ liệu. Hãy kiểm tra operation cụ thể trong execution plan; incremental sort không đồng nghĩa không có sort.

## 14. Chi phí vòng đời của chỉ mục phục vụ ORDER BY

Chỉ mục giúp đọc theo thứ tự nhưng phải được duy trì khi dữ liệu thay đổi:

- INSERT cần thêm khóa vào cấu trúc index.
- DELETE cần đánh dấu hoặc loại bỏ mục index theo cơ chế DBMS.
- UPDATE cột khóa sắp xếp có thể phải di chuyển mục index.
- Index rộng làm tăng dung lượng, cache footprint, I/O và thời gian backup.
- Nhiều index trên các tổ hợp gần giống nhau có thể gây trùng lặp chi phí.
- Tạo hoặc rebuild index trên bảng lớn có thể tiêu thụ CPU, I/O, log và khóa tùy phương thức.

Không nên tạo một index cho mọi biến thể ORDER BY của mọi endpoint. Hãy nhóm workload theo mẫu truy vấn, chọn các tổ hợp có tần suất và tác động lớn, rồi đánh giá khả năng một index phục vụ nhiều truy vấn.

Ví dụ, index (customer_id, created_at DESC, order_id DESC) có thể phục vụ danh sách đơn mới nhất của một khách hàng. Nó không nhất thiết phục vụ truy vấn toàn cục ORDER BY created_at DESC, vì customer_id là cột đầu. Một index khác có thể cần thiết nếu truy vấn toàn cục đủ quan trọng; chi phí ghi của cả hai phải được tính.

## 15. Quy trình tối ưu ORDER BY

1. **Xác định yêu cầu thứ tự.** Ghi rõ cột, hướng, NULL ordering, collation, khóa phân biệt và số hàng cần trả.
2. **Đo workload.** Xác định tần suất truy vấn, p95/p99, số hàng, tỷ lệ LIMIT và các nhóm tham số.
3. **Thu thập kế hoạch thực tế.** Tìm Sort, Top-N, index scan, row estimate, actual rows, memory, spill và I/O.
4. **Kiểm tra thứ tự chỉ mục.** So sánh equality prefix, range predicate, cột ORDER BY và hướng khóa.
5. **Xem phép toán trung gian.** Xác định join, aggregate hoặc parallel execution có phá vỡ thứ tự không.
6. **Chọn thay đổi nhỏ nhất có căn cứ.** Có thể viết lại predicate, thêm index ghép, expression index, partial/filtered index hoặc thay đổi pagination.
7. **Đo lại cùng điều kiện.** Giữ dữ liệu, tham số, tải và trạng thái cache tương đương.
8. **Đánh giá chi phí ghi và dung lượng.** Đo throughput insert/update/delete, index size, I/O và thời gian bảo trì.
9. **Kiểm tra tính đúng đắn.** Xác nhận thứ tự duy nhất, NULL, collation, phân trang và kết quả khi dữ liệu thay đổi.
10. **Theo dõi sau triển khai.** Kiểm tra p95/p99, sort spill, buffer hit, write latency và các truy vấn khác dùng chung bảng.

## 16. Những sai lầm thường gặp

- **Cho rằng bảng có thứ tự tự nhiên:** chỉ ORDER BY mới bảo đảm thứ tự kết quả.
- **Không thêm khóa phân biệt:** các hàng trùng khóa sắp xếp có thể đổi vị trí giữa các lần chạy.
- **Tạo index theo đúng tên cột nhưng sai thứ tự:** B-tree ghép có thứ tự từ trái sang phải.
- **Bỏ qua equality prefix:** chỉ mục có thể phục vụ ORDER BY sau các cột đầu được cố định bằng điều kiện bằng.
- **Nhầm range predicate với equality:** điều kiện khoảng trên cột trước có thể không cung cấp thứ tự toàn cục cho cột sau.
- **Cho rằng đọc ngược xử lý mọi hướng hỗn hợp:** reverse scan thường đảo chiều toàn bộ thứ tự khóa cùng lúc.
- **Tăng memory để chữa mọi sort spill:** sai lệch cardinality, hàng rộng và cạnh tranh memory grant cũng có thể là nguyên nhân.
- **Chỉ nhìn Sort biến mất:** index scan có thể đọc nhiều trang hoặc gây random I/O hơn scan + sort.
- **Dùng OFFSET quá lớn:** DB vẫn phải đi qua các hàng bị bỏ qua.
- **Quên GROUP BY không bảo đảm thứ tự:** cần ORDER BY riêng cho kết quả nhóm.
- **Tạo quá nhiều index phục vụ từng endpoint:** tăng chi phí ghi, dung lượng và bảo trì.

## 17. Checklist kiểm chứng

| Câu hỏi | Điều cần xác nhận |
|---|---|
| ORDER BY có tạo thứ tự xác định không? | Có khóa phân biệt khi cần |
| NULL và collation có đúng yêu cầu không? | Đã xác định rõ quy tắc |
| Có Sort hoặc Top-N sort trong plan không? | Đã xác định node và số hàng đầu vào |
| Sort có spill hoặc chờ memory grant không? | Đã kiểm tra bộ nhớ và I/O tạm |
| Chỉ mục có equality prefix phù hợp không? | Các cột đầu và thứ tự khóa phù hợp predicate |
| ASC/DESC có tương thích không? | Đã xem hướng scan và thứ tự hỗn hợp |
| Join/aggregate/parallel có làm mất thứ tự không? | Đã xem các node sau index scan |
| LIMIT có giúp dừng sớm không? | Đã đo số hàng thực sự được đọc |
| Index có quá rộng hoặc dư thừa không? | Đã cân nhắc chi phí ghi và dung lượng |
| Hiệu năng tổng thể có cải thiện không? | Có số đo trước/sau cùng workload |

## 18. Nguyên tắc ra quyết định

ORDER BY là yêu cầu về kết quả, còn sort là một cách DB thực hiện yêu cầu đó. Khi thứ tự của chỉ mục phù hợp với điều kiện lọc và thứ tự cần trả, DB có thể đọc theo index order để tránh một thao tác sort riêng, đặc biệt hiệu quả với truy vấn có LIMIT. Nhưng chỉ mục không luôn rẻ hơn scan + sort; cần xét số hàng, độ chọn lọc, lookup, cache, I/O và chi phí duy trì index.

Hãy thiết kế thứ tự khóa từ workload thực tế: các cột equality prefix trước, tiếp theo là các cột sắp xếp theo đúng hướng và khóa phân biệt. Kiểm tra tác động của range predicate, collation, biểu thức, join và aggregate. Sau điều chỉnh, xác minh bằng execution plan và số đo cả đọc lẫn ghi. Một lựa chọn tốt giúp đáp ứng thứ tự nghiệp vụ với độ trễ phù hợp mà không tạo chi phí vận hành lớn hơn lợi ích nhận được.
