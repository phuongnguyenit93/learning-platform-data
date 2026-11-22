# Đẩy điều kiện lọc và ảnh hưởng của thứ tự nối

## Mục tiêu bài học

Một truy vấn nối nhiều bảng có thể xử lý hàng triệu dòng dù kết quả cuối cùng chỉ gồm vài trăm dòng. Một nguyên nhân thường gặp là điều kiện lọc được áp dụng muộn, sau khi các bảng đã tạo ra tập trung gian lớn. Bộ tối ưu truy vấn có thể đẩy những điều kiện hợp lệ xuống gần nơi đọc dữ liệu, đồng thời thay đổi thứ tự nối để giảm số dòng phải xử lý. Tuy nhiên, việc di chuyển điều kiện không phải lúc nào cũng an toàn, đặc biệt với `LEFT JOIN`, `RIGHT JOIN` và `FULL JOIN`.

Trong chương **Phép nối** của module **DATABASE_PERFORMANCE**, bài học này giải thích predicate pushdown, ảnh hưởng của thứ tự nối và cách kiểm tra kết quả bằng kế hoạch thực thi. Module rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; vì vậy mọi thay đổi cần được đánh giá bằng số dòng ước lượng/thực tế, tài nguyên đọc và thời gian chạy trong điều kiện tải đại diện.

Sau bài học, bạn có thể:

- Giải thích vì sao lọc sớm thường làm giảm kích thước tập dữ liệu trung gian.
- Nhận diện điều kiện có thể được đẩy xuống scan hoặc subquery.
- Hiểu cách optimizer sắp xếp lại các phép nối và chọn thuật toán nối.
- Phân biệt ý nghĩa của điều kiện trong `ON` và `WHERE`, nhất là với outer join.
- Đọc `EXPLAIN (ANALYZE, BUFFERS)` để phát hiện lọc muộn, join order không phù hợp và sai lệch ước lượng.
- Chọn cách viết SQL, cập nhật thống kê và kiểm thử để cải thiện truy vấn mà vẫn giữ nguyên kết quả.

## 1. Lọc dữ liệu và phép nối trong một truy vấn

Phép nối kết hợp các dòng từ hai hoặc nhiều quan hệ theo điều kiện. Nếu bảng đầu vào có nhiều dòng, phép nối có thể tạo ra tập kết quả trung gian lớn trước khi bộ lọc loại bỏ phần lớn dữ liệu.

Giả sử hệ thống bán hàng có ba bảng:

- `customers`: thông tin khách hàng và khu vực.
- `orders`: đơn hàng, khách hàng, thời điểm tạo và trạng thái.
- `order_items`: các sản phẩm và số lượng trong từng đơn hàng.

Truy vấn sau tính doanh thu từ đơn đã hoàn tất của khách hàng ở một khu vực trong một khoảng thời gian:

```sql
SELECT
    c.region,
    SUM(oi.quantity * oi.unit_price) AS revenue
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
JOIN order_items AS oi
  ON oi.order_id = o.order_id
WHERE c.region = 'SOUTH'
  AND o.status = 'COMPLETED'
  AND o.created_at >= TIMESTAMP '2026-10-01 00:00:00'
  AND o.created_at <  TIMESTAMP '2026-11-01 00:00:00'
GROUP BY c.region;
```

Điều kiện `c.region` chỉ liên quan đến bảng khách hàng; các điều kiện trạng thái và thời gian chỉ liên quan đến bảng đơn hàng. Nếu có thể áp dụng các điều kiện này ngay khi đọc từng bảng, hệ quản trị sẽ giảm số dòng đưa vào các phép nối tiếp theo.

Ví dụ, nếu `customers` có 10 triệu dòng nhưng khu vực `SOUTH` chỉ chiếm 5%, lọc trước có thể giảm tập khách hàng xuống khoảng 500 nghìn dòng. Nếu bảng `orders` có lịch sử nhiều năm nhưng truy vấn chỉ cần một tháng và một trạng thái, lọc trước cũng có thể giảm mạnh số đơn hàng cần nối. Các con số này chỉ minh họa; tỷ lệ thực tế phải lấy từ dữ liệu và thống kê của hệ thống.

## 2. Predicate pushdown là gì?

**Predicate pushdown** (đẩy điều kiện lọc) là việc đưa một điều kiện lọc xuống gần nguồn dữ liệu nhất có thể, thường là vào thao tác scan của bảng, partition hoặc subquery. Mục tiêu là loại bỏ các dòng không cần thiết trước khi chúng đi qua những phép toán tốn kém như join, sort, aggregate hoặc truyền dữ liệu giữa các node.

Một cách nhìn đơn giản:

```text
Lọc muộn:
  Đọc customers --------+
                        +--> JOIN --> JOIN --> FILTER --> GROUP BY
  Đọc orders -----------+
  Đọc order_items ------------------+

Lọc sớm (khi hợp lệ):
  Đọc customers --> FILTER --+
                             +--> JOIN --> JOIN --> GROUP BY
  Đọc orders ------> FILTER -+
  Đọc order_items ------------+
```

Sơ đồ thể hiện ý tưởng giảm dữ liệu đầu vào; kế hoạch vật lý thực tế do optimizer lựa chọn và có thể không giống hệt sơ đồ.

### 2.1. Điều kiện lọc cục bộ và điều kiện nối

Có thể chia điều kiện truy vấn thành các nhóm:

| Nhóm điều kiện | Ví dụ | Nơi có thể áp dụng |
|---|---|---|
| Lọc trên một bảng | `o.status = 'COMPLETED'` | Scan của bảng `orders` |
| Điều kiện nối | `o.customer_id = c.customer_id` | Join node hoặc access path dùng khóa nối |
| Lọc trên biểu thức nhiều bảng | `o.total > c.credit_limit` | Thường cần dữ liệu từ cả hai phía, có thể ở join/filter node |
| Lọc sau tổng hợp | `SUM(oi.quantity) > 10` | `HAVING`, sau khi tạo nhóm |

Điều kiện chỉ phụ thuộc một bảng thường là ứng viên tốt cho pushdown. Điều kiện cần giá trị từ cả hai bảng không thể được áp dụng hoàn chỉnh trước khi hai phía được kết hợp. Tuy nhiên, optimizer có thể biến đổi biểu thức hoặc suy ra điều kiện tương đương nếu điều đó hợp lệ.

### 2.2. Ví dụ lọc trước khi nối

Có thể diễn đạt rõ tập đơn hàng cần dùng bằng một CTE:

```sql
WITH recent_completed_orders AS (
    SELECT order_id, customer_id
    FROM orders
    WHERE status = 'COMPLETED'
      AND created_at >= TIMESTAMP '2026-10-01 00:00:00'
      AND created_at <  TIMESTAMP '2026-11-01 00:00:00'
)
SELECT
    c.region,
    SUM(oi.quantity * oi.unit_price) AS revenue
FROM recent_completed_orders AS o
JOIN customers AS c
  ON c.customer_id = o.customer_id
JOIN order_items AS oi
  ON oi.order_id = o.order_id
WHERE c.region = 'SOUTH'
GROUP BY c.region;
```

CTE làm rõ ý định và giúp người đọc thấy tập đơn hàng đã được giới hạn. Nhưng CTE không tự động bảo đảm dữ liệu được vật hóa hoặc được thực thi trước. PostgreSQL từ phiên bản 12 thường có thể inline CTE không đệ quy, không có tác dụng phụ và được tham chiếu một lần; optimizer tiếp tục tối ưu toàn truy vấn. `MATERIALIZED` có thể yêu cầu ranh giới vật hóa, còn `NOT MATERIALIZED` cho phép inline trong các trường hợp hỗ trợ. Các hệ quản trị khác có quy tắc riêng.

Không nên tạo CTE chỉ để ép thứ tự thực thi nếu chưa có bằng chứng. Một ranh giới vật hóa có thể ngăn một số phép biến đổi và khiến hệ quản trị phải ghi/đọc tập trung gian. Hãy so sánh kế hoạch trước khi quyết định dùng `MATERIALIZED` hoặc cấu trúc tương đương.

### 2.3. Sargability: điều kiện phải có khả năng tận dụng đường truy cập

Đẩy điều kiện xuống scan không đồng nghĩa chắc chắn dùng được index. Điều kiện cần có dạng phù hợp với chỉ mục và kiểu dữ liệu. Ví dụ, với chỉ mục B-tree trên `created_at`, cách viết khoảng thời gian sau thường dễ tận dụng hơn:

```sql
WHERE created_at >= TIMESTAMP '2026-10-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-01 00:00:00'
```

So với cách bọc cột trong hàm:

```sql
WHERE DATE(created_at) = DATE '2026-10-15'
```

Biểu thức thứ hai có thể không dùng trực tiếp index B-tree thông thường trên `created_at`, tùy hệ quản trị và phép biến đổi optimizer. Có thể viết lại thành khoảng thời gian tương đương hoặc tạo expression index nếu truy vấn thường xuyên dùng biểu thức đó. Với cột có múi giờ, cần xác định rõ múi giờ nghiệp vụ trước khi chuyển điều kiện để không thay đổi tập kết quả.

Các nguyên tắc hỗ trợ pushdown và index access:

- So sánh cột với hằng hoặc tham số có kiểu dữ liệu tương thích.
- Tránh ép kiểu hoặc áp hàm lên cột được lập chỉ mục nếu không có expression index phù hợp.
- Dùng khoảng nửa mở cho lọc theo ngày/giờ để xử lý chính xác ranh giới.
- Chỉ chọn các cột cần thiết, tránh `SELECT *` khi không cần toàn bộ dòng.
- Giữ điều kiện tương đương về logic khi viết lại; không đổi ngữ nghĩa NULL, collation hoặc kiểu dữ liệu.

## 3. Optimizer thay đổi thứ tự nối như thế nào?

Với các phép nối inner join, thứ tự kết hợp thường có thể thay đổi mà không làm thay đổi kết quả logic. Ví dụ, về mặt đại số quan hệ:

\[
(A \bowtie B) \bowtie C \equiv A \bowtie (B \bowtie C)
\]

Khi điều kiện nối và ngữ nghĩa phù hợp, optimizer có thể chọn nối hai bảng có tập kết quả nhỏ trước, rồi nối kết quả đó với bảng còn lại. Mục tiêu thường là giảm số dòng trung gian và chi phí tổng thể.

Giả sử:

- `orders` có 50 triệu dòng.
- `customers` có 5 triệu dòng, trong đó chỉ một phần nhỏ thuộc khu vực đang truy vấn.
- `order_items` có 200 triệu dòng, trung bình vài dòng cho mỗi đơn hàng.
- Truy vấn chỉ cần đơn hàng đã hoàn tất trong một tháng và khách hàng ở một khu vực.

Một kế hoạch có thể bắt đầu bằng cách lọc `orders` và `customers`, sau đó nối các tập nhỏ hơn với `order_items`. Một kế hoạch khác có thể bắt đầu từ partition của `orders`, dùng chỉ mục trên `customer_id` hoặc `order_id`, hoặc chọn thuật toán nối khác. Không thể xác định thứ tự tối ưu chỉ bằng số dòng tổng của từng bảng; cần biết số dòng sau lọc, độ trùng lặp của khóa, phân bố dữ liệu và chi phí truy cập.

### 3.1. Vì sao thứ tự nối ảnh hưởng hiệu năng?

Mỗi phép nối tạo ra một tập dòng đầu ra. Nếu hai phía có nhiều dòng trùng khóa, số dòng kết quả có thể lớn hơn đáng kể số dòng ở từng phía. Đưa một tập lớn vào nhiều phép nối tiếp theo làm tăng:

- Số dòng cần so khớp và xử lý.
- Bộ nhớ cho hash table hoặc sort.
- I/O nếu dữ liệu trung gian vượt bộ nhớ.
- Số lần lặp inner scan trong nested loop.
- Lượng dữ liệu phải truyền giữa các worker hoặc node trong hệ thống phân tán.

Một join order tốt thường giữ các tập trung gian ở mức hợp lý. Tuy nhiên, “nối bảng nhỏ trước” chỉ là quy tắc gợi ý. Bảng nhỏ nhưng không có đường truy cập phù hợp hoặc có khóa nối phân bố bất lợi vẫn có thể tạo kế hoạch kém. Thứ tự nối tối ưu phải xét cả cardinality sau lọc và chi phí của từng thuật toán.

### 3.2. Ước lượng số dòng quyết định lựa chọn

Optimizer không chạy thử mọi thứ tự nối trên toàn bộ dữ liệu. Nó dùng thống kê để ước lượng số dòng sau filter và join, rồi so sánh chi phí dự kiến của các phương án.

Ví dụ, nếu thống kê ước lượng `status = 'COMPLETED'` trả về 2% số đơn hàng nhưng thực tế là 70%, optimizer có thể chọn một nested loop dựa trên giả định tập đầu vào nhỏ. Khi chạy, inner scan lặp lại quá nhiều lần và truy vấn chậm hơn dự kiến.

Các nguyên nhân sai lệch phổ biến:

- Thống kê chưa được cập nhật sau khi dữ liệu thay đổi lớn.
- Phân bố dữ liệu lệch (skew), một số giá trị xuất hiện rất thường xuyên.
- Các cột lọc có tương quan nhưng optimizer giả định chúng độc lập.
- Số lượng giá trị phân biệt hoặc độ trùng lặp khóa nối được ước lượng sai.
- Tham số thực tế khác với giá trị dùng khi lập kế hoạch hoặc có độ chọn lọc rất khác nhau.
- Điều kiện có biểu thức, kiểu dữ liệu hoặc hàm khiến việc ước lượng khó hơn.

Trong PostgreSQL, `ANALYZE` cập nhật thống kê cơ bản; extended statistics như `dependencies`, `mcv` và `ndistinct` có thể cải thiện ước lượng tương quan giữa nhiều cột trong cùng một bảng. Chúng không tự mô hình hóa mọi tương quan giữa các bảng. Hãy xác định loại sai lệch trước khi tăng statistics target hoặc tạo extended statistics.

## 4. Thuật toán nối và mối liên hệ với join order

