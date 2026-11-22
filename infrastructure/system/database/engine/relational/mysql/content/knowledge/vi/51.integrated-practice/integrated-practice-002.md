# Thiết kế bộ ký tự/collation để lưu và tìm kiếm tiếng Việt

Ứng dụng lưu tên người, địa chỉ, sản phẩm và nội dung tiếng Việt cần xử lý đúng dấu, chữ hoa/thường, sắp xếp và tìm kiếm. Nếu chọn sai character set hoặc collation, dữ liệu có thể bị lỗi hiển thị, phép so sánh có thể phân biệt những chuỗi mà nghiệp vụ xem là tương đương, hoặc truy vấn dùng index không như dự kiến.

Thiết kế cần phân biệt hai khái niệm: **character set** quyết định cách mã hóa ký tự thành byte; **collation** quyết định cách so sánh và sắp xếp chuỗi thuộc character set đó. Với dữ liệu tiếng Việt hiện đại, lựa chọn nền tảng nên là `utf8mb4`, sau đó chọn collation theo quy tắc tìm kiếm, uniqueness và thứ tự sắp xếp của nghiệp vụ. Trong module `DATABASE_MYSQL`, bài học này kết hợp thiết kế bảng, kiểu dữ liệu, index, truy vấn và vận hành dữ liệu quan hệ.

Sau bài học, bạn có thể:

- Phân biệt character set với collation.
- Chọn `utf8mb4` để lưu tiếng Việt và các ký tự Unicode khác.
- Hiểu hậu tố `ai`, `as`, `ci`, `cs` và collation nhị phân.
- Chọn quy tắc so sánh cho tìm kiếm tên, email, mã định danh và nội dung.
- Kiểm tra ảnh hưởng collation tới `=`, `LIKE`, `ORDER BY` và unique index.
- Thiết kế schema, index và kết nối Java/Connector/J nhất quán.
- Chuẩn hóa Unicode và di chuyển dữ liệu cũ an toàn.
- Kiểm thử bằng các từ tiếng Việt có dấu, không dấu và khác biệt chữ hoa/thường.

## 1. Character set và collation khác nhau thế nào?

Character set là tập ký tự và quy tắc mã hóa ký tự thành byte. Collation là tập quy tắc xác định hai chuỗi có được xem là bằng nhau hay không và chuỗi nào đứng trước khi sắp xếp.

Ví dụ, `utf8mb4` có thể lưu các ký tự tiếng Việt như `ă`, `â`, `đ`, `ê`, `ô`, `ơ`, `ư`, các dấu thanh và cả emoji. Một collation accent-insensitive có thể xem một số dạng có dấu và không dấu là tương đương khi so sánh; collation accent-sensitive phân biệt chúng.

| Thuộc tính | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| Character set | Ký tự được mã hóa ra byte như thế nào? | `utf8mb4` |
| Collation | So sánh và sắp xếp chuỗi theo quy tắc nào? | `utf8mb4_0900_ai_ci` |

Hai cột cùng dùng `utf8mb4` nhưng collation khác nhau vẫn có thể cho kết quả `=`, `LIKE`, `ORDER BY`, `GROUP BY` và uniqueness khác nhau.

## 2. Vì sao nên dùng `utf8mb4`?

MySQL có các character set UTF-8 khác nhau. `utf8mb3` chỉ dùng tối đa ba byte cho một ký tự và không thể biểu diễn toàn bộ Unicode. Tên `utf8` trong MySQL là alias cũ cho `utf8mb3` trên các phiên bản hiện đại và đã bị deprecated. Với schema mới, hãy dùng `utf8mb4`.

`utf8mb4` hỗ trợ tối đa bốn byte cho một ký tự, bao phủ đầy đủ Unicode, bao gồm tiếng Việt và các ký tự bổ sung ngoài Basic Multilingual Plane.

Kiểm tra character set và collation server:

```sql
SHOW VARIABLES LIKE 'character_set_server';
SHOW VARIABLES LIKE 'collation_server';
```

Kiểm tra database hiện tại:

```sql
SELECT
    SCHEMA_NAME,
    DEFAULT_CHARACTER_SET_NAME,
    DEFAULT_COLLATION_NAME
FROM INFORMATION_SCHEMA.SCHEMATA
WHERE SCHEMA_NAME = DATABASE();
```

