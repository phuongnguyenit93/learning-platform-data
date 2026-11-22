# Sắp xếp và tìm kiếm tiếng Việt theo yêu cầu nghiệp vụ

Một ứng dụng quản lý khách hàng cần sắp xếp tên theo thứ tự tiếng Việt, tìm khách hàng khi người dùng gõ thiếu dấu, nhưng vẫn phải phân biệt chính xác những tên khác nhau khi kiểm tra trùng lặp. Một cửa hàng trực tuyến lại cần tìm sản phẩm không phân biệt hoa/thường, trong khi mã SKU phải được so sánh chính xác. Các yêu cầu này không thể giải quyết bằng một quy tắc so sánh duy nhất cho mọi cột.

Trong MySQL, **character set** quyết định cách mã hóa ký tự; **collation** quyết định cách so sánh và sắp xếp chuỗi thuộc character set đó. Muốn xử lý tiếng Việt đúng, cần xác định nghiệp vụ cần phân biệt dấu hay không, cần phân biệt hoa/thường hay không, cần thứ tự từ điển tiếng Việt hay chỉ cần so sánh Unicode tổng quát. Sau đó mới chọn collation, thiết kế chỉ mục và xây dựng cách tìm kiếm tương ứng.

## 1. Character set và collation khác nhau thế nào?

### 1.1. Character set: ký tự được mã hóa ra sao?

Character set (bộ ký tự) xác định tập ký tự và cách biểu diễn chúng thành byte. Với dữ liệu tiếng Việt hiện đại, nên dùng `utf8mb4` để lưu đầy đủ Unicode, bao gồm chữ có dấu, ký tự mở rộng và emoji.

Trong MySQL, tên `utf8` trước đây là alias của `utf8mb3`, chỉ hỗ trợ tối đa ba byte cho một ký tự Unicode. `utf8mb4` hỗ trợ tối đa bốn byte và là lựa chọn nên dùng cho schema mới. Đừng chọn `utf8` chỉ vì tên có vẻ tương đương UTF-8 của Unicode.

Ví dụ, chuỗi `Tiếng Việt – Đặng` cần được truyền qua client, connection và cột bằng character set tương thích. Nếu client gửi byte UTF-8 nhưng connection diễn giải theo character set khác, dữ liệu có thể bị lỗi ngay cả khi cột đích dùng `utf8mb4`.

### 1.2. Collation: chuỗi được so sánh và sắp xếp thế nào?

Collation là tập quy tắc so sánh chuỗi trong một character set. Nó ảnh hưởng đến:

- So sánh bằng `=`, `<>`, `IN` và các phép so sánh chuỗi khác.
- Sắp xếp bằng `ORDER BY`, `GROUP BY` và `DISTINCT`.
- Tìm kiếm bằng `LIKE` và một số phép so sánh chuỗi trong biểu thức.
- Tính duy nhất của `UNIQUE INDEX`, vì hai chuỗi được xem là bằng nhau theo collation có thể không cùng byte.
- Khả năng sử dụng index khi truy vấn dùng collation tương thích với index của cột.

Ví dụ, một collation không phân biệt hoa/thường có thể xem `An` và `AN` là bằng nhau. Một collation không phân biệt dấu có thể xem `hoa` và `hòa` là bằng nhau trong một phép so sánh nhất định. Điều này có thể hữu ích cho tìm kiếm rộng, nhưng gây lỗi nghiệp vụ nếu áp dụng cho khóa định danh hoặc tên cần phân biệt dấu.

Character set và collation có thể được đặt ở cấp server, database, table, column, connection hoặc expression. Mỗi cấp có quy tắc mặc định và kế thừa riêng; khi cần kết quả chắc chắn, hãy kiểm tra collation thực tế của cột và biểu thức thay vì chỉ nhìn cấu hình server.

## 2. Những khác biệt quan trọng khi xử lý tiếng Việt

### 2.1. Dấu thanh và dấu của nguyên âm làm thay đổi nghĩa

Tiếng Việt sử dụng các dấu thanh và nhiều chữ cái có dấu. Các chuỗi dưới đây là những từ khác nhau về nghĩa:

| Chuỗi | Khác biệt |
|---|---|
| `ma` | Không dấu |
| `má` | Sắc |
| `mà` | Huyền |
| `mả` | Hỏi |
| `mã` | Ngã |
| `mạ` | Nặng |
| `a`, `ă`, `â` | Các chữ cái khác nhau trong bảng chữ cái tiếng Việt |
| `d`, `đ` | Hai chữ cái khác nhau |

Một tìm kiếm không phân biệt dấu có thể giúp người dùng gõ `Nguyen` vẫn tìm thấy `Nguyễn`. Nhưng nếu dùng cùng collation cho so sánh duy nhất, hệ thống có thể coi các giá trị mà nghiệp vụ cần phân biệt là trùng nhau. Cần thử cả dấu thanh, dấu nguyên âm và chữ `đ`; không suy luận toàn bộ hành vi chỉ từ tên collation.

