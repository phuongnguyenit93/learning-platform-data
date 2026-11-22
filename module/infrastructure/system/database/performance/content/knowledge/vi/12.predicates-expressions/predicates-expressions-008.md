# Quy tắc đối chiếu chuỗi (collation), phân biệt hoa thường và chi phí so sánh

Trong chương **Điều kiện và biểu thức** của module **DATABASE_PERFORMANCE**, cách cơ sở dữ liệu so sánh chuỗi ảnh hưởng trực tiếp đến kết quả truy vấn, thứ tự sắp xếp, tính duy nhất và khả năng sử dụng chỉ mục. Đây là một phần của phương pháp tối ưu hiệu năng dựa trên đo tải, kế hoạch thực thi, thống kê và cơ chế truy cập dữ liệu: quy tắc so sánh có thể làm thay đổi số dòng được chọn, chi phí CPU, đường truy cập chỉ mục và thời gian thực thi. Quy tắc này được xác định bởi *collation* (quy tắc đối chiếu), có thể quy định cách xử lý chữ hoa/chữ thường, dấu, ký tự theo ngôn ngữ, ký tự Unicode và một số khác biệt về khoảng trắng.

Hai chuỗi nhìn giống nhau với người dùng chưa chắc được xem là bằng nhau theo byte; ngược lại, hai chuỗi có cách viết khác nhau có thể được collation xem là tương đương. Lựa chọn collation vì vậy vừa là quyết định về ngữ nghĩa dữ liệu, vừa là quyết định hiệu năng. Một điều kiện so sánh dùng collation không phù hợp với chỉ mục có thể khiến hệ quản trị phải chuyển đổi hoặc so sánh nhiều dòng hơn dự kiến. Một collation không phân biệt hoa thường có thể làm thay đổi kết quả tìm kiếm và ràng buộc UNIQUE.

## 1. Collation là gì?

Collation là tập quy tắc xác định cách so sánh và sắp xếp các giá trị văn bản. Nó thường trả lời những câu hỏi sau:

- `An` và `an` có được xem là bằng nhau không?
- `a` và `á` có được xem là bằng nhau không?
- `o` và `ö` được sắp xếp ở vị trí nào theo ngôn ngữ đang dùng?
- Hai chuỗi có dấu Unicode được mã hóa theo dạng dựng sẵn hay dạng ký tự kết hợp có được xem là tương đương không?
- Khoảng trắng ở cuối chuỗi có ảnh hưởng đến phép so sánh không?
- Thứ tự sắp xếp có tuân theo quy tắc ngôn ngữ hay so sánh theo mã ký tự/byte?

Collation có thể được thiết lập ở cấp server, database, schema, bảng, cột hoặc ngay trong biểu thức truy vấn, tùy hệ quản trị. Giá trị mặc định ở cấp cao hơn thường được kế thừa khi tạo đối tượng mới, nhưng thay đổi mặc định database không nhất thiết tự động đổi collation của các cột đã tồn tại.

### 1.1. Phân biệt hoa thường

Collation phân biệt hoa thường (*case-sensitive*, thường ký hiệu `CS`) xem chữ hoa và chữ thường là khác nhau. Collation không phân biệt hoa thường (*case-insensitive*, thường ký hiệu `CI`) có thể xem chúng là tương đương khi so sánh.

Ví dụ với dữ liệu:

| Giá trị lưu | Tìm kiếm | Collation phân biệt hoa thường | Collation không phân biệt hoa thường |
|---|---|---|---|
| `Database` | `database` | Không khớp | Có thể khớp |
| `ADMIN` | `admin` | Không khớp | Có thể khớp |
| `Nguyen` | `NGUYEN` | Không khớp | Có thể khớp |

Kết quả chính xác còn phụ thuộc quy tắc Unicode và ngôn ngữ của collation. Không nên mặc định mọi phép chuyển chữ hoa/chữ thường đều giống nhau trong tất cả ngôn ngữ.

### 1.2. Phân biệt dấu

Collation phân biệt dấu (*accent-sensitive*, thường ký hiệu `AS`) xem các ký tự có dấu là khác ký tự cơ sở. Collation không phân biệt dấu (*accent-insensitive*, thường ký hiệu `AI`) có thể xem chúng là tương đương trong so sánh.

| Giá trị lưu | Tìm kiếm | Phân biệt dấu | Không phân biệt dấu |
|---|---|---|---|
| `cafe` | `café` | Không khớp | Có thể khớp |
| `a` | `á` | Không khớp | Có thể khớp |
| `hoa` | `hòa` | Không khớp | Có thể khớp |

