# Top-N, ORDER BY/LIMIT và yêu cầu thứ tự ổn định

Bài học thuộc chương **Tối ưu SQL** của module **DATABASE_MYSQL**. Module hướng tới việc làm chủ MySQL từ thiết kế bảng, kiểu dữ liệu, khóa và truy vấn SQL đến index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền, sao lưu và xử lý vấn đề vận hành cơ sở dữ liệu quan hệ. Truy vấn Top-N thường xuất hiện trong bảng xếp hạng, danh sách đơn hàng mới nhất, sản phẩm bán chạy, trang kết quả tìm kiếm và API phân trang. Muốn kết quả đúng và ổn định, cần xác định rõ tiêu chí sắp xếp, xử lý các giá trị bằng nhau, thiết kế index phù hợp và chọn cách phân trang theo quy mô dữ liệu.

Sau bài này, bạn có thể viết truy vấn Top-N có thứ tự xác định, phân biệt lấy đúng N hàng với lấy tất cả hàng đồng hạng, thiết kế composite index cho WHERE + ORDER BY + LIMIT, hiểu LIMIT optimization và filesort, dùng ROW_NUMBER/RANK cho Top-N theo nhóm, thay OFFSET sâu bằng keyset pagination và kiểm chứng kế hoạch bằng EXPLAIN ANALYZE.

## 1. Top-N là gì?

Top-N là truy vấn lấy N hàng đứng đầu theo một tiêu chí xếp hạng hoặc sắp xếp.

Ví dụ:

- 10 đơn hàng có giá trị cao nhất.
- 20 đơn hàng mới nhất của một khách hàng.
- 5 sản phẩm bán chạy nhất trong một danh mục.
- 3 giao dịch lớn nhất của từng tài khoản.
- Trang đầu tiên gồm 25 bản ghi trong danh sách tìm kiếm.

Cấu trúc cơ bản:

~~~sql
SELECT
    order_id,
    customer_id,
    total_amount,
    created_at
FROM orders
WHERE status = 'PAID'
ORDER BY total_amount DESC
LIMIT 10;
~~~

Ý nghĩa:

- WHERE xác định tập hàng đủ điều kiện.
- ORDER BY xác định thứ tự của tập hàng.
- LIMIT 10 yêu cầu tối đa 10 hàng đầu tiên theo thứ tự đó.

LIMIT không tự xác định hàng nào là “đầu tiên”. Nếu không có ORDER BY, MySQL được phép trả về bất kỳ 10 hàng phù hợp nào. Thứ tự vật lý, thứ tự index, execution plan hoặc lần chạy trước không phải hợp đồng về thứ tự kết quả.

Không viết:

~~~sql
SELECT *
FROM orders
LIMIT 10;
~~~

nếu nghiệp vụ yêu cầu “10 đơn mới nhất”, “10 đơn lớn nhất” hoặc một tập kết quả có thứ tự xác định.

## 2. ORDER BY phải tạo ra thứ tự xác định

Một ORDER BY chỉ xác định thứ tự theo những biểu thức được liệt kê. Nếu nhiều hàng có cùng giá trị ở tất cả các biểu thức đó, MySQL không cam kết thứ tự giữa các hàng đồng hạng.

Ví dụ:

~~~sql
SELECT
    order_id,
    customer_id,
    total_amount
FROM orders
ORDER BY total_amount DESC
LIMIT 5;
~~~

Nếu nhiều đơn có cùng total_amount, thứ tự giữa các đơn đó không được xác định. Khi execution plan thay đổi, kết quả có thể đổi thứ tự hoặc một hàng ở ranh giới Top-5 có thể bị thay bằng hàng đồng hạng khác.

### Thêm khóa phụ duy nhất

Giải pháp thông dụng là thêm primary key hoặc một khóa duy nhất vào cuối ORDER BY:

~~~sql
SELECT
    order_id,
    customer_id,
    total_amount
FROM orders
ORDER BY
    total_amount DESC,
    order_id DESC
LIMIT 5;
~~~

Ở đây:

1. Đơn có total_amount lớn hơn đứng trước.
2. Nếu hai đơn có cùng total_amount, order_id lớn hơn đứng trước.
3. Vì order_id là duy nhất, hai hàng bất kỳ không còn đồng hạng theo toàn bộ ORDER BY.

Đây là **thứ tự xác định** (deterministic ordering). Cùng một tập dữ liệu và cùng điều kiện truy vấn sẽ có cùng thứ tự logic.

Khóa phụ nên là cột:

- Duy nhất trong tập kết quả.
- Không NULL nếu có thể.
- Ổn định, ít thay đổi.
- Phù hợp với hướng sắp xếp và cursor phân trang.

Primary key thường là lựa chọn tốt. Nếu khóa chính là khóa ghép, có thể dùng toàn bộ các cột cần thiết để phân biệt hàng.

### Vì sao LIMIT làm lộ lỗi thứ tự không ổn định?

MySQL có thể chọn kế hoạch khác nhau cho truy vấn có và không có LIMIT. Ví dụ, truy vấn không LIMIT dùng một cách đọc dữ liệu, còn truy vấn có LIMIT dùng index khác hoặc tối ưu Top-N. Khi ORDER BY có các giá trị bằng nhau, các hàng đồng hạng có thể xuất hiện theo thứ tự khác nhau.

Do đó, không được giả định rằng:

~~~sql
SELECT *
FROM ratings
ORDER BY category;
~~~

