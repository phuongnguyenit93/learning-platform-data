# Chọn kiểu dữ liệu theo miền giá trị, độ chính xác và chi phí lưu trữ

Chọn kiểu dữ liệu là một quyết định thiết kế quan trọng của bảng MySQL. Kiểu dữ liệu phải biểu diễn được mọi giá trị hợp lệ của nghiệp vụ, giữ đúng độ chính xác cần thiết và có chi phí lưu trữ phù hợp. Nếu chọn kiểu quá nhỏ, dữ liệu có thể bị tràn hoặc bị từ chối khi ghi. Nếu chọn kiểu không phù hợp, chẳng hạn dùng số thực cho tiền hoặc dùng số để lưu mã định danh, kết quả có thể sai hoặc khó xử lý. Nếu chọn kiểu quá rộng cho mọi cột, index và dữ liệu có thể chiếm nhiều bộ nhớ, đĩa và I/O hơn mức cần thiết.

Bài học này thuộc module `DATABASE_MYSQL`, nơi bạn thực hành thiết kế bảng, kiểu dữ liệu, khóa, truy vấn SQL, index, transaction, kiểm soát đồng thời, đọc kế hoạch thực thi, tối ưu truy vấn, phân quyền và vận hành cơ sở dữ liệu quan hệ. Mục tiêu là thiết kế kiểu dữ liệu dựa trên miền giá trị thực tế, độ chính xác, cách so sánh và chi phí lưu trữ thay vì chọn kiểu theo thói quen.

Sau bài học, bạn có thể:

- Xác định miền giá trị và quy tắc hợp lệ trước khi chọn kiểu dữ liệu.
- Chọn kiểu số nguyên, số thập phân và số thực theo phạm vi và độ chính xác.
- Phân biệt `CHAR`, `VARCHAR`, `TEXT`, `BINARY`, `VARBINARY` và các kiểu chuỗi đặc biệt.
- Chọn kiểu ngày giờ theo ý nghĩa thời gian và cách xử lý múi giờ.
- Quyết định khi nào nên dùng `JSON`, `ENUM`, `SET` hoặc bảng tham chiếu.
- Hiểu ảnh hưởng của kích thước cột, charset, collation và index tới tài nguyên.
- Kiểm tra dữ liệu, chế độ SQL và chuyển đổi kiểu an toàn khi schema thay đổi.

## 1. Quy trình chọn kiểu dữ liệu

Trước khi viết `CREATE TABLE`, hãy trả lời các câu hỏi sau cho từng cột:

1. **Cột biểu diễn điều gì?** Một số lượng có thể cộng trừ, một số tiền, mã định danh, văn bản, thời điểm hay dữ liệu nhị phân?
2. **Miền giá trị hợp lệ là gì?** Giá trị nhỏ nhất, lớn nhất, có âm không, có cho phép số lẻ không, độ dài tối đa bao nhiêu?
3. **Độ chính xác cần thiết ra sao?** Có cần biểu diễn chính xác từng chữ số thập phân không, hay sai số gần đúng được chấp nhận?
4. **Giá trị có quy tắc định dạng không?** Có số 0 ở đầu, dấu gạch, chữ hoa/thường, ký tự Unicode hoặc mã có độ dài cố định không?
5. **Ý nghĩa thời gian là gì?** Ngày lịch, thời lượng, giờ địa phương hay một thời điểm tuyệt đối trên dòng thời gian?
6. **Cột được truy vấn và lập index như thế nào?** Cột có nằm trong primary key, foreign key, điều kiện lọc, join, sort hoặc group không?
7. **Giá trị có thể vắng mặt không?** `NULL` có ý nghĩa riêng hay cột bắt buộc phải có giá trị?

Một quy trình thực tế là ghi miền giá trị trước, chọn kiểu đáp ứng miền đó, sau đó kiểm tra kích thước lưu trữ và thử các giá trị biên. Đừng bắt đầu bằng câu hỏi “kiểu nào nhỏ nhất”; hãy bắt đầu bằng “kiểu nào biểu diễn đúng dữ liệu này?”.

| Tiêu chí | Câu hỏi cần xác định | Ví dụ |
| --- | --- | --- |
| Miền giá trị | Giá trị min/max, âm/dương, số chữ số | Số lượng hàng tồn từ 0 đến vài triệu |
| Độ chính xác | Cần chính xác tuyệt đối hay gần đúng? | Tiền cần chính xác đến 2 chữ số thập phân |
| Ngữ nghĩa | Có tính toán số học hay chỉ là mã? | Số điện thoại là chuỗi, không phải số để cộng |
| Độ dài | Độ dài cố định hay thay đổi? | Mã quốc gia cố định, tên người thay đổi |
| So sánh | Phân biệt hoa/thường, dấu hay byte? | Email có quy tắc chuẩn hóa và collation rõ ràng |
| Vòng đời | Có cần múi giờ hoặc lưu thời điểm tuyệt đối? | Thời điểm thanh toán cần quy ước UTC |
| Truy vấn | Có được dùng làm khóa hoặc index? | `customer_id` được dùng trong join và foreign key |

## 2. Kiểu số nguyên

