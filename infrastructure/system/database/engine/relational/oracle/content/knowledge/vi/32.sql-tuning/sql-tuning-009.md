# Tối ưu phân trang, Top-N và truy vấn theo khoảng thời gian

> **Chủ đề:** Database Engine Relational Oracle  
> **Chương:** Tối ưu SQL  
> **Mục tiêu:** Thiết kế truy vấn phân trang ổn định; phân biệt OFFSET/FETCH, ROWNUM, analytic functions và keyset pagination; tối ưu Top-N tổng thể và Top-N theo nhóm; chọn index phù hợp với filter và ORDER BY; viết truy vấn thời gian theo khoảng nửa mở để tận dụng index và partition pruning; xử lý DATE, TIMESTAMP, time zone và daylight saving; đánh giá execution plan và tính nhất quán khi dữ liệu thay đổi.

## 1. Ba bài toán thường gặp

Ứng dụng thường cần ba dạng truy vấn có vẻ giống nhau nhưng mục tiêu khác nhau:

1. **Pagination:** chia tập kết quả thành nhiều trang, ví dụ mỗi trang 25 đơn hàng.
2. **Top-N:** lấy N hàng tốt nhất theo tiêu chí, ví dụ 10 đơn hàng có tổng tiền cao nhất.
3. **Time-range query:** lấy dữ liệu trong khoảng thời gian, ví dụ giao dịch từ đầu ngày đến trước đầu ngày tiếp theo.

Cả ba thường có WHERE, ORDER BY và giới hạn số hàng. Tối ưu tốt đòi hỏi hiểu cách Oracle truy cập dữ liệu, sắp xếp, bỏ qua hàng, dừng sớm và duy trì thứ tự khi dữ liệu thay đổi.

Ví dụ bảng ORDERS:

~~~sql
CREATE TABLE orders (
    order_id      NUMBER PRIMARY KEY,
    customer_id   NUMBER NOT NULL,
    status        VARCHAR2(20) NOT NULL,
    created_at    TIMESTAMP(6) NOT NULL,
    total_amount  NUMBER(12,2) NOT NULL
);
~~~

Các truy vấn điển hình:

- Trang đầu: lấy 25 đơn mới nhất.
- Trang 200: bỏ qua 4.975 đơn rồi lấy 25 đơn tiếp theo.
- Lấy 10 đơn có tổng tiền lớn nhất.
- Lấy 10 đơn mới nhất của một khách hàng trong tháng trước.
- Lấy tối đa 3 đơn giá trị cao nhất của mỗi khách hàng.

Không nên dùng cùng một kỹ thuật cho mọi trường hợp. OFFSET/FETCH dễ dùng cho trang số bất kỳ; keyset pagination phù hợp khi người dùng đi tuần tự qua tập kết quả lớn; analytic functions phù hợp với Top-N theo nhóm.

## 2. Thứ tự kết quả phải xác định rõ

Một bảng quan hệ không có thứ tự hàng mặc định. Nếu truy vấn cần phân trang hoặc Top-N, phải dùng ORDER BY.

Ví dụ không ổn định:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
FETCH FIRST 25 ROWS ONLY;
~~~

Không có ORDER BY, Oracle có thể trả các hàng theo access path hoặc execution plan hiện tại. Kết quả trang có thể đổi khi statistics, index, cache hoặc plan thay đổi.

Cần sắp xếp theo một thứ tự có thể phân biệt mọi hàng:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 25 ROWS ONLY;
~~~

CREATED_AT xác định thứ tự thời gian; ORDER_ID là tie-breaker để phân biệt các đơn có cùng timestamp.

### 2.1. Vì sao cần tie-breaker duy nhất?

Giả sử nhiều đơn có cùng CREATED_AT. Nếu chỉ ORDER BY CREATED_AT DESC, Oracle không có nghĩa vụ giữ thứ tự tương đối cố định giữa các hàng có cùng giá trị sort key.

Khi chia trang, một hàng có thể xuất hiện lại hoặc bị bỏ qua nếu thứ tự trong nhóm đồng hạng thay đổi. Thêm khóa duy nhất tạo thứ tự toàn phần, miễn ORDER_ID thực sự duy nhất và không NULL.

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

### 2.2. NULL trong cột sắp xếp

Oracle cho phép chỉ định NULLS FIRST hoặc NULLS LAST:

~~~sql
ORDER BY shipped_at DESC NULLS LAST, order_id DESC
~~~

Nếu dùng keyset pagination trên cột có thể NULL, predicate so sánh cần xử lý nhóm NULL riêng vì phép so sánh với NULL không trả TRUE/FALSE thông thường mà trả UNKNOWN.

Đơn giản nhất là chọn cột sort NOT NULL hoặc dùng biểu thức sort chuẩn hóa có index phù hợp. Nếu phải hỗ trợ NULL, xác định rõ vị trí NULL trong thứ tự và viết predicate phân trang cho cả hai nhóm.

## 3. OFFSET/FETCH: phân trang theo số hàng bỏ qua

Từ Oracle Database 12c, SQL hỗ trợ row limiting clause với OFFSET và FETCH.

Lấy trang đầu, 25 hàng:

~~~sql
SELECT order_id,
       customer_id,
       created_at,
       total_amount
FROM orders
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 25 ROWS ONLY;
~~~

Lấy trang thứ 3, mỗi trang 25 hàng:

~~~sql
SELECT order_id,
       customer_id,
       created_at,
       total_amount
FROM orders
ORDER BY created_at DESC, order_id DESC
OFFSET 50 ROWS
FETCH NEXT 25 ROWS ONLY;
~~~

OFFSET là số hàng bỏ qua; FETCH NEXT là số hàng tối đa muốn nhận. Với trang đánh số từ 1, offset bằng (page number trừ 1) nhân page size.

### 3.1. Bind biến cho page và page size

Ứng dụng nên bind giá trị thay vì nối trực tiếp số vào SQL:

~~~sql
SELECT order_id,
       customer_id,
       created_at,
       total_amount
FROM orders
ORDER BY created_at DESC, order_id DESC
OFFSET :p_offset ROWS
FETCH NEXT :p_page_size ROWS ONLY;
~~~

Validate ở tầng ứng dụng:

- Offset phải là số nguyên không âm.
- Page size phải là số nguyên dương.
- Đặt giới hạn tối đa page size để tránh một request kéo quá nhiều dữ liệu.
- Không cho người dùng gửi page size cực lớn hoặc offset vượt giới hạn sản phẩm nếu không có nhu cầu.

Bind variable áp dụng cho giá trị. Tên cột sort direction hoặc SQL fragment không thể bind như dữ liệu; nếu cho phép chọn sort field, dùng whitelist các lựa chọn hợp lệ.

### 3.2. OFFSET lớn có thể đắt

Để lấy trang 1.000 với 25 hàng mỗi trang, Oracle cần xác định và bỏ qua 24.975 hàng đứng trước trong thứ tự kết quả.

Ngay cả khi có index phù hợp, database có thể phải đi qua nhiều entry index rồi mới tới hàng cần trả. Chi phí tăng theo offset, tùy access path và plan.

OFFSET/FETCH tiện cho trang gần đầu, giao diện cần nhảy tới trang bất kỳ và tập dữ liệu không quá lớn. Với luồng cuộn vô hạn qua hàng triệu hàng, keyset pagination thường phù hợp hơn.