và:

~~~sql
SELECT *
FROM ratings
ORDER BY category
LIMIT 5;
~~~

luôn giữ nguyên thứ tự tương đối của mọi hàng trong từng category. Nếu cần thứ tự ổn định, hãy viết:

~~~sql
SELECT *
FROM ratings
ORDER BY category, rating DESC, id
LIMIT 5;
~~~

Trong đó id phải duy nhất để phá hòa cuối cùng.

## 3. LIMIT lấy đúng N hàng hay lấy cả nhóm đồng hạng?

Cần xác định ý nghĩa nghiệp vụ trước khi viết truy vấn.

### Lấy tối đa N hàng

Nếu yêu cầu là “lấy đúng 10 sản phẩm đầu tiên”, dùng LIMIT với thứ tự đầy đủ:

~~~sql
SELECT
    product_id,
    product_name,
    sold_quantity
FROM products
ORDER BY sold_quantity DESC, product_id
LIMIT 10;
~~~

Kết quả có tối đa 10 hàng. Nếu hàng thứ 10 và hàng thứ 11 có cùng sold_quantity, khóa phụ product_id quyết định hàng nào đứng trước.

### Lấy tất cả hàng có cùng hạng

Nếu yêu cầu là “lấy tất cả sản phẩm đồng hạng trong Top 10”, LIMIT 10 không diễn đạt đúng nghiệp vụ. Có thể dùng RANK() để xác định hạng:

~~~sql
WITH ranked_products AS (
    SELECT
        product_id,
        product_name,
        sold_quantity,
        RANK() OVER (
            ORDER BY sold_quantity DESC
        ) AS sales_rank
    FROM products
)
SELECT
    product_id,
    product_name,
    sold_quantity,
    sales_rank
FROM ranked_products
WHERE sales_rank <= 10
ORDER BY sold_quantity DESC, product_id;
~~~

RANK() cho các hàng có cùng sold_quantity cùng hạng và bỏ qua số hạng kế tiếp. Vì vậy, kết quả có thể nhiều hơn 10 hàng nếu có đồng hạng ở ranh giới.

Không thêm product_id vào ORDER BY bên trong RANK() nếu mục tiêu là giữ các sản phẩm cùng sold_quantity đồng hạng. Nếu thêm khóa phụ duy nhất vào biểu thức xếp hạng, mỗi hàng sẽ trở thành một hạng riêng.

### Phân biệt ROW_NUMBER, RANK và DENSE_RANK

| Hàm | Cách xử lý đồng hạng | Phù hợp với |
|---|---|---|
| ROW_NUMBER() | Mỗi hàng có số thứ tự riêng | Lấy chính xác N hàng mỗi nhóm, có tie-breaker |
| RANK() | Hàng bằng nhau cùng hạng, hạng kế tiếp bị nhảy | Lấy tất cả hàng có thứ hạng <= N |
| DENSE_RANK() | Hàng bằng nhau cùng hạng, hạng kế tiếp không bị nhảy | Lấy N mức giá trị/hạng khác nhau |

Ví dụ giá trị giảm dần: 100, 90, 90, 80.

| Giá trị | ROW_NUMBER | RANK | DENSE_RANK |
|---:|---:|---:|---:|
| 100 | 1 | 1 | 1 |
| 90 | 2 | 2 | 2 |
| 90 | 3 | 2 | 2 |
| 80 | 4 | 4 | 3 |

Dùng ROW_NUMBER khi cần số lượng hàng chính xác. Dùng RANK hoặc DENSE_RANK khi đồng hạng là một phần của quy tắc nghiệp vụ.

## 4. Top-N theo một nhóm và Top-N toàn cục

Top-N toàn cục lấy N hàng tốt nhất trên toàn bộ tập kết quả. Top-N theo nhóm lấy N hàng tốt nhất trong từng nhóm độc lập.

### Top-N toàn cục

~~~sql
SELECT
    order_id,
    customer_id,
    total_amount
FROM orders
WHERE status = 'PAID'
ORDER BY total_amount DESC, order_id DESC
LIMIT 10;
~~~

Kết quả có tối đa 10 đơn hàng trên toàn bộ bảng.

### Top-N theo từng khách hàng

Ví dụ lấy 3 đơn hàng có giá trị cao nhất của mỗi khách hàng:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        total_amount,
        created_at,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY total_amount DESC, order_id DESC
        ) AS row_num
    FROM orders
    WHERE status = 'PAID'
)
SELECT
    order_id,
    customer_id,
    total_amount,
    created_at
FROM ranked_orders
WHERE row_num <= 3
ORDER BY customer_id, row_num;
~~~

PARTITION BY customer_id chia dữ liệu thành các nhóm độc lập. ROW_NUMBER đánh số đơn hàng trong từng nhóm. Truy vấn ngoài lọc ba hàng đầu mỗi nhóm.

Nếu muốn lấy tất cả đơn đồng hạng trong Top 3, thay ROW_NUMBER bằng RANK và bỏ khóa phụ khỏi ORDER BY bên trong hàm xếp hạng:

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        total_amount,
        RANK() OVER (
            PARTITION BY customer_id
            ORDER BY total_amount DESC
        ) AS amount_rank
    FROM orders
    WHERE status = 'PAID'
)
SELECT
    order_id,
    customer_id,
    total_amount,
    amount_rank
FROM ranked_orders
WHERE amount_rank <= 3
ORDER BY customer_id, total_amount DESC, order_id DESC;
~~~