Các kiểu số nguyên phù hợp với số đếm, ID dạng số, trạng thái dạng mã số và các giá trị không cần phần thập phân. MySQL cung cấp `TINYINT`, `SMALLINT`, `MEDIUMINT`, `INT` và `BIGINT`.

### 2.1. Miền giá trị và kích thước

| Kiểu | Dung lượng | Miền `SIGNED` | Miền `UNSIGNED` |
| --- | ---: | --- | --- |
| `TINYINT` | 1 byte | -128 đến 127 | 0 đến 255 |
| `SMALLINT` | 2 byte | -32,768 đến 32,767 | 0 đến 65,535 |
| `MEDIUMINT` | 3 byte | -8,388,608 đến 8,388,607 | 0 đến 16,777,215 |
| `INT` | 4 byte | -2,147,483,648 đến 2,147,483,647 | 0 đến 4,294,967,295 |
| `BIGINT` | 8 byte | -9,223,372,036,854,775,808 đến 9,223,372,036,854,775,807 | 0 đến 18,446,744,073,709,551,615 |

`SIGNED` là mặc định. `UNSIGNED` bỏ phần miền âm để mở rộng miền dương. Chỉ chọn `UNSIGNED` khi miền nghiệp vụ thực sự không có giá trị âm và các cột tham chiếu có kiểu tương thích. Kiểu và thuộc tính signedness của cột khóa ngoại cần khớp giữa bảng cha và bảng con.

Ví dụ:

```sql
CREATE TABLE inventory_items (
    item_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    quantity INT UNSIGNED NOT NULL DEFAULT 0,
    reorder_level SMALLINT UNSIGNED NOT NULL DEFAULT 10,
    is_active TINYINT UNSIGNED NOT NULL DEFAULT 1,
    PRIMARY KEY (item_id)
) ENGINE = InnoDB;
```

Ở đây, `item_id` có thể tăng theo thời gian nên dùng `BIGINT UNSIGNED`; `quantity` có miền không âm; `reorder_level` có phạm vi nhỏ hơn; `is_active` chỉ cần một miền nhỏ. Trong ứng dụng thực tế, nếu trạng thái có nhiều giá trị hoặc có quy tắc chuyển trạng thái, hãy cân nhắc bảng tham chiếu hoặc `CHECK` constraint thay vì dựa vào một con số không có ý nghĩa.

### 2.2. Chọn kích thước vừa đủ

Không nên dùng `BIGINT` cho mọi cột chỉ vì nó có miền lớn. Chênh lệch mỗi hàng có thể nhỏ, nhưng với hàng trăm triệu bản ghi và nhiều index, kiểu rộng hơn làm tăng kích thước dữ liệu, index, buffer pool và I/O.

Ngược lại, không chọn `TINYINT` cho một bộ đếm có khả năng vượt 255 chỉ vì hiện tại dữ liệu nhỏ. Hãy dự báo tốc độ tăng và tuổi thọ của dữ liệu. Với ID tự tăng, cần ước lượng số bản ghi tối đa trong vòng đời bảng, kể cả dữ liệu đã xóa vì `AUTO_INCREMENT` có thể có khoảng trống.

### 2.3. Những lưu ý về thuộc tính số nguyên

- `AUTO_INCREMENT` thường dùng cho một cột số nguyên được lập index. Giá trị tăng không đảm bảo liên tục và không nên dùng làm số thứ tự nghiệp vụ không được phép thiếu.
- Chiều rộng hiển thị như `INT(11)` không làm `INT` lưu được nhiều số hơn. Display width cho số nguyên đã bị deprecated trong MySQL 8.0.17; không dùng nó để kiểm soát miền giá trị.
- `BOOL` và `BOOLEAN` là alias của `TINYINT(1)`, không phải kiểu boolean độc lập. MySQL vẫn có thể lưu giá trị khác 0 và 1 nếu không có constraint.
- `ZEROFILL` đã bị deprecated và tự động làm cột thành `UNSIGNED`; không dùng nó để định dạng dữ liệu. Hãy định dạng khi hiển thị ở tầng ứng dụng.
- Nếu cần số thứ tự có số 0 ở đầu như `000123`, hãy cân nhắc lưu mã dưới dạng chuỗi hoặc giữ giá trị số và định dạng khi hiển thị, tùy việc số 0 có thuộc bản chất định danh hay không.

## 3. Số thập phân chính xác và số thực gần đúng

MySQL có các kiểu `DECIMAL`/`NUMERIC`, `FLOAT` và `DOUBLE`. Việc chọn đúng nhóm kiểu rất quan trọng với tiền, tỷ lệ, đo lường và phép tính khoa học.

### 3.1. DECIMAL cho giá trị cần chính xác

`DECIMAL(p, s)` lưu số thập phân với độ chính xác cố định. `p` là tổng số chữ số tối đa, `s` là số chữ số ở phần thập phân. Trong MySQL, precision tối đa là 65 và scale tối đa là 30, đồng thời scale không được lớn hơn precision.

Ví dụ:

```sql
CREATE TABLE product_prices (
    product_id BIGINT UNSIGNED NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    tax_rate DECIMAL(5, 4) NOT NULL,
    PRIMARY KEY (product_id)
) ENGINE = InnoDB;
```