### 2.2. Hoa/thường là một yêu cầu riêng

Tên người thường cần so sánh không phân biệt hoa/thường: `NGUYỄN AN`, `Nguyễn An` và `nguyễn an` có thể được xem là cùng một tên để tìm kiếm. Tuy nhiên, nội dung hiển thị vẫn nên giữ nguyên cách viết người dùng đã nhập.

Mã định danh, mã SKU hoặc token có thể cần phân biệt hoa/thường. Ví dụ `sku-a1` và `SKU-A1` có thể là hai mã khác nhau nếu quy ước hệ thống quy định như vậy. Không dùng collation của tên người cho mọi cột chuỗi.

### 2.3. Thứ tự từ điển không giống thứ tự byte

Sắp xếp chuỗi theo byte UTF-8 không tạo ra thứ tự từ điển tiếng Việt. Collation Unicode sử dụng trọng số so sánh (weight) để xác định thứ tự. Collation có tailoring theo ngôn ngữ có thể điều chỉnh thứ tự chữ cái phù hợp hơn với quy tắc của ngôn ngữ đó.

Nếu nghiệp vụ yêu cầu danh sách tên theo thứ tự từ điển tiếng Việt, hãy chọn collation tiếng Việt nếu server cung cấp và kiểm thử với bộ dữ liệu có đủ `a`, `ă`, `â`, `d`, `đ`, `e`, `ê`, `o`, `ô`, `ơ`, `u`, `ư` cùng các dấu thanh. Một collation Unicode tổng quát có thể so sánh đúng theo quy tắc Unicode của nó nhưng chưa chắc tạo ra thứ tự mà người dùng Việt Nam mong đợi.

## 3. Khám phá character set và collation đang có

Không nên đoán collation được cài trên server. Trước tiên hãy truy vấn danh sách hỗ trợ:

```sql
SHOW CHARACTER SET LIKE 'utf8mb4';

SHOW COLLATION LIKE 'utf8mb4%';

SHOW COLLATION LIKE '%vietnamese%';

SHOW COLLATION LIKE 'utf8mb4_vi_0900%';
```

Có thể truy vấn metadata:

```sql
SELECT
    COLLATION_NAME,
    CHARACTER_SET_NAME,
    IS_DEFAULT,
    IS_COMPILED,
    SORTLEN
FROM INFORMATION_SCHEMA.COLLATIONS
WHERE CHARACTER_SET_NAME = 'utf8mb4'
ORDER BY COLLATION_NAME;
```

Để kiểm tra cấu hình ở các cấp:

```sql
SHOW VARIABLES LIKE 'character_set%';
SHOW VARIABLES LIKE 'collation%';
```

Một số biến cần chú ý:

| Biến | Ý nghĩa |
|---|---|
| `character_set_server` | Character set mặc định cấp server |
| `collation_server` | Collation mặc định cấp server |
| `character_set_database` | Character set mặc định của database hiện tại (cách sử dụng biến này phụ thuộc phiên bản) |
| `collation_database` | Collation mặc định của database hiện tại |
| `character_set_client` | Character set mà client dùng để gửi câu lệnh |
| `character_set_connection` | Character set MySQL dùng khi xử lý chuỗi đầu vào của câu lệnh |
| `character_set_results` | Character set dùng để trả kết quả về client |
| `collation_connection` | Collation dùng cho biểu thức chuỗi theo connection |

Để xem thuộc tính thực tế của một biểu thức:

```sql
SELECT
    CHARSET('Tiếng Việt'),
    COLLATION('Tiếng Việt'),
    CHARSET(_utf8mb4'Đặng'),
    COLLATION(_utf8mb4'Đặng');
```

`CHARSET()` và `COLLATION()` giúp xác định cách MySQL diễn giải biểu thức. Với cột đã tạo, dùng `SHOW FULL COLUMNS` hoặc `INFORMATION_SCHEMA.COLUMNS` để kiểm tra charset/collation riêng của cột.

## 4. Hiểu hậu tố collation

Trong nhiều collation Unicode của MySQL 8.0, tên có các hậu tố biểu thị độ nhạy:

| Hậu tố | Ý nghĩa |
|---|---|
| `ai` | Accent-insensitive: bỏ qua một số khác biệt dấu theo quy tắc collation |
| `as` | Accent-sensitive: phân biệt khác biệt dấu |
| `ci` | Case-insensitive: không phân biệt hoa/thường |
| `cs` | Case-sensitive: phân biệt hoa/thường |
| `bin` | So sánh theo giá trị nhị phân của ký tự/byte theo collation binary |

