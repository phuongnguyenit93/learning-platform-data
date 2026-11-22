# LOWER, UPPER và quan hệ với bộ ký tự/collation

## Mục tiêu

Sau bài này, bạn có thể:

- Dùng `LOWER()` và `UPPER()` để chuyển chữ hoa/chữ thường trong biểu thức SQL.
- Giải thích vai trò của character set đối với việc ánh xạ ký tự và vai trò riêng của collation đối với so sánh, sắp xếp.
- Phân biệt chuyển đổi chữ hoa/thường với so sánh không phân biệt hoa thường hoặc dấu.
- Nhận diện giới hạn khi xử lý Unicode, chuỗi nhị phân và dữ liệu đa ngôn ngữ.
- Tránh làm mất khả năng sử dụng index khi bọc cột bằng `LOWER()` hoặc `UPPER()`.
- Thiết kế collation, unique key và chuẩn hóa dữ liệu nhất quán giữa MySQL và ứng dụng Java.

## 1. LOWER() và UPPER() làm gì?

`LOWER(str)` chuyển các ký tự có dạng chữ hoa trong chuỗi thành chữ thường. `UPPER(str)` chuyển các ký tự có dạng chữ thường thành chữ hoa. Hai hàm trả về một chuỗi mới trong biểu thức; chúng không tự sửa giá trị đang lưu trong bảng.

Ví dụ cơ bản:

```sql
SELECT
    LOWER('MySQL Database') AS lower_value,
    UPPER('MySQL Database') AS upper_value;
```

Kết quả:

| lower_value | upper_value |
|---|---|
| `mysql database` | `MYSQL DATABASE` |

Với dữ liệu tiếng Việt:

```sql
SELECT
    LOWER('ĐẶNG THỊ ÁNH') AS vietnamese_lower,
    UPPER('đặng thị ánh') AS vietnamese_upper;
```

Kết quả mong đợi với charset Unicode phù hợp là `đặng thị ánh` và `ĐẶNG THỊ ÁNH`. Các ký tự không có dạng hoa/thường như dấu cách, chữ số và phần lớn dấu câu không thay đổi.

### 1.1. Dùng trong SELECT

Giả sử bảng `customers` có cột `full_name`:

```sql
SELECT
    customer_id,
    full_name,
    LOWER(full_name) AS name_lower,
    UPPER(full_name) AS name_upper
FROM customers;
```

Giá trị gốc vẫn giữ nguyên. `name_lower` và `name_upper` chỉ là kết quả biểu thức trong tập kết quả.

### 1.2. Dùng trong WHERE

```sql
SELECT customer_id, full_name
FROM customers
WHERE LOWER(full_name) = LOWER('nguyễn an');
```

Hàm chuyển hai vế về chữ thường trước khi so sánh. Tuy nhiên, kết quả so sánh vẫn chịu ảnh hưởng của collation gắn với biểu thức. `LOWER()` không tự loại bỏ dấu tiếng Việt và không biến mọi quy tắc Unicode thành một phép so sánh giống nhau.

## 2. Character set, collation và chuyển đổi chữ hoa/thường

Ba khái niệm này liên quan nhưng không đồng nghĩa:

- **Character set** quy định tập ký tự và cách biểu diễn ký tự thành byte. Ví dụ `utf8mb4` hỗ trợ Unicode với tối đa bốn byte cho một ký tự.
- **Collation** quy định cách so sánh và sắp xếp chuỗi thuộc character set, gồm quy tắc phân biệt hoa/thường và dấu.
- **LOWER()/UPPER()** thực hiện ánh xạ ký tự giữa dạng chữ thường và chữ hoa theo khả năng của character set/implementation.

`LOWER()` không phải là một collation. Collation không nhất thiết biến đổi dữ liệu lưu trữ; nó ảnh hưởng việc MySQL đánh giá hai chuỗi có bằng nhau hay không và thứ tự của chúng.

