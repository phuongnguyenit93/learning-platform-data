# Collation coercibility và lỗi trộn collation

Collation quyết định cách MySQL so sánh và sắp xếp chuỗi: có phân biệt hoa/thường không, có phân biệt dấu không, ký tự nào được xem là tương đương và cách xử lý khoảng trắng cuối chuỗi. Khi một biểu thức kết hợp nhiều chuỗi có collation khác nhau, MySQL phải chọn collation để thực hiện phép so sánh hoặc tạo kết quả. Quy tắc lựa chọn đó được gọi là **collation coercibility**.

Nếu MySQL không thể xác định một collation hợp lệ, truy vấn có thể thất bại với lỗi như **Illegal mix of collations**. Lỗi thường xuất hiện khi JOIN hai cột được tạo ở các thời điểm hoặc môi trường khác nhau, khi so sánh cột với literal có charset/collation khác, hoặc khi kết hợp các biểu thức chuỗi.

Trong module **DATABASE_MYSQL**, hiểu coercibility giúp xử lý lỗi SQL, chuẩn hóa schema, bảo toàn ngữ nghĩa so sánh và giữ khả năng sử dụng index. Cần kiểm tra cả character set, collation, nguồn gốc biểu thức và quyền tác động của một thay đổi collation trước khi sửa truy vấn hoặc migration.

## 1. Phân biệt character set và collation

Hai khái niệm liên quan nhưng giải quyết hai vấn đề khác nhau:

- **Character set** xác định tập ký tự và cách mã hóa các ký tự thành byte. Ví dụ **utf8mb4** có thể biểu diễn đầy đủ các ký tự Unicode, kể cả ký tự ngoài BMP.
- **Collation** xác định quy tắc so sánh và sắp xếp các chuỗi thuộc một character set. Ví dụ **utf8mb4_0900_ai_ci** là collation của **utf8mb4**, không phân biệt dấu và không phân biệt hoa/thường.

Một character set có thể có nhiều collation. Vì vậy, hai cột cùng dùng **utf8mb4** vẫn có thể không so sánh được trực tiếp nếu chúng có collation khác nhau và không có quy tắc phân giải phù hợp.

Một số hậu tố thường gặp:

| Thành phần tên | Ý nghĩa |
|---|---|
| **_ai** | Accent-insensitive: không phân biệt dấu trong phép so sánh |
| **_as** | Accent-sensitive: phân biệt dấu |
| **_ci** | Case-insensitive: không phân biệt hoa/thường |
| **_cs** | Case-sensitive: phân biệt hoa/thường |
| **_bin** | Quy tắc so sánh nhị phân của collation tương ứng |

Ví dụ, trong một collation **_ai_ci**, các chuỗi khác dấu hoặc khác hoa/thường có thể được xem là bằng nhau. Trong collation **_as_cs**, những khác biệt đó được giữ lại khi so sánh. Hành vi chính xác phụ thuộc collation cụ thể, phiên bản Unicode mà collation dựa trên và thuộc tính như **PAD SPACE** hoặc **NO PAD**.

Không được xem hai collation là tương đương chỉ vì chúng cùng thuộc **utf8mb4**. Việc đổi collation có thể làm thay đổi kết quả **=**, **LIKE**, **ORDER BY**, **GROUP BY**, phép so sánh khóa và tính duy nhất của index.

## 2. Collation được kế thừa ở đâu?

MySQL có các giá trị mặc định ở nhiều cấp:

1. **Server:** character set và collation mặc định của instance.
2. **Database:** giá trị mặc định của database, thường được lấy từ mặc định server tại thời điểm tạo nếu không chỉ định.
3. **Table:** mặc định của bảng, thường được kế thừa từ database.
4. **Column:** collation của từng cột chuỗi, thường được kế thừa từ bảng.
5. **Connection và literal:** charset/collation dùng khi client gửi chuỗi và khi MySQL diễn giải literal trong session.

