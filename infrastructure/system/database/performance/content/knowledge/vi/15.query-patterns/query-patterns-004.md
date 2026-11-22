# Truy vấn lấy bản ghi mới nhất hoặc top-N trong từng nhóm

Nhiều ứng dụng cần lấy bản ghi mới nhất hoặc một số lượng giới hạn bản ghi đứng đầu trong từng nhóm dữ liệu. Ví dụ: lấy đơn hàng gần nhất của mỗi khách hàng, ba giao dịch mới nhất của mỗi tài khoản, năm sản phẩm bán chạy trong từng cửa hàng hoặc phiên bản mới nhất của mỗi tài liệu. Đây là mẫu truy vấn top-N-per-group.

Mẫu truy vấn này có vẻ giống việc dùng ORDER BY kết hợp LIMIT, nhưng LIMIT thông thường áp dụng cho toàn bộ kết quả. Nếu cần giới hạn riêng cho từng nhóm, phải xác định nhóm, thứ tự xếp hạng và cách xử lý các giá trị bằng nhau. Cách viết SQL còn ảnh hưởng trực tiếp đến số hàng phải đọc, khả năng tận dụng chỉ mục, chi phí sắp xếp và thời gian đáp ứng.

Bài học thuộc chương **Mẫu truy vấn** của module DATABASE_PERFORMANCE. Module DATABASE_PERFORMANCE rèn phương pháp tối ưu hiệu năng cơ sở dữ liệu dựa trên đo đạc tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu; nội dung bao gồm thiết kế chỉ mục, cải thiện SQL, nhận diện tranh chấp giao dịch, nút thắt I/O, bộ nhớ và kiểm chứng kết quả sau điều chỉnh. Vì vậy, mỗi phương án top-N cần được đánh giá trên workload thực tế và execution plan, đồng thời phải giữ đúng ngữ nghĩa nghiệp vụ.

## 1. Xác định yêu cầu top-N-per-group

Trước khi viết truy vấn, hãy xác định bốn yếu tố:

1. **Nhóm (group):** các bản ghi được chia theo cột hoặc tổ hợp cột nào?
2. **Điều kiện đủ tiêu chuẩn:** bản ghi nào được tham gia xếp hạng?
3. **Thứ tự xếp hạng:** mới nhất theo thời gian, điểm cao nhất, doanh thu lớn nhất hay một quy tắc khác?
4. **Quy tắc khi bằng nhau:** cần đúng N bản ghi, hay cần lấy tất cả bản ghi đồng hạng ở vị trí cuối?

Ví dụ, yêu cầu “lấy ba đơn hàng mới nhất của mỗi khách hàng” có thể được mô tả:

- Nhóm theo customer_id.
- Chỉ xét đơn hàng thuộc tenant hiện tại và thỏa điều kiện nghiệp vụ đã chọn.
- Sắp xếp theo created_at giảm dần.
- Dùng order_id làm tiêu chí phụ để kết quả xác định khi nhiều đơn có cùng thời điểm.
- Lấy tối đa ba đơn cho mỗi khách hàng.

Định nghĩa rõ yêu cầu giúp tránh những truy vấn chạy nhanh nhưng trả sai tập bản ghi.

## 2. Vì sao LIMIT thông thường không giải quyết được top-N-per-group?

LIMIT giới hạn số hàng của toàn bộ kết quả sau khi truy vấn được sắp xếp. Ví dụ:

~~~sql
SELECT customer_id, order_id, created_at
FROM orders
ORDER BY created_at DESC
LIMIT 3;
~~~

Truy vấn này chỉ trả ba đơn hàng mới nhất trên toàn bảng. Nó không trả ba đơn hàng mới nhất cho mỗi khách hàng. Nếu có 10.000 khách hàng, kết quả vẫn chỉ có tối đa ba hàng.

Muốn giới hạn riêng theo khách hàng, cần xếp hạng các đơn trong từng nhóm:

~~~sql
ROW_NUMBER() OVER
(
    PARTITION BY customer_id
    ORDER BY created_at DESC, order_id DESC
)
~~~

PARTITION BY chia các hàng thành nhóm độc lập. ORDER BY xác định thứ tự trong từng nhóm. Hàm cửa sổ tính số thứ tự hoặc thứ hạng cho từng hàng mà không gộp các hàng thành một kết quả tổng hợp như GROUP BY.

## 3. Dùng ROW_NUMBER để lấy đúng N hàng mỗi nhóm

ROW_NUMBER đánh số tuần tự các hàng trong từng partition bắt đầu từ 1. Để lấy tối đa N hàng đầu của mỗi nhóm, lọc kết quả có row number nhỏ hơn hoặc bằng N.

Ví dụ lấy ba đơn hàng mới nhất của mỗi khách hàng:

~~~sql
WITH ranked_orders AS
(
    SELECT
        o.customer_id,
        o.order_id,
        o.created_at,
        o.total_amount,
        ROW_NUMBER() OVER
        (
            PARTITION BY o.customer_id
            ORDER BY o.created_at DESC, o.order_id DESC
        ) AS rn
    FROM orders AS o
    WHERE o.status = 'PAID'
)
SELECT customer_id, order_id, created_at, total_amount
FROM ranked_orders
WHERE rn <= 3
ORDER BY customer_id, created_at DESC, order_id DESC;
~~~

Trong ví dụ, chỉ các đơn đã thanh toán tham gia xếp hạng. Mỗi khách hàng có tối đa ba hàng trong kết quả. Nếu một khách hàng có ít hơn ba đơn phù hợp, truy vấn trả số hàng hiện có; khách hàng không có đơn phù hợp sẽ không xuất hiện.

### Vì sao cần ORDER BY có tiêu chí phân biệt?

Nếu chỉ viết:

~~~sql
ROW_NUMBER() OVER
(
    PARTITION BY customer_id
    ORDER BY created_at DESC
)
~~~

hai đơn có cùng created_at có thể nhận thứ tự khác nhau giữa các lần thực thi hoặc kế hoạch. Cơ sở dữ liệu không bảo đảm thứ tự giữa các hàng bằng nhau nếu không có tiêu chí phân biệt bổ sung.

Thêm order_id (giả sử là khóa duy nhất) tạo thứ tự xác định:

~~~sql
ORDER BY created_at DESC, order_id DESC
~~~

Tiêu chí phụ phải phù hợp với nghiệp vụ. Nếu muốn ưu tiên đơn được tạo sau khi thời điểm chính bằng nhau, order_id tăng dần hoặc giảm dần chỉ là quy tắc kỹ thuật khi khóa phản ánh thứ tự đó. Không nên mặc định ID luôn biểu diễn thời gian.

## 4. Phân biệt ROW_NUMBER, RANK và DENSE_RANK

Ba hàm xếp hạng thường được dùng cho top-N, nhưng xử lý giá trị bằng nhau khác nhau.

| Hàm | Cách đánh số | Khi lọc thứ hạng <= N |
| --- | --- | --- |
| ROW_NUMBER | Mỗi hàng nhận số riêng 1, 2, 3, ... | Trả tối đa N hàng mỗi nhóm |
| RANK | Các hàng đồng hạng nhận cùng hạng; hạng tiếp theo có khoảng trống | Trả các hàng có vị trí xếp hạng nằm trong N vị trí đầu, bao gồm đồng hạng |
| DENSE_RANK | Các hàng đồng hạng nhận cùng hạng; hạng tiếp theo không có khoảng trống | Trả N mức giá trị xếp hạng phân biệt đầu tiên |

Ví dụ điểm doanh số trong một nhóm:

| Nhân viên | Điểm | ROW_NUMBER | RANK | DENSE_RANK |
| --- | ---: | ---: | ---: | ---: |
| An | 98 | 1 | 1 | 1 |
| Bình | 95 | 2 | 2 | 2 |
| Chi | 95 | 3 | 2 | 2 |
| Dũng | 90 | 4 | 4 | 3 |
| Hà | 85 | 5 | 5 | 4 |

Nếu lấy top 3:

- ROW_NUMBER <= 3 trả An, Bình và Chi: đúng ba hàng.
- RANK <= 3 trả An, Bình và Chi: gồm mọi người có vị trí cạnh tranh trong ba vị trí đầu.
- DENSE_RANK <= 3 trả An, Bình, Chi và Dũng: gồm ba mức điểm phân biệt đầu tiên.

### Không phá đồng hạng bằng khóa phụ trong RANK

Nếu nghiệp vụ yêu cầu người có cùng điểm phải đồng hạng, phần ORDER BY của RANK hoặc DENSE_RANK chỉ nên chứa các tiêu chí quyết định đồng hạng, ví dụ score DESC. Có thể dùng thứ tự phụ ở truy vấn ngoài để hiển thị ổn định:

~~~sql
WITH ranked_sales AS
(
    SELECT
        store_id,
        employee_id,
        sales_score,
        RANK() OVER
        (
            PARTITION BY store_id
            ORDER BY sales_score DESC
        ) AS position_rank
    FROM employee_sales
)
SELECT store_id, employee_id, sales_score, position_rank
FROM ranked_sales
WHERE position_rank <= 3
ORDER BY store_id, sales_score DESC, employee_id;
~~~

Nếu đưa employee_id vào ORDER BY bên trong RANK và employee_id là duy nhất, các hàng cùng sales_score sẽ không còn đồng hạng. Vì vậy cần phân biệt thứ tự dùng để xác định hạng với thứ tự dùng để trình bày kết quả.

## 5. Lọc trước hay sau khi xếp hạng?

Vị trí bộ lọc làm thay đổi ý nghĩa top-N. Đây là lỗi thường gặp khi truy vấn có trạng thái, loại bản ghi, thời gian hoặc cờ hiệu lực.

### Trường hợp A: lấy ba đơn đã thanh toán mới nhất

Điều kiện status được áp dụng trước khi xếp hạng:

~~~sql
WITH ranked AS
(
    SELECT o.*,
           ROW_NUMBER() OVER
           (
               PARTITION BY customer_id
               ORDER BY created_at DESC, order_id DESC
           ) AS rn
    FROM orders AS o
    WHERE status = 'PAID'
)
SELECT *
FROM ranked
WHERE rn <= 3;
~~~

Đơn chưa thanh toán không tham gia xếp hạng. Nếu đơn mới nhất của khách hàng là PENDING, đơn đó bị loại trước; các đơn PAID trước đó vẫn có thể nằm trong top ba.

### Trường hợp B: chỉ lấy đơn mới nhất nếu đơn đó đã thanh toán

Trước tiên xếp hạng tất cả đơn, sau đó mới lọc trạng thái:

~~~sql
WITH ranked AS
(
    SELECT o.*,
           ROW_NUMBER() OVER
           (
               PARTITION BY customer_id
               ORDER BY created_at DESC, order_id DESC
           ) AS rn
    FROM orders AS o
)
SELECT *
FROM ranked
WHERE rn = 1
  AND status = 'PAID';
~~~

Nếu đơn mới nhất đang PENDING, khách hàng đó không có hàng trong kết quả, dù trước đó có đơn PAID cũ hơn. Đây là yêu cầu khác với trường hợp A.

### Điều kiện tenant và quyền truy cập

Các điều kiện giới hạn tenant, phạm vi dữ liệu và quyền truy cập thường phải được áp dụng đúng trước khi xếp hạng để tránh một nhóm bao gồm dữ liệu ngoài phạm vi. Cần xác định partition key và filter theo mô hình dữ liệu, không dựa vào việc lọc kết quả cuối cùng để che dữ liệu đã tham gia xếp hạng.

## 6. Lấy bản ghi mới nhất của mỗi nhóm

Khi N = 1, có nhiều cách viết. Hàm ROW_NUMBER là cách tổng quát, dễ mở rộng và biểu đạt rõ quy tắc chọn một hàng.

~~~sql
WITH latest_event AS
(
    SELECT
        e.account_id,
        e.event_id,
        e.event_type,
        e.created_at,
        ROW_NUMBER() OVER
        (
            PARTITION BY e.account_id
            ORDER BY e.created_at DESC, e.event_id DESC
        ) AS rn
    FROM account_events AS e
)
SELECT account_id, event_id, event_type, created_at
FROM latest_event
WHERE rn = 1;
~~~

Nếu hai sự kiện có cùng thời điểm, event_id là tiêu chí phụ để chọn duy nhất một hàng. Nếu yêu cầu nghiệp vụ là trả tất cả sự kiện đồng thời mới nhất, không dùng ROW_NUMBER với tie-breaker để loại một sự kiện; hãy dùng RANK theo created_at hoặc một phép JOIN với giá trị MAX phù hợp.

### Dùng MAX rồi JOIN lại

Một cách khác là tìm thời điểm lớn nhất trong mỗi nhóm rồi nối lại bảng:

~~~sql
WITH latest_time AS
(
    SELECT account_id, MAX(created_at) AS max_created_at
    FROM account_events
    GROUP BY account_id
)
SELECT e.account_id, e.event_id, e.event_type, e.created_at
FROM account_events AS e
JOIN latest_time AS m
  ON m.account_id = e.account_id
 AND m.max_created_at = e.created_at;
~~~

Cách này trả tất cả hàng có created_at bằng thời điểm mới nhất. Nếu một tài khoản có hai sự kiện cùng timestamp, kết quả có hai hàng. Đó là hành vi đúng nếu cần giữ đồng hạng; nếu chỉ muốn một hàng, cần thêm quy tắc phá hòa rõ ràng.

Không thể chỉ thêm MAX(event_id) một cách tùy tiện nếu event_id không được chọn trong cùng tập hàng có max_created_at. Muốn chọn một hàng theo hai tiêu chí, cần biểu diễn thứ tự từ điển hoặc dùng ROW_NUMBER để tránh chọn hai giá trị cực đại độc lập thuộc về hai bản ghi khác nhau.

## 7. Dùng LATERAL hoặc APPLY để tìm top-N cho từng nhóm

Khi đã có danh sách nhóm cần xử lý, có thể thực hiện một truy vấn con tương quan cho từng nhóm, sắp xếp theo thứ tự và giới hạn N hàng. Cách này có thể tận dụng chỉ mục để dừng sớm sau khi tìm đủ N hàng trong mỗi nhóm.

### PostgreSQL với LATERAL

~~~sql
SELECT
    c.customer_id,
    recent.order_id,
    recent.created_at,
    recent.total_amount
FROM customers AS c
LEFT JOIN LATERAL
(
    SELECT o.order_id, o.created_at, o.total_amount
    FROM orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
    ORDER BY o.created_at DESC, o.order_id DESC
    LIMIT 3
) AS recent ON TRUE;
~~~

