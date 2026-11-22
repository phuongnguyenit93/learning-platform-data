# possible_keys, key, key_len và điều kiện dùng chỉ mục

Khi đọc EXPLAIN trong MySQL, ba cột possible_keys, key và key_len trả lời ba câu hỏi khác nhau:

- **possible_keys**: những index nào có thể được xem xét để tìm hàng cho bảng ở bước này?
- **key**: optimizer thực sự chọn index nào?
- **key_len**: bao nhiêu byte của phần đầu index được dùng cho access path đã chọn?

Không nên nhìn thấy tên index trong possible_keys rồi kết luận truy vấn đã dùng index. Cũng không nên xem key_len là tổng kích thước index hoặc số cột được SELECT. Cần đọc ba cột cùng với type, ref, rows, filtered, Extra, điều kiện WHERE/JOIN và cấu trúc index thực tế.

Bài viết tập trung vào cách MySQL xác định index có thể dùng, quy tắc leftmost prefix của index ghép, cách hiểu độ dài khóa, điều kiện tìm kiếm có thể tận dụng index, Index Condition Pushdown (ICP) và cách xác minh kế hoạch bằng EXPLAIN.

## 1. Bảng mẫu để đọc kế hoạch

Tạo bảng đơn hàng với các kiểu dữ liệu có độ dài rõ ràng:

~~~sql
CREATE TABLE orders (
    order_id    BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    status_code TINYINT UNSIGNED NOT NULL,
    created_at  DATETIME NOT NULL,
    total       DECIMAL(12, 2) NOT NULL,
    note        VARCHAR(100) NULL,
    PRIMARY KEY (order_id),
    KEY idx_customer_status_created
        (customer_id, status_code, created_at),
    KEY idx_status_created
        (status_code, created_at),
    KEY idx_created_at (created_at)
) ENGINE = InnoDB;
~~~

Các index trong ví dụ có mục đích khác nhau:

| Index | Thứ tự key parts | Truy vấn điển hình |
|---|---|---|
| PRIMARY | order_id | Tìm một đơn theo khóa chính |
| idx_customer_status_created | customer_id, status_code, created_at | Tìm đơn của một khách hàng theo trạng thái và thời gian |
| idx_status_created | status_code, created_at | Tìm đơn theo trạng thái và khoảng thời gian |
| idx_created_at | created_at | Tìm đơn theo khoảng thời gian |

Các cột trong ví dụ chính đều NOT NULL và có kiểu độ dài cố định. Điều này giúp tính key_len dễ quan sát:

- BIGINT: 8 byte.
- TINYINT: 1 byte.
- DATETIME không có phần giây lẻ: 5 byte.

Do đó, index ghép (customer_id, status_code, created_at) có độ dài key parts khai báo là 14 byte: 8 + 1 + 5. key_len trong EXPLAIN có thể là 8, 9 hoặc 14 tùy điều kiện truy vấn thực sự dùng đến phần nào của index.

## 2. Xem các cột trong EXPLAIN

Chạy EXPLAIN với truy vấn:

~~~sql
EXPLAIN
SELECT order_id, customer_id, status_code, created_at, total
FROM orders
WHERE customer_id = 42
  AND status_code = 2
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00';
~~~

EXPLAIN dạng bảng truyền thống có thể hiển thị các cột:

| Cột | Ý nghĩa |
|---|---|
| id | Thứ tự/định danh của SELECT block |
| select_type | Loại SELECT block, ví dụ SIMPLE hoặc PRIMARY |
| table | Bảng hoặc derived table được đọc ở bước này |
| partitions | Partition được truy cập nếu bảng partitioned |
| type | Access method như const, eq_ref, ref, range, index hoặc ALL |
| possible_keys | Index có thể dùng cho việc tìm hàng |
| key | Index được optimizer chọn |
| key_len | Độ dài phần index được dùng, tính theo byte |
| ref | Cột hoặc giá trị được so sánh với index |
| rows | Số hàng ước lượng cần đọc |
| filtered | Tỷ lệ hàng ước lượng còn lại sau điều kiện lọc |
| Extra | Thông tin bổ sung như Using where, Using index hoặc Using index condition |

Ba cột possible_keys, key, key_len cần được đọc cùng nhau. Một kế hoạch có possible_keys chứa nhiều index nhưng key chỉ có một index được chọn là chuyện bình thường.