Ví dụ tạo database và bảng với giá trị rõ ràng:

```sql
CREATE DATABASE appdb
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;

CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    display_name VARCHAR(150) NOT NULL
) ENGINE = InnoDB
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_0900_ai_ci;
```

Trong ví dụ, cột **display_name** kế thừa character set và collation của bảng. Có thể ghi rõ ở cấp cột nếu một cột có yêu cầu so sánh khác:

```sql
CREATE TABLE external_identifiers (
    identifier VARCHAR(80)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_bin
        NOT NULL,
    PRIMARY KEY (identifier)
) ENGINE = InnoDB;
```

Cách này phù hợp với mã định danh mà hoa/thường hoặc từng ký tự phải được phân biệt theo quy tắc nhị phân. Hãy chọn collation theo ý nghĩa dữ liệu; không dùng **_bin** một cách máy móc cho mọi cột.

**Thay đổi mặc định không đồng nghĩa chuyển đổi dữ liệu hiện có.** **ALTER DATABASE ... CHARACTER SET ... COLLATE ...** thay mặc định cho các đối tượng tạo sau đó; nó không tự chuyển collation của mọi cột đã tồn tại. Tương tự, đổi default của bảng không tự chuyển các cột chuỗi cũ.

## 3. Collation coercibility là gì?

Khi một biểu thức có nhiều chuỗi với collation khác nhau, MySQL gán cho mỗi toán hạng một mức coercibility. Giá trị số càng nhỏ thì collation của toán hạng càng có ưu tiên cao khi phân giải.

Các mức phổ biến trong MySQL:

| Giá trị | Nguồn biểu thức | Ví dụ |
|---:|---|---|
| 0 | Explicit: có chỉ định **COLLATE** | **name COLLATE utf8mb4_bin** |
| 1 | Kết quả nối chuỗi có collation khác nhau | Một biểu thức **CONCAT()** trộn hai collation |
| 2 | Cột, tham số stored routine hoặc biến local | **customers.display_name** |
| 3 | System constant | **USER()**, **VERSION()** |
| 4 | String literal | **'hello'** |
| 5 | Giá trị số hoặc thời gian | **123**, **CURRENT_TIMESTAMP** |
| 6 | **NULL** hoặc biểu thức được suy ra từ **NULL** | **NULL** |

Mức coercibility không phải độ ưu tiên của một collation trong toàn server. Nó chỉ giúp MySQL xác định collation nào được chọn trong một biểu thức cụ thể.

### 3.1. Kiểm tra coercibility của biểu thức

Dùng các hàm sau:

- **CHARSET(expr):** trả về character set của biểu thức.
- **COLLATION(expr):** trả về collation của biểu thức.
- **COERCIBILITY(expr):** trả về mức coercibility của biểu thức.

Ví dụ:

```sql
SELECT
    CHARSET('hello') AS literal_charset,
    COLLATION('hello') AS literal_collation,
    COERCIBILITY('hello') AS literal_coercibility,
    COLLATION(USER()) AS user_collation,
    COERCIBILITY(USER()) AS user_coercibility;
```

Với một cột:

```sql
SELECT
    CHARSET(display_name) AS column_charset,
    COLLATION(display_name) AS column_collation,
    COERCIBILITY(display_name) AS column_coercibility
FROM customers
LIMIT 1;
```

Literal thường có coercibility 4, cột có coercibility 2 và system constant như **USER()** có coercibility 3. Vì cột có mức ưu tiên cao hơn literal, collation của cột thường được dùng khi literal có thể được chuyển phù hợp.

Có thể làm collation trở thành explicit:

```sql
SELECT
    COLLATION(
        _utf8mb4'hello' COLLATE utf8mb4_bin
    ) AS chosen_collation,
    COERCIBILITY(
        _utf8mb4'hello' COLLATE utf8mb4_bin
    ) AS chosen_coercibility;
```

