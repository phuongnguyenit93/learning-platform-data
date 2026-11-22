# Điều kiện có thể tận dụng chỉ mục (SARGable) và cách nhận diện

Một câu SQL có thể trả về rất ít hàng nhưng vẫn phải đọc hàng triệu bản ghi nếu điều kiện lọc không phù hợp với cấu trúc truy cập của cơ sở dữ liệu. Ngược lại, một điều kiện được viết theo dạng có thể dùng làm điểm tìm kiếm hoặc khoảng quét trên chỉ mục thường giúp hệ quản trị thu hẹp vùng dữ liệu cần đọc. Khả năng này thường được gọi là **SARGability** — viết tắt của *Search ARGument able*.

Trong tối ưu hiệu năng cơ sở dữ liệu, nhận diện điều kiện SARGable giúp người phát triển viết SQL phù hợp với chỉ mục, giảm số trang phải đọc và tạo cơ hội cho optimizer chọn Index Seek hoặc Index Range Scan. Tuy nhiên, một điều kiện SARGable không bảo đảm optimizer sẽ dùng chỉ mục: quyết định còn phụ thuộc độ chọn lọc, thống kê, kích thước bảng, chi phí I/O, số cột cần trả về và tải đồng thời. Bài học này trình bày cách nhận diện, cách viết lại điều kiện, những trường hợp ngoại lệ và quy trình xác minh bằng kế hoạch thực thi.

## 1. SARGable là gì?

Một predicate SARGable là điều kiện mà hệ quản trị có thể sử dụng để xác định trực tiếp vị trí hoặc phạm vi khóa cần tìm trong một chỉ mục phù hợp. Với B-tree, các dạng thường có thể tận dụng chỉ mục gồm:

- So sánh bằng: cột được lập chỉ mục bằng một hằng hoặc tham số, ví dụ **customer_id = 42**.
- So sánh phạm vi: **created_at >= ...** hoặc **price BETWEEN ... AND ...**.
- Danh sách giá trị: **status IN ('NEW', 'PAID')**.
- Tiền tố chuỗi: **code LIKE 'AB%'**, nếu collation và loại chỉ mục hỗ trợ.
- Kiểm tra NULL: **deleted_at IS NULL**, nếu hệ quản trị và loại chỉ mục hỗ trợ truy cập NULL.
- Điều kiện kết hợp trên nhiều cột, khi thứ tự cột trong chỉ mục phù hợp với cách lọc.

Ví dụ, nếu có chỉ mục B-tree trên **orders(customer_id)**, điều kiện **customer_id = 42** có thể giúp hệ quản trị tìm vùng khóa tương ứng thay vì đọc toàn bộ bảng. Nếu có chỉ mục **(customer_id, created_at)**, điều kiện bằng trên cột đầu và điều kiện phạm vi trên cột kế tiếp thường có thể giới hạn một đoạn khóa liên tục.

SARGability là thuộc tính của mối quan hệ giữa biểu thức điều kiện, kiểu dữ liệu, phép so sánh và cấu trúc chỉ mục. Không thể chỉ nhìn một câu SQL và khẳng định chắc chắn nó sẽ dùng chỉ mục trong mọi hệ quản trị.

## 2. Phân biệt điều kiện tìm kiếm với điều kiện lọc sau khi đọc

Trong kế hoạch thực thi, một số hệ quản trị phân biệt điều kiện dùng để định vị khóa chỉ mục với điều kiện kiểm tra bổ sung sau khi hàng đã được đọc. Tên trường cụ thể khác nhau:

- SQL Server thường hiển thị **Seek Predicates** cho điều kiện dùng để định vị phạm vi trong Index Seek và **Predicate** cho điều kiện lọc bổ sung.
- PostgreSQL có thể hiển thị **Index Cond** cho điều kiện dùng trong truy cập chỉ mục và **Filter** cho điều kiện lọc thêm ở nút đó.
- MySQL có thể thể hiện đường truy cập qua access type, key, used key parts, range hoặc iterator filter trong định dạng kế hoạch tương ứng.

Ví dụ minh họa:

~~~text
Index Scan using orders_customer_idx on orders
  Index Cond: (customer_id = 42)
  Filter: (status = 'OPEN')
  Rows Removed by Filter: 8500
~~~

Trong ví dụ, chỉ mục được dùng để tìm các hàng theo customer_id. Sau khi đọc các hàng đó, hệ quản trị tiếp tục kiểm tra status và loại 8.500 hàng. Điều này không có nghĩa điều kiện status hoàn toàn vô dụng; nó chỉ cho thấy điều kiện đó không được dùng để thu hẹp phạm vi truy cập chỉ mục trong kế hoạch này.

Khi đọc kế hoạch, hãy hỏi:

1. Điều kiện nào được dùng để tìm khóa hoặc phạm vi chỉ mục?
2. Điều kiện nào chỉ được kiểm tra sau khi dữ liệu đã được đọc?
3. Có bao nhiêu hàng hoặc trang được đọc để tạo ra số hàng cuối cùng?
4. Số hàng bị loại ở bước Filter có lớn so với số hàng trả về không?

Nếu phần lớn hàng bị loại sau khi đọc, hãy điều tra xem điều kiện đó có thể được đưa vào chỉ mục phù hợp hay không. Nhưng cần cân nhắc thứ tự cột, chi phí cập nhật chỉ mục và khả năng các truy vấn khác sử dụng chỉ mục.

## 3. Hàm hoặc phép biến đổi đặt trên cột

Một nguyên nhân phổ biến làm điều kiện khó tận dụng chỉ mục B-tree thông thường là áp dụng hàm hoặc phép biến đổi lên cột được lập chỉ mục.

### 3.1. Hàm chuyển chữ hoa/thường

Giả sử có chỉ mục trên cột email:

~~~sql
CREATE INDEX users_email_idx ON users(email);
~~~

Điều kiện sau áp dụng hàm lên cột:

~~~sql
SELECT user_id
FROM users
WHERE LOWER(email) = 'alex@example.com';
~~~

Chỉ mục thông thường trên email được sắp theo giá trị email gốc. Nó không nhất thiết được sắp theo kết quả của LOWER(email), vì vậy hệ quản trị có thể phải tính hàm trên nhiều hàng rồi lọc.

Các lựa chọn tùy hệ quản trị:

- Chuẩn hóa dữ liệu khi ghi và lưu một giá trị canonical để truy vấn bằng phép so sánh trực tiếp.
- Tạo expression index trên LOWER(email) nếu hệ quản trị hỗ trợ.
- Dùng computed/generated column đã chuẩn hóa rồi lập chỉ mục trên cột đó.
- Chọn kiểu dữ liệu hoặc collation không phân biệt hoa thường nếu phù hợp với quy tắc nghiệp vụ và hệ quản trị.

Ví dụ PostgreSQL:

~~~sql
CREATE INDEX users_email_lower_idx
ON users (LOWER(email));

SELECT user_id
FROM users
WHERE LOWER(email) = 'alex@example.com';
~~~

Expression index giúp chỉ mục lưu khóa theo biểu thức LOWER(email). Truy vấn phải dùng biểu thức tương thích với biểu thức chỉ mục để optimizer có thể xem xét sử dụng nó. Cú pháp và giới hạn của expression/function-based index khác nhau theo hệ quản trị.

Không được loại bỏ LOWER hoặc thay đổi quy tắc so sánh chỉ để đạt Index Seek nếu điều đó làm thay đổi kết quả. Ví dụ, phép so sánh có thể chịu ảnh hưởng của collation, Unicode normalization, locale hoặc quy tắc xử lý ký tự đặc biệt.

### 3.2. Hàm trên cột ngày tháng

Một truy vấn thường gặp là lấy các bản ghi trong một ngày:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE DATE(created_at) = DATE '2026-11-19';
~~~

Hàm DATE được áp dụng lên created_at. Nếu chỉ mục được tạo trên created_at, biểu thức có thể khiến hệ quản trị không sử dụng được phạm vi B-tree thông thường một cách hiệu quả.

Có thể viết lại thành khoảng nửa mở:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= TIMESTAMP '2026-11-19 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-20 00:00:00';
~~~