Trong tiếng Việt, dấu thanh và dấu phụ có ý nghĩa phân biệt từ. Vì vậy, chọn collation không phân biệt dấu cho mọi cột văn bản có thể tạo ra kết quả tìm kiếm quá rộng hoặc làm hai tên khác nhau bị xem là một. Hãy xác định quy tắc nghiệp vụ cho từng loại dữ liệu, chẳng hạn tên hiển thị, mã định danh, email, mã sản phẩm hoặc nội dung tìm kiếm.

### 1.3. Collation ngôn ngữ và so sánh nhị phân

Collation theo ngôn ngữ (*linguistic collation*) áp dụng quy tắc sắp xếp và so sánh theo một locale. Quy tắc này có thể xử lý chữ ghép, ký tự có dấu, thứ tự chữ cái và một số quy tắc đặc thù của ngôn ngữ.

So sánh nhị phân (*binary comparison*) dựa trên biểu diễn mã ký tự hoặc byte theo quy tắc của hệ quản trị. Cách này thường có tính xác định và ít phụ thuộc ngôn ngữ, nhưng thứ tự thu được có thể không phù hợp với cách người dùng mong đợi khi sắp xếp tên.

Không nên đồng nhất collation nhị phân với kiểu dữ liệu binary. Ví dụ, collation có hậu tố `_bin` của MySQL vẫn là collation dành cho chuỗi; còn `BINARY`/`VARBINARY` là kiểu dữ liệu lưu byte. Hai khái niệm có semantics và cách sử dụng chỉ mục khác nhau.

## 2. Collation ảnh hưởng tới những phép toán nào?

Collation không chỉ tác động tới điều kiện `=`. Nó có thể ảnh hưởng đến:

- So sánh bằng và khác (`=`, `<>`, `IN`).
- So sánh thứ tự (`<`, `>`, `BETWEEN`) và điều kiện range.
- Sắp xếp (`ORDER BY`) và nhóm (`GROUP BY`).
- Ràng buộc duy nhất (`UNIQUE`) và khóa có chứa cột văn bản.
- Tìm kiếm mẫu (`LIKE`, `ILIKE`) và các phép tìm kiếm văn bản tùy hệ quản trị.
- Kết quả join giữa các cột chuỗi có collation khác nhau.

Ví dụ, nếu collation không phân biệt hoa thường, `GROUP BY username` có thể gom `Alice`, `ALICE` và `alice` vào cùng nhóm. Một unique index trên cột đó cũng có thể từ chối bản ghi mới có giá trị chỉ khác chữ hoa/chữ thường. Đây là thay đổi về ngữ nghĩa, không chỉ là tối ưu hiệu năng.

Với điều kiện range, thứ tự collation quyết định ranh giới so sánh. Nếu ứng dụng giả định thứ tự byte nhưng cột dùng collation ngôn ngữ, kết quả `ORDER BY` hoặc phân trang theo chuỗi có thể khác dự kiến. Khi dùng phân trang keyset, giá trị cursor phải được so sánh theo cùng collation và thứ tự sắp xếp của truy vấn.

## 3. Vì sao collation ảnh hưởng tới chỉ mục và hiệu năng?

Chỉ mục B-tree sắp xếp khóa theo một quy tắc nhất định. Với khóa văn bản, quy tắc sắp xếp đó phải phù hợp với phép so sánh mà truy vấn yêu cầu. Nếu truy vấn dùng collation khác với collation của chỉ mục, optimizer có thể không dùng được đường seek/range mong muốn hoặc phải thực hiện chuyển đổi bổ sung.

### 3.1. Chỉ mục được xây dựng theo quy tắc so sánh

Khi tạo chỉ mục trên cột `name`, thứ tự các khóa trong B-tree được xác định theo collation của cột hoặc biểu thức chỉ mục. Nếu truy vấn tìm theo đúng quy tắc đó, hệ quản trị có thể tìm một vùng khóa liên tiếp thay vì so sánh mọi dòng.

Ví dụ về ý tưởng:

```sql
CREATE INDEX ix_customer_name
ON customers (name);

SELECT customer_id, name
FROM customers
WHERE name = 'Nguyen An';
```

Nếu collation của `name` phù hợp với ngữ nghĩa so sánh trong truy vấn, chỉ mục có thể hỗ trợ phép tìm kiếm. Tuy nhiên, việc có chỉ mục không bảo đảm optimizer sẽ chọn nó; độ chọn lọc, số dòng cần trả về, thống kê và chi phí lookup vẫn quyết định kế hoạch.

