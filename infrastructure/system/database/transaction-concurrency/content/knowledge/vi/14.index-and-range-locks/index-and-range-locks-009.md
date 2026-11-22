# Tác động của kiểu dữ liệu, biểu thức và tính khả dụng của chỉ mục

Trong cơ sở dữ liệu giao dịch, một chỉ mục có thể giúp câu truy vấn tìm đúng hàng nhanh hơn và giảm lượng dữ liệu phải quét. Nhưng việc có tạo được chỉ mục hay không, hệ quản trị có dùng chỉ mục đó hay không còn phụ thuộc vào kiểu dữ liệu, phép so sánh, biểu thức trong điều kiện WHERE, thứ tự cột trong chỉ mục, collation và kế hoạch thực thi.

Những yếu tố này ảnh hưởng trực tiếp đến điều khiển đồng thời. Khi một câu UPDATE, DELETE hoặc locking read phải quét nhiều hàng hay một phạm vi chỉ mục rộng, nó có thể giữ nhiều khóa hơn và làm giao dịch khác phải chờ. Với các cơ chế bảo vệ phạm vi như next-key lock của InnoDB, key-range lock của SQL Server hoặc predicate lock của PostgreSQL SSI, đường truy cập còn ảnh hưởng đến phạm vi dữ liệu được bảo vệ hoặc theo dõi.

Vì vậy, tối ưu truy vấn trong bài toán đồng thời không chỉ là giảm thời gian chạy. Cần hiểu kiểu dữ liệu và biểu thức có làm chỉ mục mất tác dụng hay không, hệ quản trị thực sự chọn đường truy cập nào, và đường truy cập đó tạo ra phạm vi khóa hoặc theo dõi xung đột ra sao.

## 1. Chỉ mục ảnh hưởng đến điều gì trong giao dịch?

Xét bảng đơn hàng có chỉ mục trên customer_id:

~~~sql
CREATE INDEX idx_orders_customer
ON orders (customer_id);
~~~

Một giao dịch cập nhật đơn hàng của một khách hàng:

~~~sql
UPDATE orders
SET status = 'PROCESSING'
WHERE customer_id = 42;
~~~

Nếu hệ quản trị dùng được chỉ mục, nó có thể tìm các mục customer_id = 42 trực tiếp. Nếu không dùng được chỉ mục, nó có thể phải quét phần lớn hoặc toàn bộ bảng.

Số hàng cuối cùng được cập nhật có thể giống nhau, nhưng công việc tìm hàng khác nhau đáng kể. Trong một hệ quản trị khóa theo bản ghi chỉ mục được quét, phạm vi quét rộng có thể làm tăng số tài nguyên bị khóa hoặc được xét. Khi giao dịch giữ khóa đến COMMIT, thời gian quét dài cũng kéo dài thời gian các giao dịch khác phải chờ.

Cần phân biệt ba khái niệm:

- **Chỉ mục tồn tại:** cấu trúc chỉ mục đã được tạo và hợp lệ trong cơ sở dữ liệu.
- **Chỉ mục có thể dùng:** điều kiện truy vấn, kiểu dữ liệu, biểu thức và quy tắc so sánh tương thích với chỉ mục.
- **Optimizer chọn chỉ mục:** bộ tối ưu hóa đánh giá chỉ mục là đường truy cập có chi phí thấp hơn các phương án khác.

Một chỉ mục có thể tồn tại nhưng không phù hợp với biểu thức truy vấn. Nó cũng có thể phù hợp nhưng optimizer vẫn chọn quét bảng vì bảng nhỏ, điều kiện trả về nhiều hàng hoặc thống kê cho thấy quét bảng rẻ hơn.

## 2. Điều kiện truy vấn có khả năng sử dụng chỉ mục

### 2.1. Sargability là gì?

Một điều kiện được gọi là *sargable* khi hệ quản trị có thể dùng nó để tìm kiếm hiệu quả qua chỉ mục, thường bằng cách xác định một giá trị hoặc khoảng khóa.

Ví dụ, nếu có B-tree index trên created_at:

~~~sql
SELECT id, created_at
FROM orders
WHERE created_at >= '2026-11-01 00:00:00'
  AND created_at <  '2026-12-01 00:00:00';
~~~

Điều kiện tạo ra một khoảng liên tục trên khóa created_at. Optimizer có thể dùng index range scan hoặc index seek tùy hệ quản trị.

Ngược lại:

~~~sql
SELECT id, created_at
FROM orders
WHERE EXTRACT(MONTH FROM created_at) = 11;
~~~

Biểu thức áp dụng hàm lên từng giá trị created_at. Chỉ mục B-tree thông thường trên created_at không nhất thiết giúp hệ quản trị xác định một khoảng khóa đơn giản. Hệ quản trị có thể phải tính hàm trên nhiều hàng rồi lọc kết quả.

Sargability không chỉ phụ thuộc việc có viết hàm hay không. Nó phụ thuộc optimizer có biến đổi biểu thức thành điều kiện trên khóa được lập chỉ mục hay có một chỉ mục biểu thức tương ứng hay không.

### 2.2. So sánh trực tiếp với cột được lập chỉ mục

Với chỉ mục:

~~~sql
CREATE INDEX idx_orders_created_at
ON orders (created_at);
~~~

Ưu tiên điều kiện tạo khoảng trên cột:

~~~sql
WHERE created_at >= :start_time
  AND created_at < :end_time
~~~

Thay vì:

~~~sql
WHERE DATE(created_at) = :target_date
~~~

Dạng khoảng thường dễ sử dụng B-tree index hơn. Nó cũng diễn đạt chính xác ranh giới thời gian và tránh việc áp dụng hàm lên từng giá trị của cột.

Tuy nhiên, không nên kết luận mọi hàm đều làm chỉ mục vô dụng. Một số hệ quản trị có thể tối ưu hoặc biến đổi một số biểu thức; chỉ mục biểu thức cũng có thể hỗ trợ trực tiếp. Cần xác nhận bằng execution plan.

### 2.3. Tránh biến đổi cột trong WHERE khi không cần thiết

Một số mẫu dễ làm giảm khả năng dùng chỉ mục:

~~~sql
WHERE LOWER(email) = 'linh@example.com'
~~~

~~~sql
WHERE amount + 10 = 100
~~~

~~~sql
WHERE CAST(customer_code AS INTEGER) = 42
~~~

Có thể viết lại nếu phép biến đổi tương đương về ngữ nghĩa và không làm sai quy tắc nghiệp vụ:

~~~sql
WHERE amount = 90
~~~

Với email không phân biệt hoa thường, có thể chuẩn hóa dữ liệu khi ghi, dùng collation phù hợp hoặc tạo expression index trên LOWER(email). Không nên tự ý thay đổi cách so sánh nếu dữ liệu hiện tại có quy tắc Unicode, locale hoặc collation đặc biệt.

### 2.4. LIKE và vị trí ký tự đại diện

Với B-tree index trên name, điều kiện bắt đầu bằng một tiền tố cố định thường có thể dùng index range scan:

~~~sql
WHERE name LIKE 'Nguyen%'
~~~

Điều kiện tìm chuỗi con thường khó dùng B-tree index thông thường:

~~~sql
WHERE name LIKE '%nguyen%'
~~~

Ký tự đại diện ở đầu khiến hệ quản trị không biết bắt đầu quét từ vị trí nào trong thứ tự B-tree. Một số hệ quản trị có chỉ mục chuyên biệt như trigram, full-text hoặc n-gram để hỗ trợ tìm chuỗi con.

Khả năng dùng B-tree cho LIKE còn phụ thuộc collation, operator class, kiểu dữ liệu và cấu hình. Ví dụ, PostgreSQL có thể cần operator class phù hợp cho pattern matching trong một số locale.

## 3. Kiểu dữ liệu và phép chuyển đổi ngầm

Kiểu dữ liệu của cột và kiểu dữ liệu của tham số nên tương thích. Khi hai vế có kiểu khác nhau, hệ quản trị có thể thực hiện implicit conversion (chuyển đổi ngầm). Vị trí chuyển đổi ảnh hưởng đến khả năng dùng chỉ mục và cả ngữ nghĩa so sánh.

### 3.1. Truyền tham số đúng kiểu cột

Giả sử cột được khai báo:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    external_code VARCHAR(30) NOT NULL
);

CREATE INDEX idx_customer_external_code
ON customer (external_code);
~~~

Khi tìm kiếm, tham số nên được bind với kiểu chuỗi phù hợp:

~~~sql
SELECT *
FROM customer
WHERE external_code = ?;
~~~

Trong JDBC, nếu cột là VARCHAR, dùng setString cho tham số:

~~~java
preparedStatement.setString(1, externalCode);
~~~

Không nên truyền một giá trị số rồi để driver hoặc hệ quản trị tự chuyển đổi nếu cột thực chất lưu mã dạng chuỗi. Các mã như "00042", "42A" hoặc "0042" có ngữ nghĩa chuỗi, không phải số học.

### 3.2. Chuyển đổi có thể được áp dụng lên cột

Một số hệ quản trị có quy tắc ưu tiên kiểu dữ liệu. Nếu kiểu của tham số có độ ưu tiên cao hơn kiểu cột, optimizer có thể cần chuyển đổi cột trước khi so sánh. Khi đó biểu thức thực tế có thể tương tự:

~~~sql
CONVERT_IMPLICIT(NVARCHAR(...), external_code) = @code
~~~

Nếu phép chuyển đổi nằm trên cột được lập chỉ mục và không thể được ánh xạ thành seek, kế hoạch có thể chuyển sang scan hoặc kém hiệu quả hơn.

SQL Server hiển thị nhiều phép chuyển đổi ngầm trong execution plan dưới dạng CONVERT_IMPLICIT. Tuy nhiên, không phải mọi implicit conversion đều làm mất index seek; optimizer có thể xử lý một số trường hợp. Hãy kiểm tra plan và cảnh báo conversion thay vì suy luận chỉ từ kiểu khai báo.

### 3.3. So sánh chuỗi với số trong MySQL

MySQL có quy tắc chuyển đổi kiểu khi so sánh. Việc so sánh cột chuỗi với tham số số có thể dẫn đến so sánh theo giá trị số và kết quả bất ngờ.

Ví dụ, các giá trị chuỗi '1', '01' và '1x' không mang cùng ý nghĩa nếu bị ép sang số. Truy vấn:

~~~sql
SELECT *
FROM customer
WHERE external_code = 1;
~~~

không nên được dùng để tìm mã chuỗi. Hãy truyền chuỗi:

~~~sql
SELECT *
FROM customer
WHERE external_code = '1';
~~~

Cách viết đúng kiểu giúp giữ ngữ nghĩa và thường giúp optimizer sử dụng chỉ mục phù hợp hơn.

### 3.4. PostgreSQL và cast tường minh

PostgreSQL phân giải toán tử dựa trên kiểu dữ liệu và các phép cast được cho phép. Nếu kiểu tham số không khớp, câu truy vấn có thể cần cast:

~~~sql
SELECT *
FROM customer
WHERE external_code = $1::varchar;
~~~

Nếu cột được lập chỉ mục là số nguyên nhưng truy vấn lại cast cột sang text:

~~~sql
WHERE CAST(customer_id AS TEXT) = '42'
~~~

chỉ mục B-tree thông thường trên customer_id không nhất thiết dùng được cho biểu thức đó. Có thể bind tham số đúng kiểu số:

~~~sql
WHERE customer_id = $1::bigint
~~~

Hoặc tạo expression index nếu phép cast là cách truy cập thường xuyên và có lý do nghiệp vụ rõ ràng.

### 3.5. Số học, precision và scale

So sánh DECIMAL/NUMERIC với FLOAT/DOUBLE có thể tạo chuyển đổi hoặc quy tắc so sánh khác nhau. Với giá trị tiền tệ, nên dùng kiểu số thập phân phù hợp và bind tham số cùng kiểu/precision cần thiết.

Ví dụ:

~~~sql
WHERE total_amount >= CAST(? AS DECIMAL(12, 2))
~~~

Cú pháp cast và cách bind cụ thể phụ thuộc driver. Mục tiêu là tránh để hệ quản trị phải chuyển đổi từng giá trị cột và tránh sai lệch do số thực dấu phẩy động.

Nếu cột có index trên DECIMAL nhưng ứng dụng truyền double, hãy kiểm tra plan và phép so sánh thực tế. Không nên mặc định rằng chuyển đổi luôn nằm ở phía tham số.

### 3.6. Ngày giờ và múi giờ

Điều kiện ngày giờ cần dùng kiểu dữ liệu và ranh giới phù hợp. Ví dụ, cột created_at lưu timestamp, truy vấn một ngày nên dùng khoảng nửa mở:

~~~sql
WHERE created_at >= :start_of_day
  AND created_at < :start_of_next_day
~~~

Tránh:

~~~sql
WHERE CAST(created_at AS DATE) = :day
~~~

Khoảng nửa mở có lợi vì:

- Không phải đoán độ chính xác nhỏ nhất của timestamp.
- Không bỏ sót các giá trị ở phần cuối ngày.
- Dễ dùng B-tree index trên created_at.
- Tránh áp dụng CAST lên từng giá trị cột.

Nếu nghiệp vụ dùng ngày theo múi giờ địa phương, hãy tính thời điểm bắt đầu và kết thúc của ngày trong đúng múi giờ rồi bind hai instant tương ứng. Ngày có chuyển đổi giờ mùa hè có thể dài hoặc ngắn hơn 24 giờ; không nên luôn lấy start + 24 giờ trong mọi múi giờ.

### 3.7. Kiểu dữ liệu và collation của chuỗi

Collation quyết định quy tắc so sánh và sắp xếp chuỗi, ví dụ phân biệt hoa thường, dấu hoặc quy tắc ngôn ngữ. Một truy vấn dùng collation khác với collation của chỉ mục có thể không sử dụng được chỉ mục theo cách mong muốn hoặc cần một đường truy cập khác.