Khoảng từ đầu ngày đến trước đầu ngày kế tiếp giữ nguyên mục tiêu lấy mọi thời điểm trong ngày và thường cho phép range scan trên chỉ mục created_at. Dùng dấu nhỏ hơn ở cận trên tránh phải đoán độ chính xác của timestamp như 23:59:59.999999.

Khi cột là timestamp có múi giờ, cần xác định ngày theo múi giờ nghiệp vụ. Hãy chuyển hai mốc biên sang cùng kiểu dữ liệu và múi giờ mà cột sử dụng. Ngày có chuyển đổi giờ mùa hè có thể dài 23 hoặc 25 giờ; không nên luôn cộng cố định 24 giờ nếu yêu cầu là một ngày lịch theo múi giờ địa phương. Cách tính biên phải bảo toàn ngữ nghĩa ban đầu.

### 3.3. Phép toán số học trên cột

Ví dụ:

~~~sql
SELECT *
FROM products
WHERE price * 1.1 > 100;
~~~

Điều kiện tính price nhân 1,1 cho từng hàng. Với giá trị dương và không có vấn đề về làm tròn/kiểu dữ liệu, có thể chuyển phép biến đổi sang phía hằng:

~~~sql
SELECT *
FROM products
WHERE price > 100 / 1.1;
~~~

Tuy nhiên, không được áp dụng phép biến đổi đại số một cách máy móc. Kiểu số nguyên, decimal, floating point, overflow, phép chia cho 0, làm tròn và quy tắc chuyển kiểu có thể khiến hai biểu thức không tương đương hoàn toàn. Cần xác định kiểu dữ liệu và ngữ nghĩa nghiệp vụ trước khi viết lại, rồi so sánh tập kết quả bằng kiểm thử.

Một ví dụ khác:

~~~sql
-- Khó tận dụng index trên quantity trong một số hệ quản trị
WHERE quantity + 5 >= 20

-- Có thể viết thành
WHERE quantity >= 15
~~~

Với số nguyên và phép cộng không tràn miền giá trị, hai điều kiện có cùng ý nghĩa. Nếu cột hoặc hằng có kiểu khác nhau, hãy kiểm tra chuyển kiểu ngầm định.

## 4. Chuyển kiểu ngầm định và kiểu dữ liệu không tương thích

So sánh hai vế có kiểu dữ liệu khác nhau có thể khiến hệ quản trị phải chuyển kiểu một phía. Nếu phép chuyển kiểu được áp dụng lên cột có chỉ mục, khả năng dùng chỉ mục có thể bị giảm hoặc mất, tùy quy tắc chuyển kiểu và optimizer.

Ví dụ, cột customer_code là VARCHAR nhưng ứng dụng gửi tham số kiểu số:

~~~sql
SELECT *
FROM customers
WHERE customer_code = 12345;
~~~

Hệ quản trị có thể chuyển kiểu cột hoặc tham số theo quy tắc ưu tiên kiểu dữ liệu. Nếu nó phải chuyển từng giá trị của cột sang số, chỉ mục chuỗi có thể không còn hữu ích cho phép tìm kiếm trực tiếp.

Nên truyền tham số đúng kiểu với cột:

~~~sql
SELECT *
FROM customers
WHERE customer_code = '12345';
~~~

Trong ứng dụng, kiểu dữ liệu của bind parameter phải khớp với kiểu cột. Không nên chỉ sửa literal trong SQL mà bỏ qua kiểu mà driver gửi đến máy chủ.

Khi điều tra:

- Kiểm tra kiểu dữ liệu của cột và kiểu tham số thực tế.
- Xem kế hoạch có CONVERT_IMPLICIT, CAST, implicit cast hoặc biểu thức chuyển kiểu trên cột không.
- Kiểm tra collation, độ dài VARCHAR/NVARCHAR, precision/scale của DECIMAL và kiểu thời gian.
- Sửa kiểu bind parameter hoặc chuyển đổi một giá trị hằng trước khi so sánh nếu ngữ nghĩa cho phép.
- Đo lại kế hoạch để xác nhận điều kiện trở thành Seek Predicate hoặc Index Cond phù hợp.