Với mỗi khách hàng, truy vấn con tìm tối đa ba đơn PAID mới nhất. LEFT JOIN LATERAL giữ khách hàng không có đơn phù hợp và trả NULL ở các cột recent. Nếu chỉ muốn khách hàng có đơn, có thể dùng JOIN LATERAL.

### SQL Server với OUTER APPLY

~~~sql
SELECT
    c.customer_id,
    recent.order_id,
    recent.created_at,
    recent.total_amount
FROM dbo.Customers AS c
OUTER APPLY
(
    SELECT TOP (3)
           o.order_id,
           o.created_at,
           o.total_amount
    FROM dbo.Orders AS o
    WHERE o.customer_id = c.customer_id
      AND o.status = 'PAID'
    ORDER BY o.created_at DESC, o.order_id DESC
) AS recent;
~~~

OUTER APPLY giữ hàng bên trái ngay cả khi truy vấn con không trả hàng. CROSS APPLY chỉ giữ các hàng bên trái có ít nhất một kết quả từ truy vấn con. Cú pháp và khả năng tối ưu tương ứng khác nhau giữa hệ quản trị; không sao chép cú pháp LATERAL hoặc APPLY sang nền tảng không hỗ trợ.

### Khi nào LATERAL/APPLY có lợi?

- Danh sách nhóm đầu vào đã được giới hạn, chẳng hạn một trang gồm vài chục khách hàng.
- Mỗi nhóm chỉ cần N nhỏ.
- Có chỉ mục bắt đầu bằng khóa nhóm, tiếp theo là điều kiện lọc và thứ tự xếp hạng.
- Hệ quản trị có thể thực hiện index seek/range scan và dừng sau N hàng.

Nếu có hàng triệu nhóm và mỗi nhóm đều phải khởi chạy một lần tra cứu riêng, chi phí lặp có thể lớn. Khi đó, một lần quét và xếp hạng bằng window function có thể hiệu quả hơn. Phải so sánh số nhóm, số hàng mỗi nhóm, mức chọn lọc và execution plan.

## 8. DISTINCT ON và các cú pháp đặc thù khác

Một số hệ quản trị cung cấp cú pháp rút gọn cho trường hợp lấy một hàng đầu tiên trong mỗi nhóm.

### PostgreSQL DISTINCT ON

~~~sql
SELECT DISTINCT ON (customer_id)
       customer_id,
       order_id,
       created_at,
       total_amount
FROM orders
WHERE status = 'PAID'
ORDER BY customer_id, created_at DESC, order_id DESC;
~~~

DISTINCT ON giữ hàng đầu tiên theo thứ tự ORDER BY cho mỗi customer_id. Các cột trong DISTINCT ON phải phù hợp với phần đầu ORDER BY theo quy tắc của PostgreSQL. Nếu không quy định thứ tự đủ xác định, hàng được chọn có thể không ổn định.

Đây là cú pháp riêng của PostgreSQL, không phải SQL chuẩn dùng được trên mọi hệ quản trị. Với top-N lớn hơn 1 hoặc cần xếp hạng đồng hạng, window function thường linh hoạt hơn.

### TOP WITH TIES

SQL Server hỗ trợ TOP (N) WITH TIES để giữ các hàng đồng hạng với hàng ở vị trí cuối theo ORDER BY. Khi dùng trong truy vấn con với APPLY, nó có thể biểu đạt top-N có ties cho từng nhóm. ORDER BY trong truy vấn con phải chỉ chứa tiêu chí xác định đồng hạng; nếu thêm khóa duy nhất vào đó thì các hàng thường không còn đồng hạng.

## 9. Thiết kế chỉ mục cho top-N-per-group

Chỉ mục thường có ảnh hưởng lớn đến mẫu truy vấn này. Một chỉ mục phù hợp có thể giúp cơ sở dữ liệu định vị nhóm, đọc theo thứ tự xếp hạng và dừng sớm khi đã lấy đủ N hàng.

Giả sử truy vấn lấy ba đơn PAID mới nhất cho từng khách hàng:

~~~sql
WHERE customer_id = ?
  AND status = 'PAID'
ORDER BY created_at DESC, order_id DESC
LIMIT 3
~~~

Một chỉ mục B-tree đáng thử:

~~~sql
CREATE INDEX idx_orders_customer_status_recent
ON orders
(
    customer_id,
    status,
    created_at DESC,
    order_id DESC
);
~~~

Thứ tự cột có ý nghĩa:

1. customer_id xác định nhóm cần tra cứu.
2. status được cố định bằng equality.
3. created_at và order_id cung cấp thứ tự mới nhất có tie-breaker.

Với một lần tra cứu theo customer_id và status, các hàng có thể được đọc theo thứ tự mong muốn. Tùy hệ quản trị, bộ tối ưu có thể dùng index seek/range scan và dừng sau ba hàng.

### Khi có điều kiện equality toàn cục

Nếu truy vấn luôn lọc theo tenant_id bằng equality, có thể cần đưa tenant_id lên trước:

~~~sql
CREATE INDEX idx_orders_tenant_customer_recent
ON orders
(
    tenant_id,
    customer_id,
    status,
    created_at DESC,
    order_id DESC
);
~~~

Với tenant_id và status được cố định, customer_id là khóa nhóm, còn các cột thời gian và ID xác định thứ tự trong nhóm. Thứ tự thực tế phải được xem xét cùng các truy vấn khác, nhất là truy vấn chỉ lọc customer_id hoặc status.

### Chỉ mục có điều kiện hoặc filtered index

Nếu truy vấn luôn chỉ lấy status = 'PAID' và hệ quản trị hỗ trợ partial/filtered index, có thể thử chỉ mục chỉ chứa các hàng thỏa điều kiện đó:

~~~sql
CREATE INDEX idx_orders_paid_customer_recent
ON orders (customer_id, created_at DESC, order_id DESC)
WHERE status = 'PAID';
~~~

Đây là cú pháp minh họa cho các hệ quản trị hỗ trợ chỉ mục có điều kiện; cú pháp và khả năng sử dụng phụ thuộc nền tảng. Chỉ mục nhỏ hơn có thể giảm dung lượng và chi phí đọc, nhưng chỉ hữu ích nếu predicate truy vấn tương thích với điều kiện của chỉ mục.

### Bao phủ truy vấn

Nếu truy vấn cần thêm total_amount, một số hệ quản trị cho phép đưa cột này vào payload hoặc INCLUDE để giảm truy cập bảng. Cần cân nhắc kích thước chỉ mục và chi phí ghi. Không đưa mọi cột SELECT vào khóa sắp xếp; chỉ thêm cột bao phủ khi phép đo cho thấy lợi ích đủ lớn.

### Vì sao không chỉ lập chỉ mục trên cột thời gian?

Chỉ mục chỉ có created_at có thể tìm các bản ghi mới nhất toàn bảng, nhưng không nhất thiết tìm được các bản ghi mới nhất riêng cho từng customer_id. Nếu truy vấn partition theo customer_id, thứ tự khóa cần phản ánh cả khóa nhóm lẫn thứ tự trong nhóm. Một chỉ mục theo thời gian toàn cục không thay thế được chỉ mục theo customer rồi đến thời gian trong mọi trường hợp.

## 10. Chiến lược window function và LATERAL khác nhau thế nào?

Hai cách tiếp cận thường có kế hoạch và điểm mạnh khác nhau.

| Đặc điểm | Window function | LATERAL/APPLY với LIMIT/TOP |
| --- | --- | --- |
| Cách xử lý | Xếp hạng tập hàng đủ điều kiện theo partition | Tra cứu riêng cho từng nhóm đầu vào |
| Phạm vi nhóm | Có thể xử lý toàn bộ nhóm trong tập dữ liệu | Phù hợp khi có danh sách nhóm đầu vào rõ ràng |
| Cơ hội dừng sớm | Thường cần xử lý/xếp hạng nhiều hàng đủ điều kiện; tùy optimizer | Có thể dừng sau N hàng mỗi nhóm nếu dùng được chỉ mục |
| Chi phí lặp | Có thể quét và sort một tập lớn | Có thể có nhiều lần seek, một lần cho mỗi nhóm |
| Khi thường phù hợp | Nhiều nhóm, muốn xếp hạng một tập dữ liệu lớn | Ít nhóm hoặc nhóm đã được giới hạn, N nhỏ |
| Khả năng di động | Window functions phổ biến trong hệ quản trị hiện đại | Cú pháp LATERAL/APPLY phụ thuộc nền tảng |

Không có chiến lược nào luôn nhanh hơn. Window function có thể cần sort lớn và spill ra đĩa, nhưng một lần xử lý tập dữ liệu có thể rẻ hơn hàng trăm nghìn lần seek. LATERAL có thể rất nhanh khi chỉ có vài chục nhóm và index hỗ trợ, nhưng tốn kém khi số nhóm quá lớn hoặc mỗi lần seek gây I/O ngẫu nhiên.

## 11. Xử lý NULL, nhóm rỗng và giá trị đồng hạng

### Khóa nhóm NULL

Trong window function, các hàng có giá trị NULL ở cột PARTITION BY thường nằm cùng một partition NULL. Nếu NULL có nghĩa là “không xác định nhóm”, việc gom tất cả vào một nhóm có thể không đúng nghiệp vụ. Cần quyết định NULL được xem là một nhóm riêng, bị loại hay được ánh xạ theo một quy tắc cụ thể.

Khi dùng GROUP BY MAX rồi JOIN lại, phép so sánh bằng không khớp hai giá trị NULL theo logic SQL thông thường. Nếu khóa nhóm có thể NULL, cách nối lại cần dùng phép so sánh NULL-safe mà hệ quản trị hỗ trợ, hoặc chuẩn hóa/loại NULL theo quy tắc nghiệp vụ.

### Giá trị sắp xếp NULL