Ví dụ, nếu ứng dụng muốn tìm không phân biệt hoa thường:

~~~sql
WHERE email COLLATE some_case_insensitive_collation = :email
~~~

Cú pháp collation phụ thuộc hệ quản trị. Nếu collation của biểu thức khác với collation của index, optimizer có thể không dùng được thứ tự khóa hiện có. Hãy xác định collation ngay trong thiết kế cột/chỉ mục hoặc tạo chỉ mục biểu thức phù hợp.

## 4. Biểu thức và chỉ mục biểu thức

### 4.1. Expression index là gì?

Expression index lưu kết quả của một biểu thức thay vì chỉ lưu trực tiếp giá trị cột. Nó giúp truy vấn tìm theo chính biểu thức đó.

Ví dụ PostgreSQL:

~~~sql
CREATE INDEX idx_customer_lower_email
ON customer (LOWER(email));
~~~

Truy vấn:

~~~sql
SELECT *
FROM customer
WHERE LOWER(email) = LOWER($1);
~~~

có thể dùng expression index vì biểu thức trong điều kiện phù hợp với biểu thức của chỉ mục.

Nếu chỉ có index thông thường trên email, hệ quản trị không nhất thiết có thể dùng nó để tìm theo LOWER(email).

### 4.2. Biểu thức phải khớp với định nghĩa index

Một expression index chỉ hữu ích khi truy vấn dùng biểu thức tương thích với định nghĩa index và kiểu dữ liệu, collation, operator class phù hợp.

Ví dụ, chỉ mục trên LOWER(email) không tự động phục vụ mọi phép tìm kiếm:

~~~sql
WHERE TRIM(LOWER(email)) = 'linh@example.com'
~~~

Biểu thức TRIM(LOWER(email)) khác với LOWER(email). Optimizer không thể mặc định bỏ qua TRIM vì khoảng trắng có thể ảnh hưởng kết quả.

Có thể tạo chỉ mục đúng biểu thức:

~~~sql
CREATE INDEX idx_customer_trim_lower_email
ON customer (TRIM(LOWER(email)));
~~~

Hoặc chuẩn hóa dữ liệu khi ghi để truy vấn đơn giản hơn. Hãy cân nhắc chi phí duy trì expression index mỗi khi INSERT/UPDATE và tính ổn định của hàm được dùng.

### 4.3. Generated column

Một lựa chọn là tạo generated/computed column lưu biểu thức đã chuẩn hóa:

~~~sql
ALTER TABLE customer
ADD email_normalized VARCHAR(255)
GENERATED ALWAYS AS (LOWER(TRIM(email))) STORED;
~~~

Sau đó tạo index:

~~~sql
CREATE INDEX idx_customer_email_normalized
ON customer (email_normalized);
~~~

Cú pháp và khả năng hỗ trợ generated column khác nhau giữa PostgreSQL, MySQL và SQL Server. Một số hệ quản trị dùng computed column và có yêu cầu riêng để cột được lập chỉ mục.

Generated column giúp ứng dụng truy vấn theo một tên cột rõ ràng, nhưng vẫn có chi phí lưu trữ hoặc tính toán và duy trì chỉ mục khi dữ liệu nguồn thay đổi.

### 4.4. Hàm phải đáp ứng yêu cầu của hệ quản trị

Một số hệ quản trị yêu cầu hàm trong expression index phải deterministic hoặc immutable. Nếu kết quả hàm thay đổi theo thời gian, locale, timezone, cấu hình session hoặc dữ liệu bên ngoài, chỉ mục có thể không phản ánh đúng thứ tự/giá trị cần tìm.

Ví dụ, không nên tạo chỉ mục dựa trên một hàm có kết quả phụ thuộc vào thời gian hiện tại rồi kỳ vọng nó tự cập nhật khi thời gian trôi qua. Chỉ mục chỉ được duy trì khi dữ liệu hàng thay đổi, không phải mỗi giây.

Trước khi tạo index trên biểu thức, kiểm tra yêu cầu về volatility/determinism, collation và quy tắc cập nhật của hệ quản trị.

### 4.5. Chỉ mục JSON và thuộc tính lồng nhau

Truy vấn một thuộc tính JSON có thể cần expression index hoặc kiểu index chuyên biệt.

Ví dụ PostgreSQL:

~~~sql
CREATE INDEX idx_event_type
ON event ((payload ->> 'type'));
~~~

Truy vấn tương ứng:

~~~sql
SELECT *
FROM event
WHERE payload ->> 'type' = 'PAYMENT';
~~~

Nếu truy vấn dùng biểu thức khác, cast khác hoặc toán tử JSON khác, index có thể không khớp. PostgreSQL cũng có GIN index cho các phép toán JSONB phù hợp, nhưng GIN có semantics và trade-off khác B-tree.

Với MySQL, có thể dùng generated column trích xuất thuộc tính JSON rồi lập chỉ mục trên cột đó. Hãy kiểm tra kiểu dữ liệu của giá trị trích xuất và cast cần thiết.

## 5. Thứ tự cột trong composite index

### 5.1. Leftmost prefix

Giả sử có chỉ mục ghép:

~~~sql
CREATE INDEX idx_orders_customer_status_created
ON orders (customer_id, status, created_at);
~~~

Thứ tự khóa là customer_id trước, rồi status, cuối cùng created_at.

Các truy vấn sau thường có thể khai thác chỉ mục:

~~~sql
WHERE customer_id = 42
~~~

~~~sql
WHERE customer_id = 42
  AND status = 'OPEN'
~~~

~~~sql
WHERE customer_id = 42
  AND status = 'OPEN'
  AND created_at >= :start_time
  AND created_at < :end_time
~~~

Nhưng truy vấn chỉ lọc status:

~~~sql
WHERE status = 'OPEN'
~~~

không có điều kiện trên cột dẫn đầu customer_id. B-tree index này thường không phải đường tìm kiếm hiệu quả cho điều kiện đó.

MySQL thường mô tả quy tắc này bằng leftmost prefix. PostgreSQL B-tree cũng có lợi nhất khi các cột dẫn đầu có điều kiện bằng và cột tiếp theo có điều kiện phạm vi. SQL Server cũng cần xét thứ tự key columns trong index.

### 5.2. Equality trước range

Một thiết kế thường hữu ích là đặt các cột có điều kiện bằng trước cột dùng điều kiện phạm vi:

~~~sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at);
~~~

Truy vấn:

~~~sql
SELECT *
FROM orders
WHERE customer_id = 42
  AND created_at >= :start_time
  AND created_at < :end_time;
~~~

Hệ quản trị có thể tìm vùng customer_id = 42 rồi quét khoảng created_at bên trong vùng đó.

Nếu đặt created_at trước customer_id, phạm vi thời gian có thể bao gồm đơn hàng của nhiều khách hàng; điều kiện customer_id được dùng để lọc thêm sau khi quét.

