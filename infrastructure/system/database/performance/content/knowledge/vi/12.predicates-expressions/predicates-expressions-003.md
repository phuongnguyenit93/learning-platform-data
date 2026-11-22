# Kiểu dữ liệu tham số và ảnh hưởng đến khả năng dùng chỉ mục

## 1. Vì sao kiểu dữ liệu của tham số quan trọng?

Khi ứng dụng gửi câu SQL có điều kiện như `WHERE customer_id = :id`, hệ quản trị phải xác định kiểu dữ liệu của tham số và so sánh nó với kiểu của cột. Nếu kiểu, độ dài, độ chính xác hoặc collation không tương thích, hệ quản trị có thể phải chuyển đổi dữ liệu trước khi so sánh. Vị trí thực hiện chuyển đổi ảnh hưởng trực tiếp đến khả năng dùng chỉ mục.

Một phép chuyển đổi trên giá trị tham số thường chỉ cần thực hiện một lần hoặc một số ít lần trước khi tìm kiếm. Ngược lại, nếu hệ quản trị phải chuyển đổi giá trị của cột trên từng hàng, chỉ mục thông thường có thể không còn hỗ trợ phép tìm kiếm trực tiếp. Khi đó kế hoạch có thể phải quét nhiều trang, đánh giá biểu thức trên từng dòng hoặc dùng một điều kiện lọc phụ sau khi đọc dữ liệu.

Trong tối ưu hiệu năng cơ sở dữ liệu, kiểu dữ liệu tham số là một phần của thiết kế truy vấn và hợp đồng giữa ứng dụng với database driver. Cần đồng bộ kiểu dữ liệu giữa cột, tham số, literal và kiểu mà driver thực sự bind; sau đó kiểm tra execution plan và số đo tải để xác nhận chỉ mục được sử dụng hiệu quả.

Bài học này trình bày quan hệ kiểu dữ liệu, chuyển đổi ngầm định, khả năng tìm kiếm bằng chỉ mục (sargability), những tình huống thường gặp với số, chuỗi, ngày giờ và collation, cách bind tham số từ ứng dụng và quy trình kiểm chứng. Cú pháp ép kiểu, quy tắc ưu tiên kiểu và cách chọn kế hoạch khác nhau giữa các hệ quản trị; các ví dụ cần được điều chỉnh theo nền tảng đang dùng.

## 2. Cách hệ quản trị so sánh hai giá trị

### 2.1. Kiểu dữ liệu là một phần của phép so sánh

Một điều kiện so sánh không chỉ gồm toán tử `=`, `<` hoặc `>=`. Hệ quản trị còn phải biết kiểu của hai toán hạng, quy tắc chuyển đổi, độ chính xác, cách xử lý NULL và quy tắc so sánh chuỗi.

Ví dụ, cột `account_id` có kiểu `BIGINT`, nhưng ứng dụng bind tham số `account_id` dưới dạng chuỗi ký tự. Hệ quản trị phải quyết định có chuyển chuỗi thành số, chuyển số thành chuỗi hay từ chối phép so sánh. Quyết định này phụ thuộc hệ quản trị và khả năng suy luận kiểu của driver/câu lệnh.

Khi thiết kế điều kiện lọc, hãy biết rõ:

- Kiểu thực tế của cột trong schema.
- Kiểu, độ dài, precision và scale của tham số.
- Kiểu của literal nếu truy vấn dùng hằng số.
- Quy tắc ưu tiên kiểu và chuyển đổi ngầm định của hệ quản trị.
- Collation và quy tắc so sánh nếu dữ liệu là chuỗi.
- Kiểu thời gian có hoặc không có múi giờ nếu dữ liệu là ngày giờ.

Tên kiểu trông tương tự chưa chắc có cùng semantics. `VARCHAR`, `NVARCHAR`, `CHAR`, `TEXT`, `DECIMAL`, `NUMERIC`, `REAL`, `FLOAT`, `DATE`, `TIMESTAMP` và các biến thể theo engine có thể khác về lưu trữ, độ chính xác, so sánh và chuyển đổi.

