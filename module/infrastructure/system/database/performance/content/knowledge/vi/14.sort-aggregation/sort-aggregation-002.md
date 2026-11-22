# Sắp xếp top-N, LIMIT và yêu cầu thứ tự kết quả xác định

Truy vấn top-N thường xuất hiện trong màn hình danh sách, bảng xếp hạng, trang quản trị và báo cáo: lấy 10 đơn hàng mới nhất, 20 sản phẩm có doanh thu cao nhất hoặc 50 sự kiện gần đây. `LIMIT`, `TOP` hay `FETCH FIRST` giới hạn số hàng trả về, còn `ORDER BY` xác định thứ tự để chọn đúng những hàng đó. Nếu thứ tự không đầy đủ hoặc không duy nhất, các hàng ở ranh giới top-N có thể thay đổi giữa những lần chạy. Nếu hệ quản trị phải sắp xếp một tập dữ liệu lớn rồi mới giới hạn kết quả, thao tác sort cũng có thể trở thành nút thắt CPU, bộ nhớ và I/O.

Bài học thuộc chương **Sắp xếp và tổng hợp** của module **DATABASE_PERFORMANCE**. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu. Nội dung module hướng dẫn thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, tối ưu top-N phải đồng thời bảo đảm ngữ nghĩa thứ tự, tính ổn định của phân trang và hiệu năng đo được trên workload thực tế.

## 1. ORDER BY quyết định thứ tự, LIMIT quyết định số hàng

`ORDER BY` chỉ định thứ tự kết quả theo một hoặc nhiều biểu thức. `LIMIT`, `TOP` hoặc `FETCH FIRST` giới hạn số hàng được trả về theo cú pháp của hệ quản trị. Khi kết hợp, hệ quản trị cần tìm đúng N hàng đầu theo thứ tự đã yêu cầu.

Ví dụ lấy 10 đơn hàng mới nhất:

```sql
SELECT order_id, customer_id, created_at, total_amount
FROM orders
ORDER BY created_at DESC
LIMIT 10;
```

Ví dụ trên thể hiện cú pháp PostgreSQL/MySQL. SQL Server thường dùng `TOP (10)` hoặc `OFFSET ... FETCH`; Oracle và các hệ quản trị khác có cú pháp giới hạn hàng riêng. Ý nghĩa quan trọng là thứ tự phải được khai báo bằng `ORDER BY`.

Nếu bỏ `ORDER BY`:

```sql
SELECT order_id, customer_id, created_at
FROM orders
LIMIT 10;
```

hệ quản trị có thể trả về bất kỳ 10 hàng nào mà kế hoạch thực thi tạo ra trước. Thứ tự có thể thay đổi khi chỉ mục, dữ liệu, thống kê, song song hóa hoặc phiên bản thay đổi. Thứ tự vật lý của bảng hay thứ tự một lần chạy trước đó không phải cam kết thứ tự kết quả.

`LIMIT` cũng không tự làm truy vấn nhanh. Nếu hệ quản trị phải đọc hàng triệu hàng, tính biểu thức sắp xếp rồi mới xác định 10 hàng đầu, lượng công việc vẫn có thể rất lớn dù chỉ trả về 10 hàng.

## 2. Thứ tự xác định và khóa phụ duy nhất

Một thứ tự được xác định (deterministic ordering) là thứ tự mà mỗi hàng trong tập kết quả có vị trí rõ ràng. Nếu `ORDER BY` dùng cột có giá trị trùng nhau, các hàng bằng nhau theo tất cả biểu thức sắp xếp chưa có thứ tự tương đối được bảo đảm.

Ví dụ:

```sql
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC
LIMIT 10;
```

Nếu nhiều đơn hàng có cùng `created_at`, hệ quản trị có thể trả các hàng đồng thời ở vị trí thứ 10 theo thứ tự khác nhau giữa các lần chạy. Muốn xác định đầy đủ thứ tự, thêm khóa phụ duy nhất:

```sql
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
LIMIT 10;
```

Giả sử `order_id` là khóa chính duy nhất. Khi đó hai hàng khác nhau luôn được phân biệt bởi cặp `(created_at, order_id)`. Thứ tự này giúp top-N ổn định và tạo điểm tiếp tục rõ ràng cho keyset pagination.

### 2.1. Khóa phụ cần phù hợp với ý nghĩa nghiệp vụ

Khóa phụ không nhất thiết phải là khóa chính, nhưng phải tạo thứ tự cuối cùng duy nhất trong tập kết quả. Có thể dùng một mã định danh ổn định hoặc tổ hợp cột có constraint duy nhất. Không nên dùng giá trị ngẫu nhiên được tạo lại mỗi lần truy vấn hoặc một biểu thức không ổn định làm khóa phân xử.

