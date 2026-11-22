# DISTINCT và chi phí loại trùng trên tập dữ liệu lớn

## Mục tiêu bài học

`DISTINCT` giúp loại bỏ các dòng trùng nhau trong kết quả truy vấn. Với một bảng nhỏ, thao tác này thường đơn giản. Với hàng chục hoặc hàng trăm triệu dòng, hệ quản trị phải xác định những giá trị nào giống nhau, giữ lại một đại diện cho mỗi nhóm và có thể cần sắp xếp hoặc xây dựng cấu trúc băm lớn. Chi phí CPU, bộ nhớ và I/O tạm vì thế có thể trở thành phần tốn kém nhất của truy vấn.

Trong chương **Sắp xếp và tổng hợp** của module **DATABASE_PERFORMANCE**, bài học này phân tích ngữ nghĩa của `DISTINCT`, các chiến lược loại trùng bằng sort hoặc hash, cách dùng `DISTINCT ON`, window function và các dạng truy vấn thay thế. Module rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; do đó, cần đo chi phí loại trùng trong toàn bộ truy vấn, xác định đúng khóa nghiệp vụ và kiểm tra cả tác động tới workload đọc/ghi.

Sau bài học, bạn có thể:

- Xác định chính xác dòng nào được xem là trùng theo danh sách biểu thức của `SELECT DISTINCT`.
- Giải thích hai chiến lược phổ biến: sort rồi loại trùng và hash-based aggregation.
- Đọc `Sort`, `Unique`, `HashAggregate`, thông tin bộ nhớ và spill trong kế hoạch thực thi.
- Chọn giữa `DISTINCT`, `DISTINCT ON`, `ROW_NUMBER()`, `EXISTS`, `GROUP BY` và `UNION ALL` theo yêu cầu kết quả.
- Đánh giá vai trò của chỉ mục, độ rộng dòng, thống kê và mức đồng thời.
- Kiểm chứng thay đổi bằng số dòng, thời gian, buffer, I/O tạm và tính đúng đắn của kết quả.

## 1. DISTINCT loại bỏ dòng trùng như thế nào?

`SELECT DISTINCT` trả về các dòng duy nhất theo **toàn bộ danh sách biểu thức được chọn**. Nó không tự hiểu khóa nghiệp vụ của bảng và cũng không tự chọn bản ghi mới nhất trong mỗi nhóm.

Ví dụ, bảng `orders` có nhiều đơn hàng của cùng một khách hàng:

```sql
SELECT DISTINCT customer_id
FROM orders;
```

Truy vấn trên trả về mỗi `customer_id` một lần. Nhưng nếu chọn thêm `order_id`:

```sql
SELECT DISTINCT customer_id, order_id
FROM orders;
```

thì hai dòng chỉ được xem là trùng nếu cả `customer_id` và `order_id` giống nhau. Nếu `order_id` là khóa duy nhất, `DISTINCT` gần như không loại được dòng nào và chỉ thêm chi phí xử lý.

### 1.1. DISTINCT khác với “một dòng cho mỗi khóa”

Giả sử cần lấy đơn hàng mới nhất của từng khách hàng. Câu lệnh sau không đáp ứng yêu cầu:

```sql
SELECT DISTINCT customer_id, status, created_at
FROM orders;
```

Nó chỉ loại các dòng có cùng cả ba giá trị. Một khách hàng có nhiều đơn hàng với thời gian hoặc trạng thái khác nhau vẫn xuất hiện nhiều lần. Để chọn một bản ghi đại diện theo quy tắc nghiệp vụ, cần xác định thứ tự ưu tiên, chẳng hạn thời điểm mới nhất và mã đơn hàng dùng để phá hòa.

### 1.2. NULL và phép so sánh

Trong quá trình loại trùng, các dòng có cùng cấu trúc giá trị NULL được gom như các dòng trùng. Ví dụ:

```sql
SELECT DISTINCT region
FROM customers;
```

Nếu nhiều khách hàng có `region IS NULL`, kết quả chỉ có một dòng NULL. Điều này khác với biểu thức so sánh thông thường `NULL = NULL`, vốn không trả về TRUE theo logic ba giá trị của SQL.

Với dữ liệu chuỗi, cách xác định hai giá trị tương đương còn phụ thuộc kiểu dữ liệu và collation. Collation không phân biệt hoa/thường hoặc dấu có thể khiến các chuỗi được xem là tương đương theo quy tắc của collation đó. Khi tối ưu hoặc đổi collation, cần xác nhận ngữ nghĩa loại trùng không thay đổi ngoài ý muốn.