### 2.2. Chuyển đổi tường minh và chuyển đổi ngầm định

Chuyển đổi tường minh (explicit conversion) xuất hiện trực tiếp trong SQL, chẳng hạn `CAST(:id AS BIGINT)`. Chuyển đổi ngầm định (implicit conversion) do hệ quản trị tự chèn vào biểu thức khi hai toán hạng có kiểu khác nhau.

Ví dụ khái niệm:

```sql
-- Cột là BIGINT, tham số được bind là VARCHAR
SELECT order_id
FROM orders
WHERE order_id = :order_id;
```

Trong câu lệnh trên, ứng dụng có thể gửi `:order_id` dưới dạng chuỗi. Tùy engine, bộ phân tích có thể chuyển tham số thành số, chuyển cột thành chuỗi hoặc báo lỗi nếu không thể chuyển đổi. Nếu phép chuyển đổi được áp dụng lên cột, khả năng dùng index seek/range scan có thể bị giảm.

Nguyên tắc thực hành là bind tham số bằng kiểu tương ứng với kiểu cột. Khi cần chuyển đổi, hãy xác định phía nào được chuyển đổi và liệu phép chuyển đổi có bảo toàn ngữ nghĩa, thứ tự và khả năng tìm kiếm hay không. Không nên thêm `CAST` theo cảm tính; ép kiểu sai có thể làm mất phần thập phân, tràn số, thay đổi múi giờ hoặc khiến giá trị không còn so sánh tương đương.

### 2.3. Vì sao chuyển đổi trên cột có thể cản trở chỉ mục?

Một chỉ mục B-tree lưu khóa theo thứ tự của giá trị cột. Để tìm nhanh một khoảng khóa, bộ tối ưu cần biến điều kiện thành một phạm vi có thể xác định trên chính thứ tự đó.

Nếu điều kiện là:

```sql
WHERE order_id = 900001
```

engine có thể tìm khóa `900001` trong B-tree. Nhưng nếu điều kiện được diễn giải thành:

```sql
WHERE CAST(order_id AS VARCHAR(30)) = '900001'
```

thì biểu thức so sánh áp dụng hàm chuyển đổi lên từng giá trị `order_id`. Chỉ mục trên giá trị số ban đầu không nhất thiết sắp xếp theo kết quả chuỗi đã chuyển đổi. Hệ quản trị có thể phải tính biểu thức cho nhiều dòng hoặc cần một chỉ mục biểu thức phù hợp.

Không phải mọi hàm trên cột đều khiến chỉ mục không thể dùng. Một số engine hỗ trợ expression index, function-based index, computed column được lập chỉ mục hoặc biến đổi biểu thức đặc biệt. Cần kiểm tra access path thực tế thay vì áp dụng quy tắc tuyệt đối.

## 3. Sargability và điều kiện có thể tìm kiếm bằng chỉ mục

### 3.1. Khái niệm sargable

Một điều kiện được gọi là sargable khi bộ tối ưu có thể dùng nó để xác định vùng khóa cần tìm trong một chỉ mục hoặc cấu trúc truy cập. Điều kiện bằng trên cột được lập chỉ mục, điều kiện khoảng và một số điều kiện tiền tố chuỗi thường có thể sargable nếu kiểu dữ liệu và collation phù hợp.

Ví dụ:

```sql
-- Có thể tìm kiếm theo khoảng trên index created_at
SELECT order_id, created_at
FROM orders
WHERE created_at >= :from_time
  AND created_at <  :to_time;
```

Điều kiện so sánh trực tiếp cột với hai tham số cho phép bộ tối ưu tìm vùng khóa thời gian cần đọc, miễn là tham số có kiểu tương thích và index phù hợp.

### 3.2. Biểu thức trên cột và cách viết lại

Một số cách viết khiến cột bị bọc bởi hàm hoặc chuyển đổi:

```sql
-- Có thể làm giảm khả năng dùng index thường trên created_at
WHERE CAST(created_at AS DATE) = :target_date

-- Thường có thể dùng index theo created_at tốt hơn
WHERE created_at >= :day_start
  AND created_at <  :next_day_start
```

