# CHAR, VARCHAR và đánh đổi độ dài với cách lưu trữ

Khi thiết kế cột văn bản trong MySQL, hai kiểu dữ liệu thường gặp là `CHAR` và `VARCHAR`. Cả hai đều lưu chuỗi ký tự, nhưng khác nhau về cách biểu diễn độ dài, xử lý khoảng trắng ở cuối và lượng dữ liệu cần lưu. Chọn đúng kiểu giúp schema thể hiện đúng dữ liệu nghiệp vụ, sử dụng dung lượng hợp lý và tránh các lỗi so sánh hoặc cắt chuỗi khó phát hiện.

Quy tắc thực tế là dùng `CHAR(n)` cho giá trị có độ dài gần như cố định theo nghiệp vụ, chẳng hạn mã quốc gia hai ký tự hoặc mã tiền tệ ba ký tự; dùng `VARCHAR(n)` cho chuỗi có độ dài thay đổi như tên, email, địa chỉ và mã tham chiếu. Không nên chọn `CHAR` chỉ vì nghĩ nó luôn nhanh hơn, hoặc chọn `VARCHAR` với giới hạn tùy ý quá lớn. Cần xét charset, độ dài dữ liệu thực tế, index, giới hạn hàng và hành vi ứng dụng.

## 1. CHAR và VARCHAR khác nhau thế nào?

| Đặc điểm | `CHAR(n)` | `VARCHAR(n)` |
| --- | --- | --- |
| Độ dài khai báo | Số ký tự cố định | Số ký tự tối đa |
| Cách lưu logic | Giá trị được đệm bên phải bằng dấu cách đến độ dài khai báo | Lưu độ dài thực tế của chuỗi |
| Khi đọc | Khoảng trắng ở cuối thường được loại bỏ, trừ chế độ tương thích đặc biệt | Giữ lại khoảng trắng ở cuối |
| Chi phí độ dài | Có thể tốn chỗ nếu giá trị thường ngắn hơn `n` | Có thêm byte lưu độ dài, đổi lại không đệm toàn bộ phần còn thiếu |
| Trường hợp phù hợp | Mã có độ dài cố định | Văn bản và mã có độ dài biến đổi |

Ví dụ:

```sql
CREATE TABLE code_examples (
    country_code CHAR(2) NOT NULL,
    currency_code CHAR(3) NOT NULL,
    display_name VARCHAR(100) NOT NULL
) ENGINE=InnoDB;
```

`country_code` có thể lưu mã quốc gia dạng `VN`, `US`; `currency_code` có thể lưu `VND`, `USD`; `display_name` có độ dài khác nhau giữa các bản ghi nên phù hợp với `VARCHAR`.

## 2. Độ dài khai báo là số ký tự, không phải số byte

Với kiểu chuỗi không nhị phân như `CHAR` và `VARCHAR`, độ dài `n` được khai báo theo số ký tự. Số byte thực tế phụ thuộc character set.

Ví dụ với `utf8mb4`, một ký tự có thể cần từ 1 đến 4 byte. Do đó:

- `VARCHAR(100)` cho phép tối đa 100 ký tự, không có nghĩa là luôn chiếm 100 byte.
- Trong trường hợp tối đa, 100 ký tự `utf8mb4` có thể cần tới 400 byte dữ liệu, chưa tính phần lưu độ dài.
- `CHAR(3)` biểu diễn ba ký tự; lượng byte phụ thuộc các ký tự và character set được dùng.

Có thể phân biệt số ký tự và số byte bằng hai hàm:

```sql
SELECT
    CHAR_LENGTH('Việt') AS character_count,
    LENGTH(CONVERT('Việt' USING utf8mb4)) AS byte_count;
```

Với chuỗi ví dụ được mã hóa bằng `utf8mb4`, `CHAR_LENGTH()` đếm số ký tự còn `LENGTH()` trả về số byte. Khi kiểm tra dữ liệu tiếng Việt hoặc emoji, không nên suy ra dung lượng từ số ký tự đơn thuần.

Nên chọn charset ở cấp database/table hoặc column một cách nhất quán. Với ứng dụng mới, `utf8mb4` thường là lựa chọn phù hợp để lưu đầy đủ Unicode. Collation đi kèm charset quyết định cách so sánh và sắp xếp chuỗi, ví dụ phân biệt hoa/thường hoặc dấu trong các phép so sánh.