### 1.3. DISTINCT không bảo đảm thứ tự kết quả

Không có `ORDER BY`, thứ tự dòng trả về không được bảo đảm. Kế hoạch có thể dùng hash aggregate, sort hoặc một đường truy cập khác; thứ tự quan sát được ở một lần chạy không phải cam kết cho lần sau.

Nếu ứng dụng cần thứ tự ổn định, phải chỉ rõ `ORDER BY` với các khóa đủ để phân định thứ tự. Không dựa vào việc PostgreSQL đang dùng `Sort` để loại trùng rồi giả định kết quả luôn có thứ tự như mong muốn.

## 2. Vì sao DISTINCT trên dữ liệu lớn tốn kém?

Để loại trùng, hệ quản trị phải so sánh hoặc tra cứu các giá trị đã gặp. Nếu truy vấn đọc N dòng và chỉ có D giá trị khác nhau, engine vẫn cần xử lý các dòng đầu vào để xác định dòng nào thuộc nhóm đã tồn tại, trừ khi có một đường truy cập đặc biệt cho phép giảm đáng kể công việc.

Các yếu tố ảnh hưởng:

- **Số dòng đầu vào (N):** càng nhiều dòng phải xét, chi phí CPU và đọc dữ liệu càng cao.
- **Số giá trị khác nhau (D):** ảnh hưởng số nhóm cần lưu trong cấu trúc hash hoặc số phần tử sau sắp xếp.
- **Độ rộng dòng:** so sánh và lưu nhiều cột, đặc biệt chuỗi dài hoặc biểu thức phức tạp, làm tăng CPU và bộ nhớ.
- **Kiểu dữ liệu và collation:** một số phép so sánh hoặc chuẩn hóa chuỗi có chi phí cao hơn so sánh số nguyên.
- **Bộ nhớ khả dụng:** cấu trúc sort/hash có thể vượt giới hạn bộ nhớ và phải dùng vùng lưu trữ tạm.
- **Tính chọn lọc của điều kiện lọc:** lọc được nhiều dòng trước khi loại trùng sẽ giảm lượng dữ liệu cần xử lý.
- **Thứ tự đầu vào:** dữ liệu đã có thứ tự theo khóa loại trùng có thể giúp tránh một bước sort riêng.

Không thể chỉ nhìn tỷ lệ trùng lặp để kết luận truy vấn rẻ. Một bảng có hàng trăm triệu dòng nhưng chỉ vài nghìn giá trị khác nhau vẫn có thể cần đọc lượng lớn dữ liệu đầu vào để xác định các nhóm đó.

## 3. Hai chiến lược loại trùng phổ biến

PostgreSQL có thể dùng các chiến lược vật lý khác nhau để thực hiện `DISTINCT`. Hai dạng kế hoạch thường gặp là sort kết hợp `Unique`, hoặc hash-based aggregation. Hệ quản trị khác có tên node và cơ chế riêng.

### 3.1. Sort rồi loại trùng

Một cách thực hiện là sắp xếp các dòng theo biểu thức cần phân biệt. Khi các dòng giống nhau nằm cạnh nhau, executor chỉ giữ một dòng đại diện trong mỗi nhóm liên tiếp.

```text
Unique
  -> Sort
       Sort Key: customer_id
       -> Scan orders
```

Với N dòng, sắp xếp tổng quát thường có chi phí xấp xỉ (O(N \log N)). Sau khi sắp xếp, bước `Unique` duyệt tuần tự để bỏ các dòng lặp. Nếu đầu vào đã được sắp theo khóa phù hợp từ chỉ mục hoặc node phía dưới, hệ quản trị có thể giảm hoặc bỏ bước sort.

Sort cần bộ nhớ để giữ dữ liệu trung gian. Nếu vượt giới hạn, PostgreSQL có thể ghi các run đã sắp xếp ra đĩa rồi trộn chúng. Kế hoạch thường hiển thị `Sort Method: external merge` và dung lượng `Disk`; output `BUFFERS` có thể cho thấy temp read/write.

### 3.2. Hash-based aggregation

Một cách khác là dùng hash table với các biểu thức cần phân biệt làm khóa. Khi đọc từng dòng, executor tra khóa trong hash table; nếu đã tồn tại thì bỏ qua, nếu chưa thì thêm nhóm mới.