### 3.3. FETCH FIRST ... WITH TIES

Nếu muốn lấy ít nhất N hàng và giữ tất cả hàng đồng hạng với hàng cuối theo sort key:

~~~sql
SELECT order_id, total_amount
FROM orders
ORDER BY total_amount DESC
FETCH FIRST 10 ROWS WITH TIES;
~~~

Kết quả có thể nhiều hơn 10 hàng nếu nhiều đơn cùng TOTAL_AMOUNT tại vị trí thứ 10.

WITH TIES dựa trên toàn bộ biểu thức ORDER BY. Nếu thêm ORDER_ID duy nhất vào ORDER BY thì các hàng gần như không còn tie. Nếu muốn tie theo TOTAL_AMOUNT nhưng vẫn trình bày các hàng đồng hạng theo ORDER_ID, có thể chọn Top-N WITH TIES trong truy vấn con rồi sắp xếp kết quả bên ngoài:

~~~sql
SELECT order_id, total_amount
FROM (
    SELECT order_id, total_amount
    FROM orders
    ORDER BY total_amount DESC
    FETCH FIRST 10 ROWS WITH TIES
)
ORDER BY total_amount DESC, order_id DESC;
~~~

### 3.4. FETCH FIRST ... PERCENT

Oracle cũng hỗ trợ lấy một tỷ lệ phần trăm số hàng trong các trường hợp cú pháp hỗ trợ:

~~~sql
SELECT order_id, total_amount
FROM orders
ORDER BY total_amount DESC
FETCH FIRST 5 PERCENT ROWS ONLY;
~~~

PERCENT thường phù hợp cho một số báo cáo hơn là API pagination vì số hàng trả về thay đổi theo kích thước tập kết quả.

## 4. ROWNUM cho phiên bản Oracle cũ

Trước row limiting clause, ROWNUM thường được dùng để giới hạn số hàng.

### 4.1. Top-N với ROWNUM

Đặt ORDER BY trong truy vấn con rồi mới áp dụng ROWNUM bên ngoài:

~~~sql
SELECT *
FROM (
    SELECT order_id, created_at, total_amount
    FROM orders
    ORDER BY created_at DESC, order_id DESC
)
WHERE ROWNUM <= 25;
~~~

Nếu đặt ROWNUM và ORDER BY cùng một query block theo cách không đúng, Oracle có thể lấy 25 hàng trước rồi mới sắp xếp 25 hàng đó; kết quả không phải Top 25 toàn bảng.

### 4.2. Pagination với ROWNUM

Mẫu phân trang truyền thống:

~~~sql
SELECT order_id,
       customer_id,
       created_at,
       total_amount
FROM (
    SELECT q.*,
           ROWNUM AS rn
    FROM (
        SELECT order_id,
               customer_id,
               created_at,
               total_amount
        FROM orders
        ORDER BY created_at DESC, order_id DESC
    ) q
    WHERE ROWNUM <= :p_offset + :p_page_size
)
WHERE rn > :p_offset
ORDER BY rn;
~~~

Truy vấn trong cùng sắp xếp dữ liệu. Query block kế tiếp giới hạn số hàng tối đa cần xét. Query ngoài loại các hàng có RN không vượt offset.

ROWNUM được gán theo thứ tự Oracle chọn hàng trong query block. Nó không phải số thứ tự cố định của bảng và không nên lưu làm khóa phân trang.

### 4.3. Vì sao không viết ROWNUM > 10 trực tiếp?

Trong cùng query block, ROWNUM được gán khi Oracle chọn hàng. Điều kiện ROWNUM > 10 thường không trả hàng vì hàng đầu tiên được xét có ROWNUM = 1 và bị loại; hàng tiếp theo vẫn là ứng viên đầu tiên có thể nhận ROWNUM = 1.

Muốn bỏ qua một đoạn, phải tạo query block trung gian để gán ROWNUM tới giới hạn trên, rồi lọc RN lớn hơn offset ở query block bên ngoài.

## 5. ROW_NUMBER và analytic functions

ROW_NUMBER gán số thứ tự cho từng hàng theo ORDER BY trong analytic clause.

~~~sql
SELECT order_id,
       created_at,
       total_amount,
       ROW_NUMBER() OVER (
           ORDER BY created_at DESC, order_id DESC
       ) AS rn
FROM orders;
~~~

Có thể dùng query ngoài để lấy một khoảng số thứ tự:

~~~sql
SELECT order_id,
       created_at,
       total_amount
FROM (
    SELECT order_id,
           created_at,
           total_amount,
           ROW_NUMBER() OVER (
               ORDER BY created_at DESC, order_id DESC
           ) AS rn
    FROM orders
)
WHERE rn BETWEEN :p_first_row AND :p_last_row
ORDER BY rn;
~~~

ROW_NUMBER hữu ích khi cần gán thứ tự tường minh, phân trang theo số thứ tự hoặc Top-N theo nhóm.

### 5.1. ROW_NUMBER, RANK và DENSE_RANK

| Hàm | Hành vi khi đồng hạng |
|---|---|
| ROW_NUMBER | Luôn cấp số khác nhau cho từng hàng |
| RANK | Các hàng đồng hạng có cùng rank; vị trí sau nhóm tie bị nhảy |
| DENSE_RANK | Các hàng đồng hạng có cùng rank; rank kế tiếp không bị nhảy |

Ví dụ điểm số:

| Score | ROW_NUMBER | RANK | DENSE_RANK |
|---:|---:|---:|---:|
| 100 | 1 | 1 | 1 |
| 90 | 2 | 2 | 2 |
| 90 | 3 | 2 | 2 |
| 80 | 4 | 4 | 3 |

Nếu yêu cầu đúng 3 hàng, dùng ROW_NUMBER. Nếu muốn lấy tất cả hàng thuộc 3 vị trí xếp hạng đầu, dùng RANK. Nếu muốn lấy 3 mức điểm khác nhau, dùng DENSE_RANK.

### 5.2. Top-N theo nhóm bằng ROW_NUMBER

Ví dụ lấy 3 đơn có giá trị cao nhất cho mỗi khách hàng:

~~~sql
SELECT customer_id,
       order_id,
       total_amount,
       rn
FROM (
    SELECT customer_id,
           order_id,
           total_amount,
           ROW_NUMBER() OVER (
               PARTITION BY customer_id
               ORDER BY total_amount DESC, order_id DESC
           ) AS rn
    FROM orders
)
WHERE rn <= 3
ORDER BY customer_id, rn;
~~~

PARTITION BY tạo thứ tự riêng trong mỗi customer. Đây là Top-N per group, khác với FETCH FIRST 3 ROWS ONLY áp dụng cho toàn bộ kết quả.

Nếu cần giữ tất cả đơn đồng hạng ở vị trí thứ ba, thay ROW_NUMBER bằng RANK và chỉ đưa các cột tie-defining vào ORDER BY của analytic function.

### 5.3. Dùng RANK khi cần giữ đồng hạng

~~~sql
SELECT customer_id,
       order_id,
       total_amount,
       rnk
FROM (
    SELECT customer_id,
           order_id,
           total_amount,
           RANK() OVER (
               PARTITION BY customer_id
               ORDER BY total_amount DESC
           ) AS rnk
    FROM orders
)
WHERE rnk <= 3
ORDER BY customer_id, total_amount DESC, order_id DESC;
~~~

