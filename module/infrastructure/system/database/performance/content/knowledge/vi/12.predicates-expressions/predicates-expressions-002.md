# Hàm trên cột, phép toán và chuyển đổi kiểu ngầm trong điều kiện lọc

## Vì sao cách viết điều kiện lọc ảnh hưởng đến hiệu năng?

Một câu SQL có thể có chỉ mục phù hợp nhưng hệ quản trị vẫn phải quét nhiều hàng. Nguyên nhân đôi khi nằm ngay trong biểu thức của mệnh đề WHERE hoặc điều kiện JOIN: hàm được áp dụng lên cột, phép toán biến đổi giá trị cột, hoặc kiểu dữ liệu của cột không khớp với kiểu tham số. Những biểu thức này có thể khiến bộ tối ưu khó định vị trực tiếp vùng khóa trong chỉ mục.

Trong tối ưu hiệu năng cơ sở dữ liệu, cần xem điều kiện lọc như một phần của đường truy cập dữ liệu. Cách viết biểu thức ảnh hưởng đến khả năng sử dụng chỉ mục, ước lượng số hàng, số trang phải đọc, chi phí CPU và lượng dữ liệu phải lọc sau khi đọc. Đây là một phần quan trọng của phương pháp tối ưu dựa trên đo đạc, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu.

Một điều kiện **SARGable** (Search ARGument Able) là điều kiện có dạng cho phép hệ quản trị dùng giá trị so sánh để tìm kiếm hiệu quả trong chỉ mục hoặc cấu trúc truy cập phù hợp. Ví dụ, so sánh trực tiếp cột với một hằng hoặc tham số cùng kiểu dữ liệu thường dễ tối ưu hơn việc gọi hàm trên cột trong mỗi hàng.

Tuy vậy, SARGability không phải quy tắc cú pháp tuyệt đối. Một số hệ quản trị có thể biến đổi biểu thức, dùng expression index, computed column, generated column, bitmap hoặc chiến lược khác. Không thể kết luận chỉ từ việc nhìn thấy hàm hoặc phép toán. Cần kiểm tra kế hoạch thực thi và số liệu thực tế trên đúng hệ quản trị, phiên bản và workload.

## Điều kiện tìm kiếm và điều kiện lọc sau truy cập

Khi truy vấn dùng chỉ mục, điều kiện trong WHERE có thể được xử lý ở các giai đoạn khác nhau:

- **Điều kiện truy cập (seek predicate hoặc index condition):** giúp định vị khóa hoặc phạm vi khóa cần đọc trong chỉ mục.
- **Điều kiện lọc còn lại (residual predicate hoặc filter):** được kiểm tra sau khi hệ quản trị đã đọc các mục chỉ mục hoặc hàng ứng viên.
- **Điều kiện nối (join predicate):** xác định cách ghép hàng từ nhiều nguồn dữ liệu; kiểu dữ liệu và biểu thức của hai vế cũng ảnh hưởng đến đường truy cập.

Ví dụ, với chỉ mục B-tree trên cột created_at (literal TIMESTAMP dưới đây theo cú pháp PostgreSQL; ở hệ quản trị khác hãy bind tham số có kiểu phù hợp với cột):

~~~sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= TIMESTAMP '2026-11-01 00:00:00'
  AND created_at <  TIMESTAMP '2026-12-01 00:00:00';
~~~

Hệ quản trị có thể định vị đầu khoảng rồi duyệt đến cuối khoảng. Nếu điều kiện được viết thành CAST(created_at AS DATE) = ..., chỉ mục B-tree thông thường trên created_at có thể không định vị trực tiếp được ngày cần tìm, vì hệ quản trị phải tính biểu thức ngày cho từng giá trị hoặc cần một chỉ mục trên chính biểu thức đó.

