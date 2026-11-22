# Index range scan, ref lookup và full index scan

Khi MySQL thực hiện một truy vấn, optimizer chọn cách truy cập dữ liệu dựa trên điều kiện lọc, thứ tự cột trong index, thống kê và chi phí ước lượng. Một truy vấn có thể đi vào B-tree tại một vị trí rồi đọc một khoảng khóa, tìm các hàng bằng phép so sánh bằng trên index không duy nhất, hoặc đọc toàn bộ các entry của một index. Ba cách này thường được thể hiện trong EXPLAIN bằng access type tương ứng là range, ref và index.

Hiểu sự khác nhau giữa **index range scan**, **ref lookup** và **full index scan** giúp đọc kế hoạch thực thi chính xác hơn. Đặc biệt, không nên nhầm access type index với Extra Using index: một cái mô tả cách truy cập, cái còn lại mô tả việc truy vấn có thể lấy đủ cột từ index hay không.

Trong module DATABASE_MYSQL, bài học này tập trung vào cách B-tree phục vụ ba kiểu truy cập, điều kiện để composite index được dùng, cách đọc EXPLAIN và cách kiểm chứng số hàng thực tế.

## 1. Index InnoDB và cấu trúc B-tree

Index phổ biến của InnoDB được tổ chức theo B-tree/B+tree. Các node trong cấu trúc lưu khóa theo thứ tự, giúp MySQL tìm vị trí bắt đầu nhanh hơn việc quét mọi hàng.

Trong ví dụ của bài, bảng orders có composite index bắt đầu bằng customer_id. Một index đơn trên customer_id cũng có thể phục vụ lookup theo cột này, nhưng nếu composite index hiện tại đã đáp ứng truy vấn thì không cần tạo thêm index trùng prefix.

MySQL có thể:

- Tìm một giá trị customer_id cụ thể.
- Tìm một khoảng customer_id từ thấp đến cao.
- Đọc toàn bộ các entry theo thứ tự của index.

Index giúp truy cập nhanh khi điều kiện truy vấn khớp với cấu trúc khóa. Nó cũng có chi phí: thêm dung lượng, làm INSERT/UPDATE/DELETE tốn công duy trì index và có thể làm tăng ghi ngẫu nhiên. Vì vậy, cần chọn index theo truy vấn thực tế thay vì tạo index cho mọi cột.

## 2. Ba access type cần phân biệt

Trong EXPLAIN dạng bảng, cột type cho biết phương thức truy cập mà optimizer chọn cho từng table reference.

| Access type | Cách truy cập | Trường hợp thường gặp |
|---|---|---|
| range | Đọc một hoặc nhiều khoảng khóa trong index | BETWEEN, so sánh lớn/nhỏ, prefix LIKE, một số IN |
| ref | Tìm các entry có giá trị khóa bằng một giá trị tham chiếu, thường qua index không duy nhất | Cột được so sánh bằng với literal hoặc cột từ bảng trước |
| index | Quét toàn bộ index theo thứ tự index | Không có điều kiện giới hạn, nhưng index có thể đáp ứng cột truy vấn hoặc thứ tự sắp xếp |

Đây là các access type khác nhau về phạm vi đọc:

- range giới hạn việc đọc vào các khoảng khóa được xác định.
- ref định vị theo giá trị bằng và có thể trả về nhiều hàng cùng giá trị.
- index đọc toàn bộ entry của một index, dù không nhất thiết phải đọc toàn bộ hàng trong clustered table.

Optimizer không chọn access type chỉ dựa vào cú pháp SQL. Số lượng dữ liệu, độ chọn lọc, index hiện có, thứ tự cột và thống kê đều ảnh hưởng đến quyết định.

## 3. Index range scan: đọc một khoảng khóa

Range scan được dùng khi điều kiện WHERE xác định được một hoặc nhiều khoảng trên index. Ví dụ, bảng orders có index theo customer_id và created_at:

~~~sql
CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    created_at DATETIME NOT NULL,
    status VARCHAR(20) NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_created (
        customer_id,
        created_at
    )
) ENGINE=InnoDB;
~~~

Truy vấn lấy đơn hàng của một khách hàng trong một khoảng thời gian:

~~~sql
SELECT order_id, customer_id, created_at
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00';
~~~

