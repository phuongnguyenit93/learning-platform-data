# Đọc kế hoạch để tối ưu một truy vấn lọc và sắp xếp

## Mục tiêu bài học

Một truy vấn có điều kiện lọc và `ORDER BY` thường xuất hiện trong API danh sách, trang quản trị, lịch sử giao dịch và báo cáo. Truy vấn có thể trả về vài chục dòng nhưng database phải quét hàng triệu dòng, đọc nhiều trang heap, tạo tập kết quả trung gian rồi sắp xếp mới lấy được các dòng đầu tiên. Muốn tối ưu đúng, cần đọc execution plan để biết database đang làm gì, xác định phần công việc tốn kém và chọn access path phù hợp với predicate, thứ tự sắp xếp và số dòng cần trả.

Trong chương **Thực hành tổng hợp** của module **DATABASE_PERFORMANCE**, bài học này hướng dẫn đọc kế hoạch để tối ưu một truy vấn lọc và sắp xếp. Module **DATABASE_PERFORMANCE** rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung hướng dẫn thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, bài thực hành kết hợp SQL, index, thống kê, execution plan và benchmark để chứng minh thay đổi cải thiện workload thực tế mà vẫn giữ nguyên kết quả nghiệp vụ.

Sau bài học, bạn có thể:

- Phân tích một truy vấn có `WHERE`, `ORDER BY` và `LIMIT`.
- Đọc các trường quan trọng trong `EXPLAIN` và `EXPLAIN ANALYZE`.
- Nhận diện scan thừa, sort tốn kém, ước lượng dòng sai và truy cập heap lặp lại.
- Thiết kế B-tree index ghép theo điều kiện lọc và thứ tự sắp xếp.
- Đánh giá selectivity, thứ tự cột, chiều sort, `INCLUDE` và partial index.
- Xác minh planner có sử dụng index và truy vấn có dừng sớm khi đạt `LIMIT` hay không.
- Đo tác động tới cả truy vấn đọc lẫn đường ghi trước khi chấp nhận index.

## 1. Bài toán thực hành

Giả sử một ứng dụng thương mại điện tử có bảng `orders`. API cần hiển thị 50 đơn hàng mới nhất của một khách hàng, chỉ lấy các đơn có trạng thái `PAID`:

```sql
SELECT
    order_id,
    created_at,
    total_amount
FROM orders
WHERE customer_id = 4201
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
```

Ứng dụng chỉ cần 50 dòng, nhưng bảng có hàng chục triệu đơn hàng. Nếu database quét toàn bảng, kiểm tra từng dòng, sau đó sắp xếp mọi dòng phù hợp, thời gian và I/O có thể lớn hơn nhiều so với lượng kết quả cuối cùng.

Mục tiêu tối ưu là giúp database:

1. Đi thẳng tới phạm vi dữ liệu của khách hàng và trạng thái cần tìm.
2. Đọc dữ liệu theo thứ tự mới nhất nếu access path hỗ trợ.
3. Dừng sớm khi tìm đủ 50 dòng hợp lệ.
4. Chỉ truy cập những cột cần thiết với chi phí hợp lý.
5. Không làm write workload và dung lượng index tăng quá mức lợi ích.

Đây là bài toán access path. SQL mô tả kết quả cần có; execution plan cho biết database chọn cách lấy kết quả đó.

## 2. Chuẩn bị dữ liệu và hiểu yêu cầu truy vấn

Trước khi đọc plan, phải hiểu chính xác truy vấn và phân bố dữ liệu. Nếu không biết khách hàng có bao nhiêu đơn, tỷ lệ trạng thái `PAID` là bao nhiêu hoặc dữ liệu được phân bố theo thời gian thế nào, rất dễ chọn index sai.

### 2.1. Ví dụ cấu trúc bảng

```sql
CREATE TABLE orders (
    order_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL,
    status text NOT NULL,
    created_at timestamptz NOT NULL,
    total_amount numeric(14, 2) NOT NULL,
    payment_reference text,
    updated_at timestamptz NOT NULL DEFAULT now()
);
```

Giả sử bảng có các đặc điểm:

- 40 triệu dòng.
- Có nhiều khách hàng nhỏ và một số khách hàng lớn có hàng trăm nghìn đơn.
- Trạng thái `PAID` chiếm khoảng 70%, các trạng thái khác chiếm phần còn lại.
- Dữ liệu được thêm liên tục; `created_at` thường tăng theo thời gian.
- API thường lấy 20–100 dòng mới nhất cho một khách hàng.
- Các thao tác ghi gồm INSERT đơn hàng và UPDATE trạng thái.

Các con số này chỉ là dữ liệu giả định cho bài thực hành. Khi áp dụng vào hệ thống thật, cần lấy số liệu thực tế và giữ nguyên phân bố quan trọng như skew theo khách hàng, tỷ lệ trạng thái và độ mới của dữ liệu.

### 2.2. Xác định semantics trước khi tối ưu

Truy vấn cần bảo đảm:

- Chỉ lấy đơn thuộc đúng `customer_id`.
- Chỉ lấy trạng thái `PAID`.
- Sắp xếp theo `created_at` giảm dần.
- Trả tối đa 50 dòng.
- Nếu nhiều đơn có cùng `created_at`, thứ tự giữa chúng hiện chưa được xác định.