Biểu thức có **COLLATE** rõ ràng có coercibility 0. Nó có ưu tiên cao nhất trong quá trình chọn collation.

## 4. MySQL phân giải các collation khác nhau như thế nào?

Quy tắc tổng quát:

1. So sánh mức coercibility của các toán hạng. Mức nhỏ hơn thường thắng.
2. Nếu mức bằng nhau, xét character set và tính chất Unicode/non-Unicode.
3. Nếu cùng character set nhưng collation khác nhau, quy tắc binary có thể được ưu tiên trong trường hợp phù hợp.
4. Nếu vẫn không có collation hợp lệ để chọn, MySQL báo lỗi trộn collation.

Một số quy tắc quan trọng khi mức coercibility bằng nhau:

- Nếu một chuỗi dùng character set Unicode và chuỗi kia dùng character set non-Unicode, MySQL thường ưu tiên Unicode và chuyển chuỗi non-Unicode sang Unicode.
- Nếu cả hai cùng character set nhưng collation khác nhau, một collation **_bin** có thể thắng collation **_ci** hoặc **_cs** tương ứng.
- Nếu cả hai cùng character set và đều có collation không binary khác nhau, MySQL có thể không tự chọn được và báo lỗi.
- Nếu hai toán hạng đều được chỉ định **COLLATE** rõ ràng nhưng collation xung đột, không nên mong MySQL tự đoán ý định; biểu thức cần được viết lại với một lựa chọn thống nhất.

Các quy tắc này có chi tiết theo loại biểu thức và phiên bản. Khi điều tra, hãy dùng **COERCIBILITY()**, **CHARSET()** và **COLLATION()** trên đúng các biểu thức tham gia thay vì chỉ nhìn tên cột.

## 5. Lỗi Illegal mix of collations thường xuất hiện khi nào?

Một lỗi thường gặp có dạng:

```text
Illegal mix of collations
(utf8mb4_general_ci,IMPLICIT)
and (utf8mb4_0900_ai_ci,IMPLICIT)
for operation '='
```

Tên collation và loại operation trong thông báo phụ thuộc dữ liệu cùng câu SQL. **IMPLICIT** thường chỉ toán hạng có nguồn từ cột hoặc biểu thức có coercibility tương ứng, không phải một thiết lập cấu hình mà người dùng cần bật.

### 5.1. JOIN hai cột khác collation

Giả sử hai bảng được tạo ở hai thời điểm khác nhau:

```sql
CREATE TABLE customers_legacy (
    customer_id BIGINT PRIMARY KEY,
    display_name VARCHAR(150)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_general_ci
        NOT NULL
) ENGINE = InnoDB;

CREATE TABLE customers_new (
    customer_id BIGINT PRIMARY KEY,
    display_name VARCHAR(150)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
        NOT NULL
) ENGINE = InnoDB;
```

Cả hai cột đều là **utf8mb4**, nhưng collation khác nhau. Trong điều kiện JOIN, hai cột đều có coercibility 2. Nếu MySQL không thể phân giải hai collation ở cùng mức ưu tiên, câu truy vấn có thể lỗi:

```sql
SELECT
    old.customer_id,
    old.display_name,
    newer.display_name
FROM customers_legacy AS old
JOIN customers_new AS newer
  ON old.display_name = newer.display_name;
```

Đây là tình huống điển hình của lỗi trộn collation: hai cột có cùng charset nhưng quy tắc so sánh khác nhau và không có một toán hạng nào có coercibility mạnh hơn để quyết định kết quả.

### 5.2. Literal, biến và system constant

Literal thường có coercibility 4 nên thường nhường collation cho cột có coercibility 2. Tuy nhiên, literal có introducer hoặc **COLLATE** tường minh có thể mang charset/collation khác.

Ví dụ chỉ định literal UTF-8 rõ ràng:

```sql
SELECT *
FROM customers
WHERE display_name =
    _utf8mb4'Nguyễn An' COLLATE utf8mb4_0900_ai_ci;
```

Biểu thức này có collation explicit. Nếu cột đang dùng một collation khác, phép so sánh sẽ áp dụng quy tắc của collation được chỉ định cho biểu thức. Cần bảo đảm collation được chọn đúng ý nghĩa nghiệp vụ.

System constant như **USER()** hoặc **VERSION()** có thể mang collation khác với cột. Khi so sánh với cột, coercibility của cột thường cao hơn system constant, nhưng vẫn nên kiểm tra nếu biểu thức được lồng trong **CONCAT()**, **CASE**, **UNION** hoặc hàm khác.

### 5.3. CONCAT, CASE, COALESCE và UNION

Lỗi không chỉ xuất hiện trong **=**. Các biểu thức kết hợp nhiều chuỗi cũng cần một collation chung:

```sql
SELECT CONCAT(
    legacy.display_name,
    modern.display_name
)
FROM customers_legacy AS legacy
JOIN customers_new AS modern
  ON legacy.customer_id = modern.customer_id;
```

Nếu hai chuỗi có collation khác nhau và cùng mức coercibility, biểu thức kết hợp có thể trở thành no-collation hoặc gây lỗi khi được dùng trong một ngữ cảnh yêu cầu collation cụ thể.

Các vị trí cần kiểm tra gồm:

- **CONCAT()** và toán tử biểu thức chuỗi.
- **CASE** có các nhánh trả về chuỗi từ các nguồn khác nhau.
- **COALESCE()** hoặc **IFNULL()** trộn cột và literal/cột khác collation.
- Các nhánh **UNION** có kiểu và collation không thống nhất.
- **ORDER BY**, **GROUP BY**, **LIKE** hoặc phép so sánh trên biểu thức đã được kết hợp.

## 6. Chẩn đoán lỗi bằng metadata và hàm coercibility

Không nên sửa bằng cách thêm **COLLATE** ngẫu nhiên vào mọi chỗ. Trước tiên xác định collation thực tế của từng cột và từng biểu thức.

### 6.1. Kiểm tra cấu hình server và connection

```sql
SELECT
    @@character_set_server AS server_charset,
    @@collation_server AS server_collation,
    @@character_set_database AS database_charset,
    @@collation_database AS database_collation,
    @@character_set_connection AS connection_charset,
    @@collation_connection AS connection_collation,
    @@character_set_client AS client_charset,
    @@character_set_results AS results_charset;
```

Các biến này cho biết mặc định server, database và session. Giá trị mặc định hiện tại không nhất thiết phản ánh collation của bảng đã tạo trước đó.

Có thể liệt kê các biến liên quan:

```sql
SHOW VARIABLES LIKE 'character_set%';
SHOW VARIABLES LIKE 'collation%';
```

### 6.2. Kiểm tra collation của cột

Dùng **SHOW FULL COLUMNS**:

```sql
SHOW FULL COLUMNS FROM customers_legacy;
SHOW FULL COLUMNS FROM customers_new;
```

Hoặc truy vấn **INFORMATION_SCHEMA.COLUMNS**:

```sql
SELECT
    TABLE_SCHEMA,
    TABLE_NAME,
    COLUMN_NAME,
    CHARACTER_SET_NAME,
    COLLATION_NAME,
    COLUMN_TYPE,
    IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND COLUMN_NAME = 'display_name'
ORDER BY TABLE_NAME;
```

Nếu hai cột dùng charset hoặc collation khác nhau, ghi nhận chính xác trước khi thay đổi. Cũng cần kiểm tra độ dài, nullability, default và index vì migration cột phải giữ nguyên các thuộc tính không liên quan.

### 6.3. Kiểm tra các collation có sẵn

```sql
SHOW COLLATION LIKE 'utf8mb4%';
```

