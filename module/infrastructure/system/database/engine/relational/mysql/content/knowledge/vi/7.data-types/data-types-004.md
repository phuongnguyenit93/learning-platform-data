# Độ rộng hiển thị số nguyên, ZEROFILL và tương thích phiên bản

Trong MySQL, khai báo `INT(11)` không có nghĩa cột chứa tối đa 11 chữ số, cũng không làm số nguyên chiếm nhiều byte hơn `INT`. Con số trong ngoặc là độ rộng hiển thị (display width), một metadata cũ có thể được client sử dụng khi trình bày kết quả. Thuộc tính `ZEROFILL` từng dùng độ rộng này để thêm số 0 ở đầu giá trị, nhưng cả display width của kiểu số nguyên và `ZEROFILL` đã bị đánh dấu deprecated từ MySQL 8.0.17.

Khi thiết kế schema cho **DATABASE_MYSQL**, hãy chọn kiểu số nguyên dựa trên miền giá trị và dung lượng cần thiết. Việc định dạng số thành chuỗi có độ dài cố định nên được thực hiện ở tầng trình bày hoặc bằng biểu thức rõ ràng, thay vì phụ thuộc vào thuộc tính cũ của cột.

## 1. Độ rộng hiển thị số nguyên là gì?

Trong cú pháp MySQL truyền thống, có thể khai báo độ rộng sau tên kiểu số nguyên:

```sql
CREATE TABLE legacy_number_example (
    id INT(11),
    short_code SMALLINT(4),
    tiny_value TINYINT(1)
);
```

Các số `11`, `4` và `1` là display width. Chúng không thay đổi:

- Số byte MySQL dùng để lưu kiểu số nguyên.
- Miền giá trị hợp lệ của kiểu số nguyên.
- Số chữ số tối đa mà kiểu số nguyên có thể lưu.
- Quy tắc tràn số (overflow) của kiểu dữ liệu.

Ví dụ, `INT(3)` vẫn có thể lưu `123456`, vì miền giá trị được quyết định bởi kiểu `INT`, không phải số `3` trong ngoặc. Ngược lại, `SMALLINT(8)` không thể lưu một số lớn hơn miền `SMALLINT` chỉ vì display width là `8`.

Display width chủ yếu được đưa vào metadata kết quả. Với cột không có `ZEROFILL`, một số client có thể dùng độ rộng này để căn lề hoặc đệm khoảng trắng khi hiển thị; việc sử dụng hay không là quyết định của ứng dụng. Bản thân MySQL không dùng `INT(11)` để giới hạn giá trị ở 11 chữ số.

### Không nhầm display width với precision

Các con số trong ngoặc ở những kiểu dữ liệu khác có thể mang ý nghĩa khác:

| Kiểu dữ liệu | Ý nghĩa phần trong ngoặc | Ví dụ |
|---|---|---|
| `INT(11)` trong cú pháp cũ | Độ rộng hiển thị; không phải giới hạn giá trị | `INT(11)` và `INT` có cùng miền giá trị |
| `DECIMAL(10,2)` | Tổng số chữ số là 10, trong đó 2 chữ số sau dấu thập phân | Tối đa 8 chữ số phần nguyên và 2 chữ số phần lẻ |
| `VARCHAR(50)` | Độ dài tối đa của chuỗi theo đơn vị ký tự của kiểu dữ liệu | Chuỗi có tối đa 50 ký tự |

Do đó, không thể suy luận ý nghĩa của số trong ngoặc chỉ bằng cách nhìn cú pháp. Với `INT(M)`, `M` là display width cũ; với `DECIMAL(P,S)`, `P` và `S` là precision và scale.

## 2. Miền giá trị và dung lượng của kiểu số nguyên

Kích thước lưu trữ và miền giá trị được quyết định bởi kiểu cơ sở và thuộc tính `SIGNED`/`UNSIGNED`:

| Kiểu | Dung lượng | Miền `SIGNED` | Miền `UNSIGNED` |
|---|---:|---:|---:|
| `TINYINT` | 1 byte | -128 đến 127 | 0 đến 255 |
| `SMALLINT` | 2 byte | -32.768 đến 32.767 | 0 đến 65.535 |
| `MEDIUMINT` | 3 byte | -8.388.608 đến 8.388.607 | 0 đến 16.777.215 |
| `INT` / `INTEGER` | 4 byte | -2.147.483.648 đến 2.147.483.647 | 0 đến 4.294.967.295 |
| `BIGINT` | 8 byte | -9.223.372.036.854.775.808 đến 9.223.372.036.854.775.807 | 0 đến 18.446.744.073.709.551.615 |

Ví dụ, các khai báo sau có cùng dung lượng và miền giá trị:

```sql
INT
INT(11)
INT(3)
```

Tương tự, `BIGINT(20)` vẫn là số nguyên 8 byte. Nếu cần lưu ID có thể vượt giới hạn của `INT`, hãy chuyển sang `BIGINT`; tăng con số trong ngoặc không giải quyết được giới hạn miền giá trị.

`UNSIGNED` mở rộng miền giá trị theo hướng không âm. Chỉ dùng nó khi nghiệp vụ thực sự không cho phép số âm, chẳng hạn số lượng sản phẩm hoặc ID tăng dần. Không chọn `UNSIGNED` chỉ để làm số hiển thị dài hơn.

## 3. `ZEROFILL` hoạt động như thế nào?

`ZEROFILL` là thuộc tính mở rộng riêng của MySQL. Khi kết hợp với display width, nó yêu cầu thêm số `0` ở bên trái khi giá trị được hiển thị.

Ví dụ trong cú pháp cũ:

```sql
CREATE TABLE legacy_invoice (
    invoice_id INT(5) ZEROFILL NOT NULL
);

INSERT INTO legacy_invoice (invoice_id)
VALUES (42), (1234);

SELECT invoice_id
FROM legacy_invoice;
```

Kết quả được hiển thị theo dạng:

```text
00042
01234
```

Độ rộng `5` tạo số 0 ở đầu để giá trị có tối thiểu 5 ký tự số trong trường hợp này. Nó không giới hạn giá trị ở 5 chữ số; số lớn hơn vẫn có thể hiển thị đầy đủ.

Một tác động quan trọng của `ZEROFILL` là MySQL tự động thêm thuộc tính `UNSIGNED` cho cột. Vì vậy, cột `INT(5) ZEROFILL` không chấp nhận số âm. Nếu hệ thống cũ đang dùng `ZEROFILL`, khi thay thế cần kiểm tra cả logic định dạng lẫn giả định về miền giá trị.

`ZEROFILL` cũng không phải một kiểu dữ liệu riêng. Cột vẫn là kiểu số nguyên và có thể được dùng trong phép tính số học. Tuy nhiên, định dạng có thể không được giữ nguyên khi giá trị tham gia biểu thức hoặc `UNION`; không nên dựa vào `ZEROFILL` như một định dạng chuỗi ổn định cho mọi câu truy vấn.

## 4. `TINYINT(1)` và kiểu BOOLEAN

MySQL cung cấp `BOOL` và `BOOLEAN` như các từ đồng nghĩa của `TINYINT(1)`. Đây là quy ước tương thích phổ biến, không phải kiểu boolean có miền giá trị vật lý chỉ gồm `0` và `1`.

```sql
CREATE TABLE feature_flags (
    id BIGINT PRIMARY KEY,
    is_enabled BOOLEAN NOT NULL DEFAULT FALSE
);
```

Về bản chất, `is_enabled` là `TINYINT(1)`. Giá trị `0` được xem là false; giá trị khác `0` được xem là true trong ngữ cảnh boolean. Nếu không có ràng buộc bổ sung, cột vẫn có thể lưu các giá trị số nguyên khác như `2` hoặc `-1` (trừ khi khai báo `UNSIGNED`, khi đó không nhận số âm).

MySQL Connectors thường xem `TINYINT(1)` là dấu hiệu cột có nguồn gốc boolean. Vì lý do tương thích này, `TINYINT(1)` là trường hợp đặc biệt vẫn được giữ trong một số đầu ra metadata sau thay đổi display width ở MySQL 8.0.19. Nhưng điều đó không làm `TINYINT(1)` trở thành kiểu boolean độc lập hay ép miền giá trị chỉ còn `0` và `1`.