Nếu API cần phân trang ổn định, nên bổ sung khóa duy nhất làm tie-breaker:

```sql
ORDER BY created_at DESC, order_id DESC
```

Điều này làm thứ tự xác định hơn giữa các dòng có cùng timestamp. Tuy nhiên, thay đổi thứ tự là thay đổi semantics quan sát được của API; cần thống nhất với yêu cầu sản phẩm trước khi áp dụng.

### 2.3. Tìm hiểu tần suất và tầm quan trọng

Thu thập số lần gọi, tổng thời gian và phân vị latency của query fingerprint. Một truy vấn 200 ms gọi 10.000 lần/phút có thể đáng ưu tiên hơn truy vấn 5 giây chỉ chạy một lần trong ngày.

Ngoài truy vấn mục tiêu, cần biết bảng có bao nhiêu INSERT/UPDATE/DELETE mỗi giây. Index mới sẽ làm các thao tác ghi duy trì thêm cấu trúc dữ liệu. Nếu bảng ghi rất nhiều, chi phí đó phải được đưa vào quyết định.

## 3. Đọc EXPLAIN và EXPLAIN ANALYZE

Trong PostgreSQL, bắt đầu bằng `EXPLAIN` để xem kế hoạch dự kiến:

```sql
EXPLAIN
SELECT
    order_id,
    created_at,
    total_amount
FROM orders
WHERE customer_id = 4201
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
```

`EXPLAIN` không thực thi câu truy vấn. Nó hiển thị kế hoạch mà planner dự định sử dụng dựa trên thống kê và cấu hình hiện tại.

Để đo thực thi thực tế:

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    order_id,
    created_at,
    total_amount
FROM orders
WHERE customer_id = 4201
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
```

`EXPLAIN ANALYZE` thực thi truy vấn và bổ sung số liệu thực tế. Trên production, chỉ chạy khi đã đánh giá tải và tác động. Với câu lệnh ghi hoặc câu lệnh có tác dụng phụ, cần môi trường thử nghiệm hoặc transaction có thể rollback và bảo đảm mọi tác dụng phụ nằm trong transaction.

### 3.1. Cấu trúc cây kế hoạch

Một kế hoạch thường gồm các node cha và node con. Node cha nhận dữ liệu từ node con rồi thực hiện công việc tiếp theo. Ví dụ:

```text
Limit
  -> Sort
       Sort Key: created_at DESC
       -> Seq Scan on orders
            Filter: (customer_id = 4201 AND status = 'PAID')
```

Đọc từ node lấy dữ liệu lên node xử lý phía trên:

1. `Seq Scan` đọc các trang của bảng và kiểm tra điều kiện.
2. `Sort` sắp xếp các dòng vượt qua filter.
3. `Limit` chỉ trả 50 dòng đầu sau khi sort.

Plan này có thể hợp lý với bảng nhỏ hoặc truy vấn trả tỷ lệ lớn dữ liệu. Với bảng hàng chục triệu dòng và kết quả chỉ 50 dòng, việc quét và sort nhiều dòng có thể là công việc thừa.

### 3.2. Startup cost và total cost

Một node thường hiển thị dạng:

```text
cost=12.50..84500.00 rows=120 width=32
```

- `startup cost`: chi phí ước lượng trước khi node có thể trả dòng đầu tiên.
- `total cost`: chi phí ước lượng để node hoàn tất toàn bộ đầu ra.
- `rows`: số dòng planner ước lượng node sẽ trả.
- `width`: kích thước trung bình ước lượng của mỗi dòng, tính theo byte.

Cost là đơn vị tương đối nội bộ của planner, không phải milliseconds. Dùng cost để so sánh lựa chọn trong cùng bối cảnh, không quy đổi trực tiếp thành thời gian thực tế.

Với `LIMIT`, startup cost có ý nghĩa vì ứng dụng cần dòng đầu tiên sớm. Một plan có total cost cao hơn nhưng startup cost thấp có thể phục vụ `LIMIT` tốt hơn nếu có thể dừng sớm.

### 3.3. Actual time, rows và loops

Với `ANALYZE`, node có thể hiển thị:

```text
actual time=0.020..18.400 rows=5000 loops=1
```

- `actual time`: thời gian thực tế từ lúc bắt đầu node tới lúc node hoàn thành; khi `loops` lớn hơn 1, thời gian và số dòng hiển thị là trung bình mỗi lần lặp.
- `rows`: số dòng thực tế node trả trong mỗi lần lặp.
- `loops`: số lần node được thực thi.

Nếu một node có `actual rows=20 loops=1000`, nó đã trả khoảng 20.000 dòng cộng dồn qua các lần gọi. Node chạy lặp nhiều lần có thể tạo chi phí lớn dù thời gian mỗi lần nhỏ.

So sánh `rows` ước lượng với `actual rows`. Sai lệch lớn có thể làm planner chọn scan hoặc join không phù hợp. Nếu sai lệch xuất hiện ở node lọc, kiểm tra statistics, skew và tương quan giữa các cột.

### 3.4. Buffers và I/O

Với `BUFFERS`, các trường thường gặp:

- `shared hit`: block được tìm thấy trong shared buffers của PostgreSQL.
- `shared read`: block phải được PostgreSQL đọc vào shared buffers.
- `shared dirtied` và `shared written`: block bị đánh dấu dirty hoặc được ghi trong phạm vi đo.
- `temp read` và `temp written`: block của file tạm được đọc/ghi.

`shared read` không đồng nghĩa chắc chắn phải đọc từ thiết bị vật lý; dữ liệu có thể còn trong OS page cache. Tuy vậy, số block read tăng cho biết PostgreSQL phải nạp thêm block vào shared buffers. Đối chiếu với metric storage để biết tác động I/O thực tế.

Nếu truy vấn quét hàng trăm nghìn block để trả 50 dòng, đó là dấu hiệu cần xem lại access path và điều kiện lọc.

### 3.5. Sort method và temp spill

Sort node có thể cho biết phương thức sắp xếp, memory sử dụng hoặc disk usage. Nếu sort không vừa bộ nhớ được cấp, PostgreSQL có thể ghi dữ liệu trung gian ra temp file.

Ví dụ output minh họa:

```text
Sort Method: external merge  Disk: 18432kB
```

`external merge` cho biết sort đã dùng file tạm trên đĩa. Đây có thể là nút thắt nếu tập dữ liệu đầu vào lớn. Tuy nhiên, tăng `work_mem` không phải lúc nào cũng là giải pháp: giá trị này có thể được dùng bởi nhiều operation trong một query và nhiều session đồng thời. Một index phù hợp có thể loại bỏ sort, nhưng chỉ khi lợi ích đọc lớn hơn chi phí duy trì index.

## 4. Đọc plan ban đầu và tìm phần công việc thừa

Giả sử plan ban đầu cho truy vấn mẫu có dạng rút gọn:

```text
Limit  (cost=... rows=50)
  -> Sort  (cost=... rows=42000)
       Sort Key: created_at DESC
       Sort Method: top-N heapsort
       -> Seq Scan on orders
            (cost=... rows=42000)
            Filter: ((customer_id = 4201) AND (status = 'PAID'))
            Rows Removed by Filter: 39958000