```text
HashAggregate
  Group Key: customer_id
  -> Scan orders
```

Đối với `SELECT DISTINCT customer_id`, PostgreSQL có thể dùng `HashAggregate` với `customer_id` là khóa nhóm. Chi phí kỳ vọng thường gần tuyến tính theo số dòng đầu vào khi hash hoạt động hiệu quả, nhưng bộ nhớ cần thiết tăng theo số nhóm và kích thước khóa. Khi hash table không vừa bộ nhớ, executor có thể chia batch và dùng đĩa tạm; output có thể hiển thị `Batches`, `Memory Usage` và `Disk Usage`.

### 3.3. So sánh sort và hash

| Tiêu chí | Sort + Unique | HashAggregate |
|---|---|---|
| Cách làm | Sắp xếp theo khóa rồi bỏ dòng liền kề | Lưu khóa đã gặp trong hash table |
| Chi phí thường gặp | Sort tốn CPU và có thể spill; bước Unique duyệt tuần tự | Hash lookup nhanh khi phù hợp, nhưng cần bộ nhớ cho các nhóm |
| Có thể tận dụng thứ tự đầu vào | Có; index hoặc node đã sắp xếp có thể tránh sort | Không cần đầu vào có thứ tự |
| Rủi ro khi thiếu bộ nhớ | External sort và I/O tạm | Nhiều batch hoặc spill ra đĩa |
| Kết quả có thứ tự | Sort tạo thứ tự nội bộ, nhưng không thay thế cam kết `ORDER BY` | Không bảo đảm thứ tự |

Không có thuật toán tốt nhất trong mọi tình huống. Optimizer cân nhắc số dòng ước lượng, số nhóm, chi phí sort/hash, thứ tự có sẵn và cấu hình bộ nhớ. Hãy đọc kế hoạch thực tế thay vì ép buộc thuật toán theo quy tắc chung.

## 4. Đọc EXPLAIN để tìm chi phí loại trùng

Trong PostgreSQL, dùng `EXPLAIN` để xem kế hoạch ước lượng. `EXPLAIN (ANALYZE, BUFFERS)` thực thi truy vấn và cung cấp số dòng, thời gian cùng thông tin buffer thực tế:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT DISTINCT customer_id
FROM orders
WHERE status = 'PAID';
```

### 4.1. Các node thường gặp

| Node/trường | Ý nghĩa khi phân tích |
|---|---|
| `HashAggregate` | Loại trùng bằng cách gom nhóm qua hash table |
| `Sort` | Sắp xếp dữ liệu theo khóa; xem phương pháp sort và dung lượng dùng |
| `Unique` | Loại các dòng lặp liền kề từ đầu vào đã có thứ tự phù hợp |
| `Group Key` | Các biểu thức xác định một nhóm duy nhất |
| `Sort Key` | Các biểu thức được dùng để sắp xếp |
| `actual rows` | Số dòng đầu ra thực tế của node |
| `loops` | Số lần node được thực thi |
| `Sort Method` | Ví dụ `quicksort`, `external merge` hoặc phương pháp khác theo phiên bản |
| `Memory Usage` / `Disk Usage` | Bộ nhớ hoặc dung lượng tạm mà node báo cáo |
| `Batches` | Số batch của hash operation; nhiều batch có thể cho thấy hash không nằm trọn trong bộ nhớ |
| `Buffers` | Hoạt động shared/local/temp buffer theo output |
| `Planning Time` / `Execution Time` | Thời gian lập kế hoạch và thực thi trong lần đo |

### 4.2. Nhận diện sort spill

Ví dụ output minh họa:

```text
Unique
  -> Sort
       Sort Key: customer_id
       Sort Method: external merge  Disk: 64000kB
       -> Seq Scan on orders
            Filter: (status = 'PAID')
```

`external merge` cho biết sort đã dùng các run tạm trên đĩa. Đây là dấu hiệu cần xem xét nếu sort chiếm phần lớn thời gian. Hãy kiểm tra số dòng đầu vào, độ rộng khóa/dòng, `work_mem`, temp read/write và mức đồng thời. Không nên tăng `work_mem` ngay khi thấy spill mà chưa tính tổng nhu cầu bộ nhớ của nhiều truy vấn đồng thời.

### 4.3. Nhận diện hash spill

Ví dụ output minh họa:

```text
HashAggregate
  Group Key: customer_id
  Batches: 8
  Memory Usage: 4096kB
  Disk Usage: 32768kB
  -> Seq Scan on orders
       Filter: (status = 'PAID')