Thứ tự nối và thuật toán nối là hai quyết định liên quan nhưng khác nhau. Join order xác định quan hệ nào được kết hợp trước; thuật toán xác định cách thực hiện từng phép nối.

### 4.1. Nested Loop Join

Nested loop duyệt các dòng ở phía ngoài, rồi tìm dòng tương ứng ở phía trong. Nó có thể hiệu quả khi phía ngoài nhỏ và phía trong có chỉ mục tốt trên khóa nối.

```text
Nested Loop
  -> tập dòng bên ngoài đã lọc (ít dòng)
  -> Index Scan trên bảng bên trong theo khóa nối
```

Nếu phía ngoài có 100 dòng và mỗi lần inner index scan chỉ đọc vài dòng, nested loop có thể rất nhanh. Nhưng nếu phía ngoài thực tế có hàng triệu dòng, việc lặp inner scan có thể trở nên đắt. Khi đọc kế hoạch, chú ý `loops` của node bên trong và số dòng thực tế mỗi loop.

### 4.2. Hash Join

Hash join thường xây dựng hash table từ một phía, rồi quét phía còn lại để tìm khóa khớp. Nó thường phù hợp với tập dữ liệu lớn khi điều kiện nối là phép bằng và không cần thứ tự đầu ra.

```text
Hash Join
  Hash Cond: (o.customer_id = c.customer_id)
  -> Scan phía probe
  -> Hash
       -> Scan phía build
```

Kích thước phía build, bộ nhớ cấp phát và số dòng thực tế ảnh hưởng lớn đến hiệu năng. Nếu hash table không vừa bộ nhớ, PostgreSQL có thể chia batch và dùng vùng lưu trữ tạm. Khi đó cần xem thông tin batch, disk usage và buffers trong kế hoạch.

### 4.3. Merge Join

Merge join kết hợp hai đầu vào đã được sắp xếp theo khóa nối. Nó có thể hiệu quả khi đầu vào đã có thứ tự phù hợp từ index hoặc khi chi phí sort được chia sẻ với các thao tác khác. Nếu phải sort hai tập rất lớn chỉ để merge, chi phí sắp xếp có thể đáng kể.

### 4.4. Bảng so sánh

| Thuật toán | Thường phù hợp | Rủi ro cần theo dõi |
|---|---|---|
| Nested Loop | Phía ngoài nhỏ; phía trong có index hoặc lookup rẻ | `loops` lớn, inner scan lặp nhiều, ước lượng phía ngoài sai |
| Hash Join | Tập lớn, điều kiện equality, không cần đầu vào đã sắp xếp | Hash table lớn, batch/spill ra đĩa, thiếu bộ nhớ |
| Merge Join | Hai đầu vào có thứ tự theo khóa nối hoặc sort có lợi | Sort tốn CPU/memory/I/O, thứ tự đầu vào không phù hợp |

Không nên ép một thuật toán chỉ dựa trên tên node. Nếu optimizer chọn nested loop, có thể nó đang dựa vào ước lượng đầu vào nhỏ và index lookup rẻ. Hãy tìm hiểu vì sao ước lượng đó đúng hoặc sai trước khi thay đổi cấu hình.

## 5. Giới hạn pushdown: ON, WHERE và outer join

Một lỗi viết lại SQL thường gặp là di chuyển điều kiện giữa `ON` và `WHERE` mà không xét ngữ nghĩa outer join. Với inner join, nhiều điều kiện có thể được biến đổi tương đương. Với outer join, các dòng không khớp được bổ sung giá trị `NULL`, nên vị trí điều kiện có thể thay đổi kết quả.

### 5.1. INNER JOIN

Với inner join, điều kiện lọc một phía có thể thường được đặt trong `WHERE` hoặc điều kiện nối mà vẫn giữ kết quả tương đương nếu biểu thức và kiểu dữ liệu giống nhau:

```sql
-- Cách 1
SELECT c.customer_id, o.order_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'COMPLETED';

-- Cách 2
SELECT c.customer_id, o.order_id
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'COMPLETED';
```

Hai truy vấn trên có cùng ngữ nghĩa inner join. Optimizer thường có thể đưa điều kiện `o.status` xuống scan của `orders` bất kể điều kiện được viết ở vị trí nào. Dù vậy, hãy xác nhận kế hoạch và tránh chuyển đổi khi biểu thức có hàm volatile, phép ép kiểu hoặc ngữ nghĩa đặc biệt.

### 5.2. LEFT JOIN: điều kiện trên bảng bên phải

Giả sử cần liệt kê mọi khách hàng và các đơn hàng đã thanh toán nếu có. Cách viết đúng yêu cầu:

```sql
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
 AND o.status = 'PAID';
```