Ví dụ thường gặp trong MySQL 8.0:

- `utf8mb4_0900_ai_ci`: không phân biệt dấu và hoa/thường.
- `utf8mb4_0900_as_ci`: phân biệt dấu, không phân biệt hoa/thường.
- `utf8mb4_0900_as_cs`: phân biệt dấu và hoa/thường.
- `utf8mb4_0900_ai_cs`: không phân biệt dấu, phân biệt hoa/thường.

Nhóm `0900` dựa trên Unicode Collation Algorithm 9.0 và có trong MySQL 8.0 trở lên. Với các collation không nhị phân, nếu tên không ghi rõ `_ai` hoặc `_as`, hậu tố `_ci` ngụ ý accent-insensitive và `_cs` ngụ ý accent-sensitive. Tuy nhiên, quy tắc tailoring theo ngôn ngữ và phiên bản UCA vẫn có thể làm kết quả khác nhau; hãy kiểm tra trên đúng server.

MySQL 8.0 có collation tiếng Việt theo UCA 9.0 như `utf8mb4_vi_0900_ai_ci` (không phân biệt dấu và hoa/thường) và `utf8mb4_vi_0900_as_cs` (phân biệt dấu và hoa/thường). Một số bản còn có collation cũ `utf8mb4_vietnamese_ci`; đây là lựa chọn dựa trên bộ quy tắc Unicode cũ hơn. Đặc biệt, các collation Unicode dựa trên UCA 4.0 như `utf8mb4_unicode_ci` có hỗ trợ chưa đầy đủ cho combining marks; điều này ảnh hưởng đến tiếng Việt khi một chữ có dấu được biểu diễn bằng ký tự dựng sẵn hoặc ký tự cơ sở kết hợp dấu. Ưu tiên collation `vi_0900` khi có thể và chuẩn hóa Unicode nhất quán.

Nếu cần phân biệt dấu nhưng không phân biệt hoa/thường, collation tổng quát `utf8mb4_0900_as_ci` là một lựa chọn cần thử nghiệm; nếu cần tailoring tiếng Việt và chấp nhận phân biệt hoa/thường, có thể thử `utf8mb4_vi_0900_as_cs`. Không có một lựa chọn duy nhất đáp ứng mọi tổ hợp yêu cầu. Nếu server không có collation phù hợp, hãy cân nhắc tạo sort key riêng bằng thư viện locale-aware ở tầng ứng dụng.

## 5. Chọn collation theo mục tiêu nghiệp vụ

Không có một collation tối ưu cho tất cả tình huống. Hãy tách ít nhất ba câu hỏi: cần sắp xếp thế nào, cần tìm kiếm rộng đến đâu và quy tắc trùng lặp là gì.

| Nghiệp vụ | Yêu cầu thường gặp | Hướng chọn |
|---|---|---|
| Sắp xếp tên tiếng Việt | Thứ tự từ điển phù hợp tiếng Việt, giữ dấu | Thử `utf8mb4_vi_0900_as_cs` trên MySQL 8.0; kiểm thử thứ tự chữ và tên thực tế |
| Tìm tên có dấu chính xác | Không phân biệt hoa/thường nhưng phân biệt dấu | Collation accent-sensitive, case-insensitive như `utf8mb4_0900_as_ci` nếu phù hợp phiên bản |
| Tìm tên không dấu | Chấp nhận bỏ qua dấu để tìm rộng | Collation accent-insensitive hoặc cột tìm kiếm chuẩn hóa riêng; đánh giá false positive |
| Mã SKU/token | Thường cần so sánh chính xác | Collation binary hoặc quy tắc chuẩn hóa chữ hoa/thường rõ ràng |
| Email/tài khoản | Phụ thuộc chính sách định danh | Xác định rõ quy tắc hoa/thường, dấu và unique key; không tự động bỏ dấu tiếng Việt |
| Tìm kiếm nội dung dài | Tìm từ khóa, nhiều từ và xếp hạng | FULLTEXT hoặc hệ thống tìm kiếm chuyên dụng, sau khi thử tokenization tiếng Việt |

### 5.1. Tên người: phân biệt dấu nhưng bỏ qua hoa/thường

Với tên người, thường nên giữ dấu là khác biệt có ý nghĩa. Có thể chọn collation accent-sensitive, case-insensitive:

```sql
CREATE TABLE customers (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(200)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_as_ci NOT NULL,
    PRIMARY KEY (id),
    KEY idx_full_name (full_name)
) ENGINE=InnoDB;
```

Collation này là ví dụ cho MySQL 8.0. Nếu yêu cầu thứ tự từ điển tiếng Việt, hãy đánh giá collation tiếng Việt sẵn có trên server và dùng collation đó nếu nó đáp ứng cả so sánh lẫn sắp xếp mà ứng dụng cần.