### 3.2. Chuyển đổi collation trong điều kiện lọc

Một truy vấn có thể áp dụng `COLLATE`, `LOWER`, `UPPER` hoặc hàm chuẩn hóa lên cột. Nếu biểu thức truy vấn khác với biểu thức được đánh chỉ mục, hệ quản trị có thể phải tính giá trị cho nhiều dòng rồi mới so sánh. Khi đó, chỉ mục B-tree thông thường trên cột gốc có thể không hỗ trợ phép tìm kiếm hiệu quả.

Ví dụ tổng quát:

```sql
SELECT customer_id, name
FROM customers
WHERE LOWER(name) = LOWER(:search_name);
```

Nếu không có chỉ mục phù hợp với biểu thức `LOWER(name)`, hệ quản trị có thể phải áp dụng hàm lên nhiều giá trị. Cách xử lý cụ thể phụ thuộc optimizer; hãy kiểm tra execution plan và logical reads thay vì suy đoán từ cú pháp.

Các hướng xử lý thường gặp:

1. Chọn collation của cột ngay từ đầu để phép so sánh thông dụng dùng đúng semantics.
2. Tạo functional index hoặc expression index trên biểu thức chuẩn hóa nếu hệ quản trị hỗ trợ.
3. Dùng computed/generated column đã chuẩn hóa và tạo chỉ mục trên cột đó.
4. Nếu có nhiều quy tắc tìm kiếm, cân nhắc lưu khóa tìm kiếm chuẩn hóa riêng, đồng thời giữ nguyên giá trị hiển thị.

### 3.3. Chi phí CPU của so sánh ngôn ngữ

So sánh nhị phân đơn giản thường ít công việc hơn việc áp dụng quy tắc ngôn ngữ phức tạp. Collation có thể cần xử lý trọng số ký tự, quy tắc chữ ghép, dấu, locale hoặc chuỗi Unicode. Chi phí này có thể xuất hiện trong lọc, sort, group, join và xây dựng chỉ mục.

Trong truy vấn chỉ so sánh vài giá trị, khác biệt CPU thường không đáng kể. Trong truy vấn quét hàng triệu dòng hoặc sort lượng lớn văn bản, chi phí so sánh có thể trở nên đáng kể. Nén, cache, số dòng, độ dài chuỗi và khả năng xử lý của engine cũng ảnh hưởng kết quả. Cần benchmark với dữ liệu và truy vấn thực tế.

### 3.4. Kích thước và chi phí duy trì chỉ mục

Một số collation hoặc biểu diễn khóa có thể tạo trọng số so sánh khác với chuỗi gốc. Chỉ mục văn bản có thể cần lưu thêm thông tin để duy trì thứ tự theo collation. Kích thước khóa, độ dài chuỗi, encoding và cấu trúc nội bộ ảnh hưởng số trang chỉ mục, độ sâu cây và cache.

Khi thay đổi collation của cột hoặc biểu thức, chỉ mục liên quan có thể cần được xây dựng lại. Thay đổi collation cũng có thể làm thay đổi thứ tự khóa và semantics của unique constraint. Hãy tính thời gian rebuild, dung lượng tạm, log, khóa và thời gian ảnh hưởng dịch vụ trước khi triển khai.

## 4. Chọn collation theo mục đích dữ liệu

Không nên áp dụng một quy tắc không phân biệt hoa thường và dấu cho mọi cột. Hãy phân loại dữ liệu theo ngữ nghĩa:

| Loại dữ liệu | Quy tắc cần cân nhắc | Lý do |
|---|---|---|
| Tên người, địa chỉ hiển thị | Collation theo ngôn ngữ; quyết định riêng về hoa thường và dấu khi tìm kiếm | Cần thứ tự và cách tìm gần với kỳ vọng người dùng |
| Username hoặc mã đăng nhập | Quy tắc nhất quán, rõ ràng về hoa thường; cần xem chính sách định danh | Tránh hai tài khoản khác nhau bị nhập nhằng hoặc trùng theo collation |
| Mã sản phẩm, mã giao dịch | Có thể cần so sánh chính xác hoặc quy tắc chuẩn hóa riêng | Mã thường có semantics định danh, không phải văn bản tự nhiên |
| Email | Chuẩn hóa theo chính sách ứng dụng và quy tắc của hệ thống xác thực | Không nên tự suy diễn mọi phần địa chỉ đều không phân biệt hoa thường theo cùng cách |
| Nội dung tìm kiếm | Có thể cần tìm gần đúng, bỏ dấu hoặc không phân biệt hoa thường | Ưu tiên trải nghiệm tìm kiếm hơn định danh duy nhất |
| Token, hash, mã bí mật | So sánh chính xác theo byte/giá trị | Mọi thay đổi hoa thường hoặc ký tự đều có thể làm thay đổi định danh |