Nếu nghiệp vụ muốn các hàng cùng điểm được xem là đồng hạng, không nên thêm khóa phụ vào cùng tiêu chí xác định nhóm đồng hạng. Thay vào đó, phân biệt rõ:

- Thứ tự dùng để xác định từng hàng khi phân trang.
- Tiêu chí dùng để xác định các hàng đồng hạng khi xếp hạng.

Hai mục tiêu này có thể cần hai truy vấn hoặc hai lớp biểu thức khác nhau.

### 2.2. Thứ tự của NULL và collation

Nếu cột sắp xếp có thể là `NULL`, cần xác định vị trí của giá trị thiếu. Một số hệ quản trị hỗ trợ `NULLS FIRST` và `NULLS LAST`; cú pháp và mặc định khác nhau giữa sản phẩm. Ví dụ theo cú pháp PostgreSQL/Oracle:

```sql
SELECT product_id, published_at
FROM products
ORDER BY published_at DESC NULLS LAST, product_id DESC
FETCH FIRST 20 ROWS ONLY;
```

Với hệ quản trị không hỗ trợ cú pháp đó, có thể dùng biểu thức `CASE` để quy định thứ tự, nhưng biểu thức có thể ảnh hưởng khả năng dùng thứ tự sẵn có của chỉ mục:

```sql
ORDER BY
    CASE WHEN published_at IS NULL THEN 1 ELSE 0 END,
    published_at DESC,
    product_id DESC
```

Thứ tự chuỗi cũng phụ thuộc collation: phân biệt hoa thường, dấu, quy tắc ngôn ngữ và cách so sánh ký tự. Nếu kết quả cần ổn định giữa các môi trường, hãy xác định collation và kiểu dữ liệu rõ ràng. Không giả định hai máy chủ có cấu hình collation khác nhau sẽ sắp xếp chuỗi giống nhau.

## 3. Top-N sort và full sort

Khi không có đường truy cập cung cấp sẵn thứ tự phù hợp, hệ quản trị có thể phải sắp xếp các hàng thỏa điều kiện trước khi lấy N hàng đầu. Có hai ý tưởng thường gặp:

- **Full sort:** sắp xếp toàn bộ tập ứng viên theo các khóa `ORDER BY`, sau đó trả về N hàng đầu.
- **Top-N sort:** duy trì tập N ứng viên tốt nhất trong quá trình đọc dữ liệu, loại dần những hàng không thể lọt vào top-N.

Nếu có M hàng ứng viên và cần N hàng với N nhỏ hơn nhiều M, thuật toán top-N dùng heap hoặc cấu trúc tương tự có thể giảm bộ nhớ từ mức tỷ lệ với M xuống mức tỷ lệ với N, và có thể giảm công việc sắp xếp từ khoảng (O(M \log M)) xuống (O(M \log N)). Đây là mô hình thuật toán khái quát; cách triển khai, chi phí so sánh, xử lý song song và lựa chọn kế hoạch phụ thuộc hệ quản trị.

Điểm cần nhớ: top-N sort vẫn có thể phải đọc và đánh giá tất cả M hàng ứng viên để biết hàng nào thuộc top-N. Nó giảm chi phí sắp xếp/lưu giữ ứng viên, nhưng không nhất thiết giảm số hàng cần quét. Nếu một chỉ mục có thể cung cấp đúng thứ tự và điều kiện lọc, hệ quản trị đôi khi có thể đọc tuần tự từ đầu chỉ mục và dừng sau khi tìm đủ N hàng phù hợp.

### 3.1. So sánh hai hướng xử lý

| Cách xử lý | Công việc chính | Khi thường có lợi |
|---|---|---|
| Full sort rồi lấy N | Đọc tập ứng viên, sắp xếp toàn bộ, lấy N hàng | Tập ứng viên nhỏ hoặc cần phần lớn kết quả |
| Top-N sort | Đọc tập ứng viên, duy trì N ứng viên tốt nhất | N nhỏ so với số hàng ứng viên, không có thứ tự phù hợp sẵn |
| Đọc theo thứ tự chỉ mục | Tìm điểm bắt đầu, duyệt chỉ mục theo thứ tự và dừng khi đủ N hàng | Chỉ mục phù hợp với predicate và toàn bộ thứ tự yêu cầu |

Không nên kết luận top-N sort luôn nhanh hơn full sort. Khi N gần bằng M, lợi ích có thể nhỏ. Khi sort phải spill ra đĩa hoặc dữ liệu đầu vào rất lớn, cần xem memory grant, I/O và lượng hàng đọc. Khi chỉ mục cung cấp thứ tự nhưng điều kiện lọc loại phần lớn hàng, việc duyệt index vẫn có thể tốn kém.