Đây là hướng dẫn thiết kế phổ biến, không phải quy tắc cứng cho mọi workload. Cần xét các truy vấn khác, ORDER BY, độ chọn lọc, phân bố dữ liệu và khả năng index-only/covering.

### 5.3. Cột sau điều kiện range

Với index (customer_id, created_at, status), truy vấn có customer_id bằng và created_at trong một khoảng có thể dùng hai cột đầu để xác định phạm vi. Điều kiện status có thể được dùng để lọc thêm, nhưng thường không thu hẹp range scan theo cách tương đương cột nằm trước range.

Nếu nhiều truy vấn cần status = 'OPEN' và thời gian trong khoảng, index (customer_id, status, created_at) có thể phù hợp hơn. Hãy thiết kế theo mẫu truy vấn thực tế thay vì chỉ theo cấu trúc bảng.

### 5.4. Index-only và covering index

Một chỉ mục có thể chứa đủ cột cần truy vấn để giảm việc truy cập bảng chính.

Ví dụ SQL Server:

~~~sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at)
INCLUDE (status, total_amount);
~~~

Hoặc PostgreSQL có INCLUDE:

~~~sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at)
INCLUDE (status, total_amount);
~~~

Covering index có thể giảm I/O đọc dữ liệu hàng. Nhưng nó không có nghĩa mọi locking read sẽ chỉ khóa index hoặc không khóa hàng. Hành vi khóa phụ thuộc hệ quản trị, câu lệnh và mức cô lập. InnoDB có thể cần truy cập clustered index record; SQL Server có thể lấy khóa ở index key hoặc row tùy plan và hint; PostgreSQL có cơ chế row lock riêng cho locking read.

Covering index làm tăng kích thước index và chi phí ghi khi các cột được INCLUDE thay đổi. Không nên thêm quá nhiều cột chỉ để tránh một lần truy cập bảng.

## 6. Partial index và filtered index

### 6.1. Chỉ mục cho một tập con dữ liệu

Một số hệ quản trị hỗ trợ chỉ mục có điều kiện, chỉ lưu các hàng thỏa predicate.

Ví dụ PostgreSQL:

~~~sql
CREATE INDEX idx_orders_open_customer
ON orders (customer_id, created_at)
WHERE status = 'OPEN';
~~~

Index này nhỏ hơn index toàn bảng nếu chỉ một phần đơn hàng đang OPEN. Truy vấn:

~~~sql
SELECT *
FROM orders
WHERE status = 'OPEN'
  AND customer_id = 42
  AND created_at >= :start_time;
~~~

có thể dùng index nếu optimizer chứng minh điều kiện truy vấn bao hàm predicate của index.

SQL Server hỗ trợ filtered index:

~~~sql
CREATE INDEX idx_orders_open_customer
ON orders (customer_id, created_at)
WHERE status = 'OPEN';
~~~

Cú pháp và giới hạn predicate khác nhau theo sản phẩm.

### 6.2. Predicate phải được chứng minh

Nếu index chỉ chứa status = 'OPEN', truy vấn tìm cả OPEN và CLOSED không thể dùng index đó để trả về đầy đủ kết quả.

~~~sql
WHERE customer_id = 42
~~~

không đủ để chứng minh mọi hàng cần trả về đều nằm trong partial index.

Với truy vấn tham số hóa:

~~~sql
WHERE status = :status
  AND customer_id = :customer_id
~~~

một generic plan có thể không biết :status luôn bằng 'OPEN'. Vì vậy, optimizer có thể không dùng partial index dù ở một lần thực thi cụ thể tham số thực tế là OPEN.

Khả năng suy luận predicate phụ thuộc optimizer và kiểu plan. Nếu cần, hãy kiểm tra plan cho prepared statement/generic plan và cân nhắc thiết kế chỉ mục tổng quát hơn.

### 6.3. Lợi ích và chi phí

Partial/filtered index có thể:

- Giảm kích thước chỉ mục.
- Giảm số mục phải duy trì khi dữ liệu nằm ngoài predicate.
- Tăng tốc các truy vấn thường truy cập tập con.
- Giảm số mục cần quét cho truy vấn phù hợp.

Nhưng nó cũng tạo ra yêu cầu rõ ràng về điều kiện truy vấn. Nếu status thay đổi từ OPEN sang CLOSED, hàng phải bị loại khỏi index; nếu từ CLOSED sang OPEN, hàng phải được thêm vào index. Những thay đổi này vẫn là công việc ghi và có thể tạo xung đột/khóa tại index.

## 7. Collation, operator class và kiểu phép so sánh

### 7.1. Collation thay đổi thứ tự chuỗi

B-tree index lưu các khóa theo một thứ tự. Nếu truy vấn dùng quy tắc so sánh khác với quy tắc đã dùng khi xây dựng index, index có thể không đáp ứng trực tiếp điều kiện hoặc thứ tự yêu cầu.

Ví dụ, tìm email không phân biệt hoa thường có thể dùng:

- Cột có case-insensitive collation.
- Expression index trên LOWER(email).
- Cột chuẩn hóa riêng.
- Chỉ mục chuyên biệt theo sản phẩm.

Cần thống nhất cách chuẩn hóa giữa INSERT, UPDATE và SELECT. Nếu chỉ truy vấn dùng LOWER nhưng khi ghi không chuẩn hóa, dữ liệu trùng theo quy tắc nghiệp vụ vẫn có thể tồn tại nếu thiếu UNIQUE constraint phù hợp.

### 7.2. Operator class trong PostgreSQL

PostgreSQL dùng operator class để xác định các toán tử nào có thể khai thác thứ tự của một kiểu index.

B-tree phù hợp với các toán tử so sánh thông thường như bằng, nhỏ hơn và lớn hơn. Các loại index khác có tập toán tử hỗ trợ riêng. Ví dụ, GIN phù hợp với một số phép toán trên array, JSONB và full-text; GiST hỗ trợ các loại dữ liệu và toán tử hình học/phạm vi nhất định.

Một index tồn tại nhưng không hỗ trợ toán tử được dùng trong WHERE thì không thể tự động phục vụ điều kiện đó. Cần chọn loại index và operator class theo phép truy vấn.

### 7.3. So sánh prefix, pattern và tìm kiếm toàn văn

Không nên dùng một loại index cho mọi kiểu tìm kiếm:

| Kiểu tìm kiếm | Cấu trúc có thể phù hợp |
|---|---|
| Bằng hoặc khoảng trên số/ngày/chuỗi có thứ tự | B-tree |
| Prefix search theo chuỗi | B-tree với collation/operator class phù hợp |
| Tìm chuỗi con | Trigram/n-gram hoặc full-text tùy ngữ nghĩa |
| Tìm từ và mức liên quan | Full-text index |
| Thuộc tính JSON và phép containment | Index JSON/GIN hoặc generated column tùy DB |
| Dữ liệu không gian | Spatial index như R-tree/GiST |

Chọn sai index có thể khiến optimizer scan nhiều mục, làm tăng thời gian và phạm vi tài nguyên bị chạm tới.