### 2.1. Kiểm tra charset và collation của biểu thức

MySQL cung cấp các hàm hỗ trợ quan sát:

```sql
SELECT
    CHARSET('Nguyễn An') AS literal_charset,
    COLLATION('Nguyễn An') AS literal_collation,
    CHARSET(LOWER('Nguyễn An')) AS lower_charset,
    COLLATION(LOWER('Nguyễn An')) AS lower_collation;
```

Literal chuỗi phụ thuộc charset/collation của kết nối và quy tắc literal. Với hàm `LOWER()`/`UPPER()`, kết quả chuỗi thông thường giữ character set và collation của đối số chuỗi. Hãy kiểm tra trên chính phiên bản và connection đang sử dụng nếu biểu thức có nhiều đối số hoặc có phép ép kiểu.

Có thể kiểm tra cột thực tế:

```sql
SELECT
    COLUMN_NAME,
    CHARACTER_SET_NAME,
    COLLATION_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customers'
  AND COLUMN_NAME = 'full_name';
```

Nếu dữ liệu tiếng Việt bị lưu sai encoding, gọi `LOWER()` hoặc `UPPER()` không thể khôi phục byte hay ký tự đã mất. Cần sửa nguồn encoding trước khi nghĩ tới chuẩn hóa chữ hoa/thường.

### 2.2. Ưu tiên utf8mb4 cho dữ liệu Unicode

Với schema mới, `utf8mb4` thường là lựa chọn phù hợp để lưu dữ liệu đa ngôn ngữ, gồm tiếng Việt và ký tự ngoài BMP. Tên `utf8` trong MySQL có lịch sử là bí danh cho `utf8mb3` ở nhiều phiên bản hiện đại; nó không biểu diễn toàn bộ Unicode. Hãy khai báo rõ `utf8mb4` thay vì dựa vào tên `utf8` mơ hồ.

Ví dụ:

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(150)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE = InnoDB;
```

`utf8mb4_0900_ai_ci` là collation UCA 9.0 phổ biến trên MySQL 8.0. Nó không có trên mọi phiên bản hoặc bản phân phối tương thích MySQL. Kiểm tra `SHOW COLLATION WHERE Charset = 'utf8mb4';` trước khi dùng; chọn collation được server mục tiêu hỗ trợ.

## 3. LOWER/UPPER không thay thế collation

Collation có thể đã thực hiện so sánh không phân biệt hoa/thường mà không cần gọi `LOWER()`.

Ví dụ:

```sql
SELECT
    'Alice' COLLATE utf8mb4_0900_ai_ci =
    'alice' COLLATE utf8mb4_0900_ai_ci AS same_ignoring_case,
    'a' COLLATE utf8mb4_0900_ai_ci =
    'á' COLLATE utf8mb4_0900_ai_ci AS same_ignoring_accent,
    'Alice' COLLATE utf8mb4_0900_as_cs =
    'alice' COLLATE utf8mb4_0900_as_cs AS same_case_sensitive;
```

Với các collation MySQL 8.0 được nêu:

- `utf8mb4_0900_ai_ci`: không phân biệt dấu (`ai`) và không phân biệt hoa/thường (`ci`).
- `utf8mb4_0900_as_cs`: phân biệt dấu (`as`) và phân biệt hoa/thường (`cs`).

Kết quả so sánh có thể là `1` hoặc `0` theo quy tắc collation. Tên và tính năng collation cần được xác minh trên server đang dùng.

### 3.1. LOWER không xóa dấu

```sql
SELECT
    LOWER('ÁNH') AS lower_with_accent,
    LOWER('ANH') AS lower_without_accent,
    LOWER('ÁNH') = LOWER('ANH') AS equal_under_current_collation;
