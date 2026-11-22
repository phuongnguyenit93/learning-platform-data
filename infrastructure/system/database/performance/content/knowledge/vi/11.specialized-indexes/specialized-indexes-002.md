# Chỉ mục biểu thức, chỉ mục hàm và cột sinh theo hệ quản trị

Trong truy vấn thực tế, điều kiện lọc không phải lúc nào cũng so sánh trực tiếp một cột với một giá trị. Ứng dụng có thể chuẩn hóa email bằng `LOWER`, bỏ khoảng trắng bằng `TRIM`, lấy ngày từ timestamp, chuyển chuỗi thành số hoặc tính một biểu thức nghiệp vụ. Nếu tạo chỉ mục chỉ trên giá trị gốc, hệ quản trị có thể không dùng được chỉ mục đó khi truy vấn áp dụng hàm lên cột.

**Chỉ mục biểu thức** (*expression index*), **chỉ mục hàm** (*function-based index*) và **cột sinh/cột tính toán** (*generated/computed column*) giải quyết nhóm vấn đề này. Chúng cho phép lưu hoặc lập chỉ mục giá trị được tính từ một hay nhiều cột, để truy vấn tìm kiếm theo cùng biểu thức có thể dùng đường truy cập hiệu quả. Tên gọi và khả năng triển khai khác nhau giữa PostgreSQL, Oracle, SQL Server và MySQL.

Trong module **DATABASE_PERFORMANCE**, việc chọn đúng loại chỉ mục chuyên biệt giúp cải thiện truy vấn mà vẫn kiểm soát chi phí ghi, dung lượng, thống kê và tính nhất quán của biểu thức. Cần hiểu rõ cách bộ tối ưu nhận diện biểu thức, yêu cầu về tính xác định của hàm và khác biệt theo hệ quản trị trước khi triển khai.

## 1. Vấn đề khi truy vấn áp dụng hàm lên cột

Giả sử bảng `customer` có cột `email` và ứng dụng muốn tìm email không phân biệt chữ hoa, chữ thường:

```sql
SELECT customer_id, display_name
FROM customer
WHERE LOWER(TRIM(email)) = LOWER(TRIM(?));
```

Nếu chỉ có chỉ mục B-tree thông thường trên `email`, hệ quản trị có thể không sử dụng nó như một phép tìm kiếm trực tiếp theo khóa, vì giá trị cần so sánh là kết quả của `LOWER(TRIM(email))`, không phải giá trị `email` nguyên bản. Tùy hệ quản trị, bộ tối ưu có thể quét bảng hoặc chọn một kế hoạch khác có chi phí cao.

Một số biểu thức thường gặp:

| Nhu cầu truy vấn | Biểu thức trên cột | Vấn đề nếu chỉ có index trên cột gốc |
|---|---|---|
| Tìm văn bản không phân biệt hoa thường | `LOWER(username)` | Khóa chỉ mục gốc có thể không tương ứng với giá trị đã chuyển chữ thường |
| Chuẩn hóa khoảng trắng | `TRIM(code)` | Giá trị so sánh đã thay đổi so với dữ liệu lưu |
| Tìm theo ngày | `CAST(created_at AS DATE)` hoặc hàm tương đương | Phép biến đổi timestamp có thể cản trở range seek trên cột gốc |
| Truy vấn theo phần của mã | `SUBSTRING(code, 1, 3)` | Chỉ mục trên toàn bộ chuỗi không trực tiếp biểu diễn phần tiền tố được tính |
| Tính giá trị nghiệp vụ | `quantity * unit_price` | Mỗi lần truy vấn phải tính biểu thức và có thể không có khóa chỉ mục tương ứng |

Không phải mọi điều kiện có hàm đều chắc chắn làm mất khả năng dùng index. Một số hệ quản trị có thể biến đổi biểu thức, dùng chỉ mục phù hợp hoặc tối ưu một số phép so sánh đặc biệt. Cần kiểm tra execution plan thực tế.