Không phải mọi phép cast đều làm điều kiện mất SARGability. Một phép chuyển kiểu an toàn trên hằng hoặc tham số có thể được thực hiện trước khi truy cập dữ liệu. Tác động phụ thuộc hệ quản trị, kiểu nguồn/đích và vị trí chuyển đổi.

## 5. LIKE, tìm kiếm chuỗi và wildcard

Với B-tree, tìm theo tiền tố thường có thể dùng một khoảng khóa:

~~~sql
SELECT product_id, sku
FROM products
WHERE sku LIKE 'AB12%';
~~~

Vì chuỗi bắt đầu bằng AB12, một số hệ quản trị có thể xác định vùng khóa tương ứng trên chỉ mục sku. Khả năng này phụ thuộc collation, kiểu dữ liệu, cấu hình operator class và phiên bản.

Ngược lại, điều kiện:

~~~sql
WHERE sku LIKE '%AB12%'
~~~

không xác định được một tiền tố cố định cho B-tree thông thường. Nó thường phải kiểm tra nhiều giá trị hơn. Nếu nhu cầu là tìm chuỗi con, hãy xem xét full-text search, trigram index, inverted index hoặc công cụ tìm kiếm phù hợp. Ví dụ PostgreSQL có extension pg_trgm hỗ trợ một số mẫu LIKE/ILIKE với trigram index; đây là cơ chế khác với B-tree.

Một số lưu ý:

- LIKE 'ABC%' thường có cơ hội dùng chỉ mục tốt hơn LIKE '%ABC'.
- LIKE '%ABC' cũng không có tiền tố cố định cho B-tree thông thường.
- ILIKE hoặc so sánh không phân biệt hoa thường phụ thuộc collation và loại chỉ mục.
- Escape ký tự wildcard nếu người dùng nhập dữ liệu cần tìm theo nghĩa literal.
- Không ghép chuỗi đầu vào không an toàn vào SQL; dùng bind parameter và xử lý escape đúng.

SARGability của LIKE không phải quy tắc tuyệt đối. Hãy kiểm tra kế hoạch và tài liệu của hệ quản trị đang chạy.

## 6. NOT, khác, OR và các điều kiện nhiều nhánh

Không nên kết luận rằng NOT hoặc OR luôn làm truy vấn mất khả năng dùng chỉ mục. Tác động phụ thuộc dạng biểu thức, selectivity và optimizer.

### 6.1. Điều kiện khác

Điều kiện:

~~~sql
WHERE status <> 'CLOSED'
~~~

có thể trả về phần lớn bảng. Dù hệ quản trị có thể dùng chỉ mục, một scan tuần tự có thể rẻ hơn. Ngoài ra, hàng có status NULL không thỏa điều kiện <> theo logic ba giá trị của SQL.

Nếu nghiệp vụ cho phép, có thể tách nhóm trạng thái hoặc dùng điều kiện rõ ràng hơn. Nhưng đừng thay <> bằng một tập IN tự đoán nếu danh sách trạng thái thay đổi theo nghiệp vụ.

### 6.2. OR

Điều kiện:

~~~sql
WHERE customer_id = 42
   OR sales_rep_id = 42
~~~

có thể sử dụng nhiều chỉ mục thông qua bitmap OR, index merge hoặc cơ chế kết hợp row identifier tùy hệ quản trị. Nếu optimizer không tìm được kế hoạch hiệu quả, có thể đánh giá cách viết lại thành UNION hoặc UNION ALL.

Ví dụ dùng UNION:

~~~sql
SELECT order_id
FROM orders
WHERE customer_id = 42
UNION
SELECT order_id
FROM orders
WHERE sales_rep_id = 42;
~~~

UNION loại bỏ hàng trùng và có thể cần sort/hash distinct. UNION ALL không loại trùng và chỉ tương đương với OR trong một số điều kiện cụ thể, ví dụ hai nhánh chắc chắn không thể cùng trả một hàng hoặc kết quả trùng được chấp nhận. Hãy bảo toàn ngữ nghĩa, NULL và duplicate trước khi viết lại.

### 6.3. IN và danh sách giá trị

Điều kiện IN thường có thể tận dụng chỉ mục:

~~~sql
WHERE status IN ('NEW', 'PAID', 'SHIPPED')
~~~

Nhưng danh sách rất dài có thể làm tăng chi phí lập kế hoạch hoặc tạo nhiều lần truy cập. Nếu danh sách đến từ một bảng tạm hoặc tập dữ liệu lớn, join với bảng đó có thể rõ ràng và hiệu quả hơn. Đo bằng dữ liệu đại diện để lựa chọn.

## 7. Điều kiện trên nhiều cột và thứ tự chỉ mục tổng hợp

Một điều kiện riêng lẻ có thể SARGable nhưng vẫn không dùng được phần cột mong muốn trong chỉ mục tổng hợp nếu thứ tự cột không phù hợp.

Giả sử có chỉ mục:

~~~sql
CREATE INDEX orders_customer_created_idx
ON orders (customer_id, created_at);
~~~

Truy vấn:

~~~sql
SELECT order_id
FROM orders
WHERE customer_id = 42
  AND created_at >= TIMESTAMP '2026-01-01 00:00:00';
~~~

Điều kiện bằng trên cột đầu tiên và điều kiện phạm vi trên cột tiếp theo phù hợp với thứ tự khóa của chỉ mục. Hệ quản trị có thể tìm vùng của customer_id 42 rồi quét phần khóa created_at trong phạm vi yêu cầu.

Nếu chỉ lọc created_at mà không có customer_id, chỉ mục này có thể không hiệu quả để tìm phạm vi toàn cục theo created_at vì created_at không phải cột dẫn đầu. Một số hệ quản trị có skip scan hoặc cơ chế khác, nhưng không nên mặc định tính năng đó có sẵn hay luôn hiệu quả.

Thứ tự cột nên được quyết định dựa trên workload:

- Các điều kiện bằng thường dùng.
- Điều kiện phạm vi và thứ tự sắp xếp.
- Join key.
- Số hàng dự kiến sau từng điều kiện.
- Khả năng bao phủ cột cần trả về.
- Chi phí ghi và dung lượng của chỉ mục.

Với B-tree tổng hợp, điều kiện bằng trên tiền tố thường quan trọng. Khi gặp điều kiện phạm vi ở một cột, khả năng dùng các cột tiếp theo để tiếp tục thu hẹp vùng quét có thể bị giới hạn tùy hệ quản trị và cách tổ chức chỉ mục. Hãy xem key columns, seek/range predicates và residual predicates trong kế hoạch.

## 8. NULL, IS NULL và chỉ mục một phần

Điều kiện IS NULL có thể tận dụng chỉ mục ở nhiều hệ quản trị, nhưng cách lưu và tìm NULL phụ thuộc loại chỉ mục và sản phẩm. Không nên mặc định NULL luôn bị loại khỏi B-tree hoặc luôn được xử lý giống nhau ở mọi DBMS.

Ví dụ, một bảng orders có nhiều đơn đang mở:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE closed_at IS NULL
ORDER BY created_at DESC;
~~~

Nếu chỉ một tỷ lệ nhỏ hàng có closed_at NULL, chỉ mục một phần có thể hữu ích trong PostgreSQL:

~~~sql
CREATE INDEX orders_open_created_idx
ON orders (created_at DESC)
WHERE closed_at IS NULL;
~~~

Chỉ mục chỉ lưu hàng thỏa điều kiện. Truy vấn phải có predicate mà optimizer có thể chứng minh phù hợp với điều kiện chỉ mục. Chỉ mục nhỏ hơn có thể giảm dung lượng và chi phí đọc, nhưng mọi thao tác thay đổi closed_at vẫn có thể phải cập nhật membership của chỉ mục.

Với SQL Server, filtered index có vai trò tương tự; với hệ quản trị khác cần xem tính năng tương ứng. Hãy xác minh kế hoạch, số hàng được lọc và chi phí ghi.

## 9. OR trên các cột khác nhau và dynamic search conditions

Ứng dụng tìm kiếm thường có nhiều bộ lọc tùy chọn. Một mẫu SQL phổ biến:

~~~sql
SELECT order_id, customer_id, status
FROM orders
WHERE (@customer_id IS NULL OR customer_id = @customer_id)
  AND (@status IS NULL OR status = @status);
~~~

Mẫu này dễ viết và có thể đúng về ngữ nghĩa, nhưng điều kiện OR phụ thuộc tham số có thể làm optimizer khó chọn một kế hoạch tốt cho mọi tổ hợp bộ lọc. Khi tham số NULL, một nhánh điều kiện trở thành TRUE và truy vấn có thể phải đọc nhiều dữ liệu. Khi tham số có giá trị chọn lọc cao, một kế hoạch seek có thể phù hợp hơn.

Các lựa chọn:

- Dùng các câu SQL riêng cho những tổ hợp bộ lọc thường gặp.
- Dùng dynamic SQL có tham số hóa để chỉ đưa các predicate thực sự cần vào câu lệnh.
- Với SQL Server, đánh giá OPTION (RECOMPILE) hoặc chiến lược parameter-sensitive plan theo phiên bản và workload.
- Với PostgreSQL, đánh giá custom/generic plan của prepared statement khi phân phối tham số khác biệt đáng kể.
- Với MySQL, kiểm tra prepared statement và cách optimizer xử lý điều kiện cụ thể.

Dynamic SQL phải dùng bind parameter cho giá trị dữ liệu. Không nối trực tiếp đầu vào người dùng vào chuỗi SQL. Cần giới hạn và kiểm soát phần tên cột, toán tử hoặc thứ tự sắp xếp nếu chúng được lựa chọn động, vì identifier không thể bind như một giá trị thông thường.

## 10. SARGable không đồng nghĩa chắc chắn có Index Seek

Ngay cả khi predicate có dạng SARGable, optimizer có thể chọn Table Scan hoặc Sequential Scan. Đây có thể là quyết định đúng khi:

- Điều kiện trả về phần lớn hàng của bảng.
- Bảng nhỏ hoặc nằm gọn trong cache.
- Truy cập chỉ mục sẽ dẫn đến quá nhiều lần đọc hàng ngẫu nhiên.
- Truy vấn cần nhiều cột không có trong chỉ mục.
- Thống kê cho thấy scan rẻ hơn.
- Tải hiện tại khiến phương án scan có chi phí tổng thấp hơn.

Ví dụ, cột status có chỉ mục nhưng truy vấn lấy 90% hàng với status <> 'ARCHIVED'. Quét tuần tự có thể đọc trang liên tục và rẻ hơn việc đi qua chỉ mục rồi truy cập bảng cho hầu hết hàng.

Vì vậy, mục tiêu là tạo điều kiện cho optimizer có lựa chọn truy cập hiệu quả và kiểm chứng bằng kế hoạch, chứ không phải ép mọi truy vấn dùng index. Hint ép chỉ mục có thể trở nên bất lợi khi dữ liệu hoặc phân phối tham số thay đổi.

## 11. Ví dụ tổng hợp: viết lại predicate ngày tháng

Giả sử ứng dụng có bảng events gồm hàng trăm triệu bản ghi và chỉ mục:

~~~sql
CREATE INDEX events_created_at_idx
ON events (created_at);
~~~

Truy vấn báo cáo:

~~~sql
SELECT COUNT(*)
FROM events
WHERE CAST(created_at AS DATE) = DATE '2026-11-19';
~~~

Kế hoạch có thể cho thấy scan trên phạm vi rộng và filter loại bỏ nhiều hàng vì phép CAST được áp dụng trên cột.

Viết lại:

~~~sql
SELECT COUNT(*)
FROM events
WHERE created_at >= TIMESTAMP '2026-11-19 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-20 00:00:00';
~~~

Quy trình xác minh:

1. Chạy cả hai câu trên cùng dữ liệu và cùng ngữ cảnh múi giờ.
2. So sánh số lượng kết quả để bảo đảm tương đương.
3. Xem execution plan của hai câu.
4. Kiểm tra predicate của chỉ mục có chứa hai biên thời gian hay không.
5. So sánh số hàng và buffer/page được đọc, thời gian thực thi, CPU và I/O.
6. Đo dưới tải đại diện, không chỉ một lần chạy khi cache nóng.