## 3. CHAR lưu trữ và xử lý khoảng trắng ra sao?

`CHAR(n)` là kiểu có độ dài cố định về mặt ngữ nghĩa. Khi lưu giá trị ngắn hơn `n`, MySQL đệm thêm dấu cách ở bên phải. Khi đọc, các dấu cách ở cuối thường được loại bỏ.

Ví dụ:

```sql
CREATE TABLE char_demo (
    code CHAR(5) NOT NULL
) ENGINE=InnoDB;

INSERT INTO char_demo (code)
VALUES ('AB');

SELECT
    code,
    CHAR_LENGTH(code) AS character_count,
    HEX(code) AS stored_value_hex
FROM char_demo;
```

Giá trị `AB` được đệm theo độ dài cột. Hành vi hiển thị khi truy vấn phụ thuộc SQL mode `PAD_CHAR_TO_FULL_LENGTH`; trong chế độ mặc định, khoảng trắng ở cuối của giá trị `CHAR` được loại bỏ khi đọc. `PAD_CHAR_TO_FULL_LENGTH` là chế độ tương thích đã bị deprecated trong MySQL 8.0, không nên bật để xây dựng logic ứng dụng mới.

Điểm cần nhớ: `CHAR` không phù hợp nếu khoảng trắng cuối chuỗi mang ý nghĩa dữ liệu. Nếu ứng dụng cần bảo toàn chính xác chuỗi người dùng nhập, `VARCHAR` thường dễ dự đoán hơn.

Về triển khai nội bộ, không nên hiểu “fixed-length” là mọi cột `CHAR` luôn chiếm một số byte cố định bất kể charset. InnoDB xử lý các cột `CHAR` có độ dài tối đa vượt 255 byte như trường có độ dài biến đổi; điều này có thể xảy ra với charset nhiều byte như `utf8mb4` và cột `CHAR` dài. Vì vậy, kiểu `CHAR` mô tả quy tắc độ dài ở mức ký tự, còn cách bố trí byte thực tế vẫn phụ thuộc charset và storage engine.

## 4. VARCHAR lưu trữ độ dài thực tế

`VARCHAR(n)` cho phép mỗi hàng có chuỗi dài từ 0 đến tối đa `n` ký tự, tùy các ràng buộc khác của cột. MySQL lưu dữ liệu chuỗi cùng một phần tiền tố độ dài. Phần tiền tố thường cần một hoặc hai byte, tùy giới hạn byte tối đa mà cột có thể chứa.

Ví dụ:

```sql
CREATE TABLE customer_profiles (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    display_name VARCHAR(120) NOT NULL,
    email VARCHAR(254) NOT NULL,
    address_line VARCHAR(300) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_customer_profiles_email (email)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4;
```

Một hàng có tên hiển thị 12 ký tự chỉ lưu nội dung thực tế của tên cùng phần thông tin độ dài; nó không tự động dành chỗ cho đủ 120 ký tự. Đây là lợi thế khi độ dài giữa các hàng thay đổi nhiều.

Tuy nhiên, `VARCHAR` không miễn phí: phần tiền tố độ dài, metadata hàng, index và cách storage engine tổ chức record đều có chi phí. Với dữ liệu dài, InnoDB còn có thể dùng cơ chế lưu trữ off-page tùy row format và kích thước hàng. Vì vậy, không thể tính chính xác dung lượng bảng chỉ bằng cách cộng độ dài khai báo của các cột.

## 5. Đánh đổi dung lượng giữa CHAR và VARCHAR

Giả sử một cột mã luôn chứa đúng 3 ký tự, còn một cột tên có thể dài từ 5 đến 40 ký tự:

```sql
CREATE TABLE storage_tradeoff (
    currency_code CHAR(3) NOT NULL,
    customer_name VARCHAR(100) NOT NULL
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4;
```

- `currency_code` có độ dài nghiệp vụ cố định, vì vậy `CHAR(3)` diễn đạt ý định rõ ràng và không cần lưu một độ dài biến thiên cho từng mã.
- `customer_name` có độ dài khác nhau, vì vậy `VARCHAR(100)` tránh đệm mọi giá trị lên 100 ký tự.

