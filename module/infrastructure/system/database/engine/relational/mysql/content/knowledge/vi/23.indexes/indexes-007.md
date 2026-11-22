# Index Merge và đánh đổi so với composite index

Khi một truy vấn lọc theo nhiều cột, MySQL có thể đọc nhiều index riêng rồi hợp nhất các hàng tìm được, hoặc đọc một composite index chứa nhiều cột trong cùng một B-tree. Chiến lược thứ nhất gọi là Index Merge; chiến lược thứ hai dùng chỉ mục ghép (composite index).

Index Merge giúp tận dụng các index đơn đã có, đặc biệt với một số điều kiện AND hoặc OR. Composite index thường cho đường truy cập trực tiếp hơn khi workload lặp lại một mẫu lọc nhiều cột ổn định. Không có lựa chọn nào luôn tốt hơn: quyết định phụ thuộc điều kiện WHERE, thứ tự cột, độ chọn lọc, ORDER BY, LIMIT, số hàng thực tế, dung lượng index và chi phí ghi.

Bài học thuộc phạm vi DATABASE_MYSQL: đọc kế hoạch thực thi, hiểu cách optimizer hợp nhất nhiều index, thiết kế composite index theo leftmost-prefix, đo hiệu năng bằng EXPLAIN và cân bằng tốc độ đọc với chi phí INSERT, UPDATE, DELETE.

## 1. Index Merge là gì?

Index Merge là access method của MySQL. Với một bảng, optimizer có thể thực hiện nhiều range scan trên các index khác nhau rồi kết hợp các row ID tìm được thành một tập kết quả.

Có ba thuật toán chính:

- **Intersection**: lấy phần giao của các tập row ID, thường phù hợp với các điều kiện AND.
- **Union**: lấy hợp của các tập row ID, thường phù hợp với các điều kiện OR.
- **Sort-Union**: thu thập row ID từ các range scan, sắp xếp rồi loại trùng để tạo hợp.

Index Merge không tạo một index mới và cũng không nối hai B-tree thành một cấu trúc lưu trữ lâu dài. Đây là chiến lược thực thi của một câu truy vấn. Các index thành phần vẫn là những index riêng biệt trên bảng.

Index Merge chỉ kết hợp các range scan của **cùng một bảng** trong một query block. Nó không hợp nhất index của nhiều bảng trong JOIN thành một index chung.

### 1.1. Ví dụ hình dung

Giả sử bảng ticket có hai index riêng:

- idx_ticket_customer trên customer_id.
- idx_ticket_status trên status.

Với điều kiện:

~~~sql
SELECT ticket_id, customer_id, status
FROM ticket
WHERE customer_id = 42
  AND status = 'OPEN';
~~~

Optimizer có thể:
1. Đọc idx_ticket_customer để lấy các ticket có customer_id = 42.
2. Đọc idx_ticket_status để lấy các ticket có status = 'OPEN'.
3. Lấy phần giao giữa hai tập row ID.
4. Truy cập các hàng cần trả về.

Đó là Index Merge intersection nếu optimizer chọn chiến lược này.

Một truy vấn OR:

~~~sql
SELECT ticket_id, customer_id, status
FROM ticket
WHERE customer_id = 42
   OR status = 'OPEN';
~~~

Có thể dùng Index Merge union:
1. Lấy row ID từ index customer.
2. Lấy row ID từ index status.
3. Hợp hai tập và loại row ID trùng.
4. Đọc hàng tương ứng.

Optimizer có thể chọn một kế hoạch khác nếu chi phí thấp hơn, chẳng hạn chỉ dùng một index hoặc quét toàn bảng.

## 2. Chuẩn bị bảng thực hành

Tạo bảng có các index đơn:

~~~sql
CREATE TABLE ticket (
    ticket_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    status VARCHAR(20) NOT NULL,
    priority TINYINT UNSIGNED NOT NULL,
    created_at DATETIME(6) NOT NULL,
    title VARCHAR(200) NOT NULL,
    PRIMARY KEY (ticket_id),
    KEY idx_ticket_customer (customer_id),
    KEY idx_ticket_status (status),
    KEY idx_ticket_priority (priority),
    KEY idx_ticket_created (created_at)
) ENGINE = InnoDB;
~~~

Các index đơn cho phép optimizer cân nhắc từng điều kiện riêng. Để quan sát Index Merge, cần dữ liệu đủ lớn và phân bố giá trị đại diện. Với bảng chỉ có vài hàng, full table scan có thể rẻ hơn nhiều range scan; vì vậy ví dụ nhỏ chỉ giúp hiểu cú pháp, không bảo đảm EXPLAIN sẽ chọn Index Merge.

Kiểm tra index hiện tại:

~~~sql
SHOW INDEX FROM ticket;
~~~

Kiểm tra số lượng hàng và phân bố:

~~~sql
SELECT
    status,
    COUNT(*) AS ticket_count
FROM ticket
GROUP BY status
ORDER BY ticket_count DESC;
~~~

Độ chọn lọc (selectivity) cho biết điều kiện lọc được bao nhiêu hàng so với tổng số hàng. Một điều kiện trả về phần lớn bảng có thể không đáng dùng index vì chi phí đọc index rồi truy cập hàng có thể cao hơn quét bảng.

## 3. Intersection: hợp nhất theo phép giao

Index Merge intersection có thể được cân nhắc khi WHERE chứa các điều kiện AND, mỗi điều kiện có thể dùng một range scan trên index.

Ví dụ:

~~~sql
EXPLAIN
SELECT ticket_id, customer_id, status
FROM ticket
WHERE customer_id = 42
  AND status = 'OPEN';
~~~