Thứ tự ở truy vấn ngoài vẫn có thể dùng khóa phụ để hiển thị ổn định. Khóa phụ không cần xuất hiện trong ORDER BY của RANK nếu muốn giữ đồng hạng theo total_amount.

## 5. LIMIT optimization hoạt động thế nào?

LIMIT giúp MySQL tránh làm nhiều việc hơn mức cần thiết trong một số trường hợp.

Nếu truy vấn có thể đọc dữ liệu theo đúng thứ tự từ index, MySQL có thể đọc index, lấy hàng phù hợp và dừng khi đã có đủ N hàng.

Ví dụ:

~~~sql
SELECT
    order_id,
    created_at,
    total_amount
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Nếu index phù hợp với status, created_at và order_id, MySQL có thể:

1. Tìm vùng index có status = 'PAID'.
2. Đọc theo thứ tự created_at DESC, order_id DESC.
3. Lấy 20 hàng đầu tiên.
4. Dừng mà không phải đọc hết các đơn PAID.

Đây là trường hợp Top-N có thể rất hiệu quả.

### Khi không có index đáp ứng ORDER BY

Nếu index không thể cung cấp thứ tự cần thiết, MySQL có thể dùng filesort.

Ví dụ:

~~~sql
SELECT
    order_id,
    created_at,
    total_amount
FROM orders
WHERE status = 'PAID'
ORDER BY total_amount DESC, order_id DESC
LIMIT 20;
~~~

Nếu không có index phù hợp cho điều kiện và thứ tự, MySQL phải tìm các hàng thỏa status, sau đó sắp xếp theo total_amount và order_id để chọn Top-20.

LIMIT có thể giúp thuật toán sắp xếp chỉ giữ các ứng viên tốt nhất thay vì sắp xếp toàn bộ kết quả hoàn chỉnh. Tuy nhiên, MySQL vẫn phải xét các hàng phù hợp để biết hàng nào thuộc Top-20. LIMIT không đồng nghĩa chỉ đọc 20 hàng từ bảng.

### Filesort không có nghĩa chắc chắn ghi ra đĩa

Tên filesort là tên thuật toán sắp xếp của MySQL. Nó có thể dùng bộ nhớ nếu dữ liệu vừa với sort buffer; khi cần, MySQL có thể dùng file tạm và nhiều lượt merge.

Trong EXPLAIN:

- Có Using filesort: MySQL cần một bước sắp xếp bổ sung; chưa đủ để kết luận sort đã ghi ra đĩa.
- Không có Using filesort: MySQL không dùng filesort cho thứ tự đó, thường vì có thể đọc theo index hoặc dùng một kế hoạch khác đáp ứng thứ tự.

Muốn biết sort có dùng file tạm hay không, cần xem thêm optimizer trace, số merge pass, bộ nhớ và thực tế vận hành. Đừng tăng sort_buffer_size chỉ vì thấy chữ filesort.

## 6. Thiết kế composite index cho WHERE + ORDER BY + LIMIT

Một index phù hợp có thể giúp truy vấn Top-N tránh bước sort và dừng sớm.

Giả sử truy vấn:

~~~sql
SELECT
    order_id,
    created_at,
    total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Một index có thể cân nhắc:

~~~sql
CREATE INDEX idx_orders_tenant_status_created_id
ON orders (
    tenant_id,
    status,
    created_at,
    order_id
);
~~~

Lý do sắp xếp cột:

1. tenant_id được lọc bằng phép bằng.
2. status được lọc bằng phép bằng.
3. created_at là cột sắp xếp chính.
4. order_id là tie-breaker duy nhất.

Khi hai cột đầu được cố định bởi điều kiện WHERE, phần còn lại của index có thứ tự theo created_at và order_id. MySQL có thể quét ngược index để lấy DESC cho cả hai cột.

### Leftmost prefix

Composite index (a, b, c) có thứ tự từ trái sang phải. MySQL thường khai thác hiệu quả các phần đầu liên tiếp của index.

Ví dụ index:

~~~sql
CREATE INDEX idx_orders_status_created_id
ON orders (status, created_at, order_id);
~~~

Có thể hỗ trợ các truy vấn:

~~~sql
WHERE status = 'PAID'
~~~

~~~sql
WHERE status = 'PAID'
ORDER BY created_at DESC, order_id DESC
~~~

Nhưng truy vấn chỉ lọc theo created_at mà không có status không thể mặc định khai thác index như khi có cột status ở đầu.

### Equality columns trước, sort columns sau

Một quy tắc thiết kế hữu ích:

- Các cột lọc bằng nhau thường đứng trước.
- Các cột dùng để sắp xếp đứng tiếp theo.
- Cột tie-breaker duy nhất đứng cuối.

Ví dụ:

~~~sql
CREATE INDEX idx_feed
ON activity_feed (
    account_id,
    visibility,
    published_at,
    activity_id
);
~~~

Truy vấn:

~~~sql
SELECT
    activity_id,
    published_at,
    title
FROM activity_feed
WHERE account_id = 42
  AND visibility = 'PUBLIC'
ORDER BY published_at DESC, activity_id DESC
LIMIT 30;
~~~

Tuy nhiên, đây là quy tắc khởi đầu, không phải bảo đảm optimizer sẽ luôn chọn index. Nếu WHERE có range condition, IN nhiều giá trị, JOIN, hoặc ORDER BY dùng cột từ nhiều bảng, thứ tự index cần được đánh giá lại bằng EXPLAIN.