Nếu dùng `CHAR(100)` cho tên khách hàng thường chỉ dài 20 ký tự, phần đệm có thể gây lãng phí. Nếu dùng `VARCHAR(3)` cho mã tiền tệ luôn có đúng 3 ký tự, phần tiền tố độ dài là chi phí nhỏ và không nhất thiết tạo khác biệt hiệu năng đáng kể; lựa chọn `CHAR(3)` thường phản ánh đúng mô hình dữ liệu hơn.

| Đặc điểm dữ liệu | Lựa chọn thường hợp lý | Lý do |
| --- | --- | --- |
| Mã ISO quốc gia luôn 2 ký tự | `CHAR(2)` | Độ dài cố định theo chuẩn |
| Mã tiền tệ luôn 3 ký tự | `CHAR(3)` | Độ dài cố định theo chuẩn |
| Tên người hoặc tên sản phẩm | `VARCHAR(n)` | Độ dài thay đổi |
| Email | `VARCHAR(n)` | Độ dài thay đổi và cần giữ nguyên chuỗi |
| Số điện thoại | `VARCHAR(n)` | Có dấu `+`, số 0 đầu, khoảng trắng hoặc phần mở rộng |
| Mã đơn hàng có độ dài thay đổi | `VARCHAR(n)` | Không phải mọi mã đều có cùng độ dài |
| Chuỗi trạng thái có tập giá trị ngắn nhưng độ dài khác nhau | `VARCHAR(n)` hoặc kiểu phù hợp khác | Không cần đệm mọi giá trị lên một độ dài cố định |

Đây là nguyên tắc mô hình hóa, không phải luật tuyệt đối. Nếu một hệ thống quy định mã có đúng một độ dài và kiểm soát đầu vào, `CHAR` có thể phù hợp. Nếu dữ liệu có thể thay đổi theo nhà cung cấp hoặc tiêu chuẩn, `VARCHAR` linh hoạt hơn.

## 6. Giới hạn độ dài và giới hạn kích thước hàng

`CHAR` có giới hạn khai báo tối đa 255 ký tự. `VARCHAR` có giới hạn lớn hơn, nhưng độ dài thực tế còn phụ thuộc giới hạn kích thước hàng, charset và storage engine.

Với MySQL, kích thước hàng tối đa về mặt định nghĩa là 65.535 byte, được chia sẻ giữa các cột và chịu ảnh hưởng của overhead. Do đó, không thể khai báo nhiều cột `VARCHAR` rất lớn rồi giả định tất cả đều có thể chứa tối đa đồng thời trong cùng một hàng. `utf8mb4` có thể cần tới 4 byte cho mỗi ký tự, nên giới hạn số ký tự hiệu dụng có thể thấp hơn đáng kể so với số byte.

Với InnoDB, một số giá trị cột dài có thể được lưu ngoài trang dữ liệu chính tùy row format, nhưng điều đó không loại bỏ các giới hạn khai báo và giới hạn hàng của MySQL. Khi thiết kế chuỗi lớn, cần cân nhắc `TEXT` nếu dữ liệu có bản chất nội dung dài, đồng thời kiểm tra giới hạn index, truy vấn và cách ứng dụng đọc/ghi.

Không nên chọn `VARCHAR(65535)` chỉ để “phòng khi cần”. Hãy xác định độ dài hợp lý từ quy tắc nghiệp vụ, validation của ứng dụng và tiêu chuẩn dữ liệu đầu vào.

## 7. Ảnh hưởng của CHAR và VARCHAR đến index

Các cột chuỗi thường được dùng làm khóa tìm kiếm, khóa duy nhất hoặc điều kiện nối bảng. Khi tạo index, kích thước khóa phụ thuộc kiểu dữ liệu, charset, collation và độ dài cột. Cột khai báo quá rộng có thể làm tăng kích thước index, giảm số bản ghi trên một page và tăng chi phí cache/I/O.

Ví dụ:

```sql
CREATE TABLE accounts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    account_code CHAR(8) NOT NULL,
    email VARCHAR(254) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_accounts_account_code (account_code),
    UNIQUE KEY uq_accounts_email (email)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4;
```

`account_code` có độ dài cố định nên `CHAR(8)` thể hiện đúng quy tắc. Email thay đổi độ dài nên dùng `VARCHAR(254)`. Cả hai có unique index để database thực thi tính duy nhất.