Khi xem kế hoạch, hãy kiểm tra số hàng đọc trước lọc, số hàng sau lọc, seek predicate và residual predicate. Nếu truy vấn đọc hàng trăm nghìn hàng nhưng chỉ trả về vài trăm hàng, cần xác định phần chênh lệch đến từ điều kiện lọc còn lại, ước lượng sai hay một biểu thức không tận dụng được chỉ mục.

## Hàm áp dụng trực tiếp lên cột

### Hàm chuyển đổi ngày và thời gian

Một lỗi phổ biến là gọi hàm trích ngày trên cột timestamp:

~~~sql
-- Có thể khiến chỉ mục thông thường trên created_at khó được dùng để tìm phạm vi
SELECT order_id, created_at
FROM orders
WHERE DATE(created_at) = '2026-11-19';
~~~

Với nhiều hệ quản trị, cách viết này yêu cầu tính DATE(created_at) cho các hàng cần kiểm tra. Chỉ mục thông thường trên created_at lưu giá trị timestamp theo thứ tự, không trực tiếp lưu kết quả của phép chuyển đổi ngày.

Có thể viết lại thành khoảng nửa mở:

~~~sql
SELECT order_id, created_at
FROM orders
WHERE created_at >= TIMESTAMP '2026-11-19 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-20 00:00:00';
~~~

Khoảng nửa mở gồm thời điểm bắt đầu và loại trừ thời điểm kết thúc. Cách viết này bao gồm mọi độ chính xác phần lẻ giây của ngày 19, không cần đoán giá trị cuối như 23:59:59.997. Nó cũng tránh việc áp dụng hàm lên từng giá trị của cột trong điều kiện.

Nếu cột là timestamp có múi giờ, cần xác định ngày theo múi giờ nghiệp vụ. Hãy tính thời điểm bắt đầu ngày và bắt đầu ngày kế tiếp trong đúng múi giờ, sau đó so sánh theo instant tương ứng. Không tự ý dùng mốc UTC hoặc múi giờ máy chủ nếu yêu cầu nghiệp vụ là ngày địa phương.

### Hàm chữ hoa, chữ thường và chuẩn hóa chuỗi

Ví dụ:

~~~sql
SELECT customer_id, email
FROM customers
WHERE LOWER(email) = LOWER('User@Example.com');
~~~

Nếu chỉ mục thông thường được tạo trên email, biểu thức LOWER(email) có thể không khớp trực tiếp với khóa chỉ mục. Một số hướng xử lý:

1. Dùng collation không phân biệt hoa thường nếu phù hợp với quy tắc nghiệp vụ và hệ quản trị.
2. Tạo expression/function-based index trên LOWER(email) nếu hệ quản trị hỗ trợ.
3. Dùng cột chuẩn hóa được duy trì nhất quán, ví dụ email_normalized.
4. Chuẩn hóa giá trị ở thời điểm ghi và truy vấn theo cùng quy tắc.

Với PostgreSQL, có thể tạo chỉ mục biểu thức:

~~~sql
CREATE INDEX ix_customers_email_lower
ON customers (lower(email));
~~~

Sau đó điều kiện truy vấn cần dùng biểu thức tương thích:

~~~sql
SELECT customer_id, email
FROM customers
WHERE lower(email) = lower('User@Example.com');
~~~

Expression index có chi phí lưu trữ và duy trì khi dữ liệu thay đổi. Cần xác nhận hàm dùng trong chỉ mục đáp ứng yêu cầu tính ổn định/immutability của hệ quản trị.

Không thay LOWER() bằng collation tùy tiện. Quy tắc so sánh còn liên quan đến dấu, Unicode, locale và ngôn ngữ. Hai cách so sánh có thể không tương đương về ngữ nghĩa dù đều được mô tả là không phân biệt hoa thường.

### Hàm trên cột trong điều kiện nối

Điều kiện JOIN cũng có thể làm mất khả năng dùng chỉ mục:

~~~sql
SELECT o.order_id, c.customer_name
FROM orders AS o
JOIN customers AS c
  ON CAST(o.customer_code AS INTEGER) = c.customer_id;
~~~

Nếu kiểu dữ liệu hai cột khác nhau, hệ quản trị có thể phải chuyển đổi một phía khi nối. Khi phép chuyển đổi áp dụng lên cột được đánh chỉ mục, khả năng dùng chỉ mục để tìm hàng tương ứng có thể giảm.

Cách tốt hơn thường là thống nhất kiểu dữ liệu ở schema hoặc chuyển đổi dữ liệu ở biên ứng dụng trước khi lưu. Nếu chưa thể đổi schema, cần chọn cách chuyển đổi an toàn và kiểm tra kế hoạch. Không loại bỏ CAST nếu việc đó làm thay đổi cách so sánh hoặc khiến dữ liệu không còn khớp.

## Phép toán trên cột trong điều kiện lọc

### Cộng, trừ và nhân trên cột

Ví dụ:

~~~sql
SELECT product_id, price
FROM products
WHERE price * 1.1 > 100000;
~~~

Nếu có chỉ mục trên price, hệ quản trị có thể không dùng chỉ mục đó để tìm trực tiếp vì biểu thức so sánh nằm trên price * 1.1.

Có thể biến đổi đại số để đưa cột về một phía:

~~~sql
SELECT product_id, price
FROM products
WHERE price > 100000 / 1.1;
~~~

Cách biến đổi này có thể giữ khả năng dùng chỉ mục trên price, nhưng cần kiểm tra kiểu số, độ chính xác và quy tắc làm tròn. Với DECIMAL/NUMERIC, cần bảo đảm precision và scale không làm thay đổi kết quả biên. Với số thực dấu phẩy động, phép biến đổi có thể tạo sai khác do biểu diễn xấp xỉ.

Không phải phép toán nào cũng có thể chuyển đổi an toàn. Ví dụ:

~~~sql
WHERE price * quantity > 100000
~~~

Không thể đơn giản chia hai vế cho quantity nếu quantity có thể bằng 0, NULL hoặc âm. Cách viết lại cần xét miền giá trị, quy tắc NULL, kiểu số và nghiệp vụ. Nếu biểu thức là điều kiện quan trọng, có thể cân nhắc expression index hoặc cột tính toán được duy trì phù hợp.

### Phép cộng/trừ với ngày giờ

Ví dụ:

~~~sql
WHERE created_at + INTERVAL '7 days' < CURRENT_TIMESTAMP
~~~

Có thể viết lại thành:

~~~sql
WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '7 days'
~~~

Khi chuyển phép toán sang phía hằng hoặc tham số, cột có thể được so sánh trực tiếp với một mốc. Tuy nhiên, cần kiểm tra ngữ nghĩa múi giờ, kiểu timestamp, độ chính xác và cách hệ quản trị xử lý interval.

### Biểu thức bit, chuỗi và toán tử khác

Các biểu thức như column + 0, nối chuỗi, SUBSTRING(column, ...), COALESCE(column, ...) hoặc phép toán bit có thể làm hệ quản trị khó dùng chỉ mục thông thường trên cột. Mức độ ảnh hưởng phụ thuộc bộ tối ưu và loại chỉ mục.

Một số hệ quản trị có thể đơn giản hóa biểu thức như column + 0 trong một số kiểu dữ liệu; không nên dùng thủ thuật này với kỳ vọng chắc chắn. Hãy ưu tiên biểu thức rõ ràng, so sánh trực tiếp trên cột và xác minh kế hoạch.

### OR, NOT và phép so sánh khác

Không phải mọi điều kiện OR, NOT, <> hoặc != đều không SARGable. Optimizer có thể dùng index union, bitmap scan, nhiều nhánh truy cập hoặc chọn scan khi điều kiện trả về nhiều hàng.

Ví dụ:

~~~sql
WHERE status = 'READY'
   OR status = 'PROCESSING'