Ở cách đầu, engine có thể phải tính `CAST(created_at AS DATE)` cho từng dòng. Ở cách thứ hai, cột được so sánh trực tiếp với một khoảng. Hai cách chỉ tương đương khi `day_start` và `next_day_start` được tính đúng theo kiểu thời gian và múi giờ của nghiệp vụ.

Một ví dụ khác:

```sql
-- Có thể khó tận dụng index thường trên email
WHERE LOWER(email) = LOWER(:email)

-- Có thể dùng index nếu collation đã đáp ứng quy tắc so sánh
WHERE email = :email
```

Nếu nghiệp vụ bắt buộc tìm không phân biệt hoa thường và collation hiện tại không đáp ứng, có thể cân nhắc cột chuẩn hóa, expression index hoặc kiểu/collation phù hợp. Việc viết lại phải giữ nguyên quy tắc so sánh mong muốn.

### 3.3. Điều kiện sargable không bảo đảm index seek

Ngay cả khi điều kiện sargable, bộ tối ưu vẫn có thể chọn table scan hoặc sequential scan. Nếu điều kiện trả về phần lớn bảng, đọc tuần tự có thể rẻ hơn việc tìm nhiều khóa rồi quay lại bảng lấy dữ liệu. Kích thước bảng, độ chọn lọc, clustering, cache, thống kê, số cột cần đọc và chi phí I/O đều ảnh hưởng quyết định.

Vì vậy, cần phân biệt hai câu hỏi:

1. Điều kiện có thể được chuyển thành tìm kiếm trên chỉ mục hay không?
2. Dùng chỉ mục có thực sự là phương án rẻ nhất cho workload và dữ liệu hiện tại hay không?

Không nên ép index seek chỉ để tránh một scan. Hãy so sánh logical reads, physical reads, CPU, thời gian và số hàng thực tế.

## 4. Kiểu số: integer, decimal và floating point

### 4.1. Integer có kích thước khác nhau

Các kiểu `SMALLINT`, `INTEGER/INT`, `BIGINT` có miền giá trị và kích thước lưu trữ khác nhau. Nếu cột là `BIGINT` nhưng ứng dụng bind `INT`, hệ quản trị có thể chuyển đổi tham số theo quy tắc của nó. Trong nhiều trường hợp, chuyển đổi sang kiểu rộng hơn ở phía tham số vẫn giữ khả năng tìm kiếm; nhưng không nên suy đoán mà hãy kiểm tra kế hoạch và quy tắc engine.

Bind đúng kiểu cột giúp tránh chuyển đổi không cần thiết và giảm sự mơ hồ trong việc chọn overload/toán tử. Đặc biệt, không nên bind khóa số dưới dạng chuỗi chỉ vì dữ liệu đến từ JSON hoặc form; hãy parse và kiểm tra miền giá trị ở tầng ứng dụng rồi bind bằng kiểu số thích hợp.

### 4.2. DECIMAL/NUMERIC precision và scale

`DECIMAL(p, s)` hoặc `NUMERIC(p, s)` mô tả số chữ số tối đa và số chữ số sau dấu thập phân. Tham số có precision/scale không tương thích có thể bị làm tròn, chuyển đổi hoặc gây lỗi tùy engine và driver.

Ví dụ, cột `amount` lưu `DECIMAL(12,2)`. Nếu tham số được bind dưới dạng floating point, giá trị thập phân có thể đã được biểu diễn gần đúng trong bộ nhớ trước khi gửi đến database. Với so sánh tiền tệ hoặc giá trị cần chính xác, nên dùng kiểu decimal tương ứng và đặt precision/scale phù hợp.

```sql
SELECT invoice_id
FROM invoices
WHERE amount >= :minimum_amount;
```

Tham số `:minimum_amount` nên được bind bằng kiểu decimal với độ chính xác phù hợp với cột và nghiệp vụ. Đừng tùy tiện ép cột sang `FLOAT` hoặc `VARCHAR` để khớp với tham số.

### 4.3. Phép tính số học trong predicate