Nếu hai câu trả cùng kết quả nhưng kế hoạch mới đọc ít trang hơn và độ trễ cải thiện ổn định, việc viết lại có bằng chứng hiệu quả. Nếu optimizer vẫn chọn scan, có thể khoảng thời gian chứa phần lớn bảng hoặc chi phí scan thực sự thấp hơn; khi đó cần xem lại yêu cầu báo cáo, phân vùng theo thời gian hoặc cách lưu trữ.

## 12. Quy trình nhận diện predicate không SARGable

Hãy thực hiện theo các bước sau:

1. **Chọn truy vấn cần tối ưu.** Dùng thống kê tải hoặc trace để xác định truy vấn có tổng thời gian, p95/p99, tần suất hoặc I/O đáng kể.
2. **Thu thập kế hoạch.** Xem estimated plan và actual plan khi có thể đo an toàn. Ghi lại phiên bản DBMS, tham số, thống kê và mức tải.
3. **Tìm scan hoặc filter tốn kém.** Xác định toán tử đọc nhiều hàng/trang nhưng chỉ trả lại ít hàng.
4. **Đọc predicate.** Phân biệt Seek Predicate/Index Cond với residual Predicate/Filter; tìm hàm trên cột, phép toán, cast, wildcard đầu chuỗi hoặc OR tùy chọn.
5. **Kiểm tra kiểu dữ liệu.** So sánh kiểu cột với kiểu bind parameter; tìm implicit conversion và collation khác nhau.
6. **Đối chiếu chỉ mục.** Xem cột dẫn đầu, thứ tự cột, hướng sắp xếp, điều kiện partial/filtered và cột cần trả về.
7. **Đặt một giả thuyết cụ thể.** Ví dụ: “CAST trên created_at làm điều kiện không dùng được range seek của B-tree.”
8. **Viết lại hoặc thiết kế biểu thức phù hợp.** Bảo toàn ngữ nghĩa, NULL, múi giờ, collation, precision và duplicate.
9. **Đo lại.** So sánh kế hoạch, số hàng đọc, số hàng bị loại, logical/physical reads, CPU, thời gian và p95/p99.
10. **Đánh giá workload rộng hơn.** Kiểm tra chi phí ghi, dung lượng chỉ mục, truy vấn khác và hành vi khi tham số thay đổi.

Với PostgreSQL, có thể dùng EXPLAIN (ANALYZE, BUFFERS) cho truy vấn đọc trong môi trường phù hợp. Với SQL Server, xem Actual Execution Plan, Seek Predicates, Predicate và cảnh báo implicit conversion. Với MySQL, xem access type, key, used key parts, range và iterator details. Tên và cách hiển thị tùy phiên bản.

## 13. Các trường hợp cần thận trọng khi viết lại

### Bảo toàn logic NULL

SQL dùng logic ba giá trị. Ví dụ, phép phủ định của một điều kiện không nhất thiết đưa NULL vào kết quả. Viết lại predicate bằng De Morgan hoặc đổi NOT có thể thay đổi hàng được trả về nếu không xử lý NULL đúng.

### Bảo toàn kiểu số và độ chính xác

Chuyển phép toán từ cột sang hằng có thể thay đổi kiểu tính toán, làm tròn, overflow hoặc kết quả dấu phẩy động. Kiểm tra precision/scale, kiểu dữ liệu và miền giá trị.

### Bảo toàn ngày giờ và múi giờ

Khi đổi hàm lấy ngày thành khoảng thời gian, xác định chính xác múi giờ, độ chính xác timestamp và quy tắc ngày lịch. Dùng khoảng nửa mở thường tránh lỗi cận trên nhưng hai biên phải được tính đúng theo nghiệp vụ.

### Bảo toàn collation và so sánh chuỗi

So sánh chuỗi chịu ảnh hưởng của collation, phân biệt hoa thường, dấu, Unicode và khoảng trắng. Không loại bỏ hàm chuẩn hóa hoặc thay collation nếu kết quả so sánh thay đổi.

### Tránh tối ưu quá mức bằng cách tạo chỉ mục