Không dựa hoàn toàn vào default của server. Hãy khai báo rõ character set và collation ở database, table hoặc column để schema có hành vi ổn định giữa các môi trường.

## 3. Đọc tên collation

Tên collation của MySQL thường chứa thông tin về character set và quy tắc so sánh. Với các collation UCA 9.0 thường gặp trên MySQL 8.0:

| Thành phần | Ý nghĩa |
|---|---|
| `utf8mb4` | Character set |
| `0900` | Bộ quy tắc Unicode Collation Algorithm phiên bản 9.0 |
| `ai` | Accent-insensitive: bỏ qua khác biệt dấu trong phép so sánh theo collation |
| `as` | Accent-sensitive: phân biệt khác biệt dấu |
| `ci` | Case-insensitive: không phân biệt chữ hoa/thường |
| `cs` | Case-sensitive: phân biệt chữ hoa/thường |
| `bin` | So sánh theo giá trị mã hóa/đơn vị nhị phân của character set |

Các ví dụ:

- `utf8mb4_0900_ai_ci`: không phân biệt dấu và chữ hoa/thường.
- `utf8mb4_0900_as_ci`: phân biệt dấu nhưng không phân biệt chữ hoa/thường.
- `utf8mb4_0900_as_cs`: phân biệt cả dấu và chữ hoa/thường.
- `utf8mb4_bin`: collation nhị phân thuộc character set `utf8mb4`.

Không phải mọi collation đều có trên mọi phiên bản MySQL hoặc bản phân phối. Kiểm tra danh sách thực tế:

```sql
SHOW COLLATION LIKE 'utf8mb4%';
```

MySQL 8.0 có các collation `utf8mb4_0900_*`. Với MySQL 5.7 hoặc môi trường cũ hơn, có thể cần dùng collation như `utf8mb4_unicode_ci`; hãy kiểm tra phiên bản và kết quả `SHOW COLLATION` trước khi viết DDL.

## 4. Chọn collation theo nghiệp vụ tiếng Việt

Không có một collation tối ưu cho mọi cột. Tên hiển thị, email, mã sản phẩm và mã định danh có yêu cầu so sánh khác nhau.

### 4.1. Tìm kiếm tên không phân biệt dấu

Một ứng dụng có thể muốn người dùng nhập `nguyen` và tìm thấy `Nguyễn`. Collation accent-insensitive/case-insensitive như `utf8mb4_0900_ai_ci` có thể hỗ trợ hành vi này cho các ký tự được collation xử lý tương đương.

Ví dụ:

```sql
CREATE TABLE customer_search_demo (
    customer_id BIGINT NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(200) NOT NULL,
    PRIMARY KEY (customer_id),
    KEY idx_customer_full_name (full_name)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;

INSERT INTO customer_search_demo (full_name)
VALUES ('Nguyễn Văn An'), ('Trần Thị Bình'), ('Đặng Minh Châu');

SELECT customer_id, full_name
FROM customer_search_demo
WHERE full_name LIKE '%nguyen%';
```

Ví dụ trên minh họa so sánh không phân biệt dấu; mẫu `'%nguyen%'` có ký tự wildcard ở đầu nên B-tree index thông thường không thể dùng để tìm range theo prefix. Collation không tự làm cho tìm kiếm chứa chuỗi ở giữa trở thành truy vấn indexable.

### 4.2. Tìm kiếm có phân biệt dấu

Với mã hoặc từ khóa mà dấu làm thay đổi ý nghĩa, chọn collation accent-sensitive. Ví dụ:

```sql
CREATE TABLE dictionary_entry (
    entry_id BIGINT NOT NULL AUTO_INCREMENT,
    term VARCHAR(150) NOT NULL,
    PRIMARY KEY (entry_id),
    KEY idx_dictionary_term (term)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_as_ci;
```

Trong collation này, `ci` không phân biệt chữ hoa/thường nhưng `as` phân biệt dấu. Nếu cần phân biệt cả hoa/thường, cân nhắc `utf8mb4_0900_as_cs`.

### 4.3. Collation theo ngôn ngữ và thứ tự từ điển

Collation tổng quát UCA có quy tắc Unicode chung; collation được tailoring theo ngôn ngữ có thể sắp xếp một số chữ cái theo quy tắc riêng của ngôn ngữ đó. Với tiếng Việt, thứ tự hiển thị của `ORDER BY` có thể là yêu cầu sản phẩm quan trọng, nhất là danh bạ, từ điển hoặc danh sách tên.

