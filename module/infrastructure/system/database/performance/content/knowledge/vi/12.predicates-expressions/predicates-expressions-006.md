# OR, IN và cách tách truy vấn khi có bằng chứng kế hoạch tốt hơn

Điều kiện OR và IN giúp biểu diễn truy vấn có nhiều khả năng khớp. Chúng thường rõ ràng và đúng ngữ nghĩa, nhưng khi các nhánh điều kiện có độ chọn lọc khác nhau hoặc nằm trên những cột có chỉ mục riêng, bộ tối ưu có thể chọn một kế hoạch chưa hiệu quả. Trong một số trường hợp, tách điều kiện thành các nhánh truy vấn riêng giúp mỗi nhánh dùng đường truy cập phù hợp hơn. Trong trường hợp khác, việc tách làm tăng số lần đọc, tạo bước loại trùng, phát sinh Sort hoặc làm truy vấn khó tối ưu hơn.

Với mục tiêu tối ưu hiệu năng cơ sở dữ liệu, không nên mặc định OR chậm hơn UNION, hoặc IN luôn nhanh hơn nhiều phép so sánh. Cần hiểu ngữ nghĩa logic của SQL, cách optimizer xử lý disjunction, khả năng dùng chỉ mục, rủi ro hàng trùng và số liệu thực tế trước khi viết lại.

## 1. Ngữ nghĩa của OR và IN

### 1.1. OR kết hợp các điều kiện

OR trả về TRUE khi ít nhất một nhánh là TRUE. Ví dụ:

~~~sql
SELECT id, customer_id, status
FROM orders
WHERE status = 'OPEN'
   OR status = 'READY';
~~~

Truy vấn lấy đơn hàng có trạng thái OPEN hoặc READY. Mỗi hàng thỏa một trong hai điều kiện sẽ xuất hiện một lần trong kết quả, kể cả khi nhiều nhánh cùng đúng đối với hàng đó. OR là một điều kiện trên mỗi hàng; nó không nhân bản hàng theo số nhánh khớp.

### 1.2. IN là cách viết gọn cho nhiều phép so sánh bằng

Với danh sách giá trị cố định, biểu thức:

~~~sql
WHERE status IN ('OPEN', 'READY', 'RUNNING')
~~~

có ngữ nghĩa tương đương:

~~~sql
WHERE status = 'OPEN'
   OR status = 'READY'
   OR status = 'RUNNING'
~~~

Optimizer thường có thể chuẩn hóa hai cách viết thành cùng một dạng nội bộ. Vì vậy, thay OR bằng IN chỉ để hy vọng truy vấn nhanh hơn thường không tạo khác biệt đáng kể. Hãy ưu tiên cách viết dễ đọc, sau đó xác nhận kế hoạch.

IN cũng có thể nhận kết quả từ subquery:

~~~sql
SELECT o.id, o.customer_id
FROM orders AS o
WHERE o.customer_id IN (
    SELECT c.id
    FROM customers AS c
    WHERE c.region = 'NORTH'
);
~~~

Trong trường hợp này, bộ tối ưu có thể biến đổi truy vấn thành semi join hoặc một chiến lược tương đương. Không nên giả định IN luôn thực thi như một vòng lặp kiểm tra từng giá trị.

### 1.3. SQL dùng logic ba giá trị

Điều kiện SQL có thể cho kết quả TRUE, FALSE hoặc UNKNOWN. UNKNOWN thường phát sinh khi so sánh với NULL. Trong mệnh đề WHERE, chỉ hàng có điều kiện TRUE được giữ lại.

Ví dụ:

~~~sql
SELECT id
FROM orders
WHERE status = 'OPEN'
   OR status = NULL;
~~~

Điều kiện status = NULL không đúng để kiểm tra NULL; phép so sánh tạo UNKNOWN. Cách viết đúng là:

~~~sql
SELECT id
FROM orders
WHERE status = 'OPEN'
   OR status IS NULL;
~~~

Tương tự, IN có thể chứa NULL:

~~~sql
WHERE status IN ('OPEN', NULL)
~~~

Hàng có status = 'OPEN' được giữ lại. Với giá trị khác OPEN, phép so sánh có thể cho UNKNOWN thay vì FALSE; kết quả vẫn không được giữ trong WHERE.

Đặc biệt cẩn thận với NOT IN:

~~~sql
WHERE customer_id NOT IN (
    SELECT customer_id
    FROM blocked_customers
)
~~~

Nếu subquery trả về ít nhất một NULL, kết quả NOT IN có thể là UNKNOWN cho nhiều hàng và làm truy vấn trả về ít hoặc không có hàng như mong đợi. Trong trường hợp kiểm tra không tồn tại, NOT EXISTS thường dễ kiểm soát ngữ nghĩa NULL hơn:

~~~sql
WHERE NOT EXISTS (
    SELECT 1
    FROM blocked_customers AS b
    WHERE b.customer_id = o.customer_id
)
~~~

NOT EXISTS và NOT IN không phải lúc nào cũng tương đương khi có NULL; phải xác định rõ quy tắc nghiệp vụ trước khi thay thế.

## 2. Vì sao OR có thể ảnh hưởng đến kế hoạch?

Khi gặp OR, optimizer cần ước lượng số hàng thỏa một hoặc nhiều nhánh, rồi quyết định cách truy cập dữ liệu. Một số tình huống thường gặp:

- Các nhánh OR cùng lọc một cột có thể được chuyển thành một tập giá trị hoặc một range scan.
- Các nhánh OR lọc các cột khác nhau có thể cần kết hợp nhiều chỉ mục.
- Một nhánh rất chọn lọc nhưng nhánh còn lại trả về nhiều hàng có thể khiến optimizer chọn scan để giảm chi phí tổng thể.
- Các nhánh có tương quan khiến ước lượng số hàng sai nếu bộ tối ưu giả định độc lập.
- OR trên nhiều bảng hoặc biểu thức phức tạp có thể hạn chế khả năng đẩy predicate xuống dưới join.

Ví dụ:

~~~sql
SELECT id, email, phone
FROM customers
WHERE email = 'a@example.test'
   OR phone = '0900000000';
~~~

Nếu có chỉ mục riêng trên email và phone, hệ quản trị có thể:

1. Dùng cả hai chỉ mục rồi hợp nhất row identifier.
2. Dùng một chỉ mục và kiểm tra nhánh còn lại như residual predicate.
3. Quét bảng nếu hai nhánh trả về nhiều hàng hoặc chi phí kết hợp chỉ mục cao.

Không có một lựa chọn luôn tốt nhất. Nếu mỗi nhánh chỉ trả về rất ít hàng, kết hợp hai đường tìm kiếm có thể hiệu quả. Nếu một nhánh trả về phần lớn bảng, scan có thể rẻ hơn.

### 2.1. Selectivity và số hàng trùng giữa các nhánh

Giả sử predicate A khớp 1% bảng và predicate B khớp 2%. Không thể luôn kết luận OR khớp 3% vì hai tập có thể giao nhau:

- Nếu A và B không giao nhau, tổng tỷ lệ gần 3%.
- Nếu mọi hàng A cũng thuộc B, tổng tỷ lệ chỉ gần 2%.
- Nếu hai điều kiện độc lập, tỷ lệ hợp thường được ước lượng theo mô hình selectivity kết hợp.

Số hàng trùng giữa các nhánh rất quan trọng khi viết lại OR thành UNION hoặc UNION ALL. OR chỉ trả mỗi hàng một lần; UNION ALL nối kết quả các nhánh và có thể trả một hàng nhiều lần nếu nó thỏa nhiều nhánh.

### 2.2. OR không nhất thiết làm mất khả năng dùng chỉ mục

Nhiều hệ quản trị có cơ chế kết hợp các đường truy cập:

- Bitmap OR hoặc bitmap combination.
- Index Merge hoặc Index Union.
- Index Union, Concatenation hoặc OR expansion.
- Range scan cho nhiều giá trị của cùng một cột.

Do đó, thấy OR trong SQL không có nghĩa optimizer sẽ quét toàn bảng. Hãy mở actual execution plan và xem nó có dùng chỉ mục, kết hợp row identifier, hoặc chọn scan vì chi phí thấp hơn hay không.

## 3. Khi nào IN phù hợp hơn cách viết nhiều OR?

IN thường phù hợp khi nhiều điều kiện là phép so sánh bằng trên cùng một cột:

~~~sql
SELECT id, status
FROM orders
WHERE status = 'OPEN'
   OR status = 'READY'
   OR status = 'RUNNING';
~~~

Có thể viết gọn:

~~~sql
SELECT id, status
FROM orders
WHERE status IN ('OPEN', 'READY', 'RUNNING');
~~~

Lợi ích chính là biểu đạt ý định rõ ràng, giảm lặp điều kiện và dễ bảo trì danh sách giá trị. Optimizer thường xử lý hai cách tương đương tương tự nhau.

IN cũng có thể hữu ích khi một cột khóa cần khớp với danh sách ID:

~~~sql
SELECT id, customer_id, total_amount
FROM orders
WHERE customer_id IN (101, 205, 319, 480);
~~~

Nếu danh sách rất dài hoặc thay đổi theo từng lần gọi, cân nhắc truyền danh sách dưới dạng bảng, table-valued parameter, temporary table hoặc cơ chế tương ứng của hệ quản trị. Cách này giúp quản lý dữ liệu đầu vào rõ ràng hơn, nhưng cần chú ý thống kê, kích thước danh sách và chi phí join.

Không chuyển OR trên các cột khác nhau thành IN. Hai điều kiện email và phone là hai thuộc tính khác nhau và không thể biểu diễn bằng một IN trên một cột duy nhất.

## 4. Khi nào nên xem xét tách truy vấn?

Tách truy vấn có thể đáng thử khi có bằng chứng cho thấy kế hoạch OR hiện tại xử lý dữ liệu không hiệu quả. Một số dấu hiệu:

- Một predicate có chỉ mục chọn lọc, nhưng OR khiến optimizer chọn scan lớn.
- Các nhánh OR nằm trên những cột khác nhau và mỗi nhánh có một chỉ mục phù hợp.
- Hai nhánh có độ chọn lọc rất khác nhau, cần kế hoạch riêng.
- Kế hoạch hiện tại có ước lượng cardinality sai lớn tại node kết hợp OR.
- Một nhánh có thể dùng partition pruning hoặc đường truy cập đặc biệt nếu được lập kế hoạch riêng.
- Thời gian, logical reads hoặc I/O của kế hoạch hiện tại cho thấy operator kết hợp nhánh là nút thắt.

Ví dụ, bảng tickets có hai chỉ mục:

~~~sql
CREATE INDEX ix_tickets_assignee
ON tickets (assignee_id);

CREATE INDEX ix_tickets_reporter
ON tickets (reporter_id);
~~~

Truy vấn tìm ticket mà một người là assignee hoặc reporter:

~~~sql
SELECT id, title, assignee_id, reporter_id
FROM tickets
WHERE assignee_id = :user_id
   OR reporter_id = :user_id;
~~~

Optimizer có thể kết hợp hai chỉ mục. Nếu actual plan cho thấy nó quét quá nhiều trang hoặc chọn scan không phù hợp, có thể thử tách hai nhánh để mỗi nhánh dùng chỉ mục riêng. Nhưng phải bảo toàn tính duy nhất của mỗi ticket trong kết quả.

## 5. UNION ALL và UNION: khác biệt quyết định tính đúng đắn

### 5.1. UNION ALL giữ nguyên hàng trùng

UNION ALL nối kết quả các nhánh và không loại bỏ hàng trùng:

~~~sql
SELECT id, title
FROM tickets
WHERE assignee_id = :user_id

UNION ALL