### Index có thể bao phủ truy vấn

Nếu SELECT chỉ lấy các cột có trong index, MySQL có thể đọc dữ liệu từ index mà không cần truy cập thêm hàng clustered record. Đây là covering index.

Ví dụ:

~~~sql
CREATE INDEX idx_orders_topn_cover
ON orders (
    status,
    total_amount,
    order_id,
    customer_id
);
~~~

Truy vấn:

~~~sql
SELECT
    order_id,
    customer_id,
    total_amount
FROM orders
WHERE status = 'PAID'
ORDER BY total_amount DESC, order_id DESC
LIMIT 20;
~~~

Có thể được phục vụ hoàn toàn từ index nếu kế hoạch và điều kiện phù hợp.

Đổi lại, index rộng hơn tốn dung lượng và làm INSERT/UPDATE/DELETE đắt hơn. Chỉ thêm cột để covering khi lợi ích đọc được đo đạc rõ ràng.

## 7. ASC, DESC và khác biệt theo phiên bản

MySQL có thể đọc B-tree index theo chiều thuận hoặc chiều ngược để đáp ứng thứ tự.

- Trong MySQL 5.7, từ khóa ASC/DESC trong định nghĩa index được parser chấp nhận nhưng bị bỏ qua; các key part vẫn được lưu theo thứ tự tăng dần.
- Từ MySQL 8.0, InnoDB hỗ trợ descending index thực sự. DESC trong định nghĩa index làm giá trị key được lưu theo chiều giảm dần.
- Descending index có ích khi thứ tự nhiều cột trộn ASC và DESC hoặc muốn đọc theo chiều thuận của index.
- Descending index chỉ được hỗ trợ cho InnoDB, không áp dụng cho FULLTEXT hoặc SPATIAL index.

Ví dụ MySQL 8.0 trở lên:

~~~sql
CREATE INDEX idx_orders_mixed_sort
ON orders (
    status ASC,
    priority DESC,
    created_at ASC,
    order_id DESC
);
~~~

Có thể hỗ trợ:

~~~sql
SELECT
    order_id,
    priority,
    created_at
FROM orders
WHERE status = 'PAID'
ORDER BY priority DESC, created_at ASC, order_id DESC
LIMIT 20;
~~~

Với thứ tự toàn bộ cùng chiều, một index tăng dần có thể được quét ngược để trả về toàn bộ DESC. Với thứ tự trộn chiều, descending index giúp optimizer có thêm cách quét phù hợp.

Không tạo cả index ASC và DESC theo thói quen. Hãy xác định truy vấn thực tế, phiên bản MySQL và kế hoạch trước khi thêm index.

## 8. OFFSET pagination và chi phí khi trang càng sâu

Cú pháp phổ biến:

~~~sql
SELECT
    order_id,
    created_at,
    total_amount
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 20 OFFSET 100000;
~~~

Hoặc dạng tương đương:

~~~sql
LIMIT 100000, 20
~~~

Truy vấn yêu cầu bỏ qua 100.000 hàng đầu tiên rồi trả 20 hàng tiếp theo.

Ngay cả khi index hỗ trợ ORDER BY, MySQL vẫn phải đi qua các hàng bị bỏ qua để đến vị trí cần lấy. Vì vậy, chi phí thường tăng theo OFFSET.

Nếu không có index phù hợp và phải filesort, việc tìm trang sâu còn tốn kém hơn do phải xử lý tập hàng phù hợp trước khi bỏ qua phần đầu.

OFFSET phù hợp khi:

- Số trang nhỏ.
- Bảng kết quả không quá lớn.
- Giao diện cần nhảy trực tiếp đến một số trang cụ thể.
- Chi phí đã được đo và chấp nhận.

Với danh sách lớn, cuộn liên tục hoặc API tải thêm, keyset pagination thường phù hợp hơn.

## 9. Keyset pagination: tiếp tục từ hàng cuối trang trước

Keyset pagination dùng giá trị sắp xếp của hàng cuối trang trước làm cursor. Truy vấn tiếp theo chỉ tìm các hàng đứng sau cursor theo thứ tự đã xác định.

Giả sử thứ tự:

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

Trang đầu:

~~~sql
SELECT
    order_id,
    created_at,
    total_amount
FROM orders
WHERE status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Giả sử hàng cuối trang đầu có:

- created_at = '2026-11-10 10:30:00'
- order_id = 5000

Trang tiếp theo:

~~~sql
SELECT
    order_id,
    created_at,
    total_amount