## 2. Ba cách biểu diễn giá trị đã tính

### Chỉ mục biểu thức hoặc chỉ mục hàm

Chỉ mục được xây dựng trực tiếp trên biểu thức tính từ cột. Giá trị biểu thức được tính khi tạo hoặc cập nhật chỉ mục và được lưu trong cấu trúc chỉ mục. Truy vấn có biểu thức tương thích có thể tìm theo khóa đã tính mà không cần tạo một cột vật lý riêng trong bảng.

Ví dụ khái niệm:

```sql
CREATE INDEX ix_customer_email_normalized
ON customer (LOWER(TRIM(email)));
```

Tên cú pháp khác nhau: PostgreSQL gọi đây là expression index; Oracle thường gọi là function-based index. Một số nền tảng khác triển khai thông qua cột tính toán hoặc cột sinh.

### Cột sinh hoặc cột tính toán

Cột sinh có giá trị được xác định bởi biểu thức dựa trên các cột khác. Ứng dụng không nhất thiết phải tự ghi giá trị đó. Hệ quản trị tính giá trị theo quy tắc của cột, sau đó có thể cho phép tạo chỉ mục trên cột này.

Ví dụ:

```sql
-- Cú pháp minh họa trên hệ quản trị hỗ trợ generated column.
ALTER TABLE customer
ADD COLUMN email_normalized VARCHAR(320)
GENERATED ALWAYS AS (LOWER(TRIM(email))) STORED;

CREATE INDEX ix_customer_email_normalized
ON customer (email_normalized);
```

Tên cột được khai báo trong schema, giúp truy vấn và mã ứng dụng dễ đọc hơn. Đổi lại, cột `STORED` thường cần thêm dung lượng để lưu giá trị và hệ quản trị phải cập nhật nó khi dữ liệu nguồn thay đổi.

### Cột tính toán do ứng dụng quản lý

Một phương án khác là ứng dụng ghi đồng thời giá trị gốc và giá trị đã chuẩn hóa vào hai cột, rồi tạo index trên cột chuẩn hóa. Cách này có thể dùng ở nhiều hệ quản trị, nhưng ứng dụng phải bảo đảm hai giá trị luôn nhất quán trong mọi luồng ghi, import, migration và cập nhật hàng loạt.

Nếu có thể, nên để cơ sở dữ liệu quản lý biểu thức bằng generated/computed column hoặc expression index. Nếu buộc phải duy trì ở ứng dụng, cần có ràng buộc hoặc quy trình kiểm tra để phát hiện dữ liệu lệch.

## 3. Bộ tối ưu nhận diện biểu thức như thế nào?

Có chỉ mục trên biểu thức không có nghĩa mọi truy vấn liên quan đều tự động dùng chỉ mục. Bộ tối ưu cần xác định biểu thức trong truy vấn tương thích với biểu thức được lập chỉ mục, kiểu dữ liệu và collation phù hợp, đồng thời ước lượng chi phí của đường truy cập đó thấp hơn các phương án khác.

Với chỉ mục trên `LOWER(TRIM(email))`, truy vấn sau có cấu trúc tương thích:

```sql
SELECT customer_id
FROM customer
WHERE LOWER(TRIM(email)) = LOWER(TRIM(?));
```

Nhưng truy vấn chỉ lọc `email = ?` đang tìm theo giá trị gốc. Hệ quản trị không thể mặc nhiên coi điều kiện đó tương đương với điều kiện đã chuẩn hóa.

Các yếu tố cần kiểm tra:

- **Cấu trúc biểu thức:** thứ tự hàm, kiểu ép, toán tử và cách xử lý `NULL` có khớp không?
- **Kiểu dữ liệu:** tham số có cùng kiểu hoặc có chuyển kiểu làm thay đổi biểu thức không?
- **Collation:** phép so sánh có cùng quy tắc phân biệt hoa thường, dấu và ký tự không?
- **Hàm và phiên bản:** hệ quản trị có hỗ trợ lập chỉ mục trên hàm đó và có đủ điều kiện xác định không?
- **Độ chọn lọc:** biểu thức có lọc đủ ít hàng để dùng index có lợi hơn scan không?
- **Thống kê:** hệ quản trị có thống kê phù hợp cho giá trị biểu thức hoặc cột sinh không?