Với index (customer_id, created_at), MySQL có thể tìm đến phần khóa customer_id = 42 rồi đọc khoảng created_at từ đầu tháng 1 đến trước đầu tháng 2. Trong EXPLAIN, access type thường có thể là range vì điều kiện tạo một khoảng trên index.

Điều kiện equality trên cột đầu tiên thu hẹp phạm vi; điều kiện range trên cột tiếp theo xác định đoạn cần đọc. Đây là mẫu truy vấn phù hợp với composite index.

### Các dạng điều kiện có thể tạo range

Ví dụ thường gặp:

~~~sql
-- Khoảng số
WHERE order_id BETWEEN 1000 AND 1999

-- So sánh bất đẳng thức
WHERE created_at >= '2026-01-01'

-- Một số giá trị rời rạc
WHERE status IN ('PAID', 'SHIPPED')

-- Tìm prefix chuỗi
WHERE customer_code LIKE 'CUS-2026%'
~~~

Khả năng dùng range phụ thuộc kiểu dữ liệu, collation, index và biểu thức cụ thể. Một IN có thể được chuyển thành nhiều khoảng khóa; optimizer có thể gộp hoặc xử lý chúng theo kế hoạch khác.

### Vì sao range scan thường tốt hơn full scan?

Nếu điều kiện chỉ khớp một phần nhỏ dữ liệu, đọc một khoảng nhỏ của index thường rẻ hơn đọc toàn bảng. Nhưng range không phải lúc nào cũng nhanh: nếu điều kiện khớp phần lớn bảng, optimizer có thể chọn table scan hoặc index scan vì chi phí truy cập ngẫu nhiên đến nhiều hàng cao hơn.

## 4. Ref lookup: tìm theo giá trị bằng trên index không duy nhất

Access type ref thường xuất hiện khi MySQL dùng index không duy nhất để tìm các hàng có giá trị khóa bằng một giá trị tham chiếu.

Trong bảng orders ở phần trước, idx_orders_customer_created là index không duy nhất và có customer_id ở vị trí đầu. Một khách hàng có thể có nhiều đơn hàng nên nhiều entry có thể mang cùng giá trị customer_id.

Truy vấn:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE customer_id = 42;
~~~

Một khách hàng có thể có nhiều đơn hàng, nên customer_id không duy nhất. MySQL định vị vùng khóa có giá trị 42 trong index rồi đọc tất cả entry tương ứng. Trong EXPLAIN, access type có thể là ref.

Ref lookup không có nghĩa chỉ đọc đúng một hàng. Vì index không duy nhất, một giá trị có thể ánh xạ đến nhiều hàng. Số hàng ước lượng trong cột rows giúp hiểu số entry hoặc hàng mà optimizer dự kiến phải xử lý.

### Ref trong JOIN

Ref thường xuất hiện khi một bảng được truy cập bằng giá trị từ bảng đứng trước trong join order:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    o.order_id,
    o.created_at
FROM customers AS c
JOIN orders AS o
  ON o.customer_id = c.customer_id
WHERE c.customer_id = 42;
~~~

Nếu optimizer đọc customers trước rồi dùng customer_id để tra index của orders, bảng orders có thể dùng ref lookup trên idx_orders_customer_created. Với join, đây là cách tìm các hàng liên quan theo giá trị từ hàng hiện tại của bảng trước.

### Phân biệt ref và eq_ref

Nếu điều kiện join tra cứu bằng PRIMARY KEY hoặc UNIQUE NOT NULL và mỗi hàng phía trước khớp tối đa một hàng, EXPLAIN có thể dùng eq_ref thay vì ref.

| Access type | Tính chất |
|---|---|
| ref | Lookup bằng index không duy nhất hoặc unique key có thể chứa NULL trong ngữ cảnh phù hợp; có thể tìm nhiều hàng |
| eq_ref | Lookup bằng PRIMARY KEY hoặc UNIQUE NOT NULL cho mỗi tổ hợp hàng từ bảng trước; tối đa một hàng khớp |

Không gọi mọi phép equality lookup là ref. Hãy đọc type trong EXPLAIN để phân biệt ref, eq_ref, const và các kiểu khác.

## 5. Full index scan: đọc toàn bộ entry của index