## 3. possible_keys: index có thể được xem xét

possible_keys liệt kê các index mà optimizer có thể dùng để tìm hàng phù hợp với điều kiện của bảng ở bước thực thi đó.

Ví dụ truy vấn:

~~~sql
SELECT order_id, total
FROM orders
WHERE customer_id = 42;
~~~

Index idx_customer_status_created bắt đầu bằng customer_id, nên nó có thể được dùng. possible_keys có thể liệt kê index này.

Với truy vấn:

~~~sql
SELECT order_id, total
FROM orders
WHERE status_code = 2
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01';
~~~

idx_status_created phù hợp vì hai điều kiện khớp các key parts đầu tiên. idx_created_at cũng có thể là một ứng viên vì truy vấn có điều kiện khoảng trên created_at. Optimizer sẽ so sánh chi phí ước lượng của các lựa chọn.

### 3.1. possible_keys không phải danh sách tất cả index của bảng

Một bảng có thể có nhiều index nhưng possible_keys chỉ liệt kê các index được xem là liên quan đến điều kiện tìm hàng ở bước đó.

Ví dụ:

~~~sql
SELECT order_id, total
FROM orders
WHERE status_code = 2;
~~~

idx_status_created có thể được xem xét vì key part đầu tiên là status_code. idx_customer_status_created không thể dùng để định vị theo status_code khi không có điều kiện trên customer_id, do quy tắc leftmost prefix.

Nếu truy vấn không có điều kiện phù hợp với bất kỳ index nào, possible_keys có thể là NULL dù bảng vẫn có nhiều index.

### 3.2. possible_keys có giá trị không có nghĩa index sẽ được dùng

possible_keys là danh sách ứng viên, không phải quyết định cuối cùng. Optimizer có thể chọn full table scan nếu:

- Bảng nhỏ và đọc tuần tự rẻ hơn tra cứu index.
- Điều kiện khớp phần lớn hàng.
- Index có độ chọn lọc thấp.
- Chi phí đọc index cộng với việc quay lại clustered index cao hơn scan.
- Thống kê cardinality không phản ánh tốt dữ liệu hiện tại.

Vì vậy, luôn đọc cột key để biết lựa chọn cuối cùng.

## 4. key: index được optimizer chọn

key cho biết index mà MySQL thực sự chọn để truy cập bảng trong kế hoạch.

Ví dụ:

~~~sql
EXPLAIN
SELECT order_id, total
FROM orders
WHERE customer_id = 42;
~~~

Nếu kế hoạch chọn idx_customer_status_created, cột key sẽ hiển thị tên index đó.

Nếu key là NULL, MySQL không chọn index cho access path của bảng ở bước đó. Trường hợp này không tự động có nghĩa truy vấn sai hoặc thiếu index. Có thể full scan thực sự rẻ hơn, hoặc điều kiện không khớp cấu trúc index hiện có.

### 4.1. So sánh possible_keys và key

| possible_keys | key | Cách hiểu |
|---|---|---|
| idx_a, idx_b | idx_a | Có hai ứng viên; optimizer chọn idx_a |
| idx_a | NULL | Index có thể liên quan nhưng optimizer không dùng nó |
| NULL | NULL | Không có index phù hợp được liệt kê hoặc không dùng index để tìm hàng |
| idx_a | idx_a | Ứng viên duy nhất được chọn |

Các giá trị cụ thể phụ thuộc truy vấn, thống kê, phiên bản và dữ liệu.

### 4.2. Index được chọn không nhất thiết là index có ít key parts nhất

Optimizer cân nhắc nhiều yếu tố:

- Số hàng ước lượng phải đọc.
- Cardinality và độ chọn lọc của key parts.
- Điều kiện bằng hay điều kiện phạm vi.
- Có cần quay lại clustered index để lấy cột còn thiếu không.
- Index có thể đáp ứng ORDER BY hoặc GROUP BY không.
- Có thể dùng index-only/covering access không.
- Chi phí I/O và các phép lọc còn lại.

Không thể chọn index chỉ bằng cách đếm số cột trong index hoặc nhìn tên index.

## 5. key_len: độ dài phần index được sử dụng