```

Hai giá trị đầu là `ánh` và `anh`; hàm `LOWER()` vẫn giữ dấu. Biểu thức so sánh cuối cùng có thể trả về bằng nhau hoặc khác nhau tùy collation. Với collation accent-insensitive, chúng có thể được xem là bằng nhau; với accent-sensitive, chúng khác nhau.

### 3.2. UPPER không chuẩn hóa nội dung

`UPPER('đặng')` chuyển ký tự có dạng chữ thường sang dạng chữ hoa tương ứng, nhưng không xóa dấu, không bỏ dấu thanh, không tự sửa lỗi encoding và không biến chuỗi thành một dạng Unicode chuẩn hóa.

Ví dụ:

```sql
SELECT
    UPPER('đặng') AS uppercase_name,
    UPPER('a') = UPPER('á') AS equal_under_current_collation;
```

Giá trị chữ hoa vẫn có thể giữ dấu. Phép so sánh tiếp tục chịu ảnh hưởng của collation.

### 3.3. Chọn collation theo nghiệp vụ

| Nhu cầu | Cách thiết kế có thể phù hợp |
|---|---|
| Tìm tên người không phân biệt hoa/thường và dấu | Chọn collation `ai_ci` nếu nghiệp vụ muốn coi các khác biệt này là tương đương |
| Phân biệt dấu nhưng không phân biệt hoa/thường | Chọn collation `as_ci` nếu phiên bản có hỗ trợ |
| Phân biệt cả dấu và hoa/thường | Chọn collation `as_cs` |
| Mã/token cần so sánh chính xác | Cân nhắc collation nhị phân hoặc kiểu `VARBINARY`, tùy định dạng |
| Chỉ cần hiển thị chữ hoa/chữ thường | Dùng `UPPER()`/`LOWER()` trong biểu thức SELECT hoặc xử lý ở tầng trình bày |

Không dùng `LOWER()` để thay thế quyết định collation ở cấp schema. Nếu nhiều truy vấn cần cùng một quy tắc so sánh, khai báo collation phù hợp trên cột giúp hành vi nhất quán và thường cho phép dùng index trực tiếp.

## 4. Tác động với chuỗi tiếng Việt và Unicode

### 4.1. Chữ hoa/thường không giống bỏ dấu

Với tiếng Việt, chuyển đổi hoa/thường giữ các dấu thanh và dấu phụ:

```sql
SELECT
    LOWER('ĐIỆN TOÁN ĐÁM MÂY') AS lower_text,
    UPPER('điện toán đám mây') AS upper_text;
```

Ví dụ kết quả là `điện toán đám mây` và `ĐIỆN TOÁN ĐÁM MÂY`. Nếu mục tiêu tìm kiếm không dấu, `LOWER()` không đủ. Cần lựa chọn collation accent-insensitive hoặc xây dựng cột tìm kiếm đã chuẩn hóa theo quy tắc nghiệp vụ.

### 4.2. Unicode có thể có nhiều cách biểu diễn

Một ký tự nhìn giống nhau có thể được mã hóa theo dạng dựng sẵn (precomposed) hoặc dạng ký tự cơ sở cộng dấu kết hợp (combining mark). Ví dụ chữ `é` có thể là một code point hoặc là `e` cộng dấu sắc kết hợp. Hai chuỗi có thể trông giống nhau nhưng byte khác nhau.

`LOWER()` và `UPPER()` không phải hàm Unicode normalization như NFC/NFD. Collation Unicode có thể áp dụng quy tắc so sánh tương đương cho một số dạng, nhưng không nên giả định mọi cặp chuỗi tương đương về hiển thị đều được chuẩn hóa giống nhau trong mọi phiên bản.

Nếu hệ thống cần khóa định danh chuẩn hóa nhất quán, hãy xác định chính sách Unicode normalization/case folding ở tầng ứng dụng hoặc pipeline dữ liệu, lưu rõ phiên bản/quy tắc và kiểm thử bằng bộ dữ liệu đa ngôn ngữ.

### 4.3. Một số quy tắc ngôn ngữ đặc biệt

Không nên xem `LOWER()`/`UPPER()` là bộ xử lý ngôn ngữ hoàn chỉnh. Một số ngôn ngữ có quy tắc chuyển chữ phụ thuộc ngữ cảnh hoặc locale, ví dụ các biến thể của chữ I trong tiếng Thổ Nhĩ Kỳ. Mapping của MySQL phụ thuộc character set và implementation; nó không thay thế đầy đủ API locale-aware của ứng dụng.

Nếu nghiệp vụ cần chuyển chữ theo locale cụ thể, hãy xử lý bằng thư viện Unicode/locale ở tầng ứng dụng và kiểm thử với dữ liệu thật. Tránh dùng locale mặc định của máy chủ ứng dụng vì kết quả có thể khác giữa các môi trường.

## 5. Chuỗi nhị phân và LOWER/UPPER

`LOWER()` và `UPPER()` hoạt động trên chuỗi ký tự. Với chuỗi nhị phân (`BINARY`, `VARBINARY` hoặc biểu thức có character set `binary`), phép chuyển đổi hoa/thường không hoạt động như với chuỗi văn bản.

Ví dụ:

```sql
SELECT
    CHARSET(_binary 'ABC') AS binary_charset,
    LOWER(_binary 'ABC') AS lower_binary_value,
    LOWER(CONVERT(_binary 'ABC' USING utf8mb4)) AS lower_text_value;