Đối với khóa định danh, nên xác định quy tắc chuẩn hóa ở tầng nghiệp vụ và áp dụng nhất quán khi ghi, đọc, kiểm tra trùng và xác thực. Collation chỉ là một phần của quy tắc; nó không thay thế quy trình chuẩn hóa Unicode, kiểm tra ký tự hợp lệ hoặc chính sách bảo mật.

## 5. Ví dụ theo hệ quản trị

Tên collation, cú pháp và khả năng sử dụng chỉ mục khác nhau theo sản phẩm và phiên bản. Các ví dụ dưới đây minh họa cách tiếp cận; hãy chọn collation có sẵn và đúng locale trong môi trường thực tế.

### 5.1. SQL Server

SQL Server thường biểu diễn đặc tính collation bằng hậu tố như:

- `_CI`: không phân biệt hoa thường.
- `_CS`: phân biệt hoa thường.
- `_AI`: không phân biệt dấu.
- `_AS`: phân biệt dấu.
- `_BIN2`: so sánh theo mã ký tự nhị phân với semantics nhị phân của SQL Server.

Có thể xem collation của database và cột bằng catalog view hoặc thuộc tính tương ứng. Ví dụ kiểm tra cột:

```sql
SELECT c.name AS column_name,
       c.collation_name
FROM sys.columns AS c
WHERE c.object_id = OBJECT_ID(N'dbo.Customers')
  AND c.name = N'name';
```

Một truy vấn có thể chỉ định collation tường minh:

```sql
SELECT customer_id, name
FROM dbo.Customers
WHERE name COLLATE Latin1_General_100_CI_AI_SC = N'Nguyen An';
```

Collation minh họa trên không phân biệt hoa thường và dấu theo quy tắc Latin General. Với dữ liệu tiếng Việt, cần chọn collation hỗ trợ locale phù hợp và kiểm thử thứ tự sắp xếp. Việc đặt `COLLATE` trực tiếp lên cột có thể làm thay đổi khả năng sử dụng chỉ mục hiện có nếu collation của index không khớp. Ưu tiên thiết kế collation cột/index phù hợp với truy vấn thường xuyên; chỉ dùng collation trong biểu thức khi cần một phép so sánh đặc biệt.

Nếu cần tìm kiếm theo khóa chuẩn hóa, có thể tạo computed column và đánh chỉ mục trên biểu thức phù hợp. Ví dụ dưới đây chỉ minh họa ý tưởng dùng cột tính toán; collation của cột và biểu thức phải được kiểm tra theo schema cụ thể:

```sql
ALTER TABLE dbo.Customers
ADD name_search AS UPPER(name) PERSISTED;

CREATE INDEX ix_customers_name_search
ON dbo.Customers (name_search);
```

Nếu collation cột đã không phân biệt hoa thường, `UPPER` có thể không đem lại lợi ích. Computed column cũng làm tăng yêu cầu lưu trữ hoặc chi phí tính toán tùy cách khai báo. Hãy xác nhận truy vấn dùng đúng biểu thức và collation tương ứng.

### 5.2. MySQL

MySQL gắn collation với character set. Tên collation thường có hậu tố như `_ci`, `_cs`, `_ai`, `_as` hoặc `_bin`. MySQL 8.0 có các collation Unicode mới, ví dụ `utf8mb4_0900_ai_ci`, không phân biệt dấu và hoa thường theo quy tắc Unicode tương ứng.

Có thể kiểm tra character set và collation:

```sql
SHOW FULL COLUMNS FROM customers;

SELECT @@character_set_connection,
       @@collation_connection,
       @@collation_database;
```

Ví dụ thay đổi collation của một cột:

```sql
ALTER TABLE customers
MODIFY name VARCHAR(200)
CHARACTER SET utf8mb4
COLLATE utf8mb4_0900_ai_ci;
```

Đây là ví dụ cho MySQL 8.0; cần giữ nguyên các thuộc tính khác của cột như `NULL`, `NOT NULL`, default và comment theo schema thật. Thay đổi có thể rebuild bảng hoặc chỉ mục, tiêu tốn I/O, log và thời gian khóa tùy phiên bản, thuật toán DDL và cấu trúc bảng. Trước khi thực hiện, hãy kiểm tra các giá trị trùng mới phát sinh theo collation đích, nhất là khi có unique index.