key_len là độ dài theo byte của phần khóa index mà optimizer sử dụng để truy cập hàng. Nó giúp nhận biết index ghép đang được dùng đến key part nào.

Với bảng mẫu:

~~~sql
KEY idx_customer_status_created
    (customer_id, status_code, created_at)
~~~

Độ dài từng key part:

| Key part | Kiểu | Độ dài |
|---|---|---:|
| customer_id | BIGINT UNSIGNED NOT NULL | 8 byte |
| status_code | TINYINT UNSIGNED NOT NULL | 1 byte |
| created_at | DATETIME NOT NULL | 5 byte |
| Tổng | | 14 byte |

### 5.1. Chỉ dùng key part đầu tiên

~~~sql
EXPLAIN
SELECT order_id
FROM orders
WHERE customer_id = 42;
~~~

Nếu optimizer dùng idx_customer_status_created, key_len thường là 8 vì chỉ cần phần customer_id để tìm hàng.

### 5.2. Dùng hai key parts đầu tiên

~~~sql
EXPLAIN
SELECT order_id
FROM orders
WHERE customer_id = 42
  AND status_code = 2;
~~~

Optimizer có thể dùng customer_id và status_code. key_len thường là 9 byte (8 + 1).

### 5.3. Dùng cả ba key parts

~~~sql
EXPLAIN
SELECT order_id
FROM orders
WHERE customer_id = 42
  AND status_code = 2
  AND created_at >= '2026-01-01'
  AND created_at <  '2026-02-01';
~~~

Hai điều kiện bằng dùng hai key parts đầu, điều kiện khoảng dùng key part created_at. Khi optimizer chọn đầy đủ ba phần này, key_len thường là 14 byte.

Các con số trên là cách đọc dựa trên kiểu dữ liệu và schema minh họa. Kết quả thực tế cần xác nhận bằng EXPLAIN của phiên bản và truy vấn đang chạy.

## 6. key_len không phải tổng kích thước index

Một số nhầm lẫn phổ biến:

- key_len = 8 không có nghĩa index chỉ chứa 8 byte hoặc chỉ có một cột.
- key_len = 14 không có nghĩa truy vấn SELECT 14 byte dữ liệu.
- key_len không đo dung lượng index trên đĩa.
- key_len không cho biết có bao nhiêu cột được trả về.
- key_len không cho biết truy vấn có covering index hay không.

key_len mô tả độ dài key prefix được dùng trong access path. Muốn biết index có chứa đủ cột cho truy vấn hay không, hãy xem cấu trúc index và Extra, đặc biệt là Using index.

### 6.1. Cột nullable có thêm byte quản lý NULL

Khi key part cho phép NULL, phần khóa cần thêm thông tin để biểu diễn trạng thái NULL. Vì vậy, key_len có thể lớn hơn độ dài dữ liệu cơ bản của kiểu.

Ví dụ:

~~~sql
CREATE TABLE nullable_lookup (
    id BIGINT UNSIGNED NOT NULL,
    category_id INT NULL,
    PRIMARY KEY (id),
    KEY idx_category (category_id)
) ENGINE = InnoDB;
~~~

INT có độ dài dữ liệu 4 byte. Vì category_id nullable, key_len có thể là 5 byte, gồm 4 byte dữ liệu và 1 byte đánh dấu NULL.

Nếu đổi cột thành NOT NULL, phần đánh dấu NULL không còn cần thiết.

### 6.2. VARCHAR và cột độ dài biến thiên có byte độ dài

Với cột có độ dài biến thiên như VARCHAR, phần khóa còn có byte lưu độ dài giá trị. Số byte này phụ thuộc giới hạn tối đa theo byte của cột:

- Tối đa 255 byte: thường cần 1 byte độ dài.
- Trên 255 byte: thường cần 2 byte độ dài.

Nếu cột nullable, còn có byte đánh dấu NULL.

Ví dụ:

~~~sql
CREATE TABLE name_lookup (
    id BIGINT UNSIGNED NOT NULL,
    short_code VARCHAR(40) NOT NULL,
    long_code VARCHAR(100) NULL,
    PRIMARY KEY (id),
    KEY idx_short_code (short_code),
    KEY idx_long_code (long_code)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4;
~~~

Với utf8mb4, VARCHAR(40) có thể cần tối đa 160 byte dữ liệu ký tự; ngoài ra có byte độ dài. VARCHAR(100) có thể cần tối đa 400 byte và 2 byte độ dài; vì nullable nên còn có byte NULL. key_len vì vậy không đơn giản bằng số ký tự nhân với số byte mỗi ký tự.

Không tự tính key_len bằng mắt cho mọi kiểu phức tạp. Dùng EXPLAIN làm nguồn xác nhận và đối chiếu với kiểu, nullability, charset, collation và prefix length của index.

### 6.3. Prefix index

Index có thể chỉ lưu một prefix của cột chuỗi:

~~~sql
CREATE INDEX idx_note_prefix
ON orders (note(20));
~~~

Với prefix index, key length được tính theo prefix đã khai báo cùng overhead kiểu dữ liệu và NULL nếu có. key_len không đại diện cho toàn bộ VARCHAR(100).

Prefix index tiết kiệm dung lượng nhưng có thể có nhiều giá trị trùng prefix, khiến MySQL phải kiểm tra thêm điều kiện trên hàng đầy đủ.

## 7. Quy tắc leftmost prefix của index ghép

Index ghép lưu các key parts theo thứ tự đã khai báo. Với:

~~~sql
KEY idx_customer_status_created
    (customer_id, status_code, created_at)
~~~

Các prefix liên tục có thể dùng để định vị:

- (customer_id)
- (customer_id, status_code)
- (customer_id, status_code, created_at)

Không thể dùng riêng status_code để định vị hiệu quả bằng index này khi không có điều kiện trên customer_id. Tương tự, chỉ có created_at mà không có customer_id thì không thể bỏ qua hai key parts trước để tìm một khoảng liên tục theo created_at.

### 7.1. Các điều kiện điển hình

| Điều kiện truy vấn | Khả năng dùng index ghép |
|---|---|
| customer_id = 42 | Có, dùng key part đầu |
| customer_id = 42 AND status_code = 2 | Có, dùng hai key parts đầu |
| customer_id = 42 AND status_code = 2 AND created_at >= ... | Có, dùng cả ba phần |
| status_code = 2 | Không dùng được prefix của index này |
| created_at >= ... | Không dùng được prefix của index này |
| customer_id = 42 AND created_at >= ... | Dùng customer_id để định vị; created_at có thể được kiểm tra bằng ICP |

### 7.2. Điều kiện bằng trước, điều kiện phạm vi sau

Với index (customer_id, status_code, created_at), truy vấn:

~~~sql
WHERE customer_id = 42
  AND status_code = 2
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01'
~~~

có hai điều kiện bằng ở đầu và một điều kiện phạm vi sau đó. Đây là hình dạng phù hợp cho index ghép đã thiết kế.

Nếu một key part bị bỏ qua hoặc đã dùng điều kiện phạm vi, các key parts phía sau thường không tiếp tục thu hẹp range scan theo cách giống các prefix liên tiếp. Tuy nhiên, chúng vẫn có thể giúp kiểm tra điều kiện trong index, sắp xếp hoặc phủ truy vấn tùy kế hoạch.

Đây là lý do thứ tự cột trong composite index quan trọng. Hãy thiết kế theo nhóm truy vấn thực tế, không chỉ theo thứ tự cột trong bảng.

## 8. Điều kiện nào có thể dùng index?

Optimizer thường tận dụng index tốt hơn khi cột được so sánh trực tiếp với hằng số hoặc giá trị đã xác định:

~~~sql
WHERE customer_id = 42
WHERE created_at >= '2026-01-01'
WHERE status_code IN (1, 2, 3)
WHERE total BETWEEN 100 AND 500
WHERE note LIKE 'urgent%'
WHERE note IS NULL
~~~

Các điều kiện trên có thể tạo lookup hoặc range trên index phù hợp.

### 8.1. Hàm trên cột

Truy vấn:

~~~sql
WHERE DATE(created_at) = '2026-01-01'
~~~

không có cùng dạng truy cập với index thông thường trên created_at vì hàm DATE() được áp dụng lên cột. Có thể viết lại thành khoảng:

~~~sql
WHERE created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-01-02 00:00:00'
~~~

Nếu nghiệp vụ bắt buộc truy vấn theo biểu thức, có thể cân nhắc functional index hoặc generated column đã lập index, rồi kiểm tra bằng EXPLAIN.

### 8.2. Wildcard ở đầu LIKE

~~~sql
WHERE note LIKE '%urgent'
~~~

không xác định được điểm bắt đầu trong B-tree index thông thường vì chuỗi có thể bắt đầu bằng bất kỳ ký tự nào. Ngược lại:

~~~sql
WHERE note LIKE 'urgent%'
~~~

có thể tạo range trên prefix nếu collation và kiểu dữ liệu cho phép.

### 8.3. Chuyển đổi kiểu dữ liệu

So sánh khác kiểu có thể khiến MySQL phải chuyển đổi một phía của biểu thức. Nếu phép chuyển đổi được áp dụng lên cột đã index, khả năng dùng index có thể giảm.

Ví dụ, nếu customer_id là BIGINT, truyền tham số số nguyên đúng kiểu thường rõ ràng hơn so sánh với chuỗi không chuẩn. Hãy kiểm tra kiểu cột và kiểu bind parameter của driver.

### 8.4. OR và index merge

Truy vấn:

~~~sql
SELECT order_id
FROM orders
WHERE customer_id = 42
   OR status_code = 2;
~~~

có thể dùng Index Merge nếu optimizer đánh giá kết hợp nhiều index là có lợi. Kế hoạch có thể thể hiện access type index_merge. Không nên giả định OR luôn làm full scan; cũng không nên giả định Index Merge luôn tốt hơn một index ghép phù hợp.

## 9. Index Condition Pushdown (ICP)

Index Condition Pushdown cho phép MySQL đẩy một phần điều kiện lọc xuống storage engine để kiểm tra trên các cột có trong secondary index trước khi đọc đầy đủ hàng từ clustered index.

Mục tiêu là tránh đọc hàng đầy đủ cho những index entry không thỏa điều kiện có thể kiểm tra ngay trên index.

Ví dụ với index:

~~~sql
KEY idx_customer_status_created
    (customer_id, status_code, created_at)
~~~

Truy vấn:

~~~sql
SELECT order_id, total
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-01-01'
  AND created_at <  '2026-02-01';
~~~

Điều kiện customer_id dùng key part đầu để tìm một vùng index. status_code nằm giữa customer_id và created_at nhưng không có điều kiện. created_at vì thế không thể trở thành phần tiếp theo của một prefix liên tục để định vị range như ví dụ trước.

Tuy nhiên, created_at vẫn nằm trong secondary index. Nếu kế hoạch phù hợp, InnoDB có thể kiểm tra điều kiện created_at trên index entry trước khi quay lại clustered index để lấy total. EXPLAIN có thể hiển thị Using index condition trong cột Extra.

### 9.1. Using index condition không phải Using index

Hai thông tin này có ý nghĩa khác nhau:

| Extra | Ý nghĩa |
|---|---|
| Using index condition | Có Index Condition Pushdown; điều kiện được kiểm tra trên index entry trước khi đọc hàng đầy đủ |
| Using index | Truy vấn có thể lấy các cột cần thiết trực tiếp từ index (covering/index-only access) |
| Using where | Server còn áp dụng điều kiện lọc sau access method |

Using index condition không có nghĩa truy vấn đã được phủ hoàn toàn bởi index. Ví dụ trên vẫn cần lấy total từ clustered record vì total không nằm trong secondary index.

Using index cũng không có nghĩa mọi điều kiện đều được dùng để định vị range. Nó nói về khả năng lấy cột cần thiết từ index, không phải toàn bộ cách tạo access range.

### 9.2. Khi nào ICP có ích?

ICP thường hữu ích khi:

- Access method đọc nhiều entry từ secondary index.
- Một số điều kiện có thể kiểm tra trên các cột đã có trong index.
- Nhiều entry bị loại trước khi phải đọc clustered record.
- Truy vấn cần cột không có trong secondary index nên vẫn phải quay lại hàng đầy đủ cho các entry còn lại.

ICP có thể giảm số lần truy cập clustered index. Nó không làm biến mất chi phí quét index và không thay thế thiết kế index đúng thứ tự.

Với InnoDB, ICP được áp dụng cho secondary index; nó không đem lại lợi ích tương tự trên clustered index vì record đầy đủ đã nằm trong index đó.

## 10. Phân biệt Using where, Using index và Using index condition

Ví dụ:

~~~sql
EXPLAIN
SELECT order_id, total
FROM orders
WHERE customer_id = 42
  AND status_code = 2;
~~~

Nếu optimizer dùng index ghép để định vị nhưng vẫn phải kiểm tra một điều kiện khác, Extra có thể có Using where.

Nếu index chứa đủ mọi cột cần cho truy vấn, kế hoạch có thể hiển thị Using index. Với InnoDB, secondary index còn chứa primary key của hàng để có thể tìm clustered record; điều này cũng có thể giúp một số truy vấn chỉ cần primary key trở thành covering.

Nếu điều kiện có thể được kiểm tra trên secondary index trước khi đọc record đầy đủ, kế hoạch có thể hiển thị Using index condition.

Các dòng Extra có thể kết hợp tùy truy vấn và phiên bản. Không nên xem một nhãn đơn lẻ là kết luận hiệu năng.

## 11. Đọc một ví dụ kế hoạch từ đầu đến cuối

Truy vấn:

~~~sql
EXPLAIN
SELECT order_id, total
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00';
~~~

Giả sử EXPLAIN cho thấy:

~~~text
table: orders
type: ref
possible_keys: idx_customer_status_created, idx_created_at
key: idx_customer_status_created
key_len: 8
ref: const
rows: 120
filtered: 100.00
Extra: Using index condition
~~~

Đây là kết quả minh họa để giải thích cách đọc, không phải output được bảo đảm trên mọi bộ dữ liệu.

Phân tích:

1. possible_keys có hai index ứng viên vì truy vấn có điều kiện theo khách hàng và thời gian.
2. key là idx_customer_status_created, nghĩa là optimizer chọn index bắt đầu bằng customer_id.
3. type = ref cho biết truy cập theo giá trị customer_id bằng nhau.
4. key_len = 8 cho thấy chỉ key part customer_id được dùng để định vị; status_code bị bỏ qua nên created_at không thể nối tiếp prefix để thu hẹp lookup.
5. rows = 120 là số hàng ước lượng cần đọc trong vùng của khách hàng, không phải số hàng thực tế chắc chắn.
6. Using index condition cho biết điều kiện created_at được kiểm tra trên secondary index entry trước khi cần đọc clustered record để lấy total.

Nếu rows ước lượng rất cao hoặc index khác được chọn, hãy kiểm tra phân bố dữ liệu, thống kê và điều kiện thực tế.

## 12. Dùng EXPLAIN JSON và TREE

EXPLAIN dạng bảng hữu ích để đọc nhanh possible_keys, key, key_len, type và Extra.

Để xem cấu trúc chi tiết hơn:

~~~sql
EXPLAIN FORMAT=JSON
SELECT order_id, total
FROM orders
WHERE customer_id = 42
  AND status_code = 2
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00';
~~~

JSON plan cung cấp thông tin về access path, index, ước lượng hàng, điều kiện và chi phí theo cấu trúc lồng nhau. Các trường cụ thể phụ thuộc loại plan và phiên bản.

Trên MySQL 8.0.16 trở lên, có thể xem dạng cây:

~~~sql
EXPLAIN FORMAT=TREE
SELECT order_id, total
FROM orders
WHERE customer_id = 42
  AND status_code = 2
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00';
~~~

TREE làm rõ thứ tự iterator và quan hệ giữa các bước. EXPLAIN ANALYZE được hỗ trợ từ MySQL 8.0.18; lệnh này thực thi truy vấn và báo số liệu thực tế. Ví dụ:

~~~sql
EXPLAIN ANALYZE
SELECT order_id, total
FROM orders
WHERE customer_id = 42
  AND status_code = 2
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00';
~~~

EXPLAIN ANALYZE thực sự chạy câu SELECT và báo thời gian, số hàng thực tế và số vòng lặp của iterator. Lệnh này không chỉ là ước lượng; hãy đánh giá chi phí truy vấn và môi trường trước khi chạy.

## 13. Kiểm tra cấu trúc và thống kê index

Trước khi kết luận index không được dùng, kiểm tra index thực tế:

~~~sql
SHOW INDEX FROM orders;
~~~

Các cột cần chú ý:

- Key_name: tên index.
- Seq_in_index: vị trí key part.
- Column_name: tên cột thuộc index.
- Sub_part: prefix length nếu index chỉ lưu một phần cột.
- Cardinality: số giá trị khác nhau ước lượng.
- Collation: thứ tự tăng/giảm của key part theo metadata.

Có thể xem metadata bằng INFORMATION_SCHEMA:

~~~sql
SELECT
    INDEX_NAME,
    SEQ_IN_INDEX,
    COLUMN_NAME,
    NON_UNIQUE,
    SUB_PART,
    CARDINALITY
FROM information_schema.statistics
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'orders'
ORDER BY INDEX_NAME, SEQ_IN_INDEX;
~~~

Cardinality là ước lượng. Với dữ liệu thay đổi nhiều, thống kê cũ có thể làm optimizer đánh giá sai chi phí.

Cập nhật thống kê:

~~~sql
ANALYZE TABLE orders;
~~~

Sau đó chạy lại EXPLAIN và so sánh. ANALYZE TABLE cập nhật thống kê cho optimizer; nó không đảm bảo một index cụ thể sẽ được chọn.

## 14. Vì sao index có trong possible_keys nhưng key là NULL?

Một số nguyên nhân thường gặp:

### 14.1. Bảng nhỏ

Nếu bảng chỉ có vài hàng, đọc toàn bộ bảng có thể rẻ hơn mở index rồi truy cập clustered record. Optimizer có thể chọn type = ALL và key = NULL.

### 14.2. Điều kiện không chọn lọc

Nếu điều kiện khớp phần lớn hàng, index không giúp giảm đáng kể số hàng phải đọc. Full scan có thể hiệu quả hơn.

### 14.3. Thống kê không chính xác

Cardinality hoặc histogram không phản ánh phân bố hiện tại khiến ước lượng sai. Có thể kiểm tra SHOW INDEX, ANALYZE TABLE và EXPLAIN ANALYZE.

### 14.4. Index không phủ truy vấn

Nếu truy vấn phải lấy nhiều cột không nằm trong secondary index, MySQL có thể phải đọc clustered record cho rất nhiều entry. Chi phí đó có thể lớn hơn scan.

### 14.5. Biểu thức hoặc kiểu dữ liệu không tương thích

Hàm trên cột, chuyển đổi kiểu, collation khác nhau hoặc biểu thức không khớp functional index có thể khiến index không còn phù hợp.

### 14.6. Index ghép sai thứ tự

Nếu truy vấn chỉ lọc theo key part thứ hai hoặc thứ ba mà bỏ qua key part đầu, index ghép có thể không được dùng để định vị.

## 15. Quy trình phân tích khi index không được dùng

1. Chạy EXPLAIN trên đúng câu SQL và tham số đại diện.
2. Đọc possible_keys, key, key_len, type, rows, filtered và Extra.
3. Dùng SHOW INDEX để kiểm tra thứ tự key parts, prefix length và cardinality.
4. Đối chiếu điều kiện WHERE/JOIN với thứ tự key parts và leftmost prefix.
5. Kiểm tra hàm trên cột, chuyển đổi kiểu và collation.
6. Kiểm tra index có chọn lọc đủ tốt và có cần quay lại clustered index nhiều lần không.
7. Chạy ANALYZE TABLE nếu thống kê có dấu hiệu cũ.
8. Dùng EXPLAIN FORMAT=JSON hoặc TREE để xem access path chi tiết.
9. Dùng EXPLAIN ANALYZE để so sánh số hàng và thời gian thực tế.
10. Chỉ sau khi hiểu nguyên nhân mới thử viết lại truy vấn hoặc thay đổi index.

Không nên thêm index mới hoặc dùng FORCE INDEX chỉ vì key đang là NULL. Trước hết phải chứng minh scan hiện tại tốn kém và index đề xuất có thể giảm chi phí.

## 16. Khi nào nên dùng FORCE INDEX?

MySQL có index hint như:

~~~sql
SELECT order_id, total
FROM orders FORCE INDEX (idx_customer_status_created)
WHERE customer_id = 42
  AND status_code = 2
  AND created_at >= '2026-01-01'
  AND created_at <  '2026-02-01';
~~~

FORCE INDEX yêu cầu optimizer ưu tiên xem xét các index được chỉ định và làm cho table scan có vẻ đắt hơn trong quá trình lựa chọn. Nó không bảo đảm truy vấn sẽ nhanh hơn và không sửa được index thiết kế sai.

Chỉ cân nhắc hint khi:

- Đã xác nhận thống kê và ước lượng.
- Có benchmark cho thấy lựa chọn mặc định gây vấn đề ổn định.
- Index được chỉ định phù hợp với điều kiện và workload.
- Có kế hoạch theo dõi khi dữ liệu thay đổi.

Hint có thể trở nên bất lợi khi phân bố dữ liệu hoặc kích thước bảng thay đổi. Ưu tiên sửa thống kê, index hoặc truy vấn trước khi khóa optimizer vào một lựa chọn.

## 17. Các lỗi thường gặp

**“possible_keys là index đang được dùng.”** Không. Đây là danh sách ứng viên; key mới cho biết index được chọn.

**“key = NULL nghĩa là bảng không có index.”** Không. Bảng có thể có index nhưng optimizer không thấy index phù hợp hoặc chọn scan vì chi phí thấp hơn.

**“key_len là tổng độ dài index.”** Không. Nó là độ dài phần key được dùng cho access path, tính theo byte.

**“key_len bằng số cột được sử dụng.”** Không. Mỗi kiểu dữ liệu có kích thước byte riêng; nullable và biến độ dài còn có overhead.

**“Index ghép có thể tìm bằng bất kỳ cột nào.”** Không. B-tree composite index tuân theo leftmost prefix khi định vị.

**“Sau điều kiện range, mọi key part sau đó đều vô dụng.”** Không hoàn toàn. Chúng thường không tiếp tục thu hẹp range theo cách prefix liên tục, nhưng có thể hỗ trợ ICP, covering hoặc thứ tự.

**“Using index condition có nghĩa truy vấn đã được covering.”** Không. ICP lọc index entry trước khi đọc hàng đầy đủ; covering được thể hiện bằng Using index.

**“Using where là dấu hiệu truy vấn kém.”** Không. Nó chỉ cho biết còn điều kiện được áp dụng sau access method. Cần xem số hàng, chi phí và kế hoạch thực tế.

**“EXPLAIN rows là số hàng thực tế.”** Không. Đây là ước lượng; dùng EXPLAIN ANALYZE để quan sát số hàng thực tế và thời gian.

**“FORCE INDEX luôn sửa được kế hoạch.”** Không. Hint có thể làm kế hoạch tệ hơn khi dữ liệu hoặc workload thay đổi.

## 18. Checklist đọc possible_keys, key và key_len

- [ ] Đã đọc đúng hàng/table trong EXPLAIN, nhất là truy vấn JOIN nhiều bảng.
- [ ] Đã phân biệt possible_keys với key.
- [ ] Đã xác định vì sao index được liệt kê hoặc không được liệt kê.
- [ ] Đã kiểm tra key parts và thứ tự bằng SHOW INDEX.
- [ ] Đã đối chiếu key_len với kiểu dữ liệu, NULLability, charset và prefix length.
- [ ] Đã áp dụng leftmost prefix khi đọc index ghép.
- [ ] Đã phân biệt điều kiện dùng để định vị range với điều kiện được kiểm tra bằng ICP.
- [ ] Đã phân biệt Using index condition, Using index và Using where.
- [ ] Đã đọc type, ref, rows, filtered và Extra cùng nhau.
- [ ] Đã kiểm tra thống kê trước khi ép optimizer.
- [ ] Đã dùng EXPLAIN ANALYZE khi cần số liệu thực tế và môi trường phù hợp.
- [ ] Đã đo tác động của index đến cả đọc lẫn ghi.

## Kết luận

possible_keys cho biết các index có thể được xem xét; key cho biết index được chọn; key_len cho biết độ dài phần index được dùng để truy cập, tính theo byte. Với index ghép, key_len giúp nhận biết optimizer đã dùng đến key part nào, nhưng cần tính đến kiểu dữ liệu, NULLability, độ dài biến thiên và prefix.

Để hiểu một truy vấn có tận dụng index tốt hay không, hãy kết hợp ba cột này với leftmost prefix, type, rows, filtered và Extra. Phân biệt điều kiện định vị range với điều kiện được lọc bằng ICP, kiểm tra thống kê và xác nhận bằng EXPLAIN ANALYZE trước khi thay đổi index hoặc ép optimizer.