```

Đây là ví dụ minh họa, không phải output đo từ một database cụ thể.

Các dấu hiệu:

1. `Seq Scan` xem xét phần lớn bảng.
2. Hàng chục triệu dòng bị loại bởi filter.
3. Sort nhận khoảng 42.000 dòng dù cuối cùng chỉ trả 50.
4. `top-N heapsort` giảm chi phí so với sort toàn bộ kết quả, nhưng vẫn phải đọc đầu vào để xác định 50 dòng lớn nhất theo thứ tự.
5. `LIMIT` không giúp dừng sớm vì node phía dưới chưa cung cấp dữ liệu theo thứ tự mong muốn.

Đặt câu hỏi: có thể tổ chức index sao cho database tìm đúng customer/status và đọc theo `created_at DESC` ngay từ đầu không? Nếu có, engine có thể tránh scan rộng và sort riêng.

### 4.1. Sequential scan không phải lúc nào cũng xấu

Planner có thể chọn sequential scan hợp lý khi:

- Bảng nhỏ.
- Predicate chọn phần lớn dòng.
- Truy vấn cần nhiều cột.
- Random heap access qua index đắt hơn việc đọc tuần tự.
- Statistics cho thấy kết quả chiếm tỷ lệ lớn.

Không tạo index chỉ để loại bỏ mọi `Seq Scan`. Mục tiêu là giảm tổng chi phí workload, không phải ép plan có một node index scan.

### 4.2. Sort không phải lúc nào cũng cần loại bỏ

Sort có thể rẻ nếu số dòng đầu vào nhỏ, dữ liệu nằm trong memory hoặc sort phục vụ nhiều bước tiếp theo. Một index giúp bỏ sort nhưng làm tăng chi phí ghi và storage có thể không đáng nếu query hiếm.

Hãy so sánh thời gian và buffers trước/sau, đồng thời đo tần suất query. Tên node không tự quyết định kết luận.

## 5. Thiết kế B-tree index cho filter và sort

Với truy vấn:

```sql
WHERE customer_id = 4201
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50
```

một index ghép có thể phù hợp:

```sql
CREATE INDEX idx_orders_customer_status_created
ON orders (customer_id, status, created_at DESC);
```

B-tree lưu khóa theo thứ tự từ trái sang phải. Các cột equality đứng trước giúp thu hẹp phạm vi; cột thời gian tiếp theo cho phép duyệt các dòng trong phạm vi đó theo thứ tự mong muốn.

### 5.1. Equality trước, range/order tiếp theo

Trong nhiều truy vấn B-tree, thứ tự thiết kế hữu ích là:

1. Các cột được so sánh bằng (`=`) và thường xuất hiện cùng nhau.
2. Cột range hoặc cột phục vụ thứ tự sắp xếp.
3. Các cột bổ sung chỉ khi có lý do rõ ràng như index-only scan hoặc một query pattern khác.

Ví dụ:

```sql
WHERE tenant_id = 7
  AND status = 'OPEN'
  AND created_at >= :from_time