Không giả định collation mặc định của server là thứ tự từ điển tiếng Việt mà nghiệp vụ mong muốn. Kiểm tra các collation locale-specific có sẵn bằng `SHOW COLLATION`, sau đó thử các chữ cái và từ đại diện như `a`, `ă`, `â`, `b`, `d`, `đ`, `e`, `ê`, `o`, `ô`, `ơ`, `u`, `ư` cùng các dấu thanh. Chọn collation sau khi xác nhận thứ tự thực tế trên đúng phiên bản MySQL.

### 4.4. Không phân biệt dấu không có nghĩa mọi chuỗi đều tương đương

Collation dựa trên Unicode có trọng số và quy tắc riêng. Không nên tự suy luận rằng mọi chữ có dấu đều bằng chữ không dấu, hoặc chữ `đ` luôn được xử lý giống `d`. Hãy chạy các phép so sánh trên phiên bản server thực tế với bộ từ thử nghiệm của ứng dụng.

## 5. Kiểm tra hành vi so sánh bằng SQL

Thử trực tiếp hai chuỗi với collation mục tiêu:

```sql
SELECT
    _utf8mb4'Nguyễn' COLLATE utf8mb4_0900_ai_ci =
    _utf8mb4'Nguyen' COLLATE utf8mb4_0900_ai_ci AS accent_insensitive,

    _utf8mb4'Nguyễn' COLLATE utf8mb4_0900_as_ci =
    _utf8mb4'Nguyen' COLLATE utf8mb4_0900_as_ci AS accent_sensitive,

    _utf8mb4'NGUYEN' COLLATE utf8mb4_0900_ai_ci =
    _utf8mb4'nguyen' COLLATE utf8mb4_0900_ai_ci AS case_insensitive;
```

Kết quả mong đợi về mặt khái niệm:

- So sánh đầu tiên có thể xem hai chuỗi tương đương theo accent-insensitive collation.
- So sánh thứ hai phân biệt dấu.
- So sánh thứ ba không phân biệt chữ hoa/thường.

Các literal introducer `_utf8mb4` chỉ định character set của chuỗi; `COLLATE` chỉ định quy tắc so sánh. Chạy test này trên đúng server target vì collation/version có thể khác.

Kiểm tra hành vi với tiếng Việt thực tế:

```sql
SELECT
    _utf8mb4'ma' COLLATE utf8mb4_0900_ai_ci =
    _utf8mb4'má' COLLATE utf8mb4_0900_ai_ci AS ma_vs_ma_tone,

    _utf8mb4'd' COLLATE utf8mb4_0900_ai_ci =
    _utf8mb4'đ' COLLATE utf8mb4_0900_ai_ci AS d_vs_d_stroke,

    _utf8mb4'hoa' COLLATE utf8mb4_0900_ai_ci =
    _utf8mb4'HÒA' COLLATE utf8mb4_0900_ai_ci AS case_and_accent;
```

Không hardcode giả định về `d`/`đ` hoặc mọi cặp ký tự trong business logic trước khi xác minh kết quả. Bộ kiểm thử nên lưu các cặp mà nghiệp vụ yêu cầu bằng/khác nhau.

## 6. Khai báo character set và collation ở đúng cấp

MySQL cho phép đặt default ở server, database, table và column. Giá trị ở cấp dưới có thể ghi đè default cấp trên.

### 6.1. Database

```sql
CREATE DATABASE shop
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;
```

### 6.2. Table

```sql
CREATE TABLE customers (
    customer_id BIGINT NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(200) NOT NULL,
    email VARCHAR(254) NOT NULL,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customers_email (email),
    KEY idx_customers_full_name (full_name)
) ENGINE=InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
```

Trong ví dụ, `email` kế thừa collation không phân biệt dấu/hoa thường của bảng. Điều này có nghĩa unique index cũng sử dụng quy tắc so sánh đó. Với email, đây có thể là chính sách sản phẩm hợp lý nếu hệ thống chủ động coi email không phân biệt hoa/thường, nhưng không nên áp dụng ngẫu nhiên; quy tắc chuẩn hóa và uniqueness cần được xác định rõ.