Nếu nghiệp vụ bắt buộc chỉ có hai trạng thái, hãy áp dụng kiểm soát ở schema hoặc tầng ứng dụng. Với MySQL 8.0.16 trở lên, có thể dùng `CHECK` constraint:

```sql
CREATE TABLE feature_flags (
    id BIGINT PRIMARY KEY,
    is_enabled TINYINT NOT NULL DEFAULT 0,
    CONSTRAINT chk_feature_flags_is_enabled
        CHECK (is_enabled IN (0, 1))
);
```

Trên các phiên bản MySQL cũ hơn 8.0.16, `CHECK` constraint chưa được thực thi như ràng buộc dữ liệu, vì vậy cần xác minh phiên bản trước khi dựa vào nó.

## 5. Tương thích giữa các phiên bản MySQL

Điểm thay đổi quan trọng bắt đầu từ MySQL 8.0.17:

| Phiên bản | Display width của integer | `ZEROFILL` | Ảnh hưởng thực tế |
|---|---|---|---|
| MySQL 5.7 | Được hỗ trợ theo cú pháp cũ | Được hỗ trợ | `INT(11)` và `ZEROFILL` có thể xuất hiện trong DDL và metadata |
| MySQL 8.0.16 trở xuống | Được hỗ trợ | Được hỗ trợ | Chưa có cảnh báo deprecated như từ 8.0.17 |
| MySQL 8.0.17 trở lên | Deprecated | Deprecated | Tạo hoặc sửa cột có các thuộc tính này phát cảnh báo; nên chuyển sang cách biểu diễn khác |
| MySQL 8.0.19 trở lên | Deprecated; đầu ra metadata không còn hiển thị display width integer trong đa số trường hợp | Vẫn được thể hiện cùng display width nếu cột có `ZEROFILL` | `TINYINT(1)` là ngoại lệ tương thích cho connector; đối tượng cũ có thể còn metadata khác nhau |
| MySQL 8.4 | Vẫn được tài liệu đánh dấu deprecated | Vẫn được tài liệu đánh dấu deprecated | Không nên tạo schema mới phụ thuộc vào các thuộc tính này; kiểm tra cảnh báo và hành vi trên đúng bản phát hành |

Từ MySQL 8.0.17, server phát cảnh báo rằng integer display width và `ZEROFILL` đã deprecated và có thể bị loại bỏ trong một phiên bản tương lai. Không nên tự suy đoán một phiên bản cụ thể sẽ loại bỏ chúng nếu tài liệu của bản phát hành đích chưa xác nhận. Hãy kiểm tra release notes và chạy migration trên đúng phiên bản mục tiêu.

Từ MySQL 8.0.19, `SHOW CREATE TABLE`, `DESCRIBE` và một số đầu ra `INFORMATION_SCHEMA` không còn trình bày display width của integer trong các trường hợp thông thường. Ngoại lệ gồm `TINYINT(1)` và cột có `ZEROFILL`. Với đối tượng được tạo ở các bản MySQL 8.0 cũ hơn, metadata đã lưu trong data dictionary có thể vẫn giữ thông tin cũ. Nâng cấp từ MySQL 5.7 lên MySQL 8.0 có quy trình tái tạo data dictionary, do đó kết quả metadata có thể khác.

Điều này có thể ảnh hưởng đến script so sánh schema nếu script so sánh chuỗi `COLUMN_TYPE` hoặc kết quả `SHOW CREATE TABLE` theo kiểu tuyệt đối. Công cụ migration nên so sánh ý nghĩa kiểu dữ liệu, nullability, signedness, default và constraint thay vì coi display width là kích thước miền giá trị.

## 6. Kiểm tra cảnh báo và metadata trên máy chủ

Kiểm tra phiên bản trước khi chạy DDL:

```sql
SELECT VERSION();
```

Trên MySQL 8.0.17 trở lên, có thể quan sát cảnh báo bằng ví dụ legacy sau trong schema thử nghiệm:

```sql
CREATE TABLE legacy_width_demo (
    id INT(11) NOT NULL,
    code INT(5) ZEROFILL NOT NULL,
    PRIMARY KEY (id)
);

SHOW WARNINGS;
```

Server có thể báo mã cảnh báo `1681` cho thuộc tính deprecated. Cảnh báo cụ thể và đầu ra metadata phụ thuộc phiên bản. Đừng dùng DDL legacy này cho schema mới; nó chỉ nhằm giúp nhận biết khi bảo trì hệ thống cũ.