Biểu thức như `WHERE quantity * unit_price > :limit` áp dụng phép tính lên cột và có thể khó dùng index trực tiếp trên `quantity` hoặc `unit_price`. Nếu biểu thức có thể biến đổi đại số an toàn, hãy xem liệu có thể chuyển phép tính sang phía tham số hoặc dùng cột tính toán/index biểu thức.

Ví dụ, với `quantity > 0`, điều kiện `quantity * 10 > :limit` có thể được viết lại thành `quantity > :limit / 10` nếu kiểu số, phép chia, làm tròn và xử lý tràn số được kiểm soát. Không áp dụng phép biến đổi nếu nó làm thay đổi semantics, đặc biệt với số nguyên, decimal scale, NULL hoặc phép chia cho 0.

## 5. Chuỗi: CHAR, VARCHAR, Unicode và collation

### 5.1. Độ dài và kiểu chuỗi

`CHAR(n)` thường có độ dài cố định hoặc semantics đệm khoảng trắng; `VARCHAR(n)` thường lưu chuỗi có độ dài biến đổi; kiểu Unicode như `NVARCHAR` hoặc kiểu chuỗi đa byte có hành vi phụ thuộc hệ quản trị. Kiểu của tham số nên tương ứng với kiểu cột, không chỉ tương ứng với nội dung ký tự nhìn thấy.

Độ dài bind cũng có thể ảnh hưởng đến metadata tham số và kế hoạch trong một số engine. Chẳng hạn, ứng dụng luôn bind chuỗi dưới dạng độ dài rất lớn dù cột chỉ có độ dài giới hạn có thể tạo chuyển đổi, ước lượng hoặc lựa chọn kế hoạch không mong muốn. Hãy khai báo độ dài tham số phù hợp với miền dữ liệu và driver.

### 5.2. Ví dụ chuyển đổi Unicode trên SQL Server

SQL Server có quy tắc ưu tiên kiểu dữ liệu. Trong một số phép so sánh giữa cột `VARCHAR` và tham số `NVARCHAR`, kiểu Unicode có mức ưu tiên cao hơn và có thể khiến biểu thức chuyển đổi phía cột. Nếu cột `VARCHAR` được lập chỉ mục, điều này có thể dẫn đến cảnh báo implicit conversion, predicate không còn seek hiệu quả hoặc scan tùy collation và kế hoạch.

Ví dụ minh họa:

```sql
-- Giả sử dbo.Customers.Code là VARCHAR(20) và có index
DECLARE @code NVARCHAR(20) = N'AB123';

SELECT CustomerId
FROM dbo.Customers
WHERE Code = @code;
```

Trong tình huống này, cần xem actual execution plan để xác định có `CONVERT_IMPLICIT` trên cột `Code` hay không. Nếu schema định nghĩa cột là `VARCHAR(20)` và dữ liệu nghiệp vụ không cần Unicode cho cột đó, bind tham số bằng `VARCHAR(20)` có thể tránh chuyển đổi không cần thiết:

```sql
DECLARE @code VARCHAR(20) = 'AB123';

SELECT CustomerId
FROM dbo.Customers
WHERE Code = @code;
```

Nếu cột được thiết kế là `NVARCHAR`, hãy bind tham số Unicode tương ứng. Không đổi kiểu cột hoặc bỏ hỗ trợ Unicode chỉ để làm mất cảnh báo; kiểu phải phản ánh đúng dữ liệu nghiệp vụ.

### 5.3. Collation và quy tắc so sánh

Collation xác định các quy tắc so sánh và sắp xếp chuỗi, có thể bao gồm phân biệt hoa thường, dấu, ngôn ngữ và thứ tự ký tự. Nếu cột và tham số/biểu thức dùng collation khác nhau, hệ quản trị có thể phải chuyển đổi hoặc áp dụng quy tắc so sánh bổ sung.

Ví dụ, tìm kiếm không phân biệt hoa thường trên cột có collation phân biệt hoa thường có thể được viết bằng `LOWER(column)`, nhưng điều này có thể làm giảm khả năng dùng index thường. Các lựa chọn gồm dùng collation phù hợp ngay trên cột, tạo cột chuẩn hóa, hoặc tạo expression/function-based index nếu engine hỗ trợ.