ORDER BY created_at DESC
LIMIT 100
```

Index có thể bắt đầu bằng `(tenant_id, status, created_at DESC)`. Hai cột equality xác định một vùng khóa; `created_at` xác định range và thứ tự trong vùng đó.

Đây là hướng dẫn thiết kế phổ biến, không phải quy tắc máy móc. Nếu truy vấn khác cần lọc chỉ theo `status`, index bắt đầu bằng `tenant_id` có thể không hỗ trợ tốt truy vấn đó. Phải xem toàn bộ workload và tính chọn lọc.

### 5.2. Tại sao thứ tự cột quan trọng?

Index `(customer_id, status, created_at)` có thể tìm hiệu quả khi predicate ràng buộc `customer_id` và `status`. Nếu chỉ có `status = 'PAID'`, engine không thể luôn thu hẹp một vùng liên tục hiệu quả như khi có cột leading key.

Index `(created_at, customer_id, status)` lại ưu tiên thứ tự thời gian toàn cục. Với truy vấn chỉ cần một khách hàng, engine có thể phải đọc nhiều timestamp rồi kiểm tra customer, trừ khi planner tìm được cách truy cập phù hợp khác.

Chọn thứ tự dựa trên prefix predicate phổ biến, selectivity và sort requirement. Đừng thêm mọi permutation vì mỗi index tăng chi phí ghi và bảo trì.

### 5.3. ASC, DESC và backward scan

B-tree có thể được duyệt xuôi hoặc ngược. Với một cột, index mặc định ASC thường có thể phục vụ `ORDER BY created_at DESC` bằng backward scan.

Khi có nhiều cột sort với hướng khác nhau, thứ tự và direction của index quan trọng hơn. Ví dụ `ORDER BY priority ASC, created_at DESC` có thể cần index khai báo direction tương ứng nếu muốn tránh sort.

`NULLS FIRST` và `NULLS LAST` cũng ảnh hưởng thứ tự. Trong ví dụ `created_at NOT NULL`, vấn đề NULL không phát sinh; với cột nullable, cần so sánh order requirement với cách index lưu NULL.

### 5.4. Index có thể cho phép dừng sớm với LIMIT

Khi index chứa các cột lọc và thứ tự, database có thể:

1. Tìm vị trí đầu của vùng `(customer_id, status)`.
2. Duyệt theo `created_at DESC`.
3. Kiểm tra tuple và trả dòng hợp lệ.
4. Dừng sau khi tìm đủ 50 dòng.

Điều này khác với plan phải scan toàn bộ vùng phù hợp rồi sort mới biết 50 dòng mới nhất. Khả năng dừng sớm là một lợi ích lớn của index hỗ trợ `ORDER BY ... LIMIT`.

Nếu có predicate bổ sung không nằm trong index, engine có thể phải đọc nhiều heap tuple bị loại trước khi tìm đủ 50 dòng. Khi đó cần kiểm tra actual rows, heap fetches và số block đọc.

## 6. INCLUDE và index-only scan

Truy vấn trả về `order_id`, `created_at`, `total_amount`. Index ghép hiện tại có `customer_id`, `status`, `created_at`, nhưng chưa chứa `order_id` và `total_amount` như các giá trị có thể lấy trực tiếp cho kết quả.

PostgreSQL hỗ trợ `INCLUDE` để thêm cột payload vào leaf page mà không làm chúng trở thành khóa sắp xếp:

```sql
CREATE INDEX idx_orders_customer_status_created_cover
ON orders (customer_id, status, created_at DESC)
INCLUDE (order_id, total_amount);
```

Index này có thể hỗ trợ index-only scan cho truy vấn mẫu vì các cột cần trả đã có trong index. Nhưng index-only scan còn phụ thuộc visibility map: PostgreSQL cần biết trang heap tương ứng all-visible để tránh truy cập heap xác minh tuple.

### 6.1. Lợi ích và chi phí của covering index

Lợi ích:

- Có thể tránh một số heap fetch.
- Giảm random access tới heap khi visibility map thuận lợi.
- Có thể cải thiện query đọc lặp lại.

Chi phí:

- Index lớn hơn, chiếm storage và cache.
- INSERT/UPDATE phải duy trì payload index.
- Cột rộng làm leaf page chứa ít entry hơn.
- UPDATE cột INCLUDE có thể yêu cầu cập nhật index và làm giảm cơ hội HOT update.
- Visibility map không phải lúc nào cũng cho phép bỏ qua heap, đặc biệt với bảng cập nhật liên tục.

Không thêm tất cả cột vào `INCLUDE`. Chỉ thêm những cột có lợi ích đo được và có kích thước phù hợp.

### 6.2. Cách xác nhận index-only scan

Sau khi tạo index, chạy lại:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    order_id,
    created_at,
    total_amount
FROM orders
WHERE customer_id = 4201
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
```

Tìm node `Index Only Scan` và trường `Heap Fetches`. `Heap Fetches` càng thấp càng có khả năng lấy kết quả từ index mà không phải xác minh heap. Kết quả phụ thuộc trạng thái vacuum, cập nhật và visibility map.

## 7. Partial index cho điều kiện ổn định

Nếu truy vấn thường chỉ lấy đơn `PAID`, có thể cân nhắc partial index:

```sql
CREATE INDEX idx_orders_paid_customer_created
ON orders (customer_id, created_at DESC)
INCLUDE (order_id, total_amount)
WHERE status = 'PAID';
```