### 5.2. Tìm kiếm không dấu

Một cách đơn giản là dùng collation accent-insensitive cho biểu thức tìm kiếm:

```sql
SELECT id, full_name
FROM customers
WHERE full_name COLLATE utf8mb4_0900_ai_ci =
      _utf8mb4'Nguyen An' COLLATE utf8mb4_0900_ai_ci;
```

Kết quả có thể bao gồm các tên có dấu tương ứng theo quy tắc của collation. Tuy nhiên, với tiếng Việt, bỏ qua dấu có thể trả về nhiều tên khác nghĩa. Nếu người dùng cần tìm `ma` nhưng không muốn kết quả `má`, `mà`, `mả`, `mã`, `mạ`, không dùng accent-insensitive cho yêu cầu đó.

Một thiết kế rõ ràng hơn là giữ `full_name` nguyên bản và có thêm cột tìm kiếm đã chuẩn hóa do ứng dụng tạo. Quy tắc chuẩn hóa phải được định nghĩa cụ thể: chuyển chữ thường, bỏ dấu thanh hay bỏ mọi dấu, xử lý `đ` ra sao, chuẩn hóa khoảng trắng và Unicode form như thế nào. Không có một phép bỏ dấu duy nhất phù hợp mọi nghiệp vụ.

Ví dụ mô hình:

```sql
CREATE TABLE customer_search (
    customer_id BIGINT UNSIGNED NOT NULL,
    full_name VARCHAR(200)
        CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_as_ci NOT NULL,
    search_key VARCHAR(200)
        CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci NOT NULL,
    PRIMARY KEY (customer_id),
    KEY idx_search_key (search_key)
) ENGINE=InnoDB;
```

`search_key` được ứng dụng tạo theo quy tắc đã thống nhất và cập nhật cùng transaction với tên gốc. Có thể giữ nhiều khóa tìm kiếm nếu cần các chế độ khác nhau, ví dụ tìm có dấu và tìm không dấu. Cần đo chiều dài sau chuẩn hóa để tránh cột bị cắt cụt.

### 5.3. Mã định danh và khóa duy nhất

Với mã SKU, mã hồ sơ hoặc token, quyết định rõ chữ hoa và chữ thường có tương đương hay không. Nếu mã phải phân biệt chính xác, có thể dùng collation binary hoặc lưu dạng byte phù hợp. Nếu mã không phân biệt hoa/thường, chuẩn hóa về một dạng (ví dụ uppercase ASCII) ở tầng ứng dụng và đặt unique index trên giá trị chuẩn hóa.

Đừng dùng collation accent-insensitive cho mọi unique key. Một unique index trên cột tên với collation không phân biệt dấu có thể từ chối hai tên mà nghiệp vụ cần lưu riêng. Trước khi đổi collation, luôn kiểm tra các giá trị hiện có có trở thành trùng theo quy tắc mới không.

## 6. Sắp xếp tên tiếng Việt trong MySQL

### 6.1. ORDER BY dùng collation của biểu thức

Ví dụ sắp xếp tên:

```sql
SELECT id, full_name
FROM customers
ORDER BY full_name, id;
```

MySQL dùng collation của `full_name` để so sánh và sắp xếp. Thêm `id` làm tiêu chí phụ để kết quả có thứ tự xác định khi nhiều tên có cùng trọng số collation. Điều này đặc biệt quan trọng khi phân trang.

Nếu muốn thử một collation khác mà chưa thay đổi định nghĩa cột:

```sql
SELECT id, full_name
FROM customers
ORDER BY full_name COLLATE utf8mb4_0900_as_ci, id;
```

Đây là cách kiểm nghiệm thứ tự, nhưng không nên lạm dụng `COLLATE` tùy ý trong mọi truy vấn production. Nếu cột được index bằng collation khác, biểu thức đổi collation có thể khiến index hiện có không đáp ứng trực tiếp thứ tự hoặc điều kiện lọc.

### 6.2. Kiểm thử thứ tự tiếng Việt

Tạo tập dữ liệu nhỏ có các trường hợp dễ nhầm:

```sql
CREATE TEMPORARY TABLE vietnamese_sort_test (
    value VARCHAR(80)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_as_ci
);

INSERT INTO vietnamese_sort_test (value) VALUES
    ('An'), ('Ân'), ('Ăn'), ('Ba'), ('Bà'), ('Bá'),
    ('Da'), ('Đa'), ('Dung'), ('Dũng'),
    ('Hoa'), ('Hòa'), ('Huệ'), ('Hương'), ('Ưng');

SELECT value
FROM vietnamese_sort_test
ORDER BY value;
```

Chạy lại truy vấn với collation tiếng Việt nếu server cung cấp:

```sql
SELECT value
FROM vietnamese_sort_test
ORDER BY value COLLATE utf8mb4_vi_0900_as_cs;
```