Nếu optimizer chọn intersection, EXPLAIN truyền thống thường hiển thị:

- type = index_merge.
- key liệt kê nhiều index được dùng.
- Extra có dạng Using intersect(idx_ticket_customer,idx_ticket_status).

Tên index và cách trình bày có thể khác theo truy vấn, phiên bản và định dạng EXPLAIN.

### 3.1. Cách intersection hoạt động

Về mặt logic:

- Tập A: các row ID tìm được từ idx_ticket_customer.
- Tập B: các row ID tìm được từ idx_ticket_status.
- Kết quả: A ∩ B.

Chỉ các hàng thỏa cả hai điều kiện mới được trả về. Với InnoDB, secondary index lưu kèm primary key, vì vậy engine có thể dùng primary key để nhận diện hàng trong quá trình hợp nhất.

Intersection có thể tiết kiệm việc đọc hàng không thỏa đủ điều kiện, nhưng nó phải đọc nhiều index và kết hợp các tập row ID. Nếu một index đã đủ chọn lọc, hoặc kết hợp tạo ra nhiều row ID trung gian, chi phí merge có thể lớn hơn lợi ích.

### 3.2. Khi nào intersection có thể hữu ích?

- Bảng có nhiều index đơn phù hợp với các predicate AND.
- Mỗi predicate lọc được một tập hàng tương đối nhỏ.
- Không có composite index phù hợp hoặc workload thay đổi nhiều tổ hợp điều kiện.
- Optimizer ước tính chi phí hợp nhất thấp hơn các access path khác.

### 3.3. Vì sao composite index thường có lợi cho mẫu AND ổn định?

Với truy vấn customer_id = 42 AND status = 'OPEN', có thể tạo:

~~~sql
CREATE INDEX idx_ticket_customer_status
ON ticket (customer_id, status);
~~~

Một B-tree ghép cho phép định vị theo tiền tố customer_id rồi status. Thay vì đọc hai index riêng và giao hai tập row ID, MySQL có thể thực hiện một range/ref access trên composite index.

Điều này thường giảm công việc hợp nhất và số lần truy cập cấu trúc index. Tuy nhiên, optimizer vẫn chọn theo cost; không thể khẳng định composite index luôn thắng nếu phân bố dữ liệu, kích thước bảng hoặc workload khác nhau.

## 4. Union: hợp nhất theo phép OR

Index Merge union phù hợp với một số điều kiện OR khi mỗi nhánh có thể dùng index riêng.

Ví dụ:

~~~sql
EXPLAIN
SELECT ticket_id, customer_id, status
FROM ticket
WHERE customer_id = 42
   OR status = 'OPEN';
~~~

Nếu optimizer chọn union, Extra có thể hiển thị:

~~~text
Using union(idx_ticket_customer,idx_ticket_status)
~~~

Về logic:

- Tập A: row ID của customer_id = 42.
- Tập B: row ID của status = 'OPEN'.
- Kết quả: A ∪ B.

Một hàng thỏa cả hai điều kiện chỉ xuất hiện một lần trong kết quả truy vấn. Index Merge union hợp nhất row ID chứ không cộng nguyên hai danh sách hàng có thể trùng nhau.

### 4.1. Composite index có giải quyết được OR giữa hai cột khác nhau không?

Composite index:

~~~sql
CREATE INDEX idx_ticket_customer_status
ON ticket (customer_id, status);
~~~

có thể phục vụ truy vấn theo customer_id, hoặc customer_id kết hợp status. Nhưng nó không có leftmost prefix là status. Vì vậy, truy vấn chỉ lọc status = 'OPEN' không thể dùng composite index này như một range lookup trực tiếp theo status.

Với điều kiện:

~~~sql
WHERE customer_id = 42
   OR status = 'OPEN'
~~~

một index ghép (customer_id, status) không tự thay thế hai index đơn. Optimizer có thể tiếp tục dùng Index Merge với các index đơn, dùng một access path khác hoặc quét bảng.

Đây là lý do workload có nhiều điều kiện OR trên các cột độc lập có thể cần các index riêng, ngay cả khi bảng đã có một vài composite index.

### 4.2. OR trên cùng một cột

Không phải mọi OR đều cần Index Merge.

~~~sql
SELECT ticket_id
FROM ticket
WHERE status = 'OPEN'
   OR status = 'PENDING';
~~~

Có thể viết rõ hơn:

~~~sql
SELECT ticket_id
FROM ticket
WHERE status IN ('OPEN', 'PENDING');
~~~

Optimizer thường có thể biểu diễn nhiều giá trị trên cùng một index bằng nhiều range. Hãy xem EXPLAIN trước khi kết luận đây là Index Merge.

## 5. Sort-Union: hợp rồi sắp xếp row ID

Sort-Union cũng hợp nhất kết quả từ nhiều range scan, nhưng phải thu thập row ID rồi sắp xếp chúng trước khi tạo kết quả hợp nhất.

Một truy vấn có các nhánh OR dạng range trên các cột khác nhau có thể là ứng viên:

~~~sql
EXPLAIN
SELECT ticket_id, priority, created_at
FROM ticket
WHERE priority BETWEEN 3 AND 5
   OR created_at >= '2025-01-01 00:00:00';
~~~

Nếu optimizer chọn sort-union, Extra có thể hiển thị:

~~~text
Using sort_union(idx_ticket_priority,idx_ticket_created)
~~~

Đây là ví dụ ứng viên, không phải bảo đảm MySQL sẽ chọn sort-union. Kết quả phụ thuộc thống kê, độ chọn lọc, số hàng, phiên bản và cost model. Một truy vấn có thể dùng union, sort-union, một index đơn hoặc full scan.