Index chỉ chứa các dòng thỏa predicate `status = 'PAID'`, nên có thể nhỏ hơn index chứa mọi trạng thái. Nó cũng tránh phải lưu khóa `status` cho từng entry trong index.

### 7.1. Điều kiện để partial index được dùng

Planner phải chứng minh predicate của truy vấn hàm ý điều kiện partial index. Truy vấn viết `status = 'PAID'` thường khớp trực tiếp. Với prepared statement có parameter `status = $1`, khả năng sử dụng phụ thuộc plan custom/generic và khả năng chứng minh predicate tại thời điểm lập kế hoạch.

Không giả định partial index sẽ phục vụ mọi query có thể nhận status bất kỳ. Hãy test với cách ứng dụng bind parameter thực tế.

### 7.2. Khi partial index không phù hợp

- Trạng thái được truy vấn thay đổi thường xuyên và nhiều query cần các trạng thái khác nhau.
- Predicate không được planner chứng minh tương đương.
- Tỷ lệ dòng `PAID` quá lớn nên index không nhỏ hơn đáng kể.
- Việc cập nhật status thường xuyên làm dòng phải thêm/xóa khỏi partial index, tăng write cost.

So sánh index ghép đầy đủ và partial index bằng dữ liệu thật, gồm kích thước, read latency, write throughput và WAL.

## 8. Statistics và selectivity

Planner dựa vào statistics để ước lượng số dòng thỏa predicate. Nếu ước lượng sai, nó có thể chọn sequential scan, index scan hoặc bitmap scan không phù hợp.

### 8.1. Cập nhật statistics

```sql
ANALYZE orders;
```

`ANALYZE` lấy mẫu dữ liệu để cập nhật thống kê. Sau bulk load, thay đổi phân bố dữ liệu lớn hoặc tạo index không tự động bảo đảm mọi thống kê đã phản ánh workload mới. Theo dõi `last_analyze`, `last_autoanalyze` và thời điểm reset thống kê.

### 8.2. Selectivity

Selectivity là tỷ lệ dòng thỏa một điều kiện. Predicate chọn 0,01% dòng thường có tính chọn lọc cao; predicate chọn 90% dòng có tính chọn lọc thấp.

Index có lợi khi nó giúp tránh đọc phần lớn bảng. Nhưng với predicate trả về phần lớn dòng, sequential scan có thể rẻ hơn vì đọc tuần tự và tránh nhiều lần truy cập heap ngẫu nhiên.

### 8.3. Tương quan giữa các cột

Planner có thể giả định hai điều kiện độc lập nếu không có thống kê tương quan phù hợp. Trong thực tế, `customer_id` và `status` có thể tương quan: một số khách hàng chỉ có một số trạng thái nhất định hoặc một tenant có tỷ lệ trạng thái rất khác.

PostgreSQL hỗ trợ extended statistics:

```sql
CREATE STATISTICS st_orders_customer_status
(dependencies, mcv)
ON customer_id, status
FROM orders;

ANALYZE orders;
```

Các loại thống kê như `dependencies`, `mcv` hoặc `ndistinct` phù hợp với những kiểu tương quan khác nhau. Không tạo extended statistics cho mọi tổ hợp cột; xác định trước sai lệch estimate và query pattern cần cải thiện.

### 8.4. Dữ liệu skew và parameter sensitivity

Nếu khách hàng A có 20 đơn nhưng khách hàng B có 2 triệu đơn, cùng một query fingerprint có thể cần plan khác nhau theo parameter. Prepared statement có thể sử dụng custom hoặc generic plan tùy driver, server và chi phí ước lượng.

Kiểm tra cả tham số phổ biến, hiếm, nhỏ và lớn. Nếu plan chỉ tốt với một giá trị, điều tra parameter sensitivity trước khi kết luận index không phù hợp.

## 9. Các access path có thể xuất hiện

### 9.1. Seq Scan

Đọc tuần tự heap và đánh giá filter. Có thể phù hợp với bảng nhỏ, predicate ít chọn lọc hoặc truy vấn cần nhiều dòng.

### 9.2. Index Scan

Duyệt index để tìm tuple phù hợp, sau đó truy cập heap để lấy hoặc xác minh dữ liệu. Hiệu quả khi index thu hẹp được phạm vi và heap access không quá phân tán.

### 9.3. Index Only Scan

Lấy các cột cần thiết từ index nếu index bao phủ và visibility map cho phép. Theo dõi `Heap Fetches` để biết mức độ thực sự tránh heap access.

### 9.4. Bitmap Index Scan và Bitmap Heap Scan

PostgreSQL có thể dùng một hoặc nhiều index để tạo bitmap vị trí tuple, sau đó truy cập heap theo thứ tự trang. Cách này có thể hiệu quả khi predicate chọn nhiều dòng hơn index scan thuần nhưng vẫn không cần quét toàn bảng.

Bitmap heap scan có thể không giữ được thứ tự `ORDER BY` của index; nếu có sort node phía trên, cần tính chi phí sort. Với `LIMIT` nhỏ, một index duy trì đúng thứ tự có thể tốt hơn nếu cho phép dừng sớm.

### 9.5. Sort node