```

Chuỗi `_binary 'ABC'` được xử lý như byte; muốn chuyển chữ, cần diễn giải byte thành chuỗi ký tự theo đúng encoding trước. `CONVERT(... USING utf8mb4)` chỉ đúng nếu byte nguồn thực sự là UTF-8. Nếu byte được mã hóa theo charset khác, phải dùng charset nguồn đúng; chuyển đổi sai có thể tạo ký tự rác hoặc mất dữ liệu.

Với token, hash, chữ ký, mật khẩu đã băm hoặc dữ liệu nhị phân, không ép sang văn bản và không gọi `LOWER()`/`UPPER()`. Những giá trị này thường cần so sánh chính xác theo byte.

## 6. Dùng LOWER/UPPER để trình bày và chuẩn hóa dữ liệu

### 6.1. Chỉ chuyển đổi trong kết quả SELECT

Nếu chỉ cần hiển thị tên theo chữ hoa hoặc chữ thường:

```sql
SELECT
    customer_id,
    UPPER(full_name) AS display_name_upper
FROM customers;
```

Không cần cập nhật dữ liệu gốc. Cách này giữ nguyên dữ liệu đã nhập và cho phép từng màn hình chọn định dạng phù hợp.

### 6.2. Cập nhật dữ liệu đã lưu

Nếu nghiệp vụ thật sự yêu cầu lưu giá trị chuẩn hóa, có thể cập nhật:

```sql
UPDATE customers
SET username = LOWER(username)
WHERE username IS NOT NULL;
```

Đây là thay đổi dữ liệu vĩnh viễn. Trước khi chạy cần:

1. Xác định quy tắc nghiệp vụ và phạm vi cột được phép chuẩn hóa.
2. Kiểm tra xem các giá trị khác nhau có trở thành trùng nhau sau chuyển đổi không.
3. Backup và thử trên bản sao.
4. Xác định tác động tới unique index, foreign key, cache và dữ liệu đồng bộ ở hệ thống khác.
5. Thực hiện theo batch/transaction phù hợp và đối soát sau cập nhật.

Kiểm tra collision trước khi cập nhật:

```sql
SELECT LOWER(username) AS normalized_username,
       COUNT(*) AS duplicate_count
