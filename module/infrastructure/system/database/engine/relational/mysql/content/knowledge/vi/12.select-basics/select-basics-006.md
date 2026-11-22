# DISTINCT và chi phí loại bỏ dữ liệu trùng

DISTINCT loại bỏ các hàng trùng nhau khỏi kết quả SELECT. Câu lệnh này hữu ích khi cần liệt kê tập giá trị hoặc tổ hợp giá trị duy nhất, nhưng việc loại bỏ trùng có thể tốn bộ nhớ, CPU và I/O. Trên bảng lớn, một truy vấn có DISTINCT có thể phải đọc rất nhiều hàng, lưu kết quả trung gian hoặc sắp xếp trước khi trả về số hàng nhỏ.

Trong module **DATABASE_MYSQL**, hiểu DISTINCT giúp viết truy vấn chính xác, nhận diện dữ liệu trùng theo collation, tránh che giấu lỗi JOIN và đánh giá chi phí bằng index cùng execution plan. Bài học này tập trung vào ngữ nghĩa loại trùng, các trường hợp phát sinh chi phí, cách tận dụng index và những cách viết truy vấn thay thế khi mục tiêu thực sự là kiểm tra sự tồn tại hoặc đếm giá trị duy nhất.

## 1. DISTINCT loại bỏ trùng như thế nào?

DISTINCT áp dụng lên toàn bộ danh sách biểu thức trong SELECT và giữ lại một hàng cho mỗi tổ hợp kết quả khác nhau.

Ví dụ, bảng orders có nhiều đơn hàng thuộc cùng trạng thái:

```sql
SELECT status
FROM orders;
```

Nếu có 10.000 đơn hàng nhưng chỉ có 5 trạng thái, truy vấn trên có thể trả về hàng nghìn hàng lặp lại. Thêm DISTINCT:

```sql
SELECT DISTINCT status
FROM orders
ORDER BY status;
```

Kết quả chỉ còn mỗi trạng thái một lần.

### 1.1. DISTINCT trên nhiều cột

Khi có nhiều biểu thức trong select list, MySQL so sánh cả tổ hợp giá trị. Ví dụ:

```sql
SELECT DISTINCT customer_id, status
FROM orders
ORDER BY customer_id, status;
```

Nếu một khách hàng có 20 đơn hàng PAID và 3 đơn hàng PENDING, kết quả có tối đa hai hàng cho khách hàng đó: (customer_id, 'PAID') và (customer_id, 'PENDING').

Điều này không tương đương với việc lấy một giá trị duy nhất cho từng cột riêng lẻ. DISTINCT customer_id, status giữ các cặp khác nhau; cùng customer_id có thể xuất hiện nhiều lần nếu status khác nhau.

### 1.2. DISTINCT không chọn một hàng đại diện theo ý muốn

DISTINCT chỉ loại bỏ các hàng có cùng giá trị ở tất cả biểu thức được chọn. Nó không tự chọn hàng mới nhất, hàng có giá trị lớn nhất hoặc hàng có thời gian cập nhật gần nhất.

Ví dụ sau không có nghĩa là "mỗi khách hàng lấy đơn hàng mới nhất":

```sql
SELECT DISTINCT customer_id, order_id, created_at
FROM orders;
```

Vì order_id thường khác nhau ở mỗi đơn hàng, gần như mọi hàng vẫn khác nhau. Nếu cần một đơn hàng mới nhất cho mỗi khách hàng, phải xác định quy tắc chọn hàng bằng window function, truy vấn con hoặc phép tổng hợp phù hợp; không thêm DISTINCT để mong MySQL tự chọn.

## 2. NULL, collation và cách xác định hai giá trị trùng

### 2.1. NULL trong DISTINCT

Trong phép so sánh SQL thông thường, NULL = NULL không trả về TRUE mà trả về UNKNOWN. Tuy nhiên, khi loại trùng kết quả, MySQL xem các giá trị NULL là trùng nhau cho mục đích DISTINCT.

Ví dụ:

```sql
SELECT DISTINCT manager_id
FROM employees;
```

Nếu có nhiều nhân viên chưa được gán quản lý (manager_id IS NULL), kết quả chỉ có một hàng NULL.

Điều này hữu ích khi liệt kê tập giá trị hiện có, nhưng cần nhớ NULL không phải một mã định danh thực. Nếu cần đếm số nhân viên chưa có quản lý, dùng COUNT(*) với điều kiện manager_id IS NULL, không suy ra số lượng từ kết quả DISTINCT.