Collation cũng ảnh hưởng đến ý nghĩa của equality và range. Trước khi đổi collation hoặc ép kiểu, cần xác nhận kết quả so sánh có giữ nguyên yêu cầu nghiệp vụ và thứ tự sắp xếp hay không.

## 6. Ngày giờ, múi giờ và điều kiện khoảng

### 6.1. DATE, TIMESTAMP và kiểu có múi giờ

Hệ quản trị có thể cung cấp các kiểu ngày, giờ và timestamp với semantics khác nhau. Một số kiểu lưu ngày giờ không kèm múi giờ; một số kiểu biểu diễn thời điểm có quy tắc múi giờ hoặc chuẩn hóa riêng. Driver cũng có thể bind `Date`, `Timestamp`, `LocalDateTime`, `Instant` hoặc kiểu tương đương theo cách khác nhau.

Nếu cột `created_at` là timestamp có múi giờ, nhưng ứng dụng bind timestamp không múi giờ, engine hoặc driver có thể phải áp dụng quy tắc chuyển đổi dựa trên timezone/session. Điều này có thể làm thay đổi ranh giới thời gian cần tìm và ảnh hưởng kế hoạch hoặc kết quả.

Hãy thống nhất một mô hình thời gian: lưu thời điểm tuyệt đối hay giờ địa phương, timezone nào dùng để diễn giải ngày nghiệp vụ, và kiểu bind nào phù hợp với kiểu cột. Không dùng chuỗi ngày giờ tùy định dạng locale nếu có thể bind giá trị thời gian có kiểu rõ ràng.

### 6.2. Dùng khoảng nửa mở cho một ngày

Khi truy vấn dữ liệu trong một ngày, tránh áp dụng hàm chuyển đổi lên cột thời gian nếu có thể viết thành khoảng:

```sql
-- Có thể làm giảm khả năng dùng index thường trên created_at
WHERE CAST(created_at AS DATE) = :target_date

-- Khoảng nửa mở: bao gồm đầu ngày, không bao gồm đầu ngày kế tiếp
WHERE created_at >= :day_start
  AND created_at <  :next_day_start
```

Khoảng nửa mở tránh phải đoán độ chính xác tối đa của timestamp, chẳng hạn 23:59:59.997 hoặc 23:59:59.999999. Nó cũng cho phép tìm kiếm theo một khoảng liên tục trên chỉ mục thời gian.

Nếu ngày nghiệp vụ theo múi giờ địa phương, hãy tính `day_start` và `next_day_start` theo timezone đó rồi chuyển thành kiểu thời gian tương ứng trước khi bind. Không mặc định một ngày luôn dài đúng 24 giờ trong các khu vực có thay đổi giờ mùa hè.

### 6.3. Precision và ranh giới

Kiểu timestamp có thể có precision khác nhau. Tham số có precision thấp hơn hoặc cao hơn có thể được làm tròn hoặc chuyển đổi. Với điều kiện khoảng, việc làm tròn ranh giới có thể làm mất hoặc thêm bản ghi ở đầu/cuối khoảng.

Hãy bind tham số với kiểu và precision phù hợp; dùng khoảng nửa mở; và kiểm thử các giá trị sát biên, bao gồm đúng thời điểm bắt đầu, ngay trước thời điểm kết thúc và đúng thời điểm kết thúc.

## 7. Kiểu nhị phân, UUID và các kiểu đặc thù

Khóa có thể được lưu dưới dạng UUID/GUID, binary, enum hoặc kiểu riêng của engine. Nếu cột lưu UUID dạng 16 byte nhưng ứng dụng bind chuỗi có dấu gạch nối, hệ thống có thể phải parse hoặc chuyển đổi. Một số driver hỗ trợ bind UUID native; nếu có, nên dùng đúng kiểu đó.

Thứ tự byte và cách sắp xếp UUID có thể khác theo engine hoặc kiểu dữ liệu. Vì vậy, không nên tự chuyển UUID thành chuỗi hay byte theo một quy ước tùy ý rồi giả định thứ tự chỉ mục giống nhau. Hãy dùng mapping chuẩn của driver và xác nhận execution plan.