Để xem định nghĩa bảng và metadata:

```sql
SHOW CREATE TABLE legacy_width_demo;
DESCRIBE legacy_width_demo;

SELECT COLUMN_NAME, DATA_TYPE, COLUMN_TYPE, NUMERIC_PRECISION
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'legacy_width_demo';
```

Hãy so sánh kết quả trên MySQL 5.7, MySQL 8.0.17, MySQL 8.0.19+ hoặc phiên bản đang dùng trong tổ chức. `COLUMN_TYPE` có thể giữ hoặc bỏ thông tin display width tùy phiên bản và lịch sử tạo/nâng cấp đối tượng. `NUMERIC_PRECISION` phản ánh precision theo định nghĩa kiểu dữ liệu; nó không phải display width cũ.

## 7. Thay thế `ZEROFILL` bằng cách định dạng rõ ràng

Nếu cần hiển thị ID có độ dài tối thiểu 8 chữ số, hãy giữ dữ liệu ở kiểu số nguyên và định dạng ở lúc truy vấn:

```sql
SELECT
    id,
    LPAD(CAST(id AS CHAR), 8, '0') AS formatted_id
FROM invoices;
```

Ví dụ `id = 42` tạo `formatted_id = '00000042'`. Cần bảo đảm độ rộng đích đủ lớn cho mọi giá trị; `LPAD()` có thể cắt chuỗi nếu chuỗi đầu vào dài hơn độ dài yêu cầu. Nếu ID có thể vượt 8 chữ số, hãy chọn độ rộng phù hợp hoặc định dạng trong ứng dụng với kiểm tra rõ ràng.

Trong Java, có thể định dạng số nguyên không âm ở tầng trình bày:

```java
long id = 42L;
String formattedId = String.format("%08d", id);
// formattedId = "00000042"
```

Việc định dạng ở ứng dụng giúp API, giao diện web và báo cáo quyết định cách hiển thị mà không thay đổi kiểu lưu trữ của database. Nếu cần sắp xếp số, hãy sắp xếp theo cột số nguyên trước khi chuyển thành chuỗi.

### Khi nào nên lưu mã dưới dạng chuỗi?

Không phải mọi mã có chữ số đều là số dùng cho tính toán. Nếu số 0 ở đầu là một phần định danh có ý nghĩa, chẳng hạn mã bưu chính, mã chi nhánh hoặc mã sản phẩm `000042`, hãy cân nhắc `CHAR` hoặc `VARCHAR`:

```sql
CREATE TABLE product_catalog (
    product_code CHAR(6) NOT NULL,
    product_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (product_code)
);
```

`product_code` là định danh dạng văn bản; không cộng, trừ hoặc tính toán trên nó. Lưu bằng chuỗi giữ nguyên số 0 ở đầu và tránh phải tái tạo định dạng mỗi khi đọc dữ liệu.

Ngược lại, với khóa chính tự tăng hoặc số lượng hàng, nên lưu kiểu số nguyên phù hợp và chỉ định dạng khi trình bày. Không lưu số đã đệm số 0 thành chuỗi nếu nghiệp vụ cần phép so sánh số học.

## 8. Thiết kế schema mới không phụ thuộc display width

Thay vì khai báo:

```sql
CREATE TABLE legacy_customer (
    id INT(11) NOT NULL AUTO_INCREMENT,
    branch_code INT(4) ZEROFILL,
    PRIMARY KEY (id)
);
```

Hãy chọn kiểu số nguyên theo miền giá trị và tách định dạng khỏi lưu trữ:

```sql
CREATE TABLE customer (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    branch_code SMALLINT UNSIGNED NOT NULL,
    PRIMARY KEY (id)
);
```

Nếu `branch_code` thực chất là mã cố định 4 ký tự và có thể có số 0 đầu, kiểu chuỗi phù hợp hơn:

```sql
CREATE TABLE customer (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    branch_code CHAR(4) NOT NULL,
    PRIMARY KEY (id)
);
```

Lựa chọn giữa `SMALLINT UNSIGNED` và `CHAR(4)` phụ thuộc ý nghĩa nghiệp vụ:

- Dùng số nguyên nếu mã đại diện cho một đại lượng số, cần tính toán hoặc so sánh theo giá trị số.
- Dùng chuỗi nếu mã là nhãn/định danh, giữ số 0 đầu hoặc có thể chứa chữ cái và ký tự khác.

Không chọn `INT(4)` để ép một mã chỉ có bốn chữ số; kiểu này vẫn cho phép toàn bộ miền `INT`. Nếu cần giới hạn miền giá trị, dùng kiểu cơ sở nhỏ hơn, `UNSIGNED`, `CHECK` constraint phù hợp hoặc quy tắc xác thực nghiệp vụ.

## 9. Kế hoạch nâng cấp schema cũ

Khi chuyển ứng dụng từ MySQL 5.7 sang MySQL 8.0 hoặc các bản phát hành mới hơn, hãy kiểm tra DDL có `INT(M)`, `BIGINT(M)` hoặc `ZEROFILL` hay không.

Quy trình đề xuất:

1. Lấy DDL hiện tại bằng `SHOW CREATE TABLE` và lưu kết quả cùng bản backup.
2. Tìm các định nghĩa integer có display width tường minh và các cột có `ZEROFILL` trong migration/schema source.
3. Xác định ứng dụng có đang dựa vào việc hiển thị số 0 đầu, metadata width hoặc tính `UNSIGNED` ngầm do `ZEROFILL` tạo ra không.
4. Chọn kiểu cơ sở dựa trên miền giá trị; khai báo `UNSIGNED` tường minh nếu cột chỉ lưu giá trị không âm.
5. Chuyển định dạng sang `LPAD`, Java formatter hoặc kiểu `CHAR`/`VARCHAR` nếu mã là định danh dạng chuỗi.
6. Chạy migration trên bản sao dữ liệu, so sánh kết quả, kiểm tra ORM/JDBC mapping và API contract.
7. Chỉ triển khai sau khi các client, báo cáo, export và tích hợp bên ngoài đã tương thích.

Đặc biệt, nếu cột cũ có `ZEROFILL`, hãy xác minh rằng việc bỏ thuộc tính không vô tình cho phép số âm. `ZEROFILL` từng ngầm làm cột `UNSIGNED`; khi bỏ nó, cần thêm `UNSIGNED` tường minh nếu đó vẫn là quy tắc nghiệp vụ.

## 10. Bài tập thực hành

1. Tạo bảng thử nghiệm có các cột `INT`, `INT(11)`, `INT(3)`, `SMALLINT(4)` và so sánh `SHOW CREATE TABLE` trên phiên bản MySQL đang dùng.
2. Thử chèn một giá trị có nhiều chữ số hơn display width vào `INT(3)` và giải thích vì sao vẫn được lưu nếu giá trị nằm trong miền `INT`.
3. Trên môi trường thử nghiệm tương thích, tạo `INT(5) ZEROFILL`, chèn giá trị `42`, quan sát kết quả và kiểm tra `SHOW WARNINGS`.
4. Kiểm tra `ZEROFILL` có làm cột thành `UNSIGNED` không bằng `SHOW CREATE TABLE` và thử giá trị âm trong schema thử nghiệm.
5. Tạo cột `BOOLEAN`, thử các giá trị `0`, `1` và `2`; giải thích vì sao `BOOLEAN` trong MySQL không tự giới hạn miền giá trị ở hai trạng thái.
6. Thay cách hiển thị bằng `LPAD(CAST(id AS CHAR), 8, '0')` và so sánh kết quả với định dạng ở Java.
7. Viết lại một DDL cũ để bỏ display width và `ZEROFILL`, đồng thời giữ đúng miền giá trị và quy tắc mã nghiệp vụ.

Bạn hoàn thành bài khi giải thích được vì sao `INT(11)` không phải số chữ số tối đa, vì sao `ZEROFILL` ảnh hưởng cả `UNSIGNED`, nhận diện cảnh báo deprecated từ MySQL 8.0.17 và xử lý khác biệt metadata từ 8.0.19. Khi thiết kế mới, hãy chọn kiểu số theo miền giá trị và giữ việc định dạng số 0 đầu ở tầng trình bày hoặc dùng kiểu chuỗi nếu đó là một phần của định danh.