Ở đây tất cả đơn cùng tổng tiền có rank như nhau. Nếu thêm ORDER_ID vào ORDER BY trong RANK, các đơn sẽ không còn đồng hạng theo TOTAL_AMOUNT.

## 6. Keyset pagination (seek pagination)

Keyset pagination dùng giá trị của hàng cuối trang hiện tại làm mốc để lấy trang tiếp theo. Thay vì bỏ qua N hàng đầu, query tìm các hàng đứng sau khóa sort cuối cùng.

Giả sử thứ tự:

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

Trang đầu:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE status = :p_status
ORDER BY created_at DESC, order_id DESC
FETCH FIRST :p_page_size ROWS ONLY;
~~~

Giả sử hàng cuối trang có CREATED_AT = :p_last_created_at và ORDER_ID = :p_last_order_id. Trang tiếp theo:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE status = :p_status
  AND (
       created_at < :p_last_created_at
       OR (
           created_at = :p_last_created_at
           AND order_id < :p_last_order_id
       )
  )
ORDER BY created_at DESC, order_id DESC
FETCH FIRST :p_page_size ROWS ONLY;
~~~

Vì thứ tự giảm dần, hàng tiếp theo có timestamp nhỏ hơn; nếu timestamp bằng nhau, ORDER_ID phải nhỏ hơn.

### 6.1. Vì sao keyset thường nhanh hơn ở trang sâu?

OFFSET 100.000 cần bỏ qua một đoạn lớn của thứ tự kết quả. Keyset dùng điều kiện range trên sort key để bắt đầu gần vị trí cần tiếp tục.

Nếu có index phù hợp, Oracle có thể range scan từ mốc cursor rồi dừng sau page size hàng. Chi phí thường ổn định hơn khi người dùng đi sâu qua tập dữ liệu lớn, mặc dù kết quả thực tế vẫn phụ thuộc filter, index, selectivity và plan.

### 6.2. Composite key phải xuất hiện trong cursor

Nếu ORDER BY là CREATED_AT DESC, ORDER_ID DESC, cursor phải mang cả hai giá trị. Chỉ truyền CREATED_AT sẽ bỏ sót hoặc lặp các hàng cùng timestamp.

Nếu thứ tự có hướng hỗn hợp:

~~~sql
ORDER BY priority DESC, created_at ASC, order_id ASC
~~~

predicate keyset phải mô tả đúng thứ tự từ trái sang phải:

~~~sql
WHERE priority < :last_priority
   OR (
       priority = :last_priority
       AND created_at > :last_created_at
   )
   OR (
       priority = :last_priority
       AND created_at = :last_created_at
       AND order_id > :last_order_id
   )
~~~

Cột đầu sắp DESC nên giá trị tiếp theo nhỏ hơn; hai cột sau sắp ASC nên giá trị tiếp theo lớn hơn. Không thể dùng một dấu so sánh duy nhất cho mọi cột khi sort direction khác nhau.

### 6.3. Keyset và NULL

Điều kiện <, > và = với NULL không hoạt động như so sánh giá trị thông thường. Nếu cột sort nullable, cần thiết kế cursor và predicate cho nhóm NULL theo đúng NULLS FIRST/LAST.

Các lựa chọn:

- Dùng cột NOT NULL làm sort key.
- Chuẩn hóa NULL thành giá trị sentinel bằng biểu thức được index.
- Tạo hai nhánh truy vấn cho NULL và non-NULL.
- Lưu thêm flag biểu thị nhóm NULL trong cursor.

Không chọn sentinel tùy tiện nếu giá trị đó có thể xuất hiện trong dữ liệu thật.

### 6.4. Trang trước với keyset

Để lấy trang trước trong thứ tự DESC, dùng khóa ở hàng đầu trang hiện tại, đổi điều kiện sang lớn hơn và đảo thứ tự truy vấn để lấy các hàng gần nhất:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE status = :p_status
  AND (
       created_at > :p_first_created_at
       OR (
           created_at = :p_first_created_at
           AND order_id > :p_first_order_id
       )
  )
ORDER BY created_at ASC, order_id ASC
FETCH FIRST :p_page_size ROWS ONLY;
~~~

Ứng dụng đảo thứ tự các hàng trả về để hiển thị lại theo CREATED_AT DESC, ORDER_ID DESC.

### 6.5. Keyset không hỗ trợ nhảy tới trang tùy ý tự nhiên

Keyset cần cursor của trang trước. Nó phù hợp với Next/Previous, infinite scrolling, feed, lịch sử giao dịch và API continuation token.

Nếu người dùng cần nhập “đến trang 500”, OFFSET hoặc một cấu trúc đánh số/anchor riêng có thể phù hợp hơn.

### 6.6. Cursor token phía API

Token có thể chứa:

- Giá trị sort key cuối cùng.
- Các filter đang áp dụng.
- Sort direction và version của sort definition.
- Snapshot SCN nếu ứng dụng cần một snapshot nhất quán.
- Chữ ký hoặc mã xác thực để client không thể sửa token tùy ý.

Không nhất thiết đưa toàn bộ token ra dạng JSON rõ ràng. Có thể encode và ký token ở tầng ứng dụng. Mọi giá trị vẫn phải bind khi đưa vào SQL.

## 7. Concurrency và tính nhất quán giữa các trang

Mỗi SELECT trong Oracle có read consistency tại một SCN. Với READ COMMITTED, hai câu SELECT chạy ở hai thời điểm có thể nhìn thấy hai snapshot khác nhau.

Ví dụ OFFSET pagination:

1. Trang 1 lấy 25 hàng mới nhất.
2. Một transaction khác INSERT hàng mới đứng đầu thứ tự.
3. Trang 2 dùng OFFSET 25.
4. Hàng mới làm dịch vị trí; trang 2 có thể lặp một hàng đã thấy hoặc bỏ qua một hàng.

DELETE hoặc UPDATE sort key cũng có thể làm các hàng dịch chuyển.

### 7.1. Keyset giảm một số vấn đề dịch vị trí

Keyset tiếp tục từ giá trị khóa cuối trang, nên một INSERT mới đứng trước cursor thường không làm các hàng cũ bị dịch offset. Tuy nhiên:

- Hàng có sort key bị UPDATE có thể di chuyển qua cursor.
- Hàng bị DELETE sẽ không còn xuất hiện.
- Hàng mới có sort key nằm sau cursor có thể xuất hiện ở trang sau.
- Keyset không tạo snapshot nhất quán toàn bộ session.

Nó cải thiện tính ổn định của continuation, nhưng không thay thế snapshot semantics khi nghiệp vụ cần duyệt đúng tập dữ liệu tại một thời điểm.

### 7.2. Duyệt cùng một snapshot bằng Flashback Query

Nếu cần mọi trang nhìn cùng một trạng thái dữ liệu, có thể chụp SCN ban đầu và dùng Flashback Query AS OF SCN cho các trang:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders AS OF SCN :p_snapshot_scn
WHERE status = :p_status
ORDER BY created_at DESC, order_id DESC
OFFSET :p_offset ROWS
FETCH NEXT :p_page_size ROWS ONLY;
~~~

Với keyset, thay OFFSET bằng cursor predicate nhưng vẫn dùng cùng SCN.