Mỗi chỉ mục mới chiếm dung lượng và cần cập nhật khi INSERT, UPDATE, DELETE. Chỉ mục trên biểu thức hoặc chỉ mục một phần cũng có chi phí bảo trì. Trước khi tạo, hãy kiểm tra truy vấn thực sự có dùng nó và lợi ích có đủ bù chi phí hay không.

## 14. Bảng nhận diện nhanh

| Dạng điều kiện | Vấn đề có thể gặp | Hướng xử lý cần đánh giá |
|---|---|---|
| LOWER(email) = ... | Hàm đặt trên cột | Expression index, generated column hoặc chuẩn hóa dữ liệu |
| DATE(created_at) = ... | Hàm/cast trên cột thời gian | Khoảng nửa mở trên cột gốc |
| price * 1.1 > ... | Phép toán trên cột | Chuyển đổi sang phía hằng nếu bảo toàn kiểu và ngữ nghĩa |
| Cột VARCHAR so với tham số số | Implicit conversion | Bind parameter đúng kiểu |
| name LIKE '%abc%' | Không có tiền tố B-tree cố định | Trigram, full-text hoặc search index phù hợp |
| customer_id = ? AND created_at >= ? | Thứ tự cột index không phù hợp | Đánh giá chỉ mục tổng hợp theo workload |
| (@p IS NULL OR col = @p) | Predicate tùy chọn, OR phụ thuộc tham số | Câu SQL chuyên biệt hoặc dynamic SQL có tham số hóa |
| col IS NULL | Tùy loại index và tỷ lệ NULL | Kiểm tra index/partial/filtered index |
| status <> 'CLOSED' | Có thể trả về phần lớn bảng | So sánh chi phí scan và index; kiểm tra NULL |
| col1 = ? OR col2 = ? | Cần kết hợp nhiều nhánh | Bitmap/index merge hoặc UNION khi tương đương |

Các ví dụ trên là dấu hiệu để điều tra, không phải kết luận tuyệt đối. Một hệ quản trị có thể tối ưu một biểu thức bằng expression index, bitmap, range transformation hoặc cơ chế riêng. Luôn kiểm tra kế hoạch trên đúng phiên bản và dữ liệu đang dùng.

## 15. Checklist trước và sau khi viết lại predicate

- [ ] Đã xác định truy vấn và predicate đang tiêu tốn nhiều tài nguyên.
- [ ] Đã phân biệt điều kiện truy cập chỉ mục với điều kiện lọc sau khi đọc.
- [ ] Đã kiểm tra hàm, phép toán, cast, kiểu bind parameter và collation.
- [ ] Đã đánh giá LIKE, OR, NOT, IN và điều kiện tùy chọn theo hệ quản trị.
- [ ] Đã kiểm tra thứ tự cột trong chỉ mục tổng hợp.
- [ ] Đã cân nhắc tỷ lệ hàng được giữ lại và khả năng scan rẻ hơn seek.
- [ ] Đã bảo toàn NULL, precision, múi giờ và quy tắc so sánh.
- [ ] Đã so sánh tập kết quả trước và sau viết lại.
- [ ] Đã xác nhận kế hoạch dùng predicate phù hợp trong Seek Predicate/Index Cond hoặc dạng tương ứng.
- [ ] Đã đo số hàng/trang đọc, CPU, I/O, độ trễ và p95/p99 dưới tải đại diện.
- [ ] Đã kiểm tra chi phí ghi, dung lượng chỉ mục và tác động đến truy vấn khác.

Điều kiện SARGable tạo cơ hội để cơ sở dữ liệu tìm dữ liệu qua chỉ mục bằng khóa hoặc phạm vi phù hợp. Để nhận diện, hãy đọc predicate trong kế hoạch, tìm các phép biến đổi trên cột, chuyển kiểu không tương thích và điều kiện không khớp thứ tự chỉ mục. Khi viết lại, phải giữ nguyên ngữ nghĩa SQL và kiểm chứng bằng số hàng đọc, kế hoạch, độ trễ cùng tác động lên toàn bộ workload. Đó là cách biến một thay đổi cú pháp thành cải thiện hiệu năng có bằng chứng.