FROM orders
WHERE status = 'PAID'
  AND (
      created_at < '2026-11-10 10:30:00'
      OR (
          created_at = '2026-11-10 10:30:00'
          AND order_id < 5000
      )
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Điều kiện cursor có nghĩa:

- Lấy hàng có created_at cũ hơn.
- Hoặc cùng created_at nhưng order_id nhỏ hơn.
- Sắp xếp theo đúng thứ tự ban đầu.
- Lấy 20 hàng tiếp theo.

Không dùng riêng created_at làm cursor nếu nhiều hàng có thể cùng thời điểm. Nếu bỏ order_id, các hàng cùng timestamp ở ranh giới trang có thể bị bỏ sót hoặc lặp.

### Cursor phải chứa đủ các cột ORDER BY

Nếu thứ tự là:

~~~sql
ORDER BY priority DESC, created_at ASC, order_id DESC
~~~

Cursor phải mang cả ba giá trị và điều kiện tiếp tục phải phản ánh đúng thứ tự hỗn hợp. Không thể chỉ so sánh một cột đầu tiên.

Với cột nullable, phép so sánh < hoặc > có thể trả UNKNOWN khi gặp NULL. Thiết kế cursor đơn giản nhất nên dùng các cột NOT NULL. Nếu nghiệp vụ cho phép NULL, cần định nghĩa rõ vị trí NULL trong thứ tự và đưa điều kiện NULL vào cursor.

### Keyset pagination có thể dùng tuple comparison

Khi tất cả các cột cursor có cùng chiều và không NULL, có thể viết gọn:

~~~sql
WHERE (created_at, order_id)
    < ('2026-11-10 10:30:00', 5000)
~~~

Cách viết điều kiện tường minh bằng OR giúp người đọc thấy rõ thứ tự từ điển. Hãy kiểm tra kế hoạch và hiệu năng trên phiên bản MySQL cùng index thực tế.

### Keyset không phải snapshot bất biến

Keyset pagination giảm chi phí bỏ qua hàng và giảm tình trạng lặp/nhảy trang do OFFSET khi dữ liệu mới được chèn ở đầu danh sách. Nhưng nó không đóng băng toàn bộ tập dữ liệu qua nhiều request.

Nếu các hàng cũ bị xóa hoặc cột sắp xếp bị cập nhật, kết quả giữa các trang vẫn có thể thay đổi. Nếu cần một danh sách nhất quán tại một thời điểm, phải thiết kế thêm snapshot/high-water mark, phiên đọc nhất quán hoặc cơ chế phiên bản dữ liệu phù hợp.

## 10. Top-N và phân trang có dữ liệu thay đổi đồng thời

Ngay cả khi ORDER BY có tie-breaker duy nhất, dữ liệu vẫn có thể thay đổi giữa hai lần gọi API.

Ví dụ:

1. Người dùng tải trang 1.
2. Một đơn hàng mới được chèn với created_at mới nhất.
3. Người dùng tải trang 2 bằng OFFSET.
4. Các hàng dịch chuyển vị trí, có thể gây lặp hoặc bỏ sót ở ranh giới trang.

Keyset pagination tránh việc phải đếm bỏ qua một số lượng hàng cố định. Cursor tiếp tục từ giá trị cuối của trang trước, nên hàng mới được chèn ở đầu danh sách không đẩy cursor lùi về vị trí cũ.

Tuy vậy, nếu một hàng được cập nhật để chuyển từ sau cursor lên trước cursor hoặc ngược lại, nó vẫn có thể thay đổi vị trí. Đối với báo cáo cần snapshot chính xác, hãy xác định thời điểm chốt dữ liệu và điều kiện lọc theo thời điểm đó.

Một cách thường dùng là thêm high-water mark, ví dụ chỉ lấy các hàng có sequence/id không vượt quá giá trị lớn nhất ghi nhận khi mở phiên phân trang. Cách này chỉ đúng nếu khóa đó phản ánh được ranh giới dữ liệu mong muốn và không bị cập nhật lại.

## 11. Top-N và index: kiểm tra bằng EXPLAIN

Đừng chỉ nhìn câu SQL để kết luận index có được dùng. Kiểm tra kế hoạch.

~~~sql
EXPLAIN
SELECT
    order_id,
    customer_id,
    created_at,
    total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

Các thông tin cần xem:

| Trường | Câu hỏi |
|---|---|
| type/access_type | MySQL dùng const, ref, range, index hay ALL? |
| possible_keys | Những index nào có thể dùng? |
| key | Index nào thực sự được chọn? |
| rows | Ước lượng bao nhiêu hàng cần đọc? |
| filtered | Tỷ lệ hàng còn lại sau điều kiện lọc? |
| Extra | Có Using filesort, Using index hoặc Using index condition không? |

Nếu thấy Using filesort, MySQL phải thực hiện bước sort bổ sung. Điều đó chưa chứng minh truy vấn chậm; sort có thể nhỏ và nằm trong bộ nhớ. Cần đo số hàng, thời gian và lượng dữ liệu thực tế.

### EXPLAIN ANALYZE

~~~sql
EXPLAIN ANALYZE
SELECT
    order_id,
    customer_id,
    created_at,
    total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 20;
~~~

EXPLAIN ANALYZE thực thi câu SELECT và hiển thị số hàng, số vòng lặp, thời gian thực tế của các iterator. So sánh:

- Số hàng optimizer ước lượng.
- Số hàng iterator thực tế đọc/trả.
- Thời gian tại từng bước.
- Số vòng lặp.
- Có bước sort hoặc materialize hay không.

Chỉ chạy EXPLAIN ANALYZE trên truy vấn có thể thực thi an toàn. Đây không phải lệnh chỉ đọc metadata hoặc chỉ phân tích cú pháp.

### prefer_ordering_index

Optimizer có thể ưu tiên index cung cấp thứ tự cho truy vấn có ORDER BY/LIMIT nếu ước lượng cho rằng cách đó nhanh hơn. Hành vi này được điều khiển bởi flag prefer_ordering_index trong optimizer_switch.

Kiểm tra:

~~~sql
SELECT @@optimizer_switch;
~~~

Có thể tắt trong session để chẩn đoán và so sánh kế hoạch:

~~~sql
SET SESSION optimizer_switch = 'prefer_ordering_index=off';
~~~

Sau khi so sánh, khôi phục trạng thái ban đầu hoặc đóng session thử nghiệm. Không tắt flag trên production chỉ vì một truy vấn có kết quả EXPLAIN không như mong đợi. Trước hết kiểm tra thống kê, selectivity, index và chi phí thực tế.

## 12. Các mẫu truy vấn dễ gây vấn đề

### ORDER BY không có tie-breaker

~~~sql
SELECT *
FROM products
ORDER BY rating DESC
LIMIT 20;
~~~

Nếu nhiều sản phẩm cùng rating, thứ tự giữa chúng không ổn định.

Sửa:

~~~sql
SELECT *
FROM products
ORDER BY rating DESC, product_id
LIMIT 20;
~~~

### LIMIT không có ORDER BY

~~~sql
SELECT *
FROM orders
LIMIT 20;
~~~

Không xác định 20 hàng nào được trả về. Chỉ dùng nếu bất kỳ 20 hàng nào cũng đáp ứng nghiệp vụ.

### OFFSET quá lớn

~~~sql
SELECT *
FROM events
ORDER BY event_time DESC, event_id DESC
LIMIT 50 OFFSET 500000;
~~~

Thay bằng keyset khi giao diện tải tuần tự:

~~~sql
SELECT *
FROM events
WHERE (event_time, event_id)
    < ('2026-11-10 10:30:00', 5000)
ORDER BY event_time DESC, event_id DESC
LIMIT 50;
~~~

### ORDER BY biểu thức không có index phù hợp

~~~sql
SELECT *
FROM orders
ORDER BY DATE(created_at) DESC
LIMIT 20;
~~~

Hàm DATE() làm thứ tự không còn trùng trực tiếp với cột index created_at. Nếu nghiệp vụ chỉ cần sắp xếp theo ngày, cân nhắc cột generated hoặc functional index phù hợp với phiên bản MySQL; nếu cần chính xác thời điểm, ORDER BY created_at thường giữ được khả năng tận dụng index tốt hơn.

### ORDER BY RAND()

~~~sql
SELECT *
FROM products
ORDER BY RAND()
LIMIT 10;
~~~

Cách này thường phải tạo giá trị ngẫu nhiên và sắp xếp trên tập lớn. Với bảng lớn, không nên dùng làm cơ chế lấy mẫu ngẫu nhiên hiệu năng cao. Hãy cân nhắc chiến lược lấy mẫu theo khóa, random key hoặc bảng mẫu tùy yêu cầu phân bố.

## 13. Bài thực hành: Top-N và pagination ổn định

Bài lab tạo dữ liệu có nhiều hàng trùng giá trị để quan sát tie-breaker, index, OFFSET và keyset pagination.

### Bước 1: tạo database và bảng

~~~sql
CREATE DATABASE IF NOT EXISTS mysql_topn_lab;
USE mysql_topn_lab;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    customer_id INT NOT NULL,
    tenant_id INT NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at DATETIME NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL
) ENGINE=InnoDB;
~~~