```

Nhiều batch và `Disk Usage` cho thấy hash aggregate đã dùng vùng lưu trữ tạm. Kiểm tra số nhóm thực tế, kích thước khóa, số dòng đầu vào và giới hạn bộ nhớ. Nếu số nhóm ước lượng thấp hơn thực tế nhiều, cần xem thống kê và phân bố dữ liệu.

Các con số trong ví dụ chỉ minh họa cách đọc output, không phải ngưỡng hiệu năng chuẩn cho mọi hệ thống.

## 5. Giảm dữ liệu trước khi loại trùng

Thông thường, giảm số dòng đầu vào là cách trực tiếp nhất để giảm chi phí loại trùng, miễn là giữ nguyên kết quả nghiệp vụ.

Ví dụ cần danh sách khách hàng có đơn đã thanh toán trong tháng:

```sql
SELECT DISTINCT customer_id
FROM orders
WHERE status = 'PAID'
  AND created_at >= TIMESTAMP '2026-10-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-01 00:00:00';
```

Các điều kiện trạng thái và thời gian giới hạn tập đầu vào trước khi loại trùng. Có thể cần chỉ mục phù hợp với workload, chẳng hạn B-tree trên `(status, created_at, customer_id)` hoặc một thiết kế khác dựa trên độ chọn lọc và các truy vấn liên quan. Không có thứ tự cột tối ưu chung; phải xem kế hoạch, số dòng đọc và chi phí ghi.

### 5.1. Chỉ mục có thể giúp gì?

Một B-tree có thứ tự theo khóa loại trùng có thể cung cấp đầu vào đã sắp xếp, từ đó hỗ trợ kế hoạch `Unique` mà không cần một node sort riêng. Với truy vấn lọc theo trạng thái và lấy danh sách khách hàng, chỉ mục ghép có thể được xem xét:

```sql
CREATE INDEX idx_orders_status_customer
ON orders (status, customer_id);
```

Khi `status` được cố định bằng điều kiện bằng, các mục trong phần tương ứng của chỉ mục có thứ tự theo `customer_id`. Tuy nhiên, engine vẫn có thể phải đọc nhiều index entry để xác định mọi khách hàng khác nhau. Chỉ mục không tự bảo đảm bỏ qua toàn bộ các bản ghi trùng hoặc làm truy vấn nhanh hơn sequential scan + hash aggregate.

Nếu truy vấn cần thêm điều kiện thời gian, cần đánh giá cách bố trí cột trong index và khả năng dùng range scan. Ví dụ `(status, created_at, customer_id)` có thể lọc thời gian tốt nhưng không cung cấp thứ tự toàn cục theo `customer_id` trong toàn khoảng thời gian; `(status, customer_id, created_at)` có thứ tự khách hàng phù hợp nhưng có thể phải xét nhiều entry hơn khi lọc theo thời gian. Chọn theo workload và kế hoạch thực tế.

### 5.2. Lọc trước khi join

Nếu `DISTINCT` được dùng để loại các bản sao phát sinh từ phép nối, hãy xác định liệu có thể giảm đầu vào hoặc đổi kiểu phép nối không. Ví dụ, nếu chỉ cần khách hàng có ít nhất một đơn đã thanh toán, `EXISTS` diễn đạt đúng mục tiêu:

```sql
SELECT c.customer_id
FROM customers AS c
WHERE EXISTS (
    SELECT 1
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
);
```

So với nối mọi đơn hàng rồi dùng `DISTINCT`, dạng `EXISTS` cho phép optimizer dùng semi-join và dừng tìm kiếm sau khi xác định được một dòng phù hợp trong các trường hợp thích hợp. Quan trọng hơn, nó thể hiện rõ rằng ứng dụng chỉ quan tâm đến sự tồn tại, không cần mọi cặp khách hàng-đơn hàng.

Đừng dùng `DISTINCT` để che một phép nối sai khóa. Nếu một bảng được kỳ vọng có một dòng cho mỗi `customer_id` nhưng thực tế có nhiều dòng, hãy kiểm tra ràng buộc duy nhất và điều kiện nối. Loại trùng ở cuối có thể che lỗi dữ liệu hoặc lỗi mô hình và vẫn phải trả chi phí lớn.

## 6. Chọn một bản ghi đại diện: DISTINCT ON và window function

Nhiều bài toán gọi là “loại trùng” thực chất cần chọn một dòng theo quy tắc ưu tiên, ví dụ bản ghi mới nhất, trạng thái hiện hành hoặc sự kiện có phiên bản cao nhất.

### 6.1. DISTINCT ON trong PostgreSQL

PostgreSQL cung cấp `DISTINCT ON`, cho phép giữ một dòng đầu tiên cho mỗi nhóm biểu thức. Ví dụ lấy sự kiện mới nhất của mỗi khách hàng:

```sql
SELECT DISTINCT ON (customer_id)
       customer_id,
       event_id,
       event_type,
       created_at