### 6.3. Column

Có thể đặt collation riêng cho từng cột:

```sql
CREATE TABLE customer_profile (
    customer_id BIGINT NOT NULL,
    display_name VARCHAR(200)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci NOT NULL,
    legal_name VARCHAR(200)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_as_cs NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;
```

Ví dụ minh họa hai chính sách khác nhau: tên hiển thị dễ tìm kiếm không phân biệt dấu/hoa thường; tên pháp lý được so sánh nghiêm ngặt hơn. Trong hệ thống thật, xác định rõ yêu cầu lưu trữ và tìm kiếm trước khi chọn chính sách.

## 7. Ảnh hưởng tới unique index và dữ liệu trùng

Collation quyết định hai giá trị chuỗi có được xem là trùng nhau khi kiểm tra unique key hay không. Nếu cột dùng collation accent-insensitive/case-insensitive, các chuỗi khác dấu hoặc khác hoa/thường nhưng tương đương theo collation có thể xung đột unique index.

Ví dụ, với collation không phân biệt hoa/thường, `An@example.com` và `an@example.com` có thể bị xem là cùng một giá trị. Với collation không phân biệt dấu, các tên khác dấu có thể được xem là tương đương tùy quy tắc trọng số.

Trước khi tạo hoặc đổi unique index, kiểm tra collision theo collation đích:

```sql
SELECT
    email COLLATE utf8mb4_0900_ai_ci AS comparison_value,
    COUNT(*) AS duplicate_count
FROM customers
GROUP BY email COLLATE utf8mb4_0900_ai_ci
HAVING COUNT(*) > 1;
```

Thực hiện tương tự với tên, mã hoặc trường sẽ có unique constraint. Nếu truy vấn trả về nhóm trùng, hãy xác định quy tắc nghiệp vụ để hợp nhất, đổi giá trị hoặc chọn collation khác trước khi tạo index.

### 7.1. Tách chính sách tìm kiếm và chính sách uniqueness

Có trường hợp người dùng cần tìm tên không phân biệt dấu nhưng hệ thống vẫn phải giữ hai tên khác nhau. Không nên ép một cột dùng cùng collation cho cả hai yêu cầu nếu chúng mâu thuẫn.

Một số lựa chọn:

- Giữ cột gốc với collation phù hợp cho lưu trữ và uniqueness.
- Tạo cột tìm kiếm chuẩn hóa riêng do ứng dụng cập nhật, rồi index cột đó.
- Tạo generated column hoặc functional index nếu biểu thức chuẩn hóa và phiên bản MySQL hỗ trợ.
- Thực hiện tìm kiếm qua search service khi yêu cầu bỏ dấu, tokenization hoặc ranking vượt khả năng của collation.

Nếu dùng cột search key, phải định nghĩa thuật toán chuẩn hóa ổn định, version hóa khi cần và bảo đảm dữ liệu gốc vẫn được giữ nguyên.

## 8. Collation và hiệu năng index

Index chuỗi được xây dựng theo collation của cột. Khi truy vấn so sánh theo cùng collation, optimizer có thể dùng index phù hợp. Nếu áp dụng một collation khác ngay trong biểu thức, hoặc chuyển đổi cột bằng hàm, khả năng dùng index có thể thay đổi.

Ví dụ:

```sql
-- So sánh theo collation được định nghĩa trên cột.
SELECT customer_id, full_name
FROM customers
WHERE full_name = 'Nguyen Van An';

-- Ép collation khác trong query có thể thay đổi cách dùng index.
SELECT customer_id, full_name
FROM customers
WHERE full_name COLLATE utf8mb4_0900_as_cs = 'Nguyen Van An';
```

Chạy `EXPLAIN` cho cả hai truy vấn để xác minh access path. Nếu ứng dụng thường xuyên cần hai kiểu so sánh khác nhau, cân nhắc cột/index riêng thay vì ép collation khác trong mọi câu query.

### 8.1. Giới hạn độ dài index với `utf8mb4`

`utf8mb4` có thể cần tối đa bốn byte cho mỗi ký tự. Một cột `VARCHAR(255)` có thể cần tối đa 1.020 byte cho dữ liệu ký tự, chưa tính overhead và các cột khác trong composite index. Giới hạn key length của InnoDB phụ thuộc phiên bản, page size, row format và cấu hình; không nên dùng quy tắc cũ 191 ký tự như một giới hạn phổ quát.