### 2.2. Collation quyết định giá trị chuỗi có trùng không

Đối với chuỗi, việc xác định bằng nhau chịu ảnh hưởng của character set và collation của biểu thức. Với collation không phân biệt hoa/thường, hai chuỗi như 'Admin' và 'admin' có thể được xem là bằng nhau. Với collation không phân biệt dấu, một số chuỗi có dấu và không dấu cũng có thể được xem là tương đương.

Ví dụ minh họa:

```sql
SELECT DISTINCT email
FROM imported_contacts;
```

Nếu cột email dùng collation case-insensitive, các địa chỉ chỉ khác chữ hoa/thường có thể được gộp trong kết quả. Quy tắc cụ thể phụ thuộc collation, kể cả cách xử lý dấu và khoảng trắng cuối chuỗi (PAD SPACE hay NO PAD).

Nếu cần phân biệt mã theo từng ký tự, hãy chọn kiểu và collation phù hợp ngay từ schema. Không nên thêm BINARY() tùy tiện vào truy vấn để thay đổi cách so sánh, vì biểu thức có thể ảnh hưởng đến index và ngữ nghĩa dữ liệu.

Có thể kiểm tra collation của cột:

```sql
SHOW FULL COLUMNS FROM imported_contacts;

SELECT
    COLUMN_NAME,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'imported_contacts';
```

### 2.3. DISTINCT so sánh kết quả biểu thức

DISTINCT loại trùng theo giá trị được trả về, không nhất thiết theo giá trị thô của cột nguồn.

```sql
SELECT DISTINCT LOWER(email) AS normalized_email
FROM imported_contacts;
```

Truy vấn trên gộp các địa chỉ sau khi áp dụng LOWER(). Nếu cần giữ index và thường xuyên tìm theo giá trị chuẩn hóa, cân nhắc chuẩn hóa dữ liệu lúc ghi hoặc dùng cột/generated expression có index thích hợp. Không giả định index thông thường trên email tự động phục vụ mọi truy vấn có LOWER(email).

## 3. Chi phí loại bỏ dữ liệu trùng

Để trả về các hàng duy nhất, MySQL phải nhận diện các giá trị đã xuất hiện. Tùy câu truy vấn, index, thống kê và phiên bản, optimizer có thể chọn các chiến lược khác nhau.

Một số chi phí thường gặp:

- **Đọc dữ liệu:** cần đọc đủ số hàng liên quan để xác định tập kết quả duy nhất, trừ khi index cho phép bỏ qua các nhóm trùng.
- **Lưu kết quả trung gian:** có thể dùng internal temporary table để ghi nhận các hàng đã gặp.
- **Sắp xếp:** có thể cần sắp xếp để loại trùng hoặc đáp ứng ORDER BY.
- **CPU và bộ nhớ:** so sánh giá trị, kiểm tra trùng và duy trì cấu trúc trung gian tiêu tốn tài nguyên.
- **I/O phụ:** nếu dữ liệu trung gian vượt ngưỡng bộ nhớ hoặc phải đọc nhiều trang, truy vấn có thể phát sinh I/O đáng kể.

Không phải mọi DISTINCT đều tạo temporary table hay filesort. Optimizer có thể tận dụng index hoặc chọn kế hoạch khác. Hãy kiểm tra execution plan và đo trên dữ liệu đại diện thay vì suy luận chỉ từ cú pháp.

### 3.1. DISTINCT trên bảng lớn

Giả sử bảng page_views có hàng trăm triệu lượt xem, nhưng chỉ có vài nghìn page_id khác nhau:

```sql
SELECT DISTINCT page_id
FROM page_views;
```

Nếu không có index phù hợp, MySQL có thể phải đọc rất nhiều hàng và thực hiện loại trùng trên tập dữ liệu lớn. Số hàng kết quả ít không có nghĩa chi phí truy vấn thấp.

### 3.2. DISTINCT kết hợp ORDER BY và LIMIT

```sql
SELECT DISTINCT customer_id
FROM orders
ORDER BY customer_id
LIMIT 20;
```

MySQL cần tìm 20 customer_id duy nhất theo thứ tự yêu cầu. Nếu dữ liệu lặp nhiều, có thể phải đọc nhiều hàng hơn 20 để thu đủ 20 giá trị khác nhau. LIMIT không có nghĩa MySQL chỉ đọc đúng 20 hàng nguồn.