FROM customers
WHERE username IS NOT NULL
GROUP BY LOWER(username)
HAVING COUNT(*) > 1;
```

Truy vấn này nhóm theo biểu thức `LOWER(username)` và collation của kết quả. Nếu quy tắc duy nhất cần phân biệt dấu hoặc có quy tắc Unicode riêng, hãy áp dụng đúng collation/normalization mong muốn trong phép kiểm tra.

Không cập nhật tất cả cột văn bản thành chữ thường chỉ để dữ liệu trông đồng nhất. Tên người, địa chỉ và nội dung tự do thường cần giữ nguyên kiểu viết do người dùng cung cấp.

## 7. Collation ảnh hưởng unique index như thế nào?

Unique index kiểm tra tính duy nhất theo quy tắc so sánh của collation trên cột ký tự. Với collation không phân biệt hoa/thường, các giá trị chỉ khác nhau về chữ hoa/thường có thể bị xem là trùng.

Ví dụ:

```sql
CREATE TABLE app_users (
    user_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    username VARCHAR(100)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci NOT NULL,
    PRIMARY KEY (user_id),
    UNIQUE KEY uq_app_users_username (username)
) ENGINE = InnoDB;

INSERT INTO app_users (username) VALUES ('Alice');

-- Có thể bị duplicate key vì collation không phân biệt hoa/thường
INSERT INTO app_users (username) VALUES ('alice');
```

Với collation `ai_ci`, khác biệt về dấu cũng có thể bị bỏ qua khi so sánh. Vì vậy, `Ánh` và `Anh` có thể xung đột trong unique index. Đây là quyết định nghiệp vụ, không phải lỗi của index.

Nếu cần phân biệt hoa/thường, chọn collation case-sensitive phù hợp trước khi tạo unique index. Nếu cần quy tắc riêng cho username, email hoặc mã định danh, hãy viết rõ chính sách canonicalization và so sánh. Không dựa vào việc gọi `LOWER()` trong một truy vấn để đảm bảo tính duy nhất ở mọi đường ghi.

### 7.1. Kiểm tra duplicate trước khi đổi collation

Trước khi chuyển một cột sang collation không phân biệt hoa/thường hoặc dấu, hãy tìm các giá trị sẽ trở thành tương đương:

```sql
SELECT
    username COLLATE utf8mb4_0900_ai_ci AS comparison_value,
    COUNT(*) AS duplicate_count
FROM app_users
GROUP BY comparison_value
HAVING COUNT(*) > 1;
```

Đây là ví dụ với collation MySQL 8.0. Nếu server không hỗ trợ collation đó, thay bằng collation mục tiêu thực tế. Với unique index ghép, phải kiểm tra đầy đủ các cột của khóa và cùng quy tắc collation.

## 8. LOWER/UPPER và khả năng sử dụng index

### 8.1. Không bọc cột bằng hàm nếu collation đã đáp ứng nhu cầu

Giả sử `username` đã dùng collation không phân biệt hoa/thường và có index:

```sql
CREATE INDEX idx_customers_username ON customers (username);
```

Truy vấn:

```sql
SELECT customer_id, username
FROM customers
WHERE username = 'ALICE';
```

đã được so sánh theo collation của cột. Nếu collation là case-insensitive, MySQL có thể tìm `Alice`, `ALICE` hoặc `alice` theo quy tắc collation mà vẫn sử dụng index thông thường.

Không cần viết:

```sql
SELECT customer_id, username
FROM customers
WHERE LOWER(username) = LOWER('ALICE');
```

Khi áp dụng hàm lên cột, index B-tree thông thường trên `username` thường không được dùng như một phép tra cứu trực tiếp theo giá trị cột. Điều này có thể khiến truy vấn phải quét nhiều hàng hơn.

### 8.2. Khi cần biểu thức LOWER, dùng functional index

Nếu cột có collation phân biệt hoa/thường nhưng ứng dụng thường xuyên cần tìm theo giá trị chữ thường, MySQL 8.0.13 trở lên hỗ trợ functional key parts:

```sql
CREATE INDEX idx_customers_lower_name
ON customers ((LOWER(full_name)));
```

Truy vấn dùng cùng biểu thức:

```sql
SELECT customer_id, full_name
FROM customers
WHERE LOWER(full_name) = LOWER('Nguyễn An');
```

Functional index lưu key được tính từ biểu thức. Optimizer chỉ có thể tận dụng index khi biểu thức trong truy vấn phù hợp với định nghĩa index và các điều kiện kiểu dữ liệu/collation tương thích. Hãy kiểm tra bằng `EXPLAIN`; không giả định cứ tạo index là mọi cách viết truy vấn đều dùng được.

Functional index cần phiên bản MySQL hỗ trợ. Với phiên bản cũ hơn, có thể dùng generated column rồi tạo index trên cột đó.

### 8.3. Generated column làm khóa chuẩn hóa

Ví dụ:

```sql
ALTER TABLE customers
    ADD COLUMN full_name_lower VARCHAR(150)
        GENERATED ALWAYS AS (LOWER(full_name)) STORED,
    ADD INDEX idx_customers_full_name_lower (full_name_lower);