~~~

Có thể dùng chỉ mục trên status tùy độ chọn lọc và optimizer. Trong trường hợp khác, quét bảng có thể rẻ hơn. Hãy xem kế hoạch và số hàng thực tế trước khi tách OR thành UNION ALL; cách tách có thể làm thay đổi xử lý hàng trùng hoặc NULL nếu không thiết kế đúng.

## Chuyển đổi kiểu dữ liệu ngầm (Implicit Conversion)

### Chuyển đổi ngầm là gì?

Chuyển đổi ngầm xảy ra khi hai vế của biểu thức có kiểu dữ liệu khác nhau và hệ quản trị tự chọn một kiểu chung để thực hiện phép so sánh hoặc phép toán.

Ví dụ, cột lưu mã khách hàng là VARCHAR(20) nhưng tham số truyền vào là NVARCHAR(20) hoặc kiểu số. Hệ quản trị phải xác định cách chuyển đổi để so sánh. Tùy quy tắc ưu tiên kiểu dữ liệu và optimizer, phép chuyển đổi có thể được áp dụng lên tham số hoặc lên cột.

Nếu chuyển đổi được áp dụng lên cột, chỉ mục trên giá trị gốc có thể không còn được dùng hiệu quả để định vị. Ngay cả khi kế hoạch vẫn hiển thị một dạng index access, conversion có thể làm phát sinh residual filter hoặc đọc nhiều hàng hơn cần thiết.

### Ví dụ kiểu chuỗi không khớp

Giả sử SQL Server có cột customer_code VARCHAR(20) với chỉ mục. Ứng dụng gửi tham số NVARCHAR(20):

~~~sql
DECLARE @customer_code NVARCHAR(20) = N'C00125';

SELECT customer_id, customer_code
FROM dbo.customers
WHERE customer_code = @customer_code;
~~~

SQL Server có quy tắc ưu tiên kiểu dữ liệu; trong một số trường hợp, kế hoạch có thể thể hiện CONVERT_IMPLICIT trên cột customer_code. Điều này có thể cản trở index seek hoặc làm tăng số hàng phải đọc.

Giải pháp thường là khai báo tham số đúng kiểu, độ dài và collation phù hợp với cột:

~~~sql
DECLARE @customer_code VARCHAR(20) = 'C00125';

SELECT customer_id, customer_code
FROM dbo.customers
WHERE customer_code = @customer_code;
~~~

Cách sửa phải dựa trên schema thực tế và hợp đồng dữ liệu. Không đổi kiểu tham số chỉ để loại cảnh báo nếu dữ liệu có thể mất ký tự, sai encoding hoặc thay đổi quy tắc so sánh.

### Ví dụ số nguyên và số thập phân

Một cột INT được so sánh với tham số DECIMAL hoặc BIGINT có thể cần chuyển đổi. Nếu kiểu của tham số rộng hơn hoặc có độ chính xác khác, hệ quản trị có thể chọn chuyển đổi một phía theo quy tắc riêng.

Các rủi ro thường gặp:

- Chuyển đổi làm mất phần thập phân hoặc tràn miền giá trị.
- So sánh khác với ý định do scale/precision.
- Hàm chuyển đổi được áp dụng lên cột trong kế hoạch.
- Thống kê hoặc ước lượng cardinality thay đổi.
- Kế hoạch dùng chỉ mục kém hiệu quả hơn.

Hãy dùng tham số có kiểu tương thích với cột. Nếu nghiệp vụ cần so sánh số thập phân, hãy thiết kế cột và tham số với precision/scale phù hợp thay vì ép về số nguyên.

### Ví dụ kiểu ngày giờ

So sánh DATE, TIMESTAMP, DATETIME, DATETIME2 hoặc kiểu có múi giờ cần đặc biệt cẩn thận. Kiểu dữ liệu khác nhau có thể gây chuyển đổi, thay đổi độ chính xác hoặc diễn giải múi giờ khác nhau.