Khi index chuỗi dài, cần xem giới hạn key length của InnoDB và row format. Nếu chỉ cần tìm theo một phần định danh, prefix index có thể là lựa chọn trong một số trường hợp:

```sql
CREATE INDEX idx_accounts_email_prefix
ON accounts (email(100));
```

Prefix index không tương đương với index đầy đủ: nó chỉ lưu phần đầu của giá trị và có thể cần đọc thêm hàng để xác minh. Không dùng prefix index thay cho unique constraint khi cần bảo đảm toàn bộ email là duy nhất.

Đánh giá index bằng truy vấn thực tế và `EXPLAIN`; không tạo index chỉ vì một cột có kiểu `CHAR` hoặc `VARCHAR`.

## 8. Khoảng trắng cuối chuỗi và phép so sánh

Một khác biệt quan trọng là `VARCHAR` giữ khoảng trắng ở cuối khi lưu và đọc, trong khi `CHAR` có quy tắc đệm và loại bỏ khoảng trắng cuối khi đọc. Tuy nhiên, việc hai chuỗi có được xem là bằng nhau khi so sánh còn phụ thuộc collation.

Nhiều collation có thuộc tính `PAD SPACE`: khi so sánh, MySQL đệm chuỗi ngắn hơn bằng dấu cách để hai giá trị có cùng độ dài. Một số collation Unicode mới, chẳng hạn nhóm collation có hậu tố `0900`, sử dụng `NO PAD`, nên khoảng trắng cuối có thể ảnh hưởng đến kết quả so sánh. Vì vậy, không nên suy ra hành vi equality chỉ từ kiểu `CHAR` hay `VARCHAR`.

Có thể kiểm tra collation và thuộc tính padding:

```sql
SHOW COLLATION LIKE 'utf8mb4%';
```

Trong kết quả trên các phiên bản hỗ trợ, xem cột `Pad_attribute` để biết collation dùng `PAD SPACE` hay `NO PAD`. Cần chọn collation theo yêu cầu so sánh ngôn ngữ, không chỉ dựa vào tên hoặc thói quen.

Nếu khoảng trắng cuối là dữ liệu có ý nghĩa, hãy chọn kiểu/collation phù hợp và kiểm thử rõ ràng bằng dữ liệu đại diện. Không dùng `TRIM()` một cách tùy tiện vì có thể làm thay đổi dữ liệu hợp lệ.

## 9. Charset, collation và độ dài chuỗi

Charset xác định cách ký tự được mã hóa thành byte; collation xác định cách so sánh và sắp xếp. Cả hai có ảnh hưởng đến thiết kế `CHAR`/`VARCHAR`:

- `utf8mb4` lưu được nhiều loại ký tự Unicode, bao gồm tiếng Việt và emoji.
- `ascii` phù hợp với các mã chỉ chứa ký tự ASCII theo quy tắc nghiệp vụ rõ ràng.
- Collation không phân biệt hoa/thường có thể xem `A` và `a` là tương đương trong phép so sánh.
- Collation không phân biệt dấu có thể xem một số biến thể ký tự có/không dấu là tương đương.
- Collation `PAD SPACE` hoặc `NO PAD` ảnh hưởng cách xử lý khoảng trắng cuối khi so sánh.

Ví dụ khai báo rõ charset và collation cho cột:

```sql
CREATE TABLE localized_names (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    name VARCHAR(150)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
        NOT NULL,
    PRIMARY KEY (id)
) ENGINE=InnoDB;
```

Collation `utf8mb4_0900_ai_ci` minh họa collation Unicode của MySQL 8.0; nó không có sẵn trên mọi phiên bản hoặc hệ quản trị tương thích. Nếu cần chạy trên phiên bản cũ hơn, chọn collation được phiên bản đó hỗ trợ và kiểm thử hành vi so sánh.

Đừng thay collation trên một cột có unique index mà chưa kiểm tra dữ liệu trùng theo quy tắc mới. Một collation không phân biệt hoa/thường hoặc dấu có thể làm các giá trị trước đây khác nhau trở thành tương đương, dẫn tới lỗi khi tạo unique index hoặc thay đổi kết quả truy vấn.