Flashback Query phụ thuộc UNDO còn khả dụng, quyền truy cập và cấu hình database. Nếu snapshot quá cũ so với undo retention, query có thể gặp lỗi snapshot too old. Không giữ một snapshot qua thời gian dài nếu workload và undo capacity không hỗ trợ.

### 7.3. Chọn consistency theo yêu cầu nghiệp vụ

| Yêu cầu | Chiến lược |
|---|---|
| Feed thay đổi liên tục, chấp nhận hàng mới xuất hiện | Keyset pagination |
| Báo cáo cần tập kết quả nhất quán qua nhiều trang | Cùng snapshot SCN/Flashback Query nếu khả thi |
| Giao diện cho phép nhảy trang bất kỳ | OFFSET/FETCH |
| Duyệt lịch sử lớn tuần tự | Keyset với unique sort key |
| Export cần dữ liệu nhất quán | Snapshot SCN hoặc quy trình export transaction phù hợp |

Không hứa hẹn “không trùng, không thiếu” nếu mỗi trang chạy trên snapshot khác nhau và dữ liệu có thể thay đổi.

## 8. Top-N: lấy một số hàng tốt nhất

Top-N là truy vấn lấy N hàng đứng đầu theo một tiêu chí:

~~~sql
SELECT order_id,
       customer_id,
       total_amount
FROM orders
ORDER BY total_amount DESC, order_id DESC
FETCH FIRST 10 ROWS ONLY;
~~~

Top-N có thể được tối ưu bằng index phù hợp với ORDER BY, Top-N sort/stopkey để tránh sắp xếp toàn bộ tập dữ liệu khi chỉ cần vài hàng, predicate chọn lọc để giảm tập đầu vào và chọn đúng cột trả về để tránh truy cập bảng nhiều lần.

### 8.1. Top-N optimization và STOPKEY

Khi query chỉ cần N hàng đầu, Oracle có thể dùng chiến lược dừng sớm. Plan có thể hiển thị operation dạng SORT ORDER BY STOPKEY hoặc một biến thể STOPKEY/row-limiting phù hợp với release.

Nếu index cung cấp sẵn thứ tự cần thiết, Oracle có thể đọc index theo thứ tự và dừng khi đủ N hàng mà không cần sort toàn bộ tập dữ liệu.

Optimizer không bắt buộc chọn index chỉ vì index có cùng cột ORDER BY. Nếu filter không chọn lọc, index access cộng table lookup có thể đắt hơn full scan và sort. Kiểm tra plan thực tế.

### 8.2. Index cho Top-N theo thời gian

Truy vấn:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE status = 'OPEN'
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Index phù hợp để thử:

~~~sql
CREATE INDEX orders_status_created_ix
ON orders(status, created_at DESC, order_id DESC);
~~~

STATUS là equality predicate; các cột tiếp theo cung cấp thứ tự. Oracle có thể range scan phần index của OPEN và dừng sau khi tìm đủ 20 hàng nếu plan và selectivity phù hợp.

Nếu query trả thêm cột không có trong index, Oracle có thể truy cập table row qua ROWID. Không thêm mọi cột vào index một cách máy móc; index rộng tăng storage, redo và chi phí DML.

### 8.3. Index cho Top-N theo số tiền

~~~sql
SELECT order_id, total_amount
FROM orders
WHERE status = 'OPEN'
ORDER BY total_amount DESC, order_id DESC
FETCH FIRST 10 ROWS ONLY;
~~~

Có thể đánh giá:

~~~sql
CREATE INDEX orders_status_amount_ix
ON orders(status, total_amount DESC, order_id DESC);
~~~

Index này phù hợp với filter STATUS và sort TOTAL_AMOUNT/ORDER_ID. Nhưng nếu query chỉ lấy đơn có CREATED_AT trong một khoảng hẹp, thiết kế index có thể cần thay đổi để cân bằng time-range filter và sort.

Không có một thứ tự index tối ưu cho mọi tổ hợp predicate. Cần dựa vào workload chính, selectivity và execution plan.

## 9. Index cho pagination và keyset

Giả sử truy vấn:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = :p_customer_id
  AND status = :p_status
ORDER BY created_at DESC, order_id DESC
FETCH FIRST :p_page_size ROWS ONLY;
~~~

Một index để thử:

~~~sql
CREATE INDEX orders_customer_status_page_ix
ON orders(
    customer_id,
    status,
    created_at DESC,
    order_id DESC
);
~~~

Hai cột đầu là equality filters; hai cột sau là sort keys. Index có thể hỗ trợ seek tới đúng customer/status rồi đọc theo thứ tự.

### 9.1. Equality columns trước range/order columns

Với pattern:

~~~sql
WHERE tenant_id = :tenant
  AND created_at >= :start_ts
  AND created_at < :end_ts
ORDER BY created_at DESC, order_id DESC
~~~

Index thường được cân nhắc:

~~~sql
CREATE INDEX orders_tenant_time_page_ix
ON orders(tenant_id, created_at DESC, order_id DESC);
~~~

TENANT_ID là equality prefix. CREATED_AT hỗ trợ range và ordering; ORDER_ID tạo thứ tự phụ ổn định.

Nếu có thêm filter STATUS, việc đưa STATUS vào trước hay sau CREATED_AT phụ thuộc workload. Nếu STATUS có equality trong hầu hết query, có thể thử (TENANT_ID, STATUS, CREATED_AT, ORDER_ID). Nếu STATUS chỉ là filter phụ và time range rất chọn lọc, một thứ tự khác có thể tốt hơn.

### 9.2. Hướng ASC/DESC trong index

Oracle B-tree có thể scan index theo chiều thuận hoặc ngược. Một index ASC trên toàn bộ sort key có thể được scan ngược để phục vụ thứ tự DESC trên toàn bộ các cột đó.

Khi thứ tự có hướng hỗn hợp, ví dụ SCORE DESC, CREATED_AT ASC, ORDER_ID ASC, hướng index cần được thiết kế phù hợp. Đối chiếu plan thay vì giả định index ASC/DESC luôn tương đương.

### 9.3. Covering access

Nếu các cột cần trả về đều có trong index, Oracle có thể đáp ứng truy vấn bằng index mà không truy cập table row. Tuy nhiên, thêm nhiều cột vào B-tree làm index lớn và tăng chi phí ghi.

Chỉ cân nhắc covering index khi query chạy thường xuyên, tập kết quả nhỏ, workload nhạy latency và lợi ích giảm table access lớn hơn chi phí duy trì index.

## 10. Top-N theo nhóm và thiết kế dữ liệu

Top-N per group thường dùng analytic function:

~~~sql
SELECT customer_id, order_id, total_amount
FROM (
    SELECT customer_id,
           order_id,
           total_amount,
           ROW_NUMBER() OVER (
               PARTITION BY customer_id
               ORDER BY total_amount DESC, order_id DESC
           ) AS rn
    FROM orders
)
WHERE rn <= 3;
~~~

Nếu bảng rất lớn và cần Top 3 cho hàng triệu nhóm, Oracle vẫn phải xử lý nhiều dữ liệu để xác định kết quả. Index trên (CUSTOMER_ID, TOTAL_AMOUNT DESC, ORDER_ID DESC) có thể hữu ích cho một số workload, nhưng không bảo đảm toàn truy vấn chỉ đọc 3 hàng mỗi nhóm.