Nếu created_at có thể NULL, cần quy định NULL đứng đầu hay cuối. Thứ tự mặc định có thể khác giữa hệ quản trị. Tốt nhất là bảo đảm cột thời gian bắt buộc có NOT NULL nếu nghiệp vụ yêu cầu, hoặc chỉ rõ cách xử lý NULL trong ORDER BY khi nền tảng hỗ trợ.

### Nhóm không có bản ghi phù hợp

Window function trên bảng orders không trả nhóm khách hàng không có đơn phù hợp. Nếu cần mọi khách hàng và tối đa N đơn của mỗi người, hãy dùng customers làm tập nhóm đầu vào rồi LEFT JOIN LATERAL/APPLY, hoặc kết hợp danh sách nhóm với kết quả đã xếp hạng bằng LEFT JOIN.

### Đồng hạng tại vị trí cuối

Nếu yêu cầu “top 3 sản phẩm theo doanh thu, lấy tất cả sản phẩm đồng hạng ở vị trí thứ ba”, dùng RANK theo doanh thu. Nếu yêu cầu “ba mức doanh thu cao nhất”, dùng DENSE_RANK. Nếu yêu cầu “đúng ba sản phẩm”, dùng ROW_NUMBER với tie-breaker xác định.

## 12. Phân trang trong từng nhóm

Một số ứng dụng cần không chỉ top-N mà còn trang tiếp theo của mỗi nhóm. Có thể thêm điều kiện khoảng thứ hạng:

~~~sql
WHERE rn BETWEEN 11 AND 20
~~~

Cách này đơn giản nhưng thường vẫn phải tính thứ hạng cho các hàng đứng trước vị trí 11 trong mỗi nhóm. Với nhóm rất lớn, việc lấy trang sâu có thể tốn kém.

Một hướng khác là keyset pagination theo khóa sắp xếp trong từng nhóm. Ứng dụng lưu mốc cuối cùng của trang trước, chẳng hạn cặp created_at và order_id, rồi tìm các hàng đứng sau mốc theo đúng chiều sort. Tuy nhiên, nếu cần lấy trang tiếp theo cho nhiều nhóm cùng lúc, mỗi nhóm cần cursor riêng và truy vấn phức tạp hơn.

Không dùng offset hoặc cursor mà thiếu tie-breaker duy nhất. Nếu nhiều hàng có cùng created_at, trang kế tiếp có thể bỏ sót hoặc lặp hàng khi dữ liệu thay đổi.

## 13. Tối ưu và chẩn đoán hiệu năng

Top-N-per-group có thể chậm do nhiều nguyên nhân khác nhau:

- Tập dữ liệu đủ điều kiện quá lớn và cần sort theo group/order.
- Chỉ mục không bắt đầu bằng các cột nhóm hoặc equality filter phù hợp.
- Cột sắp xếp không tương thích với thứ tự khóa chỉ mục.
- Mỗi nhóm có quá nhiều hàng, làm tăng công việc xếp hạng.
- Số nhóm lớn khiến chiến lược LATERAL/APPLY thực hiện quá nhiều lần seek.
- Phân bố dữ liệu lệch, một vài nhóm có số hàng lớn bất thường.
- Thống kê cũ khiến optimizer ước lượng sai số hàng hoặc chọn sai join/access path.
- Sort hoặc window operation cần nhiều bộ nhớ và spill dữ liệu tạm ra đĩa.

### Đọc execution plan

Khi kiểm tra kế hoạch, hãy chú ý:

- Có sort theo partition key và thứ tự xếp hạng hay không?
- Sort có dùng đúng index order hay phải sắp xếp lại?
- Có index seek/range scan cho từng nhóm không?
- Số hàng đầu vào của window operation và số hàng đầu ra sau lọc rn <= N là bao nhiêu?
- Có bao nhiêu lần thực thi truy vấn con trong LATERAL/APPLY?
- Có sort/hash spill, memory grant lớn hoặc temp I/O không?
- Estimated rows có gần actual rows không, nhất là ở nhóm dữ liệu lệch?
- Logical reads, physical reads, CPU time và elapsed time thay đổi ra sao?

Nếu dùng EXPLAIN ANALYZE hoặc chế độ tương đương, nhớ rằng công cụ có thể thực thi truy vấn thật và tạo tải. Hãy thử trên môi trường phù hợp hoặc chọn phạm vi an toàn; không chạy một truy vấn top-N nặng trên production chỉ để xem plan mà chưa đánh giá tác động.

### Đo đúng workload

Một bộ đo có ý nghĩa nên bao gồm:

- Số nhóm và phân bố số hàng trong mỗi nhóm.
- N cần lấy cho mỗi nhóm.
- Tỷ lệ nhóm rỗng, nhóm nhỏ và nhóm rất lớn.
- Tần suất truy vấn và mức đồng thời.
- Trạng thái cache và kích thước dữ liệu.
- p50, p95, p99, thông lượng, CPU, I/O và dung lượng tạm.
- Chi phí ghi sau khi thêm chỉ mục.