### 3.2. Vì sao LIMIT nhỏ vẫn có thể chậm?

Xét truy vấn:

```sql
SELECT event_id, score
FROM events
WHERE event_type = 'ALERT'
ORDER BY score DESC
LIMIT 5;
```

Nếu không có chỉ mục hữu ích, hệ quản trị có thể phải quét nhiều hoặc toàn bộ bảng để tìm các hàng `ALERT`, sau đó xác định 5 điểm cao nhất. Dù kết quả chỉ có 5 hàng, truy vấn vẫn phải đánh giá tập ứng viên rộng.

Nếu có chỉ mục phù hợp với điều kiện và thứ tự, hệ quản trị có thể giảm lượng đọc. Tuy nhiên, một chỉ mục chỉ trên `score` có thể phải duyệt nhiều hàng không thuộc `ALERT`; chỉ mục ghép hoặc partial/filtered index có thể phù hợp hơn tùy phân bố và khả năng của hệ quản trị.

## 4. Thiết kế chỉ mục để phục vụ top-N

Một chỉ mục có thể loại bỏ sort nếu thứ tự khóa của nó tương thích với điều kiện lọc và `ORDER BY`. Hãy xem xét cả thứ tự cột, hướng tăng/giảm, predicate, giá trị `NULL` và cột cần trả về.

Ví dụ truy vấn:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = :customer_id
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Một chỉ mục ghép đáng thử:

```sql
CREATE INDEX idx_orders_customer_recent
ON orders (customer_id, created_at DESC, order_id DESC);
```

Vì `customer_id` được lọc bằng equality, hệ quản trị có thể định vị nhóm của khách hàng rồi đọc theo thứ tự thời gian và mã đơn hàng. Nếu chỉ mục bao phủ các cột cần trả về, có thể giảm lookup bổ sung, nhưng thêm `total_amount` vào chỉ mục làm tăng kích thước và chi phí ghi. Cú pháp chỉ mục và cách xử lý hướng quét phụ thuộc hệ quản trị.

### 4.1. Equality trước, thứ tự sau

Với mẫu truy vấn lọc equality trên một cột rồi sắp xếp theo cột khác, chỉ mục ghép thường được thử theo dạng:

```text
(cột_equality, cột_sắp_xếp, khóa_phân_xử)
```

Ví dụ `(customer_id, created_at, order_id)`. Cột equality ở tiền tố giới hạn vùng khóa; các cột tiếp theo cung cấp thứ tự trong vùng đó. Đây là hướng thiết kế ban đầu, không phải quy tắc tuyệt đối. Nếu có nhiều điều kiện, range predicate, nhiều nhóm truy vấn hoặc độ chọn lọc khác nhau, cần kiểm tra kế hoạch và đo thực tế.

### 4.2. Hướng sắp xếp của chỉ mục

Một số hệ quản trị có thể quét chỉ mục theo chiều ngược để đáp ứng `ASC` hoặc `DESC`. Với nhiều cột có hướng trộn lẫn, ví dụ `ORDER BY priority DESC, created_at ASC`, định nghĩa hướng cột trong index có thể quan trọng. Hãy xác nhận khả năng của hệ quản trị và execution plan thay vì giả định chỉ mục tăng dần luôn đáp ứng mọi thứ tự nhiều cột.

### 4.3. Partial/filtered index cho top-N có điều kiện cố định

Nếu truy vấn luôn lấy một tập con nhỏ, partial hoặc filtered index có thể giảm kích thước cấu trúc và cho phép đọc đúng vùng cần thiết. Ví dụ PostgreSQL:

```sql
CREATE INDEX idx_open_orders_recent
ON orders (created_at DESC, order_id DESC)
WHERE status = 'OPEN';
```

Truy vấn tương ứng:

```sql
SELECT order_id, created_at
FROM orders
WHERE status = 'OPEN'
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

Bộ tối ưu chỉ có thể dùng index nếu chứng minh được predicate truy vấn tương thích với điều kiện của index. Khả năng filtered/partial index và cách chứng minh predicate khác nhau giữa hệ quản trị. Chỉ mục nhỏ hơn có thể giảm đọc nhưng vẫn cần đo chi phí cập nhật khi hàng chuyển trạng thái vào hoặc ra khỏi tập được lập chỉ mục.

## 5. LIMIT, TOP và FETCH FIRST theo hệ quản trị

Các hệ quản trị có cú pháp giới hạn hàng khác nhau. Ví dụ tương đương về ý tưởng:

**PostgreSQL/MySQL:**

```sql
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
LIMIT 10;
```

**SQL Server:**

```sql
SELECT TOP (10) order_id, created_at
FROM dbo.Orders
ORDER BY created_at DESC, order_id DESC;
```

Hoặc phân trang theo cú pháp:

```sql
SELECT order_id, created_at
FROM dbo.Orders
ORDER BY created_at DESC, order_id DESC
OFFSET 0 ROWS FETCH NEXT 10 ROWS ONLY;
```

**Oracle và các hệ quản trị hỗ trợ chuẩn FETCH FIRST:**

```sql
SELECT order_id, created_at
FROM orders
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 10 ROWS ONLY;
```

Luôn đặt `ORDER BY` trong truy vấn xác định top-N. Một số cú pháp cho phép `TOP` hoặc `FETCH` mà không có `ORDER BY`, nhưng khi đó không có cam kết về việc hàng nào được chọn.

### 5.1. WITH TIES khi muốn giữ tất cả hàng đồng hạng

Một số hệ quản trị hỗ trợ `WITH TIES` để trả thêm các hàng có giá trị sắp xếp bằng hàng cuối cùng trong top-N. Ví dụ SQL Server:

```sql
SELECT TOP (10) WITH TIES
       product_id, rating
FROM products
ORDER BY rating DESC;
```

Nếu nhiều sản phẩm cùng điểm với sản phẩm ở vị trí thứ 10, tất cả hàng đồng điểm đó có thể được trả về, nên số hàng thực tế có thể lớn hơn 10.

Nếu thêm khóa duy nhất vào `ORDER BY`:

```sql
ORDER BY rating DESC, product_id DESC
```

thì mỗi hàng có thứ tự riêng và hầu như không còn nhóm ties theo điểm rating. Vì vậy, hãy tách tiêu chí đồng hạng khỏi khóa phụ dùng để phân trang ổn định. `WITH TIES` và cú pháp tương đương khác nhau giữa hệ quản trị; cần xác nhận hỗ trợ trên phiên bản đang dùng.

## 6. OFFSET pagination và chi phí khi trang càng sâu

Phân trang bằng `OFFSET` và `LIMIT` dễ viết:

```sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = :customer_id
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 10000;
```

Truy vấn yêu cầu bỏ qua 10.000 hàng đầu theo thứ tự rồi trả 20 hàng tiếp theo. Để xác định vị trí, hệ quản trị thường vẫn phải đi qua hoặc xử lý các hàng bị bỏ qua. Vì vậy, chi phí có thể tăng theo độ sâu trang. Nếu không có chỉ mục hỗ trợ, hệ quản trị còn có thể phải quét và sắp xếp tập ứng viên lớn trước khi bỏ qua hàng.

OFFSET cũng dễ tạo trải nghiệm không nhất quán khi dữ liệu thay đổi giữa các lần yêu cầu trang. Nếu một hàng mới được thêm vào đầu danh sách sau khi trang đầu đã đọc, các vị trí có thể dịch chuyển; người dùng có thể thấy hàng lặp lại hoặc bỏ sót giữa các trang.

OFFSET phù hợp khi:

- Tập dữ liệu nhỏ hoặc số trang không sâu.
- Người dùng cần nhảy đến một số trang bất kỳ.
- Mức thay đổi dữ liệu giữa các lần đọc thấp hoặc ứng dụng chấp nhận sai khác.
- Đã đo và xác nhận chi phí ở độ sâu trang dự kiến.

## 7. Keyset pagination (seek method)

Keyset pagination dùng giá trị khóa cuối cùng của trang trước làm điểm bắt đầu cho trang tiếp theo. Thay vì bỏ qua N hàng, truy vấn tìm các hàng đứng sau khóa cursor theo thứ tự đã xác định.

Giả sử thứ tự là `created_at DESC, order_id DESC`, cả hai cột không `NULL` và `order_id` là duy nhất. Trang đầu:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = :customer_id
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Giả sử hàng cuối trang có `created_at = :last_created_at` và `order_id = :last_order_id`. Trang tiếp theo:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = :customer_id
  AND (
       created_at < :last_created_at
       OR (created_at = :last_created_at AND order_id < :last_order_id)
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
```

Điều kiện so sánh đi theo thứ tự từ điển của cặp khóa. Với hướng giảm dần, trang tiếp theo có khóa nhỏ hơn cursor; với hướng tăng dần, thường dùng điều kiện lớn hơn. Nếu hệ quản trị hỗ trợ so sánh hàng (row-value comparison), có thể có cú pháp ngắn hơn, nhưng khả năng và cách tối ưu khác nhau.

### 7.1. Chỉ mục cho keyset pagination

Với truy vấn trên, chỉ mục `(customer_id, created_at DESC, order_id DESC)` có thể hỗ trợ định vị nhóm khách hàng và seek từ cursor, sau đó đọc 20 hàng tiếp theo. Độ trễ thường ít phụ thuộc vào số trang đã đi qua hơn OFFSET, miễn là kế hoạch dùng được index và điều kiện không yêu cầu xử lý quá nhiều hàng.