Cân nhắc giới hạn tập khách hàng trước khi analytic operation, chỉ chọn cột cần thiết, dùng predicate đẩy xuống query block khi semantics cho phép, index theo partition key và sort key, hoặc materialized view/bảng summary nếu Top-N được đọc thường xuyên.

## 11. Truy vấn theo khoảng thời gian: dùng khoảng nửa mở

Một pattern đáng tin cậy cho time-range query là khoảng từ START bao gồm đến END không bao gồm, thường gọi là half-open interval.

~~~sql
WHERE created_at >= :p_start_ts
  AND created_at <  :p_end_ts
~~~

Đây là khoảng nửa mở: bao gồm đầu, không bao gồm cuối.

### 11.1. Vì sao không dùng BETWEEN cho cả ngày?

BETWEEN bao gồm cả hai đầu:

~~~sql
WHERE created_at BETWEEN :p_start_ts AND :p_end_ts
~~~

Nếu END được truyền là nửa đêm đầu ngày tiếp theo, hàng đúng tại thời điểm đó cũng được lấy vào, dù người dùng chỉ muốn ngày trước.

Nếu END là 23:59:59, có thể bỏ sót dữ liệu có fractional seconds như 23:59:59.123456 trong TIMESTAMP(6).

Dùng:

~~~sql
WHERE created_at >= :p_day_start
  AND created_at <  :p_next_day_start
~~~

Không cần đoán độ chính xác timestamp hoặc tạo giá trị “cuối ngày” giả.

### 11.2. Truy vấn một ngày với DATE

Oracle DATE lưu ngày và thời gian đến giây, không chỉ ngày lịch.

~~~sql
SELECT order_id, created_at
FROM orders_date
WHERE created_at >= TRUNC(:p_day)
  AND created_at <  TRUNC(:p_day) + 1;
~~~

TRUNC áp dụng lên bind value, không áp dụng lên cột CREATED_AT. Điều này giúp điều kiện vẫn có thể dùng B-tree index range scan trên CREATED_AT.

Nếu bind đã là midnight chính xác, có thể truyền trực tiếp START và END đã tính trước.

### 11.3. Truy vấn một ngày với TIMESTAMP

~~~sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= :p_start_ts
  AND created_at <  :p_end_ts;
~~~

Bind phải có datatype tương thích với cột TIMESTAMP. Tránh truyền chuỗi rồi dựa vào NLS_DATE_FORMAT hoặc implicit conversion.

### 11.4. Truy vấn một tháng

Tính ngày đầu tháng và ngày đầu tháng kế tiếp:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE created_at >= :p_month_start
  AND created_at <  ADD_MONTHS(:p_month_start, 1);
~~~

P_MONTH_START nên là ngày đầu tháng lúc 00:00:00 và có datatype phù hợp với cột. Với TIMESTAMP, có thể tính boundary trong ứng dụng hoặc chuyển đổi có chủ đích để giữ datatype và precision.

### 11.5. Truy vấn một năm

~~~sql
SELECT COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
FROM orders
WHERE created_at >= TIMESTAMP '2026-01-01 00:00:00'
  AND created_at <  TIMESTAMP '2027-01-01 00:00:00';
~~~

ANSI timestamp literal giúp tránh phụ thuộc định dạng ngày trong session. Trong ứng dụng, bind hai boundary thường linh hoạt và an toàn hơn hardcode literal.

## 12. DATE, TIMESTAMP và time zone

Chọn đúng datatype rất quan trọng khi dữ liệu đại diện thời điểm thực tế.

| Datatype | Đặc điểm |
|---|---|
| DATE | Ngày và giờ đến giây; không lưu time zone |
| TIMESTAMP | Có fractional seconds; không lưu time zone |
| TIMESTAMP WITH TIME ZONE | Lưu timestamp cùng thông tin múi giờ/offset |
| TIMESTAMP WITH LOCAL TIME ZONE | Chuẩn hóa theo database time zone và hiển thị theo session time zone; không giữ nguyên zone gốc như một phần giá trị |

Không so sánh chuỗi ngày tháng với cột DATE/TIMESTAMP bằng implicit conversion. Bind value nên có kiểu tương ứng.

### 12.1. Ngày nghiệp vụ và múi giờ

Một ngày nghiệp vụ thường được hiểu theo múi giờ của địa điểm hoặc khách hàng, không phải UTC mặc định.

Ví dụ báo cáo “ngày 14/11 tại Việt Nam” cần xác định đầu ngày 14/11 theo Asia/Ho_Chi_Minh và đầu ngày kế tiếp theo cùng múi giờ. Sau đó chuyển hai boundary sang timezone/representation phù hợp với cột lưu trữ.

Nếu hệ thống lưu instant UTC, tính hai midnight trong múi giờ nghiệp vụ rồi chuyển sang UTC trước khi bind. Không lấy UTC midnight nếu yêu cầu là ngày địa phương.

### 12.2. Daylight Saving Time

Ở các vùng có daylight saving, một ngày địa phương có thể dài 23 hoặc 25 giờ. Vì vậy không luôn tính END bằng cách cộng đúng 24 giờ vào một instant UTC.

Hãy tính đầu ngày và đầu ngày kế tiếp theo calendar của timezone region, rồi chuyển cả hai thành instant tương ứng. Dùng timezone region như America/New_York thay vì một offset cố định nếu quy tắc DST cần được áp dụng.

Việt Nam hiện không áp dụng DST, nhưng ứng dụng phục vụ nhiều quốc gia vẫn cần xử lý đúng timezone của từng tenant.

### 12.3. TIMESTAMP WITH LOCAL TIME ZONE

Với TIMESTAMP WITH LOCAL TIME ZONE, Oracle chuẩn hóa dữ liệu theo database time zone và chuyển đổi khi hiển thị theo session time zone. Kết quả hiển thị có thể khác giữa hai session.

Khi bind boundary và đọc dữ liệu, xác định rõ session time zone và quy ước lưu trữ. Tránh dựa vào chuỗi hiển thị để suy ra instant gốc.

## 13. Giữ điều kiện thời gian có thể dùng index

Giả sử có index:

~~~sql
CREATE INDEX orders_created_ix ON orders(created_at);
~~~

Predicate có khả năng dùng range scan:

~~~sql
SELECT order_id
FROM orders
WHERE created_at >= :p_start_ts
  AND created_at <  :p_end_ts;
~~~

Predicate có thể làm mất lợi thế index thông thường:

~~~sql
SELECT order_id
FROM orders
WHERE TRUNC(created_at) = :p_day;
~~~

Vì hàm TRUNC được áp dụng lên từng giá trị cột, index trên CREATED_AT không nhất thiết hỗ trợ predicate này như range predicate trực tiếp.

### 13.1. Viết lại TRUNC(column)

Thay:

~~~sql
WHERE TRUNC(created_at) = :p_day
~~~

bằng:

~~~sql
WHERE created_at >= TRUNC(:p_day)
  AND created_at <  TRUNC(:p_day) + 1
~~~

Cách này giữ cột nguyên vẹn ở phía trái phép so sánh.

### 13.2. Khi nào dùng function-based index?

Nếu workload chủ yếu truy vấn theo ngày lịch và biểu thức TRUNC(CREATED_AT) là một hợp đồng query ổn định, có thể cân nhắc:

~~~sql
CREATE INDEX orders_created_day_ix
ON orders(TRUNC(created_at));
~~~

Query phải dùng biểu thức tương thích:

~~~sql
SELECT order_id
FROM orders
WHERE TRUNC(created_at) = :p_day;
~~~

Function-based index làm tăng chi phí DML và storage. Nếu query cần khoảng thời gian tùy ý hoặc partition pruning theo CREATED_AT, range predicate trực tiếp thường linh hoạt hơn.

### 13.3. Không dùng TO_CHAR trên cột để lọc ngày

Tránh:

~~~sql
WHERE TO_CHAR(created_at, 'YYYY-MM-DD') = '2026-11-14'
~~~

Cách viết này áp dụng hàm lên từng hàng, có thể ngăn index thông thường trên CREATED_AT được dùng, phụ thuộc format model và có thể che giấu datatype conversion. Dùng typed bind values và khoảng nửa mở.

## 14. Partition pruning cho time-range query

Bảng lớn thường được partition theo ngày, tháng hoặc năm dựa trên cột thời gian.

Ví dụ:

~~~sql
CREATE TABLE orders_by_month (
    order_id      NUMBER NOT NULL,
    customer_id   NUMBER NOT NULL,
    created_at    DATE NOT NULL,
    total_amount  NUMBER(12,2)
)
PARTITION BY RANGE (created_at)
INTERVAL (NUMTOYMINTERVAL(1, 'MONTH'))
(
    PARTITION p_before_2026 VALUES LESS THAN (DATE '2026-01-01')
);
~~~

Truy vấn:

~~~sql
SELECT order_id, total_amount
FROM orders_by_month
WHERE created_at >= DATE '2026-03-01'
  AND created_at <  DATE '2026-04-01';
~~~

Oracle có thể prune các partition không liên quan và chỉ đọc partition chứa tháng 3/2026.

### 14.1. Vì sao half-open range hỗ trợ pruning?

Điều kiện range trực tiếp trên partition key cho optimizer thấy giới hạn partition:

~~~sql
created_at >= :start_date
AND created_at < :end_date
~~~

Ngược lại, bọc partition key bằng TRUNC, TO_CHAR hoặc CAST không cần thiết có thể làm partition pruning khó hơn hoặc cần cơ chế pruning khác. Giữ cột partition nguyên vẹn thường là lựa chọn rõ ràng nhất.

### 14.2. Kiểm tra partition pruning trong plan

Plan có thể hiển thị operation như PARTITION RANGE SINGLE, PARTITION RANGE ITERATOR hoặc các dạng partition access khác. Pstart/Pstop cho biết phạm vi partition được chọn.

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PARTITION +PREDICATE'
    )
);
~~~

Kiểm tra Pstart/Pstop có giới hạn đúng khoảng thời gian hay không. Với bind variable, có thể xuất hiện dynamic pruning; plan cần được đọc theo runtime và bind thực tế.

### 14.3. Local index và global index

Local index được partition tương ứng với partition của bảng; global index có phạm vi toàn bảng hoặc partitioning riêng.

- Local index thường thuận tiện cho lifecycle partition và maintenance theo partition.
- Global index có thể hỗ trợ lookup không chứa partition key nhưng có tác động khi thao tác partition.
- Lựa chọn phụ thuộc truy vấn, partition key, DML và quản trị partition.

Không chọn local/global chỉ theo quy tắc chung. Đánh giá query path và thao tác partition như DROP, TRUNCATE, EXCHANGE.

## 15. Kết hợp time-range với Top-N

Ví dụ lấy 20 giao dịch mới nhất của một tenant trong một ngày:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE tenant_id = :p_tenant_id
  AND created_at >= :p_start_ts
  AND created_at <  :p_end_ts
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Index để đánh giá:

~~~sql
CREATE INDEX orders_tenant_created_ix
ON orders(tenant_id, created_at DESC, order_id DESC);
~~~

TENANT_ID equality, CREATED_AT range/order, ORDER_ID tie-breaker. Nếu bảng partition theo CREATED_AT, predicate còn có thể prune partition.

Nếu query còn lọc STATUS:

~~~sql
AND status = :p_status
~~~

thử index có STATUS trong equality prefix nếu đây là pattern phổ biến:

~~~sql
CREATE INDEX orders_tenant_status_created_ix
ON orders(
    tenant_id,
    status,
    created_at DESC,
    order_id DESC
);
~~~

Không tạo cả hai index ngay lập tức. Dùng execution plan, workload mix và DML cost để quyết định.

## 16. Đếm tổng số hàng khi phân trang

Giao diện thường muốn hiển thị tổng số kết quả. Có nhiều cách lấy total count.

### 16.1. COUNT riêng

~~~sql
SELECT COUNT(*)
FROM orders
WHERE status = :p_status;
~~~

Sau đó chạy query page. Ưu điểm là rõ ràng, có thể tối ưu riêng. Nhược điểm là phải thực hiện thêm một truy vấn và hai truy vấn có thể nhìn thấy hai SCN khác nhau ở READ COMMITTED.

Nếu cần count và page cùng snapshot, dùng cùng snapshot SCN hoặc cơ chế transaction phù hợp.

### 16.2. COUNT(*) OVER()

Có thể trả total count kèm mỗi hàng:

~~~sql
SELECT order_id,
       created_at,
       total_amount,
       COUNT(*) OVER () AS total_rows
FROM orders
WHERE status = :p_status
ORDER BY created_at DESC, order_id DESC
OFFSET :p_offset ROWS
FETCH NEXT :p_page_size ROWS ONLY;
~~~

Cách này tiện vì count và page nằm trong một statement. Nhưng analytic COUNT có thể buộc Oracle xử lý toàn bộ tập phù hợp trước khi biết tổng, làm mất lợi ích dừng sớm của Top-N trong một số plan.

Nếu trang không có hàng, không có dòng nào để mang TOTAL_ROWS về. Ứng dụng cần xử lý trường hợp đó hoặc chạy count riêng.

### 16.3. Có thật sự cần exact count?

Với bảng rất lớn và dữ liệu thay đổi liên tục, exact COUNT(*) có thể đắt. Hãy xác định UX có cần số trang chính xác hay chỉ cần “còn dữ liệu”:

- Fetch page_size + 1 hàng để xác định có trang tiếp theo.
- Dùng keyset và next-page token, không cần total count.
- Hiển thị số kết quả gần đúng nếu nghiệp vụ chấp nhận và nguồn approximate có kiểm soát.
- Chỉ tính exact count khi người dùng mở màn hình cần tổng.

### 16.4. Fetch thêm một hàng

Ví dụ muốn hiển thị 25 hàng nhưng xác định có trang sau:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE status = :p_status
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 26 ROWS ONLY;
~~~

Nếu nhận 26 hàng, hiển thị 25 hàng đầu và đánh dấu has_next = TRUE. Cách này tránh COUNT toàn bộ kết quả chỉ để biết còn trang sau hay không.

Với keyset pagination, áp dụng cùng ý tưởng: fetch page_size + 1 sau cursor.

## 17. Filter và sort động an toàn

Ứng dụng thường cho phép người dùng chọn sort theo ngày, tổng tiền hoặc trạng thái. Không nối chuỗi input trực tiếp vào ORDER BY.

Bind variable chỉ bind giá trị, không bind tên cột hoặc ASC/DESC. Hãy map lựa chọn người dùng sang danh sách SQL fragment cố định:

- newest: CREATED_AT DESC, ORDER_ID DESC
- amount_high: TOTAL_AMOUNT DESC, ORDER_ID DESC
- oldest: CREATED_AT ASC, ORDER_ID ASC

Mỗi sort mode cần ORDER BY deterministic với tie-breaker duy nhất, keyset predicate tương ứng nếu dùng seek pagination, index được đánh giá theo workload và cursor token có sort mode để không dùng nhầm cursor với thứ tự khác.

Nếu dùng dynamic SQL, chỉ ghép fragment đã whitelist; mọi giá trị filter và cursor vẫn bind.

## 18. Các vấn đề hiệu năng thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Trang đầu nhanh, trang sâu chậm | OFFSET lớn phải bỏ qua nhiều hàng | Dùng keyset cho luồng tuần tự |
| Cùng hàng xuất hiện ở hai trang | ORDER BY không unique hoặc dữ liệu thay đổi | Thêm tie-breaker, xác định snapshot semantics |
| Một số hàng bị bỏ qua | Concurrent insert/delete/update hoặc cursor predicate sai | Dùng unique sort key và kiểm tra snapshot |
| Top-N vẫn sort nhiều hàng | Không có index phù hợp hoặc filter/selectivity | Xem STOPKEY, index và plan |
| Time query full scan toàn bảng | Predicate không sargable, range quá rộng hoặc table nhỏ | Kiểm tra index, function trên cột, selectivity |
| Partition pruning không xảy ra | Bọc partition key hoặc datatype conversion | Range predicate trực tiếp, bind đúng datatype |
| Query ngày bỏ sót cuối ngày | BETWEEN/END boundary không chính xác | Dùng [start, next_start) |
| Query ngày dùng index kém | TRUNC/TO_CHAR trên cột | Tính boundary trên bind |
| Top-N per group chậm | Phải rank tập dữ liệu lớn | Filter trước, index, partition hoặc summary |
| COUNT OVER làm query chậm | Cần xử lý toàn bộ tập để đếm | Count riêng hoặc fetch thêm một hàng |
| Plan thay đổi sau bind khác | Bind peeking/selectivity khác nhau | Kiểm tra child cursor và bind distribution |
| Index mới làm DML chậm | Nhiều index hoặc index rộng | Đo read benefit so với write cost |

## 19. Đo execution plan thay vì chỉ nhìn SQL

Dùng runtime statistics cho query đại diện:

~~~sql
SELECT /*+ GATHER_PLAN_STATISTICS */
       order_id, created_at, total_amount
FROM orders
WHERE tenant_id = :p_tenant_id
  AND created_at >= :p_start_ts
  AND created_at < :p_end_ts
ORDER BY created_at DESC, order_id DESC
FETCH FIRST 20 ROWS ONLY;
~~~

Sau khi fetch kết quả, hiển thị:

~~~sql
SELECT *
FROM TABLE(
    DBMS_XPLAN.DISPLAY_CURSOR(
        NULL,
        NULL,
        'ALLSTATS LAST +PREDICATE +PARTITION'
    )
);
~~~

Kiểm tra:

- Có INDEX RANGE SCAN hay FULL TABLE SCAN?
- Có SORT ORDER BY STOPKEY hay sort toàn bộ?
- Starts của operation là bao nhiêu?
- A-Rows có gần E-Rows không?
- Buffers và Reads ở đâu cao?
- Pstart/Pstop có prune partition đúng không?
- Predicate có áp dụng trực tiếp trên cột index/partition key không?
- Query có dừng sau đủ N hàng hay phải xử lý nhiều hơn?

Không ép index bằng hint chỉ vì plan đang full scan. Full scan có thể là lựa chọn tốt khi predicate trả về tỷ lệ lớn dữ liệu hoặc bảng nhỏ.

## 20. Quy trình lựa chọn kỹ thuật

### Nếu cần trang số bất kỳ

- Dùng OFFSET/FETCH.
- ORDER BY có tie-breaker duy nhất.
- Giới hạn page size và offset.
- Tạo index phù hợp với equality filters và sort key.
- Đánh giá chi phí ở offset lớn.
- Dùng snapshot SCN nếu các trang phải nhìn cùng một tập dữ liệu.

### Nếu cần cuộn tuần tự qua dữ liệu lớn

- Dùng keyset pagination.
- Cursor chứa đầy đủ sort key cuối trang.
- Predicate phải phản ánh đúng ASC/DESC và NULL ordering.
- Tạo composite index hỗ trợ filter và sort.
- Không tính exact total count nếu không cần.
- Xác định cách xử lý dữ liệu thay đổi giữa các trang.

### Nếu cần Top-N toàn cục

- Dùng FETCH FIRST N ROWS ONLY hoặc WITH TIES.
- Có ORDER BY xác định.
- Tạo index phù hợp với filter + order nếu workload đáng kể.
- Kiểm tra stopkey và sort trong execution plan.

### Nếu cần Top-N theo từng nhóm

- Dùng ROW_NUMBER, RANK hoặc DENSE_RANK với PARTITION BY.
- Chọn hàm theo semantics tie.
- Giảm tập đầu vào trước analytic operation nếu có thể.
- Đánh giá index theo group key và sort key.

### Nếu cần truy vấn thời gian

- Dùng điều kiện half-open: column >= start AND column < end.
- Bind boundary đúng datatype.
- Tính boundary theo timezone nghiệp vụ.
- Không bọc cột thời gian bằng TRUNC/TO_CHAR nếu muốn dùng index/partition pruning.
- Kiểm tra Pstart/Pstop và access path.

## 21. Bài thực hành

Thực hiện trong schema lab, dùng dữ liệu đủ lớn để quan sát khác biệt plan.

### Bài 1 — OFFSET/FETCH

Tạo ORDERS có ít nhất vài trăm nghìn hàng. Lấy trang 1, trang 10 và trang 1.000 với page size 25. So sánh elapsed time và Buffers.

### Bài 2 — Deterministic ordering

Tạo nhiều hàng có CREATED_AT giống nhau. Chạy phân trang chỉ ORDER BY CREATED_AT rồi thêm ORDER_ID. Quan sát thứ tự và giải thích vì sao tie-breaker cần thiết.

### Bài 3 — ROWNUM

Viết Top-N bằng nested query và pagination bằng ROWNUM. Cố ý viết sai bằng cách đặt ROWNUM cùng ORDER BY rồi giải thích kết quả khác nhau.

### Bài 4 — ROW_NUMBER

Viết phân trang bằng ROW_NUMBER và so sánh plan với OFFSET/FETCH trên cùng dữ liệu.

### Bài 5 — Keyset

Lấy trang đầu, giữ CREATED_AT/ORDER_ID của hàng cuối, rồi lấy trang tiếp theo bằng seek predicate. So sánh trang sâu với OFFSET.

### Bài 6 — Concurrent changes

Mở hai session. Session A lấy trang đầu; session B INSERT một hàng mới đứng đầu; session A lấy trang hai bằng OFFSET rồi bằng keyset. Ghi nhận sự khác biệt.

### Bài 7 — Snapshot SCN

Lấy SCN, thực hiện INSERT/DELETE ở session khác, rồi chạy các trang AS OF SCN. So sánh kết quả với query hiện tại.

### Bài 8 — Top-N WITH TIES

Tạo nhiều hàng có TOTAL_AMOUNT trùng tại vị trí thứ N. So sánh ONLY với WITH TIES. Thử thêm ORDER_ID vào ORDER BY và giải thích vì sao tie biến mất.