Một chỉ mục vẫn có thể không được chọn khi bảng nhỏ, điều kiện trả về phần lớn dữ liệu hoặc chi phí đọc chỉ mục cộng với lookup cao hơn quét. Hãy dùng `EXPLAIN`, actual execution plan hoặc công cụ tương đương để xác nhận.

## 4. Yêu cầu về tính xác định của biểu thức

Chỉ mục lưu kết quả của biểu thức tại một thời điểm. Để kết quả đó tiếp tục đúng khi tìm kiếm, hệ quản trị cần bảo đảm hàm có hành vi phù hợp với việc lưu và tái sử dụng giá trị.

### Hàm xác định và không xác định

Hàm xác định (*deterministic*) trả cùng kết quả khi đầu vào và các điều kiện liên quan không đổi. Ví dụ, `LOWER(email)` thường có tính xác định trong một môi trường collation cố định. Ngược lại, `CURRENT_TIMESTAMP`, hàm sinh số ngẫu nhiên hoặc hàm phụ thuộc trạng thái bên ngoài có thể trả kết quả khác nhau dù các cột của hàng không đổi.

Một biểu thức chứa thời điểm hiện tại không phù hợp để lập chỉ mục như một giá trị cố định cho mọi hàng, bởi kết quả sẽ thay đổi theo thời gian mà không có thao tác cập nhật hàng. Hàm phụ thuộc cấu hình phiên, múi giờ, locale, bảng quy tắc bên ngoài hoặc dữ liệu không được hệ quản trị theo dõi cũng cần được xem xét cẩn thận.

### Hành vi theo hệ quản trị

- PostgreSQL yêu cầu các hàm và toán tử trong expression index đáp ứng mức bất biến (`IMMUTABLE`) theo quy tắc của hệ thống. Khai báo một hàm là immutable là cam kết của người viết hàm; không được dùng nhãn này để che giấu phụ thuộc vào thời gian hoặc trạng thái bên ngoài.
- Oracle yêu cầu biểu thức function-based index tuân thủ các giới hạn của hệ thống. Hàm do người dùng định nghĩa thường cần được khai báo `DETERMINISTIC` khi phù hợp; từ khóa này là cam kết về hành vi, không tự biến một hàm phụ thuộc trạng thái thành hàm xác định.
- SQL Server chỉ cho phép lập chỉ mục trên computed column đáp ứng các điều kiện về tính xác định, độ chính xác và các thiết lập phiên liên quan. Một số biểu thức hoặc kiểu dữ liệu không đủ điều kiện để làm khóa chỉ mục.
- MySQL áp dụng giới hạn về hàm và biểu thức cho functional index hoặc generated column. Biểu thức không được phép có thể bị từ chối khi tạo cột/chỉ mục; điều kiện chính xác phụ thuộc phiên bản.

Không nên tự đánh dấu hàm tùy chỉnh là immutable hoặc deterministic nếu kết quả phụ thuộc cấu hình có thể thay đổi. Nếu quy tắc chuẩn hóa thay đổi theo thời gian, cần có kế hoạch rebuild hoặc cập nhật dữ liệu và chỉ mục tương ứng.

## 5. PostgreSQL: expression index và generated column

PostgreSQL hỗ trợ expression index trực tiếp. Ví dụ tạo chỉ mục để tìm email đã chuyển chữ thường và bỏ khoảng trắng đầu/cuối:

```sql
CREATE INDEX ix_customer_email_normalized
ON customer (LOWER(BTRIM(email)));
```

Truy vấn cần dùng biểu thức tương thích:

```sql
SELECT customer_id, display_name
FROM customer
WHERE LOWER(BTRIM(email)) = LOWER(BTRIM($1));
```