### Bước 2: nạp dữ liệu mẫu

~~~sql
INSERT INTO orders
    (order_id, customer_id, tenant_id, status, created_at, total_amount)
VALUES
    (1001, 1, 10, 'PAID', '2026-11-10 10:30:00', 500.00),
    (1002, 1, 10, 'PAID', '2026-11-10 10:30:00', 500.00),
    (1003, 2, 10, 'PAID', '2026-11-10 10:29:00', 900.00),
    (1004, 2, 10, 'PAID', '2026-11-10 10:28:00', 200.00),
    (1005, 1, 10, 'PAID', '2026-11-10 10:27:00', 500.00),
    (1006, 3, 10, 'PENDING', '2026-11-10 10:26:00', 950.00),
    (1007, 3, 10, 'PAID', '2026-11-10 10:25:00', 900.00),
    (1008, 2, 10, 'PAID', '2026-11-10 10:24:00', 300.00),
    (1009, 1, 10, 'PAID', '2026-11-10 10:23:00', 500.00),
    (1010, 3, 10, 'PAID', '2026-11-10 10:22:00', 100.00),
    (1011, 1, 10, 'PAID', '2026-11-10 10:21:00', 900.00),
    (1012, 2, 10, 'PAID', '2026-11-10 10:20:00', 200.00),
    (1013, 2, 20, 'PAID', '2026-11-10 10:19:00', 990.00),
    (1014, 3, 10, 'PAID', '2026-11-10 10:18:00', 300.00),
    (1015, 1, 10, 'PAID', '2026-11-10 10:17:00', 900.00);
~~~

Có nhiều đơn cùng thời điểm hoặc cùng total_amount để kiểm tra thứ tự đồng hạng.

### Bước 3: chạy Top-N không có tie-breaker

~~~sql
SELECT
    order_id,
    total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY total_amount DESC
LIMIT 5;
~~~

Quan sát các đơn có total_amount bằng nhau. Thứ tự giữa chúng không được bảo đảm.

### Bước 4: thêm tie-breaker duy nhất

~~~sql
SELECT
    order_id,
    total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY total_amount DESC, order_id DESC
LIMIT 5;
~~~

Kết quả được xác định theo total_amount giảm dần, sau đó order_id giảm dần.

### Bước 5: tạo index cho Top-N

~~~sql
CREATE INDEX idx_orders_tenant_status_amount_id
ON orders (
    tenant_id,
    status,
    total_amount,
    order_id
);
~~~