### Bài 9 — Top-N per group

Dùng ROW_NUMBER để lấy 3 đơn mỗi customer. Thay bằng RANK và DENSE_RANK, so sánh số hàng.

### Bài 10 — Index cho pagination

Tạo index (CUSTOMER_ID, STATUS, CREATED_AT DESC, ORDER_ID DESC). Chạy query có equality filters và sort. Xem execution plan và actual rows.

### Bài 11 — Time range

Tạo hàng có timestamp tại đầu ngày, cuối ngày, fractional second cuối ngày và đúng đầu ngày tiếp theo. So sánh BETWEEN với half-open range.

### Bài 12 — TRUNC và range predicate

Chạy WHERE TRUNC(CREATED_AT) = :day rồi viết lại thành CREATED_AT >= :start AND CREATED_AT < :end. So sánh access path.

### Bài 13 — Partition pruning

Tạo bảng range/interval partition theo ngày hoặc tháng. Truy vấn một khoảng hẹp và xem Pstart/Pstop. Thử bọc partition key bằng hàm và so sánh.

### Bài 14 — Time zone

Tạo boundary cho một ngày theo timezone region có DST. So sánh độ dài ngày 23/24/25 giờ. Xác định hai instant đầu ngày và đầu ngày kế tiếp trước khi query.

### Bài 15 — Count total

So sánh COUNT riêng, COUNT(*) OVER() và fetch thêm page_size + 1. Ghi nhận chi phí và xử lý trang rỗng.

### Bài 16 — Báo cáo tối ưu

Với mỗi truy vấn, ghi dạng pagination/Top-N/time-range, ORDER BY và tie-breaker, predicate và bind datatype, index/partition key liên quan, E-Rows/A-Rows/Starts/Buffers/Reads/A-Time, elapsed time và kết luận về tính nhất quán khi dữ liệu thay đổi.

## 22. Checklist trước khi triển khai

- [ ] Phân biệt pagination, Top-N toàn cục và Top-N theo nhóm.
- [ ] Có ORDER BY deterministic và tie-breaker duy nhất.
- [ ] Chọn OFFSET/FETCH cho nhảy trang hoặc keyset cho duyệt tuần tự.
- [ ] Đánh giá chi phí offset lớn.
- [ ] Với keyset, lưu đầy đủ sort key và xử lý ASC/DESC đúng.
- [ ] Xác định cách xử lý NULL trong sort key.
- [ ] Chọn ROW_NUMBER/RANK/DENSE_RANK theo tie semantics.
- [ ] Dùng WITH TIES chỉ khi cần giữ đồng hạng theo đúng sort key.
- [ ] Dùng khoảng thời gian half-open [start, end).
- [ ] Bind DATE/TIMESTAMP đúng datatype, tránh implicit conversion.
- [ ] Tính boundary theo timezone nghiệp vụ và DST.
- [ ] Không dùng TRUNC/TO_CHAR trên cột thời gian nếu range predicate phù hợp.
- [ ] Kiểm tra partition pruning và Pstart/Pstop.
- [ ] Thiết kế index theo equality filters, range key và ORDER BY.
- [ ] Không tạo index rộng hoặc dư thừa khi chưa đo workload.
- [ ] Xác định yêu cầu exact count hay chỉ cần has-next.
- [ ] Xác định snapshot semantics giữa các trang.
- [ ] Dùng AS OF SCN khi cần duyệt cùng snapshot và undo còn đủ.
- [ ] Kiểm tra execution plan/runtime stats trên dữ liệu đại diện.
- [ ] Kiểm thử concurrent INSERT/UPDATE/DELETE và sort-key changes.

## 23. Ghi nhớ cốt lõi

- Phân trang và Top-N cần ORDER BY xác định; thêm unique tie-breaker để tránh thứ tự không ổn định.
- OFFSET/FETCH đơn giản và phù hợp cho trang gần đầu hoặc nhảy trang, nhưng offset sâu có thể phải bỏ qua nhiều hàng.
- ROWNUM phải được áp dụng ở query block bên ngoài phần ORDER BY; không dùng ROWNUM > n trực tiếp để phân trang.
- ROW_NUMBER đánh số từng hàng; RANK giữ đồng hạng và nhảy vị trí; DENSE_RANK giữ đồng hạng mà không nhảy.
- Top-N per group thường dùng analytic function với PARTITION BY.
- WITH TIES giữ mọi hàng đồng hạng với hàng cuối theo toàn bộ ORDER BY; thêm unique key vào ORDER BY sẽ thay đổi semantics tie.
- Keyset pagination dùng sort key cuối trang làm cursor, thường hiệu quả hơn OFFSET ở trang sâu nếu có index phù hợp.
- Keyset cần cursor đầy đủ, xử lý đúng hướng sort và NULL; nó không tự tạo snapshot nhất quán.
- Mỗi SELECT có read consistency riêng; nếu các trang phải nhìn cùng snapshot, cân nhắc Flashback Query AS OF SCN và giới hạn UNDO.
- Truy vấn thời gian nên dùng khoảng nửa mở: cột >= start AND cột < end.
- DATE lưu đến giây; TIMESTAMP có fractional seconds; không tạo “23:59:59.999999” giả làm end-of-day.
- Tính boundary theo timezone nghiệp vụ; ngày DST có thể dài 23 hoặc 25 giờ.
- Tránh áp dụng TRUNC/TO_CHAR lên cột thời gian; tính boundary trên bind để giữ index range scan và partition pruning.
- Composite index thường đặt equality filters trước range/order columns, nhưng thứ tự cuối cùng phải theo workload và plan.
- Top-N có thể dùng STOPKEY hoặc index order để dừng sớm; kiểm tra DBMS_XPLAN thay vì giả định.
- Exact COUNT có thể làm mất lợi ích dừng sớm; fetch thêm một hàng nếu chỉ cần biết có trang tiếp theo.
- Bind giá trị, whitelist sort field và không ghép input không tin cậy vào SQL/ORDER BY.
- Đo E-Rows, A-Rows, Starts, Buffers, Reads, A-Time và elapsed time trên dữ liệu đại diện trước khi thay đổi production.

### Tài liệu Oracle nên đối chiếu

- [Oracle Database SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html) — ORDER BY, row_limiting_clause, OFFSET, FETCH FIRST, WITH TIES và analytic query syntax.
- [Oracle Database SQL Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgsql/) — Top-N optimization, access paths, index range scans và execution plans.
- [Oracle Database SQL Language Reference — Analytic Functions](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Analytic-Functions.html) — ROW_NUMBER, RANK, DENSE_RANK và PARTITION BY.
- [Oracle Database SQL Language Reference — Datetime Data Types and Time Zone Support](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/) — DATE, TIMESTAMP, time zone conversion và datetime arithmetic.
- [Oracle Database VLDB and Partitioning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/vldbg/) — Range/interval partitioning, partition pruning, local/global indexes.
- [Oracle Database Performance Tuning Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/tgdba/) — Execution plans, runtime statistics và performance measurement.

Row limiting syntax, analytic features, partition behavior and optimizer transformations vary by Oracle release. Check the SQL Language Reference for the deployed version and test deep pages, tied values, time-zone boundaries, concurrent DML and actual execution plans in a representative environment before production rollout.