Sort sắp xếp các dòng đầu vào. Với tập nhỏ, sort trong memory có thể rẻ. Với tập lớn, có thể spill ra disk. `top-N heapsort` tối ưu việc giữ N dòng tốt nhất nhưng vẫn phải đọc đầu vào để biết dòng nào nằm trong top N.

Mục tiêu không phải loại bỏ mọi sort, mà là tránh sort một tập dữ liệu lớn khi index có thể cung cấp thứ tự cần thiết với chi phí tổng thể thấp hơn.

## 10. Quy trình tối ưu truy vấn mẫu

Thực hiện từng bước để có thể quy kết kết quả cho đúng thay đổi.

### Bước 1 — Lưu truy vấn và kết quả hiện tại

Ghi SQL, parameter set, số dòng kết quả và yêu cầu thứ tự. Xác nhận query fingerprint và tần suất gọi. Lưu kết quả logic hoặc aggregate đối chứng để kiểm tra tính tương đương sau thay đổi.

### Bước 2 — Thu thập baseline

Chạy workload đại diện, đo p50/p95/p99, throughput, buffers, temp spill, CPU và I/O. Lưu execution plan với `ANALYZE` trong môi trường an toàn.

### Bước 3 — Đọc node gây nhiều công việc

Tìm scan rộng, số dòng bị filter, sort đầu vào lớn, actual rows sai lệch, loops cao và heap fetches. Không chỉ nhìn node có cost lớn nhất; xem số lần chạy và tổng tác động.

### Bước 4 — Đề xuất access path

Với predicate equality trên `customer_id` và `status`, sau đó sort theo `created_at DESC`, thử index ghép:

```sql
CREATE INDEX idx_orders_customer_status_created
ON orders (customer_id, status, created_at DESC);
```

Chỉ thử partial hoặc covering index khi có bằng chứng rằng chúng giảm đáng kể kích thước hoặc heap access.

### Bước 5 — Cập nhật statistics khi cần

Chạy `ANALYZE` trong môi trường thử nghiệm hoặc theo quy trình production. Nếu estimate sai do tương quan cột, cân nhắc extended statistics và kiểm tra lại actual rows.

### Bước 6 — Chạy lại plan

```sql
EXPLAIN (ANALYZE, BUFFERS, VERBOSE)
SELECT
    order_id,
    created_at,
    total_amount
FROM orders
WHERE customer_id = 4201
  AND status = 'PAID'
ORDER BY created_at DESC
LIMIT 50;
```

Xác nhận plan mới có access path phù hợp, ít block hơn, sort được loại bỏ hoặc thu hẹp, và `LIMIT` có thể dừng sớm. Kiểm tra nhiều parameter set để tránh tối ưu chỉ cho một khách hàng.

### Bước 7 — Đo write overhead

Chạy INSERT/UPDATE/DELETE với tải đại diện. Đo throughput, commit latency, WAL bytes, index size, CPU/I/O và HOT update ratio nếu liên quan. Index đọc nhanh nhưng làm write path vượt SLA có thể không phải lựa chọn tốt.

### Bước 8 — Kiểm tra mixed workload

Chạy truy vấn danh sách đồng thời với ingestion và cập nhật trạng thái. Đo p95/p99 của cả đọc lẫn ghi, pool wait, CPU, I/O và lock. Xác nhận lợi ích không chỉ xuất hiện khi database rảnh.

### Bước 9 — Triển khai có kiểm soát

Tạo index trong cửa sổ phù hợp hoặc dùng `CREATE INDEX CONCURRENTLY` khi cần giảm mức chặn DML và phiên bản hỗ trợ. Theo dõi I/O, WAL, replication lag và dung lượng trong lúc build. Có phương án rollback và kiểm tra index hợp lệ trước khi chuyển traffic.

### Bước 10 — Ghi lại quyết định

Lưu plan trước/sau, metric, parameter set, index size, write impact, phạm vi thử nghiệm và điều kiện rollback. Không chỉ ghi “query nhanh hơn”; phải nêu mức cải thiện và chi phí đi kèm.

## 11. Ví dụ plan trước và sau

### 11.1. Trước khi có index phù hợp

Plan giả định:

```text
Limit
  -> Sort
       Sort Key: created_at DESC
       Sort Method: top-N heapsort
       -> Seq Scan on orders
            Filter: (customer_id = 4201 AND status = 'PAID')
            Rows Removed by Filter: 39958000
```

Giải thích:

- Database đọc phần lớn bảng.
- Filter giữ lại một tập con.
- Sort phải xét mọi dòng phù hợp trước khi biết 50 dòng mới nhất.
- `LIMIT` chỉ giảm số dòng trả ra, chưa giảm đáng kể lượng dữ liệu phải đọc.

### 11.2. Sau khi tạo index ghép

Plan có thể chuyển thành dạng:

```text
Limit
  -> Index Scan using idx_orders_customer_status_created on orders
       Index Cond: (customer_id = 4201 AND status = 'PAID')
```

Đây là dạng minh họa. Nếu index bao phủ các cột và visibility map thuận lợi, plan có thể dùng `Index Only Scan`. Nếu có điều kiện bổ sung không nằm trong index, có thể còn `Filter` và phải đọc thêm tuple.

Lợi ích kỳ vọng:

- Chỉ duyệt vùng khóa của khách hàng và trạng thái.
- Các entry đã có thứ tự thời gian giảm dần.
- Có thể dừng khi đủ 50 dòng.
- Không cần sort tập kết quả lớn nếu plan giữ được thứ tự.

Không kết luận thành công chỉ vì node đổi từ `Seq Scan` sang `Index Scan`. So sánh actual time, buffers, rows, heap fetches và tải ghi.

### 11.3. Trường hợp index vẫn không được dùng

Planner có thể tiếp tục chọn sequential scan nếu:

- Bảng nhỏ hoặc phần lớn dòng thỏa điều kiện.
- Statistics cũ hoặc estimate cho rằng index không có lợi.
- Parameter set trả về nhiều dòng.
- Predicate không khớp expression/partial index.
- Kiểu dữ liệu hoặc cast làm điều kiện không dùng được index như dự kiến.
- Cost model phản ánh random access đắt hơn scan tuần tự.

Không ép planner bằng cách tắt `enable_seqscan` trong production. Có thể dùng thay đổi planner setting trong môi trường chẩn đoán để hiểu một giả thuyết, nhưng quyết định cuối cùng phải dựa trên plan tự nhiên và workload thật.

## 12. Các lỗi thiết kế index thường gặp

### 12.1. Đặt cột sort trước các cột equality mà không xét query

Index `(created_at, customer_id, status)` có thể đọc theo thời gian nhưng không nhất thiết thu hẹp nhanh phạm vi của một khách hàng. Với query equality trên hai cột trước và sort theo thời gian, `(customer_id, status, created_at)` thường là điểm bắt đầu tốt hơn.

### 12.2. Index thiếu cột filter

Nếu index chỉ có `(customer_id, created_at)` nhưng `status` là filter chọn lọc, engine có thể phải đọc nhiều entry của khách hàng rồi loại các dòng không phải `PAID`. Thêm `status` vào key hoặc dùng partial index có thể giảm lượng đọc, tùy workload.

### 12.3. INCLUDE quá nhiều cột

Covering index có thể giảm heap fetch nhưng tăng kích thước, write amplification và cache pressure. Không đưa payload lớn hoặc cột ít cần thiết vào index chỉ để đạt `Index Only Scan`.

### 12.4. Bỏ qua NULL, collation và direction

Sort order của truy vấn cần khớp với thứ tự index. Với cột nullable, `NULLS FIRST/LAST`; với text, collation; với nhiều cột, ASC/DESC đều có thể ảnh hưởng khả năng bỏ sort.

### 12.5. Tạo index trùng lặp

Index `(customer_id, status, created_at)` và `(customer_id, status)` có thể trùng một phần chức năng, nhưng không thể quyết định bỏ index chỉ dựa trên prefix. Kiểm tra constraint, workload, size, scan count và write impact trước khi xóa.

## 13. Pagination và thứ tự ổn định

Truy vấn dùng `LIMIT` thường được gọi nhiều lần để phân trang. Với trang sâu, `OFFSET` có thể buộc database đọc và bỏ qua nhiều dòng trước khi trả trang tiếp theo:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 4201
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 50 OFFSET 50000;
```

Keyset pagination dùng giá trị của dòng cuối trang trước làm mốc:

```sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 4201
  AND status = 'PAID'
  AND (created_at, order_id) <
      (TIMESTAMPTZ '2026-10-15 10:30:00+00', 9000123)