Với kiểu binary, cần phân biệt độ dài cố định và biến đổi, cách so sánh byte và độ dài tham số. Với enum hoặc domain type, cần xem kiểu toán hạng mà bộ phân tích nhận được và có cần cast sang đúng kiểu cột hay không.

## 8. Bind parameter từ ứng dụng và tác động đến kế hoạch

### 8.1. Bind kiểu dữ liệu thay vì gửi chuỗi tùy ý

Prepared statement giúp tách câu SQL khỏi giá trị dữ liệu, hỗ trợ tái sử dụng kế hoạch và giảm rủi ro injection khi dùng đúng cách. Tuy nhiên, prepared statement chỉ phát huy hiệu quả nếu ứng dụng bind tham số với kiểu, độ dài và precision phù hợp.

Ví dụ trong Java JDBC:

```java
String sql = "SELECT order_id FROM orders WHERE order_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, orderId); // order_id là BIGINT
    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("order_id");
            // xử lý kết quả
        }
    }
}
```

Nếu `order_id` là `INTEGER`, dùng phương thức bind integer phù hợp. Nếu là decimal, dùng `BigDecimal` và kiểm soát precision/scale. Nếu là ngày giờ, chọn kiểu Java và setter tương ứng với semantics của cột và driver. Tránh chuyển mọi giá trị thành chuỗi rồi bind bằng `setString`.

Tên setter không thay thế việc kiểm tra schema. Hãy xem metadata cột và tài liệu driver; một số driver có thể suy luận hoặc chuyển kiểu khác nhau tùy phiên bản và cấu hình.

### 8.2. Độ dài tham số và plan cache

Một số hệ quản trị lưu hoặc tái sử dụng kế hoạch dựa trên câu SQL và metadata tham số. Kiểu, độ dài, precision hoặc scale của tham số có thể ảnh hưởng đến việc biên dịch và lựa chọn kế hoạch. Nếu cùng câu SQL lúc bind chuỗi ngắn, lúc bind chuỗi rất dài hoặc khác kiểu, engine có thể tạo nhiều biến thể kế hoạch hoặc chọn kế hoạch dựa trên metadata của lần biên dịch đầu.

Hãy giữ metadata bind ổn định và phù hợp với schema. Nếu một câu truy vấn chạy nhanh/chậm tùy giá trị tham số, kiểm tra cả parameter sniffing/peeking, plan cache và phân bố dữ liệu; không quy mọi vấn đề kế hoạch cho kiểu dữ liệu.

### 8.3. Parameterized query không đồng nghĩa với kế hoạch tối ưu

Tham số hóa giúp an toàn và có thể cải thiện tái sử dụng kế hoạch, nhưng không bảo đảm bộ tối ưu biết trước mọi giá trị hoặc chọn một kế hoạch tốt cho mọi phân bố tham số. Với dữ liệu lệch mạnh, giá trị phổ biến và hiếm có thể cần kế hoạch khác nhau. Một số engine hỗ trợ kế hoạch thích ứng hoặc nhiều biến thể; một số cần chiến lược khác theo nền tảng.

Hãy kiểm tra actual rows so với estimated rows cho nhiều giá trị đại diện. Nếu kế hoạch được tối ưu cho một giá trị không đại diện, có thể cần cập nhật thống kê, điều chỉnh cách bind/biên dịch, tách truy vấn theo trường hợp hoặc dùng tính năng phù hợp của hệ quản trị.

## 9. Quy tắc thực hành để giữ predicate tương thích với chỉ mục