```

Truy vấn:

```sql
SELECT customer_id, full_name
FROM customers
WHERE full_name_lower = LOWER('Nguyễn An');
```

Generated column được MySQL tính từ `full_name`; ứng dụng không tự ghi giá trị vào cột sinh này. Charset/collation của cột sinh và biểu thức cần được kiểm tra bằng `SHOW CREATE TABLE` và `information_schema.COLUMNS`. Nếu cần collation cụ thể, khai báo rõ trong định nghĩa generated column sau khi xác minh phiên bản và khả năng tương thích.

### 8.4. Đo kế hoạch thực thi

So sánh hai dạng truy vấn:

```sql
EXPLAIN
SELECT customer_id
FROM customers
WHERE username = 'ALICE';

EXPLAIN
SELECT customer_id
FROM customers
WHERE LOWER(username) = LOWER('ALICE');
```

Quan sát `key`, `type`, số hàng ước lượng và điều kiện lọc. Kết quả phụ thuộc dữ liệu, thống kê, collation và phiên bản; không kết luận chỉ từ cú pháp. Nếu cần, cập nhật thống kê bằng `ANALYZE TABLE` trong môi trường phù hợp rồi đo lại.

## 9. LOWER/UPPER trong GROUP BY, DISTINCT và ORDER BY

### 9.1. Nhóm theo chữ thường

```sql
SELECT
    LOWER(username) AS normalized_username,
    COUNT(*) AS user_count
FROM app_users
GROUP BY LOWER(username);
```

Truy vấn nhóm theo kết quả biểu thức. Tuy nhiên, collation của kết quả vẫn ảnh hưởng việc các chuỗi được xem là bằng nhau. Nếu collation không phân biệt dấu, hai giá trị khác dấu có thể nằm cùng nhóm dù `LOWER()` không xóa dấu.

### 9.2. Loại bỏ trùng theo biểu thức

```sql
SELECT DISTINCT LOWER(full_name) AS lower_name
FROM customers
ORDER BY lower_name;
```

`DISTINCT` so sánh theo collation của biểu thức. Nếu mục tiêu là tạo danh sách tên duy nhất theo quy tắc nghiệp vụ, phải xác định cả case sensitivity và accent sensitivity.

### 9.3. Sắp xếp theo dạng chữ thường

```sql
SELECT customer_id, full_name
FROM customers
ORDER BY LOWER(full_name), customer_id;
```

Thêm khóa duy nhất làm tie-breaker nếu cần thứ tự ổn định. Sắp xếp theo biểu thức có thể cần filesort hoặc functional index tùy kế hoạch thực thi. Nếu collation cột đã cung cấp thứ tự không phân biệt hoa/thường mong muốn, có thể `ORDER BY full_name` là đủ và tận dụng index tốt hơn.

## 10. Tích hợp với Java và JDBC

Java có các phương thức `String.toLowerCase()` và `String.toUpperCase()`. Nếu dùng chúng, hãy chú ý locale mặc định của JVM:

```java
String lowerDefaultLocale = value.toLowerCase();
String lowerRootLocale = value.toLowerCase(Locale.ROOT);
String upperRootLocale = value.toUpperCase(Locale.ROOT);
```

Với quy tắc chuẩn hóa kỹ thuật không phụ thuộc ngôn ngữ giao diện, `Locale.ROOT` thường an toàn hơn locale mặc định của máy chạy ứng dụng. Tuy nhiên, `Locale.ROOT` không đồng nghĩa với Unicode case folding hoặc normalization hoàn chỉnh. Nếu nghiệp vụ yêu cầu xử lý ngôn ngữ cụ thể, hãy chọn locale/Unicode library rõ ràng.

Không nên chuẩn hóa cùng một định danh ở Java theo một quy tắc, nhưng lại dùng collation MySQL theo quy tắc khác. Điều đó có thể khiến ứng dụng coi hai giá trị là khác nhau trong khi unique index coi chúng là trùng, hoặc ngược lại.

### 10.1. Dùng collation để tìm kiếm, không cần chuyển chữ ở Java

Nếu cột đã có collation không phân biệt hoa/thường, có thể truyền giá trị tìm kiếm nguyên bản bằng prepared statement:

```java
String sql = "SELECT customer_id, username "
           + "FROM customers WHERE username = ?";