`DECIMAL(12,2)` biểu diễn tối đa 10 chữ số phần nguyên và 2 chữ số phần thập phân. `DECIMAL(5,4)` phù hợp với một tỷ lệ có 4 chữ số sau dấu thập phân, với miền dương tối đa nhỏ hơn 10. Hãy chọn `p` và `s` theo hợp đồng nghiệp vụ, không theo ví dụ một cách máy móc.

`DECIMAL` được lưu theo dạng packed decimal; dung lượng phụ thuộc số chữ số trước và sau dấu thập phân, theo nhóm 9 chữ số. Vì vậy, nó không luôn chiếm cùng số byte như một số nguyên. Đổi lại, phép tính thập phân tránh sai số nhị phân thường gặp ở kiểu số thực.

Với tiền tệ, giá sản phẩm, số dư và thuế, `DECIMAL` thường là lựa chọn phù hợp. Tuy nhiên, vẫn cần quy định cách làm tròn, thứ tự tính thuế/chiết khấu và scale của kết quả. Kiểu dữ liệu không tự quyết định chính sách làm tròn của nghiệp vụ.

### 3.2. FLOAT và DOUBLE cho số gần đúng

`FLOAT` thường dùng 4 byte và `DOUBLE` thường dùng 8 byte. Chúng lưu số dấu phẩy động theo biểu diễn nhị phân, nên nhiều giá trị thập phân không thể biểu diễn chính xác tuyệt đối.

```sql
SELECT
    0.1 + 0.2 AS approximate_sum,
    CAST(0.1 AS DECIMAL(10, 2)) + CAST(0.2 AS DECIMAL(10, 2)) AS decimal_sum;
```

Kết quả số thực có thể gần bằng `0.3` nhưng không nhất thiết bằng chính xác. Đây là đặc tính của floating point, không phải lỗi riêng của MySQL.

Dùng `FLOAT` hoặc `DOUBLE` khi sai số gần đúng được chấp nhận, chẳng hạn dữ liệu cảm biến, tính toán khoa học, tọa độ hoặc mô hình thống kê. Không dùng chúng để lưu tiền cần đối soát chính xác. Khi so sánh số thực, thường cần ngưỡng sai số thay vì kiểm tra bằng tuyệt đối `=`.

| Nhu cầu | Kiểu thường phù hợp | Lý do |
| --- | --- | --- |
| Giá tiền, số dư, thuế | `DECIMAL(p,s)` | Chữ số thập phân chính xác theo scale |
| Số lượng nguyên | `INT` hoặc kiểu số nguyên phù hợp | Không có phần thập phân |
| Nhiệt độ từ cảm biến, dữ liệu đo | `FLOAT` hoặc `DOUBLE` | Chấp nhận sai số gần đúng |
| Tỷ lệ tài chính cần đối soát | `DECIMAL(p,s)` | Kiểm soát chính xác số chữ số |
| Mô phỏng khoa học, thống kê | Thường là `DOUBLE` | Dải biểu diễn và độ chính xác lớn hơn FLOAT |

## 4. Kiểu chuỗi và dữ liệu nhị phân

Trước khi chọn kiểu chuỗi, xác định dữ liệu là văn bản có quy tắc ngôn ngữ hay chuỗi byte cần giữ nguyên. Hai loại này có cách so sánh, charset và collation khác nhau.

### 4.1. CHAR và VARCHAR

`CHAR(M)` biểu diễn chuỗi có độ dài khai báo cố định, trong khi `VARCHAR(M)` biểu diễn chuỗi có độ dài thay đổi. `M` được tính theo số ký tự, nhưng số byte cần lưu phụ thuộc charset. `CHAR` có độ dài khai báo tối đa 255 ký tự; độ dài `VARCHAR` hiệu dụng còn phụ thuộc giới hạn byte của hàng và các cột khác.

| Kiểu | Đặc điểm | Tình huống phù hợp |
| --- | --- | --- |
| `CHAR(M)` | Độ dài cố định, có ngữ nghĩa đệm khoảng trắng | Mã có độ dài cố định, mã quốc gia 2 ký tự |
| `VARCHAR(M)` | Độ dài thay đổi, lưu độ dài thực tế cùng dữ liệu | Tên, email, địa chỉ, mã có độ dài thay đổi |
| `TINYTEXT` | Văn bản tối đa 255 byte | Đoạn văn bản nhỏ, ít cần giới hạn bằng VARCHAR |
| `TEXT` | Văn bản tối đa 65,535 byte | Nội dung văn bản dài |
| `MEDIUMTEXT` | Văn bản tối đa 16,777,215 byte | Nội dung dài hơn như bài viết |
| `LONGTEXT` | Giới hạn lý thuyết tối đa 4,294,967,295 byte | Nội dung rất lớn; giới hạn thực tế còn phụ thuộc packet, bộ nhớ và môi trường |

`VARCHAR` thường phù hợp cho phần lớn thuộc tính văn bản có giới hạn nghiệp vụ rõ ràng. Không chọn `TEXT` chỉ vì không muốn suy nghĩ về độ dài. Kiểu `TEXT` có thể ảnh hưởng cách lập index, truy vấn và lưu trữ; index trên `TEXT` thường cần chỉ định prefix hoặc chiến lược khác.