Full index scan thường được thể hiện bằng type = index. MySQL đọc toàn bộ các entry trong một index theo thứ tự khóa, thay vì định vị một giá trị hoặc một khoảng nhỏ.

Ví dụ, nếu có index theo customer_id:

~~~sql
SELECT customer_id
FROM orders
ORDER BY customer_id;
~~~

Optimizer có thể chọn đọc toàn bộ idx_orders_customer_created vì index đã chứa customer_id và cung cấp thứ tự cần thiết. Nếu index đáp ứng tất cả cột truy vấn, MySQL có thể không cần truy cập clustered record cho từng hàng.

Full index scan vẫn đọc tất cả entry của index. Nó không phải một lookup nhỏ chỉ vì có chữ index trong access type. Tuy nhiên, nếu index hẹp hơn hàng đầy đủ và truy vấn chỉ cần các cột trong index, đọc toàn bộ index có thể ít I/O hơn quét toàn bộ clustered table.

### Full index scan không đồng nghĩa full table scan

| Cách đọc | EXPLAIN type thường thấy | Dữ liệu được đọc |
|---|---|---|
| Full table scan | ALL | Quét các hàng của table/clustered index |
| Full index scan | index | Quét tất cả entry của một secondary index hoặc index được chọn |
| Index range scan | range | Quét một hoặc nhiều khoảng entry |
| Ref lookup | ref | Tra cứu entry theo giá trị tham chiếu |

Với InnoDB, PRIMARY KEY là clustered index. Quét toàn bộ clustered index về cơ bản là đọc toàn bộ hàng của bảng; EXPLAIN có thể biểu diễn điều này như table scan. Secondary index thường nhỏ hơn vì chứa secondary key và primary key để định vị hàng.

## 6. Phân biệt type = index với Extra = Using index

Đây là điểm dễ nhầm nhất khi đọc EXPLAIN.

- type = index nghĩa là access method đang quét toàn bộ index.
- Extra = Using index nghĩa là truy vấn được đáp ứng bằng dữ liệu trong index (covering index), không cần đọc thêm các cột từ hàng clustered record cho truy vấn đó.

Using index có thể xuất hiện cùng nhiều access type khác nhau như range, ref hoặc index. Nó không đồng nghĩa với full index scan.

Ví dụ covering lookup:

~~~sql
SELECT customer_id
FROM orders
WHERE customer_id = 42;
~~~

Nếu dùng index idx_orders_customer_created, truy vấn có thể dùng ref và Extra có thể ghi Using index vì cột cần trả về đã nằm trong index.

Ví dụ full covering index scan:

~~~sql
SELECT customer_id
FROM orders
ORDER BY customer_id;
~~~

Truy vấn này có thể dùng type = index và Extra = Using index vì nó đọc toàn bộ entry của index, đồng thời không cần lấy thêm cột từ clustered record.

Do đó, hãy đọc cả cột type, key, rows và Extra. Chỉ nhìn chữ Using index rồi kết luận rằng truy vấn đã có range lookup là không chính xác.

## 7. Composite index và quy tắc leftmost prefix

Một composite index chứa nhiều cột theo thứ tự đã khai báo:

~~~sql
CREATE INDEX idx_orders_customer_created_status
    ON orders (customer_id, created_at, status);
~~~

Thứ tự cột quan trọng. B-tree được sắp xếp theo customer_id trước, trong cùng customer_id mới sắp theo created_at, rồi status.

Index này thường hỗ trợ:

- Điều kiện theo customer_id.
- Điều kiện theo customer_id và created_at.
- Điều kiện theo customer_id, created_at và status.

Nó thường không hiệu quả cho lookup chỉ theo status, vì status không phải cột dẫn đầu. Tương tự, điều kiện chỉ theo created_at không tận dụng được prefix đầu tiên một cách trực tiếp như truy vấn theo customer_id.

Ví dụ:

~~~sql
-- Có thể dùng prefix customer_id
WHERE customer_id = 42

-- Có thể dùng prefix customer_id và range trên created_at
WHERE customer_id = 42
  AND created_at >= '2026-01-01'

-- Cột status đứng sau range trên created_at thường không tiếp tục thu hẹp range như một equality prefix mới
WHERE customer_id = 42
  AND created_at >= '2026-01-01'
  AND status = 'PAID'
~~~