Không phải mọi phiên bản MySQL đều có cùng danh sách collation. Ví dụ, các collation có hậu tố **0900** thuộc dòng MySQL 8.0; không thể mặc định chúng tồn tại trên MySQL 5.7 hoặc một sản phẩm tương thích MySQL khác.

### 6.4. Đo coercibility của các biểu thức

Khi nghi ngờ biểu thức nào gây lỗi, kiểm tra từng toán hạng độc lập:

```sql
SELECT
    CHARSET(display_name),
    COLLATION(display_name),
    COERCIBILITY(display_name)
FROM customers_legacy
LIMIT 1;
```

Kiểm tra literal và biểu thức hệ thống:

```sql
SELECT
    CHARSET('hello') AS literal_charset,
    COLLATION('hello') AS literal_collation,
    COERCIBILITY('hello') AS literal_coercibility,
    COLLATION(USER()) AS system_collation,
    COERCIBILITY(USER()) AS system_coercibility;
```

Với biểu thức kết hợp, hãy kiểm tra từng thành phần rồi kiểm tra kết quả **CONCAT()** hoặc **CASE** riêng. Điều này giúp xác định collation được kế thừa từ cột, literal, system constant hay được đặt tường minh.

## 7. Cách khắc phục ở cấp truy vấn

Nếu chưa thể thay đổi schema ngay, có thể dùng **COLLATE** để chỉ định rõ collation cho phép so sánh. Đây là cách xử lý có chủ đích cho một truy vấn hoặc một migration tạm thời.

### 7.1. Chọn một collation thống nhất cho phép JOIN

Với hai cột cùng charset **utf8mb4**, có thể chỉ định collation ở một phía:

```sql
SELECT
    old.customer_id,
    old.display_name,
    newer.display_name
FROM customers_legacy AS old
JOIN customers_new AS newer
  ON old.display_name COLLATE utf8mb4_0900_ai_ci
     = newer.display_name;
```

**COLLATE** làm toán hạng bên trái trở thành explicit, có coercibility 0. MySQL dùng collation được chỉ định để phân giải phép so sánh.

Chỉ chọn **utf8mb4_0900_ai_ci** nếu nghiệp vụ muốn so sánh không phân biệt hoa/thường và dấu theo quy tắc collation đó. Nếu mã định danh cần phân biệt từng ký tự, chọn collation khác phù hợp.

### 7.2. Chuyển charset trước khi chọn collation

Nếu hai cột khác character set, chỉ thêm **COLLATE** có thể chưa đủ vì collation phải thuộc character set tương ứng. Có thể chuyển một biểu thức sang charset chung rồi chỉ định collation:

```sql
SELECT *
FROM legacy_customers AS old
JOIN modern_customers AS newer
  ON CONVERT(old.display_name USING utf8mb4)
       COLLATE utf8mb4_0900_ai_ci
     = newer.display_name;
```

Phép **CONVERT()** trên cột có thể làm optimizer khó sử dụng index gốc của cột đó. Đây nên là biện pháp tạm thời hoặc dùng cho tập dữ liệu nhỏ, sau khi đã xác nhận cách chuyển đổi không làm mất ký tự.

### 7.3. Chỉ định collation cho literal

Nếu cột đã có collation chuẩn, có thể để cột quyết định collation và dùng literal có charset rõ ràng:

```sql
SELECT *
FROM customers
WHERE display_name =
    _utf8mb4'Nguyễn An';
```

Nếu cần ép quy tắc so sánh cụ thể, thêm **COLLATE** cho literal:

```sql
SELECT *
FROM customers
WHERE display_name =
    _utf8mb4'Nguyễn An' COLLATE utf8mb4_0900_ai_ci;
```

Cần phân biệt introducer **_utf8mb4** với **COLLATE**: introducer chỉ định character set của literal; **COLLATE** chỉ định quy tắc so sánh.