## 10. Chọn CHAR hay VARCHAR theo tình huống

### Nên cân nhắc CHAR khi

- Giá trị luôn có cùng số ký tự theo một chuẩn hoặc quy tắc nghiệp vụ.
- Không cần bảo toàn khoảng trắng cuối chuỗi như dữ liệu nhập tự do.
- Muốn thể hiện rõ mã có độ dài cố định trong schema.

Ví dụ: mã quốc gia hai ký tự, mã tiền tệ ba ký tự hoặc mã trạng thái cố định có quy ước rõ ràng.

### Nên cân nhắc VARCHAR khi

- Độ dài giữa các bản ghi thay đổi đáng kể.
- Cần giữ nguyên khoảng trắng cuối của giá trị khi lưu và đọc.
- Dữ liệu là tên, email, địa chỉ, số điện thoại hoặc mã có độ dài thay đổi.
- Giới hạn tối đa có thể xác định nhưng không phải độ dài thực tế của mọi giá trị.

Ví dụ: tên khách hàng, địa chỉ giao hàng, email, mã đơn hàng do nhiều hệ thống tạo ra.

### Khi nào cần kiểu khác?

- Dùng `BINARY(n)` hoặc `VARBINARY(n)` cho dữ liệu byte không có ngữ nghĩa văn bản.
- Dùng `TEXT` khi dữ liệu có thể dài hơn giới hạn `VARCHAR` hợp lý và có bản chất nội dung dài.
- Dùng `JSON` khi dữ liệu có cấu trúc JSON và cần thao tác theo tính năng JSON của MySQL.
- Dùng kiểu số hoặc ngày giờ nếu dữ liệu thực chất là số hoặc thời điểm; không lưu số điện thoại hay mã có số 0 đầu bằng kiểu số.

## 11. Kiểm tra dữ liệu và tránh lỗi cắt chuỗi

Độ dài khai báo của `CHAR`/`VARCHAR` là một ràng buộc schema. Nếu dữ liệu đầu vào dài hơn giới hạn, kết quả phụ thuộc SQL mode và ngữ cảnh thực thi. Trong chế độ strict, MySQL thường báo lỗi thay vì âm thầm cắt dữ liệu; ở chế độ không strict, có thể xuất hiện cảnh báo và giá trị bị điều chỉnh.

Kiểm tra SQL mode:

```sql
SELECT @@SESSION.sql_mode;
```

Trong ứng dụng, cần validate độ dài trước khi gửi dữ liệu và xử lý lỗi từ database. Không dựa vào việc MySQL tự cắt chuỗi để giới hạn input, vì có thể làm mất dữ liệu hoặc tạo ra hai giá trị trùng nhau ngoài ý muốn.

Có thể tìm các giá trị dài bất thường:

```sql
SELECT
    id,
    display_name,
    CHAR_LENGTH(display_name) AS character_count,
    LENGTH(display_name) AS byte_count
FROM customer_profiles
WHERE CHAR_LENGTH(display_name) > 100;
```

Ví dụ trên giả định cột `display_name` đang có giới hạn 100 ký tự; với cột `VARCHAR(100)` hợp lệ, truy vấn không thể trả về giá trị vượt giới hạn. Trong thực tế, dùng cùng mẫu để kiểm tra nguồn dữ liệu staging, file import hoặc biểu thức trước khi ghi vào bảng đích.

## 12. Quy trình chọn độ dài và kiểu chuỗi

Trước khi định nghĩa cột, hãy trả lời các câu hỏi:

1. Dữ liệu có phải chuỗi văn bản hay là mã byte nhị phân?
2. Độ dài có cố định theo chuẩn nghiệp vụ hay thay đổi theo từng bản ghi?
3. Có cần giữ khoảng trắng cuối không?
4. Character set nào được dùng và mỗi ký tự có thể chiếm bao nhiêu byte?
5. Collation cần phân biệt hoa/thường, dấu và khoảng trắng như thế nào?
6. Cột có nằm trong index hoặc unique key không? Giới hạn key length là bao nhiêu?
7. Độ dài tối đa dựa trên tiêu chuẩn, hợp đồng tích hợp hay chỉ là ước lượng?
8. Ứng dụng có validation và xử lý lỗi khi vượt giới hạn không?