Nếu index phù hợp cung cấp thứ tự và các giá trị đã nhóm liền nhau, engine có thể bỏ qua nhiều entry trùng và dừng sớm hơn. Đây là một lý do index đúng có thể giảm đáng kể chi phí DISTINCT.

## 4. Khi nào index giúp loại trùng hiệu quả?

Index B-tree sắp xếp giá trị theo thứ tự. Khi các cột trong DISTINCT tương thích với thứ tự của index, MySQL có thể đọc các giá trị theo nhóm và bỏ qua entry trùng mà không cần materialize toàn bộ tập kết quả.

### 4.1. Index trên cột DISTINCT

Ví dụ:

```sql
CREATE INDEX idx_orders_customer
    ON orders (customer_id);

EXPLAIN
SELECT DISTINCT customer_id
FROM orders;
```

Index idx_orders_customer sắp xếp các entry theo customer_id. MySQL có thể tận dụng index để đọc các giá trị duy nhất. Trong một số kế hoạch, EXPLAIN hiển thị Using index for group-by trong cột Extra khi dùng Loose Index Scan.

Không phải cứ có index trên cột là chắc chắn kế hoạch này được chọn. Optimizer còn cân nhắc độ chọn lọc, số lượng giá trị khác nhau, thống kê và chi phí đọc index so với scan bảng.

### 4.2. Index ghép và leftmost prefix

Giả sử thường xuyên liệt kê khách hàng có đơn hàng theo trạng thái:

```sql
CREATE INDEX idx_orders_status_customer
    ON orders (status, customer_id);

EXPLAIN
SELECT DISTINCT customer_id
FROM orders
WHERE status = 'PAID';
```

Với status là điều kiện bằng và customer_id đứng tiếp theo trong index, MySQL có cơ hội đọc vùng index của trạng thái PAID theo thứ tự khách hàng. Index ghép này có thể hỗ trợ lọc và loại trùng hiệu quả.

Nếu truy vấn không ràng buộc cột đầu tiên của index, index ghép có thể không phù hợp để phục vụ DISTINCT trên cột phía sau. Quy tắc leftmost prefix cần được xem xét khi thiết kế thứ tự cột.

### 4.3. Covering index

Nếu index chứa toàn bộ cột cần trả về và cột lọc, MySQL có thể đọc kết quả từ index mà không cần truy cập thêm clustered index cho từng hàng (index-only/covering access).

Ví dụ idx_orders_status_customer có thể bao phủ truy vấn chỉ lấy customer_id và lọc theo status. Giảm truy cập bảng có thể giảm I/O, đặc biệt khi bảng có nhiều cột rộng.

Tuy nhiên, thêm index làm tăng dung lượng, chi phí INSERT/UPDATE/DELETE và công việc bảo trì. Chỉ tạo index dựa trên các truy vấn quan trọng, không tạo một index mới cho mỗi câu DISTINCT riêng lẻ.

## 5. Đọc execution plan để biết DISTINCT tốn ở đâu

Dùng EXPLAIN để xem kế hoạch mà optimizer chọn:

```sql
EXPLAIN
SELECT DISTINCT customer_id
FROM orders
WHERE status = 'PAID'
ORDER BY customer_id;
```

Các cột và dấu hiệu cần quan sát:

| Thành phần | Ý nghĩa khi phân tích |
|---|---|
| type | Kiểu truy cập như range, ref hoặc ALL |
| possible_keys | Các index optimizer có thể cân nhắc |
| key | Index thực tế được chọn |
| rows | Số hàng ước lượng cần đọc |
| Extra | Dấu hiệu như Using temporary, Using filesort hoặc Using index for group-by |

Diễn giải thường gặp:

- Using index for group-by có thể cho biết optimizer dùng Loose Index Scan để lấy nhóm giá trị từ index.
- Using temporary cho biết có temporary table trong kế hoạch; cần đánh giá kích thước và thời gian thực tế.
- Using filesort cho biết cần bước sắp xếp bổ sung; tên này không có nghĩa chắc chắn dữ liệu được ghi ra file trên đĩa.
- type = ALL biểu thị table scan; với bảng nhỏ hoặc truy vấn cần phần lớn dữ liệu, scan có thể vẫn là lựa chọn rẻ nhất.

EXPLAIN ANALYZE trên phiên bản hỗ trợ sẽ thực thi SELECT và báo thời gian cùng số hàng thực tế qua các iterator:

```sql
EXPLAIN ANALYZE
SELECT DISTINCT customer_id
FROM orders
WHERE status = 'PAID';
```