Đừng chỉ thử với dữ liệu đồng đều. Trong hệ thống thực, một khách hàng lớn hoặc một cửa hàng có thể có số bản ghi lớn hơn hàng nghìn lần so với nhóm trung bình. Phải đo cả trường hợp điển hình và nhóm lệch lớn.

## 14. Những cách viết dễ gây lỗi hoặc tốn kém

### N+1 truy vấn từ ứng dụng

Ứng dụng lấy danh sách khách hàng rồi chạy thêm một câu SQL top-N cho từng khách hàng. Với 500 khách hàng, có thể phát sinh 501 lượt gọi cơ sở dữ liệu. Cách này đôi khi chấp nhận được khi danh sách nhóm rất nhỏ và latency thấp, nhưng thường tạo nhiều round-trip và tăng áp lực connection pool.

Có thể chuyển sang window function hoặc LATERAL/APPLY để xử lý theo một câu truy vấn. Tuy nhiên, cần đo vì một câu SQL phức tạp không tự động nhanh hơn mọi cách chia truy vấn.

### GROUP BY MAX nhưng không xử lý ties

MAX(created_at) tìm thời gian lớn nhất, không xác định duy nhất một hàng nếu nhiều bản ghi cùng thời điểm. Nếu join lại chỉ theo group và timestamp, có thể trả nhiều hàng. Điều này đúng nếu cần tất cả bản ghi mới nhất; nếu cần một hàng, phải bổ sung tie-breaker.

### Dùng DISTINCT để che nhiều hàng

DISTINCT có thể loại các hàng giống nhau trên danh sách cột SELECT, nhưng không xác định bản ghi mới nhất theo quy tắc nghiệp vụ. Nó cũng có thể làm mất hai bản ghi khác nhau chỉ tình cờ có các cột hiển thị giống nhau. Hãy dùng hàm xếp hạng hoặc chiến lược chọn hàng rõ ràng.

### Thêm khóa duy nhất vào RANK làm mất đồng hạng

Nếu cần giữ ties theo doanh thu nhưng đưa product_id duy nhất vào ORDER BY bên trong RANK, mọi sản phẩm có thể nhận hạng riêng. Hãy chỉ dùng tiêu chí đồng hạng trong hàm rank và dùng thứ tự phụ ở truy vấn ngoài.

### Lọc sau khi xếp hạng sai ngữ nghĩa

Lấy top 3 trên tất cả đơn rồi mới lọc status có thể trả ít hơn ba đơn đã thanh toán, dù vẫn còn nhiều đơn PAID cũ hơn. Hãy xác định điều kiện nào quyết định tập đủ tiêu chuẩn trước khi xếp hạng.

## 15. Ví dụ tổng hợp: ba giao dịch gần nhất cho mỗi tài khoản

Một dịch vụ ngân hàng cần hiển thị ba giao dịch đã ghi sổ gần nhất cho mỗi tài khoản. Bảng transactions có một hàng cho mỗi giao dịch, với các cột account_id, transaction_id, posted_at, status và amount.

### Phương án dùng ROW_NUMBER

~~~sql
WITH ranked_transactions AS
(
    SELECT
        t.account_id,
        t.transaction_id,
        t.posted_at,
        t.amount,
        ROW_NUMBER() OVER
        (
            PARTITION BY t.account_id
            ORDER BY t.posted_at DESC, t.transaction_id DESC
        ) AS rn
    FROM transactions AS t
    WHERE t.status = 'POSTED'
)
SELECT account_id, transaction_id, posted_at, amount
FROM ranked_transactions
WHERE rn <= 3
ORDER BY account_id, posted_at DESC, transaction_id DESC;
~~~

Điều kiện POSTED nằm trong truy vấn con nên chỉ giao dịch đã ghi sổ tham gia xếp hạng. transaction_id là tiêu chí phụ để xác định thứ tự khi posted_at trùng, giả sử khóa này duy nhất.

### Chỉ mục có thể thử

~~~sql
CREATE INDEX idx_transactions_account_status_recent
ON transactions
(
    account_id,
    status,
    posted_at DESC,
    transaction_id DESC
);
~~~

Chỉ mục đặt khóa nhóm trước, status equality tiếp theo và các cột xếp hạng ở cuối. Nếu truy vấn luôn lọc status = 'POSTED' và hệ quản trị hỗ trợ partial/filtered index, có thể thử một chỉ mục chỉ chứa giao dịch đã ghi sổ. Không tạo cả hai chỉ mục trước khi đo lợi ích và chi phí.

### Phương án theo từng tài khoản

Nếu màn hình chỉ hiển thị 20 tài khoản trong một trang, LATERAL hoặc APPLY có thể tra cứu tối đa ba giao dịch cho từng tài khoản và dừng sớm. Nếu cần tất cả tài khoản trong hệ thống, window function có thể tránh thực hiện một lần seek cho từng tài khoản. Hãy so sánh hai phương án trên số tài khoản, số giao dịch mỗi tài khoản và mức đồng thời thực tế.