Điều kiện `o.status = 'PAID'` nằm trong `ON`, nên nó giới hạn những dòng ở phía phải được xem là khớp. Khách hàng không có đơn đã thanh toán vẫn xuất hiện với các cột `o.*` là `NULL`.

Nếu chuyển điều kiện đó xuống `WHERE`:

```sql
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE o.status = 'PAID';
```

Các dòng không có đơn hàng sẽ có `o.status = NULL`; điều kiện `WHERE` không giữ các dòng này. Kết quả vì thế loại bỏ khách hàng không có đơn đã thanh toán và có hành vi gần với inner join đối với điều kiện đó.

### 5.3. LEFT JOIN: điều kiện trên bảng bên trái

Vị trí điều kiện trên phía được bảo toàn cũng có thể thay đổi kết quả:

```sql
-- Giữ mọi khách hàng; chỉ ghép đơn nếu khách ở khu vực SOUTH
SELECT c.customer_id, o.order_id
FROM customers AS c
LEFT JOIN orders AS o
  ON o.customer_id = c.customer_id
 AND c.region = 'SOUTH';
```

Khách hàng ở khu vực khác vẫn được trả về, nhưng không có đơn ghép. Nếu đặt `c.region = 'SOUTH'` trong `WHERE`, các khách hàng ngoài khu vực bị loại khỏi kết quả. Vì vậy, không được chuyển điều kiện giữa `ON` và `WHERE` một cách máy móc.

### 5.4. FULL JOIN và các phép nối ngoài

`RIGHT JOIN` có ngữ nghĩa đối xứng với `LEFT JOIN`; `FULL JOIN` bảo toàn dòng không khớp từ cả hai phía. Điều kiện lọc trên phía có thể nhận `NULL` cần được phân tích theo quy tắc ba giá trị của SQL. Một điều kiện trong `WHERE` có thể loại dòng được outer join bổ sung, khiến kết quả thay đổi đáng kể.

Optimizer có thể đẩy một số điều kiện qua outer join khi chứng minh được tính tương đương, hoặc chuyển một outer join thành inner join khi điều kiện phía nullable loại bỏ mọi dòng NULL-extended. Nhưng các biến đổi này bị giới hạn bởi ngữ nghĩa. Khi tự viết lại truy vấn, hãy kiểm tra kết quả trên trường hợp có và không có dòng khớp, cùng các giá trị NULL.

## 6. Những điều kiện hạn chế hoặc ngăn pushdown

Không phải mọi predicate đều có thể được đẩy tới scan. Một số rào cản thường gặp:

- **Outer join:** phải giữ nguyên dòng không khớp và vị trí sinh giá trị NULL.
- **Aggregation:** điều kiện trên nhóm (`HAVING`) thường chỉ có thể áp dụng sau khi nhóm được tạo; điều kiện trên cột đầu vào có thể được đẩy xuống trước aggregate nếu tương đương.
- **Window function:** lọc trước hoặc sau cửa sổ có thể thay đổi tập dòng tham gia tính toán và kết quả thứ hạng.
- **LIMIT/OFFSET:** đẩy lọc qua giới hạn có thể thay đổi dòng được chọn; không phải lúc nào cũng tương đương.
- **Set operation:** `UNION`, `INTERSECT`, `EXCEPT` có quy tắc riêng; chỉ đẩy predicate nếu giữ nguyên kết quả và xử lý duplicate phù hợp.
- **Hàm volatile hoặc có tác dụng phụ:** việc đổi số lần gọi hoặc thời điểm gọi có thể thay đổi hành vi.
- **CTE hoặc subquery có ranh giới vật hóa:** optimizer có thể không đẩy điều kiện qua ranh giới đó.
- **Kiểu dữ liệu, collation và NULL:** ép kiểu, so sánh chuỗi hoặc điều kiện NULL có thể làm phép viết lại không còn tương đương.

Một số hệ quản trị còn có ranh giới bảo mật như security barrier view hoặc chính sách row-level security, có thể hạn chế việc di chuyển predicate để bảo toàn ngữ nghĩa và bảo mật.

## 7. Đọc EXPLAIN để nhận diện lọc muộn và join order

Trong PostgreSQL, `EXPLAIN` hiển thị cây kế hoạch. Đọc từ các node lá (scan) lên các node cha (join, aggregate, sort). `EXPLAIN (ANALYZE, BUFFERS)` thực thi câu lệnh và bổ sung số liệu thực tế.

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    c.region,
    SUM(oi.quantity * oi.unit_price) AS revenue
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
JOIN order_items AS oi
  ON oi.order_id = o.order_id
WHERE c.region = 'SOUTH'
  AND o.status = 'COMPLETED'
  AND o.created_at >= TIMESTAMP '2026-10-01 00:00:00'
  AND o.created_at <  TIMESTAMP '2026-11-01 00:00:00'