### 7.4. Kiểm tra lại execution plan

**COLLATE**, **CONVERT()** hoặc hàm áp dụng trên cột có thể ảnh hưởng đến khả năng dùng index. Sau khi sửa truy vấn, hãy kiểm tra:

```sql
EXPLAIN
SELECT
    old.customer_id,
    newer.display_name
FROM customers_legacy AS old
JOIN customers_new AS newer
  ON old.display_name COLLATE utf8mb4_0900_ai_ci
     = newer.display_name;
```

Xem **key**, **type**, **rows**, **possible_keys** và điều kiện join. Một truy vấn hết lỗi nhưng chuyển sang full table scan trên bảng lớn vẫn cần được xử lý tiếp.

## 8. Chuẩn hóa collation ở cấp schema

Nếu nhiều truy vấn thường xuyên phải thêm **COLLATE**, vấn đề có thể nằm ở schema. Về lâu dài, các cột cùng biểu diễn một khái niệm và tham gia JOIN nên dùng cùng character set và collation, trừ khi có yêu cầu nghiệp vụ rõ ràng để khác nhau.

### 8.1. Đổi mặc định database

```sql
ALTER DATABASE appdb
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;
```

Lệnh này thay mặc định cho đối tượng được tạo sau đó. Nó không tự chuyển collation của các cột hiện có.

### 8.2. Đổi mặc định bảng và chuyển các cột hiện có

Đổi mặc định của bảng cho các cột tạo sau:

```sql
ALTER TABLE customers
    DEFAULT CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;
```

Để chuyển các cột ký tự hiện có sang charset/collation mới:

```sql
ALTER TABLE customers
    CONVERT TO CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;
```

Lệnh **CONVERT TO CHARACTER SET** có thể xây dựng lại bảng và index. Thời gian, dung lượng tạm, lock và khả năng online phụ thuộc phiên bản, engine, kích thước bảng và loại thay đổi.

### 8.3. Đổi collation một cột

Có thể chỉ định lại cột bằng **MODIFY**:

```sql
ALTER TABLE customers
    MODIFY display_name VARCHAR(150)
        CHARACTER SET utf8mb4
        COLLATE utf8mb4_0900_ai_ci
        NOT NULL;
```

Khi dùng **MODIFY**, phải khai báo lại đầy đủ thuộc tính cột cần giữ như kiểu, độ dài, **NULL/NOT NULL**, **DEFAULT**, **COMMENT**, generated expression và thuộc tính liên quan. Bỏ sót thuộc tính có thể làm thay đổi schema ngoài ý muốn.

## 9. Rủi ro khi đổi collation

Đổi collation không chỉ là sửa lỗi kỹ thuật. Nó có thể thay đổi ý nghĩa so sánh của dữ liệu và làm thay đổi tính duy nhất của index.

### 9.1. Unique index có thể phát hiện giá trị trùng

Giả sử cột hiện tại dùng collation phân biệt hoa/thường, cho phép lưu cả **Alice** và **alice**. Nếu đổi sang collation không phân biệt hoa/thường, hai giá trị có thể được xem là bằng nhau. Khi tạo lại unique index, migration có thể thất bại vì duplicate key.

Trước khi đổi, kiểm tra các giá trị trùng theo collation đích. Ví dụ khi cột hiện tại đã dùng cùng character set **utf8mb4**:

```sql
SELECT
    display_name COLLATE utf8mb4_0900_ai_ci AS normalized_name,
    COUNT(*) AS value_count
FROM customers
GROUP BY display_name COLLATE utf8mb4_0900_ai_ci
HAVING COUNT(*) > 1;
```

Truy vấn này giúp phát hiện các giá trị khác nhau theo collation hiện tại nhưng tương đương theo collation đích. Với dữ liệu nhiều charset, hãy chuyển về charset chung trước khi áp dụng collation để kiểm tra.