Trước khi tạo index:

- Kiểm tra giới hạn key length theo phiên bản và cấu hình InnoDB.
- Kiểm tra tổng độ dài byte của composite index.
- Cân nhắc index prefix nếu phù hợp với truy vấn và semantics.
- Không dùng prefix unique như thể nó tương đương unique toàn chuỗi: hai giá trị chỉ khác ở phần sau prefix có thể bị coi là trùng.
- Xem xét độ chọn lọc, write overhead và dung lượng index.

## 9. Tìm kiếm chính xác, prefix và substring

Collation điều khiển cách so sánh ký tự, nhưng kiểu pattern và index vẫn quyết định hiệu năng.

| Truy vấn | Ý nghĩa | Khả năng dùng B-tree index |
|---|---|---|
| `name = 'Nguyen'` | So sánh bằng theo collation cột | Thường có thể dùng index |
| `name LIKE 'Nguyen%'` | Tìm prefix | Thường có thể dùng range scan theo index |
| `name LIKE '%Nguyen'` | Tìm suffix | Thường không dùng B-tree range scan |
| `name LIKE '%Nguyen%'` | Tìm chuỗi ở bất kỳ vị trí nào | Thường phải scan; cân nhắc search index/service |

Ví dụ:

```sql
SELECT customer_id, full_name
FROM customers
WHERE full_name LIKE 'nguyen%';
```

Với collation accent-insensitive/case-insensitive, truy vấn có thể khớp nhiều dạng dấu và hoa/thường theo quy tắc collation. Nhưng nếu mẫu bắt đầu bằng `%`, index B-tree thông thường không thể tìm điểm bắt đầu range từ prefix.

Đối với tìm kiếm tên tiếng Việt dạng contains, cân nhắc quy mô dữ liệu, tokenization, yêu cầu bỏ dấu và ranking. MySQL FULLTEXT có cách tokenization và stopword riêng; cần kiểm thử với tiếng Việt thực tế. Nếu yêu cầu tìm gần đúng, sửa lỗi gõ, gợi ý hoặc bỏ dấu phức tạp, một search engine chuyên dụng có thể phù hợp hơn.

## 10. Unicode normalization: NFC và NFD

Unicode cho phép một ký tự hiển thị được biểu diễn bằng một code point dựng sẵn hoặc bằng chuỗi gồm ký tự cơ sở và combining mark. Ví dụ, một nguyên âm tiếng Việt có dấu có thể có biểu diễn dựng sẵn hoặc biểu diễn phân rã.

Hai chuỗi có thể nhìn giống nhau nhưng byte khác nhau. Collation hiện đại có thể xử lý một số dạng tương đương theo Unicode, nhưng không nên phụ thuộc vào giả định rằng mọi hệ thống, driver và thuật toán tìm kiếm đều chuẩn hóa giống nhau.

Khuyến nghị:

- Chuẩn hóa text đầu vào về Unicode NFC tại ranh giới ứng dụng nếu chính sách dữ liệu cho phép.
- Giữ nguyên nội dung người dùng nhập theo yêu cầu nghiệp vụ; nếu cần lưu nguyên bản, lưu thêm trường raw riêng.
- Dùng cùng thuật toán normalization cho ghi, tìm kiếm, import và đồng bộ dữ liệu.
- Kiểm thử chuỗi NFC/NFD, dấu thanh, chữ `đ`, ký tự tổ hợp và emoji.
- Không dùng thao tác bỏ dấu làm bước chuẩn hóa duy nhất vì có thể làm mất phân biệt có ý nghĩa.

Ví dụ Java:

```java
import java.text.Normalizer;

String normalizedName = Normalizer.normalize(
    inputName,
    Normalizer.Form.NFC
);
```

NFC chuẩn hóa cách biểu diễn Unicode; nó không tự chuyển tiếng Việt thành không dấu và không thay thế collation của database.

## 11. Cấu hình kết nối ứng dụng Java/Connector/J

Ứng dụng phải gửi và nhận chuỗi bằng character encoding nhất quán. Với Connector/J hiện đại, UTF-8 được ánh xạ tới `utf8mb4` trên MySQL; vẫn cần xác minh phiên bản driver và trạng thái session thực tế.