## 8. Tính khả dụng của chỉ mục trong optimizer

Ngay cả khi điều kiện có vẻ phù hợp, optimizer còn xét nhiều yếu tố trước khi chọn index.

### 8.1. Độ chọn lọc và thống kê

Nếu điều kiện trả về 80% số hàng, quét bảng tuần tự có thể rẻ hơn việc đi qua index rồi truy cập bảng chính cho từng hàng.

Optimizer dùng thống kê như:

- Số lượng hàng.
- Số giá trị phân biệt.
- Phân bố dữ liệu và histogram.
- Mức tương quan giữa thứ tự index và thứ tự vật lý.
- Thống kê đa cột hoặc extended statistics nếu có.
- Kích thước bảng và index.

Nếu thống kê cũ hoặc dữ liệu lệch, optimizer có thể ước lượng sai và chọn đường truy cập không phù hợp.

### 8.2. Bảng nhỏ

Một bảng rất nhỏ có thể được quét toàn bộ nhanh hơn dùng index. Điều này không nhất thiết là lỗi. Index có chi phí truy cập, tra cứu hàng và chuyển trang.

Nếu bảng lớn lên hoặc phân bố dữ liệu thay đổi, optimizer có thể chọn index ở thời điểm khác. Cùng một câu SQL không bảo đảm luôn có cùng plan.

### 8.3. Prepared statement và parameter sensitivity

Một prepared statement có thể được tối ưu với giả định về giá trị tham số. Trong một số hệ quản trị, plan được tái sử dụng hoặc chuyển giữa custom plan và generic plan.

Nếu customer_id = 42 có hàng triệu đơn hàng còn customer_id = 99 chỉ có vài hàng, một plan duy nhất có thể không tối ưu cho cả hai.

PostgreSQL có thể chọn generic plan hoặc custom plan cho prepared statement. SQL Server có hiện tượng parameter sniffing/parameter sensitivity. MySQL cũng có các quyết định optimizer và histogram riêng.

Nếu hiệu năng và lock footprint thay đổi mạnh theo giá trị tham số, hãy so sánh execution plan với nhiều giá trị đại diện. Không nên chỉ thử một tham số có phân bố thuận lợi.

### 8.4. Index không hợp lệ hoặc không sẵn sàng

Tùy hệ quản trị, index có thể ở trạng thái invalid, not ready, disabled hoặc invisible. Một index như vậy có thể không được optimizer dùng cho truy vấn thông thường.

Ví dụ PostgreSQL có thể hiển thị trạng thái hợp lệ trong pg_index; MySQL có invisible indexes; SQL Server có thể có index disabled. Hãy kiểm tra trạng thái index thay vì chỉ xác nhận tên index tồn tại trong metadata.

### 8.5. Hints và ép dùng index

Một số hệ quản trị cho phép index hint hoặc optimizer hint. Chúng có thể hữu ích trong trường hợp optimizer chọn plan không tốt, nhưng cũng có rủi ro:

- Dữ liệu thay đổi khiến index không còn chọn lọc.
- Thống kê thay đổi.
- Cấu trúc index được đổi tên hoặc thay thế.
- Hint buộc plan cũ dù một đường truy cập tốt hơn đã xuất hiện.
- Lock footprint không còn phù hợp với tải mới.

Chỉ dùng hint khi đã đo và có lý do cụ thể. Trước tiên nên sửa kiểu tham số, biểu thức, index design hoặc thống kê.

## 9. Đường truy cập ảnh hưởng đến phạm vi khóa

Đây là mối liên hệ quan trọng giữa chỉ mục và điều khiển đồng thời. Câu truy vấn xác định hàng cần thay đổi về mặt logic, nhưng đường truy cập quyết định hệ quản trị phải đi qua những mục dữ liệu nào để tìm chúng.

### 9.1. InnoDB: record lock, gap lock và next-key lock

InnoDB dùng index để thực hiện nhiều thao tác khóa. Khi UPDATE, DELETE hoặc locking read quét một index range, các bản ghi được quét có thể bị khóa theo quy tắc của mức cô lập.

Một số khái niệm:

- **Record lock:** khóa một bản ghi index cụ thể.
- **Gap lock:** khóa khoảng giữa các bản ghi index để ngăn chèn vào khoảng đó trong những trường hợp áp dụng.
- **Next-key lock:** kết hợp khóa bản ghi index và khoảng ngay trước bản ghi.

Ví dụ có index:

~~~sql
CREATE INDEX idx_payment_amount
ON payment (amount);
~~~

Truy vấn khóa theo khoảng:

~~~sql
START TRANSACTION;

SELECT *
FROM payment
WHERE amount >= 20
  AND amount < 40
FOR UPDATE;
~~~

Trong InnoDB ở REPEATABLE READ, locking range scan có thể dùng next-key lock trên các mục index liên quan. Giao dịch khác muốn chèn giá trị vào gap đang bị khóa có thể phải chờ dù nó không sửa một hàng đã tồn tại.

Nếu optimizer không dùng index amount và phải quét đường truy cập khác, tập bản ghi index được quét và phạm vi khóa có thể khác đáng kể. Vì vậy, kiểu dữ liệu và biểu thức làm index mất tác dụng có thể làm tăng phạm vi khóa.

Không nên suy ra chính xác các gap bị khóa chỉ từ câu SQL. Cần xem index được chọn, execution plan, isolation level và chi tiết InnoDB.

### 9.2. InnoDB: tìm chính xác bằng unique index

Một truy vấn equality trên toàn bộ khóa duy nhất thường có thể khóa một record thay vì cả một range:

~~~sql
SELECT *
FROM account
WHERE id = 42
FOR UPDATE;
~~~

Nếu id là PRIMARY KEY hoặc UNIQUE index và điều kiện khớp chính xác, phạm vi khóa thường hẹp hơn truy vấn range hoặc điều kiện không dùng được index.

Nếu điều kiện chỉ dùng một phần của composite unique key hoặc dùng biểu thức/cast khiến index không được dùng, phạm vi khóa có thể rộng hơn.

### 9.3. SQL Server: key-range lock ở SERIALIZABLE

SQL Server có thể dùng key-range locks để bảo vệ khoảng khóa khi mức cô lập SERIALIZABLE hoặc khi dùng hint phù hợp như HOLDLOCK.

Ví dụ:

~~~sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;

BEGIN TRANSACTION;

SELECT *
FROM reservation
WHERE room_id = 10
  AND start_time >= '2026-12-01 10:00:00'
  AND start_time <  '2026-12-01 11:00:00';

COMMIT;
~~~

Nếu có index phù hợp trên room_id và start_time, SQL Server có thể bảo vệ các key range tương ứng. Nếu truy vấn phải scan một index hoặc bảng rộng hơn, phạm vi khóa có thể rộng hơn và số khóa tăng.

Các chế độ key-range lock như RangeS-S, RangeS-U, RangeI-N và RangeX-X có quy tắc tương thích riêng. Không cần nhớ tên mọi chế độ để tối ưu, nhưng cần biết plan và index quyết định phạm vi key range được bảo vệ.