Nếu quy tắc nghiệp vụ yêu cầu email duy nhất sau chuẩn hóa, có thể tạo unique expression index:

```sql
CREATE UNIQUE INDEX ux_customer_email_normalized
ON customer (LOWER(BTRIM(email)));
```

Lệnh unique có thể thất bại nếu dữ liệu hiện tại chứa các giá trị trở thành trùng sau khi chuẩn hóa. Cần phát hiện và xử lý dữ liệu trước khi tạo.

PostgreSQL cũng hỗ trợ generated column ở các phiên bản có tính năng tương ứng. Cột sinh lưu biểu thức theo quy tắc của phiên bản; sau đó có thể tạo index thông thường trên cột đó:

```sql
ALTER TABLE customer
ADD COLUMN email_normalized text
GENERATED ALWAYS AS (LOWER(BTRIM(email))) STORED;

CREATE INDEX ix_customer_email_normalized_column
ON customer (email_normalized);
```

Expression index thường gọn khi chỉ cần truy cập theo biểu thức. Generated column hữu ích khi nhiều truy vấn, báo cáo hoặc ràng buộc cần tham chiếu cùng giá trị đã tính. Hãy kiểm tra giới hạn phiên bản, tính bất biến của biểu thức và chi phí cập nhật bảng khi thêm cột sinh.

## 6. Oracle Database: function-based index và virtual column

Oracle hỗ trợ function-based index để lập chỉ mục trực tiếp trên biểu thức:

```sql
CREATE INDEX ix_customer_email_normalized
ON customer (LOWER(TRIM(email)));
```

Truy vấn dùng biểu thức tương ứng:

```sql
SELECT customer_id, display_name
FROM customer
WHERE LOWER(TRIM(email)) = LOWER(TRIM(:email));
```

Nếu cần bảo đảm duy nhất sau chuẩn hóa, có thể tạo unique function-based index:

```sql
CREATE UNIQUE INDEX ux_customer_email_normalized
ON customer (LOWER(TRIM(email)));
```

Oracle cũng hỗ trợ virtual column, tức cột được định nghĩa bằng biểu thức và được tính theo cơ chế của hệ quản trị. Có thể lập chỉ mục trên virtual column:

```sql
ALTER TABLE customer ADD (
    email_normalized GENERATED ALWAYS AS (LOWER(TRIM(email))) VIRTUAL
);

CREATE INDEX ix_customer_email_normalized_column
ON customer (email_normalized);
```

Function-based index phù hợp khi mục tiêu chủ yếu là tăng tốc truy vấn theo biểu thức. Virtual column phù hợp khi muốn đặt tên cho biểu thức, dùng lại trong nhiều truy vấn hoặc gắn các quy tắc schema. Với hàm do người dùng định nghĩa, cần xem xét yêu cầu `DETERMINISTIC`, quyền thực thi và khả năng thay đổi logic hàm; thay đổi hàm không tự động bảo đảm mọi khóa chỉ mục cũ phản ánh logic mới.

## 7. SQL Server: computed column và index

SQL Server sử dụng computed column thay vì cú pháp expression index trực tiếp theo cách của PostgreSQL. Có thể khai báo cột tính toán từ các cột khác rồi tạo index trên cột đó:

```sql
ALTER TABLE dbo.Customer
ADD email_normalized AS LOWER(LTRIM(RTRIM(email))) PERSISTED;

CREATE INDEX ix_customer_email_normalized
ON dbo.Customer (email_normalized);
```

`PERSISTED` yêu cầu lưu giá trị tính toán trong hàng. Với computed column đủ điều kiện, một số trường hợp có thể tạo index mà không cần `PERSISTED`; cần kiểm tra yêu cầu cụ thể của biểu thức và phiên bản.

Để lập chỉ mục computed column, SQL Server kiểm tra tính xác định, độ chính xác, kiểu dữ liệu và các thiết lập `SET` bắt buộc tại thời điểm tạo index và khi kết nối thực thi truy vấn. Nếu các điều kiện này không phù hợp, hệ quản trị có thể từ chối tạo index hoặc không sử dụng index như mong đợi.