Keyset pagination phù hợp với danh sách lớn, cuộn liên tục và dữ liệu thường xuyên được thêm mới. Nó không hỗ trợ nhảy trực tiếp đến trang 5000 nếu không có cursor hoặc cơ chế định vị riêng. Cursor nên chứa toàn bộ khóa sắp xếp cần thiết, được mã hóa/kiểm tra ở tầng ứng dụng nếu được truyền qua API.

### 7.2. NULL trong cursor

Nếu cột sắp xếp cho phép `NULL`, phép so sánh `<`, `>` hoặc `=` với cursor có thể trả về `UNKNOWN`. Khi đó điều kiện keyset đơn giản không còn bao phủ đầy đủ thứ tự. Cần xác định thứ tự `NULLS FIRST/LAST` và viết predicate tương ứng với quy tắc đó, hoặc dùng một khóa sắp xếp đã chuẩn hóa/không nullable.

Không nên tự ý dùng `COALESCE` với một giá trị giả làm cursor nếu giá trị đó có thể xuất hiện trong dữ liệu thật hoặc làm thay đổi thứ tự. Cần bảo đảm biểu thức sắp xếp và predicate cursor mô tả cùng một thứ tự.

### 7.3. Tính nhất quán khi dữ liệu thay đổi

Keyset pagination giảm hiện tượng dịch vị trí do hàng mới chèn trước cursor, nhưng không tự tạo snapshot nhất quán cho toàn bộ phiên duyệt. Nếu một hàng được cập nhật khóa sắp xếp và chuyển từ phía sau cursor lên phía trước hoặc ngược lại, người dùng vẫn có thể thấy khác biệt giữa các trang.

Nếu nghiệp vụ yêu cầu duyệt một tập dữ liệu bất biến, cần cân nhắc transaction snapshot phù hợp, mốc thời gian/sequence giới hạn tập dữ liệu hoặc cursor gắn với snapshot logic. Cách triển khai phụ thuộc isolation level, thời gian giữ transaction và yêu cầu vận hành; giữ snapshot quá lâu có thể tạo áp lực tài nguyên.

## 8. Top-N theo từng nhóm

Một yêu cầu thường gặp là lấy 3 sản phẩm có doanh thu cao nhất trong mỗi danh mục. `LIMIT 3` ở cuối truy vấn chỉ giới hạn toàn bộ kết quả, không giới hạn 3 hàng cho từng nhóm.

Có thể dùng hàm cửa sổ `ROW_NUMBER()`:

```sql
WITH ranked AS (
    SELECT
        category_id,
        product_id,
        revenue,
        ROW_NUMBER() OVER (
            PARTITION BY category_id
            ORDER BY revenue DESC, product_id DESC
        ) AS rn
    FROM product_sales
)
SELECT category_id, product_id, revenue
FROM ranked
WHERE rn <= 3
ORDER BY category_id, revenue DESC, product_id DESC;
```

`ROW_NUMBER()` gán số thứ tự riêng cho từng hàng trong mỗi nhóm. Khóa phụ `product_id` giúp kết quả chọn đúng 3 hàng ổn định khi doanh thu bằng nhau.

Nếu muốn giữ tất cả sản phẩm đồng hạng theo doanh thu ở ranh giới, dùng `RANK()` hoặc `DENSE_RANK()` tùy cách đánh số hạng:

```sql
WITH ranked AS (
    SELECT
        category_id,
        product_id,
        revenue,
        RANK() OVER (
            PARTITION BY category_id
            ORDER BY revenue DESC
        ) AS rnk
    FROM product_sales
)
SELECT category_id, product_id, revenue
FROM ranked
WHERE rnk <= 3
ORDER BY category_id, revenue DESC, product_id DESC;
```

Không thêm `product_id` vào `ORDER BY` bên trong `RANK()` nếu muốn các sản phẩm có cùng doanh thu đồng hạng; thêm khóa phụ vào biểu thức xếp hạng sẽ phá nhóm ties. Có thể dùng khóa phụ ở `ORDER BY` cuối cùng để hiển thị ổn định mà vẫn giữ thứ hạng đồng hạng.

### 8.1. Khác biệt giữa ROW_NUMBER, RANK và DENSE_RANK

| Hàm | Cách đánh số | Hành vi khi đồng hạng |
|---|---|---|
| `ROW_NUMBER()` | 1, 2, 3, 4... | Mỗi hàng có số riêng; cần khóa phụ để thứ tự xác định |
| `RANK()` | 1, 1, 3, 4... | Hàng đồng hạng cùng số; có khoảng trống sau nhóm ties |
| `DENSE_RANK()` | 1, 1, 2, 3... | Hàng đồng hạng cùng số; không có khoảng trống |