Dung lượng `VARCHAR` gồm dữ liệu ký tự và 1 hoặc 2 byte lưu độ dài, tùy độ dài tối đa theo byte. Với charset đa byte như `utf8mb4`, một ký tự có thể cần tới 4 byte. Vì vậy, `VARCHAR(100)` không đồng nghĩa lúc nào cũng chiếm 100 byte, và giới hạn thực tế của một bảng còn chịu ảnh hưởng giới hạn row size của MySQL.

### 4.2. BINARY và VARBINARY

`BINARY(M)` và `VARBINARY(M)` lưu byte, không áp dụng charset và collation văn bản. Dùng chúng cho dữ liệu nhị phân hoặc token có quy tắc so sánh theo byte.

```sql
CREATE TABLE api_tokens (
    token_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    token_hash BINARY(32) NOT NULL,
    token_label VARCHAR(100) NOT NULL,
    PRIMARY KEY (token_id),
    UNIQUE KEY uk_api_token_hash (token_hash)
) ENGINE = InnoDB;
```

Ví dụ này lưu hash SHA-256 ở dạng 32 byte. Nếu lưu chuỗi hex gồm 64 ký tự, cột cần ít nhất 64 ký tự ASCII; biểu diễn nhị phân gọn hơn nếu ứng dụng có thể chuyển đổi nhất quán.

### 4.3. BLOB

`BLOB`, `MEDIUMBLOB` và `LONGBLOB` lưu dữ liệu nhị phân với các giới hạn dung lượng tương ứng nhóm `TEXT`. Dùng BLOB khi dữ liệu thực sự là byte, chẳng hạn nội dung nhị phân hoặc payload nhỏ cần lưu trong database.

Với tệp lớn, hãy cân nhắc lưu đối tượng trong object storage và lưu metadata, checksum, MIME type, kích thước và đường dẫn trong MySQL. Quyết định này phụ thuộc yêu cầu transaction, backup, quyền truy cập, tải đọc và quy trình phục hồi.

## 5. Charset và collation ảnh hưởng đến chuỗi

Charset quyết định cách ký tự được mã hóa thành byte. Collation quyết định cách so sánh và sắp xếp chuỗi, bao gồm quy tắc phân biệt hoa/thường và dấu.

Với ứng dụng hiện đại cần tiếng Việt và nhiều ngôn ngữ, `utf8mb4` thường là lựa chọn phù hợp:

```sql
CREATE TABLE people (
    person_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL,
    PRIMARY KEY (person_id),
    UNIQUE KEY uk_people_email (email)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;
```

`utf8mb4_0900_ai_ci` là collation phổ biến trong MySQL 8.0+; `ai` biểu thị accent-insensitive và `ci` biểu thị case-insensitive. Điều này có nghĩa phép so sánh và unique index có thể coi một số chuỗi chỉ khác dấu hoặc hoa/thường là tương đương theo quy tắc collation. Điều đó có thể phù hợp với tìm kiếm nhưng cần cân nhắc khi áp dụng cho mã định danh hoặc dữ liệu cần phân biệt chính xác.

Không phải mọi cột văn bản nên dùng cùng một collation. Ví dụ, mã token hoặc mã kỹ thuật có thể cần so sánh nhị phân/case-sensitive. Hãy chọn charset/collation theo ngữ nghĩa của từng cột và bảo đảm các cột dùng trong phép so sánh, join và foreign key có thuộc tính tương thích.

## 6. Kiểu ngày và giờ

MySQL có `DATE`, `TIME`, `DATETIME`, `TIMESTAMP` và `YEAR`. Chọn theo ý nghĩa dữ liệu, không chỉ theo hình thức chuỗi hiển thị.

| Kiểu | Ý nghĩa | Dung lượng cơ bản | Phạm vi/ghi chú |
| --- | --- | ---: | --- |
| `DATE` | Ngày lịch | 3 byte | `1000-01-01` đến `9999-12-31` |
| `TIME` | Giờ hoặc khoảng thời gian | 3 byte | Khoảng từ `-838:59:59` đến `838:59:59` |
| `DATETIME` | Ngày và giờ dạng lịch | 5 byte | `1000-01-01 00:00:00` đến `9999-12-31 23:59:59` |
| `TIMESTAMP` | Thời điểm được chuyển đổi theo múi giờ session | 4 byte | Từ `1970-01-01 00:00:01` UTC đến `2038-01-19 03:14:07` UTC |
| `YEAR` | Năm | 1 byte | Thường từ 1901 đến 2155, ngoài ra có giá trị `0000` |

`TIME`, `DATETIME` và `TIMESTAMP` có thể lưu phần giây lẻ với độ chính xác từ 0 đến 6 chữ số, ví dụ `DATETIME(3)` hoặc `TIMESTAMP(6)`. Phần giây lẻ làm tăng dung lượng lưu trữ thêm tối đa 3 byte.

### 6.1. DATE, DATETIME và TIMESTAMP