SELECT id, title
FROM tickets
WHERE reporter_id = :user_id;
~~~

Nếu một ticket có cùng người vừa là assignee vừa là reporter, ticket đó xuất hiện hai lần. Điều này khác với truy vấn OR ban đầu, vốn trả mỗi hàng của tickets một lần.

UNION ALL thường ít tốn chi phí hơn UNION vì không cần loại trùng. Chỉ dùng nó khi các nhánh chắc chắn không giao nhau hoặc khi hàng trùng là một phần có chủ đích của kết quả.

### 5.2. UNION loại trùng trên các cột được chọn

UNION loại bỏ các hàng trùng dựa trên toàn bộ danh sách cột được SELECT:

~~~sql
SELECT id, title
FROM tickets
WHERE assignee_id = :user_id

UNION

SELECT id, title
FROM tickets
WHERE reporter_id = :user_id;
~~~

Nếu id là khóa chính duy nhất và được chọn trong kết quả, UNION loại bỏ trường hợp cùng một ticket xuất hiện ở cả hai nhánh. Tuy nhiên, UNION có thể cần Sort hoặc Hash Aggregate để loại trùng, làm tăng CPU, bộ nhớ và I/O tạm.

Nếu projection không chứa khóa duy nhất, UNION có thể gộp hai hàng khác nhau của bảng chỉ vì các cột được chọn có cùng giá trị. Khi cần giữ mỗi bản ghi gốc riêng biệt, hãy dùng khóa chính để xác định bản ghi trước khi hợp nhất.

### 5.3. Hợp nhất khóa chính trước rồi đọc bản ghi

Một cách rõ ràng để giữ mỗi ticket một lần là hợp nhất ID:

~~~sql
WITH matched_ticket_ids AS (
    SELECT id
    FROM tickets
    WHERE assignee_id = :user_id

    UNION

    SELECT id
    FROM tickets
    WHERE reporter_id = :user_id
)
SELECT t.id, t.title, t.assignee_id, t.reporter_id
FROM tickets AS t
JOIN matched_ticket_ids AS m
  ON m.id = t.id;
~~~

UNION chỉ loại trùng trên khóa chính, sau đó truy vấn đọc các cột cần thiết. Cách này giữ một hàng cho mỗi ticket nếu id là khóa duy nhất và không NULL. Optimizer có thể inline CTE hoặc chọn cách thực thi khác tùy hệ quản trị; cần kiểm tra kế hoạch thực tế.

## 6. Dùng UNION ALL khi có thể chứng minh các nhánh rời nhau

Nếu có thể viết các nhánh sao cho mỗi hàng chỉ thuộc tối đa một nhánh, UNION ALL có thể tránh chi phí loại trùng mà vẫn giữ ngữ nghĩa OR.

Với ví dụ tickets, giả sử assignee_id có thể NULL. Có thể phân chia:

~~~sql
SELECT id, title, assignee_id, reporter_id
FROM tickets
WHERE assignee_id = :user_id

UNION ALL

SELECT id, title, assignee_id, reporter_id
FROM tickets
WHERE reporter_id = :user_id
  AND (assignee_id <> :user_id OR assignee_id IS NULL);
~~~

Nhánh đầu lấy các hàng có assignee khớp. Nhánh hai lấy các hàng có reporter khớp nhưng assignee không khớp hoặc là NULL. Vì vậy, một hàng không xuất hiện ở cả hai nhánh. Điều kiện IS NULL là cần thiết để bảo toàn hàng có assignee_id NULL nhưng reporter_id khớp.

Nếu assignee_id được khai báo NOT NULL, nhánh hai có thể đơn giản hơn:

~~~sql
WHERE reporter_id = :user_id
  AND assignee_id <> :user_id
~~~

Không dùng cách rút gọn này khi assignee_id có thể NULL. Với nhiều predicate phức tạp, việc tạo các nhánh rời nhau dễ sai do logic ba giá trị. Nếu khó chứng minh tính rời nhau, hợp nhất khóa chính bằng UNION thường dễ kiểm chứng hơn.