So sánh kết quả với thứ tự nghiệp vụ mà sản phẩm yêu cầu. Bộ dữ liệu kiểm thử nên có đủ chữ cái đặc biệt, dấu thanh, chữ hoa/thường, tên trùng trọng số và chuỗi có khoảng trắng. Không chỉ kiểm tra vài tên phổ biến rồi kết luận collation phù hợp.

### 6.3. Thứ tự ổn định khi phân trang

Nếu hai tên được collation xem là bằng nhau, `ORDER BY full_name` không bảo đảm thứ tự tương đối giữa chúng. Dùng thêm khóa duy nhất:

```sql
SELECT id, full_name
FROM customers
ORDER BY full_name, id
LIMIT 50 OFFSET 100;
```

Với bảng lớn và phân trang sâu, có thể dùng keyset pagination theo cặp `(full_name, id)`. Cần bảo đảm điều kiện tiếp trang sử dụng cùng collation và cùng thứ tự với `ORDER BY`; nếu không, có thể bỏ sót hoặc lặp hàng.

## 7. Tìm kiếm tiếng Việt bằng LIKE và phép so sánh

### 7.1. Tìm chính xác và tìm tiền tố

Tìm bằng `=` hoặc `LIKE` chịu ảnh hưởng bởi collation của biểu thức. Ví dụ:

```sql
-- So sánh theo collation của cột.
SELECT id, full_name
FROM customers
WHERE full_name = 'Nguyễn An';

-- Tìm theo tiền tố.
SELECT id, full_name
FROM customers
WHERE full_name LIKE 'Nguyễn%';
```

Nếu collation của cột không phân biệt hoa/thường, các biến thể chữ hoa/thường có thể khớp. Nếu collation không phân biệt dấu, biến thể có dấu có thể khớp cả từ khóa không dấu. Hãy kiểm tra bằng dữ liệu thực tế trước khi công bố hành vi tìm kiếm cho người dùng.

### 7.2. Tìm chứa chuỗi và giới hạn của B-tree

```sql
SELECT id, full_name
FROM customers
WHERE full_name LIKE '%An%';
```

Mẫu bắt đầu bằng `%` thường không thể dùng B-tree index để định vị phần đầu của chuỗi, nên có thể phải quét nhiều hàng. Với mẫu tiền tố như `'Nguyễn%'`, MySQL có thể dùng index nếu collation, kiểu dữ liệu và điều kiện phù hợp.

Không bọc cột trong hàm như `LOWER(full_name)` nếu muốn dùng index thông thường, trừ khi đã thiết kế functional index hoặc generated column tương ứng. Tốt hơn là chọn collation không phân biệt hoa/thường ngay trên cột khi đó là quy tắc nghiệp vụ.

### 7.3. Khoảng trắng và dấu câu

Một số collation có quy tắc xử lý khoảng trắng cuối chuỗi (PAD SPACE hoặc NO PAD) và dấu câu khác nhau. Vì vậy, `name = 'An'` có thể có hành vi khác với so sánh byte chính xác. Hãy kiểm tra thuộc tính collation và thử các trường hợp như `'An'`, `'An '` và chuỗi có nhiều khoảng trắng khi nghiệp vụ yêu cầu so khớp chính xác.

Nếu khoảng trắng không có ý nghĩa, hãy chuẩn hóa khoảng trắng ở tầng ứng dụng trước khi lưu. Đừng dựa vào hành vi ngầm của collation để chuẩn hóa dữ liệu.

## 8. Tìm kiếm nội dung dài bằng FULLTEXT

Với cột mô tả sản phẩm, bài viết hoặc nội dung hỗ trợ, tìm kiếm theo từ khóa có thể phù hợp với FULLTEXT index:

```sql
CREATE TABLE articles (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    title VARCHAR(250) NOT NULL,
    body MEDIUMTEXT NOT NULL,
    PRIMARY KEY (id),
    FULLTEXT KEY ft_title_body (title, body)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4;
```

Tìm theo natural language mode:

```sql
SELECT
    id,
    title,
    MATCH(title, body) AGAINST ('cơ sở dữ liệu MySQL' IN NATURAL LANGUAGE MODE) AS score
FROM articles
WHERE MATCH(title, body)
      AGAINST ('cơ sở dữ liệu MySQL' IN NATURAL LANGUAGE MODE)
ORDER BY score DESC, id;
```

FULLTEXT không giống `LIKE`. Engine phân tách nội dung thành token và áp dụng stopword, giới hạn độ dài token, parser và quy tắc collation. Tiếng Việt có nhiều từ ghép gồm nhiều âm tiết cách nhau bằng dấu cách; tìm kiếm một cụm từ có thể không tương đương với tìm kiếm một từ đơn. Cần thử với nội dung thực tế và cấu hình parser phù hợp.