- Dùng `DATE` cho ngày sinh, ngày phát hành hoặc ngày nghiệp vụ không có thành phần giờ.
- Dùng `DATETIME` cho thời điểm lịch cần lưu nguyên văn theo quy ước ứng dụng, ví dụ lịch hẹn tại một địa điểm. MySQL không tự chuyển đổi giá trị DATETIME theo múi giờ session.
- Dùng `TIMESTAMP` cho thời điểm tuyệt đối cần chuyển đổi theo `time_zone` của session. MySQL chuyển giá trị từ múi giờ session sang UTC khi lưu và chuyển từ UTC sang múi giờ session khi đọc.

Ví dụ:

```sql
CREATE TABLE appointments (
    appointment_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    starts_at DATETIME NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (appointment_id)
) ENGINE = InnoDB;
```

`starts_at` giữ ngày giờ lịch đã đặt theo quy ước ứng dụng. `created_at` ghi nhận thời điểm tạo bản ghi; với `TIMESTAMP`, kết quả hiển thị phụ thuộc múi giờ session. Hãy thống nhất quy ước lưu trữ và chuyển đổi múi giờ ở tầng ứng dụng.

Kiểm tra múi giờ hiện tại:

```sql
SELECT @@global.time_zone, @@session.time_zone, NOW(), UTC_TIMESTAMP();
```

`NOW()` trả thời gian theo múi giờ session; `UTC_TIMESTAMP()` trả thời gian UTC. Đừng giả định máy chủ, ứng dụng và người dùng cuối đang dùng cùng múi giờ.

### 6.2. TIME không phải thời điểm trong ngày

`TIME` biểu diễn giờ hoặc khoảng thời gian và có thể mang giá trị âm hoặc lớn hơn 24 giờ. Nếu nghiệp vụ cần một thời điểm cụ thể trong ngày kèm ngày tháng, dùng `DATETIME` hoặc `TIMESTAMP` theo ý nghĩa thời gian. Nếu cần thời lượng dài, cân nhắc lưu số giây hoặc đơn vị nhỏ hơn bằng kiểu số nguyên khi phép tính và giới hạn nghiệp vụ rõ ràng.

### 6.3. Tránh lưu ngày giờ dưới dạng chuỗi

Lưu ngày giờ dưới dạng `VARCHAR` khiến việc sắp xếp, lọc theo khoảng thời gian, kiểm tra hợp lệ và tính toán phức tạp hơn. Dùng kiểu temporal giúp MySQL áp dụng phép so sánh và hàm thời gian đúng ngữ nghĩa.

## 7. JSON, ENUM và SET

### 7.1. JSON

Kiểu `JSON` xác thực dữ liệu đầu vào là JSON hợp lệ và lưu theo định dạng nhị phân nội bộ cho phép truy cập các thành phần. JSON phù hợp với thuộc tính linh hoạt hoặc payload có cấu trúc thay đổi, nhưng không nên dùng để thay thế mọi cột quan hệ.

```sql
CREATE TABLE product_metadata (
    product_id BIGINT UNSIGNED NOT NULL,
    attributes JSON NOT NULL,
    PRIMARY KEY (product_id)
) ENGINE = InnoDB;

INSERT INTO product_metadata (product_id, attributes)
VALUES (1, '{"color":"black","weight_gram":850,"wireless":true}');

SELECT
    product_id,
    attributes->>'$.color' AS color,
    attributes->>'$.weight_gram' AS weight_gram
FROM product_metadata;
```

Các thuộc tính thường xuyên lọc, join, sắp xếp hoặc cần constraint nên được cân nhắc tách thành cột có kiểu dữ liệu cụ thể. Có thể lập index trên giá trị JSON thông qua generated column hoặc functional index phù hợp, nhưng cần xác định kiểu trích xuất và cách xử lý giá trị thiếu/null.

### 7.2. ENUM

`ENUM` biểu diễn một giá trị trong danh sách lựa chọn khai báo trước:

```sql
CREATE TABLE support_tickets (
    ticket_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    status ENUM('new', 'in_progress', 'resolved', 'closed') NOT NULL DEFAULT 'new',
    PRIMARY KEY (ticket_id)
) ENGINE = InnoDB;
```

ENUM dùng chỉ số nội bộ để biểu diễn giá trị, thường cần 1 byte nếu danh sách có tối đa 255 phần tử và 2 byte nếu nhiều hơn (tối đa 65,535 phần tử). Thứ tự so sánh/sắp xếp phụ thuộc thứ tự khai báo, không phải thứ tự alphabet. Khi thay đổi danh sách, cần xem xét migration và khả năng tương thích ứng dụng.

ENUM có thể hữu ích cho một tập giá trị nhỏ, ổn định. Nếu trạng thái có metadata, quy tắc chuyển đổi, bản dịch hoặc cần thay đổi thường xuyên, bảng tham chiếu thường linh hoạt hơn.

### 7.3. SET

`SET` biểu diễn tập con của danh sách phần tử đã khai báo. Nó phù hợp với một số trường hợp ít thay đổi, nhưng cách lưu và thao tác có thể gây khó khăn khi ứng dụng cần quan hệ nhiều-nhiều hoặc truy vấn từng lựa chọn. Với tập lựa chọn có thể mở rộng hoặc cần lọc/join linh hoạt, nên cân nhắc bảng liên kết thay vì SET.