Truy vấn có thể chỉ định collation ở biểu thức:

```sql
SELECT customer_id, name
FROM customers
WHERE name COLLATE utf8mb4_0900_ai_ci = 'Nguyen An';
```

Nếu cột đã dùng collation này, không cần thêm `COLLATE` ở mỗi truy vấn. Khi collation của biểu thức khác với collation chỉ mục, khả năng dùng index có thể bị ảnh hưởng. Kiểm tra `EXPLAIN` và `EXPLAIN ANALYZE` khi phiên bản hỗ trợ.

MySQL còn có khác biệt về quy tắc khoảng trắng cuối chuỗi. Một số collation dùng `PAD SPACE`, trong khi nhiều collation UCA 9.0 có `NO PAD`. Vì vậy, so sánh `'abc'` và `'abc '` có thể khác nhau giữa các collation. Không được giả định hành vi khoảng trắng giống nhau khi đổi collation hoặc nâng cấp phiên bản.

### 5.3. PostgreSQL

PostgreSQL sử dụng collation để xác định quy tắc locale cho so sánh và sắp xếp văn bản. Collation có thể đến từ libc hoặc ICU, tùy cấu hình build và phiên bản. ICU cho phép khai báo quy tắc locale và strength để điều khiển mức phân biệt ký tự.

Ví dụ tạo một collation ICU không phân biệt hoa thường nhưng vẫn phân biệt dấu bằng strength level 2:

```sql
CREATE COLLATION app_name_ci (
    provider = icu,
    locale = 'und-u-ks-level2',
    deterministic = false
);
```

Sau đó có thể tạo index theo collation này:

```sql
CREATE INDEX ix_customers_name_ci
ON customers (name COLLATE app_name_ci);

SELECT customer_id, name
FROM customers
WHERE name COLLATE app_name_ci = 'Nguyen An';
```

Collation không xác định (*nondeterministic collation*) cho phép các chuỗi có thể khác biểu diễn nhưng được ICU xem là tương đương theo quy tắc đã chọn. Điều này có thể hỗ trợ so sánh không phân biệt hoa thường hoặc chuẩn hóa Unicode, nhưng cần hiểu rõ hệ quả với tính duy nhất và các toán tử được hỗ trợ. Một số phép pattern matching hoặc operator class có giới hạn với nondeterministic collation; hãy kiểm tra tài liệu đúng phiên bản PostgreSQL trước khi dùng `LIKE`, regex hoặc tạo chỉ mục chuyên biệt.

Một cách khác là tạo expression index:

```sql
CREATE INDEX ix_customers_name_lower
ON customers (lower(name));

SELECT customer_id, name
FROM customers
WHERE lower(name) = lower('Nguyen An');
```

Expression index chỉ hỗ trợ biểu thức tương ứng. Nếu truy vấn dùng collation hoặc cách chuẩn hóa khác, index này có thể không được sử dụng như mong muốn. `lower()` cũng không thay thế đầy đủ mọi quy tắc collation ngôn ngữ.

Với ICU, phiên bản dữ liệu locale có thể thay đổi sau nâng cấp hệ điều hành hoặc thư viện ICU. PostgreSQL lưu phiên bản collation đã biết; khi phát hiện phiên bản khác, cần đánh giá lại thứ tự và tính hợp lệ của chỉ mục, cập nhật metadata phiên bản theo hướng dẫn rồi rebuild các index bị ảnh hưởng nếu cần. Không bỏ qua cảnh báo collation version mismatch.

### 5.4. Oracle Database

Oracle hỗ trợ so sánh nhị phân và so sánh ngôn ngữ thông qua cấu hình NLS. Với một số phiên bản, có thể dùng `NLS_COMP` và `NLS_SORT` để điều khiển semantics so sánh trong session. Ví dụ:

```sql
ALTER SESSION SET NLS_COMP = LINGUISTIC;
ALTER SESSION SET NLS_SORT = BINARY_CI;
```

`BINARY_CI` là ví dụ cho so sánh không phân biệt hoa thường; `BINARY_AI` có thể dùng cho so sánh không phân biệt cả hoa thường và dấu trong các phiên bản hỗ trợ. Thiết lập session có thể ảnh hưởng nhiều câu lệnh trong kết nối, vì vậy cần quản lý connection pool và reset session state đúng cách.

Để hỗ trợ truy vấn dùng cùng quy tắc, có thể tạo function-based index trên `NLSSORT`:

```sql
CREATE INDEX ix_customers_name_ci
ON customers (NLSSORT(name, 'NLS_SORT=BINARY_CI'));

SELECT customer_id, name
FROM customers
WHERE NLSSORT(name, 'NLS_SORT=BINARY_CI') =
      NLSSORT(:search_name, 'NLS_SORT=BINARY_CI');
```

Biểu thức trong truy vấn cần phù hợp với biểu thức chỉ mục để optimizer có thể sử dụng index. Cú pháp và semantics phụ thuộc phiên bản, cấu hình NLS và loại collation được bật. Với Oracle có data-bound collation, hãy đánh giá cách khai báo collation tại cột hoặc bảng theo kiến trúc ứng dụng thay vì phụ thuộc vào session setting không đồng nhất.

## 6. Chuẩn hóa chuỗi và Unicode

Collation và chuẩn hóa chuỗi là hai vấn đề liên quan nhưng khác nhau. Unicode cho phép một ký tự hiển thị được biểu diễn bằng một code point dựng sẵn hoặc bằng ký tự cơ sở cộng dấu kết hợp. Ví dụ, chữ `é` có thể được biểu diễn bằng một code point hoặc bằng `e` cộng dấu sắc kết hợp.

Hai chuỗi có thể hiển thị giống nhau nhưng có dãy code point khác nhau. Một số collation có thể xem chúng tương đương; so sánh nhị phân thường phân biệt. Ứng dụng có thể chọn chuẩn hóa NFC hoặc NFKC theo yêu cầu nghiệp vụ, nhưng NFKC có thể gộp một số ký tự tương thích mà ứng dụng muốn phân biệt. Không nên tự động áp dụng chuẩn hóa tương thích cho mọi định danh.

Các nguyên tắc nên áp dụng:

- Xác định một chuẩn Unicode ở tầng ứng dụng cho dữ liệu định danh và dữ liệu tìm kiếm.
- Không dùng collation không phân biệt dấu cho khóa định danh nếu dấu làm thay đổi ý nghĩa nghiệp vụ.
- Kiểm thử ký tự đặc biệt, ký tự kết hợp, chữ hoa/chữ thường theo locale và ký tự ngoài BMP.
- Giữ nguyên giá trị hiển thị nếu cần; có thể lưu thêm khóa tìm kiếm đã chuẩn hóa để phục vụ truy vấn.
- Đảm bảo cùng một quy tắc được dùng khi tạo dữ liệu, kiểm tra trùng, tìm kiếm và cập nhật.

Ví dụ, nếu ứng dụng chuẩn hóa username bằng cách chuyển thành chữ thường ở tầng dịch vụ nhưng database lại dùng collation có quy tắc khác, hai lớp có thể bất đồng về việc hai username có trùng nhau hay không. Quy tắc chuẩn hóa phải được xác định rõ và kiểm thử ở cả hai lớp.

## 7. Collation, LIKE và tìm kiếm chuỗi

Tìm kiếm mẫu có đặc tính khác với so sánh bằng. Điều kiện `LIKE 'abc%'` có tiền tố cố định; B-tree có thể hỗ trợ range scan trong một số collation và operator class. Điều kiện `LIKE '%abc'` có wildcard ở đầu, nên B-tree thông thường khó xác định một vùng khóa liên tiếp.

Với tìm kiếm không phân biệt hoa thường, cần chọn một cách thực hiện nhất quán:

- Dùng collation không phân biệt hoa thường ở cột hoặc biểu thức nếu hệ quản trị hỗ trợ và semantics phù hợp.
- Dùng `LOWER()`/`UPPER()` cùng expression index hoặc generated/computed column nếu biểu thức được chuẩn hóa cố định.
- Dùng full-text hoặc trigram index cho tìm kiếm từ, cụm từ hoặc chuỗi con khi workload yêu cầu.
- Kiểm tra collation và khả năng index của `LIKE`, `ILIKE` hoặc toán tử tương ứng theo từng hệ quản trị.

Ví dụ PostgreSQL với `ILIKE`:

```sql
SELECT customer_id, name
FROM customers
WHERE name ILIKE 'nguyen%';
```

`ILIKE` là toán tử không phân biệt hoa thường của PostgreSQL theo locale hiện hành. Nó không tự động bảo đảm B-tree index được dùng hiệu quả cho mọi pattern. Với tìm kiếm tiền tố, có thể cần operator class phù hợp; với tìm kiếm chuỗi con như `'%nguyen%'`, extension `pg_trgm` và GIN/GiST index có thể phù hợp hơn. Hãy kiểm tra plan và kết quả đo.