Ví dụ JDBC URL:

```text
jdbc:mysql://mysql.example.internal:3306/shop?characterEncoding=UTF-8
```

Kết nối xong, kiểm tra:

```sql
SHOW SESSION VARIABLES LIKE 'character_set_client';
SHOW SESSION VARIABLES LIKE 'character_set_connection';
SHOW SESSION VARIABLES LIKE 'character_set_results';
SHOW SESSION VARIABLES LIKE 'collation_connection';
```

Các biến có vai trò:

- `character_set_client`: encoding mà server dùng để diễn giải byte client gửi.
- `character_set_connection`: character set dùng cho biểu thức và literal sau khi nhận dữ liệu.
- `character_set_results`: encoding dùng khi gửi kết quả về client.
- `collation_connection`: collation cho các phép so sánh trong một số biểu thức/literal.

Collation của cột vẫn quyết định semantics của cột khi so sánh với literal phù hợp, nhưng collation coercibility và chuyển đổi giữa các biểu thức có thể ảnh hưởng kết quả. Nếu gặp lỗi `Illegal mix of collations`, kiểm tra collation của các cột, literal, connection và biểu thức JOIN/UNION.

### 11.1. Spring Boot

Ví dụ cấu hình:

```properties
spring.datasource.url=jdbc:mysql://mysql.example.internal:3306/shop?characterEncoding=UTF-8
spring.datasource.username=${SHOP_DB_USER}
spring.datasource.password=${SHOP_DB_PASSWORD}
```

Secret nên được inject từ secret manager hoặc môi trường triển khai được bảo vệ. Không ghi password vào repository. Khai báo collation của bảng/cột trong migration; không dựa vào `collation_connection` để thay thế định nghĩa schema.

### 11.2. Không tùy tiện `SET NAMES` trên connection pool

`SET NAMES` thay đổi session variables. Nếu dùng connection pool, session có thể được tái sử dụng cho request khác. Hãy để Connector/J quản lý character encoding qua cấu hình driver và kiểm tra trạng thái session. Nếu buộc phải thay session state, cần bảo đảm pool reset nó trước khi connection được tái sử dụng.

## 12. Di chuyển schema cũ sang `utf8mb4`

Trước khi chuyển bảng cũ, xác định character set được khai báo và encoding thực tế của byte. Có hai trường hợp khác nhau:

1. **Dữ liệu được lưu đúng theo character set cũ:** có thể dùng `ALTER TABLE ... CONVERT TO CHARACTER SET utf8mb4` để MySQL chuyển đổi ký tự từ encoding cũ sang UTF-8.
2. **Dữ liệu đã bị mojibake:** byte UTF-8 trước đây bị diễn giải sai như latin1 hoặc encoding khác. Chuyển đổi schema đơn thuần có thể giữ nguyên chuỗi lỗi hoặc làm hỏng dữ liệu thêm; cần quy trình sửa dữ liệu riêng sau khi xác định nguồn byte.

Kiểm tra định nghĩa hiện tại:

```sql
SHOW CREATE TABLE customers\G

SELECT
    COLUMN_NAME,
    CHARACTER_SET_NAME,
    COLLATION_NAME,
    COLUMN_TYPE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'customers';
```

### 12.1. Lập kế hoạch chuyển đổi

1. Backup và thử restore trên môi trường độc lập.
2. Kiểm tra encoding thật bằng mẫu dữ liệu đại diện, gồm tên tiếng Việt, dấu tổ hợp và ký tự ngoài BMP.
3. Kiểm tra unique collision theo collation đích.
4. Kiểm tra index length, composite index, foreign key và view/routine phụ thuộc.
5. Thử chuyển đổi trên bản sao có dung lượng gần production.
6. Đo thời gian, lock, I/O, dung lượng tạm và replication lag.
7. Chọn cửa sổ triển khai hoặc chiến lược online schema change phù hợp.
8. Sau chuyển đổi, kiểm tra dữ liệu, query plan, sort order, uniqueness và ứng dụng.

Ví dụ chuyển đổi bảng:

```sql
ALTER TABLE customers
    CONVERT TO CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;
```

Lệnh này có thể rebuild bảng và index, tiêu tốn I/O/dung lượng, chờ metadata lock và ảnh hưởng replication. Không chạy trực tiếp trên bảng lớn trong giờ cao điểm khi chưa thử nghiệm.