GROUP BY c.region;
```

### 7.1. Các trường quan trọng

| Trường/node | Cách diễn giải |
|---|---|
| `Seq Scan` / `Index Scan` / `Bitmap Heap Scan` | Cách đọc dữ liệu từ từng quan hệ |
| `Index Cond` | Điều kiện được dùng để tìm mục trong chỉ mục |
| `Filter` | Điều kiện được kiểm tra trên dòng ở node đó; có thể cho thấy một phần lọc được áp dụng sau access path |
| `Hash Cond` / `Merge Cond` | Điều kiện dùng cho phép nối tương ứng |
| `Join Filter` | Điều kiện bổ sung được kiểm tra tại join node |
| `Rows Removed by Filter` | Dòng bị loại tại node do filter |
| `Rows Removed by Join Filter` | Dòng hoặc cặp dòng bị loại bởi join filter |
| `estimated rows` và `actual rows` | So sánh ước lượng với số dòng thực tế |
| `loops` | Số lần node được thực thi; đặc biệt quan trọng với nested loop |
| `Buffers` | Mức sử dụng shared/local/temp buffers theo output |
| `Planning Time` / `Execution Time` | Thời gian lập kế hoạch và thực thi được báo cáo |

Không phải mọi `Filter` đều là dấu hiệu lỗi. Một điều kiện có thể được đặt tại node đó vì ngữ nghĩa, vì chi phí hoặc vì không có index phù hợp. Hãy xem số dòng trước và sau filter, số buffer và thời gian của node để đánh giá mức độ lãng phí.

### 7.2. Phát hiện ước lượng sai

Giả sử kế hoạch cho thấy:

```text
Nested Loop  (cost=... rows=100 ...)
  (actual time=... rows=250000 loops=1)
  -> Index Scan ... (rows=100)
       (actual ... rows=5000 loops=1)
  -> Index Scan ... (rows=1)
       (actual ... rows=50 loops=5000)
```

Đây là ví dụ minh họa cho trường hợp số dòng thực tế lớn hơn ước lượng. Inner scan được gọi 5.000 lần và mỗi lần trả nhiều dòng hơn dự kiến; tổng công việc có thể tăng mạnh. Cần kiểm tra thống kê, độ trùng lặp khóa và điều kiện lọc trước khi kết luận nested loop là sai.

Nếu filter xuất hiện ở node phía trên join và loại bỏ phần lớn dòng, hãy hỏi:

1. Điều kiện có chỉ phụ thuộc vào một bảng không?
2. Có thể áp dụng nó sớm hơn mà không đổi kết quả không?
3. Có chỉ mục hoặc partition pruning hỗ trợ điều kiện không?
4. Optimizer đã có thống kê đủ tốt để ước lượng số dòng sau lọc chưa?
5. Có ranh giới outer join, aggregate, LIMIT hoặc materialization ngăn pushdown không?

### 7.3. Join order thể hiện trong cây kế hoạch

Với cây kế hoạch, node join bên dưới được thực hiện trước node join bên trên. Ví dụ:

```text
Hash Join
  Hash Cond: (o.customer_id = c.customer_id)
  -> Hash Join
       Hash Cond: (oi.order_id = o.order_id)
       -> Scan order_items
       -> Scan orders (đã lọc)
  -> Hash
       -> Scan customers (đã lọc)
```

Đây chỉ là một thứ tự minh họa. Kế hoạch khác có thể nối khách hàng với đơn hàng trước rồi mới nối dòng hàng. Để hiểu lựa chọn, hãy đọc estimated/actual rows của từng nhánh và tổng chi phí truy cập, không chỉ nhìn thứ tự văn bản trong câu SQL.

## 8. Các chiến lược cải thiện truy vấn

### 8.1. Viết điều kiện lọc rõ ràng và có thể tận dụng index

Đặt predicate trực tiếp trên cột có kiểu dữ liệu phù hợp, tránh chuyển đổi không cần thiết. Dùng điều kiện khoảng khi lọc thời gian. Nếu truy vấn thường xuyên lọc theo nhiều cột, xem xét chỉ mục ghép dựa trên thứ tự điều kiện, độ chọn lọc và các truy vấn khác.

### 8.2. Giảm số cột và số dòng trước khi nối

Chỉ chọn các cột cần thiết. Nếu một bảng lớn chỉ cần một tập khóa để nối, hãy tránh mang theo payload rộng qua nhiều join node. Tuy nhiên, đừng thêm `DISTINCT` hoặc aggregate chỉ để giảm dòng nếu điều đó thay đổi ngữ nghĩa hoặc tạo thêm chi phí sort/hash.

### 8.3. Dùng EXISTS khi chỉ cần kiểm tra sự tồn tại

Nếu mục tiêu là lấy khách hàng có ít nhất một đơn hàng hoàn tất, không cần trả về mọi cặp khách hàng-đơn hàng. Có thể diễn đạt bằng `EXISTS`:

```sql
SELECT c.customer_id, c.region
FROM customers AS c
WHERE c.region = 'SOUTH'
  AND EXISTS (
      SELECT 1
      FROM orders AS o
      WHERE o.customer_id = c.customer_id
        AND o.status = 'COMPLETED'
  );