Optimizer vẫn có thể dùng status để lọc thêm bằng Index Condition Pushdown hoặc điều kiện sau khi đọc, tùy kế hoạch. Nhưng việc status xuất hiện trong index không có nghĩa nó luôn được dùng để xác định ranh giới range.

## 8. Điều kiện nào làm mất khả năng dùng index range?

Một điều kiện có thể khó dùng range nếu biểu thức không còn sargable hoặc kiểu dữ liệu không tương thích.

Ví dụ bọc cột trong hàm:

~~~sql
-- Có thể không dùng range trên created_at
WHERE DATE(created_at) = '2026-01-15'
~~~

Viết lại thành khoảng nửa mở:

~~~sql
WHERE created_at >= '2026-01-15 00:00:00'
  AND created_at <  '2026-01-16 00:00:00'
~~~

Ví dụ tìm chuỗi với wildcard ở đầu:

~~~sql
-- B-tree thường không thể định vị prefix khi wildcard ở đầu
WHERE customer_code LIKE '%2026'
~~~

Trong khi LIKE với prefix cố định có thể dùng range:

~~~sql
WHERE customer_code LIKE 'CUS-2026%'
~~~

Chuyển đổi kiểu ngầm cũng có thể làm index khó sử dụng, nhất là khi cột và literal khác kiểu hoặc khác collation. Hãy bind parameter bằng kiểu phù hợp với cột và tránh CAST trên chính cột được index nếu không cần thiết.

## 9. Range scan và thứ tự ORDER BY

Index có thể vừa lọc vừa cung cấp thứ tự, nhưng điều đó phụ thuộc cấu trúc index và cách các cột được ràng buộc.

Với index (customer_id, created_at):

~~~sql
SELECT order_id, created_at
FROM orders
WHERE customer_id = 42
ORDER BY created_at DESC;
~~~

Vì customer_id được cố định bằng equality, các hàng trong phạm vi khách hàng được sắp theo created_at. MySQL có thể đọc index theo chiều phù hợp để trả kết quả có thứ tự, tùy phiên bản và index direction.

Nếu truy vấn lọc một khoảng created_at rồi ORDER BY status, index trên (customer_id, created_at, status) không nhất thiết đáp ứng được thứ tự status toàn cục. Sau một range trên cột giữa, các cột phía sau thường không tạo thứ tự toàn cục như mong muốn.

Nếu EXPLAIN có Extra = Using filesort, MySQL cần một bước sắp xếp bổ sung. Filesort là tên thuật toán sort của MySQL, không khẳng định chắc chắn dữ liệu luôn được ghi ra đĩa.

## 10. Đọc EXPLAIN để nhận biết access type

Chạy EXPLAIN dạng bảng:

~~~sql
EXPLAIN
SELECT order_id, customer_id, created_at
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00';
~~~

Các cột cần chú ý:

| Cột | Ý nghĩa |
|---|---|
| type | Access type, ví dụ range, ref, index hoặc ALL |
| possible_keys | Các index optimizer xem là ứng viên |
| key | Index thực tế được chọn |
| key_len | Độ dài phần key được dùng trong access condition; phụ thuộc kiểu, NULL và charset |
| ref | Giá trị hoặc cột được so sánh với key |
| rows | Số hàng ước lượng cần đọc |
| filtered | Tỷ lệ phần trăm hàng ước lượng còn lại sau điều kiện lọc bổ sung |
| Extra | Thông tin bổ sung như Using index, Using index condition, Using where hoặc Using filesort |

Không đánh giá truy vấn chỉ bằng một chữ type. Một range scan có thể đọc hàng triệu entry nếu khoảng quá rộng; một full index scan có thể rất rẻ nếu index nhỏ và covering; một ref lookup có thể trả về rất nhiều hàng nếu giá trị có độ chọn lọc thấp.

### Ý nghĩa của key_len

key_len cho biết độ dài phần khóa mà optimizer dùng trong điều kiện truy cập. Với composite index, giá trị này giúp xem các thành phần đầu của index được sử dụng đến đâu. Tuy nhiên, không thể suy ra số cột một cách máy móc chỉ bằng cách chia key_len cho độ dài khai báo: kiểu dữ liệu, nullable flag, charset và thành phần prefix đều ảnh hưởng.

### Extra Using index condition