### 12.2. Kiểm tra collision trước khi đổi collation

Một collation mới có thể coi hai giá trị trước đây khác nhau là bằng nhau. Trước khi đổi cột có unique index, chạy truy vấn nhóm theo collation đích:

```sql
SELECT
    email COLLATE utf8mb4_0900_ai_ci AS comparison_value,
    COUNT(*) AS row_count
FROM customers
GROUP BY email COLLATE utf8mb4_0900_ai_ci
HAVING COUNT(*) > 1;
```

Lặp lại cho các cột có unique constraint và các composite key. Nếu có collision, xác định chính sách dữ liệu trước khi chạy `ALTER TABLE`; nếu không, migration có thể thất bại khi tạo lại unique index.

### 12.3. Phân biệt chuyển đổi charset với sửa mojibake

Không chạy các biểu thức ép kiểu byte như `CONVERT(CAST(... AS BINARY) USING ...)` trên toàn bảng chỉ vì thấy ký tự hiển thị sai. Cách sửa phụ thuộc byte gốc, charset khai báo và chuỗi đã bị diễn giải sai ở bước nào. Trước hết tạo bản sao, chọn một số mẫu có nguồn dữ liệu đã biết, xác định byte bằng `HEX(column)` và thử phục hồi trên bản sao.

Nếu dữ liệu đã bị thay thế bằng ký tự `?` hoặc replacement character trong quá trình ghi, thông tin ban đầu có thể đã mất và không thể khôi phục chỉ bằng đổi collation.

## 13. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Tiếng Việt thành `?` hoặc ký tự rác | Character set ở client/server không khớp hoặc dữ liệu đã bị ghi sai | Kiểm tra session charset, DDL và byte bằng `HEX()` |
| Một số emoji bị lỗi | Bảng/cột dùng `utf8mb3` hoặc client encoding không phù hợp | Chuyển sang `utf8mb4` và kiểm tra driver |
| Tìm `nguyen` không ra `Nguyễn` | Cột dùng accent-sensitive collation hoặc query ép collation khác | Kiểm tra collation cột và phép so sánh |
| `Nguyen` và `Nguyễn` bị coi là trùng | Unique index dùng accent-insensitive collation | Xem lại yêu cầu uniqueness và collision trước migration |
| Thứ tự tên tiếng Việt không như mong đợi | Collation không phù hợp quy tắc sort ngôn ngữ | So sánh collation có tailoring và bộ từ kiểm thử |
| `Illegal mix of collations` | Biểu thức kết hợp chuỗi từ cột/literal có collation không tương thích | Kiểm tra `COLLATION()`, column metadata và connection settings |
| Truy vấn chậm sau khi thêm `COLLATE` trong WHERE | Expression dùng collation khác làm thay đổi khả năng dùng index | Chạy `EXPLAIN`, cân nhắc collation cột hoặc search key riêng |
| Migration đổi collation thất bại | Unique key collision hoặc giới hạn index length | Tìm collision, tính độ dài byte và kiểm tra index |
| Chuyển sang utf8mb4 nhưng text vẫn lỗi | Dữ liệu đã mojibake từ trước | Xác định byte gốc và lập quy trình repair riêng |

## 14. Bộ kiểm thử tiếng Việt cho schema và search

Một bộ test nên có các nhóm dữ liệu sau:

| Nhóm | Ví dụ | Mục đích |
|---|---|---|
| Nguyên âm có dấu | `a`, `á`, `à`, `ả`, `ã`, `ạ` | Kiểm tra accent sensitivity |
| Nguyên âm biến thể | `a`, `ă`, `â`; `e`, `ê`; `o`, `ô`, `ơ`; `u`, `ư` | Kiểm tra trọng số và sort |
| Phụ âm | `d`, `đ` | Kiểm tra quy tắc riêng của collation |
| Hoa/thường | `An`, `AN`, `an` | Kiểm tra case sensitivity |
| Tên đầy đủ | `Nguyễn Văn An`, `Nguyen Van An` | Kiểm tra tìm kiếm tên |
| Unicode normalization | NFC và NFD của cùng nội dung | Kiểm tra dữ liệu tổ hợp |
| Ký tự ngoài BMP | Emoji trong tên hiển thị/nội dung | Xác nhận `utf8mb4` end-to-end |
| Khoảng trắng | space, non-breaking space, khoảng trắng cuối | Kiểm tra quy tắc trim và so sánh |