FROM customer_events
ORDER BY customer_id, created_at DESC, event_id DESC;
```

Các điểm cần nhớ:

- `DISTINCT ON (customer_id)` xác định nhóm cần một dòng đại diện.
- `ORDER BY` xác định dòng nào được xem là dòng đầu tiên trong từng nhóm.
- Các biểu thức `DISTINCT ON` phải khớp với các biểu thức `ORDER BY` đứng đầu theo quy tắc PostgreSQL.
- `event_id DESC` là khóa phá hòa để kết quả ổn định khi nhiều sự kiện có cùng `created_at`.
- `DISTINCT ON` là phần mở rộng riêng của PostgreSQL, không phải cú pháp SQL chuẩn dùng chung cho mọi hệ quản trị.

Nếu bỏ `ORDER BY` hoặc không xác định thứ tự đủ rõ, dòng được giữ lại có thể không ổn định. Không được dùng `DISTINCT ON` như một cách viết ngắn cho `SELECT DISTINCT` khi mục tiêu chỉ là loại các dòng hoàn toàn giống nhau.

Một B-tree có thể hỗ trợ thứ tự này:

```sql
CREATE INDEX idx_customer_events_latest
ON customer_events (customer_id, created_at DESC, event_id DESC)
INCLUDE (event_type);
```

Index có thể giúp cung cấp thứ tự phù hợp và trả cột payload. Nhưng tùy phân bố dữ liệu, số dòng, visibility và chi phí truy cập, optimizer vẫn có thể chọn kế hoạch khác. Với nhiều dòng lịch sử cho mỗi khách hàng, việc đọc các entry để tìm dòng đầu mỗi nhóm vẫn có chi phí; không giả định rằng index sẽ tự động nhảy qua mọi bản ghi trùng.

### 6.2. ROW_NUMBER() khi cần tính linh hoạt

Window function phù hợp khi cần chọn một dòng theo nhiều điều kiện hoặc muốn giữ thêm thông tin xếp hạng:

```sql
WITH ranked_events AS (
    SELECT
        customer_id,
        event_id,
        event_type,
        created_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY created_at DESC, event_id DESC
        ) AS rn
    FROM customer_events
)
SELECT customer_id, event_id, event_type, created_at
FROM ranked_events
WHERE rn = 1;
```

`ROW_NUMBER()` đánh số dòng trong từng nhóm theo thứ tự đã chỉ định. Điều kiện `rn = 1` giữ lại một dòng. Nếu cần giữ tất cả dòng đồng hạng ở giá trị mới nhất, hãy xem `RANK()` hoặc `DENSE_RANK()` và xác định rõ quy tắc nghiệp vụ.

Window function có thể cần sort theo partition key và thứ tự xếp hạng. Trên dữ liệu lớn, xem node `WindowAgg`, `Sort`, số dòng đầu vào và temp I/O. Không mặc định window function nhanh hơn `DISTINCT ON`; hãy so sánh cả hai khi dùng PostgreSQL và kết quả cần thiết giống nhau.

## 7. Các lựa chọn khác và khi nào nên dùng

| Mục tiêu | Cách viết thường phù hợp | Lưu ý hiệu năng/ngữ nghĩa |
|---|---|---|
| Loại các dòng giống nhau trên toàn bộ cột đã chọn | `SELECT DISTINCT ...` | Phải xét tất cả biểu thức trong select list |
| Lấy một dòng theo nhóm và thứ tự ưu tiên trong PostgreSQL | `DISTINCT ON (...)` | Phải xác định `ORDER BY` và khóa phá hòa |
| Chọn/xếp hạng dòng trong mỗi nhóm theo quy tắc linh hoạt | `ROW_NUMBER()` | Có thể cần sort và WindowAgg |
| Chỉ kiểm tra có dòng liên quan hay không | `EXISTS` | Có thể tạo semi-join, tránh nhân dòng không cần thiết |
| Tính tổng hợp theo nhóm | `GROUP BY` với aggregate | Dùng khi cần `COUNT`, `SUM`, `MIN`, `MAX` hoặc giá trị nhóm |
| Kết hợp tập kết quả mà không cần loại trùng | `UNION ALL` | Tránh bước loại trùng toàn cục của `UNION` |
| Kết hợp tập kết quả và cần loại trùng | `UNION` | Có chi phí loại trùng trên kết quả kết hợp |
| Ngăn dữ liệu trùng ngay khi ghi | `UNIQUE` constraint/index | Bảo vệ tính toàn vẹn dữ liệu, tránh chỉ dựa vào truy vấn đọc |

### 7.1. DISTINCT và GROUP BY

Nếu chỉ cần danh sách nhóm duy nhất:

```sql
SELECT customer_id
FROM orders
GROUP BY customer_id;
```

thường có cùng ý nghĩa kết quả với:

```sql
SELECT DISTINCT customer_id
FROM orders;
```

Không nên đổi sang `GROUP BY` với kỳ vọng nó luôn nhanh hơn. Optimizer thường có thể chuyển chúng về chiến lược vật lý tương tự. Dùng `GROUP BY` khi có phép tổng hợp hoặc khi cách viết thể hiện rõ mô hình nhóm.

### 7.2. COUNT(DISTINCT)

`COUNT(DISTINCT customer_id)` đếm số giá trị khác nhau và bỏ qua NULL theo quy tắc của `COUNT`:

```sql
SELECT COUNT(DISTINCT customer_id)
FROM orders
WHERE status = 'PAID';
```

Đây có thể là thao tác tốn kém trên tập lớn vì engine phải xác định các giá trị duy nhất trước khi đếm. Hãy kiểm tra kế hoạch và cách triển khai aggregate. Không thay bằng `COUNT(*)` trên subquery nếu chưa xác minh cách xử lý NULL và tính tương đương.

### 7.3. UNION và UNION ALL

`UNION` loại trùng trên tập kết quả hợp nhất; `UNION ALL` giữ tất cả dòng. Nếu hai nguồn đã bảo đảm không giao nhau hoặc nghiệp vụ chấp nhận dòng lặp, `UNION ALL` tránh được bước loại trùng không cần thiết.

```sql
-- Giữ nguyên mọi dòng từ hai nguồn
SELECT customer_id FROM active_customers
UNION ALL
SELECT customer_id FROM archived_customers;
```

Chỉ đổi `UNION` thành `UNION ALL` sau khi xác nhận không cần loại trùng. Nếu hai nguồn có thể chứa cùng khách hàng và kết quả yêu cầu mỗi khách hàng một lần, phép đổi sẽ làm thay đổi kết quả.

## 8. Khi dữ liệu trùng cần được ngăn từ đầu

Nếu quy tắc nghiệp vụ nói rằng một khóa chỉ được xuất hiện một lần, nên cân nhắc bảo vệ quy tắc đó bằng `UNIQUE` constraint hoặc unique index thay vì liên tục loại trùng ở mọi truy vấn đọc.

Ví dụ, mỗi nguồn ngoài chỉ được nhập một sự kiện cho một mã sự kiện:

```sql
CREATE TABLE imported_events (
    source_name text NOT NULL,
    source_event_id text NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    payload jsonb NOT NULL,
    CONSTRAINT uq_imported_event
        UNIQUE (source_name, source_event_id)
);
```

Khi nạp lại dữ liệu có thể lặp, PostgreSQL hỗ trợ `ON CONFLICT`:

```sql
INSERT INTO imported_events
    (source_name, source_event_id, payload)