Sau khi chọn kiểu, kiểm thử với dữ liệu thực tế: chuỗi ngắn nhất, dài nhất, tiếng Việt có dấu, emoji nếu được phép, khoảng trắng đầu/cuối và các trường hợp so sánh theo collation.

## 13. Ví dụ schema tổng hợp

Ví dụ dưới đây kết hợp mã cố định và văn bản biến độ dài:

```sql
CREATE TABLE customer_contacts (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    country_code CHAR(2) NOT NULL
        COMMENT 'Mã quốc gia gồm đúng hai ký tự theo quy ước ISO alpha-2',
    phone_number VARCHAR(32) NULL
        COMMENT 'Số điện thoại ở dạng văn bản, có thể gồm dấu + và ký tự phân cách',
    email VARCHAR(254) NOT NULL
        COMMENT 'Địa chỉ email liên hệ của khách hàng',
    display_name VARCHAR(150) NOT NULL
        COMMENT 'Tên hiển thị, có thể chứa ký tự Unicode',
    PRIMARY KEY (id),
    UNIQUE KEY uq_customer_contacts_email (email)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COMMENT='Thông tin liên hệ của khách hàng';
```

Thiết kế này dùng `CHAR(2)` cho mã quốc gia có độ dài cố định và `VARCHAR` cho các giá trị có độ dài thay đổi. `phone_number` được lưu dạng chuỗi vì số điện thoại không phải đại lượng dùng để tính toán; nó có thể có số 0 đầu, mã quốc gia, dấu cộng hoặc phần mở rộng.

`VARCHAR(254)` cho email là một giới hạn thiết kế thường dùng, nhưng validation cuối cùng phải theo chuẩn email và yêu cầu hệ thống. Nếu ứng dụng cho phép nhiều email có quy tắc so sánh đặc biệt, cần chọn collation hoặc chiến lược chuẩn hóa phù hợp trước khi tạo unique index.

## 14. Bài tập thực hành

1. Tạo bảng `fixed_codes` với `CHAR(2)` và `CHAR(3)` cho mã quốc gia, mã tiền tệ; chèn dữ liệu mẫu và đọc bằng `CHAR_LENGTH()`.
2. Tạo bảng `variable_texts` với `VARCHAR(30)`, `VARCHAR(100)`; chèn chuỗi ngắn, dài và chuỗi tiếng Việt.
3. So sánh `CHAR_LENGTH()` và `LENGTH()` cho cùng một chuỗi Unicode.
4. Thử lưu chuỗi có khoảng trắng cuối vào `CHAR` và `VARCHAR`; quan sát kết quả đọc lại và thử collation `PAD SPACE`/`NO PAD` phù hợp phiên bản.
5. Tạo unique index trên một cột `VARCHAR`, sau đó thử các giá trị khác nhau về chữ hoa/thường để hiểu ảnh hưởng của collation.
6. Dùng `SHOW CREATE TABLE` để kiểm tra charset, collation, độ dài và index.
7. Giải thích vì sao `CHAR(100)` thường không phải lựa chọn tốt cho tên người dùng nếu phần lớn tên ngắn hơn nhiều.
8. Đề xuất kiểu dữ liệu cho email, số điện thoại, mã tiền tệ, mã quốc gia, mã đơn hàng và tên sản phẩm; nêu rõ giả định về độ dài và charset.

## 15. Ghi nhớ

`CHAR(n)` phù hợp với giá trị có độ dài cố định và được đệm bên phải bằng dấu cách; khoảng trắng cuối thường được loại bỏ khi đọc. `VARCHAR(n)` lưu độ dài thực tế, giữ khoảng trắng cuối và thường phù hợp với văn bản có độ dài thay đổi. Cả hai khai báo độ dài theo ký tự, trong khi dung lượng byte phụ thuộc character set và metadata lưu độ dài.

Không có quy tắc rằng `CHAR` luôn nhanh hơn hoặc `VARCHAR` luôn tiết kiệm hơn trong mọi trường hợp. Hãy dựa vào độ dài dữ liệu thực tế, charset/collation, index, giới hạn hàng và workload. Dùng tên kiểu dữ liệu phản ánh đúng quy tắc nghiệp vụ, kiểm tra hành vi khoảng trắng và so sánh, validate đầu vào và đo hiệu năng trước khi tối ưu schema.