Kiểm tra ít nhất các thao tác:

- `=` và `<>`.
- `LIKE 'prefix%'` và `LIKE '%contains%'`.
- `ORDER BY` và `GROUP BY`.
- `DISTINCT`.
- Unique index và composite unique key.
- JOIN giữa các cột chuỗi có collation khác nhau.
- Insert/read qua MySQL client và ứng dụng Java.
- Migration từ character set/collation cũ.

Không chỉ kiểm tra dữ liệu hiển thị trên màn hình. Hãy kiểm tra byte, phép so sánh và index plan trong database.

## 15. Tình huống thực hành tổng hợp

Một cửa hàng trực tuyến lưu 5 triệu hồ sơ khách hàng. Người dùng muốn tìm tên không dấu, nhưng hệ thống vẫn phải lưu đúng tên pháp lý và không được tự gộp các hồ sơ khác nhau. Email được xem là không phân biệt hoa/thường theo chính sách sản phẩm. Danh sách tên cần được sắp xếp theo quy tắc tiếng Việt đã thống nhất.

Thực hiện trong môi trường lab:

1. Tạo database và bảng với `utf8mb4`; không dùng alias `utf8`/`utf8mb3` cho schema mới.
2. Tạo cột tên hiển thị và tên pháp lý với collation theo yêu cầu tìm kiếm/so sánh.
3. Xác định collation email và kiểm tra unique semantics bằng các giá trị chỉ khác hoa/thường.
4. Thử `SHOW COLLATION` để tìm lựa chọn phù hợp cho sort tiếng Việt; ghi lại thứ tự của bộ từ `a`, `ă`, `â`, `d`, `đ`, `e`, `ê`, `o`, `ô`, `ơ`, `u`, `ư`.
5. Nạp các cặp `Nguyễn`/`Nguyen`, `ma`/`má`, `d`/`đ`, NFC/NFD và emoji.
6. Chạy các phép so sánh và tìm kiếm bằng `=`, `LIKE`, `ORDER BY`, `GROUP BY`.
7. Tạo index cho prefix search và dùng `EXPLAIN` để xác nhận access path.
8. Thử `LIKE '%term%'` để quan sát giới hạn của B-tree; đánh giá FULLTEXT hoặc search service nếu cần.
9. Kiểm tra collision trước khi tạo unique index theo collation đã chọn.
10. Chạy ứng dụng Java/Connector/J, xác minh session charset và round-trip dữ liệu.
11. Tạo bản sao schema dùng charset cũ, chuyển sang `utf8mb4` và so sánh dữ liệu trước/sau.
12. Ghi lại chính sách character set/collation cho từng loại cột và bộ test regression để dùng trong CI.

**Câu hỏi tự đánh giá:**

- Character set khác collation ở điểm nào?
- Vì sao schema mới nên dùng `utf8mb4` thay cho alias `utf8` cũ?
- `ai_ci`, `as_ci` và `as_cs` biểu thị những quy tắc gì?
- Vì sao cần kiểm thử riêng chữ `d` và `đ` thay vì suy luận từ hậu tố `ai`?
- Collation ảnh hưởng unique index như thế nào?
- Vì sao `LIKE '%term%'` không tận dụng B-tree index như prefix search?
- NFC/NFD khác nhau ở biểu diễn Unicode nào và NFC không giải quyết vấn đề gì?
- Vì sao phải kiểm tra session charset của Connector/J?
- Vì sao đổi collation có thể làm migration unique index thất bại?
- Làm thế nào phân biệt chuyển đổi charset đúng với sửa dữ liệu mojibake?

## Kết luận

Lưu tiếng Việt an toàn bắt đầu bằng `utf8mb4`, nhưng tìm kiếm và sắp xếp đúng còn phụ thuộc collation. Chọn `ai`/`as` và `ci`/`cs` theo nghiệp vụ, kiểm tra quy tắc tiếng Việt trên phiên bản MySQL thực tế, và đánh giá ảnh hưởng tới unique index cùng execution plan. Chuẩn hóa Unicode nhất quán, xác minh encoding ở Connector/J và chuyển đổi schema trên bản sao trước khi triển khai dữ liệu lớn.