### 9.4. PostgreSQL: predicate lock trong SSI

PostgreSQL không dùng gap lock theo cách InnoDB thường dùng. Ở mức SERIALIZABLE, SSI theo dõi các phụ thuộc đọc/ghi bằng predicate lock, thường hiển thị với tên SIReadLock.

Các predicate lock này không phải khóa chặn thông thường. Chúng ghi nhận vùng dữ liệu đã đọc để hệ quản trị phát hiện lịch thực thi có nguy cơ không tuần tự hóa được.

Độ chi tiết theo dõi có thể phụ thuộc đường truy cập và cấu trúc dữ liệu:

- Index scan có thể cho phép theo dõi ở mức mục hoặc trang index phù hợp.
- Sequential scan có thể khiến hệ thống theo dõi ở mức quan hệ rộng hơn.
- Predicate lock có thể được gộp/nâng cấp từ mức nhỏ lên mức lớn để giới hạn metadata.

Khi phạm vi theo dõi thô hơn, các giao dịch không thực sự xung đột có thể bị xem là có phụ thuộc và một giao dịch bị hủy với serialization failure. Đây là false positive của cơ chế phát hiện, không phải một lần chờ do predicate lock chặn giao dịch khác.

### 9.5. Đọc thông thường và locking read

Cần phân biệt truy vấn SELECT thông thường với locking read.

- PostgreSQL và InnoDB dùng MVCC để SELECT thông thường đọc phiên bản phù hợp với snapshot trong nhiều trường hợp.
- SELECT ... FOR UPDATE có ý định khóa hàng và có thể chờ giao dịch khác.
- SQL Server có thể dùng shared lock cho đọc theo mức cô lập mặc định, hoặc row versioning nếu bật READ_COMMITTED_SNAPSHOT/SNAPSHOT.

Đường truy cập ảnh hưởng đến các hàng được tìm và khóa, nhưng loại câu lệnh và mức cô lập quyết định cơ chế khóa/phiên bản nào được áp dụng.

## 10. Ví dụ: biểu thức ngày làm tăng phạm vi quét và khóa

Giả sử bảng orders có index:

~~~sql
CREATE INDEX idx_orders_created_at
ON orders (created_at);
~~~

Một tiến trình xử lý các đơn hàng trong ngày:

~~~sql
UPDATE orders
SET status = 'ARCHIVED'
WHERE DATE(created_at) = '2026-11-14';
~~~

Nếu optimizer không thể dùng index created_at cho biểu thức DATE(created_at), nó có thể quét nhiều hàng hơn cần thiết. Trong InnoDB, điều đó có thể làm tăng số bản ghi được xét và khóa trong quá trình UPDATE. Trong SQL Server ở SERIALIZABLE, một đường scan rộng có thể dẫn đến phạm vi key-range lock lớn hơn. Trong PostgreSQL SSI, đường quét rộng có thể làm predicate tracking thô hơn.

Viết lại thành khoảng nửa mở:

~~~sql
UPDATE orders
SET status = 'ARCHIVED'
WHERE created_at >= '2026-11-14 00:00:00'
  AND created_at <  '2026-11-15 00:00:00';
~~~

Câu lệnh này thường dễ dùng B-tree index hơn. Hệ quản trị có thể tìm vùng ngày cần xử lý và giảm số hàng phải quét.

Nếu created_at là timestamp có múi giờ, hai giá trị biên phải được tạo theo múi giờ nghiệp vụ. Không nên mặc định ngày địa phương luôn tương ứng với đúng 24 giờ UTC.

## 11. Ví dụ: implicit conversion làm thay đổi đường truy cập

Giả sử mã khách hàng được lưu dưới dạng chuỗi:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    customer_code VARCHAR(20) NOT NULL
);

CREATE INDEX idx_customer_code
ON customer (customer_code);
~~~

Truy vấn đúng kiểu:

~~~sql
SELECT *
FROM customer
WHERE customer_code = '00042';
~~~

Truy vấn dùng số:

~~~sql
SELECT *
FROM customer
WHERE customer_code = 42;
~~~

Ở truy vấn thứ hai, hệ quản trị có thể chuyển đổi kiểu để so sánh. Kết quả có thể khác ý nghĩa mong muốn vì mã '00042' và '42' có thể là hai mã khác nhau. Khả năng dùng index cũng phụ thuộc vị trí và quy tắc chuyển đổi.

Cách đúng là bind tham số kiểu chuỗi. Không nên đổi kiểu cột sang số chỉ để tiện truy vấn nếu mã có thể chứa số 0 đầu, chữ cái hoặc ký tự định danh.

## 12. Ví dụ: composite index và thứ tự khóa

Giả sử bảng reservation có index:

~~~sql
CREATE INDEX idx_reservation_room_start
ON reservation (room_id, start_time);
~~~

Truy vấn theo phòng và thời gian:

~~~sql
SELECT *
FROM reservation
WHERE room_id = 10
  AND start_time >= :start_time
  AND start_time < :end_time;
~~~

Index có equality trên cột đầu room_id rồi range trên start_time, nên thường phù hợp.

Nếu truy vấn chỉ dùng start_time:

~~~sql
SELECT *
FROM reservation
WHERE start_time >= :start_time
  AND start_time < :end_time;
~~~

Index ghép trên room_id, start_time có thể không hiệu quả bằng index riêng trên start_time, vì không có điều kiện trên cột dẫn đầu. Optimizer có thể chọn scan hoặc một index khác.

Trong workload có khóa phạm vi, lựa chọn index cũng ảnh hưởng phạm vi dữ liệu được bảo vệ. Nếu một truy vấn khóa khoảng thời gian nhưng chỉ có index ghép bắt đầu bằng room_id, plan và phạm vi scan sẽ phụ thuộc điều kiện room_id. Nếu thiếu điều kiện đó, hệ quản trị có thể quét nhiều vùng hơn.

## 13. Chẩn đoán bằng execution plan

Không thể biết chắc index có được dùng chỉ bằng cách nhìn câu SQL hoặc danh sách index. Hãy xem kế hoạch thực thi thực tế.

### 13.1. PostgreSQL

Dùng:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM orders
WHERE created_at >= TIMESTAMP '2026-11-14 00:00:00'
  AND created_at <  TIMESTAMP '2026-11-15 00:00:00';
~~~

Các node thường gặp:

- Seq Scan: quét tuần tự bảng.
- Index Scan: đọc index rồi truy cập hàng.
- Index Only Scan: có thể trả kết quả từ index nếu điều kiện visibility map cho phép.
- Bitmap Index Scan/Bitmap Heap Scan: kết hợp tìm index với truy cập heap theo bitmap.

So sánh estimated rows và actual rows. Chênh lệch lớn có thể cho thấy thống kê hoặc ước lượng selectivity chưa phù hợp.

Với SERIALIZABLE, có thể xem predicate lock trong pg_locks:

~~~sql
SELECT
    locktype,
    mode,
    granted,
    relation::regclass AS relation,
    page,
    tuple,
    pid