Truy vấn có thể tham chiếu cột tính toán:

```sql
SELECT customer_id, display_name
FROM dbo.Customer
WHERE email_normalized = LOWER(LTRIM(RTRIM(@email)));
```

Việc tham chiếu trực tiếp `email_normalized` làm ý định rõ ràng và tránh phụ thuộc vào việc bộ tối ưu có nhận diện một biểu thức viết lại hay không. Cần thống nhất quy tắc chuẩn hóa giữa computed column và giá trị tham số.

## 8. MySQL: functional index và generated column

MySQL hỗ trợ functional key parts từ các phiên bản 8.0.13 trở lên. Cú pháp lập chỉ mục trên biểu thức sử dụng cặp ngoặc cho biểu thức:

```sql
CREATE INDEX ix_customer_email_normalized
ON customer ((LOWER(TRIM(email))));
```

Truy vấn cần sử dụng biểu thức tương thích:

```sql
SELECT customer_id, display_name
FROM customer
WHERE LOWER(TRIM(email)) = LOWER(TRIM(?));
```

MySQL cũng hỗ trợ generated column `VIRTUAL` hoặc `STORED` theo quy tắc của phiên bản và storage engine. Có thể tạo index trên generated column:

```sql
ALTER TABLE customer
ADD COLUMN email_normalized VARCHAR(320)
GENERATED ALWAYS AS (LOWER(TRIM(email))) STORED,
ADD INDEX ix_customer_email_normalized (email_normalized);
```

Generated column có tên riêng, thuận tiện khi biểu thức được dùng nhiều nơi. `STORED` lưu giá trị tính toán trong hàng; `VIRTUAL` thường tính khi đọc, nhưng nếu được lập chỉ mục thì giá trị cần thiết vẫn được duy trì trong cấu trúc index. Functional index của MySQL được triển khai dựa trên cơ chế cột sinh ẩn, nên chịu các giới hạn tương ứng về kiểu dữ liệu và biểu thức.

Hãy kiểm tra phiên bản MySQL, giới hạn độ dài khóa, collation, kiểu trả về của biểu thức và hỗ trợ của storage engine. Một số biểu thức cần ép kiểu tường minh để tránh kiểu kết quả không phù hợp với khóa chỉ mục.

## 9. Chọn giữa expression index và generated column

Hai cách tiếp cận có mục tiêu chung nhưng trải nghiệm schema và chi phí khác nhau:

| Tiêu chí | Chỉ mục biểu thức/hàm | Generated/computed column có index |
|---|---|---|
| Schema | Không cần thêm cột hiển thị trong mô hình dữ liệu | Thêm tên cột tính toán vào schema |
| Truy vấn | Thường phải viết biểu thức tương thích để bộ tối ưu nhận diện | Có thể truy vấn trực tiếp bằng tên cột đã tính |
| Tái sử dụng | Tốt khi một vài truy vấn cần cùng biểu thức | Tốt khi nhiều truy vấn, báo cáo hoặc constraint cùng dùng giá trị |
| Dung lượng hàng | Không nhất thiết lưu thêm cột trong hàng; index vẫn chiếm dung lượng | `STORED` làm tăng dung lượng hàng; `VIRTUAL` có cách lưu riêng theo hệ quản trị |
| Chi phí ghi | Cập nhật biểu thức và khóa chỉ mục khi dữ liệu nguồn thay đổi | Tính/cập nhật cột sinh và chỉ mục tương ứng |
| Khả năng tương thích | Phụ thuộc hỗ trợ expression/function index | Phụ thuộc hỗ trợ generated/computed column và index |
| Bảo trì logic | Biểu thức nằm trong định nghĩa index | Biểu thức được đặt tên trong schema, dễ tham chiếu hơn |