Ví dụ MySQL với collation không phân biệt hoa thường:

```sql
SELECT customer_id, name
FROM customers
WHERE name LIKE 'nguyen%';
```

Nếu cột có collation `_ci`, phép so sánh pattern thường tuân theo collation của cột. Khả năng dùng index phụ thuộc pattern, collation, kiểu dữ liệu và optimizer. Wildcard đầu chuỗi thường làm mất lợi thế range access của B-tree.

## 8. Rủi ro khi thay đổi collation

Thay collation có thể làm thay đổi kết quả truy vấn và ràng buộc dữ liệu. Trước khi thay đổi, hãy kiểm tra các tình huống sau:

1. **Giá trị trùng mới:** hai chuỗi trước đây khác nhau có thể trở thành bằng nhau theo collation mới. Unique index hoặc unique constraint có thể không tạo lại được.
2. **Thứ tự sắp xếp thay đổi:** báo cáo, phân trang và thứ tự hiển thị có thể khác trước.
3. **Kế hoạch truy vấn thay đổi:** index có thể cần rebuild; biểu thức `COLLATE` có thể làm truy vấn không dùng được index hiện có.
4. **Join giữa các cột:** hai cột khác collation có thể gây lỗi, ép chuyển đổi hoặc tăng chi phí so sánh.
5. **Khác biệt môi trường:** collation hoặc phiên bản ICU/locale không đồng nhất giữa production, staging và máy phát triển có thể tạo kết quả khác nhau.
6. **Tác động DDL:** thay đổi collation có thể yêu cầu chuyển đổi dữ liệu hoặc rebuild index, gây tải I/O, log, khóa và thời gian triển khai.

Với unique key, nên kiểm tra trước các nhóm có thể trùng theo collation đích. Có thể tạo truy vấn nhóm theo biểu thức chuẩn hóa tương ứng để tìm xung đột trước khi thay đổi constraint. Biểu thức kiểm tra phải phản ánh đúng semantics của collation đích; `LOWER()` đơn giản có thể không phát hiện hết các trường hợp tương đương theo ngôn ngữ.

## 9. Quy trình đo chi phí và xác minh chỉ mục

Khi một truy vấn so sánh chuỗi chậm, hãy thực hiện theo quy trình:

1. **Xác định semantics cần có.** Làm rõ có phân biệt hoa thường, dấu, khoảng trắng cuối chuỗi và biến thể Unicode hay không.
2. **Kiểm tra collation thực tế.** Xem collation của database, bảng, cột, tham số và biểu thức. Kiểm tra character set và phiên bản locale nếu liên quan.
3. **Đọc câu SQL.** Tìm `COLLATE`, `LOWER`, `UPPER`, `CAST`, hàm trên cột và phép chuyển đổi ngầm định.
4. **Đọc execution plan.** Kiểm tra index seek/range scan hay scan, estimated rows, actual rows, số lần lookup, sort và conversion.
5. **Đo tài nguyên.** Ghi elapsed, CPU, logical/physical reads, số dòng so sánh, memory và wait event.
6. **Tạo phương án phù hợp.** Có thể điều chỉnh collation cột, biểu thức, expression index, computed/generated column hoặc khóa tìm kiếm chuẩn hóa.
7. **Thử nhiều dữ liệu đại diện.** Bao gồm chữ hoa/chữ thường, có dấu/không dấu, ký tự kết hợp, chuỗi dài và giá trị hiếm/phổ biến.
8. **Đo lại cùng điều kiện.** So sánh kết quả, kế hoạch, độ trễ, CPU, I/O và chi phí ghi khi chỉ mục thay đổi.
9. **Kiểm tra tính duy nhất và tương thích.** Đảm bảo không tạo xung đột dữ liệu và kết quả giống chính sách nghiệp vụ.
10. **Theo dõi sau triển khai.** Quan sát query latency, index size, write throughput, lỗi so sánh và cảnh báo phiên bản collation.

### Ví dụ điều tra

Một endpoint tìm khách hàng theo tên chạy chậm sau khi ứng dụng chuyển sang tìm kiếm không phân biệt hoa thường. SQL hiện tại:

```sql
SELECT customer_id, name
FROM customers
WHERE LOWER(name) = LOWER(:name);
```

Execution plan cho thấy scan bảng lớn và CPU tăng. Chỉ mục B-tree hiện có trên `name` không tương ứng trực tiếp với biểu thức `LOWER(name)`. Nhóm vận hành có thể thử expression index hoặc cột tìm kiếm chuẩn hóa, sau đó chạy lại cùng bộ dữ liệu và tham số.