### 5.1. Vì sao sort-union có thể đắt?

Sort-Union cần:
1. Thu thập row ID từ các range scan.
2. Sắp xếp các row ID.
3. Loại row ID trùng.
4. Truy cập hàng để lấy cột đầu ra.

Nếu mỗi nhánh trả về nhiều hàng, tập row ID trung gian có thể lớn. Việc sắp xếp tiêu tốn CPU và bộ nhớ; trong một số tình huống có thể phát sinh dữ liệu tạm trên đĩa.

Với truy vấn có LIMIT nhỏ, sort-union vẫn có thể phải thu thập và sắp xếp nhiều row ID trước khi trả đủ kết quả. Một access path có thứ tự phù hợp có thể dừng sớm hiệu quả hơn.

### 5.2. Không nhầm sort-union với ORDER BY của kết quả

Sort-Union sắp xếp row ID để hợp nhất tập hàng. Nó không bảo đảm kết quả được sắp xếp theo created_at, priority hoặc cột nghiệp vụ mà ứng dụng yêu cầu.

Muốn thứ tự đầu ra ổn định:

~~~sql
SELECT ticket_id, priority, created_at
FROM ticket
WHERE priority BETWEEN 3 AND 5
   OR created_at >= '2025-01-01 00:00:00'
ORDER BY created_at DESC, ticket_id DESC;
~~~

ORDER BY ngoài cùng vẫn là điều kiện bảo đảm thứ tự. Nếu access path không cung cấp thứ tự cần thiết, MySQL có thể phải dùng filesort.

## 6. Composite index là gì?

Composite index (multi-column index) là một index chứa từ hai cột trở lên. InnoDB lưu các giá trị theo thứ tự cột đã khai báo trong B-tree.

Ví dụ:

~~~sql
CREATE INDEX idx_ticket_customer_status_created
ON ticket (customer_id, status, created_at);
~~~

Thứ tự khóa là:

1. customer_id.
2. status trong phạm vi customer_id.
3. created_at trong phạm vi cặp customer_id và status.

Composite index có thể phục vụ nhiều mẫu truy vấn bắt đầu bằng tiền tố trái của index.

### 6.1. Leftmost-prefix principle

Với index:

~~~sql
(customer_id, status, created_at)
~~~

Các tiền tố thường có thể được dùng để định vị:

- customer_id.
- customer_id, status.
- customer_id, status, created_at.

Các truy vấn chỉ có điều kiện status hoặc chỉ created_at không có tiền tố trái phù hợp.

| Điều kiện lọc | Khả năng dùng index ghép trên |
|---|---|
| customer_id = 42 | Có, dùng cột đầu |
| customer_id = 42 AND status = 'OPEN' | Có, dùng hai cột đầu |
| customer_id = 42 AND status = 'OPEN' AND created_at >= ... | Có, dùng cả tiền tố và range trên cột ngày |
| status = 'OPEN' | Không dùng được để định vị trực tiếp theo tiền tố trái |
| created_at >= ... | Không dùng được để định vị trực tiếp theo tiền tố trái |
| status = 'OPEN' AND created_at >= ... | Không có tiền tố customer_id nên thường cần index khác |

Optimizer có thể chọn scan toàn bộ index trong một số tình huống, nhưng điều đó khác với range lookup hiệu quả theo tiền tố trái. Không hiểu quy tắc leftmost-prefix thành quy tắc rằng các cột phía sau hoàn toàn vô dụng: chúng vẫn có thể giúp covering hoặc được xét qua các cơ chế tối ưu khác, nhưng không tạo ra một lookup trực tiếp giống như có cột dẫn đầu.

### 6.2. Equality trước, range sau

Với truy vấn:

~~~sql
SELECT ticket_id, created_at
FROM ticket
WHERE customer_id = 42
  AND status = 'OPEN'
  AND created_at >= '2025-01-01 00:00:00'
  AND created_at <  '2025-02-01 00:00:00';
~~~

Index:

~~~sql
(customer_id, status, created_at)
~~~

phù hợp với hai điều kiện equality ở đầu và khoảng ngày ở sau. MySQL có thể định vị đúng nhóm customer/status rồi đọc range created_at.

Quy tắc equality trước, range sau là điểm khởi đầu hữu ích, không phải công thức tuyệt đối. Cần xem thêm ORDER BY, GROUP BY, các truy vấn khác dùng cùng index và selectivity.

### 6.3. Range thường giới hạn việc dùng các cột phía sau để thu hẹp phạm vi

Với index (customer_id, created_at, status), truy vấn:

~~~sql
WHERE customer_id = 42
  AND created_at >= '2025-01-01'
  AND status = 'OPEN'
~~~

có thể dùng customer_id và range created_at để định vị. Cột status phía sau range không thường giúp tạo một range liên tục nhỏ hơn theo cùng cách cột equality trước range có thể làm; tuy nhiên, nó vẫn có thể được kiểm tra từ index hoặc hỗ trợ covering/Index Condition Pushdown tùy kế hoạch.

Vì vậy, nếu status là điều kiện equality luôn đi cùng customer_id trước khoảng ngày, thứ tự (customer_id, status, created_at) thường là ứng viên tốt hơn. Hãy xác nhận bằng EXPLAIN và dữ liệu thực.

## 7. So sánh Index Merge intersection với composite index

Giả sử workload thường xuyên chạy:

~~~sql
SELECT ticket_id, created_at
FROM ticket
WHERE customer_id = 42
  AND status = 'OPEN';
~~~

Hai cách tiếp cận:

**Cách A: index đơn và Index Merge**

~~~sql
KEY idx_ticket_customer (customer_id),
KEY idx_ticket_status (status)
~~~