Có thể chọn expression index khi chỉ cần một đường truy cập chuyên biệt và hệ quản trị hỗ trợ trực tiếp. Chọn generated/computed column khi giá trị đã tính là một khái niệm có ý nghĩa trong mô hình, được nhiều câu truy vấn sử dụng hoặc cần hiển thị trong schema.

Nếu biểu thức phức tạp, được dùng ở nhiều nơi hoặc cần kiểm thử riêng, cột sinh thường giúp chuẩn hóa cách sử dụng. Tuy nhiên, thêm cột không tự động làm truy vấn nhanh; cần index đúng cột và kiểm tra kế hoạch.

## 10. Thiết kế biểu thức an toàn và ổn định

### Chuẩn hóa văn bản

Với email, username hoặc mã tìm kiếm, cần xác định chính xác quy tắc chuẩn hóa. `LOWER` không giải quyết mọi khác biệt Unicode, dấu hoặc quy tắc ngôn ngữ. `TRIM` mặc định cũng có thể chỉ xử lý một nhóm ký tự khoảng trắng theo nền tảng. Nếu ứng dụng và cơ sở dữ liệu dùng hai thuật toán khác nhau, có thể phát sinh trường hợp hai giá trị được xem là giống nhau ở ứng dụng nhưng khác nhau ở chỉ mục, hoặc ngược lại.

Hãy định nghĩa một quy tắc duy nhất, kiểm thử với dữ liệu Unicode, ký tự có dấu, khoảng trắng, chuỗi rỗng và `NULL`. Nếu quy tắc nghiệp vụ thay đổi, cần kế hoạch cập nhật dữ liệu và xây lại chỉ mục.

### Tính toán ngày và thời gian

Truy vấn sau có thể áp dụng hàm lên cột timestamp:

```sql
SELECT COUNT(*)
FROM orders
WHERE CAST(created_at AS DATE) = ?;
```

Một cách thường dễ khai thác chỉ mục B-tree trên `created_at` hơn là chuyển điều kiện thành khoảng thời gian:

```sql
SELECT COUNT(*)
FROM orders
WHERE created_at >= ?
  AND created_at < ?;
```

Hai tham số biểu diễn đầu ngày và đầu ngày kế tiếp theo múi giờ nghiệp vụ đã thống nhất. Cách viết range predicate thường tránh phải lập chỉ mục trên biểu thức ngày và có thể hỗ trợ cả các truy vấn lọc khoảng thời gian khác. Nếu workload thực sự truy vấn thường xuyên theo một biểu thức ngày cố định, expression index hoặc cột sinh vẫn có thể là lựa chọn phù hợp.

Đặc biệt chú ý múi giờ, kiểu `timestamp with time zone`/`without time zone` và quy tắc chuyển ngày. Không tạo index trên biểu thức phụ thuộc múi giờ phiên nếu kết quả có thể thay đổi theo kết nối mà không được phản ánh trong dữ liệu chỉ mục.

### Tránh biểu thức không cần thiết

Trước khi tạo index chuyên biệt, hãy xem có thể viết lại truy vấn để dùng chỉ mục hiện có hay không. Ví dụ, thay `DATE(created_at) = ...` bằng khoảng `[start, next_start)` có thể vừa dễ hiểu vừa tận dụng index gốc. Expression index nên được dùng khi biểu thức là nhu cầu truy cập ổn định, có tần suất đủ lớn và mang lại lợi ích đo được.

## 11. Thống kê, chi phí ghi và bảo trì

Chỉ mục trên biểu thức cũng cần thống kê để bộ tối ưu ước lượng số hàng. Nếu biểu thức tạo ra phân bố lệch, thống kê trên cột gốc có thể không mô tả đầy đủ phân bố của kết quả đã tính. Tùy hệ quản trị, thống kê có thể được tạo cho expression index, generated column hoặc computed column.

Khi thêm index chuyên biệt, hãy đánh giá:

- **Chi phí tạo:** đọc dữ liệu, tính biểu thức, sắp xếp khóa, I/O và thời gian khóa hoặc đồng bộ.
- **Chi phí ghi:** mỗi `INSERT`, `UPDATE` hoặc `DELETE` liên quan có thể phải tính lại giá trị và cập nhật index.
- **Dung lượng:** kích thước khóa biểu thức, số hàng, mức trùng lặp và cấu trúc chỉ mục.
- **Bộ nhớ đệm:** index lớn hơn chiếm buffer cache, có thể đẩy dữ liệu khác ra khỏi cache.
- **Thống kê:** độ chọn lọc, số giá trị phân biệt, histogram và độ mới của thống kê.
- **Tác động truy vấn khác:** một index mới có thể giúp truy vấn này nhưng làm tăng chi phí ghi hoặc thay đổi lựa chọn kế hoạch của truy vấn khác.

Nếu biểu thức tạo ra chuỗi dài hoặc giá trị có cardinality cao, khóa chỉ mục có thể lớn. Hãy cân nhắc giới hạn độ dài, kiểu dữ liệu và nhu cầu tìm kiếm chính xác. Không lập chỉ mục trên mọi biểu thức chỉ vì có thể làm được.

### Unique expression index

Chỉ mục biểu thức có thể đồng thời bảo đảm tính duy nhất sau chuẩn hóa. Ví dụ, một email không được trùng sau khi chuyển chữ thường:

```sql
CREATE UNIQUE INDEX ux_customer_email_lower
ON customer (LOWER(email));
```

Khả năng tạo và cú pháp phụ thuộc hệ quản trị. Trước khi tạo, hãy kiểm tra dữ liệu trùng theo chính biểu thức đó:

```sql
SELECT LOWER(email) AS normalized_email, COUNT(*) AS total
FROM customer
WHERE email IS NOT NULL
GROUP BY LOWER(email)
HAVING COUNT(*) > 1;
```

Nếu biểu thức chuẩn hóa thay đổi hoặc collation khác nhau giữa môi trường, kết quả duy nhất có thể thay đổi. Hãy xác định quy tắc so sánh và xử lý dữ liệu cũ trước khi triển khai.

## 12. Quy trình kiểm chứng chỉ mục biểu thức

Một quy trình có thể lặp lại:

1. **Xác định truy vấn mục tiêu:** lấy query fingerprint, tần suất, độ trễ và số hàng trả về.
2. **Xem kế hoạch hiện tại:** xác định scan, filter, số hàng ước lượng/thực tế, logical reads và CPU.
3. **Xác định biểu thức chính xác:** ghi lại hàm, kiểu dữ liệu, collation, null semantics và tham số.
4. **Kiểm tra khả năng hệ quản trị:** expression index, function-based index, generated/computed column và yêu cầu deterministic/immutable.
5. **Kiểm tra dữ liệu:** giá trị null, trùng sau chuẩn hóa, độ dài khóa và các trường hợp Unicode/biên.
6. **Tạo thử chỉ mục:** dùng môi trường kiểm thử hoặc quy trình DDL phù hợp; đo thời gian, I/O, CPU và khóa.
7. **Chạy lại truy vấn:** xác nhận actual plan có dùng index và cardinality estimate có hợp lý.
8. **Đo workload tổng thể:** so sánh p95/p99, throughput đọc/ghi, CPU, I/O và dung lượng.
9. **Triển khai có giám sát:** theo dõi lỗi ghi, lock wait, thay đổi kế hoạch và tác động lên các truy vấn khác.
10. **Đánh giá định kỳ:** khi biểu thức, collation, dữ liệu hoặc phiên bản hệ quản trị thay đổi, kiểm tra lại tính đúng và hiệu quả của index.

Các chỉ số nên ghi nhận trước và sau:

| Nhóm | Chỉ số |
|---|---|
| Truy vấn | p50, p95, p99, elapsed time, rows returned |
| Kế hoạch | Index seek/scan, estimated rows, actual rows, filter và lookup |
| Đọc dữ liệu | Logical reads, physical reads, buffer/cache hit |
| Ghi dữ liệu | Insert/update throughput, commit latency, thời gian cập nhật index |
| Tài nguyên | CPU, I/O, bộ nhớ, dung lượng index và transaction log |