VALUES
    ('partner_a', 'evt-1001', '{"type":"created"}'::jsonb)
ON CONFLICT (source_name, source_event_id) DO NOTHING;
```

Unique constraint vừa bảo đảm tính đúng đắn khi nhiều tiến trình ghi đồng thời, vừa tạo cơ chế xác định khóa trùng ở thời điểm ghi. Tuy nhiên, nó làm tăng chi phí `INSERT`, `UPDATE` và lưu trữ index. Nếu dữ liệu trùng cần được giữ để kiểm toán hoặc xử lý lại, không nên xóa/loại ở tầng ghi một cách tùy tiện.

## 9. Bộ nhớ, spill và mức đồng thời

### 9.1. work_mem không phải giới hạn RAM toàn truy vấn

Trong PostgreSQL, `work_mem` là ngân sách bộ nhớ cơ sở cho một số thao tác sort và hash trước khi chúng phải dùng vùng tạm. Nó áp dụng theo từng thao tác, không phải một giới hạn tổng cho toàn bộ truy vấn hoặc toàn máy chủ. Một truy vấn có nhiều node sort/hash, chạy song song hoặc nhiều session đồng thời có thể sử dụng tổng bộ nhớ lớn hơn nhiều lần giá trị `work_mem`.

`hash_mem_multiplier` (trong các phiên bản PostgreSQL hỗ trợ) ảnh hưởng ngân sách bộ nhớ hash so với `work_mem`. Trước khi thay đổi, cần kiểm tra phiên bản, loại node và mức đồng thời. Tăng cấu hình toàn cục có thể làm hệ thống thiếu RAM khi nhiều truy vấn nặng chạy cùng lúc.

### 9.2. Cách xử lý spill có căn cứ

Khi thấy sort hoặc hash dùng đĩa tạm:

1. Xác định node spill và số dòng đầu vào.
2. Kiểm tra có thể lọc sớm, giảm số cột hoặc giảm số dòng trước bước loại trùng không.
3. Xem thống kê có ước lượng sai số nhóm hoặc độ rộng dữ liệu không.
4. Xác định spill có thực sự chiếm phần lớn thời gian hay không qua temp I/O và thời gian node.
5. Thử điều chỉnh bộ nhớ ở phạm vi phiên hoặc workload kiểm thử, đo cả truy vấn đơn và tải đồng thời.
6. Kiểm tra tổng bộ nhớ và các truy vấn khác sau thay đổi.

Tăng bộ nhớ có thể giảm spill nhưng không sửa được một truy vấn phải xử lý quá nhiều dòng không cần thiết. Nếu N rất lớn, giảm đầu vào hoặc thay đổi cách biểu đạt nghiệp vụ có thể đem lại lợi ích lớn hơn.

## 10. Quy trình tối ưu DISTINCT trên tập dữ liệu lớn

**Bước 1 — Xác định ý nghĩa “trùng”.** Ghi rõ khóa nghiệp vụ, biểu thức cần phân biệt, cách xử lý NULL, collation và liệu cần một dòng bất kỳ hay một dòng theo thứ tự ưu tiên.

**Bước 2 — Lưu baseline.** Chạy `EXPLAIN (ANALYZE, BUFFERS)` trong môi trường phù hợp. Ghi số dòng đầu vào/đầu ra, node sort/hash/unique, thời gian, CPU, buffer, temp read/write và độ trễ p95/p99 ở mức workload.

**Bước 3 — Tìm cơ hội giảm đầu vào.** Kiểm tra filter, partition pruning, điều kiện join và số cột đang được đưa vào bước loại trùng. Bảo đảm việc đẩy filter không đổi ngữ nghĩa.

**Bước 4 — Chọn đúng cấu trúc truy vấn.** Dùng `DISTINCT` cho dòng duy nhất theo select list; `DISTINCT ON` hoặc `ROW_NUMBER()` khi cần chọn đại diện; `EXISTS` khi chỉ cần kiểm tra tồn tại; `UNION ALL` khi không cần loại trùng giữa nguồn.

**Bước 5 — Đánh giá chỉ mục.** Kiểm tra index hiện có có thể hỗ trợ filter hoặc cung cấp thứ tự theo khóa loại trùng không. Tính cả chi phí đọc index entry, heap fetch, kích thước và chi phí ghi.

**Bước 6 — Kiểm tra bộ nhớ và spill.** Đọc `Sort Method`, `Disk Usage`, `Batches`, temp buffers và số nhóm. Thử cấu hình bộ nhớ ở phạm vi kiểm soát nếu dữ liệu cho thấy spill là nút thắt.

**Bước 7 — So sánh kết quả đúng.** Đối chiếu tập kết quả trước/sau, kể cả NULL, dòng đồng hạng và các trường hợp khóa trùng. Với bài toán chọn dòng đại diện, xác nhận quy tắc phá hòa.

**Bước 8 — Đo lại trên tải đại diện.** So sánh thời gian, p95/p99, throughput, CPU, I/O, temp spill, bộ nhớ và độ trễ ghi. Lặp lại với nhiều độ chọn lọc và mức đồng thời.

**Bước 9 — Quyết định dựa trên toàn workload.** Giữ thay đổi khi kết quả nghiệp vụ tương đương và lợi ích lớn hơn chi phí duy trì chỉ mục, bộ nhớ, ghi và vận hành.

## 11. Những nhầm lẫn thường gặp

- **“DISTINCT loại trùng theo khóa chính của bảng.”** Nó loại trùng theo toàn bộ biểu thức trong select list.
- **“DISTINCT chọn dòng mới nhất.”** Nó không có quy tắc chọn đại diện theo thời gian; cần `DISTINCT ON` với `ORDER BY` hoặc window function.
- **“Có DISTINCT thì kết quả tự được sắp xếp.”** Thứ tự không được bảo đảm nếu thiếu `ORDER BY`.
- **“Hash luôn nhanh hơn sort.”** Hash có thể tốn bộ nhớ và spill; sort có thể tận dụng thứ tự sẵn có từ index.
- **“Tạo index trên khóa DISTINCT là đủ.”** Engine vẫn có thể phải đọc nhiều index entry; lợi ích phụ thuộc filter, thứ tự và phân bố dữ liệu.
- **“Tăng work_mem càng cao càng tốt.”** Bộ nhớ được dùng bởi nhiều thao tác và nhiều session; tăng quá mức có thể gây áp lực RAM.
- **“Dùng GROUP BY chắc chắn nhanh hơn DISTINCT.”** Hai cách có thể được tối ưu thành kế hoạch tương tự.
- **“Dùng UNION ALL thay UNION luôn an toàn.”** Chỉ đúng khi nghiệp vụ không cần loại dòng trùng giữa các tập.
- **“DISTINCT sửa được join sai.”** Nó có thể che lỗi nhân dòng do khóa nối hoặc quan hệ một-nhiều không được hiểu đúng.
- **“Heap hoặc temp read luôn là đọc đĩa vật lý.”** Buffer statistics và cache phải được xem cùng để hiểu I/O thực tế.

## 12. Checklist loại trùng hiệu quả

- [ ] Đã xác định chính xác biểu thức hoặc khóa nghiệp vụ dùng để nhận diện dòng trùng.
- [ ] Đã xác định có cần chọn dòng đại diện theo thứ tự ưu tiên hay chỉ cần giá trị duy nhất.
- [ ] Đã kiểm tra cách xử lý NULL, collation và giá trị đồng hạng.
- [ ] Đã đo số dòng đầu vào và số nhóm đầu ra.
- [ ] Đã đọc node `Sort`, `Unique`, `HashAggregate` và các chỉ số memory/disk/batches.
- [ ] Đã xem filter có thể áp dụng sớm hơn và có giữ nguyên ngữ nghĩa không.
- [ ] Đã kiểm tra index có thể hỗ trợ lọc hoặc thứ tự đầu vào hay không.
- [ ] Đã cân nhắc `EXISTS`, `DISTINCT ON`, `ROW_NUMBER()`, `GROUP BY` hoặc `UNION ALL` theo đúng mục tiêu.
- [ ] Đã kiểm tra spill và mức đồng thời trước khi thay đổi `work_mem`.
- [ ] Đã so sánh tính đúng đắn và hiệu năng trước/sau trên dữ liệu đại diện.
- [ ] Đã tính cả chi phí ghi, kích thước index và tác động tới workload khác.

## Kết luận

`DISTINCT` loại bỏ các dòng trùng theo toàn bộ biểu thức được chọn. Trên tập dữ liệu lớn, quá trình này có thể cần sort hoặc hash, tiêu thụ CPU và bộ nhớ, thậm chí ghi dữ liệu tạm ra đĩa. Chỉ mục có thể cung cấp thứ tự hoặc giảm đầu vào, nhưng không tự động loại bỏ mọi chi phí đọc và so sánh.

Trước khi tối ưu, hãy xác định đúng ý nghĩa của dòng trùng. Nếu cần chọn một bản ghi mới nhất, dùng `DISTINCT ON` hoặc window function với thứ tự phá hòa rõ ràng; nếu chỉ cần kiểm tra tồn tại, cân nhắc `EXISTS`; nếu không cần loại trùng giữa các nguồn, dùng `UNION ALL`. Đọc kế hoạch thực thi, đo sort/hash spill và xác nhận kết quả trước/sau để lựa chọn giải pháp phù hợp với toàn workload.