FULLTEXT hữu ích cho tìm kiếm từ khóa và xếp hạng mức liên quan, nhưng không tự giải quyết đầy đủ lỗi gõ, đồng nghĩa, bỏ dấu theo ý nghĩa nghiệp vụ hoặc tìm kiếm gần đúng. Nếu cần gợi ý khi gõ, sửa lỗi chính tả, tách từ tiếng Việt nâng cao hoặc ranking phức tạp, hãy cân nhắc một search service chuyên dụng hoặc lớp xử lý ngôn ngữ ở ứng dụng.

## 9. Collation và index

### 9.1. Index lưu thứ tự theo collation

Index chuỗi được tổ chức theo quy tắc so sánh của collation tại thời điểm index được tạo. Nếu truy vấn dùng cùng collation với cột/index, MySQL có thể dùng index cho so sánh, range hoặc order phù hợp.

Ví dụ:

```sql
CREATE INDEX idx_customer_name
ON customers (full_name);

EXPLAIN
SELECT id, full_name
FROM customers
WHERE full_name LIKE 'Nguyễn%'
ORDER BY full_name, id;
```

Đọc `key`, `type`, `rows` và `Extra` trong kế hoạch. Index không bảo đảm luôn được chọn; optimizer dựa trên chi phí, độ chọn lọc, số hàng và thứ tự cột của index.

### 9.2. Ép COLLATE trong truy vấn có thể ảnh hưởng index

Ví dụ sau đổi collation ngay trong biểu thức:

```sql
SELECT id, full_name
FROM customers
WHERE full_name COLLATE utf8mb4_0900_ai_ci =
      _utf8mb4'nguyen an' COLLATE utf8mb4_0900_ai_ci;
```

Nếu index của `full_name` dùng collation khác, MySQL có thể phải chuyển đổi biểu thức và không dùng index theo cách mong muốn. Dùng `EXPLAIN` để xác nhận. Nếu đây là truy vấn phổ biến, cân nhắc cột tìm kiếm riêng được index bằng collation phù hợp thay vì đổi collation ở mọi câu SQL.

### 9.3. Unique index phụ thuộc collation

Ví dụ cột email có unique index với collation không phân biệt hoa/thường:

```sql
CREATE TABLE account_names (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    login_name VARCHAR(100)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_as_ci NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_login_name (login_name)
) ENGINE=InnoDB;
```

Theo collation này, hai giá trị chỉ khác chữ hoa/thường có thể bị xem là trùng. Nếu chuyển sang collation không phân biệt dấu, tập giá trị bị coi là trùng có thể tăng thêm. Đây là thay đổi quy tắc dữ liệu, không chỉ là thay đổi cách hiển thị.

## 10. Kiểm tra hành vi collation trước khi áp dụng

### 10.1. So sánh một số cặp tiếng Việt

```sql
SELECT
    _utf8mb4'Nguyen' COLLATE utf8mb4_0900_ai_ci =
    _utf8mb4'Nguyễn' COLLATE utf8mb4_0900_ai_ci AS ignores_diacritics,

    _utf8mb4'NGUYỄN' COLLATE utf8mb4_0900_as_ci =
    _utf8mb4'Nguyễn' COLLATE utf8mb4_0900_as_ci AS ignores_case,

    _utf8mb4'ma' COLLATE utf8mb4_0900_as_ci =
    _utf8mb4'má' COLLATE utf8mb4_0900_as_ci AS distinguishes_tone;
```

Kết quả cần được kiểm tra trên đúng server và phiên bản. Hãy mở rộng tập thử nghiệm với `a/ă/â`, `d/đ`, các dấu thanh, chữ hoa/thường, khoảng trắng và ký tự kết hợp Unicode.

### 10.2. Xem trọng số so sánh

`WEIGHT_STRING()` có thể hỗ trợ điều tra cách collation biến chuỗi thành trọng số so sánh:

```sql
SELECT
    HEX(WEIGHT_STRING(_utf8mb4'Nguyễn' COLLATE utf8mb4_0900_as_ci)) AS w1,
    HEX(WEIGHT_STRING(_utf8mb4'NGUYỄN' COLLATE utf8mb4_0900_as_ci)) AS w2;
```

Nếu hai chuỗi có trọng số bằng nhau theo collation, chúng có thể được xem là bằng nhau trong các phép so sánh dùng collation đó. `WEIGHT_STRING()` là công cụ chẩn đoán, không nên dùng làm API nghiệp vụ hoặc tự lưu trọng số này làm khóa ổn định qua các lần nâng cấp MySQL.

### 10.3. Kiểm tra trùng lặp trước khi đổi collation

Giả sử muốn đổi `login_name` sang collation không phân biệt dấu và hoa/thường. Trước tiên, tìm các nhóm giá trị sẽ trở thành trùng:

```sql
SELECT
    login_name COLLATE utf8mb4_0900_ai_ci AS normalized_value,
    COUNT(*) AS duplicate_count
FROM account_names
GROUP BY login_name COLLATE utf8mb4_0900_ai_ci
HAVING COUNT(*) > 1;
```

Nếu kết quả có hàng, việc tạo unique index hoặc đổi collation có thể thất bại. Cần quyết định cách xử lý từng nhóm theo nghiệp vụ, không tự động xóa một bản ghi.

## 11. Unicode normalization và dữ liệu tiếng Việt

Một ký tự hiển thị có thể được biểu diễn bằng code point dựng sẵn hoặc bằng ký tự cơ sở kết hợp với combining mark. Ví dụ một chữ có dấu có thể đến từ nguồn dữ liệu dưới dạng NFC (dạng dựng sẵn) hoặc NFD (dạng phân rã). Một số collation UCA 4.0 cũ của MySQL không xử lý đầy đủ các combining mark; hai cách biểu diễn tương đương về hiển thị vì thế có thể so sánh khác nhau.

Hai chuỗi có thể nhìn giống nhau nhưng khác byte. Để dữ liệu nhất quán giữa web, mobile, API và MySQL, nên chuẩn hóa Unicode ở ranh giới ứng dụng, thường chọn NFC cho dữ liệu văn bản được lưu. Chuẩn hóa này khác với việc bỏ dấu: NFC giữ nguyên nội dung và chỉ chuẩn hóa cách biểu diễn Unicode tương đương.

Ví dụ trong Java:

```java
import java.text.Normalizer;

String normalized = Normalizer.normalize(input, Normalizer.Form.NFC);
```

Không tự ý áp dụng NFD rồi xóa mọi combining mark nếu nghiệp vụ không yêu cầu tìm kiếm bỏ dấu. Cách đó có thể làm mất thông tin phân biệt nguyên âm tiếng Việt. Nếu tạo `search_key`, hãy định nghĩa rõ quy tắc biến đổi và giữ chuỗi gốc để hiển thị.

## 12. Kết nối ứng dụng và character set

Ngay cả khi cột dùng `utf8mb4`, dữ liệu vẫn có thể bị lỗi nếu kết nối không khai báo đúng character set. Kiểm tra:

```sql
SHOW VARIABLES LIKE 'character_set_client';
SHOW VARIABLES LIKE 'character_set_connection';
SHOW VARIABLES LIKE 'character_set_results';
SHOW VARIABLES LIKE 'collation_connection';
```

Trong phiên thử nghiệm, có thể thiết lập:

```sql
SET NAMES utf8mb4 COLLATE utf8mb4_0900_as_ci;
```

`SET NAMES` đặt character set client, connection, results và collation connection cho session. Trong ứng dụng, nên cấu hình charset qua driver/connector để thiết lập được thực hiện đúng lúc mở kết nối và tránh lặp thủ công trong từng request.

Ví dụ với mysql client:

```bash
mysql --default-character-set=utf8mb4 -h 127.0.0.1 -u app_user -p shop
```

Khi kiểm tra dữ liệu đã lưu, dùng `HEX()` cùng `CHAR_LENGTH()` và `LENGTH()`:

```sql
SELECT
    full_name,
    HEX(full_name) AS stored_bytes,
    CHAR_LENGTH(full_name) AS character_count,
    LENGTH(full_name) AS byte_count
FROM customers
LIMIT 10;
```

`CHAR_LENGTH()` đếm ký tự theo character set; `LENGTH()` đếm byte. Với `utf8mb4`, một ký tự có thể dùng từ một đến bốn byte. Kết quả giúp phát hiện chuỗi bị mã hóa sai hoặc bị cắt cụt.

## 13. Chuyển đổi collation an toàn

Đổi collation của một bảng có thể ảnh hưởng thứ tự sắp xếp, kết quả tìm kiếm, unique index và kế hoạch truy vấn. Trước khi thay đổi:

1. **Ghi nhận hiện trạng:** phiên bản MySQL, charset/collation server, database, table, column và connection.
2. **Xác định yêu cầu:** cột nào cần sắp xếp tiếng Việt, cột nào cần tìm không dấu, cột nào cần so sánh chính xác.
3. **Kiểm tra dữ liệu:** tìm byte lỗi, chuỗi có Unicode form khác nhau, khoảng trắng cuối và nhóm giá trị có thể trùng theo collation mới.
4. **Thử trên bản sao:** chạy truy vấn tìm kiếm, sắp xếp, unique check và `EXPLAIN` với collation đích.
5. **Đánh giá index:** đổi collation có thể cần rebuild index; kiểm tra thời gian DDL, dung lượng, khóa và khả năng online DDL của phiên bản/engine.
6. **Triển khai có kế hoạch:** backup, chọn cửa sổ phù hợp, theo dõi lỗi ứng dụng và chuẩn bị phương án rollback.
7. **Xác minh sau thay đổi:** kiểm tra DDL, dữ liệu tiếng Việt, kết quả tìm kiếm, thứ tự, unique constraint và hiệu năng.