FROM pg_locks
WHERE mode = 'SIReadLock';
~~~

SIReadLock không phải khóa chặn. Dùng log serialization failure và thông tin transaction để hiểu các phụ thuộc được theo dõi.

### 13.2. MySQL InnoDB

Dùng EXPLAIN:

~~~sql
EXPLAIN
SELECT *
FROM orders
WHERE created_at >= '2026-11-14 00:00:00'
  AND created_at <  '2026-11-15 00:00:00';
~~~

Ở các phiên bản hỗ trợ, EXPLAIN ANALYZE cho biết thời gian và số hàng thực tế của từng iterator.

Chú ý các cột/thuộc tính:

- type: access type như const, ref, range, index hoặc ALL.
- possible_keys: các index optimizer có thể cân nhắc.
- key: index thực tế được chọn.
- rows: số hàng ước lượng cần đọc.
- filtered: tỷ lệ hàng còn lại sau điều kiện.
- Extra: thông tin bổ sung như Using where hoặc Using index.

Để quan sát khóa đang giữ/chờ:

~~~sql
SELECT *
FROM performance_schema.data_locks;
~~~

~~~sql
SELECT *
FROM performance_schema.data_lock_waits;
~~~

Kết hợp lock information với EXPLAIN để xác định câu lệnh đang quét index nào và phạm vi nào có thể tạo chờ.

### 13.3. SQL Server

Dùng actual execution plan trong SSMS hoặc công cụ tương đương. Chú ý:

- Index Seek so với Index Scan hoặc Table Scan.
- Predicate và residual predicate.
- CONVERT_IMPLICIT trên cột.
- Estimated Rows so với Actual Rows.
- Key Lookup và số lần thực hiện.
- Memory grant, spill và parameter sensitivity.

Để quan sát khóa có thể dùng sys.dm_tran_locks kết hợp session/request và execution plan. Với SERIALIZABLE, hãy xác định key-range locks trên index nào được dùng.

Không nên chỉ nhìn tên Index Seek rồi kết luận lock footprint nhỏ. Một seek có thể trả về rất nhiều key hoặc khóa nhiều range; cần xét số hàng, loại khóa và mức cô lập.

## 14. Thống kê và kế hoạch có thể thay đổi

### 14.1. Thống kê lỗi thời

Nếu phân bố dữ liệu thay đổi mạnh, thống kê cũ có thể khiến optimizer ước lượng sai số hàng. Nó có thể chọn table scan dù index phù hợp hoặc chọn index có quá nhiều lookup.

Hãy cập nhật thống kê theo cơ chế của hệ quản trị và quan sát lại plan. Không nên thêm hint để che giấu vấn đề thống kê nếu có thể sửa nguyên nhân.

### 14.2. Data skew

Một giá trị có thể rất phổ biến trong khi các giá trị khác hiếm.

Ví dụ:

- customer_id = 1 có 40% số đơn hàng.
- customer_id = 9999 chỉ có vài đơn hàng.

Index seek có thể tốt cho 9999 nhưng không tốt cho 1. Plan được tái sử dụng cho cả hai có thể không tối ưu.

Trong workload giao dịch, plan kém không chỉ làm truy vấn chậm. Nó còn kéo dài thời gian giữ khóa, tăng số hàng được quét và tăng cơ hội chặn.

### 14.3. Plan thay đổi sau khi deploy

Một lần cập nhật thống kê, tạo index, thay đổi schema, thay đổi tham số hoặc nâng cấp phiên bản DB có thể làm optimizer chọn plan khác.

Nếu một giao dịch trước đây dùng seek hẹp nhưng sau deploy dùng scan rộng, tỷ lệ lock wait hoặc serialization failure có thể tăng dù câu SQL không đổi.

Khi điều tra sự cố đồng thời, hãy so sánh execution plan trước và sau thời điểm bắt đầu sự cố, cùng với thống kê và tham số đầu vào.

## 15. Thiết kế index cho workload có ghi đồng thời

### 15.1. Chỉ mục giảm phạm vi quét nhưng làm tăng chi phí ghi

Mỗi index bổ sung cần được duy trì khi INSERT, UPDATE hoặc DELETE. Nếu một bảng có nhiều index, một UPDATE có thể phải thay đổi nhiều cấu trúc.

Điều này làm tăng:

- CPU và I/O cho mỗi lần ghi.
- Số index page cần truy cập.
- Khả năng tranh chấp ở các trang index nóng.
- Chi phí WAL/redo/transaction log.
- Thời gian hoàn tất transaction.

Index có thể giảm phạm vi quét của một câu lệnh và đồng thời tăng công việc ghi của mọi thao tác khác. Cần đánh giá toàn bộ workload, không tối ưu một truy vấn riêng lẻ.

### 15.2. Index duy nhất và điểm tranh chấp

UNIQUE index bảo vệ tính duy nhất. Khi nhiều giao dịch chèn cùng một giá trị, chúng có thể phải phối hợp tại mục index đó. Thêm index không làm xung đột biến mất; nó giúp hệ quản trị phát hiện và bảo vệ ràng buộc.

Một giá trị khóa rất nóng, chẳng hạn một mã duy nhất được nhiều request tranh, có thể trở thành điểm contention. Hãy xử lý lỗi trùng và thiết kế luồng nghiệp vụ phù hợp.

### 15.3. Chọn index theo mẫu truy cập

Một index tốt cần phục vụ các điều kiện lọc, thứ tự sắp xếp và phạm vi cập nhật thường gặp.

Với mỗi index, hãy hỏi:

- Câu truy vấn nào sử dụng nó?
- Các cột dẫn đầu có được dùng trong WHERE không?
- Điều kiện có equality, range hay expression?
- Kiểu tham số và collation có tương thích không?
- Index có bị partial predicate giới hạn không?
- Index có giúp giảm số hàng được quét hay chỉ thêm chi phí ghi?
- Index có quá rộng hoặc chứa quá nhiều cột INCLUDE không?

Không tạo index chỉ vì một cột xuất hiện trong WHERE. Cần xem toàn bộ predicate và kế hoạch truy cập.

### 15.4. Index trên khóa ngoại

Index ở phía bảng con thường giúp tìm các hàng tham chiếu khi xóa hoặc cập nhật hàng cha.

Ví dụ:

~~~sql
CREATE INDEX idx_orders_customer_id
ON orders (customer_id);
~~~

Nếu thiếu index này, thao tác kiểm tra quan hệ có thể phải quét nhiều hàng con. Trong InnoDB, điều đó có thể làm tăng phạm vi bản ghi được quét/khóa. Với hệ quản trị khác, chi phí tìm kiếm và cơ chế khóa có thể khác.

Một số hệ quản trị tự tạo index cần thiết ở phía bảng con; PostgreSQL không tự động tạo index cho các cột khóa ngoại. Hãy kiểm tra hành vi cụ thể của hệ quản trị đang dùng.

## 16. Những nhầm lẫn thường gặp