`SET` hỗ trợ tối đa 64 phần tử; dung lượng lưu trữ từ 1 đến 8 byte tùy số phần tử được khai báo. Giống `ENUM`, thứ tự và cách biểu diễn gắn với danh sách khai báo, vì vậy cần cân nhắc kỹ khi danh sách có thể thay đổi.

## 8. NULL, DEFAULT và ràng buộc dữ liệu

`NULL` biểu thị giá trị chưa biết, không áp dụng hoặc vắng mặt theo ngữ nghĩa của cột. Nó không giống số 0, chuỗi rỗng hoặc ngày mặc định. Dùng `NOT NULL` khi nghiệp vụ yêu cầu giá trị luôn tồn tại; dùng `NULL` khi trạng thái vắng mặt có ý nghĩa.

```sql
CREATE TABLE employees (
    employee_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(150) NOT NULL,
    middle_name VARCHAR(100) NULL,
    salary DECIMAL(12, 2) NOT NULL,
    terminated_at DATETIME NULL,
    PRIMARY KEY (employee_id),
    CONSTRAINT chk_employee_salary CHECK (salary >= 0)
) ENGINE = InnoDB;
```

`middle_name` có thể không tồn tại; `terminated_at` là `NULL` khi nhân viên chưa nghỉ việc. `salary` là bắt buộc và không âm. `CHECK` constraint được thực thi trong MySQL 8.0.16 trở lên, nhưng vẫn cần kiểm tra phiên bản máy chủ nếu triển khai trên môi trường cũ.

Một số quy tắc quan trọng:

- So sánh `NULL` bằng `IS NULL` hoặc `IS NOT NULL`, không dùng `= NULL`.
- Phép tính với `NULL` thường cho kết quả `NULL`; dùng `COALESCE` khi có quy tắc thay thế rõ ràng.
- `COUNT(column)` bỏ qua giá trị NULL; `COUNT(*)` đếm hàng.
- `DEFAULT` cung cấp giá trị khi câu `INSERT` bỏ qua cột theo quy tắc của MySQL. Nó không thay thế việc quyết định cột có bắt buộc hay không.
- Tránh dùng giá trị giả như `0`, `''` hoặc `'1900-01-01'` để biểu thị “không có dữ liệu” nếu các giá trị đó có thể hợp lệ trong nghiệp vụ.

## 9. Chi phí lưu trữ và tác động tới index

Kiểu dữ liệu ảnh hưởng đến kích thước hàng, index, buffer pool, số trang dữ liệu cần đọc và chi phí truyền dữ liệu. Một cột khóa rộng được lặp lại trong nhiều secondary index có thể làm dung lượng index tăng đáng kể.

### 9.1. Kích thước cột không chỉ là kích thước hàng

Một vài kích thước cơ bản:

| Nhóm | Ví dụ | Kích thước/đặc điểm |
| --- | --- | --- |
| Số nguyên | `INT`, `BIGINT` | 4 byte và 8 byte |
| Số thực | `FLOAT`, `DOUBLE` | Thường 4 byte và 8 byte |
| Số chính xác | `DECIMAL(p,s)` | Packed decimal, phụ thuộc số chữ số |
| Thời gian | `DATE`, `DATETIME`, `TIMESTAMP` | Lần lượt 3, 5 và 4 byte trước phần giây lẻ |
| Chuỗi | `CHAR`, `VARCHAR` | Phụ thuộc số ký tự, charset và overhead độ dài |
| Văn bản lớn | `TEXT`, `BLOB` | Có thể lưu ngoài phần dữ liệu hàng tùy kích thước và row format |

Đây là số liệu cơ bản, không phải công thức tính chính xác kích thước toàn bộ hàng. MySQL còn cần metadata, NULL bitmap, độ dài biến đổi, index và cấu trúc lưu trữ của engine. `VARCHAR` dùng 1 hoặc 2 byte độ dài; chuỗi đa byte có thể chiếm nhiều byte hơn số ký tự.

### 9.2. Khóa chính và secondary index

Với InnoDB, primary key là clustered index. Các secondary index lưu giá trị khóa chính để định vị hàng. Do đó, primary key dài làm mỗi secondary index có thể lớn hơn. Chọn khóa chính nhỏ gọn, ổn định và phù hợp nghiệp vụ giúp kiểm soát dung lượng index.

Ví dụ, một khóa chính `BIGINT` chiếm 8 byte trong khi `INT` chiếm 4 byte. Nếu miền giá trị đảm bảo không vượt giới hạn `INT`, dùng `INT` có thể giảm kích thước khóa. Nhưng nếu bảng cần hơn 2.1 tỷ ID dương signed hoặc có kế hoạch tăng vượt giới hạn, chọn `BIGINT` ngay từ đầu có thể tránh migration tốn kém sau này.

### 9.3. Giới hạn kích thước hàng

MySQL có giới hạn kích thước hàng tối đa 65,535 byte ở lớp SQL, không tính toàn bộ dữ liệu BLOB/TEXT được lưu ngoài hàng. Với charset đa byte, khai báo nhiều cột `VARCHAR` rất rộng có thể vượt giới hạn này ngay cả khi dữ liệu thực tế thường ngắn. Hãy thiết kế theo kích thước byte tối đa và kiểm tra DDL khi thêm nhiều cột.