Điều kiện `rank <= 3` có thể trả nhiều hơn 3 hàng nếu có đồng hạng. Cần chọn hàm theo yêu cầu nghiệp vụ: đúng N hàng, N vị trí xếp hạng có ties hay N mức điểm phân biệt.

## 9. Sort trong execution plan và các dấu hiệu cần theo dõi

Khi phân tích top-N, hãy xem kế hoạch thực thi để biết hệ quản trị đang dùng thứ tự sẵn có hay phải sort. Tên toán tử khác nhau giữa các sản phẩm, nhưng các dấu hiệu thường gặp gồm:

- **Sort:** sắp xếp tập hàng theo các biểu thức `ORDER BY`.
- **Top-N Sort / Top:** tối ưu sắp xếp để giữ một số hàng đầu hoặc giới hạn số hàng.
- **Index Scan/Seek theo thứ tự:** đọc chỉ mục đã được sắp theo khóa tương thích.
- **Incremental/partial sort:** tận dụng một phần thứ tự có sẵn rồi sắp xếp phần còn lại, nếu hệ quản trị hỗ trợ.
- **Window/Rank:** tính số thứ tự hoặc hạng trong nhóm, thường cần thứ tự theo partition và order keys.

Các chỉ số nên quan sát:

| Nhóm | Chỉ số hoặc thông tin | Câu hỏi phân tích |
|---|---|---|
| Cardinality | Estimated rows, actual rows | Hệ quản trị có đánh giá đúng số ứng viên không? |
| Sort | Số hàng và byte đầu vào, khóa sort | Có đang sort nhiều dữ liệu hơn cần thiết không? |
| Bộ nhớ | Memory grant, memory used, sort memory | Bộ nhớ có đủ cho thao tác sort không? |
| Spill | Spill level, số lần/byte ghi tạm | Sort có tràn ra temp storage không? |
| I/O | Logical/physical reads, temp reads/writes | Chi phí đọc và ghi tạm là bao nhiêu? |
| Thời gian | CPU time, elapsed time, p95/p99 | Sort chiếm bao nhiêu trong tổng độ trễ? |
| Thông lượng | Rows/sec, requests/sec | Tối ưu top-N có cải thiện workload tổng thể không? |
| Ổn định | Kế hoạch theo tham số và mức tải | Một kế hoạch có phù hợp nhiều nhóm dữ liệu không? |

Không phải mọi hệ quản trị đều hiển thị cùng metric hoặc cùng cách tính thời gian tại toán tử. Cần đọc chú giải của công cụ, đặc biệt với truy vấn song song, nơi thời gian toán tử có thể chồng lấp và không cộng trực tiếp thành elapsed time.

### 9.1. Sort spill ra đĩa

Nếu tập cần sắp xếp lớn hơn bộ nhớ được cấp, hệ quản trị có thể ghi các run tạm ra đĩa rồi trộn chúng. Điều này làm tăng I/O và độ trễ. Một top-N sort có thể giảm bộ nhớ cần thiết, nhưng nếu đầu vào lớn hoặc N lớn, nó vẫn có thể cần nhiều tài nguyên.

Hướng điều tra gồm:

1. Xem số hàng thực tế đi vào sort và độ rộng mỗi hàng.
2. Kiểm tra có thể đẩy bộ lọc xuống sớm hơn để giảm ứng viên không.
3. Kiểm tra chỉ mục có thể cung cấp thứ tự và cho phép dừng sớm không.
4. Xem memory grant, spill và temp I/O.
5. Kiểm tra thống kê/cardinality vì ước lượng sai có thể làm cấp phát bộ nhớ không phù hợp.
6. Đo tác động của thay đổi trên nhiều truy vấn cùng chia sẻ bộ nhớ.

Không nên tăng bộ nhớ toàn hệ thống hoặc ép memory grant chỉ vì thấy một sort spill. Cần xác định workload, số phiên đồng thời và áp lực bộ nhớ tổng thể trước khi thay đổi cấu hình.

## 10. Quy trình tối ưu truy vấn top-N

Một quy trình thực hành có thể áp dụng như sau:

1. **Xác định ý nghĩa top-N.** N hàng chính xác hay giữ tất cả ties? Thứ tự nào có ý nghĩa nghiệp vụ? Có cho phép giá trị `NULL` không?
2. **Bổ sung thứ tự xác định.** Thêm khóa phụ duy nhất nếu cần chọn đúng từng hàng và phân trang ổn định.
3. **Xác định phạm vi lọc.** Ghi rõ predicate, nhóm tham số, độ chọn lọc và số hàng ứng viên.
4. **Thu thập baseline.** Đo p50/p95/p99, throughput, CPU, I/O, số hàng sort, memory grant và spill.
5. **Đọc execution plan.** Xác định sort toàn bộ, top-N sort, index order, filter, lookup và cardinality.
6. **Đánh giá chỉ mục.** Thiết kế index theo equality predicates, sort keys và khóa phân xử; xem xét partial/filtered hoặc covering index khi có lợi.
7. **Chọn chiến lược phân trang.** Dùng OFFSET khi trang nông hoặc cần nhảy trang; xem xét keyset khi danh sách lớn và duyệt tuần tự.
8. **Kiểm thử ties và dữ liệu biên.** Bao gồm giá trị trùng, `NULL`, nhóm rỗng, nhóm có ít hơn N hàng và cập nhật đồng thời.
9. **Đo lại trong cùng điều kiện.** Giữ dữ liệu, tham số, cache, tốc độ tải và thời lượng tương đương.
10. **Đánh giá chi phí phụ.** Đo ghi, dung lượng index, cache, lock, memory và workload khác.

Một thay đổi chỉ được xem là cải thiện khi kết quả vẫn đúng và mục tiêu hiệu năng được cải thiện trong workload đại diện. Giảm thời gian sort riêng lẻ không đủ nếu tổng độ trễ ứng dụng, throughput hoặc chi phí ghi xấu đi.

## 11. Ví dụ tổng hợp: danh sách đơn hàng mới nhất

Ứng dụng cần hiển thị 25 đơn hàng gần nhất của một khách hàng, cho phép cuộn liên tục và dữ liệu có thể được thêm trong khi người dùng đang duyệt.

Truy vấn ban đầu:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = :customer_id
ORDER BY created_at DESC
LIMIT 25 OFFSET :offset;
```

Các vấn đề cần xem xét:

- `created_at` có thể trùng nhau nên thứ tự chưa xác định hoàn toàn.
- OFFSET lớn phải bỏ qua nhiều hàng.
- Nếu không có chỉ mục phù hợp, hệ quản trị có thể phải sort nhiều đơn hàng của khách.
- Dữ liệu mới chèn có thể làm vị trí hàng thay đổi giữa các trang.

Thêm khóa phụ duy nhất:

```sql
ORDER BY created_at DESC, order_id DESC
```

Đề xuất thử chỉ mục:

```sql
CREATE INDEX idx_orders_customer_created_order
ON orders (customer_id, created_at DESC, order_id DESC);
```

Với keyset pagination, trang tiếp theo dùng cursor từ hàng cuối trang trước:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = :customer_id
  AND (
       created_at < :last_created_at
       OR (created_at = :last_created_at AND order_id < :last_order_id)
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 25;
```

Kế hoạch mong đợi là tìm vùng của khách hàng trong index, seek từ cursor rồi đọc tiếp 25 hàng theo thứ tự. Cần kiểm tra kế hoạch thực tế có dùng index và không còn sort lớn hay không. Sau đó đo p95/p99 ở trang đầu và các lần cuộn sâu, logical reads, CPU, throughput, thời gian ghi và kích thước index.

Nếu dữ liệu có `created_at IS NULL`, phải quyết định vị trí của những hàng đó và điều chỉnh cả thứ tự lẫn predicate cursor. Nếu ứng dụng cần giữ snapshot nhất quán trong suốt phiên duyệt, keyset đơn thuần chưa đủ; cần thêm cơ chế snapshot hoặc mốc giới hạn dữ liệu phù hợp.

## 12. Những sai lầm thường gặp

- **Dùng LIMIT mà không ORDER BY:** hàng được trả về không có thứ tự được bảo đảm.
- **ORDER BY không duy nhất:** hàng đồng hạng ở ranh giới top-N có thể thay đổi vị trí.
- **Cho rằng LIMIT nhỏ luôn nhanh:** hệ quản trị vẫn có thể phải quét toàn bộ tập ứng viên hoặc sort lớn.
- **Nhầm top-N sort với dừng đọc sớm:** top-N sort vẫn có thể phải xem mọi ứng viên.
- **Tạo chỉ mục chỉ theo cột sort:** bỏ qua predicate lọc và khóa phụ nên vẫn phải đọc nhiều hàng.
- **Không tính chi phí OFFSET:** trang sâu có thể phải đi qua hàng nghìn hoặc hàng triệu hàng bị bỏ qua.
- **Thêm khóa phụ vào RANK khi muốn giữ ties:** làm các hàng đồng điểm mất vị trí đồng hạng.
- **Bỏ qua NULL và collation:** thứ tự khác nhau có thể làm cursor và kết quả không nhất quán.
- **Chỉ đo truy vấn đơn lẻ:** bỏ qua tranh chấp bộ nhớ, I/O và chi phí duy trì chỉ mục khi tải đồng thời.
- **Không kiểm tra dữ liệu thay đổi:** phân trang có thể lặp hoặc bỏ sót hàng khi khóa sắp xếp thay đổi.