Chạy lại:

~~~sql
EXPLAIN
SELECT
    order_id,
    total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY total_amount DESC, order_id DESC
LIMIT 5;
~~~

Kiểm tra index được chọn và có còn Using filesort hay không. Với dữ liệu rất nhỏ, optimizer có thể chọn kế hoạch khác do chi phí ước lượng; mục tiêu là hiểu điều kiện index có thể đáp ứng, không ép một kết quả EXPLAIN cố định.

### Bước 6: Top-N theo từng khách hàng

~~~sql
WITH ranked_orders AS (
    SELECT
        order_id,
        customer_id,
        total_amount,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY total_amount DESC, order_id DESC
        ) AS row_num
    FROM orders
    WHERE tenant_id = 10
      AND status = 'PAID'
)
SELECT
    order_id,
    customer_id,
    total_amount,
    row_num
FROM ranked_orders
WHERE row_num <= 2
ORDER BY customer_id, row_num;
~~~

Mỗi khách hàng có tối đa hai đơn hàng.

### Bước 7: OFFSET pagination

~~~sql
SELECT
    order_id,
    created_at,
    total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 5 OFFSET 5;
~~~

Thử thay OFFSET bằng 0, 5 và 10. Ghi nhận số hàng cần đi qua tăng theo độ sâu trang.

### Bước 8: tạo index cho thứ tự thời gian

~~~sql
CREATE INDEX idx_orders_tenant_status_created_id
ON orders (
    tenant_id,
    status,
    created_at,
    order_id
);
~~~

Truy vấn trang đầu:

~~~sql
SELECT
    order_id,
    created_at,
    total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
~~~

Lấy created_at và order_id của hàng cuối cùng làm cursor. Với dữ liệu mẫu, sau khi kiểm tra kết quả trang đầu, dùng đúng giá trị cursor thực tế ở truy vấn trang tiếp theo.

### Bước 9: keyset pagination

Với truy vấn trang đầu ở bước 8, năm hàng đầu theo thứ tự là 1002, 1001, 1003, 1004 và 1005. Vì vậy hàng cuối trang có created_at = '2026-11-10 10:27:00' và order_id = 1005. Dùng chính hai giá trị này làm cursor:

~~~sql
SELECT
    order_id,
    created_at,
    total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
  AND (
      created_at < '2026-11-10 10:27:00'
      OR (
          created_at = '2026-11-10 10:27:00'
          AND order_id < 1005
      )
  )
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
~~~

Đối chiếu kết quả với trang tiếp theo của OFFSET khi dữ liệu không thay đổi. Sau đó thử chèn một đơn mới có created_at lớn hơn cursor và quan sát khác biệt giữa OFFSET và keyset.

### Bước 10: so sánh EXPLAIN ANALYZE

~~~sql
EXPLAIN ANALYZE
SELECT
    order_id,
    created_at,
    total_amount
FROM orders
WHERE tenant_id = 10
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 5;
~~~

Ghi lại actual rows, loops và thời gian. Thử bỏ index hoặc thay đổi điều kiện lọc trên một môi trường lab mới nếu muốn so sánh filesort và ordered index scan.

### Dọn dẹp

~~~sql
DROP DATABASE mysql_topn_lab;
~~~

Chỉ chạy trên database lab vừa tạo. Lệnh này xóa toàn bộ bảng và dữ liệu thực hành.

## 14. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Kết quả Top-N thay đổi giữa các lần chạy | ORDER BY chưa xác định thứ tự giữa các hàng đồng hạng | Thêm khóa phụ duy nhất |
| Trang 2 lặp hoặc bỏ sót hàng | OFFSET bị ảnh hưởng khi dữ liệu thay đổi trước vị trí trang | Dùng keyset và cursor đầy đủ |
| Truy vấn Top-N vẫn đọc nhiều hàng | Không có index đáp ứng WHERE + ORDER BY hoặc phải filesort | Thiết kế composite index và kiểm tra EXPLAIN ANALYZE |
| Thấy Using filesort và cho rằng chắc chắn ghi đĩa | Nhầm tên thuật toán với việc dùng file tạm | Kiểm tra sort buffer, optimizer trace và merge pass |
| LIMIT 10 trả ít hơn 10 hàng | Có ít hơn 10 hàng phù hợp hoặc truy vấn có điều kiện khác | Kiểm tra WHERE, JOIN, DISTINCT và dữ liệu |
| Top 3 trả hơn 3 hàng | Dùng RANK để giữ đồng hạng | Dùng ROW_NUMBER nếu cần đúng tối đa 3 hàng |
| Top-N theo nhóm chỉ trả N hàng toàn cục | Dùng LIMIT thay vì window partition | Dùng ROW_NUMBER() OVER (PARTITION BY ...) |
| Index có nhưng optimizer không dùng | Chi phí index scan cao, filter không chọn lọc hoặc thứ tự index không khớp | Đọc key, rows, filtered và actual plan |
| Index không đáp ứng ORDER BY | Cột lọc/sort sai thứ tự, có expression hoặc sort trộn chiều | Thiết kế lại composite index, cân nhắc descending index |
| OFFSET sâu chậm | Server phải đi qua nhiều hàng bị bỏ qua | Chuyển sang keyset pagination |
| Keyset bị lặp khi timestamp trùng | Cursor chỉ chứa timestamp | Thêm primary key vào ORDER BY và cursor |
| Keyset không xử lý đúng NULL | So sánh cursor với NULL trả UNKNOWN | Dùng cột NOT NULL hoặc định nghĩa rõ quy tắc NULL |
| Thứ tự thay đổi sau khi thêm index | ORDER BY không có tie-breaker | Hoàn thiện ORDER BY, không dựa vào thứ tự vật lý |