Đổi charset và đổi collation là hai việc khác nhau. `CONVERT TO CHARACTER SET` có thể chuyển đổi dữ liệu và kiểu cột; `COLLATE` chọn quy tắc so sánh. Hãy đọc DDL và kiểm tra encoding nguồn trước khi chuyển đổi để tránh biến mojibake thành dữ liệu được mã hóa hợp lệ nhưng sai nội dung.

Ví dụ đổi mặc định charset/collation của bảng và chuyển đổi các cột chuỗi:

```sql
ALTER TABLE customers
CONVERT TO CHARACTER SET utf8mb4
COLLATE utf8mb4_0900_as_ci;
```

Lệnh này có thể thay đổi kiểu/độ dài cột chuỗi và rebuild dữ liệu/index. Không chạy trực tiếp trên production khi chưa đánh giá kích thước bảng, giới hạn index, thời gian khóa và tác động của collation lên unique key.

## 14. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Tiếng Việt thành `?` hoặc ký tự lạ | Client/connection charset sai, dữ liệu đã bị thay thế trước khi lưu | Kiểm tra charset ở client, connection và cột; kiểm tra `HEX()` |
| Lỗi `Illegal mix of collations` | Biểu thức chuỗi dùng collation không tương thích | Xác định collation từng biểu thức; thống nhất schema/connection hoặc ép `COLLATE` có chủ đích |
| Tìm `Nguyen` không ra `Nguyễn` | Collation đang phân biệt dấu | Chọn collation/cột search key cho tìm không dấu theo yêu cầu |
| Tìm `ma` trả quá nhiều kết quả | Collation accent-insensitive gộp các từ khác nghĩa | Dùng tìm có dấu chính xác hoặc tách chế độ tìm rộng |
| Sắp xếp tên không theo từ điển mong đợi | Collation tổng quát không có tailoring tiếng Việt phù hợp | Kiểm tra collation tiếng Việt, thử dữ liệu đại diện hoặc dùng sort key ứng dụng |
| Tạo unique index bị duplicate | Collation mới coi các chuỗi khác byte là bằng nhau | Nhóm trùng theo collation đích và xử lý dữ liệu trước khi tạo index |
| Truy vấn chậm sau khi thêm COLLATE | Biểu thức chuyển collation khiến index không còn được dùng trực tiếp | Kiểm tra `EXPLAIN`, cân nhắc cột search key/index phù hợp |
| Kết quả khác giữa môi trường | Phiên bản MySQL, collation hoặc Unicode data khác nhau | Ghi nhận phiên bản, kiểm tra `SHOW COLLATION` và chạy cùng bộ test |

## 15. Checklist chọn quy tắc sắp xếp và tìm kiếm tiếng Việt

- Character set của database, table, column và connection có thống nhất `utf8mb4` không?
- Cần sắp xếp theo thứ tự tiếng Việt hay chỉ cần thứ tự Unicode tổng quát?
- Tìm kiếm có phân biệt dấu thanh và chữ cái `ă`, `â`, `đ`, `ê`, `ô`, `ơ`, `ư` không?
- Có cần phân biệt hoa/thường không?
- Có cần tìm không dấu như một chế độ riêng không?
- Quy tắc tìm kiếm có làm các từ khác nghĩa trở thành cùng kết quả không?
- Unique key có thể bị xung đột khi đổi collation không?
- Cột có index đúng collation và truy vấn có dùng được index không?
- FULLTEXT có tokenization và stopword phù hợp với nội dung tiếng Việt thực tế không?
- Ứng dụng đã chuẩn hóa Unicode NFC và khoảng trắng theo chính sách chưa?
- Đã kiểm thử dữ liệu thật, kế hoạch thực thi và migration trên bản sao chưa?

## Kết luận

Muốn sắp xếp và tìm kiếm tiếng Việt đúng trong MySQL, hãy tách yêu cầu về thứ tự từ điển, phân biệt dấu, phân biệt hoa/thường, tìm không dấu và kiểm tra trùng lặp. Dùng `utf8mb4` cho dữ liệu Unicode; chọn collation đã được kiểm chứng trên phiên bản server; giữ chuỗi gốc và tạo khóa tìm kiếm riêng nếu cần bỏ dấu; kiểm tra index và unique constraint trước khi thay đổi. Với tên người, sản phẩm và định danh, quy tắc so sánh phải phản ánh nghiệp vụ cụ thể thay vì áp dụng một collation chung cho mọi cột.