### 6.1. Quy tắc tổng quát

Với hai điều kiện P và Q, có thể chia tập hàng thỏa P OR Q thành hai tập rời nhau:

1. Nhánh thứ nhất lấy hàng P là TRUE.
2. Nhánh thứ hai lấy hàng Q là TRUE và P không TRUE.

Trong SQL, điều kiện “P không TRUE” phải xử lý cả FALSE và UNKNOWN. Không phải mọi hệ quản trị đều hỗ trợ cú pháp IS NOT TRUE giống nhau cho mọi biểu thức, vì vậy hãy diễn đạt rõ theo từng predicate và NULL semantics. Ví dụ assignee_id ở trên dùng điều kiện khác giá trị kết hợp với IS NULL để bao phủ cả hai trường hợp.

## 7. Ví dụ so sánh ba cách viết

Giả sử bảng tickets có 5 triệu hàng. Mỗi chỉ mục riêng tìm được khoảng 0,2% bảng, nhưng một ticket có thể khớp cả hai vai trò.

**Cách A — OR:**

~~~sql
SELECT id, title
FROM tickets
WHERE assignee_id = :user_id
   OR reporter_id = :user_id;
~~~

Optimizer có thể dùng index union/bitmap OR hoặc scan. Đây là baseline cần đo.

**Cách B — UNION:**

~~~sql
SELECT id, title
FROM tickets
WHERE assignee_id = :user_id

UNION

SELECT id, title
FROM tickets
WHERE reporter_id = :user_id;
~~~

Mỗi nhánh có cơ hội dùng chỉ mục riêng; UNION loại trùng theo id và title. Cách này giữ ngữ nghĩa hàng duy nhất trong ví dụ nếu id là khóa chính.

**Cách C — UNION ALL với nhánh rời nhau:**

~~~sql
SELECT id, title
FROM tickets
WHERE assignee_id = :user_id

UNION ALL

SELECT id, title
FROM tickets
WHERE reporter_id = :user_id
  AND (assignee_id <> :user_id OR assignee_id IS NULL);
~~~

Hai nhánh không giao nhau nên không cần bước loại trùng. Tuy nhiên, điều kiện bổ sung ở nhánh hai có thể làm kế hoạch khác đi. Cần xác nhận bằng actual plan và kiểm thử NULL, đồng thời bảo đảm kiểu dữ liệu và collation của các so sánh giống truy vấn gốc.

Không có kết luận trước rằng C nhanh nhất. Nếu OR đã được optimizer chuyển thành hai index seek và bitmap/index union hiệu quả, viết lại có thể không đem lại lợi ích. Nếu UNION phải sort/hash một tập ID lớn, chi phí loại trùng có thể cao hơn kế hoạch OR ban đầu.

## 8. Những trường hợp cần đặc biệt thận trọng khi tách

### 8.1. ORDER BY, LIMIT và phân trang

ORDER BY áp dụng cho kết quả cuối cùng của toàn bộ truy vấn. Khi tách thành nhiều nhánh, không được đặt LIMIT riêng cho mỗi nhánh rồi cho rằng kết quả tương đương với LIMIT toàn cục.

Ví dụ truy vấn gốc:

~~~sql
SELECT id, created_at
FROM events
WHERE source = 'API'
   OR severity = 'HIGH'
ORDER BY created_at DESC
LIMIT 20;
~~~

Nếu mỗi nhánh lấy 20 hàng rồi UNION ALL, sau khi hợp nhất và loại trùng có thể còn ít hơn 20 hàng, hoặc bỏ sót hàng thuộc top 20 toàn cục. Một cách viết lại đúng cần xác định đủ ứng viên của từng nhánh, hợp nhất theo khóa và áp dụng ORDER BY/LIMIT ở ngoài cùng. Nếu dùng Top-N cho từng nhánh, phải chứng minh giới hạn từng nhánh đủ để tạo top N toàn cục và xử lý trùng đúng.