## 15. Checklist trước khi phát hành truy vấn Top-N

- [ ] Đã xác định Top-N toàn cục hay Top-N theo từng nhóm.
- [ ] Đã xác định cần đúng N hàng hay cần giữ tất cả hàng đồng hạng.
- [ ] Có ORDER BY rõ ràng.
- [ ] ORDER BY có khóa phụ duy nhất để phá hòa.
- [ ] Tie-breaker có giá trị ổn định và không NULL nếu phù hợp.
- [ ] Điều kiện WHERE đã được áp dụng đúng trước khi xếp hạng.
- [ ] Đã cân nhắc ROW_NUMBER, RANK hoặc DENSE_RANK theo nghiệp vụ.
- [ ] Đã kiểm tra index theo thứ tự cột lọc và cột sắp xếp.
- [ ] Đã đánh giá composite index theo leftmost prefix.
- [ ] Đã kiểm tra filesort và không mặc định rằng filesort luôn ghi ra đĩa.
- [ ] Đã dùng EXPLAIN hoặc EXPLAIN ANALYZE để kiểm tra.
- [ ] Không dùng OFFSET quá sâu cho danh sách lớn nếu có thể dùng keyset.
- [ ] Cursor chứa đủ mọi cột ORDER BY và đúng chiều sắp xếp.
- [ ] Đã xác định cách xử lý NULL trong cột cursor.
- [ ] Đã xem xét dữ liệu thay đổi giữa các lần phân trang.
- [ ] Đã đo chi phí index bổ sung đối với INSERT/UPDATE/DELETE.
- [ ] Đã kiểm thử với giá trị trùng, dữ liệu ít hơn N và dữ liệu thay đổi đồng thời.

## 16. Nguyên tắc cần ghi nhớ

1. LIMIT chỉ giới hạn số hàng, không tự tạo thứ tự.
2. ORDER BY trên cột không duy nhất không xác định thứ tự giữa các hàng đồng hạng.
3. Thêm primary key hoặc khóa duy nhất vào cuối ORDER BY để tạo thứ tự xác định.
4. LIMIT N lấy tối đa N hàng; dùng RANK/DENSE_RANK khi cần giữ đồng hạng.
5. ROW_NUMBER phù hợp với Top-N có số hàng tối đa cố định, bao gồm Top-N theo nhóm.
6. Index phù hợp có thể giúp MySQL đọc theo thứ tự và dừng khi đã lấy đủ N hàng.
7. Filesort là bước sắp xếp bổ sung; không đồng nghĩa chắc chắn sử dụng đĩa.
8. Composite index thường đặt cột lọc bằng trước, cột sắp xếp sau và tie-breaker cuối.
9. MySQL 8.0 trở lên hỗ trợ descending index thực sự; MySQL 5.7 bỏ qua DESC trong định nghĩa index.
10. OFFSET sâu có chi phí tăng vì server phải đi qua các hàng bị bỏ qua.
11. Keyset pagination tiếp tục từ khóa sắp xếp cuối trang trước và phù hợp với danh sách lớn.
12. Keyset không tạo snapshot bất biến; cần thiết kế thêm nếu nghiệp vụ đòi hỏi dữ liệu nhất quán tại một thời điểm.
13. Kiểm tra kế hoạch và thời gian thực tế trước khi thêm index hoặc ép optimizer.

## Tài liệu tham khảo chính thức

Các cú pháp và hành vi trong bài được đối chiếu với MySQL 9.7 Reference Manual:

1. [LIMIT Query Optimization](https://dev.mysql.com/doc/refman/9.7/en/limit-optimization.html): tối ưu LIMIT, ORDER BY và hành vi nondeterministic của các hàng đồng hạng.
2. [ORDER BY Optimization](https://dev.mysql.com/doc/refman/9.7/en/order-by-optimization.html): sử dụng index để đáp ứng ORDER BY và filesort.
3. [Descending Indexes](https://dev.mysql.com/doc/refman/9.7/en/descending-indexes.html): index ASC/DESC, backward scan và giới hạn storage engine.
4. [Multiple-Column Indexes](https://dev.mysql.com/doc/refman/9.7/en/multiple-column-indexes.html): composite index và leftmost prefix.
5. [Window Function Descriptions](https://dev.mysql.com/doc/refman/9.7/en/window-function-descriptions.html): ROW_NUMBER, RANK và DENSE_RANK.
6. [EXPLAIN Statement](https://dev.mysql.com/doc/refman/9.7/en/explain.html): kiểm tra execution plan và EXPLAIN ANALYZE.
7. [EXPLAIN Output Format](https://dev.mysql.com/doc/refman/9.7/en/explain-output.html): Using filesort, Using index và thông tin kế hoạch.
8. [SELECT Statement](https://dev.mysql.com/doc/refman/9.7/en/select.html): cú pháp ORDER BY, LIMIT và OFFSET.
9. [MySQL 5.7 CREATE INDEX](https://dev.mysql.com/doc/refman/5.7/en/create-index.html): DESC trong định nghĩa index được parse nhưng không lưu hướng giảm dần trong MySQL 5.7.