Nếu truy vấn vẫn không dùng index, hãy kiểm tra biểu thức có tương thích hay không, tham số có bị ép kiểu, collation có khác, thống kê có mới và chi phí ước lượng có khiến scan được đánh giá rẻ hơn không. Không nên ép kế hoạch ngay khi chưa xác định nguyên nhân.

## 13. Những sai lầm thường gặp

1. **Tạo index trên biểu thức nhưng truy vấn dùng biểu thức khác:** bộ tối ưu có thể không nhận diện được tính tương đương.
2. **Dùng hàm không xác định:** giá trị index có thể không còn đúng khi thời gian hoặc trạng thái bên ngoài thay đổi.
3. **Chuẩn hóa khác nhau giữa ứng dụng và database:** gây lỗi tìm kiếm hoặc vi phạm uniqueness.
4. **Bỏ qua collation và Unicode:** hai chuỗi có thể được so sánh khác nhau giữa môi trường.
5. **Tạo generated column nhưng không tạo index:** truy vấn vẫn có thể phải quét dữ liệu.
6. **Dùng cột `STORED` cho mọi trường hợp:** tăng dung lượng và chi phí cập nhật mà không có lợi ích tương ứng.
7. **Tạo index trên biểu thức ngày trong khi range predicate đủ dùng:** làm tăng cấu trúc cần bảo trì không cần thiết.
8. **Không cập nhật hoặc kiểm tra thống kê:** bộ tối ưu có thể ước lượng sai và chọn scan.
9. **Không đo chi phí ghi:** truy vấn đọc nhanh hơn nhưng workload ghi có thể giảm throughput.
10. **Giả định cú pháp và tính năng giống nhau giữa các hệ quản trị:** khả năng và giới hạn phụ thuộc nền tảng, phiên bản và storage engine.

## 14. Danh sách kiểm tra trước khi triển khai

- [ ] Đã xác định truy vấn thường xuyên áp dụng hàm hoặc biểu thức lên cột.
- [ ] Đã kiểm tra có thể viết lại điều kiện để dùng chỉ mục hiện có hay không.
- [ ] Đã chọn expression/function-based index hay generated/computed column theo nhu cầu.
- [ ] Đã xác nhận biểu thức đáp ứng yêu cầu immutable/deterministic của hệ quản trị.
- [ ] Đã thống nhất kiểu dữ liệu, collation, Unicode, `NULL` và quy tắc chuẩn hóa.
- [ ] Đã kiểm tra dữ liệu trùng sau biểu thức nếu dùng unique index.
- [ ] Đã xác nhận truy vấn dùng biểu thức tương thích và kiểu tham số phù hợp.
- [ ] Đã cập nhật hoặc kiểm tra thống kê của biểu thức/cột sinh.
- [ ] Đã đo chi phí tạo index, dung lượng và tác động lên workload ghi.
- [ ] Đã xác minh actual execution plan, độ trễ và throughput sau điều chỉnh.
- [ ] Đã kiểm tra lại khi nâng cấp phiên bản hoặc thay đổi logic hàm.

Chỉ mục biểu thức, chỉ mục hàm và cột sinh giúp cơ sở dữ liệu truy cập hiệu quả theo giá trị đã tính, chẳng hạn email chuẩn hóa hoặc biểu thức nghiệp vụ. Expression index phù hợp khi truy vấn cần một đường truy cập theo biểu thức; generated/computed column phù hợp khi giá trị tính toán được dùng rộng rãi và cần tên gọi trong schema. Mỗi hệ quản trị có yêu cầu riêng về tính xác định, kiểu dữ liệu và cách nhận diện biểu thức. Hãy chọn giải pháp theo workload, kiểm tra execution plan và đo cả lợi ích đọc lẫn chi phí ghi để bảo đảm chỉ mục chuyên biệt cải thiện hiệu năng ổn định.