1. **Đối chiếu kiểu cột và kiểu tham số.** Xác định kiểu thực tế trong schema và kiểu driver gửi đến server.
2. **Khớp độ dài, precision và scale.** Đặc biệt với chuỗi, decimal và timestamp; tránh khai báo tham số quá rộng hoặc sai độ chính xác.
3. **Tránh chuyển đổi trên cột được lập chỉ mục.** Nếu cần cast, kiểm tra xem có thể chuyển tham số sang kiểu cột mà vẫn bảo toàn ngữ nghĩa hay không.
4. **Giữ cột ở dạng có thể tìm kiếm.** Ưu tiên điều kiện khoảng trên cột thời gian và tránh bọc cột bằng hàm nếu không có expression index phù hợp.
5. **Đồng bộ collation.** Xác định rõ quy tắc hoa thường, dấu và ngôn ngữ; tránh ép collation trên cột trong mọi lần truy vấn nếu có thể thiết kế collation/index phù hợp.
6. **Dùng kiểu native của driver.** Bind số, decimal, UUID, ngày giờ và binary theo kiểu phù hợp thay vì gửi tất cả dưới dạng chuỗi.
7. **Giữ semantics khi viết lại.** Kiểm tra NULL, làm tròn, overflow, timezone, padding chuỗi và so sánh trước khi thay đổi predicate.
8. **Xem xét expression index khi cần.** Nếu nghiệp vụ bắt buộc truy vấn theo biểu thức, cân nhắc chỉ mục trên biểu thức hoặc cột tính toán nếu engine hỗ trợ và chi phí ghi chấp nhận được.
9. **Đo trên nhiều giá trị tham số.** Kiểm tra giá trị phổ biến, hiếm, ngắn/dài và biên dữ liệu.
10. **Đánh giá toàn workload.** Một chỉ mục mới hoặc thay đổi kiểu bind có thể cải thiện truy vấn này nhưng ảnh hưởng truy vấn khác và chi phí insert/update/delete.

## 10. Ví dụ chẩn đoán từ execution plan

Giả sử bảng `customers` có cột `customer_code VARCHAR(20)` với chỉ mục B-tree. Ứng dụng gửi tham số dưới dạng `NVARCHAR(100)`. Truy vấn:

```sql
SELECT customer_id
FROM customers
WHERE customer_code = :code;
```

Actual plan trên một hệ quản trị có thể cho thấy implicit conversion trên cột, scan thay vì seek hoặc một residual predicate. Quy trình điều tra:

1. Kiểm tra kiểu và độ dài thực tế của `customer_code` trong schema.
2. Kiểm tra metadata bind của `:code` từ driver, không chỉ kiểu biến trong mã nguồn.
3. Đọc plan để tìm `CONVERT`, `CAST`, `CONVERT_IMPLICIT`, function trên cột hoặc cảnh báo conversion nếu engine cung cấp.
4. Kiểm tra index seek predicate và residual filter; xem engine có dùng được phần khóa nào của index.
5. Thử bind tham số đúng kiểu `VARCHAR(20)` trong môi trường kiểm thử nếu phù hợp với semantics của cột.
6. So sánh estimated/actual rows, logical reads, physical reads, CPU và elapsed time trước/sau.
7. Chạy với nhiều mã có độ dài khác nhau và xác nhận kết quả giống nhau.

Một bảng ghi nhận minh họa:

| Chỉ số | Bind NVARCHAR(100) | Bind VARCHAR(20) |
|---|---:|---:|
| Kiểu cột | VARCHAR(20) | VARCHAR(20) |
| Chuyển đổi trên cột | Có | Không |
| Access path | Scan | Index seek |
| Logical reads | 4.800 | 12 |
| Actual rows | 1 | 1 |
| Elapsed time | 42 ms | 3 ms |

Đây là số liệu giả định để minh họa, không phải kết quả bảo đảm trên mọi hệ quản trị. Nếu cả hai cách đều dùng seek, hoặc scan có chi phí thấp hơn do bảng nhỏ, kết quả có thể khác. Chỉ kết luận sau khi đọc plan thực tế và đo trên dữ liệu của hệ thống.

## 11. Những lỗi thường gặp