Optimizer có thể đọc hai index rồi lấy giao row ID.

**Cách B: composite index**

~~~sql
KEY idx_ticket_customer_status (customer_id, status)
~~~

Optimizer có thể dùng một index range theo cả hai điều kiện.

| Tiêu chí | Index Merge intersection | Composite index |
|---|---|---|
| Cấu trúc lưu trữ | Nhiều index đơn | Một B-tree nhiều cột |
| Cách tìm | Range scan riêng rồi giao row ID | Một range/ref access theo tiền tố ghép |
| Chi phí hợp nhất | Có bước kết hợp row ID | Thường không cần giao nhiều tập row ID |
| Linh hoạt | Có thể tái sử dụng index đơn cho nhiều tổ hợp | Phụ thuộc thứ tự cột và leftmost prefix |
| ORDER BY | Thường khó cung cấp thứ tự nghiệp vụ cần | Có thể hỗ trợ thứ tự nếu khớp tiền tố và hướng sort |
| Covering | Tùy các index và cột được đọc | Có thể bao phủ truy vấn bằng một index |
| Chi phí ghi | Duy trì từng index đơn | Duy trì index ghép; có thể thay thế một số index đơn nếu workload cho phép |
| Dung lượng | Nhiều B-tree riêng | Một B-tree rộng hơn |
| Khi phù hợp | Predicate thay đổi, mỗi cột cần index riêng | Mẫu AND lặp lại, ổn định và có thứ tự truy cập rõ |

Composite index thường thắng trong truy vấn AND ổn định vì nó định vị theo một cấu trúc B-tree duy nhất. Nhưng nếu ứng dụng cũng có nhiều truy vấn chỉ lọc customer_id hoặc chỉ lọc status, index đơn vẫn có thể có giá trị độc lập.

## 8. So sánh Index Merge union với composite index

Với điều kiện OR:

~~~sql
WHERE customer_id = 42
   OR status = 'OPEN'
~~~

hai index đơn có thể cho phép Index Merge union.

Composite index (customer_id, status) không có leftmost prefix status. Nó không thay thế trực tiếp index status cho nhánh OR đó.

| Mẫu truy vấn | Index phù hợp để đánh giá |
|---|---|
| customer_id = ? | Index customer hoặc composite bắt đầu bằng customer_id |
| status = ? | Index status hoặc composite bắt đầu bằng status |
| customer_id = ? AND status = ? | Composite (customer_id, status) |
| customer_id = ? OR status = ? | Hai index đơn và Index Merge union; cũng có thể thử cách viết khác sau khi xác minh semantics |
| status = ? AND created_at trong khoảng | Composite (status, created_at) |
| customer_id = ? AND status = ? AND created_at trong khoảng | Composite (customer_id, status, created_at) |

Một composite index không thể tối ưu mọi hoán vị điều kiện. Thứ tự cột quyết định tiền tố nào có thể dùng. Nếu workload có hai nhóm truy vấn độc lập, có thể cần hai index ghép khác nhau, nhưng phải cân nhắc chi phí ghi và dung lượng.

## 9. Index Merge và truy vấn OR viết lại bằng UNION

Một số truy vấn OR có thể được viết thành các nhánh UNION để tạo access path riêng. Tuy nhiên, không được thay thế máy móc vì semantics loại trùng khác nhau.

Ví dụ:

~~~sql
SELECT ticket_id, customer_id, status
FROM ticket
WHERE customer_id = 42
   OR status = 'OPEN';
~~~

Có thể viết:

~~~sql
SELECT ticket_id, customer_id, status
FROM ticket
WHERE customer_id = 42

UNION

SELECT ticket_id, customer_id, status
FROM ticket
WHERE status = 'OPEN';
~~~

UNION mặc định loại bỏ các hàng trùng trên toàn bộ cột kết quả. Trong khi điều kiện OR của một SELECT chỉ trả mỗi hàng của bảng một lần. Với cùng projection và cùng bảng, UNION DISTINCT thường giữ semantics hàng tương tự, nhưng phải tính thêm chi phí khử trùng.

Nếu dùng UNION ALL, hàng thỏa cả hai nhánh có thể xuất hiện hai lần:

~~~sql
SELECT ticket_id, customer_id, status
FROM ticket
WHERE customer_id = 42

UNION ALL

SELECT ticket_id, customer_id, status
FROM ticket
WHERE status = 'OPEN';
~~~

Đây không tương đương với OR nếu có hàng thỏa cả hai điều kiện.

Nếu chỉ lấy ID trong từng nhánh rồi JOIN lại, cần kiểm tra unique key và cách khử trùng. Việc viết lại cũng có thể thay đổi ORDER BY, LIMIT và kế hoạch thực thi. Hãy chỉ dùng khi đo được lợi ích và xác nhận kết quả giống nhau trên dữ liệu biên.

## 10. Composite index có thể bao phủ truy vấn

Covering index là index chứa đủ các cột cần để lọc và trả kết quả, giúp MySQL có thể đọc dữ liệu từ index mà không phải truy cập thêm clustered record trong một số kế hoạch.

Ví dụ:

~~~sql
CREATE INDEX idx_ticket_customer_status_created
ON ticket (customer_id, status, created_at);
~~~

Truy vấn:

~~~sql
SELECT ticket_id, created_at
FROM ticket
WHERE customer_id = 42
  AND status = 'OPEN';
~~~

Với InnoDB, secondary index lưu kèm primary key. Vì ticket_id là primary key, index ghép có thể chứa đủ customer_id, status, created_at và ticket_id để phục vụ truy vấn này mà không cần đọc thêm cột title hoặc các cột khác từ hàng chính. EXPLAIN có thể hiển thị Using index nếu kế hoạch là covering.