Dùng kết quả thực tế để so sánh số hàng đầu vào, số hàng đầu ra và thời gian ở từng bước. EXPLAIN ANALYZE thực thi truy vấn; chỉ dùng sau khi xác nhận câu lệnh an toàn và dữ liệu thử phù hợp.

## 6. DISTINCT có thể che giấu lỗi JOIN

Một trong những cách dùng dễ gây hại là thêm DISTINCT để loại các hàng bị nhân lên bởi JOIN, dù nguyên nhân thực sự là điều kiện JOIN sai hoặc quan hệ một-nhiều chưa được hiểu đúng.

Ví dụ, mỗi khách hàng có nhiều đơn hàng:

```sql
SELECT DISTINCT
    c.customer_id,
    c.full_name
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

Nếu mục tiêu chỉ là lấy khách hàng có ít nhất một đơn hàng PAID, truy vấn EXISTS mô tả đúng ý định hơn:

```sql
SELECT
    c.customer_id,
    c.full_name
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
```

EXISTS chỉ kiểm tra có hàng phù hợp hay không; nó không tạo một hàng kết quả cho mỗi đơn hàng. Optimizer MySQL có thể chuyển truy vấn này thành semi-join hoặc chiến lược tương đương tùy cấu trúc và phiên bản.

Nếu thực sự cần thông tin đơn hàng, không dùng DISTINCT để xóa dữ liệu quan trọng. Hãy quyết định muốn một khách hàng cho mỗi hàng đơn hàng, một tổng hợp theo khách hàng hay một đơn hàng đại diện theo quy tắc xác định.

### 6.1. Kiểm tra quan hệ JOIN trước khi thêm DISTINCT

Khi kết quả bị lặp, kiểm tra số hàng trước khi loại trùng:

```sql
SELECT
    c.customer_id,
    COUNT(*) AS joined_rows
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID'
GROUP BY c.customer_id
HAVING COUNT(*) > 1;
```

Nếu một khách hàng có nhiều hàng, đó có thể là quan hệ một-nhiều đúng theo dữ liệu. Nếu số hàng tăng bất thường, kiểm tra điều kiện JOIN, khóa ngoại và tính duy nhất của bảng được nối.

## 7. Khi nào dùng DISTINCT, GROUP BY hoặc EXISTS?

Các cấu trúc này có mục tiêu khác nhau, dù một số truy vấn có thể trả cùng kết quả.

| Mục tiêu | Cách viết thường phù hợp | Lý do |
|---|---|---|
| Liệt kê giá trị hoặc tổ hợp duy nhất | SELECT DISTINCT ... | Nêu trực tiếp ý định loại hàng trùng |
| Tính số lượng/tổng/trung bình theo nhóm | GROUP BY với aggregate | Mỗi nhóm tạo kết quả tổng hợp |
| Chỉ kiểm tra có bản ghi liên quan | EXISTS | Tránh tạo hàng JOIN lặp khi không cần cột từ bảng con |
| Đếm số giá trị duy nhất | COUNT(DISTINCT expr) | Đếm giá trị khác nhau thay vì trả danh sách |
| Chọn hàng mới nhất trong mỗi nhóm | Window function hoặc truy vấn chọn hàng có thứ tự xác định | DISTINCT không chọn hàng đại diện theo thứ tự |

Không thay DISTINCT bằng GROUP BY chỉ để hy vọng truy vấn nhanh hơn. Optimizer có thể dùng chiến lược tương tự, và GROUP BY thường thể hiện ý định tổng hợp dữ liệu.

## 8. COUNT(DISTINCT) và các biến thể aggregate

COUNT(DISTINCT expr) đếm số giá trị khác nhau của biểu thức, bỏ qua NULL:

```sql
SELECT
    COUNT(*) AS order_rows,
    COUNT(customer_id) AS non_null_customer_ids,
    COUNT(DISTINCT customer_id) AS unique_customers
FROM orders;
```

Ba con số trả lời ba câu hỏi khác nhau:

- COUNT(*): số hàng.
- COUNT(customer_id): số hàng có customer_id khác NULL.
- COUNT(DISTINCT customer_id): số khách hàng khác nhau, không tính NULL.

MySQL còn hỗ trợ đếm tổ hợp nhiều biểu thức:

```sql
SELECT COUNT(DISTINCT customer_id, status)
FROM orders;
```

Cú pháp này đếm các tổ hợp giá trị khác nhau của các biểu thức được liệt kê; tổ hợp có NULL trong một biểu thức bị bỏ qua. Nếu cần tính cả nhóm có NULL, hãy xử lý rõ ràng theo quy tắc nghiệp vụ thay vì thay NULL bằng một sentinel có thể trùng với dữ liệu thật.

Cẩn thận với các aggregate khác:

```sql
SELECT
    SUM(amount) AS total_amount,
    SUM(DISTINCT amount) AS sum_of_distinct_amounts