Nếu nghiệp vụ yêu cầu không phân biệt hoa thường nhưng vẫn phân biệt dấu, cần kiểm thử những cặp tên chỉ khác dấu để bảo đảm semantics. Nếu ứng dụng muốn tìm cả `Nguyen` và `Nguyễn`, đó là chính sách tìm kiếm không phân biệt dấu riêng; không nên vô tình đưa chính sách đó vào unique key hoặc mọi phép so sánh khác.

Kết quả thành công cần chứng minh cả ba điều: kết quả đúng theo quy tắc nghiệp vụ, execution plan sử dụng đường truy cập phù hợp và chi phí tổng thể giảm trong workload thực tế.

## 10. Những sai lầm thường gặp

- **Dùng một collation cho mọi cột:** tên hiển thị, mã định danh, email và token có ngữ nghĩa khác nhau.
- **Cho rằng không phân biệt hoa thường cũng là không phân biệt dấu:** đây là hai thuộc tính riêng.
- **Dùng `LOWER()` ở mọi truy vấn:** có thể làm mất khả năng dùng index nếu không có expression index hoặc cột chuẩn hóa phù hợp.
- **Áp dụng `COLLATE` trực tiếp lên cột một cách tùy tiện:** có thể khiến index hiện có không còn phù hợp với biểu thức so sánh.
- **Cho rằng binary collation luôn nhanh hơn đáng kể:** khác biệt thực tế cần đo; chi phí I/O và số dòng thường quan trọng hơn với truy vấn lớn.
- **Bỏ qua Unicode normalization:** chuỗi hiển thị giống nhau có thể có biểu diễn khác nhau.
- **Đổi collation mà không kiểm tra unique key:** dữ liệu trước đây khác nhau có thể trở thành trùng theo quy tắc mới.
- **Giả định mọi hệ quản trị xử lý khoảng trắng giống nhau:** quy tắc PAD SPACE/NO PAD và semantics so sánh khác nhau.
- **Dùng collation session không nhất quán:** connection pool có thể giữ trạng thái session và làm kết quả khác giữa các kết nối.
- **Không kiểm tra version locale/ICU:** nâng cấp thư viện có thể thay đổi thứ tự so sánh và yêu cầu rebuild index.
- **Chỉ đo truy vấn bằng một chuỗi:** cần kiểm tra nhiều ngôn ngữ, dấu, hoa thường, độ dài và tần suất giá trị.

## 11. Checklist thiết kế và tối ưu collation

- [ ] Đã xác định quy tắc hoa thường, dấu, locale, Unicode và khoảng trắng cho từng loại cột.
- [ ] Đã phân biệt collation ngôn ngữ với so sánh nhị phân và kiểu dữ liệu binary.
- [ ] Đã kiểm tra collation thực tế của cột, tham số và biểu thức truy vấn.
- [ ] Đã xác nhận điều kiện lọc dùng được chỉ mục theo cùng semantics.
- [ ] Đã kiểm tra các hàm `LOWER`, `UPPER`, `COLLATE` và implicit conversion trong predicate.
- [ ] Đã đánh giá expression index hoặc cột chuẩn hóa nếu cần tìm kiếm theo khóa biến đổi.
- [ ] Đã kiểm tra tác động tới `ORDER BY`, `GROUP BY`, join, `LIKE` và unique constraint.
- [ ] Đã thử các trường hợp Unicode dựng sẵn/kết hợp, dấu, hoa thường và ký tự đặc biệt.
- [ ] Đã đo CPU, elapsed, logical reads, plan và kích thước chỉ mục trước/sau.
- [ ] Đã kiểm tra dữ liệu trùng theo collation đích trước khi thay đổi schema.
- [ ] Đã lập kế hoạch rebuild index, DDL, rollback và đồng bộ collation giữa các môi trường.
- [ ] Đã xác minh kết quả tìm kiếm phù hợp chính sách nghiệp vụ sau triển khai.

Collation xác định cách cơ sở dữ liệu hiểu và sắp xếp chuỗi; lựa chọn đó ảnh hưởng đến kết quả tìm kiếm, tính duy nhất, execution plan và chi phí so sánh. Khi quy tắc hoa thường, dấu và locale được xác định theo từng loại dữ liệu, đồng thời chỉ mục được xây dựng theo đúng biểu thức truy vấn, hệ thống có thể duy trì semantics nhất quán và tránh các phép chuyển đổi tốn kém không cần thiết.