Index Merge từ hai index đơn có thể vẫn phải truy cập clustered record để kiểm tra cột và lấy dữ liệu đầu ra. Một composite index phù hợp có thể giảm random lookup và I/O.

Không thêm mọi cột SELECT vào index chỉ để tạo covering. Index quá rộng:
- Tốn dung lượng.
- Làm giảm số entry trên mỗi page.
- Tăng cache pressure.
- Tăng chi phí INSERT/UPDATE/DELETE.
- Có thể làm tăng thời gian build và bảo trì index.

Hãy chỉ tạo covering index cho truy vấn quan trọng, chạy thường xuyên và có lợi ích đo được.

## 11. Thứ tự cột trong composite index

Thứ tự cột phải dựa trên mẫu truy vấn, không chỉ dựa vào cột nào có cardinality cao nhất.

### 11.1. Equality columns và range column

Với truy vấn:

~~~sql
WHERE customer_id = ?
  AND status = ?
  AND created_at >= ?
  AND created_at < ?
~~~

Ứng viên:

~~~sql
(customer_id, status, created_at)
~~~

Hai cột equality đứng trước, cột range đứng sau.

### 11.2. Query cần ORDER BY

~~~sql
SELECT ticket_id, created_at
FROM ticket
WHERE customer_id = 42
  AND status = 'OPEN'
ORDER BY created_at DESC
LIMIT 20;
~~~

Index:

~~~sql
(customer_id, status, created_at)
~~~

có thể hỗ trợ lọc theo hai cột đầu và truy cập theo created_at. Khả năng đáp ứng chiều DESC và tránh filesort còn phụ thuộc phiên bản, định nghĩa index, hướng sort và các cột ORDER BY. Với MySQL hỗ trợ descending index, có thể đánh giá:

~~~sql
CREATE INDEX idx_ticket_customer_status_created_desc
ON ticket (customer_id, status, created_at DESC);
~~~

Đừng tạo cả ASC và DESC nếu chưa có bằng chứng workload cần. MySQL có thể scan index theo chiều ngược trong nhiều trường hợp.

### 11.3. Cột có độ chọn lọc thấp

Cột status có ít giá trị như OPEN, CLOSED, PENDING thường có cardinality thấp. Điều đó không có nghĩa cột này luôn phải đứng cuối hoặc không đáng index. Nếu status được kết hợp với customer_id và date, vị trí của nó phải phục vụ mẫu truy vấn và thứ tự lọc thực tế.

Một index ghép có thể hiệu quả dù cột đầu tiên không phải cột có cardinality cao nhất, nếu predicate trên cột đó luôn có mặt và giúp định vị nhóm dữ liệu phù hợp.

### 11.4. Leftmost prefix và các truy vấn khác

Index (customer_id, status, created_at) có thể phục vụ truy vấn chỉ có customer_id, nhưng không trực tiếp phục vụ status-only hoặc created_at-only như một index bắt đầu bằng các cột đó.

Nếu workload có truy vấn status-only quan trọng, có thể cần idx_ticket_status hoặc composite index bắt đầu bằng status. Đừng xóa index đơn chỉ vì đã thêm index ghép có chứa cột đó ở vị trí thứ hai.

## 12. Vì sao optimizer không luôn chọn Index Merge?

Optimizer ước lượng chi phí của nhiều access path rồi chọn phương án được dự đoán rẻ nhất. Index Merge có thể không được chọn khi:

- Một index đơn đã lọc đủ chọn lọc.
- Full table scan rẻ hơn vì điều kiện trả về nhiều hàng.
- Chi phí đọc nhiều index và hợp nhất row ID cao.
- Composite index cung cấp một range tốt hơn.
- Thống kê index chưa phản ánh dữ liệu thực.
- Predicate không sargable hoặc không thể chuyển thành range scan phù hợp.
- ORDER BY hoặc LIMIT khiến một access path khác có lợi hơn.

Ví dụ không sargable:

~~~sql
SELECT ticket_id
FROM ticket
WHERE YEAR(created_at) = 2025;
~~~

Hàm YEAR áp dụng lên cột có thể khiến index B-tree thông thường trên created_at khó dùng làm range theo thời gian. Viết khoảng nửa mở:

~~~sql
SELECT ticket_id
FROM ticket
WHERE created_at >= '2025-01-01 00:00:00'
  AND created_at <  '2026-01-01 00:00:00';
~~~

Predicate có thể định vị range trực tiếp trên created_at.

### 12.1. Cập nhật thống kê

Sau khi tải lượng dữ liệu lớn hoặc thay đổi phân bố, có thể cập nhật thống kê:

~~~sql
ANALYZE TABLE ticket;
~~~

Thống kê giúp optimizer ước lượng cardinality và chi phí. ANALYZE TABLE không bảo đảm một kế hoạch cụ thể sẽ được chọn; nó chỉ cập nhật thông tin phục vụ quyết định.

## 13. Đọc EXPLAIN để nhận diện Index Merge

Ví dụ:

~~~sql
EXPLAIN
SELECT ticket_id
FROM ticket
WHERE customer_id = 42
  AND status = 'OPEN';
~~~

Trong EXPLAIN dạng bảng, chú ý:

| Cột | Ý nghĩa |
|---|---|
| type | Nếu là index_merge, optimizer dùng Index Merge access method |
| key | Có thể liệt kê nhiều index được dùng |
| rows | Số hàng ước tính cần đọc |
| filtered | Tỷ lệ hàng ước tính còn lại sau điều kiện |
| Extra | Có thể ghi Using intersect(...), Using union(...) hoặc Using sort_union(...) |