### 8.2. GROUP BY, COUNT và SUM

Nếu mỗi nhánh tính COUNT hoặc SUM rồi UNION ALL, hàng khớp nhiều nhánh có thể bị tính hai lần. UNION trên các hàng tổng hợp cũng không tự động cộng các nhóm lại đúng cách.

Hãy hợp nhất khóa bản ghi trước khi tổng hợp, hoặc xây dựng các nhánh rời nhau rồi mới GROUP BY. Luôn kiểm tra kết quả tổng hợp với truy vấn gốc, nhất là khi có NULL và duplicate.

### 8.3. Join một-nhiều

Nếu mỗi nhánh join sang bảng con một-nhiều trước khi hợp nhất, một bản ghi cha có thể tạo nhiều hàng. Việc loại trùng sau join có thể làm mất hoặc giữ sai số lượng tùy projection. Khi mục tiêu là tìm tập bản ghi cha thỏa OR, hãy cân nhắc hợp nhất khóa chính của bảng cha trước rồi mới join sang bảng con.

### 8.4. Outer join và điều kiện nullable

Di chuyển predicate qua ON/WHERE hoặc tách nhánh quanh LEFT JOIN có thể thay đổi việc giữ hàng không khớp. Phải giữ nguyên ngữ nghĩa NULL extension của outer join. Không tách chỉ dựa trên việc hai điều kiện nhìn có vẻ độc lập.

### 8.5. Phân vùng và điều kiện thời gian

OR kết hợp điều kiện trên partition key với một điều kiện khác có thể làm partition pruning kém hiệu quả trong một số kế hoạch. Tách nhánh đôi khi giúp mỗi nhánh xác định partition rõ hơn, nhưng cũng có thể lặp đọc partition hoặc làm tăng số lần truy cập. Xem actual plan để biết số partition thực sự được quét.

### 8.6. Nhiều nhánh và danh sách rất dài

Tách một OR thành hàng chục hoặc hàng trăm nhánh làm SQL dài, tăng thời gian compile/optimize và có thể tạo kế hoạch phức tạp. Với danh sách ID lớn, nên xem xét đưa danh sách thành một quan hệ đầu vào và join/semi join, thay vì sinh SQL động với hàng trăm OR.

## 9. Hành vi của các hệ quản trị phổ biến

Tên operator và khả năng biến đổi khác nhau theo hệ quản trị, phiên bản, thống kê và cấu hình.

| Hệ quản trị | Cách xử lý thường gặp | Điều cần kiểm tra |
|---|---|---|
| PostgreSQL | Có thể kết hợp nhiều index scan bằng BitmapOr; IN trên cùng cột có thể trở thành điều kiện mảng/range phù hợp | Bitmap Index Scan, BitmapOr, Bitmap Heap Scan, Seq Scan, buffers và actual rows |
| SQL Server | Có thể dùng nhiều Index Seek, Index Union/Concatenation hoặc scan tùy cost; optimizer cũng có thể biến đổi OR | Actual Execution Plan, seek predicates, residual predicates, logical reads và lookup |
| MySQL | Range optimizer xử lý nhiều giá trị; Index Merge có thể hợp nhất kết quả nhiều chỉ mục cho OR | EXPLAIN/EXPLAIN ANALYZE, access type, Using union/Using sort_union, rows và iterator time |
| Oracle | Optimizer có thể thực hiện OR expansion, tạo các nhánh với CONCATENATION/UNION-ALL và điều kiện tránh trùng | Actual plan, OR expansion, index range scan, cardinality và buffer gets |

### 9.1. PostgreSQL

PostgreSQL có thể dùng BitmapOr để kết hợp các bitmap từ nhiều chỉ mục:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, email, phone
FROM customers
WHERE email = 'a@example.test'
   OR phone = '0900000000';
~~~

Nếu có chỉ mục phù hợp trên email và phone, kế hoạch có thể có Bitmap Index Scan cho từng nhánh, BitmapOr rồi Bitmap Heap Scan. Với tập kết quả lớn hoặc truy cập tuần tự rẻ hơn, planner có thể chọn Seq Scan.