ORDER BY created_at DESC, order_id DESC
LIMIT 50;
```

Index tương ứng có thể là:

```sql
CREATE INDEX idx_orders_customer_status_created_id
ON orders (customer_id, status, created_at DESC, order_id DESC)
INCLUDE (total_amount);
```

Keyset pagination giúp truy vấn trang tiếp theo bắt đầu từ khóa cuối thay vì bỏ qua hàng chục nghìn dòng. Cần bảo đảm thứ tự có tính duy nhất, xử lý đúng NULL và dùng so sánh phù hợp với direction của từng cột. Nếu dữ liệu thay đổi trong lúc phân trang, semantics của snapshot và thứ tự kết quả cũng cần được xác định.

## 14. Kiểm chứng bằng benchmark

### 14.1. Điều kiện so sánh

Trước và sau cần giữ:

- Cùng snapshot hoặc dữ liệu có phân bố tương đương.
- Cùng SQL semantics và bộ tham số.
- Cùng concurrency và request mix.
- Cùng cache condition hoặc ghi rõ warm/cold run.
- Cùng cấu hình CPU, memory và storage.
- Đo nhiều lần và báo cáo phân vị.

### 14.2. Metric đọc

- p50/p95/p99 query và API latency.
- Calls, total time và rows theo fingerprint.
- Shared buffers hit/read và heap fetches.
- Sort method, temp read/write và memory.
- CPU time, I/O latency và throughput.

### 14.3. Metric ghi và vận hành

- INSERT/UPDATE/DELETE throughput.
- Commit latency và WAL generation.
- Index size và tốc độ tăng dung lượng.
- HOT update ratio và vacuum activity.
- Replication lag và archive throughput.
- Chi phí build index và thời gian bảo trì.

### 14.4. Ngưỡng chấp nhận

Đặt tiêu chí trước khi chạy. Ví dụ:

- Query p95 giảm ít nhất một mức có ý nghĩa với SLA.
- p99 không xấu đi ở nhóm parameter lớn.
- Buffers read giảm rõ rệt.
- Write throughput không giảm vượt ngân sách.
- Index size nằm trong reserve storage.
- Mixed workload vẫn đáp ứng SLA và replication lag.

Các ngưỡng cụ thể phải dựa trên yêu cầu hệ thống. Không dùng một phần trăm cố định cho mọi database.

## 15. Những nhầm lẫn thường gặp

- **“Index scan luôn nhanh hơn sequential scan.”** Nếu predicate trả nhiều dòng hoặc bảng nhỏ, sequential scan có thể rẻ hơn.
- **“LIMIT 50 nghĩa là database chỉ đọc 50 dòng.”** Nếu phải sort, engine có thể cần đọc toàn bộ tập dòng phù hợp trước khi chọn 50 dòng đầu.
- **“Top-N heapsort không tốn công.”** Nó giảm bộ nhớ sort nhưng vẫn phải xét toàn bộ đầu vào.
- **“Cost là milliseconds.”** Cost là đơn vị tương đối của planner.
- **“shared read là chắc chắn đọc ổ đĩa vật lý.”** Block có thể nằm trong OS page cache; cần đối chiếu storage metrics.
- **“Chỉ cần nhìn plan node.”** Phải xem actual rows, loops, buffers, latency và workload mix.
- **“Equality luôn phải đứng trước range trong mọi index.”** Đây là hướng dẫn phổ biến cho B-tree, nhưng cần xét toàn bộ predicate, sort, prefix query và workload.
- **“DESC luôn bắt buộc phải khai báo trong index.”** B-tree có thể backward scan; direction nhiều cột và NULL ordering mới cần xem kỹ.
- **“INCLUDE làm index miễn phí trở thành covering index.”** INCLUDE tăng dung lượng và write cost; index-only scan còn phụ thuộc visibility map.
- **“Partial index được dùng cho mọi prepared statement.”** Planner phải chứng minh predicate query hàm ý predicate của index; generic plan có thể không đủ thông tin.
- **“Statistics chỉ cần cập nhật sau khi tạo index.”** Statistics phản ánh phân bố dữ liệu; thay đổi dữ liệu và skew có thể làm estimate sai.
- **“Có thể ép planner dùng index để chứng minh index tốt.”** Plan bị ép không đại diện quyết định tự nhiên của planner trong production.
- **“Index mới chỉ ảnh hưởng truy vấn mục tiêu.”** Nó ảnh hưởng storage, cache, WAL, INSERT/UPDATE/DELETE và vacuum.

## 16. Checklist thực hành

- [ ] Đã xác định semantics của filter, sort, limit và thứ tự ổn định.
- [ ] Đã hiểu kích thước bảng, skew, selectivity và tỷ lệ đọc/ghi.
- [ ] Đã lưu SQL, parameter set và baseline latency/throughput.
- [ ] Đã chạy `EXPLAIN` và `EXPLAIN ANALYZE` trong môi trường phù hợp.
- [ ] Đã đọc scan type, sort, rows, loops, actual time và buffers.
- [ ] Đã kiểm tra estimate so với actual rows và statistics freshness.
- [ ] Đã xác định index ghép có thể phục vụ equality predicate và `ORDER BY`.
- [ ] Đã đánh giá ASC/DESC, NULL ordering, collation và tie-breaker.
- [ ] Đã cân nhắc partial index hoặc INCLUDE chỉ khi có lợi ích đo được.
- [ ] Đã kiểm tra index-only scan và `Heap Fetches` nếu liên quan.
- [ ] Đã test nhiều parameter set, bao gồm tenant nhỏ và tenant lớn.
- [ ] Đã đo INSERT/UPDATE/DELETE, WAL, index size và vacuum sau thay đổi.
- [ ] Đã benchmark workload hỗn hợp với concurrency đại diện.
- [ ] Đã xác nhận kết quả dữ liệu không thay đổi ngoài yêu cầu.
- [ ] Đã có kế hoạch triển khai, giám sát và rollback.

## Kết luận

Tối ưu truy vấn lọc và sắp xếp bắt đầu từ việc hiểu semantics, dữ liệu và workload. Execution plan cho biết database đang scan, filter, sort và truy cập heap như thế nào; `EXPLAIN ANALYZE` cùng buffers cho biết công việc thực tế. Khi query cần lọc bằng các điều kiện equality rồi sắp xếp theo thời gian, B-tree index ghép có thể thu hẹp phạm vi và cung cấp thứ tự để `LIMIT` dừng sớm. Partial index và `INCLUDE` có thể tăng hiệu quả trong những trường hợp cụ thể, nhưng làm tăng chi phí ghi và dung lượng.

Không đánh giá thành công chỉ bằng việc plan có `Index Scan` hoặc thời gian một lần chạy giảm. Hãy so sánh actual rows, loops, buffers, sort, heap fetches, latency phân vị và write overhead trên workload đại diện. Kiểm tra nhiều tham số, mixed workload và khả năng rollback trước khi triển khai. Cách làm này biến việc thêm index hoặc sửa SQL thành quyết định dựa trên số liệu, phù hợp với mục tiêu tối ưu hiệu năng tổng thể của database.