try (var statement = connection.prepareStatement(sql)) {
    statement.setString(1, inputUsername);
    try (var result = statement.executeQuery()) {
        while (result.next()) {
            long customerId = result.getLong("customer_id");
            String username = result.getString("username");
        }
    }
}
```

Collation của column quyết định cách so sánh. Prepared statement tách giá trị khỏi cấu trúc SQL và giúp tránh nối chuỗi truy vấn từ đầu vào người dùng.

### 10.2. Không áp dụng LOWER cho thông tin bí mật

Không chuyển mật khẩu, password hash, API key, token, chữ ký hoặc dữ liệu mã hóa sang chữ thường/chữ hoa. Những giá trị này thường phân biệt từng byte; biến đổi chúng làm thay đổi giá trị và có thể phá hỏng xác thực hoặc kiểm tra chữ ký.

## 11. Các lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ LOWER() loại bỏ dấu | Tìm kiếm tiếng Việt không dấu vẫn không đúng như mong muốn | Chọn collation accent-insensitive hoặc chuẩn hóa riêng theo nghiệp vụ |
| Nghĩ collation ci tự đổi dữ liệu thành chữ thường | Dữ liệu gốc vẫn giữ cách viết ban đầu | Dùng LOWER/UPPER khi cần biểu diễn hoặc lưu dạng chuẩn hóa |
| Dùng LOWER(column) dù collation đã ci | Có thể làm mất khả năng dùng index thường | So sánh trực tiếp `column = ?` |
| Dùng LOWER trên BINARY/VARBINARY | Không có ánh xạ chữ như chuỗi văn bản | Chuyển byte sang đúng charset trước nếu dữ liệu thật sự là text |
| Chuyển toàn bộ tên người sang chữ hoa/thường | Mất cách viết do người dùng cung cấp | Chỉ chuẩn hóa các trường có quy tắc nghiệp vụ rõ |
| Dùng LOWER để bảo đảm unique | Các đường ghi khác có thể bỏ qua quy tắc; collation có thể tạo collision khác dự kiến | Dùng unique index với collation đúng và kiểm tra duplicate trước |
| Dùng Java locale mặc định | Kết quả có thể khác giữa máy chủ | Chọn `Locale.ROOT` hoặc locale nghiệp vụ tường minh |
| Xem LOWER/UPPER là Unicode normalization | Chuỗi nhìn giống nhau có thể vẫn có biểu diễn khác | Áp dụng normalization/case folding rõ ràng ở tầng phù hợp |

## 12. Bộ truy vấn kiểm tra nhanh

```sql
-- Quan sát kết quả chuyển đổi
SELECT
    LOWER('ĐẶNG THỊ ÁNH') AS lower_vietnamese,
    UPPER('đặng thị ánh') AS upper_vietnamese;