Với IN trên một cột, PostgreSQL có thể dùng Index Scan hoặc Bitmap Index Scan tùy số giá trị và độ chọn lọc. Hãy xem actual rows, loops, buffers và thời gian; không dựa vào việc SQL có viết IN hay OR.

### 9.2. SQL Server

SQL Server có thể dùng Index Seek riêng cho các nhánh và hợp nhất row locator bằng Index Union hoặc operator tương đương. Trong một số trường hợp, optimizer chọn scan vì chi phí ước lượng của nhiều seek và lookup cao hơn.

Có thể kết hợp Actual Execution Plan với:

~~~sql
SET STATISTICS IO ON;
SET STATISTICS TIME ON;

-- Chạy truy vấn cần đo tại đây.

SET STATISTICS IO OFF;
SET STATISTICS TIME OFF;
~~~

So sánh logical reads, CPU, elapsed time và số lần Key Lookup. Nếu thử UNION, kiểm tra operator Sort/Hash để loại trùng và memory grant.

### 9.3. MySQL

MySQL có thể sử dụng Index Merge cho OR trên nhiều chỉ mục. EXPLAIN có thể hiển thị access type index_merge và thông tin union/sort_union trong Extra. Không phải mọi truy vấn OR đều dùng Index Merge; range optimizer cân nhắc số hàng, chi phí và cấu trúc index.

~~~sql
EXPLAIN ANALYZE
SELECT id, email, phone
FROM customers
WHERE email = 'a@example.test'
   OR phone = '0900000000';
~~~

Xem iterator, actual rows và thời gian. Nếu viết lại bằng UNION, xác nhận bước deduplicate không làm chi phí tăng cao.

### 9.4. Oracle Database

Oracle có thể thực hiện OR expansion để tách một truy vấn thành các nhánh, thường thể hiện bằng CONCATENATION hoặc UNION-ALL cùng predicate bổ sung để tránh trả trùng. Đây là biến đổi do optimizer thực hiện khi đánh giá có lợi; không cần tự viết lại trước khi xem kế hoạch.

Dùng EXPLAIN PLAN để xem ước lượng và DBMS_XPLAN.DISPLAY_CURSOR với thông tin thực thi khi có quyền để xem actual rows và buffer gets. So sánh kế hoạch trước/sau và xác định mỗi nhánh có dùng index range scan hay không.

## 10. Quy trình kiểm chứng trước khi giữ cách viết mới

1. **Lưu truy vấn gốc:** ghi SQL, tham số, kiểu dữ liệu, kết quả mong đợi và execution plan.
2. **Đo baseline:** thời gian, CPU, logical/physical reads, số hàng, buffer gets, temp I/O và mức tải đồng thời.
3. **Phân tích từng nhánh:** đo độ chọn lọc, số hàng thực tế, tỷ lệ giao nhau và chỉ mục sẵn có.
4. **Đọc kế hoạch OR/IN hiện tại:** xác định optimizer đang dùng scan, index combination, bitmap, index merge hay một chiến lược khác.
5. **Tạo một phương án viết lại:** IN cho nhiều giá trị cùng cột; UNION để hợp nhất khóa và loại trùng; UNION ALL chỉ khi nhánh rời nhau hoặc hàng trùng là chủ đích.
6. **Kiểm tra ngữ nghĩa:** thử NULL, duplicate, tham số biên, outer join, ORDER BY/LIMIT, GROUP BY và các trường hợp dữ liệu giao nhau.
7. **Đo trong cùng điều kiện:** dùng cùng snapshot, tham số, cache state, concurrency và máy phát tải.
8. **So sánh toàn bộ kế hoạch:** xem mỗi nhánh có dùng đúng index, có lookup lặp, Sort/Hash để loại trùng, spill hoặc đọc lặp hay không.
9. **Đánh giá độ ổn định:** thử tham số phổ biến và hiếm, dữ liệu nhỏ và lớn, cache nóng và tải đại diện.
10. **Giữ phương án có bằng chứng:** chỉ thay đổi SQL ứng dụng khi lợi ích đo được ổn định và kết quả nghiệp vụ giống truy vấn gốc.