Nếu type không phải index_merge, không có nghĩa truy vấn sai. Optimizer có thể chọn ref, range, index hoặc ALL tùy chi phí.

### 13.1. EXPLAIN FORMAT=TREE

~~~sql
EXPLAIN FORMAT=TREE
SELECT ticket_id, customer_id, status
FROM ticket
WHERE customer_id = 42
   OR status = 'OPEN';
~~~

TREE trình bày các iterator và cách truy cập dữ liệu theo cấu trúc. Đây là cách hữu ích để đọc kế hoạch phức tạp hơn.

### 13.2. EXPLAIN ANALYZE

~~~sql
EXPLAIN ANALYZE
SELECT ticket_id, customer_id, status
FROM ticket
WHERE customer_id = 42
   OR status = 'OPEN';
~~~

EXPLAIN ANALYZE thực thi câu SELECT và báo thời gian cùng số hàng thực tế ở các iterator. So sánh:
- Estimated rows và actual rows.
- Số vòng lặp.
- Thời gian ở từng iterator.
- Chi phí hợp nhất và truy cập hàng.
- Số hàng trả cuối cùng.

EXPLAIN ANALYZE thực sự chạy truy vấn. Thử trên dữ liệu đại diện và môi trường phù hợp; không dùng tùy tiện cho truy vấn quá nặng trên production.

## 14. So sánh kế hoạch bằng cách tắt Index Merge trong session

Để kiểm tra Index Merge có thực sự giúp ích, có thể tắt chiến lược này tạm thời ở session thử nghiệm:

~~~sql
SELECT @@SESSION.optimizer_switch;

SET SESSION optimizer_switch = 'index_merge=off';

EXPLAIN
SELECT ticket_id
FROM ticket
WHERE customer_id = 42
  AND status = 'OPEN';

SET SESSION optimizer_switch = 'index_merge=on';
~~~

Có thể bật/tắt riêng các nhánh:
- index_merge_intersection.
- index_merge_union.
- index_merge_sort_union.

Ví dụ:

~~~sql
SET SESSION optimizer_switch = 'index_merge_intersection=off';
~~~

Việc tắt Index Merge chỉ phục vụ so sánh kế hoạch. Không mặc định rằng kế hoạch mới nhanh hơn. Trước khi thay đổi, lưu cấu hình optimizer_switch hiện tại để khôi phục đúng trạng thái session. Không dùng SET GLOBAL trong thử nghiệm thông thường vì sẽ ảnh hưởng các session mới.

Có thể dùng optimizer hints khi cần kiểm soát kế hoạch cho một truy vấn cụ thể, nhưng hint là công cụ cuối cùng sau khi đã hiểu dữ liệu và cost model. Hint có thể làm kế hoạch kém đi khi dữ liệu thay đổi.

## 15. Đánh đổi dung lượng và chi phí ghi

Mỗi index là một cấu trúc dữ liệu cần lưu và bảo trì.

### 15.1. Nhiều index đơn

Ưu điểm:
- Mỗi index có thể phục vụ truy vấn riêng trên một cột.
- Có thể kết hợp bằng Index Merge khi predicate phù hợp.
- Dễ tái sử dụng trong nhiều truy vấn khác nhau.

Chi phí:
- Mỗi INSERT phải cập nhật các index liên quan.
- UPDATE cột được index có thể phải sửa nhiều B-tree.
- DELETE phải loại entry khỏi các index.
- Tốn dung lượng và buffer pool.
- Index Merge có thể phải đọc nhiều cấu trúc và hợp nhất row ID.

### 15.2. Composite index

Ưu điểm:
- Một range scan có thể xử lý nhiều predicate theo tiền tố.
- Có thể hỗ trợ ORDER BY/GROUP BY nếu thứ tự phù hợp.
- Có thể trở thành covering index.
- Có thể thay thế một số index đơn trùng chức năng.

Chi phí:
- Entry thường rộng hơn index đơn.
- Tốn dung lượng và cache.
- Ghi dữ liệu phải duy trì index ghép.
- Chỉ hữu ích cho các truy vấn phù hợp leftmost prefix.
- Thay đổi thứ tự cột có thể làm mất khả năng phục vụ truy vấn khác.

### 15.3. Không giữ mọi index vì optimizer có thể merge

Nếu giữ idx_customer và idx_status chỉ vì Index Merge intersection, nhưng workload chính luôn lọc cả customer_id và status, composite index có thể giảm chi phí đọc. Tuy nhiên, trước khi xóa index đơn, hãy kiểm tra:
- Truy vấn chỉ lọc customer_id.
- Truy vấn chỉ lọc status.
- JOIN dùng từng cột.
- UNIQUE/FK và các ràng buộc.
- Các truy vấn báo cáo hoặc job nền.
- Kế hoạch của các truy vấn khác sau khi xóa.

Index có thể phục vụ nhiều workload ngoài truy vấn đang tối ưu.

## 16. Index Merge không thay thế index cho JOIN

Index Merge chỉ hợp nhất range scan trên cùng một bảng. Với JOIN:

~~~sql
SELECT
    t.ticket_id,
    c.customer_name
FROM ticket AS t
JOIN customer AS c
  ON c.customer_id = t.customer_id
WHERE t.status = 'OPEN';
~~~

Optimizer chọn access path riêng cho ticket và customer, sau đó thực hiện join. Nó không tạo Index Merge kết hợp index của cả hai bảng.

Index trên ticket.status, ticket.customer_id và customer.customer_id có thể hỗ trợ các bước khác nhau. Nếu bảng ticket thường lọc status rồi JOIN theo customer_id, composite index có thể được đánh giá theo thứ tự truy vấn và cardinality. Không suy luận Index Merge của một bảng sẽ thay thế index join key.