## 10. Chuyển đổi kiểu và kiểm soát dữ liệu đầu vào

MySQL có thể chuyển đổi kiểu ngầm định trong biểu thức hoặc khi ghi dữ liệu. Việc chuyển đổi có thể gây mất thông tin, làm kết quả so sánh khác dự kiến hoặc khiến optimizer khó sử dụng index hiệu quả.

Ví dụ, nếu `customer_id` là `INT` nhưng ứng dụng truyền chuỗi tùy ý vào điều kiện so sánh, MySQL có thể thực hiện chuyển đổi theo quy tắc kiểu. Hãy dùng tham số có kiểu phù hợp và không dựa vào ép kiểu ngầm định để làm sạch dữ liệu.

Kiểm tra chế độ SQL:

```sql
SELECT @@sql_mode;
```

Chế độ strict giúp MySQL từ chối hoặc báo lỗi nhiều giá trị nằm ngoài miền thay vì âm thầm điều chỉnh hoặc cắt bớt trong các tình huống cho phép chuyển đổi. Hành vi cụ thể còn phụ thuộc kiểu dữ liệu, câu lệnh và SQL mode. Ứng dụng nên xác thực dữ liệu ở đầu vào và xử lý lỗi ghi rõ ràng.

Khi thay đổi kiểu cột:

1. Thống kê giá trị min/max, độ dài lớn nhất, giá trị NULL và các giá trị không hợp lệ.
2. Kiểm tra code ứng dụng, API, báo cáo, import/export và các bảng tham chiếu.
3. Xác định chuyển đổi có mất dữ liệu, làm tròn, cắt chuỗi hoặc thay đổi collation hay không.
4. Sao lưu và thử migration trên bản sao dữ liệu.
5. Đánh giá thời gian rebuild table/index, khóa và dung lượng tạm.
6. Sau migration, kiểm tra số hàng, giá trị biên, constraint, index và truy vấn quan trọng.

## 11. Ví dụ thiết kế bảng theo miền nghiệp vụ

Giả sử hệ thống bán hàng cần lưu khách hàng, đơn hàng và các dòng hàng. Một thiết kế khởi đầu có thể như sau:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    email VARCHAR(255) NOT NULL,
    full_name VARCHAR(150) NOT NULL,
    phone_number VARCHAR(30) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uk_customers_email (email)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_code VARCHAR(32) NOT NULL,
    status ENUM('pending', 'paid', 'cancelled', 'refunded') NOT NULL DEFAULT 'pending',
    total_amount DECIMAL(14, 2) NOT NULL,
    placed_at DATETIME NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id),
    UNIQUE KEY uk_orders_code (order_code),
    KEY idx_orders_customer_placed (customer_id, placed_at),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id),
    CONSTRAINT chk_orders_total CHECK (total_amount >= 0)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4;

CREATE TABLE order_items (
    order_id BIGINT UNSIGNED NOT NULL,
    line_no SMALLINT UNSIGNED NOT NULL,
    product_code VARCHAR(40) NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id, line_no),
    KEY idx_order_items_product (product_code),
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id)
        REFERENCES orders (order_id),
    CONSTRAINT chk_order_items_quantity CHECK (quantity > 0),
    CONSTRAINT chk_order_items_price CHECK (unit_price >= 0)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4;