- **Bind mọi tham số dưới dạng chuỗi:** dễ tạo chuyển đổi ngầm định, sai semantics và kế hoạch kém.
- **Chỉ nhìn kiểu hiển thị trong code:** driver có thể bind kiểu, độ dài hoặc precision khác với suy nghĩ của lập trình viên.
- **Cast cột để khớp tham số:** có thể làm mất khả năng tìm kiếm trên index thường; hãy xem có thể cast tham số hoặc dùng expression index hay không.
- **Cho rằng implicit conversion luôn làm mất index:** chuyển đổi ở phía tham số có thể vẫn giữ seek; cần xem vị trí chuyển đổi và plan.
- **Cho rằng sargable luôn phải dùng seek:** scan có thể rẻ hơn khi truy vấn lấy phần lớn bảng.
- **Dùng FLOAT cho tiền tệ:** biểu diễn gần đúng có thể làm sai phép so sánh; ưu tiên decimal phù hợp.
- **So sánh ngày bằng cách cast cột:** có thể buộc tính hàm trên từng dòng; dùng khoảng nửa mở và tính ranh giới theo timezone.
- **Bỏ qua collation:** so sánh chuỗi có thể khác về hoa thường, dấu và thứ tự; ép collation có thể ảnh hưởng index.
- **Thay đổi kiểu schema chỉ để dập cảnh báo:** có thể ảnh hưởng dữ liệu, ứng dụng và các truy vấn khác; cần xác định kiểu đúng theo nghiệp vụ.
- **Chỉ kiểm tra một tham số:** phân bố giá trị và parameter sniffing có thể làm cùng câu SQL có hiệu năng khác nhau.

## 12. Bài tập tự kiểm tra

**Bài 1.** Cột `product_id` là `BIGINT` và có index. Ứng dụng bind giá trị dưới dạng chuỗi. Những vấn đề nào cần kiểm tra trước khi kết luận index không được dùng?

*Gợi ý:* Xem kiểu bind thực tế, quy tắc chuyển đổi của engine, phía bị chuyển đổi, kiểu toán tử so sánh, actual plan và số logical/physical reads. Thử bind kiểu số tương ứng trong môi trường kiểm thử.

**Bài 2.** Cột `created_at` có index. Truy vấn lọc bằng `CAST(created_at AS DATE) = :day`. Hãy viết lại điều kiện để có thể tìm theo khoảng.

*Gợi ý:* Dùng `created_at >= :day_start AND created_at < :next_day_start`, với hai tham số có kiểu timestamp tương thích và ranh giới được tính theo timezone nghiệp vụ.

**Bài 3.** Cột `amount` là `DECIMAL(12,2)`. Vì sao bind tham số bằng floating point có thể gây vấn đề?

*Gợi ý:* Floating point biểu diễn gần đúng; chuyển đổi sang decimal có thể tạo giá trị khác kỳ vọng hoặc làm tròn. Bind bằng decimal với precision/scale phù hợp.

**Bài 4.** Một truy vấn không phân biệt hoa thường dùng `LOWER(email) = LOWER(:email)`. Nêu hai cách để cải thiện khả năng dùng chỉ mục mà vẫn giữ semantics.

*Gợi ý:* Dùng collation phù hợp cho cột/index nếu hệ quản trị hỗ trợ, hoặc tạo expression/function-based index trên `LOWER(email)`. Phải xác nhận quy tắc Unicode và so sánh thực tế.

## 13. Ghi nhớ khi tối ưu

Kiểu dữ liệu của tham số quyết định cách hệ quản trị so sánh giá trị với cột. Nếu kiểu hoặc metadata không khớp, chuyển đổi ngầm định có thể xuất hiện; khi chuyển đổi áp dụng lên cột được lập chỉ mục, khả năng tìm kiếm trực tiếp có thể suy giảm. Kiểu chuỗi, Unicode, collation, decimal precision/scale và timezone của timestamp đều có thể ảnh hưởng đến kết quả lẫn hiệu năng.

Hãy bind tham số đúng kiểu và độ dài theo schema, giữ predicate ở dạng có thể tìm kiếm, tránh bọc cột bằng hàm khi không cần thiết và chỉ dùng expression index khi phù hợp. Sau mỗi thay đổi, kiểm tra actual execution plan, vị trí chuyển đổi, estimated/actual rows, logical/physical reads và thời gian trên nhiều giá trị tham số. Mục tiêu là giữ đúng semantics dữ liệu và giảm công việc thực tế của database trong toàn workload.