## 17. Ví dụ thiết kế theo workload

Giả sử hệ thống ticket có các truy vấn thường xuyên:

A. Tra cứu ticket của một khách hàng theo trạng thái:

~~~sql
SELECT ticket_id, created_at, title
FROM ticket
WHERE customer_id = ?
  AND status = ?
ORDER BY created_at DESC
LIMIT 20;
~~~

Ứng viên:

~~~sql
CREATE INDEX idx_ticket_customer_status_created
ON ticket (customer_id, status, created_at);
~~~

B. Lọc ticket theo trạng thái và khoảng thời gian:

~~~sql
SELECT ticket_id, customer_id, created_at
FROM ticket
WHERE status = ?
  AND created_at >= ?
  AND created_at < ?
ORDER BY created_at DESC;
~~~

Ứng viên:

~~~sql
CREATE INDEX idx_ticket_status_created
ON ticket (status, created_at);
~~~

C. Tìm ticket theo khách hàng hoặc trạng thái:

~~~sql
SELECT ticket_id
FROM ticket
WHERE customer_id = ?
   OR status = ?;
~~~

Có thể đánh giá hai index đơn và Index Merge union. Hai index ghép ở trên không tự thay thế mọi nhánh OR.

Không nhất thiết tạo cả ba index ngay. Hãy xếp hạng truy vấn theo tần suất, độ trễ, số hàng đọc và tác động nghiệp vụ; sau đó kiểm tra index nào được dùng chung và index nào dư thừa.

## 18. Các lỗi thường gặp

| Hiểu nhầm hoặc lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Index Merge luôn nhanh hơn full scan | Bỏ qua chi phí đọc nhiều index và hợp nhất row ID | So sánh actual rows và thời gian |
| Có index đơn thì MySQL chắc chắn intersection | Optimizer chọn theo cost | Xem EXPLAIN; không giả định |
| Composite index thay thế được mọi index đơn | Vi phạm leftmost-prefix khi truy vấn cột phía sau riêng lẻ | Kiểm tra toàn bộ workload |
| Index (a,b) dùng tốt cho điều kiện chỉ có b | b không phải tiền tố trái | Tạo index bắt đầu bằng b nếu workload cần |
| Index Merge union tương đương UNION ALL | Hàng thỏa nhiều nhánh OR chỉ trả một lần | UNION ALL có thể tạo bản sao |
| Sort-Union bảo đảm ORDER BY nghiệp vụ | Nó sắp row ID để hợp nhất | Khai báo ORDER BY ngoài cùng |
| Composite index luôn cần cột cardinality cao nhất đầu tiên | Chỉ xét selectivity, bỏ qua equality/range và workload | Thiết kế theo predicate và thứ tự truy vấn |
| Thêm nhiều index luôn làm SELECT nhanh hơn | Chi phí ghi, dung lượng và cache tăng | Chỉ giữ index có ích đo được |
| EXPLAIN rows là số hàng thực tế | Đây là ước lượng | Dùng EXPLAIN ANALYZE để xem actual rows |
| Tắt Index Merge chứng minh composite index tốt hơn | Kế hoạch thay thế có thể khác và dữ liệu nhỏ không đại diện | Benchmark trên dữ liệu thực tế |
| Index Merge kết hợp index của nhiều bảng JOIN | Access method áp dụng cho một bảng | Đánh giá access path của từng bảng trong JOIN |

## 19. Quy trình lựa chọn Index Merge hay composite index

Khi gặp truy vấn lọc nhiều cột:

1. Ghi lại SQL thực tế, tần suất chạy và yêu cầu độ trễ.
2. Xác định truy vấn dùng AND, OR hay kết hợp nhiều nhóm điều kiện.
3. Kiểm tra index hiện có bằng SHOW INDEX.
4. Chạy EXPLAIN và nhận diện type=index_merge hay access path khác.
5. Nếu là intersection, đánh giá composite index theo thứ tự equality, range và ORDER BY.
6. Nếu là union, xác định các cột độc lập trong OR và xem có cần index đơn riêng.
7. Nếu là sort-union, kiểm tra kích thước tập row ID và chi phí sort.
8. Đánh giá selectivity và thống kê; dùng ANALYZE TABLE khi cần.
9. Tạo index thử nghiệm trên staging hoặc bản sao dữ liệu.
10. So sánh EXPLAIN FORMAT=TREE và EXPLAIN ANALYZE trước/sau.
11. Kiểm tra covering, filesort, temporary operation, actual rows và thời gian.
12. Đo cả chi phí ghi và dung lượng sau khi thêm index.
13. Chỉ xóa index đơn sau khi xác minh không còn workload nào cần.
14. Theo dõi kế hoạch sau khi dữ liệu và phân bố giá trị thay đổi.

## 20. Bài tập thực hành

### Bài 1: Quan sát intersection

Dùng bảng ticket với idx_ticket_customer và idx_ticket_status. Tạo dữ liệu đủ lớn, chạy điều kiện customer_id = 42 AND status = 'OPEN'. Dùng EXPLAIN để xem optimizer có chọn index_merge intersection không. Ghi lại key và Extra.

### Bài 2: Quan sát union

Chạy customer_id = 42 OR status = 'OPEN'. Quan sát type và Extra. Tạo dữ liệu có một số hàng thỏa cả hai điều kiện để xác nhận kết quả không trả bản sao.

### Bài 3: Quan sát sort-union