-- Quan sát charset/collation của biểu thức
SELECT
    CHARSET('Nguyễn An') AS input_charset,
    COLLATION('Nguyễn An') AS input_collation,
    CHARSET(LOWER('Nguyễn An')) AS lower_charset,
    COLLATION(LOWER('Nguyễn An')) AS lower_collation;

-- So sánh phụ thuộc collation
SELECT
    'Alice' COLLATE utf8mb4_0900_ai_ci =
    'alice' COLLATE utf8mb4_0900_ai_ci AS case_insensitive_equal,
    'a' COLLATE utf8mb4_0900_ai_ci =
    'á' COLLATE utf8mb4_0900_ai_ci AS accent_insensitive_equal,
    'Alice' COLLATE utf8mb4_0900_as_cs =
    'alice' COLLATE utf8mb4_0900_as_cs AS case_sensitive_equal;

-- Kiểm tra collation thực tế của cột
SELECT COLUMN_NAME, CHARACTER_SET_NAME, COLLATION_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customers'
  AND COLUMN_NAME = 'full_name';

-- Tìm các giá trị trùng sau khi chuyển thành chữ thường
SELECT LOWER(username) AS normalized_username,
       COUNT(*) AS duplicate_count
FROM app_users
GROUP BY LOWER(username)
HAVING COUNT(*) > 1;
```

Các collation `utf8mb4_0900_*` trong ví dụ yêu cầu MySQL 8.0 có hỗ trợ tương ứng. Nếu dùng phiên bản khác, thay bằng collation đã xác minh qua `SHOW COLLATION`. Những truy vấn dùng tên bảng/cột `customers` và `app_users` là ví dụ, cần thay bằng schema thực tế.

## 13. Checklist thiết kế và sử dụng

- [ ] Cột văn bản dùng character set phù hợp, thường là `utf8mb4` cho dữ liệu Unicode mới.
- [ ] Collation được chọn theo yêu cầu phân biệt hoa/thường và dấu.
- [ ] Đã phân biệt rõ chuyển đổi chữ bằng LOWER/UPPER với quy tắc so sánh của collation.
- [ ] Đã kiểm tra kết quả trên tiếng Việt và dữ liệu Unicode thực tế.
- [ ] Không dùng LOWER/UPPER trên dữ liệu nhị phân, token hoặc hash.
- [ ] Không bọc cột bằng hàm nếu collation đã đáp ứng tìm kiếm và cần tận dụng index thường.
- [ ] Nếu cần index trên biểu thức, đã kiểm tra functional index hoặc generated column phù hợp phiên bản.
- [ ] Đã kiểm tra duplicate trước khi đổi collation hoặc chuẩn hóa dữ liệu.
- [ ] Quy tắc chuẩn hóa ở Java và MySQL thống nhất, có locale/version rõ ràng.
- [ ] Không biến đổi dữ liệu tên người hoặc nội dung tự do nếu không có yêu cầu nghiệp vụ.

## 14. Kết luận

`LOWER()` và `UPPER()` chuyển dạng chữ của chuỗi; character set cung cấp khả năng biểu diễn và ánh xạ ký tự; collation quyết định cách so sánh và sắp xếp. Chuyển một chuỗi thành chữ thường không đồng nghĩa với bỏ dấu, Unicode normalization hoặc so sánh không phân biệt hoa/thường.

Hãy chọn `utf8mb4` và collation theo nghiệp vụ, tận dụng collation để so sánh khi phù hợp, và chỉ dùng LOWER/UPPER khi thật sự cần biến đổi biểu diễn. Với truy vấn lớn, chú ý index khi bọc cột bằng hàm; với định danh, unique key và ứng dụng Java, bảo đảm quy tắc chuẩn hóa được xác định nhất quán trước khi triển khai.