```

`EXISTS` biểu diễn semi-join: mỗi khách hàng được trả về tối đa một lần khi có ít nhất một dòng phù hợp. Viết `JOIN` rồi `DISTINCT` có thể tạo nhiều dòng trung gian trước khi loại trùng. Optimizer có thể tự biến đổi một số dạng truy vấn sang semi-join, nhưng `EXISTS` thường diễn đạt đúng ý định và tránh nhân dòng ngoài mong muốn.

### 8.4. Cập nhật và cải thiện thống kê

Nếu actual rows khác xa estimated rows, kiểm tra thời điểm `ANALYZE`, độ lệch phân bố và tương quan cột. Trong PostgreSQL:

```sql
ANALYZE customers;
ANALYZE orders;
ANALYZE order_items;
```

Đối với cột có tương quan trong cùng bảng, có thể xem extended statistics:

```sql
CREATE STATISTICS orders_status_region_stats
    (dependencies, mcv)
ON status, sales_channel
FROM orders;

ANALYZE orders;
```

Ví dụ trên chỉ có ý nghĩa nếu `sales_channel` là cột tồn tại và hai cột có tương quan trong dữ liệu. Thống kê mở rộng có chi phí lưu trữ và thu thập; hãy tạo dựa trên sai lệch ước lượng quan sát được. Không thể dùng nó để mô tả trực tiếp tương quan giữa các bảng.

### 8.5. Cân nhắc partition pruning

Nếu bảng lớn được partition theo thời gian, điều kiện lọc trên partition key có thể giúp bỏ qua các partition không liên quan. Ví dụ, truy vấn đơn hàng tháng 10 chỉ cần đọc partition chứa khoảng thời gian đó nếu điều kiện tương thích với chiến lược partition. Hãy kiểm tra kế hoạch có hiển thị partition được loại bỏ hay không. Một predicate bọc partition key trong hàm hoặc ép kiểu không phù hợp có thể làm giảm khả năng pruning tùy hệ quản trị.

### 8.6. Không ép join order trước khi hiểu optimizer

Một số hệ quản trị cung cấp hint hoặc cấu hình giới hạn việc reorder join. PostgreSQL có các tham số như `join_collapse_limit` ảnh hưởng việc làm phẳng và sắp xếp lại explicit join. Việc ép thứ tự có thể hữu ích trong một tình huống đã được đo và tái hiện, nhưng dễ làm truy vấn kém đi khi dữ liệu hoặc thống kê thay đổi.

Trước khi dùng hint hoặc cấu hình để khóa join order:

- Xác minh estimated rows có đáng tin cậy không.
- Xem index, partition pruning và điều kiện lọc đã được khai thác chưa.
- Kiểm tra nhiều giá trị tham số và mức tải khác nhau.
- Đo lại sau khi cập nhật thống kê hoặc thay đổi dữ liệu.
- Ghi rõ lý do, phạm vi và điều kiện cần xem xét lại hint.

## 9. Ví dụ thực hành: từ kế hoạch kém đến kế hoạch tốt hơn

Giả sử truy vấn báo cáo nối `customers`, `orders` và `order_items`, nhưng thực tế chỉ cần khách hàng ở một khu vực và đơn hoàn tất trong một tháng.

**Bước 1 — Ghi baseline.** Chạy truy vấn gốc với `EXPLAIN (ANALYZE, BUFFERS)`. Lưu thời gian, actual rows, estimated rows, loops, buffers, temp I/O và thuật toán nối.

**Bước 2 — Xác định filter cục bộ.** Xem điều kiện `c.region`, `o.status` và `o.created_at` có được áp dụng tại scan của từng bảng không. Nếu filter xuất hiện sau join, tìm hiểu lý do ngữ nghĩa hoặc giới hạn tối ưu.

**Bước 3 — Kiểm tra access path.** Xem chỉ mục phù hợp với các điều kiện lọc và khóa nối đã tồn tại chưa. Ví dụ, một index trên `orders(created_at, customer_id)` hoặc `(status, created_at, customer_id)` có thể hữu ích tùy độ chọn lọc và các truy vấn khác; không tạo index chỉ dựa trên ví dụ.

**Bước 4 — Kiểm tra ước lượng.** Nếu số dòng thực tế lệch xa ước lượng, cập nhật thống kê và xem phân bố, tương quan cột. Đo lại trước khi đổi SQL.

**Bước 5 — Thử viết lại có kiểm soát.** Có thể dùng CTE/subquery để làm rõ tập đơn hàng đã lọc, nhưng xác nhận optimizer vẫn inline hoặc chọn kế hoạch phù hợp. Với truy vấn chỉ kiểm tra tồn tại, cân nhắc `EXISTS` để tránh nhân dòng.

**Bước 6 — Kiểm tra ngữ nghĩa.** Nếu truy vấn có outer join, so sánh kết quả trước/sau trên trường hợp không có dòng khớp, có nhiều dòng khớp và có giá trị NULL. Đảm bảo di chuyển điều kiện không làm mất dòng được bảo toàn.

**Bước 7 — Đo lại toàn workload.** So sánh p50/p95/p99, thông lượng, CPU, I/O, temp spill, lock waits và độ trễ các truy vấn khác. Giữ thay đổi khi kết quả nghiệp vụ không đổi và lợi ích hiệu năng được xác nhận.

## 10. Những nhầm lẫn thường gặp

- **“Điều kiện nào cũng nên đặt vào CTE để lọc trước.”** Optimizer có thể inline CTE; vật hóa không cần thiết có thể làm mất cơ hội tối ưu xuyên suốt truy vấn.
- **“Bảng nhỏ nhất luôn phải được nối đầu tiên.”** Cần xét số dòng sau lọc, độ trùng lặp khóa, index và thuật toán nối.
- **“Thứ tự bảng trong FROM luôn là thứ tự thực thi.”** Với inner join, optimizer thường có thể reorder; outer join và các ranh giới ngữ nghĩa giới hạn phép biến đổi.
- **“Đưa điều kiện từ WHERE vào ON luôn tương đương.”** Có thể đúng với inner join nhưng thay đổi kết quả với outer join.
- **“Filter ở node trên cùng luôn là lỗi.”** Có thể là vị trí bắt buộc về ngữ nghĩa hoặc có chi phí thấp hơn; cần đo số dòng và tài nguyên.
- **“Nested Loop luôn chậm với bảng lớn.”** Nó có thể tốt khi phía ngoài nhỏ và inner lookup có index hiệu quả.
- **“Hash Join luôn cần toàn bộ bảng nằm trong RAM.”** Hash join có thể chia batch và dùng lưu trữ tạm; spill làm tăng chi phí nhưng không nhất thiết làm truy vấn thất bại.
- **“Ép join order sẽ sửa được mọi kế hoạch xấu.”** Nếu thống kê sai hoặc điều kiện không tận dụng index, hint có thể chỉ che triệu chứng và dễ lỗi thời.
- **“EXPLAIN cost là thời gian thực tế.”** Cost là ước lượng; cần `ANALYZE`, buffers và phép đo tải để đánh giá.

## 11. Checklist tối ưu predicate pushdown và join order

- [ ] Đã xác định truy vấn và workload gây tốn tài nguyên bằng số liệu.
- [ ] Đã phân loại điều kiện lọc theo từng bảng, điều kiện nối và điều kiện sau tổng hợp.
- [ ] Đã kiểm tra filter được áp dụng ở scan hay sau join.
- [ ] Đã xác nhận predicate có thể tận dụng index hoặc partition pruning.
- [ ] Đã so sánh estimated rows với actual rows tại các scan và join node.
- [ ] Đã xem `loops`, thuật toán nối, buffers và temp I/O.
- [ ] Đã kiểm tra thống kê, độ lệch dữ liệu và tương quan giữa các cột.
- [ ] Đã giữ nguyên ngữ nghĩa `ON`/`WHERE`, NULL và dòng không khớp của outer join.
- [ ] Đã cân nhắc `EXISTS` khi chỉ cần kiểm tra sự tồn tại.
- [ ] Đã đo trước/sau với cùng dữ liệu, tham số và mức đồng thời đại diện.
- [ ] Đã kiểm tra tác động của thay đổi tới các truy vấn và giao dịch khác.

## Kết luận

Đẩy điều kiện lọc giúp giảm dữ liệu đi qua các phép nối, còn thay đổi thứ tự nối giúp optimizer kiểm soát kích thước tập trung gian và chi phí của từng thuật toán. Hai kỹ thuật này phụ thuộc vào khả năng ước lượng số dòng, cấu trúc chỉ mục, phân bố dữ liệu và ngữ nghĩa của truy vấn.

Khi tối ưu, hãy xác định predicate cục bộ, kiểm tra điều kiện có thể tận dụng index hoặc partition pruning, đọc join tree và so sánh số dòng ước lượng với thực tế. Đặc biệt, phải bảo toàn ngữ nghĩa outer join khi di chuyển điều kiện giữa `ON` và `WHERE`. Chỉ giữ thay đổi sau khi kết quả dữ liệu không đổi và phép đo trước/sau chứng minh hiệu năng tốt hơn trên workload đại diện.