Ví dụ, nếu cột là datetime2 mà tham số là chuỗi, hệ quản trị hoặc driver có thể chuyển chuỗi theo định dạng và language/session settings. Hãy bind tham số kiểu ngày giờ thay vì nối chuỗi SQL. Dùng khoảng nửa mở và xác định đúng múi giờ nghiệp vụ.

### Không phải mọi implicit conversion đều làm mất index

Optimizer có thể chuyển đổi giá trị tham số một lần trước khi tìm kiếm và vẫn sử dụng chỉ mục. Điều đáng quan tâm là chuyển đổi nằm ở đâu, có áp dụng lặp lại trên từng hàng không, và kế hoạch thực tế cho thấy số hàng đọc ra sao.

Trong SQL Server, có thể tìm cảnh báo CONVERT_IMPLICIT trong kế hoạch XML hoặc giao diện execution plan. Trong PostgreSQL và MySQL, hãy xem kiểu của biểu thức, điều kiện index và cách EXPLAIN thể hiện truy cập. Tên cảnh báo không đồng nhất giữa sản phẩm.

## Kiểu tham số, collation và cách bind giá trị

### Khớp kiểu và độ dài với cột

Ứng dụng nên bind tham số có kiểu dữ liệu tương thích với cột:

- Cột VARCHAR thì dùng tham số chuỗi tương ứng khi phù hợp.
- Cột INT/BIGINT thì dùng tham số số nguyên cùng miền giá trị.
- Cột DECIMAL/NUMERIC thì chỉ định precision và scale thích hợp.
- Cột DATE/TIMESTAMP thì bind kiểu ngày giờ thay vì chuỗi định dạng tùy môi trường.
- Cột BINARY/UUID thì dùng kiểu tương ứng với cách lưu trữ trong database.

Độ dài tham số cũng quan trọng trong một số hệ quản trị và driver. Một tham số chuỗi quá rộng hoặc kiểu Unicode khác với cột có thể ảnh hưởng đến kế hoạch, so sánh và truyền dữ liệu. Kiểm tra metadata của prepared statement hoặc driver khi cần.

### Collation và so sánh chuỗi

Collation quy định cách so sánh và sắp xếp chuỗi, bao gồm phân biệt hoa thường, dấu và quy tắc ngôn ngữ. Nếu cột và tham số hoặc hai cột JOIN có collation khác nhau, hệ quản trị có thể phải chuyển đổi collation hoặc dùng biểu thức bổ sung.

Hãy thống nhất collation giữa các cột thường xuyên dùng trong điều kiện và phép nối. Nếu phải áp dụng COLLATE trong truy vấn, kiểm tra xem biểu thức đó có làm giảm khả năng sử dụng chỉ mục hay không. Không đổi collation chỉ để tăng tốc nếu nó làm thay đổi kết quả nghiệp vụ, chẳng hạn hai mã trước đây phân biệt hoa thường trở thành tương đương.

### Bind tham số thay vì nối chuỗi SQL

Prepared statement và parameter binding giúp tách dữ liệu khỏi cú pháp SQL, giảm nguy cơ SQL injection và tạo hợp đồng kiểu dữ liệu rõ ràng. Ví dụ ở tầng ứng dụng nên khai báo tham số đúng kiểu thay vì ghép giá trị vào chuỗi SQL.

Parameterization không tự bảo đảm kế hoạch tối ưu. Giá trị tham số có thể có độ chọn lọc khác nhau, gây parameter sniffing hoặc parameter sensitivity ở một số hệ quản trị. Hãy phân biệt vấn đề kiểu dữ liệu không khớp với vấn đề kế hoạch phụ thuộc tham số; chúng có thể cùng xuất hiện nhưng cần chẩn đoán riêng.

## Khi nào nên dùng expression index hoặc cột tính toán?

### Expression index / Function-based index