## 13. Bài tập tự kiểm tra

### Bài tập 1: Tạo thứ tự xác định

Một truy vấn lấy 10 giao dịch mới nhất bằng `ORDER BY created_at DESC LIMIT 10`. Nhiều giao dịch có cùng thời điểm.

**Yêu cầu:** sửa thứ tự để kết quả xác định.

**Gợi ý trả lời:** thêm khóa duy nhất, ví dụ `ORDER BY created_at DESC, transaction_id DESC`, với `transaction_id` được bảo đảm duy nhất. Nếu `created_at` nullable, quy định rõ vị trí `NULL`.

### Bài tập 2: Trang sâu bằng OFFSET

Một API dùng `LIMIT 50 OFFSET 500000` và thời gian phản hồi tăng theo số trang.

**Câu hỏi:** vì sao và có thể đổi sang cách nào?

**Gợi ý trả lời:** hệ quản trị thường phải đi qua hoặc xử lý các hàng bị bỏ qua trước khi trả trang. Nếu người dùng duyệt tuần tự, có thể dùng keyset pagination với cursor chứa đầy đủ khóa sắp xếp và chỉ mục phù hợp. Nếu cần nhảy trang tùy ý, phải cân nhắc yêu cầu đó và đo chi phí OFFSET.

### Bài tập 3: Top-N có ties

Bảng kết quả có 8 sản phẩm cùng điểm cao nhất. Yêu cầu là lấy 5 vị trí đầu nhưng giữ tất cả sản phẩm đồng điểm ở ranh giới.

**Câu hỏi:** dùng `ROW_NUMBER()` hay `RANK()`? Có nên thêm `product_id` vào biểu thức xếp hạng không?

**Gợi ý trả lời:** dùng `RANK()` nếu muốn giữ tất cả hàng đồng hạng theo điểm. Không thêm `product_id` vào `ORDER BY` bên trong `RANK()` vì sẽ phá nhóm đồng hạng; có thể thêm `product_id` ở thứ tự hiển thị cuối cùng.

### Bài tập 4: LIMIT nhỏ nhưng sort vẫn nặng

Truy vấn trả 10 hàng nhưng execution plan cho thấy top-N sort nhận 4 triệu hàng đầu vào.

**Câu hỏi:** cần kiểm tra gì trước khi tăng bộ nhớ?

**Gợi ý trả lời:** xem predicate có thể lọc sớm không, chỉ mục có thể cung cấp thứ tự không, số hàng ước lượng có đúng không, điều kiện có thể dùng partial/filtered index không và sort có spill không. Sau đó mới đánh giá memory grant cùng tải đồng thời.

### Checklist khi thiết kế top-N và phân trang

- [ ] Có `ORDER BY` thể hiện đúng yêu cầu nghiệp vụ.
- [ ] Thứ tự có khóa phụ duy nhất khi cần chọn từng hàng ổn định.
- [ ] Đã xác định cách xử lý ties, NULL và collation.
- [ ] Đã phân biệt top-N sort với khả năng dừng đọc sớm qua index.
- [ ] Chỉ mục phù hợp với predicate, sort keys và khóa phân xử.
- [ ] Đã đo số hàng đầu vào sort, memory grant, spill và I/O.
- [ ] Đã đánh giá chi phí OFFSET ở độ sâu trang thực tế.
- [ ] Đã cân nhắc keyset pagination cho luồng duyệt liên tục.
- [ ] Đã kiểm tra dữ liệu thay đổi giữa các trang và yêu cầu snapshot.
- [ ] Đã kiểm thử top-N theo nhóm bằng ROW_NUMBER/RANK/DENSE_RANK phù hợp.
- [ ] Đã so sánh độ trễ, throughput, chi phí ghi và tính đúng đắn trước/sau.

Top-N hiệu quả cần hai điều kiện: thứ tự kết quả phải được xác định đúng và hệ quản trị phải có đường xử lý phù hợp để tìm N hàng đầu. `ORDER BY` cùng khóa phân xử duy nhất bảo đảm kết quả ổn định; chỉ mục đúng thứ tự, top-N sort, keyset pagination và các hàm xếp hạng giải quyết những mẫu truy vấn khác nhau. Hãy xác nhận bằng execution plan và số liệu tải, đồng thời tính đến ties, NULL, cập nhật đồng thời và chi phí duy trì chỉ mục.