Nếu có kết quả, cần quyết định quy tắc nghiệp vụ: hợp nhất, đổi mã, giữ collation phân biệt hoặc điều chỉnh unique key. Không tự động xóa một bản ghi để làm migration chạy qua.

### 9.2. Thứ tự sắp xếp và kết quả nhóm có thể thay đổi

Collation mới có thể thay đổi:

- Kết quả so sánh **=** và **LIKE**.
- Thứ tự **ORDER BY**.
- Nhóm của **GROUP BY** và kết quả **DISTINCT**.
- Việc kiểm tra duplicate trong unique index.
- Khả năng khớp trong JOIN và điều kiện tìm kiếm.

Một thay đổi collation vì thế có thể làm thay đổi logic nghiệp vụ ngay cả khi dữ liệu byte trong bảng không đổi.

### 9.3. Index và thời gian migration

Index chuỗi được xây dựng theo quy tắc collation. Khi collation thay đổi, MySQL có thể cần xây dựng lại index để thứ tự khóa phản ánh quy tắc mới. Cần đánh giá:

- Dung lượng bảng và index, bao gồm dung lượng tạm khi rebuild.
- Thời gian thực hiện và lock ảnh hưởng đến ứng dụng.
- Tác động đến replication lag và cửa sổ bảo trì.
- Khả năng tương thích của ứng dụng, driver, báo cáo và hệ thống tích hợp.
- Backup có thể restore và phương án quay lui.

Không giả định **ALTER TABLE ... CONVERT TO CHARACTER SET** luôn online hoặc tức thời. Thử migration trên bản sao dữ liệu gần production trước khi triển khai.

## 10. Kiểm tra charset và collation của kết nối

Ngay cả khi các cột đã chuẩn hóa, session client có thể gửi literal với charset/collation khác kỳ vọng. MySQL có các biến liên quan:

- **character_set_client:** charset mà server giả định cho dữ liệu client gửi.
- **character_set_connection:** charset dùng để chuyển literal và biểu thức chuỗi trong quá trình xử lý.
- **collation_connection:** collation mặc định của biểu thức chuỗi trong connection.
- **character_set_results:** charset server dùng khi gửi kết quả về client.

Có thể kiểm tra:

```sql
SELECT
    @@character_set_client,
    @@character_set_connection,
    @@collation_connection,
    @@character_set_results;
```

Trong mysql client, có thể đặt connection charset/collation bằng:

```sql
SET NAMES utf8mb4 COLLATE utf8mb4_0900_ai_ci;
```

Lệnh này tác động các biến charset của session liên quan đến client, connection và results. Trong ứng dụng Java dùng Connector/J, nên cấu hình encoding/collation qua driver và xác minh giá trị session sau khi kết nối. Không nên chạy **SET NAMES** tùy tiện nếu driver đã quản lý charset hoặc connection pool tái sử dụng session.

Charset của connection không tự đổi collation của cột. Một session dùng **utf8mb4_0900_ai_ci** vẫn có thể truy vấn bảng có cột **utf8mb4_general_ci**; khi đó MySQL tiếp tục áp dụng quy tắc coercibility để giải quyết biểu thức.

## 11. Quy trình xử lý lỗi trộn collation

Khi gặp **Illegal mix of collations**, hãy thực hiện theo trình tự:

1. **Đọc toàn bộ lỗi.** Ghi nhận các collation, coercibility trong ngoặc và operation gây lỗi như **=**, **LIKE** hoặc phép kết hợp.
2. **Xác định biểu thức.** Khoanh vùng điều kiện JOIN, WHERE, CONCAT, CASE, COALESCE hoặc UNION đang kết hợp chuỗi.
3. **Kiểm tra cột nguồn.** Dùng **SHOW FULL COLUMNS** hoặc **INFORMATION_SCHEMA.COLUMNS** để lấy charset/collation của từng cột.
4. **Kiểm tra coercibility.** Dùng **CHARSET()**, **COLLATION()** và **COERCIBILITY()** trên các toán hạng.
5. **Xác định quy tắc nghiệp vụ.** So sánh có cần phân biệt hoa/thường, dấu, ký tự hoặc khoảng trắng cuối không?
6. **Chọn biện pháp.** Dùng **COLLATE** cho trường hợp cục bộ; dùng **CONVERT()** khi cần thống nhất charset; lên kế hoạch chuẩn hóa schema nếu lỗi xuất hiện lặp lại.
7. **Kiểm tra dữ liệu trùng.** Trước khi đổi collation, tìm duplicate theo collation đích, nhất là khi có unique index.
8. **Kiểm tra execution plan.** Chạy **EXPLAIN** sau khi sửa để phát hiện index bị mất hoặc chi phí join tăng.
9. **Thử migration.** Backup, thử chuyển đổi trên staging và xác minh kết quả so sánh trước khi áp dụng production.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Cùng **utf8mb4** thì chắc chắn so sánh được | Hai cột cùng charset vẫn có thể có collation khác nhau và gây lỗi |
| **COLLATE** là đổi character set | **COLLATE** chọn quy tắc so sánh; **CONVERT(... USING ...)** đổi charset của biểu thức |
| Đổi default database sẽ chuyển mọi cột cũ | Chỉ đổi mặc định cho đối tượng tạo sau; cột hiện có cần migration |
| Thêm **COLLATE** ở bất kỳ phía nào cũng không ảnh hưởng hiệu năng | Biểu thức collation có thể làm thay đổi access path và khả năng dùng index |
| Collation **_ci** chỉ ảnh hưởng ORDER BY | Nó còn ảnh hưởng **=**, JOIN, GROUP BY, DISTINCT, LIKE và unique index |
| Không có lỗi sau khi đổi collation nghĩa là dữ liệu giữ nguyên ngữ nghĩa | Các chuỗi trước đây khác nhau có thể trở thành tương đương |
| Lỗi trộn collation luôn do connection | Thường có thể đến từ hai cột, biểu thức hoặc nhánh UNION khác collation |
| **SET NAMES** sẽ sửa collation của mọi bảng | Lệnh chỉ điều chỉnh charset/collation của session, không chuyển cột trong schema |

## 13. Ghi nhớ

- Character set quyết định cách mã hóa ký tự; collation quyết định cách so sánh và sắp xếp.
- Coercibility là mức ưu tiên khi MySQL chọn collation cho biểu thức; số càng nhỏ thì ưu tiên càng cao.
- Cột thường có coercibility 2, literal 4, system constant 3 và biểu thức có **COLLATE** tường minh 0.
- Hai cột cùng charset nhưng khác collation có thể gây **Illegal mix of collations** khi JOIN hoặc so sánh.
- Dùng **CHARSET()**, **COLLATION()**, **COERCIBILITY()**, **SHOW FULL COLUMNS** và **INFORMATION_SCHEMA.COLUMNS** để chẩn đoán.
- **COLLATE** có thể xử lý cục bộ; **CONVERT()** đổi charset biểu thức và có thể ảnh hưởng khả năng dùng index.
- Chuẩn hóa collation cho các cột cùng ý nghĩa là giải pháp lâu dài, nhưng phải kiểm tra duplicate, unique index, thứ tự sắp xếp và execution plan.
- Thay đổi collation có thể cần rebuild bảng/index, cần backup và thử migration trước production.
- Connection collation và column collation là hai cấp khác nhau; **SET NAMES** không chuyển đổi schema hiện có.

Khi nắm được coercibility và quy tắc phân giải collation, bạn có thể tìm đúng nguồn gây lỗi trộn collation, lựa chọn quy tắc so sánh phù hợp với nghiệp vụ và triển khai thay đổi schema an toàn mà vẫn kiểm soát được hiệu năng MySQL.