```

Giải thích các quyết định:

- ID dùng `BIGINT UNSIGNED` vì có thể tăng lâu dài và không có giá trị âm. Các cột foreign key dùng cùng kiểu và signedness.
- `email`, `full_name`, `phone_number`, `order_code` và `product_code` là chuỗi vì chúng là dữ liệu định danh/hiển thị, không phải đại lượng số học. Số điện thoại có thể có dấu `+`, khoảng trắng hoặc số 0 đầu.
- Tiền dùng `DECIMAL` để giữ độ chính xác thập phân.
- `quantity` và `line_no` là số nguyên không âm; `line_no` có miền nhỏ hơn.
- `placed_at` là `DATETIME` để lưu giờ lịch của đơn hàng theo quy ước ứng dụng; `created_at` là `TIMESTAMP` ghi nhận thời điểm tạo.
- `status` dùng `ENUM` vì ví dụ có tập trạng thái nhỏ và ổn định. Nếu quy trình trạng thái thường xuyên thay đổi hoặc cần metadata, hãy chuyển sang bảng tham chiếu.
- `CHECK` constraint ngăn giá trị âm hoặc số lượng không hợp lệ ở cấp database.

Đây là schema minh họa. Hệ thống thật cần xác định chính sách email duy nhất theo collation, chuẩn hóa số điện thoại, cách lưu tiền nhiều loại tiền tệ, múi giờ, vòng đời trạng thái và yêu cầu mở rộng dữ liệu trước khi chốt thiết kế.

## 12. Các lựa chọn sai thường gặp

| Lựa chọn sai | Vấn đề | Cách chọn phù hợp hơn |
| --- | --- | --- |
| Dùng `FLOAT` cho tiền | Có thể phát sinh sai số nhị phân | Dùng `DECIMAL(p,s)` với scale theo nghiệp vụ |
| Dùng `INT` cho số điện thoại | Mất số 0 đầu, không giữ dấu `+`, không có ý nghĩa số học | Dùng `VARCHAR` |
| Dùng `VARCHAR` cho ngày giờ | So sánh, sắp xếp và tính toán thời gian khó chính xác | Dùng `DATE`, `DATETIME` hoặc `TIMESTAMP` |
| Dùng `BIGINT` cho mọi cột | Tăng kích thước hàng và index không cần thiết | Chọn số nguyên nhỏ nhất đáp ứng miền giá trị dự kiến |
| Dùng `TEXT` cho mọi chuỗi | Khó giới hạn miền dữ liệu và có thể làm index phức tạp | Dùng `VARCHAR(M)` khi có giới hạn nghiệp vụ rõ ràng |
| Dùng `CHAR` cho chuỗi độ dài biến đổi | Có thể lãng phí và gây khác biệt xử lý khoảng trắng | Dùng `VARCHAR(M)` |
| Dùng `NULL` thay cho mọi trạng thái | Ngữ nghĩa không rõ và truy vấn phải xử lý nhiều trường hợp | Định nghĩa rõ `NULL`, default và trạng thái nghiệp vụ |
| Dùng `ENUM` cho danh sách thay đổi liên tục | Migration và thứ tự giá trị khó quản lý | Dùng bảng tham chiếu khi cần mở rộng |
| Dùng `DATETIME` và `TIMESTAMP` như nhau | Có thể sai lệch khi chuyển múi giờ | Chọn theo ý nghĩa wall-clock hay instant |

## 13. Checklist trước khi chốt schema

- [ ] Đã ghi miền giá trị min/max và khả năng tăng trưởng cho từng cột số.
- [ ] Đã xác định cột nào cần số thập phân chính xác và cột nào chấp nhận sai số gần đúng.
- [ ] Đã phân biệt dữ liệu định danh dạng chuỗi với đại lượng số học.
- [ ] Đã chọn độ dài chuỗi theo số ký tự và charset, đồng thời tính đến giới hạn byte.
- [ ] Đã chọn charset/collation theo ngôn ngữ và quy tắc so sánh.
- [ ] Đã xác định quy ước múi giờ cho `DATETIME` và `TIMESTAMP`.
- [ ] Đã quyết định rõ cột nào được phép `NULL` và default có ý nghĩa gì.
- [ ] Đã kiểm tra kiểu và signedness của các cột khóa ngoại.
- [ ] Đã xem xét kích thước primary key và ảnh hưởng lên secondary index.
- [ ] Đã thử giá trị biên, dữ liệu Unicode, giá trị NULL và dữ liệu không hợp lệ.
- [ ] Đã kiểm tra SQL mode và quy tắc chuyển đổi kiểu của môi trường triển khai.

## 14. Bài tập thực hành

1. Thiết kế cột lưu số lượng sản phẩm có thể tăng đến 5 triệu. Chọn kiểu số nguyên và giải thích miền giá trị.
2. Thiết kế cột giá sản phẩm có tối đa 8 chữ số phần nguyên và 2 chữ số thập phân. Viết DDL và giải thích precision/scale.
3. Lưu số điện thoại Việt Nam, mã bưu chính và mã đơn hàng có thể có số 0 đầu. Giải thích vì sao không dùng kiểu số nguyên.
4. Tạo bảng lưu tên tiếng Việt bằng `utf8mb4`. So sánh một collation case-insensitive/accent-insensitive với một collation nhị phân hoặc case-sensitive trên dữ liệu mẫu.
5. Chọn `DATE`, `DATETIME` hoặc `TIMESTAMP` cho ngày sinh, lịch hẹn và thời điểm thanh toán. Ghi rõ quy ước múi giờ cho từng trường hợp.
6. Chạy phép cộng `0.1 + 0.2` với số thực và `DECIMAL`. Giải thích vì sao kết quả có thể khác nhau.
7. Tạo một cột JSON cho thuộc tính ít truy vấn và tách một thuộc tính thường xuyên lọc thành cột riêng hoặc generated column có index. So sánh cách truy vấn.
8. Dùng `CHECK` constraint để giới hạn số lượng lớn hơn 0 và giá tiền không âm. Thử insert dữ liệu ngoài miền và quan sát kết quả.
9. Dùng `EXPLAIN` để xem tác động của một khóa/index rộng hơn trên truy vấn thử nghiệm; giải thích ảnh hưởng tiềm năng tới dung lượng và số trang index.

## 15. Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể xác định miền giá trị và độ chính xác trước khi chọn kiểu, giải thích được sự khác nhau giữa số chính xác và số gần đúng, chọn đúng kiểu chuỗi và thời gian theo ngữ nghĩa, cấu hình charset/collation phù hợp, quyết định rõ việc dùng `NULL`, và giải thích tác động của kích thước cột lên hàng, khóa và index. Bạn cũng cần thiết kế được một schema nhỏ có kiểu dữ liệu phù hợp, constraint rõ ràng và kiểm tra được các giá trị biên.