**“Có index trên cột thì mọi truy vấn lọc cột đó đều dùng index.”**

Sai. Hàm, cast, collation, kiểu tham số, thứ tự cột ghép, predicate của partial index và chi phí ước lượng đều ảnh hưởng khả năng dùng index.

**“Index scan luôn tốt hơn table scan.”**

Sai. Nếu điều kiện trả về phần lớn bảng hoặc bảng rất nhỏ, scan có thể rẻ hơn. Cần xét số hàng thực tế và I/O.

**“Chỉ mục chỉ ảnh hưởng tốc độ đọc.”**

Sai. Index được duy trì trong INSERT/UPDATE/DELETE và ảnh hưởng đến phạm vi quét, khóa hoặc theo dõi xung đột.

**“Một câu UPDATE chỉ khóa những hàng cuối cùng được cập nhật.”**

Không thể mặc định như vậy. Trong một số hệ quản trị và mức cô lập, các bản ghi được quét trên đường truy cập cũng có thể bị khóa hoặc được theo dõi. Cần xem plan và lock behavior cụ thể.

**“Thêm index sẽ luôn giảm deadlock.”**

Sai. Index có thể thu hẹp scan nhưng cũng thêm cấu trúc cần duy trì và điểm tranh chấp. Deadlock còn phụ thuộc thứ tự lấy khóa trên hàng, index và các tài nguyên khác.

**“Cast tường minh luôn làm truy vấn chậm.”**

Sai. Cast ở tham số sang đúng kiểu cột thường hữu ích. Vấn đề thường là cast trên cột hoặc biểu thức không tương thích với index. Vẫn phải kiểm tra plan.

**“Nếu kết quả trả về ít hàng thì phạm vi khóa cũng ít.”**

Không nhất thiết. Một truy vấn có thể quét rất nhiều mục rồi lọc còn vài hàng. Lock footprint có thể phụ thuộc đường quét, không chỉ số hàng trả về.

**“PostgreSQL predicate lock giống gap lock của InnoDB.”**

Sai. InnoDB gap/next-key lock có thể chặn thao tác chèn vào khoảng được bảo vệ. Predicate lock trong PostgreSQL SSI chủ yếu theo dõi phụ thuộc để phát hiện nguy cơ serialization anomaly và không hoạt động như khóa chặn thông thường.

## 17. Quy trình chẩn đoán một truy vấn khóa quá rộng

Khi một UPDATE, DELETE hoặc locking read gây nhiều chờ khóa, hãy làm theo trình tự:

1. **Ghi lại câu SQL và tham số thực tế.** Không chỉ xem template; cần biết kiểu dữ liệu và giá trị bind.
2. **Kiểm tra kiểu cột và kiểu tham số.** Tìm implicit conversion, cast, collation mismatch hoặc so sánh chuỗi-số không đúng ngữ nghĩa.
3. **Xem biểu thức trong WHERE.** Xác định hàm, phép toán, cast, JSON extraction hoặc LIKE pattern có làm mất khả năng seek không.
4. **Kiểm tra composite index.** Xem điều kiện có sử dụng cột dẫn đầu, thứ tự equality/range và predicate của partial index.
5. **Đọc execution plan thực tế.** Xác định index/scan được chọn, số hàng ước lượng và thực tế, residual predicate và lookup.
6. **Xác định cơ chế khóa.** Với InnoDB xem record/gap/next-key locks; với SQL Server xem key-range locks và lock escalation; với PostgreSQL phân biệt row/table locks với SIReadLock.
7. **So sánh phạm vi quét với kết quả.** Nếu truy vấn trả về ít hàng nhưng quét rất nhiều, tìm nguyên nhân access path.
8. **Sửa truy vấn hoặc index có mục tiêu.** Bind đúng kiểu, viết điều kiện range, tạo expression/composite/partial index khi phù hợp.
9. **Đo lại dưới tải đồng thời.** So sánh latency, rows scanned, lock wait, deadlock/serialization failure và chi phí duy trì index.

Không nên dừng ở việc thấy index xuất hiện trong execution plan. Cần xác định index đó đã giảm bao nhiêu hàng phải quét và cơ chế khóa thực tế đã thay đổi ra sao.

## 18. Bảng gợi ý xử lý theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Index tồn tại nhưng plan dùng scan | Hàm trên cột, cast, collation, selectivity thấp | Xem predicate và plan |
| Truy vấn lọc chuỗi chậm | Bind sai kiểu, implicit conversion | So sánh kiểu cột và tham số |
| Lọc theo ngày quét nhiều hàng | CAST/DATE trên timestamp | Viết khoảng nửa mở |
| Điều kiện trên cột thứ hai không dùng composite index | Thiếu điều kiện cột dẫn đầu | Xem thứ tự key columns |
| Partial index không được chọn | Optimizer không chứng minh predicate | Kiểm tra điều kiện và prepared plan |
| Lock wait tăng sau deploy | Execution plan thay đổi | So sánh plan và thống kê |
| PostgreSQL SSI abort tăng sau khi plan chuyển sang Seq Scan | Predicate tracking có thể rộng hơn | Xem SIReadLock và serialization logs |
| InnoDB insert bị chặn dù không sửa cùng hàng | Gap/next-key lock trên range được quét | Xem data_locks và index access |
| SQL Server SERIALIZABLE khóa nhiều key | Range scan hoặc index không phù hợp | Xem actual plan và sys.dm_tran_locks |

## 19. Câu hỏi cần trả lời khi thiết kế truy vấn và chỉ mục

Trước khi kết luận một index sẽ giải quyết vấn đề đồng thời, hãy trả lời:

- Kiểu dữ liệu của cột và tham số có khớp nhau không?
- Có implicit conversion nào được áp dụng lên cột không?
- WHERE có gọi hàm, cast hoặc phép toán trên cột không?
- Có expression index hoặc generated column phù hợp không?
- Collation và operator class có hỗ trợ phép so sánh không?
- Với composite index, điều kiện có dùng các cột dẫn đầu không?
- Nếu dùng partial/filtered index, optimizer có chứng minh được predicate không?
- Optimizer thực sự chọn index nào với giá trị tham số đại diện?
- Số hàng thực tế được quét so với số hàng trả về là bao nhiêu?
- Ở mức cô lập hiện tại, đường truy cập đó tạo loại khóa hoặc predicate tracking nào?
- Chi phí duy trì index bổ sung có chấp nhận được với workload ghi không?

Kiểu dữ liệu, biểu thức và tính khả dụng của chỉ mục quyết định cách hệ quản trị tìm dữ liệu. Đường truy cập được chọn tiếp tục ảnh hưởng đến thời gian quét, phạm vi bản ghi được khóa và vùng dữ liệu được theo dõi khi kiểm soát khả tuần tự. Vì vậy, khi điều tra chờ khóa hoặc serialization failure, hãy kiểm tra cả câu SQL, kiểu tham số, định nghĩa index và execution plan thực tế; chỉ nhìn số hàng cuối cùng được cập nhật sẽ không giải thích được toàn bộ phạm vi xung đột.