### Kiểm chứng

Sau khi thay đổi, so sánh:

- Số hàng trả về: tối đa ba giao dịch cho mỗi tài khoản có giao dịch POSTED.
- Tính chính xác của thứ tự posted_at và transaction_id.
- p50/p95/p99 và tổng thời gian của truy vấn.
- Số hàng và trang được đọc, số lần seek, sort và spill.
- CPU, bộ nhớ, I/O và throughput.
- Thời gian INSERT/UPDATE và chi phí duy trì chỉ mục.

Đối chiếu kết quả với một tập tài khoản có số giao dịch ít, nhiều và có nhiều timestamp trùng. Điều này xác nhận cả trường hợp thông thường lẫn trường hợp dễ làm lộ lỗi ties.

## 16. Quy trình lựa chọn và kiểm chứng

Có thể áp dụng quy trình sau cho mọi truy vấn top-N-per-group:

1. **Định nghĩa grain và nhóm:** xác định một hàng đại diện cho điều gì, khóa nhóm nào và N áp dụng riêng cho từng nhóm ra sao.
2. **Chốt ngữ nghĩa ties:** chọn đúng N hàng, tất cả hàng đồng hạng theo vị trí, hay N mức giá trị xếp hạng phân biệt.
3. **Xác định tập đủ điều kiện:** đặt filter trước hay sau khi xếp hạng theo đúng yêu cầu nghiệp vụ.
4. **Chọn cách viết:** ROW_NUMBER/RANK/DENSE_RANK cho tập dữ liệu lớn; LATERAL/APPLY khi danh sách nhóm nhỏ và có thể dừng sớm; cú pháp riêng của hệ quản trị khi phù hợp.
5. **Thiết kế chỉ mục:** ưu tiên khóa phạm vi/equality, khóa nhóm và thứ tự xếp hạng; xem xét bao phủ và chỉ mục có điều kiện.
6. **Đo baseline:** ghi số nhóm, phân bố số hàng, N, latency, throughput, reads, CPU, I/O và trạng thái cache.
7. **Đọc execution plan:** kiểm tra sort, index access, số lần seek, actual rows, estimated rows và spill.
8. **Thử với dữ liệu lệch:** bao gồm nhóm lớn, nhóm rỗng, ties và các giá trị NULL nếu được phép.
9. **Đánh giá toàn workload:** đo cả truy vấn đọc, thao tác ghi và các truy vấn khác dùng chung chỉ mục.
10. **Theo dõi sau điều chỉnh:** lưu kế hoạch và số liệu trước/sau, kiểm tra kết quả nghiệp vụ và hoàn nguyên nếu chỉ số bảo vệ vượt giới hạn.

## 17. Nguyên tắc cần ghi nhớ

- LIMIT thông thường giới hạn toàn bộ kết quả; top-N-per-group cần phân vùng và xếp hạng riêng cho từng nhóm.
- ROW_NUMBER trả tối đa N hàng mỗi nhóm; RANK và DENSE_RANK giữ các hàng đồng hạng theo hai cách đánh số khác nhau.
- Thêm khóa duy nhất vào thứ tự ROW_NUMBER để kết quả ổn định; không thêm vào thứ tự RANK nếu cần bảo toàn ties theo tiêu chí nghiệp vụ.
- Điều kiện lọc trước và sau khi xếp hạng có ý nghĩa khác nhau; phải xác định tập đủ điều kiện trước khi viết SQL.
- MAX(timestamp) nối lại có thể trả nhiều hàng khi timestamp trùng; cần quy tắc phá hòa nếu chỉ muốn một hàng.
- LATERAL/APPLY có thể dừng sớm theo từng nhóm khi có chỉ mục phù hợp, nhưng nhiều lần seek có thể tốn kém khi số nhóm lớn.
- Chỉ mục nên phản ánh khóa nhóm, điều kiện equality và thứ tự xếp hạng; kiểm tra khả năng sort avoidance và covering trên hệ quản trị cụ thể.
- Đo với nhóm có kích thước lệch, N khác nhau, ties và trạng thái cache phù hợp.
- Kiểm tra execution plan, số hàng thực tế, số lần truy cập, sort/spill, latency và chi phí ghi.
- Xác nhận kết quả đúng nghiệp vụ trước khi kết luận tối ưu thành công.

Truy vấn lấy bản ghi mới nhất hoặc top-N trong từng nhóm là mẫu truy vấn quan trọng trong hệ thống giao dịch, báo cáo và ứng dụng hướng sự kiện. Khi xác định đúng nhóm, tập bản ghi đủ điều kiện, thứ tự xếp hạng và quy tắc đồng hạng, nhóm phát triển có thể chọn cách viết SQL cùng chỉ mục phù hợp. Đo lường trên workload đại diện và kiểm tra execution plan sẽ cho biết phương án đó có thực sự giảm công việc cơ sở dữ liệu mà vẫn giữ đúng kết quả hay không.