Nếu truy vấn thường xuyên lọc theo cùng một biểu thức, có thể tạo chỉ mục trên biểu thức đó thay vì viết lại truy vấn. Ví dụ PostgreSQL:

~~~sql
CREATE INDEX ix_users_lower_email
ON users (lower(email));
~~~

Truy vấn phải dùng biểu thức tương thích:

~~~sql
SELECT user_id
FROM users
WHERE lower(email) = lower('person@example.com');
~~~

Expression index có thể giúp định vị theo kết quả hàm. Tuy nhiên, biểu thức cần đáp ứng các quy tắc của hệ quản trị; ví dụ PostgreSQL yêu cầu hàm trong index expression có tính IMMUTABLE. Không phải hàm phụ thuộc thời gian, locale hoặc trạng thái bên ngoài đều hợp lệ.

### Computed column và generated column

Một lựa chọn khác là tạo cột tính toán hoặc cột sinh ra từ biểu thức, sau đó đánh chỉ mục trên cột đó.

SQL Server có computed column; tùy tính xác định, độ chính xác, kiểu dữ liệu và các thiết lập cần thiết, cột có thể được persisted và đánh chỉ mục. MySQL hỗ trợ generated column và functional index ở các phiên bản phù hợp. PostgreSQL hỗ trợ expression index và generated column ở các phiên bản hiện hành.

Ví dụ minh họa một cột chuẩn hóa email:

~~~text
email_normalized = LOWER(email)
~~~

Sau đó ứng dụng và truy vấn dùng email_normalized theo cùng quy tắc. Cần có cơ chế bảo đảm giá trị được cập nhật nhất quán; nếu dùng cột do ứng dụng tự duy trì, mọi đường ghi đều phải tuân theo hợp đồng này.

### Đánh đổi của chỉ mục biểu thức

- Tăng dung lượng lưu trữ và bộ nhớ cache.
- Tăng chi phí INSERT/UPDATE/DELETE vì biểu thức hoặc chỉ mục phải được cập nhật.
- Có thể làm chậm cập nhật khi cột đầu vào thay đổi thường xuyên.
- Phải bảo đảm biểu thức, collation và kiểu dữ liệu nhất quán giữa ghi và đọc.
- Cần xem các truy vấn khác có tận dụng được chỉ mục hay không.
- Có thể phát sinh yêu cầu về tính xác định, tính bất biến hoặc thiết lập session.

Chỉ tạo expression index khi có workload thực tế đủ quan trọng và phép đo chứng minh lợi ích. Không tạo một chỉ mục riêng cho mọi cách viết biểu thức.

## Đọc kế hoạch thực thi để xác định vấn đề

Khi nghi ngờ hàm, phép toán hoặc implicit conversion làm giảm hiệu quả truy cập, hãy xem:

1. **Access path:** bảng đang được scan hay dùng index seek/scan?
2. **Seek predicate / Index condition:** điều kiện nào thực sự được dùng để định vị khóa?
3. **Residual predicate / Filter:** điều kiện nào được kiểm tra sau khi đọc?
4. **Estimated Rows và Actual Rows:** optimizer ước lượng có sát số hàng thực tế không?
5. **Rows Read so với Rows Returned:** hệ quản trị đã đọc bao nhiêu hàng để trả kết quả?
6. **Conversion warning:** có CONVERT_IMPLICIT, cast hoặc collation conversion trên cột không?
7. **Logical reads, buffers và I/O:** số trang đọc và thời gian chờ có giảm sau khi sửa không?
8. **Loops và lookup:** biểu thức có làm một toán tử bị lặp quá nhiều lần không?
9. **CPU và elapsed time:** giảm thời gian lọc hay chỉ chuyển chi phí sang một phần khác?

Một Index Seek không tự động chứng minh truy vấn tốt. Seek có thể định vị một phạm vi rộng rồi lọc phần lớn hàng bằng residual predicate. Ngược lại, một scan có thể hợp lý khi điều kiện trả về phần lớn bảng.