Chạy điều kiện OR giữa hai range trên priority và created_at. Dùng EXPLAIN để xem có Using sort_union hay không. Nếu optimizer chọn kế hoạch khác, giải thích theo cost và thử dữ liệu có phân bố khác.

### Bài 4: So sánh với composite index

Tạo idx_ticket_customer_status trên (customer_id, status). Chạy lại truy vấn AND. So sánh type, key, rows, Extra và EXPLAIN ANALYZE với kế hoạch Index Merge trước đó.

### Bài 5: Kiểm tra leftmost prefix

Tạo index (customer_id, status, created_at). Chạy bốn truy vấn:
- customer_id = ?
- customer_id = ? AND status = ?
- customer_id = ? AND status = ? AND created_at trong khoảng
- status = ? AND created_at trong khoảng

Ghi lại trường hợp nào có thể định vị theo tiền tố index.

### Bài 6: OR và UNION

Viết cùng một truy vấn bằng OR, UNION và UNION ALL. Tạo hàng thỏa cả hai nhánh. So sánh số hàng và giải thích vì sao UNION ALL không tương đương OR.

### Bài 7: ORDER BY và LIMIT

Truy vấn ticket theo customer_id, status, ORDER BY created_at DESC LIMIT 20. Thử composite index có created_at và kiểm tra filesort. So sánh với Index Merge intersection.

### Bài 8: Chi phí ghi

Tạo bảng có nhiều index đơn, sau đó thử composite index thay thế một số index. Đo thời gian INSERT batch, UPDATE cột được index và kích thước index. Không kết luận chỉ từ tốc độ SELECT.

### Bài 9: Cập nhật thống kê

Thay đổi phân bố status đáng kể, chạy EXPLAIN trước và sau ANALYZE TABLE. Ghi nhận ước lượng rows và kế hoạch.

### Bài 10: Đánh giá workload

Tổng hợp ít nhất năm truy vấn thật của một bảng. Lập bảng ánh xạ predicate, ORDER BY, LIMIT, index được dùng và đề xuất index. Giải thích index nào nên giữ, thêm hoặc loại bỏ.

## 21. Checklist trước khi triển khai index

- [ ] Đã xác định Index Merge đang dùng intersection, union hay sort-union.
- [ ] Đã kiểm tra type, key, rows và Extra trong EXPLAIN.
- [ ] Đã xác nhận Index Merge đang kết hợp index của cùng một bảng.
- [ ] Đã phân biệt Index Merge với composite index.
- [ ] Đã áp dụng leftmost-prefix khi thiết kế thứ tự cột.
- [ ] Đã cân nhắc equality columns, range column và ORDER BY.
- [ ] Đã kiểm tra truy vấn OR có cần các index đơn riêng.
- [ ] Đã không nhầm sort-union với thứ tự ORDER BY cuối cùng.
- [ ] Đã kiểm tra covering index và filesort.
- [ ] Đã xem actual rows và thời gian bằng EXPLAIN ANALYZE khi phù hợp.
- [ ] Đã cập nhật thống kê nếu phân bố dữ liệu thay đổi.
- [ ] Đã benchmark trên dữ liệu đại diện.
- [ ] Đã đánh giá dung lượng và chi phí INSERT/UPDATE/DELETE.
- [ ] Đã kiểm tra workload khác trước khi xóa index đơn.
- [ ] Đã theo dõi kế hoạch sau khi triển khai.

## 22. Kết luận

Index Merge cho phép MySQL dùng nhiều index riêng trên cùng một bảng rồi hợp nhất row ID bằng intersection, union hoặc sort-union. Nó hữu ích khi truy vấn kết hợp nhiều predicate và các index đơn đã có thể phục vụ từng nhánh. Tuy nhiên, việc đọc nhiều index, hợp nhất và truy cập hàng có thể tốn kém; sort-union còn cần sắp xếp row ID.

Composite index lưu nhiều cột trong một B-tree và thường hiệu quả cho mẫu truy vấn AND ổn định, nhất là khi thứ tự cột khớp equality, range và ORDER BY. Đổi lại, composite index phụ thuộc leftmost prefix, có thể không phục vụ truy vấn chỉ lọc cột phía sau và làm tăng chi phí ghi/dung lượng. Hãy chọn theo workload thay vì theo một quy tắc chung: đọc EXPLAIN, đo actual rows, kiểm tra ORDER BY/LIMIT, benchmark cả đọc lẫn ghi và xác minh mọi index được giữ đều có lý do.

## Tài liệu tham khảo chính thức

- [MySQL 8.4 Reference Manual – Index Merge Optimization](https://dev.mysql.com/doc/refman/8.4/en/index-merge-optimization.html)
- [MySQL 8.4 Reference Manual – Range Optimization](https://dev.mysql.com/doc/refman/8.4/en/range-optimization.html)
- [MySQL 8.4 Reference Manual – Multiple-Column Indexes](https://dev.mysql.com/doc/refman/8.4/en/multiple-column-indexes.html)
- [MySQL 8.4 Reference Manual – How MySQL Uses Indexes](https://dev.mysql.com/doc/refman/8.4/en/mysql-indexes.html)
- [MySQL 8.4 Reference Manual – EXPLAIN](https://dev.mysql.com/doc/refman/8.4/en/explain.html)
- [MySQL 8.4 Reference Manual – Optimizer Switch](https://dev.mysql.com/doc/refman/8.4/en/switchable-optimizations.html)
- [MySQL 8.4 Reference Manual – ANALYZE TABLE](https://dev.mysql.com/doc/refman/8.4/en/analyze-table.html)
- [MySQL 8.4 Reference Manual – InnoDB Index Types](https://dev.mysql.com/doc/refman/8.4/en/innodb-index-types.html)