Using index condition thường biểu thị Index Condition Pushdown (ICP): một phần điều kiện được kiểm tra ngay trên entry index trước khi đọc clustered record. ICP có thể giảm số lần truy cập hàng, nhưng khác với covering index:

- Using index: dữ liệu truy vấn được lấy đủ từ index.
- Using index condition: index giúp kiểm tra điều kiện sớm, nhưng có thể vẫn cần đọc hàng đầy đủ để lấy cột khác.

## 11. EXPLAIN FORMAT=TREE và EXPLAIN ANALYZE

Trên MySQL 8.0, có thể dùng FORMAT=TREE để xem cây thao tác:

~~~sql
EXPLAIN FORMAT=TREE
SELECT order_id, customer_id, created_at
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00';
~~~

Trong tree output, các thao tác có thể được diễn đạt rõ hơn như Index range scan, Index lookup hoặc Covering index scan. Tên mô tả ở tree không phải lúc nào cũng giống nguyên văn access type của EXPLAIN dạng bảng; hãy hiểu bản chất thao tác.

Trên MySQL 8.0.18 trở lên, EXPLAIN ANALYZE thực thi truy vấn và bổ sung số hàng, vòng lặp cùng thời gian thực tế:

~~~sql
EXPLAIN ANALYZE
SELECT order_id, customer_id, created_at
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-01-01 00:00:00'
  AND created_at <  '2026-02-01 00:00:00';
~~~

EXPLAIN ANALYZE chạy câu SELECT thật. Dùng nó trên dữ liệu thử nghiệm hoặc khi đã đánh giá tải và tác động; không xem nó là lệnh chỉ đọc kế hoạch.

So sánh estimated rows với actual rows:

- Nếu actual rows lớn hơn nhiều, thống kê hoặc giả định về độ chọn lọc có thể sai.
- Nếu một range scan đọc nhiều hàng rồi lọc bỏ gần hết, xem lại index và điều kiện.
- Nếu full index scan đọc ít byte và không cần truy cập table, nó có thể là kế hoạch tốt.
- Nếu ref lookup lặp nhiều lần trong nested loop, tổng số lần lookup có thể lớn dù mỗi lookup riêng lẻ nhanh.

## 12. Thực hành so sánh ba access type

Sử dụng bảng orders ở phần đầu. Index idx_orders_customer_created đã có customer_id ở vị trí đầu, nên có thể hỗ trợ cả lookup theo customer_id và range theo created_at. Không cần tạo thêm một index chỉ gồm customer_id nếu composite index đã đáp ứng workload; index trùng prefix làm tăng dung lượng và chi phí ghi.

### Thử A: ref lookup

~~~sql
EXPLAIN
SELECT order_id, customer_id
FROM orders
WHERE customer_id = 42;
~~~

Index composite không duy nhất cho phép nhiều đơn hàng có cùng customer_id. Optimizer có thể chọn type = ref. Vì InnoDB lưu primary key trong secondary index, index có thể đáp ứng cả order_id và customer_id; Extra có thể hiển thị Using index.

### Thử B: range scan

~~~sql
EXPLAIN
SELECT order_id, customer_id, created_at
FROM orders
WHERE customer_id = 42
  AND created_at >= '2026-01-01'
  AND created_at < '2026-02-01';
~~~

Optimizer có thể dùng range trên composite index idx_orders_customer_created. Nếu index khác được chọn, kiểm tra cột key và key_len để hiểu quyết định.

### Thử C: full index scan

~~~sql
EXPLAIN
SELECT customer_id
FROM orders
ORDER BY customer_id;
~~~

Vì không có WHERE giới hạn phạm vi, optimizer có thể đọc toàn bộ idx_orders_customer_created theo thứ tự customer_id. Access type có thể là index và Extra có thể có Using index. Nếu bảng nhỏ hoặc optimizer thấy table scan rẻ hơn, kế hoạch có thể khác; điều đó không có nghĩa ví dụ sai.

Kết quả EXPLAIN có thể thay đổi theo kích thước bảng, dữ liệu, thống kê, phiên bản MySQL và cấu hình. Hãy kiểm tra kế hoạch thực tế trên môi trường của bạn thay vì yêu cầu một type cố định.

## 13. Khi nào optimizer chọn ALL thay vì index?

Có index không đồng nghĩa optimizer bắt buộc phải dùng index. Một số lý do chọn ALL:

- Điều kiện lọc trả về phần lớn hàng.
- Bảng rất nhỏ, quét tuần tự rẻ hơn tra cứu index rồi quay lại clustered record.
- Index không phù hợp với cột hoặc biểu thức trong WHERE.
- Thống kê cardinality hoặc distribution khiến optimizer ước lượng index không có lợi.
- Truy vấn cần nhiều cột không có trong secondary index, làm random lookup tốn kém.

Không nên cố ép index chỉ để EXPLAIN không còn ALL. Hãy so sánh thời gian, số hàng đọc và lượng I/O thực tế. FORCE INDEX chỉ nên dùng sau khi đo lường, hiểu rõ nguyên nhân optimizer chọn sai và có kế hoạch theo dõi khi dữ liệu thay đổi.

## 14. Chọn index theo truy vấn thay vì theo tên access type

Một số nguyên tắc thiết kế:

1. Đặt cột equality thường dùng ở đầu composite index nếu mẫu truy vấn phù hợp.
2. Đặt cột range sau các cột equality prefix khi truy vấn thường lọc theo cả hai.
3. Đưa thêm cột cần trả về vào index chỉ khi lợi ích covering đáng giá dung lượng và chi phí ghi.
4. Kiểm tra truy vấn JOIN để xác định index trên cột liên kết của bảng được tra cứu.
5. Đánh giá cardinality và phân bố dữ liệu; cột có ít giá trị phân biệt có thể kém chọn lọc.
6. Tránh tạo index trùng lặp hoặc index không được workload sử dụng.
7. Đo cả SELECT lẫn INSERT/UPDATE/DELETE sau khi thêm index.

Không có quy tắc cứng rằng cột có cardinality cao luôn phải đứng đầu. Equality, range, sort, join, prefix và workload tổng thể cùng quyết định thứ tự cột.

## 15. Checklist đọc kế hoạch thực thi

Khi xem EXPLAIN, hãy đi theo trình tự:

1. Xác định table reference nào đang được đọc và join order.
2. Đọc type để biết optimizer chọn range, ref, index hay ALL.
3. Kiểm tra key và possible_keys để biết index nào được chọn hoặc bị bỏ qua.
4. Đọc key_len và ref để hiểu phần index thực sự được dùng.
5. So sánh rows và filtered với quy mô dữ liệu mong đợi.
6. Đọc Extra: Using index, Using index condition, Using where, Using filesort.
7. Kiểm tra composite index có được dùng theo leftmost prefix không.
8. Dùng EXPLAIN ANALYZE để so estimated rows với actual rows khi phù hợp.
9. Đánh giá tổng số lookup trong join, không chỉ chi phí một lookup.
10. Đo cả lợi ích đọc lẫn chi phí ghi sau khi thay index.

## 16. Bài tập thực hành

1. Tạo bảng orders và index (customer_id, created_at) như ví dụ.
2. Chạy EXPLAIN cho customer_id = 42; xác định khi nào optimizer dùng ref.
3. Thêm điều kiện created_at theo khoảng; quan sát khi access type chuyển sang range.
4. Chạy SELECT customer_id ORDER BY customer_id; quan sát full index scan và Extra Using index nếu optimizer chọn index.
5. Thử SELECT * không có WHERE; so sánh type ALL với type index.
6. Tạo composite index (status, customer_id, created_at), sau đó so sánh truy vấn theo status, theo customer_id và theo cả hai.
7. Viết lại DATE(created_at) = ... thành khoảng thời gian; so sánh kế hoạch.
8. So sánh LIKE 'CUS-2026%' với LIKE '%2026' trên cột có index.
9. Dùng EXPLAIN FORMAT=TREE và EXPLAIN ANALYZE để so sánh kế hoạch ước lượng với số hàng thực tế.
10. Thêm một cột vào covering index, đo tác động SELECT và chi phí ghi trước/sau.

Bạn hoàn thành bài khi có thể giải thích range scan đọc khoảng khóa, ref lookup tìm theo giá trị bằng trên index và full index scan đọc toàn bộ entry; đồng thời phân biệt type = index với Extra Using index. Hãy dùng EXPLAIN cùng số liệu thực tế để đánh giá kế hoạch, thay vì xem một access type là tốt hoặc xấu trong mọi tình huống.