## Quy trình cải thiện và kiểm chứng

Khi gặp một điều kiện lọc có hàm, phép toán hoặc chuyển đổi kiểu, hãy làm theo quy trình:

1. **Thu thập câu SQL thực tế.** Ghi fingerprint, kiểu và độ dài tham số, kiểu cột, collation và các giá trị đại diện.
2. **Đo baseline.** Thu thập p50/p95/p99, số hàng trả về, logical reads, buffer reads, CPU, I/O và throughput.
3. **Đọc kế hoạch.** Xác định điều kiện được dùng để seek, residual filter, conversion warning và chênh lệch estimated/actual rows.
4. **Nêu giả thuyết.** Ví dụ: hàm trên cột khiến hệ quản trị đọc nhiều hàng; tham số NVARCHAR làm cột VARCHAR bị chuyển đổi; biểu thức ngày giờ làm mất khả năng định vị khoảng.
5. **Chọn một thay đổi.** Viết lại điều kiện, sửa kiểu bind tham số, chuẩn hóa schema hoặc thử expression index nếu cần.
6. **Xác nhận tương đương ngữ nghĩa.** Kiểm tra NULL, biên thời gian, múi giờ, làm tròn, collation, overflow và các giá trị ngoại lệ.
7. **Chạy lại cùng workload.** Giữ dữ liệu, tham số, concurrency và trạng thái cache đủ tương đương; so sánh kế hoạch và số liệu.
8. **Đánh giá tác động phụ.** Kiểm tra chi phí ghi, dung lượng chỉ mục, các truy vấn khác và tỷ lệ lỗi.
9. **Theo dõi sau triển khai.** Quan sát đủ chu kỳ tải để xác nhận cải thiện bền vững.

Không thay đổi nhiều yếu tố cùng lúc nếu mục tiêu là xác định nguyên nhân. Một phép viết lại có thể giảm logical reads nhưng thay đổi cách xử lý NULL hoặc thời gian; nếu kết quả dữ liệu khác, đó không phải tối ưu đúng.

## Ví dụ tổng hợp: lọc đơn hàng theo ngày và trạng thái

Giả sử bảng orders có chỉ mục trên created_at, ứng dụng thường chạy:

~~~sql
SELECT order_id, status, total_amount
FROM orders
WHERE CAST(created_at AS DATE) = '2026-11-19'
  AND status = 'READY';
~~~

Kế hoạch cho thấy hệ quản trị đọc nhiều hàng theo thời gian rồi lọc kết quả của phép CAST. Nhóm cần kiểm tra số hàng đọc, số hàng trả về, kiểu cột và số liệu thống kê. Nếu created_at là timestamp và yêu cầu nghiệp vụ là ngày theo múi giờ cụ thể, hãy xác định chính xác hai mốc thời gian của ngày đó.

Một phiên bản điều kiện theo khoảng có thể là:

~~~sql
SELECT order_id, status, total_amount
FROM orders
WHERE created_at >= TIMESTAMP '2026-11-19 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-20 00:00:00'
  AND status = 'READY';
~~~

Nếu workload thường xuyên lọc đồng thời theo trạng thái và thời gian, có thể đánh giá chỉ mục ghép (status, created_at) hoặc (created_at, status) dựa trên các truy vấn quan trọng khác, độ chọn lọc và cách phân bố dữ liệu. Không chọn thứ tự chỉ từ một quy tắc chung; hãy so sánh kế hoạch và tải đọc/ghi thực tế.

Sau khi thay đổi, nhóm có thể ghi nhận:

| Chỉ số | Trước | Sau |
|---|---:|---:|
| Hàng đọc | 420.000 | 18.000 |
| Hàng trả về | 1.200 | 1.200 |
| Logical reads | 9.800 | 620 |
| p95 | 310 ms | 48 ms |
| CPU mỗi lần chạy | 85 ms | 19 ms |