FROM orders;
```

SUM(DISTINCT amount) chỉ cộng mỗi giá trị amount một lần. Hai đơn hàng khác nhau cùng có giá trị 500.000 sẽ chỉ đóng góp 500.000 một lần. Đây thường không phải tổng doanh thu nghiệp vụ; chỉ dùng khi thật sự cần tổng của tập giá trị amount duy nhất.

## 9. DISTINCT cùng biểu thức, ORDER BY và LIMIT

DISTINCT áp dụng trên các biểu thức được chọn. Nếu chọn biểu thức chuẩn hóa, kết quả sẽ được loại trùng theo giá trị sau chuẩn hóa:

```sql
SELECT DISTINCT DATE(created_at) AS order_day
FROM orders
ORDER BY order_day DESC
LIMIT 30;
```

Truy vấn trả về tối đa 30 ngày khác nhau có đơn hàng. Tuy nhiên, DATE(created_at) là biểu thức trên cột; index thường trên created_at có thể không hỗ trợ trực tiếp việc loại trùng theo ngày như một index trên biểu thức ngày. Nếu truy vấn quan trọng và chạy thường xuyên, cân nhắc generated column lưu ngày hoặc functional index trên biểu thức phù hợp với phiên bản.

Khi dùng DISTINCT với ORDER BY, bảo đảm thứ tự được xác định bởi các giá trị được chọn. MySQL có thể từ chối một số truy vấn SELECT DISTINCT mà ORDER BY tham chiếu biểu thức không nằm trong select list, vì kết quả sắp xếp không xác định sau khi các hàng trùng bị gộp. Đưa biểu thức cần sắp xếp vào select list hoặc tổ chức truy vấn qua derived table để thể hiện rõ quy tắc.

## 10. Các cách tối ưu truy vấn DISTINCT

Hãy bắt đầu bằng việc xác định truy vấn có thực sự cần loại trùng hay không. Nếu cần, có thể áp dụng các hướng sau:

1. **Chỉ chọn cột cần thiết.** Tránh SELECT DISTINCT * nếu mục tiêu chỉ là danh sách ID hoặc trạng thái. Nhiều cột rộng làm tăng chi phí lưu và so sánh hàng trung gian.
2. **Tạo index phù hợp với filter và distinct key.** Cân nhắc index ghép theo thứ tự điều kiện lọc bằng trước, sau đó là cột cần lấy giá trị duy nhất.
3. **Tận dụng leftmost prefix.** Đảm bảo các cột DISTINCT có thể được đọc theo thứ tự index phù hợp, không chỉ nằm ở phía sau một cột index không được ràng buộc.
4. **Dùng covering index khi hợp lý.** Nếu index bao phủ cột lọc và cột trả về, có thể tránh đọc thêm hàng từ clustered index.
5. **Thay JOIN bằng EXISTS khi chỉ cần kiểm tra tồn tại.** Điều này loại bỏ nhu cầu tạo rồi loại các hàng lặp do quan hệ một-nhiều.
6. **Đặt điều kiện lọc chọn lọc.** Giảm số hàng đầu vào trước khi thực hiện duplicate elimination.
7. **Không áp dụng hàm lên cột tùy tiện.** Nếu DISTINCT trên biểu thức thường xuyên, xem xét cột chuẩn hóa hoặc functional index.
8. **Đo kế hoạch và số liệu thực tế.** Dùng EXPLAIN, EXPLAIN ANALYZE, Performance Schema và dữ liệu gần production.

Index làm tăng chi phí ghi và dung lượng. Trước khi thêm index, kiểm tra các index hiện có, workload INSERT/UPDATE/DELETE và khả năng một index ghép đáp ứng nhiều truy vấn.

## 11. Quy trình phân tích một truy vấn DISTINCT chậm

Khi truy vấn loại trùng chậm, hãy làm theo thứ tự:

1. **Xác nhận kết quả cần có.** Cần danh sách cột duy nhất, tổ hợp duy nhất, số lượng duy nhất hay chỉ kiểm tra tồn tại?
2. **Xác nhận ngữ nghĩa bằng nhau.** Kiểm tra NULL, collation, biểu thức và kiểu dữ liệu.
3. **Đếm quy mô đầu vào.** Ước lượng số hàng thỏa WHERE trước khi loại trùng và số giá trị duy nhất dự kiến.
4. **Kiểm tra JOIN.** Xác định có quan hệ một-nhiều hay điều kiện JOIN sai làm nhân bản hàng.
5. **Đọc index.** Kiểm tra index hiện có, thứ tự cột và leftmost prefix.
6. **Chạy EXPLAIN.** Xem key, access type, rows, temporary table, filesort và dấu hiệu Loose Index Scan.
7. **Đo thực tế.** Dùng EXPLAIN ANALYZE trên câu SELECT an toàn và dữ liệu đại diện.
8. **Viết lại theo mục tiêu.** Dùng EXISTS, GROUP BY, COUNT(DISTINCT) hoặc window function khi phù hợp.
9. **Đánh giá index mới.** So sánh lợi ích đọc với chi phí ghi, dung lượng và maintenance.
10. **Kiểm thử kết quả.** Đối chiếu số hàng, tập giá trị, NULL, collation và các trường hợp biên trước/sau khi tối ưu.

## 12. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Dùng DISTINCT để chọn một hàng mới nhất mỗi nhóm | Không có quy tắc chọn hàng đại diện | Dùng ROW_NUMBER() hoặc truy vấn xác định theo thời gian |
| Dùng DISTINCT để che JOIN sai | Kết quả có vẻ hết trùng nhưng lỗi quan hệ vẫn còn | Kiểm tra điều kiện JOIN, cardinality và dùng EXISTS nếu chỉ cần tồn tại |
| Cho rằng DISTINCT trên nhiều cột loại trùng từng cột riêng | Hiểu sai ngữ nghĩa tổ hợp | Xác định rõ tuple cần duy nhất |
| Dùng SELECT DISTINCT * | So sánh và lưu nhiều cột không cần thiết | Chọn đúng cột cần trả về |
| Cho rằng LIMIT 10 chỉ đọc 10 hàng nguồn | Có thể phải đọc nhiều hàng để tìm 10 giá trị duy nhất | Đánh giá index và số hàng trùng |
| Dùng SUM(DISTINCT amount) để tính tổng doanh thu | Các giao dịch cùng số tiền bị gộp | Dùng SUM(amount) theo đơn vị giao dịch |
| Bỏ qua collation | Các chuỗi khác chữ hoa/thường hoặc dấu có thể bị gộp | Chọn collation theo nghiệp vụ |
| Thêm index mà không đo | Tăng chi phí ghi và dung lượng | Đọc EXPLAIN và benchmark trước/sau |

## 13. Ghi nhớ

- DISTINCT loại hàng trùng theo toàn bộ tổ hợp biểu thức trong select list.
- Nhiều NULL được gộp thành một hàng NULL trong kết quả DISTINCT, dù phép NULL = NULL không trả TRUE.
- Collation quyết định các giá trị chuỗi nào được xem là tương đương; thay collation có thể thay đổi kết quả DISTINCT.
- DISTINCT có thể cần đọc nhiều hàng, temporary table, sort, CPU và I/O; số hàng đầu ra ít không bảo đảm truy vấn rẻ.
- Index có thứ tự phù hợp có thể hỗ trợ loại trùng; kiểm tra Using index for group-by và các dấu hiệu trong EXPLAIN.
- DISTINCT trên nhiều cột loại trùng theo tuple, không loại trùng riêng từng cột.
- Nếu chỉ cần kiểm tra hàng liên quan tồn tại, EXISTS thường diễn đạt ý định rõ hơn JOIN cộng DISTINCT.
- COUNT(DISTINCT) bỏ qua NULL; SUM(DISTINCT) có thể sai mục tiêu khi các giao dịch khác nhau có cùng giá trị.
- Không dùng DISTINCT để chọn hàng mới nhất hoặc che giấu quan hệ JOIN sai.
- Tối ưu bằng cách giảm cột, lọc sớm, thiết kế index phù hợp và đo execution plan trên dữ liệu đại diện.

Hãy dùng DISTINCT khi mục tiêu thực sự là lấy các hàng hoặc tổ hợp duy nhất. Khi hiểu rõ ngữ nghĩa và chi phí loại trùng, bạn có thể chọn đúng index hoặc cấu trúc truy vấn để giảm tài nguyên MySQL mà vẫn giữ nguyên kết quả nghiệp vụ.