Khi đo, không chỉ so sánh một lần chạy nhanh nhất. Hãy xem median và p95 nếu workload có nhiều lần thực thi, cùng throughput và tác động đến truy vấn khác. Một cách viết nhanh hơn khi chạy đơn lẻ nhưng tạo thêm I/O hoặc CPU khi concurrency cao có thể làm hệ thống kém ổn định.

## 11. Sai lầm thường gặp

- **Cho rằng IN luôn nhanh hơn OR:** hai cách viết cùng cột thường được optimizer chuẩn hóa tương tự.
- **Cho rằng OR luôn làm mất index:** nhiều engine có bitmap OR, index merge hoặc OR expansion.
- **Tách mọi nhánh thành UNION ALL:** các nhánh giao nhau sẽ làm hàng bị lặp so với OR.
- **Dùng UNION mà không xét projection:** UNION loại trùng theo toàn bộ cột SELECT, có thể gộp hai bản ghi khác nhau nếu không có khóa duy nhất trong projection.
- **Tách nhánh nhưng quên NULL:** điều kiện loại trùng có thể bỏ hàng có predicate UNKNOWN.
- **Tách truy vấn và đặt LIMIT riêng:** kết quả có thể khác top N toàn cục.
- **Tổng hợp từng nhánh rồi cộng:** hàng giao nhau có thể bị đếm hoặc cộng hai lần.
- **Đẩy predicate qua outer join:** có thể thay đổi tập hàng được giữ.
- **Không xem chi phí deduplicate:** UNION có thể tạo Sort hoặc Hash Aggregate lớn.
- **Không thử prepared statement:** giá trị tham số và plan cache có thể khiến kế hoạch khác với literal query.
- **Chỉ đo một tham số:** độ chọn lọc khác nhau có thể đảo ngược lựa chọn kế hoạch.

## 12. Checklist quyết định có nên tách OR hay không

- [ ] Đã xác định OR cùng cột hay trên nhiều cột.
- [ ] Đã kiểm tra IN có thể biểu diễn rõ hơn cùng ngữ nghĩa hay không.
- [ ] Đã đo selectivity và số hàng thực tế của từng nhánh.
- [ ] Đã xem các nhánh có giao nhau và tỷ lệ hàng trùng.
- [ ] Đã kiểm tra NULL và logic ba giá trị.
- [ ] Đã xem optimizer có thể kết hợp index hoặc thực hiện OR expansion không.
- [ ] Đã xác định UNION hay UNION ALL giữ đúng ngữ nghĩa kết quả.
- [ ] Nếu dùng UNION ALL, đã chứng minh các nhánh rời nhau.
- [ ] Nếu dùng UNION, projection có khóa duy nhất khi cần giữ từng bản ghi riêng không.
- [ ] Đã kiểm tra ORDER BY, LIMIT, phân trang, aggregate và outer join.
- [ ] Đã so sánh actual plan, reads, CPU, thời gian và temp I/O.
- [ ] Đã thử các giá trị tham số và mức concurrency đại diện.
- [ ] Đã đối chiếu kết quả nghiệp vụ giữa truy vấn gốc và truy vấn viết lại.

OR và IN là cách biểu đạt điều kiện hợp lệ; việc tách truy vấn chỉ đáng làm khi execution plan và phép đo chỉ ra lợi ích cụ thể. Hãy bảo toàn logic ba giá trị, kiểm soát hàng trùng bằng khóa duy nhất hoặc nhánh rời nhau, rồi đo cả chi phí tìm kiếm lẫn chi phí hợp nhất kết quả. Kết quả đúng và kế hoạch tốt hơn trên workload đại diện mới là căn cứ để giữ cách viết mới.