Các số liệu chỉ minh họa cách trình bày. Phải xác nhận hai truy vấn trả về cùng tập kết quả, đặc biệt tại biên ngày, và đo với nhiều tham số. Nếu tham số trạng thái có độ chọn lọc khác nhau hoặc phân bố dữ liệu lệch theo thời gian, optimizer có thể chọn kế hoạch khác.

## Những sai lầm thường gặp

- **Cho rằng cứ có hàm trên cột là không thể dùng chỉ mục:** expression index, computed column hoặc optimizer transformation có thể hỗ trợ.
- **Viết lại biểu thức mà không kiểm tra ngữ nghĩa:** làm sai NULL, biên ngày, múi giờ, làm tròn hoặc collation.
- **Chỉ nhìn tên Index Seek:** bỏ qua residual predicate và số hàng thực tế phải đọc.
- **Bỏ qua implicit conversion:** tham số không đúng kiểu có thể làm cột bị chuyển đổi hoặc gây ước lượng sai.
- **Dùng chuỗi cho ngày giờ và số:** phụ thuộc định dạng, locale và quy tắc chuyển đổi của session.
- **Ép kiểu trên cột một cách tùy tiện:** có thể làm mất khả năng dùng chỉ mục và tạo lỗi khi gặp dữ liệu không hợp lệ.
- **Dùng LOWER/UPPER mà không xét collation:** kết quả so sánh có thể thay đổi theo ngôn ngữ và quy tắc Unicode.
- **Tạo expression index quá sớm:** tăng chi phí ghi và dung lượng mà chưa chứng minh workload cần.
- **Tách OR thành UNION ALL mà không xét trùng lặp:** có thể làm thay đổi kết quả.
- **Chỉ đo một giá trị tham số:** bỏ qua dữ liệu lệch và độ nhạy kế hoạch theo tham số.

## Checklist rà soát điều kiện lọc

- [ ] Cột trong WHERE/JOIN có bị bọc bởi hàm hoặc phép toán không?
- [ ] Có thể chuyển biểu thức sang phía hằng hoặc tham số mà vẫn giữ nguyên ngữ nghĩa không?
- [ ] Kiểu dữ liệu, độ dài, precision/scale và collation của tham số có khớp với cột không?
- [ ] Có implicit conversion hoặc conversion warning trong kế hoạch không?
- [ ] Điều kiện có dùng được seek predicate/index condition không?
- [ ] Residual predicate có khiến số hàng đọc lớn hơn nhiều số hàng trả về không?
- [ ] Estimated Rows có gần Actual Rows không?
- [ ] Có cần expression index, computed column hoặc generated column không?
- [ ] Thay đổi có bảo toàn NULL, múi giờ, biên thời gian, overflow và quy tắc so sánh không?
- [ ] Đã đo lại p95/p99, logical reads, CPU, I/O và chi phí ghi chưa?

## Kết luận

Hàm trên cột, phép toán và chuyển đổi kiểu ngầm có thể thay đổi cách hệ quản trị tìm dữ liệu trong chỉ mục. Khi điều kiện không phù hợp với cấu trúc chỉ mục, hệ quản trị có thể phải đọc nhiều hàng rồi lọc sau, làm tăng CPU, bộ nhớ và I/O. Cách xử lý có thể là viết lại điều kiện để so sánh trực tiếp trên cột, bind tham số đúng kiểu, chuẩn hóa schema hoặc tạo chỉ mục trên biểu thức khi workload chứng minh cần thiết.

Không có quy tắc cú pháp nào thay thế được phép đo. Hãy kết hợp điều kiện SQL với kế hoạch thực thi, thống kê, số hàng thực tế và chi phí tài nguyên; sau đó xác nhận kết quả trả về không đổi và workload tổng thể được cải thiện sau điều chỉnh.
